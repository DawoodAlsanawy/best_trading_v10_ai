#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ml_filter_trainer_v6.py
-----------------------
Sequence-aware Meta-Labeling trainer.

Extends v5 (52 features) with 40 sequence features:
    For each of 10 "core" features, over W=20 window:
        - mean, std, slope, last   → 10 × 4 = 40 features.
    Total = 92 features.

First 52 features are IDENTICAL to v5 (backward compatible).

Usage:
    python3 ml_filter_trainer_v6.py --months 24 --assets 10 --capital 100
"""

import argparse, importlib.util, os, sys, pickle
from datetime import datetime
import numpy as np

try:
    import lightgbm as lgb
    _LGBM_AVAILABLE = True
except ImportError:
    _LGBM_AVAILABLE = False


# ════════════════════════════════════════════════════════════════
# Load bot
# ════════════════════════════════════════════════════════════════
BOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "best_trading_v10_ai5_2.py")
if not os.path.exists(BOT_PATH):
    for alt in ["best_trading_v12.py", "best_trading_v10.py"]:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), alt)
        if os.path.exists(p):
            BOT_PATH = p
            break
    else:
        print("ERROR: bot file not found")
        sys.exit(1)

spec = importlib.util.spec_from_file_location("bot", BOT_PATH)
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
CFG = bot.CFG
print(f"[Setup] Loaded bot: {BOT_PATH}")


# ════════════════════════════════════════════════════════════════
# Feature schema
# ════════════════════════════════════════════════════════════════
SEQ_WINDOW = 20
SEQ_CORE = [
    "ret_24h", "rvol_1h", "rvol_24h", "tf_agreement", "trend_1h",
    "candle_body_ratio", "upper_wick_ratio", "volume_z_20",
    "range_position_20", "atr_percentile",
]

ML_FEATURE_NAMES = [
    # ─── 52 base (v5, unchanged) ───
    "score_raw", "score_log", "T_info", "dyn_sl_factor", "dyn_risk",
    "action_buy", "geo_accel", "friction", "gauge_force", "delta_gap",
    "log_V", "C_neg", "dH", "dF", "atr_ratio", "adv_ratio",
    "hour", "tri",
    "hour_sin", "hour_cos", "dow", "is_weekend",
    "ret_24h", "ret_1h", "rvol_1h", "rvol_24h", "dist_ema", "vol_z",
    "candle_body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "consecutive_same_dir", "candle_dir_agrees",
    "trend_1h", "trend_4h", "trend_1d", "tf_agreement",
    "volume_z_20", "volume_slope_20", "volume_price_corr_20", "volume_ratio_50",
    "hour_sin_2", "hour_cos_2", "dow_sin", "dow_cos", "minutes_to_funding",
    "range_position_20", "dist_from_20_high", "dist_from_20_low",
    "atr_percentile", "vol_of_vol", "range_expansion",
]
# ─── 40 sequence features (v6) ───
for _c in SEQ_CORE:
    for _s in ("mean", "std", "slope", "last"):
        ML_FEATURE_NAMES.append(f"seq_{_c}_{_s}")


# ════════════════════════════════════════════════════════════════
# Base 52-feature extractor (identical to v5)
# ════════════════════════════════════════════════════════════════
def _base_features_v5(sig, ad) -> np.ndarray:
    ci = sig.close_idx
    fi = sig.feat_idx
    try:
        ts = sig.timestamp
        hour = ts.hour; minute = ts.minute; dow = ts.dayofweek
        hour_sin = float(np.sin(2 * np.pi * hour / 24))
        hour_cos = float(np.cos(2 * np.pi * hour / 24))
        dow_sin = float(np.sin(2 * np.pi * dow / 7))
        dow_cos = float(np.cos(2 * np.pi * dow / 7))
        is_weekend = 1.0 if dow >= 5 else 0.0
        minutes_to_funding = (480 - ((hour * 60 + minute) % 480)) / 480.0

        closes = ad.closes; highs = ad.highs; lows = ad.lows; vols = ad.volumes
        opens = getattr(ad, 'opens', None)
        if opens is None:
            opens_arr = np.empty_like(closes)
            opens_arr[0] = closes[0]; opens_arr[1:] = closes[:-1]
        else:
            opens_arr = opens

        p_now = float(closes[ci]); o_now = float(opens_arr[ci])
        h_now = float(highs[ci]); l_now = float(lows[ci]); v_now = float(vols[ci])

        ret_24h = (p_now - float(closes[ci-24])) / max(float(closes[ci-24]),1e-12) if ci>=24 else 0.0
        ret_1h  = (p_now - float(closes[ci-1]))  / max(float(closes[ci-1]),1e-12)  if ci>=1  else 0.0

        def _rvol(window):
            if ci < window+1: return 0.0
            w = closes[ci-window: ci+1]
            lr = np.diff(np.log(np.maximum(w, 1e-12)))
            return float(np.std(lr))
        rvol_1h = _rvol(20); rvol_24h = _rvol(100)

        ema200_val = float(ad.ema200[ci]) if ci < len(ad.ema200) else p_now
        dist_ema = (p_now - ema200_val) / max(ema200_val, 1e-12)

        if ci >= 50:
            vw = vols[ci-50: ci+1]
            vm = float(np.mean(vw)); vs = float(np.std(vw)) + 1e-12
            vol_z = (v_now - vm) / vs
        else:
            vol_z = 0.0

        rng = h_now - l_now
        if rng > 1e-12:
            candle_body_ratio = abs(p_now - o_now) / rng
            upper_wick_ratio  = (h_now - max(o_now, p_now)) / rng
            lower_wick_ratio  = (min(o_now, p_now) - l_now) / rng
        else:
            candle_body_ratio = upper_wick_ratio = lower_wick_ratio = 0.0

        consec = 0
        if ci >= 1:
            sgn0 = 1 if p_now > o_now else (-1 if p_now < o_now else 0)
            for k in range(1, min(6, ci+1)):
                c_ = closes[ci-k]; o_ = opens_arr[ci-k]
                sg_ = 1 if c_ > o_ else (-1 if c_ < o_ else 0)
                if sg_ == sgn0 and sgn0 != 0: consec += 1
                else: break
        consecutive_same_dir = float(consec)

        candle_dir_agrees = 1.0 if ((p_now > o_now and sig.action=="BUY") or
                                    (p_now < o_now and sig.action=="SELL")) else 0.0

        trend_1h = np.sign(closes[ci] - closes[ci-60])   if ci>=60   else 0.0
        trend_4h = np.sign(closes[ci] - closes[ci-240])  if ci>=240  else 0.0
        trend_1d = np.sign(closes[ci] - closes[ci-1440]) if ci>=1440 else 0.0
        sig_dir  = 1 if sig.action=="BUY" else -1
        tf_agreement = (float(np.sign(trend_1h)==sig_dir) +
                        float(np.sign(trend_4h)==sig_dir) +
                        float(np.sign(trend_1d)==sig_dir)) / 3.0

        if ci >= 20:
            v20 = vols[ci-20: ci+1]
            vm20 = float(np.mean(v20)); vs20 = float(np.std(v20)) + 1e-12
            volume_z_20 = (v_now - vm20) / vs20
            x = np.arange(len(v20), dtype=np.float64); xm = x.mean(); ym = float(np.mean(v20))
            num = float(np.sum((x-xm)*(v20-ym))); den = float(np.sum((x-xm)**2)) + 1e-12
            volume_slope_20 = num / den / (vm20 + 1e-12)
            if len(v20) >= 3:
                w = closes[ci-20: ci+1]
                absr = np.abs(np.diff(np.log(np.maximum(w, 1e-12))))
                vv = vols[ci-19: ci+1]
                if len(absr)==len(vv) and len(vv)>=3:
                    m1 = absr.mean(); m2 = float(np.mean(vv))
                    num2 = np.sum((absr-m1)*(vv-m2))
                    den2 = np.sqrt(np.sum((absr-m1)**2)*np.sum((vv-m2)**2)) + 1e-12
                    volume_price_corr_20 = float(num2/den2)
                else:
                    volume_price_corr_20 = 0.0
            else:
                volume_price_corr_20 = 0.0
        else:
            volume_z_20 = volume_slope_20 = volume_price_corr_20 = 0.0

        volume_ratio_50 = (v_now / (float(np.mean(vols[ci-50: ci+1])) + 1e-12)
                           if ci>=50 else 1.0)

        if ci >= 20:
            h20 = float(np.max(highs[ci-20: ci+1]))
            l20 = float(np.min(lows[ci-20: ci+1]))
            range_position_20 = (p_now - l20) / (h20 - l20 + 1e-12)
            dist_from_20_high = (p_now - h20) / p_now
            dist_from_20_low  = (p_now - l20) / p_now
        else:
            range_position_20 = 0.5; dist_from_20_high = dist_from_20_low = 0.0

        if ci >= 100:
            atr_window = ad.atr14[ci-100: ci+1]
            atr_percentile = float(np.mean(atr_window <= ad.atr14[ci]))
        else:
            atr_percentile = 0.5

        if ci >= 80:
            sig_w = 20; vovs = []
            for k in range(60):
                ii = ci - k
                if ii - sig_w < 0: break
                ww = closes[ii-sig_w: ii+1]
                lrw = np.diff(np.log(np.maximum(ww, 1e-12)))
                vovs.append(np.std(lrw))
            vol_of_vol = float(np.std(vovs)) if len(vovs) >= 5 else 0.0
        else:
            vol_of_vol = 0.0

        range_expansion = (h_now - l_now) / (float(ad.atr14[ci]) + 1e-12)

        v = np.array([
            float(sig.score), float(np.log1p(max(sig.score, 0.0))),
            float(sig.T_info_val), float(sig.dyn_sl_factor), float(sig.dynamic_risk),
            1.0 if sig.action=="BUY" else 0.0,
            float(ad.geodesic_accel[fi]), float(ad.friction[fi]),
            float(ad.gauge_force[fi]), float(ad.delta_gap[fi]),
            float(np.log1p(max(ad.V[fi], 0.0))), float(-ad.C[fi]),
            float(ad.dH[fi]), float(ad.dF[fi]),
            float(sig.atr / max(sig.price, 1e-12)),
            float(ad.adv_usd[ci] / max(ad.closes[ci], 1e-12)),
            float(hour), float(sig.tri_val),
            hour_sin, hour_cos, float(dow), is_weekend,
            float(ret_24h), float(ret_1h), float(rvol_1h), float(rvol_24h),
            float(dist_ema), float(vol_z),
            float(candle_body_ratio), float(upper_wick_ratio), float(lower_wick_ratio),
            float(consecutive_same_dir), float(candle_dir_agrees),
            float(trend_1h), float(trend_4h), float(trend_1d), float(tf_agreement),
            float(volume_z_20), float(volume_slope_20), float(volume_price_corr_20),
            float(volume_ratio_50),
            hour_sin, hour_cos, dow_sin, dow_cos, float(minutes_to_funding),
            float(range_position_20), float(dist_from_20_high), float(dist_from_20_low),
            float(atr_percentile), float(vol_of_vol), float(range_expansion),
        ], dtype=np.float64)
    except Exception:
        return np.zeros(52, dtype=np.float64)

    if not np.all(np.isfinite(v)):
        v = np.where(np.isfinite(v), v, 0.0)
    return v


# ════════════════════════════════════════════════════════════════
# Single core-feature computation at arbitrary index
# ════════════════════════════════════════════════════════════════
def _core_at(ad, sig, name: str, idx: int) -> float:
    closes = ad.closes; highs = ad.highs; lows = ad.lows; vols = ad.volumes
    try:
        n = len(closes)
        if idx < 0 or idx >= n: return 0.0
        if name == "ret_24h":
            if idx < 24: return 0.0
            return (closes[idx]-closes[idx-24]) / max(closes[idx-24], 1e-12)
        if name == "rvol_1h":
            if idx < 21: return 0.0
            w = closes[idx-20: idx+1]
            return float(np.std(np.diff(np.log(np.maximum(w, 1e-12)))))
        if name == "rvol_24h":
            if idx < 101: return 0.0
            w = closes[idx-100: idx+1]
            return float(np.std(np.diff(np.log(np.maximum(w, 1e-12)))))
        if name == "trend_1h":
            if idx < 60: return 0.0
            return float(np.sign(closes[idx]-closes[idx-60]))
        if name == "tf_agreement":
            t1  = np.sign(closes[idx]-closes[idx-60])   if idx>=60   else 0
            t4  = np.sign(closes[idx]-closes[idx-240])  if idx>=240  else 0
            t1d = np.sign(closes[idx]-closes[idx-1440]) if idx>=1440 else 0
            sig_dir = 1 if sig.action=="BUY" else -1
            return (float(np.sign(t1)==sig_dir) + float(np.sign(t4)==sig_dir) +
                    float(np.sign(t1d)==sig_dir)) / 3.0
        if name == "candle_body_ratio":
            rng = highs[idx] - lows[idx]
            if rng < 1e-12: return 0.0
            opens_arr = getattr(ad, 'opens', None)
            o_ = opens_arr[idx] if opens_arr is not None else (closes[idx-1] if idx>0 else closes[idx])
            return abs(closes[idx]-o_) / rng
        if name == "upper_wick_ratio":
            rng = highs[idx] - lows[idx]
            if rng < 1e-12: return 0.0
            opens_arr = getattr(ad, 'opens', None)
            o_ = opens_arr[idx] if opens_arr is not None else (closes[idx-1] if idx>0 else closes[idx])
            return (highs[idx] - max(o_, closes[idx])) / rng
        if name == "volume_z_20":
            if idx < 20: return 0.0
            vw = vols[idx-20: idx+1]
            vm = float(np.mean(vw)); vs = float(np.std(vw)) + 1e-12
            return (float(vols[idx])-vm) / vs
        if name == "range_position_20":
            if idx < 20: return 0.5
            h20 = float(np.max(highs[idx-20: idx+1]))
            l20 = float(np.min(lows[idx-20: idx+1]))
            return (float(closes[idx])-l20) / (h20-l20+1e-12)
        if name == "atr_percentile":
            if idx < 100 or idx >= len(ad.atr14): return 0.5
            w = ad.atr14[idx-100: idx+1]
            return float(np.mean(w <= ad.atr14[idx]))
    except Exception:
        return 0.0
    return 0.0


def _seq_stats(ad, sig, name: str, ci: int, W: int):
    """(mean, std, slope, last) of `name` over window [ci-W+1, ci]."""
    if ci < W:
        return 0.0, 0.0, 0.0, 0.0
    vals = np.array(
        [_core_at(ad, sig, name, ci-k) for k in range(W-1, -1, -1)],
        dtype=np.float64
    )
    vals = np.where(np.isfinite(vals), vals, 0.0)
    m = float(np.mean(vals)); sd = float(np.std(vals)); last = float(vals[-1])
    x = np.arange(W, dtype=np.float64); xm = x.mean()
    num = float(np.sum((x-xm)*(vals-m)))
    den = float(np.sum((x-xm)**2)) + 1e-12
    slope = num / den
    return m, sd, slope, last


def extract_ml_features(sig, ad) -> np.ndarray:
    """92-feature extractor: 52 base + 40 sequence (10 core × 4 stats)."""
    base = _base_features_v5(sig, ad)
    ci = sig.close_idx
    parts = []
    for name in SEQ_CORE:
        parts.extend(_seq_stats(ad, sig, name, ci, SEQ_WINDOW))
    seq = np.array(parts, dtype=np.float64)
    v = np.concatenate([base, seq])
    if not np.all(np.isfinite(v)):
        v = np.where(np.isfinite(v), v, 0.0)
    return v


# ════════════════════════════════════════════════════════════════
# Data collection
# ════════════════════════════════════════════════════════════════
def collect_training_data(months, n_assets, capital, timeframe):
    import ccxt
    exchange = ccxt.binance({'enableRateLimit': True, 'options': {'defaultType': 'future'}})
    CFG.timeframe = timeframe
    CFG.history_days = months * 30
    CFG.n_assets = n_assets
    CFG.INITIAL_CAPITAL = capital

    print(f"[1/5] Scanning top {n_assets}...")
    syms = bot.scan_top_assets(exchange, n_assets)
    print(f"[2/5] Fetching {months} months...")
    raw = bot.fetch_all(syms, exchange, timeframe, CFG.history_days, workers=5)
    if not raw: sys.exit("no data")

    print(f"[3/5] Processing {len(raw)} symbols...")
    assets = {}
    for i, (sym, df) in enumerate(raw.items(), 1):
        ad = bot.process_asset(sym, df, current_capital=capital)
        if ad is not None:
            assets[sym] = ad
            print(f"      [{i}/{len(raw)}] {sym}: OK")

    print(f"[4/5] Signals...")
    sigs = bot.build_signals(assets, mode="backtest")
    sigs = bot.deduplicate_signals(sigs)
    print(f"      {len(sigs):,} signals")

    print(f"[5/5] Portfolio...")
    corr_matrix = bot.precompute_correlations(assets)
    trades, _ = bot.simulate_portfolio(sigs, assets, corr_matrix, "backtest")
    print(f"      {len(trades):,} trades")

    sig_index = {(s.symbol, s.timestamp): s for s in sigs}
    X_list, y_list, w_list, matched = [], [], [], []
    for t in trades:
        sig = sig_index.get((t.symbol, t.entry_time))
        if sig is None: continue
        ad = assets.get(t.symbol)
        if ad is None: continue
        X_list.append(extract_ml_features(sig, ad))
        y_list.append(1 if t.net_pnl > 0 else 0)
        w_list.append(float(abs(t.log_return)))
        matched.append(t)

    X = np.vstack(X_list)
    y = np.array(y_list, dtype=np.int32)
    w = np.clip(np.array(w_list), 1e-4, 0.2); w = w / w.mean()
    return X, y, w, matched, assets


# ════════════════════════════════════════════════════════════════
# Walk-forward CV
# ════════════════════════════════════════════════════════════════
def walk_forward_validate(X, y, w, n_windows=4, embargo_frac=0.02):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, log_loss

    n = len(y); ws = n // (n_windows + 1); results = []
    for k in range(1, n_windows + 1):
        tr_end = k * ws
        emb = int(n * embargo_frac)
        te_start = tr_end + emb
        te_end = min(te_start + ws, n)
        if te_end - te_start < 30: continue
        Xtr, ytr, wtr = X[:tr_end], y[:tr_end], w[:tr_end]
        Xte, yte = X[te_start:te_end], y[te_start:te_end]
        if len(set(ytr)) < 2 or len(set(yte)) < 2: continue
        sc = StandardScaler()
        Xtr_s = sc.fit_transform(Xtr); Xte_s = sc.transform(Xte)
        clf = LogisticRegression(C=0.05, penalty='l2', max_iter=3000,
                                  class_weight='balanced', random_state=42)
        clf.fit(Xtr_s, ytr, sample_weight=wtr)
        p = clf.predict_proba(Xte_s)[:, 1]
        results.append({'fold': k, 'train_n': tr_end,
                        'test_n': te_end - te_start,
                        'auc': roc_auc_score(yte, p),
                        'logloss': log_loss(yte, p)})
    return results


# ════════════════════════════════════════════════════════════════
# Failure-pattern report
# ════════════════════════════════════════════════════════════════
def failure_pattern_report(X, y, feature_names, top_k=20):
    print("\n" + "=" * 70)
    print("  FAILURE PATTERN REPORT (v6, 92 features)")
    print("=" * 70)
    print(f"  Base win rate: {y.mean()*100:.2f}%  (n={len(y)})")
    print(f"\n  {'feature':<32s} {'low':>7s} {'mid':>7s} {'high':>7s} {'spread':>8s}")
    results = []
    for j, name in enumerate(feature_names):
        col = X[:, j]
        if not np.all(np.isfinite(col)): continue
        q33 = np.quantile(col, 0.33); q66 = np.quantile(col, 0.66)
        mlo = col <= q33; mhi = col >= q66; mmid = ~mlo & ~mhi
        wl = y[mlo].mean() if mlo.sum()>10 else np.nan
        wm = y[mmid].mean() if mmid.sum()>10 else np.nan
        wh = y[mhi].mean() if mhi.sum()>10 else np.nan
        if np.isnan(wl) or np.isnan(wh): continue
        results.append((abs(wl-wh), name, wl, wm, wh))
    results.sort(reverse=True)
    for spread, name, wl, wm, wh in results[:top_k]:
        marker = " ← pattern" if spread > 0.10 else ""
        print(f"  {name:<32s} {wl*100:6.1f}% {wm*100:6.1f}% {wh*100:6.1f}% "
              f"{spread*100:7.2f}%{marker}")
    print("=" * 70)
    return results


# ════════════════════════════════════════════════════════════════
# Model + training
# ════════════════════════════════════════════════════════════════
def build_model():
    if _LGBM_AVAILABLE:
        return lgb.LGBMClassifier(
            n_estimators=250, max_depth=3, num_leaves=4,
            learning_rate=0.03, min_child_samples=30,
            reg_alpha=0.5, reg_lambda=0.5,
            class_weight='balanced', random_state=42, verbose=-1,
        )
    from sklearn.linear_model import LogisticRegression
    return LogisticRegression(C=0.05, penalty='l2', max_iter=3000,
                               class_weight='balanced', random_state=42)


def train_final(X, y, w):
    from sklearn.preprocessing import StandardScaler
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import roc_auc_score, log_loss

    n = len(y); split = int(0.70 * n)
    Xtr, ytr, wtr = X[:split], y[:split], w[:split]
    Xte, yte = X[split:], y[split:]

    sc = StandardScaler()
    Xtr_s = sc.fit_transform(Xtr); Xte_s = sc.transform(Xte)

    base = build_model()
    try: base.fit(Xtr_s, ytr, sample_weight=wtr)
    except TypeError: base.fit(Xtr_s, ytr)

    try:
        calib = CalibratedClassifierCV(base, method='sigmoid', cv=3)
        calib.fit(Xtr_s, ytr, sample_weight=wtr)
        model = calib
    except TypeError:
        model = base

    p_tr = model.predict_proba(Xtr_s)[:, 1]
    p_te = model.predict_proba(Xte_s)[:, 1]
    auc_tr = roc_auc_score(ytr, p_tr); auc_te = roc_auc_score(yte, p_te)
    ll_te = log_loss(yte, p_te)
    print(f"\n[Eval] AUC_train={auc_tr:.4f}  AUC_test={auc_te:.4f}  "
          f"logloss={ll_te:.4f}")

    try:
        if _LGBM_AVAILABLE and hasattr(base, 'feature_importances_'):
            imp = base.feature_importances_
        else:
            imp = np.abs(base.coef_[0])
        order = np.argsort(-imp)[:15]
        print("[Eval] Top features:")
        for i in order:
            print(f"        {ML_FEATURE_NAMES[i]:>32s}  imp={imp[i]:+.4f}")
    except Exception:
        pass

    return {'model': model, 'scaler': sc, 'X_te': Xte_s, 'y_te': yte,
            'auc_train': auc_tr, 'auc_test': auc_te,
            'model_type': 'lightgbm' if _LGBM_AVAILABLE else 'logreg'}


def select_threshold(res, trades, min_reject=0.10, max_reject=0.35):
    model = res['model']; Xte = res['X_te']; yte = res['y_te']
    split = int(0.70 * len(trades)); test_trades = trades[split:]
    if len(test_trades) != len(yte): return 0.45, {'error': 'mismatch'}
    p_te = model.predict_proba(Xte)[:, 1]

    def sharpe_of(subset):
        if len(subset) < 5: return 0.0
        lrs = np.array([t.log_return for t in subset])
        mu, sd = lrs.mean(), lrs.std(ddof=1)
        return float(mu / sd * np.sqrt(252)) if sd > 1e-10 else 0.0

    baseline = sharpe_of(test_trades)
    best = {'threshold': 0.45, 'sharpe': baseline, 'reject': 0.0}
    sweep = []
    for th in np.arange(0.30, 0.71, 0.05):
        kept = [t for t, p in zip(test_trades, p_te) if p >= th]
        rej = 1.0 - len(kept) / max(len(test_trades), 1)
        sh = sharpe_of(kept)
        sweep.append({'threshold': float(th), 'reject': rej,
                      'sharpe': sh, 'kept': len(kept)})
        if min_reject <= rej <= max_reject and sh > best['sharpe']:
            best = {'threshold': float(th), 'sharpe': sh, 'reject': rej}
    best['baseline_sharpe'] = baseline; best['sweep'] = sweep
    return best['threshold'], best


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--months", type=int, default=24)
    p.add_argument("--assets", type=int, default=10)
    p.add_argument("--capital", type=float, default=100.0)
    p.add_argument("--timeframe", type=str, default=None)
    p.add_argument("--out", type=str, default="ml_filter.pkl")
    p.add_argument("--min-auc", type=float, default=0.55)
    p.add_argument("--target-reject", type=float, default=0.20)
    args = p.parse_args()

    timeframe = args.timeframe or CFG.timeframe

    print("=" * 70)
    print(f"  ML Filter Trainer v6 (92 features, sequence-aware)")
    print(f"  LightGBM available: {_LGBM_AVAILABLE}")
    print("=" * 70)

    X, y, w, trades, assets = collect_training_data(
        args.months, args.assets, args.capital, timeframe)
    print(f"\n[Data] X.shape={X.shape}  pos_rate={y.mean():.3f}")

    failure_pattern_report(X, y, ML_FEATURE_NAMES, top_k=25)

    print(f"\n[Walk-Forward CV]")
    wf = walk_forward_validate(X, y, w, n_windows=4, embargo_frac=0.02)
    for r in wf:
        print(f"  fold {r['fold']}: train={r['train_n']:5d} "
              f"test={r['test_n']:5d} AUC={r['auc']:.4f} "
              f"logloss={r['logloss']:.4f}")
    wf_aucs = [r['auc'] for r in wf] if wf else [0.5]
    print(f"  Mean AUC (WF): {np.mean(wf_aucs):.4f} ± {np.std(wf_aucs):.4f}")

    res = train_final(X, y, w)
    threshold, info = select_threshold(
        res, trades,
        min_reject=max(0.05, args.target_reject - 0.10),
        max_reject=min(0.40, args.target_reject + 0.15))

    print(f"\n[Threshold]")
    print(f"  Baseline Sharpe: {info.get('baseline_sharpe', 0):.3f}")
    print(f"  Selected        : {threshold:.3f}")
    print(f"  Reject rate     : {info.get('reject', 0)*100:.1f}%")
    print(f"  Filtered Sharpe : {info.get('sharpe', 0):.3f}")
    print(f"  Improvement     : {info.get('sharpe', 0) - info.get('baseline_sharpe', 0):+.3f}")

    accept = res['auc_test'] >= args.min_auc
    print(f"\n[Quality] AUC_test={res['auc_test']:.4f} → "
          f"{'✅ ACCEPT' if accept else '⚠️  WEAK'}")

    payload = {
        'model': res['model'], 'scaler': res['scaler'],
        'features': ML_FEATURE_NAMES,
        'threshold': float(threshold),
        'metadata': {
            'trained_at': datetime.now().isoformat(),
            'auc_train': float(res['auc_train']),
            'auc_test': float(res['auc_test']),
            'wf_mean_auc': float(np.mean(wf_aucs)),
            'wf_std_auc': float(np.std(wf_aucs)),
            'baseline_sharpe': float(info.get('baseline_sharpe', 0)),
            'filtered_sharpe': float(info.get('sharpe', 0)),
            'reject_rate': float(info.get('reject', 0)),
            'model_type': res['model_type'],
            'n_features': len(ML_FEATURE_NAMES),
            'seq_window': SEQ_WINDOW,
            'seq_core': SEQ_CORE,
        }
    }
    with open(args.out, 'wb') as f:
        pickle.dump(payload, f)
    print(f"\n[Save] → {args.out}")
    print("=" * 70)


if __name__ == "__main__":
    main()
