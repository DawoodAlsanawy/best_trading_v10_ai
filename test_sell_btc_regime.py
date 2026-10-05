#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sell_btc_regime.py — SELL مع كاشف BTC bull regime.

الفرضية: SELL يفشل في bull. نُعطّله عندما BTC قريب من ATH.

5 configs:
  - baseline (بدون فلتر)
  - btc_ath_5pct   (رفض إذا BTC > 95% من أعلى 90 يوم)
  - btc_ath_10pct  (رفض إذا BTC > 90% من أعلى 90 يوم)
  - btc_ath_5pct_30d (نافذة 30 يوم)
  - btc_ret_filter  (رفض إذا BTC عائد 30 يوم > +20%)
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
    CFG.SELL_REQUIRE_ORDER_EMERGING = False
    CFG.SELL_REQUIRE_DECELERATING = False
    CFG.SELL_REQUIRE_DOWNWARD_FORCE = False
    CFG.SELL_REQUIRE_LOW_FRICTION = False
    # fixed slots config (best from previous test)
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


def build_btc_regime_indicators(assets, lookback_bars=90):
    """
    Returns:
      - btc_ratio_to_high[ts] = btc_close / highest_close_in_last_N_bars
      - btc_30d_return[ts] = btc return over last 30 days
    """
    btc = assets.get('BTC/USDT')
    if btc is None:
        return None, None

    ts = btc.timestamps
    closes = btc.closes

    # rolling highest high over lookback
    s = pd.Series(closes, index=ts)
    rolling_max = s.rolling(lookback_bars, min_periods=1).max()
    ratio = s / rolling_max

    # 30-day return (30 * 24 / tf_hours bars)
    n_30d = int(30 * 24 / max(CFG.TF_HOURS, 1e-6))
    ret_30d = s.pct_change(n_30d)

    return ratio, ret_30d


def filter_signals_btc(sigs, btc_ratio, btc_ret30, mode, param=None):
    """
    mode:
      'off' — no filter
      'ath'  — reject SELL if btc_ratio > param
      'ret'  — reject SELL if btc_ret30 > param
    """
    if mode == 'off' or btc_ratio is None:
        return sigs

    out = []
    for sig in sigs:
        if sig.action != "SELL":
            out.append(sig)
            continue
        ts = sig.timestamp
        try:
            r = float(btc_ratio.loc[ts]) if ts in btc_ratio.index else 1.0
        except Exception:
            r = 1.0
        try:
            rr = float(btc_ret30.loc[ts]) if ts in btc_ret30.index else 0.0
        except Exception:
            rr = 0.0
        if not np.isfinite(r): r = 1.0
        if not np.isfinite(rr): rr = 0.0

        if mode == 'ath' and r > param:
            continue
        if mode == 'ret' and rr > param:
            continue
        out.append(sig)
    return out


def run_one(filtered_sigs, assets, corr):
    sigs = engine.deduplicate_signals(filtered_sigs)
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
        "dd": float(m.get("max_drawdown_pct", 0)),
    }


CONFIGS = [
    ("baseline",           "off", None),
    ("btc_ath_5pct_90d",   "ath", 0.95),
    ("btc_ath_10pct_90d",  "ath", 0.90),
    ("btc_ath_15pct_90d",  "ath", 0.85),
    ("btc_ret30_20pct",    "ret", 0.20),
    ("btc_ret30_10pct",    "ret", 0.10),
]

WINDOWS = {
    "2024": "2024-12-31",
    "2025": "2025-12-31",
    "2026": "2026-10-01",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h')
    ap.add_argument('--nassets', type=int, default=100)
    args = ap.parse_args()

    print("═" * 88)
    print(f"  SELL with BTC regime filter — {args.tf}, n={args.nassets}")
    print("═" * 88)

    all_res = {}
    for label, end_date in WINDOWS.items():
        print(f"\n{'─' * 88}")
        print(f"  Window {label}  (end={end_date})")
        print(f"{'─' * 88}")
        base_config(end_date, args.tf, args.nassets)

        t0 = time.time()
        assets = load_window(end_date, args.nassets, args.tf)
        print(f"  Loaded {len(assets)} assets in {time.time()-t0:.0f}s")
        if not assets:
            continue

        # BTC regime indicators
        btc_ratio, btc_ret30 = build_btc_regime_indicators(assets)
        if btc_ratio is not None:
            print(f"  BTC regime: ratio range "
                  f"[{btc_ratio.min():.3f}, {btc_ratio.max():.3f}], "
                  f"ret30 range [{btc_ret30.min():.3f}, "
                  f"{btc_ret30.max():.3f}]")

        t0 = time.time()
        raw_sigs = engine.build_signals(assets, mode="backtest")
        print(f"  Raw signals: {len(raw_sigs)} in {time.time()-t0:.0f}s")

        corr = engine.precompute_correlations(assets)

        wr = {}
        print(f"\n  Running {len(CONFIGS)} configs:")
        for name, mode, param in CONFIGS:
            t0 = time.time()
            filtered = filter_signals_btc(raw_sigs, btc_ratio, btc_ret30,
                                           mode, param)
            n_kept = len(filtered)
            n_rejected = len(raw_sigs) - n_kept
            r = run_one(filtered, assets, corr)
            r['n_kept_signals'] = n_kept
            r['n_rejected'] = n_rejected
            r['dt'] = time.time() - t0
            wr[name] = r
            print(f"    {name:<22}  Sharpe={r['sharpe']:>7.3f}  "
                  f"Final=${r['final']:>7.2f}  n={r['n']:>4}  "
                  f"WR={r['wr']*100:>5.1f}%  "
                  f"(kept={n_kept}, rejected={n_rejected})")
        all_res[label] = wr

    # Final report
    print("\n\n" + "═" * 96)
    print("  FINAL — BTC regime filter")
    print("═" * 96)
    print()
    print(f"  {'Config':<22} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Avg':>10} {'N':>8}")
    print(f"  {'─'*22} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*8}")

    for name, _, _ in CONFIGS:
        ss = [all_res.get(y, {}).get(name, {}).get('sharpe')
              for y in WINDOWS]
        valid = [s for s in ss if s is not None]
        n = sum(all_res.get(y, {}).get(name, {}).get('n', 0)
                for y in WINDOWS)
        if not valid: continue
        avg = float(np.mean(valid))

        def f(x): return f"{x:>10.3f}" if x is not None else f"{'—':>10}"
        print(f"  {name:<22} {f(ss[0])} {f(ss[1])} {f(ss[2])} "
              f"{avg:>10.3f} {n:>8}")

    os.makedirs("results", exist_ok=True)
    with open(f"results/sell_btc_regime_{args.tf}.json", "w") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: results/sell_btc_regime_{args.tf}.json")


if __name__ == "__main__":
    main()
