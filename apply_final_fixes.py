#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
Final Fixes Patcher
═══════════════════════════════════════════════════════════════════════════
Applies 8 fixes across two files:

  test_exchange_comms.py (3):
    T1. test_leverage_tiers  -- handle dict[sym, list] shape
    T2. test_limit_gtx_place -- respect MIN_NOTIONAL
    T3. test_scan_tickers    -- handle BTC/USDT:USDT futures

  trading_live_v2.py (5):
    B1. Add _get_min_notional() + cache
    B2. Use it in place_pending_entry (pre-check)
    B3. Use it in run_live before entry
    B4. Add position check in _lv_ensure_protection
    B5. Clean up _lv_preflight_check globals() guard

Usage:
    python apply_final_fixes.py                    # patch both
    python apply_final_fixes.py --dry-run          # preview
    python apply_final_fixes.py --verify-only      # check state
    python apply_final_fixes.py --rollback         # restore latest
    python apply_final_fixes.py --file X.py        # patch one file only
═══════════════════════════════════════════════════════════════════════════
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
    log(f"  Backup: {dst}")
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


def normalize(text: str, le: str) -> str:
    if le == "\r\n":
        return text.replace("\r\n", "\n").replace("\n", "\r\n")
    return text.replace("\r\n", "\n")


# ═══════════════════════════════════════════════════════════════════
# Fix definition
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Fix:
    name: str
    kind: str           # insert_before | insert_after | replace
    anchor: str
    content: str = ""
    idempotency: str = ""
    required: bool = True
    description: str = ""


# ═══════════════════════════════════════════════════════════════════
# ══ TEST FILE FIXES ══
# ═══════════════════════════════════════════════════════════════════

T1_ANCHOR = '''def test_leverage_tiers(exchange, symbol):
    def run():
        raw = exchange.fetch_leverage_tiers([symbol])
        # Handle both list and dict shapes (ccxt 4.x)
        if isinstance(raw, dict):
            entry = raw.get(symbol) or next(iter(raw.values()), None)
        elif isinstance(raw, list):
            entry = raw[0] if raw else None
        else:
            entry = None
        if not entry:
            return "FAIL", f"unexpected shape: {type(raw).__name__}"
        tiers = entry.get('tiers') or []
        if not tiers:
            return "FAIL", "no tiers"
        max_lev = int(tiers[0].get('maxLeverage', 0))
        mmr = float(tiers[0].get('maintenanceMarginRate', 0))
        return "PASS", f"tiers={len(tiers)} max_lev={max_lev}x mmr={mmr*100:.3f}%"
    return run'''

T1_CONTENT = '''def test_leverage_tiers(exchange, symbol):
    def run():
        raw = exchange.fetch_leverage_tiers([symbol])

        def _sym_match(a, b):
            if not a or not b:
                return False
            return a.split(':')[0] == b.split(':')[0]

        def _wrap(v):
            if isinstance(v, dict):
                return v
            if isinstance(v, list):
                return {'symbol': symbol, 'tiers': v}
            return None

        entry = None
        if isinstance(raw, list):
            if raw:
                for e in raw:
                    if isinstance(e, dict) and _sym_match(
                            e.get('symbol', ''), symbol):
                        entry = e
                        break
                if entry is None and isinstance(raw[0], dict):
                    entry = raw[0]
        elif isinstance(raw, dict):
            if symbol in raw:
                entry = _wrap(raw[symbol])
            else:
                for k, v in raw.items():
                    if _sym_match(k, symbol):
                        entry = _wrap(v)
                        break
                if entry is None and len(raw) > 0:
                    entry = _wrap(next(iter(raw.values())))

        if not entry:
            return "FAIL", f"unexpected shape: {type(raw).__name__}"

        tiers = entry.get('tiers') or []
        if not tiers:
            return "FAIL", f"no tiers (keys: {list(entry.keys())})"

        first = tiers[0]
        if not isinstance(first, dict):
            return "FAIL", f"tier[0] is {type(first).__name__}"

        max_lev = int(first.get('maxLeverage', 0))
        mmr = float(first.get('maintenanceMarginRate', 0))
        return "PASS", f"tiers={len(tiers)} max_lev={max_lev}x mmr={mmr*100:.3f}%"
    return run'''


T2_ANCHOR = '''def test_limit_gtx_place(exchange, symbol):
    """Place a limit GTX far from market (should stay open)."""
    state = {}
    def run():
        tick = _get_tick_size(exchange, symbol) or 0.01
        q = _get_min_qty(exchange, symbol) or 0.001
        ticker = exchange.fetch_ticker(symbol)
        last = float(ticker['last'])
        # Place BUY at -5% (far below, safe GTX)
        price = _round_to_tick(last * 0.95, tick)
        o = exchange.create_order(
            symbol, 'limit', 'buy', q, price,
            params={'timeInForce': 'GTX'}
        )
        state['order'] = o
        state['id'] = o['id']
        state['symbol'] = symbol
        # Register cleanup
        CLEANUP_ACTIONS.append(
            lambda: _cancel_order_robust(exchange, state['id'], symbol)
        )
        return "PASS", f"id={o['id']} @ {price} qty={q}"
    return run'''

T2_CONTENT = '''def test_limit_gtx_place(exchange, symbol):
    """Place a limit GTX far from market (should stay open)."""
    state = {}

    def run():
        tick = _get_tick_size(exchange, symbol) or 0.01
        ticker = exchange.fetch_ticker(symbol)
        last = float(ticker['last'])
        if last <= 0:
            return "FAIL", "no last price"

        # MIN_NOTIONAL from exchange filters
        m = exchange.market(symbol)
        min_notional = 5.0
        info = m.get('info') or {}
        for f in (info.get('filters') or []):
            if isinstance(f, dict) and f.get('filterType') == 'MIN_NOTIONAL':
                try:
                    min_notional = float(f.get('notional', 5.0))
                except Exception:
                    pass
                break
        if min_notional <= 0:
            min_notional = 5.0

        # qty = (min_notional x 1.2) / price
        qty_raw = (min_notional * 1.2) / last
        qty = float(exchange.amount_to_precision(symbol, qty_raw))

        actual_notional = qty * last
        if actual_notional < min_notional:
            qty_raw = (min_notional * 1.5) / last
            qty = float(exchange.amount_to_precision(symbol, qty_raw))
            actual_notional = qty * last

        if qty <= 0:
            return "FAIL", f"computed qty=0 (min_notional={min_notional})"

        price = _round_to_tick(last * 0.95, tick)
        try:
            o = exchange.create_order(
                symbol, 'limit', 'buy', qty, price,
                params={'timeInForce': 'GTX'}
            )
        except Exception as e:
            return "FAIL", (f"create_order failed: {str(e)[:120]} "
                            f"(qty={qty} price={price} "
                            f"notional={actual_notional:.2f})")

        state['order'] = o
        state['id'] = o['id']
        state['symbol'] = symbol
        CLEANUP_ACTIONS.append(
            lambda: _cancel_order_robust(exchange, state['id'], symbol)
        )
        return "PASS", (f"id={o['id']} @ {price} qty={qty} "
                        f"notional=${actual_notional:.2f}")
    return run'''


T3_ANCHOR = '''def test_scan_tickers(exchange, symbol):
    def run():
        tickers = exchange.fetch_tickers()
        n = len(tickers)
        usdt = sum(1 for s in tickers if s.endswith('/USDT'))
        return "PASS", f"total={n} usdt_pairs={usdt}"
    return run'''

T3_CONTENT = '''def test_scan_tickers(exchange, symbol):
    def run():
        tickers = exchange.fetch_tickers()
        n = len(tickers)
        usdt_spot = sum(1 for s in tickers if s.endswith('/USDT'))
        usdt_fut = sum(1 for s in tickers
                       if '/USDT:' in s and s.split(':')[1] == 'USDT')
        return "PASS", (f"total={n} spot_usdt={usdt_spot} "
                        f"fut_usdt={usdt_fut}")
    return run'''


TEST_FIXES: List[Fix] = [
    Fix(name="T1_leverage_tiers",
        kind="replace",
        anchor=T1_ANCHOR,
        content=T1_CONTENT,
        idempotency="def _sym_match(a, b):",
        description="Handle dict-shape leverage tiers"),

    Fix(name="T2_limit_gtx_min_notional",
        kind="replace",
        anchor=T2_ANCHOR,
        content=T2_CONTENT,
        idempotency="# MIN_NOTIONAL from exchange filters",
        description="Respect actual MIN_NOTIONAL"),

    Fix(name="T3_scan_tickers_futures",
        kind="replace",
        anchor=T3_ANCHOR,
        content=T3_CONTENT,
        idempotency="usdt_fut = sum(1 for s in tickers",
        description="Detect futures USDT pairs"),
]


# ═══════════════════════════════════════════════════════════════════
# ══ BOT FILE FIXES ══
# ═══════════════════════════════════════════════════════════════════

B1_ANCHOR = '''                _TICK_SIZE_CACHE[symbol] = ts
                return ts
        except Exception:
            pass
    return None'''

B1_CONTENT = '''                _TICK_SIZE_CACHE[symbol] = ts
                return ts
        except Exception:
            pass
    return None


# ══ [MIN_NOTIONAL CACHE] ══
_MIN_NOTIONAL_CACHE: Dict[str, float] = {}


def _get_min_notional(exchange, symbol: str) -> float:
    """
    Returns the actual minimum notional from exchange filters.
    Falls back to CFG.MIN_NOTIONAL if all filters fail.
    """
    if symbol in _MIN_NOTIONAL_CACHE:
        return _MIN_NOTIONAL_CACHE[symbol]

    _min_notional = float(getattr(CFG, 'MIN_NOTIONAL', 5.0))
    try:
        m = exchange.market(symbol)
        if m:
            info = m.get('info') or {}
            for f in (info.get('filters') or []):
                if isinstance(f, dict) and f.get('filterType') == 'MIN_NOTIONAL':
                    try:
                        v = float(f.get('notional', 0))
                        if v > 0:
                            _min_notional = v
                            break
                    except Exception:
                        pass
            cost_min = ((m.get('limits') or {}).get('cost') or {}).get('min')
            if cost_min and float(cost_min) > _min_notional:
                _min_notional = float(cost_min)
    except Exception:
        pass

    _MIN_NOTIONAL_CACHE[symbol] = _min_notional
    return _min_notional'''


B2_ANCHOR = '''    # ══ Log القرار ══
    log.debug(f"[Pending] {sym} base={'tunnel' if explicit_target is None else 'watch'} "'''

B2_CONTENT = '''    # ══ [MIN-NOTIONAL CHECK] قبل إرسال الأمر ══
    _min_notional_actual = _get_min_notional(exchange, sym)
    _notional_est = float(qty) * float(target)
    if _notional_est < _min_notional_actual * 1.05:
        log.warning(
            f"[Pending] {sym} notional ${_notional_est:.2f} < "
            f"min ${_min_notional_actual:.2f} (x1.05 buffer) -- "
            f"refusing order"
        )
        return None

    # ══ Log القرار ══
    log.debug(f"[Pending] {sym} base={'tunnel' if explicit_target is None else 'watch'} "'''


B3_ANCHOR = '''                    if qty * lmt < cfg.MIN_NOTIONAL:
                        continue'''

B3_CONTENT = '''                    _min_notional_live = _get_min_notional(exchange, sym)
                    if qty * lmt < _min_notional_live * 1.05:
                        log.debug(
                            f"[Notional] {sym} too small: "
                            f"${qty*lmt:.2f} < ${_min_notional_live:.2f}"
                        )
                        continue'''


B4_ANCHOR = '''    # ══ [PRE-FLIGHT GATE] ══
    # Before calling _place_protective_orders, verify that the SL is
    # placeable. If not, skip entirely — leave whatever exists on the
    # exchange untouched instead of starting a cancel-then-fail cycle.
    _close_side = 'sell' if pos.get('action') == 'BUY' else 'buy'
    _pf_ok, _pf_reason = _lv_preflight_check(
        exchange, sym, _close_side,
        float(pos.get('sl') or 0.0), float(pos.get('qty') or 0.0)
    )'''

B4_CONTENT = '''    # ══ [SAFETY] تحقق من وجود المركز على البورصة قبل وضع أوامر حماية ══
    # testnet وبعض البيئات قد لا تفرض reduceOnly. نحمي أنفسنا.
    try:
        _pos_map = _lv_fetch_positions(exchange, [sym])
        if _pos_map is None:
            log.debug(f"[Prot] {sym} position check failed -- proceeding")
        elif sym not in _pos_map:
            log.warning(
                f"[Prot] {sym} no exchange position -- "
                f"skipping protective placement"
            )
            return
    except Exception as _e_pos:
        log.debug(f"[Prot] {sym} pre-check error: {_e_pos}")

    # ══ [PRE-FLIGHT GATE] ══
    # Before calling _place_protective_orders, verify that the SL is
    # placeable. If not, skip entirely — leave whatever exists on the
    # exchange untouched instead of starting a cancel-then-fail cycle.
    _close_side = 'sell' if pos.get('action') == 'BUY' else 'buy'
    _pf_ok, _pf_reason = _lv_preflight_check(
        exchange, sym, _close_side,
        float(pos.get('sl') or 0.0), float(pos.get('qty') or 0.0)
    )'''


B5_ANCHOR = '''    # ── 4. Notional check ──
    try:
        _min_notional = float(_get_min_notional(exchange, sym)) \\
            if '_get_min_notional' in globals() else 5.0
    except Exception:
        _min_notional = 5.0'''

B5_CONTENT = '''    # ── 4. Notional check ──
    try:
        _min_notional = float(_get_min_notional(exchange, sym))
    except Exception:
        _min_notional = float(getattr(CFG, 'MIN_NOTIONAL', 5.0))'''


BOT_FIXES: List[Fix] = [
    Fix(name="B1_add_get_min_notional",
        kind="replace",
        anchor=B1_ANCHOR,
        content=B1_CONTENT,
        idempotency="def _get_min_notional(exchange, symbol: str) -> float:",
        description="Add _get_min_notional + cache"),

    Fix(name="B2_pending_precheck",
        kind="replace",
        anchor=B2_ANCHOR,
        content=B2_CONTENT,
        idempotency="# ══ [MIN-NOTIONAL CHECK] قبل إرسال الأمر ══",
        description="Pre-check MIN_NOTIONAL in place_pending_entry"),

    Fix(name="B3_run_live_notional",
        kind="replace",
        anchor=B3_ANCHOR,
        content=B3_CONTENT,
        idempotency="_min_notional_live = _get_min_notional(exchange, sym)",
        description="Dynamic MIN_NOTIONAL in run_live"),

    Fix(name="B4_prot_position_check",
        kind="replace",
        anchor=B4_ANCHOR,
        content=B4_CONTENT,
        idempotency="# ══ [SAFETY] تحقق من وجود المركز على البورصة قبل وضع أوامر حماية ══",
        description="Position check before protective placement"),

    Fix(name="B5_preflight_direct_call",
        kind="replace",
        anchor=B5_ANCHOR,
        content=B5_CONTENT,
        idempotency="        _min_notional = float(_get_min_notional(exchange, sym))\n    except Exception:",
        description="Clean up globals() guard in _lv_preflight_check",
        required=False),   # اختياري
]


# ═══════════════════════════════════════════════════════════════════
# Engine
# ═══════════════════════════════════════════════════════════════════

def apply_fix(source: str, fix: Fix, le: str) -> Tuple[str, str]:
    if fix.idempotency and fix.idempotency in source:
        return source, "SKIP (already applied)"

    anchor = normalize(fix.anchor, le)
    content = normalize(fix.content, le)

    cnt = source.count(anchor)
    if cnt == 0:
        return source, "ERROR: anchor not found"
    if cnt > 1:
        return source, f"ERROR: anchor appears {cnt} times"

    if fix.kind == "replace":
        return source.replace(anchor, content, 1), "OK"
    if fix.kind == "insert_before":
        return source.replace(anchor, content + anchor, 1), "OK"
    if fix.kind == "insert_after":
        return source.replace(anchor, anchor + content, 1), "OK"
    return source, f"ERROR: unknown kind {fix.kind}"


def process_file(path: str, fixes: List[Fix],
                 dry_run: bool = False) -> int:
    if not os.path.exists(path):
        log(f"File not found: {path}", level="ERROR")
        return 1

    source, le = read_source(path)
    log(f"Processing {path} ({len(source)} chars)")

    if dry_run:
        current = source
        for fix in fixes:
            _, status = apply_fix(current, fix, le)
            icon = "OK  " if status == "OK" else (
                "SKIP" if status.startswith("SKIP") else "FAIL")
            print(f"  [{icon}] {fix.name:35s} -- {status}")
            if status == "OK":
                current, _ = apply_fix(current, fix, le)
        return 0

    backup = make_backup(path)
    current = source
    results: List[Tuple[Fix, str]] = []
    hard_failure = False

    for fix in fixes:
        new_src, status = apply_fix(current, fix, le)
        results.append((fix, status))
        if status == "OK":
            current = new_src
            log(f"  [OK  ] {fix.name:35s} -- applied")
        elif status.startswith("SKIP"):
            log(f"  [SKIP] {fix.name:35s} -- {status}")
        else:
            _lvl = "ERROR" if fix.required else "WARN"
            _tag = "REQUIRED" if fix.required else "OPTIONAL"
            log(f"  [FAIL] {fix.name:35s} -- {status} [{_tag}]",
                level=_lvl)
            if fix.required:
                hard_failure = True

    if hard_failure:
        log(f"Rolling back {path} (required fix failed)", level="ERROR")
        return 2

    # Syntax check
    try:
        compile(current, path, "exec")
        log(f"  Syntax check: OK")
    except SyntaxError as e:
        log(f"  Syntax error after patching: {e}", level="ERROR")
        log(f"  Backup preserved at {backup}", level="ERROR")
        return 4

    write_source(path, current)
    n_ok = sum(1 for _, s in results if s == "OK")
    n_skip = sum(1 for _, s in results if s.startswith("SKIP"))
    log(f"  Applied={n_ok} Skipped={n_skip}")
    return 0


def cmd_verify(path: str, fixes: List[Fix]) -> int:
    if not os.path.exists(path):
        log(f"File not found: {path}", level="ERROR")
        return 1
    source, _ = read_source(path)
    print(f"\n  {path}")
    missing = 0
    for fix in fixes:
        if fix.idempotency and fix.idempotency in source:
            print(f"    [OK  ] {fix.name}")
        else:
            print(f"    [MISS] {fix.name}")
            missing += 1
    return missing


def cmd_rollback(path: str) -> int:
    backup = latest_backup(path)
    if not backup:
        log(f"No backup found for {path}", level="ERROR")
        return 1
    shutil.copy2(backup, path)
    log(f"Restored {path} from {backup}")
    return 0


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main() -> int:
    p = argparse.ArgumentParser(
        description="Final Fixes Patcher (test + bot)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--file", choices=["test", "bot", "both"],
                   default="both")
    args = p.parse_args()

    targets: List[Tuple[str, List[Fix]]] = []
    if args.file in ("test", "both"):
        targets.append((TEST_FILE, TEST_FIXES))
    if args.file in ("bot", "both"):
        targets.append((BOT_FILE, BOT_FIXES))

    if args.rollback:
        rc = 0
        for path, _ in targets:
            rc |= cmd_rollback(path)
        return rc

    if args.verify_only:
        missing_total = 0
        for path, fixes in targets:
            missing_total += cmd_verify(path, fixes)
        print()
        if missing_total == 0:
            log("All fixes present.")
            return 0
        log(f"{missing_total} fix(es) missing.", level="WARN")
        return 1

    if args.dry_run:
        for path, fixes in targets:
            log(f"[DRY-RUN] {path}")
            process_file(path, fixes, dry_run=True)
            print()
        return 0

    # Apply
    rc_total = 0
    for path, fixes in targets:
        log(f"═══ Applying to {path} ═══")
        rc = process_file(path, fixes)
        if rc != 0:
            rc_total = rc
        print()

    if rc_total == 0:
        log("All patches applied successfully.")
        print()
        log("Next steps:")
        log(f"  1. python apply_final_fixes.py --verify-only")
        log(f"  2. python test_exchange_comms.py --mode testnet \\")
        log(f"       --api-key KEY --api-secret SECRET")
        log(f"  3. python trading_live_v2.py --help   (syntax check)")
    return rc_total


if __name__ == "__main__":
    sys.exit(main())
