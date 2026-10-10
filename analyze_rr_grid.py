#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_rr_grid.py — يقارن نتائج الـ grid ويحدد الفائز
"""
import os
import re
import sys

GRID = [
    ("A1", 1.0, 3.0),
    ("A2", 1.0, 4.0),
    ("A3", 1.0, 5.0),
    ("B1", 1.5, 3.0),
    ("B2", 1.5, 4.0),
    ("B3", 1.5, 5.0),
    ("C1", 2.0, 3.0),
    ("C2", 2.0, 4.0),
    ("C3", 2.0, 5.0),
]

LOG_DIR = "results/rr_grid"


def _extract(log_path):
    """استخراج المقاييس من ملف اللوج"""
    if not os.path.exists(log_path):
        return None
    with open(log_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()

    def _find(pattern, cast=float, default=None):
        m = re.search(pattern, text)
        if not m:
            return default
        try:
            return cast(m.group(1))
        except Exception:
            return default

    r = {}

    r["n_trades"] = _find(r"عدد الصفقات\s*:\s*([\d,]+)",
                          lambda s: int(s.replace(",", "")), 0)
    r["wr_pct"] = _find(r"نسبة النجاح\s*:\s*([\d.]+)%", float, 0.0)
    r["pf"] = _find(r"عامل الربح \(PF\)\s*:\s*([\d.]+)", float, 0.0)
    r["sharpe"] = _find(r"شارب \(سنوي\)\s*:\s*([+\-]?[\d.]+)", float, 0.0)
    r["dd_pct"] = _find(r"أقصى انخفاض\s*:\s*([\d.]+)%", float, 0.0)
    r["e_ln"] = _find(r"متوسط\s*:\s*([+\-]?[\d.]+)", float, 0.0)
    r["final_cap"] = _find(r"نهائي:\s*\$([\d,.]+)",
                            lambda s: float(s.replace(",", "")), 0.0)

    # توزيع الخروج
    exit_reasons = {}
    section = re.search(r"توزيع أسباب الخروج\s*\n(.*?)(?:\n═|$)", text, re.S)
    if section:
        for line in section.group(1).splitlines():
            m = re.match(r"\s*([A-Za-z][\w\-\s:]+?)\s*:\s*([\d,]+)", line)
            if m:
                name = m.group(1).strip()
                cnt = int(m.group(2).replace(",", ""))
                exit_reasons[name] = cnt
    r["exits"] = exit_reasons

    return r


def _pct(a, b):
    return 100.0 * a / max(b, 1)


def main():
    print()
    print("═" * 100)
    print("  R:R GRID — RESULTS")
    print("═" * 100)
    print()

    rows = []
    for tag, ptr, tpm in GRID:
        log_path = os.path.join(LOG_DIR, f"bt_rr_{tag}.log")
        r = _extract(log_path)
        if r is None:
            rows.append({
                "tag": tag, "ptr": ptr, "tpm": tpm,
                "status": "MISSING",
            })
            continue
        r["tag"] = tag
        r["ptr"] = ptr
        r["tpm"] = tpm
        r["status"] = "OK"
        rows.append(r)

    # جدول أساسي
    print(f"{'Tag':<5s} {'PTR':>5s} {'TP':>5s} | "
          f"{'n':>6s} {'WR%':>7s} {'PF':>7s} "
          f"{'Sharpe':>8s} {'DD%':>7s} {'E[ln]':>11s} "
          f"{'Cap$':>12s} | {'SL%':>6s} {'Apex%':>7s} {'TP%':>6s}")
    print("-" * 100)

    valid = []
    for r in rows:
        if r["status"] != "OK":
            print(f"{r['tag']:<5s} {r['ptr']:>5.1f} {r['tpm']:>5.1f} | "
                  f"{r['status']}")
            continue

        sl_pct = _pct(r["exits"].get("Emergency SL", 0), r["n_trades"])
        apex_pct = _pct(
            sum(v for k, v in r["exits"].items() if "Apex" in k),
            r["n_trades"])
        tp_pct = _pct(r["exits"].get("Hard TP", 0), r["n_trades"])

        print(f"{r['tag']:<5s} {r['ptr']:>5.1f} {r['tpm']:>5.1f} | "
              f"{r['n_trades']:>6d} {r['wr_pct']:>7.2f} {r['pf']:>7.3f} "
              f"{r['sharpe']:>+8.3f} {r['dd_pct']:>7.2f} {r['e_ln']:>+11.6f} "
              f"{r['final_cap']:>12,.0f} | "
              f"{sl_pct:>6.1f} {apex_pct:>7.1f} {tp_pct:>6.1f}")

        r["sl_pct"] = sl_pct
        r["apex_pct"] = apex_pct
        r["tp_pct"] = tp_pct
        valid.append(r)

    if not valid:
        print("\nNo valid results. Run `bash run_rr_grid.sh` first.")
        sys.exit(1)

    # الترتيب حسب Sharpe
    print()
    print("─" * 100)
    print("  RANKING by SHARPE")
    print("─" * 100)
    ranked = sorted(valid, key=lambda x: -x["sharpe"])
    for i, r in enumerate(ranked, 1):
        print(f"  #{i}  {r['tag']:<4s}  "
              f"Sharpe={r['sharpe']:+.3f}  "
              f"DD={r['dd_pct']:5.2f}%  "
              f"E[ln]={r['e_ln']:+.6f}  "
              f"PF={r['pf']:.3f}  "
              f"WR={r['wr_pct']:.1f}%")

    # الترتيب حسب Sharpe/DD
    print()
    print("─" * 100)
    print("  RANKING by SHARPE/DD (risk-adjusted)")
    print("─" * 100)
    for r in valid:
        r["sharpe_dd"] = r["sharpe"] / max(r["dd_pct"] / 100.0, 1e-9)
    ranked_dd = sorted(valid, key=lambda x: -x["sharpe_dd"])
    for i, r in enumerate(ranked_dd, 1):
        print(f"  #{i}  {r['tag']:<4s}  "
              f"Sh={r['sharpe']:+.3f}  DD={r['dd_pct']:5.2f}%  "
              f"ratio={r['sharpe_dd']:.3f}")

    # أفضل في كل فئة
    print()
    print("─" * 100)
    print("  WINNERS")
    print("─" * 100)
    best_sh = ranked[0]
    best_dd = min(valid, key=lambda x: x["dd_pct"])
    best_eln = max(valid, key=lambda x: x["e_ln"])
    best_pf = max(valid, key=lambda x: x["pf"])
    best_ratio = ranked_dd[0]
    best_tp = max(valid, key=lambda x: x["tp_pct"])

    print(f"  Highest Sharpe   : {best_sh['tag']}  "
          f"(PTR={best_sh['ptr']}, TP={best_sh['tpm']})  "
          f"Sharpe={best_sh['sharpe']:+.3f}")
    print(f"  Lowest DD        : {best_dd['tag']}  "
          f"DD={best_dd['dd_pct']:.2f}%")
    print(f"  Best E[ln]       : {best_eln['tag']}  "
          f"E[ln]={best_eln['e_ln']:+.6f}")
    print(f"  Best PF          : {best_pf['tag']}  "
          f"PF={best_pf['pf']:.3f}")
    print(f"  Best Sharpe/DD   : {best_ratio['tag']}  "
          f"ratio={best_ratio['sharpe_dd']:.3f}")
    print(f"  Most Hard TPs    : {best_tp['tag']}  "
          f"TP%={best_tp['tp_pct']:.1f}%  "
          f"(vs baseline B3 TP%={next((x['tp_pct'] for x in valid if x['tag']=='B3'), 0):.1f}%)")

    # مقارنة مع baseline B3
    print()
    print("─" * 100)
    print("  VS BASELINE B3 (PTR=1.5, TP=5.0 = abl8b)")
    print("─" * 100)
    b3 = next((x for x in valid if x["tag"] == "B3"), None)
    if b3 is None:
        print("  B3 missing. Cannot compare.")
    else:
        print(f"  {'Tag':<5s} {'ΔSharpe':>10s} {'ΔDD':>10s} "
              f"{'ΔE[ln]':>13s} {'ΔPF':>10s} {'ΔTP%':>8s}  Verdict")
        for r in ranked:
            if r["tag"] == "B3":
                continue
            d_sh = r["sharpe"] - b3["sharpe"]
            d_dd = r["dd_pct"] - b3["dd_pct"]
            d_eln = r["e_ln"] - b3["e_ln"]
            d_pf = r["pf"] - b3["pf"]
            d_tp = r["tp_pct"] - b3["tp_pct"]

            # verdict
            better = 0
            worse = 0
            if d_sh > 0.05: better += 1
            if d_sh < -0.05: worse += 1
            if d_dd < -2.0: better += 1
            if d_dd > 2.0: worse += 1
            if d_eln > 0.00005: better += 1
            if d_eln < -0.00005: worse += 1

            if better >= 2 and worse == 0:
                v = "✅ BETTER"
            elif worse >= 2 and better == 0:
                v = "❌ worse"
            else:
                v = "≈ tie"

            print(f"  {r['tag']:<5s} {d_sh:>+10.3f} {d_dd:>+10.2f} "
                  f"{d_eln:>+13.6f} {d_pf:>+10.3f} {d_tp:>+8.1f}  {v}")

    print()
    print("═" * 100)


if __name__ == "__main__":
    main()
