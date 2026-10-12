#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compression Filter Diagnostic
==============================
يختبر هل الانكماش قبل الانعكاس له قيمة تنبؤية.
"""

import argparse
import sys
import time
import numpy as np
import pandas as pd
import ccxt

import trading_2_live2_1 as bot


def log(msg, level="INFO"):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def section(title):
    print(f"\n{'═' * 78}")
    print(f"  {title}")
    print(f"{'═' * 78}")


def subsection(title):
    print(f"\n  ── {title} ──")


# ═════════════════════════════════════════════════════════════════════
# Compression features
# ═════════════════════════════════════════════════════════════════════

def compute_compression(ad, fi, K=50):
    if fi < 5 or fi >= len(ad.E_therm):
        return None
    start = max(0, fi - K)
    sw = ad.E_therm[start:fi+1]
    Hw = ad.H[start:fi+1]
    Vw = ad.V[start:fi+1]
    KEw = ad.KE[start:fi+1]
    gw = ad.gauge_force[start:fi+1]
    if len(sw) < 10:
        return None

    sigma_r = float(np.mean(sw <= ad.E_therm[fi]))
    H_r = float(np.mean(Hw <= ad.H[fi]))
    V_r = float(np.mean(Vw <= ad.V[fi]))
    KE_r = float(np.mean(KEw <= ad.KE[fi]))
    gf_r = float(np.mean(gw <= ad.gauge_force[fi]))

    d_sig = float(ad.E_therm[fi] - ad.E_therm[fi-5])
    d_H = float(ad.H[fi] - ad.H[fi-5])
    d_V = float(ad.V[fi] - ad.V[fi-5])
    d_KE = float(ad.KE[fi] - ad.KE[fi-5])

    comp = 0
    if sigma_r < 0.30: comp += 1
    if d_sig < 0: comp += 1
    if H_r < 0.35: comp += 1
    if d_H < 0: comp += 1
    if V_r < 0.40: comp += 1
    if KE_r < 0.35: comp += 1

    return {
        'sigma': float(ad.E_therm[fi]),
        'sigma_rank': sigma_r,
        'd_sigma_5': d_sig,
        'H_rank': H_r,
        'd_H_5': d_H,
        'V_rank': V_r,
        'd_V_5': d_V,
        'KE_rank': KE_r,
        'd_KE_5': d_KE,
        'gf_rank': gf_r,
        'comp_score': comp,
    }


# ═════════════════════════════════════════════════════════════════════
# Trade simulation (SL/TP only)
# ═════════════════════════════════════════════════════════════════════

def simulate_signal(ad, sig, tp_mult, max_sl_frac, W_enter, H):
    fi = int(sig.feat_idx)
    ci = int(sig.close_idx)
    n = len(ad.closes)

    try:
        side = 'buy' if sig.action == 'BUY' else 'sell'
        entry_target = bot._compute_entry_target(
            sig, ad, side, exchange=None)
    except Exception:
        entry_target = float(ad.closes[ci])

    if not np.isfinite(entry_target) or entry_target <= 0:
        return 'NO_FILL', 0

    fill_bar = -1
    for k in range(ci + 1, min(ci + 1 + W_enter, n)):
        lo = float(ad.lows[k]); hi = float(ad.highs[k])
        if sig.action == 'BUY' and lo <= entry_target:
            fill_bar = k; break
        if sig.action == 'SELL' and hi >= entry_target:
            fill_bar = k; break

    if fill_bar < 0:
        return 'NO_FILL', 0

    sigma_fi = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
    friction = float(ad.friction[fi]) if 0 <= fi < len(ad.friction) else 0.2
    sl_sigma = 0.8 / (1.0 + friction * 5.0)
    sl_sigma = max(3.0, min(sl_sigma, 8.0))
    sigma_price = sigma_fi * entry_target
    sl_dist = min(sl_sigma * sigma_price, entry_target * max_sl_frac)

    if sl_dist <= 0:
        return 'NO_FILL', 0

    if sig.action == 'BUY':
        sl_px = entry_target - sl_dist
        tp_px = entry_target + sl_dist * tp_mult
    else:
        sl_px = entry_target + sl_dist
        tp_px = entry_target - sl_dist * tp_mult

    for k in range(fill_bar + 1, min(fill_bar + 1 + H, n)):
        lo = float(ad.lows[k]); hi = float(ad.highs[k])
        if sig.action == 'BUY':
            if lo <= sl_px:
                return 'SL', k - fill_bar
            if hi >= tp_px:
                return 'TP', k - fill_bar
        else:
            if hi >= sl_px:
                return 'SL', k - fill_bar
            if lo <= tp_px:
                return 'TP', k - fill_bar

    return 'TIMEOUT', H


# ═════════════════════════════════════════════════════════════════════
# Statistics
# ═════════════════════════════════════════════════════════════════════

def calc_stats(records, tp_mult):
    tp = sum(1 for r in records if r['outcome'] == 'TP')
    sl = sum(1 for r in records if r['outcome'] == 'SL')
    to = sum(1 for r in records if r['outcome'] == 'TIMEOUT')
    nf = sum(1 for r in records if r['outcome'] == 'NO_FILL')
    resolved = tp + sl
    if resolved == 0:
        return {'n': len(records), 'tp': 0, 'sl': 0,
                'to': to, 'nf': nf,
                'p_tp': None, 'edge': None}
    p_tp = tp / resolved
    rw = 1.0 / (1.0 + tp_mult)
    return {'n': len(records), 'tp': tp, 'sl': sl,
            'to': to, 'nf': nf,
            'p_tp': p_tp, 'edge': p_tp - rw, 'rw': rw}


def print_stats(records, tp_mult, indent="  "):
    s = calc_stats(records, tp_mult)
    if s['p_tp'] is None:
        print(f"{indent}n={s['n']}  (no resolved trades)")
        return s
    print(f"{indent}n={s['n']}  TP={s['tp']}  SL={s['sl']}  "
          f"TO={s['to']}  NF={s['nf']}")
    print(f"{indent}P(TP)={s['p_tp']*100:.1f}%  "
          f"edge={s['edge']*100:+.1f}%  "
          f"(RW={s['rw']*100:.1f}%)")
    return s


def strat_numeric(records, feature, tp_mult, n_bins=5):
    vals = np.array([r[feature] for r in records
                     if np.isfinite(r.get(feature, np.nan))],
                    dtype=np.float64)
    if len(vals) < 10:
        return None
    qs = np.quantile(vals, np.linspace(0, 1, n_bins + 1))
    qs = np.unique(qs)
    if len(qs) < 3:
        return None
    subsection(feature)
    print(f"    {'bin':<22} {'n':>5} {'P(TP)':>8} {'edge':>8}")
    edges = []
    for i in range(len(qs) - 1):
        lo, hi = qs[i], qs[i + 1]
        if i == len(qs) - 2:
            subset = [r for r in records
                      if lo <= r.get(feature, np.nan) <= hi]
        else:
            subset = [r for r in records
                      if lo <= r.get(feature, np.nan) < hi]
        if len(subset) < 3:
            continue
        s = calc_stats(subset, tp_mult)
        if s['p_tp'] is None:
            continue
        rng = f"[{lo:+.4g}, {hi:+.4g}]"
        print(f"    {rng:<22} {len(subset):>5} "
              f"{s['p_tp']*100:>7.1f}% {s['edge']*100:>+7.1f}%")
        edges.append(s['edge'])
    if edges:
        spread = max(edges) - min(edges)
        print(f"    → spread = {spread*100:+.1f}%")
    return edges


# ═════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--history-days", type=int, default=30)
    p.add_argument("--nassets", type=int, default=50)
    p.add_argument("--capital", type=float, default=2.0)
    p.add_argument("--maxcon", type=int, default=2)
    p.add_argument("--enable-sell", action="store_true", default=True)
    p.add_argument("--sell-gauge-pct", type=float, default=1.0)
    p.add_argument("--tp-mult", type=float, default=5.0)
    p.add_argument("--sl-widen-mult", type=float, default=0.15)
    p.add_argument("--partial-tp-r", type=float, default=7.0)
    args = p.parse_args()

    # ═══════════════════════════════════════════════════════════
    # Configure CFG
    # ═══════════════════════════════════════════════════════════
    bot.CFG.timeframe = args.timeframe
    bot.CFG.history_days = args.history_days
    bot.CFG.INITIAL_CAPITAL = args.capital
    bot.CFG.MAX_CONCURRENT_ASSETS = args.maxcon
    bot.CFG.SELL_ENABLED = args.enable_sell
    bot.CFG.GAUGE_DISABLE_SELL = False
    # If value >= 1.0, treat as percent
    if args.sell_gauge_pct >= 1.0:
        bot.CFG.SELL_GAUGE_PCT = args.sell_gauge_pct / 100.0
    else:
        bot.CFG.SELL_GAUGE_PCT = args.sell_gauge_pct
    bot.CFG.TP_MULT = args.tp_mult
    bot.CFG.SL_WIDEN_MULT = args.sl_widen_mult
    bot.CFG.PARTIAL_TP_R = args.partial_tp_r
    bot.CFG.APEX_ENABLED = False
    bot.CFG.TRAIL_ENABLED = False
    bot.CFG.PO_FIXED_PRICE = False

    # TF scale
    ex = ccxt.binance({'options': {'defaultType': 'future'}})
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)

    # Window scaling
    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))
    bot.CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))

    W_ENTER = max(2, int(np.ceil(8.0 / _tf_h)))
    H_BARS = max(10, int(np.ceil(168.0 / _tf_h)))
    max_sl_frac = 0.015 * args.sl_widen_mult

    section("Configuration")
    print(f"  Timeframe:       {args.timeframe}")
    print(f"  History days:    {args.history_days}")
    print(f"  N assets:        {args.nassets}")
    print(f"  Capital:         ${args.capital}")
    print(f"  TP_MULT:         {args.tp_mult}")
    print(f"  SL_WIDEN_MULT:   {args.sl_widen_mult} "
          f"→ max_sl_frac={max_sl_frac*100:.3f}%")
    print(f"  N={bot.CFG.N}  W={bot.CFG.W}  L={bot.CFG.L}  "
          f"ADV_BARS={bot.CFG.ADV_BARS}")
    print(f"  W_ENTER={W_ENTER} bars  H_BARS={H_BARS} bars")
    print(f"  SELL_ENABLED:    {bot.CFG.SELL_ENABLED}")
    print(f"  SELL_GAUGE_PCT:  {bot.CFG.SELL_GAUGE_PCT}")
    if bot.CFG.SELL_GAUGE_PCT >= 1.0:
        print(f"    ⚠ SELL_GAUGE_PCT=1.0 → no SELL will pass gauge filter")

    # ═══════════════════════════════════════════════════════════
    # Scan & fetch
    # ═══════════════════════════════════════════════════════════
    log("Scanning top assets...")
    top_syms = bot.scan_top_assets(ex, args.nassets)
    log(f"Found {len(top_syms)} symbols")

    log("Fetching OHLCV...")
    raw = bot.fetch_all(top_syms, ex, args.timeframe,
                        args.history_days, workers=5)
    log(f"Fetched {len(raw)} symbols")

    if len(raw) < 5:
        log("Too few symbols", level="ERROR")
        return 1

    # ═══════════════════════════════════════════════════════════
    # Process assets
    # ═══════════════════════════════════════════════════════════
    log("Processing assets...")
    assets = {}
    for sym, df in raw.items():
        try:
            ad = bot.process_asset(sym, df, current_capital=args.capital)
            if ad is not None:
                assets[sym] = ad
        except Exception:
            pass
    log(f"Processed {len(assets)}/{len(raw)} assets")

    if len(assets) < 3:
        log("Too few assets processed", level="ERROR")
        return 1

    # ═══════════════════════════════════════════════════════════
    # Build signals
    # ═══════════════════════════════════════════════════════════
    log("Building signals...")
    bot._filter_reset_stats()
    sigs = bot.build_signals(assets, mode="backtest")
    sigs = bot.deduplicate_signals(sigs)
    log(f"Got {len(sigs)} signals")

    if not sigs:
        log("No signals produced", level="ERROR")
        return 1

    # ═══════════════════════════════════════════════════════════
    # Simulate
    # ═══════════════════════════════════════════════════════════
    log("Simulating trades...")
    records = []
    for sig in sigs:
        ad = assets.get(sig.symbol)
        if ad is None:
            continue
        comp = compute_compression(ad, int(sig.feat_idx))
        if comp is None:
            continue
        outcome, bars = simulate_signal(
            ad, sig, args.tp_mult, max_sl_frac, W_ENTER, H_BARS)
        rec = {
            'symbol': sig.symbol,
            'action': sig.action,
            'score': float(sig.score),
            'outcome': outcome,
            'bars_to_res': bars,
        }
        rec.update(comp)
        records.append(rec)

    log(f"Simulated {len(records)} trades")

    if not records:
        return 1

    # ═══════════════════════════════════════════════════════════
    # Analysis
    # ═══════════════════════════════════════════════════════════
    section("BASELINE (all signals)")
    print_stats(records, args.tp_mult)

    # By direction
    subsection("By direction")
    for act in ['BUY', 'SELL']:
        sub = [r for r in records if r['action'] == act]
        if not sub:
            continue
        print(f"    {act}:")
        print_stats(sub, args.tp_mult, indent="      ")

    # By compression score
    section("BY COMPRESSION SCORE (0 to 6)")
    print(f"  {'score':<8} {'n':>5} {'TP':>5} {'SL':>5} "
          f"{'P(TP)':>8} {'edge':>8}")
    for s in range(7):
        sub = [r for r in records if r['comp_score'] == s]
        if len(sub) < 3:
            continue
        st = calc_stats(sub, args.tp_mult)
        if st['p_tp'] is None:
            continue
        print(f"  {s:<8} {st['n']:>5} {st['tp']:>5} {st['sl']:>5} "
              f"{st['p_tp']*100:>7.1f}% {st['edge']*100:>+7.1f}%")

    # By individual features
    section("BY INDIVIDUAL FEATURES (5 quantiles each)")
    for feat in ['sigma_rank', 'd_sigma_5', 'H_rank', 'd_H_5',
                 'V_rank', 'd_V_5', 'KE_rank', 'd_KE_5', 'gf_rank']:
        strat_numeric(records, feat, args.tp_mult)

    # ═══════════════════════════════════════════════════════════
    # Verdict
    # ═══════════════════════════════════════════════════════════
    section("VERDICT")
    low = [r for r in records if r['comp_score'] <= 2]
    high = [r for r in records if r['comp_score'] >= 4]
    mid = [r for r in records if r['comp_score'] in (3,)]

    if low:
        s_low = calc_stats(low, args.tp_mult)
        if s_low['p_tp'] is not None:
            print(f"  comp_score 0-2 (low):   n={s_low['n']:<4}  "
                  f"P(TP)={s_low['p_tp']*100:>5.1f}%  "
                  f"edge={s_low['edge']*100:>+6.1f}%")
    if mid:
        s_mid = calc_stats(mid, args.tp_mult)
        if s_mid['p_tp'] is not None:
            print(f"  comp_score 3   (mid):   n={s_mid['n']:<4}  "
                  f"P(TP)={s_mid['p_tp']*100:>5.1f}%  "
                  f"edge={s_mid['edge']*100:>+6.1f}%")
    if high:
        s_high = calc_stats(high, args.tp_mult)
        if s_high['p_tp'] is not None:
            print(f"  comp_score 4-6 (high):  n={s_high['n']:<4}  "
                  f"P(TP)={s_high['p_tp']*100:>5.1f}%  "
                  f"edge={s_high['edge']*100:>+6.1f}%")

    if low and high:
        s_low = calc_stats(low, args.tp_mult)
        s_high = calc_stats(high, args.tp_mult)
        if s_low['edge'] is not None and s_high['edge'] is not None:
            diff = s_high['edge'] - s_low['edge']
            print()
            if diff > 0.10:
                print(f"  ✓✓ STRONG: compression adds "
                      f"+{diff*100:.1f}% edge")
                print(f"     → يستحق فلترة إضافية")
            elif diff > 0.05:
                print(f"  ✓ MODERATE: compression adds "
                      f"+{diff*100:.1f}% edge")
                print(f"     → يستحق اختبار Walk-Forward")
            elif diff > -0.05:
                print(f"  ~ NEUTRAL: {diff*100:+.1f}% edge")
                print(f"     → الانكماش لا يفرق")
            else:
                print(f"  ✗ NEGATIVE: {diff*100:+.1f}% edge")
                print(f"     → الفلتر يضر")

    # Save records for external analysis
    try:
        df = pd.DataFrame(records)
        df.to_csv("compression_records.csv", index=False)
        log("Saved: compression_records.csv")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
