#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اختبار معادلة الإزاحة القريبة.
يفحص: هل الإزاحة الناتجة قريبة من السعر؟ هل P_touch معقولة؟
لا يعمل أي تعديل على البوت، فقط قراءة.
"""
import argparse
import sys
import numpy as np
import pandas as pd
from scipy.stats import norm

import trading_2_live2_1 as bot


def compute_near_entry(p_now, sigma_bar, P_act, tick, spread,
                        K_MIN=0.02, K_MAX=0.15):
    """المعادلة المقترحة."""
    k_signal = K_MIN + (K_MAX - K_MIN) * (1.0 - P_act)
    eps_signal = k_signal * sigma_bar * p_now
    eps_tick = 2.0 * tick
    eps_spread = 0.5 * spread
    epsilon = max(eps_signal, eps_tick, eps_spread)
    return {
        'entry_buy':  p_now - epsilon,
        'entry_sell': p_now + epsilon,
        'epsilon': epsilon,
        'eps_bps': epsilon / p_now * 1e4,
        'eps_ticks': epsilon / tick if tick > 0 else 0.0,
        'eps_signal_bps': eps_signal / p_now * 1e4,
        'eps_tick_bps':   eps_tick   / p_now * 1e4,
        'eps_spread_bps': eps_spread / p_now * 1e4,
        'k_signal': k_signal,
    }


def touch_prob(epsilon, sigma_bar, T_obs, T_bar):
    """P(price touches level ε within T_obs) — one-sided, reflection principle."""
    if sigma_bar <= 0 or epsilon <= 0:
        return 0.0
    sigma_obs = sigma_bar * np.sqrt(T_obs / T_bar)
    z = epsilon / sigma_obs
    return float(2.0 * norm.cdf(-z))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="TON/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--bars", type=int, default=200, help="last N bars")
    p.add_argument("--K_MIN", type=float, default=0.02)
    p.add_argument("--K_MAX", type=float, default=0.15)
    p.add_argument("--T_obs", type=int, default=60, help="observation window (s)")
    p.add_argument("--capital", type=float, default=1000.0)
    args = p.parse_args()

    import ccxt
    ex = ccxt.binance({'options': {'defaultType': 'future'}})

    # ضبط الإطار الزمني
    bot.CFG.timeframe = args.timeframe
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)
    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))

    print(f"Symbol: {args.symbol}  TF: {args.timeframe}  "
          f"N={bot.CFG.N} W={bot.CFG.W} L={bot.CFG.L}\n")

    ohlcv = ex.fetch_ohlcv(args.symbol, args.timeframe, limit=1000)
    if not ohlcv:
        print("No data"); return 1
    df = pd.DataFrame(ohlcv, columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()

    print(f"Fetched {len(df)} bars")
    print("Computing physics...")
    ad = bot.process_asset(args.symbol, df, current_capital=args.capital)
    if ad is None:
        print("process_asset returned None"); return 1

    tick = bot._get_tick_size(ex, args.symbol)
    if tick is None:
        tick = ad.closes[-1] * 1e-6
    try:
        ob = ex.fetch_order_book(args.symbol, limit=5)
        spread = float(ob['asks'][0][0]) - float(ob['bids'][0][0])
    except Exception:
        spread = tick * 5

    print(f"Tick={tick}  Spread={spread} ({spread/ad.closes[-1]*1e4:.2f} bps)")
    print(f"Last close: {ad.closes[-1]:.6f}\n")

    n = len(ad.closes)
    start = max(ad.train_end + 1, n - args.bars)

    # جدول النتائج
    print("=" * 100)
    header = (f"{'bar':>6} {'p_now':>12} {'sigma_b%':>9} {'P_act':>7} "
              f"{'k_sig':>7} {'eps_bps':>8} {'eps_tk':>7} "
              f"{'P_touch':>8} {'entry_buy':>12} {'src':>6}")
    print(header)
    print("-" * len(header))

    signals = 0
    for i in range(start, n - 1):
        fi = i - ad.feat_start
        if fi < 0 or fi >= len(ad.score):
            continue

        p_now = float(ad.closes[i])
        sigma_bar = float(ad.E_therm[fi])
        friction = float(ad.friction[fi])
        T_info = float(ad.T_info[fi])
        geo = float(ad.geodesic_accel[fi])

        if sigma_bar <= 1e-6 or not np.isfinite(sigma_bar):
            continue

        P_act = float(np.exp(-friction / ((abs(geo) + 1e-9) * T_info)))
        if P_act < 0.35:
            continue

        # اختيار الاتجاه كالبوت: z_dev
        win = ad.closes[max(0, i - bot.CFG.N): i]
        if len(win) < 2:
            continue
        mu = float(np.mean(win)); sd = float(np.std(win))
        if sd <= 1e-12:
            continue
        z = (p_now - mu) / sd
        if z >= -1.5:
            continue  # BUY فقط في هذا الاختبار

        signals += 1
        r = compute_near_entry(p_now, sigma_bar, P_act, tick, spread,
                                args.K_MIN, args.K_MAX)
        P_t = touch_prob(r['epsilon'], sigma_bar, args.T_obs, bot.CFG.TF_SECONDS)

        # مصدر الإزاحة الفعلي
        if abs(r['epsilon'] - 2 * tick) < 1e-12:
            src = "tick"
        elif abs(r['epsilon'] - 0.5 * spread) < 1e-12:
            src = "spread"
        else:
            src = "signal"

        print(f"{i:>6} {p_now:>12.6f} {sigma_bar*100:>8.3f}% {P_act:>7.3f} "
              f"{r['k_signal']:>7.4f} {r['eps_bps']:>7.2f} "
              f"{r['eps_ticks']:>7.1f} {P_t:>7.3f} "
              f"{r['entry_buy']:>12.6f} {src:>6}")

    print("=" * 100)
    print(f"\nBUY signals found: {signals}")
    print(f"T_obs = {args.T_obs}s, TF = {bot.CFG.TF_SECONDS}s")

    # مقارنة مع الصيغة القديمة
    print("\n" + "=" * 60)
    print("مقارنة: الصيغة القديمة (--no-fixed-price) مقابل المقترحة")
    print("=" * 60)
    for i in range(n - 2, start - 1, -1):
        fi = i - ad.feat_start
        if fi < 0 or fi >= len(ad.score):
            continue
        p_now = float(ad.closes[i])
        sigma_bar = float(ad.E_therm[fi])
        friction = float(ad.friction[fi])
        T_info = float(ad.T_info[fi])
        geo = float(ad.geodesic_accel[fi])
        if sigma_bar <= 1e-6:
            continue
        P_act = float(np.exp(-friction / ((abs(geo) + 1e-9) * T_info)))
        if P_act < 0.35:
            continue
        win = ad.closes[max(0, i - bot.CFG.N): i]
        if len(win) < 2: continue
        sd = float(np.std(win))
        if sd <= 1e-12: continue
        z = (p_now - float(np.mean(win))) / sd
        if z >= -1.5: continue

        eps_old = 0.02 * sigma_bar * p_now * 3.0   # adv_mult=3
        r = compute_near_entry(p_now, sigma_bar, P_act, tick, spread,
                                args.K_MIN, args.K_MAX)
        print(f"\nBar {i}: p_now={p_now:.6f} σ={sigma_bar*100:.3f}% P_act={P_act:.3f}")
        print(f"  Old:  ε = {eps_old:.6f} ({eps_old/p_now*1e4:.2f} bps)")
        print(f"  New:  ε = {r['epsilon']:.6f} ({r['eps_bps']:.2f} bps)  "
              f"[signal={r['eps_signal_bps']:.2f}  tick={r['eps_tick_bps']:.2f}  "
              f"spread={r['eps_spread_bps']:.2f}]")
        break
    return 0


if __name__ == "__main__":
    sys.exit(main())
