#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SELL Filter Validation
========================
- يجمع BUY و SELL من 20 رمزاً
- يقسم البيانات إلى Train (60%) / Test (40%)
- يختبر مرشحي فلاتر SELL على Train، ثم يتحقق على Test
- يقارن مع BUY baseline و BUY+SELL المُفلتر
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


def collect_symbol(ex, sym, tf, bars_to_test, capital, train_frac=0.6):
    try:
        ohlcv = ex.fetch_ohlcv(sym, tf, limit=2000)
    except Exception:
        return [], []
    if not ohlcv or len(ohlcv) < 500:
        return [], []
    df = pd.DataFrame(ohlcv,
                      columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()
    ad = bot.process_asset(sym, df, current_capital=capital)
    if ad is None:
        return [], []

    n = len(ad.closes)
    start = max(ad.train_end + 1, n - bars_to_test)
    stop = n - H_BARS - 2
    if stop <= start + 20:
        return [], []
    split_bar = start + int((stop - start) * train_frac)

    train_sigs, test_sigs = [], []
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
        sig = {
            'symbol': sym, 'action': action, 'bar': i,
            'outcome': outcome,
            'z_dev': float(z), 'abs_z': float(abs(z)),
            'P_act': P_act, 'score': score, 'sigma': sigma,
            'friction': fric,
            'delta_gap': float(ad.delta_gap[fi]),
            'gauge_force': float(ad.gauge_force[fi]),
            'T_info': T, 'accel': abs(geo),
        }
        if i < split_bar:
            train_sigs.append(sig)
        else:
            test_sigs.append(sig)
    return train_sigs, test_sigs


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
# مرشحو فلاتر SELL
# ═════════════════════════════════════════════════════════════════════

SELL_FILTERS = [
    ("baseline",         lambda s: True),
    ("sigma_mid",        lambda s: 0.0097 <= s['sigma'] <= 0.0133),
    ("sigma_hi",         lambda s: s['sigma'] >= 0.0097),
    ("Tinfo_mid",        lambda s: 4.86 <= s['T_info'] <= 6.32),
    ("gf_mid",           lambda s: 0.105 <= s['gauge_force'] <= 0.129),
    ("Pact_hi",          lambda s: 0.818 <= s['P_act'] <= 0.937),
    ("sig_and_Tinfo",    lambda s: 0.0097 <= s['sigma'] <= 0.0133
                                    and 4.86 <= s['T_info'] <= 6.32),
    ("sig_and_gf",       lambda s: 0.0097 <= s['sigma'] <= 0.0133
                                    and 0.105 <= s['gauge_force'] <= 0.129),
    ("sig_or_Tinfo",     lambda s: (0.0097 <= s['sigma'] <= 0.0133)
                                    or (4.86 <= s['T_info'] <= 6.32)),
    ("sig_and_Tinfo_and_gf", lambda s:
        0.0097 <= s['sigma'] <= 0.0133
        and 4.86 <= s['T_info'] <= 6.32
        and 0.105 <= s['gauge_force'] <= 0.129),
    ("sig_hi_or_Tinfo_hi", lambda s:
        s['sigma'] >= 0.0097 or s['T_info'] >= 4.86),
]


def apply_filter(sigs, cond):
    return [s for s in sigs if cond(s)]


def print_metrics_row(label, m, tag=''):
    if m is None:
        print(f"  {label:<26} {'(empty)':>60}")
        return
    tag_s = f"  {tag}" if tag else ''
    print(f"  {label:<26} "
          f"n={m['n']:>4}  "
          f"P(TP)={m['p_tp']*100:>5.1f}%  "
          f"edge={m['edge']*100:>+6.1f}%  "
          f"E[R]={m['e_r']:>+6.3f}{tag_s}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeframe', default='1h')
    ap.add_argument('--bars', type=int, default=1500)
    ap.add_argument('--capital', type=float, default=1000.0)
    ap.add_argument('--train-frac', type=float, default=0.6)
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

    print(f"TF: {args.timeframe}  bars={args.bars}  "
          f"train_frac={args.train_frac}")
    print(f"SL={SL_SIGMA}σ  TP={TP_SIGMA}σ  H={H_BARS}  RW=50%\n")

    syms = args.symbols if args.symbols else SYMBOLS
    tr_signals, te_signals = [], []
    print("=" * 78)
    print(f"{'Symbol':<14} {'Train':>7} {'Test':>7} "
          f"{'BUY_tr':>7} {'SELL_tr':>8} "
          f"{'BUY_te':>7} {'SELL_te':>8}")
    print("=" * 78)
    for sym in syms:
        try:
            tr, te = collect_symbol(ex, sym, args.timeframe,
                                     args.bars, args.capital,
                                     train_frac=args.train_frac)
        except Exception as e:
            print(f"{sym:<14} ERROR: {e}")
            continue
        if not tr and not te:
            print(f"{sym:<14} (no signals)")
            continue
        bt = sum(1 for s in tr if s['action'] == 'BUY')
        st = sum(1 for s in tr if s['action'] == 'SELL')
        be = sum(1 for s in te if s['action'] == 'BUY')
        se = sum(1 for s in te if s['action'] == 'SELL')
        print(f"{sym:<14} {len(tr):>7} {len(te):>7} "
              f"{bt:>7} {st:>8} {be:>7} {se:>8}")
        tr_signals.extend(tr)
        te_signals.extend(te)

    print("=" * 78)
    print(f"Total: train={len(tr_signals)}  test={len(te_signals)}\n")

    if len(tr_signals) < 50 or len(te_signals) < 30:
        print("⚠ Sample too small"); return 1

    # ═══════════════════════════════════════════════════════════
    # Baseline BUY / SELL on Train and Test
    # ═══════════════════════════════════════════════════════════
    print("═" * 78)
    print("  BASELINE (no filter)")
    print("═" * 78)
    for split_name, sigs in [("TRAIN", tr_signals), ("TEST", te_signals)]:
        buy = [s for s in sigs if s['action'] == 'BUY']
        sell = [s for s in sigs if s['action'] == 'SELL']
        all_s = sigs
        print(f"\n  [{split_name}]")
        print_metrics_row("BUY baseline", metrics(buy))
        print_metrics_row("SELL baseline", metrics(sell))
        print_metrics_row("POOLED baseline", metrics(all_s))

    # ═══════════════════════════════════════════════════════════
    # SELL filters: apply to TRAIN and TEST
    # ═══════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 78}")
    print("  SELL FILTER CANDIDATES")
    print(f"{'═' * 78}")

    sell_train = [s for s in tr_signals if s['action'] == 'SELL']
    sell_test = [s for s in te_signals if s['action'] == 'SELL']

    results = []
    for fname, cond in SELL_FILTERS:
        tr_f = apply_filter(sell_train, cond)
        te_f = apply_filter(sell_test, cond)
        m_tr = metrics(tr_f)
        m_te = metrics(te_f)
        print(f"\n  ── {fname} ──")
        print_metrics_row("Train", m_tr)
        print_metrics_row("Test", m_te)
        if m_tr and m_te:
            results.append({
                'name': fname,
                'tr_n': m_tr['n'], 'tr_edge': m_tr['edge'],
                'te_n': m_te['n'], 'te_edge': m_te['edge'],
                'te_p': m_te['p_tp'],
            })

    # ═══════════════════════════════════════════════════════════
    # Ranking by TEST edge
    # ═══════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 78}")
    print("  RANKING (by TEST edge, requires test_n >= 20)")
    print(f"{'═' * 78}")
    print(f"  {'filter':<26} {'tr_n':>5} {'tr_edge':>9} "
          f"{'te_n':>5} {'te_edge':>9} {'te_P(TP)':>10}")
    valid = [r for r in results if r['te_n'] >= 20]
    for r in sorted(valid, key=lambda x: -x['te_edge']):
        print(f"  {r['name']:<26} {r['tr_n']:>5} "
              f"{r['tr_edge']*100:>+8.1f}% "
              f"{r['te_n']:>5} {r['te_edge']*100:>+8.1f}% "
              f"{r['te_p']*100:>9.1f}%")

    # ═══════════════════════════════════════════════════════════
    # Combined BUY + filtered SELL
    # ═══════════════════════════════════════════════════════════
    print(f"\n\n{'═' * 78}")
    print("  PORTFOLIO: BUY + SELL_filtered")
    print(f"{'═' * 78}")
    buy_train = [s for s in tr_signals if s['action'] == 'BUY']
    buy_test = [s for s in te_signals if s['action'] == 'BUY']

    # Try each SELL filter and combine with all BUY
    for fname, cond in SELL_FILTERS:
        if fname == 'baseline':
            continue
        sell_tr_f = apply_filter(sell_train, cond)
        sell_te_f = apply_filter(sell_test, cond)
        if len(sell_tr_f) < 20 or len(sell_te_f) < 15:
            continue
        combined_tr = buy_train + sell_tr_f
        combined_te = buy_test + sell_te_f
        m_tr = metrics(combined_tr)
        m_te = metrics(combined_te)
        if m_tr and m_te:
            print(f"\n  ── BUY + SELL[{fname}] ──")
            print_metrics_row("Train", m_tr)
            print_metrics_row("Test", m_te)

    # ═══════════════════════════════════════════════════════════
    # Verdict
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'═' * 78}")
    print("  VERDICT")
    print(f"{'═' * 78}")

    sell_base_tr = metrics(sell_train)
    sell_base_te = metrics(sell_test)
    print(f"\n  SELL baseline:  "
          f"train edge={sell_base_tr['edge']*100:+.1f}%, "
          f"test edge={sell_base_te['edge']*100:+.1f}%")

    if valid:
        best = max(valid, key=lambda x: x['te_edge'])
        print(f"\n  Best filter by TEST edge: {best['name']}")
        print(f"    Train: n={best['tr_n']}, edge={best['tr_edge']*100:+.1f}%")
        print(f"    Test:  n={best['te_n']}, edge={best['te_edge']*100:+.1f}%")
        # Check consistency
        tr_ok = best['tr_edge'] > 0.05
        te_ok = best['te_edge'] > 0.05
        if tr_ok and te_ok:
            print(f"\n  ✓ CONSISTENT: edge > +5% on both train and test")
            print(f"    → يمكن تفعيل SELL بهذا الفلتر")
        elif tr_ok and not te_ok:
            print(f"\n  ✗ OVERFITTING: edge strong on train, weak on test")
            print(f"    → لا يُنصح بتفعيل SELL بهذا الفلتر")
        else:
            print(f"\n  ✗ WEAK: no filter beats baseline meaningfully")

    return 0


if __name__ == '__main__':
    sys.exit(main())
