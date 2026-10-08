#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_guardian_sweep.py                                                 ║
║  Single-source protection: sweep every position every N cycles           ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Fixes:                                                                  ║
║    G1  Add _caller parameter to _place_protective_orders (signature)     ║
║    G2  Add _lv_guardian_sweep() — reads exchange, places missing SL/TP  ║
║    G3  Call sweep at startup (after reconcile)                          ║
║    G4  Call sweep every LIVE_GUARDIAN_INTERVAL_S in main loop           ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 patch_guardian_sweep.py --dry-run                            ║
║    python3 patch_guardian_sweep.py                                      ║
║    python3 patch_guardian_sweep.py --restore                            ║
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
# G1 — Ensure _place_protective_orders accepts _caller
# ══════════════════════════════════════════════════════════════════════════

G1_OLD = '''def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:'''

G1_NEW = '''def _place_protective_orders(exchange, sym: str, pos: Dict,
                                _caller: str = "") -> bool:'''


# ══════════════════════════════════════════════════════════════════════════
# G2 — Insert guardian sweep function before run_live
# ══════════════════════════════════════════════════════════════════════════

G2_ANCHOR = '''def run_live(cfg, exchange):'''

G2_BLOCK = '''def _lv_guardian_sweep(exchange, open_pos_live, reason="periodic"):
    """
    [GUARDIAN] Unconditional protection sweep.

    For every position (local OR exchange-only):
      1. Fetch real position list from exchange
      2. Adopt any orphans into open_pos_live
      3. Fetch real protective orders from exchange
      4. For each position, check if SL and TP exist (matched by price)
      5. Place what is missing

    This function IGNORES:
      - _prot_last_sl / _prot_last_tp markers
      - _SYMBOL_META hints
      - pending-order deferral logic (orphans have no pending anyway)

    It reads GROUND TRUTH from the exchange every time it runs.
    Designed to be the SINGLE source of protection guarantees.

    Call sites:
      - Right after reconcile at startup       (reason="startup")
      - Every LIVE_GUARDIAN_INTERVAL_S in loop (reason="periodic")
    """
    _sweep_t0 = time.time()
    _adopted = 0
    _placed_sl = 0
    _placed_tp = 0
    _ok_already = 0
    _failed = 0

    # ── 1. Fetch exchange positions ──
    try:
        ex_positions = _lv_fetch_positions(exchange, None)
    except Exception as e:
        log.warning(f"[Guardian:{reason}] fetch_positions failed: {e}")
        return
    if ex_positions is None:
        log.warning(f"[Guardian:{reason}] fetch_positions returned None")
        return

    # ── 2. Adopt orphans ──
    for sym, e in ex_positions.items():
        if sym not in open_pos_live:
            try:
                open_pos_live[sym] = _lv_adopt(exchange, sym, e, _LV_ASSETS)
                _adopted += 1
                log.warning(f"[Guardian:{reason}] adopted orphan {sym} "
                            f"qty={e['qty']} entry={e['entry']}")
            except Exception as _ae:
                log.error(f"[Guardian:{reason}] adopt {sym} failed: {_ae}")

    # ── 3. For each local position, ensure SL/TP on exchange ──
    for sym, pos in list(open_pos_live.items()):
        if sym not in ex_positions:
            continue  # position gone from exchange — will be handled by reconcile
        sl = float(pos.get('sl') or 0)
        tp = float(pos.get('tp1') or 0)
        if sl <= 0 or tp <= 0:
            log.warning(f"[Guardian:{reason}] {sym} has invalid sl={sl} "
                        f"tp={tp} — skipping")
            continue

        # Fetch protective orders from exchange
        try:
            _rate_record(2.0)
            orders = _lv_open_orders_all(exchange, sym)
        except Exception as _oe:
            log.warning(f"[Guardian:{reason}] {sym} fetch orders "
                        f"failed: {_oe}")
            continue

        # Match by price with 10 bps tolerance
        has_sl = False
        has_tp = False
        tol_sl = max(abs(sl) * 1e-3, 1e-9)
        tol_tp = max(abs(tp) * 1e-3, 1e-9)
        for o in orders:
            sp = float(
                o.get('stopPrice')
                or o.get('triggerPrice')
                or (o.get('info') or {}).get('stopPrice')
                or 0
            )
            if sp <= 0:
                continue
            ot = str(o.get('type') or '').lower()
            if 'take_profit' in ot:
                if abs(sp - tp) < tol_tp:
                    has_tp = True
            else:
                if abs(sp - sl) < tol_sl:
                    has_sl = True

        if has_sl and has_tp:
            _ok_already += 1
            continue

        # Place whatever is missing (single call places both if needed)
        log.warning(
            f"[Guardian:{reason}] {sym} MISSING protection "
            f"(sl_exists={has_sl}, tp_exists={has_tp}) — placing now"
        )
        try:
            ok = _place_protective_orders(
                exchange, sym, pos,
                _caller=f"guardian-{reason}"
            )
            if ok:
                pos['_prot_last_sl'] = sl
                pos['_prot_last_tp'] = tp
                pos['_prot_last_ts'] = time.time()
                if not has_sl:
                    _placed_sl += 1
                if not has_tp:
                    _placed_tp += 1
            else:
                _failed += 1
                log.error(f"[Guardian:{reason}] {sym} placement "
                          f"returned False")
        except Exception as _pe:
            _failed += 1
            log.error(f"[Guardian:{reason}] {sym} placement raised: {_pe}")

    _sweep_elapsed = time.time() - _sweep_t0
    if (_adopted + _placed_sl + _placed_tp + _failed) > 0:
        log.warning(
            f"[Guardian:{reason}] sweep done in {_sweep_elapsed:.2f}s — "
            f"adopted={_adopted} placed_sl={_placed_sl} "
            f"placed_tp={_placed_tp} ok={_ok_already} failed={_failed}"
        )
    else:
        log.info(
            f"[Guardian:{reason}] sweep done in {_sweep_elapsed:.2f}s — "
            f"{_ok_already} positions already protected"
        )


def run_live(cfg, exchange):'''

G2_MARKER = "def _lv_guardian_sweep(exchange, open_pos_live, reason=\"periodic\"):"


# ══════════════════════════════════════════════════════════════════════════
# G3 — Call sweep right after reconcile at startup
# ══════════════════════════════════════════════════════════════════════════

G3_OLD = '''    open_pos_live = reconcile_state_machine(exchange, open_pos_live, None)
    log.info(f"  [State] After initial sync: {len(open_pos_live)} positions")'''

G3_NEW = '''    open_pos_live = reconcile_state_machine(exchange, open_pos_live, None)
    log.info(f"  [State] After initial sync: {len(open_pos_live)} positions")

    # ══ [GUARDIAN] Startup sweep — guarantee every position is protected ══
    # This is the LAST line of defense. It reads ground truth from the
    # exchange and places any missing SL/TP unconditionally.
    try:
        _lv_guardian_sweep(exchange, open_pos_live, reason="startup")
    except Exception as _gse:
        log.error(f"[Guardian:startup] sweep raised: {_gse}")'''

G3_MARKER = "[GUARDIAN] Startup sweep"


# ══════════════════════════════════════════════════════════════════════════
# G4 — Call sweep periodically inside main loop
# ══════════════════════════════════════════════════════════════════════════

G4_OLD = '''            loop_iter += 1
            _LV_STATE['recon_immediate'] = False'''

G4_NEW = '''            loop_iter += 1
            _LV_STATE['recon_immediate'] = False

            # ══ [GUARDIAN] Periodic sweep — safety net for orphans ══
            _guardian_interval = float(
                getattr(CFG, 'LIVE_GUARDIAN_INTERVAL_S', 60.0))
            if (not hasattr(run_live, '_last_guardian_ts')
                    or time.time() - run_live._last_guardian_ts
                        >= _guardian_interval):
                run_live._last_guardian_ts = time.time()
                try:
                    _lv_guardian_sweep(exchange, open_pos_live,
                                        reason="periodic")
                except Exception as _gse:
                    log.error(f"[Guardian:periodic] sweep raised: {_gse}")'''

G4_MARKER = "[GUARDIAN] Periodic sweep"


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
                    print(f"{C.GREEN}  Restored.{C.END}")
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
    print(f"{C.BOLD}  Guardian Sweep Patch{C.END}")
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

    print(f"\n{C.BOLD}Applying 4 patches...{C.END}\n")

    pt.replace("G1  _place_protective_orders accepts _caller",
               G1_OLD, G1_NEW,
               marker="def _place_protective_orders(exchange, sym: str, pos: Dict,\n                                _caller: str = \"\") -> bool:")

    # Insert sweep function before run_live
    pt.replace("G2  Insert _lv_guardian_sweep()",
               G2_ANCHOR, G2_BLOCK,
               marker=G2_MARKER)

    pt.replace("G3  Call sweep at startup",
               G3_OLD, G3_NEW,
               marker=G3_MARKER)

    pt.replace("G4  Call sweep periodically in main loop",
               G4_OLD, G4_NEW,
               marker=G4_MARKER)

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
        print(f"  2. Run bot. Expected in logs:")
        print(f"     {C.BOLD}[Guardian:startup] sweep done — "
              f"placed_sl=N placed_tp=M ok=K failed=0{C.END}")
        print(f"     {C.BOLD}[Guardian:periodic] sweep done...{C.END} (every 60s)")
        print(f"  3. Revert:  python3 {Path(__file__).name} --restore")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
