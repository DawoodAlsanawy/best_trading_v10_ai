#!/usr/bin/env python3
"""apply_abl2b.py — Ablation-2b: |z| >= 2.0 gate + TP_MULT 5.0 -> 2.0."""
import os, sys

SRC = "trading_2_abl1.py"
DST = "trading_2_abl2b.py"

PATCHES = [
    (
        "2b.gate",
        "            _z_dev = (p - _z_mu) / _z_sd\n"
        "            if _z_dev == 0.0:\n"
        "                continue\n"
        "            action = \"BUY\" if _z_dev < 0 else \"SELL\"\n",
        "            _z_dev = (p - _z_mu) / _z_sd\n"
        "            if _z_dev == 0.0:\n"
        "                continue\n"
        "            # [ABLATION-2b] trade only extreme deviations\n"
        "            if abs(_z_dev) < 2.0:\n"
        "                continue\n"
        "            action = \"BUY\" if _z_dev < 0 else \"SELL\"\n",
    ),
    (
        "2b.tp_mult",
        "    TP_MULT: float = 5.0    # \u0643\u0627\u0646 2.0 \u2192 \u0627\u0644\u0622\u0646 1.5 (R:R = 1.5)\n",
        "    TP_MULT: float = 2.0    # [ABLATION-2b] 5.0 \u2192 2.0\n",
    ),
]

def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr); sys.exit(1)
    text = open(SRC, encoding="utf-8").read()
    fail = False
    for cid, old, new in PATCHES:
        n_old = text.count(old); n_new = text.count(new)
        print(f"-- ABLATION-{cid} --")
        if n_old == 1:
            text = text.replace(old, new, 1); print("  status : APPLIED")
        elif n_old == 0 and n_new == 1:
            print("  status : ALREADY APPLIED")
        else:
            print(f"  status : FAIL (old={n_old} new={n_new})", file=sys.stderr)
            fail = True
    if fail:
        sys.exit(2)
    compile(text, DST, "exec")
    open(DST, "w", encoding="utf-8").write(text)
    print(f"  wrote {DST}")

if __name__ == "__main__":
    main()
