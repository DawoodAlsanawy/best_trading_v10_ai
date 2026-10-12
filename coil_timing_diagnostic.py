#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Coil Timing Diagnostic
========================
يختبر فلتر الانكماش اللحظي (intra-bar timing):
- الإشارة على 4h (كما هي)
- الانتظار حتى انكماش σ_1m قبل التنفيذ
- مقارنة مع baseline (تنفيذ فوري)
"""

import argparse
import sys
import time
from datetime import timedelta
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


# ═════════════════════════════════════════════════════════════════════
# Coil detection
# ═════════════════════════════════════════════════════════════════════

def compute_coil_score(m1_ts, m1_close, t_now,
                        window_min=15, baseline_min=60):
    """
    يعيد (coil_score, sigma_now, sigma_base) عند الزمن t_now.
    """
    m1_ts = np.asarray(m1_ts)
    m1_close = np.asarray(m1_close, dtype=np.float64)
    t_now_ns = np.datetime64(t_now, 'ns') if not isinstance(
        t_now, np.datetime64) else t_now

    # آخر window_min دقيقة
    t_win = t_now - np.timedelta64(window_min, 'm')
    win_mask = (m1_ts >= t_win) & (m1_ts <= t_now)
    win_close = m1_close[win_mask]
    if len(win_close) < 5:
        return 0.0, 0.0, 0.0

    # baseline من baseline_min قبل signal
    t_base = t_now - np.timedelta64(baseline_min, 'm')
    base_mask = (m1_ts >= t_base) & (m1_ts < t_now)
    base_close = m1_close[base_mask]
    if len(base_close) < 10:
        return 0.0, 0.0, 0.0

    log_ret_win = np.diff(np.log(np.maximum(win_close, 1e-12)))
    log_ret_base = np.diff(np.log(np.maximum(base_close, 1e-12)))
    if len(log_ret_win) < 3 or len(log_ret_base) < 5:
        return 0.0, 0.0, 0.0

    sigma_now = float(np.std(log_ret_win))
    sigma_base = float(np.std(log_ret_base))
    if sigma_base <= 1e-9:
        return 0.0, sigma_now, 0.0

    ratio = sigma_now / sigma_base
    coil = max(0.0, min(1.0, 1.0 - ratio))
    return coil, sigma_now, sigma_base


def find_coil_moment(m1_df, signal_time, max_wait_min=5,
                     coil_threshold=0.5, window_min=15,
                     baseline_min=60):
    """
    يبحث عن أول لحظة انكماش بعد signal_time.
    يعيد (coil_ts, coil_score, sigma_now, sigma_base) أو None.
    """
    if m1_df is None or len(m1_df) < 10:
        return None

    end_time = signal_time + timedelta(minutes=max_wait_min)
    window_df = m1_df[(m1_df.index >= signal_time)
                      & (m1_df.index <= end_time)]
    if len(window_df) == 0:
        return None

    m1_ts = m1_df.index.values.astype('datetime64[ns]')
    m1_close = m1_df['Close'].values.astype(np.float64)

    for ts, _ in window_df.iterrows():
        t_now = np.datetime64(ts.tz_localize(None), 'ns') \
            if hasattr(ts, 'tz_localize') and ts.tz else np.datetime64(ts, 'ns')
        coil, s_now, s_base = compute_coil_score(
            m1_ts, m1_close, t_now, window_min, baseline_min)
        if coil >= coil_threshold:
            return ts, coil, s_now, s_base
    return None


# ═════════════════════════════════════════════════════════════════════
# Trade simulation
# ═════════════════════════════════════════════════════════════════════

def simulate_from_entry(ad, entry_bar_4h, entry_px, action,
                        sl_dist, tp_mult, H_bars):
    """
    Simulates SL/TP from a specific bar. Returns 'TP'|'SL'|'TIMEOUT'.
    """
    n = len(ad.closes)
    if action == 'BUY':
        sl_px = entry_px - sl_dist
        tp_px = entry_px + sl_dist * tp_mult
    else:
        sl_px = entry_px + sl_dist
        tp_px = entry_px - sl_dist * tp_mult

    for k in range(entry_bar_4h + 1, min(entry_bar_4h + 1 + H_bars, n)):
        lo = float(ad.lows[k]); hi = float(ad.highs[k])
        if action == 'BUY':
            if lo <= sl_px: return 'SL'
            if hi >= tp_px: return 'TP'
        else:
            if hi >= sl_px: return 'SL'
            if lo <= tp_px: return 'TP'
    return 'TIMEOUT'


def calc_stats(records, tp_mult):
    tp = sum(1 for r in records if r['outcome'] == 'TP')
    sl = sum(1 for r in records if r['outcome'] == 'SL')
    to = sum(1 for r in records if r['outcome'] == 'TIMEOUT')
    resolved = tp + sl
    if resolved == 0:
        return {'n': len(records), 'tp': 0, 'sl': 0, 'to': to,
                'p_tp': None, 'edge': None}
    p_tp = tp / resolved
    rw = 1.0 / (1.0 + tp_mult)
    return {'n': len(records), 'tp': tp, 'sl': sl, 'to': to,
            'p_tp': p_tp, 'edge': p_tp - rw, 'rw': rw}


# ═════════════════════════════════════════════════════════════════════
# 1m fetch
# ═════════════════════════════════════════════════════════════════════

def fetch_1m_around(ex, sym, signal_time, before_min=60, after_min=5):
    """
    يجلب 1m bars من signal_time - before_min إلى signal_time + after_min.
    """
    since_ms = int((signal_time - timedelta(minutes=before_min)).timestamp() * 1000)
    end_ms = int((signal_time + timedelta(minutes=after_min)).timestamp() * 1000)
    try:
        ohlcv = ex.fetch_ohlcv(sym, '1m', since=since_ms,
                               limit=before_min + after_min + 5)
    except Exception as e:
        return None
    if not ohlcv:
        return None
    df = pd.DataFrame(ohlcv,
                      columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()
    # اقصتطاع الفترة
    end_ts = signal_time + timedelta(minutes=after_min)
    df = df[(df.index >= signal_time - timedelta(minutes=before_min))
            & (df.index <= end_ts)]
    return df


# ═════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--history-days", type=int, default=30)
    p.add_argument("--nassets", type=int, default=50)
    p.add_argument("--capital", type=float, default=2.0)
    p.add_argument("--tp-mult", type=float, default=5.0)
    p.add_argument("--sl-widen-mult", type=float, default=0.15)
    p.add_argument("--coil-threshold", type=float, default=0.5)
    p.add_argument("--max-wait-min", type=int, default=5)
    p.add_argument("--window-min", type=int, default=15)
    p.add_argument("--baseline-min", type=int, default=60)
    p.add_argument("--enable-sell", action="store_true", default=True)
    p.add_argument("--sell-gauge-pct", type=float, default=1.0)
    args = p.parse_args()

    # ═══════════════════════════════════════════════════════════
    # Configure CFG
    # ═══════════════════════════════════════════════════════════
    bot.CFG.timeframe = args.timeframe
    bot.CFG.history_days = args.history_days
    bot.CFG.INITIAL_CAPITAL = args.capital
    bot.CFG.SELL_ENABLED = args.enable_sell
    bot.CFG.GAUGE_DISABLE_SELL = False
    bot.CFG.TP_MULT = args.tp_mult
    bot.CFG.SL_WIDEN_MULT = args.sl_widen_mult
    bot.CFG.APEX_ENABLED = False
    bot.CFG.TRAIL_ENABLED = False
    bot.CFG.PO_FIXED_PRICE = False
    if args.sell_gauge_pct >= 1.0:
        bot.CFG.SELL_GAUGE_PCT = args.sell_gauge_pct / 100.0
    else:
        bot.CFG.SELL_GAUGE_PCT = args.sell_gauge_pct

    ex = ccxt.binance({'options': {'defaultType': 'future'}})
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)

    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))
    bot.CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))

    H_BARS = max(10, int(np.ceil(168.0 / _tf_h)))
    max_sl_frac = 0.015 * args.sl_widen_mult

    section("Configuration")
    print(f"  Timeframe:        {args.timeframe}")
    print(f"  History days:     {args.history_days}")
    print(f"  N assets:         {args.nassets}")
    print(f"  TP_MULT:          {args.tp_mult}")
    print(f"  SL_WIDEN_MULT:    {args.sl_widen_mult} "
          f"→ max_sl_frac={max_sl_frac*100:.3f}%")
    print(f"  Coil threshold:   {args.coil_threshold}")
    print(f"  Max wait:         {args.max_wait_min} min")
    print(f"  Window:           {args.window_min} min")
    print(f"  Baseline:         {args.baseline_min} min")

    # ═══════════════════════════════════════════════════════════
    # Fetch 4h + process
    # ═══════════════════════════════════════════════════════════
    log("Scanning assets...")
    top_syms = bot.scan_top_assets(ex, args.nassets)
    log(f"Found {len(top_syms)} symbols")

    log("Fetching 4h OHLCV...")
    raw = bot.fetch_all(top_syms, ex, args.timeframe,
                        args.history_days, workers=5)
    log(f"Fetched {len(raw)} symbols")

    log("Processing assets...")
    assets = {}
    for sym, df in raw.items():
        try:
            ad = bot.process_asset(sym, df, current_capital=args.capital)
            if ad is not None:
                assets[sym] = ad
        except Exception:
            pass
    log(f"Processed {len(assets)} assets")

    log("Building signals...")
    bot._filter_reset_stats()
    sigs = bot.build_signals(assets, mode="backtest")
    sigs = bot.deduplicate_signals(sigs)
    log(f"Got {len(sigs)} signals")

    if not sigs:
        log("No signals", level="ERROR")
        return 1

    # ═══════════════════════════════════════════════════════════
    # Process each signal
    # ═══════════════════════════════════════════════════════════
    log("Analyzing coil timing...")
    log(f"  Fetching 1m data for each signal "
        f"(~{len(sigs)} fetches)...")

    records = []
    n_coil_found = 0
    n_no_coil = 0
    n_no_1m = 0

    for idx, sig in enumerate(sigs):
        if idx % 20 == 0:
            log(f"  {idx}/{len(sigs)}...")
        try:
            ad = assets.get(sig.symbol)
            if ad is None:
                continue

            # signal_time = timestamp of the 4h close bar
            signal_time = sig.timestamp
            if signal_time.tz is None:
                signal_time = signal_time.tz_localize('UTC')

            # fetch 1m around
            m1_df = fetch_1m_around(ex, sig.symbol, signal_time,
                                     args.baseline_min,
                                     args.max_wait_min)
            if m1_df is None or len(m1_df) < 10:
                n_no_1m += 1
                continue

            # baseline entry: fill at signal_time + 1 (first 1m bar after)
            baseline_bar = m1_df[m1_df.index > signal_time]
            if len(baseline_bar) == 0:
                n_no_1m += 1
                continue
            baseline_px = float(baseline_bar.iloc[0]['Open'])

            # coil detection
            coil = find_coil_moment(
                m1_df, signal_time,
                max_wait_min=args.max_wait_min,
                coil_threshold=args.coil_threshold,
                window_min=args.window_min,
                baseline_min=args.baseline_min,
            )

            # SL distance from 4h sigma
            fi = int(sig.feat_idx)
            sigma_4h = (float(ad.E_therm[fi])
                        if 0 <= fi < len(ad.E_therm) else 0.01)
            friction = (float(ad.friction[fi])
                        if 0 <= fi < len(ad.friction) else 0.2)
            sl_sigma = 0.8 / (1.0 + friction * 5.0)
            sl_sigma = max(3.0, min(sl_sigma, 8.0))

            # Same SL fraction for fair comparison
            sl_dist_frac = max_sl_frac

            # Determine 4h entry bar (the close_idx bar in ad)
            entry_4h_bar = int(sig.close_idx)

            # ---- baseline outcome ----
            sl_dist_base = baseline_px * sl_dist_frac
            outcome_base = simulate_from_entry(
                ad, entry_4h_bar, baseline_px, sig.action,
                sl_dist_base, args.tp_mult, H_BARS)

            # ---- coil outcome ----
            coil_ts = None
            coil_score = 0.0
            outcome_coil = None
            coil_delay_bars = 0
            coil_px = 0.0

            if coil is not None:
                coil_ts, coil_score, s_now, s_base = coil
                # الحصول على سعر الانكماش: open الشمعة التالية
                after_coil = m1_df[m1_df.index > coil_ts]
                if len(after_coil) > 0:
                    coil_px = float(after_coil.iloc[0]['Open'])
                    sl_dist_coil = coil_px * sl_dist_frac
                    outcome_coil = simulate_from_entry(
                        ad, entry_4h_bar, coil_px, sig.action,
                        sl_dist_coil, args.tp_mult, H_BARS)
                    coil_delay_bars = int(
                        (coil_ts - signal_time).total_seconds() / 60)
                    n_coil_found += 1
                else:
                    n_no_coil += 1
            else:
                n_no_coil += 1

            records.append({
                'symbol': sig.symbol,
                'action': sig.action,
                'signal_time': str(signal_time),
                'baseline_px': baseline_px,
                'outcome_base': outcome_base,
                'coil_found': coil is not None,
                'coil_score': coil_score,
                'coil_delay_min': coil_delay_bars,
                'coil_px': coil_px,
                'outcome_coil': outcome_coil,
                'sl_sigma_4h': sl_sigma,
                'sigma_4h': sigma_4h,
            })
        except Exception as e:
            log(f"  error on {sig.symbol}: {e}", level="WARN")
            continue

    log(f"Analyzed {len(records)} signals "
        f"(coil_found={n_coil_found}, no_coil={n_no_coil}, "
        f"no_1m={n_no_1m})")

    if not records:
        return 1

    # ═══════════════════════════════════════════════════════════
    # Analysis
    # ═══════════════════════════════════════════════════════════
    section("BASELINE — Execute at first 1m bar after signal")
    base_records = [{'outcome': r['outcome_base']} for r in records]
    sb = calc_stats(base_records, args.tp_mult)
    print(f"  n={sb['n']}  TP={sb['tp']}  SL={sb['sl']}  TO={sb['to']}")
    if sb['p_tp'] is not None:
        print(f"  P(TP)={sb['p_tp']*100:.1f}%  "
              f"edge={sb['edge']*100:+.1f}%  (RW={sb['rw']*100:.1f}%)")

    section("COIL FILTER — Execute at first coil moment")
    coil_records = [r for r in records if r['coil_found']]
    if not coil_records:
        print("  No coil moments detected with current threshold")
    else:
        cr = [{'outcome': r['outcome_coil']} for r in coil_records
              if r['outcome_coil'] is not None]
        sc = calc_stats(cr, args.tp_mult)
        print(f"  Triggered: {len(coil_records)}/{len(records)} "
              f"({100*len(coil_records)/len(records):.1f}%)")
        print(f"  n={sc['n']}  TP={sc['tp']}  SL={sc['sl']}  TO={sc['to']}")
        if sc['p_tp'] is not None:
            print(f"  P(TP)={sc['p_tp']*100:.1f}%  "
                  f"edge={sc['edge']*100:+.1f}%  "
                  f"(RW={sc['rw']*100:.1f}%)")

        if sb['edge'] is not None and sc['edge'] is not None:
            diff = sc['edge'] - sb['edge']
            print(f"\n  Δ edge = {diff*100:+.1f}%  "
                  f"(coil − baseline)")
            if diff > 0.05:
                print(f"  ✓✓ STRONG: coil timing adds "
                      f"+{diff*100:.1f}% edge")
            elif diff > 0.02:
                print(f"  ✓ MODERATE: +{diff*100:.1f}%")
            elif diff > -0.02:
                print(f"  ~ NEUTRAL")
            else:
                print(f"  ✗ NEGATIVE: {diff*100:+.1f}%")

    # ═══════════════════════════════════════════════════════════
    # Coil delay distribution
    # ═══════════════════════════════════════════════════════════
    if coil_records:
        section("COIL DELAY DISTRIBUTION")
        delays = [r['coil_delay_min'] for r in coil_records]
        scores = [r['coil_score'] for r in coil_records]
        print(f"  Delay min: min={min(delays)}  "
              f"max={max(delays)}  mean={np.mean(delays):.1f}")
        print(f"  Coil score: min={min(scores):.3f}  "
              f"max={max(scores):.3f}  mean={np.mean(scores):.3f}")

        # Delay buckets
        print(f"\n  {'delay (min)':<14} {'n':>5} {'edge':>8}")
        for lo, hi in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]:
            sub = [{'outcome': r['outcome_coil']}
                   for r in coil_records
                   if lo <= r['coil_delay_min'] < hi
                   and r['outcome_coil'] is not None]
            if len(sub) < 3:
                continue
            s = calc_stats(sub, args.tp_mult)
            if s['p_tp'] is None:
                continue
            print(f"  [{lo}-{hi}) min      "
                  f"{s['n']:>5} {s['edge']*100:>+7.1f}%")

    # ═══════════════════════════════════════════════════════════
    # By direction
    # ═══════════════════════════════════════════════════════════
    section("BY DIRECTION")
    for act in ['BUY', 'SELL']:
        sub_base = [{'outcome': r['outcome_base']}
                    for r in records if r['action'] == act]
        sub_coil = [{'outcome': r['outcome_coil']}
                    for r in records
                    if r['action'] == act and r['coil_found']
                    and r['outcome_coil'] is not None]
        print(f"\n  {act}:")
        s_b = calc_stats(sub_base, args.tp_mult)
        if s_b['p_tp'] is not None:
            print(f"    baseline: n={s_b['n']}  "
                  f"P(TP)={s_b['p_tp']*100:.1f}%  "
                  f"edge={s_b['edge']*100:+.1f}%")
        s_c = calc_stats(sub_coil, args.tp_mult)
        if s_c['p_tp'] is not None:
            print(f"    coil:     n={s_c['n']}  "
                  f"P(TP)={s_c['p_tp']*100:.1f}%  "
                  f"edge={s_c['edge']*100:+.1f}%")

    # Save records
    try:
        df = pd.DataFrame(records)
        df.to_csv("coil_records.csv", index=False)
        log("Saved: coil_records.csv")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
