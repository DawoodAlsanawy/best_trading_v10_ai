#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_trail_subbars_only.py — Sub-Bar-Gated Trailing SL (Live Parity)
======================================================================
المشكلة:
    في Live مع --no-dynamic-trail (trailing fixed distance)، الـ SL
    يُحدَّث على كل ticker (كل ~5s) — يمكن أن يتغيّر عدة مرات داخل نفس
    الشمعة الفرعية. في Backtest، الـ SL يُحدَّث فقط على sub-bar close.

    هذا يكسر parity، ويعطي Live سلوكاً "أكثر عدوانية" من Backtest.

الحل (3 إصلاحات):
    1. auto-enable TRAIL_USE_SUBBARS_ONLY=True عند استخدام
       --no-dynamic-trail في live/testnet
    2. إصلاح حساب peak: في sub-bar mode، استخدم _hi/_lo فقط
       (بدون ticker) — parity دقيق مع backtest
    3. gate تحديث SL: لا يُحدَّث إلا عند إغلاق sub-bar جديد
       (tracked via _trail_last_update_sub_ts)

Backward compatible 100%:
    - بدون --no-dynamic-trail (أو في backtest): سلوك قديم محفوظ
    - Legacy trailing mode (TRAIL_USE_SUBBARS_ONLY=False): محفوظ

الاستخدام:
    python3 apply_trail_subbars_only.py --dry-run --verbose
    python3 apply_trail_subbars_only.py

    # ثم في التشغيل:
    --no-dynamic-trail     # يُفعّل تلقائياً sub-bar gating في live
"""

import ast, os, shutil, sys
from datetime import datetime

MARKER = "# [TRAIL-SUBBARS-ONLY-APPLIED]"
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
    bak = f"{path}.bak_trail_sb_{ts}"
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
             f"expected: {old[:150]!r}")
    if n > 1:
        fail(f"[{label}] ambiguous ({n} matches)")
    vlog(f"    [{label}] replaced ({len(old)}->{len(new)} chars)")
    return content.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════
# NEW TRAILING BLOCK (sub-bar-gated)
# ═══════════════════════════════════════════════════════════════

NEW_TRAILING_BLOCK = '''                # ── Trailing SL (dynamic σ-scaled) ──
                # [GATE] يُشغّل Trailing فقط إذا كان TRAIL_ENABLED=True.
                # [SUB-BAR-GATE] عند TRAIL_USE_SUBBARS_ONLY=True:
                #   • SL يُحدَّث فقط عند إغلاق sub-bar جديد
                #   • peak يُحسب من _hi/_lo (sub-bar) فقط، بلا ticker
                #   • مطابق تماماً لسلوك الـ backtest
                if not ex and getattr(CFG, 'TRAIL_ENABLED', True):
                    _use_subbars_trail = bool(getattr(
                        CFG, 'TRAIL_USE_SUBBARS_ONLY', False))
                    _allow_trail_update = True
                    _cur_sub_ts_t = 0
                    if _use_subbars_trail:
                        _cur_sub_ts_t = int(pos.get('_last_sub_ts', 0))
                        _last_upd_ts_t = int(
                            pos.get('_trail_last_update_sub_ts', -1))
                        if _cur_sub_ts_t == 0 or _cur_sub_ts_t <= _last_upd_ts_t:
                            _allow_trail_update = False
                    
                    if _allow_trail_update:
                        entry_px = float(pos['entry'])
                        _sl_before = float(pos['sl'])
                        _td = float(pos.get('trail_dist_frac',
                                            CFG.TRAIL_DISTANCE))
                        _sl_dist_init = float(
                            pos.get('sl_dist_initial', 0) or 0)
                        _sl_frac_init = (_sl_dist_init / entry_px
                                         if entry_px > 0 and _sl_dist_init > 0
                                         else 0.01)
                        _act_at_r = float(getattr(
                            CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
                        _ta = _sl_frac_init * _act_at_r
                        
                        if pos['action'] == "BUY":
                            cur_peak = float(pos.get('peak_price', entry_px))
                            if _use_subbars_trail:
                                _cand_peak = float(
                                    pos.get('_hi', entry_px) or entry_px)
                            else:
                                _cand_peak = max(
                                    float(price),
                                    float(pos.get('_hi', entry_px)),
                                )
                            if _cand_peak > cur_peak:
                                pos['peak_price'] = _cand_peak
                                cur_peak = _cand_peak
                            _mfe = (cur_peak - entry_px) / entry_px
                        else:
                            cur_peak = float(pos.get('peak_price', entry_px))
                            if _use_subbars_trail:
                                _cand_peak = float(
                                    pos.get('_lo', entry_px) or entry_px)
                            else:
                                _cand_peak = min(
                                    float(price),
                                    float(pos.get('_lo', entry_px) or price),
                                )
                            if _cand_peak < cur_peak or cur_peak == entry_px:
                                pos['peak_price'] = _cand_peak
                                cur_peak = _cand_peak
                            _mfe = (entry_px - cur_peak) / entry_px
                        
                        if _mfe >= _ta:
                            if pos['action'] == "BUY":
                                new_sl = cur_peak * (1.0 - _td)
                                if new_sl > pos['sl']:
                                    pos['sl'] = new_sl
                            else:
                                new_sl = cur_peak * (1.0 + _td)
                                if new_sl < pos['sl']:
                                    pos['sl'] = new_sl
                        
                        if (getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True)
                                and abs(float(pos['sl']) - _sl_before) > 1e-12):
                            try:
                                _sync_protective_orders(exchange, sym, pos)
                            except Exception as _e:
                                log.debug(f"[Prot] {sym} sync error: {_e}")
                        
                        if _use_subbars_trail:
                            pos['_trail_last_update_sub_ts'] = _cur_sub_ts_t
'''

# Anchor to find the old trailing block.
OLD_TRAILING_START = "                # ── Trailing SL (dynamic σ-scaled) ──\n"
OLD_TRAILING_END = "                # ── [FIX 4] Partial TP ──\n"


# ═══════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════

def patch_01_argparse(content):
    """Auto-enable TRAIL_USE_SUBBARS_ONLY when --no-dynamic-trail in live."""
    if "# [SUB-BAR-GATE] Auto-enable" in content:
        log("  [argparse] already present — skip")
        return content
    old = '''    if args.no_dynamic_trail:
        CFG.TRAIL_DYNAMIC = False
'''
    if old not in content:
        fail("[argparse] --no-dynamic-trail anchor not found")
    new = '''    if args.no_dynamic_trail:
        CFG.TRAIL_DYNAMIC = False
        # [SUB-BAR-GATE] Auto-enable sub-bar-only trailing in live/testnet
        # so live matches backtest (SL updates once per sub-bar close).
        if CFG.mode in ('live', 'testnet') and not CFG.TRAIL_USE_SUBBARS_ONLY:
            CFG.TRAIL_USE_SUBBARS_ONLY = True
            log.info(
                "[Trail] --no-dynamic-trail in live → "
                "TRAIL_USE_SUBBARS_ONLY=True (SL updates only on "
                "sub-bar close, parity with backtest)"
            )
'''
    return must_replace(content, old, new, "argparse")


def patch_02_trailing_block(content):
    """Replace the live trailing block with sub-bar-gated version."""
    if "# [SUB-BAR-GATE] عند TRAIL_USE_SUBBARS_ONLY=True:" in content:
        log("  [trailing-block] already present — skip")
        return content
    
    lines = content.split("\n")
    start_i = -1
    end_i = -1
    for i, line in enumerate(lines):
        if OLD_TRAILING_START.rstrip("\n") in line and start_i < 0:
            start_i = i
        if (OLD_TRAILING_END.rstrip("\n") in line
                and start_i >= 0 and end_i < 0):
            end_i = i
            break
    
    if start_i < 0:
        fail("[trailing-block] start anchor not found "
             "('# ── Trailing SL (dynamic σ-scaled) ──')")
    if end_i < 0:
        fail("[trailing-block] end anchor not found "
             "('# ── [FIX 4] Partial TP ──')")
    
    vlog(f"    [trailing-block] replacing lines {start_i+1}..{end_i} "
         f"({end_i - start_i} lines)")
    
    new_lines = lines[:start_i] + NEW_TRAILING_BLOCK.split("\n") + lines[end_i:]
    return "\n".join(new_lines)


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
        log("Sub-Bar Trailing already applied. Use --force to re-apply.")
        return 0

    ok, err = verify_syntax(content, "PRE")
    if not ok:
        fail(f"File has syntax errors: {err}")

    log(f"File: {path} ({len(content)} chars, {content.count(chr(10))} lines)")

    if not args.dry_run:
        backup(path)

    try:
        content = patch_01_argparse(content)
        content = patch_02_trailing_block(content)

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
        log("Sub-Bar Trailing applied.")
        log("")
        log("Default: UNCHANGED (no impact on existing runs).")
        log("")
        log("To enable sub-bar-only trailing in live, add:")
        log("  --no-dynamic-trail")
        log("")
        log("This auto-enables TRAIL_USE_SUBBARS_ONLY=True in live/testnet,")
        log("making SL updates happen ONLY on sub-bar close (e.g. 15m)")
        log("— matching backtest exactly.")
        log("")
        log("Note: requires --no-trailing NOT set (trailing must be enabled).")
        log("=" * 60)
        return 0

    except SystemExit:
        raise
    except Exception as e:
        log(f"FAILED: {e}", "FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
