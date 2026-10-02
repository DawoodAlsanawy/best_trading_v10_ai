#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_CSD_v2.py — Critical Slowing Down Hypothesis Test
========================================================
Auto-discovers trade log file and computes Criticality Index.
"""

import json
import os
import sys
import glob
import numpy as np

# ═══════════════════════════════════════════════════════════════
# 1. اكتشاف ملف الـ trades
# ═══════════════════════════════════════════════════════════════
def find_trades_file():
    """يبحث عن أكبر ملف jsonl في المجلد الحالي."""
    candidates = []
    
    # ملفات jsonl في المجلد الحالي
    for pattern in ["trades*.jsonl", "*_trades*.jsonl", "*.jsonl"]:
        for f in glob.glob(pattern):
            if os.path.isfile(f):
                size = os.path.getsize(f)
                # احصل على عدد الأسطر
                try:
                    with open(f) as fh:
                        n_lines = sum(1 for _ in fh)
                except Exception:
                    n_lines = 0
                if n_lines > 10:
                    candidates.append((f, size, n_lines))
    
    if not candidates:
        return None
    
    # اختر الأكبر بـ n_lines
    candidates.sort(key=lambda x: -x[2])
    
    print("Files found:")
    for f, size, n in candidates[:10]:
        print(f"  {f:<50} {n:>8} lines, {size/1e6:>7.1f} MB")
    print()
    
    # لو الملف الافتراضي موجود، استخدمه أولاً
    for f, _, _ in candidates:
        if f == "trades_log_backtest.jsonl":
            return f
    
    # وإلا اختر الأكبر
    return candidates[0][0]


# ═══════════════════════════════════════════════════════════════
# 2. القيم الافتراضية
# ═══════════════════════════════════════════════════════════════
DEFAULT_DYN_K = 8
DEFAULT_H_MAX = np.log2(DEFAULT_DYN_K)  # ≈ 3.0


# ═══════════════════════════════════════════════════════════════
# 3. تحميل الصفقات
# ═══════════════════════════════════════════════════════════════
def load_trades(path):
    trades = []
    errors = 0
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
                errors += 1
    print(f"Loaded: {len(trades)} trades (errors: {errors})")
    return trades


# ═══════════════════════════════════════════════════════════════
# 4. حساب Criticality Index
# ═══════════════════════════════════════════════════════════════
def compute_CI(t):
    """
    CI = T_info × (1 − H/H_max) × E_therm
    
    يستخدم الحقول الموجودة فعلاً في الـ trades log:
      - T_info_val
      - H_over_Hmax  ← موجود جاهزاً
      - E_therm
    """
    try:
        T_info = float(t.get("T_info_val", 0) or 0)
        E_therm = float(t.get("E_therm", 0) or 0)
        
        # استخدم H_over_Hmax إن وُجد، وإلا احسبه
        H_ratio = t.get("H_over_Hmax")
        if H_ratio is None:
            H = float(t.get("H", 0) or 0)
            dyn_k = max(int(t.get("dynamic_k", DEFAULT_DYN_K)), 2)
            H_max = np.log2(dyn_k)
            H_ratio = H / max(H_max, 1e-9)
        H_ratio = float(H_ratio)
        
        # clip
        H_ratio = max(0.0, min(1.0, H_ratio))
        order = 1.0 - H_ratio
        
        CI = T_info * order * E_therm
        return CI
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# 5. التحليل
# ═══════════════════════════════════════════════════════════════
def analyze(trades):
    pairs = []  # (CI, pnl)
    missing = {"T_info_val": 0, "E_therm": 0, "H_ratio": 0}
    
    for t in trades:
        ci = compute_CI(t)
        if ci is None or not np.isfinite(ci):
            continue
        pnl = float(t.get("net_pnl", 0) or 0)
        pairs.append((ci, pnl))
        
        if "T_info_val" not in t: missing["T_info_val"] += 1
        if "E_therm" not in t: missing["E_therm"] += 1
        if "H_over_Hmax" not in t and "H" not in t: missing["H_ratio"] += 1
    
    if len(pairs) < 20:
        print(f"⚠️  Only {len(pairs)} valid trades — need ≥ 20")
        print(f"Missing fields: {missing}")
        return None
    
    pairs.sort(key=lambda x: x[0])
    cis = np.array([p[0] for p in pairs])
    pnls = np.array([p[1] for p in pairs])
    n = len(pnls)
    
    print(f"\nValid trades: {n}")
    print(f"CI range: [{cis.min():.6f}, {cis.max():.6f}]")
    print(f"CI median: {np.median(cis):.6f}")
    print()
    
    # 3 buckets
    q70 = int(n * 0.70)
    q90 = int(n * 0.90)
    
    low = pnls[:q70]
    mid = pnls[q70:q90]
    high = pnls[q90:]
    
    def _stats(arr):
        if len(arr) == 0:
            return 0.0, 0.0
        return float(arr.mean()), float((arr > 0).mean() * 100)
    
    low_m, low_w = _stats(low)
    mid_m, mid_w = _stats(mid)
    high_m, high_w = _stats(high)
    
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"{'Group':<20} {'n':>6} {'avg_pnl':>12} {'WR':>8}")
    print("-" * 70)
    print(f"{'Q1-Q7 (low CI)':<20} {len(low):>6} ${low_m:>10.2f} {low_w:>7.1f}%")
    print(f"{'Q7-Q9 (mid CI)':<20} {len(mid):>6} ${mid_m:>10.2f} {mid_w:>7.1f}%")
    print(f"{'Q9-Q10 (high CI)':<20} {len(high):>6} ${high_m:>10.2f} {high_w:>7.1f}%")
    print("-" * 70)
    
    # إضافي: نسبة عالية مقابل منخفضة
    if abs(low_m) > 1e-9:
        ratio = high_m / low_m if low_m != 0 else float('inf')
    else:
        ratio = float('inf')
    print(f"\nHigh/Low avg_pnl ratio: {ratio:.2f}×")
    print()
    
    if ratio > 2.0:
        print("✅ HYPOTHESIS SUPPORTED: High CI has 2×+ better performance")
        print("   → Implement Critical Transition Trading")
    elif ratio > 1.3:
        print("⚠️  WEAK SUPPORT: High CI is somewhat better")
        print("   → Test with smaller filter threshold")
    else:
        print("❌ HYPOTHESIS NOT SUPPORTED: CI does not discriminate")
        print("   → Focus on Breakeven only")
    
    return {"low": (low_m, low_w), "mid": (mid_m, mid_w),
            "high": (high_m, high_w), "ratio": ratio}


# ═══════════════════════════════════════════════════════════════
# 6. main
# ═══════════════════════════════════════════════════════════════
def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_trades_file()
    if path is None or not os.path.exists(path):
        print("❌ No trades log found")
        print("Usage: python verify_CSD_v2.py [path_to_trades.jsonl]")
        return
    
    print(f"Using: {path}")
    print()
    
    trades = load_trades(path)
    if not trades:
        print("❌ No trades loaded")
        return
    
    # افحص الحقول الموجودة
    sample = trades[0]
    print("Sample fields:", sorted(sample.keys())[:20], "...")
    print()
    
    analyze(trades)


if __name__ == "__main__":
    main()
