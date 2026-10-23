#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_bee_cancel_patch.py
=========================
Adds BREAKEVEN_ESCAPE_CANCEL_KAPPA — optional "cancel escape on
strong bounce" feature on top of the existing BEEsc.

Behavior:
    - BEEsc activates as before (TP → entry at 0.30R adverse move)
    - If the bounce from the extreme reaches κ × σ_bar × entry
      BEFORE price touches entry, BEEsc is CANCELLED and TP is
      RESTORED to its original target.
    - κ = 0.0 (default) → feature DISABLED, current behavior preserved.

Usage:
    python3 apply_bee_cancel_patch.py            # patch in place
    python3 apply_bee_cancel_patch.py --dry-run  # verify only
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime

DEFAULT_FILE = "trading_2_live4_claude2_v4.py"


# ══════════════════════════════════════════════════════════════
# PATCH 1 — Config field
# ══════════════════════════════════════════════════════════════
P1_OLD = (
    "    BREAKEVEN_ESCAPE_MIN_PROFIT_R: float = 0.0\n"
    "    BREAKEVEN_ESCAPE_RESPECT_PARTIAL: bool = False\n"
)
P1_NEW = (
    "    BREAKEVEN_ESCAPE_MIN_PROFIT_R: float = 0.0\n"
    "    BREAKEVEN_ESCAPE_RESPECT_PARTIAL: bool = False\n"
    "    # ══ [BEEsc-CANCEL] cancel escape on strong bounce ══\n"
    "    # > 0: if the bounce from the extreme (after BEEsc fires)\n"
    "    # reaches κ × σ_bar × entry BEFORE price touches entry, cancel\n"
    "    # BEEsc and RESTORE the original TP.\n"
    "    # 0.0 = never cancel (default, current behavior preserved)\n"
    "    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 2 — Backtest price-trigger activation
# ══════════════════════════════════════════════════════════════
P2_OLD = (
    "                if _tp_new_be is not None:\n"
    "                    _tp_old_be = float(sig.tp1)\n"
    "                    sig.tp1 = _tp_new_be\n"
    "                    pos._be_esc_done = True\n"
    "                    #log.info(\n"
    "                    #    f\"[BEEsc-BT] {sig.symbol} {sig.action} \"\n"
    "                    #    f\"TP {_tp_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                    #    f\"({_be_rsn})\"\n"
    "                    #)\n"
)
P2_NEW = (
    "                if _tp_new_be is not None:\n"
    "                    _tp_old_be = float(sig.tp1)\n"
    "                    sig.tp1 = _tp_new_be\n"
    "                    pos._be_esc_done = True\n"
    "                    pos._be_orig_tp1 = _tp_old_be\n"
    "                    if sig.action == \"BUY\":\n"
    "                        pos._be_low = float(p)\n"
    "                    else:\n"
    "                        pos._be_high = float(p)\n"
    "                    #log.info(\n"
    "                    #    f\"[BEEsc-BT] {sig.symbol} {sig.action} \"\n"
    "                    #    f\"TP {_tp_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                    #    f\"({_be_rsn})\"\n"
    "                    #)\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 3 — Backtest cancel block (inserted after activation)
# ══════════════════════════════════════════════════════════════
P3_OLD = (
    "                    #log.info(\n"
    "                    #    f\"[BEEsc-BT] {sig.symbol} {sig.action} \"\n"
    "                    #    f\"TP {_tp_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                    #    f\"({_be_rsn})\"\n"
    "                    #)\n"
    "\n"
    "        # ── Determine sub-bar iteration range for this bar ──\n"
)
P3_NEW = (
    "                    #log.info(\n"
    "                    #    f\"[BEEsc-BT] {sig.symbol} {sig.action} \"\n"
    "                    #    f\"TP {_tp_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                    #    f\"({_be_rsn})\"\n"
    "                    #)\n"
    "\n"
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
    "\n"
    "        # ── Determine sub-bar iteration range for this bar ──\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 4 — Backtest signal-trigger activation
# ══════════════════════════════════════════════════════════════
P4_OLD = (
    "                    if _tp_new_be is not None:\n"
    "                        _tp_old_be = float(_be_pos.signal.tp1)\n"
    "                        _be_pos.signal.tp1 = _tp_new_be\n"
    "                        _be_pos._be_esc_done = True\n"
    "                        log.info(\n"
    "                            f\"[BEEsc-BT-Sig] {_be_pos.symbol} \"\n"
    "                            f\"{_be_pos.signal.action} \"\n"
    "                            f\"TP {_tp_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                            f\"({_be_rsn})\"\n"
    "                        )\n"
)
P4_NEW = (
    "                    if _tp_new_be is not None:\n"
    "                        _tp_old_be = float(_be_pos.signal.tp1)\n"
    "                        _be_pos.signal.tp1 = _tp_new_be\n"
    "                        _be_pos._be_esc_done = True\n"
    "                        _be_pos._be_orig_tp1 = _tp_old_be\n"
    "                        if _be_pos.signal.action == \"BUY\":\n"
    "                            _be_pos._be_low = float(_be_px)\n"
    "                        else:\n"
    "                            _be_pos._be_high = float(_be_px)\n"
    "                        log.info(\n"
    "                            f\"[BEEsc-BT-Sig] {_be_pos.symbol} \"\n"
    "                            f\"{_be_pos.signal.action} \"\n"
    "                            f\"TP {_tp_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                            f\"({_be_rsn})\"\n"
    "                        )\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 5 — Live price-trigger activation
# ══════════════════════════════════════════════════════════════
P5_OLD = (
    "                        if _tp_new_be is not None:\n"
    "                            _old_tp_be = float(pos['tp1'])\n"
    "                            pos['tp1'] = _tp_new_be\n"
    "                            pos['_be_esc_done'] = True\n"
    "                            log.info(\n"
    "                                f\"[BEEsc-LV] {sym} {pos['action']} \"\n"
    "                                f\"TP {_old_tp_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                                f\"({_be_rsn})\"\n"
    "                            )\n"
)
P5_NEW = (
    "                        if _tp_new_be is not None:\n"
    "                            _old_tp_be = float(pos['tp1'])\n"
    "                            pos['tp1'] = _tp_new_be\n"
    "                            pos['_be_esc_done'] = True\n"
    "                            pos['_be_orig_tp1'] = _old_tp_be\n"
    "                            if pos['action'] == \"BUY\":\n"
    "                                pos['_be_low'] = float(price)\n"
    "                            else:\n"
    "                                pos['_be_high'] = float(price)\n"
    "                            log.info(\n"
    "                                f\"[BEEsc-LV] {sym} {pos['action']} \"\n"
    "                                f\"TP {_old_tp_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                                f\"({_be_rsn})\"\n"
    "                            )\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 6 — Live cancel block
# ══════════════════════════════════════════════════════════════
P6_OLD = (
    "                            try:\n"
    "                                if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):\n"
    "                                    _sync_protective_orders(exchange, sym, pos)\n"
    "                            except Exception as _e:\n"
    "                                log.debug(f\"[BEEsc-LV] {sym} prot sync: {_e}\")\n"
    "                            try:\n"
    "                                _lv_save_state(state_file, open_pos_live)\n"
    "                            except Exception:\n"
    "                                pass\n"
    "\n"
    "                ex = False\n"
    "                rsn = \"\"\n"
)
P6_NEW = (
    "                            try:\n"
    "                                if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):\n"
    "                                    _sync_protective_orders(exchange, sym, pos)\n"
    "                            except Exception as _e:\n"
    "                                log.debug(f\"[BEEsc-LV] {sym} prot sync: {_e}\")\n"
    "                            try:\n"
    "                                _lv_save_state(state_file, open_pos_live)\n"
    "                            except Exception:\n"
    "                                pass\n"
    "\n"
    "                # ══ [BEEsc-CANCEL-Live] track extremes + cancel ══\n"
    "                if (pos.get('_be_esc_done', False)\n"
    "                        and not pos.get('_be_cancelled', False)\n"
    "                        and float(getattr(CFG, 'BREAKEVEN_ESCAPE_CANCEL_KAPPA', 0.0)) > 0\n"
    "                        and '_be_orig_tp1' in pos):\n"
    "                    try:\n"
    "                        _sigma_c = 0.01\n"
    "                        if ad is not None:\n"
    "                            _fi_c = (len(ad.closes) - 2 - ad.feat_start)\n"
    "                            if 0 <= _fi_c < len(ad.E_therm):\n"
    "                                _sigma_c = float(ad.E_therm[_fi_c])\n"
    "                        if not np.isfinite(_sigma_c) or _sigma_c <= 1e-9:\n"
    "                            _sigma_c = 0.01\n"
    "                        _kappa_c = float(CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA)\n"
    "                        _thr_c = _kappa_c * _sigma_c * float(pos['entry'])\n"
    "                        if pos['action'] == \"BUY\":\n"
    "                            _low_c = min(\n"
    "                                float(pos.get('_be_low', float(pos['entry']))),\n"
    "                                float(price),\n"
    "                            )\n"
    "                            pos['_be_low'] = _low_c\n"
    "                            _bounce_c = float(price) - _low_c\n"
    "                            if _bounce_c >= _thr_c:\n"
    "                                _restore_c = float(pos['_be_orig_tp1'])\n"
    "                                pos['tp1'] = _restore_c\n"
    "                                pos['_be_cancelled'] = True\n"
    "                                log.info(\n"
    "                                    f\"[BEEsc-Cancel-LV] {sym} BUY \"\n"
    "                                    f\"bounce={_bounce_c:.6f} ≥ \"\n"
    "                                    f\"{_thr_c:.6f} → TP restored to \"\n"
    "                                    f\"{_restore_c:.6f}\"\n"
    "                                )\n"
    "                                try:\n"
    "                                    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):\n"
    "                                        _sync_protective_orders(exchange, sym, pos)\n"
    "                                except Exception:\n"
    "                                    pass\n"
    "                                try:\n"
    "                                    _lv_save_state(state_file, open_pos_live)\n"
    "                                except Exception:\n"
    "                                    pass\n"
    "                        else:\n"
    "                            _high_c = max(\n"
    "                                float(pos.get('_be_high', float(pos['entry']))),\n"
    "                                float(price),\n"
    "                            )\n"
    "                            pos['_be_high'] = _high_c\n"
    "                            _bounce_c = _high_c - float(price)\n"
    "                            if _bounce_c >= _thr_c:\n"
    "                                _restore_c = float(pos['_be_orig_tp1'])\n"
    "                                pos['tp1'] = _restore_c\n"
    "                                pos['_be_cancelled'] = True\n"
    "                                log.info(\n"
    "                                    f\"[BEEsc-Cancel-LV] {sym} SELL \"\n"
    "                                    f\"bounce={_bounce_c:.6f} ≥ \"\n"
    "                                    f\"{_thr_c:.6f} → TP restored to \"\n"
    "                                    f\"{_restore_c:.6f}\"\n"
    "                                )\n"
    "                                try:\n"
    "                                    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):\n"
    "                                        _sync_protective_orders(exchange, sym, pos)\n"
    "                                except Exception:\n"
    "                                    pass\n"
    "                                try:\n"
    "                                    _lv_save_state(state_file, open_pos_live)\n"
    "                                except Exception:\n"
    "                                    pass\n"
    "                    except Exception as _e_c:\n"
    "                        log.debug(f\"[BEEsc-Cancel-LV] {sym}: {_e_c}\")\n"
    "\n"
    "                ex = False\n"
    "                rsn = \"\"\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 7 — Live signal-trigger activation
# ══════════════════════════════════════════════════════════════
P7_OLD = (
    "                            if _tp_new_be is not None:\n"
    "                                _old_be = float(_pos_be['tp1'])\n"
    "                                _pos_be['tp1'] = _tp_new_be\n"
    "                                _pos_be['_be_esc_done'] = True\n"
    "                                log.info(\n"
    "                                    f\"[BEEsc-LV-Sig] {_sig_be.symbol} \"\n"
    "                                    f\"{_pos_be['action']} \"\n"
    "                                    f\"TP {_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                                    f\"({_be_rsn})\"\n"
    "                                )\n"
)
P7_NEW = (
    "                            if _tp_new_be is not None:\n"
    "                                _old_be = float(_pos_be['tp1'])\n"
    "                                _pos_be['tp1'] = _tp_new_be\n"
    "                                _pos_be['_be_esc_done'] = True\n"
    "                                _pos_be['_be_orig_tp1'] = _old_be\n"
    "                                if _pos_be['action'] == \"BUY\":\n"
    "                                    _pos_be['_be_low'] = float(_p_be)\n"
    "                                else:\n"
    "                                    _pos_be['_be_high'] = float(_p_be)\n"
    "                                log.info(\n"
    "                                    f\"[BEEsc-LV-Sig] {_sig_be.symbol} \"\n"
    "                                    f\"{_pos_be['action']} \"\n"
    "                                    f\"TP {_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                                    f\"({_be_rsn})\"\n"
    "                                )\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 8 — CLI argument
# ══════════════════════════════════════════════════════════════
P8_OLD = (
    "    p.add_argument(\"--no-be-escape-ema\", action=\"store_true\",\n"
    "                   help=\"Disable EMA-flip requirement (pure price as \"\n"
    "                        \"trigger — RISKIER)\")\n"
)
P8_NEW = (
    "    p.add_argument(\"--no-be-escape-ema\", action=\"store_true\",\n"
    "                   help=\"Disable EMA-flip requirement (pure price as \"\n"
    "                        \"trigger — RISKIER)\")\n"
    "    p.add_argument(\"--be-escape-cancel-kappa\", type=float, default=None,\n"
    "                   help=\"Cancel BEEsc when bounce from extreme ≥ \"\n"
    "                        \"κ × σ_bar × entry BEFORE touching entry. \"\n"
    "                        \"TP is restored to its original target. \"\n"
    "                        \"0.0 = disabled (default)\")\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 9 — CLI wiring
# ══════════════════════════════════════════════════════════════
P9_OLD = (
    "    if getattr(args, \"no_be_escape_ema\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP = False\n"
    "        log.warning(\"[BEEsc] EMA-flip requirement DISABLED — \"\n"
    "                    \"HIGHER risk of premature exit\")\n"
)
P9_NEW = (
    "    if getattr(args, \"no_be_escape_ema\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP = False\n"
    "        log.warning(\"[BEEsc] EMA-flip requirement DISABLED — \"\n"
    "                    \"HIGHER risk of premature exit\")\n"
    "    if getattr(args, \"be_escape_cancel_kappa\", None) is not None:\n"
    "        CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA = float(\n"
    "            args.be_escape_cancel_kappa)\n"
    "    if CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA > 0:\n"
    "        log.info(\n"
    "            f\"[BEEsc] CANCEL enabled: κ=\"\n"
    "            f\"{CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA} × σ_bar — \"\n"
    "            f\"BEEsc will be undone if bounce from extreme exceeds \"\n"
    "            f\"this threshold before touching entry\"\n"
    "        )\n"
)


PATCHES = [
    ("P1_CONFIG",    "Add BREAKEVEN_ESCAPE_CANCEL_KAPPA",       P1_OLD, P1_NEW),
    ("P2_BT_ACT",    "Backtest price-trigger: store state",      P2_OLD, P2_NEW),
    ("P3_BT_CANCEL", "Backtest cancel block",                    P3_OLD, P3_NEW),
    ("P4_BT_SIG",    "Backtest signal-trigger: store state",     P4_OLD, P4_NEW),
    ("P5_LV_ACT",    "Live price-trigger: store state",          P5_OLD, P5_NEW),
    ("P6_LV_CANCEL", "Live cancel block",                        P6_OLD, P6_NEW),
    ("P7_LV_SIG",    "Live signal-trigger: store state",         P7_OLD, P7_NEW),
    ("P8_ARGS",      "Add --be-escape-cancel-kappa flag",        P8_OLD, P8_NEW),
    ("P9_WIRE",      "CLI wiring",                               P9_OLD, P9_NEW),
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
    if "BREAKEVEN_ESCAPE_CANCEL_KAPPA" in src_text:
        raise RuntimeError(
            "Patch already applied (found BREAKEVEN_ESCAPE_CANCEL_KAPPA). "
            "Restore from a backup before re-applying.")
    if "def _should_breakeven_escape" not in src_text:
        raise RuntimeError(
            "Prerequisite missing: BEEsc base feature not found. "
            "Apply apply_bee_patch.py first.")

    text = src_text
    applied = []
    for pid, desc, old, new in PATCHES:
        n_old = _count(text, old)
        if n_old == 0:
            raise RuntimeError(
                f"[{pid}] anchor NOT FOUND: {desc}\n"
                f"  preview: {old[:200]!r}")
        if n_old > 1:
            raise RuntimeError(
                f"[{pid}] anchor AMBIGUOUS ({n_old} matches): {desc}")
        text = text.replace(old, new, 1)
        applied.append((pid, desc))
        print(f"  [OK]   {pid:14s} — {desc}")
    return text, applied


def verify_syntax(text):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"


def main():
    ap = argparse.ArgumentParser(
        description="Add BEEsc-CANCEL feature to the bot.")
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--output", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: source file not found: {args.file}")
        sys.exit(1)

    print(f"Reading {args.file}...")
    with open(args.file, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"  size: {len(src):,} bytes\n")

    print("Applying 9 patches...")
    try:
        new_text, applied = apply_patches(src)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print(f"\n{len(applied)}/9 patches applied.\n")

    print("Verifying syntax...")
    ok, err = verify_syntax(new_text)
    if not ok:
        print(f"  FAIL: {err}")
        print("  No files were written.")
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

    print("=" * 68)
    print("  DONE — BEEsc-CANCEL patched successfully")
    print("=" * 68)
    print()
    print("What it does:")
    print("  • After BEEsc fires (TP moved to entry), track the extreme")
    print("    (low for BUY, high for SELL) as price continues.")
    print("  • If the bounce from that extreme reaches κ × σ_bar × entry")
    print("    BEFORE price touches entry, CANCEL BEEsc and RESTORE the")
    print("    original TP (e.g., 2.5R).")
    print("  • Default κ = 0.0 → feature DISABLED, no behavior change.")
    print()
    print("New CLI flag:")
    print("  --be-escape-cancel-kappa FLOAT")
    print("    0.0 = disabled (default)")
    print("    0.3 = aggressive (small bounce triggers cancel)")
    print("    0.5 = balanced (recommended starting point)")
    print("    1.0 = conservative (big bounce required)")
    print()
    print("Test in backtest:")
    print("  --be-escape --be-escape-cancel-kappa 0.5")
    print("  then compare E[ln], Sharpe, Hard TP, Emergency SL, MaxDD")


if __name__ == "__main__":
    main()
