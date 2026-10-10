#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_mfal.py
=============
MFAL — Multi-Factor Adaptive Leverage للبوت الحالي.

المكونات المُضافة:
    1. Quality Factor Q     — جودة الإشارة (أوزان مُتعلَّمة)
    2. Risk Factor R        — قدرة المحفظة
    3. Time Factor T        — سيولة حسب ساعة UTC
    4. Micro Factor M       — سبريد/عمق دفتر الأوامر
    5. Online Learning      — تحديث أوزان Q من التاريخ
    6. Persistence          — حفظ الأوزان في JSON

الفلسفة:
    L_final = L_core × Q × R × T × M
    ثم clamp بواسطة L_liq و L_symbol_max و L_min

الاستخدام:
    python apply_mfal.py \\
        --input  trading_2_complete4.py \\
        --output trading_2_mfal.py
"""

import argparse
import os
import re
import sys
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════
# الأدوات المساعدة
# ══════════════════════════════════════════════════════════════════════

def _find_function_bounds(src, func_name):
    """يرجع (start, end) لحدود دالة عُلْيا في الملف."""
    pat = re.compile(r"^def " + re.escape(func_name) + r"\(",
                     re.MULTILINE)
    m = pat.search(src)
    if not m:
        return None
    start = m.start()
    end_pat = re.compile(r"^(?:def |class |if __name__)",
                          re.MULTILINE)
    m2 = end_pat.search(src, m.end())
    end = m2.start() if m2 else len(src)
    return start, end


def _replace_func(src, name, new_body, label):
    bounds = _find_function_bounds(src, name)
    if bounds is None:
        print(f"   ❌ [{label}] function '{name}' not found")
        return src, False
    s, e = bounds
    src = src[:s] + new_body + src[e:]
    print(f"   ✅ [{label}] {name} replaced")
    return src, True


def _replace_once(src, old, new, label, marker=None):
    if marker and marker in src:
        print(f"   ℹ️  [{label}] already applied")
        return src, True
    if old not in src:
        print(f"   ❌ [{label}] anchor not found")
        # اطبع سياق مفيد
        head = old[:60].split("\n")[0]
        idx = src.find(head)
        if idx >= 0:
            print(f"      near: {src[max(0, idx-100):idx+200]!r}")
        return src, False
    n = src.count(old)
    if n > 1:
        print(f"   ⚠️  [{label}] anchor ×{n}, replacing first")
    src = src.replace(old, new, 1)
    print(f"   ✅ [{label}]")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# كتلة MFAL — تُدرج قبل load_symbol_meta
# ══════════════════════════════════════════════════════════════════════

MFAL_BLOCK = r'''# ══════════════════════════════════════════════════════════════════════
# [MFAL] Multi-Factor Adaptive Leverage
# ══════════════════════════════════════════════════════════════════════
#
# Philosophy:
#   Leverage is NOT a single number derived from one formula.
#   It is a DECISION that fuses multiple independent factors:
#
#       L_final = L_core × Q × R × T × M
#
#   where:
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
    "q_min": float("inf"),
    "q_max": float("-inf"),
    "q_sum": 0.0,
    "r_min": float("inf"),
    "r_max": float("-inf"),
    "r_sum": 0.0,
    "l_core_sum": 0.0,
    "l_final_sum": 0.0,
    "trades_recorded": 0,
    "retrains": 0,
    "last_report_ts": 0.0,
}
_MFAL_RECENT_R: List[float] = []   # آخر 50 نتيجة R-multiple


# ──────────────────────────────────────────────────────────────────────
# Load / Save weights
# ──────────────────────────────────────────────────────────────────────

def _mfal_load_weights(path: Optional[str] = None):
    global _MFAL_WEIGHTS, _MFAL_BIAS
    p = path or _MFAL_WEIGHTS_PATH
    if not os.path.exists(p):
        log.info(f"[MFAL] No weights file at {p} — using defaults")
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


def _mfal_save_weights(path: Optional[str] = None):
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
        log.debug(f"[MFAL] Weights saved to {p}")
    except Exception as e:
        log.warning(f"[MFAL] Save failed: {e}")


# ──────────────────────────────────────────────────────────────────────
# Feature extraction
# ──────────────────────────────────────────────────────────────────────

def _mfal_signal_features(score, p_act, accel_ratio, gauge,
                          z_dev, rr):
    """
    [MFAL] 7-dimensional feature vector from signal-time data.
    All features normalized to roughly [-1, +1] or [0, 1].
    """
    try:
        x = np.array([
            float(score) / 8.0,
            float(p_act),
            float(np.tanh(accel_ratio / 3.0)),
            float(np.tanh(gauge * 10.0)),
            float(np.tanh(abs(z_dev) / 2.0)),
            float(np.tanh(rr / 3.0)),
            1.0,   # freshness (1.0 for fresh signal)
        ], dtype=np.float64)
        if not np.all(np.isfinite(x)):
            return None
        return x
    except Exception:
        return None


def _mfal_quality(x: Optional[np.ndarray]) -> float:
    """Q = 0.4 + 1.4·σ(w·x), range [0.4, 1.8]."""
    if x is None:
        return 1.0
    try:
        z = float(np.dot(_MFAL_WEIGHTS, x)) + _MFAL_BIAS
        s = 1.0 / (1.0 + np.exp(-np.clip(z, -20.0, 20.0)))
        q = 0.4 + 1.4 * s
        return float(np.clip(q, 0.40, 1.80))
    except Exception:
        return 1.0


def _mfal_time_factor(now_ts: Optional[float] = None) -> float:
    """
    Time-of-day multiplier. Based on typical crypto liquidity:
      Asia night (0-3):    0.75 - 0.85
      London open (7-10):  0.95 - 1.05
      LD/NY overlap (13-16): 1.10 - 1.15
      NY close (20-23):    0.85 - 0.90
    """
    try:
        if now_ts is None:
            now_ts = time.time()
        h = datetime.utcfromtimestamp(now_ts).hour
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


def _mfal_micro_factor(exchange, sym: str) -> float:
    """
    Micro-structure multiplier from current book.
    Uses 5-level book (weight ~5).
    """
    if not _MFAL_USE_MICRO:
        return 1.0
    try:
        ob = exchange.fetch_order_book(sym, limit=5)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        if not bids or not asks:
            return 1.0
        bb = float(bids[0][0])
        ba = float(asks[0][0])
        if bb <= 0 or ba <= 0 or ba < bb:
            return 1.0
        mid = (bb + ba) / 2.0
        spread_bps = (ba - bb) / mid * 1e4

        # depth of top 5 levels
        depth_bid = sum(float(x[1]) for x in bids[:5]) * bb
        depth_ask = sum(float(x[1]) for x in asks[:5]) * ba
        depth_usd = (depth_bid + depth_ask) / 2.0

        # Typical thresholds (very conservative baselines)
        typical_spread = 3.0    # bps
        typical_depth  = 1.0e5  # USD

        f_spread = float(np.clip(
            (typical_spread / max(spread_bps, 0.1)) ** 0.5,
            0.60, 1.20,
        ))
        f_depth = float(np.clip(
            (depth_usd / typical_depth) ** 0.30,
            0.70, 1.10,
        ))
        return float(np.clip(f_spread * f_depth, 0.42, 1.32))
    except Exception as e:
        log.debug(f"[MFAL] micro_factor failed for {sym}: {e}")
        return 1.0


def _mfal_portfolio_factor(sym: str,
                            open_pos_live: Dict,
                            capital: float,
                            peak_capital: float,
                            corr_cache: Dict) -> float:
    """
    Portfolio capacity multiplier:
        R = R_corr × R_heat × R_dd × R_perf
    """
    try:
        # ── R_corr: max correlation with existing positions ──
        if open_pos_live and corr_cache:
            rho_max = 0.0
            for other in open_pos_live.keys():
                rho = abs(float(corr_cache.get((sym, other), 0.0)))
                if rho > rho_max:
                    rho_max = rho
            R_corr = 1.0 - 0.5 * rho_max
        else:
            R_corr = 1.0

        # ── R_heat: portfolio heat usage ──
        heat_max = float(getattr(CFG, "PORTFOLIO_HEAT_MAX", 0.10))
        heat_used = 0.0
        for p in open_pos_live.values():
            try:
                heat_used += float(p.get("dyn_risk", 0.0) or 0.0)
            except Exception:
                pass
        if heat_max > 1e-9:
            R_heat = 1.0 - 0.4 * min(1.0, heat_used / heat_max)
        else:
            R_heat = 1.0

        # ── R_dd: current drawdown ──
        if peak_capital > 1e-9:
            dd = max(0.0, (peak_capital - capital) / peak_capital)
        else:
            dd = 0.0
        R_dd = float(np.exp(-3.0 * dd))

        # ── R_perf: recent rolling Sharpe ──
        if len(_MFAL_RECENT_R) >= 10:
            r = np.array(_MFAL_RECENT_R[-50:], dtype=np.float64)
            mu = float(np.mean(r))
            sd = float(np.std(r, ddof=1)) if len(r) > 1 else 0.0
            if sd > 1e-9:
                sharpe = mu / sd * np.sqrt(len(r))
            else:
                sharpe = 0.0
            R_perf = float(np.clip(0.9 + 0.1 * sharpe, 0.70, 1.20))
        else:
            R_perf = 1.0

        R = R_corr * R_heat * R_dd * R_perf
        return float(np.clip(R, 0.30, 1.30))
    except Exception as e:
        log.debug(f"[MFAL] portfolio_factor failed: {e}")
        return 1.0


# ──────────────────────────────────────────────────────────────────────
# Main entry — combines everything
# ──────────────────────────────────────────────────────────────────────

def compute_adaptive_leverage(symbol: str,
                                sig,
                                open_pos_live: Optional[Dict],
                                capital: float,
                                peak_capital: float,
                                corr_cache: Optional[Dict],
                                exchange,
                                cfg) -> int:
    """
    [MFAL] Adaptive leverage:
        L_final = clamp(L_core × Q × R × T × M, L_min, min(L_liq, L_sym))
    """
    # ── 1. Core (unchanged physics) ──
    L_core = int(compute_dynamic_leverage(capital, cfg, symbol=symbol))

    if not _MFAL_ENABLED:
        return L_core

    # ── 2. Quality factor ──
    x = getattr(sig, "mfal_x", None) if sig is not None else None
    Q = _mfal_quality(x)

    # ── 3. Risk factor ──
    R = _mfal_portfolio_factor(
        sym=symbol,
        open_pos_live=open_pos_live or {},
        capital=capital,
        peak_capital=peak_capital,
        corr_cache=corr_cache or {},
    )

    # ── 4. Time factor ──
    T = _mfal_time_factor() if _MFAL_USE_TIME else 1.0

    # ── 5. Micro factor ──
    M = _mfal_micro_factor(exchange, symbol) if _MFAL_USE_MICRO else 1.0

    # ── 6. Score product ──
    L_scored = L_core * Q * R * T * M

    # ── 7. Hard constraints ──
    try:
        _mmr = _get_mmr_for_symbol(exchange, symbol)
        _sl_frac_max = 0.015 * float(
            getattr(cfg, "SL_WIDEN_MULT", 1.5)
        )
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

    # ── 8. Snap to tiers ──
    try:
        tiers = _symbol_tiers(symbol, cfg)
        valid = [int(t) for t in tiers
                 if L_min <= int(t) <= L_final]
        if valid:
            L_final = int(valid[-1])
        else:
            L_final = L_min
    except Exception:
        pass

    # ── 9. Stats ──
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


# ──────────────────────────────────────────────────────────────────────
# Trade recording + online learning
# ──────────────────────────────────────────────────────────────────────

def _mfal_record_trade(sig, outcome_R: float, success: bool):
    """يُسجّل نتيجة صفقة في history ويُحدّث stats."""
    try:
        x = getattr(sig, "mfal_x", None) if sig is not None else None
        if x is None:
            return
        record = {
            "ts": time.time(),
            "symbol": str(getattr(sig, "symbol", "?")),
            "x": x.tolist(),
            "outcome_R": float(outcome_R),
            "success": bool(success),
        }
        try:
            with open(_MFAL_HISTORY_PATH, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

        _MFAL_RECENT_R.append(float(outcome_R))
        if len(_MFAL_RECENT_R) > 200:
            _MFAL_RECENT_R[:] = _MFAL_RECENT_R[-100:]

        _MFAL_STATS["trades_recorded"] += 1

        # Trigger retrain if enough new trades
        if (_MFAL_USE_LEARNING
                and _MFAL_STATS["trades_recorded"]
                    >= _MFAL_MIN_TRADES_FOR_LEARNING
                and _MFAL_STATS["trades_recorded"]
                    % _MFAL_RETRAIN_EVERY == 0):
            _mfal_retrain()
    except Exception as e:
        log.debug(f"[MFAL] record_trade failed: {e}")


def _mfal_retrain():
    """يعيد تدريب الأوزان من history عبر logistic regression."""
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

        # Basic sanity: must have both classes
        if ya.sum() < 20 or (1.0 - ya).sum() < 20:
            return

        # Simple logistic regression via scipy
        from scipy.optimize import minimize as _scipy_min

        def _loss(params):
            w = params[:-1]
            b = params[-1]
            z = Xa @ w + b
            # stable sigmoid
            p = np.where(z >= 0,
                          1.0 / (1.0 + np.exp(-z)),
                          np.exp(z) / (1.0 + np.exp(z)))
            eps = 1e-9
            p = np.clip(p, eps, 1.0 - eps)
            nll = -np.mean(ya * np.log(p) + (1 - ya) * np.log(1 - p))
            # L2 regularization
            reg = 0.1 * float(np.sum(w * w))
            return float(nll + reg)

        x0 = np.concatenate([_MFAL_WEIGHTS, [_MFAL_BIAS]])
        res = _scipy_min(_loss, x0, method="L-BFGS-B",
                          options={"maxiter": 100})

        w_new = res.x[:-1]
        b_new = float(res.x[-1])

        # Blend: 80% old, 20% new  (conservative)
        _MFAL_WEIGHTS = 0.8 * _MFAL_WEIGHTS + 0.2 * w_new
        _MFAL_BIAS = 0.8 * _MFAL_BIAS + 0.2 * b_new

        _MFAL_STATS["retrains"] += 1
        _mfal_save_weights()
        log.info(
            f"[MFAL] Retrained #{_MFAL_STATS['retrains']} "
            f"(n={len(X)}, loss={_loss(res.x):.4f}) "
            f"w_norm={np.linalg.norm(_MFAL_WEIGHTS):.4f}"
        )
    except Exception as e:
        log.warning(f"[MFAL] retrain failed: {e}")


def _mfal_log_stats():
    """طبع إحصائيات MFAL كل 5 دقائق."""
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
        f"μ={_MFAL_STATS['q_sum']/n:.2f}, "
        f"R=[{_MFAL_STATS['r_min']:.2f},{_MFAL_STATS['r_max']:.2f}] "
        f"μ={_MFAL_STATS['r_sum']/n:.2f}, "
        f"L_core_avg={_MFAL_STATS['l_core_sum']/n:.2f}, "
        f"L_final_avg={_MFAL_STATS['l_final_sum']/n:.2f}, "
        f"trades={_MFAL_STATS['trades_recorded']}, "
        f"retrains={_MFAL_STATS['retrains']}"
    )


# ══ end MFAL block ══


'''


# ══════════════════════════════════════════════════════════════════════
# Edit 1: إدراج الكتلة
# ══════════════════════════════════════════════════════════════════════

def edit1_insert_block(src):
    print("\n▶ Edit 1: insert MFAL block")
    anchor = "def load_symbol_meta(mode: str) -> Dict[str, Dict]:"
    if anchor not in src:
        print("   ❌ anchor 'load_symbol_meta' not found")
        return src, False
    if "[MFAL] Multi-Factor Adaptive Leverage" in src:
        print("   ℹ️  already applied")
        return src, True
    src = src.replace(anchor, MFAL_BLOCK + anchor, 1)
    print("   ✅ MFAL block inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 2: توسيع Signal dataclass
# ══════════════════════════════════════════════════════════════════════

def edit2_extend_signal_dataclass(src):
    print("\n▶ Edit 2: extend Signal dataclass with mfal fields")
    old = (
        "    # ══ [SMART ENTRY] ══\n"
        "    entry_ref_price: float = 0.0   # close price at signal time (dip ref)\n"
        "    entry_base_dip: float = 0.0    # |ref_price − price| in price units"
    )
    new = (
        "    # ══ [SMART ENTRY] ══\n"
        "    entry_ref_price: float = 0.0   # close price at signal time (dip ref)\n"
        "    entry_base_dip: float = 0.0    # |ref_price − price| in price units\n"
        "    # ══ [MFAL] Signal-time feature vector for Quality factor ══\n"
        "    mfal_x: Optional[np.ndarray] = None\n"
        "    mfal_p_act: float = 0.0"
    )
    return _replace_once(src, old, new, "extend-signal",
                          marker="mfal_x: Optional[np.ndarray]")


# ══════════════════════════════════════════════════════════════════════
# Edit 3: build_signals — استخراج features الإشارة
# ══════════════════════════════════════════════════════════════════════

def edit3_extract_signal_features(src):
    print("\n▶ Edit 3: extract MFAL features in build_signals")
    old = (
        "            # ══ [TRADE FILTER] ══\n"
        "            _new_sig = Signal(\n"
        "                timestamp=ad.timestamps[ci], symbol=sym,\n"
        "                price=tunnel_entry_p,\n"
        "                score=float(ad.score[fi]), action=action,\n"
        "                sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,\n"
        "                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,\n"
        "                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),\n"
        "                dynamic_risk=dynamic_risk, T_info_val=T_info,\n"
        "                dyn_sl_factor=sl_dist / tunnel_entry_p,\n"
        "                entry_ref_price=float(p),\n"
        "                entry_base_dip=float(_entry_dip),\n"
        "            )"
    )
    new = (
        "            # ══ [MFAL] Extract signal features ══\n"
        "            try:\n"
        "                _accel_ratio_mfal = abs(geo_accel) / max(fric_val, 1e-9)\n"
        "                _sl_dist_mfal = abs(tunnel_entry_p - sl)\n"
        "                _rr_mfal = abs(tp1 - tunnel_entry_p) / max(_sl_dist_mfal, 1e-9)\n"
        "                _mfal_x = _mfal_signal_features(\n"
        "                    score=float(ad.score[fi]),\n"
        "                    p_act=float(P_activation),\n"
        "                    accel_ratio=float(_accel_ratio_mfal),\n"
        "                    gauge=float(ad.gauge_force[fi]),\n"
        "                    z_dev=float(_z_dev),\n"
        "                    rr=float(_rr_mfal),\n"
        "                )\n"
        "            except Exception:\n"
        "                _mfal_x = None\n"
        "\n"
        "            # ══ [TRADE FILTER] ══\n"
        "            _new_sig = Signal(\n"
        "                timestamp=ad.timestamps[ci], symbol=sym,\n"
        "                price=tunnel_entry_p,\n"
        "                score=float(ad.score[fi]), action=action,\n"
        "                sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,\n"
        "                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,\n"
        "                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),\n"
        "                dynamic_risk=dynamic_risk, T_info_val=T_info,\n"
        "                dyn_sl_factor=sl_dist / tunnel_entry_p,\n"
        "                entry_ref_price=float(p),\n"
        "                entry_base_dip=float(_entry_dip),\n"
        "                mfal_x=_mfal_x,\n"
        "                mfal_p_act=float(P_activation),\n"
        "            )"
    )
    return _replace_once(src, old, new, "signal-features",
                          marker="mfal_x=_mfal_x")


# ══════════════════════════════════════════════════════════════════════
# Edit 4: استبدال استدعاء الرافعة في run_live
# ══════════════════════════════════════════════════════════════════════

def edit4_replace_live_call(src):
    print("\n▶ Edit 4: replace leverage call in run_live")
    old = "                    dynamic_leverage = compute_dynamic_leverage(cap_live, cfg, symbol=sym)"
    new = (
        "                    # ══ [MFAL] Adaptive leverage ══\n"
        "                    dynamic_leverage = compute_adaptive_leverage(\n"
        "                        symbol=sym,\n"
        "                        sig=sig,\n"
        "                        open_pos_live=open_pos_live,\n"
        "                        capital=cap_live,\n"
        "                        peak_capital=peak_cap_live,\n"
        "                        corr_cache=corr_cache,\n"
        "                        exchange=exchange,\n"
        "                        cfg=cfg,\n"
        "                    )"
    )
    return _replace_once(src, old, new, "live-call")


# ══════════════════════════════════════════════════════════════════════
# Edit 5: استبدال استدعاء الرافعة في backtest
# ══════════════════════════════════════════════════════════════════════

def edit5_replace_backtest_call(src):
    print("\n▶ Edit 5: replace leverage call in simulate_portfolio")
    old = "        dynamic_leverage = compute_dynamic_leverage(capital, CFG, symbol=sym)"
    new = (
        "        # ══ [MFAL] Adaptive leverage (backtest mode) ══\n"
        "        dynamic_leverage = compute_adaptive_leverage(\n"
        "            symbol=sym,\n"
        "            sig=sig,\n"
        "            open_pos_live=open_pos,\n"
        "            capital=capital,\n"
        "            peak_capital=peak_cap,\n"
        "            corr_cache=corr_matrix,\n"
        "            exchange=None,\n"
        "            cfg=CFG,\n"
        "        )"
    )
    return _replace_once(src, old, new, "backtest-call")


# ══════════════════════════════════════════════════════════════════════
# Edit 6: تسجيل نتيجة الصفقة بعد الإغلاق في live
# ══════════════════════════════════════════════════════════════════════

def edit6_record_live_outcome(src):
    print("\n▶ Edit 6: record live trade outcome")
    # نُضيف قبل حذف المركز في مسار live
    old = (
        "                    del open_pos_live[sym]\n"
        "                    last_exit_time[sym] = time.time()\n"
        "                    log.info(f\"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]\")"
    )
    new = (
        "                    # ══ [MFAL] Record trade outcome ══\n"
        "                    try:\n"
        "                        _entry_px_m = float(pos.get('entry') or 0)\n"
        "                        _sl_d0_m = float(pos.get('sl_dist_initial') or 0)\n"
        "                        if _entry_px_m > 0 and _sl_d0_m > 0:\n"
        "                            _exit_px_m = float(exec_price or 0)\n"
        "                            if pos.get('action') == 'BUY':\n"
        "                                _pnl_frac_m = (_exit_px_m - _entry_px_m) / _entry_px_m\n"
        "                            else:\n"
        "                                _pnl_frac_m = (_entry_px_m - _exit_px_m) / _entry_px_m\n"
        "                            _sl_frac_m = _sl_d0_m / _entry_px_m\n"
        "                            _R_m = _pnl_frac_m / _sl_frac_m if _sl_frac_m > 0 else 0.0\n"
        "                            _sig_m = None\n"
        "                            try:\n"
        "                                _sig_m = getattr(pos, 'signal', None)\n"
        "                            except Exception:\n"
        "                                pass\n"
        "                            if _sig_m is None:\n"
        "                                _sig_m = pos.get('_sig_ref') if isinstance(pos, dict) else None\n"
        "                            if _sig_m is None:\n"
        "                                _sig_m = pos if isinstance(pos, dict) else None\n"
        "                            _mfal_record_trade(_sig_m, float(_R_m), _R_m > 0.5)\n"
        "                    except Exception as _me:\n"
        "                        log.debug(f\"[MFAL] record failed: {_me}\")\n"
        "\n"
        "                    del open_pos_live[sym]\n"
        "                    last_exit_time[sym] = time.time()\n"
        "                    log.info(f\"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]\")"
    )
    return _replace_once(src, old, new, "record-outcome")


# ══════════════════════════════════════════════════════════════════════
# Edit 7: stats logger في الحلقة
# ══════════════════════════════════════════════════════════════════════

def edit7_wire_stats(src):
    print("\n▶ Edit 7: wire MFAL stats logger")
    anchor = (
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()"
    )
    if anchor not in src:
        print("   ❌ pos-cache anchor not found")
        return src, False
    if "_mfal_log_stats()" in src:
        print("   ℹ️  already applied")
        return src, True
    new = (
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()\n"
        "            # [MFAL] stats every 5 min\n"
        "            _mfal_log_stats()"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ stats logger wired")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 8: CLI args في main()
# ══════════════════════════════════════════════════════════════════════

def edit8_add_cli_args(src):
    print("\n▶ Edit 8: add MFAL CLI args")
    if 'p.add_argument("--mfal"' in src:
        print("   ℹ️  already applied")
        return src, True

    # ابحث عن آخر parser.add_argument قبل args = p.parse_args()
    anchor = "    args = p.parse_args()"
    if anchor not in src:
        print("   ❌ parse_args anchor not found")
        return src, False

    injection = (
        '    # ══ [MFAL] CLI args ══\n'
        '    p.add_argument("--mfal", action="store_true",\n'
        '                   help="Enable Multi-Factor Adaptive Leverage")\n'
        '    p.add_argument("--mfal-no-micro", action="store_true",\n'
        '                   help="Disable micro-structure factor M")\n'
        '    p.add_argument("--mfal-no-time", action="store_true",\n'
        '                   help="Disable time-of-day factor T")\n'
        '    p.add_argument("--mfal-no-learn", action="store_true",\n'
        '                   help="Disable online learning")\n'
        '    p.add_argument("--mfal-weights", type=str, default=None,\n'
        '                   help="Path to MFAL weights JSON")\n'
        '\n'
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ CLI args added")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 9: تفعيل MFAL في main() من CLI
# ══════════════════════════════════════════════════════════════════════

def edit9_wire_cli(src):
    print("\n▶ Edit 9: wire CLI flags to MFAL globals")
    if "# [MFAL] CLI wiring" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = "    args = p.parse_args()"
    if anchor not in src:
        print("   ❌ parse_args anchor not found")
        return src, False

    injection = anchor + (
        "\n"
        "    # [MFAL] CLI wiring\n"
        "    try:\n"
        "        if args.mfal:\n"
        "            globals()['_MFAL_ENABLED'] = True\n"
        "            if args.mfal_no_micro:\n"
        "                globals()['_MFAL_USE_MICRO'] = False\n"
        "            if args.mfal_no_time:\n"
        "                globals()['_MFAL_USE_TIME'] = False\n"
        "            if args.mfal_no_learn:\n"
        "                globals()['_MFAL_USE_LEARNING'] = False\n"
        "            if args.mfal_weights:\n"
        "                globals()['_MFAL_WEIGHTS_PATH'] = str(args.mfal_weights)\n"
        "            _mfal_load_weights()\n"
        "            log.info(\n"
        "                \"[MFAL] ENABLED  \"\n"
        "                f\"micro={_MFAL_USE_MICRO} \"\n"
        "                f\"time={_MFAL_USE_TIME} \"\n"
        "                f\"learn={_MFAL_USE_LEARNING}\"\n"
        "            )\n"
        "        else:\n"
        "            log.info(\"[MFAL] Disabled (use --mfal to enable)\")\n"
        "    except Exception as _e:\n"
        "        log.warning(f\"[MFAL] CLI wiring failed: {_e}\")"
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
        ("MFAL block",               "[MFAL] Multi-Factor Adaptive Leverage"),
        ("_MFAL_ENABLED",            "_MFAL_ENABLED: bool = False"),
        ("_MFAL_WEIGHTS",            "_MFAL_WEIGHTS: np.ndarray"),
        ("load weights",             "def _mfal_load_weights("),
        ("save weights",             "def _mfal_save_weights("),
        ("signal features",          "def _mfal_signal_features("),
        ("quality Q",                "def _mfal_quality("),
        ("time T",                   "def _mfal_time_factor("),
        ("micro M",                  "def _mfal_micro_factor("),
        ("portfolio R",              "def _mfal_portfolio_factor("),
        ("compute_adaptive_leverage","def compute_adaptive_leverage("),
        ("record trade",             "def _mfal_record_trade("),
        ("retrain",                  "def _mfal_retrain("),
        ("log stats",                "def _mfal_log_stats("),
        ("Signal.mfal_x",            "mfal_x: Optional[np.ndarray] = None"),
        ("build_signals extract",    "mfal_x=_mfal_x"),
        ("live call",                "compute_adaptive_leverage("),
        ("record outcome",           "[MFAL] Record trade outcome"),
        ("stats wired",              "_mfal_log_stats()"),
        ("CLI arg --mfal",           'p.add_argument("--mfal"'),
        ("CLI wiring",               "# [MFAL] CLI wiring"),
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
    ap.add_argument("--input", default="trading_2_complete4.py")
    ap.add_argument("--output", default="trading_2_mfal.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} chars)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  MFAL — Multi-Factor Adaptive Leverage                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: insert block",     edit1_insert_block),
        ("Edit 2: Signal dataclass", edit2_extend_signal_dataclass),
        ("Edit 3: extract features", edit3_extract_signal_features),
        ("Edit 4: live call",        edit4_replace_live_call),
        ("Edit 5: backtest call",    edit5_replace_backtest_call),
        ("Edit 6: record outcome",   edit6_record_live_outcome),
        ("Edit 7: stats logger",     edit7_wire_stats),
        ("Edit 8: CLI args",         edit8_add_cli_args),
        ("Edit 9: CLI wiring",       edit9_wire_cli),
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
        "#  MFAL Build — Multi-Factor Adaptive Leverage\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  MFAL adds:\n"
        "#    • Q — Quality Factor (learned signal quality)\n"
        "#    • R — Risk Factor (portfolio capacity)\n"
        "#    • T — Time Factor (hour-of-day liquidity)\n"
        "#    • M — Micro Factor (spread / depth)\n"
        "#    • Online learning (logistic regression on outcomes)\n"
        "#    • Persistent weights (mfal_weights.json)\n"
        "#    • Trade history (mfal_history.jsonl)\n"
        "#\n"
        "#  Default: DISABLED. Enable with --mfal flag.\n"
        "# ═══════════════════════════════════════════════════════════\n"
    )

    if src.startswith("#!"):
        first_nl = src.index("\n")
        src_out = header + src[first_nl + 1:]
    else:
        src_out = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src_out)

    # Re-verify written
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
    print("  ▶ Run with MFAL enabled:")
    print(f"     python {args.output} --mode testnet --mfal --api-key ... "
          f"--api-secret ...")
    print()
    print("  ▶ Run with MFAL disabled (default):")
    print(f"     python {args.output} --mode testnet --api-key ... "
          f"--api-secret ...")

    if not write_ok:
        sys.exit(3)


if __name__ == "__main__":
    main()
