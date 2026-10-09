#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Small-Capital Post-Only + Order Hygiene Patcher for trading_live_v2.py
════════════════════════════════════════════════════════════════════════
Applies 18 surgical fixes. Safe, idempotent, reversible.

Usage:
    python apply_patches.py                       # patch trading_live_v2.py
    python apply_patches.py --target other.py
    python apply_patches.py --dry-run             # preview
    python apply_patches.py --verify-only         # check current state
    python apply_patches.py --rollback            # restore latest backup
"""

import argparse
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

DEFAULT_TARGET = "trading_live_v2.py"
BACKUP_DIR = ".patches_backup"


# ═══════════════════════════════════════════════════════════════════
# I/O helpers
# ═══════════════════════════════════════════════════════════════════

def log(msg: str, level: str = "INFO") -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def read_source(path: str) -> Tuple[str, str]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    le = "\r\n" if "\r\n" in raw else "\n"
    return raw, le


def write_source(path: str, content: str) -> None:
    tmp = path + ".patched_tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(content)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


def make_backup(path: str) -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = os.path.basename(path)
    dst = os.path.join(BACKUP_DIR, f"{base}.{ts}.bak")
    shutil.copy2(path, dst)
    log(f"Backup: {dst}")
    return dst


def latest_backup(path: str) -> Optional[str]:
    if not os.path.isdir(BACKUP_DIR):
        return None
    base = os.path.basename(path)
    candidates = [f for f in os.listdir(BACKUP_DIR)
                  if f.startswith(base + ".") and f.endswith(".bak")]
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return os.path.join(BACKUP_DIR, candidates[0])


# ═══════════════════════════════════════════════════════════════════
# Fix definition
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Fix:
    name: str
    kind: str           # 'insert_before' | 'insert_after' | 'replace' | 'replace_between'
    anchor: str         # unique string in source (for insert_* and replace)
    start_marker: str = ""   # for 'replace_between'
    end_marker: str = ""
    content: str = ""
    idempotency: str = ""    # if present in source → skip
    description: str = ""
    applied: bool = False
    skipped: bool = False
    error: str = ""


# ═══════════════════════════════════════════════════════════════════
# Fix content definitions
# ═══════════════════════════════════════════════════════════════════

A1_CONTENT = """

    # ══ [SMALL-CAPITAL POST-ONLY] ══
    # تحت هذه العتبة، كل أوامر الدخول والخروج غير الطارئة إلزامية Post-Only.
    SMALL_CAPITAL_THRESHOLD: float = 100.0
    FORCE_POST_ONLY_BELOW_CAPITAL: bool = True
    PO_MAX_ATTEMPTS_SMALLCAP: int = 5
    PO_MAX_WAIT_S_SMALLCAP: int = 90
    SMALLCAP_DISABLE_PARTIAL_TP: bool = True
    SMALLCAP_DISABLE_SING_MARKETABLE: bool = True
"""

A2A3_CONTENT = """

# ══ [SMALL-CAPITAL STATE] ══
_LIVE_CAPITAL_STATE: Dict = {
    'capital': 0.0,
    'post_only_forced': False,
    'forced_since_ts': 0.0,
    'forced_transitions': 0,
    'rejected_cross_attempts': 0,
}


def _is_post_only_forced(capital: float) -> bool:
    if not getattr(CFG, 'FORCE_POST_ONLY_BELOW_CAPITAL', True):
        return False
    try:
        return float(capital) < float(CFG.SMALL_CAPITAL_THRESHOLD)
    except Exception:
        return False


def _refresh_post_only_state(capital: float) -> None:
    _forced_now = _is_post_only_forced(capital)
    _was_forced = bool(_LIVE_CAPITAL_STATE.get('post_only_forced', False))
    _LIVE_CAPITAL_STATE['capital'] = float(capital)

    if _forced_now and not _was_forced:
        _LIVE_CAPITAL_STATE['post_only_forced'] = True
        _LIVE_CAPITAL_STATE['forced_since_ts'] = time.time()
        _LIVE_CAPITAL_STATE['forced_transitions'] += 1
        log.warning(
            f"[SmallCap] POST-ONLY MODE ENGAGED -- capital "
            f"${capital:.2f} < ${CFG.SMALL_CAPITAL_THRESHOLD:.0f}. "
            f"All non-emergency orders -> GTX (maker)."
        )
    elif not _forced_now and _was_forced:
        _LIVE_CAPITAL_STATE['post_only_forced'] = False
        _LIVE_CAPITAL_STATE['forced_transitions'] += 1
        log.info(
            f"[SmallCap] POST-ONLY MODE RELEASED -- capital "
            f"${capital:.2f} >= ${CFG.SMALL_CAPITAL_THRESHOLD:.0f}. "
            f"Transitions: {_LIVE_CAPITAL_STATE['forced_transitions']}"
        )
    else:
        _LIVE_CAPITAL_STATE['post_only_forced'] = _forced_now
"""

A4_ANCHOR = """    _tick = _get_tick_size(exchange, symbol)

    def _refresh_active():"""

A4_CONTENT = """    _tick = _get_tick_size(exchange, symbol)

    # ══ [SMALL-CAPITAL OVERRIDE] ══
    _po_forced = bool(_LIVE_CAPITAL_STATE.get('post_only_forced', False))
    _is_emergency = (
        bool(fallback_market) and bool(cross_spread) and bool(reduce_only)
    )
    if _po_forced and not _is_emergency:
        if cross_spread or fallback_market:
            _LIVE_CAPITAL_STATE['rejected_cross_attempts'] = int(
                _LIVE_CAPITAL_STATE.get('rejected_cross_attempts', 0)
            ) + 1
        cross_spread = False
        fallback_market = False
        _new_wait = int(getattr(CFG, 'PO_MAX_WAIT_S_SMALLCAP', 90))
        if max_wait_s is None or int(max_wait_s) < _new_wait:
            max_wait_s = _new_wait
        if not reduce_only:
            max_attempts = int(getattr(CFG, 'PO_MAX_ATTEMPTS_SMALLCAP', 5))

    def _refresh_active():"""

A5A_ANCHOR = """    _exec_mode = "gtx"
    _marketable_px = None"""

A5A_CONTENT = """    # ══ [SMALL-CAPITAL] منع Marketable تحت رأس مال صغير ══
    _po_forced_pp = bool(_LIVE_CAPITAL_STATE.get('post_only_forced', False))
    _sing_marketable_disabled = (
        _po_forced_pp
        and getattr(CFG, 'SMALLCAP_DISABLE_SING_MARKETABLE', True)
    )

    _exec_mode = "gtx"
    _marketable_px = None"""

A5B_ANCHOR = """    if (getattr(CFG, 'SING_TIMING_ENABLED', False)
            and getattr(CFG, 'SING_ACTIVE_MARKETABLE', False)
            and _sing_state == "ACTIVE"):"""

A5B_CONTENT = """    if (not _sing_marketable_disabled
            and getattr(CFG, 'SING_TIMING_ENABLED', False)
            and getattr(CFG, 'SING_ACTIVE_MARKETABLE', False)
            and _sing_state == "ACTIVE"):"""

A6_ANCHOR = """                        _cross = bool(_urgent and
                                      getattr(CFG, 'PO_EXIT_URGENT_CROSS_SPREAD', True))
                        _wait = (
                            int(getattr(CFG, 'PO_EXIT_URGENT_WAIT_S', 4))
                            if _urgent
                            else int(CFG.PO_EXIT_MAX_WAIT_S)
                        )"""

A6_CONTENT = """                        _cross = bool(_urgent and
                                      getattr(CFG, 'PO_EXIT_URGENT_CROSS_SPREAD', True))
                        _wait = (
                            int(getattr(CFG, 'PO_EXIT_URGENT_WAIT_S', 4))
                            if _urgent
                            else int(CFG.PO_EXIT_MAX_WAIT_S)
                        )
                        _po_forced_exit = bool(_LIVE_CAPITAL_STATE.get(
                            'post_only_forced', False))
                        if _po_forced_exit and 'Emergency LiqProximity' not in rsn:
                            if _cross:
                                _LIVE_CAPITAL_STATE['rejected_cross_attempts'] = int(
                                    _LIVE_CAPITAL_STATE.get(
                                        'rejected_cross_attempts', 0)) + 1
                                log.info(
                                    f"[SmallCap] {sym} blocking cross_spread "
                                    f"for exit: {rsn}"
                                )
                            _cross = False
                            _wait = int(max(_wait, getattr(
                                CFG, 'PO_MAX_WAIT_S_SMALLCAP', 90)))"""

A7_ANCHOR = """                _LV_STATE['free'] = _bal_free
                _LV_STATE['bal_ok'] = True
                _last_known_cap = cap_live"""

A7_CONTENT = """                _LV_STATE['free'] = _bal_free
                _LV_STATE['bal_ok'] = True
                _last_known_cap = cap_live
                _refresh_post_only_state(cap_live)"""

A8_ANCHOR = """                if (not ex
                        and getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                        and not pos.get('_broker_partial', False)
                        and not pos.get('_partial_taken', False)):"""

A8_CONTENT = """                _partial_disabled_smallcap = (
                    bool(_LIVE_CAPITAL_STATE.get('post_only_forced', False))
                    and getattr(CFG, 'SMALLCAP_DISABLE_PARTIAL_TP', True)
                )
                if (not ex
                        and not _partial_disabled_smallcap
                        and getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                        and not pos.get('_broker_partial', False)
                        and not pos.get('_partial_taken', False)):"""

B1_CONTENT = '''

def _cleanup_symbol_orders(exchange, sym: str,
                            include_entries: bool = True,
                            include_protective: bool = True,
                            reason: str = "unknown") -> Dict:
    """
    [ORDER-HYGIENE] إلغاء شامل ومنظم لكل أوامر الرمز.
    """
    stats = {'protective': 0, 'entries': 0, 'failed': 0,
             'passes': 0, 'reason': reason}
    if not sym:
        return stats

    for pass_idx in range(2):
        stats['passes'] = pass_idx + 1
        try:
            _rate_record(2.0)
            orders = _lv_open_orders_all(exchange, sym)
        except Exception as e:
            log.debug(f"[OrderHygiene:{reason}] {sym} fetch failed: {e}")
            try:
                orders = exchange.fetch_open_orders(sym)
            except Exception as e2:
                log.debug(f"[OrderHygiene:{reason}] {sym} fallback failed: {e2}")
                break
        if not orders:
            break

        _cancelled_this_pass = 0
        for o in orders:
            try:
                _is_prot = _is_protective_order(o)
                if _is_prot and not include_protective:
                    continue
                if (not _is_prot) and not include_entries:
                    continue
                _cat = 'protective' if _is_prot else 'entries'
                _oid = o.get('id')
                if not _oid:
                    continue
                _done = False
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
                        continue
                if _done:
                    stats[_cat] += 1
                    _cancelled_this_pass += 1
                else:
                    stats['failed'] += 1
            except Exception as _e:
                log.debug(f"[OrderHygiene:{reason}] {sym} item error: {_e}")
                stats['failed'] += 1

        if _cancelled_this_pass == 0:
            break
        time.sleep(0.25)

    if stats['protective'] or stats['entries']:
        log.info(
            f"[OrderHygiene:{reason}] {sym}: "
            f"protective={stats['protective']} "
            f"entries={stats['entries']} "
            f"failed={stats['failed']} "
            f"passes={stats['passes']}"
        )
    return stats

'''

B1_ANCHOR = """                log.warning(f"[Prot] cancel {sym} oid={_oid} failed")
        import time as _t
        _t.sleep(0.3)
    return n"""

B1_CONTENT = """                log.warning(f"[Prot] cancel {sym} oid={_oid} failed")
        import time as _t
        _t.sleep(0.3)
    return n
""" + B1_CONTENT

B2_ANCHOR = """                    # ══ Position now closed. Clean any leftover protective
                    # orders. With closePosition=True, Binance auto-cancels
                    # them; this is defensive for edge cases (partial fills,
                    # exchange lag). ══
                    try:
                        _leftovers = _cancel_all_protective_orders(exchange, sym)
                        if _leftovers > 0:
                            log.debug(f"[Prot] {sym} cleaned "
                                      f"{_leftovers} leftover order(s)")
                    except Exception as _e:
                        log.debug(f"[Prot] {sym} post-exit cleanup: {_e}")"""

B2_CONTENT = """                    # ══ [ORDER-HYGIENE] إلغاء كامل عند إغلاق المركز ══
                    try:
                        _hygiene = _cleanup_symbol_orders(
                            exchange, sym,
                            include_entries=True,
                            reason=f"exit:{exit_reason[:30]}"
                        )
                    except Exception as _e:
                        log.warning(f"[OrderHygiene] {sym} failed: {_e}")"""

B3_ANCHOR = """    try:
        _cancel_all_protective_orders(exchange, sym)
    except Exception:
        pass
    _LV_LAST_EXIT[sym] = time.time()"""

B3_CONTENT = """    try:
        _cleanup_symbol_orders(
            exchange, sym,
            include_entries=True,
            reason="exchange-closed"
        )
    except Exception as _e:
        log.debug(f"[OrderHygiene:exchange-closed] {sym} failed: {_e}")
    _LV_LAST_EXIT[sym] = time.time()"""

B4_ANCHOR = """    # Cancel all pending
    for sym in list(_PENDING_ORDERS.keys()):
        rec = _PENDING_ORDERS[sym]
        oid = rec.get('order_id')
        if oid:
            try:
                exchange.cancel_order(oid, sym)
            except Exception:
                pass
        _PENDING_ORDERS.pop(sym, None)

    try:
        _lv_kill_flatten_all(exchange)
    except Exception as _e:
        log.error(f"[KillSwitch] second pass failed: {_e}")"""

B4_CONTENT = """    # ══ [ORDER-HYGIENE] تنظيف كامل قبل الإغلاق الجماعي ══
    _all_syms_ks = set(list(open_pos_live.keys())
                        + list(_PENDING_ORDERS.keys())
                        + list(_WATCHED_SIGNALS.keys()))
    for sym in _all_syms_ks:
        try:
            _cleanup_symbol_orders(
                exchange, sym,
                include_entries=True,
                reason="kill-switch"
            )
        except Exception as _e:
            log.debug(f"[OrderHygiene:kill-switch] {sym} failed: {_e}")

    _PENDING_ORDERS.clear()
    _WATCHED_SIGNALS.clear()

    try:
        _lv_kill_flatten_all(exchange)
    except Exception as _e:
        log.error(f"[KillSwitch] second pass failed: {_e}")"""

B6_ANCHOR = """            # ══ Persist state ══
            try:
                _lv_save_state(state_file, open_pos_live)"""

B6_CONTENT = """            # ══ [ORDER-HYGIENE-AUDIT] تدقيق كل 5 دقائق ══
            if not hasattr(run_live, '_last_hygiene_audit'):
                run_live._last_hygiene_audit = time.time()
            if time.time() - run_live._last_hygiene_audit > 300:
                try:
                    _active_syms = (set(open_pos_live.keys())
                                     | set(_PENDING_ORDERS.keys()))
                    try:
                        _rate_record(40.0)
                        _all_open = _lv_open_orders_all(exchange, None)
                    except Exception:
                        _all_open = []
                    from collections import defaultdict as _dd_audit
                    _by_sym_a = _dd_audit(list)
                    for o in _all_open or []:
                        try:
                            _rs = str(o.get('symbol') or '')
                            _s = _rs.split(':')[0] if ':' in _rs else _rs
                            if _s:
                                _by_sym_a[_s].append(o)
                        except Exception:
                            continue
                    _orphans_cleaned = 0
                    for _s, _orders in _by_sym_a.items():
                        if _s in _active_syms:
                            continue
                        if _orders:
                            log.warning(
                                f"[Hygiene-Audit] {_s} has "
                                f"{len(_orders)} orphan order(s) -- cleaning"
                            )
                            _cleanup_symbol_orders(
                                exchange, _s,
                                include_entries=True,
                                reason="audit-orphan"
                            )
                            _orphans_cleaned += 1
                    if _orphans_cleaned > 0:
                        log.info(f"[Hygiene-Audit] cleaned "
                                 f"{_orphans_cleaned} orphan symbol(s)")
                except Exception as _e:
                    log.warning(f"[Hygiene-Audit] failed: {_e}")
                run_live._last_hygiene_audit = time.time()

            # ══ Persist state ══
            try:
                _lv_save_state(state_file, open_pos_live)"""

C1_ANCHOR = """    pos['qty'] = left
    pos['_partial_taken'] = True
    pos['_prot_last_sl'] = None
    log.warning(f"⚠️ [Exit] {sym} PARTIAL exit fill {filled}/{total} → remainder {left} stays "
                f"open and protected; retrying next cycle")
    return True"""

C1_CONTENT = """    pos['qty'] = left
    pos['_partial_taken'] = True
    pos['_prot_last_sl'] = None
    try:
        _cleanup_symbol_orders(
            exchange, sym,
            include_entries=True,
            include_protective=False,
            reason="partial-exit"
        )
    except Exception as _e:
        log.debug(f"[OrderHygiene:partial-exit] {sym} failed: {_e}")
    log.warning(f"⚠️ [Exit] {sym} PARTIAL exit fill {filled}/{total} → remainder {left} stays "
                f"open and protected; retrying next cycle")
    return True"""

C2_ANCHOR = """        _ok = (placed['sl'] and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if _ok:
            return True
        log.warning(f"[Prot] {sym} incomplete after place-first: "
                    f"sl={placed['sl']} tp={placed['tp']} "
                    f"partial={placed['partial_tp']}")
        return _ok"""

C2_CONTENT = """        _ok = (placed['sl'] and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if not placed['sl']:
            log.critical(
                f"🚨 [PROT-FAIL] {sym} STOP LOSS FAILED TO PLACE -- "
                f"position is UNPROTECTED on exchange. "
                f"qty={qty} entry={pos.get('entry')} sl={sl} tp={tp}."
            )
        if _ok:
            return True
        log.warning(f"[Prot] {sym} incomplete after place-first: "
                    f"sl={placed['sl']} tp={placed['tp']} "
                    f"partial={placed['partial_tp']}")
        return _ok"""

D1_ANCHOR = """def _lv_atomic_json(path, obj) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=2, default=str)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)"""

D1_CONTENT = """def _lv_atomic_json(path, obj) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, 'w') as f:
        json.dump(obj, f, indent=2, default=str)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)
    try:
        _dir = os.path.dirname(os.path.abspath(path)) or "."
        _dfd = os.open(_dir, os.O_RDONLY)
        try:
            os.fsync(_dfd)
        finally:
            os.close(_dfd)
    except Exception:
        pass"""


# ═══════════════════════════════════════════════════════════════════
# Fix list
# ═══════════════════════════════════════════════════════════════════

FIXES: List[Fix] = [
    Fix(name="A1_config_fields",
        kind="insert_before",
        anchor="CFG = Config()",
        content=A1_CONTENT,
        idempotency="SMALL_CAPITAL_THRESHOLD: float = 100.0",
        description="Add Small-Capital config fields"),

    Fix(name="A2A3_state_and_functions",
        kind="insert_after",
        anchor="_LIQ_EMERGENCY_STATS: Dict = {\n    'triggers': 0,\n    'last_warned_at': 0.0,\n}",
        content=A2A3_CONTENT,
        idempotency="_LIVE_CAPITAL_STATE: Dict = {",
        description="Add Post-Only state + functions"),

    Fix(name="A4_execute_post_only_override",
        kind="replace",
        anchor=A4_ANCHOR,
        content=A4_CONTENT,
        idempotency="_po_forced = bool(_LIVE_CAPITAL_STATE.get('post_only_forced', False))",
        description="Enforce Post-Only in execute_post_only"),

    Fix(name="A5a_place_pending_var",
        kind="replace",
        anchor=A5A_ANCHOR,
        content=A5A_CONTENT,
        idempotency="_sing_marketable_disabled = (",
        description="Add SmallCap variable in place_pending_entry"),

    Fix(name="A5b_place_pending_condition",
        kind="replace",
        anchor=A5B_ANCHOR,
        content=A5B_CONTENT,
        idempotency="    if (not _sing_marketable_disabled",
        description="Gate Marketable upgrade by SmallCap flag"),

    Fix(name="A6_run_live_exit_gate",
        kind="replace",
        anchor=A6_ANCHOR,
        content=A6_CONTENT,
        idempotency="_po_forced_exit = bool(_LIVE_CAPITAL_STATE.get(",
        description="Block cross_spread on exit under SmallCap"),

    Fix(name="A7_run_live_refresh",
        kind="replace",
        anchor=A7_ANCHOR,
        content=A7_CONTENT,
        idempotency="_refresh_post_only_state(cap_live)",
        description="Refresh Post-Only state each loop"),

    Fix(name="A8_partial_tp_gate",
        kind="replace",
        anchor=A8_ANCHOR,
        content=A8_CONTENT,
        idempotency="_partial_disabled_smallcap = (",
        description="Disable Partial TP under SmallCap"),

    Fix(name="B1_cleanup_symbol_orders",
        kind="replace",
        anchor=B1_ANCHOR,
        content=B1_CONTENT,
        idempotency="def _cleanup_symbol_orders(exchange, sym: str,",
        description="Add _cleanup_symbol_orders function"),

    Fix(name="B2_run_live_cleanup",
        kind="replace",
        anchor=B2_ANCHOR,
        content=B2_CONTENT,
        idempotency='reason=f"exit:{exit_reason[:30]}"',
        description="Use OrderHygiene in exit block"),

    Fix(name="B3_exchange_closed_cleanup",
        kind="replace",
        anchor=B3_ANCHOR,
        content=B3_CONTENT,
        idempotency='reason="exchange-closed"',
        description="OrderHygiene on exchange-close"),

    Fix(name="B4_kill_switch_cleanup",
        kind="replace",
        anchor=B4_ANCHOR,
        content=B4_CONTENT,
        idempotency='reason="kill-switch"',
        description="OrderHygiene on kill switch"),

    Fix(name="C1_partial_exit_cleanup",
        kind="replace",
        anchor=C1_ANCHOR,
        content=C1_CONTENT,
        idempotency='include_protective=False',
        description="Preserve protection on partial exit"),

    Fix(name="C2_prot_fail_critical",
        kind="replace",
        anchor=C2_ANCHOR,
        content=C2_CONTENT,
        idempotency="[PROT-FAIL]",
        description="Critical log if SL fails"),

    Fix(name="D1_atomic_fsync_dir",
        kind="replace",
        anchor=D1_ANCHOR,
        content=D1_CONTENT,
        idempotency="os.O_RDONLY",
        description="fsync directory on atomic save"),
]


# ═══════════════════════════════════════════════════════════════════
# Replacement engine
# ═══════════════════════════════════════════════════════════════════

def normalize(text: str, le: str) -> str:
    if le == "\r\n":
        return text.replace("\r\n", "\n").replace("\n", "\r\n")
    return text.replace("\r\n", "\n")


def apply_fix(source: str, fix: Fix, le: str) -> Tuple[str, str]:
    """Returns (new_source, status)."""
    # Idempotency
    if fix.idempotency and fix.idempotency in source:
        return source, "SKIP (already applied)"

    anchor = normalize(fix.anchor, le)
    content = normalize(fix.content, le)

    if fix.kind == "replace_between":
        start_marker = normalize(fix.start_marker, le)
        end_marker = normalize(fix.end_marker, le)
        i = source.find(start_marker)
        if i == -1:
            return source, "ERROR: start_marker not found"
        j = source.find(end_marker, i + len(start_marker))
        if j == -1:
            return source, "ERROR: end_marker not found"
        return source[:i] + content + source[j:], "OK"

    cnt = source.count(anchor)
    if cnt == 0:
        return source, "ERROR: anchor not found"
    if cnt > 1:
        return source, f"ERROR: anchor appears {cnt} times (must be unique)"

    if fix.kind == "insert_before":
        return source.replace(anchor, content + anchor, 1), "OK"
    if fix.kind == "insert_after":
        return source.replace(anchor, anchor + content, 1), "OK"
    if fix.kind == "replace":
        return source.replace(anchor, content, 1), "OK"
    return source, f"ERROR: unknown kind '{fix.kind}'"


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def cmd_dry_run(target: str) -> int:
    source, le = read_source(target)
    log(f"Dry-run on {target} ({len(source)} chars)")
    for fix in FIXES:
        _, status = apply_fix(source, fix, le)
        icon = "OK  " if status == "OK" else ("SKIP" if status.startswith("SKIP") else "FAIL")
        print(f"  [{icon}] {fix.name:35s} -- {status}")
        if status == "OK":
            new_src, _ = apply_fix(source, fix, le)
            source = new_src
    return 0


def cmd_verify(target: str) -> int:
    source, _ = read_source(target)
    log(f"Verify on {target}")
    applied = 0
    missing = 0
    for fix in FIXES:
        if fix.idempotency and fix.idempotency in source:
            print(f"  [OK  ] {fix.name:35s} -- present")
            applied += 1
        else:
            print(f"  [MISS] {fix.name:35s} -- ABSENT")
            missing += 1
    log(f"Summary: {applied}/{len(FIXES)} applied, {missing} missing")
    return 0 if missing == 0 else 1


def cmd_apply(target: str) -> int:
    source, le = read_source(target)
    log(f"Applying patches to {target}")
    backup = make_backup(target)

    current = source
    results: List[Tuple[Fix, str]] = []
    hard_failure = False

    for fix in FIXES:
        new_src, status = apply_fix(current, fix, le)
        results.append((fix, status))
        if status == "OK":
            current = new_src
            log(f"  [OK  ] {fix.name:35s} -- applied")
        elif status.startswith("SKIP"):
            log(f"  [SKIP] {fix.name:35s} -- {status}")
        else:
            log(f"  [FAIL] {fix.name:35s} -- {status}", level="ERROR")
            hard_failure = True

    if hard_failure:
        log("Rolling back (no changes written)", level="ERROR")
        return 2

    # Final verification: each non-skipped fix's content should be present
    for fix, status in results:
        if status == "OK" and fix.idempotency:
            if fix.idempotency not in current:
                log(f"Post-verify FAILED for {fix.name}", level="ERROR")
                return 3

    # Syntax check via compile
    try:
        compile(current, target, "exec")
        log("Syntax check: OK")
    except SyntaxError as e:
        log(f"Syntax error after patching: {e}", level="ERROR")
        log(f"Backup preserved at {backup}", level="ERROR")
        return 4

    write_source(target, current)
    log(f"Applied {sum(1 for _, s in results if s == 'OK')} fixes")
    log(f"Skipped {sum(1 for _, s in results if s.startswith('SKIP'))}")
    log(f"Backup: {backup}")
    return 0


def cmd_rollback(target: str) -> int:
    backup = latest_backup(target)
    if not backup:
        log("No backup found", level="ERROR")
        return 1
    shutil.copy2(backup, target)
    log(f"Restored from {backup}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Small-Capital Post-Only + Order Hygiene Patcher")
    p.add_argument("--target", default=DEFAULT_TARGET,
                   help=f"target file (default: {DEFAULT_TARGET})")
    p.add_argument("--dry-run", action="store_true",
                   help="show what would change without writing")
    p.add_argument("--verify-only", action="store_true",
                   help="check which fixes are present")
    p.add_argument("--rollback", action="store_true",
                   help="restore latest backup")
    args = p.parse_args()

    if not os.path.exists(args.target):
        log(f"Target not found: {args.target}", level="ERROR")
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
