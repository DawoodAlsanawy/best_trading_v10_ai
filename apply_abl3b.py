#!/usr/bin/env python3
"""apply_abl3b.py — HEAT_MAX 0.10 -> 0.03."""
import os, sys
SRC = "trading_2.py"
DST = "trading_2_abl3b.py"
OLD = "    PORTFOLIO_HEAT_MAX: float = 0.10       # 10% total risk-at-SL across all slots\n"
NEW = "    PORTFOLIO_HEAT_MAX: float = 0.03       # [ABL3b] 10% -> 3% total risk-at-SL\n"

def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr); sys.exit(1)
    text = open(SRC, encoding="utf-8").read()
    n_old = text.count(OLD); n_new = text.count(NEW)
    print("-- ABL3b --")
    if n_old == 1:
        text = text.replace(OLD, NEW, 1); print("  status : APPLIED")
    elif n_old == 0 and n_new == 1:
        print("  status : ALREADY APPLIED")
    else:
        print(f"  status : FAIL (old={n_old} new={n_new})", file=sys.stderr); sys.exit(2)
    compile(text, DST, "exec")
    open(DST, "w", encoding="utf-8").write(text)
    print(f"  wrote {DST}")

if __name__ == "__main__": main()
