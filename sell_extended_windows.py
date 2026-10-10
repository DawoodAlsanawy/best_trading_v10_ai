#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sell_extended_windows.py — اختبار SELL across full cycle.

7 نوافذ × configs:
  - SELL-only, gauge filter OFF
  - SELL-only, low_p25
  - BUY+SELL, gauge filter OFF
  - BUY-only baseline

الهدف: هل SELL إيجابي فقط في 2026؟ أم حافة عامة؟
"""

import os, sys, time, json, argparse
for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
          'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[v] = '1'
sys.path.insert(0, '.')

import numpy as np
import trading_rnd_sell_only as engine
import __main__ as _pcmain
for _cn in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(engine, _cn):
        setattr(_pcmain, _cn, getattr(engine, _cn))

CFG = engine.CFG


def force_config(end_date, tf, n_assets, sell_only, gauge_on):
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf

    CFG.SELL_ENABLED = True
    CFG.BUY_DISABLED = bool(sell_only)
    CFG.GAUGE_DISABLE_SELL = False
    CFG.GAUGE_FILTER_ENABLED = bool(gauge_on)

    CFG.SELL_GAUGE_PCT = 0.95
    CFG.SELL_MIN_SCORE = 3
    CFG.SELL_MIN_ZDEV = 1.5
    CFG.SELL_REQUIRE_EMA_DOWN = False
    CFG.SELL_MAJOR_ONLY = False
    CFG.SELL_MIN_ATR_FRAC = 0.0
    CFG.SELL_REQUIRE_ORDER_EMERGING = False
    CFG.SELL_REQUIRE_DECELERATING = False
    CFG.SELL_REQUIRE_DOWNWARD_FORCE = False
    CFG.SELL_REQUIRE_LOW_FRICTION = False
    CFG.SELL_SL_WIDEN_MULT = 1.0
    CFG.SELL_REQUIRE_EMA_UP = False
    CFG.SELL_GAUGE_POOL_PER_ASSET = False

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


def run_bt(assets, corr):
    sigs = engine.build_signals(assets, mode="backtest")
    sigs = engine.deduplicate_signals(sigs)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h')
    ap.add_argument('--nassets', type=int, default=100)
    args = ap.parse_args()

    WINDOWS = [
        ("2021", "2021-12-31"),
        ("2022", "2022-12-31"),
        ("2023", "2023-12-31"),
        ("2024", "2024-12-31"),
        ("2025", "2025-12-31"),
        ("2026", "2026-10-01"),
    ]

    # configs: (name, sell_only, gauge_on)
    CONFIGS = [
        ("sell_only_no_gauge", True,  False),
        ("sell_only_gauge95",  True,  True),
        ("buy_sell_no_gauge",  False, False),
        ("buy_only_baseline",  False, True),  # gauge filter only affects SELL
    ]

    print("═" * 92)
    print(f"  SELL extended windows test — {args.tf}, n_assets={args.nassets}")
    print("═" * 92)

    all_res = {}

    for label, end_date in WINDOWS:
        print(f"\n{'─' * 92}")
        print(f"  Window {label}  (end={end_date})")
        print(f"{'─' * 92}")

        wr = {}
        for name, sell_only, gauge_on in CONFIGS:
            force_config(end_date, args.tf, args.nassets,
                          sell_only, gauge_on)

            t0 = time.time()
            try:
                assets = load_window(end_date, args.nassets, args.tf)
            except Exception as e:
                print(f"    ❌ {name}: fetch failed: {e}")
                continue
            if not assets:
                continue

            t0 = time.time()
            try:
                corr = engine.precompute_correlations(assets)
                r = run_bt(assets, corr)
            except Exception as e:
                print(f"    ❌ {name}: simulate failed: {e}")
                continue

            r["assets"] = len(assets)
            r["dt"] = time.time() - t0
            wr[name] = r
            print(f"    ✅ {name:<22}  "
                  f"Sharpe={r['sharpe']:>8.3f}  "
                  f"Final=${r['final']:>8.2f}  "
                  f"n={r['n']:>5} (B={r['n_buy']:>4},S={r['n_sell']:>4})  "
                  f"WR={r['wr']*100:>5.1f}%  PF={r['pf']:.3f}  "
                  f"DD={r['dd']:.1f}%  ({r['dt']:.0f}s)")

        all_res[label] = wr

    # ═══ Report ═══
    print("\n\n" + "═" * 100)
    print("  SELL vs BUY across full cycle")
    print("═" * 100)
    print()

    for name, _, _ in CONFIGS:
        print(f"\n  ▶ {name}:")
        print(f"    {'Window':<10} {'Sharpe':>10} {'Final':>12} "
              f"{'N':>6} {'Sell':>6} {'WR':>8} {'PF':>8} {'DD':>8}")
        for label, _ in WINDOWS:
            r = all_res.get(label, {}).get(name)
            if r is None:
                print(f"    {label:<10} — incomplete")
                continue
            print(f"    {label:<10} {r['sharpe']:>10.3f} "
                  f"${r['final']:>10.2f} {r['n']:>6} {r['n_sell']:>6} "
                  f"{r['wr']*100:>7.1f}% {r['pf']:>8.3f} {r['dd']:>7.1f}%")

        # Aggregate
        sharpes = [all_res[l][name]['sharpe']
                   for l, _ in WINDOWS if name in all_res.get(l, {})]
        if sharpes:
            mn = min(sharpes)
            avg = float(np.mean(sharpes))
            pos = sum(1 for s in sharpes if s > 0)
            print(f"    {'SUMMARY':<10} min={mn:>7.3f}  avg={avg:>7.3f}  "
                  f"positive={pos}/{len(sharpes)}")

    print()
    print("═" * 100)

    os.makedirs("results", exist_ok=True)
    out = f"results/sell_extended_{args.tf}.json"
    with open(out, "w") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Saved: {out}")


if __name__ == "__main__":
    main()
