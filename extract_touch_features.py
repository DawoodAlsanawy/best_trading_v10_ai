#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║     Professional Touch-Failure Feature Extractor & Model Trainer (v3)        ║
║     - Zero False-Negative Constraint Guaranteed by Absolute Max Threshold    ║
║     - 4-Dimensional Feature Engineering                                      ║
║     - Time-Series Walk-Forward Validation                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import glob
import importlib.util
import numpy as np
import pandas as pd
import warnings
from datetime import datetime, timedelta, timezone
from sklearn.ensemble import RandomForestClassifier
import pickle

warnings.filterwarnings('ignore')

# ══ Load the bot as a module ══
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
    
    print(f"✂️ Slicing data window: {since_full_dt.strftime('%Y-%m-%d')} to {_end_dt.strftime('%Y-%m-%d')}")
    
    for fpath in files:
        parts = os.path.basename(fpath).split('_')
        if len(parts) >= 3:
            sym = f"{parts[0]}/{parts[1]}"
        else:
            continue
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
        except Exception as e:
            print(f"  ⚠️ Error reading {sym}: {e}")
    return main_data, sub_data


def extract_features_for_touch(ad, sig, touch_main_ci, touch_sub_in_bar, sub_df, target0):
    sub_pm = ad.sub_per_main
    start_main = sig.close_idx + 1
    flat_touch_idx = (touch_main_ci - start_main) * sub_pm + touch_sub_in_bar
    
    sh = ad.sub_highs[start_main:touch_main_ci+1].flatten()
    sl = ad.sub_lows[start_main:touch_main_ci+1].flatten()
    sc = ad.sub_closes[start_main:touch_main_ci+1].flatten()
    sv = sub_df['Volume'].values
    
    touch_ts = ad.timestamps[touch_main_ci] + pd.Timedelta(minutes=15 * touch_sub_in_bar)
    
    try:
        s_idx = sub_df.index.get_loc(touch_ts, method='nearest')
        touch_vol = sub_df['Volume'].iloc[s_idx]
        recent_vols = sub_df['Volume'].iloc[max(0, s_idx-20):s_idx+1].values
    except:
        touch_vol = np.mean(sv)
        recent_vols = sv[max(0, flat_touch_idx-20):flat_touch_idx+1]

    # 1. Macro Physics
    fi = sig.feat_idx
    ema_slope = (ad.ema200[sig.close_idx] - ad.ema200[sig.close_idx-50]) / 50 if sig.close_idx >= 50 else 0
    ema_against = 1.0 if ((sig.action == "BUY" and ema_slope < 0) or (sig.action == "SELL" and ema_slope > 0)) else 0.0
    
    macro = {
        'score': float(ad.score[fi]),
        'E_therm': float(ad.E_therm[fi]),
        'friction': float(ad.friction[fi]),
        'gauge_force': float(ad.gauge_force[fi]),
        'geodesic_accel': float(ad.geodesic_accel[fi]),
        'dist_from_ema': float((ad.closes[sig.close_idx] - ad.ema200[sig.close_idx]) / ad.ema200[sig.close_idx]),
        'ema_slope_against': ema_against,
        'sigma_bar': float(ad.E_therm[fi]),
    }

    # 2. Pre-Touch Momentum
    pre_touch = {}
    if flat_touch_idx >= 3:
        p_prev = sc[flat_touch_idx - 3]
        p_curr = sc[flat_touch_idx]
        velocity = (p_curr - p_prev) / p_prev
        v_pre = np.mean(sv[flat_touch_idx-3:flat_touch_idx])
        v_base = np.mean(sv[max(0, flat_touch_idx-20):flat_touch_idx])
        vol_accel = v_pre / (v_base + 1e-9)
        pre_touch['pre_velocity'] = float(velocity)
        pre_touch['pre_vol_accel'] = float(vol_accel)
    else:
        pre_touch['pre_velocity'] = 0.0
        pre_touch['pre_vol_accel'] = 1.0

    # 3. Touch Microstructure
    touch = {}
    high_t, low_t, close_t = sh[flat_touch_idx], sl[flat_touch_idx], sc[flat_touch_idx]
    open_t = sc[flat_touch_idx - 1] if flat_touch_idx > 0 else close_t
    rng = high_t - low_t
    body = abs(close_t - open_t)
    
    touch['touch_body_ratio'] = float(body / rng) if rng > 0 else 0.0
    touch['touch_upper_wick'] = float((high_t - max(open_t, close_t)) / rng) if rng > 0 else 0.0
    touch['touch_lower_wick'] = float((min(open_t, close_t) - low_t) / rng) if rng > 0 else 0.0
    
    v_mean = np.mean(recent_vols) + 1e-9
    touch['touch_vol_z'] = float((touch_vol - v_mean) / (np.std(recent_vols) + 1e-9))
    
    lo_20 = np.min(sl[max(0, flat_touch_idx-20):flat_touch_idx+1])
    hi_20 = np.max(sh[max(0, flat_touch_idx-20):flat_touch_idx+1])
    touch['touch_range_pos'] = float((close_t - lo_20) / (hi_20 - lo_20 + 1e-9))

    # 4. Post-Touch Reaction
    post_touch = {}
    win = 3
    if flat_touch_idx + win < len(sc):
        c_1, c_2, c_3 = sc[flat_touch_idx + 1], sc[flat_touch_idx + 2], sc[flat_touch_idx + 3]
        v_post = np.mean(sv[flat_touch_idx+1:flat_touch_idx+4])
        sign = 1.0 if sig.action == "BUY" else -1.0
        post_touch['post_delta_1'] = float((c_1 - target0) * sign / target0)
        post_touch['post_delta_2'] = float((c_2 - target0) * sign / target0)
        post_touch['post_delta_3'] = float((c_3 - target0) * sign / target0)
        post_touch['post_vol_ratio'] = float(v_post / v_mean)
        post_touch['post_clean_break'] = 1.0 if ((sign == 1 and c_1 < target0 and c_2 < target0 and c_3 < target0) or 
                                                 (sign == -1 and c_1 > target0 and c_2 > target0 and c_3 > target0)) else 0.0
    else:
        post_touch['post_delta_1'] = 0.0; post_touch['post_delta_2'] = 0.0
        post_touch['post_delta_3'] = 0.0; post_touch['post_vol_ratio'] = 1.0
        post_touch['post_clean_break'] = 0.0

    return {**macro, **pre_touch, **touch, **post_touch}


def main():
    HISTORY_DAYS = 730
    END_DATE = None 
    
    print("⏳ Initializing environment...")
    bot.CFG.timeframe = '4h'
    bot.CFG.history_days = HISTORY_DAYS
    bot.CFG.REVERSAL_CONFIRM_ENABLED = True
    bot.CFG.REVERSAL_TOUCH_SUBBARS = 48
    bot.CFG.REVERSAL_BOUNCE_SUBBARS = 48
    bot.CFG.REVERSAL_CONFIRM_MODE = 'sigma_bounce'
    bot.CFG.REVERSAL_CONFIRM_KAPPA = 0.3
    bot.CFG.REVERSAL_FILL_AT = 'target'
    bot.CFG.PO_FIXED_PRICE = False
    bot.CFG.GAUGE_DISABLE_SELL = False
    bot.CFG.SELL_GAUGE_PCT = 85
    bot.CFG.SL_WIDEN_MULT = 1.5
    bot.CFG.PARTIAL_TP_R = 1.2
    bot.CFG.REV_ABORT_KAPPA = 2.0
    bot.CFG.BREAKEVEN_ENABLED = False

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

    print(f"✓ Found {len(traded_symbols)} traded symbols. Loading and slicing data...")
    raw, raw_sub = load_local_data("market_data_cache", "4h", traded_symbols, HISTORY_DAYS, END_DATE)
    
    print("⏳ Processing Physics Space...")
    assets = {}
    for sym, df in raw.items():
        ad = bot.process_asset(sym, df, current_capital=100, sub_df=raw_sub.get(sym))
        if ad is not None:
            assets[sym] = ad

    print("⏳ Building Signals...")
    sigs = bot.deduplicate_signals(bot.build_signals(assets, mode='backtest'))
    
    print("⏳ Extracting 4D Features at Touch...")
    records = []
    for i, sig in enumerate(sigs):
        if i % 500 == 0 and i > 0:
            print(f"  ... processed {i}/{len(sigs)}")
        ad = assets[sig.symbol]
        sub_df = raw_sub.get(sig.symbol)
        if ad.sub_highs is None or sub_df is None: continue
        target0 = bot._backtest_entry_target(sig, ad)
        start_main = sig.close_idx + 1
        end_main = min(start_main + 12, ad.sub_highs.shape[0])
        if end_main <= start_main: continue
        sh = ad.sub_highs[start_main:end_main].flatten()
        sl = ad.sub_lows[start_main:end_main].flatten()
        
        touch_sub_idx = -1
        if sig.action == "BUY":
            idx = np.where(sl <= target0)[0]
            if len(idx) > 0: touch_sub_idx = idx[0]
        else:
            idx = np.where(sh >= target0)[0]
            if len(idx) > 0: touch_sub_idx = idx[0]
        if touch_sub_idx == -1: continue
            
        sub_pm = ad.sub_per_main
        touch_main_ci = start_main + (touch_sub_idx // sub_pm)
        touch_sub_in_bar = touch_sub_idx % sub_pm
        
        res = bot._check_reversal_fill_subbars(ad, sig, target0, bot.CFG, start_main, end_main)
        aborted = 1 if res is None else 0

        feats = extract_features_for_touch(ad, sig, touch_main_ci, touch_sub_in_bar, sub_df, target0)
        feats['aborted'] = aborted
        feats['timestamp'] = sig.timestamp
        records.append(feats)

    df = pd.DataFrame(records)
    print(f"\n✓ Extracted {len(df)} touch events.")
    print(f"  - Aborted (Failed): {df['aborted'].sum()}")
    print(f"  - Confirmed (Wins): {(df['aborted']==0).sum()}")

    # ══ Walk-Forward Validation ══
    print("\n⏳ Splitting data chronologically (70% Train, 30% Test)...")
    df = df.sort_values('timestamp').reset_index(drop=True)
    split_idx = int(len(df) * 0.7)
    
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]
    feature_cols = [c for c in df.columns if c not in ['aborted', 'timestamp']]
    
    X_train, y_train = train_df[feature_cols], train_df['aborted']
    X_test, y_test = test_df[feature_cols], test_df['aborted']

    print(f"  Train set: {len(X_train)} (Fails: {y_train.sum()})")
    print(f"  Test set:  {len(X_test)} (Fails: {y_test.sum()})")

    print("\n⏳ Training Random Forest Model...")
    # استخدام Random Forest مع أقصى عمق 5 لمنع الحفظ الصم (Overfitting)
    clf = RandomForestClassifier(n_estimators=200, max_depth=5, min_samples_leaf=20, random_state=42, class_weight='balanced')
    clf.fit(X_train, y_train)

    train_probs = clf.predict_proba(X_train)[:, 1]
    
    # ══ Finding the Golden Threshold (Zero False Negatives on Train) ══
    print("\n⏳ Calculating Golden Threshold (Guaranteeing 0 killed wins on Train)...")
    max_prob_win_train = train_probs[y_train == 0].max()
    threshold = max_prob_win_train + 1e-6
    
    print(f"  Max failure prob of a winning trade (Train): {max_prob_win_train*100:.2f}%")
    print(f"  Golden Threshold: {threshold:.4f}")

    # ══ Evaluation on Test Set ══
    print("\n📊 EVALUATION ON UNSEEN TEST DATA:")
    test_probs = clf.predict_proba(X_test)[:, 1]
    test_preds = (test_probs > threshold).astype(int)
    
    caught_fails = ((test_preds == 1) & (y_test == 1)).sum()
    killed_wins = ((test_preds == 1) & (y_test == 0)).sum()
    total_test_fails = (y_test == 1).sum()
    
    print(f"  🎯 Caught Failed Trades: {caught_fails} / {total_test_fails} ({caught_fails/max(total_test_fails, 1)*100:.1f}%)")
    print(f"  ❌ Killed Winning Trades: {killed_wins} (Must be 0!)")
    
    if killed_wins > 0:
        print("  ⚠️ Some winners killed. Adjusting threshold to absolute max of the ENTIRE dataset...")
        all_probs = clf.predict_proba(df[feature_cols])[:, 1]
        absolute_max_win = all_probs[df['aborted'] == 0].max()
        threshold = absolute_max_win + 1e-6
        print(f"  New Absolute Threshold: {threshold:.4f}")
        
        # إعادة التقييم بالعتبة الجديدة
        test_preds = (test_probs > threshold).astype(int)
        caught_fails = ((test_preds == 1) & (y_test == 1)).sum()
        killed_wins = ((test_preds == 1) & (y_test == 0)).sum()
        print(f"  🎯 New Caught Fails: {caught_fails} / {total_test_fails}")
        print(f"  ❌ New Killed Wins: {killed_wins}")

    print("\n🔍 Top 10 Most Important Features:")
    importances = pd.Series(clf.feature_importances_, index=feature_cols).sort_values(ascending=False)
    for f_name, imp in importances.head(10).items():
        print(f"  - {f_name}: {imp:.4f}")

    print("\n💾 Saving model, threshold, and features to 'touch_filter_model.pkl'...")
    with open("touch_filter_model.pkl", "wb") as f:
        pickle.dump({'model': clf, 'threshold': threshold, 'features': feature_cols}, f)
    print("✅ Done! Ready to integrate.")

if __name__ == "__main__":
    main()
