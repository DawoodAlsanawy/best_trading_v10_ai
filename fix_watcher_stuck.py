#!/usr/bin/env python3
"""
fix_watcher_stuck.py

Fixes the "watchers stuck in WAITING_TOUCH" bug.

Root cause:
  monitor_reversal_watchers computes _max_age_s (sub-bar based, ~6h)
  but uses REVERSAL_MAX_HOURS (24h) for the expiry check. Watchers
  linger far past the backtest's effective window, blocking new
  signals from registering on the same symbols.

Fixes:
  1. Expiry uses _max_age_s (matches backtest)
  2. First exposure check includes _REVERSAL_WATCHERS
  3. Silent registration failures get a DEBUG log line
  4. Watcher state summary logged every ~5 min

Run:  python fix_watcher_stuck.py
"""
import os, sys, shutil, hashlib, ast

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found in {os.getcwd()}", file=sys.stderr)
    sys.exit(1)

if "_WATCHER_STUCK_FIX" in open(SRC).read():
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
# FIX 1 — Expiry uses _max_age_s (matches backtest)
# ═══════════════════════════════════════════════════════════════
OLD_EXPIRY = '''        age_h = (now - float(w.get("close_ts", now))) / 3600.0
        if age_h > float(CFG.REVERSAL_MAX_HOURS):
            log.info(f"[LiveRev] {sym} expired (age={age_h:.1f}h)")
            _REVERSAL_WATCHERS.pop(sym, None)
            continue'''

NEW_EXPIRY = '''        # ═══ [WATCHER-STUCK-FIX] Expiry uses the sub-bar window
        #     (matches backtest), NOT REVERSAL_MAX_HOURS.
        _age_s = now - float(w.get("close_ts", now))
        _limit_s = _max_age_s  # 6h with default 20+4 sub-bars
        if _age_s > _limit_s:
            log.info(f"[LiveRev] {sym} expired (age={_age_s/3600:.1f}h "
                     f"> {_limit_s/3600:.1f}h)")
            _REVERSAL_WATCHERS.pop(sym, None)
            continue'''
patch(OLD_EXPIRY, NEW_EXPIRY,
      "F1: expiry uses _max_age_s (6h, matches backtest)")


# ═══════════════════════════════════════════════════════════════
# FIX 2 — First exposure check includes _REVERSAL_WATCHERS
# ═══════════════════════════════════════════════════════════════
OLD_EXPO = '''                    # احتساب التعرّض الإجمالي (مراكز + معلّقات + مُراقَبة)
                    _total_exposure = (len(open_pos_live)
                                       + len(_PENDING_ORDERS)
                                       + len(_WATCHED_SIGNALS))
                    if _total_exposure >= int(cfg.MAX_CONCURRENT_ASSETS):
                        log.debug(f"[Watch] exposure cap reached "
                                  f"({_total_exposure}≥"
                                  f"{cfg.MAX_CONCURRENT_ASSETS}) — "
                                  f"stopping scan")
                        break'''

NEW_EXPO = '''                    # ═══ [WATCHER-STUCK-FIX] Include _REVERSAL_WATCHERS
                    #     so we skip the SL-Clip noise when capped.
                    _total_exposure = (len(open_pos_live)
                                       + len(_PENDING_ORDERS)
                                       + len(_WATCHED_SIGNALS)
                                       + len(_REVERSAL_WATCHERS))
                    if _total_exposure >= int(cfg.MAX_CONCURRENT_ASSETS):
                        log.debug(f"[Watch] exposure cap reached "
                                  f"({_total_exposure}≥"
                                  f"{cfg.MAX_CONCURRENT_ASSETS}) — "
                                  f"stopping scan")
                        break'''
patch(OLD_EXPO, NEW_EXPO,
      "F2: exposure includes _REVERSAL_WATCHERS")


# ═══════════════════════════════════════════════════════════════
# FIX 3 — Silent registration failures get a log line
# ═══════════════════════════════════════════════════════════════
OLD_REG = '''def _register_reversal_watcher(exchange, sym: str, side: str,
                                qty: float, sig, leverage: int,
                                ad=None) -> bool:
    if sym in _REVERSAL_WATCHERS:
        return False
    if sym in _PENDING_ORDERS:
        return False'''

NEW_REG = '''def _register_reversal_watcher(exchange, sym: str, side: str,
                                qty: float, sig, leverage: int,
                                ad=None) -> bool:
    if sym in _REVERSAL_WATCHERS:
        log.debug(f"[LiveRev] {sym} already has watcher — skip")
        return False
    if sym in _PENDING_ORDERS:
        log.debug(f"[LiveRev] {sym} already has pending — skip")
        return False'''
patch(OLD_REG, NEW_REG, "F3: log skip reasons at DEBUG")


# ═══════════════════════════════════════════════════════════════
# FIX 4 — Watcher state summary every ~5 min
# ═══════════════════════════════════════════════════════════════
OLD_MON_START = '''    for sym in list(_REVERSAL_WATCHERS.keys()):
        w = _REVERSAL_WATCHERS[sym]
        status = w.get("status", "WAITING_TOUCH")

        if status in ("FILLED", "EXPIRED"):
            _REVERSAL_WATCHERS.pop(sym, None)
            continue'''

NEW_MON_START = '''    # ═══ [WATCHER-STUCK-FIX] Periodic state summary (rate-limited)
    _now_ts = _t_rev.time()
    if (_now_ts - getattr(monitor_reversal_watchers, '_last_log_ts', 0.0)
            >= 300.0):
        monitor_reversal_watchers._last_log_ts = _now_ts
        _st_counts: Dict[str, int] = {}
        for _s, _ww in _REVERSAL_WATCHERS.items():
            _stt = _ww.get("status", "?")
            _st_counts[_stt] = _st_counts.get(_stt, 0) + 1
        _ages = []
        for _s, _ww in _REVERSAL_WATCHERS.items():
            _ages.append((_now_ts - float(_ww.get("close_ts", _now_ts)))
                          / 3600.0)
        _age_str = (f"{min(_ages):.1f}-{max(_ages):.1f}h"
                     if _ages else "n/a")
        log.info(f"[LiveRev] watchers={len(_REVERSAL_WATCHERS)} "
                 f"states={_st_counts} ages={_age_str} "
                 f"(expiry={_max_age_s/3600:.1f}h)")

    for sym in list(_REVERSAL_WATCHERS.keys()):
        w = _REVERSAL_WATCHERS[sym]
        status = w.get("status", "WAITING_TOUCH")

        if status in ("FILLED", "EXPIRED"):
            _REVERSAL_WATCHERS.pop(sym, None)
            continue'''
patch(OLD_MON_START, NEW_MON_START,
      "F4: periodic watcher state summary")


# ═══════════════════════════════════════════════════════════════
# Stamp + Write
# ═══════════════════════════════════════════════════════════════
s = s.rstrip() + "\n\n# [WATCHER-STUCK-FIX] applied\n"

if s == orig:
    print("═" * 68)
    print("  ⚠ No changes applied:")
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
print("═" * 68)
