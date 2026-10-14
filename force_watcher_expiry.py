#!/usr/bin/env python3
"""
force_watcher_expiry.py

Fixes the age check so watchers expire after the sub-bar window
(matching backtest), not after REVERSAL_MAX_HOURS.

Uses regex to handle all known code variants.

Run:  python force_watcher_expiry.py
"""
import os, sys, shutil, hashlib, ast, re

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found", file=sys.stderr); sys.exit(1)

if "_FORCE_EXPIRY_FIX" in open(SRC).read():
    print("✗ Already patched. Restore from .bak first.", file=sys.stderr)
    sys.exit(3)

shutil.copy2(SRC, SRC + ".bak")
print(f"✓ backup → {SRC}.bak\n")

with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()
orig = s
report = []

# ═══════════════════════════════════════════════════════════════
# Strategy: find any line inside monitor_reversal_watchers that
# references REVERSAL_MAX_HOURS and nullify it (max() → only _max_age_s)
# ═══════════════════════════════════════════════════════════════

# FIX A — Remove the max() that combined _max_age_s with 24h
PAT_A = r'_limit_s\s*=\s*max\(\s*_max_age_s\s*,\s*float\(CFG\.REVERSAL_MAX_HOURS\)\s*\*\s*3600\.0\s*\)'
REP_A = '_limit_s = _max_age_s  # [FIXED] only sub-bar window'
s2, n_a = re.subn(PAT_A, REP_A, s)
if n_a > 0:
    s = s2
    report.append(f"✓ FIX-A: removed max() with 24h ({n_a} site(s))")
else:
    report.append("⚠ FIX-A: max() pattern not found")

# FIX B — Direct comparison line (original code)
OLD_B = 'if age_h > float(CFG.REVERSAL_MAX_HOURS):'
NEW_B = 'if age_h > (_max_age_s / 3600.0):  # [FIXED] sub-bar window'
if OLD_B in s:
    s = s.replace(OLD_B, NEW_B)
    report.append("✓ FIX-B: replaced direct 24h comparison")
else:
    report.append("⚠ FIX-B: direct comparison not found")

# FIX C — Any remaining `_limit_s = ` that still references 24h
PAT_C = r'float\(CFG\.REVERSAL_MAX_HOURS\)\s*\*\s*3600\.0'
s3, n_c = re.subn(PAT_C, '0.0  # [FIXED] never block expiry', s)
if n_c > 0:
    s = s3
    report.append(f"✓ FIX-C: neutralized {n_c} residual 24h reference(s)")
else:
    report.append("ℹ FIX-C: no residual references found")

# FIX D — Force _max_age_s to be computed BEFORE the loop
# (in case some variants compute it late)
if "_max_age_s = (" not in s:
    # Insert just before the `for sym in list(_REVERSAL_WATCHERS.keys()):`
    # line inside monitor_reversal_watchers
    anchor = "    for sym in list(_REVERSAL_WATCHERS.keys()):\n" \
             "        w = _REVERSAL_WATCHERS[sym]\n" \
             "        status = w.get(\"status\", \"WAITING_TOUCH\")"
    if anchor in s:
        block = (
            "    # [FORCE-EXPIRY] Guarantee _max_age_s is defined\n"
            "    if \"_max_age_s\" not in dir():\n"
            "        _tw = int(getattr(CFG, 'REVERSAL_TOUCH_SUBBARS', 20))\n"
            "        _bw = int(getattr(CFG, 'REVERSAL_BOUNCE_SUBBARS', 4))\n"
            "        _max_age_s = (_tw + _bw) * tf_sec\n\n"
        )
        # Only add if not already present
        if "_max_age_s = (" not in s.split(anchor)[0][-500:]:
            s = s.replace(anchor, block + anchor, 1)
            report.append("✓ FIX-D: ensured _max_age_s defined")
        else:
            report.append("ℹ FIX-D: _max_age_s already defined")
    else:
        report.append("⚠ FIX-D: loop anchor not found")

# ═══════════════════════════════════════════════════════════════
# Stamp + write
# ═══════════════════════════════════════════════════════════════
s = s.rstrip() + "\n\n# [FORCE_EXPIRY_FIX] applied\n"

if s == orig:
    print("═" * 68)
    print("  ⚠ No changes applied")
    for r in report:
        print("   " + r)
    print("═" * 68)
    sys.exit(2)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

try:
    ast.parse(s)
    syntax_ok = True
except SyntaxError as e:
    syntax_ok = False
    print(f"  ✗ SYNTAX ERROR: {e}")

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 68)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 68)
for line in report:
    print("   " + line)
print("═" * 68)
if syntax_ok:
    print("  ✓ Python syntax OK")
else:
    print(f"  ✗ Restore from {SRC}.bak")
    sys.exit(2)
print("═" * 68)
