#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_live_apex_bug.py — يُصلح 'dict' object has no attribute 'entry_px'

المشكلة: في run_live، استدعاء check_thermodynamic_apex يستخدم
         pos.entry_px (dot access) على dict.
الإصلاح: pos['entry'] و pos['action'].
"""

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# نمط متعدد الأسطر — يقبل whitespace variations
BUG_PAT = re.compile(
    r"is_apex, apex_rsn = check_thermodynamic_apex\(\s*\n"
    r"(?P<ind>[ \t]+)(?P<act>sig\.action|pos\.action|pos\[['\"]action['\"]\])\s*,\s*"
    r"pos\.entry_px\s*,\s*"
    r"p\s*,\s*ad\s*,\s*fi\s*\n"
    r"(?P=ind)\)",
)


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
    print("  fix_live_apex_bug.py")
    print("═" * 70)
    print()

    # ── البحث ──
    matches = list(BUG_PAT.finditer(text))
    print(f"  🔍 مطابقات النمط المتعدد الأسطر: {len(matches)}")

    if not matches:
        # جرّب البحث البسيط
        n_simple = text.count("pos.entry_px")
        print(f"  🔍 'pos.entry_px' في كل الملف: {n_simple} موضع")
        print()
        print("  جميع المواضع:")
        for i, line in enumerate(text.splitlines(), 1):
            if 'pos.entry_px' in line:
                indent = len(line) - len(line.lstrip())
                mark = " ← bug?" if indent >= 12 else ""
                print(f"    [{i:5d}] {line.strip()[:90]}{mark}")
        return 0

    # ── المعاينة ──
    print()
    print("  المواضع التي ستُعدَّل:")
    for i, m in enumerate(matches, 1):
        print(f"\n  ── Fix #{i} ──")
        for line in m.group(0).splitlines():
            print(f"    | {line}")

    # ── الاستبدال ──
    def repl(m):
        ind = m.group('ind')
        return (
            f"is_apex, apex_rsn = check_thermodynamic_apex(\n"
            f"{ind}pos['action'], pos['entry'], p, ad, fi\n"
            f"{ind})"
        )

    new_text = BUG_PAT.sub(repl, text, count=len(matches))

    # ── التحقق ──
    try:
        ast.parse(new_text)
        print()
        print(f"  ✅ الصياغة صحيحة (ast.parse)")
    except SyntaxError as e:
        print(f"\n  ❌ خطأ صياغة: {e.lineno}: {e.text}")
        return 3

    if args.dry_run:
        print()
        print("═" * 70)
        print("  ℹ️  Dry run — لم يُكتب أي شيء")
        print("═" * 70)
        return 0

    # ── Backup + Write ──
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_apex_{ts}')
    shutil.copy2(p, backup)
    print()
    print(f"  💾 Backup: {backup}")

    p.write_text(new_text, encoding='utf-8')
    print(f"  ✏️  كُتب: {p}")
    print()
    print("═" * 70)
    print(f"  ✅ تم — {len(matches)} موضع أُصلح")
    print("═" * 70)
    print(f"  للتراجع: cp {backup.name} {p.name}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
