#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تطبيق إصلاحات ما قبل Testnet على trading_2.py

الإصلاحات:
  1. V1: _partial_tp fee (MAKER → MAKER+TAKER) — مُختبر ومُعتمد
  2. _trade_log_from_live: net_pnl=None → محسوب
  3. _promote_pending_to_position: signature bug fix
  4. Capital source: 'free' → 'total' مع fallback

مبادئ:
  - لا يعدّل شيئاً إذا فشل أي patch → all-or-nothing
  - Backup تلقائي مع timestamp
  - Idempotent: لا يُعيد التطبيق
  - ast.parse بعد كل التعديلات
  - Dry-run للمعاينة

التشغيل:
    python3 apply_live_fixes.py --dry-run    # معاينة
    python3 apply_live_fixes.py              # تطبيق فعلي
"""

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# تعريف الإصلاحات
# ═══════════════════════════════════════════════════════════════

# ── Fix #1: _partial_tp fee (V1 — مُختبر ومُعتمد) ──
FIX1_NAME = "V1: partial_tp fee (MAKER → MAKER+TAKER)"
FIX1_DONE_MARKER = "_exit_fee  = _close_qty * px * CFG.TAKER_FEE"
FIX1_PATTERN = re.compile(
    r'^(?P<indent>[ \t]+)_fee = _close_qty \* \(pos\.entry_px \+ px\) \* CFG\.MAKER_FEE[ \t]*$',
    re.MULTILINE,
)

def fix1_replace(match):
    ind = match.group('indent')
    return (
        f"{ind}_entry_fee = _close_qty * pos.entry_px * CFG.MAKER_FEE\n"
        f"{ind}_exit_fee  = _close_qty * px * CFG.TAKER_FEE\n"
        f"{ind}_fee = _entry_fee + _exit_fee"
    )


# ── Fix #2: net_pnl في _trade_log_from_live ──
FIX2_NAME = "_trade_log_from_live: net_pnl محسوب بدل None"
FIX2_DONE_MARKER = "net_pnl=float(_net_pnl_lg)"
FIX2_PATTERN = re.compile(
    r'(?P<indent>[ \t]+)_trade_log_from_live\(\s*\n'
    r'(?P=indent)\s+pos, exec_price, exit_reason,\s*\n'
    r'(?P=indent)\s+ad=assets\.get\(sym\),\s*\n'
    r'(?P=indent)\s+net_pnl=None,\s*\n'
    r'(?P=indent)\)',
    re.MULTILINE,
)

def fix2_replace(match):
    ind = match.group('indent')
    return (
        f"{ind}# احسب net_pnl من الدخول/الخروج/الكمية + الربح الجزئي\n"
        f"{ind}_entry_px_lg = float(pos.get('entry') or 0)\n"
        f"{ind}_exit_px_lg  = float(exec_price or 0)\n"
        f"{ind}_qty_lg      = float(pos.get('qty') or 0)\n"
        f"{ind}_partial_lg  = float(pos.get('_partial_pnl', 0.0))\n"
        f"{ind}if pos.get('action') == 'BUY':\n"
        f"{ind}    _net_pnl_lg = (_exit_px_lg - _entry_px_lg) * _qty_lg + _partial_lg\n"
        f"{ind}else:\n"
        f"{ind}    _net_pnl_lg = (_entry_px_lg - _exit_px_lg) * _qty_lg + _partial_lg\n"
        f"{ind}_trade_log_from_live(\n"
        f"{ind}    pos, exec_price, exit_reason,\n"
        f"{ind}    ad=assets.get(sym),\n"
        f"{ind}    net_pnl=float(_net_pnl_lg),\n"
        f"{ind})"
    )


# ── Fix #3: _promote_pending_to_position signature ──
FIX3_NAME = "_promote_pending_to_position: exchange argument missing"
FIX3_DONE_MARKER = "_promote_pending_to_position(exchange, sym, rec2, open_pos_live)"
FIX3_PATTERN = re.compile(
    r'(?<!exchange, )_promote_pending_to_position\(\s*sym,\s*rec2,\s*open_pos_live\s*\)',
)

FIX3_REPLACEMENT = "_promote_pending_to_position(exchange, sym, rec2, open_pos_live)"


# ── Fix #4: Capital source ──
FIX4_NAME = "Capital source: 'free' → 'total' (with fallback)"
FIX4_DONE_MARKER = "bal['USDT'].get('total')"
FIX4_PATTERN = re.compile(
    r"cap_live = float\(bal\['USDT'\]\['free'\]\)",
)

FIX4_REPLACEMENT = "cap_live = float(bal['USDT'].get('total') or bal['USDT'].get('free') or 0)"


# ═══════════════════════════════════════════════════════════════
# محرك التطبيق
# ═══════════════════════════════════════════════════════════════

class Fix:
    def __init__(self, name, done_marker, pattern, replacer, expected_count=1):
        self.name = name
        self.done_marker = done_marker
        self.pattern = pattern
        self.replacer = replacer  # callable(match) or str
        self.expected_count = expected_count

    def is_applied(self, text):
        return self.done_marker in text

    def apply(self, text):
        """يُعيد (new_text, count). count = عدد التطبيقات."""
        if callable(self.replacer):
            return self.pattern.subn(self.replacer, text)
        else:
            return self.pattern.subn(self.replacer, text)


def process_file(path, dry_run=False):
    p = Path(path)
    if not p.exists():
        print(f"❌ {path} غير موجود")
        return 1

    original = p.read_text(encoding='utf-8')

    fixes = [
        Fix(FIX1_NAME, FIX1_DONE_MARKER, FIX1_PATTERN, fix1_replace, 1),
        Fix(FIX2_NAME, FIX2_DONE_MARKER, FIX2_PATTERN, fix2_replace, 1),
        Fix(FIX3_NAME, FIX3_DONE_MARKER, FIX3_PATTERN, FIX3_REPLACEMENT, 1),
        Fix(FIX4_NAME, FIX4_DONE_MARKER, FIX4_PATTERN, FIX4_REPLACEMENT, 1),
    ]

    print(f"📄 الملف: {path}")
    print(f"📊 الحجم: {len(original):,} حرف")
    print()

    # ── مرحلة الفحص ──
    text = original
    applied_count = 0
    skipped_count = 0
    preview_blocks = []

    for i, fix in enumerate(fixes, 1):
        if fix.is_applied(text):
            print(f"  [{i}] ⏭️  {fix.name}")
            print(f"       (مُطبَّق مسبقاً — تخطي)")
            skipped_count += 1
            continue

        matches = list(fix.pattern.finditer(text))
        n = len(matches)

        if n == 0:
            print(f"  [{i}] ❌ {fix.name}")
            print(f"       (لم يُعثر على النمط — لم يُطبَّق)")
            return 2
        elif n != fix.expected_count:
            print(f"  [{i}] ⚠️  {fix.name}")
            print(f"       (متوقع {fix.expected_count} مطابقة، وُجد {n})")
            print(f"       → أرفض المتابعة لتفادي التعديل الخاطئ")
            return 3

        print(f"  [{i}] ✅ {fix.name}  (مطابقة واحدة)")

        # preview
        for m in matches:
            old_snip = m.group(0)
            if callable(fix.replacer):
                new_snip = fix.replacer(m)
            else:
                new_snip = fix.replacer
            preview_blocks.append((i, old_snip, new_snip))

        text = fix.pattern.sub(fix.replacer, text, count=fix.expected_count)
        applied_count += 1

    # ── حالة خاصة: كل الإصلاحات مُطبَّقة مسبقاً ──
    if applied_count == 0:
        print()
        print("✅ كل الإصلاحات مُطبَّقة مسبقاً. لا حاجة لتعديل.")
        return 0

    # ── التحقق من الصياغة على النص الجديد ──
    try:
        ast.parse(text)
    except SyntaxError as e:
        print()
        print(f"❌ خطأ صياغة بعد التعديل: {e}")
        print(f"   السطر {e.lineno}: {e.text}")
        return 4

    print()
    print(f"✅ الصياغة صحيحة (ast.parse نجح)")
    print(f"📊 التعديلات: {applied_count} مُطبَّقة، {skipped_count} متخطّاة")

    # ── معاينة الفروق ──
    print()
    print("═" * 70)
    print("  الفروق المتوقعة")
    print("═" * 70)

    for idx, old, new in preview_blocks:
        print()
        print(f"  ── Fix #{idx} ──")
        print(f"  - OLD:")
        for line in old.splitlines():
            print(f"      {line}")
        print(f"  + NEW:")
        for line in new.splitlines():
            print(f"      {line}")

    # ── Dry run: توقف ──
    if dry_run:
        print()
        print("═" * 70)
        print("  ℹ️  Dry run — لم يُكتب أي شيء")
        print("═" * 70)
        return 0

    # ── backup ──
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_{ts}')
    shutil.copy2(p, backup)
    print()
    print(f"💾 Backup: {backup}")

    # ── اكتب ──
    p.write_text(text, encoding='utf-8')
    print(f"✏️  كُتب: {path}")
    print()
    print("═" * 70)
    print("  ✅ تم التطبيق بنجاح")
    print("═" * 70)
    print(f"  للتراجع: cp {backup.name} {path.name}")
    print()
    return 0


# ═══════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    print("═" * 70)
    print("  apply_live_fixes.py")
    print("  إصلاحات ما قبل Testnet")
    print("═" * 70)
    print()

    rc = process_file(args.file, dry_run=args.dry_run)
    sys.exit(rc)


if __name__ == '__main__':
    main()
