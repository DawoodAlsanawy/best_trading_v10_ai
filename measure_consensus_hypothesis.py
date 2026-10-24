#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
measure_consensus_hypothesis.py
================================
Measures the "5-coin consensus" hypothesis on existing trade logs.

Hypothesis:
    Trades with 5+ other trades in the SAME direction, within ±N bars,
    have higher win rate and E[ln] than isolated trades.

Test:
    For each trade T (symbol S, entry time t, direction D):
        Count other trades T' where:
            - T'.symbol != T.symbol
            - T'.direction == T.direction
            - |T'.entry_time - T.entry_time| <= window_bars × tf_seconds

    Group trades by this "consensus count" and compare metrics.

Output:
    1. Distribution of consensus counts
    2. Performance by bucket (0-1, 2-3, 4-5, 6-7, 8+)
    3. Threshold sweep (>=3, >=4, >=5, >=6, >=7)
    4. BUY vs SELL split
    5. Recommendation (implement or not)

Usage:
    python3 measure_consensus_hypothesis.py
    python3 measure_consensus_hypothesis.py --window-bars 3 --timeframe 4h
    python3 measure_consensus_hypothesis.py --log trades_log_backtest.jsonl

No files are modified. Read-only analysis.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════
# Loaders
# ══════════════════════════════════════════════════════════════
def load_trades(path):
    """Load trades from JSONL, skip _meta, validate required fields."""
    trades = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("_meta"):
                continue
            if not all(k in r for k in ("symbol", "entry_time", "action")):
                continue
            trades.append(r)
    return trades


def parse_timeframe(tf_str):
    """Convert '4h', '1d', '15m', etc. to seconds."""
    tf_str = str(tf_str).lower().strip()
    try:
        if tf_str.endswith("m"):
            return int(tf_str[:-1]) * 60
        if tf_str.endswith("h"):
            return int(tf_str[:-1]) * 3600
        if tf_str.endswith("d"):
            return int(tf_str[:-1]) * 86400
    except Exception:
        pass
    return 3600


def parse_trade_time(ts):
    """Parse ISO string or epoch to float seconds."""
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        dt = pd.Timestamp(ts)
        if dt.tz is None:
            dt = dt.tz_localize("UTC")
        return float(dt.timestamp())
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# Consensus computation
# ══════════════════════════════════════════════════════════════
def compute_consensus(trades, tf_sec, window_bars):
    """
    For each trade, count OTHER trades in the same direction
    within ±window_bars.

    O(n log n + n × window_size) via sorted search.
    """
    for t in trades:
        t["_entry_ts"] = parse_trade_time(t.get("entry_time"))
        t["_consensus"] = 0

    valid = [t for t in trades if t["_entry_ts"] is not None]
    if not valid:
        return valid

    window_sec = window_bars * tf_sec

    # Process each direction separately
    for direction in ("BUY", "SELL"):
        group = [t for t in valid if t["action"] == direction]
        if not group:
            continue

        # Sort by time
        group.sort(key=lambda x: x["_entry_ts"])
        times = np.array([t["_entry_ts"] for t in group], dtype=np.float64)
        symbols = [t["symbol"] for t in group]

        for i, t in enumerate(group):
            left = int(np.searchsorted(times, t["_entry_ts"] - window_sec,
                                         side="left"))
            right = int(np.searchsorted(times, t["_entry_ts"] + window_sec,
                                          side="right"))
            total_in_window = right - left - 1  # exclude self
            if total_in_window <= 0:
                continue

            # Subtract same-symbol trades
            same_sym = 0
            for j in range(left, right):
                if j != i and symbols[j] == t["symbol"]:
                    same_sym += 1

            t["_consensus"] = max(0, total_in_window - same_sym)

    return valid


# ══════════════════════════════════════════════════════════════
# Metrics
# ══════════════════════════════════════════════════════════════
def bucket_stats(trades):
    """Compute comprehensive stats for a group of trades."""
    if not trades:
        return None

    n = len(trades)
    pnls = [t.get("net_pnl", 0) for t in trades]
    lrs = [t.get("log_return", 0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    avg_lr = float(np.mean(lrs))
    std_lr = float(np.std(lrs, ddof=1)) if n > 1 else 0.0
    sharpe = (avg_lr / std_lr * np.sqrt(252)) if std_lr > 1e-10 else 0.0

    mfes = [t.get("mfe_frac", 0) or 0 for t in trades]
    holds = [t.get("hold_bars", 0) or 0 for t in trades]

    # Exit reason distribution
    exits = defaultdict(int)
    for t in trades:
        r = str(t.get("exit_reason", "?"))
        # Simplify
        if "Emergency SL" in r:
            exits["SL"] += 1
        elif "Hard TP" in r:
            exits["TP"] += 1
        elif "MaxHold" in r:
            exits["MaxHold"] += 1
        elif "Apex" in r:
            exits["Apex"] += 1
        elif "Topo" in r:
            exits["Topo"] += 1
        elif "BEEsc" in r:
            exits["BEEsc"] += 1
        else:
            exits["Other"] += 1

    return {
        "n": n,
        "win_rate": len(wins) / n,
        "E_ln": avg_lr,
        "std_ln": std_lr,
        "sharpe": sharpe,
        "avg_win": float(np.mean(wins)) if wins else 0.0,
        "avg_loss": float(np.mean(losses)) if losses else 0.0,
        "E_ln_x_N": avg_lr * n,
        "avg_mfe": float(np.mean(mfes)) if mfes else 0.0,
        "median_mfe": float(np.median(mfes)) if mfes else 0.0,
        "avg_hold": float(np.mean(holds)) if holds else 0.0,
        "exits": dict(exits),
    }


def format_stats(s):
    if s is None:
        return "—"
    return (f"N={s['n']:>5}  Win={s['win_rate']*100:>5.1f}%  "
            f"E[ln]={s['E_ln']:>+10.6f}  Sharpe={s['sharpe']:>6.2f}")


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(
        description="Measure '5-coin consensus' hypothesis on trade logs.")
    ap.add_argument("--log", default="trades_log_backtest.jsonl",
                    help="Path to trades log (JSONL)")
    ap.add_argument("--timeframe", default="4h",
                    help="Timeframe (default 4h)")
    ap.add_argument("--window-bars", type=int, default=3,
                    help="Window in bars (default ±3)")
    ap.add_argument("--thresholds", default="2,3,4,5,6,7",
                    help="Comma-separated thresholds to test")
    ap.add_argument("--min-trades-for-threshold", type=int, default=50,
                    help="Ignore thresholds that keep < N trades")
    args = ap.parse_args()

    if not os.path.exists(args.log):
        print(f"ERROR: file not found: {args.log}")
        sys.exit(1)

    print(f"Reading {args.log}...")
    trades = load_trades(args.log)
    print(f"  Loaded: {len(trades):,} trades")

    if len(trades) < 50:
        print("  ⚠ Not enough trades for analysis (< 50)")
        sys.exit(1)

    tf_sec = parse_timeframe(args.timeframe)
    window_sec = args.window_bars * tf_sec
    print(f"  Timeframe: {args.timeframe} ({tf_sec}s)")
    print(f"  Window: ±{args.window_bars} bars (±{window_sec/3600:.1f}h)")
    print()

    # ── Compute consensus ──
    print("Computing consensus per trade...")
    valid = compute_consensus(trades, tf_sec, args.window_bars)
    print(f"  Valid trades: {len(valid):,}\n")

    if len(valid) < 50:
        print("Not enough valid trades.")
        sys.exit(1)

    # ══════════════════════════════════════════════════════════
    # Section 1 — Distribution
    # ══════════════════════════════════════════════════════════
    print("=" * 78)
    print("  1. CONSENSUS DISTRIBUTION")
    print("=" * 78)

    consensuses = np.array([t["_consensus"] for t in valid])
    print(f"\n  Min: {int(consensuses.min())}")
    print(f"  Median: {int(np.median(consensuses))}")
    print(f"  Mean: {consensuses.mean():.2f}")
    print(f"  Std: {consensuses.std():.2f}")
    print(f"  Max: {int(consensuses.max())}")

    print(f"\n  Histogram (bars are relative):")
    hist = defaultdict(int)
    for c in consensuses:
        hist[int(c)] += 1
    max_cnt = max(hist.values()) if hist else 1
    for c in sorted(hist.keys()):
        cnt = hist[c]
        pct = cnt / len(valid) * 100
        bar = "█" * int(cnt / max_cnt * 40)
        print(f"    {c:>2d} signals: {cnt:>5} ({pct:>5.1f}%) {bar}")

    # ══════════════════════════════════════════════════════════
    # Section 2 — Bucket performance
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  2. PERFORMANCE BY CONSENSUS BUCKET")
    print("=" * 78)

    buckets = [
        ("0-1 (isolated)",  lambda c: c <= 1),
        ("2-3 (low)",       lambda c: 2 <= c <= 3),
        ("4-5 (medium)",    lambda c: 4 <= c <= 5),
        ("6-7 (high)",      lambda c: 6 <= c <= 7),
        ("8+ (very high)",  lambda c: c >= 8),
    ]

    header = (f"\n  {'Bucket':<20} {'N':>6} {'Win%':>7} {'E[ln]':>11} "
              f"{'E[ln]×N':>10} {'Sharpe':>8} {'AvgMFE':>8} {'Hold':>6}")
    print(header)
    print("  " + "-" * 76)

    for label, filter_fn in buckets:
        group = [t for t in valid if filter_fn(t["_consensus"])]
        s = bucket_stats(group)
        if s:
            print(f"  {label:<20} {s['n']:>6} "
                  f"{s['win_rate']*100:>6.1f}% "
                  f"{s['E_ln']:>+11.6f} "
                  f"{s['E_ln_x_N']:>+10.3f} "
                  f"{s['sharpe']:>8.2f} "
                  f"{s['avg_mfe']*100:>7.2f}% "
                  f"{s['avg_hold']:>6.1f}")
        else:
            print(f"  {label:<20} {0:>6} {'—':>7} {'—':>11} "
                  f"{'—':>10} {'—':>8} {'—':>8} {'—':>6}")

    # Exit distribution per bucket
    print(f"\n  Exit reason distribution per bucket:")
    print(f"  {'Bucket':<20} {'SL%':>6} {'TP%':>6} {'MaxHold%':>10} "
          f"{'Apex%':>7} {'BEEsc%':>8}")
    print("  " + "-" * 62)
    for label, filter_fn in buckets:
        group = [t for t in valid if filter_fn(t["_consensus"])]
        s = bucket_stats(group)
        if not s:
            continue
        exits = s["exits"]
        n = s["n"]
        print(f"  {label:<20} "
              f"{exits.get('SL',0)/n*100:>5.1f}% "
              f"{exits.get('TP',0)/n*100:>5.1f}% "
              f"{exits.get('MaxHold',0)/n*100:>9.1f}% "
              f"{exits.get('Apex',0)/n*100:>6.1f}% "
              f"{exits.get('BEEsc',0)/n*100:>7.1f}%")

    # ══════════════════════════════════════════════════════════
    # Section 3 — Threshold sweep
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  3. THRESHOLD SWEEP (require consensus >= N)")
    print("=" * 78)

    thresholds = []
    for x in args.thresholds.split(","):
        try:
            thresholds.append(int(x.strip()))
        except ValueError:
            continue

    baseline = bucket_stats(valid)
    print(f"\n  Baseline (all trades): {format_stats(baseline)}")

    print(f"\n  {'Threshold':<12} {'N keep':>8} {'Keep%':>7} {'Win%':>7} "
          f"{'E[ln]':>11} {'E[ln]×N':>10} {'Δ vs base':>11} {'Score':>8}")
    print("  " + "-" * 78)

    best_thr = None
    best_score = baseline["E_ln_x_N"]  # E[ln]×N
    results_by_thr = {}

    for thr in thresholds:
        passing = [t for t in valid if t["_consensus"] >= thr]
        s = bucket_stats(passing)
        if s is None:
            continue
        results_by_thr[thr] = s

        keep_pct = s["n"] / len(valid) * 100
        delta = s["E_ln_x_N"] - baseline["E_ln_x_N"]
        # Score: E[ln]×N (simple total profit proxy)
        score = s["E_ln_x_N"]

        marker = " ⭐" if score > best_score else ""
        if s["n"] >= args.min_trades_for_threshold and score > best_score:
            best_score = score
            best_thr = thr

        print(f"  >={thr:<10} {s['n']:>8} {keep_pct:>6.1f}% "
              f"{s['win_rate']*100:>6.1f}% "
              f"{s['E_ln']:>+11.6f} "
              f"{s['E_ln_x_N']:>+10.3f} "
              f"{delta:>+11.3f} "
              f"{score:>+8.3f}{marker}")

    # ══════════════════════════════════════════════════════════
    # Section 4 — Direction split
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  4. BUY vs SELL SPLIT")
    print("=" * 78)

    for action in ("BUY", "SELL"):
        group = [t for t in valid if t["action"] == action]
        if not group:
            continue
        cons_grp = np.array([t["_consensus"] for t in group])
        s = bucket_stats(group)
        print(f"\n  ── {action} ──")
        print(f"  Total: {s['n']} trades, median consensus = "
              f"{int(np.median(cons_grp))}, mean = {cons_grp.mean():.2f}")
        print(f"  Baseline: Win={s['win_rate']*100:.1f}%, "
              f"E[ln]={s['E_ln']:+.6f}, E[ln]×N={s['E_ln_x_N']:+.3f}")

        for thr in (3, 5, 7):
            passing = [t for t in group if t["_consensus"] >= thr]
            s2 = bucket_stats(passing)
            if s2 and s2["n"] >= 20:
                delta = s2["E_ln_x_N"] - s["E_ln_x_N"]
                print(f"    >={thr}: N={s2['n']:>5} "
                      f"Win={s2['win_rate']*100:>5.1f}% "
                      f"E[ln]={s2['E_ln']:>+10.6f} "
                      f"E[ln]×N={s2['E_ln_x_N']:>+8.3f} "
                      f"(Δ={delta:+.3f})")

    # ══════════════════════════════════════════════════════════
    # Section 5 — Recommendation
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  5. RECOMMENDATION")
    print("=" * 78)

    if best_thr is None:
        print("\n  ❌ NO THRESHOLD IMPROVES E[ln]×N")
        print("     The consensus filter is NOT useful on this data.")
        print("     → Do NOT implement it.")
        print("\n  Note: 'NO EDGE' here means: filtering by consensus")
        print("  reduces total profit. The hypothesis is REJECTED.")
    else:
        s_best = results_by_thr[best_thr]
        delta_abs = s_best["E_ln_x_N"] - baseline["E_ln_x_N"]
        delta_pct = (delta_abs / abs(baseline["E_ln_x_N"]) * 100
                     if baseline["E_ln_x_N"] != 0 else 0)

        print(f"\n  Best threshold: consensus >= {best_thr}")
        print(f"  Δ E[ln]×N: {delta_abs:+.3f} ({delta_pct:+.1f}%)")
        print(f"  Trades kept: {s_best['n']} / {len(valid)} "
              f"({s_best['n']/len(valid)*100:.1f}%)")
        print(f"  E[ln] kept: {s_best['E_ln']:+.6f} "
              f"(vs baseline {baseline['E_ln']:+.6f})")
        print(f"  Win%: {s_best['win_rate']*100:.1f}% "
              f"(vs {baseline['win_rate']*100:.1f}%)")
        print(f"  Sharpe: {s_best['sharpe']:.2f} "
              f"(vs {baseline['sharpe']:.2f})")

        print()
        if delta_pct > 20 and s_best["n"] >= 200:
            print("  ✅ STRONG EDGE — worth implementing")
            print(f"     Estimated gain: +{delta_pct:.0f}% in total profit")
        elif delta_pct > 5 and s_best["n"] >= 500:
            print("  🟡 MODERATE EDGE — worth A/B testing")
            print(f"     Estimated gain: +{delta_pct:.0f}% in total profit")
        elif delta_pct > 0:
            print("  🔵 WEAK EDGE — unlikely to help live")
            print(f"     Marginal gain: {delta_pct:+.1f}%")
        else:
            print(f"  ❌ NEGATIVE EDGE ({delta_pct:+.1f}%)")
            print("     Do NOT implement.")

    # ══════════════════════════════════════════════════════════
    # Section 6 — Caveats
    # ══════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("  6. STATISTICAL CAVEATS")
    print("=" * 78)

    print("""
  ⚠ IMPORTANT LIMITATIONS of this analysis:

  1. SELECTION BIAS
     These are EXECUTED trades — not all signals. The bot may have
     filtered some signals by CORRELATION_THRESHOLD (0.70) and
     MAX_CONCURRENT_ASSETS. Trades here are a subset of signals.

  2. CORRELATION NATURAL IN CRYPTO
     Coins are ~70% correlated. "5+ consensus" may occur 50-70% of
     the time REGARDLESS of signal quality. That's why we measure
     win rate per bucket — to see if consensus adds signal.

  3. NO TRANSACTION COST MODELING
     Live execution may degrade consensus trades (many orders hit
     the book simultaneously → worse fills, more slippage).

  4. WINDOW SIZE MATTERS
     Used ±3 bars = ±12h on 4h. Try ±1, ±2, ±5 to check robustness.
     If the edge appears only at one specific window, it's suspect.

  5. IN-SAMPLE TEST
     This is the same data the bot was tuned on. The edge may not
     survive OUT-OF-SAMPLE. Always test on the last 90-180 days.

  If the edge survives ALL of these checks, THEN it's real.
    """)

    print("=" * 78)
    print("  ANALYSIS COMPLETE")
    print("=" * 78)


if __name__ == "__main__":
    main()
