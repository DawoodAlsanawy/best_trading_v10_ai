#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
edge_quality_audit.py — فحص جودة الحافة على 3 سنوات.
يجيب على: هل الحافة موزعة أم مركّزة؟ هل الاتجاه ضد الإشارة مؤلم؟
"""

import json
from pathlib import Path
from collections import defaultdict
import numpy as np


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


def stats(pnls):
    pnls = np.asarray(pnls, dtype=np.float64)
    if len(pnls) == 0:
        return {'n': 0, 'mean': 0, 'sharpe': 0, 'wr': 0, 'pf': 0,
                'sum': 0, 'top10pct_contrib': 0}
    n = len(pnls)
    mean = float(pnls.mean())
    std = float(pnls.std())
    sharpe = mean / std * np.sqrt(252) if std > 1e-12 else 0.0
    wr = float((pnls > 0).mean() * 100)
    total = float(pnls.sum())
    # Top 10% contribution
    sorted_p = np.sort(pnls)[::-1]
    top_10pct_n = max(1, int(n * 0.10))
    top_contrib = float(sorted_p[:top_10pct_n].sum())
    top_pct = 100.0 * top_contrib / total if abs(total) > 1e-12 else 0.0
    return {
        'n': n, 'mean': mean, 'sharpe': sharpe,
        'wr': wr, 'sum': total, 'top10pct_contrib': top_pct,
    }


# ═══════════════════════════════════════════════════════════════

def analyze_asset_concentration(trades):
    """هل الربح مركّز في 1-2 أصول؟"""
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t.get('symbol', '?')].append(t.get('net_pnl', 0.0))

    sym_pnl = []
    for sym, pnls in by_sym.items():
        sym_pnl.append((sym, len(pnls), sum(pnls)))

    sym_pnl.sort(key=lambda x: -x[2])
    total = sum(x[2] for x in sym_pnl)
    if abs(total) < 1e-9:
        return sym_pnl, 0.0

    cum = 0.0
    herfindahl = 0.0
    for sym, n, pnl in sym_pnl:
        cum += pnl
        share = max(0, pnl) / max(abs(total), 1e-9)
        herfindahl += share ** 2

    top5 = sum(x[2] for x in sym_pnl[:5])
    top5_pct = 100.0 * top5 / total if abs(total) > 1e-9 else 0.0
    return sym_pnl, top5_pct, herfindahl


def analyze_time_distribution(trades):
    """هل الربح مركّز في فترة قصيرة؟"""
    # Group by month
    by_month = defaultdict(list)
    for t in trades:
        et = str(t.get('entry_time', ''))
        # "2024-03-15 ..." → "2024-03"
        month = et[:7] if len(et) >= 7 else '?'
        by_month[month].append(t.get('net_pnl', 0.0))

    months = sorted(by_month.items())
    if not months:
        return []

    rows = []
    for m, pnls in months:
        s = stats(pnls)
        rows.append({
            'month': m,
            'n': s['n'],
            'sum': s['sum'],
            'sharpe': s['sharpe'],
            'wr': s['wr'],
        })
    return rows


def analyze_slope_against(trades):
    """
    الفحص الأهم: هل الصفقات التي EMA_slope ضد إشارتها أسوأ؟
    """
    aligned = []   # ema_slope_against == 0
    against = []   # ema_slope_against == 1
    unknown = []
    for t in trades:
        pnl = t.get('net_pnl', 0.0)
        flag = t.get('ema_slope_against', None)
        if flag is None:
            unknown.append(pnl)
        elif flag >= 0.5:
            against.append(pnl)
        else:
            aligned.append(pnl)

    return {
        'aligned': stats(aligned),
        'against': stats(against),
        'unknown': stats(unknown),
    }


def analyze_buy_sell(trades):
    buy = [t.get('net_pnl', 0.0) for t in trades if t.get('action') == 'BUY']
    sell = [t.get('net_pnl', 0.0) for t in trades if t.get('action') == 'SELL']
    return {'buy': stats(buy), 'sell': stats(sell)}


# ═══════════════════════════════════════════════════════════════

def main():
    base = Path('results')

    print("═" * 72)
    print("  edge_quality_audit.py — فحص جودة الحافة")
    print("═" * 72)

    all_summaries = {}

    for year in ['2024', '2025', '2026']:
        p = base / f'trades_{year}.jsonl'
        trades = load_trades(p)
        if not trades:
            print(f"\n⚠️  {year}: لا يوجد ملف")
            continue

        print(f"\n{'═' * 72}")
        print(f"  {year}  ({len(trades)} صفقة)")
        print(f"{'═' * 72}")

        # ── 1. التركيز على الأصول ──
        sym_pnl, top5_pct, hhi = analyze_asset_concentration(trades)
        print(f"\n  ▶ تركيز الأصول:")
        print(f"     Top 5 أصول = {top5_pct:.1f}% من الربح")
        print(f"     Herfindahl = {hhi:.4f}  "
              f"(0=موزع، 1=مركّز)")
        print(f"     أعلى 5 أصول:")
        for sym, n, pnl in sym_pnl[:5]:
            pct = 100.0 * pnl / sum(x[2] for x in sym_pnl) \
                  if abs(sum(x[2] for x in sym_pnl)) > 1e-9 else 0
            print(f"       {sym:15s}: n={n:4d}  Σpnl={pnl:>10.2f}  "
                  f"({pct:>5.1f}%)")

        # ── 2. الاتجاه ضد الإشارة ──
        sl = analyze_slope_against(trades)
        print(f"\n  ▶ ema_slope_against (الأهم):")
        print(f"     {'Group':<12} {'N':>5} {'WR%':>7} "
              f"{'Σpnl':>12} {'Sharpe':>8}")
        for name in ['aligned', 'against', 'unknown']:
            s = sl[name]
            if s['n'] == 0:
                continue
            print(f"     {name:<12} {s['n']:>5} {s['wr']:>7.1f} "
                  f"{s['sum']:>12.2f} {s['sharpe']:>8.3f}")

        if sl['aligned']['n'] > 0 and sl['against']['n'] > 0:
            ratio = sl['against']['sharpe'] / max(sl['aligned']['sharpe'], 1e-9)
            print(f"     → نسبة Sharpe (against/aligned) = {ratio:.2f}")
            if ratio < 0.5:
                print(f"     ✅ الفلتر الاتجاهي سيُحسّن")
            elif ratio > 1.2:
                print(f"     ⚠️  المعاكس صحيح — الفلتر سيضُر")
            else:
                print(f"     🟡 لا فرق واضح")

        # ── 3. BUY vs SELL ──
        bs = analyze_buy_sell(trades)
        print(f"\n  ▶ BUY vs SELL:")
        print(f"     {'Action':<8} {'N':>5} {'WR%':>7} "
              f"{'Σpnl':>12} {'Sharpe':>8}")
        for name in ['buy', 'sell']:
            s = bs[name]
            if s['n'] == 0:
                continue
            print(f"     {name.upper():<8} {s['n']:>5} {s['wr']:>7.1f} "
                  f"{s['sum']:>12.2f} {s['sharpe']:>8.3f}")

        # ── 4. التركيز الزمني ──
        months = analyze_time_distribution(trades)
        # أفضل/أسوأ شهر
        if months:
            best = max(months, key=lambda x: x['sum'])
            worst = min(months, key=lambda x: x['sum'])
            total = sum(m['sum'] for m in months)
            best_pct = 100.0 * best['sum'] / total if abs(total) > 1e-9 else 0
            print(f"\n  ▶ التركيز الزمني:")
            print(f"     أفضل شهر: {best['month']}  "
                  f"Σ={best['sum']:.2f}  ({best_pct:.1f}% من الإجمالي)")
            print(f"     أسوأ شهر: {worst['month']}  Σ={worst['sum']:.2f}")

        # ── 5. ملخص ──
        full = stats([t.get('net_pnl', 0.0) for t in trades])
        all_summaries[year] = {
            'full': full,
            'top5_pct': top5_pct,
            'hhi': hhi,
            'slope_ratio': (sl['against']['sharpe'] /
                            max(sl['aligned']['sharpe'], 1e-9)
                            if sl['aligned']['n'] > 0 and sl['against']['n'] > 0
                            else None),
        }

    # ── ملخص عبر السنوات ──
    print(f"\n\n{'═' * 72}")
    print(f"  الخلاصة الشاملة")
    print(f"{'═' * 72}")
    print(f"\n  {'Year':<6} {'Sharpe':>8} {'Σpnl':>12} "
          f"{'Top5%':>8} {'HHI':>8} {'slope_ratio':>12}")
    print(f"  {'─' * 6} {'─' * 8} {'─' * 12} {'─' * 8} {'─' * 8} {'─' * 12}")
    for year in ['2024', '2025', '2026']:
        s = all_summaries.get(year)
        if not s:
            continue
        sr = f"{s['slope_ratio']:.2f}" if s['slope_ratio'] is not None else "—"
        print(f"  {year:<6} {s['full']['sharpe']:>8.3f} "
              f"{s['full']['sum']:>12.2f} "
              f"{s['top5_pct']:>7.1f}% {s['hhi']:>8.4f} {sr:>12}")

    print()
    print("═" * 72)
    print("  التفسير:")
    print("═" * 72)
    print("""
  • Top5%: لو > 60% → الحافة مركّزة (خطر)
  • HHI: 0.05=موزع صحي، 0.2+=مركّز خطير
  • slope_ratio: < 0.5 → الفلتر الاتجاهي مفيد
                  > 1.0 → الفلتر سيضُر
  • Σpnl عبر السنوات: يجب أن يكون موجباً في كل سنة
""")


if __name__ == '__main__':
    main()
