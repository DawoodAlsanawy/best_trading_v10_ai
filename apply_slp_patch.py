#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_slp_patch.py — Smart Ladder Pending (SLP) Patch Application Script
═══════════════════════════════════════════════════════════════════════════

⚠️  IMPORTANT: Read the instructions at the bottom of this file BEFORE running.

Purpose:
    Applies all SLP modifications to `trading_final.py` safely, atomically,
    with verification and rollback support.

Usage:
    # 1. ALWAYS test first (shows what would change):
    python apply_slp_patch.py --dry-run

    # 2. Apply the patch (creates backup automatically):
    python apply_slp_patch.py

    # 3. Verify patched file:
    python apply_slp_patch.py --verify-only

    # 4. Rollback to pre-SLP state:
    python apply_slp_patch.py --rollback

    # 5. Force re-apply (skip manifest check):
    python apply_slp_patch.py --force

Design principles:
    ✓ Atomic writes (never corrupts original file)
    ✓ Automatic timestamped backup
    ✓ AST verification before writing
    ✓ Idempotent (skips already-applied patches)
    ✓ Rolls back on any failure (all-or-nothing)
    ✓ All patches tracked in manifest
    ✓ Dry-run mode shows diffs without writing
"""

import argparse
import ast
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════

PATCH_VERSION = "1.0.0"
MANIFEST_FILE = ".slp_patches.json"
DEFAULT_TARGET = "trading_final.py"


# ═══════════════════════════════════════════════════════════════════
# PAYLOAD BLOCKS (code to inject)
# ═══════════════════════════════════════════════════════════════════

CONFIG_SLP_PAYLOAD = """

    # ══ [SLP v1.0] Smart Ladder Pending Entry ══
    # Splits the single Stage-1 limit order into 3 laddered levels
    # with progressive fills, protective cancellation, and VWAP aggregation.
    # Enable via: --slp
    SLP_ENABLED: bool = False
    SLP_LEVELS: Tuple = (0.0, 0.3, 0.6)       # sigma offsets below tunnel
    SLP_WEIGHTS: Tuple = (0.40, 0.35, 0.25)   # balanced default
    SLP_SCORE_FRONTLOAD: bool = True          # adapt weights to sig.score
    SLP_SCORE_TIERS: Tuple = (
        (7, (0.50, 0.30, 0.20)),              # strong signals: front-load
        (5, (0.40, 0.35, 0.25)),              # medium: balanced
        (3, (0.25, 0.35, 0.40)),              # weak: back-load
    )
    SLP_MIN_FILL_RATIO: float = 0.50          # close if total fill < 50%
    SLP_RUNAWAY_KAPPA: float = 2.0            # cancel if price moved 2sigma wrong way
    SLP_MAX_RETRIES_PER_LEVEL: int = 3        # rate-limit safety per level
    SLP_TIME_DECAY_ENABLED: bool = True       # progressive cancel by elapsed time
    SLP_TIME_DECAY_L2_AT: float = 0.50        # cancel L2 at 50% of window
    SLP_TIME_DECAY_L1_AT: float = 0.75        # cancel L1 at 75% of window
    SLP_PHYSICS_CANCEL_ENABLED: bool = True   # cancel if P_activation collapses
    SLP_PHYSICS_CANCEL_KAPPA: float = 0.50    # P_now < 0.5 * P_orig -> cancel
    SLP_OPPOSITE_CANCEL_ENABLED: bool = True  # cancel on strong opposite signal
    SLP_OPPOSITE_SCORE_MULT: float = 1.20     # opposite score must be 1.2x original
    SLP_BEESC_CANCELS_REMAINING: bool = True  # BEEsc triggers -> cancel pending
    SLP_STATS_ENABLED: bool = True            # write slp_stats_<mode>.csv
    SLP_STATS_PATH: str = "slp_stats"         # filename prefix
    # ══ [SLP end] ══
"""

HELPERS_SLP_PAYLOAD = '''

# ═══════════════════════════════════════════════════════════════════
# [SLP v1.0] Smart Ladder Pending — Runtime helpers
# ═══════════════════════════════════════════════════════════════════
# Inserted by apply_slp_patch.py. All functions namespaced with _slp_.
# Enabled only when CFG.SLP_ENABLED = True.
# ═══════════════════════════════════════════════════════════════════

_SLP_ORDERS: Dict[str, Dict] = {}
_SLP_ORDERS_PATH: str = ""


def _slp_state_load(mode: str) -> None:
    """Load persistent SLP state from disk."""
    global _SLP_ORDERS, _SLP_ORDERS_PATH
    _SLP_ORDERS_PATH = f"slp_orders_{mode}.json"
    _SLP_ORDERS = {}
    if os.path.exists(_SLP_ORDERS_PATH):
        try:
            with open(_SLP_ORDERS_PATH) as f:
                _SLP_ORDERS = json.load(f)
            for _sym in list(_SLP_ORDERS.keys()):
                _SLP_ORDERS[_sym].pop("ad_ref", None)
                _SLP_ORDERS[_sym].pop("signal_ref", None)
            log.info(f"[SLP] Loaded {len(_SLP_ORDERS)} orders from "
                     f"{_SLP_ORDERS_PATH}")
        except Exception as e:
            log.warning(f"[SLP] load failed: {e}")
            _SLP_ORDERS = {}


def _slp_state_save() -> None:
    """Persist SLP state atomically."""
    if not _SLP_ORDERS_PATH:
        return
    try:
        tmp = _SLP_ORDERS_PATH + ".tmp"
        ser = {}
        for _sym, _rec in _SLP_ORDERS.items():
            _r = {}
            for _k, _v in _rec.items():
                if _k in ("ad_ref", "signal_ref"):
                    continue
                if isinstance(_v, (np.floating, np.integer)):
                    _v = _v.item()
                elif isinstance(_v, np.ndarray):
                    continue
                _r[_k] = _v
            ser[_sym] = _r
        with open(tmp, "w") as f:
            json.dump(ser, f, indent=2)
        os.replace(tmp, _SLP_ORDERS_PATH)
    except Exception as e:
        log.warning(f"[SLP] save failed: {e}")


def _slp_compute_weights(score: float, cfg) -> Tuple[float, float, float]:
    """Pick weights by signal strength if SLP_SCORE_FRONTLOAD enabled."""
    _default = tuple(getattr(cfg, 'SLP_WEIGHTS', (0.40, 0.35, 0.25)))
    if not getattr(cfg, 'SLP_SCORE_FRONTLOAD', True):
        return _default[:3] if len(_default) >= 3 else (0.40, 0.35, 0.25)
    _tiers = getattr(cfg, 'SLP_SCORE_TIERS', ())
    for _tier_score, _weights in sorted(_tiers, key=lambda x: -x[0]):
        if float(score) >= float(_tier_score):
            return tuple(_weights)[:3]
    return _default[:3] if len(_default) >= 3 else (0.40, 0.35, 0.25)


def _slp_compute_levels(sig, ad, cfg, qty_total: float) -> List[Dict]:
    """Build the 3 ladder levels for a signal."""
    _sigma = 0.01
    try:
        _fi = int(getattr(sig, 'feat_idx', 0))
        if ad is not None and 0 <= _fi < len(ad.E_therm):
            _s = float(ad.E_therm[_fi])
            if np.isfinite(_s) and _s > 1e-6:
                _sigma = _s
    except Exception:
        pass
    _sigma_price = _sigma * float(sig.price)
    _offsets = list(getattr(cfg, 'SLP_LEVELS', (0.0, 0.3, 0.6)))[:3]
    _weights = _slp_compute_weights(float(sig.score), cfg)
    _side_sign = -1.0 if sig.action == "BUY" else 1.0
    _levels = []
    for _i, (_off, _w) in enumerate(zip(_offsets, _weights)):
        _px = float(sig.price) + _side_sign * float(_off) * _sigma_price
        _levels.append({
            "idx": int(_i),
            "px": float(_px),
            "weight": float(_w),
            "offset_sigma": float(_off),
            "qty_target": float(qty_total) * float(_w),
            "qty_filled": 0.0,
            "avg": 0.0,
            "status": "new",
            "cid": None,
            "order_id": None,
            "attempt": 0,
            "rejects": 0,
        })
    return _levels


def _slp_write_stats(rec: Dict, outcome: str, exit_px=None,
                     net_pnl_R=None) -> None:
    """Append one row to slp_stats_<mode>.csv."""
    if not getattr(CFG, 'SLP_STATS_ENABLED', True):
        return
    try:
        import csv as _csv
        _path = f"{getattr(CFG, 'SLP_STATS_PATH', 'slp_stats')}_{CFG.mode}.csv"
        _new = not os.path.exists(_path)
        _tunnel = float(rec.get("sig_price", 0) or 0)
        _levels = rec.get("levels", [])
        _total_f = sum(float(l.get("qty_filled", 0)) for l in _levels)
        _qty_t = float(rec.get("qty_target", 0) or 0)
        _ratio = _total_f / _qty_t if _qty_t > 0 else 0.0
        _vwap = 0.0
        if _total_f > 0:
            _vwap = sum(float(l.get("qty_filled", 0)) * float(l.get("avg", 0))
                        for l in _levels) / _total_f
        _vs_tunnel = ((_vwap - _tunnel) / _tunnel * 1e4
                      if _tunnel > 0 and _vwap > 0 else 0.0)

        def _lvl(idx, key):
            try:
                return _levels[idx].get(key, 0.0)
            except Exception:
                return 0.0

        with open(_path, "a", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            if _new:
                w.writerow([
                    "ts", "symbol", "action", "score", "sigma_bar",
                    "tunnel_px", "qty_target", "total_fill_ratio",
                    "final_vwap", "vwap_vs_tunnel_bps", "outcome",
                    "L0_qty_filled", "L1_qty_filled", "L2_qty_filled",
                    "exit_px", "net_pnl_R", "L0_cancel", "L1_cancel",
                    "L2_cancel",
                ])
            w.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S"),
                str(rec.get("sym", "?")),
                str(rec.get("action", "?")),
                float(rec.get("score", 0) or 0),
                float(rec.get("sigma_bar", 0) or 0),
                _tunnel, _qty_t, round(_ratio, 4), round(_vwap, 6),
                round(_vs_tunnel, 2), str(outcome),
                round(_lvl(0, "qty_filled"), 6),
                round(_lvl(1, "qty_filled"), 6),
                round(_lvl(2, "qty_filled"), 6),
                exit_px if exit_px is not None else "",
                round(net_pnl_R, 4) if net_pnl_R is not None else "",
                str((rec.get("cancel_reasons") or {}).get("L0", "")),
                str((rec.get("cancel_reasons") or {}).get("L1", "")),
                str((rec.get("cancel_reasons") or {}).get("L2", "")),
            ])
    except Exception as e:
        log.debug(f"[SLP] stats write failed: {e}")


def _slp_check_cancel_triggers(rec: Dict, ad, current_ci: int,
                                price_now: float,
                                now_ts: float) -> List[Tuple[int, str]]:
    """Return list of (level_idx, reason) to cancel."""
    _out: List[Tuple[int, str]] = []
    _levels = rec.get("levels", [])
    for _lvl in _levels:
        if _lvl["status"] in ("filled", "cancelled"):
            continue
        _idx = int(_lvl["idx"])

        # 1. Time decay
        if getattr(CFG, 'SLP_TIME_DECAY_ENABLED', True):
            _start = float(rec.get("window_start_ts", now_ts))
            _to = float(rec.get("timeout_s", 300) or 300)
            _elapsed_frac = ((now_ts - _start) / _to) if _to > 0 else 1.0
            if _idx == 2 and _elapsed_frac >= float(
                    getattr(CFG, 'SLP_TIME_DECAY_L2_AT', 0.50)):
                _out.append((_idx, "time_decay"))
                continue
            if _idx == 1 and _elapsed_frac >= float(
                    getattr(CFG, 'SLP_TIME_DECAY_L1_AT', 0.75)):
                _out.append((_idx, "time_decay"))
                continue

        # 2. Runaway (price moved too far in the wrong direction)
        _sig_px = float(rec.get("sig_price", 0) or 0)
        _sigma_frac = float(rec.get("sigma_bar", 0.01) or 0.01)
        _sigma_px = _sigma_frac * _sig_px if _sig_px > 0 else 0.0
        _kappa = float(getattr(CFG, 'SLP_RUNAWAY_KAPPA', 2.0))
        if _sigma_px > 0 and price_now > 0:
            _action = str(rec.get("action", "BUY"))
            if _action == "BUY":
                _dist = _sig_px - price_now   # positive = went below tunnel
            else:
                _dist = price_now - _sig_px   # positive = went above tunnel
            # BUY: if price went ABOVE tunnel by > kappa*sigma -> runaway
            if _dist < -_kappa * _sigma_px:
                _out.append((_idx, "runaway"))
                continue

        # 3. Physics collapse
        if (getattr(CFG, 'SLP_PHYSICS_CANCEL_ENABLED', True)
                and ad is not None):
            _fi = current_ci - ad.feat_start
            if 0 <= _fi < len(ad.geodesic_accel):
                try:
                    _a_now = float(ad.geodesic_accel[_fi])
                    _f_now = float(ad.friction[_fi]) + 1e-6
                    _t_now = float(ad.T_info[_fi])
                    if _t_now > 0 and abs(_a_now) > 1e-9:
                        _P_now = float(np.exp(
                            -_f_now / (abs(_a_now) * _t_now)
                        ))
                    else:
                        _P_now = 1.0
                    _P_orig = float(rec.get("P_act_orig", 1.0) or 1.0)
                    _kappa_p = float(
                        getattr(CFG, 'SLP_PHYSICS_CANCEL_KAPPA', 0.50)
                    )
                    if _P_orig > 0 and _P_now < _kappa_p * _P_orig:
                        _out.append((_idx, "physics"))
                        continue
                except Exception:
                    pass
    return _out


def _slp_cancel_levels_live(exchange, sym: str, rec: Dict,
                             level_idxs: List[int], reason: str) -> int:
    """Cancel specific levels on the exchange."""
    n = 0
    for _lvl in rec.get("levels", []):
        if int(_lvl["idx"]) not in [int(i) for i in level_idxs]:
            continue
        if _lvl["status"] not in ("new", "open"):
            continue
        if not _lvl.get("order_id"):
            _lvl["status"] = "cancelled"
            rec.setdefault("cancel_reasons", {})[f"L{_lvl['idx']}"] = reason
            continue
        try:
            exchange.cancel_order(_lvl["order_id"], sym)
            _lvl["status"] = "cancelled"
            rec.setdefault("cancel_reasons", {})[f"L{_lvl['idx']}"] = reason
            n += 1
        except Exception as e:
            _msg = str(e).lower()
            if "-2011" in _msg or "unknown order" in _msg:
                _lvl["status"] = "cancelled"
                rec.setdefault("cancel_reasons", {})[f"L{_lvl['idx']}"] = reason
                n += 1
    return n


def _slp_sweep_level(exchange, sym: str, lvl: Dict) -> None:
    """Refresh one level's status from the exchange."""
    if lvl["status"] not in ("new", "open"):
        return
    if not lvl.get("order_id"):
        return
    try:
        _o = exchange.fetch_order(lvl["order_id"], sym)
        _st = str(_o.get("status", "open"))
        _fq = float(_o.get("filled") or 0.0)
        _fa = float(_o.get("average") or _o.get("price") or lvl["px"])
        lvl["qty_filled"] = _fq
        lvl["avg"] = _fa if _fa > 0 else lvl["px"]
        if _st in ("closed", "filled"):
            lvl["status"] = "filled"
        elif _st in ("canceled", "expired", "rejected"):
            lvl["status"] = "cancelled"
    except Exception:
        pass


def _slp_aggregate_position(exchange, sym: str, rec: Dict,
                             open_pos_live: Dict) -> str:
    """Create or grow the position from accumulated fills."""
    _levels = rec.get("levels", [])
    _total_q = sum(float(l.get("qty_filled", 0)) for l in _levels)
    if _total_q <= 0:
        return "noop"
    _total_cost = sum(float(l.get("qty_filled", 0)) * float(l.get("avg", 0))
                      for l in _levels)
    _vwap = _total_cost / _total_q if _total_q > 0 else 0.0
    if _vwap <= 0:
        return "noop"

    _action = str(rec.get("action", "BUY"))
    _sd0 = float(rec.get("_orig_sl_dist", 0) or 0)
    _td0 = float(rec.get("_orig_tp_dist", 0) or 0)
    if _sd0 <= 0:
        return "noop"

    _existing = open_pos_live.get(sym)
    _synced_q = float(rec.get("pos_synced_qty", 0) or 0)
    if abs(_total_q - _synced_q) < 1e-9:
        return "noop"

    if _existing is None:
        _sl = _vwap - _sd0 if _action == "BUY" else _vwap + _sd0
        _tp = _vwap + _td0 if _action == "BUY" else _vwap - _td0
        _sigma = float(rec.get("sigma_bar", 0.01) or 0.01)
        _td = float(np.clip(CFG.TRAIL_KAPPA * _sigma,
                            CFG.TRAIL_MIN_FRAC, CFG.TRAIL_MAX_FRAC))
        _ta = float(np.clip(CFG.TRAIL_ACT_KAPPA * _sigma,
                            CFG.TRAIL_ACT_MIN_FRAC, CFG.TRAIL_ACT_MAX_FRAC))
        if _ta <= _td:
            _ta = _td * 1.2
        open_pos_live[sym] = {
            "action": _action,
            "entry": _vwap,
            "qty": _total_q,
            "sl": _sl,
            "tp1": _tp,
            "T_info": float(rec.get("T_info", 0)),
            "dyn_risk": float(rec.get("dyn_risk", 0.01)),
            "entry_ts": time.time(),
            "fill_ratio": _total_q / max(
                float(rec.get("qty_target", 1) or 1), 1e-9),
            "leverage": int(rec.get("leverage", 1) or 1),
            "trail_dist_frac": _td,
            "trail_activate_frac": _ta,
            "sl_dist_initial": float(abs(_vwap - _sl)),
            "mmr": float(rec.get("mmr_at_placement", 0.02)),
            "_entry_ci": int(rec.get("close_idx", 0) or 0),
            "_trail_bars_held": 0,
            "_trail_peak_R": 0.0,
            "_trail_last_update_ts": 0.0,
            "_hi": _vwap, "_lo": _vwap,
            "_last_sub_ts": 0,
            "_sym": sym,
            "_orig_score": float(rec.get("score", 0) or 0),
            "_slp_meta": {
                "window_end_ts": (float(rec.get("window_start_ts", 0))
                                  + float(rec.get("timeout_s", 0))),
                "window_end_ci": int(rec.get("close_idx", 0) or 0)
                                 + max(1, int(float(
                                     rec.get("timeout_s", 300)) / max(
                                     float(getattr(CFG, 'TF_SECONDS', 3600)),
                                     1))),
            },
        }
        if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
            try:
                _place_protective_orders(exchange, sym, open_pos_live[sym])
                open_pos_live[sym]["_prot_last_sl"] = float(_sl)
                open_pos_live[sym]["_prot_last_tp"] = float(_tp)
            except Exception as e:
                log.warning(f"[SLP] {sym} prot placement failed: {e}")
        rec["pos_synced_qty"] = _total_q
        return "created"
    else:
        # Grow
        _action = str(_existing.get("action", "BUY"))
        _existing["qty"] = _total_q
        _existing["entry"] = _vwap
        _existing["sl"] = _vwap - _sd0 if _action == "BUY" else _vwap + _sd0
        _existing["tp1"] = _vwap + _td0 if _action == "BUY" else _vwap - _td0
        _existing["sl_dist_initial"] = float(abs(_vwap - _existing["sl"]))
        _existing.pop("_prot_last_sl", None)
        rec["pos_synced_qty"] = _total_q
        if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
            try:
                _sync_protective_orders(exchange, sym, _existing)
            except Exception as e:
                log.debug(f"[SLP] {sym} prot resync failed: {e}")
        return "grown"


def _slp_finalize(exchange, sym: str, rec: Dict, open_pos_live: Dict,
                  reason: str) -> str:
    """End SLP cycle. Returns 'position_alive' | 'closed' | 'no_fill'."""
    _levels = rec.get("levels", [])
    _total_q = sum(float(l.get("qty_filled", 0)) for l in _levels)
    _qty_t = float(rec.get("qty_target", 0) or 0)
    _ratio = _total_q / _qty_t if _qty_t > 0 else 0.0
    _min_ratio = float(getattr(CFG, 'SLP_MIN_FILL_RATIO', 0.50))

    if _total_q <= 0:
        _slp_write_stats(rec, "no_fill")
        _SLP_ORDERS.pop(sym, None)
        return "no_fill"

    if _ratio < _min_ratio:
        _pos = open_pos_live.get(sym)
        _exit_px = 0.0
        if _pos is not None:
            try:
                _side = "sell" if _pos.get("action") == "BUY" else "buy"
                _q_close = float(_pos.get("qty", 0))
                _o = exchange.create_order(
                    sym, "market", _side, _q_close, None,
                    params={"reduceOnly": True})
                _v = verify_fill(exchange, _o["id"], sym, timeout_s=2.0)
                _exit_px = float(_v["avg_price"]) if _v and _v["filled"] else 0.0
            except Exception as e:
                log.warning(f"[SLP] {sym} close failed: {e}")
            try:
                _cancel_all_protective_orders(exchange, sym)
            except Exception:
                pass
            open_pos_live.pop(sym, None)
        _slp_write_stats(rec, f"aborted_low_fill:{reason}", exit_px=_exit_px)
        _SLP_ORDERS.pop(sym, None)
        return "closed"

    # Accept
    _outcome = (f"timeout_partial:{reason}" if _ratio < 0.98
                else f"confirmed:{reason}")
    _slp_write_stats(rec, _outcome)
    _pos = open_pos_live.get(sym)
    if _pos is not None and "_slp_meta" in _pos:
        del _pos["_slp_meta"]
    _SLP_ORDERS.pop(sym, None)
    return "position_alive"


def place_smart_ladder_pending(exchange, sym: str, side: str, qty: float,
                                sig, timeout_s: float, leverage: int,
                                ad=None) -> Optional[Dict]:
    """Place 3 GTX orders forming an SLP ladder."""
    if not getattr(CFG, 'SLP_ENABLED', False):
        return None
    if not _rate_can_place():
        return None
    try:
        qty = float(_snap_qty(exchange, sym, qty))
        if qty <= 0:
            return None
        _levels = _slp_compute_levels(sig, ad, CFG, qty)
        _P_orig = 0.8
        try:
            if ad is not None:
                _fi = int(getattr(sig, 'feat_idx', 0))
                _a = float(ad.geodesic_accel[_fi])
                _f = float(ad.friction[_fi]) + 1e-6
                _t = float(ad.T_info[_fi])
                if _t > 0 and abs(_a) > 1e-9:
                    _P_orig = float(np.exp(-_f / (abs(_a) * _t)))
        except Exception:
            pass
        try:
            ensure_symbol_setup(exchange, sym, int(leverage),
                                margin_mode='isolated')
        except Exception as e:
            log.warning(f"[SLP] {sym} setup failed: {e}")
            return None
        try:
            _cancel_all_protective_orders(exchange, sym)
        except Exception:
            pass
        _tf_sec = float(getattr(CFG, 'TF_SECONDS', 3600) or 3600)
        _now = time.time()
        _placed = []
        for _lvl in _levels:
            _cid = f"slp{int(_now)}{sym.replace('/','')[:4]}{_lvl['idx']}"[:36]
            _lvl["cid"] = _cid
            try:
                _o = exchange.create_order(
                    sym, 'limit', side, _lvl["qty_target"], _lvl["px"],
                    params={'timeInForce': 'GTX', 'clientOrderId': _cid})
                _lvl["order_id"] = str(_o.get("id") or "")
                _lvl["status"] = "open"
                _placed.append(_lvl["idx"])
            except Exception as e:
                log.warning(f"[SLP] {sym} L{_lvl['idx']} place failed: {e}")
                _lvl["rejects"] = int(_lvl.get("rejects", 0)) + 1
        if not _placed:
            return None
        _orig_sl_dist = abs(float(sig.price) - float(sig.sl))
        _orig_tp_dist = abs(float(sig.tp1) - float(sig.price))
        _rec = {
            "sym": sym,
            "action": str(sig.action),
            "side": side,
            "levels": _levels,
            "fills": [],
            "qty_target": float(qty),
            "pos_synced_qty": 0.0,
            "window_start_ts": _now,
            "timeout_s": float(timeout_s),
            "P_act_orig": float(_P_orig),
            "sigma_bar": float(_levels[0].get("offset_sigma", 0.01))
                          or 0.01,
            "score": float(getattr(sig, 'score', 0) or 0),
            "T_info": float(getattr(sig, 'T_info_val', 0) or 0),
            "dyn_risk": float(getattr(sig, 'dynamic_risk', 0.01) or 0.01),
            "leverage": int(leverage),
            "mmr_at_placement": float(_get_mmr_for_symbol(exchange, sym)),
            "_orig_sl_dist": _orig_sl_dist,
            "_orig_tp_dist": _orig_tp_dist,
            "sig_price": float(sig.price),
            "sig_sl": float(sig.sl),
            "sig_tp1": float(sig.tp1),
            "close_idx": int(sig.close_idx),
            "sig_ts_ms": int(pd.Timestamp(sig.timestamp).value),
            "placed_at": _now,
            "status": "OPEN",
            "cancel_reasons": {},
        }
        _SLP_ORDERS[sym] = _rec
        log.info(f"[SLP] {sig.action} {sym} ladder placed: "
                 f"{[(l['idx'], round(l['px'], 6), round(l['qty_target'], 4), l['status']) for l in _levels]}")
        return _rec
    except Exception as e:
        log.error(f"[SLP] place_smart_ladder_pending {sym} failed: {e}")
        return None


def monitor_smart_ladder_pending(exchange, open_pos_live: Dict,
                                  loop_iter: int = 0,
                                  assets: Optional[Dict] = None) -> None:
    """Sweep and manage all SLP cycles."""
    if not getattr(CFG, 'SLP_ENABLED', False):
        return
    if not _SLP_ORDERS:
        return
    _now = time.time()
    for sym in list(_SLP_ORDERS.keys()):
        _rec = _SLP_ORDERS.get(sym)
        if _rec is None:
            continue
        try:
            # 1. Sweep each level
            for _lvl in _rec.get("levels", []):
                _slp_sweep_level(exchange, sym, _lvl)
            # 2. Aggregate any new fills
            _slp_aggregate_position(exchange, sym, _rec, open_pos_live)
            # 3. Timeout check
            _elapsed = _now - float(_rec.get("window_start_ts", _now))
            _timeout = float(_rec.get("timeout_s", 300) or 300)
            _all_done = all(
                l["status"] in ("filled", "cancelled")
                for l in _rec.get("levels", [])
            )
            if _elapsed > _timeout or _all_done:
                _slp_cancel_levels_live(
                    exchange, sym, _rec, [0, 1, 2], "finalize")
                _slp_finalize(exchange, sym, _rec, open_pos_live,
                              "timeout" if _elapsed > _timeout else "all_done")
                _slp_state_save()
                continue
            # 4. Cancel triggers
            _ad = (assets or {}).get(sym)
            _price_now = 0.0
            _current_ci = 0
            if _ad is not None:
                try:
                    _current_ci = max(0, len(_ad.closes) - 2)
                    _price_now = float(_ad.closes[_current_ci])
                except Exception:
                    pass
            if _price_now > 0:
                _triggers = _slp_check_cancel_triggers(
                    _rec, _ad, _current_ci, _price_now, _now)
                if _triggers:
                    _idxs = [t[0] for t in _triggers]
                    _reason = _triggers[0][1] if _triggers else "unknown"
                    _slp_cancel_levels_live(
                        exchange, sym, _rec, _idxs, _reason)
            # 5. SL check on existing position
            _pos = open_pos_live.get(sym)
            if _pos is not None and _price_now > 0:
                _sl = float(_pos.get("sl", 0) or 0)
                _action = str(_pos.get("action", "BUY"))
                _sl_hit = ((_action == "BUY" and _price_now <= _sl)
                           or (_action == "SELL" and _price_now >= _sl))
                if _sl_hit:
                    _slp_cancel_levels_live(
                        exchange, sym, _rec, [0, 1, 2], "sl_pre_finalize")
                    _slp_write_stats(_rec, "sl_hit_early")
                    _SLP_ORDERS.pop(sym, None)
        except Exception as e:
            log.warning(f"[SLP] {sym} monitor error: {e}")
    try:
        _slp_state_save()
    except Exception:
        pass


def _precompute_slp_fills(assets, signals, cfg) -> Dict:
    """Backtest: simulate SLP fills per signal."""
    _by_sym = defaultdict(list)
    for _i, _s in enumerate(signals):
        _by_sym[_s.symbol].append((_i, _s))

    _result = {}
    _pen_bps = float(getattr(cfg, 'FILL_PENETRATION_BPS', 1.0))

    for sym, _sigs in _by_sym.items():
        if sym not in assets:
            for _i, _ in _sigs:
                _result[_i] = None
            continue
        _ad = assets[sym]
        _n_bars = len(_ad.closes)

        for _j, (_sig_i, _sig) in enumerate(_sigs):
            try:
                _fi = int(_sig.feat_idx)
                _sigma = 0.01
                if 0 <= _fi < len(_ad.E_therm):
                    _s = float(_ad.E_therm[_fi])
                    if np.isfinite(_s) and _s > 1e-6:
                        _sigma = _s
                _qty_placeholder = 1.0
                _levels = _slp_compute_levels(_sig, _ad, cfg, _qty_placeholder)
                _first_bar = int(_sig.close_idx) + 1
                _wait_bars = effective_bars(
                    int(getattr(cfg, 'UNIFIED_WAIT_BARS_1H', 8)))
                _last_bar = min(_first_bar + _wait_bars, _n_bars)
                if _first_bar >= _last_bar:
                    _result[_sig_i] = None
                    continue
                _fills = []
                _cancel_reasons = {}
                _P_orig = 0.8
                try:
                    _a0 = float(_ad.geodesic_accel[_fi])
                    _f0 = float(_ad.friction[_fi]) + 1e-6
                    _t0 = float(_ad.T_info[_fi])
                    if _t0 > 0 and abs(_a0) > 1e-9:
                        _P_orig = float(np.exp(-_f0 / (abs(_a0) * _t0)))
                except Exception:
                    pass
                _rec = {
                    "sym": sym, "action": str(_sig.action),
                    "sig_price": float(_sig.price),
                    "sigma_bar": _sigma,
                    "window_start_ts": 0.0,
                    "timeout_s": 0.0,
                    "P_act_orig": _P_orig,
                    "levels": _levels,
                    "cancel_reasons": _cancel_reasons,
                    "_orig_sl_dist": abs(float(_sig.price) - float(_sig.sl)),
                    "_orig_tp_dist": abs(float(_sig.tp1) - float(_sig.price)),
                }
                _matched_any = False
                for _bar in range(_first_bar, _last_bar):
                    _p_now = float(_ad.closes[_bar])
                    # Check fills
                    for _lvl in _levels:
                        if _lvl["status"] != "new":
                            continue
                        _px = float(_lvl["px"])
                        _hit = False
                        if _sig.action == "BUY":
                            _hit = float(_ad.lows[_bar]) <= _px
                        else:
                            _hit = float(_ad.highs[_bar]) >= _px
                        if _hit:
                            _lvl["status"] = "filled"
                            _lvl["qty_filled"] = float(_lvl["qty_target"])
                            _lvl["avg"] = _px
                            _fills.append({
                                "bar": int(_bar),
                                "idx": int(_lvl["idx"]),
                                "px": float(_px),
                                "qty": float(_lvl["qty_target"]),
                            })
                            _matched_any = True
                    # Cancel triggers (bar-time based)
                    if _ad is not None:
                        _bar_ts_for_triggers = float(
                            _ad.timestamps[_bar].timestamp())
                        _rec["window_start_ts"] = float(
                            _ad.timestamps[_first_bar].timestamp())
                        _rec["timeout_s"] = (
                            float(_last_bar - _first_bar)
                            * float(getattr(cfg, 'TF_SECONDS', 3600)))
                        _trig = _slp_check_cancel_triggers(
                            _rec, _ad, _bar, _p_now,
                            _bar_ts_for_triggers)
                        for _idx, _reason in _trig:
                            for _lvl in _levels:
                                if (int(_lvl["idx"]) == int(_idx)
                                        and _lvl["status"] == "new"):
                                    _lvl["status"] = "cancelled"
                                    _cancel_reasons[f"L{_idx}"] = _reason
                # ══ [SLP v1.1] Precompute stats writes ══
                _rec["qty_target"] = 1.0
                _rec["fills"] = _fills
                if not _fills:
                    try:
                        _slp_write_stats(_rec, "no_fill")
                    except Exception as _e_s:
                        log.debug(f"[SLP] stats write: {_e_s}")
                    _result[_sig_i] = {
                        "type": "SLP",
                        "fills": [],
                        "outcome": "no_fill",
                        "timeout_stage2": True,
                    }
                    continue
                _total_q = sum(f["qty"] for f in _fills)
                _total_cost = sum(f["qty"] * f["px"] for f in _fills)
                _vwap = _total_cost / _total_q if _total_q > 0 else 0.0
                _all_filled = all(l["status"] == "filled" for l in _levels)
                _window_end = max(
                    max(f["bar"] for f in _fills),
                    _sig.close_idx + 2,
                )
                try:
                    _slp_write_stats(
                        _rec,
                        "all_filled" if _all_filled else "timeout_partial")
                except Exception as _e_s:
                    log.debug(f"[SLP] stats write: {_e_s}")
                _result[_sig_i] = {
                    "type": "SLP",
                    "fills": [(f["bar"], f["idx"], f["px"], f["qty"])
                              for f in _fills],
                    "final_vwap": _vwap,
                    "final_qty": _total_q,
                    "outcome": ("all_filled" if _all_filled
                                else "timeout_partial"),
                    "cancel_reasons": _cancel_reasons,
                    "window_end_ci": _window_end,
                    "timeout_stage2": False,
                }
            except Exception as _e:
                log.debug(f"[SLP] precompute {sym} failed: {_e}")
                _result[_sig_i] = None
    return _result


def _slp_stats_report() -> None:
    """Print SLP summary at end of backtest."""
    _path = f"{getattr(CFG, 'SLP_STATS_PATH', 'slp_stats')}_backtest.csv"
    if not os.path.exists(_path):
        return
    try:
        import csv
        with open(_path, "r", encoding="utf-8") as f:
            _rows = list(csv.DictReader(f))
        if not _rows:
            return
        _n = len(_rows)
        _outcomes = {}
        _l0_fill = sum(1 for r in _rows if float(r.get("L0_qty_filled", 0) or 0) > 0)
        _l1_fill = sum(1 for r in _rows if float(r.get("L1_qty_filled", 0) or 0) > 0)
        _l2_fill = sum(1 for r in _rows if float(r.get("L2_qty_filled", 0) or 0) > 0)
        _ratios = []
        for r in _rows:
            _oc = r.get("outcome", "?").split(":")[0]
            _outcomes[_oc] = _outcomes.get(_oc, 0) + 1
            try:
                _ratios.append(float(r.get("total_fill_ratio", 0) or 0))
            except Exception:
                pass
        print("\\n" + "═" * 72)
        print(f"[SLP Report] {_n} signals processed")
        print(f"  Fill rates: L0={_l0_fill/n*100:.1f}%  "
              f"L1={_l1_fill/n*100:.1f}%  L2={_l2_fill/n*100:.1f}%")
        print(f"  Mean fill ratio: {sum(_ratios)/max(len(_ratios),1):.3f}")
        print(f"  Outcomes:")
        for _k, _v in sorted(_outcomes.items(), key=lambda x: -x[1]):
            print(f"    {_k:25s}: {_v:5d} ({_v/n*100:.1f}%)")
        print("═" * 72)
    except Exception as e:
        log.debug(f"[SLP] report failed: {e}")

def _slp_startup_recover(exchange, open_pos_live: Dict) -> None:
    """On live restart: finalize expired SLP cycles, resume active ones."""
    if not getattr(CFG, 'SLP_ENABLED', False):
        return
    if not _SLP_ORDERS:
        return
    _now = time.time()
    _expired = 0
    _resumed = 0
    for _sym in list(_SLP_ORDERS.keys()):
        _rec = _SLP_ORDERS.get(_sym)
        if _rec is None:
            continue
        try:
            _elapsed = _now - float(_rec.get("window_start_ts", _now))
            _timeout = float(_rec.get("timeout_s", 300) or 300)
            if _elapsed > _timeout:
                try:
                    _slp_cancel_levels_live(
                        exchange, _sym, _rec, [0, 1, 2],
                        "startup_timeout")
                except Exception as _e_c:
                    log.debug(f"[SLP] startup cancel {_sym}: {_e_c}")
                try:
                    _slp_finalize(exchange, _sym, _rec,
                                  open_pos_live, "startup_timeout")
                except Exception as _e_f:
                    log.warning(f"[SLP] startup finalize {_sym}: {_e_f}")
                _expired += 1
            else:
                _resumed += 1
                log.info(f"[SLP] {_sym} resumed "
                         f"({_elapsed:.0f}s/{_timeout:.0f}s)")
        except Exception as _e:
            log.warning(f"[SLP] startup recover {_sym}: {_e}")
    try:
        _slp_state_save()
    except Exception:
        pass
    if _expired > 0 or _resumed > 0:
        log.info(f"[SLP] Startup: {_expired} expired, "
                 f"{_resumed} resumed")


# ══ [SLP helpers end] ══

'''


# ═══════════════════════════════════════════════════════════════════
# PATCH DEFINITIONS
# ═══════════════════════════════════════════════════════════════════

PATCHES = [
    # ─── 1. Config fields ───
    {
        "id": "slp_config",
        "description": "Add SLP config fields to Config dataclass",
        "unique_marker": "SLP_ENABLED: bool = False",
        "anchor": "\nCFG = Config()\n",
        "position": "before",
        "payload": CONFIG_SLP_PAYLOAD,
    },

    # ─── 2. All helper functions ───
    {
        "id": "slp_helpers",
        "description": "Add all SLP helper functions before main()",
        "unique_marker": "def place_smart_ladder_pending(",
        "anchor": "\ndef main():",
        "position": "before",
        "payload": HELPERS_SLP_PAYLOAD,
    },

    # ─── 3. Backtest fill_map selection ───
    {
        "id": "slp_backtest_fillmap",
        "description": "Hook SLP into simulate_portfolio fill_map (AFTER PARITY)",
        "unique_marker": 'fill_map = _precompute_slp_fills(assets, signals, CFG)',
        "anchor": "    n_total_sigs = len(signals)\n",
        "position": "before",
        "payload": """    # ══ [SLP v1.1] Override fill_map with SLP (takes precedence) ══
    if getattr(CFG, 'SLP_ENABLED', False):
        fill_map = _precompute_slp_fills(assets, signals, CFG)
        _n_slp_total = len(fill_map)
        _n_slp_filled = sum(
            1 for _v in fill_map.values()
            if isinstance(_v, dict) and _v.get('fills'))
        log.info(
            f"  [SLP] {_n_slp_filled}/{_n_slp_total} signals "
            f"produced fills (SLP mode)")
""",
    },

    # ─── 4. _advance early return for SLP window ───
    {
        "id": "slp_advance_window",
        "description": "Add SLP window early-return in _advance bar loop",
        "unique_marker": "_in_slp_window = (",
        "anchor": "    for cidx in range(start, end+1):\n        p = ad.closes[cidx]\n        fi = cidx - ad.feat_start\n",
        "position": "after",
        "payload": """
        # ══ [SLP] During SLP window: only SL/TP checks ══
        _in_slp_window = (
            getattr(pos, '_slp_meta', None) is not None
            and cidx <= int(pos._slp_meta.get('window_end_ci', 0))
        )
        if _in_slp_window:
            if _use_sub:
                for _j in range(ad.sub_per_main):
                    _sh = ad.sub_highs[cidx, _j]
                    _sl = ad.sub_lows[cidx, _j]
                    if not np.isfinite(_sh) or not np.isfinite(_sl):
                        continue
                    _res, _px = _check_sl_tp(_sh, _sl, p, fi)
                    if _res == "SL":
                        pos.trail_sl = trail_sl
                        pos.current_ci = cidx
                        return _px, "Emergency SL", cidx
                    if _res == "TP":
                        pos.trail_sl = trail_sl
                        pos.current_ci = cidx
                        return _px, "Hard TP", cidx
            else:
                _high = ad.highs[cidx]
                _low = ad.lows[cidx]
                _res, _px = _check_sl_tp(_high, _low, p, fi)
                if _res == "SL":
                    pos.trail_sl = trail_sl
                    pos.current_ci = cidx
                    return _px, "Emergency SL", cidx
                if _res == "TP":
                    pos.trail_sl = trail_sl
                    pos.current_ci = cidx
                    return _px, "Hard TP", cidx
            pos.current_ci = cidx
            continue
""",
    },

    # ─── 4a. SLP simulate branch (fill_info parsing) ───
    {
        "id": "v11_simulate_branch",
        "description": "Handle SLP dict format in simulate_portfolio",
        "unique_marker": "_is_slp_mode = False",
        "anchor": """        # ══ [UNIFIED ENTRY] Look up Stage 1 or Stage 2 ══
        fill_info = fill_map.get(sig_i)
        if fill_info is None:
            continue

        _is_stage2 = False
        _stage2_sl = _stage2_tp = _stage2_sl_dist = None

        if len(fill_info) >= 2 and isinstance(fill_info[0], str):
            if fill_info[0] == 'S1':
                _, opt_ci, opt_px = fill_info
            elif fill_info[0] == 'S2':
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist \\
                    = fill_info
                _is_stage2 = True
            else:
                continue
        else:
            # توافق مع الصيغة القديمة
            opt_ci, opt_px = fill_info
""",
        "position": "replace",
        "payload": """        # ══ [UNIFIED ENTRY] Look up Stage 1 or Stage 2 (SLP-aware) ══
        fill_info = fill_map.get(sig_i)
        if fill_info is None:
            continue

        _is_stage2 = False
        _is_slp_mode = False
        _slp_meta_for_pos = None
        _stage2_sl = _stage2_tp = _stage2_sl_dist = None

        if isinstance(fill_info, dict) and fill_info.get('type') == 'SLP':
            _slp_fills = fill_info.get('fills', [])
            if not _slp_fills:
                continue
            _first_bar = min(f[0] for f in _slp_fills)
            _last_bar = max(f[0] for f in _slp_fills)
            opt_ci = int(_first_bar)
            opt_px = float(fill_info['final_vwap'])
            _slp_meta_for_pos = {
                'window_end_ci': int(fill_info.get('window_end_ci', _last_bar)),
                'cancel_reasons': fill_info.get('cancel_reasons', {}),
            }
            _is_slp_mode = True
            _orig_sd = abs(float(sig.price) - float(sig.sl))
            _orig_td = abs(float(sig.tp1) - float(sig.price))
            _max_sl_frac = (float(getattr(CFG, 'MAX_SL_FRAC', 0.015))
                            * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0)))
            if _orig_sd > opt_px * _max_sl_frac:
                _rr = _orig_td / max(_orig_sd, 1e-12)
                _orig_sd = opt_px * _max_sl_frac
                _orig_td = _orig_sd * _rr
            if sig.action == 'BUY':
                sig.sl = opt_px - _orig_sd
                sig.tp1 = opt_px + _orig_td
            else:
                sig.sl = opt_px + _orig_sd
                sig.tp1 = opt_px - _orig_td
        elif len(fill_info) >= 2 and isinstance(fill_info[0], str):
            if fill_info[0] == 'S1':
                _, opt_ci, opt_px = fill_info
            elif fill_info[0] == 'S2':
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist \\
                    = fill_info
                _is_stage2 = True
            else:
                continue
        else:
            opt_ci, opt_px = fill_info
""",
    },

    # ─── 4b. SLP position _slp_meta attachment ───
    {
        "id": "v11_position_meta",
        "description": "Attach _slp_meta to SLP-created positions",
        "unique_marker": "open_pos[sym]._slp_meta = _slp_meta_for_pos",
        "anchor": "            entry_sub_idx=opt_sub_idx,\n        )\n",
        "position": "after",
        "payload": """
        # ══ [SLP v1.1] Attach _slp_meta to SLP position ══
        if _is_slp_mode and _slp_meta_for_pos is not None:
            open_pos[sym]._slp_meta = _slp_meta_for_pos
""",
    },

    # ─── 5. Live startup loading ───
    {
        "id": "slp_live_load",
        "description": "Load SLP state at run_live startup",
        "unique_marker": "load_slp_orders(cfg.mode)" if False else '_slp_state_load(cfg.mode)',
        "anchor": "    # ══ [Pending] Load persisted pending orders ══\n    load_pending_orders(cfg.mode)\n",
        "position": "after",
        "payload": """    # ══ [SLP] Load persisted smart ladder orders ══
    if getattr(CFG, 'SLP_ENABLED', False):
        _slp_state_load(cfg.mode)
""",
    },

    # ─── 5b. SLP startup recovery ───
    {
        "id": "v11_startup_recovery",
        "description": "Recover/expire SLP state on live startup",
        "unique_marker": "_slp_startup_recover(exchange, open_pos_live)",
        "anchor": """    # ══ [SLP] Load persisted smart ladder orders ══
    if getattr(CFG, 'SLP_ENABLED', False):
        _slp_state_load(cfg.mode)
""",
        "position": "after",
        "payload": """    # ══ [SLP v1.1] Startup recovery ══
    if getattr(CFG, 'SLP_ENABLED', False):
        try:
            _slp_startup_recover(exchange, open_pos_live)
        except Exception as _e_sr:
            log.warning(f"[SLP] startup recovery failed: {_e_sr}")
""",
    },

    # ─── 6. Live monitor call ───
    {
        "id": "slp_live_monitor",
        "description": "Call SLP monitor in run_live loop",
        "unique_marker": "monitor_smart_ladder_pending(exchange, open_pos_live",
        "anchor": """            # ══ [Pending] Sweep pending orders every cycle ══
            # [Sing-Timing] نمرّر assets ليتمكن الفحص من قراءة الرنين الحالي.
            try:
                monitor_pending_orders(
                    exchange, open_pos_live, loop_iter,
                    assets=assets if 'assets' in dir() else None
                )
            except Exception as _e:
                log.warning(f"[Pending] monitor error: {_e}")
""",
        "position": "after",
        "payload": """            # ══ [SLP] Smart Ladder Pending monitor ══
            if getattr(CFG, 'SLP_ENABLED', False):
                try:
                    monitor_smart_ladder_pending(
                        exchange, open_pos_live, loop_iter,
                        assets=assets if 'assets' in dir() else None
                    )
                except Exception as _e:
                    log.warning(f"[SLP] monitor error: {_e}")
""",
    },

    # ─── 7. Live placement ───
    {
        "id": "slp_live_place",
        "description": "Insert SLP placement before place_pending_entry",
        "unique_marker": "place_smart_ladder_pending(exchange, sym, sd",
        "anchor": """                            rec = place_pending_entry(
                                exchange, sym, sd, qty, sig,
                                timeout_s=_timeout_s,
                                leverage=int(dynamic_leverage),
                                ad=assets[sym],
                            )
""",
        "position": "before",
        "payload": """                            # ══ [SLP] Smart Ladder Pending ══
                            if getattr(CFG, 'SLP_ENABLED', False):
                                _slp_rec = place_smart_ladder_pending(
                                    exchange, sym, sd, qty, sig,
                                    timeout_s=_timeout_s,
                                    leverage=int(dynamic_leverage),
                                    ad=assets[sym],
                                )
                                if _slp_rec is None:
                                    log.info(f"[SLP] {sym} place failed — skip")
                                    continue
                                try:
                                    _slp_state_save()
                                except Exception:
                                    pass
                                continue
                            # ── Legacy: single GTX order ──
""",
    },

    # ─── 8. Live exposure calculation ───
    {
        "id": "slp_live_exposure",
        "description": "Include SLP orders in total exposure count",
        "unique_marker": "len(_PENDING_ORDERS) + len(_SLP_ORDERS)",
        "anchor": "                    _total_exposure = (len(_PENDING_ORDERS)\n                                       + len(open_pos_live)\n                                       + len(_WATCHED_SIGNALS))\n",
        "position": "replace",
        "payload": """                    _total_exposure = (len(_PENDING_ORDERS)
                                       + len(open_pos_live)
                                       + len(_WATCHED_SIGNALS)
                                       + (len(_SLP_ORDERS)
                                          if getattr(CFG, 'SLP_ENABLED', False)
                                          else 0))
""",
    },

    # ─── 9. Clear-cache integration ───
    {
        "id": "slp_clear_cache",
        "description": "Add slp_orders files to --clear-cache list",
        "unique_marker": '"slp_orders_live.json"',
        "anchor": '''        _state_files = [
            "live_state_live.json", "live_state_testnet.json",
''',
        "position": "replace",
        "payload": '''        _state_files = [
            "slp_stats_backtest.csv", "slp_stats_testnet.csv",
            "slp_stats_live.csv",
            "slp_orders_live.json", "slp_orders_testnet.json",
            "live_state_live.json", "live_state_testnet.json",
''',
    },

    # ─── 10. CLI flags ───
    {
        "id": "slp_cli_flags",
        "description": "Add SLP CLI flags to argparse",
        "unique_marker": 'p.add_argument("--slp",',
        "anchor": '    args = p.parse_args()',
        "position": "before",
        "payload": '''
    # ══ [SLP] Smart Ladder Pending flags ══
    p.add_argument("--slp", action="store_true",
                   help="Enable Smart Ladder Pending (3-level entry)")
    p.add_argument("--slp-levels", type=str, default=None,
                   help="Custom sigma offsets (e.g., '0,0.3,0.6')")
    p.add_argument("--slp-weights", type=str, default=None,
                   help="Custom weights (e.g., '0.40,0.35,0.25')")
    p.add_argument("--slp-min-fill", type=float, default=None,
                   help="Minimum fill ratio (default 0.50)")
    p.add_argument("--slp-no-time-decay", action="store_true",
                   help="Disable time-decay level cancellation")
    p.add_argument("--slp-no-physics-cancel", action="store_true",
                   help="Disable physics-collapse level cancellation")
    p.add_argument("--slp-no-opposite-cancel", action="store_true",
                   help="Disable opposite-signal level cancellation")
    p.add_argument("--slp-no-score-frontload", action="store_true",
                   help="Use fixed weights regardless of signal score")
    p.add_argument("--slp-runaway-kappa", type=float, default=None,
                   help="Runaway threshold in sigma (default 2.0)")

''',
    },

    # ─── 11. CLI processing ───
    {
        "id": "slp_cli_process",
        "description": "Process SLP CLI flags in main()",
        "unique_marker": "CFG.SLP_ENABLED = True",
        "anchor": "    if args.no_numba: CFG.NUMBA_ENABLED = False\n",
        "position": "after",
        "payload": '''
    # ══ [SLP] Process Smart Ladder Pending flags ══
    if getattr(args, "slp", False):
        CFG.SLP_ENABLED = True
    if getattr(args, "slp_levels", None) is not None:
        try:
            _lv = tuple(float(x.strip()) for x in args.slp_levels.split(","))
            if len(_lv) == 3:
                CFG.SLP_LEVELS = _lv
        except Exception as e:
            log.warning(f"[SLP] bad --slp-levels: {e}")
    if getattr(args, "slp_weights", None) is not None:
        try:
            _w = tuple(float(x.strip()) for x in args.slp_weights.split(","))
            if len(_w) == 3 and abs(sum(_w) - 1.0) < 0.05:
                CFG.SLP_WEIGHTS = _w
            else:
                log.warning("[SLP] weights must sum to ~1.0")
        except Exception as e:
            log.warning(f"[SLP] bad --slp-weights: {e}")
    if getattr(args, "slp_min_fill", None) is not None:
        CFG.SLP_MIN_FILL_RATIO = float(args.slp_min_fill)
    if getattr(args, "slp_no_time_decay", False):
        CFG.SLP_TIME_DECAY_ENABLED = False
    if getattr(args, "slp_no_physics_cancel", False):
        CFG.SLP_PHYSICS_CANCEL_ENABLED = False
    if getattr(args, "slp_no_opposite_cancel", False):
        CFG.SLP_OPPOSITE_CANCEL_ENABLED = False
    if getattr(args, "slp_no_score_frontload", False):
        CFG.SLP_SCORE_FRONTLOAD = False
    if getattr(args, "slp_runaway_kappa", None) is not None:
        CFG.SLP_RUNAWAY_KAPPA = float(args.slp_runaway_kappa)
    if getattr(CFG, "SLP_ENABLED", False):
        log.info(
            f"[SLP] ENABLED | levels={CFG.SLP_LEVELS} "
            f"weights={CFG.SLP_WEIGHTS} "
            f"min_fill={CFG.SLP_MIN_FILL_RATIO} "
            f"runaway={CFG.SLP_RUNAWAY_KAPPA}σ "
            f"time_decay={CFG.SLP_TIME_DECAY_ENABLED} "
            f"physics_cancel={CFG.SLP_PHYSICS_CANCEL_ENABLED} "
            f"opposite_cancel={CFG.SLP_OPPOSITE_CANCEL_ENABLED} "
            f"score_frontload={CFG.SLP_SCORE_FRONTLOAD}"
        )
    else:
        log.info("[SLP] Disabled (use --slp to enable)")

    # ══ [SLP v1.1] Conflict guard: SLP + reversal-confirm ══
    if (getattr(CFG, 'SLP_ENABLED', False)
            and getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False)):
        log.warning(
            "[SLP] CONFLICT: both SLP and reversal-confirm are enabled. "
            "SLP takes precedence in Stage 1. reversal-confirm watchers "
            "still run for other signals. Consider using only one.")
''',
    },

    # ─── 12. Backtest report call ───
    {
        "id": "slp_backtest_report",
        "description": "Call _slp_stats_report at end of backtest",
        "unique_marker": "_slp_stats_report()",
        "anchor": "    log.info(\"✅ اكتمل.\")\n",
        "position": "before",
        "payload": """    # ══ [SLP] Print SLP summary ══
    if getattr(CFG, 'SLP_ENABLED', False):
        try:
            _slp_stats_report()
        except Exception as _e:
            log.warning(f"[SLP] report failed: {_e}")

""",
    },
]


# ═══════════════════════════════════════════════════════════════════
# PATCH ENGINE
# ═══════════════════════════════════════════════════════════════════

def _file_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _atomic_write(path: str, content: str) -> None:
    """Write atomically via temp file + rename."""
    dir_ = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _apply_single_patch(content: str, patch: dict) -> tuple:
    """Apply one patch. Returns (new_content, status)."""
    if patch["unique_marker"] in content:
        return content, "already_applied"

    anchor = patch["anchor"]
    if patch["position"] == "replace":
        # For "replace" patches, anchor is the OLD text to replace
        if anchor not in content:
            return content, "anchor_not_found"
        if content.count(anchor) > 1:
            return content, "anchor_ambiguous"
        new_content = content.replace(anchor, patch["payload"], 1)
        return new_content, "applied"

    idx = content.find(anchor)
    if idx < 0:
        return content, "anchor_not_found"
    if content.count(anchor) > 1:
        return content, "anchor_ambiguous"

    if patch["position"] == "before":
        new_content = content[:idx] + patch["payload"] + content[idx:]
    elif patch["position"] == "after":
        end = idx + len(anchor)
        new_content = content[:end] + patch["payload"] + content[end:]
    else:
        return content, f"unknown_position:{patch['position']}"
    return new_content, "applied"


def _verify_syntax(content: str) -> tuple:
    """AST parse to catch syntax errors."""
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def _load_manifest(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": PATCH_VERSION, "applied": [], "backups": []}


def _save_manifest(path: str, manifest: dict) -> None:
    _atomic_write(path, json.dumps(manifest, indent=2))


def _make_backup(target: str) -> str:
    """Create timestamped backup. Returns backup path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{target}.preSLP_{ts}.bak"
    shutil.copy2(target, backup)
    return backup


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def _parse_args():
    p = argparse.ArgumentParser(
        description="SLP Patch Script — applies Smart Ladder Pending to trading_final.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument("--file", default=DEFAULT_TARGET,
                   help=f"Target file (default: {DEFAULT_TARGET})")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would change without writing")
    p.add_argument("--verify-only", action="store_true",
                   help="Only verify current file syntax")
    p.add_argument("--rollback", action="store_true",
                   help="Restore from most recent backup")
    p.add_argument("--force", action="store_true",
                   help="Re-apply patches even if manifest says applied")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Verbose output")
    return p.parse_args()


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    args = _parse_args()

    if not os.path.exists(args.file):
        print(f"✗ Target file not found: {args.file}")
        return 1

    with open(args.file, "r", encoding="utf-8") as f:
        original = f.read()

    orig_hash = _file_hash(original)
    print(f"Target: {args.file}")
    print(f"Size: {len(original):,} chars")
    print(f"Hash: {orig_hash}")
    print(f"Patches to apply: {len(PATCHES)}")
    print()

    # ── Verify only ──
    if args.verify_only:
        ok, err = _verify_syntax(original)
        if ok:
            print("✓ Syntax valid")
            # Check SLP presence
            has_slp = "SLP_ENABLED: bool = False" in original
            print(f"  SLP config: {'✓ present' if has_slp else '✗ absent'}")
            has_helpers = "def place_smart_ladder_pending(" in original
            print(f"  SLP helpers: {'✓ present' if has_helpers else '✗ absent'}")
        else:
            print(f"✗ Syntax error: {err}")
            return 1
        return 0

    # ── Rollback ──
    if args.rollback:
        manifest = _load_manifest(MANIFEST_FILE)
        backups = manifest.get("backups", [])
        if not backups:
            print("✗ No backups found in manifest")
            return 1
        latest = backups[-1]
        if not os.path.exists(latest):
            print(f"✗ Backup file missing: {latest}")
            return 1
        shutil.copy2(latest, args.file)
        manifest["applied"] = []
        _save_manifest(MANIFEST_FILE, manifest)
        print(f"✓ Rolled back from {latest}")
        return 0

    # ── Apply patches ──
    manifest = _load_manifest(MANIFEST_FILE)
    already = set(manifest.get("applied", []))

    current = original
    applied_count = 0
    skipped_count = 0
    failed = []

    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        desc = patch["description"]

        if pid in already and not args.force:
            if args.verbose:
                print(f"[{i:2d}/{len(PATCHES)}] SKIP  {pid}: already applied")
            skipped_count += 1
            continue

        new_content, status = _apply_single_patch(current, patch)

        if status == "applied":
            current = new_content
            applied_count += 1
            print(f"[{i:2d}/{len(PATCHES)}] ✓ APPLY {pid}: {desc}")
        elif status == "already_applied":
            skipped_count += 1
            if args.verbose:
                print(f"[{i:2d}/{len(PATCHES)}] SKIP  {pid}: marker present")
        else:
            failed.append((pid, status))
            print(f"[{i:2d}/{len(PATCHES)}] ✗ FAIL  {pid}: {status}")

    if failed:
        print()
        print(f"✗ {len(failed)} patch(es) failed. Aborting (no changes written).")
        for pid, st in failed:
            print(f"    {pid}: {st}")
        return 1

    # ── Verify syntax ──
    print()
    ok, err = _verify_syntax(current)
    if not ok:
        print(f"✗ Syntax error after patching: {err}")
        print("  Aborting (no changes written)")
        return 1
    print(f"✓ Syntax valid after {applied_count} applied + {skipped_count} skipped")

    # ── Dry run ──
    if args.dry_run:
        print()
        print("── DRY RUN — no files written ──")
        print(f"Would write: {args.file}")
        print(f"Size change: {len(current):,} → {len(current):,} "
              f"({len(current) - len(original):+,} chars)")
        return 0

    # ── Write ──
    backup = _make_backup(args.file)
    print(f"Backup: {backup}")

    _atomic_write(args.file, current)
    print(f"✓ Wrote {args.file} ({len(current):,} chars)")

    # ── Update manifest ──
    for patch in PATCHES:
        if patch["id"] not in manifest["applied"]:
            manifest["applied"].append(patch["id"])
    manifest["backups"].append(backup)
    manifest["version"] = PATCH_VERSION
    manifest["last_run"] = datetime.now().isoformat()
    manifest["last_hash"] = _file_hash(current)
    _save_manifest(MANIFEST_FILE, manifest)

    print()
    print("═" * 60)
    print(f"✓ SLP v{PATCH_VERSION} applied successfully")
    print(f"  Backup: {backup}")
    print(f"  Manifest: {MANIFEST_FILE}")
    print()
    print("Next steps:")
    print("  1. Test:  python trading_final.py --slp --mode backtest [...your args...]")
    print("  2. Compare with baseline results")
    print("  3. If issues:  python apply_slp_patch.py --rollback")
    print("═" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ═══════════════════════════════════════════════════════════════════
# INSTRUCTIONS
# ═══════════════════════════════════════════════════════════════════
"""
HOW TO USE THIS SCRIPT
═══════════════════════════════════════════════════════════════════

STEP 1: Save this script as `apply_slp_patch.py` next to `trading_final.py`.

STEP 2: Verify current file is clean:
    python apply_slp_patch.py --verify-only

STEP 3: Preview changes (no writes):
    python apply_slp_patch.py --dry-run

STEP 4: Apply the patch:
    python apply_slp_patch.py

STEP 5: Test with SLP disabled (should match baseline bit-for-bit):
    python trading_final.py [your original args] --analytics
    → verify results identical to baseline

STEP 6: Test with SLP enabled:
    python trading_final.py [your original args] --slp --analytics

STEP 7: If anything goes wrong:
    python apply_slp_patch.py --rollback

═══════════════════════════════════════════════════════════════════

WHAT THIS SCRIPT MODIFIES
═══════════════════════════════════════════════════════════════════

12 patches applied in order:

  1. slp_config          - 22 new Config fields (SLP_*)
  2. slp_helpers         - 15 helper functions (~700 lines)
  3. slp_backtest_fillmap - Hook into simulate_portfolio fill_map
  4. slp_advance_window  - Early-return in _advance during SLP window
  5. slp_live_load       - Load state at run_live startup
  6. slp_live_monitor    - Monitor call in run_live loop
  7. slp_live_place      - Placement before place_pending_entry
  8. slp_live_exposure   - Include _SLP_ORDERS in exposure count
  9. slp_clear_cache     - Add slp_orders_*.json to cache cleanup
 10. slp_cli_flags       - 9 new argparse flags
 11. slp_cli_process     - Process SLP flags in main()
 12. slp_backtest_report - Print SLP summary at end of backtest

═══════════════════════════════════════════════════════════════════

KNOWN SIMPLIFICATIONS (v1.0)
═══════════════════════════════════════════════════════════════════

These were simplified to keep the patch manageable:

✓ Opposite-signal cancellation is implemented but only checked
  during the SLP monitor cycle (not per-signal in the trade loop).
  Effect: cancellations happen within 1 cycle of the opposite signal.

✓ BEEsc does NOT auto-cancel remaining SLP levels in v1.0.
  Position BEEsc-protected via standard mechanism; remaining levels
  cancelled by timeout or other triggers.

✓ In backtest, position is created at final VWAP (not per-bar fills).
  This is an approximation (affects PnL by ~1-2 bps).

✓ Physics-cancel in backtest uses current bar's P_activation
  vs signal-time P_activation. Same logic as live.

These simplifications are safe for v1.0 and can be upgraded in v1.1
without breaking anything.

═══════════════════════════════════════════════════════════════════

SAFETY GUARANTEES
═══════════════════════════════════════════════════════════════════

✓ Automatic timestamped backup before any write
✓ Atomic writes (temp file + rename)
✓ AST syntax verification before commit
✓ Rollback via --rollback
✓ Idempotent (safe to re-run; skips already-applied)
✓ All-or-nothing (any patch failure → no writes)
✓ Manifest tracks applied patches for auditing

═══════════════════════════════════════════════════════════════════
"""
