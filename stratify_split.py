#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stratification Lab v2 — تحليل منفصل لكل اتجاه
================================================
- BUY  و SELL يُجمَعان معاً
- التحليل الطبقي يتم على كل اتجاه بمعزل
- نبحث عن sweet spots خاصة بكل اتجاه
- SL/TP فقط (لا trailing، لا apex، لا breakeven)
"""

import argparse
import sys
import numpy as np
import pandas as pd
import ccxt

import trading_2_live2_1 as bot

SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT',
    'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT', 'LTC/USDT',
    'ATOM/USDT', 'NEAR/USDT', 'APT/USDT', 'FIL/USDT', 'UNI/USDT',
]

SL_SIGMA = 1.5
TP_SIGMA = 1.5
H_BARS = 100


def simulate_outcome(ad, sig_bar, action, p0, sigma0,
                     sl_sigma=SL_SIGMA, tp_sigma=TP_SIGMA, H=H_BARS):
    n = len(ad.closes)
    if action == 'BUY':
        sl_px = p0 * np.exp(-sl_sigma * sigma0)
        tp_px = p0 * np.exp(+tp_sigma * sigma0)
    else:
        sl_px = p0 * np.exp(+sl_sigma * sigma0)
        tp_px = p0 * np.exp(-tp_sigma * sigma0)

    for j in range(sig_bar + 1, min(sig_bar + 1 + H, n)):
        hi = float(ad.highs[j]); lo = float(ad.lows[j])
        if action == 'BUY':
            if lo <= sl_px: return 'SL', j - sig_bar
            if hi >= tp_px: return 'TP', j - sig_bar
        else:
            if hi >= sl_px: return 'SL', j - sig_bar
            if lo <= tp_px: return 'TP', j - sig_bar
    return 'TIMEOUT', None


def collect_from_symbol(ex, sym, tf, bars_to_test, capital,
                        enable_sell=True):
    try:
        ohlcv = ex.fetch_ohlcv(sym, tf, limit=2000)
    except Exception:
        return []
    if not ohlcv or len(ohlcv) < 500:
        return []
    df = pd.DataFrame(ohlcv,
                      columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()
    ad = bot.process_asset(sym, df, current_capital=capital)
    if ad is None:
        return []

    n = len(ad.closes)
    start = max(ad.train_end + 1, n - bars_to_test)
    stop = n - H_BARS - 2
    signals = []
    for i in range(start, stop):
        fi = i - ad.feat_start
        if fi < 0 or fi >= len(ad.score):
            continue
        p0 = float(ad.closes[i])
        sigma = float(ad.E_therm[fi])
        if not np.isfinite(sigma) or sigma <= 1e-6:
            continue
        fric = float(ad.friction[fi])
        T = float(ad.T_info[fi])
        geo = float(ad.geodesic_accel[fi])
        P_act = float(np.exp(-fric / ((abs(geo) + 1e-9) * T)))
        if P_act < 0.35:
            continue
        win = ad.closes[max(0, i - bot.CFG.N): i]
        if len(win) < 2:
            continue
        sd = float(np.std(win))
        if sd <= 1e-12:
            continue
        z = (p0 - float(np.mean(win))) / sd
        if abs(z) < 1.5:
            continue
        action = 'BUY' if z < 0 else 'SELL'
        if action == 'SELL' and not enable_sell:
            continue
        score = float(ad.score[fi])
        if score < bot.CFG.MIN_SCORE:
            continue
        outcome, bars = simulate_outcome(ad, i, action, p0, sigma)
        if outcome == 'TIMEOUT':
            continue
        signals.append({
            'symbol': sym, 'action': action, 'bar': i,
            'outcome': outcome, 'bars_to_resolve': bars,
            'z_dev': float(z), 'abs_z': float(abs(z)),
            'P_act': P_act, 'score': score, 'sigma': sigma,
            'friction': fric,
            'delta_gap': float(ad.delta_gap[fi]),
            'gauge_force': float(ad.gauge_force[fi]),
            'T_info': T, 'accel': abs(geo),
        })
    return signals


def segment_metrics(signals):
    n = len(signals)
    if n == 0:
        return None
    tp = sum(1 for s in signals if s['outcome'] == 'TP')
    sl = n - tp
    p_tp = tp / n
    rw = SL_SIGMA / (SL_SIGMA + TP_SIGMA)
    edge = p_tp - rw
    e_r = TP_SIGMA * p_tp - SL_SIGMA * (1 - p_tp)
    return {'n': n, 'tp': tp, 'sl': sl, 'p_tp': p_tp,
            'edge': edge, 'e_r': e_r}


def stratify(signals, feature, n_bins=5):
    values = np.array([s[feature] for s in signals], dtype=np.float64)
    values = values[np.isfinite(values)]
    if len(values) < 30:
        return None
    qs = np.quantile(values, np.linspace(0, 1, n_bins + 1))
    qs = np.unique(qs)
    if len(qs) < 3:
        return None
    bins = []
    for i in range(len(qs) - 1):
        lo, hi = qs[i], qs[i + 1]
        if i == len(qs) - 2:
            subset = [s for s in signals if lo <= s[feature] <= hi]
        else:
            subset = [s for s in signals if lo <= s[feature] < hi]
        m = segment_metrics(subset)
        if m is None:
            continue
        m['lo'] = float(lo); m['hi'] = float(hi)
        bins.append(m)
    return bins


def print_strat(title, bins, fmt=".4g"):
    if bins is None or len(bins) == 0:
        print(f"\n[{title}] — insufficient data")
        return None
    print(f"\n{'─' * 78}")
    print(f"{title}")
    print(f"{'─' * 78}")
    print(f"  {'bin':<24} {'n':>5} {'TP':>5} {'SL':>5} "
          f"{'P(TP)':>8} {'edge':>8} {'E[R]':>8}")
    best_edge = -1.0
    best_bin = None
    edges = []
    for b in bins:
        rng = f"[{b['lo']:{fmt}}, {b['hi']:{fmt}}]"
        edge_pct = f"{b['edge']*100:+.1f}%"
        print(f"  {rng:<24} {b['n']:>5} {b['tp']:>5} {b['sl']:>5} "
              f"{b['p_tp']*100:>7.1f}% {edge_pct:>8} {b['e_r']:>+8.3f}")
        edges.append(b['edge'])
        if b['edge'] > best_edge and b['n'] >= 20:
            best_edge = b['edge']
            best_bin = (b['lo'], b['hi'], b['n'], b['p_tp'])
    if best_bin is not None:
        print(f"  → Best bin: [{best_bin[0]:{fmt}}, {best_bin[1]:{fmt}}]"
              f"  n={best_bin[2]}  P(TP)={best_bin[3]*100:.1f}%  "
              f"edge={best_edge*100:+.1f}%")
    if len(edges) >= 3:
        spread = max(edges) - min(edges)
        print(f"  → Edge spread: {spread*100:+.1f}%")
    return best_edge


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeframe', default='1h')
    ap.add_argument('--bars', type=int, default=800)
    ap.add_argument('--capital', type=float, default=1000.0)
    ap.add_argument('--enable-sell', action='store_true', default=True)
    ap.add_argument('--symbols', nargs='*', default=None)
    ap.add_argument('--min-bin-n', type=int, default=20)
    args = ap.parse_args()

    # تفعيل SELL في Config
    bot.CFG.SELL_ENABLED = args.enable_sell
    print(f"SELL_ENABLED = {bot.CFG.SELL_ENABLED}")

    ex = ccxt.binance({'options': {'defaultType': 'future'}})
    bot.CFG.timeframe = args.timeframe
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)
    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))

    print(f"TF: {args.timeframe}  bars_to_test: {args.bars}  H: {H_BARS}")
    print(f"SL: {SL_SIGMA}σ  TP: {TP_SIGMA}σ  RW baseline = 50%\n")

    syms = args.symbols if args.symbols else SYMBOLS
    all_signals = []
    print("=" * 78)
    print(f"{'Symbol':<14} {'N':>5} {'TP':>5} {'SL':>5} "
          f"{'P(TP)':>8} {'edge':>8} {'E[R]':>8}")
    print("=" * 78)
    for sym in syms:
        try:
            s = collect_from_symbol(ex, sym, args.timeframe,
                                     args.bars, args.capital,
                                     enable_sell=args.enable_sell)
        except Exception as e:
            print(f"{sym:<14} ERROR: {e}")
            continue
        if not s:
            print(f"{sym:<14} (no signals)")
            continue
        m = segment_metrics(s)
        print(f"{sym:<14} {m['n']:>5} {m['tp']:>5} {m['sl']:>5} "
              f"{m['p_tp']*100:>7.1f}% "
              f"{m['edge']*100:>+7.1f}% {m['e_r']:>+8.3f}")
        all_signals.extend(s)

    print("=" * 78)
    print(f"TOTAL: {len(all_signals)}\n")

    if len(all_signals) < 30:
        print("⚠ SAMPLE TOO SMALL")
        return 1

    buy = [s for s in all_signals if s['action'] == 'BUY']
    sell = [s for s in all_signals if s['action'] == 'SELL']

    print(f"═══ POOLED ═══")
    m_all = segment_metrics(all_signals)
    print(f"  N={m_all['n']}  P(TP)={m_all['p_tp']*100:.1f}%  "
          f"edge={m_all['edge']*100:+.1f}%  E[R]={m_all['e_r']:+.3f}")

    print(f"\n═══ BY DIRECTION ═══")
    m_buy = segment_metrics(buy)
    m_sell = segment_metrics(sell)
    if m_buy:
        print(f"  BUY   n={m_buy['n']:>4}  P(TP)={m_buy['p_tp']*100:>5.1f}%  "
              f"edge={m_buy['edge']*100:>+6.1f}%  "
              f"E[R]={m_buy['e_r']:>+7.3f}")
    if m_sell:
        print(f"  SELL  n={m_sell['n']:>4}  P(TP)={m_sell['p_tp']*100:>5.1f}%  "
              f"edge={m_sell['edge']*100:>+6.1f}%  "
              f"E[R]={m_sell['e_r']:>+7.3f}")

    # ═══════════════════════════════════════════════════════════
    # BUY stratification
    # ═══════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 78}")
    print(f"  BUY-ONLY STRATIFICATION (n={len(buy)})")
    print(f"{'═' * 78}")
    features = ['abs_z', 'P_act', 'score', 'sigma',
                'friction', 'delta_gap', 'gauge_force',
                'T_info', 'accel']
    buy_bests = []
    for feat in features:
        b = stratify(buy, feat, n_bins=5)
        best = print_strat(f"BUY × {feat}", b)
        if best is not None:
            buy_bests.append((feat, best))

    print(f"\n  ── BUY TOP FEATURES ──")
    for feat, edge in sorted(buy_bests, key=lambda x: -x[1])[:5]:
        print(f"    {feat:<15} best edge = {edge*100:+.1f}%")

    # ═══════════════════════════════════════════════════════════
    # SELL stratification
    # ═══════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 78}")
    print(f"  SELL-ONLY STRATIFICATION (n={len(sell)})")
    print(f"{'═' * 78}")
    sell_bests = []
    for feat in features:
        b = stratify(sell, feat, n_bins=5)
        best = print_strat(f"SELL × {feat}", b)
        if best is not None:
            sell_bests.append((feat, best))

    print(f"\n  ── SELL TOP FEATURES ──")
    for feat, edge in sorted(sell_bests, key=lambda x: -x[1])[:5]:
        print(f"    {feat:<15} best edge = {edge*100:+.1f}%")

    # ═══════════════════════════════════════════════════════════
    # Side-by-side comparison
    # ═══════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 78}")
    print(f"  SIDE-BY-SIDE: BUY vs SELL")
    print(f"{'═' * 78}")
    print(f"  {'feature':<15} {'BUY best':>12} {'SELL best':>12} "
          f"{'winner':>10}")
    buy_map = dict(buy_bests)
    sell_map = dict(sell_bests)
    for feat in features:
        b_e = buy_map.get(feat, 0.0)
        s_e = sell_map.get(feat, 0.0)
        winner = 'BUY' if b_e > s_e else ('SELL' if s_e > b_e else '—')
        print(f"  {feat:<15} {b_e*100:>+11.1f}% {s_e*100:>+11.1f}% "
              f"{winner:>10}")

    # ═══════════════════════════════════════════════════════════
    # Verdict
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'═' * 78}")
    print(f"  VERDICT")
    print(f"{'═' * 78}")
    if buy_bests:
        bf, be = max(buy_bests, key=lambda x: x[1])
        print(f"  BUY  best feature: {bf:<15} edge={be*100:+.1f}%  "
              f"(vs baseline {m_buy['edge']*100:+.1f}%)")
    if sell_bests:
        sf, se = max(sell_bests, key=lambda x: x[1])
        print(f"  SELL best feature: {sf:<15} edge={se*100:+.1f}%  "
              f"(vs baseline {m_sell['edge']*100:+.1f}%)")

    if sell_bests and max(sell_bests, key=lambda x: x[1])[1] > 0.10:
        print(f"\n  ✓ SELL finds exploitable edge in some feature")
        print(f"    → يمكن إعادة تفعيل SELL بفلتر مخصص")
    else:
        print(f"\n  ✗ SELL لا يجد edge > +10%")
        print(f"    → إبقاء SELL معطلاً صحيح")

    return 0


if __name__ == '__main__':
    sys.exit(main())
