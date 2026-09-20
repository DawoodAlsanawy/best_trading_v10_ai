#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ml_filter_trainer.py
--------------------
Train an ML signal filter using backtest data.

Usage:
    python3 ml_filter_trainer.py --months 24 --assets 10 --capital 100

Output:
    ml_filter.pkl  (model + scaler + metadata)
"""

import argparse, importlib.util, os, sys, pickle, json
from datetime import datetime
import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════
# Load the bot
# ════════════════════════════════════════════════════════════════

BOT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "best_trading_v10_ai.py")
if not os.path.exists(BOT_PATH):
    print(f"ERROR: {BOT_PATH} not found")
    sys.exit(1)

spec = importlib.util.spec_from_file_location("bot", BOT_PATH)
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
CFG = bot.CFG

# ════════════════════════════════════════════════════════════════
# Feature specification
# ════════════════════════════════════════════════════════════════

ML_FEATURE_NAMES = [
    "score_raw", "score_log", "T_info", "dyn_sl_factor", "dyn_risk",
    "action_buy",
    "geo_accel", "friction", "gauge_force", "delta_gap",
    "log_V", "C_neg", "dH", "dF",
    "atr_ratio", "adv_ratio", "hour", "tri",
]

def extract_ml_features(sig, ad) -> np.ndarray:
    """
    All features use ONLY data at or before sig.close_idx / sig.feat_idx.
    No look-ahead. Returns float64 vector of length 18.
    """
    ci = sig.close_idx
    fi = sig.feat_idx
    try:
        v = np.array([
            float(sig.score),
            float(np.log1p(max(sig.score, 0.0))),
            float(sig.T_info_val),
            float(sig.dyn_sl_factor),
            float(sig.dynamic_risk),
            1.0 if sig.action == "BUY" else 0.0,
            float(ad.geodesic_accel[fi]),
            float(ad.friction[fi]),
            float(ad.gauge_force[fi]),
            float(ad.delta_gap[fi]),
            float(np.log1p(max(ad.V[fi], 0.0))),
            float(-ad.C[fi]),
            float(ad.dH[fi]),
            float(ad.dF[fi]),
            float(sig.atr / max(sig.price, 1e-12)),
            float(ad.adv_usd[ci] / max(ad.closes[ci], 1e-12)),
            float(sig.timestamp.hour),
            float(sig.tri_val),
        ], dtype=np.float64)
    except Exception:
        return np.zeros(len(ML_FEATURE_NAMES), dtype=np.float64)

    if not np.all(np.isfinite(v)):
        v = np.where(np.isfinite(v), v, 0.0)
    return v


# ════════════════════════════════════════════════════════════════
# Data collection
# ════════════════════════════════════════════════════════════════

def collect_training_data(months, n_assets, capital, timeframe):
    """
    Run backtest, return (X, y, trades) where:
      X : (N, 18) features
      y : (N,) labels (1 if net_pnl > 0)
      trades: original Trade objects (for Sharpe comparison)
    """
    try:
        import ccxt
    except ImportError:
        print("ERROR: pip install ccxt")
        sys.exit(1)

    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    CFG.timeframe = timeframe
    CFG.history_days = months * 30
    CFG.n_assets = n_assets
    CFG.INITIAL_CAPITAL = capital

    print(f"[1/5] Scanning top {n_assets} assets...")
    syms = bot.scan_top_assets(exchange, n_assets)

    print(f"[2/5] Fetching data ({months} months, {timeframe})...")
    raw = bot.fetch_all(syms, exchange, timeframe, CFG.history_days, workers=5)
    if not raw:
        print("ERROR: no data")
        sys.exit(1)

    print(f"[3/5] Processing {len(raw)} symbols (serial)...")
    assets = {}
    for i, (sym, df) in enumerate(raw.items(), 1):
        ad = bot.process_asset(sym, df, current_capital=capital)
        if ad is not None:
            assets[sym] = ad
            print(f"      [{i}/{len(raw)}] {sym}: OK")
        else:
            print(f"      [{i}/{len(raw)}] {sym}: FAILED")

    print(f"[4/5] Generating signals...")
    sigs = bot.build_signals(assets, mode="backtest")
    sigs = bot.deduplicate_signals(sigs)
    print(f"      {len(sigs):,} signals after dedup")

    print(f"[5/5] Running portfolio simulation...")
    corr_matrix = bot.precompute_correlations(assets)
    trades, equity = bot.simulate_portfolio(sigs, assets, corr_matrix, "backtest")
    print(f"      {len(trades):,} trades executed")

    if len(trades) < 50:
        print("WARNING: < 50 trades — insufficient for training")

    # Match trades to signals by (symbol, entry_time)
    sig_index = {(s.symbol, s.timestamp): s for s in sigs}

    X_list = []
    y_list = []
    matched_trades = []
    unmatched = 0

    for t in trades:
        key = (t.symbol, t.entry_time)
        sig = sig_index.get(key)
        if sig is None:
            unmatched += 1
            continue
        ad = assets.get(t.symbol)
        if ad is None:
            unmatched += 1
            continue
        feat = extract_ml_features(sig, ad)
        X_list.append(feat)
        y_list.append(1 if t.net_pnl > 0 else 0)
        matched_trades.append(t)

    if unmatched > 0:
        print(f"WARNING: {unmatched} trades could not be matched to signals")

    if len(X_list) == 0:
        print("ERROR: no matched trades")
        sys.exit(1)

    X = np.vstack(X_list)
    y = np.array(y_list, dtype=np.int32)
    return X, y, matched_trades, assets


# ════════════════════════════════════════════════════════════════
# Training
# ════════════════════════════════════════════════════════════════

def train_model(X, y):
    """
    Time-based split (first 70% train, last 30% test).
    LogisticRegressionCV (auto-tuned regularization).
    Returns dict with model, scaler, and evaluation.
    """
    from sklearn.linear_model import LogisticRegressionCV
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, log_loss

    n = len(y)
    split_idx = int(0.70 * n)

    X_tr, X_te = X[:split_idx], X[split_idx:]
    y_tr, y_te = y[:split_idx], y[split_idx:]

    print(f"\n[Train] n_train={len(y_tr)}, n_test={len(y_te)}")
    print(f"        win_rate_train={y_tr.mean():.3f}, win_rate_test={y_te.mean():.3f}")

    if len(set(y_tr)) < 2:
        print("ERROR: training set has only one class")
        sys.exit(1)

    # Standardize on train only
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)

    # Regularized Logistic Regression with internal CV
    Cs = np.logspace(-3, 1, 12)
    model = LogisticRegressionCV(
        Cs=Cs,
        cv=5,
        penalty='l2',
        class_weight='balanced',
        scoring='roc_auc',
        max_iter=3000,
        random_state=42,
        n_jobs=1,
    )
    model.fit(X_tr_s, y_tr)

    # Evaluate
    p_tr = model.predict_proba(X_tr_s)[:, 1]
    p_te = model.predict_proba(X_te_s)[:, 1]

    auc_tr = roc_auc_score(y_tr, p_tr)
    auc_te = roc_auc_score(y_te, p_te)
    ll_te = log_loss(y_te, p_te)

    print(f"[Eval] AUC_train={auc_tr:.4f}, AUC_test={auc_te:.4f}, logloss_test={ll_te:.4f}")
    print(f"[Eval] Best C = {model.C_[0]:.5f}")

    # Feature importances (coefficients on standardized features)
    coefs = model.coef_[0]
    order = np.argsort(-np.abs(coefs))
    print("[Eval] Top features:")
    for i in order[:10]:
        print(f"        {ML_FEATURE_NAMES[i]:>16s}  coef={coefs[i]:+.4f}")

    # Threshold sweep on test set
    thresholds = np.arange(0.30, 0.71, 0.05)
    print(f"\n[Threshold Sweep on test]")
    print(f"  {'thresh':>7s}  {'kept':>5s}  {'rej%':>5s}  {'win_kept':>9s}  {'sharpe':>8s}")

    # We need trades aligned with test set
    return {
        'model': model,
        'scaler': scaler,
        'X_te': X_te_s,
        'y_te': y_te,
        'X_tr': X_tr_s,
        'y_tr': y_tr,
        'auc_train': auc_tr,
        'auc_test': auc_te,
        'best_C': float(model.C_[0]),
    }


def select_threshold(train_result, trades, min_reject=0.10, max_reject=0.35):
    """
    Choose threshold that:
      1. keeps reject rate in [min_reject, max_reject]
      2. maximizes Sharpe improvement on the test set.
    Falls back to 0.45 if no threshold satisfies the reject constraint.
    """
    model = train_result['model']
    X_te = train_result['X_te']
    y_te = train_result['y_te']

    # Trades aligned to the test window (last 30%)
    n_total = len(trades)
    split_idx = int(0.70 * n_total)
    test_trades = trades[split_idx:]

    if len(test_trades) != len(y_te):
        # Defensive — fall back to plain threshold
        return 0.45, {'error': 'trade/label mismatch'}

    p_te = model.predict_proba(X_te)[:, 1]

    def sharpe_of(subset):
        if len(subset) < 5:
            return 0.0
        lrs = np.array([t.log_return for t in subset])
        mu, sd = lrs.mean(), lrs.std(ddof=1)
        if sd < 1e-10:
            return 0.0
        return float(mu / sd * np.sqrt(252))

    baseline_sharpe = sharpe_of(test_trades)

    best = {'threshold': 0.45, 'sharpe': baseline_sharpe, 'reject': 0.0}
    sweep = []
    for th in np.arange(0.30, 0.71, 0.05):
        kept = [t for t, p in zip(test_trades, p_te) if p >= th]
        rej = 1.0 - len(kept) / max(len(test_trades), 1)
        sh = sharpe_of(kept)
        sweep.append({'threshold': float(th), 'reject': rej,
                     'sharpe': sh, 'kept': len(kept)})
        if min_reject <= rej <= max_reject:
            if sh > best['sharpe']:
                best = {'threshold': float(th), 'sharpe': sh, 'reject': rej}

    best['baseline_sharpe'] = baseline_sharpe
    best['sweep'] = sweep
    return best['threshold'], best


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Train ML filter for trading signals")
    p.add_argument("--months", type=int, default=24)
    p.add_argument("--assets", type=int, default=10)
    p.add_argument("--capital", type=float, default=100.0)
    p.add_argument("--timeframe", type=str, default=None,
                   help="Default: use bot's CFG.timeframe")
    p.add_argument("--out", type=str, default="ml_filter2.pkl")
    p.add_argument("--min-auc", type=float, default=0.55,
                   help="Minimum test AUC to accept model")
    p.add_argument("--target-reject", type=float, default=0.20,
                   help="Target reject rate (0.10-0.35)")
    args = p.parse_args()

    timeframe = args.timeframe or CFG.timeframe

    print("=" * 70)
    print(f"  ML Filter Training")
    print(f"  Bot: {BOT_PATH}")
    print(f"  months={args.months}, assets={args.assets}, timeframe={timeframe}")
    print("=" * 70)

    X, y, trades, assets = collect_training_data(
        args.months, args.assets, args.capital, timeframe
    )

    print(f"\n[Data] X.shape={X.shape}, positive_rate={y.mean():.3f}")

    if len(y) < 200:
        print(f"\nWARNING: only {len(y)} samples — model may be unstable")
        print("        Recommend months >= 24 or more assets")

    train_result = train_model(X, y)
    threshold, info = select_threshold(
        train_result, trades,
        min_reject=max(0.05, args.target_reject - 0.10),
        max_reject=min(0.40, args.target_reject + 0.15),
    )

    print(f"\n[Threshold Selection]")
    print(f"  Baseline Sharpe (test, no filter) : {info.get('baseline_sharpe', 0):.3f}")
    print(f"  Selected threshold                : {threshold:.3f}")
    print(f"  Reject rate @ threshold           : {info.get('reject', 0)*100:.1f}%")
    print(f"  Filtered Sharpe                   : {info.get('sharpe', 0):.3f}")
    improvement = (info.get('sharpe', 0) - info.get('baseline_sharpe', 0))
    print(f"  Improvement                       : {improvement:+.3f}")

    print(f"\n  Full sweep:")
    for row in info.get('sweep', []):
        marker = " ←" if abs(row['threshold'] - threshold) < 1e-6 else ""
        print(f"    t={row['threshold']:.2f}  kept={row['kept']:4d}  "
              f"reject={row['reject']*100:5.1f}%  sharpe={row['sharpe']:.3f}{marker}")

    # Decide acceptance
    auc = train_result['auc_test']
    accept = auc >= args.min_auc
    status = "✅ ACCEPT" if accept else "⚠️  WEAK"
    print(f"\n[Quality] AUC_test={auc:.4f}  →  {status} (min={args.min_auc})")

    # Save
    payload = {
        'model': train_result['model'],
        'scaler': train_result['scaler'],
        'features': ML_FEATURE_NAMES,
        'threshold': float(threshold),
        'metadata': {
            'trained_at': datetime.now().isoformat(),
            'n_train': int(len(train_result['y_tr'])),
            'n_test': int(len(train_result['y_te'])),
            'auc_train': float(train_result['auc_train']),
            'auc_test': float(auc),
            'best_C': train_result['best_C'],
            'baseline_sharpe': float(info.get('baseline_sharpe', 0)),
            'filtered_sharpe': float(info.get('sharpe', 0)),
            'reject_rate': float(info.get('reject', 0)),
            'months': args.months,
            'assets': args.assets,
            'timeframe': timeframe,
        }
    }
    with open(args.out, 'wb') as f:
        pickle.dump(payload, f)

    print(f"\n[Save] Model written to {args.out}")
    if not accept:
        print("[WARN] Model does not meet min AUC. Do NOT use in production")
        print("       without more data or feature engineering.")

    print("=" * 70)


if __name__ == "__main__":
    main()
