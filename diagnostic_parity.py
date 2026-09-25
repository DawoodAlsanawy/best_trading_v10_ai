#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnostic_parity.py — Why does the live-parity backtest lose money?

Runs the full pipeline once, then dissects:
  1. Signal quality (dip, score distribution)
  2. Trade distances (SL%, TP%, R/R)
  3. Exit reason breakdown (win rate + MFE per reason)
  4. Emergency SL: profit-exit vs real-loss
  5. MFE distribution of losing trades (was profit ever possible?)
  6. Post-fill price action (is entry anti-predictive?)
  7. Fill-rate sensitivity to wait-window size

No code changes to trading.py. Read-only.
"""
import os, sys, time
from collections import defaultdict
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import trading as T
from trading import (
    scan_top_assets, fetch_all_with_subbars, process_asset,
    build_signals, deduplicate_signals, precompute_correlations,
    simulate_portfolio, precompute_entry_fills,
)


def ts_to_ci(ad, ts):
    try:
        return int(np.searchsorted(ad.timestamps.asi8, ts.value,
                                    side='right') - 1)
    except Exception:
        return -1


def print_flags():
    print("=" * 78)
    print("  KEY CONFIG FLAGS")
    print("=" * 78)
    keys = [
        "SIMULATE_LIVE_FAITHFULLY", "USE_ABSOLUTE_THRESHOLDS",
        "SL_WIDEN_MULT", "MIN_SCORE",
        "ENTRY_ATR_MULT", "ENTRY_MIN_DIP_MULT", "ENTRY_MAX_DIP_MULT",
        "ENTRY_REGIME_SCALE", "ENTRY_STRUCTURE_ANCHOR",
        "ENTRY_TIME_DECAY", "ENTRY_TIME_DECAY_MULT_1",
        "SUBBARS_ENABLED", "PO_FIXED_PRICE",
        "PO_MAX_WAIT_S", "FILL_ENTRY_MAX_WAIT_BARS",
        "FILL_PENETRATION_BPS",
        "TRAIL_ENABLED", "TRAIL_ADVANCED_ENABLED",
        "TRAIL_DYNAMIC", "TRAIL_KAPPA", "TRAIL_ACT_KAPPA",
        "TRAIL_ACTIVATE_SIGMA_MULT", "TRAIL_CHANDELIER_K",
        "TRAIL_MIN_FRAC", "TRAIL_MAX_FRAC",
        "TRAIL_ACT_MIN_FRAC", "TRAIL_ACT_MAX_FRAC",
        "BREAKEVEN_ENABLED",
        "LIQ_ENABLED", "MAX_CONCURRENT_ASSETS",
        "PORTFOLIO_HEAT_MAX", "INITIAL_CAPITAL",
        "MAX_HOLD_BARS", "MAKER_FEE", "TAKER_FEE",
    ]
    for k in keys:
        print(f"  {k:35s} = {getattr(T.CFG, k, '<missing>')}")
    print()


def run_pipeline(exchange):
    syms = scan_top_assets(exchange, T.CFG.n_assets)
    print(f"  symbols: {len(syms)}")
    raw, raw_sub = fetch_all_with_subbars(
        syms, exchange, T.CFG.timeframe, T.CFG.history_days, workers=5)
    print(f"  fetched: {len(raw)} symbols")

    assets = {}
    skipped = []
    for sym, df in raw.items():
        try:
            ad = process_asset(sym, df,
                                current_capital=T.CFG.INITIAL_CAPITAL,
                                sub_df=raw_sub.get(sym) if raw_sub else None)
            if ad is not None:
                assets[sym] = ad
            else:
                skipped.append(sym)
        except Exception as e:
            skipped.append(sym)
    print(f"  processed: {len(assets)}  skipped: {len(skipped)}")

    if not assets:
        return None, None, None, None

    sigs = deduplicate_signals(build_signals(assets))
    print(f"  signals: {len(sigs):,}")

    corr = precompute_correlations(assets)
    trades, equity = simulate_portfolio(sigs, assets, corr, mode="backtest")
    print(f"  trades: {len(trades)}")
    return trades, equity, sigs, assets


def analyze(trades, equity, sigs, assets):
    if not trades:
        print("\n  ⚠️ NO TRADES — pipeline produced empty result.")
        return

    n = len(trades)
    pnls = np.array([t.net_pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    pf = (wins.sum() / abs(losses.sum())
          if len(losses) and losses.sum() != 0 else float('inf'))

    print(f"\n  ── BASIC ──")
    print(f"    n_trades : {n}")
    print(f"    win_rate : {len(wins)/n*100:.2f}%")
    print(f"    PF       : {pf:.3f}")
    print(f"    equity   : ${equity[0]:.2f} → ${equity[-1]:.2f}")
    print(f"    avg_win  : ${np.mean(wins) if len(wins) else 0:+.4f}")
    print(f"    avg_loss : ${np.mean(losses) if len(losses) else 0:+.4f}")

    # Match trades to signals (by symbol + entry_time + action)
    sig_map = defaultdict(list)
    for s in sigs:
        sig_map[(s.symbol, s.timestamp)].append(s)
    matched = []
    for t in trades:
        for s in sig_map.get((t.symbol, t.entry_time), []):
            if s.action == t.action:
                matched.append((t, s))
                break
    print(f"    matched  : {len(matched)}/{n}")

    # ── DISTANCES ──
    print(f"\n  ── DISTANCES (from signals) ──")
    sl_d, tp_d = [], []
    for t, s in matched:
        e = t.entry_price
        if e <= 0:
            continue
        if t.action == "BUY":
            sd = (e - s.sl) / e * 100
            td = (s.tp1 - e) / e * 100
        else:
            sd = (s.sl - e) / e * 100
            td = (e - s.tp1) / e * 100
        if sd > 0:
            sl_d.append(sd)
            tp_d.append(td)
    if sl_d:
        a, b = np.array(sl_d), np.array(tp_d)
        print(f"    SL%: μ={a.mean():7.3f}  med={np.median(a):7.3f}  "
              f"p10={np.percentile(a,10):7.3f}  p90={np.percentile(a,90):7.3f}")
        print(f"    TP%: μ={b.mean():7.3f}  med={np.median(b):7.3f}")
        print(f"    R/R: μ={(b/a).mean():7.3f}")

    # ── EXIT REASONS ──
    print(f"\n  ── EXIT REASONS ──")
    by_r = defaultdict(list)
    for t in trades:
        r = t.exit_reason.split("(")[0].strip()
        by_r[r].append(t)
    for r, lst in sorted(by_r.items(), key=lambda x: -len(x[1])):
        mfes = np.array([t.mfe_frac for t in lst]) * 100
        pp = [t.net_pnl for t in lst]
        wpct = sum(1 for p in pp if p > 0) / len(lst) * 100
        print(f"    {r:22s}: n={len(lst):5d}  "
              f"μMFE={mfes.mean():5.2f}%  μPnL=${np.mean(pp):+.4f}  "
              f"win={wpct:5.1f}%")

    # ── EMERGENCY SL SPLIT ──
    sl_trades = by_r.get("Emergency SL", [])
    if sl_trades:
        prof_sl = [t for t in sl_trades if t.net_pnl > 0]
        loss_sl = [t for t in sl_trades if t.net_pnl <= 0]
        print(f"\n  ── EMERGENCY SL: profit vs loss ──")
        print(f"    total       : {len(sl_trades)}")
        print(f"    trail-prof  : {len(prof_sl)} "
              f"({len(prof_sl)/len(sl_trades)*100:.1f}%)  ← SL moved above entry")
        print(f"    real-loss   : {len(loss_sl)} "
              f"({len(loss_sl)/len(sl_trades)*100:.1f}%)  ← SL stayed below entry")

        if loss_sl:
            mfes = np.array([t.mfe_frac for t in loss_sl]) * 100
            print(f"\n  ── MFE of REAL-LOSS trades (n={len(loss_sl)}) ──")
            print(f"    μ={mfes.mean():.3f}%  med={np.median(mfes):.3f}%  "
                  f"p90={np.percentile(mfes,90):.3f}%  max={mfes.max():.3f}%")
            for thr in [0.2, 0.5, 1.0, 2.0]:
                c = int((mfes >= thr).sum())
                print(f"    MFE >= {thr}%: {c:5d} ({c/len(loss_sl)*100:5.1f}%)")

    # ── POST-FILL PRICE ACTION ──
    print(f"\n  ── POST-FILL PRICE ACTION (return from entry) ──")
    horizons = {1: [], 3: [], 5: [], 24: []}
    for t, s in matched:
        ad = assets.get(t.symbol)
        if ad is None:
            continue
        ci = ts_to_ci(ad, t.entry_time)
        if ci < 0:
            continue
        ep = t.entry_price
        if ep <= 0:
            continue
        for h in horizons:
            j = ci + h
            if j < len(ad.closes):
                r = (ad.closes[j] - ep) / ep
                if t.action == "SELL":
                    r = -r
                horizons[h].append(r * 100)
    for h, lst in horizons.items():
        if lst:
            a = np.array(lst)
            print(f"    +{h:2d} bars: μ={a.mean():+7.3f}%  "
                  f"med={np.median(a):+7.3f}%  "
                  f"%pos={(a>0).mean()*100:5.1f}%")

    # ── COSTS ──
    fees = sum(t.fee for t in trades)
    slips = sum(t.slippage_paid for t in trades)
    gross = sum(t.gross_pnl for t in trades)
    net = sum(t.net_pnl for t in trades)
    print(f"\n  ── COSTS ──")
    print(f"    gross=${gross:+.4f}  fees=${fees:.4f}  "
          f"slip=${slips:.4f}  net=${net:+.4f}")


def fill_rate_sensitivity(sigs, assets):
    print(f"\n  ── FILL-RATE SENSITIVITY ──")
    print(f"    (how many signals would fill with different wait windows)")
    for wait in [1, 2, 3, 5, 10, 25]:
        try:
            fm = precompute_entry_fills(
                assets, sigs,
                max_wait_bars=wait,
                pen_bps=T.CFG.FILL_PENETRATION_BPS,
            )
            n_f = 0
            for v in fm.values():
                if v is None:
                    continue
                if isinstance(v, tuple):
                    if v[0] is not None:
                        n_f += 1
                else:
                    n_f += 1
            pct = 100 * n_f / max(len(sigs), 1)
            print(f"    wait={wait:3d} bars : {n_f:6d}/{len(sigs):6d} ({pct:5.1f}%)")
        except Exception as e:
            print(f"    wait={wait:3d} bars : ERROR — {e}")


def main():
    try:
        import ccxt
    except ImportError:
        print("pip install ccxt")
        return

    print_flags()

    print("=" * 78)
    print("  RUNNING PIPELINE")
    print("=" * 78)
    exchange = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })

    t0 = time.time()
    result = run_pipeline(exchange)
    elapsed = time.time() - t0
    print(f"  elapsed: {elapsed:.1f}s")

    if result is None or result[0] is None:
        print("Pipeline failed.")
        return

    trades, equity, sigs, assets = result

    # Signal stats
    if sigs:
        dips = []
        scores = []
        for s in sigs:
            scores.append(s.score)
            ad = assets.get(s.symbol)
            if ad is None:
                continue
            ci = s.close_idx
            if 0 <= ci < len(ad.closes):
                p = ad.closes[ci]
                if p > 0:
                    dips.append(abs(p - s.price) / p * 100)
        if dips:
            a = np.array(dips)
            print(f"\n  ── SIGNAL DIP% ──")
            print(f"    μ={a.mean():.3f}  med={np.median(a):.3f}  "
                  f"p10={np.percentile(a,10):.3f}  p90={np.percentile(a,90):.3f}")
        if scores:
            s = np.array(scores)
            print(f"  ── SIGNAL SCORE ──")
            print(f"    μ={s.mean():.3f}  med={np.median(s):.3f}  "
                  f"min={s.min():.3f}  max={s.max():.3f}")

    # Trade analysis
    print(f"\n{'━' * 78}")
    print(f"  TRADE ANALYSIS")
    print(f"{'━' * 78}")
    analyze(trades, equity, sigs, assets)

    # Fill-rate sensitivity
    fill_rate_sensitivity(sigs, assets)
    print("\n" + "=" * 78)
    print("  END OF DIAGNOSTIC")
    print("=" * 78)


if __name__ == "__main__":
    main()
