#!/usr/bin/env python3
"""Show exactly how a patched file differs from trading_2.py.
  python verify_clean.py                          # trading_2.py vs trading_2_clean.py   (expects 7 hunks = 4 edits)
  python verify_clean.py trading_2_baseline.py    # baseline file                        (expects 1 hunk  = 1 edit)
"""
import sys, difflib

A = "trading_2.py"
B = sys.argv[1] if len(sys.argv) > 1 else "trading_2_clean.py"
EXPECT_HUNKS = 1 if "baseline" in B else 7      # V=1, P1.1=2 (cap0 line sits between), L.1=3, L.2=1
EXPECT_EDITS = 1 if "baseline" in B else 4
rd = lambda p: open(p, encoding="utf-8", newline="").read().splitlines()
a, b = rd(A), rd(B)
print(f"{A}: {len(a)} lines\n{B}: {len(b)} lines   (delta {len(b)-len(a):+d})\n")
hunks = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
removed = added = 0
for i, (tag, i1, i2, j1, j2) in enumerate(hunks, 1):
    print(f"=== hunk {i}: {tag}  old lines {i1+1}-{i2}  ->  new lines {j1+1}-{j2}")
    for k in range(i1, i2): print(f"  - {k+1:>5}: {a[k]}")
    for k in range(j1, j2): print(f"  + {k+1:>5}: {b[k]}")
    removed += i2 - i1; added += j2 - j1
print(f"\nhunks={len(hunks)} (expected {EXPECT_HUNKS}), lines removed={removed}, added={added}")
ok = len(hunks) == EXPECT_HUNKS
print(f"CONFIDENCE: {'PASS' if ok else 'FAIL'} - {EXPECT_EDITS} logical edit(s) => {EXPECT_HUNKS} hunk(s) expected")
sys.exit(0 if ok else 1)
