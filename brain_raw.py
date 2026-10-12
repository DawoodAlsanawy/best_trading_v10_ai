#!/usr/bin/env python3
"""
brain_raw.py — Unfiltered signal brain for BUY/SELL edge discovery.
Reuses all physics from trading_2_live2.py, removes ALL filters.
"""
import argparse, copy, json, os, sys
import numpy as np

from trading_2_live2 import (
    CFG, Signal, OpenPosition, Trade, AssetData,
    compute_features, fit_kmeans, assign, entropy_series,
    compute_gauge_force_and_gap, compute_entropy_friction,
    compute_geometry, compute_lyapunov_dynamic, compute_PE,
    compute_energy_dynamics, compute_tri, process_asset,
    compute_geodesic_kelly, compute_geodesic_stop,
    effective_bars, _ts_to_ci, precompute_entry_fills,
    simulate_portfolio, apply_slippage, cap_notional,
    _get_mmr_for_symbol, compute_liquidation_price,
    compute_max_leverage_by_liq, compute_trail_params,
    check_thermodynamic_apex, _advance, _get_risk_multiplier,
    _resonance_state_for_direction, precompute_correlations,
    _trade_log_from_backtest, _extract_entry_features_for_log,
    fetch_all, scan_top_assets, compute_tf_scale,
    _warmup_numba_kernels, _resolve_data_params,
    _compute_entry_dip,
    prefetch_all_leverage_tiers,
)

# ── We must re-bind the trade logger to prevent cross-contamination ──
import trading_2_live2 as _core


# ════════════════════════════════════════════════════════════════
# RAW SIGNAL BUILDER — all filters removed
# ════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# [RAW-EXIT] Permanent _advance() replacement.
# SL / TP / MaxHold ONLY. Nothing else, ever.
# ═══════════════════════════════════════════════════════════════
import trading_2_live2 as _core


def _advance_raw(pos, ad, to_ci, partial_cb=None):
    """Pure exit walker: SL, TP, MaxHold. Nothing else."""
    sig = pos.signal
    sl = pos.trail_sl
    start = pos.current_ci + 1
    end = min(to_ci, len(ad.closes) - 1)
    if start > end:
        return 0., "", -1

    pen_frac = (CFG.FILL_PENETRATION_BPS * 1e-4
                if CFG.FILL_APPLY_TO_EXITS else 0.0)
    _use_sub = (ad.sub_highs is not None
                and ad.sub_lows is not None
                and ad.sub_per_main >= 2)

    def _check(high, low):
        if sig.action == "BUY":
            if low <= sl * (1.0 - pen_frac):
                return "SL", sl
            if high >= sig.tp1 * (1.0 + pen_frac):
                return "TP", sig.tp1
        else:
            if high >= sl * (1.0 + pen_frac):
                return "SL", sl
            if low <= sig.tp1 * (1.0 - pen_frac):
                return "TP", sig.tp1
        return None, 0.0

    _max_hold = effective_bars(CFG.MAX_HOLD_BARS)

    for cidx in range(start, end + 1):
        p = ad.closes[cidx]
        if _use_sub and cidx == pos.entry_ci:
            j0, j1 = int(pos.entry_sub_idx) + 1, ad.sub_per_main
        elif _use_sub:
            j0, j1 = 0, ad.sub_per_main
        else:
            j0, j1 = 0, 0

        if _use_sub:
            for j in range(j0, j1):
                sh = ad.sub_highs[cidx, j]
                sll = ad.sub_lows[cidx, j]
                if not (np.isfinite(sh) and np.isfinite(sll)):
                    continue
                mfe = ((sh - pos.entry_px) / pos.entry_px
                       if sig.action == "BUY"
                       else (pos.entry_px - sll) / pos.entry_px)
                if mfe > pos.mfe_frac:
                    pos.mfe_frac = mfe
                r, px = _check(sh, sll)
                if r == "SL":
                    pos.current_ci = cidx
                    return px, "Emergency SL", cidx
                if r == "TP":
                    pos.current_ci = cidx
                    return px, "Hard TP", cidx
        else:
            if cidx == pos.entry_ci:
                continue
            high = ad.highs[cidx]
            low = ad.lows[cidx]
            mfe = ((high - pos.entry_px) / pos.entry_px
                   if sig.action == "BUY"
                   else (pos.entry_px - low) / pos.entry_px)
            if mfe > pos.mfe_frac:
                pos.mfe_frac = mfe
            r, px = _check(high, low)
            if r == "SL":
                pos.current_ci = cidx
                return px, "Emergency SL", cidx
            if r == "TP":
                pos.current_ci = cidx
                return px, "Hard TP", cidx

        if cidx - pos.entry_ci > _max_hold:
            pos.current_ci = cidx
            return p, "MaxHold", cidx

    pos.current_ci = max(end, pos.current_ci)
    return 0., "", -1


_core._advance = _advance_raw

CFG.TRAIL_ENABLED      = False
CFG.APEX_ENABLED       = False
CFG.BREAKEVEN_ENABLED  = False
CFG.PARTIAL_TP_ENABLED = False
CFG.TIME_KILL_ENABLED  = False
# ═══════════════════════════════════════════════════════════════


def build_signals_raw(assets, z_min=0.0):
    sigs = []
    for sym, ad in assets.items():
        n = len(ad.score)
        for fi in range(ad.train_end + 1, n):
            ci = ad.feat_start + fi
            if ci >= len(ad.closes) - 1:
                continue
            p = ad.closes[ci]
            if p <= 0:
                continue

            geo_accel = float(ad.geodesic_accel[fi])
            fric_val = float(ad.friction[fi]) + 1e-6
            T_info = float(ad.T_info[fi])
            # P_act computed but NOT used as a gate (raw mode)
            P_act = float(np.exp(-fric_val / ((abs(geo_accel) + 1e-9) * T_info)))

            _z_win = ad.closes[max(0, ci - CFG.N): ci]
            if len(_z_win) < 2:
                continue
            _z_mu = float(np.mean(_z_win))
            _z_sd = float(np.std(_z_win))
            if _z_sd <= 1e-12:
                continue
            _z_dev = (p - _z_mu) / _z_sd
            if _z_dev == 0.0:
                continue
            if abs(_z_dev) < z_min:
                continue
            action = "BUY" if _z_dev < 0 else "SELL"

            try:
                _sf = float(ad.E_therm[fi])
                if not np.isfinite(_sf) or _sf <= 1e-6:
                    _sf = 0.01
            except Exception:
                _sf = 0.01
            _sigma_price = _sf * p
            _fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))
            _friction_dip = _fd_kappa * _sigma_price
            _atr_dip = _compute_entry_dip(ad, fi, ci, action, p)
            _entry_dip = max(_friction_dip, 0.5 * _atr_dip)
            if _entry_dip <= 0.0:
                _entry_dip = p * 0.001

            tunnel = (p - _entry_dip) if action == "BUY" else (p + _entry_dip)
            sl_dist = compute_geodesic_stop(tunnel, ad, fi, CFG)
            sl = tunnel - sl_dist if action == "BUY" else tunnel + sl_dist
            _tpm = float(getattr(CFG, 'TP_MULT', 1.5))
            tp1 = tunnel + sl_dist * _tpm if action == "BUY" else tunnel - sl_dist * _tpm

            if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel):
                continue

            s = Signal(
                timestamp=ad.timestamps[ci], symbol=sym, price=tunnel,
                score=float(ad.score[fi]), action=action,
                sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                dynamic_risk=compute_geodesic_kelly(ad, fi, CFG),
                T_info_val=T_info, dyn_sl_factor=sl_dist / tunnel,
                entry_ref_price=float(p), entry_base_dip=float(_entry_dip),
                mfal_p_act=P_act,
            )
            # Extra attributes for downstream logging
            s.z_dev = float(_z_dev)
            s.friction_v = fric_val
            s.gauge_v = float(ad.gauge_force[fi])
            sigs.append(s)
    sigs.sort(key=lambda s: (s.timestamp, -s.score))
    return sigs


# ════════════════════════════════════════════════════════════════
# RAW PORTFOLIO SIMULATOR — single side, no correlation gate
# ════════════════════════════════════════════════════════════════
def simulate_portfolio_raw(signals, assets, side):
    """
    Isolated backtest per side.
    - Filters signals to one side only.
    - Passes empty corr_matrix → no correlation gate.
    - Uses a LOCAL copy of CFG attributes, does NOT mutate global CFG.
    """
    sg = [copy.copy(s) for s in signals if s.action == side]

    # Save + override MAX_CONCURRENT_ASSETS via a temporary swap
    _orig_max = CFG.MAX_CONCURRENT_ASSETS
    _orig_budget = CFG.BUDGET_ENABLED
    try:
        CFG.MAX_CONCURRENT_ASSETS = 1
        # Keep budget sizing identical to original (heat-max per slot).
        # If you want to compare fairly, keep BUDGET_ENABLED=True.
        # Set CFG.BUDGET_ENABLED = False only if you want flat per-trade risk.
        return simulate_portfolio(sg, assets, {}, "backtest")
    finally:
        CFG.MAX_CONCURRENT_ASSETS = _orig_max
        CFG.BUDGET_ENABLED = _orig_budget


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def _load_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not r.get('_meta'):
                out.append(r)
    return out


def _stats(recs, eq):
    if not recs:
        return None
    pn = np.array([r['net_pnl'] for r in recs], float)
    lr = np.array([r['log_return'] for r in recs], float)

    R = []
    for r in recs:
        sd = float(r.get('sl_dist_initial') or 0.0)
        if sd <= 0 or r.get('entry_price') is None or r.get('exit_price') is None:
            continue
        sg = 1.0 if r.get('action') == 'BUY' else -1.0
        R.append(sg * (float(r['exit_price']) - float(r['entry_price'])) / sd)

    w = float(pn[pn > 0].sum()) if (pn > 0).any() else 0.0
    l = float(-pn[pn <= 0].sum()) if (pn <= 0).any() else 0.0
    if len(lr) > 1 and lr.std(ddof=1) > 1e-10:
        sh = float(lr.mean() / lr.std(ddof=1) * np.sqrt(252))
    else:
        sh = 0.0

    e = np.array(eq, float)
    peak = np.maximum.accumulate(e)
    dd = float(np.max((peak - e) / (peak + 1e-12)) * 100) if len(e) else 0.0

    return dict(
        n=len(recs),
        win=100.0 * float((pn > 0).mean()),
        R=float(np.mean(R)) if R else 0.0,
        pf=(w / l) if l > 1e-12 else float('inf'),
        sh=sh,
        dd=dd,
        hold=float(np.mean([r.get('hold_bars', 0) for r in recs])),
        mfe=float(np.mean([r.get('mfe_frac', 0.0) for r in recs])),
    )


def _feature_row(recs, win_bool, key):
    vals = []
    for r in recs:
        if bool(r.get('is_win')) != win_bool:
            continue
        v = r.get(key)
        if v is None:
            continue
        try:
            v = float(v)
        except Exception:
            continue
        if not np.isfinite(v):
            continue
        vals.append(abs(v) if key == 'geodesic_accel' else v)
    return float(np.mean(vals)) if vals else float('nan')


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════
def main_raw():
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", default="BOTH", choices=["BUY", "SELL", "BOTH"])
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--history-days", type=int, default=30)
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--nassets", type=int, default=10)
    ap.add_argument("--z-min", type=float, default=0.0)
    ap.add_argument("--tp-mult",  type=float, default=None,
                    help="TP distance in R units")
    ap.add_argument("--sl-kappa", type=float, default=None,
                    help="SL_REF_KAPPA override")
    ap.add_argument("--max-hold", type=int,   default=None,
                    help="MaxHold bars override")
    ap.add_argument("--no-trail",     action="store_true")
    ap.add_argument("--no-apex",      action="store_true")
    ap.add_argument("--no-breakeven", action="store_true")
    ap.add_argument("--no-partial",   action="store_true")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    import ccxt
    ex = ccxt.binance({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })

    # ── Configure CFG ──
    CFG.mode = "backtest"
    CFG.timeframe = a.timeframe
    CFG.INITIAL_CAPITAL = a.capital
    CFG.n_assets = a.nassets
    CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = compute_tf_scale(ex, CFG.timeframe)

    _tfh = max(float(CFG.TF_HOURS), 1e-6)
    CFG.N = max(CFG.N, int(np.ceil(CFG.N_HOURS / _tfh)))
    CFG.W = max(CFG.W, int(np.ceil(CFG.W_HOURS / _tfh)))
    CFG.L = max(CFG.L, int(np.ceil(CFG.L_HOURS / _tfh)))
    CFG.ADV_BARS = max(1, int(round(CFG.ADV_HOURS / _tfh)))

    hd, *_ = _resolve_data_params(
        CFG, "backtest", CFG.TF_HOURS,
        user_history_days=a.history_days
    )
    CFG.history_days = int(hd)
    if a.tp_mult   is not None: CFG.TP_MULT        = float(a.tp_mult)
    if a.sl_kappa  is not None: CFG.SL_REF_KAPPA   = float(a.sl_kappa)
    if a.max_hold  is not None: CFG.MAX_HOLD_BARS  = int(a.max_hold)
    print(f"[Tune] TP_MULT={CFG.TP_MULT}  SL_REF_KAPPA={CFG.SL_REF_KAPPA}  MAX_HOLD={CFG.MAX_HOLD_BARS}")
    CFG.TRAIL_ENABLED      = not a.no_trail
    CFG.APEX_ENABLED       = not a.no_apex
    CFG.BREAKEVEN_ENABLED  = not a.no_breakeven
    CFG.PARTIAL_TP_ENABLED = not a.no_partial
    print("[Exits] RAW — SL/TP/MaxHold only")
    _warmup_numba_kernels()

    # ── Fetch + process ──
    print(f"[Raw] timeframe={CFG.timeframe} history={CFG.history_days}d "
          f"nassets={a.nassets} z_min={a.z_min}")
    syms = scan_top_assets(ex, CFG.n_assets)
    raw = fetch_all(syms, ex, CFG.timeframe, CFG.history_days, workers=5)
    try:
        prefetch_all_leverage_tiers(ex, list(raw.keys()))
    except Exception:
        pass

    assets = {}
    for s, df in raw.items():
        ad = process_asset(s, df, current_capital=a.capital)
        if ad is not None:
            assets[s] = ad
    print(f"[Raw] processed {len(assets)}/{len(raw)} assets")

    # ── Build signals (unfiltered) ──
    sigs = build_signals_raw(assets, a.z_min)
    n_buy = sum(1 for s in sigs if s.action == "BUY")
    n_sell = sum(1 for s in sigs if s.action == "SELL")
    print(f"[Raw] signals: BUY={n_buy} SELL={n_sell} total={len(sigs)}")

    # ── Dump raw signals ──
    with open("raw_signals.jsonl", "w", encoding="utf-8") as f:
        for s in sigs:
            r = _extract_entry_features_for_log(s, assets[s.symbol])
            r.update(
                symbol=s.symbol,
                ts=str(s.timestamp),
                z_dev=float(getattr(s, 'z_dev', np.nan)),
                friction_v=float(getattr(s, 'friction_v', np.nan)),
                gauge_v=float(getattr(s, 'gauge_v', np.nan)),
            )
            f.write(json.dumps(r, default=str) + "\n")

    # ── Per-side backtest ──
    sides = ("BUY", "SELL") if a.side == "BOTH" else (a.side,)
    res, allrecs = {}, {}

    for side in sides:
        path = f"trades_{side}.jsonl"
        if os.path.exists(path):
            os.remove(path)
        # Rebind the logger's global path for this side
        _core._TRADE_LOG_PATH = path
        # Write a meta header (mirrors original format)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                '_meta': True, 'mode': 'backtest_raw', 'side': side,
                'timeframe': CFG.timeframe,
                'z_min': a.z_min,
                'n_signals_input': sum(1 for s in sigs if s.action == side),
            }) + "\n")

        trades, eq = simulate_portfolio_raw(sigs, assets, side)
        recs = _load_jsonl(path)
        allrecs[side] = recs
        res[side] = _stats(recs, eq)

    # ── Summary table ──
    hdr = f"{'SIDE':5s}{'n':>7s}{'win%':>8s}{'muR':>9s}{'PF':>7s}{'Sharpe':>9s}{'DD%':>8s}{'hold':>8s}{'MFE%':>8s}"
    print("\n" + hdr)
    print("-" * len(hdr))
    for side in sides:
        s = res[side]
        if s is None:
            print(f"{side:5s}{0:7d}  (no trades)")
            continue
        print(f"{side:5s}{s['n']:7d}{s['win']:8.1f}{s['R']:9.3f}"
              f"{s['pf']:7.2f}{s['sh']:9.2f}{s['dd']:8.1f}"
              f"{s['hold']:8.1f}{s['mfe']*100:8.2f}")

    # ── Feature discriminator table ──
    print(f"\n{'feat':16s}{'BUY_win':>11s}{'BUY_loss':>11s}"
          f"{'SELL_win':>11s}{'SELL_loss':>11s}")
    print("-" * 60)
    for lab, key in (
        ("friction", "friction"),
        ("|geo_accel|", "geodesic_accel"),
        ("z_dev", "z_dev"),
        ("T_info", "T_info"),
        ("gauge_force", "gauge_force"),
        ("score", "score"),
        ("atr_frac", "atr"),
        ("sl_sigma", "sl_sigma"),
        ("H_over_Hmax", "H_over_Hmax"),
        ("ema_slope_agn", "ema_slope_against"),
    ):
        row = [lab.ljust(16)]
        for side in ("BUY", "SELL"):
            if side not in allrecs:
                row += [f"{'--':>11s}", f"{'--':>11s}"]
                continue
            recs = allrecs[side]
            w = _feature_row(recs, True, key)
            l = _feature_row(recs, False, key)
            row.append(f"{w:11.4f}" if np.isfinite(w) else f"{'nan':>11s}")
            row.append(f"{l:11.4f}" if np.isfinite(l) else f"{'nan':>11s}")
        print("".join(row))

    # ── z_dev histogram ──
    edges = np.linspace(-4, 4, 11)
    print("\nz_dev bins: " + "  ".join(f"{e:+.1f}" for e in edges))
    for side in ("BUY", "SELL"):
        z = np.array([s.z_dev for s in sigs if s.action == side], float)
        if len(z) == 0:
            print(f"{side:5s} (none)")
            continue
        z = np.clip(z, -3.999, 3.999)
        c, _ = np.histogram(z, bins=edges)
        print(f"{side:5s}" + " ".join(f"{int(x):5d}" for x in c))

    # ── Win rate per z-bin ──
    print("\nWin% per z-bin (from trades):")
    for side in sides:
        recs = allrecs.get(side, [])
        if not recs:
            continue
        zs = np.array([r.get('z_dev', np.nan) for r in recs], float)
        wins = np.array([1.0 if r.get('is_win') else 0.0 for r in recs])
        valid = np.isfinite(zs)
        zs, wins = zs[valid], wins[valid]
        if len(zs) < 5:
            continue
        bins = np.clip(zs, -3.999, 3.999)
        hist, edges2 = np.histogram(bins, bins=edges)
        counts, _ = np.histogram(bins, bins=edges, weights=wins)
        wr = np.where(hist > 0, 100.0 * counts / np.maximum(hist, 1), np.nan)
        print(f"{side:5s}" + " ".join(
            f"{wr[i]:5.1f}" if np.isfinite(wr[i]) else "  --  "
            for i in range(len(wr))
        ))


def _emit_csv_row(a, res, sides):
    """Append one CSV row per side to edges_scan.csv."""
    import csv, os
    hdr = ["tag","side","z_min","timeframe","history_days","n","win","muR",
           "PF","Sharpe","DD","hold","MFE","exits"]
    new = not os.path.exists("edges_scan.csv")
    with open("edges_scan.csv","a",newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(hdr)
        for side in sides:
            r = res.get(side)
            if not r:
                w.writerow([a.tag,side,a.z_min,a.timeframe,a.history_days,
                            0,0,0,0,0,0,0,0,"none"])
                continue
            w.writerow([a.tag,side,a.z_min,a.timeframe,a.history_days,
                        r["n"], f"{r['win']:.2f}", f"{r['R']:.4f}",
                        f"{r['pf']:.4f}", f"{r['sh']:.4f}",
                        f"{r['dd']:.2f}", f"{r['hold']:.2f}",
                        f"{r['mfe']*100:.4f}",
                        f"trail={not a.no_trail};apex={not a.no_apex};"
                        f"be={not a.no_breakeven};ptp={not a.no_partial}"])


if __name__ == "__main__":
    main_raw()
