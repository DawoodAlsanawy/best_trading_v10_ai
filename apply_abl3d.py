#!/usr/bin/env python3
"""apply_abl3d.py — combined: HEAT_MAX 0.05 + tightened DRAWDOWN thresholds."""
import os, sys
SRC = "trading_2.py"
DST = "trading_2_abl3d.py"

PATCHES = [
    ("3d.heat",
     "    PORTFOLIO_HEAT_MAX: float = 0.10       # 10% total risk-at-SL across all slots\n",
     "    PORTFOLIO_HEAT_MAX: float = 0.05       # [ABL3d] 10% -> 5% total risk-at-SL\n"),
    ("3d.dd_at",
     "    DRAWDOWN_REDUCE_AT:  float = 0.30\n",
     "    DRAWDOWN_REDUCE_AT:  float = 0.15   # [ABL3d] 0.30 -> 0.15\n"),
    ("3d.dd_at_50",
     "    DRAWDOWN_REDUCE_AT_50: float=0.50\n",
     "    DRAWDOWN_REDUCE_AT_50: float=0.30   # [ABL3d] 0.50 -> 0.30\n"),
    ("3d.dd_at_70",
     "    DRAWDOWN_REDUCE_AT_70: float=0.70\n",
     "    DRAWDOWN_REDUCE_AT_70: float=0.50   # [ABL3d] 0.70 -> 0.50\n"),
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
