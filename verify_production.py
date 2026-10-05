#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_production.py — تحقق شامل من سلامة البوت النهائي.

يتأكد من:
  1. كل الإصلاحات الحرجة موجودة
  2. الإعدادات صحيحة (BUY-only)
  3. الصياغة سليمة
  4. checksum يطابق المرجع
"""

import re
import sys
import ast
import hashlib
from pathlib import Path

PROD = "trading_prod_buy_only.py"
REF = "trading_prod_buy_only.py.v1.0_production"

REQUIRED_PATTERNS = [
    ("GAUGE_DISABLE_SELL = True",
     r"GAUGE_DISABLE_SELL:\s*bool\s*=\s*True"),
    ("SELL_ENABLED = False",
     r"SELL_ENABLED:\s*bool\s*=\s*False"),
    ("WATCH_REMOVED = True",
     r"^WATCH_REMOVED\s*=\s*True"),
    ("--end-date flag",
     r'p\.add_argument\("--end-date"'),
    ("--live-capital flag",
     r'p\.add_argument\("--live-capital"'),
    ("LIVE_TRADING_CAPITAL field",
     r"LIVE_TRADING_CAPITAL:\s*float\s*=\s*0\.0"),
    ("BACKTEST_END_DATE field",
     r"BACKTEST_END_DATE:\s*Optional\[str\]"),
    ("_resolve_end_datetime helper",
     r"def _resolve_end_datetime"),
    ("Watch-then-trigger DISABLED log",
     r"Watch-then-trigger DISABLED \(Config default\)"),
    ("net_pnl logging fix",
     r"net_pnl=float\(_net_pnl_lg\)"),
    ("Partial TP taker fee fix",
     r"_exit_fee\s*=\s*_close_qty \* px \* CFG\.TAKER_FEE"),
    ("_promote_pending signature fix",
     r"_promote_pending_to_position\(exchange, sym, rec2"),
    ("Duplicate-orders fix (2-pass cancel)",
     r"\[DUPLICATE-FIX\] two-pass cancel"),
    ("Apex pos dict fix",
     r"pos\['action'\], pos\['entry'\], price, ad, fi"),
]

FORBIDDEN_PATTERNS = [
    ("BUY_DISABLED = True (should NOT be)",
     r"BUY_DISABLED:\s*bool\s*=\s*True"),
    ("Old buggy capital source",
     r"cap_live = float\(bal\['USDT'\]\['free'\]\)"),
    ("Old apex sig.action bug",
     r"sig\.action, pos\.entry_px, p, ad, fi"),
    ("Old cancel (no two-pass)",
     r"def _cancel_all_protective_orders\(exchange, sym: str\) -> int:\n"
     r"    \"\"\"\n    Cancel every STOP_MARKET"),
]


def main():
    p = Path(PROD)
    if not p.exists():
        print(f"❌ {PROD} غير موجود")
        return 1

    text = p.read_text(encoding="utf-8")
    size_kb = len(text) / 1024

    print("═" * 72)
    print("  verify_production.py")
    print("═" * 72)
    print(f"\n  File: {PROD}")
    print(f"  Size: {size_kb:.1f} KB")
    print(f"  Lines: {len(text.splitlines()):,}")
    print()

    # ── 1. Required patterns ──
    print("  ▶ Required fixes:")
    missing = []
    for name, pat in REQUIRED_PATTERNS:
        if re.search(pat, text, re.MULTILINE):
            print(f"    ✅ {name}")
        else:
            print(f"    ❌ {name}  ← MISSING")
            missing.append(name)

    # ── 2. Forbidden patterns ──
    print()
    print("  ▶ Forbidden patterns (must NOT exist):")
    forbidden_found = []
    for name, pat in FORBIDDEN_PATTERNS:
        if re.search(pat, text, re.MULTILINE):
            print(f"    ❌ {name}  ← FOUND (bad!)")
            forbidden_found.append(name)
        else:
            print(f"    ✅ {name} (not present)")

    # ── 3. Syntax check ──
    print()
    print("  ▶ Syntax check:")
    try:
        ast.parse(text)
        print(f"    ✅ ast.parse OK")
    except SyntaxError as e:
        print(f"    ❌ SyntaxError at line {e.lineno}: {e.text}")
        return 1

    # ── 4. Checksum ──
    print()
    print("  ▶ Checksum:")
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"    sha256: {sha256}")

    ref = Path(REF)
    if ref.exists():
        ref_text = ref.read_text(encoding="utf-8")
        ref_sha = hashlib.sha256(ref_text.encode("utf-8")).hexdigest()
        if sha256 == ref_sha:
            print(f"    ✅ matches reference {REF}")
        else:
            print(f"    ⚠️  differs from reference {REF}")
            print(f"       ref sha256: {ref_sha}")
    else:
        print(f"    ⚠️  Reference not found: {REF}")

    # ── 5. Final verdict ──
    print()
    print("═" * 72)
    if not missing and not forbidden_found:
        print("  ✅ PRODUCTION BOT READY")
        print("═" * 72)
        return 0
    else:
        print("  ❌ VERIFICATION FAILED")
        if missing:
            print(f"     Missing fixes: {len(missing)}")
        if forbidden_found:
            print(f"     Forbidden patterns: {len(forbidden_found)}")
        print("═" * 72)
        return 1


if __name__ == "__main__":
    sys.exit(main())
