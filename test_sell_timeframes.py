#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sell_timeframes.py — اختبار SELL-only على فريمات أصغر.

الفرضية: الفريم الأصغر يكشف حافة SELL غير مرئية على 4h.

الاستخدام:
  python3 test_sell_timeframes.py --tf 1h --no-subbars
  python3 test_sell_timeframes.py --tf 15m --no-subbars
  python3 test_sell_timeframes.py --tf 4h       # للمقارنة
"""

import os
import sys
import time
import json
import argparse

for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
          'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[v] = '1'

sys.path.insert(0, '.')

try:
    import numpy as np
    import trading_rnd_sell_only as engine
except ImportError as e:
    print(f"ERR: {e}")
    sys.exit(1)

CFG = engine.CFG


# ═══════════════════════════════════════════════════════════════
# استراتيجيات SELL للاختبار
# ═══════════════════════════════════════════════════════════════

CONFIGS = {
    "baseline_g95_z15": {"SELL_GAUGE_PCT": 0.95, "SELL_MIN_ZDEV": 1.5},
    "loose_g85_z15":    {"SELL_GAUGE_PCT": 0.85, "SELL_MIN_ZDEV": 1.5},
    "vloose_g75_z10":   {"SELL_GAUGE_PCT": 0.75, "SELL_MIN_ZDEV": 1.0},
    "decel_g95":        {"SELL_GAUGE_PCT": 0.95,
                          "SELL_REQUIRE_DECELERATING": True},
    "composite_g95":    {"SELL_GAUGE_PCT": 0.95,
                          "SELL_REQUIRE_DECELERATING": True,
                          "SELL_REQUIRE_DOWNWARD_FORCE": True},
}

WINDOWS = {
    "2024": "2024-12-31",
    "2025": "2025-12-31",
    "2026": "2026-10-01",
}

SELL_TUNABLES = [
    'SELL_GAUGE_PCT', 'SELL_MIN_SCORE', 'SELL_MIN_ZDEV',
    'SELL_REQUIRE_EMA_DOWN', 'SELL_MAJOR_ONLY', 'SELL_MIN_ATR_FRAC',
    'SELL_REQUIRE_ORDER_EMERGING', 'SELL_REQUIRE_DECELERATING',
    'SELL_REQUIRE_DOWNWARD_FORCE', 'SELL_REQUIRE_LOW_FRICTION',
    'SELL_FRICTION_PCT',
]

_ORIG = {k: getattr(CFG, k, None) for k in SELL_TUNABLES}


def reset_sell_cfg():
    for k, v in _ORIG.items():
        if v is not None:
            setattr(CFG, k, v)


def setup_tf(tf):
    """يضبط CFG للفريم المطلوب."""
    import ccxt
    ex = ccxt.binance()
    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = \
        engine.compute_tf_scale(ex, tf)
    CFG.timeframe = tf

    _tf_h = max(float(CFG.TF_HOURS), 1e-6)
    _n_min = int(np.ceil(float(getattr(CFG, 'N_HOURS', 24.0)) / _tf_h))
    _w_min = int(np.ceil(float(getattr(CFG, 'W_HOURS', 20.0)) / _tf_h))
    _l_min = int(np.ceil(float(getattr(CFG, 'L_HOURS', 10.0)) / _tf_h))

    CFG.N = max(24, _n_min)
    CFG.W = max(20, _w_min)
    CFG.L = max(10, _l_min)

    _adv_h = float(getattr(CFG, 'ADV_HOURS', 24.0))
    CFG.ADV_BARS = max(1, int(round(_adv_h / _tf_h)))

    print(f"  TF setup: {tf}  N={CFG.N}  W={CFG.W}  L={CFG.L}  "
          f"ADV={CFG.ADV_BARS}  TF_SEC={CFG.TF_SECONDS}")


def load_window(end_date, n_assets):
    """يبني (assets, corr) لنافذة."""
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets

    import ccxt
    ex = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })

    syms = engine.scan_top_assets(ex, n_assets)
    print(f"  Fetching {len(syms)} symbols...")
    t0 = time.time()
    raw, raw_sub = engine.fetch_all_with_subbars(
        syms, ex, CFG.timeframe, CFG.history_days, workers=5,
    )
    print(f"  Fetched in {time.time()-t0:.1f}s ({len(raw)} symbols)")

    t0 = time.time()
    assets = {}
    hits, comp = 0, 0
    for sym, df in raw.items():
        ad = engine._load_asset_cache(sym, CFG.timeframe, df, CFG)
        if ad is not None:
            hits += 1
        else:
            ad = engine.process_asset(
                sym, df,
                current_capital=CFG.INITIAL_CAPITAL,
                sub_df=(raw_sub.get(sym) if raw_sub else None),
            )
            if ad is not None:
                engine._save_asset_cache(sym, CFG.timeframe, df, ad, CFG)
                comp += 1
        if ad is not None:
            assets[sym] = ad
    print(f"  AssetData in {time.time()-t0:.1f}s "
          f"(cache={hits}, computed={comp}, valid={len(assets)})")

    corr = engine.precompute_correlations(assets)
    return assets, corr


def run_config(sid, params, assets, corr):
    reset_sell_cfg()
    for k, v in params.items():
        setattr(CFG, k, v)

    t0 = time.time()
    try:
        sigs = engine.build_signals(assets, mode="backtest")
        sigs = engine.deduplicate_signals(sigs)
        trades, equity = engine.simulate_portfolio(
            sigs, assets, corr, "backtest",
        )
        m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    except Exception as e:
        print(f"    ERR {sid}: {e}")
        return None

    return {
        "sharpe": float(m.get("sharpe_ratio", 0)),
        "final": float(m.get("final_capital", 0)),
        "n": int(m.get("n_trades", 0)),
        "n_sell": int(m.get("sell_count", 0)),
        "dt": time.time() - t0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='1h',
                    choices=['5m', '15m', '30m', '1h', '4h'])
    ap.add_argument('--nassets', type=int, default=15)
    ap.add_argument('--no-subbars', action='store_true')
    args = ap.parse_args()

    if args.no_subbars:
        CFG.SUBBARS_ENABLED = False
        print("  Sub-bars DISABLED (faster fetch)")

    print("═" * 80)
    print(f"  SELL-only on {args.tf}  —  {len(CONFIGS)} configs × "
          f"{len(WINDOWS)} windows")
    print("═" * 80)

    setup_tf(args.tf)

    all_res = {}

    for label, end_date in WINDOWS.items():
        print(f"\n{'═' * 80}")
        print(f"  Window {label}  (end={end_date})")
        print(f"{'═' * 80}")

        assets, corr = load_window(end_date, args.nassets)
        if not assets:
            continue

        print(f"\n  Running {len(CONFIGS)} configs on "
              f"{len(assets)} assets:")
        wr = {}
        for sid, params in CONFIGS.items():
            r = run_config(sid, params, assets, corr)
            if r is None:
                continue
            wr[sid] = r
            print(f"    ✅ {sid:<22}  "
                  f"Sharpe={r['sharpe']:>7.3f}  "
                  f"Final=${r['final']:>8.2f}  "
                  f"n={r['n']:>4} (SELL={r['n_sell']:>3})  "
                  f"({r['dt']:.0f}s)")
        all_res[label] = wr

    # تقرير نهائي
    print("\n\n" + "═" * 92)
    print(f"  SELL on {args.tf}  —  FINAL REPORT")
    print("═" * 92)
    print()
    print(f"  {'Config':<22} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'SELLs':>8} {'Verdict':<15}")
    print(f"  {'─' * 22} {'─' * 10} {'─' * 10} "
          f"{'─' * 10} {'─' * 10} {'─' * 8} {'─' * 15}")

    viable = []
    promising = []
    for sid in CONFIGS:
        ss = []
        total_sell = 0
        for y in WINDOWS:
            r = all_res.get(y, {}).get(sid)
            if r is None:
                ss = []
                break
            ss.append(r["sharpe"])
            total_sell += r["n_sell"]
        if len(ss) != 3:
            print(f"  {sid:<22} — incomplete")
            continue
        mn = min(ss)
        if mn >= 0.8 and total_sell >= 300:
            v = "✅ VIABLE"
            viable.append(sid)
        elif mn >= 0.5:
            v = "🟡 promising"
            promising.append(sid)
        elif mn >= 0:
            v = "🟠 marginal"
        else:
            v = "❌ losing"
        print(f"  {sid:<22} {ss[0]:>10.3f} {ss[1]:>10.3f} "
              f"{ss[2]:>10.3f} {mn:>10.3f} {total_sell:>8} {v:<15}")

    print()
    if viable:
        print(f"  🏆 VIABLE: {', '.join(viable)}")
        print(f"     → تجاوز المعايير، يستحق R&D أعمق")
    elif promising:
        print(f"  🟡 PROMISING: {', '.join(promising)}")
        print(f"     → يحتاج تحسين إضافي قبل الدمج")
    else:
        print(f"  ❌ لا config يظهر حافة على {args.tf}")
    print("═" * 92)

    os.makedirs("results", exist_ok=True)
    out = f"results/sell_tf_{args.tf}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
