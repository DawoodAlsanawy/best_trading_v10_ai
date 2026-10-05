#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_sell_wide_sl.py — اختبار SELL مع SL مضاعف."""

import os, sys, time, json
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

    # ══ [PICKLE-FIX] register dataclass aliases in __main__ ══
    import __main__ as _pcmain
    for _cn in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
        if hasattr(engine, _cn):
            setattr(_pcmain, _cn, getattr(engine, _cn))
CFG = engine.CFG

# ═══════════════════════════════════════════════════════════════
# Configs — نبدأ من loose_g85_z15 (الأفضل أداءً في 2024)
# ═══════════════════════════════════════════════════════════════

CONFIGS = {
    "baseline_sl1x":     {"SELL_SL_WIDEN_MULT": 1.0},
    "wide_sl2x":         {"SELL_SL_WIDEN_MULT": 2.0},
    "wide_sl3x":         {"SELL_SL_WIDEN_MULT": 3.0},
    "wide_sl5x":         {"SELL_SL_WIDEN_MULT": 5.0},
    "wide_sl3x_loose":   {"SELL_SL_WIDEN_MULT": 3.0,
                          "SELL_GAUGE_PCT": 0.85,
                          "SELL_MIN_ZDEV": 1.5},
    "wide_sl3x_decel":   {"SELL_SL_WIDEN_MULT": 3.0,
                          "SELL_REQUIRE_DECELERATING": True},
}

WINDOWS = {"2024": "2024-12-31",
           "2025": "2025-12-31",
           "2026": "2026-10-01"}

# القيم الافتراضية التي نضبطها
DEFAULTS = {
    "SELL_GAUGE_PCT": 0.95,
    "SELL_MIN_ZDEV": 1.5,
    "SELL_MIN_SCORE": 3,
    "SELL_SL_WIDEN_MULT": 1.0,
    "SELL_REQUIRE_DECELERATING": False,
    "SELL_REQUIRE_DOWNWARD_FORCE": False,
    "SELL_REQUIRE_ORDER_EMERGING": False,
    "SELL_REQUIRE_LOW_FRICTION": False,
    "SELL_REQUIRE_EMA_DOWN": False,
    "SELL_MAJOR_ONLY": False,
    "SELL_MIN_ATR_FRAC": 0.0,
}

def reset_cfg():
    for k, v in DEFAULTS.items():
        setattr(CFG, k, v)


def load_window(end_date, tf='4h'):
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = 100
    CFG.timeframe = tf

    import ccxt
    ex = ccxt.binance({'enableRateLimit': True,
                       'options': {'defaultType': 'future'}})

    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = \
        engine.compute_tf_scale(ex, tf)

    # TF-unified windows
    _tf_h = max(float(CFG.TF_HOURS), 1e-6)
    CFG.N = max(24, int(np.ceil(24.0 / _tf_h)))
    CFG.W = max(20, int(np.ceil(20.0 / _tf_h)))
    CFG.L = max(10, int(np.ceil(10.0 / _tf_h)))
    CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))

    syms = engine.scan_top_assets(ex, CFG.n_assets)
    t0 = time.time()
    raw, raw_sub = engine.fetch_all_with_subbars(
        syms, ex, tf, CFG.history_days, workers=5)
    print(f"  Fetch: {time.time()-t0:.1f}s ({len(raw)} symbols)")

    t0 = time.time()
    assets = {}
    for sym, df in raw.items():
        ad = engine._load_asset_cache(sym, tf, df, CFG)
        if ad is None:
            ad = engine.process_asset(sym, df,
                current_capital=CFG.INITIAL_CAPITAL,
                sub_df=(raw_sub.get(sym) if raw_sub else None))
            if ad is not None:
                engine._save_asset_cache(sym, tf, df, ad, CFG)
        if ad is not None:
            assets[sym] = ad
    print(f"  AssetData: {time.time()-t0:.1f}s ({len(assets)} valid)")
    return assets, engine.precompute_correlations(assets)


def run_config(sid, params, assets, corr):
    reset_cfg()
    for k, v in params.items():
        setattr(CFG, k, v)
    t0 = time.time()
    try:
        sigs = engine.build_signals(assets, mode="backtest")
        sigs = engine.deduplicate_signals(sigs)
        trades, equity = engine.simulate_portfolio(
            sigs, assets, corr, "backtest")
        m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    except Exception as e:
        print(f"    ERR {sid}: {e}")
        return None
    return {
        "sharpe": float(m.get("sharpe_ratio", 0)),
        "final": float(m.get("final_capital", 0)),
        "n": int(m.get("n_trades", 0)),
        "n_sell": int(m.get("sell_count", 0)),
        "avg_sl": float(m.get("avg_loss", 0)),
        "dt": time.time() - t0,
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h',
                    choices=['1h', '4h'])
    args = ap.parse_args()

    print("═" * 80)
    print(f"  SELL WIDE-SL test on {args.tf}")
    print("═" * 80)

    all_res = {}
    for label, end_date in WINDOWS.items():
        print(f"\n{'═' * 80}")
        print(f"  Window {label} (end={end_date})")
        print(f"{'═' * 80}")
        assets, corr = load_window(end_date, args.tf)
        if not assets:
            continue
        wr = {}
        print(f"\n  Running {len(CONFIGS)} configs on {len(assets)} assets:")
        for sid, params in CONFIGS.items():
            r = run_config(sid, params, assets, corr)
            if r is None:
                continue
            wr[sid] = r
            print(f"    ✅ {sid:<22} Sharpe={r['sharpe']:>7.3f} "
                  f"Final=${r['final']:>8.2f} n={r['n']:>4} "
                  f"(SELL={r['n_sell']:>3}) ({r['dt']:.0f}s)")
        all_res[label] = wr

    # Final
    print("\n\n" + "═" * 92)
    print(f"  SELL WIDE-SL on {args.tf} — FINAL")
    print("═" * 92)
    print()
    print(f"  {'Config':<22} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'SELLs':>8} {'Verdict':<15}")
    print(f"  {'─'*22} {'─'*10} {'─'*10} {'─'*10} {'─'*10} "
          f"{'─'*8} {'─'*15}")

    viable = []
    for sid in CONFIGS:
        ss, tot = [], 0
        for y in WINDOWS:
            r = all_res.get(y, {}).get(sid)
            if r is None:
                ss = []; break
            ss.append(r["sharpe"])
            tot += r["n_sell"]
        if len(ss) != 3:
            print(f"  {sid:<22} — incomplete")
            continue
        mn = min(ss)
        if mn >= 0.8 and tot >= 300:
            v = "✅ VIABLE"; viable.append(sid)
        elif mn >= 0.5:
            v = "🟡 promising"
        elif mn >= 0:
            v = "🟠 marginal"
        else:
            v = "❌ losing"
        print(f"  {sid:<22} {ss[0]:>10.3f} {ss[1]:>10.3f} "
              f"{ss[2]:>10.3f} {mn:>10.3f} {tot:>8} {v:<15}")

    print()
    if viable:
        print(f"  🏆 VIABLE: {', '.join(viable)}")
    else:
        print(f"  ℹ️  لا config حقق المعايير على {args.tf}")

    with open(f"results/sell_widesl_{args.tf}.json", "w") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
