#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_leverage_tiers.py
=====================
Proper symbol-aware leverage tier snapping.

Replaces the hardcoded FIX-01 (which used a fixed tuple) with:
  * Live:    queries exchange.fetch_leverage_tiers([sym]) per symbol
  * Backtest: prefetches all symbols' tiers during data-load phase
  * Fallback: standard Binance ladder clipped to [LEVERAGE_MIN, LEVERAGE_MAX]

Affects:
  * compute_dynamic_leverage        (new signature: + symbol)
  * compute_max_leverage_by_liq     (new signature: + symbol)
  * ensure_symbol_setup             (snaps target to actual max)
  * simulate_portfolio              (passes symbol=sym)
  * run_live                        (passes symbol=sym)
  * run_backtest                    (prefetches all tiers)
"""

import argparse
import os
import re
import sys
from datetime import datetime


# ═════════════════════════════════════════════════════════════════
# Utils
# ═════════════════════════════════════════════════════════════════

def replace_once(src, old, new, tag, verbose=True):
    if old not in src:
        if verbose:
            print(f"   ⚠️  [{tag}] anchor not found")
        return src, False
    cnt = src.count(old)
    if cnt > 1 and verbose:
        print(f"   ⚠️  [{tag}] anchor appears {cnt}× — replacing first")
    src = src.replace(old, new, 1)
    if verbose:
        print(f"   ✅ [{tag}]")
    return src, True


def insert_before(src, anchor, block, tag, verbose=True):
    """Insert block before the FIRST occurrence of anchor."""
    idx = src.find(anchor)
    if idx < 0:
        if verbose:
            print(f"   ⚠️  [{tag}] anchor not found")
        return src, False
    src = src[:idx] + block + src[idx:]
    if verbose:
        print(f"   ✅ [{tag}]")
    return src, True


def insert_after(src, anchor, block, tag, verbose=True):
    idx = src.find(anchor)
    if idx < 0:
        if verbose:
            print(f"   ⚠️  [{tag}] anchor not found")
        return src, False
    end = idx + len(anchor)
    src = src[:end] + block + src[end:]
    if verbose:
        print(f"   ✅ [{tag}]")
    return src, True


# ═════════════════════════════════════════════════════════════════
# Edit 1: Add global tier cache + helpers after _BINANCE_LEVERAGE_TIERS
# ═════════════════════════════════════════════════════════════════

# We need to find the exact definition of _BINANCE_LEVERAGE_TIERS.
# From the earlier diagnostic, it's:
#   _BINANCE_LEVERAGE_TIERS = (1, 2, 3, 5, 10, 20, 25, 50, 75, 100, 125)

def edit_1_add_cache(src):
    anchor = "_BINANCE_LEVERAGE_TIERS = (1, 2, 3, 5, 10, 20, 25, 50, 75, 100, 125)"
    if anchor not in src:
        # try regex
        m = re.search(
            r"^_BINANCE_LEVERAGE_TIERS\s*=\s*\([^)]*\)\s*$",
            src, re.MULTILINE
        )
        if not m:
            print("   ❌ cannot locate _BINANCE_LEVERAGE_TIERS")
            return src, False
        anchor = m.group(0)

    block = anchor + '''


# ═════════════════════════════════════════════════════════════════
# [FIX-01-PROPER] Per-symbol leverage tiers
# ═════════════════════════════════════════════════════════════════
# Cache:  symbol → (max_leverage, [valid_tiers])
# Populated:
#   * Live:     lazily inside ensure_symbol_setup()
#   * Backtest: eagerly inside prefetch_all_leverage_tiers()
# Fallback:   standard Binance ladder clipped to cfg.LEVERAGE_MAX.
# ═════════════════════════════════════════════════════════════════

_SYMBOL_LEV_TIERS: Dict[str, Tuple[int, List[int]]] = {}

# Static fallback table for well-known symbols. Used when the exchange
# cannot be queried (offline backtest with cached data, etc.).
_STATIC_MAX_LEVERAGE: Dict[str, int] = {
    "BTC/USDT": 125,  "ETH/USDT": 100,  "BNB/USDT": 75,
    "SOL/USDT": 50,   "XRP/USDT": 50,   "DOGE/USDT": 50,
    "ADA/USDT": 50,   "AVAX/USDT": 50,  "LINK/USDT": 50,
    "DOT/USDT": 50,   "LTC/USDT": 50,   "UNI/USDT": 50,
    "ATOM/USDT": 50,  "ETC/USDT": 50,   "TRX/USDT": 50,
    "TON/USDT": 50,   "BCH/USDT": 50,   "NEAR/USDT": 50,
    "APT/USDT": 50,   "HBAR/USDT": 50,  "AAVE/USDT": 50,
    "ARB/USDT": 50,   "OP/USDT": 50,    "SUI/USDT": 50,
    "TIA/USDT": 50,   "SEI/USDT": 50,   "ALGO/USDT": 50,
    "GRT/USDT": 50,   "FET/USDT": 50,   "RENDER/USDT": 50,
    "LDO/USDT": 50,   "KAS/USDT": 50,   "WIF/USDT": 50,
    "THETA/USDT": 50, "SAND/USDT": 50,  "MANA/USDT": 50,
    "AXS/USDT": 50,   "XLM/USDT": 50,   "CHZ/USDT": 50,
    "POL/USDT": 50,   "FIL/USDT": 50,   "QNT/USDT": 50,
    "DASH/USDT": 50,  "STX/USDT": 50,   "MKR/USDT": 50,
}


def _standard_ladder(max_lev: int) -> List[int]:
    """Binance's standard leverage ladder clipped to max_lev."""
    ladder = (1, 2, 3, 5, 10, 20, 25, 50, 75, 100, 125)
    out = [t for t in ladder if t <= int(max_lev)]
    if not out:
        out = [int(max_lev)]
    return out


def _register_leverage_tiers(symbol: str, max_lev: int) -> None:
    """Cache the max leverage and valid tiers for a symbol."""
    max_lev = int(max_lev)
    if max_lev <= 0:
        return
    _SYMBOL_LEV_TIERS[symbol] = (max_lev, _standard_ladder(max_lev))


def _fallback_max_leverage(symbol: str, cfg) -> int:
    """Static fallback when the exchange is not available."""
    if symbol in _STATIC_MAX_LEVERAGE:
        return _STATIC_MAX_LEVERAGE[symbol]
    # Unknown symbol — use the conservative default
    return int(getattr(cfg, 'LEVERAGE_MAX', 50))


def _symbol_tiers(symbol: Optional[str], cfg) -> List[int]:
    """
    Return the valid leverage ladder for a symbol.
    Priority: cache → static table → standard ladder clipped to cfg.LEVERAGE_MAX.
    """
    if symbol and symbol in _SYMBOL_LEV_TIERS:
        return list(_SYMBOL_LEV_TIERS[symbol][1])
    if symbol:
        max_lev = _fallback_max_leverage(symbol, cfg)
        return _standard_ladder(max_lev)
    # No symbol — use CFG.LEVERAGE_MAX as the upper bound
    return _standard_ladder(int(getattr(cfg, 'LEVERAGE_MAX', 50)))


def fetch_symbol_leverage_tiers(exchange, symbol: str) -> Optional[int]:
    """
    Query the exchange for a symbol's max leverage.
    Returns the max leverage (int) or None on failure.
    """
    try:
        tiers = exchange.fetch_leverage_tiers([symbol])
        if not tiers or len(tiers) == 0:
            return None
        t0 = tiers[0]
        tier_list = t0.get('tiers') or []
        if not tier_list:
            return None
        # Binance returns the smallest-notional tier first,
        # which carries the highest leverage.
        max_lev = int(tier_list[0].get('maxLeverage', 0))
        return max_lev if max_lev > 0 else None
    except Exception as e:
        log.debug(f"[LevTiers] fetch failed for {symbol}: {e}")
        return None


def prefetch_all_leverage_tiers(exchange, symbols: List[str]) -> int:
    """
    Populate _SYMBOL_LEV_TIERS for a batch of symbols.
    Called from run_backtest and run_live once at startup.
    Returns count of successfully resolved symbols.
    """
    n_ok = 0
    for sym in symbols:
        if sym in _SYMBOL_LEV_TIERS:
            n_ok += 1
            continue
        max_lev = fetch_symbol_leverage_tiers(exchange, sym)
        if max_lev is not None:
            _register_leverage_tiers(sym, max_lev)
            n_ok += 1
        else:
            fb = _fallback_max_leverage(sym, CFG)
            _register_leverage_tiers(sym, fb)
            log.debug(f"[LevTiers] {sym} using fallback max={fb}x")
    log.info(f"[LevTiers] prefetched tiers for {n_ok}/{len(symbols)} symbols")
    return n_ok
'''

    return replace_once(src, anchor, block, "Edit-1-cache")


# ═════════════════════════════════════════════════════════════════
# Edit 2: Rewrite compute_dynamic_leverage
# ═════════════════════════════════════════════════════════════════

def edit_2_dynamic_leverage(src):
    # Match the whole function
    pattern = re.compile(
        r"def compute_dynamic_leverage\(capital, cfg\):\n"
        r"(?:[ ]{4}.*\n|\n)*?"
        r"(?=\n\S|\nclass |\ndef |\Z)",
        re.MULTILINE
    )
    m = pattern.search(src)
    if not m:
        print("   ❌ compute_dynamic_leverage not found")
        return src, False

    new_fn = '''def compute_dynamic_leverage(capital, cfg, symbol=None):
    """
    Dynamic leverage: Lev(C) = LEVERAGE_BASE / √(C/C₀)

    [FIX-01-PROPER] Snap to the symbol's actual valid tiers:
      * If `symbol` is provided and cached → use its tiers
      * Otherwise → fallback ladder clipped to [LEVERAGE_MIN, LEVERAGE_MAX]

    The snap prevents Binance's -4028 (invalid leverage) rejection
    without hardcoding a single global tuple.
    """
    C0 = max(float(cfg.INITIAL_CAPITAL), 1e-9)
    raw_lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    raw_lev = int(np.clip(round(raw_lev),
                          cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))

    # Get the symbol's valid ladder
    tiers = _symbol_tiers(symbol, cfg)

    # Clip to [LEVERAGE_MIN, LEVERAGE_MAX]
    lo = int(cfg.LEVERAGE_MIN)
    hi = int(cfg.LEVERAGE_MAX)
    valid = [int(t) for t in tiers if lo <= int(t) <= hi]
    if not valid:
        return lo

    # Snap to closest tier ≤ raw_lev
    below = [t for t in valid if t <= raw_lev]
    if below:
        return int(below[-1])
    return int(valid[0])


'''
    src = src[:m.start()] + new_fn + src[m.end():]
    print(f"   ✅ [Edit-2-dynamic-leverage] function replaced")
    return src, True


# ═════════════════════════════════════════════════════════════════
# Edit 3: Update compute_max_leverage_by_liq to accept symbol
# ═════════════════════════════════════════════════════════════════

def edit_3_max_lev_by_liq(src):
    pattern = re.compile(
        r"def compute_max_leverage_by_liq\(sl_frac_max: float, mmr: float,\n"
        r"\s+safety_mult: float = 1\.5\) -> int:\n"
        r"(?:[ ]{4}.*\n|\n)*?"
        r"(?=\n\S|\nclass |\ndef |\Z)",
        re.MULTILINE
    )
    m = pattern.search(src)
    if not m:
        print("   ❌ compute_max_leverage_by_liq not found")
        return src, False

    new_fn = '''def compute_max_leverage_by_liq(sl_frac_max: float, mmr: float,
                                  safety_mult: float = 1.5,
                                  symbol: Optional[str] = None) -> int:
    """
    Max leverage such that: sl_gap × safety_mult < liq_gap.

    [FIX-01-PROPER] When `symbol` is given, snap to that symbol's
    actual tiers. Falls back to the standard ladder otherwise.
    """
    s = max(sl_frac_max * safety_mult, 1e-6)
    m = max(float(mmr), 0.0)
    denom = 1.0 - (1.0 - m) * (1.0 - s)
    if denom <= 1e-9:
        return 1
    _raw = int(np.floor(1.0 / denom))

    # Symbol-aware ladder
    try:
        tiers = _symbol_tiers(symbol, CFG)
    except Exception:
        tiers = list(_BINANCE_LEVERAGE_TIERS)
    _candidates = [int(t) for t in tiers if int(t) <= _raw]
    if not _candidates:
        return 1
    return int(_candidates[-1])


'''
    src = src[:m.start()] + new_fn + src[m.end():]
    print(f"   ✅ [Edit-3-max-lev-by-liq] function replaced")
    return src, True


# ═════════════════════════════════════════════════════════════════
# Edit 4: ensure_symbol_setup — snap target to actual max
# ═════════════════════════════════════════════════════════════════

def edit_4_ensure_setup_snap(src):
    """
    Insert a block at the top of ensure_symbol_setup that:
      1. Queries max leverage for the symbol (cached)
      2. Snaps target_leverage to a valid tier ≤ max_lev
    """
    anchor = '''def ensure_symbol_setup(exchange, sym: str, target_leverage: int,
                        margin_mode: str = 'isolated') -> bool:'''
    if anchor not in src:
        print("   ❌ ensure_symbol_setup signature not found")
        return src, False

    # Find the docstring that follows
    idx = src.find(anchor)
    if idx < 0:
        return src, False

    # find the end of the docstring """...""" 
    doc_start = src.find('"""', idx)
    doc_end = src.find('"""', doc_start + 3)
    if doc_start < 0 or doc_end < 0:
        print("   ❌ cannot locate docstring")
        return src, False

    insert_at = doc_end + 3  # after closing """

    # We'll insert a block that snaps target_leverage
    snap_block = '''

    # ══ [FIX-01-PROPER] Snap target to the symbol's actual tiers ══
    try:
        if sym not in _SYMBOL_LEV_TIERS:
            _max_lev = fetch_symbol_leverage_tiers(exchange, sym)
            if _max_lev is None:
                _max_lev = _fallback_max_leverage(sym, CFG)
            _register_leverage_tiers(sym, _max_lev)
            log.debug(f"[Setup] {sym} max_leverage={_max_lev}x cached")

        _tiers_for_sym = _SYMBOL_LEV_TIERS[sym][1]
        _snapped = [t for t in _tiers_for_sym
                    if int(t) <= int(target_leverage)]
        if _snapped:
            _new_lev = int(_snapped[-1])
        else:
            _new_lev = int(_tiers_for_sym[0]) if _tiers_for_sym else 1

        if _new_lev != int(target_leverage):
            log.info(f"[Setup] {sym} snap leverage "
                     f"{target_leverage}x → {_new_lev}x "
                     f"(max={_SYMBOL_LEV_TIERS[sym][0]}x)")
            target_leverage = _new_lev
    except Exception as _e:
        log.warning(f"[Setup] {sym} snap failed: {_e} — "
                    f"using target as-is")
'''

    src = src[:insert_at] + snap_block + src[insert_at:]
    print(f"   ✅ [Edit-4-setup-snap] block inserted")
    return src, True


# ═════════════════════════════════════════════════════════════════
# Edit 5: Call prefetch in run_backtest
# ═════════════════════════════════════════════════════════════════

def edit_5_prefetch_backtest(src):
    # Insert prefetch after fetch_all_with_subbars returns
    anchor = '    raw, raw_sub = fetch_all_with_subbars('
    idx = src.find(anchor)
    if idx < 0:
        print("   ⚠️  [Edit-5] fetch_all_with_subbars call not found")
        return src, False

    # Find the end of this statement (next line starting with same or less indent)
    # Simpler: find the line after the closing `)` of the call.
    # The call spans multiple lines: 
    #   raw, raw_sub = fetch_all_with_subbars(
    #       syms, exchange, cfg.timeframe, cfg.history_days, workers=5
    #   )
    # So we look for the "\n    )\n" after idx.
    end_marker = "\n    )\n"
    end_idx = src.find(end_marker, idx)
    if end_idx < 0:
        print("   ⚠️  [Edit-5] cannot find end of fetch_all_with_subbars call")
        return src, False

    insert_at = end_idx + len(end_marker)

    block = '''
    # ══ [FIX-01-PROPER] Prefetch leverage tiers for all symbols ══
    try:
        prefetch_all_leverage_tiers(exchange, list(raw.keys()))
    except Exception as _e:
        log.warning(f"[LevTiers] backtest prefetch failed: {_e}")

'''
    src = src[:insert_at] + block + src[insert_at:]
    print(f"   ✅ [Edit-5-prefetch-backtest] block inserted")
    return src, True


# ═════════════════════════════════════════════════════════════════
# Edit 6: Call prefetch in run_live
# ═════════════════════════════════════════════════════════════════

def edit_6_prefetch_live(src):
    # After `cached_data = fetch_all(top_syms, exchange, cfg.timeframe, days=_live_history_days, workers=5)`
    anchor = "cached_data = fetch_all(top_syms, exchange, cfg.timeframe,\n                            days=_live_history_days, workers=5)"
    idx = src.find(anchor)
    if idx < 0:
        print("   ⚠️  [Edit-6] cached_data assignment not found")
        return src, False

    insert_at = idx + len(anchor)

    block = '''

    # ══ [FIX-01-PROPER] Prefetch leverage tiers for all live symbols ══
    try:
        prefetch_all_leverage_tiers(exchange, list(cached_data.keys()))
    except Exception as _e:
        log.warning(f"[LevTiers] live prefetch failed: {_e}")
'''

    src = src[:insert_at] + block + src[insert_at:]
    print(f"   ✅ [Edit-6-prefetch-live] block inserted")
    return src, True


# ═════════════════════════════════════════════════════════════════
# Edit 7: compute_dynamic_leverage calls (in simulate_portfolio + run_live)
# ═════════════════════════════════════════════════════════════════

def edit_7_dynamic_calls(src):
    n_total = 0

    # Call in simulate_portfolio
    old1 = "dynamic_leverage = compute_dynamic_leverage(capital, CFG)"
    new1 = "dynamic_leverage = compute_dynamic_leverage(capital, CFG, symbol=sym)"
    if old1 in src:
        src = src.replace(old1, new1, 1)
        print(f"   ✅ [Edit-7a] simulate_portfolio call updated")
        n_total += 1
    else:
        print(f"   ⚠️  [Edit-7a] simulate_portfolio call pattern not found")

    # Call in run_live
    old2 = "dynamic_leverage = compute_dynamic_leverage(cap_live, cfg)"
    new2 = "dynamic_leverage = compute_dynamic_leverage(cap_live, cfg, symbol=sym)"
    if old2 in src:
        src = src.replace(old2, new2, 1)
        print(f"   ✅ [Edit-7b] run_live call updated")
        n_total += 1
    else:
        print(f"   ⚠️  [Edit-7b] run_live call pattern not found")

    return src, n_total > 0


# ═════════════════════════════════════════════════════════════════
# Edit 8: compute_max_leverage_by_liq calls
# ═════════════════════════════════════════════════════════════════

def edit_8_max_lev_calls(src):
    n_total = 0

    # Both backtest and live use the same call pattern.
    # Pattern 1 (in simulate_portfolio):
    #   _lev_by_liq = compute_max_leverage_by_liq(
    #       sl_frac_max=_sl_frac_max,
    #       mmr=_mmr,
    #       safety_mult=float(CFG.LIQ_SAFETY_MULT),
    #   )

    old_pat = """            _lev_by_liq = compute_max_leverage_by_liq(
                sl_frac_max=_sl_frac_max,
                mmr=_mmr,
                safety_mult=float(CFG.LIQ_SAFETY_MULT),
            )"""
    new_pat = """            _lev_by_liq = compute_max_leverage_by_liq(
                sl_frac_max=_sl_frac_max,
                mmr=_mmr,
                safety_mult=float(CFG.LIQ_SAFETY_MULT),
                symbol=sym,
            )"""

    if old_pat in src:
        src = src.replace(old_pat, new_pat, 1)
        print(f"   ✅ [Edit-8a] backtest LevCap call updated")
        n_total += 1

    # Live version has different indentation
    old_live = """                        _lev_by_liq = compute_max_leverage_by_liq(
                            sl_frac_max=_sl_frac_max,
                            mmr=_mmr_sig,
                            safety_mult=float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5)),
                        )"""
    new_live = """                        _lev_by_liq = compute_max_leverage_by_liq(
                            sl_frac_max=_sl_frac_max,
                            mmr=_mmr_sig,
                            safety_mult=float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5)),
                            symbol=sym,
                        )"""
    if old_live in src:
        src = src.replace(old_live, new_live, 1)
        print(f"   ✅ [Edit-8b] live LevCap call updated")
        n_total += 1

    # Fallback: try regex-based for any remaining occurrence
    # (in case indentation differs)
    if n_total == 0:
        print(f"   ⚠️  [Edit-8] exact patterns not found — trying regex")
        # Regex approach: find any compute_max_leverage_by_liq call with safety_mult,
        # and add symbol=sym before the closing paren.
        pattern = re.compile(
            r"(compute_max_leverage_by_liq\(\s*\n"
            r"(?:\s+[a-z_]+=[^,\n]+,?\s*\n)+?)"
            r"(\s*\))",
            re.MULTILINE
        )
        def repl(m):
            inner = m.group(1)
            if "symbol=" in inner:
                return m.group(0)
            # Detect indent of last kwarg
            lines = inner.rstrip().split('\n')
            last_line = lines[-1]
            indent = len(last_line) - len(last_line.lstrip())
            pad = " " * indent
            # Remove trailing comma if present, add new kwarg
            return inner.rstrip().rstrip(',') + ',\n' + pad + 'symbol=sym,\n' + pad + m.group(2).lstrip()
        new_src, n = pattern.subn(repl, src)
        if n > 0:
            src = new_src
            print(f"   ✅ [Edit-8] regex applied to {n} call(s)")
            n_total += n

    return src, n_total > 0


# ═════════════════════════════════════════════════════════════════
# Verification
# ═════════════════════════════════════════════════════════════════

def verify(src):
    print()
    print("╔" + "═" * 62 + "╗")
    print("║" + " VERIFICATION ".center(62) + "║")
    print("╚" + "═" * 62 + "╝")

    checks = {
        "_SYMBOL_LEV_TIERS defined":
            "_SYMBOL_LEV_TIERS: Dict[str, Tuple[int, List[int]]] = {}",
        "_STATIC_MAX_LEVERAGE table":
            "_STATIC_MAX_LEVERAGE: Dict[str, int]",
        "_standard_ladder helper":
            "def _standard_ladder(",
        "_symbol_tiers helper":
            "def _symbol_tiers(",
        "fetch_symbol_leverage_tiers":
            "def fetch_symbol_leverage_tiers(",
        "prefetch_all_leverage_tiers":
            "def prefetch_all_leverage_tiers(",
        "compute_dynamic_leverage signature":
            "def compute_dynamic_leverage(capital, cfg, symbol=None):",
        "compute_max_leverage_by_liq signature":
            "def compute_max_leverage_by_liq(sl_frac_max: float, mmr: float,",
        "ensure_symbol_setup snap block":
            "[FIX-01-PROPER] Snap target to the symbol's actual tiers",
        "prefetch in backtest":
            "[FIX-01-PROPER] Prefetch leverage tiers for all symbols",
        "prefetch in live":
            "[FIX-01-PROPER] Prefetch leverage tiers for all live symbols",
        "dynamic call - simulate_portfolio":
            "compute_dynamic_leverage(capital, CFG, symbol=sym)",
        "dynamic call - run_live":
            "compute_dynamic_leverage(cap_live, cfg, symbol=sym)",
    }

    # Additional check: number of compute_max_leverage_by_liq calls with symbol=
    cmb_calls = src.count("symbol=sym")
    print(f"   total `symbol=sym` kwarg occurrences: {cmb_calls}")
    print()

    all_ok = True
    for name, marker in checks.items():
        ok = marker in src
        icon = "✅" if ok else "❌"
        print(f"   {icon} {name}")
        if not ok:
            all_ok = False

    # Ensure NO leftover of the OLD hardcoded snap
    old_snap = "# Snap to Binance valid tier"
    if old_snap in src:
        print(f"   ⚠️  OLD FIX-01 hardcoded snap still present")
    else:
        print(f"   ✅ OLD FIX-01 hardcoded snap removed")

    print()
    return all_ok


# ═════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="trading_2_release.py")
    ap.add_argument("--output", default="trading_2_final_lev.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ {args.input} not found")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    n0 = len(src)
    print(f"📖 Loaded {args.input} ({n0:,} bytes)\n")

    print("╔" + "═" * 62 + "╗")
    print("║" + " APPLYING FIX-01-PROPER ".center(62) + "║")
    print("╚" + "═" * 62 + "╝")

    results = {}

    print("\n▶ Edit 1: add global tier cache + helpers")
    src, ok = edit_1_add_cache(src); results['Edit 1'] = ok

    print("\n▶ Edit 2: rewrite compute_dynamic_leverage")
    src, ok = edit_2_dynamic_leverage(src); results['Edit 2'] = ok

    print("\n▶ Edit 3: rewrite compute_max_leverage_by_liq")
    src, ok = edit_3_max_lev_by_liq(src); results['Edit 3'] = ok

    print("\n▶ Edit 4: ensure_symbol_setup — snap to actual max")
    src, ok = edit_4_ensure_setup_snap(src); results['Edit 4'] = ok

    print("\n▶ Edit 5: prefetch in run_backtest")
    src, ok = edit_5_prefetch_backtest(src); results['Edit 5'] = ok

    print("\n▶ Edit 6: prefetch in run_live")
    src, ok = edit_6_prefetch_live(src); results['Edit 6'] = ok

    print("\n▶ Edit 7: update compute_dynamic_leverage call sites")
    src, ok = edit_7_dynamic_calls(src); results['Edit 7'] = ok

    print("\n▶ Edit 8: update compute_max_leverage_by_liq call sites")
    src, ok = edit_8_max_lev_calls(src); results['Edit 8'] = ok

    # Verify
    verify_ok = verify(src)

    # Syntax
    print("╔" + "═" * 62 + "╗")
    print("║" + " SYNTAX CHECK ".center(62) + "║")
    print("╚" + "═" * 62 + "╝")
    try:
        compile(src, args.output, "exec")
        print(f"   ✅ compiles OK")
    except SyntaxError as e:
        print(f"   ❌ SyntaxError at line {e.lineno}: {e.msg}")
        print(f"      {e.text}")
        sys.exit(2)

    # Header + write
    header = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  {os.path.basename(args.output)}
#  Quantum Thermodynamic Trading Engine
#  FIX-01-PROPER (symbol-aware leverage tiers)
#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
#  Base: {args.input}
#
#  What changed vs previous FIX-01:
#    BEFORE: hardcoded tuple (1,2,3,5,10,20,25,50,75,100,125)
#            applied uniformly to every symbol — often wrong for
#            alt coins whose max leverage is 25x or 20x.
#
#    AFTER:
#      * Live: query exchange.fetch_leverage_tiers([sym]) once per
#        symbol, cache the result, and snap only to those tiers.
#      * Backtest: prefetch all tiers during data-loading phase.
#      * Fallback: static table for well-known symbols; conservative
#        LEVERAGE_MAX otherwise.
#      * LevCap (compute_max_leverage_by_liq) also symbol-aware.
#      * ensure_symbol_setup snaps its target BEFORE calling
#        set_leverage, eliminating -4028 completely.
# ════════════════════════════════════════════════════════════════════
"""
    if src.startswith("#!"):
        first_nl = src.index("\n")
        src = header + src[first_nl+1:]
    else:
        src = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src)

    n1 = len(src)
    print()
    print("╔" + "═" * 62 + "╗")
    print("║" + " DONE ".center(62) + "║")
    print("╚" + "═" * 62 + "╝")
    print(f"   Input:  {args.input}  ({n0:,} bytes)")
    print(f"   Output: {args.output} ({n1:,} bytes)")

    n_ok = sum(1 for v in results.values() if v)
    if n_ok == len(results) and verify_ok:
        print(f"\n   ✅ All {len(results)} edits applied successfully")
        print(f"   ▶ Run:")
        print(f"     python {args.output} --mode backtest ...")
        print(f"     python {args.output} --mode testnet --api-key ... "
              f"--api-secret ...")
        sys.exit(0)
    else:
        print(f"\n   ⚠️  {n_ok}/{len(results)} edits succeeded, "
              f"verify={verify_ok}")
        for name, ok in results.items():
            if not ok:
                print(f"     - {name} failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
