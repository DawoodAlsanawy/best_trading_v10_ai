#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_backtest.py
===================
Comprehensive analyzer for backtest trade logs.

Reads a trades_log_*.jsonl file (default: trades_log_backtest.jsonl)
and produces a full HTML analysis suite using Plotly:

    <out_dir>/
        index.html              Master page: summary + charts + table
        trades/
            trade_0001_BTC_USDT.html    Per-trade interactive chart
            trade_0002_ETH_USDT.html
            ...
        summary.json            Machine-readable stats
        metrics.csv             Flat CSV (one row per trade)
        equity_curve.html       Standalone equity curve page
        distributions.html      Standalone distributions page

Usage:
    python analyze_backtest.py
    python analyze_backtest.py --input trades_log_backtest.jsonl
    python analyze_backtest.py --input my_log.jsonl --out-dir ./report
    python analyze_backtest.py --no-trades-html    # skip per-trade pages
"""

import argparse
import json
import math
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
except ImportError:
    print("ERROR: plotly is required.")
    print("Install with: pip install plotly")
    sys.exit(1)


# ════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════

DEFAULT_CACHE_DIR = "market_data_cache"
DEFAULT_INPUT = "trades_log_backtest.jsonl"
DEFAULT_OUT = "results/analysis_out"

# Theme colors
C_BG = "#0d1117"
C_PANEL = "#161b22"
C_TEXT = "#e6edf3"
C_DIM = "#8b949e"
C_ACCENT = "#00e5ff"
C_GREEN = "#3fb950"
C_RED = "#f85149"
C_ORANGE = "#d29922"
C_PURPLE = "#a371f7"
C_BLUE = "#58a6ff"


# ════════════════════════════════════════════════════════════════
# Utilities
# ════════════════════════════════════════════════════════════════

def _safe_float(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _fmt(v, decimals: int = 4) -> str:
    """Format number with commas; handles inf/nan."""
    try:
        f = float(v)
        if math.isnan(f):
            return "—"
        if math.isinf(f):
            return "∞" if f > 0 else "-∞"
        return f"{f:,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pct(v, decimals: int = 2) -> str:
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return "—"
        return f"{f:,.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _esc(s) -> str:
    """HTML-escape."""
    return (str(s).replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;")
                   .replace('"', "&quot;")
                   .replace("'", "&#39;"))


def _safe_filename(s: str) -> str:
    """Make a string filesystem-safe."""
    out = []
    for ch in str(s):
        if ch.isalnum() or ch in "-_. ":
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip().replace(" ", "_")


# ════════════════════════════════════════════════════════════════
# Loading
# ════════════════════════════════════════════════════════════════

def load_jsonl(path: str) -> Tuple[Optional[Dict], List[Dict]]:
    """Read JSONL, separating meta record from trade records."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")
    meta = None
    trades: List[Dict] = []
    n_bad = 0
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                n_bad += 1
                continue
            if rec.get("_meta"):
                meta = rec
            else:
                # Add an internal sequence id
                rec["_seq"] = len(trades)
                trades.append(rec)
    if n_bad > 0:
        print(f"  ⚠️  skipped {n_bad} malformed line(s)")
    return meta, trades


def load_ohlcv(symbol: str, timeframe: str,
                cache_dir: str = DEFAULT_CACHE_DIR
                ) -> Optional[pd.DataFrame]:
    """Load OHLCV from parquet cache. Returns None if not found."""
    safe = symbol.replace("/", "_")
    fp = os.path.join(cache_dir, f"{safe}_{timeframe}.parquet")
    if not os.path.exists(fp):
        return None
    try:
        df = pd.read_parquet(fp)
        if df.index.tz is None:
            df.index = pd.to_datetime(df.index, utc=True)
        else:
            df.index = df.index.tz_convert("UTC")
        for col in ("Open", "High", "Low", "Close", "Volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        return df
    except Exception as e:
        print(f"  ⚠️  failed to read {fp}: {e}")
        return None


# ════════════════════════════════════════════════════════════════
# Summary statistics
# ════════════════════════════════════════════════════════════════

def compute_summary(trades: List[Dict]) -> Dict:
    """Compute comprehensive summary statistics."""
    n = len(trades)
    if n == 0:
        return {"n_trades": 0}

    pnls      = np.array([_safe_float(t.get("net_pnl")) for t in trades])
    log_rets  = np.array([_safe_float(t.get("log_return")) for t in trades])
    holds     = np.array([_safe_int(t.get("hold_bars")) for t in trades])
    mfes      = np.array([_safe_float(t.get("mfe_frac")) for t in trades])
    scores    = np.array([_safe_float(t.get("score")) for t in trades])
    t_infos   = np.array([_safe_float(t.get("T_info") or t.get("T_info_val"))
                          for t in trades])
    risks     = np.array([_safe_float(t.get("dynamic_risk")) for t in trades])

    wins   = pnls[pnls > 0]
    losses = pnls[pnls <= 0]

    # Consecutive
    max_cw = max_cl = 0
    cw = cl = 0
    for p in pnls:
        if p > 0:
            cw += 1; cl = 0
            max_cw = max(max_cw, cw)
        else:
            cl += 1; cw = 0
            max_cl = max(max_cl, cl)

    # Sharpe / Sortino (per-trade)
    mu_lr = float(np.mean(log_rets)) if len(log_rets) > 0 else 0.0
    sd_lr = float(np.std(log_rets, ddof=1)) if len(log_rets) > 1 else 0.0
    sharpe = (mu_lr / sd_lr) if sd_lr > 1e-12 else 0.0

    downside = log_rets[log_rets < 0]
    sd_down = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
    sortino = (mu_lr / sd_down) if sd_down > 1e-12 else 0.0

    # Equity curve + drawdown
    initial = _safe_float(trades[0].get("capital_before"))
    if initial <= 0:
        initial = 100.0
    cap_after = [_safe_float(t.get("capital_after"), initial) for t in trades]
    peak = initial
    max_dd_pct = 0.0
    max_dd_abs = 0.0
    for c in cap_after:
        if c > peak:
            peak = c
        dd = peak - c
        if peak > 0:
            dd_pct = dd / peak * 100.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
                max_dd_abs = dd

    # Time analysis (parse entry_time)
    entry_hours = Counter()
    entry_dows = Counter()
    for t in trades:
        ts = t.get("entry_time")
        try:
            dt = pd.Timestamp(ts)
            entry_hours[dt.hour] += 1
            entry_dows[dt.day_name()] += 1
        except Exception:
            pass

    # By symbol
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t.get("symbol", "?")].append(t)
    sym_stats = {}
    for sym, lst in by_sym.items():
        sp = np.array([_safe_float(x.get("net_pnl")) for x in lst])
        sw = sp[sp > 0]; sl_ = sp[sp <= 0]
        sym_stats[sym] = {
            "n": len(lst),
            "wins": int(len(sw)),
            "losses": int(len(sl_)),
            "win_rate": float(len(sw) / len(lst)),
            "sum_pnl": float(sp.sum()),
            "mean_pnl": float(sp.mean()),
            "profit_factor": float(sw.sum() / abs(sl_.sum()))
                if len(sl_) > 0 and sl_.sum() != 0 else float("inf"),
            "avg_hold_bars": float(np.mean(
                [_safe_int(x.get("hold_bars")) for x in lst])),
        }

    # By action
    by_act = defaultdict(list)
    for t in trades:
        by_act[t.get("action", "?")].append(t)
    act_stats = {}
    for act, lst in by_act.items():
        sp = np.array([_safe_float(x.get("net_pnl")) for x in lst])
        sw = sp[sp > 0]; sl_ = sp[sp <= 0]
        act_stats[act] = {
            "n": len(lst),
            "wins": int(len(sw)),
            "losses": int(len(sl_)),
            "win_rate": float(len(sw) / len(lst)),
            "sum_pnl": float(sp.sum()),
            "mean_pnl": float(sp.mean()),
            "profit_factor": float(sw.sum() / abs(sl_.sum()))
                if len(sl_) > 0 and sl_.sum() != 0 else float("inf"),
        }

    # By exit reason
    by_exit = defaultdict(list)
    for t in trades:
        r = str(t.get("exit_reason") or "unknown")
        # Normalize: strip parenthetical suffix
        if "(" in r:
            r = r.split("(")[0].strip()
        by_exit[r].append(t)
    exit_stats = {}
    for r, lst in by_exit.items():
        sp = np.array([_safe_float(x.get("net_pnl")) for x in lst])
        sw = sp[sp > 0]; sl_ = sp[sp <= 0]
        exit_stats[r] = {
            "n": len(lst),
            "wins": int(len(sw)),
            "losses": int(len(sl_)),
            "win_rate": float(len(sw) / len(lst)),
            "sum_pnl": float(sp.sum()),
            "mean_pnl": float(sp.mean()),
            "avg_hold_bars": float(np.mean(
                [_safe_int(x.get("hold_bars")) for x in lst])),
        }

    # By score bucket
    by_score = defaultdict(list)
    for t in trades:
        s = int(round(_safe_float(t.get("score"))))
        by_score[s].append(t)
    score_stats = {}
    for s, lst in sorted(by_score.items()):
        sp = np.array([_safe_float(x.get("net_pnl")) for x in lst])
        sw = sp[sp > 0]
        score_stats[s] = {
            "n": len(lst),
            "win_rate": float(len(sw) / len(lst)),
            "mean_pnl": float(sp.mean()),
            "sum_pnl": float(sp.sum()),
        }

    # By T_info bucket
    by_ti = defaultdict(list)
    for t in trades:
        ti = _safe_float(t.get("T_info") or t.get("T_info_val"))
        # Bucket to nearest 0.25
        b = round(ti * 4) / 4.0
        by_ti[b].append(t)
    ti_stats = {}
    for b, lst in sorted(by_ti.items()):
        sp = np.array([_safe_float(x.get("net_pnl")) for x in lst])
        sw = sp[sp > 0]
        ti_stats[b] = {
            "n": len(lst),
            "win_rate": float(len(sw) / len(lst)),
            "mean_pnl": float(sp.mean()),
        }

    return {
        "n_trades": n,
        "n_wins": int(len(wins)),
        "n_losses": int(len(losses)),
        "win_rate": float(len(wins) / n),
        "profit_factor": float(wins.sum() / abs(losses.sum()))
            if len(losses) > 0 and losses.sum() != 0 else float("inf"),
        "sum_pnl": float(pnls.sum()),
        "mean_pnl": float(pnls.mean()),
        "median_pnl": float(np.median(pnls)),
        "std_pnl": float(pnls.std(ddof=1)) if len(pnls) > 1 else 0.0,
        "max_win": float(pnls.max()),
        "max_loss": float(pnls.min()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "expectancy": float(pnls.mean()),
        "sharpe_per_trade": sharpe,
        "sortino_per_trade": sortino,
        "mean_log_return": mu_lr,
        "std_log_return": sd_lr,
        "median_log_return": float(np.median(log_rets)),
        "avg_hold_bars": float(holds.mean()),
        "median_hold_bars": float(np.median(holds)),
        "min_hold_bars": int(holds.min()),
        "max_hold_bars": int(holds.max()),
        "avg_mfe_frac": float(mfes.mean()),
        "max_mfe_frac": float(mfes.max()),
        "avg_score": float(scores.mean()),
        "min_score": float(scores.min()),
        "max_score": float(scores.max()),
        "avg_T_info": float(t_infos.mean()) if len(t_infos) else 0.0,
        "avg_dynamic_risk": float(risks.mean()) if len(risks) else 0.0,
        "max_consecutive_wins": max_cw,
        "max_consecutive_losses": max_cl,
        "initial_capital": float(initial),
        "final_capital": float(cap_after[-1]),
        "total_return_pct": ((cap_after[-1] - initial) / initial * 100.0)
            if initial > 0 else 0.0,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_abs": max_dd_abs,
        "by_symbol": sym_stats,
        "by_action": act_stats,
        "by_exit_reason": exit_stats,
        "by_score": score_stats,
        "by_t_info": ti_stats,
        "entry_hours": dict(entry_hours),
        "entry_dows": dict(entry_dows),
        "_equity_curve": {
            "n": len(cap_after),
            "initial": initial,
            "values": [float(x) for x in cap_after],
        },
    }


# ════════════════════════════════════════════════════════════════
# Plotly chart builders
# ════════════════════════════════════════════════════════════════

_DARK_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor=C_BG,
    plot_bgcolor=C_PANEL,
    font=dict(color=C_TEXT, family="Inter, system-ui, sans-serif"),
    margin=dict(l=60, r=30, t=60, b=50),
)


def make_equity_curve(summary: Dict) -> go.Figure:
    eq = summary.get("_equity_curve", {})
    vals = eq.get("values", [])
    init = eq.get("initial", 100.0)
    if not vals:
        fig = go.Figure()
        fig.add_annotation(text="No equity data", showarrow=False,
                            xref="paper", yref="paper", x=0.5, y=0.5)
        fig.update_layout(**_DARK_LAYOUT, height=420)
        return fig

    x = list(range(1, len(vals) + 1))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=vals, mode="lines",
        line=dict(color=C_ACCENT, width=2),
        fill="tozeroy",
        fillcolor="rgba(0,229,255,0.08)",
        name="Capital",
        hovertemplate="Trade #%{x}<br>Capital: $%{y:.2f}<extra></extra>",
    ))
    fig.add_hline(y=init, line=dict(color=C_DIM, dash="dash", width=1),
                  annotation_text=f"Initial ${init:.2f}",
                  annotation_position="bottom right")
    peak = np.maximum.accumulate(vals)
    fig.add_trace(go.Scatter(
        x=x, y=peak, mode="lines",
        line=dict(color="rgba(139,148,158,0.4)", width=1, dash="dot"),
        name="Peak", hoverinfo="skip",
    ))
    fig.update_layout(
        **_DARK_LAYOUT, height=420,
        title=f"Equity Curve — {len(vals)} trades",
        xaxis_title="Trade #",
        yaxis_title="Capital ($)",
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", y=1.02, x=0),
    )
    return fig


def make_distributions(trades: List[Dict]) -> go.Figure:
    pnls = [_safe_float(t.get("net_pnl")) for t in trades]
    logs = [_safe_float(t.get("log_return")) for t in trades]
    holds = [_safe_int(t.get("hold_bars")) for t in trades]
    mfes = [_safe_float(t.get("mfe_frac")) * 100 for t in trades]
    scores = [_safe_float(t.get("score")) for t in trades]

    fig = make_subplots(
        rows=2, cols=3,
        subplot_titles=(
            "Net PnL ($)", "Log Return", "Hold Bars",
            "MFE %", "Score", "Dynamic Risk %",
        ),
        vertical_spacing=0.14,
        horizontal_spacing=0.08,
    )
    # 1
    fig.add_trace(go.Histogram(
        x=pnls, nbinsx=50, marker_color=C_ACCENT, opacity=0.75,
        name="PnL", showlegend=False,
    ), row=1, col=1)
    fig.add_vline(x=0, line=dict(color=C_RED, width=1.5), row=1, col=1)
    # 2
    fig.add_trace(go.Histogram(
        x=logs, nbinsx=50, marker_color=C_GREEN, opacity=0.75,
        showlegend=False,
    ), row=1, col=2)
    fig.add_vline(x=0, line=dict(color=C_RED, width=1.5), row=1, col=2)
    # 3
    fig.add_trace(go.Histogram(
        x=holds, nbinsx=50, marker_color=C_PURPLE, opacity=0.75,
        showlegend=False,
    ), row=1, col=3)
    # 4
    fig.add_trace(go.Histogram(
        x=mfes, nbinsx=50, marker_color=C_ORANGE, opacity=0.75,
        showlegend=False,
    ), row=2, col=1)
    # 5
    fig.add_trace(go.Histogram(
        x=scores, nbinsx=30, marker_color=C_BLUE, opacity=0.75,
        showlegend=False,
    ), row=2, col=2)
    # 6
    risks = [_safe_float(t.get("dynamic_risk")) * 100 for t in trades]
    fig.add_trace(go.Histogram(
        x=risks, nbinsx=30, marker_color=C_GREEN, opacity=0.75,
        showlegend=False,
    ), row=2, col=3)

    fig.update_layout(**_DARK_LAYOUT, height=620,
                      title="Distributions")
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    return fig


def make_symbol_bars(summary: Dict) -> go.Figure:
    sym = summary.get("by_symbol", {})
    if not sym:
        fig = go.Figure()
        fig.update_layout(**_DARK_LAYOUT, height=400,
                          title="By Symbol")
        return fig
    items = sorted(sym.items(), key=lambda x: -x[1]["sum_pnl"])
    names = [s for s, _ in items]
    sum_pnl = [d["sum_pnl"] for _, d in items]
    win_rate = [d["win_rate"] * 100 for _, d in items]
    counts = [d["n"] for _, d in items]
    colors = [C_GREEN if v >= 0 else C_RED for v in sum_pnl]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=names, y=sum_pnl, marker_color=colors,
        name="Sum PnL ($)",
        hovertemplate="<b>%{x}</b><br>Sum PnL: $%{y:.2f}<extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=names, y=win_rate, mode="markers+lines",
        line=dict(color=C_ACCENT, width=1.5, dash="dot"),
        marker=dict(color=C_ACCENT, size=8),
        name="Win Rate (%)",
        hovertemplate="<b>%{x}</b><br>WR: %{y:.1f}%<extra></extra>",
    ), secondary_y=True)
    fig.update_yaxes(title_text="Sum PnL ($)", secondary_y=False)
    fig.update_yaxes(title_text="Win Rate (%)", secondary_y=True,
                     range=[0, 100])
    fig.update_layout(**_DARK_LAYOUT, height=440,
                      title="Performance by Symbol",
                      hovermode="x unified",
                      xaxis_tickangle=-45)
    return fig


def make_exit_reason_pie(summary: Dict) -> go.Figure:
    exits = summary.get("by_exit_reason", {})
    if not exits:
        fig = go.Figure()
        fig.update_layout(**_DARK_LAYOUT, height=440,
                          title="Exit Reasons")
        return fig
    labels = list(exits.keys())
    values = [exits[k]["n"] for k in labels]
    # Sort desc
    order = sorted(range(len(values)), key=lambda i: -values[i])
    labels = [labels[i] for i in order]
    values = [values[i] for i in order]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.45,
        textinfo="label+percent",
        textfont=dict(size=11),
        marker=dict(line=dict(color=C_BG, width=2)),
    ))
    fig.update_layout(**_DARK_LAYOUT, height=440,
                      title="Exit Reason Distribution",
                      showlegend=True)
    return fig


def make_action_breakdown(summary: Dict) -> go.Figure:
    act = summary.get("by_action", {})
    if not act:
        fig = go.Figure()
        fig.update_layout(**_DARK_LAYOUT, height=380)
        return fig
    names = list(act.keys())
    metric_groups = [
        ("Trades", [act[k]["n"] for k in names]),
        ("Win Rate %", [act[k]["win_rate"] * 100 for k in names]),
        ("Mean PnL $", [act[k]["mean_pnl"] for k in names]),
    ]
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=[m[0] for m in metric_groups],
    )
    colors = [C_GREEN if k == "BUY" else C_RED for k in names]
    for i, (_, vals) in enumerate(metric_groups, start=1):
        fig.add_trace(go.Bar(
            x=names, y=vals, marker_color=colors,
            showlegend=False,
            text=[_fmt(v, 2) for v in vals],
            textposition="auto",
            textfont=dict(size=10),
        ), row=1, col=i)
    fig.update_layout(**_DARK_LAYOUT, height=380,
                      title="BUY vs SELL Breakdown")
    return fig


def make_hour_heatmap(summary: Dict) -> go.Figure:
    hours = summary.get("entry_hours", {})
    if not hours:
        fig = go.Figure()
        fig.update_layout(**_DARK_LAYOUT, height=300,
                          title="Entry Hour (UTC)")
        return fig
    h = list(range(24))
    v = [hours.get(i, 0) for i in h]
    fig = go.Figure(go.Bar(
        x=h, y=v, marker_color=C_ORANGE, opacity=0.8,
        hovertemplate="Hour %{x}:00 UTC<br>Trades: %{y}<extra></extra>",
    ))
    fig.update_layout(**_DARK_LAYOUT, height=300,
                      title="Trade Entry Hours (UTC)",
                      xaxis=dict(dtick=1, title="Hour"),
                      yaxis_title="Trades")
    return fig


# ════════════════════════════════════════════════════════════════
# Per-trade chart
# ════════════════════════════════════════════════════════════════

def make_trade_chart(trade: Dict, ohlcv: pd.DataFrame) -> go.Figure:
    entry_ci = _safe_int(trade.get("entry_ci"))
    exit_ci = _safe_int(trade.get("exit_ci"))
    if exit_ci <= entry_ci:
        exit_ci = entry_ci + 1

    n = len(ohlcv)
    lo = max(0, entry_ci - 30)
    hi = min(n - 1, exit_ci + 30)
    df = ohlcv.iloc[lo:hi + 1].copy()

    if len(df) < 2:
        fig = go.Figure()
        fig.add_annotation(text="Insufficient OHLCV data",
                           showarrow=False,
                           xref="paper", yref="paper", x=0.5, y=0.5)
        fig.update_layout(**_DARK_LAYOUT, height=560)
        return fig

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.74, 0.26],
        vertical_spacing=0.06,
        shared_xaxes=True,
    )

    # Candlesticks
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        name="Price",
        increasing_line_color=C_GREEN,
        decreasing_line_color=C_RED,
        increasing_fillcolor=C_GREEN,
        decreasing_fillcolor=C_RED,
        showlegend=False,
    ), row=1, col=1)

    # Entry marker
    if 0 <= (entry_ci - lo) < len(df):
        entry_t = df.index[entry_ci - lo]
        entry_px = _safe_float(trade.get("entry_price"))
        action = trade.get("action", "BUY")
        entry_color = C_GREEN if action == "BUY" else C_RED
        entry_sym = "triangle-up" if action == "BUY" else "triangle-down"
        fig.add_trace(go.Scatter(
            x=[entry_t], y=[entry_px],
            mode="markers",
            marker=dict(symbol=entry_sym, size=20,
                        color=entry_color,
                        line=dict(color="white", width=2)),
            name=f"Entry ({action})",
            hovertemplate=(f"<b>ENTRY {action}</b><br>"
                           f"Time: %{{x|%Y-%m-%d %H:%M}}<br>"
                           f"Price: {entry_px:.6f}<extra></extra>"),
        ), row=1, col=1)

    # Exit marker
    if 0 <= (exit_ci - lo) < len(df):
        exit_t = df.index[exit_ci - lo]
        exit_px = _safe_float(trade.get("exit_price"))
        net = _safe_float(trade.get("net_pnl"))
        exit_color = C_GREEN if net > 0 else C_RED
        exit_reason = trade.get("exit_reason", "?")
        fig.add_trace(go.Scatter(
            x=[exit_t], y=[exit_px],
            mode="markers",
            marker=dict(symbol="x", size=18,
                        color=exit_color,
                        line=dict(color="white", width=2)),
            name=f"Exit ({exit_reason[:20]})",
            hovertemplate=(f"<b>EXIT</b> {exit_reason}<br>"
                           f"Time: %{{x|%Y-%m-%d %H:%M}}<br>"
                           f"Price: {exit_px:.6f}<br>"
                           f"PnL: ${net:+.4f}<extra></extra>"),
        ), row=1, col=1)

    # Trade period shading
    try:
        t_entry = df.index[entry_ci - lo]
        t_exit = df.index[exit_ci - lo]
        fig.add_vrect(
            x0=t_entry, x1=t_exit,
            fillcolor="rgba(255,235,59,0.08)",
            line_width=0, row=1, col=1,
            annotation_text="HOLD",
            annotation_position="top left",
            annotation_font=dict(size=10, color=C_ORANGE),
        )
    except Exception:
        pass

    # Entry line
    entry_px = _safe_float(trade.get("entry_price"))
    if entry_px > 0:
        fig.add_hline(
            y=entry_px, line=dict(color=C_ACCENT, width=1, dash="dot"),
            row=1, col=1,
            annotation_text=f"Entry {entry_px:.6f}",
            annotation_position="right",
            annotation_font=dict(size=10, color=C_ACCENT),
        )

    # SL line
    sl_dist = _safe_float(trade.get("sl_dist_initial"))
    action = trade.get("action", "BUY")
    if sl_dist > 0 and entry_px > 0:
        sl_px = entry_px - sl_dist if action == "BUY" else entry_px + sl_dist
        fig.add_hline(
            y=sl_px, line=dict(color=C_RED, width=1.5, dash="dash"),
            row=1, col=1,
            annotation_text=f"SL {sl_px:.6f}",
            annotation_position="right",
            annotation_font=dict(size=10, color=C_RED),
        )

    # TP line
    rr = _safe_float(trade.get("rr_design"), 2.0)
    if rr <= 0:
        rr = 2.0
    if sl_dist > 0 and entry_px > 0:
        tp_px = (entry_px + sl_dist * rr) if action == "BUY" \
                else (entry_px - sl_dist * rr)
        fig.add_hline(
            y=tp_px, line=dict(color=C_GREEN, width=1.5, dash="dash"),
            row=1, col=1,
            annotation_text=f"TP {tp_px:.6f} (R:R={rr:.2f})",
            annotation_position="right",
            annotation_font=dict(size=10, color=C_GREEN),
        )

    # Volume subplot
    colors = [C_GREEN if df["Close"].iloc[i] >= df["Open"].iloc[i]
              else C_RED for i in range(len(df))]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"], marker_color=colors,
        name="Volume", showlegend=False,
        hovertemplate="Vol: %{y:,.0f}<extra></extra>",
    ), row=2, col=1)

    sym = trade.get("symbol", "?")
    fig.update_layout(
        **_DARK_LAYOUT, height=640,
        title=(f"{sym}  —  {action}  "
               f"(PnL: ${_safe_float(trade.get('net_pnl')):+.4f})"),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    return fig


# ════════════════════════════════════════════════════════════════
# HTML builders
# ════════════════════════════════════════════════════════════════

CSS = """
:root {
  --bg: #0d1117;
  --panel: #161b22;
  --border: #30363d;
  --text: #e6edf3;
  --dim: #8b949e;
  --accent: #00e5ff;
  --green: #3fb950;
  --red: #f85149;
  --orange: #d29922;
  --purple: #a371f7;
  --blue: #58a6ff;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  background: var(--bg); color: var(--text);
  font-family: Inter, -apple-system, system-ui, sans-serif;
  font-size: 14px; line-height: 1.5;
}
.container { max-width: 1600px; margin: 0 auto; padding: 20px; }
h1 { font-size: 26px; margin: 0 0 8px 0; }
h2 { font-size: 18px; margin: 28px 0 12px 0;
     border-bottom: 1px solid var(--border); padding-bottom: 8px; }
h3 { font-size: 15px; margin: 20px 0 10px 0; color: var(--dim); }
.subtitle { color: var(--dim); font-size: 13px; margin-bottom: 24px; }
.meta-line { color: var(--dim); font-size: 12px; margin: 4px 0; }
.meta-line b { color: var(--text); font-weight: 500; }

.grid { display: grid; gap: 14px; }
.grid.metrics { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.metric {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 14px 16px;
}
.metric .label { color: var(--dim); font-size: 11px;
                 text-transform: uppercase; letter-spacing: 0.5px; }
.metric .value { font-size: 22px; font-weight: 600; margin-top: 4px;
                 font-variant-numeric: tabular-nums; }
.metric .value.pos { color: var(--green); }
.metric .value.neg { color: var(--red); }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
table th { background: var(--panel); color: var(--dim);
           text-align: left; padding: 8px 10px;
           border-bottom: 1px solid var(--border);
           font-weight: 500; font-size: 11px; text-transform: uppercase;
           letter-spacing: 0.3px; cursor: pointer;
           user-select: none; position: sticky; top: 0; z-index: 2; }
table th:hover { color: var(--accent); }
table td { padding: 7px 10px; border-bottom: 1px solid var(--border);
           font-variant-numeric: tabular-nums; }
table tr:hover { background: rgba(0,229,255,0.04); }
table .pos { color: var(--green); }
table .neg { color: var(--red); }
table .sym { color: var(--accent); font-weight: 500; }
table .link { color: var(--blue); text-decoration: none; }
table .link:hover { text-decoration: underline; }

.chart-wrap { background: var(--panel); border: 1px solid var(--border);
              border-radius: 8px; margin-bottom: 18px; overflow: hidden; }

.kv { display: grid; grid-template-columns: 200px 1fr;
      gap: 4px 12px; font-size: 13px; }
.kv .k { color: var(--dim); }
.kv .v { font-variant-numeric: tabular-nums; }
.kv .v.pos { color: var(--green); }
.kv .v.neg { color: var(--red); }

.tabs { display: flex; gap: 6px; margin: 20px 0 12px 0;
        border-bottom: 1px solid var(--border); }
.tab { padding: 8px 14px; background: transparent; color: var(--dim);
       border: none; cursor: pointer; font-size: 13px;
       border-bottom: 2px solid transparent; }
.tab:hover { color: var(--text); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-content { display: none; }
.tab-content.active { display: block; }

input.filter { background: var(--panel); border: 1px solid var(--border);
               color: var(--text); border-radius: 6px;
               padding: 8px 12px; width: 260px; margin-bottom: 10px; }

.navbar { display: flex; justify-content: space-between;
          align-items: center; margin-bottom: 20px; }
.navbar a { color: var(--accent); text-decoration: none; font-size: 13px; }
.navbar a:hover { text-decoration: underline; }

.footer { color: var(--dim); font-size: 11px;
          text-align: center; margin-top: 40px; padding: 20px;
          border-top: 1px solid var(--border); }
"""


def _metric_card(label: str, value: str, cls: str = "") -> str:
    return f'''<div class="metric">
      <div class="label">{_esc(label)}</div>
      <div class="value {cls}">{value}</div>
    </div>'''


def build_metrics_grid(summary: Dict) -> str:
    s = summary
    cards = []

    # PnL-related
    pnl_val = _fmt(s.get("sum_pnl", 0), 2)
    pnl_cls = "pos" if s.get("sum_pnl", 0) > 0 else (
        "neg" if s.get("sum_pnl", 0) < 0 else "")
    cards.append(_metric_card("Total PnL ($)", f"${pnl_val}", pnl_cls))

    wr = s.get("win_rate", 0) * 100
    wr_cls = "pos" if wr >= 50 else "neg"
    cards.append(_metric_card("Win Rate", _fmt_pct(wr), wr_cls))

    pf = s.get("profit_factor", 0)
    pf_cls = "pos" if pf >= 1.0 else "neg"
    cards.append(_metric_card("Profit Factor", _fmt(pf, 3), pf_cls))

    sharpe = s.get("sharpe_per_trade", 0)
    sh_cls = "pos" if sharpe > 0 else "neg"
    cards.append(_metric_card("Sharpe / Trade", _fmt(sharpe, 3), sh_cls))

    sortino = s.get("sortino_per_trade", 0)
    so_cls = "pos" if sortino > 0 else "neg"
    cards.append(_metric_card("Sortino / Trade", _fmt(sortino, 3), so_cls))

    cards.append(_metric_card("Trades", f"{s.get('n_trades', 0):,}"))
    cards.append(_metric_card("Wins", f"{s.get('n_wins', 0):,}"))
    cards.append(_metric_card("Losses", f"{s.get('n_losses', 0):,}"))

    cards.append(_metric_card("Avg Win ($)",
        f"${_fmt(s.get('avg_win', 0), 2)}", "pos"))
    cards.append(_metric_card("Avg Loss ($)",
        f"${_fmt(s.get('avg_loss', 0), 2)}", "neg"))
    cards.append(_metric_card("Expectancy ($)",
        f"${_fmt(s.get('expectancy', 0), 3)}",
        "pos" if s.get("expectancy", 0) > 0 else "neg"))

    cards.append(_metric_card("Mean ln(1+fR)",
        _fmt(s.get("mean_log_return", 0), 6),
        "pos" if s.get("mean_log_return", 0) > 0 else "neg"))

    cards.append(_metric_card("Max Win ($)",
        f"${_fmt(s.get('max_win', 0), 2)}", "pos"))
    cards.append(_metric_card("Max Loss ($)",
        f"${_fmt(s.get('max_loss', 0), 2)}", "neg"))

    cards.append(_metric_card("Max DD",
        _fmt_pct(s.get("max_drawdown_pct", 0)), "neg"))

    cards.append(_metric_card("Total Return",
        _fmt_pct(s.get("total_return_pct", 0)),
        "pos" if s.get("total_return_pct", 0) > 0 else "neg"))

    cards.append(_metric_card("Max Consec Wins",
        f"{s.get('max_consecutive_wins', 0)}", "pos"))
    cards.append(_metric_card("Max Consec Losses",
        f"{s.get('max_consecutive_losses', 0)}", "neg"))

    cards.append(_metric_card("Avg Hold (bars)",
        _fmt(s.get("avg_hold_bars", 0), 1)))
    cards.append(_metric_card("Avg MFE %",
        _fmt(s.get("avg_mfe_frac", 0) * 100, 3)))
    cards.append(_metric_card("Avg Score",
        _fmt(s.get("avg_score", 0), 2)))
    cards.append(_metric_card("Avg T_info",
        _fmt(s.get("avg_T_info", 0), 3)))
    cards.append(_metric_card("Avg Risk %",
        _fmt(s.get("avg_dynamic_risk", 0) * 100, 3)))

    return '<div class="grid metrics">' + "".join(cards) + '</div>'


def build_kv_panel(rows: List[Tuple[str, str, str]]) -> str:
    parts = ['<div class="kv">']
    for k, v, cls in rows:
        parts.append(f'<div class="k">{_esc(k)}</div>'
                     f'<div class="v {cls}">{v}</div>')
    parts.append("</div>")
    return "".join(parts)


def build_stats_table(stats_dict: Dict, key_col: str,
                       extra_cols: List[str]) -> str:
    if not stats_dict:
        return "<p style='color:var(--dim)'>No data.</p>"
    rows = []
    cols = [key_col, "Trades", "Wins", "Losses", "WR%",
            "Sum PnL", "Mean PnL", "PF"] + extra_cols
    header = "".join(f"<th>{_esc(c)}</th>" for c in cols)
    for k, d in stats_dict.items():
        wr = d.get("win_rate", 0) * 100
        sum_pnl = d.get("sum_pnl", 0)
        mean_pnl = d.get("mean_pnl", 0)
        pf = d.get("profit_factor", 0)
        wr_cls = "pos" if wr >= 50 else "neg"
        sp_cls = "pos" if sum_pnl > 0 else ("neg" if sum_pnl < 0 else "")
        mp_cls = "pos" if mean_pnl > 0 else ("neg" if mean_pnl < 0 else "")
        pf_cls = "pos" if pf >= 1.0 else "neg"
        pf_str = "∞" if pf == float("inf") else _fmt(pf, 3)

        cells = [
            f'<td class="sym">{_esc(k)}</td>',
            f"<td>{d.get('n', 0)}</td>",
            f"<td>{d.get('wins', 0)}</td>",
            f"<td>{d.get('losses', 0)}</td>",
            f'<td class="{wr_cls}">{wr:.1f}%</td>',
            f'<td class="{sp_cls}">${_fmt(sum_pnl, 2)}</td>',
            f'<td class="{mp_cls}">${_fmt(mean_pnl, 2)}</td>',
            f'<td class="{pf_cls}">{pf_str}</td>',
        ]
        # Extra columns
        for ec in extra_cols:
            if ec == "Avg Hold":
                cells.append(f"<td>{_fmt(d.get('avg_hold_bars', 0), 1)}</td>")
            elif ec == "Mean Score":
                cells.append(f"<td>{_fmt(d.get('mean_score', 0), 2)}</td>")
            else:
                cells.append("<td>—</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (f'<table id="stats-table"><thead><tr>{header}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def build_trade_table(trades: List[Dict],
                       per_trade_dir: Optional[str]) -> str:
    """Build sortable table of all trades."""
    if not trades:
        return "<p style='color:var(--dim)'>No trades.</p>"

    header_cols = ["#", "Symbol", "Action", "Entry Time",
                    "Entry $", "Exit $", "PnL $", "ln(1+fR)",
                    "Score", "T_info", "Risk %", "MFE %",
                    "Hold", "Exit Reason"]
    header = "".join(
        f'<th onclick="sortTable({i})">{c}</th>'
        for i, c in enumerate(header_cols)
    )

    rows = []
    for i, t in enumerate(trades):
        seq = i + 1
        sym = _esc(t.get("symbol", "?"))
        action = _esc(t.get("action", "?"))
        entry_t = str(t.get("entry_time", ""))[:19]
        entry_px = _safe_float(t.get("entry_price"))
        exit_px = _safe_float(t.get("exit_price"))
        net = _safe_float(t.get("net_pnl"))
        lr = _safe_float(t.get("log_return"))
        score = _safe_float(t.get("score"))
        ti = _safe_float(t.get("T_info") or t.get("T_info_val"))
        risk = _safe_float(t.get("dynamic_risk")) * 100
        mfe = _safe_float(t.get("mfe_frac")) * 100
        hold = _safe_int(t.get("hold_bars"))
        reason = _esc(str(t.get("exit_reason", "?"))[:40])

        pnl_cls = "pos" if net > 0 else ("neg" if net < 0 else "")
        lr_cls = "pos" if lr > 0 else ("neg" if lr < 0 else "")

        # Link to per-trade page
        link = ""
        if per_trade_dir is not None:
            fname = f"trades/trade_{i+1:04d}_{_safe_filename(sym)}.html"
            link = f'<a class="link" href="{_esc(fname)}">#{seq}</a>'
        else:
            link = f"#{seq}"

        rows.append(
            f'<tr>'
            f'<td>{link}</td>'
            f'<td class="sym">{sym}</td>'
            f'<td>{action}</td>'
            f'<td>{_esc(entry_t)}</td>'
            f'<td>{_fmt(entry_px, 6)}</td>'
            f'<td>{_fmt(exit_px, 6)}</td>'
            f'<td class="{pnl_cls}">{net:+.4f}</td>'
            f'<td class="{lr_cls}">{lr:+.6f}</td>'
            f'<td>{score:.2f}</td>'
            f'<td>{ti:.3f}</td>'
            f'<td>{risk:.3f}</td>'
            f'<td>{mfe:.3f}</td>'
            f'<td>{hold}</td>'
            f'<td>{reason}</td>'
            f'</tr>'
        )

    return (f'<input class="filter" id="tradeFilter" '
            f'placeholder="Filter trades…" '
            f'oninput="filterTable()"/>'
            f'<table id="tradeTable"><thead><tr>{header}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


SORT_JS = """
<script>
let sortDir = {};
function sortTable(col) {
  const table = document.getElementById('tradeTable')
              || document.getElementById('stats-table');
  if (!table) return;
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const dir = sortDir[col] = !sortDir[col];
  const getVal = (r) => {
    const c = r.cells[col];
    if (!c) return '';
    const txt = c.innerText.trim();
    // Strip $ , % + and try numeric
    const n = parseFloat(txt.replace(/[$,%+]/g, ''));
    return isNaN(n) ? txt.toLowerCase() : n;
  };
  rows.sort((a, b) => {
    const va = getVal(a), vb = getVal(b);
    if (typeof va === 'number' && typeof vb === 'number')
      return dir ? va - vb : vb - va;
    return dir ? String(va).localeCompare(String(vb))
               : String(vb).localeCompare(String(va));
  });
  rows.forEach(r => tbody.appendChild(r));
}
function filterTable() {
  const q = document.getElementById('tradeFilter').value.toLowerCase();
  const rows = document.querySelectorAll('#tradeTable tbody tr');
  rows.forEach(r => {
    r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none';
  });
}
function showTab(id) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  document.querySelector(`[data-tab="${id}"]`).classList.add('active');
}
</script>
"""


def build_index_html(meta: Optional[Dict], trades: List[Dict],
                       summary: Dict, out_dir: str,
                       per_trade: bool) -> str:
    # Header
    h = []
    h.append('<!DOCTYPE html><html lang="en"><head>')
    h.append('<meta charset="utf-8"/>')
    h.append('<meta name="viewport" '
             'content="width=device-width,initial-scale=1"/>')
    h.append('<title>Backtest Analysis</title>')
    # Plotly from CDN (inline for the first chart will be included)
    h.append('<script src="https://cdn.plot.ly/plotly-2.27.0.min.js">'
             '</script>')
    h.append(f'<style>{CSS}</style>')
    h.append('</head><body><div class="container">')

    # Title
    mode = (meta or {}).get("mode", "backtest")
    h.append(f'<h1>📊 Backtest Analysis — {_esc(mode)}</h1>')
    if meta:
        h.append('<div class="subtitle">')
        for k in ("started_at", "timeframe", "N", "W", "L",
                   "K_MIN", "K_MAX", "INITIAL_CAPITAL",
                   "LEVERAGE_BASE", "PO_FIXED_PRICE",
                   "GAUGE_DISABLE_SELL", "TRAIL_ENABLED"):
            if k in meta:
                h.append(f'<span class="meta-line">'
                         f'<b>{_esc(k)}</b>: {_esc(meta[k])}</span> &nbsp; ')
        h.append('</div>')
    h.append(f'<div class="meta-line">Generated: '
             f'{datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}'
             f'</div>')

    # Metric cards
    h.append('<h2>📈 Key Metrics</h2>')
    h.append(build_metrics_grid(summary))

    # Tabs
    h.append('<div class="tabs">')
    h.append('<button class="tab active" data-tab="overview" '
             'onclick="showTab(\'overview\')">Overview</button>')
    h.append('<button class="tab" data-tab="trades" '
             'onclick="showTab(\'trades\')">All Trades</button>')
    h.append('<button class="tab" data-tab="symbols" '
             'onclick="showTab(\'symbols\')">By Symbol</button>')
    h.append('<button class="tab" data-tab="actions" '
             'onclick="showTab(\'actions\')">By Action</button>')
    h.append('<button class="tab" data-tab="exits" '
             'onclick="showTab(\'exits\')">By Exit</button>')
    h.append('<button class="tab" data-tab="scores" '
             'onclick="showTab(\'scores\')">By Score</button>')
    h.append('</div>')

    # Tab 1: Overview
    h.append('<div class="tab-content active" id="tab-overview">')
    equity_fig = make_equity_curve(summary)
    h.append('<div class="chart-wrap">')
    h.append(equity_fig.to_html(full_html=False,
                                  include_plotlyjs=False,
                                  config={"displayModeBar": True,
                                          "responsive": True}))
    h.append('</div>')
    dist_fig = make_distributions(trades)
    h.append('<div class="chart-wrap">')
    h.append(dist_fig.to_html(full_html=False, include_plotlyjs=False,
                                config={"responsive": True}))
    h.append('</div>')
    hour_fig = make_hour_heatmap(summary)
    h.append('<div class="chart-wrap">')
    h.append(hour_fig.to_html(full_html=False, include_plotlyjs=False,
                                config={"responsive": True}))
    h.append('</div>')
    h.append('</div>')  # /overview

    # Tab 2: Trades
    h.append('<div class="tab-content" id="tab-trades">')
    h.append('<h2>📋 All Trades</h2>')
    h.append(build_trade_table(trades,
                                per_trade_dir="." if per_trade else None))
    h.append('</div>')

    # Tab 3: By Symbol
    h.append('<div class="tab-content" id="tab-symbols">')
    h.append('<h2>💱 Performance by Symbol</h2>')
    sym_fig = make_symbol_bars(summary)
    h.append('<div class="chart-wrap">')
    h.append(sym_fig.to_html(full_html=False, include_plotlyjs=False,
                                config={"responsive": True}))
    h.append('</div>')
    h.append(build_stats_table(
        summary.get("by_symbol", {}), "Symbol", ["Avg Hold"]))
    h.append('</div>')

    # Tab 4: By Action
    h.append('<div class="tab-content" id="tab-actions">')
    h.append('<h2>🔼🔽 BUY vs SELL</h2>')
    act_fig = make_action_breakdown(summary)
    h.append('<div class="chart-wrap">')
    h.append(act_fig.to_html(full_html=False, include_plotlyjs=False,
                                config={"responsive": True}))
    h.append('</div>')
    h.append(build_stats_table(
        summary.get("by_action", {}), "Action", []))
    h.append('</div>')

    # Tab 5: By Exit
    h.append('<div class="tab-content" id="tab-exits">')
    h.append('<h2>🚪 Exit Reasons</h2>')
    exit_fig = make_exit_reason_pie(summary)
    h.append('<div class="chart-wrap">')
    h.append(exit_fig.to_html(full_html=False, include_plotlyjs=False,
                                config={"responsive": True}))
    h.append('</div>')
    h.append(build_stats_table(
        summary.get("by_exit_reason", {}), "Exit Reason",
        ["Avg Hold"]))
    h.append('</div>')

    # Tab 6: By Score
    h.append('<div class="tab-content" id="tab-scores">')
    h.append('<h2>🎯 Score Buckets</h2>')
    # Score bar chart
    scores = summary.get("by_score", {})
    if scores:
        xs = sorted(scores.keys())
        ns = [scores[s]["n"] for s in xs]
        wrs = [scores[s]["win_rate"] * 100 for s in xs]
        pnls = [scores[s]["mean_pnl"] for s in xs]
        sfig = make_subplots(specs=[[{"secondary_y": True}]])
        sfig.add_trace(go.Bar(
            x=xs, y=ns, marker_color=C_BLUE, name="Trades",
            hovertemplate="Score %{x}<br>Trades: %{y}<extra></extra>",
        ), secondary_y=False)
        sfig.add_trace(go.Scatter(
            x=xs, y=wrs, mode="markers+lines",
            line=dict(color=C_GREEN, width=2),
            marker=dict(size=10),
            name="Win Rate %",
            hovertemplate="Score %{x}<br>WR: %{y:.1f}%<extra></extra>",
        ), secondary_y=True)
        sfig.add_trace(go.Scatter(
            x=xs, y=pnls, mode="markers+lines",
            line=dict(color=C_ORANGE, width=2, dash="dot"),
            marker=dict(size=8, symbol="diamond"),
            name="Mean PnL $",
            yaxis="y3",
            hovertemplate="Score %{x}<br>Mean: $%{y:.2f}<extra></extra>",
        ))
        sfig.update_layout(
            **_DARK_LAYOUT, height=440,
            title="Performance by Score",
            xaxis_title="Score",
            hovermode="x unified",
            legend=dict(orientation="h", y=1.02, x=0),
            yaxis=dict(title="Trades", showgrid=True,
                       gridcolor="rgba(255,255,255,0.05)"),
            yaxis2=dict(title="Win Rate %", overlaying="y", side="right",
                        range=[0, 100], showgrid=False),
        )
        h.append('<div class="chart-wrap">')
        h.append(sfig.to_html(full_html=False, include_plotlyjs=False,
                                config={"responsive": True}))
        h.append('</div>')
    # Table
    rows = []
    for s in sorted(scores.keys()):
        d = scores[s]
        rows.append(
            f"<tr><td>{s}</td><td>{d['n']}</td>"
            f"<td class='{'pos' if d['win_rate']>=0.5 else 'neg'}'>"
            f"{d['win_rate']*100:.1f}%</td>"
            f"<td class='{'pos' if d['mean_pnl']>0 else 'neg'}'>"
            f"${d['mean_pnl']:.2f}</td>"
            f"<td>${d['sum_pnl']:.2f}</td></tr>"
        )
    h.append('<table><thead><tr><th>Score</th><th>Trades</th>'
             '<th>Win Rate</th><th>Mean PnL</th><th>Sum PnL</th>'
             f'</tr></thead><tbody>{"".join(rows)}</tbody></table>')
    h.append('</div>')

    # Footer
    h.append(f'<div class="footer">'
             f'Generated by analyze_backtest.py — '
             f'{len(trades):,} trades analyzed'
             f'</div>')
    h.append('</div>')  # /container
    h.append(SORT_JS)
    h.append('</body></html>')
    return "".join(h)


def build_trade_html(trade: Dict, idx: int, ohlcv: Optional[pd.DataFrame],
                      meta: Optional[Dict]) -> str:
    sym = trade.get("symbol", "?")
    action = trade.get("action", "?")
    net = _safe_float(trade.get("net_pnl"))
    h = []
    h.append('<!DOCTYPE html><html lang="en"><head>')
    h.append('<meta charset="utf-8"/>')
    h.append(f'<title>Trade #{idx} — {_esc(sym)}</title>')
    h.append('<script src="https://cdn.plot.ly/plotly-2.27.0.min.js">'
             '</script>')
    h.append(f'<style>{CSS}</style>')
    h.append('</head><body><div class="container">')

    h.append('<div class="navbar">')
    h.append('<a href="../index.html">← Back to summary</a>')
    h.append(f'<span style="color:var(--dim)">Trade #{idx}</span>')
    h.append('</div>')

    pnl_cls = "pos" if net > 0 else ("neg" if net < 0 else "")
    h.append(f'<h1>{_esc(sym)} — {_esc(action)} — '
             f'<span class="{pnl_cls}">${net:+.4f}</span></h1>')

    # Chart
    if ohlcv is not None and len(ohlcv) > 0:
        fig = make_trade_chart(trade, ohlcv)
        h.append('<div class="chart-wrap">')
        h.append(fig.to_html(full_html=False, include_plotlyjs=False,
                              config={"responsive": True,
                                      "scrollZoom": True}))
        h.append('</div>')
    else:
        h.append('<div class="chart-wrap" style="padding:20px;'
                 'text-align:center;color:var(--dim)">'
                 'OHLCV data not available in cache for this symbol.</div>')

    # Key/value panels
    h.append('<h2>Trade Details</h2>')

    def _cls(v):
        return "pos" if v > 0 else ("neg" if v < 0 else "")

    rows_a = [
        ("Symbol", _esc(sym), ""),
        ("Action", _esc(action),
            "pos" if action == "BUY" else "neg"),
        ("Entry Time", _esc(str(trade.get("entry_time", ""))[:19]), ""),
        ("Entry Price", _fmt(trade.get("entry_price"), 6), ""),
        ("Exit Price", _fmt(trade.get("exit_price"), 6), ""),
        ("Exit Reason", _esc(trade.get("exit_reason", "?")), ""),
        ("Net PnL ($)", f"${_fmt(net, 4)}", _cls(net)),
        ("Log Return",
            _fmt(trade.get("log_return"), 6),
            _cls(_safe_float(trade.get("log_return")))),
        ("Partial PnL ($)",
            f"${_fmt(trade.get('partial_pnl', 0), 4)}",
            _cls(_safe_float(trade.get("partial_pnl")))),
        ("Is Win", "YES" if trade.get("is_win") else "NO",
            "pos" if trade.get("is_win") else "neg"),
        ("Hold Bars", str(_safe_int(trade.get("hold_bars"))), ""),
        ("MFE %", _fmt(_safe_float(trade.get("mfe_frac")) * 100, 3), ""),
    ]
    rows_b = [
        ("Score", _fmt(trade.get("score"), 3), ""),
        ("T_info", _fmt(trade.get("T_info") or trade.get("T_info_val"), 4),
            ""),
        ("Dynamic Risk",
            _fmt(_safe_float(trade.get("dynamic_risk")) * 100, 3) + "%",
            ""),
        ("ATR", _fmt(trade.get("atr"), 6), ""),
        ("SL Dist Frac",
            _fmt(trade.get("sl_dist_frac"), 6), ""),
        ("R:R Design", _fmt(trade.get("rr_design"), 3), ""),
        ("SL Sigma", _fmt(trade.get("sl_sigma"), 3), ""),
        ("Adv USD",
            f"${_fmt(trade.get('adv_usd', 0)/1e6, 2)}M", ""),
        ("Friction", _fmt(trade.get("friction"), 6), ""),
        ("Gauge Force", _fmt(trade.get("gauge_force"), 6), ""),
        ("ΔGap", _fmt(trade.get("delta_gap"), 6), ""),
        ("Geodesic Accel", _fmt(trade.get("geodesic_accel"), 6), ""),
        ("H", _fmt(trade.get("H"), 6), ""),
        ("H/Hmax", _fmt(trade.get("H_over_Hmax"), 4), ""),
        ("dH", _fmt(trade.get("dH"), 6), ""),
        ("dF", _fmt(trade.get("dF"), 6), ""),
        ("E_therm", _fmt(trade.get("E_therm"), 6), ""),
        ("V", _fmt(trade.get("V"), 6), ""),
        ("C", _fmt(trade.get("C"), 6), ""),
        ("EMA Slope", _fmt(trade.get("ema_slope"), 8), ""),
        ("Dist from EMA (σ)",
            _fmt(trade.get("dist_from_ema_norm"), 3), ""),
        ("Friction/SL",
            _fmt(trade.get("friction_drag_over_sl"), 4), ""),
    ]

    h.append('<div style="display:grid;grid-template-columns:1fr 1fr;'
             'gap:30px">')
    h.append('<div><h3>Execution</h3>')
    h.append(build_kv_panel(rows_a))
    h.append('</div>')
    h.append('<div><h3>Physics & Signals</h3>')
    h.append(build_kv_panel(rows_b))
    h.append('</div>')
    h.append('</div>')

    h.append('<div class="footer">Trade #%d — %s</div>'
             % (idx, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")))
    h.append('</div></body></html>')
    return "".join(h)


# ════════════════════════════════════════════════════════════════
# Flat CSV export
# ════════════════════════════════════════════════════════════════

def export_csv(trades: List[Dict], path: str):
    if not trades:
        return
    df = pd.DataFrame(trades)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")],
                  errors="ignore")
    df.to_csv(path, index=False)
    print(f"  💾 {path}")


# ════════════════════════════════════════════════════════════════
# Standalone pages
# ════════════════════════════════════════════════════════════════

def write_standalone_fig(fig: go.Figure, path: str, title: str):
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        f'<title>{_esc(title)}</title>'
        f'<style>{CSS}</style>'
        '</head><body><div class="container">'
        f'<h1>{_esc(title)}</h1>'
        '<p><a href="index.html" '
        'style="color:var(--accent)">← Back</a></p>'
        '<div class="chart-wrap">'
        + fig.to_html(full_html=False, include_plotlyjs="cdn",
                       config={"responsive": True})
        + '</div></div></body></html>'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  🌐 {path}")


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Comprehensive backtest trade analyzer."
    )
    ap.add_argument("--input", default=DEFAULT_INPUT,
                    help=f"Input JSONL (default: {DEFAULT_INPUT})")
    ap.add_argument("--out-dir", default=DEFAULT_OUT,
                    help=f"Output directory (default: {DEFAULT_OUT})")
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR,
                    help="OHLCV parquet cache directory")
    ap.add_argument("--no-trades-html", action="store_true",
                    help="Skip per-trade HTML pages")
    ap.add_argument("--no-charts-index", action="store_true",
                    help="Skip heavy charts in index (faster)")
    args = ap.parse_args()

    print(f"╔══════════════════════════════════════════════════════════════╗")
    print(f"║  Backtest Analyzer                                          ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"📖 Input:  {args.input}")

    try:
        meta, trades = load_jsonl(args.input)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)

    print(f"✓ Loaded {len(trades):,} trades")
    if meta:
        print(f"  Meta: mode={meta.get('mode')}, "
              f"tf={meta.get('timeframe')}, "
              f"N={meta.get('N')}, W={meta.get('W')}")
    if not trades:
        print("❌ No trades found.")
        sys.exit(1)

    # Prepare output dirs
    os.makedirs(args.out_dir, exist_ok=True)
    trades_dir = os.path.join(args.out_dir, "trades")
    if not args.no_trades_html:
        os.makedirs(trades_dir, exist_ok=True)

    print(f"\n📊 Computing summary statistics…")
    summary = compute_summary(trades)
    print(f"  ✓ {summary['n_trades']} trades, "
          f"WR={summary['win_rate']*100:.1f}%, "
          f"PF={summary['profit_factor']:.3f}, "
          f"PnL=${summary['sum_pnl']:+.2f}")

    # Save summary JSON (strip _equity_curve to a reasonable size)
    summary_path = os.path.join(args.out_dir, "summary.json")
    summary_for_json = {k: v for k, v in summary.items()
                         if not k.startswith("_")}
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_for_json, f, indent=2, default=str)
    print(f"  💾 {summary_path}")

    # CSV
    csv_path = os.path.join(args.out_dir, "metrics.csv")
    export_csv(trades, csv_path)

    # Standalone pages
    eq_fig = make_equity_curve(summary)
    write_standalone_fig(eq_fig,
                          os.path.join(args.out_dir, "equity_curve.html"),
                          "Equity Curve")
    dist_fig = make_distributions(trades)
    write_standalone_fig(dist_fig,
                          os.path.join(args.out_dir, "distributions.html"),
                          "Distributions")

    # Per-trade pages
    if not args.no_trades_html:
        print(f"\n📈 Rendering per-trade pages…")
        # Determine timeframe for OHLCV loading
        tf = (meta or {}).get("timeframe", "1h")
        # Preload OHLCV per symbol
        needed_syms = set(t.get("symbol") for t in trades if t.get("symbol"))
        ohlcv_cache: Dict[str, Optional[pd.DataFrame]] = {}
        n_loaded = 0
        for sym in needed_syms:
            df = load_ohlcv(sym, tf, args.cache_dir)
            ohlcv_cache[sym] = df
            if df is not None:
                n_loaded += 1
        print(f"  ✓ Loaded OHLCV for {n_loaded}/{len(needed_syms)} symbols "
              f"(timeframe={tf})")

        for i, t in enumerate(trades):
            sym = t.get("symbol", "?")
            fname = f"trade_{i+1:04d}_{_safe_filename(sym)}.html"
            fpath = os.path.join(trades_dir, fname)
            html = build_trade_html(t, i + 1,
                                      ohlcv_cache.get(sym), meta)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(html)
            if (i + 1) % 50 == 0 or (i + 1) == len(trades):
                print(f"  ✓ {i+1}/{len(trades)}")

    # Index
    print(f"\n📄 Building index page…")
    index_html = build_index_html(meta, trades, summary,
                                    args.out_dir,
                                    per_trade=not args.no_trades_html)
    index_path = os.path.join(args.out_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"  💾 {index_path}")

    print(f"\n╔══════════════════════════════════════════════════════════════╗")
    print(f"║  ✅ DONE                                                    ║")
    print(f"╚══════════════════════════════════════════════════════════════╝")
    print(f"  📁 {args.out_dir}/")
    print(f"     ├── index.html")
    if not args.no_trades_html:
        print(f"     ├── trades/  ({len(trades)} pages)")
    print(f"     ├── summary.json")
    print(f"     ├── metrics.csv")
    print(f"     ├── equity_curve.html")
    print(f"     └── distributions.html")
    print(f"\n  ▶ Open in browser:")
    print(f"     file://{os.path.abspath(index_path)}")


if __name__ == "__main__":
    main()
