#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
  Diagnostic — why did reinforcement_validator analyze 0 trades?
═══════════════════════════════════════════════════════════════════════════
يقرأ trades_log_backtest.jsonl + asset_cache/ ويطبع 12 قسم تشخيصي
يحدد بالضبط أي شرط يفشل على كل الصفقات.
═══════════════════════════════════════════════════════════════════════════
"""

import json
import os
import sys
import pickle
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd


TRADES_FILE = "trades_log_backtest.jsonl"
ASSET_CACHE_DIR = "asset_cache"
MAX_SAMPLE = 500
MAX_CACHE_LOAD = 5


def section(title):
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def parse_cache_filename(name):
    """{SYMBOL_PARTS}_{TF}_{HASH}.pkl -> (symbol, tf, hash)"""
    if not name.endswith(".pkl"):
        return None
    stem = name[:-4]
    parts = stem.split("_")
    if len(parts) < 3:
        return None
    hash_part = parts[-1]
    tf_part = parts[-2]
    symbol_parts = parts[:-2]
    if not symbol_parts:
        return None
    return "/".join(symbol_parts), tf_part, hash_part


def safe_float(v, default=float("nan")):
    try:
        x = float(v)
        if not np.isfinite(x):
            return default
        return x
    except Exception:
        return default


def main():
    section("REINFORCEMENT VALIDATOR — DIAGNOSTIC")

    # ═══════════════════════════════════════════════════════════════
    # 1. TRADE FILE
    # ═══════════════════════════════════════════════════════════════
    section("1. TRADE FILE")
    if not os.path.exists(TRADES_FILE):
        print(f"  ERROR: {TRADES_FILE} not found in {os.getcwd()}")
        return 1
    size_mb = os.path.getsize(TRADES_FILE) / 1024 / 1024
    print(f"  File: {TRADES_FILE}")
    print(f"  Size: {size_mb:.2f} MB")
    print(f"  CWD : {os.getcwd()}")

    # ═══════════════════════════════════════════════════════════════
    # 2. PARSE TRADE FILE
    # ═══════════════════════════════════════════════════════════════
    section("2. PARSE TRADE FILE")
    trades = []
    n_meta = 0
    n_blank = 0
    n_parse_error = 0
    n_other = 0
    meta_records = []

    with open(TRADES_FILE, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                n_blank += 1
                continue
            try:
                obj = json.loads(s)
            except Exception as e:
                n_parse_error += 1
                if n_parse_error <= 3:
                    print(f"  Parse error line {ln}: {e}")
                continue
            if not isinstance(obj, dict):
                n_other += 1
                continue
            if obj.get("_meta"):
                n_meta += 1
                meta_records.append(obj)
            else:
                trades.append(obj)

    print(f"  Meta records   : {n_meta:,}")
    print(f"  Trade records  : {len(trades):,}")
    print(f"  Blank lines    : {n_blank:,}")
    print(f"  Parse errors   : {n_parse_error:,}")
    print(f"  Non-dict lines : {n_other:,}")

    if meta_records:
        print(f"\n  Meta records summary:")
        for i, m in enumerate(meta_records[-3:], 1):  # last 3
            print(f"    Meta #{i}: mode={m.get('mode')}, tf={m.get('timeframe')}, "
                  f"N={m.get('N')}, W={m.get('W')}, L={m.get('L')}, "
                  f"K_MAX={m.get('K_MAX')}, K_MIN={m.get('K_MIN')}, "
                  f"started={m.get('started_at')}")

    if not trades:
        print("  ERROR: no trade records found")
        return 1

    # ═══════════════════════════════════════════════════════════════
    # 3. FIELD PRESENCE
    # ═══════════════════════════════════════════════════════════════
    section(f"3. FIELD PRESENCE (first {min(MAX_SAMPLE, len(trades))})")
    sample = trades[:min(MAX_SAMPLE, len(trades))]

    key_fields = [
        "symbol", "action",
        "entry_price", "exit_price",
        "signal_price", "signal_sl", "signal_tp1",
        "entry_ci", "exit_ci", "feat_idx", "close_idx",
        "score", "hold_bars", "net_pnl", "log_return",
        "mfe_frac", "sl_dist_frac", "rr_design",
        "E_therm", "friction", "gauge_force", "delta_gap",
        "geodesic_accel", "T_info", "dF", "dH", "H", "V",
        "entry_time", "exit_reason",
    ]

    print(f"  {'Field':<18} {'present':>8}  {'types':<40}")
    print(f"  {'-'*18} {'-'*8}  {'-'*40}")

    for fld in key_fields:
        present = 0
        types = Counter()
        for t in sample:
            if fld in t and t[fld] is not None:
                present += 1
                v = t[fld]
                if isinstance(v, bool):
                    types["bool"] += 1
                elif isinstance(v, int):
                    types["int"] += 1
                elif isinstance(v, float):
                    if np.isnan(v):
                        types["nan"] += 1
                    elif np.isinf(v):
                        types["inf"] += 1
                    else:
                        types["float"] += 1
                elif isinstance(v, str):
                    types["str"] += 1
                else:
                    types[type(v).__name__] += 1
            else:
                types["MISSING"] += 1

        types_str = ", ".join(f"{k}={v}" for k, v in types.most_common(3))
        flag = ""
        if present < len(sample):
            flag = "  <-- PARTIAL"
        if "MISSING" in types and types["MISSING"] == len(sample):
            flag = "  <-- ALL MISSING"
        print(f"  {fld:<18} {present:>8}  {types_str:<40}{flag}")

    # ═══════════════════════════════════════════════════════════════
    # 4. FIRST TRADE DUMP
    # ═══════════════════════════════════════════════════════════════
    section("4. FIRST TRADE DUMP")
    t0 = trades[0]
    for k in sorted(t0.keys()):
        v = t0[k]
        if isinstance(v, float):
            v_repr = f"{v:.6g}"
        elif isinstance(v, str) and len(v) > 60:
            v_repr = v[:57] + "..."
        else:
            v_repr = repr(v)
        print(f"  {k:<25} = {v_repr}")

    # ═══════════════════════════════════════════════════════════════
    # 5. ASSET CACHE
    # ═══════════════════════════════════════════════════════════════
    section("5. ASSET CACHE DIRECTORY")
    if not os.path.isdir(ASSET_CACHE_DIR):
        print(f"  ERROR: directory '{ASSET_CACHE_DIR}' not found")
        return 1

    cache_files = sorted(Path(ASSET_CACHE_DIR).glob("*.pkl"))
    print(f"  .pkl files found: {len(cache_files):,}")

    if not cache_files:
        print("  ERROR: no .pkl files")
        return 1

    print(f"  Sample filenames:")
    for cf in cache_files[:5]:
        print(f"    {cf.name}")

    # ═══════════════════════════════════════════════════════════════
    # 6. PARSE CACHE FILENAMES
    # ═══════════════════════════════════════════════════════════════
    section("6. PARSE CACHE FILENAMES")
    cache_symbols = {}  # symbol -> [(tf, hash, path)]
    parse_errors = []

    for cf in cache_files:
        parsed = parse_cache_filename(cf.name)
        if parsed is None:
            parse_errors.append(cf.name)
            continue
        sym, tf, h = parsed
        cache_symbols.setdefault(sym, []).append((tf, h, cf))

    print(f"  Unique symbols : {len(cache_symbols):,}")
    print(f"  Parse errors   : {len(parse_errors):,}")
    if parse_errors:
        print(f"  Bad filenames (first 5):")
        for n in parse_errors[:5]:
            print(f"    {n}")

    print(f"  Sample symbols (first 10):")
    for s in list(cache_symbols)[:10]:
        tfs = [tf for tf, _, _ in cache_symbols[s]]
        print(f"    {s:<20}  files={len(cache_symbols[s])}  timeframes={tfs}")

    # ═══════════════════════════════════════════════════════════════
    # 7. CROSS-REFERENCE
    # ═══════════════════════════════════════════════════════════════
    section("7. CROSS-REFERENCE TRADES <-> CACHE")
    trade_symbols = Counter(
        t.get("symbol") for t in trades if t.get("symbol")
    )
    trade_sym_set = set(trade_symbols.keys())
    cache_sym_set = set(cache_symbols.keys())

    in_both = trade_sym_set & cache_sym_set
    only_trades = trade_sym_set - cache_sym_set
    only_cache = cache_sym_set - trade_sym_set

    print(f"  Trade symbols        : {len(trade_sym_set):,}")
    print(f"  Cache symbols        : {len(cache_sym_set):,}")
    print(f"  In both              : {len(in_both):,}")
    print(f"  Only in trades       : {len(only_trades):,}")
    print(f"  Only in cache        : {len(only_cache):,}")

    if only_trades:
        print(f"\n  ONLY-IN-TRADES (top 5 by count):")
        for s, cnt in Counter(
            {s: trade_symbols[s] for s in only_trades}
        ).most_common(5):
            print(f"    {s:<20}  trades={cnt}")

    if only_cache:
        print(f"\n  ONLY-IN-CACHE (first 5):")
        for s in list(only_cache)[:5]:
            print(f"    {s}")

    n_with_cache = sum(1 for t in trades if t.get("symbol") in cache_sym_set)
    print(f"\n  Trades with symbol in cache: {n_with_cache:,} / {len(trades):,}")

    if n_with_cache == 0:
        print("\n  *** CRITICAL: no trades have a matching cache ***")
        return 1

    # ═══════════════════════════════════════════════════════════════
    # 8. LOAD SAMPLE CACHES (top symbols by trade count)
    # ═══════════════════════════════════════════════════════════════
    section(f"8. LOAD TOP {MAX_CACHE_LOAD} CACHES (by trade count)")
    top_syms = [
        s for s, _ in trade_symbols.most_common()
        if s in cache_sym_set
    ][:MAX_CACHE_LOAD]

    loaded = {}
    for sym in top_syms:
        files_for_sym = cache_symbols[sym]
        success = False
        for tf, h, cf in files_for_sym:
            try:
                with open(cf, "rb") as f:
                    ad = pickle.load(f)
                loaded[sym] = ad
                print(f"  {sym:<20} ({tf})  OK  closes={len(ad.closes):,}  "
                      f"feat_start={getattr(ad, 'feat_start', '?')}")
                success = True
                break
            except Exception as e:
                print(f"  {sym:<20} ({tf})  FAILED: {type(e).__name__}: {e}")
        if not success:
            print(f"  {sym:<20} NO CACHE COULD LOAD")

    if not loaded:
        print("\n  *** CRITICAL: no cache file could be loaded ***")
        return 1

    # ═══════════════════════════════════════════════════════════════
    # 9. TIMESTAMP + INDEX MATCHING (CRITICAL)
    # ═══════════════════════════════════════════════════════════════
    section("9. ENTRY_CI / TIMESTAMP MATCHING (CRITICAL)")
    for sym, ad in loaded.items():
        print(f"\n  ── {sym} ──")
        print(f"    len(closes)    : {len(ad.closes):,}")
        print(f"    feat_start     : {getattr(ad, 'feat_start', '?')}")
        print(f"    train_end      : {getattr(ad, 'train_end', '?')}")
        print(f"    timestamps.tz  : {ad.timestamps.tz}")
        print(f"    first_ts       : {ad.timestamps[0]}")
        print(f"    last_ts        : {ad.timestamps[-1]}")

        sym_trades = [t for t in trades if t.get("symbol") == sym][:3]
        print(f"    Trade samples ({len(sym_trades)}):")

        for t in sym_trades:
            eci = t.get("entry_ci")
            fi = t.get("feat_idx")
            et = t.get("entry_time")

            print(f"\n      trade: entry_ci={eci} feat_idx={fi} entry_time={et}")

            # Test 1: entry_ci is int and in bounds
            if type(eci) != int or eci < 0:
                print(f"        [X] entry_ci not int>=0 (type={type(eci).__name__})")
            elif eci >= len(ad.closes):
                print(f"        [X] entry_ci {eci} >= len(closes) {len(ad.closes)}")
            else:
                ts_at_ci = ad.timestamps[eci]
                print(f"        [OK] entry_ci in bounds")
                print(f"             ts_at_ci = {ts_at_ci}")
                print(f"             entry_time = {et}")
                print(f"             str match = {str(ts_at_ci) == str(et)}")

            # Test 2: implied feat_start from trade
            if type(eci) == int and type(fi) == int and eci >= 0 and fi >= 0:
                implied_fs = eci - fi
                ad_fs = getattr(ad, "feat_start", None)
                match = (implied_fs == ad_fs)
                print(f"        implied feat_start = {implied_fs}, "
                      f"cache feat_start = {ad_fs}, match = {match}")
                if not match:
                    print(f"        *** CFG MISMATCH — cache was computed with "
                          f"different N or feats ***")

            # Test 3: entry_time -> searchsorted
            if isinstance(et, str):
                try:
                    ts = pd.Timestamp(et)
                    if ad.timestamps.tz is not None and ts.tz is None:
                        ts = ts.tz_localize(ad.timestamps.tz)
                    elif ad.timestamps.tz is None and ts.tz is not None:
                        ts = ts.tz_convert(None)
                    idx = int(ad.timestamps.searchsorted(ts, side="left"))
                    if 0 <= idx < len(ad.timestamps):
                        found = ad.timestamps[idx]
                        exact = (found == ts)
                        print(f"        searchsorted -> idx={idx} exact={exact}")
                        if not exact:
                            print(f"        found={found}, requested={ts}")
                    else:
                        print(f"        searchsorted -> OUT OF BOUNDS idx={idx}")
                except Exception as e:
                    print(f"        timestamp parse FAILED: {type(e).__name__}: {e}")

    # ═══════════════════════════════════════════════════════════════
    # 10. SIMULATED FILTER CHAIN
    # ═══════════════════════════════════════════════════════════════
    section("10. SIMULATED FILTER CHAIN")
    trades_sample = [t for t in trades if t.get("symbol") in loaded]
    if not trades_sample:
        trades_sample = trades
        print(f"  Using all {len(trades_sample):,} trades (no symbol loaded)")
    else:
        print(f"  Using {len(trades_sample):,} trades whose symbols loaded")

    checks = [
        ("symbol in loaded", lambda t: t.get("symbol") in loaded),
        ("entry_ci int>=0", lambda t: type(t.get("entry_ci")) == int
                                     and t.get("entry_ci") >= 0),
        ("exit_ci int>=0", lambda t: type(t.get("exit_ci")) == int
                                    and t.get("exit_ci") >= 0),
        ("feat_idx int>=0", lambda t: type(t.get("feat_idx")) == int
                                     and t.get("feat_idx") >= 0),
        ("entry_price>0", lambda t: safe_float(t.get("entry_price"), -1) > 0),
        ("exit_price>0", lambda t: safe_float(t.get("exit_price"), -1) > 0),
        ("signal_price>0", lambda t: safe_float(t.get("signal_price"), -1) > 0),
        ("signal_sl>0", lambda t: safe_float(t.get("signal_sl"), -1) > 0),
        ("hold_bars>0", lambda t: type(t.get("hold_bars")) == int
                                 and t.get("hold_bars") > 0),
        ("E_therm finite", lambda t: np.isfinite(
            safe_float(t.get("E_therm"), np.nan))),
        ("friction finite", lambda t: np.isfinite(
            safe_float(t.get("friction"), np.nan))),
        ("geodesic_accel finite", lambda t: np.isfinite(
            safe_float(t.get("geodesic_accel"), np.nan))),
        ("entry_ci in cache bounds", lambda t: (
            type(t.get("entry_ci")) == int
            and t.get("entry_ci") >= 0
            and t.get("symbol") in loaded
            and t["entry_ci"] < len(loaded[t["symbol"]].closes)
        )),
        ("feat_start matches", lambda t: (
            type(t.get("entry_ci")) == int
            and type(t.get("feat_idx")) == int
            and t.get("symbol") in loaded
            and (t["entry_ci"] - t["feat_idx"]) == loaded[t["symbol"]].feat_start
        )),
    ]

    remaining = list(trades_sample)
    for label, fn in checks:
        before = len(remaining)
        try:
            remaining = [t for t in remaining if fn(t)]
        except Exception as e:
            print(f"  {label:<28}: EXCEPTION: {e}")
            continue
        after = len(remaining)
        pct = 100.0 * after / max(before, 1)
        status = ""
        if after == 0 and before > 0:
            status = "  *** ELIMINATED ALL ***"
        print(f"  {label:<28}: {before:>6,} -> {after:>6,}  ({pct:5.1f}%){status}")
        if after == 0:
            break

    # ═══════════════════════════════════════════════════════════════
    # 11. EXIT REASON DISTRIBUTION
    # ═══════════════════════════════════════════════════════════════
    section("11. EXIT REASON DISTRIBUTION (top 20)")
    exit_dist = Counter()
    for t in trades:
        r = t.get("exit_reason", "?")
        if isinstance(r, str):
            key = r.split("(")[0].split("=")[0].strip()[:45]
        else:
            key = str(r)[:45]
        exit_dist[key] += 1

    for reason, cnt in exit_dist.most_common(20):
        pct = 100.0 * cnt / len(trades)
        print(f"  {reason:<48}: {cnt:>7,}  ({pct:5.1f}%)")

    # ═══════════════════════════════════════════════════════════════
    # 12. SUBSET STATISTICS
    # ═══════════════════════════════════════════════════════════════
    section("12. SUBSET STATISTICS")

    n_hb2 = sum(1 for t in trades
                if type(t.get("hold_bars")) == int and t.get("hold_bars") >= 2)
    print(f"  hold_bars >= 2                    : {n_hb2:,} / {len(trades):,}")

    n_sl = sum(1 for t in trades
               if isinstance(t.get("exit_reason"), str)
               and "Emergency SL" in t["exit_reason"])
    print(f"  exit_reason contains 'Emergency SL': {n_sl:,}")

    n_tp = sum(1 for t in trades
               if isinstance(t.get("exit_reason"), str)
               and "Hard TP" in t["exit_reason"])
    print(f"  exit_reason contains 'Hard TP'    : {n_tp:,}")

    n_full = sum(
        1 for t in trades
        if type(t.get("entry_ci")) == int
        and t["entry_ci"] >= 0
        and t.get("symbol") in loaded
        and t["entry_ci"] < len(loaded[t["symbol"]].closes)
    )
    print(f"  entry_ci valid AND in cache bounds: {n_full:,}")

    n_fs_match = sum(
        1 for t in trades
        if type(t.get("entry_ci")) == int
        and type(t.get("feat_idx")) == int
        and t.get("symbol") in loaded
        and (t["entry_ci"] - t["feat_idx"]) == loaded[t["symbol"]].feat_start
    )
    print(f"  feat_start matches (entry_ci-fi)  : {n_fs_match:,}")

    section("DIAGNOSTIC COMPLETE")
    print("\n  Copy-paste this entire output for analysis.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted.\n")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n  FATAL: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
