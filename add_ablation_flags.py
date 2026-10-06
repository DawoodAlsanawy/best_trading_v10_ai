#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_ablation_flags.py — إضافة flags للتحكم بعناصر الحافة.

إضافات:
  --no-apex           إيقاف Apex exit
  --no-partial        إيقاف Partial TP
  --no-breakeven      إيقاف Breakeven SL
  --tp-mult N         تعديل TP_MULT
  --sell-only         تداول SELL فقط (عكس --gauge-disable-sell)
"""

import argparse
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ═══ Patch 1: Config field GAUGE_DISABLE_BUY ═══

P1_OLD = '    GAUGE_DISABLE_SELL: bool = False   # True → BUY-only mode'
P1_NEW = ('    GAUGE_DISABLE_SELL: bool = False   # True → BUY-only mode\n'
          '    GAUGE_DISABLE_BUY: bool = False    # True → SELL-only mode')
P1_MARK = 'GAUGE_DISABLE_BUY: bool'


# ═══ Patch 2: build_signals hook ═══

P2_OLD = '''            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):
                if action == "SELL" and getattr(CFG, 'GAUGE_DISABLE_SELL', False):
                    continue'''
P2_NEW = '''            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):
                if action == "SELL" and getattr(CFG, 'GAUGE_DISABLE_SELL', False):
                    continue
                if action == "BUY" and getattr(CFG, 'GAUGE_DISABLE_BUY', False):
                    continue'''
P2_MARK = "action == \"BUY\" and getattr(CFG, 'GAUGE_DISABLE_BUY'"


# ═══ Patch 3: argparse flags ═══

P3_OLD = '    p.add_argument("--gauge-disable-sell", action="store_true",\n' \
         '                   help="Disable SELL entirely (BUY-only mode)")'
P3_NEW = ('    p.add_argument("--gauge-disable-sell", action="store_true",\n'
          '                   help="Disable SELL entirely (BUY-only mode)")\n'
          '    # ═══ [ABLATION-FLAGS] ═══\n'
          '    p.add_argument("--no-apex", action="store_true",\n'
          '                   help="Disable Apex exit")\n'
          '    p.add_argument("--no-partial", action="store_true",\n'
          '                   help="Disable Partial TP")\n'
          '    p.add_argument("--no-breakeven", action="store_true",\n'
          '                   help="Disable Breakeven SL")\n'
          '    p.add_argument("--tp-mult", type=float, default=None,\n'
          '                   help="Override TP_MULT")\n'
          '    p.add_argument("--sell-only", action="store_true",\n'
          '                   help="SELL-only mode (opposite of --gauge-disable-sell)")')
P3_MARK = 'p.add_argument("--no-apex"'


# ═══ Patch 4: main() wiring ═══

P4_OLD = '    if args.gauge_disable_sell:\n' \
         '        CFG.GAUGE_DISABLE_SELL = True\n' \
         '        log.info("[Gauge] SELL DISABLED — BUY-only mode")'
P4_NEW = ('    if args.gauge_disable_sell:\n'
          '        CFG.GAUGE_DISABLE_SELL = True\n'
          '        log.info("[Gauge] SELL DISABLED — BUY-only mode")\n'
          '    # ═══ [ABLATION-FLAGS] ═══\n'
          '    if getattr(args, "no_apex", False):\n'
          '        CFG.APEX_ENABLED = False\n'
          '        log.info("[Ablation] APEX DISABLED")\n'
          '    if getattr(args, "no_partial", False):\n'
          '        CFG.PARTIAL_TP_ENABLED = False\n'
          '        log.info("[Ablation] PARTIAL_TP DISABLED")\n'
          '    if getattr(args, "no_breakeven", False):\n'
          '        CFG.BREAKEVEN_ENABLED = False\n'
          '        log.info("[Ablation] BREAKEVEN DISABLED")\n'
          '    if getattr(args, "tp_mult", None) is not None:\n'
          '        CFG.TP_MULT = float(args.tp_mult)\n'
          '        log.info(f"[Ablation] TP_MULT = {CFG.TP_MULT}")\n'
          '    if getattr(args, "sell_only", False):\n'
          '        CFG.GAUGE_DISABLE_BUY = True\n'
          '        log.info("[Ablation] BUY DISABLED — SELL-only mode")')
P4_MARK = 'if getattr(args, "no_apex", False)'


# ═══ Apply engine ═══

def apply(text, old, new, mark, name):
    if mark in text:
        return text, f"SKIP: {name}"
    if old not in text:
        return text, f"ERR: {name} (anchor not found)"
    return text.replace(old, new, 1), f"OK: {name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"ERR: {args.file} not found")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("=" * 70)
    print("  add_ablation_flags.py")
    print("=" * 70)
    print()

    for old, new, mark, name in [
        (P1_OLD, P1_NEW, P1_MARK, "Config field GAUGE_DISABLE_BUY"),
        (P2_OLD, P2_NEW, P2_MARK, "build_signals hook"),
        (P3_OLD, P3_NEW, P3_MARK, "argparse flags"),
        (P4_OLD, P4_NEW, P4_MARK, "main() wiring"),
    ]:
        text, s = apply(text, old, new, mark, name)
        print(f"  {s}")

    try:
        ast.parse(text)
        print("\n  OK: ast.parse passed")
    except SyntaxError as e:
        print(f"\n  ERR: syntax error at line {e.lineno}: {e.text}")
        return 3

    if text == original:
        print("\n  No changes.")
        return 0

    if args.dry_run:
        print("\n" + "=" * 70)
        print("  Dry run — nothing written")
        print("=" * 70)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_abl_{ts}')
    shutil.copy2(p, backup)
    print(f"\n  Backup: {backup}")

    p.write_text(text, encoding='utf-8')
    print(f"  Written: {p}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
