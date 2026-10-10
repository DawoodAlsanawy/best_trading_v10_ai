#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_signed_flow_v2.py — تشخيص signed_flow (نسخة مُصلَحة).

الإصلاحات:
  1. لا _ORIG restore — ضبط مباشر
  2. gauge_filter OFF — الحد الأقصى من الصفقات
  3. BUY+SELL enabled — للمقارنة الكاملة
  4. يقبل --end-date متعدد لتحليل عبر سنوات
"""

import os
import sys
import time
import json
import argparse
import tempfile

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

import __main__ as _pcmain
for _cn in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(engine, _cn):
        setattr(_pcmain, _cn, getattr(engine, _cn))

CFG = engine.CFG


# ═══════════════════════════════════════════════════════════════
# Force config — no restore, no ambiguity
# ═══════════════════════════════════════════════════════════════

def force_config(end_date, tf, n_assets):
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf

    # ✅ كل من BUY و SELL مُفعَّل
    CFG.SELL_ENABLED = True
    CFG.BUY_DISABLED = False
    CFG.GAUGE_DISABLE_SELL = False

    # ✅ gauge_filter OFF — لا نُفلتر، نريد أقصى عدد من الصفقات
    CFG.GAUGE_FILTER_ENABLED = False

    # ✅ عتبات SELL الأساسية
    CFG.SELL_GAUGE_PCT = 0.95
    CFG.SELL_MIN_SCORE = 3
    CFG.SELL_MIN_ZDEV = 1.5

    # ✅ باقي فلاتر SELL مُطفأة (لمقارنة نظيفة)
    CFG.SELL_REQUIRE_EMA_DOWN = False
    CFG.SELL_MAJOR_ONLY = False
    CFG.SELL_MIN_ATR_FRAC = 0.0
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


# ═══════════════════════════════════════════════════════════════
# signed_flow kernel
# ═══════════════════════════════════════════════════════════════

def _make_signed_flow_kernel():
    try:
        from numba import njit
    except ImportError:
        def njit(*a, **kw):
            if len(a) == 1 and callable(a[0]):
                return a[0]
            return lambda f: f

    @njit(cache=True)
    def _signed_flow(sym_q, rank_map, dyn_k, W):
        n = len(sym_q)
        out = np.zeros(n)
        if n <= W:
            return out

        T_ord = np.zeros((dyn_k, dyn_k))

        for i in range(W, n):
            for a in range(dyn_k):
                for b in range(dyn_k):
                    T_ord[a, b] = 0.0

            for j in range(i - W + 1, i):
                a_orig = sym_q[j - 1]
                b_orig = sym_q[j]
                a_rank = rank_map[a_orig]
                b_rank = rank_map[b_orig]
                T_ord[a_rank, b_rank] += 1.0

            sum_T = 0.0
            for a in range(dyn_k):
                for b in range(dyn_k):
                    sum_T += T_ord[a, b]
            if sum_T > 0.0:
                for a in range(dyn_k):
                    for b in range(dyn_k):
                        T_ord[a, b] /= sum_T

            sf = 0.0
            for a in range(dyn_k):
                for b in range(a + 1, dyn_k):
                    sf += T_ord[a, b] - T_ord[b, a]
            out[i] = sf

        return out

    return _signed_flow


_signed_flow = _make_signed_flow_kernel()


def compute_rank_map(ad):
    km = ad.km
    k = int(km.n_clusters)
    mean_r = km.cluster_centers_[:, 0]
    order = np.argsort(mean_r)
    rank_map = np.zeros(k, dtype=np.int64)
    for rank, orig in enumerate(order):
        rank_map[int(orig)] = int(rank)
    return rank_map


def compute_signed_flow_for_asset(ad):
    rank_map = compute_rank_map(ad)
    sym_q = np.ascontiguousarray(ad.sym_q, dtype=np.int64)
    return _signed_flow(sym_q, rank_map, int(ad.dynamic_k), int(CFG.W))


# ═══════════════════════════════════════════════════════════════
# Load assets
# ═══════════════════════════════════════════════════════════════

def load_window(end_date, n_assets, tf):
    import ccxt
    ex = ccxt.binance({'enableRateLimit': True,
                       'options': {'defaultType': 'future'}})

    syms = engine.scan_top_assets(ex, n_assets)
    print(f"  Fetching {len(syms)} symbols...")
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


# ═══════════════════════════════════════════════════════════════
# Run + collect
# ═══════════════════════════════════════════════════════════════

def run_and_collect(assets):
    tmp_path = tempfile.mktemp(suffix='.jsonl')
    engine._TRADE_LOG_PATH = tmp_path

    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'_meta': True, 'diag': True}) + "\n")

    sigs = engine.build_signals(assets, mode="backtest")
    sigs = engine.deduplicate_signals(sigs)
    corr = engine.precompute_correlations(assets)
    trades, equity = engine.simulate_portfolio(
        sigs, assets, corr, "backtest")

    trades_data = []
    with open(tmp_path, encoding='utf-8') as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get('_meta'):
                continue
            trades_data.append(r)

    try:
        os.remove(tmp_path)
    except Exception:
        pass

    return trades_data, sigs


# ═══════════════════════════════════════════════════════════════
# Analysis
# ═══════════════════════════════════════════════════════════════

def stats(arr):
    a = np.asarray(arr, dtype=np.float64)
    if len(a) == 0:
        return None
    return {
        'n': int(len(a)),
        'mean': float(a.mean()),
        'std': float(a.std()),
        'median': float(np.median(a)),
        'q25': float(np.percentile(a, 25)),
        'q75': float(np.percentile(a, 75)),
    }


def analyze(trades_data, sf_map):
    groups = {('SELL', 'win'): [], ('SELL', 'loss'): [],
              ('BUY', 'win'): [], ('BUY', 'loss'): []}
    pnls = {k: [] for k in groups}
    missing = 0

    for t in trades_data:
        sym = t.get('symbol')
        action = t.get('action')
        pnl = float(t.get('net_pnl') or 0.0)
        fi = int(t.get('feat_idx', -1))

        if sym not in sf_map:
            missing += 1
            continue
        sf = sf_map[sym]
        if fi < 0 or fi >= len(sf):
            missing += 1
            continue

        key = (action, 'win' if pnl > 0 else 'loss')
        if key in groups:
            groups[key].append(float(sf[fi]))
            pnls[key].append(pnl)

    return groups, pnls, missing


def print_group(label, values):
    s = stats(values)
    if s is None:
        print(f"    {label:<14} (empty)")
        return
    print(f"    {label:<14} n={s['n']:>5}  "
          f"mean={s['mean']:>+9.5f}  "
          f"med={s['median']:>+9.5f}  "
          f"q25={s['q25']:>+9.5f}  "
          f"q75={s['q75']:>+9.5f}  "
          f"std={s['std']:>8.5f}")


def t_test(wins, losses):
    if not wins or not losses:
        return None
    w = np.asarray(wins)
    l = np.asarray(losses)
    mw = w.mean(); ml = l.mean()
    sw = w.std(ddof=1) if len(w) > 1 else 0.0
    sl = l.std(ddof=1) if len(l) > 1 else 0.0
    se = np.sqrt(sw**2/len(w) + sl**2/len(l))
    if se <= 1e-12:
        return None
    return {
        'diff': mw - ml,
        't': (mw - ml) / se,
        'mw': mw, 'ml': ml, 'sw': sw, 'sl': sl,
        'nw': len(w), 'nl': len(l),
    }


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h', choices=['1h', '4h'])
    ap.add_argument('--nassets', type=int, default=100)
    ap.add_argument('--end-dates', nargs='+',
                    default=['2024-12-31', '2025-12-31', '2026-10-01'])
    args = ap.parse_args()

    print("═" * 78)
    print(f"  diagnose_signed_flow_v2 — tf={args.tf}  "
          f"windows={args.end_dates}  n_assets={args.nassets}")
    print(f"  CONFIG FORCED: BUY+SELL enabled, gauge_filter OFF")
    print("═" * 78)

    all_groups = {('SELL', 'win'): [], ('SELL', 'loss'): [],
                  ('BUY', 'win'): [], ('BUY', 'loss'): []}
    all_pnls = {k: [] for k in all_groups}

    for end_date in args.end_dates:
        print(f"\n{'─' * 78}")
        print(f"  Window end={end_date}")
        print(f"{'─' * 78}")

        force_config(end_date, args.tf, args.nassets)

        t0 = time.time()
        assets = load_window(end_date, args.nassets, args.tf)
        print(f"  Loaded {len(assets)} assets in {time.time()-t0:.0f}s")

        if not assets:
            continue

        print(f"  Computing signed_flow...")
        t0 = time.time()
        sf_map = {}
        for sym, ad in assets.items():
            try:
                sf_map[sym] = compute_signed_flow_for_asset(ad)
            except Exception as e:
                print(f"    ⚠️  {sym}: {e}")
        print(f"  Computed for {len(sf_map)}/{len(assets)} in "
              f"{time.time()-t0:.0f}s")

        print(f"  Running backtest...")
        t0 = time.time()
        trades_data, _ = run_and_collect(assets)
        print(f"  {len(trades_data)} trades in {time.time()-t0:.0f}s")

        groups, pnls, missing = analyze(trades_data, sf_map)
        print(f"  valid feat_idx: {sum(len(v) for v in groups.values())}  "
              f"(missing={missing})")

        # Accumulate
        for k in all_groups:
            all_groups[k].extend(groups[k])
            all_pnls[k].extend(pnls[k])

    # ═══ Full Report ═══
    print("\n\n" + "═" * 78)
    print("  النتائج المُجمَّعة عبر كل النوافذ")
    print("═" * 78)

    print(f"\n  ▶ signed_flow distribution at entry:")
    print_group("SELL win", all_groups[('SELL', 'win')])
    print_group("SELL loss", all_groups[('SELL', 'loss')])
    print_group("BUY win", all_groups[('BUY', 'win')])
    print_group("BUY loss", all_groups[('BUY', 'loss')])

    print(f"\n  ▶ PnL by group:")
    for key in [('SELL', 'win'), ('SELL', 'loss'),
                ('BUY', 'win'), ('BUY', 'loss')]:
        pnl_list = all_pnls[key]
        if pnl_list:
            print(f"    {key[0]} {key[1]:<6} n={len(pnl_list):>5}  "
                  f"mean={np.mean(pnl_list):>+10.5f}  "
                  f"sum={np.sum(pnl_list):>+12.2f}")

    print("\n" + "═" * 78)
    print("  الحكم — t-test بين win و loss")
    print("═" * 78)
    print()

    for action in ('SELL', 'BUY'):
        wins = all_groups[(action, 'win')]
        losses = all_groups[(action, 'loss')]
        r = t_test(wins, losses)
        if r is None:
            print(f"  {action}: insufficient data (win={len(wins)}, "
                  f"loss={len(losses)})")
            print()
            continue

        print(f"  {action}:")
        print(f"    win  n={r['nw']:>5}  mean={r['mw']:>+9.5f}  "
              f"std={r['sw']:>8.5f}")
        print(f"    loss n={r['nl']:>5}  mean={r['ml']:>+9.5f}  "
              f"std={r['sl']:>8.5f}")
        print(f"    difference = {r['diff']:>+9.5f}  "
              f"t = {r['t']:>+8.3f}")
        if abs(r['t']) > 2.5:
            print(f"    ✅ STRONG SIGNIFICANCE")
        elif abs(r['t']) > 2.0:
            print(f"    ✅ SIGNIFICANT")
        elif abs(r['t']) > 1.5:
            print(f"    🟡 MARGINAL")
        else:
            print(f"    ❌ NOT SIGNIFICANT")
        print()


if __name__ == '__main__':
    main()
