#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_maxhold_anchors.py — تشخيص دقيق لجميع anchors
═══════════════════════════════════════════════════════════════════════════

يكشف:
  1. كل سطر يحتوي MAX_HOLD_BARS (القيمة الحقيقية + المسافات الدقيقة)
  2. حالة كل من الـ 8 anchors (OK / NOT FOUND / AMBIGUOUS)
  3. سطور مشابهة للـ anchors المفقودة (لفهم سبب عدم التطابق)
  4. Regex fallback للسطر الأول

الاستخدام:
    python diagnose_maxhold_anchors.py > diagnostic.txt 2>&1
    cat diagnostic.txt
"""

import os
import re
import sys

TARGET = "trading_final.py"


ANCHORS_TO_TEST = [
    ("mht_config",
     "    MAX_HOLD_BARS: int = 2000\n",
     "after"),

    ("mht_backtest_block",
     '        # 3. MaxHold (close-based)\n'
     '        # ══ [TF-FIX] scale bar-count to preserve real-time duration ══\n'
     '        if cidx - pos.entry_ci > effective_bars(CFG.MAX_HOLD_BARS):\n'
     '            pos.trail_sl = trail_sl; pos.current_ci = cidx\n'
     '            return p, "MaxHold", cidx\n',
     "replace"),

    ("mht_backtest_subbar_gate",
     '                _ta_eff = _sl_frac_init * _act_at_r\n'
     '                if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:\n',
     "replace"),

    ("mht_backtest_mainbar_gate",
     '            _ta_eff = _sl_frac_init * _act_at_r\n'
     '            if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:\n',
     "replace"),

    ("mht_live_block",
     '                        if bars_held > effective_bars(cfg.MAX_HOLD_BARS):\n'
     '                            ex = True\n'
     '                            rsn = f"MaxHold({int(bars_held)}bars)"\n',
     "replace"),

    ("mht_live_trail_gate",
     '                        _act_at_r = float(getattr(\n'
     "                            CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))\n"
     '                        _ta = _sl_frac_init * _act_at_r\n',
     "replace"),

    ("mht_cli_flag",
     '    p.add_argument("--max-hold",    type=int,   default=None)\n',
     "after"),

    ("mht_cli_process",
     '    if args.max_hold  is not None: CFG.MAX_HOLD_BARS = args.max_hold\n',
     "after"),
]


def _show_similar_lines(content, anchor, max_show=5):
    """عرض سطور مشابهة للـ anchor المفقود."""
    first_line = anchor.split("\n")[0].strip()
    if len(first_line) < 10:
        return
    key = first_line[:30]
    lines = content.split("\n")
    found = 0
    for i, line in enumerate(lines, 1):
        if key and key in line:
            print(f"       line {i:5d} (len={len(line):3d}): {line!r}")
            found += 1
            if found >= max_show:
                break
    if found == 0:
        # Try searching by main keyword
        keywords = [w for w in first_line.split() if len(w) > 5][:1]
        if keywords:
            kw = keywords[0]
            print(f"       (no exact match — searching keyword {kw!r})")
            for i, line in enumerate(lines, 1):
                if kw in line:
                    print(f"       line {i:5d}: {line!r}")
                    found += 1
                    if found >= max_show:
                        break


def main():
    print("═" * 78)
    print(" MAXHOLD Transition — Anchor Diagnostic")
    print("═" * 78)
    print()

    if not os.path.exists(TARGET):
        print(f"✗ File not found: {TARGET}")
        return 1

    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    print(f"File:      {TARGET}")
    print(f"Size:      {len(content):,} chars")
    print(f"Line count: {content.count(chr(10)):,}")
    print()

    # ── 1. MAX_HOLD_BARS lines ──
    print("─" * 78)
    print(" 1. All lines containing 'MAX_HOLD_BARS':")
    print("─" * 78)
    lines = content.split("\n")
    count_mhb = 0
    for i, line in enumerate(lines, 1):
        if "MAX_HOLD_BARS" in line:
            count_mhb += 1
            print(f"   Line {i:5d}: {line!r}")
    if count_mhb == 0:
        print("   ✗ MAX_HOLD_BARS NOT FOUND anywhere in file!")
    else:
        print(f"   → {count_mhb} occurrence(s)")
    print()

    # ── 2. Regex fallback for Config line ──
    print("─" * 78)
    print(" 2. Regex search for Config line:")
    print("─" * 78)
    m = re.search(
        r"^(\s*)MAX_HOLD_BARS\s*:\s*int\s*=\s*(\S+)",
        content, re.MULTILINE)
    if m:
        indent = m.group(1)
        value = m.group(2)
        print(f"   ✓ Found")
        print(f"     Indent:  {len(indent)} chars "
              f"({'tabs' if chr(9) in indent else 'spaces'})")
        print(f"     Value:   {value!r}")
        print(f"     Full:    {m.group(0)!r}")
    else:
        print("   ✗ Not found via regex")
    print()

    # ── 3. Test each anchor ──
    print("─" * 78)
    print(" 3. Anchor test results:")
    print("─" * 78)
    ok_count = 0
    missing = []
    ambiguous = []
    for pid, anchor, pos in ANCHORS_TO_TEST:
        cnt = content.count(anchor)
        if cnt == 1:
            status = "✓ OK"
            ok_count += 1
        elif cnt == 0:
            status = "✗ NOT FOUND"
            missing.append((pid, anchor))
        else:
            status = f"⚠ AMBIGUOUS ({cnt}x)"
            ambiguous.append((pid, cnt))

        print(f"   [{status:20s}] {pid}")

        if cnt == 0:
            print(f"     First line being searched:")
            print(f"     {anchor.split(chr(10))[0]!r}")
            print(f"     Similar lines in file:")
            _show_similar_lines(content, anchor)
            print()
    print()

    # ── 4. Summary ──
    print("═" * 78)
    print(" SUMMARY")
    print("═" * 78)
    total = len(ANCHORS_TO_TEST)
    print(f"   Total anchors:    {total}")
    print(f"   ✓ OK:             {ok_count}")
    print(f"   ✗ NOT FOUND:      {len(missing)}")
    print(f"   ⚠ AMBIGUOUS:      {len(ambiguous)}")
    print()

    if missing:
        print("   Missing anchors:")
        for pid, _ in missing:
            print(f"     - {pid}")
    if ambiguous:
        print("   Ambiguous anchors:")
        for pid, cnt in ambiguous:
            print(f"     - {pid} ({cnt}x)")
    print()

    if ok_count == total:
        print("   ✓ All anchors present and unique — patch script should work")
        return 0
    else:
        print("   ⚠ Fix needed — send this output for correction")
        return 2


if __name__ == "__main__":
    sys.exit(main())
