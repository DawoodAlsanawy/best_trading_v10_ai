#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_live2_ob_restrict.py                                              ║
║  Option A: Restrict ORDER_BOOK_ENTRY to --no-fixed-price mode only       ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Why:                                                                    ║
║    When PO_FIXED_PRICE=True, the user wants the classic S1/S2 path.      ║
║    Currently, OB entry overrides it unconditionally whenever it is      ║
║    enabled (as long as FILL_ENGINE_ENABLED is True). That made OB       ║
║    replace the accurate tunnel-based entry even in fixed-price mode.    ║
║                                                                          ║
║  Fix:                                                                    ║
║    Add `and not PO_FIXED_PRICE` to:                                      ║
║      * the live OB-Entry branch in run_live                              ║
║      * the `use_ob_entry` flag in the backtest's simulate_portfolio     ║
║                                                                          ║
║  Effect:                                                                 ║
║    * PO_FIXED_PRICE=True  → classic S1/S2 everywhere (unchanged)         ║
║    * PO_FIXED_PRICE=False → OB entry active in live AND backtest         ║
║    * Both modes stay in parity by construction                           ║
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
# Patch 1 — Live: OB-Entry branch condition
# ══════════════════════════════════════════════════════════════════════════

P1_OLD = '''                        # ══ [OB-ENTRY] Order-book-aware entry ══
                        # When enabled, replaces both Watch and pending
                        # flows with a blocking order-book executor that
                        # anchors the ladder at _compute_entry_target().
                        if (getattr(CFG, 'ORDER_BOOK_ENTRY_ENABLED', False)
                                and getattr(CFG, 'FILL_ENGINE_ENABLED', True)):'''

P1_NEW = '''                        # ══ [OB-ENTRY] Order-book-aware entry ══
                        # [OPTION-A] Restricted to --no-fixed-price mode:
                        # When PO_FIXED_PRICE=True, the tunnel-based S1/S2
                        # path is used (its precision is the whole point of
                        # the fixed-price design). OB's σ-anchored ladder
                        # only overrides when the caller has explicitly
                        # opted into dynamic pricing (--no-fixed-price).
                        if (getattr(CFG, 'ORDER_BOOK_ENTRY_ENABLED', False)
                                and getattr(CFG, 'FILL_ENGINE_ENABLED', True)
                                and not getattr(CFG, 'PO_FIXED_PRICE', True)):'''

P1_MARKER = "[OPTION-A] Restricted to --no-fixed-price mode:"


# ══════════════════════════════════════════════════════════════════════════
# Patch 2 — Backtest: use_ob_entry flag
# ══════════════════════════════════════════════════════════════════════════

P2_OLD = '''            use_time_decay_price=_td_enabled,
            use_ob_entry=bool(getattr(
                CFG, 'ORDER_BOOK_ENTRY_ENABLED', False)),
        )'''

P2_NEW = '''            use_time_decay_price=_td_enabled,
            # [OPTION-A] Mirror the live restriction exactly:
            # OB backtest runs only when the live would run it too.
            use_ob_entry=bool(
                getattr(CFG, 'ORDER_BOOK_ENTRY_ENABLED', False)
                and not getattr(CFG, 'PO_FIXED_PRICE', True)),
        )'''

P2_MARKER = "[OPTION-A] Mirror the live restriction exactly:"


# ══════════════════════════════════════════════════════════════════════════
# Patch 3 — CLI wiring: add a one-line diagnostics banner
# ══════════════════════════════════════════════════════════════════════════

P3_OLD = '''    try:
        if getattr(args, 'order_book_entry', False):
            CFG.ORDER_BOOK_ENTRY_ENABLED = True
            log.info("[OB-Entry] ENABLED (order-book-aware entry)")
        else:
            CFG.ORDER_BOOK_ENTRY_ENABLED = False'''

P3_NEW = '''    try:
        if getattr(args, 'order_book_entry', False):
            CFG.ORDER_BOOK_ENTRY_ENABLED = True
            _effective_ob = (
                bool(CFG.ORDER_BOOK_ENTRY_ENABLED)
                and not bool(getattr(CFG, 'PO_FIXED_PRICE', True))
            )
            log.info(
                "[OB-Entry] ENABLED (order-book-aware entry); "
                f"effective={_effective_ob} "
                f"(PO_FIXED_PRICE={getattr(CFG, 'PO_FIXED_PRICE', True)}, "
                f"PO_FIXED_PRICE must be False for OB to run)"
            )
        else:
            CFG.ORDER_BOOK_ENTRY_ENABLED = False'''

P3_MARKER = "effective={_effective_ob}"


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
    p.add_argument("--bot", default="trading_live.py",
                   help="Bot file to patch")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.BOLD}  Option-A Patcher -- {bot.name}{C.END}")
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
    pt.replace("P1  Live: OB-Entry branch restriction",
               P1_OLD, P1_NEW, marker=P1_MARKER)
    pt.replace("P2  Backtest: use_ob_entry restriction",
               P2_OLD, P2_NEW, marker=P2_MARKER)
    pt.replace("P3  CLI: diagnostics banner",
               P3_OLD, P3_NEW, marker=P3_MARKER)

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
        print(f"  2. Grep:    grep -n 'OPTION-A' {bot.name}")
        print(f"  3. Behaviour:")
        print(f"     {C.BOLD}PO_FIXED_PRICE=True →  S1/S2 (classic)")
        print(f"     PO_FIXED_PRICE=False → OB entry (σ-ladder){C.END}")
        print(f"  4. Revert:  python3 {Path(__file__).name} --restore")


if __name__ == "__main__":
    main()
