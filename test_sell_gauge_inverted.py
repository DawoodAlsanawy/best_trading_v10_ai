#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sell_gauge_inverted.py — اختبار SELL مع gauge منخفض.

الفرضية: SELL يحتاج gauge_force منخفض (لا مرتفع).

4 configs:
  - baseline (gauge off)
  - gauge_low_p25  (احتفظ بأدنى 25%)
  - gauge_low_p50  (احتفظ بأدنى 50%)
  - gauge_high_p95 (السلوك الحالي — للمقارنة)
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


def force_config(end_date, tf, n_assets):
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf
    # SELL-only for clean test
    CFG.SELL_ENABLED = True
    CFG.BUY_DISABLED = True
    CFG.GAUGE_DISABLE_SELL = False
    CFG.GAUGE_FILTER_ENABLED = False   # نحن نُصفّي يدوياً
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


def filter_by_gauge(sigs, assets, mode, pct_thresh):
    """
    mode: 'off' | 'low' | 'high'
    low: keep if gauge_force <= p{pct_thresh*100}
    high: keep if gauge_force >= p{pct_thresh*100}
    """
    if mode == 'off':
        return sigs

    # compute global thresholds
    all_gf = []
    for ad in assets.values():
        tr = int(getattr(ad, 'train_end', 0))
        pool = ad.gauge_force[tr:]
        pool = pool[pool > 0]
        if len(pool) > 0:
            all_gf.extend(pool.tolist())
    if not all_gf:
        return sigs
    arr = np.asarray(all_gf)
    thr = float(np.percentile(arr, pct_thresh * 100))

    out = []
    for sig in sigs:
        ad = assets.get(sig.symbol)
        if ad is None:
            continue
        fi = int(sig.feat_idx)
        if not (0 <= fi < len(ad.gauge_force)):
            continue
        gf = float(ad.gauge_force[fi])
        if mode == 'low' and gf > thr:
            continue
        if mode == 'high' and gf < thr:
            continue
        out.append(sig)
    return out


def run_one(sigs, assets, corr):
    sigs = engine.deduplicate_signals(sigs)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h', choices=['1h', '4h'])
    ap.add_argument('--nassets', type=int, default=100)
    args = ap.parse_args()

    WINDOWS = {"2024": "2024-12-31",
               "2025": "2025-12-31",
               "2026": "2026-10-01"}

    CONFIGS = {
        "off":              ("off",  0.0),
        "low_p25":          ("low",  0.25),
        "low_p50":          ("low",  0.50),
        "high_p95_current": ("high", 0.95),
    }

    print("═" * 80)
    print(f"  SELL gauge inverted test — {args.tf}, n_assets={args.nassets}")
    print("═" * 80)

    all_res = {}
    for label, end_date in WINDOWS.items():
        print(f"\n{'─' * 80}")
        print(f"  Window {label}  (end={end_date})")
        print(f"{'─' * 80}")
        force_config(end_date, args.tf, args.nassets)

        t0 = time.time()
        assets = load_window(end_date, args.nassets, args.tf)
        print(f"  Loaded {len(assets)} assets in {time.time()-t0:.0f}s")
        if not assets:
            continue

        t0 = time.time()
        raw_sigs = engine.build_signals(assets, mode="backtest")
        print(f"  Raw signals: {len(raw_sigs)} in {time.time()-t0:.0f}s")

        corr = engine.precompute_correlations(assets)

        wr = {}
        for sid, (mode, pct) in CONFIGS.items():
            t0 = time.time()
            filtered = filter_by_gauge(raw_sigs, assets, mode, pct)
            r = run_one(filtered, assets, corr)
            r["dt"] = time.time() - t0
            wr[sid] = r
            print(f"    ✅ {sid:<20} Sharpe={r['sharpe']:>8.3f}  "
                  f"Final=${r['final']:>8.2f}  n={r['n']:>4}  "
                  f"WR={r['wr']*100:>5.1f}%  PF={r['pf']:.3f}  "
                  f"DD={r['dd']:.1f}%  ({r['dt']:.0f}s)")
        all_res[label] = wr

    # ═══ Final Report ═══
    print("\n\n" + "═" * 88)
    print("  FINAL — SELL with different gauge filters")
    print("═" * 88)
    print()
    print(f"  {'Config':<20} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'Avg':>10} {'Trades':>8}")
    print(f"  {'─'*20} {'─'*10} {'─'*10} {'─'*10} {'─'*10} "
          f"{'─'*10} {'─'*8}")

    for sid in CONFIGS:
        ss, tot = [], 0
        for y in WINDOWS:
            r = all_res.get(y, {}).get(sid)
            if r is None:
                ss = []; break
            ss.append(r["sharpe"])
            tot += r["n_sell"]
        if len(ss) != 3:
            continue
        mn = min(ss)
        avg = float(np.mean(ss))
        print(f"  {sid:<20} {ss[0]:>10.3f} {ss[1]:>10.3f} "
              f"{ss[2]:>10.3f} {mn:>10.3f} {avg:>10.3f} {tot:>8}")

    # Detailed table
    print()
    print(f"  {'Config':<20} {'Final 2024':>12} {'Final 2025':>12} "
          f"{'Final 2026':>12}")
    print(f"  {'─'*20} {'─'*12} {'─'*12} {'─'*12}")
    for sid in CONFIGS:
        finals = []
        for y in WINDOWS:
            r = all_res.get(y, {}).get(sid)
            finals.append(r['final'] if r else 0)
        print(f"  {sid:<20} ${finals[0]:>10.2f} ${finals[1]:>10.2f} "
              f"${finals[2]:>10.2f}")

    os.makedirs("results", exist_ok=True)
    with open(f"results/sell_gauge_inverted_{args.tf}.json", "w") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: results/sell_gauge_inverted_{args.tf}.json")


if __name__ == "__main__":
    main()
