#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
live_vs_backtest.py — يقارن نتائج Testnet الحقيقية بـ abl8b
============================================================

يقرأ trades_log_testnet.jsonl (أو live) ويقارن مع baseline abl8b.
"""
import json
import sys
import os
from collections import defaultdict
from statistics import mean, median


BASELINE_ABL8B = {
    "n_trades": 3229,
    "wr": 0.493,
    "pf": 1.125,
    "sharpe": 1.920,
    "max_dd": 0.4288,
    "mean_ln": 0.001714,
    "median_ln": -0.000400,
    "buy_frac": 2776 / 3229,
}


def load_trades(path):
    trades = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("_meta"):
                continue
            trades.append(rec)
    return trades


def compute_stats(trades):
    if not trades:
        return {}
    pnls = [float(t.get("net_pnl", 0.0) or 0.0) for t in trades]
    lrs  = [float(t.get("log_return", 0.0) or 0.0) for t in trades]
    actions = [t.get("action", "?") for t in trades]

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = len(wins) / len(pnls)
    pf = sum(wins) / abs(sum(losses)) if losses and wins else float("inf")

    m = float(mean(lrs)) if lrs else 0.0
    sd = float(mean([(x - m) ** 2 for x in lrs]) ** 0.5) if lrs else 0.0
    sharpe = (m / sd * (252 ** 0.5)) if sd > 1e-9 else 0.0

    # Equity & DD (from cumulative log returns)
    eq = [1.0]
    for lr in lrs:
        eq.append(eq[-1] * (1.0 + lr))
    peak = eq[0]
    dd_max = 0.0
    for v in eq:
        if v > peak:
            peak = v
        dd = (peak - v) / max(peak, 1e-12)
        if dd > dd_max:
            dd_max = dd

    buy_count = sum(1 for a in actions if a == "BUY")
    buy_frac = buy_count / max(len(actions), 1)

    return {
        "n_trades": len(trades),
        "wr": wr,
        "pf": pf,
        "sharpe": sharpe,
        "max_dd": dd_max,
        "mean_ln": m,
        "median_ln": float(median(lrs)) if lrs else 0.0,
        "buy_frac": buy_frac,
    }


def print_comparison(live, base, label):
    print(f"\n{'═' * 78}")
    print(f"  {label}")
    print(f"{'═' * 78}")
    print(f"{'Metric':<18s} {'Live/New':>14s} {'ABL8B':>14s} {'Δ':>14s}")
    print(f"{'-' * 78}")

    rows = [
        ("n_trades", "n_trades", "{:.0f}", "{:.0f}"),
        ("Win Rate", "wr", "{:.1%}", "{:.1%}"),
        ("Profit Factor", "pf", "{:.3f}", "{:.3f}"),
        ("Sharpe (ann)", "sharpe", "{:+.3f}", "{:+.3f}"),
        ("Max Drawdown", "max_dd", "{:.1%}", "{:.1%}"),
        ("E[ln(1+fR)]", "mean_ln", "{:+.6f}", "{:+.6f}"),
        ("Median ln", "median_ln", "{:+.6f}", "{:+.6f}"),
        ("BUY fraction", "buy_frac", "{:.1%}", "{:.1%}"),
    ]

    for name, key, fmt, _ in rows:
        live_v = live.get(key, 0)
        base_v = base.get(key, 0)
        delta = live_v - base_v
        print(f"{name:<18s} {fmt.format(live_v):>14s} "
              f"{fmt.format(base_v):>14s} {delta:>+14.4f}")

    # Verdict
    print(f"\n{'─' * 78}")
    verdict = []
    if live["mean_ln"] > 0:
        verdict.append("✅ E[ln] positive")
    else:
        verdict.append("❌ E[ln] negative")

    if live["max_dd"] < 0.55:
        verdict.append("✅ DD < 55%")
    elif live["max_dd"] < 0.70:
        verdict.append("⚠ DD 55-70%")
    else:
        verdict.append("❌ DD > 70%")

    if live["n_trades"] < 30:
        verdict.append(f"⚠ Sample too small ({live['n_trades']})")
    elif live["n_trades"] < 100:
        verdict.append(f"⚠ Sample modest ({live['n_trades']})")
    else:
        verdict.append(f"✅ Sample OK ({live['n_trades']})")

    print("  " + " | ".join(verdict))


def main():
    if len(sys.argv) < 2:
        print("Usage: python live_vs_backtest.py <trades.jsonl> [<trades2.jsonl>...]")
        print()
        print("Examples:")
        print("  python live_vs_backtest.py trades_log_testnet.jsonl")
        print("  python live_vs_backtest.py trades_abl8b.jsonl")
        sys.exit(1)

    for path in sys.argv[1:]:
        if not os.path.exists(path):
            print(f"[skip] {path} not found")
            continue
        trades = load_trades(path)
        if not trades:
            print(f"[skip] {path} empty or unparseable")
            continue
        stats = compute_stats(trades)
        print_comparison(stats, BASELINE_ABL8B, f"FILE: {path}")


if __name__ == "__main__":
    main()
