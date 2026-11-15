#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_bear_shield.py — تشخيص دقيق لـ preflight failure
═══════════════════════════════════════════════════════════════════════════

يكشف:
  1. كل سطر يحتوي "print_report" (المشكلة: ambiguous(2))
  2. حالة كل من الـ 18 anchor (OK / NOT FOUND / AMBIGUOUS)
  3. سطور مشابهة لأي anchor مفقود (لإعادة الكتابة)
  4. فرق الحجم عن الملف الأصلي (لفهم ما تم تعديله)

الاستخدام:
    python diagnose_bear_shield.py > diagnostic.txt 2>&1
    cat diagnostic.txt
"""

import os
import re
import sys

TARGET = "trading_final.py"
ORIGINAL_SIZE = 945_916   # size of the file in first message


# نفس الـ anchors بالضبط كما في apply_bear_shield.py
ANCHORS_TO_TEST = [
    ("bs_config",
     "    MAX_HOLD_BARS: int = 2000\n",
     "after"),

    ("bs_helpers",
     'def build_signals(assets, mode="backtest"):',
     "before"),

    ("bs_sig_init",
     "    sigs = []\n",
     "after"),

    ("bs_sig_filter",
     "            if abs(_z_dev) < 1.5:\n"
     "                continue\n"
     '            action = "BUY" if _z_dev < 0 else "SELL"\n',
     "replace"),

    ("bs_sig_score",
     "            if ad.score[fi] < _min_score: continue\n",
     "replace"),

    ("bs_sig_gauge",
     '                    if action == "BUY" and _gf < _gauge_thr_buy:\n'
     '                        continue\n',
     "replace"),

    ("bs_sim_init",
     "    capital  = CFG.INITIAL_CAPITAL\n"
     "    peak_cap = capital\n",
     "after"),

    ("bs_sim_bias",
     "        # حاجز أمان مطلق: يستحيل بدء تداول جديد إذا اقترب الجسيم من عتبة الفناء (5.1$)\n"
     "        if capital <= CFG.CAPITAL_FLOOR + 0.1:\n"
     "            break\n",
     "after"),

    ("bs_sim_risk",
     "        if len(open_pos) >= CFG.MAX_CONCURRENT_ASSETS: continue\n",
     "replace"),

    ("bs_sim_riskmult",
     "        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)\n"
     "        if risk_frac <= 0.0:\n",
     "before"),

    ("bs_sim_apply",
     "        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)\n"
     "        if risk_frac <= 0.0:\n"
     '            log.debug(f"[Budget] {sym} skipped: no heat budget available")\n'
     "            continue\n",
     "replace"),

    ("bs_live_bias",
     "            _LV_ASSETS.clear()\n"
     "            _LV_ASSETS.update(assets)\n",
     "after"),

    ("bs_live_concurrency",
     "                            else:\n"
     "                                _total_exposure = (len(_PENDING_ORDERS)\n"
     "                                                   + len(open_pos_live)\n"
     "                                                   + len(_WATCHED_SIGNALS))\n"
     "                                _exp_cap = int(CFG.MAX_CONCURRENT_ASSETS)\n",
     "replace"),

    ("bs_live_risk",
     "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
     "                    if risk_frac <= 0.0:\n",
     "before"),

    ("bs_live_apply",
     "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
     "                    if risk_frac <= 0.0:\n"
     '                        log.debug(f"[Budget] {sym} skipped: no heat budget")\n'
     "                        continue\n",
     "replace"),

    ("bs_cli_flags",
     "    args = p.parse_args()\n",
     "before"),

    ("bs_cli_process",
     "    if args.no_numba: CFG.NUMBA_ENABLED = False\n",
     "after"),

    # ← هذا هو الـ anchor الذي فشل
    ("bs_report",
     '    print_report(m, "backtest")\n',
     "after"),
]


def _show_all_occurrences(content, anchor, max_show=10):
    """عرض كل المواضع التي يظهر فيها الـ anchor مع أرقام الأسطر."""
    lines = content.split("\n")
    anchor_lines = anchor.split("\n")
    first_line = anchor_lines[0]
    
    found = []
    for i, line in enumerate(lines, 1):
        if first_line in line or (first_line.strip() and first_line.strip() in line):
            # Check if the full anchor matches here
            start = i - 1
            if start + len(anchor_lines) <= len(lines):
                block = "\n".join(lines[start:start + len(anchor_lines)]) + "\n"
                if block == anchor:
                    found.append((i, "EXACT"))
                else:
                    found.append((i, "partial"))
    
    if not found:
        # Try line-by-line to find similar lines
        print(f"       (no exact match — searching similar lines)")
        key = first_line.strip()
        if len(key) >= 10:
            cnt = 0
            for i, line in enumerate(lines, 1):
                if key in line:
                    print(f"       line {i:5d}: {line!r}")
                    cnt += 1
                    if cnt >= max_show:
                        break
        return
    
    for line_no, kind in found[:max_show]:
        print(f"       line {line_no:5d} [{kind:7s}]: {lines[line_no-1]!r}")


def main():
    print("═" * 78)
    print(" BEAR-SHIELD — Diagnostic")
    print("═" * 78)
    print()

    if not os.path.exists(TARGET):
        print(f"✗ File not found: {TARGET}")
        return 1

    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    size = len(content)
    print(f"File:        {TARGET}")
    print(f"Size:        {size:,} chars")
    print(f"Original:    {ORIGINAL_SIZE:,} chars")
    print(f"Δ Size:      {size - ORIGINAL_SIZE:+,} chars")
    print(f"Line count:  {content.count(chr(10)):,}")
    print()

    # ── 1. كل سطور print_report ──
    print("─" * 78)
    print(" 1. All lines containing 'print_report':")
    print("─" * 78)
    lines = content.split("\n")
    count_pr = 0
    for i, line in enumerate(lines, 1):
        if "print_report" in line:
            count_pr += 1
            print(f"   Line {i:5d}: {line!r}")
    print(f"   → {count_pr} occurrence(s)")
    print()

    # ── 2. سياق كل ظهور (الأسطر قبل وبعد) ──
    print("─" * 78)
    print(" 2. Context around each 'print_report' call:")
    print("─" * 78)
    for i, line in enumerate(lines, 1):
        if "print_report" in line:
            print(f"\n   ┌─ Around line {i} ─────────────────────")
            for j in range(max(0, i - 4), min(len(lines), i + 3)):
                marker = "→" if j == i - 1 else " "
                print(f"   {marker} {j+1:5d}: {lines[j]!r}")
            print(f"   └──────────────────────────────────────")
    print()

    # ── 3. اختبار كل anchor ──
    print("─" * 78)
    print(" 3. Anchor test results (all 18):")
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
            missing.append((pid, anchor, pos))
        else:
            status = f"⚠ AMBIGUOUS ({cnt}x)"
            ambiguous.append((pid, anchor, cnt))

        print(f"   [{status:20s}] {pid}")

        if cnt != 1:
            print(f"     First line: {anchor.split(chr(10))[0]!r}")
            print(f"     All occurrences in file:")
            _show_all_occurrences(content, anchor)
            print()
    print()

    # ── 4. تحقق من تعديلات محتملة (الفرق 278 chars) ──
    print("─" * 78)
    print(" 4. Possible manual edits (Δ = {} chars):".format(
        size - ORIGINAL_SIZE))
    print("─" * 78)
    print("   Looking for lines that differ from the original file...")
    print()
    # We don't have the original to compare, but we can look for signs:
    # - Lines that mention "SLP" or "Quality" or other patch artifacts
    # - Lines that are unusually long/short
    # - Comments marked with recent edits
    _markers = ["SLP", "Quality", "agreement", "AGREEMENT", "Ladder",
                "ROE", "PFCW", "BUYSELL", "MHT"]
    for marker in _markers:
        cnt = content.count(marker)
        if cnt > 0:
            print(f"   ⚠ '{marker}' found {cnt} times")
            # Show first few
            cnt_shown = 0
            for i, line in enumerate(lines, 1):
                if marker in line and cnt_shown < 3:
                    print(f"       line {i:5d}: {line.strip()[:100]!r}")
                    cnt_shown += 1
    print()

    # ── 5. ملخص ──
    print("═" * 78)
    print(" SUMMARY")
    print("═" * 78)
    total = len(ANCHORS_TO_TEST)
    print(f"   Total anchors:    {total}")
    print(f"   ✓ OK:             {ok_count}")
    print(f"   ✗ NOT FOUND:      {len(missing)}")
    print(f"   ⚠ AMBIGUOUS:      {len(ambiguous)}")
    print()

    if ambiguous:
        print("   Ambiguous anchors (cause of failure):")
        for pid, anchor, cnt in ambiguous:
            print(f"     - {pid} ({cnt} occurrences)")
            print(f"       Anchor: {anchor!r}")
        print()

    if missing:
        print("   Missing anchors:")
        for pid, _, _ in missing:
            print(f"     - {pid}")
        print()

    if ok_count == total:
        print("   ✓ All anchors present and unique — patch should work")
        return 0
    else:
        print("   ⚠ Fix needed — send this output for correction")
        return 2


if __name__ == "__main__":
    sys.exit(main())
