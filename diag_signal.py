#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تشخيص MFE/MAE — هل الإشارة تتنبأ بانعكاس حقيقي؟
=========================================================
يقيس لكل إشارة BUY:
  MFE = Maximum Favorable Excursion (كم صعد السعر بعدها، بوحدات σ)
  MAE = Maximum Adverse Excursion  (كم نزل السعر بعدها، بوحدات σ)
  زمن أول لمس لمستويات ±0.5σ, ±1σ, ±1.5σ, ±2σ, ±3σ, ±5σ

لا يحاكي دخول ولا SL ولا TP. فقط يقيس قوة الإشارة الفيزيائية.
"""

import argparse
import sys
import numpy as np
import pandas as pd
import ccxt

import trading_2_live2_1 as bot


LEVELS = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]


def first_touch(ad, sig_bar, p0, sigma0, levels, H, direction):
    """
    Returns:
      ft   : dict {f'+Lσ': bar_or_None, f'-Lσ': bar_or_None}
      mfe  : max favorable excursion (in σ units, log-based)
      mae  : max adverse excursion (in σ units, log-based)
      t_mfe, t_mae : bar when each max occurred
    """
    n = len(ad.closes)
    ft = {f'+{L}σ': None for L in levels}
    ft.update({f'-{L}σ': None for L in levels})
    mfe = 0.0; mae = 0.0
    t_mfe = 0; t_mae = 0

    for k in range(1, H + 1):
        j = sig_bar + k
        if j >= n: break
        hi = float(ad.highs[j])
        lo = float(ad.lows[j])

        up_s = np.log(hi / p0) / sigma0 if hi > p0 else 0.0
        dn_s = -np.log(lo / p0) / sigma0 if lo < p0 else 0.0

        if direction == 'BUY':
            mfe_cand, mae_cand = up_s, dn_s
        else:  # SELL
            mfe_cand, mae_cand = dn_s, up_s

        if mfe_cand > mfe:
            mfe = mfe_cand; t_mfe = k
        if mae_cand > mae:
            mae = mae_cand; t_mae = k

        for L in levels:
            up_lvl = p0 * np.exp(+L * sigma0)
            dn_lvl = p0 * np.exp(-L * sigma0)
            kp = f'+{L}σ'
            km = f'-{L}σ'
            if ft[kp] is None and hi >= up_lvl:
                ft[kp] = k
            if ft[km] is None and lo <= dn_lvl:
                ft[km] = k

    return ft, mfe, mae, t_mfe, t_mae


def r_ladder(first_touches, directions, pairs):
    """
    For each (SL, TP) pair:
      - consider only signals where BOTH levels got touched
      - count how often TP touched BEFORE SL
      - compare against random-walk baseline SL/(SL+TP)
    """
    out = []
    for sl, tp in pairs:
        both = 0; tp_first = 0
        for ft, d in zip(first_touches, directions):
            if d == 'BUY':
                kt = ft.get(f'+{tp}σ')
                ks = ft.get(f'-{sl}σ')
            else:
                kt = ft.get(f'-{tp}σ')
                ks = ft.get(f'+{sl}σ')
            if kt is None or ks is None:
                continue
            both += 1
            if kt < ks:
                tp_first += 1
        if both == 0:
            continue
        p_tp = tp_first / both
        e_r = p_tp * tp - (1 - p_tp) * sl
        rw = sl / (sl + tp)
        out.append({
            'sl': sl, 'tp': tp, 'n_both': both,
            'p_tp_first': p_tp, 'e_R': e_r, 'rw': rw,
            'edge': p_tp - rw,
        })
    return out


def collect_signals(ad, bars, min_score, action='buy'):
    n = len(ad.closes)
    start = max(ad.train_end + 1, n - bars)
    sigs = []
    for i in range(start, n):
        fi = i - ad.feat_start
        if fi < 0 or fi >= len(ad.score):
            continue
        p = float(ad.closes[i])
        if p <= 0:
            continue
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
        z = (p - float(np.mean(win))) / sd
        if abs(z) < 1.5:
            continue
        sig_action = 'BUY' if z < 0 else 'SELL'
        if action == 'buy' and sig_action != 'BUY':
            continue
        if action == 'sell' and sig_action != 'SELL':
            continue
        if float(ad.score[fi]) < min_score:
            continue

        sigs.append({
            'bar': i, 'fi': fi, 'price': p,
            'sigma': sigma, 'P_act': P_act,
            'score': float(ad.score[fi]),
            'z': z, 'action': sig_action,
        })
    return sigs


def analyze(ad, sigs, H):
    mfe_list = []; mae_list = []
    t_mfe_list = []; t_mae_list = []
    first_touches = []
    directions = []

    for s in sigs:
        ft, mfe, mae, t_mfe, t_mae = first_touch(
            ad, s['bar'], s['price'], s['sigma'],
            LEVELS, H, s['action']
        )
        mfe_list.append(mfe); mae_list.append(mae)
        t_mfe_list.append(t_mfe); t_mae_list.append(t_mae)
        first_touches.append(ft)
        directions.append(s['action'])

    return (mfe_list, mae_list, t_mfe_list, t_mae_list,
            first_touches, directions)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol', default='BTC/USDT')
    ap.add_argument('--timeframe', default='1h')
    ap.add_argument('--bars', type=int, default=800)
    ap.add_argument('--capital', type=float, default=1000.0)
    ap.add_argument('--action', choices=['buy', 'sell', 'both'], default='buy')
    ap.add_argument('--H', type=int, default=168,
                    help='horizon in bars (default: 168 = 7d on 1h)')
    ap.add_argument('--random-baseline', action='store_true')
    args = ap.parse_args()

    ex = ccxt.binance({'options': {'defaultType': 'future'}})
    bot.CFG.timeframe = args.timeframe
    bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
        bot.compute_tf_scale(ex, args.timeframe)
    _tf_h = max(bot.CFG.TF_HOURS, 1e-6)
    bot.CFG.N = max(bot.CFG.N, int(np.ceil(24.0 / _tf_h)))
    bot.CFG.W = max(bot.CFG.W, int(np.ceil(20.0 / _tf_h)))
    bot.CFG.L = max(bot.CFG.L, int(np.ceil(10.0 / _tf_h)))
    bot.CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))

    print(f"Symbol: {args.symbol}  TF: {args.timeframe}  H={args.H} bars")
    print(f"Action filter: {args.action}  capital=${args.capital:.0f}")

    ohlcv = ex.fetch_ohlcv(args.symbol, args.timeframe, limit=5000)
    if not ohlcv:
        print("no data"); return 1
    df = pd.DataFrame(ohlcv,
                      columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()

    ad = bot.process_asset(args.symbol, df, current_capital=args.capital)
    if ad is None:
        print("process_asset returned None"); return 1

    print(f"Bars processed: {len(ad.closes)}")
    print(f"Last close: {ad.closes[-1]:.6f}\n")

    sigs = collect_signals(ad, args.bars, bot.CFG.MIN_SCORE, args.action)
    print(f"Signals ({args.action}): {len(sigs)}\n")
    if not sigs:
        return 0

    (mfe_list, mae_list, t_mfe_list, t_mae_list,
     first_touches, directions) = analyze(ad, sigs, args.H)

    n = len(sigs)

    print(f"{'#':>3} {'bar':>6} {'p0':>12} {'σ%':>7} {'P_act':>7} "
          f"{'score':>6} {'z':>7} {'MFEσ':>7} {'MAEσ':>7} "
          f"{'T_MFE':>6} {'T_MAE':>6} {'MFE>MAE':>8}")
    print("-" * 108)
    for i, s in enumerate(sigs):
        flag = '✓' if mfe_list[i] > mae_list[i] else '✗'
        print(f"{i+1:>3} {s['bar']:>6} {s['price']:>12.6f} "
              f"{s['sigma']*100:>6.3f}% {s['P_act']:>7.3f} "
              f"{s['score']:>6.2f} {s['z']:>+7.2f} "
              f"{mfe_list[i]:>7.2f} {mae_list[i]:>7.2f} "
              f"{t_mfe_list[i]:>6} {t_mae_list[i]:>6} {flag:>8}")
    print("-" * 108)

    E_mfe = float(np.mean(mfe_list))
    E_mae = float(np.mean(mae_list))
    p_dir = sum(1 for m, a in zip(mfe_list, mae_list) if m > a) / n
    ratio = E_mfe / max(E_mae, 1e-9)

    print(f"\n═══ AGGREGATE ═══")
    print(f"  N signals          : {n}")
    print(f"  E[MFE]             : {E_mfe:>7.3f} σ")
    print(f"  E[MAE]             : {E_mae:>7.3f} σ")
    print(f"  E[MFE]/E[MAE]      : {ratio:>7.3f}")
    print(f"  P(MFE > MAE)       : {p_dir*100:>6.1f}%  "
          f"(random = 50%)")
    print(f"  E[T_MFE]           : {np.mean(t_mfe_list):>7.1f} bars")
    print(f"  E[T_MAE]           : {np.mean(t_mae_list):>7.1f} bars")

    print(f"\n  Probability of reaching each level:")
    print(f"  {'level':>6} {'P(MFE>L)':>10} {'P(MAE>L)':>10}")
    for L in LEVELS:
        p_mfe = sum(1 for m in mfe_list if m > L) / n
        p_mae = sum(1 for m in mae_list if m > L) / n
        print(f"  {L:>5.1f}σ {p_mfe*100:>9.1f}% {p_mae*100:>9.1f}%")

    print(f"\n═══ R:R LADDER (based on which level is touched first) ═══")
    print(f"  {'SLσ':>5} {'TPσ':>5} {'N_both':>7} "
          f"{'P(TP first)':>12} {'E[R]':>8} "
          f"{'RW_base':>9} {'edge':>9}")
    pairs = [(1,1),(1,1.5),(1,2),(1,3),(1,5),
             (1.5,1.5),(1.5,2),(1.5,3),
             (2,2),(2,3),(2,4),(3,5)]
    rows = r_ladder(first_touches, directions, pairs)
    for r in rows:
        edge = r['p_tp_first'] - r['rw']
        edge_s = f"+{edge*100:>5.1f}%" if edge >= 0 else f"{edge*100:>6.1f}%"
        print(f"  {r['sl']:>5.1f} {r['tp']:>5.1f} {r['n_both']:>7} "
              f"{r['p_tp_first']*100:>11.1f}% "
              f"{r['e_R']:>+7.3f} "
              f"{r['rw']*100:>8.1f}% {edge_s:>9}")

    print(f"\n═══ VERDICT ═══")
    if n < 30:
        print(f"  ⚠ SAMPLE TOO SMALL (n={n} < 30). Statistical noise dominates.")
    if ratio > 1.15:
        v = f"FAVORABLE (MFE/MAE={ratio:.2f} > 1.15)"
    elif ratio < 0.85:
        v = f"ADVERSE (MFE/MAE={ratio:.2f} < 0.85)"
    else:
        v = f"NEUTRAL (MFE/MAE={ratio:.2f} ≈ 1.0)"
    print(f"  Directional bias : {v}")
    print(f"  P(MFE > MAE)     : {p_dir*100:.1f}%  "
          f"(edge over random: {(p_dir-0.5)*100:+.1f}%)")

    if rows:
        best = max(rows, key=lambda r: r['edge'])
        if best['edge'] > 0.05:
            print(f"  Best (SL,TP) edge: SL={best['sl']}σ TP={best['tp']}σ "
                  f"→ P(TP first)={best['p_tp_first']*100:.1f}% "
                  f"vs RW {best['rw']*100:.1f}% "
                  f"(+{best['edge']*100:.1f}% edge, E[R]={best['e_R']:+.2f})")
        else:
            print(f"  Best edge found  : {best['edge']*100:+.1f}% "
                  f"(weak — no exploitable edge)")

    if args.random_baseline:
        print(f"\n═══ RANDOM BASELINE ═══")
        rng = np.random.default_rng(42)
        start = max(ad.train_end + 1, len(ad.closes) - args.bars)
        stop = len(ad.closes) - args.H - 1
        if stop > start:
            random_bars = rng.integers(start, stop, size=max(n, 100))
            r_mfe, r_mae = [], []
            for bi in random_bars:
                fi = int(bi) - ad.feat_start
                if fi < 0 or fi >= len(ad.E_therm):
                    continue
                sig0 = float(ad.E_therm[fi])
                if not np.isfinite(sig0) or sig0 <= 1e-6:
                    continue
                _, mfe, mae, _, _ = first_touch(
                    ad, int(bi), float(ad.closes[bi]), sig0,
                    LEVELS, args.H, 'BUY'
                )
                r_mfe.append(mfe); r_mae.append(mae)
            if r_mfe:
                rn = len(r_mfe)
                r_E_mfe = float(np.mean(r_mfe))
                r_E_mae = float(np.mean(r_mae))
                r_p_dir = sum(1 for m, a in zip(r_mfe, r_mae) if m > a) / rn
                print(f"  Random N        : {rn}")
                print(f"  Random E[MFE]   : {r_E_mfe:.3f} σ")
                print(f"  Random E[MAE]   : {r_E_mae:.3f} σ")
                print(f"  Random P(MFE>MAE): {r_p_dir*100:.1f}%")
                print(f"  ─ Delta vs signal ─")
                print(f"  ΔE[MFE]         : {E_mfe - r_E_mfe:+.3f} σ")
                print(f"  ΔE[MAE]         : {E_mae - r_E_mae:+.3f} σ")
                print(f"  ΔP(MFE>MAE)     : {(p_dir - r_p_dir)*100:+.1f}%")

    return 0


if __name__ == '__main__':
    sys.exit(main())
