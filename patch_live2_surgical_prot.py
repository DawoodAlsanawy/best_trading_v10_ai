#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_live2_surgical_prot.py                                            ║
║  Replace _place_protective_orders with surgical (per-leg) logic         ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Why:                                                                    ║
║    P11 (previous patch) only detected partial protection but did        ║
║    not change placement. The existing code still calls the wholesale    ║
║    cancel + re-place of all legs, which causes SL stacking when the     ║
║    SL is a closePosition order that fetch_open_orders cannot see.      ║
║                                                                          ║
║  Fix:                                                                    ║
║    Rewrite the body of _place_protective_orders:                        ║
║      * Detect existing SL / partial-TP / full-TP by their prices       ║
║      * Cancel ONLY the legs whose prices differ from the targets       ║
║      * Place ONLY the legs that are missing                             ║
║      * Never cancel a leg that's already at the right price             ║
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
# The full replacement function
# ══════════════════════════════════════════════════════════════════════════

NEW_FUNC = '''def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:
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

        # ── Cancel ONLY the stale legs ──
        for _oid in _stale_ids:
            _done = False
            for _prm in ({'trigger': True}, {}):
                try:
                    exchange.cancel_order(_oid, sym, params=_prm)
                    _done = True
                    break
                except Exception as _ce:
                    _m = str(_ce).lower()
                    if '-2011' in _m or 'unknown order' in _m:
                        _done = True
                        break
            if not _done:
                log.warning(f"[Prot] {sym} stale cancel oid={_oid} failed")
        if _stale_ids:
            log.info(f"[Prot] {sym} cancelled {len(_stale_ids)} stale "
                     f"protective order(s) before placement")
            time.sleep(0.4)

        # ── Early return if everything is already in place ──
        if (_ex_sl is not None
                and _ex_tp_full is not None
                and (not _partial_enabled or _ex_tp_partial is not None)):
            log.debug(f"[Prot] {sym} all legs present -- no action")
            pos['_broker_partial'] = bool(_ex_tp_partial is not None)
            return True

        placed = {
            'sl': _ex_sl is not None,
            'tp': _ex_tp_full is not None,
            'partial_tp': _ex_tp_partial is not None,
        }

        # ══════════════════════════════════════════════════════════════
        # SL — place only if missing
        # ══════════════════════════════════════════════════════════════
        if not placed['sl']:
            for attempt in range(max_retries):
                try:
                    exchange.create_order(
                        sym, 'STOP_MARKET', close_side, None, None,
                        params={'stopPrice': sl,
                                'closePosition': True,
                                'workingType': wt})
                    placed['sl'] = True
                    log.info(f"[Prot] {sym} SL placed @ {sl:.6f} "
                             f"(closePosition)")
                    break
                except Exception as e:
                    log.debug(f"[Prot] {sym} SL closePosition "
                              f"attempt {attempt+1} failed: {e}")
                    try:
                        exchange.create_order(
                            sym, 'STOP_MARKET', close_side, qty, None,
                            params={'stopPrice': sl,
                                    'reduceOnly': True,
                                    'workingType': wt})
                        placed['sl'] = True
                        log.info(f"[Prot] {sym} SL placed @ {sl:.6f} "
                                 f"(reduceOnly)")
                        break
                    except Exception as e2:
                        log.debug(f"[Prot] {sym} SL reduceOnly "
                                  f"attempt {attempt+1} failed: {e2}")
        else:
            log.debug(f"[Prot] {sym} SL already present @ "
                      f"{_ex_sl:.6f} -- kept")

        # ══════════════════════════════════════════════════════════════
        # Partial TP — place only if enabled and missing
        # ══════════════════════════════════════════════════════════════
        _partial_qty = qty * _partial_pct if _partial_enabled else 0.0
        _full_qty = (qty * (1.0 - _partial_pct)
                     if _partial_enabled else qty)

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
                             f"{_partial_price:.6f} qty={_partial_qty:.6f} "
                             f"({_partial_pct*100:.0f}%)")
                    break
                except Exception as e:
                    log.debug(f"[Prot] {sym} partial-TP attempt "
                              f"{attempt+1} failed: {e}")
            if not placed['partial_tp']:
                log.warning(f"[Prot] {sym} partial-TP rejected -- "
                            f"falling back to full-qty TP only")
                _partial_enabled = False
        elif _partial_enabled and placed['partial_tp']:
            log.debug(f"[Prot] {sym} PARTIAL-TP already present @ "
                      f"{_ex_tp_partial:.6f} -- kept")

        pos['_broker_partial'] = bool(placed['partial_tp'])

        # ══════════════════════════════════════════════════════════════
        # Full TP — place only if missing
        # ══════════════════════════════════════════════════════════════
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
                    log.info(f"[Prot] {sym} FULL-TP placed @ {tp:.6f} "
                             f"({'closePosition' if _tp_close_pos else 'reduceOnly'})")
                    break
                except Exception as e:
                    log.debug(f"[Prot] {sym} full-TP attempt "
                              f"{attempt+1} failed: {e}")
        else:
            log.debug(f"[Prot] {sym} FULL-TP already present @ "
                      f"{_ex_tp_full:.6f} -- kept")

        _ok = (placed['sl'] and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if _ok:
            return True
        log.warning(f"[Prot] {sym} incomplete: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return _ok
    except Exception as e:
        log.warning(f"[Prot] {sym} place_protective_orders fatal: {e}")
        return False

'''


# ══════════════════════════════════════════════════════════════════════════
# Patcher that swaps the function
# ══════════════════════════════════════════════════════════════════════════

class Patcher:
    def __init__(self, path: Path, dry_run: bool = False):
        self.path = path
        self.dry_run = dry_run
        self.content = None
        self.backup_path = None

    def load(self) -> bool:
        if not self.path.exists():
            print(f"{C.RED}  Not found: {self.path}{C.END}")
            return False
        self.content = self.path.read_text(encoding='utf-8')
        print(f"{C.CYAN}  Loaded {self.path.name} "
              f"({len(self.content):,} bytes){C.END}")
        return True

    def backup(self) -> bool:
        if self.dry_run:
            return True
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = self.path.with_suffix(
            self.path.suffix + f'.bak.{ts}')
        shutil.copy2(self.path, self.backup_path)
        print(f"{C.CYAN}  Backup: {self.backup_path.name}{C.END}")
        return True

    def replace_function(self, name: str,
                         start_marker: str,
                         end_marker: str,
                         new_body: str) -> bool:
        # Already applied?
        if "[SURGICAL-PLACEMENT]" in self.content:
            print(f"  {C.GRAY}○ SKIP{C.END}  {name} "
                  f"{C.GRAY}(already applied){C.END}")
            return True

        s = self.content.find(start_marker)
        if s < 0:
            print(f"  {C.RED}✗ FAIL{C.END}  {name} "
                  f"{C.GRAY}(start not found){C.END}")
            return False
        e = self.content.find(end_marker, s + len(start_marker))
        if e < 0:
            print(f"  {C.RED}✗ FAIL{C.END}  {name} "
                  f"{C.GRAY}(end not found){C.END}")
            return False

        old_len = e - s
        self.content = self.content[:s] + new_body + self.content[e:]
        print(f"  {C.GREEN}✓ OK{C.END}    {name} "
              f"(replaced {old_len} chars)")
        return True

    def save(self) -> bool:
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
        self.path.write_text(self.content, encoding='utf-8')
        print(f"{C.GREEN}  Written {self.path.name} "
              f"({len(self.content):,} bytes){C.END}")
        return True


def restore_latest(path: Path) -> bool:
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
    p.add_argument("--bot", default="trading_2_live2.py")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.BOLD}  Surgical-Protection Patcher -- {bot.name}{C.END}")
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
    ok = pt.replace_function(
        "Replace _place_protective_orders",
        start_marker="def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:",
        end_marker="def _sync_protective_orders(exchange, sym: str, pos: Dict) -> bool:",
        new_body=NEW_FUNC,
    )

    if not ok:
        sys.exit(4)
    if not pt.save():
        sys.exit(5)

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.GREEN}  SURGICAL-PLACEMENT APPLIED SUCCESSFULLY{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if not args.dry_run:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify:  python3 -m py_compile {bot.name}")
        print(f"  2. Grep:    grep -n 'SURGICAL-PLACEMENT' {bot.name}")
        print(f"  3. Clean existing duplicates on Binance (manual):")
        print(f"     - Open Futures -> Open Orders")
        print(f"     - For each symbol, keep ONE SL and ONE TP, cancel extras")
        print(f"  4. Run bot. New logs to look for:")
        print(f"     {C.BOLD}[Prot] X SL@... already present -- kept{C.END}")
        print(f"     {C.BOLD}[Prot] X FULL-TP already present -- kept{C.END}")
        print(f"     {C.BOLD}[Prot] X cancelled N stale protective order(s){C.END}")
        print(f"  5. Revert:  python3 {Path(__file__).name} --restore")


if __name__ == "__main__":
    main()
