#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sell_slots_fixed.py — إصلاح خطأ MIN_RISK_PER_TRADE.

الإصلاحات:
  1. رفع heat_max مع slots بدل تخفيض per_slot
  2. المعادلة: total_heat = n_slots × base_per_slot (constant)
  3. وبذلك slots أعلى = per_slot ثابت

Configs:
  - baseline (3, heat=0.10)
  - slots_10_heat30 (10, heat=0.30)
  - slots_20_heat50 (20, heat=0.50)
  - slots_20_heat30 (20, heat=0.30) — اختبار أثر heat
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
    # ── البارامترات الحاسمة ──
    CFG.MIN_RISK_PER_TRADE = 0.003   # نخفّض الحد من 0.5% إلى 0.3%
    CFG.MAX_RISK_PER_TRADE = 0.030   # نُبقي السقف
    CFG.RISK_STRENGTH_MIN = 0.5
    CFG.RISK_STRENGTH_MAX = 1.5

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


def run_config(sigs, assets, corr, max_slots, heat_max,
                cooldown_bars, label):
    # نُعيد MONKEYPATCH — لكن مُتَّسق هذه المرة
    CFG.MAX_CONCURRENT_ASSETS = int(max_slots)
    CFG.PORTFOLIO_HEAT_MAX = float(heat_max)
    CFG.REENTRY_COOLDOWN_ENABLED = (cooldown_bars > 0)
    CFG.REENTRY_COOLDOWN_BARS = int(cooldown_bars)

    # تحقق أمني
    base_per_slot = heat_max / max_slots
    if base_per_slot * 0.5 < CFG.MIN_RISK_PER_TRADE:
        print(f"    ⚠️  {label}: base_per_slot × min_strength "
              f"({base_per_slot*0.5:.4f}) < MIN_RISK "
              f"({CFG.MIN_RISK_PER_TRADE})")

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
        "wr": float(m.get("win_rate", 0)),
        "pf": float(m.get("profit_factor", 0)),
        "dd": float(m.get("max_drawdown_pct", 0)),
        "base_per_slot": base_per_slot,
        "dt": time.time() - t0,
    }


# (name, slots, heat_max, cooldown_bars)
CONFIGS = [
    ("baseline_s3_h10",    3,  0.10, 3),
    ("s10_h30",           10,  0.30, 3),
    ("s10_h15",           10,  0.15, 3),
    ("s20_h40",           20,  0.40, 3),
    ("s20_h60",           20,  0.60, 3),
    ("s10_h30_cd1",       10,  0.30, 1),
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
    print(f"  SELL slots FIXED test — {args.tf}, n_assets={args.nassets}")
    print(f"  MIN_RISK_PER_TRADE lowered to 0.003 (from 0.005)")
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

        t0 = time.time()
        sigs = engine.build_signals(assets, mode="backtest")
        sigs = engine.deduplicate_signals(sigs)
        print(f"  Signals: {len(sigs)} in {time.time()-t0:.0f}s")

        corr = engine.precompute_correlations(assets)

        wr = {}
        print(f"\n  Running {len(CONFIGS)} configs:")
        for name, slots, heat, cd in CONFIGS:
            r = run_config(sigs, assets, corr, slots, heat, cd, name)
            if r is None:
                continue
            wr[name] = r
            print(f"    {name:<20}  Sharpe={r['sharpe']:>7.3f}  "
                  f"Final=${r['final']:>7.2f}  n={r['n']:>4}  "
                  f"WR={r['wr']*100:>5.1f}%  PF={r['pf']:.3f}  "
                  f"DD={r['dd']:>5.1f}%  "
                  f"(bps={r['base_per_slot']*100:.2f}%)")
        all_res[label] = wr

    # Final report
    print("\n\n" + "═" * 92)
    print("  FINAL — FIXED slots test")
    print("═" * 92)
    print()
    print(f"  {'Config':<20} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Avg':>10} {'N':>8}")
    print(f"  {'─'*20} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*8}")

    for name, _, _, _ in CONFIGS:
        ss = [all_res.get(y, {}).get(name, {}).get('sharpe')
              for y in WINDOWS]
        valid = [s for s in ss if s is not None]
        n = sum(all_res.get(y, {}).get(name, {}).get('n', 0)
                for y in WINDOWS)
        if not valid:
            continue
        avg = float(np.mean(valid))

        def f(x): return f"{x:>10.3f}" if x is not None else f"{'—':>10}"
        print(f"  {name:<20} {f(ss[0])} {f(ss[1])} {f(ss[2])} "
              f"{avg:>10.3f} {n:>8}")

    os.makedirs("results", exist_ok=True)
    with open(f"results/sell_slots_fixed_{args.tf}.json", "w") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: results/sell_slots_fixed_{args.tf}.json")


if __name__ == "__main__":
    main()
