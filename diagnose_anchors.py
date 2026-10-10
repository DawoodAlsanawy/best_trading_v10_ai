#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
يُخرج النص الفعلي حول المناطق التي فشلت فيها anchors.
أرسل المخرجات كاملة.

python diagnose_anchors.py --input trading_2_fixed_v2.py
"""

import argparse
import os
import sys


def show(src, start, end, label, max_chars=1500):
    print(f"\n{'='*72}")
    print(f"  {label}")
    print(f"  offsets: {start} .. {end}")
    print(f"{'='*72}")
    snippet = src[start:end]
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars] + "\n... [truncated]"
    # طباعة النص الخام + repr لرؤية whitespace
    print(snippet)
    print(f"\n  ───── repr (first 400 chars) ─────")
    print(repr(snippet[:400]))


def find_all(src, needle):
    """يعيد قائمة كل offsets حيث يظهر needle."""
    out = []
    start = 0
    while True:
        i = src.find(needle, start)
        if i < 0:
            break
        out.append(i)
        start = i + 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="trading_2_fixed_v2.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ {args.input} not found")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()

    print(f"📖 Loaded {len(src):,} bytes from {args.input}\n")

    # ═══════════════════════════════════════════════════════════
    # 1) ابحث عن place_pending_entry و اعرض الجزء الأخير منه
    # ═══════════════════════════════════════════════════════════
    print("\n" + "█"*72)
    print("█  SECTION 1: place_pending_entry — final GTX block")
    print("█"*72)

    ppe = src.find("def place_pending_entry(")
    if ppe < 0:
        print("❌ place_pending_entry NOT FOUND")
    else:
        # آخر 2000 حرف من الدالة (نهاية الدالة هي rec = {...} و log)
        # نبحث عن "rec = {" بعد ppe
        rec_pos = src.find("rec = {", ppe)
        if rec_pos < 0:
            print("❌ `rec = {` not found after place_pending_entry")
            # اطبع 3000 حرف من البداية
            show(src, ppe, ppe + 3000, "place_pending_entry head")
        else:
            # اطبع 1500 حرف قبل rec = { (هذا يحتوي على GTX block)
            show(src,
                 max(ppe, rec_pos - 1800),
                 rec_pos + 50,
                 "GTX block + rec start (in place_pending_entry)")

    # ═══════════════════════════════════════════════════════════
    # 2) ابحث عن كل تطابقات "GTX" داخل place_pending_entry
    # ═══════════════════════════════════════════════════════════
    print("\n" + "█"*72)
    print("█  SECTION 2: All 'GTX' occurrences in place_pending_entry")
    print("█"*72)

    if ppe >= 0:
        # نهاية الدالة = بداية الدالة التالية أو نهاية الملف
        next_def = src.find("\ndef ", ppe + 10)
        if next_def < 0:
            next_def = len(src)
        ppe_body = src[ppe:next_def]
        print(f"place_pending_entry body: {len(ppe_body)} chars")
        for m in find_all(ppe_body, "GTX"):
            print(f"  • GTX at relative offset {m} "
                  f"(abs {ppe + m})")
            print(f"      ... {ppe_body[max(0,m-80):m+120]!r}")

    # ═══════════════════════════════════════════════════════════
    # 3) ابحث عن exit block الذي يحتوي no fill
    # ═══════════════════════════════════════════════════════════
    print("\n" + "█"*72)
    print("█  SECTION 3: Exit no-fill block in run_live")
    print("█"*72)

    # ابحث عن "execute_post_only(" الذي يسبق exit
    # الـ anchor الأفضل: البحث عن "po_exit" أو "[Exit]"
    exit_marker = src.find("⬛ [Exit]")
    if exit_marker < 0:
        exit_marker = src.find("[Exit]")

    if exit_marker >= 0:
        print(f"  • '[Exit]' log found at offset {exit_marker}")
        # اطبع 2500 حرف قبل ذلك
        show(src,
             max(0, exit_marker - 2500),
             exit_marker + 100,
             "Exit block (before ⬛ [Exit] log)")
    else:
        print("  ❌ '[Exit]' not found")

    # ═══════════════════════════════════════════════════════════
    # 4) ابحث عن كل تطابقات "no fill" و "[Exit]"
    # ═══════════════════════════════════════════════════════════
    print("\n" + "█"*72)
    print("█  SECTION 4: All 'no fill' and '[Exit]' occurrences")
    print("█"*72)

    print("\n  'no fill' occurrences:")
    for i in find_all(src, "no fill"):
        print(f"    • offset {i}: ...{src[max(0,i-60):i+60]!r}")

    print("\n  '[Exit]' occurrences:")
    for i in find_all(src, "[Exit]"):
        print(f"    • offset {i}: ...{src[max(0,i-60):i+60]!r}")

    # ═══════════════════════════════════════════════════════════
    # 5) ابحث عن _exit_ok و _exit_retry
    # ═══════════════════════════════════════════════════════════
    print("\n" + "█"*72)
    print("█  SECTION 5: _exit_ok / _exit_retry context")
    print("█"*72)

    for needle in ("_exit_ok", "_exit_retry", "forcing MARKET after"):
        print(f"\n  '{needle}' occurrences:")
        for i in find_all(src, needle):
            print(f"    • offset {i}: "
                  f"...{src[max(0,i-80):i+120]!r}")

    # ═══════════════════════════════════════════════════════════
    # 6) اطبع حول rec.get('filled')
    # ═══════════════════════════════════════════════════════════
    print("\n" + "█"*72)
    print("█  SECTION 6: monitor_pending_orders timeout block")
    print("█"*72)

    mpo = src.find("def monitor_pending_orders(")
    if mpo < 0:
        print("❌ monitor_pending_orders NOT FOUND")
    else:
        # ابحث عن timeout داخل هذه الدالة
        timeout_pos = src.find("timeout_s = float(rec.get", mpo)
        if timeout_pos < 0:
            timeout_pos = src.find("elapsed > timeout_s", mpo)
        if timeout_pos > 0:
            show(src,
                 max(mpo, timeout_pos - 800),
                 timeout_pos + 1500,
                 "timeout block in monitor_pending_orders")
        else:
            print("⚠️  timeout block not found — showing first 2500 chars of function")
            show(src, mpo, mpo + 2500, "monitor_pending_orders head")

    print("\n" + "█"*72)
    print("█  END OF DIAGNOSTIC")
    print("█"*72)
    print("\n📋 أرسل المخرجات كاملة (من أول SECTION 1 حتى النهاية)")


if __name__ == "__main__":
    main()
