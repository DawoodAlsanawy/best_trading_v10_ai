#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_rr_results.py — يستخرج فقط المقاييس الجوهرية من rr_grid_fast
====================================================================

يقرأ 9 ملفات لوج وينتج مخرجات مضغوطة (~40 سطر) قابلة للنسخ واللصق.

الاستخدام:
    python3 extract_rr_results.py
    python3 extract_rr_results.py results/rr_grid_fast
"""
import os
import re
import sys

GRID_TAGS = ["A1","A2","A3","B1","B2","B3","C1","C2","C3"]
GRID_PARAMS = {
    "A1": (1.0, 3.0), "A2": (1.0, 4.0), "A3": (1.0, 5.0),
    "B1": (1.5, 3.0), "B2": (1.5, 4.0), "B3": (1.5, 5.0),
    "C1": (2.0, 3.0), "C2": (2.0, 4.0), "C3": (2.0, 5.0),
}


def _find(text, pattern, cast=float, default=None):
    m = re.search(pattern, text)
    if not m:
        return default
    try:
        return cast(m.group(1))
    except Exception:
        return default


def extract_one(log_path):
    if not os.path.exists(log_path):
        return None
    with open(log_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()

    r = {}
    r["n"]      = _find(r"عدد الصفقات\s*:\s*([\d,]+)",
                        lambda s: int(s.replace(",", "")), 0)
    r["wr"]     = _find(r"نسبة النجاح\s*:\s*([\d.]+)%", float, 0.0)
    r["pf"]     = _find(r"عامل الربح \(PF\)\s*:\s*([\d.]+)", float, 0.0)
    r["sharpe"] = _find(r"شارب \(سنوي\)\s*:\s*([+\-]?[\d.]+)", float, 0.0)
    r["dd"]     = _find(r"أقصى انخفاض\s*:\s*([\d.]+)%", float, 0.0)
    r["eln"]    = _find(r"متوسط\s*:\s*([+\-]?[\d.]+)", float, 0.0)
    r["cap"]    = _find(r"نهائي:\s*\$([\d,.]+)",
                        lambda s: float(s.replace(",", "")), 0.0)

    # Exit distribution (only key categories)
    section = re.search(r"توزيع أسباب الخروج\s*\n(.*?)(?:\n═|$)",
                        text, re.S)
    exits = {}
    if section:
        for line in section.group(1).splitlines():
            m = re.match(r"\s*([A-Za-z][\w\-\s:]+?)\s*:\s*([\d,]+)", line)
            if m:
                name = m.group(1).strip()
                cnt = int(m.group(2).replace(",", ""))
                exits[name] = cnt
    sl   = sum(v for k, v in exits.items() if "Emergency" in k)
    apex = sum(v for k, v in exits.items() if "Apex" in k)
    tp   = sum(v for k, v in exits.items() if "Hard TP" in k)
    n = max(r["n"], 1)
    r["sl_pct"]   = 100.0 * sl   / n
    r["apex_pct"] = 100.0 * apex / n
    r["tp_pct"]   = 100.0 * tp   / n
    return r


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "results/rr_grid_fast"

    results = {}
    for tag in GRID_TAGS:
        log_path = os.path.join(d, f"bt_rr_{tag}.log")
        r = extract_one(log_path)
        if r is not None:
            r["tag"] = tag
            r["ptr"], r["tpm"] = GRID_PARAMS[tag]
            results[tag] = r

    if not results:
        print(f"ERROR: no logs found in {d}/")
        sys.exit(1)

    # ── جدول مضغوط ──
    print("=" * 96)
    print(f"  R:R GRID RESULTS  (dir={d}/)")
    print("=" * 96)
    hdr = (f"{'Tag':<4s} {'PTR':>4s} {'TP':>4s} | "
           f"{'n':>5s} {'WR%':>6s} {'PF':>6s} {'Sharpe':>8s} "
           f"{'DD%':>6s} {'E[ln]':>10s} {'Cap$':>10s} | "
           f"{'SL%':>5s} {'Ap%':>5s} {'TP%':>5s}")
    print(hdr)
    print("-" * 96)

    for tag in GRID_TAGS:
        if tag not in results:
            print(f"{tag:<4s} {'—':>4s} {'—':>4s} | (log missing)")
            continue
        r = results[tag]
        print(f"{tag:<4s} {r['ptr']:>4.1f} {r['tpm']:>4.1f} | "
              f"{r['n']:>5d} {r['wr']:>6.2f} {r['pf']:>6.3f} "
              f"{r['sharpe']:>+8.3f} {r['dd']:>6.2f} "
              f"{r['eln']:>+10.6f} {r['cap']:>10,.0f} | "
              f"{r['sl_pct']:>5.1f} {r['apex_pct']:>5.1f} "
              f"{r['tp_pct']:>5.1f}")

    print("=" * 96)

    # ── ترتيب حسب Sharpe ──
    ranked = sorted(results.values(), key=lambda x: -x["sharpe"])
    print("\n── TOP 3 by Sharpe ──")
    for i, r in enumerate(ranked[:3], 1):
        print(f"  {i}. {r['tag']}  Sharpe={r['sharpe']:+.3f}  "
              f"DD={r['dd']:.2f}%  E[ln]={r['eln']:+.6f}  "
              f"PF={r['pf']:.3f}")

    # ── ترتيب حسب Sharpe/DD ──
    for r in results.values():
        r["sh_dd"] = r["sharpe"] / max(r["dd"] / 100.0, 1e-9)
    ranked_dd = sorted(results.values(), key=lambda x: -x["sh_dd"])
    print("\n── TOP 3 by Sharpe/DD ──")
    for i, r in enumerate(ranked_dd[:3], 1):
        print(f"  {i}. {r['tag']}  Sh/DD={r['sh_dd']:.3f}  "
              f"(Sh={r['sharpe']:+.3f}, DD={r['dd']:.2f}%)")

    # ── مقارنة مع B3 (baseline abl8b) ──
    b3 = results.get("B3")
    if b3:
        print("\n── vs BASELINE B3 (PTR=1.5, TP=5.0 = abl8b) ──")
        print(f"  {'Tag':<4s} {'ΔSharpe':>9s} {'ΔDD':>8s} "
              f"{'ΔE[ln]':>12s} {'ΔPF':>8s} {'ΔTP%':>7s}  verdict")
        for r in ranked:
            if r["tag"] == "B3":
                continue
            d_sh  = r["sharpe"] - b3["sharpe"]
            d_dd  = r["dd"]     - b3["dd"]
            d_eln = r["eln"]    - b3["eln"]
            d_pf  = r["pf"]     - b3["pf"]
            d_tp  = r["tp_pct"] - b3["tp_pct"]

            better = sum([d_sh > 0.05, d_dd < -2.0, d_eln > 0.00005])
            worse  = sum([d_sh < -0.05, d_dd > 2.0, d_eln < -0.00005])
            if better >= 2 and worse == 0:
                v = "BETTER"
            elif worse >= 2 and better == 0:
                v = "worse"
            else:
                v = "~tie"

            print(f"  {r['tag']:<4s} {d_sh:>+9.3f} {d_dd:>+8.2f} "
                  f"{d_eln:>+12.6f} {d_pf:>+8.3f} {d_tp:>+7.1f}  {v}")

    print()


if __name__ == "__main__":
    main()
