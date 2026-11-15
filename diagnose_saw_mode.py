#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_saw_mode.py — تشخيص دقيق لـ saw_direction_gate و saw_report
═══════════════════════════════════════════════════════════════════════════

يكشف:
  1. الحالة الحقيقية لكل من الـ 14 anchor
  2. سياق كامل حول [ABLATION-2c] و z_dev gate (لـ saw_direction_gate)
  3. كل ظهور لـ print_report مع محيطها (لـ saw_report)
  4. علامات تعديلات سابقة (SLP, Quality, Agreement, Bear Shield, إلخ)
  5. قياس دقيق للفرق بين الملف الحالي والأصلي

الاستخدام:
    python diagnose_saw_mode.py > diagnostic.txt 2>&1
    cat diagnostic.txt
"""

import os
import sys

TARGET = "trading_final.py"
ORIGINAL_SIZE = 945_916


# نفس الـ 14 anchors من apply_saw_mode.py
ANCHORS = [
    ("saw_config",
     "    MAX_HOLD_BARS: int = 2000\n",
     "after"),
    ("saw_signal_field",
     "    mfal_p_act: float = 0.0\n",
     "after"),
    ("saw_helper",
     'def build_signals(assets, mode="backtest"):',
     "before"),
    ("saw_init_trend",
     "            geo_accel = float(ad.geodesic_accel[fi])\n",
     "before"),
    ("saw_direction_gate",
     "            # [ABLATION-2c] softer deviation gate\n"
     "            if abs(_z_dev) < 1.5:\n"
     "                continue\n"
     '            action = "BUY" if _z_dev < 0 else "SELL"\n',
     "replace"),
    ("saw_sell_bypass",
     '            if action == "SELL":\n'
     "                if not getattr(CFG, 'SELL_ENABLED', False):\n"
     "                    continue\n"
     "                if ad.score[fi] < float(getattr(CFG, 'SELL_MIN_SCORE', 3)):\n"
     "                    continue\n"
     "                if abs(_z_dev) < float(getattr(CFG, 'SELL_MIN_ZDEV', 1.5)):\n"
     "                    continue\n",
     "replace"),
    ("saw_gauge_bypass",
     "            # ══ [GAUGE-FILTER] ══\n"
     "            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):\n",
     "replace"),
    ("saw_tp_adjust",
     "            _tp_mult = float(getattr(CFG, 'TP_MULT', 1.5))\n"
     '            tp1 = tunnel_entry_p + (sl_dist * _tp_mult) if action == "BUY" else tunnel_entry_p - (sl_dist * _tp_mult)\n',
     "replace"),
    ("saw_signal_create",
     "                mfal_x=_mfal_x,\n"
     "                mfal_p_act=float(P_activation),\n"
     "            )\n",
     "replace"),
    ("saw_risk_backtest",
     "        # Apply drawdown multiplier + floor protection\n"
     "        risk_frac *= dd_mult * power_law_scale\n"
     "        risk_frac = float(np.clip(risk_frac,\n",
     "replace"),
    ("saw_risk_live",
     "                    risk_frac *= power_law_scale * (\n"
     "                        dd_mult if getattr(CFG, 'LIVE_APPLY_DD_MULT', True) else 1.0)\n"
     "                    risk_frac = float(np.clip(risk_frac,\n",
     "replace"),
    ("saw_cli_flags",
     "    args = p.parse_args()\n",
     "before"),
    ("saw_cli_process",
     "    if args.no_numba: CFG.NUMBA_ENABLED = False\n",
     "after"),
    ("saw_report",
     '    print_report(m, "backtest")\n'
     "    \n"
     "    # ══ [Analytics] finalize backtest ══\n",
     "replace"),
]


def _context_around(content, anchor, max_before=5, max_after=5):
    """طباعة السياق حول كل ظهور (جزئي أو كامل) للـ anchor."""
    lines = content.split("\n")
    first_line = anchor.split("\n")[0]
    key = first_line.strip()

    if len(key) < 5:
        print("       (first line too short — cannot search)")
        return

    matches = []
    for i, line in enumerate(lines):
        if key in line:
            matches.append(i)

    if not matches:
        print(f"       (no line contains {key!r})")
        return

    for idx in matches[:5]:
        print(f"       ┌─ Around line {idx+1} ─────────────")
        for j in range(max(0, idx - max_before),
                        min(len(lines), idx + max_after + 1)):
            marker = "→" if j == idx else " "
            print(f"       {marker} {j+1:5d}: {lines[j]!r}")
        print(f"       └─────────────────────────")

        # Try full anchor match here
        anchor_lines = anchor.split("\n")
        start = idx
        end = start + len(anchor_lines)
        if end <= len(lines):
            block = "\n".join(lines[start:end]) + "\n"
            if block == anchor:
                print(f"       ✓ FULL MATCH at this position")
            else:
                # Show diff
                print(f"       ✗ partial match — expected block:")
                for k, exp in enumerate(anchor_lines[:3]):
                    actual = lines[start + k] if start + k < len(lines) else ""
                    same = "=" if actual == exp else "≠"
                    print(f"         {same} exp: {exp!r}")
                    if actual != exp:
                        print(f"           got: {actual!r}")


def main():
    print("═" * 78)
    print(" SAW-MODE — Diagnostic")
    print("═" * 78)
    print()

    if not os.path.exists(TARGET):
        print(f"✗ File not found: {TARGET}")
        return 1

    with open(TARGET, "r", encoding="utf-8") as f:
        content = f.read()

    size = len(content)
    delta = size - ORIGINAL_SIZE
    print(f"File:        {TARGET}")
    print(f"Size:        {size:,} chars")
    print(f"Original:    {ORIGINAL_SIZE:,} chars")
    print(f"Δ Size:      {delta:+,} chars")
    print(f"Line count:  {content.count(chr(10)):,}")
    print()

    # ── 1. حالة كل الـ anchors ──
    print("─" * 78)
    print(" 1. Anchor test results (all 14):")
    print("─" * 78)
    ok_count = 0
    missing = []
    ambiguous = []
    for pid, anchor, pos in ANCHORS:
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
            print()
            print(f"       Position: {pos}")
            print(f"       Full anchor (first 200 chars):")
            print(f"       {anchor[:200]!r}")
            print()
            print(f"       Context search in file:")
            _context_around(content, anchor)
            print()
    print()

    # ── 2. تحديداً: saw_direction_gate ──
    print("─" * 78)
    print(" 2. Deep dive — saw_direction_gate (z_dev gate):")
    print("─" * 78)
    print("   Searching for related patterns:")
    print()

    # البحث عن أي سطر يحتوي z_dev أو ABLATION
    lines = content.split("\n")
    print("   Lines containing 'z_dev' near '1.5' or 'ABLATION':")
    shown = 0
    for i, line in enumerate(lines, 1):
        if ("_z_dev" in line or "ABLATION" in line) and (
                "1.5" in line or "ABLATION" in line or "z_dev" in line):
            if shown < 30:  # limit
                # Only show lines with z_dev threshold OR ABLATION
                if "1.5" in line or "ABLATION" in line or "abs(_z_dev)" in line:
                    print(f"     line {i:5d}: {line!r}")
                    shown += 1
    print()

    # ── 3. تحديداً: saw_report ──
    print("─" * 78)
    print(" 3. Deep dive — saw_report (print_report context):")
    print("─" * 78)
    print("   All lines containing 'print_report':")
    for i, line in enumerate(lines, 1):
        if "print_report" in line:
            print(f"     line {i:5d}: {line!r}")
    print()

    print("   Context around each (10 lines before/after):")
    for i, line in enumerate(lines, 1):
        if "print_report(m," in line and i > 1:
            print(f"\n   ╔═══ Around line {i} ═══")
            for j in range(max(0, i - 6), min(len(lines), i + 6)):
                marker = "→" if j == i - 1 else " "
                print(f"   {marker} {j+1:5d}: {lines[j]!r}")
            print(f"   ╚══════════════════════")
    print()

    # ── 4. علامات تعديلات سابقة ──
    print("─" * 78)
    print(" 4. Previous edits markers:")
    print("─" * 78)
    markers = [
        ("SLP", "Smart Ladder Pending"),
        ("QUALITY_V2", "Quality-V2"),
        ("AGREEMENT_REQUIRED", "Direction Agreement"),
        ("BEAR_SHIELD", "Bear Shield"),
        ("SAW_MODE_ENABLED", "Saw Mode (already applied?)"),
        ("PFCW", "PFCW"),
        ("MAXHOLD_TRANSITION", "MaxHold Transition"),
        ("BUYSELL-PARITY", "BUY/SELL Parity"),
        ("_slp_", "SLP helpers"),
        ("_asset_bias_at_index", "Bear Shield helper"),
        ("_compute_trend_strength", "Saw Mode helper"),
    ]
    for marker, label in markers:
        cnt = content.count(marker)
        if cnt > 0:
            print(f"   ⚠ '{marker}' ({label}): {cnt} occurrences")
            shown = 0
            for i, line in enumerate(lines, 1):
                if marker in line and shown < 3:
                    print(f"       line {i:5d}: {line.strip()[:110]!r}")
                    shown += 1
    print()

    # ── 5. تحليل التغييرات ──
    print("─" * 78)
    print(f" 5. Analysis of Δ = {delta:+,} chars:")
    print("─" * 78)
    if delta > 5000:
        print("   ⚠ Δ كبير جداً — ربما تم تطبيق patch سابق بالكامل")
        print("   تحقق من قائمة markers أعلاه لتحديد ما تم تطبيقه")
    elif delta > 500:
        print("   ⚠ Δ متوسط — ربما تعديلات يدوية + patch جزئي")
    elif delta > 0:
        print("   ⚠ Δ صغير — ربما تعليقات إضافية أو تعديل طفيف")
    elif delta == 0:
        print("   ✓ الملف لم يتغير من الأصل")
    else:
        print(f"   ⚠ الملف أصغر من الأصل (ربما حُذفت أجزاء)")
    print()

    # ── 6. الملخص ──
    print("═" * 78)
    print(" SUMMARY")
    print("═" * 78)
    print(f"   Total anchors:    {len(ANCHORS)}")
    print(f"   ✓ OK:             {ok_count}")
    print(f"   ✗ NOT FOUND:      {len(missing)}")
    print(f"   ⚠ AMBIGUOUS:      {len(ambiguous)}")
    print()

    if missing:
        print("   Missing anchors (must be corrected):")
        for pid, _, _ in missing:
            print(f"     - {pid}")
        print()

    if ambiguous:
        print("   Ambiguous anchors:")
        for pid, _, cnt in ambiguous:
            print(f"     - {pid} ({cnt}x)")
        print()

    if ok_count == len(ANCHORS):
        print("   ✓ All anchors found — patch should work")
        return 0
    else:
        print("   ⚠ Send this output for correction")
        return 2


if __name__ == "__main__":
    sys.exit(main())
