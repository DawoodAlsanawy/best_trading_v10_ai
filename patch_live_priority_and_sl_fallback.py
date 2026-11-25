#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch script #6:
  1. Fix inverted signal priority in run_live: replace `reversed(sigs)`
     with sorting by (timestamp DESC, score DESC) so Live selects the
     HIGHEST-score signals first (matching backtest) rather than weakest.
  2. Enable market fallback (reduceOnly) on `Emergency SL` exits if
     execute_post_only fails to fill within PO_EXIT_URGENT_WAIT_S.

Usage:
  python patch_live_priority_and_sl_fallback.py --dry-run
  python patch_live_priority_and_sl_fallback.py
"""

import argparse
import os
import py_compile
import shutil
import sys
from datetime import datetime

PATCH_MARKER = "# [LIVE-PRIORITY-SL-FALLBACK-APPLIED]"


def _default_target() -> str:
    for cand in (
        "trading_published_pro_1h_fixed_LV_v3.py",
        "trading_published_pro_1h_fixed_LV_v3.py",
        "trading_published_pro_1h_fixed_LV_v3.py",
    ):
        if os.path.exists(cand):
            return cand
    return "trading_published_pro_1h_fixed_LV.py"


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
        (
            "patch marker 6",
            "# [LIVE-SIGNAL-ONCE-APPLIED]",
            "# [LIVE-SIGNAL-ONCE-APPLIED]\n" + PATCH_MARKER,
        ),
        (
            "run_live signal priority (highest score first)",
            r'''                for sig in reversed(sigs):
                    sym = sig.symbol''',
            r'''                _ordered_sigs = sorted(
                    sigs,
                    key=lambda s: (s.timestamp, s.score),
                    reverse=True,
                )
                for sig in _ordered_sigs:
                    sym = sig.symbol''',
        ),
        (
            "run_live Emergency SL market fallback",
            r'''                        # [APEX-PARITY] Market fallback for Apex/Topo-Div
                        _apex_fallback = (
                            bool(getattr(CFG,
                                'PO_EXIT_APEX_MARKET_FALLBACK', True))
                            and (('Apex' in rsn) or ('Topo-Div' in rsn))
                        )
                        result = execute_post_only(
                            exchange, sym, s, pos['qty'],
                            max_wait_s=_wait,
                            fallback_market=_apex_fallback,
                            cross_spread=_cross,
                            reduce_only=True,
                        )''',
            r'''                        # [APEX-PARITY + SL-SAFETY] Market fallback for Apex/Topo-Div & Emergency SL
                        _apex_fallback = (
                            bool(getattr(CFG,
                                'PO_EXIT_APEX_MARKET_FALLBACK', True))
                            and (('Apex' in rsn) or ('Topo-Div' in rsn))
                        )
                        _sl_fallback = (
                            bool(getattr(CFG, 'PO_EXIT_FALLBACK_MARKET', True))
                            and ('Emergency' in rsn)
                        )
                        result = execute_post_only(
                            exchange, sym, s, pos['qty'],
                            max_wait_s=_wait,
                            fallback_market=(_apex_fallback or _sl_fallback),
                            cross_spread=_cross,
                            reduce_only=True,
                        )''',
        ),
    ]

    for name, old, _ in replacements:
        cnt = src.count(old)
        if cnt != 1:
            print(
                f"[ERROR] Hunk '{name}' matched {cnt} times (expected 1). Aborting.",
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
        py_compile.compile(tmp_path, doraise=True)
        os.replace(tmp_path, target_path)
        print(f"[SUCCESS] Patched & syntax-verified: {target_path}")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"[ERROR] Verification failed, original file untouched: {e}", file=sys.stderr)
        sys.exit(3)


def main():
    parser = argparse.ArgumentParser(description="Fix Live signal priority and Emergency SL market fallback")
    parser.add_argument("--target", default=_default_target(), help="Path to target script")
    parser.add_argument("--dry-run", action="store_true", help="Verify matches without modifying file")
    args = parser.parse_args()
    apply_patch(args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
