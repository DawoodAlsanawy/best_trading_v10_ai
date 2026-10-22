#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Smart Abort Analyzer (Depth-Based) - Phase 2                                ║
║                                                                              ║
║  Idea: Enter at p_tunnel (as usual), but if price goes AGAINST us by         ║
║        X * sigma_bar, ABORT immediately.                                     ║
║                                                                              ║
║  Tests: X = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]                                   ║
║  Compares: Baseline (no abort) vs Smart Abort at each depth.                 ║
║                                                                              ║
║  Features:                                                                   ║
║    - Accurate Partial TP simulation (PARTIAL_TP_R = 1.2)                     ║
║    - Correct event ordering (touch → abort / SL / TP)                        ║
║    - Precise R-multiple calculation                                          ║
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


def simulate_trade(sig, ad, p_tunnel, sigma, sl_dist, tp_dist, abort_mult):
    """
    Simulates ONE trade with optional Smart Abort.
    Returns a dict with outcome and R-multiple.
    """
    sign = 1.0 if sig.action == "BUY" else -1.0
    
    # Prices
    sl_price = p_tunnel - sign * sl_dist
    tp_price = p_tunnel + sign * tp_dist
    partial_price = p_tunnel + sign * sl_dist * bot.CFG.PARTIAL_TP_R
    
    # Abort threshold (only if abort_mult is not None)
    abort_price = None
    if abort_mult is not None:
        abort_price = p_tunnel - sign * abort_mult * sigma * p_tunnel
        
    # Sub-bar arrays
    start = sig.close_idx + 1
    end = min(start + 12, ad.sub_highs.shape[0])
    sh = ad.sub_highs[start:end].flatten()
    sl_arr = ad.sub_lows[start:end].flatten()
    
    # Find touch (price hits p_tunnel)
    touch = -1
    for i in range(len(sh)):
        if sign > 0 and sl_arr[i] <= p_tunnel: touch = i; break
        if sign < 0 and sh[i] >= p_tunnel: touch = i; break
    if touch == -1:
        return {'outcome': 'no_touch', 'R': 0.0}
    
    # Simulate from touch onward
    partial_taken = False
    position_remaining = 1.0 # 1.0 = full position
    
    for i in range(touch, len(sh)):
        hi = sh[i]
        lo = sl_arr[i]
        
        # ── CHECK PARTIAL TP FIRST (it's a "good" event) ──
        if not partial_taken:
            if sign > 0 and hi >= partial_price:
                partial_taken = True
                position_remaining -= 0.5  # Close 50%
            elif sign < 0 and lo <= partial_price:
                partial_taken = True
                position_remaining -= 0.5
        
        # ── CHECK EXITS ──
        # For BUY: SL and Abort are below, TP is above.
        # For SELL: SL and Abort are above, TP is below.
        
        # Check SL (the worst outcome)
        sl_hit = (sign > 0 and lo <= sl_price) or (sign < 0 and hi >= sl_price)
        
        # Check Abort (only if not already hit SL, and abort is enabled)
        abort_hit = False
        if abort_price is not None:
            abort_hit = (sign > 0 and lo <= abort_price) or (sign < 0 and hi >= abort_price)
        
        # Check TP (the best outcome)
        tp_hit = (sign > 0 and hi >= tp_price) or (sign < 0 and lo <= tp_price)
        
        # ── EVENT ORDERING ──
        # If both SL and Abort are hit in the same bar, we assume SL hit first (pessimistic)
        # because SL is further from p_tunnel, so price must have passed Abort to reach SL.
        if sl_hit:
            # Full SL triggered. But wait - if abort was closer, we should have aborted.
            # To be realistic: if the bar's low went below SL, we need to know if it 
            # also went below Abort BEFORE hitting SL. Since we only have OHLC, 
            # we assume the worst: if abort_price is above sl_price (for BUY), 
            # then abort triggered first.
            if abort_price is not None and ((sign > 0 and abort_price > sl_price) or (sign < 0 and abort_price < sl_price)):
                # Abort hit first
                return _finalize_abort(partial_taken, abort_mult, sigma, sl_dist)
            else:
                return _finalize_sl(partial_taken)
        
        if abort_hit and not tp_hit:
            return _finalize_abort(partial_taken, abort_mult, sigma, sl_dist)
        
        if tp_hit:
            return _finalize_tp(partial_taken, tp_dist, sl_dist)
    
    # Timeout (no SL, no TP, no Abort in 12 bars)
    return _finalize_timeout(partial_taken)


def _finalize_sl(partial_taken):
    """Full SL hit. If partial was taken, we have mixed R."""
    if partial_taken:
        # 50% at +PARTIAL_TP_R (e.g. +1.2R), 50% at -1.0R
        R = 0.5 * bot.CFG.PARTIAL_TP_R + 0.5 * (-1.0)
    else:
        R = -1.0
    return {'outcome': 'sl', 'R': R}


def _finalize_abort(partial_taken, abort_mult, sigma, sl_dist):
    """Abort triggered. Loss is proportional to abort depth."""
    # Loss fraction in price = abort_mult * sigma
    # Loss in R = (abort_mult * sigma) / (sl_dist / p_tunnel)
    # But sl_dist is in price, and abort is in sigma.
    # Simpler: loss_R = abort_mult * sigma * p_tunnel / sl_dist
    # We need sl_dist to be in the same unit.
    # Actually: sl_dist is absolute price distance.
    # abort_price_distance = abort_mult * sigma * p_tunnel
    # loss_R = abort_price_distance / sl_dist
    # We don't have p_tunnel here, so we pass sigma (which is fraction) and use it.
    # Wait, we do have it in the caller. Let me fix by passing explicitly.
    pass


def _finalize_sl_v2(partial_taken, R_loss):
    if partial_taken:
        R = 0.5 * bot.CFG.PARTIAL_TP_R + 0.5 * (-R_loss)
    else:
        R = -R_loss
    return {'outcome': 'abort', 'R': R}


def _finalize_tp(partial_taken, tp_dist, sl_dist):
    """TP hit. R depends on whether partial was taken."""
    full_R = tp_dist / sl_dist # Typically 2.0
    if partial_taken:
        # 50% at +PARTIAL_TP_R, 50% at +full_R
        R = 0.5 * bot.CFG.PARTIAL_TP_R + 0.5 * full_R
    else:
        R = full_R
    return {'outcome': 'win', 'R': R}


def _finalize_timeout(partial_taken):
    """Timeout with no clear resolution."""
    if partial_taken:
        # 50% at +PARTIAL_TP_R, 50% at 0
        R = 0.5 * bot.CFG.PARTIAL_TP_R + 0.5 * 0
    else:
        R = 0.0
    return {'outcome': 'timeout', 'R': R}


def simulate_trade_corrected(sig, ad, p_tunnel, sigma, sl_dist, tp_dist, abort_mult):
    """Corrected version with proper R calculation for abort."""
    sign = 1.0 if sig.action == "BUY" else -1.0
    
    sl_price = p_tunnel - sign * sl_dist
    tp_price = p_tunnel + sign * tp_dist
    partial_price = p_tunnel + sign * sl_dist * bot.CFG.PARTIAL_TP_R
    
    abort_price = None
    abort_loss_R = 0.0  # Loss in R units if abort triggers
    if abort_mult is not None:
        abort_dist = abort_mult * sigma * p_tunnel
        abort_price = p_tunnel - sign * abort_dist
        abort_loss_R = abort_dist / sl_dist  # Convert to R units
    
    start = sig.close_idx + 1
    end = min(start + 12, ad.sub_highs.shape[0])
    sh = ad.sub_highs[start:end].flatten()
    sl_arr = ad.sub_lows[start:end].flatten()
    
    # Find touch
    touch = -1
    for i in range(len(sh)):
        if sign > 0 and sl_arr[i] <= p_tunnel: touch = i; break
        if sign < 0 and sh[i] >= p_tunnel: touch = i; break
    if touch == -1:
        return {'outcome': 'no_touch', 'R': 0.0}
    
    partial_taken = False
    
    for i in range(touch, len(sh)):
        hi = sh[i]
        lo = sl_arr[i]
        
        # Partial TP
        if not partial_taken:
            if sign > 0 and hi >= partial_price: partial_taken = True
            elif sign < 0 and lo <= partial_price: partial_taken = True
        
        # SL check
        sl_hit = (sign > 0 and lo <= sl_price) or (sign < 0 and hi >= sl_price)
        # Abort check
        abort_hit = abort_price is not None and ((sign > 0 and lo <= abort_price) or (sign < 0 and hi >= abort_price))
        # TP check
        tp_hit = (sign > 0 and hi >= tp_price) or (sign < 0 and lo <= tp_price)
        
        # Order of events in the same bar (pessimistic: SL first if both hit)
        if sl_hit:
            if abort_hit and ((sign > 0 and abort_price > sl_price) or (sign < 0 and abort_price < sl_price)):
                # Abort was triggered before SL
                if partial_taken:
                    return {'outcome': 'abort', 'R': 0.5 * bot.CFG.PARTIAL_TP_R + 0.5 * (-abort_loss_R)}
                return {'outcome': 'abort', 'R': -abort_loss_R}
            # SL directly
            if partial_taken:
                return {'outcome': 'sl', 'R': 0.5 * bot.CFG.PARTIAL_TP_R + 0.5 * (-1.0)}
            return {'outcome': 'sl', 'R': -1.0}
        
        if abort_hit and not tp_hit:
            if partial_taken:
                return {'outcome': 'abort', 'R': 0.5 * bot.CFG.PARTIAL_TP_R + 0.5 * (-abort_loss_R)}
            return {'outcome': 'abort', 'R': -abort_loss_R}
        
        if tp_hit:
            full_R = tp_dist / sl_dist
            if partial_taken:
                return {'outcome': 'win', 'R': 0.5 * bot.CFG.PARTIAL_TP_R + 0.5 * full_R}
            return {'outcome': 'win', 'R': full_R}
    
    # Timeout
    if partial_taken:
        return {'outcome': 'timeout', 'R': 0.5 * bot.CFG.PARTIAL_TP_R}
    return {'outcome': 'timeout', 'R': 0.0}


def main():
    HISTORY_DAYS = 730
    
    print("⏳ Configuring bot to match backtest...")
    bot.CFG.timeframe = '4h'
    bot.CFG.history_days = HISTORY_DAYS
    bot.CFG.GAUGE_DISABLE_SELL = False
    bot.CFG.SELL_GAUGE_PCT = 85
    bot.CFG.SL_WIDEN_MULT = 1.5
    bot.CFG.PARTIAL_TP_R = 1.2
    bot.CFG.PARTIAL_TP_ENABLED = True
    bot.CFG.TP_MULT = 2.0
    bot.CFG.PO_FIXED_PRICE = False
    bot.CFG.MIN_SCORE = 4
    
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
    print(f"✓ Found {len(traded_symbols)} symbols.")
    
    raw, raw_sub = load_local_data("market_data_cache", "4h", traded_symbols, HISTORY_DAYS)
    
    print("⏳ Processing Physics State...")
    assets = {}
    for sym, df in raw.items():
        ad = bot.process_asset(sym, df, current_capital=100, sub_df=raw_sub.get(sym))
        if ad is not None: assets[sym] = ad
    
    print("⏳ Building Signals...")
    sigs = bot.deduplicate_signals(bot.build_signals(assets, mode='backtest'))
    print(f"✓ Generated {len(sigs)} signals.")
    
    # ══════════════════════════════════════════════════════════════
    # Test Abort Depths
    # ══════════════════════════════════════════════════════════════
    abort_mult_list = [None, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    # None = baseline (no abort, current bot behavior)
    
    results = {m: [] for m in abort_mult_list}
    
    print("\n⏳ Running simulation with all abort depths...")
    for si, sig in enumerate(sigs):
        if si % 1000 == 0 and si > 0:
            print(f"   ... {si}/{len(sigs)}")
        
        ad = assets[sig.symbol]
        if ad.sub_highs is None or ad.sub_lows is None: continue
        
        p_tunnel = float(bot._backtest_entry_target(sig, ad))
        sigma = float(ad.E_therm[sig.feat_idx])
        sl_dist = abs(p_tunnel - float(sig.sl))
        tp_dist = abs(float(sig.tp1) - p_tunnel)
        
        if sl_dist <= 1e-9 or sigma <= 1e-6 or tp_dist <= 1e-9: continue
        
        for m in abort_mult_list:
            r = simulate_trade_corrected(sig, ad, p_tunnel, sigma, sl_dist, tp_dist, m)
            results[m].append(r)
    
    # ══════════════════════════════════════════════════════════════
    # Report
    # ══════════════════════════════════════════════════════════════
    print("\n" + "═" * 110)
    print("📊 SMART ABORT AT DEPTH X * sigma_bar")
    print("═" * 110)
    print(f"{'Abort X':>8} | {'N_total':>8} | {'N_fill':>7} | {'Win%':>6} | {'SL%':>6} | {'Abort%':>7} | {'Timeout%':>9} | {'E[R/sig]':>10} | {'Delta_vs_base':>13}")
    print("─" * 110)
    
    baseline_ev = None
    comparison = {}
    
    for m in abort_mult_list:
        rs = results[m]
        n_total = len(rs)
        if n_total == 0: continue
        
        n_fill = sum(1 for r in rs if r['outcome'] in ('win', 'sl', 'abort', 'timeout'))
        n_win = sum(1 for r in rs if r['outcome'] == 'win')
        n_sl = sum(1 for r in rs if r['outcome'] == 'sl')
        n_abort = sum(1 for r in rs if r['outcome'] == 'abort')
        n_timeout = sum(1 for r in rs if r['outcome'] == 'timeout')
        
        if n_fill == 0: continue
        
        R_arr = np.array([r['R'] for r in rs])
        E_R = float(R_arr.mean())
        
        if m is None:
            baseline_ev = E_R
        
        comparison[m] = {
            'E_R': E_R,
            'win_rate': n_win / n_fill,
            'sl_rate': n_sl / n_fill,
            'abort_rate': n_abort / n_fill,
            'n_fill': n_fill,
        }
        
        delta = ""
        if baseline_ev is not None:
            d = E_R - baseline_ev
            delta = f"{d:+.4f}" + (" ★" if d > 0.005 else "")
        
        label = "None" if m is None else f"{m:.2f}σ"
        print(f"{label:>8} | {n_total:>8} | {n_fill:>7} | "
              f"{n_win/n_fill*100:>5.1f}% | {n_sl/n_fill*100:>5.1f}% | "
              f"{n_abort/n_fill*100:>6.1f}% | {n_timeout/n_fill*100:>8.1f}% | "
              f"{E_R:>+10.4f} | {delta:>13}")
    
    print("═" * 110)
    
    # ══════════════════════════════════════════════════════════════
    # Find Best Abort
    # ══════════════════════════════════════════════════════════════
    best_m = None
    best_ev = -1e9
    for m, c in comparison.items():
        if c['E_R'] > best_ev:
            best_ev = c['E_R']
            best_m = m
    
    print("\n🎯 FINAL RECOMMENDATION")
    print("═" * 110)
    
    if best_m is None or baseline_ev is None:
        print("  ❌ No valid data.")
        return
    
    if best_m is None or best_ev <= baseline_ev:
        print(f"  ❌ Smart Abort does NOT improve over baseline.")
        print(f"     Baseline E[R/sig] = {baseline_ev:+.4f}")
        print(f"     → Recommendation: Keep the current bot as-is (no abort).")
    else:
        label = "None" if best_m is None else f"{best_m:.2f}σ"
        print(f"  🏆 Best Abort Depth: X = {label}")
        print(f"  📈 E[R/sig]: {baseline_ev:+.4f} → {best_ev:+.4f} ({((best_ev-baseline_ev)/abs(baseline_ev))*100:+.1f}%)")
        
        if baseline_ev > 0:
            improvement = (best_ev - baseline_ev) / baseline_ev * 100
            print(f"  ✅ Improvement: {improvement:+.1f}%")
        
        print(f"\n  ── Comparison vs Baseline (No Abort) ──")
        b = comparison[None]
        best_c = comparison[best_m]
        print(f"  Win rate:   {b['win_rate']*100:.1f}% → {best_c['win_rate']*100:.1f}%")
        print(f"  SL rate:    {b['sl_rate']*100:.1f}% → {best_c['sl_rate']*100:.1f}%")
        print(f"  Abort rate: 0.0% → {best_c['abort_rate']*100:.1f}%")
        
        print(f"\n  → CLI flag to apply: --rev-abort-kappa {best_m:.2f}")
    
    print("═" * 110 + "\n")


if __name__ == "__main__":
    main()
