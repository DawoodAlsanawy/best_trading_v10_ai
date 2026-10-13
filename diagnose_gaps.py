#!/usr/bin/env python3
"""
diagnose_gaps.py — CACHE GAP DIAGNOSTIC

No assumptions. Collects raw evidence from:
  1. The cached parquet file (what's actually stored)
  2. The exchange (what it actually returns for each gap)
  3. Network timing and errors
  4. Rate limit signals
  5. Timezone consistency

Usage:
  python diagnose_gaps.py BCH/USDT 4h
  python diagnose_gaps.py BCH/USDT 4h --exchange testnet
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd

CACHE_DIR = "market_data_cache"


def parse_tf_seconds(tf: str) -> int:
    tf = tf.strip().lower()
    if tf.endswith('m'): return int(tf[:-1]) * 60
    if tf.endswith('h'): return int(tf[:-1]) * 3600
    if tf.endswith('d'): return int(tf[:-1]) * 86400
    return 3600


def find_cache_file(symbol: str, timeframe: str) -> str:
    """Try every possible cache filename variant."""
    safe = symbol.replace('/', '_')
    candidates = [
        f"{safe}_{timeframe}_live.parquet",
        f"{safe}_{timeframe}_testnet.parquet",
        f"{safe}_{timeframe}.parquet",
        f"{safe}_{timeframe}.parquet.legacy",
    ]
    for c in candidates:
        p = os.path.join(CACHE_DIR, c)
        if os.path.exists(p):
            return p
    return ""


def section(title):
    print("\n" + "═" * 72)
    print(f"  {title}")
    print("═" * 72)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("timeframe")
    ap.add_argument("--exchange", choices=["live", "testnet", "both"],
                    default="both")
    ap.add_argument("--max-gaps", type=int, default=5,
                    help="how many gap ranges to probe")
    a = ap.parse_args()

    tf_sec = parse_tf_seconds(a.timeframe)

    # ═══════════════════════════════════════════════════════════
    section("1. CACHED FILE")
    # ═══════════════════════════════════════════════════════════
    fp = find_cache_file(a.symbol, a.timeframe)
    if not fp:
        print(f"✗ No cache file found for {a.symbol} {a.timeframe}")
        print(f"  Looked in: {os.path.abspath(CACHE_DIR)}")
        print(f"  Files present:")
        for f in sorted(os.listdir(CACHE_DIR))[:30]:
            print(f"    {f}")
        sys.exit(1)

    print(f"  Path:      {fp}")
    print(f"  Size:      {os.path.getsize(fp):,} bytes")
    print(f"  mtime:     {datetime.fromtimestamp(os.path.getmtime(fp), tz=timezone.utc)}")

    df = pd.read_parquet(fp)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, utc=True)
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    else:
        df.index = df.index.tz_convert('UTC')

    print(f"  Rows:      {len(df):,}")
    print(f"  Columns:   {list(df.columns)}")
    print(f"  Index tz:  {df.index.tz}")
    print(f"  First ts:  {df.index[0]}")
    print(f"  Last  ts:  {df.index[-1]}")
    print(f"  Span:      {(df.index[-1] - df.index[0])}")
    print(f"  Expected:  {(df.index[-1] - df.index[0]) / timedelta(seconds=tf_sec):.1f} bars")
    print(f"  Actual:    {len(df):,} bars")

    diffs = df.index.to_series().diff().dropna()
    print(f"\n  Diff stats (should all equal {tf_sec}s):")
    print(f"    min:   {int(diffs.min().total_seconds())}s")
    print(f"    max:   {int(diffs.max().total_seconds())}s")
    print(f"    mode:  {int(diffs.mode().iloc[0].total_seconds())}s")
    print(f"    unique values: {diffs.dt.total_seconds().unique()[:10]}")

    # Detect gaps
    gap_mask = diffs > timedelta(seconds=tf_sec * 1.5)
    gap_idx = np.where(gap_mask.values)[0]
    print(f"\n  Gaps found: {len(gap_idx)}")
    print(f"  Gap sizes (bars missing):")
    gap_list = []
    for gi in gap_idx[:20]:
        prev_ts = df.index[gi]
        next_ts = df.index[gi + 1]
        missing = int((next_ts - prev_ts).total_seconds() // tf_sec) - 1
        gap_list.append((prev_ts, next_ts, missing))
        print(f"    {prev_ts}  →  {next_ts}   ({missing} bars)")
    if len(gap_idx) > 20:
        print(f"    ... and {len(gap_idx) - 20} more")

    # ═══════════════════════════════════════════════════════════
    section("2. EXCHANGE CONNECTIVITY")
    # ═══════════════════════════════════════════════════════════
    try:
        import ccxt
    except ImportError:
        print("✗ pip install ccxt"); sys.exit(1)

    exchanges = {}
    if a.exchange in ("live", "both"):
        exchanges['live'] = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
        })
    if a.exchange in ("testnet", "both"):
        ex_t = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
        })
        try:
            ex_t.enable_demo_trading(True)
        except Exception:
            pass
        exchanges['testnet'] = ex_t

    for name, ex in exchanges.items():
        print(f"\n  ── {name} ──")
        try:
            _t0 = time.time()
            srv_ms = ex.fetch_time()
            _latency = (time.time() * 1000) - srv_ms
            print(f"    fetch_time:        {srv_ms}  (latency {_latency:.0f}ms)")
        except Exception as e:
            print(f"    ✗ fetch_time: {e}")
            continue

        try:
            _t0 = time.time()
            tick = ex.fetch_ticker(a.symbol)
            print(f"    fetch_ticker:      OK ({time.time()-_t0:.2f}s)  "
                  f"last={tick.get('last')}")
        except Exception as e:
            print(f"    ✗ fetch_ticker:    {e}")

        # Probe the most recent gap (usually the most relevant)
        if gap_list:
            prev_ts, next_ts, missing = gap_list[0]
            print(f"\n    Probing gap: {prev_ts} → {next_ts} ({missing} missing)")
            since_ms = int((prev_ts + timedelta(seconds=tf_sec)).timestamp() * 1000)
            end_ms   = int(next_ts.timestamp() * 1000)
            print(f"      since_ms = {since_ms}  ({prev_ts + timedelta(seconds=tf_sec)})")
            print(f"      end_ms   = {end_ms}    ({next_ts})")

            try:
                _t0 = time.time()
                chunk = ex.fetch_ohlcv(a.symbol, a.timeframe,
                                        since=since_ms, limit=1000)
                _dt = time.time() - _t0
                print(f"      fetch_ohlcv returned {len(chunk)} bars "
                      f"in {_dt:.2f}s")
                if chunk:
                    print(f"      First bar: {datetime.fromtimestamp(chunk[0][0]/1000, tz=timezone.utc)}  "
                          f"O={chunk[0][1]} H={chunk[0][2]} L={chunk[0][3]} C={chunk[0][4]} V={chunk[0][5]}")
                    print(f"      Last bar:  {datetime.fromtimestamp(chunk[-1][0]/1000, tz=timezone.utc)}")
                    # Do any bars fall inside our gap?
                    inside = [c for c in chunk if since_ms <= c[0] <= end_ms]
                    print(f"      Bars INSIDE the gap window: {len(inside)}")
                    if inside:
                        print(f"        → Exchange HAS data for this gap")
                    else:
                        print(f"        → Exchange has NO data for this gap "
                              f"(genuine hole in history)")
            except Exception as e:
                print(f"      ✗ fetch_ohlcv raised: {type(e).__name__}: {e}")

        # Rate-limit signals
        print(f"\n    Rate-limit info:")
        for attr in ('last_response_headers', 'rateLimit', 'options'):
            try:
                v = getattr(ex, attr, None)
                if attr == 'last_response_headers' and v:
                    interesting = {k: vv for k, vv in v.items()
                                   if 'weight' in k.lower() or
                                      'ratelimit' in k.lower() or
                                      'retry' in k.lower()}
                    print(f"      {attr}: {interesting or '(none)'}")
                elif attr != 'last_response_headers':
                    print(f"      {attr}: {v}")
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════
    section("3. CONCURRENT PROBE — 10 back-to-back fetches")
    # ═══════════════════════════════════════════════════════════
    if 'live' in exchanges:
        ex = exchanges['live']
        success = 0
        failures = []
        for i in range(10):
            try:
                _t0 = time.time()
                chunk = ex.fetch_ohlcv(a.symbol, a.timeframe, limit=100)
                _dt = time.time() - _t0
                if chunk:
                    success += 1
                else:
                    failures.append((i, 'empty', _dt))
            except Exception as e:
                failures.append((i, f'{type(e).__name__}: {e}', 0))
            time.sleep(0.1)
        print(f"  Successes: {success}/10")
        if failures:
            for i, msg, dt in failures:
                print(f"    attempt {i}: {msg}")

    # ═══════════════════════════════════════════════════════════
    section("4. VERDICT")
    # ═══════════════════════════════════════════════════════════
    print("  Read the sections above.")
    print("  - If the exchange returns 0 bars inside a gap → genuine hole (Binance)")
    print("  - If it returns bars but cache still shows the gap → merge bug")
    print("  - If fetch_ohlcv raises intermittently → network / rate-limit")
    print("  - If testnet returns fewer bars than live → testnet data is sparse")
    print("═" * 72)


if __name__ == "__main__":
    main()
