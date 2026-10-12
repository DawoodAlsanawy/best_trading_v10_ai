#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مختبر المعادلات: يقارن 8 صيغ لإزاحة الدخول على فيزياء البوت الحقيقي.
لا يعمل أي تعديل على البوت.
"""
import argparse
import sys
import numpy as np
import pandas as pd
import ccxt

import trading_2_live2_1 as bot


# ═════════════════════════════════════════════════════════════════════
# الصيغ المرشّحة
# ═════════════════════════════════════════════════════════════════════

def f_current(sigma, price, P_act, friction, T_info, dF, delta, G):
    """الصيغة الحالية: 0.02 × σ × adv_mult(=3) × price"""
    return 0.02 * sigma * 3.0 * price


def f_p_act_linear(sigma, price, P_act, friction, T_info, dF, delta, G):
    """إزاحة خطية في (1-P_act)."""
    return sigma * price * (1.0 - P_act) * 0.10


def f_p_act_quad(sigma, price, P_act, friction, T_info, dF, delta, G):
    """إزاحة تربيعية في (1-P_act)."""
    return sigma * price * (1.0 - P_act) ** 2 * 0.20


def f_neg_log(sigma, price, P_act, friction, T_info, dF, delta, G):
    """إزاحة لوغاريتمية: تزداد كلما انخفضت P_act."""
    P_act_safe = max(P_act, 0.35)
    return sigma * price * (-np.log(P_act_safe)) * 0.15


def f_sl_frac(sigma, price, P_act, friction, T_info, dF, delta, G):
    """جزء من مسافة SL الفيزيائية (10%)."""
    # sl_dist ≈ 3 × σ × price (من إعدادات البوت الحالية)
    sl_dist = 3.0 * sigma * price
    return sl_dist * 0.10


def f_free_e(sigma, price, P_act, friction, T_info, dF, delta, G):
    """مبني على نسبة |dF| إلى حرارة الاهتزاز."""
    num = abs(dF)
    den = abs(dF) + T_info * friction + 1e-9
    return sigma * price * (num / den)


def f_composite(sigma, price, P_act, friction, T_info, dF, delta, G):
    """تركيب (1-P_act) مع تلاشي أسّي في الاحتكاك."""
    return sigma * price * (1.0 - P_act) * np.exp(-friction / 0.5)


def f_delta(sigma, price, P_act, friction, T_info, dF, delta, G):
    """مبني على فجوة التوازن."""
    return sigma * price * delta * P_act


FORMULAS = [
    ("F_current",   f_current),
    ("F_lin_Pact",  f_p_act_linear),
    ("F_quad_Pact", f_p_act_quad),
    ("F_neg_log",   f_neg_log),
    ("F_sl_frac",   f_sl_frac),
    ("F_free_e",    f_free_e),
    ("F_composite", f_composite),
    ("F_delta",     f_delta),
]


# ═════════════════════════════════════════════════════════════════════
# محاكاة صفقة واحدة
# ═════════════════════════════════════════════════════════════════════

def simulate_trade(ad, sig_bar, entry_px, W_enter, W_hold,
                    tp_mult=5.0, sl_sigma_floor=3.0):
    """
    يُحاكي:
      1. هل وصل السعر إلى entry_px خلال W_enter شمعة؟
      2. إن وصل: هل ضرب SL أم TP أولاً خلال W_hold شمعة؟
    """
    n = len(ad.closes)
    # مرحلة 1: البحث عن اللمس
    touch_bar = -1
    for bar in range(sig_bar + 1, min(sig_bar + 1 + W_enter, n)):
        if ad.lows[bar] <= entry_px:
            touch_bar = bar
            break
    if touch_bar < 0:
        return {'touched': False, 'result': 'NO_TOUCH',
                'bars_to_touch': W_enter, 'bars_held': 0}

    # مرحلة 2: SL/TP من نفس الشمعة
    fi_t = touch_bar - ad.feat_start
    if fi_t < 0 or fi_t >= len(ad.E_therm):
        return {'touched': True, 'result': 'BAD_IDX',
                'bars_to_touch': touch_bar - sig_bar, 'bars_held': 0}
    sigma_t = float(ad.E_therm[fi_t])
    if not np.isfinite(sigma_t) or sigma_t <= 1e-6:
        return {'touched': True, 'result': 'BAD_SIGMA',
                'bars_to_touch': touch_bar - sig_bar, 'bars_held': 0}
    sl_dist = sl_sigma_floor * sigma_t * entry_px
    sl_px = entry_px - sl_dist
    tp_px = entry_px + sl_dist * tp_mult

    for j in range(touch_bar + 1, min(touch_bar + 1 + W_hold, n)):
        if ad.lows[j] <= sl_px:
            return {'touched': True, 'result': 'SL',
                    'bars_to_touch': touch_bar - sig_bar,
                    'bars_held': j - touch_bar}
        if ad.highs[j] >= tp_px:
            return {'touched': True, 'result': 'TP',
                    'bars_to_touch': touch_bar - sig_bar,
                    'bars_held': j - touch_bar}
    return {'touched': True, 'result': 'TIMEOUT',
            'bars_to_touch': touch_bar - sig_bar, 'bars_held': W_hold}


# ═════════════════════════════════════════════════════════════════════
# التشغيل الرئيسي
# ═════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--bars", type=int, default=300)
    p.add_argument("--capital", type=float, default=1000.0)
    args = p.parse_args()

    ex = ccxt.binance({'options': {'defaultType': 'future'}})
    bot.CFG.timeframe = args.timeframe
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)
    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))
    bot.CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))

    # نوافذ المحاكاة بالوحدات الفعلية
    W_enter = max(2, int(round(8.0 * bot.CFG.TF_SCALE)))   # ~8 ساعات
    W_hold = max(10, int(round(50.0 * bot.CFG.TF_SCALE)))  # ~50 ساعة

    print(f"Symbol: {args.symbol}  TF: {args.timeframe}")
    print(f"N={bot.CFG.N} W={bot.CFG.W} L={bot.CFG.L} "
          f"ADV_BARS={bot.CFG.ADV_BARS}")
    print(f"W_enter={W_enter} bars  W_hold={W_hold} bars")
    print()

    ohlcv = ex.fetch_ohlcv(args.symbol, args.timeframe, limit=1000)
    if not ohlcv:
        print("No data"); return 1
    df = pd.DataFrame(ohlcv, columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()

    ad = bot.process_asset(args.symbol, df, current_capital=args.capital)
    if ad is None:
        print("process_asset returned None"); return 1

    print(f"Bars processed: {len(ad.closes)}")
    print(f"Last close: {ad.closes[-1]:.6f}")
    print()

    n = len(ad.closes)
    start = max(ad.train_end + 1, n - args.bars)
    stop = n - W_hold - W_enter - 2

    # جمع الإشارات
    signals = []
    for i in range(start, stop):
        fi = i - ad.feat_start
        if fi < 0 or fi >= len(ad.score):
            continue
        p_now = float(ad.closes[i])
        sigma = float(ad.E_therm[fi])
        if not np.isfinite(sigma) or sigma <= 1e-6:
            continue
        friction = float(ad.friction[fi])
        T_info = float(ad.T_info[fi])
        geo = float(ad.geodesic_accel[fi])
        P_act = float(np.exp(-friction / ((abs(geo) + 1e-9) * T_info)))
        if P_act < 0.35:
            continue
        dF = float(ad.dF[fi])
        delta = float(ad.delta_gap[fi])
        G = float(ad.gauge_force[fi])

        # شرط التوجيه (BUY) — مطابق للبوت
        win = ad.closes[max(0, i - bot.CFG.N): i]
        if len(win) < 2:
            continue
        sd = float(np.std(win))
        if sd <= 1e-12:
            continue
        z = (p_now - float(np.mean(win))) / sd
        if z >= -1.5:
            continue
        if ad.score[fi] < bot.CFG.MIN_SCORE:
            continue

        signals.append({
            'bar': i, 'fi': fi, 'price': p_now,
            'sigma': sigma, 'P_act': P_act,
            'friction': friction, 'T_info': T_info,
            'dF': dF, 'delta': delta, 'G': G,
        })

    print(f"BUY signals found: {len(signals)}\n")
    if len(signals) == 0:
        print("No signals — cannot compare formulas"); return 0

    # تشغيل كل صيغة على كل إشارة
    print("=" * 110)
    print(f"{'Formula':<14} {'mean_eps':>9} {'std_eps':>9} {'min_eps':>9} "
          f"{'max_eps':>9} {'touch%':>7} {'SL%':>6} {'TP%':>6} "
          f"{'TO%':>6} {'win_rate':>9}")
    print("=" * 110)

    results = []
    for fname, fn in FORMULAS:
        eps_list = []
        touch_count = 0
        sl_count = 0
        tp_count = 0
        to_count = 0
        bar_to_touch = []

        for sig in signals:
            i = sig['bar']
            price = sig['price']
            eps = fn(sig['sigma'], price, sig['P_act'],
                     sig['friction'], sig['T_info'],
                     sig['dF'], sig['delta'], sig['G'])
            if not np.isfinite(eps) or eps <= 0:
                continue

            entry = price - eps  # BUY
            r = simulate_trade(ad, i, entry, W_enter, W_hold)

            eps_list.append(eps / price * 1e4)
            if r['touched']:
                touch_count += 1
                bar_to_touch.append(r['bars_to_touch'])
                if r['result'] == 'SL':
                    sl_count += 1
                elif r['result'] == 'TP':
                    tp_count += 1
                elif r['result'] == 'TIMEOUT':
                    to_count += 1

        n_sig = len(eps_list)
        if n_sig == 0:
            continue
        touch_pct = 100.0 * touch_count / n_sig
        sl_pct = 100.0 * sl_count / max(touch_count, 1)
        tp_pct = 100.0 * tp_count / max(touch_count, 1)
        to_pct = 100.0 * to_count / max(touch_count, 1)
        win_rate = 100.0 * tp_count / max(touch_count, 1)

        results.append({
            'name': fname, 'mean_eps': np.mean(eps_list),
            'touch_pct': touch_pct, 'sl_pct': sl_pct,
            'tp_pct': tp_pct, 'win_rate': win_rate,
            'touch_count': touch_count, 'n_sig': n_sig,
        })

        print(f"{fname:<14} {np.mean(eps_list):>8.2f}b "
              f"{np.std(eps_list):>8.2f}b {np.min(eps_list):>8.2f}b "
              f"{np.max(eps_list):>8.2f}b {touch_pct:>6.1f}% "
              f"{sl_pct:>5.1f}% {tp_pct:>5.1f}% "
              f"{to_pct:>5.1f}% {win_rate:>8.1f}%")

    print("=" * 110)
    print()
    print("الترتيب حسب win_rate (TP% من الصفقات الملموسة):")
    for r in sorted(results, key=lambda x: -x['win_rate']):
        print(f"  {r['name']:<14} win={r['win_rate']:>5.1f}%  "
              f"touch={r['touch_pct']:>5.1f}%  "
              f"eps={r['mean_eps']:>5.2f}b  "
              f"(n={r['touch_count']}/{r['n_sig']})")

    print()
    print("الترتيب حسب touch_pct (نسبة اللمس):")
    for r in sorted(results, key=lambda x: -x['touch_pct']):
        print(f"  {r['name']:<14} touch={r['touch_pct']:>5.1f}%  "
              f"win={r['win_rate']:>5.1f}%  "
              f"eps={r['mean_eps']:>5.2f}b")

    return 0


if __name__ == "__main__":
    sys.exit(main())
