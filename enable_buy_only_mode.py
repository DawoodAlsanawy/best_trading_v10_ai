#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enable_buy_only_mode.py — تفعيل BUY-only كإعداد افتراضي.

التغييرات:
  1. Config: GAUGE_DISABLE_SELL = False → True
  2. CLI: إضافة --enable-sell للعكس (اختياري للاختبار)
  3. main(): ربط --enable-sell
  4. TradeLog: تسجيل الحالة

التشغيل:
  python3 enable_buy_only_mode.py --dry-run
  python3 enable_buy_only_mode.py
"""

import argparse
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Patch 1: Config default
# ═══════════════════════════════════════════════════════════════

P1_OLD = '    GAUGE_DISABLE_SELL: bool = False   # True → BUY-only mode'
P1_NEW = (
    '    # [ABL10] confirmed BUY-only across 2024/2025/2026:\n'
    '    # Min Sharpe 1.606 (vs 0.937 baseline), GeoFinal $1,873\n'
    '    GAUGE_DISABLE_SELL: bool = True    # Default: BUY-only'
)
P1_MARK = '# [ABL10] confirmed BUY-only'


# ═══════════════════════════════════════════════════════════════
# Patch 2: CLI flag --enable-sell
# ═══════════════════════════════════════════════════════════════

P2_OLD = '''    p.add_argument("--gauge-disable-sell", action="store_true",
                   help="Disable SELL entirely (BUY-only mode)")'''
P2_NEW = '''    p.add_argument("--gauge-disable-sell", action="store_true",
                   help="[DEPRECATED] SELL already disabled by default")
    p.add_argument("--enable-sell", action="store_true",
                   help="Re-enable SELL signals (default: BUY-only)")'''
P2_MARK = 'p.add_argument("--enable-sell"'


# ═══════════════════════════════════════════════════════════════
# Patch 3: main() wiring
# ═══════════════════════════════════════════════════════════════

P3_OLD = '''    if args.gauge_disable_sell:
        CFG.GAUGE_DISABLE_SELL = True
        log.info("[Gauge] SELL DISABLED — BUY-only mode")'''
P3_NEW = '''    if args.gauge_disable_sell:
        CFG.GAUGE_DISABLE_SELL = True
        log.info("[Gauge] SELL DISABLED — BUY-only mode")
    if getattr(args, "enable_sell", False):
        CFG.GAUGE_DISABLE_SELL = False
        log.info("[Gauge] SELL RE-ENABLED — experimental mode")'''
P3_MARK = 'log.info("[Gauge] SELL RE-ENABLED'


# ═══════════════════════════════════════════════════════════════
# Patch 4: TradeLog meta
# ═══════════════════════════════════════════════════════════════

P4_OLD = '''                'PO_FIXED_PRICE': CFG.PO_FIXED_PRICE,
            }, default=str) + "\\n")'''
P4_NEW = '''                'PO_FIXED_PRICE': CFG.PO_FIXED_PRICE,
                'GAUGE_DISABLE_SELL': CFG.GAUGE_DISABLE_SELL,
                'TRAIL_ENABLED': CFG.TRAIL_ENABLED,
            }, default=str) + "\\n")'''
P4_MARK = "'GAUGE_DISABLE_SELL': CFG.GAUGE_DISABLE_SELL"


# ═══════════════════════════════════════════════════════════════

def apply(text, old, new, marker, name):
    if marker in text:
        return text, f"SKIP: {name}"
    if old not in text:
        return text, f"ERR: {name} (anchor not found)"
    text = text.replace(old, new, 1)
    return text, f"OK: {name}"


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
    print("  enable_buy_only_mode.py")
    print("=" * 70)
    print()

    text, s = apply(text, P1_OLD, P1_NEW, P1_MARK, "Config default")
    print(f"  {s}")

    text, s = apply(text, P2_OLD, P2_NEW, P2_MARK, "CLI --enable-sell")
    print(f"  {s}")

    text, s = apply(text, P3_OLD, P3_NEW, P3_MARK, "main() wiring")
    print(f"  {s}")

    text, s = apply(text, P4_OLD, P4_NEW, P4_MARK, "TradeLog meta")
    print(f"  {s}")

    try:
        ast.parse(text)
        print()
        print("  OK: ast.parse passed")
    except SyntaxError as e:
        print(f"\n  ERR: syntax error at line {e.lineno}: {e.text}")
        return 3

    if text == original:
        print("\n  No changes")
        return 0

    if args.dry_run:
        print()
        print("=" * 70)
        print("  Dry run - nothing written")
        print("=" * 70)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_buyonly_{ts}')
    shutil.copy2(p, backup)
    print()
    print(f"  Backup: {backup}")

    p.write_text(text, encoding='utf-8')
    print(f"  Written: {p}")
    print()
    print("=" * 70)
    print("  Done")
    print("=" * 70)
    print(f"  Rollback: cp {backup.name} {p.name}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
