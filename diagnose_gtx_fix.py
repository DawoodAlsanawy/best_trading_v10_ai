#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic for FIX-25 — finds why "improved fallback" check failed.
"""

import os
import sys
import re


def main():
    fp = sys.argv[1] if len(sys.argv) > 1 else "trading_2_complete4.py"
    if not os.path.exists(fp):
        print(f"❌ File not found: {fp}")
        sys.exit(1)

    with open(fp, "r", encoding="utf-8") as f:
        src = f.read()

    print(f"📖 Loaded {fp} ({len(src):,} bytes)")
    print()

    # ═══ 1. Check the markers used in verify() ═══
    print("═" * 60)
    print("  MARKERS AS CHECKED BY verify()")
    print("═" * 60)

    markers = [
        ("pre-flight call",         "[FIX-25] Pre-flight: adjust to safe side"),
        ("improved fallback",       "[FIX-25] retry"),
        ("-5022 detection",         "'-5022' in _emsg"),
        ("stats logger call",       "_gtx_preflight_log_stats()"),
    ]
    for name, m in markers:
        present = m in src
        print(f"  {'✅' if present else '❌'} {name}")
        print(f"      marker: {m!r}")
    print()

    # ═══ 2. What actually appears in the file ═══
    print("═" * 60)
    print("  WHAT ACTUALLY EXISTS (all [FIX-25] lines)")
    print("═" * 60)
    for i, line in enumerate(src.split("\n"), 1):
        if "[FIX-25]" in line:
            stripped = line.strip()
            print(f"  L{i}: {stripped!r}")
    print()

    # ═══ 3. Context around the fallback code ═══
    print("═" * 60)
    print("  CONTEXT: GTX rejected after pre-flight")
    print("═" * 60)

    idx = src.find("GTX rejected after pre-flight")
    if idx < 0:
        print("  ❌ 'GTX rejected after pre-flight' NOT FOUND")
        # try alternative
        idx = src.find("GTX rejected after")
        if idx >= 0:
            print(f"  partial match at {idx}")
    if idx >= 0:
        start = max(0, idx - 100)
        end = min(len(src), idx + 1200)
        print(src[start:end])
    print()

    # ═══ 4. Look for the retry log specifically ═══
    print("═" * 60)
    print("  LOOKING FOR 'retry' LOG LINE")
    print("═" * 60)

    retry_pat = re.compile(r'.*retry.*')
    found = False
    for i, line in enumerate(src.split("\n"), 1):
        if "retry" in line and ("FIX-25" in line or "fallback" in line):
            print(f"  L{i}: {line.strip()!r}")
            found = True
    if not found:
        print("  ❌ No 'retry' log line with FIX-25 found")
    print()

    # ═══ 5. Check whether the GTX block was updated correctly ═══
    print("═" * 60)
    print("  GTX BLOCK STATUS")
    print("═" * 60)

    checks = {
        "_gtx_preflight() called":
            "_gtx_preflight(exchange, sym, side, target" in src,
        "fetch_order_book in fallback":
            "GTX rejected after pre-flight" in src,
        "best_bid extraction in fallback":
            "_bb2 = float(_ob2" in src,
        "-5022 detection present":
            "'-5022' in _emsg" in src,
        "old FIX-4.1 blind retry removed":
            "انزلق بعيداً عن السوق بمقدار 1 tick" not in src,
    }
    for k, v in checks.items():
        print(f"  {'✅' if v else '❌'} {k}")
    print()

    # ═══ 6. Show the exact new GTX block ═══
    print("═" * 60)
    print("  EXACT NEW GTX BLOCK (from 'وضع الأمر النهائي')")
    print("═" * 60)
    idx = src.find("# ══ وضع الأمر النهائي ══")
    if idx >= 0:
        end = min(len(src), idx + 3000)
        # Stop at next blank line followed by non-indented content
        snippet = src[idx:end]
        # Trim at first occurrence of a clean function-level dedent
        lines = snippet.split("\n")
        out = []
        for ln in lines[:80]:
            out.append(ln)
        print("\n".join(out))
    print()


if __name__ == "__main__":
    main()
