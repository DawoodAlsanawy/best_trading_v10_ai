#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bee_failure_analysis.py
=======================
Replays every trade from the log to answer ONE question:

    After price moves against us by K × SL,
    does it come back to entry BEFORE the final SL?

This is exactly what determines whether BEEsc (TP→entry) can work.
If not, we tune BREAKEVEN_ESCAPE_MIN_PROFIT_R to the level price
actually reaches (a small loss exit instead of a full SL).

Usage:
    python3 bee_failure_analysis.py
    python3 bee_failure_analysis.py --log trades_log_backtest.jsonl
    python3 bee_failure_analysis.py --timeframe 4h --K 0.2,0.3,0.5,0.7,1.0
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

CACHE_DIR = "market_data_cache"


# ─────────────────────────────────────────────────────────────
def load_trades(path):
    trades = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("_meta"):
                continue
            if "entry_price" not in r or "exit_price" not in r:
                continue
            if "symbol" not in r or "action" not in r:
                continue
            trades.append(r)
    return trades


def load_candles(symbol, timeframe):
    fp = os.path.join(CACHE_DIR,
                      f"{symbol.replace('/','_')}_{timeframe}.parquet")
    if not os.path.exists(fp):
        return None
    try:
        df = pd.read_parquet(fp)
    except Exception as e:
        print(f"  WARN: cannot read {fp}: {e}")
        return None
    if df.index.tz is None:
        df.index = pd.to_datetime(df.index, utc=True)
    else:
        df.index = df.index.tz_convert("UTC")
    return df


# ─────────────────────────────────────────────────────────────
def analyze_trade(trade, df, K_levels):
    try:
        entry_ts = pd.Timestamp(trade["entry_time"])
        if entry_ts.tz is None:
            entry_ts = entry_ts.tz_localize("UTC")
        entry_price = float(trade["entry_price"])
        exit_price  = float(trade["exit_price"])
        action      = trade["action"]
        exit_reason = str(trade.get("exit_reason", "?"))

        sl_dist = float(trade.get("sl_dist_initial", 0) or 0)
        if sl_dist <= 0:
            _sig_sl = float(trade.get("signal_sl", 0) or 0)
            if _sig_sl > 0:
                sl_dist = abs(entry_price - _sig_sl)
            else:
                sl_dist = entry_price * 0.01
        if sl_dist <= 0 or entry_price <= 0:
            return None

        try:
            idx = df.index.get_indexer([entry_ts], method="nearest",
                                        tolerance="5min")
        except Exception:
            idx = [-1]
        if len(idx) == 0 or idx[0] < 0:
            return {"error": "entry_bar_not_found",
                    "symbol": trade.get("symbol", "?")}
        entry_ci = idx[0]

        hold_bars = int(trade.get("hold_bars", 0) or 0)
        end_ci = min(entry_ci + max(hold_bars, 50) + 5, len(df))
        if end_ci - entry_ci < 2:
            return None

        w = df.iloc[entry_ci:end_ci]
        highs  = w["High"].values.astype(np.float64)
        lows   = w["Low"].values.astype(np.float64)
        closes = w["Close"].values.astype(np.float64)

        # Trigger basis = close (matches BEEsc live & backtest trigger)
        # Recovery basis = high/low (matches TP check)
        if action == "BUY":
            adverse_close = (entry_price - closes) / sl_dist
            adverse_worst = (entry_price - lows) / sl_dist
            favorable     = (highs - entry_price) / sl_dist
        else:
            adverse_close = (closes - entry_price) / sl_dist
            adverse_worst = (highs - entry_price) / sl_dist
            favorable     = (entry_price - lows) / sl_dist

        r = {
            "symbol": trade["symbol"],
            "action": action,
            "exit_reason": exit_reason,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "sl_dist": sl_dist,
            "hold_bars": int(len(w) - 1),
            "final_R": ((exit_price - entry_price) / sl_dist
                        if action == "BUY"
                        else (entry_price - exit_price) / sl_dist),
            "peak_adverse_R":  float(np.max(adverse_worst)),
            "max_favorable_R": float(np.max(favorable)),
        }

        for K in K_levels:
            trig_bars = np.where(adverse_close >= K)[0]
            if len(trig_bars) == 0:
                r[f"trig_{K}"]           = -1
                r[f"recov_{K}"]          = None
                r[f"recov_b4sl_{K}"]     = None
                r[f"recov_b4exit_{K}"]   = None
                r[f"hit_entry_{K}"]      = None
                r[f"hit_entry_b4sl_{K}"] = None
                continue

            trig = int(trig_bars[0])
            r[f"trig_{K}"] = trig

            fut_fav = favorable[trig:]
            fut_adv = adverse_worst[trig:]

            # Optimistic: no SL exists
            best_rec = float(np.max(fut_fav)) if len(fut_fav) else None
            r[f"recov_{K}"] = best_rec
            r[f"hit_entry_{K}"] = (best_rec is not None and best_rec >= 0.0)

            # Realistic: entry reached BEFORE -1R SL?
            best_b4sl, hit_b4sl = -999.0, False
            for j in range(len(fut_fav)):
                if fut_adv[j] >= 1.0:      # SL first (pessimistic)
                    break
                if fut_fav[j] > best_b4sl:
                    best_b4sl = fut_fav[j]
                if fut_fav[j] >= 0.0:
                    hit_b4sl = True
            r[f"recov_b4sl_{K}"]     = (best_b4sl if best_b4sl > -999 else None)
            r[f"hit_entry_b4sl_{K}"] = hit_b4sl

            # Best recovery before the ACTUAL exit (using hold_bars)
            exit_bar = min(int(trade.get("hold_bars", len(fut_fav)) or
                               len(fut_fav)), len(fut_fav) - 1)
            if exit_bar > 0:
                fav_until_exit = fut_fav[:exit_bar + 1]
                r[f"recov_b4exit_{K}"] = (float(np.max(fav_until_exit))
                                           if len(fav_until_exit) else None)
            else:
                r[f"recov_b4exit_{K}"] = None
        return r
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}",
                "symbol": trade.get("symbol", "?")}


# ─────────────────────────────────────────────────────────────
def print_summary(results, K_levels):
    total = len(results)
    print("\n" + "═" * 82)
    print(f"  BEE FAILURE ANALYSIS  —  {total} trades analyzed")
    print("═" * 82)

    # Exit reasons
    reasons = defaultdict(int)
    for r in results:
        reasons[r["exit_reason"]] += 1
    print("\n▶ Exit reasons")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"    {k:35s}  {v:5d}  ({v/total*100:5.1f}%)")

    # CORE TABLE
    print("\n" + "─" * 82)
    print("  After price moves −K×SL, does it come back to entry?")
    print("─" * 82)
    print(f"  {'K':>5} | {'triggered':>10} | {'hit entry %':>13} | "
          f"{'hit entry BEFORE SL %':>23} | {'median best recov R':>20}")
    print("  " + "-" * 78)
    for K in K_levels:
        trig = [r for r in results if r.get(f"trig_{K}", -1) >= 0]
        n = len(trig)
        if n == 0:
            print(f"  {K:>5.1f} | {0:>10} | {'—':>13} | {'—':>23} | {'—':>20}")
            continue
        hit_all  = sum(1 for r in trig if r.get(f"hit_entry_{K}"))
        hit_b4sl = sum(1 for r in trig if r.get(f"hit_entry_b4sl_{K}"))
        recs     = [r[f"recov_{K}"] for r in trig
                    if r.get(f"recov_{K}") is not None]
        med_str  = (f"{float(np.median(recs)):>19.3f}"
                    if recs else f"{'—':>20}")
        print(f"  {K:>5.1f} | {n:>10} | {hit_all/n*100:>12.1f}% | "
              f"{hit_b4sl/n*100:>22.1f}% | {med_str}")

    print("\n  Legend:")
    print("    triggered              = trades that closed below −K×SL")
    print("    hit entry %            = % where price eventually touched entry")
    print("                             (ignores SL — optimistic)")
    print("    hit entry BEFORE SL %  = % where price touched entry BEFORE −1R")
    print("                             (this is what BEEsc actually delivers)")
    print("    median best recov R    = median best favorable excursion")
    print("                             0 = entry, >0 = profit, <0 = still loss")

    # Distribution: where does price recover to?
    print("\n" + "─" * 82)
    print("  Distribution of best recovery BEFORE SL (where price returns to)")
    print("─" * 82)
    for K in K_levels:
        recs = [r[f"recov_b4sl_{K}"] for r in results
                if r.get(f"trig_{K}", -1) >= 0
                and r.get(f"recov_b4sl_{K}") is not None]
        if not recs:
            continue
        arr = np.array(recs)
        n = len(arr)
        buckets = [
            ("≥  0.0R (entry or better)", int(np.sum(arr >= 0.0))),
            ("≥ -0.1R", int(np.sum(arr >= -0.1))),
            ("≥ -0.2R", int(np.sum(arr >= -0.2))),
            ("≥ -0.3R", int(np.sum(arr >= -0.3))),
            ("≥ -0.4R", int(np.sum(arr >= -0.4))),
            ("≥ -0.5R", int(np.sum(arr >= -0.5))),
            ("≥ -0.7R", int(np.sum(arr >= -0.7))),
            ("< -0.7R (deep)", int(np.sum(arr < -0.7))),
        ]
        print(f"\n  K = {K:.2f}   (n = {n} triggered)")
        for label, cnt in buckets:
            print(f"    {label:32s}  {cnt:5d}  ({cnt/n*100:5.1f}%)")

    # SL-only deep dive
    print("\n" + "─" * 82)
    print("  Trades that ACTUALLY ended in Emergency SL")
    print("─" * 82)
    sl_trades = [r for r in results if "SL" in r["exit_reason"]]
    if not sl_trades:
        print("  (none)")
    else:
        print(f"  count: {len(sl_trades)}")
        pk = np.array([r["peak_adverse_R"] for r in sl_trades])
        print(f"  peak adverse R: median={np.median(pk):.2f}  "
              f"mean={np.mean(pk):.2f}  max={np.max(pk):.2f}")
        for K in K_levels:
            tg = [r for r in sl_trades if r.get(f"trig_{K}", -1) >= 0]
            if not tg:
                continue
            hit = sum(1 for r in tg if r.get(f"hit_entry_b4sl_{K}"))
            print(f"    K={K:.2f}: {len(tg):4d} triggered, "
                  f"{hit/len(tg)*100:5.1f}% recovered to entry before SL")

    # Recommendation
    print("\n" + "═" * 82)
    print("  RECOMMENDATION ENGINE")
    print("═" * 82)
    best_k = None
    best_pct = 0.0
    for K in K_levels:
        trig = [r for r in results if r.get(f"trig_{K}", -1) >= 0]
        if len(trig) < 20:
            continue
        hit = sum(1 for r in trig if r.get(f"hit_entry_b4sl_{K}"))
        pct = hit / len(trig) * 100
        if pct > best_pct:
            best_pct, best_k = pct, K
    if best_k is None:
        print("  Not enough data to recommend.")
    elif best_pct < 20:
        print(f"  ⚠ Best K = {best_k:.2f} only reaches entry in {best_pct:.1f}%.")
        print(f"  → BEEsc at ENTRY is nearly useless.")
        print(f"  → Recommended: BREAKEVEN_ESCAPE_MIN_PROFIT_R < 0 (accept")
        print(f"    a small loss exit). Look at the 'Distribution' table")
        print(f"    above and pick a level reached ≥ 40% of the time.")
    elif best_pct < 40:
        print(f"  ⚠ Best K = {best_k:.2f} reaches entry in {best_pct:.1f}%.")
        print(f"  → BEEsc helps marginally. Consider negative MIN_PROFIT_R")
        print(f"    for a higher save rate.")
    else:
        print(f"  ✓ Best K = {best_k:.2f} reaches entry in {best_pct:.1f}%.")
        print(f"  → BEEsc SHOULD work at this K. If it didn't, check:")
        print(f"      • Partial TP interaction (RESPECT_PARTIAL=True blocks)")
        print(f"      • pen_frac (TP needs 1 bps overshoot)")
        print(f"      • EMA-flip trigger may be too strict")


# ─────────────────────────────────────────────────────────────
def write_outputs(results, K_levels, out_trades, out_summary):
    pd.DataFrame(results).to_csv(out_trades, index=False)
    print(f"\n  Wrote: {out_trades}")

    rows = []
    for K in K_levels:
        trig = [r for r in results if r.get(f"trig_{K}", -1) >= 0]
        n = len(trig)
        if n == 0:
            rows.append({"K": K, "triggered": 0,
                         "hit_entry_pct": 0.0,
                         "hit_entry_b4sl_pct": 0.0,
                         "median_recov_R": None,
                         "median_recov_b4sl_R": None})
            continue
        hit_all  = sum(1 for r in trig if r.get(f"hit_entry_{K}"))
        hit_b4sl = sum(1 for r in trig if r.get(f"hit_entry_b4sl_{K}"))
        recs     = [r[f"recov_{K}"] for r in trig
                    if r.get(f"recov_{K}") is not None]
        recs_sl  = [r[f"recov_b4sl_{K}"] for r in trig
                    if r.get(f"recov_b4sl_{K}") is not None]
        rows.append({
            "K": K,
            "triggered": n,
            "hit_entry_pct": hit_all / n * 100,
            "hit_entry_b4sl_pct": hit_b4sl / n * 100,
            "median_recov_R": float(np.median(recs)) if recs else None,
            "median_recov_b4sl_R": float(np.median(recs_sl))
                                   if recs_sl else None,
        })
    pd.DataFrame(rows).to_csv(out_summary, index=False)
    print(f"  Wrote: {out_summary}")


# ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="trades_log_backtest.jsonl")
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--K", default="0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0")
    ap.add_argument("--out", default="bee_analysis_per_trade.csv")
    ap.add_argument("--out-summary", default="bee_analysis_summary.csv")
    args = ap.parse_args()

    if not os.path.exists(args.log):
        print(f"ERROR: log not found: {args.log}")
        sys.exit(1)

    K_levels = [float(x) for x in args.K.split(",") if x.strip()]

    print(f"Reading {args.log}...")
    trades = load_trades(args.log)
    print(f"  {len(trades)} trades")

    if not trades:
        print("No trades.")
        sys.exit(0)

    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t["symbol"]].append(t)

    candles = {}
    for sym in by_sym:
        df = load_candles(sym, args.timeframe)
        if df is not None:
            candles[sym] = df
    print(f"  candles loaded for {len(candles)}/{len(by_sym)} symbols")
    if len(candles) < len(by_sym):
        missing = [s for s in by_sym if s not in candles]
        print(f"  missing candles: {missing[:5]}...")

    results = []
    errors = 0
    for t in trades:
        if t["symbol"] not in candles:
            errors += 1
            continue
        r = analyze_trade(t, candles[t["symbol"]], K_levels)
        if r is None or "error" in r:
            errors += 1
        else:
            results.append(r)
    print(f"  analyzed {len(results)}, skipped {errors}")

    if not results:
        print("No usable results.")
        sys.exit(1)

    print_summary(results, K_levels)
    write_outputs(results, K_levels, args.out, args.out_summary)

    print("\n" + "═" * 82)
    print("  ✓ Done. Copy the terminal output above and paste it in chat.")
    print("═" * 82)


if __name__ == "__main__":
    main()
