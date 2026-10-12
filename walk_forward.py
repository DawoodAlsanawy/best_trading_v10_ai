#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Walk-Forward Validation for SELL filters
==========================================
- 20 رمز
- 5 نوافذ زمنية متتالية
- لكل نافذة × لكل فلتر: edge, n, P(TP)
- التحقق النهائي: ثبات الفلتر عبر النوافذ
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
    'ARB/USDT', 'OP/USDT', 'INJ/USDT', 'SUI/USDT', 'SEI/USDT',
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
            if lo <= sl_px: return 'SL'
            if hi >= tp_px: return 'TP'
        else:
            if hi >= sl_px: return 'SL'
            if lo <= tp_px: return 'TP'
    return 'TIMEOUT'


def collect_all(ex, sym, tf, capital, n_windows):
    try:
        ohlcv = ex.fetch_ohlcv(sym, tf, limit=2000)
    except Exception:
        return []
    if not ohlcv or len(ohlcv) < 800:
        return []
    df = pd.DataFrame(ohlcv,
                      columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()
    ad = bot.process_asset(sym, df, current_capital=capital)
    if ad is None:
        return []

    n = len(ad.closes)
    start = max(ad.train_end + 1, n // 4)
    stop = n - H_BARS - 2
    if stop <= start + 100:
        return []

    span = stop - start
    boundaries = [start + int(span * i / n_windows)
                  for i in range(n_windows + 1)]
    boundaries[-1] = stop

    sigs = []
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
        outcome = simulate_outcome(ad, i, action, p0, sigma)
        if outcome == 'TIMEOUT':
            continue

        # which window?
        w_idx = n_windows - 1
        for wi in range(n_windows):
            if boundaries[wi] <= i < boundaries[wi + 1]:
                w_idx = wi
                break

        sigs.append({
            'symbol': sym, 'action': action, 'bar': i, 'window': w_idx,
            'outcome': outcome,
            'P_act': P_act, 'score': score, 'sigma': sigma,
            'friction': fric,
            'delta_gap': float(ad.delta_gap[fi]),
            'gauge_force': float(ad.gauge_force[fi]),
            'T_info': T, 'accel': abs(geo),
        })
    return sigs


def metrics(sigs):
    n = len(sigs)
    if n == 0:
        return None
    tp = sum(1 for s in sigs if s['outcome'] == 'TP')
    p = tp / n
    rw = SL_SIGMA / (SL_SIGMA + TP_SIGMA)
    return {
        'n': n, 'tp': tp, 'sl': n - tp,
        'p_tp': p, 'edge': p - rw,
        'e_r': TP_SIGMA * p - SL_SIGMA * (1 - p),
    }


# ═════════════════════════════════════════════════════════════════════
# الفلاتر
# ═════════════════════════════════════════════════════════════════════

SELL_FILTERS = [
    ("baseline",  lambda s: True),
    ("Tinfo",     lambda s: 4.86 <= s['T_info'] <= 6.32),
    ("sigma",     lambda s: 0.0097 <= s['sigma'] <= 0.0133),
    ("Tinfo_or_sigma",
        lambda s: (4.86 <= s['T_info'] <= 6.32) or (0.0097 <= s['sigma'] <= 0.0133)),
    ("Tinfo_and_sigma",
        lambda s: (4.86 <= s['T_info'] <= 6.32) and (0.0097 <= s['sigma'] <= 0.0133)),
    ("gf_mid",    lambda s: 0.105 <= s['gauge_force'] <= 0.129),
    ("Tinfo_or_gf",
        lambda s: (4.86 <= s['T_info'] <= 6.32) or (0.105 <= s['gauge_force'] <= 0.129)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeframe', default='1h')
    ap.add_argument('--n-windows', type=int, default=5)
    ap.add_argument('--capital', type=float, default=1000.0)
    ap.add_argument('--symbols', nargs='*', default=None)
    ap.add_argument('--min-n', type=int, default=8,
                    help='min signals per (window × filter) to count')
    args = ap.parse_args()

    ex = ccxt.binance({'options': {'defaultType': 'future'}})
    bot.CFG.timeframe = args.timeframe
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)
    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))

    print(f"TF: {args.timeframe}  windows: {args.n_windows}  "
          f"SL={SL_SIGMA}σ  TP={TP_SIGMA}σ  H={H_BARS}")
    print(f"SL/TP symétrique → RW = 50%\n")

    syms = args.symbols if args.symbols else SYMBOLS
    all_sigs = []
    print("=" * 78)
    print(f"{'Symbol':<14} {'total':>7} {'BUY':>6} {'SELL':>6} "
          f"{'W0':>5} {'W1':>5} {'W2':>5} {'W3':>5} {'W4':>5}")
    print("=" * 78)
    for sym in syms:
        try:
            s = collect_all(ex, sym, args.timeframe,
                            args.capital, args.n_windows)
        except Exception as e:
            print(f"{sym:<14} ERROR: {e}")
            continue
        if not s:
            print(f"{sym:<14} (no signals)")
            continue
        buy = sum(1 for x in s if x['action'] == 'BUY')
        sell = sum(1 for x in s if x['action'] == 'SELL')
        counts = [sum(1 for x in s if x['window'] == w)
                  for w in range(args.n_windows)]
        print(f"{sym:<14} {len(s):>7} {buy:>6} {sell:>6} "
              + " ".join(f"{c:>5}" for c in counts))
        all_sigs.extend(s)

    print("=" * 78)
    print(f"TOTAL signals: {len(all_sigs)}\n")

    if not all_sigs:
        print("No signals"); return 1

    # ═══════════════════════════════════════════════════════════
    # Baseline: BUY and SELL across windows
    # ═══════════════════════════════════════════════════════════
    print("═" * 78)
    print("  BASELINE per window (reference)")
    print("═" * 78)
    print(f"  {'window':<8} {'BUY_n':>6} {'BUY_edg':>9} "
          f"{'SELL_n':>7} {'SELL_edg':>9}")
    for w in range(args.n_windows):
        buy_w = [s for s in all_sigs
                 if s['action'] == 'BUY' and s['window'] == w]
        sell_w = [s for s in all_sigs
                  if s['action'] == 'SELL' and s['window'] == w]
        mb = metrics(buy_w)
        ms = metrics(sell_w)
        print(f"  W{w:<7} "
              f"{(mb['n'] if mb else 0):>6} "
              f"{(mb['edge']*100 if mb else 0):>+8.1f}% "
              f"{(ms['n'] if ms else 0):>7} "
              f"{(ms['edge']*100 if ms else 0):>+8.1f}%")

    # ═══════════════════════════════════════════════════════════
    # Walk-Forward table: filter × window
    # ═══════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 78}")
    print("  WALK-FORWARD: SELL filter × window → edge%")
    print(f"{'═' * 78}")

    sell_all = [s for s in all_sigs if s['action'] == 'SELL']

    print(f"  {'filter':<22}", end="")
    for w in range(args.n_windows):
        print(f"  {'W'+str(w):>8}", end="")
    print(f"  {'profitable':>11}  {'mean':>8}")

    summary = []
    for fname, cond in SELL_FILTERS:
        row_edges = []
        row_counts = []
        for w in range(args.n_windows):
            subset = [s for s in sell_all
                      if s['window'] == w and cond(s)]
            m = metrics(subset)
            if m is None or m['n'] < args.min_n:
                row_edges.append(None)
                row_counts.append(0)
            else:
                row_edges.append(m['edge'])
                row_counts.append(m['n'])

        # Count profitable windows
        valid_edges = [e for e in row_edges if e is not None]
        profitable = sum(1 for e in valid_edges if e > 0.05)
        total_valid = len(valid_edges)
        mean_edge = float(np.mean(valid_edges)) if valid_edges else 0.0

        print(f"  {fname:<22}", end="")
        for e in row_edges:
            if e is None:
                print(f"  {'---':>8}", end="")
            else:
                print(f"  {e*100:>+7.1f}%", end="")
        print(f"  {f'{profitable}/{total_valid}':>11}  "
              f"{mean_edge*100:>+7.1f}%")

        summary.append({
            'name': fname,
            'edges': row_edges,
            'profitable': profitable,
            'total_valid': total_valid,
            'mean': mean_edge,
        })

    # ═══════════════════════════════════════════════════════════
    # Ranking
    # ═══════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 78}")
    print("  RANKING (sorted by mean edge, requires ≥3 valid windows)")
    print(f"{'═' * 78}")
    print(f"  {'filter':<22} {'windows':>9} {'prof':>6} "
          f"{'mean_edge':>11} {'verdict':>12}")
    ranked = sorted(
        [s for s in summary if s['total_valid'] >= 3],
        key=lambda x: -x['mean'],
    )
    for s in ranked:
        if s['profitable'] >= 4:
            verdict = "STRONG"
        elif s['profitable'] >= 3:
            verdict = "MODERATE"
        elif s['profitable'] >= 2:
            verdict = "WEAK"
        else:
            verdict = "FAIL"
        print(f"  {s['name']:<22} "
              f"{s['total_valid']:>9} {s['profitable']:>6} "
              f"{s['mean']*100:>+10.1f}% {verdict:>12}")

    # ═══════════════════════════════════════════════════════════
    # Best filter: per-window detail
    # ═══════════════════════════════════════════════════════════
    if ranked:
        best = ranked[0]
        print(f"\n\n{'═' * 78}")
        print(f"  BEST FILTER DETAIL: {best['name']}")
        print(f"{'═' * 78}")
        cond = dict(SELL_FILTERS)[best['name']]
        for w in range(args.n_windows):
            subset = [s for s in sell_all
                      if s['window'] == w and cond(s)]
            m = metrics(subset)
            if m is None:
                print(f"  W{w}: (no signals)")
                continue
            print(f"  W{w}: n={m['n']:>4}  "
                  f"P(TP)={m['p_tp']*100:>5.1f}%  "
                  f"edge={m['edge']*100:>+6.1f}%  "
                  f"E[R]={m['e_r']:>+7.3f}")

    # ═══════════════════════════════════════════════════════════
    # Overall verdict
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'═' * 78}")
    print("  OVERALL VERDICT")
    print(f"{'═' * 78}")

    if not ranked:
        print("  ⚠ Not enough valid windows to judge")
        return 1

    best = ranked[0]
    if best['profitable'] >= 4:
        print(f"  ✓ STRONG: {best['name']} رابح في {best['profitable']}/"
              f"{best['total_valid']} نافذة")
        print(f"    → حافة حقيقية عبر الزمن")
        print(f"    → يمكن تفعيل SELL بهذا الفلتر")
    elif best['profitable'] >= 3:
        print(f"  ~ MODERATE: {best['name']} رابح في "
              f"{best['profitable']}/{best['total_valid']} نافذة")
        print(f"    → حافة ضعيفة، تستحق مزيداً من التحقق")
        print(f"    → تفعيل SELL مشروط بفلتر محافظ")
    else:
        print(f"  ✗ WEAK: best filter رابح في "
              f"{best['profitable']}/{best['total_valid']} نافذة")
        print(f"    → لا حافة حقيقية")
        print(f"    → SELL يبقى معطّلاً")

    return 0


if __name__ == '__main__':
    sys.exit(main())
