#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اختبار تجريبي مقارن: baseline vs partial_tp fee fix.
- يُنشئ نسختين من trading_2.py
- يُشغّل باكتيست على كل منهما (أمر واحد، 90 ثانية)
- يستخرج المقاييس ويقارنها
- لا يعدّل الملف الأصلي
التشغيل: python3 test_partial_tp_fix.py
"""

import shutil
import subprocess
import sys
import re
import json
from pathlib import Path
from datetime import datetime

SOURCE = "trading_2.py"
BASELINE_VAR = "trading_2_test_baseline.py"
V1_VAR = "trading_2_test_v1_partialfee.py"
LOG_DIR = Path("results/test_partial_tp")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# التعديل: نبحث عن كتلة _partial_tp الفعلية ونعدّلها
# ═══════════════════════════════════════════════════════════════

# النمط الأصلي (minimal match — فقط السطر المفتاحي)
OLD_FEE_LINE_PATTERN = re.compile(
    r"(\s+)_fee = _close_qty \* \(pos\.entry_px \+ px\) \* CFG\.MAKER_FEE"
)


def apply_partial_tp_fix(source_text: str) -> tuple[str, bool, str]:
    """
    يبحث عن سطر fee في _partial_tp ويستبدله بالنسخة المصححة.
    يُعيد (new_text, applied, message).
    """
    m = OLD_FEE_LINE_PATTERN.search(source_text)
    if not m:
        return source_text, False, "لم أجد سطر fee في _partial_tp"

    indent = m.group(1)
    old_line = m.group(0)

    new_block = (
        f"{indent}_entry_fee = _close_qty * pos.entry_px * CFG.MAKER_FEE\n"
        f"{indent}_exit_fee  = _close_qty * px * CFG.TAKER_FEE\n"
        f"{indent}_fee = _entry_fee + _exit_fee"
    )

    new_text = source_text.replace(old_line, new_block, 1)
    return new_text, True, "تم تطبيق الإصلاح"


# ═══════════════════════════════════════════════════════════════
# الإقلاع والتحقق
# ═══════════════════════════════════════════════════════════════

def create_variant(src: str, dst: str, patch=None):
    """ينسخ src إلى dst، ويُطبّق patch إن وُجد. يتحقق من الصياغة."""
    text = Path(src).read_text(encoding='utf-8')

    if patch is not None:
        text, applied, msg = patch(text)
        if not applied:
            print(f"  ⚠️  {dst}: {msg}")
            return False

    Path(dst).write_text(text, encoding='utf-8')

    # تحقق الصياغة
    try:
        import ast
        ast.parse(text)
    except SyntaxError as e:
        print(f"  ❌ {dst}: خطأ صياغة: {e}")
        return False

    return True


def run_backtest(script: str, log_path: str, tag: str) -> bool:
    """يُشغّل باكتيست واحد. يُعيد True إذا نجح."""
    cmd = [
        sys.executable, script,
        "--mode", "backtest",
        "--capital", "100",
        "--nassets", "100",
        "--timeframe", "4h",
        "--no-fixed-price",
        "--no-trailing",
        "--history-days", "730",
        "--trade-log", f"{log_path}.jsonl",
    ]

    print(f"  ▶ تشغيل {tag} ...")
    t0 = datetime.now()
    with open(log_path, 'w', encoding='utf-8') as f:
        result = subprocess.run(
            cmd, stdout=f, stderr=subprocess.STDOUT,
            text=True, timeout=600
        )
    elapsed = (datetime.now() - t0).total_seconds()

    if result.returncode != 0:
        print(f"  ❌ {tag}: returncode={result.returncode}")
        # اطبع آخر 5 أسطر
        with open(log_path, encoding='utf-8') as f:
            lines = f.readlines()
            for l in lines[-5:]:
                print(f"     {l.rstrip()}")
        return False

    print(f"  ✅ {tag}: نجح ({elapsed:.0f}s)")
    return True


# ═══════════════════════════════════════════════════════════════
# استخراج المقاييس من السجل
# ═══════════════════════════════════════════════════════════════

def extract_metrics(log_path: str) -> dict:
    """قراءة السجل واستخراج المقاييس الرئيسية."""
    metrics = {
        'sharpe': None,
        'win_rate': None,
        'profit_factor': None,
        'mean_log_return': None,
        'max_drawdown': None,
        'n_trades': None,
        'final_capital': None,
        'avg_win': None,
        'avg_loss': None,
        'n_signals': None,
        'n_fills': None,
    }

    if not Path(log_path).exists():
        return metrics

    text = Path(log_path).read_text(encoding='utf-8', errors='ignore')

    # الأنماط
    patterns = {
        'sharpe': r"شارب \(سنوي\)\s+:\s+([\d.\-]+)",
        'win_rate': r"نسبة النجاح\s+:\s+([\d.]+)%",
        'profit_factor': r"عامل الربح \(PF\)\s+:\s+([\d.]+)",
        'mean_log_return': r"متوسط\s+:\s+([+\-][\d.]+)",
        'max_drawdown': r"أقصى انخفاض\s+:\s+([\d.]+)%",
        'n_trades': r"عدد الصفقات\s+:\s+([\d,]+)",
        'final_capital': r"نهائي:\s+\$([\d,.]+)",
        'avg_win': r"متوسط الربح\s+:\s+\$([\d.\-]+)",
        'avg_loss': r"متوسط الخسارة\s+:\s+\$([\-\d.]+)",
        'n_signals': r"✔\s+([\d,]+) إشارة",
        'n_fills': r"Entry fills:\s+([\d,]+)/",
    }

    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            val = m.group(1).replace(',', '').replace('$', '')
            try:
                metrics[key] = float(val)
            except ValueError:
                metrics[key] = val

    return metrics


def delta(baseline, variant, key, pct=False):
    """حساب الفرق."""
    b = baseline.get(key)
    v = variant.get(key)
    if b is None or v is None:
        return "—"
    try:
        d = float(v) - float(b)
        if pct and b != 0:
            return f"{d:+.4f} ({100*d/b:+.2f}%)"
        return f"{d:+.4f}"
    except (ValueError, TypeError):
        return f"{v}"


# ═══════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════

def main():
    print("═" * 70)
    print("  اختبار: baseline vs partial_tp fee fix")
    print("═" * 70)
    print()

    if not Path(SOURCE).exists():
        print(f"❌ {SOURCE} غير موجود")
        sys.exit(1)

    # ── 1. إنشاء النسخ ──
    print("▶ إنشاء النسخ ...")
    if not create_variant(SOURCE, BASELINE_VAR, patch=None):
        print("❌ فشل إنشاء baseline")
        sys.exit(2)
    print(f"  ✅ {BASELINE_VAR}")

    if not create_variant(SOURCE, V1_VAR, patch=apply_partial_tp_fix):
        print("❌ فشل إنشاء V1")
        sys.exit(3)
    print(f"  ✅ {V1_VAR}")

    # ── 2. تشغيل الباكتيستات ──
    print("\n▶ تشغيل الباكتيستات (قد يستغرق 4-6 دقائق) ...")
    log_base = str(LOG_DIR / "baseline.log")
    log_v1 = str(LOG_DIR / "v1.log")

    if not run_backtest(BASELINE_VAR, log_base, "BASELINE"):
        print("❌ فشل تشغيل baseline")
        sys.exit(4)

    if not run_backtest(V1_VAR, log_v1, "V1 (partial_tp fix)"):
        print("❌ فشل تشغيل V1")
        sys.exit(5)

    # ── 3. استخراج المقاييس ──
    print("\n▶ استخراج المقاييس ...")
    m_base = extract_metrics(log_base)
    m_v1 = extract_metrics(log_v1)

    # ── 4. جدول المقارنة ──
    print()
    print("═" * 70)
    print("  نتائج المقارنة")
    print("═" * 70)
    print()
    print(f"  {'المقياس':<28} {'BASELINE':>14} {'V1':>14} {'Δ':>12}")
    print(f"  {'─'*28} {'─'*14} {'─'*14} {'─'*12}")

    rows = [
        ('Sharpe (سنوي)', 'sharpe', False),
        ('Win Rate %', 'win_rate', False),
        ('Profit Factor', 'profit_factor', False),
        ('E[ln]', 'mean_log_return', False),
        ('Max Drawdown %', 'max_drawdown', False),
        ('عدد الصفقات', 'n_trades', False),
        ('رأس المال النهائي $', 'final_capital', False),
        ('متوسط الربح $', 'avg_win', False),
        ('متوسط الخسارة $', 'avg_loss', False),
        ('عدد الإشارات', 'n_signals', False),
        ('عدد الملء', 'n_fills', False),
    ]

    for label, key, as_pct in rows:
        b = m_base.get(key)
        v = m_v1.get(key)
        d = delta(m_base, m_v1, key, pct=as_pct)
        b_str = f"{b}" if b is not None else "—"
        v_str = f"{v}" if v is not None else "—"
        print(f"  {label:<28} {b_str:>14} {v_str:>14} {d:>12}")

    # ── 5. الحكم ──
    print()
    print("═" * 70)
    print("  الحكم")
    print("═" * 70)
    print()

    try:
        sharpe_delta = (float(m_v1['sharpe']) - float(m_base['sharpe']))
    except (ValueError, TypeError, KeyError):
        sharpe_delta = None

    try:
        pf_delta = (float(m_v1['profit_factor']) -
                    float(m_base['profit_factor']))
    except (ValueError, TypeError, KeyError):
        pf_delta = None

    if sharpe_delta is None:
        print("  ⚠️  لم أستطع استخراج Sharpe من أحد السجلين")
    else:
        print(f"  Δ Sharpe = {sharpe_delta:+.4f}")
        if abs(sharpe_delta) < 0.02:
            print("  ✅ الفرق صغير جداً (< 0.02) → V1 آمن")
        elif abs(sharpe_delta) < 0.05:
            print("  ✅ الفرق مقبول (< 0.05) → V1 آمن")
        elif abs(sharpe_delta) < 0.10:
            print("  ⚠️  الفرق ملحوظ (0.05-0.10) → فكر قبل التطبيق")
        else:
            print("  ❌ الفرق كبير (> 0.10) → لا تُطبّق بدون تحليل إضافي")

    if pf_delta is not None:
        print(f"  Δ Profit Factor = {pf_delta:+.4f}")
        if abs(pf_delta) < 0.005:
            print("  ✅ PF شبه ثابت → V1 لا يضر الربحية")

    print()
    print(f"  سجلات كاملة:")
    print(f"    {log_base}")
    print(f"    {log_v1}")
    print()
    print(f"  ملفات الباكتيست:")
    print(f"    {BASELINE_VAR}")
    print(f"    {V1_VAR}")
    print()
    print("  للتنظيف: rm trading_2_test_*.py")
    print("═" * 70)


if __name__ == '__main__':
    main()
