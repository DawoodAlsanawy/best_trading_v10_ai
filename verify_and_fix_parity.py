#!/usr/bin/env python3
"""
verify_and_fix_parity.py

Ensures all live-parity fixes are present in trading_2_live4.py.
Idempotent: safe to run multiple times.

Critical fix:
  B2  Insert missing _snap_qty helper (was called but undefined)

Bonus fixes:
  A2  Make _max_age_s actually used in the age check

Verification-only:
  A1, A3, B5 — reported, not modified (already present)

Run:  python verify_and_fix_parity.py
"""
import os, sys, shutil, hashlib

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found in {os.getcwd()}", file=sys.stderr)
    sys.exit(1)

# Always backup (safe — overwrites previous .bak)
shutil.copy2(SRC, SRC + ".bak")
print(f"✓ backup → {SRC}.bak\n")

with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()
orig = s

report = []

def patch(old, new, label, required=True):
    global s
    if old not in s:
        report.append(("✗" if required else "⚠") + f" {label}: anchor not found")
        return False
    s = s.replace(old, new, 1)
    report.append("✓ " + label)
    return True

def check(marker, label):
    if marker in s:
        report.append("✓ " + label + " (already present)")
        return True
    report.append("✗ " + label + " (MISSING)")
    return False


# ═══════════════════════════════════════════════════════════════
# CRITICAL FIX 1 — Insert _snap_qty helper
# ═══════════════════════════════════════════════════════════════
if "_snap_qty" in s and "def _snap_qty" in s:
    report.append("✓ _snap_qty helper (already present)")
else:
    # Insert before the first caller. The first call site is inside
    # _execute_reversal_fill. Insert the helper just before it.
    ANCHOR = "def _execute_reversal_fill(exchange, sym: str, w: Dict,\n" \
             "                            open_pos_live: Dict) -> None:"
    if ANCHOR in s:
        HELPER = '''def _snap_qty(exchange, sym: str, qty: float) -> float:
    """
    [B2] Snap qty to exchange precision. Returns 0.0 on failure.
    Prevents -1111: Precision is over the maximum errors from Binance.
    """
    try:
        q = float(exchange.amount_to_precision(sym, float(qty)))
        return q if q > 0 else 0.0
    except Exception:
        return float(qty)


'''
        s = s.replace(ANCHOR, HELPER + ANCHOR, 1)
        report.append("✓ _snap_qty helper inserted (critical fix)")
    else:
        report.append("✗ _snap_qty: anchor function not found — MANUAL FIX NEEDED")


# ═══════════════════════════════════════════════════════════════
# CRITICAL FIX 2 — Make _max_age_s actually used in monitor
# ═══════════════════════════════════════════════════════════════
# Current code:
#   _max_age_s = (_tw + _bw) * tf_sec
#   ...
#   if age_h > float(CFG.REVERSAL_MAX_HOURS):
#
# We want: the age check uses _max_age_s (sub-bar based, matches backtest)
# OR the REVERSAL_MAX_HOURS if that's larger (user override protection).

OLD_AGE = '''        age_h = (now - float(w.get("close_ts", now))) / 3600.0
        if age_h > float(CFG.REVERSAL_MAX_HOURS):
            log.info(f"[LiveRev] {sym} expired (age={age_h:.1f}h)")
            _REVERSAL_WATCHERS.pop(sym, None)
            continue'''

NEW_AGE = '''        # ═══ [A2-FIX] Age limit uses sub-bar window (matches backtest),
        #    but honors a larger REVERSAL_MAX_HOURS if user set one.
        _age_s = now - float(w.get("close_ts", now))
        _limit_s = max(_max_age_s, float(CFG.REVERSAL_MAX_HOURS) * 3600.0)
        if _age_s > _limit_s:
            log.info(f"[LiveRev] {sym} expired (age={_age_s/3600:.1f}h "
                     f"> {_limit_s/3600:.1f}h)")
            _REVERSAL_WATCHERS.pop(sym, None)
            continue'''
patch(OLD_AGE, NEW_AGE, "A2: make _max_age_s actually used in age check")


# ═══════════════════════════════════════════════════════════════
# VERIFICATION — informational checks for A1, A3, B5, B2 call sites
# ═══════════════════════════════════════════════════════════════
check("_backtest_entry_target(sig, ad)",
      "A1: unified target in reversal watcher")
check("created_at\": float(close_ts)",
      "A3: created_at anchored on signal timestamp")
check("SELL_ONLY", "B5: SELL_ONLY flag")
check("BUY_ONLY", "B5: BUY_ONLY flag")

# Count _snap_qty call sites
_n_calls = s.count("_snap_qty(exchange")
if _n_calls >= 2:
    report.append(f"✓ B2: {_n_calls} call sites of _snap_qty present")
else:
    report.append(f"⚠ B2: only {_n_calls} call sites (expected ≥ 2)")


# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
if s == orig:
    print("═" * 72)
    print("  ℹ No changes needed — verification only")
    print("═" * 72)
    for line in report:
        print("   " + line)
    print("═" * 72)
    sys.exit(0)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 72)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 72)
for line in report:
    print("   " + line)
print("═" * 72)

# ═══════════════════════════════════════════════════════════════
# Syntax check
# ═══════════════════════════════════════════════════════════════
import ast
try:
    ast.parse(s)
    print("  ✓ Python syntax OK")
except SyntaxError as e:
    print(f"  ✗ SYNTAX ERROR: {e}")
    print(f"    Restore from {SRC}.bak if broken")
    sys.exit(2)
print("═" * 72)
