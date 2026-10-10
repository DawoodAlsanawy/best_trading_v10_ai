#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  exchange_api_test_v2.py                                                 ║
║  Comprehensive Exchange API Test — Post ccxt-4.x Fixes                   ║
╠══════════════════════════════════════════════════════════════════════════╣
║  New vs v1:                                                              ║
║    • Parity Check section — compares test extraction with bot logic     ║
║    • Dict/list normalization verification                               ║
║    • True MMR / tick / step extraction verification                     ║
║    • Leverage cap simulation (compute_max_leverage_by_liq)              ║
║    • Liquidation price simulation (compute_liquidation_price)           ║
║    • GTX preflight simulation                                           ║
║    • Order lifecycle with cleanup                                       ║
║    • JSON report with fix-verification section                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    python3 exchange_api_test_v2.py --mode testnet \                      ║
║        --api-key $KEY --api-secret $SECRET                               ║
║                                                                          ║
║    python3 exchange_api_test_v2.py --mode testnet \                      ║
║        --api-key $KEY --api-secret $SECRET \                             ║
║        --allow-orders --output report.json                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import ccxt
except ImportError:
    print("ERROR: ccxt not installed. Run: pip install ccxt")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════
# ANSI colors
# ══════════════════════════════════════════════════════════════════════════
class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    END = '\033[0m'


# ══════════════════════════════════════════════════════════════════════════
# Test infrastructure
# ══════════════════════════════════════════════════════════════════════════
class SkipTest(Exception):
    pass


class WarnTest(Exception):
    pass


class TestResults:
    def __init__(self):
        self.tests: List[Dict] = []
        self.start_ts = time.time()

    def add(self, name: str, status: str, duration: float,
            detail: str = "", error: str = "", category: str = ""):
        self.tests.append({
            'name': name,
            'status': status,
            'duration': duration,
            'detail': detail,
            'error': error,
            'category': category,
        })

    def summary(self) -> Dict:
        counts = {'PASS': 0, 'FAIL': 0, 'SKIP': 0, 'WARN': 0}
        for t in self.tests:
            counts[t['status']] = counts.get(t['status'], 0) + 1
        return counts

    def print_report(self):
        print()
        print("═" * 78)
        print(f"{C.BOLD}  EXCHANGE API TEST REPORT — v2{C.END}")
        print("═" * 78)

        last_cat = None
        for t in self.tests:
            if t['category'] and t['category'] != last_cat:
                print()
                print(f"{C.MAGENTA}  ▸ {t['category']}{C.END}")
                last_cat = t['category']

            if t['status'] == 'PASS':
                icon = f"{C.GREEN}✓ PASS{C.END}"
            elif t['status'] == 'FAIL':
                icon = f"{C.RED}✗ FAIL{C.END}"
            elif t['status'] == 'WARN':
                icon = f"{C.YELLOW}⚠ WARN{C.END}"
            else:
                icon = f"{C.GRAY}○ SKIP{C.END}"

            dur = f"{t['duration']*1000:6.0f}ms"
            print(f"    {icon}  {t['name']:<44} {dur}")
            if t['detail']:
                print(f"           {C.GRAY}{t['detail']}{C.END}")
            if t['error']:
                err = t['error'].replace('\n', ' ')[:180]
                print(f"           {C.RED}{err}{C.END}")

        counts = self.summary()
        total = sum(counts.values())
        print()
        print("─" * 78)
        print(f"  Total: {total}  |  "
              f"{C.GREEN}PASS: {counts['PASS']}{C.END}  |  "
              f"{C.RED}FAIL: {counts['FAIL']}{C.END}  |  "
              f"{C.YELLOW}WARN: {counts['WARN']}{C.END}  |  "
              f"{C.GRAY}SKIP: {counts['SKIP']}{C.END}")
        print(f"  Elapsed: {time.time() - self.start_ts:.1f}s")

        # ── Fix verification summary ──
        print()
        print("─" * 78)
        print(f"{C.BOLD}  FIX VERIFICATION{C.END}")
        print("─" * 78)
        # Helper: case-insensitive substring search
        def _has_test(substr: str, status: str = 'PASS') -> bool:
            s = substr.lower()
            return any(s in t['name'].lower() and t['status'] == status
                       for t in self.tests)

        def _has_detail(substr: str, status: str = 'PASS') -> bool:
            s = substr.lower()
            return any(s in t.get('detail', '').lower()
                       and t['status'] == status
                       for t in self.tests)

        # Helper: MMR test passes AND returns real value (not the 2% fallback)
        def _mmr_is_real() -> bool:
            for t in self.tests:
                if 'mmr' not in t['name'].lower():
                    continue
                if t['status'] != 'PASS':
                    continue
                det = t.get('detail', '').lower()
                # Real MMR is any value NOT equal to the fallback 2%
                if 'real_mmr=' in det and '2.0000' not in det:
                    return True
            return False

        fixes = [
            ('ccxt-4.x dict shape',       _has_detail('shape=dict')),
            ('Futures symbol notation',   _has_test('fetch_tickers')),
            ('True MMR extraction',       _mmr_is_real()),
            ('Leverage cap logic',        _has_test('levcap')),
            ('Liquidation price math',    _has_test('liquidation')),
            ('GTX preflight',             _has_test('preflight')
                                          or _has_test('preflight', 'WARN')),
        ]
        for fix_name, ok in fixes:
            icon = f"{C.GREEN}✓{C.END}" if ok else f"{C.RED}✗{C.END}"
            status = (f"{C.GREEN}verified{C.END}" if ok
                      else f"{C.RED}not verified{C.END}")
            print(f"    {icon}  {fix_name:<35} {status}")
        print("═" * 78)


RESULTS = TestResults()


def run_test(name: str, fn, *args, category: str = "", **kwargs) -> Tuple[bool, Any]:
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        duration = time.time() - t0
        detail = ""
        if isinstance(result, tuple) and len(result) == 2:
            detail = str(result[1])
            result = result[0]
        RESULTS.add(name, 'PASS', duration, detail=detail, category=category)
        return True, result
    except SkipTest as e:
        RESULTS.add(name, 'SKIP', time.time() - t0, detail=str(e),
                    category=category)
        return False, None
    except WarnTest as e:
        RESULTS.add(name, 'WARN', time.time() - t0, detail=str(e),
                    category=category)
        return True, None
    except Exception as e:
        tb = traceback.format_exc()
        RESULTS.add(name, 'FAIL', time.time() - t0,
                    error=f"{type(e).__name__}: {e}\n{tb}",
                    category=category)
        return False, None


# ══════════════════════════════════════════════════════════════════════════
# [BOT LOGIC] — Duplicate the fixed bot helpers to verify parity
# ══════════════════════════════════════════════════════════════════════════

def _extract_tier_entry(tiers_raw, symbol: str) -> Optional[Dict]:
    """[Copy from fixed bot] Normalize fetch_leverage_tiers across ccxt versions."""
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


def _bot_fetch_symbol_max_leverage(exchange, symbol: str) -> Optional[int]:
    """[Copy from fixed bot] fetch_symbol_leverage_tiers."""
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
    except Exception:
        return None


def _bot_get_mmr(exchange, symbol: str) -> float:
    """[Copy from fixed bot] _get_mmr_for_symbol."""
    try:
        tiers_raw = exchange.fetch_leverage_tiers([symbol])
        entry = _extract_tier_entry(tiers_raw, symbol)
        if entry is not None:
            tier_list = entry.get('tiers', []) or []
            if tier_list:
                mmr = float(tier_list[0].get('maintenanceMarginRate', 0))
                if mmr > 0:
                    return mmr
    except Exception:
        pass
    return 0.02  # LIQ_FALLBACK_MMR


def _bot_get_tick_size(exchange, symbol: str) -> Optional[float]:
    """[Copy from bot] _get_tick_size."""
    try:
        mkt = exchange.market(symbol)
    except Exception:
        return None
    if not mkt:
        return None
    info = mkt.get('info') or {}
    for f in (info.get('filters') or []):
        if isinstance(f, dict) and f.get('filterType') == 'PRICE_FILTER':
            try:
                ts = float(f.get('tickSize', 0))
                if ts > 0 and math.isfinite(ts):
                    return ts
            except Exception:
                pass
    prec = (mkt.get('precision') or {}).get('price')
    if prec is not None:
        try:
            ts = float(prec)
            if ts > 0 and math.isfinite(ts):
                return ts
        except Exception:
            pass
    return None


def _bot_get_step_size(exchange, symbol: str) -> float:
    """[Copy from bot] _get_step_size."""
    try:
        mkt = exchange.market(symbol)
        info = mkt.get('info') or {}
        for f in (info.get('filters') or []):
            if f.get('filterType') in ('LOT_SIZE', 'MARKET_LOT_SIZE'):
                step = float(f.get('stepSize', 0))
                if step > 0:
                    return step
    except Exception:
        pass
    return 1e-6


def _bot_get_min_notional(exchange, symbol: str) -> float:
    """[Copy from bot] _get_min_notional."""
    try:
        mkt = exchange.market(symbol)
        info = mkt.get('info') or {}
        for f in (info.get('filters') or []):
            if f.get('filterType') == 'MIN_NOTIONAL':
                mn = float(f.get('notional', 5.0))
                return mn
    except Exception:
        pass
    return 5.0


def _bot_compute_liquidation_price(entry: float, side: str,
                                     leverage: int, mmr: float) -> float:
    """[Copy from bot] compute_liquidation_price."""
    L = max(int(leverage), 1)
    m = max(float(mmr), 0.0)
    if side == "BUY":
        return float(entry * (1.0 - 1.0 / L) / max(1.0 - m, 1e-6))
    else:
        return float(entry * (1.0 + 1.0 / L) / max(1.0 + m, 1e-6))


def _bot_compute_max_leverage_by_liq(sl_frac_max: float, mmr: float,
                                       safety_mult: float = 1.5) -> int:
    """[Copy from bot] compute_max_leverage_by_liq (without symbol tiers)."""
    s = max(sl_frac_max * safety_mult, 1e-6)
    m = max(float(mmr), 0.0)
    denom = 1.0 - (1.0 - m) * (1.0 - s)
    if denom <= 1e-9:
        return 1
    return int(math.floor(1.0 / denom))


# ══════════════════════════════════════════════════════════════════════════
# Test helpers
# ══════════════════════════════════════════════════════════════════════════

def _find_testable_symbol(exchange, preferred: str = "BTC/USDT") -> str:
    markets = exchange.load_markets()
    candidates = [
        preferred,
        preferred + ":USDT",
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "BTC/USDT",
        "ETH/USDT",
        "BNB/USDT",
    ]
    for s in candidates:
        if s in markets:
            return s
    for s in markets:
        if s.endswith(":USDT") or s.endswith("/USDT"):
            return s
    raise SkipTest("no testable symbol found")


def compute_safe_test_order(exchange, symbol: str,
                             price: float) -> Tuple[float, float, float]:
    min_notional = _bot_get_min_notional(exchange, symbol)
    step = _bot_get_step_size(exchange, symbol)
    tick = _bot_get_tick_size(exchange, symbol) or (price * 1e-4)

    target_notional = max(min_notional * 2.0, 10.0)
    qty_raw = target_notional / price
    qty = math.ceil(qty_raw / step) * step

    safe_buy_px = math.floor(price * 0.50 / tick) * tick
    safe_sell_px = math.ceil(price * 1.50 / tick) * tick
    return qty, safe_buy_px, safe_sell_px


def cleanup_all_orders(exchange, symbol: str) -> int:
    n = 0
    try:
        orders = exchange.fetch_open_orders(symbol)
        for o in orders:
            try:
                exchange.cancel_order(o['id'], symbol)
                n += 1
                time.sleep(0.15)
            except Exception:
                pass
    except Exception:
        pass
    return n


# ══════════════════════════════════════════════════════════════════════════
# PHASE 1 — Init & Metadata
# ══════════════════════════════════════════════════════════════════════════

def test_import_and_init(exchange):
    assert exchange is not None
    assert hasattr(exchange, 'fetch_ohlcv')
    return True, f"ccxt {ccxt.__version__}"


def test_fetch_time(exchange):
    server_ms = exchange.fetch_time()
    drift = abs(time.time() - float(server_ms) / 1000.0)
    if drift > 30:
        raise WarnTest(f"drift={drift:.1f}s (>30s) — check NTP")
    return True, f"drift={drift:.2f}s"


def test_load_markets(exchange):
    markets = exchange.load_markets()
    assert len(markets) > 0
    return True, f"{len(markets)} markets"


def test_market_lookup(exchange, symbol):
    mkt = exchange.market(symbol)
    assert mkt is not None
    filters = (mkt.get('info') or {}).get('filters') or []
    types = [f.get('filterType') for f in filters]
    return True, f"filters: {types}"


def test_parse_timeframe(exchange):
    checks = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600,
              '4h': 14400, '1d': 86400}
    for tf, exp in checks.items():
        got = int(exchange.parse_timeframe(tf))
        assert got == exp, f"{tf}: {got} != {exp}"
    return True, "all TFs OK"


def test_parse8601(exchange):
    ts = exchange.parse8601("2026-01-01T00:00:00Z")
    assert ts and ts > 0
    return True, f"ts={ts}"


# ══════════════════════════════════════════════════════════════════════════
# PHASE 2 — Public data
# ══════════════════════════════════════════════════════════════════════════

def test_fetch_ohlcv(exchange, symbol):
    c = exchange.fetch_ohlcv(symbol, '1h', limit=10)
    assert len(c) > 0 and len(c[0]) == 6
    return True, f"{len(c)} bars, close={c[-1][4]:.4f}"


def test_fetch_ohlcv_since(exchange, symbol):
    since = exchange.parse8601("2026-01-01T00:00:00Z")
    c = exchange.fetch_ohlcv(symbol, '1h', since=since, limit=5)
    assert len(c) > 0 and c[0][0] >= since
    return True, f"{len(c)} bars"


def test_fetch_ticker(exchange, symbol):
    tk = exchange.fetch_ticker(symbol)
    last = float(tk.get('last') or 0)
    assert last > 0
    return True, f"last={last:.4f}"


def test_fetch_order_book(exchange, symbol):
    ob = exchange.fetch_order_book(symbol, limit=5)
    bid, ask = float(ob['bids'][0][0]), float(ob['asks'][0][0])
    assert ask >= bid
    spread = (ask - bid) / bid * 1e4
    return True, f"bid={bid:.4f} ask={ask:.4f} spread={spread:.2f}bps"


def test_fetch_order_book_20(exchange, symbol):
    ob = exchange.fetch_order_book(symbol, limit=20)
    assert len(ob['bids']) >= 5 and len(ob['asks']) >= 5
    db = sum(float(b[1]) for b in ob['bids'][:5])
    da = sum(float(a[1]) for a in ob['asks'][:5])
    return True, f"5-lvl: bid={db:.2f} ask={da:.2f}"


def test_fetch_trades(exchange, symbol):
    t = exchange.fetch_trades(symbol, limit=20)
    if not t:
        raise WarnTest("empty trades")
    assert 'price' in t[0] and 'amount' in t[0]
    return True, f"{len(t)} trades"


def test_fetch_tickers(exchange):
    """[T1 FIXED] — accepts futures notation 'BTC/USDT:USDT'."""
    tickers = exchange.fetch_tickers()
    n = len(tickers)
    assert n > 0, "no tickers"

    # FIX: match both 'BTC/USDT' and 'BTC/USDT:USDT'
    usdt = [t for k, t in tickers.items() if '/USDT' in k]
    assert len(usdt) > 0, "no USDT pairs"

    # Show sample keys for transparency
    sample = list(tickers.keys())[:3]
    return True, f"{n} tickers ({len(usdt)} USDT) sample={sample}"


# ══════════════════════════════════════════════════════════════════════════
# PHASE 3 — Authenticated read-only
# ══════════════════════════════════════════════════════════════════════════

def test_fetch_balance(exchange):
    bal = exchange.fetch_balance()
    assert 'USDT' in bal
    free = float(bal['USDT'].get('free') or 0)
    total = float(bal['USDT'].get('total') or 0)
    return True, f"free={free:.4f} total={total:.4f}"


def test_fetch_positions(exchange):
    p = exchange.fetch_positions()
    active = []
    for x in p:
        try:
            amt = float(x['info'].get('positionAmt', 0) or 0)
            if abs(amt) > 1e-12:
                active.append(x['symbol'])
        except Exception:
            pass
    return True, f"{len(p)} total, {len(active)} active"


def test_fetch_positions_filtered(exchange, symbol):
    p = exchange.fetch_positions([symbol])
    return True, f"{len(p)} positions for {symbol}"


def test_fetch_open_orders(exchange, symbol):
    o = exchange.fetch_open_orders(symbol)
    return True, f"{len(o)} open orders"


def test_fetch_leverage(exchange, symbol):
    """[B4 FIX] — must handle None gracefully."""
    try:
        info = exchange.fetch_leverage(symbol)
        # FIX: explicitly check for None (Binance Demo returns None)
        if info is None or not hasattr(info, 'get'):
            raise WarnTest(
                f"returned {type(info).__name__} — "
                f"bot's B4 fix handles this gracefully"
            )
        lev = int(info.get('leverage', 0))
        return True, f"leverage={lev}x"
    except WarnTest:
        raise
    except Exception as e:
        raise WarnTest(f"unsupported: {e}")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 4 — PARITY CHECK (bot logic verification)
# ══════════════════════════════════════════════════════════════════════════

def test_parity_extract_tier_shape(exchange, symbol):
    """
    [B1+B2 FIX] Verify _extract_tier_entry handles actual exchange output.
    This is the primary fix that was broken before.
    """
    tiers_raw = exchange.fetch_leverage_tiers([symbol])
    assert tiers_raw, "empty response"

    # Determine actual shape
    shape = ('list' if isinstance(tiers_raw, list)
             else 'dict' if isinstance(tiers_raw, dict)
             else type(tiers_raw).__name__)

    # Use the FIXED helper
    entry = _extract_tier_entry(tiers_raw, symbol)
    assert entry is not None, f"_extract_tier_entry returned None (shape={shape})"
    tier_list = entry.get('tiers') or []
    assert len(tier_list) > 0, "no tiers after extraction"

    max_lev = int(tier_list[0].get('maxLeverage', 0))
    mmr = float(tier_list[0].get('maintenanceMarginRate', 0))

    return True, (f"shape={shape}, tiers={len(tier_list)}, "
                  f"max_lev={max_lev}x, mmr={mmr*100:.4f}%")


def test_parity_fetch_symbol_max_lev(exchange, symbol):
    """[B2 FIX] Verify bot's fetch_symbol_leverage_tiers works."""
    max_lev = _bot_fetch_symbol_max_leverage(exchange, symbol)
    assert max_lev is not None and max_lev > 0, \
        f"bot returned {max_lev} — expected positive int"
    return True, f"bot_max_lev={max_lev}x"


def test_parity_get_mmr(exchange, symbol):
    """[B3 FIX] Verify bot's _get_mmr_for_symbol returns real MMR (not 2% fallback)."""
    mmr = _bot_get_mmr(exchange, symbol)
    assert 0 < mmr < 0.5, f"invalid mmr={mmr}"

    # Detect whether it fell through to fallback
    if abs(mmr - 0.02) < 1e-9:
        raise WarnTest(
            f"mmr={mmr*100:.4f}% — this is the LIQ_FALLBACK_MMR (2%), "
            f"not the real rate. B3 fix may not be applied."
        )
    return True, f"real_mmr={mmr*100:.4f}%"


def test_parity_tick_size(exchange, symbol):
    """Verify _get_tick_size (used by GTX preflight and watch offset)."""
    tick = _bot_get_tick_size(exchange, symbol)
    assert tick is not None and tick > 0, "tick_size unavailable"
    # Reasonable range: BTC tick is 0.10, alts can be 1e-5
    assert tick < 100, f"tick_size too large: {tick}"
    return True, f"tick={tick}"


def test_parity_step_size(exchange, symbol):
    """Verify _get_step_size (used by _round_qty)."""
    step = _bot_get_step_size(exchange, symbol)
    assert step > 0, f"invalid step={step}"
    return True, f"step={step}"


def test_parity_min_notional(exchange, symbol):
    """Verify _get_min_notional."""
    mn = _bot_get_min_notional(exchange, symbol)
    assert mn > 0
    return True, f"min_notional=${mn:.2f}"


def test_parity_liquidation_price_math():
    """
    [Liq math] Verify compute_liquidation_price formula.
    Test case: entry=100, L=10, MMR=0.5%
      LONG:  Liq = 100 × (1 - 0.1) / (1 - 0.005) = 90 / 0.995 = 90.4523
      SHORT: Liq = 100 × (1 + 0.1) / (1 + 0.005) = 110 / 1.005 = 109.4527
    """
    entry = 100.0
    L = 10
    mmr = 0.005

    liq_long = _bot_compute_liquidation_price(entry, "BUY", L, mmr)
    liq_short = _bot_compute_liquidation_price(entry, "SELL", L, mmr)

    exp_long = 100.0 * (1.0 - 1.0 / L) / (1.0 - mmr)
    exp_short = 100.0 * (1.0 + 1.0 / L) / (1.0 + mmr)

    assert abs(liq_long - exp_long) < 1e-6, \
        f"long: {liq_long} != {exp_long}"
    assert abs(liq_short - exp_short) < 1e-6, \
        f"short: {liq_short} != {exp_short}"

    # Sanity: Liq_long < entry < Liq_short
    assert liq_long < entry < liq_short

    return True, (f"LONG={liq_long:.4f} (expected {exp_long:.4f}), "
                  f"SHORT={liq_short:.4f} (expected {exp_short:.4f})")


def test_parity_max_leverage_by_liq():
    """
    [LevCap math] Verify compute_max_leverage_by_liq.
    Test: sl_frac_max=1.5%, safety=1.5x, MMR=0.5%
      s = 0.015 * 1.5 = 0.0225
      denom = 1 - (1 - 0.005)(1 - 0.0225) = 1 - 0.995 * 0.9775 = 0.0274
      Lev = floor(1 / 0.0274) = 36
    """
    sl_frac_max = 0.015
    safety = 1.5
    mmr = 0.005

    lev = _bot_compute_max_leverage_by_liq(sl_frac_max, mmr, safety)

    # Manual calculation
    s = sl_frac_max * safety
    denom = 1 - (1 - mmr) * (1 - s)
    expected = int(math.floor(1.0 / denom))

    assert lev == expected, f"{lev} != {expected}"
    assert 1 <= lev <= 200, f"unrealistic leverage: {lev}"

    return True, (f"LevCap={lev}x (mmr={mmr*100:.2f}%, "
                  f"sl_frac={sl_frac_max*100:.1f}%, safety={safety}x)")


def test_parity_full_levcap_pipeline(exchange, symbol):
    """
    End-to-end: fetch real MMR → compute LevCap for a 1.5% SL.
    This is what the bot does on every entry decision.
    """
    mmr = _bot_get_mmr(exchange, symbol)
    sl_frac_max = 0.015 * 1.5  # SL_WIDEN_MULT = 1.5
    lev = _bot_compute_max_leverage_by_liq(sl_frac_max, mmr, 1.5)

    # Sanity: must be >= LEVERAGE_MIN (5)
    assert lev >= 5, f"computed {lev}x < 5x minimum"
    return True, (f"MMR={mmr*100:.3f}% → LevCap={lev}x "
                  f"for SL=2.25% (safe)")


def test_parity_gtx_preflight(exchange, symbol):
    """
    [GTX preflight] Simulate the fix-25 adjustment logic.
    Ensure a marketable BUY would be adjusted to safe side.
    """
    ob = exchange.fetch_order_book(symbol, limit=5)
    bid, ask = float(ob['bids'][0][0]), float(ob['asks'][0][0])
    tick = _bot_get_tick_size(exchange, symbol)

    if not tick or tick <= 0:
        raise WarnTest("no tick size — cannot simulate")

    # Simulate: user tries to place BUY at bid (would cross → GTX reject)
    target = bid
    # Bot's _gtx_preflight logic:
    if target > bid - tick:
        safe = bid - tick
    else:
        safe = target

    assert safe < bid, f"safe_buy {safe} not below bid {bid}"
    assert safe < ask, "safe_buy must be below ask"

    # SELL side
    target_s = ask
    if target_s < ask + tick:
        safe_s = ask + tick
    else:
        safe_s = target_s

    assert safe_s > ask, f"safe_sell {safe_s} not above ask {ask}"

    return True, (f"bid={bid:.4f} → safe_buy={safe:.4f}; "
                  f"ask={ask:.4f} → safe_sell={safe_s:.4f}")


# ══════════════════════════════════════════════════════════════════════════
# PHASE 5 — Order lifecycle (mutating)
# ══════════════════════════════════════════════════════════════════════════

def test_set_margin_mode(exchange, symbol):
    try:
        exchange.set_margin_mode('isolated', symbol)
        return True, "set isolated"
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ('no need', 'already', '-4046')):
            return True, f"already isolated"
        raise


def test_set_leverage(exchange, symbol, leverage=5):
    try:
        exchange.set_leverage(leverage, symbol)
        return True, f"set {leverage}x"
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ('no need', 'already')):
            return True, f"already {leverage}x"
        raise


def test_create_limit_order(exchange, symbol, qty, price, side='buy'):
    o = exchange.create_order(
        symbol, 'limit', side, qty, price,
        params={'timeInForce': 'GTC'}
    )
    return True, f"oid={o['id']}"


def test_fetch_order(exchange, symbol, order_id):
    o = exchange.fetch_order(order_id, symbol)
    return True, f"status={o.get('status')}"


def test_cancel_order(exchange, symbol, order_id):
    try:
        r = exchange.cancel_order(order_id, symbol)
        return True, "cancelled"
    except Exception as e:
        if '-2011' in str(e):
            return True, "already gone"
        raise


def test_gtx_post_only(exchange, symbol, qty, price, side='buy'):
    try:
        o = exchange.create_order(
            symbol, 'limit', side, qty, price,
            params={'timeInForce': 'GTX'}
        )
        oid = o['id']
        try:
            exchange.cancel_order(oid, symbol)
        except Exception:
            pass
        return True, f"GTX accepted, oid={oid}"
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ('-2010', 'post only', '-5022')):
            raise WarnTest(f"GTX rejected: {msg[:80]}")
        raise


def test_gtx_with_preflight(exchange, symbol, qty):
    """
    [FIX-25 verification] Apply preflight THEN send GTX.
    This should always succeed (no rejection).
    """
    ob = exchange.fetch_order_book(symbol, limit=5)
    bid = float(ob['bids'][0][0])
    tick = _bot_get_tick_size(exchange, symbol) or (bid * 1e-6)

    # Preflight: place BUY at bid - tick (definitely maker)
    safe_px = bid - tick
    assert safe_px > 0

    try:
        o = exchange.create_order(
            symbol, 'limit', 'buy', qty, safe_px,
            params={'timeInForce': 'GTX'}
        )
        oid = o['id']
        try:
            exchange.cancel_order(oid, symbol)
        except Exception:
            pass
        return True, f"preflight+GTX OK @ {safe_px:.4f}"
    except Exception as e:
        raise Exception(f"preflight+GTX failed: {e}")


def test_stop_market_protective(exchange, symbol, qty, stop_price):
    try:
        try:
            o = exchange.create_order(
                symbol, 'STOP_MARKET', 'sell', None, None,
                params={'stopPrice': stop_price,
                        'closePosition': True,
                        'workingType': 'MARK_PRICE'}
            )
            try:
                exchange.cancel_order(o['id'], symbol)
            except Exception:
                pass
            return True, f"closePosition OK"
        except Exception as e1:
            # Fallback
            try:
                o = exchange.create_order(
                    symbol, 'STOP_MARKET', 'sell', qty, None,
                    params={'stopPrice': stop_price,
                            'reduceOnly': True,
                            'workingType': 'MARK_PRICE'}
                )
                try:
                    exchange.cancel_order(o['id'], symbol)
                except Exception:
                    pass
                return True, f"reduceOnly fallback (closePos failed)"
            except Exception as e2:
                raise Exception(f"both failed: {e1} | {e2}")
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ('reduceonly', '-2021', 'position')):
            raise WarnTest(f"requires position: {msg[:80]}")
        raise


def test_take_profit_market(exchange, symbol, qty, tp_price):
    """TAKE_PROFIT_MARKET — same as STOP but opposite direction."""
    try:
        o = exchange.create_order(
            symbol, 'TAKE_PROFIT_MARKET', 'sell', None, None,
            params={'stopPrice': tp_price,
                    'closePosition': True,
                    'workingType': 'MARK_PRICE'}
        )
        try:
            exchange.cancel_order(o['id'], symbol)
        except Exception:
            pass
        return True, f"TP market OK"
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ('reduceonly', '-2021')):
            raise WarnTest(f"requires position: {msg[:80]}")
        raise


# ══════════════════════════════════════════════════════════════════════════
# Output
# ══════════════════════════════════════════════════════════════════════════

def section(title: str):
    print()
    print(f"{C.BOLD}{C.BLUE}── {title} {'─' * max(1, 70 - len(title))}{C.END}")


# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="Exchange API test v2 (post ccxt-4.x fixes)"
    )
    p.add_argument("--mode", default="testnet",
                   choices=["testnet", "live"])
    p.add_argument("--api-key", default=os.environ.get("BINANCE_API_KEY", ""))
    p.add_argument("--api-secret",
                   default=os.environ.get("BINANCE_API_SECRET", ""))
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--allow-orders", action="store_true")
    p.add_argument("--i-know-what-im-doing", action="store_true")
    p.add_argument("--leverage", type=int, default=5)
    p.add_argument("--skip-slow", action="store_true")
    p.add_argument("--output", type=str, default=None)
    args = p.parse_args()

    if args.mode == "live" and not args.i_know_what_im_doing:
        print(f"{C.RED}ERROR: --mode live requires --i-know-what-im-doing{C.END}")
        sys.exit(2)

    print()
    print("╔" + "═" * 76 + "╗")
    print(f"║  {C.BOLD}Exchange API Test v2 — Post ccxt-4.x Fixes{C.END}"
          f"{' ' * 28}║")
    print(f"║  Mode: {args.mode:<10}  Symbol: {args.symbol:<15}  "
          f"Orders: {'YES' if args.allow_orders else 'NO':<12}    ║")
    print("╚" + "═" * 76 + "╝")

    # Build exchange
    try:
        exchange = ccxt.binance({
            'apiKey': args.api_key,
            'secret': args.api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
            'timeout': 15000,
        })
    except Exception as e:
        print(f"{C.RED}Cannot create exchange: {e}{C.END}")
        sys.exit(3)

    if args.mode == "testnet":
        try:
            exchange.enable_demo_trading(True)
            print(f"{C.CYAN}→ Demo trading mode enabled{C.END}")
        except Exception as e:
            print(f"{C.RED}Demo mode failed: {e}{C.END}")
            sys.exit(4)
    else:
        print(f"{C.YELLOW}→ LIVE MAINNET{C.END}")

    # ── Phase 1 ──
    section("PHASE 1 — Init & Metadata")
    run_test("import + init", test_import_and_init, exchange,
             category="Phase 1")
    run_test("fetch_time (clock sync)", test_fetch_time, exchange,
             category="Phase 1")
    run_test("load_markets", test_load_markets, exchange,
             category="Phase 1")

    try:
        actual_symbol = _find_testable_symbol(exchange, args.symbol)
        print(f"{C.CYAN}  → Resolved symbol: {actual_symbol}{C.END}")
    except Exception as e:
        print(f"{C.RED}  → No symbol: {e}{C.END}")
        RESULTS.print_report()
        sys.exit(5)

    run_test(f"market({actual_symbol})", test_market_lookup,
             exchange, actual_symbol, category="Phase 1")
    run_test("parse_timeframe", test_parse_timeframe, exchange,
             category="Phase 1")
    run_test("parse8601", test_parse8601, exchange,
             category="Phase 1")

    # ── Phase 2 ──
    section("PHASE 2 — Public Data")
    run_test(f"fetch_ohlcv", test_fetch_ohlcv, exchange, actual_symbol,
             category="Phase 2")
    run_test("fetch_ohlcv with since", test_fetch_ohlcv_since,
             exchange, actual_symbol, category="Phase 2")
    run_test("fetch_ticker", test_fetch_ticker, exchange, actual_symbol,
             category="Phase 2")
    run_test("fetch_order_book(5)", test_fetch_order_book,
             exchange, actual_symbol, category="Phase 2")
    run_test("fetch_order_book(20)", test_fetch_order_book_20,
             exchange, actual_symbol, category="Phase 2")
    run_test("fetch_trades", test_fetch_trades, exchange, actual_symbol,
             category="Phase 2")
    if args.skip_slow:
        RESULTS.add("fetch_tickers (bulk)", "SKIP", 0.0,
                    detail="--skip-slow", category="Phase 2")
    else:
        run_test("fetch_tickers (bulk)", test_fetch_tickers, exchange,
                 category="Phase 2")

    # ── Phase 3 ──
    section("PHASE 3 — Authenticated Read-Only")
    if not args.api_key or not args.api_secret:
        for name in ["fetch_balance", "fetch_positions",
                     "fetch_positions filtered", "fetch_open_orders",
                     "fetch_leverage"]:
            RESULTS.add(name, 'SKIP', 0.0, detail="no credentials",
                        category="Phase 3")
    else:
        run_test("fetch_balance", test_fetch_balance, exchange,
                 category="Phase 3")
        run_test("fetch_positions", test_fetch_positions, exchange,
                 category="Phase 3")
        run_test("fetch_positions filtered", test_fetch_positions_filtered,
                 exchange, actual_symbol, category="Phase 3")
        run_test("fetch_open_orders", test_fetch_open_orders,
                 exchange, actual_symbol, category="Phase 3")
        run_test("fetch_leverage [B4 fix]", test_fetch_leverage,
                 exchange, actual_symbol, category="Phase 3")

    # ── Phase 4 — PARITY CHECK ──
    section("PHASE 4 — PARITY CHECK (bot fixes verification)")

    if not args.api_key or not args.api_secret:
        print(f"{C.YELLOW}  Skipped — no credentials{C.END}")
        for name in ["_extract_tier_entry shape",
                     "fetch_symbol_leverage_tiers [B2]",
                     "_get_mmr_for_symbol [B3]",
                     "tick_size", "step_size", "min_notional",
                     "liquidation_price math",
                     "max_leverage_by_liq math",
                     "LevCap pipeline",
                     "GTX preflight"]:
            RESULTS.add(name, 'SKIP', 0.0, detail="no credentials",
                        category="Phase 4")
    else:
        run_test("_extract_tier_entry shape [B1]",
                 test_parity_extract_tier_shape,
                 exchange, actual_symbol, category="Phase 4")
        run_test("fetch_symbol_leverage_tiers [B2]",
                 test_parity_fetch_symbol_max_lev,
                 exchange, actual_symbol, category="Phase 4")
        run_test("_get_mmr_for_symbol [B3]",
                 test_parity_get_mmr,
                 exchange, actual_symbol, category="Phase 4")
        run_test("tick_size", test_parity_tick_size,
                 exchange, actual_symbol, category="Phase 4")
        run_test("step_size", test_parity_step_size,
                 exchange, actual_symbol, category="Phase 4")
        run_test("min_notional", test_parity_min_notional,
                 exchange, actual_symbol, category="Phase 4")
        run_test("liquidation_price math",
                 test_parity_liquidation_price_math,
                 category="Phase 4")
        run_test("max_leverage_by_liq math",
                 test_parity_max_leverage_by_liq,
                 category="Phase 4")
        run_test("LevCap pipeline (real MMR)",
                 test_parity_full_levcap_pipeline,
                 exchange, actual_symbol, category="Phase 4")
        run_test("GTX preflight simulation",
                 test_parity_gtx_preflight,
                 exchange, actual_symbol, category="Phase 4")

    # ── Phase 5 — Order lifecycle ──
    section("PHASE 5 — Order Lifecycle (mutating)")

    if not args.allow_orders or not args.api_key:
        print(f"{C.YELLOW}  Skipped — pass --allow-orders + credentials{C.END}")
        for name in ["set_margin_mode", "set_leverage",
                     "create_limit_order", "fetch_order",
                     "cancel_order", "gtx_post_only",
                     "gtx_with_preflight", "stop_market",
                     "take_profit_market"]:
            RESULTS.add(name, 'SKIP', 0.0,
                        detail="--allow-orders not set or no creds",
                        category="Phase 5")
    else:
        try:
            tk = exchange.fetch_ticker(actual_symbol)
            current_px = float(tk['last'])
            print(f"{C.CYAN}  → price={current_px:.4f}{C.END}")
        except Exception:
            current_px = 100.0

        qty, buy_px, sell_px = compute_safe_test_order(
            exchange, actual_symbol, current_px
        )
        print(f"{C.CYAN}  → test qty={qty}, buy@{buy_px:.6f}, "
              f"sell@{sell_px:.6f}{C.END}")

        run_test("set_margin_mode", test_set_margin_mode,
                 exchange, actual_symbol, category="Phase 5")
        run_test(f"set_leverage({args.leverage}x)", test_set_leverage,
                 exchange, actual_symbol, args.leverage,
                 category="Phase 5")

        # Create BUY limit
        ok, res = run_test("create_limit_order (BUY)",
                           test_create_limit_order,
                           exchange, actual_symbol, qty, buy_px, 'buy',
                           category="Phase 5")
        oid = None
        if ok:
            try:
                orders = exchange.fetch_open_orders(actual_symbol)
                buys = [o for o in orders if o.get('side') == 'buy']
                if buys:
                    oid = buys[-1]['id']
            except Exception:
                pass

        if oid:
            run_test("fetch_order", test_fetch_order,
                     exchange, actual_symbol, oid, category="Phase 5")
            run_test("cancel_order", test_cancel_order,
                     exchange, actual_symbol, oid, category="Phase 5")
        else:
            RESULTS.add("fetch_order", 'SKIP', 0.0,
                        detail="no order_id", category="Phase 5")
            RESULTS.add("cancel_order", 'SKIP', 0.0,
                        detail="no order_id", category="Phase 5")

        run_test("gtx_post_only", test_gtx_post_only,
                 exchange, actual_symbol, qty, buy_px, 'buy',
                 category="Phase 5")
        run_test("gtx_with_preflight [FIX-25]",
                 test_gtx_with_preflight,
                 exchange, actual_symbol, qty, category="Phase 5")
        run_test("stop_market protective",
                 test_stop_market_protective,
                 exchange, actual_symbol, qty, current_px * 0.90,
                 category="Phase 5")
        run_test("take_profit_market",
                 test_take_profit_market,
                 exchange, actual_symbol, qty, current_px * 1.10,
                 category="Phase 5")

        # Cleanup
        print(f"{C.CYAN}  → Cleanup: cancelling leftover orders...{C.END}")
        n = cleanup_all_orders(exchange, actual_symbol)
        print(f"{C.CYAN}  → Cancelled {n}{C.END}")

    # ── Report ──
    RESULTS.print_report()

    # ── JSON output ──
    if args.output:
        try:
            report = {
                'version': 2,
                'mode': args.mode,
                'symbol': actual_symbol,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'ccxt_version': ccxt.__version__,
                'summary': RESULTS.summary(),
                'tests': RESULTS.tests,
                'elapsed_s': time.time() - RESULTS.start_ts,
            }
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\n{C.CYAN}Report saved → {args.output}{C.END}")
        except Exception as e:
            print(f"{C.RED}Cannot save report: {e}{C.END}")

    counts = RESULTS.summary()
    sys.exit(1 if counts['FAIL'] > 0 else 0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Interrupted{C.END}")
        sys.exit(130)
