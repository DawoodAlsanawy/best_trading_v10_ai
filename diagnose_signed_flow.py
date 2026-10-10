#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_signed_flow.py — تشخيص إشارة التدفق الاتجاهي المُوقَّع.

المبدأ الرياضي:
  gauge_force = ||A||_F  (بلا اتجاه)
  signed_flow = Σ_{a<b} (T[a,b] - T[b,a])  (باتجاه)

حيث a,b مرتّبان حسب mean_r من KMeans centroids.
  - signed_flow > 0 → التدفق السائد صاعد
  - signed_flow < 0 → التدفق السائد هابط

التشخيص:
  - يبني signed_flow لكل شمعة
  - يُشغّل baseline SELL-only
  - يقارن توزيع signed_flow عند الرابحة vs الخاسرة
  - صفر تعديل على الفيزياء
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

# [PICKLE-FIX]
import __main__ as _pcmain
for _cn in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(engine, _cn):
        setattr(_pcmain, _cn, getattr(engine, _cn))

CFG = engine.CFG


# ═══════════════════════════════════════════════════════════════
# numba kernel for signed_flow
# ═══════════════════════════════════════════════════════════════

def _make_signed_flow_kernel():
    """Build numba kernel (or Python fallback)."""
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
            # reset
            for a in range(dyn_k):
                for b in range(dyn_k):
                    T_ord[a, b] = 0.0

            # build transition matrix on ranked symbols
            for j in range(i - W + 1, i):
                a_orig = sym_q[j - 1]
                b_orig = sym_q[j]
                a_rank = rank_map[a_orig]
                b_rank = rank_map[b_orig]
                T_ord[a_rank, b_rank] += 1.0

            # normalize
            sum_T = 0.0
            for a in range(dyn_k):
                for b in range(dyn_k):
                    sum_T += T_ord[a, b]
            if sum_T > 0.0:
                for a in range(dyn_k):
                    for b in range(dyn_k):
                        T_ord[a, b] /= sum_T

            # signed flow: sum over a<b of T[a,b] - T[b,a]
            sf = 0.0
            for a in range(dyn_k):
                for b in range(a + 1, dyn_k):
                    sf += T_ord[a, b] - T_ord[b, a]
            out[i] = sf

        return out

    return _signed_flow


_signed_flow = _make_signed_flow_kernel()


def compute_rank_map(ad):
    """Compute rank of each cluster by mean_r (dim 0 of X)."""
    km = ad.km
    k = int(km.n_clusters)
    mean_r = km.cluster_centers_[:, 0]  # dim 0 = mean_r
    order = np.argsort(mean_r)
    rank_map = np.zeros(k, dtype=np.int64)
    for rank, orig in enumerate(order):
        rank_map[int(orig)] = int(rank)
    return rank_map


def compute_signed_flow_for_asset(ad):
    """Compute signed_flow array for one AssetData. Indexed by feat_idx."""
    rank_map = compute_rank_map(ad)
    sym_q = np.ascontiguousarray(ad.sym_q, dtype=np.int64)
    return _signed_flow(sym_q, rank_map, int(ad.dynamic_k), int(CFG.W))


# ═══════════════════════════════════════════════════════════════
# Window loader
# ═══════════════════════════════════════════════════════════════

_SELL_DEFAULTS = {
    'SELL_ENABLED': True,
    'BUY_DISABLED': False,      # allow both for diagnostic
    'GAUGE_DISABLE_SELL': False,
    'GAUGE_FILTER_ENABLED': True,
    'SELL_GAUGE_PCT': 0.95,
    'SELL_MIN_SCORE': 3,
    'SELL_MIN_ZDEV': 1.5,
}
_ORIG = {k: getattr(CFG, k, None) for k in _SELL_DEFAULTS}


def reset_sell_cfg():
    for k, v in _ORIG.items():
        if v is not None:
            setattr(CFG, k, v)


def load_window(end_date, n_assets, tf):
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

    print(f"  {len(assets)} assets loaded")
    return assets


# ═══════════════════════════════════════════════════════════════
# Run baseline SELL-only and collect trade log
# ═══════════════════════════════════════════════════════════════

def run_and_collect(assets):
    """Run build_signals + simulate, return trade list."""
    reset_sell_cfg()

    # Set up temp trade log
    tmp_path = tempfile.mktemp(suffix='.jsonl')
    engine._TRADE_LOG_PATH = tmp_path

    # Write meta line manually (since _trade_log_init would overwrite it)
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'_meta': True, 'diag': True}) + "\n")

    sigs = engine.build_signals(assets, mode="backtest")
    sigs = engine.deduplicate_signals(sigs)
    corr = engine.precompute_correlations(assets)
    trades, equity = engine.simulate_portfolio(
        sigs, assets, corr, "backtest")

    # Read trades from JSONL (has feat_idx)
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
        'min': float(a.min()),
        'q25': float(np.percentile(a, 25)),
        'median': float(np.median(a)),
        'q75': float(np.percentile(a, 75)),
        'max': float(a.max()),
    }


def analyze(trades_data, sf_map, action_filter):
    """Group trades by action + outcome, look at signed_flow."""
    groups = {
        ('SELL', 'win'): [],
        ('SELL', 'loss'): [],
        ('BUY', 'win'): [],
        ('BUY', 'loss'): [],
    }
    pnls = {
        ('SELL', 'win'): [],
        ('SELL', 'loss'): [],
        ('BUY', 'win'): [],
        ('BUY', 'loss'): [],
    }
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
        print(f"    {label:<16} (empty)")
        return
    print(f"    {label:<16} n={s['n']:>5}  "
          f"mean={s['mean']:>+9.5f}  "
          f"med={s['median']:>+9.5f}  "
          f"q25={s['q25']:>+9.5f}  "
          f"q75={s['q75']:>+9.5f}  "
          f"std={s['std']:>8.5f}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h', choices=['1h', '4h'])
    ap.add_argument('--nassets', type=int, default=100)
    ap.add_argument('--end-date', default='2025-12-31')
    args = ap.parse_args()

    print("═" * 78)
    print(f"  diagnose_signed_flow — tf={args.tf}  "
          f"end={args.end_date}  n_assets={args.nassets}")
    print("═" * 78)

    # ── Load ──
    print("\n▶ Loading window...")
    t0 = time.time()
    assets = load_window(args.end_date, args.nassets, args.tf)
    print(f"  Loaded {len(assets)} assets in {time.time()-t0:.0f}s")

    # ── Compute signed_flow for each asset ──
    print("\n▶ Computing signed_flow...")
    t0 = time.time()
    sf_map = {}
    sf_abs_mean = []
    sf_std_mean = []
    for sym, ad in assets.items():
        try:
            sf = compute_signed_flow_for_asset(ad)
            sf_map[sym] = sf
            valid = sf[ad.train_end:]
            if len(valid) > 0:
                sf_abs_mean.append(float(np.abs(valid).mean()))
                sf_std_mean.append(float(valid.std()))
        except Exception as e:
            print(f"    ⚠️  {sym}: {e}")
    print(f"  Computed for {len(sf_map)}/{len(assets)} assets in "
          f"{time.time()-t0:.0f}s")
    print(f"  Mean |signed_flow| across assets: {np.mean(sf_abs_mean):.5f}")
    print(f"  Mean std(signed_flow) across assets: {np.mean(sf_std_mean):.5f}")

    # ── Run baseline SELL-only ──
    print("\n▶ Running baseline (BUY+SELL enabled, gauge filter ON)...")
    t0 = time.time()
    trades_data, sigs = run_and_collect(assets)
    print(f"  {len(trades_data)} trades in {time.time()-t0:.0f}s")

    # ── Analyze ──
    print("\n" + "═" * 78)
    print("  النتائج — signed_flow at signal time")
    print("═" * 78)

    groups, pnls, missing = analyze(trades_data, sf_map, None)
    print(f"\n  trades with valid feat_idx: "
          f"{sum(len(v) for v in groups.values())}  "
          f"(missing={missing})")

    print(f"\n  ▶ signed_flow distribution at entry:")
    print(f"  {'':14} {'':16} {'value of signed_flow':>50}")
    print_group("SELL win", groups[('SELL', 'win')])
    print_group("SELL loss", groups[('SELL', 'loss')])
    print_group("BUY win", groups[('BUY', 'win')])
    print_group("BUY loss", groups[('BUY', 'loss')])

    print(f"\n  ▶ PnL by group (average net_pnl):")
    for key, pnl_list in pnls.items():
        if pnl_list:
            label = f"{key[0]} {key[1]}"
            print(f"    {label:<16} n={len(pnl_list):>5}  "
                  f"mean_pnl={np.mean(pnl_list):>+10.5f}  "
                  f"sum_pnl={np.sum(pnl_list):>+12.2f}")

    # ── Verdict ──
    print("\n" + "═" * 78)
    print("  الحكم — هل signed_flow يفرّق بين win/loss؟")
    print("═" * 78)
    print()

    for action in ('SELL', 'BUY'):
        wins = groups[(action, 'win')]
        losses = groups[(action, 'loss')]
        if not wins or not losses:
            continue
        mw = np.mean(wins)
        ml = np.mean(losses)
        sw = np.std(wins)
        sl = np.std(losses)
        # pooled standard error
        se = np.sqrt(sw**2 / len(wins) + sl**2 / len(losses))
        t_stat = (mw - ml) / se if se > 0 else 0.0

        print(f"  {action}:")
        print(f"    win  mean signed_flow = {mw:+.6f}  (std={sw:.6f}, n={len(wins)})")
        print(f"    loss mean signed_flow = {ml:+.6f}  (std={sl:.6f}, n={len(losses)})")
        print(f"    difference = {mw-ml:+.6f}  "
              f"t-stat = {t_stat:+.3f}")
        if abs(t_stat) > 2.0:
            print(f"    ✅ SIGNIFICANT (|t| > 2)")
        elif abs(t_stat) > 1.0:
            print(f"    🟡 MARGINAL (1 < |t| < 2)")
        else:
            print(f"    ❌ NOT SIGNIFICANT (|t| < 1)")
        print()


if __name__ == '__main__':
    main()
