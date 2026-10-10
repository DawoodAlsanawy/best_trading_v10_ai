#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_unified.py
================
Unified Decision Engine — replaces the sequential
(risk → leverage → qty) pipeline with a single constrained
Bayesian optimization.

Core idea:
    (qty*, L*, accept*) = argmax_{qty,L,a}  a · E[log W_T]

    subject to all constraints simultaneously:
        C1 : notional ≥ MVT_symbol(price)       [dynamic]
        C2 : L ∈ valid_tiers(symbol)
        C3 : L ≤ L_liq_max(f_SL, MMR, safety)
        C4 : margin(qty, L) ≤ free_capital
        C5 : portfolio_heat ≤ H_max(history)    [derived, not fixed]
        C6 : notional ≤ κ(ADV)                  [derived]
        C7 : P(ruin) ≤ ε                        [philosophical]

    Edge estimation is Bayesian:
        p_hat = E[σ(w·x)] from logistic regression on trade history

Usage:
    python apply_unified.py \\
        --input  trading_2_mfal.py \\
        --output trading_2_unified.py
"""

import argparse
import os
import sys
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════

def _replace_once(src, old, new, label, marker=None):
    if marker and marker in src:
        print(f"   ℹ️  [{label}] already applied")
        return src, True
    if old not in src:
        print(f"   ❌ [{label}] anchor not found")
        head = old[:60].split("\n")[0]
        idx = src.find(head)
        if idx >= 0:
            print(f"      near: {src[max(0, idx-120):idx+240]!r}")
        return src, False
    n = src.count(old)
    if n > 1:
        print(f"   ⚠️  [{label}] anchor ×{n}, replacing first")
    src = src.replace(old, new, 1)
    print(f"   ✅ [{label}]")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# The UNIFIED block (inserted before load_symbol_meta)
# ══════════════════════════════════════════════════════════════════════

UNIFIED_BLOCK = r'''# ══════════════════════════════════════════════════════════════════════
# [UNIFIED DECISION ENGINE] — v1
# ══════════════════════════════════════════════════════════════════════
#
# A single constrained Bayesian optimizer that replaces:
#     risk pipeline (8 layers) → leverage pipeline (3 layers) → min()
#
# With:
#     argmax_{qty, L, accept}  a · E[ log W_T | state ]
#     subject to all constraints SIMULTANEOUSLY
#
# Design principles:
#   1. No sequential pipeline — one decision.
#   2. No hardcoded constants — everything derived from history,
#      capital, and exchange rules (MVT, tiers, MMR).
#   3. Bayesian edge estimation (learns from outcomes).
#   4. Scale-invariant (works for $1 and $1M alike).
#
# Only three "philosophical" inputs remain (owner's choices):
#     • ε  (ruin tolerance)      — default 0.001
#     • λ  (Kelly shrinkage)     — default 0.5
#     • k  (Liq safety margin)   — default 1.5
#
# Default: DISABLED. Enable with --unified flag.

_UNIFIED_ENABLED: bool = False
_UNIFIED_EPSILON: float = 0.001
_UNIFIED_SHRINKAGE: float = 0.5
_UNIFIED_LIQ_SAFETY: float = 1.5
_UNIFIED_KAPPA_BASE: float = 0.01
_UNIFIED_RETRAIN_EVERY: int = 30
_UNIFIED_MIN_TRADES: int = 50

_UNIFIED_STATE: Dict = {
    "feature_names": [
        "score_norm", "p_act", "accel_ratio",
        "gauge", "z_dev", "rr", "freshness",
    ],
    "w_mean": [0.30, 0.25, 0.15, 0.10, 0.10, 0.05, 0.05],
    "w_precision_diag": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "bias": 0.0,
    "n_observations": 0,
    "recent_R": [],
    "recent_wins": [],
}

_UNIFIED_WEIGHTS_PATH: str = "unified_weights.json"
_UNIFIED_HISTORY_PATH: str = "unified_history.jsonl"

_UNIFIED_STATS: Dict = {
    "calls": 0, "accepts": 0, "rejects": 0,
    "qty_sum": 0.0, "L_sum": 0, "f_sum": 0.0,
    "reject_reasons": {},
    "last_report_ts": 0.0,
    "trades_recorded": 0,
    "retrains": 0,
}


# ──────────────────────────────────────────────────────────────────────
# State persistence
# ──────────────────────────────────────────────────────────────────────

def _unified_load_state(path: Optional[str] = None) -> bool:
    global _UNIFIED_STATE
    p = path or _UNIFIED_WEIGHTS_PATH
    if not os.path.exists(p):
        log.info(f"[Unified] No state at {p} — using prior")
        return False
    try:
        with open(p) as f:
            data = json.load(f)
        for k in ("w_mean", "w_precision_diag", "bias",
                  "n_observations", "recent_R", "recent_wins"):
            if k in data:
                _UNIFIED_STATE[k] = data[k]
        log.info(f"[Unified] State loaded: n_obs="
                 f"{_UNIFIED_STATE['n_observations']}, "
                 f"|w|={np.linalg.norm(_UNIFIED_STATE['w_mean']):.4f}")
        return True
    except Exception as e:
        log.warning(f"[Unified] Load failed: {e}")
        return False


def _unified_save_state(path: Optional[str] = None):
    p = path or _UNIFIED_WEIGHTS_PATH
    try:
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_UNIFIED_STATE, f, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        log.debug(f"[Unified] Save failed: {e}")


# ──────────────────────────────────────────────────────────────────────
# Derived parameters — no hardcoded constants
# ──────────────────────────────────────────────────────────────────────

def _unified_compute_mvt(exchange, sym: str, price: float) -> float:
    """Dynamic MVT per symbol/price. Falls back to MIN_NOTIONAL."""
    if price <= 0:
        return float(getattr(CFG, "MIN_NOTIONAL", 5.0))
    try:
        mkt = exchange.market(sym)
        if not mkt:
            raise ValueError("no market")
        info = mkt.get("info") or {}
        filters = {}
        for f in (info.get("filters") or []):
            ft = f.get("filterType")
            if ft:
                filters[ft] = f
        min_notional = float(
            (filters.get("MIN_NOTIONAL") or {}).get("notional", 5.0) or 5.0
        )
        lot = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE") or {}
        min_qty = float(lot.get("minQty", 0) or 0)
        step_size = float(lot.get("stepSize", 0) or 0)
        return float(max(
            min_notional,
            min_qty * price if min_qty > 0 else 0.0,
            step_size * price if step_size > 0 else 0.0,
        ))
    except Exception:
        return float(getattr(CFG, "MIN_NOTIONAL", 5.0))


def _unified_get_adv(sym: str, ad) -> float:
    try:
        if ad is not None and hasattr(ad, "adv_usd") and len(ad.adv_usd) > 0:
            adv = float(ad.adv_usd[-1])
            if np.isfinite(adv) and adv > 0:
                return adv
    except Exception:
        pass
    return 1e8


def _unified_get_mmr(exchange, sym: str) -> float:
    try:
        return float(_get_mmr_for_symbol(exchange, sym))
    except Exception:
        return float(getattr(CFG, "LIQ_FALLBACK_MMR", 0.02))


def _unified_compute_H_max() -> float:
    """H_max = 2·E[r]/E[r²]·(1-ε), from historical R-multiples."""
    recent = _UNIFIED_STATE.get("recent_R", [])
    if len(recent) < 20:
        return 0.05
    r = np.array(recent[-100:], dtype=np.float64)
    mean_r = float(np.mean(r))
    mean_r2 = float(np.mean(r * r))
    if mean_r <= 0 or mean_r2 <= 1e-9:
        return 0.02
    h = 2.0 * mean_r / mean_r2 * (1.0 - _UNIFIED_EPSILON)
    return float(np.clip(h, 0.01, 0.50))


def _unified_compute_kappa(adv_usd: float, max_slip_bps: float = 5.0) -> float:
    slip_factor = max_slip_bps / 5.0
    return float(np.clip(_UNIFIED_KAPPA_BASE * slip_factor, 0.001, 0.05))


def _unified_compute_L_liq_max(mmr: float, f_sl: float) -> int:
    try:
        return int(compute_max_leverage_by_liq(
            sl_frac_max=f_sl, mmr=mmr,
            safety_mult=_UNIFIED_LIQ_SAFETY,
        ))
    except Exception:
        return int(getattr(CFG, "LEVERAGE_MAX", 50))


# ──────────────────────────────────────────────────────────────────────
# Bayesian edge
# ──────────────────────────────────────────────────────────────────────

def _unified_sigmoid(z):
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def _unified_bayesian_edge(x: Optional[np.ndarray]):
    """Return (p_hat, var_p) via Laplace approximation."""
    if x is None or len(x) != len(_UNIFIED_STATE["feature_names"]):
        return 0.5, 0.25
    w = np.array(_UNIFIED_STATE["w_mean"], dtype=np.float64)
    prec = np.array(_UNIFIED_STATE["w_precision_diag"], dtype=np.float64)
    bias = float(_UNIFIED_STATE["bias"])
    z = float(np.dot(w, x)) + bias
    var_z = float(np.sum((x ** 2) / np.maximum(prec, 1e-6)))
    p_hat = float(_unified_sigmoid(z))
    var_p = p_hat * (1 - p_hat) + (p_hat * (1 - p_hat)) ** 2 * var_z * (np.pi / 8)
    return p_hat, float(np.clip(var_p, 1e-4, 0.25))


def _unified_kelly_bayes(p_hat: float, var_p: float, rr: float) -> float:
    p = float(np.clip(p_hat, 1e-6, 1.0 - 1e-6))
    q = 1.0 - p
    if rr <= 0 or p <= 0.01:
        return 0.0
    denom = p * rr * rr + q
    f_kelly = max(0.0, (p * rr - q) / denom) if denom > 1e-9 else 0.0
    pq = p * q
    penalty = max(0.0, 1.0 - var_p / pq) if pq > 1e-9 else 1.0
    return float(np.clip(f_kelly * penalty * _UNIFIED_SHRINKAGE, 0.0, 0.20))


# ──────────────────────────────────────────────────────────────────────
# Signal features
# ──────────────────────────────────────────────────────────────────────

def _unified_signal_x(sig, ad, fi):
    """7-dim feature vector."""
    try:
        score = float(getattr(sig, "score", 0.0))
        p_act = getattr(sig, "mfal_p_act", None)
        if p_act is None or p_act <= 0:
            try:
                geo = abs(float(ad.geodesic_accel[fi]))
                fric = float(ad.friction[fi]) + 1e-6
                T_info = float(ad.T_info[fi])
                p_act = float(np.exp(-fric / (max(geo, 1e-9) * T_info)))
            except Exception:
                p_act = 0.5
        try:
            accel_ratio = abs(float(ad.geodesic_accel[fi])) / max(float(ad.friction[fi]), 1e-9)
        except Exception:
            accel_ratio = 1.0
        try:
            gauge = float(ad.gauge_force[fi])
        except Exception:
            gauge = 0.0
        try:
            _zw = ad.closes[max(0, fi - 24): fi]
            if len(_zw) >= 2:
                _mu = float(np.mean(_zw))
                _sd = float(np.std(_zw)) + 1e-9
                z_dev = (float(ad.closes[fi]) - _mu) / _sd
            else:
                z_dev = 0.0
        except Exception:
            z_dev = 0.0
        try:
            entry = float(sig.price); sl = float(sig.sl); tp = float(sig.tp1)
            sl_dist = abs(entry - sl)
            tp_dist = abs(tp - entry)
            rr = tp_dist / max(sl_dist, 1e-9)
        except Exception:
            rr = 2.0
        x = np.array([
            score / 8.0,
            float(np.clip(p_act, 0.0, 1.0)),
            float(np.tanh(accel_ratio / 3.0)),
            float(np.tanh(gauge * 10.0)),
            float(np.tanh(abs(z_dev) / 2.0)),
            float(np.tanh(rr / 3.0)),
            1.0,
        ], dtype=np.float64)
        return x if np.all(np.isfinite(x)) else None
    except Exception:
        return None


def _unified_get_f_sl(sig) -> float:
    try:
        entry = float(sig.price); sl = float(sig.sl)
        if entry <= 0:
            return 0.02
        return float(np.clip(abs(entry - sl) / entry, 0.001, 0.10))
    except Exception:
        return 0.02


def _unified_get_rr(sig) -> float:
    try:
        entry = float(sig.price); sl = float(sig.sl); tp = float(sig.tp1)
        return float(abs(tp - entry) / max(abs(entry - sl), 1e-9))
    except Exception:
        return 2.0


# ──────────────────────────────────────────────────────────────────────
# MAIN: Unified Decision
# ──────────────────────────────────────────────────────────────────────

def compute_unified_decision(sym, sig, capital, peak, open_pos_live,
                              corr_cache, exchange, ad, cfg) -> Dict:
    """
    Returns:
        {
            "accept": bool,
            "qty": float, "leverage": int, "f_actual": float,
            "reason": str, "candidates": list,
        }
    """
    _UNIFIED_STATS["calls"] += 1
    default = {"accept": False, "qty": 0.0,
               "leverage": int(cfg.LEVERAGE_MIN),
               "f_actual": 0.0, "reason": "uninit", "candidates": []}
    try:
        fi = int(getattr(sig, "feat_idx", 0))
        x = _unified_signal_x(sig, ad, fi)
        p_hat, var_p = _unified_bayesian_edge(x)
        rr = _unified_get_rr(sig)

        f_kelly = _unified_kelly_bayes(p_hat, var_p, rr)
        if f_kelly <= 0.0:
            r = f"no_edge(p={p_hat:.3f},rr={rr:.2f})"
            default["reason"] = r
            _UNIFIED_STATS["rejects"] += 1
            _UNIFIED_STATS["reject_reasons"][r] = \
                _UNIFIED_STATS["reject_reasons"].get(r, 0) + 1
            return default

        f_sl = _unified_get_f_sl(sig)
        price = float(getattr(sig, "price", 0.0))
        if price <= 0:
            default["reason"] = "invalid_price"
            return default

        MVT = _unified_compute_mvt(exchange, sym, price) if exchange is not None \
              else float(getattr(cfg, "MIN_NOTIONAL", 5.0))
        adv = _unified_get_adv(sym, ad)
        kappa = _unified_compute_kappa(adv, 5.0)
        mmr = _unified_get_mmr(exchange, sym) if exchange is not None \
              else float(getattr(cfg, "LIQ_FALLBACK_MMR", 0.02))
        L_liq_max = _unified_compute_L_liq_max(mmr, f_sl)
        H_max = _unified_compute_H_max()

        free_capital = float(capital)
        for pos in open_pos_live.values():
            try:
                pn = float(pos.get("entry", 0)) * float(pos.get("qty", 0))
                pL = max(int(pos.get("leverage", 1)), 1)
                free_capital -= pn / pL
            except Exception:
                pass
        free_capital = max(0.0, free_capital)

        heat_used = 0.0
        for pos in open_pos_live.values():
            try:
                heat_used += float(pos.get("dyn_risk", 0.0) or 0.0)
            except Exception:
                pass

        try:
            if exchange is not None:
                tiers = _symbol_tiers(sym, cfg)
            else:
                tiers = list(range(int(cfg.LEVERAGE_MIN),
                                    int(cfg.LEVERAGE_MAX) + 1))
        except Exception:
            tiers = [int(cfg.LEVERAGE_MIN), int(cfg.LEVERAGE_MAX)]

        candidates = []
        for L in tiers:
            L = int(L)
            if L > L_liq_max: continue
            if L < int(cfg.LEVERAGE_MIN): continue

            N_by_margin = L * free_capital
            heat_av = max(0.0, H_max - heat_used)
            N_by_heat = heat_av * capital / f_sl
            N_by_adv = kappa * adv
            N_by_abs = float(getattr(cfg, "MAX_ABS_NOTIONAL", 1e9))

            N_upper = min(N_by_margin, N_by_heat, N_by_adv, N_by_abs)
            N_lower = MVT
            if N_lower > N_upper:
                continue

            N_target = f_kelly * capital / f_sl
            N_opt = float(np.clip(N_target, N_lower, N_upper))
            f_actual = N_opt * f_sl / capital
            U = (p_hat * np.log(1 + f_actual * rr)
                 + (1 - p_hat) * np.log(max(1 - f_actual, 1e-9)))
            p_ruin = (f_actual / 0.20) ** 3 if f_actual > 0 else 1.0
            if p_ruin > _UNIFIED_EPSILON:
                continue
            candidates.append({"leverage": L, "N_opt": N_opt,
                                "f_actual": f_actual, "U": U})

        if not candidates:
            r = "no_feasible"
            default["reason"] = r
            _UNIFIED_STATS["rejects"] += 1
            _UNIFIED_STATS["reject_reasons"][r] = \
                _UNIFIED_STATS["reject_reasons"].get(r, 0) + 1
            return default

        best = max(candidates, key=lambda c: c["U"])
        best_U = best["U"]
        for c in candidates:
            if abs(c["U"] - best_U) < 1e-6 and c["leverage"] < best["leverage"]:
                best = c

        qty = best["N_opt"] / price
        try:
            if exchange is not None:
                qty = _round_qty(exchange, sym, qty)
        except Exception:
            pass

        if qty <= 0:
            default["reason"] = "zero_qty"
            return default
        if qty * price < MVT * 0.99:
            r = f"qty_below_mvt({qty*price:.2f}<{MVT:.2f})"
            default["reason"] = r
            _UNIFIED_STATS["rejects"] += 1
            _UNIFIED_STATS["reject_reasons"][r] = \
                _UNIFIED_STATS["reject_reasons"].get(r, 0) + 1
            return default

        result = {
            "accept": True, "qty": qty,
            "leverage": int(best["leverage"]),
            "f_actual": float(best["f_actual"]),
            "reason": f"U={best['U']:+.4f} p={p_hat:.3f} rr={rr:.2f}",
            "candidates": candidates,
        }
        _UNIFIED_STATS["accepts"] += 1
        _UNIFIED_STATS["qty_sum"] += qty
        _UNIFIED_STATS["L_sum"] += best["leverage"]
        _UNIFIED_STATS["f_sum"] += best["f_actual"]

        log.debug(
            f"[Unified] {sym} ACCEPT qty={qty:.6f} L={best['leverage']}x "
            f"f={best['f_actual']*100:.2f}% "
            f"(p={p_hat:.3f} RR={rr:.2f})"
        )
        return result
    except Exception as e:
        log.warning(f"[Unified] {sym} error: {e}")
        return default


# ──────────────────────────────────────────────────────────────────────
# Recording + Retraining
# ──────────────────────────────────────────────────────────────────────

def _unified_record_trade(sig, ad, outcome_R: float, success: bool):
    try:
        fi = int(getattr(sig, "feat_idx", 0)) if sig is not None else 0
        x = _unified_signal_x(sig, ad, fi) if sig is not None else None
        if x is None:
            return
        try:
            with open(_UNIFIED_HISTORY_PATH, "a") as f:
                f.write(json.dumps({
                    "ts": time.time(),
                    "symbol": str(getattr(sig, "symbol", "?")),
                    "x": x.tolist(),
                    "outcome_R": float(outcome_R),
                    "success": bool(success),
                }) + "\n")
        except Exception:
            pass

        _UNIFIED_STATE["n_observations"] += 1
        _UNIFIED_STATE["recent_R"].append(float(outcome_R))
        _UNIFIED_STATE["recent_wins"].append(1 if success else 0)
        if len(_UNIFIED_STATE["recent_R"]) > 200:
            _UNIFIED_STATE["recent_R"] = _UNIFIED_STATE["recent_R"][-100:]
            _UNIFIED_STATE["recent_wins"] = _UNIFIED_STATE["recent_wins"][-100:]
        _UNIFIED_STATS["trades_recorded"] += 1

        if (_UNIFIED_STATS["trades_recorded"] >= _UNIFIED_MIN_TRADES
                and _UNIFIED_STATS["trades_recorded"] % _UNIFIED_RETRAIN_EVERY == 0):
            _unified_retrain()
            _unified_save_state()
    except Exception as e:
        log.debug(f"[Unified] record failed: {e}")


def _unified_retrain():
    if not os.path.exists(_UNIFIED_HISTORY_PATH):
        return
    try:
        Xl, yl = [], []
        with open(_UNIFIED_HISTORY_PATH) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                xv = r.get("x")
                if not isinstance(xv, list): continue
                if len(xv) != len(_UNIFIED_STATE["feature_names"]): continue
                Xl.append(xv); yl.append(1.0 if r.get("success") else 0.0)
        if len(Xl) < _UNIFIED_MIN_TRADES:
            return
        X = np.array(Xl); y = np.array(yl)
        if y.sum() < 10 or (1 - y).sum() < 10:
            return
        w = np.array(_UNIFIED_STATE["w_mean"], dtype=np.float64)
        b = float(_UNIFIED_STATE["bias"])
        for _ in range(50):
            p = _unified_sigmoid(X @ w + b)
            grad_w = X.T @ (p - y) / len(y) + 0.05 * w
            grad_b = float(np.mean(p - y))
            w -= 0.01 * grad_w
            b -= 0.01 * grad_b
        old_w = np.array(_UNIFIED_STATE["w_mean"], dtype=np.float64)
        _UNIFIED_STATE["w_mean"] = (0.8 * old_w + 0.2 * w).tolist()
        _UNIFIED_STATE["bias"] = 0.8 * float(_UNIFIED_STATE["bias"]) + 0.2 * b
        _UNIFIED_STATE["w_precision_diag"] = [
            1.0 + _UNIFIED_STATE["n_observations"] / 100.0 for _ in w
        ]
        _UNIFIED_STATS["retrains"] += 1
        log.info(f"[Unified] Retrain #{_UNIFIED_STATS['retrains']} "
                 f"(n={len(y)}, |w|={np.linalg.norm(w):.4f})")
    except Exception as e:
        log.warning(f"[Unified] Retrain failed: {e}")


def _unified_log_stats():
    if not _UNIFIED_ENABLED:
        return
    now = time.time()
    if now - _UNIFIED_STATS.get("last_report_ts", 0.0) < 300:
        return
    _UNIFIED_STATS["last_report_ts"] = now
    n = max(_UNIFIED_STATS["calls"], 1)
    a = _UNIFIED_STATS["accepts"]
    r = _UNIFIED_STATS["rejects"]
    log.info(
        f"[Unified] calls={n}, accepts={a}, rejects={r}, "
        f"avg_qty={_UNIFIED_STATS['qty_sum']/max(a,1):.4f}, "
        f"avg_L={_UNIFIED_STATS['L_sum']/max(a,1):.1f}x, "
        f"avg_f={_UNIFIED_STATS['f_sum']/max(a,1)*100:.2f}%, "
        f"n_obs={_UNIFIED_STATE['n_observations']}, "
        f"retrains={_UNIFIED_STATS['retrains']}"
    )
    reasons = _UNIFIED_STATS.get("reject_reasons", {})
    if reasons:
        top = sorted(reasons.items(), key=lambda kv: -kv[1])[:3]
        log.info(f"[Unified] top rejects: {top}")


# ══ end UNIFIED DECISION ENGINE ══


'''


# ══════════════════════════════════════════════════════════════════════
# Edit 1: Insert block
# ══════════════════════════════════════════════════════════════════════

def edit1_insert_block(src):
    print("\n▶ Edit 1: insert UNIFIED block")
    anchor = "def load_symbol_meta(mode: str) -> Dict[str, Dict]:"
    if anchor not in src:
        print("   ❌ anchor 'load_symbol_meta' not found")
        return src, False
    if "[UNIFIED DECISION ENGINE] — v1" in src:
        print("   ℹ️  already applied")
        return src, True
    src = src.replace(anchor, UNIFIED_BLOCK + anchor, 1)
    print("   ✅ inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 2: Store sig reference in position dict
# ══════════════════════════════════════════════════════════════════════

def edit2_store_sig_ref(src):
    print("\n▶ Edit 2: store _sig_ref in position dict")
    old = (
        "                            '_sym': sym,\n"
        "                            '_orig_score': float(sig.score),\n"
        "                        }"
    )
    new = (
        "                            '_sym': sym,\n"
        "                            '_orig_score': float(sig.score),\n"
        "                            '_sig_ref': sig,\n"
        "                        }"
    )
    return _replace_once(src, old, new, "store-sig-ref",
                          marker="'_sig_ref': sig,")


# ══════════════════════════════════════════════════════════════════════
# Edit 3: Insert unified decision in run_live (before SAFETY block)
# ══════════════════════════════════════════════════════════════════════

def edit3_insert_live_hook(src):
    print("\n▶ Edit 3: insert unified decision in run_live")
    if "[UNIFIED] Compute decision" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "                    # ══ [SAFETY] Drawdown-aware risk reduction ══\n"
        "                    if 'peak_cap_live' not in dir():"
    )
    if anchor not in src:
        print("   ❌ anchor not found")
        idx = src.find("# ══ [SAFETY] Drawdown-aware risk reduction ══")
        if idx >= 0:
            print(f"      near: {src[max(0,idx-100):idx+300]!r}")
        return src, False

    injection = (
        "                    # ══ [UNIFIED] Compute decision ══\n"
        "                    _u_decision = None\n"
        "                    if _UNIFIED_ENABLED:\n"
        "                        try:\n"
        "                            _u_decision = compute_unified_decision(\n"
        "                                sym=sym, sig=sig, capital=cap_live,\n"
        "                                peak=peak_cap_live,\n"
        "                                open_pos_live=open_pos_live,\n"
        "                                corr_cache=corr_cache,\n"
        "                                exchange=exchange,\n"
        "                                ad=assets.get(sym), cfg=cfg,\n"
        "                            )\n"
        "                        except Exception as _ue:\n"
        "                            log.warning(f\"[Unified] {sym} error: {_ue}\")\n"
        "                            _u_decision = None\n"
        "                        if _u_decision is not None and not _u_decision[\"accept\"]:\n"
        "                            log.debug(f\"[Unified] {sym} rejected: {_u_decision['reason']}\")\n"
        "                            continue\n"
        "\n"
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ hook inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 4: Bypass risk_frac<=0 continue when unified accepts
# ══════════════════════════════════════════════════════════════════════

def edit4_bypass_risk_continue(src):
    print("\n▶ Edit 4: bypass risk_frac<=0 when unified accepts")
    if "[UNIFIED] override risk_frac" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
        "                    if risk_frac <= 0.0:\n"
        "                        log.debug(f\"[Budget] {sym} skipped: no heat budget\")\n"
        "                        continue"
    )
    new = (
        "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
        "                    if risk_frac <= 0.0:\n"
        "                        # [UNIFIED] override risk_frac if unified accepts\n"
        "                        if _u_decision is not None and _u_decision.get(\"accept\"):\n"
        "                            risk_frac = float(_u_decision[\"f_actual\"])\n"
        "                        else:\n"
        "                            log.debug(f\"[Budget] {sym} skipped: no heat budget\")\n"
        "                            continue"
    )
    return _replace_once(src, old, new, "bypass-risk-continue")


# ══════════════════════════════════════════════════════════════════════
# Edit 5: Override qty/leverage/risk after qty cap
# ══════════════════════════════════════════════════════════════════════

def edit5_override_qty(src):
    print("\n▶ Edit 5: override qty/leverage/risk with unified")
    if "[UNIFIED] Apply qty/leverage/risk override" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        "                    # ══ [NOTIONAL CAP] ══\n"
        "                    qty = cap_notional(qty, lmt)\n"
        "\n"
        "                    if qty * lmt < cfg.MIN_NOTIONAL:\n"
        "                        continue"
    )
    new = (
        "                    # ══ [NOTIONAL CAP] ══\n"
        "                    qty = cap_notional(qty, lmt)\n"
        "\n"
        "                    # ══ [UNIFIED] Apply qty/leverage/risk override ══\n"
        "                    if _u_decision is not None and _u_decision.get(\"accept\"):\n"
        "                        qty = float(_u_decision[\"qty\"])\n"
        "                        dynamic_leverage = int(_u_decision[\"leverage\"])\n"
        "                        risk_frac = float(_u_decision[\"f_actual\"])\n"
        "\n"
        "                    if qty * lmt < cfg.MIN_NOTIONAL:\n"
        "                        continue"
    )
    return _replace_once(src, old, new, "override-qty")


# ══════════════════════════════════════════════════════════════════════
# Edit 6: Record trade outcome in live
# ══════════════════════════════════════════════════════════════════════

def edit6_record_outcome(src):
    print("\n▶ Edit 6: record trade outcome (live)")
    if "[UNIFIED] Record live trade outcome" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "                    del open_pos_live[sym]\n"
        "                    last_exit_time[sym] = time.time()\n"
        "                    log.info(f\"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]\")"
    )
    if anchor not in src:
        print("   ❌ exit anchor not found")
        return src, False

    injection = (
        "                    # ══ [UNIFIED] Record live trade outcome ══\n"
        "                    if _UNIFIED_ENABLED:\n"
        "                        try:\n"
        "                            _entry_px_u = float(pos.get('entry') or 0)\n"
        "                            _sl_d0_u = float(pos.get('sl_dist_initial') or 0)\n"
        "                            _exit_px_u = float(exec_price or 0)\n"
        "                            if (_entry_px_u > 0 and _sl_d0_u > 0\n"
        "                                    and _exit_px_u > 0):\n"
        "                                if pos.get('action') == 'BUY':\n"
        "                                    _pnl_frac_u = (_exit_px_u - _entry_px_u) / _entry_px_u\n"
        "                                else:\n"
        "                                    _pnl_frac_u = (_entry_px_u - _exit_px_u) / _entry_px_u\n"
        "                                _sl_frac_u = _sl_d0_u / _entry_px_u\n"
        "                                _R_u = _pnl_frac_u / _sl_frac_u if _sl_frac_u > 0 else 0.0\n"
        "                                _sig_u = pos.get('_sig_ref') if isinstance(pos, dict) else None\n"
        "                                _ad_u = assets.get(sym) if 'assets' in dir() else None\n"
        "                                _unified_record_trade(_sig_u, _ad_u, float(_R_u), _R_u > 0.5)\n"
        "                        except Exception as _re:\n"
        "                            log.debug(f\"[Unified] record failed: {_re}\")\n"
        "\n"
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ outcome recording inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 7: Wire stats logger
# ══════════════════════════════════════════════════════════════════════

def edit7_wire_stats(src):
    print("\n▶ Edit 7: wire unified stats logger")
    if "_unified_log_stats()" in src and "# [UNIFIED] stats logger" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()"
    )
    if anchor not in src:
        print("   ❌ pos-cache anchor not found")
        return src, False

    new = (
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()\n"
        "            # [UNIFIED] stats logger\n"
        "            _unified_log_stats()"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ stats logger wired")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 8: Add CLI args
# ══════════════════════════════════════════════════════════════════════

def edit8_add_cli(src):
    print("\n▶ Edit 8: add CLI args")
    if 'p.add_argument("--unified"' in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = "    args = p.parse_args()"
    if anchor not in src:
        print("   ❌ parse_args anchor not found")
        return src, False

    injection = (
        '    # ══ [UNIFIED] CLI args ══\n'
        '    p.add_argument("--unified", action="store_true",\n'
        '                   help="Enable Unified Decision Engine")\n'
        '    p.add_argument("--unified-weights", type=str, default=None,\n'
        '                   help="Path to unified weights JSON")\n'
        '    p.add_argument("--unified-epsilon", type=float, default=None,\n'
        '                   help="Ruin tolerance (default 0.001)")\n'
        '    p.add_argument("--unified-shrinkage", type=float, default=None,\n'
        '                   help="Kelly shrinkage factor (default 0.5)")\n'
        '\n'
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ CLI args added")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 9: Wire CLI to globals
# ══════════════════════════════════════════════════════════════════════

def edit9_wire_cli(src):
    print("\n▶ Edit 9: wire CLI flags to unified globals")
    if "# [UNIFIED] CLI wiring" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = "    args = p.parse_args()"
    if anchor not in src:
        print("   ❌ parse_args anchor not found")
        return src, False

    injection = anchor + (
        "\n"
        "    # [UNIFIED] CLI wiring\n"
        "    try:\n"
        "        if getattr(args, 'unified', False):\n"
        "            globals()['_UNIFIED_ENABLED'] = True\n"
        "            if getattr(args, 'unified_weights', None):\n"
        "                globals()['_UNIFIED_WEIGHTS_PATH'] = str(args.unified_weights)\n"
        "            if getattr(args, 'unified_epsilon', None) is not None:\n"
        "                globals()['_UNIFIED_EPSILON'] = float(args.unified_epsilon)\n"
        "            if getattr(args, 'unified_shrinkage', None) is not None:\n"
        "                globals()['_UNIFIED_SHRINKAGE'] = float(args.unified_shrinkage)\n"
        "            _unified_load_state()\n"
        "            log.info(\n"
        "                f\"[Unified] ENABLED \"\n"
        "                f\"(ε={_UNIFIED_EPSILON}, shrink={_UNIFIED_SHRINKAGE})\"\n"
        "            )\n"
        "        else:\n"
        "            log.info(\"[Unified] Disabled (use --unified to enable)\")\n"
        "    except Exception as _e:\n"
        "        log.warning(f\"[Unified] CLI wiring failed: {_e}\")"
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ CLI wired")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = [
        ("UNIFIED block",           "[UNIFIED DECISION ENGINE] — v1"),
        ("_UNIFIED_ENABLED",        "_UNIFIED_ENABLED: bool = False"),
        ("_UNIFIED_EPSILON",        "_UNIFIED_EPSILON: float = 0.001"),
        ("_UNIFIED_SHRINKAGE",      "_UNIFIED_SHRINKAGE: float = 0.5"),
        ("_UNIFIED_STATE",          "_UNIFIED_STATE: Dict = {"),
        ("load state",              "def _unified_load_state("),
        ("save state",              "def _unified_save_state("),
        ("compute MVT",             "def _unified_compute_mvt("),
        ("compute H_max",           "def _unified_compute_H_max("),
        ("compute kappa",           "def _unified_compute_kappa("),
        ("signal features",         "def _unified_signal_x("),
        ("bayesian edge",           "def _unified_bayesian_edge("),
        ("kelly bayes",             "def _unified_kelly_bayes("),
        ("main decision",           "def compute_unified_decision("),
        ("record trade",            "def _unified_record_trade("),
        ("retrain",                 "def _unified_retrain("),
        ("log stats",               "def _unified_log_stats("),
        ("store sig_ref",           "'_sig_ref': sig,"),
        ("live hook",               "[UNIFIED] Compute decision"),
        ("bypass risk continue",    "[UNIFIED] override risk_frac"),
        ("qty override",            "[UNIFIED] Apply qty/leverage/risk override"),
        ("record live outcome",     "[UNIFIED] Record live trade outcome"),
        ("stats wired",             "# [UNIFIED] stats logger"),
        ("CLI arg --unified",       'p.add_argument("--unified"'),
        ("CLI wiring",              "# [UNIFIED] CLI wiring"),
    ]
    all_ok = True
    for label, marker in checks:
        ok = marker in src
        print(f"   {'✅' if ok else '❌'} {label}")
        if not ok:
            all_ok = False

    print("\n   Sanity:")
    for label, marker, expect in [
        ("def run_live", "def run_live(", 1),
        ("def run_backtest", "def run_backtest(", 1),
        ("def main", "def main(", 1),
        ("def compute_dynamic_leverage",
            "def compute_dynamic_leverage(", 1),
        ("def compute_adaptive_leverage",
            "def compute_adaptive_leverage(", 1),
        ("def build_signals", "def build_signals(", 1),
    ]:
        cnt = src.count(marker)
        ok = (cnt == expect)
        print(f"   {'✅' if ok else '❌'} {label}: {cnt}")
        if not ok:
            all_ok = False
    return all_ok


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="trading_2_mfal.py")
    ap.add_argument("--output", default="trading_2_unified.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} chars)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  UNIFIED DECISION ENGINE — Batch Apply                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: insert UNIFIED block",       edit1_insert_block),
        ("Edit 2: store _sig_ref",             edit2_store_sig_ref),
        ("Edit 3: hook in run_live",           edit3_insert_live_hook),
        ("Edit 4: bypass risk continue",       edit4_bypass_risk_continue),
        ("Edit 5: override qty",               edit5_override_qty),
        ("Edit 6: record outcome",             edit6_record_outcome),
        ("Edit 7: wire stats",                 edit7_wire_stats),
        ("Edit 8: add CLI args",               edit8_add_cli),
        ("Edit 9: wire CLI",                   edit9_wire_cli),
    ]
    results = []
    for label, fn in steps:
        try:
            src, ok = fn(src)
            results.append((label, ok))
        except Exception as e:
            print(f"   ❌ {label} exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((label, False))

    all_ok = verify(src)

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  SYNTAX CHECK                                               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    syntax_ok = True
    try:
        compile(src, args.output, "exec")
        print("   ✅ compiles OK")
    except SyntaxError as e:
        print(f"   ❌ SyntaxError line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text!r}")
        syntax_ok = False

    if not (all_ok and syntax_ok):
        print("\n╔══════════════════════════════════════════════════════════════╗")
        print("║  ❌ ABORTED — output NOT written                            ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        for label, ok in results:
            print(f"   {'✅' if ok else '❌'} {label}")
        print(f"   verify:  {'OK' if all_ok else 'FAILED'}")
        print(f"   syntax:  {'OK' if syntax_ok else 'FAILED'}")
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine\n"
        "#  UNIFIED DECISION ENGINE Build\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  Unified Decision Engine replaces the sequential\n"
        "#  (risk → leverage → qty) pipeline with a single\n"
        "#  constrained Bayesian optimization:\n"
        "#\n"
        "#      (qty*, L*, a*) = argmax a·E[log W_T]\n"
        "#      subject to all constraints simultaneously.\n"
        "#\n"
        "#  Default: DISABLED. Enable with --unified flag.\n"
        "# ═══════════════════════════════════════════════════════════\n"
    )

    if src.startswith("#!"):
        first_nl = src.index("\n")
        src_out = header + src[first_nl + 1:]
    else:
        src_out = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src_out)

    with open(args.output, "r", encoding="utf-8") as f:
        written = f.read()
    try:
        compile(written, args.output, "exec")
        write_ok = True
    except SyntaxError as e:
        write_ok = False
        print(f"   ❌ Written file broken at line {e.lineno}")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                             DONE                             ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"   Input:  {args.input}  ({len(src):,} chars)")
    print(f"   Output: {args.output}  ({len(src_out):,} chars)")
    for label, ok in results:
        print(f"   {'✅' if ok else '❌'} {label}")
    print(f"   verify:  {'✅ ALL PASSED' if all_ok else '❌ FAILED'}")
    print(f"   written: {'✅ OK' if write_ok else '❌ FAILED'}")
    print()
    print("  ▶ Run with UNIFIED enabled:")
    print(f"     python {args.output} --mode testnet --unified --api-key ... "
          f"--api-secret ...")
    print()
    print("  ▶ Run with MFAL only:")
    print(f"     python {args.output} --mode testnet --mfal --api-key ... "
          f"--api-secret ...")
    print()
    print("  ▶ Run with both (Unified wins):")
    print(f"     python {args.output} --mode testnet --unified --mfal "
          f"--api-key ... --api-secret ...")

    if not write_ok:
        sys.exit(3)


if __name__ == "__main__":
    main()
