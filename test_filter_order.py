#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_filter_order.py — اختبار ترتيب filter vs dedup.

يختبر 3 أوامر:
  A: filter → dedup (الحالي)
  B: dedup → filter
  C: filter → dedup → filter (مزدوج)

الهدف: هل التناوب يختفي عند ترتيب آخر؟
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


def filter_ratio(sigs, btc_ratio, thr):
    if btc_ratio is None:
        return sigs
    out = []
    for sig in sigs:
        if sig.action != "SELL":
            out.append(sig); continue
        try:
            r = float(btc_ratio.loc[sig.timestamp])
        except Exception:
            r = 1.0
        if not np.isfinite(r): r = 1.0
        if r > thr: continue
        out.append(sig)
    return out


def run_bt(filtered, assets, corr):
    trades, equity = engine.simulate_portfolio(
        filtered, assets, corr, "backtest")
    m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    return {
        "sharpe": float(m.get("sharpe_ratio", 0)),
        "final": float(m.get("final_capital", 0)),
        "n": int(m.get("n_trades", 0)),
        "wr": float(m.get("win_rate", 0)),
    }


WINDOWS = {"2024": "2024-12-31", "2025": "2025-12-31",
           "2026": "2026-10-01"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h')
    ap.add_argument('--nassets', type=int, default=100)
    ap.add_argument('--lb', type=int, default=90)
    args = ap.parse_args()

    print("═" * 88)
    print(f"  filter order test — tf={args.tf}, lb={args.lb}d")
    print("═" * 88)

    # للأداء، حددنا العتبات المثيرة للاهتمام
    THRESHOLDS = [0.88, 0.89, 0.90, 0.91, 0.92, 0.93, 0.94, 0.95, 0.96]

    per_window = {}
    for label, end in WINDOWS.items():
        base_config(end, args.tf, args.nassets)
        print(f"\n  Loading {label}...")
        t0 = time.time()
        assets = load_window(end, args.nassets, args.tf)
        if not assets: continue
        print(f"  → {len(assets)} assets in {time.time()-t0:.0f}s")
        raw_sigs = engine.build_signals(assets, mode="backtest")
        corr = engine.precompute_correlations(assets)
        lb_bars = int(args.lb * 24 / max(CFG.TF_HOURS, 1e-6))
        btc_ratio = build_btc_ratio(assets, lb_bars)
        per_window[label] = {
            'assets': assets, 'corr': corr,
            'raw_sigs': raw_sigs, 'ratio': btc_ratio,
        }
        print(f"  → {len(raw_sigs)} raw signals")

    # Order A: filter -> dedup
    print(f"\n{'─' * 88}")
    print(f"  ORDER A: filter → dedup")
    print(f"{'─' * 88}")
    print(f"  {'Thr':<6} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'N':>7}")
    for thr in THRESHOLDS:
        ss, ns = [], 0
        for label in WINDOWS:
            if label not in per_window: continue
            pw = per_window[label]
            filt = filter_ratio(pw['raw_sigs'], pw['ratio'], thr)
            filt = engine.deduplicate_signals(filt)
            r = run_bt(filt, pw['assets'], pw['corr'])
            ss.append(r['sharpe']); ns += r['n']
        if len(ss) == 3:
            print(f"  {thr:<6.2f} {ss[0]:>10.3f} {ss[1]:>10.3f} "
                  f"{ss[2]:>10.3f} {min(ss):>10.3f} {ns:>7}")

    # Order B: dedup -> filter
    print(f"\n{'─' * 88}")
    print(f"  ORDER B: dedup → filter")
    print(f"{'─' * 88}")
    print(f"  {'Thr':<6} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'N':>7}")
    for thr in THRESHOLDS:
        ss, ns = [], 0
        for label in WINDOWS:
            if label not in per_window: continue
            pw = per_window[label]
            deduped = engine.deduplicate_signals(pw['raw_sigs'])
            filt = filter_ratio(deduped, pw['ratio'], thr)
            r = run_bt(filt, pw['assets'], pw['corr'])
            ss.append(r['sharpe']); ns += r['n']
        if len(ss) == 3:
            print(f"  {thr:<6.2f} {ss[0]:>10.3f} {ss[1]:>10.3f} "
                  f"{ss[2]:>10.3f} {min(ss):>10.3f} {ns:>7}")

    # Order C: filter -> dedup -> filter (double)
    print(f"\n{'─' * 88}")
    print(f"  ORDER C: filter → dedup → filter (double check)")
    print(f"{'─' * 88}")
    print(f"  {'Thr':<6} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'N':>7}")
    for thr in THRESHOLDS:
        ss, ns = [], 0
        for label in WINDOWS:
            if label not in per_window: continue
            pw = per_window[label]
            filt = filter_ratio(pw['raw_sigs'], pw['ratio'], thr)
            filt = engine.deduplicate_signals(filt)
            filt = filter_ratio(filt, pw['ratio'], thr)
            r = run_bt(filt, pw['assets'], pw['corr'])
            ss.append(r['sharpe']); ns += r['n']
        if len(ss) == 3:
            print(f"  {thr:<6.2f} {ss[0]:>10.3f} {ss[1]:>10.3f} "
                  f"{ss[2]:>10.3f} {min(ss):>10.3f} {ns:>7}")


if __name__ == "__main__":
    main()
