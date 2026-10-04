#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_duplicate_orders.py — إصلاح تكرار أوامر الحماية على البورصة
+ إصلاحات ثانوية.

المعالجات:
  1. _cancel_all_protective_orders → متعدد المرات + تحقق
  2. Initial restoration → تخطّي إذا pending موجود
  3. _place_protective_orders → sleep 0.5 + verify + retry
  4. reconcile_state_machine → استخدم قيم pending إن وُجدت
  5. _trade_log_init → append بدل truncate

التشغيل:
  python3 fix_duplicate_orders.py --dry-run
  python3 fix_duplicate_orders.py
"""

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Patch 1: _cancel_all_protective_orders → robust
# ═══════════════════════════════════════════════════════════════

PATCH1_MARKER = "[DUPLICATE-FIX] two-pass cancel"
PATCH1_OLD = '''def _cancel_all_protective_orders(exchange, sym: str) -> int:
    """
    Cancel every STOP_MARKET / TAKE_PROFIT_MARKET on the symbol.
    Returns count cancelled. Silent on errors (best-effort).
    """
    n = 0
    try:
        for o in exchange.fetch_open_orders(sym):
            if _is_protective_order(o):
                try:
                    exchange.cancel_order(o['id'], sym)
                    n += 1
                except Exception as e:
                    log.debug(f"[Prot] cancel {sym} oid={o['id']} failed: {e}")
    except Exception as e:
        log.debug(f"[Prot] fetch_open_orders {sym} failed: {e}")
    return n'''

PATCH1_NEW = '''def _cancel_all_protective_orders(exchange, sym: str,
                                     max_passes: int = 2) -> int:
    """
    Cancel every STOP_MARKET / TAKE_PROFIT_MARKET on the symbol.

    [DUPLICATE-FIX] two-pass cancel: الأولى تلغي، والثانية تتحقق.
    هذا يمنع بقاء نسخة ثانية من الأوامر على البورصة.
    """
    n = 0
    for pass_idx in range(max_passes):
        try:
            open_orders = exchange.fetch_open_orders(sym)
        except Exception as e:
            log.debug(f"[Prot] fetch_open_orders {sym} failed: {e}")
            break
        prot_orders = [o for o in open_orders if _is_protective_order(o)]
        if not prot_orders:
            break
        if pass_idx == 0:
            log.info(f"[Prot] {sym} cancelling {len(prot_orders)} "
                     f"stale protective order(s)")
        for o in prot_orders:
            try:
                exchange.cancel_order(o['id'], sym)
                n += 1
            except Exception as e:
                log.warning(f"[Prot] cancel {sym} oid={o['id']} failed: {e}")
        import time as _t
        _t.sleep(0.3)
    return n'''


# ═══════════════════════════════════════════════════════════════
# Patch 2: initial restoration → skip if pending exists
# ═══════════════════════════════════════════════════════════════

PATCH2_MARKER = "[DUPLICATE-FIX] defer if pending exists"
PATCH2_OLD = '''    # ══ [LAYER 7] Ensure every restored position has fresh protective orders ══
    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        _prot_ok = 0
        _prot_fail = 0
        for _sym_p, _pos_p in open_pos_live.items():
            # Clear stale cache so we force re-place
            _pos_p.pop('_prot_last_sl', None)
            _pos_p.pop('_prot_last_tp', None)
            try:
                if _place_protective_orders(exchange, _sym_p, _pos_p):
                    _pos_p['_prot_last_sl'] = float(_pos_p.get('sl') or 0)
                    _pos_p['_prot_last_tp'] = float(_pos_p.get('tp1') or 0)
                    _prot_ok += 1
                else:
                    _prot_fail += 1
            except Exception as _e:
                log.warning(f"[Prot] restore {_sym_p} failed: {_e}")
                _prot_fail += 1
        log.info(f"  [Prot] restored={_prot_ok} failed={_prot_fail}")'''

PATCH2_NEW = '''    # ══ [LAYER 7] Ensure every restored position has fresh protective orders ══
    # [DUPLICATE-FIX] defer if pending exists — لأن الترقية ستضعها
    # بشكل صحيح، ووضعها الآن يسبب تكراراً على البورصة.
    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        _prot_ok = 0
        _prot_fail = 0
        _prot_deferred = 0
        _prot_dropped_pending = 0
        for _sym_p, _pos_p in list(open_pos_live.items()):
            _pending_rec = _PENDING_ORDERS.get(_sym_p)
            if _pending_rec is not None:
                # جلب الحالة الحديثة
                _status = str(_pending_rec.get('status') or 'open')
                try:
                    _sweep_pending_once(exchange, _sym_p)
                    _pending_rec = _PENDING_ORDERS.get(_sym_p)
                    if _pending_rec is not None:
                        _status = str(_pending_rec.get('status') or 'open')
                except Exception as _e:
                    log.debug(f"[Prot] sweep {_sym_p} failed: {_e}")

                if _status == 'closed':
                    log.info(
                        f"[Prot] {_sym_p} pending already closed — "
                        f"dropping record, placing protection now"
                    )
                    _PENDING_ORDERS.pop(_sym_p, None)
                    _prot_dropped_pending += 1
                    # continue to place protection below
                else:
                    log.info(
                        f"[Prot] {_sym_p} pending status={_status} — "
                        f"deferring protective placement"
                    )
                    _prot_deferred += 1
                    continue

            _pos_p.pop('_prot_last_sl', None)
            _pos_p.pop('_prot_last_tp', None)
            try:
                if _place_protective_orders(exchange, _sym_p, _pos_p):
                    _pos_p['_prot_last_sl'] = float(_pos_p.get('sl') or 0)
                    _pos_p['_prot_last_tp'] = float(_pos_p.get('tp1') or 0)
                    _prot_ok += 1
                else:
                    _prot_fail += 1
            except Exception as _e:
                log.warning(f"[Prot] restore {_sym_p} failed: {_e}")
                _prot_fail += 1
        log.info(f"  [Prot] restored={_prot_ok} "
                 f"deferred={_prot_deferred} "
                 f"dropped={_prot_dropped_pending} "
                 f"failed={_prot_fail}")'''


# ═══════════════════════════════════════════════════════════════
# Patch 3: _place_protective_orders → verify cancel
# ═══════════════════════════════════════════════════════════════

PATCH3_MARKER = "[DUPLICATE-FIX] verify cancel before placing"
PATCH3_OLD = '''        # Cancel any stale protective orders first (idempotent)
        _cancel_all_protective_orders(exchange, sym)
        time.sleep(0.1)

        placed = {'sl': False, 'tp': False, 'partial_tp': False}'''

PATCH3_NEW = '''        # Cancel any stale protective orders first (idempotent)
        # [DUPLICATE-FIX] verify cancel before placing
        _canceled_count = _cancel_all_protective_orders(exchange, sym)
        if _canceled_count > 0:
            log.debug(f"[Prot] {sym} canceled {_canceled_count} "
                      f"stale order(s)")
        time.sleep(0.5)
        try:
            _remaining = [o for o in exchange.fetch_open_orders(sym)
                          if _is_protective_order(o)]
            if _remaining:
                log.warning(
                    f"[Prot] {sym} {len(_remaining)} protective "
                    f"order(s) still open after cancel — retrying"
                )
                _cancel_all_protective_orders(exchange, sym)
                time.sleep(0.5)
        except Exception as _e:
            log.debug(f"[Prot] verify cancel for {sym} failed: {_e}")

        placed = {'sl': False, 'tp': False, 'partial_tp': False}'''


# ═══════════════════════════════════════════════════════════════
# Patch 4: reconcile → use pending geometry when adopting
# ═══════════════════════════════════════════════════════════════

PATCH4_MARKER = "[DUPLICATE-FIX] use pending geometry"
PATCH4_OLD_LINE = 'log.warning(f"[Reconcile] {sym} exchange-only → adopting")'
PATCH4_OLD_BLOCK = '''            log.warning(f"[Reconcile] {sym} exchange-only → adopting")
            open_pos_live[sym] = {
                'action': ex['side'],
                'entry': ex['entry'],
                'qty': ex['qty'],
                'sl': ex['entry'] * (0.985 if ex['side'] == 'BUY' else 1.015),
                'tp1': ex['entry'] * (1.03 if ex['side'] == 'BUY' else 0.97),
                'T_info': 0.0,
                'dyn_risk': 0.01,
                'entry_ts': time.time(),
                'adopted': True,
            }
            changed += 1'''

PATCH4_NEW_BLOCK = '''            log.warning(f"[Reconcile] {sym} exchange-only → adopting")
            # [DUPLICATE-FIX] use pending geometry if available
            _pending_vals = None
            _pending_rec = _PENDING_ORDERS.get(sym)
            if _pending_rec is not None:
                _p_sl_dist = float(_pending_rec.get('orig_sl_dist') or 0)
                _p_tp_dist = float(_pending_rec.get('orig_tp_dist') or 0)
                if _p_sl_dist > 0 and _p_tp_dist > 0:
                    _pending_vals = {
                        'sl_dist': _p_sl_dist,
                        'tp_dist': _p_tp_dist,
                        'T_info': float(_pending_rec.get('T_info') or 0),
                        'dyn_risk': float(_pending_rec.get('dyn_risk') or 0.01),
                    }
                    log.info(
                        f"[Reconcile] {sym} using pending geometry: "
                        f"sl_dist={_p_sl_dist:.6f} tp_dist={_p_tp_dist:.6f}"
                    )

            if _pending_vals is not None:
                if ex['side'] == 'BUY':
                    _adopted_sl = ex['entry'] - _pending_vals['sl_dist']
                    _adopted_tp = ex['entry'] + _pending_vals['tp_dist']
                else:
                    _adopted_sl = ex['entry'] + _pending_vals['sl_dist']
                    _adopted_tp = ex['entry'] - _pending_vals['tp_dist']
                open_pos_live[sym] = {
                    'action': ex['side'],
                    'entry': ex['entry'],
                    'qty': ex['qty'],
                    'sl': _adopted_sl,
                    'tp1': _adopted_tp,
                    'T_info': _pending_vals['T_info'],
                    'dyn_risk': _pending_vals['dyn_risk'],
                    'entry_ts': time.time(),
                    'adopted': True,
                    'sl_dist_initial': _pending_vals['sl_dist'],
                }
                _PENDING_ORDERS.pop(sym, None)
            else:
                open_pos_live[sym] = {
                    'action': ex['side'],
                    'entry': ex['entry'],
                    'qty': ex['qty'],
                    'sl': ex['entry'] * (0.985 if ex['side'] == 'BUY' else 1.015),
                    'tp1': ex['entry'] * (1.03 if ex['side'] == 'BUY' else 0.97),
                    'T_info': 0.0,
                    'dyn_risk': 0.01,
                    'entry_ts': time.time(),
                    'adopted': True,
                }
            changed += 1'''


# ═══════════════════════════════════════════════════════════════
# Patch 5: _trade_log_init → append instead of truncate
# ═══════════════════════════════════════════════════════════════

PATCH5_MARKER = "[DUPLICATE-FIX] append mode"
PATCH5_OLD = '''    try:
        with open(_TRADE_LOG_PATH, 'w', encoding='utf-8') as f:'''
PATCH5_NEW = '''    try:
        # [DUPLICATE-FIX] append mode — keep prior trades
        with open(_TRADE_LOG_PATH, 'a', encoding='utf-8') as f:'''


# ═══════════════════════════════════════════════════════════════
# محرك التطبيق
# ═══════════════════════════════════════════════════════════════

def apply_patch(text, old, new, marker, name):
    if marker in text:
        return text, f"⏭️  {name}: مُطبَّق مسبقاً"
    if old not in text:
        return text, f"❌ {name}: لم أجد النص الأصلي"
    text = text.replace(old, new, 1)
    return text, f"✅ {name}: طُبِّق"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"❌ {args.file} غير موجود")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("═" * 70)
    print("  fix_duplicate_orders.py")
    print("═" * 70)
    print()

    text, s = apply_patch(text, PATCH1_OLD, PATCH1_NEW, PATCH1_MARKER,
                          "Patch 1: robust cancel (multi-pass)")
    print(f"  {s}")

    text, s = apply_patch(text, PATCH2_OLD, PATCH2_NEW, PATCH2_MARKER,
                          "Patch 2: defer restoration if pending")
    print(f"  {s}")

    text, s = apply_patch(text, PATCH3_OLD, PATCH3_NEW, PATCH3_MARKER,
                          "Patch 3: verify cancel in place_protective")
    print(f"  {s}")

    text, s = apply_patch(text, PATCH4_OLD_BLOCK, PATCH4_NEW_BLOCK,
                          PATCH4_MARKER,
                          "Patch 4: reconcile uses pending geometry")
    print(f"  {s}")

    text, s = apply_patch(text, PATCH5_OLD, PATCH5_NEW, PATCH5_MARKER,
                          "Patch 5: trade log append mode")
    print(f"  {s}")

    # verify
    try:
        ast.parse(text)
        print()
        print("  ✅ الصياغة صحيحة (ast.parse)")
    except SyntaxError as e:
        print()
        print(f"  ❌ خطأ صياغة: {e.lineno}: {e.text}")
        return 3

    if text == original:
        print()
        print("  ℹ️  لا تعديلات جديدة.")
        return 0

    if args.dry_run:
        print()
        print("═" * 70)
        print("  ℹ️  Dry run — لم يُكتب أي شيء")
        print("═" * 70)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_dup_{ts}')
    shutil.copy2(p, backup)
    print()
    print(f"  💾 Backup: {backup}")
    p.write_text(text, encoding='utf-8')
    print(f"  ✏️  كُتب: {p}")
    print()
    print("═" * 70)
    print("  ✅ تم")
    print("═" * 70)
    print(f"  للتراجع: cp {backup.name} {p.name}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
