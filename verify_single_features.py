# verify_single_features.py
import json, numpy as np

with open("trades_CSD_test.jsonl") as f:
    trades = [json.loads(l) for l in f if not json.loads(l).get("_meta")]

def test_feature(trades, key, name):
    pairs = [(float(t.get(key, 0) or 0), float(t.get("net_pnl", 0) or 0))
             for t in trades if t.get(key) is not None]
    if len(pairs) < 100:
        return
    pairs.sort()
    pnls = np.array([p[1] for p in pairs])
    n = len(pnls)
    q70, q90 = int(n*0.7), int(n*0.9)
    
    low = pnls[:q70].mean()
    mid = pnls[q70:q90].mean()
    high = pnls[q90:].mean()
    
    print(f"{name:<25} | low=${low:>8.2f}  mid=${mid:>8.2f}  "
          f"high=${high:>8.2f}  | high/low={high/max(abs(low),0.01):>5.2f}×")

print("FEATURE-BY-FEATURE ANALYSIS")
print("=" * 90)
for key, name in [
    ("T_info_val", "T_info"),
    ("E_therm", "E_therm"),
    ("H_over_Hmax", "H/H_max"),
    ("friction", "Friction"),
    ("gauge_force", "Gauge"),
    ("geodesic_accel", "Geo_Accel (abs)"),
    ("delta_gap", "Delta_Gap"),
    ("sl_sigma", "SL_Sigma"),
    ("friction_drag_over_sl", "Friction_Drag"),
    ("dist_from_ema_norm", "Dist_EMA"),
    ("score", "Score"),
]:
    test_feature(trades, key, name)
