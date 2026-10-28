#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_rescue_exit.py — Rescue Exit (Loss Zone Guardian)
========================================================
يُضيف طبقة حماية بين BEEsc و SL: الخروج المبكر عندما يُثبت النظام
الفيزيائي أن احتمال العودة ضعيف جداً.

المبدأ الرياضي (Two-Sided Barrier Problem):
    P_rescue = P_BM(μ_eff, σ, a, b) × f_phys × f_time
    Exit if P_rescue < max(1 - L_now/L_SL - margin, P_floor)

الترتيب في بوابات الخروج:
    Flash → BROKEN_extreme → Apex → BROKEN → **RESCUE** → SL/TP → BEEsc → Trailing

الفلسفة:
  • Opt-in فقط (--rescue-exit) — لا تغيير على السلوك الافتراضي
  • Rescue يعمل فقط بعد BEEsc fired (لا تداخل مع mean reversion)
  • Conservative default — Rescue نادر لكنه دقيق
  • Parity كامل: نفس المنطق في Backtest و Live
  • 3 مستويات: conservative / moderate / aggressive

الاستخدام:
    python3 apply_rescue_exit.py --dry-run --verbose
    python3 apply_rescue_exit.py

    # في التشغيل:
    --rescue-exit                    # conservative (افتراضي عند التفعيل)
    --rescue-exit moderate           # أكثر حساسية
    --rescue-exit aggressive         # أقصى حساسية (الأخطر)

    # ضبط العتبات يدوياً:
    --rescue-margin 0.05
    --rescue-floor 0.15
    --rescue-accel-kappa 0.5
    --rescue-gauge-kappa 0.3
"""

import ast
import os
import shutil
import sys
from datetime import datetime

MARKER = "# [RESCUE-EXIT-APPLIED]"
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
    bak = f"{path}.bak_rescue_{ts}"
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
        fail(f"[{label}] anchor not found\n"
             f"Expected prefix: {old[:120]!r}")
    if n > 1:
        fail(f"[{label}] ambiguous ({n} matches)")
    vlog(f"    [{label}] replaced ({len(old)}→{len(new)} chars)")
    return content.replace(old, new, 1)


def must_insert_before(content, anchor, block, label):
    idx = content.find(anchor)
    if idx < 0:
        fail(f"[{label}] anchor not found: {anchor[:120]!r}")
    if content.count(anchor) > 1:
        fail(f"[{label}] anchor ambiguous ({content.count(anchor)} matches)")
    vlog(f"    [{label}] inserted before anchor ({len(block)} chars)")
    return content[:idx] + block + content[idx:]


# ═══════════════════════════════════════════════════════════════
# CONFIG BLOCK
# ═══════════════════════════════════════════════════════════════

CONFIG_BLOCK = '''
    # ══ [RESCUE EXIT — Loss Zone Guardian] ══
    # Fills the "dead zone" between BEEsc trigger and SL.
    # Math: P_rescue = P_BM × f_phys × f_time
    #       Exit if P_rescue < max(1 - L/L_SL - margin, floor)
    #
    # Opt-in only: enable via --rescue-exit
    # Behavior with flag OFF: zero overhead, zero behavior change
    RESCUE_EXIT_ENABLED: bool = False
    RESCUE_EXIT_MODE: str = "conservative"   # conservative | moderate | aggressive
    RESCUE_ONLY_AFTER_BEESC: bool = True     # start rescue only after BEEsc fired
    RESCUE_MIN_BARS_AFTER_BEESC: int = 2     # min bars in dead zone before rescue
    RESCUE_MARGIN: float = 0.05              # safety buffer for exit rule
    RESCUE_FLOOR: float = 0.15               # absolute P_floor (min hope to stay)
    RESCUE_ACCEL_KAPPA: float = 0.5          # accel contribution to drift
    RESCUE_GAUGE_KAPPA: float = 0.3          # gauge contribution to drift
    RESCUE_PHYS_GAMMA: float = 0.5           # physics multiplier strength
    RESCUE_PHYS_MIN: float = 0.4             # clip f_phys low
    RESCUE_PHYS_MAX: float = 1.6             # clip f_phys high
    RESCUE_DRIFT_HIST_BARS: int = 20         # drift estimation window
    RESCUE_LOG_VERBOSE: bool = False         # log every rescue check

'''


# ═══════════════════════════════════════════════════════════════
# CORE FUNCTIONS BLOCK
# ═══════════════════════════════════════════════════════════════

FUNCTIONS_BLOCK = r'''
# ═══════════════════════════════════════════════════════════════
# [RESCUE EXIT] — Loss Zone Guardian
# Fills the "dead zone" between BEEsc trigger and SL with a
# state-based early exit.
# ═══════════════════════════════════════════════════════════════


def _rescue_compute_physics_z(ad, fi, action):
    """
    Compute physics z-score in [-1, +1] for the current bar.

    Each component is normalized to [-1, +1]:
        +1 = physics supports holding (hopeful)
        -1 = physics against holding (breaking)
    """
    sign = 1.0 if action == "BUY" else -1.0
    components = {}
    weights = {
        'accel':    0.30,
        'gauge':    0.20,
        'friction': 0.10,
        'dfree':    0.10,
        'dh':       0.10,
        'ema':      0.15,
        'score':    0.05,
    }

    # 1. Accel alignment
    try:
        a_now = float(ad.geodesic_accel[fi])
        win = ad.geodesic_accel[max(0, fi - 100):fi + 1]
        a_std = float(np.std(win)) + 1e-9
        z = sign * a_now / a_std
        components['accel'] = float(np.tanh(z * 0.5))
    except Exception:
        components['accel'] = 0.0

    # 2. Gauge strength vs p90 (normalized to [-1, +1])
    try:
        g_now = float(ad.gauge_force[fi])
        g_past = ad.gauge_force[max(0, fi - 100):fi + 1]
        g_p90 = float(np.percentile(g_past, 90)) + 1e-9
        components['gauge'] = float(np.clip(2.0 * (g_now / g_p90) - 1.0,
                                             -1.0, 1.0))
    except Exception:
        components['gauge'] = 0.0

    # 3. Friction (low = good) normalized
    try:
        f_now = float(ad.friction[fi])
        f_past = ad.friction[max(0, fi - 100):fi + 1]
        f_med = float(np.median(f_past)) + 1e-9
        ratio = f_now / f_med
        components['friction'] = float(np.clip(2.0 - 2.0 * ratio, -1.0, 1.0))
    except Exception:
        components['friction'] = 0.0

    # 4. dF (free energy change)
    try:
        df_now = float(ad.dF[fi])
        df_past = ad.dF[max(0, fi - 100):fi + 1]
        df_std = float(np.std(df_past)) + 1e-9
        components['dfree'] = float(np.tanh(-sign * df_now / (2.0 * df_std)))
    except Exception:
        components['dfree'] = 0.0

    # 5. dH (entropy change)
    try:
        dh_now = float(ad.dH[fi])
        dh_past = ad.dH[max(0, fi - 100):fi + 1]
        dh_std = float(np.std(dh_past)) + 1e-9
        components['dh'] = float(np.tanh(-sign * dh_now / (2.0 * dh_std)))
    except Exception:
        components['dh'] = 0.0

    # 6. EMA slope
    try:
        if fi >= 50 and fi < len(ad.ema200):
            slope = (float(ad.ema200[fi])
                     - float(ad.ema200[fi - 50])) / 50.0
            components['ema'] = float(np.tanh(sign * slope * 100.0))
        else:
            components['ema'] = 0.0
    except Exception:
        components['ema'] = 0.0

    # 7. Score freshness
    try:
        sc_now = float(ad.score[fi]) if 0 <= fi < len(ad.score) else 0.0
        components['score'] = float(np.tanh(sc_now * 0.3))
    except Exception:
        components['score'] = 0.0

    z_phys = 0.0
    for k, w in weights.items():
        z_phys += w * components[k]

    return float(np.clip(z_phys, -1.0, 1.0)), components


def _rescue_compute_physics_multiplier(ad, fi, action):
    """f_phys = clip(1 + gamma * z_phys, min, max)"""
    try:
        z_phys, _ = _rescue_compute_physics_z(ad, fi, action)
    except Exception:
        return 1.0
    gamma = float(getattr(CFG, 'RESCUE_PHYS_GAMMA', 0.5))
    lo = float(getattr(CFG, 'RESCUE_PHYS_MIN', 0.4))
    hi = float(getattr(CFG, 'RESCUE_PHYS_MAX', 1.6))
    return float(np.clip(1.0 + gamma * z_phys, lo, hi))


def _rescue_compute_drift(ad, fi, action, cfg):
    """
    μ_eff = mean_return(window) + κ_a·sign·accel + κ_g·sign·gauge·sign(dH)
    """
    sign = 1.0 if action == "BUY" else -1.0
    n_hist = int(getattr(cfg, 'RESCUE_DRIFT_HIST_BARS', 20))
    n_hist = max(5, n_hist)

    # Base drift (mean of last N log-returns)
    r_hist = 0.0
    try:
        lo = max(1, fi - n_hist)
        cl = ad.closes[lo:fi + 1]
        if len(cl) >= 2:
            lr = np.diff(np.log(np.maximum(cl, 1e-12)))
            r_hist = float(np.mean(lr)) if len(lr) > 0 else 0.0
    except Exception:
        r_hist = 0.0

    # Accel contribution
    kappa_a = float(getattr(cfg, 'RESCUE_ACCEL_KAPPA', 0.5))
    try:
        accel = float(ad.geodesic_accel[fi]) if fi < len(ad.geodesic_accel) else 0.0
    except Exception:
        accel = 0.0
    mu_accel = kappa_a * sign * accel

    # Gauge contribution
    kappa_g = float(getattr(cfg, 'RESCUE_GAUGE_KAPPA', 0.3))
    try:
        gauge = float(ad.gauge_force[fi]) if fi < len(ad.gauge_force) else 0.0
        dH_now = float(ad.dH[fi]) if fi < len(ad.dH) else 0.0
        dH_sign = 1.0 if dH_now >= 0 else -1.0
    except Exception:
        gauge = 0.0
        dH_sign = 0.0
    mu_gauge = kappa_g * sign * gauge * dH_sign

    mu_eff = r_hist + mu_accel + mu_gauge
    # Guard against zero drift (avoid division by zero)
    if abs(mu_eff) < 1e-9:
        mu_eff = 1e-9 * sign if sign != 0 else 1e-9
    return float(mu_eff)


def _rescue_compute_P_BM(mu, sigma, a, b):
    """
    Classic two-sided barrier Brownian probability:
        P_BM = (1 - exp(-2μb/σ²)) / (1 - exp(-2μ(a+b)/σ²))

    - μ: drift (log-return per bar)
    - σ: volatility (log-return std per bar)
    - a: log distance to entry (positive)
    - b: log distance to SL (positive)
    """
    if sigma <= 1e-9:
        return 0.5
    sv = sigma * sigma
    try:
        z = -2.0 * mu / sv
        na = z * b
        da = z * (a + b)
        # Numerically stable exp for small/large args
        if abs(na) > 40.0:
            num = 1.0 if na > 0 else -1.0
        else:
            num = 1.0 - np.exp(na)
        if abs(da) > 40.0:
            den = 1.0 if da > 0 else -1.0
        else:
            den = 1.0 - np.exp(da)
        if abs(den) < 1e-9:
            P = b / (a + b) if (a + b) > 0 else 0.5
        else:
            P = num / den
        if not np.isfinite(P):
            P = b / (a + b) if (a + b) > 0 else 0.5
        return float(np.clip(P, 0.0, 1.0))
    except Exception:
        return b / (a + b) if (a + b) > 0 else 0.5


def _rescue_compute_P(ad, fi, action, entry, sl, price, bars_held, cfg):
    """
    Unified rescue probability:
        P_rescue = P_BM(μ_eff, σ, a, b) × f_phys × f_time
    Returns dict with all components.
    """
    out = {
        'P': 1.0, 'P_BM': 0.5, 'f_phys': 1.0, 'f_time': 1.0,
        'a': 0.0, 'b': 0.0, 'mu': 0.0, 'sigma': 0.01,
        'L_now_frac': 0.0, 'L_sl_frac': 0.01,
        'threshold': 0.5, 'error': None,
    }
    try:
        if ad is None or fi < 3 or entry <= 0 or sl <= 0 or price <= 0:
            out['error'] = 'invalid_inputs'
            return out

        # Distances in log space
        if action == "BUY":
            a = float(np.log(entry / price))
            b = float(np.log(price / sl))
        else:
            a = float(np.log(price / entry))
            b = float(np.log(sl / price))
        if a <= 0 or b <= 0:
            out['error'] = 'invalid_distances'
            return out
        out['a'] = a
        out['b'] = b

        # Volatility (per bar)
        sigma = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
        if not np.isfinite(sigma) or sigma <= 1e-6:
            sigma = 0.01
        out['sigma'] = sigma

        # Drift
        mu = _rescue_compute_drift(ad, fi, action, cfg)
        out['mu'] = mu

        # P_BM
        P_BM = _rescue_compute_P_BM(mu, sigma, a, b)
        out['P_BM'] = P_BM

        # Physics multiplier
        f_phys = _rescue_compute_physics_multiplier(ad, fi, action)
        out['f_phys'] = f_phys

        # Time factor
        max_hold = int(getattr(cfg, 'MAX_HOLD_BARS', 2000))
        try:
            max_hold_eff = effective_bars(max_hold)
        except Exception:
            max_hold_eff = max_hold
        t_rem = max(0.0, float(max_hold_eff) - float(bars_held))
        t_need = a / (abs(mu) + 1e-9)
        if t_rem <= 0:
            f_time = 0.0
        elif t_need <= 0:
            f_time = 1.0
        else:
            f_time = float(min(1.0, t_rem / t_need))
        out['f_time'] = f_time

        # Final P
        P = float(np.clip(P_BM * f_phys * f_time, 0.0, 1.0))
        out['P'] = P

        # Loss fractions
        L_now_frac = abs(entry - price) / entry
        L_sl_frac = abs(entry - sl) / entry
        out['L_now_frac'] = float(L_now_frac)
        out['L_sl_frac'] = float(max(L_sl_frac, 1e-9))

        # Threshold
        margin = float(getattr(cfg, 'RESCUE_MARGIN', 0.05))
        floor = float(getattr(cfg, 'RESCUE_FLOOR', 0.15))
        th_math = 1.0 - L_now_frac / max(L_sl_frac, 1e-9) - margin
        th = max(th_math, floor)
        out['threshold'] = float(np.clip(th, 0.0, 1.0))

        return out
    except Exception as e:
        out['error'] = f'exception:{e}'
        return out


def _rescue_check(pos, ad, current_ci, current_fi, bars_held,
                  be_esc_done, cfg):
    """
    Main decision function.
    Returns (should_exit: bool, reason: str, info: dict).
    """
    if not getattr(cfg, 'RESCUE_EXIT_ENABLED', False):
        return False, 'disabled', {}
    if not getattr(cfg, 'RESCUE_ONLY_AFTER_BEESC', True):
        pass  # allow rescue even without BEEsc
    elif not be_esc_done:
        return False, 'beesc_not_done', {}
    if ad is None:
        return False, 'no_data', {}
    if bars_held < int(getattr(cfg, 'RESCUE_MIN_BARS_AFTER_BEESC', 2)):
        return False, 'too_early', {}
    if current_fi < 3 or current_fi >= len(ad.score):
        return False, 'bad_index', {}

    try:
        entry = float(pos.get('entry') if isinstance(pos, dict)
                      else pos.entry_px)
        sl = float(pos.get('sl') if isinstance(pos, dict)
                   else pos.trail_sl)
        action = str(pos.get('action') if isinstance(pos, dict)
                     else pos.signal.action)
        price = float(ad.closes[current_ci])
        tp = float(pos.get('tp1') if isinstance(pos, dict)
                   else pos.signal.tp1)
    except Exception as e:
        return False, f'extract_error:{e}', {}

    info = _rescue_compute_P(ad, current_fi, action, entry, sl, price,
                             bars_held, cfg)
    if info.get('error'):
        return False, f"calc_error:{info['error']}", info

    P = float(info['P'])
    th = float(info['threshold'])
    L_now = info['L_now_frac']
    L_sl = info['L_sl_frac']

    if P < th:
        return True, (f"Rescue(P={P:.2f}<th={th:.2f}, "
                      f"L={L_now*100:.1f}%/{L_sl*100:.1f}%, "
                      f"a={info['a']:.4f}, b={info['b']:.4f}, "
                      f"μ={info['mu']:.4f})"), info

    return False, 'ok', info

'''


# ═══════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════

def patch_01_config(content):
    if "RESCUE_EXIT_ENABLED" in content:
        log("  [config] already present — skip")
        return content
    anchor = "    # ══ [WATCH ENTRY OFFSET — dynamic, fills on touch] ══\n"
    if anchor not in content:
        fail("[config] WATCH ENTRY OFFSET comment not found")
    return must_insert_before(content, anchor, CONFIG_BLOCK, "config")


def patch_02_functions(content):
    if "def _rescue_check(" in content:
        log("  [functions] already present — skip")
        return content
    anchor = 'def build_signals(assets, mode="backtest"):'
    return must_insert_before(content, anchor, FUNCTIONS_BLOCK + "\n\n", "functions")


def patch_03_advance_backtest(content):
    """Add rescue check to _advance (backtest), between BROKEN/Apex and SL/TP."""
    if "# ══ [RESCUE EXIT — Backtest] ══" in content:
        log("  [_advance] already patched — skip")
        return content

    # We insert the rescue check right BEFORE the SL/TP hit test.
    # In _advance, the SL/TP block appears inside BOTH the sub-bar loop
    # and the main-bar branch. We insert once in the main-bar path right
    # after the physics exits and before the SL/TP check, so it applies
    # uniformly.

    # Find the anchor: after Apex/Topo-Div physics exits, before MaxHold.
    anchor = """        # ── Physics-based exits (close-only, per main bar) ──
        is_apex, apex_rsn = False, ""
        if getattr(CFG, 'APEX_ENABLED', True):
            is_apex, apex_rsn = check_thermodynamic_apex(
                sig.action, pos.entry_px, p, ad, fi
            )
        if is_apex:
            pos.trail_sl = trail_sl; pos.current_ci = cidx
            return p, apex_rsn, cidx
"""
    if anchor not in content:
        fail("[_advance] physics-exits anchor not found")

    # We add rescue right after this block.
    rescue_backtest = """

        # ══ [RESCUE EXIT — Backtest] ══
        if getattr(CFG, 'RESCUE_EXIT_ENABLED', False):
            try:
                _bars_held = cidx - pos.entry_ci
                _be_done = bool(getattr(pos, '_be_esc_done', False))
                _rescue_exit, _rescue_rsn, _rescue_info = _rescue_check(
                    {'entry': float(pos.entry_px),
                     'sl': float(trail_sl),
                     'action': str(sig.action),
                     'tp1': float(sig.tp1)},
                    ad, cidx, fi, _bars_held, _be_done, CFG
                )
                if getattr(CFG, 'RESCUE_LOG_VERBOSE', False) and _rescue_info:
                    log.debug(
                        f"[Rescue-BT] {sig.symbol} {sig.action} "
                        f"P={_rescue_info.get('P', 0):.3f} "
                        f"th={_rescue_info.get('threshold', 0):.3f} "
                        f"L={_rescue_info.get('L_now_frac', 0)*100:.2f}% "
                        f"bars={_bars_held} be={_be_done}"
                    )
                if _rescue_exit:
                    pos.trail_sl = trail_sl
                    pos.current_ci = cidx
                    log.info(
                        f"[Rescue-BT] {sig.symbol} {sig.action} EXIT "
                        f"@ {p:.6f} — {_rescue_rsn}"
                    )
                    return p, _rescue_rsn, cidx
            except Exception as _e:
                log.debug(f"[Rescue-BT] error {sig.symbol}: {_e}")
"""

    # Insert rescue after the Apex block, before Topo-Div continuation.
    # The Apex block ends with "return p, apex_rsn, cidx\n". We append after that.
    new_anchor = anchor + rescue_backtest
    return must_replace(content, anchor, new_anchor, "_advance-rescue")


def patch_04_run_live(content):
    """Add rescue check to run_live, after Apex/TopoDiv and before SL/TP."""
    if "# ══ [RESCUE EXIT — Live] ══" in content:
        log("  [run_live] already patched — skip")
        return content

    # In run_live, we insert rescue just BEFORE the SL/TP check.
    # The anchor is the start of the SL/TP check block.
    anchor = """                # ── SL / TP ──
                if not ex:
                    if pos['action'] == "BUY":
                        if price <= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price >= pos.get('tp1', 1e18): ex = True; rsn = "Hard TP"
                    else:
                        if price >= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price <= pos.get('tp1', 0.): ex = True; rsn = "Hard TP"
"""
    if anchor not in content:
        fail("[run_live] SL/TP anchor not found")

    rescue_live = """                # ══ [RESCUE EXIT — Live] ══
                if (not ex
                        and getattr(CFG, 'RESCUE_EXIT_ENABLED', False)
                        and ad is not None
                        and fi is not None and fi >= 3):
                    try:
                        _cur_fi_resc = fi
                        _be_done_resc = bool(pos.get('_be_esc_done', False))
                        _entry_ci_resc = int(pos.get('_entry_ci', 0) or 0)
                        _bars_held_resc = max(0, _cur_fi_resc
                                              - max(0, _entry_ci_resc - ad.feat_start))
                        _resc_exit, _resc_rsn, _resc_info = _rescue_check(
                            {'entry': float(pos.get('entry') or 0),
                             'sl': float(pos.get('sl') or 0),
                             'action': str(pos.get('action') or 'BUY'),
                             'tp1': float(pos.get('tp1') or 0)},
                            ad, len(ad.closes) - 2, _cur_fi_resc,
                            _bars_held_resc, _be_done_resc, CFG
                        )
                        if (getattr(CFG, 'RESCUE_LOG_VERBOSE', False)
                                and _resc_info):
                            log.debug(
                                f"[Rescue-LV] {sym} {pos.get('action')} "
                                f"P={_resc_info.get('P', 0):.3f} "
                                f"th={_resc_info.get('threshold', 0):.3f} "
                                f"L={_resc_info.get('L_now_frac', 0)*100:.2f}% "
                                f"bars={_bars_held_resc} "
                                f"be={_be_done_resc}"
                            )
                        if _resc_exit:
                            ex = True
                            rsn = _resc_rsn
                            log.info(
                                f"[Rescue-LV] {sym} {pos.get('action')} "
                                f"triggered: {_resc_rsn}"
                            )
                    except Exception as _resc_e:
                        log.debug(f"[Rescue-LV] {sym} error: {_resc_e}")
"""

    new_anchor = rescue_live + "\n" + anchor
    return must_replace(content, anchor, new_anchor, "run_live-rescue")


def patch_05_cli_flags(content):
    if 'p.add_argument("--rescue-exit"' in content:
        log("  [cli] already present — skip")
        return content

    anchor = '''    p.add_argument("--signal-sl-clamp-beesc", action="store_true",
                   help="[Signal-SL] Clamp SL below BEEsc level (default: "
                        "allow crossing — BEEsc disabled when crossed)")'''
    if anchor not in content:
        fail("[cli] --signal-sl-clamp-beesc anchor not found")

    new = anchor + '''
    p.add_argument("--rescue-exit", type=str, nargs="?", const="conservative",
                   default=None,
                   choices=["conservative", "moderate", "aggressive"],
                   help="[Rescue] Enable state-based rescue exit in loss zone "
                        "(default: conservative)")
    p.add_argument("--rescue-margin", type=float, default=None,
                   help="[Rescue] Safety margin (default: 0.05)")
    p.add_argument("--rescue-floor", type=float, default=None,
                   help="[Rescue] Absolute P_floor (default: 0.15)")
    p.add_argument("--rescue-accel-kappa", type=float, default=None,
                   help="[Rescue] Accel drift coefficient (default: 0.5)")
    p.add_argument("--rescue-gauge-kappa", type=float, default=None,
                   help="[Rescue] Gauge drift coefficient (default: 0.3)")
    p.add_argument("--rescue-log-verbose", action="store_true",
                   help="[Rescue] Log every rescue check at DEBUG level")'''
    return must_replace(content, anchor, new, "cli")


def patch_06_argparse(content):
    if 'CFG.RESCUE_EXIT_ENABLED = True' in content:
        log("  [argparse] already present — skip")
        return content

    anchor = '    if args.no_numba: CFG.NUMBA_ENABLED = False\n'
    if anchor not in content:
        fail("[argparse] no_numba anchor not found")

    new = anchor + '''
    # ══ [RESCUE EXIT] ══
    if getattr(args, "rescue_exit", None) is not None:
        CFG.RESCUE_EXIT_ENABLED = True
        CFG.RESCUE_EXIT_MODE = str(args.rescue_exit)
        _mode = CFG.RESCUE_EXIT_MODE
        if _mode == "conservative":
            CFG.RESCUE_MARGIN = 0.05
            CFG.RESCUE_FLOOR = 0.15
            CFG.RESCUE_MIN_BARS_AFTER_BEESC = 2
        elif _mode == "moderate":
            CFG.RESCUE_MARGIN = 0.03
            CFG.RESCUE_FLOOR = 0.12
            CFG.RESCUE_MIN_BARS_AFTER_BEESC = 2
        elif _mode == "aggressive":
            CFG.RESCUE_MARGIN = 0.02
            CFG.RESCUE_FLOOR = 0.10
            CFG.RESCUE_MIN_BARS_AFTER_BEESC = 1
        log.info(
            f"[Rescue] ENABLED mode={_mode} "
            f"margin={CFG.RESCUE_MARGIN} "
            f"floor={CFG.RESCUE_FLOOR} "
            f"min_bars={CFG.RESCUE_MIN_BARS_AFTER_BEESC}"
        )
    # Per-parameter overrides
    if getattr(args, "rescue_margin", None) is not None:
        CFG.RESCUE_MARGIN = float(args.rescue_margin)
    if getattr(args, "rescue_floor", None) is not None:
        CFG.RESCUE_FLOOR = float(args.rescue_floor)
    if getattr(args, "rescue_accel_kappa", None) is not None:
        CFG.RESCUE_ACCEL_KAPPA = float(args.rescue_accel_kappa)
    if getattr(args, "rescue_gauge_kappa", None) is not None:
        CFG.RESCUE_GAUGE_KAPPA = float(args.rescue_gauge_kappa)
    if getattr(args, "rescue_log_verbose", False):
        CFG.RESCUE_LOG_VERBOSE = True
    if not getattr(args, "rescue_exit", None):
        log.info("[Rescue] DISABLED (use --rescue-exit to enable)")
'''
    return must_replace(content, anchor, new, "argparse")


def patch_07_trade_log_fields(content):
    """Add rescue_p to trade log (for A/B analysis)."""
    if "'rescue_p':" in content or "rescue_p=" in content:
        log("  [trade_log] rescue_p already present — skip")
        return content

    # Extend _trade_log_from_backtest record
    old = """            'sl_dist_initial': float(getattr(pos, 'sl_dist_initial', 0.0)),
        }
        rec.update(_extract_entry_features_for_log(sig, ad))"""
    new = """            'sl_dist_initial': float(getattr(pos, 'sl_dist_initial', 0.0)),
            'be_esc_done': bool(getattr(pos, '_be_esc_done', False)),
            'rescue_p': float(getattr(pos, '_rescue_p', -1.0)),
        }
        rec.update(_extract_entry_features_for_log(sig, ad))"""
    if old in content:
        content = must_replace(content, old, new, "trade_log-bt")
    else:
        vlog("    [trade_log-bt] anchor not found — skip")

    return content


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
        log("Rescue Exit already applied. Use --force to re-apply.")
        return 0

    ok, err = verify_syntax(content, "PRE")
    if not ok:
        fail(f"File has syntax errors: {err}")

    log(f"File: {path} ({len(content)} chars, {content.count(chr(10))} lines)")

    if not args.dry_run:
        backup(path)

    try:
        content = patch_01_config(content)
        content = patch_02_functions(content)
        content = patch_03_advance_backtest(content)
        content = patch_04_run_live(content)
        content = patch_05_cli_flags(content)
        content = patch_06_argparse(content)
        content = patch_07_trade_log_fields(content)

        content = MARKER + "\n" + content

        ok, err = verify_syntax(content, "POST")
        if not ok:
            fail(f"Result has syntax errors: {err}")

        if args.dry_run:
            log("DRY RUN: syntax OK. Would write to file.")
            log("")
            log("Summary:")
            log("  • Config: RESCUE_EXIT_* (12 fields)")
            log("  • Functions: _rescue_compute_P, _rescue_check, helpers")
            log("  • _advance: rescue check between Apex and SL/TP")
            log("  • run_live: rescue check between Apex/TopoDiv and SL/TP")
            log("  • CLI: --rescue-exit, --rescue-margin, --rescue-floor,")
            log("         --rescue-accel-kappa, --rescue-gauge-kappa,")
            log("         --rescue-log-verbose")
            log("  • Trade log: be_esc_done, rescue_p fields")
            return 0

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
        log(f"Saved: {path}  ({content.count(chr(10))} lines)")
        log("=" * 60)
        log("Rescue Exit applied successfully.")
        log("")
        log("Default: DISABLED (zero behavior change).")
        log("")
        log("To enable, add to your run command:")
        log("  --rescue-exit                   # conservative (recommended)")
        log("  --rescue-exit moderate          # more aggressive")
        log("  --rescue-exit aggressive        # most aggressive (risky)")
        log("")
        log("Manual overrides:")
        log("  --rescue-margin 0.05")
        log("  --rescue-floor 0.15")
        log("  --rescue-accel-kappa 0.5")
        log("  --rescue-gauge-kappa 0.3")
        log("  --rescue-log-verbose")
        log("")
        log("IMPORTANT — A/B test before production:")
        log("  A: python3 bot.py ... (baseline, no rescue)")
        log("  B: python3 bot.py ... --rescue-exit conservative")
        log("  C: python3 bot.py ... --rescue-exit moderate")
        log("  Compare: E[ln], MaxDD, #Rescue exits, Rescue avg PnL")
        log("=" * 60)
        return 0

    except SystemExit:
        raise
    except Exception as e:
        log(f"FAILED: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
