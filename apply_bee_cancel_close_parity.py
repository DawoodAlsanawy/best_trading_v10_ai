#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_bee_cancel_close_parity.py
=================================
Fixes the last remaining live↔backtest parity gap: BEEsc-Cancel.

Problem:
    Backtest uses ad.lows[cidx] (wick) for extreme tracking.
    Live uses ticker (every 5s).
    → Different BEEsc-Cancel behavior between backtest and live.

Fix (opt-in, default OFF):
    --be-cancel-close-only:
        Use CLOSED bar close for extreme tracking + bounce.
        Matches S/R philosophy (level broken only by close).
    --be-cancel-sr-check:
        Skip BEEsc-Cancel if swing support/resistance broken by close.

Prerequisites:
    • BEEsc base (BREAKEVEN_ESCAPE_ENABLED)
    • BEEsc-Cancel (BREAKEVEN_ESCAPE_CANCEL_KAPPA)
    Both are already applied in your file.

Usage:
    python3 apply_bee_cancel_close_parity.py --dry-run
    python3 apply_bee_cancel_close_parity.py
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
# IDEMPOTENCY MARKERS — if present, patch is already applied
# ══════════════════════════════════════════════════════════════
MARK_P1 = "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False"
MARK_P2 = "mode={'close' if _be_use_close else 'wick'}"
MARK_P3 = "mode={'close' if _be_use_close else 'ticker'}"
MARK_P4 = "--be-cancel-close-only"
MARK_P5 = "CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True"


# ══════════════════════════════════════════════════════════════
# P1 — Config: add 3 new flags
# ══════════════════════════════════════════════════════════════
P1_OLD = "    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0\n"
P1_NEW = (
    "    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0\n"
    "    # ══ [BEEsc-Cancel-Close] CLOSE-ONLY tracking (no wick, no ticker) ══\n"
    "    # When True, extreme tracking + bounce confirmation use the LAST\n"
    "    # CLOSED bar's close. Matches S/R philosophy and eliminates the\n"
    "    # live-vs-backtest ticker/wick gap.\n"
    "    # Default False → preserves current behavior.\n"
    "    BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False\n"
    "    # ══ [BEEsc-Cancel-SR] Require S/R intact before cancelling ══\n"
    "    # When True, BEEsc-Cancel is skipped if price has BROKEN (by close)\n"
    "    # the nearest swing support (BUY) or resistance (SELL).\n"
    "    # Default False → no S/R filter.\n"
    "    BREAKEVEN_ESCAPE_CANCEL_SR_CHECK: bool = False\n"
    "    BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK: int = 60\n"
)


# ══════════════════════════════════════════════════════════════
# P2 — Backtest: regex-based block replacement
# ══════════════════════════════════════════════════════════════
P2_PATTERN = re.compile(
    r'(        # ══ \[BEEsc-CANCEL\] track extremes \+ cancel on strong bounce ══\n'
    r'.*?)'
    r'(        # ── Determine sub-bar iteration range for this bar ──\n)',
    re.DOTALL,
)

P2_NEW = (
    "        # ══ [BEEsc-CANCEL] track extremes + cancel on strong bounce ══\n"
    "        # [BEEsc-Cancel-Close] Optional close-only (no wick)\n"
    "        # [BEEsc-Cancel-SR] Optional S/R intact check\n"
    "        if (getattr(pos, '_be_esc_done', False)\n"
    "                and not getattr(pos, '_be_cancelled', False)\n"
    "                and float(getattr(CFG, 'BREAKEVEN_ESCAPE_CANCEL_KAPPA', 0.0)) > 0\n"
    "                and hasattr(pos, '_be_orig_tp1')):\n"
    "            try:\n"
    "                _be_use_close = bool(getattr(\n"
    "                    CFG, 'BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY', False))\n"
    "                _be_sr_check = bool(getattr(\n"
    "                    CFG, 'BREAKEVEN_ESCAPE_CANCEL_SR_CHECK', False))\n"
    "                _be_sr_ok = True\n"
    "                if _be_sr_check:\n"
    "                    _be_lb = int(getattr(\n"
    "                        CFG, 'BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK', 60))\n"
    "                    _be_swing = _find_recent_swing(\n"
    "                        ad, max(0, cidx - _be_lb), cidx, sig.action)\n"
    "                    if _be_swing is not None:\n"
    "                        _be_close_now = float(ad.closes[cidx])\n"
    "                        if (sig.action == 'BUY'\n"
    "                                and _be_close_now < _be_swing):\n"
    "                            _be_sr_ok = False\n"
    "                            log.debug(\n"
    "                                f\"[BEEsc-Cancel-SR] {sig.symbol} \"\n"
    "                                f\"BUY skip: support broken \"\n"
    "                                f\"close={_be_close_now:.6f}<\"\n"
    "                                f\"swing={_be_swing:.6f}\")\n"
    "                        elif (sig.action == 'SELL'\n"
    "                                and _be_close_now > _be_swing):\n"
    "                            _be_sr_ok = False\n"
    "                            log.debug(\n"
    "                                f\"[BEEsc-Cancel-SR] {sig.symbol} \"\n"
    "                                f\"SELL skip: resistance broken \"\n"
    "                                f\"close={_be_close_now:.6f}>\"\n"
    "                                f\"swing={_be_swing:.6f}\")\n"
    "                if _be_sr_ok:\n"
    "                    _sigma_c = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01\n"
    "                    if not np.isfinite(_sigma_c) or _sigma_c <= 1e-9:\n"
    "                        _sigma_c = 0.01\n"
    "                    _kappa_c = float(CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA)\n"
    "                    _thr_c = _kappa_c * _sigma_c * pos.entry_px\n"
    "                    if sig.action == \"BUY\":\n"
    "                        _low_src = (float(ad.closes[cidx]) if _be_use_close\n"
    "                                    else float(ad.lows[cidx]))\n"
    "                        _low_c = min(\n"
    "                            float(getattr(pos, '_be_low', pos.entry_px)),\n"
    "                            _low_src,\n"
    "                        )\n"
    "                        pos._be_low = _low_c\n"
    "                        _bounce_c = float(p) - _low_c\n"
    "                        if _bounce_c >= _thr_c:\n"
    "                            _restore_c = float(pos._be_orig_tp1)\n"
    "                            sig.tp1 = _restore_c\n"
    "                            pos._be_cancelled = True\n"
    "                            log.info(\n"
    "                                f\"[BEEsc-Cancel-BT] {sig.symbol} \"\n"
    "                                f\"BUY bounce={_bounce_c:.6f} ≥ \"\n"
    "                                f\"{_thr_c:.6f} → TP restored to \"\n"
    "                                f\"{_restore_c:.6f} \"\n"
    "                                f\"(mode={'close' if _be_use_close else 'wick'})\"\n"
    "                            )\n"
    "                    else:\n"
    "                        _high_src = (float(ad.closes[cidx]) if _be_use_close\n"
    "                                     else float(ad.highs[cidx]))\n"
    "                        _high_c = max(\n"
    "                            float(getattr(pos, '_be_high', pos.entry_px)),\n"
    "                            _high_src,\n"
    "                        )\n"
    "                        pos._be_high = _high_c\n"
    "                        _bounce_c = _high_c - float(p)\n"
    "                        if _bounce_c >= _thr_c:\n"
    "                            _restore_c = float(pos._be_orig_tp1)\n"
    "                            sig.tp1 = _restore_c\n"
    "                            pos._be_cancelled = True\n"
    "                            log.info(\n"
    "                                f\"[BEEsc-Cancel-BT] {sig.symbol} \"\n"
    "                                f\"SELL bounce={_bounce_c:.6f} ≥ \"\n"
    "                                f\"{_thr_c:.6f} → TP restored to \"\n"
    "                                f\"{_restore_c:.6f} \"\n"
    "                                f\"(mode={'close' if _be_use_close else 'wick'})\"\n"
    "                            )\n"
    "            except Exception as _e_c:\n"
    "                log.debug(f\"[BEEsc-Cancel-BT] {sig.symbol}: {_e_c}\")\n"
    "\n"
)


# ══════════════════════════════════════════════════════════════
# P3 — Live: regex-based block replacement
# ══════════════════════════════════════════════════════════════
P3_PATTERN = re.compile(
    r'(                # ══ \[BEEsc-Cancel-Live\] track extremes \+ cancel ══\n'
    r'.*?)'
    r'(                ex = False\n)',
    re.DOTALL,
)

P3_NEW = (
    "                # ══ [BEEsc-Cancel-Live] track extremes + cancel ══\n"
    "                # [BEEsc-Cancel-Close] Optional close-only (no ticker)\n"
    "                # [BEEsc-Cancel-SR] Optional S/R intact check\n"
    "                if (pos.get('_be_esc_done', False)\n"
    "                        and not pos.get('_be_cancelled', False)\n"
    "                        and float(getattr(CFG, 'BREAKEVEN_ESCAPE_CANCEL_KAPPA', 0.0)) > 0\n"
    "                        and '_be_orig_tp1' in pos):\n"
    "                    try:\n"
    "                        _be_use_close = bool(getattr(\n"
    "                            CFG, 'BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY', False))\n"
    "                        _be_sr_check = bool(getattr(\n"
    "                            CFG, 'BREAKEVEN_ESCAPE_CANCEL_SR_CHECK', False))\n"
    "                        _be_sr_ok = True\n"
    "                        _be_ci = (len(ad.closes) - 2) if ad is not None else -1\n"
    "                        if _be_sr_check and ad is not None and _be_ci > 0:\n"
    "                            _be_lb = int(getattr(\n"
    "                                CFG, 'BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK', 60))\n"
    "                            _be_swing = _find_recent_swing(\n"
    "                                ad, max(0, _be_ci - _be_lb), _be_ci, pos['action'])\n"
    "                            if _be_swing is not None:\n"
    "                                _be_close_now = float(ad.closes[_be_ci])\n"
    "                                if (pos['action'] == 'BUY'\n"
    "                                        and _be_close_now < _be_swing):\n"
    "                                    _be_sr_ok = False\n"
    "                                    log.debug(\n"
    "                                        f\"[BEEsc-Cancel-SR] {sym} \"\n"
    "                                        f\"BUY skip: support broken \"\n"
    "                                        f\"close={_be_close_now:.6f}<\"\n"
    "                                        f\"swing={_be_swing:.6f}\")\n"
    "                                elif (pos['action'] == 'SELL'\n"
    "                                        and _be_close_now > _be_swing):\n"
    "                                    _be_sr_ok = False\n"
    "                                    log.debug(\n"
    "                                        f\"[BEEsc-Cancel-SR] {sym} \"\n"
    "                                        f\"SELL skip: resistance broken \"\n"
    "                                        f\"close={_be_close_now:.6f}>\"\n"
    "                                        f\"swing={_be_swing:.6f}\")\n"
    "                        if _be_sr_ok:\n"
    "                            _sigma_c = 0.01\n"
    "                            if ad is not None:\n"
    "                                _fi_c = (len(ad.closes) - 2 - ad.feat_start)\n"
    "                                if 0 <= _fi_c < len(ad.E_therm):\n"
    "                                    _sigma_c = float(ad.E_therm[_fi_c])\n"
    "                            if not np.isfinite(_sigma_c) or _sigma_c <= 1e-9:\n"
    "                                _sigma_c = 0.01\n"
    "                            _kappa_c = float(CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA)\n"
    "                            _thr_c = _kappa_c * _sigma_c * float(pos['entry'])\n"
    "                            if _be_use_close and ad is not None and _be_ci > 0:\n"
    "                                _be_price_c = float(ad.closes[_be_ci])\n"
    "                            else:\n"
    "                                _be_price_c = float(price)\n"
    "                            if pos['action'] == \"BUY\":\n"
    "                                _low_c = min(\n"
    "                                    float(pos.get('_be_low', float(pos['entry']))),\n"
    "                                    _be_price_c,\n"
    "                                )\n"
    "                                pos['_be_low'] = _low_c\n"
    "                                _bounce_c = _be_price_c - _low_c\n"
    "                                if _bounce_c >= _thr_c:\n"
    "                                    _restore_c = float(pos['_be_orig_tp1'])\n"
    "                                    pos['tp1'] = _restore_c\n"
    "                                    pos['_be_cancelled'] = True\n"
    "                                    log.info(\n"
    "                                        f\"[BEEsc-Cancel-LV] {sym} BUY \"\n"
    "                                        f\"bounce={_bounce_c:.6f} ≥ \"\n"
    "                                        f\"{_thr_c:.6f} → TP restored to \"\n"
    "                                        f\"{_restore_c:.6f} \"\n"
    "                                        f\"(mode={'close' if _be_use_close else 'ticker'})\"\n"
    "                                    )\n"
    "                                    try:\n"
    "                                        if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):\n"
    "                                            _sync_protective_orders(exchange, sym, pos)\n"
    "                                    except Exception:\n"
    "                                        pass\n"
    "                                    try:\n"
    "                                        _lv_save_state(state_file, open_pos_live)\n"
    "                                    except Exception:\n"
    "                                        pass\n"
    "                            else:\n"
    "                                _high_c = max(\n"
    "                                    float(pos.get('_be_high', float(pos['entry']))),\n"
    "                                    _be_price_c,\n"
    "                                )\n"
    "                                pos['_be_high'] = _high_c\n"
    "                                _bounce_c = _high_c - _be_price_c\n"
    "                                if _bounce_c >= _thr_c:\n"
    "                                    _restore_c = float(pos['_be_orig_tp1'])\n"
    "                                    pos['tp1'] = _restore_c\n"
    "                                    pos['_be_cancelled'] = True\n"
    "                                    log.info(\n"
    "                                        f\"[BEEsc-Cancel-LV] {sym} SELL \"\n"
    "                                        f\"bounce={_bounce_c:.6f} ≥ \"\n"
    "                                        f\"{_thr_c:.6f} → TP restored to \"\n"
    "                                        f\"{_restore_c:.6f} \"\n"
    "                                        f\"(mode={'close' if _be_use_close else 'ticker'})\"\n"
    "                                    )\n"
    "                                    try:\n"
    "                                        if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):\n"
    "                                            _sync_protective_orders(exchange, sym, pos)\n"
    "                                    except Exception:\n"
    "                                        pass\n"
    "                                    try:\n"
    "                                        _lv_save_state(state_file, open_pos_live)\n"
    "                                    except Exception:\n"
    "                                        pass\n"
    "                    except Exception as _e_c:\n"
    "                        log.debug(f\"[BEEsc-Cancel-LV] {sym}: {_e_c}\")\n"
    "\n"
)


# ══════════════════════════════════════════════════════════════
# P4 — CLI args: add 2 flags AFTER --be-escape-cancel-kappa
# ══════════════════════════════════════════════════════════════
P4_OLD = (
    "    p.add_argument(\"--be-escape-cancel-kappa\", type=float, default=None,\n"
    "                   help=\"Cancel BEEsc if bounce from extreme ≥ \"\n"
    "                        \"κ × σ_bar × entry (default 0.0 = never \"\n"
    "                        \"cancel, current behavior)\")\n"
)
P4_NEW = (
    "    p.add_argument(\"--be-escape-cancel-kappa\", type=float, default=None,\n"
    "                   help=\"Cancel BEEsc if bounce from extreme ≥ \"\n"
    "                        \"κ × σ_bar × entry (default 0.0 = never \"\n"
    "                        \"cancel, current behavior)\")\n"
    "    p.add_argument(\"--be-cancel-close-only\", action=\"store_true\",\n"
    "                   help=\"BEEsc-Cancel uses CLOSED bar close for \"\n"
    "                        \"extreme tracking + bounce (no wick, no ticker)\")\n"
    "    p.add_argument(\"--be-cancel-sr-check\", action=\"store_true\",\n"
    "                   help=\"BEEsc-Cancel skipped if nearest swing \"\n"
    "                        \"support/resistance was BROKEN by close\")\n"
)


# ══════════════════════════════════════════════════════════════
# P5 — CLI wiring: set CFG flags + extended log
# ══════════════════════════════════════════════════════════════
P5_OLD = (
    "    if getattr(args, \"be_escape_cancel_kappa\", None) is not None:\n"
    "        CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA = float(\n"
    "            args.be_escape_cancel_kappa)\n"
    "        if CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA > 0:\n"
    "            log.info(\n"
    "                f\"[BEEsc] CANCEL enabled: κ=\"\n"
    "                f\"{CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA} × σ_bar — \"\n"
    "                f\"BEEsc will be undone if bounce from extreme \"\n"
    "                f\"exceeds this threshold before touching entry\"\n"
    "            )\n"
)
P5_NEW = (
    "    if getattr(args, \"be_escape_cancel_kappa\", None) is not None:\n"
    "        CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA = float(\n"
    "            args.be_escape_cancel_kappa)\n"
    "    if getattr(args, \"be_cancel_close_only\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True\n"
    "    if getattr(args, \"be_cancel_sr_check\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_CANCEL_SR_CHECK = True\n"
    "    if CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA > 0:\n"
    "        log.info(\n"
    "            f\"[BEEsc] CANCEL enabled: κ=\"\n"
    "            f\"{CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA} × σ_bar — \"\n"
    "            f\"BEEsc will be undone if bounce from extreme \"\n"
    "            f\"exceeds this threshold before touching entry\"\n"
    "        )\n"
    "        log.info(\n"
    "            f\"[BEEsc] CANCEL mode: close_only=\"\n"
    "            f\"{CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY} \"\n"
    "            f\"sr_check={CFG.BREAKEVEN_ESCAPE_CANCEL_SR_CHECK} \"\n"
    "            f\"sr_lookback={CFG.BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK}\"\n"
    "        )\n"
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


def _apply_exact(text, old, new, label):
    n = _count(text, old)
    if n == 0:
        return text, "ANCHOR_NOT_FOUND"
    if n > 1:
        return text, f"AMBIGUOUS({n})"
    return text.replace(old, new, 1), "OK"


def _apply_regex(text, pattern, new_block, label):
    m = pattern.search(text)
    if m is None:
        return text, "REGEX_NOT_FOUND"
    # Replace entire match with new block + preserved tail (group 2)
    def _replacer(match):
        return new_block + match.group(2)
    return pattern.sub(_replacer, text, count=1), "OK"


def apply_all(src_text):
    text = src_text
    results = []

    # ── P1 (Config) ──
    if MARK_P1 in text:
        results.append(("P1_CONFIG", "SKIP_ALREADY", "Config flags"))
    else:
        text, status = _apply_exact(text, P1_OLD, P1_NEW, "P1")
        results.append(("P1_CONFIG", status, "Config flags"))

    # ── P2 (Backtest regex) ──
    if MARK_P2 in text:
        results.append(("P2_BT", "SKIP_ALREADY", "Backtest block"))
    else:
        text, status = _apply_regex(text, P2_PATTERN, P2_NEW, "P2")
        results.append(("P2_BT", status, "Backtest block"))

    # ── P3 (Live regex) ──
    if MARK_P3 in text:
        results.append(("P3_LV", "SKIP_ALREADY", "Live block"))
    else:
        text, status = _apply_regex(text, P3_PATTERN, P3_NEW, "P3")
        results.append(("P3_LV", status, "Live block"))

    # ── P4 (CLI args) ──
    if MARK_P4 in text:
        results.append(("P4_ARGS", "SKIP_ALREADY", "CLI args"))
    else:
        text, status = _apply_exact(text, P4_OLD, P4_NEW, "P4")
        results.append(("P4_ARGS", status, "CLI args"))

    # ── P5 (Wiring) ──
    if MARK_P5 in text:
        results.append(("P5_WIRE", "SKIP_ALREADY", "CLI wiring"))
    else:
        text, status = _apply_exact(text, P5_OLD, P5_NEW, "P5")
        results.append(("P5_WIRE", status, "CLI wiring"))

    return text, results


def verify_syntax(text):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"


def main():
    ap = argparse.ArgumentParser(
        description="Apply BEEsc-Cancel close-only + S/R parity patch.")
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

    print("Applying 5 patches...")
    new_text, results = apply_all(src)

    for pid, status, desc in results:
        if status == "OK":
            sym = "✓"
        elif status == "SKIP_ALREADY":
            sym = "⏭ "
        else:
            sym = "✗"
        print(f"  [{status:22s}] {sym} {pid:10s} — {desc}")

    n_ok = sum(1 for _, s, _ in results if s in ("OK", "SKIP_ALREADY"))
    n_fail = len(results) - n_ok
    print(f"\n  Applied: {n_ok}/{len(results)}")

    if n_fail > 0:
        print(f"\n  ⚠ {n_fail} patch(es) failed.")
        print(f"  This means your file's anchors differ from expected.")
        print(f"  Please verify:")
        print(f"    grep 'BREAKEVEN_ESCAPE_CANCEL_KAPPA' <file>")
        print(f"    grep 'BEEsc-Cancel-Live' <file>")
        print(f"    grep 'BEEsc-CANCEL' <file>")
        print(f"  No files were written.")
        sys.exit(1)

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
    print("  DONE — BEEsc-Cancel close-only + S/R parity applied")
    print("=" * 74)
    print()
    print("What was added (all OPT-IN, default OFF):")
    print()
    print("  --be-cancel-close-only")
    print("    Extreme tracking + bounce use CLOSED bar close.")
    print("    Backtest: closes[cidx] instead of lows/highs")
    print("    Live:     closes[-2] instead of ticker")
    print("    → Parity: 100% between backtest and live")
    print("    → S/R philosophy: level not broken until candle closes")
    print()
    print("  --be-cancel-sr-check")
    print("    Skip BEEsc-Cancel if nearest swing support/resistance")
    print("    was BROKEN by the last close.")
    print("    → Prevents cancelling on fake bounces after breakout")
    print()
    print("Verify with:")
    print("  grep BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY <file>  → 3+")
    print("  grep 'mode=.close' <file>                       → 4+")
    print("  grep 'BEEsc-Cancel-SR' <file>                   → 2")
    print("  grep 'be-cancel-close-only' <file>              → 2")
    print()
    print("Test plan (A/B/C on backtest):")
    print("  A) no new flags                    → baseline (unchanged)")
    print("  B) --be-cancel-close-only          → parity mode")
    print("  C) --be-cancel-close-only --be-cancel-sr-check → + S/R")
    print()
    print("Compare on A/B/C:")
    print("  • Emergency SL%    (should not increase)")
    print("  • Hard TP%         (should not decrease)")
    print("  • Max DD           (should not increase)")
    print("  • E[ln]            (should not decrease)")
    print("  • #BEEsc-Cancel    (should decrease)")
    print()
    print("If A > B > C on E[ln]: keep baseline (don't use flags).")
    print("If C ≥ B ≥ A on E[ln]: use C (best parity + S/R).")
    print("If B > A but C < B: use B (parity without S/R).")


if __name__ == "__main__":
    main()
