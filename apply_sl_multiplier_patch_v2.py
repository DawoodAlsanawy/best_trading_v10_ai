#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_sl_multiplier_patch_v2.py
================================
Fixed P5 anchor — disambiguates the two SL_WIDEN_MULT blocks in main()
by including the CFG.SELL_ONLY = True line (present only in the first).

All other patches (P1-P4) unchanged from v1.
"""

import argparse
import ast
import os
import re
import shutil
import sys
from datetime import datetime

DEFAULT_FILE = "trading_2_live4_claude2_v4.py"


MARK_P1 = "SL_MULTIPLIER: float = 1.0"
MARK_P2 = "[SL-MULTIPLIER — Real widening]"
MARK_P3 = "[SL-MULTIPLIER — Real widening]"
MARK_P4 = "--sl-multiplier"
MARK_P5 = "CFG.SL_MULTIPLIER = float"


# P1 — Config
P1_PATTERN = re.compile(r'(\n    SL_WIDEN_MULT: float = [\d.]+\n)')
P1_NEW = (
    "\n    SL_WIDEN_MULT: float = 1.5\n"
    "\n"
    "    # ══ [SL-MULTIPLIER — Real Widening] ══\n"
    "    # SL_WIDEN_MULT acts as a CAP (min SL floor) only.\n"
    "    # SL_MULTIPLIER multiplies geodesic SL BEFORE the cap.\n"
    "    # 1.0 → 100%% backward compatible (no change)\n"
    "    # 1.3 → widen SL +30%%, TP +30%% (R:R preserved)\n"
    "    SL_MULTIPLIER: float = 1.0\n"
    "    # ══ [ABSOLUTE SAFETY CAPS] ══\n"
    "    MAX_ABS_SL_FRAC: float = 0.08\n"
    "    MAX_ABS_TP_FRAC: float = 0.15\n"
    "    # ══ [SWING FLOOR — Optional] ══\n"
    "    SL_USE_SWING_FLOOR: bool = False\n"
    "    SL_SWING_LOOKBACK: int = 60\n"
    "    SL_SWING_BUFFER_ATR: float = 0.3\n"
)


# P2 — Backtest SL/TP block
P2_OLD = (
    "        _design_sl_dist = abs(sig.price - sig.sl)\n"
    "        _design_tp_dist = abs(sig.tp1 - sig.price)\n"
    "        if _design_sl_dist <= 1e-12:\n"
    "            continue\n"
    "\n"
    "        # Clip SL to max_sl_frac × opt_px (entry-based cap)\n"
    "        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))\n"
    "        if _design_sl_dist > opt_px * _max_sl_frac:\n"
    "            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)\n"
    "            _design_sl_dist = opt_px * _max_sl_frac\n"
    "            _design_tp_dist = _design_sl_dist * _rr\n"
)

P2_NEW = (
    "        _design_sl_dist = abs(sig.price - sig.sl)\n"
    "        _design_tp_dist = abs(sig.tp1 - sig.price)\n"
    "        if _design_sl_dist <= 1e-12:\n"
    "            continue\n"
    "\n"
    "        # ══ [SL-MULTIPLIER — Real widening] ══\n"
    "        _sl_mult_new = float(getattr(CFG, 'SL_MULTIPLIER', 1.0))\n"
    "        if _sl_mult_new != 1.0:\n"
    "            _design_sl_dist = _design_sl_dist * _sl_mult_new\n"
    "            _design_tp_dist = _design_tp_dist * _sl_mult_new\n"
    "\n"
    "        # ══ [SWING FLOOR — Optional] ══\n"
    "        if getattr(CFG, 'SL_USE_SWING_FLOOR', False):\n"
    "            try:\n"
    "                _sw_swing = _find_nearest_swing(\n"
    "                    ad, opt_ci,\n"
    "                    int(getattr(CFG, 'SL_SWING_LOOKBACK', 60)),\n"
    "                    \"low\" if sig.action == \"BUY\" else \"high\")\n"
    "                if _sw_swing is not None:\n"
    "                    _sw_atr = float(ad.atr14[opt_ci]) \\\n"
    "                        if opt_ci < len(ad.atr14) else 0.0\n"
    "                    _sw_dist = abs(opt_px - _sw_swing) + \\\n"
    "                        float(getattr(CFG, 'SL_SWING_BUFFER_ATR', 0.3)) * _sw_atr\n"
    "                    if _sw_dist > _design_sl_dist:\n"
    "                        _sw_rr = _design_tp_dist / max(_design_sl_dist, 1e-12)\n"
    "                        _design_sl_dist = _sw_dist\n"
    "                        _design_tp_dist = _design_sl_dist * _sw_rr\n"
    "            except Exception as _sw_e:\n"
    "                log.debug(f\"[SwingFloor-BT] {sym} failed: {_sw_e}\")\n"
    "\n"
    "        # ══ [ABSOLUTE CAP vs BACKWARD COMPAT] ══\n"
    "        if _sl_mult_new != 1.0:\n"
    "            _max_abs_sl = opt_px * float(getattr(\n"
    "                CFG, 'MAX_ABS_SL_FRAC', 0.08))\n"
    "            _max_abs_tp = opt_px * float(getattr(\n"
    "                CFG, 'MAX_ABS_TP_FRAC', 0.15))\n"
    "            if _design_sl_dist > _max_abs_sl:\n"
    "                _abs_rr = _design_tp_dist / max(_design_sl_dist, 1e-12)\n"
    "                _design_sl_dist = _max_abs_sl\n"
    "                _design_tp_dist = min(_design_sl_dist * _abs_rr,\n"
    "                                       _max_abs_tp)\n"
    "            if _design_tp_dist > _max_abs_tp:\n"
    "                _design_tp_dist = _max_abs_tp\n"
    "        else:\n"
    "            _max_sl_frac = 0.015 * float(getattr(\n"
    "                CFG, 'SL_WIDEN_MULT', 1.0))\n"
    "            if _design_sl_dist > opt_px * _max_sl_frac:\n"
    "                _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)\n"
    "                _design_sl_dist = opt_px * _max_sl_frac\n"
    "                _design_tp_dist = _design_sl_dist * _rr\n"
)


# P3 — Live SL/TP block
P3_OLD = (
    "    rr = orig_tp_dist / orig_sl_dist\n"
    "    # Cap scales with widening so the loosened SL isn't re-clipped.\n"
    "    max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))\n"
    "    if orig_sl_dist > entry_price * max_sl_frac:\n"
    "        orig_sl_dist = entry_price * max_sl_frac\n"
    "        orig_tp_dist = orig_sl_dist * rr\n"
)

P3_NEW = (
    "    rr = orig_tp_dist / orig_sl_dist\n"
    "\n"
    "    # ══ [SL-MULTIPLIER — Real widening] ══\n"
    "    _sl_mult_new_lv = float(getattr(CFG, 'SL_MULTIPLIER', 1.0))\n"
    "    if _sl_mult_new_lv != 1.0:\n"
    "        orig_sl_dist = orig_sl_dist * _sl_mult_new_lv\n"
    "        orig_tp_dist = orig_sl_dist * rr\n"
    "\n"
    "    # ══ [SWING FLOOR — Optional] ══\n"
    "    if getattr(CFG, 'SL_USE_SWING_FLOOR', False):\n"
    "        try:\n"
    "            _ad_lv = rec.get('ad_ref')\n"
    "            if _ad_lv is not None:\n"
    "                _ci_lv = max(0, len(_ad_lv.closes) - 2)\n"
    "                _sw_lv = _find_nearest_swing(\n"
    "                    _ad_lv, _ci_lv,\n"
    "                    int(getattr(CFG, 'SL_SWING_LOOKBACK', 60)),\n"
    "                    \"low\" if rec['action'] == 'BUY' else \"high\")\n"
    "                if _sw_lv is not None:\n"
    "                    _sw_atr_lv = float(_ad_lv.atr14[_ci_lv]) \\\n"
    "                        if _ci_lv < len(_ad_lv.atr14) else 0.0\n"
    "                    _sw_dist_lv = abs(entry_price - _sw_lv) + \\\n"
    "                        float(getattr(CFG, 'SL_SWING_BUFFER_ATR', 0.3)) * _sw_atr_lv\n"
    "                    if _sw_dist_lv > orig_sl_dist:\n"
    "                        orig_sl_dist = _sw_dist_lv\n"
    "                        orig_tp_dist = orig_sl_dist * rr\n"
    "        except Exception as _sw_e_lv:\n"
    "            log.debug(f\"[SwingFloor-LV] {sym} failed: {_sw_e_lv}\")\n"
    "\n"
    "    # ══ [ABSOLUTE CAP vs BACKWARD COMPAT] ══\n"
    "    if _sl_mult_new_lv != 1.0:\n"
    "        _max_abs_sl_lv = entry_price * float(getattr(\n"
    "            CFG, 'MAX_ABS_SL_FRAC', 0.08))\n"
    "        _max_abs_tp_lv = entry_price * float(getattr(\n"
    "            CFG, 'MAX_ABS_TP_FRAC', 0.15))\n"
    "        if orig_sl_dist > _max_abs_sl_lv:\n"
    "            orig_sl_dist = _max_abs_sl_lv\n"
    "            orig_tp_dist = min(orig_sl_dist * rr, _max_abs_tp_lv)\n"
    "        if orig_tp_dist > _max_abs_tp_lv:\n"
    "            orig_tp_dist = _max_abs_tp_lv\n"
    "    else:\n"
    "        max_sl_frac = 0.015 * float(getattr(\n"
    "            CFG, 'SL_WIDEN_MULT', 1.0))\n"
    "        if orig_sl_dist > entry_price * max_sl_frac:\n"
    "            orig_sl_dist = entry_price * max_sl_frac\n"
    "            orig_tp_dist = orig_sl_dist * rr\n"
)


# P4 — CLI args
P4_OLD = (
    "    p.add_argument(\"--sl-widen-mult\", type=float, default=None,\n"
    "                   help=\"Override SL_WIDEN_MULT\")\n"
)
P4_NEW = (
    "    p.add_argument(\"--sl-widen-mult\", type=float, default=None,\n"
    "                   help=\"Override SL_WIDEN_MULT\")\n"
    "    p.add_argument(\"--sl-multiplier\", type=float, default=None,\n"
    "                   help=\"Real SL multiplier (1.0=no change, \"\n"
    "                        \"1.3=+30%%, 2.0=+100%%)\")\n"
    "    p.add_argument(\"--max-abs-sl-frac\", type=float, default=None,\n"
    "                   help=\"Absolute SL cap (default 0.08 = 8%%)\")\n"
    "    p.add_argument(\"--max-abs-tp-frac\", type=float, default=None,\n"
    "                   help=\"Absolute TP cap (default 0.15 = 15%%)\")\n"
    "    p.add_argument(\"--sl-use-swing-floor\", action=\"store_true\",\n"
    "                   help=\"Extend SL to swing low/high + buffer\")\n"
    "    p.add_argument(\"--sl-swing-lookback\", type=int, default=None,\n"
    "                   help=\"Lookback bars for swing search (default 60)\")\n"
    "    p.add_argument(\"--sl-swing-buffer-atr\", type=float, default=None,\n"
    "                   help=\"Buffer below swing × ATR (default 0.3)\")\n"
)


# P5 — CLI WIRING (FIXED: includes CFG.SELL_ONLY disambiguator)
P5_OLD = (
    "    if getattr(args, \"sl_widen_mult\", None) is not None:\n"
    "        CFG.SL_WIDEN_MULT = float(args.sl_widen_mult)\n"
    "        log.info(f\"[Ablation] SL_WIDEN_MULT = {CFG.SL_WIDEN_MULT}\")\n"
    "    if getattr(args, \"sell_only\", False):\n"
    "        CFG.SELL_ONLY = True\n"
)
P5_NEW = (
    "    if getattr(args, \"sl_widen_mult\", None) is not None:\n"
    "        CFG.SL_WIDEN_MULT = float(args.sl_widen_mult)\n"
    "        log.info(f\"[Ablation] SL_WIDEN_MULT = {CFG.SL_WIDEN_MULT}\")\n"
    "    if getattr(args, \"sl_multiplier\", None) is not None:\n"
    "        CFG.SL_MULTIPLIER = float(args.sl_multiplier)\n"
    "        if CFG.SL_MULTIPLIER != 1.0:\n"
    "            log.info(\n"
    "                f\"[SL] SL_MULTIPLIER = {CFG.SL_MULTIPLIER}× \"\n"
    "                f\"(real widening; TP follows R:R)\")\n"
    "    if getattr(args, \"max_abs_sl_frac\", None) is not None:\n"
    "        CFG.MAX_ABS_SL_FRAC = float(args.max_abs_sl_frac)\n"
    "    if getattr(args, \"max_abs_tp_frac\", None) is not None:\n"
    "        CFG.MAX_ABS_TP_FRAC = float(args.max_abs_tp_frac)\n"
    "    if getattr(args, \"sl_use_swing_floor\", False):\n"
    "        CFG.SL_USE_SWING_FLOOR = True\n"
    "        log.info(\n"
    "            f\"[SL] SWING FLOOR enabled \"\n"
    "            f\"(lookback={CFG.SL_SWING_LOOKBACK}, \"\n"
    "            f\"buffer_atr={CFG.SL_SWING_BUFFER_ATR})\")\n"
    "    if getattr(args, \"sl_swing_lookback\", None) is not None:\n"
    "        CFG.SL_SWING_LOOKBACK = int(args.sl_swing_lookback)\n"
    "    if getattr(args, \"sl_swing_buffer_atr\", None) is not None:\n"
    "        CFG.SL_SWING_BUFFER_ATR = float(args.sl_swing_buffer_atr)\n"
    "    if getattr(args, \"sell_only\", False):\n"
    "        CFG.SELL_ONLY = True\n"
)


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
    return text.replace(m.group(1), new_block, 1), "OK"


def apply_all(src_text):
    text = src_text
    results = []

    if MARK_P1 in text:
        results.append(("P1_CONFIG", "SKIP_ALREADY", "Config fields"))
    else:
        text, status = _apply_regex(text, P1_PATTERN, P1_NEW, "P1")
        results.append(("P1_CONFIG", status, "Config fields"))

    if text.count("[SL-MULTIPLIER — Real widening]") >= 2:
        results.append(("P2_BT", "SKIP_ALREADY", "Backtest block"))
    else:
        text, status = _apply_exact(text, P2_OLD, P2_NEW, "P2")
        results.append(("P2_BT", status, "Backtest block"))

    if "if _sl_mult_new_lv != 1.0:" in text:
        results.append(("P3_LV", "SKIP_ALREADY", "Live block"))
    else:
        text, status = _apply_exact(text, P3_OLD, P3_NEW, "P3")
        results.append(("P3_LV", status, "Live block"))

    if MARK_P4 in text:
        results.append(("P4_ARGS", "SKIP_ALREADY", "CLI args"))
    else:
        text, status = _apply_exact(text, P4_OLD, P4_NEW, "P4")
        results.append(("P4_ARGS", status, "CLI args"))

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
        description="Apply SL_MULTIPLIER patch (v2 — fixed P5 anchor).")
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

    print("Applying 5 patches (v2)...")
    new_text, results = apply_all(src)

    for pid, status, desc in results:
        if status == "OK":
            sym = "✓"
        elif status == "SKIP_ALREADY":
            sym = "⏭ "
        else:
            sym = "✗"
        print(f"  [{status:22s}] {sym} {pid:11s} — {desc}")

    n_ok = sum(1 for _, s, _ in results if s in ("OK", "SKIP_ALREADY"))
    n_fail = len(results) - n_ok
    print(f"\n  Applied: {n_ok}/{len(results)}")

    if n_fail > 0:
        print(f"\n  ⚠ {n_fail} patch(es) failed.")
        for pid, status, desc in results:
            if status not in ("OK", "SKIP_ALREADY"):
                print(f"    ✗ {pid}: {status}")
        sys.exit(1)

    print("\nVerifying syntax...")
    ok, err = verify_syntax(new_text)
    if not ok:
        print(f"  FAIL: {err}")
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
    print("  DONE — SL_MULTIPLIER + Safety Caps + Swing Floor applied")
    print("=" * 74)
    print()
    print("New CLI flags (all OPT-IN, default = no change):")
    print("  --sl-multiplier FLOAT")
    print("  --max-abs-sl-frac FLOAT  (default 0.08)")
    print("  --max-abs-tp-frac FLOAT  (default 0.15)")
    print("  --sl-use-swing-floor")
    print("  --sl-swing-lookback INT  (default 60)")
    print("  --sl-swing-buffer-atr FLOAT  (default 0.3)")
    print()
    print("Test A/B/C/D on backtest:")
    print("  A) no flags                           → baseline")
    print("  B) --sl-multiplier 1.3                → +30% SL/TP")
    print("  C) --sl-multiplier 1.5                → +50% SL/TP")
    print("  D) --sl-multiplier 1.3 --sl-use-swing-floor")


if __name__ == "__main__":
    main()
