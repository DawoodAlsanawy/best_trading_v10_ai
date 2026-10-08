#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_live2_ccxt4.py                                                    ║
║  Comprehensive ccxt 4.x fix for trading_2_live2.py                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Fixes applied (12 patches):                                             ║
║   P1   Insert tier infrastructure (helpers + caches + functions)         ║
║   P2   Replace _get_mmr_for_symbol       (dict-shape)                    ║
║   P3   Replace compute_max_leverage_by_liq (symbol-aware)                ║
║   P4   Replace compute_dynamic_leverage   (symbol-aware)                 ║
║   P5a  Insert tier-snap in ensure_symbol_setup                           ║
║   P5b  Fix has_pos branch (None-safe fetch_leverage)                     ║
║   P6   Add prefetch call in run_backtest                                 ║
║   P7   Add prefetch call in run_live                                     ║
║   P8a  Update compute_dynamic_leverage(capital, CFG) call                ║
║   P8b  Update compute_dynamic_leverage(cap_live, cfg) call               ║
║   P9a  Add symbol= to first compute_max_leverage_by_liq call             ║
║   P9b  Add symbol= to second compute_max_leverage_by_liq call            ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 patch_live2_ccxt4.py                    # apply                ║
║    python3 patch_live2_ccxt4.py --dry-run          # preview              ║
║    python3 patch_live2_ccxt4.py --bot PATH         # custom path          ║
║    python3 patch_live2_ccxt4.py --restore          # rollback             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    END = '\033[0m'


# ══════════════════════════════════════════════════════════════════════════
# P1 — Insert tier infrastructure block
# ══════════════════════════════════════════════════════════════════════════

P1_ANCHOR = "_MMR_CACHE: Dict[str, float] = {}\n\n\ndef _get_mmr_for_symbol"

P1_INSERTED = '''_MMR_CACHE: Dict[str, float] = {}


# ═════════════════════════════════════════════════════════════════════
# [ccxt 4.x FIX] Per-symbol leverage tier infrastructure
# ═════════════════════════════════════════════════════════════════════
#
# Problem solved:
#   ccxt >= 4.x returns fetch_leverage_tiers() as a DICT keyed by symbol
#   (e.g. {"BTC/USDT:USDT": {...}}) instead of the older LIST shape.
#   The old code assumed a list (tiers[0]) → KeyError: 0 on every call.
#   Effect: _SYMBOL_LEV_TIERS never populated, MMR always fell through
#   to the conservative 2% fallback → LevCap used wrong values.
#
# Solution:
#   * _extract_tier_entry() normalizes both list and dict shapes.
#   * _SYMBOL_LEV_TIERS caches (max_lev, [valid_tiers]) per symbol.
#   * All tier-consuming code paths route through _symbol_tiers().
# ═════════════════════════════════════════════════════════════════════

_SYMBOL_LEV_TIERS: Dict[str, Tuple[int, List[int]]] = {}

# Static fallback table for well-known symbols (used when exchange
# is unreachable or the symbol is not yet cached).
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
    "DASH/USDT": 50,  "STX/USDT": 50,
}


def _extract_tier_entry(tiers_raw, symbol: str) -> Optional[Dict]:
    """
    [ccxt 4.x FIX] Normalize fetch_leverage_tiers output across versions.

    Shapes observed:
      A) list[ {symbol, tiers:[...]}, ... ]        (older ccxt)
      B) dict[ symbol_str, {tiers:[...]} ]         (ccxt >= 4.x, common)
      C) dict[ symbol_str, [tier_dict, ...] ]      (rare third-party)

    Returns a single entry dict with a 'tiers' key, or None on failure.
    """
    if not tiers_raw:
        return None

    def _sym_match(a: str, b: str) -> bool:
        if not a or not b:
            return False
        return a.split(':')[0] == b.split(':')[0]

    def _wrap(v):
        if isinstance(v, dict):
            return v
        if isinstance(v, list):
            return {'symbol': symbol, 'tiers': v}
        return None

    # Case A: list
    if isinstance(tiers_raw, list):
        if len(tiers_raw) == 0:
            return None
        for entry in tiers_raw:
            if isinstance(entry, dict) and _sym_match(
                    entry.get('symbol', ''), symbol):
                return entry
        first = tiers_raw[0]
        return first if isinstance(first, dict) else None

    # Case B / C: dict
    if isinstance(tiers_raw, dict):
        if symbol in tiers_raw:
            return _wrap(tiers_raw[symbol])
        for k, v in tiers_raw.items():
            if _sym_match(k, symbol):
                return _wrap(v)
        if len(tiers_raw) > 0:
            k = next(iter(tiers_raw))
            return _wrap(tiers_raw[k])

    return None


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
    return int(getattr(cfg, 'LEVERAGE_MAX', 50))


def _symbol_tiers(symbol: Optional[str], cfg) -> List[int]:
    """
    Return the valid leverage ladder for a symbol.
    Priority: cache → static table → standard ladder clipped to
    cfg.LEVERAGE_MAX.
    """
    if symbol and symbol in _SYMBOL_LEV_TIERS:
        return list(_SYMBOL_LEV_TIERS[symbol][1])
    if symbol:
        max_lev = _fallback_max_leverage(symbol, cfg)
        return _standard_ladder(max_lev)
    return _standard_ladder(int(getattr(cfg, 'LEVERAGE_MAX', 50)))


def fetch_symbol_leverage_tiers(exchange, symbol: str) -> Optional[int]:
    """
    Query the exchange for a symbol's max leverage.

    [ccxt 4.x FIX] Uses _extract_tier_entry() to handle both list and
    dict return shapes. Before the fix, `tiers[0]` raised KeyError: 0
    when the exchange returned a dict (ccxt 4.x default).

    Returns the max leverage (int) or None on failure.
    """
    try:
        tiers_raw = exchange.fetch_leverage_tiers([symbol])
        entry = _extract_tier_entry(tiers_raw, symbol)
        if entry is None:
            return None
        tier_list = entry.get('tiers') or []
        if not tier_list:
            return None
        max_lev = int(tier_list[0].get('maxLeverage', 0))
        return max_lev if max_lev > 0 else None
    except Exception as e:
        log.debug(f"[LevTiers] fetch failed for {symbol}: {e}")
        return None


def prefetch_all_leverage_tiers(exchange, symbols: List[str]) -> int:
    """
    Populate _SYMBOL_LEV_TIERS for a batch of symbols.
    Called once at startup from run_backtest / run_live.
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


# ═════════════════════════════════════════════════════════════════════
# [/ccxt 4.x FIX]
# ═════════════════════════════════════════════════════════════════════


def _get_mmr_for_symbol'''


# ══════════════════════════════════════════════════════════════════════════
# P2 — Replace _get_mmr_for_symbol
# ══════════════════════════════════════════════════════════════════════════

P2_OLD = '''def _get_mmr_for_symbol(exchange, symbol: str) -> float:
    """
    Maintenance margin rate for a symbol.
    - Cached per session.
    - Returns tier-0 (smallest notional) MMR, since our positions are small.
    - Falls back to CFG.LIQ_FALLBACK_MMR on any failure.
    """
    if symbol in _MMR_CACHE:
        return _MMR_CACHE[symbol]
    try:
        tiers = exchange.fetch_leverage_tiers([symbol])
        if tiers and len(tiers) > 0:
            t0 = tiers[0]
            tiers_list = t0.get('tiers', []) or []
            if tiers_list:
                mmr = float(tiers_list[0].get('maintenanceMarginRate', 0))
                if mmr > 0:
                    _MMR_CACHE[symbol] = mmr
                    return mmr
    except Exception as e:
        log.debug(f"[MMR] fetch failed for {symbol}: {e}")
    _MMR_CACHE[symbol] = float(getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
    return _MMR_CACHE[symbol]'''

P2_NEW = '''def _get_mmr_for_symbol(exchange, symbol: str) -> float:
    """
    Maintenance margin rate for a symbol.

    [ccxt 4.x FIX] Uses _extract_tier_entry() to handle dict-shaped
    responses. Before the fix, dict responses silently fell through to
    the fallback MMR, so ALL LevCap / LiqGate calculations used the
    conservative 2% instead of the true per-symbol MMR
    (0.4% for BTC, 1% for alts, etc.).

    - Cached per session.
    - Returns tier-0 (smallest notional) MMR.
    - Falls back to CFG.LIQ_FALLBACK_MMR on any failure.
    """
    if symbol in _MMR_CACHE:
        return _MMR_CACHE[symbol]
    try:
        tiers_raw = exchange.fetch_leverage_tiers([symbol])
        entry = _extract_tier_entry(tiers_raw, symbol)
        if entry is not None:
            tier_list = entry.get('tiers', []) or []
            if tier_list:
                mmr = float(tier_list[0].get('maintenanceMarginRate', 0))
                if mmr > 0:
                    _MMR_CACHE[symbol] = mmr
                    return mmr
    except Exception as e:
        log.debug(f"[MMR] fetch failed for {symbol}: {e}")
    _MMR_CACHE[symbol] = float(getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
    return _MMR_CACHE[symbol]'''


# ══════════════════════════════════════════════════════════════════════════
# P3 — Replace compute_max_leverage_by_liq
# ══════════════════════════════════════════════════════════════════════════

P3_OLD = '''def compute_max_leverage_by_liq(sl_frac_max: float, mmr: float,
                                  safety_mult: float = 1.5) -> int:
    """
    Max leverage such that: sl_gap × safety_mult < liq_gap.

    [TIER-SNAP] يُعاد الرقم من قائمة الرافعات الصالحة على Binance،
    وليس قيمة تعسفية. هذا يمنع set_leverage من الرفض بـ -4028.
    """
    s = max(sl_frac_max * safety_mult, 1e-6)
    m = max(float(mmr), 0.0)
    denom = 1.0 - (1.0 - m) * (1.0 - s)
    if denom <= 1e-9:
        return 1
    _raw = int(np.floor(1.0 / denom))
    _candidates = [t for t in _BINANCE_LEVERAGE_TIERS if t <= _raw]
    if not _candidates:
        return 1
    return int(_candidates[-1])'''

P3_NEW = '''def compute_max_leverage_by_liq(sl_frac_max: float, mmr: float,
                                  safety_mult: float = 1.5,
                                  symbol: Optional[str] = None) -> int:
    """
    Max leverage such that: sl_gap × safety_mult < liq_gap.

    [ccxt 4.x FIX] When `symbol` is given, snap to that symbol's
    actual tiers (from _SYMBOL_LEV_TIERS cache). Falls back to the
    standard ladder otherwise. Prevents -4028 rejections.
    """
    s = max(sl_frac_max * safety_mult, 1e-6)
    m = max(float(mmr), 0.0)
    denom = 1.0 - (1.0 - m) * (1.0 - s)
    if denom <= 1e-9:
        return 1
    _raw = int(np.floor(1.0 / denom))

    try:
        tiers = _symbol_tiers(symbol, CFG)
    except Exception:
        tiers = list(_BINANCE_LEVERAGE_TIERS)
    _candidates = [int(t) for t in tiers if int(t) <= _raw]
    if not _candidates:
        return 1
    return int(_candidates[-1])'''


# ══════════════════════════════════════════════════════════════════════════
# P4 — Replace compute_dynamic_leverage
# ══════════════════════════════════════════════════════════════════════════

P4_OLD = '''def compute_dynamic_leverage(capital, cfg):
    """
    ③ الرافعة الديناميكية تتناقص مع نمو رأس المال:
    
    Lev(C) = LEVERAGE_BASE / √(C / C₀)
    
    فيزيائياً: الجسيم الأثقل (رأس مال أكبر) يتجاهل التقلبات الصغيرة
    → رافعة أقل تعني حماية أكثر عند نمو الثروة.
    """
    C0 = cfg.INITIAL_CAPITAL
    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    return int(np.clip(round(lev), cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))'''

P4_NEW = '''def compute_dynamic_leverage(capital, cfg, symbol=None):
    """
    ③ الرافعة الديناميكية تتناقص مع نمو رأس المال:

        Lev(C) = LEVERAGE_BASE / √(C / C₀)

    فيزيائياً: الجسيم الأثقل (رأس مال أكبر) يتجاهل التقلبات الصغيرة
    → رافعة أقل تعني حماية أكثر عند نمو الثروة.

    [ccxt 4.x FIX] When `symbol` is given, snap the result to the
    symbol's actual valid tiers (avoids -4028).
    """
    C0 = cfg.INITIAL_CAPITAL
    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    raw_lev = int(np.clip(round(lev), cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))

    if symbol is None:
        return raw_lev

    # Snap to symbol's actual ladder
    try:
        tiers = _symbol_tiers(symbol, cfg)
        lo = int(cfg.LEVERAGE_MIN)
        hi = int(cfg.LEVERAGE_MAX)
        valid = [int(t) for t in tiers if lo <= int(t) <= hi]
        if not valid:
            return lo
        below = [t for t in valid if t <= raw_lev]
        if below:
            return int(below[-1])
        return int(valid[0])
    except Exception:
        return raw_lev'''


# ══════════════════════════════════════════════════════════════════════════
# P5a — Insert tier-snap in ensure_symbol_setup (before fast path)
# ══════════════════════════════════════════════════════════════════════════

P5A_ANCHOR = '''    global _SYMBOL_META
    meta = _SYMBOL_META.get(sym, {})

    # Fast path: already set up with matching leverage
    if meta.get('setup_done') and int(meta.get('leverage', 0)) == target_leverage:
        return True'''

P5A_REPLACEMENT = '''    global _SYMBOL_META

    # [ccxt 4.x FIX] Snap target to the symbol's actual tiers BEFORE
    # any decision. Prevents -4028 rejections.
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
                     f"{target_leverage}x -> {_new_lev}x "
                     f"(max={_SYMBOL_LEV_TIERS[sym][0]}x)")
            target_leverage = _new_lev
    except Exception as _e:
        log.warning(f"[Setup] {sym} snap failed: {_e} -- using target as-is")

    meta = _SYMBOL_META.get(sym, {})

    # Fast path: already set up with matching leverage
    if meta.get('setup_done') and int(meta.get('leverage', 0)) == target_leverage:
        return True'''


# ══════════════════════════════════════════════════════════════════════════
# P5b — Fix has_pos branch (None-safe fetch_leverage)
# ══════════════════════════════════════════════════════════════════════════

P5B_OLD = '''    if has_pos:
        # Read current leverage, do NOT change it
        try:
            lev_info = exchange.fetch_leverage(sym)
            cur_lev = int(lev_info.get('leverage', target_leverage))
        except Exception:
            cur_lev = target_leverage'''

P5B_NEW = '''    if has_pos:
        # Read current leverage, do NOT change it
        # [ccxt 4.x FIX] Binance Demo returns None from fetch_leverage.
        # Guard explicitly instead of relying on AttributeError catch.
        try:
            lev_info = exchange.fetch_leverage(sym)
            if lev_info is None or not hasattr(lev_info, 'get'):
                cur_lev = target_leverage
                log.debug(
                    f"[Setup] {sym} fetch_leverage returned "
                    f"{type(lev_info).__name__} -- using target="
                    f"{target_leverage}x"
                )
            else:
                cur_lev = int(lev_info.get('leverage', target_leverage)
                              or target_leverage)
        except Exception as e:
            log.debug(f"[Setup] {sym} fetch_leverage failed: {e}")
            cur_lev = target_leverage'''


# ══════════════════════════════════════════════════════════════════════════
# P6 — Add prefetch in run_backtest
# ══════════════════════════════════════════════════════════════════════════

P6_ANCHOR = '''    if not raw: log.error("لا بيانات."); return
    if raw_sub:'''

P6_REPLACEMENT = '''    if not raw: log.error("لا بيانات."); return

    # [ccxt 4.x FIX] Prefetch leverage tiers for all symbols.
    # This populates _SYMBOL_LEV_TIERS so LevCap and LevSnap work
    # with real values instead of static fallback.
    try:
        prefetch_all_leverage_tiers(exchange, list(raw.keys()))
    except Exception as _e:
        log.warning(f"[LevTiers] backtest prefetch failed: {_e}")

    if raw_sub:'''


# ══════════════════════════════════════════════════════════════════════════
# P7 — Add prefetch in run_live
# ══════════════════════════════════════════════════════════════════════════

P7_ANCHOR = '''    cached_data = fetch_all(top_syms, exchange, cfg.timeframe,
                            days=_live_history_days, workers=5)'''

P7_REPLACEMENT = '''    cached_data = fetch_all(top_syms, exchange, cfg.timeframe,
                            days=_live_history_days, workers=5)

    # [ccxt 4.x FIX] Prefetch leverage tiers for all live symbols.
    # Must run AFTER fetch_all so symbols are known, and BEFORE any
    # entry decision so LevCap sees real values.
    try:
        prefetch_all_leverage_tiers(exchange, list(cached_data.keys()))
    except Exception as _e:
        log.warning(f"[LevTiers] live prefetch failed: {_e}")'''


# ══════════════════════════════════════════════════════════════════════════
# P8a — Update compute_dynamic_leverage call in simulate_portfolio
# ══════════════════════════════════════════════════════════════════════════

P8A_OLD = '''        # Leverage cap
        dynamic_leverage = compute_dynamic_leverage(capital, CFG)'''

P8A_NEW = '''        # Leverage cap
        dynamic_leverage = compute_dynamic_leverage(capital, CFG, symbol=sym)'''


# ══════════════════════════════════════════════════════════════════════════
# P8b — Update compute_dynamic_leverage call in run_live
# ══════════════════════════════════════════════════════════════════════════

P8B_OLD = '''                    dynamic_leverage = compute_dynamic_leverage(cap_live, cfg)'''

P8B_NEW = '''                    dynamic_leverage = compute_dynamic_leverage(
                        cap_live, cfg, symbol=sym)'''


# ══════════════════════════════════════════════════════════════════════════
# P9a — Add symbol= to first compute_max_leverage_by_liq call
# ══════════════════════════════════════════════════════════════════════════

P9A_OLD = '''            _lev_by_liq = compute_max_leverage_by_liq(
                sl_frac_max=_sl_frac_max,
                mmr=_mmr,
                safety_mult=float(CFG.LIQ_SAFETY_MULT),
            )'''

P9A_NEW = '''            _lev_by_liq = compute_max_leverage_by_liq(
                sl_frac_max=_sl_frac_max,
                mmr=_mmr,
                safety_mult=float(CFG.LIQ_SAFETY_MULT),
                symbol=sym,
            )'''


# ══════════════════════════════════════════════════════════════════════════
# P9b — Add symbol= to second compute_max_leverage_by_liq call
# ══════════════════════════════════════════════════════════════════════════

P9B_OLD = '''                        _lev_by_liq = compute_max_leverage_by_liq(
                            sl_frac_max=_sl_frac_max,
                            mmr=_mmr_sig,
                            safety_mult=float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5)),
                        )'''

P9B_NEW = '''                        _lev_by_liq = compute_max_leverage_by_liq(
                            sl_frac_max=_sl_frac_max,
                            mmr=_mmr_sig,
                            safety_mult=float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5)),
                            symbol=sym,
                        )'''


# ══════════════════════════════════════════════════════════════════════════
# Patcher
# ══════════════════════════════════════════════════════════════════════════

class Patcher:
    def __init__(self, path: Path, dry_run: bool = False):
        self.path = path
        self.dry_run = dry_run
        self.content = None
        self.backup_path = None
        self.results: List[Tuple[str, str]] = []

    def load(self) -> bool:
        if not self.path.exists():
            print(f"{C.RED}  File not found: {self.path}{C.END}")
            return False
        try:
            self.content = self.path.read_text(encoding='utf-8')
            print(f"{C.CYAN}  Loaded {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Cannot read: {e}{C.END}")
            return False

    def backup(self) -> bool:
        if self.dry_run:
            return True
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = self.path.with_suffix(
            self.path.suffix + f'.bak.{ts}')
        try:
            shutil.copy2(self.path, self.backup_path)
            print(f"{C.CYAN}  Backup: {self.backup_path.name}{C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Backup failed: {e}{C.END}")
            return False

    def replace(self, name: str, old: str, new: str,
                marker: str = None, count: int = 1) -> bool:
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name} "
                  f"{C.GRAY}(already applied){C.END}")
            return True
        n = self.content.count(old)
        if n == 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} "
                  f"{C.GRAY}(anchor not found){C.END}")
            return False
        if count > 0 and n != count:
            print(f"  {C.YELLOW}⚠ WARN{C.END}  {name}: found {n} "
                  f"occurrences (expected {count}) — replacing all")
        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    def save(self) -> bool:
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN — no changes written{C.END}")
            return True
        if self.path.suffix == '.py':
            try:
                compile(self.content, str(self.path), 'exec')
            except SyntaxError as e:
                print(f"{C.RED}  Syntax error after patch: {e}{C.END}")
                if self.backup_path and self.backup_path.exists():
                    shutil.copy2(self.backup_path, self.path)
                    print(f"{C.GREEN}  Restored from backup.{C.END}")
                return False
        try:
            self.path.write_text(self.content, encoding='utf-8')
            print(f"{C.GREEN}  Written {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Write failed: {e}{C.END}")
            return False

    def report(self) -> int:
        applied = sum(1 for _, s in self.results if s == 'applied')
        skipped = sum(1 for _, s in self.results if s == 'skip')
        failed = sum(1 for _, s in self.results if s == 'fail')
        print(f"\n  {C.BOLD}Summary:{C.END}  "
              f"{C.GREEN}applied={applied}{C.END}, "
              f"{C.GRAY}skipped={skipped}{C.END}, "
              f"{C.RED}failed={failed}{C.END}")
        return failed


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

def restore_latest(path: Path) -> bool:
    backups = sorted(
        path.parent.glob(path.name + '.bak.*'),
        key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print(f"{C.RED}No backups for {path.name}{C.END}")
        return False
    latest = backups[0]
    print(f"{C.CYAN}Restoring {path.name} from {latest.name}{C.END}")
    shutil.copy2(latest, path)
    print(f"{C.GREEN}✓ Restored.{C.END}")
    return True


def main():
    p = argparse.ArgumentParser(
        description="Apply ccxt 4.x fixes to trading_2_live2.py")
    p.add_argument("--bot", type=str, default="trading_2_live2.py",
                   help="Path to the trading bot file")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview without writing")
    p.add_argument("--restore", action="store_true",
                   help="Restore from the latest backup")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}╔{'═' * 74}╗{C.END}")
    print(f"{C.BOLD}║  ccxt 4.x Patcher -- trading_2_live2.py"
          f"{' ' * 33}║{C.END}")
    print(f"{C.BOLD}║  Mode: "
          f"{'DRY-RUN' if args.dry_run else 'APPLY':<66}"
          f"║{C.END}")
    print(f"{C.BOLD}╚{'═' * 74}╝{C.END}")

    if args.restore:
        sys.exit(0 if restore_latest(bot) else 1)

    if not bot.exists():
        print(f"{C.RED}File not found: {bot}{C.END}")
        sys.exit(2)

    pt = Patcher(bot, dry_run=args.dry_run)
    if not pt.load():
        sys.exit(3)
    if not pt.backup():
        sys.exit(4)

    print(f"\n{C.BOLD}Applying 12 patches...{C.END}\n")

    # P1
    pt.replace("P1  Insert tier infrastructure",
               P1_ANCHOR, P1_INSERTED,
               marker="def _extract_tier_entry(tiers_raw, symbol: str) -> Optional[Dict]:")

    # P2
    pt.replace("P2  _get_mmr_for_symbol (dict-shape)",
               P2_OLD, P2_NEW,
               marker="[ccxt 4.x FIX] Uses _extract_tier_entry() to handle dict-shaped")

    # P3
    pt.replace("P3  compute_max_leverage_by_liq (symbol-aware)",
               P3_OLD, P3_NEW,
               marker="when `symbol` is given, snap to that symbol's")

    # P4
    pt.replace("P4  compute_dynamic_leverage (symbol-aware)",
               P4_OLD, P4_NEW,
               marker="When `symbol` is given, snap the result to the")

    # P5a
    pt.replace("P5a ensure_symbol_setup tier-snap",
               P5A_ANCHOR, P5A_REPLACEMENT,
               marker="Snap target to the symbol's actual tiers BEFORE")

    # P5b
    pt.replace("P5b ensure_symbol_setup has_pos (None-safe)",
               P5B_OLD, P5B_NEW,
               marker="Binance Demo returns None from fetch_leverage")

    # P6
    pt.replace("P6  prefetch in run_backtest",
               P6_ANCHOR, P6_REPLACEMENT,
               marker="Prefetch leverage tiers for all symbols.\n    # This populates _SYMBOL_LEV_TIERS")

    # P7
    pt.replace("P7  prefetch in run_live",
               P7_ANCHOR, P7_REPLACEMENT,
               marker="Prefetch leverage tiers for all live symbols.")

    # P8a
    pt.replace("P8a compute_dynamic_leverage call (backtest)",
               P8A_OLD, P8A_NEW,
               marker="dynamic_leverage = compute_dynamic_leverage(capital, CFG, symbol=sym)")

    # P8b
    pt.replace("P8b compute_dynamic_leverage call (live)",
               P8B_OLD, P8B_NEW,
               marker="dynamic_leverage = compute_dynamic_leverage(\n                        cap_live, cfg, symbol=sym)")

    # P9a
    pt.replace("P9a add symbol= to max_lev_by_liq call (backtest)",
               P9A_OLD, P9A_NEW,
               marker="safety_mult=float(CFG.LIQ_SAFETY_MULT),\n                symbol=sym,")

    # P9b
    pt.replace("P9b add symbol= to max_lev_by_liq call (live)",
               P9B_OLD, P9B_NEW,
               marker="safety_mult=float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5)),\n                            symbol=sym,")

    if not pt.save():
        sys.exit(5)

    failed = pt.report()

    print(f"\n{C.BOLD}╔{'═' * 74}╗{C.END}")
    if failed == 0:
        print(f"{C.BOLD}║  {C.GREEN}ALL 12 PATCHES APPLIED SUCCESSFULLY"
              f"{C.END}{' ' * 28}║{C.END}")
    else:
        print(f"{C.BOLD}║  {C.RED}{failed} PATCH(ES) FAILED"
              f"{C.END}{' ' * 47}║{C.END}")
    print(f"{C.BOLD}╚{'═' * 74}╝{C.END}")

    if not args.dry_run and failed == 0:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify syntax:  "
              f"{C.BOLD}python3 -m py_compile {bot.name}{C.END}")
        print(f"  2. Grep for fixes: "
              f"{C.BOLD}grep -n '_extract_tier_entry\\|"
              f"prefetch_all_leverage_tiers' {bot.name}{C.END}")
        print(f"  3. Run test:       "
              f"{C.BOLD}python3 exchange_api_test2.py --mode testnet "
              f"--api-key $KEY --api-secret $SECRET{C.END}")
        print(f"  4. To revert:      "
              f"{C.BOLD}python3 patch_live2_ccxt4.py --restore{C.END}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
