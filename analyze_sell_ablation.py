#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_sell_ablation.py — يقارن SELL strategies + الدمج مع BUY."""
import json, re, sys
from pathlib import Path
import numpy as np

STRATEGIES = {
    'S0_baseline_buy_only': None,   # production (no SELL)
    'S1': '--enable-sell --sell-gauge-pct 0.95',
    'S2': '--enable-sell --sell-gauge-pct 0.98',
    'S3': '--enable-sell --sell-min-score 5 --sell-gauge-pct 0.95',
    'S4': '--enable-sell --sell-min-zdev 2.5 --sell-gauge-pct 0.95',
    'S5': '--enable-sell --sell-require-ema-down --sell-gauge-pct 0.95',
    'S6': '--enable-sell --sell-major-only --sell-gauge-pct 0.95',
    'S7': '--enable-sell --sell-min-atr-frac 0.02 --sell-gauge-pct 0.95',
}
YEARS = ['2024', '2025', '2026']


def get_metrics(log_path):
    try:
        text = Path(log_path).read_text(encoding='utf-8', errors='ignore')
    except FileNotFoundError:
        return None
    m = re.search(r"شارب \(سنوي\)\s+:\s+([\d.\-]+)", text)
    f = re.search(r"نهائي:\s+\$([\d,.]+)", text)
    return {
        'sharpe': float(m.group(1)) if m else None,
        'final': float(f.group(1).replace(',', '')) if f else None,
    }


def count_by_action(jsonl_path):
    n_buy = n_sell = 0
    try:
        with open(jsonl_path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get('_meta'):
                    continue
                if r.get('action') == 'BUY':
                    n_buy += 1
                elif r.get('action') == 'SELL':
                    n_sell += 1
    except FileNotFoundError:
        pass
    return n_buy, n_sell


def main():
    base = Path('results/sell_ablation')
    # S0: from ablation run
    s0_paths = {
        y: Path(f'results/ablation/buy_only_{y}.log')
        for y in YEARS
    }

    print("═" * 100)
    print("  SELL R&D — مقارنة 7 استراتيجيات + BUY-only baseline")
    print("═" * 100)

    results = {}
    # S0
    results['S0'] = {}
    for y in YEARS:
        m = get_metrics(s0_paths[y])
        if m:
            results['S0'][y] = {**m, 'buy': 0, 'sell': 0}

    # S1-S7
    for sid in ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']:
        results[sid] = {}
        for y in YEARS:
            log = base / f"{sid}_{y}.log"
            trades = base / f"{sid}_{y}.jsonl"
            m = get_metrics(log)
            if m is None:
                continue
            buy, sell = count_by_action(trades)
            results[sid][y] = {**m, 'buy': buy, 'sell': sell}

    # Table 1: Sharpe
    print(f"\n  {'Strat':<6} {'2024':>8} {'2025':>8} {'2026':>8} "
          f"{'Min':>8} {'SellCount':>11} {'Verdict':<15}")
    print(f"  {'─'*6} {'─'*8} {'─'*8} {'─'*8} {'─'*8} {'─'*11} {'─'*15}")

    winners = []
    for sid in ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']:
        vals = [results[sid].get(y, {}).get('sharpe') for y in YEARS]
        if any(v is None for v in vals):
            print(f"  {sid:<6} — missing")
            continue
        mn = min(vals)
        total_sell = sum(results[sid].get(y, {}).get('sell', 0) for y in YEARS)

        # Verdict
        if sid == 'S0':
            verdict = "REFERENCE"
        elif mn < 0.8:
            verdict = "❌ weak"
        elif total_sell < 300:
            verdict = "⚠️ too few"
        elif mn >= 1.55:
            verdict = "✅ WINNER"
            winners.append(sid)
        else:
            verdict = "🟡 candidate"

        print(f"  {sid:<6} {vals[0]:>8.3f} {vals[1]:>8.3f} {vals[2]:>8.3f} "
              f"{mn:>8.3f} {total_sell:>11} {verdict:<15}")

    print()
    if winners:
        print(f"  🏆 Winners for merge: {', '.join(winners)}")
        print(f"     Min Sharpe ≥ 1.55 AND ≥300 SELL trades")
    else:
        print(f"  ℹ️  No strategy met the merge criteria yet")
        print(f"     BUY-only remains the best production config")

    # Table 2: SELL count breakdown
    print(f"\n  عدد صفقات SELL لكل استراتيجية:")
    print(f"  {'Strat':<6} {'2024':>8} {'2025':>8} {'2026':>8} {'Total':>8}")
    for sid in ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']:
        if not all(y in results[sid] for y in YEARS):
            continue
        sells = [results[sid][y]['sell'] for y in YEARS]
        print(f"  {sid:<6} {sells[0]:>8} {sells[1]:>8} {sells[2]:>8} "
              f"{sum(sells):>8}")


if __name__ == '__main__':
    main()
