#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trade_filter_diagnostic.py

أداة تشخيصية لاكتشاف الصفقات الخاسرة قبل الدخول.

المنهجية:
  1. تشغيل الـ pipeline كاملاً (fetch, process, build_signals, simulate).
  2. استخراج ~30 ميزة لكل صفقة عند لحظة الدخول (بدون أي اطلاع على المستقبل).
  3. تحليل أحادي المتغير لترتيب الميزات حسب قوتها التمييزية.
  4. نموذج لوجستي مع Walk-Forward validation.
  5. منحنى المقايضة (كم خاسر نرفض / كم رابح نخسر) لكل عتبة.
  6. كتابة تقرير شامل إلى ملف نصي.

الاستخدام:
  python trade_filter_diagnostic.py
  python trade_filter_diagnostic.py --timeframe 4h --history-days 730 --nassets 15
  python trade_filter_diagnostic.py --min-train 40 --output my_report.txt
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from collections import defaultdict

import numpy as np
import pandas as pd


# ════════════════════════════════════════════════════════════════
# 0. Optional dependencies
# ════════════════════════════════════════════════════════════════

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    print("[WARN] sklearn not installed - logistic regression disabled")

try:
    from scipy.stats import mannwhitneyu
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("[WARN] scipy not installed - Mann-Whitney disabled")


# ════════════════════════════════════════════════════════════════
# 1. Bot detection & import
# ════════════════════════════════════════════════════════════════

BOT_CANDIDATES = [
    "trading.py",
    "trading_best_version_with_tf4h_and_his_days_30.py",
    "best_trading_bot_22_9_2026.py",
]


def detect_bot_file(explicit=None):
    if explicit:
        if not os.path.exists(explicit):
            raise FileNotFoundError(f"Bot file not found: {explicit}")
        return explicit
    for c in BOT_CANDIDATES:
        if os.path.exists(c):
            return c
    for f in os.listdir("."):
        if f.endswith(".py") and "trading" in f.lower():
            return f
    raise FileNotFoundError(f"Could not find bot file. Tried: {BOT_CANDIDATES}")


def import_bot(path):
    abs_path = os.path.abspath(path)
    spec = importlib.util.spec_from_file_location("bot_module", abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bot_module"] = mod
    spec.loader.exec_module(mod)
    return mod


# ════════════════════════════════════════════════════════════════
# 2. Bot configuration setup
# ════════════════════════════════════════════════════════════════

def setup_bot_cfg(bot, timeframe, history_days, n_assets,
                  no_fixed_price=True, use_cache=False):
    """Configure the bot exactly as it would be configured in main()."""
    bot.CFG.timeframe = timeframe
    bot.CFG.history_days = history_days
    bot.CFG.n_assets = n_assets
    bot.CFG.mode = "backtest"
    bot.CFG.PO_FIXED_PRICE = not no_fixed_price
    bot.CFG.ASSET_CACHE_ENABLED = use_cache
    bot.CFG.PARALLEL_PROCESSING = False   # serial for reproducibility

    # TF scale
    try:
        import ccxt
        _probe = ccxt.binance()
        tf_scale, tf_secs, tf_hours = bot.compute_tf_scale(_probe, timeframe)
    except Exception:
        tf_scale, tf_secs, tf_hours = bot.compute_tf_scale(None, timeframe)

    bot.CFG.TF_SCALE = tf_scale
    bot.CFG.TF_SECONDS = tf_secs
    bot.CFG.TF_HOURS = tf_hours

    print(f"[Setup] TF={timeframe}  TF_SCALE={tf_scale:.3f}  "
          f"TF_HOURS={tf_hours:.3f}")

    # Window scaling (matches main())
    _tf_h = max(float(tf_hours), 1e-6)
    _n_min = int(np.ceil(float(getattr(bot.CFG, 'N_HOURS', 24.0)) / _tf_h))
    _w_min = int(np.ceil(float(getattr(bot.CFG, 'W_HOURS', 20.0)) / _tf_h))
    _l_min = int(np.ceil(float(getattr(bot.CFG, 'L_HOURS', 10.0)) / _tf_h))

    if bot.CFG.N < _n_min:
        bot.CFG.N = _n_min
    if bot.CFG.W < _w_min:
        bot.CFG.W = _w_min
    if bot.CFG.L < _l_min:
        bot.CFG.L = _l_min

    _adv_h = float(getattr(bot.CFG, 'ADV_HOURS', 24.0))
    bot.CFG.ADV_BARS = max(1, int(round(_adv_h / _tf_h)))

    print(f"[Setup] N={bot.CFG.N} W={bot.CFG.W} L={bot.CFG.L} "
          f"ADV_BARS={bot.CFG.ADV_BARS}")


# ════════════════════════════════════════════════════════════════
# 3. Full pipeline (fetch, process, build signals)
# ════════════════════════════════════════════════════════════════

def run_full_pipeline(bot):
    import ccxt

    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })

    print("[Pipeline] Scanning top assets...")
    syms = bot.scan_top_assets(exchange, bot.CFG.n_assets)
    print(f"[Pipeline] {len(syms)} symbols: {syms[:5]}...")

    print(f"[Pipeline] Fetching {bot.CFG.history_days} days of data...")
    t0 = time.time()
    raw, raw_sub = bot.fetch_all_with_subbars(
        syms, exchange, bot.CFG.timeframe,
        bot.CFG.history_days, workers=5
    )
    print(f"[Pipeline] Fetched {len(raw)} symbols in {time.time()-t0:.1f}s")

    print("[Pipeline] Processing assets...")
    t0 = time.time()
    assets = {}
    for i, (sym, df) in enumerate(raw.items()):
        try:
            ad = bot.process_asset(
                sym, df,
                current_capital=bot.CFG.INITIAL_CAPITAL,
                sub_df=raw_sub.get(sym) if raw_sub else None
            )
            if ad is not None:
                assets[sym] = ad
        except Exception as e:
            print(f"  [WARN] {sym}: {e}")
        if (i + 1) % 5 == 0:
            print(f"    processed {i+1}/{len(raw)}")
    print(f"[Pipeline] Processed {len(assets)}/{len(raw)} assets "
          f"in {time.time()-t0:.1f}s")

    print("[Pipeline] Building signals...")
    t0 = time.time()
    sigs = bot.build_signals(assets, mode="backtest")
    sigs = bot.deduplicate_signals(sigs)
    print(f"[Pipeline] Built {len(sigs)} signals in {time.time()-t0:.1f}s")

    print("[Pipeline] Computing correlations...")
    corr = bot.precompute_correlations(assets)

    return assets, sigs, corr


# ════════════════════════════════════════════════════════════════
# 4. Run simulate_portfolio and capture signal metadata
# ════════════════════════════════════════════════════════════════

def run_backtest_and_capture(bot, assets, sigs, corr):
    """Save signal info BEFORE simulation mutates them."""
    sig_info = {}
    for s in sigs:
        key = (s.symbol, s.timestamp)
        sig_info[key] = {
            'close_idx': int(s.close_idx),
            'feat_idx': int(s.feat_idx),
            'action': s.action,
            'price': float(s.price),
            'sl': float(s.sl),
            'tp1': float(s.tp1),
            'atr': float(s.atr),
            'score': float(s.score),
            'adv_usd': float(s.adv_usd),
            'tri_val': float(s.tri_val),
            'dynamic_risk': float(s.dynamic_risk),
            'T_info_val': float(s.T_info_val),
            'dyn_sl_factor': float(s.dyn_sl_factor),
            'entry_ref_price': float(s.entry_ref_price),
            'entry_base_dip': float(s.entry_base_dip),
        }

    print("[Backtest] Running simulate_portfolio...")
    t0 = time.time()
    trades, equity = bot.simulate_portfolio(sigs, assets, corr, "backtest")
    print(f"[Backtest] {len(trades)} trades executed in {time.time()-t0:.1f}s")

    return trades, equity, sig_info


# ════════════════════════════════════════════════════════════════
# 5. Feature extraction (no look-ahead)
# ════════════════════════════════════════════════════════════════

FEATURE_NAMES = [
    # Signal-level (from the Signal object)
    'score', 'action_buy', 'atr_frac', 'tri_val',
    'dyn_sl_factor', 'dynamic_risk', 'T_info_val',
    # Physics (from AssetData at feat_idx)
    'geodesic_accel', 'friction', 'gauge_force', 'delta_gap',
    'H_over_Hmax', 'dH', 'dF', 'V_norm', 'E_therm', 'T_info', 'C',
    # Geometry of the designed trade
    'sl_dist_frac', 'rr_design', 'friction_drag_over_sl', 'sl_sigma',
    # Market context
    'ema_slope_against', 'dist_from_ema_norm', 'atr_percentile',
    # Time-of-day
    'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos', 'is_weekend',
    # Dynamic (computed sequentially)
    'recent_trades_24h',
    'recent_losses_symbol_5',
    'recent_losses_portfolio_10',
]


def extract_static_features(bot, trade, info, assets):
    """Extract features that don't depend on trade history."""
    F = {}
    ad = assets.get(trade.symbol)
    if ad is None:
        return None

    fi = info['feat_idx']
    ci = info['close_idx']
    price = info['price']
    sl = info['sl']
    tp1 = info['tp1']
    action = info['action']

    if not (0 <= fi < len(ad.score)):
        return None

    # ── Signal-level features ──
    F['score'] = info['score']
    F['action_buy'] = 1.0 if action == 'BUY' else 0.0
    F['atr_frac'] = info['atr'] / max(price, 1e-12)
    F['tri_val'] = info['tri_val']
    F['dyn_sl_factor'] = info['dyn_sl_factor']
    F['dynamic_risk'] = info['dynamic_risk']
    F['T_info_val'] = info['T_info_val']

    # ── Physics at feat_idx ──
    F['geodesic_accel'] = float(ad.geodesic_accel[fi])
    F['friction'] = float(ad.friction[fi])
    F['gauge_force'] = float(ad.gauge_force[fi])
    F['delta_gap'] = float(ad.delta_gap[fi])

    Hmax = max(np.log2(max(int(ad.dynamic_k), 2)), 1e-9)
    F['H_over_Hmax'] = float(ad.H[fi]) / Hmax
    F['dH'] = float(ad.dH[fi])
    F['dF'] = float(ad.dF[fi])

    V_mean = float(np.mean(ad.V)) + 1e-9
    F['V_norm'] = float(ad.V[fi]) / V_mean
    F['E_therm'] = float(ad.E_therm[fi])
    F['T_info'] = float(ad.T_info[fi])
    F['C'] = float(ad.C[fi])

    # ── Geometry design ──
    sl_dist = abs(price - sl)
    tp_dist = abs(tp1 - price)
    F['sl_dist_frac'] = sl_dist / max(price, 1e-12)
    F['rr_design'] = tp_dist / max(sl_dist, 1e-12)

    sigma_frac = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
    if not np.isfinite(sigma_frac) or sigma_frac <= 1e-6:
        sigma_frac = 0.01
    sigma_price = sigma_frac * price

    fd_kappa = float(getattr(bot.CFG, 'FRICTION_DIP_KAPPA', 4.0))
    friction_drag = fd_kappa * sigma_price

    F['friction_drag_over_sl'] = friction_drag / max(sl_dist, 1e-12)
    F['sl_sigma'] = sl_dist / max(sigma_price, 1e-12)

    # ── Context ──
    if 0 <= ci < len(ad.ema200):
        ema = float(ad.ema200[ci])
        lookback = 50
        if ci - lookback >= 0:
            slope = (float(ad.ema200[ci]) - float(ad.ema200[ci - lookback])) / lookback
            F['ema_slope_against'] = 1.0 if (
                (action == 'BUY' and slope < 0) or
                (action == 'SELL' and slope > 0)
            ) else 0.0
        else:
            F['ema_slope_against'] = 0.0
        F['dist_from_ema_norm'] = (price - ema) / max(sigma_price, 1e-12)
    else:
        F['ema_slope_against'] = 0.0
        F['dist_from_ema_norm'] = 0.0

    if 0 <= ci < len(ad.atr14) and ci >= 100:
        window = ad.atr14[ci - 100:ci + 1]
        F['atr_percentile'] = float(np.mean(window <= ad.atr14[ci]))
    else:
        F['atr_percentile'] = 0.5

    # ── Time-of-day ──
    ts = trade.entry_time
    F['hour_sin'] = float(np.sin(2 * np.pi * ts.hour / 24))
    F['hour_cos'] = float(np.cos(2 * np.pi * ts.hour / 24))
    F['dow_sin'] = float(np.sin(2 * np.pi * ts.dayofweek / 7))
    F['dow_cos'] = float(np.cos(2 * np.pi * ts.dayofweek / 7))
    F['is_weekend'] = 1.0 if ts.dayofweek >= 5 else 0.0

    return F


def compute_dynamic_features(trades_with_features):
    """
    Compute recent-history features sequentially.
    Guarantees no look-ahead: history is appended AFTER features are computed.
    """
    by_symbol = defaultdict(list)
    all_history = []

    for tw in trades_with_features:
        t = tw['entry_time']
        sym = tw['symbol']
        is_loss = tw['is_loss']

        # recent_trades_24h
        cutoff = t - pd.Timedelta(hours=24)
        n_24h = sum(1 for (tt, _) in all_history if tt >= cutoff)
        tw['features']['recent_trades_24h'] = float(n_24h)

        # recent_losses_symbol_5
        sym_hist = by_symbol[sym]
        last5 = sym_hist[-5:]
        n_loss_sym = sum(1 for (_, l) in last5 if l)
        tw['features']['recent_losses_symbol_5'] = float(n_loss_sym)

        # recent_losses_portfolio_10
        last10 = all_history[-10:]
        n_loss_port = sum(1 for (_, l) in last10 if l)
        tw['features']['recent_losses_portfolio_10'] = float(n_loss_port)

        # Append AFTER computing (no leak)
        by_symbol[sym].append((t, is_loss))
        all_history.append((t, is_loss))


# ════════════════════════════════════════════════════════════════
# 6. Walk-forward logistic regression
# ════════════════════════════════════════════════════════════════

def walk_forward_logistic(X, y, min_train=50, C=1.0):
    """Return (p_loss_oos, coefs_history)."""
    n = len(X)
    p_preds = np.full(n, np.nan)
    coefs = []

    if not HAS_SKLEARN or n < min_train + 5:
        return p_preds, coefs

    for i in range(min_train, n):
        X_tr = X[:i]
        y_tr = y[:i]

        # NaN handling: replace with training-column medians
        col_med = np.nanmedian(X_tr, axis=0)
        col_med = np.where(np.isfinite(col_med), col_med, 0.0)
        X_tr_c = np.where(np.isnan(X_tr), col_med, X_tr)
        x_i = X[i:i+1]
        x_i_c = np.where(np.isnan(x_i), col_med, x_i)

        if len(np.unique(y_tr)) < 2:
            continue

        try:
            scaler = StandardScaler()
            X_tr_s = scaler.fit_transform(X_tr_c)
            x_i_s = scaler.transform(x_i_c)
        except Exception:
            continue

        try:
            model = LogisticRegression(
                penalty='l1', solver='liblinear',
                C=C, max_iter=5000, random_state=42,
                class_weight='balanced',
            )
            model.fit(X_tr_s, y_tr)
            p = float(model.predict_proba(x_i_s)[0, 1])
            p_preds[i] = p
            coefs.append(model.coef_.flatten().copy())
        except Exception:
            continue

    return p_preds, coefs


# ════════════════════════════════════════════════════════════════
# 7. Analysis: univariate + threshold
# ════════════════════════════════════════════════════════════════

def univariate_analysis(X, y, names):
    """For each feature, compute AUC and Mann-Whitney p-value."""
    results = []
    for j, name in enumerate(names):
        x_j = X[:, j].astype(float)
        valid = np.isfinite(x_j)
        if valid.sum() < 20:
            continue
        x = x_j[valid]
        yv = y[valid]
        if len(np.unique(yv)) < 2:
            continue

        # AUC (adjust direction)
        try:
            auc = roc_auc_score(yv, x)
        except Exception:
            continue
        direction = 1
        if auc < 0.5:
            auc = 1.0 - auc
            direction = -1

        # Mann-Whitney
        p_val = 1.0
        if HAS_SCIPY:
            try:
                _, p_val = mannwhitneyu(x[yv == 0], x[yv == 1],
                                         alternative='two-sided')
            except Exception:
                p_val = 1.0

        results.append({
            'feature': name,
            'auc': float(auc),
            'direction': int(direction),
            'p_value': float(p_val),
            'mean_win': float(np.mean(x[yv == 0])),
            'mean_loss': float(np.mean(x[yv == 1])),
        })
    return sorted(results, key=lambda r: -r['auc'])


def threshold_analysis(trades, p_preds, thresholds):
    """For each threshold, compute filter metrics."""
    n = len(trades)
    lrs = np.array([tw['log_return'] for tw in trades], dtype=float)
    is_loss = np.array([tw['is_loss'] for tw in trades], dtype=bool)

    valid = np.isfinite(p_preds)
    if valid.sum() < 20:
        return []

    lrs_v = lrs[valid]
    is_loss_v = is_loss[valid]
    p_v = p_preds[valid]

    n_loss_total = int(is_loss_v.sum())
    n_win_total = int((~is_loss_v).sum())
    baseline_E = float(np.mean(lrs_v))

    rows = []
    for tau in thresholds:
        keep = p_v < tau
        n_kept = int(keep.sum())
        if n_kept < 5:
            continue
        is_loss_k = is_loss_v[keep]
        lrs_k = lrs_v[keep]
        n_loss_kept = int(is_loss_k.sum())
        n_win_kept = n_kept - n_loss_kept

        R_loss = (n_loss_total - n_loss_kept) / max(n_loss_total, 1)
        R_win = (n_win_total - n_win_kept) / max(n_win_total, 1)

        E_kept = float(np.mean(lrs_k))
        dE = E_kept - baseline_E
        std_k = float(np.std(lrs_k, ddof=1)) if len(lrs_k) > 1 else 0.0
        sharpe = E_kept / max(std_k, 1e-9) * np.sqrt(252)

        rows.append({
            'threshold': float(tau),
            'n_kept': n_kept,
            'n_win_kept': n_win_kept,
            'n_loss_kept': n_loss_kept,
            'n_win_skipped': n_win_total - n_win_kept,
            'n_loss_skipped': n_loss_total - n_loss_kept,
            'R_loss': R_loss,
            'R_win': R_win,
            'efficiency': R_loss / max(R_win, 1e-6),
            'E_kept': E_kept,
            'dE': dE,
            'sharpe_kept': sharpe,
        })
    return rows


# ════════════════════════════════════════════════════════════════
# 8. Report writer
# ════════════════════════════════════════════════════════════════

def write_report(txt_path, json_path, bot_file, args,
                 trades, sigs, univ, threshold_rows,
                 p_preds, coefs, feat_names,
                 baseline_metrics):
    lines = []
    def W(s=""):
        lines.append(s)

    def H(char='=', n=78):
        W(char * n)

    H()
    W("TRADE FILTER DIAGNOSTIC REPORT")
    H()
    W(f"Bot: {bot_file}")
    W(f"Timeframe: {args.timeframe}")
    W(f"History: {args.history_days} days")
    W(f"No-fixed-price: {args.no_fixed_price}")
    W(f"N assets: {args.nassets}")
    W(f"Min-train: {args.min_train}")
    W(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    H()
    W()

    # ── Overview ──
    W("=" * 78)
    W("SECTION 1: OVERVIEW")
    W("=" * 78)
    W(f"Total signals built: {len(sigs)}")
    W(f"Total trades executed: {len(trades)}")
    W(f"Baseline E[ln(1+fR)]: {baseline_metrics['E']:+.6f}")
    W(f"Baseline win rate: {baseline_metrics['WR']*100:.2f}%")
    W(f"Baseline profit factor: {baseline_metrics['PF']:.3f}")
    W(f"Baseline Sharpe: {baseline_metrics['Sharpe']:.3f}")
    W(f"Baseline MaxDD: {baseline_metrics['MaxDD']:.2f}%")
    W(f"Baseline total return: {baseline_metrics['TotalRet']:+.2f}%")
    W()
    W(f"Trades classified as LOSS: {baseline_metrics['n_loss']} "
      f"({baseline_metrics['n_loss']/max(len(trades),1)*100:.1f}%)")
    W(f"Trades classified as WIN:  {baseline_metrics['n_win']} "
      f"({baseline_metrics['n_win']/max(len(trades),1)*100:.1f}%)")
    W()

    # ── Exit distribution ──
    W("--- Exit reason distribution ---")
    ec = defaultdict(int)
    for t in trades:
        reason_str = str(t.get('exit_reason', 'unknown'))
        r = reason_str.split('(')[0].split('=')[0].strip()
        if not r:
            r = 'unknown'
        ec[r] += 1
    for r, cnt in sorted(ec.items(), key=lambda x: -x[1]):
        W(f"  {r:35s}: {cnt:5d}  ({cnt/max(len(trades),1)*100:5.1f}%)")
    W()

    # ── Univariate ──
    W("=" * 78)
    W("SECTION 2: UNIVARIATE FEATURE DISCRIMINATION")
    W("=" * 78)
    W("AUC > 0.5 means the feature has predictive value for LOSING trades.")
    W("Sorted by AUC descending. Only shows top features.")
    W()
    W(f"{'Rank':>4} | {'Feature':<28} | {'AUC':>6} | {'p_value':>10} | "
      f"{'mean_win':>12} | {'mean_loss':>12} | {'Direction':>9}")
    W("-" * 100)
    for i, r in enumerate(univ[:25]):
        dir_ = "higher=win" if r['direction'] == 1 else "lower=win"
        W(f"{i+1:>4} | {r['feature']:<28} | {r['auc']:>6.3f} | "
          f"{r['p_value']:>10.2e} | {r['mean_win']:>12.5f} | "
          f"{r['mean_loss']:>12.5f} | {dir_:>9}")
    W()

    # ── Walk-forward LR ──
    W("=" * 78)
    W("SECTION 3: WALK-FORWARD LOGISTIC REGRESSION")
    W("=" * 78)

    valid = np.isfinite(p_preds)
    n_valid = int(valid.sum())
    if n_valid < 20:
        W("Not enough out-of-sample predictions. Skipping.")
    else:
        y_v = np.array([tw['is_loss'] for tw in trades])[valid]
        p_v = p_preds[valid]

        try:
            auc_oos = roc_auc_score(y_v, p_v)
        except Exception:
            auc_oos = float('nan')

        W(f"Number of OOS predictions: {n_valid}")
        W(f"OOS AUC of P(loss): {auc_oos:.4f}")
        W("  (0.5=random, 0.6=weak, 0.7=moderate, 0.8=strong)")
        W()

        # Coefficient analysis
        if coefs:
            coef_mat = np.array(coefs)
            mean_coef = np.mean(coef_mat, axis=0)
            std_coef = np.std(coef_mat, axis=0)
            sign_stability = np.mean(
                np.sign(coef_mat) == np.sign(mean_coef), axis=0
            )
            # Top features by |mean| (only those with stable sign)
            order = np.argsort(-np.abs(mean_coef))
            W("Top 15 features by average |coefficient| (sign stability > 0.7):")
            W()
            W(f"{'Rank':>4} | {'Feature':<28} | {'mean_coef':>10} | "
              f"{'std_coef':>10} | {'sign_stab':>10} | {'effect':>20}")
            W("-" * 100)
            for rank, j in enumerate(order[:15]):
                if j >= len(feat_names):
                    continue
                eff = "increases loss" if mean_coef[j] > 0 else "decreases loss"
                W(f"{rank+1:>4} | {feat_names[j]:<28} | "
                  f"{mean_coef[j]:>+10.4f} | {std_coef[j]:>10.4f} | "
                  f"{sign_stability[j]:>10.2f} | {eff:>20}")
            W()

    # ── Threshold trade-off ──
    W("=" * 78)
    W("SECTION 4: THRESHOLD TRADE-OFF CURVE")
    W("=" * 78)
    W("Threshold τ: keep trade if P(loss) < τ")
    W()
    W(f"{'τ':>5} | {'n_kept':>7} | {'n_win':>6} | {'n_loss':>6} | "
      f"{'R_loss':>7} | {'R_win':>7} | {'eff':>5} | {'E_kept':>10} | "
      f"{'dE':>10} | {'Sharpe':>7}")
    W("-" * 105)
    for row in threshold_rows:
        W(f"{row['threshold']:>5.2f} | {row['n_kept']:>7d} | "
          f"{row['n_win_kept']:>6d} | {row['n_loss_kept']:>6d} | "
          f"{row['R_loss']*100:>6.1f}% | {row['R_win']*100:>6.1f}% | "
          f"{row['efficiency']:>5.2f} | {row['E_kept']:>+10.6f} | "
          f"{row['dE']:>+10.6f} | {row['sharpe_kept']:>7.2f}")
    W()

    # Best row
    if threshold_rows:
        # Score = dE weighted by n_kept retention
        def score(r):
            retention = r['n_kept'] / max(len(trades), 1)
            return r['dE'] * (0.5 + 0.5 * retention)
        best = max(threshold_rows, key=score)
        W("★ Best threshold by (dE × retention):")
        W(f"  τ* = {best['threshold']:.2f}")
        W(f"  Trades kept: {best['n_kept']} / {len(trades)}")
        W(f"  Losses rejected: {best['R_loss']*100:.1f}%")
        W(f"  Winners lost:   {best['R_win']*100:.1f}%")
        W(f"  E[ln] before: {baseline_metrics['E']:+.6f}")
        W(f"  E[ln] after:  {best['E_kept']:+.6f}")
        W(f"  ΔE[ln]:       {best['dE']:+.6f}")
        W(f"  Sharpe after: {best['sharpe_kept']:.3f}")
        W()

    # ── Recommendations ──
    W("=" * 78)
    W("SECTION 5: RECOMMENDATIONS")
    W("=" * 78)
    if univ:
        top5 = univ[:5]
        W("Top 5 features (by AUC):")
        for i, r in enumerate(top5):
            W(f"  {i+1}. {r['feature']:28s}  AUC={r['auc']:.3f}  "
              f"p={r['p_value']:.2e}  direction: {r['direction']}")
    W()
    W("Simple rules (single-feature) that could help:")
    W("  → See Section 2 for full details.")
    W()
    W("Next steps:")
    W("  1. Send the full report file to the assistant.")
    W("  2. The assistant will propose a specific filter configuration.")
    W()

    H()
    W("END OF REPORT")
    H()

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"\n[Report] Saved to: {txt_path}")

    # Also save JSON with detailed data
    try:
        json_data = {
            'baseline': {k: (float(v) if isinstance(v, (int, float, np.number)) else v)
                          for k, v in baseline_metrics.items()},
            'univariate': univ,
            'thresholds': threshold_rows,
            'feature_names': feat_names,
            'n_trades': len(trades),
            'n_signals': len(sigs),
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False, default=str)
        print(f"[Report] JSON saved to: {json_path}")
    except Exception as e:
        print(f"[WARN] JSON save failed: {e}")


# ════════════════════════════════════════════════════════════════
# 9. Main
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Trade Filter Diagnostic")
    p.add_argument("--bot", type=str, default=None)
    p.add_argument("--timeframe", type=str, default="4h")
    p.add_argument("--history-days", type=int, default=730)
    p.add_argument("--nassets", type=int, default=15)
    p.add_argument("--no-fixed-price", action="store_true", default=True)
    p.add_argument("--min-train", type=int, default=50)
    p.add_argument("--l1-c", type=float, default=1.0)
    p.add_argument("--output", type=str,
                   default="trade_filter_diagnostic_report.txt")
    p.add_argument("--output-json", type=str,
                   default="trade_filter_diagnostic_data.json")
    p.add_argument("--use-cache", action="store_true", default=False)
    args = p.parse_args()

    # 1. Detect bot
    bot_file = detect_bot_file(args.bot)
    print(f"[Main] Bot file: {bot_file}")

    # 2. Import
    bot = import_bot(bot_file)
    try:
        bot.log.setLevel("ERROR")   # silence bot's internal logs
    except Exception:
        pass

    # 3. Setup CFG
    setup_bot_cfg(
        bot,
        timeframe=args.timeframe,
        history_days=args.history_days,
        n_assets=args.nassets,
        no_fixed_price=args.no_fixed_price,
        use_cache=args.use_cache,
    )

    # 4. Pipeline
    assets, sigs, corr = run_full_pipeline(bot)
    if not sigs:
        print("[ERROR] No signals generated. Aborting.")
        return

    # 5. Backtest
    trades, equity, sig_info = run_backtest_and_capture(bot, assets, sigs, corr)
    if not trades:
        print("[ERROR] No trades. Aborting.")
        return

    # 6. Extract features for each trade
    print("[Features] Extracting features...")
    trades_with_features = []
    n_missing = 0
    for trade in trades:
        key = (trade.symbol, trade.entry_time)
        info = sig_info.get(key)
        if info is None:
            n_missing += 1
            continue
        F = extract_static_features(bot, trade, info, assets)
        if F is None:
            n_missing += 1
            continue

        # Compute dynamic placeholder values (will be filled later)
        F['recent_trades_24h'] = 0.0
        F['recent_losses_symbol_5'] = 0.0
        F['recent_losses_portfolio_10'] = 0.0

        trades_with_features.append({
            'symbol': trade.symbol,
            'entry_time': trade.entry_time,
            'is_loss': bool(trade.net_pnl < 0),
            'log_return': float(trade.log_return),
            'net_pnl': float(trade.net_pnl),
            'exit_reason': str(getattr(trade, 'exit_reason', 'unknown')),
            'features': F,
        })

    print(f"[Features] Extracted for {len(trades_with_features)} trades "
          f"(missing {n_missing})")

    # Sort by entry_time (chronological)
    trades_with_features.sort(key=lambda x: x['entry_time'])

    # 7. Compute dynamic features sequentially
    compute_dynamic_features(trades_with_features)

    # 8. Build feature matrix
    X = np.zeros((len(trades_with_features), len(FEATURE_NAMES)))
    y = np.zeros(len(trades_with_features), dtype=int)
    for i, tw in enumerate(trades_with_features):
        for j, name in enumerate(FEATURE_NAMES):
            X[i, j] = float(tw['features'].get(name, 0.0))
        y[i] = 1 if tw['is_loss'] else 0

    print(f"[Features] Matrix: {X.shape}")

    # 9. Baseline metrics
    lrs = np.array([tw['log_return'] for tw in trades_with_features])
    n_loss = int(y.sum())
    n_win = int((1 - y).sum())
    wins = lrs[y == 0]
    losses = lrs[y == 1]
    mean_lr = float(np.mean(lrs))
    std_lr = float(np.std(lrs, ddof=1)) if len(lrs) > 1 else 0.0

    # Equity curve (from trades in entry order)
    init_cap = bot.CFG.INITIAL_CAPITAL
    cap = init_cap
    eq = [cap]
    for tw in trades_with_features:
        # Approximate: multiply by exp(log_return)
        cap *= np.exp(tw['log_return'])
        eq.append(cap)
    eq = np.array(eq)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.maximum(peak, 1e-12)
    max_dd = float(np.max(dd) * 100)

    baseline_metrics = {
        'E': mean_lr,
        'WR': float(n_win / max(n_loss + n_win, 1)),
        'PF': float(np.sum(wins) / abs(np.sum(losses))) if len(losses) > 0
              and np.sum(losses) != 0 else float('inf'),
        'Sharpe': mean_lr / max(std_lr, 1e-9) * np.sqrt(252),
        'MaxDD': max_dd,
        'TotalRet': float((eq[-1] - init_cap) / init_cap * 100),
        'n_loss': n_loss,
        'n_win': n_win,
        'mean_win': float(np.mean(wins)) if len(wins) > 0 else 0.0,
        'mean_loss': float(np.mean(losses)) if len(losses) > 0 else 0.0,
    }

    print(f"[Baseline] E[ln]={baseline_metrics['E']:+.6f}  "
          f"WR={baseline_metrics['WR']*100:.1f}%  "
          f"PF={baseline_metrics['PF']:.3f}  "
          f"Sharpe={baseline_metrics['Sharpe']:.3f}")

    # 10. Univariate analysis
    print("[Analysis] Computing univariate statistics...")
    univ = univariate_analysis(X, y, FEATURE_NAMES)
    for r in univ[:10]:
        print(f"  {r['feature']:28s}  AUC={r['auc']:.3f}  "
              f"p={r['p_value']:.2e}")

    # 11. Walk-forward logistic
    print(f"[Analysis] Walk-forward logistic (min_train={args.min_train})...")
    p_preds, coefs = walk_forward_logistic(
        X, y, min_train=args.min_train, C=args.l1_c
    )
    n_valid = int(np.isfinite(p_preds).sum())
    print(f"[Analysis] Got {n_valid} out-of-sample predictions")

    if n_valid >= 20 and HAS_SKLEARN:
        try:
            y_v = y[np.isfinite(p_preds)]
            p_v = p_preds[np.isfinite(p_preds)]
            auc_oos = roc_auc_score(y_v, p_v)
            print(f"[Analysis] OOS AUC = {auc_oos:.4f}")
        except Exception:
            pass

    # 12. Threshold analysis
    print("[Analysis] Computing threshold trade-off...")
    thresholds = np.arange(0.05, 1.00, 0.05)
    threshold_rows = threshold_analysis(trades_with_features, p_preds,
                                         thresholds)
    for r in threshold_rows:
        print(f"  τ={r['threshold']:.2f}  n_kept={r['n_kept']:>3d}  "
              f"R_loss={r['R_loss']*100:>5.1f}%  "
              f"R_win={r['R_win']*100:>5.1f}%  "
              f"dE={r['dE']:+.6f}")

    # 13. Write report
    write_report(
        args.output, args.output_json,
        bot_file, args,
        trades_with_features, sigs,
        univ, threshold_rows,
        p_preds, coefs, FEATURE_NAMES,
        baseline_metrics,
    )

    print()
    print("=" * 60)
    print(f"Done. Send the file: {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
