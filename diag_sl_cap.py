#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SL Cap Diagnostic
==================
يقرأ ملف trade log (JSONL) ويحلل:
  1. كم صفقة فيها %-cap قصّت SL؟
  2. نسبة الفوز للصفقات المقطوعة vs غير المقطوعة
  3. هل σ_bar يشرح الفشل أم cap نفسه؟
  4. توصية عملية: هل إزالة cap ستحسّن؟

الاستخدام:
  python diag_sl_cap.py --log trades_log_backtest.jsonl
  python diag_sl_cap.py --log trades_log_backtest.jsonl --widen-mult 0.15
"""

import argparse
import json
import os
import sys
from collections import defaultdict
import numpy as np


def log(msg, level="INFO"):
    print(f"[{level}] {msg}", flush=True)


def section(t):
    print(f"\n{'═' * 78}")
    print(f"  {t}")
    print(f"{'═' * 78}")


def load_trades(path):
    """يقرأ ملف JSONL، يعيد (meta, trades)."""
    if not os.path.exists(path):
        log(f"Not found: {path}", level="ERROR")
        return None, []

    meta = {}
    trades = []
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
                meta.update(rec)
            else:
                trades.append(rec)
    return meta, trades


def pct(x):
    return f"{x*100:.2f}%"


def mean(xs):
    return float(np.mean(xs)) if xs else 0.0


def median(xs):
    return float(np.median(xs)) if xs else 0.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--log", required=True)
    p.add_argument("--widen-mult", type=float, default=0.15,
                   help="SL_WIDEN_MULT used in the run (default 0.15)")
    p.add_argument("--widen-base", type=float, default=0.015,
                   help="base max_sl_frac (default 0.015)")
    p.add_argument("--out", default="sl_cap_report.txt")
    args = p.parse_args()

    meta, trades = load_trades(args.log)
    if not trades:
        log("No trades found", level="ERROR")
        return 1

    section("FILE INFO")
    print(f"  log:            {args.log}")
    print(f"  mode:           {meta.get('mode', '?')}")
    print(f"  timeframe:      {meta.get('timeframe', '?')}")
    print(f"  n_trades:       {len(trades)}")
    print(f"  N={meta.get('N', '?')} W={meta.get('W', '?')} L={meta.get('L', '?')}")
    print(f"  K_MIN={meta.get('K_MIN', '?')} K_MAX={meta.get('K_MAX', '?')}")

    # ═══════════════════════════════════════════════════════════════
    # Compute per-trade: cap, σ, clipping
    # ═══════════════════════════════════════════════════════════════
    max_sl_frac = args.widen_base * args.widen_mult
    log(f"  max_sl_frac (cap) = {args.widen_base} × {args.widen_mult} "
        f"= {max_sl_frac:.6f} ({pct(max_sl_frac)})")

    enriched = []
    for t in trades:
        try:
            sig_px = float(t.get("signal_price") or 0)
            sig_sl = float(t.get("signal_sl") or 0)
            entry_px = float(t.get("entry_price") or 0)
            sl_d_used = float(t.get("sl_dist_initial") or 0)
            E_therm = float(t.get("E_therm") or 0)
            if sig_px <= 0 or entry_px <= 0:
                continue

            design_sl_orig = abs(sig_px - sig_sl)
            cap_value = entry_px * max_sl_frac
            sigma_price = E_therm * entry_px if E_therm > 1e-9 else 0.0

            # classify
            clipped = False
            clip_ratio = 1.0
            if design_sl_orig > 1e-12:
                clip_ratio = sl_d_used / design_sl_orig
                if clip_ratio < 0.99:  # 1% tolerance
                    clipped = True

            sl_in_sigma = (design_sl_orig / sigma_price
                           if sigma_price > 1e-12 else 0.0)
            sl_used_in_sigma = (sl_d_used / sigma_price
                                if sigma_price > 1e-12 else 0.0)
            cap_in_sigma = (cap_value / sigma_price
                            if sigma_price > 1e-12 else 0.0)

            enriched.append({
                'symbol': t.get('symbol', '?'),
                'action': t.get('action', '?'),
                'exit_reason': t.get('exit_reason', '?'),
                'is_win': bool(t.get('is_win', False)),
                'net_pnl': float(t.get('net_pnl') or 0),
                'entry_px': entry_px,
                'sig_px': sig_px,
                'design_sl_orig': design_sl_orig,
                'sl_d_used': sl_d_used,
                'cap_value': cap_value,
                'sigma_price': sigma_price,
                'E_therm': E_therm,
                'clipped': clipped,
                'clip_ratio': clip_ratio,
                'sl_in_sigma': sl_in_sigma,
                'sl_used_in_sigma': sl_used_in_sigma,
                'cap_in_sigma': cap_in_sigma,
            })
        except Exception as e:
            log(f"  skip bad trade: {e}", level="WARN")

    if not enriched:
        log("No valid trades after enrichment", level="ERROR")
        return 1

    N = len(enriched)

    # ═══════════════════════════════════════════════════════════════
    # Overall stats
    # ═══════════════════════════════════════════════════════════════
    section("OVERALL")
    all_win = sum(1 for e in enriched if e['is_win'])
    print(f"  N trades:          {N}")
    print(f"  Win rate:          {pct(all_win/N)}")
    print(f"  Total net PnL:     ${sum(e['net_pnl'] for e in enriched):+.4f}")

    # Exit distribution
    exits = defaultdict(int)
    for e in enriched:
        k = e['exit_reason'].split('(')[0].split('=')[0].strip()
        exits[k] += 1
    print(f"\n  Exit distribution:")
    for k, v in sorted(exits.items(), key=lambda x: -x[1]):
        print(f"    {k:<25s} {v:>5}  ({pct(v/N)})")

    # ═══════════════════════════════════════════════════════════════
    # Clipping analysis
    # ═══════════════════════════════════════════════════════════════
    section("CLIPPING ANALYSIS")
    clipped = [e for e in enriched if e['clipped']]
    not_clipped = [e for e in enriched if not e['clipped']]

    print(f"  Clipped:      {len(clipped):>5} / {N} "
          f"({pct(len(clipped)/N)})")
    print(f"  Not clipped:  {len(not_clipped):>5} / {N} "
          f"({pct(len(not_clipped)/N)})")

    if clipped:
        wr_c = sum(1 for e in clipped if e['is_win']) / len(clipped)
        pnl_c = sum(e['net_pnl'] for e in clipped)
        avg_ratio = mean([e['clip_ratio'] for e in clipped])
        print(f"\n  ── Clipped trades ──")
        print(f"  Win rate:          {pct(wr_c)}")
        print(f"  Total PnL:         ${pnl_c:+.4f}")
        print(f"  Avg clip ratio:    {avg_ratio:.3f}  "
              f"(1.0 = no clip, 0.5 = half)"
        )
        print(f"  Median clip ratio: {median([e['clip_ratio'] for e in clipped]):.3f}")

    if not_clipped:
        wr_nc = sum(1 for e in not_clipped if e['is_win']) / len(not_clipped)
        pnl_nc = sum(e['net_pnl'] for e in not_clipped)
        print(f"\n  ── Not clipped trades ──")
        print(f"  Win rate:          {pct(wr_nc)}")
        print(f"  Total PnL:         ${pnl_nc:+.4f}")

    if clipped and not_clipped:
        diff = wr_c - wr_nc
        print(f"\n  Δ win rate (clipped − not_clipped): "
              f"{pct(diff)}")
        if diff < -0.05:
            print(f"  ✗ STRONG NEGATIVE: clipping hurts win rate by "
                  f"{abs(diff)*100:.1f}pp")
        elif diff < -0.02:
            print(f"  ⚠ MODERATE: clipped slightly worse")
        else:
            print(f"  ~ No significant difference")

    # ═══════════════════════════════════════════════════════════════
    # σ distribution
    # ═══════════════════════════════════════════════════════════════
    section("SIGMA-BASED ANALYSIS")

    sigmas = [e['E_therm'] for e in enriched if e['E_therm'] > 0]
    if sigmas:
        print(f"  E_therm (σ):")
        print(f"    min:    {pct(min(sigmas))}")
        print(f"    median: {pct(median(sigmas))}")
        print(f"    mean:   {pct(mean(sigmas))}")
        print(f"    max:    {pct(max(sigmas))}")

    # How much is cap relative to σ?
    cap_vs_sigma = [e['cap_in_sigma'] for e in enriched
                    if e['cap_in_sigma'] > 0]
    if cap_vs_sigma:
        print(f"\n  Cap / σ_price  (higher = more room, lower = tighter)")
        print(f"    min:    {min(cap_vs_sigma):.2f}σ")
        print(f"    median: {median(cap_vs_sigma):.2f}σ")
        print(f"    mean:   {mean(cap_vs_sigma):.2f}σ")
        print(f"    max:    {max(cap_vs_sigma):.2f}σ")

        # Bucket analysis
        print(f"\n  By cap_in_sigma bucket:")
        buckets = [
            (0, 1, "cap < 1σ"),
            (1, 2, "1σ ≤ cap < 2σ"),
            (2, 3, "2σ ≤ cap < 3σ"),
            (3, 5, "3σ ≤ cap < 5σ"),
            (5, 1e9, "cap ≥ 5σ"),
        ]
        for lo, hi, label in buckets:
            sub = [e for e in enriched
                   if lo <= e['cap_in_sigma'] < hi]
            if not sub:
                continue
            wr = sum(1 for e in sub if e['is_win']) / len(sub)
            clipped_pct = sum(1 for e in sub if e['clipped']) / len(sub)
            print(f"    {label:<16s} n={len(sub):>4}  "
                  f"win={pct(wr):>7s}  "
                  f"clipped={pct(clipped_pct):>7s}")

    # ═══════════════════════════════════════════════════════════════
    # Original design SL in σ units
    # ═══════════════════════════════════════════════════════════════
    section("ORIGINAL DESIGN SL (σ units)")

    ds = [e['sl_in_sigma'] for e in enriched if e['sl_in_sigma'] > 0]
    if ds:
        print(f"  Design SL / σ_price:")
        print(f"    min:    {min(ds):.2f}σ")
        print(f"    median: {median(ds):.2f}σ")
        print(f"    mean:   {mean(ds):.2f}σ")
        print(f"    max:    {max(ds):.2f}σ")
        print(f"  (typical target: 0.8-3.0σ)")

    # ═══════════════════════════════════════════════════════════════
    # Per-symbol breakdown
    # ═══════════════════════════════════════════════════════════════
    section("PER-SYMBOL BREAKDOWN")

    by_sym = defaultdict(list)
    for e in enriched:
        by_sym[e['symbol']].append(e)

    print(f"  {'symbol':<15} {'n':>4} {'win%':>7} {'clipped':>8} "
          f"{'σ_med%':>8} {'cap/σ':>7}")
    for sym in sorted(by_sym.keys()):
        sub = by_sym[sym]
        wr = sum(1 for e in sub if e['is_win']) / len(sub)
        cl = sum(1 for e in sub if e['clipped']) / len(sub)
        sig_med = median([e['E_therm'] for e in sub
                          if e['E_therm'] > 0])
        cs = median([e['cap_in_sigma'] for e in sub
                     if e['cap_in_sigma'] > 0])
        print(f"  {sym:<15} {len(sub):>4} {pct(wr):>7s} "
              f"{pct(cl):>8s} {pct(sig_med):>8s} {cs:>7.2f}")

    # ═══════════════════════════════════════════════════════════════
    # Clipping severity
    # ═══════════════════════════════════════════════════════════════
    section("CLIP SEVERITY")

    if clipped:
        ratios = [e['clip_ratio'] for e in clipped]
        print(f"  Distribution of clip_ratio (sl_used / design_sl):")
        for label, cond in [
            ("ratio ≤ 0.10", lambda r: r <= 0.10),
            ("0.10 < ratio ≤ 0.25", lambda r: 0.10 < r <= 0.25),
            ("0.25 < ratio ≤ 0.50", lambda r: 0.25 < r <= 0.50),
            ("0.50 < ratio ≤ 0.75", lambda r: 0.50 < r <= 0.75),
            ("0.75 < ratio < 0.99", lambda r: 0.75 < r < 0.99),
        ]:
            n = sum(1 for r in ratios if cond(r))
            p = n / len(ratios)
            print(f"    {label:<24s} {n:>4}  ({pct(p)})")

        # For severe clips, what's the win rate?
        severe = [e for e in clipped if e['clip_ratio'] <= 0.25]
        mild = [e for e in clipped if e['clip_ratio'] > 0.50]
        if severe:
            wr_s = sum(1 for e in severe if e['is_win']) / len(severe)
            print(f"\n  Severe clip (ratio ≤ 0.25): n={len(severe)}  "
                  f"win={pct(wr_s)}")
        if mild:
            wr_m = sum(1 for e in mild if e['is_win']) / len(mild)
            print(f"  Mild clip (ratio > 0.50):   n={len(mild)}  "
                  f"win={pct(wr_m)}")

    # ═══════════════════════════════════════════════════════════════
    # VERDICT
    # ═══════════════════════════════════════════════════════════════
    section("VERDICT")

    clipped_pct = len(clipped) / N
    if clipped_pct < 0.05:
        print(f"  ✓ Only {pct(clipped_pct)} of trades were clipped.")
        print(f"    → %-cap is NOT the bottleneck.")
        print(f"    → Focus elsewhere.")
    elif clipped_pct < 0.20:
        print(f"  ⚠ {pct(clipped_pct)} of trades were clipped.")
        print(f"    → %-cap has moderate impact.")
        print(f"    → Consider replacing with adaptive cap.")
    else:
        print(f"  ✗✗ {pct(clipped_pct)} of trades were clipped.")
        print(f"    → %-cap is a MAJOR bottleneck.")
        print(f"    → Replacing it should improve results.")
        if clipped and not_clipped:
            wr_c = sum(1 for e in clipped if e['is_win']) / len(clipped)
            wr_nc = sum(1 for e in not_clipped if e['is_win']) / len(not_clipped)
            if wr_c < wr_nc - 0.05:
                print(f"    → Clipped win rate {pct(wr_c)} vs "
                      f"non-clipped {pct(wr_nc)}")
                print(f"    → Confirms: cap is hurting performance.")

    # Write report
    try:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(f"SL Cap Diagnostic Report\n")
            f.write(f"=========================\n")
            f.write(f"Log: {args.log}\n")
            f.write(f"N:   {N}\n")
            f.write(f"Cap: {pct(max_sl_frac)}\n")
            f.write(f"Clipped: {len(clipped)} ({pct(clipped_pct)})\n")
            f.write(f"Win rate overall: {pct(all_win/N)}\n")
        log(f"Report saved: {args.out}")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
