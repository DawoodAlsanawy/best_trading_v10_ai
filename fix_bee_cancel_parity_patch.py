#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_bee_cancel_parity_patch.py
==============================
Idempotent, tolerant fixer for the BEEsc-Cancel parity patch.

Handles partial application:
    - P1/P2 already applied → skips them
    - P3 (live) uses REGEX (tolerant to whitespace/content variations)
    - P4/P5 applied if not present
    - Safe to re-run any number of times

Usage:
    python3 fix_bee_cancel_parity_patch.py --dry-run
    python3 fix_bee_cancel_parity_patch.py
"""

import argparse
import ast
import os
import re
import shutil
import sys
from datetime import datetime

DEFAULT_FILE = "trading_2_live4_claude2_v4.py"


# ══════════════════════════════════════════════════════════════
# MARKERS  (used to detect what's already applied)
# ══════════════════════════════════════════════════════════════
MARK_P1 = "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False"
MARK_P2 = "mode={'close' if _be_use_close else 'wick'}"
MARK_P3 = "mode={'close' if _be_use_close else 'ticker'}"
MARK_P4 = "--be-cancel-close-only"
MARK_P5 = "CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True"


# ══════════════════════════════════════════════════════════════
# P1 — Config
# ══════════════════════════════════════════════════════════════
P1_OLD = "    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0\n"
P1_NEW = (
    "    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0\n"
    "    # ══ [BEEsc-Cancel-Close] CLOSE-ONLY tracking (no wick, no ticker)\n"
    "    BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False\n"
    "    # ══ [BEEsc-Cancel-SR] Require S/R intact before cancelling\n"
    "    BREAKEVEN_ESCAPE_CANCEL_SR_CHECK: bool = False\n"
    "    BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK: int = 60\n"
)


# ══════════════════════════════════════════════════════════════
# P2 — Backtest block (exact-match still works — it matched OK)
# ══════════════════════════════════════════════════════════════
P2_OLD = (
    "        # ══ [BEEsc-CANCEL] track extremes + cancel on strong bounce ══\n"
    "        if (getattr(pos, '_be_esc_done', False)\n"
    "                and not getattr(pos, '_be_cancelled', False)\n"
    "                and float(getattr(CFG, 'BREAKEVEN_ESCAPE_CANCEL_KAPPA', 0.0)) > 0\n"
    "                and hasattr(pos, '_be_orig_tp1')):\n"
    "            try:\n"
    "                _sigma_c = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01\n"
    "                if not np.isfinite(_sigma_c) or _sigma_c <= 1e-9:\n"
    "                    _sigma_c = 0.01\n"
    "                _kappa_c = float(CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA)\n"
    "                _thr_c = _kappa_c * _sigma_c * pos.entry_px\n"
    "                if sig.action == \"BUY\":\n"
    "                    _low_c = min(\n"
    "                        float(getattr(pos, '_be_low', pos.entry_px)),\n"
    "                        float(ad.lows[cidx]),\n"
    "                    )\n"
    "                    pos._be_low = _low_c\n"
    "                    _bounce_c = float(p) - _low_c\n"
    "                    if _bounce_c >= _thr_c:\n"
    "                        _restore_c = float(pos._be_orig_tp1)\n"
    "                        sig.tp1 = _restore_c\n"
    "                        pos._be_cancelled = True\n"
    "                        log.info(\n"
    "                            f\"[BEEsc-Cancel-BT] {sig.symbol} \"\n"
    "                            f\"BUY bounce={_bounce_c:.6f} ≥ \"\n"
    "                            f\"{_thr_c:.6f} → TP restored to \"\n"
    "                            f\"{_restore_c:.6f}\"\n"
    "                        )\n"
    "                else:\n"
    "                    _high_c = max(\n"
    "                        float(getattr(pos, '_be_high', pos.entry_px)),\n"
    "                        float(ad.highs[cidx]),\n"
    "                    )\n"
    "                    pos._be_high = _high_c\n"
    "                    _bounce_c = _high_c - float(p)\n"
    "                    if _bounce_c >= _thr_c:\n"
    "                        _restore_c = float(pos._be_orig_tp1)\n"
    "                        sig.tp1 = _restore_c\n"
    "                        pos._be_cancelled = True\n"
    "                        log.info(\n"
    "                            f\"[BEEsc-Cancel-BT] {sig.symbol} \"\n"
    "                            f\"SELL bounce={_bounce_c:.6f} ≥ \"\n"
    "                            f\"{_thr_c:.6f} → TP restored to \"\n"
    "                            f\"{_restore_c:.6f}\"\n"
    "                        )\n"
    "            except Exception as _e_c:\n"
    "                log.debug(f\"[BEEsc-Cancel-BT] {sig.symbol}: {_e_c}\")\n"
)

P2_NEW = (
    "        # ══ [BEEsc-CANCEL] track extremes + cancel on strong bounce ══\n"
    "        # [BEEsc-Cancel-Close] Optional close-only tracking (no wick)\n"
    "        # [BEEsc-Cancel-SR] Optional: require S/R intact before cancel\n"
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
)


# ══════════════════════════════════════════════════════════════
# P3 — Live block:  REGEX based (tolerant to variations)
# ══════════════════════════════════════════════════════════════
# Match: from "# ══ [BEEsc-Cancel-Live]..." up to "ex = False"
# (non-greedy, DOTALL). Group 1 = "ex = False\n" (preserved).
P3_PATTERN = re.compile(
    r'                # ══ \[BEEsc-Cancel-Live\] track extremes \+ cancel ══\n'
    r'.*?'
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
# P4 — CLI args
# ══════════════════════════════════════════════════════════════
P4_OLD = (
    "    p.add_argument(\"--be-escape-cancel-kappa\", type=float, default=None,\n"
    "                   help=\"Cancel BEEsc when bounce from extreme ≥ \"\n"
    "                        \"κ × σ_bar × entry BEFORE touching entry. \"\n"
    "                        \"TP is restored to its original target. \"\n"
    "                        \"0.0 = disabled (default)\")\n"
)
P4_NEW = (
    "    p.add_argument(\"--be-escape-cancel-kappa\", type=float, default=None,\n"
    "                   help=\"Cancel BEEsc when bounce from extreme ≥ \"\n"
    "                        \"κ × σ_bar × entry BEFORE touching entry. \"\n"
    "                        \"TP is restored to its original target. \"\n"
    "                        \"0.0 = disabled (default)\")\n"
    "    p.add_argument(\"--be-cancel-close-only\", action=\"store_true\",\n"
    "                   help=\"BEEsc-Cancel uses CLOSED bar close for \"\n"
    "                        \"extreme tracking + bounce (no wick, no ticker)\")\n"
    "    p.add_argument(\"--be-cancel-sr-check\", action=\"store_true\",\n"
    "                   help=\"BEEsc-Cancel skipped if nearest swing \"\n"
    "                        \"support/resistance was BROKEN by close\")\n"
)


# ══════════════════════════════════════════════════════════════
# P5 — CLI wiring
# ══════════════════════════════════════════════════════════════
P5_OLD = (
    "    if CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA > 0:\n"
    "        log.info(\n"
    "            f\"[BEEsc] CANCEL enabled: κ=\"\n"
    "            f\"{CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA} × σ_bar — \"\n"
    "            f\"BEEsc will be undone if bounce from extreme exceeds \"\n"
    "            f\"this threshold before touching entry\"\n"
    "        )\n"
)
P5_NEW = (
    "    if getattr(args, \"be_cancel_close_only\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True\n"
    "    if getattr(args, \"be_cancel_sr_check\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_CANCEL_SR_CHECK = True\n"
    "    if CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA > 0:\n"
    "        log.info(\n"
    "            f\"[BEEsc] CANCEL enabled: κ=\"\n"
    "            f\"{CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA} × σ_bar — \"\n"
    "            f\"BEEsc will be undone if bounce from extreme exceeds \"\n"
    "            f\"this threshold before touching entry\"\n"
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


def _apply_exact(text, old, new, label, required=True):
    if _count(text, old) == 0:
        if required:
            raise RuntimeError(
                f"[{label}] anchor NOT FOUND\n"
                f"  preview: {old[:200]!r}")
        return text, False
    if _count(text, old) > 1:
        raise RuntimeError(
            f"[{label}] anchor AMBIGUOUS ({_count(text, old)} matches)")
    return text.replace(old, new, 1), True


def apply_all(src_text):
    text = src_text
    log_lines = []

    # ── P1 ──
    if MARK_P1 in text:
        log_lines.append(("P1_CONFIG", "SKIP (already applied)"))
    else:
        text, ok = _apply_exact(text, P1_OLD, P1_NEW, "P1_CONFIG")
        log_lines.append(("P1_CONFIG", "OK" if ok else "SKIP (not found — optional?)"))

    # ── P2 ──
    if MARK_P2 in text:
        log_lines.append(("P2_BT", "SKIP (already applied)"))
    else:
        text, ok = _apply_exact(text, P2_OLD, P2_NEW, "P2_BT")
        log_lines.append(("P2_BT", "OK" if ok else "SKIP"))

    # ── P3 (regex) ──
    if MARK_P3 in text:
        log_lines.append(("P3_LV", "SKIP (already applied)"))
    else:
        m = P3_PATTERN.search(text)
        if m is None:
            raise RuntimeError(
                "[P3_LV] regex pattern NOT FOUND\n"
                "  expected block starting with:\n"
                "    '                # ══ [BEEsc-Cancel-Live] track extremes...'\n"
                "  and ending at:\n"
                "    '                ex = False'\n"
                "  This means the live BEEsc-Cancel block was either\n"
                "  heavily modified or does not exist.\n"
                "  Please verify the file contains the original\n"
                "  apply_bee_cancel_patch.py output.")
        # Replace: from block start .. up to (but not including) "ex = False"
        # \1 = "                ex = False\n" (preserved)
        text = P3_PATTERN.sub(P3_NEW + r"\1", text, count=1)
        log_lines.append(("P3_LV", "OK (regex)"))

    # ── P4 ──
    if MARK_P4 in text:
        log_lines.append(("P4_ARGS", "SKIP (already applied)"))
    else:
        text, ok = _apply_exact(text, P4_OLD, P4_NEW, "P4_ARGS")
        log_lines.append(("P4_ARGS", "OK" if ok else "SKIP"))

    # ── P5 ──
    if MARK_P5 in text:
        log_lines.append(("P5_WIRE", "SKIP (already applied)"))
    else:
        text, ok = _apply_exact(text, P5_OLD, P5_NEW, "P5_WIRE")
        log_lines.append(("P5_WIRE", "OK" if ok else "SKIP"))

    return text, log_lines


def verify_syntax(text):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"


def main():
    ap = argparse.ArgumentParser(
        description="Tolerant fixer for BEEsc-Cancel parity patch.")
    ap.add_argument("--file", default=DEFAULT_FILE)
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

    print("Checking and applying patches...")
    try:
        new_text, log_lines = apply_all(src)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    for pid, status in log_lines:
        print(f"  [{status:22s}] {pid}")

    print("\nVerifying syntax...")
    ok, err = verify_syntax(new_text)
    if not ok:
        print(f"  FAIL: {err}")
        print("  No files were written. Original untouched.")
        sys.exit(1)
    print("  OK: ast.parse passed.\n")

    # Sanity: ensure all markers present after patch
    print("Post-patch marker check:")
    for label, marker in [
        ("P1_CONFIG", MARK_P1), ("P2_BT", MARK_P2),
        ("P3_LV", MARK_P3), ("P4_ARGS", MARK_P4),
        ("P5_WIRE", MARK_P5),
    ]:
        status = "✅" if marker in new_text else "❌ MISSING"
        print(f"  {status} {label}")

    if args.dry_run:
        print("\n[dry-run] No files written.")
        sys.exit(0)

    if args.output is None and not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{args.file}.bak.{ts}"
        shutil.copy2(args.file, backup)
        print(f"\nBackup saved: {backup}")

    out_path = args.output or args.file
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"Wrote: {out_path}  ({len(new_text):,} bytes)\n")

    print("=" * 72)
    print("  DONE — BEEsc-Cancel parity patch now fully applied")
    print("=" * 72)
    print()
    print("New flags (all OPT-IN, zero change when OFF):")
    print("  --be-cancel-close-only   Use CLOSED bar close (no wick, no ticker)")
    print("  --be-cancel-sr-check     Skip cancel if S/R broken by close")
    print()
    print("Test A/B/C on backtest:")
    print("  A) baseline (no new flags)         → same result as before")
    print("  B) --be-cancel-close-only")
    print("  C) --be-cancel-close-only --be-cancel-sr-check")


if __name__ == "__main__":
    main()
