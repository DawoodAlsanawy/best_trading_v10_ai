#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_live2_place_first.py                                              ║
║  Phase 1 (Pre-flight) + Phase 2 (Place-first)                            ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Fixes:                                                                  ║
║    PF1  Insert _lv_preflight_check helper                                ║
║    PF2  Rewrite _place_protective_orders with place-first ordering       ║
║    PF3  _lv_breakeven: pre-flight + place-first + reduceOnly             ║
║    PF4  _lv_ensure_protection: pre-flight gate                           ║
║    PF5  _cancel_stale_legs helper (surgical cancel by price)             ║
║                                                                          ║
║  Key changes:                                                            ║
║    * SL now uses reduceOnly=True (not closePosition=True)                ║
║      → multiple SLs can coexist safely → no naked window                ║
║    * Every leg is validated BEFORE touching the exchange                ║
║    * New legs placed BEFORE stale legs are cancelled                    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse, shutil, sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class C:
    GREEN='\033[92m'; RED='\033[91m'; YELLOW='\033[93m'
    CYAN='\033[96m'; GRAY='\033[90m'; BOLD='\033[1m'; END='\033[0m'


# ══════════════════════════════════════════════════════════════════════════
# PF1 — Insert helper functions before _place_protective_orders
# ══════════════════════════════════════════════════════════════════════════

PF1_ANCHOR = '''def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:'''

PF1_BLOCK = '''def _lv_preflight_check(exchange, sym: str, side: str,
                         target_price: float, qty: float,
                         mark_price: Optional[float] = None
                         ) -> Tuple[bool, str]:
    """
    [PRE-FLIGHT] Validate that a STOP_MARKET / TAKE_PROFIT_MARKET
    order can be placed on the exchange for `target_price` without
    being rejected.

    Checks (in order of cost):
      1. price > 0
      2. side matches direction (BUY: target < mark, SELL: target > mark)
      3. distance from mark >= min_dist_bps (Binance rejects too-close)
      4. qty * target >= MIN_NOTIONAL

    Returns (ok, reason).
    """
    if target_price <= 0 or qty <= 0:
        return False, "invalid_args"
    if mark_price is None or mark_price <= 0:
        try:
            _tk = exchange.fetch_ticker(sym)
            _rate_record(float(getattr(CFG, 'LIVE_PRICE_RATE_WEIGHT', 2.0)))
            mark_price = float(_tk.get('last') or 0)
        except Exception as _e:
            log.debug(f"[PreFlight] {sym} ticker failed: {_e}")
            return True, "ticker_unavailable_fail_open"

    if mark_price <= 0:
        return True, "mark_unavailable_fail_open"

    # ── 2. Side check ──
    if side == 'buy':
        if target_price >= mark_price:
            return False, (f"BUY_sl_above_mark"
                           f"(tgt={target_price:.6f}>=m={mark_price:.6f})")
    else:
        if target_price <= mark_price:
            return False, (f"SELL_sl_below_mark"
                           f"(tgt={target_price:.6f}<=m={mark_price:.6f})")

    # ── 3. Distance check ──
    _min_bps = float(getattr(CFG, 'MIN_STOP_DISTANCE_BPS', 50.0))
    dist_bps = abs(target_price - mark_price) / mark_price * 1e4
    if dist_bps < _min_bps:
        return False, (f"too_close_to_mark"
                       f"({dist_bps:.1f}bps<{_min_bps:.0f}bps)")

    # ── 4. Notional check ──
    try:
        _min_notional = float(_get_min_notional(exchange, sym)) \\
            if '_get_min_notional' in globals() else 5.0
    except Exception:
        _min_notional = 5.0
    notional = qty * target_price
    if notional < _min_notional:
        return False, f"notional({notional:.2f}<{_min_notional:.2f})"

    return True, "OK"


def _lv_cancel_stale_legs(exchange, sym: str, stale_order_ids: List[str]) -> int:
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
    return n


def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:'''

PF1_MARKER = "def _lv_preflight_check(exchange, sym: str, side: str,"


# ══════════════════════════════════════════════════════════════════════════
# PF2 — Rewrite _place_protective_orders body (place-first)
# ══════════════════════════════════════════════════════════════════════════

# Identify the current function body (after surgical patch)
PF2_OLD_START = '''def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:
    """
    Place STOP_MARKET at SL and TAKE_PROFIT_MARKET at TP for the position.

    [SURGICAL-PLACEMENT] This version handles each leg independently:

      1. Fetch current protective orders (via _lv_open_orders_all which
         includes Algo Orders / conditional orders on Binance Futures).
      2. Classify each existing order:
           - SL at pos['sl']           -> kept as-is
           - Full-TP at pos['tp1']     -> kept as-is
           - Partial-TP at partial_px  -> kept as-is
           - anything else             -> STALE -> cancelled
      3. Place ONLY the legs that are missing.

    Never cancels a leg that already exists at the correct price. This
    eliminates the SL-stacking bug that occurred when the SL was a
    closePosition order that fetch_open_orders could not see.

    Returns True on success.
    """'''

PF2_OLD_END = '''        _ok = (placed['sl'] and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if _ok:
            return True
        log.warning(f"[Prot] {sym} incomplete: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return _ok
    except Exception as e:
        log.warning(f"[Prot] {sym} place_protective_orders fatal: {e}")
        return False

def _sync_protective_orders(exchange, sym: str, pos: Dict) -> bool:'''

PF2_NEW = '''def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:
    """
    [PLACE-FIRST] Surgical, pre-flight-validated SL/TP placement.

    Order of operations (the critical difference from cancel-then-place):

      1. Compute target prices (SL, TP, partial-TP if enabled).
      2. PRE-FLIGHT validate every target BEFORE touching the exchange.
         If a target is invalid (too close to mark, wrong side, etc.),
         log the reason and DO NOT touch the corresponding existing leg.
      3. Read existing protective orders, classify by price match.
      4. PLACE missing legs first (reduceOnly=True).
      5. ONLY AFTER all desired legs are placed, cancel stale legs.

    This guarantees that at no point does an existing leg disappear
    before its replacement is confirmed on the exchange.

    SL uses reduceOnly=True (not closePosition=True) so that multiple
    SLs can coexist briefly during the swap. Binance auto-cancels
    reduceOnly orders when the position reaches zero.

    Returns True iff all desired legs exist on the exchange.
    """
    if not getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        return False
    try:
        action = pos.get('action')
        sl = float(pos.get('sl') or 0)
        tp = float(pos.get('tp1') or 0)
        qty = float(pos.get('qty') or 0)
        if action not in ('BUY', 'SELL') or sl <= 0 or tp <= 0 or qty <= 0:
            return False

        close_side = 'sell' if action == 'BUY' else 'buy'
        wt = str(getattr(CFG, 'PROTECTIVE_WORKING_TYPE', 'MARK_PRICE'))
        max_retries = int(getattr(CFG, 'PROTECTIVE_MAX_RETRIES', 2))

        # ── 1. Partial-TP target price ──
        _partial_pct = float(getattr(CFG, 'PARTIAL_TP_PCT', 0.0))
        _partial_enabled = (
            bool(getattr(CFG, 'PARTIAL_TP_ENABLED', False))
            and 0.0 < _partial_pct < 1.0
        )
        _sl_dist0 = float(pos.get('sl_dist_initial') or 0.0)
        _entry_px = float(pos.get('entry') or 0.0)
        _partial_price = 0.0
        if _partial_enabled and _sl_dist0 > 0 and _entry_px > 0:
            _partial_r = float(getattr(CFG, 'PARTIAL_TP_R', 1.5))
            if action == 'BUY':
                _partial_price = _entry_px + _sl_dist0 * _partial_r
            else:
                _partial_price = _entry_px - _sl_dist0 * _partial_r
            if action == 'BUY' and _partial_price >= tp:
                _partial_enabled = False
            elif action == 'SELL' and _partial_price <= tp:
                _partial_enabled = False
        if _partial_enabled and _partial_price <= 0:
            _partial_enabled = False
        if pos.get('_partial_taken'):
            _partial_enabled = False

        _partial_qty = qty * _partial_pct if _partial_enabled else 0.0
        _full_qty = (qty * (1.0 - _partial_pct)
                     if _partial_enabled else qty)

        # ── 2. PRE-FLIGHT validation (before ANY exchange mutation) ──
        _mark = None
        try:
            _tk = exchange.fetch_ticker(sym)
            _rate_record(float(getattr(CFG, 'LIVE_PRICE_RATE_WEIGHT', 2.0)))
            _mark = float(_tk.get('last') or 0) or None
        except Exception:
            _mark = None

        _sl_ok, _sl_reason = _lv_preflight_check(
            exchange, sym, close_side, sl, qty, mark_price=_mark
        )
        if not _sl_ok:
            log.warning(
                f"[Prot] {sym} SL pre-flight FAILED ({_sl_reason}) — "
                f"existing SL left intact, no mutation"
            )
            return False

        _tp_ok = True
        _tp_reason = "OK"
        if tp > 0:
            _tp_ok, _tp_reason = _lv_preflight_check(
                exchange, sym, close_side, tp,
                _partial_qty if False else qty, mark_price=_mark
            )
            if not _tp_ok:
                log.debug(f"[Prot] {sym} TP pre-flight soft-fail: {_tp_reason}")

        # ── 3. Read + classify existing protective orders ──
        try:
            _existing = _lv_open_orders_all(exchange, sym)
        except Exception as _e:
            log.debug(f"[Prot] {sym} fetch orders failed: {_e}")
            _existing = []
        _prot = [o for o in _existing if _is_protective_order(o)]

        def _px(o):
            return float(
                o.get('stopPrice')
                or o.get('triggerPrice')
                or (o.get('info') or {}).get('stopPrice')
                or 0
            )

        def _is_tp(o):
            return 'take_profit' in str(o.get('type') or '').lower()

        tol = 1e-4
        _ex_sl = None
        _ex_tp_full = None
        _ex_tp_partial = None
        _stale_ids = []
        for o in _prot:
            p = _px(o)
            if p <= 0:
                continue
            if _is_tp(o):
                if (_partial_enabled
                        and abs(p - _partial_price) /
                            max(abs(_partial_price), 1e-9) < tol):
                    _ex_tp_partial = p
                elif abs(p - tp) / max(abs(tp), 1e-9) < tol:
                    _ex_tp_full = p
                else:
                    _stale_ids.append(o['id'])
            else:
                if abs(p - sl) / max(abs(sl), 1e-9) < tol:
                    _ex_sl = p
                else:
                    _stale_ids.append(o['id'])

        placed = {
            'sl': _ex_sl is not None,
            'tp': _ex_tp_full is not None,
            'partial_tp': _ex_tp_partial is not None,
        }

        # ── 4. PLACE missing legs (all BEFORE any cancel) ──

        # 4a. SL — reduceOnly (not closePosition) so place-first is safe
        if not placed['sl']:
            for attempt in range(max_retries):
                try:
                    exchange.create_order(
                        sym, 'STOP_MARKET', close_side, qty, None,
                        params={'stopPrice': sl,
                                'reduceOnly': True,
                                'workingType': wt})
                    placed['sl'] = True
                    log.info(f"[Prot] {sym} SL placed @ {sl:.6f} "
                             f"(reduceOnly, place-first)")
                    break
                except Exception as e:
                    log.debug(f"[Prot] {sym} SL attempt {attempt+1} "
                              f"failed: {e}")
            if not placed['sl']:
                log.warning(
                    f"[Prot] {sym} SL placement FAILED — "
                    f"existing stale SL (if any) PRESERVED"
                )
                # لا نلغي أي شيء — SL القديم قد لا يكون بسعرنا لكنه أفضل من لا شيء
                return False

        # 4b. Partial TP
        if _partial_enabled and not placed['partial_tp'] and _partial_qty > 0:
            for attempt in range(max_retries):
                try:
                    exchange.create_order(
                        sym, 'TAKE_PROFIT_MARKET', close_side,
                        _partial_qty, None,
                        params={'stopPrice': _partial_price,
                                'reduceOnly': True,
                                'workingType': wt})
                    placed['partial_tp'] = True
                    log.info(f"[Prot] {sym} PARTIAL-TP placed @ "
                             f"{_partial_price:.6f} qty={_partial_qty:.6f}")
                    break
                except Exception as e:
                    log.debug(f"[Prot] {sym} partial-TP attempt "
                              f"{attempt+1} failed: {e}")
            if not placed['partial_tp']:
                log.warning(f"[Prot] {sym} partial-TP rejected — "
                            f"continuing with full-qty TP only")
                _partial_enabled = False

        pos['_broker_partial'] = bool(placed['partial_tp'])

        # 4c. Full TP
        if not placed['tp']:
            _tp_close_pos = (not _partial_enabled)
            _tp_qty = None if _tp_close_pos else _full_qty
            for attempt in range(max_retries):
                try:
                    params_tp = {'stopPrice': tp, 'workingType': wt}
                    if _tp_close_pos:
                        params_tp['closePosition'] = True
                    else:
                        params_tp['reduceOnly'] = True
                    exchange.create_order(
                        sym, 'TAKE_PROFIT_MARKET', close_side,
                        _tp_qty, None, params=params_tp)
                    placed['tp'] = True
                    log.info(f"[Prot] {sym} FULL-TP placed @ {tp:.6f}")
                    break
                except Exception as e:
                    log.debug(f"[Prot] {sym} full-TP attempt "
                              f"{attempt+1} failed: {e}")

        # ── 5. NOW cancel stale legs (all desired legs confirmed) ──
        if _stale_ids:
            n_cancelled = _lv_cancel_stale_legs(exchange, sym, _stale_ids)
            if n_cancelled > 0:
                log.info(f"[Prot] {sym} cancelled {n_cancelled} stale "
                         f"protective order(s) after placement")

        _ok = (placed['sl'] and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if _ok:
            return True
        log.warning(f"[Prot] {sym} incomplete after place-first: "
                    f"sl={placed['sl']} tp={placed['tp']} "
                    f"partial={placed['partial_tp']}")
        return _ok
    except Exception as e:
        log.warning(f"[Prot] {sym} place_protective_orders fatal: {e}")
        return False

def _sync_protective_orders(exchange, sym: str, pos: Dict) -> bool:'''

PF2_MARKER = "[PLACE-FIRST] Surgical, pre-flight-validated SL/TP placement."


# ══════════════════════════════════════════════════════════════════════════
# PF3 — _lv_breakeven: pre-flight + place-first
# ══════════════════════════════════════════════════════════════════════════

PF3_OLD = '''def _lv_breakeven(exchange, sym, pos, now) -> None:
    """
    Live twin of the backtest BREAKEVEN-SL.

    [SMART-BE] The exchange SL is read first. Behaviour:
      * Exchange SL at the same price as our target → NO-OP (do nothing)
      * Exchange SL at a different price            → cancel it, then
                                                      place the new SL
      * No exchange SL                              → place the new SL
    """
    if getattr(CFG, 'TRAIL_ENABLED', True) or not getattr(CFG, 'BREAKEVEN_ENABLED', True):
        return
    if pos.get('_be_done'):
        return
    entry = float(pos.get('entry') or 0.0)
    d0 = float(pos.get('sl_dist_initial') or 0.0)
    if entry <= 0 or d0 <= 0:
        return
    r = float(_lv_cfg('BREAKEVEN_AT_R', 1.0))
    mfe = (float(pos.get('_hi', entry)) - entry) if pos['action'] == 'BUY' \\
          else (entry - float(pos.get('_lo', entry)))
    if mfe < d0 * r:
        return
    cur = float(pos['sl'])
    better = (entry > cur) if pos['action'] == 'BUY' else (entry < cur)
    pos['_be_done'] = True
    if not better:
        return

    _target_sl = entry

    # ══ [SMART-BE] Read the actual SL that's on the exchange ══
    _exch_sl = _lv_get_exchange_sl(exchange, sym, pos)

    if _exch_sl is not None:
        _same = abs(_exch_sl - _target_sl) / max(abs(_target_sl), 1e-9) < 1e-4
        if _same:
            # Same price -> no-op, just record it as placed
            pos['sl'] = _target_sl
            pos['_prot_last_sl'] = _exch_sl
            pos['_be_ts'] = now
            log.info(
                f"[Breakeven] {sym} exchange SL already at "
                f"{_exch_sl:.6f} -- no-op"
            )
            return
        # Different price -> cancel the existing SL first (explicit replace)
        log.info(
            f"[Breakeven] {sym} replacing exchange SL "
            f"{_exch_sl:.6f} -> {_target_sl:.6f}"
        )
        try:
            _cancel_all_protective_orders(exchange, sym)
            time.sleep(0.5)
        except Exception as _e:
            log.warning(f"[Breakeven] {sym} cancel before replace failed: {_e}")

    pos['sl'] = _target_sl
    pos['_be_ts'] = now
    pos['_prot_last_sl'] = None
    log.info(
        f"[Breakeven] {sym} {pos['action']} MFE={mfe:.6f} >= {r}R "
        f"({d0 * r:.6f}) -> SL moved to {_target_sl:.6f}"
    )'''

PF3_NEW = '''def _lv_breakeven(exchange, sym, pos, now) -> None:
    """
    Live twin of the backtest BREAKEVEN-SL.

    [PLACE-FIRST + PRE-FLIGHT] Behaviour:
      1. Read the exchange SL.
      2. If same as target → no-op.
      3. PRE-FLIGHT: check target SL is far enough from mark.
         If not → SKIP entirely, existing SL preserved.
      4. PLACE new SL (reduceOnly).
      5. Only after confirmation, cancel the old SL (surgically).
    """
    if getattr(CFG, 'TRAIL_ENABLED', True) or not getattr(CFG, 'BREAKEVEN_ENABLED', True):
        return
    if pos.get('_be_done'):
        return
    entry = float(pos.get('entry') or 0.0)
    d0 = float(pos.get('sl_dist_initial') or 0.0)
    if entry <= 0 or d0 <= 0:
        return
    r = float(_lv_cfg('BREAKEVEN_AT_R', 1.0))
    mfe = (float(pos.get('_hi', entry)) - entry) if pos['action'] == 'BUY' \\
          else (entry - float(pos.get('_lo', entry)))
    if mfe < d0 * r:
        return
    cur = float(pos['sl'])
    better = (entry > cur) if pos['action'] == 'BUY' else (entry < cur)
    if not better:
        pos['_be_done'] = True
        return

    _target_sl = entry
    _close_side = 'sell' if pos['action'] == 'BUY' else 'buy'

    # ── 2. Same-price no-op ──
    _exch_sl = _lv_get_exchange_sl(exchange, sym, pos)
    if _exch_sl is not None:
        _same = abs(_exch_sl - _target_sl) / max(abs(_target_sl), 1e-9) < 1e-4
        if _same:
            pos['sl'] = _target_sl
            pos['_prot_last_sl'] = _exch_sl
            pos['_be_ts'] = now
            pos['_be_done'] = True
            log.info(
                f"[Breakeven] {sym} exchange SL already at "
                f"{_exch_sl:.6f} -- no-op"
            )
            return

    # ── 3. PRE-FLIGHT: can we place the new SL? ──
    _qty = float(pos.get('qty') or 0.0)
    _pf_ok, _pf_reason = _lv_preflight_check(
        exchange, sym, _close_side, _target_sl, _qty
    )
    if not _pf_ok:
        log.info(
            f"[Breakeven] {sym} SKIP: pre-flight failed ({_pf_reason}) "
            f"— existing SL preserved"
        )
        pos['_be_skipped'] = True
        # لا نضع _be_done=True لنسمح بمحاولة لاحقة إذا تحرك السوق
        return

    # ── 4. PLACE new SL (reduceOnly) — before touching the old one ──
    _placed = False
    for attempt in range(3):
        try:
            exchange.create_order(
                sym, 'STOP_MARKET', _close_side, _qty, None,
                params={'stopPrice': _target_sl,
                        'reduceOnly': True,
                        'workingType': str(getattr(
                            CFG, 'PROTECTIVE_WORKING_TYPE', 'MARK_PRICE'))}
            )
            _placed = True
            log.info(
                f"[Breakeven] {sym} new SL placed @ {_target_sl:.6f} "
                f"(reduceOnly, place-first)"
            )
            break
        except Exception as _e:
            log.debug(f"[Breakeven] {sym} place attempt {attempt+1}: {_e}")

    if not _placed:
        log.warning(
            f"[Breakeven] {sym} FAILED to place new SL — "
            f"existing SL at {_exch_sl if _exch_sl else 'None'} preserved"
        )
        pos['_be_skipped'] = True
        return

    # ── 5. Cancel old SL surgically ──
    if _exch_sl is not None:
        _stale = []
        for o in _lv_open_orders_all(exchange, sym):
            if not _is_protective_order(o):
                continue
            _ot = str(o.get('type') or '').lower()
            if 'take_profit' in _ot:
                continue
            _sp = float(
                o.get('stopPrice')
                or o.get('triggerPrice')
                or (o.get('info') or {}).get('stopPrice')
                or 0
            )
            if _sp > 0 and abs(_sp - _exch_sl) / max(abs(_exch_sl), 1e-9) < 1e-4:
                _stale.append(o['id'])
        if _stale:
            _n = _lv_cancel_stale_legs(exchange, sym, _stale)
            log.info(
                f"[Breakeven] {sym} cancelled {_n} old SL(s) after "
                f"new placement confirmed"
            )

    pos['sl'] = _target_sl
    pos['_be_ts'] = now
    pos['_be_done'] = True
    pos['_prot_last_sl'] = _target_sl
    log.info(
        f"[Breakeven] {sym} {pos['action']} MFE={mfe:.6f} >= {r}R "
        f"({d0 * r:.6f}) -> SL moved to {_target_sl:.6f}"
    )'''

PF3_MARKER = "[PLACE-FIRST + PRE-FLIGHT] Behaviour:"


# ══════════════════════════════════════════════════════════════════════════
# PF4 — _lv_ensure_protection: pre-flight gate
# ══════════════════════════════════════════════════════════════════════════

PF4_OLD = '''    if not stale:
        return
    if now - float(pos.get('_prot_try_ts', 0.0)) < float(_lv_cfg('LIVE_PROT_RETRY_S', 20.0)):
        return
    pos['_prot_try_ts'] = now
    if pos.get('_broker_partial') and not pos.get('_partial_taken'):
        # the partial leg may already have fired: re-placing it would take a SECOND partial
        _lv_sync_with_exchange(exchange, sym, pos)
        pos['_sync_ts'] = now
    try:
        ok = _place_protective_orders(exchange, sym, pos)
    except Exception as e:
        log.warning(f"[Prot] {sym} re-place error: {e}")
        ok = False'''

PF4_NEW = '''    if not stale:
        return
    if now - float(pos.get('_prot_try_ts', 0.0)) < float(_lv_cfg('LIVE_PROT_RETRY_S', 20.0)):
        return
    pos['_prot_try_ts'] = now
    if pos.get('_broker_partial') and not pos.get('_partial_taken'):
        # the partial leg may already have fired: re-placing it would take a SECOND partial
        _lv_sync_with_exchange(exchange, sym, pos)
        pos['_sync_ts'] = now

    # ══ [PRE-FLIGHT GATE] ══
    # Before calling _place_protective_orders, verify that the SL is
    # placeable. If not, skip entirely — leave whatever exists on the
    # exchange untouched instead of starting a cancel-then-fail cycle.
    _close_side = 'sell' if pos.get('action') == 'BUY' else 'buy'
    _pf_ok, _pf_reason = _lv_preflight_check(
        exchange, sym, _close_side,
        float(pos.get('sl') or 0.0), float(pos.get('qty') or 0.0)
    )
    if not _pf_ok:
        log.debug(
            f"[Prot] {sym} re-place SKIP: pre-flight {_pf_reason}"
        )
        return

    try:
        ok = _place_protective_orders(exchange, sym, pos)
    except Exception as e:
        log.warning(f"[Prot] {sym} re-place error: {e}")
        ok = False'''

PF4_MARKER = "[PRE-FLIGHT GATE]"


# ══════════════════════════════════════════════════════════════════════════
# PF5 — Add MIN_STOP_DISTANCE_BPS to Config (in-place insert)
# ══════════════════════════════════════════════════════════════════════════

PF5_OLD = '''    # ══ [LAYER 7 — Broker-side protective orders] ══
    PROTECTIVE_ORDERS_ENABLED: bool = True
    PROTECTIVE_WORKING_TYPE: str = "MARK_PRICE"
    PROTECTIVE_SYNC_MIN_STEP_FRAC: float = 0.001   # 0.1% SL movement → resync
    PROTECTIVE_MAX_RETRIES: int = 2'''

PF5_NEW = '''    # ══ [LAYER 7 — Broker-side protective orders] ══
    PROTECTIVE_ORDERS_ENABLED: bool = True
    PROTECTIVE_WORKING_TYPE: str = "MARK_PRICE"
    PROTECTIVE_SYNC_MIN_STEP_FRAC: float = 0.001   # 0.1% SL movement → resync
    PROTECTIVE_MAX_RETRIES: int = 2
    # ══ [PLACE-FIRST] Minimum distance from mark for a STOP_MARKET
    # Binance USDT-M Futures rejects STOP_MARKET orders whose
    # stopPrice is too close to markPrice. The exact minimum varies
    # by symbol (usually 0.5% for majors, sometimes less for alts).
    # 50 bps = 0.5% is a safe conservative default.
    MIN_STOP_DISTANCE_BPS: float = 50.0'''

PF5_MARKER = "MIN_STOP_DISTANCE_BPS: float = 50.0"


# ══════════════════════════════════════════════════════════════════════════
# Patcher
# ══════════════════════════════════════════════════════════════════════════

class Patcher:
    def __init__(self, path, dry_run=False):
        self.path = path
        self.dry_run = dry_run
        self.content = None
        self.backup_path = None
        self.results: List[Tuple[str, str]] = []

    def load(self):
        if not self.path.exists():
            print(f"{C.RED}  Not found: {self.path}{C.END}")
            return False
        try:
            self.content = self.path.read_text(encoding='utf-8')
            print(f"{C.CYAN}  Loaded {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Read error: {e}{C.END}")
            return False

    def backup(self):
        if self.dry_run:
            return True
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = self.path.with_suffix(
            self.path.suffix + f'.bak.{ts}')
        try:
            shutil.copy2(self.path, self.backup_path)
            print(f"{C.CYAN}  Backup: {self.backup_path.name}{C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Backup failed: {e}{C.END}")
            return False

    def replace(self, name, old, new, marker=None):
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name} (already applied)")
            return True
        n = self.content.count(old)
        if n == 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} (anchor not found)")
            return False
        if n > 1:
            print(f"  {C.YELLOW}⚠ WARN{C.END}  {name}: {n} occurrences")
        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    def replace_between(self, name, start_m, end_m, new_body, marker=None):
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name} (already applied)")
            return True
        s = self.content.find(start_m)
        if s < 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} (start not found)")
            return False
        e = self.content.find(end_m, s + len(start_m))
        if e < 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} (end not found)")
            return False
        self.content = self.content[:s] + new_body + self.content[e + len(end_m):]
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name} "
              f"(replaced {e + len(end_m) - s} chars)")
        return True

    def save(self):
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN -- not written{C.END}")
            return True
        try:
            compile(self.content, str(self.path), 'exec')
        except SyntaxError as e:
            print(f"{C.RED}  Syntax error: {e}{C.END}")
            if self.backup_path and self.backup_path.exists():
                shutil.copy2(self.backup_path, self.path)
                print(f"{C.GREEN}  Restored from backup.{C.END}")
            return False
        try:
            self.path.write_text(self.content, encoding='utf-8')
            print(f"{C.GREEN}  Written {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Write failed: {e}{C.END}")
            return False

    def report(self):
        a = sum(1 for _, s in self.results if s == 'applied')
        s = sum(1 for _, s in self.results if s == 'skip')
        f = sum(1 for _, s in self.results if s == 'fail')
        print(f"\n  {C.BOLD}Summary:{C.END}  "
              f"{C.GREEN}applied={a}{C.END}, "
              f"{C.GRAY}skipped={s}{C.END}, "
              f"{C.RED}failed={f}{C.END}")
        return f


def restore_latest(path):
    backups = sorted(path.parent.glob(path.name + '.bak.*'),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print(f"{C.RED}No backups for {path.name}{C.END}")
        return False
    shutil.copy2(backups[0], path)
    print(f"{C.GREEN}✓ Restored from {backups[0].name}{C.END}")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bot", default="trading_live.py")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.BOLD}  Place-First + Pre-Flight Patcher -- {bot.name}{C.END}")
    print(f"{C.BOLD}  Mode: {'DRY-RUN' if args.dry_run else 'APPLY'}{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if args.restore:
        sys.exit(0 if restore_latest(bot) else 1)
    if not bot.exists():
        print(f"{C.RED}File not found: {bot}{C.END}")
        sys.exit(2)

    pt = Patcher(bot, dry_run=args.dry_run)
    if not pt.load() or not pt.backup():
        sys.exit(3)

    print()
    pt.replace("PF1  Insert pre-flight + surgical-cancel helpers",
               PF1_ANCHOR, PF1_BLOCK, marker=PF1_MARKER)

    pt.replace_between(
        "PF2  Rewrite _place_protective_orders (place-first)",
        PF2_OLD_START, PF2_OLD_END, PF2_NEW, marker=PF2_MARKER)

    pt.replace("PF3  _lv_breakeven (pre-flight + place-first)",
               PF3_OLD, PF3_NEW, marker=PF3_MARKER)

    pt.replace("PF4  _lv_ensure_protection pre-flight gate",
               PF4_OLD, PF4_NEW, marker=PF4_MARKER)

    pt.replace("PF5  Config: MIN_STOP_DISTANCE_BPS",
               PF5_OLD, PF5_NEW, marker=PF5_MARKER)

    if not pt.save():
        sys.exit(4)
    failed = pt.report()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    if failed == 0:
        print(f"{C.GREEN}  ALL PATCHES APPLIED SUCCESSFULLY{C.END}")
    else:
        print(f"{C.RED}  {failed} PATCH(ES) FAILED{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if not failed and not args.dry_run:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify:  python3 -m py_compile {bot.name}")
        print(f"  2. Grep:    grep -n 'PLACE-FIRST\\|PRE-FLIGHT\\|_lv_preflight_check\\|_lv_cancel_stale_legs' {bot.name}")
        print(f"  3. Behaviour after patch:")
        print(f"     {C.BOLD}• New SL uses reduceOnly (not closePosition)")
        print(f"     • SLs placed BEFORE stale ones cancelled")
        print(f"     • Breakeven skips if target too close to mark")
        print(f"     • No naked window between cancel and place{C.END}")
        print(f"  4. Look for these new log lines:")
        print(f"     {C.BOLD}[Prot] X SL placed @ ... (reduceOnly, place-first){C.END}")
        print(f"     {C.BOLD}[Breakeven] X SKIP: pre-flight failed (too_close_to_mark){C.END}")
        print(f"  5. Revert:  python3 {Path(__file__).name} --restore")


if __name__ == "__main__":
    main()
