#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_smart_center_v4.py — Precision tuning
=============================================
يُطبّق 3 إصلاحات بنيوية بناءً على تحليل النتائج:

  1. Clamp (BEEsc) فقط قبل +1R — يمنح Smart Center حرية بعد إثبات الصفقة
  2. تجنب BROKEN(H) أثناء HEALTHY — BROKEN(H) يعمل فقط عندما H تضعف
     أصلاً (H < 0.55 في آخر 3 bars) لتجنب قطع صفقات سليمة
  3. Rescue threshold أكثر ذكاءً — يتطلب H < 0.50 (الحالة ضعيفة) قبل
     السماح لـ Rescue بالخروج

+ CLI flag جديد: --sc-broken-h إلى جانب --no-smart-center
+ CLI flag: --be-escape-move-r يُستخدم الآن فعلاً في clamp

الإصلاحات idempotent، آمنة على v3-fixed الحالي.
"""

import ast, os, shutil, sys
from datetime import datetime

V3_MARKER = "# [SMART-CENTER-MIGRATION-V3-FIXED-APPLIED]"
V4_MARKER = "# [SMART-CENTER-MIGRATION-V4-PRECISION]"
DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"
VERBOSE = False


def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)

def vlog(msg):
    if VERBOSE: log(msg, "DEBUG")

def fail(msg):
    log(msg, "FAIL"); raise SystemExit(1)

def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_v4_{ts}"
    shutil.copy2(path, bak)
    log(f"  نسخة احتياطية: {bak}")
    return bak

def verify_syntax(content, label=""):
    try:
        ast.parse(content); return True, ""
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
    if n == 0: fail(f"[{label}] anchor not found")
    if n > 1: fail(f"[{label}] ambiguous ({n})")
    vlog(f"    [{label}] replaced")
    return content.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════

def patch_01_clamp_before_1r(content):
    """Clamp فقط قبل +1R — أهم إصلاح."""
    if "# [V4-CLAMP-FIX]" in content:
        log("  [clamp-1r-fix] already applied — skip")
        return content
    old = '''        if bool(pos_snap.get('be_esc_armed', True)):
            kb = float(getattr(config, 'BREAKEVEN_ESCAPE_PRICE_MOVE_R', 0.30))
            buf = float(getattr(config, 'SC_BE_ESC_BUFFER', 0.001))
            if action == "BUY":
                lvl = entry - kb * sl_d0
                new_sl = min(new_sl, lvl * (1.0 - buf))
            else:
                lvl = entry + kb * sl_d0
                new_sl = max(new_sl, lvl * (1.0 + buf))'''
    new = '''        # ══ [V4-CLAMP-FIX] Clamp فقط قبل +1R — يمنح SC حرية بعد الإثبات ══
        if bool(pos_snap.get('be_esc_armed', True)) and mfe_R < 1.0:
            kb = float(getattr(config, 'BREAKEVEN_ESCAPE_PRICE_MOVE_R', 0.30))
            buf = float(getattr(config, 'SC_BE_ESC_BUFFER', 0.001))
            if action == "BUY":
                lvl = entry - kb * sl_d0
                new_sl = min(new_sl, lvl * (1.0 - buf))
            else:
                lvl = entry + kb * sl_d0
                new_sl = max(new_sl, lvl * (1.0 + buf))'''
    return must_replace(content, old, new, "clamp-before-1r")


def patch_02_broken_h_requires_weak(content):
    """BROKEN(H) يعمل فقط عندما H أصلاً ضعيف (وليس مجرد تقلب طبيعي)."""
    if "# [V4-BROKEN-H-STRICT]" in content:
        log("  [broken-h-strict] already applied — skip")
        return content
    old = '''    new_streak = (res['new_streak'] + 1) if H <= float(getattr(config, 'SC_BROKEN_THRESHOLD', 0.40)) else 0
    res['new_streak'] = new_streak
    struct_br = _structure_broken(ad, current_ci, entry_ci, action, config)
    if (new_streak >= int(getattr(config, 'SC_BROKEN_PERSIST_BARS', 2))
            or S_p > float(getattr(config, 'SC_PRICE_DIST_MAX', 3.0))
            or struct_br):'''
    new = '''    # ══ [V4-BROKEN-H-STRICT] BROKEN(H) يتطلب H < 0.55 ALSO ══
    # السبب: H قد تنخفض لـ 0.38 في تقلب طبيعي ثم ترتد. شرط إضافي: H
    # يجب أن تكون ضعيفة أصلاً (ميزة التقلب التاريخية قريبة أيضاً).
    _h_hist = []
    try:
        _h_hist = [ad.score[max(0, fi - k)] for k in range(1, 4)]
    except Exception:
        pass
    _really_weak = (H <= float(getattr(config, 'SC_BROKEN_THRESHOLD', 0.40))
                    and (not _h_hist or np.mean(_h_hist) <= 0.55))
    new_streak = (res['new_streak'] + 1) if _really_weak else 0
    res['new_streak'] = new_streak
    struct_br = _structure_broken(ad, current_ci, entry_ci, action, config)
    if (new_streak >= int(getattr(config, 'SC_BROKEN_PERSIST_BARS', 2))
            or S_p > float(getattr(config, 'SC_PRICE_DIST_MAX', 3.0))
            or struct_br):'''
    return must_replace(content, old, new, "broken-h-strict")


def patch_03_rescue_requires_weak_h(content):
    """Rescue فقط عندما H < 0.50 (الحالة ضعيفة)."""
    if "# [V4-RESCUE-WEAK-H]" in content:
        log("  [rescue-weak-h] already applied — skip")
        return content
    old = '''        if is_losing and bars_held >= 1:
            _mh_for_rescue = locals().get('_max_hold_eff',
                                            int(getattr(config, 'MAX_HOLD_BARS', 168)))
            ri = _compute_rescue_probability(ad, fi, action, entry, sl_cur, tp, price,
                                              bars_held, _mh_for_rescue,
                                              config, entry_fi)
            res['rescue_p'] = ri['P_rescue']
            if ri['error'] is None and ri['P_rescue'] < ri['threshold']:
                res['action'] = 'exit'; res['tier'] = 'RESCUE'
                res['reason'] = f"Rescue(P={ri['P_rescue']:.2f}<{ri['threshold']:.2f})"
                return res'''
    new = '''        # ══ [V4-RESCUE-WEAK-H] Rescue يتطلب H < 0.50 (وليس فقط الخسارة) ══
        _rescue_h_ok = (H <= float(getattr(config, 'SC_BROKEN_THRESHOLD', 0.40)) + 0.10)
        if is_losing and bars_held >= 1 and _rescue_h_ok:
            _mh_for_rescue = locals().get('_max_hold_eff',
                                            int(getattr(config, 'MAX_HOLD_BARS', 168)))
            ri = _compute_rescue_probability(ad, fi, action, entry, sl_cur, tp, price,
                                              bars_held, _mh_for_rescue,
                                              config, entry_fi)
            res['rescue_p'] = ri['P_rescue']
            if ri['error'] is None and ri['P_rescue'] < ri['threshold']:
                res['action'] = 'exit'; res['tier'] = 'RESCUE'
                res['reason'] = f"Rescue(P={ri['P_rescue']:.2f}<{ri['threshold']:.2f})"
                return res'''
    return must_replace(content, old, new, "rescue-weak-h")


def patch_04_trail_activation_lower(content):
    """تفعيل التريلينغ في HEALTHY عند +0.3R بدلاً من +0.5R."""
    if "# [V4-TRAIL-ACT-LOW]" in content:
        log("  [trail-act-low] already applied — skip")
        return content
    # Config change
    old_cfg = "    SC_ACTIVATE_R_HEALTHY: float = 0.5"
    new_cfg = "    SC_ACTIVATE_R_HEALTHY: float = 0.3   # [V4-TRAIL-ACT-LOW]"
    content = must_replace(content, old_cfg, new_cfg, "config-act-healthy")

    old_cfg2 = "    SC_HEALTHY_TRAIL_KAPPA: float = 3.0"
    new_cfg2 = "    SC_HEALTHY_TRAIL_KAPPA: float = 2.0   # [V4-TRAIL-ACT-LOW] أضيق من 3.0"
    return must_replace(content, old_cfg2, new_cfg2, "config-kappa-healthy")


def patch_05_cli_flags(content):
    """Add CLI flags for tuning."""
    if 'p.add_argument("--sc-broken-threshold"' in content:
        log("  [cli-sc-flags] already present — skip")
        return content
    old = '''    p.add_argument("--no-smart-center", action="store_true",
                   help="Disable Smart Center (fallback: no dynamic SL management)")'''
    new = '''    p.add_argument("--no-smart-center", action="store_true",
                   help="Disable Smart Center (fallback: no dynamic SL management)")
    p.add_argument("--sc-broken-threshold", type=float, default=None,
                   help="Override SC_BROKEN_THRESHOLD (default 0.40)")
    p.add_argument("--sc-rescue-floor", type=float, default=None,
                   help="Override SC_RESCUE_FLOOR (default 0.15)")
    p.add_argument("--sc-healthy-threshold", type=float, default=None,
                   help="Override SC_HEALTHY_THRESHOLD (default 0.65)")
    p.add_argument("--sc-kappa-healthy", type=float, default=None,
                   help="Override SC_HEALTHY_TRAIL_KAPPA (default 2.0 after v4)")
    p.add_argument("--sc-kappa-weak", type=float, default=None,
                   help="Override SC_WEAK_TRAIL_KAPPA (default 1.5)")'''
    return must_replace(content, old, new, "cli-sc-flags")


def patch_06_cli_argparse(content):
    """Add argparse handling for new CLI flags."""
    if 'CFG.SC_BROKEN_THRESHOLD = float(args.sc_broken_threshold)' in content:
        log("  [cli-argparse-sc] already present — skip")
        return content
    old = '''    if getattr(args, "no_smart_center", False):
        CFG.SMART_CENTER_ENABLED = False
        log.warning("[Ablation] SMART CENTER DISABLED — SL management fallback OFF")'''
    new = '''    if getattr(args, "no_smart_center", False):
        CFG.SMART_CENTER_ENABLED = False
        log.warning("[Ablation] SMART CENTER DISABLED — SL management fallback OFF")
    if getattr(args, "sc_broken_threshold", None) is not None:
        CFG.SC_BROKEN_THRESHOLD = float(args.sc_broken_threshold)
        log.info(f"[SC-v4] SC_BROKEN_THRESHOLD = {CFG.SC_BROKEN_THRESHOLD}")
    if getattr(args, "sc_rescue_floor", None) is not None:
        CFG.SC_RESCUE_FLOOR = float(args.sc_rescue_floor)
        log.info(f"[SC-v4] SC_RESCUE_FLOOR = {CFG.SC_RESCUE_FLOOR}")
    if getattr(args, "sc_healthy_threshold", None) is not None:
        CFG.SC_HEALTHY_THRESHOLD = float(args.sc_healthy_threshold)
        log.info(f"[SC-v4] SC_HEALTHY_THRESHOLD = {CFG.SC_HEALTHY_THRESHOLD}")
    if getattr(args, "sc_kappa_healthy", None) is not None:
        CFG.SC_HEALTHY_TRAIL_KAPPA = float(args.sc_kappa_healthy)
        log.info(f"[SC-v4] SC_HEALTHY_TRAIL_KAPPA = {CFG.SC_HEALTHY_TRAIL_KAPPA}")
    if getattr(args, "sc_kappa_weak", None) is not None:
        CFG.SC_WEAK_TRAIL_KAPPA = float(args.sc_kappa_weak)
        log.info(f"[SC-v4] SC_WEAK_TRAIL_KAPPA = {CFG.SC_WEAK_TRAIL_KAPPA}")'''
    return must_replace(content, old, new, "cli-argparse-sc")


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
    if not os.path.exists(path): fail(f"File not found: {path}")

    content = open(path, "r", encoding="utf-8").read()

    if V3_MARKER not in content:
        fail("v3-fixed marker not found — run apply_smart_center_v3.py first!")
    if V4_MARKER in content and not args.force:
        log("v4 already applied. Use --force to re-apply.")
        return 0

    ok, err = verify_syntax(content, "PRE-V4")
    if not ok: fail(f"Current file has syntax errors: {err}")

    log(f"File: {path} ({len(content)} chars, {content.count(chr(10))} lines)")

    if not args.dry_run: backup(path)

    try:
        content = patch_01_clamp_before_1r(content)
        content = patch_02_broken_h_requires_weak(content)
        content = patch_03_rescue_requires_weak_h(content)
        content = patch_04_trail_activation_lower(content)
        content = patch_05_cli_flags(content)
        content = patch_06_cli_argparse(content)

        content = V4_MARKER + "\n" + content

        ok, err = verify_syntax(content, "POST-V4")
        if not ok: fail(f"Result has syntax errors: {err}")

        if args.dry_run:
            log("DRY RUN: syntax OK. Would write to file.")
            return 0

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
        log(f"Saved: {path}  ({content.count(chr(10))} lines)")
        log("=" * 60)
        log("Migration v4 (Precision) complete.")
        log("")
        log("NEW flags available:")
        log("  --sc-broken-threshold FLOAT   (default 0.40)")
        log("  --sc-rescue-floor FLOAT       (default 0.15)")
        log("  --sc-healthy-threshold FLOAT  (default 0.65)")
        log("  --sc-kappa-healthy FLOAT      (default 2.0 after v4)")
        log("  --sc-kappa-weak FLOAT         (default 1.5)")
        log("=" * 60)
        return 0

    except SystemExit:
        raise
    except Exception as e:
        log(f"v4 FAILED: {e}", "FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
