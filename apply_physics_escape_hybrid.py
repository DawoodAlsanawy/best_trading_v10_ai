#!/usr/bin/env python3
"""
apply_physics_escape_hybrid.py

Upgrades _execute_reversal_fill from GTX-only to a physics-aware hybrid:

  * Places GTX at target (maker, cheap).
  * While open, polls the ticker and evaluates an "escape" signal:
        d_sigma = |p_now − target| / (σ_bar · target)
        rho     = |accel| · (1 + gauge) / (friction · d_sigma + ε)
    ESCAPE when d_sigma > D_MAX, or (d_sigma ≥ D_MIN and rho > RHO_THR).
  * On ESCAPE: cancel GTX, sweep fills, send MARKET for the REMAINING
    quantity only (partial-fill safe).

Requires: apply_gtx_only_fix.py already applied (marker: GTX-ONLY).

Run:  python apply_physics_escape_hybrid.py
"""
import os, re, sys, shutil, hashlib

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found", file=sys.stderr); sys.exit(1)

txt = open(SRC).read()
if "GTX-ONLY" not in txt:
    print("✗ apply_gtx_only_fix.py not applied. Run it first.",
          file=sys.stderr); sys.exit(2)
if "_physics_escape_decision" in txt:
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

# ═══════════════════════════════════════════════════════════════
# 1. CFG — escape decision parameters
# ═══════════════════════════════════════════════════════════════
CFG_ANCHOR = '    REVERSAL_FILL_AT:        str   = "target" # [DEPRECATED] always target'
CFG_NEW = CFG_ANCHOR + """

    # ══ [ESCAPE] Physics-based switch from GTX to Market ══
    # The decision uses two quantities derived from stored signal-time
    # physics + the live ticker:
    #   d_sigma = |p_now − target| / (σ_bar · target)
    #   rho     = |accel| · (1 + gauge) / (friction · d_sigma + ε)
    REVERSAL_ESCAPE_ENABLED: bool = True
    REVERSAL_ESCAPE_D_SIGMA_MIN: float = 1.0
    REVERSAL_ESCAPE_D_SIGMA_MAX: float = 2.0
    REVERSAL_ESCAPE_RHO_THRESHOLD: float = 1.5
    REVERSAL_ESCAPE_CHECK_INTERVAL_S: float = 5.0"""
patch(CFG_ANCHOR, CFG_NEW, "CFG: 5 escape parameters")

# ═══════════════════════════════════════════════════════════════
# 2. Physics helper — insert before _execute_reversal_fill
# ═══════════════════════════════════════════════════════════════
ANCHOR2 = '''def _execute_reversal_fill(exchange, sym: str, w: Dict,
                            open_pos_live: Dict) -> None:'''

HELPER = '''def _physics_escape_decision(w: Dict, p_now: float) -> str:
    """
    [ESCAPE] Decide whether to abandon GTX and market-fill.

    Returns 'HOLD' or 'ESCAPE'.

    Physics:
      d_sigma = |p_now − target| / (σ_bar · target)
      rho     = |accel| · (1 + gauge) / (friction · d_sigma + ε)

    Rules (in order):
      1. Direction check — if price moved TOWARD target, HOLD.
      2. Hard cap      — d_sigma > D_MAX  → ESCAPE.
      3. Min distance  — d_sigma < D_MIN  → HOLD.
      4. Force ratio   — rho > RHO_THR    → ESCAPE.
    Otherwise HOLD.
    """
    if not getattr(CFG, 'REVERSAL_ESCAPE_ENABLED', True):
        return 'HOLD'
    try:
        action = w.get('action', 'BUY')
        target = float(w.get('target', 0.0))
        if target <= 0 or p_now <= 0:
            return 'HOLD'

        sigma = float(w.get('sigma_bar', 0.01))
        if not (sigma > 1e-9):
            return 'HOLD'

        d = abs(p_now - target) / (sigma * target)

        # Direction: ESCAPE means the price is moving AWAY from target.
        if action == 'BUY':
            moving_away = p_now > target
        else:
            moving_away = p_now < target
        if not moving_away:
            return 'HOLD'

        d_max = float(getattr(CFG, 'REVERSAL_ESCAPE_D_SIGMA_MAX', 2.0))
        if d > d_max:
            return 'ESCAPE'

        d_min = float(getattr(CFG, 'REVERSAL_ESCAPE_D_SIGMA_MIN', 1.0))
        if d < d_min:
            return 'HOLD'

        accel = abs(float(w.get('accel', 0.05)))
        gauge = float(w.get('gauge_force', 0.1))
        friction = float(w.get('friction', 0.2))

        rho = (accel * (1.0 + gauge)) / (friction * d + 1e-9)
        rho_thr = float(getattr(CFG, 'REVERSAL_ESCAPE_RHO_THRESHOLD', 1.5))

        return 'ESCAPE' if rho > rho_thr else 'HOLD'
    except Exception:
        return 'HOLD'


'''
patch(ANCHOR2, HELPER + ANCHOR2, "insert _physics_escape_decision helper")

# ═══════════════════════════════════════════════════════════════
# 3. Replace the entire _execute_reversal_fill body
# ═══════════════════════════════════════════════════════════════
SIG = ('def _execute_reversal_fill(exchange, sym: str, w: Dict,\n'
       '                            open_pos_live: Dict) -> None:')
if SIG not in s:
    report.append("✗ _execute_reversal_fill signature not found")
else:
    start = s.index(SIG) + len(SIG)
    # Find next top-level function
    m = re.search(r"\ndef [a-zA-Z_]", s[start:])
    if not m:
        report.append("✗ next top-level def not found")
    else:
        end = start + m.start()
        NEW_BODY = r'''

    action = w["action"]
    target = float(w["target"])
    qty = float(w["qty"])
    side = "buy" if action == "BUY" else "sell"

    # ── Leverage / margin setup ──
    try:
        ensure_symbol_setup(exchange, sym, int(w["leverage"]),
                             margin_mode="isolated")
    except Exception as e:
        log.warning(f"[LiveRev] setup {sym}: {e}")
        w["status"] = "EXPIRED"
        return

    # ── Place initial GTX at target ──
    try:
        _o = exchange.create_order(sym, 'limit', side, qty, target,
                                    params={'timeInForce': 'GTX'})
        order_id = str(_o['id'])
    except Exception as e:
        log.info(f"[LiveRev] {sym} GTX rejected at {target:.6f}: {e}")
        w["status"] = "EXPIRED"
        return

    filled_qty = 0.0
    total_cost = 0.0
    active = True
    t0 = _t_rev.time()
    last_phys_check = 0.0
    max_wait = float(getattr(CFG, 'PO_MAX_WAIT_S', 30))
    escape_interval = float(getattr(
        CFG, 'REVERSAL_ESCAPE_CHECK_INTERVAL_S', 5.0))

    # ── Main polling loop ──
    while active and (_t_rev.time() - t0) < max_wait:
        _t_rev.sleep(1.0)
        try:
            _st = exchange.fetch_order(order_id, sym)
        except Exception:
            continue

        _fq = float(_st.get('filled') or 0.0)
        _fp = float(_st.get('average') or _st.get('price') or target)
        _status = str(_st.get('status') or 'open')

        if _fq > filled_qty:
            _delta = _fq - filled_qty
            total_cost += _delta * _fp
            filled_qty = _fq

        if _status == 'closed':
            active = False
            break
        if _status in ('canceled', 'expired', 'rejected'):
            active = False
            break

        # ── Physics escape check ──
        now = _t_rev.time()
        if (now - last_phys_check) >= escape_interval:
            last_phys_check = now
            try:
                _tk = exchange.fetch_ticker(sym)
                p_now = float(_tk.get('last') or 0)
            except Exception:
                p_now = 0.0

            if p_now > 0 and \
                    _physics_escape_decision(w, p_now) == 'ESCAPE':
                log.info(f"[LiveRev] {sym} ESCAPE detected "
                         f"(price={p_now:.6f} target={target:.6f} "
                         f"filled={filled_qty:.6f}/{qty:.6f}) "
                         f"→ market for remaining")
                # Cancel GTX
                try:
                    exchange.cancel_order(order_id, sym)
                except Exception:
                    pass
                _t_rev.sleep(0.3)
                # Mandatory sweep — catch late fills
                try:
                    _st2 = exchange.fetch_order(order_id, sym)
                    _fq2 = float(_st2.get('filled') or 0.0)
                    if _fq2 > filled_qty:
                        _d2 = _fq2 - filled_qty
                        _fp2 = float(_st2.get('average') or target)
                        total_cost += _d2 * _fp2
                        filled_qty = _fq2
                except Exception:
                    pass

                # Market order for REMAINING only
                remaining = qty - filled_qty
                _min_notional = float(getattr(CFG, 'MIN_NOTIONAL', 5.0))
                if remaining > 0 and (remaining * target) >= _min_notional:
                    try:
                        _mo = exchange.create_order(
                            sym, 'market', side, remaining, None)
                        _v = verify_fill(exchange, _mo['id'], sym,
                                          timeout_s=3.0)
                        if _v and _v.get('filled'):
                            _mq = float(_v['qty'])
                            _mp = float(_v['avg_price'])
                            total_cost += _mq * _mp
                            filled_qty += _mq
                    except Exception as _me:
                        log.warning(f"[LiveRev] {sym} market fallback "
                                    f"failed: {_me}")
                elif remaining > 0:
                    log.info(f"[LiveRev] {sym} remaining "
                             f"{remaining:.6f} below MIN_NOTIONAL — "
                             f"keeping partial")
                active = False
                break

    # ── Loop exited with active=True: timeout or status change ──
    if active:
        try:
            exchange.cancel_order(order_id, sym)
        except Exception:
            pass
        _t_rev.sleep(0.3)
        try:
            _stf = exchange.fetch_order(order_id, sym)
            _fqf = float(_stf.get('filled') or 0.0)
            if _fqf > filled_qty:
                _df = _fqf - filled_qty
                _fpf = float(_stf.get('average') or target)
                total_cost += _df * _fpf
                filled_qty = _fqf
        except Exception:
            pass

    if filled_qty <= 0:
        log.info(f"[LiveRev] {sym} no fill — watcher expired")
        w["status"] = "EXPIRED"
        return

    entry_px = total_cost / filled_qty
    actual_qty = filled_qty

    # ── SL / TP rebuild (unchanged) ──
    orig_sl_dist = float(w["orig_sl_dist"])
    orig_tp_dist = float(w["orig_tp_dist"])
    if orig_sl_dist <= 1e-12:
        orig_sl_dist = entry_px * 0.015
        orig_tp_dist = orig_sl_dist * float(getattr(CFG, "TP_MULT", 2.0))

    _max_sl_frac = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
    if orig_sl_dist > entry_px * _max_sl_frac:
        _rr = orig_tp_dist / max(orig_sl_dist, 1e-12)
        orig_sl_dist = entry_px * _max_sl_frac
        orig_tp_dist = orig_sl_dist * _rr

    if action == "BUY":
        new_sl = entry_px - orig_sl_dist
        new_tp = entry_px + orig_tp_dist
    else:
        new_sl = entry_px + orig_sl_dist
        new_tp = entry_px - orig_tp_dist

    _sb = float(w.get("sigma_bar", 0.01))
    _td = float(np.clip(CFG.TRAIL_KAPPA * _sb,
                         CFG.TRAIL_MIN_FRAC, CFG.TRAIL_MAX_FRAC))
    _ta = float(np.clip(CFG.TRAIL_ACT_KAPPA * _sb,
                         CFG.TRAIL_ACT_MIN_FRAC, CFG.TRAIL_ACT_MAX_FRAC))
    if _ta <= _td:
        _ta = _td * 1.2

    open_pos_live[sym] = {
        "action": action,
        "entry": entry_px,
        "qty": actual_qty,
        "sl": new_sl,
        "tp1": new_tp,
        "T_info": float(w.get("T_info", 0.0)),
        "dyn_risk": float(w.get("dyn_risk", 0.01)),
        "entry_ts": _t_rev.time(),
        "fill_ratio": actual_qty / max(qty, 1e-9),
        "leverage": int(w["leverage"]),
        "trail_dist_frac": _td,
        "trail_activate_frac": _ta,
        "sl_dist_initial": float(abs(entry_px - new_sl)),
        "mmr": float(w.get("mmr", CFG.LIQ_FALLBACK_MMR)),
        "_entry_ci": 0,
        "_trail_bars_held": 0,
        "_trail_peak_R": 0.0,
        "_trail_last_update_ts": 0.0,
        "_sym": sym,
        "_orig_score": 0.0,
        "stage": "REVERSAL",
    }

    if getattr(CFG, "PROTECTIVE_ORDERS_ENABLED", True):
        try:
            if _place_protective_orders(exchange, sym,
                                          open_pos_live[sym]):
                open_pos_live[sym]["_prot_last_sl"] = float(new_sl)
                open_pos_live[sym]["_prot_last_tp"] = float(new_tp)
        except Exception as e:
            log.warning(f"[LiveRev] prot {sym}: {e}")

    log.info(f"✅ [LiveRev] {action} {sym} @ {entry_px:.6f} "
             f"qty={actual_qty:.6f}/{qty:.6f} sl={new_sl:.6f} "
             f"tp={new_tp:.6f}")
    w["status"] = "FILLED"

'''
        s = s[:start] + NEW_BODY + s[end:]
        report.append("✓ _execute_reversal_fill: hybrid body installed")

# ═══════════════════════════════════════════════════════════════
# 4. _register_reversal_watcher — store physics snapshots
# ═══════════════════════════════════════════════════════════════
OLD_SNAP = '''    sigma_bar = 0.01
    if ad is not None:
        try:
            fi = int(sig.feat_idx)
            if 0 <= fi < len(ad.E_therm):
                _s = float(ad.E_therm[fi])
                if np.isfinite(_s) and _s > 1e-9:
                    sigma_bar = _s
        except Exception:
            pass'''

NEW_SNAP = '''    sigma_bar = 0.01
    friction_v = 0.2
    accel_v = 0.05
    gauge_v = 0.1
    if ad is not None:
        try:
            fi = int(sig.feat_idx)
            if 0 <= fi < len(ad.E_therm):
                _s = float(ad.E_therm[fi])
                if np.isfinite(_s) and _s > 1e-9:
                    sigma_bar = _s
            if 0 <= fi < len(ad.friction):
                friction_v = float(ad.friction[fi])
            if 0 <= fi < len(ad.geodesic_accel):
                accel_v = float(ad.geodesic_accel[fi])
            if 0 <= fi < len(ad.gauge_force):
                gauge_v = float(ad.gauge_force[fi])
        except Exception:
            pass'''
patch(OLD_SNAP, NEW_SNAP,
      "_register_reversal_watcher: extract physics snapshot")

# Store them in the watcher dict — anchor on sigma_bar assignment
OLD_DICT = '        "sigma_bar": float(sigma_bar),'
NEW_DICT = ('        "sigma_bar": float(sigma_bar),\n'
            '        "friction": float(friction_v),\n'
            '        "accel": float(accel_v),\n'
            '        "gauge_force": float(gauge_v),')
patch(OLD_DICT, NEW_DICT,
      "_register_reversal_watcher: store physics fields")

# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
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
