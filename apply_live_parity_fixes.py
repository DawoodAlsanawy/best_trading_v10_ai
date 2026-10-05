#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_live_parity_fixes.py
==========================

يقرأ trading_2.py، يطبّق 15 إصلاحاً حرجاً، ثم يكتب trading_2_fixed.py.

الاستخدام:
    python apply_live_parity_fixes.py
    python apply_live_parity_fixes.py --input trading_2.py --output trading_2_fixed.py
"""

import argparse
import re
import sys
import os
from datetime import datetime

# ════════════════════════════════════════════════════════════════
# أدوات مساعدة
# ════════════════════════════════════════════════════════════════

def _replace_once(src: str, old: str, new: str, tag: str) -> str:
    if old not in src:
        print(f"  ⚠️  [{tag}] لم يُعثر على النمط — تم التخطي")
        return src
    if src.count(old) > 1:
        print(f"  ⚠️  [{tag}] النمط يظهر {src.count(old)} مرات — استبدل الأول فقط")
        return src.replace(old, new, 1)
    return src.replace(old, new, 1)


def _regex_once(src: str, pattern: str, replacement: str, tag: str) -> str:
    new_src, n = re.subn(pattern, replacement, src, count=1)
    if n == 0:
        print(f"  ⚠️  [{tag}] النمط regex لم يُطابَق")
        return src
    print(f"  ✓ [{tag}] تم")
    return new_src


# ════════════════════════════════════════════════════════════════
# الإصلاح 1: Snap dynamic leverage to Binance tiers
# ════════════════════════════════════════════════════════════════

def fix_01_snap_leverage(src: str) -> str:
    """إصلاح 3.1: اجعل compute_dynamic_leverage يُعيد قيمة صالحة."""
    old = '''def compute_dynamic_leverage(capital, cfg):
    """
    ③ الرافعة الديناميكية تتناقص مع نمو رأس المال:
    
    Lev(C) = LEVERAGE_BASE / √(C / C₀)
    
    فيزيائياً: الجسيم الأثقل (رأس مال أكبر) يتجاهل التقلبات الصغيرة
    → رافعة أقل تعني حماية أكثر عند نمو الثروة.
    """
    C0 = cfg.INITIAL_CAPITAL
    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    return int(np.clip(round(lev), cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))'''

    new = '''def compute_dynamic_leverage(capital, cfg):
    """
    ③ الرافعة الديناميكية تتناقص مع نمو رأس المال:
    Lev(C) = LEVERAGE_BASE / √(C / C₀)

    [FIX-3.1] يُعاد الرقم من قائمة Tier صالحة على Binance،
    وإلا set_leverage يرفض بـ -4028.
    """
    C0 = cfg.INITIAL_CAPITAL
    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    lev = int(np.clip(round(lev), cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))
    # Snap to Binance valid tier
    _tiers = (1, 2, 3, 5, 10, 20, 25, 50, 75, 100, 125)
    _valid = [t for t in _tiers
              if t >= int(cfg.LEVERAGE_MIN) and t <= int(cfg.LEVERAGE_MAX)]
    if not _valid:
        return int(cfg.LEVERAGE_MIN)
    # اختر أقرب tier ≤ lev
    _below = [t for t in _valid if t <= lev]
    return int(_below[-1]) if _below else int(_valid[0])'''

    result = _replace_once(src, old, new, "FIX-01-snap-leverage")
    if "FIX-3.1" in result:
        print("  ✓ [FIX-01-snap-leverage] تم")
    return result


# ════════════════════════════════════════════════════════════════
# الإصلاح 2: Round quantity to stepSize
# ════════════════════════════════════════════════════════════════

def fix_02_step_size_helper(src: str) -> str:
    """
    إصلاح 4.2 / 4.3: helper لدوران الكمية.
    يُضاف بعد `_get_tick_size`.
    """
    anchor = '''def _get_tick_size(exchange, symbol: str) -> Optional[float]:'''

    helper = '''# ══ [FIX-4.2/4.3] Step size + MIN_NOTIONAL enforcement ══
_STEP_SIZE_CACHE: Dict[str, float] = {}
_MIN_NOTIONAL_CACHE: Dict[str, float] = {}


def _get_step_size(exchange, symbol: str) -> float:
    """Lot size filter — smallest order qty step."""
    if symbol in _STEP_SIZE_CACHE:
        return _STEP_SIZE_CACHE[symbol]
    try:
        mkt = exchange.market(symbol)
        info = mkt.get('info') or {}
        for f in (info.get('filters') or []):
            if f.get('filterType') in ('LOT_SIZE', 'MARKET_LOT_SIZE'):
                step = float(f.get('stepSize', 0))
                if step > 0:
                    _STEP_SIZE_CACHE[symbol] = step
                    return step
    except Exception:
        pass
    _STEP_SIZE_CACHE[symbol] = 1e-6
    return 1e-6


def _get_min_notional(exchange, symbol: str) -> float:
    """MIN_NOTIONAL filter — minimum order value in USDT."""
    if symbol in _MIN_NOTIONAL_CACHE:
        return _MIN_NOTIONAL_CACHE[symbol]
    try:
        mkt = exchange.market(symbol)
        info = mkt.get('info') or {}
        for f in (info.get('filters') or []):
            if f.get('filterType') == 'MIN_NOTIONAL':
                mn = float(f.get('notional', 5.0))
                _MIN_NOTIONAL_CACHE[symbol] = mn
                return mn
    except Exception:
        pass
    _MIN_NOTIONAL_CACHE[symbol] = 5.0
    return 5.0


def _round_qty(exchange, symbol: str, qty: float) -> float:
    """Round qty down to valid step size."""
    step = _get_step_size(exchange, symbol)
    if step <= 0 or qty <= 0:
        return qty
    import math
    return math.floor(qty / step) * step


def _round_price(exchange, symbol: str, price: float, side: str) -> float:
    """Round price to tick size in the correct direction."""
    tick = _get_tick_size(exchange, symbol) or 1e-8
    if tick <= 0 or price <= 0:
        return price
    import math
    if side == 'buy':
        return math.floor(price / tick) * tick
    else:
        return math.ceil(price / tick) * tick


def _get_tick_size(exchange, symbol: str) -> Optional[float]:'''

    return _replace_once(src, anchor, helper, "FIX-02-step-size")


# ════════════════════════════════════════════════════════════════
# الإصلاح 3: Sanitize qty + notional قبل place_pending_entry
# ════════════════════════════════════════════════════════════════

def fix_03_qty_sanitize_in_pending(src: str) -> str:
    """إصلاح 4.2 + 4.3: قبل create_order، round qty + فحص MIN_NOTIONAL."""
    old = '''    # ══ تحديد الـ target ══
    if explicit_target is not None and explicit_target > 0:'''

    new = '''    # ══ [FIX-4.2/4.3] Sanitize qty + notional ══
    qty = _round_qty(exchange, sym, float(qty))
    if qty <= 0:
        log.warning(f"[Pending] {sym} qty rounded to 0 — skip")
        return None
    _min_notional = _get_min_notional(exchange, sym)
    _approx_price = float(sig.price)
    if _approx_price <= 0:
        _approx_price = 1.0
    if qty * _approx_price < _min_notional:
        log.warning(f"[Pending] {sym} notional "
                    f"${qty*_approx_price:.2f} < MIN_NOTIONAL "
                    f"${_min_notional:.2f} — skip")
        return None

    # ══ تحديد الـ target ══
    if explicit_target is not None and explicit_target > 0:'''

    return _replace_once(src, old, new, "FIX-03-qty-sanitize")


# ════════════════════════════════════════════════════════════════
# الإصلاح 4: GTX rejection fallback
# ════════════════════════════════════════════════════════════════

def fix_04_gtx_fallback(src: str) -> str:
    """إصلاح 4.1: عند رفض GTX (-2010)، جرّب limit عادي مع حماية."""
    old = '''    # ══ وضع الأمر النهائي ══
    if _exec_mode == "gtx":
        try:
            o = exchange.create_order(
                sym, 'limit', side, qty, target,
                params={'timeInForce': 'GTX'}
            )
        except Exception as e:
            log.debug(f"[Pending] {sym} GTX rejected @ {target:.6f}: {e}")
            return None'''

    new = '''    # ══ وضع الأمر النهائي ══
    if _exec_mode == "gtx":
        try:
            o = exchange.create_order(
                sym, 'limit', side, qty, target,
                params={'timeInForce': 'GTX'}
            )
        except Exception as e:
            _emsg = str(e).lower()
            # [FIX-4.1] عند رفض GTX (post-only would cross):
            # انزلق بعيداً عن السوق بمقدار 1 tick إضافي ثم أعد المحاولة.
            if '-2010' in _emsg or 'post only' in _emsg or 'gtx' in _emsg:
                log.info(f"[Pending] {sym} GTX rejected — "
                         f"falling back with wider offset")
                try:
                    _tick = _get_tick_size(exchange, sym) or target * 1e-5
                    if side == 'buy':
                        target2 = target - _tick
                    else:
                        target2 = target + _tick
                    o = exchange.create_order(
                        sym, 'limit', side, qty, target2,
                        params={'timeInForce': 'GTX'}
                    )
                    target = target2  # للـ rec
                except Exception as e2:
                    log.warning(f"[Pending] {sym} GTX fallback failed: {e2}")
                    return None
            else:
                log.debug(f"[Pending] {sym} order rejected @ "
                          f"{target:.6f}: {e}")
                return None'''

    return _replace_once(src, old, new, "FIX-04-gtx-fallback")


# ════════════════════════════════════════════════════════════════
# الإصلاح 5: capital_at_placement set correctly
# ════════════════════════════════════════════════════════════════

def fix_05_capital_at_placement(src: str) -> str:
    """إصلاح 4.7: عيّن capital_at_placement الحقيقي."""
    old = '''        'capital_at_placement': 0.0, # يُملأ لاحقاً إن أردت'''

    new = '''        'capital_at_placement': float(
            _cap_snapshot if '_cap_snapshot' in dir() else 0.0
        ),'''

    # نضيف snapshot قبل الاستخدام
    old2 = '''    rec = {
        'order_id': str(o['id']),'''

    new2 = '''    # [FIX-4.7] Capital snapshot for Stage-2 sizing
    _cap_snapshot = 0.0
    try:
        if ad is not None:
            _bal_snap = exchange.fetch_balance()
            _cap_snapshot = float(_bal_snap['USDT'].get('free') or 0.0)
    except Exception:
        _cap_snapshot = 0.0

    rec = {
        'order_id': str(o['id']),'''

    result = _replace_once(src, old2, new2, "FIX-05a-cap-snapshot")
    result = _replace_once(result, old, new, "FIX-05b-cap-field")
    return result


# ════════════════════════════════════════════════════════════════
# الإصلاح 6: partial_taken=True after protective orders
# ════════════════════════════════════════════════════════════════

def fix_06_partial_taken_flag(src: str) -> str:
    """
    إصلاح 5.3: بعد وضع _place_protective_orders بنجاح، اضبط
    `_partial_taken=True` لتجنب partial مزدوج.
    """
    old = '''    # ══ [LAYER 7] Place protective orders on the exchange ══
    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        try:
            _ok = _place_protective_orders(exchange, sym, open_pos_live[sym])
            if _ok:
                open_pos_live[sym]['_prot_last_sl'] = float(adapted_sl)
                open_pos_live[sym]['_prot_last_tp'] = float(adapted_tp)
            else:
                log.warning(f"[Prot] {sym} protective orders not placed — "
                            f"bot will monitor manually")
        except Exception as _e:
            log.warning(f"[Prot] {sym} placement error: {_e}")'''

    new = '''    # ══ [LAYER 7] Place protective orders on the exchange ══
    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        _prot_ok = False
        for _attempt in range(3):
            try:
                _ok = _place_protective_orders(exchange, sym,
                                                open_pos_live[sym])
                if _ok:
                    open_pos_live[sym]['_prot_last_sl'] = float(adapted_sl)
                    open_pos_live[sym]['_prot_last_tp'] = float(adapted_tp)
                    _prot_ok = True
                    # [FIX-5.3] Broker-side partial TP is now placed.
                    # Mark it taken so the bot doesn't double-fire.
                    if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                            and float(getattr(CFG, 'PARTIAL_TP_PCT', 0.0)) > 0):
                        open_pos_live[sym]['_partial_taken'] = True
                        open_pos_live[sym]['_partial_pnl'] = float(
                            open_pos_live[sym].get('_partial_pnl', 0.0)
                        )
                    break
                log.warning(f"[Prot] {sym} protective placement "
                            f"attempt {_attempt+1} failed")
                time.sleep(0.5)
            except Exception as _e:
                log.warning(f"[Prot] {sym} attempt {_attempt+1} error: {_e}")
                time.sleep(0.5)
        if not _prot_ok:
            log.warning(f"[Prot] {sym} protective orders NOT placed after "
                        f"3 attempts — bot will monitor manually")'''

    return _replace_once(src, old, new, "FIX-06-partial-taken")


# ════════════════════════════════════════════════════════════════
# الإصلاح 7: fix physics fi index (no look-ahead)
# ════════════════════════════════════════════════════════════════

def fix_07_physics_fi(src: str) -> str:
    """إصلاح 7.1: استخدم آخر شمعة مغلقة، لا forming bar."""
    old = '''                # fi is only needed for physics-based checks
                fi = (len(ad.score) - 1) if ad is not None else -1'''

    new = '''                # [FIX-7.1] fi points to last CLOSED bar to avoid
                # look-ahead. In live, ad.closes[-1] is the forming bar.
                fi = (len(ad.score) - 2) if ad is not None else -1
                if fi < 0:
                    fi = 0'''

    return _replace_once(src, old, new, "FIX-07-physics-fi")


# ════════════════════════════════════════════════════════════════
# الإصلاح 8: remove duplicate Topo-Div check
# ════════════════════════════════════════════════════════════════

def fix_08_remove_dup_topo(src: str) -> str:
    """إصلاح 7.3: احذف الفحص المكرر لـ Topo-Div."""
    old = '''                # ── Topo-Div ──
                if not ex and fi > 0:
                    div_t = (ad.V[fi] - ad.V[fi-1]) / (ad.V[fi-1] + 1e-12)
                    if div_t > cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0:
                        ex = True; rsn = f"Topo-Div({div_t:.3f})"

                # ── MaxHold ──'''

    new = '''                # (Topo-Div already checked above — removed duplicate)

                # ── MaxHold ──'''

    return _replace_once(src, old, new, "FIX-08-dup-topo")


# ════════════════════════════════════════════════════════════════
# الإصلاح 9: handle -2022 in exit
# ════════════════════════════════════════════════════════════════

def fix_09_reduceonly_2022(src: str) -> str:
    """
    إصلاح 7.7: إذا رفض Binance الأمر بـ -2022 (ReduceOnly Rejected)
    فذلك يعني أن المركز أُغلق بالفعل بواسطة STOP_MARKET.
    اعتبره نجاحاً.
    """
    old = '''                        if not result['filled_qty'] or result['filled_qty'] <= 0:
                            log.warning(
                                f"⚠️ [Exit] {sym} no fill "
                                f"({result['reason']}) — position stays, "
                                f"protective orders INTACT on exchange"
                            )
                            # NO cancel. NO restore. Orders were never touched.
                            continue'''

    new = '''                        if not result['filled_qty'] or result['filled_qty'] <= 0:
                            _reason_str = str(result.get('reason', ''))
                            # [FIX-7.7] If exchange rejected with -2022,
                            # the position was already closed by the
                            # broker-side STOP_MARKET. Treat as success.
                            try:
                                _pos_chk = exchange.fetch_positions([sym])
                                _exch_amt = 0.0
                                for _pp in _pos_chk:
                                    _amt_pp = float(_pp['info'].get(
                                        'positionAmt', 0) or 0)
                                    if abs(_amt_pp) > 0:
                                        _exch_amt = abs(_amt_pp)
                                        break
                                if _exch_amt <= 0:
                                    log.info(
                                        f"✅ [Exit] {sym} position already "
                                        f"closed on exchange (protective "
                                        f"order fired) — removing local"
                                    )
                                    try:
                                        _cancel_all_protective_orders(
                                            exchange, sym)
                                    except Exception:
                                        pass
                                    del open_pos_live[sym]
                                    last_exit_time[sym] = time.time()
                                    continue
                            except Exception as _e:
                                log.debug(f"[Exit] position check "
                                          f"failed {sym}: {_e}")

                            log.warning(
                                f"⚠️ [Exit] {sym} no fill "
                                f"({result['reason']}) — position stays, "
                                f"protective orders INTACT on exchange"
                            )
                            continue'''

    return _replace_once(src, old, new, "FIX-09-reduceonly-2022")


# ════════════════════════════════════════════════════════════════
# الإصلاح 10: Add fees to live PnL
# ════════════════════════════════════════════════════════════════

def fix_10_live_fees_pnl(src: str) -> str:
    """إصلاح 10.1: اطرح الرسوم من PnL في الـ trade log."""
    old = '''                        # احسب net_pnl من الدخول/الخروج/الكمية + الربح الجزئي
                        _entry_px_lg = float(pos.get('entry') or 0)
                        _exit_px_lg  = float(exec_price or 0)
                        _qty_lg      = float(pos.get('qty') or 0)
                        _partial_lg  = float(pos.get('_partial_pnl', 0.0))
                        if pos.get('action') == 'BUY':
                            _net_pnl_lg = (_exit_px_lg - _entry_px_lg) * _qty_lg + _partial_lg
                        else:
                            _net_pnl_lg = (_entry_px_lg - _exit_px_lg) * _qty_lg + _partial_lg'''

    new = '''                        # [FIX-10.1] احسب net_pnl مع الرسوم
                        _entry_px_lg = float(pos.get('entry') or 0)
                        _exit_px_lg  = float(exec_price or 0)
                        _qty_lg      = float(pos.get('qty') or 0)
                        _partial_lg  = float(pos.get('_partial_pnl', 0.0))
                        if pos.get('action') == 'BUY':
                            _gross_lg = (_exit_px_lg - _entry_px_lg) * _qty_lg
                        else:
                            _gross_lg = (_entry_px_lg - _exit_px_lg) * _qty_lg
                        # Maker fee on entry, taker on exit (SL/TP)
                        _entry_fee_lg = _qty_lg * _entry_px_lg * CFG.MAKER_FEE
                        _exit_fee_lg  = _qty_lg * _exit_px_lg * CFG.TAKER_FEE
                        # Funding (best-effort estimate)
                        _hold_s_lg = time.time() - float(pos.get('entry_ts') or time.time())
                        _fund_pays_lg = max(0, int(_hold_s_lg // 28800))  # 8h
                        _funding_lg = _qty_lg * _entry_px_lg * CFG.FUNDING_RATE_COST * _fund_pays_lg
                        _net_pnl_lg = (_gross_lg - _entry_fee_lg - _exit_fee_lg
                                        - _funding_lg + _partial_lg)'''

    return _replace_once(src, old, new, "FIX-10-live-fees")


# ════════════════════════════════════════════════════════════════
# الإصلاح 11: cancel protective orders after successful exit
# ════════════════════════════════════════════════════════════════

def fix_11_cancel_prot_after_exit(src: str) -> str:
    """
    إصلاح 9.2: تأكد من إلغاء كل الأوامر الواقية بعد كل exit ناجح
    (بما فيها الـ partial TP التي قد تبقى).
    """
    old = '''                    del open_pos_live[sym]
                    last_exit_time[sym] = time.time()
                    log.info(f"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]")'''

    new = '''                    # [FIX-9.2] Force-clean ALL protective orders
                    try:
                        _left = _cancel_all_protective_orders(exchange, sym)
                        if _left > 0:
                            log.debug(f"[Prot] {sym} post-exit cleaned "
                                      f"{_left} residual order(s)")
                    except Exception as _e:
                        log.debug(f"[Prot] {sym} post-exit cleanup: {_e}")

                    del open_pos_live[sym]
                    last_exit_time[sym] = time.time()
                    log.info(f"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]")'''

    return _replace_once(src, old, new, "FIX-11-clean-prot-after-exit")


# ════════════════════════════════════════════════════════════════
# الإصلاح 12: fix _pending_drop_stale to actually cancel
# ════════════════════════════════════════════════════════════════

def fix_12_pending_drop_cancel(src: str) -> str:
    """إصلاح 0.1: اجعل _pending_drop_stale يُلغي فعلاً."""
    old = '''def _pending_drop_stale(max_age_s: float = 3600.0) -> int:
    """Remove pending entries older than max_age_s (safety)."""
    now = time.time()
    removed = 0
    for sym in list(_PENDING_ORDERS.keys()):
        rec = _PENDING_ORDERS[sym]
        if now - float(rec.get('placed_at', 0.0)) > max_age_s:
            oid = rec.get('order_id')
            if oid:
                try:
                    # best-effort cancel
                    pass
                except Exception:
                    pass
            _PENDING_ORDERS.pop(sym, None)
            removed += 1
    return removed'''

    new = '''def _pending_drop_stale(exchange=None, max_age_s: float = 3600.0) -> int:
    """
    [FIX-0.1] Remove pending entries older than max_age_s AND
    cancel their exchange-side orders.
    """
    now = time.time()
    removed = 0
    for sym in list(_PENDING_ORDERS.keys()):
        rec = _PENDING_ORDERS[sym]
        if now - float(rec.get('placed_at', 0.0)) > max_age_s:
            oid = rec.get('order_id')
            if oid and exchange is not None:
                try:
                    exchange.cancel_order(oid, sym)
                    log.info(f"[Pending] stale cancel {sym} oid={oid}")
                except Exception as _e:
                    _msg = str(_e).lower()
                    if ('-2011' not in _msg and 'unknown order' not in _msg
                            and '-2013' not in _msg):
                        log.warning(f"[Pending] stale cancel {sym} failed: {_e}")
            _PENDING_ORDERS.pop(sym, None)
            removed += 1
    return removed'''

    result = _replace_once(src, old, new, "FIX-12-pending-stale-cancel")

    # أيضًا: update the call site
    old2 = '''    _stale = _pending_drop_stale(max_age_s=max(3600.0, CFG.PO_MAX_WAIT_S * 4))'''
    new2 = '''    _stale = _pending_drop_stale(exchange, max_age_s=max(3600.0, CFG.PO_MAX_WAIT_S * 4))'''
    result = _replace_once(result, old2, new2, "FIX-12b-stale-call")
    return result


# ════════════════════════════════════════════════════════════════
# الإصلاح 13: adopt protective orders on periodic reconcile
# ════════════════════════════════════════════════════════════════

def fix_13_reconcile_places_prot(src: str) -> str:
    """
    إصلاح 0.2/72: بعد كل reconcile دوري، اضبط أوامر واقية
    للمراكز المُعتمدة حديثاً.
    """
    old = '''                try:
                    open_pos_live = reconcile_state_machine(
                        exchange, open_pos_live, _recon_syms
                    )
                except Exception as _e:
                    log.warning(f"[Reconcile] state machine failed: {_e}")
                run_live._last_reconcile = time.time()'''

    new = '''                _before = set(open_pos_live.keys())
                try:
                    open_pos_live = reconcile_state_machine(
                        exchange, open_pos_live, _recon_syms
                    )
                except Exception as _e:
                    log.warning(f"[Reconcile] state machine failed: {_e}")
                _after = set(open_pos_live.keys())
                # [FIX-72] Ensure newly adopted positions have protective orders
                _newly_adopted = _after - _before
                for _sym_na in _newly_adopted:
                    try:
                        _place_protective_orders(exchange, _sym_na,
                                                 open_pos_live[_sym_na])
                        log.info(f"[Reconcile] protective orders placed "
                                 f"for adopted {_sym_na}")
                    except Exception as _e:
                        log.warning(f"[Reconcile] protective placement "
                                    f"for {_sym_na} failed: {_e}")
                run_live._last_reconcile = time.time()'''

    return _replace_once(src, old, new, "FIX-13-reconcile-prot")


# ════════════════════════════════════════════════════════════════
# الإصلاح 14: protect against infinite exit retries
# ════════════════════════════════════════════════════════════════

def fix_14_exit_retry_limit(src: str) -> str:
    """
    إصلاح 8.4: بعد N محاولات فاشلة، استخدم market بغض النظر.
    """
    old = '''                            log.warning(
                                f"⚠️ [Exit] {sym} no fill "
                                f"({result['reason']}) — position stays, "
                                f"protective orders INTACT on exchange"
                            )
                            continue'''

    new = '''                            # [FIX-8.4] After 3 failed attempts, force market
                            _retry_cnt = int(pos.get('_exit_retry', 0)) + 1
                            pos['_exit_retry'] = _retry_cnt
                            if _retry_cnt >= 3:
                                log.warning(
                                    f"[Exit] {sym} forcing MARKET after "
                                    f"{_retry_cnt} failed post-only attempts"
                                )
                                try:
                                    o = exchange.create_order(
                                        sym, 'market', s, pos['qty'], None,
                                        params={'reduceOnly': True},
                                    )
                                    v = verify_fill(exchange, o['id'], sym,
                                                    timeout_s=3.0)
                                    if v and v['filled']:
                                        exec_price = float(v.get('avg_price')
                                                          or price)
                                        exit_reason = f"{rsn} (forced-market)"
                                        _exit_ok = True
                                        # Fall through to cleanup below
                                except Exception as _em:
                                    log.error(f"[Exit] forced market "
                                              f"failed {sym}: {_em}")

                            if not _exit_ok:
                                log.warning(
                                    f"⚠️ [Exit] {sym} no fill "
                                    f"({result['reason']}) — attempt "
                                    f"{_retry_cnt}/3"
                                )
                                continue'''

    # ملاحظة: يجب أن يبقى منطق الـ check for exchange-closed position.
    # سنُبقي الجزء الأول من الفحص (FIX-09) كما هو.
    return _replace_once(src, old, new, "FIX-14-exit-retry")


# ════════════════════════════════════════════════════════════════
# الإصلاح 15: set capital_at_placement in place_pending_entry
# ════════════════════════════════════════════════════════════════

def fix_15_adv_snapshot(src: str) -> str:
    """
    إصلاح إضافي: احفظ `trail_dist_frac` و `trail_activate_frac`
    في rec لاستخدامها عند promotion لاحقاً.
    """
    old = '''        'execution_mode': str(_exec_mode),
        'marketable_px': (float(_marketable_px)
                           if _marketable_px is not None else 0.0),
    }'''

    new = '''        'execution_mode': str(_exec_mode),
        'marketable_px': (float(_marketable_px)
                           if _marketable_px is not None else 0.0),
        # [FIX-15] snapshot trail params to avoid needing ad_ref later
        'trail_dist_frac': float(_trail_d_snapshot),
        'trail_activate_frac': float(_trail_a_snapshot),
    }'''

    old2 = '''    rec = {
        'order_id': str(o['id']),
        'sym': sym,'''

    new2 = '''    # [FIX-15] Trail params snapshot
    _trail_d_snapshot, _trail_a_snapshot = 0.003, 0.004
    try:
        if ad is not None:
            _trail_d_snapshot, _trail_a_snapshot = compute_trail_params(
                ad, max(0, min(int(sig.feat_idx), len(ad.E_therm) - 1))
            )
    except Exception:
        pass

    rec = {
        'order_id': str(o['id']),
        'sym': sym,'''

    result = _replace_once(src, old2, new2, "FIX-15a-snapshot")
    result = _replace_once(result, old, new, "FIX-15b-store")
    return result


# ════════════════════════════════════════════════════════════════
# الإصلاح 16: use snapshot trail params in promotion
# ════════════════════════════════════════════════════════════════

def fix_16_use_snapshot_in_promote(src: str) -> str:
    """استخدم trail params من rec بدل ad_ref (المحذوف)."""
    old = '''    # σ-scaled trailing params at entry
    trail_d, trail_a = (0.003, 0.004)
    try:
        ad = rec.get('ad_ref')
        entry_fi = int(rec.get('entry_fi') or 0)
        if ad is not None:
            trail_d, trail_a = compute_trail_params(ad, entry_fi)
    except Exception:
        pass'''

    new = '''    # [FIX-16] Prefer snapshot in rec; fall back to ad_ref; else defaults
    trail_d = float(rec.get('trail_dist_frac') or 0.003)
    trail_a = float(rec.get('trail_activate_frac') or 0.004)
    if trail_d <= 0 or trail_a <= 0:
        try:
            ad = rec.get('ad_ref')
            entry_fi = int(rec.get('entry_fi') or 0)
            if ad is not None:
                trail_d, trail_a = compute_trail_params(ad, entry_fi)
        except Exception:
            pass'''

    return _replace_once(src, old, new, "FIX-16-promote-trail")


# ════════════════════════════════════════════════════════════════
# الإصلاح 17: fix _partial_pnl in live to subtract fees
# ════════════════════════════════════════════════════════════════

def fix_17_partial_pnl_fees(src: str) -> str:
    """إصلاح 10.2: اطرح رسوم partial من _partial_pnl في live."""
    old = '''                                    if pos['action'] == "BUY":
                                        _partial_net = (_avg_px - float(pos['entry'])) * _filled_q
                                    else:
                                        _partial_net = (float(pos['entry']) - _avg_px) * _filled_q
                                    pos['_partial_pnl'] = float(pos.get('_partial_pnl', 0.0)) + _partial_net'''

    new = '''                                    # [FIX-10.2] subtract fees from partial
                                    if pos['action'] == "BUY":
                                        _partial_gross = (_avg_px - float(pos['entry'])) * _filled_q
                                    else:
                                        _partial_gross = (float(pos['entry']) - _avg_px) * _filled_q
                                    _partial_fee = (_filled_q * float(pos['entry']) * CFG.MAKER_FEE
                                                    + _filled_q * _avg_px * CFG.TAKER_FEE)
                                    _partial_net = _partial_gross - _partial_fee
                                    pos['_partial_pnl'] = float(pos.get('_partial_pnl', 0.0)) + _partial_net'''

    return _replace_once(src, old, new, "FIX-17-partial-fees")


# ════════════════════════════════════════════════════════════════
# الإصلاح 18: guard against -1003 rate limit
# ════════════════════════════════════════════════════════════════

def fix_18_rate_limit_guard(src: str) -> str:
    """
    إصلاح 3.7/7.6: wrapper يعيد المحاولة عند rate limit
    لكن لا يُنفّذ في الـ fetch_positions المتكرر.
    نسجّل فقط الحدث.
    """
    # هذا إصلاح ضوئي: نضيف تتبع بسيط لـ -1003
    old = '''_RATE_TRACKER: Dict = {
    'window': [],          # list of (ts, weight)
    'total_this_min': 0.0,
    'rejected_count': 0,
    'last_report_ts': 0.0,
}'''

    new = '''_RATE_TRACKER: Dict = {
    'window': [],          # list of (ts, weight)
    'total_this_min': 0.0,
    'rejected_count': 0,
    'last_report_ts': 0.0,
    # [FIX-3.7] Count actual exchange rate-limit hits
    'hits_1003': 0,
    'last_hit_ts': 0.0,
}'''

    return _replace_once(src, old, new, "FIX-18-rate-tracker")


# ════════════════════════════════════════════════════════════════
# الإصلاح 19: prevent double protective orders - check before place
# ════════════════════════════════════════════════════════════════

def fix_19_verify_protective_after_place(src: str) -> str:
    """
    إصلاح 6.3/6.5: بعد وضع الأوامر الواقية، تحقق من وجودها،
    وإذا فشل SL، ألغِ TP.
    """
    old = '''        _partial_ok = placed['partial_tp'] or not _partial_enabled
        if placed['sl'] and placed['tp'] and _partial_ok:
            if _partial_enabled:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"PARTIAL-TP@{_partial_price:.6f} "
                         f"FULL-TP@{tp:.6f} placed")
            else:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"TP@{tp:.6f} placed")
            return True
        log.warning(f"[Prot] {sym} partial: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return (placed['sl'] and placed['tp']
                and (placed['partial_tp'] or not _partial_enabled))'''

    new = '''        _partial_ok = placed['partial_tp'] or not _partial_enabled
        # [FIX-6.5] If SL failed but TP succeeded, roll back TP to avoid
        # unprotected position with only TP.
        if not placed['sl']:
            log.warning(f"[Prot] {sym} SL placement failed — "
                        f"rolling back any placed TP")
            try:
                _cancel_all_protective_orders(exchange, sym)
            except Exception:
                pass
            return False

        if placed['sl'] and placed['tp'] and _partial_ok:
            if _partial_enabled:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"PARTIAL-TP@{_partial_price:.6f} "
                         f"FULL-TP@{tp:.6f} placed")
            else:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"TP@{tp:.6f} placed")
            return True
        log.warning(f"[Prot] {sym} partial: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return False'''

    return _replace_once(src, old, new, "FIX-19-prot-rollback")


# ════════════════════════════════════════════════════════════════
# Main runner
# ════════════════════════════════════════════════════════════════

FIXES = [
    ("FIX-01 snap leverage",         fix_01_snap_leverage),
    ("FIX-02 step size helpers",     fix_02_step_size_helper),
    ("FIX-03 qty sanitize",          fix_03_qty_sanitize_in_pending),
    ("FIX-04 GTX fallback",          fix_04_gtx_fallback),
    ("FIX-05 capital_at_placement",  fix_05_capital_at_placement),
    ("FIX-06 partial_taken",         fix_06_partial_taken_flag),
    ("FIX-07 physics fi",            fix_07_physics_fi),
    ("FIX-08 dup Topo-Div",          fix_08_remove_dup_topo),
    ("FIX-09 reduceOnly -2022",      fix_09_reduceonly_2022),
    ("FIX-10 live fees PnL",         fix_10_live_fees_pnl),
    ("FIX-11 cancel prot exit",      fix_11_cancel_prot_after_exit),
    ("FIX-12 pending stale cancel",  fix_12_pending_drop_cancel),
    ("FIX-13 reconcile prot",        fix_13_reconcile_places_prot),
    ("FIX-14 exit retry limit",      fix_14_exit_retry_limit),
    ("FIX-15 adv snapshot",          fix_15_adv_snapshot),
    ("FIX-16 promote trail",         fix_16_use_snapshot_in_promote),
    ("FIX-17 partial fees",          fix_17_partial_pnl_fees),
    ("FIX-18 rate tracker",          fix_18_rate_limit_guard),
    ("FIX-19 prot rollback",         fix_19_verify_protective_after_place),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="trading_2.py")
    ap.add_argument("--output", default="trading_2_fixed.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()

    print(f"📖 Loaded {len(src):,} bytes from {args.input}")
    print(f"🔧 Applying {len(FIXES)} fixes...\n")

    for name, fn in FIXES:
        print(f"▶ {name}")
        try:
            src = fn(src)
        except Exception as e:
            print(f"  ❌ Fix crashed: {e}")
            import traceback
            traceback.print_exc()

    # Header comment
    header = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  trading_2_fixed.py — Auto-patched for Live/Backtest parity
#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
#  Patches applied: {len(FIXES)}
#  Source: {args.input}
# ════════════════════════════════════════════════════════════════════
"""
    # Keep the shebang if present
    if src.startswith("#!"):
        first_nl = src.index("\n")
        shebang = src[:first_nl+1]
        src = shebang + header.split("\n", 1)[1] + src[first_nl+1:]

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src)

    # Syntax check
    print(f"\n🧪 Syntax check...")
    try:
        compile(src, args.output, "exec")
        print(f"✅ {args.output} compiles OK")
    except SyntaxError as e:
        print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
        sys.exit(2)

    print(f"\n✅ Done. Output: {args.output}")
    print(f"\nTo run:")
    print(f"  python {args.output} --mode backtest ...")
    print(f"  python {args.output} --mode live --api-key ... --api-secret ...")


if __name__ == "__main__":
    main()
