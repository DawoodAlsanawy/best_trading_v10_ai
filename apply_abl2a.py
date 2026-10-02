#!/usr/bin/env python3
"""apply_abl2a.py — Ablation-2a: |z| >= 2.0 gate on top of Ablation-1."""
import os, sys

SRC = "trading_2_abl1.py"
DST = "trading_2_abl2a.py"

OLD = (
    "            _z_dev = (p - _z_mu) / _z_sd\n"
    "            if _z_dev == 0.0:\n"
    "                continue\n"
    "            action = \"BUY\" if _z_dev < 0 else \"SELL\"\n"
)
NEW = (
    "            _z_dev = (p - _z_mu) / _z_sd\n"
    "            if _z_dev == 0.0:\n"
    "                continue\n"
    "            # [ABLATION-2a] trade only extreme deviations\n"
    "            if abs(_z_dev) < 2.0:\n"
    "                continue\n"
    "            action = \"BUY\" if _z_dev < 0 else \"SELL\"\n"
)

def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr); sys.exit(1)
    text = open(SRC, encoding="utf-8").read()
    n_old = text.count(OLD); n_new = text.count(NEW)
    print("-- ABLATION-2a --")
    if n_old == 1:
        text = text.replace(OLD, NEW, 1); print("  status : APPLIED")
    elif n_old == 0 and n_new == 1:
        print("  status : ALREADY APPLIED")
    else:
        print(f"  status : FAIL (old={n_old} new={n_new})", file=sys.stderr)
        sys.exit(2)
    compile(text, DST, "exec")
    open(DST, "w", encoding="utf-8").write(text)
    print(f"  wrote {DST}")

if __name__ == "__main__":
    main()
