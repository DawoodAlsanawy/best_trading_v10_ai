#!/usr/bin/env python3
"""apply_abl3c.py — tighten DRAWDOWN_REDUCE_AT: 0.30/0.50/0.70 -> 0.15/0.30/0.50."""
import os, sys
SRC = "trading_2.py"
DST = "trading_2_abl3c.py"

PATCHES = [
    ("3c.dd_at",
     "    DRAWDOWN_REDUCE_AT:  float = 0.30\n",
     "    DRAWDOWN_REDUCE_AT:  float = 0.15   # [ABL3c] 0.30 -> 0.15\n"),
    ("3c.dd_at_50",
     "    DRAWDOWN_REDUCE_AT_50: float=0.50\n",
     "    DRAWDOWN_REDUCE_AT_50: float=0.30   # [ABL3c] 0.50 -> 0.30\n"),
    ("3c.dd_at_70",
     "    DRAWDOWN_REDUCE_AT_70: float=0.70\n",
     "    DRAWDOWN_REDUCE_AT_70: float=0.50   # [ABL3c] 0.70 -> 0.50\n"),
]

def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr); sys.exit(1)
    text = open(SRC, encoding="utf-8").read()
    fail = False
    for cid, old, new in PATCHES:
        n_old = text.count(old); n_new = text.count(new)
        print(f"-- ABL{cid} --")
        if n_old == 1:
            text = text.replace(old, new, 1); print("  status : APPLIED")
        elif n_old == 0 and n_new == 1:
            print("  status : ALREADY APPLIED")
        else:
            print(f"  status : FAIL (old={n_old} new={n_new})", file=sys.stderr); fail = True
    if fail: sys.exit(2)
    compile(text, DST, "exec")
    open(DST, "w", encoding="utf-8").write(text)
    print(f"  wrote {DST}")

if __name__ == "__main__": main()
