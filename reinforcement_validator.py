#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reinforcement Statistical Validator
═══════════════════════════════════════════════════════════════════════════
Standalone analyzer (no bot code changes required).

Question answered:
  Among trades that reached 0.4-0.85R adverse excursion AND at some
  subsequent bar physics improved (P_act×1.20, friction×0.90, gauge×1.15),
  what fraction ended up profitable if we had reinforced at that bar?

Requires:
  • trades_log_backtest.jsonl    (from --analytics backtest run)
  • asset_cache/*.pkl            (from --cache-enabled backtest run)

If asset_cache missing → falls back to trades_log-only analysis
with explicit limitations stated.
"""

import json
import glob
import os
import sys
import pickle
import numpy as np
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════

TRADES_LOG = "trades_log_backtest.jsonl"
ASSET_CACHE_DIR = "asset_cache"

R_LOSS_MIN = 0.40      # minimum loss to consider for reinforcement
R_LOSS_MAX = 0.85      # maximum loss (close to SL = don't reinforce)
P_ACT_RATIO_MIN = 1.20
FRICTION_RATIO_MAX = 0.90
GAUGE_RATIO_MIN = 1.15

# Reinforcement sizing assumption
REINFORCE_QTY_FRAC = 0.30   # 30% of original


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def safe_div(a, b, default=0.0):
    try:
        if b is None or b == 0 or not np.isfinite(b):
            return default
        if not np.isfinite(a):
            return default
        return float(a) / float(b)
    except Exception:
        return default


def safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        if isinstance(v, str):
            return float(v)
        f = float(v)
        return f if np.isfinite(f) else default
    except Exception:
        return default


def parse_timestamp(s):
    """Best-effort parse. Returns pd.Timestamp or None."""
    try:
        import pandas as pd
        return pd.Timestamp(s)
    except Exception:
        return None


def safe_div(a, b, default=0.0):
    try:
        if b is None or b == 0 or not np.isfinite(b):
            return default
        if not np.isfinite(a):
            return default
        return float(a) / float(b)
    except Exception:
        return default


def classify_exit(exit_reason):
    """Returns one of: 'FULL_TP', 'FULL_SL', 'BEEsc', 'APEX', 'TOPO', 'MAXHOLD', 'EOD', 'OTHER'."""
    r = str(exit_reason or "").lower()
    if "hard tp" in r:
        return "FULL_TP"
    if "emergency sl" in r or "emergency liqproximity" in r:
        return "FULL_SL"
    if "beesc" in r:
        return "BEEsc"
    if "apex" in r:
        return "APEX"
    if "topo" in r:
        return "TOPO"
    if "maxhold" in r:
        return "MAXHOLD"
    if "endofdata" in r:
        return "EOD"
    return "OTHER"


# ═══════════════════════════════════════════════════════════════════════
# LOAD TRADES
# ═══════════════════════════════════════════════════════════════════════

def load_trades(path):
    if not os.path.exists(path):
        print(f"[ERROR] Trades log not found: {path}")
        print(f"        Run a backtest with --analytics first.")
        return []

    trades = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get('_meta'):
                continue
            trades.append(rec)

    print(f"[OK] Loaded {len(trades)} trades from {path}")
    return trades


# ═══════════════════════════════════════════════════════════════════════
# LOAD ASSET DATA
# ═══════════════════════════════════════════════════════════════════════

def discover_asset_caches(cache_dir):
    """
    Returns dict: symbol -> list of (path, timeframe, key)
    """
    if not os.path.isdir(cache_dir):
        return {}

    by_sym = {}
    for path in glob.glob(os.path.join(cache_dir, "*.pkl")):
        name = os.path.basename(path)
        if not name.endswith('.pkl'):
            continue
        stem = name[:-4]
        # Format: {safe_sym}_{tf}_{key}.pkl
        parts = stem.rsplit('_', 2)
        if len(parts) != 3:
            continue
        safe_sym, timeframe, key = parts
        symbol = safe_sym.replace('_', '/')
        by_sym.setdefault(symbol, []).append((path, timeframe, key))

    return by_sym


def load_asset_for_trade(cache_map, trade, timeframe_filter=None):
    """
    Find an AssetData whose close_idx matches the trade's entry_time.
    Returns AssetData or None.
    """
    sym = trade.get('symbol')
    if not sym or sym not in cache_map:
        return None

    entry_ci = int(trade.get('close_idx', -1))
    if entry_ci < 0:
        return None

    entry_time_str = trade.get('entry_time', '')
    entry_ts = parse_timestamp(entry_time_str)

    candidates = cache_map[sym]
    # Sort by mtime desc (most recent first)
    try:
        candidates = sorted(candidates, key=lambda x: os.path.getmtime(x[0]), reverse=True)
    except Exception:
        pass

    for path, tf, key in candidates:
        if timeframe_filter and tf != timeframe_filter:
            continue
        try:
            with open(path, 'rb') as f:
                ad = pickle.load(f)
        except Exception:
            continue

        if not hasattr(ad, 'closes') or not hasattr(ad, 'timestamps'):
            continue
        if entry_ci >= len(ad.closes):
            continue

        # Verify timestamp matches
        try:
            ad_ts = ad.timestamps[entry_ci]
            if entry_ts is not None:
                # Compare loosely
                if str(ad_ts)[:19] == str(entry_ts)[:19]:
                    return ad
            else:
                return ad  # no timestamp to verify, trust the file
        except Exception:
            continue

    return None


# ═══════════════════════════════════════════════════════════════════════
# PHYSICS COMPUTATION
# ═══════════════════════════════════════════════════════════════════════

def compute_physics_at(ad, fi):
    """Returns (P_activation, friction, gauge) at feature index fi. None on failure."""
    try:
        if fi < 0 or fi >= len(ad.E_therm):
            return None
        accel = abs(float(ad.geodesic_accel[fi]))
        fric = float(ad.friction[fi])
        T_info = float(ad.T_info[fi])
        gauge = float(ad.gauge_force[fi])

        if not all(np.isfinite([accel, fric, T_info, gauge])):
            return None

        denom = accel * T_info
        if denom <= 1e-12:
            return None
        P_act = float(np.exp(-fric / denom))
        if not np.isfinite(P_act):
            return None

        return P_act, fric, gauge
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════
# TRADE ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def analyze_trade(trade, ad):
    """
    Returns dict with:
      - status: 'ok' | 'skip_*'
      - reached_r: R at lowest point (close-based)
      - candidate: bool  (reached 0.4-0.85R AND physics improved after)
      - reinforce_bar, reinforce_price: where physics improved
      - exit_class: FULL_TP | FULL_SL | ...
      - reinforced_profit: bool | None  (would reinforcement at reinforce_price be profitable?)
      - original_pnl_R: R outcome of original position
      - R:R at reinforcement
    """
    out = {'status': 'ok'}

    try:
        action = str(trade.get('action', '')).upper()
        if action not in ('BUY', 'SELL'):
            return {'status': 'skip_invalid_action'}

        entry_price = safe_float(trade.get('entry_price'))
        if entry_price <= 0:
            return {'status': 'skip_invalid_entry'}

        exit_price = safe_float(trade.get('exit_price'))
        if exit_price <= 0:
            return {'status': 'skip_invalid_exit'}

        sl_dist = safe_float(trade.get('sl_dist_initial'))
        if sl_dist <= 0:
            return {'status': 'skip_invalid_sl_dist'}

        entry_ci = int(trade.get('close_idx', -1))
        exit_ci = int(trade.get('exit_ci', -1))
        entry_fi = int(trade.get('feat_idx', -1))
        if entry_ci < 0 or exit_ci <= entry_ci or entry_fi < 0:
            return {'status': 'skip_invalid_indices'}

        exit_class = classify_exit(trade.get('exit_reason'))
        out['exit_class'] = exit_class

        # Compute entry physics (for baseline)
        entry_phys = compute_physics_at(ad, entry_fi)
        if entry_phys is None:
            return {'status': 'skip_entry_physics'}
        entry_P, entry_fric, entry_gauge = entry_phys

        # Guard against degenerate baselines
        if entry_P <= 1e-9 or entry_fric <= 1e-9 or entry_gauge <= 1e-9:
            return {'status': 'skip_degenerate_entry_physics'}

        feat_start = ad.feat_start
        n_closes = len(ad.closes)

        # Walk bars from entry+1 to exit
        reached_low_R = 0.0
        reinforced_at_bar = None
        reinforced_at_price = None
        physics_improved_after_loss = False
        loss_reached_at_bar = None

        for i in range(entry_ci + 1, min(exit_ci + 1, n_closes)):
            fi = i - feat_start
            if fi < 0 or fi >= len(ad.E_therm):
                continue

            close = safe_float(ad.closes[i])
            if close <= 0:
                continue

            # Compute R at this bar (close-based)
            if action == 'BUY':
                r_now = (close - entry_price) / sl_dist
            else:
                r_now = (entry_price - close) / sl_dist

            if r_now < reached_low_R:
                reached_low_R = r_now

            # Did we reach 0.4R loss?
            if r_now <= -R_LOSS_MIN and loss_reached_at_bar is None:
                loss_reached_at_bar = i

            # If loss reached AND no physics improvement yet → check
            if loss_reached_at_bar is not None and reinforced_at_bar is None:
                # Not already past 0.85R at this bar (would be too close to SL)
                if r_now < -R_LOSS_MAX:
                    continue

                phys = compute_physics_at(ad, fi)
                if phys is None:
                    continue
                P_now, fric_now, gauge_now = phys

                P_ratio = safe_div(P_now, entry_P, 0.0)
                fric_ratio = safe_div(fric_now, entry_fric, 999.0)
                gauge_ratio = safe_div(gauge_now, entry_gauge, 0.0)

                if (P_ratio >= P_ACT_RATIO_MIN
                        and fric_ratio <= FRICTION_RATIO_MAX
                        and gauge_ratio >= GAUGE_RATIO_MIN):
                    reinforced_at_bar = i
                    reinforced_at_price = close
                    physics_improved_after_loss = True

        out['reached_low_R'] = float(reached_low_R)
        out['reached_04R'] = (loss_reached_at_bar is not None)
        out['candidate'] = physics_improved_after_loss

        if not physics_improved_after_loss:
            return out

        # Compute profit of reinforcement
        A = reinforced_at_price
        if A <= 0:
            return {'status': 'skip_invalid_reinforce_price'}

        if action == 'BUY':
            reinforced_gain = exit_price - A
        else:
            reinforced_gain = A - exit_price

        out['reinforce_bar'] = reinforced_at_bar
        out['reinforce_price'] = A
        out['reinforced_gain_price'] = float(reinforced_gain)
        out['reinforced_profit'] = (reinforced_gain > 0)

        # Convert to R units (relative to entry sl_dist)
        out['reinforced_gain_R'] = safe_div(reinforced_gain, sl_dist, 0.0)

        # Original R
        if action == 'BUY':
            original_gain = exit_price - entry_price
        else:
            original_gain = entry_price - exit_price
        out['original_gain_R'] = safe_div(original_gain, sl_dist, 0.0)

        # R:R at reinforcement point
        if action == 'BUY':
            dist_to_sl = A - (entry_price - sl_dist)  # assuming sl at entry - sl_dist
        else:
            dist_to_sl = (entry_price + sl_dist) - A

        # But we should use actual SL price
        sl_price = safe_float(trade.get('signal_sl'))
        tp_price = safe_float(trade.get('signal_tp1'))
        if sl_price > 0 and tp_price > 0:
            if action == 'BUY':
                dist_to_sl = A - sl_price
                dist_to_tp = tp_price - A
            else:
                dist_to_sl = sl_price - A
                dist_to_tp = A - tp_price

            if dist_to_sl > 0:
                out['rr_at_reinforce'] = safe_div(dist_to_tp, dist_to_sl, 0.0)

        return out
    except Exception as e:
        return {'status': f'error:{type(e).__name__}'}


# ═══════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("═" * 72)
    print("  Reinforcement Statistical Validator")
    print("═" * 72)
    print()

    trades = load_trades(TRADES_LOG)
    if not trades:
        return

    cache_map = discover_asset_caches(ASSET_CACHE_DIR)
    n_sym_cached = len(cache_map)
    n_files = sum(len(v) for v in cache_map.values())
    print(f"[OK] Found {n_files} asset cache files for {n_sym_cached} symbols")
    print()

    if not cache_map:
        print("⚠️  ASSET CACHE MISSING")
        print("    Without it, we can only do LIMITED analysis from trades_log alone.")
        print()
        print("    Run a backtest first with --cache enabled (default), OR")
        print("    run with --no-clear-cache if you already cleared it accidentally.")
        print()
        # Fall back to simple analysis
        run_simple_analysis(trades)
        return

    # Full analysis with cache
    print("Running FULL analysis with physics reconstruction...")
    print()

    results = []
    skipped = {}
    for i, trade in enumerate(trades):
        if (i + 1) % 100 == 0:
            print(f"  Processing {i+1}/{len(trades)}...")

        ad = load_asset_for_trade(cache_map, trade)
        if ad is None:
            st = 'skip_no_assetdata'
            skipped[st] = skipped.get(st, 0) + 1
            continue

        res = analyze_trade(trade, ad)
        results.append(res)
        if res['status'] != 'ok':
            skipped[res['status']] = skipped.get(res['status'], 0) + 1

    print(f"  Done. Analyzed {len(results)} trades.")
    print()

    report_results(results, skipped)


def report_results(results, skipped):
    print("═" * 72)
    print("  RESULTS")
    print("═" * 72)
    print()

    if not results:
        print("[ERROR] No trades analyzed.")
        return

    if skipped:
        print("Skipped trades by reason:")
        for k, v in sorted(skipped.items(), key=lambda x: -x[1]):
            print(f"  {k:40s}: {v}")
        print()

    # Aggregate
    n_total = len(results)
    n_ok = sum(1 for r in results if r.get('status') == 'ok')
    n_reached_04 = sum(1 for r in results if r.get('reached_04R'))
    n_candidates = sum(1 for r in results if r.get('candidate'))

    print(f"Total trades analyzed     : {n_total:,}")
    print(f"Reached 0.4R loss         : {n_reached_04:,} ({100*n_reached_04/max(n_total,1):.1f}%)")
    print(f"  + Physics improved      : {n_candidates:,} ({100*n_candidates/max(n_total,1):.1f}%)")
    print()

    if n_candidates == 0:
        print("[VERDICT] No candidates met the reinforcement criteria.")
        print("          The filter is too strict, or the data doesn't support it.")
        print()
        return

    # Among candidates, how many would have profited?
    candidates = [r for r in results if r.get('candidate')]
    n_profit = sum(1 for r in candidates if r.get('reinforced_profit'))
    n_loss = n_candidates - n_profit
    p_profit = n_profit / n_candidates

    # Compute R-gain stats
    gains_R = [r.get('reinforced_gain_R', 0) for r in candidates]
    mean_gain_R = float(np.mean(gains_R)) if gains_R else 0.0
    median_gain_R = float(np.median(gains_R)) if gains_R else 0.0

    # Compute EV of reinforcement
    # If we add 30% qty at reinforce_price, R-gain per reinforcement = 0.30 × gain_R
    r_qty = REINFORCE_QTY_FRAC
    ev_per_reinforce_R = r_qty * mean_gain_R

    # Original EV of the position (baseline)
    orig_gains_R = [r.get('original_gain_R', 0) for r in candidates]
    mean_orig_R = float(np.mean(orig_gains_R)) if orig_gains_R else 0.0

    print("─" * 72)
    print("  CANDIDATE TRADES (met all physics criteria)")
    print("─" * 72)
    print(f"Candidates                : {n_candidates:,}")
    print(f"  Profitable if reinforced: {n_profit:,} ({100*p_profit:.1f}%)")
    print(f"  Unprofitable            : {n_loss:,} ({100*(1-p_profit):.1f}%)")
    print()
    print(f"Mean R-gain per reinforcement : {mean_gain_R:+.3f} R")
    print(f"Median R-gain per reinforcement: {median_gain_R:+.3f} R")
    print()
    print(f"With {int(r_qty*100)}% qty add → EV per reinforcement: {ev_per_reinforce_R:+.4f} R")
    print()

    # Break-even probability
    # EV per reinforcement = P × (mean_positive_gain) + (1-P) × (mean_negative_gain)
    # Need to split gains_R into positive and negative
    pos_gains = [g for g in gains_R if g > 0]
    neg_gains = [g for g in gains_R if g <= 0]
    mean_pos = float(np.mean(pos_gains)) if pos_gains else 0.0
    mean_neg = float(np.mean(neg_gains)) if neg_gains else 0.0

    if mean_pos > 0 and mean_neg < 0:
        # Break-even probability: P × mean_pos + (1-P) × mean_neg > 0
        # P × (mean_pos - mean_neg) > -mean_neg
        # P > -mean_neg / (mean_pos - mean_neg)
        p_be = -mean_neg / (mean_pos - mean_neg)
        print(f"Mean positive gain (if win)   : {mean_pos:+.3f} R")
        print(f"Mean negative gain (if loss)  : {mean_neg:+.3f} R")
        print(f"Break-even win probability    : {100*p_be:.1f}%")
        print(f"Actual observed win probability: {100*p_profit:.1f}%")
        print()
        if p_profit > p_be + 0.05:
            print(f"✅ VERDICT: Physics filter has an edge.")
            print(f"            Win rate {100*p_profit:.1f}% > break-even {100*p_be:.1f}% + 5%")
            print(f"            → Reinforcement is +EV.")
        elif p_profit > p_be:
            print(f"⚠️  MARGINAL: Win rate above break-even but margin < 5%.")
            print(f"            Positive but not robust.")
        else:
            print(f"❌ VERDICT: Physics filter has NO edge.")
            print(f"            Win rate {100*p_profit:.1f}% < break-even {100*p_be:.1f}%")
            print(f"            → Reinforcement would LOSE money.")
    else:
        print(f"⚠️  Cannot compute break-even: pos_gains={len(pos_gains)}, neg_gains={len(neg_gains)}")

    print()

    # Also compare against "no reinforcement" baseline
    print("─" * 72)
    print("  BASELINE (no reinforcement)")
    print("─" * 72)
    print(f"Mean original R per candidate trade : {mean_orig_R:+.3f} R")
    print()
    print(f"Reinforcement uplift : {ev_per_reinforce_R:+.4f} R per trade")
    if ev_per_reinforce_R > 0.01:
        print(f"✅ Reinforcement ADDS value")
    else:
        print(f"❌ Reinforcement does NOT add value")
    print()

    print("═" * 72)
    print("  END OF REPORT")
    print("═" * 72)


def run_simple_analysis(trades):
    """Fallback: analyze trades_log alone, without physics reconstruction."""
    print("═" * 72)
    print("  FALLBACK ANALYSIS (no asset_cache)")
    print("═" * 72)
    print()
    print("⚠️  Without asset_cache we CANNOT measure:")
    print("    - Whether physics improved DURING trades")
    print("    - Base rate of 'reached 0.4R then TP'")
    print()
    print("What we CAN measure from trades_log:")
    print()

    n = len(trades)
    if n == 0:
        print("  No trades.")
        return

    # Exit reason distribution
    exit_dist = {}
    for t in trades:
        cls = classify_exit(t.get('exit_reason'))
        exit_dist[cls] = exit_dist.get(cls, 0) + 1

    print("Exit reasons distribution:")
    for k, v in sorted(exit_dist.items(), key=lambda x: -x[1]):
        print(f"  {k:15s}: {v:5d} ({100*v/n:.1f}%)")
    print()

    # Base rates
    n_tp = sum(1 for t in trades if 'Hard TP' in str(t.get('exit_reason', '')))
    n_sl = sum(1 for t in trades if 'Emergency SL' in str(t.get('exit_reason', '')))
    n_win = sum(1 for t in trades if safe_float(t.get('net_pnl')) > 0)

    print(f"TP rate  : {100*n_tp/n:.1f}%")
    print(f"SL rate  : {100*n_sl/n:.1f}%")
    print(f"Win rate : {100*n_win/n:.1f}%  (by net_pnl > 0)")
    print()

    # MFE distribution by outcome
    print("MFE distribution by outcome:")
    for label, cond in [
        ("TP trades", lambda t: 'Hard TP' in str(t.get('exit_reason', ''))),
        ("SL trades", lambda t: 'Emergency SL' in str(t.get('exit_reason', ''))),
    ]:
        subset = [safe_float(t.get('mfe_frac')) for t in trades if cond(t)]
        if subset:
            arr = np.array(subset)
            print(f"  {label:15s} (n={len(arr):5d}): "
                  f"mean={arr.mean():.4f} median={np.median(arr):.4f} "
                  f"p90={np.percentile(arr, 90):.4f}")
    print()

    # Correlation of entry features with outcome
    print("Entry feature correlation with win (point-biserial):")
    for feat in ['E_therm', 'friction', 'gauge_force', 'delta_gap',
                 'geodesic_accel', 'H', 'dH', 'T_info', 'V']:
        vals = []
        wins = []
        for t in trades:
            v = t.get(feat)
            if v is None:
                continue
            try:
                v = float(v)
                if not np.isfinite(v):
                    continue
            except Exception:
                continue
            vals.append(v)
            wins.append(1 if safe_float(t.get('net_pnl')) > 0 else 0)

        if len(vals) < 30:
            continue

        # Simple correlation
        try:
            corr = float(np.corrcoef(vals, wins)[0, 1])
            if np.isfinite(corr):
                print(f"  {feat:20s}: r = {corr:+.4f}  (n={len(vals)})")
        except Exception:
            continue

    print()
    print("─" * 72)
    print("  CONCLUSION")
    print("─" * 72)
    print()
    print("To answer the reinforcement question, you MUST have asset_cache.")
    print()
    print("Action: re-run the backtest WITHOUT --clear-cache:")
    print(f"  python trading_2_live4_claude2_v4.py --mode backtest ...")
    print()
    print("Then re-run this analyzer.")


if __name__ == "__main__":
    main()
