#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Professional atomic patch script for trading_published_pro_1h.py

Fixes:
  1. [FIX-C1/C3] Restrict restart peak/CI reconstruction strictly to
     positions restored at startup, and scan ONLY bars opened strictly
     after entry_ts (unit-safe DatetimeIndex search, never sig.close_idx
     and never 0 / 1e18 defaults).
  2. [_lv_finalize_position] Initialize peak_price = entry.
  3. [_lv_update_extremes] Only include 1m candles opened strictly after
     entry_ts (prevents pre-fill intrabar wick leakage).
  4. [_is_tp_protective] Inspect info.type / info.origType /
     takeProfitPrice / stopLossPrice so Binance Futures TP orders are
     never misclassified as stale SL orders.
  5. [_place_protective_orders & _lv_check_protective_on_exchange]
     Snap SL/TP/partial prices & quantities to exchange precision, read
     info.triggerPrice, and use tick-aware comparison tolerance so
     unchanged TP/SL orders are not needlessly cancelled and re-placed.

Usage:
  python patch_fix_live_prot_c1.py
  python patch_fix_live_prot_c1.py --target path/to/trading_published_pro_1h.py --dry-run
"""

import argparse
import os
import py_compile
import shutil
import sys
from datetime import datetime

PATCH_MARKER = "# [LIVE-TRAIL-PROT-FIX-APPLIED]"


def apply_patch(target_path: str, dry_run: bool = False) -> None:
    if not os.path.exists(target_path):
        print(f"[ERROR] Target file not found: {target_path}", file=sys.stderr)
        sys.exit(1)

    with open(target_path, "r", encoding="utf-8") as f:
        src = f.read()

    if PATCH_MARKER in src:
        print(f"[OK] Patch already applied ({PATCH_MARKER} found). Nothing to do.")
        return

    replacements = [
        # ── 1. Add patch marker at top ──────────────────────────────────
        (
            "patch marker",
            "# [LIVE-PARITY-FIXES] applied",
            "# [LIVE-PARITY-FIXES] applied\n" + PATCH_MARKER,
        ),

        # ── 2. Fix _is_tp_protective ────────────────────────────────────
        (
            "_is_tp_protective",
            '''def _is_tp_protective(o: Dict) -> bool:
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
        return False''',
            '''def _is_tp_protective(o: Dict) -> bool:
    """
    [FIXED] True if the protective order is a TAKE_PROFIT (vs SL).
    Checks unified trigger fields and raw Binance info fields
    (orderType / type / origType) before falling back to unified type.
    """
    try:
        if o.get('takeProfitPrice'):
            return True
        if o.get('stopLossPrice'):
            return False
        info = o.get('info') or {}
        raw_t = str(
            info.get('orderType')
            or info.get('type')
            or info.get('origType')
            or ''
        ).lower()
        if 'take_profit' in raw_t:
            return True
        if 'stop_market' in raw_t or raw_t == 'stop':
            return False
        # Fallback to unified type
        t = str(o.get('type') or '').lower()
        return 'take_profit' in t
    except Exception:
        return False''',
        ),

        # ── 3. Fix _lv_check_protective_on_exchange triggerPrice lookup ──
        (
            "_lv_check_protective_on_exchange",
            '''    for o in orders:
        sp = float(
            o.get('stopPrice')
            or o.get('triggerPrice')
            or (o.get('info') or {}).get('stopPrice')
            or 0
        )''',
            '''    for o in orders:
        _info = o.get('info') or {}
        sp = float(
            o.get('stopPrice')
            or o.get('triggerPrice')
            or _info.get('stopPrice')
            or _info.get('triggerPrice')
            or 0
        )''',
        ),

        # ── 4. Fix _place_protective_orders precision & tick-aware tol ──
        (
            "_place_protective_orders precision & tol",
            '''        # ── Compute partial-TP target price (needed for stale detection) ──
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

        # ── Fetch existing protective orders ──
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
            # [CLASSIFIER-FIX] delegate to global helper
            return _is_tp_protective(o)

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
                    _stale_ids.append(o['id'])''',
            '''        def _snap_p(px_val):
            try:
                return float(exchange.price_to_precision(sym, float(px_val)))
            except Exception:
                return float(px_val)

        def _snap_q(q_val):
            try:
                return float(exchange.amount_to_precision(sym, float(q_val)))
            except Exception:
                return float(q_val)

        sl = _snap_p(sl)
        tp = _snap_p(tp)
        qty = _snap_q(qty)
        if sl <= 0 or tp <= 0 or qty <= 0:
            return False

        # ── Compute partial-TP target price (needed for stale detection) ──
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
                _partial_price = _snap_p(_entry_px + _sl_dist0 * _partial_r)
            else:
                _partial_price = _snap_p(_entry_px - _sl_dist0 * _partial_r)
            if action == 'BUY' and _partial_price >= tp:
                _partial_enabled = False
            elif action == 'SELL' and _partial_price <= tp:
                _partial_enabled = False
        if _partial_enabled and _partial_price <= 0:
            _partial_enabled = False
        if pos.get('_partial_taken'):
            _partial_enabled = False

        # ── Fetch existing protective orders ──
        try:
            _existing = _lv_open_orders_all(exchange, sym)
        except Exception as _e:
            log.debug(f"[Prot] {sym} fetch orders failed: {_e}")
            _existing = []
        _prot = [o for o in _existing if _is_protective_order(o)]

        def _px(o):
            _info = o.get('info') or {}
            return float(
                o.get('stopPrice')
                or o.get('triggerPrice')
                or _info.get('stopPrice')
                or _info.get('triggerPrice')
                or 0
            )

        def _is_tp(o):
            # [CLASSIFIER-FIX] delegate to global helper
            return _is_tp_protective(o)

        _tick_sz = _get_tick_size(exchange, sym) or 0.0

        def _same_px(a, b):
            if b <= 0:
                return False
            _t_tol = max(1e-4, (_tick_sz / max(abs(b), 1e-9)) * 0.6)
            return abs(a - b) / max(abs(b), 1e-9) < _t_tol

        _ex_sl = None
        _ex_tp_full = None
        _ex_tp_partial = None
        _stale_ids = []

        for o in _prot:
            p = _px(o)
            if p <= 0:
                continue
            if _is_tp(o):
                if _partial_enabled and _same_px(p, _partial_price):
                    _ex_tp_partial = p
                elif _same_px(p, tp):
                    _ex_tp_full = p
                else:
                    _stale_ids.append(o['id'])
            else:
                if _same_px(p, sl):
                    _ex_sl = p
                else:
                    _stale_ids.append(o['id'])''',
        ),

        # ── 5. Snap partial & full TP quantities ────────────────────────
        (
            "_place_protective_orders partial/full qty precision",
            '''        # ══════════════════════════════════════════════════════════════
        # Partial TP — place only if enabled and missing
        # ══════════════════════════════════════════════════════════════
        _partial_qty = qty * _partial_pct if _partial_enabled else 0.0
        _full_qty = (qty * (1.0 - _partial_pct)
                     if _partial_enabled else qty)''',
            '''        # ══════════════════════════════════════════════════════════════
        # Partial TP — place only if enabled and missing
        # ══════════════════════════════════════════════════════════════
        _partial_qty = _snap_q(qty * _partial_pct) if _partial_enabled else 0.0
        _full_qty = (_snap_q(max(0.0, qty - _partial_qty))
                     if _partial_enabled else qty)
        if _partial_enabled and (_partial_qty <= 0 or _full_qty <= 0):
            _partial_enabled = False
            _partial_qty = 0.0
            _full_qty = qty''',
        ),

        # ── 6. Initialize peak_price in _lv_finalize_position ───────────
        (
            "_lv_finalize_position peak_price default",
            '''        if entry > 0:
            pos.setdefault('_hi', entry)
            pos.setdefault('_lo', entry)
            pos.setdefault('_last_sub_ts', 0)''',
            '''        if entry > 0:
            pos.setdefault('peak_price', entry)
            pos.setdefault('_hi', entry)
            pos.setdefault('_lo', entry)
            pos.setdefault('_last_sub_ts', 0)''',
        ),

        # ── 7. Strict post-entry 1m candle check in _lv_update_extremes ─
        (
            "_lv_update_extremes 1m post-entry filter",
            '''                t0 = float(pos.get('entry_ts') or now) // 60 * 60 * 1000
                for c in exchange.fetch_ohlcv(sym, '1m', limit=3) or []:
                    if float(c[0]) >= t0:
                        hi = max(hi, float(c[2]))
                        lo = min(lo, float(c[3]))''',
            '''                t0 = float(pos.get('entry_ts') or now) * 1000.0
                for c in exchange.fetch_ohlcv(sym, '1m', limit=3) or []:
                    if float(c[0]) > t0:
                        hi = max(hi, float(c[2]))
                        lo = min(lo, float(c[3]))''',
        ),

        # ── 8. Mark only startup-restored positions for C1 validation ───
        (
            "run_live startup C1 tagging",
            '''    # ══ [State] Initial reconciliation with exchange ══
    # [LV02] symbols=None -> full scan: positions on ANY symbol are found, adopted and protected
    open_pos_live = reconcile_state_machine(exchange, open_pos_live, None)
    log.info(f"  [State] After initial sync: {len(open_pos_live)} positions")''',
            '''    # ══ [State] Initial reconciliation with exchange ══
    # [LV02] symbols=None -> full scan: positions on ANY symbol are found, adopted and protected
    open_pos_live = reconcile_state_machine(exchange, open_pos_live, None)
    for _pos_init in open_pos_live.values():
        _pos_init['_needs_restart_c1'] = True
    _LV_STATE['_post_restart_validated'] = (len(open_pos_live) == 0)
    log.info(f"  [State] After initial sync: {len(open_pos_live)} positions")''',
        ),

        # ── 9. Fix [FIX-C1/C3] block in run_live ────────────────────────
        (
            "run_live FIX-C1/C3 safe post-entry reconstruction",
            '''            # [FIX-C1/C3] Post-restart validation (runs once per process)
            if not _LV_STATE.get('_post_restart_validated', False) and open_pos_live:
                _LV_STATE['_post_restart_validated'] = True
                for _sym_v, _pos_v in list(open_pos_live.items()):
                    _ad_v = assets.get(_sym_v)
                    if _ad_v is None:
                        continue
                    try:
                        _ci_old = int(_pos_v.get('_entry_ci', -1))
                        if _ci_old < 0 or _ci_old >= len(_ad_v.closes):
                            _ts_v = float(_pos_v.get('entry_ts', 0))
                            if _ts_v > 0:
                                _new_ci = int(np.searchsorted(
                                    _ad_v.timestamps.asi8,
                                    int(_ts_v * 1e9), side='right') - 1)
                                _new_ci = max(0, min(_new_ci, len(_ad_v.closes) - 1))
                            else:
                                _new_ci = max(0, len(_ad_v.closes) - 100)
                            _pos_v['_entry_ci'] = _new_ci
                            log.warning(f"[FIX-C3] {_sym_v} _entry_ci {_ci_old} -> {_new_ci}")
                            _ci_old = _new_ci
                        if _ci_old >= 0 and _ci_old < len(_ad_v.closes):
                            _action_v = str(_pos_v.get('action', 'BUY'))
                            _entry_v = float(_pos_v.get('entry', 0))
                            if _entry_v > 0:
                                if _action_v == 'BUY':
                                    _hi_r = float(np.max(_ad_v.highs[_ci_old:]))
                                    _lo_r = float(np.min(_ad_v.lows[_ci_old:]))
                                    _old_pk = float(_pos_v.get('peak_price', 0))
                                    _new_pk = max(_old_pk, _hi_r)
                                    if _new_pk > _old_pk:
                                        log.info(f"[FIX-C1] {_sym_v} peak {_old_pk:.6f} -> {_new_pk:.6f}")
                                        _pos_v['peak_price'] = _new_pk
                                    _pos_v['_hi'] = max(float(_pos_v.get('_hi', 0)), _hi_r)
                                    _pos_v['_lo'] = min(float(_pos_v.get('_lo', _entry_v)), _lo_r)
                                else:
                                    _lo_r = float(np.min(_ad_v.lows[_ci_old:]))
                                    _hi_r = float(np.max(_ad_v.highs[_ci_old:]))
                                    _old_pk = float(_pos_v.get('peak_price', 1e18))
                                    _new_pk = min(_old_pk, _lo_r)
                                    if _new_pk < _old_pk:
                                        log.info(f"[FIX-C1] {_sym_v} peak {_old_pk:.6f} -> {_new_pk:.6f}")
                                        _pos_v['peak_price'] = _new_pk
                                    _pos_v['_lo'] = min(float(_pos_v.get('_lo', 1e18)), _lo_r)
                                    _pos_v['_hi'] = max(float(_pos_v.get('_hi', _entry_v)), _hi_r)
                    except Exception as _e_v:
                        log.debug(f"[FIX-C1] {_sym_v} reconstruct failed: {_e_v}")''',
            '''            # [FIX-C1/C3] Post-restart validation (ONLY for startup-restored positions)
            for _sym_v, _pos_v in list(open_pos_live.items()):
                if not _pos_v.get('_needs_restart_c1', False):
                    continue
                _ad_v = assets.get(_sym_v)
                if _ad_v is None:
                    continue
                _pos_v.pop('_needs_restart_c1', None)
                try:
                    _ts_v = float(_pos_v.get('entry_ts', 0) or 0)
                    _entry_v = float(_pos_v.get('entry', 0) or 0)
                    if _ts_v <= 0 or _entry_v <= 0:
                        continue
                    _tidx_v = pd.DatetimeIndex(_ad_v.timestamps)
                    _t_entry_v = pd.Timestamp(_ts_v, unit='s', tz='UTC')
                    if _tidx_v.tz is None:
                        _t_entry_v = _t_entry_v.tz_localize(None)
                    # Strictly bars that opened AFTER entry_ts (never pre-entry candles)
                    _post_ci = int(_tidx_v.searchsorted(_t_entry_v, side='right'))
                    _ci_old = int(_pos_v.get('_entry_ci', -1))
                    _entry_bar_ci = max(0, min(_post_ci - 1, len(_ad_v.closes) - 1))
                    if _ci_old < 0 or _ci_old >= len(_ad_v.closes):
                        _pos_v['_entry_ci'] = _entry_bar_ci
                        log.warning(f"[FIX-C3] {_sym_v} _entry_ci {_ci_old} -> {_entry_bar_ci}")
                    if _post_ci < len(_ad_v.closes):
                        _action_v = str(_pos_v.get('action', 'BUY'))
                        _hi_r = float(np.max(_ad_v.highs[_post_ci:]))
                        _lo_r = float(np.min(_ad_v.lows[_post_ci:]))
                        if _action_v == 'BUY':
                            _old_pk = float(_pos_v.get('peak_price') or _entry_v)
                            _new_pk = max(_old_pk, _hi_r)
                            if _new_pk > _old_pk:
                                log.info(f"[FIX-C1] {_sym_v} peak {_old_pk:.6f} -> {_new_pk:.6f}")
                                _pos_v['peak_price'] = _new_pk
                            _pos_v['_hi'] = max(float(_pos_v.get('_hi') or _entry_v), _hi_r)
                            _pos_v['_lo'] = min(float(_pos_v.get('_lo') or _entry_v), _lo_r)
                        else:
                            _old_pk = float(_pos_v.get('peak_price') or _entry_v)
                            _new_pk = min(_old_pk, _lo_r)
                            if _new_pk < _old_pk:
                                log.info(f"[FIX-C1] {_sym_v} peak {_old_pk:.6f} -> {_new_pk:.6f}")
                                _pos_v['peak_price'] = _new_pk
                            _pos_v['_lo'] = min(float(_pos_v.get('_lo') or _entry_v), _lo_r)
                            _pos_v['_hi'] = max(float(_pos_v.get('_hi') or _entry_v), _hi_r)
                except Exception as _e_v:
                    log.debug(f"[FIX-C1] {_sym_v} reconstruct failed: {_e_v}")''',
        ),
    ]

    # Verify every hunk matches EXACTLY once before mutating anything
    for name, old, _ in replacements:
        cnt = src.count(old)
        if cnt != 1:
            print(
                f"[ERROR] Hunk '{name}' matched {cnt} times (expected 1). "
                f"Aborting without modifying {target_path}.",
                file=sys.stderr,
            )
            sys.exit(2)

    patched = src
    for name, old, new in replacements:
        patched = patched.replace(old, new, 1)
        print(f"[PATCH] Applied: {name}")

    if dry_run:
        print("[DRY-RUN] All hunks matched cleanly. No files were modified.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{target_path}.bak_{ts}"
    shutil.copy2(target_path, backup_path)
    print(f"[BACKUP] Created: {backup_path}")

    tmp_path = f"{target_path}.patched.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(patched)
        # Verify Python syntax before replacing target
        py_compile.compile(tmp_path, doraise=True)
        os.replace(tmp_path, target_path)
        print(f"[SUCCESS] Patched & syntax-verified: {target_path}")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"[ERROR] Verification failed, original file untouched: {e}", file=sys.stderr)
        sys.exit(3)


def main():
    parser = argparse.ArgumentParser(description="Patch trading_published_pro_1h_fixed.py live protection & trailing bugs")
    parser.add_argument("--target", default="trading_published_pro_1h_fixed.py", help="Path to target script")
    parser.add_argument("--dry-run", action="store_true", help="Verify matches without modifying file")
    args = parser.parse_args()
    apply_patch(args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
