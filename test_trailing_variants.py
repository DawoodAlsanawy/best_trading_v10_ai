#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_trailing_variants.py — 7 إعدادات trailing × 3 سنوات.

المقارنة:
  - no_trail + Apex (baseline الإنتاج)
  - current default trailing + Apex
  - 3 wide trailing variants + Apex
  - wide trailing بدون Apex (هل يمكن الاستبدال؟)
  - no trailing, no Apex (control)
"""

import os, sys, time, json, argparse, copy
from collections import defaultdict

for v in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
          'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[v] = '1'
sys.path.insert(0, '.')

import numpy as np
import trading_prod_buy_only as engine
import __main__ as _pcmain
for _cn in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(engine, _cn):
        setattr(_pcmain, _cn, getattr(engine, _cn))

CFG = engine.CFG


# ═══════════════════════════════════════════════════════════════
# Configs
# ═══════════════════════════════════════════════════════════════

CONFIGS = {
    'baseline_prod': {
        'TRAIL_ENABLED': False,
        'APEX_ENABLED': True,
    },
    'current_trail': {
        'TRAIL_ENABLED': True,
        'TRAIL_KAPPA': 0.30,
        'TRAIL_ACTIVATE_AT_R': 2.5,
        'APEX_ENABLED': True,
    },
    'wide_1.0_2R': {
        'TRAIL_ENABLED': True,
        'TRAIL_KAPPA': 1.0,
        'TRAIL_ACTIVATE_AT_R': 2.0,
        'APEX_ENABLED': True,
    },
    'wide_1.5_2R': {
        'TRAIL_ENABLED': True,
        'TRAIL_KAPPA': 1.5,
        'TRAIL_ACTIVATE_AT_R': 2.0,
        'APEX_ENABLED': True,
    },
    'wide_2.0_2R': {
        'TRAIL_ENABLED': True,
        'TRAIL_KAPPA': 2.0,
        'TRAIL_ACTIVATE_AT_R': 2.0,
        'APEX_ENABLED': True,
    },
    'wide_1.5_2R_no_apex': {
        'TRAIL_ENABLED': True,
        'TRAIL_KAPPA': 1.5,
        'TRAIL_ACTIVATE_AT_R': 2.0,
        'APEX_ENABLED': False,
    },
    'no_trail_no_apex': {
        'TRAIL_ENABLED': False,
        'APEX_ENABLED': False,
    },
}

WINDOWS = {
    '2024': '2024-12-31',
    '2025': '2025-12-31',
    '2026': '2026-10-01',
}


# ═══════════════════════════════════════════════════════════════
# Setup / Load
# ═══════════════════════════════════════════════════════════════

def base_config(end_date, tf, n_assets):
    CFG.BACKTEST_END_DATE = end_date
    CFG.history_days = 365
    CFG.n_assets = n_assets
    CFG.timeframe = tf
    # BUY-only
    if hasattr(CFG, 'SELL_ENABLED'):
        CFG.SELL_ENABLED = False
    CFG.GAUGE_DISABLE_SELL = True
    CFG.GAUGE_FILTER_ENABLED = True
    # Risk
    CFG.MAX_CONCURRENT_ASSETS = 3
    CFG.PORTFOLIO_HEAT_MAX = 0.10
    CFG.MIN_RISK_PER_TRADE = 0.005
    CFG.REENTRY_COOLDOWN_ENABLED = True
    CFG.REENTRY_COOLDOWN_BARS = 3
    # Defaults for tested params
    CFG.TRAIL_ENABLED = False
    CFG.TRAIL_KAPPA = 0.30
    CFG.TRAIL_ACTIVATE_AT_R = 2.5
    CFG.TRAIL_DYNAMIC = True
    CFG.TRAIL_MIN_FRAC = 0.002
    CFG.TRAIL_MAX_FRAC = 0.008
    CFG.TRAIL_DISTANCE = 0.003
    CFG.TRAIL_ACTIVATE_MFE = 0.004
    CFG.TRAIL_MIN_STEP = 0.0005
    CFG.APEX_ENABLED = True

    import ccxt
    ex = ccxt.binance()
    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = \
        engine.compute_tf_scale(ex, tf)
    _tf_h = max(float(CFG.TF_HOURS), 1e-6)
    CFG.N = max(24, int(np.ceil(24.0 / _tf_h)))
    CFG.W = max(20, int(np.ceil(20.0 / _tf_h)))
    CFG.L = max(10, int(np.ceil(10.0 / _tf_h)))
    CFG.ADV_BARS = max(1, int(round(24.0 / _tf_h)))


def load_window(end_date, n_assets, tf):
    import ccxt
    ex = ccxt.binance({'enableRateLimit': True,
                       'options': {'defaultType': 'future'}})
    syms = engine.scan_top_assets(ex, n_assets)
    raw, raw_sub = engine.fetch_all_with_subbars(
        syms, ex, tf, CFG.history_days, workers=5)
    assets = {}
    for sym, df in raw.items():
        ad = engine._load_asset_cache(sym, tf, df, CFG)
        if ad is None:
            ad = engine.process_asset(
                sym, df,
                current_capital=CFG.INITIAL_CAPITAL,
                sub_df=(raw_sub.get(sym) if raw_sub else None))
            if ad is not None:
                engine._save_asset_cache(sym, tf, df, ad, CFG)
        if ad is not None:
            assets[sym] = ad
    return assets


# ═══════════════════════════════════════════════════════════════
# Run one config
# ═══════════════════════════════════════════════════════════════

def run_config(sigs_orig, assets, corr, overrides):
    # Deep-copy sigs (simulate mutates them)
    sigs = copy.deepcopy(sigs_orig)

    saved = {}
    for k in overrides:
        saved[k] = getattr(CFG, k, None)
    for k, v in overrides.items():
        setattr(CFG, k, v)

    t0 = time.time()
    try:
        trades, equity = engine.simulate_portfolio(
            sigs, assets, corr, 'backtest')
        m = engine.compute_metrics(trades, equity, CFG.INITIAL_CAPITAL)
    except Exception:
        import traceback
        traceback.print_exc()
        for k, v in saved.items():
            setattr(CFG, k, v)
        return None

    for k, v in saved.items():
        setattr(CFG, k, v)

    # Exit distribution
    exit_dist = defaultdict(int)
    trail_wins = 0
    trail_losses = 0
    for t in trades:
        ec = t.exit_reason.split('(')[0].split(':')[0].strip()
        exit_dist[ec] += 1
        if 'Emergency SL' in t.exit_reason:
            if t.net_pnl > 0:
                trail_wins += 1
            else:
                trail_losses += 1

    return {
        'sharpe': float(m.get('sharpe_ratio', 0)),
        'final': float(m.get('final_capital', 0)),
        'n': int(m.get('n_trades', 0)),
        'wr': float(m.get('win_rate', 0)),
        'pf': float(m.get('profit_factor', 0)),
        'dd': float(m.get('max_drawdown_pct', 0)),
        'avg_win': float(m.get('avg_win', 0)),
        'avg_loss': float(m.get('avg_loss', 0)),
        'mean_lr': float(m.get('mean_log_return', 0)),
        'trail_wins': trail_wins,
        'trail_losses': trail_losses,
        'exit_dist': dict(exit_dist),
        'dt': time.time() - t0,
    }


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='4h')
    ap.add_argument('--nassets', type=int, default=100)
    args = ap.parse_args()

    print('═' * 92)
    print(f'  test_trailing_variants — tf={args.tf}, n={args.nassets}')
    print(f'  Configs: {len(CONFIGS)}  ×  Windows: 3')
    print('═' * 92)

    all_results = {}

    for label, end in WINDOWS.items():
        print(f'\n{"─" * 92}')
        print(f'  Window {label}  (end={end})')
        print(f'{"─" * 92}')
        base_config(end, args.tf, args.nassets)

        t0 = time.time()
        assets = load_window(end, args.nassets, args.tf)
        print(f'  Loaded {len(assets)} assets in {time.time()-t0:.0f}s')
        if not assets:
            continue

        t0 = time.time()
        sigs = engine.build_signals(assets, mode='backtest')
        sigs = engine.deduplicate_signals(sigs)
        print(f'  Signals: {len(sigs)} in {time.time()-t0:.0f}s')

        corr = engine.precompute_correlations(assets)

        results = {}
        print(f'\n  Running {len(CONFIGS)} configs:')
        for name, overrides in CONFIGS.items():
            r = run_config(sigs, assets, corr, overrides)
            if r is None:
                continue
            results[name] = r
            print(f'    {name:<24} Sharpe={r["sharpe"]:>8.3f}  '
                  f'Final=${r["final"]:>8.2f}  n={r["n"]:>4}  '
                  f'WR={r["wr"]*100:>5.1f}%  DD={r["dd"]:>5.1f}%  '
                  f'({r["dt"]:.0f}s)')

        all_results[label] = results

    # ═══ FINAL REPORT ═══
    print('\n\n' + '═' * 100)
    print('  FINAL — Trailing variants comparison')
    print('═' * 100)

    # Sharpe table
    print(f'\n  ▶ Sharpe عبر السنوات:')
    print(f'  {"Config":<24} {"2024":>10} {"2025":>10} '
          f'{"2026":>10} {"Min":>10} {"Avg":>10}')
    print(f'  {"─"*24} {"─"*10} {"─"*10} {"─"*10} {"─"*10} {"─"*10}')
    for name in CONFIGS:
        ss = []
        for y in WINDOWS:
            r = all_results.get(y, {}).get(name)
            if r is None:
                ss = []; break
            ss.append(r['sharpe'])
        if len(ss) != 3:
            continue
        print(f'  {name:<24} {ss[0]:>10.3f} {ss[1]:>10.3f} '
              f'{ss[2]:>10.3f} {min(ss):>10.3f} {np.mean(ss):>10.3f}')

    # Final capital table
    print(f'\n  ▶ رأس المال النهائي:')
    print(f'  {"Config":<24} {"2024":>12} {"2025":>12} '
          f'{"2026":>12} {"GeoMean":>12}')
    print(f'  {"─"*24} {"─"*12} {"─"*12} {"─"*12} {"─"*12}')
    for name in CONFIGS:
        ff = []
        for y in WINDOWS:
            r = all_results.get(y, {}).get(name)
            if r is None:
                ff = []; break
            ff.append(r['final'])
        if len(ff) != 3:
            continue
        geo = np.prod(ff) ** (1/3)
        print(f'  {name:<24} ${ff[0]:>10.2f} ${ff[1]:>10.2f} '
              f'${ff[2]:>10.2f} ${geo:>10.2f}')

    # Exit distribution (2025)
    print(f'\n  ▶ توزيع الخروج (2025):')
    print(f'  {"Config":<24} {"EmSL":>8} {"Apex":>8} '
          f'{"HardTP":>8} {"MaxHold":>8} {"TrailWins":>10}')
    print(f'  {"─"*24} {"─"*8} {"─"*8} {"─"*8} {"─"*8} {"─"*10}')
    for name in CONFIGS:
        r = all_results.get('2025', {}).get(name)
        if r is None:
            continue
        ed = r['exit_dist']
        em = sum(v for k, v in ed.items() if 'Emergency' in k)
        ap = sum(v for k, v in ed.items() if 'Apex' in k)
        ht = sum(v for k, v in ed.items() if 'Hard' in k)
        mh = sum(v for k, v in ed.items() if 'MaxHold' in k)
        tw = r.get('trail_wins', 0)
        print(f'  {name:<24} {em:>8} {ap:>8} {ht:>8} {mh:>8} {tw:>10}')

    # Verdict
    print(f'\n{"═" * 100}')

    # Find best
    best_avg = -999
    best_name = None
    for name in CONFIGS:
        ss = []
        for y in WINDOWS:
            r = all_results.get(y, {}).get(name)
            if r is None:
                ss = []; break
            ss.append(r['sharpe'])
        if len(ss) != 3:
            continue
        avg = np.mean(ss)
        if avg > best_avg:
            best_avg = avg
            best_name = name

    if best_name:
        print(f'\n  🏆 الأفضل حسب Avg Sharpe: {best_name} ({best_avg:.3f})')

    # Determine if trailing can replace Apex
    b = all_results.get('2025', {}).get('baseline_prod', {})
    w_no_apex = all_results.get('2025', {}).get('wide_1.5_2R_no_apex', {})
    if b and w_no_apex:
        delta = w_no_apex['sharpe'] - b['sharpe']
        print(f'\n  هل يمكن استبدال Apex بـ Trailing؟')
        print(f'    baseline_prod Sharpe: {b["sharpe"]:.3f}')
        print(f'    wide_1.5_2R_no_apex Sharpe: {w_no_apex["sharpe"]:.3f}')
        print(f'    ΔSharpe = {delta:+.3f}')
        if delta > 0.1:
            print(f'    ✅ Trailing أفضل — يمكن استبدال Apex')
        elif delta > -0.1:
            print(f'    🟡 متقارب — يمكن الاستبدال بدون خسارة كبيرة')
        else:
            print(f'    ❌ Apex أفضل بكثير — لا تستبدله')

    # Save
    os.makedirs('results', exist_ok=True)
    out = f'results/trailing_variants_{args.tf}.json'
    with open(out, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f'\n  Saved: {out}')
    print('═' * 100)


if __name__ == '__main__':
    main()
