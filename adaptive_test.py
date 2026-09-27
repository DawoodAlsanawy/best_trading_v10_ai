#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Adaptive Framework Feasibility Test (v2 — fixed + fully commented)
=================================================================

Goal
----
Empirically answer whether an "adaptive normalization layer" can make
the thermodynamic strategy work across DIFFERENT assets AND timeframes,
using REAL Binance USDT-M futures data (no synthetic data).

This script does NOT modify trading.py. It imports it and calls
`process_asset` to reuse the exact same feature engine, KMeans pipeline,
entropy/gauge/geometry/lyapunov computation, and score formula. What we
measure is the *distributional behavior* of those outputs across assets
and TFs — because only that tells us if z-scoring / quantile thresholds
can replace the current fixed constants.

Questions answered
------------------
Q1  Does MIN_SCORE=5.5 (fixed) select wildly different signal rates
    across assets and TFs?                → tests need for normalization
Q2  If we z-score each feature per-asset, does a fixed z-threshold
    select ~5% across all (asset, TF) pairs? (Normal dist → 5% at z≥1.645)
Q3  Are feature distributions symmetric enough (skew/kurt) for z-scores
    to be meaningful, or do we need quantile thresholds?
Q4  Can we reliably classify REGIMES (ranging/trending/explosive) and
    do they occupy non-trivial fractions of real data?
Q5  Does the SCORE distribution shift across regimes within the same
    asset? → tests need for regime-conditional thresholds
Q6  Does the fixed bps penetration (PO_PENETRATION_BPS) translate into
    at least 1 tick across assets with very different prices?
Q7  Does the SAME asset behave consistently across TFs (15m/1h/4h)?

The output is a set of tables (§1..§9) and an automated verdict (§10),
plus a JSON file for the caller to analyze in depth.

No assumption is baked into the output — every table reports real
measurements, and §10 flags what they mean for the adaptive design.
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta, timezone
from collections import OrderedDict

import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis

# ═══════════════════════════════════════════════════════════════════
# 1) Import trading.py from the same directory
# ═══════════════════════════════════════════════════════════════════
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import trading as T
except Exception as e:
    print(f"FATAL: cannot import trading.py: {e}")
    sys.exit(1)

# Disable any side-effects that could touch production caches.
# process_asset itself doesn't use caches — this is defensive.
T.CFG.ASSET_CACHE_ENABLED = False
T.CFG.ML_FILTER_ENABLED = False
T.CFG.RULE_FILTER_ENABLED = False
T.CFG.SR_FILTER_ENABLED = False

# Compile numba kernels once so per-asset timing and features are
# deterministic (identical to what the live bot sees).
T._warmup_numba_kernels()


# ═══════════════════════════════════════════════════════════════════
# 2) Test configuration
# ═══════════════════════════════════════════════════════════════════
ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "WIF/USDT", "DOGE/USDT"]
TIMEFRAMES = ["15m", "1h", "4h"]
HISTORY_DAYS = 180
CACHE_DIR = "data/adaptive_test_cache"
OUTPUT_JSON = "data/adaptive_test_results.json"

# Warmup in feature-space index. Features (score, dH, dF, accel, H, Γ,
# gauge) have length (n_bars - N) with N = CFG.N = 24.
# Feature i corresponds to closes index (N + i).
# We skip the first WARMP closes bars to let every internal window
# (Lyapunov window=60, entropy W=20, gauge W=20, ATR=14) fully stabilize.
# WARMP = 150 closes bars is safely larger than 2*min_dist+steps+window
# for Lyapunov (2*10 + 5 + 60 = 85) and larger than any rolling window.
WARMP_CLOSES_BARS = 150

os.makedirs(CACHE_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════
# 3) Real data fetching with on-disk parquet caching
# ═══════════════════════════════════════════════════════════════════
def fetch_ohlcv(exchange, symbol, tf, days):
    """
    Fetch real OHLCV from Binance USDT-M futures via ccxt.
    Cache on disk as parquet; refresh if cached file is older than 24h.

    Returns:
        DataFrame indexed by UTC timestamps, columns
        [Open, High, Low, Close, Volume] (all float), or None if
        not enough data was retrieved.
    """
    fname = f"{symbol.replace('/', '_')}_{tf}_{days}d.parquet"
    path = os.path.join(CACHE_DIR, fname)

    # Try cache first
    if os.path.exists(path):
        try:
            df = pd.read_parquet(path)
            if df.index.tz is None:
                df.index = pd.to_datetime(df.index, utc=True)
            if len(df) > 200:
                age_s = (datetime.now(timezone.utc)
                         - df.index[-1]).total_seconds()
                if age_s < 24 * 3600:
                    return df
        except Exception:
            # Corrupt cache — fall through to refetch
            pass

    print(f"    fetch {symbol} {tf} {days}d ...", flush=True)
    since = exchange.parse8601(
        (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() + "Z"
    )
    rows = []
    # Paginate — Binance returns max 1000 candles per call.
    while True:
        try:
            chunk = exchange.fetch_ohlcv(symbol, tf, since=since, limit=1000)
        except Exception as e:
            print(f"      error: {e}")
            break
        if not chunk:
            break
        rows.extend(chunk)
        since = chunk[-1][0] + 1
        if len(chunk) < 1000:
            break
        time.sleep(0.15)  # respect rate limits

    if len(rows) < 200:
        return None

    df = pd.DataFrame(rows, columns=['ts', 'Open', 'High', 'Low',
                                     'Close', 'Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').drop_duplicates().astype(float)

    try:
        df.to_parquet(path)
    except Exception:
        pass
    return df


# ═══════════════════════════════════════════════════════════════════
# 4) TF-aware CFG setup
# ═══════════════════════════════════════════════════════════════════
def set_cfg_for_tf(exchange, tf):
    """
    Update global CFG to reflect the current timeframe.

    Note: process_asset's INTERNAL windows (N=24, W=20, L=10, lyapunov
    window=60, ATR=14, adv=24) are FIXED bar counts — they are NOT scaled
    by TF here. This is intentional: the test measures how the strategy
    behaves with its CURRENT fixed-window design across TFs. If the
    distributions diverge across TFs, that's a finding (Q7).
    """
    try:
        tf_sec = int(exchange.parse_timeframe(tf))
    except Exception:
        s = tf.lower()
        if s.endswith('m'):
            tf_sec = int(s[:-1]) * 60
        elif s.endswith('h'):
            tf_sec = int(s[:-1]) * 3600
        elif s.endswith('d'):
            tf_sec = int(s[:-1]) * 86400
        else:
            tf_sec = 3600
    T.CFG.TF_SCALE   = 3600.0 / tf_sec
    T.CFG.TF_SECONDS = tf_sec
    T.CFG.TF_HOURS   = tf_sec / 3600.0


# ═══════════════════════════════════════════════════════════════════
# 5) Safe statistical helpers
# ═══════════════════════════════════════════════════════════════════
def _safe_skew(x):
    """Sample skewness (bias=False) with NaN protection."""
    try:
        v = float(skew(x, bias=False))
        return v if np.isfinite(v) else 0.0
    except Exception:
        return 0.0


def _safe_kurt(x):
    """Sample excess kurtosis (bias=False, fisher=True) with protection."""
    try:
        v = float(kurtosis(x, bias=False))
        return v if np.isfinite(v) else 0.0
    except Exception:
        return 0.0


def _sanitize_for_json(obj):
    """
    Recursively convert numpy types → Python natives and NaN/Inf → None,
    so the resulting structure is strictly valid JSON.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(x) for x in obj]
    if isinstance(obj, np.ndarray):
        return _sanitize_for_json(obj.tolist())
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return f if np.isfinite(f) else None
    if isinstance(obj, float):
        return obj if np.isfinite(obj) else None
    return obj


# ═══════════════════════════════════════════════════════════════════
# 6) Tick size lookup from exchange metadata
# ═══════════════════════════════════════════════════════════════════
def get_tick_size(exchange, symbol):
    """
    Return the price tick size for `symbol`, or None if unavailable.

    Primary source: the exchange's own PRICE_FILTER (Binance futures
    always exposes this in market['info']['filters']).
    Fallback: ccxt-normalized precision['price'] if it looks like a
    tick size (positive float). We never treat it as a decimal count
    because Binance futures never reports it that way.
    """
    try:
        mkt = exchange.market(symbol)
    except Exception:
        mkt = None
    if not mkt:
        return None

    # Primary — raw filter
    info = mkt.get('info') or {}
    filters = info.get('filters') or []
    for f in filters:
        if isinstance(f, dict) and f.get('filterType') == 'PRICE_FILTER':
            try:
                ts = float(f.get('tickSize', 0))
                if ts > 0 and np.isfinite(ts):
                    return ts
            except Exception:
                pass

    # Fallback — ccxt precision
    prec = mkt.get('precision') or {}
    tp = prec.get('price')
    if tp is not None:
        try:
            v = float(tp)
            if v > 0 and np.isfinite(v):
                return v
        except Exception:
            pass
    return None


# ═══════════════════════════════════════════════════════════════════
# 7) Profile one (symbol, TF): the core measurement
# ═══════════════════════════════════════════════════════════════════
def profile_asset(symbol, tf, df, exchange):
    """
    Run process_asset on real OHLCV and compute a full statistical
    profile of its outputs, without any modification to the engine.
    """
    # Set global CFG to reflect current TF (see set_cfg_for_tf docstring).
    set_cfg_for_tf(exchange, tf)

    try:
        ad = T.process_asset(symbol, df, current_capital=55.0)
    except Exception as e:
        return {"error": f"process_asset failed: {type(e).__name__}: {e}"}
    if ad is None:
        return {"error": "process_asset returned None"}

    # ── Extract arrays as float64 for numerical safety ──
    closes = np.asarray(ad.closes,          dtype=np.float64)
    score  = np.asarray(ad.score,           dtype=np.float64)
    dH     = np.asarray(ad.dH,              dtype=np.float64)
    dF     = np.asarray(ad.dF,              dtype=np.float64)
    accel  = np.asarray(ad.geodesic_accel,  dtype=np.float64)
    H      = np.asarray(ad.H,               dtype=np.float64)
    fr     = np.asarray(ad.friction,        dtype=np.float64)
    gauge  = np.asarray(ad.gauge_force,     dtype=np.float64)

    # Lengths:
    #   closes   → n_bars
    #   features → n_bars - feat_start (feat_start = N = 24)
    n_bars     = len(closes)
    feat_start = int(ad.feat_start)
    n_feat     = len(score)
    # Feature i corresponds to closes index (feat_start + i).
    # We require closes index >= WARMP_CLOSES_BARS, i.e.:
    #   feat_start + i >= WARMP  →  i >= WARMP - feat_start
    i_start = max(0, WARMP_CLOSES_BARS - feat_start)
    if i_start >= n_feat:
        return {"error": f"not enough features after warmup "
                         f"(n_feat={n_feat}, i_start={i_start})"}

    # ── Slice all feature arrays with the same warmup offset ──
    score_w = score[i_start:]
    dH_w    = dH[i_start:]
    dF_w    = dF[i_start:]
    accel_w = accel[i_start:]
    H_w     = H[i_start:]
    fr_w    = fr[i_start:]
    g_w     = gauge[i_start:]

    # Theoretical max entropy for the current dynamic K.
    H_max_theo = float(np.log2(max(int(ad.dynamic_k), 2)))

    # ══════════════════════════════════════════════════════════════
    # 7.1  Basic counts + score distribution
    # ══════════════════════════════════════════════════════════════
    st = {
        "symbol": symbol, "tf": tf,
        "n_bars": int(n_bars),
        "n_features": int(n_feat),
        "n_features_used": int(len(score_w)),
        "dynamic_k": int(ad.dynamic_k),

        "score_mean": float(np.mean(score_w)),
        "score_std":  float(np.std(score_w)),
        "score_q50":  float(np.percentile(score_w, 50)),
        "score_q75":  float(np.percentile(score_w, 75)),
        "score_q90":  float(np.percentile(score_w, 90)),
        "score_q95":  float(np.percentile(score_w, 95)),
        "score_q99":  float(np.percentile(score_w, 99)),
        "score_max":  float(np.max(score_w)),
        "score_skew": _safe_skew(score_w),
        "score_kurt": _safe_kurt(score_w),
    }

    # ══════════════════════════════════════════════════════════════
    # 7.2  Signal rate at several FIXED absolute thresholds (Q1)
    # ══════════════════════════════════════════════════════════════
    for th in (3.0, 4.0, 5.0, 5.5, 6.0, 7.0, 8.0, 10.0):
        key = f"rate_abs_{th}"
        st[key] = float((score_w >= th).mean())

    # ══════════════════════════════════════════════════════════════
    # 7.3  Distribution of dH, dF, accel (Q3, plus z-test inputs)
    # ══════════════════════════════════════════════════════════════
    st.update({
        "dH_mean": float(np.mean(dH_w)),
        "dH_std":  float(np.std(dH_w)),
        "dH_skew": _safe_skew(dH_w),
        "dH_kurt": _safe_kurt(dH_w),

        "dF_mean": float(np.mean(dF_w)),
        "dF_std":  float(np.std(dF_w)),
        "dF_skew": _safe_skew(dF_w),
        "dF_kurt": _safe_kurt(dF_w),

        "accel_mean": float(np.mean(accel_w)),
        "accel_std":  float(np.std(accel_w)),
        "accel_skew": _safe_skew(accel_w),
        "accel_kurt": _safe_kurt(accel_w),
    })

    # ══════════════════════════════════════════════════════════════
    # 7.4  Entropy / friction / gauge scalars
    # ══════════════════════════════════════════════════════════════
    st.update({
        "H_mean":  float(np.mean(H_w)),
        "H_std":   float(np.std(H_w)),
        "H_max_achieved":    float(np.max(H_w)),
        "H_max_theoretical": H_max_theo,
        "H_ratio_mean":      float(np.mean(H_w) / (H_max_theo + 1e-12)),

        "friction_mean": float(np.mean(fr_w)),
        "friction_std":  float(np.std(fr_w)),
        "gauge_mean":    float(np.mean(g_w)),
        "gauge_std":     float(np.std(g_w)),
    })

    # ══════════════════════════════════════════════════════════════
    # 7.5  Z-score threshold test (Q2)
    # ══════════════════════════════════════════════════════════════
    # For each feature, z-score with THIS asset's own μ and σ, then
    # measure the fraction crossing a fixed z-threshold. For a perfectly
    # Gaussian variable, z≥1.645 should fire ~5% of bars; z≤-1.645 ~5%.
    # If measured rates deviate strongly, z-normalization is still
    # *valid* (it always mean-shifts and unit-scales), but the target
    # fraction per asset must be set via QUANTILES instead of z-values.
    for name, series in [("score", score_w), ("dH", dH_w),
                         ("accel", accel_w), ("dF", dF_w)]:
        mu = float(np.mean(series))
        sd = float(np.std(series)) + 1e-12
        z  = (series - mu) / sd
        st[f"z{name}_rate_above_1.645"]  = float((z >=  1.645).mean())
        st[f"z{name}_rate_below_neg1.645"] = float((z <= -1.645).mean())
        st[f"z{name}_rate_beyond_1.96"]  = float((np.abs(z) >= 1.96).mean())

    # ══════════════════════════════════════════════════════════════
    # 7.6  Regime classification (Q4)
    # ══════════════════════════════════════════════════════════════
    # Two dimensionless descriptors computed directly on closes:
    #   r = σ_fast / σ_slow   (recent vs older per-bar volatility)
    #   d = (P - EMA200) / (σ_slow * P)   (standardized displacement)
    #   |d| is in units of "σ_slow bars", which is TF-invariant.
    # Window lengths are TF-scaled so both refer to the same real-time
    # horizon on every TF:
    #   fast ≈ 20 hours, slow ≈ 100 hours (baseline from 1h design).
    scale  = max(T.CFG.TF_SCALE, 1e-6)
    fast_w = int(round(20  * scale))
    slow_w = int(round(100 * scale))
    fast_w = max(5,   min(fast_w, 500))
    slow_w = max(20,  min(slow_w, 2000))
    if slow_w <= fast_w:
        slow_w = fast_w * 3

    # log-returns (length n_bars - 1)
    logret = np.diff(np.log(np.maximum(closes, 1e-12)))

    # Rolling std on log-returns, then pad the FRONT with NaN so that
    # index i in the padded array refers to "volatility up to bar i",
    # matching the closes array indexing exactly (no forward-looking).
    s_fast_arr = pd.Series(logret).rolling(fast_w, min_periods=fast_w).std().values
    s_slow_arr = pd.Series(logret).rolling(slow_w, min_periods=slow_w).std().values
    s_fast = np.concatenate([[np.nan], s_fast_arr])   # length n_bars
    s_slow = np.concatenate([[np.nan], s_slow_arr])   # length n_bars

    # Ratio r — safe division (NaN where s_slow is not finite / ~0)
    ratio = np.full(n_bars, np.nan, dtype=np.float64)
    valid_r = np.isfinite(s_fast) & np.isfinite(s_slow) & (s_slow > 1e-12)
    ratio[valid_r] = s_fast[valid_r] / s_slow[valid_r]

    # Standardized displacement d — safe division
    ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values
    dist_ema = closes - ema200
    denom = s_slow * closes
    dist_ema_z = np.full(n_bars, np.nan, dtype=np.float64)
    valid_d = np.isfinite(denom) & (np.abs(denom) > 1e-12)
    dist_ema_z[valid_d] = dist_ema[valid_d] / denom[valid_d]

    # Regime rule (heuristic, documented):
    #   2 explosive : r > 1.6                        (volatility burst)
    #   1 trending  : 0.7 ≤ r ≤ 1.6 and |d| > 1.5    (extended in one dir.)
    #   0 ranging   : otherwise
    # This is intentionally crude — the test only checks WHETHER such
    # regimes occupy non-trivial fractions of real data, not how
    # optimal the boundaries are.
    regime = np.zeros(n_bars, dtype=np.int8)
    valid_all = np.isfinite(ratio) & np.isfinite(dist_ema_z)
    exp_mask = valid_all & (ratio > 1.6)
    trd_mask = (valid_all
                & (np.abs(dist_ema_z) > 1.5)
                & (ratio >= 0.7)
                & (ratio <= 1.6))
    regime[exp_mask] = 2
    regime[trd_mask] = 1

    # Only count bars at/after warmup as "valid regime measurements"
    warm_bar = max(slow_w, WARMP_CLOSES_BARS)
    valid_range = np.zeros(n_bars, dtype=bool)
    valid_range[warm_bar:] = True
    counted = valid_all & valid_range
    if counted.sum() > 0:
        st["pct_ranging"]   = float((regime[counted] == 0).mean())
        st["pct_trending"]  = float((regime[counted] == 1).mean())
        st["pct_explosive"] = float((regime[counted] == 2).mean())
    else:
        st["pct_ranging"]   = 0.0
        st["pct_trending"]  = 0.0
        st["pct_explosive"] = 0.0

    # ══════════════════════════════════════════════════════════════
    # 7.7  Score by regime (Q5)
    # ══════════════════════════════════════════════════════════════
    # score[i] corresponds to closes index (feat_start + i).
    # We build score_aligned (length n_bars) where score_aligned[k]
    # holds score for closes index k, if available.
    score_aligned = np.full(n_bars, np.nan, dtype=np.float64)
    src_start = feat_start
    src_end = min(n_bars, feat_start + n_feat)
    if src_end > src_start:
        score_aligned[src_start:src_end] = score[:src_end - src_start]

    for r_idx, r_name in [(0, "ranging"), (1, "trending"), (2, "explosive")]:
        mask = counted & (regime == r_idx) & np.isfinite(score_aligned)
        if mask.sum() > 10:
            vals = score_aligned[mask]
            st[f"score_mean_in_{r_name}"] = float(np.mean(vals))
            st[f"score_std_in_{r_name}"]  = float(np.std(vals))
            st[f"rate_5.5_in_{r_name}"]   = float((vals >= 5.5).mean())

    # ══════════════════════════════════════════════════════════════
    # 7.8  Price / tick-size feasibility (Q6)
    # ══════════════════════════════════════════════════════════════
    price_now = float(closes[-1])
    st["price_now"] = price_now
    tick = get_tick_size(exchange, symbol)
    st["tick_size"] = float(tick) if tick is not None else None
    if tick is not None and tick > 0 and np.isfinite(tick):
        # A penetration of 1 bps in price = price * 1e-4 in absolute
        # price units. Divided by the tick size → how many ticks.
        st["ticks_per_bps"] = float((price_now * 1e-4) / tick)
    else:
        st["ticks_per_bps"] = None

    return st


# ═══════════════════════════════════════════════════════════════════
# 8) Main
# ═══════════════════════════════════════════════════════════════════
def main():
    try:
        import ccxt
    except ImportError:
        print("pip install ccxt")
        return

    print("=" * 78)
    print("  ADAPTIVE FRAMEWORK FEASIBILITY TEST  (real data, no assumptions)")
    print(f"  Assets : {ASSETS}")
    print(f"  TFs    : {TIMEFRAMES}")
    print(f"  Days   : {HISTORY_DAYS}")
    print(f"  Cache  : {CACHE_DIR}")
    print("=" * 78)
    sys.stdout.flush()

    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })
    try:
        exchange.load_markets()
    except Exception as e:
        print(f"WARN: load_markets failed: {e}")

    results = OrderedDict()

    # ── Collect profiles for every (asset, TF) pair ──
    for tf in TIMEFRAMES:
        print(f"\n─── TF = {tf} ───")
        sys.stdout.flush()
        for sym in ASSETS:
            print(f"  [{sym}]", flush=True)
            df = fetch_ohlcv(exchange, sym, tf, HISTORY_DAYS)
            if df is None or len(df) < 300:
                got = len(df) if df is not None else 0
                print(f"    SKIP: insufficient data ({got} bars)")
                continue
            print(f"    bars = {len(df)}")
            sys.stdout.flush()
            t0 = time.time()
            st = profile_asset(sym, tf, df, exchange)
            el = time.time() - t0
            if "error" in st:
                print(f"    ERROR: {st['error']}")
                continue
            print(f"    process={el:.1f}s  K={st['dynamic_k']}  "
                  f"score_q95={st['score_q95']:.2f}  "
                  f"rate_5.5={st['rate_abs_5.5']*100:.2f}%")
            sys.stdout.flush()
            results[(sym, tf)] = st

    # ── Persist JSON ──
    if results:
        try:
            with open(OUTPUT_JSON, "w") as f:
                json.dump(_sanitize_for_json(
                    {f"{k[0]}|{k[1]}": v for k, v in results.items()}
                ), f, indent=2, allow_nan=False)
        except Exception as e:
            print(f"WARN: JSON save failed: {e}")

    if not results:
        print("\nNo results collected — cannot proceed with diagnostics.")
        return

    # ═══════════════════════════════════════════════════════════════
    # §1  Raw score statistics
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §1  RAW SCORE STATISTICS (per asset × tf)")
    print("=" * 78)
    print(f"{'symbol':<10} {'tf':<5} {'Nfeat':>7} {'K':>3} "
          f"{'mean':>8} {'std':>8} {'Q50':>8} {'Q95':>8} {'Q99':>8} "
          f"{'skew':>8} {'kurt':>8}")
    for (sym, tf), s in results.items():
        print(f"{sym:<10} {tf:<5} {s['n_features_used']:>7} "
              f"{s['dynamic_k']:>3} "
              f"{s['score_mean']:>8.3f} {s['score_std']:>8.3f} "
              f"{s['score_q50']:>8.3f} {s['score_q95']:>8.3f} "
              f"{s['score_q99']:>8.3f} "
              f"{s['score_skew']:>8.2f} {s['score_kurt']:>8.2f}")

    # ═══════════════════════════════════════════════════════════════
    # §2  Signal rate at fixed absolute thresholds
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §2  SIGNAL RATE AT FIXED ABSOLUTE SCORE THRESHOLD")
    print("      Q1: if rates vary wildly → absolute thresholds fail")
    print("=" * 78)
    print(f"{'symbol':<10} {'tf':<5} "
          f"{'≥3.0':>8} {'≥4.0':>8} {'≥5.0':>8} {'≥5.5':>8} "
          f"{'≥6.0':>8} {'≥7.0':>8} {'≥8.0':>8} {'≥10':>8}")
    for (sym, tf), s in results.items():
        print(f"{sym:<10} {tf:<5} "
              f"{s['rate_abs_3.0']*100:>7.2f}% {s['rate_abs_4.0']*100:>7.2f}% "
              f"{s['rate_abs_5.0']*100:>7.2f}% {s['rate_abs_5.5']*100:>7.2f}% "
              f"{s['rate_abs_6.0']*100:>7.2f}% {s['rate_abs_7.0']*100:>7.2f}% "
              f"{s['rate_abs_8.0']*100:>7.2f}% {s['rate_abs_10.0']*100:>7.2f}%")

    # ═══════════════════════════════════════════════════════════════
    # §3  Z-score threshold test
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §3  Z-SCORE THRESHOLD TEST")
    print("      Q2: for a normal var, z≥1.645 fires ~5.00% of bars.")
    print("      If all values cluster near 5% → z-normalization is")
    print("      distribution-safe. Otherwise use quantile thresholds.")
    print("=" * 78)
    print(f"{'symbol':<10} {'tf':<5} "
          f"{'zS>+1.6':>9} {'zS<-1.6':>9} {'zS|>1.96':>9} "
          f"{'zH>+1.6':>9} {'zH<-1.6':>9} "
          f"{'zA>+1.6':>9} {'zA<-1.6':>9}")
    for (sym, tf), s in results.items():
        print(f"{sym:<10} {tf:<5} "
              f"{s.get('zscore_rate_above_1.645', 0)*100:>8.2f}% "
              f"{s.get('zscore_rate_below_neg1.645', 0)*100:>8.2f}% "
              f"{s.get('zscore_rate_beyond_1.96', 0)*100:>8.2f}% "
              f"{s.get('zdH_rate_above_1.645', 0)*100:>8.2f}% "
              f"{s.get('zdH_rate_below_neg1.645', 0)*100:>8.2f}% "
              f"{s.get('zaccel_rate_above_1.645', 0)*100:>8.2f}% "
              f"{s.get('zaccel_rate_below_neg1.645', 0)*100:>8.2f}%")

    # ═══════════════════════════════════════════════════════════════
    # §4  Distribution shape
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §4  DISTRIBUTION SHAPE (skew / excess kurtosis)")
    print("      Q3: |skew|<0.5 and |kurt|<1 → roughly normal")
    print("          |skew|>1 or |kurt|>3   → heavy tail / asymmetric")
    print("=" * 78)
    print(f"{'symbol':<10} {'tf':<5} "
          f"{'sc_skew':>9} {'sc_kurt':>9} "
          f"{'dH_skew':>9} {'dH_kurt':>9} "
          f"{'ac_skew':>9} {'ac_kurt':>9}")
    for (sym, tf), s in results.items():
        print(f"{sym:<10} {tf:<5} "
              f"{s['score_skew']:>9.2f} {s['score_kurt']:>9.2f} "
              f"{s['dH_skew']:>9.2f} {s['dH_kurt']:>9.2f} "
              f"{s['accel_skew']:>9.2f} {s['accel_kurt']:>9.2f}")

    # ═══════════════════════════════════════════════════════════════
    # §5  Entropy / friction / gauge scales
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §5  ENTROPY / FRICTION / GAUGE SCALE")
    print("=" * 78)
    print(f"{'symbol':<10} {'tf':<5} "
          f"{'H_mean':>8} {'H_std':>8} {'H_max_theo':>11} {'H/theo':>8} "
          f"{'Γ_mean':>9} {'Γ_std':>9} {'gauge_μ':>10} {'gauge_σ':>10}")
    for (sym, tf), s in results.items():
        print(f"{sym:<10} {tf:<5} "
              f"{s['H_mean']:>8.3f} {s['H_std']:>8.3f} "
              f"{s['H_max_theoretical']:>11.3f} {s['H_ratio_mean']:>8.3f} "
              f"{s['friction_mean']:>9.3f} {s['friction_std']:>9.3f} "
              f"{s['gauge_mean']:>10.3f} {s['gauge_std']:>10.3f}")

    # ═══════════════════════════════════════════════════════════════
    # §6  Regime composition
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §6  REGIME COMPOSITION (ranging / trending / explosive)")
    print("      Q4: are all three regimes present in real data?")
    print("=" * 78)
    print(f"{'symbol':<10} {'tf':<5} "
          f"{'%ranging':>10} {'%trending':>11} {'%explosive':>12}")
    for (sym, tf), s in results.items():
        print(f"{sym:<10} {tf:<5} "
              f"{s['pct_ranging']*100:>9.2f}% "
              f"{s['pct_trending']*100:>10.2f}% "
              f"{s['pct_explosive']*100:>11.2f}%")

    # ═══════════════════════════════════════════════════════════════
    # §7  Score distribution by regime
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §7  SCORE DISTRIBUTION BY REGIME")
    print("      Q5: if μ(score) or rate(5.5) differ substantially across")
    print("          regimes → we need regime-conditional thresholds.")
    print("=" * 78)
    print(f"{'symbol':<10} {'tf':<5} "
          f"{'μ_range':>9} {'μ_trend':>9} {'μ_explo':>9} "
          f"{'r5.5_rng':>10} {'r5.5_trn':>10} {'r5.5_exp':>10}")
    for (sym, tf), s in results.items():
        mr = s.get('score_mean_in_ranging')
        mt = s.get('score_mean_in_trending')
        me = s.get('score_mean_in_explosive')
        rr = s.get('rate_5.5_in_ranging')
        rt = s.get('rate_5.5_in_trending')
        re = s.get('rate_5.5_in_explosive')
        def _f(v): return f"{v:.3f}" if v is not None else "—"
        def _p(v): return f"{v*100:.2f}%" if v is not None else "—"
        print(f"{sym:<10} {tf:<5} "
              f"{_f(mr):>9} {_f(mt):>9} {_f(me):>9} "
              f"{_p(rr):>10} {_p(rt):>10} {_p(re):>10}")

    # ═══════════════════════════════════════════════════════════════
    # §8  Price / tick-size feasibility
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §8  PRICE / TICK-SIZE FEASIBILITY")
    print("      Q6: does 1 bps penetration ≥ 1 tick across assets?")
    print("=" * 78)
    print(f"{'symbol':<10} {'tf':<5} {'price_now':>16} {'tick_size':>16} "
          f"{'ticks_per_bps':>14}")
    for (sym, tf), s in results.items():
        p  = s.get('price_now', 0)
        tk = s.get('tick_size')
        tb = s.get('ticks_per_bps')
        t_str = f"{tk:.10f}" if tk and tk > 0 else "n/a"
        b_str = f"{tb:.3f}" if tb is not None else "n/a"
        print(f"{sym:<10} {tf:<5} {p:>16.8f} {t_str:>16} {b_str:>14}")

    # ═══════════════════════════════════════════════════════════════
    # §9  Cross-TF comparison of the same asset
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §9  CROSS-TF COMPARISON (same asset, different TFs)")
    print("      Q7: does the SAME asset behave consistently across TFs?")
    print("=" * 78)
    for sym in ASSETS:
        rows = [(tf, results[(sym, tf)]) for tf in TIMEFRAMES
                if (sym, tf) in results]
        if not rows:
            continue
        print(f"\n  {sym}:")
        print(f"    {'tf':<5} {'Q95':>8} {'rate_5.5':>10} "
              f"{'μ_dH':>11} {'σ_dH':>11} {'μ_score':>10} {'σ_score':>10}")
        for tf, s in rows:
            print(f"    {tf:<5} {s['score_q95']:>8.2f} "
                  f"{s['rate_abs_5.5']*100:>9.2f}% "
                  f"{s['dH_mean']:>11.5f} {s['dH_std']:>11.5f} "
                  f"{s['score_mean']:>10.3f} {s['score_std']:>10.3f}")

    # ═══════════════════════════════════════════════════════════════
    # §10  Automated verdict summary
    # ═══════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  §10  AUTOMATED VERDICT")
    print("=" * 78)

    print("\n  [Q1] Signal-rate spread at MIN_SCORE=5.5 (per TF):")
    for tf in TIMEFRAMES:
        rates = [results[(s, tf)]['rate_abs_5.5'] * 100
                 for s in ASSETS if (s, tf) in results]
        if len(rates) > 1:
            spread = max(rates) - min(rates)
            ratio = max(rates) / max(min(rates), 1e-6)
            print(f"    [{tf:<3}] min={min(rates):6.2f}%  "
                  f"max={max(rates):6.2f}%  "
                  f"spread={spread:6.2f} pp   max/min={ratio:6.1f}×")

    print("\n  [Q2] z-score consistency (target 5.00% for perfect normal):")
    z_rates = [results[k]['zscore_rate_above_1.645'] * 100
               for k in results]
    if z_rates:
        print(f"    min={min(z_rates):.2f}%  max={max(z_rates):.2f}%  "
              f"mean={np.mean(z_rates):.2f}%  std={np.std(z_rates):.2f}%")

    print("\n  [Q3] Distribution shape extremes:")
    print(f"    max |score_skew| = "
          f"{max(abs(s['score_skew']) for s in results.values()):.2f}")
    print(f"    max |score_kurt| = "
          f"{max(abs(s['score_kurt']) for s in results.values()):.2f}")
    print(f"    max |dH_skew|    = "
          f"{max(abs(s['dH_skew']) for s in results.values()):.2f}")
    print(f"    max |dH_kurt|    = "
          f"{max(abs(s['dH_kurt']) for s in results.values()):.2f}")

    print("\n  [Q4] Regime composition ranges across all (asset, TF):")
    pr = [s['pct_ranging'] * 100 for s in results.values()]
    pt = [s['pct_trending'] * 100 for s in results.values()]
    pe = [s['pct_explosive'] * 100 for s in results.values()]
    print(f"    %ranging  : {min(pr):5.1f} – {max(pr):5.1f}  (mean {np.mean(pr):.1f})")
    print(f"    %trending : {min(pt):5.1f} – {max(pt):5.1f}  (mean {np.mean(pt):.1f})")
    print(f"    %explosive: {min(pe):5.1f} – {max(pe):5.1f}  (mean {np.mean(pe):.1f})")

    print("\n  [Q5] Score-mean shift across regimes (per asset):")
    shifts = []
    for k, s in results.items():
        vals = [s.get('score_mean_in_ranging'),
                s.get('score_mean_in_trending'),
                s.get('score_mean_in_explosive')]
        vals = [v for v in vals if v is not None]
        if len(vals) > 1:
            shifts.append(max(vals) - min(vals))
    if shifts:
        print(f"    min shift = {min(shifts):.3f}  "
              f"max shift = {max(shifts):.3f}  "
              f"mean shift = {np.mean(shifts):.3f}")
    else:
        print("    not enough data")

    print("\n  [Q6] Tick feasibility (1 bps in ticks):")
    bad = [(s, tf) for (s, tf), v in results.items()
           if v.get('ticks_per_bps') is not None
           and v['ticks_per_bps'] < 1.0]
    good = [(s, tf) for (s, tf), v in results.items()
            if v.get('ticks_per_bps') is not None
            and v['ticks_per_bps'] >= 1.0]
    n_known = len(bad) + len(good)
    print(f"    measured: {n_known} pairs  |  "
          f"1 bps < 1 tick in {len(bad)} of them")
    for s, tf in bad:
        v = results[(s, tf)]
        print(f"      {s:<10} {tf:<5} price={v['price_now']:.6f} "
              f"tick={v['tick_size']}  ticks/bps={v['ticks_per_bps']:.3f}")

    print(f"\n  Full JSON diagnostics written to: {OUTPUT_JSON}")
    print("=" * 78)
    print("  Send the complete output above (sections §1 through §10).")
    print("=" * 78)


if __name__ == "__main__":
    main()
