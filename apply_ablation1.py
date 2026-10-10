#!/usr/bin/env python3
"""
apply_ablation1.py — Single surgical patch: direction source.

Replaces 1-bar micro-momentum with rolling-window mean-reversion
deviation in sigma units. Score, entry, SL/TP, sizing unchanged.

Idempotent. Aborts on ambiguity. Syntax-checks before writing.
"""
import os, sys

SRC = "trading_2.py"
DST = "trading_2_abl1.py"

OLD = (
    "            # المزامنة الطورية: زخم السعر الميكروي السريع لتحديد اتجاه التدفق\n"
    "            micro_momentum = p - ad.closes[ci - 1]\n"
    "            if micro_momentum == 0: continue\n"
    "            action = \"BUY\" if micro_momentum > 0 else \"SELL\"\n"
)

NEW = (
    "            # \u2550\u2550 [ABLATION-1] Direction from mean-reversion in \u03c3 units \u2550\u2550\n"
    "            _z_win = ad.closes[max(0, ci - CFG.N): ci]\n"
    "            if len(_z_win) < 2:\n"
    "                continue\n"
    "            _z_mu = float(np.mean(_z_win))\n"
    "            _z_sd = float(np.std(_z_win))\n"
    "            if _z_sd <= 1e-12:\n"
    "                continue\n"
    "            _z_dev = (p - _z_mu) / _z_sd\n"
    "            if _z_dev == 0.0:\n"
    "                continue\n"
    "            action = \"BUY\" if _z_dev < 0 else \"SELL\"\n"
)


def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr)
        sys.exit(1)

    with open(SRC, encoding="utf-8") as f:
        text = f.read()

    n_old = text.count(OLD)
    n_new = text.count(NEW)

    print("-- ABLATION-1 --")
    if n_old == 1:
        text = text.replace(OLD, NEW, 1)
        print("  status : APPLIED")
        print(f"  old[0] : {OLD.splitlines()[0].strip()[:70]}")
        print(f"  new[0] : {NEW.splitlines()[0].strip()[:70]}")
    elif n_old == 0 and n_new == 1:
        print("  status : ALREADY APPLIED")
        print(f"  new[0] : {NEW.splitlines()[0].strip()[:70]}")
    elif n_old == 0 and n_new == 0:
        print("  status : NOT FOUND", file=sys.stderr)
        print("  expected old snippet:", file=sys.stderr)
        for ln in OLD.splitlines():
            print(f"    | {ln}", file=sys.stderr)
        sys.exit(2)
    else:
        print(f"  status : AMBIGUOUS (old={n_old}x, new={n_new}x)",
              file=sys.stderr)
        sys.exit(2)

    try:
        compile(text, DST, "exec")
    except SyntaxError as e:
        print(f"SYNTAX ERROR after patch: {e}", file=sys.stderr)
        sys.exit(3)

    with open(DST, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\nWrote {DST} ({len(text):,} chars)")


if __name__ == "__main__":
    main()
