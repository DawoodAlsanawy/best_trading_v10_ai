#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ablation_sell_and_fee.py — اختبار ما إذا كان abl7a فعلاً أفضل من current.

يُنتج 4 نسخ من trading_2.py:
  baseline: current كما هو
  v1: GAUGE_SELL = 0.85 فقط
  v2: MAKER-only partial fee فقط
  v3: كلاهما (= abl7a سلوكياً)

يُشغّل كل نسخة على نفس البيانات، يستخرج المقاييس، يُقارن.
"""

import argparse, ast, re, shutil, subprocess, sys, time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor


def make_variant(src_text, gauge_sell=None, maker_only_partial=False):
    """يُعيد نص الكود بعد التطبيق."""
    text = src_text
    if gauge_sell is not None:
        # استبدال القيمة
        text = re.sub(
            r"GAUGE_PERCENTILE_SELL:\s*float\s*=\s*[\d.]+[^\n]*",
            f"GAUGE_PERCENTILE_SELL: float = {gauge_sell}   # [ABLATION]",
            text,
            count=1,
        )
    if maker_only_partial:
        # عكس V1: إرجاع fee إلى MAKER-only
        text = re.sub(
            r"_entry_fee = _close_qty \* pos\.entry_px \* CFG\.MAKER_FEE\n"
            r"(\s+)_exit_fee  = _close_qty \* px \* CFG\.TAKER_FEE\n"
            r"(\s+)_fee = _entry_fee \+ _exit_fee",
            r"_fee = _close_qty * (pos.entry_px + px) * CFG.MAKER_FEE",
            text,
            count=1,
        )
    return text


def run_backtest(script, log_path):
    """يُشغّل باكتيست واحد، يُعيد True إذا نجح."""
    cmd = [
        sys.executable, script,
        "--mode", "backtest",
        "--capital", "100",
        "--nassets", "100",
        "--timeframe", "4h",
        "--no-fixed-price",
        "--no-trailing",
        "--history-days", "730",
        "--trade-log", str(log_path) + ".jsonl",
    ]
    with open(log_path, 'w', encoding='utf-8') as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=600)
    return r.returncode == 0


def extract_metrics(log_path):
    """قراءة المقاييس من سجل الباكتيست."""
    text = Path(log_path).read_text(encoding='utf-8', errors='ignore')
    patterns = {
        'sharpe': r"شارب \(سنوي\)\s+:\s+([\d.\-]+)",
        'final': r"نهائي:\s+\$([\d,.]+)",
        'n_trades': r"عدد الصفقات\s+:\s+([\d,]+)",
        'buy': r"شراء / بيع\s+:\s+([\d,]+)",
        'sell': r"شراء / بيع\s+:\s+[\d,]+ / ([\d,]+)",
        'wr': r"نسبة النجاح\s+:\s+([\d.]+)",
        'pf': r"عامل الربح \(PF\)\s+:\s+([\d.]+)",
        'dd': r"أقصى انخفاض\s+:\s+([\d.]+)",
        'eln': r"متوسط\s+:\s+([+\-][\d.]+)",
        'risk': r"① متوسط المخاطرة الديناميكية\s+:\s+([\d.]+)",
    }
    out = {}
    for k, p in patterns.items():
        m = re.search(p, text)
        if m:
            v = m.group(1).replace(',', '').replace('$', '')
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--parallel', action='store_true',
                    help='تشغيل النسخ الأربع بالتوازي')
    args = ap.parse_args()

    src = Path(args.file)
    if not src.exists():
        print(f"❌ {args.file} غير موجود")
        return 1
    src_text = src.read_text(encoding='utf-8')

    workdir = Path('results/ablation_sell_fee')
    workdir.mkdir(parents=True, exist_ok=True)

    variants = {
        'baseline_current': (None, False),
        'v1_sell085':       (0.85, False),
        'v2_maker_fee':     (None, True),
        'v3_abl7a_behavior':(0.85, True),
    }

    print("═" * 70)
    print("  ablation_sell_and_fee.py")
    print("═" * 70)
    print()

    # إنشاء النسخ
    scripts = {}
    for name, (gs, mk) in variants.items():
        txt = make_variant(src_text, gauge_sell=gs, maker_only_partial=mk)
        try:
            ast.parse(txt)
        except SyntaxError as e:
            print(f"❌ {name}: خطأ صياغة: {e}")
            return 2
        p = workdir / f"trading_2_{name}.py"
        p.write_text(txt, encoding='utf-8')
        scripts[name] = str(p)
        print(f"  ✅ أُنشئ: {p.name}")

    print()
    print("▶ تشغيل 4 نسخ (قد يستغرق 6-10 دقائق) ...")
    t0 = time.time()

    def run_one(name):
        log = str(workdir / f"{name}.log")
        ok = run_backtest(scripts[name], log)
        return name, ok, log

    if args.parallel:
        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(run_one, scripts.keys()))
    else:
        results = [run_one(n) for n in scripts.keys()]

    elapsed = time.time() - t0
    print(f"  ✅ اكتمل في {elapsed:.0f}s")
    print()

    # استخراج المقاييس
    metrics = {}
    for name, ok, log in results:
        if ok:
            metrics[name] = extract_metrics(log)
        else:
            print(f"  ❌ {name}: فشل التشغيل")
            metrics[name] = {}

    # جدول المقارنة
    print("═" * 100)
    print("  نتائج المقارنة")
    print("═" * 100)
    print()

    headers = ['baseline_current', 'v1_sell085',
               'v2_maker_fee', 'v3_abl7a_behavior']
    rows = [
        ('Sharpe', 'sharpe'),
        ('E[ln]', 'eln'),
        ('WR %', 'wr'),
        ('PF', 'pf'),
        ('Max DD %', 'dd'),
        ('# trades', 'n_trades'),
        ('BUY', 'buy'),
        ('SELL', 'sell'),
        ('Final $', 'final'),
        ('AvgRisk %', 'risk'),
    ]

    # Header
    print(f"  {'Metric':<18} {'baseline':>12} {'v1(SELL.85)':>14} "
          f"{'v2(MAKER)':>13} {'v3(both)':>13}")
    print(f"  {'─'*18} {'─'*12} {'─'*14} {'─'*13} {'─'*13}")

    for label, key in rows:
        vals = []
        for h in headers:
            v = metrics.get(h, {}).get(key, '—')
            if isinstance(v, float):
                if key in ('final', 'n_trades', 'buy', 'sell'):
                    vals.append(f"{v:,.0f}")
                else:
                    vals.append(f"{v:.4f}")
            else:
                vals.append(str(v))
        print(f"  {label:<18} {vals[0]:>12} {vals[1]:>14} "
              f"{vals[2]:>13} {vals[3]:>13}")

    print()
    print("═" * 100)
    print("  التحليل")
    print("═" * 100)
    print()

    base = metrics.get('baseline_current', {})
    v1 = metrics.get('v1_sell085', {})
    v2 = metrics.get('v2_maker_fee', {})
    v3 = metrics.get('v3_abl7a_behavior', {})

    def delta(a, b, key):
        try:
            return float(a[key]) - float(b[key])
        except (KeyError, ValueError, TypeError):
            return None

    print(f"  Sharpe: baseline={base.get('sharpe', '?')} → "
          f"v3={v3.get('sharpe', '?')} "
          f"(Δ={delta(v3, base, 'sharpe')})")
    print(f"  Final:  baseline=${base.get('final', '?')} → "
          f"v3=${v3.get('final', '?')}")
    print()
    print(f"  مساهمة SELL (v1 - baseline):")
    print(f"    ΔSharpe = {delta(v1, base, 'sharpe')}")
    print(f"    ΔFinal  = ${delta(v1, base, 'final')}")
    print()
    print(f"  مساهمة Fee (v2 - baseline):")
    print(f"    ΔSharpe = {delta(v2, base, 'sharpe')}")
    print(f"    ΔFinal  = ${delta(v2, base, 'final')}")
    print()
    print(f"  المجموع (v3 - baseline):")
    print(f"    ΔSharpe = {delta(v3, base, 'sharpe')}")
    print(f"    ΔFinal  = ${delta(v3, base, 'final')}")

    print()
    print(f"  📁 كل السجلات في: {workdir}")
    print("═" * 100)


if __name__ == '__main__':
    sys.exit(main())
