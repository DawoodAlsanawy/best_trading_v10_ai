# apply_abl8b.py
#!/usr/bin/env python3
"""apply_abl8b.py — GAUGE_PERCENTILE_SELL 0.85 -> 0.95."""
import os, sys
SRC = "trading_2.py"
DST = "trading_2_abl8b.py"
OLD = "    GAUGE_PERCENTILE_SELL: float = 0.85\n"
NEW = "    GAUGE_PERCENTILE_SELL: float = 0.95   # [ABL8b] 0.85 -> 0.95\n"

def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr); sys.exit(1)
    text = open(SRC, encoding="utf-8").read()
    n_old = text.count(OLD); n_new = text.count(NEW)
    print("-- ABL8b --")
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
