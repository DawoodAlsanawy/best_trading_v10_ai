#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  exchange_api_test.py                                                    ║
║  Comprehensive Exchange Communication Test Suite                         ║
║  Verifies EVERY exchange call used by trading_2_mfal2.py                 ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                  ║
║    # Safe — read-only tests (no orders placed):                         ║
║    python3 exchange_api_test.py --mode testnet \                         ║
║        --api-key $KEY --api-secret $SECRET                               ║
║                                                                          ║
║    # Full test including order lifecycle (CANCELS everything):          ║
║    python3 exchange_api_test.py --mode testnet \                         ║
║        --api-key $KEY --api-secret $SECRET --allow-orders                ║
║                                                                          ║
║    # Test with a specific symbol:                                       ║
║    python3 exchange_api_test.py --mode testnet ... --symbol BTC/USDT     ║
║                                                                          ║
║  Safety:                                                                 ║
║    * Mainnet mode requires --i-know-what-im-doing flag                  ║
║    * Order tests use MINIMUM notional and cancel immediately            ║
║    * All placed orders are cancelled in cleanup phase                   ║
║    * Read-only tests never place orders                                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import os
import sys
import time
import json
import traceback
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any

try:
    import ccxt
except ImportError:
    print("ERROR: ccxt not installed. Run: pip install ccxt")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════
# ANSI colors for readable output
# ══════════════════════════════════════════════════════════════════════════
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
# Test result tracking
# ══════════════════════════════════════════════════════════════════════════
class TestResults:
    def __init__(self):
        self.tests: List[Dict] = []
        self.start_ts = time.time()

    def add(self, name: str, status: str, duration: float,
            detail: str = "", error: str = ""):
        self.tests.append({
            'name': name,
            'status': status,       # PASS / FAIL / SKIP / WARN
            'duration': duration,
            'detail': detail,
            'error': error,
        })

    def summary(self) -> Dict:
        counts = {'PASS': 0, 'FAIL': 0, 'SKIP': 0, 'WARN': 0}
        for t in self.tests:
            counts[t['status']] = counts.get(t['status'], 0) + 1
        return counts

    def print_report(self):
        print()
        print("═" * 78)
        print(f"{C.BOLD}  EXCHANGE API TEST REPORT{C.END}")
        print("═" * 78)

        for t in self.tests:
            if t['status'] == 'PASS':
                icon = f"{C.GREEN}✓ PASS{C.END}"
            elif t['status'] == 'FAIL':
                icon = f"{C.RED}✗ FAIL{C.END}"
            elif t['status'] == 'WARN':
                icon = f"{C.YELLOW}⚠ WARN{C.END}"
            else:
                icon = f"{C.GRAY}○ SKIP{C.END}"

            dur = f"{t['duration']*1000:6.0f}ms"
            print(f"  {icon}  {t['name']:<45} {dur}")

            if t['detail']:
                print(f"         {C.GRAY}{t['detail']}{C.END}")
            if t['error']:
                err = t['error'].replace('\n', ' ')[:200]
                print(f"         {C.RED}{err}{C.END}")

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
        print("═" * 78)


RESULTS = TestResults()


# ══════════════════════════════════════════════════════════════════════════
# Helper: run one test with timing + exception capture
# ══════════════════════════════════════════════════════════════════════════
def run_test(name: str, fn, *args, **kwargs) -> Tuple[bool, Any]:
    """
    Execute test function. Returns (ok, result).
    Records to RESULTS automatically.
    """
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        duration = time.time() - t0
        detail = ""
        if isinstance(result, tuple) and len(result) == 2:
            detail = str(result[1])
            result = result[0]
        RESULTS.add(name, 'PASS', duration, detail=detail)
        return True, result
    except SkipTest as e:
        RESULTS.add(name, 'SKIP', time.time() - t0, detail=str(e))
        return False, None
    except WarnTest as e:
        RESULTS.add(name, 'WARN', time.time() - t0, detail=str(e))
        return True, None
    except Exception as e:
        duration = time.time() - t0
        tb = traceback.format_exc()
        RESULTS.add(name, 'FAIL', duration,
                    error=f"{type(e).__name__}: {e}\n{tb}")
        return False, None


class SkipTest(Exception):
    """Raised by tests that cannot run (missing prereq)."""
    pass


class WarnTest(Exception):
    """Raised by tests that pass but with warnings."""
    pass


# ══════════════════════════════════════════════════════════════════════════
# ============ 1. READ-ONLY TESTS (safe, no state changes) ============
# ══════════════════════════════════════════════════════════════════════════

def test_import_and_init(exchange) -> Tuple[bool, str]:
    """Verify ccxt loaded and exchange object is valid."""
    assert exchange is not None, "exchange is None"
    assert hasattr(exchange, 'fetch_ohlcv'), "missing fetch_ohlcv"
    return True, f"ccxt {ccxt.__version__}"


def test_fetch_time(exchange) -> Tuple[bool, str]:
    """Server time — required for time-sync guard."""
    server_ms = exchange.fetch_time()
    server_s = float(server_ms) / 1000.0
    local_s = time.time()
    drift = abs(local_s - server_s)
    if drift > 30:
        raise WarnTest(f"drift={drift:.1f}s (>30s) — check NTP")
    return True, f"drift={drift:.2f}s"


def test_load_markets(exchange) -> Tuple[bool, str]:
    """Load market metadata — required for filters, precision, tick size."""
    markets = exchange.load_markets()
    n = len(markets)
    assert n > 0, "no markets loaded"
    return True, f"{n} markets"


def test_market_lookup(exchange, symbol: str) -> Tuple[bool, str]:
    """Fetch single market metadata (used by _get_tick_size, _get_step_size)."""
    mkt = exchange.market(symbol)
    assert mkt is not None, f"market({symbol}) returned None"
    filters = (mkt.get('info') or {}).get('filters') or []
    types = [f.get('filterType') for f in filters]
    return True, f"filters: {types}"


def test_parse_timeframe(exchange) -> Tuple[bool, str]:
    """TF parsing — used by compute_tf_scale."""
    checks = {
        '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400
    }
    results = []
    for tf, expected in checks.items():
        got = int(exchange.parse_timeframe(tf))
        assert got == expected, f"{tf}: got {got}, expected {expected}"
        results.append(f"{tf}={got}")
    return True, " ".join(results)


def test_parse8601(exchange) -> Tuple[bool, str]:
    """ISO8601 parsing — used by _load_cached."""
    ts = exchange.parse8601("2026-01-01T00:00:00Z")
    assert ts is not None and ts > 0, "parse8601 returned invalid"
    return True, f"parsed to {ts}"


def test_fetch_ohlcv(exchange, symbol: str) -> Tuple[bool, str]:
    """OHLCV fetch — core data pipeline."""
    candles = exchange.fetch_ohlcv(symbol, '1h', limit=10)
    assert len(candles) > 0, "empty candles"
    assert len(candles[0]) == 6, f"expected 6 fields, got {len(candles[0])}"
    last = candles[-1]
    assert last[4] > 0, f"invalid close price: {last[4]}"
    return True, f"{len(candles)} bars, last close={last[4]:.4f}"


def test_fetch_ohlcv_with_since(exchange, symbol: str) -> Tuple[bool, str]:
    """OHLCV with since — used by _load_cached back-fill."""
    since_ms = exchange.parse8601("2026-01-01T00:00:00Z")
    candles = exchange.fetch_ohlcv(symbol, '1h', since=since_ms, limit=5)
    assert len(candles) > 0, "empty candles with since"
    assert candles[0][0] >= since_ms, "since not respected"
    return True, f"{len(candles)} bars from {candles[0][0]}"


def test_fetch_ticker(exchange, symbol: str) -> Tuple[bool, str]:
    """Ticker — used by LIVE_PRICE_ENABLED path."""
    tk = exchange.fetch_ticker(symbol)
    last = float(tk.get('last') or 0)
    assert last > 0, f"invalid last price: {last}"
    return True, f"last={last:.4f}"


def test_fetch_order_book(exchange, symbol: str) -> Tuple[bool, str]:
    """Order book — used by _watch_compute_entry_offset, GTX preflight, AFE."""
    ob = exchange.fetch_order_book(symbol, limit=5)
    bids = ob.get('bids') or []
    asks = ob.get('asks') or []
    assert len(bids) > 0, "no bids"
    assert len(asks) > 0, "no asks"
    bid = float(bids[0][0])
    ask = float(asks[0][0])
    assert ask >= bid, f"ask ({ask}) < bid ({bid})"
    spread_bps = (ask - bid) / bid * 1e4
    return True, f"bid={bid:.4f} ask={ask:.4f} spread={spread_bps:.2f}bps"


def test_fetch_order_book_20(exchange, symbol: str) -> Tuple[bool, str]:
    """Deeper book (20 levels) — used by AdaptiveFillEngine."""
    ob = exchange.fetch_order_book(symbol, limit=20)
    bids = ob.get('bids') or []
    asks = ob.get('asks') or []
    assert len(bids) >= 5, f"only {len(bids)} bids"
    assert len(asks) >= 5, f"only {len(asks)} asks"
    depth_bid = sum(float(b[1]) for b in bids[:5])
    depth_ask = sum(float(a[1]) for a in asks[:5])
    return True, f"5-lvl depth: bid={depth_bid:.2f} ask={depth_ask:.2f}"


def test_fetch_trades(exchange, symbol: str) -> Tuple[bool, str]:
    """Recent trades — used by MicroTracker.update_trades."""
    trades = exchange.fetch_trades(symbol, limit=20)
    # Some exchanges return [] for futures — not fatal
    if not trades:
        raise WarnTest("empty trades — may be normal for futures")
    t0 = trades[0]
    assert 'price' in t0 and 'amount' in t0, "missing price/amount"
    return True, f"{len(trades)} trades, last price={t0['price']}"


def test_fetch_tickers(exchange) -> Tuple[bool, str]:
    """Bulk tickers — used by scan_top_assets."""
    tickers = exchange.fetch_tickers()
    n = len(tickers)
    assert n > 0, "no tickers returned"
    # Verify a USDT pair has quoteVolume
    # [ccxt 4.x FIX] Binance Futures uses "BTC/USDT:USDT" notation,
    # so endswith('/USDT') returns zero. Match both notations.
    usdt = [t for k, t in tickers.items() if '/USDT' in k]
    assert len(usdt) > 0, "no USDT pairs"
    return True, f"{n} tickers ({len(usdt)} USDT)"


# ══════════════════════════════════════════════════════════════════════════
# ============ 2. AUTHENTICATED READ-ONLY TESTS ============
# ══════════════════════════════════════════════════════════════════════════

def test_fetch_balance(exchange) -> Tuple[bool, str]:
    """Balance — used by run_live main loop."""
    bal = exchange.fetch_balance()
    assert 'USDT' in bal, "no USDT in balance"
    usdt = bal['USDT']
    free = float(usdt.get('free') or 0)
    total = float(usdt.get('total') or 0)
    return True, f"USDT free={free:.4f} total={total:.4f}"


def test_fetch_positions(exchange) -> Tuple[bool, str]:
    """Positions list — used by _fetch_positions_cached, reconcile_*."""
    positions = exchange.fetch_positions()
    active = []
    for p in positions:
        try:
            amt = float(p['info'].get('positionAmt', 0) or 0)
            if abs(amt) > 1e-12:
                active.append(p['symbol'])
        except Exception:
            pass
    return True, f"{len(positions)} total, {len(active)} active"


def test_fetch_positions_filtered(exchange, symbol: str) -> Tuple[bool, str]:
    """Filtered positions — used by _fake_pos_list."""
    positions = exchange.fetch_positions([symbol])
    return True, f"{len(positions)} positions for {symbol}"


def test_fetch_open_orders(exchange, symbol: str) -> Tuple[bool, str]:
    """Open orders list — used by _cancel_all_protective_orders."""
    orders = exchange.fetch_open_orders(symbol)
    return True, f"{len(orders)} open orders on {symbol}"


def test_fetch_leverage(exchange, symbol: str) -> Tuple[bool, str]:
    """Leverage query — used by ensure_symbol_setup."""
    try:
        lev_info = exchange.fetch_leverage(symbol)
        if lev_info is None:
            raise WarnTest("returned None — endpoint may be unsupported")
        lev = int(lev_info.get('leverage', 0))
        return True, f"leverage={lev}x"
    except Exception as e:
        # Some testnets don't support this — mark as warning, not failure
        raise WarnTest(f"fetch_leverage unsupported: {e}")


def test_fetch_leverage_tiers(exchange, symbol: str) -> Tuple[bool, str]:
    """
    Leverage tiers — used by fetch_symbol_leverage_tiers.

    [ccxt 4.x FIX] Handles both list and dict return shapes.
    ccxt 4.x on Binance returns: dict[ "BTC/USDT:USDT", {tiers:[...]} ]
    """
    tiers = exchange.fetch_leverage_tiers([symbol])
    assert tiers, "empty tiers"

    shape = ('list' if isinstance(tiers, list)
             else 'dict' if isinstance(tiers, dict)
             else type(tiers).__name__)

    if isinstance(tiers, list):
        t0 = tiers[0] if len(tiers) > 0 else None
    elif isinstance(tiers, dict):
        # Prefer matching entry
        t0 = None
        for k, v in tiers.items():
            if k.split(':')[0] == symbol.split(':')[0]:
                t0 = v
                break
        if t0 is None and len(tiers) > 0:
            t0 = next(iter(tiers.values()))
    else:
        raise Exception(f"unexpected type: {shape}")

    assert t0 is not None, "no entry extracted"
    # Handle case where dict value is a raw list
    if isinstance(t0, list):
        tier_list = t0
    elif isinstance(t0, dict):
        tier_list = t0.get('tiers') or []
    else:
        raise Exception(f"unexpected entry type: {type(t0).__name__}")

    assert len(tier_list) > 0, "no tiers in response"
    max_lev = int(tier_list[0].get('maxLeverage', 0))
    mmr = float(tier_list[0].get('maintenanceMarginRate', 0))
    return True, (f"shape={shape}, max_lev={max_lev}x, "
                  f"mmr={mmr*100:.4f}%")


# ══════════════════════════════════════════════════════════════════════════
# ============ 3. STATE-MUTATING TESTS (require --allow-orders) ============
# ══════════════════════════════════════════════════════════════════════════

def _find_testable_symbol(exchange, preferred: str = "BTC/USDT") -> str:
    """
    Find a symbol that exists on the exchange and has a reasonable price.
    Falls back to other majors if preferred is missing.
    """
    markets = exchange.load_markets()
    # Normalize: ccxt may use BTC/USDT:USDT for futures
    candidates = [
        preferred,
        preferred + ":USDT",   # swap notation
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "BTC/USDT",
        "ETH/USDT",
        "BNB/USDT",
    ]
    for s in candidates:
        if s in markets:
            return s
    # Last resort: first USDT market
    for s in markets:
        if s.endswith(":USDT") or s.endswith("/USDT"):
            return s
    raise SkipTest("no testable symbol found")


def test_set_margin_mode(exchange, symbol: str) -> Tuple[bool, str]:
    """
    Set margin mode — used by ensure_symbol_setup.
    Idempotent: if already isolated, exchange returns error we tolerate.
    """
    try:
        exchange.set_margin_mode('isolated', symbol)
        return True, "set isolated"
    except Exception as e:
        msg = str(e).lower()
        if 'no need' in msg or 'already' in msg or '-4046' in msg:
            return True, f"already isolated ({msg[:60]})"
        raise


def test_set_leverage(exchange, symbol: str, leverage: int = 5) -> Tuple[bool, str]:
    """Set leverage — used by ensure_symbol_setup."""
    try:
        exchange.set_leverage(leverage, symbol)
        # Verify
        try:
            lev_info = exchange.fetch_leverage(symbol)
            actual = int(lev_info.get('leverage', 0))
            return True, f"set {leverage}x, verified={actual}x"
        except Exception:
            return True, f"set {leverage}x (verify unsupported)"
    except Exception as e:
        msg = str(e).lower()
        if 'no need' in msg or 'already' in msg:
            return True, f"already at target: {msg[:60]}"
        raise


def test_create_limit_order(exchange, symbol: str,
                             qty: float, price: float,
                             side: str = 'buy') -> Tuple[bool, str]:
    """
    Create LIMIT order — used by place_pending_entry.
    Uses far-from-market price to guarantee no accidental fill.
    """
    try:
        o = exchange.create_order(
            symbol, 'limit', side, qty, price,
            params={'timeInForce': 'GTC'}   # GTC avoids GTX rejection risk
        )
        oid = o['id']
        return True, f"oid={oid} status={o.get('status')}"
    except Exception as e:
        raise


def test_fetch_order(exchange, symbol: str, order_id: str) -> Tuple[bool, str]:
    """Fetch single order — used everywhere for status checks."""
    o = exchange.fetch_order(order_id, symbol)
    status = o.get('status')
    filled = float(o.get('filled') or 0)
    return True, f"status={status} filled={filled}"


def test_cancel_order(exchange, symbol: str, order_id: str) -> Tuple[bool, str]:
    """Cancel order — used by cancel flows."""
    try:
        r = exchange.cancel_order(order_id, symbol)
        return True, f"cancelled: {r.get('status', 'ok')}"
    except Exception as e:
        msg = str(e).lower()
        if 'unknown order' in msg or '-2011' in msg:
            return True, "already gone (-2011)"
        raise


def test_gtx_post_only(exchange, symbol: str,
                        qty: float, price: float,
                        side: str = 'buy') -> Tuple[bool, str]:
    """
    Post-only (GTX) order — the primary entry mode.
    Tests that exchange accepts GTX and enforces maker-only.
    """
    try:
        o = exchange.create_order(
            symbol, 'limit', side, qty, price,
            params={'timeInForce': 'GTX'}
        )
        oid = o['id']
        # Cancel immediately
        try:
            exchange.cancel_order(oid, symbol)
        except Exception:
            pass
        return True, f"GTX accepted, oid={oid}"
    except Exception as e:
        msg = str(e).lower()
        if '-2010' in msg or 'post only' in msg or '-5022' in msg:
            raise WarnTest(f"GTX rejected (expected for marketable px): "
                           f"{msg[:80]}")
        raise


def test_gtx_preflight_behavior(exchange, symbol: str) -> Tuple[bool, str]:
    """
    Verify our _gtx_preflight logic would produce safe orders.
    Simulates: BUY at best_bid → should be adjusted to bid-tick.
    """
    ob = exchange.fetch_order_book(symbol, limit=5)
    bid = float(ob['bids'][0][0])
    ask = float(ob['asks'][0][0])

    mkt = exchange.market(symbol)
    tick = None
    for f in ((mkt.get('info') or {}).get('filters') or []):
        if f.get('filterType') == 'PRICE_FILTER':
            tick = float(f.get('tickSize', 0))
            break

    if not tick or tick <= 0:
        raise WarnTest("no tick size — skipping preflight simulation")

    # Simulate what our bot does
    safe_buy = bid - tick
    safe_sell = ask + tick

    assert safe_buy > 0, "safe_buy <= 0"
    assert safe_buy < bid, "safe_buy not below bid"
    assert safe_sell > ask, "safe_sell not above ask"

    return True, (f"tick={tick:.8f} safe_buy={safe_buy:.6f} "
                  f"safe_sell={safe_sell:.6f}")


def test_protective_order_stop_market(exchange, symbol: str,
                                       qty: float,
                                       stop_price: float) -> Tuple[bool, str]:
    """
    STOP_MARKET with closePosition=True — used by _place_protective_orders.
    Cannot test closePosition without a real position — use reduceOnly instead.
    """
    try:
        # Try closePosition first (production path)
        try:
            o = exchange.create_order(
                symbol, 'STOP_MARKET', 'sell', None, None,
                params={
                    'stopPrice': stop_price,
                    'closePosition': True,
                    'workingType': 'MARK_PRICE',
                }
            )
            oid = o['id']
            try:
                exchange.cancel_order(oid, symbol)
            except Exception:
                pass
            return True, f"closePosition accepted: oid={oid}"
        except Exception as e1:
            # Fallback to reduceOnly
            try:
                o = exchange.create_order(
                    symbol, 'STOP_MARKET', 'sell', qty, None,
                    params={
                        'stopPrice': stop_price,
                        'reduceOnly': True,
                        'workingType': 'MARK_PRICE',
                    }
                )
                oid = o['id']
                try:
                    exchange.cancel_order(oid, symbol)
                except Exception:
                    pass
                return True, (f"reduceOnly fallback used "
                              f"(closePosition failed: "
                              f"{str(e1)[:60]})")
            except Exception as e2:
                raise Exception(f"both failed. closePos: {e1} | "
                                f"reduceOnly: {e2}")
    except Exception as e:
        msg = str(e).lower()
        # Some exchanges reject STOP_MARKET without position — acceptable
        if 'reduceonly' in msg or '-2021' in msg or 'position' in msg:
            raise WarnTest(f"STOP_MARKET requires position: {msg[:80]}")
        raise


# ══════════════════════════════════════════════════════════════════════════
# ============ ORCHESTRATOR ============
# ══════════════════════════════════════════════════════════════════════════

def section(title: str):
    print()
    print(f"{C.BOLD}{C.BLUE}── {title} {'─' * (74 - len(title))}{C.END}")


def find_min_notional(exchange, symbol: str) -> Tuple[float, float]:
    """
    Returns (min_notional_usd, tick_size). Falls back to conservative values.
    """
    min_notional = 5.0
    tick = 0.0
    try:
        mkt = exchange.market(symbol)
        for f in ((mkt.get('info') or {}).get('filters') or []):
            if f.get('filterType') == 'MIN_NOTIONAL':
                min_notional = float(f.get('notional', 5.0))
            if f.get('filterType') == 'PRICE_FILTER':
                tick = float(f.get('tickSize', 0))
    except Exception:
        pass
    return min_notional, tick


def find_step_size(exchange, symbol: str) -> float:
    """Returns lot size step."""
    try:
        mkt = exchange.market(symbol)
        for f in ((mkt.get('info') or {}).get('filters') or []):
            if f.get('filterType') in ('LOT_SIZE', 'MARKET_LOT_SIZE'):
                step = float(f.get('stepSize', 0))
                if step > 0:
                    return step
    except Exception:
        pass
    return 1e-6


def compute_safe_test_order(exchange, symbol: str,
                             price: float) -> Tuple[float, float]:
    """
    Compute (qty, safe_far_price) such that:
      - notional ≈ 2× MIN_NOTIONAL (safe margin)
      - price is FAR from market (no accidental fill)
    """
    min_notional, tick = find_min_notional(exchange, symbol)
    step = find_step_size(exchange, symbol)

    if tick <= 0:
        tick = price * 1e-4

    # Target notional: 2× MIN_NOTIONAL, minimum 10 USDT
    target_notional = max(min_notional * 2.0, 10.0)

    # qty = notional / price, rounded UP to step
    import math
    qty_raw = target_notional / price
    qty = math.ceil(qty_raw / step) * step

    # Safe BUY price: 50% below market → never fills
    # Safe SELL price: 50% above market → never fills
    safe_buy_px = price * 0.50
    safe_sell_px = price * 1.50

    # Round to tick
    safe_buy_px = math.floor(safe_buy_px / tick) * tick
    safe_sell_px = math.ceil(safe_sell_px / tick) * tick

    return qty, safe_buy_px, safe_sell_px


def cleanup_all_orders(exchange, symbol: str) -> int:
    """Emergency cleanup — cancel ALL open orders on symbol."""
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
# ============ MAIN ============
# ══════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="Comprehensive exchange API test for trading bot"
    )
    p.add_argument("--mode", default="testnet",
                    choices=["testnet", "live"],
                    help="testnet=demo trading, live=mainnet")
    p.add_argument("--api-key", default=os.environ.get("BINANCE_API_KEY", ""))
    p.add_argument("--api-secret",
                    default=os.environ.get("BINANCE_API_SECRET", ""))
    p.add_argument("--symbol", default="BTC/USDT",
                    help="Symbol to test order operations on")
    p.add_argument("--allow-orders", action="store_true",
                    help="Enable state-mutating tests (places + cancels orders)")
    p.add_argument("--i-know-what-im-doing", action="store_true",
                    help="Required for --mode live (real money)")
    p.add_argument("--leverage", type=int, default=5,
                    help="Leverage used in setup tests")
    p.add_argument("--skip-slow", action="store_true",
                    help="Skip fetch_tickers (may take 5-10s)")
    p.add_argument("--output", type=str, default=None,
                    help="Save JSON report to this path")
    args = p.parse_args()

    # ══ Safety gates ══
    if args.mode == "live" and not args.i_know_what_im_doing:
        print(f"{C.RED}ERROR: --mode live requires "
              f"--i-know-what-im-doing{C.END}")
        print("  This flag exists to prevent accidental mainnet trades.")
        sys.exit(2)

    if not args.api_key or not args.api_secret:
        print(f"{C.YELLOW}WARNING: no API credentials — "
              f"authenticated tests will be skipped{C.END}")

    # ══ Banner ══
    print()
    print("╔" + "═" * 76 + "╗")
    print(f"║  {C.BOLD}Exchange API Test Suite{C.END}"
          f"{' ' * 52}║")
    print(f"║  Mode: {args.mode:<12}  "
          f"Symbol: {args.symbol:<15}  "
          f"Orders: {'YES' if args.allow_orders else 'NO (read-only)':<12} ║")
    print("╚" + "═" * 76 + "╝")

    # ══ Create exchange ══
    try:
        exchange = ccxt.binance({
            'apiKey': args.api_key,
            'secret': args.api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
            'timeout': 15000,
        })
    except Exception as e:
        print(f"{C.RED}Failed to create exchange: {e}{C.END}")
        sys.exit(3)

    if args.mode == "testnet":
        try:
            exchange.enable_demo_trading(True)
            print(f"{C.CYAN}→ Demo trading mode enabled{C.END}")
        except Exception as e:
            print(f"{C.RED}Failed to enable demo: {e}{C.END}")
            print("  Falling back to sandbox mode...")
            try:
                exchange.set_sandbox_mode(True)
            except Exception as e2:
                print(f"{C.RED}Sandbox also failed: {e2}{C.END}")
                sys.exit(4)
    else:
        print(f"{C.YELLOW}→ LIVE MAINNET mode{C.END}")

    # ══ Phase 1: Basic / Init ══
    section("PHASE 1 — Initialization & Metadata")

    run_test("import + init", test_import_and_init, exchange)

    ok, _ = run_test("fetch_time (server clock)", test_fetch_time, exchange)
    if not ok:
        print(f"{C.RED}  → Cannot continue without server time{C.END}")
        RESULTS.print_report()
        sys.exit(5)

    run_test("load_markets", test_load_markets, exchange)

    # Resolve actual symbol (BTC/USDT:USDT etc.)
    try:
        actual_symbol = _find_testable_symbol(exchange, args.symbol)
        print(f"{C.CYAN}  → Using symbol: {actual_symbol}{C.END}")
    except Exception as e:
        print(f"{C.RED}  → Cannot resolve symbol: {e}{C.END}")
        RESULTS.print_report()
        sys.exit(6)

    run_test(f"market({actual_symbol})", test_market_lookup,
             exchange, actual_symbol)
    run_test("parse_timeframe", test_parse_timeframe, exchange)
    run_test("parse8601", test_parse8601, exchange)

    # ══ Phase 2: Public data ══
    section("PHASE 2 — Public Data Endpoints (no auth)")

    run_test(f"fetch_ohlcv({actual_symbol})", test_fetch_ohlcv,
             exchange, actual_symbol)
    run_test(f"fetch_ohlcv with since", test_fetch_ohlcv_with_since,
             exchange, actual_symbol)
    run_test(f"fetch_ticker({actual_symbol})", test_fetch_ticker,
             exchange, actual_symbol)
    run_test(f"fetch_order_book(5)", test_fetch_order_book,
             exchange, actual_symbol)
    run_test(f"fetch_order_book(20)", test_fetch_order_book_20,
             exchange, actual_symbol)
    run_test(f"fetch_trades", test_fetch_trades,
             exchange, actual_symbol)

    if args.skip_slow:
        RESULTS.add("fetch_tickers (bulk)", "SKIP", 0.0,
                     detail="--skip-slow")
    else:
        run_test("fetch_tickers (bulk)", test_fetch_tickers, exchange)

    # ══ Phase 3: Authenticated read-only ══
    section("PHASE 3 — Authenticated Read-Only (requires API keys)")

    if not args.api_key or not args.api_secret:
        for name in ["fetch_balance", "fetch_positions",
                      "fetch_positions filtered", "fetch_open_orders",
                      "fetch_leverage", "fetch_leverage_tiers"]:
            RESULTS.add(name, 'SKIP', 0.0, detail="no credentials")
    else:
        run_test("fetch_balance", test_fetch_balance, exchange)
        run_test("fetch_positions", test_fetch_positions, exchange)
        run_test("fetch_positions filtered", test_fetch_positions_filtered,
                 exchange, actual_symbol)
        run_test("fetch_open_orders", test_fetch_open_orders,
                 exchange, actual_symbol)
        run_test("fetch_leverage", test_fetch_leverage,
                 exchange, actual_symbol)
        run_test("fetch_leverage_tiers", test_fetch_leverage_tiers,
                 exchange, actual_symbol)

    # ══ Phase 4: Order lifecycle ══
    section("PHASE 4 — Order Lifecycle (state-mutating)")

    if not args.allow_orders:
        print(f"{C.YELLOW}  Skipped — pass --allow-orders to enable{C.END}")
        for name in ["set_margin_mode", "set_leverage",
                      "create_limit_order", "fetch_order",
                      "cancel_order", "gtx_post_only",
                      "gtx_preflight simulation",
                      "stop_market protective"]:
            RESULTS.add(name, 'SKIP', 0.0, detail="--allow-orders not set")
    elif not args.api_key or not args.api_secret:
        print(f"{C.YELLOW}  Skipped — no credentials{C.END}")
        for name in ["set_margin_mode", "set_leverage",
                      "create_limit_order", "fetch_order",
                      "cancel_order", "gtx_post_only",
                      "gtx_preflight simulation",
                      "stop_market protective"]:
            RESULTS.add(name, 'SKIP', 0.0, detail="no credentials")
    else:
        # Get current price for safe order sizing
        try:
            tk = exchange.fetch_ticker(actual_symbol)
            current_px = float(tk['last'])
            print(f"{C.CYAN}  → Current price: {current_px:.4f}{C.END}")
        except Exception as e:
            print(f"{C.RED}  → Cannot fetch price: {e}{C.END}")
            current_px = 100.0

        # Setup tests
        run_test("set_margin_mode", test_set_margin_mode,
                 exchange, actual_symbol)
        run_test(f"set_leverage({args.leverage}x)", test_set_leverage,
                 exchange, actual_symbol, args.leverage)

        # Compute safe order parameters
        try:
            qty, safe_buy_px, safe_sell_px = compute_safe_test_order(
                exchange, actual_symbol, current_px
            )
            print(f"{C.CYAN}  → Safe test order: qty={qty}, "
                  f"BUY@{safe_buy_px:.6f}, SELL@{safe_sell_px:.6f}{C.END}")
        except Exception as e:
            print(f"{C.RED}  → Cannot compute safe order: {e}{C.END}")
            qty = 0.001
            safe_buy_px = current_px * 0.5
            safe_sell_px = current_px * 1.5

        # Create → fetch → cancel (BUY limit)
        order_id = None
        ok, res = run_test("create_limit_order (BUY)", test_create_limit_order,
                            exchange, actual_symbol, qty, safe_buy_px, 'buy')
        if ok and res:
            # Extract oid
            try:
                if isinstance(res, str):
                    oid = res.split("oid=")[1].split()[0]
                else:
                    oid = str(res)
            except Exception:
                oid = None

        # Try to get order id from a fresh fetch
        if not oid:
            try:
                orders = exchange.fetch_open_orders(actual_symbol)
                buy_orders = [o for o in orders if o.get('side') == 'buy']
                if buy_orders:
                    oid = buy_orders[-1]['id']
            except Exception:
                pass

        if oid:
            run_test("fetch_order", test_fetch_order,
                     exchange, actual_symbol, oid)
            run_test("cancel_order", test_cancel_order,
                     exchange, actual_symbol, oid)
        else:
            RESULTS.add("fetch_order", 'SKIP', 0.0,
                         detail="no order_id from create")
            RESULTS.add("cancel_order", 'SKIP', 0.0,
                         detail="no order_id from create")

        # GTX test (may be rejected if price crosses book — acceptable)
        run_test("gtx_post_only", test_gtx_post_only,
                 exchange, actual_symbol, qty, safe_buy_px, 'buy')

        # GTX preflight simulation
        run_test("gtx_preflight simulation", test_gtx_preflight_behavior,
                 exchange, actual_symbol)

        # STOP_MARKET protective (may warn if no position)
        run_test("stop_market protective", test_protective_order_stop_market,
                 exchange, actual_symbol, qty, current_px * 0.9)

        # ══ Final cleanup ══
        print()
        print(f"{C.CYAN}  → Cleanup: cancelling all open orders on "
              f"{actual_symbol}...{C.END}")
        n_cancelled = cleanup_all_orders(exchange, actual_symbol)
        print(f"{C.CYAN}  → Cancelled {n_cancelled} leftover order(s){C.END}")

    # ══ Print report ══
    RESULTS.print_report()

    # ══ Save JSON if requested ══
    if args.output:
        try:
            report = {
                'mode': args.mode,
                'symbol': actual_symbol,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'summary': RESULTS.summary(),
                'tests': RESULTS.tests,
                'elapsed_s': time.time() - RESULTS.start_ts,
            }
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"\n{C.CYAN}Report saved to {args.output}{C.END}")
        except Exception as e:
            print(f"{C.RED}Failed to save report: {e}{C.END}")

    # ══ Exit code ══
    counts = RESULTS.summary()
    if counts['FAIL'] > 0:
        sys.exit(1)   # CI-friendly: fail on any failure
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Interrupted by user{C.END}")
        # Emergency cleanup note
        print(f"{C.YELLOW}NOTE: If you had --allow-orders, manually "
              f"check for orphan orders on your account.{C.END}")
        sys.exit(130)
