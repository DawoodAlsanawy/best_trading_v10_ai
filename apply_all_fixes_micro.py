#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_all_fixes_micro.py
========================
Comprehensive batch patcher for trading_2_live4_claude2_v4_micro_pro.py

Applies ALL previously-issued fixes in ONE pass:

  ┌─ BEEsc intent-fix (18 modifications)
  │    Config:  PRICE_MOVE_R 0.30→0.80, SIGNAL_ENABLED → True,
  │             MIN_PROFIT_R → 0.15, +3 new fields
  │    Func:    _should_breakeven_escape (MFE-guard + signal trigger)
  │             _exit_is_taker (BEEsc-breakeven classification)
  │    _advance:  price-trigger (opp_by_sym_ci), cancel BUY/SELL (high),
  │               TP label (sub + main), signature (opp_by_sym_ci param)
  │    _simulate_portfolio: build map + update 2 _advance calls
  │    _run_live: BEEsc-MIGRATION block, price call, signal call,
  │              TP label, _urgent, warnings
  └─ OppTP Profit-Guard (6 modifications)
       Config: + OPP_TP_REQUIRE_PROFIT = True
       Func:   _opp_tp_decide + current_price + guard
               _maybe_adapt_tp_backtest: + current_price
               _maybe_adapt_tp_live:     + current_price
       CLI:    --opp-tp-allow-loss
       Wiring: flag → CFG.OPP_TP_REQUIRE_PROFIT

Guarantees:
  * Idempotent         — safe to run twice
  * Timestamped backup — written before any change
  * Syntax verified    — before AND after each stage
  * Nothing written    — if any patch fails
  * Auto-rollback      — on syntax failure after patching
  * UTF-8 preserved    — Arabic comments intact
  * Live-safe          — no open-position is force-closed

Usage:
    python3 apply_all_fixes_micro.py                  # apply
    python3 apply_all_fixes_micro.py --check          # verify only
    python3 apply_all_fixes_micro.py --dry-run        # plan only
    python3 apply_all_fixes_micro.py --verbose        # context on failure
    python3 apply_all_fixes_micro.py --no-backup      # skip backup (DANGER)
    python3 apply_all_fixes_micro.py --file PATH      # custom target
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
#  I/O + integrity
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
    """Locate a top-level `def func_name(` ... up to next def/class/section."""
    m = re.search(rf"^def {re.escape(func_name)}\(", text, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    rest = text[start + 1:]
    nxt = re.search(r"\n(?=def [A-Za-z_]|class [A-Za-z_]|# [\u2550=])", rest)
    end = (start + 1 + nxt.start() + 1) if nxt else len(text)
    return (start, end)


# ═══════════════════════════════════════════════════════════════
#  Patch primitives
# ═══════════════════════════════════════════════════════════════

def _apply_exact(text, old, new, marker):
    if marker and marker in text:
        return text, "already_applied"
    if old in text:
        return text.replace(old, new, 1), "applied"
    return text, "ANCHOR_NOT_FOUND"


def _apply_function(text, func, new_body, marker):
    rng = _find_function_range(text, func)
    if rng is None:
        return text, "FUNCTION_NOT_FOUND"
    s, e = rng
    if marker and marker in text[s:e]:
        return text, "already_applied"
    return text[:s] + new_body.rstrip() + "\n\n" + text[e:], "applied"


def _set_field_value(text, field, new_value):
    """
    Replace the value of `    field: <type> = <old>` on its Config line,
    preserving the type and any trailing comment.
    """
    pattern = (rf"^(\s*{re.escape(field)}\s*:\s*\w+\s*=\s*)"
               rf"([^\s#]+)(\s*#.*)?$")
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return text, "FIELD_NOT_FOUND"
    current = m.group(2).strip()
    if current == new_value.strip():
        return text, "already_applied"

    def _repl(mm):
        return f"{mm.group(1)}{new_value}{mm.group(3) or ''}"

    return re.sub(pattern, _repl, text, count=1, flags=re.MULTILINE), "applied"


def _add_field(text, field_decl, after_field):
    """Insert `field_decl` immediately after the `after_field:` line."""
    field_name = field_decl.split(":")[0].strip()
    if re.search(rf"^\s*{re.escape(field_name)}\s*:", text, re.MULTILINE):
        return text, "already_applied"
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(after_field)}\s*:", line):
            lines.insert(i + 1, f"    {field_decl}")
            return "\n".join(lines), "applied"
    return text, "AFTER_FIELD_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════
#  NEW FUNCTION BODIES
# ═══════════════════════════════════════════════════════════════

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

    # [LOSS-ONLY-GUARD] \u0644\u0627 \u064a\u0639\u0645\u0644 \u0641\u064a \u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0631\u0628\u062d
    if action == "BUY" and current_price >= entry:
        _pnl_pct = (current_price - entry) / entry * 100.0
        return False, f"in_profit({_pnl_pct:+.2f}%)"
    if action == "SELL" and current_price <= entry:
        _pnl_pct = (entry - current_price) / entry * 100.0
        return False, f"in_profit({_pnl_pct:+.2f}%)"

    # [MFE-GUARD] \u0644\u0627 \u064a\u064f\u0637\u0644\u0642 \u0625\u0630\u0627 \u0643\u0627\u0646\u062a \u0627\u0644\u0635\u0641\u0642\u0629 \u0631\u0627\u0628\u062d\u0629 \u0633\u0627\u0628\u0642\u0627\u064b
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

    # TRIGGER 1 \u2014 PRICE (\u0647\u0628\u0648\u0637 \u0639\u0645\u064a\u0642 0.80R)
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

    # TRIGGER 2 \u2014 SIGNAL (\u0625\u0634\u0627\u0631\u0629 \u0645\u0639\u0627\u0643\u0633\u0629 \u0642\u0648\u064a\u0629 \u062d\u062f\u064a\u062b\u0629)
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


FUNC_DECIDE_NEW = '''def _opp_tp_decide(action_pos: str, entry: float, sl_dist0: float,
                   tp_old: float, partial_taken: bool,
                   entry_ci: int,
                   sig_opp, current_ci: int,
                   current_price=None):
    """
    Pure decision function. Returns (new_tp: float | None, reason: str).
    [OPP-TP-PROFIT-GUARD] \u0627\u0644\u0627\u0641\u062a\u0631\u0627\u0636\u064a: \u064a\u0639\u0645\u0644 \u0641\u0642\u0637 \u0648\u0627\u0644\u0633\u0639\u0631 \u0641\u064a \u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0631\u0628\u062d.
    """
    if not getattr(CFG, 'OPP_TP_ENABLED', False):
        return None, "disabled"
    if action_pos == sig_opp.action:
        return None, "same_direction"

    sc_o = float(getattr(sig_opp, 'score', 0.0) or 0.0)
    age = current_ci - int(getattr(sig_opp, 'close_idx', current_ci))
    if age < 0 or age > int(CFG.OPP_TP_MAX_AGE_BARS):
        return None, f"stale_opp(age={age})"
    if entry <= 0 or sl_dist0 <= 0:
        return None, "invalid_geom"

    p_opp = float(getattr(sig_opp, 'price', 0.0) or 0.0)
    if p_opp <= 0:
        return None, "invalid_opp_price"

    # [OPP-TP-PROFIT-GUARD] \u0641\u0642\u0637 \u0641\u064a \u0645\u0646\u0637\u0642\u0629 \u0627\u0644\u0631\u0628\u062d (\u0627\u0641\u062a\u0631\u0627\u0636\u064a)
    if getattr(CFG, 'OPP_TP_REQUIRE_PROFIT', True):
        if current_price is None or current_price <= 0:
            return None, "no_current_price_for_profit_guard"
        if action_pos == "BUY":
            _pnl_pct = (current_price - entry) / entry * 100.0
            if current_price <= entry:
                return None, f"not_in_profit(pnl={_pnl_pct:+.2f}%)"
        else:
            _pnl_pct = (entry - current_price) / entry * 100.0
            if current_price >= entry:
                return None, f"not_in_profit(pnl={_pnl_pct:+.2f}%)"

    min_gain = float(CFG.OPP_TP_MIN_PROFIT_R) * sl_dist0
    min_delta = float(CFG.OPP_TP_MIN_DELTA_R) * sl_dist0

    if action_pos == "BUY":
        tp_new = min(tp_old, p_opp)
        if tp_new < entry + min_gain:
            return None, f"below_min_gain({tp_new:.6f}<{entry+min_gain:.6f})"
        if tp_old - tp_new < min_delta:
            return None, f"delta_too_small({tp_old-tp_new:.6f}<{min_delta:.6f})"
        if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                and not partial_taken
                and getattr(CFG, 'OPP_TP_RESPECT_PARTIAL', True)):
            _p_trig = entry + float(CFG.PARTIAL_TP_R) * sl_dist0
            if tp_new <= _p_trig:
                return None, f"would_skip_partial(trig={_p_trig:.6f})"
    else:
        tp_new = max(tp_old, p_opp)
        if tp_new > entry - min_gain:
            return None, f"below_min_gain({tp_new:.6f}>{entry-min_gain:.6f})"
        if tp_new - tp_old < min_delta:
            return None, f"delta_too_small({tp_new-tp_old:.6f}<{min_delta:.6f})"
        if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                and not partial_taken
                and getattr(CFG, 'OPP_TP_RESPECT_PARTIAL', True)):
            _p_trig = entry - float(CFG.PARTIAL_TP_R) * sl_dist0
            if tp_new >= _p_trig:
                return None, f"would_skip_partial(trig={_p_trig:.6f})"

    return float(tp_new), "ok"
'''


FUNC_BT_NEW = '''def _maybe_adapt_tp_backtest(pos, sig_opp, ad, current_ci: int) -> bool:
    """
    Backtest wrapper for OpenPosition dataclass.
    Modifies pos.signal.tp1 in place.
    [OPP-TP-PROFIT-GUARD] current_price = close of the opposite signal's bar.
    """
    try:
        if getattr(pos, 'signal', None) is sig_opp:
            return False
        if int(current_ci) <= int(pos.entry_ci):
            return False

        sc_e = float(pos.signal.score)
        sc_o = float(sig_opp.score)
        if sc_e > 0 and sc_o < float(CFG.OPP_TP_SCORE_MULT) * sc_e:
            return False

        _cur_px = None
        try:
            if 0 <= int(current_ci) < len(ad.closes):
                _cur_px = float(ad.closes[int(current_ci)])
        except Exception:
            _cur_px = None

        tp_new, reason = _opp_tp_decide(
            action_pos=str(pos.signal.action),
            entry=float(pos.entry_px),
            sl_dist0=float(pos.sl_dist_initial),
            tp_old=float(pos.signal.tp1),
            partial_taken=bool(getattr(pos, 'partial_taken', False)),
            entry_ci=int(pos.entry_ci),
            sig_opp=sig_opp,
            current_ci=int(current_ci),
            current_price=_cur_px,
        )
        if tp_new is None:
            if reason not in ("disabled", "same_direction", "not_in_profit"):
                log.debug(f"[OppTP-BT] {pos.symbol} skip: {reason}")
            return False

        tp_old = float(pos.signal.tp1)
        pos.signal.tp1 = float(tp_new)

        _profit_pct = ((tp_new - float(pos.entry_px)) / float(pos.entry_px) * 100.0
                       if pos.signal.action == "BUY"
                       else (float(pos.entry_px) - tp_new) / float(pos.entry_px) * 100.0)

        _log_extra = f", cur_px={_cur_px:.6f}" if _cur_px is not None else ""
        log.info(
            f"[OppTP] {pos.symbol} {pos.signal.action} "
            f"TP {tp_old:.6f} -> {tp_new:.6f} "
            f"(profit={_profit_pct:+.2f}%, "
            f"opp score={float(sig_opp.score):.2f} vs {sc_e:.2f}"
            f"{_log_extra})"
        )
        return True
    except Exception as e:
        log.debug(f"[OppTP] backtest adapter failed: {e}")
        return False
'''


FUNC_LIVE_NEW = '''def _maybe_adapt_tp_live(pos: Dict, sig_opp, ad, exchange) -> bool:
    """
    Live wrapper for dict-based positions. Syncs protective orders.
    [OPP-TP-PROFIT-GUARD] current_price = close of last CLOSED bar
    (matches backtest; avoids ticker-vs-bar divergence).
    """
    try:
        _act = str(pos.get('action', '?'))
        if _act not in ('BUY', 'SELL'):
            return False
        if _act == sig_opp.action:
            return False

        _entry = float(pos.get('entry', 0.0))
        _sl_d0 = float(pos.get('sl_dist_initial', 0.0) or 0.0)
        if _entry <= 0 or _sl_d0 <= 0:
            return False

        _cur_ci = max(0, len(ad.closes) - 2) if ad is not None else int(
            getattr(sig_opp, 'close_idx', 0)
        )
        _entry_ci = int(pos.get('_entry_ci', 0) or 0)
        if _cur_ci <= _entry_ci:
            return False

        sc_e = float(pos.get('_orig_score', 0.0) or 0.0)
        sc_o = float(getattr(sig_opp, 'score', 0.0) or 0.0)
        if sc_e > 0 and sc_o < float(CFG.OPP_TP_SCORE_MULT) * sc_e:
            return False

        _cur_px = None
        try:
            if ad is not None and 0 <= _cur_ci < len(ad.closes):
                _cur_px = float(ad.closes[_cur_ci])
        except Exception:
            _cur_px = None

        _tp_old = float(pos.get('tp1', 0.0))
        if _tp_old <= 0:
            return False

        tp_new, reason = _opp_tp_decide(
            action_pos=_act,
            entry=_entry,
            sl_dist0=_sl_d0,
            tp_old=_tp_old,
            partial_taken=bool(pos.get('_partial_taken', False)),
            entry_ci=_entry_ci,
            sig_opp=sig_opp,
            current_ci=_cur_ci,
            current_price=_cur_px,
        )
        if tp_new is None:
            if reason not in ("disabled", "same_direction", "not_in_profit"):
                log.debug(f"[OppTP] {pos.get('_sym','?')} skip: {reason}")
            return False

        pos['tp1'] = float(tp_new)

        _profit_pct = ((tp_new - _entry) / _entry * 100.0
                       if _act == "BUY"
                       else (_entry - tp_new) / _entry * 100.0)

        _log_extra = f", cur_px={_cur_px:.6f}" if _cur_px else ""
        log.info(
            f"[OppTP-LV] {pos.get('_sym','?')} {_act} "
            f"TP {_tp_old:.6f} -> {tp_new:.6f} "
            f"(profit={_profit_pct:+.2f}%, "
            f"opp score={sc_o:.2f} vs {sc_e:.2f}"
            f"{_log_extra})"
        )

        if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
            try:
                _sync_protective_orders(exchange, pos['_sym'], pos)
            except Exception as _e:
                log.warning(f"[OppTP] {pos.get('_sym','?')} "
                            f"prot sync failed: {_e}")
        return True
    except Exception as e:
        log.debug(f"[OppTP] live adapter failed: {e}")
        return False
'''


# ═══════════════════════════════════════════════════════════════
#  EXACT BLOCK anchors (old → new)
# ═══════════════════════════════════════════════════════════════

# ── _advance signature ─────────────────────────────────────────
ADVANCE_SIG_OLD = "def _advance(pos, ad, to_ci, partial_cb=None):\n"
ADVANCE_SIG_NEW = "def _advance(pos, ad, to_ci, partial_cb=None, opp_by_sym_ci=None):\n"


# ── BEEsc price-trigger (micro version — no _signal_sl_above_beesc) ─
BEESC_PRICE_OLD = """        # \u2550\u2550 [BREAKEVEN ESCAPE \u2014 Price Trigger] \u2550\u2550
        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                and not getattr(pos, '_be_esc_done', False)
                and pos.sl_dist_initial > 0):
            _be_trig, _be_rsn = _should_breakeven_escape(
                ad, cidx, float(p), sig.action,
                pos.entry_px, pos.sl_dist_initial, sig_opp=None
            )
"""

BEESC_PRICE_NEW = """        # \u2550\u2550 [BEEsc-FIX] Price Trigger \u2014 \u064a\u062c\u0645\u0639 sig_opp \u0645\u0646 \u0646\u0641\u0633 \u0627\u0644\u0634\u0645\u0639\u0629 \u2550\u2550
        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                and not getattr(pos, '_be_esc_done', False)
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


# ── BEEsc-cancel BUY branch ────────────────────────────────────
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
                        if _be_use_close:
                            _bounce_src = float(ad.closes[cidx])
                        elif _use_high_for_bounce:
                            _bounce_src = float(ad.highs[cidx])
                        else:
                            _bounce_src = float(p)
                        _bounce_c = _bounce_src - _low_c
"""


# ── BEEsc-cancel SELL branch ───────────────────────────────────
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


# ── TP labels ──────────────────────────────────────────────────
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


# ── simulate_portfolio: build opp_by_sym_ci map ───────────────
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


# ── simulate_portfolio: update _advance calls ─────────────────
ADV_CALL1_OLD = """            ep, er, ec = _advance(pos, ad, toci, partial_cb=_partial_tp)
"""

ADV_CALL1_NEW = """            ep, er, ec = _advance(pos, ad, toci, partial_cb=_partial_tp,
                                   opp_by_sym_ci=_opp_by_sym_ci)
"""

ADV_CALL2_OLD = """        _advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp)
"""

ADV_CALL2_NEW = """        _advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp,
                 opp_by_sym_ci=_opp_by_sym_ci)
"""


# ── run_live: BEEsc-MIGRATION block ───────────────────────────
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


# ── run_live: BEEsc price-call ────────────────────────────────
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
                        pos=pos,
                    )
"""


# ── run_live: BEEsc signal-call ───────────────────────────────
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
                            pos=_pos_be,
                        )
"""


# ── run_live: TP label ────────────────────────────────────────
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


# ── run_live: _urgent ─────────────────────────────────────────
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
                        or 'BEEsc-breakeven' in rsn
                        or 'LiqProximity' in rsn
                        or (_apex_urgent_lv and (
                            ('Apex' in rsn) or ('Topo-Div' in rsn)))
                    )
"""


# ── main(): BEEsc warnings ────────────────────────────────────
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
                f"[BEEsc] --be-escape-move-r={_v} < 0.60 "
                f"\u0642\u062f \u064a\u064f\u0637\u0644\u0642 BEEsc \u0639\u0644\u0649 \u062a\u0630\u0628\u0630\u0628 \u0639\u0627\u062f\u064a. "
                f"\u0627\u0644\u0645\u0648\u0635\u0649 \u0628\u0647: 0.80"
            )
    if getattr(args, "be_escape_min_profit_r", None) is not None:
        _v = float(args.be_escape_min_profit_r)
        if _v < 0.10:
            log.warning(
                f"[BEEsc] --be-escape-min-profit-r={_v} < 0.10 "
                f"\u064a\u062c\u0639\u0644 BEEsc-exit \u0633\u0627\u0644\u0628\u0627\u064b (\u0631\u0633\u0648\u0645 > \u0631\u0628\u062d). "
                f"\u0627\u0644\u0645\u0648\u0635\u0649 \u0628\u0647: 0.15+"
            )
"""


# ── CLI: --opp-tp-allow-loss ─────────────────────────────────
CLI_OLD = """    p.add_argument("--opp-tp", action="store_true",
                   help="Enable adaptive TP: when an opposite signal "
                        "appears on the same symbol, move the open "
                        "position's TP to the opposite's tunnel entry")
"""

CLI_NEW = """    p.add_argument("--opp-tp", action="store_true",
                   help="Enable adaptive TP: when an opposite signal "
                        "appears on the same symbol, move the open "
                        "position's TP to the opposite's tunnel entry")
    p.add_argument("--opp-tp-allow-loss", action="store_true",
                   help="[OppTP] Allow the adaptive TP to fire even when "
                        "the position is in loss zone. Default: only in "
                        "profit zone (safer -- protection of profit region)")
"""


# ── Wiring: OppTP flag ────────────────────────────────────────
WIRING_OLD = """    if args.opp_tp:
        CFG.OPP_TP_ENABLED = True
        if args.opp_tp_score_mult is not None:
            CFG.OPP_TP_SCORE_MULT = float(args.opp_tp_score_mult)
        if args.opp_tp_min_profit_r is not None:
            CFG.OPP_TP_MIN_PROFIT_R = float(args.opp_tp_min_profit_r)
        if args.opp_tp_min_delta_r is not None:
            CFG.OPP_TP_MIN_DELTA_R = float(args.opp_tp_min_delta_r)
        if args.opp_tp_max_age_bars is not None:
            CFG.OPP_TP_MAX_AGE_BARS = int(args.opp_tp_max_age_bars)
        log.info("[OppTP] Opposite-Signal Adaptive TP ENABLED")
        log.info(f"[OppTP]  score_mult={CFG.OPP_TP_SCORE_MULT}, "
                 f"min_profit_R={CFG.OPP_TP_MIN_PROFIT_R}, "
                 f"min_delta_R={CFG.OPP_TP_MIN_DELTA_R}, "
                 f"max_age={CFG.OPP_TP_MAX_AGE_BARS}")
    else:
        log.info("[OppTP] Opposite-Signal Adaptive TP DISABLED")
"""

WIRING_NEW = """    if args.opp_tp:
        CFG.OPP_TP_ENABLED = True
        if args.opp_tp_score_mult is not None:
            CFG.OPP_TP_SCORE_MULT = float(args.opp_tp_score_mult)
        if args.opp_tp_min_profit_r is not None:
            CFG.OPP_TP_MIN_PROFIT_R = float(args.opp_tp_min_profit_r)
        if args.opp_tp_min_delta_r is not None:
            CFG.OPP_TP_MIN_DELTA_R = float(args.opp_tp_min_delta_r)
        if args.opp_tp_max_age_bars is not None:
            CFG.OPP_TP_MAX_AGE_BARS = int(args.opp_tp_max_age_bars)
        if getattr(args, "opp_tp_allow_loss", False):
            CFG.OPP_TP_REQUIRE_PROFIT = False
            log.warning(
                "[OppTP] --opp-tp-allow-loss: OPP_TP may fire in LOSS zone "
                "-- moving TP to opposite signal's entry even when the "
                "position is losing. NOT recommended."
            )
        else:
            CFG.OPP_TP_REQUIRE_PROFIT = True
        log.info("[OppTP] Opposite-Signal Adaptive TP ENABLED")
        log.info(f"[OppTP]  score_mult={CFG.OPP_TP_SCORE_MULT}, "
                 f"min_profit_R={CFG.OPP_TP_MIN_PROFIT_R}, "
                 f"min_delta_R={CFG.OPP_TP_MIN_DELTA_R}, "
                 f"max_age={CFG.OPP_TP_MAX_AGE_BARS}, "
                 f"profit_guard={CFG.OPP_TP_REQUIRE_PROFIT}")
        if CFG.OPP_TP_REQUIRE_PROFIT:
            log.info("[OppTP] Behavior: fires ONLY in profit zone; TP moves to "
                     "the opposite signal's entry, guaranteeing at least "
                     "OPP_TP_MIN_PROFIT_R.")
    else:
        log.info("[OppTP] Opposite-Signal Adaptive TP DISABLED")
"""


# ═══════════════════════════════════════════════════════════════
#  PATCH LIST (ordered)
# ═══════════════════════════════════════════════════════════════

PATCHES = [
    # ── Config fields (order: set → add) ──
    {"name": "Config: set PRICE_MOVE_R = 0.80",
     "kind": "set_field", "field": "BREAKEVEN_ESCAPE_PRICE_MOVE_R",
     "value": "0.80"},

    {"name": "Config: set SIGNAL_ENABLED = True",
     "kind": "set_field", "field": "BREAKEVEN_ESCAPE_SIGNAL_ENABLED",
     "value": "True"},

    {"name": "Config: set MIN_PROFIT_R = 0.15",
     "kind": "set_field", "field": "BREAKEVEN_ESCAPE_MIN_PROFIT_R",
     "value": "0.15"},

    {"name": "Config: + MFE_GUARD_R",
     "kind": "add_field",
     "field_decl": "BREAKEVEN_ESCAPE_MFE_GUARD_R: float = 0.50",
     "after": "BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK"},

    {"name": "Config: + CANCEL_USE_HIGH",
     "kind": "add_field",
     "field_decl": "BREAKEVEN_ESCAPE_CANCEL_USE_HIGH: bool = True",
     "after": "BREAKEVEN_ESCAPE_MFE_GUARD_R"},

    {"name": "Config: + CANCEL_MIN_BOUNCE_SIGMA",
     "kind": "add_field",
     "field_decl": "BREAKEVEN_ESCAPE_CANCEL_MIN_BOUNCE_SIGMA: float = 1.0",
     "after": "BREAKEVEN_ESCAPE_CANCEL_USE_HIGH"},

    {"name": "Config: + OPP_TP_REQUIRE_PROFIT",
     "kind": "add_field",
     "field_decl": "OPP_TP_REQUIRE_PROFIT: bool = True",
     "after": "OPP_TP_RESPECT_PARTIAL"},

    # ── Function replacements ──
    {"name": "Func: _should_breakeven_escape",
     "kind": "func", "name_arg": "_should_breakeven_escape",
     "body": FUNC_SHOULD_BE_NEW, "marker": "was_profitable(mfe="},

    {"name": "Func: _exit_is_taker",
     "kind": "func", "name_arg": "_exit_is_taker",
     "body": FUNC_EXIT_TAKER_NEW, "marker": '"BEEsc-breakeven" in r'},

    {"name": "Func: _opp_tp_decide",
     "kind": "func", "name_arg": "_opp_tp_decide",
     "body": FUNC_DECIDE_NEW, "marker": "current_price=None):"},

    {"name": "Func: _maybe_adapt_tp_backtest",
     "kind": "func", "name_arg": "_maybe_adapt_tp_backtest",
     "body": FUNC_BT_NEW, "marker": "current_price=_cur_px,"},

    {"name": "Func: _maybe_adapt_tp_live",
     "kind": "func", "name_arg": "_maybe_adapt_tp_live",
     "body": FUNC_LIVE_NEW, "marker": "current_price=_cur_px,"},

    # ── Exact block replacements ──
    {"name": "4a.  _advance: BEEsc price trigger",
     "kind": "exact", "old": BEESC_PRICE_OLD, "new": BEESC_PRICE_NEW,
     "marker": "_sig_opp_here"},

    {"name": "4b1. _advance: BEEsc-cancel BUY",
     "kind": "exact", "old": CANCEL_BUY_OLD, "new": CANCEL_BUY_NEW,
     "marker": "_use_high_for_bounce"},

    {"name": "4b2. _advance: BEEsc-cancel SELL",
     "kind": "exact", "old": CANCEL_SELL_OLD, "new": CANCEL_SELL_NEW,
     "marker": "_bounce_c = _high_c - _bounce_src"},

    {"name": "4c1. _advance: TP label (sub-bar)",
     "kind": "exact", "old": TP_LABEL_SUB_OLD, "new": TP_LABEL_SUB_NEW,
     "marker": '_tp_label = ("BEEsc-breakeven"\n                                 if'},

    {"name": "4c2. _advance: TP label (main-bar)",
     "kind": "exact", "old": TP_LABEL_MAIN_OLD, "new": TP_LABEL_MAIN_NEW,
     "marker": '_tp_label = ("BEEsc-breakeven"\n                             if'},

    {"name": "5.   _advance: signature",
     "kind": "exact", "old": ADVANCE_SIG_OLD, "new": ADVANCE_SIG_NEW,
     "marker": "def _advance(pos, ad, to_ci, partial_cb=None, opp_by_sym_ci=None):"},

    {"name": "6a.  simulate_portfolio: build map",
     "kind": "exact", "old": OPP_MAP_OLD, "new": OPP_MAP_NEW,
     "marker": "_opp_by_sym_ci = defaultdict(list)"},

    {"name": "6b.  simulate_portfolio: _advance call #1",
     "kind": "exact", "old": ADV_CALL1_OLD, "new": ADV_CALL1_NEW,
     "marker": "opp_by_sym_ci=_opp_by_sym_ci)"},

    {"name": "6c.  simulate_portfolio: _advance call #2",
     "kind": "exact", "old": ADV_CALL2_OLD, "new": ADV_CALL2_NEW,
     "marker": "_advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp,\n                 opp_by_sym_ci=_opp_by_sym_ci)"},

    {"name": "7a.  run_live: BEEsc-MIGRATION block",
     "kind": "exact", "old": MIGRATION_ANCHOR, "new": MIGRATION_BLOCK,
     "marker": "[BEEsc-MIGRATION]"},

    {"name": "7b.  run_live: BEEsc price call (pos=)",
     "kind": "exact", "old": LIVE_BE_PRICE_OLD, "new": LIVE_BE_PRICE_NEW,
     "marker": "pos=pos,"},

    {"name": "7c.  run_live: BEEsc signal call (pos=)",
     "kind": "exact", "old": LIVE_BE_SIG_OLD, "new": LIVE_BE_SIG_NEW,
     "marker": "pos=_pos_be,"},

    {"name": "7d.  run_live: TP label",
     "kind": "exact", "old": LIVE_TP_LABEL_OLD, "new": LIVE_TP_LABEL_NEW,
     "marker": "_tp_label_lv"},

    {"name": "7e.  run_live: _urgent",
     "kind": "exact", "old": LIVE_URGENT_OLD, "new": LIVE_URGENT_NEW,
     "marker": "'BEEsc-breakeven' in rsn"},

    {"name": "8.   main(): BEEsc warnings",
     "kind": "exact", "old": WARN_OLD, "new": WARN_NEW,
     "marker": "[BEEsc-WARN]"},

    {"name": "CLI: --opp-tp-allow-loss",
     "kind": "exact", "old": CLI_OLD, "new": CLI_NEW,
     "marker": "--opp-tp-allow-loss"},

    {"name": "Wiring: OppTP flag",
     "kind": "exact", "old": WIRING_OLD, "new": WIRING_NEW,
     "marker": 'if getattr(args, "opp_tp_allow_loss", False):'},
]


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Apply ALL fixes to trading_2_live4_claude2_v4_micro_pro.py")
    ap.add_argument("--file", default=DEFAULT_TARGET)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--verbose", action="store_true")
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
        print(f"[ERROR] Target has syntax errors BEFORE patching: {err}",
              file=sys.stderr)
        return 3
    print("[OK] Original syntax verified.\n")

    text = original
    results = []

    for p in PATCHES:
        try:
            if p["kind"] == "set_field":
                text, status = _set_field_value(text, p["field"], p["value"])
            elif p["kind"] == "add_field":
                text, status = _add_field(text, p["field_decl"], p["after"])
            elif p["kind"] == "func":
                text, status = _apply_function(
                    text, p["name_arg"], p["body"], p["marker"])
            elif p["kind"] == "exact":
                text, status = _apply_exact(
                    text, p["old"], p["new"], p["marker"])
            else:
                status = f"UNKNOWN_KIND:{p['kind']}"
        except Exception as e:
            status = f"EXCEPTION:{e}"

        results.append((p["name"], status))
        icon = {"applied": "\u2705",
                "already_applied": "\u23ed\ufe0f",
                "FIELD_NOT_FOUND": "\u274c",
                "AFTER_FIELD_NOT_FOUND": "\u274c",
                "FUNCTION_NOT_FOUND": "\u274c",
                "ANCHOR_NOT_FOUND": "\u274c"}.get(status, "\u26a0\ufe0f")
        print(f"  {icon} {p['name']:45s} [{status}]")

        if status.endswith("NOT_FOUND") and args.verbose:
            anchor = p.get("old", p.get("field_decl", p.get("name_arg", "")))
            print(f"       ANCHOR preview:")
            for line in anchor.splitlines()[:3]:
                print(f"         | {line}")

    failed = [r for r in results if "NOT_FOUND" in r[1] or "EXCEPTION" in r[1]]
    if failed:
        print(f"\n[ERROR] {len(failed)} patch(es) failed — nothing written.",
              file=sys.stderr)
        for name, st in failed:
            print(f"    \u2022 {name}: {st}", file=sys.stderr)
        print("\n[INFO] Use --verbose to preview expected anchors. The file "
              "may have been edited manually — patch the affected block by "
              "hand or adjust the anchor in this script.", file=sys.stderr)
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
        delta = len(text.encode("utf-8")) - len(original.encode("utf-8"))
        print(f"[DRY-RUN] Would write {len(text.encode('utf-8')):,} bytes "
              f"(delta: {delta:+,})")
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
    print("  1. Verify: python3 apply_all_fixes_micro.py --check")
    print("  2. Run   : python3 trading_2_live4_claude2_v4_micro_pro.py "
          "--opp-tp --be-escape --be-escape-move-r 0.80 "
          "--be-escape-min-profit-r 0.15 (remove --no-be-escape-ema)")
    print("  3. Watch : grep -E 'BEEsc-breakeven|OppTP|Hard TP' bot.log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
