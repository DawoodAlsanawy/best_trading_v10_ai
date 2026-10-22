#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, glob
import importlib.util
import numpy as np
import pandas as pd
import warnings
from datetime import timedelta

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
    
    for fpath in files:
        parts = os.path.basename(fpath).split('_')
        if len(parts) >= 3: sym = f"{parts[0]}/{parts[1]}"
        else: continue
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

def main():
    HISTORY_DAYS = 730
    print("⏳ Initializing environment...")
    bot.CFG.timeframe = '4h'
    bot.CFG.history_days = HISTORY_DAYS
    bot.CFG.REVERSAL_CONFIRM_ENABLED = True
    bot.CFG.REVERSAL_TOUCH_SUBBARS = 48
    bot.CFG.REVERSAL_BOUNCE_SUBBARS = 48
    bot.CFG.REVERSAL_CONFIRM_MODE = 'sigma_bounce'
    bot.CFG.REVERSAL_CONFIRM_KAPPA = 0.3
    bot.CFG.REVERSAL_FILL_AT = 'target'
    bot.CFG.GAUGE_DISABLE_SELL = False
    bot.CFG.SELL_GAUGE_PCT = 85
    bot.CFG.SL_WIDEN_MULT = 1.5
    bot.CFG.PARTIAL_TP_R = 1.2
    bot.CFG.REV_ABORT_KAPPA = 2.0
    bot.CFG.BREAKEVEN_ENABLED = False

    traded_symbols = set()
    with open("trades_log_backtest.jsonl") as f:
        for line in f:
            if line.strip():
                try:
                    r = json.loads(line)
                    if not r.get('_meta') and 'symbol' in r: traded_symbols.add(r['symbol'])
                except: pass

    raw, raw_sub = load_local_data("market_data_cache", "4h", traded_symbols, HISTORY_DAYS)
    assets = {}
    for sym, df in raw.items():
        ad = bot.process_asset(sym, df, current_capital=100, sub_df=raw_sub.get(sym))
        if ad is not None: assets[sym] = ad

    sigs = bot.deduplicate_signals(bot.build_signals(assets, mode='backtest'))
    print(f"✓ Analyzing {len(sigs)} signals...")

    wins_excursions = []
    fails_excursions = []
    
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
        
        touch_sub_idx = -1
        if sig.action == "BUY":
            idx = np.where(sl <= target0)[0]
            if len(idx) > 0: touch_sub_idx = idx[0]
        else:
            idx = np.where(sh >= target0)[0]
            if len(idx) > 0: touch_sub_idx = idx[0]
        if touch_sub_idx == -1: continue

        # التأكد من النتيجة النهائية (بعد 48 شمعة)
        res = bot._check_reversal_fill_subbars(ad, sig, target0, bot.CFG, start_main, end_main)
        aborted = 1 if res is None else 0

        # حساب أقصى هبوط في أول 3 شموع فقط
        if touch_sub_idx + 3 < len(sc):
            c_3 = sc[touch_sub_idx + 3]
            sign = 1.0 if sig.action == "BUY" else -1.0
            # delta سالب يعني أن السعر ذهب ضدنا
            delta_3 = (c_3 - target0) * sign / target0
            
            if aborted:
                fails_excursions.append(-delta_3)
            else:
                wins_excursions.append(-delta_3)

    # إيجاد الحد الآمن
    max_win_excursion = max(wins_excursions) if wins_excursions else 0.0
    # نضيف هامش أمان 0.0001 (0.01%)
    safe_threshold = max_win_excursion + 0.0001

    caught_fails = sum(1 for f in fails_excursions if f > safe_threshold)
    total_fails = len(fails_excursions)

    print("\n" + "="*60)
    print("📊 نتائج الإلغاء المبكر الآمن (Smart Early Abort at k=3):")
    print(f"  إجمالي الصفقات الفاشلة: {total_fails}")
    print(f"  إجمالي الصفقات الرابحة: {len(wins_excursions)}")
    print("-" * 60)
    print(f"  أقصى هبوط مؤقت لصفقة رابحة (في أول 45 دقيقة): {max_win_excursion*100:.2f}%")
    print(f"  حد الإلغاء الآمن المقترح: {safe_threshold*100:.2f}%")
    print("-" * 60)
    print(f"  🎯 الصفقات الفاشلة التي سيتم إيقافها مبكراً: {caught_fails} ({caught_fails/max(total_fails,1)*100:.1f}%)")
    print(f"  ❌ الصفقات الرابحة المقتولة: 0 (مضمون رياضياً)")
    print("="*60)
    print(f"\n💡 لتطبيق هذا في البوت، استخدم المعامل: REV_ABORT_KAPPA = {safe_threshold / 0.01:.2f}")
    print("   (بافتراض أن sigma_bar ≈ 1% في المتوسط)")

if __name__ == "__main__":
    main()
