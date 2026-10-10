#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_live2_smart_protection.py                                         ║
║  ccxt 4.x fixes + smart SL/TP placement + smart breakeven               ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Group A — ccxt 4.x infrastructure                                       ║
║    P1    Insert tier helpers / caches / functions                        ║
║    P2    _get_mmr_for_symbol  (dict-shape)                               ║
║    P3    compute_max_leverage_by_liq (symbol-aware)                      ║
║    P4    compute_dynamic_leverage   (symbol-aware)                       ║
║    P5a   ensure_symbol_setup — tier-snap                                 ║
║    P5b   ensure_symbol_setup — None-safe has_pos                         ║
║    P6    prefetch in run_backtest                                        ║
║    P7    prefetch in run_live                                            ║
║    P8a/b callsite updates (compute_dynamic_leverage)                     ║
║    P9a/b callsite updates (compute_max_leverage_by_liq)                  ║
║                                                                          ║
║  Group B — Smart SL/TP protection                                        ║
║    P10   _cancel_all_protective_orders uses _lv_open_orders_all          ║
║    P11   _lv_check_protective_on_exchange helper +                     ║
║          _place_protective_orders idempotency precheck                   ║
║    P12   _lv_adopt accepts state_hint (use state SL/TP if valid)         ║
║    P13   _lv_reconcile_state_machine snapshots state before removal      ║
║                                                                          ║
║  Group C — Smart breakeven                                               ║
║    P14   _lv_get_exchange_sl helper                                      ║
║    P15   _lv_breakeven — compare with exchange SL, no-op / replace       ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 patch_live2_smart_protection.py --dry-run                    ║
║    python3 patch_live2_smart_protection.py                              ║
║    python3 patch_live2_smart_protection.py --restore                    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse, shutil, sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class C:
    GREEN='\033[92m'; RED='\033[91m'; YELLOW='\033[93m'
    CYAN='\033[96m'; GRAY='\033[90m'; BOLD='\033[1m'; END='\033[0m'


# ══════════════════════════════════════════════════════════════════════════
# P1 — Insert tier infrastructure (helpers + caches + functions)
# ══════════════════════════════════════════════════════════════════════════

P1_ANCHOR = "_MMR_CACHE: Dict[str, float] = {}\n\n\ndef _get_mmr_for_symbol"

P1_INSERTED = '''_MMR_CACHE: Dict[str, float] = {}


# ═════════════════════════════════════════════════════════════════════
# [ccxt 4.x FIX] Per-symbol leverage tier infrastructure
# ═════════════════════════════════════════════════════════════════════
#
# ccxt >= 4.x returns fetch_leverage_tiers() as a DICT keyed by symbol
# (e.g. {"BTC/USDT:USDT": {...}}) instead of the older LIST shape.
# The old code assumed a list (tiers[0]) -> KeyError: 0 on every call.
# Effect: MMR fell through to the conservative 2% fallback, and
# leverage was never snapped to the exchange's actual ladder.
#
# Solution:
#   * _extract_tier_entry() normalizes both list and dict shapes.
#   * _SYMBOL_LEV_TIERS caches (max_lev, [valid_tiers]) per symbol.
#   * All tier-consuming code paths route through _symbol_tiers().
# ═════════════════════════════════════════════════════════════════════

_SYMBOL_LEV_TIERS: Dict[str, Tuple[int, List[int]]] = {}

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

    if isinstance(tiers_raw, list):
        if len(tiers_raw) == 0:
            return None
        for entry in tiers_raw:
            if isinstance(entry, dict) and _sym_match(
                    entry.get('symbol', ''), symbol):
                return entry
        first = tiers_raw[0]
        return first if isinstance(first, dict) else None

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
    ladder = (1, 2, 3, 5, 10, 20, 25, 50, 75, 100, 125)
    out = [t for t in ladder if t <= int(max_lev)]
    if not out:
        out = [int(max_lev)]
    return out


def _register_leverage_tiers(symbol: str, max_lev: int) -> None:
    max_lev = int(max_lev)
    if max_lev <= 0:
        return
    _SYMBOL_LEV_TIERS[symbol] = (max_lev, _standard_ladder(max_lev))


def _fallback_max_leverage(symbol: str, cfg) -> int:
    if symbol in _STATIC_MAX_LEVERAGE:
        return _STATIC_MAX_LEVERAGE[symbol]
    return int(getattr(cfg, 'LEVERAGE_MAX', 50))


def _symbol_tiers(symbol: Optional[str], cfg) -> List[int]:
    if symbol and symbol in _SYMBOL_LEV_TIERS:
        return list(_SYMBOL_LEV_TIERS[symbol][1])
    if symbol:
        max_lev = _fallback_max_leverage(symbol, cfg)
        return _standard_ladder(max_lev)
    return _standard_ladder(int(getattr(cfg, 'LEVERAGE_MAX', 50)))


def fetch_symbol_leverage_tiers(exchange, symbol: str) -> Optional[int]:
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
# P2 — _get_mmr_for_symbol  (dict-shape)
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
    responses. Before the fix, dict responses fell through to the 2%
    fallback, so all LevCap / LiqGate calculations used conservative
    values instead of the true per-symbol MMR.
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
# P3 — compute_max_leverage_by_liq (symbol-aware)
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

    [ccxt 4.x FIX] When `symbol` is given, snaps to that symbol's
    actual tiers. Prevents -4028 rejections.
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
# P4 — compute_dynamic_leverage (symbol-aware)
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
    ③ الرافعة الديناميكية تتناقص مع نمو رأس المال.

    [ccxt 4.x FIX] When `symbol` is given, snaps to that symbol's
    actual valid tiers (prevents -4028).
    """
    C0 = cfg.INITIAL_CAPITAL
    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    raw_lev = int(np.clip(round(lev), cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))
    if symbol is None:
        return raw_lev
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
# P5a — ensure_symbol_setup — tier-snap
# ══════════════════════════════════════════════════════════════════════════

P5A_OLD = '''    global _SYMBOL_META
    meta = _SYMBOL_META.get(sym, {})

    # Fast path: already set up with matching leverage
    if meta.get('setup_done') and int(meta.get('leverage', 0)) == target_leverage:
        return True'''

P5A_NEW = '''    global _SYMBOL_META

    # ══ [ccxt 4.x FIX] Snap target to the symbol's actual tiers ══
    try:
        if sym not in _SYMBOL_LEV_TIERS:
            _max_lev = fetch_symbol_leverage_tiers(exchange, sym)
            if _max_lev is None:
                _max_lev = _fallback_max_leverage(sym, CFG)
            _register_leverage_tiers(sym, _max_lev)
        _tiers_for_sym = _SYMBOL_LEV_TIERS[sym][1]
        _snapped = [t for t in _tiers_for_sym
                    if int(t) <= int(target_leverage)]
        if _snapped:
            _new_lev = int(_snapped[-1])
        else:
            _new_lev = int(_tiers_for_sym[0]) if _tiers_for_sym else 1
        if _new_lev != int(target_leverage):
            log.info(f"[Setup] {sym} snap {target_leverage}x -> {_new_lev}x "
                     f"(max={_SYMBOL_LEV_TIERS[sym][0]}x)")
            target_leverage = _new_lev
    except Exception as _e:
        log.warning(f"[Setup] {sym} snap failed: {_e}")

    meta = _SYMBOL_META.get(sym, {})

    # Fast path: already set up with matching leverage
    if meta.get('setup_done') and int(meta.get('leverage', 0)) == target_leverage:
        return True'''


# ══════════════════════════════════════════════════════════════════════════
# P5b — ensure_symbol_setup — None-safe has_pos
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
        try:
            lev_info = exchange.fetch_leverage(sym)
            if lev_info is None or not hasattr(lev_info, 'get'):
                cur_lev = target_leverage
            else:
                cur_lev = int(lev_info.get('leverage', target_leverage)
                              or target_leverage)
        except Exception:
            cur_lev = target_leverage'''


# ══════════════════════════════════════════════════════════════════════════
# P6 — prefetch in run_backtest
# ══════════════════════════════════════════════════════════════════════════

P6_OLD = '''    if not raw: log.error("لا بيانات."); return
    if raw_sub:'''

P6_NEW = '''    if not raw: log.error("لا بيانات."); return

    # [ccxt 4.x FIX] Prefetch leverage tiers for all symbols
    try:
        prefetch_all_leverage_tiers(exchange, list(raw.keys()))
    except Exception as _e:
        log.warning(f"[LevTiers] backtest prefetch failed: {_e}")

    if raw_sub:'''


# ══════════════════════════════════════════════════════════════════════════
# P7 — prefetch in run_live
# ══════════════════════════════════════════════════════════════════════════

P7_OLD = '''    cached_data = fetch_all(top_syms, exchange, cfg.timeframe,
                            days=_live_history_days, workers=5)

    # ══ [HELD SYMBOLS] Ensure open positions are always tracked ══'''

P7_NEW = '''    cached_data = fetch_all(top_syms, exchange, cfg.timeframe,
                            days=_live_history_days, workers=5)

    # [ccxt 4.x FIX] Prefetch leverage tiers for all live symbols
    try:
        prefetch_all_leverage_tiers(exchange, list(cached_data.keys()))
    except Exception as _e:
        log.warning(f"[LevTiers] live prefetch failed: {_e}")

    # ══ [HELD SYMBOLS] Ensure open positions are always tracked ══'''


# ══════════════════════════════════════════════════════════════════════════
# P8a — backtest callsite for compute_dynamic_leverage
# ══════════════════════════════════════════════════════════════════════════

P8A_OLD = '''        # Leverage cap
        dynamic_leverage = compute_dynamic_leverage(capital, CFG)'''

P8A_NEW = '''        # Leverage cap
        dynamic_leverage = compute_dynamic_leverage(capital, CFG, symbol=sym)'''


# ══════════════════════════════════════════════════════════════════════════
# P8b — live callsite for compute_dynamic_leverage
# ══════════════════════════════════════════════════════════════════════════

P8B_OLD = '''                    dynamic_leverage = compute_dynamic_leverage(cap_live, cfg)'''

P8B_NEW = '''                    dynamic_leverage = compute_dynamic_leverage(
                        cap_live, cfg, symbol=sym)'''


# ══════════════════════════════════════════════════════════════════════════
# P9a — backtest callsite for compute_max_leverage_by_liq
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
# P9b — live callsite for compute_max_leverage_by_liq
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
# P10 — _cancel_all_protective_orders uses _lv_open_orders_all
# ══════════════════════════════════════════════════════════════════════════

P10_OLD = '''def _cancel_all_protective_orders(exchange, sym: str,
                                     max_passes: int = 2) -> int:
    """
    Cancel every STOP_MARKET / TAKE_PROFIT_MARKET on the symbol.

    [DUPLICATE-FIX] two-pass cancel: الأولى تلغي، والثانية تتحقق.
    هذا يمنع بقاء نسخة ثانية من الأوامر على البورصة.
    """
    n = 0
    for pass_idx in range(max_passes):
        try:
            open_orders = exchange.fetch_open_orders(sym)
        except Exception as e:
            log.debug(f"[Prot] fetch_open_orders {sym} failed: {e}")
            break
        prot_orders = [o for o in open_orders if _is_protective_order(o)]
        if not prot_orders:
            break
        if pass_idx == 0:
            log.info(f"[Prot] {sym} cancelling {len(prot_orders)} "
                     f"stale protective order(s)")
        for o in prot_orders:
            try:
                exchange.cancel_order(o['id'], sym)
                n += 1
            except Exception as e:
                log.warning(f"[Prot] cancel {sym} oid={o['id']} failed: {e}")
        import time as _t
        _t.sleep(0.3)
    return n'''

P10_NEW = '''def _cancel_all_protective_orders(exchange, sym: str,
                                     max_passes: int = 2) -> int:
    """
    Cancel every STOP_MARKET / TAKE_PROFIT_MARKET on the symbol.

    [ccxt 4.x FIX] Uses _lv_open_orders_all which queries BOTH the
    standard endpoint AND params={'trigger': True}. Before the fix,
    plain fetch_open_orders returned [] for conditional orders on
    Binance Futures (Algo Order service) -> the cancel was a no-op
    and old orders lingered forever.
    """
    n = 0
    for pass_idx in range(max_passes):
        try:
            open_orders = _lv_open_orders_all(exchange, sym)
        except Exception:
            try:
                open_orders = exchange.fetch_open_orders(sym)
            except Exception as e:
                log.debug(f"[Prot] fetch_open_orders {sym} failed: {e}")
                break
        prot_orders = [o for o in open_orders if _is_protective_order(o)]
        if not prot_orders:
            break
        if pass_idx == 0:
            log.info(f"[Prot] {sym} cancelling {len(prot_orders)} "
                     f"stale protective order(s)")
        for o in prot_orders:
            _oid = o['id']
            _cancelled = False
            for _params in ({'trigger': True}, {}):
                try:
                    exchange.cancel_order(_oid, sym, params=_params)
                    _cancelled = True
                    n += 1
                    break
                except Exception as _e:
                    _msg = str(_e).lower()
                    if '-2011' in _msg or 'unknown order' in _msg:
                        _cancelled = True
                        break
                    continue
            if not _cancelled:
                log.warning(f"[Prot] cancel {sym} oid={_oid} failed")
        import time as _t
        _t.sleep(0.3)
    return n'''


# ══════════════════════════════════════════════════════════════════════════
# P11 — Insert _lv_check_protective_on_exchange before _place_protective_orders
#       + Insert smart check inside _place_protective_orders
# ══════════════════════════════════════════════════════════════════════════

P11_HELPER_ANCHOR = '''def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:'''

P11_HELPER_BLOCK = '''def _lv_check_protective_on_exchange(exchange, sym: str,
                                       sl: float, tp: float
                                       ) -> Tuple[bool, bool]:
    """
    [SMART-CHECK] Returns (has_sl, has_tp) indicating whether the
    exchange already has a protective SL at ~sl and a protective TP
    at ~tp for this symbol.

    Uses price-match with 1 bps tolerance (or 1e-9 absolute minimum).

    A non-TP protective order whose stopPrice matches `sl` counts as SL.
    Any take_profit type whose stopPrice matches `tp` counts as TP.
    """
    try:
        orders = _lv_open_orders_all(exchange, sym)
    except Exception as e:
        log.debug(f"[SmartProt] {sym} fetch orders failed: {e}")
        return False, False
    tol_sl = max(abs(sl) * 1e-4, 1e-9)
    tol_tp = max(abs(tp) * 1e-4, 1e-9)
    has_sl = False
    has_tp = False
    for o in orders:
        sp = float(
            o.get('stopPrice')
            or o.get('triggerPrice')
            or (o.get('info') or {}).get('stopPrice')
            or 0
        )
        if sp <= 0:
            continue
        ot = str(o.get('type') or '').lower()
        if 'take_profit' in ot:
            if abs(sp - tp) < tol_tp:
                has_tp = True
        else:
            if abs(sp - sl) < tol_sl:
                has_sl = True
    return has_sl, has_tp


def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:'''


P11_INNER_OLD = """        if action not in ('BUY', 'SELL') or sl <= 0 or tp <= 0 or qty <= 0:
            return False

        close_side = 'sell' if action == 'BUY' else 'buy'
"""


P11_INNER_NEW = """        if action not in ('BUY', 'SELL') or sl <= 0 or tp <= 0 or qty <= 0:
            return False

        # SMART-CHECK: if the exchange already has matching SL and TP,
        # leave them untouched and return success immediately.
        _ex_has_sl, _ex_has_tp = _lv_check_protective_on_exchange(
            exchange, sym, sl, tp
        )
        if _ex_has_sl and _ex_has_tp:
            log.debug(
                f"[Prot] {sym} SL@{sl:.6f} and TP@{tp:.6f} already "
                f"exist on exchange -- no action"
            )
            return True
        if _ex_has_sl or _ex_has_tp:
            log.info(
                f"[Prot] {sym} partial protection "
                f"(sl_exists={_ex_has_sl}, tp_exists={_ex_has_tp}) -- "
                f"will cancel remaining and re-place both"
            )

        close_side = 'sell' if action == 'BUY' else 'buy'
"""


# ══════════════════════════════════════════════════════════════════════════
# P12 — _lv_adopt accepts state_hint
# ══════════════════════════════════════════════════════════════════════════

P12_OLD = '''def _lv_adopt(exchange, sym, ex, assets=None):
    # build a complete local record for an exchange-only position and PROTECT it now
    entry, side, qty = float(ex['entry']), ex['side'], float(ex['qty'])
    max_sl_frac = 0.015 * float(_lv_cfg('SL_WIDEN_MULT', 1.0))
    tp_mult = float(_lv_cfg('TP_MULT', 1.5))
    sl_dist = tp_dist = 0.0
    src = 'fallback'
    prec = _PENDING_ORDERS.get(sym)
    T_info, dyn_risk = 0.0, 0.01
    if prec is not None:
        sd0 = float(prec.get('orig_sl_dist') or 0.0)
        td0 = float(prec.get('orig_tp_dist') or 0.0)
        if sd0 > 0 and td0 > 0:
            sl_dist, tp_dist, src = sd0, td0, 'pending'
            T_info = float(prec.get('T_info') or 0.0)
            dyn_risk = float(prec.get('dyn_risk') or 0.01)
    ad = (assets or {}).get(sym)
    if sl_dist <= 0 and ad is not None:
        try:
            ci = len(ad.closes) - 2
            fi = max(0, min(ci - ad.feat_start, len(ad.E_therm) - 1))
            sl_dist = float(compute_geodesic_stop(entry, ad, fi, CFG))
            tp_dist = sl_dist * tp_mult
            src = 'physics'
        except Exception:
            sl_dist = 0.0
    if sl_dist <= 0 or not np.isfinite(sl_dist):
        sl_dist = entry * 0.015
        tp_dist = sl_dist * tp_mult
        src = 'fallback'
    if sl_dist > entry * max_sl_frac:
        rr = tp_dist / max(sl_dist, 1e-12)
        sl_dist = entry * max_sl_frac
        tp_dist = sl_dist * rr'''

P12_NEW = '''def _lv_adopt(exchange, sym, ex, assets=None, state_hint=None):
    # build a complete local record for an exchange-only position and PROTECT it now
    entry, side, qty = float(ex['entry']), ex['side'], float(ex['qty'])
    max_sl_frac = 0.015 * float(_lv_cfg('SL_WIDEN_MULT', 1.0))
    tp_mult = float(_lv_cfg('TP_MULT', 1.5))
    sl_dist = tp_dist = 0.0
    src = 'fallback'
    T_info, dyn_risk = 0.0, 0.01

    # ══ [ORPHAN-STATE] Prefer state-file SL/TP values if valid ══
    # The user requirement: if an orphan position has SL/TP recorded
    # in the state file, place THOSE on the exchange as-is, instead
    # of recomputing them from physics. Fall back to physics only
    # when the state has no valid record for this symbol.
    if state_hint is not None:
        try:
            _st_sl = float(state_hint.get('sl') or 0)
            _st_tp = float(state_hint.get('tp1') or 0)
        except Exception:
            _st_sl = _st_tp = 0.0
        if _st_sl > 0 and _st_tp > 0:
            _sl_side_ok = ((side == 'BUY' and _st_sl < entry) or
                           (side == 'SELL' and _st_sl > entry))
            _tp_side_ok = ((side == 'BUY' and _st_tp > entry) or
                           (side == 'SELL' and _st_tp < entry))
            if _sl_side_ok and _tp_side_ok:
                sl_dist = abs(entry - _st_sl)
                tp_dist = abs(_st_tp - entry)
                src = 'state'
                T_info = float(state_hint.get('T_info') or 0.0)
                dyn_risk = float(state_hint.get('dyn_risk') or 0.01)
                log.info(
                    f"[Reconcile] {sym} orphan: using state SL="
                    f"{_st_sl:.6f} TP={_st_tp:.6f}"
                )
            else:
                log.info(
                    f"[Reconcile] {sym} orphan: state SL={_st_sl:.6f} "
                    f"TP={_st_tp:.6f} invalid side -- using physics"
                )

    prec = _PENDING_ORDERS.get(sym)
    if sl_dist <= 0 and prec is not None:
        sd0 = float(prec.get('orig_sl_dist') or 0.0)
        td0 = float(prec.get('orig_tp_dist') or 0.0)
        if sd0 > 0 and td0 > 0:
            sl_dist, tp_dist, src = sd0, td0, 'pending'
            T_info = float(prec.get('T_info') or 0.0)
            dyn_risk = float(prec.get('dyn_risk') or 0.01)
    ad = (assets or {}).get(sym)
    if sl_dist <= 0 and ad is not None:
        try:
            ci = len(ad.closes) - 2
            fi = max(0, min(ci - ad.feat_start, len(ad.E_therm) - 1))
            sl_dist = float(compute_geodesic_stop(entry, ad, fi, CFG))
            tp_dist = sl_dist * tp_mult
            src = 'physics'
        except Exception:
            sl_dist = 0.0
    if sl_dist <= 0 or not np.isfinite(sl_dist):
        sl_dist = entry * 0.015
        tp_dist = sl_dist * tp_mult
        src = 'fallback'
    if sl_dist > entry * max_sl_frac:
        rr = tp_dist / max(sl_dist, 1e-12)
        sl_dist = entry * max_sl_frac
        tp_dist = sl_dist * rr'''


# ══════════════════════════════════════════════════════════════════════════
# P13 — _lv_reconcile_state_machine — snapshot + pass state_hint
# ══════════════════════════════════════════════════════════════════════════

P13A_OLD = '''    ex = _lv_fetch_positions(exchange, symbols)
    if ex is None:
        return open_pos_live
    now = time.time()
    changed = 0
    confirm = float(_lv_cfg('LIVE_MISSING_CONFIRM_S', 20.0))
    for sym in list(open_pos_live.keys()):'''

P13A_NEW = '''    ex = _lv_fetch_positions(exchange, symbols)
    if ex is None:
        return open_pos_live
    now = time.time()
    changed = 0
    confirm = float(_lv_cfg('LIVE_MISSING_CONFIRM_S', 20.0))
    # ══ [ORPHAN-STATE] Snapshot the state file BEFORE any removal, so
    # that _lv_adopt can read the recorded SL/TP values for any symbol
    # that exists on the exchange but not in local memory.
    _state_snapshot = dict(open_pos_live)
    for sym in list(open_pos_live.keys()):'''


P13B_OLD = '''            log.warning(f"[Reconcile] {sym} exchange-only → adopting")
            open_pos_live[sym] = _lv_adopt(exchange, sym, e, _LV_ASSETS)
            changed += 1'''

P13B_NEW = '''            log.warning(f"[Reconcile] {sym} exchange-only → adopting")
            open_pos_live[sym] = _lv_adopt(
                exchange, sym, e, _LV_ASSETS,
                state_hint=_state_snapshot.get(sym),
            )
            changed += 1'''


# ══════════════════════════════════════════════════════════════════════════
# P14 — Insert _lv_get_exchange_sl before _lv_breakeven
# ══════════════════════════════════════════════════════════════════════════

P14_ANCHOR = '''def _lv_breakeven(exchange, sym, pos, now) -> None:'''

P14_BLOCK = '''def _lv_get_exchange_sl(exchange, sym, pos):
    """
    [SMART-BE] Return the price of the current SL order on the exchange
    for this position, or None if no SL exists on the exchange.

    Non-TP protective orders only.
    """
    try:
        orders = _lv_open_orders_all(exchange, sym)
    except Exception as e:
        log.debug(f"[SmartBE] {sym} fetch orders failed: {e}")
        return None
    for o in orders:
        ot = str(o.get('type') or '').lower()
        if 'take_profit' in ot:
            continue
        sp = float(
            o.get('stopPrice')
            or o.get('triggerPrice')
            or (o.get('info') or {}).get('stopPrice')
            or 0
        )
        if sp > 0:
            return sp
    return None


def _lv_breakeven(exchange, sym, pos, now) -> None:'''


# ══════════════════════════════════════════════════════════════════════════
# P15 — _lv_breakeven — compare with exchange SL, no-op or replace
# ══════════════════════════════════════════════════════════════════════════

P15_OLD = '''def _lv_breakeven(exchange, sym, pos, now) -> None:
    # live twin of the backtest BREAKEVEN-SL: MFE >= BREAKEVEN_AT_R × initial SL distance
    # → SL := entry. Only when trailing is OFF (same gate as _advance).
    if getattr(CFG, 'TRAIL_ENABLED', True) or not getattr(CFG, 'BREAKEVEN_ENABLED', True):
        return
    if pos.get('_be_done'):
        return
    entry = float(pos.get('entry') or 0.0)
    d0 = float(pos.get('sl_dist_initial') or 0.0)
    if entry <= 0 or d0 <= 0:
        return
    r = float(_lv_cfg('BREAKEVEN_AT_R', 1.0))
    mfe = (float(pos.get('_hi', entry)) - entry) if pos['action'] == 'BUY' else (entry - float(pos.get('_lo', entry)))
    if mfe < d0 * r:
        return
    cur = float(pos['sl'])
    better = (entry > cur) if pos['action'] == 'BUY' else (entry < cur)
    pos['_be_done'] = True
    if not better:
        return
    pos['sl'] = entry
    pos['_be_ts'] = now
    pos['_prot_last_sl'] = None       # _lv_ensure_protection re-places the broker orders
    log.info(f"[Breakeven] {sym} {pos['action']} MFE={mfe:.6f} ≥ {r}R "
             f"({d0 * r:.6f}) → SL moved to entry {entry:.6f}")'''

P15_NEW = '''def _lv_breakeven(exchange, sym, pos, now) -> None:
    """
    Live twin of the backtest BREAKEVEN-SL.

    [SMART-BE] The exchange SL is read first. Behaviour:
      * Exchange SL at the same price as our target → NO-OP (do nothing)
      * Exchange SL at a different price            → cancel it, then
                                                      place the new SL
      * No exchange SL                              → place the new SL
    """
    if getattr(CFG, 'TRAIL_ENABLED', True) or not getattr(CFG, 'BREAKEVEN_ENABLED', True):
        return
    if pos.get('_be_done'):
        return
    entry = float(pos.get('entry') or 0.0)
    d0 = float(pos.get('sl_dist_initial') or 0.0)
    if entry <= 0 or d0 <= 0:
        return
    r = float(_lv_cfg('BREAKEVEN_AT_R', 1.0))
    mfe = (float(pos.get('_hi', entry)) - entry) if pos['action'] == 'BUY' \\
          else (entry - float(pos.get('_lo', entry)))
    if mfe < d0 * r:
        return
    cur = float(pos['sl'])
    better = (entry > cur) if pos['action'] == 'BUY' else (entry < cur)
    pos['_be_done'] = True
    if not better:
        return

    _target_sl = entry

    # ══ [SMART-BE] Read the actual SL that's on the exchange ══
    _exch_sl = _lv_get_exchange_sl(exchange, sym, pos)

    if _exch_sl is not None:
        _same = abs(_exch_sl - _target_sl) / max(abs(_target_sl), 1e-9) < 1e-4
        if _same:
            # Same price -> no-op, just record it as placed
            pos['sl'] = _target_sl
            pos['_prot_last_sl'] = _exch_sl
            pos['_be_ts'] = now
            log.info(
                f"[Breakeven] {sym} exchange SL already at "
                f"{_exch_sl:.6f} -- no-op"
            )
            return
        # Different price -> cancel the existing SL first (explicit replace)
        log.info(
            f"[Breakeven] {sym} replacing exchange SL "
            f"{_exch_sl:.6f} -> {_target_sl:.6f}"
        )
        try:
            _cancel_all_protective_orders(exchange, sym)
            time.sleep(0.5)
        except Exception as _e:
            log.warning(f"[Breakeven] {sym} cancel before replace failed: {_e}")

    pos['sl'] = _target_sl
    pos['_be_ts'] = now
    pos['_prot_last_sl'] = None
    log.info(
        f"[Breakeven] {sym} {pos['action']} MFE={mfe:.6f} >= {r}R "
        f"({d0 * r:.6f}) -> SL moved to {_target_sl:.6f}"
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
            print(f"{C.RED}  Not found: {self.path}{C.END}")
            return False
        try:
            self.content = self.path.read_text(encoding='utf-8')
            print(f"{C.CYAN}  Loaded {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Read error: {e}{C.END}")
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
                marker: str = None) -> bool:
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
        if n > 1:
            print(f"  {C.YELLOW}⚠ WARN{C.END}  {name}: {n} occurrences")
        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    def save(self) -> bool:
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN -- not written{C.END}")
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
        a = sum(1 for _, s in self.results if s == 'applied')
        s = sum(1 for _, s in self.results if s == 'skip')
        f = sum(1 for _, s in self.results if s == 'fail')
        print(f"\n  {C.BOLD}Summary:{C.END}  "
              f"{C.GREEN}applied={a}{C.END}, "
              f"{C.GRAY}skipped={s}{C.END}, "
              f"{C.RED}failed={f}{C.END}")
        return f


def restore_latest(path: Path) -> bool:
    backups = sorted(path.parent.glob(path.name + '.bak.*'),
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
        description="ccxt 4.x + smart protection for trading_2_live2.py")
    p.add_argument("--bot", default="trading_2_live2.py")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.BOLD}  Smart Protection Patcher "
          f"-- {bot.name}{' ' * (40 - len(bot.name))}{C.END}")
    print(f"{C.BOLD}  Mode:   "
          f"{'DRY-RUN' if args.dry_run else 'APPLY'}{' ' * 60}{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if args.restore:
        sys.exit(0 if restore_latest(bot) else 1)
    if not bot.exists():
        print(f"{C.RED}File not found: {bot}{C.END}")
        sys.exit(2)

    pt = Patcher(bot, dry_run=args.dry_run)
    if not pt.load() or not pt.backup():
        sys.exit(3)

    print(f"\n{C.BOLD}═══ Group A: ccxt 4.x infrastructure ═══{C.END}\n")

    pt.replace("P1   Insert tier infrastructure",
               P1_ANCHOR, P1_INSERTED,
               marker="def _extract_tier_entry(tiers_raw, symbol: str) -> Optional[Dict]:")

    pt.replace("P2   _get_mmr_for_symbol (dict-shape)",
               P2_OLD, P2_NEW,
               marker="[ccxt 4.x FIX] Uses _extract_tier_entry() to handle dict-shaped")

    pt.replace("P3   compute_max_leverage_by_liq (symbol-aware)",
               P3_OLD, P3_NEW,
               marker="When `symbol` is given, snaps to that symbol's\n    actual tiers")

    pt.replace("P4   compute_dynamic_leverage (symbol-aware)",
               P4_OLD, P4_NEW,
               marker="When `symbol` is given, snaps to that symbol's\n    actual valid tiers")

    pt.replace("P5a  ensure_symbol_setup tier-snap",
               P5A_OLD, P5A_NEW,
               marker="Snap target to the symbol's actual tiers")

    pt.replace("P5b  ensure_symbol_setup None-safe has_pos",
               P5B_OLD, P5B_NEW,
               marker="Binance Demo returns None from fetch_leverage")

    pt.replace("P6   prefetch in run_backtest",
               P6_OLD, P6_NEW,
               marker="Prefetch leverage tiers for all symbols\n")

    pt.replace("P7   prefetch in run_live",
               P7_OLD, P7_NEW,
               marker="Prefetch leverage tiers for all live symbols")

    pt.replace("P8a  compute_dynamic_leverage backtest call",
               P8A_OLD, P8A_NEW,
               marker="compute_dynamic_leverage(capital, CFG, symbol=sym)")

    pt.replace("P8b  compute_dynamic_leverage live call",
               P8B_OLD, P8B_NEW,
               marker="compute_dynamic_leverage(\n                        cap_live, cfg, symbol=sym)")

    pt.replace("P9a  max_lev_by_liq backtest call",
               P9A_OLD, P9A_NEW,
               marker="safety_mult=float(CFG.LIQ_SAFETY_MULT),\n                symbol=sym,")

    pt.replace("P9b  max_lev_by_liq live call",
               P9B_OLD, P9B_NEW,
               marker="safety_mult=float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5)),\n                            symbol=sym,")

    print(f"\n{C.BOLD}═══ Group B: Smart protection ═══{C.END}\n")

    pt.replace("P10  _cancel_all_protective_orders uses _lv_open_orders_all",
               P10_OLD, P10_NEW,
               marker="Uses _lv_open_orders_all which queries BOTH the")

    pt.replace("P11  _lv_check_protective_on_exchange helper",
               P11_HELPER_ANCHOR, P11_HELPER_BLOCK,
               marker="def _lv_check_protective_on_exchange(exchange, sym: str,")

    pt.replace("P11b smart check inside _place_protective_orders",
               P11_INNER_OLD, P11_INNER_NEW,
               marker="[SMART-CHECK] If both SL and TP already exist on the exchange")

    pt.replace("P12  _lv_adopt accepts state_hint",
               P12_OLD, P12_NEW,
               marker="[ORPHAN-STATE] Prefer state-file SL/TP values if valid")

    pt.replace("P13a snapshot state before removal",
               P13A_OLD, P13A_NEW,
               marker="[ORPHAN-STATE] Snapshot the state file BEFORE any removal")

    pt.replace("P13b pass state_hint to _lv_adopt",
               P13B_OLD, P13B_NEW,
               marker="state_hint=_state_snapshot.get(sym),")

    print(f"\n{C.BOLD}═══ Group C: Smart breakeven ═══{C.END}\n")

    pt.replace("P14  _lv_get_exchange_sl helper",
               P14_ANCHOR, P14_BLOCK,
               marker="def _lv_get_exchange_sl(exchange, sym, pos):")

    pt.replace("P15  _lv_breakeven smart replace",
               P15_OLD, P15_NEW,
               marker="[SMART-BE] The exchange SL is read first")

    if not pt.save():
        sys.exit(4)
    failed = pt.report()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    if failed == 0:
        print(f"{C.GREEN}  ALL PATCHES APPLIED SUCCESSFULLY{C.END}")
    else:
        print(f"{C.RED}  {failed} PATCH(ES) FAILED{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if not args.dry_run and failed == 0:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify:  python3 -m py_compile {bot.name}")
        print(f"  2. Grep:    grep -n 'SMART-CHECK\\|ORPHAN-STATE\\|SMART-BE' {bot.name}")
        print(f"  3. Run bot and expect in logs:")
        print(f"     {C.BOLD}[Prot] BTC/USDT SL@... TP@... already exist on exchange"
              f" -- no action{C.END}")
        print(f"     {C.BOLD}[Reconcile] X orphan: using state SL=... TP=...{C.END}")
        print(f"     {C.BOLD}[Breakeven] X exchange SL already at ... -- no-op{C.END}")
        print(f"  4. Revert:  python3 {Path(__file__).name} --restore")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
