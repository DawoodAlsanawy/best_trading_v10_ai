#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_live_p_var.py — يُصلح 'name p is not defined' في run_live.

المشكلة: بعد إصلاح Fix A السابق، السطر:
    pos['action'], pos['entry'], p, ad, fi
يستخدم `p` وهو غير مُعرَّف في سياق live (المتغير الصحيح: `price`).

الإصلاح: `p` → `price` في هذا السطر فقط.
"""

import argparse
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path


# السطر بعد Fix A السابق
OLD_LINE = "pos['action'], pos['entry'], p, ad, fi"
NEW_LINE = "pos['action'], pos['entry'], price, ad, fi"


def find_matching_lines(lines, target):
    """يُعيد قائمة المواضع (index, indent) التي محتواها = target."""
    hits = []
    for i, line in enumerate(lines):
        if line.strip() == target:
            indent = len(line) - len(line.lstrip(' '))
            hits.append((i, indent))
    return hits


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

    # Idempotency
    if NEW_LINE in original and OLD_LINE not in original:
        print("✅ مُطبَّق مسبقاً")
        return 0

    lines = original.split('\n')

    # ── إيجاد السطر ──
    hits = find_matching_lines(lines, OLD_LINE)
    if not hits:
        print(f"❌ لم أجد السطر:")
        print(f"   {OLD_LINE}")
        print()
        print("  المواضع الحالية لـ `pos['action']`:")
        for i, line in enumerate(lines, 1):
            if "pos['action']" in line:
                print(f"    [{i:5d}] {line.strip()[:100]}")
        return 2

    print("═" * 70)
    print("  fix_live_p_var.py")
    print("═" * 70)
    print()
    print(f"  🔍 وُجد {len(hits)} موضع:")
    for idx, ind in hits:
        print(f"    السطر {idx + 1}  (indent={ind})")
        print(f"      {lines[idx]}")
        print()

    # ── التعديل ──
    for idx, ind in hits:
        lines[idx] = ' ' * ind + NEW_LINE

    new_text = '\n'.join(lines)

    # ── التحقق ──
    try:
        ast.parse(new_text)
        print("  ✅ الصياغة صحيحة (ast.parse)")
    except SyntaxError as e:
        print(f"  ❌ خطأ صياغة: {e.lineno}: {e.text}")
        return 3

    print()
    print("  ── بعد التعديل ──")
    for idx, ind in hits:
        print(f"    [{idx + 1}] {lines[idx]}")

    if args.dry_run:
        print()
        print("═" * 70)
        print("  ℹ️  Dry run — لم يُكتب أي شيء")
        print("═" * 70)
        return 0

    # ── Backup + Write ──
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_pvar_{ts}')
    shutil.copy2(p, backup)
    print()
    print(f"  💾 Backup: {backup}")

    p.write_text(new_text, encoding='utf-8')
    print(f"  ✏️  كُتب: {p}")
    print()
    print("═" * 70)
    print(f"  ✅ تم — {len(hits)} موضع أُصلح")
    print("═" * 70)
    print(f"  للتراجع: cp {backup.name} {p.name}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

