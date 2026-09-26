#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tf_full_diagnostic.py — تشخيص شامل للأُطر الزمنية مع Backtest كامل.

لا يكتفي بقياس الكميات الفيزيائية، بل يشغّل simulate_portfolio
على كل إطار ويقارن:
  - عدد الإشارات
  - عدد الصفقات الفعلية
  - Win Rate, PF, E[ln(1+fR)]
  - توزيع أسباب الخروج
  - معدل الامتلاء (Stage 1 vs Stage 2)
  - الكميات الفيزيائية (friction_drag/σ، sl_dist/σ)

يختبر وضعين:
  - PO_FIXED_PRICE=True   (العادي)
  - PO_FIXED_PRICE=False  (no-fixed-price)

الإخراج:
  - tf_full_report.txt
  - tf_full_data.json

الاستخدام:
  python tf_full_diagnostic.py
  python tf_full_diagnostic.py --timeframes 15m,1h,4h --assets 3 --history 90
  python tf_full_diagnostic.py --mode fixed     # اختبار PO_FIXED_PRICE=True فقط
  python tf_full_diagnostic.py --mode nofix     # اختبار PO_FIXED_PRICE=False فقط
"""

import argparse
import importlib.util
import json
import logging
import os
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np


BOT_CANDIDATES = [
    "trading.py",
    "trading_best_version_with_tf4h_and_his_days_30.py",
    "best_trading_bot_22_9_2026.py",
]


def detect_bot_file(explicit=None):
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
    raise FileNotFoundError(f"لم أجد ملف البوت. جرّب --bot <filename>")


def import_bot(path):
    abs_path = os.path.abspath(path)
    spec = importlib.util.spec_from_file_location("bot_module", abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"تعذر تحميل البوت من {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bot_module"] = mod
    spec.loader.exec_module(mod)
    return mod


def _stats(arr):
    try:
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
    except Exception:
        return {'n': 0, 'mean': 0., 'median': 0., 'std': 0.,
                'p05': 0., 'p95': 0., 'min': 0., 'max': 0.}


# ════════════════════════════════════════════════════════════════
# اختبار إطار واحد
# ════════════════════════════════════════════════════════════════

def run_one_tf(bot, exchange, tf: str, assets_n: int, history_days: int,
               mode: str, verbose: bool = True) -> Dict[str, Any]:
    """
    يشغّل backtest كامل على إطار واحد ويعيد كل المقاييس.

    mode ∈ {'fixed', 'nofix', 'both'}
    """
    out: Dict[str, Any] = {
        'timeframe': tf,
        'ok': False,
        'error': '',
        'modes': {},
    }

    try:
        # ── إعداد CFG ──
        bot.CFG.timeframe = tf
        bot.CFG.history_days = history_days
        bot.CFG.n_assets = assets_n

        # ── TF scale ──
        try:
            tf_scale, tf_secs, tf_hours = bot.compute_tf_scale(exchange, tf)
            bot.CFG.TF_SCALE = tf_scale
            bot.CFG.TF_SECONDS = tf_secs
            bot.CFG.TF_HOURS = tf_hours
        except Exception as e:
            out['error'] = f"compute_tf_scale: {e}"
            return out

        out['TF_SCALE'] = float(tf_scale)
        out['TF_SECONDS'] = int(tf_secs)
        out['TF_HOURS'] = float(tf_hours)

        # ── حساب النوافذ الفعلية (مطابق لـ main) ──
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

        out['windows'] = {
            'N': int(bot.CFG.N),
            'W': int(bot.CFG.W),
            'L': int(bot.CFG.L),
            'ADV_BARS': int(bot.CFG.ADV_BARS),
            'N_hours': float(bot.CFG.N * _tf_h),
            'W_hours': float(bot.CFG.W * _tf_h),
            'L_hours': float(bot.CFG.L * _tf_h),
        }

        # ── جلب الأصول ──
        if verbose:
            print(f"  [{tf}] جلب الأصول...")
        try:
            syms = bot.scan_top_assets(exchange, assets_n)
        except Exception:
            syms = bot._default_assets()[:assets_n]
        out['symbols'] = list(syms)

        # ── جلب البيانات ──
        if verbose:
            print(f"  [{tf}] جلب بيانات {len(syms)} أصل × {history_days} يوم...")
        try:
            raw = bot.fetch_all(syms, exchange, tf, history_days, workers=3)
        except Exception as e:
            out['error'] = f"fetch_all: {e}"
            return out
        if not raw:
            out['error'] = "no_data"
            return out

        # ── معالجة الأصول ──
        if verbose:
            print(f"  [{tf}] معالجة {len(raw)} أصل...")
        assets: Dict[str, Any] = {}
        errors = []
        for sym, df in raw.items():
            try:
                ad = bot.process_asset(
                    sym, df, current_capital=bot.CFG.INITIAL_CAPITAL
                )
                if ad is not None:
                    assets[sym] = ad
                else:
                    errors.append((sym, "None"))
            except Exception as e:
                errors.append((sym, str(e)[:80]))

        out['n_assets_ok'] = len(assets)
        out['per_asset_errors'] = errors[:5]

        if not assets:
            out['error'] = "all_assets_failed"
            return out

        # ── قياس الكميات الفيزيائية بعد الإصلاح ──
        if verbose:
            print(f"  [{tf}] قياس الكميات الفيزيائية...")
        fds_ratio = []       # friction_drag / σ
        sls_ratio = []       # sl_dist / σ
        sigmas = []
        E_therms = []
        sl_dist_arr = []
        friction_drags = []

        # σ المرجعي
        SIGMA_REF_1H = 0.01
        _fd_kappa = float(getattr(bot.CFG, 'FRICTION_DIP_KAPPA', 4.0))
        _sl_kappa = float(getattr(bot.CFG, 'SL_REF_KAPPA', 2.0))

        for sym, ad in assets.items():
            try:
                train_end = int(ad.train_end)
                n = len(ad.closes)
                if train_end + 10 >= n:
                    continue
                lo = max(train_end, 1)
                hi = n
                sl_lo = ad.feat_start + lo
                sl_hi = ad.feat_start + hi

                for fi in range(lo, min(hi, len(ad.E_therm))):
                    ci = ad.feat_start + fi
                    if ci >= len(ad.closes):
                        break
                    p = float(ad.closes[ci])
                    sigma_frac = float(ad.E_therm[fi])
                    if not np.isfinite(sigma_frac) or sigma_frac <= 1e-6:
                        continue
                    sigma_price = sigma_frac * p
                    if sigma_price <= 1e-9:
                        continue
                    sigmas.append(sigma_frac)
                    E_therms.append(sigma_frac)

                    # friction_drag = κ_fd × σ_price
                    fd = _fd_kappa * sigma_price
                    friction_drags.append(fd)
                    fds_ratio.append(fd / sigma_price)  # دائماً = κ_fd

                    # sl_dist = clip(κ_sl × unc / (1+fric×5), 0.5σ, 5σ) × σ_price
                    try:
                        unc = float(np.clip(
                            ad.V[fi] / (np.mean(ad.V) + 1e-9), 0.5, 3.0
                        ))
                        fric = float(ad.friction[fi]) + 1e-6
                        sl_sigma = (_sl_kappa * unc) / (1.0 + fric * 5.0)
                        sl_sigma = float(np.clip(sl_sigma, 1.0, 5.0))
                        sl_d = sl_sigma * sigma_price
                        sl_dist_arr.append(sl_d)
                        sls_ratio.append(sl_sigma)  # = sl_dist / σ_price
                    except Exception:
                        pass
            except Exception:
                continue

        out['physics'] = {
            'sigma_frac': _stats(sigmas),
            'E_therm_frac': _stats(E_therms),
            'friction_drag_over_sigma': _stats(fds_ratio),
            'sl_dist_over_sigma': _stats(sls_ratio),
            'friction_drag_abs': _stats(friction_drags),
            'sl_dist_abs': _stats(sl_dist_arr),
        }

        # ══ بناء الإشارات (مرة واحدة) ══
        if verbose:
            print(f"  [{tf}] بناء الإشارات...")
        try:
            sigs = bot.build_signals(assets, mode="backtest")
            sigs = bot.deduplicate_signals(sigs)
        except Exception as e:
            out['error'] = f"build_signals: {str(e)[:120]}"
            return out

        out['n_signals'] = int(len(sigs))
        if sigs:
            scores = [float(s.score) for s in sigs]
            out['signal_score'] = _stats(scores)
            out['n_buy'] = int(sum(1 for s in sigs if s.action == "BUY"))
            out['n_sell'] = int(sum(1 for s in sigs if s.action == "SELL"))
            # قياس R:R المُصمَّم
            rrs = []
            sls_sig = []
            for s in sigs[:500]:
                try:
                    sl_d = abs(s.price - s.sl)
                    tp_d = abs(s.tp1 - s.price)
                    if sl_d > 1e-12:
                        rrs.append(tp_d / sl_d)
                    ad = assets.get(s.symbol)
                    if ad is not None:
                        fi = int(s.feat_idx)
                        if 0 <= fi < len(ad.E_therm):
                            sp = float(ad.E_therm[fi]) * float(s.price)
                            if sp > 1e-12:
                                sls_sig.append(sl_d / sp)
                except Exception:
                    pass
            out['signal_RR'] = _stats(rrs)
            out['signal_sl_over_sigma'] = _stats(sls_sig)

        # ══ تشغيل backtest في كل وضع ══
        modes_to_test = []
        if mode in ('fixed', 'both'):
            modes_to_test.append('fixed')
        if mode in ('nofix', 'both'):
            modes_to_test.append('nofix')

        for m in modes_to_test:
            if verbose:
                print(f"  [{tf}] Backtest [{m}]...")
            _pf = (m == 'fixed')
            _saved = getattr(bot.CFG, 'PO_FIXED_PRICE', True)
            bot.CFG.PO_FIXED_PRICE = _pf

            try:
                # نسخة نظيفة من الإشارات (لأن simulate_portfolio يعدّل sig.sl)
                import copy as _copy
                sigs_copy = [_copy.copy(s) for s in sigs]

                # مصفوفة ارتباط
                corr = bot.precompute_correlations(assets)

                # تعطيل log المزعج
                _lvl = bot.log.level
                bot.log.setLevel(logging.ERROR)
                try:
                    trades, equity = bot.simulate_portfolio(
                        sigs_copy, assets, corr, "backtest"
                    )
                    metrics = bot.compute_metrics(
                        trades, equity, bot.CFG.INITIAL_CAPITAL
                    )
                finally:
                    bot.log.setLevel(_lvl)

                # احسب نسب الامتلاء
                fill_map = bot.precompute_entry_fills(
                    assets, sigs_copy,
                    max_wait_bars=bot.effective_bars(
                        bot.CFG.FILL_ENTRY_MAX_WAIT_BARS
                    ),
                    pen_bps=bot.CFG.FILL_PENETRATION_BPS,
                )
                n_s1 = sum(1 for v in fill_map.values()
                           if v is not None and len(v) >= 1
                           and isinstance(v[0], str) and v[0] == 'S1')
                n_s2 = sum(1 for v in fill_map.values()
                           if v is not None and len(v) >= 1
                           and isinstance(v[0], str) and v[0] == 'S2')
                n_none = sum(1 for v in fill_map.values() if v is None)
                n_total = len(fill_map)

                # MFE analysis
                sl_trades = [t for t in trades if "Emergency SL" in t.exit_reason]
                tp_trades = [t for t in trades if "Hard TP" in t.exit_reason]
                apex_trades = [t for t in trades if "Apex" in t.exit_reason]

                mfe_stats = {}
                for label, grp in [("SL", sl_trades),
                                   ("TP", tp_trades),
                                   ("Apex", apex_trades)]:
                    if grp:
                        mfes = [t.mfe_frac for t in grp]
                        mfe_stats[label] = _stats(mfes)

                out['modes'][m] = {
                    'n_trades': int(metrics.get('n_trades', 0)),
                    'win_rate': float(metrics.get('win_rate', 0.0)),
                    'profit_factor': float(metrics.get('profit_factor', 0.0)),
                    'mean_log_return': float(metrics.get('mean_log_return', 0.0)),
                    'median_log_return': float(metrics.get('median_log_return', 0.0)),
                    'sharpe': float(metrics.get('sharpe_ratio', 0.0)),
                    'max_dd_pct': float(metrics.get('max_drawdown_pct', 0.0)),
                    'final_capital': float(metrics.get('final_capital', 0.0)),
                    'total_return_pct': float(metrics.get('total_return_pct', 0.0)),
                    'avg_win': float(metrics.get('avg_win', 0.0)),
                    'avg_loss': float(metrics.get('avg_loss', 0.0)),
                    'exit_distribution': dict(metrics.get('exit_distribution', {})),
                    'fill_stats': {
                        'total': n_total,
                        'S1': n_s1,
                        'S2': n_s2,
                        'none': n_none,
                        's1_rate': n_s1 / max(n_total, 1),
                        's2_rate': n_s2 / max(n_total, 1),
                        'total_rate': (n_s1 + n_s2) / max(n_total, 1),
                    },
                    'mfe_stats': mfe_stats,
                }
            except Exception as e:
                out['modes'][m] = {'error': str(e)[:200]}
            finally:
                bot.CFG.PO_FIXED_PRICE = _saved

        out['ok'] = True
        return out

    except Exception as e:
        import traceback
        out['error'] = f"fatal: {str(e)[:200]}\n{traceback.format_exc()[:500]}"
        return out


# ════════════════════════════════════════════════════════════════
# كتابة التقرير
# ════════════════════════════════════════════════════════════════

def write_report(results: List[Dict[str, Any]],
                 txt_path: str, json_path: str, bot_file: str) -> None:

    # ── JSON ──
    try:
        def _clean(o):
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            if isinstance(o, np.ndarray):
                return o.tolist()
            if isinstance(o, dict):
                return {k: _clean(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [_clean(x) for x in o]
            return o
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(_clean(results), f, indent=2, ensure_ascii=False,
                       default=str)
    except Exception as e:
        print(f"[WARN] فشل JSON: {e}")

    # ── TXT ──
    lines = []
    def W(s=""):
        lines.append(str(s))

    W("=" * 100)
    W("TF FULL DIAGNOSTIC REPORT (with real backtest)")
    W(f"Bot: {bot_file}")
    W(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    W("=" * 100)
    W()

    # ═══════════════════════════════════════════════════════════
    # TABLE 1: TF Parameters
    # ═══════════════════════════════════════════════════════════
    W("─" * 100)
    W("TABLE 1 — TF Parameters & Windows")
    W("─" * 100)
    W(f"{'TF':>5} | {'TF_H':>6} | {'N':>4} | {'W':>4} | {'L':>4} | "
      f"{'ADV':>4} | {'N_h':>6} | {'W_h':>6} | {'L_h':>6} | "
      f"{'n_assets':>8} | {'status':>8}")
    W("-" * 100)
    for r in results:
        if not r.get('ok'):
            W(f"{r['timeframe']:>5} | {'FAIL':>60s} | "
              f"{r.get('error','')[:30]}")
            continue
        w = r.get('windows', {})
        W(f"{r['timeframe']:>5} | {r['TF_HOURS']:>6.3f} | "
          f"{w.get('N',0):>4d} | {w.get('W',0):>4d} | {w.get('L',0):>4d} | "
          f"{w.get('ADV_BARS',0):>4d} | "
          f"{w.get('N_hours',0):>6.1f} | {w.get('W_hours',0):>6.1f} | "
          f"{w.get('L_hours',0):>6.1f} | "
          f"{r.get('n_assets_ok',0):>8d} | {'OK':>8}")
    W()

    # ═══════════════════════════════════════════════════════════
    # TABLE 2: Physics scaling (post-fix)
    # ═══════════════════════════════════════════════════════════
    W("─" * 100)
    W("TABLE 2 — Physics Scaling (المفروض يكون ثابتاً عبر الأُطر)")
    W("─" * 100)
    W(f"{'TF':>5} | {'σ_frac':>8} | {'fd/σ':>7} | {'sl/σ':>7} | "
      f"{'fd_abs':>9} | {'sl_abs':>9} | {'SL_abs/price%':>13}")
    W("-" * 100)
    for r in results:
        if not r.get('ok'):
            continue
        phy = r.get('physics', {})
        sig = phy.get('sigma_frac', {}).get('median', 0)
        fd = phy.get('friction_drag_over_sigma', {}).get('median', 0)
        sl = phy.get('sl_dist_over_sigma', {}).get('median', 0)
        fda = phy.get('friction_drag_abs', {}).get('median', 0)
        sla = phy.get('sl_dist_abs', {}).get('median', 0)
        # sl_abs كنسبة من متوسط السعر — سنستخدم نسبة تقريبية
        sl_pct = (sla / max(sig, 1e-9)) if sig > 0 else 0
        W(f"{r['timeframe']:>5} | {sig:>8.5f} | {fd:>7.3f} | {sl:>7.3f} | "
          f"{fda:>9.4f} | {sla:>9.4f} | {sl_pct:>12.2f}%")
    W()
    W("التفسير:")
    W("  fd/σ  يجب = FRICTION_DIP_KAPPA (افتراضي 4.0) ثابتاً")
    W("  sl/σ  يجب أن يكون بين SL_MIN_SIGMA (1.0) و SL_MAX_SIGMA (5.0)")
    W("  إذا اختلفت القيم بين الأُطر → مشكلة في التحجيم")
    W()

    # ═══════════════════════════════════════════════════════════
    # TABLE 3: Signals summary
    # ═══════════════════════════════════════════════════════════
    W("─" * 100)
    W("TABLE 3 — Signals Summary")
    W("─" * 100)
    W(f"{'TF':>5} | {'n_signals':>10} | {'BUY':>6} | {'SELL':>6} | "
      f"{'RR_med':>8} | {'sl/σ_sig_med':>14} | {'score_med':>10}")
    W("-" * 100)
    for r in results:
        if not r.get('ok'):
            continue
        W(f"{r['timeframe']:>5} | {r.get('n_signals',0):>10d} | "
          f"{r.get('n_buy',0):>6d} | {r.get('n_sell',0):>6d} | "
          f"{r.get('signal_RR',{}).get('median',0):>8.3f} | "
          f"{r.get('signal_sl_over_sigma',{}).get('median',0):>14.3f} | "
          f"{r.get('signal_score',{}).get('median',0):>10.3f}")
    W()

    # ═══════════════════════════════════════════════════════════
    # TABLE 4: Backtest performance — FIXED mode
    # ═══════════════════════════════════════════════════════════
    W("=" * 100)
    W("TABLE 4 — Backtest Performance [PO_FIXED_PRICE=True]")
    W("=" * 100)
    W(f"{'TF':>5} | {'n_tr':>6} | {'WR%':>6} | {'PF':>6} | "
      f"{'E[ln]':>10} | {'Sharpe':>7} | {'MaxDD%':>7} | "
      f"{'fill%':>6} | {'S1%':>5} | {'S2%':>5}")
    W("-" * 100)
    for r in results:
        if not r.get('ok'):
            continue
        m = r.get('modes', {}).get('fixed', {})
        if 'error' in m:
            W(f"{r['timeframe']:>5} | ERROR: {m['error'][:60]}")
            continue
        fs = m.get('fill_stats', {})
        W(f"{r['timeframe']:>5} | {m.get('n_trades',0):>6d} | "
          f"{m.get('win_rate',0)*100:>6.2f} | "
          f"{m.get('profit_factor',0):>6.2f} | "
          f"{m.get('mean_log_return',0):>10.6f} | "
          f"{m.get('sharpe',0):>7.2f} | "
          f"{m.get('max_dd_pct',0):>7.2f} | "
          f"{fs.get('total_rate',0)*100:>6.2f} | "
          f"{fs.get('s1_rate',0)*100:>5.1f} | "
          f"{fs.get('s2_rate',0)*100:>5.1f}")
    W()

    # ═══════════════════════════════════════════════════════════
    # TABLE 5: Backtest performance — NO-FIX mode
    # ═══════════════════════════════════════════════════════════
    W("=" * 100)
    W("TABLE 5 — Backtest Performance [PO_FIXED_PRICE=False]")
    W("=" * 100)
    W(f"{'TF':>5} | {'n_tr':>6} | {'WR%':>6} | {'PF':>6} | "
      f"{'E[ln]':>10} | {'Sharpe':>7} | {'MaxDD%':>7} | "
      f"{'fill%':>6} | {'S1%':>5} | {'S2%':>5}")
    W("-" * 100)
    for r in results:
        if not r.get('ok'):
            continue
        m = r.get('modes', {}).get('nofix', {})
        if 'error' in m:
            W(f"{r['timeframe']:>5} | ERROR: {m['error'][:60]}")
            continue
        fs = m.get('fill_stats', {})
        W(f"{r['timeframe']:>5} | {m.get('n_trades',0):>6d} | "
          f"{m.get('win_rate',0)*100:>6.2f} | "
          f"{m.get('profit_factor',0):>6.2f} | "
          f"{m.get('mean_log_return',0):>10.6f} | "
          f"{m.get('sharpe',0):>7.2f} | "
          f"{m.get('max_dd_pct',0):>7.2f} | "
          f"{fs.get('total_rate',0)*100:>6.2f} | "
          f"{fs.get('s1_rate',0)*100:>5.1f} | "
          f"{fs.get('s2_rate',0)*100:>5.1f}")
    W()

    # ═══════════════════════════════════════════════════════════
    # TABLE 6: Exit distribution
    # ═══════════════════════════════════════════════════════════
    W("=" * 100)
    W("TABLE 6 — Exit Distribution per TF (fixed mode)")
    W("=" * 100)
    for r in results:
        if not r.get('ok'):
            continue
        m = r.get('modes', {}).get('fixed', {})
        if not m or 'error' in m:
            continue
        n_tr = m.get('n_trades', 0)
        if n_tr == 0:
            W(f"{r['timeframe']:>5}: no trades")
            continue
        W(f"--- {r['timeframe']} (n_trades={n_tr}) ---")
        ed = m.get('exit_distribution', {})
        for rsn, cnt in sorted(ed.items(), key=lambda x: -x[1]):
            pct = cnt / n_tr * 100
            W(f"    {rsn:30s}: {cnt:5d} ({pct:5.1f}%)")
        W()

    # ═══════════════════════════════════════════════════════════
    # TABLE 7: MFE analysis
    # ═══════════════════════════════════════════════════════════
    W("=" * 100)
    W("TABLE 7 — MFE Analysis (fixed mode)")
    W("=" * 100)
    for r in results:
        if not r.get('ok'):
            continue
        m = r.get('modes', {}).get('fixed', {})
        if not m or 'error' in m:
            continue
        mfe = m.get('mfe_stats', {})
        if not mfe:
            continue
        W(f"--- {r['timeframe']} ---")
        for label, st in mfe.items():
            W(f"  {label:>6}: n={st.get('n',0):5d} "
              f"median={st.get('median',0)*100:6.3f}% "
              f"mean={st.get('mean',0)*100:6.3f}% "
              f"p95={st.get('p95',0)*100:6.3f}%")
        W()

    # ═══════════════════════════════════════════════════════════
    # SUMMARY OF ISSUES
    # ═══════════════════════════════════════════════════════════
    W("=" * 100)
    W("SUMMARY OF ISSUES")
    W("=" * 100)
    W()

    ok_results = [r for r in results if r.get('ok')]

    # فحص fd/σ
    fds = [r.get('physics', {}).get('friction_drag_over_sigma', {}).get('median', 0)
           for r in ok_results]
    if fds and min(fds) > 0:
        spread = max(fds) / max(min(fds), 1e-6)
        W(f"1. friction_drag / σ: {min(fds):.3f} – {max(fds):.3f} "
          f"(spread ×{spread:.2f})")
        if spread > 1.5:
            W("   ⚠️  SPREAD TOO LARGE — لا يزال التحجيم غير ثابت")
        else:
            W("   ✅ مستقر نسبياً")
    W()

    # فحص sl/σ
    sls = [r.get('physics', {}).get('sl_dist_over_sigma', {}).get('median', 0)
           for r in ok_results]
    if sls and min(sls) > 0:
        spread = max(sls) / max(min(sls), 1e-6)
        W(f"2. sl_dist / σ: {min(sls):.3f} – {max(sls):.3f} "
          f"(spread ×{spread:.2f})")
        if spread > 2.0:
            W("   ⚠️  SPREAD TOO LARGE — SL ما زال غير متكيّف")
        else:
            W("   ✅ مستقر نسبياً")
    W()

    # فحص Win Rate
    W("3. Win Rate by TF (fixed mode):")
    for r in ok_results:
        m = r.get('modes', {}).get('fixed', {})
        if not m or 'error' in m:
            continue
        wr = m.get('win_rate', 0) * 100
        flag = ""
        if wr < 25: flag = "  ⚠️"
        elif wr > 55: flag = "  ✅"
        W(f"   {r['timeframe']:>5}: {wr:>6.2f}%{flag}")
    W()

    # فحص E[ln]
    W("4. E[ln(1+fR)] by TF (fixed mode):")
    for r in ok_results:
        m = r.get('modes', {}).get('fixed', {})
        if not m or 'error' in m:
            continue
        e = m.get('mean_log_return', 0)
        flag = ""
        if e < 0: flag = "  ❌ سالب"
        elif e > 0.001: flag = "  ✅ جيد"
        W(f"   {r['timeframe']:>5}: {e:>+10.6f}{flag}")
    W()

    # فحص E[ln] no-fix
    W("5. E[ln(1+fR)] by TF (no-fix mode):")
    for r in ok_results:
        m = r.get('modes', {}).get('nofix', {})
        if not m or 'error' in m:
            continue
        e = m.get('mean_log_return', 0)
        flag = ""
        if e < 0: flag = "  ❌ سالب"
        elif e > 0.001: flag = "  ✅ جيد"
        W(f"   {r['timeframe']:>5}: {e:>+10.6f}{flag}")
    W()

    # فحص fill rates
    W("6. Fill Rate (Stage 1 / Stage 2 / Total):")
    for r in ok_results:
        m = r.get('modes', {}).get('nofix', {})
        if not m or 'error' in m:
            continue
        fs = m.get('fill_stats', {})
        W(f"   {r['timeframe']:>5}: "
          f"S1={fs.get('s1_rate',0)*100:>5.1f}% "
          f"S2={fs.get('s2_rate',0)*100:>5.1f}% "
          f"total={fs.get('total_rate',0)*100:>5.1f}%")
    W()

    W("=" * 100)
    W("END OF REPORT")
    W("=" * 100)

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print(f"\n[OK] التقرير: {txt_path}")
    print(f"[OK] JSON:    {json_path}")


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bot", type=str, default=None)
    p.add_argument("--timeframes", type=str,
                   default="15m,30m,1h,4h",
                   help="قائمة الأُطر مفصولة بفواصل (افتراضي: 15m,30m,1h,4h)")
    p.add_argument("--assets", type=int, default=3,
                   help="عدد الأصول (افتراضي 3 للسرعة)")
    p.add_argument("--history", type=int, default=120,
                   help="عدد الأيام (افتراضي 120)")
    p.add_argument("--mode", choices=["fixed", "nofix", "both"],
                   default="both",
                   help="الوضع المُختبر (افتراضي both)")
    p.add_argument("--out-txt", type=str,
                   default="tf_full_report.txt")
    p.add_argument("--out-json", type=str,
                   default="tf_full_data.json")
    args = p.parse_args()

    bot_file = detect_bot_file(args.bot)
    print(f"[Main] ملف البوت: {bot_file}")
    bot = import_bot(bot_file)

    try:
        bot.log.setLevel(logging.WARNING)
    except Exception:
        pass

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
    print(f"[Main] الوضع: {args.mode}")
    print()

    results: List[Dict[str, Any]] = []
    for tf in timeframes:
        print(f"━━━ [{tf}] ━━━")
        t0 = time.time()
        try:
            r = run_one_tf(
                bot, exchange, tf,
                assets_n=args.assets,
                history_days=args.history,
                mode=args.mode,
                verbose=True,
            )
        except Exception as e:
            import traceback
            r = {'timeframe': tf, 'ok': False,
                 'error': f"fatal: {e}\n{traceback.format_exc()[:300]}"}
        r['elapsed_s'] = round(time.time() - t0, 1)
        results.append(r)
        status = "OK" if r.get('ok') else f"FAIL: {r.get('error','')[:50]}"
        print(f"  → {status} ({r['elapsed_s']}s)")
        print()

    write_report(results, args.out_txt, args.out_json, bot_file)

    print()
    print("━" * 60)
    print("انتهى. أرسل هذين الملفين:")
    print(f"  - {args.out_txt}")
    print(f"  - {args.out_json}")
    print("━" * 60)


if __name__ == "__main__":
    main()
