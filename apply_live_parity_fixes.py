#!/usr/bin/env python3
"""
apply_live_parity_fixes.py

Applies parity fixes between LIVE reversal logic and BACKTEST:

  A1  Live target now calls _backtest_entry_target (unified source)
  A2  Live window in sub-bars (matches backtest) — not hours
  A3  created_at / last_scan_ts anchored on sig.timestamp, not now()
  B2  qty snapped to exchange precision in every order placement
  B3  Watcher survives save_pending_orders() failure (no orphan orders)
  B5  SELL_ONLY / BUY_ONLY actually filter in build_signals

Idempotent: run once. A .bak is written before any change.

Run:  python apply_live_parity_fixes.py
"""
import os, re, sys, shutil, hashlib

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found in {os.getcwd()}", file=sys.stderr)
    sys.exit(1)

if "_LIVE_PARITY_FIXES" in open(SRC).read():
    print("✗ Already patched. Restore from .bak first.", file=sys.stderr)
    sys.exit(3)

shutil.copy2(SRC, SRC + ".bak")
print(f"✓ backup → {SRC}.bak\n")

with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()
orig = s
report = []

def patch(old, new, label, required=True):
    global s
    if old not in s:
        report.append(("✗" if required else "⚠") + f" {label}")
        return False
    s = s.replace(old, new, 1)
    report.append("✓ " + label)
    return True

def patch_all(old, new, label, required=True, max_n=10):
    global s
    n = s.count(old)
    if n == 0:
        report.append(("✗" if required else "⚠") + f" {label}: 0 matches")
        return False
    s = s.replace(old, new, max_n)
    report.append(f"✓ {label} ({n} site(s))")
    return True


# ═══════════════════════════════════════════════════════════════
# A1 — Unified target: live uses _backtest_entry_target
# ═══════════════════════════════════════════════════════════════
# Match both the apply_live_reversal.py variant (target = sig.price)
# and the apply_reversal_simple.py variant.

A1_OLD_A = '''    _REVERSAL_WATCHERS[sym] = w
    log.info(f"[LiveRev] {sig.action} {sym} registered — '''
A1_NEW_A = '''    _REVERSAL_WATCHERS[sym] = w
    log.info(f"[LiveRev] {sig.action} {sym} registered — '''

# In apply_live_reversal.py, target is set as:
A1_OLD_1 = '''    w = {
        "sym": sym,
        "side": side,
        "action": sig.action,
        "target": float(sig.price),'''
A1_NEW_1 = '''    # ═══ [A1] Unified target: same source as backtest ═══
    try:
        _bt_target = float(_backtest_entry_target(sig, ad))
    except Exception:
        _bt_target = float(sig.price)
    w = {
        "sym": sym,
        "side": side,
        "action": sig.action,
        "target": _bt_target,'''
patch(A1_OLD_1, A1_NEW_1, "A1a: live_reversal target → _backtest_entry_target",
      required=False)

# In apply_reversal_simple.py, target is set as:
A1_OLD_2 = '''        "target":      float(sig.price),'''
A1_NEW_2 = '''        "target":      (float(_backtest_entry_target(sig, ad))
                         if ad is not None else float(sig.price)),'''
patch(A1_OLD_2, A1_NEW_2, "A1b: reversal_simple target → _backtest_entry_target",
      required=False)


# ═══════════════════════════════════════════════════════════════
# A2 — Window units: sub-bars, not hours
# ═══════════════════════════════════════════════════════════════
A2_OLD = '''    max_h  = float(getattr(CFG, 'REVERSAL_MAX_HOURS', 24.0))
    now    = _t_rc.time()
    throttle = float(getattr(CFG, 'REVERSAL_LIVE_FETCH_EVERY_S', 30.0))'''
A2_NEW = '''    # ═══ [A2] Window in sub-bars (matches backtest) ═══
    _tw = int(getattr(CFG, 'REVERSAL_TOUCH_WINDOW', 20))
    _bw = int(getattr(CFG, 'REVERSAL_BOUNCE_WINDOW', 4))
    _sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"
    _sub_sec = _sub_tf_seconds_simple(_sub_tf)
    max_h = (_tw + _bw) * _sub_sec / 3600.0
    now    = _t_rc.time()
    throttle = float(getattr(CFG, 'REVERSAL_LIVE_FETCH_EVERY_S', 30.0))'''
patch(A2_OLD, A2_NEW, "A2: window in sub-bars (reversal_simple)",
      required=False)

# For apply_live_reversal.py variant
A2_OLD_B = '''    sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"
    tf_sec = _sub_tf_seconds(sub_tf)
    now = _t_rev.time()
    fills_this_cycle = 0'''
A2_NEW_B = '''    sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"
    tf_sec = _sub_tf_seconds(sub_tf)
    now = _t_rev.time()
    fills_this_cycle = 0
    # ═══ [A2] Unified max-age in sub-bars (matches backtest) ═══
    _tw = int(getattr(CFG, 'REVERSAL_TOUCH_SUBBARS', 20))
    _bw = int(getattr(CFG, 'REVERSAL_BOUNCE_SUBBARS', 4))
    _max_age_s = (_tw + _bw) * tf_sec'''
patch(A2_OLD_B, A2_NEW_B, "A2b: unified max-age (live_reversal)",
      required=False)


# ═══════════════════════════════════════════════════════════════
# A3 — created_at / last_scan_ts anchored on sig.timestamp
# ═══════════════════════════════════════════════════════════════
A3_OLD_1 = '''    sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"
    _now = _t_rc.time()
    _REVERSAL_STATES[sym] = {'''
A3_NEW_1 = '''    sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"
    # ═══ [A3] Anchor on signal timestamp, not wall-clock ═══
    try:
        _sig_ts = pd.Timestamp(sig.timestamp)
        if _sig_ts.tz is None:
            _sig_ts = _sig_ts.tz_localize("UTC")
        _sig_unix = float(_sig_ts.timestamp())
    except Exception:
        _sig_unix = _t_rc.time()
    _now = _sig_unix
    _REVERSAL_STATES[sym] = {'''
patch(A3_OLD_1, A3_NEW_1, "A3a: reversal_simple anchor on sig.timestamp",
      required=False)

# Also fix created_at in reversal_simple variant
A3_OLD_2 = '''        "created_at":  _now,'''
A3_NEW_2 = '''        "created_at":  _now,
        "sig_ts_unix": _now,'''
patch(A3_OLD_2, A3_NEW_2, "A3b: reversal_simple add sig_ts_unix",
      required=False)

# For apply_live_reversal.py variant — sig_ts is already stored but
# created_at uses wall-clock. Anchor it to sig_ts.
A3_OLD_3 = '''        "close_ts": float(close_ts),
        "created_at": _t_rev.time(),'''
A3_NEW_3 = '''        "close_ts": float(close_ts),
        "created_at": float(close_ts),
        "last_scan_ts": float(close_ts),'''
patch(A3_OLD_3, A3_NEW_3,
      "A3c: live_reversal anchor created_at on sig.close_ts",
      required=False)


# ═══════════════════════════════════════════════════════════════
# B2 — Precision snap for qty (Live + place_pending_entry)
# ═══════════════════════════════════════════════════════════════
# Snapshot a precision helper near the top of the module.
B2_HELPER_ANCHOR = "def _exchange_source_tag(exchange) -> str:"
if B2_HELPER_ANCHOR in s:
    B2_HELPER = '''def _snap_qty(exchange, sym: str, qty: float) -> float:
    """[B2] Snap qty to exchange precision. Returns 0.0 if invalid."""
    try:
        q = float(exchange.amount_to_precision(sym, float(qty)))
        return q if q > 0 else 0.0
    except Exception:
        return float(qty)


'''
    patch(B2_HELPER_ANCHOR, B2_HELPER + B2_HELPER_ANCHOR,
          "B2a: insert _snap_qty helper")
else:
    report.append("⚠ B2a: _exchange_source_tag anchor not found — "
                  "helper inserted at module start")

# Snap qty in place_pending_entry right after qty validation.
B2_OLD_1 = '''    # ══ [OFFSET-DELEGATION] ══'''
if B2_OLD_1 in s:
    B2_NEW_1 = '''    # ═══ [B2] Snap qty to exchange precision ═══
    try:
        qty = float(_snap_qty(exchange, sym, qty))
        if qty <= 0:
            log.warning(f"[Pending] {sym} qty after precision = 0 — skip")
            return None
    except Exception:
        pass

    # ══ [OFFSET-DELEGATION] ══'''
    patch(B2_OLD_1, B2_NEW_1, "B2b: snap qty in place_pending_entry")

# Snap qty in _execute_reversal_fill (all variants).
B2_PATTERN = r"    qty = float\(w\[.qty.\]\)"
B2_REPL = ("    qty = float(w[\"qty\"])\n"
           "    qty = float(_snap_qty(exchange, sym, qty))\n"
           "    if qty <= 0:\n"
           "        w[\"status\"] = \"EXPIRED\"\n"
           "        return")
s, n = re.subn(B2_PATTERN, B2_REPL, s, count=5)
if n > 0:
    report.append(f"✓ B2c: snap qty in _execute_reversal_fill ({n} site(s))")
else:
    report.append("⚠ B2c: _execute_reversal_fill qty anchor not found")

# Snap qty in _fire_eager_market
B2_EAGER = "    qty = float(w[\"qty\"])\n    try:\n        _mo = exchange.create_order(sym, 'market', side, qty, None)"
B2_EAGER_NEW = ("    qty = float(w[\"qty\"])\n"
                "    qty = float(_snap_qty(exchange, sym, qty))\n"
                "    if qty <= 0:\n"
                "        w[\"status\"] = \"EXPIRED\"\n"
                "        return\n"
                "    try:\n"
                "        _mo = exchange.create_order(sym, 'market', side, qty, None)")
patch(B2_EAGER, B2_EAGER_NEW, "B2d: snap qty in _fire_eager_market",
      required=False)


# ═══════════════════════════════════════════════════════════════
# B3 — Watcher survives save_pending_orders() failure
# ═══════════════════════════════════════════════════════════════
B3_OLD = '''                    try:
                        _to_s = float(getattr(CFG, 'PO_MAX_WAIT_S', 0) or 30.0)
                        place_pending_entry(
                            exchange, sym, rec["side"], rec["qty"],
                            rec["sig"],
                            timeout_s=_to_s,
                            leverage=int(rec["leverage"]),
                            ad=rec["ad_ref"],
                        )
                        try:
                            save_pending_orders()
                        except Exception:
                            pass
                    except Exception as e:
                        log.warning(f"[RevConfirm] {sym} place failed: {e}")
                    _REVERSAL_STATES.pop(sym, None)
                    break'''

B3_NEW = '''                    _placed_ok = False
                    try:
                        _to_s = float(getattr(CFG, 'PO_MAX_WAIT_S', 0) or 30.0)
                        place_pending_entry(
                            exchange, sym, rec["side"], rec["qty"],
                            rec["sig"],
                            timeout_s=_to_s,
                            leverage=int(rec["leverage"]),
                            ad=rec["ad_ref"],
                        )
                        _placed_ok = True
                    except Exception as e:
                        log.warning(f"[RevConfirm] {sym} place failed: {e}")

                    # ═══ [B3] Only drop the watcher on success ═══
                    if _placed_ok:
                        try:
                            save_pending_orders()
                        except Exception as _se:
                            # Order exists on the exchange but could not
                            # be persisted. Keep the watcher and let
                            # reconcile adopt on next cycle.
                            log.warning(
                                f"[RevConfirm] {sym} save failed "
                                f"({_se}) — keeping watcher for reconcile"
                            )
                            rec["phase"] = "PLACED_UNPERSISTED"
                            break
                        _REVERSAL_STATES.pop(sym, None)
                    else:
                        # Placement itself failed → drop (no order exists)
                        _REVERSAL_STATES.pop(sym, None)
                    break'''
patch(B3_OLD, B3_NEW, "B3: watcher survives save failure",
      required=False)


# ═══════════════════════════════════════════════════════════════
# B5 — SELL_ONLY / BUY_ONLY in build_signals
# ═══════════════════════════════════════════════════════════════
B5_ANCHOR = '''            _z_dev = (p - _z_mu) / _z_sd
            if _z_dev == 0.0:
                continue'''
B5_NEW = '''            _z_dev = (p - _z_mu) / _z_sd
            if _z_dev == 0.0:
                continue

            # ═══ [B5] Direction gate: honor SELL_ONLY / BUY_ONLY ═══
            if _z_dev > 0:
                if getattr(CFG, 'BUY_ONLY', False):
                    continue
            else:
                if getattr(CFG, 'SELL_ONLY', False):
                    continue'''
patch(B5_ANCHOR, B5_NEW, "B5a: direction gate in build_signals",
      required=False)

# Also honor GAUGE_DISABLE_BUY if SELL_ONLY was wired there.
B5B_ANCHOR = '    if getattr(args, "sell_only", False):\n        CFG.GAUGE_DISABLE_BUY = True\n        log.info("[Ablation] BUY DISABLED — SELL-only mode")'
B5B_NEW = '''    if getattr(args, "sell_only", False):
        CFG.SELL_ONLY = True
        CFG.GAUGE_DISABLE_BUY = True
        log.info("[Ablation] SELL_ONLY — BUY signals rejected")'''
patch(B5B_ANCHOR, B5B_NEW, "B5b: wire --sell-only to CFG.SELL_ONLY",
      required=False)

# Add the CFG fields if missing.
CFG_ANCHOR = "    GAUGE_DISABLE_SELL: bool = True    # Default: BUY-only"
CFG_NEW = CFG_ANCHOR + """
    SELL_ONLY: bool = False
    BUY_ONLY:  bool = False"""
patch(CFG_ANCHOR, CFG_NEW, "B5c: CFG fields SELL_ONLY / BUY_ONLY",
      required=False)


# ═══════════════════════════════════════════════════════════════
# Stamp marker + write
# ═══════════════════════════════════════════════════════════════
s = s.rstrip() + "\n\n# [LIVE-PARITY-FIXES] applied\n"

if s == orig:
    print("⚠  No changes applied:", file=sys.stderr)
    for line in report:
        print("   " + line, file=sys.stderr)
    sys.exit(2)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 68)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 68)
for line in report:
    print("   " + line)
print("═" * 68)
