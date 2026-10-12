#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final Validation Test
========================
يقارن نسختين بأمر واحد:
  1. Original (BUY-only)  ← trading_2_live2_1.py
  2. SELL-enabled         ← trading_2_live2_1_sell.py
بإعدادات الحافة القصوى:
  --no-trailing --history-days 365 --tp-mult 7
  --sl-widen-mult 0.8 --no-apex --partial-tp-r 3.5
"""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path


# الألوان
class C:
    R = '\033[0m'
    G = '\033[92m'
    Y = '\033[93m'
    B = '\033[94m'
    RED = '\033[91m'
    BOLD = '\033[1m'


def log(msg, level="INFO"):
    ts = time.strftime("%H:%M:%S")
    colors = {
        "INFO": C.B, "OK": C.G, "WARN": C.Y, "ERROR": C.RED,
    }
    color = colors.get(level, "")
    print(f"[{ts}] {color}[{level}]{C.R} {msg}", flush=True)


def section(title):
    print(f"\n{C.BOLD}{'═' * 78}{C.R}")
    print(f"{C.BOLD}  {title}{C.R}")
    print(f"{C.BOLD}{'═' * 78}{C.R}")


def check_file(path):
    if not os.path.exists(path):
        return False
    return True


def parse_metrics(output_text):
    """
    يستخرج المقاييس الرئيسية من مخرجات البوت.
    """
    metrics = {}

    # متوسط log return
    m = re.search(r'متوسط\s*:\s*([+\-]?\d+\.\d+)', output_text)
    if m:
        metrics['mean_log_return'] = float(m.group(1))

    # عدد الصفقات
    m = re.search(r'عدد الصفقات\s*:\s*([\d,]+)', output_text)
    if m:
        metrics['n_trades'] = int(m.group(1).replace(',', ''))

    # شراء / بيع
    m = re.search(r'شراء\s*/\s*بيع\s*:\s*([\d,]+)\s*/\s*([\d,]+)',
                  output_text)
    if m:
        metrics['buy_count'] = int(m.group(1).replace(',', ''))
        metrics['sell_count'] = int(m.group(2).replace(',', ''))

    # نسبة النجاح
    m = re.search(r'نسبة النجاح\s*:\s*([\d.]+)%', output_text)
    if m:
        metrics['win_rate'] = float(m.group(1))

    # PF
    m = re.search(r'عامل الربح.*?:\s*([\d.]+)', output_text)
    if m:
        metrics['profit_factor'] = float(m.group(1))

    # Sharpe
    m = re.search(r'شارب.*?:\s*([\-\d.]+)', output_text)
    if m:
        metrics['sharpe'] = float(m.group(1))

    # رأس المال النهائي
    m = re.search(r'نهائي:\s*\$([\d,\.]+)', output_text)
    if m:
        metrics['final_capital'] = float(m.group(1).replace(',', ''))

    # العائد الكلي
    m = re.search(r'العائد الكلي\s*:\s*([\-\d,\.]+)%', output_text)
    if m:
        metrics['total_return_pct'] = float(m.group(1).replace(',', ''))

    # Max DD
    m = re.search(r'أقصى انخفاض\s*:\s*([\d.]+)%', output_text)
    if m:
        metrics['max_drawdown_pct'] = float(m.group(1))

    # عدد الإشارات (قبل الفلترة)
    m = re.search(r'✔\s*([\d,]+)\s*إشارة', output_text)
    if m:
        metrics['n_signals'] = int(m.group(1).replace(',', ''))

    # BUY/SELL في الإشارات
    m = re.search(r'BUY=([\d,]+)\s*\|\s*SELL=([\d,]+)', output_text)
    if m:
        metrics['signal_buy'] = int(m.group(1).replace(',', ''))
        metrics['signal_sell'] = int(m.group(2).replace(',', ''))

    # Fill rate
    m = re.search(r'Entry fills:\s*([\d,]+)/([\d,]+)\s*\(([\d.]+)%\)',
                  output_text)
    if m:
        metrics['fills'] = int(m.group(1).replace(',', ''))
        metrics['total_sigs'] = int(m.group(2).replace(',', ''))
        metrics['fill_pct'] = float(m.group(3))

    return metrics


def run_backtest(script, args, label, log_path):
    section(f"Running: {label}")
    cmd = [sys.executable, script] + args

    log(f"CMD: {' '.join(cmd)}")
    log(f"Log: {log_path}")

    t0 = time.time()
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            proc = subprocess.run(
                cmd, stdout=f, stderr=subprocess.STDOUT,
                cwd=os.path.dirname(os.path.abspath(script)),
                timeout=1800,
            )
    except subprocess.TimeoutExpired:
        log(f"Timeout after 30 min", level="ERROR")
        return None, ""
    except Exception as e:
        log(f"Failed: {e}", level="ERROR")
        return None, ""

    elapsed = time.time() - t0
    log(f"Completed in {elapsed:.1f}s, exit code={proc.returncode}",
        level="OK" if proc.returncode == 0 else "ERROR")

    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        text = ""

    return proc.returncode, text


def print_comparison(m_buy, m_sell):
    section("SIDE-BY-SIDE COMPARISON")

    fields = [
        ('n_signals',    'إشارات قبل الفلترة',  '{:,}'),
        ('signal_buy',   '  BUY signals',     '{:,}'),
        ('signal_sell',  '  SELL signals',    '{:,}'),
        ('n_trades',     'صفقات مُنفَّذة',      '{:,}'),
        ('buy_count',    '  BUY trades',      '{:,}'),
        ('sell_count',   '  SELL trades',     '{:,}'),
        ('win_rate',     'Win rate',          '{:.2f}%'),
        ('profit_factor', 'Profit factor',    '{:.3f}'),
        ('sharpe',       'Sharpe',            '{:.3f}'),
        ('mean_log_return', 'Mean log ret',   '{:+.6f}'),
        ('max_drawdown_pct', 'Max DD',        '{:.2f}%'),
        ('total_return_pct', 'Total return',  '{:+.1f}%'),
        ('final_capital', 'Final capital',    '${:,.2f}'),
    ]

    print(f"  {C.BOLD}{'Metric':<28} {'BUY-only':>16} "
          f"{'BUY+SELL':>16} {'Δ':>12}{C.R}")
    print(f"  {'─' * 74}")

    for key, label, fmt in fields:
        v_buy = m_buy.get(key)
        v_sell = m_sell.get(key)

        def f(v):
            if v is None:
                return "—"
            try:
                return fmt.format(v)
            except Exception:
                return str(v)

        delta = ""
        try:
            if isinstance(v_buy, (int, float)) and \
               isinstance(v_sell, (int, float)):
                d = v_sell - v_buy
                if key in ('mean_log_return',):
                    delta = f"{d:+.6f}"
                elif key in ('win_rate', 'max_drawdown_pct',
                             'total_return_pct'):
                    delta = f"{d:+.2f}%"
                elif key in ('sharpe', 'profit_factor'):
                    delta = f"{d:+.3f}"
                elif key == 'final_capital':
                    delta = f"${d:+,.2f}"
                else:
                    delta = f"{d:+,.0f}"

                # لون
                if key in ('max_drawdown_pct',):
                    color = C.G if d < 0 else C.RED
                else:
                    color = C.G if d > 0 else (C.RED if d < 0 else '')
                delta = f"{color}{delta}{C.R}"
        except Exception:
            delta = ""

        print(f"  {label:<28} {f(v_buy):>16} {f(v_sell):>16} "
              f"{delta:>12}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--history-days", type=int, default=365)
    ap.add_argument("--timeframe", default="1h")
    ap.add_argument("--nassets", type=int, default=20)
    ap.add_argument("--maxcon", type=int, default=3)
    ap.add_argument("--run-buy-only", action="store_true", default=True,
                    help="Run original BUY-only for comparison")
    ap.add_argument("--run-sell", action="store_true", default=True,
                    help="Run SELL-enabled version")
    ap.add_argument("--tp-mult", type=float, default=7.0)
    ap.add_argument("--sl-widen-mult", type=float, default=0.8)
    ap.add_argument("--partial-tp-r", type=float, default=3.5)
    ap.add_argument("--out-dir", default="final_test_results")
    args = ap.parse_args()

    # تحقق من الملفات
    base_dir = Path(__file__).parent
    buy_script = base_dir / "trading_2_live2_1.py"
    sell_script = base_dir / "trading_2_live2_1_sell.py"

    if args.run_buy_only and not check_file(str(buy_script)):
        log(f"Not found: {buy_script}", level="ERROR")
        return 1
    if args.run_sell and not check_file(str(sell_script)):
        log(f"Not found: {sell_script}", level="ERROR")
        log("Create it with: python make_sell_version.py --filter tinfo_or_gf",
            level="WARN")
        return 1

    # أنشئ مجلد النتائج
    os.makedirs(args.out_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    # ═══════════════════════════════════════════════════════════
    # الأوامر المشتركة
    # ═══════════════════════════════════════════════════════════
    common_args = [
        "--mode", "backtest",
        "--capital", str(int(args.capital)),
        "--timeframe", args.timeframe,
        "--history-days", str(args.history_days),
        "--nassets", str(args.nassets),
        "--maxcon", str(args.maxcon),
        "--no-trailing",
        "--tp-mult", str(args.tp_mult),
        "--sl-widen-mult", str(args.sl_widen_mult),
        "--no-apex",
        "--partial-tp-r", str(args.partial_tp_r),
    ]

    section("Configuration")
    print(f"  Capital:        ${args.capital:.0f}")
    print(f"  History:        {args.history_days} days")
    print(f"  Timeframe:      {args.timeframe}")
    print(f"  N assets:       {args.nassets}")
    print(f"  Max concurrent: {args.maxcon}")
    print(f"  TP_MULT:        {args.tp_mult}")
    print(f"  SL_WIDEN_MULT:  {args.sl_widen_mult}")
    print(f"  PARTIAL_TP_R:   {args.partial_tp_r}")
    print(f"  Trailing:       OFF")
    print(f"  Apex:           OFF")
    print(f"  Output dir:     {args.out_dir}")

    m_buy, m_sell = None, None

    # ═══════════════════════════════════════════════════════════
    # Run 1: BUY-only (original)
    # ═══════════════════════════════════════════════════════════
    if args.run_buy_only:
        log_buy = os.path.join(args.out_dir, f"buy_only_{ts}.log")
        rc, text = run_backtest(
            str(buy_script),
            common_args + ["--disable-sell"] if False else common_args,
            "BUY-only (original)",
            log_buy,
        )
        if text:
            m_buy = parse_metrics(text)
            log(f"Extracted {len(m_buy)} metrics", level="OK")
            # اطبع ملخص سريع
            if m_buy.get('n_trades'):
                print(f"  → Trades: {m_buy.get('n_trades')}  "
                      f"Win: {m_buy.get('win_rate', 0):.1f}%  "
                      f"Sharpe: {m_buy.get('sharpe', 0):.2f}  "
                      f"Final: ${m_buy.get('final_capital', 0):.2f}")

    # ═══════════════════════════════════════════════════════════
    # Run 2: SELL-enabled
    # ═══════════════════════════════════════════════════════════
    if args.run_sell:
        log_sell = os.path.join(args.out_dir, f"sell_enabled_{ts}.log")
        rc, text = run_backtest(
            str(sell_script),
            common_args,
            "BUY+SELL (validated filter)",
            log_sell,
        )
        if text:
            m_sell = parse_metrics(text)
            log(f"Extracted {len(m_sell)} metrics", level="OK")
            if m_sell.get('n_trades'):
                print(f"  → Trades: {m_sell.get('n_trades')}  "
                      f"Win: {m_sell.get('win_rate', 0):.1f}%  "
                      f"Sharpe: {m_sell.get('sharpe', 0):.2f}  "
                      f"Final: ${m_sell.get('final_capital', 0):.2f}")

    # ═══════════════════════════════════════════════════════════
    # Comparison
    # ═══════════════════════════════════════════════════════════
    if m_buy and m_sell:
        print_comparison(m_buy, m_sell)

        section("VERDICT")
        ret_buy = m_buy.get('total_return_pct', 0)
        ret_sell = m_sell.get('total_return_pct', 0)
        sh_buy = m_buy.get('sharpe', 0)
        sh_sell = m_sell.get('sharpe', 0)
        dd_buy = m_buy.get('max_drawdown_pct', 0)
        dd_sell = m_sell.get('max_drawdown_pct', 0)

        print(f"  Return:      BUY {ret_buy:+.1f}%  vs  "
              f"SELL {ret_sell:+.1f}%")
        print(f"  Sharpe:      BUY {sh_buy:.3f}  vs  SELL {sh_sell:.3f}")
        print(f"  Max DD:      BUY {dd_buy:.2f}%  vs  SELL {dd_sell:.2f}%")

        # حساب حكم
        wins = 0
        if ret_sell > ret_buy:
            wins += 1
        if sh_sell > sh_buy:
            wins += 1
        if dd_sell < dd_buy:
            wins += 1

        if wins >= 2:
            print(f"\n  {C.G}✓ SELL version WINS on {wins}/3 metrics{C.R}")
            print(f"    → المضي قدماً في testnet")
        elif wins == 1:
            print(f"\n  {C.Y}~ SELL mixed on {wins}/3 metrics{C.R}")
            print(f"    → يحتاج مزيداً من التحقق")
        else:
            print(f"\n  {C.RED}✗ SELL worse on {3 - wins}/3 metrics{C.R}")
            print(f"    → إعادة النظر في الفلتر")

    section("LOGS")
    print(f"  Files saved in: {args.out_dir}/")
    print(f"  Next: python -m json.tool {args.out_dir}/*.json")
    print(f"  Or:   grep 'Exit\\|Entry' {args.out_dir}/*.log | tail -50")

    return 0


if __name__ == "__main__":
    sys.exit(main())
