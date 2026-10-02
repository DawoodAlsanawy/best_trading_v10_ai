#!/usr/bin/env python3
"""verify_clean.py — diff trading_2.py vs trading_2_clean.py"""

import difflib
import sys

SRC = "trading_2.py"
DST = "trading_2_clean.py"


def main():
    try:
        with open(SRC, encoding="utf-8") as f:
            a = f.readlines()
        with open(DST, encoding="utf-8") as f:
            b = f.readlines()
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"trading_2.py       : {len(a):,} lines")
    print(f"trading_2_clean.py : {len(b):,} lines")
    print(f"delta              : {len(b) - len(a):+d} lines")
    print()

    diff = list(difflib.unified_diff(
        a, b, fromfile=SRC, tofile=DST, lineterm=""
    ))
    for line in diff:
        print(line, end="")

    hunk_count = sum(1 for line in diff if line.startswith("@@"))
    added = sum(1 for line in diff
                if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff
                  if line.startswith("-") and not line.startswith("---"))

    print()
    print(f"hunks  : {hunk_count}")
    print(f"added  : {added}")
    print(f"removed: {removed}")

    if hunk_count != 6:
        print(f"WARNING: expected 6 hunks, got {hunk_count}",
              file=sys.stderr)
        print("(Hunk count depends on the -U context; use `diff -U1` if "
              "you want an exact count.)", file=sys.stderr)


if __name__ == "__main__":
    main()
