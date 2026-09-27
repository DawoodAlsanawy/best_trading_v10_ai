#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
explosion_timing_test_v2.py

نسخة محسّنة من اختبار التنبؤ بوقت الانفجار.
يختبر 6 تهيئات مختلفة في نفس التشغيل:

  Config 1: Baseline (rolling θ + raw jerk + no filter)
  Config 2: A only (rolling θ + raw jerk + wide filter)
  Config 3: B only (rolling θ + smoothed jerk + no filter)
  Config 4: C only (fixed θ + raw jerk + no filter)
  Config 5: A+B (rolling θ + smoothed jerk + wide filter)
  Config 6: A+B+C (fixed θ + smoothed jerk + wide filter) ← الأفضل المتوقع

التحسينات المختبرة:
  A: wide filter (frac > 0.80, λ ∈ [0.3, 6], |s|/j < 2)
  B: median-smoothed jerk/snap (window=5)
  C: fixed θ (percentile 90 من |a| على أول 50% من البيانات)

الإخراج: explosion_timing_v2_report.txt + explosion_timing_v2_data.json

الاستخدام:
  python explosion_timing_test_v2.py --timeframe 4h --history-days 730 --nassets 30
"""

import argparse
import importlib.util
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ════════════════════════════════════════════════════════════════
# 0. اكتشاف البوت واستيراده
# ════════════════════════════════════════════════════════════════

BOT_CANDIDATES = [
    "trading.py",
    "trading_best_version_with_tf4h_and_his_days_30.py",
    "best_trading_bot_22_9_2026.py",
]


def detect_bot_file(explicit=None):
    if explicit:
        if not os.path.exists(explicit):
            raise FileNotFoundError(f"Bot not found: {explicit}")
        return explicit
    for c in BOT_CANDIDATES:
        if os.path.exists(c):
            return c
    for f in os.listdir("."):
        if f.endswith(".py") and "trading" in f.lower():
            return f
    raise FileNotFoundError(f"Could not find bot. Tried: {BOT_CANDIDATES}")


def import_bot(path):
    abs_path = os.path.abspath(path)
    spec = importlib.util.spec_from_file_location("bot_module", abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bot_module"] = mod
    spec.loader.exec_module(mod)
    return mod


# ════════════════════════════════════════════════════════════════
# 1. إعداد البوت
# ════════════════════════════════════════════════════════════════

def setup_bot_cfg(bot, timeframe, history_days, n_assets):
    bot.CFG.mode = "backtest"
    bot.CFG.timeframe = timeframe
    bot.CFG.history_days = int(history_days)
    bot.CFG.n_assets = int(n_assets)

    for attr, val in [
        ("SINGULARITY_MODE", False),
        ("SING_TIMING_ENABLED", False),
        ("SING_ACTIVE_MARKETABLE", False),
        ("SING_FUNDING_GUARD_ENABLED", False),
        ("SING_RISK_BOOST_ENABLED", False),
        ("FILTER_ENABLED", False),
        ("RULE_FILTER_ENABLED", False),
        ("ML_FILTER_ENABLED", False),
        ("ASSET_CACHE_ENABLED", True),
        ("PARALLEL_PROCESSING", False),
    ]:
        try:
            setattr(bot.CFG, attr, val)
        except Exception:
            pass

    try:
        import ccxt
        _probe = ccxt.binance()
        tf_scale, tf_secs, tf_hours = bot.compute_tf_scale(_probe, timeframe)
    except Exception:
        tf_scale, tf_secs, tf_hours = bot.compute_tf_scale(None, timeframe)

    bot.CFG.TF_SCALE = tf_scale
    bot.CFG.TF_SECONDS = tf_secs
    bot.CFG.TF_HOURS = tf_hours

    _tf_h = max(float(tf_hours), 1e-6)
    _n_min = int(np.ceil(float(getattr(bot.CFG, 'N_HOURS', 24.0)) / _tf_h))
    _w_min = int(np.ceil(float(getattr(bot.CFG, 'W_HOURS', 20.0)) / _tf_h))
    _l_min = int(np.ceil(float(getattr(bot.CFG, 'L_HOURS', 10.0)) / _tf_h))

    if bot.CFG.N < _n_min:
        bot.CFG.N = _n_min
    if bot.CFG.W < _w_min:
        bot.CFG.W = _w_min
    if bot.CFG.L < _l_min:
        bot.CFG.L = _l_min

    _adv_h = float(getattr(bot.CFG, 'ADV_HOURS', 24.0))
    bot.CFG.ADV_BARS = max(1, int(round(_adv_h / _tf_h)))

    print(f"[Setup] TF={timeframe}  TF_SCALE={tf_scale:.3f}  "
          f"TF_HOURS={tf_hours:.3f}")
    print(f"[Setup] N={bot.CFG.N}  W={bot.CFG.W}  L={bot.CFG.L}")


# ════════════════════════════════════════════════════════════════
# 2. تشغيل الـ pipeline
# ════════════════════════════════════════════════════════════════

def run_pipeline(bot):
    import ccxt

    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })

    print("[Pipeline] Scanning top assets...")
    syms = bot.scan_top_assets(exchange, bot.CFG.n_assets)
    print(f"[Pipeline] {len(syms)} symbols selected")

    print(f"[Pipeline] Fetching {bot.CFG.history_days} days...")
    t0 = time.time()
    raw = bot.fetch_all(
        syms, exchange, bot.CFG.timeframe,
        bot.CFG.history_days, workers=8
    )
    print(f"[Pipeline] Fetched {len(raw)} symbols in {time.time()-t0:.1f}s")

    print("[Pipeline] Processing assets...")
    t0 = time.time()
    assets: Dict[str, Any] = {}
    n_failed = 0
    for i, (sym, df) in enumerate(raw.items()):
        try:
            ad = bot.process_asset(
                sym, df,
                current_capital=bot.CFG.INITIAL_CAPITAL,
            )
            if ad is not None:
                assets[sym] = ad
            else:
                n_failed += 1
        except Exception as e:
            n_failed += 1
            print(f"  [WARN] {sym}: {e}")
        if (i + 1) % 5 == 0:
            print(f"    processed {i+1}/{len(raw)}")
    print(f"[Pipeline] Processed {len(assets)}/{len(raw)} assets "
          f"in {time.time()-t0:.1f}s (failed={n_failed})")

    return assets


# ════════════════════════════════════════════════════════════════
# 3. دوال مساعدة
# ════════════════════════════════════════════════════════════════

def compute_rolling_theta(ad, fi: int, lookback: int = 200,
                           pct: float = 0.90) -> Optional[float]:
    """θ متدحرج = percentile 90 من |a| على آخر lookback شمعة."""
    if fi < 30:
        return None
    start = max(0, fi - lookback)
    window = ad.geodesic_accel[start:fi + 1]
    if len(window) < 30:
        return None
    abs_w = np.abs(window).astype(np.float64)
    theta = float(np.percentile(abs_w, pct * 100))
    if theta < 1e-12 or not np.isfinite(theta):
        return None
    return theta


def compute_fixed_theta(ad, train_end: int,
                         pct: float = 0.90) -> Optional[float]:
    """θ ثابت = percentile 90 من |a| على بيانات التدريب فقط."""
    if train_end < 100:
        return None
    window = ad.geodesic_accel[:train_end]
    abs_w = np.abs(window).astype(np.float64)
    theta = float(np.percentile(abs_w, pct * 100))
    if theta < 1e-12 or not np.isfinite(theta):
        return None
    return theta


def compute_smoothed_jerk_snap(ad, fi: int, sign: float,
                                window: int = 5
                                ) -> Tuple[float, float]:
    """
    يُعيد (j_smooth, s_smooth) باستخدام median على window شموع.

    j(t) = a(t) - a(t-1)
    s(t) = j(t) - j(t-1) = a(t) - 2a(t-1) + a(t-2)

    j_smooth = median( [j(fi-k) for k in 0..window-1] )
    s_smooth = median( [s(fi-k) for k in 0..window-2] )  # نافذة أقصر بـ 1
    """
    n = len(ad.geodesic_accel)
    if fi < window + 2:
        # لا يمكن التنعيم
        if fi >= 2:
            j_raw = (float(ad.geodesic_accel[fi])
                     - float(ad.geodesic_accel[fi-1])) * sign
            s_raw = ((float(ad.geodesic_accel[fi])
                      - 2*float(ad.geodesic_accel[fi-1])
                      + float(ad.geodesic_accel[fi-2])) * sign)
            return j_raw, s_raw
        return 0.0, 0.0

    j_vals = []
    for k in range(window):
        idx = fi - k
        if idx < 1:
            break
        j_k = (float(ad.geodesic_accel[idx])
               - float(ad.geodesic_accel[idx-1])) * sign
        j_vals.append(j_k)

    s_vals = []
    for k in range(window - 1):
        idx = fi - k
        if idx < 2:
            break
        s_k = ((float(ad.geodesic_accel[idx])
                - 2*float(ad.geodesic_accel[idx-1])
                + float(ad.geodesic_accel[idx-2])) * sign)
        s_vals.append(s_k)

    j_smooth = float(np.median(j_vals)) if j_vals else 0.0
    s_smooth = float(np.median(s_vals)) if s_vals else 0.0
    return j_smooth, s_smooth


def predict_three_models(a_s: float, j_s: float, s_s: float,
                          theta: float) -> Tuple[
                              Optional[float], Optional[float],
                              Optional[float], Optional[float]]:
    """نفس دالة v1."""
    delta = theta - a_s
    if delta <= 0.0 or j_s <= 0.0:
        return None, None, None, None

    dt_lin = delta / j_s if j_s > 1e-15 else None

    dt_snap = None
    if abs(s_s) > 1e-15:
        disc = j_s * j_s + 2.0 * s_s * delta
        if disc >= 0.0:
            _num = -j_s + np.sqrt(disc)
            if abs(s_s) > 1e-15:
                _dt = _num / s_s
                if _dt > 0.0 and np.isfinite(_dt):
                    dt_snap = float(_dt)
    else:
        dt_snap = dt_lin

    dt_exp = None
    lam = None
    if j_s > 1e-15:
        lam_val = s_s / j_s
        if np.isfinite(lam_val) and lam_val > 1e-12:
            _inner = 1.0 + lam_val * delta / j_s
            if _inner > 0.0:
                _dt = (1.0 / lam_val) * np.log(_inner)
                if _dt > 0.0 and np.isfinite(_dt):
                    dt_exp = float(_dt)
                    lam = float(lam_val)

    return dt_lin, dt_snap, dt_exp, lam


def find_actual_delta_tau(ad, fi: int, sign: float,
                           theta: float, max_horizon: int) -> int:
    """يعيد أول k حيث a(fi+k) × sign >= θ. أو -1."""
    n = len(ad.geodesic_accel)
    for k in range(1, max_horizon + 1):
        nfi = fi + k
        if nfi >= n:
            return -1
        a_k = float(ad.geodesic_accel[nfi]) * sign
        if a_k >= theta:
            return k
    return -1


# ════════════════════════════════════════════════════════════════
# 4. توليد النقاط المرشحة
# ════════════════════════════════════════════════════════════════

def generate_candidates(assets, max_horizon: int,
                         smooth_window: int = 5) -> List[Dict]:
    """
    يُولّد كل النقاط التي قد تكون تنبؤات.
    كل نقطة تحمل كل القيم المطلوبة لكل التهيئات.
    """
    all_candidates = []
    n_assets = len(assets)

    for i, (sym, ad) in enumerate(assets.items()):
        try:
            n = len(ad.geodesic_accel)
            train_end = int(getattr(ad, 'train_end', n // 2))
            feat_start = int(getattr(ad, 'feat_start', 0))

            if train_end < 100 or n < train_end + 30:
                continue

            theta_fixed = compute_fixed_theta(ad, train_end, 0.90)
            if theta_fixed is None:
                continue

            per_sym_count = 0
            for action, sign in (("BUY", 1.0), ("SELL", -1.0)):
                for fi in range(train_end + 15, n - max_horizon - 1):
                    a_now_s = float(ad.geodesic_accel[fi]) * sign

                    # شروط أساسية
                    if a_now_s <= 0:
                        continue

                    theta_roll = compute_rolling_theta(ad, fi, 200, 0.90)
                    if theta_roll is None:
                        continue
                    if a_now_s >= theta_roll:
                        continue
                    if a_now_s >= theta_fixed:
                        continue

                    # j و s الخام
                    if fi < 3:
                        continue
                    j_raw = (float(ad.geodesic_accel[fi])
                             - float(ad.geodesic_accel[fi-1])) * sign
                    if j_raw <= 0:
                        continue
                    s_raw = ((float(ad.geodesic_accel[fi])
                              - 2*float(ad.geodesic_accel[fi-1])
                              + float(ad.geodesic_accel[fi-2])) * sign)

                    # j و s المنعَّم
                    j_smooth, s_smooth = compute_smoothed_jerk_snap(
                        ad, fi, sign, window=smooth_window
                    )

                    # actual (بالعتبتين)
                    actual_roll = find_actual_delta_tau(
                        ad, fi, sign, theta_roll, max_horizon
                    )
                    actual_fixed = find_actual_delta_tau(
                        ad, fi, sign, theta_fixed, max_horizon
                    )

                    all_candidates.append({
                        'symbol': sym,
                        'action': action,
                        'fi': int(fi),
                        'ci': int(fi + feat_start),
                        'sign': float(sign),
                        'a_now': float(a_now_s),
                        'j_raw': float(j_raw),
                        's_raw': float(s_raw),
                        'j_smooth': float(j_smooth),
                        's_smooth': float(s_smooth),
                        'theta_roll': float(theta_roll),
                        'theta_fixed': float(theta_fixed),
                        'actual_roll': int(actual_roll),
                        'actual_fixed': int(actual_fixed),
                    })
                    per_sym_count += 1

            print(f"  [{i+1:>3}/{n_assets}] {sym:<14}: "
                  f"candidates={per_sym_count:>7,}")
        except Exception as e:
            print(f"  [{i+1:>3}/{n_assets}] {sym:<14}: FAIL ({e})")

    return all_candidates


# ════════════════════════════════════════════════════════════════
# 5. تقييم تهيئة
# ════════════════════════════════════════════════════════════════

def evaluate_config(candidates: List[Dict], config: Dict) -> List[Dict]:
    """
    يطبق فلاتر التهيئة على النقاط ويعيد السجلات.
    """
    use_fixed_theta = config.get('use_fixed_theta', False)
    use_smooth = config.get('use_smooth', False)
    use_filter = config.get('use_filter', False)
    frac_min = config.get('frac_min', 0.0)
    frac_max = config.get('frac_max', 1.0)
    lam_min = config.get('lam_min', -1e9)
    lam_max = config.get('lam_max', 1e9)
    ratio_max = config.get('ratio_max', 1e9)

    records = []
    for c in candidates:
        theta = c['theta_fixed'] if use_fixed_theta else c['theta_roll']
        actual = c['actual_fixed'] if use_fixed_theta else c['actual_roll']
        a_now = c['a_now']

        if a_now >= theta:
            continue

        j_s = c['j_smooth'] if use_smooth else c['j_raw']
        s_s = c['s_smooth'] if use_smooth else c['s_raw']

        if j_s <= 0:
            continue

        lam = s_s / j_s if j_s > 1e-15 else 0.0
        frac = a_now / theta

        if use_filter:
            if not (frac_min <= frac <= frac_max):
                continue
            if not (lam_min <= lam <= lam_max):
                continue
            if abs(s_s) / max(j_s, 1e-15) > ratio_max:
                continue

        dt_lin, dt_snap, dt_exp, _ = predict_three_models(
            a_now, j_s, s_s, theta
        )

        records.append({
            'symbol': c['symbol'],
            'action': c['action'],
            'fi': c['fi'],
            'a_now': a_now,
            'j_s': j_s,
            's_s': s_s,
            'theta': theta,
            'frac': frac,
            'lam': lam,
            'dt_lin': dt_lin if dt_lin is not None else -1.0,
            'dt_snap': dt_snap if dt_snap is not None else -1.0,
            'dt_exp': dt_exp if dt_exp is not None else -1.0,
            'actual': actual,
            'is_hit': actual > 0,
        })
    return records


# ════════════════════════════════════════════════════════════════
# 6. حساب الإحصاءات
# ════════════════════════════════════════════════════════════════

def _stats(arr):
    a = np.asarray(arr, dtype=np.float64)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return {'n': 0, 'mean': 0., 'median': 0., 'std': 0.,
                'p05': 0., 'p95': 0., 'min': 0., 'max': 0.}
    return {
        'n': int(len(a)),
        'mean': float(np.mean(a)),
        'median': float(np.median(a)),
        'std': float(np.std(a)),
        'p05': float(np.percentile(a, 5)),
        'p95': float(np.percentile(a, 95)),
        'min': float(np.min(a)),
        'max': float(np.max(a)),
    }


def compute_model_metrics(records, model_key: str,
                           restrict_horizon: Optional[Tuple[int, int]] = None
                           ) -> Dict[str, Any]:
    """يحسب MAE، Median AE، R²، Pearson لـ model_key."""
    valid = [r for r in records
             if r['is_hit'] and r[model_key] > 0]
    if restrict_horizon is not None:
        lo, hi = restrict_horizon
        valid = [r for r in valid if lo <= r['actual'] <= hi]

    if len(valid) < 5:
        return {'n': len(valid), 'error': 'insufficient_samples'}

    pred = np.array([r[model_key] for r in valid], dtype=np.float64)
    actual = np.array([r['actual'] for r in valid], dtype=np.float64)

    err = pred - actual
    abs_err = np.abs(err)

    if np.std(pred) > 1e-9 and np.std(actual) > 1e-9:
        pearson = float(np.corrcoef(pred, actual)[0, 1])
    else:
        pearson = 0.0

    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((actual - np.mean(actual)) ** 2))
    r2 = 1.0 - ss_res / max(ss_tot, 1e-12)

    return {
        'n': len(valid),
        'mae': float(np.mean(abs_err)),
        'median_ae': float(np.median(abs_err)),
        'rmse': float(np.sqrt(np.mean(err ** 2))),
        'bias': float(np.mean(err)),
        'pearson': pearson,
        'r2': r2,
    }


# ════════════════════════════════════════════════════════════════
# 7. كتابة التقرير
# ════════════════════════════════════════════════════════════════

def write_report(configs_results: Dict[str, List[Dict]],
                  out_txt: str, out_json: str,
                  bot_file: str, args):
    lines = []
    def W(s=""):
        lines.append(str(s))

    W("=" * 100)
    W("EXPLOSION TIMING TEST v2 — REPORT")
    W("=" * 100)
    W(f"Bot: {bot_file}")
    W(f"Timeframe: {args.timeframe}")
    W(f"History days: {args.history_days}")
    W(f"N assets: {args.nassets}")
    W(f"Max horizon: {args.max_horizon}")
    W(f"Smooth window: {args.smooth_window}")
    W(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    W("=" * 100)
    W()

    # ── Section 1: عدد النقاط ──
    W("=" * 100)
    W("SECTION 1: SAMPLE SIZES PER CONFIG")
    W("=" * 100)
    W(f"{'Config':<45} | {'total':>8} | {'hit':>8} | {'hit%':>6}")
    W("-" * 75)
    for name, recs in configs_results.items():
        n_tot = len(recs)
        n_hit = sum(1 for r in recs if r['is_hit'])
        W(f"{name:<45} | {n_tot:>8,} | {n_hit:>8,} | "
          f"{100*n_hit/max(n_tot,1):>5.1f}%")
    W()

    # ── Section 2: مقارنة شاملة للنماذج عبر التهيئات ──
    W("=" * 100)
    W("SECTION 2: MODEL COMPARISON ACROSS CONFIGS (Full Sample)")
    W("=" * 100)
    W(f"{'Config':<45} | {'Model':<8} | {'n':>6} | {'MAE':>7} | "
      f"{'MedAE':>7} | {'Pearson':>8} | {'R²':>8}")
    W("-" * 100)
    for name, recs in configs_results.items():
        for key, label in [('dt_lin', 'Lin'), ('dt_snap', 'Snap'),
                            ('dt_exp', 'Exp')]:
            m = compute_model_metrics(recs, key)
            if 'error' in m:
                W(f"{name:<45} | {label:<8} | {m['n']:>6} | INSUFFICIENT")
                continue
            W(f"{name:<45} | {label:<8} | {m['n']:>6,} | "
              f"{m['mae']:>7.2f} | {m['median_ae']:>7.2f} | "
              f"{m['pearson']:>+8.4f} | {m['r2']:>+8.4f}")
        W("-" * 100)
    W()

    # ── Section 3: MAE حسب الأفق لكل تهيئة ──
    W("=" * 100)
    W("SECTION 3: MAE_exp BY ACTUAL HORIZON (per config)")
    W("=" * 100)
    horizons = [
        (1, 3, "1-3 (فوري)"),
        (4, 8, "4-8"),
        (9, 15, "9-15"),
        (16, 30, "16-30"),
        (31, 60, "31-60"),
    ]
    for name, recs in configs_results.items():
        W(f"--- {name} ---")
        W(f"  {'Horizon':<15} | {'n':>5} | {'MAE_lin':>8} | "
          f"{'MAE_snap':>9} | {'MAE_exp':>8} | {'Best':<8}")
        W("  " + "-" * 65)
        for lo, hi, label in horizons:
            m_lin = compute_model_metrics(recs, 'dt_lin', (lo, hi))
            m_snap = compute_model_metrics(recs, 'dt_snap', (lo, hi))
            m_exp = compute_model_metrics(recs, 'dt_exp', (lo, hi))
            if 'error' in m_exp:
                continue
            best = min(
                [("Lin", m_lin.get('mae', 999)),
                 ("Snap", m_snap.get('mae', 999)),
                 ("Exp", m_exp.get('mae', 999))],
                key=lambda x: x[1]
            )
            W(f"  {label:<15} | {m_exp.get('n', 0):>5} | "
              f"{m_lin.get('mae', 0):>8.2f} | "
              f"{m_snap.get('mae', 0):>9.2f} | "
              f"{m_exp.get('mae', 0):>8.2f} | {best[0]:<8}")
        W()

    # ── Section 4: MAE حسب frac band ──
    W("=" * 100)
    W("SECTION 4: MAE_exp BY FRAC BAND (per config)")
    W("=" * 100)
    bands = [
        (0.0, 0.30, "0.00-0.30"),
        (0.30, 0.50, "0.30-0.50"),
        (0.50, 0.70, "0.50-0.70"),
        (0.70, 0.80, "0.70-0.80"),
        (0.80, 0.90, "0.80-0.90"),
        (0.90, 1.00, "0.90-1.00"),
    ]
    for name, recs in configs_results.items():
        W(f"--- {name} ---")
        W(f"  {'Band':<12} | {'n':>5} | {'MAE_exp':>9} | "
          f"{'Median_actual':>14}")
        W("  " + "-" * 50)
        for lo, hi, label in bands:
            sub = [r for r in recs
                   if r['is_hit'] and lo <= r['frac'] < hi
                   and r['dt_exp'] > 0]
            if not sub:
                continue
            mae = np.mean([abs(r['dt_exp'] - r['actual'])
                            for r in sub])
            med_act = np.median([r['actual'] for r in sub])
            W(f"  {label:<12} | {len(sub):>5} | {mae:>9.2f} | "
              f"{med_act:>14.1f}")
        W()

    # ── Section 5: أمثلة من الأفضل تهيئة ──
    W("=" * 100)
    W("SECTION 5: EXAMPLES — Actual 1-3 bars only")
    W("=" * 100)
    for name in ['A+B+C', 'A+B', 'A only', 'Baseline']:
        if name not in configs_results:
            continue
        recs = configs_results[name]
        sub = [r for r in recs
               if r['is_hit'] and 1 <= r['actual'] <= 3
               and r['dt_exp'] > 0]
        if not sub:
            continue
        W(f"--- {name}: {len(sub)} points with actual ≤ 3 ---")
        W(f"  {'Symbol':<12} | {'Action':<5} | {'frac':>5} | "
          f"{'λ':>7} | {'pred_exp':>9} | {'actual':>6}")
        W("  " + "-" * 60)
        sub_sorted = sorted(sub, key=lambda r: -r['frac'])[:15]
        for r in sub_sorted:
            W(f"  {r['symbol']:<12} | {r['action']:<5} | "
              f"{r['frac']:>5.3f} | {r['lam']:>+7.3f} | "
              f"{r['dt_exp']:>9.2f} | {r['actual']:>6}")
        W()

    W("=" * 100)
    W("END OF REPORT")
    W("=" * 100)

    with open(out_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"\n[Report] {out_txt}")

    # JSON
    try:
        summary = {
            'meta': {
                'bot_file': bot_file,
                'timeframe': args.timeframe,
                'history_days': args.history_days,
                'n_assets': args.nassets,
                'max_horizon': args.max_horizon,
                'smooth_window': args.smooth_window,
            },
            'configs': {}
        }
        for name, recs in configs_results.items():
            summary['configs'][name] = {
                'n_total': len(recs),
                'n_hit': sum(1 for r in recs if r['is_hit']),
                'dt_lin': compute_model_metrics(recs, 'dt_lin'),
                'dt_snap': compute_model_metrics(recs, 'dt_snap'),
                'dt_exp': compute_model_metrics(recs, 'dt_exp'),
                'horizon_1_3_exp': compute_model_metrics(
                    recs, 'dt_exp', (1, 3)
                ),
                'horizon_4_8_exp': compute_model_metrics(
                    recs, 'dt_exp', (4, 8)
                ),
                'horizon_9_15_exp': compute_model_metrics(
                    recs, 'dt_exp', (9, 15)
                ),
            }
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"[Report] {out_json}")
    except Exception as e:
        print(f"[WARN] JSON save failed: {e}")


# ════════════════════════════════════════════════════════════════
# 8. الدالة الرئيسية
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Explosion Timing Test v2")
    p.add_argument("--bot", type=str, default=None)
    p.add_argument("--timeframe", type=str, default="4h")
    p.add_argument("--history-days", type=int, default=730)
    p.add_argument("--nassets", type=int, default=30)
    p.add_argument("--max-horizon", type=int, default=100)
    p.add_argument("--smooth-window", type=int, default=5)
    p.add_argument("--out-txt", type=str,
                   default="explosion_timing_v2_report.txt")
    p.add_argument("--out-json", type=str,
                   default="explosion_timing_v2_data.json")
    args = p.parse_args()

    print(f"[Main] Explosion Timing Test v2")
    print(f"[Main] TF={args.timeframe} days={args.history_days} "
          f"n_assets={args.nassets}")

    bot_file = detect_bot_file(args.bot)
    print(f"[Main] Bot: {bot_file}")

    bot = import_bot(bot_file)
    try:
        bot.log.setLevel("ERROR")
    except Exception:
        pass

    setup_bot_cfg(bot, args.timeframe, args.history_days, args.nassets)

    assets = run_pipeline(bot)
    if not assets:
        print("[ERROR] No assets processed.")
        return

    print()
    print("=" * 100)
    print("GENERATING CANDIDATES (once, for all configs)")
    print("=" * 100)
    t0 = time.time()
    candidates = generate_candidates(
        assets, max_horizon=int(args.max_horizon),
        smooth_window=int(args.smooth_window)
    )
    print(f"[Candidates] {len(candidates):,} points "
          f"in {time.time()-t0:.1f}s")

    if len(candidates) < 100:
        print("[ERROR] Too few candidates.")
        return

    # ══ التهيئات الست ══
    configs = {
        "Baseline": {
            "use_fixed_theta": False,
            "use_smooth": False,
            "use_filter": False,
        },
        "A only": {
            "use_fixed_theta": False,
            "use_smooth": False,
            "use_filter": True,
            "frac_min": 0.80, "frac_max": 0.95,
            "lam_min": 0.3, "lam_max": 6.0,
            "ratio_max": 2.0,
        },
        "B only": {
            "use_fixed_theta": False,
            "use_smooth": True,
            "use_filter": False,
        },
        "C only": {
            "use_fixed_theta": True,
            "use_smooth": False,
            "use_filter": False,
        },
        "A+B": {
            "use_fixed_theta": False,
            "use_smooth": True,
            "use_filter": True,
            "frac_min": 0.80, "frac_max": 0.95,
            "lam_min": 0.3, "lam_max": 6.0,
            "ratio_max": 2.0,
        },
        "A+B+C": {
            "use_fixed_theta": True,
            "use_smooth": True,
            "use_filter": True,
            "frac_min": 0.80, "frac_max": 0.95,
            "lam_min": 0.3, "lam_max": 6.0,
            "ratio_max": 2.0,
        },
    }

    print()
    print("=" * 100)
    print("EVALUATING CONFIGS")
    print("=" * 100)
    configs_results: Dict[str, List[Dict]] = {}
    for name, cfg in configs.items():
        t0 = time.time()
        recs = evaluate_config(candidates, cfg)
        configs_results[name] = recs
        n_hit = sum(1 for r in recs if r['is_hit'])
        print(f"  {name:<15}: total={len(recs):>7,}  hit={n_hit:>7,}  "
              f"({time.time()-t0:.1f}s)")

    write_report(configs_results, args.out_txt, args.out_json,
                  bot_file, args)

    print()
    print("=" * 100)
    print(f"Done. Send: {args.out_txt} and {args.out_json}")
    print("=" * 100)


if __name__ == "__main__":
    main()
