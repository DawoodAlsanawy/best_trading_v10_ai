#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_live_monitoring.py — إصلاحان حاسمان لـ run_live:

Fix A: Apex call يستخدم sig.action و pos.entry_px بشكل خاطئ.
       الإصلاح: pos['action'], pos['entry'].
Fix B: _place_protective_orders يحاول وضع Partial-TP بدون sl_dist0.
       الإصلاح: تعطيل Partial إذا _partial_price <= 0.

لا يمس الباكتيست.
"""

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# FIX A: Apex call — line-based
# ═══════════════════════════════════════════════════════════════

APEX_OLD_LINE = "sig.action, pos.entry_px, p, ad, fi"
APEX_NEW_LINE = "pos['action'], pos['entry'], p, ad, fi"

# الحد الأدنى للإزاحة للتمييز بين الباكتيست (16 مسافة) والـ live (28 مسافة)
MIN_INDENT_FOR_LIVE = 20


def fix_apex_call(lines):
    """
    يُعيد (modified_count, positions).
    يبحث عن الأسطر التي:
      - محتواها الأساسي = APEX_OLD_LINE
      - الإزاحة >= MIN_INDENT_FOR_LIVE
    """
    positions = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped != APEX_OLD_LINE:
            continue
        indent = len(line) - len(line.lstrip(' '))
        if indent < MIN_INDENT_FOR_LIVE:
            continue
        lines[i] = ' ' * indent + APEX_NEW_LINE
        positions.append(i + 1)
    return len(positions), positions


# ═══════════════════════════════════════════════════════════════
# FIX B: partial_enabled check
# ═══════════════════════════════════════════════════════════════

# نُدرج بعد كتلة if _partial_enabled and _sl_dist0 > 0 and _entry_px > 0:
PARTIAL_BLOCK_ANCHOR = """        if _partial_enabled and _sl_dist0 > 0 and _entry_px > 0:
            _partial_r = float(getattr(CFG, 'PARTIAL_TP_R', 1.5))
            if action == 'BUY':
                _partial_price = _entry_px + _sl_dist0 * _partial_r
            else:
                _partial_price = _entry_px - _sl_dist0 * _partial_r
            # تأكد أن Partial TP أدنى من Full TP في الاتجاه الصحيح
            if action == 'BUY' and _partial_price >= tp:
                _partial_enabled = False
            elif action == 'SELL' and _partial_price <= tp:
                _partial_enabled = False"""

PARTIAL_BLOCK_NEW = """        if _partial_enabled and _sl_dist0 > 0 and _entry_px > 0:
            _partial_r = float(getattr(CFG, 'PARTIAL_TP_R', 1.5))
            if action == 'BUY':
                _partial_price = _entry_px + _sl_dist0 * _partial_r
            else:
                _partial_price = _entry_px - _sl_dist0 * _partial_r
            # تأكد أن Partial TP أدنى من Full TP في الاتجاه الصحيح
            if action == 'BUY' and _partial_price >= tp:
                _partial_enabled = False
            elif action == 'SELL' and _partial_price <= tp:
                _partial_enabled = False
        # [FIX-B] إذا لم يُحسب سعر Partial (sl_dist0 = 0)، عطّله
        if _partial_enabled and _partial_price <= 0:
            _partial_enabled = False"""

FIX_B_MARKER = "[FIX-B] إذا لم يُحسب سعر Partial"


# ═══════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"❌ {args.file} غير موجود")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("═" * 70)
    print("  fix_live_monitoring.py")
    print("═" * 70)
    print()

    # ── Fix A ──
    lines = text.split('\n')
    n_fixed, positions = fix_apex_call(lines)
    if n_fixed == 0:
        # تحقق إن كان مُطبَّقاً مسبقاً
        if APEX_NEW_LINE in text:
            print("  ⏭️  Fix A: مُطبَّق مسبقاً")
        else:
            print(f"  ❌ Fix A: لم أجد سطر '{APEX_OLD_LINE}' بإزاحة ≥ {MIN_INDENT_FOR_LIVE}")
            print()
            print("  🔍 جميع المواضع (لاستكشاف اليدوي):")
            for i, line in enumerate(lines, 1):
                if APEX_OLD_LINE in line:
                    indent = len(line) - len(line.lstrip(' '))
                    print(f"    [{i:5d}] (indent={indent}) {line.strip()[:80]}")
            return 2
    else:
        text = '\n'.join(lines)
        print(f"  ✅ Fix A: أُصلح {n_fixed} موضع (الأسطر: {positions})")

    # ── Fix B ──
    if FIX_B_MARKER in text:
        print("  ⏭️  Fix B: مُطبَّق مسبقاً")
    elif PARTIAL_BLOCK_ANCHOR in text:
        text = text.replace(PARTIAL_BLOCK_ANCHOR, PARTIAL_BLOCK_NEW, 1)
        print("  ✅ Fix B: partial_enabled safety أُضيف")
    else:
        print("  ⚠️  Fix B: لم أجد كتلة _partial_enabled — تخطّي")

    # ── التحقق ──
    try:
        ast.parse(text)
        print()
        print("  ✅ الصياغة صحيحة (ast.parse)")
    except SyntaxError as e:
        print()
        print(f"  ❌ خطأ صياغة: {e.lineno}: {e.text}")
        return 3

    if text == original:
        print()
        print("  ℹ️  لا تعديلات جديدة.")
        return 0

    if args.dry_run:
        print()
        print("═" * 70)
        print("  ℹ️  Dry run — لم يُكتب أي شيء")
        print("═" * 70)
        return 0

    # ── Backup + Write ──
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_mon_{ts}')
    shutil.copy2(p, backup)
    print()
    print(f"  💾 Backup: {backup}")

    p.write_text(text, encoding='utf-8')
    print(f"  ✏️  كُتب: {p}")
    print()
    print("═" * 70)
    print("  ✅ تم")
    print("═" * 70)
    print(f"  للتراجع: cp {backup.name} {p.name}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
