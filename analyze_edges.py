#!/usr/bin/env python3
"""Reads edges_scan.csv → ranks configs by side, prints edge zones."""
import sys
import numpy as np
import pandas as pd

CSV = sys.argv[1] if len(sys.argv) > 1 else "edges_scan.csv"

df = pd.read_csv(CSV)
df = df[df.n > 0].copy()
if df.empty:
    print("No valid rows"); sys.exit(0)

# Composite score: reward high Sharpe + PF + win, penalize DD
df["score"] = (df.Sharpe.clip(lower=0) *
               df["PF"].clip(upper=10) ** 0.5 *
               (df.win / 100.0) ** 0.5 *
               np.exp(-df.DD / 40.0))

for side in ("BUY", "SELL"):
    sub = df[df.side == side].sort_values("score", ascending=False)
    if sub.empty:
        continue
    print(f"\n{'═'*78}")
    print(f"  {side} — TOP 8 configs (pure edge, all adaptive exits OFF)")
    print(f"{'═'*78}")
    cols = ["z_min","n","win","muR","PF","Sharpe","DD","hold","MFE"]
    print(sub[cols].head(8).to_string(index=False,
          float_format=lambda x: f"{x:.3f}"))

    # Edge zone: contiguous z_min values with Sharpe > 0.7 * max
    best = sub.iloc[0]
    thr = 0.7 * best.Sharpe
    zone = sub[sub.Sharpe >= thr].sort_values("z_min")
    print(f"\n  ▶ Sharp zone (Sharpe ≥ {thr:.2f}):")
    print(f"     z_min ∈ [{zone.z_min.min():.2f}, {zone.z_min.max():.2f}]")
    print(f"     peak Sharpe = {best.Sharpe:.3f} @ z_min={best.z_min:.2f}")

    # Robustness: does Sharpe monotone increase before peak, decrease after?
    all_z = sub.sort_values("z_min")
    peak_i = all_z.Sharpe.idxmax()
    pos = all_z.index.get_loc(peak_i)
    left_ok  = (all_z.Sharpe.iloc[:pos+1].diff().dropna() >= 0).mean() if pos > 0 else 1.0
    right_ok = (all_z.Sharpe.iloc[pos:].diff().dropna() <= 0).mean() if pos < len(all_z)-1 else 1.0
    shape = "✓ clean peak" if (left_ok > 0.5 and right_ok > 0.5) else "⚠ noisy peak"
    print(f"     shape: {shape}  (left_mono={left_ok:.2f}, right_mono={right_ok:.2f})")

# Cross-side comparison
print(f"\n{'═'*78}")
print(f"  BUY vs SELL — best config each")
print(f"{'═'*78}")
best_b = df[df.side=="BUY"].sort_values("score", ascending=False).head(1)
best_s = df[df.side=="SELL"].sort_values("score", ascending=False).head(1)
if not best_b.empty and not best_s.empty:
    b, s = best_b.iloc[0], best_s.iloc[0]
    for k in ["z_min","n","win","muR","PF","Sharpe","DD","hold","MFE"]:
        print(f"  {k:10s}  BUY={b[k]:>10.3f}   SELL={s[k]:>10.3f}   "
              f"ratio={b[k]/s[k] if s[k] else 0:.2f}")
