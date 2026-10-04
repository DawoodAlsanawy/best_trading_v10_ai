#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_regime.py — يقيس أداء النظام حسب "regime" السوقي عند الدخول.

المؤشر: |ema[ci] - ema[ci-50]| / atr
  - قيم صغيرة (~0.3-0.8) = سوق ranging
  - قيم كبيرة (~2+)     = سوق trending

الهدف: هل النظام رابح في كل الـ regimes أم فقط في بعضها؟
"""

import json
import sys
import numpy as np
from pathlib import Path


def load_trades(path):
    trades = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get('_meta'):
                    continue
                trades.append(r)
    except FileNotFoundError:
        return []
    return trades


def extract_data(trades):
    """يعيد list of (slope_norm, pnl, action, exit_reason)"""
    out = []
    missing_slope = 0
    missing_atr = 0
    for t in trades:
        slope = t.get('ema_slope')
        atr = t.get('atr')
        pnl = t.get('net_pnl', 0.0)
        action = t.get('action', '?')
        reason = t.get('exit_reason', '?')

        if slope is None:
            missing_slope += 1
            continue
        if atr is None or atr <= 0:
            missing_atr += 1
            continue

        # slope_norm = |slope * 50| / atr = |ΔEMA over 50 bars| / ATR
        slope_norm = abs(float(slope) * 50.0) / float(atr)
        if not np.isfinite(slope_norm):
            continue

        out.append((slope_norm, float(pnl), action, reason))

    return out, missing_slope, missing_atr


def stats(pnls):
    if len(pnls) == 0:
        return {'n': 0, 'mean': 0, 'wr': 0, 'pf': 0, 'sharpe': 0}

    pnls = np.asarray(pnls)
    n = len(pnls)
    mean = float(pnls.mean())
    std = float(pnls.std())
    sharpe = mean / std * np.sqrt(252) if std > 1e-12 else 0.0
    wr = float((pnls > 0).mean() * 100)
    wins = float(pnls[pnls > 0].sum())
    losses = float(abs(pnls[pnls <= 0].sum()))
    pf = wins / losses if losses > 1e-12 else float('inf')
    return {
        'n': n, 'mean': mean, 'wr': wr, 'pf': pf, 'sharpe': sharpe,
    }


def analyze_window(year, trades):
    print(f"\n{'═' * 72}")
    print(f"  نافذة {year}  —  {len(trades)} صفقة")
    print(f"{'═' * 72}")

    data, miss_slope, miss_atr = extract_data(trades)
    print(f"  صالحة للتحليل: {len(data)}  (ناقص ema_slope: {miss_slope}, "
          f"ناقص atr: {miss_atr})")

    if len(data) < 50:
        print(f"  ⚠️  عدد الصفقات قليل جداً — تخطّي")
        return None

    slopes = np.array([d[0] for d in data])
    pnls = np.array([d[1] for d in data])

    # إحصاءات عامة
    print(f"\n  slope/atr distribution:")
    print(f"    min={slopes.min():.3f}  "
          f"q10={np.percentile(slopes, 10):.3f}  "
          f"q25={np.percentile(slopes, 25):.3f}  "
          f"median={np.median(slopes):.3f}  "
          f"q75={np.percentile(slopes, 75):.3f}  "
          f"q90={np.percentile(slopes, 90):.3f}  "
          f"max={slopes.max():.3f}")

    # 4 quantile buckets
    print(f"\n  {'Bucket':<28} {'Range':<20} {'N':>5} "
          f"{'MeanPnL':>11} {'WR%':>7} {'PF':>7} {'Sharpe':>8}")
    print(f"  {'─' * 28} {'─' * 20} {'─' * 5} "
          f"{'─' * 11} {'─' * 7} {'─' * 7} {'─' * 8}")

    qs = [0, 25, 50, 75, 100]
    bounds = np.percentile(slopes, qs)
    bounds = list(bounds) + [np.inf]

    for i in range(4):
        lo, hi = bounds[i], bounds[i + 1]
        mask = (slopes >= lo) & (slopes < hi)
        if mask.sum() < 10:
            continue
        b_pnls = pnls[mask]
        s = stats(b_pnls)
        range_str = f"{lo:.2f}–{hi:.2f}" if hi != np.inf else f"{lo:.2f}+"
        label = f"q{qs[i]}-q{qs[i + 1]}"

        print(f"  {label:<28} {range_str:<20} {s['n']:>5} "
              f"{s['mean']:>11.4f} {s['wr']:>7.1f} {s['pf']:>7.2f} "
              f"{s['sharpe']:>8.3f}")

    # فحص عتبات محددة
    print(f"\n  أثر عتبة REGIME_SLOPE_ATR_MAX على الأداء:")
    print(f"  {'Threshold':<12} {'N kept':<10} {'% kept':<10} "
          f"{'MeanPnL':>11} {'Sharpe':>8}")
    print(f"  {'─' * 12} {'─' * 10} {'─' * 10} {'─' * 11} {'─' * 8}")

    full_stats = stats(pnls)
    for threshold in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
        mask = slopes <= threshold
        if mask.sum() < 20:
            continue
        kept = pnls[mask]
        s = stats(kept)
        pct_kept = 100.0 * mask.sum() / len(slopes)
        print(f"  {threshold:<12.1f} {s['n']:<10} "
              f"{pct_kept:<10.1f} {s['mean']:>11.4f} {s['sharpe']:>8.3f}")

    print(f"\n  خط الأساس (بدون فلتر):")
    print(f"    n={full_stats['n']}  mean={full_stats['mean']:.4f}  "
          f"Sharpe={full_stats['sharpe']:.3f}")

    return {
        'year': year,
        'full': full_stats,
        'slopes': slopes,
        'pnls': pnls,
    }


def main():
    base = Path('results')
    results = {}

    print(f"\n{'═' * 72}")
    print(f"  تحليل Regime — مقارنة عبر 3 نوافذ مستقلة")
    print(f"{'═' * 72}")

    for year in ['2024', '2025', '2026']:
        p = base / f'trades_{year}.jsonl'
        trades = load_trades(p)
        if not trades:
            print(f"\n⚠️  {p} — لا يوجد أو فارغ")
            continue
        r = analyze_window(year, trades)
        if r:
            results[year] = r

    # الخلاصة النهائية
    print(f"\n\n{'═' * 72}")
    print(f"  الخلاصة — مقارنة العتبات عبر النوافذ الثلاث")
    print(f"{'═' * 72}")
    print(f"\n  {'Threshold':<12} "
          f"{'2024 Sharpe':>13} {'2025 Sharpe':>13} {'2026 Sharpe':>13} "
          f"{'Min Sharpe':>11}")
    print(f"  {'─' * 12} "
          f"{'─' * 13} {'─' * 13} {'─' * 13} {'─' * 11}")

    for threshold in [0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]:
        sharpes = []
        for year in ['2024', '2025', '2026']:
            if year not in results:
                sharpes.append(np.nan)
                continue
            slopes = results[year]['slopes']
            pnls = results[year]['pnls']
            mask = slopes <= threshold
            if mask.sum() < 20:
                sharpes.append(np.nan)
                continue
            s = stats(pnls[mask])
            sharpes.append(s['sharpe'])

        valid = [s for s in sharpes if not np.isnan(s)]
        min_s = min(valid) if valid else np.nan

        print(f"  {threshold:<12.1f} "
              f"{sharpes[0]:>13.3f} {sharpes[1]:>13.3f} {sharpes[2]:>13.3f} "
              f"{min_s:>11.3f}")

    # السطر المرجعي: بدون فلتر
    print(f"\n  {'no filter':<12} ", end="")
    for year in ['2024', '2025', '2026']:
        if year in results:
            print(f"{results[year]['full']['sharpe']:>13.3f} ", end="")
        else:
            print(f"{'—':>13} ", end="")
    print()


if __name__ == '__main__':
    main()
