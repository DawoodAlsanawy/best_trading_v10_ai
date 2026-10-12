#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مختبر v2: يقارن نفس الصيغ لكن بمحاكاة TP/SL واقعية:
  - TP = R × SL (لاختبار R = 1، 2، 3)
  - SL صغير ومتعدد (1σ، 2σ، 3σ)
  - W_hold = MAX_HOLD الفعلي (168 على 1h، 42 على 4h)
  - Trailing SL بعد +1R
  - Baseline: entry = current (بلا إزاحة)
"""
import argparse
import sys
import numpy as np
import pandas as pd
import ccxt

import trading_2_live2_1 as bot


def f_current(sigma, price, P_act, friction, T_info, dF, delta, G):
    return 0.02 * sigma * 3.0 * price

def f_quad(sigma, price, P_act, friction, T_info, dF, delta, G):
    return sigma * price * (1.0 - P_act) ** 2 * 0.20

def f_baseline_zero(sigma, price, P_act, friction, T_info, dF, delta, G):
    """صفر إزاحة = دخول عند السعر الحالي (baseline)"""
    return 0.0

def f_tick(sigma, price, P_act, friction, T_info, dF, delta, G):
    """بس 1 tick"""
    return price * 1e-5

def f_sl_frac_1(sigma, price, P_act, friction, T_info, dF, delta, G):
    """1% من مسافة SL الفيزيائية"""
    return 3.0 * sigma * price * 0.01

FORMULAS = [
    ("F_baseline",  f_baseline_zero),
    ("F_tick",      f_tick),
    ("F_current",   f_current),
    ("F_quad",      f_quad),
    ("F_slfrac_1",  f_sl_frac_1),
]


def simulate(ad, sig_bar, entry_px, sigma_t, sl_k, R, W_hold,
             use_trailing=True):
    """محاكاة واحدة بلون R معين و SL=k×σ."""
    sl_dist = sl_k * sigma_t * entry_px
    sl_px = entry_px - sl_dist
    tp_px = entry_px + sl_dist * R
    trail_active = False
    peak = entry_px
    trail_sl = sl_px

    for j in range(sig_bar + 1, min(sig_bar + 1 + W_hold, len(ad.closes))):
        hi = float(ad.highs[j]); lo = float(ad.lows[j])
        # SL first (pessimistic)
        if lo <= trail_sl:
            return 'SL' if not trail_active else 'TRAIL_SL'
        if hi >= tp_px:
            return 'TP'
        # Trailing after 1R
        if use_trailing:
            mfe = (hi - entry_px) / sl_dist
            if mfe >= 1.0:
                trail_active = True
                if hi > peak:
                    peak = hi
                new_sl = peak - sl_dist * 0.5
                if new_sl > trail_sl:
                    trail_sl = new_sl
    return 'TIMEOUT'


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--bars", type=int, default=300)
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--sl_k", type=float, default=1.0,
                   help="SL = k × σ")
    p.add_argument("--R", type=float, default=2.0,
                   help="TP = R × SL")
    args = p.parse_args()

    ex = ccxt.binance({'options': {'defaultType': 'future'}})
    bot.CFG.timeframe = args.timeframe
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)
    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))

    W_enter = max(2, int(round(8.0 * bot.CFG.TF_SCALE)))
    W_hold = int(round(168.0 * bot.CFG.TF_SCALE))

    print(f"Symbol: {args.symbol}  TF: {args.timeframe}")
    print(f"W_enter={W_enter}  W_hold={W_hold}  "
          f"SL={args.sl_k}σ  R={args.R}\n")

    ohlcv = ex.fetch_ohlcv(args.symbol, args.timeframe, limit=1000)
    if not ohlcv:
        print("No data"); return 1
    df = pd.DataFrame(ohlcv, columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()

    ad = bot.process_asset(args.symbol, df, current_capital=args.capital)
    if ad is None:
        print("process_asset None"); return 1

    n = len(ad.closes)
    start = max(ad.train_end + 1, n - args.bars)
    stop = n - W_hold - W_enter - 2

    # جمع إشارات BUY فقط
    sigs = []
    for i in range(start, stop):
        fi = i - ad.feat_start
        if fi < 0 or fi >= len(ad.score): continue
        p_now = float(ad.closes[i])
        sigma = float(ad.E_therm[fi])
        if not np.isfinite(sigma) or sigma <= 1e-6: continue
        fric = float(ad.friction[fi])
        T = float(ad.T_info[fi])
        geo = float(ad.geodesic_accel[fi])
        P_act = float(np.exp(-fric / ((abs(geo)+1e-9) * T)))
        if P_act < 0.35: continue
        # z_dev
        win = ad.closes[max(0, i - bot.CFG.N): i]
        if len(win) < 2: continue
        sd = float(np.std(win))
        if sd <= 1e-12: continue
        z = (p_now - float(np.mean(win))) / sd
        if z >= -1.5: continue  # BUY only
        if ad.score[fi] < bot.CFG.MIN_SCORE: continue

        sigs.append({'bar': i, 'fi': fi, 'price': p_now, 'sigma': sigma,
                     'P_act': P_act, 'friction': fric, 'T_info': T,
                     'dF': float(ad.dF[fi]), 'delta': float(ad.delta_gap[fi]),
                     'G': float(ad.gauge_force[fi])})

    print(f"Signals: {len(sigs)}\n")
    if not sigs: return 0

    print("=" * 105)
    print(f"{'Formula':<12} {'mean_eps':>9} {'touch%':>7} "
          f"{'TP%':>6} {'SL%':>6} {'TRAIL%':>7} {'TO%':>6} "
          f"{'win_rate':>9} {'net_R':>8}")
    print("=" * 105)

    results = []
    for fname, fn in FORMULAS:
        eps_list = []
        counts = {'TP': 0, 'SL': 0, 'TRAIL_SL': 0, 'TIMEOUT': 0, 'NO_TOUCH': 0}
        touched = 0
        n_sig = 0
        net_R_list = []

        for s in sigs:
            i = s['bar']
            eps = fn(s['sigma'], s['price'], s['P_act'], s['friction'],
                     s['T_info'], s['dF'], s['delta'], s['G'])
            if not np.isfinite(eps) or eps < 0:
                continue
            entry = s['price'] - eps
            n_sig += 1
            eps_list.append(eps / s['price'] * 1e4)

            # مرحلة اللمس
            touch_bar = -1
            for bar in range(i+1, min(i+1+W_enter, n)):
                if ad.lows[bar] <= entry:
                    touch_bar = bar; break

            if touch_bar < 0:
                counts['NO_TOUCH'] += 1
                net_R_list.append(0.0)
                continue

            touched += 1
            fi_t = touch_bar - ad.feat_start
            if fi_t < 0 or fi_t >= len(ad.E_therm):
                counts['NO_TOUCH'] += 1; net_R_list.append(0.0); continue
            sigma_t = float(ad.E_therm[fi_t])
            if not np.isfinite(sigma_t) or sigma_t <= 1e-6:
                counts['NO_TOUCH'] += 1; net_R_list.append(0.0); continue

            res = simulate(ad, touch_bar, entry, sigma_t,
                           args.sl_k, args.R, W_hold)
            counts[res] += 1
            if res == 'TP':
                net_R_list.append(args.R)
            elif res == 'TRAIL_SL':
                net_R_list.append(0.5)  # تقدير تقريبي
            elif res == 'SL':
                net_R_list.append(-1.0)
            else:
                net_R_list.append(0.0)

        if n_sig == 0: continue
        touch_pct = 100.0 * touched / n_sig
        tp_pct = 100.0 * counts['TP'] / max(touched, 1)
        sl_pct = 100.0 * counts['SL'] / max(touched, 1)
        trail_pct = 100.0 * counts['TRAIL_SL'] / max(touched, 1)
        to_pct = 100.0 * counts['TIMEOUT'] / max(touched, 1)
        win_rate = tp_pct
        net_R = float(np.mean(net_R_list))

        results.append({'name': fname, 'mean_eps': np.mean(eps_list),
                        'touch': touch_pct, 'tp': tp_pct, 'sl': sl_pct,
                        'net_R': net_R, 'n_touched': touched, 'n_sig': n_sig})

        print(f"{fname:<12} {np.mean(eps_list):>8.2f}b {touch_pct:>6.1f}% "
              f"{tp_pct:>5.1f}% {sl_pct:>5.1f}% {trail_pct:>6.1f}% "
              f"{to_pct:>5.1f}% {win_rate:>8.1f}% {net_R:>+7.3f}")

    print("=" * 105)
    print("\nالترتيب حسب net_R (متوسط R لكل إشارة):")
    for r in sorted(results, key=lambda x: -x['net_R']):
        print(f"  {r['name']:<12} net_R={r['net_R']:>+6.3f}  "
              f"touch={r['touch']:>5.1f}%  TP={r['tp']:>5.1f}%  "
              f"SL={r['sl']:>5.1f}%  eps={r['mean_eps']:>5.2f}b  "
              f"(n={r['n_touched']}/{r['n_sig']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
