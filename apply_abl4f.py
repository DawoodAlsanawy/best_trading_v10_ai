#!/usr/bin/env python3
"""apply_abl4f.py — SL_WIDEN_MULT 1.5 -> 2.0."""
import os, sys
SRC = "trading_2.py"    # 4a-installed version
DST = "trading_2_abl4f.py"
OLD = "    SL_WIDEN_MULT: float = 1.5\n"
NEW = "    SL_WIDEN_MULT: float = 2.0   # [ABL4f] 1.5 -> 2.0 (wider SL)\n"

def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr); sys.exit(1)
    text = open(SRC, encoding="utf-8").read()
    n_old = text.count(OLD); n_new = text.count(NEW)
    print("-- ABL4f --")
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
