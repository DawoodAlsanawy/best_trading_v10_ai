#!/usr/bin/env python3
"""apply_abl4e.py — PARTIAL_TP_R=1.5 + BREAKEVEN_AT_R=0.5."""
import os, sys
SRC = "trading_2.py"    # must be 4a-installed version
DST = "trading_2_abl4e.py"

PATCHES = [
    ("4e.be",
     "    BREAKEVEN_AT_R: float = 1.0\n",
     "    BREAKEVEN_AT_R: float = 0.5   # [ABL4e] combined with PT=1.5\n"),
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
            print(f"  status : FAIL (old={n_old} new={n_new})", file=sys.stderr)
            fail = True
    if fail: sys.exit(2)
    compile(text, DST, "exec")
    open(DST, "w", encoding="utf-8").write(text)
    print(f"  wrote {DST}")

if __name__ == "__main__": main()
