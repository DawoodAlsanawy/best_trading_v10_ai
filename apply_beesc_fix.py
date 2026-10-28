#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_beesc_fix.py
==================
Batch patcher for trading_2_live4_claude2_v4.py — applies the FULL BEEsc
intent-fix package (9 modification groups).

Patches applied (in order):
    1  Config: BEEsc fields + new MFE_GUARD_R / CANCEL_USE_HIGH
    2  _should_breakeven_escape  — full replacement (MFE-guard + signal trigger)
    3  _exit_is_taker            — add "BEEsc-breakeven" classification
    4a _advance: BEEsc price trigger  (opp_by_sym_ci + pos=pos)
    4b _advance: BEEsc-cancel BUY     (use high for bounce detection)
    4b _advance: BEEsc-cancel SELL    (use low for bounce detection)
    4c _advance: TP label sub-bar     ("BEEsc-breakeven" vs "Hard TP")
    4c _advance: TP label main-bar
    5  _advance: signature            (add opp_by_sym_ci=None)
    6  simulate_portfolio: build map + update 2 _advance calls
    7a run_live: BEEsc-MIGRATION block (before load_symbol_meta)
    7b run_live: pass pos=pos in price-trigger call
    7c run_live: pass pos=_pos_be in signal-trigger call
    7d run_live: TP label
    7e run_live: add "BEEsc-breakeven" to _urgent
    8  main(): warnings for dangerous --be-escape-* values

Guarantees:
    * Idempotent — safe to run twice
    * Timestamped backup before writing
    * Syntax verified with ast.parse (before + after)
    * Auto-rollback on any syntax failure (nothing written)
    * Preserves UTF-8 (Arabic comments) + line endings
    * Safe with live positions — no open-position is force-closed

Usage:
    python3 apply_beesc_fix.py                     # apply
    python3 apply_beesc_fix.py --check             # verify only
    python3 apply_beesc_fix.py --dry-run           # plan only
    python3 apply_beesc_fix.py --verbose           # show context diffs
    python3 apply_beesc_fix.py --file PATH         # custom target
    python3 apply_beesc_fix.py --no-backup         # skip backup (DANGER)
"""

import argparse
import ast
import os
import re
import shutil
import sys
import time
from pathlib import Path

DEFAULT_TARGET = "trading_2_live4_claude2_v4_micro.py"


# ═══════════════════════════════════════════════════════════════
#  File helpers
# ═══════════════════════════════════════════════════════════════

def _read(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def _syntax_ok(text: str):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def _backup(path: Path) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = path.with_name(f"{path.name}.bak.{ts}")
    shutil.copy2(path, bak)
    return bak


def _find_function_range(text: str, func_name: str):
    m = re.search(rf"^def {re.escape(func_name)}\(", text, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    rest = text[start + 1:]
    nxt = re.search(r"\n(?=def [a-zA-Z_]|class [a-zA-Z_]|# [\u2550=])", rest)
    end = (start + 1 + nxt.start() + 1) if nxt else len(text)
    return (start, end)


# ═══════════════════════════════════════════════════════════════
#  Patch application primitives
# ═══════════════════════════════════════════════════════════════

def _apply_exact(text: str, old: str, new: str, marker: str):
    """Returns (new_text, status)."""
    if marker and marker in text:
        return text, "already_applied"
    if old in text:
        return text.replace(old, new, 1), "applied"
    if new in text:
        return text, "already_applied"
    return text, "ANCHOR_NOT_FOUND"


def _apply_function(text: str, func: str, new_body: str, marker: str):
    """Function-level replacement (start to next def/class/top-comment)."""
    rng = _find_function_range(text, func)
    if rng is None:
        return text, "FUNCTION_NOT_FOUND"
    s, e = rng
    current = text[s:e]
    if marker and marker in current:
        return text, "already_applied"
    return text[:s] + new_body.rstrip() + "\n\n" + text[e:], "applied"


# ═══════════════════════════════════════════════════════════════
#  Patch text payloads
# ═══════════════════════════════════════════════════════════════

# ── 1. Config block ────────────────────────────────────────────

CONFIG_OLD = """    BREAKEVEN_ESCAPE_ENABLED: bool = False
    BREAKEVEN_ESCAPE_PRICE_MOVE_R: float = 0.30
    BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP: bool = True
    BREAKEVEN_ESCAPE_EMA_LOOKBACK: int = 50
    BREAKEVEN_ESCAPE_SIGNAL_ENABLED: bool = False
    BREAKEVEN_ESCAPE_SIGNAL_MAX_AGE_BARS: int = 6
    BREAKEVEN_ESCAPE_SIGNAL_SCORE_MULT: float = 1.15
    BREAKEVEN_ESCAPE_MIN_PROFIT_R: float = 0.0
    BREAKEVEN_ESCAPE_RESPECT_PARTIAL: bool = False
    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0
    BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False
    BREAKEVEN_ESCAPE_CANCEL_SR_CHECK: bool = False
    BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK: int = 60
"""

CONFIG_NEW = """    # \u2550\u2550 [BREAKEVEN ESCAPE] reversal-confirmed exit at entry \u00b1 small_gain \u2550\u2550
    # [BEEsc-INTENT-FIX] \u0645\u0637\u0627\u0628\u0642 \u0644\u0646\u064a\u0629 \u0627\u0644\u0645\u0627\u0644\u0643:
    #   \u2022 \u064a\u0639\u0645\u0644 \u0641\u0642\u0637 \u0639\u0644\u0649 \u0627\u0644\u0635\u0641\u0642\u0627\u062a \u0627\u0644\u062e\u0627\u0633\u0631\u0629 \u0627\u0644\u062a\u064a \u0644\u0645 \u062a\u0643\u0646 \u0631\u0627\u0628\u062d\u0629 \u0633\u0627\u0628\u0642\u0627\u064b (MFE guard)
    #   \u2022 \u064a\u064f\u0637\u0644\u0642 \u0641\u0642\u0637 \u0639\u0646\u062f \u0627\u0646\u0639\u0643\u0627\u0633 \u0645\u0624\u0643\u062f (\u0625\u0634\u0627\u0631\u0629 \u0645\u0639\u0627\u0643\u0633\u0629 \u0623\u0648 \u0647\u0628\u0648\u0637 \u0639\u0645\u064a\u0642 0.80R)
    #   \u2022 \u064a\u062e\u0631\u062c \u0628\u0647\u0627\u0645\u0634 \u0635\u063a\u064a\u0631 \u0645\u0648\u062c\u0628 \u064a\u063a\u0637\u064a \u0627\u0644\u0631\u0633\u0648\u0645 (+0.15R)
    #   \u2022 BEEsc-Cancel \u064a\u0633\u062a\u062e\u062f\u0645 high \u0644\u0627 close \u0644\u0643\u0634\u0641 \u0627\u0644\u0627\u0631\u062a\u062f\u0627\u062f \u0627\u0644\u062d\u0642\u064a\u0642\u064a
    BREAKEVEN_ESCAPE_ENABLED: bool = False
    BREAKEVEN_ESCAPE_PRICE_MOVE_R: float = 0.80      # \u0643\u0627\u0646 0.30
    BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP: bool = True
    BREAKEVEN_ESCAPE_EMA_LOOKBACK: int = 50
    BREAKEVEN_ESCAPE_SIGNAL_ENABLED: bool = True     # \u0643\u0627\u0646 False
    BREAKEVEN_ESCAPE_SIGNAL_MAX_AGE_BARS: int = 6
    BREAKEVEN_ESCAPE_SIGNAL_SCORE_MULT: float = 1.15
    BREAKEVEN_ESCAPE_MIN_PROFIT_R: float = 0.15      # \u0643\u0627\u0646 0.0
    BREAKEVEN_ESCAPE_RESPECT_PARTIAL: bool = False
    BREAKEVEN_ESCAPE_CANCEL_KAPPA: float = 0.0
    BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False
    BREAKEVEN_ESCAPE_CANCEL_SR_CHECK: bool = False
    BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK: int = 60
    # \u2550\u2550 [BEEsc-INTENT-FIX] \u2014 NEW FIELDS \u2550\u2550
    # \u0644\u0627 \u062a\u064f\u0637\u0644\u0642 BEEsc \u0625\u0630\u0627 \u0648\u0635\u0644\u062a \u0627\u0644\u0635\u0641\u0642\u0629 \u0625\u0644\u0649 \u0631\u0628\u062d \u2265 \u0647\u0630\u0627 \u0627\u0644\u062d\u062f (\u0628\u0648\u062d\u062f\u0627\u062a R).
    # \u0647\u0630\u0627 \u064a\u062d\u0645\u064a "\u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0631\u0628\u062d" \u2014 \u062d\u0645\u0627\u064a\u0627\u062a\u0647\u0627 \u0627\u0644\u062e\u0627\u0635\u0629 (Partial/Trail/TP) \u062a\u062a\u0648\u0644\u0627\u0647\u0627.
    BREAKEVEN_ESCAPE_MFE_GUARD_R: float = 0.50
    # \u0627\u0633\u062a\u062e\u062f\u0645 high \u0644\u0644\u0643\u0634\u0641 \u0639\u0646 \u0627\u0644\u0627\u0631\u062a\u062f\u0627\u062f (\u0623\u062f\u0642 \u0645\u0646 close\u060c \u064a\u0645\u0646\u0639 \u0625\u0644\u063a\u0627\u0621 cancel \u0627\u0644\u0648\u0647\u0645\u064a)
    BREAKEVEN_ESCAPE_CANCEL_USE_HIGH: bool = True
    # \u0645\u0647\u0644\u0629 \u0645\u0633\u0645\u0648\u062d\u0629 \u0628\u064a\u0646 \u0625\u063a\u0644\u0627\u0642 \u0635\u0641\u0642\u0629 \u0648\u0625\u0639\u0627\u062f\u0629 \u0641\u062a\u062d\u0647\u0627 \u0641\u064a \u0646\u0641\u0633 \u0627\u0644\u0631\u0645\u0632 \u062f\u0627\u062e\u0644 BEEsc-Cancel
    BREAKEVEN_ESCAPE_CANCEL_MIN_BOUNCE_SIGMA: float = 1.0
"""


# ── 2. _should_breakeven_escape ────────────────────────────────

FUNC_SHOULD_BE_NEW = '''def _should_breakeven_escape(ad, current_ci: int, current_price: float,
                              action: str, entry: float,
                              sl_dist0: float,
                              sig_opp=None, pos=None,
                              mfe_override=None):
    """
    BEEsc trigger \u2014 \u0645\u0637\u0627\u0628\u0642 \u0644\u0646\u064a\u0629 \u0627\u0644\u0645\u0627\u0644\u0643:
      \u2022 LOSS-ONLY (\u0644\u0627 \u064a\u0644\u0645\u0633 \u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0631\u0628\u062d)
      \u2022 MFE-GUARD (\u0644\u0627 \u064a\u064f\u0637\u0644\u0642 \u0639\u0644\u0649 \u0635\u0641\u0642\u0627\u062a \u0643\u0627\u0646\u062a \u0631\u0627\u0628\u062d\u0629 \u0633\u0627\u0628\u0642\u0627\u064b)
      \u2022 reversal-confirmed (\u0625\u0634\u0627\u0631\u0629 \u0645\u0639\u0627\u0643\u0633\u0629 \u0642\u0648\u064a\u0629 \u0623\u0648 \u0647\u0628\u0648\u0637 0.80R)
      \u2022 small positive gain \u0639\u0646\u062f \u0627\u0644\u062e\u0631\u0648\u062c
    """
    if not getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False):
        return False, "disabled"
    if entry <= 0 or sl_dist0 <= 0 or current_price <= 0:
        return False, "invalid"

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # [LOSS-ONLY-GUARD] \u2014 \u0644\u0627 \u064a\u0639\u0645\u0644 \u0641\u064a \u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0631\u0628\u062d
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    if action == "BUY" and current_price >= entry:
        _pnl_pct = (current_price - entry) / entry * 100.0
        return False, f"in_profit({_pnl_pct:+.2f}%)"
    if action == "SELL" and current_price <= entry:
        _pnl_pct = (entry - current_price) / entry * 100.0
        return False, f"in_profit({_pnl_pct:+.2f}%)"

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # [MFE-GUARD] \u2014 \u0644\u0627 \u064a\u064f\u0637\u0644\u0642 \u0625\u0630\u0627 \u0643\u0627\u0646\u062a \u0627\u0644\u0635\u0641\u0642\u0629 \u0631\u0627\u0628\u062d\u0629 \u0633\u0627\u0628\u0642\u0627\u064b
    # \u064a\u062f\u0639\u0645 \u0643\u0644\u0627\u064b \u0645\u0646 OpenPosition (backtest) \u0648 pos dict (live)
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    _guard_r = float(getattr(CFG, 'BREAKEVEN_ESCAPE_MFE_GUARD_R', 0.50))
    if _guard_r > 0:
        _mfe_r = None
        try:
            if mfe_override is not None:
                _mfe_r = float(mfe_override)
            elif pos is not None and isinstance(pos, dict):
                _hi = float(pos.get('_hi', entry) or entry)
                _lo = float(pos.get('_lo', entry) or entry)
                if action == "BUY":
                    _mfe_r = (_hi - entry) / sl_dist0
                else:
                    _mfe_r = (entry - _lo) / sl_dist0
            elif pos is not None:
                _mfe_frac = float(getattr(pos, 'mfe_frac', 0.0))
                _mfe_r = (_mfe_frac * entry) / sl_dist0 if entry > 0 else 0.0
        except Exception:
            _mfe_r = None
        if _mfe_r is not None and _mfe_r > _guard_r:
            return False, f"was_profitable(mfe={_mfe_r:.2f}R>{_guard_r:.2f}R)"

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # TRIGGER 1 \u2014 PRICE: \u0647\u0628\u0648\u0637 \u0639\u0645\u064a\u0642 (0.80R \u0627\u0641\u062a\u0631\u0627\u0636\u064a\u0627\u064b)
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    price_trig = False
    price_reason = ""
    _min_move = float(getattr(
        CFG, 'BREAKEVEN_ESCAPE_PRICE_MOVE_R', 0.80)) * sl_dist0

    if action == "BUY":
        _adverse = entry - current_price
    else:
        _adverse = current_price - entry

    if _adverse >= _min_move:
        if getattr(CFG, 'BREAKEVEN_ESCAPE_REQUIRE_EMA_FLIP', True):
            _lb = int(getattr(CFG, 'BREAKEVEN_ESCAPE_EMA_LOOKBACK', 50))
            if _ema_slope_against(ad, current_ci, action, _lb):
                price_trig = True
                price_reason = f"price+EMA(adv={_adverse/sl_dist0:.2f}R)"
        else:
            price_trig = True
            price_reason = f"price_only(adv={_adverse/sl_dist0:.2f}R)"

    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # TRIGGER 2 \u2014 SIGNAL: \u0625\u0634\u0627\u0631\u0629 \u0645\u0639\u0627\u0643\u0633\u0629 \u0642\u0648\u064a\u0629 \u062d\u062f\u064a\u062b\u0629
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    sig_trig = False
    sig_reason = ""
    if (getattr(CFG, 'BREAKEVEN_ESCAPE_SIGNAL_ENABLED', True)
            and sig_opp is not None):
        if sig_opp.action != action:
            _age = current_ci - int(getattr(sig_opp, 'close_idx', current_ci))
            _max_age = int(getattr(
                CFG, 'BREAKEVEN_ESCAPE_SIGNAL_MAX_AGE_BARS', 6))
            if 0 <= _age <= _max_age:
                try:
                    _sc_o = float(getattr(sig_opp, 'score', 0.0) or 0.0)
                    _sc_orig = 0.0
                    if pos is not None:
                        if isinstance(pos, dict):
                            _sc_orig = float(pos.get('_orig_score', 0.0) or 0.0)
                        else:
                            _sc_orig = float(getattr(
                                getattr(pos, 'signal', None), 'score', 0.0) or 0.0)
                    _mult = float(getattr(
                        CFG, 'BREAKEVEN_ESCAPE_SIGNAL_SCORE_MULT', 1.15))
                    if _sc_o > 0 and (_sc_orig <= 0 or _sc_o >= _sc_orig * _mult):
                        sig_trig = True
                        sig_reason = f"opp_signal(age={_age},score={_sc_o:.2f})"
                except Exception:
                    pass

    if price_trig or sig_trig:
        _reasons = [r for r in (price_reason, sig_reason) if r]
        return True, "|".join(_reasons)
    return False, "not_triggered"
'''


# ── 3. _exit_is_taker ──────────────────────────────────────────

FUNC_EXIT_TAKER_NEW = '''def _exit_is_taker(exit_rsn: str) -> bool:
    """
    Classify the exit reason as taker (crosses the book) or maker.
    Matches Live's classification in run_live().
    [BEEsc-FIX] "BEEsc-breakeven" \u062a\u062e\u0631\u062c \u0639\u0646\u062f entry \u2192 \u062a\u0639\u0628\u0631 \u0627\u0644\u0633\u0628\u0631\u064a\u062f \u2192 taker
    """
    r = str(exit_rsn or "")
    _apex_urgent = bool(getattr(CFG, 'PO_EXIT_APEX_URGENT', True))
    _apex_match = _apex_urgent and (("Apex" in r) or ("Topo-Div" in r))
    if (("Emergency" in r) or ("Hard TP" in r)
            or ("BEEsc-breakeven" in r)
            or ("LiqProximity" in r) or _apex_match):
        return True
    return False
'''


# ── 4a. BEEsc price trigger in _advance ────────────────────────

BEESC_PRICE_OLD = """        # \u2550\u2550 [BREAKEVEN ESCAPE \u2014 Price Trigger] \u2550\u2550
        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                and not getattr(pos, '_be_esc_done', False)
                and not getattr(pos, '_signal_sl_above_beesc', False)
                and pos.sl_dist_initial > 0):
            _be_trig, _be_rsn = _should_breakeven_escape(
                ad, cidx, float(p), sig.action,
                pos.entry_px, pos.sl_dist_initial, sig_opp=None
            )
"""

BEESC_PRICE_NEW = """        # \u2550\u2550 [BEEsc-FIX] Price Trigger \u2014 \u064a\u062c\u0645\u0639 sig_opp \u0645\u0646 \u0646\u0641\u0633 \u0627\u0644\u0634\u0645\u0639\u0629 \u2550\u2550
        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                and not getattr(pos, '_be_esc_done', False)
                and not getattr(pos, '_signal_sl_above_beesc', False)
                and pos.sl_dist_initial > 0):
            _sig_opp_here = None
            if (getattr(CFG, 'BREAKEVEN_ESCAPE_SIGNAL_ENABLED', True)
                    and opp_by_sym_ci is not None):
                try:
                    for _c_opp in opp_by_sym_ci.get((sig.symbol, cidx), []):
                        if _c_opp.action != sig.action:
                            _sig_opp_here = _c_opp
                            break
                except Exception:
                    pass
            _be_trig, _be_rsn = _should_breakeven_escape(
                ad, cidx, float(p), sig.action,
                pos.entry_px, pos.sl_dist_initial,
                sig_opp=_sig_opp_here,
                pos=pos,
            )
"""


# ── 4b-1. BEEsc-cancel BUY branch ──────────────────────────────

CANCEL_BUY_OLD = """                if _be_sr_ok:
                    _sigma_c = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
                    if not np.isfinite(_sigma_c) or _sigma_c <= 1e-9:
                        _sigma_c = 0.01
                    _kappa_c = float(CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA)
                    _thr_c = _kappa_c * _sigma_c * pos.entry_px
                    if sig.action == "BUY":
                        _low_src = (float(ad.closes[cidx]) if _be_use_close
                                    else float(ad.lows[cidx]))
                        _low_c = min(
                            float(getattr(pos, '_be_low', pos.entry_px)),
                            _low_src,
                        )
                        pos._be_low = _low_c
                        _bounce_c = float(p) - _low_c
"""

CANCEL_BUY_NEW = """                if _be_sr_ok:
                    _sigma_c = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
                    if not np.isfinite(_sigma_c) or _sigma_c <= 1e-9:
                        _sigma_c = 0.01
                    _kappa_c = float(CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA)
                    _thr_c = _kappa_c * _sigma_c * pos.entry_px
                    # [BEEsc-Cancel-USE-HIGH] \u0645\u0635\u062f\u0631 \u0627\u0644\u0627\u0631\u062a\u062f\u0627\u062f
                    _use_high_for_bounce = bool(getattr(
                        CFG, 'BREAKEVEN_ESCAPE_CANCEL_USE_HIGH', True))
                    if sig.action == "BUY":
                        _low_src = (float(ad.closes[cidx]) if _be_use_close
                                    else float(ad.lows[cidx]))
                        _low_c = min(
                            float(getattr(pos, '_be_low', pos.entry_px)),
                            _low_src,
                        )
                        pos._be_low = _low_c
                        # \u0645\u0635\u062f\u0631 \u0627\u0644\u0627\u0631\u062a\u062f\u0627\u062f: high \u0628\u062f\u0644 close (\u0643\u0634\u0641 \u0623\u062f\u0642)
                        if _be_use_close:
                            _bounce_src = float(ad.closes[cidx])
                        elif _use_high_for_bounce:
                            _bounce_src = float(ad.highs[cidx])
                        else:
                            _bounce_src = float(p)
                        _bounce_c = _bounce_src - _low_c
"""


# ── 4b-2. BEEsc-cancel SELL branch ─────────────────────────────

CANCEL_SELL_OLD = """                    else:
                        _high_src = (float(ad.closes[cidx]) if _be_use_close
                                     else float(ad.highs[cidx]))
                        _high_c = max(
                            float(getattr(pos, '_be_high', pos.entry_px)),
                            _high_src,
                        )
                        pos._be_high = _high_c
                        _bounce_c = _high_c - float(p)
"""

CANCEL_SELL_NEW = """                    else:
                        _high_src = (float(ad.closes[cidx]) if _be_use_close
                                     else float(ad.highs[cidx]))
                        _high_c = max(
                            float(getattr(pos, '_be_high', pos.entry_px)),
                            _high_src,
                        )
                        pos._be_high = _high_c
                        # [BEEsc-Cancel-USE-HIGH] \u0645\u0635\u062f\u0631 \u0627\u0644\u0627\u0631\u062a\u062f\u0627\u062f \u0644\u0644\u0640 SELL
                        if _be_use_close:
                            _bounce_src = float(ad.closes[cidx])
                        elif _use_high_for_bounce:
                            _bounce_src = float(ad.lows[cidx])
                        else:
                            _bounce_src = float(p)
                        _bounce_c = _high_c - _bounce_src
"""


# ── 4c-sub. TP label (sub-bar mode) ────────────────────────────

TP_LABEL_SUB_OLD = """                if res == "TP":
                    pos.trail_sl = trail_sl; pos.current_ci = cidx
                    return px, "Hard TP", cidx
"""

TP_LABEL_SUB_NEW = """                if res == "TP":
                    pos.trail_sl = trail_sl; pos.current_ci = cidx
                    # [BEEsc-LABEL] \u0645\u064a\u0651\u0632 \u0627\u0644\u062e\u0631\u0648\u062c \u0639\u0646\u062f entry (BEEsc) \u0639\u0646 TP \u0627\u0644\u0623\u0635\u0644\u064a
                    _tp_label = ("BEEsc-breakeven"
                                 if getattr(pos, '_be_esc_done', False)
                                 else "Hard TP")
                    return px, _tp_label, cidx
"""


# ── 4c-main. TP label (main-bar mode) ──────────────────────────

TP_LABEL_MAIN_OLD = """            if res == "TP":
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return px, "Hard TP", cidx
"""

TP_LABEL_MAIN_NEW = """            if res == "TP":
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                _tp_label = ("BEEsc-breakeven"
                             if getattr(pos, '_be_esc_done', False)
                             else "Hard TP")
                return px, _tp_label, cidx
"""


# ── 5. _advance signature ──────────────────────────────────────

ADVANCE_SIG_OLD = "def _advance(pos, ad, to_ci, partial_cb=None):\n"
ADVANCE_SIG_NEW = "def _advance(pos, ad, to_ci, partial_cb=None, opp_by_sym_ci=None):\n"


# ── 6-map. Build opp_by_sym_ci in simulate_portfolio ──────────

OPP_MAP_OLD = """    # \u2550\u2550 [FIX 4] Partial TP callback \u2550\u2550
    def _partial_tp(pos, px, ci):
"""

OPP_MAP_NEW = """    # \u2550\u2550 [BEEsc-FIX] \u062e\u0631\u064a\u0637\u0629 \u0625\u0634\u0627\u0631\u0627\u062a \u0645\u0639\u0627\u0643\u0633\u0629 \u0644\u0643\u0644 (\u0631\u0645\u0632\u060c ci) \u2550\u2550
    _opp_by_sym_ci = defaultdict(list)
    for _s in signals:
        try:
            _opp_by_sym_ci[(_s.symbol, int(_s.close_idx))].append(_s)
        except Exception:
            pass

    # \u2550\u2550 [FIX 4] Partial TP callback \u2550\u2550
    def _partial_tp(pos, px, ci):
"""


# ── 6-call1. _advance call (main loop) ────────────────────────

ADV_CALL1_OLD = """            ep, er, ec = _advance(pos, ad, toci, partial_cb=_partial_tp)
"""

ADV_CALL1_NEW = """            ep, er, ec = _advance(pos, ad, toci, partial_cb=_partial_tp,
                                   opp_by_sym_ci=_opp_by_sym_ci)
"""


# ── 6-call2. _advance call (end-of-data) ──────────────────────

ADV_CALL2_OLD = """        _advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp)
"""

ADV_CALL2_NEW = """        _advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp,
                 opp_by_sym_ci=_opp_by_sym_ci)
"""


# ── 7a. Migration block in run_live ───────────────────────────

MIGRATION_ANCHOR = """    # \u2550\u2550 [State] Load persistent symbol metadata (leverage/margin/setup) \u2550\u2550
    load_symbol_meta(cfg.mode)
"""

MIGRATION_BLOCK = """    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    # [BEEsc-MIGRATION] \u062a\u0631\u062d\u064a\u0644 \u0622\u0645\u0646 \u0644\u0644\u0635\u0641\u0642\u0627\u062a \u0627\u0644\u0642\u062f\u064a\u0645\u0629 \u0627\u0644\u062a\u064a \u0623\u064f\u063a\u0644\u0642\u062a BEEsc \u062e\u0627\u0637\u0626.
    # \u064a\u0639\u064a\u062f TP \u0627\u0644\u0623\u0635\u0644\u064a \u0641\u0642\u0637 \u0625\u0630\u0627:
    #   1. MFE > guard (\u0643\u0627\u0646\u062a \u0631\u0627\u0628\u062d\u0629 \u0633\u0627\u0628\u0642\u0627\u064b)
    #   2. \u0627\u0644\u0633\u0639\u0631 \u0627\u0644\u062d\u0627\u0644\u064a \u0644\u0645 \u064a\u0635\u0644 \u0625\u0644\u0649 TP \u0627\u0644\u0623\u0635\u0644\u064a \u0628\u0639\u062f (\u0622\u0645\u0646)
    # \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
    _besc_migrated = 0
    for _sym_mig, _pos_mig in list(open_pos_live.items()):
        if not _pos_mig.get('_be_esc_done', False):
            continue
        _orig_tp = _pos_mig.get('_be_orig_tp1')
        if _orig_tp is None or float(_orig_tp) <= 0:
            continue
        _entry_mig = float(_pos_mig.get('entry', 0) or 0)
        _sd0_mig = float(_pos_mig.get('sl_dist_initial', 0) or 0)
        if _entry_mig <= 0 or _sd0_mig <= 0:
            continue
        _hi_mig = float(_pos_mig.get('_hi', _entry_mig) or _entry_mig)
        _lo_mig = float(_pos_mig.get('_lo', _entry_mig) or _entry_mig)
        if _pos_mig.get('action') == 'BUY':
            _mfe_r_mig = (_hi_mig - _entry_mig) / _sd0_mig
        else:
            _mfe_r_mig = (_entry_mig - _lo_mig) / _sd0_mig
        _guard_mig = float(getattr(CFG, 'BREAKEVEN_ESCAPE_MFE_GUARD_R', 0.50))
        if _mfe_r_mig <= _guard_mig:
            continue
        try:
            _tk_mig = exchange.fetch_ticker(_sym_mig)
            _p_mig = float(_tk_mig.get('last') or 0)
        except Exception:
            _p_mig = 0.0
        if _p_mig <= 0:
            log.debug(f"[BEEsc-Migration] {_sym_mig} skipped (no price)")
            continue
        if (_pos_mig.get('action') == 'BUY' and _p_mig >= float(_orig_tp)):
            log.info(f"[BEEsc-Migration] {_sym_mig} skipped "
                     f"(price {_p_mig:.6f} >= orig TP {_orig_tp:.6f})")
            continue
        if (_pos_mig.get('action') == 'SELL' and _p_mig <= float(_orig_tp)):
            log.info(f"[BEEsc-Migration] {_sym_mig} skipped "
                     f"(price {_p_mig:.6f} <= orig TP {_orig_tp:.6f})")
            continue
        _old_tp_mig = _pos_mig.get('tp1')
        _pos_mig['tp1'] = float(_orig_tp)
        _pos_mig['_be_esc_done'] = False
        _pos_mig.pop('_be_orig_tp1', None)
        _besc_migrated += 1
        log.info(
            f"[BEEsc-Migration] {_sym_mig} {_pos_mig.get('action')} "
            f"TP {_old_tp_mig} -> {_orig_tp} "
            f"(MFE={_mfe_r_mig:.2f}R>{_guard_mig}R, price={_p_mig:.6f})"
        )
        try:
            if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
                _sync_protective_orders(exchange, _sym_mig, _pos_mig)
        except Exception as _e:
            log.warning(f"[BEEsc-Migration] {_sym_mig} sync: {_e}")
    if _besc_migrated > 0:
        log.info(f"[BEEsc-Migration] Migrated {_besc_migrated} positions")
        try:
            _lv_save_state(state_file, open_pos_live)
        except Exception:
            pass

""" + MIGRATION_ANCHOR


# ── 7b. run_live BEEsc price-trigger call ─────────────────────

LIVE_BE_PRICE_OLD = """                    _be_trig, _be_rsn = _should_breakeven_escape(
                        ad, _ci_now_be, _be_price,
                        pos['action'], float(pos['entry']),
                        _sl_d0_be, sig_opp=None,
                    )
"""

LIVE_BE_PRICE_NEW = """                    _be_trig, _be_rsn = _should_breakeven_escape(
                        ad, _ci_now_be, _be_price,
                        pos['action'], float(pos['entry']),
                        _sl_d0_be, sig_opp=None,
                        pos=pos,   # \u2190 \u064a\u064f\u0645\u0643\u0651\u0646 MFE-guard \u0645\u0646 _hi/_lo
                    )
"""


# ── 7c. run_live BEEsc signal-trigger call ────────────────────

LIVE_BE_SIG_OLD = """                        _be_trig, _be_rsn = _should_breakeven_escape(
                            _ad_be, _ci_be, _p_be,
                            _pos_be['action'], float(_pos_be['entry']),
                            _sl_d0_be, sig_opp=_sig_be,
                        )
"""

LIVE_BE_SIG_NEW = """                        _be_trig, _be_rsn = _should_breakeven_escape(
                            _ad_be, _ci_be, _p_be,
                            _pos_be['action'], float(_pos_be['entry']),
                            _sl_d0_be, sig_opp=_sig_be,
                            pos=_pos_be,   # \u2190 MFE-guard
                        )
"""


# ── 7d. run_live TP label ─────────────────────────────────────

LIVE_TP_LABEL_OLD = """                if not ex:
                    if pos['action'] == "BUY":
                        if price <= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price >= pos.get('tp1', 1e18): ex = True; rsn = "Hard TP"
                    else:
                        if price >= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price <= pos.get('tp1', 0.): ex = True; rsn = "Hard TP"
"""

LIVE_TP_LABEL_NEW = """                if not ex:
                    # [BEEsc-LABEL] \u0627\u0644\u062a\u0645\u064a\u064a\u0632 \u0628\u064a\u0646 BEEsc-exit \u0648 TP \u0627\u0644\u0623\u0635\u0644\u064a
                    _tp_label_lv = ("BEEsc-breakeven"
                                    if pos.get('_be_esc_done')
                                    else "Hard TP")
                    if pos['action'] == "BUY":
                        if price <= pos['sl']:
                            ex = True; rsn = "Emergency SL"
                        elif price >= pos.get('tp1', 1e18):
                            ex = True; rsn = _tp_label_lv
                    else:
                        if price >= pos['sl']:
                            ex = True; rsn = "Emergency SL"
                        elif price <= pos.get('tp1', 0.):
                            ex = True; rsn = _tp_label_lv
"""


# ── 7e. run_live _urgent ──────────────────────────────────────

LIVE_URGENT_OLD = """                    _urgent = (
                        'Emergency' in rsn
                        or 'Hard TP' in rsn
                        or 'LiqProximity' in rsn
                        or (_apex_urgent_lv and (
                            ('Apex' in rsn) or ('Topo-Div' in rsn)))
                    )
"""

LIVE_URGENT_NEW = """                    _urgent = (
                        'Emergency' in rsn
                        or 'Hard TP' in rsn
                        or 'BEEsc-breakeven' in rsn   # \u2190 NEW
                        or 'LiqProximity' in rsn
                        or (_apex_urgent_lv and (
                            ('Apex' in rsn) or ('Topo-Div' in rsn)))
                    )
"""


# ── 8. main() warnings ────────────────────────────────────────

WARN_OLD = """    if getattr(args, "be_escape_move_r", None) is not None:
        CFG.BREAKEVEN_ESCAPE_PRICE_MOVE_R = float(args.be_escape_move_r)
    if getattr(args, "be_escape_min_profit_r", None) is not None:
        CFG.BREAKEVEN_ESCAPE_MIN_PROFIT_R = float(
            args.be_escape_min_profit_r)
"""

WARN_NEW = """    if getattr(args, "be_escape_move_r", None) is not None:
        CFG.BREAKEVEN_ESCAPE_PRICE_MOVE_R = float(args.be_escape_move_r)
    if getattr(args, "be_escape_min_profit_r", None) is not None:
        CFG.BREAKEVEN_ESCAPE_MIN_PROFIT_R = float(
            args.be_escape_min_profit_r)

    # \u2550\u2550 [BEEsc-WARN] \u062a\u062d\u0630\u064a\u0631\u0627\u062a \u0636\u062f \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u062e\u0637\u0631\u0629 \u2550\u2550
    if getattr(args, "be_escape_move_r", None) is not None:
        _v = float(args.be_escape_move_r)
        if _v < 0.60:
            log.warning(
                f"[BEEsc] \u26a0\ufe0f  --be-escape-move-r={_v} < 0.60 \u0642\u062f \u064a\u064f\u0637\u0644\u0642 BEEsc "
                f"\u0639\u0644\u0649 \u062a\u0630\u0628\u0630\u0628 \u0639\u0627\u062f\u064a \u0648\u064a\u0642\u062a\u0644 \u0635\u0641\u0642\u0627\u062a \u0631\u0627\u0628\u062d\u0629. \u0627\u0644\u0645\u0648\u0635\u0649 \u0628\u0647: 0.80"
            )
    if getattr(args, "be_escape_min_profit_r", None) is not None:
        _v = float(args.be_escape_min_profit_r)
        if _v < 0.10:
            log.warning(
                f"[BEEsc] \u26a0\ufe0f  --be-escape-min-profit-r={_v} < 0.10 "
                f"\u064a\u062c\u0639\u0644 BEEsc-exit \u0633\u0627\u0644\u0628\u0627\u064b \u0635\u0627\u0641\u064a\u0627\u064b (\u0631\u0633\u0648\u0645 > \u0631\u0628\u062d). \u0627\u0644\u0645\u0648\u0635\u0649 \u0628\u0647: 0.15+"
            )
"""


# ═══════════════════════════════════════════════════════════════
#  Patch list
# ═══════════════════════════════════════════════════════════════

PATCHES = [
    {"name": "1.  Config: BEEsc fields + MFE guard",
     "kind": "exact", "old": CONFIG_OLD, "new": CONFIG_NEW,
     "marker": "BREAKEVEN_ESCAPE_MFE_GUARD_R: float = 0.50"},

    {"name": "2.  _should_breakeven_escape (full)",
     "kind": "function", "func": "_should_breakeven_escape",
     "new": FUNC_SHOULD_BE_NEW,
     "marker": "was_profitable(mfe="},

    {"name": "3.  _exit_is_taker (full)",
     "kind": "function", "func": "_exit_is_taker",
     "new": FUNC_EXIT_TAKER_NEW,
     "marker": '"BEEsc-breakeven" in r'},

    {"name": "4a. _advance: BEEsc price trigger",
     "kind": "exact", "old": BEESC_PRICE_OLD, "new": BEESC_PRICE_NEW,
     "marker": "_sig_opp_here"},

    {"name": "4b1 _advance: BEEsc-cancel BUY",
     "kind": "exact", "old": CANCEL_BUY_OLD, "new": CANCEL_BUY_NEW,
     "marker": "_use_high_for_bounce"},

    {"name": "4b2 _advance: BEEsc-cancel SELL",
     "kind": "exact", "old": CANCEL_SELL_OLD, "new": CANCEL_SELL_NEW,
     "marker": "_bounce_c = _high_c - _bounce_src"},

    {"name": "4c1 _advance: TP label (sub-bar)",
     "kind": "exact", "old": TP_LABEL_SUB_OLD, "new": TP_LABEL_SUB_NEW,
     "marker": "_tp_label = (\"BEEsc-breakeven\"\n                                 if"},

    {"name": "4c2 _advance: TP label (main-bar)",
     "kind": "exact", "old": TP_LABEL_MAIN_OLD, "new": TP_LABEL_MAIN_NEW,
     "marker": "_tp_label = (\"BEEsc-breakeven\"\n                             if"},

    {"name": "5.  _advance: signature",
     "kind": "exact", "old": ADVANCE_SIG_OLD, "new": ADVANCE_SIG_NEW,
     "marker": "def _advance(pos, ad, to_ci, partial_cb=None, opp_by_sym_ci=None):"},

    {"name": "6a. simulate_portfolio: build map",
     "kind": "exact", "old": OPP_MAP_OLD, "new": OPP_MAP_NEW,
     "marker": "_opp_by_sym_ci = defaultdict(list)"},

    {"name": "6b. simulate_portfolio: call #1",
     "kind": "exact", "old": ADV_CALL1_OLD, "new": ADV_CALL1_NEW,
     "marker": "opp_by_sym_ci=_opp_by_sym_ci)"},

    {"name": "6c. simulate_portfolio: call #2",
     "kind": "exact", "old": ADV_CALL2_OLD, "new": ADV_CALL2_NEW,
     "marker": "_advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp,\n                 opp_by_sym_ci=_opp_by_sym_ci)"},

    {"name": "7a. run_live: BEEsc-MIGRATION block",
     "kind": "exact", "old": MIGRATION_ANCHOR, "new": MIGRATION_BLOCK,
     "marker": "[BEEsc-MIGRATION]"},

    {"name": "7b. run_live: BEEsc price call",
     "kind": "exact", "old": LIVE_BE_PRICE_OLD, "new": LIVE_BE_PRICE_NEW,
     "marker": "pos=pos,   # \u2190 \u064a\u064f\u0645\u0643\u0651\u0646 MFE-guard"},

    {"name": "7c. run_live: BEEsc signal call",
     "kind": "exact", "old": LIVE_BE_SIG_OLD, "new": LIVE_BE_SIG_NEW,
     "marker": "pos=_pos_be,   # \u2190 MFE-guard"},

    {"name": "7d. run_live: TP label",
     "kind": "exact", "old": LIVE_TP_LABEL_OLD, "new": LIVE_TP_LABEL_NEW,
     "marker": "_tp_label_lv"},

    {"name": "7e. run_live: _urgent",
     "kind": "exact", "old": LIVE_URGENT_OLD, "new": LIVE_URGENT_NEW,
     "marker": "'BEEsc-breakeven' in rsn   # \u2190 NEW"},

    {"name": "8.  main(): warnings",
     "kind": "exact", "old": WARN_OLD, "new": WARN_NEW,
     "marker": "[BEEsc-WARN]"},
]


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Apply BEEsc intent-fix patch package."
    )
    ap.add_argument("--file", default=DEFAULT_TARGET,
                    help=f"Target file (default: {DEFAULT_TARGET})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show plan only; do not write")
    ap.add_argument("--check", action="store_true",
                    help="Verify state only; never write")
    ap.add_argument("--no-backup", action="store_true",
                    help="Skip backup (NOT recommended)")
    ap.add_argument("--verbose", action="store_true",
                    help="Print anchor preview on failure")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        return 2

    print(f"[*] Target: {path}")
    print(f"[*] Size  : {path.stat().st_size:,} bytes")

    original = _read(path)
    ok, err = _syntax_ok(original)
    if not ok:
        print(f"[ERROR] File has syntax errors BEFORE patching: {err}",
              file=sys.stderr)
        return 3
    print("[OK] Original syntax verified.\n")

    text = original
    results = []
    for p in PATCHES:
        if p["kind"] == "exact":
            text, status = _apply_exact(text, p["old"], p["new"], p["marker"])
        elif p["kind"] == "function":
            text, status = _apply_function(
                text, p["func"], p["new"], p["marker"])
        else:
            status = f"UNKNOWN_KIND:{p['kind']}"

        results.append((p["name"], status))
        icon = {"applied": "\u2705",
                "already_applied": "\u23ed\ufe0f",
                "ANCHOR_NOT_FOUND": "\u274c",
                "FUNCTION_NOT_FOUND": "\u274c"}.get(status, "\u26a0\ufe0f")
        print(f"  {icon} {p['name']:44s} [{status}]")
        if status.endswith("NOT_FOUND") and args.verbose:
            print(f"      ANCHOR preview:")
            old = p.get("old", p.get("func", ""))
            for line in old.splitlines()[:3]:
                print(f"        | {line}")

    failed = [r for r in results if "NOT_FOUND" in r[1]]
    if failed:
        print(f"\n[ERROR] {len(failed)} patch(es) failed — nothing written.",
              file=sys.stderr)
        for name, st in failed:
            print(f"    \u2022 {name}: {st}", file=sys.stderr)
        print("\n[INFO] The file may have been edited manually since the "
              "previous patch. Use --verbose to preview the expected anchor,\n"
              "       then patch the affected block by hand or adjust the "
              "anchor in this script.", file=sys.stderr)
        return 4

    if text == original:
        print("\n[OK] No changes needed — file already fully patched.")
        return 0

    ok, err = _syntax_ok(text)
    if not ok:
        print(f"\n[ERROR] Patched file fails syntax check: {err}",
              file=sys.stderr)
        print("[INFO] Nothing written; original file untouched.",
              file=sys.stderr)
        return 5
    print("\n[OK] Patched syntax verified.")

    if args.check:
        print("[CHECK] All checks passed; write skipped (--check).")
        return 0

    if args.dry_run:
        print(f"[DRY-RUN] Would write {len(text.encode('utf-8')):,} bytes "
              f"(delta: {len(text.encode('utf-8')) - len(original.encode('utf-8')):+,} bytes)")
        return 0

    if not args.no_backup:
        try:
            bak = _backup(path)
            print(f"[OK] Backup saved: {bak}")
        except Exception as e:
            print(f"[WARN] Backup failed: {e}", file=sys.stderr)
            return 6

    try:
        _write(path, text)
    except Exception as e:
        print(f"[ERROR] Write failed: {e}", file=sys.stderr)
        return 7

    print(f"[OK] Wrote {len(text.encode('utf-8')):,} bytes to {path}")
    n_applied = sum(1 for _, s in results if s == "applied")
    n_skipped = sum(1 for _, s in results if s == "already_applied")
    print(f"\n\u2550\u2550\u2550 Summary \u2550\u2550\u2550")
    print(f"  {n_applied} applied, {n_skipped} skipped (already applied)")
    print("\nNext steps:")
    print("  1. Verify: python3 apply_beesc_fix.py --check")
    print("  2. Syntax: python3 -c \"import ast; "
          "ast.parse(open('%s').read())\"" % path.name)
    print("  3. Run  : python3 %s --be-escape "
          "--be-escape-move-r 0.80 --be-escape-min-profit-r 0.15 "
          "(drop --no-be-escape-ema)" % path.name)
    print("  4. Watch: grep -E 'BEEsc-breakeven|Hard TP' "
          "trades_log_backtest.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
