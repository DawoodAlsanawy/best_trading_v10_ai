#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pre_restart_check.py — فحص ما قبل إعادة التشغيل (read-only)
═══════════════════════════════════════════════════════════════════════════

يفحص:
  1. حالة state file (آخر تعديل، عدد المراكز)
  2. تطابق المراكز مع البورصة
  3. وجود SL/TP على البورصة لكل مركز
  4. حالة pending orders
  5. تحذيرات over-risk

لا يغيّر أي شيء — للتشخيص فقط.

الاستخدام:
    python pre_restart_check.py --mode live
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone


def _load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ✗ Failed to load {path}: {e}")
        return None


def _file_age_s(path):
    if not os.path.exists(path):
        return None
    return time.time() - os.path.getmtime(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="testnet", choices=["live", "testnet"])
    p.add_argument("--api-key", default=os.environ.get("BINANCE_API_KEY", ""))
    p.add_argument("--api-secret", default=os.environ.get("BINANCE_API_SECRET", ""))
    p.add_argument("--live-capital", type=float, default=0.0)
    p.add_argument("--capital", type=float, default=10.0)
    args = p.parse_args()

    mode = args.mode
    state_file = f"live_state_{mode}.json"
    pending_file = f"pending_orders_{mode}.json"
    peak_file = f"live_peak_{mode}.json"

    print("═" * 78)
    print(f" PRE-RESTART CHECK — mode={mode}")
    print("═" * 78)
    print()

    # ─── 1. State files ───
    print("─" * 78)
    print(" 1. State files:")
    print("─" * 78)

    open_pos = _load_json(state_file) or {}
    pending = _load_json(pending_file) or {}
    peak_data = _load_json(peak_file) or {}

    state_age = _file_age_s(state_file)
    if state_age is None:
        print(f"  ✗ {state_file} NOT FOUND (no open positions?)")
    else:
        print(f"  ✓ {state_file}: {len(open_pos)} positions, "
              f"age={state_age:.0f}s ({state_age/60:.1f}min)")
        if state_age > 300:
            print(f"    ⚠ State file older than 5 minutes — bot may be stopped or lagging")

    pending_age = _file_age_s(pending_file)
    if pending_age is None:
        print(f"  · {pending_file}: not found (no pending)")
    else:
        print(f"  ✓ {pending_file}: {len(pending)} pending, "
              f"age={pending_age:.0f}s")

    if peak_data:
        print(f"  ✓ {peak_file}: peak=${peak_data.get('peak', 0):.2f}")
    else:
        print(f"  ⚠ {peak_file}: not found")

    print()

    # ─── 2. Warning: capital vs live-capital ───
    print("─" * 78)
    print(" 2. Capital consistency:")
    print("─" * 78)
    print(f"  --capital (backtest reference): ${args.capital:.2f}")
    print(f"  --live-capital (live sizing):   ${args.live_capital:.2f}")
    if args.live_capital > 0:
        print(f"  → After patches: leverage uses --live-capital (not --capital)")
        print(f"  → DD uses wallet (not --live-capital)")
    else:
        print(f"  → After patches: leverage uses wallet directly")
    print()

    # ─── 3. Exchange connection ───
    print("─" * 78)
    print(" 3. Exchange connection (read-only):")
    print("─" * 78)

    if not args.api_key or not args.api_secret:
        print("  ⚠ No API credentials — skipping exchange check")
        print("    Run with --api-key and --api-secret to verify positions")
        print()
        _print_summary(open_pos, pending, None, None)
        return 0

    try:
        import ccxt
        ex = ccxt.binance({
            'apiKey': args.api_key,
            'secret': args.api_secret,
            'enableRateLimit': True,
            'options': {'defaultType': 'future',
                        'adjustForTimeDifference': True,
                        'recvWindow': 20000}
        })
        if mode == "testnet":
            ex.enable_demo_trading(True)

        bal = ex.fetch_balance()
        wallet_balance = 0.0
        free = 0.0
        try:
            info = bal.get('info') or {}
            wallet_balance = float(info.get('totalWalletBalance', 0) or 0)
            free = float(bal['USDT'].get('free', 0) or 0)
        except Exception:
            wallet_balance = float(bal['USDT'].get('total', 0) or 0)
            free = float(bal['USDT'].get('free', 0) or 0)

        print(f"  Wallet balance:  ${wallet_balance:.2f}")
        print(f"  Free margin:     ${free:.2f}")

        # Check --live-capital vs wallet
        if args.live_capital > 0 and wallet_balance > 0:
            ratio = args.live_capital / wallet_balance
            if ratio > 1.1:
                print(f"  ⚠ --live-capital ${args.live_capital:.2f} > "
                      f"wallet ${wallet_balance:.2f} × {ratio:.2f}")
                print(f"     → Position sizing uses ${args.live_capital:.2f}")
                print(f"     → Real risk is {ratio:.2f}× higher than planned")
            elif ratio < 0.3:
                print(f"  ⚠ --live-capital is only {ratio*100:.0f}% of wallet")
                print(f"     → Bot will use only ${args.live_capital:.2f} of ${wallet_balance:.2f}")

        # Fetch positions
        positions = ex.fetch_positions()
        active_pos = {}
        for p in positions:
            try:
                amt = float(p['info'].get('positionAmt', 0) or 0)
                if abs(amt) < 1e-12:
                    continue
                sym = p['symbol'].split(':')[0] if ':' in p['symbol'] else p['symbol']
                active_pos[sym] = {
                    'qty': abs(amt),
                    'entry': float(p['info'].get('entryPrice', 0) or 0),
                    'side': 'BUY' if amt > 0 else 'SELL',
                    'liq': float(p['info'].get('liquidationPrice', 0) or 0),
                }
            except Exception:
                continue

        print(f"  Exchange positions: {len(active_pos)}")

        # Fetch open orders
        try:
            all_orders = ex.fetch_open_orders()
        except Exception:
            all_orders = []

        print(f"  Open orders:        {len(all_orders)}")
        print()

        _print_summary(open_pos, pending, active_pos, all_orders)

    except Exception as e:
        print(f"  ✗ Exchange error: {e}")
        print()
        _print_summary(open_pos, pending, None, None)

    return 0


def _print_summary(open_pos, pending, active_pos, all_orders):
    print("─" * 78)
    print(" 4. Position protection status:")
    print("─" * 78)

    if not open_pos:
        print("  No positions in state file.")
        print()
        print("═" * 78)
        print(" ✓ SAFE TO RESTART (no positions)")
        print("═" * 78)
        return

    if active_pos is None:
        print("  ⚠ Cannot verify exchange protection (no API)")
        for sym, pos in open_pos.items():
            print(f"    {sym}: {pos.get('action')} qty={pos.get('qty')} "
                  f"sl={pos.get('sl')} tp={pos.get('tp1')}")
        print()
        print("═" * 78)
        print(" ⚠ MANUAL CHECK REQUIRED (no API to verify)")
        print("═" * 78)
        return

    issues = []
    for sym, pos in open_pos.items():
        in_state = True
        in_exch = sym in active_pos
        if not in_exch:
            issues.append(f"{sym}: MISSING on exchange (state only)")
            print(f"  ✗ {sym}: in state, NOT on exchange → will be removed")
            continue

        # Check protective orders
        sym_orders = [o for o in (all_orders or []) if
                      (str(o.get('symbol', '')).split(':')[0] == sym)]
        has_sl = any(
            (o.get('type', '').lower() in ('stop_market', 'stop', 'stop_loss')
             or 'stop' in str((o.get('info') or {}).get('orderType', '')).lower())
            for o in sym_orders
        )
        has_tp = any(
            (o.get('type', '').lower() in ('take_profit_market', 'take_profit')
             or 'take_profit' in str((o.get('info') or {}).get('orderType', '')).lower())
            for o in sym_orders
        )

        status_sl = "✓" if has_sl else "✗"
        status_tp = "✓" if has_tp else "✗"
        print(f"  {sym}: {pos.get('action')} qty={float(pos.get('qty', 0)):.6f} "
              f"entry={float(pos.get('entry', 0)):.6f} | "
              f"SL:{status_sl} TP:{status_tp}")

        if not has_sl:
            issues.append(f"{sym}: NO SL on exchange")
        if not has_tp:
            issues.append(f"{sym}: NO TP on exchange")

    print()
    if issues:
        print("═" * 78)
        print(" ⚠ ISSUES FOUND:")
        for i in issues:
            print(f"   · {i}")
        print()
        print(" ⚠ DO NOT RESTART until these are fixed")
        print("   → Bot will try to place protective orders at restart")
        print("   → But it may take 1-2 seconds (window of exposure)")
        print("   → Manually place SL/TP on exchange FIRST")
        print("═" * 78)
    else:
        print("═" * 78)
        print(" ✓ SAFE TO RESTART")
        print("   All positions are protected on exchange")
        print("   Bot will resume correctly with patches applied")
        print("═" * 78)


if __name__ == "__main__":
    sys.exit(main())
