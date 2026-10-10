#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_ccxt4_fixes.py                                                    ║
║  Batch patcher for ccxt 4.x compatibility issues                         ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Fixes applied:                                                          ║
║    1. [Bot]  _extract_tier_entry helper (list/dict normalization)        ║
║    2. [Bot]  fetch_symbol_leverage_tiers — handle dict shape             ║
║    3. [Bot]  _get_mmr_for_symbol — handle dict shape                     ║
║    4. [Bot]  ensure_symbol_setup has_pos — None-safe fetch_leverage      ║
║    5. [Test] test_fetch_tickers — futures symbol notation                ║
║    6. [Test] test_fetch_leverage_tiers — list/dict normalization         ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 patch_ccxt4_fixes.py                     # apply all           ║
║    python3 patch_ccxt4_fixes.py --dry-run           # preview only        ║
║    python3 patch_ccxt4_fixes.py --bot PATH          # custom bot path     ║
║    python3 patch_ccxt4_fixes.py --test PATH         # custom test path    ║
║    python3 patch_ccxt4_fixes.py --restore           # restore from backup ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional


# ══════════════════════════════════════════════════════════════════════════
# ANSI colors
# ══════════════════════════════════════════════════════════════════════════
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
# Patcher class
# ══════════════════════════════════════════════════════════════════════════
class FilePatcher:
    def __init__(self, path: Path, dry_run: bool = False):
        self.path = path
        self.dry_run = dry_run
        self.original = None
        self.content = None
        self.backup_path = None
        self.results: List[Tuple[str, str, str]] = []   # (name, status, detail)

    # ──────────────────────────────────────────────────────────────────────
    def load(self) -> bool:
        if not self.path.exists():
            print(f"{C.RED}  ✗ File not found: {self.path}{C.END}")
            return False
        try:
            self.original = self.path.read_text(encoding='utf-8')
            self.content = self.original
            print(f"{C.CYAN}  → Loaded {self.path.name} "
                  f"({len(self.original):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  ✗ Cannot read {self.path}: {e}{C.END}")
            return False

    # ──────────────────────────────────────────────────────────────────────
    def backup(self) -> bool:
        if self.dry_run:
            return True
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = self.path.with_suffix(
            self.path.suffix + f'.bak.{ts}'
        )
        try:
            shutil.copy2(self.path, self.backup_path)
            print(f"{C.CYAN}  → Backup: {self.backup_path.name}{C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  ✗ Backup failed: {e}{C.END}")
            return False

    # ──────────────────────────────────────────────────────────────────────
    def patch(self, name: str, old: str, new: str,
              marker: Optional[str] = None) -> bool:
        """
        Replace `old` with `new`. If `marker` provided and found in content,
        assume already applied → skip.
        """
        # Already applied?
        if marker and marker in self.content:
            self.results.append((name, 'skip', 'already applied'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name} "
                  f"{C.GRAY}(already applied){C.END}")
            return True

        # Not found?
        if old not in self.content:
            self.results.append((name, 'fail', 'anchor not found'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} "
                  f"{C.GRAY}(anchor not found){C.END}")
            return False

        # Multiple occurrences? Warn.
        n = self.content.count(old)
        if n > 1:
            print(f"  {C.YELLOW}⚠ WARN{C.END}  {name} — "
                  f"{n} occurrences, replacing all")

        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied', f'{n} replacement(s)'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    # ──────────────────────────────────────────────────────────────────────
    def insert_before(self, name: str, anchor: str, block: str,
                       marker: Optional[str] = None) -> bool:
        """Insert `block` immediately before `anchor`."""
        if marker and marker in self.content:
            self.results.append((name, 'skip', 'already applied'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name} "
                  f"{C.GRAY}(already applied){C.END}")
            return True

        if anchor not in self.content:
            self.results.append((name, 'fail', 'anchor not found'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} "
                  f"{C.GRAY}(anchor not found){C.END}")
            return False

        self.content = self.content.replace(anchor, block + anchor, 1)
        self.results.append((name, 'applied', ''))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    # ──────────────────────────────────────────────────────────────────────
    def save(self) -> bool:
        if self.dry_run:
            print(f"{C.YELLOW}  → DRY RUN — no changes written{C.END}")
            return True
        # Verify syntax compiles (Python files only)
        if self.path.suffix == '.py':
            try:
                compile(self.content, str(self.path), 'exec')
            except SyntaxError as e:
                print(f"{C.RED}  ✗ Syntax error after patch: {e}{C.END}")
                print(f"{C.RED}  → Restoring from backup...{C.END}")
                if self.backup_path and self.backup_path.exists():
                    shutil.copy2(self.backup_path, self.path)
                    print(f"{C.GREEN}  → Restored. No changes made.{C.END}")
                return False

        try:
            self.path.write_text(self.content, encoding='utf-8')
            print(f"{C.GREEN}  → Written {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  ✗ Write failed: {e}{C.END}")
            return False

    # ──────────────────────────────────────────────────────────────────────
    def report(self) -> int:
        """Returns number of failures."""
        applied = sum(1 for _, s, _ in self.results if s == 'applied')
        skipped = sum(1 for _, s, _ in self.results if s == 'skip')
        failed = sum(1 for _, s, _ in self.results if s == 'fail')
        print(f"\n  {C.BOLD}Summary for {self.path.name}:{C.END}  "
              f"{C.GREEN}applied={applied}{C.END}, "
              f"{C.GRAY}skipped={skipped}{C.END}, "
              f"{C.RED}failed={failed}{C.END}")
        return failed


# ══════════════════════════════════════════════════════════════════════════
# BOT PATCHES (trading_2_mfal2.py)
# ══════════════════════════════════════════════════════════════════════════

# ── Patch B1: _extract_tier_entry helper ──
BOT_HELPER_BLOCK = '''def _extract_tier_entry(tiers_raw, symbol: str) -> Optional[Dict]:
    """
    [ccxt 4.x FIX] Normalize fetch_leverage_tiers output across versions.

    ccxt shapes observed in the wild:
      A) list[ {symbol, tiers:[...]}, ... ]          (older ccxt)
      B) dict[ symbol_str, {tiers:[...]} ]           (ccxt >= 4.x, common)
      C) dict[ symbol_str, [tier_dict, ...] ]        (rare)

    Returns a single entry dict with a 'tiers' key, or None on failure.
    """
    if not tiers_raw:
        return None

    def _sym_match(a: str, b: str) -> bool:
        if not a or not b:
            return False
        return a.split(':')[0] == b.split(':')[0]

    def _wrap(v):
        if isinstance(v, dict):
            return v
        if isinstance(v, list):
            return {'symbol': symbol, 'tiers': v}
        return None

    # ── Case A: list ──
    if isinstance(tiers_raw, list):
        if len(tiers_raw) == 0:
            return None
        for entry in tiers_raw:
            if isinstance(entry, dict) and _sym_match(
                    entry.get('symbol', ''), symbol):
                return entry
        first = tiers_raw[0]
        return first if isinstance(first, dict) else None

    # ── Case B / C: dict ──
    if isinstance(tiers_raw, dict):
        if symbol in tiers_raw:
            return _wrap(tiers_raw[symbol])
        for k, v in tiers_raw.items():
            if _sym_match(k, symbol):
                return _wrap(v)
        if len(tiers_raw) > 0:
            k = next(iter(tiers_raw))
            return _wrap(tiers_raw[k])

    return None


'''

# ── Patch B2: fetch_symbol_leverage_tiers ──
BOT_OLD_FETCH_TIERS = '''def fetch_symbol_leverage_tiers(exchange, symbol: str) -> Optional[int]:
    """
    Query the exchange for a symbol's max leverage.
    Returns the max leverage (int) or None on failure.
    """
    try:
        tiers = exchange.fetch_leverage_tiers([symbol])
        if not tiers or len(tiers) == 0:
            return None
        t0 = tiers[0]
        tier_list = t0.get('tiers') or []
        if not tier_list:
            return None
        # Binance returns the smallest-notional tier first,
        # which carries the highest leverage.
        max_lev = int(tier_list[0].get('maxLeverage', 0))
        return max_lev if max_lev > 0 else None
    except Exception as e:
        log.debug(f"[LevTiers] fetch failed for {symbol}: {e}")
        return None'''

BOT_NEW_FETCH_TIERS = '''def fetch_symbol_leverage_tiers(exchange, symbol: str) -> Optional[int]:
    """
    Query the exchange for a symbol's max leverage.

    [ccxt 4.x FIX] Uses _extract_tier_entry to handle both list and dict
    return shapes. Before the fix, `tiers[0]` raised KeyError: 0 when the
    exchange returned a dict (which ccxt 4.x does by default).
    Returns the max leverage (int) or None on failure.
    """
    try:
        tiers_raw = exchange.fetch_leverage_tiers([symbol])
        entry = _extract_tier_entry(tiers_raw, symbol)
        if entry is None:
            return None
        tier_list = entry.get('tiers') or []
        if not tier_list:
            return None
        # Binance returns the smallest-notional tier first,
        # which carries the highest leverage.
        max_lev = int(tier_list[0].get('maxLeverage', 0))
        return max_lev if max_lev > 0 else None
    except Exception as e:
        log.debug(f"[LevTiers] fetch failed for {symbol}: {e}")
        return None'''

# ── Patch B3: _get_mmr_for_symbol ──
BOT_OLD_MMR = '''def _get_mmr_for_symbol(exchange, symbol: str) -> float:
    """
    Maintenance margin rate for a symbol.
    - Cached per session.
    - Returns tier-0 (smallest notional) MMR, since our positions are small.
    - Falls back to CFG.LIQ_FALLBACK_MMR on any failure.
    """
    if symbol in _MMR_CACHE:
        return _MMR_CACHE[symbol]
    try:
        tiers = exchange.fetch_leverage_tiers([symbol])
        if tiers and len(tiers) > 0:
            t0 = tiers[0]
            tiers_list = t0.get('tiers', []) or []
            if tiers_list:
                mmr = float(tiers_list[0].get('maintenanceMarginRate', 0))
                if mmr > 0:
                    _MMR_CACHE[symbol] = mmr
                    return mmr
    except Exception as e:
        log.debug(f"[MMR] fetch failed for {symbol}: {e}")
    _MMR_CACHE[symbol] = float(getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
    return _MMR_CACHE[symbol]'''

BOT_NEW_MMR = '''def _get_mmr_for_symbol(exchange, symbol: str) -> float:
    """
    Maintenance margin rate for a symbol.

    [ccxt 4.x FIX] Uses _extract_tier_entry to handle dict-shaped responses.
    Before the fix, dict responses silently fell through to the fallback MMR,
    which meant ALL LiqGate / LevCap calculations used the conservative 2%
    instead of the true per-symbol MMR (0.4% for BTC, 1% for alts, etc.).

    - Cached per session.
    - Returns tier-0 (smallest notional) MMR, since our positions are small.
    - Falls back to CFG.LIQ_FALLBACK_MMR on any failure.
    """
    if symbol in _MMR_CACHE:
        return _MMR_CACHE[symbol]
    try:
        tiers_raw = exchange.fetch_leverage_tiers([symbol])
        entry = _extract_tier_entry(tiers_raw, symbol)
        if entry is not None:
            tier_list = entry.get('tiers', []) or []
            if tier_list:
                mmr = float(tier_list[0].get('maintenanceMarginRate', 0))
                if mmr > 0:
                    _MMR_CACHE[symbol] = mmr
                    return mmr
    except Exception as e:
        log.debug(f"[MMR] fetch failed for {symbol}: {e}")
    _MMR_CACHE[symbol] = float(getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
    return _MMR_CACHE[symbol]'''

# ── Patch B4: ensure_symbol_setup has_pos branch ──
BOT_OLD_SETUP_HASPOS = '''    if has_pos:
        # Read current leverage, do NOT change it
        try:
            lev_info = exchange.fetch_leverage(sym)
            cur_lev = int(lev_info.get('leverage', target_leverage))
        except Exception:
            cur_lev = target_leverage'''

BOT_NEW_SETUP_HASPOS = '''    if has_pos:
        # Read current leverage, do NOT change it
        # [ccxt 4.x FIX] Some exchanges (Binance Demo) return None from
        # fetch_leverage — guard against that explicitly instead of
        # relying on an implicit AttributeError being caught.
        try:
            lev_info = exchange.fetch_leverage(sym)
            if lev_info is None or not hasattr(lev_info, 'get'):
                cur_lev = target_leverage
                log.debug(
                    f"[Setup] {sym} fetch_leverage returned "
                    f"{type(lev_info).__name__} — using target="
                    f"{target_leverage}x"
                )
            else:
                cur_lev = int(lev_info.get('leverage', target_leverage)
                              or target_leverage)
        except Exception as e:
            log.debug(f"[Setup] {sym} fetch_leverage failed: {e}")
            cur_lev = target_leverage'''


# ══════════════════════════════════════════════════════════════════════════
# TEST PATCHES (exchange_api_test.py)
# ══════════════════════════════════════════════════════════════════════════

TEST_OLD_TICKERS = '''    # Verify a USDT pair has quoteVolume
    usdt = [t for k, t in tickers.items() if k.endswith('/USDT')]
    assert len(usdt) > 0, "no USDT pairs"
    return True, f"{n} tickers ({len(usdt)} USDT)"'''

TEST_NEW_TICKERS = '''    # Verify a USDT pair has quoteVolume
    # [ccxt 4.x FIX] Binance Futures uses "BTC/USDT:USDT" notation,
    # so endswith('/USDT') returns zero. Match both notations.
    usdt = [t for k, t in tickers.items() if '/USDT' in k]
    assert len(usdt) > 0, "no USDT pairs"
    return True, f"{n} tickers ({len(usdt)} USDT)"'''

TEST_OLD_TIERS = '''def test_fetch_leverage_tiers(exchange, symbol: str) -> Tuple[bool, str]:
    """Leverage tiers — used by fetch_symbol_leverage_tiers."""
    tiers = exchange.fetch_leverage_tiers([symbol])
    assert tiers and len(tiers) > 0, "empty tiers"
    t0 = tiers[0]
    tier_list = t0.get('tiers') or []
    assert len(tier_list) > 0, "no tiers in response"
    max_lev = int(tier_list[0].get('maxLeverage', 0))
    mmr = float(tier_list[0].get('maintenanceMarginRate', 0))
    return True, f"max_lev={max_lev}x, mmr={mmr*100:.4f}%"'''

TEST_NEW_TIERS = '''def test_fetch_leverage_tiers(exchange, symbol: str) -> Tuple[bool, str]:
    """
    Leverage tiers — used by fetch_symbol_leverage_tiers.

    [ccxt 4.x FIX] Handles both list and dict return shapes.
    ccxt 4.x on Binance returns: dict[ "BTC/USDT:USDT", {tiers:[...]} ]
    """
    tiers = exchange.fetch_leverage_tiers([symbol])
    assert tiers, "empty tiers"

    shape = ('list' if isinstance(tiers, list)
             else 'dict' if isinstance(tiers, dict)
             else type(tiers).__name__)

    if isinstance(tiers, list):
        t0 = tiers[0] if len(tiers) > 0 else None
    elif isinstance(tiers, dict):
        # Prefer matching entry
        t0 = None
        for k, v in tiers.items():
            if k.split(':')[0] == symbol.split(':')[0]:
                t0 = v
                break
        if t0 is None and len(tiers) > 0:
            t0 = next(iter(tiers.values()))
    else:
        raise Exception(f"unexpected type: {shape}")

    assert t0 is not None, "no entry extracted"
    # Handle case where dict value is a raw list
    if isinstance(t0, list):
        tier_list = t0
    elif isinstance(t0, dict):
        tier_list = t0.get('tiers') or []
    else:
        raise Exception(f"unexpected entry type: {type(t0).__name__}")

    assert len(tier_list) > 0, "no tiers in response"
    max_lev = int(tier_list[0].get('maxLeverage', 0))
    mmr = float(tier_list[0].get('maintenanceMarginRate', 0))
    return True, (f"shape={shape}, max_lev={max_lev}x, "
                  f"mmr={mmr*100:.4f}%")'''


# ══════════════════════════════════════════════════════════════════════════
# RESTORE
# ══════════════════════════════════════════════════════════════════════════
def restore_latest(path: Path) -> bool:
    """Find latest .bak.* for this file and restore it."""
    backups = sorted(
        path.parent.glob(path.name + '.bak.*'),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not backups:
        print(f"{C.RED}No backups found for {path.name}{C.END}")
        return False
    latest = backups[0]
    print(f"{C.CYAN}Restoring {path.name} from {latest.name}...{C.END}")
    shutil.copy2(latest, path)
    print(f"{C.GREEN}✓ Restored.{C.END}")
    return True


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════
def patch_bot(bot_path: Path, dry_run: bool) -> int:
    print(f"\n{C.BOLD}{C.BLUE}═══ Patching BOT: {bot_path.name} "
          f"{'═' * (50 - len(bot_path.name))}{C.END}")
    p = FilePatcher(bot_path, dry_run=dry_run)
    if not p.load():
        return 1

    if not dry_run:
        if not p.backup():
            return 1

    # ── Patch B1: insert _extract_tier_entry helper ──
    p.insert_before(
        name="[B1] Insert _extract_tier_entry helper",
        anchor="def fetch_symbol_leverage_tiers(exchange, symbol: str) -> Optional[int]:",
        block=BOT_HELPER_BLOCK,
        marker="def _extract_tier_entry(tiers_raw, symbol: str) -> Optional[Dict]:",
    )

    # ── Patch B2: fetch_symbol_leverage_tiers ──
    p.patch(
        name="[B2] fetch_symbol_leverage_tiers (dict-shape fix)",
        old=BOT_OLD_FETCH_TIERS,
        new=BOT_NEW_FETCH_TIERS,
        marker="[ccxt 4.x FIX] Uses _extract_tier_entry to handle both list and dict",
    )

    # ── Patch B3: _get_mmr_for_symbol ──
    p.patch(
        name="[B3] _get_mmr_for_symbol (dict-shape fix)",
        old=BOT_OLD_MMR,
        new=BOT_NEW_MMR,
        marker="[ccxt 4.x FIX] Uses _extract_tier_entry to handle dict-shaped responses",
    )

    # ── Patch B4: ensure_symbol_setup has_pos ──
    p.patch(
        name="[B4] ensure_symbol_setup has_pos (None-safe fetch_leverage)",
        old=BOT_OLD_SETUP_HASPOS,
        new=BOT_NEW_SETUP_HASPOS,
        marker="[ccxt 4.x FIX] Some exchanges (Binance Demo) return None",
    )

    if not p.save():
        return 1

    return p.report()


def patch_test(test_path: Path, dry_run: bool) -> int:
    print(f"\n{C.BOLD}{C.BLUE}═══ Patching TEST: {test_path.name} "
          f"{'═' * (50 - len(test_path.name))}{C.END}")
    p = FilePatcher(test_path, dry_run=dry_run)
    if not p.load():
        return 1

    if not dry_run:
        if not p.backup():
            return 1

    # ── Patch T1: test_fetch_tickers ──
    p.patch(
        name="[T1] test_fetch_tickers (futures symbol notation)",
        old=TEST_OLD_TICKERS,
        new=TEST_NEW_TICKERS,
        marker="[ccxt 4.x FIX] Binance Futures uses \"BTC/USDT:USDT\" notation",
    )

    # ── Patch T2: test_fetch_leverage_tiers ──
    p.patch(
        name="[T2] test_fetch_leverage_tiers (list/dict normalization)",
        old=TEST_OLD_TIERS,
        new=TEST_NEW_TIERS,
        marker="[ccxt 4.x FIX] Handles both list and dict return shapes",
    )

    if not p.save():
        return 1

    return p.report()


def main():
    p = argparse.ArgumentParser(
        description="Batch patcher: fix ccxt 4.x compatibility issues"
    )
    p.add_argument("--bot", type=str,
                   default="trading_2_mfal2.py",
                   help="Path to the trading bot")
    p.add_argument("--test", type=str,
                   default="exchange_api_test.py",
                   help="Path to the exchange test script")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview changes without writing")
    p.add_argument("--restore", action="store_true",
                   help="Restore both files from their latest backups")
    p.add_argument("--skip-bot", action="store_true",
                   help="Skip patching the bot")
    p.add_argument("--skip-test", action="store_true",
                   help="Skip patching the test script")
    args = p.parse_args()

    bot_path = Path(args.bot).resolve()
    test_path = Path(args.test).resolve()

    print(f"\n{C.BOLD}╔{'═' * 74}╗{C.END}")
    print(f"{C.BOLD}║  ccxt 4.x Compatibility Patcher"
          f"{' ' * 39}║{C.END}")
    print(f"{C.BOLD}║  Mode: "
          f"{'DRY-RUN (no writes)' if args.dry_run else 'APPLY (writes + backup)':<63}"
          f"║{C.END}")
    print(f"{C.BOLD}╚{'═' * 74}╝{C.END}")

    # ── Restore mode ──
    if args.restore:
        ok = True
        if bot_path.exists() and not args.skip_bot:
            ok &= restore_latest(bot_path)
        if test_path.exists() and not args.skip_test:
            ok &= restore_latest(test_path)
        sys.exit(0 if ok else 1)

    # ── Apply patches ──
    total_failures = 0

    if not args.skip_bot:
        if bot_path.exists():
            total_failures += patch_bot(bot_path, args.dry_run)
        else:
            print(f"{C.YELLOW}[Bot] {bot_path.name} not found — "
                  f"skipped{C.END}")

    if not args.skip_test:
        if test_path.exists():
            total_failures += patch_test(test_path, args.dry_run)
        else:
            print(f"{C.YELLOW}[Test] {test_path.name} not found — "
                  f"skipped{C.END}")

    # ── Final summary ──
    print(f"\n{C.BOLD}╔{'═' * 74}╗{C.END}")
    if total_failures == 0:
        print(f"{C.BOLD}║  {C.GREEN}ALL PATCHES APPLIED SUCCESSFULLY"
              f"{C.END}{' ' * 35}║{C.END}")
    else:
        print(f"{C.BOLD}║  {C.RED}{total_failures} PATCH(ES) FAILED"
              f"{C.END}{' ' * 46}║{C.END}")
    print(f"{C.BOLD}╚{'═' * 74}╝{C.END}")

    if args.dry_run:
        print(f"\n{C.YELLOW}This was a dry-run. "
              f"Remove --dry-run to apply.{C.END}")
    elif total_failures == 0:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify syntax: "
              f"{C.BOLD}python3 -m py_compile {bot_path.name}{C.END}")
        print(f"  2. Re-run test:   "
              f"{C.BOLD}python3 exchange_api_test.py --mode testnet "
              f"--api-key $KEY --api-secret $SECRET{C.END}")
        print(f"  3. To revert:     "
              f"{C.BOLD}python3 patch_ccxt4_fixes.py --restore{C.END}")

    sys.exit(0 if total_failures == 0 else 1)


if __name__ == "__main__":
    main()
