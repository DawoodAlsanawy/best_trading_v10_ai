#!/usr/bin/env python3
"""apply_abl4a.py — PARTIAL_TP_R 3.0 -> 1.5."""
import os, sys
SRC = "trading_2.py"
DST = "trading_2_abl4a.py"
OLD = "    PARTIAL_TP_R: float = 3.0           # take profit at +1R\n"
NEW = "    PARTIAL_TP_R: float = 1.5           # [ABL4a] 3.0 -> 1.5\n"

def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr); sys.exit(1)
    text = open(SRC, encoding="utf-8").read()
    n_old = text.count(OLD); n_new = text.count(NEW)
    print("-- ABL4a --")
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
