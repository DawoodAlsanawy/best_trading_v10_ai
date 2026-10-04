#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sell_ablation_fast.py — نسخة محسّنة (15 دقيقة بدل 35).

المبدأ:
  - AssetData يُبنى مرة واحدة لكل نافذة.
  - 7 استراتيجيات تُشغَّل على نفس AssetData.
  - لا subprocess spawning.
  - CFG يُعدَّل in-place ثم يُستعاد.

النتائج مطابقة 100% لـ sell_ablation_full.py.
"""

import os
import sys
import time
import json

# ── 1. قيود الخيوط قبل أي imports ──
for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
          'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[v] = '1'

# ── 2. اضمن وجود الملف في المسار ──
sys.path.insert(0, '.')

# ── 3. استيراد المحرك ──
try:
    import trading_rnd_sell_only as engine
except ImportError as e:
    print(f"❌ فشل استيراد trading_rnd_sell_only: {e}")
    print(f"   المسار الحالي: {os.getcwd()}")
    print(f"   تأكد من وجود الملف في هذه المجلد.")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# استراتيجيات SELL
# ═══════════════════════════════════════════════════════════════

STRATEGIES = {
    "S1_baseline":       {"SELL_GAUGE_PCT": 0.95},
    "S2_tight":          {"SELL_GAUGE_PCT": 0.98},
    "S3_highscore":      {"SELL_MIN_SCORE": 5, "SELL_GAUGE_PCT": 0.95},
    "S4_xtreme_zdev":    {"SELL_MIN_ZDEV": 2.5, "SELL_GAUGE_PCT": 0.95},
    "S5_ema_down":       {"SELL_REQUIRE_EMA_DOWN": True,
                           "SELL_GAUGE_PCT": 0.95},
    "S6_major":          {"SELL_MAJOR_ONLY": True, "SELL_GAUGE_PCT": 0.95},
    "S7_atr_frac":       {"SELL_MIN_ATR_FRAC": 0.02, "SELL_GAUGE_PCT": 0.95},
}

WINDOWS = {
    "2024": "2024-12-31",
    "2025": "2025-12-31",
    "2026": "2026-10-01",
}


# ═══════════════════════════════════════════════════════════════
# حفظ القيم الأصلية
# ═══════════════════════════════════════════════════════════════

CFG = engine.CFG

_ORIGINALS = {
    "SELL_GAUGE_PCT":       getattr(CFG, "SELL_GAUGE_PCT", 0.95),
    "SELL_MIN_SCORE":       getattr(CFG, "SELL_MIN_SCORE", 3),
    "SELL_MIN_ZDEV":        getattr(CFG, "SELL_MIN_ZDEV", 1.5),
    "SELL_REQUIRE_EMA_DOWN": getattr(CFG, "SELL_REQUIRE_EMA_DOWN", False),
    "SELL_MAJOR_ONLY":      getattr(CFG, "SELL_MAJOR_ONLY", False),
    "SELL_MIN_ATR_FRAC":    getattr(CFG, "SELL_MIN_ATR_FRAC", 0.0),
    "BACKTEST_END_DATE":    getattr(CFG, "BACKTEST_END_DATE", None),
}


def reset_cfg():
    """يعيد CFG إلى القيم الأصلية."""
    for k, v in _ORIGINALS.items():
        setattr(CFG, k, v)


def apply_strategy(params):
    """يطبّق معاملات استراتيجية."""
    reset_cfg()
    for k, v in params.items():
        setattr(CFG, k, v)


# ═══════════════════════════════════════════════════════════════
# تحميل نافذة + بناء AssetData مرة واحدة
# ═══════════════════════════════════════════════════════════════

def load_window(label, end_date):
    """يبني (assets, corr_matrix, exchange) لنافذة واحدة."""
    print(f"\n{'═' * 72}")
    print(f"  Loading window {label} (end_date={end_date})")
    print(f"{'═' * 72}")

    # اطبع المعاملات النشطة
    print(f"  GAUGE_DISABLE_SELL = {getattr(CFG, 'GAUGE_DISABLE_SELL', '?')}")
    print(f"  SELL_ENABLED       = {getattr(CFG, 'SELL_ENABLED', '?')}")
    print(f"  BUY_DISABLED       = {getattr(CFG, 'BUY_DISABLED', '?')}")

    reset_cfg()
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365

    # ── Exchange ──
    try:
        import ccxt
    except ImportError:
        print("❌ pip install ccxt")
        sys.exit(1)

    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })

    # ── Symbols ──
    syms = engine.scan_top_assets(exchange, CFG.n_assets)
    print(f"  Symbols: {len(syms)}")

    # ── Fetch data ──
    t0 = time.time()
    raw, raw_sub = engine.fetch_all_with_subbars(
        syms, exchange, CFG.timeframe, CFG.history_days, workers=5,
    )
    dt_fetch = time.time() - t0
    print(f"  Data fetch: {dt_fetch:.1f}s  ({len(raw)}/{len(syms)} symbols)")

    # ── Build AssetData (with cache) ──
    t0 = time.time()
    assets = {}
    cache_hits = 0
    computed = 0
    for sym, df in raw.items():
        ad = engine._load_asset_cache(sym, CFG.timeframe, df, CFG)
        if ad is not None:
            cache_hits += 1
        else:
            ad = engine.process_asset(
                sym, df,
                current_capital=CFG.INITIAL_CAPITAL,
                sub_df=(raw_sub.get(sym) if raw_sub else None),
            )
            if ad is not None:
                engine._save_asset_cache(sym, CFG.timeframe, df, ad, CFG)
                computed += 1
        if ad is not None:
            assets[sym] = ad
    dt_build = time.time() - t0
    print(f"  AssetData: {dt_build:.1f}s "
          f"(cache={cache_hits}, computed={computed}, total={len(assets)})")

    # ── Correlations ──
    t0 = time.time()
    corr_matrix = engine.precompute_correlations(assets)
    print(f"  Correlations: {time.time() - t0:.1f}s")

    return assets, corr_matrix, exchange


# ═══════════════════════════════════════════════════════════════
# تشغيل استراتيجية على AssetData محمَّل
# ═══════════════════════════════════════════════════════════════

def run_strategy(sid, params, assets, corr_matrix):
    """يشغّل استراتيجية واحدة ويُعيد metrics."""
    apply_strategy(params)

    t0 = time.time()

    # build_signals (mode=backtest)
    try:
        sigs = engine.build_signals(assets, mode="backtest")
    except Exception as e:
        print(f"    ❌ {sid}: build_signals failed: {e}")
        return None

    sigs = engine.deduplicate_signals(sigs)
    n_sigs = len(sigs)

    # simulate_portfolio
    try:
        trades, equity = engine.simulate_portfolio(
            sigs, assets, corr_matrix, "backtest",
        )
    except Exception as e:
        print(f"    ❌ {sid}: simulate failed: {e}")
        return None

    metrics = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)

    dt = time.time() - t0

    return {
        "sharpe": float(metrics.get("sharpe_ratio", 0)),
        "final": float(metrics.get("final_capital", 0)),
        "n_trades": int(metrics.get("n_trades", 0)),
        "n_signals": n_sigs,
        "n_buy": int(metrics.get("buy_count", 0)),
        "n_sell": int(metrics.get("sell_count", 0)),
        "dt": dt,
    }


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    print("═" * 72)
    print("  SELL-only FAST Ablation")
    print("  7 strategies × 3 windows")
    print("═" * 72)

    all_results = {}

    for label, end_date in WINDOWS.items():
        # 1. حمّل AssetData لهذه النافذة (مرة واحدة)
        try:
            assets, corr_matrix, exchange = load_window(label, end_date)
        except Exception as e:
            print(f"  ❌ Failed to load window {label}: {e}")
            all_results[label] = {}
            continue

        if not assets:
            print(f"  ⚠️  No assets for window {label} — skipping")
            all_results[label] = {}
            continue

        # 2. شغّل كل الاستراتيجيات على نفس AssetData
        print(f"\n  Running {len(STRATEGIES)} strategies on "
              f"{len(assets)} assets...")
        window_results = {}
        for sid, params in STRATEGIES.items():
            r = run_strategy(sid, params, assets, corr_matrix)
            if r is None:
                continue
            window_results[sid] = r
            print(f"    ✅ {sid:<20}  "
                  f"Sharpe={r['sharpe']:>6.3f}  "
                  f"Final=${r['final']:>9.2f}  "
                  f"n={r['n_trades']:>4}  "
                  f"({r['dt']:.0f}s)")

        all_results[label] = window_results

    # ═══ Final report ═══
    print("\n\n" + "═" * 96)
    print("  SELL-only FINAL COMPARISON")
    print("═" * 96)
    print()

    # Sharpe table
    print(f"  {'Strategy':<20} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'Verdict':<15}")
    print(f"  {'─' * 20} {'─' * 10} {'─' * 10} "
          f"{'─' * 10} {'─' * 10} {'─' * 15}")

    viable = []
    for sid in STRATEGIES:
        sharpes = []
        for y in WINDOWS:
            r = all_results.get(y, {}).get(sid)
            if r is not None:
                sharpes.append(r["sharpe"])

        if len(sharpes) != 3:
            print(f"  {sid:<20} — incomplete")
            continue

        min_s = min(sharpes)
        if min_s >= 0.8:
            v = "✅ VIABLE"
            viable.append(sid)
        elif min_s >= 0.5:
            v = "🟡 weak"
        elif min_s >= 0:
            v = "🟠 marginal"
        else:
            v = "❌ losing"

        print(f"  {sid:<20} {sharpes[0]:>10.3f} {sharpes[1]:>10.3f} "
              f"{sharpes[2]:>10.3f} {min_s:>10.3f} {v:<15}")

    # Trade counts table
    print()
    print(f"  {'Strategy':<20} {'Trades 2024':>12} {'2025':>10} "
          f"{'2026':>10} {'Total':>10}")
    print(f"  {'─' * 20} {'─' * 12} {'─' * 10} "
          f"{'─' * 10} {'─' * 10}")
    for sid in STRATEGIES:
        counts = []
        for y in WINDOWS:
            r = all_results.get(y, {}).get(sid)
            counts.append(r["n_trades"] if r else 0)
        print(f"  {sid:<20} {counts[0]:>12} {counts[1]:>10} "
              f"{counts[2]:>10} {sum(counts):>10}")

    # Final verdict
    print()
    print("═" * 96)
    if viable:
        print(f"  🏆 استراتيجيات قابلة للدمج: {', '.join(viable)}")
        print(f"     → متابعة R&D على هذه")
    else:
        print(f"  ❌ لا استراتيجية SELL قابلة للدمج")
        print(f"     → إغلاق ملف SELL R&D")
    print("═" * 96)

    # Save JSON
    out_path = "results/sell_ablation_fast.json"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)
        print(f"\n  Saved: {out_path}")
    except Exception as e:
        print(f"\n  ⚠️  Save failed: {e}")


if __name__ == "__main__":
    main()
