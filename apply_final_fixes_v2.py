#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Targeted fix: correct order-cancellation parameter order.

Bug: for regular limit orders, ccxt silently accepts trigger=True
but doesn't actually cancel. We must send plain params for regular
orders, and trigger=True only for protective (STOP/TP) orders.

Applies to:
  test_exchange_comms.py  -> _cancel_order_robust
  trading_live_v2.py      -> _cleanup_symbol_orders, _lv_cancel_stale_legs,
                             _lv_startup_order_cleanup
"""

import argparse
import os
import shutil
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

TEST_FILE = "test_exchange_comms.py"
BOT_FILE = "trading_live_v2.py"
BACKUP_DIR = ".patches_backup"


# ═══════════════════════════════════════════════════════════════════

def log(msg, level="INFO"):
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def read_source(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    return raw, ("\r\n" if "\r\n" in raw else "\n")


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


def make_backup(path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(BACKUP_DIR,
                       f"{os.path.basename(path)}.{ts}.v2.bak")
    shutil.copy2(path, dst)
    log(f"  Backup: {dst}")
    return dst


def normalize(text, le):
    return (text.replace("\r\n", "\n").replace("\n", "\r\n")
            if le == "\r\n" else text.replace("\r\n", "\n"))


# ═══════════════════════════════════════════════════════════════════
# Fix: test_exchange_comms.py -- _cancel_order_robust
# ═══════════════════════════════════════════════════════════════════

T_ANCHOR = '''def _cancel_order_robust(exchange, oid, sym):
    """
    Try trigger=True first, then default. Handles -2011 gracefully.
    """
    for prm in ({'trigger': True}, {}):
        try:
            exchange.cancel_order(oid, sym, params=prm)
            return True, prm
        except Exception as e:
            m = str(e).lower()
            if ('-2011' in m or 'unknown order' in m
                    or 'not found' in m or 'does not exist' in m):
                return True, "already_cancelled"
            continue
    return False, None'''

T_CONTENT = '''def _cancel_order_robust(exchange, oid, sym, is_protective=None):
    """
    Robust cancel that respects Binance's split between regular orders
    and Algo (conditional) orders.

    Rule:
      - Regular limit order  -> plain cancel works
      - STOP_MARKET / TP     -> needs params={'trigger': True}

    Sending trigger=True on a regular order returns a SUCCESS response
    from Binance but does NOT actually cancel it (silent no-op).
    Therefore: for regular orders, try plain FIRST.
    """
    if is_protective is True:
        params_order = ({'trigger': True}, {})
    else:
        # Regular or unknown: plain first (this is the fix)
        params_order = ({}, {'trigger': True})

    for prm in params_order:
        try:
            exchange.cancel_order(oid, sym, params=prm)
            return True, (prm if prm else 'plain')
        except Exception as e:
            m = str(e).lower()
            if ('-2011' in m or 'unknown order' in m
                    or 'not found' in m or 'does not exist' in m):
                return True, "already_cancelled"
            continue
    return False, None'''


# ═══════════════════════════════════════════════════════════════════
# Fix: trading_live_v2.py -- _cleanup_symbol_orders inner loop
# ═══════════════════════════════════════════════════════════════════

B1_ANCHOR = '''                _done = False
                for _prm in ({'trigger': True}, {}):
                    try:
                        exchange.cancel_order(_oid, sym, params=_prm)
                        _rate_record(1.0)
                        _done = True
                        break
                    except Exception as _e:
                        _m = str(_e).lower()
                        if ('-2011' in _m or 'unknown order' in _m
                                or 'not found' in _m
                                or 'order does not exist' in _m):
                            _done = True
                            break
                        continue'''

B1_CONTENT = '''                # ══ [CANCEL-PARAMS] ترتيب المعاملات حسب نوع الأمر ══
                # Binance يفصل الأوامر العادية عن Algo (STOP/TP).
                # إرسال trigger=True لأمر عادي = نجاح كاذب بلا إلغاء.
                if _is_prot:
                    _params_order = ({'trigger': True}, {})
                else:
                    _params_order = ({}, {'trigger': True})
                _done = False
                for _prm in _params_order:
                    try:
                        exchange.cancel_order(_oid, sym, params=_prm)
                        _rate_record(1.0)
                        _done = True
                        break
                    except Exception as _e:
                        _m = str(_e).lower()
                        if ('-2011' in _m or 'unknown order' in _m
                                or 'not found' in _m
                                or 'order does not exist' in _m):
                            _done = True
                            break
                        continue'''

B1_IDEMPOTENCY = "# ══ [CANCEL-PARAMS] ترتيب المعاملات حسب نوع الأمر ══"


# ═══════════════════════════════════════════════════════════════════
# Fix: trading_live_v2.py -- _lv_cancel_stale_legs (already protective-only)
# Also works for regular orders if ever called with them.
# ═══════════════════════════════════════════════════════════════════

B2_ANCHOR = '''def _lv_cancel_stale_legs(exchange, sym: str, stale_order_ids: List[str]) -> int:
    """
    [SURGICAL-CANCEL] Cancel a specific list of order IDs (not "all").
    Uses trigger=True first (Algo Orders), falls back to default.
    Returns count cancelled.
    """
    n = 0
    for _oid in stale_order_ids:
        _done = False
        for _prm in ({'trigger': True}, {}):
            try:
                exchange.cancel_order(_oid, sym, params=_prm)
                _done = True
                n += 1
                break
            except Exception as _e:
                _m = str(_e).lower()
                if '-2011' in _m or 'unknown order' in _m:
                    _done = True
                    break
                continue
        if not _done:
            log.debug(f"[StaleCancel] {sym} oid={_oid} failed")
    return n'''

B2_CONTENT = '''def _lv_cancel_stale_legs(exchange, sym: str, stale_order_ids: List[str],
                            is_protective: bool = True) -> int:
    """
    [SURGICAL-CANCEL] Cancel a specific list of order IDs.
    Default is_protective=True (used by SL/TP swap logic).
    If is_protective=False, uses plain cancel first.
    """
    n = 0
    _params_order = (({'trigger': True}, {}) if is_protective
                     else ({}, {'trigger': True}))
    for _oid in stale_order_ids:
        _done = False
        for _prm in _params_order:
            try:
                exchange.cancel_order(_oid, sym, params=_prm)
                _done = True
                n += 1
                break
            except Exception as _e:
                _m = str(_e).lower()
                if '-2011' in _m or 'unknown order' in _m:
                    _done = True
                    break
                continue
        if not _done:
            log.debug(f"[StaleCancel] {sym} oid={_oid} failed")
    return n'''

B2_IDEMPOTENCY = "def _lv_cancel_stale_legs(exchange, sym: str, stale_order_ids: List[str],"


# ═══════════════════════════════════════════════════════════════════
# Fix: trading_live_v2.py -- _lv_startup_order_cleanup
# ═══════════════════════════════════════════════════════════════════

B3_ANCHOR = '''                if _should_cancel:
                    _done = False
                    for _prm in ({'trigger': True}, {}):
                        try:
                            exchange.cancel_order(oid, o.get('symbol') or sym,
                                                   params=_prm)
                            _rate_record(1.0)
                            _done = True
                            break
                        except Exception as _e:
                            _m = str(_e).lower()
                            if ('-2011' in _m or 'unknown order' in _m
                                    or 'not found' in _m):
                                _done = True
                                break
                            continue'''

B3_CONTENT = '''                if _should_cancel:
                    _done = False
                    _params_order = (({'trigger': True}, {}) if is_prot
                                     else ({}, {'trigger': True}))
                    for _prm in _params_order:
                        try:
                            exchange.cancel_order(oid, o.get('symbol') or sym,
                                                   params=_prm)
                            _rate_record(1.0)
                            _done = True
                            break
                        except Exception as _e:
                            _m = str(_e).lower()
                            if ('-2011' in _m or 'unknown order' in _m
                                    or 'not found' in _m):
                                _done = True
                                break
                            continue'''

B3_IDEMPOTENCY = "_params_order = (({'trigger': True}, {}) if is_prot"


# ═══════════════════════════════════════════════════════════════════

@dataclass
class Fix:
    name: str
    anchor: str
    content: str
    idempotency: str
    required: bool = True


TEST_FIXES = [
    Fix(name="T_cancel_robust_params",
        anchor=T_ANCHOR,
        content=T_CONTENT,
        idempotency="if is_protective is True:"),
]

BOT_FIXES = [
    Fix(name="B1_cleanup_cancel_params",
        anchor=B1_ANCHOR,
        content=B1_CONTENT,
        idempotency=B1_IDEMPOTENCY),
    Fix(name="B2_stale_legs_param",
        anchor=B2_ANCHOR,
        content=B2_CONTENT,
        idempotency=B2_IDEMPOTENCY),
    Fix(name="B3_startup_cancel_params",
        anchor=B3_ANCHOR,
        content=B3_CONTENT,
        idempotency=B3_IDEMPOTENCY,
        required=False),   # optional — only if code still uses old shape
]


def apply_fix(source, fix, le):
    if fix.idempotency in source:
        return source, "SKIP (already applied)"
    anchor = normalize(fix.anchor, le)
    content = normalize(fix.content, le)
    cnt = source.count(anchor)
    if cnt == 0:
        return source, "ERROR: anchor not found"
    if cnt > 1:
        return source, f"ERROR: anchor appears {cnt} times"
    return source.replace(anchor, content, 1), "OK"


def process_file(path, fixes, dry_run=False):
    if not os.path.exists(path):
        log(f"Not found: {path}", level="ERROR")
        return 1
    source, le = read_source(path)
    log(f"Processing {path} ({len(source)} chars)")

    if dry_run:
        current = source
        for fix in fixes:
            _, status = apply_fix(current, fix, le)
            icon = ("OK  " if status == "OK"
                    else "SKIP" if status.startswith("SKIP") else "FAIL")
            print(f"  [{icon}] {fix.name:35s} -- {status}")
            if status == "OK":
                current, _ = apply_fix(current, fix, le)
        return 0

    make_backup(path)
    current = source
    hard_failure = False

    for fix in fixes:
        new_src, status = apply_fix(current, fix, le)
        if status == "OK":
            current = new_src
            log(f"  [OK  ] {fix.name:35s}")
        elif status.startswith("SKIP"):
            log(f"  [SKIP] {fix.name:35s} -- {status}")
        else:
            _lvl = "ERROR" if fix.required else "WARN"
            log(f"  [FAIL] {fix.name:35s} -- {status}", level=_lvl)
            if fix.required:
                hard_failure = True

    if hard_failure:
        log("Rolling back", level="ERROR")
        return 2

    try:
        compile(current, path, "exec")
        log("  Syntax check: OK")
    except SyntaxError as e:
        log(f"  Syntax error: {e}", level="ERROR")
        return 4

    write_source(path, current)
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rollback", action="store_true")
    args = p.parse_args()

    targets = [(TEST_FILE, TEST_FIXES), (BOT_FILE, BOT_FIXES)]

    if args.rollback:
        for path, _ in targets:
            base = os.path.basename(path)
            cands = sorted([
                f for f in os.listdir(BACKUP_DIR)
                if f.startswith(base + ".") and f.endswith(".v2.bak")
            ], reverse=True) if os.path.isdir(BACKUP_DIR) else []
            if cands:
                shutil.copy2(os.path.join(BACKUP_DIR, cands[0]), path)
                log(f"Restored {path}")
        return 0

    if args.verify_only:
        ok = 0
        miss = 0
        for path, fixes in targets:
            if not os.path.exists(path):
                continue
            source, _ = read_source(path)
            print(f"\n  {path}")
            for fix in fixes:
                if fix.idempotency in source:
                    print(f"    [OK  ] {fix.name}")
                    ok += 1
                else:
                    print(f"    [MISS] {fix.name}")
                    miss += 1
        return 0 if miss == 0 else 1

    if args.dry_run:
        for path, fixes in targets:
            log(f"[DRY-RUN] {path}")
            process_file(path, fixes, dry_run=True)
        return 0

    for path, fixes in targets:
        log(f"═══ {path} ═══")
        process_file(path, fixes)
        print()
    log("Done. Next: python test_exchange_comms.py ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
