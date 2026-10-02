# verify_CSD_hypothesis.py
import json
import numpy as np

trades = []
with open("trades_log_backtest.jsonl") as f:
    for line in f:
        r = json.loads(line)
        if not r.get("_meta"):
            trades.append(r)

# حساب CI لكل صفقة
cis = []
pnls = []
for t in trades:
    try:
        T_info = float(t.get("T_info", 0))
        E_therm = float(t.get("E_therm", 0))
        H = float(t.get("H", 0))
        dyn_k = max(int(t.get("dynamic_k", 8)), 2)
        H_max = np.log2(dyn_k)
        order = 1.0 - H / H_max
        CI = T_info * order * E_therm
        cis.append(CI)
        pnls.append(float(t.get("net_pnl", 0)))
    except:
        continue

cis = np.array(cis)
pnls = np.array(pnls)

# ترتيب
order = np.argsort(cis)
pnls_sorted = pnls[order]

n = len(pnls)
q70 = int(n * 0.70)
q90 = int(n * 0.90)

print(f"Total trades: {n}")
print()
print("Q1-Q7 (low CI):  avg_pnl = ${:.2f}, WR = {:.1f}%".format(
    pnls_sorted[:q70].mean(),
    (pnls_sorted[:q70] > 0).mean() * 100
))
print("Q7-Q9 (mid CI):  avg_pnl = ${:.2f}, WR = {:.1f}%".format(
    pnls_sorted[q70:q90].mean(),
    (pnls_sorted[q70:q90] > 0).mean() * 100
))
print("Q9-Q10 (high CI): avg_pnl = ${:.2f}, WR = {:.1f}%".format(
    pnls_sorted[q90:].mean(),
    (pnls_sorted[q90:] > 0).mean() * 100
))
print()
print("Expected if hypothesis true: high CI should be 2-3x better")
