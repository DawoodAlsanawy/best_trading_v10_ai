#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_smart_center.py — Smart Center Trailing v3 Migration Script
==================================================================

يحوّل البوت من نظام التريلينغ القديم إلى نظام Smart Center الكامل.
يطبّق التعديلات التالية بدقة:
  1. إضافة حقول SC_* إلى Config
  2. إضافة 6 دوال جديدة (health, rescue, structure, smart_center, smart_trail_apply, live)
  3. استبدال OpenPosition dataclass
  4. استبدال كتل التريلينغ في _advance (sub-bar و main-bar)
  5. تحديث simulate_portfolio لـ sigma_entry
  6. تحديث _promote_pending_to_position (Live)
  7. استبدال كتلة التريلينغ في run_live
  8. تحديث _exit_is_taker بالأسباب الجديدة
  9. تحديث _trade_log_from_live بـ health/rescue_p
 10. تحديث compute_metrics بحقول Rescue/BROKEN
 11. حذف CLI flags القديمة
 12. حذف منطق argparse القديم

السلامة:
  • نسخة احتياطية timestamped أولاً
  • Idempotent (آمن للتشغيل المتكرر)
  • التحقق من syntax قبل الكتابة
  • Rollback تلقائي عند أي فشل

الاستخدام:
  python3 apply_smart_center.py                    # يطبّق على الملف الافتراضي
  python3 apply_smart_center.py --target other.py  # ملف آخر
  python3 apply_smart_center.py --dry-run          # عرض فقط، لا كتابة
"""

import ast
import os
import re
import shutil
import sys
from datetime import datetime

MIGRATION_MARKER = "# [SMART-CENTER-MIGRATION-APPLIED]"
DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"


# ═══════════════════════════════════════════════════════════════
# INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════

def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def fail(msg):
    log(msg, "FAIL")
    raise SystemExit(1)


def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_{ts}"
    shutil.copy2(path, bak)
    log(f"  نسخة احتياطية: {bak}")
    return bak


def verify_syntax(content):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def must_replace(content, old, new, label):
    n = content.count(old)
    if n == 0:
        fail(f"[{label}] anchor not found")
    if n > 1:
        fail(f"[{label}] ambiguous ({n} matches)")
    return content.replace(old, new, 1)


def must_insert_before(content, anchor, block, label):
    idx = content.find(anchor)
    if idx < 0:
        fail(f"[{label}] anchor not found: {anchor[:60]!r}")
    return content[:idx] + block + content[idx:]


def replace_line_range(content, start_marker, end_marker, replacement, label):
    """Replace text from start_marker line through end_marker line (inclusive)."""
    lines = content.split("\n")
    start = end = -1
    for i, line in enumerate(lines):
        if start_marker in line:
            start = i
            break
    if start < 0:
        fail(f"[{label}] start marker not found")
    for i in range(start, len(lines)):
        if end_marker in lines[i]:
            end = i
            break
    if end < 0:
        fail(f"[{label}] end marker not found after line {start}")
    new_lines = lines[:start] + replacement.split("\n") + lines[end + 1:]
    return "\n".join(new_lines)


# ═══════════════════════════════════════════════════════════════
# CODE BLOCKS TO INSERT
# ═══════════════════════════════════════════════════════════════

SC_CONFIG_BLOCK = '''
    # ══ [SMART CENTER TRAILING v3 — Migration] ══
    SMART_CENTER_ENABLED: bool = True
    SC_HEALTHY_THRESHOLD: float = 0.65
    SC_BROKEN_THRESHOLD: float = 0.40
    SC_BROKEN_EXTREME_THRESHOLD: float = 0.15
    SC_BROKEN_PERSIST_BARS: int = 2
    SC_PRICE_DIST_MAX: float = 3.0
    SC_PRICE_DIST_EXTREME: float = 6.0
    SC_FLASH_SIGMA_1BAR: float = 8.0
    SC_FLASH_SIGMA_2BAR: float = 3.0
    SC_RESCUE_ENABLED: bool = True
    SC_RESCUE_MARGIN: float = 0.05
    SC_RESCUE_FLOOR: float = 0.15
    SC_HEALTHY_TRAIL_KAPPA: float = 3.0
    SC_WEAK_TRAIL_KAPPA: float = 1.5
    SC_ACTIVATE_R_HEALTHY: float = 0.5
    SC_ACTIVATE_R_WEAK: float = 0.3
    SC_BE_ESC_BUFFER: float = 0.001
    SC_TRAIL_MIN_STEP: float = 0.0005
    SC_HEALTH_WEIGHTS: tuple = (0.30, 0.20, 0.15, 0.15, 0.10, 0.05, 0.05)
    SC_MU_HIST_BARS: int = 20

'''


SC_FUNCTIONS_BLOCK = r'''
# ═══════════════════════════════════════════════════════════════
# [SMART CENTER TRAILING v3] — Migration-added functions
# ═══════════════════════════════════════════════════════════════

def _compute_health_score(ad, fi, entry_fi, action, config):
    """Composite health score H in [0,1]. Returns (H, components)."""
    try:
        if ad is None or fi < 3:
            return 0.5, {}
        n = len(getattr(ad, 'geodesic_accel', []))
        if n == 0 or fi >= n:
            return 0.5, {}
    except Exception:
        return 0.5, {}
    sign = 1.0 if action == "BUY" else -1.0
    comp = {}
    try:
        a_now = float(ad.geodesic_accel[fi])
        win = ad.geodesic_accel[max(0, fi - 100):fi + 1]
        a_std = float(np.std(win)) + 1e-9
        z = sign * a_now / a_std
        comp['accel'] = float(1.0 / (1.0 + np.exp(-np.clip(z - 0.5, -10, 10))))
    except Exception:
        comp['accel'] = 0.5
    try:
        g_now = float(ad.gauge_force[fi])
        g_past = ad.gauge_force[max(0, fi - 100):fi + 1]
        g_p90 = float(np.percentile(g_past, 90)) + 1e-9
        comp['gauge'] = float(np.clip(g_now / g_p90, 0.0, 1.0))
    except Exception:
        comp['gauge'] = 0.5
    try:
        f_now = float(ad.friction[fi])
        f_past = ad.friction[max(0, fi - 100):fi + 1]
        f_med = float(np.median(f_past)) + 1e-9
        comp['friction'] = float(np.clip((2.0 - f_now / f_med) / 1.5, 0.0, 1.0))
    except Exception:
        comp['friction'] = 0.5
    try:
        df_now = float(ad.dF[fi])
        df_past = ad.dF[max(0, fi - 100):fi + 1]
        df_std = float(np.std(df_past)) + 1e-9
        comp['dfree'] = float(1.0 / (1.0 + np.exp(np.clip(sign * df_now / df_std, -10, 10))))
    except Exception:
        comp['dfree'] = 0.5
    try:
        dh_now = float(ad.dH[fi])
        dh_past = ad.dH[max(0, fi - 100):fi + 1]
        dh_std = float(np.std(dh_past)) + 1e-9
        comp['dh'] = float(1.0 / (1.0 + np.exp(np.clip(sign * dh_now / dh_std, -10, 10))))
    except Exception:
        comp['dh'] = 0.5
    try:
        if fi >= 50 and fi < len(ad.ema200):
            slope = (float(ad.ema200[fi]) - float(ad.ema200[fi - 50])) / 50.0
            sn = sign * slope / (float(ad.closes[fi]) * 0.01 + 1e-9)
            comp['ema'] = float(np.clip(0.5 + sn * 0.5, 0.2, 1.0))
        else:
            comp['ema'] = 0.5
    except Exception:
        comp['ema'] = 0.5
    try:
        sc_n = float(ad.score[fi]) if 0 <= fi < len(ad.score) else 0.0
        sc_e = float(ad.score[entry_fi]) if 0 <= entry_fi < len(ad.score) else sc_n
        comp['score'] = float(np.clip(sc_n / sc_e, 0.0, 1.2)) / 1.2 if sc_e > 1e-6 else 0.5
    except Exception:
        comp['score'] = 0.5
    w = list(getattr(config, 'SC_HEALTH_WEIGHTS', (0.30, 0.20, 0.15, 0.15, 0.10, 0.05, 0.05)))
    keys = ('accel', 'gauge', 'friction', 'dfree', 'dh', 'ema', 'score')
    H = sum(w[i] * comp[keys[i]] for i in range(7))
    return float(np.clip(H, 0.0, 1.0)), comp


def _compute_rescue_probability(ad, fi, action, entry, sl, tp, price,
                                 bars_held, max_hold, config, entry_fi=0):
    out = {'P_rescue': 1.0, 'P_BM': 0.5, 'f_phys': 1.0, 'f_time': 1.0,
           'a': 0.0, 'b': 0.0, 'mu': 0.0, 'sigma': 0.01, 'threshold': 0.5,
           'L_now_frac': 0.0, 'L_sl_frac': 0.01, 'health': 0.5,
           'components': {}, 'error': None}
    try:
        if ad is None or fi < 3 or entry <= 0 or sl <= 0 or price <= 0:
            out['error'] = 'invalid_inputs'
            return out
        if action == "BUY" and price >= entry:
            return out
        if action == "SELL" and price <= entry:
            return out
        if action == "BUY":
            a = float(np.log(entry / price)); b = float(np.log(price / sl))
        else:
            a = float(np.log(price / entry)); b = float(np.log(sl / price))
        if a <= 0 or b <= 0:
            out['error'] = 'invalid_distances'
            return out
        out['a'] = a; out['b'] = b
        sigma = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
        if not np.isfinite(sigma) or sigma <= 1e-6:
            sigma = 0.01
        out['sigma'] = sigma
        sv = sigma * sigma
        n_h = int(getattr(config, 'SC_MU_HIST_BARS', 20))
        try:
            lo = max(1, fi - n_h)
            cl = ad.closes[lo:fi + 1]
            r_hist = float(np.mean(np.diff(np.log(np.maximum(cl, 1e-12))))) if len(cl) >= 2 else 0.0
        except Exception:
            r_hist = 0.0
        sign = 1.0 if action == "BUY" else -1.0
        try:
            acc = float(ad.geodesic_accel[fi]) if 0 <= fi < len(ad.geodesic_accel) else 0.0
        except Exception:
            acc = 0.0
        mu = r_hist + 0.5 * sign * acc
        if abs(mu) < 1e-9:
            mu = 1e-9 * (1.0 if r_hist >= 0 else -1.0)
        out['mu'] = mu
        z = -2.0 * mu / sv
        try:
            na = -z * b; da = -z * (a + b)
            num = 1.0 - np.exp(na) if abs(na) < 40 else (1.0 if na > 0 else -1.0)
            den = 1.0 - np.exp(da) if abs(da) < 40 else (1.0 if da > 0 else -1.0)
            P_BM = num / den if abs(den) > 1e-9 else b / (a + b)
            if not np.isfinite(P_BM) or P_BM < 0 or P_BM > 1:
                P_BM = b / (a + b)
        except Exception:
            P_BM = b / (a + b)
        out['P_BM'] = float(np.clip(P_BM, 0.0, 1.0))
        H, comps = _compute_health_score(ad, fi, entry_fi, action, config)
        out['health'] = H; out['components'] = comps
        out['f_phys'] = float(np.clip(1.0 + 0.5 * (H - 0.5) * 2.0, 0.4, 1.6))
        t_rem = max(0.0, float(max_hold) - float(bars_held))
        t_need = a / (abs(mu) + 1e-9)
        out['f_time'] = 0.0 if t_rem <= 0 else (1.0 if t_need <= 0 else float(min(1.0, t_rem / t_need)))
        out['P_rescue'] = float(np.clip(out['P_BM'] * out['f_phys'] * out['f_time'], 0.0, 1.0))
        L_now = abs(entry - price) / entry
        L_sl = abs(entry - sl) / entry
        out['L_now_frac'] = float(L_now); out['L_sl_frac'] = float(max(L_sl, 1e-9))
        th = max(1.0 - L_now / max(L_sl, 1e-9) - float(getattr(config, 'SC_RESCUE_MARGIN', 0.05)),
                 float(getattr(config, 'SC_RESCUE_FLOOR', 0.15)))
        out['threshold'] = float(np.clip(th, 0.0, 1.0))
        return out
    except Exception as e:
        out['error'] = f'exception:{e}'
        return out


def _structure_broken(ad, current_ci, entry_ci, action, config=None):
    try:
        if ad is None or current_ci is None or entry_ci is None:
            return False
        if current_ci - entry_ci < 3:
            return False
        lookback = max(5, int(current_ci - entry_ci))
        lo = max(1, current_ci - lookback)
        hi = min(current_ci, len(ad.lows) - 1)
        if hi - lo < 3:
            return False
        price = float(ad.closes[current_ci])
        atr = float(ad.atr14[current_ci]) if current_ci < len(ad.atr14) else 0.0
        buf = 0.3 * atr if atr > 0 else price * 0.005
        if action == "BUY":
            for j in range(hi - 1, lo, -1):
                if ad.lows[j] < ad.lows[j - 1] and ad.lows[j] < ad.lows[j + 1]:
                    return price < float(ad.lows[j]) - buf
        else:
            for j in range(hi - 1, lo, -1):
                if ad.highs[j] > ad.highs[j - 1] and ad.highs[j] > ad.highs[j + 1]:
                    return price > float(ad.highs[j]) + buf
    except Exception:
        return False
    return False


def _smart_center_decision(pos_snap, price, ad, fi, entry_fi,
                            bars_held, current_ci, entry_ci, config):
    res = {'action': 'hold', 'new_sl': float(pos_snap.get('sl', 0.0)),
           'new_streak': int(pos_snap.get('broken_streak', 0)),
           'health': 0.5, 'tier': 'UNKNOWN', 'rescue_p': 1.0,
           'reason': 'init', 'components': {}}
    if not getattr(config, 'SMART_CENTER_ENABLED', True):
        res['reason'] = 'sc_disabled'
        return res
    action = pos_snap.get('action', 'BUY')
    entry = float(pos_snap.get('entry', 0.0))
    sl_cur = float(pos_snap.get('sl', 0.0))
    tp = float(pos_snap.get('tp', 0.0))
    peak = float(pos_snap.get('peak', entry))
    sigma_entry = float(pos_snap.get('sigma_entry', 0.01))
    if sigma_entry <= 1e-9:
        sigma_entry = 0.01
    if ad is None:
        res['reason'] = 'data_missing'
        return res
    try:
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
        pass
    H, comps = _compute_health_score(ad, fi, entry_fi, action, config)
    res['health'] = H; res['components'] = comps
    sl_d0 = abs(entry - float(pos_snap.get('sl_initial', sl_cur) or sl_cur))
    if sl_d0 <= 1e-12:
        sl_d0 = max(sigma_entry * entry * 3.0, entry * 0.002)
    try:
        d_tp = abs(tp - price) if tp > 0 else 0.0
        rem = max(1.0, float(getattr(config, 'MAX_HOLD_BARS', 168)) - float(bars_held))
        S_p = d_tp / max(sigma * price * np.sqrt(rem), 1e-12)
    except Exception:
        S_p = 0.0
    if H <= float(getattr(config, 'SC_BROKEN_EXTREME_THRESHOLD', 0.15)) or S_p > float(getattr(config, 'SC_PRICE_DIST_EXTREME', 6.0)):
        res['action'] = 'exit'; res['tier'] = 'BROKEN_EXTREME'
        res['reason'] = f'BROKEN_EXTREME(H={H:.2f},S={S_p:.1f})'
        return res
    try:
        ap, ar = check_thermodynamic_apex(action, entry, price, ad, fi)
        if ap:
            res['action'] = 'exit'; res['reason'] = ar
            return res
    except Exception:
        pass
    new_streak = (res['new_streak'] + 1) if H <= float(getattr(config, 'SC_BROKEN_THRESHOLD', 0.40)) else 0
    res['new_streak'] = new_streak
    struct_br = _structure_broken(ad, current_ci, entry_ci, action, config)
    if (new_streak >= int(getattr(config, 'SC_BROKEN_PERSIST_BARS', 2))
            or S_p > float(getattr(config, 'SC_PRICE_DIST_MAX', 3.0))
            or struct_br):
        res['action'] = 'exit'; res['tier'] = 'BROKEN'
        rsn = 'H' if new_streak >= 2 else ('S' if S_p > 3.0 else 'struct')
        res['reason'] = f'BROKEN({rsn},H={H:.2f},S={S_p:.1f})'
        return res
    if getattr(config, 'SC_RESCUE_ENABLED', True):
        is_losing = (action == "BUY" and price < entry) or (action == "SELL" and price > entry)
        if is_losing and bars_held >= 1:
            ri = _compute_rescue_probability(ad, fi, action, entry, sl_cur, tp, price,
                                              bars_held, int(getattr(config, 'MAX_HOLD_BARS', 168)),
                                              config, entry_fi)
            res['rescue_p'] = ri['P_rescue']
            if ri['error'] is None and ri['P_rescue'] < ri['threshold']:
                res['action'] = 'exit'; res['tier'] = 'RESCUE'
                res['reason'] = f"Rescue(P={ri['P_rescue']:.2f}<{ri['threshold']:.2f})"
                return res
    mfe_R = ((peak - entry) if action == "BUY" else (entry - peak)) / sl_d0 if sl_d0 > 0 else 0.0
    if H > float(getattr(config, 'SC_HEALTHY_THRESHOLD', 0.65)):
        tier = 'HEALTHY'
        act_r = float(getattr(config, 'SC_ACTIVATE_R_HEALTHY', 0.5))
        kappa = float(getattr(config, 'SC_HEALTHY_TRAIL_KAPPA', 3.0))
    else:
        tier = 'WEAKENING'
        act_r = float(getattr(config, 'SC_ACTIVATE_R_WEAK', 0.3))
        kappa = float(getattr(config, 'SC_WEAK_TRAIL_KAPPA', 1.5))
    res['tier'] = tier
    if mfe_R >= act_r:
        td = kappa * sigma_entry
        new_sl = peak * (1.0 - td) if action == "BUY" else peak * (1.0 + td)
        if bool(pos_snap.get('be_esc_armed', True)):
            kb = float(getattr(config, 'BREAKEVEN_ESCAPE_PRICE_MOVE_R', 0.30))
            buf = float(getattr(config, 'SC_BE_ESC_BUFFER', 0.001))
            if action == "BUY":
                lvl = entry - kb * sl_d0
                new_sl = min(new_sl, lvl * (1.0 - buf))
            else:
                lvl = entry + kb * sl_d0
                new_sl = max(new_sl, lvl * (1.0 + buf))
        ms = float(getattr(config, 'SC_TRAIL_MIN_STEP', 0.0005))
        if action == "BUY":
            new_sl = min(new_sl, price * 0.999)
            if new_sl > sl_cur * (1.0 + ms):
                res['action'] = 'update_sl'; res['new_sl'] = float(new_sl)
                res['reason'] = f'{tier}(H={H:.2f},MFE={mfe_R:.2f}R)'
                return res
        else:
            new_sl = max(new_sl, price * 1.001)
            if new_sl < sl_cur * (1.0 - ms):
                res['action'] = 'update_sl'; res['new_sl'] = float(new_sl)
                res['reason'] = f'{tier}(H={H:.2f},MFE={mfe_R:.2f}R)'
                return res
    res['reason'] = f'{tier}(H={H:.2f})'
    return res


def _smart_trail_apply(pos, ad, sig, cidx, fi, high, low, trail_sl):
    if not getattr(CFG, 'SMART_CENTER_ENABLED', True):
        return trail_sl, None
    try:
        mfe_c = ((high - pos.entry_px) if sig.action == "BUY" else (pos.entry_px - low)) / pos.entry_px
        if mfe_c > pos.mfe_frac:
            pos.mfe_frac = mfe_c
        if sig.action == "BUY":
            if high > pos.peak_price:
                pos.peak_price = float(high)
        else:
            if pos.peak_price == 0 or low < pos.peak_price:
                pos.peak_price = float(low)
        price_now = float(ad.closes[cidx])
        snap = {
            'entry': float(pos.entry_px), 'sl': float(trail_sl),
            'sl_initial': float(getattr(pos, 'sl_dist_initial', 0.0)),
            'tp': float(sig.tp1), 'peak': float(pos.peak_price),
            'sigma_entry': float(getattr(pos, 'sigma_entry', 0.01)),
            'broken_streak': int(getattr(pos, '_broken_streak', 0)),
            'action': sig.action,
            'be_esc_armed': not bool(getattr(pos, '_be_esc_done', False)),
        }
        result = _smart_center_decision(
            snap, price_now, ad, fi, int(getattr(pos, 'entry_fi', 0)),
            cidx - pos.entry_ci, cidx, pos.entry_ci, CFG
        )
        try:
            pos._broken_streak = int(result.get('new_streak', 0))
            pos._health = float(result.get('health', 0.5))
            pos._rescue_p = float(result.get('rescue_p', 1.0))
        except Exception:
            pass
        if result['action'] == 'exit':
            return trail_sl, (price_now, result['reason'], cidx)
        if result['action'] == 'update_sl':
            ns = float(result['new_sl'])
            ms = float(getattr(CFG, 'SC_TRAIL_MIN_STEP', 0.0005))
            if sig.action == "BUY":
                if ns > trail_sl * (1.0 + ms):
                    trail_sl = ns
            else:
                if ns < trail_sl * (1.0 - ms):
                    trail_sl = ns
    except Exception as e:
        log.debug(f"[SmartTrail] apply failed {getattr(pos, 'symbol', '?')}: {e}")
    return trail_sl, None


def _smart_center_decision_live(exchange, sym, pos, price, ad):
    try:
        if not getattr(CFG, 'SMART_CENTER_ENABLED', True) or ad is None or price <= 0:
            return {'action': 'hold', 'reason': 'sc_off_or_missing'}
        entry_ci = int(pos.get('_entry_ci', 0))
        fi = max(0, len(ad.closes) - 2 - ad.feat_start)
        entry_fi = max(0, entry_ci - ad.feat_start)
        tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
        bars_held = int(max(0.0, (time.time() - float(pos.get('entry_ts', time.time()))) / max(tf_sec, 1)))
        snap = {
            'entry': float(pos.get('entry', 0)),
            'sl': float(pos.get('sl', 0)),
            'sl_initial': float(pos.get('sl_dist_initial', 0)),
            'tp': float(pos.get('tp1', 0)),
            'peak': float(pos.get('peak_price', pos.get('entry', 0))),
            'sigma_entry': float(pos.get('sigma_entry', 0.01)),
            'broken_streak': int(pos.get('_broken_streak', 0)),
            'action': str(pos.get('action', 'BUY')),
            'be_esc_armed': not bool(pos.get('_be_esc_done', False)),
        }
        if snap['action'] == "BUY":
            if price > snap['peak']:
                snap['peak'] = float(price); pos['peak_price'] = price
        else:
            if snap['peak'] == 0 or price < snap['peak']:
                snap['peak'] = float(price); pos['peak_price'] = price
        result = _smart_center_decision(snap, float(price), ad, fi, entry_fi,
                                         bars_held, len(ad.closes) - 2, entry_ci, CFG)
        pos['_broken_streak'] = int(result.get('new_streak', 0))
        pos['_health'] = float(result.get('health', 0.5))
        pos['_rescue_p'] = float(result.get('rescue_p', 1.0))
        if result['action'] == 'update_sl':
            old = float(pos.get('sl', 0))
            pos['sl'] = float(result['new_sl'])
            try:
                if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
                    _sync_protective_orders(exchange, sym, pos)
            except Exception as e:
                log.debug(f"[SmartCenter-Live] sync {sym}: {e}")
            log.debug(f"[SmartCenter-Live] {sym} SL {old:.6f}->{pos['sl']:.6f} ({result['reason']})")
        return result
    except Exception as e:
        log.debug(f"[SmartCenter-Live] {sym} failed: {e}")
        return {'action': 'hold', 'reason': f'err:{e}'}

'''


OLD_OPEN_POSITION_BLOCK = """@dataclass
class OpenPosition:
    symbol: str; signal: Signal
    entry_px: float; pos_size: float; trail_sl: float
    entry_cap: float; entry_ci: int; current_ci: int
    slip_paid: float; opt_entry: bool; tri_entry: float
    mfe_frac: float = 0.0
    peak_price: float = 0.0
    trail_dist_frac: float = 0.003
    trail_activate_frac: float = 0.004
    sl_dist_initial: float = 0.0
    trail_peak_R: float = 0.0
    entry_sub_idx: int = 0
    partial_taken: bool = False      # [FIX 4]
    partial_pnl: float = 0.0         # [FIX 4] accumulated partial profit"""

NEW_OPEN_POSITION_BLOCK = """@dataclass
class OpenPosition:
    symbol: str; signal: Signal
    entry_px: float; pos_size: float; trail_sl: float
    entry_cap: float; entry_ci: int; current_ci: int
    slip_paid: float; opt_entry: bool; tri_entry: float
    mfe_frac: float = 0.0
    peak_price: float = 0.0
    sigma_entry: float = 0.01
    entry_fi: int = 0
    sl_dist_initial: float = 0.0
    trail_peak_R: float = 0.0
    entry_sub_idx: int = 0
    partial_taken: bool = False
    partial_pnl: float = 0.0
    _broken_streak: int = 0
    _health: float = 0.5
    _rescue_p: float = 1.0"""


# ═══════════════════════════════════════════════════════════════
# TRANSFORMATIONS
# ═══════════════════════════════════════════════════════════════

def op_add_config(content):
    anchor = "\nCFG = Config()"
    return must_insert_before(content, anchor, SC_CONFIG_BLOCK, "Config")


def op_add_functions(content):
    anchor = "def build_signals(assets, mode=\"backtest\"):"
    return must_insert_before(content, anchor, SC_FUNCTIONS_BLOCK + "\n", "Functions")


def op_replace_open_position(content):
    return must_replace(content, OLD_OPEN_POSITION_BLOCK, NEW_OPEN_POSITION_BLOCK, "OpenPosition")


def op_fix_advance_subbar(content):
    """Replace sub-bar trailing block in _advance."""
    start = "                # Legacy trailing (uses sub-bar high/low as peak candidate)"
    end_marker = "                            trail_sl = new_sl\n"
    lines = content.split("\n")
    start_i = -1
    for i, line in enumerate(lines):
        if line == start.strip() or start in line:
            start_i = i
            break
    if start_i < 0:
        fail("[_advance-subbar] start not found")
    end_i = -1
    for i in range(start_i, len(lines)):
        if lines[i].strip() == "trail_sl = new_sl" and lines[i].startswith(" " * 28):
            end_i = i
            break
    if end_i < 0:
        fail("[_advance-subbar] end not found")
    replacement = (
        "                # ══ [SMART CENTER v3] ══\n"
        "                _new_trail, _exit_t = _smart_trail_apply(\n"
        "                    pos, ad, sig, cidx, fi, s_high, s_low, trail_sl\n"
        "                )\n"
        "                trail_sl = _new_trail\n"
        "                if _exit_t is not None:\n"
        "                    pos.trail_sl = trail_sl; pos.current_ci = cidx\n"
        "                    return _exit_t[0], _exit_t[1], _exit_t[2]"
    )
    new_lines = lines[:start_i] + replacement.split("\n") + lines[end_i + 1:]
    log("  _advance sub-bar: replaced")
    return "\n".join(new_lines)


def op_fix_advance_mainbar(content):
    """Replace main-bar trailing block in _advance."""
    lines = content.split("\n")
    start_i = -1
    for i, line in enumerate(lines):
        if line.strip() == "_td = pos.trail_dist_frac if pos.trail_dist_frac > 0 else CFG.TRAIL_DISTANCE" and line.startswith(" " * 12):
            start_i = i
            break
    if start_i < 0:
        fail("[_advance-mainbar] start not found")
    end_i = -1
    for i in range(start_i, len(lines)):
        if lines[i].strip() == "trail_sl = new_sl" and lines[i].startswith(" " * 24):
            end_i = i
            break
    if end_i < 0:
        fail("[_advance-mainbar] end not found")
    replacement = (
        "            # ══ [SMART CENTER v3] ══\n"
        "            _new_trail, _exit_t = _smart_trail_apply(\n"
        "                pos, ad, sig, cidx, fi, high, low, trail_sl\n"
        "            )\n"
        "            trail_sl = _new_trail\n"
        "            if _exit_t is not None:\n"
        "                pos.trail_sl = trail_sl; pos.current_ci = cidx\n"
        "                return _exit_t[0], _exit_t[1], _exit_t[2]"
    )
    new_lines = lines[:start_i] + replacement.split("\n") + lines[end_i + 1:]
    log("  _advance main-bar: replaced")
    return "\n".join(new_lines)


def op_fix_simulate_portfolio(content):
    """Remove compute_trail_params call and add sigma_entry."""
    old = """        # ══ [DYNAMIC TRAIL] compute σ-scaled trail params at entry ══
        entry_fi = max(0, min(opt_ci - ad.feat_start,
                              len(ad.E_therm) - 1))
        trail_d, trail_a = compute_trail_params(ad, entry_fi)"""
    new = """        # ══ [SMART CENTER v3] compute sigma_entry at entry ══
        entry_fi = max(0, min(opt_ci - ad.feat_start,
                              len(ad.E_therm) - 1))
        try:
            _sigma_entry = float(ad.E_therm[entry_fi])
            if not np.isfinite(_sigma_entry) or _sigma_entry <= 1e-9:
                _sigma_entry = 0.01
        except Exception:
            _sigma_entry = 0.01"""
    content = must_replace(content, old, new, "simulate_portfolio sigma")
    old2 = """            trail_dist_frac=trail_d,
            trail_activate_frac=trail_a,
            sl_dist_initial=float(abs(eff_px - sl_h)),
            trail_peak_R=0.0,
            entry_sub_idx=opt_sub_idx,
        )"""
    new2 = """            sigma_entry=_sigma_entry,
            entry_fi=entry_fi,
            sl_dist_initial=float(abs(eff_px - sl_h)),
            trail_peak_R=0.0,
            entry_sub_idx=opt_sub_idx,
            _broken_streak=0,
            _health=0.5,
            _rescue_p=1.0,
        )"""
    content = must_replace(content, old2, new2, "simulate_portfolio OpenPosition")
    return content


def op_fix_promote(content):
    """Live: remove trail calc, add sigma."""
    old = """    # σ-scaled trailing params at entry
    trail_d, trail_a = (0.003, 0.004)
    try:
        ad = rec.get('ad_ref')
        entry_fi = int(rec.get('entry_fi') or 0)
        if ad is not None:
            trail_d, trail_a = compute_trail_params(ad, entry_fi)
    except Exception:
        pass"""
    new = """    # [SMART CENTER v3] compute sigma_entry at fill
    _sigma_entry = 0.01
    _entry_fi_p = 0
    try:
        ad = rec.get('ad_ref')
        _entry_fi_p = int(rec.get('entry_fi') or 0)
        if ad is not None:
            _s = float(ad.E_therm[_entry_fi_p]) if 0 <= _entry_fi_p < len(ad.E_therm) else 0.01
            if np.isfinite(_s) and _s > 1e-9:
                _sigma_entry = _s
    except Exception:
        pass"""
    content = must_replace(content, old, new, "promote sigma")
    old2 = """        'trail_dist_frac': float(trail_d),
        'trail_activate_frac': float(trail_a),
        'liq_price_estimated': _liq_estimated,
        'mmr': _mmr,
        'sl_dist_initial': float(abs(entry_price - adapted_sl)),"""
    new2 = """        'sigma_entry': float(_sigma_entry),
        'liq_price_estimated': _liq_estimated,
        'mmr': _mmr,
        'sl_dist_initial': float(abs(entry_price - adapted_sl)),
        '_broken_streak': 0,
        '_health': 0.5,
        '_rescue_p': 1.0,"""
    return must_replace(content, old2, new2, "promote dict fields")


def op_fix_run_live_trailing(content):
    """Replace the trailing block in run_live with smart center call."""
    old_start = "                # ── Trailing SL (dynamic σ-scaled) ──"
    old_end = "                            _sync_protective_orders(exchange, sym, pos)\n                        except Exception as _e:\n                            log.debug(f\"[Prot] {sym} sync error: {_e}\")\n"
    lines = content.split("\n")
    start_i = -1
    for i, line in enumerate(lines):
        if old_start.strip() in line:
            start_i = i
            break
    if start_i < 0:
        fail("[run_live-trailing] start not found")
    # Find end: next line containing "── [FIX 4] Partial TP ──" or similar
    end_i = -1
    for i in range(start_i + 1, len(lines)):
        if "── [FIX 4] Partial TP ──" in lines[i] or "# ── [FIX 4] Partial TP ──" in lines[i]:
            end_i = i
            break
    if end_i < 0:
        fail("[run_live-trailing] end not found")
    replacement = [
        "                # ── [SMART CENTER v3] ──",
        "                if not ex and getattr(CFG, 'SMART_CENTER_ENABLED', True):",
        "                    _sc_result = _smart_center_decision_live(exchange, sym, pos, price, ad)",
        "                    if _sc_result.get('action') == 'exit':",
        "                        ex = True; rsn = _sc_result.get('reason', 'SmartCenter')",
        "",
    ]
    new_lines = lines[:start_i] + replacement + lines[end_i:]
    log("  run_live trailing: replaced with Smart Center")
    return "\n".join(new_lines)


def op_fix_exit_taker(content):
    old = """    if ((\"Emergency\" in r) or (\"Hard TP\" in r)
            or (\"LiqProximity\" in r) or _apex_match):
        return True"""
    new = """    _sc_match = ((\"Rescue\" in r) or (\"BROKEN\" in r)
                 or (\"FlashCrash\" in r))
    if ((\"Emergency\" in r) or (\"Hard TP\" in r)
            or (\"LiqProximity\" in r) or _apex_match or _sc_match):
        return True"""
    return must_replace(content, old, new, "exit_taker reasons")


def op_fix_trade_log(content):
    old = """            'action': str(pos.get('action', '?')),
            'stage': str(pos.get('stage', 'S1')),"""
    new = """            'action': str(pos.get('action', '?')),
            'stage': str(pos.get('stage', 'S1')),
            'health_at_exit': float(pos.get('_health', -1.0)),
            'rescue_p_at_exit': float(pos.get('_rescue_p', -1.0)),"""
    return must_replace(content, old, new, "trade_log fields")


def op_fix_metrics(content):
    old = """        'buy_count': buy_count, 'sell_count': sell_count,
    }"""
    new = """        'buy_count': buy_count, 'sell_count': sell_count,
        'rescue_exits': sum(1 for t in trades if 'Rescue' in t.exit_reason),
        'broken_exits': sum(1 for t in trades if 'BROKEN' in t.exit_reason),
        'flash_exits': sum(1 for t in trades if 'FlashCrash' in t.exit_reason),
    }"""
    return must_replace(content, old, new, "metrics fields")


def op_remove_cli_flags(content):
    """Remove obsolete CLI flags."""
    flags_to_remove = [
        ("""    p.add_argument(\"--no-trailing\", action=\"store_true\",
                   help=\"Disable Trailing Stop Loss entirely (SL stays fixed)\")
""", ""),
        ("""    p.add_argument(\"--trailing\", action=\"store_true\",
                   help=\"Force-enable Trailing Stop Loss (overrides config)\")
""", ""),
        ("""    p.add_argument(\"--trail-sync-to-subbars\", action=\"store_true\",
                   help=\"Update peak/SL ONLY on sub-bar close (e.g., 15m) \"
                        \"— matches backtest exactly. No ticker, no 1m forming bar.\")
""", ""),
        ("""    p.add_argument(\"--trail-kappa\", type=float, default=None,
                   help=\"Trail multiplier on σ (default 1.5)\")
""", ""),
        ("""    p.add_argument(\"--no-dynamic-trail\", action=\"store_true\",
                   help=\"Use fixed TRAIL_DISTANCE instead of σ-scaled trailing\")
""", ""),
    ]
    for old, new in flags_to_remove:
        if old in content:
            content = content.replace(old, new, 1)
            log(f"  Removed CLI flag")
    return content


def op_remove_argparse(content):
    """Remove obsolete argparse handling."""
    blocks = [
        """    if args.no_dynamic_trail:
        CFG.TRAIL_DYNAMIC = False
""",
        """    if args.no_trailing:
        CFG.TRAIL_ENABLED = False
        log.info(\"[Trail] Trailing Stop Loss DISABLED — SL is fixed\")
    elif args.trailing:
        CFG.TRAIL_ENABLED = True
        log.info(\"[Trail] Trailing Stop Loss FORCED ON\")
""",
        """    if getattr(args, \"trail_sync_to_subbars\", False):
        CFG.TRAIL_USE_SUBBARS_ONLY = True
        _sub_tf_for_log = _get_subbars_tf(CFG.timeframe) or CFG.timeframe
        log.info(
            f\"[Trail] SUB-BAR PARITY ON: peak/SL update only on \"
            f\"sub-bar close ({_sub_tf_for_log}). \"
            f\"No ticker, no 1m forming bar. Matches backtest exactly.\"
        )
""",
        """    if args.trail_kappa is not None:
        CFG.TRAIL_KAPPA = float(args.trail_kappa)
""",
    ]
    for block in blocks:
        if block in content:
            content = content.replace(block, "", 1)
            log("  Removed argparse block")
    return content


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = args.target
    if not os.path.exists(path):
        fail(f"File not found: {path}")

    content = open(path, "r", encoding="utf-8").read()

    if MIGRATION_MARKER in content:
        log("Already migrated. Exiting.")
        return 0

    ok, err = verify_syntax(content)
    if not ok:
        fail(f"Original file has syntax errors: {err}")

    log(f"File loaded: {path} ({len(content)} chars, {content.count(chr(10))} lines)")

    if not args.dry_run:
        backup(path)

    try:
        content = op_add_config(content)
        content = op_add_functions(content)
        content = op_replace_open_position(content)
        content = op_fix_advance_subbar(content)
        content = op_fix_advance_mainbar(content)
        content = op_fix_simulate_portfolio(content)
        content = op_fix_promote(content)
        content = op_fix_run_live_trailing(content)
        content = op_fix_exit_taker(content)
        content = op_fix_trade_log(content)
        content = op_fix_metrics(content)
        content = op_remove_cli_flags(content)
        content = op_remove_argparse(content)

        # Add marker
        content = MIGRATION_MARKER + "\n" + content

        # Verify
        ok, err = verify_syntax(content)
        if not ok:
            fail(f"Resulted file has syntax errors: {err}. Rolling back.")

        if args.dry_run:
            log("DRY RUN: syntax OK. Would write to file.")
            return 0

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
        log(f"Saved: {path}")
        log("Migration complete.")
        return 0

    except SystemExit:
        raise
    except Exception as e:
        log(f"Migration FAILED: {e}", "FAIL")
        log("Original file unchanged (backup exists)", "WARN")
        return 1


if __name__ == "__main__":
    sys.exit(main())
