#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parity_check.py — التحقق النهائي قبل Testnet (v2)
- إصلاح: pickle alias for AssetData
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, '.')

# ── استيراد محرك التداول ──
try:
    import trading_2 as T
except ImportError as e:
    print(f"❌ فشل استيراد trading_2: {e}")
    sys.exit(1)

# ══ [PICKLE-FIX] حل مشكلة "module '__main__' has no attribute 'AssetData'" ══
# الكاش كُتب عندما كان trading_2.py هو __main__. نُسجّل alias في __main__
# حتى يستطيع pickle إيجاد الفئات.
import __main__ as _pcmain
for _cls_name in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(T, _cls_name):
        setattr(_pcmain, _cls_name, getattr(T, _cls_name))

T_CFG = T.CFG
T_build_signals = T.build_signals
T_deduplicate = T.deduplicate_signals
T_load_asset_cache = T._load_asset_cache


# ═══════════════════════════════════════════════════════════════
# الإعدادات
# ═══════════════════════════════════════════════════════════════

N_ASSETS = 100
TIMEFRAME = "4h"
HISTORY_DAYS = 730
CACHE_DIR = "market_data_cache"


# ═══════════════════════════════════════════════════════════════
# أدوات
# ═══════════════════════════════════════════════════════════════

def load_symbols_from_cache():
    p = Path(CACHE_DIR)
    if not p.exists():
        return []
    syms = []
    for f in p.glob(f"*_{TIMEFRAME}.parquet"):
        name = f.stem
        parts = name.rsplit(f"_{TIMEFRAME}", 1)
        if len(parts) != 2:
            continue
        base = parts[0]
        if "_USDT" in base:
            sym = base.replace("_", "/", 1)
            syms.append(sym)
    return syms[:N_ASSETS]


def load_dataframe(sym):
    import pandas as pd
    import datetime
    fp = Path(CACHE_DIR) / f"{sym.replace('/', '_')}_{TIMEFRAME}.parquet"
    if not fp.exists():
        return None
    try:
        df = pd.read_parquet(fp)
        if df.index.tz is None:
            df.index = pd.to_datetime(df.index, utc=True)
        else:
            df.index = df.index.tz_convert('UTC')
        df = df.sort_index()
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=HISTORY_DAYS)
        )
        df = df[df.index >= cutoff]
        return df if len(df) >= 500 else None
    except Exception as e:
        print(f"  ⚠️  قراءة {sym}: {e}")
        return None


def build_assets(symbols):
    assets = {}
    print(f"\n▶ بناء AssetData لـ {len(symbols)} رمز ...")
    cache_hits = 0
    cache_misses = 0
    for i, sym in enumerate(symbols, 1):
        df = load_dataframe(sym)
        if df is None:
            continue
        ad = None
        try:
            ad = T_load_asset_cache(sym, TIMEFRAME, df, T_CFG)
        except Exception:
            ad = None
        if ad is not None:
            cache_hits += 1
        else:
            cache_misses += 1
            try:
                ad = T.process_asset(sym, df,
                                     current_capital=T_CFG.INITIAL_CAPITAL)
            except Exception as e:
                print(f"  ✗ {sym}: process_asset فشل: {e}")
                continue
        if ad is not None:
            assets[sym] = ad
        if i % 20 == 0 or i == len(symbols):
            print(f"  [{i:3d}/{len(symbols)}] hit={cache_hits}, miss={cache_misses}, "
                  f"assets={len(assets)}")
    return assets


# ═══════════════════════════════════════════════════════════════
# المقارنة
# ═══════════════════════════════════════════════════════════════

SIGNAL_FIELDS = [
    'action', 'price', 'sl', 'tp1',
    'score', 'close_idx', 'feat_idx',
    'atr', 'T_info_val', 'dynamic_risk',
    'dyn_sl_factor', 'tri_val',
]


def signal_to_dict(sig):
    d = {}
    for f in SIGNAL_FIELDS:
        v = getattr(sig, f, None)
        if isinstance(v, float):
            d[f] = round(v, 8)
        else:
            d[f] = v
    return d


def compare_signals(sig_bt, sig_live):
    if sig_bt is None and sig_live is None:
        return True, []
    if sig_bt is None:
        return False, [('missing_in_backtest', None, None)]
    if sig_live is None:
        return False, [('missing_in_live', None, None)]

    d_bt = signal_to_dict(sig_bt)
    d_live = signal_to_dict(sig_live)

    diffs = []
    for f in SIGNAL_FIELDS:
        v_bt = d_bt.get(f)
        v_live = d_live.get(f)
        if isinstance(v_bt, float) and isinstance(v_live, float):
            if abs(v_bt - v_live) > 1e-6:
                diffs.append((f, v_bt, v_live))
        elif v_bt != v_live:
            diffs.append((f, v_bt, v_live))
    return (len(diffs) == 0), diffs


# ═══════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════

def main():
    print("═" * 70)
    print("  parity_check.py")
    print("  التحقق من تطابق backtest ↔ live على نفس البيانات")
    print("═" * 70)

    symbols = load_symbols_from_cache()
    if not symbols:
        print(f"❌ لا توجد رموز في {CACHE_DIR}")
        sys.exit(1)
    print(f"\n▶ {len(symbols)} رمز محمّل من الكاش")

    assets = build_assets(symbols)
    print(f"\n▶ {len(assets)} AssetData جاهز")

    if len(assets) == 0:
        print("❌ لا AssetData — لا يمكن المتابعة")
        sys.exit(1)

    print("\n▶ build_signals(mode='backtest') ...")
    try:
        sigs_bt = T_build_signals(assets, mode="backtest")
    except Exception as e:
        print(f"❌ فشل: {e}")
        import traceback; traceback.print_exc()
        sys.exit(2)
    print(f"  ✓ {len(sigs_bt):,} إشارة")

    print("\n▶ build_signals(mode='live') ...")
    try:
        sigs_live = T_build_signals(assets, mode="live")
    except Exception as e:
        print(f"❌ فشل: {e}")
        import traceback; traceback.print_exc()
        sys.exit(3)
    print(f"  ✓ {len(sigs_live):,} إشارة")

    # ── تجميع backtest signals ──
    bt_by_key = {}
    for s in sigs_bt:
        key = (s.symbol, int(s.close_idx))
        bt_by_key[key] = s

    matches = 0
    mismatches = []
    only_live = []
    tested = 0

    for s_live in sigs_live:
        sym = s_live.symbol
        ci = int(s_live.close_idx)
        tested += 1

        s_bt = bt_by_key.get((sym, ci))
        if s_bt is None:
            only_live.append(s_live)
            continue

        ok, diffs = compare_signals(s_bt, s_live)
        if ok:
            matches += 1
        else:
            mismatches.append((s_bt, s_live, diffs))

    if tested == 0:
        print()
        print("═" * 70)
        print("  ⚠️  لا إشارات في آخر شمعة مغلقة عبر كل الرموز")
        print("═" * 70)
        print("  هذا يعني: في اللحظة الحالية، لا توجد فرصة تداول.")
        print("  الاختبار غير حاسم — لكنه لا يكشف أي مشكلة.")
        # كم إشارة في backtest عند آخر شمعة لكل رمز؟
        last_bar_signals = 0
        for sym, ad in assets.items():
            last_ci = len(ad.closes) - 2
            if (sym, last_ci) in bt_by_key:
                last_bar_signals += 1
        print(f"\n  إجمالي إشارات الباكتيست: {len(sigs_bt):,}")
        print(f"  إشارات عند آخر شمعة مغلقة: {last_bar_signals}")
        return

    print()
    print("═" * 70)
    print("  نتائج المقارنة")
    print("═" * 70)
    print()
    print(f"  عدد الإشارات المُختبرة: {tested}")
    print(f"  ✅ مُتطابقة:            {matches}")
    print(f"  ❌ مُختلفة:            {len(mismatches)}")
    print(f"  ⚠️  فقط في live:        {len(only_live)}")
    print()

    if mismatches:
        print("═" * 70)
        print("  تفاصيل الاختلافات (أول 5)")
        print("═" * 70)
        for s_bt, s_live, diffs in mismatches[:5]:
            print(f"\n  🔴 {s_bt.symbol} @ ci={s_bt.close_idx}")
            print(f"     action: {s_bt.action} vs {s_live.action}")
            for f, v_bt, v_live in diffs:
                print(f"     {f}: {v_bt} vs {v_live}")

    if only_live:
        print()
        print("═" * 70)
        print("  إشارات في live وليس في backtest (أول 5)")
        print("═" * 70)
        for s in only_live[:5]:
            print(f"  ⚠️  {s.symbol} @ ci={s.close_idx} ({s.action})")

    print()
    print("═" * 70)
    print("  الحكم النهائي")
    print("═" * 70)
    print()

    match_pct = 100.0 * matches / tested if tested > 0 else 0.0

    if match_pct == 100.0:
        verdict = "✅ PARITY CONFIRMED"
        recommendation = "آمن للانتقال إلى Testnet"
    elif match_pct >= 90.0:
        verdict = "⚠️  HIGH CONFIDENCE"
        recommendation = "راجع الاختلافات قبل المتابعة"
    else:
        verdict = "❌ PARITY FAILURE"
        recommendation = "لا تنتقل إلى Testnet — أصلح أولاً"

    print(f"  {verdict}")
    print(f"  نسبة التطابق: {match_pct:.1f}%")
    print(f"  التوصية:      {recommendation}")
    print()
    print("═" * 70)


if __name__ == '__main__':
    main()
