#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diag_anchor.py
==============
يُظهر الـ anchor الفعلي في ملف trading_2_complete4.py للتحقق من
سبب فشل Edit 3.

الاستخدام:
    python diag_anchor.py --input trading_2_complete4.py
"""

import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="trading_2_complete4.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()

    print(f"📖 File: {args.input}")
    print(f"   Size: {len(src):,} chars")
    print(f"   Encoding check passed\n")

    # ═══════════════════════════════════════════════════════════
    # 1) ابحث عن موضع `top_syms = scan_top_assets(exchange)`
    # ═══════════════════════════════════════════════════════════
    marker = "top_syms = scan_top_assets(exchange)"
    idx = src.find(marker)

    if idx < 0:
        print(f"❌ marker '{marker}' NOT found")
        sys.exit(1)

    print(f"═══ SECTION 1: Around '{marker}' ═══")
    print(f"Marker found at offset {idx}\n")

    # اطبع 400 حرف قبل و 200 بعد
    start = max(0, idx - 400)
    end = min(len(src), idx + 200)
    snippet = src[start:end]

    print("── Plain text (may look weird due to RTL) ──")
    print(snippet)
    print()
    print("── Python repr (exact chars) ──")
    print(repr(snippet))
    print()

    # ═══════════════════════════════════════════════════════════
    # 2) اختبر بعض الأنماط المحتملة
    # ═══════════════════════════════════════════════════════════
    print("═══ SECTION 2: Anchor pattern tests ═══\n")

    # النمط الأصلي المستخدم في السكربت
    pattern_A = (
        '    log.info("⏳ جلب الزمكان المالي التاريخي '
        '(هذه العملية تحدث مرة واحدة فقط...)")\n'
        '    top_syms = scan_top_assets(exchange)'
    )
    print(f"Pattern A (original from script):")
    print(f"   {'✅ MATCH' if pattern_A in src else '❌ NO MATCH'}")
    if pattern_A not in src:
        # ابحث عن أقرب بداية
        prefix = '    log.info("⏳'
        pidx = src.find(prefix)
        if pidx >= 0:
            print(f"   Found prefix '    log.info(\"⏳' at offset {pidx}")
            print(f"   First 100 chars after prefix:")
            print(f"   {repr(src[pidx:pidx+200])}")
    print()

    # نمط مبسّط: فقط سطر top_syms مع البادئة
    pattern_B = "    top_syms = scan_top_assets(exchange)"
    print(f"Pattern B (just top_syms line):")
    print(f"   {'✅ MATCH' if pattern_B in src else '❌ NO MATCH'}")
    print()

    # نمط ASCII فقط (بدون عربي)
    pattern_C = "    top_syms = scan_top_assets(exchange)\n"
    print(f"Pattern C (with newline):")
    print(f"   {'✅ MATCH' if pattern_C in src else '❌ NO MATCH'}")
    print()

    # ═══════════════════════════════════════════════════════════
    # 3) اعرض كل bytes السطر الذي يحتوي على top_syms
    # ═══════════════════════════════════════════════════════════
    print("═══ SECTION 3: Line-by-line byte analysis ═══\n")

    lines = src.split("\n")
    for i, line in enumerate(lines):
        if "top_syms = scan_top_assets" in line:
            print(f"Line {i+1}:")
            print(f"  repr  : {line!r}")
            print(f"  bytes : {list(line.encode('utf-8')[:60])}...")
            print(f"  len   : {len(line)} chars")
            print()

            # السطر السابق
            if i > 0:
                prev = lines[i-1]
                print(f"Line {i} (previous):")
                print(f"  repr  : {prev!r}")
                print(f"  len   : {len(prev)} chars")
                # حلل كل حرف
                print(f"  char-by-char (last 80 chars):")
                for j, ch in enumerate(prev[-80:]):
                    cp = ord(ch)
                    name = ""
                    if cp < 32:
                        name = f" (control)"
                    elif cp < 128:
                        name = f" '{ch}'"
                    else:
                        try:
                            name = f" U+{cp:04X}"
                        except Exception:
                            name = "?"
                    print(f"    [{len(prev)-80+j:>4}] U+{cp:04X}{name}")
            break

    # ═══════════════════════════════════════════════════════════
    # 4) اقتراح النمط الصحيح
    # ═══════════════════════════════════════════════════════════
    print("\n═══ SECTION 4: Suggested safe anchor ═══\n")

    # نبني نمطاً يعتمد فقط على السطر التالي (top_syms + سطر بعده)
    if pattern_B in src:
        # اطبع النص الأصلي لآخر 3 أسطر قبل top_syms للاستنساخ
        line_idx = None
        for i, line in enumerate(lines):
            if "top_syms = scan_top_assets" in line:
                line_idx = i
                break

        if line_idx is not None:
            print("Suggested anchor (exact lines to copy):")
            print("```python")
            for k in range(max(0, line_idx - 2), min(len(lines), line_idx + 3)):
                print(f"# line {k+1}: {lines[k]!r}")
            print("```")
            print()
            print("Suggested pattern to use (multi-line, avoid Arabic):")
            print("```python")
            print("anchor = (")
            print("    '    top_syms = scan_top_assets(exchange)\\n'")
            print("    '\\n'")
            print("    '    # ══ [DATA-LENGTH-FIX]'")
            print(")")
            print("```")
            # تحقق
            test = (
                '    top_syms = scan_top_assets(exchange)\n'
                '\n'
                '    # ══ [DATA-LENGTH-FIX]'
            )
            print()
            print(f"Verification: {'✅ MATCH' if test in src else '❌ NO MATCH'}")


if __name__ == "__main__":
    main()
