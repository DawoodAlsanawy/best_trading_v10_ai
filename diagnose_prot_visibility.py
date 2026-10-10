#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Root-cause diagnostic: why protective orders are "not visible".

Place a real STOP_MARKET on testnet, then query it via 8 different
methods, printing full raw responses. This reveals whether the issue
is:
  1. ccxt param mismatch ('trigger' vs 'stop')
  2. Wrong endpoint (regular vs algo)
  3. Type classification failure ('stop' vs 'stop_market')
  4. Propagation delay
  5. Testnet-specific behavior

Usage:
    python diagnose_prot_visibility.py \\
        --mode testnet \\
        --api-key KEY --api-secret SECRET \\
        [--symbol BTC/USDT]
"""

import argparse
import json
import os
import sys
import time

try:
    import ccxt
except ImportError:
    print("ERROR: pip install ccxt")
    sys.exit(1)


def sep(title=""):
    print(f"\n{'═' * 74}")
    if title:
        print(f"  {title}")
        print(f"{'═' * 74}")


def safe_json(obj, max_len=2000):
    try:
        s = json.dumps(obj, indent=2, default=str)
        if len(s) > max_len:
            s = s[:max_len] + "\n  ... (truncated)"
        return s
    except Exception as e:
        return f"<json failed: {e}>"


def _is_protective_order_bot(o):
    """Exact copy of bot's classifier."""
    try:
        t = str(o.get('type') or '').lower()
        return ('stop_market' in t or 'take_profit_market' in t)
    except Exception:
        return False


def _is_protective_order_alt(o):
    """Alternative classifier — checks both unified and raw."""
    try:
        # Check unified type
        t_uni = str(o.get('type') or '').lower()
        if 'stop_market' in t_uni or 'take_profit_market' in t_uni:
            return True
        # Check ccxt normalized type
        if t_uni in ('stop', 'take_profit', 'stop_loss', 'stop_market',
                     'take_profit_market'):
            return True
        # Check raw info
        info = o.get('info') or {}
        t_raw = str(info.get('type') or '').lower()
        if 'stop' in t_raw or 'take_profit' in t_raw:
            return True
        # Check triggerPrice existence
        if o.get('triggerPrice') or info.get('stopPrice'):
            return True
    except Exception:
        pass
    return False


def ensure_position(exchange, symbol, force=False):
    """Open a tiny position if none exists."""
    positions = exchange.fetch_positions([symbol])
    for p in positions or []:
        amt = float((p.get('info') or {}).get('positionAmt', 0) or 0)
        if abs(amt) > 1e-12:
            return abs(amt), 'existing'
    if not force:
        return None, 'none'

    # Open tiny market position
    ticker = exchange.fetch_ticker(symbol)
    last = float(ticker['last'])
    m = exchange.market(symbol)
    min_notional = 5.0
    info = m.get('info') or {}
    for f in (info.get('filters') or []):
        if isinstance(f, dict) and f.get('filterType') == 'MIN_NOTIONAL':
            min_notional = float(f.get('notional', 5.0))
            break
    qty_raw = (min_notional * 1.3) / last
    qty = float(exchange.amount_to_precision(symbol, qty_raw))
    print(f"  Opening test position: {qty} @ ~{last}")
    o = exchange.create_order(symbol, 'market', 'buy', qty)
    time.sleep(1.5)
    # Verify
    positions = exchange.fetch_positions([symbol])
    for p in positions or []:
        amt = float((p.get('info') or {}).get('positionAmt', 0) or 0)
        if abs(amt) > 1e-12:
            return abs(amt), 'opened'
    return None, 'failed'


def cleanup(exchange, symbol):
    print("\n  ─── CLEANUP ───")
    # Cancel everything
    try:
        for o in exchange.fetch_open_orders(symbol) or []:
            try:
                exchange.cancel_order(o['id'], symbol)
            except Exception:
                pass
    except Exception:
        pass
    try:
        for o in exchange.fetch_open_orders(symbol, params={'trigger': True}) or []:
            try:
                exchange.cancel_order(o['id'], symbol, params={'trigger': True})
            except Exception:
                try:
                    exchange.cancel_order(o['id'], symbol)
                except Exception:
                    pass
    except Exception:
        pass
    # Close position
    try:
        positions = exchange.fetch_positions([symbol])
        for p in positions or []:
            amt = float((p.get('info') or {}).get('positionAmt', 0) or 0)
            if abs(amt) > 0:
                side = 'sell' if amt > 0 else 'buy'
                exchange.create_order(symbol, 'market', side, abs(amt),
                                       None, params={'reduceOnly': True})
                print(f"  Closed {symbol} qty={abs(amt)}")
    except Exception as e:
        print(f"  Close failed: {e}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="testnet",
                   choices=["testnet", "live"])
    p.add_argument("--api-key",
                   default=os.environ.get("BINANCE_API_KEY", ""))
    p.add_argument("--api-secret",
                   default=os.environ.get("BINANCE_API_SECRET", ""))
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if not args.api_key or not args.api_secret:
        print("ERROR: --api-key and --api-secret required")
        return 1

    ex = ccxt.binance({
        'apiKey': args.api_key,
        'secret': args.api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
        'verbose': args.verbose,
    })
    if args.mode == "testnet":
        try:
            ex.enable_demo_trading(True)
        except AttributeError:
            ex.set_sandbox_mode(True)

    sep("1. Environment")
    print(f"  ccxt version:  {ccxt.__version__}")
    print(f"  mode:          {args.mode}")
    print(f"  symbol:        {args.symbol}")
    ex.load_markets()
    print(f"  markets loaded: {len(ex.markets)}")
    print(f"  urls.api:      {ex.urls['api']}")

    # ── Ensure position ──
    sep("2. Ensure position exists")
    qty, how = ensure_position(ex, args.symbol, force=True)
    if qty is None:
        print(f"  FAILED to open position ({how})")
        return 1
    print(f"  Position qty = {qty} ({how})")

    # ── Place STOP_MARKET ──
    sep("3. Place STOP_MARKET (protective SL)")
    ticker = ex.fetch_ticker(args.symbol)
    last = float(ticker['last'])
    m = ex.market(args.symbol)
    tick = 0.01
    info = m.get('info') or {}
    for f in (info.get('filters') or []):
        if isinstance(f, dict) and f.get('filterType') == 'PRICE_FILTER':
            tick = float(f.get('tickSize', 0.01))
            break

    stop_px = round(round(last * 0.90 / tick) * tick, 10)
    print(f"  last={last}  tick={tick}  stopPrice={stop_px}")

    sl_params = {
        'stopPrice': stop_px,
        'reduceOnly': True,
        'workingType': 'MARK_PRICE',
    }
    sl_order = None
    try:
        sl_order = ex.create_order(
            args.symbol, 'STOP_MARKET', 'sell', qty, None,
            params=sl_params
        )
        print(f"  ✓ STOP_MARKET placed")
        print(f"  ─── create_order response ───")
        print(safe_json(sl_order))
    except Exception as e:
        print(f"  ✗ create_order failed: {e}")
        cleanup(ex, args.symbol)
        return 1

    sl_id = str(sl_order.get('id') or '')
    print(f"\n  SL order_id = {sl_id}")

    # ── Immediate query (no delay) ──
    sep("4. Query #1 — IMMEDIATE (0ms after place)")
    _test_all_query_methods(ex, args.symbol, sl_id)

    # ── After 2s ──
    sep("5. Query #2 — after 2s delay")
    time.sleep(2.0)
    _test_all_query_methods(ex, args.symbol, sl_id)

    # ── After 5s more ──
    sep("6. Query #3 — after 7s total")
    time.sleep(5.0)
    _test_all_query_methods(ex, args.symbol, sl_id)

    # ── fetch_order by ID (direct) ──
    sep("7. fetch_order by ID (direct)")
    try:
        o = ex.fetch_order(sl_id, args.symbol)
        print(f"  ✓ fetch_order returned")
        print(safe_json(o))
        print(f"\n  is_protective (bot's classifier): "
              f"{_is_protective_order_bot(o)}")
        print(f"  is_protective (alt classifier):   "
              f"{_is_protective_order_alt(o)}")
    except Exception as e:
        print(f"  ✗ fetch_order failed: {e}")

    # ── fetch_order with trigger=True ──
    sep("8. fetch_order by ID with trigger=True")
    try:
        o = ex.fetch_order(sl_id, args.symbol, params={'trigger': True})
        print(f"  ✓ returned")
        print(safe_json(o))
    except Exception as e:
        print(f"  ✗ failed: {e}")

    # ── fetch_orders (all, including closed) ──
    sep("9. fetch_orders (all recent)")
    try:
        orders = ex.fetch_orders(args.symbol, limit=20)
        print(f"  returned {len(orders)} orders")
        for o in orders[-5:]:
            print(f"    id={o.get('id')} type={o.get('type')} "
                  f"status={o.get('status')}")
    except Exception as e:
        print(f"  ✗ failed: {e}")

    # ── Raw API probes ──
    sep("10. Raw Binance API probes")
    _raw_probe(ex, args.symbol)

    # ── Summary ──
    sep("11. DIAGNOSIS SUMMARY")
    _summarize(ex, args.symbol, sl_id)

    # ── Cleanup ──
    cleanup(ex, args.symbol)

    print("\nDone. Please share the FULL output.")
    return 0


def _test_all_query_methods(ex, symbol, target_id):
    """Query open orders via 8 different methods."""
    methods = [
        ("A. fetch_open_orders (no params)",
         lambda: ex.fetch_open_orders(symbol)),
        ("B. fetch_open_orders (trigger=True)",
         lambda: ex.fetch_open_orders(symbol, params={'trigger': True})),
        ("C. fetch_open_orders (stop=True)",
         lambda: ex.fetch_open_orders(symbol, params={'stop': True})),
        ("D. fetch_open_orders (type=stop_market)",
         lambda: ex.fetch_open_orders(symbol,
                                       params={'type': 'stop_market'})),
        ("E. fetch_open_orders (stop=True, trigger=True)",
         lambda: ex.fetch_open_orders(
             symbol, params={'stop': True, 'trigger': True})),
        ("F. fapiPrivateGetOpenOrders (raw)",
         lambda: ex.fapiPrivateGetOpenOrders({'symbol': symbol})),
        ("G. fapiPrivateGetOpenAlgoOrders (raw algo)",
         lambda: ex.fapiPrivateGetOpenAlgoOrders()),
        ("H. fetch_open_orders (all symbols)",
         lambda: ex.fetch_open_orders()),
    ]

    for name, fn in methods:
        try:
            result = fn()
            _analyze_result(name, result, target_id)
        except Exception as e:
            print(f"  {name}: EXCEPTION")
            print(f"    {type(e).__name__}: {str(e)[:200]}")


def _analyze_result(name, result, target_id):
    if result is None:
        print(f"  {name}: None")
        return
    if isinstance(result, list):
        n = len(result)
        found = any(str(o.get('id') or '') == target_id for o in result
                    if isinstance(o, dict))
        # Check each order
        types = [o.get('type') for o in result if isinstance(o, dict)]
        print(f"  {name}: list with {n} items, "
              f"target_found={found}, types={types[:5]}")
        if n > 0 and n <= 5:
            for o in result[:3]:
                if isinstance(o, dict):
                    print(f"    → id={o.get('id')} "
                          f"type={o.get('type')} "
                          f"stopPrice={o.get('stopPrice')} "
                          f"reduceOnly={o.get('reduceOnly')}")
    elif isinstance(result, dict):
        # Could be {"orders": [...]} or {"total": ..., ...}
        if 'orders' in result:
            print(f"  {name}: dict with 'orders' key, "
                  f"len={len(result['orders'])}")
            _analyze_result(name + " (orders)", result['orders'], target_id)
        else:
            keys = list(result.keys())[:10]
            print(f"  {name}: dict with keys {keys}")
    else:
        print(f"  {name}: {type(result).__name__}")


def _raw_probe(ex, symbol):
    """Try raw API endpoints that bypass ccxt normalization."""
    probes = [
        ("fapiPrivateGetOpenOrders",
         lambda: ex.fapiPrivateGetOpenOrders({'symbol': symbol})),
        ("fapiPrivateGetOpenAlgoOrders",
         lambda: ex.fapiPrivateGetOpenAlgoOrders()),
        ("fapiPrivateGetAllOrders",
         lambda: ex.fapiPrivateGetAllOrders({'symbol': symbol, 'limit': 5})),
    ]
    for name, fn in probes:
        try:
            r = fn()
            if isinstance(r, list):
                print(f"  {name}: list len={len(r)}")
                if r and len(r) <= 3:
                    print(f"    sample: {safe_json(r[0], 800)}")
                elif r:
                    print(f"    first id={r[0].get('orderId')} "
                          f"type={r[0].get('type')} "
                          f"status={r[0].get('status')}")
            elif isinstance(r, dict):
                print(f"  {name}: dict keys={list(r.keys())[:8]}")
                if 'orders' in r:
                    print(f"    orders len={len(r['orders'])}")
            else:
                print(f"  {name}: {type(r).__name__}")
        except Exception as e:
            print(f"  {name}: EXCEPTION {type(e).__name__}: {str(e)[:150]}")


def _summarize(ex, symbol, sl_id):
    """Final diagnosis summary."""
    print("  Testing visibility of SL order through each method:\n")
    methods = [
        ("fetch_open_orders()",
         lambda: ex.fetch_open_orders(symbol)),
        ("fetch_open_orders(trigger=True)",
         lambda: ex.fetch_open_orders(symbol, params={'trigger': True})),
        ("fetch_open_orders(stop=True)",
         lambda: ex.fetch_open_orders(symbol, params={'stop': True})),
        ("_lv_open_orders_all equivalent",
         lambda: _bot_lv_open_orders_all(ex, symbol)),
    ]
    bot_visible = False
    for name, fn in methods:
        try:
            orders = fn()
            found = any(str(o.get('id') or '') == sl_id for o in (orders or []))
            bot_prot = sum(1 for o in (orders or [])
                           if _is_protective_order_bot(o))
            alt_prot = sum(1 for o in (orders or [])
                           if _is_protective_order_alt(o))
            marker = "✓" if found else "✗"
            print(f"    [{marker}] {name:45s} "
                  f"found={found}  bot_classified={bot_prot}  "
                  f"alt_classified={alt_prot}")
            if name.startswith("_lv_open_orders_all") and found:
                bot_visible = True
        except Exception as e:
            print(f"    [!] {name:45s} EXCEPTION: {str(e)[:80]}")

    print()
    if bot_visible:
        print("  ✓ The order IS visible via _lv_open_orders_all.")
        print("    The warning in the bot is likely a TIMING issue.")
    else:
        print("  ✗ The order is NOT visible via _lv_open_orders_all.")
        print("    Root cause is a query/classification issue.")


def _bot_lv_open_orders_all(exchange, sym):
    """Exact copy of bot's function."""
    seen, out = set(), []
    for prm in (None, {'trigger': True}):
        try:
            lst = (exchange.fetch_open_orders(sym) if prm is None
                   else exchange.fetch_open_orders(sym, params=prm))
        except Exception:
            continue
        for o in lst or []:
            k = str(o.get('id'))
            if k not in seen:
                seen.add(k)
                out.append(o)
    return out


if __name__ == "__main__":
    sys.exit(main())
