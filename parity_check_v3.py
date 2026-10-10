#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parity_check_v3.py — اختبار تطابق backtest ↔ live على شموع تاريخية.
لكل إشارة backtest (20 الأحدث)، نُقلّص AssetData لتنتهي عند شمعتها
ونُشغّل live mode → يجب أن تُنتج نفس الإشارة.
"""

import sys
import copy
from pathlib import Path

sys.path.insert(0, '.')
import trading_2 as T
import __main__ as _pcmain
for _c in ('AssetData', 'Signal', 'Trade', 'OpenPosition', 'MicroState'):
    if hasattr(T, _c):
        setattr(_pcmain, _c, getattr(T, _c))

T_CFG = T.CFG
T_build_signals = T.build_signals
T_load_asset_cache = T._load_asset_cache

TIMEFRAME = "4h"
HISTORY_DAYS = 730
CACHE_DIR = "market_data_cache"
N_TEST_SIGNALS = 20


def load_symbols():
    p = Path(CACHE_DIR)
    return [f.stem.rsplit(f"_{TIMEFRAME}", 1)[0].replace("_", "/", 1)
            for f in p.glob(f"*_{TIMEFRAME}.parquet")
            if "_USDT" in f.stem][:100]


def load_df(sym):
    import pandas as pd, datetime
    fp = Path(CACHE_DIR) / f"{sym.replace('/', '_')}_{TIMEFRAME}.parquet"
    if not fp.exists():
        return None
    df = pd.read_parquet(fp)
    df.index = (df.index.tz_localize('UTC') if df.index.tz is None
                else df.index.tz_convert('UTC'))
    df = df.sort_index()
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=HISTORY_DAYS))
    df = df[df.index >= cutoff]
    return df if len(df) >= 500 else None


def build_assets(symbols):
    assets = {}
    for sym in symbols:
        df = load_df(sym)
        if df is None:
            continue
        ad = None
        try:
            ad = T_load_asset_cache(sym, TIMEFRAME, df, T_CFG)
        except Exception:
            pass
        if ad is None:
            try:
                ad = T.process_asset(sym, df,
                                     current_capital=T_CFG.INITIAL_CAPITAL)
            except Exception:
                continue
        if ad:
            assets[sym] = ad
    return assets


def truncate_asset(ad, target_ci):
    """
    Shallow-copy with arrays truncated so that len(closes) - 2 == target_ci.
    Handles the distinction between close-indexed and X-indexed arrays.
    """
    ad2 = copy.copy(ad)
    cut_c = target_ci + 2
    cut_x = cut_c - ad.feat_start

    close_fields = ['closes', 'highs', 'lows', 'volumes',
                    'ema200', 'ema_accel', 'atr14', 'adv_usd']
    x_fields = ['X', 'sym_q', 'H', 'dH', 'd2H', 'E_therm', 'F', 'dF',
                'C', 'V', 'h', 'score', 'KE', 'PE', 'ME', 'dKE', 'lya',
                'tri', 'T_info', 'gauge_force', 'friction', 'delta_gap',
                'geodesic_accel']

    for fn in close_fields:
        arr = getattr(ad2, fn, None)
        if arr is not None and hasattr(arr, '__len__') and len(arr) > cut_c:
            setattr(ad2, fn, arr[:cut_c])
    for fn in x_fields:
        arr = getattr(ad2, fn, None)
        if arr is not None and hasattr(arr, '__len__') and len(arr) > cut_x:
            setattr(ad2, fn, arr[:cut_x])
    if hasattr(ad2, 'timestamps') and len(ad2.timestamps) > cut_c:
        ad2.timestamps = ad2.timestamps[:cut_c]

    return ad2


SIGNAL_FIELDS = [
    'action', 'price', 'sl', 'tp1', 'score', 'close_idx', 'feat_idx',
    'atr', 'T_info_val', 'dynamic_risk', 'dyn_sl_factor', 'tri_val',
]


def compare(s_bt, s_lv):
    diffs = []
    for f in SIGNAL_FIELDS:
        v1 = getattr(s_bt, f, None)
        v2 = getattr(s_lv, f, None)
        if isinstance(v1, float) and isinstance(v2, float):
            if abs(v1 - v2) > 1e-6:
                diffs.append((f, round(v1, 8), round(v2, 8)))
        elif v1 != v2:
            diffs.append((f, v1, v2))
    return diffs


def main():
    print("═" * 70)
    print("  parity_check_v3 — اختبار إشارات تاريخية")
    print("═" * 70)

    symbols = load_symbols()
    print(f"\n▶ {len(symbols)} رمز محمّل")
    assets = build_assets(symbols)
    print(f"▶ {len(assets)} AssetData جاهز")

    print("\n▶ build_signals(mode='backtest') ...")
    sigs_bt = T_build_signals(assets, mode="backtest")
    print(f"  ✓ {len(sigs_bt):,} إشارة")

    # آخر N إشارة زمنياً
    sigs_sorted = sorted(sigs_bt, key=lambda s: (s.timestamp, s.close_idx))
    test_sigs = sigs_sorted[-N_TEST_SIGNALS:]

    print(f"\n▶ اختبار {len(test_sigs)} إشارة في mode='live' ...")

    matches = 0
    mismatches = []
    no_live = 0

    for i, s_orig in enumerate(test_sigs, 1):
        sym = s_orig.symbol
        target_ci = int(s_orig.close_idx)

        # Truncate ONLY this asset
        ad_trunc = truncate_asset(assets[sym], target_ci)
        live_dict = dict(assets)   # shallow
        live_dict[sym] = ad_trunc

        try:
            sigs_live = T_build_signals(live_dict, mode="live")
        except Exception as e:
            print(f"  ✗ [{i:2d}] {sym:12s}@{target_ci}: {e}")
            mismatches.append((s_orig, None, [("exception", str(e), None)]))
            continue

        # Filter for this symbol
        live_for_sym = [s for s in sigs_live if s.symbol == sym]

        if not live_for_sym:
            print(f"  ⚠️  [{i:2d}] {sym:12s}@{target_ci}: live=0, bt=1")
            no_live += 1
            mismatches.append((s_orig, None, [("no_live_signal", 1, 0)]))
            continue

        s_live = live_for_sym[0]
        diffs = compare(s_orig, s_live)

        if not diffs:
            print(f"  ✅ [{i:2d}] {sym:12s}@{target_ci}: "
                  f"{s_orig.action} score={s_orig.score:.2f}")
            matches += 1
        else:
            print(f"  ❌ [{i:2d}] {sym:12s}@{target_ci}: {len(diffs)} اختلاف")
            for f, v1, v2 in diffs[:5]:
                print(f"       {f}: {v1} vs {v2}")
            mismatches.append((s_orig, s_live, diffs))

    # تقرير
    tested = len(test_sigs)
    print()
    print("═" * 70)
    print("  التقرير النهائي")
    print("═" * 70)
    print(f"  مُختبرة:        {tested}")
    print(f"  ✅ مُتطابقة:    {matches}")
    print(f"  ❌ مُختلفة:    {len(mismatches) - no_live}")
    print(f"  ⚠️  live=0:     {no_live}")
    print()

    if tested > 0:
        pct = 100.0 * matches / tested
        print(f"  نسبة التطابق: {pct:.1f}%")
        if pct == 100.0:
            print("  ✅ PARITY CONFIRMED — آمن للانتقال إلى Testnet")
        elif pct >= 90.0:
            print("  ⚠️  HIGH CONFIDENCE — راجع الاختلافات")
        else:
            print("  ❌ PARITY FAILURE — أصلح أولاً")
    print("═" * 70)


if __name__ == '__main__':
    main()
