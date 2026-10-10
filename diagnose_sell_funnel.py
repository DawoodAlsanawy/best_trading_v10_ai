#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_sell_funnel.py — قياس فقدان إشارات SELL.

لكل شمعة، نحسب:
  1. كم إشارة SELL "خام" موجودة (z_dev>1.5 فقط)
  2. كم نجت من P_activation
  3. كم نجت من MIN_SCORE
  4. كم نجت من gauge filter
  5. كم قبِلها deduplicate
  6. كم نفّذها simulate (slots + cooldown + correlation)

النتيجة: جدول فقدان واضح.
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
    CFG.SELL_ENABLED = True
    CFG.BUY_DISABLED = True   # SELL-only
    CFG.GAUGE_DISABLE_SELL = False
    CFG.GAUGE_FILTER_ENABLED = False  # نقيس الفقدان بدونه
    CFG.SELL_GAUGE_PCT = 0.95
    CFG.SELL_MIN_SCORE = 3
    CFG.SELL_MIN_ZDEV = 1.5
    CFG.SELL_REQUIRE_EMA_DOWN = False
    CFG.SELL_MAJOR_ONLY = False
    CFG.SELL_MIN_ATR_FRAC = 0.0
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


def funnel_analysis(assets):
    """يقيس عدد الإشارات في كل مرحلة من الفلاتر."""
    counters = {
        'total_bars': 0,
        'zdev_ok': 0,
        'p_act_ok': 0,
        'score_ok': 0,
        'gauge_filter_ok': 0,
        'final_signals': 0,
    }

    for sym, ad in assets.items():
        n = len(ad.score)
        tr_end = int(ad.train_end)
        for fi in range(tr_end + 1, n):
            ci = ad.feat_start + fi
            if ci >= len(ad.closes) - 1:
                continue
            counters['total_bars'] += 1

            p = ad.closes[ci]
            if p <= 0:
                continue

            # 1. Z_DEV direction
            _z_win = ad.closes[max(0, ci - CFG.N): ci]
            if len(_z_win) < 2:
                continue
            _z_mu = float(np.mean(_z_win))
            _z_sd = float(np.std(_z_win))
            if _z_sd <= 1e-12:
                continue
            _z_dev = (p - _z_mu) / _z_sd
            if _z_dev <= 1.5:   # SELL requires z_dev > 1.5
                continue
            counters['zdev_ok'] += 1

            # 2. Boltzmann activation
            geo_accel = float(ad.geodesic_accel[fi])
            fric_val = float(ad.friction[fi]) + 1e-6
            T_info = float(ad.T_info[fi])
            P_activation = np.exp(-fric_val / ((abs(geo_accel) + 1e-9) * T_info))
            if P_activation < 0.35:
                continue
            counters['p_act_ok'] += 1

            # 3. MIN_SCORE
            if ad.score[fi] < CFG.SELL_MIN_SCORE:
                continue
            counters['score_ok'] += 1

            # 4. Gauge filter (OFF حالياً — كل الإشارات تمر)
            # لو الفلتر مفعّل، نطبّقه هنا
            counters['gauge_filter_ok'] += 1

            # 5. This signal survives to build_signals output
            counters['final_signals'] += 1

    return counters


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h')
    ap.add_argument('--nassets', type=int, default=100)
    args = ap.parse_args()

    WINDOWS = [
        ("2024", "2024-12-31"),
        ("2025", "2025-12-31"),
        ("2026", "2026-10-01"),
    ]

    print("═" * 92)
    print(f"  SELL funnel analysis — {args.tf}, n_assets={args.nassets}")
    print("═" * 92)
    print()

    all_counts = {}
    for label, end_date in WINDOWS:
        print(f"\n{'─' * 92}")
        print(f"  Window {label}  (end={end_date})")
        print(f"{'─' * 92}")

        force_config(end_date, args.tf, args.nassets)
        t0 = time.time()
        assets = load_window(end_date, args.nassets, args.tf)
        print(f"  Loaded {len(assets)} assets in {time.time()-t0:.0f}s")

        t0 = time.time()
        counters = funnel_analysis(assets)
        all_counts[label] = counters
        print(f"  Funnel computed in {time.time()-t0:.1f}s")

        print()
        print(f"  ▶ SELL signal funnel:")
        base = counters['total_bars']
        prev = base
        for stage in ['total_bars', 'zdev_ok', 'p_act_ok',
                      'score_ok', 'gauge_filter_ok', 'final_signals']:
            cnt = counters[stage]
            pct_total = 100.0 * cnt / max(base, 1)
            loss = prev - cnt
            loss_pct = 100.0 * loss / max(prev, 1) if prev > 0 else 0
            print(f"    {stage:<20} {cnt:>9}  "
                  f"({pct_total:>5.2f}% من الإجمالي, "
                  f"خسرنا {loss} = {loss_pct:.1f}% من المرحلة السابقة)")
            prev = cnt

        # الآن، كم منها نجح في simulate؟
        print()
        print(f"  ▶ Now run actual simulation...")
        CFG.GAUGE_FILTER_ENABLED = False
        sigs = engine.build_signals(assets, mode="backtest")
        sigs = engine.deduplicate_signals(sigs)
        corr = engine.precompute_correlations(assets)
        trades, equity = engine.simulate_portfolio(
            sigs, assets, corr, "backtest")
        m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)

        n_sell_trades = m.get('sell_count', 0)
        n_signals_in = len(sigs)

        print(f"    Signals into simulate: {n_signals_in}")
        print(f"    Trades executed:       {n_sell_trades}")
        if n_signals_in > 0:
            pct_exec = 100.0 * n_sell_trades / n_signals_in
            print(f"    Execution rate:        {pct_exec:.1f}%")

    # ═══ Final Summary ═══
    print("\n\n" + "═" * 92)
    print("  FINAL SUMMARY — SELL signal loss across pipeline")
    print("═" * 92)
    print()
    print(f"  {'Stage':<20} "
          f"{'2024':>12} {'2025':>12} {'2026':>12}")
    print(f"  {'─'*20} {'─'*12} {'─'*12} {'─'*12}")
    for stage in ['total_bars', 'zdev_ok', 'p_act_ok',
                  'score_ok', 'gauge_filter_ok', 'final_signals']:
        row = [str(all_counts.get(y, {}).get(stage, 0))
               for y, _ in WINDOWS]
        print(f"  {stage:<20} {row[0]:>12} {row[1]:>12} {row[2]:>12}")

    os.makedirs("results", exist_ok=True)
    with open("results/sell_funnel.json", "w") as f:
        json.dump(all_counts, f, indent=2)

    print()
    print("═" * 92)
    print("  التفسير:")
    print("═" * 92)
    print("""
  الفلاتر التي تقتل أكبر نسبة = حيث يجب التدخل.

  التوصيات حسب النتيجة:
  - إذا zdev_ok صغير: z_dev>1.5 صارم جداً لـ SELL → خفّف
  - إذا p_act خسر كثيراً: P_activation صارمة → اختلف مع SELL
  - إذا score خسر كثيراً: MIN_SCORE صارم → خفّف لـ SELL
  - إذا final_signals كبير لكن trades صغير: slots/cooldown
""")


if __name__ == "__main__":
    main()
