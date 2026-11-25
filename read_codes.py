#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code Inspector — يقرأ المواضع التي سيتم تعديلها في trading_2_live4_claude2_v4.py
يطبع رقم السطر + السياق (قبل/بعد) لكل anchor
"""

import re
import sys
from pathlib import Path

TARGET = "trading_published_pro_1h_test.py"
CONTEXT_BEFORE = 6
CONTEXT_AFTER = 6

# كل anchor: (id, regex, description)
ANCHORS = [
    # ── Config fields ──
    ("A1-N-config",      r"^\s+N:\s*int\s*=\s*\d+",
     "N في Config (يجب أن يكون 24)"),

    ("A2-TP_MULT",       r"^\s+TP_MULT:\s*float\s*=\s*[\d.]+",
     "TP_MULT في Config (يجب أن يصبح 3.0)"),

    # ── P_activation (البحث عن كل ظهور) ──
    ("A3-P_activation",  r"P_activation",
     "كل ظهور لـ P_activation (للتحقق إن كان محذوفاً أم لا)"),

    ("A4-force_mag",     r"force_mag",
     "force_mag — السطر الذي يسبق P_activation"),

    ("A5-geo_accel",     r"geo_accel\s*=\s*float\(ad\.geodesic_accel",
     "geo_accel — بداية كتلة P_activation"),

    # ── z_dev (البحث عن كل ظهور) ──
    ("A6-z_win",         r"_z_win\s*=",
     "_z_win — نافذة z_dev (تستخدم CFG.N)"),

    ("A7-z_dev_calc",    r"_z_dev\s*=\s*\(p\s*-\s*_z_mu\)",
     "_z_dev — الحساب"),

    ("A8-z_dev_thr",     r"abs\(_z_dev\)\s*<\s*[\d.]+",
     "abs(_z_dev) — البوابة (يجب أن تصبح 1.5)"),

    # ── Stage 2 TP rebuild ──
    ("A9-stage2_tp_buy",  r"tp_new\s*=\s*S_new\s*\+\s*\(sl_dist_new\s*\*\s*[\d.]+\)",
     "Stage 2 TP BUY (رقم 2.0 صلب)"),

    ("A10-stage2_tp_sell", r"tp_new\s*=\s*S_new\s*-\s*\(sl_dist_new\s*\*\s*[\d.]+\)",
     "Stage 2 TP SELL (رقم 2.0 صلب)"),

    # ── sl_dist في build_signals (لعرض مكان إضافة فلتر sl_sigma) ──
    ("A11-sl_dist_build", r"sl_dist\s*=\s*compute_geodesic_stop",
     "sl_dist = compute_geodesic_stop — مكان إضافة فلتر sl_sigma"),

    # ── sl_sigma موجود (للتأكد لا يوجد تعارض) ──
    ("A12-sl_sigma",     r"sl_sigma",
     "أي ظهور لـ sl_sigma (قد يكون في compute_geodesic_stop)"),
]


def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


def find_matches(lines, pattern):
    rx = re.compile(pattern)
    hits = []
    for i, line in enumerate(lines):
        if rx.search(line):
            hits.append((i, line))
    return hits


def print_context(lines, idx, before=CONTEXT_BEFORE, after=CONTEXT_AFTER):
    start = max(0, idx - before)
    end = min(len(lines), idx + after + 1)
    for i in range(start, end):
        marker = ">>>" if i == idx else "   "
        num = i + 1
        print(f"  {marker} {num:>6}: {lines[i].rstrip()}")


def main():
    p = Path(TARGET)
    if not p.exists():
        print(f"ERROR: {TARGET} not found in {Path.cwd()}")
        return 1

    lines = load_lines(p)
    print(f"\n{'=' * 78}")
    print(f"  FILE : {TARGET}")
    print(f"  LINES: {len(lines):,}")
    print(f"  CWD  : {Path.cwd()}")
    print(f"{'=' * 78}")

    total_found = 0
    total_missing = 0
    missing_ids = []

    for anchor_id, pattern, desc in ANCHORS:
        print(f"\n{'─' * 78}")
        print(f"  ANCHOR: {anchor_id}")
        print(f"  DESC  : {desc}")
        print(f"  PATTERN: {pattern}")
        print(f"{'─' * 78}")

        hits = find_matches(lines, pattern)

        if not hits:
            print(f"  ❌ NO MATCH FOUND")
            print(f"     (قد يكون السطر معدلاً أو محذوفاً)")
            total_missing += 1
            missing_ids.append(anchor_id)
            continue

        total_found += 1
        print(f"  ✓ Found {len(hits)} match(es)")

        if len(hits) > 5:
            # أول 3
            for idx, line in hits[:3]:
                print(f"\n  ── match at line {idx + 1} ──")
                print_context(lines, idx)
            print(f"\n  ... ({len(hits) - 5} more matches skipped) ...")
            # آخر 2
            for idx, line in hits[-2:]:
                print(f"\n  ── match at line {idx + 1} ──")
                print_context(lines, idx)
        else:
            for idx, line in hits:
                print(f"\n  ── match at line {idx + 1} ──")
                print_context(lines, idx)

    # ── ملخص ──
    print(f"\n{'=' * 78}")
    print(f"  SUMMARY")
    print(f"{'=' * 78}")
    print(f"  Anchors found  : {total_found}/{len(ANCHORS)}")
    print(f"  Anchors missing: {total_missing}/{len(ANCHORS)}")
    if missing_ids:
        print(f"  Missing        : {', '.join(missing_ids)}")
    print(f"{'=' * 78}\n")
    print("  📋 انسخ هذا المخرج كاملاً وأرسله.")
    print("     بعد قراءته سأعطيك patch script دقيقاً يطابق الحالة الحالية.\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted.\n")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n  FATAL: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
