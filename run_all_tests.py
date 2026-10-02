#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all_tests.py — Automated Backtest Validation Suite
=======================================================
يشغّل كل الاختبارات تلقائياً ثم يُنتج تقريراً موحّداً.

يغطي:
  1. Baseline (بدون فلتر)
  2. BUY-only بثلاث عتبات (p50, p60, p70)
  3. Hybrid (BUY + SELL مع فلتر صارم)
  4. Multi-period validation (90d / 180d / 365d)

الاستخدام:
    python run_all_tests.py                  # تشغيل كامل
    python run_all_tests.py --quick          # 90d فقط (سريع)
    python run_all_tests.py --resume         # تخطّي الاختبارات المكتملة
    python run_all_tests.py --list           # عرض الاختبارات فقط

المخرجات:
    results/                                 # مجلد النتائج
      ├── trades_<test>.jsonl               # سجل التداول لكل اختبار
      ├── bt_<test>.log                     # سجل كامل
      ├── metrics_<test>.json               # المقاييس المُستخرجة
      └── FINAL_REPORT.md                   # التقرير الموحّد
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import glob
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np


# ═══════════════════════════════════════════════════════════════
# § 1 — الإعدادات
# ═══════════════════════════════════════════════════════════════

BOT_FILE = "trading_2.py"
RESULTS_DIR = "results"
TIMEOUT_MINUTES = 60
API_KEY = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")


# ═══════════════════════════════════════════════════════════════
# § 2 — سيناريوهات الاختبار
# ═══════════════════════════════════════════════════════════════

def build_configs(quick=False):
    """يبني قائمة كل الاختبارات."""
    base_args = [
        "--mode", "backtest",
        "--capital", "100",
        "--nassets", "100",
        "--maxcon", "5",
        "--timeframe", "4h",
        "--no-fixed-price",
        "--no-trailing",
    ]
    
    configs = []
    
    if quick:
        # وضع سريع: 90 يوم فقط
        hd = 90
        for name, extra in [
            ("baseline_90d", []),
            ("buy_only_p50_90d", ["--gauge-filter", "--gauge-disable-sell",
                                   "--gauge-buy-pct", "0.50"]),
            ("buy_only_p60_90d", ["--gauge-filter", "--gauge-disable-sell",
                                   "--gauge-buy-pct", "0.60"]),
            ("buy_only_p70_90d", ["--gauge-filter", "--gauge-disable-sell",
                                   "--gauge-buy-pct", "0.70"]),
            ("hybrid_90d", ["--gauge-filter",
                             "--gauge-buy-pct", "0.60",
                             "--gauge-sell-pct", "0.85"]),
        ]:
            configs.append({
                "name": name,
                "args": base_args + ["--history-days", str(hd)] + extra,
                "group": "90d",
            })
    else:
        # الوضع الكامل: 90 + 180 + 365
        for hd in [90, 180, 365]:
            tag = f"{hd}d"
            for name, extra in [
                (f"baseline_{tag}", []),
                (f"buy_p50_{tag}", ["--gauge-filter",
                                     "--gauge-disable-sell",
                                     "--gauge-buy-pct", "0.50"]),
                (f"buy_p60_{tag}", ["--gauge-filter",
                                     "--gauge-disable-sell",
                                     "--gauge-buy-pct", "0.60"]),
                (f"buy_p70_{tag}", ["--gauge-filter",
                                     "--gauge-disable-sell",
                                     "--gauge-buy-pct", "0.70"]),
                (f"hybrid_{tag}", ["--gauge-filter",
                                    "--gauge-buy-pct", "0.60",
                                    "--gauge-sell-pct", "0.85"]),
            ]:
                configs.append({
                    "name": name,
                    "args": base_args + ["--history-days", str(hd)] + extra,
                    "group": tag,
                })
    
    return configs


# ═══════════════════════════════════════════════════════════════
# § 3 — تشغيل backtest واحد
# ═══════════════════════════════════════════════════════════════

def is_completed(name):
    """هل الاختبار مكتمل ومخرجاته موجودة؟"""
    trades = os.path.join(RESULTS_DIR, f"trades_{name}.jsonl")
    metrics = os.path.join(RESULTS_DIR, f"metrics_{name}.json")
    return os.path.exists(metrics) and os.path.exists(trades)


def run_single_backtest(config):
    """يشغّل backtest واحد ويعيد (name, status, error)."""
    name = config["name"]
    args = config["args"]
    
    trades_file = os.path.join(RESULTS_DIR, f"trades_{name}.jsonl")
    log_file = os.path.join(RESULTS_DIR, f"bt_{name}.log")
    
    if not os.path.exists(BOT_FILE):
        return name, "error", f"Bot file not found: {BOT_FILE}"
    
    cmd = [sys.executable, BOT_FILE] + args + [
        "--trade-log", trades_file
    ]
    
    # إضافة API keys إن وُجدت
    if API_KEY:
        cmd += ["--api-key", API_KEY, "--api-secret", API_SECRET]
    
    print(f"  → Running: {name}")
    print(f"    cmd: {' '.join(cmd[:8])} ...")
    
    t0 = time.time()
    try:
        with open(log_file, "w") as lf:
            proc = subprocess.run(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                timeout=TIMEOUT_MINUTES * 60,
            )
        
        elapsed = time.time() - t0
        
        if proc.returncode != 0:
            return name, "error", f"Exit code {proc.returncode}"
        
        if not os.path.exists(trades_file):
            return name, "error", "No trades file created"
        
        print(f"    ✅ done in {elapsed/60:.1f} min")
        return name, "ok", None
    
    except subprocess.TimeoutExpired:
        return name, "error", f"Timeout after {TIMEOUT_MINUTES} min"
    except Exception as e:
        return name, "error", str(e)


# ═══════════════════════════════════════════════════════════════
# § 4 — تحميل وحساب المقاييس
# ═══════════════════════════════════════════════════════════════

def load_trades(path):
    trades = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("_meta"):
                    continue
                trades.append(r)
            except Exception:
                pass
    return trades


def compute_metrics(trades):
    """يحسب كل المقاييس لسلة صفقات."""
    if not trades:
        return None
    pnls = np.array([float(t.get("net_pnl", 0) or 0) for t in trades])
    n = len(pnls)
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    
    wr = len(wins) / n * 100 if n else 0
    pf = (wins.sum() / abs(losses.sum())) if losses.sum() < 0 else float('inf')
    avg_pnl = pnls.mean()
    total = pnls.sum()
    std = pnls.std(ddof=1) if n > 1 else 0
    sharpe = (avg_pnl / std * np.sqrt(252)) if std > 0 else 0
    
    # Equity curve + DD
    caps = [float(t.get("capital_after", 0) or 0) for t in trades]
    cap0 = float(trades[0].get("capital_before", 100) or 100)
    eq = [cap0] + caps
    peak = eq[0]
    max_dd = 0.0
    for e in eq:
        peak = max(peak, e)
        dd = (peak - e) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    # توزيع أسباب الخروج
    exits = {}
    for t in trades:
        r = str(t.get("exit_reason", "?"))
        if "Hard TP" in r:
            k = "Hard TP"
        elif "Emergency SL" in r:
            k = "Emergency SL"
        elif "MaxHold" in r:
            k = "MaxHold"
        elif "EndOfData" in r:
            k = "EndOfData"
        else:
            k = r[:20]
        exits[k] = exits.get(k, 0) + 1
    
    # BUY/SELL split
    buys = [t for t in trades if t.get("action") == "BUY"]
    sells = [t for t in trades if t.get("action") == "SELL"]
    
    def _sub_stats(lst):
        if not lst:
            return {"n": 0, "avg": 0, "wr": 0}
        p = np.array([float(t.get("net_pnl", 0) or 0) for t in lst])
        return {
            "n": len(p),
            "avg": float(p.mean()),
            "wr": float((p > 0).mean() * 100),
            "total": float(p.sum()),
        }
    
    return {
        "n": n,
        "avg_pnl": float(avg_pnl),
        "total": float(total),
        "wr": float(wr),
        "pf": float(pf),
        "sharpe": float(sharpe),
        "std": float(std),
        "max_dd": float(max_dd),
        "final_capital": float(eq[-1]),
        "initial_capital": cap0,
        "exits": exits,
        "buy": _sub_stats(buys),
        "sell": _sub_stats(sells),
    }


# ═══════════════════════════════════════════════════════════════
# § 5 — استخراج إعدادات التشغيل
# ═══════════════════════════════════════════════════════════════

def extract_meta(trades_file):
    """يقرأ الـ _meta من السجل."""
    with open(trades_file, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("_meta"):
                    return r
            except Exception:
                continue
    return {}


# ═══════════════════════════════════════════════════════════════
# § 6 — تحليل ملف واحد وحفظ metrics
# ═══════════════════════════════════════════════════════════════

def analyze_and_save(name):
    """يحلل trades_<name>.jsonl ويحفظ metrics_<name>.json."""
    trades_file = os.path.join(RESULTS_DIR, f"trades_{name}.jsonl")
    metrics_file = os.path.join(RESULTS_DIR, f"metrics_{name}.json")
    
    if not os.path.exists(trades_file):
        return None
    
    trades = load_trades(trades_file)
    if len(trades) < 10:
        return None
    
    metrics = compute_metrics(trades)
    if metrics is None:
        return None
    
    metrics["_meta"] = extract_meta(trades_file)
    metrics["_file"] = trades_file
    
    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    
    return metrics


# ═══════════════════════════════════════════════════════════════
# § 7 — توليد التقرير النهائي
# ═══════════════════════════════════════════════════════════════

def generate_report(configs, results):
    """يولّد FINAL_REPORT.md."""
    report_path = os.path.join(RESULTS_DIR, "FINAL_REPORT.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Automated Backtest Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Group by history_days
        groups = {}
        for cfg in configs:
            g = cfg.get("group", "all")
            groups.setdefault(g, []).append(cfg["name"])
        
        # الترتيب
        def _sort_key(g):
            m = re.match(r"(\d+)d", g)
            return int(m.group(1)) if m else 0
        
        groups = dict(sorted(groups.items(), key=lambda x: _sort_key(x[0])))
        
        for group, names in groups.items():
            f.write(f"## Group: {group}\n\n")
            
            # جدول المقارنة
            f.write("| Test | n_trades | avg_pnl | WR% | PF | Sharpe | MaxDD | final |\n")
            f.write("|------|----------|---------|-----|----|----|-------|-------|\n")
            
            for name in names:
                m = results.get(name)
                if m is None:
                    f.write(f"| {name} | — | — | — | — | — | — | — |\n")
                    continue
                f.write(
                    f"| {name} | {m['n']:,} | "
                    f"${m['avg_pnl']:.2f} | "
                    f"{m['wr']:.1f}% | "
                    f"{m['pf']:.3f} | "
                    f"{m['sharpe']:.3f} | "
                    f"{m['max_dd']:.1f}% | "
                    f"${m['final_capital']:,.0f} |\n"
                )
            f.write("\n")
            
            # BUY vs SELL
            f.write("### BUY vs SELL breakdown\n\n")
            f.write("| Test | BUY_n | BUY_avg | BUY_WR | SELL_n | SELL_avg | SELL_WR |\n")
            f.write("|------|-------|---------|--------|--------|----------|---------|\n")
            for name in names:
                m = results.get(name)
                if m is None:
                    continue
                b = m.get("buy", {})
                s = m.get("sell", {})
                f.write(
                    f"| {name} | "
                    f"{b.get('n', 0):,} | ${b.get('avg', 0):.2f} | "
                    f"{b.get('wr', 0):.1f}% | "
                    f"{s.get('n', 0):,} | ${s.get('avg', 0):.2f} | "
                    f"{s.get('wr', 0):.1f}% |\n"
                )
            f.write("\n")
            
            # Exit reasons
            f.write("### Exit Distribution\n\n")
            all_exits = set()
            for name in names:
                m = results.get(name)
                if m:
                    all_exits.update(m.get("exits", {}).keys())
            all_exits = sorted(all_exits)
            
            f.write("| Test | " + " | ".join(all_exits) + " |\n")
            f.write("|------|" + "|".join(["------"] * len(all_exits)) + "|\n")
            for name in names:
                m = results.get(name)
                if m is None:
                    continue
                cells = []
                n = m["n"]
                for ex in all_exits:
                    cnt = m.get("exits", {}).get(ex, 0)
                    pct = cnt / n * 100 if n > 0 else 0
                    cells.append(f"{cnt} ({pct:.0f}%)")
                f.write(f"| {name} | " + " | ".join(cells) + " |\n")
            f.write("\n")
        
        # القرار النهائي
        f.write("## Final Decision\n\n")
        
        # ابحث عن الأفضل
        valid = [(k, v) for k, v in results.items() if v is not None]
        if valid:
            valid.sort(key=lambda x: x[1]["sharpe"], reverse=True)
            top = valid[0]
            f.write(f"**Best Sharpe:** `{top[0]}` — "
                    f"Sharpe={top[1]['sharpe']:.3f}, "
                    f"avg=${top[1]['avg_pnl']:.2f}, "
                    f"PF={top[1]['pf']:.3f}, "
                    f"n={top[1]['n']:,}\n\n")
            
            valid_avg = sorted(valid, key=lambda x: x[1]["avg_pnl"], reverse=True)
            top_avg = valid_avg[0]
            f.write(f"**Best avg_pnl:** `{top_avg[0]}` — "
                    f"avg=${top_avg[1]['avg_pnl']:.2f}, "
                    f"Sharpe={top_avg[1]['sharpe']:.3f}, "
                    f"n={top_avg[1]['n']:,}\n\n")
            
            # المقارنة مع baseline
            for group in groups:
                baseline_key = f"baseline_{group}"
                if baseline_key in results:
                    base = results[baseline_key]
                    f.write(f"### Group {group} — Baseline vs Best\n\n")
                    f.write(f"- Baseline: avg=${base['avg_pnl']:.2f}, "
                            f"Sharpe={base['sharpe']:.3f}, "
                            f"n={base['n']:,}\n")
                    
                    best_in_group = max(
                        [n for n in groups[group] if results.get(n)],
                        key=lambda n: results[n]["sharpe"],
                        default=None,
                    )
                    if best_in_group and best_in_group != baseline_key:
                        bm = results[best_in_group]
                        imp_avg = (bm["avg_pnl"] / base["avg_pnl"] - 1) * 100 \
                                  if base["avg_pnl"] != 0 else 0
                        imp_sh = (bm["sharpe"] - base["sharpe"])
                        f.write(f"- Best: `{best_in_group}` — "
                                f"avg=${bm['avg_pnl']:.2f} ({imp_avg:+.1f}%), "
                                f"Sharpe={bm['sharpe']:.3f} ({imp_sh:+.3f})\n\n")
        
        f.write("---\n\n")
        f.write("*Generated by run_all_tests.py*\n")
    
    print(f"\n📄 Report saved: {report_path}")
    return report_path


# ═══════════════════════════════════════════════════════════════
# § 8 — main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Automated Backtest Suite")
    parser.add_argument("--quick", action="store_true",
                        help="90d only (fast mode)")
    parser.add_argument("--resume", action="store_true",
                        help="Skip completed tests")
    parser.add_argument("--list", action="store_true",
                        help="List configs and exit")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Only analyze existing trades files")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel workers (default 1)")
    args = parser.parse_args()
    
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    configs = build_configs(quick=args.quick)
    
    if args.list:
        print(f"Total configs: {len(configs)}")
        for c in configs:
            print(f"  [{c['group']:<5}] {c['name']}")
        return
    
    print("█" * 80)
    print(f"  AUTOMATED BACKTEST SUITE")
    print(f"  Total configs: {len(configs)}")
    print(f"  Results dir: {RESULTS_DIR}")
    print(f"  Timeout: {TIMEOUT_MINUTES} min/config")
    print("█" * 80)
    print()
    
    # ── التشغيل ──
    if not args.analyze_only:
        t_start = time.time()
        
        # Resume: تخطّي المكتمل
        pending = configs
        if args.resume:
            pending = [c for c in configs if not is_completed(c["name"])]
            skipped = len(configs) - len(pending)
            if skipped > 0:
                print(f"Resume: skipping {skipped} completed configs")
        
        if pending:
            print(f"\nRunning {len(pending)} tests...\n")
            
            if args.workers > 1:
                # متوازي
                with ThreadPoolExecutor(max_workers=args.workers) as ex:
                    futures = {ex.submit(run_single_backtest, c): c
                               for c in pending}
                    for fut in as_completed(futures):
                        name, status, err = fut.result()
                        if status != "ok":
                            print(f"    ❌ {name}: {err}")
            else:
                # تسلسلي
                for c in pending:
                    name, status, err = run_single_backtest(c)
                    if status != "ok":
                        print(f"    ❌ {name}: {err}")
        
        elapsed = time.time() - t_start
        print(f"\n⏱️  Total time: {elapsed/60:.1f} min")
    
    # ── التحليل ──
    print("\n" + "=" * 80)
    print("ANALYZING RESULTS")
    print("=" * 80)
    
    results = {}
    for c in configs:
        name = c["name"]
        print(f"  Analyzing: {name} ...")
        m = analyze_and_save(name)
        if m is not None:
            results[name] = m
    
    # ── التقرير ──
    print()
    generate_report(configs, results)
    
    # ── طباعة موجزة ──
    print("\n" + "=" * 80)
    print("QUICK SUMMARY")
    print("=" * 80)
    for group in sorted(set(c["group"] for c in configs)):
        print(f"\n── Group {group} ──")
        for c in [x for x in configs if x["group"] == group]:
            name = c["name"]
            m = results.get(name)
            if m is None:
                print(f"  {name:<25} — no data")
                continue
            print(f"  {name:<25} "
                  f"n={m['n']:>5} "
                  f"avg=${m['avg_pnl']:>8.2f} "
                  f"WR={m['wr']:>5.1f}% "
                  f"PF={m['pf']:>5.3f} "
                  f"Sharpe={m['sharpe']:>5.3f}")
    
    print()
    print(f"📄 Full report: {os.path.join(RESULTS_DIR, 'FINAL_REPORT.md')}")
    print("✅ Done.")


if __name__ == "__main__":
    main()
