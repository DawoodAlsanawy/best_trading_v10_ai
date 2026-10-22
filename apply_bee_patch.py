#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_bee_patch.py
==================
Batch patcher — adds the BREAKEVEN-ESCAPE feature to
trading_2_live4_claude2_v4.py. Works for BOTH backtest and live.

Feature:
    When an open position is confirmed reversed (price moved
    ≥ N×SL against us AND EMA-200 flipped, OR a fresh opposite
    signal appeared), the TP is moved to entry ± small_gain.
    Bounces exit flat; SLs still fire normally. Zero extra risk.

Usage:
    python3 apply_bee_patch.py                  # patch in place
    python3 apply_bee_patch.py --dry-run        # verify only
    python3 apply_bee_patch.py --output out.py  # write elsewhere
    python3 apply_bee_patch.py --file src.py    # custom source

Exit codes:
    0 = success
    1 = error
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime


DEFAULT_FILE = "trading_2_live4_claude2_v4.py"


# ══════════════════════════════════════════════════════════════
# PATCH DEFINITIONS  (id, description, old_anchor, new_text)
# Each old_anchor must appear EXACTLY ONCE in the source.
# ══════════════════════════════════════════════════════════════

# ─── PATCH 1 — Config fields ────────────────────────────────────
P1_OLD = (
    "    BREAKEVEN_ENABLED: bool = True\n"
    "    BREAKEVEN_AT_R: float = 1.0\n"
)
P1_NEW = (
    "    BREAKEVEN_ENABLED: bool = True\n"
    "    BREAKEVEN_AT_R: float = 1.0\n"
    "\n"
    "    # ══ [BREAKEVEN ESCAPE] reversal-confirmed exit at entry ══\n"
    "    # When the market is confirmed reversed against our position,\n"
    "    # the TP is moved to entry ± small_gain. Bounces exit flat\n"
    "    # instead of a full SL loss. Zero additional risk.\n"
    "    BREAKEVEN_ESCAPE_ENABLED: bool = True\n"
    "    BREAKEVEN_ESCAPE_PRICE_MOVE_R: float = 0.30\n"
    "    BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP: bool = True\n"
    "    BREAKEVEN_ESCAPE_EMA_LOOKBACK: int = 50\n"
    "    BREAKEVEN_ESCAPE_SIGNAL_ENABLED: bool = True\n"
    "    BREAKEVEN_ESCAPE_SIGNAL_MAX_AGE_BARS: int = 6\n"
    "    BREAKEVEN_ESCAPE_SIGNAL_SCORE_MULT: float = 1.15\n"
    "    BREAKEVEN_ESCAPE_MIN_PROFIT_R: float = 0.0\n"
    "    BREAKEVEN_ESCAPE_RESPECT_PARTIAL: bool = True\n"
)

# ─── PATCH 2 — Helper functions (inserted after _check_confirmation) ─
P2_OLD = (
    "    thr = float(cfg.CONFIRM_KAPPA) * sigma_bar * close_sig\n"
    "\n"
    "    if sig.action == \"BUY\":\n"
    "        ok = delta > thr\n"
    "    else:\n"
    "        ok = -delta > thr\n"
    "\n"
    "    if not ok:\n"
    "        return False, 0.0, -1\n"
    "    return True, close_cf, cf_ci\n"
)
P2_NEW = P2_OLD + '''
# ═══════════════════════════════════════════════════════════════
# [BREAKEVEN ESCAPE] — reversal-confirmed exit at entry price
# ═══════════════════════════════════════════════════════════════


def _ema_slope_against(ad, current_ci: int, action: str,
                        lookback: int = 50) -> bool:
    """True if EMA200 slope is against the position direction."""
    try:
        if ad is None or ad.ema200 is None:
            return False
        n = len(ad.ema200)
        if current_ci < lookback or current_ci >= n:
            return False
        ema_now  = float(ad.ema200[current_ci])
        ema_prev = float(ad.ema200[current_ci - lookback])
        slope = ema_now - ema_prev
        if action == "BUY"  and slope < 0:
            return True
        if action == "SELL" and slope > 0:
            return True
    except Exception:
        pass
    return False


def _should_breakeven_escape(ad, current_ci: int, current_price: float,
                              action: str, entry: float,
                              sl_dist0: float,
                              sig_opp=None):
    """
    Unified trigger detector for breakeven-escape.
    Triggers:
      1) Price: adverse move >= PRICE_MOVE_R × SL, AND (optionally)
         EMA200 slope is against the position.
      2) Signal: fresh opposite signal on the same symbol.
    Returns (triggered, reason_string).
    """
    if not getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False):
        return False, "disabled"
    if entry <= 0 or sl_dist0 <= 0 or current_price <= 0:
        return False, "invalid"

    # Trigger 1: price-based
    price_trig = False
    price_reason = ""
    _min_move = float(getattr(
        CFG, 'BREAKEVEN_ESCAPE_PRICE_MOVE_R', 0.30)) * sl_dist0
    if action == "BUY":
        _adverse = entry - current_price
    else:
        _adverse = current_price - entry
    if _adverse >= _min_move:
        if getattr(CFG, 'BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP', True):
            _lb = int(getattr(CFG, 'BREAKEVEN_ESCAPE_EMA_LOOKBACK', 50))
            if _ema_slope_against(ad, current_ci, action, _lb):
                price_trig = True
                price_reason = f"price+EMA(adv={_adverse / sl_dist0:.2f}R)"
        else:
            price_trig = True
            price_reason = f"price_only(adv={_adverse / sl_dist0:.2f}R)"

    # Trigger 2: signal-based
    sig_trig = False
    sig_reason = ""
    if (getattr(CFG, 'BREAKEVEN_ESCAPE_SIGNAL_ENABLED', True)
            and sig_opp is not None):
        if sig_opp.action != action:
            _age = current_ci - int(getattr(
                sig_opp, 'close_idx', current_ci))
            _max_age = int(getattr(
                CFG, 'BREAKEVEN_ESCAPE_SIGNAL_MAX_AGE_BARS', 6))
            if 0 <= _age <= _max_age:
                try:
                    _sc_o = float(getattr(sig_opp, 'score', 0.0) or 0.0)
                    if _sc_o > 0:
                        sig_trig = True
                        sig_reason = f"opp_signal(age={_age},score={_sc_o:.2f})"
                except Exception:
                    pass

    if price_trig or sig_trig:
        _reasons = [r for r in (price_reason, sig_reason) if r]
        return True, "|".join(_reasons)
    return False, "not_triggered"


def _apply_breakeven_escape(action: str, entry: float, sl_dist0: float,
                              tp_old: float, partial_taken: bool):
    """
    Compute the new TP (entry ± small gain) and validate it.
    Returns new_tp (float) or None (no change).
    """
    if entry <= 0 or sl_dist0 <= 0 or tp_old <= 0:
        return None
    _min_gain = float(getattr(
        CFG, 'BREAKEVEN_ESCAPE_MIN_PROFIT_R', 0.0)) * sl_dist0

    if action == "BUY":
        tp_new = entry + _min_gain
        if tp_new >= tp_old:
            return None
        if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                and not partial_taken
                and getattr(CFG,
                    'BREAKEVEN_ESCAPE_RESPECT_PARTIAL', True)):
            _p_trig = entry + float(CFG.PARTIAL_TP_R) * sl_dist0
            if tp_new <= _p_trig:
                return None
    else:
        tp_new = entry - _min_gain
        if tp_new <= tp_old:
            return None
        if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                and not partial_taken
                and getattr(CFG,
                    'BREAKEVEN_ESCAPE_RESPECT_PARTIAL', True)):
            _p_trig = entry - float(CFG.PARTIAL_TP_R) * sl_dist0
            if tp_new >= _p_trig:
                return None
    return float(tp_new)

# ═══════════════════════════════════════════════════════════════

'''

# ─── PATCH 3 — Backtest: price trigger inside _advance ──────────
P3_OLD = (
    "    for cidx in range(start, end+1):\n"
    "        p = ad.closes[cidx]\n"
    "        fi = cidx - ad.feat_start\n"
    "\n"
    "        # ── Determine sub-bar iteration range for this bar ──\n"
)
P3_NEW = (
    "    for cidx in range(start, end+1):\n"
    "        p = ad.closes[cidx]\n"
    "        fi = cidx - ad.feat_start\n"
    "\n"
    "        # ══ [BREAKEVEN ESCAPE — Price Trigger] ══\n"
    "        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)\n"
    "                and not getattr(pos, '_be_esc_done', False)\n"
    "                and pos.sl_dist_initial > 0):\n"
    "            _be_trig, _be_rsn = _should_breakeven_escape(\n"
    "                ad, cidx, float(p), sig.action,\n"
    "                pos.entry_px, pos.sl_dist_initial, sig_opp=None\n"
    "            )\n"
    "            if _be_trig:\n"
    "                _tp_new_be = _apply_breakeven_escape(\n"
    "                    sig.action, pos.entry_px, pos.sl_dist_initial,\n"
    "                    float(sig.tp1),\n"
    "                    bool(getattr(pos, 'partial_taken', False))\n"
    "                )\n"
    "                if _tp_new_be is not None:\n"
    "                    _tp_old_be = float(sig.tp1)\n"
    "                    sig.tp1 = _tp_new_be\n"
    "                    pos._be_esc_done = True\n"
    "                    log.info(\n"
    "                        f\"[BEEsc-BT] {sig.symbol} {sig.action} \"\n"
    "                        f\"TP {_tp_old_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                        f\"({_be_rsn})\"\n"
    "                    )\n"
    "\n"
    "        # ── Determine sub-bar iteration range for this bar ──\n"
)

# ─── PATCH 4 — Backtest: signal trigger in simulate_portfolio ───
P4_OLD = (
    "            _maybe_adapt_tp_backtest(\n"
    "                open_pos[sig.symbol], sig, assets[sig.symbol],\n"
    "                int(sig.close_idx)\n"
    "            )\n"
    "\n"
    "        sym = sig.symbol\n"
)
P4_NEW = (
    "            _maybe_adapt_tp_backtest(\n"
    "                open_pos[sig.symbol], sig, assets[sig.symbol],\n"
    "                int(sig.close_idx)\n"
    "            )\n"
    "\n"
    "        # ══ [BREAKEVEN ESCAPE — Signal Trigger] ══\n"
    "        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)\n"
    "                and sig.symbol in open_pos):\n"
    "            _be_pos = open_pos[sig.symbol]\n"
    "            if (not getattr(_be_pos, '_be_esc_done', False)\n"
    "                    and _be_pos.signal.action != sig.action\n"
    "                    and _be_pos.sl_dist_initial > 0):\n"
    "                _be_ad = assets.get(sig.symbol)\n"
    "                _be_ci = int(sig.close_idx)\n"
    "                _be_px = (float(_be_ad.closes[_be_ci])\n"
    "                          if _be_ad is not None\n"
    "                          and 0 <= _be_ci < len(_be_ad.closes)\n"
    "                          else float(sig.price))\n"
    "                _be_trig, _be_rsn = _should_breakeven_escape(\n"
    "                    _be_ad, _be_ci, _be_px,\n"
    "                    _be_pos.signal.action,\n"
    "                    _be_pos.entry_px, _be_pos.sl_dist_initial,\n"
    "                    sig_opp=sig,\n"
    "                )\n"
    "                if _be_trig:\n"
    "                    _tp_new_be = _apply_breakeven_escape(\n"
    "                        _be_pos.signal.action, _be_pos.entry_px,\n"
    "                        _be_pos.sl_dist_initial,\n"
    "                        float(_be_pos.signal.tp1),\n"
    "                        bool(getattr(_be_pos, 'partial_taken', False))\n"
    "                    )\n"
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
    "\n"
    "        sym = sig.symbol\n"
)

# ─── PATCH 5 — Live: price trigger in run_live position loop ────
P5_OLD = (
    "                if _lv_manage_position(exchange, sym, pos, price, ad, state_file,\n"
    "                                       open_pos_live, last_exit_time) == 'closed':\n"
    "                    continue\n"
    "\n"
    "                ex = False\n"
    "                rsn = \"\"\n"
)
P5_NEW = (
    "                if _lv_manage_position(exchange, sym, pos, price, ad, state_file,\n"
    "                                       open_pos_live, last_exit_time) == 'closed':\n"
    "                    continue\n"
    "\n"
    "                # ══ [BREAKEVEN ESCAPE — Price Trigger — Live] ══\n"
    "                if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)\n"
    "                        and not pos.get('_be_esc_done', False)\n"
    "                        and float(pos.get('sl_dist_initial', 0)) > 0):\n"
    "                    _sl_d0_be = float(pos['sl_dist_initial'])\n"
    "                    _ci_now_be = (max(0, len(ad.closes) - 2)\n"
    "                                  if ad is not None else 0)\n"
    "                    _be_trig, _be_rsn = _should_breakeven_escape(\n"
    "                        ad, _ci_now_be, float(price),\n"
    "                        pos['action'], float(pos['entry']),\n"
    "                        _sl_d0_be, sig_opp=None,\n"
    "                    )\n"
    "                    if _be_trig:\n"
    "                        _tp_new_be = _apply_breakeven_escape(\n"
    "                            pos['action'], float(pos['entry']), _sl_d0_be,\n"
    "                            float(pos['tp1']),\n"
    "                            bool(pos.get('_partial_taken', False))\n"
    "                        )\n"
    "                        if _tp_new_be is not None:\n"
    "                            _old_tp_be = float(pos['tp1'])\n"
    "                            pos['tp1'] = _tp_new_be\n"
    "                            pos['_be_esc_done'] = True\n"
    "                            log.info(\n"
    "                                f\"[BEEsc-LV] {sym} {pos['action']} \"\n"
    "                                f\"TP {_old_tp_be:.6f} → {_tp_new_be:.6f} \"\n"
    "                                f\"({_be_rsn})\"\n"
    "                            )\n"
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

# ─── PATCH 6 — Live: signal trigger (next to OppTP block) ──────
P6_OLD = (
    "                        _maybe_adapt_tp_live(_pos_o, _sig_o, _ad_o, exchange)\n"
    "\n"
    "                for sig in reversed(sigs):\n"
)
P6_NEW = (
    "                        _maybe_adapt_tp_live(_pos_o, _sig_o, _ad_o, exchange)\n"
    "\n"
    "                # ══ [BREAKEVEN ESCAPE — Signal Trigger — Live] ══\n"
    "                if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)\n"
    "                        and open_pos_live):\n"
    "                    for _sig_be in sigs:\n"
    "                        if _sig_be.symbol not in open_pos_live:\n"
    "                            continue\n"
    "                        _pos_be = open_pos_live[_sig_be.symbol]\n"
    "                        if _pos_be.get('action') == _sig_be.action:\n"
    "                            continue\n"
    "                        if _pos_be.get('_be_esc_done'):\n"
    "                            continue\n"
    "                        _sl_d0_be = float(_pos_be.get('sl_dist_initial', 0))\n"
    "                        if _sl_d0_be <= 0:\n"
    "                            continue\n"
    "                        _ad_be = assets.get(_sig_be.symbol)\n"
    "                        _ci_be = (max(0, len(_ad_be.closes) - 2)\n"
    "                                  if _ad_be is not None\n"
    "                                  else int(_sig_be.close_idx))\n"
    "                        _p_be = (float(_ad_be.closes[_ci_be])\n"
    "                                 if _ad_be is not None\n"
    "                                 and 0 <= _ci_be < len(_ad_be.closes)\n"
    "                                 else float(_sig_be.price))\n"
    "                        _be_trig, _be_rsn = _should_breakeven_escape(\n"
    "                            _ad_be, _ci_be, _p_be,\n"
    "                            _pos_be['action'], float(_pos_be['entry']),\n"
    "                            _sl_d0_be, sig_opp=_sig_be,\n"
    "                        )\n"
    "                        if _be_trig:\n"
    "                            _tp_new_be = _apply_breakeven_escape(\n"
    "                                _pos_be['action'], float(_pos_be['entry']),\n"
    "                                _sl_d0_be, float(_pos_be['tp1']),\n"
    "                                bool(_pos_be.get('_partial_taken', False))\n"
    "                            )\n"
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
    "                                try:\n"
    "                                    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):\n"
    "                                        _sync_protective_orders(\n"
    "                                            exchange, _sig_be.symbol, _pos_be)\n"
    "                                except Exception:\n"
    "                                    pass\n"
    "                                try:\n"
    "                                    _lv_save_state(state_file, open_pos_live)\n"
    "                                except Exception:\n"
    "                                    pass\n"
    "\n"
    "                for sig in reversed(sigs):\n"
)

# ─── PATCH 7 — CLI argparse flags ──────────────────────────────
P7_OLD = (
    "    p.add_argument(\"--no-breakeven\", action=\"store_true\",\n"
    "                   help=\"Disable Breakeven SL\")\n"
)
P7_NEW = (
    "    p.add_argument(\"--no-breakeven\", action=\"store_true\",\n"
    "                   help=\"Disable Breakeven SL\")\n"
    "    # ══ [BREAKEVEN ESCAPE] ══\n"
    "    p.add_argument(\"--be-escape\", action=\"store_true\",\n"
    "                   help=\"Force-enable breakeven-escape (reversal-\"\n"
    "                        \"confirmed exit at entry price)\")\n"
    "    p.add_argument(\"--no-be-escape\", action=\"store_true\",\n"
    "                   help=\"Disable breakeven-escape\")\n"
    "    p.add_argument(\"--be-escape-move-r\", type=float, default=None,\n"
    "                   help=\"Adverse move in R units to trigger escape \"\n"
    "                        \"(default 0.30)\")\n"
    "    p.add_argument(\"--be-escape-min-profit-r\", type=float, default=None,\n"
    "                   help=\"Small profit at exit in R units (default 0.0 \"\n"
    "                        \"= pure breakeven)\")\n"
    "    p.add_argument(\"--be-escape-ema-lookback\", type=int, default=None,\n"
    "                   help=\"EMA-200 slope lookback for confirmation \"\n"
    "                        \"(default 50)\")\n"
    "    p.add_argument(\"--no-be-escape-ema\", action=\"store_true\",\n"
    "                   help=\"Disable EMA-flip requirement (pure price as \"\n"
    "                        \"trigger — RISKIER)\")\n"
)

# ─── PATCH 8 — CLI wiring in main() ────────────────────────────
P8_OLD = (
    "    if args.sell_min_atr_frac is not None:\n"
    "        CFG.SELL_MIN_ATR_FRAC = float(args.sell_min_atr_frac)\n"
    "\n"
    "    # ══ [OppTP] Opposite-Signal Adaptive TP ══\n"
)
P8_NEW = (
    "    if args.sell_min_atr_frac is not None:\n"
    "        CFG.SELL_MIN_ATR_FRAC = float(args.sell_min_atr_frac)\n"
    "\n"
    "    # ══ [BREAKEVEN ESCAPE] ══\n"
    "    if getattr(args, \"no_be_escape\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_ENABLED = False\n"
    "        log.info(\"[BEEsc] DISABLED via --no-be-escape\")\n"
    "    elif getattr(args, \"be_escape\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_ENABLED = True\n"
    "        log.info(\"[BEEsc] ENABLED via --be-escape\")\n"
    "    if getattr(args, \"be_escape_move_r\", None) is not None:\n"
    "        CFG.BREAKEVEN_ESCAPE_PRICE_MOVE_R = float(args.be_escape_move_r)\n"
    "    if getattr(args, \"be_escape_min_profit_r\", None) is not None:\n"
    "        CFG.BREAKEVEN_ESCAPE_MIN_PROFIT_R = float(\n"
    "            args.be_escape_min_profit_r)\n"
    "    if getattr(args, \"be_escape_ema_lookback\", None) is not None:\n"
    "        CFG.BREAKEVEN_ESCAPE_EMA_LOOKBACK = int(\n"
    "            args.be_escape_ema_lookback)\n"
    "    if getattr(args, \"no_be_escape_ema\", False):\n"
    "        CFG.BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP = False\n"
    "        log.warning(\"[BEEsc] EMA-flip requirement DISABLED — \"\n"
    "                    \"HIGHER risk of premature exit\")\n"
    "    if CFG.BREAKEVEN_ESCAPE_ENABLED:\n"
    "        log.info(\n"
    "            f\"[BEEsc] ENABLED | move_R=\"\n"
    "            f\"{CFG.BREAKEVEN_ESCAPE_PRICE_MOVE_R} \"\n"
    "            f\"min_profit_R={CFG.BREAKEVEN_ESCAPE_MIN_PROFIT_R} \"\n"
    "            f\"require_ema={CFG.BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP} \"\n"
    "            f\"ema_lookback={CFG.BREAKEVEN_ESCAPE_EMA_LOOKBACK}\"\n"
    "        )\n"
    "\n"
    "    # ══ [OppTP] Opposite-Signal Adaptive TP ══\n"
)


PATCHES = [
    ("P1_CONFIG",   "Add BREAKEVEN_ESCAPE config fields",     P1_OLD, P1_NEW),
    ("P2_HELPERS",  "Insert _should_breakeven_escape helper",  P2_OLD, P2_NEW),
    ("P3_BT_PRICE", "Backtest _advance price trigger",         P3_OLD, P3_NEW),
    ("P4_BT_SIG",   "Backtest signal-trigger in simulate",     P4_OLD, P4_NEW),
    ("P5_LV_PRICE", "Live price trigger in run_live",          P5_OLD, P5_NEW),
    ("P6_LV_SIG",   "Live signal trigger (near OppTP)",        P6_OLD, P6_NEW),
    ("P7_ARGS",     "Add CLI argparse arguments",              P7_OLD, P7_NEW),
    ("P8_WIRE",     "CLI wiring in main()",                    P8_OLD, P8_NEW),
]


# ══════════════════════════════════════════════════════════════
# Patcher core
# ══════════════════════════════════════════════════════════════

def _count(haystack, needle):
    """Count non-overlapping occurrences of needle."""
    c = 0
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return c
        c += 1
        start = idx + len(needle)


def apply_patches(src_text):
    """Apply all patches. Returns (new_text, applied_list). Raises on error."""
    # Idempotency guard
    if "def _should_breakeven_escape" in src_text:
        raise RuntimeError(
            "Patch already applied (found 'def _should_breakeven_escape'). "
            "Restore from a backup before re-applying.")

    text = src_text
    applied = []
    for pid, desc, old, new in PATCHES:
        n_old = _count(text, old)
        if n_old == 0:
            raise RuntimeError(
                f"[{pid}] anchor NOT FOUND: {desc}\n"
                f"  anchor preview (first 150 chars):\n"
                f"  {old[:150]!r}\n"
                f"  File may be from a different version."
            )
        if n_old > 1:
            raise RuntimeError(
                f"[{pid}] anchor AMBIGUOUS ({n_old} matches): {desc}\n"
                f"  anchor preview:\n  {old[:150]!r}"
            )
        text = text.replace(old, new, 1)
        applied.append((pid, desc))
        print(f"  [OK]   {pid:12s} — {desc}")
    return text, applied


def verify_syntax(text):
    """Return (ok, err_msg) by parsing with ast."""
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Apply BREAKEVEN-ESCAPE patch to the trading bot.")
    ap.add_argument("--file", default=DEFAULT_FILE,
                    help=f"Source file (default: {DEFAULT_FILE})")
    ap.add_argument("--output", default=None,
                    help="Output file (default: patch in place)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Verify patches only; don't write anything")
    ap.add_argument("--no-backup", action="store_true",
                    help="Skip .bak backup of the source file")
    args = ap.parse_args()

    src_path = args.file
    if not os.path.exists(src_path):
        print(f"ERROR: source file not found: {src_path}")
        sys.exit(1)

    print(f"Reading {src_path}...")
    with open(src_path, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"  size: {len(src):,} bytes\n")

    print("Applying 8 patches...")
    try:
        new_text, applied = apply_patches(src)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print(f"\n{len(applied)}/8 patches applied successfully.\n")

    print("Verifying syntax...")
    ok, err = verify_syntax(new_text)
    if not ok:
        print(f"  FAIL: {err}")
        print("  No files were written. The original is untouched.")
        sys.exit(1)
    print("  OK: ast.parse passed.\n")

    if args.dry_run:
        print("[Dry-run] No files written. Exiting.")
        sys.exit(0)

    # Backup
    if args.output is None and not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{src_path}.bak.{ts}"
        shutil.copy2(src_path, backup)
        print(f"Backup saved: {backup}")

    # Write
    out_path = args.output or src_path
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"Wrote: {out_path}  ({len(new_text):,} bytes)\n")

    # Summary
    print("=" * 66)
    print("  DONE — BREAKEVEN ESCAPE patched successfully")
    print("=" * 66)
    print()
    print("What it does:")
    print("  • Price trigger : when price moves ≥ 0.30R against us AND")
    print("                    EMA-200 slope confirms reversal → TP→entry")
    print("  • Signal trigger: when a fresh opposite signal fires → TP→entry")
    print("  • Zero extra risk: SLs stay put; bounces exit flat, deeper")
    print("    drops still exit at SL exactly as before.")
    print()
    print("Enabled by default in BOTH backtest and live.")
    print()
    print("New CLI flags:")
    print("  --be-escape                 force-enable")
    print("  --no-be-escape              disable")
    print("  --be-escape-move-r 0.30     adverse move threshold (R units)")
    print("  --be-escape-min-profit-r 0.0  pure breakeven (default)")
    print("  --be-escape-ema-lookback 50 EMA-200 slope window")
    print("  --no-be-escape-ema          price-only trigger (riskier)")
    print()
    print("Add to your existing command:")
    print("  --be-escape --be-escape-move-r 0.30")
    sys.exit(0)


if __name__ == "__main__":
    main()
