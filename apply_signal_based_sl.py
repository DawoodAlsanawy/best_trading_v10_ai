#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_signal_based_sl.py — Signal-Based SL Update
===================================================
يُضيف ميزة اختيارية (opt-in): عندما تظهر إشارة جديدة بنفس الاتجاه
على أصل لديه مركز مفتوح، رفع SL لمستوى SL الإشارة الجديدة (ratchet فقط).

- Backward compatible: معطّل افتراضياً — السلوك الحالي محفوظ 100%.
- Parity: نفس المنطق في backtest و live.
- BEEsc: إذا تجاوز SL مستوى BEEsc، يُلغى BEEsc لهذه الصفقة (SL أكثر حماية).

التفعيل: --signal-based-sl

الاستخدام:
    python3 apply_signal_based_sl.py --dry-run --verbose
    python3 apply_signal_based_sl.py
"""

import ast, os, shutil, sys
from datetime import datetime

MARKER = "# [SIGNAL-BASED-SL-APPLIED]"
DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"
VERBOSE = False


def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def vlog(msg):
    if VERBOSE:
        log(msg, "DEBUG")


def fail(msg):
    log(msg, "FAIL")
    raise SystemExit(1)


def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_signal_sl_{ts}"
    shutil.copy2(path, bak)
    log(f"  نسخة احتياطية: {bak}")
    return bak


def verify_syntax(content, label=""):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        ctx = ""
        if e.lineno:
            lines = content.split("\n")
            lo, hi = max(0, e.lineno - 9), min(len(lines), e.lineno + 8)
            ctx = f"\n{label} Context:\n"
            for i in range(lo, hi):
                m = ">>> " if i == e.lineno - 1 else "    "
                ctx += f"{m}{i+1:6d}: {lines[i]}\n"
        return False, f"line {e.lineno}: {e.msg}\n{ctx}"


def must_replace(content, old, new, label):
    n = content.count(old)
    if n == 0:
        fail(f"[{label}] anchor not found (0 matches)\n"
             f"expected: {old[:120]!r}")
    if n > 1:
        fail(f"[{label}] ambiguous ({n} matches)")
    vlog(f"    [{label}] replaced ({len(old)}->{len(new)} chars)")
    return content.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════
# CODE BLOCKS
# ═══════════════════════════════════════════════════════════════

CONFIG_BLOCK = '''
    # ══ [SIGNAL-BASED SL] ══
    # When enabled, if a NEW same-direction signal appears on a symbol
    # with an open position, raise SL to the new signal's SL level
    # (ratchet-only, never widens).
    #
    # Ratchet rule (BUY):  new_sl = max(current_sl, sig.sl)
    # Ratchet rule (SELL): new_sl = min(current_sl, sig.sl)
    #
    # Filters (all must pass):
    #   - S_new.action == pos.action
    #   - S_new.score >= pos.score × SIGNAL_SL_MIN_SCORE_RATIO
    #   - |new_sl - current_sl| / current_sl >= SIGNAL_SL_MIN_IMPROVEMENT
    #   - new_sl is SIGNAL_SL_SAFETY_MARGIN away from current price
    #   - If SIGNAL_SL_PROTECT_PROFIT_ONLY: new_sl above entry (BUY) / below (SELL)
    #
    # BEEsc interaction:
    #   - SIGNAL_SL_ALLOW_ABOVE_BEESC=True: SL may cross BEEsc level.
    #     When it does, BEEsc is disabled for this trade (SL takes priority).
    #   - False: SL clamped to BEEsc level.
    #
    # Design note: SL updates are EVENT-DRIVEN (only on new signals),
    # NOT continuous trailing. This avoids the "cut every winner" failure
    # mode of Smart Center, while still protecting unrealized gains.
    #
    # Enable via --signal-based-sl CLI flag.
    SIGNAL_BASED_SL_ENABLED: bool = False
    SIGNAL_SL_MIN_SCORE_RATIO: float = 1.5
    SIGNAL_SL_MIN_IMPROVEMENT: float = 0.005
    SIGNAL_SL_SAFETY_MARGIN: float = 0.001
    SIGNAL_SL_PROTECT_PROFIT_ONLY: bool = False
    SIGNAL_SL_ALLOW_ABOVE_BEESC: bool = True
'''


FUNCTION_BLOCK = r'''
# ══ [SIGNAL-SL] Live: track last processed signal close_idx per symbol ══
_SIGNAL_SL_LAST_PROCESSED: Dict[str, int] = {}


def _maybe_update_sl_from_signal(pos, sig, current_price, ad):
    """
    [Signal-SL] Try to raise SL when a new same-direction signal appears
    on a symbol with an open position.

    Ratchet-only: SL moves only in the favorable direction (up for BUY,
    down for SELL). Never widens.

    Works with both OpenPosition dataclass (backtest) and pos dict (live).

    Returns
    -------
    (updated: bool, new_sl: float, reason: str)
        - updated=False → new_sl equals current pos SL (no change).
        - updated=True  → new_sl is the proposed SL; caller must apply it.
    """
    # ── 0. Validate inputs ──
    try:
        if ad is None or sig is None:
            return False, 0.0, "no_data"
        if current_price is None or current_price <= 0:
            return False, 0.0, "invalid_price"
    except Exception as e:
        return False, 0.0, f"input_err:{e}"

    is_dict = isinstance(pos, dict)

    # ── 1. Extract position fields ──
    try:
        if is_dict:
            pos_action = str(pos.get('action', '?'))
            pos_sl_cur = float(pos.get('sl') or 0)
            pos_entry = float(pos.get('entry') or 0)
            pos_score = float(pos.get('_orig_score') or 0)
            pos_sl_dist0 = float(pos.get('sl_dist_initial') or 0)
            be_esc_done = bool(pos.get('_be_esc_done', False))
            sl_above_beesc = bool(pos.get('_signal_sl_above_beesc', False))
        else:
            pos_action = str(pos.signal.action)
            pos_sl_cur = float(pos.trail_sl)
            pos_entry = float(pos.entry_px)
            pos_score = float(pos.signal.score)
            pos_sl_dist0 = float(getattr(pos, 'sl_dist_initial', 0.0))
            be_esc_done = bool(getattr(pos, '_be_esc_done', False))
            sl_above_beesc = bool(getattr(pos, '_signal_sl_above_beesc', False))
    except Exception as e:
        return False, 0.0, f"extract_err:{e}"

    # ── 2. Same-direction guard ──
    if pos_action not in ('BUY', 'SELL'):
        return False, pos_sl_cur, "invalid_pos_action"
    if sig.action != pos_action:
        return False, pos_sl_cur, "opposite_direction"

    # ── 3. Basic validity ──
    if pos_sl_cur <= 0 or pos_entry <= 0:
        return False, pos_sl_cur, "invalid_position"
    if be_esc_done:
        return False, pos_sl_cur, "be_esc_already_done"

    # ── 4. Score filter ──
    score_ratio = float(getattr(CFG, 'SIGNAL_SL_MIN_SCORE_RATIO', 1.5))
    sig_score = float(getattr(sig, 'score', 0.0))
    if pos_score > 0 and sig_score > 0:
        if sig_score < pos_score * score_ratio:
            return False, pos_sl_cur, (
                f"score_below_ratio({sig_score:.2f}<{pos_score * score_ratio:.2f})")

    # ── 5. Signal SL validity ──
    sig_sl = float(getattr(sig, 'sl', 0.0))
    if sig_sl <= 0 or not np.isfinite(sig_sl):
        return False, pos_sl_cur, "invalid_sig_sl"

    # ── 6. Ratchet: only improve ──
    if pos_action == 'BUY':
        if sig_sl <= pos_sl_cur:
            return False, pos_sl_cur, (
                f"ratchet_no_improve(BUY {sig_sl:.6f}<={pos_sl_cur:.6f})")
    else:  # SELL
        if sig_sl >= pos_sl_cur:
            return False, pos_sl_cur, (
                f"ratchet_no_improve(SELL {sig_sl:.6f}>={pos_sl_cur:.6f})")

    # ── 7. Minimum improvement ──
    min_imp = float(getattr(CFG, 'SIGNAL_SL_MIN_IMPROVEMENT', 0.005))
    improvement = abs(sig_sl - pos_sl_cur) / max(abs(pos_sl_cur), 1e-12)
    if improvement < min_imp:
        return False, pos_sl_cur, (
            f"tiny_improvement({improvement*100:.3f}%<{min_imp*100:.3f}%)")

    # ── 8. Protect profit only (optional) ──
    if getattr(CFG, 'SIGNAL_SL_PROTECT_PROFIT_ONLY', False):
        if pos_action == 'BUY' and sig_sl <= pos_entry:
            return False, pos_sl_cur, (
                f"not_protecting_profit(BUY {sig_sl:.6f}<={pos_entry:.6f})")
        if pos_action == 'SELL' and sig_sl >= pos_entry:
            return False, pos_sl_cur, (
                f"not_protecting_profit(SELL {sig_sl:.6f}>={pos_entry:.6f})")

    # ── 9. Safety margin: SL must be away from current price ──
    safety = float(getattr(CFG, 'SIGNAL_SL_SAFETY_MARGIN', 0.001))
    new_sl = sig_sl
    if pos_action == 'BUY':
        max_allowed = current_price * (1.0 - safety)
        if new_sl > max_allowed:
            new_sl = max_allowed
    else:
        min_allowed = current_price * (1.0 + safety)
        if new_sl < min_allowed:
            new_sl = min_allowed

    # Re-check ratchet after safety clamp
    if pos_action == 'BUY' and new_sl <= pos_sl_cur:
        return False, pos_sl_cur, "safety_clamp_no_improve"
    if pos_action == 'SELL' and new_sl >= pos_sl_cur:
        return False, pos_sl_cur, "safety_clamp_no_improve"

    # ── 10. BEEsc interaction ──
    allow_above = bool(getattr(CFG, 'SIGNAL_SL_ALLOW_ABOVE_BEESC', True))
    set_above_flag = False

    if (not be_esc_done
            and not sl_above_beesc
            and getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
            and pos_sl_dist0 > 0):
        kb = float(getattr(CFG, 'BREAKEVEN_ESCAPE_PRICE_MOVE_R', 0.30))
        be_buffer = 0.001
        if pos_action == 'BUY':
            be_level = pos_entry - kb * pos_sl_dist0
            be_max = be_level * (1.0 - be_buffer)
            if new_sl > be_max:
                if allow_above:
                    set_above_flag = True
                else:
                    new_sl = be_max
                    if new_sl <= pos_sl_cur:
                        return False, pos_sl_cur, "beesc_clamp_no_improve"
        else:  # SELL
            be_level = pos_entry + kb * pos_sl_dist0
            be_min = be_level * (1.0 + be_buffer)
            if new_sl < be_min:
                if allow_above:
                    set_above_flag = True
                else:
                    new_sl = be_min
                    if new_sl >= pos_sl_cur:
                        return False, pos_sl_cur, "beesc_clamp_no_improve"

    # ── 11. Apply BEEsc-disable flag (sticky) ──
    if set_above_flag:
        try:
            if is_dict:
                pos['_signal_sl_above_beesc'] = True
            else:
                pos._signal_sl_above_beesc = True
        except Exception:
            pass

    reason = (f"signal_sl {pos_sl_cur:.6f}->{new_sl:.6f} "
              f"(imp={improvement*100:.2f}%")
    if set_above_flag:
        reason += ",beesc_disabled"
    reason += ")"
    return True, new_sl, reason

# ═══════════════════════════════════════════════════════════════
'''


BACKTEST_INTEGRATION = '''        # ══ [SIGNAL-SL] رفع SL من إشارة جديدة (نفس الاتجاه) ══
        if (getattr(CFG, 'SIGNAL_BASED_SL_ENABLED', False)
                and sig.symbol in open_pos):
            try:
                _ssl_pos = open_pos[sig.symbol]
                _ssl_ad = assets.get(sig.symbol)
                _ssl_ci = int(sig.close_idx)
                if _ssl_ad is not None and 0 <= _ssl_ci < len(_ssl_ad.closes):
                    _ssl_price = float(_ssl_ad.closes[_ssl_ci])
                else:
                    _ssl_price = float(sig.price)
                _ssl_ok, _ssl_new, _ssl_rsn = _maybe_update_sl_from_signal(
                    _ssl_pos, sig, _ssl_price, _ssl_ad
                )
                if _ssl_ok:
                    _ssl_old = float(_ssl_pos.trail_sl)
                    _ssl_pos.trail_sl = _ssl_new
                    log.debug(
                        f"[Signal-SL-BT] {sig.symbol} {sig.action} "
                        f"SL {_ssl_old:.6f}->{_ssl_new:.6f} ({_ssl_rsn})"
                    )
                elif VERBOSE:
                    log.debug(
                        f"[Signal-SL-BT] {sig.symbol} {sig.action} "
                        f"rejected: {_ssl_rsn}"
                    )
            except Exception as _ssl_e:
                log.debug(f"[Signal-SL-BT] {sig.symbol} error: {_ssl_e}")

'''


LIVE_INTEGRATION = '''                # ══ [SIGNAL-SL] رفع SL من إشارة جديدة (نفس الاتجاه) ══
                if (getattr(CFG, 'SIGNAL_BASED_SL_ENABLED', False)
                        and 'assets' in dir() and assets):
                    for _ssl_sig in sigs:
                        _ssl_sym = _ssl_sig.symbol
                        if _ssl_sym not in open_pos_live:
                            continue
                        _ssl_key = int(_ssl_sig.close_idx)
                        if _ssl_key <= _SIGNAL_SL_LAST_PROCESSED.get(_ssl_sym, -1):
                            continue
                        _ssl_pos = open_pos_live[_ssl_sym]
                        _ssl_ad = assets.get(_ssl_sym)
                        if _ssl_ad is None:
                            continue
                        _SIGNAL_SL_LAST_PROCESSED[_ssl_sym] = _ssl_key
                        try:
                            _ssl_ci_now = max(0, len(_ssl_ad.closes) - 2)
                            _ssl_price = (
                                float(_ssl_ad.closes[_ssl_ci_now])
                                if 0 <= _ssl_ci_now < len(_ssl_ad.closes)
                                else float(_ssl_sig.price))
                            _ssl_ok, _ssl_new, _ssl_rsn = _maybe_update_sl_from_signal(
                                _ssl_pos, _ssl_sig, _ssl_price, _ssl_ad
                            )
                            if _ssl_ok:
                                _ssl_old = float(_ssl_pos.get('sl', 0))
                                _ssl_pos['sl'] = _ssl_new
                                _ssl_pos['_signal_sl_last_reason'] = _ssl_rsn
                                log.info(
                                    f"[Signal-SL-LV] {_ssl_sym} "
                                    f"{_ssl_sig.action} SL "
                                    f"{_ssl_old:.6f}->{_ssl_new:.6f} "
                                    f"({_ssl_rsn})"
                                )
                                try:
                                    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
                                        _sync_protective_orders(
                                            exchange, _ssl_sym, _ssl_pos)
                                except Exception as _ssl_e:
                                    log.debug(
                                        f"[Signal-SL-LV] {_ssl_sym} "
                                        f"prot sync: {_ssl_e}")
                                try:
                                    _lv_save_state(state_file, open_pos_live)
                                except Exception:
                                    pass
                            elif VERBOSE:
                                log.debug(
                                    f"[Signal-SL-LV] {_ssl_sym} "
                                    f"{_ssl_sig.action} rejected: {_ssl_rsn}")
                        except Exception as _ssl_e:
                            log.debug(
                                f"[Signal-SL-LV] {_ssl_sym} error: {_ssl_e}")

'''


CLI_FLAGS = '''    p.add_argument("--signal-based-sl", action="store_true",
                   help="[Signal-SL] Raise SL when a same-direction new signal "
                        "appears on an open position (ratchet-only, never widens)")
    p.add_argument("--signal-sl-score-ratio", type=float, default=None,
                   help="[Signal-SL] New signal score must be >= this × original "
                        "score (default 1.5)")
    p.add_argument("--signal-sl-min-improvement", type=float, default=None,
                   help="[Signal-SL] Minimum SL improvement ratio "
                        "(default 0.005 = 0.5%%)")
    p.add_argument("--signal-sl-protect-profit", action="store_true",
                   help="[Signal-SL] Only accept SL updates that move above "
                        "entry (BUY) / below entry (SELL)")
    p.add_argument("--signal-sl-clamp-beesc", action="store_true",
                   help="[Signal-SL] Clamp SL below BEEsc level (default: "
                        "allow crossing — BEEsc disabled when crossed)")
'''


ARGPARSE_BLOCK = '''
    if getattr(args, "signal_based_sl", False):
        CFG.SIGNAL_BASED_SL_ENABLED = True
        log.info("[Signal-SL] ENABLED — same-direction signals may raise SL "
                 "(ratchet-only, event-driven)")
        if args.signal_sl_score_ratio is not None:
            CFG.SIGNAL_SL_MIN_SCORE_RATIO = float(args.signal_sl_score_ratio)
            log.info(f"[Signal-SL] score_ratio = {CFG.SIGNAL_SL_MIN_SCORE_RATIO}")
        if args.signal_sl_min_improvement is not None:
            CFG.SIGNAL_SL_MIN_IMPROVEMENT = float(args.signal_sl_min_improvement)
            log.info(f"[Signal-SL] min_improvement = "
                     f"{CFG.SIGNAL_SL_MIN_IMPROVEMENT*100:.2f}%")
        if args.signal_sl_protect_profit:
            CFG.SIGNAL_SL_PROTECT_PROFIT_ONLY = True
            log.info("[Signal-SL] protect_profit = ON")
        if args.signal_sl_clamp_beesc:
            CFG.SIGNAL_SL_ALLOW_ABOVE_BEESC = False
            log.info("[Signal-SL] BEEsc clamp = ON (SL cannot cross BEEsc)")
        else:
            log.info("[Signal-SL] BEEsc clamp = OFF "
                     "(SL may cross BEEsc → BEEsc disabled for that trade)")
    else:
        log.info("[Signal-SL] Disabled (use --signal-based-sl to enable)")
'''


# ═══════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════

def patch_01_config(content):
    if "SIGNAL_BASED_SL_ENABLED" in content:
        log("  [config] already present — skip")
        return content
    anchor = ('''    OPP_TP_MAX_AGE_BARS: int = 4             # عمر الإشارة المعاكسة
    OPP_TP_RESPECT_PARTIAL: bool = True      # لا تنقل TP تحت trigger partial
''')
    if anchor not in content:
        fail("[config] OPP_TP anchor not found")
    return must_replace(content, anchor, anchor + CONFIG_BLOCK, "config")


def patch_02_open_position_dataclass(content):
    if "_signal_sl_above_beesc: bool = False" in content:
        log("  [open_position] already present — skip")
        return content
    anchor = '''    partial_taken: bool = False      # [FIX 4]
    partial_pnl: float = 0.0         # [FIX 4] accumulated partial profit'''
    if anchor not in content:
        fail("[open_position] anchor not found")
    new = anchor + '''
    _signal_sl_above_beesc: bool = False   # [Signal-SL] BEEsc disabled flag'''
    return must_replace(content, anchor, new, "open_position")


def patch_03_insert_function(content):
    if "def _maybe_update_sl_from_signal(" in content:
        log("  [function] already present — skip")
        return content
    anchor = '''    return float(tp_new)

# ═══════════════════════════════════════════════════════════════
'''
    if anchor not in content:
        fail("[function] _apply_breakeven_escape end anchor not found")
    new = '''    return float(tp_new)
''' + FUNCTION_BLOCK + "\n"
    return must_replace(content, anchor, new, "function")


def patch_04_advance_beesc_check(content):
    if "# [Signal-SL] skip BEEsc if SL already above" in content:
        log("  [advance-beesc] already present — skip")
        return content
    anchor = '''        # ══ [BREAKEVEN ESCAPE — Price Trigger] ══
        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                and not getattr(pos, '_be_esc_done', False)
                and pos.sl_dist_initial > 0):'''
    if anchor not in content:
        fail("[advance-beesc] anchor not found")
    new = '''        # ══ [BREAKEVEN ESCAPE — Price Trigger] ══
        # [Signal-SL] skip BEEsc if SL already above (Signal-SL took priority)
        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                and not getattr(pos, '_be_esc_done', False)
                and not getattr(pos, '_signal_sl_above_beesc', False)
                and pos.sl_dist_initial > 0):'''
    return must_replace(content, anchor, new, "advance-beesc")


def patch_05_simulate_portfolio_integration(content):
    if "[SIGNAL-SL] رفع SL من إشارة جديدة (نفس الاتجاه) ══\n        if (getattr(CFG, 'SIGNAL_BASED_SL_ENABLED', False)" in content:
        log("  [simulate_portfolio] already present — skip")
        return content
    anchor = '''        # ══ [BREAKEVEN ESCAPE — Signal Trigger] ══
        if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                and sig.symbol in open_pos):'''
    if anchor not in content:
        fail("[simulate_portfolio] BEEsc signal-trigger anchor not found")
    new = BACKTEST_INTEGRATION + anchor
    return must_replace(content, anchor, new, "simulate_portfolio")


def patch_06_run_live_beesc_check(content):
    if "# [Signal-SL] skip BEEsc if SL already above" in content:
        log("  [run_live-beesc] already present — skip")
        return content
    anchor = '''                # ══ [BREAKEVEN ESCAPE — Price Trigger — Live] ══
                if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                        and not pos.get('_be_esc_done', False)
                        and float(pos.get('sl_dist_initial', 0)) > 0):'''
    if anchor not in content:
        fail("[run_live-beesc] anchor not found")
    new = '''                # ══ [BREAKEVEN ESCAPE — Price Trigger — Live] ══
                # [Signal-SL] skip BEEsc if SL already above
                if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                        and not pos.get('_be_esc_done', False)
                        and not pos.get('_signal_sl_above_beesc', False)
                        and float(pos.get('sl_dist_initial', 0)) > 0):'''
    return must_replace(content, anchor, new, "run_live-beesc")


def patch_07_run_live_integration(content):
    if "[SIGNAL-SL] رفع SL من إشارة جديدة (نفس الاتجاه) ══\n                if (getattr(CFG, 'SIGNAL_BASED_SL_ENABLED', False)" in content:
        log("  [run_live] already present — skip")
        return content
    anchor = '''                for sig in reversed(sigs):
                    sym = sig.symbol
                    if sym in open_pos_live: continue'''
    if anchor not in content:
        fail("[run_live] sigs loop anchor not found")
    new = LIVE_INTEGRATION + anchor
    return must_replace(content, anchor, new, "run_live")


def patch_08_cli_flags(content):
    if 'p.add_argument("--signal-based-sl"' in content:
        log("  [cli] already present — skip")
        return content
    anchor = '''    p.add_argument("--opp-tp-max-age-bars", type=int, default=None,
                   help="Max age of opposite signal in bars (default 4)")
'''
    if anchor not in content:
        fail("[cli] --opp-tp-max-age-bars anchor not found")
    return must_replace(content, anchor, anchor + CLI_FLAGS, "cli")


def patch_09_argparse(content):
    if 'CFG.SIGNAL_BASED_SL_ENABLED = True' in content:
        log("  [argparse] already present — skip")
        return content
    anchor = '''    else:
        log.info("[OppTP] Opposite-Signal Adaptive TP DISABLED")
'''
    if anchor not in content:
        fail("[argparse] --opp-tp handling anchor not found")
    return must_replace(content, anchor, anchor + ARGPARSE_BLOCK, "argparse")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose

    path = args.target
    if not os.path.exists(path):
        fail(f"File not found: {path}")

    content = open(path, "r", encoding="utf-8").read()

    if args.force and content.startswith(MARKER + "\n"):
        content = content[len(MARKER) + 1:]
        log("  removed existing marker for re-apply")

    if MARKER in content and not args.force:
        log("Signal-Based SL already applied. Use --force to re-apply.")
        return 0

    ok, err = verify_syntax(content, "PRE")
    if not ok:
        fail(f"File has syntax errors: {err}")

    log(f"File: {path} ({len(content)} chars, {content.count(chr(10))} lines)")

    if not args.dry_run:
        backup(path)

    try:
        content = patch_01_config(content)
        content = patch_02_open_position_dataclass(content)
        content = patch_03_insert_function(content)
        content = patch_04_advance_beesc_check(content)
        content = patch_05_simulate_portfolio_integration(content)
        content = patch_06_run_live_beesc_check(content)
        content = patch_07_run_live_integration(content)
        content = patch_08_cli_flags(content)
        content = patch_09_argparse(content)

        content = MARKER + "\n" + content

        ok, err = verify_syntax(content, "POST")
        if not ok:
            fail(f"Result has syntax errors: {err}")

        if args.dry_run:
            log("DRY RUN: syntax OK. Would write to file.")
            return 0

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
        log(f"Saved: {path}  ({content.count(chr(10))} lines)")
        log("=" * 60)
        log("Signal-Based SL applied successfully.")
        log("")
        log("Default: OFF (behavior unchanged).")
        log("")
        log("To enable, add to your run command:")
        log("  --signal-based-sl")
        log("")
        log("Recommended with:")
        log("  --tp-mult 3 --sl-widen-mult 2.5")
        log("  (Signal-SL is more effective with tighter TP and wider SL)")
        log("")
        log("Optional tuning:")
        log("  --signal-sl-score-ratio 1.5         # min score ratio (default 1.5)")
        log("  --signal-sl-min-improvement 0.005   # min SL improvement (default 0.5%)")
        log("  --signal-sl-protect-profit          # only above entry (BUY)")
        log("  --signal-sl-clamp-beesc             # clamp to BEEsc level")
        log("=" * 60)
        return 0

    except SystemExit:
        raise
    except Exception as e:
        log(f"FAILED: {e}", "FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
