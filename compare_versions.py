#!/usr/bin/env python3
"""
compare_versions.py — Compare all trades_log_*.jsonl files.

Reads the JSONL trade logs produced by trading_2.py, computes identical
metrics for each run, groups by data window, and prints a ranked table.

Usage:
    python3 compare_versions.py                          # scan ./results
    python3 compare_versions.py --root .                 # scan cwd
    python3 compare_versions.py --min-trades 100         # filter small runs
    python3 compare_versions.py --sort sharpe            # sort by metric
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


# ════════════════════════════════════════════════════════════════
# File discovery
# ════════════════════════════════════════════════════════════════

def find_trade_logs(root: str) -> List[Path]:
    """Find all trades_*.jsonl files recursively."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        return []
    files = []
    for p in root_path.rglob("trades_*.jsonl"):
        if p.is_file() and p.stat().st_size > 100:
            files.append(p)
    return sorted(files)


# ════════════════════════════════════════════════════════════════
# Parser
# ════════════════════════════════════════════════════════════════

def parse_trade_log(path: Path) -> Optional[Dict]:
    """Parse a single trades_*.jsonl file into a metrics dict."""
    trades = []
    meta = None
    n_bad = 0

    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    n_bad += 1
                    continue
                if rec.get("_meta"):
                    meta = rec
                    continue
                trades.append(rec)
    except Exception as e:
        return {"_err": str(e), "_path": str(path)}

    if not trades:
        return {
            "_path": str(path),
            "_n_trades": 0,
            "_meta": meta,
            "_err": "empty",
        }

    # ── Extract fields safely ──
    def _num(d, k, default=0.0):
        try:
            v = d.get(k)
            if v is None:
                return default
            return float(v)
        except Exception:
            return default

    net_pnls = []
    log_rets = []
    cap_series = []
    exit_reasons = defaultdict(int)
    actions = defaultdict(int)
    mfe_wins = []
    mfe_losses = []
    times = []
    symbols = set()

    for t in trades:
        pnl = _num(t, "net_pnl", 0.0)
        lr = _num(t, "log_return", 0.0)
        cap = _num(t, "capital_after", 0.0)
        net_pnls.append(pnl)
        log_rets.append(lr)
        if cap > 0:
            cap_series.append(cap)

        er = str(t.get("exit_reason", "?")).split("(")[0].strip()
        exit_reasons[er] += 1
        actions[str(t.get("action", "?"))] += 1

        mfe = _num(t, "mfe_frac", 0.0)
        if pnl > 0:
            mfe_wins.append(mfe)
        else:
            mfe_losses.append(mfe)

        et = t.get("entry_time", "")
        if et:
            times.append(str(et))
        sym = t.get("symbol", "")
        if sym:
            symbols.add(sym)

    n = len(trades)
    pnls_arr = np.array(net_pnls, dtype=np.float64)
    lrs_arr = np.array(log_rets, dtype=np.float64)

    wins = pnls_arr[pnls_arr > 0]
    losses = pnls_arr[pnls_arr <= 0]
    wr = float(len(wins) / n)

    if losses.size > 0 and wins.size > 0:
        pf = float(wins.sum() / abs(losses.sum()))
    elif wins.size > 0:
        pf = float("inf")
    else:
        pf = 0.0

    mean_lr = float(np.mean(lrs_arr))
    median_lr = float(np.median(lrs_arr))
    std_lr = float(np.std(lrs_arr, ddof=1)) if n > 1 else 0.0
    sharpe = float(mean_lr / std_lr * np.sqrt(252)) if std_lr > 1e-12 else 0.0

    # Max drawdown from capital_after series
    if cap_series:
        cap_arr = np.array(cap_series, dtype=np.float64)
        peak = np.maximum.accumulate(cap_arr)
        dd = (peak - cap_arr) / (peak + 1e-12)
        max_dd = float(np.max(dd))
    else:
        max_dd = 0.0

    # Data window (first to last entry)
    window_days = None
    if len(times) >= 2:
        try:
            def _parse_time(s):
                s = str(s).replace("T", " ")[:19]
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(s[:len(fmt)], fmt)
                    except Exception:
                        continue
                return None
            t0 = _parse_time(times[0])
            t1 = _parse_time(times[-1])
            if t0 and t1:
                window_days = (t1 - t0).days
        except Exception:
            pass

    # Exit breakdown
    apex_n = exit_reasons.get("Apex: Action Integral Exhaustion", 0)
    sl_n = exit_reasons.get("Emergency SL", 0)
    tp_n = exit_reasons.get("Hard TP", 0)
    mh_n = exit_reasons.get("MaxHold", 0)

    # Config fingerprint from meta (if present)
    cfg_sig = ""
    if meta:
        parts = []
        for k in ("N", "W", "L", "K_MAX", "K_MIN",
                  "INITIAL_CAPITAL", "LEVERAGE_BASE", "PO_FIXED_PRICE"):
            if k in meta:
                parts.append(f"{k}={meta[k]}")
        cfg_sig = " ".join(parts)

    return {
        "_path": str(path),
        "_name": path.name,
        "_n_trades": n,
        "_n_bad": n_bad,
        "_window_days": window_days,
        "_first_trade": times[0] if times else "",
        "_last_trade": times[-1] if times else "",
        "_n_symbols": len(symbols),
        "_cfg_sig": cfg_sig,

        "mean_log_return": mean_lr,
        "median_log_return": median_lr,
        "std_log_return": std_lr,
        "sharpe": sharpe,
        "win_rate": wr,
        "profit_factor": pf,
        "max_drawdown": max_dd,
        "final_capital": float(cap_series[-1]) if cap_series else 0.0,
        "total_pnl": float(pnls_arr.sum()),

        "avg_win": float(np.mean(wins)) if wins.size > 0 else 0.0,
        "avg_loss": float(np.mean(losses)) if losses.size > 0 else 0.0,

        "buy_n": int(actions.get("BUY", 0)),
        "sell_n": int(actions.get("SELL", 0)),

        "apex_n": int(apex_n),
        "sl_n": int(sl_n),
        "tp_n": int(tp_n),
        "mh_n": int(mh_n),
        "apex_pct": apex_n / n if n > 0 else 0.0,

        "mfe_mean_wins": float(np.mean(mfe_wins)) if mfe_wins else 0.0,
        "mfe_mean_losses": float(np.mean(mfe_losses)) if mfe_losses else 0.0,
    }


# ════════════════════════════════════════════════════════════════
# Reporting
# ════════════════════════════════════════════════════════════════

def _fmt_metric(m: Dict, sort_key: str) -> str:
    """One-line summary for a run."""
    return (
        f"  {m['_name']:48s}  "
        f"n={m['_n_trades']:5d}  "
        f"WR={m['win_rate']*100:5.1f}%  "
        f"PF={m['profit_factor']:5.3f}  "
        f"Sh={m['sharpe']:+5.2f}  "
        f"DD={m['max_drawdown']*100:5.1f}%  "
        f"E[ln]={m['mean_log_return']:+.5f}  "
        f"B/S={m['buy_n']}/{m['sell_n']}"
    )


def _group_by_window(metrics: List[Dict], tol_days: int = 30) -> Dict[int, List[Dict]]:
    """Group runs by approximate data window."""
    groups: Dict[int, List[Dict]] = defaultdict(list)
    for m in metrics:
        wd = m.get("_window_days")
        if wd is None:
            groups[0].append(m)
            continue
        bucket = (wd // tol_days) * tol_days
        groups[bucket].append(m)
    return dict(groups)


def print_report(metrics: List[Dict], sort_key: str, min_trades: int):
    """Print full ranked report."""
    metrics = [m for m in metrics
               if "_err" not in m and m["_n_trades"] >= min_trades]

    if not metrics:
        print("❌ No valid trade logs found.")
        print("   Looking for trades_*.jsonl files under ./results/")
        print("   Ensure at least one backtest has been run.")
        return

    # Group by window
    groups = _group_by_window(metrics)

    for window, group in sorted(groups.items(), key=lambda x: -x[0]):
        if window == 0:
            header = "═══ Unknown window ═══"
        else:
            header = f"═══ Window ≈ {window}–{window+30} days  ({len(group)} runs) ═══"
        print()
        print(header)
        print()

        # Sort by key
        group.sort(key=lambda m: m.get(sort_key, 0.0), reverse=True)

        for m in group:
            print(_fmt_metric(m, sort_key))

        # Also print best by Sharpe, by DD, by E[ln]
        if len(group) > 1:
            best_sh = max(group, key=lambda m: m["sharpe"])
            best_dd = min(group, key=lambda m: m["max_drawdown"])
            best_ln = max(group, key=lambda m: m["mean_log_return"])
            best_pf = max(group, key=lambda m: m["profit_factor"])
            print()
            print(f"  ── Winners in this window ──")
            print(f"  Best Sharpe : {best_sh['_name']}  ({best_sh['sharpe']:+.2f})")
            print(f"  Best DD     : {best_dd['_name']}  ({best_dd['max_drawdown']*100:.1f}%)")
            print(f"  Best E[ln]  : {best_ln['_name']}  ({best_ln['mean_log_return']:+.5f})")
            print(f"  Best PF     : {best_pf['_name']}  ({best_pf['profit_factor']:.3f})")

    # ── Global analysis ──
    print()
    print("═" * 70)
    print("GLOBAL ANALYSIS")
    print("═" * 70)

    # Filter to runs with enough trades
    solid = [m for m in metrics if m["_n_trades"] >= 500]
    if not solid:
        solid = metrics

    # Best overall by Sharpe
    best = max(solid, key=lambda m: m["sharpe"])
    print(f"\n► Best Sharpe (any window):")
    print(f"  {best['_name']}")
    print(f"  Sharpe = {best['sharpe']:+.2f}  |  DD = {best['max_drawdown']*100:.1f}%  "
          f"|  E[ln] = {best['mean_log_return']:+.5f}  |  WR = {best['win_rate']*100:.1f}%")

    # Best DD
    best_dd = min(solid, key=lambda m: m["max_drawdown"])
    print(f"\n► Lowest MaxDD:")
    print(f"  {best_dd['_name']}")
    print(f"  DD = {best_dd['max_drawdown']*100:.1f}%  |  Sharpe = {best_dd['sharpe']:+.2f}")

    # Best E[ln]
    best_ln = max(solid, key=lambda m: m["mean_log_return"])
    print(f"\n► Best E[ln(1+fR)]:")
    print(f"  {best_ln['_name']}")
    print(f"  E[ln] = {best_ln['mean_log_return']:+.5f}  |  Sharpe = {best_ln['sharpe']:+.2f}")

    # Best Sharpe-to-DD ratio
    def _sh_over_dd(m):
        if m["max_drawdown"] < 1e-6:
            return 1e6
        return m["sharpe"] / m["max_drawdown"]
    best_ratio = max(solid, key=_sh_over_dd)
    print(f"\n► Best Sharpe/DD ratio (Sharpe per unit risk):")
    print(f"  {best_ratio['_name']}")
    print(f"  Sharpe/DD = {_sh_over_dd(best_ratio):.2f}  "
          f"(Sharpe={best_ratio['sharpe']:+.2f}, DD={best_ratio['max_drawdown']*100:.1f}%)")

    # Statistical significance warning
    print()
    print("─" * 70)
    print("STATISTICAL NOTE")
    print("─" * 70)
    print("  Sharpe SE ≈ 1/√n. For 1,500 trades: SE ≈ ±0.026 per-trade,")
    print("  but with autocorrelation and fat tails, ±0.3 is realistic.")
    print("  Differences smaller than 0.3 between runs are within noise.")
    print()


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Compare trades_log_*.jsonl outputs")
    ap.add_argument("--root", default="results",
                    help="Root directory to scan (default: results)")
    ap.add_argument("--min-trades", type=int, default=100,
                    help="Minimum trades to include in report (default: 100)")
    ap.add_argument("--sort", default="sharpe",
                    choices=["sharpe", "mean_log_return", "profit_factor",
                             "win_rate", "max_drawdown"],
                    help="Sort key within each window group (default: sharpe)")
    args = ap.parse_args()

    files = find_trade_logs(args.root)
    if not files:
        print(f"❌ No trades_*.jsonl files found under {args.root}/")
        print()
        print("  Expected layout:")
        print("    results/trades_*.jsonl")
        print("    results/walkforward/trades_*.jsonl")
        print()
        print("  Run at least one backtest first, e.g.:")
        print("    python3 trading_2.py --mode backtest --capital 100 \\")
        print("        --nassets 100 --timeframe 4h --no-fixed-price \\")
        print("        --no-trailing --history-days 730 --no-cache \\")
        print("        --trade-log results/trades_myversion.jsonl")
        sys.exit(1)

    print(f"Found {len(files)} trade log(s). Parsing...")
    metrics = []
    for p in files:
        m = parse_trade_log(p)
        if "_err" in m:
            print(f"  ⚠ {p.name}: {m['_err']}")
            continue
        metrics.append(m)

    print()
    print("═" * 70)
    print(f"REPORT  ({len(metrics)} valid runs)")
    print("═" * 70)

    print_report(metrics, args.sort, args.min_trades)


if __name__ == "__main__":
    main()
