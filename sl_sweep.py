#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sl_sweep.py — SL Width Grid Search
==================================
يستكشف تأثير SL_WIDEN_MULT + TP_MULT على الأداء الفعلي.
"""

import os, sys, time, copy, json
import numpy as np
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

CFG.mode = "backtest"
CFG.timeframe = "4h"
CFG.n_assets = 100
CFG.MAX_CONCURRENT_ASSETS = 5
CFG.TRAIL_ENABLED = False
CFG.PO_FIXED_PRICE = False
CFG.REENTRY_COOLDOWN_BARS = 0
CFG.REENTRY_COOLDOWN_ENABLED = True
CFG.history_days = 730
CFG.INITIAL_CAPITAL = 100.0
CFG.MIN_SCORE = 3
CFG.OPP_TP_ENABLED = False
CFG.WATCH_MODE_ENABLED = False
CFG.APEX_ENABLED = False          # عطّل APEX (حكمنا عليه)

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

T._TRADE_LOG_PATH = None

# ════════════════════════════════════════════════════════════════
# الشبكة: SL_WIDEN_MULT × TP_MULT
# ════════════════════════════════════════════════════════════════
SL_WIDEN_VALUES = [0.75, 1.0, 1.5, 2.0, 3.0]
TP_MULT_VALUES  = [2.0, 3.0, 4.0, 6.0, 8.0]

print("═" * 120)
print(f"SL Sweep — tf={CFG.timeframe} n={CFG.n_assets} hist={CFG.history_days}d")
print(f"SL_WIDEN: {SL_WIDEN_VALUES}")
print(f"TP_MULT : {TP_MULT_VALUES}")
print("═" * 120)

# ════════════════════════════════════════════════════════════════
# Load + process + signals (once)
# ════════════════════════════════════════════════════════════════
print("[1/3] Loading data...")
_t0 = time.time()
_ex = ccxt.binance({'enableRateLimit': True,
                     'options': {'defaultType': 'future'}})
_syms = scan_top_assets(_ex, CFG.n_assets)
_raw, _raw_sub = fetch_all_with_subbars(_syms, _ex, CFG.timeframe,
                                          CFG.history_days, workers=5)
print(f"   {len(_raw)} symbols in {time.time()-_t0:.1f}s")

print("[2/3] Processing assets...")
_t0 = time.time()
_assets = {}
for _sym, _df in _raw.items():
    try:
        _ad = process_asset(_sym, _df,
                             current_capital=CFG.INITIAL_CAPITAL,
                             sub_df=_raw_sub.get(_sym) if _raw_sub else None)
        if _ad is not None:
            _assets[_sym] = _ad
    except Exception:
        pass
print(f"   {len(_assets)} assets in {time.time()-_t0:.1f}s")

_corr = precompute_correlations(_assets)

print("[3/3] Building signals...")
_t0 = time.time()
_sigs_orig = deduplicate_signals(build_signals(_assets))
print(f"   {len(_sigs_orig)} signals in {time.time()-_t0:.1f}s")
print()

if not _sigs_orig:
    print("⚠ no signals")
    sys.exit(1)

# ════════════════════════════════════════════════════════════════
# Sweep
# ════════════════════════════════════════════════════════════════
_hdr = (f"{'SL_W':>5} {'TP_M':>5} | "
        f"{'n':>5} {'WR%':>5} {'avgW$':>8} {'avgL$':>8} "
        f"{'RR_ef':>6} | {'PF':>5} {'DD%':>6} "
        f"{'SL%':>5} {'TP%':>5} {'MH%':>5} | "
        f"{'final$':>10}")
print("═" * 120)
print(_hdr)
print("-" * 120)

_results = []
for _slw in SL_WIDEN_VALUES:
    for _tpm in TP_MULT_VALUES:
        _sigs = copy.deepcopy(_sigs_orig)
        CFG.SL_WIDEN_MULT = float(_slw)
        CFG.TP_MULT = float(_tpm)

        try:
            _trades, _eq = simulate_portfolio(_sigs, _assets, _corr,
                                                "backtest")
            _m = compute_metrics(_trades, _eq, CFG.INITIAL_CAPITAL)
        except Exception as _e:
            print(f"{_slw:>5} {_tpm:>5} | ERROR: {_e}")
            continue

        if not _m.get('n_trades'):
            print(f"{_slw:>5} {_tpm:>5} | NO TRADES")
            continue

        _n = _m['n_trades']
        _ex_d = _m['exit_distribution']
        _sl_n = sum(_ex_d.get(k, 0) for k in _ex_d if 'SL' in k)
        _tp_n = sum(_ex_d.get(k, 0) for k in _ex_d if 'TP' in k or 'Hard' in k)
        _mh_n = sum(_ex_d.get(k, 0) for k in _ex_d if 'MaxHold' in k)
        _sl_pct = _sl_n / max(_n, 1) * 100
        _tp_pct = _tp_n / max(_n, 1) * 100
        _mh_pct = _mh_n / max(_n, 1) * 100

        _rr_ef = (abs(_m['avg_win']) / abs(_m['avg_loss'])
                  if _m['avg_loss'] != 0 else 0)

        print(f"{_slw:>5} {_tpm:>5} | "
              f"{_n:>5} {_m['win_rate']*100:>5.1f} "
              f"{_m['avg_win']:>8.2f} {_m['avg_loss']:>8.2f} "
              f"{_rr_ef:>6.2f} | {_m['profit_factor']:>5.2f} "
              f"{_m['max_drawdown_pct']:>5.1f}% "
              f"{_sl_pct:>5.1f} {_tp_pct:>5.1f} {_mh_pct:>5.1f} | "
              f"${_m['final_capital']:>9.2f}")

        _results.append({
            'sl_widen': _slw, 'tp_mult': _tpm,
            'n': _n, 'wr': _m['win_rate'],
            'avg_win': _m['avg_win'], 'avg_loss': _m['avg_loss'],
            'rr_effective': _rr_ef, 'pf': _m['profit_factor'],
            'dd': _m['max_drawdown_pct'],
            'sl_pct': _sl_pct, 'tp_pct': _tp_pct, 'mh_pct': _mh_pct,
            'final': _m['final_capital'],
            'mean_lr': _m['mean_log_return'],
        })

# ════════════════════════════════════════════════════════════════
# Ranking
# ════════════════════════════════════════════════════════════════
if _results:
    print()
    print("═" * 120)
    print("TOP 10 by final capital")
    print("═" * 120)
    _sorted = sorted(_results, key=lambda r: r['final'], reverse=True)[:10]
    for _i, _r in enumerate(_sorted, 1):
        print(f"  #{_i:>2} SL_W={_r['sl_widen']:.2f} TP_M={_r['tp_mult']:.1f} | "
              f"n={_r['n']:>5} WR={_r['wr']*100:>5.1f}% "
              f"RR_ef={_r['rr_effective']:.2f} "
              f"PF={_r['pf']:.3f} DD={_r['dd']:.1f}% "
              f"SL%={_r['sl_pct']:.0f} TP%={_r['tp_pct']:.0f} "
              f"| final=${_r['final']:>10.2f}")

    print()
    print("TOP 5 by profit factor")
    print("═" * 120)
    _sorted2 = sorted(_results, key=lambda r: r['pf'], reverse=True)[:5]
    for _i, _r in enumerate(_sorted2, 1):
        print(f"  #{_i} SL_W={_r['sl_widen']:.2f} TP_M={_r['tp_mult']:.1f} | "
              f"PF={_r['pf']:.3f} WR={_r['wr']*100:.1f}% "
              f"RR_ef={_r['rr_effective']:.2f} "
              f"final=${_r['final']:.2f}")

    with open("sl_sweep_results.json", "w") as _f:
        json.dump(_results, _f, indent=2, default=str)
    print()
    print("💾 saved: sl_sweep_results.json")

print()
print("✅ done.")
