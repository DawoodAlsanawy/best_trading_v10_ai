#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch: SL Delay (grace window before exchange SL)
═════════════════════════════════════════════════════════════════════
يضيف نافذة سماح قبل وضع SL على البورصة.
- SL_DELAY_ENABLED = False (افتراضي - معطّل)
- SL_DELAY_SECONDS = 900 (15 دقيقة عند التفعيل)

عند التفعيل من CLI: --sl-delay-s 900
"""

import argparse
import os
import shutil
import sys
import time
from dataclasses import dataclass
from typing import List

DEFAULT_TARGET = "trading_2_live2_1.py"


def log(msg, level="INFO"):
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


# ═════════════════════════════════════════════════════════════════════
# F1 — Config fields
# ═════════════════════════════════════════════════════════════════════

FIX1_ANCHOR = '''    SELL_MAJOR_PAIRS: Tuple = ("BTC/USDT", "ETH/USDT",
                                "SOL/USDT", "BNB/USDT")

CFG = Config()'''

FIX1_CONTENT = '''    SELL_MAJOR_PAIRS: Tuple = ("BTC/USDT", "ETH/USDT",
                                "SOL/USDT", "BNB/USDT")

    # ══ [SL-DELAY] نافذة سماح قبل وضع SL على البورصة ══
    # عند True: لا يُوضع SL على البورصة حتى تمر SL_DELAY_SECONDS
    # من لحظة لمس سعر الدخول. TP يُوضع فوراً. المراقبة اللحظية
    # في Live (client-side) تبقى تعمل.
    # CLI: --sl-delay-s 900 لتفعيل 15 دقيقة.
    SL_DELAY_ENABLED: bool = False
    SL_DELAY_SECONDS: int = 900

CFG = Config()'''

FIX1_IDEM = "[SL-DELAY] نافذة سماح قبل وضع SL على البورصة"


# ═════════════════════════════════════════════════════════════════════
# F2 — _place_protective_orders: skip SL during delay
# ═════════════════════════════════════════════════════════════════════

FIX2_ANCHOR = '''        # ══════════════════════════════════════════════════════════════
        # SL — place only if missing
        # ══════════════════════════════════════════════════════════════
        if not placed['sl']:'''

FIX2_CONTENT = '''        # ══════════════════════════════════════════════════════════════
        # SL — place only if missing
        # [SL-DELAY] إذا كنا داخل نافذة السماح، نأجل وضع SL
        # ══════════════════════════════════════════════════════════════
        _sl_delay_enabled = bool(getattr(CFG, 'SL_DELAY_ENABLED', False))
        _sl_delay_s = int(getattr(CFG, 'SL_DELAY_SECONDS', 900))
        _entry_ts_pos = float(pos.get('entry_ts') or 0.0)
        _now_pos = time.time()
        if _sl_delay_enabled and _entry_ts_pos > 0.0:
            _delay_rem = _sl_delay_s - (_now_pos - _entry_ts_pos)
        else:
            _delay_rem = 0.0
        _sl_delay_active = _delay_rem > 0.0

        if _sl_delay_active:
            log.info(
                f"[SL-Delay] {sym} SL placement deferred -- "
                f"{int(_delay_rem)}s remaining in grace window"
            )
            pos['_sl_delay_pending'] = True
        elif not placed['sl']:'''

FIX2_IDEM = "[SL-Delay]"

# Separate small fix: don't fail if SL was skipped due to delay
FIX3_ANCHOR = '''        _ok = (placed['sl'] and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if _ok:
            return True
        log.warning(f"[Prot] {sym} incomplete: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return _ok'''

FIX3_CONTENT = '''        # [SL-DELAY] SL is "effectively OK" if either placed OR deferred
        _sl_effectively_ok = placed['sl'] or _sl_delay_active
        _ok = (_sl_effectively_ok and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if _ok:
            if _sl_delay_active:
                log.debug(f"[Prot] {sym} TP placed, SL deferred "
                          f"by SL-DELAY")
            return True
        log.warning(f"[Prot] {sym} incomplete: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return _ok'''

FIX3_IDEM = "[SL-DELAY] SL is \"effectively OK\""


# ═════════════════════════════════════════════════════════════════════
# F4 — _promote_pending_to_position: don't set _prot_last_sl during delay
# ═════════════════════════════════════════════════════════════════════

FIX4_ANCHOR = '''    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        try:
            _ok = _place_protective_orders(exchange, sym, open_pos_live[sym])
            if _ok:
                open_pos_live[sym]['_prot_last_sl'] = float(adapted_sl)
                open_pos_live[sym]['_prot_last_tp'] = float(adapted_tp)
            else:
                log.warning(f"[Prot] {sym} protective orders not placed — "
                            f"bot will monitor manually")
        except Exception as _e:
            log.warning(f"[Prot] {sym} placement error: {_e}")

    return True'''

FIX4_CONTENT = '''    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        try:
            _ok = _place_protective_orders(exchange, sym, open_pos_live[sym])
            # [SL-DELAY] لا نُسجّل _prot_last_sl إذا كان SL مؤجلاً
            _in_delay = bool(
                open_pos_live[sym].get('_sl_delay_pending', False)
            )
            if _ok:
                if not _in_delay:
                    open_pos_live[sym]['_prot_last_sl'] = float(adapted_sl)
                open_pos_live[sym]['_prot_last_tp'] = float(adapted_tp)
            else:
                log.warning(f"[Prot] {sym} protective orders not placed — "
                            f"bot will monitor manually")
        except Exception as _e:
            log.warning(f"[Prot] {sym} placement error: {_e}")

    return True'''

FIX4_IDEM = "[SL-DELAY] لا نُسجّل _prot_last_sl إذا كان SL مؤجلاً"


# ═════════════════════════════════════════════════════════════════════
# F5 — _lv_ensure_protection: skip during delay, retry after
# ═════════════════════════════════════════════════════════════════════

FIX5_ANCHOR = '''def _lv_ensure_protection(exchange, sym, pos, now) -> None:
    # (re)place broker-side SL/TP whenever they are missing, stale vs pos['sl'],
    # or (every 5 min) not found on the exchange
    if not getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        return
    last = pos.get('_prot_last_sl')'''

FIX5_CONTENT = '''def _lv_ensure_protection(exchange, sym, pos, now) -> None:
    # (re)place broker-side SL/TP whenever they are missing, stale vs pos['sl'],
    # or (every 5 min) not found on the exchange
    if not getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        return

    # [SL-DELAY] داخل نافذة السماح: لا نضع SL، ونُصفّر _prot_last_sl
    # حتى يُعاد المحاولة بعد انتهاء النافذة.
    _sl_delay_on = bool(getattr(CFG, 'SL_DELAY_ENABLED', False))
    _sl_delay_s = int(getattr(CFG, 'SL_DELAY_SECONDS', 900))
    _entry_ts_pos = float(pos.get('entry_ts') or 0.0)
    if _sl_delay_on and _entry_ts_pos > 0.0:
        _rem = _sl_delay_s - (now - _entry_ts_pos)
        if _rem > 0:
            pos['_prot_last_sl'] = None
            pos['_sl_delay_pending'] = True
            return
        elif pos.get('_sl_delay_pending'):
            log.info(f"[SL-Delay] {sym} grace window expired -- "
                     f"placing SL now")
            pos['_sl_delay_pending'] = False

    last = pos.get('_prot_last_sl')'''

FIX5_IDEM = "[SL-Delay] {sym} grace window expired"


# ═════════════════════════════════════════════════════════════════════
# F6 — _advance (backtest): skip SL check during delay bars
# ═════════════════════════════════════════════════════════════════════

FIX6_ANCHOR = '''    def _check_sl_tp(high, low, close_px, fi):
        """Return ('SL'|'TP'|None, price). SL before TP when both hit."""
        if sig.action == "BUY":
            sl_trig = trail_sl * (1.0 - pen_frac)
            tp_trig = sig.tp1 * (1.0 + pen_frac)
            sl_hit = low <= sl_trig
            tp_hit = high >= tp_trig
        else:
            sl_trig = trail_sl * (1.0 + pen_frac)
            tp_trig = sig.tp1 * (1.0 - pen_frac)
            sl_hit = high >= sl_trig
            tp_hit = low <= tp_trig'''

FIX6_CONTENT = '''    def _check_sl_tp(high, low, close_px, fi, sl_enabled=True):
        """Return ('SL'|'TP'|None, price). SL before TP when both hit."""
        if sig.action == "BUY":
            sl_trig = trail_sl * (1.0 - pen_frac)
            tp_trig = sig.tp1 * (1.0 + pen_frac)
            sl_hit = sl_enabled and (low <= sl_trig)
            tp_hit = high >= tp_trig
        else:
            sl_trig = trail_sl * (1.0 + pen_frac)
            tp_trig = sig.tp1 * (1.0 - pen_frac)
            sl_hit = sl_enabled and (high >= sl_trig)
            tp_hit = low <= tp_trig'''

FIX6_IDEM = "def _check_sl_tp(high, low, close_px, fi, sl_enabled=True):"


# Compute delay bars once per _advance call
FIX7_ANCHOR = '''    pen_frac = CFG.FILL_PENETRATION_BPS * 1e-4 if CFG.FILL_APPLY_TO_EXITS else 0.0
    _use_sub = (ad.sub_highs is not None
                and ad.sub_lows is not None
                and ad.sub_per_main >= 2)'''

FIX7_CONTENT = '''    pen_frac = CFG.FILL_PENETRATION_BPS * 1e-4 if CFG.FILL_APPLY_TO_EXITS else 0.0
    _use_sub = (ad.sub_highs is not None
                and ad.sub_lows is not None
                and ad.sub_per_main >= 2)

    # [SL-DELAY] في الباكتست: نمنع فحص SL لأول _sl_delay_bars شمعة
    _sl_delay_enabled = bool(getattr(CFG, 'SL_DELAY_ENABLED', False))
    _sl_delay_s = int(getattr(CFG, 'SL_DELAY_SECONDS', 900))
    _tf_sec_b = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
    _sl_delay_bars = (
        max(1, int(np.ceil(_sl_delay_s / _tf_sec_b)))
        if _sl_delay_enabled else 0
    )'''

FIX7_IDEM = "# [SL-DELAY] في الباكتست: نمنع فحص SL"


# Update the sub-bar call site
FIX8_ANCHOR = '''                # SL / TP check on sub-bar
                res, px = _check_sl_tp(s_high, s_low, p, fi)'''

FIX8_CONTENT = '''                # SL / TP check on sub-bar
                # [SL-DELAY] compute whether SL is enabled for this bar
                _bars_since_entry = cidx - pos.entry_ci
                _sl_enabled_here = (_bars_since_entry >= _sl_delay_bars)
                res, px = _check_sl_tp(s_high, s_low, p, fi,
                                       sl_enabled=_sl_enabled_here)'''

FIX8_IDEM = "_sl_enabled_here = (_bars_since_entry >= _sl_delay_bars)"


# Update the main-bar call site
FIX9_ANCHOR = '''            res, px = _check_sl_tp(high, low, p, fi)
            if res == "SL":
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return px, "Emergency SL", cidx
            if res == "TP":
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return px, "Hard TP", cidx'''

FIX9_CONTENT = '''            # [SL-DELAY] respect grace window in main-bar mode too
            _bars_since_entry = cidx - pos.entry_ci
            _sl_enabled_here = (_bars_since_entry >= _sl_delay_bars)
            res, px = _check_sl_tp(high, low, p, fi,
                                   sl_enabled=_sl_enabled_here)
            if res == "SL":
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return px, "Emergency SL", cidx
            if res == "TP":
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return px, "Hard TP", cidx'''

FIX9_IDEM = "# [SL-DELAY] respect grace window in main-bar mode too"


# ═════════════════════════════════════════════════════════════════════
# F10 — CLI flags
# ═════════════════════════════════════════════════════════════════════

FIX10_ANCHOR = '''    p.add_argument("--no-apex", action="store_true",
                   help="Disable Apex exit")'''

FIX10_CONTENT = '''    p.add_argument("--no-apex", action="store_true",
                   help="Disable Apex exit")
    p.add_argument("--sl-delay-s", type=int, default=None,
                   help="Delay exchange SL placement by N seconds "
                        "after entry (e.g. 900 = 15 min). 0 disables.")'''

FIX10_IDEM = 'p.add_argument("--sl-delay-s", type=int, default=None,'


FIX11_ANCHOR = '''    if getattr(args, "no_apex", False):
        CFG.APEX_ENABLED = False
        log.info("[Ablation] APEX DISABLED")'''

FIX11_CONTENT = '''    if getattr(args, "no_apex", False):
        CFG.APEX_ENABLED = False
        log.info("[Ablation] APEX DISABLED")

    # [SL-DELAY] CLI wiring
    if getattr(args, "sl_delay_s", None) is not None:
        _v = int(args.sl_delay_s)
        if _v > 0:
            CFG.SL_DELAY_ENABLED = True
            CFG.SL_DELAY_SECONDS = _v
            log.info(f"[SL-Delay] ENABLED -- SL deferred by {_v}s "
                     f"({_v/60.0:.1f} min) after entry")
        else:
            CFG.SL_DELAY_ENABLED = False
            log.info("[SL-Delay] disabled via --sl-delay-s 0")'''

FIX11_IDEM = "[SL-Delay] CLI wiring"


# ═════════════════════════════════════════════════════════════════════

@dataclass
class Fix:
    name: str
    anchor: str
    content: str
    idempotency: str
    required: bool = True


FIXES: List[Fix] = [
    Fix("F1_Config", FIX1_ANCHOR, FIX1_CONTENT, FIX1_IDEM, True),
    Fix("F2_place_prot_SL", FIX2_ANCHOR, FIX2_CONTENT, FIX2_IDEM, True),
    Fix("F3_place_prot_final", FIX3_ANCHOR, FIX3_CONTENT, FIX3_IDEM, True),
    Fix("F4_promote", FIX4_ANCHOR, FIX4_CONTENT, FIX4_IDEM, True),
    Fix("F5_ensure_prot", FIX5_ANCHOR, FIX5_CONTENT, FIX5_IDEM, True),
    Fix("F6_check_sl_tp_sig", FIX6_ANCHOR, FIX6_CONTENT, FIX6_IDEM, True),
    Fix("F7_advance_delay_bars", FIX7_ANCHOR, FIX7_CONTENT, FIX7_IDEM, True),
    Fix("F8_subbar_call", FIX8_ANCHOR, FIX8_CONTENT, FIX8_IDEM, True),
    Fix("F9_mainbar_call", FIX9_ANCHOR, FIX9_CONTENT, FIX9_IDEM, True),
    Fix("F10_cli_arg", FIX10_ANCHOR, FIX10_CONTENT, FIX10_IDEM, True),
    Fix("F11_cli_wiring", FIX11_ANCHOR, FIX11_CONTENT, FIX11_IDEM, True),
]


def apply_fix(source, fix):
    if fix.idempotency and fix.idempotency in source:
        return source, "SKIP"
    if fix.anchor not in source:
        return source, "ANCHOR_NOT_FOUND"
    cnt = source.count(fix.anchor)
    if cnt > 1:
        return source, f"AMBIGUOUS({cnt})"
    return source.replace(fix.anchor, fix.content, 1), "OK"


def cmd_dry(source_path):
    source = read(source_path)
    log(f"Dry-run: {source_path} ({len(source)} chars)")
    current = source
    for fix in FIXES:
        new, status = apply_fix(current, fix)
        icon = "OK  " if status == "OK" else (
            "SKIP" if status == "SKIP" else "FAIL")
        print(f"  [{icon}] {fix.name:28s} -- {status}")
        if status == "OK":
            current = new
    try:
        compile(current, source_path, "exec")
        print("  [OK  ] syntax check")
    except SyntaxError as e:
        print(f"  [FAIL] syntax: {e}")
        return 1
    return 0


def cmd_apply(source_path):
    source = read(source_path)
    log(f"Applying: {source_path}")

    os.makedirs(".patches_backup", exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = f".patches_backup/{os.path.basename(source_path)}.{ts}.sldelay.bak"
    shutil.copy2(source_path, backup)
    log(f"Backup: {backup}")

    current = source
    ok = skip = fail = 0
    for fix in FIXES:
        new, status = apply_fix(current, fix)
        if status == "OK":
            current = new
            log(f"  [OK  ] {fix.name}")
            ok += 1
        elif status == "SKIP":
            log(f"  [SKIP] {fix.name}")
            skip += 1
        else:
            log(f"  [FAIL] {fix.name}: {status}", level="ERROR")
            fail += 1
            if fix.required:
                log("Rolling back", level="ERROR")
                return 2

    try:
        compile(current, source_path, "exec")
        log("Syntax OK")
    except SyntaxError as e:
        log(f"Syntax error: {e}", level="ERROR")
        return 3

    write(source_path, current)
    log(f"Applied={ok} Skipped={skip} Failed={fail}")
    log(f"Backup: {backup}")
    return 0


def cmd_verify(source_path):
    source = read(source_path)
    missing = 0
    for fix in FIXES:
        if fix.idempotency and fix.idempotency in source:
            print(f"  [OK  ] {fix.name}")
        else:
            print(f"  [MISS] {fix.name}")
            missing += 1
    return 0 if missing == 0 else 1


def cmd_rollback(source_path):
    bdir = ".patches_backup"
    if not os.path.isdir(bdir):
        log("No backup dir", level="ERROR")
        return 1
    base = os.path.basename(source_path)
    cands = sorted(
        [f for f in os.listdir(bdir)
         if f.startswith(base + ".") and f.endswith(".sldelay.bak")],
        reverse=True,
    )
    if not cands:
        log("No backups", level="ERROR")
        return 1
    src = os.path.join(bdir, cands[0])
    shutil.copy2(src, source_path)
    log(f"Restored from {src}")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default=DEFAULT_TARGET)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rollback", action="store_true")
    args = p.parse_args()

    if not os.path.exists(args.target):
        log(f"Not found: {args.target}", level="ERROR")
        return 1

    if args.rollback:
        return cmd_rollback(args.target)
    if args.verify_only:
        return cmd_verify(args.target)
    if args.dry_run:
        return cmd_dry(args.target)
    return cmd_apply(args.target)


if __name__ == "__main__":
    sys.exit(main())
