#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
explosion_timing_test.py

الغرض: اختبار فرضية التنبؤ بوقت الانفجار السعري.

المنهجية:
  1. تشغيل الـ pipeline كاملاً (fetch, process).
  2. لكل أصل، المرور على كل شمعة في فترة الاختبار.
  3. عند كل شمعة، إذا تحققت شروط "ما قبل الانفجار":
       - a_s > 0  (التسارع في اتجاه الإشارة)
       - a_s < θ  (لم يصل للعتبة بعد)
       - j_s > 0  (الجيرك موجب)
     نحسب ثلاثة تنبؤات لـ Δτ (حتى الوصول لـ θ):
       - خطي:  Δτ = δ / j_s
       - Snap: Δτ = (-j_s + √(j_s² + 2·s_s·δ)) / s_s
       - أسي:  Δτ = (1/λ) · ln(1 + λ·δ/j_s)  حيث λ = s_s / j_s
  4. نبحث عن Δτ الحقيقي بالنظر للأمام (حتى الوصول فعلاً لـ θ).
  5. نجمع الأخطاء ونحسب MAE و R² و Pearson Correlation.

القيود الواقعية:
  - لا نستخدم أي معلومة مستقبلية عند التنبؤ (التنبؤ من t فقط).
  - القياس الفعلي يستخدم المستقبل فقط لقياس "الحقيقة".
  - θ يُجمَّد عند لحظة التنبؤ (لا نعيد حسابه أثناء البحث).
  - أفق البحث محدود بـ max_horizon شمعة (افتراضي 100).

الإخراج:
  - explosion_timing_report.txt
  - explosion_timing_data.json

الاستخدام:
  python explosion_timing_test.py
  python explosion_timing_test.py --timeframe 4h --history-days 730 --nassets 30
  python explosion_timing_test.py --max-horizon 60
"""

import argparse
import importlib.util
import json
import logging
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
    """
    إعداد CFG مطابق لـ main() مع تفعيل نافذة N/W/L حسب الإطار.
    """
    bot.CFG.mode = "backtest"
    bot.CFG.timeframe = timeframe
    bot.CFG.history_days = int(history_days)
    bot.CFG.n_assets = int(n_assets)

    # إيقاف الفلاتر والطبقات لتجنب أي تداخل
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

    # حساب TF scale
    try:
        import ccxt
        _probe = ccxt.binance()
        tf_scale, tf_secs, tf_hours = bot.compute_tf_scale(_probe, timeframe)
    except Exception:
        tf_scale, tf_secs, tf_hours = bot.compute_tf_scale(None, timeframe)

    bot.CFG.TF_SCALE = tf_scale
    bot.CFG.TF_SECONDS = tf_secs
    bot.CFG.TF_HOURS = tf_hours

    # نافذة N/W/L مطابقة لـ main()
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
    print(f"[Setup] N={bot.CFG.N}  W={bot.CFG.W}  L={bot.CFG.L}  "
          f"ADV_BARS={bot.CFG.ADV_BARS}")


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
                print(f"  [WARN] {sym}: process_asset returned None")
        except Exception as e:
            n_failed += 1
            print(f"  [WARN] {sym}: {e}")
        if (i + 1) % 5 == 0:
            print(f"    processed {i+1}/{len(raw)}")
    print(f"[Pipeline] Processed {len(assets)}/{len(raw)} assets "
          f"in {time.time()-t0:.1f}s (failed={n_failed})")

    return assets


# ════════════════════════════════════════════════════════════════
# 3. دوال التنبؤ
# ════════════════════════════════════════════════════════════════

def predict_three_models(a_s: float, j_s: float, s_s: float,
                          theta: float) -> Tuple[
                              Optional[float], Optional[float],
                              Optional[float], Optional[float]]:
    """
    يحسب التنبؤات الثلاثة + λ.

    Parameters
    ----------
    a_s : float
        التسارع الموجّه (a × sign).
    j_s : float
        الجيرك الموجّه (da × sign).
    s_s : float
        Snap الموجّه (dj × sign).
    theta : float
        عتبة الوصول (موجبة دائماً).

    Returns
    -------
    (dt_lin, dt_snap, dt_exp, lam) — قد تكون None عند الفشل.
    """
    delta = theta - a_s

    # شروط الحد الأدنى للتنبؤ
    if delta <= 0.0:
        return None, None, None, None
    if j_s <= 0.0:
        return None, None, None, None

    # ── Model 1: Linear ──
    dt_lin = delta / j_s if j_s > 1e-15 else None

    # ── Model 2: Snap ──
    dt_snap = None
    if abs(s_s) > 1e-15:
        disc = j_s * j_s + 2.0 * s_s * delta
        if disc >= 0.0:
            _num = -j_s + np.sqrt(disc)
            _den = s_s
            if abs(_den) > 1e-15:
                _dt = _num / _den
                if _dt > 0.0 and np.isfinite(_dt):
                    dt_snap = float(_dt)
    else:
        dt_snap = dt_lin  # تنطبق على النموذج الخطي

    # ── Model 3: Exponential ──
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
                           theta: float,
                           max_horizon: int) -> int:
    """
    يبحث عن أول شمعة (fi + k) حيث a_s(fi+k) >= θ.
    يعيد k (عدد الشموع)، أو -1 إذا لم يحدث داخل الأفق.
    """
    n = len(ad.geodesic_accel)
    for k in range(1, max_horizon + 1):
        nfi = fi + k
        if nfi >= n:
            return -1
        a_k = float(ad.geodesic_accel[nfi]) * sign
        if a_k >= theta:
            return k
    return -1


def compute_theta_at(ad, fi: int, lookback: int = 200,
                     pct: float = 0.90) -> Optional[float]:
    """
    يحسب العتبة θ عند fi بناءً على percentile 90 من |a| على نافذة سابقة.
    هذا مطابق لمنطق _resonance_state_for_direction في البوت.
    """
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


# ════════════════════════════════════════════════════════════════
# 4. التحليل الرئيسي
# ════════════════════════════════════════════════════════════════

def analyze_asset(ad, max_horizon: int,
                  min_theta_frac: float = 0.05,
                  max_theta_frac: float = 0.95,
                  enable_filter: bool = True) -> List[Dict[str, Any]]:
    """
    يحلل أصلاً واحداً ويعيد قائمة سجلات التنبؤ.

    Parameters
    ----------
    ad : AssetData
    max_horizon : int
        أقصى عدد شموع للبحث عن الانفجار.
    min_theta_frac : float
        أدنى نسبة a_s/θ لقبول النقطة (لتصفية النقاط البعيدة جداً).
    max_theta_frac : float
        أقصى نسبة a_s/θ لقبول النقطة (لتصفية النقاط القريبة جداً).
    enable_filter : bool
        إذا True، نطبق شروط الفلترة.
    """
    records = []
    n_accel = len(ad.geodesic_accel)
    if n_accel < 50:
        return records

    # بداية فترة الاختبار
    train_end = int(getattr(ad, 'train_end', n_accel // 2))
    feat_start = int(getattr(ad, 'feat_start', 0))

    # الاتجاهان: BUY و SELL
    for action, sign in (("BUY", 1.0), ("SELL", -1.0)):
        for fi in range(train_end + 15, n_accel - max_horizon - 1):
            # θ عند هذه اللحظة
            theta = compute_theta_at(ad, fi, lookback=200, pct=0.90)
            if theta is None:
                continue

            # الحالة الحالية
            a_now = float(ad.geodesic_accel[fi]) * sign
            a_prev = float(ad.geodesic_accel[fi - 1]) * sign
            a_prev2 = float(ad.geodesic_accel[fi - 2]) * sign

            j_s = a_now - a_prev
            s_s = (a_now - a_prev) - (a_prev - a_prev2)
            # ملاحظة: s_s = a_now - 2*a_prev + a_prev2

            # شرط أساسي: في اتجاهنا لكن لم نصل بعد، والجيرك موجب
            if a_now <= 0.0:
                continue
            if a_now >= theta:
                continue
            if j_s <= 0.0:
                continue

            # فلترة إضافية بحسب النسبة
            frac = a_now / theta
            if enable_filter:
                if frac < min_theta_frac or frac > max_theta_frac:
                    continue

            # التنبؤ
            dt_lin, dt_snap, dt_exp, lam = predict_three_models(
                a_now, j_s, s_s, theta
            )

            # الحقيقة الفعلية
            actual = find_actual_delta_tau(
                ad, fi, sign, theta, max_horizon
            )

            if actual <= 0:
                # لم يحدث الانفجار داخل الأفق
                # نسجلها منفصلة (بـ actual=-1) لتشخيص الظاهرة
                records.append({
                    'symbol': ad.symbol,
                    'action': action,
                    'fi': int(fi),
                    'ci': int(fi + feat_start),
                    'a_now': float(a_now),
                    'j_s': float(j_s),
                    's_s': float(s_s),
                    'theta': float(theta),
                    'frac': float(frac),
                    'lam': float(lam) if lam is not None else 0.0,
                    'dt_lin': float(dt_lin) if dt_lin is not None else -1.0,
                    'dt_snap': float(dt_snap) if dt_snap is not None else -1.0,
                    'dt_exp': float(dt_exp) if dt_exp is not None else -1.0,
                    'actual': -1,
                    'is_hit': False,
                })
            else:
                records.append({
                    'symbol': ad.symbol,
                    'action': action,
                    'fi': int(fi),
                    'ci': int(fi + feat_start),
                    'a_now': float(a_now),
                    'j_s': float(j_s),
                    's_s': float(s_s),
                    'theta': float(theta),
                    'frac': float(frac),
                    'lam': float(lam) if lam is not None else 0.0,
                    'dt_lin': float(dt_lin) if dt_lin is not None else -1.0,
                    'dt_snap': float(dt_snap) if dt_snap is not None else -1.0,
                    'dt_exp': float(dt_exp) if dt_exp is not None else -1.0,
                    'actual': int(actual),
                    'is_hit': True,
                })

    return records


# ════════════════════════════════════════════════════════════════
# 5. حساب الإحصاءات
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


def compute_model_metrics(records, model_key: str) -> Dict[str, Any]:
    """
    يحسب MAE، Median AE، R²، Pearson لـ model_key.
    يستخدم فقط السجلات التي يكون فيها:
      - is_hit = True (الانفجار حدث فعلاً)
      - dt_model > 0 (النموذج أعطى تنبؤاً)
    """
    valid = [r for r in records
             if r['is_hit'] and r[model_key] > 0]
    if len(valid) < 5:
        return {'n': len(valid), 'error': 'insufficient_samples'}

    pred = np.array([r[model_key] for r in valid], dtype=np.float64)
    actual = np.array([r['actual'] for r in valid], dtype=np.float64)

    err = pred - actual
    abs_err = np.abs(err)

    # Pearson
    if np.std(pred) > 1e-9 and np.std(actual) > 1e-9:
        pearson = float(np.corrcoef(pred, actual)[0, 1])
    else:
        pearson = 0.0

    # R²
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((actual - np.mean(actual)) ** 2))
    r2 = 1.0 - ss_res / max(ss_tot, 1e-12)

    # Bias
    bias = float(np.mean(err))

    return {
        'n': len(valid),
        'mae': float(np.mean(abs_err)),
        'median_ae': float(np.median(abs_err)),
        'rmse': float(np.sqrt(np.mean(err ** 2))),
        'bias': bias,
        'pearson': pearson,
        'r2': r2,
        'pred_stats': _stats(pred.tolist()),
        'actual_stats': _stats(actual.tolist()),
    }


# ════════════════════════════════════════════════════════════════
# 6. كتابة التقرير
# ════════════════════════════════════════════════════════════════

def write_report(records: List[Dict], out_txt: str, out_json: str,
                 bot_file: str, args):
    lines = []
    def W(s=""):
        lines.append(str(s))

    W("=" * 90)
    W("EXPLOSION TIMING TEST — REPORT")
    W("=" * 90)
    W(f"Bot: {bot_file}")
    W(f"Timeframe: {args.timeframe}")
    W(f"History days: {args.history_days}")
    W(f"N assets: {args.nassets}")
    W(f"Max horizon: {args.max_horizon} bars")
    W(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    W("=" * 90)
    W()

    if not records:
        W("No records. Check pipeline.")
        with open(out_txt, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        return

    # ═══ Overview ═══
    W("=" * 90)
    W("SECTION 1: OVERVIEW")
    W("=" * 90)
    n_total = len(records)
    n_hit = sum(1 for r in records if r['is_hit'])
    n_miss = n_total - n_hit
    W(f"Total candidate points: {n_total:,}")
    W(f"  Hit (explosion within horizon): {n_hit:,} "
      f"({100*n_hit/max(n_total,1):.1f}%)")
    W(f"  Miss (no explosion): {n_miss:,} "
      f"({100*n_miss/max(n_total,1):.1f}%)")
    W()

    if n_hit == 0:
        W("No explosion events found. Aborting analysis.")
        with open(out_txt, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        return

    # توزيع actual Δτ
    actuals = [r['actual'] for r in records if r['is_hit']]
    W("--- Distribution of actual Δτ (bars) ---")
    st = _stats(actuals)
    W(f"  n={st['n']:,}  mean={st['mean']:.2f}  median={st['median']:.2f}  "
      f"std={st['std']:.2f}")
    W(f"  p05={st['p05']:.1f}  p95={st['p95']:.1f}  "
      f"min={st['min']:.0f}  max={st['max']:.0f}")
    W()

    # توزيع frac = a_s / θ
    fracs = [r['frac'] for r in records if r['is_hit']]
    st = _stats(fracs)
    W("--- Distribution of frac = a_now / θ ---")
    W(f"  n={st['n']:,}  mean={st['mean']:.3f}  median={st['median']:.3f}")
    W()

    # توزيع λ
    lams = [r['lam'] for r in records if r['is_hit'] and r['lam'] > 0]
    st = _stats(lams)
    W("--- Distribution of λ = s_s / j_s (jerk growth rate) ---")
    W(f"  n={st['n']:,}  mean={st['mean']:.4f}  median={st['median']:.4f}")
    W(f"  p05={st['p05']:.4f}  p95={st['p95']:.4f}")
    W()

    # ═══ Model Comparison ═══
    W("=" * 90)
    W("SECTION 2: MODEL COMPARISON")
    W("=" * 90)
    models = [
        ('dt_lin', 'Linear (δ / j)'),
        ('dt_snap', 'Snap (quadratic)'),
        ('dt_exp', 'Exponential (1/λ · ln(1+λ·δ/j))'),
    ]
    W(f"{'Model':<40} | {'n':>6} | {'MAE':>6} | {'MedAE':>6} | "
      f"{'RMSE':>6} | {'Bias':>7} | {'Pearson':>8} | {'R²':>7}")
    W("-" * 100)
    model_metrics = {}
    for key, label in models:
        m = compute_model_metrics(records, key)
        model_metrics[key] = m
        if 'error' in m:
            W(f"{label:<40} | {m['n']:>6} | INSUFFICIENT")
            continue
        W(f"{label:<40} | {m['n']:>6} | {m['mae']:>6.2f} | "
          f"{m['median_ae']:>6.2f} | {m['rmse']:>6.2f} | "
          f"{m['bias']:>+7.3f} | {m['pearson']:>8.4f} | "
          f"{m['r2']:>+7.4f}")
    W()

    # ═══ Effect of frac on accuracy ═══
    W("=" * 90)
    W("SECTION 3: ACCURACY vs frac (a_now / θ)")
    W("=" * 90)
    W("المقصود: هل التنبؤ يصبح دقيقاً عندما نقترب من العتبة؟")
    W()
    bands = [
        (0.05, 0.30, "0.05 – 0.30 (بعيد)"),
        (0.30, 0.50, "0.30 – 0.50"),
        (0.50, 0.70, "0.50 – 0.70"),
        (0.70, 0.85, "0.70 – 0.85 (قريب)"),
        (0.85, 0.95, "0.85 – 0.95 (قريب جداً)"),
    ]
    W(f"{'Band':<25} | {'n':>5} | {'MAE_lin':>7} | {'MAE_snap':>8} | "
      f"{'MAE_exp':>7} | {'Actual_med':>10}")
    W("-" * 85)
    for lo, hi, label in bands:
        sub = [r for r in records
               if r['is_hit'] and lo <= r['frac'] < hi]
        if not sub:
            W(f"{label:<25} | {0:>5} | —")
            continue
        act = np.array([r['actual'] for r in sub])
        m_lin = [abs(r['dt_lin'] - r['actual']) for r in sub
                 if r['dt_lin'] > 0]
        m_snap = [abs(r['dt_snap'] - r['actual']) for r in sub
                  if r['dt_snap'] > 0]
        m_exp = [abs(r['dt_exp'] - r['actual']) for r in sub
                 if r['dt_exp'] > 0]
        W(f"{label:<25} | {len(sub):>5} | "
          f"{np.mean(m_lin) if m_lin else 0:>7.2f} | "
          f"{np.mean(m_snap) if m_snap else 0:>8.2f} | "
          f"{np.mean(m_exp) if m_exp else 0:>7.2f} | "
          f"{np.median(act):>10.2f}")
    W()

    # ═══ Effect of horizon on error ═══
    W("=" * 90)
    W("SECTION 4: ACCURACY BY ACTUAL HORIZON")
    W("=" * 90)
    horizons = [
        (1, 3, "1 – 3 bars (فوري)"),
        (4, 8, "4 – 8 bars"),
        (9, 15, "9 – 15 bars"),
        (16, 30, "16 – 30 bars"),
        (31, 60, "31 – 60 bars"),
        (61, 999, "61+ bars"),
    ]
    W(f"{'Horizon':<25} | {'n':>5} | {'frac_med':>8} | "
      f"{'MAE_exp':>8} | {'Best_Model':<15}")
    W("-" * 75)
    for lo, hi, label in horizons:
        sub = [r for r in records
               if r['is_hit'] and lo <= r['actual'] <= hi]
        if not sub:
            continue
        frac_m = np.median([r['frac'] for r in sub])
        m_lin = np.mean([abs(r['dt_lin'] - r['actual']) for r in sub
                         if r['dt_lin'] > 0]) if any(
            r['dt_lin'] > 0 for r in sub) else 999
        m_snap = np.mean([abs(r['dt_snap'] - r['actual']) for r in sub
                          if r['dt_snap'] > 0]) if any(
            r['dt_snap'] > 0 for r in sub) else 999
        m_exp = np.mean([abs(r['dt_exp'] - r['actual']) for r in sub
                         if r['dt_exp'] > 0]) if any(
            r['dt_exp'] > 0 for r in sub) else 999
        best = min([("Linear", m_lin), ("Snap", m_snap), ("Exp", m_exp)],
                   key=lambda x: x[1])
        W(f"{label:<25} | {len(sub):>5} | {frac_m:>8.3f} | "
          f"{m_exp:>8.2f} | {best[0]:<15}")
    W()

    # ═══ Example predictions (closest 20) ═══
    W("=" * 90)
    W("SECTION 5: EXAMPLE PREDICTIONS (closest to explosion)")
    W("=" * 90)
    W("عينة من 20 نقطة تنبؤ كان فيها الانفجار قريباً (actual ≤ 5 bars)")
    W()
    W(f"{'Symbol':<14} | {'Action':<5} | {'frac':>5} | "
      f"{'λ':>7} | {'pred_exp':>9} | {'actual':>6}")
    W("-" * 70)
    examples = [r for r in records
                if r['is_hit'] and 1 <= r['actual'] <= 5 and r['dt_exp'] > 0]
    # رتب حسب frac تنازلياً
    examples.sort(key=lambda r: -r['frac'])
    for r in examples[:20]:
        W(f"{r['symbol']:<14} | {r['action']:<5} | "
          f"{r['frac']:>5.3f} | {r['lam']:>7.4f} | "
          f"{r['dt_exp']:>9.2f} | {r['actual']:>6}")
    W()

    # ═══ Interpretation ═══
    W("=" * 90)
    W("SECTION 6: INTERPRETATION GUIDE")
    W("=" * 90)
    W("كيف تقرأ التقرير:")
    W()
    W("1. إذا كان Pearson > 0.5 لأحد النماذج → وجود ارتباط حقيقي.")
    W("2. إذا كان R² > 0.3 → النموذج يفسر جزءاً معتبراً من التباين.")
    W("3. إذا كان MAE_exp < 3 شموع على 4h → تنبؤ عملي.")
    W("4. Section 3: يجب أن تقل MAE كلما زاد frac (اقتراباً من العتبة).")
    W("   إذا لم يحصل ذلك → التنبؤ غير مستقر.")
    W("5. Section 4: يجب أن يقل MAE مع الأفق القصير.")
    W("6. Section 5: هل pred_exp قريب من actual في الحالات القريبة؟")
    W()

    W("=" * 90)
    W("END OF REPORT")
    W("=" * 90)

    with open(out_txt, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"\n[Report] {out_txt}")

    # JSON output (compact — without the full records list)
    try:
        summary = {
            'meta': {
                'bot_file': bot_file,
                'timeframe': args.timeframe,
                'history_days': args.history_days,
                'n_assets': args.nassets,
                'max_horizon': args.max_horizon,
            },
            'overview': {
                'n_total': n_total,
                'n_hit': n_hit,
                'n_miss': n_miss,
            },
            'model_metrics': model_metrics,
        }
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"[Report] {out_json}")
    except Exception as e:
        print(f"[WARN] JSON save failed: {e}")


# ════════════════════════════════════════════════════════════════
# 7. الدالة الرئيسية
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Explosion Timing Test")
    p.add_argument("--bot", type=str, default=None)
    p.add_argument("--timeframe", type=str, default="4h")
    p.add_argument("--history-days", type=int, default=730)
    p.add_argument("--nassets", type=int, default=30)
    p.add_argument("--max-horizon", type=int, default=100,
                   help="أقصى أفق للبحث عن الانفجار (شمعة)")
    p.add_argument("--min-frac", type=float, default=0.05,
                   help="أدنى a/θ لقبول نقطة")
    p.add_argument("--max-frac", type=float, default=0.95,
                   help="أقصى a/θ لقبول نقطة")
    p.add_argument("--no-filter", action="store_true",
                   help="إلغاء فلترة a/θ (أخذ كل النقاط)")
    p.add_argument("--out-txt", type=str,
                   default="explosion_timing_report.txt")
    p.add_argument("--out-json", type=str,
                   default="explosion_timing_data.json")
    args = p.parse_args()

    print(f"[Main] Explosion Timing Test")
    print(f"[Main] TF={args.timeframe}  days={args.history_days}  "
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
    print("=" * 90)
    print("ANALYSIS: computing predictions for each (asset, bar)")
    print("=" * 90)

    all_records: List[Dict[str, Any]] = []
    n_assets = len(assets)
    for i, (sym, ad) in enumerate(assets.items()):
        try:
            recs = analyze_asset(
                ad,
                max_horizon=int(args.max_horizon),
                min_theta_frac=float(args.min_frac),
                max_theta_frac=float(args.max_frac),
                enable_filter=not args.no_filter,
            )
            all_records.extend(recs)
            n_hit = sum(1 for r in recs if r['is_hit'])
            print(f"  [{i+1:>3}/{n_assets}] {sym:<14}: "
                  f"total={len(recs):>6,}  hit={n_hit:>6,}")
        except Exception as e:
            print(f"  [{i+1:>3}/{n_assets}] {sym:<14}: FAIL ({e})")

    print()
    print(f"[Analysis] Total records: {len(all_records):,}")

    write_report(all_records, args.out_txt, args.out_json, bot_file, args)

    print()
    print("=" * 90)
    print(f"Done. Send: {args.out_txt} and {args.out_json}")
    print("=" * 90)


if __name__ == "__main__":
    main()
