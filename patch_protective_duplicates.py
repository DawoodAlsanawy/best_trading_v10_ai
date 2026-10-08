#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_protective_duplicates.py                                          ║
║  Fix protective-order duplication bug in trading_2_live2.py              ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Root cause:                                                             ║
║    exchange.fetch_open_orders(sym) does NOT return STOP_MARKET /         ║
║    TAKE_PROFIT_MARKET on Binance Futures (Algo Order migration).         ║
║    Bot assumed "no orders exist" -> placed duplicates on every restart. ║
║                                                                          ║
║  Fixes (6 patches):                                                      ║
║    P1  _cancel_all_protective_orders uses _lv_open_orders_all            ║
║    P2  Pre-flight idempotency check in _place_protective_orders          ║
║    P3  Persist SL/TP + timestamp marker in _SYMBOL_META                  ║
║    P4a Restart-guard pre-check in run_live (compare meta vs position)    ║
║    P4b Skip-in-loop for positions flagged by restart-guard               ║
║    P5  Verify-cancel uses _lv_open_orders_all (defensive)                ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 patch_protective_duplicates.py                   # apply      ║
║    python3 patch_protective_duplicates.py --dry-run         # preview    ║
║    python3 patch_protective_duplicates.py --bot PATH        # custom     ║
║    python3 patch_protective_duplicates.py --restore         # rollback   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    END = '\033[0m'


# ══════════════════════════════════════════════════════════════════════════
# P1 — Rewrite _cancel_all_protective_orders
# ══════════════════════════════════════════════════════════════════════════

P1_OLD = '''def _cancel_all_protective_orders(exchange, sym: str,
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

P1_NEW = '''def _cancel_all_protective_orders(exchange, sym: str,
                                     max_passes: int = 2) -> int:
    """
    Cancel every STOP_MARKET / TAKE_PROFIT_MARKET on the symbol.

    [ccxt 4.x FIX] Uses _lv_open_orders_all() which queries BOTH the
    standard endpoint AND params={'trigger': True}. Before the fix,
    plain fetch_open_orders returned [] for conditional orders on
    Binance Futures (Algo Order service migration) -> the bot thought
    no protective orders existed -> placed DUPLICATES on every restart.

    Cancel is attempted with params={'trigger': True} first (Algo Order
    service) and falls back to no-params for other ccxt versions.
    """
    n = 0
    for pass_idx in range(max_passes):
        try:
            open_orders = _lv_open_orders_all(exchange, sym)
        except Exception:
            # Fallback: at least try the standard endpoint
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


# ══════════════════════════════════════════════════════════════════════════
# P2 — Insert idempotency pre-flight in _place_protective_orders
# ══════════════════════════════════════════════════════════════════════════

P2_OLD = '''        close_side = 'sell' if action == 'BUY' else 'buy'
        wt = str(getattr(CFG, 'PROTECTIVE_WORKING_TYPE', 'MARK_PRICE'))
        max_retries = int(getattr(CFG, 'PROTECTIVE_MAX_RETRIES', 2))

        # Cancel any stale protective orders first (idempotent)
        # [DUPLICATE-FIX] verify cancel before placing
        _canceled_count = _cancel_all_protective_orders(exchange, sym)'''

P2_NEW = '''        close_side = 'sell' if action == 'BUY' else 'buy'
        wt = str(getattr(CFG, 'PROTECTIVE_WORKING_TYPE', 'MARK_PRICE'))
        max_retries = int(getattr(CFG, 'PROTECTIVE_MAX_RETRIES', 2))

        # ══ [RESTART-GUARD] Idempotency pre-flight ══
        # Ask the exchange FIRST whether matching SL/TP already exist.
        # This is the primary defense against the duplicate-order bug:
        # on restart, _prot_last_sl is None (fresh dict from JSON), so
        # the bot would re-place orders that are already on the broker.
        try:
            _existing = _lv_open_orders_all(exchange, sym)
            _existing_prot = [o for o in _existing
                              if _is_protective_order(o)]
            if _existing_prot:
                _sl_match = False
                _tp_match = False
                for o in _existing_prot:
                    _otype = str(o.get('type') or '').lower()
                    _ostop = float(
                        o.get('stopPrice')
                        or o.get('triggerPrice')
                        or (o.get('info') or {}).get('stopPrice')
                        or 0
                    )
                    if _ostop <= 0:
                        continue
                    _tol = max(abs(sl) * 1e-4, 1e-9)
                    if 'stop_market' in _otype and abs(_ostop - sl) < _tol:
                        _sl_match = True
                    if 'take_profit' in _otype and abs(_ostop - tp) < _tol:
                        _tp_match = True
                if _sl_match and _tp_match:
                    log.info(
                        f"[Prot-RestartGuard] {sym} matching SL/TP "
                        f"already exist (sl~{sl:.6f}, tp~{tp:.6f}) "
                        f"-- skipping re-placement"
                    )
                    # Persist the marker so future restarts also skip
                    try:
                        _SYMBOL_META.setdefault(sym, {})
                        _SYMBOL_META[sym]['prot_last_placed_ts'] = time.time()
                        _SYMBOL_META[sym]['prot_last_sl'] = float(sl)
                        _SYMBOL_META[sym]['prot_last_tp'] = float(tp)
                        save_symbol_meta()
                    except Exception:
                        pass
                    return True
        except Exception as _e:
            log.debug(f"[Prot-RestartGuard] {sym} preflight failed: {_e}")

        # Cancel any stale protective orders first (idempotent)
        # [DUPLICATE-FIX] verify cancel before placing
        _canceled_count = _cancel_all_protective_orders(exchange, sym)'''


# ══════════════════════════════════════════════════════════════════════════
# P3 — Persist restart-guard marker after successful placement
# ══════════════════════════════════════════════════════════════════════════

P3_OLD = '''        if placed['sl'] and placed['tp'] and _partial_ok:
            if _partial_enabled:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"PARTIAL-TP@{_partial_price:.6f} "
                         f"FULL-TP@{tp:.6f} placed")
            else:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"TP@{tp:.6f} placed")
            return True'''

P3_NEW = '''        if placed['sl'] and placed['tp'] and _partial_ok:
            # ══ [RESTART-GUARD] Persist marker to prevent duplicates ══
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
                          f"failed: {_e}")

            if _partial_enabled:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"PARTIAL-TP@{_partial_price:.6f} "
                         f"FULL-TP@{tp:.6f} placed")
            else:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"TP@{tp:.6f} placed")
            return True'''


# ══════════════════════════════════════════════════════════════════════════
# P4a — Insert restart-guard pre-check in run_live
# ══════════════════════════════════════════════════════════════════════════

P4A_ANCHOR = '''    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        _prot_ok = 0
        _prot_fail = 0
        _prot_deferred = 0
        _prot_dropped_pending = 0'''

P4A_REPLACEMENT = '''    # ══ [RESTART-GUARD] Pre-check: compare _SYMBOL_META marker vs position ══
    # When the bot restarts, open_pos_live is loaded from JSON with
    # _prot_last_sl = None (the field was never persisted). This makes
    # the LAYER-7 loop below think "no protection exists" and re-place
    # orders that are STILL on the broker from the previous session.
    #
    # This pre-check reads the persistent marker written by
    # _place_protective_orders on success, and marks positions whose
    # SL/TP still match. The LAYER-7 loop then skips them.
    _restart_guard_skip = 0
    _restart_guard_place = 0
    for _sym_p, _pos_p in list(open_pos_live.items()):
        _meta_p = _SYMBOL_META.get(_sym_p, {})
        _meta_sl = float(_meta_p.get('prot_last_sl') or 0)
        _meta_tp = float(_meta_p.get('prot_last_tp') or 0)
        _meta_ts = float(_meta_p.get('prot_last_placed_ts') or 0)
        _cur_sl = float(_pos_p.get('sl') or 0)
        _cur_tp = float(_pos_p.get('tp1') or 0)
        _age_h = (time.time() - _meta_ts) / 3600.0 if _meta_ts > 0 else 999.0

        _sl_ok = (_meta_sl > 0 and _cur_sl > 0
                  and abs(_meta_sl - _cur_sl) / max(abs(_cur_sl), 1e-9) < 1e-3)
        _tp_ok = (_meta_tp > 0 and _cur_tp > 0
                  and abs(_meta_tp - _cur_tp) / max(abs(_cur_tp), 1e-9) < 1e-3)
        if _sl_ok and _tp_ok and _age_h < 168:
            _pos_p['_prot_last_sl'] = _cur_sl
            _pos_p['_prot_last_tp'] = _cur_tp
            _restart_guard_skip += 1
        else:
            _restart_guard_place += 1
    if _restart_guard_skip > 0 or _restart_guard_place > 0:
        log.info(f"  [Prot-RestartGuard] skip={_restart_guard_skip} "
                 f"will_place={_restart_guard_place}")

    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        _prot_ok = 0
        _prot_fail = 0
        _prot_deferred = 0
        _prot_dropped_pending = 0'''


# ══════════════════════════════════════════════════════════════════════════
# P4b — Add skip-check inside the LAYER-7 loop
# ══════════════════════════════════════════════════════════════════════════

P4B_OLD = '''        for _sym_p, _pos_p in list(open_pos_live.items()):
            _pending_rec = _PENDING_ORDERS.get(_sym_p)
            if _pending_rec is not None:'''

P4B_NEW = '''        for _sym_p, _pos_p in list(open_pos_live.items()):
            # [RESTART-GUARD] Skip if pre-check marked this position
            if (_pos_p.get('_prot_last_sl') is not None
                    and _pos_p.get('_prot_last_tp') is not None):
                log.info(f"  [Prot] {_sym_p} skip re-placement "
                         f"(restart-guard: sl={_pos_p['_prot_last_sl']:.6f}, "
                         f"tp={_pos_p['_prot_last_tp']:.6f})")
                _prot_ok += 1
                continue

            _pending_rec = _PENDING_ORDERS.get(_sym_p)
            if _pending_rec is not None:'''


# ══════════════════════════════════════════════════════════════════════════
# P5 — Verify-cancel block uses _lv_open_orders_all
# ══════════════════════════════════════════════════════════════════════════

P5_OLD = '''        time.sleep(0.5)
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
            log.debug(f"[Prot] verify cancel for {sym} failed: {_e}")'''

P5_NEW = '''        time.sleep(0.5)
        try:
            # [ccxt 4.x FIX] Use _lv_open_orders_all to include
            # conditional orders (Algo Order service on Binance).
            _remaining = [o for o in _lv_open_orders_all(exchange, sym)
                          if _is_protective_order(o)]
            if _remaining:
                log.warning(
                    f"[Prot] {sym} {len(_remaining)} protective "
                    f"order(s) still open after cancel — retrying"
                )
                _cancel_all_protective_orders(exchange, sym)
                time.sleep(0.5)
        except Exception as _e:
            log.debug(f"[Prot] verify cancel for {sym} failed: {_e}")'''


# ══════════════════════════════════════════════════════════════════════════
# Patcher
# ══════════════════════════════════════════════════════════════════════════

class Patcher:
    def __init__(self, path: Path, dry_run: bool = False):
        self.path = path
        self.dry_run = dry_run
        self.content = None
        self.backup_path = None
        self.results: List[Tuple[str, str]] = []

    def load(self) -> bool:
        if not self.path.exists():
            print(f"{C.RED}  File not found: {self.path}{C.END}")
            return False
        try:
            self.content = self.path.read_text(encoding='utf-8')
            print(f"{C.CYAN}  Loaded {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Cannot read: {e}{C.END}")
            return False

    def backup(self) -> bool:
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

    def replace(self, name: str, old: str, new: str,
                marker: str = None) -> bool:
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name} "
                  f"{C.GRAY}(already applied){C.END}")
            return True
        n = self.content.count(old)
        if n == 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} "
                  f"{C.GRAY}(anchor not found){C.END}")
            return False
        if n > 1:
            print(f"  {C.YELLOW}⚠ WARN{C.END}  {name}: "
                  f"{n} occurrences, replacing all")
        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    def save(self) -> bool:
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN — no changes written{C.END}")
            return True
        if self.path.suffix == '.py':
            try:
                compile(self.content, str(self.path), 'exec')
            except SyntaxError as e:
                print(f"{C.RED}  Syntax error after patch: {e}{C.END}")
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

    def report(self) -> int:
        applied = sum(1 for _, s in self.results if s == 'applied')
        skipped = sum(1 for _, s in self.results if s == 'skip')
        failed = sum(1 for _, s in self.results if s == 'fail')
        print(f"\n  {C.BOLD}Summary:{C.END}  "
              f"{C.GREEN}applied={applied}{C.END}, "
              f"{C.GRAY}skipped={skipped}{C.END}, "
              f"{C.RED}failed={failed}{C.END}")
        return failed


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def restore_latest(path: Path) -> bool:
    backups = sorted(
        path.parent.glob(path.name + '.bak.*'),
        key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print(f"{C.RED}No backups for {path.name}{C.END}")
        return False
    latest = backups[0]
    print(f"{C.CYAN}Restoring {path.name} from {latest.name}{C.END}")
    shutil.copy2(latest, path)
    print(f"{C.GREEN}✓ Restored.{C.END}")
    return True


def main():
    p = argparse.ArgumentParser(
        description="Fix protective-order duplication in trading_2_live2.py")
    p.add_argument("--bot", type=str, default="trading_2_live2.py")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}╔{'═' * 74}╗{C.END}")
    print(f"{C.BOLD}║  Protective-Order Duplication Fix"
          f"{' ' * 40}║{C.END}")
    print(f"{C.BOLD}║  Target: {bot.name:<62}║{C.END}")
    print(f"{C.BOLD}║  Mode:   "
          f"{'DRY-RUN' if args.dry_run else 'APPLY':<62}║{C.END}")
    print(f"{C.BOLD}╚{'═' * 74}╝{C.END}")

    if args.restore:
        sys.exit(0 if restore_latest(bot) else 1)

    if not bot.exists():
        print(f"{C.RED}File not found: {bot}{C.END}")
        sys.exit(2)

    pt = Patcher(bot, dry_run=args.dry_run)
    if not pt.load() or not pt.backup():
        sys.exit(3)

    print(f"\n{C.BOLD}Applying 6 patches...{C.END}\n")

    pt.replace("P1  _cancel_all_protective_orders (use _lv_open_orders_all)",
               P1_OLD, P1_NEW,
               marker="[ccxt 4.x FIX] Uses _lv_open_orders_all() which queries BOTH the")

    pt.replace("P2  Pre-flight idempotency in _place_protective_orders",
               P2_OLD, P2_NEW,
               marker="[RESTART-GUARD] Idempotency pre-flight")

    pt.replace("P3  Persist restart-guard marker in _SYMBOL_META",
               P3_OLD, P3_NEW,
               marker="[RESTART-GUARD] Persist marker to prevent duplicates")

    pt.replace("P4a Restart-guard pre-check in run_live",
               P4A_ANCHOR, P4A_REPLACEMENT,
               marker="[RESTART-GUARD] Pre-check: compare _SYMBOL_META marker")

    pt.replace("P4b Skip-in-loop for flagged positions",
               P4B_OLD, P4B_NEW,
               marker="[RESTART-GUARD] Skip if pre-check marked this position")

    pt.replace("P5  Verify-cancel uses _lv_open_orders_all",
               P5_OLD, P5_NEW,
               marker="[ccxt 4.x FIX] Use _lv_open_orders_all to include")

    if not pt.save():
        sys.exit(4)

    failed = pt.report()

    print(f"\n{C.BOLD}╔{'═' * 74}╗{C.END}")
    if failed == 0:
        print(f"{C.BOLD}║  {C.GREEN}ALL PATCHES APPLIED SUCCESSFULLY"
              f"{C.END}{' ' * 34}║{C.END}")
    else:
        print(f"{C.BOLD}║  {C.RED}{failed} PATCH(ES) FAILED"
              f"{C.END}{' ' * 47}║{C.END}")
    print(f"{C.BOLD}╚{'═' * 74}╝{C.END}")

    if not args.dry_run and failed == 0:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify syntax:    "
              f"{C.BOLD}python3 -m py_compile {bot.name}{C.END}")
        print(f"  2. Check fixes:      "
              f"{C.BOLD}grep -n 'RESTART-GUARD' {bot.name}{C.END}")
        print(f"  3. MANUAL cleanup:   إلغِ الأوامر الواقية المكررة يدوياً "
              f"من Binance قبل التشغيل")
        print(f"  4. Run bot:          "
              f"{C.BOLD}python3 {bot.name} --mode testnet ...{C.END}")
        print(f"  5. To revert:        "
              f"{C.BOLD}python3 {__file__ if '__file__' in dir() else 'patch_protective_duplicates.py'} "
              f"--restore{C.END}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
