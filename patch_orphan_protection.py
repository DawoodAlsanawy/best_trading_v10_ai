#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_orphan_protection.py                                              ║
║  Fix orphan positions not being protected after my earlier patches      ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Root cause (two bugs):                                                  ║
║    1. _lv_adopt calls _place_protective_orders(..., _caller="adopt")    ║
║       but the function signature did not accept `_caller`.              ║
║       Result: TypeError caught silently → orphan not protected.         ║
║                                                                          ║
║    2. My P4a pre-check trusted _symbol_meta alone and marked            ║
║       positions as protected, causing LAYER-7 restore to skip them      ║
║       even when the exchange had no protective orders.                  ║
║                                                                          ║
║  Fix:                                                                    ║
║    F1  Add _caller parameter to _place_protective_orders                ║
║    F2  P4a pre-check must verify against the LIVE exchange              ║
║    F3  Final safety sweep after LAYER-7                                 ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 patch_orphan_protection.py --dry-run                         ║
║    python3 patch_orphan_protection.py                                   ║
║    python3 patch_orphan_protection.py --restore                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class C:
    GREEN='\033[92m'; RED='\033[91m'; YELLOW='\033[93m'
    CYAN='\033[96m'; GRAY='\033[90m'; BOLD='\033[1m'; END='\033[0m'


# ══════════════════════════════════════════════════════════════════════════
# F1 — Add _caller parameter to _place_protective_orders
# ══════════════════════════════════════════════════════════════════════════

F1_OLD = '''def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:
    """
    Place STOP_MARKET at SL and TAKE_PROFIT_MARKET at TP for the position.
'''

F1_NEW = '''def _place_protective_orders(exchange, sym: str, pos: Dict,
                                _caller: str = "") -> bool:
    """
    Place STOP_MARKET at SL and TAKE_PROFIT_MARKET at TP for the position.

    [F1 FIX] Accepts optional `_caller` diagnostic tag. The original
    code had callers (_lv_adopt) passing _caller="adopt" while this
    function did not accept it → TypeError was caught silently in
    _lv_adopt's try/except → orphan positions never got SL/TP.

    _caller is used only for logging so duplicates can be traced
    to their source during diagnostics.
'''

F1_MARKER = '''def _place_protective_orders(exchange, sym: str, pos: Dict,
                                _caller: str = "") -> bool:'''


# ══════════════════════════════════════════════════════════════════════════
# F2 — Fix P4a pre-check to verify against the live exchange
# ══════════════════════════════════════════════════════════════════════════

F2_OLD = '''    _restart_guard_skip = 0
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
                 f"will_place={_restart_guard_place}")'''

F2_NEW = '''    _restart_guard_skip = 0
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

        # ══ [F2 FIX] Never trust the meta marker alone ══
        # The previous P4a patch trusted meta and could leave orphans
        # UNPROTECTED on the exchange (e.g. if the user cancelled the
        # SL manually, or Binance lost the Algo Order after a maintenance
        # window). Now we ALWAYS verify against the live exchange before
        # marking a position as "already protected".
        _exchange_verified = False
        if _sl_ok and _tp_ok and _age_h < 168:
            try:
                _live_orders = _lv_open_orders_all(exchange, _sym_p)
                _tol = max(abs(_cur_sl) * 1e-3, 1e-9)
                for _o in _live_orders:
                    _osp = float(
                        _o.get('stopPrice')
                        or _o.get('triggerPrice')
                        or (_o.get('info') or {}).get('stopPrice')
                        or 0
                    )
                    if _osp > 0 and abs(_osp - _cur_sl) < _tol:
                        _exchange_verified = True
                        break
            except Exception as _e:
                log.debug(f"[Prot-RestartGuard] {_sym_p} live verify "
                          f"failed: {_e}")
                _exchange_verified = False

        if _exchange_verified:
            _pos_p['_prot_last_sl'] = _cur_sl
            _pos_p['_prot_last_tp'] = _cur_tp
            _restart_guard_skip += 1
            log.info(f"[Prot-RestartGuard] {_sym_p} meta+exchange agree "
                     f"(sl={_cur_sl:.6f}) -- skip re-placement")
        elif _sl_ok and _tp_ok:
            log.warning(
                f"[Prot-RestartGuard] {_sym_p} meta says protected "
                f"(sl={_meta_sl:.6f}) but EXCHANGE HAS NO MATCHING SL "
                f"-- will RE-PLACE (sl={_cur_sl:.6f})"
            )
            _restart_guard_place += 1
        else:
            _restart_guard_place += 1

    if _restart_guard_skip > 0 or _restart_guard_place > 0:
        log.info(f"  [Prot-RestartGuard] skip={_restart_guard_skip} "
                 f"will_place={_restart_guard_place}")'''

F2_MARKER = "[F2 FIX] Never trust the meta marker alone"


# ══════════════════════════════════════════════════════════════════════════
# F3 — Final safety sweep after LAYER-7 restore
# ══════════════════════════════════════════════════════════════════════════

F3_OLD = '''        log.info(f"  [Prot] restored={_prot_ok} "
                 f"deferred={_prot_deferred} "
                 f"dropped={_prot_dropped_pending} "
                 f"failed={_prot_fail}")'''

F3_NEW = '''        log.info(f"  [Prot] restored={_prot_ok} "
                 f"deferred={_prot_deferred} "
                 f"dropped={_prot_dropped_pending} "
                 f"failed={_prot_fail}")

        # ══ [F3 FIX] Final safety sweep ══
        # After LAYER-7 restore, verify EVERY open position has a
        # protective marker. Any position that is (a) not deferred due to
        # a pending order, (b) has valid sl/tp, and (c) still lacks the
        # marker after the restore loop, gets one more forced attempt.
        # This catches edge cases where restore silently failed.
        _final_unprotected = []
        for _sym_f, _pos_f in list(open_pos_live.items()):
            _has_marker = (_pos_f.get('_prot_last_sl') is not None
                            and _pos_f.get('_prot_last_tp') is not None)
            if _has_marker:
                continue
            _sl_f = float(_pos_f.get('sl') or 0)
            _tp_f = float(_pos_f.get('tp1') or 0)
            if _sl_f <= 0 or _tp_f <= 0:
                continue
            if _sym_f in _PENDING_ORDERS:
                continue  # deferred
            _final_unprotected.append(_sym_f)

        for _sym_f in _final_unprotected:
            try:
                log.warning(
                    f"[Prot-Sweep] {_sym_f} has NO protective marker "
                    f"after restore -- forcing placement"
                )
                _ok_f = _place_protective_orders(
                    exchange, _sym_f,
                    open_pos_live[_sym_f],
                    _caller="final-sweep"
                )
                if _ok_f:
                    open_pos_live[_sym_f]['_prot_last_sl'] = float(
                        open_pos_live[_sym_f].get('sl') or 0)
                    open_pos_live[_sym_f]['_prot_last_tp'] = float(
                        open_pos_live[_sym_f].get('tp1') or 0)
                    open_pos_live[_sym_f]['_prot_last_ts'] = time.time()
                    log.info(f"[Prot-Sweep] {_sym_f} protected OK")
                else:
                    log.error(f"[Prot-Sweep] {_sym_f} placement returned False")
            except Exception as _e_f:
                log.error(f"[Prot-Sweep] {_sym_f} failed: {_e_f}")

        if _final_unprotected:
            log.warning(f"[Prot-Sweep] attempted {len(_final_unprotected)} "
                        f"positions")'''

F3_MARKER = "[F3 FIX] Final safety sweep"


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
            print(f"{C.RED}  Not found: {self.path}{C.END}"); return False
        try:
            self.content = self.path.read_text(encoding='utf-8')
            print(f"{C.CYAN}  Loaded {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Read error: {e}{C.END}"); return False

    def backup(self) -> bool:
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

    def replace(self, name: str, old: str, new: str,
                marker: str = None) -> bool:
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name}")
            return True
        n = self.content.count(old)
        if n == 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name}")
            return False
        if n > 1:
            print(f"  {C.YELLOW}⚠ WARN{C.END}  {name}: {n} occurrences")
        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    def save(self) -> bool:
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN — not written{C.END}"); return True
        if self.path.suffix == '.py':
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
            print(f"{C.GREEN}  Written.{C.END}"); return True
        except Exception as e:
            print(f"{C.RED}  Write failed: {e}{C.END}"); return False

    def report(self) -> int:
        a = sum(1 for _, s in self.results if s == 'applied')
        s = sum(1 for _, s in self.results if s == 'skip')
        f = sum(1 for _, s in self.results if s == 'fail')
        print(f"\n  {C.BOLD}Summary:{C.END}  "
              f"{C.GREEN}applied={a}{C.END}, "
              f"{C.GRAY}skipped={s}{C.END}, "
              f"{C.RED}failed={f}{C.END}")
        return f


def restore_latest(path: Path) -> bool:
    backups = sorted(path.parent.glob(path.name + '.bak.*'),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print(f"{C.RED}No backups for {path.name}{C.END}"); return False
    print(f"{C.CYAN}Restoring {path.name} from {backups[0].name}{C.END}")
    shutil.copy2(backups[0], path)
    print(f"{C.GREEN}✓ Restored.{C.END}")
    return True


def main():
    p = argparse.ArgumentParser(
        description="Fix orphan positions not being protected")
    p.add_argument("--bot", default="trading_2_live2.py")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.BOLD}  Orphan-Protection Fix{C.END}")
    print(f"{C.BOLD}  Target: {bot.name}{C.END}")
    print(f"{C.BOLD}  Mode:   {'DRY-RUN' if args.dry_run else 'APPLY'}{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if args.restore:
        sys.exit(0 if restore_latest(bot) else 1)
    if not bot.exists():
        print(f"{C.RED}File not found: {bot}{C.END}"); sys.exit(2)

    pt = Patcher(bot, dry_run=args.dry_run)
    if not pt.load() or not pt.backup():
        sys.exit(3)

    print(f"\n{C.BOLD}Applying 3 fixes...{C.END}\n")

    pt.replace("F1  _place_protective_orders accepts _caller",
               F1_OLD, F1_NEW, marker=F1_MARKER)

    pt.replace("F2  P4a pre-check verifies against exchange",
               F2_OLD, F2_NEW, marker=F2_MARKER)

    pt.replace("F3  Final safety sweep after LAYER-7",
               F3_OLD, F3_NEW, marker=F3_MARKER)

    if not pt.save():
        sys.exit(4)
    failed = pt.report()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    if failed == 0:
        print(f"{C.GREEN}  ALL FIXES APPLIED SUCCESSFULLY{C.END}")
    else:
        print(f"{C.RED}  {failed} FIX(ES) FAILED{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if failed == 0 and not args.dry_run:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify:  python3 -m py_compile {bot.name}")
        print(f"  2. OPTIONAL reset of stale meta (recommended):")
        print(f"     {C.BOLD}rm -f symbol_meta_testnet.json{C.END}")
        print(f"  3. Run bot and watch for:")
        print(f"     {C.BOLD}[Prot-RestartGuard] ... skip=0 will_place=N{C.END}")
        print(f"     {C.BOLD}[Prot-Sweep] BTC/USDT protected OK{C.END}")
        print(f"  4. Revert:  python3 {Path(__file__).name} --restore")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
