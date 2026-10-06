#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""analyze_ablation_v2.py — تقرير شامل عن مصفوفة الـ ablation."""

import re
import sys
from pathlib import Path


def extract_metrics(log_path):
    if not Path(log_path).exists():
        return None
    text = Path(log_path).read_text(encoding='utf-8', errors='ignore')
    patterns = {
        'sharpe': r"شارب \(سنوي\)\s+:\s+([\d.\-]+)",
        'final':  r"نهائي:\s+\$([\d,.]+)",
        'n':      r"عدد الصفقات\s+:\s+([\d,]+)",
        'wr':     r"نسبة النجاح\s+:\s+([\d.]+)",
        'pf':     r"عامل الربح \(PF\)\s+:\s+([\d.]+)",
        'dd':     r"أقصى انخفاض\s+:\s+([\d.]+)",
        'eln':    r"متوسط\s+:\s+([+\-][\d.]+)",
        'risk':   r"① متوسط المخاطرة الديناميكية\s+:\s+([\d.]+)",
    }
    out = {}
    for k, p in patterns.items():
        m = re.search(p, text)
        if m:
            v = m.group(1).replace(',', '').replace('$', '')
            try:
                out[k] = float(v)
            except ValueError:
                pass

    # Exit distribution
    ex = {}
    m = re.search(r"توزيع أسباب الخروج(.*?)══", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"\s*(.+?)\s*:\s*([\d,]+)\s+\(", line)
            if mm:
                ex[mm.group(1).strip()] = int(mm.group(2).replace(',', ''))
    out['exits'] = ex

    return out


def main():
    base = Path('results/ablation_v2')
    if not base.exists():
        print("ERR: results/ablation_v2/ not found")
        return 1

    years = ['2024', '2025', '2026']
    configs = ['A_full', 'B_no_apex', 'C_no_apex_partial',
               'D_pure_signal', 'E_tp3', 'F_tp1.5']

    # جمع البيانات
    data = {}
    for y in years:
        for c in configs:
            log = base / f"{y}_{c}.log"
            m = extract_metrics(str(log))
            if m:
                data[(y, c)] = m

    if not data:
        print("ERR: no data found")
        return 1

    # ═══ الجدول الرئيسي: Sharpe ═══
    print()
    print("=" * 90)
    print("  Sharpe عبر النوافذ والحالات")
    print("=" * 90)
    print()
    header = f"  {'Config':<22} " + " ".join(f"{y:>14}" for y in years) + f" {'Min':>10}"
    print(header)
    print("  " + "─" * 86)

    for c in configs:
        row = f"  {c:<22} "
        values = []
        for y in years:
            m = data.get((y, c))
            if m and 'sharpe' in m:
                values.append(m['sharpe'])
                row += f"{m['sharpe']:>14.3f} "
            else:
                row += f"{'—':>14} "
                values.append(None)
        valid = [v for v in values if v is not None]
        min_s = min(valid) if valid else None
        row += f"{min_s:>10.3f}" if min_s is not None else f"{'—':>10}"
        print(row)

    # ═══ الجدول: Final Capital ═══
    print()
    print("=" * 90)
    print("  Final Capital")
    print("=" * 90)
    print()
    print(header)
    print("  " + "─" * 86)
    for c in configs:
        row = f"  {c:<22} "
        for y in years:
            m = data.get((y, c))
            if m and 'final' in m:
                row += f"{'$' + format(m['final'], ',.0f'):>14} "
            else:
                row += f"{'—':>14} "
        print(row)

    # ═══ الجدول: WR ═══
    print()
    print("=" * 90)
    print("  Win Rate %")
    print("=" * 90)
    print()
    print(header)
    print("  " + "─" * 86)
    for c in configs:
        row = f"  {c:<22} "
        for y in years:
            m = data.get((y, c))
            if m and 'wr' in m:
                row += f"{m['wr']:>14.2f} "
            else:
                row += f"{'—':>14} "
        print(row)

    # ═══ الجدول: عدد الصفقات ═══
    print()
    print("=" * 90)
    print("  عدد الصفقات")
    print("=" * 90)
    print()
    print(header)
    print("  " + "─" * 86)
    for c in configs:
        row = f"  {c:<22} "
        for y in years:
            m = data.get((y, c))
            if m and 'n' in m:
                row += f"{int(m['n']):>14,} "
            else:
                row += f"{'—':>14} "
        print(row)

    # ═══ تحليل: أين ذهبت الحافة؟ ═══
    print()
    print("=" * 90)
    print("  تحليل: كيف توزعت الحافة؟")
    print("=" * 90)
    print()

    # الفرق بين A_full و D_pure_signal
    print("  ── مساهمة Apex + Partial + Breakeven ──")
    print()
    for y in years:
        a = data.get((y, 'A_full'), {})
        d = data.get((y, 'D_pure_signal'), {})
        if a and d and 'sharpe' in a and 'sharpe' in d:
            delta = a['sharpe'] - d['sharpe']
            ratio = a['sharpe'] / d['sharpe'] if d['sharpe'] != 0 else float('inf')
            print(f"  {y}: A_full={a['sharpe']:.3f} vs D_pure={d['sharpe']:.3f}  "
                  f"Δ={delta:+.3f}  (ratio={ratio:.2f}×)")

    print()
    print("  ── مساهمة Apex فقط ──")
    for y in years:
        a = data.get((y, 'A_full'), {})
        b = data.get((y, 'B_no_apex'), {})
        if a and b and 'sharpe' in a and 'sharpe' in b:
            print(f"  {y}: A={a['sharpe']:.3f} vs B(no-apex)={b['sharpe']:.3f}  "
                  f"Δ={a['sharpe']-b['sharpe']:+.3f}")

    print()
    print("  ── مساهمة Partial (بعد إزالة Apex) ──")
    for y in years:
        b = data.get((y, 'B_no_apex'), {})
        c = data.get((y, 'C_no_apex_partial'), {})
        if b and c and 'sharpe' in b and 'sharpe' in c:
            print(f"  {y}: B={b['sharpe']:.3f} vs C(no-partial)={c['sharpe']:.3f}  "
                  f"Δ={b['sharpe']-c['sharpe']:+.3f}")

    print()
    print("  ── مساهمة Breakeven (بعد إزالة Apex + Partial) ──")
    for y in years:
        c = data.get((y, 'C_no_apex_partial'), {})
        d = data.get((y, 'D_pure_signal'), {})
        if c and d and 'sharpe' in c and 'sharpe' in d:
            print(f"  {y}: C={c['sharpe']:.3f} vs D(pure)={d['sharpe']:.3f}  "
                  f"Δ={c['sharpe']-d['sharpe']:+.3f}")

    print()
    print("  ── حساسية TP (pure signal) ──")
    for y in years:
        d = data.get((y, 'D_pure_signal'), {})
        e = data.get((y, 'E_tp3'), {})
        f = data.get((y, 'F_tp1.5'), {})
        row = f"  {y}: TP5.0={d.get('sharpe', 0):.3f}  "
        row += f"TP3.0={e.get('sharpe', 0):.3f}  "
        row += f"TP1.5={f.get('sharpe', 0):.3f}"
        print(row)

    # ═══ الحكم النهائي ═══
    print()
    print("=" * 90)
    print("  الحكم النهائي")
    print("=" * 90)
    print()

    # هل pure signal رابح؟
    pure_sharpes = [data.get((y, 'D_pure_signal'), {}).get('sharpe')
                    for y in years]
    pure_sharpes = [s for s in pure_sharpes if s is not None]

    if pure_sharpes:
        avg = sum(pure_sharpes) / len(pure_sharpes)
        min_s = min(pure_sharpes)
        print(f"  Pure signal (D): avg Sharpe={avg:.3f}, min={min_s:.3f}")
        if min_s > 0.5:
            print(f"  ✅ الإشارة المجردة رابحة — الحافة في الإشارة")
        elif min_s > 0:
            print(f"  ⚠️  الإشارة المجردة موجبة لكن ضعيفة")
        else:
            print(f"  ❌ الإشارة المجردة قد لا تحمل حافة كافية")

    print()
    print("  ── Full picture ──")
    for c in configs:
        sharpes = [data.get((y, c), {}).get('sharpe') for y in years]
        valid = [s for s in sharpes if s is not None]
        if valid:
            avg = sum(valid) / len(valid)
            print(f"  {c:<22} avg Sharpe = {avg:.3f}")


if __name__ == '__main__':
    sys.exit(main())
