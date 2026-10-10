# verify_BUY_only.py
import json
import numpy as np

with open("trades_CSD_test.jsonl") as f:
    trades = [json.loads(l) for l in f if not json.loads(l).get("_meta")]

# ── استخراج ──
gauge = np.array([float(t.get("gauge_force", 0) or 0) for t in trades])
pnls = np.array([float(t.get("net_pnl", 0) or 0) for t in trades])
actions = np.array([t.get("action", "?") for t in trades])

print("=" * 80)
print("BUY-ONLY with GAUGE FILTER")
print("=" * 80)

buy_mask = actions == "BUY"
gauge_buy = gauge[buy_mask]
pnls_buy = pnls[buy_mask]

print(f"\nTotal BUY trades: {buy_mask.sum()}")
print(f"BUY WR: {(pnls_buy > 0).mean()*100:.2f}%")
print(f"BUY avg_pnl: ${pnls_buy.mean():.2f}")

# Gauge bands
print(f"\n{'Band':<20} {'n':>6} {'avg_pnl':>12} {'WR':>8} {'total':>14}")
print("-" * 80)

for name, lo, hi in [
    ("Gauge < p50", 0, 50),
    ("p50-p70", 50, 70),
    ("p70-p80", 70, 80),
    ("p80-p90", 80, 90),
    ("p90-p95", 90, 95),
    ("p95-p100 (top 5%)", 95, 100),
]:
    lo_v = np.percentile(gauge_buy, lo)
    hi_v = np.percentile(gauge_buy, hi)
    mask = (gauge_buy >= lo_v) & (gauge_buy < hi_v)
    if mask.sum() == 0:
        continue
    p = pnls_buy[mask]
    print(f"{name:<20} {mask.sum():>6} "
          f"${p.mean():>10.2f} "
          f"{(p > 0).mean()*100:>7.1f}% "
          f"${p.sum():>12,.0f}")

# Compare filter thresholds
print()
print("=" * 80)
print("FILTER COMPARISON — BUY only")
print("=" * 80)
print(f"{'Threshold':<20} {'n':>6} {'avg_pnl':>12} {'WR':>8} {'total':>14}")
print("-" * 80)

for pct in [50, 60, 70, 75, 80, 85, 90, 95]:
    thr = np.percentile(gauge_buy, pct)
    mask = gauge_buy > thr
    p = pnls_buy[mask]
    print(f"Top {100-pct}% (gauge>{pct}): "
          f"{mask.sum():>6} ${p.mean():>10.2f} "
          f"{(p > 0).mean()*100:>7.1f}% ${p.sum():>12,.0f}")

# ── نسبة استرجاع الذيل الرابح ──
print()
print("=" * 80)
print("TAIL CAPTURE ANALYSIS")
print("=" * 80)
print("الهدف: كم من الأرباح الكلية نستطيع الاحتفاظ بها عند تصفية")
print()

for pct in [50, 70, 80, 90]:
    thr = np.percentile(gauge_buy, pct)
    mask = gauge_buy > thr
    p = pnls_buy[mask]
    
    total_all = pnls_buy[pnls_buy > 0].sum()
    total_filtered = p[p > 0].sum()
    capture = total_filtered / total_all * 100
    
    loss_all = abs(pnls_buy[pnls_buy < 0].sum())
    loss_filtered = abs(p[p < 0].sum())
    loss_reduction = (1 - loss_filtered / loss_all) * 100
    
    print(f"Top {100-pct}%: "
          f"captures {capture:.1f}% of profits, "
          f"reduces {loss_reduction:.1f}% of losses")
