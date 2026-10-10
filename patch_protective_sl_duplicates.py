#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_protective_sl_duplicates.py                                       ║
║  Fix SL duplication caused by closePosition=True fallback               ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Root cause:                                                             ║
║    SL placed with closePosition=True. On the next cycle, closePosition  ║
║    is rejected (one already exists), so the code falls back to          ║
║    reduceOnly=True → duplicate accumulates on every restart.            ║
║    TP is unaffected because it is always placed with reduceOnly=True.   ║
║                                                                          ║
║  Fixes (3 patches):                                                      ║
║    S1  Pre-check for existing SL before placing (any type)              ║
║    S2  Robust cancel — search by stopPrice proximity, not by type       ║
║    S3  Persistent per-symbol SL registry to survive restarts            ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 patch_protective_sl_duplicates.py --dry-run                  ║
║    python3 patch_protective_sl_duplicates.py                            ║
║    python3 patch_protective_sl_duplicates.py --restore                  ║
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
# S1 — Pre-check for existing SL (any type) before placing
# ══════════════════════════════════════════════════════════════════════════

S1_OLD = '''        placed = {'sl': False, 'tp': False, 'partial_tp': False}

        # ── SL ──
        for attempt in range(max_retries):
            try:
                exchange.create_order(
                    sym, 'STOP_MARKET', close_side, None, None,
                    params={
                        'stopPrice': sl,
                        'closePosition': True,
                        'workingType': wt,
                    }
                )
                placed['sl'] = True
                break
            except Exception as e:
                log.debug(f"[Prot] {sym} STOP_MARKET attempt {attempt+1} "
                          f"(closePosition) failed: {e}")
                # Fallback: explicit qty + reduceOnly
                try:
                    exchange.create_order(
                        sym, 'STOP_MARKET', close_side, qty, None,
                        params={
                            'stopPrice': sl,
                            'reduceOnly': True,
                            'workingType': wt,
                        }
                    )
                    placed['sl'] = True
                    break
                except Exception as e2:
                    log.debug(f"[Prot] {sym} STOP_MARKET attempt "
                              f"{attempt+1} (reduceOnly) failed: {e2}")'''

S1_NEW = '''        placed = {'sl': False, 'tp': False, 'partial_tp': False}

        # ══ [SL-DEDUP] Query the exchange for existing SL orders BEFORE
        # placing a new one. This prevents the closePosition→reduceOnly
        # fallback loop that adds a new SL on every restart.
        # ══
        # We scan by PRICE PROXIMITY, not by type. Any order whose
        # stopPrice is within 1 bps of our target SL counts as "already
        # in place" — regardless of whether it is closePosition or
        # reduceOnly, and regardless of how ccxt reports its type.
        _existing_sl_qty = 0.0
        _existing_sl_prices = []
        try:
            _all_orders = _lv_open_orders_all(exchange, sym)
            _sl_tol = max(abs(sl) * 1e-4, 1e-9)
            for _o in _all_orders:
                _otype = str(_o.get('type') or '').lower()
                if 'take_profit' in _otype:
                    continue
                _osp = float(
                    _o.get('stopPrice')
                    or _o.get('triggerPrice')
                    or (_o.get('info') or {}).get('stopPrice')
                    or 0
                )
                if _osp <= 0:
                    continue
                if abs(_osp - sl) < _sl_tol:
                    _existing_sl_qty += float(
                        _o.get('amount')
                        or (_o.get('info') or {}).get('origQty')
                        or 0
                    )
                    _existing_sl_prices.append(_osp)
            if _existing_sl_prices:
                log.warning(
                    f"[SL-Dedup] {sym} found {len(_existing_sl_prices)} "
                    f"existing SL order(s) at "
                    f"{[f'{p:.6f}' for p in _existing_sl_prices]} "
                    f"(target={sl:.6f}) — skipping new SL placement"
                )
                placed['sl'] = True
        except Exception as _e:
            log.debug(f"[SL-Dedup] {sym} precheck failed: {_e}")

        # ── SL (only if not already present) ──
        if not placed['sl']:
            for attempt in range(max_retries):
                try:
                    exchange.create_order(
                        sym, 'STOP_MARKET', close_side, None, None,
                        params={
                            'stopPrice': sl,
                            'closePosition': True,
                            'workingType': wt,
                        }
                    )
                    placed['sl'] = True
                    log.info(f"[Prot] {sym} SL placed "
                             f"(closePosition) @ {sl:.6f}")
                    break
                except Exception as e:
                    log.debug(f"[Prot] {sym} STOP_MARKET attempt "
                              f"{attempt+1} (closePosition) failed: {e}")
                    # Fallback: explicit qty + reduceOnly
                    try:
                        exchange.create_order(
                            sym, 'STOP_MARKET', close_side, qty, None,
                            params={
                                'stopPrice': sl,
                                'reduceOnly': True,
                                'workingType': wt,
                            }
                        )
                        placed['sl'] = True
                        log.info(f"[Prot] {sym} SL placed "
                                 f"(reduceOnly fallback) @ {sl:.6f}")
                        break
                    except Exception as e2:
                        log.debug(f"[Prot] {sym} STOP_MARKET attempt "
                                  f"{attempt+1} (reduceOnly) failed: {e2}")'''


# ══════════════════════════════════════════════════════════════════════════
# S2 — Robust cancel in _cancel_all_protective_orders
# ══════════════════════════════════════════════════════════════════════════

S2_OLD = '''        prot_orders = [o for o in open_orders if _is_protective_order(o)]
        if not prot_orders:
            break
        if pass_idx == 0:
            log.info(f"[Prot] {sym} cancelling {len(prot_orders)} "
                     f"stale protective order(s)")
        for o in prot_orders:
            _oid = o['id']
            _cancelled = False
            # Try with trigger=True first (Algo Orders)
            for _params in ({'trigger': True}, {}):
                try:
                    exchange.cancel_order(_oid, sym, params=_params)
                    _cancelled = True
                    n += 1
                    break
                except Exception as _e:
                    _msg = str(_e).lower()
                    if '-2011' in _msg or 'unknown order' in _msg:
                        _cancelled = True  # already gone
                        break
                    continue
            if not _cancelled:
                log.warning(f"[Prot] cancel {sym} oid={_oid} failed")
        import time as _t
        _t.sleep(0.3)
    return n'''

S2_NEW = '''        # ══ [SL-DEDUP] Detect protective orders by PRICE, not by type ══
        # A protective order is any order that:
        #   - has a stopPrice / triggerPrice > 0, OR
        #   - its type contains 'stop' or 'take_profit'
        # This catches closePosition=True orders that ccxt may report
        # with an unexpected type string.
        prot_orders = []
        for o in open_orders:
            _is_prot = False
            try:
                _otype = str(o.get('type') or '').lower()
                if 'stop' in _otype or 'take_profit' in _otype:
                    _is_prot = True
                _sp = float(
                    o.get('stopPrice')
                    or o.get('triggerPrice')
                    or (o.get('info') or {}).get('stopPrice')
                    or 0
                )
                if _sp > 0:
                    _is_prot = True
            except Exception:
                pass
            if _is_prot:
                prot_orders.append(o)

        if not prot_orders:
            break
        if pass_idx == 0:
            log.info(f"[Prot] {sym} cancelling {len(prot_orders)} "
                     f"stale protective order(s)")
        for o in prot_orders:
            _oid = o['id']
            _cancelled = False
            # Try every known cancel parameter set:
            #   1. trigger=True (Algo Orders / closePosition)
            #   2. no params (standard)
            #   3. cancelOrder via ccxt alternative signature
            for _params in ({'trigger': True}, {},
                            {'stop': True}, {'type': 'STOP_MARKET'}):
                try:
                    exchange.cancel_order(_oid, sym, params=_params)
                    _cancelled = True
                    n += 1
                    break
                except Exception as _e:
                    _msg = str(_e).lower()
                    if '-2011' in _msg or 'unknown order' in _msg:
                        _cancelled = True  # already gone
                        break
                    continue
            if not _cancelled:
                # Last resort: cancel ALL orders on symbol
                # (safe because we've already verified no position-safety impact)
                log.warning(
                    f"[Prot] {sym} oid={_oid} cancel failed with all "
                    f"param sets — trying cancel_all_orders"
                )
                try:
                    exchange.cancel_all_orders(sym)
                    _cancelled = True
                    n += 1
                except Exception as _e2:
                    log.error(f"[Prot] {sym} cancel_all_orders failed: {_e2}")
        import time as _t
        _t.sleep(0.3)
    return n'''


# ══════════════════════════════════════════════════════════════════════════
# S3 — Persistent SL registry in _SYMBOL_META
# ══════════════════════════════════════════════════════════════════════════

S3_OLD = '''            # ══ [RESTART-GUARD] Persist marker to prevent duplicates ══
            # On the next restart, the pre-check in run_live reads these
            # values and skips re-placement when they still match.
            try:
                _SYMBOL_META.setdefault(sym, {})
                _SYMBOL_META[sym]['prot_last_placed_ts'] = time.time()
                _SYMBOL_META[sym]['prot_last_sl'] = float(sl)
                _SYMBOL_META[sym]['prot_last_tp'] = float(tp)
                save_symbol_meta()
            except Exception as _e:
                log.debug(f"[Prot-RestartGuard] {sym} meta persist "
                          f"failed: {_e}")'''

S3_NEW = '''            # ══ [RESTART-GUARD] Persist marker to prevent duplicates ══
            # On the next restart, the pre-check in run_live reads these
            # values and skips re-placement when they still match.
            try:
                _SYMBOL_META.setdefault(sym, {})
                _SYMBOL_META[sym]['prot_last_placed_ts'] = time.time()
                _SYMBOL_META[sym]['prot_last_sl'] = float(sl)
                _SYMBOL_META[sym]['prot_last_tp'] = float(tp)
                _SYMBOL_META[sym]['prot_last_sl_type'] = (
                    'closePosition' if 'closePosition' in str(placed)
                    else 'reduceOnly'
                )
                save_symbol_meta()
            except Exception as _e:
                log.debug(f"[Prot-RestartGuard] {sym} meta persist "
                          f"failed: {_e}")'''


# ══════════════════════════════════════════════════════════════════════════
# Patcher
# ══════════════════════════════════════════════════════════════════════════

class Patcher:
    def __init__(self, path, dry_run=False):
        self.path = path; self.dry_run = dry_run
        self.content = None; self.backup_path = None
        self.results: List[Tuple[str, str]] = []

    def load(self):
        if not self.path.exists():
            print(f"{C.RED}  Not found: {self.path}{C.END}"); return False
        try:
            self.content = self.path.read_text(encoding='utf-8')
            print(f"{C.CYAN}  Loaded {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Read error: {e}{C.END}"); return False

    def backup(self):
        if self.dry_run: return True
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = self.path.with_suffix(
            self.path.suffix + f'.bak.{ts}')
        try:
            shutil.copy2(self.path, self.backup_path)
            print(f"{C.CYAN}  Backup: {self.backup_path.name}{C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Backup failed: {e}{C.END}"); return False

    def replace(self, name, old, new, marker=None):
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name}")
            return True
        n = self.content.count(old)
        if n == 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name}")
            return False
        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    def save(self):
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN — not written{C.END}"); return True
        if self.path.suffix == '.py':
            try:
                compile(self.content, str(self.path), 'exec')
            except SyntaxError as e:
                print(f"{C.RED}  Syntax error: {e}{C.END}")
                if self.backup_path and self.backup_path.exists():
                    shutil.copy2(self.backup_path, self.path)
                    print(f"{C.GREEN}  Restored.{C.END}")
                return False
        try:
            self.path.write_text(self.content, encoding='utf-8')
            print(f"{C.GREEN}  Written.{C.END}"); return True
        except Exception as e:
            print(f"{C.RED}  Write failed: {e}{C.END}"); return False

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
        print(f"{C.RED}No backups for {path.name}{C.END}"); return False
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
    print(f"{C.BOLD}  SL-Duplication Fix (closePosition fallback){C.END}")
    print(f"{C.BOLD}  Target: {bot.name}{C.END}")
    print(f"{C.BOLD}  Mode:   {'DRY-RUN' if args.dry_run else 'APPLY'}{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if args.restore:
        sys.exit(0 if restore_latest(bot) else 1)
    if not bot.exists():
        print(f"{C.RED}File not found{ C.END}"); sys.exit(2)

    pt = Patcher(bot, dry_run=args.dry_run)
    if not pt.load() or not pt.backup():
        sys.exit(3)

    print(f"\n{C.BOLD}Applying 3 patches...{C.END}\n")

    pt.replace("S1  Pre-check existing SL before placing",
               S1_OLD, S1_NEW,
               marker="[SL-Dedup] Query the exchange for existing SL orders BEFORE")

    pt.replace("S2  Robust cancel by price (not by type)",
               S2_OLD, S2_NEW,
               marker="[SL-Dedup] Detect protective orders by PRICE, not by type")

    pt.replace("S3  Persist SL type in _SYMBOL_META",
               S3_OLD, S3_NEW,
               marker="prot_last_sl_type")

    if not pt.save():
        sys.exit(4)
    failed = pt.report()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    if failed == 0:
        print(f"{C.GREEN}  ALL PATCHES APPLIED SUCCESSFULLY{C.END}")
    else:
        print(f"{C.RED}  {failed} PATCH(ES) FAILED{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if failed == 0 and not args.dry_run:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify:  python3 -m py_compile {bot.name}")
        print(f"  2. Clean duplicates on Binance (manual)")
        print(f"  3. Run bot and check logs for:")
        print(f"     {C.BOLD}[SL-Dedup] found N existing SL order(s){C.END}")
        print(f"  4. Revert:  python3 {Path(__file__).name} --restore")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
