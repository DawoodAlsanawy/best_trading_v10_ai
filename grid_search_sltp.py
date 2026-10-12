#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Grid Search: SL_WIDEN_MULT × TP_MULT
=====================================
يُشغّل 25 تركيبة backtest ويُرتّبها.

الاستخدام:
  python grid_search_sltp.py                     # 90 يوم (دقيق، بطيء)
  python grid_search_sltp.py --fast              # 30 يوم (سريع)
  python grid_search_sltp.py --resume            # استئناف بعد الانقطاع
  python grid_search_sltp.py --report-only       # عرض النتائج فقط
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


# ═════════════════════════════════════════════════════════════════════
# الإعدادات
# ═════════════════════════════════════════════════════════════════════

SL_MULTS = [0.15, 0.30, 0.50, 1.00, 2.00]
TP_MULTS = [1.5, 2.0, 3.0, 5.0, 7.0]

DEFAULT_BOT = "trading_2_live2_1_sell.py"
RESULTS_DIR = "grid_results"
LOGS_DIR = os.path.join(RESULTS_DIR, "logs")
CACHE_FILE = os.path.join(RESULTS_DIR, "results.json")


def log(msg, level="INFO"):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def section(t):
    print(f"\n{'═' * 78}")
    print(f"  {t}")
    print(f"{'═' * 78}")


# ═════════════════════════════════════════════════════════════════════
# Parse metrics from log file
# ═════════════════════════════════════════════════════════════════════

_PATTERNS = {
    'mean_log_return':  r'متوسط\s*:\s*([+\-]?\d+\.\d+)',
    'median_log_return': r'وسيط\s*:\s*([+\-]?\d+\.\d+)',
    'std_log_return':   r'انحراف\s*:\s*(\d+\.\d+)',
    'n_trades':         r'عدد الصفقات\s*:\s*([\d,]+)',
    'buy_count':        r'شراء\s*/\s*بيع\s*:\s*([\d,]+)\s*/\s*([\d,]+)',
    'win_rate':         r'نسبة النجاح\s*:\s*(\d+\.\d+)%',
    'profit_factor':    r'عامل الربح.*?:\s*([\d.]+)',
    'sharpe':           r'شارب.*?:\s*([\-\d.]+)',
    'final_capital':    r'نهائي:\s*\$([\d,\.]+)',
    'total_return_pct': r'العائد الكلي\s*:\s*([\-\d,\.]+)%',
    'max_drawdown_pct': r'أقصى انخفاض\s*:\s*([\d.]+)%',
    'n_signals':        r'✔\s*([\d,]+)\s*إشارة',
    'signal_buy':       r'BUY=([\d,]+)\s*\|\s*SELL=([\d,]+)',
    'fill_info':        r'Entry fills:\s*(\d+)/(\d+)\s*\((\d+\.\d+)%\)',
    'hard_tp_count':    r'Hard TP\s*:\s*(\d+)',
    'emergency_sl':     r'Emergency SL\s*:\s*(\d+)',
}


def parse_log(text):
    """Extract key metrics from bot log."""
    m = {}
    for k, pat in _PATTERNS.items():
        match = re.search(pat, text)
        if not match:
            continue
        try:
            if k == 'buy_count':
                m['buy_count'] = int(match.group(1).replace(',', ''))
                m['sell_count'] = int(match.group(2).replace(',', ''))
            elif k == 'signal_buy':
                m['signal_buy'] = int(match.group(1).replace(',', ''))
                m['signal_sell'] = int(match.group(2).replace(',', ''))
            elif k == 'fill_info':
                m['fills'] = int(match.group(1))
                m['total_sigs'] = int(match.group(2))
                m['fill_pct'] = float(match.group(3))
            elif k == 'n_trades':
                m[k] = int(match.group(1).replace(',', ''))
            elif k == 'n_signals':
                m[k] = int(match.group(1).replace(',', ''))
            elif k == 'final_capital':
                m[k] = float(match.group(1).replace(',', ''))
            elif k == 'total_return_pct':
                m[k] = float(match.group(1).replace(',', ''))
            elif k in ('sharpe', 'mean_log_return', 'median_log_return',
                       'std_log_return', 'win_rate', 'profit_factor',
                       'max_drawdown_pct'):
                m[k] = float(match.group(1))
            elif k in ('hard_tp_count', 'emergency_sl'):
                m[k] = int(match.group(1))
        except (ValueError, IndexError):
            pass
    return m


# ═════════════════════════════════════════════════════════════════════
# Run one combination
# ═════════════════════════════════════════════════════════════════════

def run_one(bot_path, sl_mult, tp_mult, args):
    """Runs one combination. Returns dict or None on failure."""
    tag = f"sl{sl_mult:.2f}_tp{tp_mult:.1f}".replace('.', 'p')
    log_path = os.path.join(LOGS_DIR, f"{tag}.log")
    trade_log = os.path.join(LOGS_DIR, f"{tag}_trades.jsonl")

    # Remove old trade log to avoid append pollution
    if os.path.exists(trade_log):
        try:
            os.remove(trade_log)
        except Exception:
            pass

    cmd = [
        sys.executable, bot_path,
        "--mode", "backtest",
        "--capital", str(args.capital),
        "--timeframe", args.timeframe,
        "--history-days", str(args.days),
        "--nassets", str(args.nassets),
        "--no-trailing",
        "--no-apex",
        "--sl-widen-mult", str(sl_mult),
        "--tp-mult", str(tp_mult),
        "--partial-tp-r", str(tp_mult),  # partial = TP
        "--enable-sell",
        "--sell-gauge-pct", "100",
        "--no-fixed-price",
        "--trade-log", trade_log,
    ]

    t0 = time.time()
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            proc = subprocess.run(
                cmd, stdout=f, stderr=subprocess.STDOUT,
                timeout=args.timeout,
            )
        el = time.time() - t0
    except subprocess.TimeoutExpired:
        return {'status': 'TIMEOUT', 'elapsed': args.timeout, 'tag': tag}
    except Exception as e:
        return {'status': f'ERROR: {e}', 'elapsed': 0.0, 'tag': tag}

    if proc.returncode != 0:
        return {'status': f'EXIT_{proc.returncode}',
                'elapsed': el, 'tag': tag}

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return {'status': 'NO_LOG', 'elapsed': el, 'tag': tag}

    metrics = parse_log(text)
    if 'n_trades' not in metrics or metrics['n_trades'] == 0:
        return {'status': 'NO_TRADES', 'elapsed': el, 'tag': tag,
                'metrics': metrics}

    metrics['status'] = 'OK'
    metrics['elapsed'] = el
    metrics['tag'] = tag
    metrics['sl_mult'] = sl_mult
    metrics['tp_mult'] = tp_mult
    return metrics


# ═════════════════════════════════════════════════════════════════════
# Cache
# ═════════════════════════════════════════════════════════════════════

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache):
    try:
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cache, f, indent=2, default=str)
        os.replace(tmp, CACHE_FILE)
    except Exception as e:
        log(f"Cache save failed: {e}", level="WARN")


def cache_key(sl, tp):
    return f"{sl:.4f}_{tp:.4f}"


# ═════════════════════════════════════════════════════════════════════
# Report
# ═════════════════════════════════════════════════════════════════════

def print_report(cache):
    section("GRID RESULTS")

    rows = []
    for k, v in cache.items():
        if v.get('status') != 'OK':
            continue
        rows.append(v)
    if not rows:
        print("  No successful runs yet.")
        return

    # Sort by Sharpe
    rows.sort(key=lambda r: -r.get('sharpe', 0))

    print(f"\n  {'SL':>6} {'TP':>5} | {'N':>4} {'Win%':>6} "
          f"{'Sharpe':>8} {'E[lr]':>9} {'Ret%':>9} "
          f"{'MaxDD':>7} {'PF':>6} {'Fill%':>6}")
    print(f"  {'─' * 6} {'─' * 5} | {'─' * 4} {'─' * 6} "
          f"{'─' * 8} {'─' * 9} {'─' * 9} "
          f"{'─' * 7} {'─' * 6} {'─' * 6}")

    for r in rows:
        n = r.get('n_trades', 0)
        wr = r.get('win_rate', 0)
        sh = r.get('sharpe', 0)
        elr = r.get('mean_log_return', 0)
        ret = r.get('total_return_pct', 0)
        dd = r.get('max_drawdown_pct', 0)
        pf = r.get('profit_factor', 0)
        fill = r.get('fill_pct', 0)
        print(f"  {r['sl_mult']:>6.2f} {r['tp_mult']:>5.1f} | "
              f"{n:>4} {wr:>5.1f}% {sh:>8.3f} {elr:>+9.6f} "
              f"{ret:>+8.1f}% {dd:>6.2f}% {pf:>5.2f} {fill:>5.1f}%")

    # Best by different metrics
    print(f"\n  ── Best by Sharpe ──")
    b = max(rows, key=lambda r: r.get('sharpe', 0))
    print(f"    SL={b['sl_mult']:.2f} TP={b['tp_mult']:.1f}  "
          f"Sharpe={b['sharpe']:.3f}  "
          f"Return={b['total_return_pct']:+.1f}%  "
          f"DD={b['max_drawdown_pct']:.2f}%  "
          f"N={b['n_trades']}")

    print(f"  ── Best by E[log_return] ──")
    b = max(rows, key=lambda r: r.get('mean_log_return', 0))
    print(f"    SL={b['sl_mult']:.2f} TP={b['tp_mult']:.1f}  "
          f"E[lr]={b['mean_log_return']:+.6f}  "
          f"Sharpe={b['sharpe']:.3f}  "
          f"Return={b['total_return_pct']:+.1f}%")

    print(f"  ── Best by Total Return ──")
    b = max(rows, key=lambda r: r.get('total_return_pct', 0))
    print(f"    SL={b['sl_mult']:.2f} TP={b['tp_mult']:.1f}  "
          f"Return={b['total_return_pct']:+.1f}%  "
          f"Sharpe={b['sharpe']:.3f}  "
          f"DD={b['max_drawdown_pct']:.2f}%")

    print(f"  ── Best Risk-Adjusted (Sharpe / DD) ──")
    def _sharpe_over_dd(r):
        dd = max(r.get('max_drawdown_pct', 0.1), 0.1)
        return r.get('sharpe', 0) / dd
    b = max(rows, key=_sharpe_over_dd)
    print(f"    SL={b['sl_mult']:.2f} TP={b['tp_mult']:.1f}  "
          f"Sharpe={b['sharpe']:.3f}  DD={b['max_drawdown_pct']:.2f}%  "
          f"ratio={_sharpe_over_dd(b):.3f}")

    # SL summary
    print(f"\n  ── Average by SL_WIDEN_MULT ──")
    print(f"  {'SL':>6} {'avg_Sharpe':>12} {'avg_Return%':>13} "
          f"{'avg_DD%':>10} {'avg_N':>7}")
    by_sl = {}
    for r in rows:
        by_sl.setdefault(r['sl_mult'], []).append(r)
    for sl in sorted(by_sl.keys()):
        sub = by_sl[sl]
        print(f"  {sl:>6.2f} "
              f"{sum(x['sharpe'] for x in sub)/len(sub):>12.3f} "
              f"{sum(x['total_return_pct'] for x in sub)/len(sub):>+12.1f}% "
              f"{sum(x['max_drawdown_pct'] for x in sub)/len(sub):>9.2f}% "
              f"{sum(x['n_trades'] for x in sub)/len(sub):>7.1f}")

    # TP summary
    print(f"\n  ── Average by TP_MULT ──")
    print(f"  {'TP':>6} {'avg_Sharpe':>12} {'avg_Return%':>13} "
          f"{'avg_DD%':>10} {'avg_N':>7}")
    by_tp = {}
    for r in rows:
        by_tp.setdefault(r['tp_mult'], []).append(r)
    for tp in sorted(by_tp.keys()):
        sub = by_tp[tp]
        print(f"  {tp:>6.1f} "
              f"{sum(x['sharpe'] for x in sub)/len(sub):>12.3f} "
              f"{sum(x['total_return_pct'] for x in sub)/len(sub):>+12.1f}% "
              f"{sum(x['max_drawdown_pct'] for x in sub)/len(sub):>9.2f}% "
              f"{sum(x['n_trades'] for x in sub)/len(sub):>7.1f}")

    # Failures
    fails = [v for v in cache.values() if v.get('status') != 'OK']
    if fails:
        print(f"\n  ── Failed runs: {len(fails)} ──")
        for f in fails:
            print(f"    {f.get('tag', '?')}: {f.get('status')}")


# ═════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bot", default=DEFAULT_BOT)
    p.add_argument("--capital", type=float, default=2.0)
    p.add_argument("--timeframe", default="4h")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--nassets", type=int, default=50)
    p.add_argument("--timeout", type=int, default=600,
                   help="timeout per run (sec)")
    p.add_argument("--fast", action="store_true",
                   help="use 30 days instead of 90")
    p.add_argument("--resume", action="store_true",
                   help="skip already-completed runs")
    p.add_argument("--report-only", action="store_true")
    p.add_argument("--force", action="store_true",
                   help="rerun all, ignore cache")
    p.add_argument("--sl-mults", type=str, default=None,
                   help="comma-separated, override defaults")
    p.add_argument("--tp-mults", type=str, default=None,
                   help="comma-separated, override defaults")
    args = p.parse_args()

    if args.fast:
        args.days = 30
    if args.sl_mults:
        sl_mults = [float(x) for x in args.sl_mults.split(",")]
    else:
        sl_mults = SL_MULTS
    if args.tp_mults:
        tp_mults = [float(x) for x in args.tp_mults.split(",")]
    else:
        tp_mults = TP_MULTS

    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    # Bot existence
    if not os.path.exists(args.bot):
        log(f"Bot not found: {args.bot}", level="ERROR")
        return 1

    section("CONFIG")
    print(f"  bot:        {args.bot}")
    print(f"  capital:    ${args.capital}")
    print(f"  timeframe:  {args.timeframe}")
    print(f"  days:       {args.days}")
    print(f"  nassets:    {args.nassets}")
    print(f"  SL mults:   {sl_mults}")
    print(f"  TP mults:   {tp_mults}")
    print(f"  combinations: {len(sl_mults) * len(tp_mults)}")

    if args.report_only:
        print_report(load_cache())
        return 0

    cache = load_cache() if (args.resume and not args.force) else {}

    combos = [(sl, tp) for sl in sl_mults for tp in tp_mults]
    total = len(combos)
    n_done = 0
    n_ok = 0
    n_fail = 0
    t_start = time.time()

    for i, (sl, tp) in enumerate(combos, 1):
        key = cache_key(sl, tp)
        if args.resume and key in cache and not args.force:
            st = cache[key].get('status', '?')
            if st == 'OK':
                n_ok += 1
            else:
                n_fail += 1
            log(f"  [{i:>2}/{total}] SL={sl:.2f} TP={tp:.1f} "
                f"— SKIP (cached: {st})")
            continue

        el_total = time.time() - t_start
        eta = (el_total / max(i - 1, 1)) * (total - i + 1) if i > 1 else 0
        log(f"  [{i:>2}/{total}] SL={sl:.2f} TP={tp:.1f} "
            f"(ETA≈{eta/60:.1f}m)")

        res = run_one(args.bot, sl, tp, args)
        cache[key] = res
        save_cache(cache)

        if res.get('status') == 'OK':
            n_ok += 1
            el = res.get('elapsed', 0)
            log(f"    ✓ N={res.get('n_trades', 0)} "
                f"Sharpe={res.get('sharpe', 0):.3f} "
                f"Return={res.get('total_return_pct', 0):+.1f}% "
                f"DD={res.get('max_drawdown_pct', 0):.2f}%  "
                f"({el:.0f}s)")
        else:
            n_fail += 1
            log(f"    ✗ {res.get('status')}", level="WARN")
        n_done += 1

    el_total = time.time() - t_start
    section("SUMMARY")
    print(f"  Done:        {n_done}/{total}")
    print(f"  Success:     {n_ok}")
    print(f"  Failed:      {n_fail}")
    print(f"  Elapsed:     {el_total/60:.1f} min")
    print(f"  Cache:       {CACHE_FILE}")
    print(f"  Logs:        {LOGS_DIR}/")

    print_report(cache)

    return 0


if __name__ == "__main__":
    sys.exit(main())
