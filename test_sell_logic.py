#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sell_logic.py — اختبار 5 فرضيات منطق SELL جديدة.

يستخدم نفس بنية sell_ablation_fast.py (AssetData cache)
لكن مع flags منطق جديدة.
"""

import os
import sys
import time
import json

for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
          'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[v] = '1'

sys.path.insert(0, '.')

try:
    import trading_rnd_sell_only as engine
except ImportError as e:
    print(f"ERR: {e}")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# Hypotheses
# ═══════════════════════════════════════════════════════════════

HYPOTHESES = {
    "H0_baseline":          {},
    "H1_order_emerging":    {"SELL_REQUIRE_ORDER_EMERGING": True},
    "H2_decelerating":      {"SELL_REQUIRE_DECELERATING": True},
    "H3_downward_force":    {"SELL_REQUIRE_DOWNWARD_FORCE": True},
    "H4_low_friction":      {"SELL_REQUIRE_LOW_FRICTION": True},
    "H5_composite":         {
        "SELL_REQUIRE_ORDER_EMERGING": True,
        "SELL_REQUIRE_DECELERATING": True,
        "SELL_REQUIRE_DOWNWARD_FORCE": True,
    },
}

WINDOWS = {"2024": "2024-12-31",
           "2025": "2025-12-31",
           "2026": "2026-10-01"}

CFG = engine.CFG

# جميع الحقول التي نُعدّلها
_TUNABLE = [
    "SELL_GAUGE_PCT", "SELL_MIN_SCORE", "SELL_MIN_ZDEV",
    "SELL_REQUIRE_EMA_DOWN", "SELL_MAJOR_ONLY", "SELL_MIN_ATR_FRAC",
    "SELL_REQUIRE_ORDER_EMERGING", "SELL_REQUIRE_DECELERATING",
    "SELL_REQUIRE_DOWNWARD_FORCE", "SELL_REQUIRE_LOW_FRICTION",
    "SELL_FRICTION_PCT", "BACKTEST_END_DATE",
]

_ORIG = {k: getattr(CFG, k, None) for k in _TUNABLE}


def reset_cfg():
    for k, v in _ORIG.items():
        if v is not None:
            setattr(CFG, k, v)


def apply_hypothesis(params):
    reset_cfg()
    # defaults for this test
    CFG.SELL_GAUGE_PCT = 0.95
    CFG.SELL_MIN_ZDEV = 1.0  # more permissive base
    for k, v in params.items():
        setattr(CFG, k, v)


def load_window(label, end_date):
    print(f"\n{'═' * 72}")
    print(f"  Loading {label} (end={end_date})")
    print(f"{'═' * 72}")

    reset_cfg()
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365

    import ccxt
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })

    syms = engine.scan_top_assets(exchange, CFG.n_assets)
    t0 = time.time()
    raw, raw_sub = engine.fetch_all_with_subbars(
        syms, exchange, CFG.timeframe, CFG.history_days, workers=5,
    )
    print(f"  Fetch: {time.time() - t0:.1f}s ({len(raw)} symbols)")

    t0 = time.time()
    assets = {}
    for sym, df in raw.items():
        ad = engine._load_asset_cache(sym, CFG.timeframe, df, CFG)
        if ad is None:
            ad = engine.process_asset(
                sym, df,
                current_capital=CFG.INITIAL_CAPITAL,
                sub_df=(raw_sub.get(sym) if raw_sub else None),
            )
            if ad is not None:
                engine._save_asset_cache(sym, CFG.timeframe, df, ad, CFG)
        if ad is not None:
            assets[sym] = ad
    print(f"  AssetData: {time.time() - t0:.1f}s ({len(assets)} valid)")

    corr = engine.precompute_correlations(assets)
    return assets, corr, exchange


def run_one(hid, params, assets, corr):
    apply_hypothesis(params)
    t0 = time.time()
    try:
        sigs = engine.build_signals(assets, mode="backtest")
        sigs = engine.deduplicate_signals(sigs)
        trades, equity = engine.simulate_portfolio(
            sigs, assets, corr, "backtest",
        )
        m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    except Exception as e:
        print(f"    ERR: {hid}: {e}")
        return None
    return {
        "sharpe": float(m.get("sharpe_ratio", 0)),
        "final": float(m.get("final_capital", 0)),
        "n": int(m.get("n_trades", 0)),
        "n_sell": int(m.get("sell_count", 0)),
        "dt": time.time() - t0,
    }


def main():
    print("═" * 72)
    print("  SELL LOGIC V2 — 6 hypotheses × 3 windows")
    print("═" * 72)

    all_res = {}

    for label, end_date in WINDOWS.items():
        assets, corr, exchange = load_window(label, end_date)
        if not assets:
            continue

        print(f"\n  Running {len(HYPOTHESES)} hypotheses on "
              f"{len(assets)} assets:")
        wr = {}
        for hid, params in HYPOTHESES.items():
            r = run_one(hid, params, assets, corr)
            if r is None:
                continue
            wr[hid] = r
            print(f"    ✅ {hid:<24}  "
                  f"Sharpe={r['sharpe']:>7.3f}  "
                  f"Final=${r['final']:>8.2f}  "
                  f"n={r['n']:>4} (SELL={r['n_sell']:>3})  "
                  f"({r['dt']:.0f}s)")
        all_res[label] = wr

    # Final table
    print("\n\n" + "═" * 92)
    print("  SELL LOGIC V2 — FINAL")
    print("═" * 92)
    print()
    print(f"  {'Hypothesis':<24} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'SELLs':>8} {'Verdict':<15}")
    print(f"  {'─' * 24} {'─' * 10} {'─' * 10} "
          f"{'─' * 10} {'─' * 10} {'─' * 8} {'─' * 15}")

    viable = []
    for hid in HYPOTHESES:
        ss = []
        total_sell = 0
        for y in WINDOWS:
            r = all_res.get(y, {}).get(hid)
            if r is None:
                ss = []
                break
            ss.append(r["sharpe"])
            total_sell += r["n_sell"]
        if len(ss) != 3:
            print(f"  {hid:<24} — incomplete")
            continue
        mn = min(ss)
        if mn >= 0.8 and total_sell >= 300:
            v = "✅ VIABLE"
            viable.append(hid)
        elif mn >= 0.5:
            v = "🟡 weak"
        elif mn >= 0:
            v = "🟠 marginal"
        else:
            v = "❌ losing"
        print(f"  {hid:<24} {ss[0]:>10.3f} {ss[1]:>10.3f} "
              f"{ss[2]:>10.3f} {mn:>10.3f} {total_sell:>8} {v:<15}")

    print()
    if viable:
        print(f"  🏆 VIABLE: {', '.join(viable)}")
    else:
        print(f"  ❌ لا hypothesis يلبّي المعايير")
    print("═" * 92)

    with open("results/sell_logic_v2.json", "w") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: results/sell_logic_v2.json")


if __name__ == "__main__":
    main()
