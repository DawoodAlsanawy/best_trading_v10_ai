#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_bot.py — Comprehensive bot diagnostic
- Extracts Config from trading.py (via AST)
- Analyzes trades_log_backtest.jsonl
- Focuses on worst-case scenarios

Usage:
    python analyze_bot.py
"""

import os
import ast
import json
import math
from collections import defaultdict
from datetime import datetime


# ============================================================
# Config extraction
# ============================================================

def extract_config(bot_file="trading.py"):
    if not os.path.exists(bot_file):
        for cand in ["trading_11.py", "trading_10.py"]:
            if os.path.exists(cand):
                bot_file = cand
                break
        else:
            return None, "Bot file not found"
    try:
        with open(bot_file, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        return None, f"Parse error: {e}"

    cfg = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'Config':
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign):
                    if not isinstance(stmt.target, ast.Name):
                        continue
                    cfg[stmt.target.id] = _ast_val(stmt.value)
                elif isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Name):
                            cfg[tgt.id] = _ast_val(stmt.value)
            break
    return cfg, None


def _ast_val(node):
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        pass
    if isinstance(node, ast.Call):
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name == 'field':
            for kw in node.keywords:
                if kw.arg == 'default_factory':
                    try:
                        return f"<factory: {ast.unparse(kw.value)}>"
                    except Exception:
                        return "<factory>"
                if kw.arg == 'default':
                    return _ast_val(kw.value)
    try:
        return f"<expr: {ast.unparse(node)[:80]}>"
    except Exception:
        return "<unknown>"


# ============================================================
# Trade loader
# ============================================================

def load_trades(path="trades_log_backtest.jsonl"):
    trades, meta = [], None
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('_meta'):
                meta = r
                continue
            trades.append(r)
    return trades, meta


# ============================================================
# Helpers
# ============================================================

def _f(v, d=0.0):
    try:
        return float(v)
    except Exception:
        return d

def _i(v, d=0):
    try:
        return int(v)
    except Exception:
        return d

def _mean(a):
    return sum(a) / len(a) if a else 0.0

def _std(a):
    if len(a) < 2:
        return 0.0
    m = _mean(a)
    return math.sqrt(sum((x - m) ** 2 for x in a) / (len(a) - 1))

def _pct(a, p):
    if not a:
        return 0.0
    s = sorted(a)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)

def _trade_notional(t):
    p = _f(t.get('entry_price', 0)) or _f(t.get('signal_price', 0))
    q = _f(t.get('pos_size', 0))
    return p * q

def _trade_risk(t):
    p = _f(t.get('entry_price', 0)) or _f(t.get('signal_price', 0))
    q = _f(t.get('pos_size', 0))
    sld = _f(t.get('sl_dist_frac', 0))
    return p * q * sld

def _effective_leverage(t):
    n = _trade_notional(t)
    cap = _f(t.get('capital_before', 100))
    return n / cap if cap > 0 and n > 0 else 0.0


# ============================================================
# Sections
# ============================================================

def S1_config(cfg, meta, out):
    out.append("=" * 78)
    out.append("SECTION 1 — BOT CONFIGURATION (extracted from bot file)")
    out.append("=" * 78)
    if not cfg:
        out.append("❌ extraction failed")
        return

    groups = {
        "Capital & Risk": [
            "INITIAL_CAPITAL", "CAPITAL_FLOOR", "BASE_RISK", "MIN_RISK",
            "MAX_RISK", "MIN_RISK_PER_TRADE", "MAX_RISK_PER_TRADE",
            "PORTFOLIO_HEAT_MAX", "RISK_STRENGTH_MIN", "RISK_STRENGTH_MAX",
            "MAX_DRAWDOWN_HALT", "DRAWDOWN_REDUCE_AT", "DRAWDOWN_REDUCE_AT_50",
            "DRAWDOWN_REDUCE_AT_70", "REDUCED_RISK_MULT", "BUDGET_ENABLED",
        ],
        "Leverage & Margin": [
            "LEVERAGE_BASE", "LEVERAGE_MIN", "LEVERAGE_MAX", "LEVERAGE",
            "MAX_ABS_NOTIONAL", "MIN_NOTIONAL", "LIQ_ENABLED",
            "LIQ_SAFETY_MULT", "LIQ_FALLBACK_MMR", "LIQ_EMERGENCY_PROGRESS",
        ],
        "SL / TP": [
            "SL_REF_KAPPA", "SL_MIN_SIGMA", "SL_MAX_SIGMA", "SL_WIDEN_MULT",
            "TP_MULT", "FRICTION_DIP_KAPPA", "SL_FACTOR",
        ],
        "Trailing & Partial": [
            "TRAIL_ENABLED", "TRAIL_KAPPA", "TRAIL_MIN_FRAC", "TRAIL_MAX_FRAC",
            "TRAIL_ACTIVATE_AT_R", "TRAIL_DYNAMIC",
            "PARTIAL_TP_ENABLED", "PARTIAL_TP_R", "PARTIAL_TP_PCT",
        ],
        "Filters": [
            "MIN_SCORE", "FILTER_ENABLED", "FILTER_MIN_VOTES",
            "REGIME_FILTER_ENABLED", "SR_FILTER_ENABLED",
            "RULE_FILTER_ENABLED", "RULE_MIN_SCORE", "ML_FILTER_ENABLED",
        ],
        "Timeframe & Windows": [
            "timeframe", "history_days", "N", "W", "L", "K_MIN", "K_MAX",
            "MAX_HOLD_BARS", "REENTRY_COOLDOWN_BARS", "REENTRY_COOLDOWN_ENABLED",
            "N_HOURS", "W_HOURS", "L_HOURS", "ADV_BARS",
        ],
        "Concurrency": [
            "MAX_CONCURRENT_ASSETS", "CORRELATION_THRESHOLD",
        ],
        "Fees": [
            "MAKER_FEE", "TAKER_FEE", "FUNDING_RATE_COST", "FUNDING_INTERVAL_BARS",
        ],
    }
    seen = set()
    for cat, keys in groups.items():
        out.append(f"\n  ── {cat} ──")
        for k in keys:
            if k in cfg:
                out.append(f"    {k:<28} = {cfg[k]}")
                seen.add(k)
    others = sorted(k for k in cfg if k not in seen)
    out.append(f"\n  ── Other fields ({len(others)}) ──")
    for k in others[:60]:
        v = cfg[k]
        out.append(f"    {k:<28} = {str(v)[:60]}")

    if meta:
        out.append("\n  ── Run metadata ──")
        for k, v in meta.items():
            if k == '_meta':
                continue
            out.append(f"    {k:<28} = {v}")
    out.append("")


def S2_overall(trades, out):
    out.append("=" * 78)
    out.append("SECTION 2 — OVERALL PERFORMANCE")
    out.append("=" * 78)
    if not trades:
        out.append("no trades")
        return
    n = len(trades)
    pnls = [_f(t.get('net_pnl')) for t in trades]
    lrs = [_f(t.get('log_return')) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    cap0 = _f(trades[0].get('capital_before', 100))
    capN = _f(trades[-1].get('capital_after', 100))

    # Drawdown curve
    eq = [cap0]
    for t in trades:
        eq.append(_f(t.get('capital_after', eq[-1])))
    peak = eq[0]
    max_dd = 0.0
    max_dd_at = 0
    for i, e in enumerate(eq):
        peak = max(peak, e)
        dd = (peak - e) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_at = i

    out.append(f"  n_trades                {n:>12}")
    out.append(f"  Capital start           ${cap0:>12,.2f}")
    out.append(f"  Capital end             ${capN:>12,.2f}")
    out.append(f"  Return                  {(capN / cap0 - 1) * 100:>12,.2f}%")
    out.append(f"  Win rate                {len(wins)/n*100:>12,.2f}%")
    out.append(f"  Profit factor           {(sum(wins)/abs(sum(losses)) if losses else float('inf')):>12,.4f}")
    out.append(f"  Avg win                 ${_mean(wins):>12,.2f}")
    out.append(f"  Avg loss                ${_mean(losses):>12,.2f}")
    out.append(f"  Payoff ratio            {(_mean(wins)/abs(_mean(losses)) if losses else 0):>12,.4f}")
    out.append(f"  Mean log return         {_mean(lrs):>12,.6f}")
    out.append(f"  Std log return          {_std(lrs):>12,.6f}")
    out.append(f"  Max drawdown            {max_dd:>12,.2f}%")
    out.append(f"  Max DD at trade index   {max_dd_at:>12}")
    out.append("")


def S3_sl_dist(trades, out):
    out.append("=" * 78)
    out.append("SECTION 3 — SL DISTANCE (qty explosion check)")
    out.append("=" * 78)
    sld = [_f(t.get('sl_dist_frac', 0)) for t in trades]
    sld = [x for x in sld if x > 0]
    if not sld:
        # fallback
        for t in trades:
            p = _f(t.get('signal_price', 0))
            sl = _f(t.get('signal_sl', 0))
            if p > 0 and sl > 0:
                sld.append(abs(p - sl) / p)
    if not sld:
        out.append("no data")
        return
    out.append(f"  n                       {len(sld):>12}")
    out.append(f"  Mean                    {_mean(sld)*100:>12.3f}%")
    out.append(f"  Std                     {_std(sld)*100:>12.3f}%")
    for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        out.append(f"  p{p:<2}                     {_pct(sld, p)*100:>12.3f}%")

    out.append("\n  Distribution:")
    buckets = [
        ("< 0.3%   🔴 VERY TIGHT (explosion)", 0.0, 0.003),
        ("0.3-0.5% 🟠 TIGHT (warning)", 0.003, 0.005),
        ("0.5-0.8% 🟡 ACCEPTABLE", 0.005, 0.008),
        ("0.8-1.5% 🟢 NORMAL", 0.008, 0.015),
        ("1.5-3.0% 🟢 WIDE", 0.015, 0.030),
        ("> 3.0%   ⚪ VERY WIDE", 0.030, 10.0),
    ]
    for label, lo, hi in buckets:
        c = sum(1 for x in sld if lo <= x < hi)
        p = c / len(sld) * 100
        out.append(f"    {label:<40} {c:>6} ({p:>5.2f}%)")
    out.append("")


def S4_notional_leverage(trades, out):
    out.append("=" * 78)
    out.append("SECTION 4 — NOTIONAL & EFFECTIVE LEVERAGE")
    out.append("=" * 78)
    notionals = [_trade_notional(t) for t in trades]
    notionals = [x for x in notionals if x > 0]
    levs = [_effective_leverage(t) for t in trades]
    levs = [x for x in levs if x > 0]

    if not notionals:
        out.append("no data")
        return
    out.append(f"  Notional n              {len(notionals):>12}")
    out.append(f"  Mean                    ${_mean(notionals):>12,.2f}")
    out.append(f"  Median                  ${_pct(notionals, 50):>12,.2f}")
    out.append(f"  Max                     ${max(notionals):>12,.2f}")
    out.append(f"  Min                     ${min(notionals):>12,.2f}")
    for p in [90, 95, 99]:
        out.append(f"  p{p:<2}                     ${_pct(notionals, p):>12,.2f}")

    out.append("\n  Notional buckets:")
    nb = [
        ("$0-50", 0, 50), ("$50-100", 50, 100), ("$100-200", 100, 200),
        ("$200-500", 200, 500), ("$500-1000", 500, 1000),
        ("$1000-5000", 1000, 5000), ("> $5000 (XL)", 5000, float('inf')),
    ]
    for label, lo, hi in nb:
        c = sum(1 for x in notionals if lo <= x < hi)
        p = c / len(notionals) * 100
        out.append(f"    {label:<15} {c:>6} ({p:>5.2f}%)")

    if levs:
        out.append(f"\n  Effective leverage n    {len(levs):>12}")
        out.append(f"  Mean                    {_mean(levs):>12.2f}x")
        out.append(f"  Median                  {_pct(levs, 50):>12.2f}x")
        out.append(f"  Max                     {max(levs):>12.2f}x")
        for p in [90, 95, 99]:
            out.append(f"  p{p:<2}                     {_pct(levs, p):>12.2f}x")

        out.append("\n  Leverage buckets (Binance-typical limits):")
        lb = [
            ("< 10x (safe)", 0, 10),
            ("10-25x (typical alts)", 10, 25),
            ("25-50x (typical majors)", 25, 50),
            ("50-75x (BNB max)", 50, 75),
            ("75-100x (ETH max)", 75, 100),
            ("> 100x (BTC only)", 100, 1e9),
        ]
        for label, lo, hi in lb:
            c = sum(1 for x in levs if lo <= x < hi)
            p = c / len(levs) * 100
            out.append(f"    {label:<28} {c:>6} ({p:>5.2f}%)")

    # Top-10 highest notional
    out.append("\n  Top 10 highest-notional trades:")
    ordered = sorted(trades, key=_trade_notional, reverse=True)
    for t in ordered[:10]:
        p = _f(t.get('entry_price', 0))
        q = _f(t.get('pos_size', 0))
        sld = _f(t.get('sl_dist_frac', 0))
        cap = _f(t.get('capital_before', 100))
        n = p * q
        lev = n / cap if cap > 0 else 0
        out.append(f"    {t.get('symbol','?'):<15} "
                   f"notional=${n:>9,.2f} qty={q:.4f} "
                   f"sl={sld*100:.3f}% lev={lev:.2f}x")
    out.append("")


def S5_risk_per_trade(trades, out):
    out.append("=" * 78)
    out.append("SECTION 5 — RISK PER TRADE (actual dollar risk)")
    out.append("=" * 78)
    risks = [_trade_risk(t) for t in trades]
    risks = [x for x in risks if x > 0]
    if not risks:
        out.append("no data")
        return
    out.append(f"  n                       {len(risks):>12}")
    out.append(f"  Mean                    ${_mean(risks):>12,.2f}")
    out.append(f"  Median                  ${_pct(risks, 50):>12,.2f}")
    out.append(f"  Min                     ${min(risks):>12,.2f}")
    out.append(f"  Max                     ${max(risks):>12,.2f}")
    for p in [5, 25, 75, 95, 99]:
        out.append(f"  p{p:<2}                     ${_pct(risks, p):>12,.2f}")
    med = _pct(risks, 50)
    if med > 0:
        out.append(f"  Max/Median ratio        {max(risks)/med:>12.2f}x")
    out.append("")


def S6_streaks(trades, out):
    out.append("=" * 78)
    out.append("SECTION 6 — WORST-CASE SEQUENCES")
    out.append("=" * 78)
    pnls = [_f(t.get('net_pnl')) for t in trades]

    # Longest losing streak
    max_ls = 0; cur = 0; mx_sum = 0; cur_sum = 0; worst_at = 0
    for i, p in enumerate(pnls):
        if p < 0:
            cur += 1; cur_sum += p
            if cur > max_ls:
                max_ls = cur; mx_sum = cur_sum; worst_at = i - cur + 1
        else:
            cur = 0; cur_sum = 0
    out.append(f"  Longest losing streak   {max_ls} (at index {worst_at})")
    out.append(f"    total loss            ${mx_sum:+,.2f}")

    # Longest winning streak
    max_ws = 0; cur = 0; ws_sum = 0; cur_sum = 0
    for p in pnls:
        if p > 0:
            cur += 1; cur_sum += p
            if cur > max_ws:
                max_ws = cur; ws_sum = cur_sum
        else:
            cur = 0; cur_sum = 0
    out.append(f"  Longest winning streak  {max_ws}")
    out.append(f"    total win             ${ws_sum:+,.2f}")

    # Worst rolling windows
    for W in [10, 20, 50, 100]:
        if len(pnls) < W:
            continue
        worst_sum = float('inf'); worst_at = 0
        for i in range(len(pnls) - W + 1):
            s = sum(pnls[i:i+W])
            if s < worst_sum:
                worst_sum = s; worst_at = i
        out.append(f"  Worst {W:>3}-trade window   ${worst_sum:+,.2f} "
                   f"(at index {worst_at})")
    out.append("")


def S7_starting_losses(trades, out):
    out.append("=" * 78)
    out.append("SECTION 7 — STARTING-WORST SIMULATION")
    out.append("=" * 78)
    pnls = [_f(t.get('net_pnl')) for t in trades]
    losses = [p for p in pnls if p < 0]
    if not losses:
        out.append("no losses")
        return
    cap0 = _f(trades[0].get('capital_before', 100))
    avg_l = _mean(losses)
    worst_l = min(losses)

    out.append(f"  Initial capital         ${cap0:>12,.2f}")
    out.append(f"  Avg loss                ${avg_l:>12,.2f}")
    out.append(f"  Worst single loss       ${worst_l:>12,.2f}")

    out.append("\n  If bot STARTS with N consecutive average losses:")
    for N in [3, 5, 10, 15, 20, 30]:
        c = cap0 + N * avg_l
        dd = (cap0 - c) / cap0 * 100
        out.append(f"    N={N:>2}: cap=${c:>10,.2f}  dd={dd:>6.2f}%")

    out.append("\n  If bot STARTS with N consecutive WORST losses:")
    for N in [3, 5, 10, 15, 20]:
        c = cap0 + N * worst_l
        dd = (cap0 - c) / cap0 * 100
        out.append(f"    N={N:>2}: cap=${c:>10,.2f}  dd={dd:>6.2f}%")
    out.append("")


def S8_directional(trades, out):
    out.append("=" * 78)
    out.append("SECTION 8 — BUY vs SELL")
    out.append("=" * 78)
    for act in ["BUY", "SELL"]:
        grp = [t for t in trades if t.get('action') == act]
        if not grp:
            continue
        pnls = [_f(t.get('net_pnl')) for t in grp]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        wr = len(wins) / len(grp) * 100
        pf = sum(wins) / abs(sum(losses)) if losses else float('inf')
        out.append(f"  {act}: n={len(grp)} WR={wr:.2f}% PF={pf:.3f} "
                   f"pnl=${sum(pnls):+,.2f} "
                   f"avg_win=${_mean(wins):.2f} avg_loss=${_mean(losses):.2f}")
    out.append("")


def S9_score(trades, out):
    out.append("=" * 78)
    out.append("SECTION 9 — PERFORMANCE BY SCORE")
    out.append("=" * 78)
    buckets = defaultdict(list)
    for t in trades:
        buckets[int(_f(t.get('score', 0)))].append(t)
    out.append(f"  {'score':>6} {'n':>6} {'WR%':>7} {'PF':>7} "
               f"{'avg_pnl':>11} {'total_pnl':>14}")
    for b in sorted(buckets.keys()):
        grp = buckets[b]
        pnls = [_f(t.get('net_pnl')) for t in grp]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        wr = len(wins) / len(grp) * 100
        pf = sum(wins) / abs(sum(losses)) if losses else 0
        out.append(f"  {b:>6} {len(grp):>6} {wr:>6.2f}% {pf:>7.3f} "
                   f"${_mean(pnls):>10,.2f} ${sum(pnls):>13,.2f}")
    out.append("")


def S10_features(trades, out):
    out.append("=" * 78)
    out.append("SECTION 10 — FEATURE CONDITIONAL (Q1–Q4)")
    out.append("=" * 78)
    feats = ['E_therm', 'friction', 'H_over_Hmax', 'T_info', 'sl_sigma',
             'friction_drag_over_sl', 'dist_from_ema_norm', 'delta_gap',
             'gauge_force', 'geodesic_accel']
    for f in feats:
        vp = [(_f(t.get(f, 0)), _f(t.get('net_pnl'))) for t in trades if f in t]
        vp = [(v, p) for v, p in vp if v != 0]
        if len(vp) < 20:
            continue
        vp.sort(key=lambda x: x[0])
        n = len(vp); q = n // 4
        out.append(f"\n  {f}")
        out.append(f"    {'Q':<3} {'range':<22} {'n':>6} {'WR%':>7} "
                   f"{'PF':>7} {'avg_pnl':>11}")
        for qi in range(4):
            lo = qi * q
            hi = (qi + 1) * q if qi < 3 else n
            chunk = vp[lo:hi]
            if not chunk:
                continue
            vmin = chunk[0][0]; vmax = chunk[-1][0]
            pnls = [p for _, p in chunk]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]
            wr = len(wins) / len(chunk) * 100
            pf = sum(wins) / abs(sum(losses)) if losses else 0
            out.append(f"    Q{qi+1}  [{vmin:>8.4f}, {vmax:>8.4f}] "
                       f"{len(chunk):>6} {wr:>6.2f}% {pf:>7.3f} "
                       f"${_mean(pnls):>10,.2f}")
    out.append("")


def S11_symbols(trades, out):
    out.append("=" * 78)
    out.append("SECTION 11 — PER-SYMBOL (top/bottom 15)")
    out.append("=" * 78)
    by = defaultdict(list)
    for t in trades:
        by[t.get('symbol', '?')].append(t)
    rows = []
    for sym, grp in by.items():
        pnls = [_f(t.get('net_pnl')) for t in grp]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        rows.append((sym, len(grp),
                     len(wins) / len(grp) * 100,
                     sum(wins) / abs(sum(losses)) if losses else 0,
                     sum(pnls)))
    rows.sort(key=lambda r: r[4], reverse=True)

    out.append("  Top 15:")
    out.append(f"  {'symbol':<15} {'n':>5} {'WR%':>7} {'PF':>7} {'pnl':>14}")
    for s, n, wr, pf, p in rows[:15]:
        out.append(f"  {s:<15} {n:>5} {wr:>6.2f}% {pf:>7.3f} ${p:>13,.2f}")

    out.append("\n  Bottom 15:")
    for s, n, wr, pf, p in rows[-15:]:
        out.append(f"  {s:<15} {n:>5} {wr:>6.2f}% {pf:>7.3f} ${p:>13,.2f}")
    out.append("")


def S12_monthly(trades, out):
    out.append("=" * 78)
    out.append("SECTION 12 — MONTHLY")
    out.append("=" * 78)
    by = defaultdict(list)
    for t in trades:
        m = str(t.get('entry_time', ''))[:7]
        if m:
            by[m].append(t)
    out.append(f"  {'month':<10} {'n':>5} {'WR%':>7} {'PF':>7} {'pnl':>14}")
    for m in sorted(by.keys()):
        grp = by[m]
        pnls = [_f(t.get('net_pnl')) for t in grp]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        wr = len(wins) / len(grp) * 100
        pf = sum(wins) / abs(sum(losses)) if losses else 0
        out.append(f"  {m:<10} {len(grp):>5} {wr:>6.2f}% {pf:>7.3f} "
                   f"${sum(pnls):>13,.2f}")
    out.append("")


def S13_exits(trades, out):
    out.append("=" * 78)
    out.append("SECTION 13 — EXIT REASON DISTRIBUTION")
    out.append("=" * 78)
    buckets = defaultdict(list)
    for t in trades:
        r = str(t.get('exit_reason', '?'))
        if "Emergency SL" in r:
            k = "Emergency SL"
        elif "Hard TP" in r:
            k = "Hard TP"
        elif "MaxHold" in r:
            k = "MaxHold"
        elif "EndOfData" in r:
            k = "EndOfData"
        elif "Apex" in r:
            k = "Apex"
        elif "Topo" in r:
            k = "Topo-Div"
        else:
            k = r[:25]
        buckets[k].append(t)
    n = len(trades)
    out.append(f"  {'reason':<25} {'n':>6} {'%':>7} {'avg_pnl':>11} "
               f"{'med_hold':>10}")
    for k in sorted(buckets.keys(), key=lambda x: -len(buckets[x])):
        grp = buckets[k]
        pnls = [_f(t.get('net_pnl')) for t in grp]
        holds = [_i(t.get('hold_bars', 0)) for t in grp]
        out.append(f"  {k:<25} {len(grp):>6} {len(grp)/n*100:>6.2f}% "
                   f"${_mean(pnls):>10,.2f} {_pct(holds, 50):>9.1f}")
    out.append("")


def S14_mfe(trades, out):
    out.append("=" * 78)
    out.append("SECTION 14 — MFE ANALYSIS")
    out.append("=" * 78)
    winners = [t for t in trades if _f(t.get('net_pnl')) > 0]
    losers = [t for t in trades if _f(t.get('net_pnl')) <= 0]

    def summ(grp, label):
        if not grp:
            return
        mfes = [_f(t.get('mfe_frac', 0)) * 100 for t in grp]
        out.append(f"\n  {label} (n={len(grp)})")
        for p in [10, 25, 50, 75, 90, 95]:
            out.append(f"    p{p:<2}  {_pct(mfes, p):>8.3f}%")
        out.append(f"    mean {_mean(mfes):>8.3f}%")
        for thr in [0.5, 1.0, 2.0, 3.0, 5.0]:
            c = sum(1 for m in mfes if m >= thr)
            out.append(f"    >= {thr}%: {c:>6} ({c/len(mfes)*100:>5.2f}%)")

    summ(winners, "Winners")
    summ(losers, "Losers")
    out.append("")


def S15_capital(trades, out):
    out.append("=" * 78)
    out.append("SECTION 15 — CAPITAL PROTECTION")
    out.append("=" * 78)
    caps = [_f(t.get('capital_after', 0)) for t in trades]
    if not caps:
        return
    cap0 = _f(trades[0].get('capital_before', 100))
    min_c = min(caps)
    out.append(f"  Start                   ${cap0:>12,.2f}")
    out.append(f"  Min reached             ${min_c:>12,.2f}")
    out.append(f"  Min/Start ratio         {min_c/cap0:>12.4f}")

    # how close to hypothetical CAPITAL_FLOOR
    for fl in [0.15, 5.0, 10.0]:
        ratio = min_c / fl if fl > 0 else 0
        flag = "⚠️  close" if min_c < fl * 2 else "ok"
        out.append(f"  vs floor ${fl:<5,.2f}          ratio={ratio:>6.2f}x  {flag}")
    out.append("")


def S16_worst_case(trades, out):
    """Additional worst-case analyses."""
    out.append("=" * 78)
    out.append("SECTION 16 — ADDITIONAL WORST-CASE STRESS")
    out.append("=" * 78)

    # 1) Capital fully lost scenarios
    pnls = [_f(t.get('net_pnl')) for t in trades]
    cap0 = _f(trades[0].get('capital_before', 100))

    # Find "ruin" if using different starting capitals
    out.append("  If starting with $1, $10, $50 instead of $100:")
    for start in [1, 10, 50, 100]:
        cur = start
        min_seen = start
        for p in pnls:
            # scale p by (start / cap0)
            cur += p * (start / cap0)
            min_seen = min(min_seen, cur)
        out.append(f"    Start ${start:>5}: min reached ${min_seen:>9,.4f} "
                   f"({'🔴 ruin' if min_seen <= 0 else 'ok'})")

    # 2) Max simultaneous notional (simplified: assume 5 slots)
    # We can't perfectly reconstruct but estimate max rolling notional
    out.append("\n  Rolling 5-trade notional exposure (upper-bound estimate):")
    notionals = [_trade_notional(t) for t in trades]
    if len(notionals) >= 5:
        rolling = []
        for i in range(len(notionals) - 4):
            rolling.append(sum(notionals[i:i+5]))
        out.append(f"    Max sum of 5 notionals  ${max(rolling):>12,.2f}")
        out.append(f"    Median sum of 5         ${_pct(rolling, 50):>12,.2f}")

    # 3) Max risk simultaneously
    risks = [_trade_risk(t) for t in trades]
    if len(risks) >= 5:
        rr = []
        for i in range(len(risks) - 4):
            rr.append(sum(risks[i:i+5]))
        out.append(f"    Max sum of 5 risks      ${max(rr):>12,.2f}")
        out.append(f"    Median sum of 5 risks   ${_pct(rr, 50):>12,.2f}")

    # 4) Largest consecutive drawdown %
    cap = cap0
    peak = cap0
    dd_series = []
    for p in pnls:
        cap += p
        peak = max(peak, cap)
        dd_series.append((peak - cap) / peak * 100 if peak > 0 else 0)
    if dd_series:
        out.append(f"\n  Largest peak-to-trough dd: {max(dd_series):.2f}%")

    # 5) Time from start to breakeven if starting bad
    cum = 0
    peak_cum = 0
    worst_dd_idx = 0
    worst_dd_val = 0
    for i, p in enumerate(pnls):
        cum += p
        if cum > peak_cum:
            peak_cum = cum
        dd = peak_cum - cum
        if dd > worst_dd_val:
            worst_dd_val = dd
            worst_dd_idx = i
    # find recovery
    recovery_idx = None
    cum2 = 0
    for i, p in enumerate(pnls):
        cum2 += p
        if i > worst_dd_idx and cum2 >= peak_cum:
            recovery_idx = i
            break
    out.append(f"  Worst peak-to-trough at index {worst_dd_idx}")
    if recovery_idx is not None:
        out.append(f"  Recovery at index {recovery_idx} "
                   f"(after {recovery_idx - worst_dd_idx} trades)")
    else:
        out.append("  ⚠️  No full recovery")
    out.append("")


def S17_warnings(cfg, trades, out):
    """Aggregate summary flags."""
    out.append("=" * 78)
    out.append("SECTION 17 — AUTOMATIC WARNINGS & FLAGS")
    out.append("=" * 78)
    flags = []

    # Config check
    if cfg:
        if cfg.get('TRAIL_ENABLED') is True:
            flags.append("TRAIL_ENABLED=True — causes premature exits on 4h")
        if cfg.get('SL_REF_KAPPA', 0) < 3.5:
            flags.append(f"SL_REF_KAPPA={cfg.get('SL_REF_KAPPA')} — likely too tight")
        if cfg.get('SL_WIDEN_MULT', 1) < 1.0:
            flags.append(f"SL_WIDEN_MULT={cfg.get('SL_WIDEN_MULT')} < 1")

    # SL distance
    sld = [_f(t.get('sl_dist_frac', 0)) for t in trades if _f(t.get('sl_dist_frac', 0)) > 0]
    if sld:
        tight_pct = sum(1 for x in sld if x < 0.005) / len(sld) * 100
        if tight_pct > 5:
            flags.append(f"{tight_pct:.1f}% of trades have SL < 0.5% — "
                         f"qty explosion risk")

    # Effective leverage
    levs = [_effective_leverage(t) for t in trades]
    levs = [x for x in levs if x > 0]
    if levs:
        over_50 = sum(1 for x in levs if x > 50) / len(levs) * 100
        over_100 = sum(1 for x in levs if x > 100) / len(levs) * 100
        if over_50 > 10:
            flags.append(f"{over_50:.1f}% of trades used effective lev > 50x")
        if over_100 > 1:
            flags.append(f"🔴 {over_100:.1f}% of trades used effective lev > 100x")

    # Drawdown
    caps = [_f(t.get('capital_after', 0)) for t in trades]
    if caps:
        cap0 = _f(trades[0].get('capital_before', 100))
        min_c = min(caps)
        dd = (cap0 - min_c) / cap0 * 100
        if dd > 50:
            flags.append(f"🔴 Max drawdown {dd:.1f}% — very high")

    # Streaks
    pnls = [_f(t.get('net_pnl')) for t in trades]
    mx = 0; cur = 0
    for p in pnls:
        if p < 0:
            cur += 1; mx = max(mx, cur)
        else:
            cur = 0
    if mx > 20:
        flags.append(f"Longest losing streak {mx} — severe")

    # Win/loss asymmetry
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    if wins and losses:
        payoff = _mean(wins) / abs(_mean(losses))
        wr = len(wins) / len(pnls)
        ev = wr * payoff - (1 - wr)
        if ev < 0.05:
            flags.append(f"⚠️  Expected value {ev:+.4f}R — extremely thin edge")

    if not flags:
        out.append("  ✅ No warnings triggered")
    else:
        for i, f in enumerate(flags, 1):
            out.append(f"  {i}. {f}")
    out.append("")


# ============================================================
# Main
# ============================================================

def main():
    out = []
    out.append("█" * 78)
    out.append("  COMPREHENSIVE BOT ANALYSIS")
    out.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    out.append("█" * 78)
    out.append("")

    cfg, err = extract_config()
    if err:
        out.append(f"⚠️  Config: {err}")
    else:
        out.append(f"✅ Extracted {len(cfg)} Config fields")
    out.append("")

    tf = "trades_log_backtest.jsonl"
    if not os.path.exists(tf):
        out.append(f"❌ {tf} not found")
        _dump(out, "analysis_report.txt")
        print(f"❌ {tf} missing")
        return

    trades, meta = load_trades(tf)
    out.append(f"✅ Loaded {len(trades)} trades from {tf}")
    out.append("")

    S1_config(cfg, meta, out)
    S2_overall(trades, out)
    S3_sl_dist(trades, out)
    S4_notional_leverage(trades, out)
    S5_risk_per_trade(trades, out)
    S6_streaks(trades, out)
    S7_starting_losses(trades, out)
    S8_directional(trades, out)
    S9_score(trades, out)
    S10_features(trades, out)
    S11_symbols(trades, out)
    S12_monthly(trades, out)
    S13_exits(trades, out)
    S14_mfe(trades, out)
    S15_capital(trades, out)
    S16_worst_case(trades, out)
    S17_warnings(cfg, trades, out)

    text = "\n".join(str(x) for x in out)
    _dump(out, "analysis_report.txt")
    print(text)
    print()
    print("✅ Report saved: analysis_report.txt")


def _dump(out, path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(str(x) for x in out))


if __name__ == "__main__":
    main()
