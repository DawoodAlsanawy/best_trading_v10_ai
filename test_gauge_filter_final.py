#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_gauge_filter_final.py
==========================
اختبار شامل وكامل لفلتر Gauge على صفقات الـ backtest.

يغطي:
  1. تشخيص الإعدادات الفعلية
  2. تحليل Gauge عبر deciles (BUY و SELL منفصلين)
  3. تطبيق 3 عتبات مختلفة (p50, p60, p70)
  4. مقارنة قبل/بعد
  5. اختبار على فترات زمنية متعددة (شهري/ربع سنوي)
  6. حساب المؤشرات الكاملة (PF, WR, Sharpe, DD)
  7. قرار نهائي: هل نطبّق الفلتر؟

الاستخدام:
    python test_gauge_filter_final.py [trades_file.jsonl]
"""

import sys
import os
import json
import glob
import numpy as np
from collections import defaultdict
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# § 1 — اكتشاف ملف الـ trades
# ═══════════════════════════════════════════════════════════════

def find_best_trades_file():
    """يبحث عن أكبر ملف trades*.jsonl في المجلد الحالي."""
    candidates = []
    for pattern in ["trades*.jsonl", "*.jsonl"]:
        for f in glob.glob(pattern):
            if not os.path.isfile(f):
                continue
            try:
                size = os.path.getsize(f)
                with open(f) as fh:
                    n = sum(1 for _ in fh)
                if n > 100:
                    candidates.append((f, size, n))
            except Exception:
                pass
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[2])
    return candidates[0][0]


# ═══════════════════════════════════════════════════════════════
# § 2 — تحميل الصفقات
# ═══════════════════════════════════════════════════════════════

def load_trades(path):
    trades, meta = [], None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("_meta"):
                    meta = r
                    continue
                trades.append(r)
            except Exception:
                pass
    return trades, meta


# ═══════════════════════════════════════════════════════════════
# § 3 — تشخيص الإعدادات
# ═══════════════════════════════════════════════════════════════

def diagnose_config(meta, trades):
    print("=" * 90)
    print("SECTION 1 — CONFIGURATION DIAGNOSIS")
    print("=" * 90)
    if meta:
        for k in ["mode", "timeframe", "INITIAL_CAPITAL", "N", "W", "L",
                  "K_MIN", "K_MAX", "LEVERAGE_BASE", "PO_FIXED_PRICE",
                  "started_at"]:
            if k in meta:
                print(f"  {k:<25} = {meta[k]}")
    
    # استخرج dynamic_k الفعلي
    dyn_ks = [int(t.get("dynamic_k", 0)) for t in trades
              if t.get("dynamic_k")]
    if dyn_ks:
        print(f"\n  dynamic_k distribution:")
        print(f"    min  = {min(dyn_ks)}")
        print(f"    max  = {max(dyn_ks)}")
        print(f"    mean = {np.mean(dyn_ks):.1f}")
        uniq = sorted(set(dyn_ks))
        if len(uniq) < 15:
            print(f"    values = {uniq}")
    else:
        print(f"\n  ⚠️  dynamic_k غير موجود في السجل")
    print()


# ═══════════════════════════════════════════════════════════════
# § 4 — استخراج الميزات
# ═══════════════════════════════════════════════════════════════

def extract_features(trades):
    """يستخرج كل الميزات في numpy arrays."""
    feat = {
        "gauge": np.array([float(t.get("gauge_force", 0) or 0)
                           for t in trades]),
        "pnl": np.array([float(t.get("net_pnl", 0) or 0)
                         for t in trades]),
        "action": np.array([t.get("action", "?") for t in trades]),
        "symbol": np.array([t.get("symbol", "?") for t in trades]),
        "entry_time": np.array([t.get("entry_time", "") for t in trades]),
        "is_win": np.array([bool(t.get("is_win", False))
                            for t in trades]),
        "mfe": np.array([float(t.get("mfe_frac", 0) or 0)
                         for t in trades]),
        "hold_bars": np.array([int(t.get("hold_bars", 0) or 0)
                               for t in trades]),
        "sl_dist": np.array([float(t.get("sl_dist_frac", 0) or 0)
                             for t in trades]),
        "score": np.array([float(t.get("score", 0) or 0)
                           for t in trades]),
        "T_info": np.array([float(t.get("T_info_val", 0) or 0)
                            for t in trades]),
        "E_therm": np.array([float(t.get("E_therm", 0) or 0)
                             for t in trades]),
        "H_ratio": np.array([float(t.get("H_over_Hmax", 0) or 0)
                             for t in trades]),
    }
    return feat


# ═══════════════════════════════════════════════════════════════
# § 5 — حساب المؤشرات الكاملة
# ═══════════════════════════════════════════════════════════════

def compute_metrics(pnls, is_win, label=""):
    """يحسب كل المؤشرات لسلة صفقات."""
    n = len(pnls)
    if n == 0:
        return None
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    
    wr = len(wins) / n * 100 if n > 0 else 0
    pf = (wins.sum() / abs(losses.sum())) if losses.sum() < 0 else float('inf')
    avg_pnl = pnls.mean()
    avg_win = wins.mean() if len(wins) > 0 else 0
    avg_loss = losses.mean() if len(losses) > 0 else 0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    total = pnls.sum()
    
    # Sharpe pseudo
    std_pnl = pnls.std(ddof=1) if n > 1 else 0
    sharpe = (avg_pnl / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0
    
    return {
        "n": n,
        "wr": wr,
        "pf": pf,
        "avg_pnl": avg_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": payoff,
        "total": total,
        "sharpe": sharpe,
        "std": std_pnl,
    }


# ═══════════════════════════════════════════════════════════════
# § 6 — القسم 1: Gauge Decile Analysis
# ═══════════════════════════════════════════════════════════════

def section_gauge_deciles(feat):
    print("=" * 90)
    print("SECTION 2 — GAUGE DECILE ANALYSIS (BUY vs SELL)")
    print("=" * 90)
    
    for action in ["BUY", "SELL"]:
        mask_act = feat["action"] == action
        if mask_act.sum() < 50:
            continue
        
        gauge_act = feat["gauge"][mask_act]
        pnl_act = feat["pnl"][mask_act]
        
        # Deciles
        qs = np.percentile(gauge_act, [10, 20, 30, 40, 50, 60, 70, 80, 90])
        
        print(f"\n  ── {action} (n={mask_act.sum()}) ──")
        print(f"  {'Decile':<10} {'n':>6} {'avg_pnl':>12} {'WR%':>7} {'total':>14}")
        print("  " + "-" * 55)
        
        prev = -np.inf
        for i, q in enumerate(qs):
            m = (gauge_act > prev) & (gauge_act <= q)
            prev = q
            if m.sum() == 0:
                continue
            p = pnl_act[m]
            print(f"  D{i+1:<9} {m.sum():>6} "
                  f"${p.mean():>10.2f} "
                  f"{(p > 0).mean()*100:>6.1f}% "
                  f"${p.sum():>12,.0f}")
        
        m = gauge_act > qs[-1]
        if m.sum() > 0:
            p = pnl_act[m]
            print(f"  D10{'':<7} {m.sum():>6} "
                  f"${p.mean():>10.2f} "
                  f"{(p > 0).mean()*100:>6.1f}% "
                  f"${p.sum():>12,.0f}")
    print()


# ═══════════════════════════════════════════════════════════════
# § 7 — القسم 2: Filter Comparison
# ═══════════════════════════════════════════════════════════════

def section_filter_comparison(feat):
    print("=" * 90)
    print("SECTION 3 — FILTER THRESHOLD COMPARISON")
    print("=" * 90)
    
    # Baseline
    base_metrics = compute_metrics(feat["pnl"], feat["is_win"])
    print(f"\n  BASELINE (no filter):")
    print(f"    n={base_metrics['n']}, avg=${base_metrics['avg_pnl']:.2f}, "
          f"WR={base_metrics['wr']:.1f}%, PF={base_metrics['pf']:.3f}, "
          f"Sharpe={base_metrics['sharpe']:.3f}")
    
    # Thresholds to test
    for action_filter in ["ALL", "BUY", "SELL"]:
        if action_filter == "ALL":
            act_mask = np.ones(len(feat["pnl"]), dtype=bool)
            title = "ALL ACTIONS"
        else:
            act_mask = feat["action"] == action_filter
            title = f"{action_filter} ONLY"
        
        if act_mask.sum() < 100:
            continue
        
        gauge_sub = feat["gauge"][act_mask]
        pnl_sub = feat["pnl"][act_mask]
        win_sub = feat["is_win"][act_mask]
        
        print(f"\n  ── {title} (n={act_mask.sum()}) ──")
        print(f"  {'Threshold':<20} {'n':>6} {'avg_pnl':>12} "
              f"{'WR%':>7} {'PF':>7} {'Sharpe':>8} {'total':>14}")
        print("  " + "-" * 78)
        
        for pct in [0, 50, 60, 70, 80, 90]:
            thr = np.percentile(gauge_sub, pct)
            m = gauge_sub > thr
            if m.sum() < 30:
                continue
            metrics = compute_metrics(pnl_sub[m], win_sub[m])
            if metrics is None:
                continue
            tag = f"top {100-pct}%" if pct > 0 else "all"
            print(f"  {tag:<20} {metrics['n']:>6} "
                  f"${metrics['avg_pnl']:>10.2f} "
                  f"{metrics['wr']:>6.1f}% "
                  f"{metrics['pf']:>6.3f} "
                  f"{metrics['sharpe']:>7.3f} "
                  f"${metrics['total']:>12,.0f}")
    print()


# ═══════════════════════════════════════════════════════════════
# § 8 — القسم 3: Time Period Validation
# ═══════════════════════════════════════════════════════════════

def section_time_periods(feat, threshold_pct=0.60):
    """يختبر الفلتر على فترات زمنية متعددة."""
    print("=" * 90)
    print(f"SECTION 4 — TIME PERIOD VALIDATION (threshold = p{int(threshold_pct*100)})")
    print("=" * 90)
    
    # استخرج السنة-الشهر من entry_time
    months = np.array([str(t)[:7] for t in feat["entry_time"]])
    unique_months = sorted(set(months))
    
    if len(unique_months) < 3:
        print("  ⚠️  أقل من 3 أشهر — لا يمكن التحقق")
        return
    
    # عتبة Gauge العالمية
    thr_global = np.percentile(feat["gauge"], threshold_pct * 100)
    thr_buy = np.percentile(feat["gauge"][feat["action"] == "BUY"],
                            threshold_pct * 100)
    thr_sell = np.percentile(feat["gauge"][feat["action"] == "SELL"],
                             threshold_pct * 100)
    
    print(f"\n  Global thresholds:")
    print(f"    p{int(threshold_pct*100)} overall = {thr_global:.5f}")
    print(f"    p{int(threshold_pct*100)} BUY     = {thr_buy:.5f}")
    print(f"    p{int(threshold_pct*100)} SELL    = {thr_sell:.5f}")
    
    print(f"\n  {'Month':<10} {'n_all':>7} {'avg_all':>10} "
          f"{'n_filt':>7} {'avg_filt':>10} {'improve':>9}")
    print("  " + "-" * 60)
    
    improvements = []
    for m in unique_months:
        mask_m = months == m
        if mask_m.sum() < 20:
            continue
        pnl_all = feat["pnl"][mask_m]
        
        # تطبيق فلتر مزدوج (BUY يستخدم عتبته، SELL يستخدم عتبته)
        gauge_m = feat["gauge"][mask_m]
        action_m = feat["action"][mask_m]
        
        keep = np.zeros(mask_m.sum(), dtype=bool)
        for i, act in enumerate(action_m):
            if act == "BUY" and gauge_m[i] > thr_buy:
                keep[i] = True
            elif act == "SELL" and gauge_m[i] > thr_sell:
                keep[i] = True
        
        pnl_filt = pnl_all[keep]
        if len(pnl_filt) < 5 or len(pnl_all) < 10:
            continue
        
        avg_all = pnl_all.mean()
        avg_filt = pnl_filt.mean()
        
        if avg_all > 0:
            improve = (avg_filt / avg_all - 1) * 100
        else:
            improve = 0
        
        improvements.append(improve)
        
        print(f"  {m:<10} {len(pnl_all):>7} ${avg_all:>8.2f} "
              f"{len(pnl_filt):>7} ${avg_filt:>8.2f} "
              f"{improve:>+7.1f}%")
    
    if improvements:
        improvements = np.array(improvements)
        n_improved = (improvements > 0).sum()
        n_total = len(improvements)
        median_impr = np.median(improvements)
        
        print()
        print(f"  ── Summary ──")
        print(f"    Periods improved: {n_improved}/{n_total} "
              f"({n_improved/n_total*100:.0f}%)")
        print(f"    Median improvement: {median_impr:+.1f}%")
        
        if n_improved >= n_total * 0.6:
            print(f"  ✅ STABLE: filter improves in ≥60% of periods")
        else:
            print(f"  ❌ UNSTABLE: filter fails in many periods")
    print()


# ═══════════════════════════════════════════════════════════════
# § 9 — القسم 4: Final Decision
# ═══════════════════════════════════════════════════════════════

def section_final_decision(feat):
    print("=" * 90)
    print("SECTION 5 — FINAL DECISION MATRIX")
    print("=" * 90)
    
    # baseline
    base = compute_metrics(feat["pnl"], feat["is_win"])
    
    # أفضل 3 تركيزات
    scenarios = []
    
    # 1) BUY + gauge>p60 فقط
    thr_buy = np.percentile(feat["gauge"][feat["action"] == "BUY"], 60)
    m = (feat["action"] == "BUY") & (feat["gauge"] > thr_buy)
    m_all = m  # BUY only
    scenarios.append(("BUY+gauge>p60", compute_metrics(
        feat["pnl"][m], feat["is_win"][m])))
    
    # 2) BUY + gauge>p60, SELL بدون فلتر
    m = (feat["action"] == "SELL") | (
        (feat["action"] == "BUY") & (feat["gauge"] > thr_buy)
    )
    scenarios.append(("BUY+filter, SELL unfiltered",
                       compute_metrics(feat["pnl"][m], feat["is_win"][m])))
    
    # 3) BUY + gauge>p60, SELL + gauge>p85
    thr_sell = np.percentile(feat["gauge"][feat["action"] == "SELL"], 85)
    m = (((feat["action"] == "BUY") & (feat["gauge"] > thr_buy)) |
         ((feat["action"] == "SELL") & (feat["gauge"] > thr_sell)))
    scenarios.append(("BUY+filter, SELL strict-filter",
                       compute_metrics(feat["pnl"][m], feat["is_win"][m])))
    
    # 4) BUY + gauge>p70, SELL + gauge>p85 (متشدد)
    thr_buy_strict = np.percentile(feat["gauge"][feat["action"] == "BUY"], 70)
    m = (((feat["action"] == "BUY") & (feat["gauge"] > thr_buy_strict)) |
         ((feat["action"] == "SELL") & (feat["gauge"] > thr_sell)))
    scenarios.append(("BUY+filter strict, SELL strict",
                       compute_metrics(feat["pnl"][m], feat["is_win"][m])))
    
    # طبع المقارنة
    print(f"\n  {'Scenario':<35} {'n':>6} {'avg$':>9} "
          f"{'WR%':>6} {'PF':>6} {'Sharpe':>8} {'total$':>13}")
    print("  " + "-" * 90)
    
    b_n, b_avg, b_wr = base["n"], base["avg_pnl"], base["wr"]
    b_pf, b_sharpe, b_total = base["pf"], base["sharpe"], base["total"]
    
    print(f"  {'BASELINE (all)':<35} {b_n:>6} ${b_avg:>7.2f} "
          f"{b_wr:>5.1f}% {b_pf:>6.3f} {b_sharpe:>7.3f} "
          f"${b_total:>11,.0f}")
    print("  " + "-" * 90)
    
    for name, m in scenarios:
        if m is None:
            continue
        print(f"  {name:<35} {m['n']:>6} ${m['avg_pnl']:>7.2f} "
              f"{m['wr']:>5.1f}% {m['pf']:>6.3f} {m['sharpe']:>7.3f} "
              f"${m['total']:>11,.0f}")
    
    # القرار
    print()
    print("  ── DECISION CRITERIA ──")
    
    best = max(scenarios, key=lambda x: x[1]["avg_pnl"]
               if x[1] is not None else 0)
    best_name, best_m = best
    
    if best_m is None:
        print("  ❌ All scenarios failed")
        return
    
    improvement = (best_m["avg_pnl"] / b_avg - 1) * 100 if b_avg != 0 else 0
    
    print(f"\n  Best scenario: {best_name}")
    print(f"    avg_pnl : ${b_avg:.2f} → ${best_m['avg_pnl']:.2f} "
          f"({improvement:+.1f}%)")
    print(f"    WR      : {b_wr:.1f}% → {best_m['wr']:.1f}%")
    print(f"    PF      : {b_pf:.3f} → {best_m['pf']:.3f}")
    print(f"    Sharpe  : {b_sharpe:.3f} → {best_m['sharpe']:.3f}")
    print(f"    n       : {b_n} → {best_m['n']} "
          f"({best_m['n']/b_n*100:.0f}% retained)")
    print()
    
    # توصية
    if best_m["avg_pnl"] > b_avg * 1.3 and best_m["pf"] > 1.0:
        print(f"  ✅ RECOMMEND: Apply '{best_name}'")
        print(f"     Gauge filter adds significant value")
    elif best_m["pf"] > 1.0:
        print(f"  ⚠️  MARGINAL: Apply with caution")
        print(f"     Filter improves PF but avg not strong")
    else:
        print(f"  ❌ NOT RECOMMENDED: PF still < 1.0")
        print(f"     Revisit base strategy first")
    print()


# ═══════════════════════════════════════════════════════════════
# § 10 — main
# ═══════════════════════════════════════════════════════════════

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_best_trades_file()
    
    if path is None or not os.path.exists(path):
        print("❌ No trades file found")
        print("Usage: python test_gauge_filter_final.py <file.jsonl>")
        return
    
    print("█" * 90)
    print("  GAUGE FILTER — FINAL VALIDATION")
    print(f"  File: {path}")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█" * 90)
    print()
    
    trades, meta = load_trades(path)
    print(f"Loaded {len(trades):,} trades\n")
    
    if len(trades) < 100:
        print("❌ Not enough trades")
        return
    
    diagnose_config(meta, trades)
    
    feat = extract_features(trades)
    
    section_gauge_deciles(feat)
    section_filter_comparison(feat)
    section_time_periods(feat, threshold_pct=0.60)
    section_final_decision(feat)
    
    print("=" * 90)
    print("END OF VALIDATION")
    print("=" * 90)


if __name__ == "__main__":
    main()
