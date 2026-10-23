#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_bee_cancel_parity_patch.py
=================================
Improves BEEsc-Cancel parity between backtest and live + adds optional
S/R intact check. Both features are OPT-IN (default OFF → zero change).

Two orthogonal flags:

    --be-cancel-close-only
        Extreme tracking + bounce use the CLOSED bar's close instead of
        wicks (backtest) or ticker (live). This is the S/R philosophy:
        a level is not broken until a candle closes beyond it.
        Aligns backtest and live for BEEsc-Cancel.

    --be-cancel-sr-check
        Skip BEEsc-Cancel if the nearest swing support (BUY) or
        resistance (SELL) was BROKEN by the last close.
        Prevents cancelling on fake bounces after a real breakout.

Prerequisites: BEEsc-Cancel (BREAKEVEN_ESCAPE_CANCEL_KAPPA) must exist.

Usage:
    python3 apply_bee_cancel_parity_patch.py --dry-run
    python3 apply_bee_cancel_parity_patch.py
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime

DEFAULT_FILE = "trading_2_live4_claude2_v4.py"


# ══════════════════════════════════════════════════════════════
# PATCH 1 — Config: new flags
# ══════════════════════════════════════════════════════════════
P1_OLD = (
    "    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0\n"
)
P1_NEW = (
    "    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0\n"
    "    # ══ [BEEsc-Cancel-Close] Use CLOSE-ONLY tracking (no wick, no ticker)\n"
    "    # When True, extreme tracking + bounce confirmation use the LAST\n"
    "    # CLOSED bar's close. This matches the S/R philosophy (a level is\n"
    "    # not broken until a candle closes beyond it) and eliminates the\n"
    "    # live-vs-backtest ticker/wick gap.\n"
    "    # Default False → preserves current behavior.\n"
    "    BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False\n"
    "    # ══ [BEEsc-Cancel-SR] Require S/R intact before cancelling\n"
    "    # When True, BEEsc-Cancel is skipped if price has BROKEN (by close)\n"
    "    # the nearest swing support (BUY) or resistance (SELL).\n"
    "    # Rationale: an escape is only useful if a real bounce exists.\n"
    "    # Default False → no S/R filter.\n"
    "    BREAKEVEN_ESCAPE_CANCEL_SR_CHECK: bool = False\n"
    "    BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK: int = 60\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 2 — Backtest BEEsc-Cancel block (full replacement)
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
# PATCH 3 — Live BEEsc-Cancel block (full replacement)
# ══════════════════════════════════════════════════════════════
P3_OLD = (
    "                # ══ [BEEsc-Cancel-Live] track extremes + cancel ══\n"
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
)

# ══════════════════════════════════════════════════════════════
# PATCH 4 — CLI arguments
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
    "                        \"extreme tracking + bounce (no wick, no \"\n"
    "                        \"ticker). Matches S/R philosophy.\")\n"
    "    p.add_argument(\"--be-cancel-sr-check\", action=\"store_true\",\n"
    "                   help=\"BEEsc-Cancel skipped if the nearest swing \"\n"
    "                        \"support/resistance was BROKEN by close \"\n"
    "                        \"(prevents fake cancels)\")\n"
)

# ══════════════════════════════════════════════════════════════
# PATCH 5 — CLI wiring
# ══════════════════════════════════════════════════════════════
P5_OLD = (
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
P5_NEW = (
    "    if getattr(args, \"no_be_escape_ema\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP = False\n"
    "        log.warning(\"[BEEsc] EMA-flip requirement DISABLED — \"\n"
    "                    \"HIGHER risk of premature exit\")\n"
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


PATCHES = [
    ("P1_CONFIG", "Add CLOSE_ONLY + SR_CHECK flags", P1_OLD, P1_NEW),
    ("P2_BT",     "Backtest BEEsc-Cancel: close + S/R", P2_OLD, P2_NEW),
    ("P3_LV",     "Live BEEsc-Cancel: close + S/R", P3_OLD, P3_NEW),
    ("P4_ARGS",   "Add CLI flags", P4_OLD, P4_NEW),
    ("P5_WIRE",   "CLI wiring + startup log", P5_OLD, P5_NEW),
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
    if "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY" in src_text:
        raise RuntimeError(
            "Patch already applied (found BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY). "
            "Restore backup first.")
    if "BREAKEVEN_ESCAPE_CANCEL_KAPPA" not in src_text:
        raise RuntimeError(
            "Prerequisite missing: BEEsc-Cancel (BREAKEVEN_ESCAPE_CANCEL_KAPPA) "
            "must be applied first.")

    text = src_text
    applied = []
    for pid, desc, old, new in PATCHES:
        n = _count(text, old)
        if n == 0:
            raise RuntimeError(
                f"[{pid}] anchor NOT FOUND: {desc}\n"
                f"  preview: {old[:200]!r}")
        if n > 1:
            raise RuntimeError(
                f"[{pid}] anchor AMBIGUOUS ({n} matches): {desc}")
        text = text.replace(old, new, 1)
        applied.append((pid, desc))
        print(f"  [OK]   {pid:10s} — {desc}")
    return text, applied


def verify_syntax(text):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"


def main():
    ap = argparse.ArgumentParser(description="Add BEEsc-Cancel parity fixes.")
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

    print("Applying 5 patches...")
    try:
        new_text, applied = apply_patches(src)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print(f"\n{len(applied)}/5 patches applied.\n")

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

    print("=" * 72)
    print("  DONE — BEEsc-Cancel parity patch applied")
    print("=" * 72)
    print()
    print("What it adds (all OPT-IN, zero change when OFF):")
    print()
    print("  --be-cancel-close-only")
    print("    Extreme tracking + bounce use CLOSED bar close.")
    print("    → Backtest: uses closes[cidx] instead of lows/highs")
    print("    → Live:     uses closes[-2] instead of ticker")
    print("    → Aligns backtest↔live AND respects S/R philosophy")
    print("      (level not broken until a candle closes beyond it)")
    print()
    print("  --be-cancel-sr-check")
    print("    Skip BEEsc-Cancel if nearest swing support/resistance")
    print("    was BROKEN by the last close.")
    print("    → Prevents cancelling on fake bounces after breakout")
    print()
    print("Recommended for full parity + S/R respect:")
    print("  --be-cancel-close-only --be-cancel-sr-check")
    print()
    print("Test A/B/C on the backtest:")
    print("  A) Baseline (no flags)  → same results as now")
    print("  B) --be-cancel-close-only")
    print("  C) --be-cancel-close-only --be-cancel-sr-check")
    print()
    print("Verify in log:")
    print("  grep 'BEEsc-Cancel' qtt6.log")
    print("  grep 'mode=close' qtt6.log   (should appear if flag on)")
    print("  grep 'BEEsc-Cancel-SR' qtt6.log   (S/R skips)")


if __name__ == "__main__":
    main()
