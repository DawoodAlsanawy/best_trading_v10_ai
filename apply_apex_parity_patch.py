#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_apex_parity_patch.py
==========================
Fixes the Apex/Topo-Div exit parity gap between backtest and live.

Problem:
    Backtest: Apex/Topo-Div returns immediately at bar close.
    Live    : Apex/Topo-Div placed as GTX post-only → often unfilled
              → position stays open (drifts to SL or MaxHold).

Fix (Solution 1 + Solution 2 combined):
    1. _exit_is_taker(): classify Apex/Topo-Div as taker → apply
       slippage in backtest (parity with live marketable fill).
    2. run_live _urgent: treat Apex/Topo-Div as urgent → cross_spread
       marketable limit (fills as taker, not post-only).
    3. run_live fallback: for Apex/Topo-Div, enable market fallback
       if the marketable limit somehow fails.

Default: ENABLED. Disable via --no-apex-parity if needed.

Usage:
    python3 apply_apex_parity_patch.py            # patch in place
    python3 apply_apex_parity_patch.py --dry-run  # verify only
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime

DEFAULT_FILE = "trading_2_live4_claude2_v4.py"


# ══════════════════════════════════════════════════════════════
# PATCH 1 — Config: new toggle flags
# ══════════════════════════════════════════════════════════════
P1_OLD = (
    "    PO_EXIT_MAX_WAIT_S: int = 12            # was 45 (still used for soft exits)\n"
    "    PO_EXIT_URGENT_WAIT_S: int = 4          # for SL/TP/LiqProximity\n"
    "    PO_EXIT_URGENT_CROSS_SPREAD: bool = True\n"
)
P1_NEW = (
    "    PO_EXIT_MAX_WAIT_S: int = 12            # was 45 (still used for soft exits)\n"
    "    PO_EXIT_URGENT_WAIT_S: int = 4          # for SL/TP/LiqProximity\n"
    "    PO_EXIT_URGENT_CROSS_SPREAD: bool = True\n"
    "    # ══ [APEX-PARITY] Backtest↔Live parity for Apex/Topo-Div exits ══\n"
    "    # Backtest returns immediately at bar close, but live placed\n"
    "    # them as post-only GTX (often unfilled). These flags fix it:\n"
    "    #   - PO_EXIT_APEX_URGENT → treat Apex/Topo-Div as taker exits\n"
    "    #     (apply slippage in backtest, use marketable in live)\n"
    "    #   - PO_EXIT_APEX_MARKET_FALLBACK → market order if marketable\n"
    "    #     somehow fails to fill within the wait window\n"
    "    PO_EXIT_APEX_URGENT: bool = True\n"
    "    PO_EXIT_APEX_MARKET_FALLBACK: bool = True\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 2 — _exit_is_taker: classify Apex/Topo-Div as taker
# ══════════════════════════════════════════════════════════════
P2_OLD = (
    "    r = str(exit_rsn or \"\")\n"
    "    if (\"Emergency\" in r) or (\"Hard TP\" in r) or (\"LiqProximity\" in r):\n"
    "        return True\n"
    "    return False\n"
)
P2_NEW = (
    "    r = str(exit_rsn or \"\")\n"
    "    # [APEX-PARITY] Apex/Topo-Div classified as taker (slippage)\n"
    "    # to match live's marketable-fill behavior when the parity\n"
    "    # flag PO_EXIT_APEX_URGENT is enabled.\n"
    "    _apex_urgent = bool(getattr(CFG, 'PO_EXIT_APEX_URGENT', True))\n"
    "    _apex_match = _apex_urgent and ((\"Apex\" in r) or (\"Topo-Div\" in r))\n"
    "    if ((\"Emergency\" in r) or (\"Hard TP\" in r)\n"
    "            or (\"LiqProximity\" in r) or _apex_match):\n"
    "        return True\n"
    "    return False\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 3 — run_live: add Apex/Topo-Div to _urgent
# ══════════════════════════════════════════════════════════════
P3_OLD = (
    "                    _urgent = (\n"
    "                        'Emergency' in rsn\n"
    "                        or 'Hard TP' in rsn\n"
    "                        or 'LiqProximity' in rsn\n"
    "                    )\n"
)
P3_NEW = (
    "                    # [APEX-PARITY] Apex/Topo-Div urgent when enabled\n"
    "                    _apex_urgent_lv = bool(getattr(\n"
    "                        CFG, 'PO_EXIT_APEX_URGENT', True))\n"
    "                    _urgent = (\n"
    "                        'Emergency' in rsn\n"
    "                        or 'Hard TP' in rsn\n"
    "                        or 'LiqProximity' in rsn\n"
    "                        or (_apex_urgent_lv and (\n"
    "                            ('Apex' in rsn) or ('Topo-Div' in rsn)))\n"
    "                    )\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 4 — run_live: enable market fallback for Apex/Topo-Div
# ══════════════════════════════════════════════════════════════
P4_OLD = (
    "                        result = execute_post_only(\n"
    "                            exchange, sym, s, pos['qty'],\n"
    "                            max_wait_s=_wait,\n"
    "                            fallback_market=False,\n"
    "                            cross_spread=_cross,\n"
    "                            reduce_only=True,   # ← NEW param\n"
    "                        )\n"
)
P4_NEW = (
    "                        # [APEX-PARITY] Market fallback for Apex/Topo-Div\n"
    "                        _apex_fallback = (\n"
    "                            bool(getattr(CFG,\n"
    "                                'PO_EXIT_APEX_MARKET_FALLBACK', True))\n"
    "                            and (('Apex' in rsn) or ('Topo-Div' in rsn))\n"
    "                        )\n"
    "                        result = execute_post_only(\n"
    "                            exchange, sym, s, pos['qty'],\n"
    "                            max_wait_s=_wait,\n"
    "                            fallback_market=_apex_fallback,\n"
    "                            cross_spread=_cross,\n"
    "                            reduce_only=True,\n"
    "                        )\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 5 — CLI argument
# ══════════════════════════════════════════════════════════════
P5_OLD = (
    "    p.add_argument(\"--no-be-escape-ema\", action=\"store_true\",\n"
    "                   help=\"Disable EMA-flip requirement (pure price as \"\n"
    "                        \"trigger — RISKIER)\")\n"
)
P5_NEW = (
    "    p.add_argument(\"--no-be-escape-ema\", action=\"store_true\",\n"
    "                   help=\"Disable EMA-flip requirement (pure price as \"\n"
    "                        \"trigger — RISKIER)\")\n"
    "    p.add_argument(\"--no-apex-parity\", action=\"store_true\",\n"
    "                   help=\"Disable Apex/Topo-Div parity fix (reverts \"\n"
    "                        \"to post-only GTX exits — NOT recommended: \"\n"
    "                        \"live may fail to exit Apex signals)\")\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 6 — CLI wiring + startup log
# ══════════════════════════════════════════════════════════════
P6_OLD = (
    "    if CFG.BREAKEVEN_ESCAPE_ENABLED:\n"
    "        log.info(\n"
    "            f\"[BEEsc] ENABLED | move_R=\"\n"
    "            f\"{CFG.BREAKEVEN_ESCAPE_PRICE_MOVE_R} \"\n"
    "            f\"min_profit_R={CFG.BREAKEVEN_ESCAPE_MIN_PROFIT_R} \"\n"
    "            f\"require_ema={CFG.BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP} \"\n"
    "            f\"ema_lookback={CFG.BREAKEVEN_ESCAPE_EMA_LOOKBACK}\"\n"
    "        )\n"
)
P6_NEW = (
    "    if CFG.BREAKEVEN_ESCAPE_ENABLED:\n"
    "        log.info(\n"
    "            f\"[BEEsc] ENABLED | move_R=\"\n"
    "            f\"{CFG.BREAKEVEN_ESCAPE_PRICE_MOVE_R} \"\n"
    "            f\"min_profit_R={CFG.BREAKEVEN_ESCAPE_MIN_PROFIT_R} \"\n"
    "            f\"require_ema={CFG.BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP} \"\n"
    "            f\"ema_lookback={CFG.BREAKEVEN_ESCAPE_EMA_LOOKBACK}\"\n"
    "        )\n"
    "    # ══ [APEX-PARITY] wiring ══\n"
    "    if getattr(args, \"no_apex_parity\", False):\n"
    "        CFG.PO_EXIT_APEX_URGENT = False\n"
    "        CFG.PO_EXIT_APEX_MARKET_FALLBACK = False\n"
    "        log.warning(\"[Apex-Parity] DISABLED via --no-apex-parity \"\n"
    "                    \"(NOT recommended: live may fail to exit Apex)\")\n"
    "    else:\n"
    "        log.info(\n"
    "            f\"[Apex-Parity] ENABLED | urgent=\"\n"
    "            f\"{CFG.PO_EXIT_APEX_URGENT} \"\n"
    "            f\"market_fallback={CFG.PO_EXIT_APEX_MARKET_FALLBACK} \"\n"
    "            f\"(Apex/Topo-Div → taker exits in backtest, \"\n"
    "            f\"marketable+fallback in live)\"\n"
    "        )\n"
)


PATCHES = [
    ("P1_CONFIG", "Config: PO_EXIT_APEX_URGENT + MARKET_FALLBACK", P1_OLD, P1_NEW),
    ("P2_TAKER",  "Classify Apex/Topo-Div as taker", P2_OLD, P2_NEW),
    ("P3_URGENT", "Add Apex/Topo-Div to _urgent in live", P3_OLD, P3_NEW),
    ("P4_FALLB",  "Market fallback for Apex/Topo-Div exits", P4_OLD, P4_NEW),
    ("P5_ARGS",   "Add --no-apex-parity CLI flag", P5_OLD, P5_NEW),
    ("P6_WIRE",   "CLI wiring + startup log", P6_OLD, P6_NEW),
]


def _count(haystack, needle):
    c = 0
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return c
        c += 1
        start = idx + len(needle)


def apply_patches(src_text):
    # Idempotency guard
    if "PO_EXIT_APEX_URGENT" in src_text:
        raise RuntimeError(
            "Patch already applied (found PO_EXIT_APEX_URGENT). "
            "Restore from a backup before re-applying.")

    text = src_text
    applied = []
    for pid, desc, old, new in PATCHES:
        n = _count(text, old)
        if n == 0:
            raise RuntimeError(
                f"[{pid}] anchor NOT FOUND: {desc}\n"
                f"  anchor preview (first 200 chars):\n"
                f"  {old[:200]!r}\n"
                f"  File may be from a different version.")
        if n > 1:
            raise RuntimeError(
                f"[{pid}] anchor AMBIGUOUS ({n} matches): {desc}\n"
                f"  preview: {old[:200]!r}")
        text = text.replace(old, new, 1)
        applied.append((pid, desc))
        print(f"  [OK]   {pid:11s} — {desc}")
    return text, applied


def verify_syntax(text):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"


def main():
    ap = argparse.ArgumentParser(
        description="Apply Apex/Topo-Div parity fix.")
    ap.add_argument("--file", default=DEFAULT_FILE,
                    help=f"Source file (default: {DEFAULT_FILE})")
    ap.add_argument("--output", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: file not found: {args.file}")
        sys.exit(1)

    print(f"Reading {args.file}...")
    with open(args.file, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"  size: {len(src):,} bytes\n")

    print("Applying 6 patches...")
    try:
        new_text, applied = apply_patches(src)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print(f"\n{len(applied)}/6 patches applied.\n")

    print("Verifying syntax...")
    ok, err = verify_syntax(new_text)
    if not ok:
        print(f"  FAIL: {err}")
        print("  No files were written. Original untouched.")
        sys.exit(1)
    print("  OK: ast.parse passed.\n")

    if args.dry_run:
        print("[dry-run] No files written.")
        sys.exit(0)

    if args.output is None and not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{args.file}.bak.{ts}"
        shutil.copy2(args.file, backup)
        print(f"Backup saved: {backup}")

    out_path = args.output or args.file
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"Wrote: {out_path}  ({len(new_text):,} bytes)\n")

    print("=" * 70)
    print("  DONE — Apex/Topo-Div parity fix applied")
    print("=" * 70)
    print()
    print("What changed:")
    print("  1. _exit_is_taker()  → Apex/Topo-Div classified as taker")
    print("     (backtest now applies slippage to match live fills)")
    print("  2. run_live _urgent  → Apex/Topo-Div urgent → marketable")
    print("     limit (fills as taker, not post-only)")
    print("  3. fallback_market   → market order if marketable still")
    print("     fails (extra safety)")
    print()
    print("New CLI flag:")
    print("  --no-apex-parity  → disable fix (reverts to old behavior)")
    print("                      (NOT recommended)")
    print()
    print("Default: ENABLED — no flags needed, works automatically.")
    print()
    print("Test backtest (results should now differ slightly from")
    print("previous baseline — Apex/Topo-Div exits pay slippage):")
    print("  python3 trading_2_live4_claude2_v4.py --mode backtest ...")
    print()
    print("Verify in log:")
    print("  grep 'Apex-Parity' qtt6.log")


if __name__ == "__main__":
    main()
