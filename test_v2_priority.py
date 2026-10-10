#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_v2_priority.py — اختبار Priority Simulation vs Legacy.

يقارن نفس الإشارات تحت محاكاة تقليدية vs محاكاة بأولوية.
"""

import os, sys, time, json, argparse
for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
          'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[v] = '1'
sys.path.insert(0, '.')

import numpy as np
import pandas as pd
import importlib

# نحتاج استخدام v2 كـ module، ليس كـ main
# نستخدم importlib لتحميل الملف كنص
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # ← السطر الجديد
    spec.loader.exec_module(mod)
    return mod

V1_PATH = 'trading_rnd_sell_only_v1_baseline.py'
V2_PATH = 'trading_rnd_v2_priority.py'

if not os.path.exists(V1_PATH):
    print(f"ERR: {V1_PATH} not found")
    sys.exit(1)
if not os.path.exists(V2_PATH):
    print(f"ERR: {V2_PATH} not found")
    sys.exit(1)

V1 = load_module('v1_module', V1_PATH)
V2 = load_module('v2_module', V2_PATH)


def base_config(mod, end_date, tf, n_assets, sell_only=True):
    CFG = mod.CFG
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
    CFG.SELL_SL_WIDEN_MULT = 1.0
    CFG.MAX_CONCURRENT_ASSETS = 3
    CFG.PORTFOLIO_HEAT_MAX = 0.10
    CFG.MIN_RISK_PER_TRADE = 0.005
    CFG.REENTRY_COOLDOWN_ENABLED = True
    CFG.REENTRY_COOLDOWN_BARS = 3

    import ccxt
    ex = ccxt.binance()
    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = \
        mod.compute_tf_scale(ex, tf)
    _tf_h = max(float(CFG.TF_HOURS), 1e-6)
    CFG.N = max(24, int(np.ceil(24.0 / _tf_h)))
    CFG.W = max(20, int(np.ceil(20.0 / _tf_h)))
    CFG.L = max(10, int(np.ceil(10.0 / _tf_h)))
    CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))


def load_window(mod, end_date, n_assets, tf):
    import ccxt
    ex = ccxt.binance({'enableRateLimit': True,
                       'options': {'defaultType': 'future'}})
    CFG = mod.CFG
    syms = mod.scan_top_assets(ex, n_assets)
    raw, raw_sub = mod.fetch_all_with_subbars(
        syms, ex, tf, CFG.history_days, workers=5)
    assets = {}
    for sym, df in raw.items():
        ad = mod._load_asset_cache(sym, tf, df, CFG)
        if ad is None:
            ad = mod.process_asset(
                sym, df,
                current_capital=CFG.INITIAL_CAPITAL,
                sub_df=(raw_sub.get(sym) if raw_sub else None))
            if ad is not None:
                mod._save_asset_cache(sym, tf, df, ad, CFG)
        if ad is not None:
            assets[sym] = ad
    return assets


def run_one(mod, assets, corr, pending_mode=False, max_pending=5):
    CFG = mod.CFG
    if hasattr(CFG, 'SIG_PENDING_MODE'):
        CFG.SIG_PENDING_MODE = pending_mode
        CFG.SIG_MAX_PENDING_BARS = max_pending

    sigs = mod.build_signals(assets, mode="backtest")
    sigs = mod.deduplicate_signals(sigs)
    trades, equity = mod.simulate_portfolio(sigs, assets, corr, "backtest")
    m = mod.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    return {
        "sharpe": float(m.get("sharpe_ratio", 0)),
        "final": float(m.get("final_capital", 0)),
        "n": int(m.get("n_trades", 0)),
        "wr": float(m.get("win_rate", 0)),
        "pf": float(m.get("profit_factor", 0)),
    }


WINDOWS = {"2024": "2024-12-31", "2025": "2025-12-31",
           "2026": "2026-10-01"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h')
    ap.add_argument('--nassets', type=int, default=100)
    ap.add_argument('--max-pending', type=int, default=5)
    args = ap.parse_args()

    print("═" * 80)
    print(f"  V1 vs V2 priority simulation — tf={args.tf}")
    print("═" * 80)

    results = {'v1': {}, 'v2': {}}

    for label, end in WINDOWS.items():
        print(f"\n{'─' * 80}")
        print(f"  {label} (end={end})")
        print(f"{'─' * 80}")

        # V1 setup
        base_config(V1, end, args.tf, args.nassets, sell_only=True)
        assets = load_window(V1, end, args.nassets, args.tf)
        if not assets:
            continue
        corr = V1.precompute_correlations(assets)
        print(f"  V1: {len(assets)} assets")

        r1 = run_one(V1, assets, corr, pending_mode=False)
        results['v1'][label] = r1
        print(f"    V1 (legacy):   Sharpe={r1['sharpe']:>8.3f}  "
              f"n={r1['n']:>4}  WR={r1['wr']*100:>5.1f}%  "
              f"Final=${r1['final']:>7.2f}")

        # V2 setup — same signals, only simulate differs
        base_config(V2, end, args.tf, args.nassets, sell_only=True)
        r2 = run_one(V2, assets, corr,
                     pending_mode=True,
                     max_pending=args.max_pending)
        results['v2'][label] = r2
        print(f"    V2 (priority): Sharpe={r2['sharpe']:>8.3f}  "
              f"n={r2['n']:>4}  WR={r2['wr']*100:>5.1f}%  "
              f"Final=${r2['final']:>7.2f}")

    print("\n\n" + "═" * 80)
    print("  FINAL COMPARISON")
    print("═" * 80)
    print()
    print(f"  {'Metric':<20} {'2024':>12} {'2025':>12} {'2026':>12}")
    print(f"  {'─'*20} {'─'*12} {'─'*12} {'─'*12}")
    for key in ['sharpe', 'n', 'wr', 'final']:
        v1_vals = [results['v1'].get(y, {}).get(key, 0) for y in WINDOWS]
        v2_vals = [results['v2'].get(y, {}).get(key, 0) for y in WINDOWS]

        if key == 'sharpe':
            print(f"  V1 Sharpe           {v1_vals[0]:>12.3f} "
                  f"{v1_vals[1]:>12.3f} {v1_vals[2]:>12.3f}")
            print(f"  V2 Sharpe           {v2_vals[0]:>12.3f} "
                  f"{v2_vals[1]:>12.3f} {v2_vals[2]:>12.3f}")
        elif key == 'n':
            print(f"  V1 Trades           {v1_vals[0]:>12} "
                  f"{v1_vals[1]:>12} {v1_vals[2]:>12}")
            print(f"  V2 Trades           {v2_vals[0]:>12} "
                  f"{v2_vals[1]:>12} {v2_vals[2]:>12}")
        elif key == 'wr':
            print(f"  V1 WR%              {v1_vals[0]*100:>12.1f} "
                  f"{v1_vals[1]*100:>12.1f} {v1_vals[2]*100:>12.1f}")
            print(f"  V2 WR%              {v2_vals[0]*100:>12.1f} "
                  f"{v2_vals[1]*100:>12.1f} {v2_vals[2]*100:>12.1f}")
        elif key == 'final':
            print(f"  V1 Final $          {v1_vals[0]:>12.2f} "
                  f"{v1_vals[1]:>12.2f} {v1_vals[2]:>12.2f}")
            print(f"  V2 Final $          {v2_vals[0]:>12.2f} "
                  f"{v2_vals[1]:>12.2f} {v2_vals[2]:>12.2f}")

    with open("results/v1_vs_v2.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Saved: results/v1_vs_v2.json")


if __name__ == "__main__":
    main()
