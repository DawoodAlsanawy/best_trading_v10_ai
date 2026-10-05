#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clean_redundant_fix15.py — يحذف كتلة FIX-15b المكررة فقط."""

import argparse
import re
import sys
import os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_release.py")
    ap.add_argument("--output", default="trading_2_clean.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ {args.input} not found")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()

    before = len(src)

    # ابحث عن كتلة FIX-15b بأكملها واحذفها
    pattern = re.compile(
        r'[ ]*# \[FIX-15b\] Trail params snapshot \(robust version\)\n'
        r'[ ]*_trail_d_snapshot, _trail_a_snapshot = 0\.003, 0\.004\n'
        r'[ ]*try:\n'
        r'(?:[ ]+.*\n)+?'
        r'[ ]*except Exception as _e:\n'
        r'[ ]*log\.debug\(f"\[FIX-15b\] trail snapshot failed: \{_e\}"\)\n',
        re.MULTILINE
    )
    matches = pattern.findall(src)
    if not matches:
        print("ℹ️  FIX-15b block not found in expected format — "
              "no changes made")
        sys.exit(0)

    src = pattern.sub('', src)
    after = len(src)

    # syntax check
    try:
        compile(src, args.output, "exec")
    except SyntaxError as e:
        print(f"❌ cleanup would break syntax at line {e.lineno}: {e.msg}")
        sys.exit(2)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src)

    print(f"✅ Cleaned: {args.output}")
    print(f"   Removed: {before - after:,} bytes")
    print(f"   Before:  {before:,} bytes")
    print(f"   After:   {after:,} bytes")

if __name__ == "__main__":
    main()
