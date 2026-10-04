#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_ablation.py — مقارنة 4 variants × 3 windows
يجيب: أي إعداد يعطي أفضل Sharpe عبر السنوات الثلاث؟
"""

import json
import re
from pathlib import Path
import numpy as np


def extract_metrics(log_path):
    """يقرأ Sharpe + final capital من سجل الباكتيست."""
    try:
        text = Path(log_path).read_text(encoding='utf-8', errors='ignore')
    except FileNotFoundError:
        return None

    sharpe = None
    final = None

    m = re.search(r"شارب \(سنوي\)\s+:\s+([\d.\-]+)", text)
    if m:
        sharpe = float(m.group(1))

    m = re.search(r"نهائي:\s+\$([\d,.]+)", text)
    if m:
        final = float(m.group(1).replace(',', ''))

    return {'sharpe': sharpe, 'final': final}


def count_from_trades(jsonl_path):
    """إحصاءات من ملف الصفقات."""
    n_trades = 0
    n_buy = 0
    n_sell = 0
    total_pnl = 0.0
    try:
        with open(jsonl_path, encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get('_meta'):
                    continue
                n_trades += 1
                if r.get('action') == 'BUY':
                    n_buy += 1
                elif r.get('action') == 'SELL':
                    n_sell += 1
                total_pnl += float(r.get('net_pnl') or 0.0)
    except FileNotFoundError:
        pass
    return {'n': n_trades, 'buy': n_buy, 'sell': n_sell,
            'sum_pnl': total_pnl}


def main():
    base = Path('results/ablation')
    variants = ['baseline', 'buy_only', 'min_score_4', 'sell_085']
    years = ['2024', '2025', '2026']

    results = {}

    for v in variants:
        results[v] = {}
        for y in years:
            log = base / f"{v}_{y}.log"
            trades = base / f"{v}_{y}.jsonl"
            m = extract_metrics(log)
            if m is None:
                continue
            t = count_from_trades(trades)
            results[v][y] = {**m, **t}

    # ═══ Table 1: Sharpe ═══
    print("═" * 100)
    print("  Sharpe عبر السنوات")
    print("═" * 100)
    print()
    print(f"  {'Variant':<16} {'2024':>10} {'2025':>10} "
          f"{'2026':>10} {'Min':>10} {'Avg':>10}")
    print(f"  {'─' * 16} {'─' * 10} {'─' * 10} "
          f"{'─' * 10} {'─' * 10} {'─' * 10}")

    for v in variants:
        vals = [results[v].get(y, {}).get('sharpe') for y in years]
        valid = [x for x in vals if x is not None]
        min_s = min(valid) if valid else None
        avg_s = sum(valid) / len(valid) if valid else None

        def fmt(x):
            return f"{x:.3f}" if x is not None else "—"

        print(f"  {v:<16} {fmt(vals[0]):>10} {fmt(vals[1]):>10} "
              f"{fmt(vals[2]):>10} {fmt(min_s):>10} {fmt(avg_s):>10}")

    # ═══ Table 2: Final Capital ═══
    print()
    print("═" * 100)
    print("  رأس المال النهائي (من $100)")
    print("═" * 100)
    print()
    print(f"  {'Variant':<16} {'2024':>12} {'2025':>12} "
          f"{'2026':>12} {'Min':>12} {'GeoMean':>12}")
    print(f"  {'─' * 16} {'─' * 12} {'─' * 12} "
          f"{'─' * 12} {'─' * 12} {'─' * 12}")

    for v in variants:
        vals = [results[v].get(y, {}).get('final') for y in years]
        valid = [x for x in vals if x is not None and x > 0]
        min_v = min(valid) if valid else None
        geo = (np.prod(valid) ** (1.0/len(valid))) if valid else None

        def fmt(x):
            return f"${x:,.0f}" if x is not None else "—"

        print(f"  {v:<16} {fmt(vals[0]):>12} {fmt(vals[1]):>12} "
              f"{fmt(vals[2]):>12} {fmt(min_v):>12} {fmt(geo):>12}")

    # ═══ Table 3: Number of Trades & BUY/SELL split ═══
    print()
    print("═" * 100)
    print("  عدد الصفقات و BUY/SELL")
    print("═" * 100)
    print()

    for v in variants:
        print(f"\n  ▶ {v}:")
        for y in years:
            r = results[v].get(y, {})
            n = r.get('n', 0)
            buy = r.get('buy', 0)
            sell = r.get('sell', 0)
            print(f"     {y}: n={n:5d}  (BUY={buy:5d}, SELL={sell:5d})")

    # ═══ Final Verdict ═══
    print()
    print("═" * 100)
    print("  الحكم النهائي — أي variant يفوز؟")
    print("═" * 100)
    print()

    # Score each variant: min_sharpe + log(geo_mean_final)
    scores = {}
    for v in variants:
        vals = [results[v].get(y, {}).get('sharpe') for y in years]
        finals = [results[v].get(y, {}).get('final')
                  for y in years]
        valid_s = [x for x in vals if x is not None]
        valid_f = [x for x in finals
                   if x is not None and x > 0]

        min_sharpe = min(valid_s) if valid_s else 0
        geo_final = np.prod(valid_f) ** (1.0/len(valid_f)) if valid_f else 0

        # Score = min_sharpe × log10(geo_final)
        log_geo = np.log10(geo_final) if geo_final > 0 else 0
        score = min_sharpe * log_geo
        scores[v] = {
            'min_sharpe': min_sharpe,
            'geo_final': geo_final,
            'score': score,
        }

    print(f"  {'Variant':<16} {'MinSharpe':>12} {'GeoFinal$':>12} "
          f"{'Score':>10}")
    print(f"  {'─' * 16} {'─' * 12} {'─' * 12} {'─' * 10}")

    ranked = sorted(scores.items(), key=lambda x: -x[1]['score'])
    for v, s in ranked:
        marker = " 🏆" if v == ranked[0][0] else ""
        print(f"  {v:<16} {s['min_sharpe']:>12.3f} "
              f"${s['geo_final']:>10,.0f} "
              f"{s['score']:>10.3f}{marker}")

    print()
    print(f"  ⚠️  ملاحظة: Score = MinSharpe × log10(GeoFinal)")
    print(f"      يكافئ Sharpe متسق عبر السنوات AND نمواً جيداً.")

    # ═══ Recommendation ═══
    best = ranked[0][0]
    print()
    print(f"  💡 التوصية: {best}")
    print()

    # Detail analysis
    print(f"  تحليل مفصل لـ {best}:")
    for y in years:
        r = results[best].get(y, {})
        print(f"     {y}: Sharpe={r.get('sharpe')} "
              f"final=${r.get('final', 0):,.0f} "
              f"n={r.get('n', 0)} "
              f"(BUY={r.get('buy', 0)}, SELL={r.get('sell', 0)})")


if __name__ == '__main__':
    main()
