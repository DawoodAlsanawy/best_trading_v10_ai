#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sl_diag.py — Diagnostic of SL hits timing and magnitude."""

import os, sys, json, numpy as np
os.environ["QTT_OFFLINE"] = "1"   # cache-only

# لا تحتاج تشغيل البوت — اقرأ ملف trades_log_backtest.jsonl مباشرة
_log_file = "trades_log_backtest.jsonl"

if not os.path.exists(_log_file):
    print(f"❌ {_log_file} not found")
    sys.exit(1)

trades = []
with open(_log_file) as f:
    for line in f:
        try:
            r = json.loads(line)
            if r.get('_meta'):
                continue
            trades.append(r)
        except Exception:
            pass

print(f"Total trades: {len(trades):,}")
print()

# ═══════════════════════════════════════════════════════════════
# 1) Distribution of exit reasons
# ═══════════════════════════════════════════════════════════════
from collections import Counter
_reasons = Counter()
for t in trades:
    r = str(t.get('exit_reason', '?'))
    # simplify
    if 'SL' in r or 'Emergency' in r:
        key = 'SL'
    elif 'Hard TP' in r:
        key = 'TP'
    elif 'MaxHold' in r:
        key = 'MaxHold'
    elif 'EndOfData' in r:
        key = 'EndOfData'
    else:
        key = r[:20]
    _reasons[key] += 1

print("═══ Exit reasons ═══")
for k, v in _reasons.most_common():
    print(f"  {k:15s}: {v:6,} ({v/len(trades)*100:5.1f}%)")
print()

# ═══════════════════════════════════════════════════════════════
# 2) SL hits: hold_bars distribution
# ═══════════════════════════════════════════════════════════════
sl_trades = [t for t in trades
             if 'SL' in str(t.get('exit_reason', ''))
             or 'Emergency' in str(t.get('exit_reason', ''))]

if sl_trades:
    holds = np.array([t.get('hold_bars', 0) for t in sl_trades])
    print("═══ SL hits: hold_bars distribution ═══")
    for pct in [10, 25, 50, 75, 90, 95, 99]:
        print(f"  p{pct:>2}: {np.percentile(holds, pct):.0f} bars")
    print(f"  mean: {holds.mean():.1f}  "
          f"max: {holds.max():.0f}")
    print()

    # Buckets
    buckets = [(0, 5), (5, 10), (10, 20), (20, 50),
               (50, 100), (100, 168), (168, 99999)]
    print("═══ SL hold_bars buckets ═══")
    for lo, hi in buckets:
        n = int(((holds >= lo) & (holds < hi)).sum())
        print(f"  [{lo:>3}, {hi:>3}): {n:6,} "
              f"({n/len(holds)*100:5.1f}%)")
    print()

# ═══════════════════════════════════════════════════════════════
# 3) SL hits: MFE before hitting SL
# ═══════════════════════════════════════════════════════════════
if sl_trades:
    mfes = np.array([t.get('mfe_frac', 0) for t in sl_trades])
    print("═══ SL hits: MFE (max favorable excursion) ═══")
    for pct in [10, 25, 50, 75, 90, 95]:
        print(f"  p{pct:>2}: {np.percentile(mfes, pct)*100:6.2f}%")
    print(f"  mean: {mfes.mean()*100:.2f}%")
    print()

    # كيف كانت MFE موزعة؟
    mfe_buckets = [(0.0, 0.005), (0.005, 0.01), (0.01, 0.02),
                   (0.02, 0.05), (0.05, 0.10), (0.10, 1.0)]
    print("═══ SL: MFE buckets ═══")
    for lo, hi in mfe_buckets:
        n = int(((mfes >= lo) & (mfes < hi)).sum())
        print(f"  [{lo*100:>5.1f}%, {hi*100:>5.1f}%): {n:6,} "
              f"({n/len(mfes)*100:5.1f}%)")
    print()

# ═══════════════════════════════════════════════════════════════
# 4) SL hits: by score
# ═══════════════════════════════════════════════════════════════
print("═══ SL rate by score bucket ═══")
for lo in [3.0, 4.0, 5.0, 6.0, 8.0, 10.0]:
    hi = lo + 1.0
    grp = [t for t in trades
           if lo <= float(t.get('score', 0)) < hi]
    if not grp:
        continue
    sl_in = sum(1 for t in grp
                if 'SL' in str(t.get('exit_reason', ''))
                or 'Emergency' in str(t.get('exit_reason', '')))
    print(f"  score [{lo:.0f}, {hi:.0f}): n={len(grp):5,}  "
          f"SL%={sl_in/max(len(grp),1)*100:5.1f}%")
print()

# ═══════════════════════════════════════════════════════════════
# 5) SL hits: by action (BUY vs SELL)
# ═══════════════════════════════════════════════════════════════
print("═══ SL rate by action ═══")
for act in ['BUY', 'SELL']:
    grp = [t for t in trades if t.get('action') == act]
    if not grp:
        continue
    sl_in = sum(1 for t in grp
                if 'SL' in str(t.get('exit_reason', ''))
                or 'Emergency' in str(t.get('exit_reason', '')))
    print(f"  {act:5s}: n={len(grp):5,}  "
          f"SL%={sl_in/max(len(grp),1)*100:5.1f}%")
print()

# ═══════════════════════════════════════════════════════════════
# 6) SL hits: by sl_dist_initial
# ═══════════════════════════════════════════════════════════════
print("═══ SL rate by initial SL distance ═══")
sld = [(t.get('sl_dist_frac', 0), t) for t in trades
       if t.get('sl_dist_frac', 0) > 0]
sld.sort()
for lo_pct in [0, 20, 40, 60, 80]:
    hi_pct = lo_pct + 20
    lo_idx = int(len(sld) * lo_pct / 100)
    hi_idx = int(len(sld) * hi_pct / 100)
    chunk = sld[lo_idx:hi_idx]
    if not chunk:
        continue
    lo_val = chunk[0][0] * 100
    hi_val = chunk[-1][0] * 100
    sl_in = sum(1 for _d, t in chunk
                if 'SL' in str(t.get('exit_reason', ''))
                or 'Emergency' in str(t.get('exit_reason', '')))
    print(f"  sl_dist [{lo_val:5.2f}%, {hi_val:5.2f}%]: "
          f"n={len(chunk):5,}  "
          f"SL%={sl_in/max(len(chunk),1)*100:5.1f}%")
print()

# ═══════════════════════════════════════════════════════════════
# 7) ATR percentile vs SL hits
# ═══════════════════════════════════════════════════════════════
print("═══ SL rate by ATR fraction ═══")
atr_frac = [(t.get('atr', 0) / max(t.get('signal_price', 1), 1e-9), t)
            for t in trades if t.get('signal_price', 0) > 0]
atr_frac.sort()
for lo_pct in [0, 20, 40, 60, 80]:
    hi_pct = lo_pct + 20
    lo_idx = int(len(atr_frac) * lo_pct / 100)
    hi_idx = int(len(atr_frac) * hi_pct / 100)
    chunk = atr_frac[lo_idx:hi_idx]
    if not chunk:
        continue
    lo_val = chunk[0][0] * 100
    hi_val = chunk[-1][0] * 100
    sl_in = sum(1 for _d, t in chunk
                if 'SL' in str(t.get('exit_reason', ''))
                or 'Emergency' in str(t.get('exit_reason', '')))
    print(f"  atr/price [{lo_val:5.2f}%, {hi_val:5.2f}%]: "
          f"n={len(chunk):5,}  "
          f"SL%={sl_in/max(len(chunk),1)*100:5.1f}%")
print()

# ═══════════════════════════════════════════════════════════════
# 8) Summary by symbol (top 10)
# ═══════════════════════════════════════════════════════════════
print("═══ SL rate by symbol (top 15 by count) ═══")
from collections import defaultdict
_by_sym = defaultdict(list)
for t in trades:
    _by_sym[t.get('symbol', '?')].append(t)
_sorted = sorted(_by_sym.items(), key=lambda x: -len(x[1]))[:15]
for sym, grp in _sorted:
    sl_in = sum(1 for t in grp
                if 'SL' in str(t.get('exit_reason', ''))
                or 'Emergency' in str(t.get('exit_reason', '')))
    print(f"  {sym:16s}: n={len(grp):5,}  "
          f"SL%={sl_in/max(len(grp),1)*100:5.1f}%")
print()

print("✅ done.")
