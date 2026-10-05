#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_parity.py
=================
يقارن سجلات الصفقات (JSONL) بين Backtest و Testnet/Live ويُنتج
تقريراً مفصلاً بالفروقات الإحصائية.

يقرأ من:
    trades_log_backtest.jsonl
    trades_log_testnet.jsonl   (أو trades_log_live.jsonl)

يُنتج:
    parity_report.md      — تقرير Markdown
    parity_report.png     — رسوم بيانية للمقارنة
    parity_summary.json   — خلاصة قابلة للقراءة آلياً

الاستخدام:
    python compare_parity.py
    python compare_parity.py --bt trades_log_backtest.jsonl \\
                             --live trades_log_testnet.jsonl \\
                             --out-dir ./parity_out
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _MPL_OK = True
except ImportError:
    _MPL_OK = False


# ════════════════════════════════════════════════════════════════
# Load
# ════════════════════════════════════════════════════════════════

def load_jsonl(path):
    """يقرأ ملف JSONL، يفصل الميتا عن الصفقات."""
    meta = None
    trades = []
    if not os.path.exists(path):
        return None, []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("_meta"):
                meta = rec
            else:
                trades.append(rec)
    return meta, trades


# ════════════════════════════════════════════════════════════════
# Metrics
# ════════════════════════════════════════════════════════════════

def compute_metrics(trades):
    """يحسب المقاييس الإحصائية من قائمة الصفقات."""
    m = {"n_trades": 0}
    if not trades:
        return m

    pnls = [float(t.get("net_pnl") or 0.0) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    # Geometric stats
    logs = [float(t.get("log_return") or 0.0) for t in trades]
    logs = [l for l in logs if np.isfinite(l)]

    # Hold times
    holds = [int(t.get("hold_bars") or 0) for t in trades]

    # MFE
    mfes = [float(t.get("mfe_frac") or 0.0) for t in trades]

    # Exit reasons
    exit_dist = Counter()
    for t in trades:
        r = str(t.get("exit_reason") or "unknown")
        # Normalize: strip parenthetical details
        r = r.split("(")[0].strip()
        exit_dist[r] += 1

    # Actions
    actions = Counter(str(t.get("action") or "?") for t in trades)

    # Sharpe (per-trade, then annualized assuming ~365 trades/yr as placeholder)
    if logs:
        mean_l = float(np.mean(logs))
        std_l = float(np.std(logs, ddof=1)) if len(logs) > 1 else 0.0
        sharpe_per_trade = (mean_l / std_l) if std_l > 1e-12 else 0.0
    else:
        mean_l = std_l = sharpe_per_trade = 0.0

    m.update({
        "n_trades": len(trades),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": (len(wins) / len(pnls)) if pnls else 0.0,
        "avg_win": float(np.mean(wins)) if wins else 0.0,
        "avg_loss": float(np.mean(losses)) if losses else 0.0,
        "sum_pnl": float(np.sum(pnls)),
        "mean_pnl": float(np.mean(pnls)) if pnls else 0.0,
        "median_pnl": float(np.median(pnls)) if pnls else 0.0,
        "std_pnl": float(np.std(pnls, ddof=1)) if len(pnls) > 1 else 0.0,
        "profit_factor": (sum(wins) / abs(sum(losses))
                          if losses and sum(losses) != 0 else float("inf")),
        "mean_log_return": mean_l,
        "std_log_return": std_l,
        "sharpe_per_trade": sharpe_per_trade,
        "avg_hold_bars": float(np.mean(holds)) if holds else 0.0,
        "median_hold_bars": float(np.median(holds)) if holds else 0.0,
        "avg_mfe_frac": float(np.mean(mfes)) if mfes else 0.0,
        "exit_distribution": dict(exit_dist),
        "action_distribution": dict(actions),
        "sum_fees": float(np.sum([float(t.get("fee") or 0.0)
                                    for t in trades])),
    })
    return m


# ════════════════════════════════════════════════════════════════
# Parity assessment
# ════════════════════════════════════════════════════════════════

def pct_delta(a, b):
    """Returns |b-a|/max(|a|,eps) * 100."""
    if abs(a) < 1e-12:
        return 0.0 if abs(b) < 1e-12 else float("inf")
    return abs(b - a) / abs(a) * 100.0


def parity_verdict(bt, live):
    """
    تُقيّم مدى التطابق بين Backtest و Live.
    Returns list of (metric, bt_val, live_val, delta_pct, status).
    """
    rows = []
    SPEC = [
        # (name, key, tolerance_pct, min_n_trades_for_check)
        ("Win rate",         "win_rate",        10.0, 20),
        ("Profit factor",    "profit_factor",   15.0, 20),
        ("Mean log return",  "mean_log_return", 20.0, 20),
        ("Sharpe/trade",     "sharpe_per_trade",25.0, 30),
        ("Mean PnL",         "mean_pnl",        20.0, 20),
        ("Avg hold bars",    "avg_hold_bars",   20.0, 20),
        ("Avg MFE",          "avg_mfe_frac",    25.0, 20),
    ]

    for label, key, tol, min_n in SPEC:
        bv = float(bt.get(key, 0.0) or 0.0)
        lv = float(live.get(key, 0.0) or 0.0)
        if (bt.get("n_trades", 0) < min_n
                or live.get("n_trades", 0) < min_n):
            status = "insufficient_data"
        else:
            d = pct_delta(bv, lv)
            if d <= tol:
                status = "ok"
            elif d <= tol * 2:
                status = "warning"
            else:
                status = "fail"
            rows.append((label, bv, lv, d, status))
            continue
        rows.append((label, bv, lv, 0.0, status))

    return rows


# ════════════════════════════════════════════════════════════════
# Report generation
# ════════════════════════════════════════════════════════════════

def write_markdown(report_path, bt_meta, bt_m, lv_meta, lv_m, rows):
    lines = []
    lines.append("# Parity Report: Backtest vs Live/Testnet\n")
    lines.append(f"**Generated:** "
                 f"{datetime.now(timezone.utc).isoformat()}\n")

    lines.append("\n## Configuration\n")
    lines.append("| Field | Backtest | Live/Testnet |")
    lines.append("|---|---|---|")
    for key in ("mode", "timeframe", "started_at", "N", "W", "L",
                "K_MAX", "K_MIN", "INITIAL_CAPITAL", "LEVERAGE_BASE"):
        b = (bt_meta or {}).get(key, "—")
        l = (lv_meta or {}).get(key, "—")
        lines.append(f"| {key} | {b} | {l} |")

    lines.append("\n## Trade Counts\n")
    lines.append(f"- Backtest: **{bt_m.get('n_trades', 0)}** trades")
    lines.append(f"- Live/Testnet: **{lv_m.get('n_trades', 0)}** trades")

    lines.append("\n## Parity Assessment\n")
    lines.append("| Metric | Backtest | Live/Testnet | Δ% | Verdict |")
    lines.append("|---|---|---|---|---|")
    for label, bv, lv, d, status in rows:
        icon = {"ok": "✅", "warning": "⚠️",
                "fail": "❌", "insufficient_data": "⬜"}[status]
        lines.append(f"| {label} | {bv:.6f} | {lv:.6f} | "
                     f"{d:.1f}% | {icon} {status} |")

    lines.append("\n## Exit Distribution\n")
    all_reasons = set()
    all_reasons.update(bt_m.get("exit_distribution", {}).keys())
    all_reasons.update(lv_m.get("exit_distribution", {}).keys())
    lines.append("| Exit Reason | Backtest | Live/Testnet |")
    lines.append("|---|---|---|")
    for r in sorted(all_reasons):
        b = bt_m.get("exit_distribution", {}).get(r, 0)
        l = lv_m.get("exit_distribution", {}).get(r, 0)
        lines.append(f"| {r} | {b} | {l} |")

    lines.append("\n## Action Distribution\n")
    all_act = set()
    all_act.update(bt_m.get("action_distribution", {}).keys())
    all_act.update(lv_m.get("action_distribution", {}).keys())
    lines.append("| Action | Backtest | Live/Testnet |")
    lines.append("|---|---|---|")
    for a in sorted(all_act):
        b = bt_m.get("action_distribution", {}).get(a, 0)
        l = lv_m.get("action_distribution", {}).get(a, 0)
        lines.append(f"| {a} | {b} | {l} |")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_plot(plot_path, bt_m, lv_m):
    if not _MPL_OK:
        return
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    # 1. Core metrics bar
    ax = axes[0, 0]
    labels = ["WR", "PF", "Mean LR×100"]
    bv = [bt_m.get("win_rate", 0) * 100,
          bt_m.get("profit_factor", 0),
          bt_m.get("mean_log_return", 0) * 100]
    lv = [lv_m.get("win_rate", 0) * 100,
          lv_m.get("profit_factor", 0),
          lv_m.get("mean_log_return", 0) * 100]
    x = np.arange(len(labels))
    ax.bar(x - 0.2, bv, 0.4, label="Backtest", color="#3498db")
    ax.bar(x + 0.2, lv, 0.4, label="Live", color="#e74c3c")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title("Core metrics")
    ax.legend()
    ax.grid(alpha=0.3)

    # 2. Exit distribution
    ax = axes[0, 1]
    all_r = sorted(set(list(bt_m.get("exit_distribution", {}).keys())
                        + list(lv_m.get("exit_distribution", {}).keys())))
    bv = [bt_m.get("exit_distribution", {}).get(r, 0) for r in all_r]
    lv = [lv_m.get("exit_distribution", {}).get(r, 0) for r in all_r]
    y = np.arange(len(all_r))
    ax.barh(y - 0.2, bv, 0.4, label="Backtest", color="#3498db")
    ax.barh(y + 0.2, lv, 0.4, label="Live", color="#e74c3c")
    ax.set_yticks(y)
    ax.set_yticklabels([r[:20] for r in all_r], fontsize=8)
    ax.set_title("Exit distribution")
    ax.legend()
    ax.grid(alpha=0.3)

    # 3. Hold bars histogram
    ax = axes[1, 0]
    ax.bar(["Backtest", "Live"],
           [bt_m.get("avg_hold_bars", 0), lv_m.get("avg_hold_bars", 0)],
           color=["#3498db", "#e74c3c"])
    ax.set_title("Avg hold (bars)")
    ax.grid(alpha=0.3)

    # 4. MFE
    ax = axes[1, 1]
    ax.bar(["Backtest", "Live"],
           [bt_m.get("avg_mfe_frac", 0) * 100,
            lv_m.get("avg_mfe_frac", 0) * 100],
           color=["#3498db", "#e74c3c"])
    ax.set_title("Avg MFE (%)")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(plot_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def write_summary(summary_path, bt_m, lv_m, rows):
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backtest": bt_m,
        "live": lv_m,
        "parity": [
            {"metric": r[0], "bt": r[1], "live": r[2],
             "delta_pct": r[3], "status": r[4]}
            for r in rows
        ],
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bt",     default="trades_log_backtest.jsonl")
    ap.add_argument("--live",   default="trades_log_testnet.jsonl")
    ap.add_argument("--out-dir", default="./parity_out")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    bt_meta, bt_trades = load_jsonl(args.bt)
    lv_meta, lv_trades = load_jsonl(args.live)

    if bt_meta is None and not bt_trades:
        print(f"❌ Backtest log not found or empty: {args.bt}")
        sys.exit(1)
    if lv_meta is None and not lv_trades:
        print(f"❌ Live log not found or empty: {args.live}")
        sys.exit(1)

    bt_m = compute_metrics(bt_trades)
    lv_m = compute_metrics(lv_trades)

    print(f"\n{'='*64}")
    print(f"  Backtest  : {bt_m['n_trades']} trades")
    print(f"  Live      : {lv_m['n_trades']} trades")
    print(f"{'='*64}\n")

    rows = parity_verdict(bt_m, lv_m)

    # Console summary
    print(f"{'Metric':<20} {'Backtest':>12} {'Live':>12} "
          f"{'Delta%':>8}  Verdict")
    print("-" * 64)
    for label, bv, lv, d, status in rows:
        icon = {"ok": "✅", "warning": "⚠️",
                "fail": "❌", "insufficient_data": "⬜"}[status]
        print(f"{label:<20} {bv:>12.6f} {lv:>12.6f} "
              f"{d:>7.1f}%  {icon} {status}")

    ok = sum(1 for r in rows if r[4] == "ok")
    warn = sum(1 for r in rows if r[4] == "warning")
    fail = sum(1 for r in rows if r[4] == "fail")
    nodata = sum(1 for r in rows if r[4] == "insufficient_data")
    print(f"\n  Summary: {ok} ✅, {warn} ⚠️, {fail} ❌, "
          f"{nodata} ⬜ (insufficient data)\n")

    # Files
    md_path = os.path.join(args.out_dir, "parity_report.md")
    png_path = os.path.join(args.out_dir, "parity_report.png")
    js_path = os.path.join(args.out_dir, "parity_summary.json")

    write_markdown(md_path, bt_meta, bt_m, lv_meta, lv_m, rows)
    write_plot(png_path, bt_m, lv_m)
    write_summary(js_path, bt_m, lv_m, rows)

    print(f"  📝 {md_path}")
    if _MPL_OK:
        print(f"  📊 {png_path}")
    print(f"  🗄  {js_path}")

    # Exit code: 0 if no fails, 1 if any fail
    if fail > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
