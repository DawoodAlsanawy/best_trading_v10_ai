# verify_gauge_score.py
import json
import numpy as np
from scipy.stats import rankdata

with open("trades_CSD_test.jsonl") as f:
    trades = [json.loads(l) for l in f if not json.loads(l).get("_meta")]

print(f"Loaded: {len(trades)} trades\n")

# ── 1. استخراج الميزات ──
gauge = np.array([float(t.get("gauge_force", 0) or 0) for t in trades])
dist_ema = np.array([abs(float(t.get("dist_from_ema_norm", 0) or 0)) for t in trades])
t_info = np.array([float(t.get("T_info_val", 0) or 0) for t in trades])
e_therm = np.array([float(t.get("E_therm", 0) or 0) for t in trades])
pnls = np.array([float(t.get("net_pnl", 0) or 0) for t in trades])
actions = np.array([t.get("action", "?") for t in trades])

# ── 2. تحويل إلى مراتب مئوية (percentile rank) ──
# هذا يجنّبنا مشكلة اختلاف المقاييس
rank_gauge = rankdata(gauge) / len(gauge)
rank_dist = rankdata(dist_ema) / len(dist_ema)
rank_tinfo = rankdata(t_info) / len(t_info)
rank_etherm = rankdata(e_therm) / len(e_therm)

# ── 3. Composite Gauge Score ──
CGS = (
    1.00 * rank_gauge +
    0.50 * rank_dist +
    0.30 * rank_tinfo +
    0.30 * rank_etherm
)
CGS /= CGS.max()  # التطبيع إلى [0, 1]

print("=" * 80)
print("COMPOSITE GAUGE SCORE (CGS) — QUINTILE ANALYSIS")
print("=" * 80)
print(f"{'Quintile':<12} {'n':>6} {'avg_pnl':>12} {'WR':>8} {'tot_pnl':>14}")
print("-" * 80)

# 5 quintiles
qs = np.percentile(CGS, [20, 40, 60, 80])
buckets = [
    ("Q1 (worst)", CGS <= qs[0]),
    ("Q2", (CGS > qs[0]) & (CGS <= qs[1])),
    ("Q3", (CGS > qs[1]) & (CGS <= qs[2])),
    ("Q4", (CGS > qs[2]) & (CGS <= qs[3])),
    ("Q5 (best)", CGS > qs[3]),
]

for name, mask in buckets:
    if mask.sum() == 0:
        continue
    p = pnls[mask]
    print(f"{name:<12} {len(p):>6} "
          f"${p.mean():>10.2f} {(p > 0).mean()*100:>7.1f}% "
          f"${p.sum():>12,.0f}")

print()

# ── 4. Top 30% only ──
thr_70 = np.percentile(CGS, 70)
top_mask = CGS >= thr_70
p_top = pnls[top_mask]
print("=" * 80)
print("TOP 30% ONLY (CGS ≥ p70)")
print("=" * 80)
print(f"n_trades      : {top_mask.sum()}")
print(f"avg_pnl       : ${p_top.mean():.2f}")
print(f"WR            : {(p_top > 0).mean()*100:.1f}%")
print(f"total_pnl     : ${p_top.sum():,.0f}")
print()

# ── 5. Compare with Score filter ──
score_arr = np.array([float(t.get("score", 0) or 0) for t in trades])
top_score_mask = score_arr >= np.percentile(score_arr, 70)
p_top_score = pnls[top_score_mask]
print("=" * 80)
print("COMPARISON — Top 30%: CGS vs old Score")
print("=" * 80)
print(f"{'Filter':<15} {'n':>6} {'avg_pnl':>12} {'WR':>8}")
print("-" * 80)
print(f"{'CGS':<15} {top_mask.sum():>6} ${p_top.mean():>10.2f} "
      f"{(p_top > 0).mean()*100:>7.1f}%")
print(f"{'Old Score':<15} {top_score_mask.sum():>6} "
      f"${p_top_score.mean():>10.2f} "
      f"{(p_top_score > 0).mean()*100:>7.1f}%")

# ── 6. BUY vs SELL inside CGS top 30% ──
print()
print("=" * 80)
print("TOP 30% CGS — BUY vs SELL")
print("=" * 80)
for act in ["BUY", "SELL"]:
    act_mask = top_mask & (actions == act)
    if act_mask.sum() == 0:
        continue
    p = pnls[act_mask]
    print(f"{act:<6}: n={act_mask.sum():>5}  "
          f"avg_pnl=${p.mean():>8.2f}  "
          f"WR={(p > 0).mean()*100:>5.1f}%  "
          f"total=${p.sum():>10,.0f}")

# ── 7. Save CGS for further analysis ──
with open("cgs_analysis.json", "w") as f:
    json.dump({
        "thresholds": {"p70": float(thr_70), "p80": float(qs[3])},
        "top30": {"n": int(top_mask.sum()),
                  "avg_pnl": float(p_top.mean()),
                  "wr": float((p_top > 0).mean())},
        "all_trades_cgs": CGS.tolist(),
    }, f)
print()
print("Saved: cgs_analysis.json")
