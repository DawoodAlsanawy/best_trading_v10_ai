#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sell_h6.py — اختبار فرضية H6 مع per-asset pool.

7 configs × 3 نوافذ = 21 backtest، بـ AssetData cache مُعاد استخدامه.

المقارنة الرئيسية:
  - baseline: العتبة العالمية (سلوك حالي)
  - H6a-h6f: تجارب مختلفة على EMA_UP و per-asset pool
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

# ══ [PICKLE-FIX] — يُسجّل dataclass aliases في __main__ ══
import __main__ as _pcmain
for _cn in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(engine, _cn):
        setattr(_pcmain, _cn, getattr(engine, _cn))

CFG = engine.CFG


# ═══════════════════════════════════════════════════════════════
# Test configs
# ═══════════════════════════════════════════════════════════════

CONFIGS = {
    "baseline":           {},                                       # current behavior
    "H6a_ema_up":         {"SELL_REQUIRE_EMA_UP": True},
    "H6b_ema_up_zdev25":  {"SELL_REQUIRE_EMA_UP": True,
                           "SELL_MIN_ZDEV": 2.5},
    "H6c_per_asset":      {"SELL_GAUGE_POOL_PER_ASSET": True},
    "H6d_per_asset_z25":  {"SELL_GAUGE_POOL_PER_ASSET": True,
                           "SELL_MIN_ZDEV": 2.5},
    "H6e_ema_up_per":     {"SELL_REQUIRE_EMA_UP": True,
                           "SELL_GAUGE_POOL_PER_ASSET": True},
    "H6f_all_combined":   {"SELL_REQUIRE_EMA_UP": True,
                           "SELL_GAUGE_POOL_PER_ASSET": True,
                           "SELL_MIN_ZDEV": 2.5},
}

WINDOWS = {
    "2024": "2024-12-31",
    "2025": "2025-12-31",
    "2026": "2026-10-01",
}


# ═══════════════════════════════════════════════════════════════
# CFG reset utilities
# ═══════════════════════════════════════════════════════════════

_TUNABLE = [
    'SELL_GAUGE_PCT', 'SELL_MIN_SCORE', 'SELL_MIN_ZDEV',
    'SELL_REQUIRE_EMA_DOWN', 'SELL_MAJOR_ONLY', 'SELL_MIN_ATR_FRAC',
    'SELL_REQUIRE_ORDER_EMERGING', 'SELL_REQUIRE_DECELERATING',
    'SELL_REQUIRE_DOWNWARD_FORCE', 'SELL_REQUIRE_LOW_FRICTION',
    'SELL_FRICTION_PCT', 'SELL_SL_WIDEN_MULT',
    'SELL_REQUIRE_EMA_UP', 'SELL_EMA_UP_LOOKBACK',
    'SELL_GAUGE_POOL_PER_ASSET', 'SELL_GAUGE_POOL_MIN_SAMPLES',
]

_DEFAULTS = {
    'SELL_GAUGE_PCT': 0.95,
    'SELL_MIN_SCORE': 3,
    'SELL_MIN_ZDEV': 1.5,
    'SELL_REQUIRE_EMA_DOWN': False,
    'SELL_MAJOR_ONLY': False,
    'SELL_MIN_ATR_FRAC': 0.0,
    'SELL_REQUIRE_ORDER_EMERGING': False,
    'SELL_REQUIRE_DECELERATING': False,
    'SELL_REQUIRE_DOWNWARD_FORCE': False,
    'SELL_REQUIRE_LOW_FRICTION': False,
    'SELL_FRICTION_PCT': 0.25,
    'SELL_SL_WIDEN_MULT': 1.0,
    'SELL_REQUIRE_EMA_UP': False,
    'SELL_EMA_UP_LOOKBACK': 50,
    'SELL_GAUGE_POOL_PER_ASSET': False,
    'SELL_GAUGE_POOL_MIN_SAMPLES': 200,
}


def reset_cfg():
    for k, v in _DEFAULTS.items():
        try:
            setattr(CFG, k, v)
        except Exception:
            pass


def apply_config(params):
    reset_cfg()
    for k, v in params.items():
        setattr(CFG, k, v)


# ═══════════════════════════════════════════════════════════════
# Load window
# ═══════════════════════════════════════════════════════════════

def load_window(label, end_date, n_assets, tf):
    print(f"\n{'═' * 76}")
    print(f"  Loading window {label}  (end={end_date}, n_assets={n_assets})")
    print(f"{'═' * 76}")

    reset_cfg()
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf

    import ccxt
    ex = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })

    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = \
        engine.compute_tf_scale(ex, tf)

    # TF-unified windows
    _tf_h = max(float(CFG.TF_HOURS), 1e-6)
    CFG.N = max(24, int(np.ceil(24.0 / _tf_h)))
    CFG.W = max(20, int(np.ceil(20.0 / _tf_h)))
    CFG.L = max(10, int(np.ceil(10.0 / _tf_h)))
    CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))

    syms = engine.scan_top_assets(ex, n_assets)
    print(f"  Fetching {len(syms)} symbols ...")
    t0 = time.time()
    raw, raw_sub = engine.fetch_all_with_subbars(
        syms, ex, tf, CFG.history_days, workers=5)
    print(f"  Fetch: {time.time()-t0:.1f}s ({len(raw)} symbols)")

    t0 = time.time()
    assets = {}
    hits, comp = 0, 0
    for sym, df in raw.items():
        ad = engine._load_asset_cache(sym, tf, df, CFG)
        if ad is not None:
            hits += 1
        else:
            ad = engine.process_asset(
                sym, df,
                current_capital=CFG.INITIAL_CAPITAL,
                sub_df=(raw_sub.get(sym) if raw_sub else None))
            if ad is not None:
                engine._save_asset_cache(sym, tf, df, ad, CFG)
                comp += 1
        if ad is not None:
            assets[sym] = ad
    print(f"  AssetData: {time.time()-t0:.1f}s "
          f"(cache={hits}, computed={comp}, valid={len(assets)})")

    corr = engine.precompute_correlations(assets)
    return assets, corr


# ═══════════════════════════════════════════════════════════════
# Run one config
# ═══════════════════════════════════════════════════════════════

def run_config(sid, params, assets, corr):
    apply_config(params)
    t0 = time.time()
    try:
        sigs = engine.build_signals(assets, mode="backtest")
        sigs = engine.deduplicate_signals(sigs)
        trades, equity = engine.simulate_portfolio(
            sigs, assets, corr, "backtest")
        m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    except Exception as e:
        import traceback
        print(f"    ERR {sid}: {e}")
        traceback.print_exc()
        return None

    return {
        "sharpe": float(m.get("sharpe_ratio", 0)),
        "final": float(m.get("final_capital", 0)),
        "n": int(m.get("n_trades", 0)),
        "n_sell": int(m.get("sell_count", 0)),
        "n_buy": int(m.get("buy_count", 0)),
        "wr": float(m.get("win_rate", 0)),
        "pf": float(m.get("profit_factor", 0)),
        "dd": float(m.get("max_drawdown_pct", 0)),
        "dt": time.time() - t0,
    }


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h', choices=['1h', '4h'])
    ap.add_argument('--nassets', type=int, default=100)
    args = ap.parse_args()

    print("═" * 76)
    print(f"  SELL H6 test — {len(CONFIGS)} configs × "
          f"{len(WINDOWS)} windows on {args.tf}")
    print("═" * 76)

    all_res = {}

    for label, end_date in WINDOWS.items():
        assets, corr = load_window(label, end_date, args.nassets, args.tf)
        if not assets:
            print(f"  ⚠️  Window {label} has no assets")
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
                  f"Sharpe={r['sharpe']:>8.3f}  "
                  f"Final=${r['final']:>8.2f}  "
                  f"n={r['n']:>4} (B={r['n_buy']:>4},S={r['n_sell']:>3})  "
                  f"({r['dt']:.0f}s)")
        all_res[label] = wr

    # ═══ Final Report ═══
    print("\n\n" + "═" * 100)
    print("  H6 FINAL — SELL with EMA_UP + per-asset pool")
    print("═" * 100)
    print()
    print(f"  {'Config':<22} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'SELLs':>7} {'Verdict':<15}")
    print(f"  {'─'*22} {'─'*10} {'─'*10} {'─'*10} {'─'*10} "
          f"{'─'*7} {'─'*15}")

    viable = []
    promising = []
    for sid in CONFIGS:
        ss, tot_s = [], 0
        for y in WINDOWS:
            r = all_res.get(y, {}).get(sid)
            if r is None:
                ss = []; break
            ss.append(r["sharpe"])
            tot_s += r["n_sell"]
        if len(ss) != 3:
            print(f"  {sid:<22} — incomplete")
            continue
        mn = min(ss)
        if mn >= 0.8 and tot_s >= 300:
            v = "✅ VIABLE"; viable.append(sid)
        elif mn >= 0.5:
            v = "🟡 promising"; promising.append(sid)
        elif mn >= 0:
            v = "🟠 marginal"
        else:
            v = "❌ losing"
        print(f"  {sid:<22} {ss[0]:>10.3f} {ss[1]:>10.3f} "
              f"{ss[2]:>10.3f} {mn:>10.3f} {tot_s:>7} {v:<15}")

    # ═══ SELL-only Detail Table ═══
    print()
    print(f"  تفاصيل SELL فقط (عدد الصفقات):")
    print(f"  {'Config':<22} {'2024':>8} {'2025':>8} "
          f"{'2026':>8} {'Total':>8}")
    for sid in CONFIGS:
        cs = []
        for y in WINDOWS:
            r = all_res.get(y, {}).get(sid)
            cs.append(r["n_sell"] if r else 0)
        print(f"  {sid:<22} {cs[0]:>8} {cs[1]:>8} "
              f"{cs[2]:>8} {sum(cs):>8}")

    print()
    if viable:
        print(f"  🏆 VIABLE: {', '.join(viable)}")
        print(f"     → {len(viable)} config(s) تجاوزت المعايير!")
        print(f"     → يحتاج اختبار out-of-sample قبل الدمج")
    elif promising:
        print(f"  🟡 PROMISING: {', '.join(promising)}")
        print(f"     → يظهر حافة في 2024/2025، نُراقب 2026")
    else:
        print(f"  ❌ لا config حقق المعايير")

    print("═" * 100)

    # Save
    os.makedirs("results", exist_ok=True)
    out = f"results/sell_h6_{args.tf}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
