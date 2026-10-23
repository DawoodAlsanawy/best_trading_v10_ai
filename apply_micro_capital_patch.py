#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_micro_capital_patch.py
=============================
Enables $1 micro-capital support in the bot.

Changes (23 patches total):
    • 19 Config value updates (risk, leverage, drawdown thresholds)
    • 1 Backtest MIN_NOTIONAL forcing (first check, opt_px)
    • 1 Backtest MIN_NOTIONAL forcing (second check, eff_px)
    • 1 Live MIN_NOTIONAL forcing
    • 1 Symbol filter in scan_top_assets (excludes BTC/ETH etc.)

All patches are:
    ✓ Idempotent (safe to re-run)
    ✓ Reversible (backup written automatically)
    ✓ Syntax-verified (ast.parse check before write)
    ✓ Gated on INITIAL_CAPITAL < 20 for the symbol filter

⚠️  WARNING: Micro-capital mode is EXPERIMENTAL.
    • Each trade risks 8-15% of capital
    • Fees consume 30-50% of profits
    • 5 consecutive losses = -50% to -67%
    • Test on Testnet for at least 2 weeks first

Usage:
    python3 apply_micro_capital_patch.py --file trading_2_live4_claude2_v4_micro.py --dry-run
    python3 apply_micro_capital_patch.py --file trading_2_live4_claude2_v4_micro.py
"""

import argparse
import ast
import os
import re
import shutil
import sys
from datetime import datetime

DEFAULT_FILE = "trading_2_live4_claude2_v4_micro.py"


# ══════════════════════════════════════════════════════════════
# PART 1 — Config value changes (regex-based, 19 fields)
# ══════════════════════════════════════════════════════════════
# (field_name, new_value, note)
CONFIG_CHANGES = [
    ("INITIAL_CAPITAL",       "1.0",   "was 10.0 → $1 start"),
    ("CAPITAL_FLOOR",         "0.05",  "was 0.15 → lower floor"),
    ("MIN_RISK_PER_TRADE",    "0.08",  "was 0.005 → 8% min"),
    ("MAX_RISK_PER_TRADE",    "0.15",  "was 0.030 → 15% max"),
    ("BASE_RISK",             "0.10",  "was 0.02 → 10% base"),
    ("MIN_RISK",              "0.08",  "was 0.01 → 8% min"),
    ("MAX_RISK",              "0.15",  "was 0.05 → 15% max"),
    ("PORTFOLIO_HEAT_MAX",    "0.30",  "was 0.10 → 30% heat"),
    ("MAX_CONCURRENT_ASSETS", "2",     "was 3 → 2 slots"),
    ("LEVERAGE_MIN",          "20",    "was 5 → 20x min"),
    ("LEVERAGE_BASE",         "25.0",  "was 50.0 → 25x base"),
    ("LIQ_SAFETY_MULT",       "2.5",   "was 1.5 → wider liq margin"),
    ("DRAWDOWN_REDUCE_AT",    "0.30",  "was 0.15 → 30% trigger"),
    ("DRAWDOWN_REDUCE_AT_50", "0.60",  "was 0.30 → 60% trigger"),
    ("DRAWDOWN_REDUCE_AT_70", "0.80",  "was 0.50 → 80% trigger"),
    ("REDUCED_RISK_MULT",     "0.50",  "was 0.25 → 50% reduction"),
    ("REDUCED_RISK_MULT_50",  "0.25",  "was 0.10 → 25% reduction"),
    ("REDUCED_RISK_MULT_70",  "0.10",  "was 0.05 → 10% reduction"),
    ("REENTRY_COOLDOWN_BARS", "6",     "was 3 → 6 bars"),
]


def _patch_config_field(text, field, new_value, note):
    """
    Replace a Config field's numeric value using regex.
    Handles trailing comments and whitespace.
    Returns (new_text, status) where status in {OK, SKIP_ALREADY, MISSING}.
    """
    # Pattern: FIELD: type = <number>  (stops at number, ignores trailing)
    pattern = rf'(\b{re.escape(field)}:\s*\w+\s*=\s*)([\d.]+)'

    m = re.search(pattern, text)
    if not m:
        return text, "MISSING"

    current_val = m.group(2)
    # Normalize comparison (strip trailing zeros, "10.0" == "10")
    try:
        cur_num = float(current_val)
        new_num = float(new_value)
        if abs(cur_num - new_num) < 1e-9:
            return text, "SKIP_ALREADY"
    except ValueError:
        pass  # non-numeric? shouldn't happen

    new_text = re.sub(pattern, rf'\g<1>{new_value}', text, count=1)
    return new_text, f"OK ({current_val} → {new_value}, {note})"


# ══════════════════════════════════════════════════════════════
# PART 2 — Backtest MIN_NOTIONAL forcing (first check, opt_px)
# ══════════════════════════════════════════════════════════════
P2_OLD = (
    "        # ══ [NOTIONAL CAP] ══\n"
    "        qty = cap_notional(qty, opt_px)\n"
    "\n"
    "        not_ = qty * opt_px\n"
    "\n"
    "        if not_ < CFG.MIN_NOTIONAL:\n"
    "            continue\n"
)
P2_NEW = (
    "        # ══ [NOTIONAL CAP] ══\n"
    "        qty = cap_notional(qty, opt_px)\n"
    "\n"
    "        not_ = qty * opt_px\n"
    "\n"
    "        # ══ [MICRO-CAPITAL FIX] Force MIN_NOTIONAL ══\n"
    "        if not_ < CFG.MIN_NOTIONAL:\n"
    "            _forced_qty = CFG.MIN_NOTIONAL / opt_px\n"
    "            _forced_risk_amt = _forced_qty * delta\n"
    "            _forced_risk_frac = _forced_risk_amt / max(capital, 1e-9)\n"
    "            if _forced_risk_frac > 2.0 * CFG.MAX_RISK_PER_TRADE:\n"
    "                log.debug(\n"
    "                    f\"[MicroCap] {sym} REJECT: forced \"\n"
    "                    f\"${CFG.MIN_NOTIONAL:.2f} needs \"\n"
    "                    f\"{_forced_risk_frac*100:.1f}% risk \"\n"
    "                    f\"(> {2*CFG.MAX_RISK_PER_TRADE*100:.1f}%)\")\n"
    "                continue\n"
    "            qty = _forced_qty\n"
    "            risk_frac = _forced_risk_frac\n"
    "            not_ = CFG.MIN_NOTIONAL\n"
    "            log.info(\n"
    "                f\"[MicroCap] {sym} forced to \"\n"
    "                f\"${CFG.MIN_NOTIONAL:.2f} notional \"\n"
    "                f\"(actual risk {_forced_risk_frac*100:.1f}%)\")\n"
)

# ══════════════════════════════════════════════════════════════
# PART 3 — Backtest MIN_NOTIONAL forcing (second check, eff_px)
# ══════════════════════════════════════════════════════════════
P3_OLD = (
    "        # ══ [NOTIONAL CAP] ══\n"
    "        qty = cap_notional(qty, eff_px)\n"
    "\n"
    "        not_ = qty * eff_px\n"
    "\n"
    "        if not_ < CFG.MIN_NOTIONAL: continue\n"
)
P3_NEW = (
    "        # ══ [NOTIONAL CAP] ══\n"
    "        qty = cap_notional(qty, eff_px)\n"
    "\n"
    "        not_ = qty * eff_px\n"
    "\n"
    "        # ══ [MICRO-CAPITAL FIX] Force MIN_NOTIONAL (safety net) ══\n"
    "        if not_ < CFG.MIN_NOTIONAL:\n"
    "            qty = CFG.MIN_NOTIONAL / eff_px\n"
    "            not_ = CFG.MIN_NOTIONAL\n"
)

# ══════════════════════════════════════════════════════════════
# PART 4 — Live MIN_NOTIONAL forcing
# ══════════════════════════════════════════════════════════════
P4_OLD = (
    "                    # ══ [NOTIONAL CAP] ══\n"
    "                    qty = cap_notional(qty, lmt)\n"
    "\n"
    "                    if qty * lmt < cfg.MIN_NOTIONAL:\n"
    "                        continue\n"
)
P4_NEW = (
    "                    # ══ [NOTIONAL CAP] ══\n"
    "                    qty = cap_notional(qty, lmt)\n"
    "\n"
    "                    # ══ [MICRO-CAPITAL FIX] Force MIN_NOTIONAL ══\n"
    "                    _notional_now = qty * lmt\n"
    "                    if _notional_now < cfg.MIN_NOTIONAL:\n"
    "                        _forced_qty = cfg.MIN_NOTIONAL / lmt\n"
    "                        _forced_risk_amt = _forced_qty * delta\n"
    "                        _forced_risk_frac = (\n"
    "                            _forced_risk_amt / max(cap_live, 1e-9))\n"
    "                        if _forced_risk_frac > 2.0 * CFG.MAX_RISK_PER_TRADE:\n"
    "                            log.debug(\n"
    "                                f\"[MicroCap] {sym} REJECT: forced \"\n"
    "                                f\"${cfg.MIN_NOTIONAL:.2f} needs \"\n"
    "                                f\"{_forced_risk_frac*100:.1f}% risk\")\n"
    "                            continue\n"
    "                        qty = _forced_qty\n"
    "                        risk_frac = _forced_risk_frac\n"
    "                        log.info(\n"
    "                            f\"[MicroCap] {sym} forced to \"\n"
    "                            f\"${cfg.MIN_NOTIONAL:.2f} notional \"\n"
    "                            f\"(actual risk {_forced_risk_frac*100:.1f}%)\")\n"
)

# ══════════════════════════════════════════════════════════════
# PART 5 — Symbol filter (in scan_top_assets)
# ══════════════════════════════════════════════════════════════
P5_OLD = (
    "    scored.sort(key=lambda x: -x[0])\n"
    "    sel = [s for _,s in scored[:n]]\n"
    "    if not sel:\n"
    "        return _default_assets()[:n]\n"
    "    log.info(f\"مسح الأصول: {len(sel)} عملة مختارة\")\n"
    "    return sel\n"
)
P5_NEW = (
    "    scored.sort(key=lambda x: -x[0])\n"
    "    sel = [s for _,s in scored[:n]]\n"
    "    if not sel:\n"
    "        return _default_assets()[:n]\n"
    "\n"
    "    # ══ [MICRO-CAPITAL FILTER] exclude high-min-notional symbols ══\n"
    "    # When capital < $20, symbols like BTC (min $100) and ETH (min $15)\n"
    "    # can never be traded. Filter them out upfront to avoid wasting\n"
    "    # signal slots on untradeable symbols.\n"
    "    if getattr(CFG, 'INITIAL_CAPITAL', 10.0) < 20.0:\n"
    "        _micro_filtered = []\n"
    "        _rejected_count = 0\n"
    "        for _sym in sel:\n"
    "            try:\n"
    "                _mkt = exchange.market(_sym)\n"
    "                _min_qty = float(\n"
    "                    ((_mkt.get('limits') or {}).get('amount') or {})\n"
    "                    .get('min') or 0)\n"
    "                _ticker = tickers.get(_sym, {})\n"
    "                _price = float(\n"
    "                    _ticker.get('last') or _ticker.get('close') or 0)\n"
    "                _eff_min = (max(5.0, _min_qty * _price)\n"
    "                            if _price > 0 else 5.0)\n"
    "                if _eff_min <= 15.0:\n"
    "                    _micro_filtered.append(_sym)\n"
    "                else:\n"
    "                    _rejected_count += 1\n"
    "                    log.debug(\n"
    "                        f\"[MicroCap] excluding {_sym}: \"\n"
    "                        f\"min_qty={_min_qty}, price=${_price:.4f}, \"\n"
    "                        f\"eff_min=${_eff_min:.2f}\")\n"
    "            except Exception:\n"
    "                _micro_filtered.append(_sym)  # keep on error\n"
    "        if _micro_filtered:\n"
    "            log.warning(\n"
    "                f\"[MicroCap] Symbol filter: {len(_micro_filtered)}/\"\n"
    "                f\"{len(sel)} pass (rejected {_rejected_count} \"\n"
    "                f\"high-min-notional)\")\n"
    "            sel = _micro_filtered\n"
    "\n"
    "    log.info(f\"مسح الأصول: {len(sel)} عملة مختارة\")\n"
    "    return sel\n"
)


# ══════════════════════════════════════════════════════════════
# Apply logic
# ══════════════════════════════════════════════════════════════
def _count(haystack, needle):
    c = 0
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return c
        c += 1
        start = idx + len(needle)


def apply_all(src_text):
    text = src_text
    results = []

    # ── Config changes (19 fields, regex-based) ──
    for field, new_val, note in CONFIG_CHANGES:
        text, status = _patch_config_field(text, field, new_val, note)
        results.append((f"CONFIG.{field}", status))

    # ── Code patches (exact-match) ──
    code_patches = [
        ("BT_MIN_NOTIONAL_1", P2_OLD, P2_NEW,
         "Backtest MIN_NOTIONAL forcing (opt_px)"),
        ("BT_MIN_NOTIONAL_2", P3_OLD, P3_NEW,
         "Backtest MIN_NOTIONAL safety net (eff_px)"),
        ("LV_MIN_NOTIONAL",   P4_OLD, P4_NEW,
         "Live MIN_NOTIONAL forcing"),
        ("SYMBOL_FILTER",     P5_OLD, P5_NEW,
         "Symbol filter for micro-capital"),
    ]
    for pid, old, new, desc in code_patches:
        n = _count(text, old)
        if n == 0:
            # Maybe already applied? Check for a marker
            marker = new[:60]  # first 60 chars of replacement
            if marker in text:
                results.append((pid, "SKIP_ALREADY"))
            else:
                results.append((pid, "MISSING"))
            continue
        if n > 1:
            results.append((pid, f"AMBIGUOUS ({n}x)"))
            continue
        text = text.replace(old, new, 1)
        results.append((pid, "OK"))

    return text, results


def verify_syntax(text):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"


def main():
    ap = argparse.ArgumentParser(
        description="Enable $1 micro-capital support in the bot.")
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

    print("Applying patches...")
    new_text, results = apply_all(src)

    # Group by category
    config_ok = sum(1 for _, s in results
                    if s.startswith("OK") or s == "SKIP_ALREADY"
                    for _ in [1])
    code_ok = sum(1 for pid, s in results
                  if not pid.startswith("CONFIG")
                  and s in ("OK", "SKIP_ALREADY"))

    # Print config changes
    print("  ── Config values ──")
    for pid, status in results:
        if pid.startswith("CONFIG."):
            field = pid.replace("CONFIG.", "")
            symbol = "  ✓" if status != "MISSING" else "  ✗"
            print(f"  {symbol} {field:24s}: {status}")

    # Print code patches
    print("\n  ── Code patches ──")
    for pid, status in results:
        if not pid.startswith("CONFIG"):
            symbol = "  ✓" if status in ("OK", "SKIP_ALREADY") else "  ✗"
            print(f"  {symbol} {pid:20s}: {status}")

    # Summary
    total_ok = config_ok + code_ok
    print(f"\n  Applied: {total_ok}/{len(results)}")

    if total_ok < len(results):
        missing = [pid for pid, s in results if s == "MISSING"]
        if missing:
            print(f"  ⚠ Missing anchors: {missing}")
            print("    File may already have some patches, or version differs.")

    print("\nVerifying syntax...")
    ok, err = verify_syntax(new_text)
    if not ok:
        print(f"  FAIL: {err}")
        print("  No files written. Original untouched.")
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

    print("=" * 74)
    print("  DONE — Micro-capital ($1) support applied")
    print("=" * 74)
    print()
    print("⚠️  WARNING: Micro-capital mode is EXPERIMENTAL")
    print()
    print("What changed:")
    print("  • INITIAL_CAPITAL   = $1      (was $10)")
    print("  • MAX_RISK/TRADE    = 15%     (was 3%)")
    print("  • PORTFOLIO_HEAT    = 30%     (was 10%)")
    print("  • MAX_CONCURRENT    = 2       (was 3)")
    print("  • LEVERAGE_MIN      = 20x     (was 5x)")
    print("  • MIN_NOTIONAL      = forced to $5 (was: rejected)")
    print("  • Symbol filter     = excludes BTC/ETH/etc. when capital < $20")
    print()
    print("Expected behavior with $1:")
    print("  • Each trade = $5 notional → $0.40-$0.75 risk (8-15%)")
    print("  • ~2-5 trades/month (cooldown + filter)")
    print("  • Fees consume 30-50% of profits")
    print("  • Max DD expected: 30-50%")
    print()
    print("RECOMMENDED TEST SEQUENCE:")
    print("  1. Testnet for 2 weeks:")
    print("     --mode testnet --capital 1 --live-capital 1 --maxcon 2")
    print("  2. Review logs for [MicroCap] messages")
    print("  3. If stable → Live with $1")
    print("  4. If DD > 50% → stop and reconsider")
    print()
    print("VERIFY IN LOG:")
    print("  grep '\\[MicroCap\\]' qtt6.log")
    print("  grep 'Symbol filter' qtt6.log")
    print()
    print("FALLBACK / ROLLBACK:")
    print("  • Config values: pass --capital 10 --max-risk 0.03 --maxcon 3 ...")
    print("  • Symbol filter: only active when INITIAL_CAPITAL < 20")
    print("  • MIN_NOTIONAL forcing: only active when notional < $5")
    print("  • Full rollback: restore from .bak file")


if __name__ == "__main__":
    main()
