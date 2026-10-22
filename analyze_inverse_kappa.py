#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Inverse Kappa Feasibility Study (Phase 1)                                   ║
║                                                                              ║
║  Tests entering BEFORE p_tunnel:                                             ║
║    P_entry = p_tunnel + kappa * sigma_bar * p_tunnel  (for BUY)              ║
║    P_entry = p_tunnel - kappa * sigma_bar * p_tunnel  (for SELL)             ║
║                                                                              ║
║  Measures:                                                                   ║
║    - Distribution of ACTUAL reversal points (kappa_rev)                      ║
║    - Fill rate, win rate, expected R/signal at each kappa                    ║
║    - Walk-forward validation (train vs test)                                 ║
║    - Recommended optimal kappa                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, glob, importlib.util
import numpy as np
import pandas as pd
import warnings
from datetime import timedelta

warnings.filterwarnings('ignore')

spec = importlib.util.spec_from_file_location("bot", "trading_2_live4_claude2_v4.py")
bot = importlib.util.module_from_spec(spec)
sys.modules["bot"] = bot
spec.loader.exec_module(bot)


def load_local_data(cache_dir, timeframe, target_symbols, history_days, end_date_str=None):
    main_data, sub_data = {}, {}
    pattern = os.path.join(cache_dir, f"*_{timeframe}.parquet")
    files = glob.glob(pattern)
    sub_tf = bot._get_subbars_tf(timeframe)
    bot.CFG.BACKTEST_END_DATE = end_date_str
    _end_dt = bot._resolve_end_datetime()
    since_full_dt = _end_dt - timedelta(days=int(history_days))
    print(f"✂️  Slicing: {since_full_dt.strftime('%Y-%m-%d')} → {_end_dt.strftime('%Y-%m-%d')}")
    
    for fpath in files:
        parts = os.path.basename(fpath).split('_')
        if len(parts) < 3: continue
        sym = f"{parts[0]}/{parts[1]}"
        if target_symbols and sym not in target_symbols: continue
        try:
            df = pd.read_parquet(fpath)
            df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
            df = df[(df.index >= since_full_dt) & (df.index <= _end_dt)]
            if len(df) > 0: main_data[sym] = df
            
            sub_path = os.path.join(cache_dir, f"{parts[0]}_{parts[1]}_{sub_tf}_sub.parquet")
            if os.path.exists(sub_path):
                sdf = pd.read_parquet(sub_path)
                sdf.index = sdf.index.tz_localize("UTC") if sdf.index.tz is None else sdf.index.tz_convert("UTC")
                sdf = sdf[(sdf.index >= since_full_dt) & (sdf.index <= _end_dt)]
                if len(sdf) > 0: sub_data[sym] = sdf
        except: pass
    return main_data, sub_data


def simulate_kappa(sig, ad, p_tunnel, p_close, sigma, sl_dist, ref_sl, ref_tp, kappa):
    """Simulate one signal for one kappa value. Returns dict."""
    sign = 1.0 if sig.action == "BUY" else -1.0
    
    # Entry price
    p_entry = p_tunnel + sign * kappa * sigma * p_tunnel
    
    # Fillability: entry must be BEFORE tunnel (between market and tunnel)
    if sign * (p_entry - p_close) >= 0:
        return {'outcome': 'not_fillable'}
    
    # TP must be beyond entry (positive R:R)
    if sign * (ref_tp - p_entry) <= 0:
        return {'outcome': 'not_fillable'}
    
    # Sub-bar arrays
    start = sig.close_idx + 1
    end = min(start + 12, ad.sub_highs.shape[0])
    sh = ad.sub_highs[start:end].flatten()
    sl_arr = ad.sub_lows[start:end].flatten()
    
    # Find touch (price reaches p_tunnel)
    touch = -1
    for i in range(len(sh)):
        if sign > 0 and sl_arr[i] <= p_tunnel: touch = i; break
        if sign < 0 and sh[i] >= p_tunnel: touch = i; break
    if touch == -1:
        return {'outcome': 'no_touch'}
    
    # Simulate from touch onward
    filled = False
    fill_bar = -1
    outcome = 'timeout'
    
    for i in range(touch, len(sh)):
        if not filled:
            if sign > 0 and sl_arr[i] <= p_entry:
                filled = True; fill_bar = i
            elif sign < 0 and sh[i] >= p_entry:
                filled = True; fill_bar = i
        
        if filled:
            if sign > 0:
                if sl_arr[i] <= ref_sl: outcome = 'loss'; break
                if sh[i] >= ref_tp: outcome = 'win'; break
            else:
                if sh[i] >= ref_sl: outcome = 'loss'; break
                if sl_arr[i] <= ref_tp: outcome = 'win'; break
    
    if not filled:
        return {'outcome': 'not_filled'}
    
    risk = abs(p_entry - ref_sl)
    reward = abs(ref_tp - p_entry)
    R_if_win = reward / risk if risk > 0 else 0
    
    return {
        'outcome': outcome,
        'p_entry': p_entry,
        'risk_frac': risk / p_entry,
        'reward_frac': reward / p_entry,
        'R_if_win': R_if_win,
        'fill_bar': fill_bar,
    }


def compute_actual_reversal_depth(sig, ad, p_tunnel, sigma, ref_sl, ref_tp):
    """Find how deep the price actually went (in sigma units) before TP/SL."""
    sign = 1.0 if sig.action == "BUY" else -1.0
    start = sig.close_idx + 1
    end = min(start + 12, ad.sub_highs.shape[0])
    sh = ad.sub_highs[start:end].flatten()
    sl_arr = ad.sub_lows[start:end].flatten()
    
    touch = -1
    for i in range(len(sh)):
        if sign > 0 and sl_arr[i] <= p_tunnel: touch = i; break
        if sign < 0 and sh[i] >= p_tunnel: touch = i; break
    if touch == -1: return None, None
    
    extreme = p_tunnel
    outcome = 'timeout'
    for i in range(touch, len(sh)):
        if sign > 0:
            if sl_arr[i] < extreme: extreme = sl_arr[i]
            if sl_arr[i] <= ref_sl: outcome = 'loss'; break
            if sh[i] >= ref_tp: outcome = 'win'; break
        else:
            if sh[i] > extreme: extreme = sh[i]
            if sh[i] >= ref_sl: outcome = 'loss'; break
            if sl_arr[i] <= ref_tp: outcome = 'win'; break
    
    kappa_rev = sign * (extreme - p_tunnel) / (sigma * p_tunnel) if sigma > 0 else 0
    return kappa_rev, outcome


def main():
    HISTORY_DAYS = 730
    END_DATE = None
    
    print("⏳ Setting up bot config to match backtest command...")
    bot.CFG.timeframe = '4h'
    bot.CFG.history_days = HISTORY_DAYS
    bot.CFG.GAUGE_DISABLE_SELL = False
    bot.CFG.SELL_GAUGE_PCT = 85
    bot.CFG.SL_WIDEN_MULT = 1.5
    bot.CFG.PARTIAL_TP_R = 1.2
    bot.CFG.TP_MULT = 2.0
    bot.CFG.PO_FIXED_PRICE = False
    bot.CFG.MIN_SCORE = 4
    
    # Load symbols
    traded_symbols = set()
    if os.path.exists("trades_log_backtest.jsonl"):
        with open("trades_log_backtest.jsonl") as f:
            for line in f:
                if line.strip():
                    try:
                        r = json.loads(line)
                        if not r.get('_meta') and 'symbol' in r:
                            traded_symbols.add(r['symbol'])
                    except: pass
    print(f"✓ Found {len(traded_symbols)} symbols in log.")
    
    raw, raw_sub = load_local_data("market_data_cache", "4h", traded_symbols, HISTORY_DAYS, END_DATE)
    
    print("⏳ Processing Physics State...")
    assets = {}
    for sym, df in raw.items():
        ad = bot.process_asset(sym, df, current_capital=100, sub_df=raw_sub.get(sym))
        if ad is not None: assets[sym] = ad
    
    print("⏳ Building Signals...")
    sigs = bot.deduplicate_signals(bot.build_signals(assets, mode='backtest'))
    print(f"✓ Generated {len(sigs)} signals.")
    
    # ══════════════════════════════════════════════════════════════
    # Sweep over kappa values
    # ══════════════════════════════════════════════════════════════
    kappas = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
    results = {k: [] for k in kappas}
    kappa_rev_win = []
    kappa_rev_loss = []
    
    print("\n⏳ Running kappa sweep...")
    for si, sig in enumerate(sigs):
        if si % 1000 == 0 and si > 0:
            print(f"   ... {si}/{len(sigs)}")
        
        ad = assets[sig.symbol]
        if ad.sub_highs is None or ad.sub_lows is None: continue
        
        p_tunnel = float(bot._backtest_entry_target(sig, ad))
        p_close = float(ad.closes[sig.close_idx])
        sigma = float(ad.E_therm[sig.feat_idx])
        sl_dist = abs(p_tunnel - float(sig.sl))
        
        if sl_dist <= 1e-9 or sigma <= 1e-6: continue
        
        sign = 1.0 if sig.action == "BUY" else -1.0
        ref_sl = p_tunnel - sign * sl_dist
        ref_tp = p_tunnel + sign * sl_dist * bot.CFG.TP_MULT
        
        # Compute actual reversal depth
        kv, ref_outcome = compute_actual_reversal_depth(
            sig, ad, p_tunnel, sigma, ref_sl, ref_tp
        )
        if kv is not None:
            if ref_outcome == 'win': kappa_rev_win.append(kv)
            elif ref_outcome == 'loss': kappa_rev_loss.append(kv)
        
        # Test each kappa
        for k in kappas:
            r = simulate_kappa(sig, ad, p_tunnel, p_close, sigma, sl_dist,
                               ref_sl, ref_tp, k)
            results[k].append(r)
    
    # ══════════════════════════════════════════════════════════════
    # Aggregate & print results
    # ══════════════════════════════════════════════════════════════
    print("\n" + "═" * 100)
    print("📊 KAPPA SWEEP RESULTS")
    print("═" * 100)
    print(f"{'Kappa':>6} | {'N_touch':>7} | {'Fill%':>6} | {'Win%':>6} | {'Loss%':>6} | {'RR_avg':>7} | {'E[R/sig]':>10} | {'Sharpe':>8}")
    print("─" * 100)
    
    best_ev = -1e9
    best_kappa = None
    comparison = {}
    
    for k in kappas:
        rs = results[k]
        n_total = len(rs)
        if n_total == 0: continue
        
        n_touch = sum(1 for r in rs if r['outcome'] in ('win', 'loss', 'timeout', 'not_filled'))
        n_filled = sum(1 for r in rs if r['outcome'] in ('win', 'loss', 'timeout'))
        n_win = sum(1 for r in rs if r['outcome'] == 'win')
        n_loss = sum(1 for r in rs if r['outcome'] == 'loss')
        
        if n_filled == 0:
            print(f"{k:>6.2f} | {n_touch:>7} | {'—':>6} | {'—':>6} | {'—':>6} | {'—':>7} | {'—':>10} | {'—':>8}")
            continue
        
        fill_rate = n_filled / n_touch if n_touch > 0 else 0
        win_rate = n_win / n_filled
        loss_rate = n_loss / n_filled
        
        # R distribution per signal (unfilled = 0)
        R_arr = []
        for r in rs:
            if r['outcome'] == 'win':
                R_arr.append(r['R_if_win'])
            elif r['outcome'] == 'loss':
                R_arr.append(-1.0)
            else:
                R_arr.append(0.0)
        R_arr = np.array(R_arr)
        
        E_R = float(R_arr.mean())
        sharpe = float(R_arr.mean() / (R_arr.std() + 1e-9))
        rr_avg = np.mean([r['R_if_win'] for r in rs if r['outcome'] == 'win']) if n_win > 0 else 0
        
        comparison[k] = {'E_R': E_R, 'fill_rate': fill_rate, 'win_rate': win_rate}
        
        marker = ""
        if E_R > best_ev:
            best_ev = E_R
            best_kappa = k
            marker = " ★"
        
        print(f"{k:>6.2f} | {n_touch:>7} | {fill_rate*100:>5.1f}% | {win_rate*100:>5.1f}% | {loss_rate*100:>5.1f}% | {rr_avg:>7.2f} | {E_R:>+10.4f} | {sharpe:>+8.3f}{marker}")
    
    print("═" * 100)
    
    # ══════════════════════════════════════════════════════════════
    # Actual reversal depth distribution
    # ══════════════════════════════════════════════════════════════
    print("\n📊 ACTUAL REVERSAL DEPTH (kappa_rev = overshoot below p_tunnel)")
    print("─" * 80)
    
    if kappa_rev_win and kappa_rev_loss:
        kw = np.array(kappa_rev_win)
        kl = np.array(kappa_rev_loss)
        
        print(f"\n  WINS (n={len(kw)}):")
        for p in [10, 25, 50, 75, 90, 95, 99]:
            print(f"    {p:>3}%: {np.percentile(kw, p):>7.3f}σ")
        print(f"    Mean: {kw.mean():.3f}σ | Median: {np.median(kw):.3f}σ | Max: {kw.max():.2f}σ")
        
        print(f"\n  LOSSES (n={len(kl)}):")
        for p in [10, 25, 50, 75, 90, 95, 99]:
            print(f"    {p:>3}%: {np.percentile(kl, p):>7.3f}σ")
        print(f"    Mean: {kl.mean():.3f}σ | Median: {np.median(kl):.3f}σ | Max: {kl.max():.2f}σ")
        
        # Key insight: what % of wins reversed within X sigma?
        print(f"\n  💡 Key insights:")
        for thresh in [0.0, 0.5, 1.0, 2.0, 3.0]:
            pct_wins = (kw <= thresh).mean() * 100
            print(f"    {pct_wins:>5.1f}% of WINS reversed within {thresh:>4.1f}σ of p_tunnel")
            pct_losses = (kl <= thresh).mean() * 100
            print(f"    {pct_losses:>5.1f}% of LOSSES reversed within {thresh:>4.1f}σ of p_tunnel")
    
    # ══════════════════════════════════════════════════════════════
    # Walk-Forward Validation
    # ══════════════════════════════════════════════════════════════
    print("\n" + "═" * 100)
    print("🔬 WALK-FORWARD VALIDATION (70% train, 30% test)")
    print("═" * 100)
    
    # Split signals chronologically
    sig_times = [s.timestamp for s in sigs]
    # Get R arrays per kappa for train/test
    split_idx = int(len(sigs) * 0.7)
    train_sig_ids = set(range(split_idx))
    
    print(f"\n{'Kappa':>6} | {'Train E[R]':>12} | {'Test E[R]':>12} | {'Delta':>10} | Status")
    print("─" * 100)
    
    for k in kappas:
        rs = results[k]
        if not rs: continue
        
        train_R = []
        test_R = []
        for idx, r in enumerate(rs):
            if r is None: continue
            R = 0.0
            if r.get('outcome') == 'win': R = r.get('R_if_win', 0)
            elif r.get('outcome') == 'loss': R = -1.0
            
            if idx < split_idx:
                train_R.append(R)
            else:
                test_R.append(R)
        
        if not train_R or not test_R: continue
        
        train_ev = np.mean(train_R)
        test_ev = np.mean(test_R)
        delta = test_ev - train_ev
        
        # Stability check
        status = "✅ Stable" if abs(delta) < 0.05 and test_ev > 0 else (
                 "⚠️ Degraded" if test_ev < train_ev - 0.05 else "❌ Failed"
        )
        
        print(f"{k:>6.2f} | {train_ev:>+12.4f} | {test_ev:>+12.4f} | {delta:>+10.4f} | {status}")
    
    print("═" * 100)
    
    # ══════════════════════════════════════════════════════════════
    # Final Recommendation
    # ══════════════════════════════════════════════════════════════
    print("\n🎯 FINAL RECOMMENDATION")
    print("═" * 100)
    
    if best_kappa is not None:
        print(f"\n  🏆 Best kappa: {best_kappa:.2f}")
        print(f"  📈 Expected R per signal: {best_ev:+.4f}")
        
        if 0.0 in comparison:
            baseline = comparison[0.0]
            improvement = (best_ev - baseline['E_R']) / max(abs(baseline['E_R']), 1e-9) * 100
            
            print(f"\n  ── Comparison vs Current System (kappa=0) ──")
            print(f"  Fill rate:  {baseline['fill_rate']*100:.1f}% → {comparison[best_kappa]['fill_rate']*100:.1f}%")
            print(f"  Win rate:   {baseline['win_rate']*100:.1f}% → {comparison[best_kappa]['win_rate']*100:.1f}%")
            print(f"  E[R/signal]: {baseline['E_R']:+.4f} → {best_ev:+.4f}")
            print(f"  Improvement: {improvement:+.1f}%")
        
        # Verdict
        print(f"\n  ── Verdict ──")
        if best_kappa == 0.0:
            print(f"  ❌ The inverse kappa idea does NOT improve on the current system.")
            print(f"     → Recommendation: Stick with the current reversal-confirm logic.")
        elif best_ev < comparison.get(0.0, {}).get('E_R', 0):
            print(f"  ❌ Best kappa ({best_kappa}) is STILL worse than current system.")
            print(f"     → Recommendation: Abandon the inverse kappa idea.")
        else:
            print(f"  ✅ kappa={best_kappa:.2f} IMPROVES on the current system.")
            print(f"     → Recommendation: Implement inverse kappa with this value.")
            print(f"     → CLI flag: --pre-entry-kappa {best_kappa:.2f}")
    
    print("═" * 100 + "\n")


if __name__ == "__main__":
    main()
