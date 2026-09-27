#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════
 diagnostic_entry.py — Old vs New Entry Logic on REAL cached data
═══════════════════════════════════════════════════════════════════════

Purpose:
  Runs BOTH entry logics on the SAME `AssetData` and reports:
    1. Dip size distributions (how deep does each wait for entry)
    2. Predicted fill rates (using precompute_entry_fills)
    3. Intrabar SL-hit rates (pessimistic, one bar after entry)
    4. K_SKIP_IF_DEGENERATE rejection counts
    5. Signal counts per symbol
    6. Time-decay effect on NEW dip
    7. Score distribution to see MIN_SCORE impact

No API calls if cache exists. Reads from market_data_cache/*.parquet.
Uses trading.py's own process_asset and compute_geodesic_stop.
═══════════════════════════════════════════════════════════════════════
"""

import os, sys, time, json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

# ── Import trading.py from same dir ──
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import trading as T
    from trading import (
        process_asset, compute_geodesic_stop,
        precompute_entry_fills, effective_bars,
    )
except Exception as e:
    print(f"FATAL: cannot import trading.py: {e}")
    sys.exit(1)

# Silences some noise
T.CFG.SUBBARS_ENABLED = False   # we don't need sub-bars for entry logic
T.CFG.PARALLEL_PROCESSING = False
T.CFG.ASSET_CACHE_ENABLED = False

# ── Test configuration ──
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
TIMEFRAMES = ["1h", "15m"]
HISTORY_DAYS = 90
CACHE_DIR = "market_data_cache"


def load_df(sym, tf, days):
    """Read directly from parquet cache. No API call if it exists."""
    fp = os.path.join(CACHE_DIR,
                       f"{sym.replace('/', '_')}_{tf}.parquet")
    if not os.path.exists(fp):
        return None
    try:
        df = pd.read_parquet(fp)
        if df.index.tz is None:
            df.index = pd.to_datetime(df.index, utc=True)
        return df
    except Exception as e:
        print(f"  read {fp} failed: {e}")
        return None


def old_friction_drag(fric_val, p):
    """Exactly the formula from best_trading_v10_ai5_1_1.py"""
    return fric_val * p * 0.1


def build_signals_old(assets, cfg, min_score=5.5):
    """
    Re-implements the OLD best_trading_v10_ai5_1_1 build_signals.
    Uses:
      - friction_drag = fric_val * p * 0.1  (1–2% dip)
      - MIN_SCORE = 5.5
      - P_activation >= 0.35
    """
    sigs = []
    for sym, ad in assets.items():
        n = len(ad.score)
        for fi in range(ad.train_end + 1, n):
            ci = ad.feat_start + fi
            if ci >= len(ad.closes) - 1:
                continue
            p = float(ad.closes[ci])
            if p <= 0:
                continue
            geo_accel = float(ad.geodesic_accel[fi])
            fric_val = float(ad.friction[fi]) + 1e-6
            T_info = float(ad.T_info[fi])
            force_mag = abs(geo_accel) + 1e-9
            P_activation = np.exp(-fric_val / (force_mag * T_info))
            if P_activation < 0.35:
                continue
            micro_momentum = p - ad.closes[ci - 1]
            if micro_momentum == 0:
                continue
            action = "BUY" if micro_momentum > 0 else "SELL"
            if ad.score[fi] < min_score:
                continue
            dip = old_friction_drag(fric_val, p)
            tunnel = p - dip if action == "BUY" else p + dip
            sl_dist = compute_geodesic_stop(tunnel, ad, fi, cfg)
            sl = tunnel - sl_dist if action == "BUY" else tunnel + sl_dist
            tp1 = tunnel + sl_dist * 2.0 if action == "BUY" else tunnel - sl_dist * 2.0
            sigs.append({
                'sym': sym, 'ci': ci, 'fi': fi, 'action': action,
                'market_p': p, 'tunnel_p': tunnel,
                'dip': dip, 'dip_frac': dip / p,
                'sl': sl, 'tp1': tp1,
                'sl_dist': sl_dist,
                'score': float(ad.score[fi]),
                'fric': fric_val,
                'atr': float(ad.atr14[ci]) if ci < len(ad.atr14) else 0.0,
            })
    return sigs


def build_signals_new(assets, cfg):
    """Calls the current trading.py build_signals, then enriches."""
    try:
        raw = T.build_signals(assets, mode="backtest")
    except Exception as e:
        print(f"  build_signals failed: {e}")
        return []
    sigs = []
    for s in raw:
        ad = assets[s.symbol]
        ci = int(s.close_idx)
        if ci >= len(ad.closes):
            continue
        p = float(ad.closes[ci])
        sigs.append({
            'sym': s.symbol, 'ci': ci, 'fi': int(s.feat_idx),
            'action': s.action,
            'market_p': p, 'tunnel_p': float(s.price),
            'dip': abs(p - float(s.price)),
            'dip_frac': abs(p - float(s.price)) / p if p > 0 else 0.0,
            'sl': float(s.sl), 'tp1': float(s.tp1),
            'sl_dist': abs(float(s.price) - float(s.sl)),
            'score': float(s.score),
            'fric': float(ad.friction[s.feat_idx]) + 1e-6,
            'atr': float(ad.atr14[ci]) if ci < len(ad.atr14) else 0.0,
        })
    return sigs


def predict_fill_rate(sigs, assets, max_wait_bars, pen_bps):
    """Compute per-signal fill prediction using precompute_entry_fills logic."""
    by_sym = defaultdict(list)
    for i, s in enumerate(sigs):
        by_sym[s['sym']].append((i, s))
    pen_frac = pen_bps * 1e-4
    fills = {}
    for sym, lst in by_sym.items():
        if sym not in assets:
            for i, _ in lst:
                fills[i] = None
            continue
        ad = assets[sym]
        n_bars = len(ad.closes)
        for j, (i, s) in enumerate(lst):
            deadline = min(s['ci'] + max_wait_bars, n_bars - 1)
            if j + 1 < len(lst):
                deadline = min(deadline, lst[j + 1][1]['ci'])
            start = s['ci'] + 1
            if start >= deadline:
                fills[i] = None
                continue
            target = s['tunnel_p']
            if s['action'] == "BUY":
                need = target * (1.0 - pen_frac)
                idx = np.where(ad.lows[start:deadline] <= need)[0]
            else:
                need = target * (1.0 + pen_frac)
                idx = np.where(ad.highs[start:deadline] >= need)[0]
            fills[i] = (start + int(idx[0])) if len(idx) else None
    return fills


def intrabar_sl_hits(sigs, assets, bars_ahead=1):
    """
    For each signal, check whether SL would be hit within `bars_ahead`
    bars after the entry bar (pessimistic: uses low/high for BUY/SELL).
    """
    hits = []
    for s in sigs:
        ad = assets[s['sym']]
        ci = s['ci']
        end = min(ci + 1 + bars_ahead, len(ad.closes))
        start = ci + 1
        if start >= end:
            hits.append(False)
            continue
        if s['action'] == "BUY":
            hit = bool(np.any(ad.lows[start:end] <= s['sl']))
        else:
            hit = bool(np.any(ad.highs[start:end] >= s['sl']))
        hits.append(hit)
    return hits


def intrabar_tp_hits(sigs, assets, bars_ahead=1):
    """Same but for TP."""
    hits = []
    for s in sigs:
        ad = assets[s['sym']]
        ci = s['ci']
        end = min(ci + 1 + bars_ahead, len(ad.closes))
        start = ci + 1
        if start >= end:
            hits.append(False)
            continue
        if s['action'] == "BUY":
            hit = bool(np.any(ad.highs[start:end] >= s['tp1']))
        else:
            hit = bool(np.any(ad.lows[start:end] <= s['tp1']))
        hits.append(hit)
    return hits


def dist_stats(arr, label):
    if not arr:
        return f"  {label}: (no data)"
    a = np.asarray(arr, dtype=float)
    return (f"  {label}: n={len(a):6,}  "
            f"mean={a.mean():8.4f}  median={np.median(a):8.4f}  "
            f"p10={np.percentile(a,10):8.4f}  "
            f"p90={np.percentile(a,90):8.4f}")


def main():
    print("=" * 78)
    print("  DIAGNOSTIC — Old vs New Entry Logic on REAL cached data")
    print("=" * 78)
    print(f"  Symbols: {SYMBOLS}")
    print(f"  TFs    : {TIMEFRAMES}")
    print(f"  Days   : {HISTORY_DAYS}")
    print(f"  Cache  : {CACHE_DIR}")
    print("=" * 78)

    # Probe: do we have cached data?
    have = []
    for tf in TIMEFRAMES:
        for sym in SYMBOLS:
            fp = os.path.join(CACHE_DIR,
                               f"{sym.replace('/', '_')}_{tf}.parquet")
            if os.path.exists(fp):
                have.append((sym, tf))
    if not have:
        print("\n❌ No cached parquet files found.")
        print("   Run trading.py in backtest mode once to populate "
              f"{CACHE_DIR}/, then re-run this script.")
        return
    print(f"\n✔ Found {len(have)} cached files in {CACHE_DIR}/")

    # We don't actually need ccxt if we use cached parquet
    class _NoOpExchange:
        def parse_timeframe(self, tf):
            return {'1m': 60, '5m': 300, '15m': 900, '30m': 1800,
                    '1h': 3600, '4h': 14400, '1d': 86400}.get(tf, 3600)
    noop_ex = _NoOpExchange()

    for tf in TIMEFRAMES:
        print("\n" + "#" * 78)
        print(f"# TIMEFRAME = {tf}")
        print("#" * 78)

        # ── Configure TF ──
        tf_scale, tf_sec, tf_hours = T.compute_tf_scale(noop_ex, tf)
        T.CFG.TF_SCALE = tf_scale
        T.CFG.TF_SECONDS = tf_sec
        T.CFG.TF_HOURS = tf_hours
        T.CFG.timeframe = tf

        # ── Load data ──
        print(f"\n[1] Loading cached data...")
        raw = {}
        for sym in SYMBOLS:
            df = load_df(sym, tf, HISTORY_DAYS)
            if df is None or len(df) < 500:
                print(f"  ✗ {sym:12s}: {'missing' if df is None else f'only {len(df)} bars'}")
                continue
            raw[sym] = df
            print(f"  ✓ {sym:12s}: {len(df):6,} bars")
        if not raw:
            print("  no usable data"); continue

        # ── Process assets — measure K_SKIP_IF_DEGENERATE ──
        print(f"\n[2] Processing assets (measuring KMeans rejection)...")
        assets = {}
        rejected = []
        for sym, df in raw.items():
            try:
                # Disable sub-bars: pass sub_df=None
                ad = process_asset(sym, df, current_capital=55.0, sub_df=None)
            except Exception as e:
                print(f"  ✗ {sym:12s} EXCEPTION: {type(e).__name__}: {e}")
                rejected.append(sym)
                continue
            if ad is None:
                print(f"  ✗ {sym:12s} REJECTED by K_SKIP_IF_DEGENERATE")
                rejected.append(sym)
                continue
            assets[sym] = ad
            H_mean = float(np.mean(ad.H[:ad.train_end]))
            H_theo = np.log2(max(ad.dynamic_k, 2))
            ratio = H_mean / H_theo if H_theo > 0 else 0
            print(f"  ✓ {sym:12s}  K={ad.dynamic_k:2d}  "
                  f"H_ratio={ratio:.3f}  bars={len(ad.closes):6,}")

        print(f"  → Accepted: {len(assets)}  Rejected: {len(rejected)}")
        if rejected:
            print(f"  → Rejected: {rejected}")
        if not assets:
            continue

        # ── Build signals ──
        print(f"\n[3] Building signals with BOTH logics...")
        t0 = time.time()
        sigs_old = build_signals_old(assets, T.CFG, min_score=5.5)
        t_old = time.time() - t0
        t0 = time.time()
        sigs_new = build_signals_new(assets, T.CFG)
        t_new = time.time() - t0

        print(f"  OLD logic: {len(sigs_old):6,} signals  ({t_old:.1f}s)")
        print(f"  NEW logic: {len(sigs_new):6,} signals  ({t_new:.1f}s)")

        # ── Dip distribution ──
        print(f"\n[4] Dip size (% of market close at signal):")
        if sigs_old:
            print(dist_stats([s['dip_frac']*100 for s in sigs_old], "OLD"))
        if sigs_new:
            print(dist_stats([s['dip_frac']*100 for s in sigs_new], "NEW"))

        # ── ATR-normalized dip ──
        print(f"\n[5] Dip / ATR ratio (how many ATRs is the dip?):")
        if sigs_old:
            ratios_old = [s['dip'] / s['atr'] for s in sigs_old
                          if s['atr'] > 0]
            print(dist_stats(ratios_old, "OLD"))
        if sigs_new:
            ratios_new = [s['dip'] / s['atr'] for s in sigs_new
                          if s['atr'] > 0]
            print(dist_stats(ratios_new, "NEW"))

        # ── Predicted fill rate ──
        print(f"\n[6] Predicted fill rate (pen_bps={T.CFG.FILL_PENETRATION_BPS}, "
              f"wait={T.effective_bars(T.CFG.FILL_ENTRY_MAX_WAIT_BARS)} bars):")
        max_wait = T.effective_bars(T.CFG.FILL_ENTRY_MAX_WAIT_BARS)
        pen_bps = T.CFG.FILL_PENETRATION_BPS
        fills_old = predict_fill_rate(sigs_old, assets, max_wait, pen_bps)
        fills_new = predict_fill_rate(sigs_new, assets, max_wait, pen_bps)
        n_fill_old = sum(1 for v in fills_old.values() if v is not None)
        n_fill_new = sum(1 for v in fills_new.values() if v is not None)
        rate_old = 100.0 * n_fill_old / max(len(sigs_old), 1)
        rate_new = 100.0 * n_fill_new / max(len(sigs_new), 1)
        print(f"  OLD: {rate_old:6.2f}%  ({n_fill_old:6,} / {len(sigs_old):6,})")
        print(f"  NEW: {rate_new:6.2f}%  ({n_fill_new:6,} / {len(sigs_new):6,})")

        # ── Intrabar SL/TP hit rate (only signals that would fill) ──
        print(f"\n[7] Intrabar outcomes (only FILLED signals, 1 bar ahead):")
        # Filter sigs to those with fills
        sigs_old_filled = [sigs_old[i] for i, v in fills_old.items() if v is not None]
        sigs_new_filled = [sigs_new[i] for i, v in fills_new.items() if v is not None]
        if sigs_old_filled:
            sl_hits = intrabar_sl_hits(sigs_old_filled, assets, bars_ahead=1)
            tp_hits = intrabar_tp_hits(sigs_old_filled, assets, bars_ahead=1)
            pct_sl = 100.0 * sum(sl_hits) / len(sl_hits)
            pct_tp = 100.0 * sum(tp_hits) / len(tp_hits)
            print(f"  OLD: SL hit: {pct_sl:5.1f}%   TP hit: {pct_tp:5.1f}%  "
                  f"(n={len(sl_hits)})")
        if sigs_new_filled:
            sl_hits = intrabar_sl_hits(sigs_new_filled, assets, bars_ahead=1)
            tp_hits = intrabar_tp_hits(sigs_new_filled, assets, bars_ahead=1)
            pct_sl = 100.0 * sum(sl_hits) / len(sl_hits)
            pct_tp = 100.0 * sum(tp_hits) / len(tp_hits)
            print(f"  NEW: SL hit: {pct_sl:5.1f}%   TP hit: {pct_tp:5.1f}%  "
                  f"(n={len(sl_hits)})")

        # ── Same 24 bars ahead ──
        print(f"\n[8] Intrabar outcomes over 24 bars ahead:")
        if sigs_old_filled:
            sl_hits = intrabar_sl_hits(sigs_old_filled, assets, bars_ahead=24)
            tp_hits = intrabar_tp_hits(sigs_old_filled, assets, bars_ahead=24)
            pct_sl = 100.0 * sum(sl_hits) / len(sl_hits)
            pct_tp = 100.0 * sum(tp_hits) / len(tp_hits)
            print(f"  OLD: SL hit: {pct_sl:5.1f}%   TP hit: {pct_tp:5.1f}%")
        if sigs_new_filled:
            sl_hits = intrabar_sl_hits(sigs_new_filled, assets, bars_ahead=24)
            tp_hits = intrabar_tp_hits(sigs_new_filled, assets, bars_ahead=24)
            pct_sl = 100.0 * sum(sl_hits) / len(sl_hits)
            pct_tp = 100.0 * sum(tp_hits) / len(tp_hits)
            print(f"  NEW: SL hit: {pct_sl:5.1f}%   TP hit: {pct_tp:5.1f}%")

        # ── Time-decay impact on NEW ──
        print(f"\n[9] Time-decay effect on NEW dip (if applied in Live):")
        if sigs_new:
            base_dip_pct = np.mean([s['dip_frac'] for s in sigs_new]) * 100
            m1 = T.CFG.ENTRY_TIME_DECAY_MULT_1
            m2 = T.CFG.ENTRY_TIME_DECAY_MULT_2
            m3 = T.CFG.ENTRY_TIME_DECAY_MULT_3
            print(f"  base dip (Stage 0): {base_dip_pct:.4f}%")
            print(f"  after Stage 1:      {base_dip_pct * m1:.4f}%")
            print(f"  after Stage 2:      {base_dip_pct * m2:.4f}%")
            print(f"  after Stage 3:      {base_dip_pct * m3:.4f}%")
            print(f"  → At Stage 3, the dip is essentially zero "
                  f"(enters at market)")

        # ── Score distribution ──
        print(f"\n[10] Score distribution:")
        if sigs_old:
            print(dist_stats([s['score'] for s in sigs_old], "OLD"))
        if sigs_new:
            print(dist_stats([s['score'] for s in sigs_new], "NEW"))

        # ── Per-symbol count ──
        print(f"\n[11] Per-symbol signal counts:")
        print(f"  {'symbol':12s}  {'OLD':>6s}  {'NEW':>6s}  {'delta':>7s}")
        by_old = Counter(s['sym'] for s in sigs_old)
        by_new = Counter(s['sym'] for s in sigs_new)
        for sym in sorted(set(list(by_old.keys()) + list(by_new.keys()))):
            o = by_old.get(sym, 0)
            n = by_new.get(sym, 0)
            print(f"  {sym:12s}  {o:>6d}  {n:>6d}  {n - o:>+7d}")

        # ── What if we take NEW signals but force OLD dip? ──
        print(f"\n[12] Hypothetical: NEW signals but with OLD-style dip:")
        print(f"  (Simulates: keep current score/min_score logic,")
        print(f"   but restore friction_drag = fric_val * p * 0.1)")
        sim_sigs = []
        for s in sigs_new:
            p = s['market_p']
            dip = old_friction_drag(s['fric'], p)
            tunnel = p - dip if s['action'] == "BUY" else p + dip
            sl_dist = s['sl_dist']
            sim_sigs.append({
                'sym': s['sym'], 'ci': s['ci'],
                'action': s['action'],
                'market_p': p, 'tunnel_p': tunnel,
                'dip': dip, 'dip_frac': dip / p,
                'sl': tunnel - sl_dist if s['action'] == "BUY" else tunnel + sl_dist,
                'tp1': tunnel + sl_dist * 2.0 if s['action'] == "BUY" else tunnel - sl_dist * 2.0,
                'atr': s['atr'],
            })
        fills_sim = predict_fill_rate(sim_sigs, assets, max_wait, pen_bps)
        n_fill_sim = sum(1 for v in fills_sim.values() if v is not None)
        rate_sim = 100.0 * n_fill_sim / max(len(sim_sigs), 1)
        print(f"  Predicted fill rate: {rate_sim:.1f}%  "
              f"({n_fill_sim:,} / {len(sim_sigs):,})")
        if sigs_new:
            print(f"  vs NEW dip fill rate: {rate_new:.1f}%")
        if sigs_old:
            print(f"  vs OLD dip fill rate: {rate_old:.1f}%")
        sim_dips = [s['dip_frac'] for s in sim_sigs]
        if sim_dips:
            print(dist_stats([d * 100 for d in sim_dips], "SIM dip %"))
        sim_ratios = [s['dip'] / s['atr'] for s in sim_sigs if s['atr'] > 0]
        print(dist_stats(sim_ratios, "SIM dip/ATR"))

    # ── Final summary ──
    print("\n" + "=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    print("""
  Interpretation guide:

  • §4 Dip size — OLD should be 1.5–2%, NEW should be 0.3–0.6%.
    If NEW is < 0.5%, the bot is entering near market, NOT on a dip.

  • §5 Dip/ATR — OLD should be ~1.5–2 ATR, NEW should be ~0.3–0.5 ATR.
    Below 0.5 ATR = entry is inside normal noise → SL is hit by noise.

  • §6 Fill rate — if NEW > OLD by a lot, this is the "chasing"
    behaviour; the bot is paying the market price instead of waiting.

  • §7/§8 SL hit rate — if NEW has higher SL hit rate, NEW entries
    are premature. Key metric: (SL_hit − TP_hit) should be negative.

  • §9 Time decay — at Stage 3 the dip is ~30% of base. Combined with
    NEW base of 0.4%, that is 0.12% → basically market order.

  • §12 SIM — putting OLD dip on NEW signals shows whether the dip
    formula is the root cause, independent of score/min_score changes.
    If SIM fill rate ≈ OLD fill rate, the formula is the driver.
""")
    print("=" * 78)


if __name__ == "__main__":
    main()
