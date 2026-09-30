#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apex_sweep.py — APEX Threshold Grid Search
==========================================
يحمل البيانات مرة واحدة، ثم يعيد محاكاة المحفظة عبر شبكة
من عتبات APEX. يقارن النتائج إحصائياً.

التشغيل:
    python apex_sweep.py
"""

import os, sys, time, copy, json
import numpy as np

# ── إعدادات مطابقة لسطر أوامرك ──
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import ccxt
import trading as T
from trading import (
    CFG, scan_top_assets, fetch_all_with_subbars, process_asset,
    precompute_correlations, build_signals, deduplicate_signals,
    simulate_portfolio, compute_metrics, compute_tf_scale,
)

# ════════════════════════════════════════════════════════════════
# إعدادات الجلسة (طابق سطر أوامرك الحقيقي)
# ════════════════════════════════════════════════════════════════
CFG.mode = "backtest"
CFG.timeframe = "4h"
CFG.n_assets = 100            # خفّض إلى 50 للسرعة
CFG.MAX_CONCURRENT_ASSETS = 5
CFG.TRAIL_ENABLED = False
CFG.PO_FIXED_PRICE = False
CFG.REENTRY_COOLDOWN_BARS = 0
CFG.REENTRY_COOLDOWN_ENABLED = True
CFG.history_days = 730        # خفّض إلى 365 للسرعة
CFG.INITIAL_CAPITAL = 100.0
CFG.MIN_SCORE = 3
CFG.OPP_TP_ENABLED = False    # نعزل تأثير APEX
CFG.WATCH_MODE_ENABLED = False # مفعّل بشكل صريح لتسريع الـ sweep

# مزوّد TF
try:
    _probe = ccxt.binance()
    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = compute_tf_scale(
        _probe, CFG.timeframe
    )
except Exception:
    compute_tf_scale(None, CFG.timeframe)

_tf_h = max(float(CFG.TF_HOURS), 1e-6)
CFG.N = max(CFG.N, int(np.ceil(CFG.N_HOURS / _tf_h)))
CFG.W = max(CFG.W, int(np.ceil(CFG.W_HOURS / _tf_h)))
CFG.L = max(CFG.L, int(np.ceil(CFG.L_HOURS / _tf_h)))
CFG.ADV_BARS = max(1, int(round(CFG.ADV_HOURS / _tf_h)))

# إلغاء trade logging مؤقتاً (لتجنب تلويث الملفات)
T._TRADE_LOG_PATH = None

# ════════════════════════════════════════════════════════════════
# الشبكة (عدّلها كما تشاء)
# ════════════════════════════════════════════════════════════════
# كل عنصر: (اسم، kappa_pnl, kappa_energy, kappa_accel)
# ('off', None, None, None) = APEX معطّل تماماً (المرجع)
GRID = [
    ('OFF',      None, None, None),    # baseline
    ('tight',     0.3,  0.3,  0.2),
    ('default',   0.5,  0.5,  0.3),    # القيم الحالية
    ('loose',     0.7,  0.7,  0.4),
    ('looser',    1.0,  1.0,  0.5),
    ('aggr',      1.5,  1.5,  0.8),
    ('wide_E',    0.5,  1.0,  0.3),    # طاقة أعرض
    ('wide_P',    1.0,  0.5,  0.3),    # ربح أدنى أعلى
    ('accel_off', 0.5,  0.5,  0.0),    # بلا فلتر accel
    ('accel_hi',  0.5,  0.5,  1.0),    # accel صارم
]

# ════════════════════════════════════════════════════════════════
# 1) تحميل البيانات مرة واحدة
# ════════════════════════════════════════════════════════════════
print("═" * 100)
print(f"APEX Sweep — tf={CFG.timeframe} n_assets={CFG.n_assets} "
      f"history={CFG.history_days}d")
print("═" * 100)
print()

print("[1/3] Loading data from cache/network...")
_t0 = time.time()
_ex = ccxt.binance({'enableRateLimit': True,
                     'options': {'defaultType': 'future'}})
_syms = scan_top_assets(_ex, CFG.n_assets)
_raw, _raw_sub = fetch_all_with_subbars(
    _syms, _ex, CFG.timeframe, CFG.history_days, workers=5
)
print(f"   loaded {len(_raw)} symbols in {time.time()-_t0:.1f}s")

# ════════════════════════════════════════════════════════════════
# 2) معالجة الأصول مرة واحدة
# ════════════════════════════════════════════════════════════════
print("[2/3] Processing assets (KMeans + features)...")
_t0 = time.time()
_assets = {}
for _sym, _df in _raw.items():
    try:
        _ad = process_asset(_sym, _df,
                             current_capital=CFG.INITIAL_CAPITAL,
                             sub_df=_raw_sub.get(_sym) if _raw_sub else None)
        if _ad is not None:
            _assets[_sym] = _ad
    except Exception as _e:
        print(f"   ✗ {_sym}: {_e}")
print(f"   processed {len(_assets)} assets in {time.time()-_t0:.1f}s")

_corr = precompute_correlations(_assets)

# ════════════════════════════════════════════════════════════════
# 3) بناء الإشارات مرة واحدة
# ════════════════════════════════════════════════════════════════
print("[3/3] Building signals...")
_t0 = time.time()
_sigs_orig = deduplicate_signals(build_signals(_assets))
print(f"   {len(_sigs_orig)} signals in {time.time()-_t0:.1f}s")
print()

if not _sigs_orig:
    print("⚠  لا إشارات — تحقق من الإعدادات")
    sys.exit(1)

# ════════════════════════════════════════════════════════════════
# 4) الـ sweep
# ════════════════════════════════════════════════════════════════
print("═" * 100)
print("SWEEP RESULTS")
print("═" * 100)

# جدول الرأس
_hdr = (f"{'name':>10} {'kp':>5} {'ke':>5} {'ka':>5} | "
        f"{'n':>5} {'apex':>5} {'apex%':>6} | "
        f"{'wr%':>6} {'avgW$':>8} {'avgL$':>8} | "
        f"{'PF':>5} {'DD%':>6} {'μ_lr':>10} {'final$':>10}")
print(_hdr)
print("-" * len(_hdr))

_results = []
for _name, _kp, _ke, _ka in GRID:
    # نسخة عميقة من الإشارات (لأن simulate_portfolio يُعدّلها)
    _sigs = copy.deepcopy(_sigs_orig)

    if _kp is None:
        CFG.APEX_ENABLED = False
    else:
        CFG.APEX_ENABLED = True
        CFG.APEX_SIGMA_SCALED = True
        CFG.APEX_KAPPA_PNL    = float(_kp)
        CFG.APEX_KAPPA_ENERGY = float(_ke)
        CFG.APEX_KAPPA_ACCEL  = float(_ka)

    try:
        _trades, _eq = simulate_portfolio(_sigs, _assets, _corr, "backtest")
        _m = compute_metrics(_trades, _eq, CFG.INITIAL_CAPITAL)
    except Exception as _e:
        import traceback
        print(f"{_name:>10} | ERROR: {_e}")
        traceback.print_exc()
        continue

    if not _m.get('n_trades'):
        print(f"{_name:>10} | NO TRADES")
        continue

    _apex_n = sum(1 for _t in _trades
                  if 'Apex' in str(_t.exit_reason))
    _apex_pct = _apex_n / max(_m['n_trades'], 1) * 100

    _kp_s = f"{_kp:.2f}" if _kp is not None else "—"
    _ke_s = f"{_ke:.2f}" if _ke is not None else "—"
    _ka_s = f"{_ka:.2f}" if _ka is not None else "—"

    print(f"{_name:>10} {_kp_s:>5} {_ke_s:>5} {_ka_s:>5} | "
          f"{_m['n_trades']:>5} {_apex_n:>5} {_apex_pct:>5.1f}% | "
          f"{_m['win_rate']*100:>5.1f}% "
          f"{_m['avg_win']:>8.3f} {_m['avg_loss']:>8.3f} | "
          f"{_m['profit_factor']:>5.2f} "
          f"{_m['max_drawdown_pct']:>5.1f}% "
          f"{_m['mean_log_return']:>+10.6f} "
          f"${_m['final_capital']:>9.2f}")

    _results.append({
        'name': _name,
        'kp': _kp, 'ke': _ke, 'ka': _ka,
        'n': _m['n_trades'],
        'apex_n': _apex_n,
        'apex_pct': _apex_pct,
        'wr': _m['win_rate'],
        'avg_win': _m['avg_win'],
        'avg_loss': _m['avg_loss'],
        'pf': _m['profit_factor'],
        'dd': _m['max_drawdown_pct'],
        'mean_lr': _m['mean_log_return'],
        'final': _m['final_capital'],
        'exit_dist': _m['exit_distribution'],
    })

# ════════════════════════════════════════════════════════════════
# 5) الترتيب
# ════════════════════════════════════════════════════════════════
if _results:
    print()
    print("═" * 100)
    print("TOP 5 by mean_log_return")
    print("═" * 100)
    _top = sorted(_results, key=lambda r: r['mean_lr'], reverse=True)[:5]
    for _i, _r in enumerate(_top, 1):
        print(f"  #{_i} {_r['name']:>10}  "
              f"kp={_r['kp']} ke={_r['ke']} ka={_r['ka']}  "
              f"|  μ_lr={_r['mean_lr']:+.6f}  "
              f"WR={_r['wr']*100:.1f}%  "
              f"PF={_r['pf']:.3f}  "
              f"DD={_r['dd']:.1f}%  "
              f"apex%={_r['apex_pct']:.1f}%  "
              f"final=${_r['final']:.2f}")

    print()
    print("TOP 5 by profit_factor")
    print("═" * 100)
    _top2 = sorted(_results, key=lambda r: r['pf'], reverse=True)[:5]
    for _i, _r in enumerate(_top2, 1):
        print(f"  #{_i} {_r['name']:>10}  "
              f"kp={_r['kp']} ke={_r['ke']} ka={_r['ka']}  "
              f"|  PF={_r['pf']:.3f}  "
              f"μ_lr={_r['mean_lr']:+.6f}  "
              f"WR={_r['wr']*100:.1f}%  "
              f"DD={_r['dd']:.1f}%  "
              f"apex%={_r['apex_pct']:.1f}%")

    # Baseline comparison
    _base = next((r for r in _results if r['name'] == 'OFF'), None)
    if _base:
        print()
        print("═" * 100)
        print(f"BASELINE (APEX OFF): μ_lr={_base['mean_lr']:+.6f}  "
              f"WR={_base['wr']*100:.1f}%  PF={_base['pf']:.3f}  "
              f"DD={_base['dd']:.1f}%  final=${_base['final']:.2f}")
        print("═" * 100)
        print("DELTAS vs baseline:")
        for _r in _results:
            if _r['name'] == 'OFF':
                continue
            _d_mu = (_r['mean_lr'] - _base['mean_lr'])
            _d_pf = _r['pf'] - _base['pf']
            _d_final = _r['final'] - _base['final']
            _sign = '+' if _d_mu > 0 else ''
            print(f"  {_r['name']:>10}: "
                  f"Δμ_lr={_sign}{_d_mu:+.6f}  "
                  f"ΔPF={_d_pf:+.3f}  "
                  f"Δfinal=${_d_final:+.2f}  "
                  f"apex%={_r['apex_pct']:.1f}%")

    # Exit distribution for winner
    _winner = _top[0]
    print()
    print("═" * 100)
    print(f"EXIT DISTRIBUTION — winner: {_winner['name']}")
    print("═" * 100)
    for _k, _v in sorted(_winner['exit_dist'].items(),
                          key=lambda x: -x[1]):
        _pct = _v / max(_winner['n'], 1) * 100
        print(f"  {_k:30s}: {_v:6d} ({_pct:5.1f}%)")

    # احفظ النتائج JSON
    with open("apex_sweep_results.json", "w") as _f:
        json.dump(_results, _f, indent=2, default=str)
    print()
    print("💾 saved: apex_sweep_results.json")

print()
print("✅ done.")
