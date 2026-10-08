#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_live2_mfal.py                                                     ║
║  Multi-Factor Adaptive Leverage for trading_2_live2.py                   ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Group D — MFAL infrastructure                                           ║
║    M1    Signal dataclass: add mfal_x + mfal_p_act fields                ║
║    M2    Insert MFAL block (state, helpers, compute_adaptive_leverage)   ║
║                                                                          ║
║  Group E — Trade lifecycle integration                                   ║
║    M3    build_signals: extract MFAL features + include in Signal        ║
║    M4    backtest _close: record MFAL outcome                            ║
║    M5    live exit path: record MFAL outcome                             ║
║    M6a   _lv_place_pending_entry: store sig_mfal_x in record             ║
║    M6b   _lv_promote_pending_to_position: transfer _mfal_x to position   ║
║                                                                          ║
║  Group F — Leverage callsites + CLI                                      ║
║    M7    backtest callsite -> compute_adaptive_leverage                  ║
║    M8    live callsite     -> compute_adaptive_leverage                  ║
║    M9    main(): MFAL CLI args                                           ║
║    M10   main(): MFAL CLI wiring                                         ║
║    M11   run_live loop: periodic _mfal_log_stats()                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 patch_live2_mfal.py --dry-run                                ║
║    python3 patch_live2_mfal.py                                          ║
║    python3 patch_live2_mfal.py --restore                                ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse, shutil, sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class C:
    GREEN='\033[92m'; RED='\033[91m'; YELLOW='\033[93m'
    CYAN='\033[96m'; GRAY='\033[90m'; BOLD='\033[1m'; END='\033[0m'


# ══════════════════════════════════════════════════════════════════════════
# M1 — Signal dataclass: add mfal_x + mfal_p_act
# ══════════════════════════════════════════════════════════════════════════

M1_OLD = """    dyn_sl_factor: float = 0.1
    # ══ [SMART ENTRY] ══
    entry_ref_price: float = 0.0   # close price at signal time (dip ref)
    entry_base_dip: float = 0.0    # |ref_price − price| in price units"""

M1_NEW = """    dyn_sl_factor: float = 0.1
    # ══ [SMART ENTRY] ══
    entry_ref_price: float = 0.0   # close price at signal time (dip ref)
    entry_base_dip: float = 0.0    # |ref_price − price| in price units
    # ══ [MFAL] Signal-time feature vector for Quality factor ══
    mfal_x: Optional[np.ndarray] = None
    mfal_p_act: float = 0.0"""


# ══════════════════════════════════════════════════════════════════════════
# M2 — Insert MFAL block before SR section
# ══════════════════════════════════════════════════════════════════════════

M2_ANCHOR = """# ════════════════════════════════════════════════════════════════
# § 12.9  Support/Resistance Detection
# ════════════════════════════════════════════════════════════════"""

M2_BLOCK = '''# ══════════════════════════════════════════════════════════════════════
# [MFAL] Multi-Factor Adaptive Leverage
# ══════════════════════════════════════════════════════════════════════
#
# Philosophy:
#   Leverage is not a single number derived from one formula. It is a
#   DECISION that fuses multiple independent factors:
#
#       L_final = L_core * Q * R * T * M
#
#     L_core = physical base (capital + liquidity)
#     Q      = signal quality (learned weights)
#     R      = portfolio capacity (corr, heat, dd, perf)
#     T      = time-of-day liquidity multiplier
#     M      = micro-structure (spread / depth) multiplier
#
#   Hard constraints (Liq cap, symbol max, L_min) applied LAST.
#
# Default state: DISABLED. Enable via --mfal flag.

_MFAL_ENABLED: bool = False
_MFAL_USE_MICRO: bool = True
_MFAL_USE_TIME: bool = True
_MFAL_USE_LEARNING: bool = True
_MFAL_MIN_TRADES_FOR_LEARNING: int = 200
_MFAL_RETRAIN_EVERY: int = 50

_MFAL_WEIGHTS_PATH: str = "mfal_weights.json"
_MFAL_HISTORY_PATH: str = "mfal_history.jsonl"
_MFAL_FEATURE_KEYS = [
    "score", "p_act", "accel_ratio",
    "gauge", "z_dev", "rr", "freshness",
]
_MFAL_DEFAULT_WEIGHTS = np.array(
    [0.30, 0.25, 0.15, 0.10, 0.10, 0.05, 0.05],
    dtype=np.float64,
)
_MFAL_WEIGHTS: np.ndarray = _MFAL_DEFAULT_WEIGHTS.copy()
_MFAL_BIAS: float = 0.0

_MFAL_STATS: Dict = {
    "compute_calls": 0,
    "q_min": float("inf"), "q_max": float("-inf"), "q_sum": 0.0,
    "r_min": float("inf"), "r_max": float("-inf"), "r_sum": 0.0,
    "l_core_sum": 0.0, "l_final_sum": 0.0,
    "trades_recorded": 0, "retrains": 0, "last_report_ts": 0.0,
}
_MFAL_RECENT_R: List[float] = []


def _mfal_load_weights(path=None):
    global _MFAL_WEIGHTS, _MFAL_BIAS
    p = path or _MFAL_WEIGHTS_PATH
    if not os.path.exists(p):
        log.info(f"[MFAL] No weights file at {p} -- using defaults")
        return False
    try:
        with open(p, "r") as f:
            data = json.load(f)
        w = data.get("weights", None)
        b = float(data.get("bias", 0.0))
        if w is None or len(w) != len(_MFAL_FEATURE_KEYS):
            log.warning(f"[MFAL] Invalid weights shape in {p}")
            return False
        _MFAL_WEIGHTS = np.array(w, dtype=np.float64)
        _MFAL_BIAS = b
        log.info(f"[MFAL] Loaded weights from {p}: "
                 f"norm={np.linalg.norm(_MFAL_WEIGHTS):.4f}")
        return True
    except Exception as e:
        log.warning(f"[MFAL] Load failed: {e}")
        return False


def _mfal_save_weights(path=None):
    p = path or _MFAL_WEIGHTS_PATH
    try:
        payload = {
            "weights": _MFAL_WEIGHTS.tolist(),
            "bias": float(_MFAL_BIAS),
            "features": list(_MFAL_FEATURE_KEYS),
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_trades_at_save": int(_MFAL_STATS.get("trades_recorded", 0)),
        }
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        log.warning(f"[MFAL] Save failed: {e}")


def _mfal_signal_features(score, p_act, accel_ratio, gauge, z_dev, rr):
    """7-dim feature vector from signal-time data. Bounded to [-1, 1]."""
    try:
        x = np.array([
            float(score) / 8.0,
            float(p_act),
            float(np.tanh(accel_ratio / 3.0)),
            float(np.tanh(gauge * 10.0)),
            float(np.tanh(abs(z_dev) / 2.0)),
            float(np.tanh(rr / 3.0)),
            1.0,
        ], dtype=np.float64)
        if not np.all(np.isfinite(x)):
            return None
        return x
    except Exception:
        return None


def _mfal_quality(x):
    """Q = 0.4 + 1.4 * sigmoid(w.x), range [0.40, 1.80]."""
    if x is None:
        return 1.0
    try:
        z = float(np.dot(_MFAL_WEIGHTS, x)) + _MFAL_BIAS
        s = 1.0 / (1.0 + np.exp(-np.clip(z, -20.0, 20.0)))
        q = 0.4 + 1.4 * s
        return float(np.clip(q, 0.40, 1.80))
    except Exception:
        return 1.0


def _mfal_time_factor(now_ts=None):
    """Hour-of-day liquidity multiplier (0.75 -> 1.15)."""
    try:
        if now_ts is None:
            now_ts = time.time()
        h = datetime.fromtimestamp(now_ts, timezone.utc).hour
        table = {
            0: 0.85, 1: 0.80, 2: 0.75, 3: 0.75,
            4: 0.80, 5: 0.85, 6: 0.90, 7: 0.95,
            8: 1.00, 9: 1.05, 10: 1.05, 11: 1.00,
            12: 1.05, 13: 1.10, 14: 1.15, 15: 1.15,
            16: 1.10, 17: 1.05, 18: 1.00, 19: 0.95,
            20: 0.90, 21: 0.90, 22: 0.85, 23: 0.85,
        }
        return float(table.get(h, 1.0))
    except Exception:
        return 1.0


def _mfal_micro_factor(exchange, sym):
    """Spread / depth multiplier from live book. Range [0.42, 1.32]."""
    if not _MFAL_USE_MICRO or exchange is None:
        return 1.0
    try:
        ob = exchange.fetch_order_book(sym, limit=5)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        if not bids or not asks:
            return 1.0
        bb = float(bids[0][0]); ba = float(asks[0][0])
        if bb <= 0 or ba <= 0 or ba < bb:
            return 1.0
        mid = (bb + ba) / 2.0
        spread_bps = (ba - bb) / mid * 1e4
        depth_bid = sum(float(x[1]) for x in bids[:5]) * bb
        depth_ask = sum(float(x[1]) for x in asks[:5]) * ba
        depth_usd = (depth_bid + depth_ask) / 2.0
        f_spread = float(np.clip(
            (3.0 / max(spread_bps, 0.1)) ** 0.5, 0.60, 1.20))
        f_depth = float(np.clip(
            (depth_usd / 1.0e5) ** 0.30, 0.70, 1.10))
        return float(np.clip(f_spread * f_depth, 0.42, 1.32))
    except Exception as e:
        log.debug(f"[MFAL] micro_factor failed for {sym}: {e}")
        return 1.0


def _mfal_portfolio_factor(sym, open_pos_live, capital,
                             peak_capital, corr_cache):
    """R = R_corr * R_heat * R_dd * R_perf, clipped to [0.30, 1.30]."""
    try:
        if open_pos_live and corr_cache:
            rho_max = 0.0
            for other in open_pos_live.keys():
                rho = abs(float(corr_cache.get((sym, other), 0.0)))
                if rho > rho_max:
                    rho_max = rho
            R_corr = 1.0 - 0.5 * rho_max
        else:
            R_corr = 1.0

        heat_max = float(getattr(CFG, "PORTFOLIO_HEAT_MAX", 0.10))
        heat_used = 0.0
        for p in open_pos_live.values():
            try:
                if isinstance(p, dict):
                    heat_used += float(p.get("dyn_risk", 0.0) or 0.0)
                else:
                    try:
                        heat_used += float(p.signal.dynamic_risk)
                    except Exception:
                        heat_used += float(
                            getattr(p, "dynamic_risk", 0.0) or 0.0)
            except Exception:
                pass
        R_heat = (1.0 - 0.4 * min(1.0, heat_used / heat_max)
                  if heat_max > 1e-9 else 1.0)

        dd = (max(0.0, (peak_capital - capital) / peak_capital)
              if peak_capital > 1e-9 else 0.0)
        R_dd = float(np.exp(-3.0 * dd))

        if len(_MFAL_RECENT_R) >= 10:
            r = np.array(_MFAL_RECENT_R[-50:], dtype=np.float64)
            mu = float(np.mean(r))
            sd = float(np.std(r, ddof=1)) if len(r) > 1 else 0.0
            sharpe = (mu / sd * np.sqrt(len(r))) if sd > 1e-9 else 0.0
            R_perf = float(np.clip(0.9 + 0.1 * sharpe, 0.70, 1.20))
        else:
            R_perf = 1.0

        R = R_corr * R_heat * R_dd * R_perf
        return float(np.clip(R, 0.30, 1.30))
    except Exception as e:
        log.debug(f"[MFAL] portfolio_factor failed: {e}")
        return 1.0


def compute_adaptive_leverage(symbol, sig, open_pos_live, capital,
                                peak_capital, corr_cache, exchange,
                                cfg):
    """
    [MFAL] Adaptive leverage:
        L = clamp(L_core * Q * R * T * M, L_min, min(L_liq, L_sym))
    Falls back to compute_dynamic_leverage when MFAL is disabled.
    """
    L_core = int(compute_dynamic_leverage(capital, cfg, symbol=symbol))

    if not _MFAL_ENABLED:
        return L_core

    x = getattr(sig, "mfal_x", None) if sig is not None else None
    Q = _mfal_quality(x)
    R = _mfal_portfolio_factor(
        sym=symbol,
        open_pos_live=open_pos_live or {},
        capital=capital,
        peak_capital=peak_capital,
        corr_cache=corr_cache or {},
    )
    T = _mfal_time_factor() if _MFAL_USE_TIME else 1.0
    M = _mfal_micro_factor(exchange, symbol) if _MFAL_USE_MICRO else 1.0

    L_scored = L_core * Q * R * T * M

    try:
        _mmr = _get_mmr_for_symbol(exchange, symbol) if exchange else 0.02
        _sl_frac_max = 0.015 * float(getattr(cfg, "SL_WIDEN_MULT", 1.0))
        L_liq = int(compute_max_leverage_by_liq(
            sl_frac_max=_sl_frac_max,
            mmr=_mmr,
            safety_mult=float(getattr(cfg, "LIQ_SAFETY_MULT", 1.5)),
            symbol=symbol,
        ))
    except Exception:
        L_liq = int(cfg.LEVERAGE_MAX)

    try:
        L_sym = int(max(_symbol_tiers(symbol, cfg)))
    except Exception:
        L_sym = int(cfg.LEVERAGE_MAX)

    L_min = int(cfg.LEVERAGE_MIN)
    L_final = int(np.floor(L_scored))
    L_final = max(L_min, min(L_final, L_liq, L_sym))

    try:
        tiers = _symbol_tiers(symbol, cfg)
        valid = [int(t) for t in tiers if L_min <= int(t) <= L_final]
        L_final = int(valid[-1]) if valid else L_min
    except Exception:
        pass

    _MFAL_STATS["compute_calls"] += 1
    _MFAL_STATS["q_min"] = min(_MFAL_STATS["q_min"], Q)
    _MFAL_STATS["q_max"] = max(_MFAL_STATS["q_max"], Q)
    _MFAL_STATS["q_sum"] += Q
    _MFAL_STATS["r_min"] = min(_MFAL_STATS["r_min"], R)
    _MFAL_STATS["r_max"] = max(_MFAL_STATS["r_max"], R)
    _MFAL_STATS["r_sum"] += R
    _MFAL_STATS["l_core_sum"] += L_core
    _MFAL_STATS["l_final_sum"] += L_final

    if Q < 0.7 or Q > 1.4 or R < 0.7:
        log.info(
            f"[MFAL] {symbol} L={L_final}x "
            f"(core={L_core}, Q={Q:.2f}, R={R:.2f}, "
            f"T={T:.2f}, M={M:.2f})"
        )

    return int(L_final)


def _mfal_record_trade(sig, outcome_R, success):
    """Records a trade outcome. Accepts Signal object OR dict."""
    try:
        x = None
        if sig is not None:
            if isinstance(sig, dict):
                _x_raw = sig.get("_mfal_x") or sig.get("mfal_x")
                if _x_raw is not None:
                    try:
                        x = np.asarray(_x_raw, dtype=np.float64)
                    except Exception:
                        x = None
            else:
                x = getattr(sig, "mfal_x", None)
        if x is None:
            return
        record = {
            "ts": time.time(),
            "symbol": str(
                sig.get("_sym") if isinstance(sig, dict)
                else getattr(sig, "symbol", "?")),
            "x": np.asarray(x).tolist(),
            "outcome_R": float(outcome_R),
            "success": bool(success),
        }
        try:
            with open(_MFAL_HISTORY_PATH, "a") as f:
                f.write(json.dumps(record) + "\\n")
        except Exception:
            pass

        _MFAL_RECENT_R.append(float(outcome_R))
        if len(_MFAL_RECENT_R) > 200:
            _MFAL_RECENT_R[:] = _MFAL_RECENT_R[-100:]

        _MFAL_STATS["trades_recorded"] += 1

        if (_MFAL_USE_LEARNING
                and _MFAL_STATS["trades_recorded"] >= _MFAL_MIN_TRADES_FOR_LEARNING
                and _MFAL_STATS["trades_recorded"] % _MFAL_RETRAIN_EVERY == 0):
            _mfal_retrain()
    except Exception as e:
        log.debug(f"[MFAL] record_trade failed: {e}")


def _mfal_retrain():
    if not os.path.exists(_MFAL_HISTORY_PATH):
        return
    try:
        X, y = [], []
        with open(_MFAL_HISTORY_PATH) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                x = r.get("x")
                if not isinstance(x, list):
                    continue
                if len(x) != len(_MFAL_FEATURE_KEYS):
                    continue
                X.append(x)
                y.append(1.0 if r.get("success") else 0.0)
        if len(X) < _MFAL_MIN_TRADES_FOR_LEARNING:
            return
        Xa = np.array(X, dtype=np.float64)
        ya = np.array(y, dtype=np.float64)
        if ya.sum() < 20 or (1.0 - ya).sum() < 20:
            return
        from scipy.optimize import minimize as _scipy_min

        def _loss(params):
            w = params[:-1]; b = params[-1]
            z = Xa @ w + b
            p = np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)),
                         np.exp(z) / (1.0 + np.exp(z)))
            eps = 1e-9
            p = np.clip(p, eps, 1.0 - eps)
            nll = -np.mean(ya * np.log(p) + (1 - ya) * np.log(1 - p))
            reg = 0.1 * float(np.sum(w * w))
            return float(nll + reg)

        x0 = np.concatenate([_MFAL_WEIGHTS, [_MFAL_BIAS]])
        res = _scipy_min(_loss, x0, method="L-BFGS-B",
                          options={"maxiter": 100})

        global _MFAL_WEIGHTS, _MFAL_BIAS
        _MFAL_WEIGHTS = 0.8 * _MFAL_WEIGHTS + 0.2 * res.x[:-1]
        _MFAL_BIAS = 0.8 * _MFAL_BIAS + 0.2 * float(res.x[-1])

        _MFAL_STATS["retrains"] += 1
        _mfal_save_weights()
        log.info(
            f"[MFAL] Retrained #{_MFAL_STATS['retrains']} "
            f"(n={len(X)}, w_norm={np.linalg.norm(_MFAL_WEIGHTS):.4f})"
        )
    except Exception as e:
        log.warning(f"[MFAL] retrain failed: {e}")


def _mfal_log_stats():
    if not _MFAL_ENABLED:
        return
    now = time.time()
    if now - _MFAL_STATS.get("last_report_ts", 0.0) < 300:
        return
    _MFAL_STATS["last_report_ts"] = now
    n = max(_MFAL_STATS["compute_calls"], 1)
    log.info(
        f"[MFAL] calls={n}, "
        f"Q=[{_MFAL_STATS['q_min']:.2f},{_MFAL_STATS['q_max']:.2f}] "
        f"mu={_MFAL_STATS['q_sum']/n:.2f}, "
        f"R=[{_MFAL_STATS['r_min']:.2f},{_MFAL_STATS['r_max']:.2f}] "
        f"mu={_MFAL_STATS['r_sum']/n:.2f}, "
        f"L_core_avg={_MFAL_STATS['l_core_sum']/n:.2f}, "
        f"L_final_avg={_MFAL_STATS['l_final_sum']/n:.2f}, "
        f"trades={_MFAL_STATS['trades_recorded']}, "
        f"retrains={_MFAL_STATS['retrains']}"
    )


# ══════════════════════════════════════════════════════════════════════
# [/MFAL]
# ══════════════════════════════════════════════════════════════════════


''' + M2_ANCHOR


# ══════════════════════════════════════════════════════════════════════════
# M3 — build_signals: extract MFAL features + include in Signal
# ══════════════════════════════════════════════════════════════════════════

M3_OLD = """            dynamic_risk = compute_geodesic_kelly(ad, fi, CFG)

            # ══ [TRADE FILTER] ══
            _new_sig = Signal(
                timestamp=ad.timestamps[ci], symbol=sym,
                price=tunnel_entry_p,
                score=float(ad.score[fi]), action=action,
                sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                dynamic_risk=dynamic_risk, T_info_val=T_info,
                dyn_sl_factor=sl_dist / tunnel_entry_p,
                entry_ref_price=float(p),
                entry_base_dip=float(_entry_dip),
            )"""

M3_NEW = """            dynamic_risk = compute_geodesic_kelly(ad, fi, CFG)

            # ══ [MFAL] Extract signal features for Quality factor ══
            try:
                _accel_ratio_mfal = abs(geo_accel) / max(fric_val, 1e-9)
                _sl_dist_mfal = abs(tunnel_entry_p - sl)
                _rr_mfal = abs(tp1 - tunnel_entry_p) / max(_sl_dist_mfal, 1e-9)
                _mfal_x = _mfal_signal_features(
                    score=float(ad.score[fi]),
                    p_act=float(P_activation),
                    accel_ratio=float(_accel_ratio_mfal),
                    gauge=float(ad.gauge_force[fi]),
                    z_dev=float(_z_dev),
                    rr=float(_rr_mfal),
                )
            except Exception:
                _mfal_x = None

            # ══ [TRADE FILTER] ══
            _new_sig = Signal(
                timestamp=ad.timestamps[ci], symbol=sym,
                price=tunnel_entry_p,
                score=float(ad.score[fi]), action=action,
                sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                dynamic_risk=dynamic_risk, T_info_val=T_info,
                dyn_sl_factor=sl_dist / tunnel_entry_p,
                entry_ref_price=float(p),
                entry_base_dip=float(_entry_dip),
                mfal_x=_mfal_x,
                mfal_p_act=float(P_activation),
            )"""


# ══════════════════════════════════════════════════════════════════════════
# M4 — backtest _close: record MFAL outcome
# ══════════════════════════════════════════════════════════════════════════

M4_OLD = """        # ══ [TradeLog] تسجيل الصفقة ══
        try:
            _trade_log_from_backtest(
                pos, ad, exit_eff, exit_rsn, exit_ci,
                pos.entry_cap, capital,
                net_pnl=net, log_return=lr
            )
        except Exception as _tle:
            log.debug(f"[TradeLog] backtest hook failed: {_tle}")"""

M4_NEW = """        # ══ [TradeLog] تسجيل الصفقة ══
        try:
            _trade_log_from_backtest(
                pos, ad, exit_eff, exit_rsn, exit_ci,
                pos.entry_cap, capital,
                net_pnl=net, log_return=lr
            )
        except Exception as _tle:
            log.debug(f"[TradeLog] backtest hook failed: {_tle}")

        # ══ [MFAL] Record trade outcome ══
        try:
            if _MFAL_ENABLED:
                _entry_px_m = float(pos.entry_px)
                _sl_d0_m = float(getattr(pos, "sl_dist_initial", 0.0))
                if _entry_px_m > 0 and _sl_d0_m > 0:
                    if sig.action == "BUY":
                        _pnl_frac_m = (exit_eff - _entry_px_m) / _entry_px_m
                    else:
                        _pnl_frac_m = (_entry_px_m - exit_eff) / _entry_px_m
                    _sl_frac_m = _sl_d0_m / _entry_px_m
                    _R_m = _pnl_frac_m / _sl_frac_m if _sl_frac_m > 0 else 0.0
                    _mfal_record_trade(sig, float(_R_m), _R_m > 0.5)
        except Exception as _me:
            log.debug(f"[MFAL] backtest record failed: {_me}")"""


# ══════════════════════════════════════════════════════════════════════════
# M5 — live exit path: record MFAL outcome
# ══════════════════════════════════════════════════════════════════════════

M5_OLD = """                    except Exception as _tle:
                        log.debug(f"[TradeLog] live hook failed: {_tle}")

                    del open_pos_live[sym]
                    last_exit_time[sym] = time.time()
                    _LV_LAST_EXIT[sym] = last_exit_time[sym]"""

M5_NEW = """                    except Exception as _tle:
                        log.debug(f"[TradeLog] live hook failed: {_tle}")

                    # ══ [MFAL] Record trade outcome ══
                    try:
                        _entry_px_m = float(pos.get('entry') or 0)
                        _sl_d0_m = float(pos.get('sl_dist_initial') or 0)
                        if _entry_px_m > 0 and _sl_d0_m > 0:
                            _exit_px_m = float(exec_price or 0)
                            if pos.get('action') == 'BUY':
                                _pnl_frac_m = (
                                    _exit_px_m - _entry_px_m) / _entry_px_m
                            else:
                                _pnl_frac_m = (
                                    _entry_px_m - _exit_px_m) / _entry_px_m
                            _sl_frac_m = _sl_d0_m / _entry_px_m
                            _R_m = _pnl_frac_m / _sl_frac_m \\
                                    if _sl_frac_m > 0 else 0.0
                            _mfal_record_trade(pos, float(_R_m), _R_m > 0.5)
                    except Exception as _me:
                        log.debug(f"[MFAL] record failed: {_me}")

                    del open_pos_live[sym]
                    last_exit_time[sym] = time.time()
                    _LV_LAST_EXIT[sym] = last_exit_time[sym]"""


# ══════════════════════════════════════════════════════════════════════════
# M6a — _lv_place_pending_entry: store sig_mfal_x in record
# ══════════════════════════════════════════════════════════════════════════

M6A_OLD = """            rec['sig_ref_px'] = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            rec['sig_base_dip'] = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)
        except Exception as e:
            log.debug(f"[LV] pending extras failed: {e}")"""

M6A_NEW = """            rec['sig_ref_px'] = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            rec['sig_base_dip'] = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)
            try:
                _mx = getattr(sig, 'mfal_x', None)
                rec['sig_mfal_x'] = (
                    _mx.tolist() if _mx is not None else None)
            except Exception:
                rec['sig_mfal_x'] = None
            rec['sig_mfal_p_act'] = float(getattr(sig, 'mfal_p_act', 0.0))
        except Exception as e:
            log.debug(f"[LV] pending extras failed: {e}")"""


# ══════════════════════════════════════════════════════════════════════════
# M6b — _lv_promote_pending_to_position: transfer _mfal_x to position
# ══════════════════════════════════════════════════════════════════════════

M6B_OLD = """def _lv_promote_pending_to_position(exchange, sym, rec, open_pos_live) -> bool:
    ok = _lv_orig_promote_pending(exchange, sym, rec, open_pos_live)
    if ok and sym in open_pos_live:
        p = open_pos_live[sym]
        if rec.get('close_idx'):
            p['_entry_ci'] = int(rec['close_idx'])
        _lv_finalize_position(exchange, sym, p, rec.get('ad_ref'))
    return ok"""

M6B_NEW = """def _lv_promote_pending_to_position(exchange, sym, rec, open_pos_live) -> bool:
    ok = _lv_orig_promote_pending(exchange, sym, rec, open_pos_live)
    if ok and sym in open_pos_live:
        p = open_pos_live[sym]
        if rec.get('close_idx'):
            p['_entry_ci'] = int(rec['close_idx'])
        _lv_finalize_position(exchange, sym, p, rec.get('ad_ref'))
        # [MFAL] carry the signal-quality vector into the position record
        try:
            p['_mfal_x'] = rec.get('sig_mfal_x')
            p['_mfal_p_act'] = float(rec.get('sig_mfal_p_act', 0.0))
        except Exception:
            pass
    return ok"""


# ══════════════════════════════════════════════════════════════════════════
# M7 — backtest callsite
# ══════════════════════════════════════════════════════════════════════════

M7_OLD = """        # Leverage cap
        dynamic_leverage = compute_dynamic_leverage(capital, CFG, symbol=sym)"""

M7_NEW = """        # Leverage cap (MFAL-aware when --mfal is enabled)
        dynamic_leverage = compute_adaptive_leverage(
            symbol=sym,
            sig=sig,
            open_pos_live=open_pos,
            capital=capital,
            peak_capital=peak_cap,
            corr_cache=corr_matrix,
            exchange=None,
            cfg=CFG,
        )"""


# ══════════════════════════════════════════════════════════════════════════
# M8 — live callsite
# ══════════════════════════════════════════════════════════════════════════

M8_OLD = """                    dynamic_leverage = compute_dynamic_leverage(
                        cap_live, cfg, symbol=sym)"""

M8_NEW = """                    dynamic_leverage = compute_adaptive_leverage(
                        symbol=sym,
                        sig=sig,
                        open_pos_live=open_pos_live,
                        capital=cap_live,
                        peak_capital=peak_cap_live,
                        corr_cache=corr_cache,
                        exchange=exchange,
                        cfg=cfg,
                    )"""


# ══════════════════════════════════════════════════════════════════════════
# M9 — main(): MFAL CLI args
# ══════════════════════════════════════════════════════════════════════════

M9_OLD = """    p.add_argument("--opp-tp-max-age-bars", type=int, default=None,
                   help="Max age of opposite signal in bars (default 4)")
    args = p.parse_args()"""

M9_NEW = """    p.add_argument("--opp-tp-max-age-bars", type=int, default=None,
                   help="Max age of opposite signal in bars (default 4)")
    # ══ [MFAL] CLI args ══
    p.add_argument("--mfal", action="store_true",
                   help="Enable Multi-Factor Adaptive Leverage")
    p.add_argument("--mfal-no-micro", action="store_true",
                   help="Disable micro-structure factor M")
    p.add_argument("--mfal-no-time", action="store_true",
                   help="Disable time-of-day factor T")
    p.add_argument("--mfal-no-learn", action="store_true",
                   help="Disable online learning")
    p.add_argument("--mfal-weights", type=str, default=None,
                   help="Path to MFAL weights JSON")
    args = p.parse_args()"""


# ══════════════════════════════════════════════════════════════════════════
# M10 — main(): MFAL CLI wiring
# ══════════════════════════════════════════════════════════════════════════

M10_OLD = """    args = p.parse_args()

    CFG.mode = args.mode"""

M10_NEW = """    args = p.parse_args()

    # ══ [MFAL] CLI wiring ══
    try:
        if args.mfal:
            globals()['_MFAL_ENABLED'] = True
            if args.mfal_no_micro:
                globals()['_MFAL_USE_MICRO'] = False
            if args.mfal_no_time:
                globals()['_MFAL_USE_TIME'] = False
            if args.mfal_no_learn:
                globals()['_MFAL_USE_LEARNING'] = False
            if args.mfal_weights:
                globals()['_MFAL_WEIGHTS_PATH'] = str(args.mfal_weights)
            _mfal_load_weights()
            log.info(
                "[MFAL] ENABLED  "
                f"micro={_MFAL_USE_MICRO} "
                f"time={_MFAL_USE_TIME} "
                f"learn={_MFAL_USE_LEARNING}"
            )
        else:
            log.info("[MFAL] Disabled (use --mfal to enable)")
    except Exception as _e:
        log.warning(f"[MFAL] CLI wiring failed: {_e}")

    CFG.mode = args.mode"""


# ══════════════════════════════════════════════════════════════════════════
# M11 — run_live loop: periodic _mfal_log_stats()
# ══════════════════════════════════════════════════════════════════════════

M11_OLD = """        try:
            t0 = time.time()
            # ══ [RateLimit] periodic report ══
            _rate_report()
            # ══ [KILL SWITCH] check every cycle ══"""

M11_NEW = """        try:
            t0 = time.time()
            # ══ [RateLimit] periodic report ══
            _rate_report()
            # ══ [MFAL] periodic stats ══
            _mfal_log_stats()
            # ══ [KILL SWITCH] check every cycle ══"""


# ══════════════════════════════════════════════════════════════════════════
# Patcher
# ══════════════════════════════════════════════════════════════════════════

class Patcher:
    def __init__(self, path, dry_run=False):
        self.path = path
        self.dry_run = dry_run
        self.content = None
        self.backup_path = None
        self.results: List[Tuple[str, str]] = []

    def load(self):
        if not self.path.exists():
            print(f"{C.RED}  Not found: {self.path}{C.END}")
            return False
        try:
            self.content = self.path.read_text(encoding='utf-8')
            print(f"{C.CYAN}  Loaded {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Read error: {e}{C.END}")
            return False

    def backup(self):
        if self.dry_run:
            return True
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = self.path.with_suffix(
            self.path.suffix + f'.bak.{ts}')
        try:
            shutil.copy2(self.path, self.backup_path)
            print(f"{C.CYAN}  Backup: {self.backup_path.name}{C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Backup failed: {e}{C.END}")
            return False

    def replace(self, name, old, new, marker=None):
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name}")
            return True
        n = self.content.count(old)
        if n == 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name}")
            return False
        if n > 1:
            print(f"  {C.YELLOW}⚠ WARN{C.END}  {name}: {n} occurrences")
        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    def save(self):
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN -- not written{C.END}")
            return True
        if self.path.suffix == '.py':
            try:
                compile(self.content, str(self.path), 'exec')
            except SyntaxError as e:
                print(f"{C.RED}  Syntax error: {e}{C.END}")
                if self.backup_path and self.backup_path.exists():
                    shutil.copy2(self.backup_path, self.path)
                    print(f"{C.GREEN}  Restored from backup.{C.END}")
                return False
        try:
            self.path.write_text(self.content, encoding='utf-8')
            print(f"{C.GREEN}  Written {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Write failed: {e}{C.END}")
            return False

    def report(self):
        a = sum(1 for _, s in self.results if s == 'applied')
        s = sum(1 for _, s in self.results if s == 'skip')
        f = sum(1 for _, s in self.results if s == 'fail')
        print(f"\n  {C.BOLD}Summary:{C.END}  "
              f"{C.GREEN}applied={a}{C.END}, "
              f"{C.GRAY}skipped={s}{C.END}, "
              f"{C.RED}failed={f}{C.END}")
        return f


def restore_latest(path):
    backups = sorted(path.parent.glob(path.name + '.bak.*'),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print(f"{C.RED}No backups for {path.name}{C.END}")
        return False
    shutil.copy2(backups[0], path)
    print(f"{C.GREEN}✓ Restored from {backups[0].name}{C.END}")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bot", default="trading_2_live2.py")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.BOLD}  MFAL Patcher -- {bot.name}{C.END}")
    print(f"{C.BOLD}  Mode: {'DRY-RUN' if args.dry_run else 'APPLY'}{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if args.restore:
        sys.exit(0 if restore_latest(bot) else 1)
    if not bot.exists():
        print(f"{C.RED}File not found: {bot}{C.END}")
        sys.exit(2)

    pt = Patcher(bot, dry_run=args.dry_run)
    if not pt.load() or not pt.backup():
        sys.exit(3)

    print(f"\n{C.BOLD}═══ Group D: MFAL infrastructure ═══{C.END}\n")

    pt.replace("M1   Signal dataclass: mfal_x + mfal_p_act",
               M1_OLD, M1_NEW,
               marker="mfal_x: Optional[np.ndarray] = None")

    pt.replace("M2   Insert MFAL block",
               M2_ANCHOR, M2_BLOCK,
               marker="def compute_adaptive_leverage(symbol, sig, open_pos_live, capital,")

    print(f"\n{C.BOLD}═══ Group E: Trade lifecycle integration ═══{C.END}\n")

    pt.replace("M3   build_signals: extract + include MFAL",
               M3_OLD, M3_NEW,
               marker="mfal_x=_mfal_x,\n                mfal_p_act=float(P_activation),")

    pt.replace("M4   backtest _close: record MFAL",
               M4_OLD, M4_NEW,
               marker="[MFAL] Record trade outcome\n        try:\n            if _MFAL_ENABLED:")

    pt.replace("M5   live exit: record MFAL",
               M5_OLD, M5_NEW,
               marker="# ══ [MFAL] Record trade outcome ══\n                    try:")

    pt.replace("M6a  pending record: store sig_mfal_x",
               M6A_OLD, M6A_NEW,
               marker="rec['sig_mfal_x'] = (")

    pt.replace("M6b  promote: transfer _mfal_x to position",
               M6B_OLD, M6B_NEW,
               marker="# [MFAL] carry the signal-quality vector into the position record")

    print(f"\n{C.BOLD}═══ Group F: Leverage callsites + CLI ═══{C.END}\n")

    pt.replace("M7   backtest callsite -> compute_adaptive_leverage",
               M7_OLD, M7_NEW,
               marker="Leverage cap (MFAL-aware when --mfal is enabled)")

    pt.replace("M8   live callsite -> compute_adaptive_leverage",
               M8_OLD, M8_NEW,
               marker="dynamic_leverage = compute_adaptive_leverage(\n                        symbol=sym,")

    pt.replace("M9   main: MFAL CLI args",
               M9_OLD, M9_NEW,
               marker='p.add_argument("--mfal", action="store_true",')

    pt.replace("M10  main: MFAL CLI wiring",
               M10_OLD, M10_NEW,
               marker="# ══ [MFAL] CLI wiring ══")

    pt.replace("M11  run_live loop: periodic _mfal_log_stats()",
               M11_OLD, M11_NEW,
               marker="# ══ [MFAL] periodic stats ══")

    if not pt.save():
        sys.exit(4)
    failed = pt.report()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    if failed == 0:
        print(f"{C.GREEN}  ALL PATCHES APPLIED SUCCESSFULLY{C.END}")
    else:
        print(f"{C.RED}  {failed} PATCH(ES) FAILED{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if not failed and not args.dry_run:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify:  python3 -m py_compile {bot.name}")
        print(f"  2. Grep:    grep -n 'MFAL\\|compute_adaptive_leverage' {bot.name}")
        print(f"  3. Run backtest with MFAL:")
        print(f"     {C.BOLD}python3 {bot.name} --mode backtest --mfal ...{C.END}")
        print(f"  4. Or run live with MFAL:")
        print(f"     {C.BOLD}python3 {bot.name} --mode testnet --mfal ...{C.END}")
        print(f"  5. Revert:  python3 {Path(__file__).name} --restore")

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
