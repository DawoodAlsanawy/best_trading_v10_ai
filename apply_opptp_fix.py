#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_opptp_fix.py
==================
Batch patcher for trading_2_live4_claude2_v4.py

Applies ONLY the OppTP Profit-Guard modifications:
    1. Config: add OPP_TP_REQUIRE_PROFIT
    2. _opp_tp_decide: add current_price param + profit guard
    3. _maybe_adapt_tp_backtest: pass current_price from ad.closes
    4. _maybe_adapt_tp_live: pass current_price from ad.closes
    5. CLI: add --opp-tp-allow-loss flag
    6. main() wiring: connect flag → CFG.OPP_TP_REQUIRE_PROFIT

Guarantees:
    * Idempotent — safe to run twice
    * Timestamped backup before writing
    * Syntax verified with ast.parse
    * Auto-rollback on any failure
    * Preserves line endings + UTF-8 (Arabic comments intact)

Usage:
    python3 apply_opptp_fix.py                    # apply
    python3 apply_opptp_fix.py --dry-run          # show plan only
    python3 apply_opptp_fix.py --check            # verify without writing
    python3 apply_opptp_fix.py --file PATH        # custom target
    python3 apply_opptp_fix.py --no-backup        # skip backup (DANGER)
"""

import argparse
import ast
import os
import re
import shutil
import sys
import time
from pathlib import Path

DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def _read_file(path: Path) -> str:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write_file(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def _syntax_ok(text: str) -> tuple[bool, str]:
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
    """(start, end) of a top-level function, or None."""
    m = re.search(rf"^def {re.escape(func_name)}\(", text, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    rest = text[start + 1:]
    nxt = re.search(r"\n(?=def |class |# ══|\Z)", rest)
    end = (start + 1 + nxt.start() + 1) if nxt else len(text)
    return (start, end)


# ═══════════════════════════════════════════════════════════════
#  New code blocks
# ═══════════════════════════════════════════════════════════════

CONFIG_OLD = """    OPP_TP_ENABLED: bool = False
    OPP_TP_SCORE_MULT: float = 1.20          # score_opp ≥ 1.2 × score_entry
    OPP_TP_MIN_PROFIT_R: float = 0.5         # ربح أدنى مضمون بوحدات R
    OPP_TP_MIN_DELTA_R: float = 0.3          # تحسّن أدنى لنقل TP
    OPP_TP_MAX_AGE_BARS: int = 4             # عمر الإشارة المعاكسة
    OPP_TP_RESPECT_PARTIAL: bool = True      # لا تنقل TP تحت trigger partial
"""

CONFIG_NEW = """    OPP_TP_ENABLED: bool = False
    OPP_TP_SCORE_MULT: float = 1.20          # score_opp ≥ 1.2 × score_entry
    OPP_TP_MIN_PROFIT_R: float = 0.5         # ربح أدنى مضمون بوحدات R
    OPP_TP_MIN_DELTA_R: float = 0.3          # تحسّن أدنى لنقل TP
    OPP_TP_MAX_AGE_BARS: int = 4             # عمر الإشارة المعاكسة
    OPP_TP_RESPECT_PARTIAL: bool = True      # لا تنقل TP تحت trigger partial
    # ══ [OPP-TP-PROFIT-GUARD] ══
    # True  → لا يعمل إلا والسعر في منطقة الربح
    # False → يعمل أيضاً في منطقة الخسارة (سلوك قديم)
    # يُضبط عبر --opp-tp-allow-loss
    OPP_TP_REQUIRE_PROFIT: bool = True
"""


FUNC_DECIDE_NEW = '''def _opp_tp_decide(action_pos: str, entry: float, sl_dist0: float,
                   tp_old: float, partial_taken: bool,
                   entry_ci: int,
                   sig_opp, current_ci: int,
                   current_price=None):
    """
    Pure decision function. Returns (new_tp: float | None, reason: str).

    [OPP-TP-PROFIT-GUARD] الافتراضي: يعمل فقط والسعر في منطقة الربح.
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

    # ════════════════════════════════════════════════════════════════
    # [OPP-TP-PROFIT-GUARD] فقط في منطقة الربح (افتراضي)
    # ════════════════════════════════════════════════════════════════
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
    else:  # SELL
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

        # ── current_price = close of the opposite signal's bar ──
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


FUNC_LIVE_NEW = '''def _maybe_adapt_tp_live(pos: dict, sig_opp, ad, exchange) -> bool:
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

        # ── current_price = close of last CLOSED bar ──
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


CLI_OLD = '''    p.add_argument("--opp-tp", action="store_true",
                   help="Enable adaptive TP: when an opposite signal "
                        "appears on the same symbol, move the open "
                        "position's TP to the opposite's tunnel entry")
'''

CLI_NEW = '''    p.add_argument("--opp-tp", action="store_true",
                   help="Enable adaptive TP: when an opposite signal "
                        "appears on the same symbol, move the open "
                        "position's TP to the opposite's tunnel entry")
    p.add_argument("--opp-tp-allow-loss", action="store_true",
                   help="[OppTP] Allow the adaptive TP to fire even when "
                        "the position is in loss zone. Default: only in "
                        "profit zone (safer -- protection of profit region)")
'''


WIRING_OLD = '''    if args.opp_tp:
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
'''

WIRING_NEW = '''    if args.opp_tp:
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
'''


# ═══════════════════════════════════════════════════════════════
#  Patch definitions
# ═══════════════════════════════════════════════════════════════

PATCHES = [
    {
        "name": "Config: OPP_TP_REQUIRE_PROFIT",
        "kind": "exact",
        "old": CONFIG_OLD,
        "new": CONFIG_NEW,
        "marker": "OPP_TP_REQUIRE_PROFIT: bool = True",
    },
    {
        "name": "Function: _opp_tp_decide",
        "kind": "function",
        "func": "_opp_tp_decide",
        "new": FUNC_DECIDE_NEW,
        "marker": "current_price=None):",
    },
    {
        "name": "Function: _maybe_adapt_tp_backtest",
        "kind": "function",
        "func": "_maybe_adapt_tp_backtest",
        "new": FUNC_BT_NEW,
        "marker": "current_price=_cur_px,",
    },
    {
        "name": "Function: _maybe_adapt_tp_live",
        "kind": "function",
        "func": "_maybe_adapt_tp_live",
        "new": FUNC_LIVE_NEW,
        "marker": "current_price=_cur_px,",
    },
    {
        "name": "CLI: --opp-tp-allow-loss",
        "kind": "exact",
        "old": CLI_OLD,
        "new": CLI_NEW,
        "marker": "--opp-tp-allow-loss",
    },
    {
        "name": "Wiring: OppTP flag",
        "kind": "exact",
        "old": WIRING_OLD,
        "new": WIRING_NEW,
        "marker": "if getattr(args, \"opp_tp_allow_loss\", False):",
    },
]


# ═══════════════════════════════════════════════════════════════
#  Apply logic
# ═══════════════════════════════════════════════════════════════

def _apply_exact(text, old, new, marker):
    if old in text:
        return text.replace(old, new, 1), "applied"
    if marker in text:
        return text, "already_applied"
    return text, "ANCHOR_NOT_FOUND"


def _apply_function(text, func, new_body, marker):
    rng = _find_function_range(text, func)
    if rng is None:
        return text, "FUNCTION_NOT_FOUND"
    s, e = rng
    if marker in text[s:e]:
        return text, "already_applied"
    return text[:s] + new_body.rstrip() + "\n\n" + text[e:], "applied"


def main():
    ap = argparse.ArgumentParser(
        description="Apply OppTP Profit-Guard patch to the trading bot."
    )
    ap.add_argument("--file", default=DEFAULT_TARGET,
                    help=f"Target file (default: {DEFAULT_TARGET})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would change; do not write")
    ap.add_argument("--check", action="store_true",
                    help="Only verify current state; never write")
    ap.add_argument("--no-backup", action="store_true",
                    help="Skip backup file creation (NOT recommended)")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        return 2

    print(f"[*] Target: {path}")
    print(f"[*] Size  : {path.stat().st_size:,} bytes")

    original = _read_file(path)
    ok, err = _syntax_ok(original)
    if not ok:
        print(f"[ERROR] Target file has syntax errors BEFORE patching: {err}",
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
                text, p["func"], p["new"], p["marker"]
            )
        else:
            status = f"UNKNOWN_KIND:{p['kind']}"
        results.append((p["name"], status))
        icon = {"applied": "✅",
                "already_applied": "⏭️",
                "ANCHOR_NOT_FOUND": "❌",
                "FUNCTION_NOT_FOUND": "❌"}.get(status, "⚠️")
        print(f"  {icon} {p['name']:42s} [{status}]")

    # Abort if any patch failed
    failed = [r for r in results if "NOT_FOUND" in r[1]]
    if failed:
        print(f"\n[ERROR] {len(failed)} patch(es) failed — nothing written.",
              file=sys.stderr)
        for name, st in failed:
            print(f"    • {name}: {st}", file=sys.stderr)
        print("\n[INFO] The file may have been edited manually since the "
              "previous patch. Search for the expected anchor text and "
              "patch manually.", file=sys.stderr)
        return 4

    if text == original:
        print("\n[OK] No changes needed — file already patched.")
        return 0

    # Syntax check on the new text
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
        print("[DRY-RUN] Would write {:,} bytes (delta: {:+,} bytes)".format(
            len(text.encode("utf-8")),
            len(text.encode("utf-8")) - len(original.encode("utf-8")),
        ))
        return 0

    # Backup + write
    if not args.no_backup:
        try:
            bak = _backup(path)
            print(f"[OK] Backup saved: {bak}")
        except Exception as e:
            print(f"[WARN] Backup failed: {e}", file=sys.stderr)
            return 6

    try:
        _write_file(path, text)
    except Exception as e:
        print(f"[ERROR] Write failed: {e}", file=sys.stderr)
        return 7

    print(f"[OK] Wrote {len(text.encode('utf-8')):,} bytes to {path}")
    print("\n═══ Summary ═══")
    n_applied = sum(1 for _, s in results if s == "applied")
    n_skipped = sum(1 for _, s in results if s == "already_applied")
    print(f"  {n_applied} applied, {n_skipped} skipped (already applied)")
    print("\nNext steps:")
    print("  1. Re-verify: python3 apply_opptp_fix.py --check")
    print("  2. Run bot : python3 trading_2_live4_claude2_v4.py "
          "--opp-tp [other args]")
    print("  3. Watch   : grep '\\[OppTP' bot.log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
