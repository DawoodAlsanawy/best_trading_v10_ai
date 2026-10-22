#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, glob
import importlib.util
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import pickle
import warnings
warnings.filterwarnings('ignore')

# ══ تحميل البوت كوحدة ══
spec = importlib.util.spec_from_file_location("bot", "trading_2_live4_claude2_v4.py")
bot = importlib.util.module_from_spec(spec)
sys.modules["bot"] = bot
spec.loader.exec_module(bot)

def load_local_data(cache_dir, timeframe, target_symbols):
    main_data, sub_data = {}, {}
    pattern = os.path.join(cache_dir, f"*_{timeframe}.parquet")
    files = glob.glob(pattern)
    sub_tf = bot._get_subbars_tf(timeframe)
    
    for fpath in files:
        basename = os.path.basename(fpath)
        parts = basename.split('_')
        if len(parts) >= 3:
            sym = f"{parts[0]}/{parts[1]}"
        else:
            continue
        if target_symbols and sym not in target_symbols: continue
        try:
            df = pd.read_parquet(fpath)
            df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
            main_data[sym] = df
            sub_path = os.path.join(cache_dir, f"{parts[0]}_{parts[1]}_{sub_tf}_sub.parquet")
            if os.path.exists(sub_path):
                sdf = pd.read_parquet(sub_path)
                sdf.index = sdf.index.tz_localize("UTC") if sdf.index.tz is None else sdf.index.tz_convert("UTC")
                sub_data[sym] = sdf
        except: pass
    return main_data, sub_data

def main():
    bot.CFG.timeframe = '4h'
    bot.CFG.history_days = 730
    bot.CFG.REVERSAL_CONFIRM_ENABLED = True
    bot.CFG.REVERSAL_TOUCH_SUBBARS = 48
    bot.CFG.REVERSAL_BOUNCE_SUBBARS = 48
    bot.CFG.REVERSAL_CONFIRM_MODE = 'sigma_bounce'
    bot.CFG.REVERSAL_CONFIRM_KAPPA = 0.3
    bot.CFG.REVERSAL_FILL_AT = 'target'
    bot.CFG.PO_FIXED_PRICE = False
    bot.CFG.SL_WIDEN_MULT = 1.5
    bot.CFG.PARTIAL_TP_R = 1.2
    bot.CFG.REV_ABORT_KAPPA = 2.0
    bot.CFG.BREAKEVEN_ENABLED = False
    bot.CFG.GAUGE_DISABLE_SELL = False
    bot.CFG.SELL_GAUGE_PCT = 85

    traded_symbols = set()
    with open("trades_log_backtest.jsonl") as f:
        for line in f:
            if not line.strip(): continue
            try:
                r = json.loads(line)
                if not r.get('_meta') and 'symbol' in r: traded_symbols.add(r['symbol'])
            except: pass

    raw, raw_sub = load_local_data("market_data_cache", "4h", traded_symbols)
    assets = {}
    for sym, df in raw.items():
        ad = bot.process_asset(sym, df, current_capital=100, sub_df=raw_sub.get(sym))
        if ad is not None: assets[sym] = ad

    sigs = bot.deduplicate_signals(bot.build_signals(assets, mode='backtest'))
    records = []
    
    for sig in sigs:
        ad = assets[sig.symbol]
        if ad.sub_highs is None: continue
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
            
        touch_main_ci = start_main + (touch_sub_idx // ad.sub_per_main)
        touch_fi = touch_main_ci - ad.feat_start
        if touch_fi < 0 or touch_fi >= len(ad.score): continue

        res = bot._check_reversal_fill_subbars(ad, sig, target0, bot.CFG, start_main, end_main)
        aborted = 1 if res is None else 0

        ema_slope = (ad.ema200[touch_main_ci] - ad.ema200[touch_main_ci-50]) / 50 if touch_main_ci >= 50 else 0
        ema_against = 1.0 if ((sig.action == "BUY" and ema_slope < 0) or (sig.action == "SELL" and ema_slope > 0)) else 0.0
        body = abs(ad.closes[touch_main_ci] - ad.closes[touch_main_ci-1])
        rng = ad.highs[touch_main_ci] - ad.lows[touch_main_ci]
        body_ratio = body / rng if rng > 0 else 0
        vol_z = 0
        if touch_main_ci >= 20:
            vols = ad.volumes[touch_main_ci-20:touch_main_ci+1]
            vol_z = (ad.volumes[touch_main_ci] - np.mean(vols)) / (np.std(vols) + 1e-9)
        range_pos = 0.5
        if touch_main_ci >= 20:
            lo = np.min(ad.lows[touch_main_ci-20:touch_main_ci+1])
            hi = np.max(ad.highs[touch_main_ci-20:touch_main_ci+1])
            range_pos = (ad.closes[touch_main_ci] - lo) / (hi - lo + 1e-9)

        records.append({
            'aborted': aborted,
            'ema_slope_against': ema_against,
            'gauge_force': float(ad.gauge_force[touch_fi]),
            'friction': float(ad.friction[touch_fi]),
            'E_therm': float(ad.E_therm[touch_fi]),
            'body_ratio': float(body_ratio),
            'vol_z': float(vol_z),
            'range_pos': float(range_pos),
            'dist_from_ema': float((ad.closes[touch_main_ci] - ad.ema200[touch_main_ci]) / ad.ema200[touch_main_ci]),
            'score': float(ad.score[touch_fi])
        })

    df = pd.DataFrame(records)
    features = ['ema_slope_against', 'gauge_force', 'friction', 'E_therm', 'body_ratio', 'vol_z', 'range_pos', 'dist_from_ema', 'score']
    X = df[features]
    y = df['aborted']

    print("⏳ تدريب نموذج Random Forest للتنبؤ بالفشل...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, class_weight='balanced')
    clf.fit(X, y)

    # الحصول على احتمالية الفشل لكل صفقة
    probs = clf.predict_proba(X)[:, 1]

    # إيجاد أقصى احتمال فشل لصفقة *رابحة*
    max_prob_win = probs[y == 0].max()
    print(f"\n🔍 أقصى احتمال فشل لصفقة رابحة: {max_prob_win*100:.2f}%")

    # العتبة الذهبية: أي احتمال فشل أعلى من هذا الرقم سيُعتبر فشلاً مؤكداً (يضمن 0 صفقات رابحة مقتولة)
    threshold = max_prob_win + 1e-5
    caught_fails = (probs[y == 1] > threshold).sum()
    total_fails = (y == 1).sum()
    killed_wins = (probs[y == 0] > threshold).sum()

    print(f"🎯 العتبة المثالية: {threshold:.4f}")
    print(f"✅ تم التقاط {caught_fails} صفقة فاشلة من أصل {total_fails} (نسبة {caught_fails/total_fails*100:.1f}%)")
    print(f"❌ عدد الصفقات الرابحة المقتولة: {killed_wins} (يجب أن يكون 0)")

    # حفظ النموذج
    with open("touch_filter_model.pkl", "wb") as f:
        pickle.dump({'model': clf, 'threshold': threshold, 'features': features}, f)
    print("💾 تم حفظ النموذج في touch_filter_model.pkl")

if __name__ == "__main__":
    main()
