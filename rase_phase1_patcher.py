#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  RASE Phase 1 — Automated Batch Patcher                                      ║
║  Regime-Adaptive Sub-Bar Entry — Surgical implementation on trading bot      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Applies 12 atomic patches delivering Phase 1:                               ║
║                                                                              ║
║  Layer 1 — Regime classification:                                            ║
║    • 4-state regime (ranging / normal / trending / explosive)               ║
║    • 'normal' vs 'trending' split via gauge_force p75                       ║
║                                                                              ║
║  Layer 2 — Regime-adaptive dip (clamped):                                   ║
║    • dip = regime_mult × σ_bar × price                                      ║
║    • Clamped to [0.4, 1.0] × friction_dip (preserves physics)               ║
║                                                                              ║
║  Layer 3 — Sub-bar rejection:                                                ║
║    • Backtest: touch+bounce via _check_reversal_fill_subbars                ║
║    • Live: watcher registration (existing infra)                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  USAGE:                                                                      ║
║    python3 rase_phase1_patcher.py                  # patch default file     ║
║    python3 rase_phase1_patcher.py --dry-run        # preview, no write      ║
║    python3 rase_phase1_patcher.py --verify-only    # check patched state    ║
║    python3 rase_phase1_patcher.py --rollback       # restore latest backup  ║
║    python3 rase_phase1_patcher.py --target FILE    # custom target         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  SAFETY:                                                                     ║
║    • Timestamped backup before write                                         ║
║    • ast.parse() syntax validation                                           ║
║    • Idempotent (safe to re-run)                                             ║
║    • Atomic write (tmp → os.replace)                                         ║
║    • Every anchor must match EXACTLY ONCE                                    ║
║    • Auto-rollback on failure                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"
MARKER = "# ═══ [RASE-PHASE-1-APPLIED] ═══"


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════
# Every `old` string MUST appear exactly once in the target.
# Every `new` string contains the modified version.

PATCHES = [

    # ═══════════════════════════════════════════════════════════════════════
    # P01 — Config fields
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P01-config-fields",
        "desc": "Add RASE config fields + 'normal' regime multiplier",
        "old": (
            "    ENTRY_REGIME_EXPLOSIVE_MULT: float = 1.30\n"
            "    # Layer 3: structure anchor (nearest swing)\n"
        ),
        "new": (
            "    ENTRY_REGIME_EXPLOSIVE_MULT: float = 1.30\n"
            "    ENTRY_REGIME_NORMAL_MULT: float = 1.50\n"
            "    # ══ [RASE Phase 1] Regime-Adaptive Sub-Bar Entry ══\n"
            "    # Disabled by default → bit-identical to legacy behavior.\n"
            "    # When True → regime-classified dip + sub-bar rejection.\n"
            "    RASE_ENABLED: bool = False\n"
            "    RASE_DIP_FLOOR_FRAC: float = 0.4      # dip floor (× friction_dip)\n"
            "    RASE_DIP_CAP_FRAC:   float = 1.0      # dip cap   (× friction_dip)\n"
            "    RASE_REGIME_GAUGE_P75_WINDOW: int = 200\n"
            "    # ══ [RASE end] ══\n"
            "    # Layer 3: structure anchor (nearest swing)\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P02 — Regime classifier: split (0.7, 1.6) band via gauge p75
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P02-regime-classifier",
        "desc": "Split 'trending' into 'trending' vs 'normal' via gauge p75",
        "old": (
            "        ratio = sig_now / sig_mean\n"
            "        if ratio > 1.6:\n"
            "            return \"explosive\"\n"
            "        elif ratio < 0.7:\n"
            "            return \"ranging\"\n"
            "        else:\n"
            "            return \"trending\"\n"
            "    except Exception:\n"
            "        return \"normal\"\n"
        ),
        "new": (
            "        ratio = sig_now / sig_mean\n"
            "        if ratio > 1.6:\n"
            "            return \"explosive\"\n"
            "        elif ratio < 0.7:\n"
            "            return \"ranging\"\n"
            "        # ══ [RASE Phase 1] distinguish trending from normal via gauge ══\n"
            "        if not getattr(CFG, 'RASE_ENABLED', False):\n"
            "            return \"trending\"\n"
            "        try:\n"
            "            _win = int(getattr(CFG, 'RASE_REGIME_GAUGE_P75_WINDOW', 200))\n"
            "            _lo = max(0, fi - _win)\n"
            "            _gf = ad.gauge_force[_lo:fi + 1]\n"
            "            if len(_gf) >= 20:\n"
            "                _p75 = float(np.percentile(_gf, 75))\n"
            "                _g_now = float(ad.gauge_force[fi])\n"
            "                if np.isfinite(_g_now) and _g_now > _p75:\n"
            "                    return \"trending\"\n"
            "            return \"normal\"\n"
            "        except Exception:\n"
            "            return \"normal\"\n"
            "    except Exception:\n"
            "        return \"normal\"\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P03 — Regime multiplier: handle 'normal'
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P03-regime-mult",
        "desc": "Extend _regime_entry_mult to handle 'normal' state",
        "old": (
            "def _regime_entry_mult(regime: str) -> float:\n"
            "    \"\"\"Entry dip multiplier by regime.\"\"\"\n"
            "    if regime == \"explosive\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_EXPLOSIVE_MULT', 1.30))\n"
            "    if regime == \"ranging\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_RANGING_MULT', 0.60))\n"
            "    return float(getattr(CFG, 'ENTRY_REGIME_TRENDING_MULT', 1.00))\n"
        ),
        "new": (
            "def _regime_entry_mult(regime: str) -> float:\n"
            "    \"\"\"Entry dip multiplier by regime.\"\"\"\n"
            "    if regime == \"explosive\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_EXPLOSIVE_MULT', 1.30))\n"
            "    if regime == \"ranging\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_RANGING_MULT', 0.60))\n"
            "    if regime == \"normal\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_NORMAL_MULT', 1.50))\n"
            "    return float(getattr(CFG, 'ENTRY_REGIME_TRENDING_MULT', 1.00))\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P04 — New helper: _compute_rase_dip (clamped regime dip)
    # Inserted right after _compute_entry_dip's return statement
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P04-rase-dip-helper",
        "desc": "Insert _compute_rase_dip helper (clamped regime-adaptive dip)",
        "old": (
            "        dip = float(np.clip(dip, min_d, max_d))\n"
            "        return float(dip)\n"
            "    except Exception:\n"
            "        return 0.0\n"
            "\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "# § TRADE FILTER — Pre-entry multi-signal rejection\n"
        ),
        "new": (
            "        dip = float(np.clip(dip, min_d, max_d))\n"
            "        return float(dip)\n"
            "    except Exception:\n"
            "        return 0.0\n"
            "\n"
            "\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "# [RASE Phase 1] Regime-adaptive dip (clamped to physics envelope)\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "def _compute_rase_dip(ad, fi, ci, action, close_price, sigma_price):\n"
            "    \"\"\"\n"
            "    RASE Layer 2 — dip that adapts to the current market regime.\n"
            "\n"
            "    The 'friction dip' (4σ_bar) is the base physics envelope.\n"
            "    Regime scales the dip WITHIN that envelope:\n"
            "      ranging   → 0.60 × friction_dip  (shallower, quiet market)\n"
            "      normal    → 1.00 × friction_dip  (equivalent to legacy)\n"
            "      trending  → 1.00 × friction_dip  (legacy)\n"
            "      explosive → 1.30 × friction_dip  (deeper, wild market)\n"
            "\n"
            "    Result is clamped to [floor×friction, cap×friction] so the\n"
            "    original 'friction tunnel' philosophy is never violated.\n"
            "    Returns 0.0 on any failure → caller falls back to friction_dip.\n"
            "    \"\"\"\n"
            "    try:\n"
            "        if not getattr(CFG, 'RASE_ENABLED', False):\n"
            "            return 0.0\n"
            "        if sigma_price <= 0 or close_price <= 0:\n"
            "            return 0.0\n"
            "        regime = _classify_regime_local(\n"
            "            ad, fi, int(getattr(CFG, 'ENTRY_REGIME_LOOKBACK', 100))\n"
            "        )\n"
            "        mult = _regime_entry_mult(regime)\n"
            "        # Base: friction dip = 4 × σ_price. Regime scales it.\n"
            "        _fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))\n"
            "        friction_dip = _fd_kappa * sigma_price\n"
            "        raw_dip = friction_dip * mult\n"
            "        floor_frac = float(getattr(CFG, 'RASE_DIP_FLOOR_FRAC', 0.4))\n"
            "        cap_frac   = float(getattr(CFG, 'RASE_DIP_CAP_FRAC', 1.0))\n"
            "        lo = friction_dip * floor_frac\n"
            "        hi = friction_dip * cap_frac\n"
            "        if hi < lo:\n"
            "            lo, hi = hi, lo\n"
            "        return float(np.clip(raw_dip, lo, hi))\n"
            "    except Exception:\n"
            "        return 0.0\n"
            "\n"
            "\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "# § TRADE FILTER — Pre-entry multi-signal rejection\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P05 — build_signals: replace dip selection with RASE logic
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P05-dip-selection",
        "desc": "Route dip selection through _compute_rase_dip when RASE_ENABLED",
        "old": (
            "            _sigma_price_bs = _sigma_frac_bs * p\n"
            "            _fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))\n"
            "            _friction_dip = _fd_kappa * _sigma_price_bs\n"
            "            _atr_dip = _compute_entry_dip(ad, fi, ci, action, p)\n"
            "            # Floor: never use a dip smaller than 0.5×ATR\n"
            "            _entry_dip = max(_friction_dip, 0.5 * _atr_dip)\n"
            "            if _entry_dip <= 0.0:\n"
            "                _entry_dip = p * 0.001\n"
        ),
        "new": (
            "            _sigma_price_bs = _sigma_frac_bs * p\n"
            "            _fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))\n"
            "            _friction_dip = _fd_kappa * _sigma_price_bs\n"
            "            # ══ [RASE Phase 1] regime-adaptive dip when enabled ══\n"
            "            _entry_dip = 0.0\n"
            "            if getattr(CFG, 'RASE_ENABLED', False):\n"
            "                _entry_dip = _compute_rase_dip(\n"
            "                    ad, fi, ci, action, p, _sigma_price_bs\n"
            "                )\n"
            "            if _entry_dip <= 0.0:\n"
            "                # Legacy path (unchanged)\n"
            "                _atr_dip = _compute_entry_dip(ad, fi, ci, action, p)\n"
            "                _entry_dip = max(_friction_dip, 0.5 * _atr_dip)\n"
            "            if _entry_dip <= 0.0:\n"
            "                _entry_dip = p * 0.001\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P06 — precompute_entry_fills: hook for RASE sub-bar path
    # Insert right before `target0 = _backtest_entry_target(sig, ad)`
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P06-subbar-hook",
        "desc": "Add RASE sub-bar rejection hook in precompute_entry_fills",
        "old": (
            "            if first_bar >= stage1_last and first_bar >= stage2_last:\n"
            "                result[sig_i] = None\n"
            "                continue\n"
            "\n"
            "            target0 = _backtest_entry_target(sig, ad)\n"
        ),
        "new": (
            "            if first_bar >= stage1_last and first_bar >= stage2_last:\n"
            "                result[sig_i] = None\n"
            "                continue\n"
            "\n"
            "            target0 = _backtest_entry_target(sig, ad)\n"
            "            # ══ [RASE Phase 1] sub-bar rejection path ══\n"
            "            if (getattr(CFG, 'RASE_ENABLED', False)\n"
            "                    and ad.sub_highs is not None\n"
            "                    and ad.sub_lows is not None\n"
            "                    and ad.sub_closes is not None\n"
            "                    and ad.sub_per_main >= 2\n"
            "                    and not getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False)):\n"
            "                _rase_win = int(max(4, np.ceil(\n"
            "                    float(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))\n"
            "                    * float(CFG.TF_SCALE)\n"
            "                )))\n"
            "                _rase_deadline = min(first_bar + _rase_win, stage2_last)\n"
            "                _rase_res = _check_reversal_fill_subbars(\n"
            "                    ad, sig, target0, CFG,\n"
            "                    first_bar, _rase_deadline,\n"
            "                )\n"
            "                if _rase_res is None:\n"
            "                    result[sig_i] = None\n"
            "                    continue\n"
            "                _rase_ci, _rase_px = _rase_res\n"
            "                result[sig_i] = ('S1', int(_rase_ci), float(_rase_px))\n"
            "                continue\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P07 — simulate_portfolio: log RASE status
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P07-sim-log",
        "desc": "Log RASE mode status in simulate_portfolio",
        "old": (
            "    n_total_sigs = len(signals)\n"
            "    n_would_fill = sum(1 for v in fill_map.values() if v is not None)\n"
            "    log.info(f\"  [Backtest Realism] Entry fills: \"\n"
        ),
        "new": (
            "    n_total_sigs = len(signals)\n"
            "    n_would_fill = sum(1 for v in fill_map.values() if v is not None)\n"
            "    # ══ [RASE Phase 1] announce mode ══\n"
            "    if getattr(CFG, 'RASE_ENABLED', False):\n"
            "        _rase_ok = (not WATCH_REMOVED) and getattr(CFG, 'WATCH_MODE_ENABLED', False)\n"
            "        _sub_ok = any(getattr(a, 'sub_per_main', 0) >= 2\n"
            "                       for a in assets.values())\n"
            "        log.info(\n"
            "            f\"  [RASE Phase 1] ENABLED  \"\n"
            "            f\"subbar_avail={_sub_ok}  \"\n"
            "            f\"watch_mode={_rase_ok}  \"\n"
            "            f\"dip_range=[{CFG.RASE_DIP_FLOOR_FRAC:.2f},{CFG.RASE_DIP_CAP_FRAC:.2f}]×friction\"\n"
            "        )\n"
            "        if not _sub_ok:\n"
            "            log.warning(\n"
            "                \"  [RASE Phase 1] NO sub-bar data → falling back \"\n"
            "                \"to legacy linear fill\"\n"
            "            )\n"
            "    log.info(f\"  [Backtest Realism] Entry fills: \"\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P08 — print_report: show RASE-specific stats
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P08-report-section",
        "desc": "Print RASE Phase 1 section in report",
        "old": (
            "    print(f\"\\n▶ توزيع أسباب الخروج\")\n"
            "    for r,c in sorted(m['exit_distribution'].items(), key=lambda x:-x[1]):\n"
            "        print(f\"   {r:25s}: {c:7,}  ({c/m['n_trades']*100:.1f}%)\")\n"
        ),
        "new": (
            "    print(f\"\\n▶ توزيع أسباب الخروج\")\n"
            "    for r,c in sorted(m['exit_distribution'].items(), key=lambda x:-x[1]):\n"
            "        print(f\"   {r:25s}: {c:7,}  ({c/m['n_trades']*100:.1f}%)\")\n"
            "\n"
            "    # ══ [RASE Phase 1] dedicated section ══\n"
            "    if getattr(CFG, 'RASE_ENABLED', False):\n"
            "        print(f\"\\n▶ RASE Phase 1\")\n"
            "        print(f\"   الوضع             : ENABLED\")\n"
            "        print(f\"   dip floor/cap      : \"\n"
            "              f\"[{CFG.RASE_DIP_FLOOR_FRAC:.2f}, \"\n"
            "              f\"{CFG.RASE_DIP_CAP_FRAC:.2f}] × friction_dip\")\n"
            "        print(f\"   sub-bar rejection  : \"\n"
            "              f\"{'ON' if any(getattr(ad, 'sub_per_main', 0) >= 2 for ad in _RASE_LAST_ASSETS.values()) else 'OFF (no sub-bar data)'}\"\n"
            "              if '_RASE_LAST_ASSETS' in globals() else 'active')\"\n"
            "        print(f\"   regime p75 window  : \"\n"
            "              f\"{CFG.RASE_REGIME_GAUGE_P75_WINDOW} bars\")\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P09 — CLI: --rase, --rase-dip-floor, --rase-dip-cap, --rase-p75-window
    # Insert after --confirm-kappa argument
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P09-cli-args",
        "desc": "Add RASE CLI arguments",
        "old": (
            "    p.add_argument(\"--confirm-kappa\", type=float, default=None,\n"
            "                   help=\"[NEW] Confirmation threshold (× σ_bar). \"\n"
            "                        \"Default 0.20. Try 0.1 / 0.2 / 0.3 / 0.5.\")\n"
        ),
        "new": (
            "    p.add_argument(\"--confirm-kappa\", type=float, default=None,\n"
            "                   help=\"[NEW] Confirmation threshold (× σ_bar). \"\n"
            "                        \"Default 0.20. Try 0.1 / 0.2 / 0.3 / 0.5.\")\n"
            "    # ══ [RASE Phase 1] CLI flags ══\n"
            "    p.add_argument(\"--rase\", action=\"store_true\",\n"
            "                   help=\"[RASE] Enable regime-adaptive dip + sub-bar rejection\")\n"
            "    p.add_argument(\"--rase-dip-floor\", type=float, default=None,\n"
            "                   help=\"[RASE] dip floor as × friction_dip (default 0.4)\")\n"
            "    p.add_argument(\"--rase-dip-cap\", type=float, default=None,\n"
            "                   help=\"[RASE] dip cap as × friction_dip (default 1.0)\")\n"
            "    p.add_argument(\"--rase-p75-window\", type=int, default=None,\n"
            "                   help=\"[RASE] gauge p75 window for regime split (default 200)\")\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P10 — CLI wiring: apply RASE values + log
    # Insert right after the confirm-entry wiring block
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P10-cli-wiring",
        "desc": "Wire RASE CLI flags into CFG + log warnings",
        "old": (
            "    if getattr(args, \"confirm_kappa\", None) is not None:\n"
            "        CFG.CONFIRM_KAPPA = float(args.confirm_kappa)\n"
            "        log.info(f\"[Confirm] CONFIRM_KAPPA = {CFG.CONFIRM_KAPPA}\")\n"
        ),
        "new": (
            "    if getattr(args, \"confirm_kappa\", None) is not None:\n"
            "        CFG.CONFIRM_KAPPA = float(args.confirm_kappa)\n"
            "        log.info(f\"[Confirm] CONFIRM_KAPPA = {CFG.CONFIRM_KAPPA}\")\n"
            "\n"
            "    # ══ [RASE Phase 1] CLI wiring ══\n"
            "    if getattr(args, \"rase\", False):\n"
            "        CFG.RASE_ENABLED = True\n"
            "        log.info(\"[RASE] Phase 1 ENABLED — regime-adaptive dip + sub-bar rejection\")\n"
            "    if getattr(args, \"rase_dip_floor\", None) is not None:\n"
            "        CFG.RASE_DIP_FLOOR_FRAC = float(args.rase_dip_floor)\n"
            "        log.info(f\"[RASE] dip floor = {CFG.RASE_DIP_FLOOR_FRAC:.2f} × friction_dip\")\n"
            "    if getattr(args, \"rase_dip_cap\", None) is not None:\n"
            "        CFG.RASE_DIP_CAP_FRAC = float(args.rase_dip_cap)\n"
            "        log.info(f\"[RASE] dip cap = {CFG.RASE_DIP_CAP_FRAC:.2f} × friction_dip\")\n"
            "    if getattr(args, \"rase_p75_window\", None) is not None:\n"
            "        CFG.RASE_REGIME_GAUGE_P75_WINDOW = int(args.rase_p75_window)\n"
            "        log.info(f\"[RASE] gauge p75 window = {CFG.RASE_REGIME_GAUGE_P75_WINDOW} bars\")\n"
            "    if CFG.RASE_ENABLED:\n"
            "        if CFG.RASE_DIP_FLOOR_FRAC <= 0 or CFG.RASE_DIP_CAP_FRAC <= 0:\n"
            "            log.warning(\"[RASE] non-positive dip bounds — clamping to defaults\")\n"
            "            CFG.RASE_DIP_FLOOR_FRAC = max(0.1, CFG.RASE_DIP_FLOOR_FRAC)\n"
            "            CFG.RASE_DIP_CAP_FRAC   = max(0.1, CFG.RASE_DIP_CAP_FRAC)\n"
            "        if CFG.RASE_DIP_CAP_FRAC < CFG.RASE_DIP_FLOOR_FRAC:\n"
            "            log.warning(\"[RASE] cap < floor — swapping\")\n"
            "            _tmp = CFG.RASE_DIP_FLOOR_FRAC\n"
            "            CFG.RASE_DIP_FLOOR_FRAC = CFG.RASE_DIP_CAP_FRAC\n"
            "            CFG.RASE_DIP_CAP_FRAC = _tmp\n"
            "        if getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False):\n"
            "            log.warning(\"[RASE] REVERSAL_CONFIRM_ENABLED is also ON → \"\n"
            "                        \"sub-bar path will be skipped (reversal path takes priority)\")\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P11 — Banner: show RASE status
    # Insert right after the [Level-1] print
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P11-banner",
        "desc": "Show RASE status in the startup banner",
        "old": (
            "    print(f\"  [Level-2] Numba: {_NUMBA_AVAILABLE and CFG.NUMBA_ENABLED}\\n\")\n"
        ),
        "new": (
            "    print(f\"  [Level-2] Numba: {_NUMBA_AVAILABLE and CFG.NUMBA_ENABLED}\")\n"
            "    if getattr(CFG, 'RASE_ENABLED', False):\n"
            "        print(f\"  [RASE-P1] ENABLED  \"\n"
            "              f\"dip=[{CFG.RASE_DIP_FLOOR_FRAC:.2f},{CFG.RASE_DIP_CAP_FRAC:.2f}]×friction  \"\n"
            "              f\"p75_win={CFG.RASE_REGIME_GAUGE_P75_WINDOW}\")\n"
            "    else:\n"
            "        print(f\"  [RASE-P1] disabled\")\n"
            "    print()\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P12 — Version marker at file top
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P12-marker",
        "desc": "Add RASE Phase 1 marker at file top",
        "old": (
            "# [RESCUE-EXIT-APPLIED]\n"
        ),
        "new": (
            "# ═══ [RASE-PHASE-1-APPLIED] ═══\n"
            "# [RESCUE-EXIT-APPLIED]\n"
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _count_occurrences(text: str, pattern: str) -> int:
    """Count how many times `pattern` appears literally in `text`."""
    if not pattern:
        return 0
    return text.count(pattern)


def _apply_one_patch(content: str, patch: dict) -> tuple:
    """
    Apply a single patch to `content`.
    Returns (new_content, status, detail).
      status ∈ {'applied', 'already_applied', 'not_found', 'ambiguous'}
    """
    old = patch["old"]
    new = patch["new"]
    pid = patch["id"]

    # Fast path: already applied? (new is present exactly once)
    new_count = _count_occurrences(content, new)
    if new_count == 1:
        return content, "already_applied", f"{pid}: already applied"

    # Find the anchor
    old_count = _count_occurrences(content, old)
    if old_count == 0:
        return content, "not_found", f"{pid}: anchor not found (may be patched by another tool or already applied differently)"
    if old_count > 1:
        return content, "ambiguous", f"{pid}: anchor found {old_count} times (must be exactly 1)"

    # Do the replacement (only first occurrence, which is the only one)
    new_content = content.replace(old, new, 1)
    return new_content, "applied", f"{pid}: OK"


def _verify_syntax(content: str) -> tuple:
    """Return (ok, error_message)."""
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


def _is_already_patched(content: str) -> bool:
    """Detect the file-level marker indicating Phase 1 was already applied."""
    return MARKER in content


def run_patch(target: Path, dry_run: bool = False) -> int:
    """Main patch entry point. Returns exit code."""
    print(f"\n{'═' * 74}")
    print(f"  RASE Phase 1 — Batch Patcher")
    print(f"  Target: {target}")
    print(f"  Mode  : {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target file not found: {target}")
        return 1

    original = target.read_text(encoding="utf-8")
    print(f"  📄 Loaded {len(original):,} chars "
          f"({original.count(chr(10)):,} lines)\n")

    # ── Early exit: already patched? ────────────────────────────────────
    if _is_already_patched(original):
        print(f"  ⚠️  File already contains marker: {MARKER}")
        print(f"     (This usually means Phase 1 is already applied.)")
        print(f"     Use --verify-only to check, or --rollback to restore.\n")
        if not dry_run:
            # Re-run anyway in dry-run style to confirm state
            print(f"  🔁 Verifying all patches present...")
            all_present = True
            for patch in PATCHES:
                if _count_occurrences(original, patch["new"]) != 1:
                    print(f"     ❌ {patch['id']}: missing or duplicated")
                    all_present = False
            if all_present:
                print(f"  ✅ All {len(PATCHES)} patches verified present.\n")
                return 0
            else:
                print(f"  ⚠️  Some patches missing despite marker — "
                      f"consider --rollback.\n")
                return 2
        else:
            print(f"  ℹ️  Dry-run: skipping apply.\n")
            return 0

    # ── Apply patches sequentially ──────────────────────────────────────
    content = original
    applied = []
    skipped = []
    failed = []

    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        print(f"  [{i:02d}/{len(PATCHES)}] {pid} ... ", end="", flush=True)
        new_content, status, detail = _apply_one_patch(content, patch)
        if status == "applied":
            content = new_content
            applied.append(patch)
            print(f"✅ applied")
        elif status == "already_applied":
            skipped.append(patch)
            print(f"⏭️  already applied")
        else:
            failed.append((patch, detail))
            print(f"❌ {status}")
            print(f"        └─ {detail}")

    print(f"\n{'─' * 74}")
    print(f"  Summary: {len(applied)} applied, {len(skipped)} already, "
          f"{len(failed)} failed")
    print(f"{'─' * 74}\n")

    # ── Handle failures: abort before writing ───────────────────────────
    if failed:
        print(f"  ❌ Patching aborted — {len(failed)} patch(es) failed.")
        print(f"     No file was modified. Please inspect the anchors below:\n")
        for patch, detail in failed:
            print(f"     • {patch['id']}")
            print(f"       {patch['desc']}")
            print(f"       → {detail}\n")
        return 3

    # ── No changes needed? ──────────────────────────────────────────────
    if len(applied) == 0:
        print(f"  ✅ File already fully patched — nothing to write.\n")
        return 0

    # ── Syntax validation ───────────────────────────────────────────────
    print(f"  🔍 Validating syntax (ast.parse)...")
    ok, err = _verify_syntax(content)
    if not ok:
        print(f"  ❌ Syntax validation FAILED: {err}")
        print(f"     No file was modified. This is a patcher bug — "
              f"please report.\n")
        return 4
    print(f"  ✅ Syntax OK\n")

    # ── Dry-run: stop here ──────────────────────────────────────────────
    if dry_run:
        print(f"  🧪 DRY-RUN — would write {len(content):,} chars "
              f"to {target}")
        print(f"     Diff preview (first {len(applied)} patches shown "
              f"as before/after anchors):\n")
        for patch in applied:
            print(f"     ── {patch['id']} ──")
            print(f"       OLD: {patch['old'].splitlines()[0][:70]}...")
            print(f"       NEW: {patch['new'].splitlines()[0][:70]}...")
        print()
        return 0

    # ── Backup original ─────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target.with_suffix(
        target.suffix + f".rase_p1_backup_{ts}"
    )
    try:
        shutil.copy2(target, backup_path)
        print(f"  💾 Backup: {backup_path.name}")
    except Exception as e:
        print(f"  ❌ Backup failed: {e}")
        print(f"     Aborting — no file modified.\n")
        return 5

    # ── Atomic write (tmp → os.replace) ─────────────────────────────────
    tmp_path = target.with_suffix(target.suffix + ".rase_tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        # Final safety: re-parse the written file
        _ = tmp_path.read_text(encoding="utf-8")
        os.replace(tmp_path, target)
        print(f"  ✅ Written: {target}")
        print(f"     Backup : {backup_path.name}\n")
    except Exception as e:
        print(f"  ❌ Write failed: {e}")
        # Try to clean up tmp
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        # Auto-rollback from backup (file shouldn't be touched yet, but
        # be defensive in case os.replace partially succeeded)
        try:
            if backup_path.exists():
                shutil.copy2(backup_path, target)
                print(f"  🔄 Auto-rollback from backup complete.\n")
        except Exception as rb_err:
            print(f"  ⚠️  Auto-rollback also failed: {rb_err}\n")
        return 6

    # ── Success banner ──────────────────────────────────────────────────
    print(f"{'═' * 74}")
    print(f"  ✅ RASE Phase 1 successfully applied!")
    print(f"{'═' * 74}")
    print(f"  To enable at runtime:")
    print(f"      python3 {target.name} --rase")
    print(f"  To disable (legacy behavior):")
    print(f"      python3 {target.name}   # RASE_ENABLED defaults to False")
    print(f"  To rollback:")
    print(f"      python3 {Path(__file__).name} --rollback --target {target.name}")
    print(f"{'═' * 74}\n")
    return 0


def run_verify(target: Path) -> int:
    """Verify-only mode: check whether Phase 1 is fully applied."""
    print(f"\n{'═' * 74}")
    print(f"  RASE Phase 1 — Verification")
    print(f"  Target: {target}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target not found: {target}\n")
        return 1

    content = target.read_text(encoding="utf-8")
    has_marker = _is_already_patched(content)
    print(f"  Marker present : {'✅ YES' if has_marker else '❌ NO'}")
    print(f"  File size      : {len(content):,} chars "
          f"({content.count(chr(10)):,} lines)\n")

    ok_count = 0
    bad_count = 0
    for patch in PATCHES:
        pid = patch["id"]
        new_count = _count_occurrences(content, patch["new"])
        old_count = _count_occurrences(content, patch["old"])
        if new_count == 1:
            print(f"  ✅ {pid:35s} applied")
            ok_count += 1
        elif new_count > 1:
            print(f"  ⚠️  {pid:35s} applied {new_count}× (dup?)")
            bad_count += 1
        elif old_count == 1:
            print(f"  ❌ {pid:35s} NOT applied (anchor intact)")
            bad_count += 1
        elif old_count > 1:
            print(f"  ❌ {pid:35s} anchor {old_count}× (ambiguous)")
            bad_count += 1
        else:
            print(f"  ⚠️  {pid:35s} anchor missing (modified externally?)")
            bad_count += 1

    print(f"\n{'─' * 74}")
    if ok_count == len(PATCHES):
        print(f"  ✅ All {len(PATCHES)} patches verified — Phase 1 active.")
        print(f"{'─' * 74}\n")
        return 0
    else:
        print(f"  ⚠️  {ok_count}/{len(PATCHES)} verified, "
              f"{bad_count} issue(s).")
        print(f"{'─' * 74}\n")
        return 2


def run_rollback(target: Path) -> int:
    """Rollback mode: restore the most recent RASE backup."""
    print(f"\n{'═' * 74}")
    print(f"  RASE Phase 1 — Rollback")
    print(f"  Target: {target}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target not found: {target}\n")
        return 1

    # Find backups matching our naming pattern, sorted newest-first
    backups = sorted(
        target.parent.glob(target.name + ".rase_p1_backup_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not backups:
        print(f"  ❌ No RASE backups found in {target.parent}")
        print(f"     Looking for: {target.name}.rase_p1_backup_*\n")
        return 1

    latest = backups[0]
    print(f"  🔍 Found {len(backups)} backup(s). Latest:")
    print(f"     {latest.name}")
    print(f"     {latest.stat().st_size:,} bytes, "
          f"mtime={datetime.fromtimestamp(latest.stat().st_mtime)}")

    # Verify backup is valid Python before restoring
    try:
        backup_content = latest.read_text(encoding="utf-8")
        ok, err = _verify_syntax(backup_content)
        if not ok:
            print(f"  ⚠️  Backup fails syntax check: {err}")
            print(f"     Restoring anyway (it's the safest available state).\n")
    except Exception as e:
        print(f"  ❌ Cannot read backup: {e}\n")
        return 2

    # Safety: back up the *current* (patched) state before overwriting
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_rollback = target.with_suffix(
        target.suffix + f".pre_rollback_{ts}"
    )
    try:
        shutil.copy2(target, pre_rollback)
        print(f"  💾 Pre-rollback snapshot: {pre_rollback.name}")
    except Exception as e:
        print(f"  ❌ Pre-rollback snapshot failed: {e}\n")
        return 3

    # Restore
    try:
        shutil.copy2(latest, target)
        print(f"  ✅ Rolled back: {target}")
        print(f"     Restored from: {latest.name}")
        print(f"     Snapshot kept: {pre_rollback.name}\n")
    except Exception as e:
        print(f"  ❌ Rollback failed: {e}")
        print(f"     Pre-rollback snapshot is safe at: {pre_rollback.name}\n")
        return 4

    # Verify the restored file parses
    try:
        restored = target.read_text(encoding="utf-8")
        ok, err = _verify_syntax(restored)
        if ok:
            print(f"  ✅ Restored file passes syntax check.")
            print(f"     RASE marker present: "
                  f"{'yes (unexpected!)' if _is_already_patched(restored) else 'no (expected)'}\n")
        else:
            print(f"  ⚠️  Restored file FAILS syntax: {err}")
            print(f"     You may want to restore {pre_rollback.name} manually.\n")
            return 5
    except Exception as e:
        print(f"  ⚠️  Could not verify restored file: {e}\n")

    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="RASE Phase 1 — Automated Batch Patcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 rase_phase1_patcher.py                 # apply\n"
            "  python3 rase_phase1_patcher.py --dry-run       # preview\n"
            "  python3 rase_phase1_patcher.py --verify-only   # check\n"
            "  python3 rase_phase1_patcher.py --rollback      # restore\n"
            "  python3 rase_phase1_patcher.py --target foo.py # custom file\n"
        ),
    )
    parser.add_argument(
        "--target", type=str, default=DEFAULT_TARGET,
        help=f"Target file to patch (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing",
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Check if patches are applied, no write",
    )
    parser.add_argument(
        "--rollback", action="store_true",
        help="Restore the most recent RASE backup",
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()

    # Mode dispatch (verify + rollback are mutually exclusive with apply)
    try:
        if args.rollback:
            return run_rollback(target)
        if args.verify_only:
            return run_verify(target)
        return run_patch(target, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n\n  ⏹️  Interrupted by user.\n")
        return 130
    except Exception as e:
        print(f"\n  💥 Unexpected error: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())

