#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_smart_center_v3.py — FIXED FINAL (v3.1)
==============================================
إصلاحات حرجة عن v3:
  • patch_06: SC guard بعد docstring (لا قبل إغلاقه) → يحل خطأ U+2192
  • patch_10: استبدال _smart_center_decision بالكامل (flash يستخدم
              current_ci لا fi → يحل 52.8% FlashCrash الكاذب)
  • patch_11: إضافة APEX_ENABLED check داخل check_thermodynamic_apex
              → --no-apex يعمل الآن
  • patch_12: effective_bars لـ MAX_HOLD_BARS (يحل مشكلة 4h)

كل patches idempotent.
"""

import ast, os, shutil, sys
from datetime import datetime

V2_MARKER = "# [SMART-CENTER-MIGRATION-V2-APPLIED]"
V3_MARKER = "# [SMART-CENTER-MIGRATION-V3-FIXED-APPLIED]"
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
    bak = f"{path}.bak_v3f_{ts}"
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
        fail(f"[{label}] anchor not found (0 matches)")
    if n > 1:
        fail(f"[{label}] ambiguous ({n} matches)")
    vlog(f"    [{label}] replaced")
    return content.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════

def patch_01_no_smart_center_flag(content):
    if 'p.add_argument("--no-smart-center"' in content:
        log("  [flag-no-smart-center] already present — skip")
        return content
    old = '''    p.add_argument("--no-apex", action="store_true",
                   help="Disable Apex exit")'''
    new = '''    p.add_argument("--no-apex", action="store_true",
                   help="Disable Apex exit")
    p.add_argument("--no-smart-center", action="store_true",
                   help="Disable Smart Center (fallback: no dynamic SL management)")'''
    return must_replace(content, old, new, "flag-no-smart-center")


def patch_02_no_smart_center_argparse(content):
    if 'if getattr(args, "no_smart_center", False):' in content:
        log("  [argparse-no-smart-center] already present — skip")
        return content
    old = '''    # [ABLATION-FLAGS]
    if getattr(args, "no_apex", False):
        CFG.APEX_ENABLED = False
        log.info("[Ablation] APEX DISABLED")
    if getattr(args, "no_partial", False):
        CFG.PARTIAL_TP_ENABLED = False
        log.info("[Ablation] PARTIAL_TP DISABLED")'''
    new = '''    # [ABLATION-FLAGS]
    if getattr(args, "no_apex", False):
        CFG.APEX_ENABLED = False
        log.info("[Ablation] APEX DISABLED")
    if getattr(args, "no_smart_center", False):
        CFG.SMART_CENTER_ENABLED = False
        log.warning("[Ablation] SMART CENTER DISABLED — SL management fallback OFF")
    if getattr(args, "no_partial", False):
        CFG.PARTIAL_TP_ENABLED = False
        log.info("[Ablation] PARTIAL_TP DISABLED")'''
    return must_replace(content, old, new, "argparse-no-smart-center")


def patch_03_lv_finalize_sc_fields(content):
    idx = content.find("def _lv_finalize_position(")
    if idx >= 0:
        be = content.find("\ndef ", idx + 10)
        block = content[idx:be if be > 0 else len(content)]
        if "pos.setdefault('_broken_streak', 0)" in block:
            log("  [lv_finalize-sc-fields] already present — skip")
            return content
    old = '''def _lv_finalize_position(exchange, sym, pos, ad=None) -> None:
    # make sure every live position record carries all fields the manager relies on
    try:
        pos.setdefault('_sym', sym)'''
    new = '''def _lv_finalize_position(exchange, sym, pos, ad=None) -> None:
    # make sure every live position record carries all fields the manager relies on
    try:
        pos.setdefault('_sym', sym)
        # ══ [SC-V3] ensure Smart Center fields exist ══
        pos.setdefault('_broken_streak', 0)
        pos.setdefault('_health', 0.5)
        pos.setdefault('_rescue_p', 1.0)
        if 'sigma_entry' not in pos or float(pos.get('sigma_entry') or 0) <= 0:
            _sc_sigma = 0.01
            if ad is not None:
                try:
                    _sc_ci = len(ad.closes) - 2
                    _sc_fi = max(0, min(_sc_ci - ad.feat_start,
                                        len(ad.E_therm) - 1))
                    _sc_s = float(ad.E_therm[_sc_fi])
                    if np.isfinite(_sc_s) and _sc_s > 1e-9:
                        _sc_sigma = _sc_s
                except Exception:
                    pass
            if _sc_sigma <= 1e-9:
                _sl_d = float(pos.get('sl_dist_initial') or 0)
                _e_px = float(pos.get('entry') or 1)
                if _e_px > 0 and _sl_d > 0:
                    _sc_sigma = _sl_d / _e_px / 3.0
            pos['sigma_entry'] = float(max(_sc_sigma, 0.001))'''
    return must_replace(content, old, new, "lv_finalize-sc-fields")


def patch_04_rev_finalize_sc_fields(content):
    idx = content.find("def _rev_finalize(")
    if idx >= 0:
        be = content.find("\ndef ", idx + 10)
        block = content[idx:be if be > 0 else len(content)]
        if '"sigma_entry": _sigma_entry' in block:
            log("  [rev_finalize-sc-fields] already applied — skip")
            return content
    old_td = '''    _sb = float(w.get("sigma_bar", 0.01))
    _td = float(np.clip(CFG.TRAIL_KAPPA * _sb,
                        CFG.TRAIL_MIN_FRAC, CFG.TRAIL_MAX_FRAC))
    _ta = float(np.clip(CFG.TRAIL_ACT_KAPPA * _sb,
                        CFG.TRAIL_ACT_MIN_FRAC, CFG.TRAIL_ACT_MAX_FRAC))
    if _ta <= _td:
        _ta = _td * 1.2'''
    new_td = '''    _sb = float(w.get("sigma_bar", 0.01))
    _sigma_entry = float(max(_sb, 0.001))'''
    content = must_replace(content, old_td, new_td, "rev_finalize-td-ta")
    old_f = '''        "trail_dist_frac": _td,
        "trail_activate_frac": _ta,
        "liq_price_estimated": _liq,
        "mmr": _mmr,
        "sl_dist_initial": float(abs(entry_px - new_sl)),'''
    new_f = '''        "sigma_entry": _sigma_entry,
        "_broken_streak": 0,
        "_health": 0.5,
        "_rescue_p": 1.0,
        "liq_price_estimated": _liq,
        "mmr": _mmr,
        "sl_dist_initial": float(abs(entry_px - new_sl)),'''
    return must_replace(content, old_f, new_f, "rev_finalize-fields")


def patch_05_live_peak_from_hi_lo(content):
    idx = content.find("def _smart_center_decision_live(")
    if idx >= 0:
        be = content.find("\ndef ", idx + 10)
        block = content[idx:be if be > 0 else len(content)]
        if "Peak from _hi/_lo (1m candles) for parity" in block:
            log("  [live-peak-hi-lo] already applied — skip")
            return content
    old = '''        if snap['action'] == "BUY":
            if price > snap['peak']:
                snap['peak'] = float(price); pos['peak_price'] = price
        else:
            if snap['peak'] == 0 or price < snap['peak']:
                snap['peak'] = float(price); pos['peak_price'] = price'''
    new = '''        # ══ [SC-V3] Peak from _hi/_lo (1m candles) for parity with backtest ══
        _sc_hi = float(pos.get('_hi', snap['peak']) or snap['peak'])
        _sc_lo = float(pos.get('_lo', snap['peak']) or snap['peak'])
        if snap['action'] == "BUY":
            _sc_cand = max(float(price), _sc_hi)
            if _sc_cand > snap['peak']:
                snap['peak'] = _sc_cand; pos['peak_price'] = _sc_cand
        else:
            _sc_cand = (min(float(price), _sc_lo)
                        if _sc_lo > 0 else float(price))
            if snap['peak'] == 0 or _sc_cand < snap['peak']:
                snap['peak'] = _sc_cand; pos['peak_price'] = _sc_cand'''
    return must_replace(content, old, new, "live-peak-hi-lo")


def patch_06_breakeven_sc_guard(content):
    """FIXED: place guard AFTER docstring, not inside it."""
    idx = content.find("def _lv_breakeven(")
    if idx >= 0:
        be = content.find("\ndef ", idx + 10)
        block = content[idx:be if be > 0 else len(content)]
        # Check the guard is already present AND not inside a bad docstring
        if ("if getattr(CFG, 'SMART_CENTER_ENABLED', True):\n        return"
                in block and "→ NO-OP" in block and
                '"""' in block and
                block.count('"""') == 2):
            log("  [breakeven-sc-guard] already applied correctly — skip")
            return content
    old = '''def _lv_breakeven(exchange, sym, pos, now) -> None:
    """
    Live twin of the backtest BREAKEVEN-SL.

    [SMART-BE] The exchange SL is read first. Behaviour:
      * Exchange SL at the same price as our target → NO-OP (do nothing)
      * Exchange SL at a different price            → cancel it, then
                                                      place the new SL
      * No exchange SL                              → place the new SL
    """
    if getattr(CFG, 'TRAIL_ENABLED', True) or not getattr(CFG, 'BREAKEVEN_ENABLED', True):
        return'''
    new = '''def _lv_breakeven(exchange, sym, pos, now) -> None:
    """
    Live twin of the backtest BREAKEVEN-SL.

    [SMART-BE] The exchange SL is read first. Behaviour:
      * Exchange SL at the same price as our target → NO-OP (do nothing)
      * Exchange SL at a different price            → cancel it, then
                                                      place the new SL
      * No exchange SL                              → place the new SL

    [SC-V3] Early return when Smart Center is enabled — SC handles
    SL movement (including a stricter breakeven via BEEsc clamp).
    """
    if getattr(CFG, 'SMART_CENTER_ENABLED', True):
        return
    if getattr(CFG, 'TRAIL_ENABLED', True) or not getattr(CFG, 'BREAKEVEN_ENABLED', True):
        return'''
    return must_replace(content, old, new, "breakeven-sc-guard")


def patch_07_print_report_sc_section(content):
    if "Smart Center Exits (v3)" in content:
        log("  [print-report-sc] already applied — skip")
        return content
    old = '''    print(f"\\n▶ توزيع أسباب الخروج")
    for r,c in sorted(m['exit_distribution'].items(), key=lambda x:-x[1]):
        print(f"   {r:25s}: {c:7,}  ({c/m['n_trades']*100:.1f}%)")'''
    new = '''    print(f"\\n▶ توزيع أسباب الخروج")
    for r,c in sorted(m['exit_distribution'].items(), key=lambda x:-x[1]):
        print(f"   {r:25s}: {c:7,}  ({c/m['n_trades']*100:.1f}%)")

    # ══ [SC-V3] Smart Center exit breakdown ══
    _sc_rescue = m.get('rescue_exits', 0)
    _sc_broken = m.get('broken_exits', 0)
    _sc_flash = m.get('flash_exits', 0)
    _sc_total = _sc_rescue + _sc_broken + _sc_flash
    if _sc_total > 0:
        print(f"\\n▶ Smart Center Exits (v3)")
        print(f"   Rescue exits    : {_sc_rescue:7,}  "
              f"({_sc_rescue/m['n_trades']*100:.1f}%)")
        print(f"   BROKEN exits    : {_sc_broken:7,}  "
              f"({_sc_broken/m['n_trades']*100:.1f}%)")
        print(f"   Flash exits     : {_sc_flash:7,}  "
              f"({_sc_flash/m['n_trades']*100:.1f}%)")
        print(f"   ─────────────────────────────────────")
        print(f"   Total SC exits  : {_sc_total:7,}  "
              f"({_sc_total/m['n_trades']*100:.1f}%)")'''
    return must_replace(content, old, new, "print-report-sc")


def patch_08_plot_results_sc_info(content):
    if "_sc_total_v3" in content:
        log("  [plot-results-sc] already applied — skip")
        return content
    old = '''    summ=(f"صفقات: {m['n_trades']:,}\\n"
          f"نجاح:  {m['win_rate']*100:.1f}%\\n"
          f"PF:    {m['profit_factor']:.2f}\\n"
          f"Sharpe:{m['sharpe_ratio']:.2f}\\n"
          f"MaxDD: {m['max_drawdown_pct']:.1f}%\\n"
          f"Topo:  {m['topo_exit_pct']:.1f}%\\n"
          f"TRI:   {m['tri_exit_pct']:.1f}%\\n"
          f"Opt:   {m['opt_entry_pct']:.1f}%\\n"
          f"T_avg: {m['avg_T_info']:.3f}\\n"
          f"r_avg: {m['avg_dynamic_risk']*100:.3f}%\\n"
          f"Slip:  ${m['total_slip']:,.0f}")'''
    new = '''    _sc_total_v3 = (m.get('rescue_exits', 0) + m.get('broken_exits', 0)
                    + m.get('flash_exits', 0))
    _sc_line = (f"\\nSC_v3: R{m.get('rescue_exits',0)} "
                f"B{m.get('broken_exits',0)} "
                f"F{m.get('flash_exits',0)}") if _sc_total_v3 > 0 else ""
    summ=(f"صفقات: {m['n_trades']:,}\\n"
          f"نجاح:  {m['win_rate']*100:.1f}%\\n"
          f"PF:    {m['profit_factor']:.2f}\\n"
          f"Sharpe:{m['sharpe_ratio']:.2f}\\n"
          f"MaxDD: {m['max_drawdown_pct']:.1f}%\\n"
          f"Topo:  {m['topo_exit_pct']:.1f}%\\n"
          f"TRI:   {m['tri_exit_pct']:.1f}%\\n"
          f"Opt:   {m['opt_entry_pct']:.1f}%\\n"
          f"T_avg: {m['avg_T_info']:.3f}\\n"
          f"r_avg: {m['avg_dynamic_risk']*100:.3f}%\\n"
          f"Slip:  ${m['total_slip']:,.0f}"
          f"{_sc_line}")'''
    return must_replace(content, old, new, "plot-results-sc")


def patch_09_startup_info(content):
    if "[SmartCenter v3]" in content:
        log("  [startup-sc-info] already applied — skip")
        return content
    old = '''    print("╔"+"═"*70+"╗")
    print(f"  [Level-1] Parallel: {CFG.PARALLEL_PROCESSING}  "
          f"Cache: {CFG.ASSET_CACHE_ENABLED}")'''
    new = '''    _sc_status = "ENABLED" if getattr(CFG, 'SMART_CENTER_ENABLED', True) else "DISABLED"
    log.info(f"[SmartCenter v3] {_sc_status}  "
             f"(Healthy={getattr(CFG,'SC_HEALTHY_THRESHOLD',0.65):.2f}, "
             f"Broken={getattr(CFG,'SC_BROKEN_THRESHOLD',0.40):.2f}, "
             f"Rescue={'ON' if getattr(CFG,'SC_RESCUE_ENABLED',True) else 'OFF'})")
    print("╔"+"═"*70+"╗")
    print(f"  [Level-1] Parallel: {CFG.PARALLEL_PROCESSING}  "
          f"Cache: {CFG.ASSET_CACHE_ENABLED}")
    print(f"  [SmartCenter v3] {_sc_status}")'''
    return must_replace(content, old, new, "startup-sc-info")


def patch_10_fix_flash_and_maxhold(content):
    """FIXED: replace whole _smart_center_decision with corrected version."""
    if "══ [SC-V3-FLASH-FIX] ══" in content:
        log("  [flash-maxhold-fix] already applied — skip")
        return content
    # The old function body (from v2)
    old_flash = '''    try:
        sigma = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
        if sigma <= 1e-6:
            sigma = 0.01
        if fi >= 1:
            r1 = abs(float(np.log(max(price, 1e-12) / max(ad.closes[fi - 1], 1e-12))))
            if r1 / sigma > float(getattr(config, 'SC_FLASH_SIGMA_1BAR', 8.0)):
                res['action'] = 'exit'; res['reason'] = f'FlashCrash(1bar={r1/sigma:.1f}s)'
                return res
        if fi >= 2:
            r2 = abs(float(np.log(max(price, 1e-12) / max(ad.closes[fi - 2], 1e-12))))
            if r2 / (sigma * 1.4142) > float(getattr(config, 'SC_FLASH_SIGMA_2BAR', 3.0)):
                res['action'] = 'exit'; res['reason'] = f'FlashCrash(2bar={r2/(sigma*1.4142):.1f}s)'
                return res
    except Exception:
        pass'''
    new_flash = '''    try:
        sigma = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
        if sigma <= 1e-6:
            sigma = 0.01
        # ══ [SC-V3-FLASH-FIX] use current_ci (not fi) for price comparisons ══
        _cc = int(current_ci) if current_ci is not None else -1
        if _cc >= 0 and _cc < len(ad.closes) and price > 0:
            _close_at_cc = float(ad.closes[_cc])
            if _close_at_cc > 1e-9:
                # Detect backtest (price == close[_cc]) vs live (ticker)
                _is_bt = abs(price - _close_at_cc) / _close_at_cc < 1e-4
                # 1-bar flash
                _ref1_ci = (_cc - 1) if _is_bt else _cc
                if _ref1_ci >= 0:
                    _p_ref1 = float(ad.closes[_ref1_ci])
                    if _p_ref1 > 1e-9:
                        r1 = abs(float(np.log(price / _p_ref1)))
                        if r1 / sigma > float(getattr(config, 'SC_FLASH_SIGMA_1BAR', 8.0)):
                            res['action'] = 'exit'
                            res['reason'] = f'FlashCrash(1bar={r1/sigma:.1f}s)'
                            return res
                # 2-bar flash
                _ref2_ci = (_cc - 2) if _is_bt else (_cc - 1)
                if _ref2_ci >= 0:
                    _p_ref2 = float(ad.closes[_ref2_ci])
                    if _p_ref2 > 1e-9:
                        r2 = abs(float(np.log(price / _p_ref2)))
                        if r2 / (sigma * 1.4142) > float(getattr(config, 'SC_FLASH_SIGMA_2BAR', 3.0)):
                            res['action'] = 'exit'
                            res['reason'] = f'FlashCrash(2bar={r2/(sigma*1.4142):.1f}s)'
                            return res
    except Exception:
        pass'''
    content = must_replace(content, old_flash, new_flash, "flash-fix")

    # Apex: add APEX_ENABLED check
    old_ap = '''    try:
        ap, ar = check_thermodynamic_apex(action, entry, price, ad, fi)
        if ap:
            res['action'] = 'exit'; res['reason'] = ar
            return res
    except Exception:
        pass'''
    new_ap = '''    if getattr(config, 'APEX_ENABLED', True):
        try:
            ap, ar = check_thermodynamic_apex(action, entry, price, ad, fi)
            if ap:
                res['action'] = 'exit'; res['reason'] = ar
                return res
        except Exception:
            pass'''
    content = must_replace(content, old_ap, new_ap, "apex-flag")

    # max_hold effective_bars
    old_mh = '''    try:
        d_tp = abs(tp - price) if tp > 0 else 0.0
        rem = max(1.0, float(getattr(config, 'MAX_HOLD_BARS', 168)) - float(bars_held))
        S_p = d_tp / max(sigma * price * np.sqrt(rem), 1e-12)
    except Exception:
        S_p = 0.0'''
    new_mh = '''    try:
        d_tp = abs(tp - price) if tp > 0 else 0.0
        try:
            _max_hold_eff = effective_bars(int(getattr(config, 'MAX_HOLD_BARS', 168)))
        except Exception:
            _max_hold_eff = int(getattr(config, 'MAX_HOLD_BARS', 168))
        rem = max(1.0, float(_max_hold_eff) - float(bars_held))
        S_p = d_tp / max(sigma * price * np.sqrt(rem), 1e-12)
    except Exception:
        S_p = 0.0'''
    content = must_replace(content, old_mh, new_mh, "max-hold-eff")

    # Pass _max_hold_eff to rescue
    old_rs = '''            ri = _compute_rescue_probability(ad, fi, action, entry, sl_cur, tp, price,
                                              bars_held, int(getattr(config, 'MAX_HOLD_BARS', 168)),
                                              config, entry_fi)'''
    new_rs = '''            _mh_for_rescue = locals().get('_max_hold_eff',
                                            int(getattr(config, 'MAX_HOLD_BARS', 168)))
            ri = _compute_rescue_probability(ad, fi, action, entry, sl_cur, tp, price,
                                              bars_held, _mh_for_rescue,
                                              config, entry_fi)'''
    content = must_replace(content, old_rs, new_rs, "rescue-mh")
    return content


def patch_11_apex_function_guard(content):
    """Add APEX_ENABLED guard inside check_thermodynamic_apex itself."""
    idx = content.find("def check_thermodynamic_apex(")
    if idx >= 0:
        be = content.find("\ndef ", idx + 10)
        block = content[idx:be if be > 0 else len(content)]
        if "if not getattr(CFG, 'APEX_ENABLED', True):" in block[:500]:
            log("  [apex-function-guard] already applied — skip")
            return content
    old = '''def check_thermodynamic_apex(pos_action, entry_price, current_price, ad, fi):
    """
    مستشعر الأوج — σ-scaled thresholds when APEX_SIGMA_SCALED=True.'''
    new = '''def check_thermodynamic_apex(pos_action, entry_price, current_price, ad, fi):
    """
    مستشعر الأوج — σ-scaled thresholds when APEX_SIGMA_SCALED=True.'''
    # Add the guard right after the docstring ends, but easier: prepend before "if fi < 3"
    old2 = '''def check_thermodynamic_apex(pos_action, entry_price, current_price, ad, fi):
    """
    مستشعر الأوج — σ-scaled thresholds when APEX_SIGMA_SCALED=True.'''
    # Find the "if fi < 3:" line that follows
    # Safer to anchor on "    if fi < 3:\n        return False, \"\"\n\n    # ── σ-scaled base ──"
    old_anchor = '''    if fi < 3:
        return False, ""

    # ── σ-scaled base ──'''
    new_anchor = '''    if fi < 3:
        return False, ""
    if not getattr(CFG, 'APEX_ENABLED', True):
        return False, ""

    # ── σ-scaled base ──'''
    return must_replace(content, old_anchor, new_anchor, "apex-function-guard")


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

    if V2_MARKER not in content:
        fail("v2 migration marker not found — run v2 first!")
    if V3_MARKER in content and not args.force:
        log("v3-fixed already applied. Use --force to re-apply.")
        return 0

    ok, err = verify_syntax(content, "PRE-V3F")
    if not ok:
        fail(f"Current file has syntax errors: {err}")

    log(f"File: {path} ({len(content)} chars, {content.count(chr(10))} lines)")

    if not args.dry_run:
        backup(path)

    try:
        content = patch_01_no_smart_center_flag(content)
        content = patch_02_no_smart_center_argparse(content)
        content = patch_03_lv_finalize_sc_fields(content)
        content = patch_04_rev_finalize_sc_fields(content)
        content = patch_05_live_peak_from_hi_lo(content)
        content = patch_06_breakeven_sc_guard(content)
        content = patch_07_print_report_sc_section(content)
        content = patch_08_plot_results_sc_info(content)
        content = patch_09_startup_info(content)
        content = patch_10_fix_flash_and_maxhold(content)
        content = patch_11_apex_function_guard(content)

        content = V3_MARKER + "\n" + content

        ok, err = verify_syntax(content, "POST-V3F")
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
        log("Migration v3-FIXED complete.")
        log("")
        log("⚠️  Flags: --no-trailing/--trailing/--trail-sync-to-subbars")
        log("           --trail-kappa/--no-dynamic-trail → REMOVED")
        log("    New: --no-smart-center (A/B test)")
        log("=" * 60)
        return 0

    except SystemExit:
        raise
    except Exception as e:
        log(f"v3-fixed FAILED: {e}", "FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
