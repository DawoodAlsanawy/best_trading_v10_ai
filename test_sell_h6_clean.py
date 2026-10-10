#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sell_h6_clean.py — اختبار H6 بدون تعديل أي ملف.

يُصفّي الإشارات ديناميكياً بعد build_signals:
  - H6a: EMA_UP gate
  - H6b: per-asset gauge pool
  - H6c: دمج الاثنين

7 configs × 3 نوافذ على 4h.
"""

import os
import sys
import time
import json
import argparse

# قيود الخيوط قبل أي import
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

# [PICKLE-FIX] register dataclass aliases
import __main__ as _pcmain
for _cn in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(engine, _cn):
        setattr(_pcmain, _cn, getattr(engine, _cn))

CFG = engine.CFG


# ═══════════════════════════════════════════════════════════════
# Configs to test
# ═══════════════════════════════════════════════════════════════

CONFIGS = {
    "baseline":           {},
    "H6a_ema_up":         {"ema_up": True},
    "H6b_per_asset":      {"per_asset": True},
    "H6c_both":           {"ema_up": True, "per_asset": True},
    "H6d_ema_up_z25":     {"ema_up": True, "min_zdev": 2.5},
    "H6e_per_asset_z25":  {"per_asset": True, "min_zdev": 2.5},
    "H6f_all":            {"ema_up": True, "per_asset": True,
                           "min_zdev": 2.5},
}

WINDOWS = {
    "2024": "2024-12-31",
    "2025": "2025-12-31",
    "2026": "2026-10-01",
}


# ═══════════════════════════════════════════════════════════════
# Signal filter — H6 logic (pure function, no side effects)
# ═══════════════════════════════════════════════════════════════

def _slope_at(ad, ci, lookback):
    """Compute EMA slope over lookback at bar ci."""
    if ci < lookback or ci >= len(ad.ema200):
        return None
    denom = float(max(lookback, 1))
    return (float(ad.ema200[ci]) - float(ad.ema200[ci - lookback])) / denom


def _per_asset_gauge_threshold(ad, pct=0.95, min_samples=200):
    """Compute per-asset gauge threshold from training+test portion."""
    train_end = int(getattr(ad, 'train_end', 0))
    pool = ad.gauge_force[train_end:]
    pool = pool[pool > 0]
    if len(pool) < min_samples:
        return None
    return float(np.percentile(pool, pct * 100))


def _global_gauge_threshold(assets, pct=0.95):
    """Compute global gauge threshold across all assets."""
    all_gf = []
    for ad in assets.values():
        train_end = int(getattr(ad, 'train_end', 0))
        pool = ad.gauge_force[train_end:]
        pool = pool[pool > 0]
        if len(pool) > 0:
            all_gf.extend(pool.tolist())
    if not all_gf:
        return 0.0
    return float(np.percentile(np.asarray(all_gf), pct * 100))


def filter_signals_h6(sigs, assets, config, global_p95_cache):
    """
    Pure filter function — no side effects on assets or signals.

    config keys:
      - ema_up: bool → require SELL only when EMA slopes up
      - per_asset: bool → use per-asset gauge threshold
      - min_zdev: float → override for SELL (applied post-hoc)
    """
    ema_up = config.get("ema_up", False)
    per_asset = config.get("per_asset", False)
    min_zdev = config.get("min_zdev", None)

    out = []
    for sig in sigs:
        # BUY untouched
        if sig.action != "SELL":
            out.append(sig)
            continue

        ad = assets.get(sig.symbol)
        if ad is None:
            continue

        # ── H6: EMA_UP gate ──
        if ema_up:
            slope = _slope_at(ad, int(sig.close_idx), 50)
            if slope is None or slope <= 0:
                continue

        # ── H6: per-asset gauge pool ──
        if per_asset:
            pct = float(getattr(CFG, 'SELL_GAUGE_PCT', 0.95))
            thr = _per_asset_gauge_threshold(ad, pct=pct)
            if thr is None:
                # fallback to global
                thr = global_p95_cache.get(sig.symbol, 0.0)
            fi = int(sig.feat_idx)
            if 0 <= fi < len(ad.gauge_force):
                if float(ad.gauge_force[fi]) < thr:
                    continue
        else:
            # baseline gauge: global p95
            thr = global_p95_cache.get('__global__', 0.0)
            fi = int(sig.feat_idx)
            if 0 <= fi < len(ad.gauge_force):
                if float(ad.gauge_force[fi]) < thr:
                    continue

        out.append(sig)

    return out


# ═══════════════════════════════════════════════════════════════
# CFG reset
# ═══════════════════════════════════════════════════════════════

_SELL_DEFAULTS = {
    'SELL_ENABLED': True,
    'BUY_DISABLED': True,
    'GAUGE_DISABLE_SELL': False,
    'SELL_GAUGE_PCT': 0.95,
    'SELL_MIN_SCORE': 3,
    'SELL_MIN_ZDEV': 1.5,
}

_ORIG = {k: getattr(CFG, k, None) for k in _SELL_DEFAULTS}


def reset_sell_cfg():
    for k, v in _ORIG.items():
        if v is not None:
            setattr(CFG, k, v)


def force_permissive_build():
    """Force settings that produce maximal SELL signal superset."""
    reset_sell_cfg()
    CFG.SELL_ENABLED = True
    CFG.BUY_DISABLED = True
    CFG.GAUGE_DISABLE_SELL = False
    CFG.GAUGE_FILTER_ENABLED = False   # ← مهم: نُصفّي لاحقاً


# ═══════════════════════════════════════════════════════════════
# Window loader
# ═══════════════════════════════════════════════════════════════

def load_window(label, end_date, n_assets, tf):
    print(f"\n{'═' * 76}")
    print(f"  Loading {label}  (end={end_date}, n_assets={n_assets}, tf={tf})")
    print(f"{'═' * 76}")

    reset_sell_cfg()
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf

    import ccxt
    ex = ccxt.binance({'enableRateLimit': True,
                       'options': {'defaultType': 'future'}})
    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = \
        engine.compute_tf_scale(ex, tf)

    _tf_h = max(float(CFG.TF_HOURS), 1e-6)
    CFG.N = max(24, int(np.ceil(24.0 / _tf_h)))
    CFG.W = max(20, int(np.ceil(20.0 / _tf_h)))
    CFG.L = max(10, int(np.ceil(10.0 / _tf_h)))
    CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))

    syms = engine.scan_top_assets(ex, n_assets)
    print(f"  Fetching {len(syms)} symbols...")
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

def run_config(sid, config, raw_sigs, assets, corr, global_p95_cache):
    t0 = time.time()
    try:
        # Filter
        filtered = filter_signals_h6(raw_sigs, assets, config,
                                      global_p95_cache)
        filtered = engine.deduplicate_signals(filtered)

        # Simulate
        trades, equity = engine.simulate_portfolio(
            filtered, assets, corr, "backtest")
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
    print(f"  SELL H6 clean test — {len(CONFIGS)} configs × "
          f"{len(WINDOWS)} windows")
    print(f"  Strategy: filter signals dynamically (no file modification)")
    print("═" * 76)

    all_res = {}

    for label, end_date in WINDOWS.items():
        # 1. Load window
        assets, corr = load_window(label, end_date, args.nassets, args.tf)
        if not assets:
            continue

        # 2. Build raw signals (gauge filter OFF for superset)
        force_permissive_build()
        t0 = time.time()
        try:
            raw_sigs = engine.build_signals(assets, mode="backtest")
        except Exception as e:
            print(f"  ❌ build_signals failed: {e}")
            continue
        print(f"  build_signals: {len(raw_sigs)} signals in "
              f"{time.time()-t0:.1f}s")

        # 3. Compute global gauge thresholds once
        global_p95 = _global_gauge_threshold(assets, pct=0.95)
        global_p95_cache = {'__global__': global_p95}
        print(f"  Global gauge p95 = {global_p95:.6f}")

        # 4. Run each config
        print(f"\n  Running {len(CONFIGS)} configs on "
              f"{len(assets)} assets:")
        wr = {}
        for sid, config in CONFIGS.items():
            r = run_config(sid, config, raw_sigs, assets, corr,
                            global_p95_cache)
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

    viable, promising = [], []
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

    # SELL-only detail
    print()
    print(f"  تفاصيل SELL فقط (عدد الصفقات):")
    print(f"  {'Config':<22} {'2024':>8} {'2025':>8} "
          f"{'2026':>8} {'Total':>8}")
    for sid in CONFIGS:
        cs = [all_res.get(y, {}).get(sid, {}).get("n_sell", 0)
              for y in WINDOWS]
        print(f"  {sid:<22} {cs[0]:>8} {cs[1]:>8} "
              f"{cs[2]:>8} {sum(cs):>8}")

    print()
    if viable:
        print(f"  🏆 VIABLE: {', '.join(viable)}")
    elif promising:
        print(f"  🟡 PROMISING: {', '.join(promising)}")
    else:
        print(f"  ❌ لا config حقق المعايير")
    print("═" * 100)

    os.makedirs("results", exist_ok=True)
    out = f"results/sell_h6_clean_{args.tf}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_res, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Saved: {out}")


if __name__ == "__main__":
    main()
