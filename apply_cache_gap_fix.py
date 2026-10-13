#!/usr/bin/env python3
"""
apply_cache_gap_fix.py
Makes the OHLCV cache remember "dead gaps" — gaps the exchange cannot
fill. They are skipped on future runs instead of being retried forever.

Run:  python apply_cache_gap_fix.py
"""
import os, sys, shutil, hashlib

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found", file=sys.stderr); sys.exit(1)

if "_DEAD_GAPS" in open(SRC).read():
    print("✗ Already patched. Restore from .bak first.", file=sys.stderr)
    sys.exit(3)

shutil.copy2(SRC, SRC + ".bak")
print(f"✓ backup → {SRC}.bak\n")

with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()
orig = s
report = []

def patch(old, new, label, required=True):
    global s
    if old not in s:
        report.append(("✗" if required else "⚠") + f" {label}")
        return False
    s = s.replace(old, new, 1)
    report.append("✓ " + label)
    return True

# ═══════════════════════════════════════════════════════════════
# 1. Dead-gap tracking helpers — inserted after _CACHE_HEALTH
# ═══════════════════════════════════════════════════════════════
ANCHOR1 = '''_CACHE_HEALTH: Dict = {
    'files_scanned': 0,
    'issues_fixed_local': 0,
    'gaps_found': 0,
    'bars_refetched': 0,
    'files_saved': 0,
}'''

MODULE = '''_CACHE_HEALTH: Dict = {
    'files_scanned': 0,
    'issues_fixed_local': 0,
    'gaps_found': 0,
    'bars_refetched': 0,
    'files_saved': 0,
}

# ═══════════════════════════════════════════════════════════════
# [DEAD-GAPS] Persistent record of gaps the exchange cannot fill.
# Once a (symbol, timeframe, start_ts, end_ts) is confirmed dead,
# we stop retrying it forever.
# ═══════════════════════════════════════════════════════════════
_DEAD_GAPS_FILE = "cache_dead_gaps.json"
_DEAD_GAPS: Dict[str, list] = {}


def _dead_gaps_load() -> None:
    global _DEAD_GAPS
    if not os.path.exists(_DEAD_GAPS_FILE):
        return
    try:
        with open(_DEAD_GAPS_FILE) as f:
            _DEAD_GAPS = json.load(f)
    except Exception:
        _DEAD_GAPS = {}


def _dead_gaps_save() -> None:
    try:
        tmp = _DEAD_GAPS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_DEAD_GAPS, f)
        os.replace(tmp, _DEAD_GAPS_FILE)
    except Exception:
        pass


def _is_dead_gap(symbol: str, timeframe: str,
                  start_ts: int, end_ts: int) -> bool:
    """True if the entire [start_ts, end_ts] lies inside a known dead gap."""
    for (ds, de) in _DEAD_GAPS.get(f"{symbol}|{timeframe}", []):
        if ds <= start_ts and end_ts <= de:
            return True
    return False


def _mark_dead_gap(symbol: str, timeframe: str,
                    start_ts: int, end_ts: int) -> None:
    key = f"{symbol}|{timeframe}"
    lst = _DEAD_GAPS.setdefault(key, [])
    for (ds, de) in lst:
        if ds == start_ts and de == end_ts:
            return  # already recorded
    lst.append([int(start_ts), int(end_ts)])
    _dead_gaps_save()


# Load on import
try:
    _dead_gaps_load()
except Exception:
    pass'''

patch(ANCHOR1, MODULE, "insert dead-gaps helpers")

# ═══════════════════════════════════════════════════════════════
# 2. _load_cached — filter dead gaps + mark unfilled
# ═══════════════════════════════════════════════════════════════
OLD1 = '''    if issues.get('gaps', 0) > 0 and gap_ranges:
        _relevant = [(s, e) for (s, e) in gap_ranges
                     if e >= since_full_dt]
        if _relevant:
            _n_before = len(df)
            try:
                df_gap = _fetch_ranges(
                    exchange, symbol, timeframe, _relevant, _tf_sec
                )
            except Exception as e:
                log.warning(f"[Cache-Health] {symbol} gap fetch "
                            f"failed: {e}")
                df_gap = None

            if df_gap is not None and len(df_gap) > 0:
                df = pd.concat([df, df_gap])
                df = (df[~df.index.duplicated(keep='last')]
                        .sort_index())
                _gaps_filled = len(_relevant)
                _bars_fetched = len(df) - _n_before
                try:
                    df.to_parquet(fp)
                    _CACHE_HEALTH['files_saved'] += 1
                except Exception as e:
                    log.debug(f"[Cache-Health] {symbol} save failed: {e}")'''

NEW1 = '''    if issues.get('gaps', 0) > 0 and gap_ranges:
        _candidates = [(s, e) for (s, e) in gap_ranges
                       if e >= since_full_dt]
        # [DEAD-GAPS] Skip gaps the exchange cannot fill
        _relevant = [(s, e) for (s, e) in _candidates
                     if not _is_dead_gap(symbol, timeframe,
                                          int(s.timestamp()),
                                          int(e.timestamp()))]
        _n_dead_skipped = len(_candidates) - len(_relevant)
        if _n_dead_skipped > 0:
            log.debug(f"[Cache-Health] {symbol} {timeframe}: "
                      f"skipped {_n_dead_skipped} known-dead gap(s)")
        if _relevant:
            _n_before = len(df)
            try:
                df_gap = _fetch_ranges(
                    exchange, symbol, timeframe, _relevant, _tf_sec
                )
            except Exception as e:
                log.warning(f"[Cache-Health] {symbol} gap fetch "
                            f"failed: {e}")
                df_gap = None

            # [DEAD-GAPS] Identify gaps that returned no bars
            if df_gap is not None and len(df_gap) > 0:
                _gap_idx = df_gap.index
                for (s, e) in _relevant:
                    _hit = _gap_idx[(_gap_idx >= s) & (_gap_idx <= e)]
                    if len(_hit) == 0:
                        _mark_dead_gap(symbol, timeframe,
                                        int(s.timestamp()),
                                        int(e.timestamp()))
                df = pd.concat([df, df_gap])
                df = (df[~df.index.duplicated(keep='last')]
                        .sort_index())
                _gaps_filled = len(_relevant)
                _bars_fetched = len(df) - _n_before
                try:
                    df.to_parquet(fp)
                    _CACHE_HEALTH['files_saved'] += 1
                except Exception as e:
                    log.debug(f"[Cache-Health] {symbol} save failed: {e}")
            else:
                # Every candidate gap returned nothing → mark all dead
                for (s, e) in _relevant:
                    _mark_dead_gap(symbol, timeframe,
                                    int(s.timestamp()),
                                    int(e.timestamp()))'''

patch(OLD1, NEW1, "_load_cached: filter + mark dead gaps")

# ═══════════════════════════════════════════════════════════════
# 3. _log_cache_health — log at INFO only if bars were added
# ═══════════════════════════════════════════════════════════════
OLD2 = '''    if gaps_filled > 0:
        log.info(f"[Cache-Health] {symbol} {timeframe}: "
                 f"filled {bars_fetched} bar(s) across "
                 f"{gaps_filled} gap(s) — network fetch")'''

NEW2 = '''    if gaps_filled > 0:
        if bars_fetched > 0:
            log.info(f"[Cache-Health] {symbol} {timeframe}: "
                     f"filled {bars_fetched} bar(s) across "
                     f"{gaps_filled} gap(s) — network fetch")
        else:
            log.debug(f"[Cache-Health] {symbol} {timeframe}: "
                      f"{gaps_filled} gap(s) confirmed dead "
                      f"(exchange has no data)")'''

patch(OLD2, NEW2, "_log_cache_health: softer log for dead gaps")

# ═══════════════════════════════════════════════════════════════
# 4. Clear-cache: also wipe the dead-gaps file
# ═══════════════════════════════════════════════════════════════
OLD3 = '''            "reversal_watchers_live.json",
            "reversal_watchers_testnet.json",
            "kill_switch.json",'''
NEW3 = '''            "reversal_watchers_live.json",
            "reversal_watchers_testnet.json",
            "cache_dead_gaps.json",
            "kill_switch.json",'''

patch(OLD3, NEW3, "clear-cache: also wipe cache_dead_gaps.json",
      required=False)

# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
if s == orig:
    print("⚠  No changes applied:", file=sys.stderr)
    for line in report:
        print("   " + line, file=sys.stderr)
    sys.exit(2)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 68)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 68)
for line in report:
    print("   " + line)
print("═" * 68)
