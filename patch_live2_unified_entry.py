#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_live2_unified_entry.py                                            ║
║  Unified entry logic between backtest and live                           ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Fixes:                                                                  ║
║    U1  Insert _compute_entry_target (single source of truth)             ║
║    U2  _backtest_entry_target delegates to _compute_entry_target         ║
║    U3  place_pending_entry (live) delegates to _compute_entry_target     ║
║                                                                          ║
║  Effect:                                                                 ║
║    * Direction fixed for --no-fixed-price: BUY below, SELL above         ║
║    * Same dynamic offset (tick / sigma_bar / ADV) in both modes          ║
║    * PO_FIXED_PRICE=True also unified (sig.price in both)                ║
║    * Sanity gate stays live-only (backtest has no live mid)              ║
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
# U1 — Insert _compute_entry_target before _backtest_entry_target
# ══════════════════════════════════════════════════════════════════════════

U1_ANCHOR = '''def _backtest_entry_target(sig, ad) -> float:'''

U1_BLOCK = '''def _compute_entry_target(sig, ad, side, exchange=None) -> float:
    """
    [UNIFIED-ENTRY] Single source of truth for entry pricing in BOTH
    backtest and live.

    Two modes, controlled by CFG.PO_FIXED_PRICE:

      PO_FIXED_PRICE = True:
          target = sig.price   (the tunnel price, no offset)
          Backtest and live both use the exact same value.

      PO_FIXED_PRICE = False (--no-fixed-price):
          base   = close[sig.close_idx]
          offset = dynamic (tick / sigma_bar / ADV)
          Direction is mean-reversion:
              BUY : target = base - offset   (below -> wait for a dip)
              SELL: target = base + offset   (above -> wait for a rally)

    The offset function _watch_compute_entry_offset is shared with the
    live Watch mode. With exchange=None (backtest) it uses a pure-bps
    tick fallback so the result is deterministic and reproducible.
    """
    # ── PO_FIXED_PRICE path (identical in backtest and live) ──
    if getattr(CFG, 'PO_FIXED_PRICE', True):
        return float(sig.price)

    # ── --no-fixed-price path ──
    _base = float(sig.price)
    try:
        _ci = int(getattr(sig, 'close_idx', -1))
        if ad is not None and 0 <= _ci < len(ad.closes):
            _base = float(ad.closes[_ci])
    except Exception:
        pass

    _sigma = 0.01
    try:
        _fi = int(getattr(sig, 'feat_idx', -1))
        if ad is not None and 0 <= _fi < len(ad.E_therm):
            _s = float(ad.E_therm[_fi])
            if np.isfinite(_s) and _s > 1e-6:
                _sigma = _s
    except Exception:
        pass

    _adv = 1e8
    try:
        _ci = int(getattr(sig, 'close_idx', -1))
        if ad is not None and 0 <= _ci < len(ad.adv_usd):
            _adv = float(ad.adv_usd[_ci])
    except Exception:
        pass

    _off = _watch_compute_entry_offset(
        tunnel_p=_base,
        sigma_bar=_sigma,
        adv_usd=_adv,
        exchange=exchange,
        symbol=(getattr(sig, 'symbol', None)
                if exchange is not None else None),
        qty=0.0,
    )

    # Direction: mean-reversion
    #   BUY  -> below market (wait for a dip)
    #   SELL -> above market (wait for a rally)
    if side == 'buy':
        return float(_base - _off)
    return float(_base + _off)


def _backtest_entry_target(sig, ad) -> float:'''


# ══════════════════════════════════════════════════════════════════════════
# U2 — _backtest_entry_target delegates
# ══════════════════════════════════════════════════════════════════════════

U2_OLD = '''def _backtest_entry_target(sig, ad) -> float:
    """
    Limit order target in backtest — mirrors Live's two pricing modes.

    PO_FIXED_PRICE=True (default):
        target = sig.price   (the tunnel / phase-matched price)

    PO_FIXED_PRICE=False (--no-fixed-price):
        target ≈ the live best bid/ask at placement time:
          BUY:  closes[sig.close_idx] × (1 − pen_frac)
          SELL: closes[sig.close_idx] × (1 + pen_frac)
        where pen_frac = PO_PENETRATION_BPS × 1e-4.

    Bar-level proxy for Live's live order-book fetch.
    """
    if getattr(CFG, 'PO_FIXED_PRICE', True):
        return float(sig.price)
    try:
        _close_at_sig = float(ad.closes[int(sig.close_idx)])
        _pen_frac = float(getattr(CFG, 'PO_PENETRATION_BPS', 1.0)) * 1e-4
        if sig.action == "BUY":
            return _close_at_sig * (1.0 - _pen_frac)
        else:
            return _close_at_sig * (1.0 + _pen_frac)
    except Exception:
        return float(sig.price)'''

U2_NEW = '''def _backtest_entry_target(sig, ad) -> float:
    """[UNIFIED-ENTRY] Delegates to _compute_entry_target (single source)."""
    _side = 'buy' if sig.action == "BUY" else 'sell'
    return _compute_entry_target(sig, ad, _side, exchange=None)'''


# ══════════════════════════════════════════════════════════════════════════
# U3 — place_pending_entry (live) delegates
# ══════════════════════════════════════════════════════════════════════════

U3_OLD = '''    # ══ تحديد الـ target ══
    if explicit_target is not None and explicit_target > 0:
        # Watch mode: يُمرَّر جاهزاً
        target = float(explicit_target)
    elif getattr(CFG, 'PO_FIXED_PRICE', True):
        # Base = tunnel، offset outward
        if side == 'buy':
            target = float(sig.price) + _dyn_offset
        else:
            target = float(sig.price) - _dyn_offset
    else:
        # --no-fixed-price: Base = close[sig.close_idx]، offset outward
        try:
            _base = float(sig.price)
            if ad is not None and hasattr(ad, 'closes'):
                _ci = int(getattr(sig, 'close_idx', -1))
                if 0 <= _ci < len(ad.closes):
                    _base = float(ad.closes[_ci])

            if side == 'buy':
                target = _base + _dyn_offset
            else:
                target = _base - _dyn_offset

            # Sanity gate
            try:
                ob = exchange.fetch_order_book(sym, limit=5)
                _mid = (float(ob['bids'][0][0])
                        + float(ob['asks'][0][0])) / 2.0
                if _mid > 0:
                    _gap_bps = abs(target - _mid) / _mid * 1e4
                    _max_gap = float(
                        getattr(CFG, 'PO_MAX_DRIFT_BPS', 5.0)
                    ) * 4.0
                    if _gap_bps > _max_gap:
                        log.info(
                            f"[Pending] {sym} target {target:.6f} "
                            f"is {_gap_bps:.1f}bps from mid "
                            f"(> {_max_gap:.1f}) — skip"
                        )
                        return None
            except Exception:
                pass
        except Exception as e:
            log.warning(
                f"[Pending] {sym} offset computation failed: {e} — "
                f"falling back to sig.price ± fixed pen"
            )
            _fallback_pen = max(pen, 1e-5)
            target = (float(sig.price) * (1.0 - _fallback_pen)
                      if side == 'buy'
                      else float(sig.price) * (1.0 + _fallback_pen))'''

U3_NEW = '''    # ══ [UNIFIED-ENTRY] Target via _compute_entry_target ══
    # Same function used by the backtest -> no divergence.
    if explicit_target is not None and explicit_target > 0:
        # Watch mode passes the price ready-made
        target = float(explicit_target)
    else:
        try:
            target = _compute_entry_target(sig, ad, side,
                                            exchange=exchange)
        except Exception as e:
            log.warning(
                f"[Pending] {sym} unified target computation failed: "
                f"{e} — falling back to sig.price ± fixed pen"
            )
            _fallback_pen = max(pen, 1e-5)
            target = (float(sig.price) * (1.0 - _fallback_pen)
                      if side == 'buy'
                      else float(sig.price) * (1.0 + _fallback_pen))

        # Sanity gate: live-only (backtest has no live mid).
        # Applies in --no-fixed-price mode only.
        if not getattr(CFG, 'PO_FIXED_PRICE', True):
            try:
                ob = exchange.fetch_order_book(sym, limit=5)
                _mid = (float(ob['bids'][0][0])
                        + float(ob['asks'][0][0])) / 2.0
                if _mid > 0:
                    _gap_bps = abs(target - _mid) / _mid * 1e4
                    _max_gap = float(
                        getattr(CFG, 'PO_MAX_DRIFT_BPS', 5.0)
                    ) * 4.0
                    if _gap_bps > _max_gap:
                        log.info(
                            f"[Pending] {sym} target {target:.6f} "
                            f"is {_gap_bps:.1f}bps from mid "
                            f"(> {_max_gap:.1f}) — skip"
                        )
                        return None
            except Exception:
                pass'''


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

    def save(self):
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN -- not written{C.END}")
            return True
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
    p.add_argument("--bot", default="trading_2_live2.py")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.BOLD}  Unified-Entry Patcher -- {bot.name}{C.END}")
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
    pt.replace("U1   Insert _compute_entry_target",
               U1_ANCHOR, U1_BLOCK,
               marker="def _compute_entry_target(sig, ad, side, exchange=None) -> float:")

    pt.replace("U2   _backtest_entry_target delegates",
               U2_OLD, U2_NEW,
               marker='"""\'[UNIFIED-ENTRY] Delegates to _compute_entry_target (single source).\'"""')

    pt.replace("U3   place_pending_entry (live) delegates",
               U3_OLD, U3_NEW,
               marker="# ══ [UNIFIED-ENTRY] Target via _compute_entry_target ══")

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
        print(f"  2. Grep:    grep -n 'UNIFIED-ENTRY' {bot.name}")
        print(f"  3. Sanity check:")
        print(f"     - Backtest BUY uses  base = close[sig.close_idx] - offset")
        print(f"     - Backtest SELL uses base = close[sig.close_idx] + offset")
        print(f"     - Live      uses the SAME _compute_entry_target")
        print(f"  4. Revert:  python3 {Path(__file__).name} --restore")


if __name__ == "__main__":
    main()
