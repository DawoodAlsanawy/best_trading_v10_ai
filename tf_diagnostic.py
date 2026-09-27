#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tf_diagnostic.py — كاشف مشاكل تحجيم الأُطر الزمنية في البوت.

الغرض:
  فحص كل الكميات الفيزيائية في البوت على أُطر مختلفة (5m, 15m, 30m, 1h, 4h)
  وقياس مدى تكيّفها مع الإطار. يكشف:
    - friction_drag / σ_price  (هل ثابت عبر الأُطر؟)
    - sl_dist / σ_price        (هل ثابت عبر الأُطر؟)
    - النوافذ N/W/L الفعلية    (هل تغطي نفس المدة الحقيقية؟)
    - H / H_max                (هل الإنتروبيا في نفس النطاق؟)
    - P_activation             (هل التنشيط يحدث على كل إطار؟)
    - adv_usd                  (هل الوحدة الزمنية موحّدة؟)
    - عدد الإشارات             (هل هناك إشارات على الإطارات الصغيرة؟)
    - T_info, geodesic_accel, friction, gauge_force, delta_gap

الإخراج:
  - tf_diagnostic_report.txt  (تقرير بشري)
  - tf_diagnostic_data.json   (بيانات خامة للتحليل)

الاستخدام:
  python tf_diagnostic.py
  python tf_diagnostic.py --assets 3 --history 120 --timeframes 5m,15m,1h,4h
  python tf_diagnostic.py --bot my_bot.py
"""

import argparse
import importlib.util
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import numpy as np


# ════════════════════════════════════════════════════════════════
# 0) اكتشاف ملف البوت
# ════════════════════════════════════════════════════════════════

BOT_CANDIDATES = [
    "trading_best_version_with_tf4h_and_his_days_30.py",
    "best_trading_bot_22_9_2026.py",
    "trading.py",
    "bot.py",
]


def detect_bot_file(explicit: Optional[str] = None) -> str:
    if explicit:
        if not os.path.exists(explicit):
            raise FileNotFoundError(f"Bot file not found: {explicit}")
        return explicit
    for c in BOT_CANDIDATES:
        if os.path.exists(c):
            return c
    for f in os.listdir("."):
        if f.endswith(".py") and "trading" in f.lower():
            return f
    raise FileNotFoundError(
        f"لم أستطع اكتشاف ملف البوت. جرّب --bot <filename>. "
        f"المرشحون: {BOT_CANDIDATES}"
    )


def import_bot(path: str):
    abs_path = os.path.abspath(path)
    spec = importlib.util.spec_from_file_location("bot_module", abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"تعذر تحميل البوت من {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bot_module"] = mod
    spec.loader.exec_module(mod)
    return mod


# ════════════════════════════════════════════════════════════════
# 1) أدوات إحصائية
# ════════════════════════════════════════════════════════════════

def _stats(arr) -> Dict[str, float]:
    try:
        a = np.asarray(arr, dtype=np.float64)
        a = a[np.isfinite(a)]
        if len(a) == 0:
            return {'n': 0, 'mean': 0.0, 'std': 0.0, 'min': 0.0,
                    'p05': 0.0, 'p25': 0.0, 'median': 0.0,
                    'p75': 0.0, 'p95': 0.0, 'max': 0.0}
        return {
            'n': int(len(a)),
            'mean': float(np.mean(a)),
            'std': float(np.std(a)),
            'min': float(np.min(a)),
            'p05': float(np.percentile(a, 5)),
            'p25': float(np.percentile(a, 25)),
            'median': float(np.median(a)),
            'p75': float(np.percentile(a, 75)),
            'p95': float(np.percentile(a, 95)),
            'max': float(np.max(a)),
        }
    except Exception:
        return {'n': 0, 'mean': 0.0, 'std': 0.0, 'min': 0.0,
                'p05': 0.0, 'p25': 0.0, 'median': 0.0,
                'p75': 0.0, 'p95': 0.0, 'max': 0.0}


def _safe_attr(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


# ════════════════════════════════════════════════════════════════
# 2) تشخيص إطار واحد
# ════════════════════════════════════════════════════════════════

def diagnose_one_timeframe(bot, exchange, timeframe: str,
                            assets_n: int, history_days: int,
                            verbose: bool = True) -> Dict[str, Any]:
    """
    يشغّل البوت على إطار واحد ويجمع كل القياسات المطلوبة.
    """
    out: Dict[str, Any] = {
        'timeframe': timeframe,
        'ok': False,
        'error': '',
    }

    try:
        # ── إعداد CFG لهذا الإطار ──
        bot.CFG.timeframe = timeframe
        bot.CFG.history_days = history_days
        bot.CFG.n_assets = assets_n
        bot.CFG.PO_FIXED_PRICE = True  # لقياس السلوك الطبيعي
        bot.CFG.SLP_FILTER_ENABLED = False

        # ── حساب TF scale ──
        try:
            tf_scale, tf_secs, tf_hours = bot.compute_tf_scale(
                exchange, timeframe
            )
            bot.CFG.TF_SCALE = tf_scale
            bot.CFG.TF_SECONDS = tf_secs
            bot.CFG.TF_HOURS = tf_hours
        except Exception as e:
            out['error'] = f"compute_tf_scale: {e}"
            return out

        out['TF_SCALE'] = float(tf_scale)
        out['TF_SECONDS'] = int(tf_secs)
        out['TF_HOURS'] = float(tf_hours)

        # ── النوافذ المُعايَرة على 1h والقيم الفعلية ──
        N_1h = int(_safe_attr(bot.CFG, 'N', 24))
        W_1h = int(_safe_attr(bot.CFG, 'W', 20))
        L_1h = int(_safe_attr(bot.CFG, 'L', 10))
        N_hours = N_1h * 1.0
        W_hours = W_1h * 1.0
        L_hours = L_1h * 1.0

        out['windows'] = {
            'N_config': N_1h,
            'W_config': W_1h,
            'L_config': L_1h,
            'N_hours_intended': N_hours,
            'W_hours_intended': W_hours,
            'L_hours_intended': L_hours,
            'N_hours_actual': N_1h * tf_hours,
            'W_hours_actual': W_1h * tf_hours,
            'L_hours_actual': L_1h * tf_hours,
        }

        # ── جلب الأصول ──
        if verbose:
            print(f"  [{timeframe}] جلب الأصول...")
        try:
            syms = bot.scan_top_assets(exchange, assets_n)
        except Exception:
            syms = bot._default_assets()[:assets_n]

        out['symbols'] = list(syms)

        # ── جلب البيانات ──
        if verbose:
            print(f"  [{timeframe}] جلب بيانات {len(syms)} أصل × "
                  f"{history_days} يوم...")
        try:
            raw = bot.fetch_all(
                syms, exchange, timeframe, history_days, workers=3
            )
        except Exception as e:
            out['error'] = f"fetch_all: {e}"
            return out

        if not raw:
            out['error'] = "no_data"
            return out

        # ── معالجة الأصول ──
        if verbose:
            print(f"  [{timeframe}] معالجة {len(raw)} أصل...")
        assets: Dict[str, Any] = {}
        per_asset_errors = []
        for sym, df in raw.items():
            try:
                ad = bot.process_asset(
                    sym, df, current_capital=bot.CFG.INITIAL_CAPITAL
                )
                if ad is not None:
                    assets[sym] = ad
                else:
                    per_asset_errors.append((sym, "None"))
            except Exception as e:
                per_asset_errors.append((sym, str(e)[:80]))

        out['n_assets_ok'] = len(assets)
        out['per_asset_errors'] = per_asset_errors[:10]

        if not assets:
            out['error'] = "all_assets_failed"
            return out

        # ── جمع القياسات ──
        if verbose:
            print(f"  [{timeframe}] جمع القياسات...")

        # قوائم تراكمية
        E_therm_vals: List[float] = []
        sigma_price_vals: List[float] = []
        friction_vals: List[float] = []
        friction_drag_ratio_vals: List[float] = []  # friction_drag / σ_price
        sl_dist_ratio_vals: List[float] = []        # sl_dist / σ_price
        T_info_vals: List[float] = []
        accel_vals: List[float] = []
        gauge_vals: List[float] = []
        delta_gap_vals: List[float] = []
        H_ratio_vals: List[float] = []
        V_vals: List[float] = []
        adv_dollar_vals: List[float] = []
        adv_bars_used: List[int] = []

        per_asset_summary = []

        for sym, ad in assets.items():
            try:
                dyn_k = int(_safe_attr(ad, 'dynamic_k', 0))
                H_max = np.log2(max(dyn_k, 2))
                n_bars = len(ad.closes)
                train_end = int(_safe_attr(ad, 'train_end', 0))
                feat_start = int(_safe_attr(ad, 'feat_start', 0))

                # ── النطاق التشغيلي: من train_end إلى النهاية ──
                if train_end + 10 >= n_bars:
                    continue
                lo = max(train_end, 1)
                hi = n_bars
                sl_lo = feat_start + lo
                sl_hi = feat_start + hi

                # E_therm
                E_arr = ad.E_therm
                E_slice = E_arr[lo:hi] if hi <= len(E_arr) else E_arr[lo:]
                E_therm_vals.extend(E_slice.tolist())

                # σ_price = E_therm × price
                closes_slice = ad.closes[sl_lo:sl_hi] if sl_hi <= len(ad.closes) \
                    else ad.closes[sl_lo:]
                min_len = min(len(E_slice), len(closes_slice))
                if min_len > 0:
                    sigma_p = E_slice[:min_len] * closes_slice[:min_len]
                    sigma_price_vals.extend(sigma_p.tolist())

                # friction
                fric_arr = ad.friction[lo:hi] if hi <= len(ad.friction) \
                    else ad.friction[lo:]
                friction_vals.extend(fric_arr.tolist())

                # friction_drag / σ_price
                # friction_drag = fric × p × 0.1  (المعادلة الحالية)
                if min_len > 0:
                    fd = fric_arr[:min_len] * closes_slice[:min_len] * 0.1
                    ratio = fd / np.maximum(sigma_p, 1e-12)
                    friction_drag_ratio_vals.extend(ratio.tolist())

                # sl_dist / σ_price
                # sl_dist = clip(0.012 × unc / (1+fric×5) × p,
                #                0.005 p, 0.05 p)
                try:
                    V_arr = ad.V
                    V_slice = V_arr[lo:hi] if hi <= len(V_arr) else V_arr[lo:]
                    V_mean = float(np.mean(V_arr[V_arr > 0])) if np.any(V_arr > 0) else 1.0
                    min_len2 = min(len(V_slice), len(fric_arr), len(closes_slice))
                    if min_len2 > 0:
                        unc = np.clip(V_slice[:min_len2] / (V_mean + 1e-9),
                                       0.5, 3.0)
                        fric_v = fric_arr[:min_len2]
                        p_v = closes_slice[:min_len2]
                        sl_pct = (0.012 * unc) / (1.0 + fric_v * 5.0)
                        sl_dist = np.clip(sl_pct * p_v,
                                           0.005 * p_v, 0.05 * p_v)
                        sigma_p2 = E_slice[:min_len2] * p_v
                        ratio_sl = sl_dist / np.maximum(sigma_p2, 1e-12)
                        sl_dist_ratio_vals.extend(ratio_sl.tolist())
                        V_vals.extend(V_slice[:min_len2].tolist())
                except Exception:
                    pass

                # T_info
                T_arr = ad.T_info
                T_slice = T_arr[lo:hi] if hi <= len(T_arr) else T_arr[lo:]
                T_info_vals.extend(T_slice.tolist())

                # geodesic_accel
                acc_arr = ad.geodesic_accel
                acc_slice = acc_arr[lo:hi] if hi <= len(acc_arr) else acc_arr[lo:]
                accel_vals.extend(acc_slice.tolist())

                # gauge_force
                g_arr = ad.gauge_force
                g_slice = g_arr[lo:hi] if hi <= len(g_arr) else g_arr[lo:]
                gauge_vals.extend(g_slice.tolist())

                # delta_gap
                d_arr = ad.delta_gap
                d_slice = d_arr[lo:hi] if hi <= len(d_arr) else d_arr[lo:]
                delta_gap_vals.extend(d_slice.tolist())

                # H / H_max
                H_arr = ad.H
                H_slice = H_arr[lo:hi] if hi <= len(H_arr) else H_arr[lo:]
                if H_max > 0:
                    H_ratio_vals.extend((H_slice / H_max).tolist())

                # adv_usd
                adv_arr = ad.adv_usd
                adv_slice = adv_arr[sl_lo:sl_hi] if sl_hi <= len(adv_arr) \
                    else adv_arr[sl_lo:]
                adv_dollar_vals.extend(adv_slice.tolist())

                # الوحدة الزمنية لـ adv (24 شمعة = كم ساعة؟)
                adv_bars_used.append(24)

                # ملخص الأصل
                per_asset_summary.append({
                    'symbol': sym,
                    'n_bars': int(n_bars),
                    'dyn_k': dyn_k,
                    'train_end': int(train_end),
                    'E_therm_median': float(np.median(E_slice)) if len(E_slice) > 0 else 0.0,
                    'H_ratio_mean': float(np.mean(H_slice / H_max)) if len(H_slice) > 0 else 0.0,
                    'fric_median': float(np.median(fric_arr)) if len(fric_arr) > 0 else 0.0,
                    'T_info_median': float(np.median(T_slice)) if len(T_slice) > 0 else 0.0,
                    'accel_abs_median': float(np.median(np.abs(acc_slice))) if len(acc_slice) > 0 else 0.0,
                })
            except Exception as e:
                per_asset_errors.append((sym, f"measure:{str(e)[:80]}"))

        # ── إحصاءات تراكمية ──
        out['stats'] = {
            'E_therm': _stats(E_therm_vals),
            'sigma_price': _stats(sigma_price_vals),
            'friction': _stats(friction_vals),
            'friction_drag_over_sigma': _stats(friction_drag_ratio_vals),
            'sl_dist_over_sigma': _stats(sl_dist_ratio_vals),
            'T_info': _stats(T_info_vals),
            'geodesic_accel_abs': _stats(np.abs(accel_vals).tolist()),
            'gauge_force': _stats(gauge_vals),
            'delta_gap': _stats(delta_gap_vals),
            'H_over_H_max': _stats(H_ratio_vals),
            'V': _stats(V_vals),
            'adv_usd': _stats(adv_dollar_vals),
        }

        out['per_asset'] = per_asset_summary
        out['adv_bars_per_day_equiv'] = 24  # 24 شمعة، ليست 24 ساعة

        # ── بناء الإشارات (لقياس P_activation و عدد الإشارات) ──
        if verbose:
            print(f"  [{timeframe}] بناء الإشارات (قياس P_activation)...")

        try:
            # نحسب P_activation يدوياً لكل نقطة في فترة الاختبار
            P_act_vals: List[float] = []
            score_vals: List[float] = []
            for sym, ad in assets.items():
                try:
                    n = len(ad.score)
                    train_end = int(ad.train_end)
                    if train_end + 5 >= n:
                        continue
                    for fi in range(train_end + 1, n):
                        acc = abs(float(ad.geodesic_accel[fi]))
                        fric = float(ad.friction[fi]) + 1e-6
                        T = float(ad.T_info[fi])
                        if T <= 0 or not np.isfinite(T):
                            continue
                        force_mag = acc + 1e-9
                        pa = float(np.exp(-fric / (force_mag * T)))
                        P_act_vals.append(pa)
                        score_vals.append(float(ad.score[fi]))
                except Exception:
                    continue

            out['P_activation'] = _stats(P_act_vals)
            out['score'] = _stats(score_vals)

            # نسبة النقاط التي تتجاوز عتبة 0.35
            if P_act_vals:
                pa_arr = np.asarray(P_act_vals)
                out['P_activation_frac_above_035'] = float(
                    np.mean(pa_arr >= 0.35)
                )
                out['P_activation_frac_above_050'] = float(
                    np.mean(pa_arr >= 0.50)
                )
            else:
                out['P_activation_frac_above_035'] = 0.0
                out['P_activation_frac_above_050'] = 0.0

            # ── بناء الإشارات الفعلي ──
            sigs = bot.build_signals(assets, mode="backtest")
            sigs = bot.deduplicate_signals(sigs)
            out['n_signals'] = int(len(sigs))

            if sigs:
                scores = [float(s.score) for s in sigs]
                out['signal_score'] = _stats(scores)
                out['n_buy'] = int(sum(1 for s in sigs if s.action == "BUY"))
                out['n_sell'] = int(sum(1 for s in sigs if s.action == "SELL"))

                # حساب R:R الفعلي المُصمَّم
                rr_vals = []
                sl_sigma_vals = []
                for s in sigs[:500]:
                    try:
                        sl_dist = abs(s.price - s.sl)
                        tp_dist = abs(s.tp1 - s.price)
                        if sl_dist > 1e-12:
                            rr_vals.append(tp_dist / sl_dist)
                        # sl_dist / σ_price
                        ad = assets.get(s.symbol)
                        if ad is not None:
                            fi = int(s.feat_idx)
                            if 0 <= fi < len(ad.E_therm):
                                sig_p = float(ad.E_therm[fi]) * float(s.price)
                                if sig_p > 1e-12:
                                    sl_sigma_vals.append(sl_dist / sig_p)
                    except Exception:
                        pass
                out['signal_RR'] = _stats(rr_vals)
                out['signal_sl_over_sigma'] = _stats(sl_sigma_vals)
            else:
                out['signal_score'] = _stats([])
                out['signal_RR'] = _stats([])
                out['signal_sl_over_sigma'] = _stats([])
                out['n_buy'] = 0
                out['n_sell'] = 0

        except Exception as e:
            out['error'] = f"build_signals: {str(e)[:200]}"

        out['ok'] = True
        return out

    except Exception as e:
        out['error'] = f"fatal: {str(e)[:200]}"
        return out


# ════════════════════════════════════════════════════════════════
# 3) كتابة التقرير
# ════════════════════════════════════════════════════════════════

def write_report(all_results: List[Dict[str, Any]],
                  txt_path: str, json_path: str,
                  bot_file: str) -> None:

    # ── JSON ──
    try:
        def _clean(o):
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            if isinstance(o, np.ndarray):
                return o.tolist()
            return str(o)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False,
                       default=_clean)
    except Exception as e:
        print(f"[WARN] فشل حفظ JSON: {e}")

    # ── TXT ──
    lines = []
    def W(s=""):
        lines.append(str(s))

    W("=" * 78)
    W("TF DIAGNOSTIC REPORT")
    W(f"Bot: {bot_file}")
    W(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    W("=" * 78)
    W()

    # ── جدول مقارنة ──
    W("─" * 78)
    W("TABLE 1 — TF Parameters")
    W("─" * 78)
    W(f"{'TF':>6} | {'TF_SCALE':>9} | {'TF_SECS':>8} | "
      f"{'TF_HOURS':>9} | {'n_assets':>8} | {'n_sigs':>7} | {'status':>8}")
    W("-" * 78)
    for r in all_results:
        tf = r.get('timeframe', '?')
        ts = r.get('TF_SCALE', 0.0)
        tsec = r.get('TF_SECONDS', 0)
        th = r.get('TF_HOURS', 0.0)
        na = r.get('n_assets_ok', 0)
        ns = r.get('n_signals', 0)
        st = "OK" if r.get('ok') else "FAIL"
        W(f"{tf:>6} | {ts:>9.4f} | {tsec:>8d} | "
          f"{th:>9.3f} | {na:>8d} | {ns:>7d} | {st:>8}")
    W()

    # ── النوافذ ──
    W("─" * 78)
    W("TABLE 2 — Windows (N, W, L) in hours")
    W("─" * 78)
    W(f"{'TF':>6} | {'N_hours':>9} | {'W_hours':>9} | {'L_hours':>9} | "
      f"{'N_actual':>9} | {'W_actual':>9} | {'L_actual':>9}")
    W("-" * 78)
    for r in all_results:
        if not r.get('ok'):
            continue
        w = r.get('windows', {})
        W(f"{r['timeframe']:>6} | "
          f"{w.get('N_hours_intended', 0):>9.1f} | "
          f"{w.get('W_hours_intended', 0):>9.1f} | "
          f"{w.get('L_hours_intended', 0):>9.1f} | "
          f"{w.get('N_hours_actual', 0):>9.1f} | "
          f"{w.get('W_hours_actual', 0):>9.1f} | "
          f"{w.get('L_hours_actual', 0):>9.1f}")
    W()
    W("ملاحظة: الأعمدة intended = ما يجب أن تكون عليه (مبنية على 1h).")
    W("        actual = ما هي عليه فعلاً (N × TF_HOURS).")
    W("        الفرق = مقدار عدم التكيّف.")
    W()

    # ── المقياس الأساسي: friction_drag / σ_price ──
    W("─" * 78)
    W("TABLE 3 — friction_drag / σ_price (المفروض يكون ثابتاً عبر الأُطر)")
    W("─" * 78)
    W(f"{'TF':>6} | {'mean':>8} | {'median':>8} | {'p05':>8} | "
      f"{'p95':>8} | {'std':>8}")
    W("-" * 78)
    for r in all_results:
        if not r.get('ok'):
            continue
        s = r.get('stats', {}).get('friction_drag_over_sigma', {})
        W(f"{r['timeframe']:>6} | "
          f"{s.get('mean', 0):>8.3f} | "
          f"{s.get('median', 0):>8.3f} | "
          f"{s.get('p05', 0):>8.3f} | "
          f"{s.get('p95', 0):>8.3f} | "
          f"{s.get('std', 0):>8.3f}")
    W()
    W("التفسير: إذا كانت القيم متقاربة (~1.5)، فالتحجيم صحيح.")
    W("         إذا اختلفت كثيراً، فهذه مشكلة.")
    W()

    # ── sl_dist / σ_price ──
    W("─" * 78)
    W("TABLE 4 — sl_dist / σ_price (المفروض يكون ثابتاً)")
    W("─" * 78)
    W(f"{'TF':>6} | {'mean':>8} | {'median':>8} | {'p05':>8} | "
      f"{'p95':>8} | {'std':>8}")
    W("-" * 78)
    for r in all_results:
        if not r.get('ok'):
            continue
        s = r.get('stats', {}).get('sl_dist_over_sigma', {})
        W(f"{r['timeframe']:>6} | "
          f"{s.get('mean', 0):>8.3f} | "
          f"{s.get('median', 0):>8.3f} | "
          f"{s.get('p05', 0):>8.3f} | "
          f"{s.get('p95', 0):>8.3f} | "
          f"{s.get('std', 0):>8.3f}")
    W()

    # ── H / H_max ──
    W("─" * 78)
    W("TABLE 5 — H / H_max (إنتروبيا النظام)")
    W("─" * 78)
    W(f"{'TF':>6} | {'mean':>8} | {'median':>8} | {'p05':>8} | "
      f"{'p95':>8} | {'std':>8}")
    W("-" * 78)
    for r in all_results:
        if not r.get('ok'):
            continue
        s = r.get('stats', {}).get('H_over_H_max', {})
        W(f"{r['timeframe']:>6} | "
          f"{s.get('mean', 0):>8.3f} | "
          f"{s.get('median', 0):>8.3f} | "
          f"{s.get('p05', 0):>8.3f} | "
          f"{s.get('p95', 0):>8.3f} | "
          f"{s.get('std', 0):>8.3f}")
    W()
    W("التفسير: يجب أن يكون ~0.6–0.8. إذا اقترب من 1.0،")
    W("         فالتسلسل الرمزي عشوائي (ضجيج) → مشكلة على TF الصغيرة.")
    W()

    # ── P_activation ──
    W("─" * 78)
    W("TABLE 6 — P_activation (يجب أن تتجاوز 0.35 لتنشيط الصفقة)")
    W("─" * 78)
    W(f"{'TF':>6} | {'mean':>8} | {'median':>8} | {'p95':>8} | "
      f"{'frac>0.35':>10} | {'frac>0.50':>10}")
    W("-" * 78)
    for r in all_results:
        if not r.get('ok'):
            continue
        s = r.get('P_activation', {})
        f35 = r.get('P_activation_frac_above_035', 0.0)
        f50 = r.get('P_activation_frac_above_050', 0.0)
        W(f"{r['timeframe']:>6} | "
          f"{s.get('mean', 0):>8.4f} | "
          f"{s.get('median', 0):>8.4f} | "
          f"{s.get('p95', 0):>8.4f} | "
          f"{f35*100:>9.2f}% | "
          f"{f50*100:>9.2f}%")
    W()
    W("التفسير: إذا كان frac>0.35 قريباً من 0، فالإشارات لا تُولَّد.")
    W()

    # ── friction, T_info, accel, gauge, delta ──
    W("─" * 78)
    W("TABLE 7 — الكميات الفيزيائية (median)")
    W("─" * 78)
    W(f"{'TF':>6} | {'friction':>10} | {'T_info':>10} | "
      f"{'|accel|':>10} | {'gauge':>10} | {'delta':>10} | {'E_therm':>10}")
    W("-" * 78)
    for r in all_results:
        if not r.get('ok'):
            continue
        st = r.get('stats', {})
        fric = st.get('friction', {}).get('median', 0)
        T = st.get('T_info', {}).get('median', 0)
        acc = st.get('geodesic_accel_abs', {}).get('median', 0)
        g = st.get('gauge_force', {}).get('median', 0)
        d = st.get('delta_gap', {}).get('median', 0)
        E = st.get('E_therm', {}).get('median', 0)
        W(f"{r['timeframe']:>6} | "
          f"{fric:>10.4f} | {T:>10.4f} | "
          f"{acc:>10.5f} | {g:>10.4f} | {d:>10.4f} | {E:>10.4f}")
    W()

    # ── R:R و sl/σ في الإشارات الفعلية ──
    W("─" * 78)
    W("TABLE 8 — خصائص الإشارات المُنتَجة")
    W("─" * 78)
    W(f"{'TF':>6} | {'n_sigs':>7} | {'buy':>5} | {'sell':>5} | "
      f"{'RR_median':>10} | {'SL/σ_median':>12} | {'score_median':>13}")
    W("-" * 78)
    for r in all_results:
        if not r.get('ok'):
            continue
        ns = r.get('n_signals', 0)
        nb = r.get('n_buy', 0)
        nsl = r.get('n_sell', 0)
        rr = r.get('signal_RR', {}).get('median', 0)
        sls = r.get('signal_sl_over_sigma', {}).get('median', 0)
        sm = r.get('signal_score', {}).get('median', 0)
        W(f"{r['timeframe']:>6} | "
          f"{ns:>7d} | {nb:>5d} | {nsl:>5d} | "
          f"{rr:>10.3f} | {sls:>12.3f} | {sm:>13.3f}")
    W()

    # ── adv_usd ──
    W("─" * 78)
    W("TABLE 9 — adv_usd (يجب أن يكون بوحدة 24 ساعة)")
    W("─" * 78)
    W(f"{'TF':>6} | {'bars_used':>10} | {'hours_covered':>14} | "
      f"{'adv_median (USD)':>20}")
    W("-" * 78)
    for r in all_results:
        if not r.get('ok'):
            continue
        th = r.get('TF_HOURS', 1.0)
        bars = r.get('adv_bars_per_day_equiv', 24)
        hours = bars * th
        adv = r.get('stats', {}).get('adv_usd', {}).get('median', 0)
        W(f"{r['timeframe']:>6} | {bars:>10d} | {hours:>14.1f} | "
          f"{adv:>20.2f}")
    W()
    W("التفسير: يجب أن يكون hours_covered ≈ 24. إذا كان أقل،")
    W("         فالـ ADV محسوب على نافذة أقصر → K قد يكون غير مناسب.")
    W()

    # ── ملخص المشاكل ──
    W("=" * 78)
    W("SUMMARY OF ISSUES")
    W("=" * 78)
    W()

    if len(all_results) >= 2:
        # مقارنة friction_drag / σ
        fds = [r.get('stats', {}).get('friction_drag_over_sigma', {}).get('median', 0)
               for r in all_results if r.get('ok')]
        if fds and max(fds) > 0:
            ratio = max(fds) / max(min(fds), 1e-6)
            W(f"1. friction_drag / σ_price ratio across TFs: "
              f"{min(fds):.3f} – {max(fds):.3f}  (spread ×{ratio:.2f})")
            if ratio > 2.0:
                W("   ⚠️  SPREAD TOO LARGE — friction_drag not TF-adapted")
            W()

        # مقارنة sl_dist / σ
        sds = [r.get('stats', {}).get('sl_dist_over_sigma', {}).get('median', 0)
               for r in all_results if r.get('ok')]
        if sds and max(sds) > 0:
            ratio = max(sds) / max(min(sds), 1e-6)
            W(f"2. sl_dist / σ_price ratio across TFs: "
              f"{min(sds):.3f} – {max(sds):.3f}  (spread ×{ratio:.2f})")
            if ratio > 2.0:
                W("   ⚠️  SPREAD TOO LARGE — SL not TF-adapted")
            W()

        # مقارنة H / H_max
        hs = [r.get('stats', {}).get('H_over_H_max', {}).get('median', 0)
              for r in all_results if r.get('ok')]
        if hs:
            W(f"3. H / H_max across TFs: "
              f"{min(hs):.3f} – {max(hs):.3f}")
            if max(hs) > 0.90:
                W("   ⚠️  H/H_max HIGH on some TF — symbolic sequence is noise")
            W()

        # مقارنة عدد الإشارات
        nss = [(r.get('timeframe', '?'), r.get('n_signals', 0))
               for r in all_results if r.get('ok')]
        if nss:
            W("4. Signals per TF:")
            for tf, n in nss:
                W(f"   {tf:>6}: {n:>6d}")
            W()

        # P_activation
        pas = [(r.get('timeframe', '?'),
                r.get('P_activation_frac_above_035', 0.0))
               for r in all_results if r.get('ok')]
        if pas:
            W("5. P_activation frac > 0.35 per TF:")
            for tf, f in pas:
                flag = "  ⚠️" if f < 0.01 else ""
                W(f"   {tf:>6}: {f*100:>6.2f}%{flag}")
            W()

    W("=" * 78)
    W("END OF REPORT")
    W("=" * 78)

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print(f"\n[OK] التقرير النصي: {txt_path}")
    print(f"[OK] البيانات الخام: {json_path}")


# ════════════════════════════════════════════════════════════════
# 4) الدالة الرئيسية
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="TF Scaling Diagnostic")
    p.add_argument("--bot", type=str, default=None)
    p.add_argument("--timeframes", type=str,
                   default="5m,15m,30m,1h,4h",
                   help="قائمة الأُطر مفصولة بفواصل")
    p.add_argument("--assets", type=int, default=3,
                   help="عدد الأصول لكل إطار (افتراضي 3 للسرعة)")
    p.add_argument("--history", type=int, default=180,
                   help="عدد الأيام (افتراضي 180)")
    p.add_argument("--out-txt", type=str,
                   default="tf_diagnostic_report.txt")
    p.add_argument("--out-json", type=str,
                   default="tf_diagnostic_data.json")
    p.add_argument("--verbose", action="store_true", default=True)
    args = p.parse_args()

    # ── اكتشاف البوت ──
    bot_file = detect_bot_file(args.bot)
    print(f"[Main] ملف البوت: {bot_file}")
    bot = import_bot(bot_file)

    # ── إعداد السجل ──
    try:
        bot.log.setLevel(logging.WARNING)
    except Exception:
        pass

    # ── البورصة ──
    try:
        import ccxt
    except ImportError:
        print("[ERROR] pip install ccxt")
        return
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })

    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    print(f"[Main] الأُطر: {timeframes}")
    print(f"[Main] الأصول/إطار: {args.assets}")
    print(f"[Main] الأيام: {args.history}")
    print()

    all_results: List[Dict[str, Any]] = []
    for tf in timeframes:
        print(f"━━━ [{tf}] ━━━")
        t0 = time.time()
        try:
            r = diagnose_one_timeframe(
                bot, exchange, tf,
                assets_n=args.assets,
                history_days=args.history,
                verbose=args.verbose,
            )
        except Exception as e:
            r = {'timeframe': tf, 'ok': False, 'error': f"fatal: {e}"}
        r['elapsed_s'] = round(time.time() - t0, 1)
        all_results.append(r)
        status = "OK" if r.get('ok') else f"FAIL: {r.get('error','')[:60]}"
        print(f"  → {status}  ({r['elapsed_s']}s)")
        print()

    # ── التقرير ──
    write_report(
        all_results, args.out_txt, args.out_json, bot_file
    )

    print()
    print("━" * 60)
    print("انتهى. أرسل الملفين التاليين:")
    print(f"  - {args.out_txt}")
    print(f"  - {args.out_json}")
    print("━" * 60)


if __name__ == "__main__":
    main()
