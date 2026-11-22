#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_opposite_patterns.py — Discovery of "Flip Patterns" in Backtest Trades
═══════════════════════════════════════════════════════════════════════════

الغرض:
    تحليل trades_log_backtest.jsonl + market_data_cache/ لاكتشاف الحالات التي
    كان البوت فيها سيُحقق ربحاً لو دخل بالاتجاه المعاكس.

المنهجية:
    1. تصنيف كل صفقة إلى A/B/C:
       - A: صفقة رابحة (net_pnl > 0)
       - B: خاسرة لكن السوق لم يستمر ضدها (لا فائدة من العكس)
       - C: خاسرة والسوق استمر ضدها بقوة (العكس كان سيربح)
    2. استخراج 25+ ميزة لكل صفقة من لحظة الإشارة فقط (no lookahead)
    3. اختبارات إحصائية (Mann-Whitney, Cohen's d, AUC, permutation)
    4. اكتشاف أنماط مركّبة (Decision Tree depth 2-3 + pairwise)
    5. اختبار الاستقرار الزمني (train/validation split)
    6. تقييم كل نمط بـ: precision, recall, lift, permutation p-value

النتائج:
    - opposite_analysis.json     — بيانات كاملة + إحصاءات
    - opposite_analysis.html     — تقرير تفاعلي مع رسوم
    - opposite_patterns.txt      — ملخص الأنماط القابلة للتنفيذ

الاستخدام:
    python diagnose_opposite_patterns.py \
        --trades trades_log_backtest.jsonl \
        --cache market_data_cache \
        --timeframe 4h \
        --flip-r 2.0 \
        --horizon-bars 100 \
        --min-support 30 \
        --out-prefix opposite_analysis
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import base64
import io
import json
import os
import sys
import warnings
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

try:
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split
    _SKLEARN = True
except Exception:
    _SKLEARN = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _MPL = True
except Exception:
    _MPL = False


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

TF_TO_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400,
}

MIN_FEATURE_SAMPLES = 20
PERMUTATION_ITERATIONS = 1000
DT_MAX_DEPTH = 3
PAIRWISE_QUANTILES = [0.33, 0.67]


# ═══════════════════════════════════════════════════════════════════════════
# TRADE LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_trades(path):
    """Load trade records from JSONL, skipping the _meta header."""
    if not os.path.exists(path):
        print(f"✗ Trades file not found: {path}")
        return None, None

    meta = None
    trades = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("_meta"):
                meta = obj
                continue
            trades.append(obj)

    print(f"✓ Loaded {len(trades):,} trades from {path}")
    if meta:
        print(f"  Config: tf={meta.get('timeframe')}, "
              f"N={meta.get('N')}, K_MAX={meta.get('K_MAX')}, "
              f"cap=${meta.get('INITIAL_CAPITAL')}")
    return trades, meta


# ═══════════════════════════════════════════════════════════════════════════
# CACHE LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_cache(cache_dir, timeframe):
    """Load all parquet files for the given timeframe."""
    if not os.path.isdir(cache_dir):
        print(f"✗ Cache directory not found: {cache_dir}")
        return {}

    cache = {}
    suffix = f"_{timeframe}.parquet"
    n_loaded = 0
    for fn in os.listdir(cache_dir):
        if not fn.endswith(suffix):
            continue
        sym_file = fn[:-len(suffix)]
        sym = sym_file.replace("_", "/", 1)  # BTC_USDT → BTC/USDT
        full_path = os.path.join(cache_dir, fn)
        try:
            df = pd.read_parquet(full_path)
            if df is None or len(df) < 50:
                continue
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            cache[sym] = df
            n_loaded += 1
        except Exception as e:
            print(f"  ⚠ Failed to load {fn}: {e}")

    print(f"✓ Loaded {n_loaded} symbol(s) from {cache_dir}")
    return cache


# ═══════════════════════════════════════════════════════════════════════════
# CLASSIFICATION (A / B / C)
# ═══════════════════════════════════════════════════════════════════════════

def _find_bar_index(df, ts_str):
    """Find the bar index (in df) at or just before ts_str."""
    try:
        ts = pd.Timestamp(ts_str)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        idx = df.index.searchsorted(ts, side="right") - 1
        if idx < 0 or idx >= len(df):
            return None
        return int(idx)
    except Exception:
        return None


def classify_trade(trade, cache_df, flip_r=2.0, flip_sl=1.0,
                   horizon_bars=100):
    """
    Returns 'A', 'B', 'C', or 'skip' (with reason).
    """
    net = float(trade.get("net_pnl", 0))
    exit_rsn = str(trade.get("exit_reason", ""))
    action = str(trade.get("action", ""))
    entry_px = float(trade.get("entry_price", 0))
    sl_dist = float(trade.get("sl_dist_initial", 0))
    hold_bars = int(trade.get("hold_bars", 0))

    # Skip: incomplete / broken data
    if entry_px <= 0 or sl_dist <= 0 or action not in ("BUY", "SELL"):
        return "skip", "invalid_data"
    if exit_rsn == "EndOfData":
        return "skip", "no_horizon"

    # Winner = Category A
    if net > 0:
        return "A", "winner"

    # Find exit bar
    entry_bar = _find_bar_index(cache_df, trade.get("entry_time", ""))
    if entry_bar is None:
        return "skip", "no_entry_bar"
    # Approximate exit bar: entry_ci + hold_bars (but entry_ci in log
    # may be off from signal time; use conservative: signal_bar + hold_bars + 10)
    exit_bar_guess = entry_bar + hold_bars + 10
    if exit_bar_guess >= len(cache_df):
        return "skip", "no_future_data"

    horizon_end = min(exit_bar_guess + horizon_bars, len(cache_df))
    if horizon_end - exit_bar_guess < 20:
        return "skip", "horizon_too_short"

    future = cache_df.iloc[exit_bar_guess:horizon_end]
    if len(future) == 0:
        return "skip", "no_future_bars"

    exit_px = float(trade.get("exit_price", 0))
    if exit_px <= 0:
        exit_px = entry_px  # fallback

    # For BUY loser: flip SELL. Profit = price drops further.
    # For SELL loser: flip BUY. Profit = price rises further.
    try:
        min_low = float(future["Low"].min())
        max_high = float(future["High"].max())
    except Exception:
        return "skip", "future_data_missing"

    if action == "BUY":
        # Flip SELL: profit = exit_px - min_low (price drops more)
        # Flip SELL: loss = max_high - exit_px (price bounces)
        mfe_flip = (exit_px - min_low) / sl_dist
        mae_flip = (max_high - exit_px) / sl_dist
    else:  # SELL
        # Flip BUY: profit = max_high - exit_px
        # Flip BUY: loss = exit_px - min_low
        mfe_flip = (max_high - exit_px) / sl_dist
        mae_flip = (exit_px - min_low) / sl_dist

    if mfe_flip >= flip_r and mfe_flip > mae_flip:
        return "C", f"trend_against(mfe={mfe_flip:.2f}R)"
    return "B", f"whipsaw(mfe={mfe_flip:.2f}R,mae={mae_flip:.2f}R)"


# ═══════════════════════════════════════════════════════════════════════════
# FEATURE EXTRACTION (no look-ahead)
# ═══════════════════════════════════════════════════════════════════════════

def _ema(values, span):
    return pd.Series(values).ewm(span=span, adjust=False).mean().values


def _rsi(closes, period=14):
    """Wilder's RSI."""
    n = len(closes)
    rsi = np.full(n, 50.0)
    if n < period + 1:
        return rsi
    deltas = np.diff(closes)
    gains = np.maximum(deltas, 0)
    losses = np.maximum(-deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss < 1e-12:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    return rsi


def _safe_float(v, default=0.0):
    try:
        f = float(v)
        if not np.isfinite(f):
            return default
        return f
    except Exception:
        return default


def extract_features(trade, cache_df, btc_df, all_assets_at_ts,
                     last_trade_ts_per_sym, N=24):
    """Extract 25+ features from signal-time data only."""
    feats = {}

    entry_time_str = trade.get("entry_time", "")
    try:
        entry_ts = pd.Timestamp(entry_time_str)
        if entry_ts.tz is None:
            entry_ts = entry_ts.tz_localize("UTC")
    except Exception:
        return None

    sig_bar = _find_bar_index(cache_df, entry_time_str)
    if sig_bar is None or sig_bar < N + 200:
        return None

    # ─── From log (already computed at signal time) ───
    feats["score"] = _safe_float(trade.get("score"))
    feats["T_info"] = _safe_float(trade.get("T_info_val"))
    feats["friction"] = _safe_float(trade.get("friction"))
    feats["gauge_force"] = _safe_float(trade.get("gauge_force"))
    feats["geodesic_accel"] = _safe_float(trade.get("geodesic_accel"))
    feats["delta_gap"] = _safe_float(trade.get("delta_gap"))
    feats["E_therm"] = _safe_float(trade.get("E_therm"))
    feats["H"] = _safe_float(trade.get("H"))
    feats["dH"] = _safe_float(trade.get("dH"))
    feats["dF"] = _safe_float(trade.get("dF"))
    feats["V"] = _safe_float(trade.get("V"))
    feats["C"] = _safe_float(trade.get("C"))
    feats["tri_val"] = _safe_float(trade.get("tri_val"))
    feats["H_over_Hmax"] = _safe_float(trade.get("H_over_Hmax"))
    feats["ema_slope"] = _safe_float(trade.get("ema_slope"))
    feats["ema_slope_against"] = _safe_float(trade.get("ema_slope_against"))
    feats["dist_from_ema_norm"] = _safe_float(trade.get("dist_from_ema_norm"))
    feats["sl_sigma"] = _safe_float(trade.get("sl_sigma"))
    feats["friction_drag_over_sl"] = _safe_float(
        trade.get("friction_drag_over_sl"))

    # ─── From cache: recompute z_dev ───
    closes = cache_df["Close"].values
    try:
        win = closes[sig_bar - N: sig_bar]
        if len(win) >= N:
            _mu = float(np.mean(win))
            _sd = float(np.std(win))
            if _sd > 1e-12:
                feats["z_dev"] = (closes[sig_bar] - _mu) / _sd
            else:
                feats["z_dev"] = 0.0
        else:
            feats["z_dev"] = 0.0
    except Exception:
        feats["z_dev"] = 0.0

    # ─── ATR% ───
    try:
        if sig_bar >= 14:
            highs = cache_df["High"].values[sig_bar - 14:sig_bar + 1]
            lows = cache_df["Low"].values[sig_bar - 14:sig_bar + 1]
            prev_close = cache_df["Close"].values[sig_bar - 14:sig_bar]
            tr = np.maximum(highs[1:] - lows[1:],
                            np.maximum(np.abs(highs[1:] - prev_close),
                                       np.abs(lows[1:] - prev_close)))
            atr = float(np.mean(tr)) if len(tr) > 0 else 0.0
            feats["atr_pct"] = atr / max(closes[sig_bar], 1e-9)
        else:
            feats["atr_pct"] = 0.0
    except Exception:
        feats["atr_pct"] = 0.0

    # ─── RSI ───
    try:
        rsi_arr = _rsi(closes, 14)
        feats["rsi"] = float(rsi_arr[sig_bar])
        feats["rsi_dev_from_50"] = feats["rsi"] - 50.0
    except Exception:
        feats["rsi"] = 50.0
        feats["rsi_dev_from_50"] = 0.0

    # ─── Volume ───
    try:
        vols = cache_df["Volume"].values
        if sig_bar >= 20:
            vol_mean = float(np.mean(vols[sig_bar - 20: sig_bar]))
            feats["vol_ratio_20"] = vols[sig_bar] / max(vol_mean, 1e-9)
        else:
            feats["vol_ratio_20"] = 1.0
    except Exception:
        feats["vol_ratio_20"] = 1.0

    # ─── Range position (20 bars) ───
    try:
        highs = cache_df["High"].values
        lows = cache_df["Low"].values
        if sig_bar >= 20:
            h20 = float(np.max(highs[sig_bar - 20:sig_bar + 1]))
            l20 = float(np.min(lows[sig_bar - 20:sig_bar + 1]))
            rng = max(h20 - l20, 1e-9)
            feats["range_pos_20"] = (closes[sig_bar] - l20) / rng
            feats["dist_high_20"] = (h20 - closes[sig_bar]) / max(
                closes[sig_bar], 1e-9)
            feats["dist_low_20"] = (closes[sig_bar] - l20) / max(
                closes[sig_bar], 1e-9)
        else:
            feats["range_pos_20"] = 0.5
            feats["dist_high_20"] = 0.0
            feats["dist_low_20"] = 0.0
    except Exception:
        feats["range_pos_20"] = 0.5
        feats["dist_high_20"] = 0.0
        feats["dist_low_20"] = 0.0

    # ─── Candle shape ───
    try:
        opens = cache_df["Open"].values
        highs = cache_df["High"].values
        lows = cache_df["Low"].values
        o, h, l, c = opens[sig_bar], highs[sig_bar], lows[sig_bar], closes[sig_bar]
        rng = max(h - l, 1e-9)
        feats["body_ratio"] = abs(c - o) / rng
        feats["upper_wick"] = (h - max(o, c)) / rng
        feats["lower_wick"] = (min(o, c) - l) / rng
        feats["close_vs_mid"] = ((c - l) / rng) - 0.5
    except Exception:
        feats["body_ratio"] = 0.0
        feats["upper_wick"] = 0.0
        feats["lower_wick"] = 0.0
        feats["close_vs_mid"] = 0.0

    # ─── Consecutive direction ───
    try:
        closes_ar = cache_df["Close"].values
        opens_ar = cache_df["Open"].values
        consec = 0
        sign_0 = 1 if closes_ar[sig_bar] > opens_ar[sig_bar] else -1
        for k in range(1, min(6, sig_bar)):
            sign_k = 1 if closes_ar[sig_bar - k] > opens_ar[sig_bar - k] else -1
            if sign_k == sign_0:
                consec += 1
            else:
                break
        feats["consecutive_dir"] = consec * sign_0
    except Exception:
        feats["consecutive_dir"] = 0

    # ─── EMA200 distance ───
    try:
        ema200 = _ema(closes, 200)
        if sig_bar >= 50:
            feats["dist_ema200_pct"] = (
                closes[sig_bar] - ema200[sig_bar]
            ) / max(closes[sig_bar], 1e-9)
        else:
            feats["dist_ema200_pct"] = 0.0
    except Exception:
        feats["dist_ema200_pct"] = 0.0

    # ─── BTC regime ───
    if btc_df is not None:
        try:
            btc_bar = _find_bar_index(btc_df, entry_time_str)
            if btc_bar is not None and btc_bar >= 200:
                btc_closes = btc_df["Close"].values
                win_b = btc_closes[btc_bar - N: btc_bar]
                if len(win_b) >= N:
                    mu_b = float(np.mean(win_b))
                    sd_b = float(np.std(win_b))
                    if sd_b > 1e-12:
                        feats["btc_z_dev"] = (btc_closes[btc_bar] - mu_b) / sd_b
                    else:
                        feats["btc_z_dev"] = 0.0
                else:
                    feats["btc_z_dev"] = 0.0
                ema_b = _ema(btc_closes, 200)
                if btc_bar >= 50:
                    slope_b = (ema_b[btc_bar] - ema_b[btc_bar - 50]) / 50.0
                    atr_b = max(abs(btc_closes[btc_bar]) * 0.01, 1e-9)
                    feats["btc_ema_slope_norm"] = slope_b * 50.0 / atr_b
                else:
                    feats["btc_ema_slope_norm"] = 0.0
                feats["btc_above_ema200"] = 1.0 if (
                    btc_closes[btc_bar] > ema_b[btc_bar]) else 0.0
            else:
                feats["btc_z_dev"] = 0.0
                feats["btc_ema_slope_norm"] = 0.0
                feats["btc_above_ema200"] = 0.0
        except Exception:
            feats["btc_z_dev"] = 0.0
            feats["btc_ema_slope_norm"] = 0.0
            feats["btc_above_ema200"] = 0.0
    else:
        feats["btc_z_dev"] = 0.0
        feats["btc_ema_slope_norm"] = 0.0
        feats["btc_above_ema200"] = 0.0

    # ─── Cross-asset extremity rank ───
    try:
        if all_assets_at_ts and len(all_assets_at_ts) >= 5:
            my_action = trade.get("action", "BUY")
            my_zd = feats["z_dev"]
            # For BUY: we're extreme-low; for SELL: extreme-high
            if my_action == "BUY":
                n_more_extreme = sum(1 for z in all_assets_at_ts
                                     if z < my_zd)
            else:
                n_more_extreme = sum(1 for z in all_assets_at_ts
                                     if z > my_zd)
            feats["extremity_rank"] = n_more_extreme / len(all_assets_at_ts)
        else:
            feats["extremity_rank"] = 0.5
    except Exception:
        feats["extremity_rank"] = 0.5

    # ─── Time of day / day of week ───
    try:
        feats["hour"] = float(entry_ts.hour)
        feats["dow"] = float(entry_ts.dayofweek)
    except Exception:
        feats["hour"] = 0.0
        feats["dow"] = 0.0

    # ─── Days since last trade on same symbol ───
    sym = trade.get("symbol", "")
    last_ts = last_trade_ts_per_sym.get(sym)
    if last_ts is not None:
        delta_days = (entry_ts - last_ts).total_seconds() / 86400.0
        feats["days_since_last"] = min(delta_days, 30.0)
    else:
        feats["days_since_last"] = 30.0

    # ─── Direction as numeric ───
    feats["action_code"] = 1.0 if trade.get("action") == "BUY" else -1.0

    return feats


def _collect_all_assets_zdev(cache, entry_time_str, N=24):
    """At a given time, compute z_dev for ALL symbols."""
    result = []
    for sym, df in cache.items():
        bar = _find_bar_index(df, entry_time_str)
        if bar is None or bar < N:
            continue
        closes = df["Close"].values
        win = closes[bar - N: bar]
        if len(win) < N:
            continue
        mu = float(np.mean(win))
        sd = float(np.std(win))
        if sd > 1e-12:
            result.append((closes[bar] - mu) / sd)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# STATISTICAL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def cohens_d(a, b):
    """Cohen's d between two samples."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0
    ma, mb = np.mean(a), np.mean(b)
    sa, sb = np.std(a, ddof=1), np.std(b, ddof=1)
    pooled = np.sqrt(((na - 1) * sa**2 + (nb - 1) * sb**2) / (na + nb - 2))
    if pooled < 1e-12:
        return 0.0
    return (ma - mb) / pooled


def analyze_feature(feat_name, group_c_vals, group_ab_vals):
    """Full statistical test for one feature."""
    try:
        a = np.array([v for v in group_c_vals if np.isfinite(v)],
                     dtype=np.float64)
        b = np.array([v for v in group_ab_vals if np.isfinite(v)],
                     dtype=np.float64)
    except Exception:
        return None

    if len(a) < MIN_FEATURE_SAMPLES or len(b) < MIN_FEATURE_SAMPLES:
        return None

    try:
        u_stat, p_value = stats.mannwhitneyu(a, b, alternative="two-sided")
    except Exception:
        return None

    # AUC (probability C > A+B by this feature)
    try:
        combined = np.concatenate([a, b])
        labels = np.concatenate([np.ones(len(a)), np.zeros(len(b))])
        if _SKLEARN:
            auc = roc_auc_score(labels, combined)
        else:
            # Manual AUC via U statistic
            auc = u_stat / (len(a) * len(b))
    except Exception:
        auc = 0.5

    d = cohens_d(a, b)

    return {
        "feature": feat_name,
        "n_c": int(len(a)),
        "n_ab": int(len(b)),
        "mean_c": float(np.mean(a)),
        "mean_ab": float(np.mean(b)),
        "median_c": float(np.median(a)),
        "median_ab": float(np.median(b)),
        "std_c": float(np.std(a, ddof=1)) if len(a) > 1 else 0.0,
        "std_ab": float(np.std(b, ddof=1)) if len(b) > 1 else 0.0,
        "cohens_d": float(d),
        "auc": float(auc),
        "p_value": float(p_value),
        "p_value_abs": abs(float(d)),
    }


def permutation_test_feature(feat_name, group_c_vals, group_ab_vals,
                              n_iter=PERMUTATION_ITERATIONS):
    """Permutation test for the mean difference."""
    try:
        a = np.array([v for v in group_c_vals if np.isfinite(v)],
                     dtype=np.float64)
        b = np.array([v for v in group_ab_vals if np.isfinite(v)],
                     dtype=np.float64)
    except Exception:
        return None
    if len(a) < MIN_FEATURE_SAMPLES or len(b) < MIN_FEATURE_SAMPLES:
        return None

    observed_diff = abs(np.mean(a) - np.mean(b))
    combined = np.concatenate([a, b])
    n_a = len(a)
    count_extreme = 0
    rng = np.random.default_rng(42)
    for _ in range(n_iter):
        perm = rng.permutation(combined)
        perm_a = perm[:n_a]
        perm_b = perm[n_a:]
        perm_diff = abs(np.mean(perm_a) - np.mean(perm_b))
        if perm_diff >= observed_diff:
            count_extreme += 1
    return (count_extreme + 1) / (n_iter + 1)


# ═══════════════════════════════════════════════════════════════════════════
# PATTERN DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════

def _rule_to_text(rule_dict):
    """Convert a rule dict to human-readable text."""
    parts = []
    for feat, op, val in rule_dict["conditions"]:
        parts.append(f"{feat} {op} {val:.4f}")
    return " AND ".join(parts)


def extract_tree_rules(tree, feature_names, X, y, min_support=30):
    """
    Extract leaf rules from a fitted DecisionTreeClassifier.
    Returns list of rule dicts with support, precision, etc.
    """
    rules = []
    tree_ = tree.tree_

    def _recurse(node, conditions):
        if tree_.feature[node] == -2:  # leaf
            # Identify samples reaching this leaf
            leaf_id = node
            decision_path = tree.decision_path(X)
            leaf_mask = decision_path[:, leaf_id].toarray().ravel().astype(bool)
            n_samples = int(leaf_mask.sum())
            if n_samples < min_support:
                return
            n_pos = int(y[leaf_mask].sum())
            precision = n_pos / n_samples if n_samples > 0 else 0.0
            rules.append({
                "conditions": list(conditions),
                "n_samples": n_samples,
                "n_positive": n_pos,
                "precision": float(precision),
                "recall": float(n_pos / max(int(y.sum()), 1)),
                "lift": float(precision / max(np.mean(y), 1e-9)),
            })
            return
        feat_idx = tree_.feature[node]
        threshold = tree_.threshold[node]
        feat_name = feature_names[feat_idx]
        # Left child: feature <= threshold
        _recurse(tree_.children_left[node],
                 conditions + [(feat_name, "<=", float(threshold))])
        # Right child: feature > threshold
        _recurse(tree_.children_right[node],
                 conditions + [(feat_name, ">", float(threshold))])

    _recurse(0, [])
    return rules


def permutation_test_tree(X, y, max_depth=DT_MAX_DEPTH,
                           n_iter=200, min_support=30):
    """
    Permutation test on best-rule precision-lift.
    Returns dict {observed_best_f1, p_value, null_dist}.
    """
    rng = np.random.default_rng(42)

    def _fit_and_extract(y_perm):
        try:
            clf = DecisionTreeClassifier(
                max_depth=max_depth, min_samples_leaf=min_support,
                random_state=42)
            clf.fit(X, y_perm)
            rules = extract_tree_rules(
                clf, [f"f{i}" for i in range(X.shape[1])],
                X, y_perm, min_support=min_support)
            if not rules:
                return 0.0
            # F1 for the best rule
            best_f1 = 0.0
            for r in rules:
                p = r["precision"]; rec = r["recall"]
                f1 = 2 * p * rec / max(p + rec, 1e-9)
                if f1 > best_f1:
                    best_f1 = f1
            return best_f1
        except Exception:
            return 0.0

    observed_f1 = _fit_and_extract(y)
    null_f1 = []
    for _ in range(n_iter):
        y_perm = rng.permutation(y)
        null_f1.append(_fit_and_extract(y_perm))
    null_f1 = np.array(null_f1)
    p_value = float((null_f1 >= observed_f1).mean())
    return {
        "observed_f1": float(observed_f1),
        "null_mean_f1": float(null_f1.mean()),
        "null_95pct": float(np.percentile(null_f1, 95)),
        "p_value": p_value,
    }


def discover_pairwise_patterns(df, top_features, min_support=30):
    """
    For each pair of top features, split each into tertiles and test
    the 4 extreme cells (low-low, low-high, high-low, high-high).
    """
    patterns = []
    if len(top_features) < 2:
        return patterns

    target = df["is_C"].values
    baseline = float(np.mean(target))
    n = len(df)

    for i in range(len(top_features)):
        for j in range(i + 1, len(top_features)):
            f1 = top_features[i]
            f2 = top_features[j]
            if f1 not in df.columns or f2 not in df.columns:
                continue
            v1 = df[f1].values
            v2 = df[f2].values
            if not (np.isfinite(v1).all() and np.isfinite(v2).all()):
                continue

            try:
                q_lo_1, q_hi_1 = np.quantile(v1, PAIRWISE_QUANTILES)
                q_lo_2, q_hi_2 = np.quantile(v2, PAIRWISE_QUANTILES)
            except Exception:
                continue

            cells = [
                ("low", "low", v1 <= q_lo_1, v2 <= q_lo_2),
                ("low", "high", v1 <= q_lo_1, v2 >= q_hi_2),
                ("high", "low", v1 >= q_hi_1, v2 <= q_lo_2),
                ("high", "high", v1 >= q_hi_1, v2 >= q_hi_2),
            ]
            for side1, side2, mask1, mask2 in cells:
                mask = mask1 & mask2
                n_match = int(mask.sum())
                if n_match < min_support:
                    continue
                n_pos = int(target[mask].sum())
                precision = n_pos / n_match
                recall = n_pos / max(int(target.sum()), 1)
                lift = precision / max(baseline, 1e-9)
                if precision < baseline * 1.3:
                    continue
                op1 = "<=" if side1 == "low" else ">="
                op2 = "<=" if side2 == "low" else ">="
                v1_val = q_lo_1 if side1 == "low" else q_hi_1
                v2_val = q_lo_2 if side2 == "low" else q_hi_2
                patterns.append({
                    "type": "pairwise",
                    "conditions": [
                        (f1, op1, float(v1_val)),
                        (f2, op2, float(v2_val)),
                    ],
                    "n_samples": n_match,
                    "n_positive": n_pos,
                    "precision": float(precision),
                    "recall": float(recall),
                    "lift": float(lift),
                })
    return patterns


# ═══════════════════════════════════════════════════════════════════════════
# VISUALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def _fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=80, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def plot_class_distribution(counts):
    if not _MPL:
        return ""
    fig, ax = plt.subplots(figsize=(6, 4))
    labels = ["A (Correct)", "B (Whipsaw)", "C (Trend-Against)"]
    vals = [counts.get("A", 0), counts.get("B", 0), counts.get("C", 0)]
    colors = ["#66bb6a", "#ffa726", "#ef5350"]
    ax.bar(labels, vals, color=colors)
    ax.set_ylabel("Trades")
    ax.set_title("Trade Classification")
    for i, v in enumerate(vals):
        ax.text(i, v + max(vals) * 0.01, str(v), ha="center")
    return _fig_to_base64(fig)


def plot_top_feature_aucs(feature_results, top_n=15):
    if not _MPL or not feature_results:
        return ""
    sorted_feats = sorted(feature_results,
                           key=lambda x: abs(x["auc"] - 0.5), reverse=True)[:top_n]
    fig, ax = plt.subplots(figsize=(8, max(4, len(sorted_feats) * 0.3)))
    names = [f["feature"] for f in sorted_feats]
    aucs = [f["auc"] for f in sorted_feats]
    colors = ["#66bb6a" if a > 0.5 else "#ef5350" for a in aucs]
    ax.barh(range(len(names)), [a - 0.5 for a in aucs], color=colors)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.axvline(0, color="black", lw=0.5)
    ax.set_xlabel("AUC − 0.5  (>0: higher in C, <0: lower in C)")
    ax.set_title(f"Top {top_n} Features by AUC")
    return _fig_to_base64(fig)


def plot_feature_distribution(df, feat_name):
    if not _MPL or feat_name not in df.columns:
        return ""
    fig, ax = plt.subplots(figsize=(6, 3))
    c_vals = df.loc[df["is_C"] == 1, feat_name].dropna()
    ab_vals = df.loc[df["is_C"] == 0, feat_name].dropna()
    if len(c_vals) > 0:
        ax.hist(c_vals, bins=30, alpha=0.6, label="C", color="#ef5350")
    if len(ab_vals) > 0:
        ax.hist(ab_vals, bins=30, alpha=0.5, label="A+B", color="#66bb6a")
    ax.set_title(f"{feat_name}")
    ax.legend(fontsize=8)
    return _fig_to_base64(fig)


# ═══════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_text_report(results, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 78 + "\n")
        f.write(" OPPOSITE-SIGNAL ANALYSIS REPORT\n")
        f.write("=" * 78 + "\n\n")

        counts = results["class_counts"]
        total = sum(counts.values())
        f.write(f"Class distribution:\n")
        f.write(f"  A (correct direction):    {counts.get('A', 0):6d}  "
                f"({counts.get('A', 0)/max(total,1)*100:5.1f}%)\n")
        f.write(f"  B (whipsaw):              {counts.get('B', 0):6d}  "
                f"({counts.get('B', 0)/max(total,1)*100:5.1f}%)\n")
        f.write(f"  C (trend against — flip): {counts.get('C', 0):6d}  "
                f"({counts.get('C', 0)/max(total,1)*100:5.1f}%)\n")
        f.write(f"  Skipped:                  {counts.get('skip', 0):6d}\n")
        f.write("\n")

        f.write("=" * 78 + "\n")
        f.write(" TOP 10 DISCRIMINATIVE FEATURES (by |AUC−0.5|)\n")
        f.write("=" * 78 + "\n")
        top_feats = results.get("top_features", [])
        for i, feat in enumerate(top_feats[:10], 1):
            f.write(f"\n{i}. {feat['feature']}\n")
            f.write(f"   AUC = {feat['auc']:.3f}   "
                    f"Cohen's d = {feat['cohens_d']:+.3f}   "
                    f"p = {feat['p_value']:.2e}\n")
            f.write(f"   C:    mean={feat['mean_c']:+.4f}  "
                    f"median={feat['median_c']:+.4f}  n={feat['n_c']}\n")
            f.write(f"   A+B:  mean={feat['mean_ab']:+.4f}  "
                    f"median={feat['median_ab']:+.4f}  n={feat['n_ab']}\n")

        f.write("\n" + "=" * 78 + "\n")
        f.write(" DISCOVERED PATTERNS (top 15)\n")
        f.write("=" * 78 + "\n")
        patterns = results.get("patterns", [])
        for i, pat in enumerate(patterns[:15], 1):
            f.write(f"\n{i}. [{pat['type']}]  "
                    f"precision={pat['precision']*100:.1f}%  "
                    f"lift={pat['lift']:.2f}  "
                    f"support={pat['n_samples']}\n")
            f.write(f"   Rule:\n")
            for cond in pat["conditions"]:
                f.write(f"     {cond[0]} {cond[1]} {cond[2]:.4f}\n")
            f.write(f"   In-sample: {pat['n_positive']}/{pat['n_samples']} "
                    f"are Category C\n")
            if "test_precision" in pat:
                f.write(f"   Out-of-sample: precision={pat['test_precision']*100:.1f}%  "
                        f"support={pat.get('test_support', 0)}\n")

        f.write("\n" + "=" * 78 + "\n")
        f.write(" RECOMMENDATIONS\n")
        f.write("=" * 78 + "\n")
        n_pat_strong = len([p for p in patterns if p.get("test_precision", 0) > 0.55])
        if n_pat_strong == 0:
            f.write("\nNo patterns passed out-of-sample validation.\n")
            f.write("Conclusion: no reliable flip signal found in this data.\n")
        else:
            f.write(f"\n{n_pat_strong} patterns passed out-of-sample validation "
                    f"with precision ≥ 55%.\n")
            f.write("Consider implementing these as a 'flip rule' in the bot.\n")


def generate_html_report(results, path):
    counts = results["class_counts"]
    top_feats = results.get("top_features", [])
    patterns = results.get("patterns", [])

    dist_img = plot_class_distribution(counts)
    auc_img = plot_top_feature_aucs(top_feats)
    first_feat = top_feats[0]["feature"] if top_feats else None
    dist_feat_img = plot_feature_distribution(
        results.get("df_for_plots"), first_feat) if first_feat else ""

    rows_feats = ""
    for f in top_feats[:20]:
        rows_feats += (
            f"<tr><td>{f['feature']}</td>"
            f"<td>{f['auc']:.3f}</td>"
            f"<td>{f['cohens_d']:+.3f}</td>"
            f"<td>{f['p_value']:.2e}</td>"
            f"<td>{f['mean_c']:+.4f}</td>"
            f"<td>{f['mean_ab']:+.4f}</td>"
            f"<td>{f['n_c']}</td><td>{f['n_ab']}</td></tr>"
        )

    rows_patterns = ""
    for i, p in enumerate(patterns[:20], 1):
        rule_text = " AND ".join([f"{c[0]} {c[1]} {c[2]:.3f}"
                                   for c in p["conditions"]])
        test_prec = p.get("test_precision", p["precision"])
        test_supp = p.get("test_support", p["n_samples"])
        rows_patterns += (
            f"<tr><td>{i}</td>"
            f"<td>{p['type']}</td>"
            f"<td style='font-family:monospace;font-size:11px'>{rule_text}</td>"
            f"<td>{p['precision']*100:.1f}%</td>"
            f"<td>{test_prec*100:.1f}%</td>"
            f"<td>{p['lift']:.2f}</td>"
            f"<td>{p['n_samples']}</td>"
            f"<td>{test_supp}</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Opposite-Signal Analysis</title>
<style>
body {{ background: #0d0d0d; color: #e0e0e0; font-family: -apple-system, sans-serif; padding: 20px; }}
h1 {{ color: #00e5ff; border-bottom: 2px solid #00e5ff; padding-bottom: 10px; }}
h2 {{ color: #66bb6a; margin-top: 30px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 10px; }}
th {{ background: #1e1e1e; padding: 8px; text-align: left; border-bottom: 2px solid #333; }}
td {{ padding: 6px; border-bottom: 1px solid #222; }}
tr:hover {{ background: #1a1a1a; }}
.kpi {{ display: inline-block; background: #1e1e1e; padding: 15px 25px; margin: 5px; border-radius: 8px; }}
.kpi-label {{ font-size: 11px; color: #999; }}
.kpi-val {{ font-size: 24px; font-weight: bold; }}
.kpi-val.pos {{ color: #66bb6a; }}
.kpi-val.neg {{ color: #ef5350; }}
.kpi-val.neu {{ color: #00e5ff; }}
img {{ max-width: 100%; margin: 10px 0; }}
.note {{ color: #999; font-style: italic; font-size: 12px; margin-top: 5px; }}
</style></head><body>

<h1>Opposite-Signal Pattern Discovery</h1>
<p class="note">Generated: {datetime.utcnow().isoformat()}Z</p>

<h2>Class Distribution</h2>
<div>
<div class="kpi"><div class="kpi-label">A (Correct)</div><div class="kpi-val pos">{counts.get('A', 0):,}</div></div>
<div class="kpi"><div class="kpi-label">B (Whipsaw)</div><div class="kpi-val neu">{counts.get('B', 0):,}</div></div>
<div class="kpi"><div class="kpi-label">C (Trend-Against)</div><div class="kpi-val neg">{counts.get('C', 0):,}</div></div>
<div class="kpi"><div class="kpi-label">Skipped</div><div class="kpi-val neu">{counts.get('skip', 0):,}</div></div>
</div>
{f'<img src="data:image/png;base64,{dist_img}" />' if dist_img else ''}

<h2>Top Discriminative Features</h2>
{f'<img src="data:image/png;base64,{auc_img}" />' if auc_img else ''}
<table>
<thead><tr><th>Feature</th><th>AUC</th><th>Cohen's d</th><th>p-value</th>
<th>mean (C)</th><th>mean (A+B)</th><th>n_C</th><th>n_A+B</th></tr></thead>
<tbody>{rows_feats}</tbody></table>

{f'<h2>Distribution of Top Feature</h2><img src="data:image/png;base64,{dist_feat_img}" />' if dist_feat_img else ''}

<h2>Discovered Patterns</h2>
<p class="note">
Patterns listed with both in-sample and out-of-sample precision.
Only patterns with out-of-sample precision > baseline and support ≥ 30 should be considered.
</p>
<table>
<thead><tr><th>#</th><th>Type</th><th>Rule</th><th>In-sample Prec</th>
<th>Out-of-sample Prec</th><th>Lift</th><th>In-samples</th><th>OOS-samples</th></tr></thead>
<tbody>{rows_patterns}</tbody></table>

<h2>Notes</h2>
<ul>
<li><strong>A</strong>: winning trade (flip would lose)</li>
<li><strong>B</strong>: losing trade but market didn't strongly continue (whipsaw)</li>
<li><strong>C</strong>: losing trade where market continued ≥ 2R against — <strong>flip would work</strong></li>
<li>AUC &gt; 0.5: feature is higher in C (stronger signal for flip)</li>
<li>AUC &lt; 0.5: feature is lower in C</li>
<li>Only patterns with out-of-sample support ≥ 30 should be trusted</li>
</ul>

</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="Discover flip patterns in backtest trades",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--trades", default="trades_log_backtest.jsonl",
                   help="Path to trades JSONL file")
    p.add_argument("--cache", default="market_data_cache",
                   help="Path to market data cache directory")
    p.add_argument("--timeframe", default="4h",
                   help="Timeframe used in backtest (default: 4h)")
    p.add_argument("--flip-r", type=float, default=2.0,
                   help="R multiple required to qualify as Category C "
                        "(default: 2.0)")
    p.add_argument("--horizon-bars", type=int, default=100,
                   help="Bars to look ahead after exit (default: 100)")
    p.add_argument("--min-support", type=int, default=30,
                   help="Minimum pattern support (default: 30)")
    p.add_argument("--out-prefix", default="opposite_analysis",
                   help="Output file prefix (default: opposite_analysis)")
    p.add_argument("--perf-perm", type=int, default=1000,
                   help="Permutation iterations for feature tests (default: 1000)")
    p.add_argument("--perf-tree-perm", type=int, default=100,
                   help="Permutation iterations for tree test (default: 100)")
    args = p.parse_args()

    print("=" * 78)
    print(" OPPOSITE-SIGNAL PATTERN DISCOVERY")
    print("=" * 78)
    print()

    # 1. Load trades
    trades, meta = load_trades(args.trades)
    if not trades:
        return 1

    # 2. Load cache
    cache = load_cache(args.cache, args.timeframe)
    if not cache:
        return 1

    # 3. Get BTC reference (special)
    btc_df = cache.get("BTC/USDT")

    # 4. Classify and extract features
    print("\nClassifying trades and extracting features...")
    records = []
    class_counts = defaultdict(int)
    last_ts_per_sym = {}
    skipped_reasons = defaultdict(int)

    # Sort by time to compute "days_since_last" correctly
    trades_sorted = sorted(trades, key=lambda t: t.get("entry_time", ""))

    for i, trade in enumerate(trades_sorted):
        if (i + 1) % 1000 == 0:
            print(f"  Processed {i + 1:,} / {len(trades_sorted):,}...")

        sym = trade.get("symbol", "")
        if sym not in cache:
            class_counts["skip"] += 1
            skipped_reasons["symbol_not_in_cache"] += 1
            continue
        cache_df = cache[sym]

        # Classify
        cls, reason = classify_trade(
            trade, cache_df,
            flip_r=args.flip_r,
            flip_sl=1.0,
            horizon_bars=args.horizon_bars,
        )
        if cls == "skip":
            class_counts["skip"] += 1
            skipped_reasons[reason] += 1
            continue
        class_counts[cls] += 1

        # Cross-asset z_dev at this time
        all_zdev = _collect_all_assets_zdev(
            cache, trade.get("entry_time", ""), N=24)

        # Features
        feats = extract_features(
            trade, cache_df, btc_df, all_zdev,
            last_ts_per_sym, N=24
        )

        # Update last_ts AFTER extraction (so days_since_last uses previous)
        try:
            ts = pd.Timestamp(trade.get("entry_time", ""))
            if ts.tz is None:
                ts = ts.tz_localize("UTC")
            last_ts_per_sym[sym] = ts
        except Exception:
            pass

        if feats is None:
            class_counts["skip"] += 1
            class_counts[cls] -= 1  # undo the count
            skipped_reasons["feature_extraction_failed"] += 1
            continue

        rec = {
            "trade_id": i,
            "symbol": sym,
            "action": trade.get("action"),
            "entry_time": trade.get("entry_time"),
            "net_pnl": float(trade.get("net_pnl", 0)),
            "class": cls,
            "class_reason": reason,
            "is_C": 1 if cls == "C" else 0,
            "is_A": 1 if cls == "A" else 0,
            "is_B": 1 if cls == "B" else 0,
        }
        rec.update(feats)
        records.append(rec)

    print(f"\n✓ Classified: A={class_counts.get('A', 0):,}, "
          f"B={class_counts.get('B', 0):,}, "
          f"C={class_counts.get('C', 0):,}, "
          f"skip={class_counts.get('skip', 0):,}")
    if skipped_reasons:
        print("  Skip reasons:")
        for r, c in sorted(skipped_reasons.items(), key=lambda x: -x[1]):
            print(f"    {r}: {c:,}")

    if not records:
        print("\n✗ No valid records — aborting")
        return 1

    # 5. Build DataFrame
    df = pd.DataFrame(records)
    print(f"\n✓ Feature matrix: {df.shape[0]} rows × {df.shape[1]} cols")

    n_c = int((df["is_C"] == 1).sum())
    n_ab = int((df["is_C"] == 0).sum())
    if n_c < 10:
        print(f"\n⚠ Only {n_c} Category-C samples — results will be noisy")

    # 6. Statistical analysis of features
    print("\nAnalyzing features...")
    feature_cols = [
        c for c in df.columns
        if c not in ("trade_id", "symbol", "action", "entry_time",
                     "net_pnl", "class", "class_reason",
                     "is_C", "is_A", "is_B")
    ]
    feature_results = []
    for feat in feature_cols:
        try:
            res = analyze_feature(
                feat,
                df.loc[df["is_C"] == 1, feat].values,
                df.loc[df["is_C"] == 0, feat].values,
            )
            if res is not None:
                feature_results.append(res)
        except Exception:
            continue

    # Sort by |AUC − 0.5|
    feature_results.sort(key=lambda x: abs(x["auc"] - 0.5), reverse=True)

    # Bonferroni correction
    n_tests = max(len(feature_results), 1)
    for f in feature_results:
        f["p_bonferroni"] = min(f["p_value"] * n_tests, 1.0)
        f["p_significant_bonf"] = f["p_bonferroni"] < 0.05

    # Permutation test for top 10
    print("Running permutation tests for top 10 features...")
    for f in feature_results[:10]:
        p_perm = permutation_test_feature(
            f["feature"],
            df.loc[df["is_C"] == 1, f["feature"]].values,
            df.loc[df["is_C"] == 0, f["feature"]].values,
            n_iter=args.perf_perm,
        )
        f["p_permutation"] = p_perm

    # 7. Pattern discovery
    print("\nDiscovering patterns...")
    top_feat_names = [f["feature"] for f in feature_results[:15]
                      if abs(f["auc"] - 0.5) > 0.05]

    all_patterns = []

    # 7a. Decision tree patterns
    if _SKLEARN and len(top_feat_names) > 0:
        print("  Training decision tree (depth=3)...")
        try:
            X = df[top_feat_names].fillna(0).values
            y = df["is_C"].values

            # Chronological train/test split
            n = len(df)
            split_idx = int(n * 0.6)
            df_sorted = df.sort_values("entry_time").reset_index(drop=True)
            X_sorted = df_sorted[top_feat_names].fillna(0).values
            y_sorted = df_sorted["is_C"].values

            X_train = X_sorted[:split_idx]
            y_train = y_sorted[:split_idx]
            X_test = X_sorted[split_idx:]
            y_test = y_sorted[split_idx:]

            if len(y_train) > 100 and len(y_test) > 100:
                clf = DecisionTreeClassifier(
                    max_depth=DT_MAX_DEPTH,
                    min_samples_leaf=max(args.min_support, 10),
                    random_state=42)
                clf.fit(X_train, y_train)

                # Extract rules from train
                train_rules = extract_tree_rules(
                    clf, top_feat_names, X_train, y_train,
                    min_support=args.min_support)

                # Test each rule on validation
                for r in train_rules:
                    r["type"] = "tree"
                    # Re-evaluate on test
                    mask_test = np.ones(len(X_test), dtype=bool)
                    for cond in r["conditions"]:
                        feat_idx = top_feat_names.index(cond[0])
                        op = cond[1]
                        val = cond[2]
                        if op == "<=":
                            mask_test &= (X_test[:, feat_idx] <= val)
                        else:
                            mask_test &= (X_test[:, feat_idx] > val)
                    n_test_match = int(mask_test.sum())
                    if n_test_match > 0:
                        n_test_pos = int(y_test[mask_test].sum())
                        r["test_precision"] = float(
                            n_test_pos / n_test_match)
                        r["test_support"] = n_test_match
                    else:
                        r["test_precision"] = 0.0
                        r["test_support"] = 0

                all_patterns.extend(train_rules)

                # Permutation test on best F1
                print(f"  Running tree permutation test "
                      f"({args.perf_tree_perm} iterations)...")
                perm_result = permutation_test_tree(
                    X_train, y_train,
                    max_depth=DT_MAX_DEPTH,
                    n_iter=args.perf_tree_perm,
                    min_support=args.min_support)
                print(f"    observed F1={perm_result['observed_f1']:.3f}, "
                      f"null_mean={perm_result['null_mean_f1']:.3f}, "
                      f"p={perm_result['p_value']:.4f}")
        except Exception as e:
            print(f"  ⚠ Tree training failed: {e}")
            perm_result = None
    else:
        perm_result = None

    # 7b. Pairwise patterns
    print("  Discovering pairwise patterns...")
    try:
        pair_patterns = discover_pairwise_patterns(
            df, top_feat_names[:10], min_support=args.min_support)
        all_patterns.extend(pair_patterns)
        print(f"    Found {len(pair_patterns)} pairwise patterns")
    except Exception as e:
        print(f"  ⚠ Pairwise discovery failed: {e}")

    # Sort patterns by lift × precision (best quality first)
    all_patterns.sort(
        key=lambda x: x.get("lift", 0) * x.get("precision", 0),
        reverse=True)

    # 8. Save JSON
    json_out = f"{args.out_prefix}.json"
    df_for_plots = df.copy()
    try:
        results = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "config": {
                "trades_file": args.trades,
                "cache_dir": args.cache,
                "timeframe": args.timeframe,
                "flip_r": args.flip_r,
                "horizon_bars": args.horizon_bars,
                "min_support": args.min_support,
            },
            "class_counts": dict(class_counts),
            "skipped_reasons": dict(skipped_reasons),
            "feature_results": feature_results,
            "top_features": feature_results[:15],
            "patterns": all_patterns[:50],
            "tree_permutation_test": perm_result,
        }
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n✓ Saved JSON: {json_out}")
    except Exception as e:
        print(f"  ⚠ JSON save failed: {e}")

    # 9. Generate text report
    txt_out = f"{args.out_prefix}_patterns.txt"
    try:
        results["df_for_plots"] = df_for_plots
        generate_text_report(results, txt_out)
        print(f"✓ Saved text report: {txt_out}")
    except Exception as e:
        print(f"  ⚠ Text report failed: {e}")

    # 10. Generate HTML report
    html_out = f"{args.out_prefix}.html"
    try:
        generate_html_report(results, html_out)
        print(f"✓ Saved HTML report: {html_out}")
    except Exception as e:
        print(f"  ⚠ HTML report failed: {e}")

    # 11. Console summary
    print("\n" + "=" * 78)
    print(" TOP 10 FEATURES")
    print("=" * 78)
    for i, f in enumerate(feature_results[:10], 1):
        sig_mark = "✓" if f.get("p_significant_bonf") else " "
        print(f"{i:2d}. {sig_mark} {f['feature']:28s}  "
              f"AUC={f['auc']:.3f}  "
              f"d={f['cohens_d']:+.2f}  "
              f"p_bonf={f.get('p_bonferroni', 0):.1e}")

    print("\n" + "=" * 78)
    print(" TOP 10 PATTERNS (by precision × lift)")
    print("=" * 78)
    for i, p in enumerate(all_patterns[:10], 1):
        rule_text = " AND ".join(
            [f"{c[0]} {c[1]} {c[2]:.3f}" for c in p["conditions"]])
        test_prec = p.get("test_precision", p["precision"])
        test_supp = p.get("test_support", p["n_samples"])
        print(f"{i:2d}. [{p['type']:8s}] precision={p['precision']*100:.1f}%  "
              f"OOS={test_prec*100:.1f}%  "
              f"lift={p['lift']:.2f}  "
              f"n={p['n_samples']}  OOS_n={test_supp}")
        print(f"    Rule: {rule_text}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
