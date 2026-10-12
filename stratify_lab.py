#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stratification Lab
==================
يجمع إشارات BUY و SELL من 15 رمزاً، ثم يختبر:
  - هل توجد خاصية فيزيائية تُنتج تدرجاً رتيباً في P(TP first)?
  - أم أن النتائج ضوضاء بحتة؟

لا Trailing، لا Breakeven، لا Apex، لا Partial. فقط SL/TP.

SL = 1.5 × σ_bar
TP = 1.5 × σ_bar
RW_baseline = 0.5  (متماثل)
edge = P(TP first) - 0.5
E[R] = 3 × P - 1.5
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


# ═════════════════════════════════════════════════════════════════════
# محاكاة بسيطة: SL/TP فقط، من الشمعة التالية للإشارة
# ═════════════════════════════════════════════════════════════════════

def simulate_outcome(ad, sig_bar, action, p0, sigma0,
                     sl_sigma=SL_SIGMA, tp_sigma=TP_SIGMA, H=H_BARS):
    """
    Returns: ('SL'|'TP'|'TIMEOUT', bars_to_resolution_or_None)
    Pessimistic: if SL and TP at same bar, SL wins.
    """
    n = len(ad.closes)
    if action == 'BUY':
        sl_px = p0 * np.exp(-sl_sigma * sigma0)
        tp_px = p0 * np.exp(+tp_sigma * sigma0)
    else:
        sl_px = p0 * np.exp(+sl_sigma * sigma0)
        tp_px = p0 * np.exp(-tp_sigma * sigma0)

    for j in range(sig_bar + 1, min(sig_bar + 1 + H, n)):
        hi = float(ad.highs[j])
        lo = float(ad.lows[j])
        if action == 'BUY':
            if lo <= sl_px:
                return 'SL', j - sig_bar
            if hi >= tp_px:
                return 'TP', j - sig_bar
        else:
            if hi >= sl_px:
                return 'SL', j - sig_bar
            if lo <= tp_px:
                return 'TP', j - sig_bar
    return 'TIMEOUT', None


# ═════════════════════════════════════════════════════════════════════
# جمع إشارات رمز واحد
# ═════════════════════════════════════════════════════════════════════

def collect_from_symbol(ex, sym, tf, bars_to_test, capital):
    try:
        ohlcv = ex.fetch_ohlcv(sym, tf, limit=2000)
    except Exception as e:
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
        score = float(ad.score[fi])
        if score < bot.CFG.MIN_SCORE:
            continue

        outcome, bars = simulate_outcome(ad, i, action, p0, sigma)
        if outcome == 'TIMEOUT':
            continue

        signals.append({
            'symbol': sym,
            'action': action,
            'bar': i,
            'outcome': outcome,
            'bars_to_resolve': bars,
            # Features
            'z_dev': float(z),
            'abs_z': float(abs(z)),
            'P_act': P_act,
            'score': score,
            'sigma': sigma,
            'friction': fric,
            'delta_gap': float(ad.delta_gap[fi]),
            'gauge_force': float(ad.gauge_force[fi]),
            'T_info': T,
            'accel': abs(geo),
        })
    return signals


# ═════════════════════════════════════════════════════════════════════
# حساب المقاييس لشريحة
# ═════════════════════════════════════════════════════════════════════

def segment_metrics(signals):
    n = len(signals)
    if n == 0:
        return None
    tp = sum(1 for s in signals if s['outcome'] == 'TP')
    sl = n - tp
    p_tp = tp / n
    rw = SL_SIGMA / (SL_SIGMA + TP_SIGMA)  # = 0.5
    edge = p_tp - rw
    e_r = TP_SIGMA * p_tp - SL_SIGMA * (1 - p_tp)
    return {
        'n': n, 'tp': tp, 'sl': sl,
        'p_tp': p_tp, 'edge': edge, 'e_r': e_r,
    }


# ═════════════════════════════════════════════════════════════════════
# التقسيم الطبقي على خاصية واحدة
# ═════════════════════════════════════════════════════════════════════

def stratify(all_signals, feature, n_bins=5):
    values = np.array([s[feature] for s in all_signals], dtype=np.float64)
    values = values[np.isfinite(values)]
    if len(values) < 30:
        return None
    qs = np.quantile(values, np.linspace(0, 1, n_bins + 1))
    # Handle degenerate quantiles
    qs = np.unique(qs)
    if len(qs) < 3:
        return None
    bins = []
    for i in range(len(qs) - 1):
        lo, hi = qs[i], qs[i + 1]
        if i == len(qs) - 2:
            subset = [s for s in all_signals
                      if lo <= s[feature] <= hi]
        else:
            subset = [s for s in all_signals
                      if lo <= s[feature] < hi]
        m = segment_metrics(subset)
        if m is None:
            continue
        m['lo'] = float(lo)
        m['hi'] = float(hi)
        bins.append(m)
    return bins


# ═════════════════════════════════════════════════════════════════════
# عرض جدول
# ═════════════════════════════════════════════════════════════════════

def print_strat(feature_name, bins, fmt=".4g"):
    if bins is None or len(bins) == 0:
        print(f"\n[{feature_name}] — insufficient data")
        return
    print(f"\n{'─' * 78}")
    print(f"Stratify by: {feature_name}")
    print(f"{'─' * 78}")
    print(f"  {'bin range':<24} {'n':>5} {'TP':>5} {'SL':>5} "
          f"{'P(TP)':>8} {'edge':>8} {'E[R]':>8}")
    edges = []
    for b in bins:
        rng = f"[{b['lo']:{fmt}}, {b['hi']:{fmt}}]"
        edge_pct = f"{b['edge']*100:+.1f}%"
        print(f"  {rng:<24} {b['n']:>5} {b['tp']:>5} {b['sl']:>5} "
              f"{b['p_tp']*100:>7.1f}% {edge_pct:>8} {b['e_r']:>+8.3f}")
        edges.append(b['edge'])
    # Monotonicity check
    if len(edges) >= 3:
        diffs = np.diff(edges)
        n_pos = sum(1 for d in diffs if d > 0.02)
        n_neg = sum(1 for d in diffs if d < -0.02)
        if n_pos == len(diffs):
            verdict = "STRICTLY INCREASING ✓"
        elif n_neg == len(diffs):
            verdict = "STRICTLY DECREASING ✓"
        elif n_pos + n_neg <= 1:
            verdict = "MOSTLY MONOTONIC ~"
        else:
            verdict = "NO TREND"
        spread = max(edges) - min(edges)
        print(f"  → Trend: {verdict}  |  Edge spread: "
              f"{spread*100:+.1f}%")


# ═════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeframe', default='1h')
    ap.add_argument('--bars', type=int, default=800)
    ap.add_argument('--capital', type=float, default=1000.0)
    ap.add_argument('--symbols', nargs='*', default=None)
    args = ap.parse_args()

    ex = ccxt.binance({'options': {'defaultType': 'future'}})
    bot.CFG.timeframe = args.timeframe
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)
    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))

    print(f"TF: {args.timeframe}  bars_to_test: {args.bars}  "
          f"H: {H_BARS}  SL: {SL_SIGMA}σ  TP: {TP_SIGMA}σ")
    print(f"SL/TP symétrique → RW baseline = 50.0%\n")

    syms = args.symbols if args.symbols else SYMBOLS
    all_signals = []
    print("=" * 78)
    print(f"{'Symbol':<14} {'N':>5} {'TP':>5} {'SL':>5} "
          f"{'P(TP)':>8} {'edge':>8} {'E[R]':>8}")
    print("=" * 78)

    per_symbol = []
    for sym in syms:
        try:
            s = collect_from_symbol(ex, sym, args.timeframe,
                                     args.bars, args.capital)
        except Exception as e:
            print(f"{sym:<14} ERROR: {e}")
            continue
        if not s:
            print(f"{sym:<14} (no signals)")
            continue
        m = segment_metrics(s)
        per_symbol.append((sym, m))
        print(f"{sym:<14} {m['n']:>5} {m['tp']:>5} {m['sl']:>5} "
              f"{m['p_tp']*100:>7.1f}% "
              f"{m['edge']*100:>+7.1f}% {m['e_r']:>+8.3f}")
        all_signals.extend(s)

    print("=" * 78)
    print(f"TOTAL signals: {len(all_signals)}")
    if len(all_signals) < 30:
        print("\n⚠ SAMPLE TOO SMALL (< 30) — results meaningless.")
        return 1

    # Pooled
    m_all = segment_metrics(all_signals)
    print(f"\n═══ POOLED ═══")
    print(f"  N     = {m_all['n']}")
    print(f"  TP    = {m_all['tp']}  SL = {m_all['sl']}")
    print(f"  P(TP) = {m_all['p_tp']*100:.1f}%")
    print(f"  Edge  = {m_all['edge']*100:+.1f}%  (vs RW 50%)")
    print(f"  E[R]  = {m_all['e_r']:+.3f}")

    # BUY vs SELL
    buy = [s for s in all_signals if s['action'] == 'BUY']
    sell = [s for s in all_signals if s['action'] == 'SELL']
    print(f"\n═══ DIRECTION SPLIT ═══")
    for label, subset in [('BUY', buy), ('SELL', sell)]:
        if not subset:
            continue
        m = segment_metrics(subset)
        print(f"  {label:<5} n={m['n']:>4}  "
              f"P(TP)={m['p_tp']*100:>5.1f}%  "
              f"edge={m['edge']*100:>+6.1f}%  "
              f"E[R]={m['e_r']:>+7.3f}")

    # Stratification
    features = ['abs_z', 'P_act', 'score', 'sigma',
                'friction', 'delta_gap', 'gauge_force',
                'T_info', 'accel']

    print(f"\n\n{'═' * 78}")
    print(f"  STRATIFICATION ANALYSIS (each feature → 5 quantiles)")
    print(f"{'═' * 78}")

    winners = []
    for feat in features:
        bins = stratify(all_signals, feat, n_bins=5)
        print_strat(feat, bins)
        if bins is not None and len(bins) >= 3:
            edges = [b['edge'] for b in bins]
            spread = max(edges) - min(edges)
            winners.append((feat, spread))

    # Best feature
    print(f"\n{'═' * 78}")
    print(f"  TOP FEATURES BY EDGE SPREAD")
    print(f"{'═' * 78}")
    for feat, spread in sorted(winners, key=lambda x: -x[1])[:5]:
        print(f"  {feat:<15} spread = {spread*100:+.1f}%")

    # Verdict
    print(f"\n{'═' * 78}")
    print(f"  VERDICT")
    print(f"{'═' * 78}")
    if winners:
        best_feat, best_spread = max(winners, key=lambda x: x[1])
        if best_spread > 0.15:
            print(f"  ✓ STRONG feature: {best_feat} "
                  f"(spread {best_spread*100:.1f}%)")
            print(f"    → البوت يمكن أن يستفيد من فلترة إضافية على هذه الخاصية")
        elif best_spread > 0.08:
            print(f"  ~ MODERATE feature: {best_feat} "
                  f"(spread {best_spread*100:.1f}%)")
        else:
            print(f"  ✗ NO exploitable feature found "
                  f"(best spread {best_spread*100:.1f}% < 8%)")
            print(f"    → الإشارة لا تحتوي معلومات كافية في هذه الخصائص")

    return 0


if __name__ == '__main__':
    sys.exit(main())
