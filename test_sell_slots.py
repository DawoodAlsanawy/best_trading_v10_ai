#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sell_slots.py — اختبار SELL مع فلاتر تنفيذ مستقلة.

4 configs × 3 نوافذ. لا تعديل على الملف المصدر.
يُعدّل CFG مباشرة قبل simulate_portfolio.
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


def base_config(end_date, tf, n_assets):
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf
    CFG.SELL_ENABLED = True
    CFG.BUY_DISABLED = True   # SELL-only
    CFG.GAUGE_DISABLE_SELL = False
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


def run_config(sigs, assets, corr, max_slots, cooldown_bars,
                corr_thr, label):
    # monkeypatch CFG before simulate
    CFG.MAX_CONCURRENT_ASSETS = int(max_slots)
    CFG.REENTRY_COOLDOWN_ENABLED = (cooldown_bars > 0)
    CFG.REENTRY_COOLDOWN_BARS = int(cooldown_bars)
    CFG.CORRELATION_THRESHOLD = float(corr_thr)

    t0 = time.time()
    try:
        trades, equity = engine.simulate_portfolio(
            sigs, assets, corr, "backtest")
        m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    except Exception as e:
        print(f"    ERR {label}: {e}")
        return None

    return {
        "sharpe": float(m.get("sharpe_ratio", 0)),
        "final": float(m.get("final_capital", 0)),
        "n": int(m.get("n_trades", 0)),
        "n_sell": int(m.get("sell_count", 0)),
        "wr": float(m.get("win_rate", 0)),
        "pf": float(m.get("profit_factor", 0)),
        "dd": float(m.get("max_drawdown_pct", 0)),
        "dt": time.time() - t0,
    }


# (name, max_slots, cooldown_bars, corr_thr)
CONFIGS = [
    ("baseline_s3_cd3",    3,  3, 0.70),
    ("slots_10",          10,  3, 0.70),
    ("slots_20",          20,  3, 0.70),
    ("slots_30_cd1",      30,  1, 0.70),
    ("slots_20_relaxed",  20,  1, 0.85),
    ("slots_30_all_relax",30,  0, 0.95),
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

    print("═" * 80)
    print(f"  SELL execution filters test — {args.tf}, n_assets={args.nassets}")
    print("═" * 80)

    all_res = {}
    for label, end_date in WINDOWS.items():
        print(f"\n{'─' * 80}")
        print(f"  Window {label}  (end={end_date})")
        print(f"{'─' * 80}")
        base_config(end_date, args.tf, args.nassets)

        t0 = time.time()
        assets = load_window(end_date, args.nassets, args.tf)
        print(f"  Loaded {len(assets)} assets in {time.time()-t0:.0f}s")
        if not assets:
            continue

        t0 = time.time()
        sigs = engine.build_signals(assets, mode="backtest")
        sigs = engine.deduplicate_signals(sigs)
        print(f"  Signals: {len(sigs)} in {time.time()-t0:.0f}s")

        corr = engine.precompute_correlations(assets)

        wr = {}
        print(f"\n  Running {len(CONFIGS)} execution configs:")
        for name, slots, cd, ct in CONFIGS:
            r = run_config(sigs, assets, corr, slots, cd, ct, name)
            if r is None:
                continue
            wr[name] = r
            print(f"    {name:<22}  Sharpe={r['sharpe']:>7.3f}  "
                  f"Final=${r['final']:>8.2f}  n={r['n']:>4}  "
                  f"WR={r['wr']*100:>5.1f}%  PF={r['pf']:.3f}  "
                  f"DD={r['dd']:>5.1f}%  ({r['dt']:.0f}s)")
        all_res[label] = wr

    # ═══ Final Report ═══
    print("\n\n" + "═" * 100)
    print("  FINAL — SELL with independent execution filters")
    print("═" * 100)
    print()

    header = ['2024', '2025', '2026']
    for name, _, _, _ in CONFIGS:
        row_s, row_f, row_n, row_wr, row_dd = [], [], [], [], []
        for y in header:
            r = all_res.get(y, {}).get(name)
            if r is None:
                row_s.append(None); row_f.append(None); row_n.append(0)
                row_wr.append(None); row_dd.append(None)
            else:
                row_s.append(r['sharpe']); row_f.append(r['final'])
                row_n.append(r['n']); row_wr.append(r['wr'])
                row_dd.append(r['dd'])

        def fmt_s(x): return f"{x:>8.3f}" if x is not None else "     —"
        def fmt_f(x): return f"${x:>7.1f}" if x is not None else "    —  "
        def fmt_w(x): return f"{x*100:>6.1f}%" if x is not None else "   —  "

        print(f"\n  ▶ {name}")
        print(f"      Sharpe:  " + "  ".join(fmt_s(x) for x in row_s))
        print(f"      Final:   " + "  ".join(fmt_f(x) for x in row_f))
        print(f"      Trades:  " + "  ".join(f"{x:>8}" for x in row_n))
        print(f"      WR:      " + "  ".join(fmt_w(x) for x in row_wr))

    # ═══ Best config ═══
    print("\n" + "═" * 100)
    print("  أفضل config حسب متوسط Sharpe")
    print("═" * 100)

    rankings = []
    for name, _, _, _ in CONFIGS:
        vals = [all_res.get(y, {}).get(name, {}).get('sharpe', None)
                for y in header]
        valid = [v for v in vals if v is not None]
        if not valid:
            continue
        rankings.append((name, float(np.mean(valid)),
                          min(valid), max(valid),
                          sum(all_res.get(y, {}).get(name, {}).get('n', 0)
                              for y in header)))

    rankings.sort(key=lambda x: -x[1])
    print(f"\n  {'Config':<22} {'Avg':>9} {'Min':>9} {'Max':>9} {'N':>8}")
    print(f"  {'─'*22} {'─'*9} {'─'*9} {'─'*9} {'─'*8}")
    for name, avg, mn, mx, n in rankings:
        marker = " 🏆" if name == rankings[0][0] else ""
        print(f"  {name:<22} {avg:>9.3f} {mn:>9.3f} {mx:>9.3f} {n:>8}{marker}")

    os.makedirs("results", exist_ok=True)
    with open(f"results/sell_slots_{args.tf}.json", "w") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: results/sell_slots_{args.tf}.json")


if __name__ == "__main__":
    main()
