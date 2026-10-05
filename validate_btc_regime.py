#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_btc_regime.py — تحقق صارم من حافة btc_ath filter.

المرحلة 1: threshold sweep (7 قيم)
المرحلة 2: TF robustness (4h vs 1h)
المرحلة 3: BUY+SELL combined
"""

import os, sys, time, json, argparse
for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
          'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[v] = '1'
sys.path.insert(0, '.')

import numpy as np
import pandas as pd
import trading_rnd_sell_only as engine
import __main__ as _pcmain
for _cn in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(engine, _cn):
        setattr(_pcmain, _cn, getattr(engine, _cn))

CFG = engine.CFG


def base_config(end_date, tf, n_assets, sell_only=True):
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf
    CFG.SELL_ENABLED = True
    CFG.BUY_DISABLED = bool(sell_only)
    CFG.GAUGE_FILTER_ENABLED = False
    CFG.SELL_GAUGE_PCT = 0.95
    CFG.SELL_MIN_SCORE = 3
    CFG.SELL_MIN_ZDEV = 1.5
    CFG.SELL_REQUIRE_EMA_DOWN = False
    CFG.SELL_REQUIRE_EMA_UP = False
    CFG.SELL_MAJOR_ONLY = False
    CFG.SELL_MIN_ATR_FRAC = 0.0
    CFG.SELL_SL_WIDEN_MULT = 1.0
    CFG.MAX_CONCURRENT_ASSETS = 20
    CFG.PORTFOLIO_HEAT_MAX = 0.60
    CFG.MIN_RISK_PER_TRADE = 0.003
    CFG.REENTRY_COOLDOWN_ENABLED = True
    CFG.REENTRY_COOLDOWN_BARS = 3

    import ccxt
    ex = ccxt.binance()
    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = \
        engine.compute_tf_scale(ex, tf)
    _tf_h = max(float(CFG.TF_HOURS), 1e-6)
    CFG.N = max(24, int(np.ceil(24.0 / _tf_h)))
    CFG.W = max(20, int(np.ceil(20.0 / _tf_h)))
    CFG.L = max(10, int(np.ceil(10.0 / _tf_h)))
    CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))


def load_window(end_date, n_assets, tf):
    import ccxt
    ex = ccxt.binance({'enableRateLimit': True,
                       'options': {'defaultType': 'future'}})
    syms = engine.scan_top_assets(ex, n_assets)
    raw, raw_sub = engine.fetch_all_with_subbars(
        syms, ex, tf, CFG.history_days, workers=5)
    assets = {}
    for sym, df in raw.items():
        ad = engine._load_asset_cache(sym, tf, df, CFG)
        if ad is None:
            ad = engine.process_asset(
                sym, df,
                current_capital=CFG.INITIAL_CAPITAL,
                sub_df=(raw_sub.get(sym) if raw_sub else None))
            if ad is not None:
                engine._save_asset_cache(sym, tf, df, ad, CFG)
        if ad is not None:
            assets[sym] = ad
    return assets


def build_btc_ratio(assets, lookback=90):
    btc = assets.get('BTC/USDT')
    if btc is None:
        return None
    s = pd.Series(btc.closes, index=btc.timestamps)
    rmax = s.rolling(lookback, min_periods=1).max()
    return s / rmax


def filter_by_ratio(sigs, btc_ratio, thr):
    if btc_ratio is None or thr is None:
        return sigs
    out = []
    for sig in sigs:
        if sig.action != "SELL":
            out.append(sig)
            continue
        try:
            r = float(btc_ratio.loc[sig.timestamp])
        except Exception:
            r = 1.0
        if not np.isfinite(r): r = 1.0
        if r > thr:
            continue
        out.append(sig)
    return out


def run_bt(filtered, assets, corr):
    sigs = engine.deduplicate_signals(filtered)
    trades, equity = engine.simulate_portfolio(
        sigs, assets, corr, "backtest")
    m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    return {
        "sharpe": float(m.get("sharpe_ratio", 0)),
        "final": float(m.get("final_capital", 0)),
        "n": int(m.get("n_trades", 0)),
        "n_sell": int(m.get("sell_count", 0)),
        "n_buy": int(m.get("buy_count", 0)),
        "wr": float(m.get("win_rate", 0)),
        "pf": float(m.get("profit_factor", 0)),
        "dd": float(m.get("max_drawdown_pct", 0)),
    }


WINDOWS = {"2024": "2024-12-31", "2025": "2025-12-31",
           "2026": "2026-10-01"}


def phase_1_thresholds(tf, n_assets):
    print("\n\n" + "═" * 92)
    print("  PHASE 1 — Threshold sweep (SELL-only, 4h)")
    print("═" * 92)

    THRESHOLDS = [0.85, 0.88, 0.90, 0.92, 0.94, 0.95, 0.97]
    results = {}

    for label, end in WINDOWS.items():
        base_config(end, tf, n_assets, sell_only=True)
        assets = load_window(end, n_assets, tf)
        if not assets: continue
        btc_ratio = build_btc_ratio(assets)
        raw_sigs = engine.build_signals(assets, mode="backtest")
        corr = engine.precompute_correlations(assets)
        row = {}
        for thr in THRESHOLDS:
            filtered = filter_by_ratio(raw_sigs, btc_ratio, thr)
            r = run_bt(filtered, assets, corr)
            row[thr] = r
        results[label] = row
        print(f"  {label}:")
        for thr in THRESHOLDS:
            r = row[thr]
            print(f"    thr={thr:.2f}  Sharpe={r['sharpe']:>7.3f}  "
                  f"n={r['n']:>4}  WR={r['wr']*100:>5.1f}%  "
                  f"Final=${r['final']:>7.2f}")

    print("\n  ── Summary across years ──")
    print(f"  {'Threshold':<10} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'Avg':>10} {'N':>7}")
    for thr in THRESHOLDS:
        ss = [results[y][thr]['sharpe'] for y in WINDOWS]
        ns = sum(results[y][thr]['n'] for y in WINDOWS)
        mn = min(ss); avg = float(np.mean(ss))
        flag = "✅" if mn >= 2.0 and ns >= 300 else ("🟡" if mn >= 1.0 else "❌")
        print(f"  {thr:<10.2f} {ss[0]:>10.3f} {ss[1]:>10.3f} "
              f"{ss[2]:>10.3f} {mn:>10.3f} {avg:>10.3f} {ns:>7} {flag}")

    return results


def phase_2_tf(n_assets):
    print("\n\n" + "═" * 92)
    print("  PHASE 2 — TF robustness (btc_ath=0.90)")
    print("═" * 92)

    results = {}
    for tf in ['4h', '1h']:
        results[tf] = {}
        print(f"\n  ▶ tf={tf}")
        for label, end in WINDOWS.items():
            base_config(end, tf, n_assets, sell_only=True)
            assets = load_window(end, n_assets, tf)
            if not assets: continue
            btc_ratio = build_btc_ratio(assets)
            raw_sigs = engine.build_signals(assets, mode="backtest")
            corr = engine.precompute_correlations(assets)
            filtered = filter_by_ratio(raw_sigs, btc_ratio, 0.90)
            r = run_bt(filtered, assets, corr)
            results[tf][label] = r
            print(f"    {label}: Sharpe={r['sharpe']:>7.3f}  n={r['n']:>4}  "
                  f"WR={r['wr']*100:>5.1f}%  Final=${r['final']:>7.2f}")

    print("\n  ── Summary ──")
    for tf in ['4h', '1h']:
        ss = [results[tf][y]['sharpe'] for y in WINDOWS]
        ns = sum(results[tf][y]['n'] for y in WINDOWS)
        print(f"  {tf}: min={min(ss):>7.3f}  avg={np.mean(ss):>7.3f}  "
              f"N={ns}")

    return results


def phase_3_combined(n_assets):
    print("\n\n" + "═" * 92)
    print("  PHASE 3 — BUY + SELL(btc_ath=0.90) combined")
    print("═" * 92)

    results = {}
    for label, end in WINDOWS.items():
        base_config(end, '4h', n_assets, sell_only=False)  # both enabled
        assets = load_window(end, n_assets, '4h')
        if not assets: continue
        btc_ratio = build_btc_ratio(assets)
        raw_sigs = engine.build_signals(assets, mode="backtest")
        corr = engine.precompute_correlations(assets)
        filtered = filter_by_ratio(raw_sigs, btc_ratio, 0.90)
        r = run_bt(filtered, assets, corr)
        results[label] = r
        print(f"    {label}: Sharpe={r['sharpe']:>7.3f}  "
              f"n={r['n']:>4} (B={r['n_buy']:>4},S={r['n_sell']:>4})  "
              f"WR={r['wr']*100:>5.1f}%  Final=${r['final']:>7.2f}")

    print("\n  ── Summary ──")
    ss = [results[y]['sharpe'] for y in WINDOWS]
    ns = sum(results[y]['n'] for y in WINDOWS)
    print(f"  combined: min={min(ss):>7.3f}  avg={np.mean(ss):>7.3f}  "
          f"N={ns}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nassets', type=int, default=100)
    ap.add_argument('--phase', choices=['all', '1', '2', '3'], default='all')
    args = ap.parse_args()

    print("═" * 92)
    print(f"  validate_btc_regime.py — n_assets={args.nassets}")
    print("═" * 92)

    p1 = p2 = p3 = None
    if args.phase in ('all', '1'):
        p1 = phase_1_thresholds('4h', args.nassets)
    if args.phase in ('all', '2'):
        p2 = phase_2_tf(args.nassets)
    if args.phase in ('all', '3'):
        p3 = phase_3_combined(args.nassets)

    # Save all
    out = {
        'phase1_thresholds': p1,
        'phase2_tf': p2,
        'phase3_combined': p3,
    }
    os.makedirs("results", exist_ok=True)
    with open("results/validate_btc_regime.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: results/validate_btc_regime.json")


if __name__ == "__main__":
    main()
