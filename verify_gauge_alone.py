# verify_gauge_alone.py
import json
import numpy as np

with open("trades_CSD_test.jsonl") as f:
    trades = [json.loads(l) for l in f if not json.loads(l).get("_meta")]

gauge = np.array([float(t.get("gauge_force", 0) or 0) for t in trades])
pnls = np.array([float(t.get("net_pnl", 0) or 0) for t in trades])
actions = np.array([t.get("action", "?") for t in trades])

print("=" * 80)
print("GAUGE ALONE — Decile Analysis")
print("=" * 80)
print(f"{'Decile':<12} {'n':>6} {'avg_pnl':>12} {'WR':>8} {'BUY_avg':>10} {'SELL_avg':>10}")
print("-" * 80)

# 10 deciles
qs = np.percentile(gauge, [10, 20, 30, 40, 50, 60, 70, 80, 90])

deciles = []
prev = -np.inf
for i, q in enumerate(qs):
    mask = (gauge > prev) & (gauge <= q)
    deciles.append((f"D{i+1}", mask))
    prev = q
deciles.append(("D10", gauge > qs[-1]))

for name, mask in deciles:
    if mask.sum() == 0:
        continue
    p = pnls[mask]
    a = actions[mask]
    
    buy_mask = a == "BUY"
    sell_mask = a == "SELL"
    
    buy_avg = p[buy_mask].mean() if buy_mask.sum() > 0 else 0
    sell_avg = p[sell_mask].mean() if sell_mask.sum() > 0 else 0
    
    print(f"{name:<12} {len(p):>6} ${p.mean():>10.2f} "
          f"{(p > 0).mean()*100:>7.1f}% "
          f"${buy_avg:>9.2f} ${sell_avg:>9.2f}")

# ── Top 20% only ──
print()
print("=" * 80)
print("GAUGE TOP 20% ONLY (D9-D10)")
print("=" * 80)
thr_80 = qs[-2]
top = gauge > thr_80
p_top = pnls[top]
a_top = actions[top]

print(f"Total n: {top.sum()}, avg_pnl=${p_top.mean():.2f}, WR={(p_top>0).mean()*100:.1f}%")

for act in ["BUY", "SELL"]:
    m = a_top == act
    if m.sum() > 0:
        p = p_top[m]
        print(f"  {act}: n={m.sum():>5}  avg=${p.mean():>8.2f}  "
              f"WR={(p>0).mean()*100:>5.1f}%  total=${p.sum():>10,.0f}")

# ── Top 10% only ──
print()
print("=" * 80)
print("GAUGE TOP 10% ONLY (D10)")
print("=" * 80)
top = gauge > qs[-1]
p_top = pnls[top]
a_top = actions[top]

print(f"Total n: {top.sum()}, avg_pnl=${p_top.mean():.2f}, WR={(p_top>0).mean()*100:.1f}%")

for act in ["BUY", "SELL"]:
    m = a_top == act
    if m.sum() > 0:
        p = p_top[m]
        print(f"  {act}: n={m.sum():>5}  avg=${p.mean():>8.2f}  "
              f"WR={(p>0).mean()*100:>5.1f}%  total=${p.sum():>10,.0f}")
