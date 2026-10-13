#!/usr/bin/env python3
"""
apply_gap_window_fix.py

Fixes the phantom gap-alerts:
  - Gaps detected by _validate_cache_local are reported even if they lie
    OUTSIDE the current --history-days window.
  - _load_cached then correctly refuses to fetch them (since_full_dt filter),
    but the detection counter and log line are already polluted.

Fix: pass since_ts to _validate_cache_local so it only reports gaps
     inside the current window.

Run:  python apply_gap_window_fix.py
"""
import os, sys, shutil, hashlib

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found", file=sys.stderr); sys.exit(1)

if "_validate_cache_local(df, symbol, timeframe, tf_sec, since_ts" in open(SRC).read():
    print("✗ Already patched. Restore from .bak first.", file=sys.stderr)
    sys.exit(3)

shutil.copy2(SRC, SRC + ".bak")
print(f"✓ backup → {SRC}.bak\n")

with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()
orig = s
report = []

def patch(old, new, label, required=True):
    global s
    if old not in s:
        report.append(("✗" if required else "⚠") + f" {label}")
        return False
    s = s.replace(old, new, 1)
    report.append("✓ " + label)
    return True

# ═══════════════════════════════════════════════════════════════
# 1. _validate_cache_local — accept since_ts, skip old gaps
# ═══════════════════════════════════════════════════════════════
OLD1 = '''def _validate_cache_local(df, symbol: str, timeframe: str, tf_sec: int):
    """
    مرحلة الإصلاح المحلي (بدون شبكة).
    Returns: (cleaned_df | None, gap_ranges: list[(start_ts, end_ts)], issues: dict)
    """'''
NEW1 = '''def _validate_cache_local(df, symbol: str, timeframe: str, tf_sec: int,
                           since_ts=None):
    """
    مرحلة الإصلاح المحلي (بدون شبكة).
    Returns: (cleaned_df | None, gap_ranges: list[(start_ts, end_ts)], issues: dict)

    since_ts: if given, only gaps whose end_ts >= since_ts are reported.
              Gaps entirely before it are dropped from gap_ranges AND
              excluded from issues['gaps'].
    """'''
patch(OLD1, NEW1, "_validate_cache_local: accept since_ts")

# ═══════════════════════════════════════════════════════════════
# 2. Gap detection — apply since_ts filter
# ═══════════════════════════════════════════════════════════════
OLD2 = '''        for gi in gap_idx:
            if gi == 0:
                continue
            start_ts = df.index[gi - 1] + expected
            end_ts = df.index[gi] - expected
            if start_ts <= end_ts:
                gap_ranges.append((start_ts, end_ts))
        issues['gaps'] = len(gap_ranges)'''

NEW2 = '''        for gi in gap_idx:
            if gi == 0:
                continue
            start_ts = df.index[gi - 1] + expected
            end_ts = df.index[gi] - expected
            if start_ts > end_ts:
                continue
            # [WINDOW-FILTER] skip gaps entirely outside the current window
            if since_ts is not None:
                try:
                    if end_ts < since_ts:
                        continue
                except Exception:
                    pass
            gap_ranges.append((start_ts, end_ts))
        issues['gaps'] = len(gap_ranges)'''
patch(OLD2, NEW2, "gap detection: apply since_ts filter")

# ═══════════════════════════════════════════════════════════════
# 3. _load_cached — pass since_full_dt
# ═══════════════════════════════════════════════════════════════
OLD3 = '''    df, gap_ranges, issues = _validate_cache_local(
        df, symbol, timeframe, _tf_sec
    )
    if df is None or len(df) < min_rows:
        return None

    # ═══ 3.6 جلب الفراغات فقط (إن وُجدت) ═══'''
NEW3 = '''    df, gap_ranges, issues = _validate_cache_local(
        df, symbol, timeframe, _tf_sec, since_ts=since_full_dt
    )
    if df is None or len(df) < min_rows:
        return None

    # ═══ 3.6 جلب الفراغات فقط (إن وُجدت) ═══'''
patch(OLD3, NEW3, "_load_cached: pass since_full_dt")

# ═══════════════════════════════════════════════════════════════
# 4. _load_cached_sub — same treatment
# ═══════════════════════════════════════════════════════════════
OLD4 = '''    df, gap_ranges, issues = _validate_cache_local(
        df, symbol, sub_tf, _sub_sec
    )
    if df is None or len(df) < min_rows:
        return None'''
NEW4 = '''    df, gap_ranges, issues = _validate_cache_local(
        df, symbol, sub_tf, _sub_sec, since_ts=since_full_dt
    )
    if df is None or len(df) < min_rows:
        return None'''
patch(OLD4, NEW4, "_load_cached_sub: pass since_full_dt")

# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
if s == orig:
    print("⚠  No changes applied:", file=sys.stderr)
    for line in report:
        print("   " + line, file=sys.stderr)
    sys.exit(2)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 68)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 68)
for line in report:
    print("   " + line)
print("═" * 68)
