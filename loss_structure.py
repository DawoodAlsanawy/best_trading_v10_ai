#!/usr/bin/env python3
"""Loss structure from a backtest JSONL WITHOUT using its net_pnl (polluted, see N4).
Uses only: action, entry_price, exit_price, sl_dist_initial, pos_size, exit_reason, hold_bars, entry_time.
R_final = direction*(exit-entry)/sl_dist_initial  (final leg only, gross of fees; partial leg not recoverable)
usage: python loss_structure.py results/trades_baseline_730d.jsonl"""
import sys, json, numpy as np, pandas as pd
df = pd.DataFrame([json.loads(l) for l in open(sys.argv[1]) if l.strip()])
need = ["action","entry_price","exit_price","sl_dist_initial","pos_size","exit_reason","hold_bars","entry_time"]
miss = [c for c in need if c not in df]; assert not miss, f"missing fields: {miss}"
df = df[df.sl_dist_initial > 0].copy()
d = np.where(df.action == "BUY", 1.0, -1.0)
df["R"] = d * (df.exit_price - df.entry_price) / df.sl_dist_initial
df["px_pnl"] = d * (df.exit_price - df.entry_price) * df.pos_size      # $ gross, final leg, sizing-weighted
df["t"] = pd.to_datetime(df.entry_time, errors="coerce")
f = lambda g: pd.Series({"n": len(g), "share%": 100*len(g)/len(df), "meanR": g.R.mean(), "medR": g.R.median(),
                         "sum_px_pnl$": g.px_pnl.sum(), "hold_med": g.hold_bars.median()})
pd.set_option("display.width", 160); pd.set_option("display.float_format", "{:,.3f}".format)
print(f"trades with sl_dist_initial>0: {len(df)}   overall meanR_final={df.R.mean():.3f}  medR={df.R.median():.3f}\n")
print("== by exit_reason ==");  print(df.groupby("exit_reason").apply(f).sort_values("n", ascending=False), "\n")
print("== by action ==");       print(df.groupby("action").apply(f), "\n")
df["quarter"] = pd.qcut(df.t.rank(method="first"), 4, labels=["Q1","Q2","Q3","Q4"])
print("== chronological quarters (by entry_time) ==");  print(df.groupby("quarter", observed=True).apply(f), "\n")
eod = df[df.exit_reason == "EndOfData"]
print(f"EndOfData: n={len(eod)}  sum_px_pnl=${eod.px_pnl.sum():,.2f}  worst R={eod.R.min() if len(eod) else float('nan'):.2f}")
print(f"R_final >= 3 (partial level): {100*(df.R>=3).mean():.2f}%   R_final >= 5 (hard TP): {100*(df.R>=5).mean():.2f}%   R_final <= -1: {100*(df.R<=-1).mean():.2f}%")
