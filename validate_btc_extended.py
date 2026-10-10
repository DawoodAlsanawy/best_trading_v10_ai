#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_btc_extended.py — تحقق موسّع من حافة BTC regime filter.

اختبارات:
  1. Threshold refinement: 0.89, 0.90, 0.91, 0.92, 0.93, 0.94
  2. Lookback sweep: 60d, 90d, 120d
  3. TF: 4h, 1h
  4. Robustness: هل 0.92 ينجح عبر كل الأبعاد؟

قرار: هل 0.92 حافة حقيقية أم overfitting؟
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


def base_config(end_date, tf, n_assets):
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf
    CFG.SELL_ENABLED = True
    CFG.BUY_DISABLED = True
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


def build_btc_ratio(assets, lookback_bars):
    btc = assets.get('BTC/USDT')
    if btc is None:
        return None
    s = pd.Series(btc.closes, index=btc.timestamps)
    rmax = s.rolling(lookback_bars, min_periods=1).max()
    return s / rmax


def filter_by_ratio(sigs, btc_ratio, thr):
    if btc_ratio is None:
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
        "wr": float(m.get("win_rate", 0)),
        "pf": float(m.get("profit_factor", 0)),
    }


WINDOWS = {"2024": "2024-12-31", "2025": "2025-12-31",
           "2026": "2026-10-01"}


def evaluate_grid(tf, n_assets, lookbacks_days, thresholds):
    """
    يبني 4h AssetData مرة واحدة لكل نافذة، ثم يجرب كل lookback × threshold.
    """
    print(f"\n{'═' * 92}")
    print(f"  Grid: tf={tf}, lookbacks={lookbacks_days}, "
          f"thresholds={thresholds}")
    print(f"{'═' * 92}")

    # لكل نافذة، احسب raw_sigs مرة واحدة
    per_window = {}
    for label, end in WINDOWS.items():
        base_config(end, tf, n_assets)
        print(f"\n  Loading {label}...")
        t0 = time.time()
        assets = load_window(end, n_assets, tf)
        if not assets:
            continue
        print(f"  → {len(assets)} assets in {time.time()-t0:.0f}s")

        t0 = time.time()
        raw_sigs = engine.build_signals(assets, mode="backtest")
        corr = engine.precompute_correlations(assets)
        print(f"  → {len(raw_sigs)} signals in {time.time()-t0:.0f}s")

        # precompute ratios for all lookbacks
        ratios = {}
        for lbd in lookbacks_days:
            lb_bars = int(lbd * 24 / max(CFG.TF_HOURS, 1e-6))
            ratios[lbd] = build_btc_ratio(assets, lb_bars)

        per_window[label] = {
            'assets': assets, 'corr': corr,
            'raw_sigs': raw_sigs, 'ratios': ratios,
        }

    # Grid search
    results = {}
    for lbd in lookbacks_days:
        for thr in thresholds:
            key = f"lb{lbd}_thr{thr:.2f}"
            row = {}
            for label in WINDOWS:
                if label not in per_window:
                    continue
                pw = per_window[label]
                filtered = filter_by_ratio(
                    pw['raw_sigs'], pw['ratios'][lbd], thr)
                r = run_bt(filtered, pw['assets'], pw['corr'])
                row[label] = r
            results[key] = row

    # Print
    print(f"\n{'─' * 92}")
    print(f"  Grid Results")
    print(f"{'─' * 92}")
    print(f"  {'Config':<22} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'N':>7} {'Verdict':<15}")
    print(f"  {'─'*22} {'─'*10} {'─'*10} {'─'*10} {'─'*10} "
          f"{'─'*7} {'─'*15}")

    passers = []
    for key, row in results.items():
        ss = [row.get(y, {}).get('sharpe') for y in WINDOWS]
        ns = sum(row.get(y, {}).get('n', 0) for y in WINDOWS)
        if any(s is None for s in ss):
            continue
        mn = min(ss)
        if mn >= 1.5 and ns >= 300:
            v = "✅ STRONG"
            passers.append(key)
        elif mn >= 0.5 and ns >= 200:
            v = "🟡 OK"
        elif mn >= 0:
            v = "🟠 marginal"
        else:
            v = "❌ fail"
        print(f"  {key:<22} {ss[0]:>10.3f} {ss[1]:>10.3f} "
              f"{ss[2]:>10.3f} {mn:>10.3f} {ns:>7} {v:<15}")

    return results, passers


def analyze_robustness(results, lookbacks_days, thresholds):
    """هل الحافة على plateau أم spike؟"""
    print(f"\n{'═' * 92}")
    print(f"  Robustness Analysis")
    print(f"{'═' * 92}")

    # لكل lookback، احسب عدد الـ thresholds التي نجحت
    print(f"\n  عدد العتبات الناجحة (min Sharpe ≥ 0.5) لكل lookback:")
    for lbd in lookbacks_days:
        pass_count = 0
        total = 0
        for thr in thresholds:
            key = f"lb{lbd}_thr{thr:.2f}"
            if key not in results:
                continue
            total += 1
            row = results[key]
            ss = [row.get(y, {}).get('sharpe') for y in WINDOWS]
            if any(s is None for s in ss): continue
            if min(ss) >= 0.5:
                pass_count += 1
        pct = 100.0 * pass_count / max(total, 1)
        status = "✅ plateau" if pct >= 50 else (
            "🟡 partial" if pct >= 25 else "❌ spike")
        print(f"    lookback {lbd}d: {pass_count}/{total} "
              f"({pct:.0f}%)  {status}")

    # لكل threshold، احسب عبر كل lookbacks
    print(f"\n  عدد الـ lookbacks الناجحة لكل threshold:")
    for thr in thresholds:
        pass_count = 0
        total = 0
        for lbd in lookbacks_days:
            key = f"lb{lbd}_thr{thr:.2f}"
            if key not in results:
                continue
            total += 1
            row = results[key]
            ss = [row.get(y, {}).get('sharpe') for y in WINDOWS]
            if any(s is None for s in ss): continue
            if min(ss) >= 0.5:
                pass_count += 1
        pct = 100.0 * pass_count / max(total, 1)
        print(f"    thr {thr:.2f}: {pass_count}/{total} "
              f"({pct:.0f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nassets', type=int, default=100)
    args = ap.parse_args()

    # Grid parameters
    LOOKBACKS = [60, 90, 120]
    THRESHOLDS = [0.89, 0.90, 0.91, 0.92, 0.93, 0.94]

    results_4h, passers_4h = evaluate_grid(
        '4h', args.nassets, LOOKBACKS, THRESHOLDS)
    analyze_robustness(results_4h, LOOKBACKS, THRESHOLDS)

    print(f"\n  Total strong passers (4h): {len(passers_4h)}")
    for p in passers_4h[:10]:
        print(f"    ✅ {p}")

    # Save
    os.makedirs("results", exist_ok=True)
    with open("results/validate_btc_extended.json", "w") as f:
        json.dump({
            'grid_4h': results_4h,
            'passers_4h': passers_4h,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: results/validate_btc_extended.json")


if __name__ == "__main__":
    main()
