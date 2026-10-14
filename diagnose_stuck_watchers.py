#!/usr/bin/env python3
"""
diagnose_stuck_watchers.py

Fixes the watcher-expiry bug (uses sub-bar window, not REVERSAL_MAX_HOURS)
AND adds diagnostic logging to reveal why target is never touched.

- Forces the age check to use _max_age_s.
- Logs target vs current price for every watcher (rate-limited, 5 min).
- Logs sub-bar fetch success/failure at INFO level.
- Logs the outcome of each sub-bar scan.

Run:  python diagnose_stuck_watchers.py
"""
import os, sys, shutil, hashlib, ast

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found", file=sys.stderr); sys.exit(1)

if "_STUCK_DIAG" in open(SRC).read():
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
# FIX 1 — Force expiry to use _max_age_s
# ═══════════════════════════════════════════════════════════════
OLD1 = '''        age_h = (now - float(w.get("close_ts", now))) / 3600.0
        if age_h > float(CFG.REVERSAL_MAX_HOURS):
            log.info(f"[LiveRev] {sym} expired (age={age_h:.1f}h)")
            _REVERSAL_WATCHERS.pop(sym, None)
            continue'''

NEW1 = '''        # [STUCK_DIAG] Expiry = sub-bar window (matches backtest)
        _age_s = now - float(w.get("close_ts", now))
        if _age_s > _max_age_s:
            log.info(f"[LiveRev] {sym} expired (age={_age_s/3600:.2f}h "
                     f"> {_max_age_s/3600:.2f}h)")
            _REVERSAL_WATCHERS.pop(sym, None)
            continue'''
patch(OLD1, NEW1, "F1: expiry uses _max_age_s")


# ═══════════════════════════════════════════════════════════════
# FIX 2 — Log sub-bar fetch result at INFO
# ═══════════════════════════════════════════════════════════════
OLD2 = '''        df = _fetch_live_subbars(exchange, sym, sub_tf, keep_bars=200)
        if df is None or len(df) < 3:
            continue
        df_closed = _only_closed_subbars(df, tf_sec)
        if df_closed is None or len(df_closed) == 0:
            continue'''

NEW2 = '''        df = _fetch_live_subbars(exchange, sym, sub_tf, keep_bars=200)
        if df is None or len(df) < 3:
            # [STUCK_DIAG] fetch failure — log at INFO once per 5 min per symbol
            _fk = f"_warned_nofetch_{sym}"
            _now_d = _t_rev.time()
            if _now_d - getattr(_fetch_live_subbars, _fk, 0.0) > 300.0:
                setattr(_fetch_live_subbars, _fk, _now_d)
                log.warning(f"[LiveRev] {sym} sub-bar fetch returned "
                            f"{'None' if df is None else len(df)} bars "
                            f"— scan skipped")
            continue
        df_closed = _only_closed_subbars(df, tf_sec)
        if df_closed is None or len(df_closed) == 0:
            continue'''
patch(OLD2, NEW2, "F2: log sub-bar fetch failures")


# ═══════════════════════════════════════════════════════════════
# FIX 3 — Log target vs current price for each watcher
# ═══════════════════════════════════════════════════════════════
OLD3 = '''        last_scan_ts = float(w.get("last_scan_ts", 0.0))
        new_bars = df_closed[
            (df_closed.index.astype("int64") // 10**9) > last_scan_ts
        ]
        if len(new_bars) == 0:
            continue'''

NEW3 = '''        last_scan_ts = float(w.get("last_scan_ts", 0.0))
        new_bars = df_closed[
            (df_closed.index.astype("int64") // 10**9) > last_scan_ts
        ]
        if len(new_bars) == 0:
            continue

        # [STUCK_DIAG] Log target vs current price (rate-limited 5 min)
        _lk = f"_warned_target_{sym}"
        _now_t = _t_rev.time()
        if _now_t - getattr(_fetch_live_subbars, _lk, 0.0) > 300.0:
            setattr(_fetch_live_subbars, _lk, _now_t)
            try:
                _cur_p = float(df_closed["Close"].iloc[-1])
                _gap_pct = (float(w["target"]) - _cur_p) / _cur_p * 100
                log.info(f"[LiveRev-DIAG] {sym} {w['action']} "
                         f"target={float(w['target']):.6f} "
                         f"current={_cur_p:.6f} "
                         f"gap={_gap_pct:+.2f}% "
                         f"new_bars={len(new_bars)}")
            except Exception as _e:
                log.debug(f"[LiveRev-DIAG] {sym} log failed: {_e}")'''
patch(OLD3, NEW3, "F3: log target vs price per watcher")


# ═══════════════════════════════════════════════════════════════
# FIX 4 — Force expiry on startup (drop watchers older than 6h)
# ═══════════════════════════════════════════════════════════════
OLD4 = '''    # ══ [LiveRev] Drop watchers older than REVERSAL_MAX_HOURS ══
    if _REVERSAL_WATCHERS:
        _now_rev = _t_rev.time()
        _max_s = float(CFG.REVERSAL_MAX_HOURS) * 3600.0
        _dropped = 0
        for _s in list(_REVERSAL_WATCHERS.keys()):
            _w = _REVERSAL_WATCHERS[_s]
            if _now_rev - float(_w.get("close_ts", _now_rev)) > _max_s:
                _REVERSAL_WATCHERS.pop(_s, None)
                _dropped += 1
        if _dropped:
            log.info(f"[LiveRev] Dropped {_dropped} stale watchers on startup")
            save_reversal_watchers()'''

NEW4 = '''    # ══ [STUCK_DIAG] Drop watchers older than sub-bar window ══
    if _REVERSAL_WATCHERS:
        _now_rev = _t_rev.time()
        _sub_tf_s = _get_subbars_tf(CFG.timeframe) or "15m"
        _sub_s = _sub_tf_seconds(_sub_tf_s)
        _tw_s = int(getattr(CFG, 'REVERSAL_TOUCH_SUBBARS', 20))
        _bw_s = int(getattr(CFG, 'REVERSAL_BOUNCE_SUBBARS', 4))
        _max_s = (_tw_s + _bw_s) * _sub_s   # = sub-bar window
        _dropped = 0
        for _s in list(_REVERSAL_WATCHERS.keys()):
            _w = _REVERSAL_WATCHERS[_s]
            _age = _now_rev - float(_w.get("close_ts", _now_rev))
            if _age > _max_s:
                _REVERSAL_WATCHERS.pop(_s, None)
                _dropped += 1
        if _dropped:
            log.warning(f"[LiveRev] Dropped {_dropped} stale watchers "
                        f"(age > {_max_s/3600:.2f}h)")
            save_reversal_watchers()'''
patch(OLD4, NEW4, "F4: drop stale watchers on startup (sub-bar window)")


# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
s = s.rstrip() + "\n\n# [STUCK_DIAG] applied\n"

if s == orig:
    print("═" * 68)
    print("  ⚠ No changes applied")
    for r in report:
        print("   " + r)
    print("═" * 68)
    sys.exit(2)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

try:
    ast.parse(s)
    syntax_ok = True
except SyntaxError as e:
    syntax_ok = False
    print(f"  ✗ SYNTAX ERROR: {e}")

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 68)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 68)
for line in report:
    print("   " + line)
print("═" * 68)
if syntax_ok:
    print("  ✓ Python syntax OK")
else:
    print(f"  ✗ Restore from {SRC}.bak")
    sys.exit(2)
