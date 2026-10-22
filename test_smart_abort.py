#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, glob
import importlib.util
import numpy as np
import pandas as pd
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
        parts = os.path.basename(fpath).split('_')
        if len(parts) >= 3: sym = f"{parts[0]}/{parts[1]}"
        else: continue
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
    # ضبط إعدادات البوت
    bot.CFG.timeframe = '4h'
    bot.CFG.history_days = 730
    bot.CFG.REVERSAL_CONFIRM_ENABLED = True
    bot.CFG.REVERSAL_TOUCH_SUBBARS = 48
    bot.CFG.REVERSAL_BOUNCE_SUBBARS = 48
    bot.CFG.REVERSAL_CONFIRM_MODE = 'sigma_bounce'
    bot.CFG.REVERSAL_CONFIRM_KAPPA = 0.3
    bot.CFG.REVERSAL_FILL_AT = 'target'
    bot.CFG.PO_FIXED_PRICE = False
    bot.CFG.GAUGE_DISABLE_SELL = False
    bot.CFG.SELL_GAUGE_PCT = 85
    
    traded_symbols = set()
    with open("trades_log_backtest.jsonl") as f:
        for line in f:
            if line.strip() and not json.loads(line).get('_meta'):
                traded_symbols.add(json.loads(line)['symbol'])

    raw, raw_sub = load_local_data("market_data_cache", "4h", traded_symbols)
    assets = {}
    for sym, df in raw.items():
        ad = bot.process_asset(sym, df, current_capital=100, sub_df=raw_sub.get(sym))
        if ad is not None: assets[sym] = ad

    sigs = bot.deduplicate_signals(bot.build_signals(assets, mode='backtest'))
    
    caught_early_fails = 0
    total_fails = 0
    killed_wins = 0
    total_wins = 0
    
    print("⏳ محاكاة الإيقاف الذكي المبكر (Smart Early Abort)...")
    
    for sig in sigs:
        ad = assets[sig.symbol]
        if ad.sub_highs is None: continue
        target0 = bot._backtest_entry_target(sig, ad)
        
        start_main = sig.close_idx + 1
        end_main = min(start_main + 12, ad.sub_highs.shape[0])
        if end_main <= start_main: continue
        
        sh = ad.sub_highs[start_main:end_main].flatten()
        sl = ad.sub_lows[start_main:end_main].flatten()
        sc = ad.sub_closes[start_main:end_main].flatten()
        sv = ad.sub_volumes[start_main:end_main].flatten() if hasattr(ad, 'sub_volumes') and ad.sub_volumes is not None else np.ones_like(sh)
        
        touch_sub_idx = -1
        if sig.action == "BUY":
            idx = np.where(sl <= target0)[0]
            if len(idx) > 0: touch_sub_idx = idx[0]
        else:
            idx = np.where(sh >= target0)[0]
            if len(idx) > 0: touch_sub_idx = idx[0]
            
        if touch_sub_idx == -1: continue

        # 1. النتيجة الحقيقية (بعد 48 شمعة)
        res = bot._check_reversal_fill_subbars(ad, sig, target0, bot.CFG, start_main, end_main)
        aborted = 1 if res is None else 0
        
        if aborted: total_fails += 1
        else: total_wins += 1

        # 2. محاكاة الإيقاف الذكي: نفحص أول شمعتين فرعيتين بعد اللمس
        smart_abort = False
        if touch_sub_idx + 2 < len(sc):
            # الشمعة الفرعية الأولى والثانية
            c1 = sc[touch_sub_idx + 1]
            c2 = sc[touch_sub_idx + 2]
            v1 = sv[touch_sub_idx + 1]
            v2 = sv[touch_sub_idx + 2]
            
            # حجم التداول المتوسط في آخر 20 شمعة
            avg_v = np.mean(sv[max(0, touch_sub_idx-20):touch_sub_idx+1])
            
            if sig.action == "BUY":
                # إذا أغلقت الشمعة الثانية تحت الهدف بجسم كبير وحجم تداول عالي
                if c2 < target0 and (target0 - c2) > (ad.E_therm[sig.feat_idx] * target0 * 0.5) and v2 > avg_v * 1.5:
                    smart_abort = True
            else:
                if c2 > target0 and (c2 - target0) > (ad.E_therm[sig.feat_idx] * target0 * 0.5) and v2 > avg_v * 1.5:
                    smart_abort = True

        # 3. التقييم
        if smart_abort:
            if aborted: caught_early_fails += 1
            else: killed_wins += 1

    print("\n" + "="*50)
    print("📊 نتائج الإيقاف الذكي المبكر (Smart Early Abort):")
    print(f"إجمالي الصفقات الفاشلة: {total_fails}")
    print(f"إجمالي الصفقات الرابحة: {total_wins}")
    print("-" * 50)
    print(f"🎯 الصفقات الفاشلة التي تم إيقافها مبكراً: {caught_early_fails} (نسبة {caught_early_fails/max(total_fails,1)*100:.1f}%)")
    print(f"❌ الصفقات الرابحة التي تم قتلها بالخطأ: {killed_wins} (نسبة {killed_wins/max(total_wins,1)*100:.1f}%)")
    print("="*50)
    
    if killed_wins == 0:
        print("✅ ممتاز! هذه القاعدة تقضي على الخسائر دون المساس بأي صفقة رابحة.")
    else:
        print("⚠️ القاعدة تحتاج إلى ضبط أكثر (تشديد الشروط) لتجنب قتل الصفقات الرابحة.")

if __name__ == "__main__":
    main()
