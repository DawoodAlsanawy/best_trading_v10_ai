#!/usr/bin/env python3
"""apply_abl7b.py — APEX_ENABLED=True + KAPPA_PNL 0.5 -> 2.0."""
import os, sys
SRC = "trading_2.py"
DST = "trading_2_abl7b.py"

PATCHES = [
    ("7b.enable",
     "    APEX_ENABLED: bool = False    #",
     "    APEX_ENABLED: bool = True     #"),
    ("7b.kappa_pnl",
     "    APEX_KAPPA_PNL: float = 0.5\n",
     "    APEX_KAPPA_PNL: float = 2.0   # [ABL7b]\n"),
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
            print(f"  status : FAIL", file=sys.stderr); fail = True
    if fail: sys.exit(2)
    compile(text, DST, "exec")
    open(DST, "w", encoding="utf-8").write(text)
    print(f"  wrote {DST}")

if __name__ == "__main__": main()
