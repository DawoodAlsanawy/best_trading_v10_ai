#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Classifier + Breakeven Naked-Window Patch (v3)
════════════════════════════════════════════════════════════════════════
Basé sur le diagnostic de trading_2_live2_1.py:

  F1. _is_protective_order  : ccxt normalizes STOP_MARKET to type='market'
  F2. _lv_check_protective_on_exchange : use helper for TP detection
  F3. _lv_ensure_protection : helper-based check for SL presence
  F4. _lv_get_exchange_sl   : use helper for TP detection
  F5. _lv_breakeven         : add _prot_try_ts=0 to close naked window
                              (uses the ACTUAL code structure of this file)
  F6. _place_protective_orders internal _is_tp : delegate to helper

Le F5 précédent ciblait une block chirurgicale qui n'existe pas dans ce
fichier. Le nouveau F5 cible le code réel (_cancel_all_protective_orders)
et corrige le vrai bug: le cooldown de _lv_ensure_protection (20s) peut
laisser la position sans protection après Breakeven.

Usage:
    python fix_classifier.py --target trading_2_live2_1.py --dry-run
    python fix_classifier.py --target trading_2_live2_1.py
    python fix_classifier.py --target trading_2_live2_1.py --verify-only
    python fix_classifier.py --target trading_2_live2_1.py --rollback
"""

import argparse
import os
import shutil
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

BOT_FILE = "trading_2_live2.py"
BACKUP_DIR = ".patches_backup"


def log(m, level="INFO"):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {m}", flush=True)


def read_source(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    le = "\r\n" if "\r\n" in raw else "\n"
    return raw, le


def write_source(path, content):
    tmp = path + ".patched_tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(content)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


def normalize(text, le):
    if le == "\r\n":
        return text.replace("\r\n", "\n").replace("\n", "\r\n")
    return text.replace("\r\n", "\n")


# ═════════════════════════════════════════════════════════════════════
# FIX 1 — _is_protective_order (root cause)
# ═════════════════════════════════════════════════════════════════════

FIX1_ANCHOR = '''def _is_protective_order(o: Dict) -> bool:
    """True if the order is a protective SL/TP placed by this bot."""
    try:
        t = str(o.get('type') or '').lower()
        return ('stop_market' in t or 'take_profit_market' in t)
    except Exception:
        return False'''

FIX1_CONTENT = '''def _is_protective_order(o: Dict) -> bool:
    """
    True if the order is a protective SL/TP placed by this bot.

    [ccxt-NORMALIZATION FIX]
    ccxt maps Binance's STOP_MARKET to unified type='market' and stores
    the truth only in info.orderType / info.algoType.
    """
    try:
        # 1. Unified type (works when ccxt keeps the original)
        t = str(o.get('type') or '').lower()
        if 'stop_market' in t or 'take_profit_market' in t:
            return True
        if t in ('stop', 'take_profit', 'stop_loss'):
            return True

        # 2. ccxt-normalized top-level fields
        if (o.get('triggerPrice')
                or o.get('stopPrice')
                or o.get('stopLossPrice')
                or o.get('takeProfitPrice')):
            return True

        # 3. Raw Binance info fields (source of truth)
        info = o.get('info') or {}
        raw_type = str(
            info.get('orderType') or info.get('type') or ''
        ).lower()
        if 'stop_market' in raw_type or 'take_profit_market' in raw_type:
            return True
        if 'stop' in raw_type or 'take_profit' in raw_type:
            return True

        # 4. Algo Order Service marker
        if str(info.get('algoType') or '').upper() == 'CONDITIONAL':
            return True

        # 5. Last resort: any stop/trigger price in raw info
        if (info.get('stopPrice')
                or info.get('triggerPrice')
                or info.get('stopLossPrice')
                or info.get('takeProfitPrice')):
            return True
    except Exception:
        pass
    return False


def _is_tp_protective(o: Dict) -> bool:
    """
    [NEW] True if the protective order is a TAKE_PROFIT (vs SL).
    Uses raw info.orderType first.
    """
    try:
        info = o.get('info') or {}
        raw_t = str(info.get('orderType') or '').lower()
        if 'take_profit' in raw_t:
            return True
        if 'stop_market' in raw_t or raw_t == 'stop':
            return False
        # Fallback to unified type
        t = str(o.get('type') or '').lower()
        return 'take_profit' in t
    except Exception:
        return False'''

FIX1_IDEM = "def _is_tp_protective(o: Dict) -> bool:"


# ═════════════════════════════════════════════════════════════════════
# FIX 2 — _lv_check_protective_on_exchange
# ═════════════════════════════════════════════════════════════════════

FIX2_ANCHOR = '''        ot = str(o.get('type') or '').lower()
        if 'take_profit' in ot:
            if abs(sp - tp) < tol_tp:
                has_tp = True
        else:
            if abs(sp - sl) < tol_sl:
                has_sl = True
    return has_sl, has_tp'''

FIX2_CONTENT = '''        # [CLASSIFIER-FIX] use raw orderType via helper
        if _is_tp_protective(o):
            if abs(sp - tp) < tol_tp:
                has_tp = True
        else:
            if abs(sp - sl) < tol_sl:
                has_sl = True
    return has_sl, has_tp'''

FIX2_IDEM = "# [CLASSIFIER-FIX] use raw orderType via helper"


# ═════════════════════════════════════════════════════════════════════
# FIX 3 — _lv_ensure_protection (inline has_sl check)
# ═════════════════════════════════════════════════════════════════════

FIX3_ANCHOR = '''            _rate_record(2.0)
            orders = _lv_open_orders_all(exchange, sym)
            has_sl = any('stop' in str(o.get('type') or '').lower() for o in orders)
            if not has_sl:
                log.critical(f"[Prot] {sym} STOP order NOT FOUND on exchange — re-placing")
                stale = True'''

FIX3_CONTENT = '''            _rate_record(2.0)
            orders = _lv_open_orders_all(exchange, sym)
            # [CLASSIFIER-FIX] helper-based check (ccxt normalizes type)
            prot_orders = [o for o in orders if _is_protective_order(o)]
            has_sl = any(not _is_tp_protective(o) for o in prot_orders)
            if not has_sl:
                log.critical(
                    f"[Prot] {sym} STOP order NOT FOUND on exchange "
                    f"-- re-placing"
                )
                stale = True'''

FIX3_IDEM = "# [CLASSIFIER-FIX] helper-based check (ccxt normalizes type)"


# ═════════════════════════════════════════════════════════════════════
# FIX 4 — _lv_get_exchange_sl
# ═════════════════════════════════════════════════════════════════════

FIX4_ANCHOR = '''    for o in orders:
        ot = str(o.get('type') or '').lower()
        if 'take_profit' in ot:
            continue
        sp = float(
            o.get('stopPrice')
            or o.get('triggerPrice')
            or (o.get('info') or {}).get('stopPrice')
            or 0
        )
        if sp > 0:
            return sp
    return None'''

FIX4_CONTENT = '''    for o in orders:
        if not _is_protective_order(o):
            continue
        # [CLASSIFIER-FIX] use helper for TP detection
        if _is_tp_protective(o):
            continue
        _info = o.get('info') or {}
        sp = float(
            o.get('stopPrice')
            or o.get('triggerPrice')
            or _info.get('stopPrice')
            or _info.get('triggerPrice')
            or 0
        )
        if sp > 0:
            return sp
    return None'''

FIX4_IDEM = "# [CLASSIFIER-FIX] use helper for TP detection"


# ═════════════════════════════════════════════════════════════════════
# FIX 5 — _lv_breakeven: close naked window after cancel
# Uses the ACTUAL code in this file version (_cancel_all_protective_orders)
# ═════════════════════════════════════════════════════════════════════

FIX5_ANCHOR = '''        try:
            _cancel_all_protective_orders(exchange, sym)
            time.sleep(0.5)
        except Exception as _e:
            log.warning(f"[Breakeven] {sym} cancel before replace failed: {_e}")'''

FIX5_CONTENT = '''        try:
            _cancel_all_protective_orders(exchange, sym)
            time.sleep(0.5)
        except Exception as _e:
            log.warning(f"[Breakeven] {sym} cancel before replace failed: {_e}")
        # ══ [BREAKEVEN-FIX] Force _lv_ensure_protection to re-place
        # immediately, bypassing the LIVE_PROT_RETRY_S cooldown.
        # Without this line, if _prot_try_ts was set < 20s ago (which
        # happens right after ANY protective placement), the position
        # stays NAKED until the cooldown expires. This closes the window.
        pos['_prot_try_ts'] = 0'''

FIX5_IDEM = "# ══ [BREAKEVEN-FIX] Force _lv_ensure_protection to re-place"


# ═════════════════════════════════════════════════════════════════════
# FIX 6 — _place_protective_orders internal _is_tp (optional)
# ═════════════════════════════════════════════════════════════════════

FIX6_ANCHOR = '''        def _is_tp(o):
            return 'take_profit' in str(o.get('type') or '').lower()'''

FIX6_CONTENT = '''        def _is_tp(o):
            # [CLASSIFIER-FIX] delegate to global helper
            return _is_tp_protective(o)'''

FIX6_IDEM = "# [CLASSIFIER-FIX] delegate to global helper"


# ═════════════════════════════════════════════════════════════════════

@dataclass
class Fix:
    name: str
    anchor: str
    content: str
    idempotency: str
    required: bool = True


FIXES: List[Fix] = [
    Fix(name="F1_is_protective_order",
        anchor=FIX1_ANCHOR, content=FIX1_CONTENT,
        idempotency=FIX1_IDEM, required=True),
    Fix(name="F2_check_on_exchange",
        anchor=FIX2_ANCHOR, content=FIX2_CONTENT,
        idempotency=FIX2_IDEM, required=True),
    Fix(name="F3_ensure_protection",
        anchor=FIX3_ANCHOR, content=FIX3_CONTENT,
        idempotency=FIX3_IDEM, required=True),
    Fix(name="F4_get_exchange_sl",
        anchor=FIX4_ANCHOR, content=FIX4_CONTENT,
        idempotency=FIX4_IDEM, required=True),
    Fix(name="F5_breakeven_naked_window",
        anchor=FIX5_ANCHOR, content=FIX5_CONTENT,
        idempotency=FIX5_IDEM, required=True),
    Fix(name="F6_place_prot_internal_is_tp",
        anchor=FIX6_ANCHOR, content=FIX6_CONTENT,
        idempotency=FIX6_IDEM, required=False),
]


def apply_fix(source, fix, le):
    if fix.idempotency and fix.idempotency in source:
        return source, "SKIP (already applied)"
    anchor = normalize(fix.anchor, le)
    content = normalize(fix.content, le)
    cnt = source.count(anchor)
    if cnt == 0:
        return source, "ERROR: anchor not found"
    if cnt > 1:
        return source, f"ERROR: anchor appears {cnt} times"
    return source.replace(anchor, content, 1), "OK"


def cmd_dry_run(path):
    source, le = read_source(path)
    log(f"Dry-run on {path} ({len(source)} chars)")
    current = source
    for fix in FIXES:
        new_src, status = apply_fix(current, fix, le)
        icon = ("OK  " if status == "OK"
                else "SKIP" if status.startswith("SKIP") else "FAIL")
        print(f"  [{icon}] {fix.name:35s} -- {status}")
        if status == "OK":
            current = new_src
    return 0


def cmd_verify(path):
    source, _ = read_source(path)
    log(f"Verify on {path}")
    missing = 0
    for fix in FIXES:
        if fix.idempotency and fix.idempotency in source:
            print(f"  [OK  ] {fix.name}")
        else:
            print(f"  [MISS] {fix.name}")
            missing += 1
    return 0 if missing == 0 else 1


def cmd_rollback(path):
    if not os.path.isdir(BACKUP_DIR):
        log("No backup dir", level="ERROR")
        return 1
    base = os.path.basename(path)
    cands = sorted(
        [f for f in os.listdir(BACKUP_DIR)
         if f.startswith(base + ".") and f.endswith(".classifier.bak")],
        reverse=True,
    )
    if not cands:
        log("No classifier backups", level="ERROR")
        return 1
    src = os.path.join(BACKUP_DIR, cands[0])
    shutil.copy2(src, path)
    log(f"Restored {path} from {src}")
    return 0


def cmd_apply(path):
    source, le = read_source(path)
    log(f"Applying to {path}")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(
        BACKUP_DIR, f"{os.path.basename(path)}.{ts}.classifier.bak")
    shutil.copy2(path, backup)
    log(f"Backup: {backup}")

    current = source
    applied = 0
    skipped = 0
    hard_failure = False

    for fix in FIXES:
        new_src, status = apply_fix(current, fix, le)
        if status == "OK":
            current = new_src
            applied += 1
            log(f"  [OK  ] {fix.name}")
        elif status.startswith("SKIP"):
            skipped += 1
            log(f"  [SKIP] {fix.name} -- {status}")
        else:
            if fix.required:
                log(f"  [FAIL] {fix.name} -- {status}", level="ERROR")
                hard_failure = True
            else:
                log(f"  [WARN] {fix.name} -- {status}", level="WARN")

    if hard_failure:
        log("Rolling back — no changes written", level="ERROR")
        return 2

    try:
        compile(current, path, "exec")
        log("Syntax check: OK")
    except SyntaxError as e:
        log(f"Syntax error: {e}", level="ERROR")
        return 3

    write_source(path, current)
    log(f"Applied={applied} Skipped={skipped}")
    log(f"Backup: {backup}")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--target", default=BOT_FILE)
    args = p.parse_args()

    if not os.path.exists(args.target):
        log(f"Not found: {args.target}", level="ERROR")
        return 1

    if args.rollback:
        return cmd_rollback(args.target)
    if args.verify_only:
        return cmd_verify(args.target)
    if args.dry_run:
        return cmd_dry_run(args.target)
    return cmd_apply(args.target)


if __name__ == "__main__":
    sys.exit(main())
