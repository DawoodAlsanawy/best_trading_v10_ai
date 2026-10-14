#!/usr/bin/env python3
"""
diagnose_nobounce.py — Feature forensics for reversal-filter outcomes.

Compares physics features at signal time across three classes:
    Accepted   — touch + bounce (entry taken)
    No-touch   — price never returned to target
    No-bounce  — touch happened, no confirming close

Reports mean / median / std per feature per class, plus an effect size
(Cohen's d style) for Accepted vs No-bounce.

Usage:
    python3 diagnose_nobounce.py --history-days 730 --nassets 100 --timeframe 4h
"""
import argparse
import numpy as np
import trading_2_live2_2 as core


FEATURES = [
    ("score",                 "score"),
    ("|geo_accel|",           "abs_geodesic_accel"),
    ("friction",              "friction"),
    ("gauge_force",           "gauge_force"),
    ("delta_gap",             "delta_gap"),
    ("T_info",                "T_info"),
    ("H_over_Hmax",           "H_over_Hmax"),
    ("z_dev",                 "z_dev"),
    ("atr_frac",              "atr_frac"),
    ("sl_sigma",              "sl_sigma"),
    ("ema_slope_against",     "ema_slope_against"),
    ("E_therm",               "E_therm"),
    ("dF",                    "dF"),
    ("dH",                    "dH"),
    ("d2H",                   "d2H"),
    ("V",                     "V"),
    ("C",                     "C"),
    ("friction_drag_over_sl", "friction_drag_over_sl"),
    ("dist_from_ema_norm",    "dist_from_ema_norm"),
    ("tri_val",               "tri_val"),
]


def extract_features(ad, sig):
    """Compute the 20 features for a single signal."""
    fi = int(sig.feat_idx)
    ci = int(sig.close_idx)
    p = float(sig.price)
    out = {}

    def _safe(arr, i, default=0.0):
        try:
            v = float(arr[i])
            return v if np.isfinite(v) else default
        except Exception:
            return default

    out["score"] = float(sig.score)
    out["abs_geodesic_accel"] = abs(_safe(ad.geodesic_accel, fi))
    out["friction"] = _safe(ad.friction, fi)
    out["gauge_force"] = _safe(ad.gauge_force, fi)
    out["delta_gap"] = _safe(ad.delta_gap, fi)
    out["T_info"] = _safe(ad.T_info, fi)
    out["E_therm"] = _safe(ad.E_therm, fi)
    out["dF"] = _safe(ad.dF, fi)
    out["dH"] = _safe(ad.dH, fi)
    out["d2H"] = _safe(ad.d2H, fi)
    out["V"] = _safe(ad.V, fi)
    out["C"] = _safe(ad.C, fi)
    out["tri_val"] = float(getattr(sig, "tri_val", 0.0) or 0.0)

    # H_over_Hmax
    try:
        _dk = max(int(getattr(ad, "dynamic_k", 2)), 2)
        _Hmax = np.log2(_dk) + 1e-12
        out["H_over_Hmax"] = _safe(ad.H, fi) / _Hmax
    except Exception:
        out["H_over_Hmax"] = 0.0

    # z_dev
    try:
        _win = ad.closes[max(0, ci - core.CFG.N): ci]
        if len(_win) >= 2:
            _mu = float(np.mean(_win))
            _sd = float(np.std(_win))
            out["z_dev"] = (p - _mu) / _sd if _sd > 1e-12 else 0.0
        else:
            out["z_dev"] = 0.0
    except Exception:
        out["z_dev"] = 0.0

    # atr_frac
    try:
        _atr = _safe(ad.atr14, ci)
        out["atr_frac"] = _atr / p if p > 0 else 0.0
    except Exception:
        out["atr_frac"] = 0.0

    # sl_sigma
    try:
        _sigma_price = _safe(ad.E_therm, fi) * p
        _sl_dist = abs(p - float(sig.sl))
        out["sl_sigma"] = _sl_dist / max(_sigma_price, 1e-12)
    except Exception:
        out["sl_sigma"] = 0.0

    # ema_slope_against
    try:
        if ci >= 50 and ci < len(ad.ema200):
            _slope = (float(ad.ema200[ci]) -
                      float(ad.ema200[ci - 50])) / 50.0
            out["ema_slope_against"] = 1.0 if (
                (sig.action == "BUY" and _slope < 0) or
                (sig.action == "SELL" and _slope > 0)) else 0.0
        else:
            out["ema_slope_against"] = 0.0
    except Exception:
        out["ema_slope_against"] = 0.0

    # friction_drag_over_sl
    try:
        _fd_kappa = float(getattr(core.CFG, "FRICTION_DIP_KAPPA", 4.0))
        _sigma_price = _safe(ad.E_therm, fi) * p
        _fd = _fd_kappa * _sigma_price
        _sl_dist = abs(p - float(sig.sl))
        out["friction_drag_over_sl"] = _fd / max(_sl_dist, 1e-12)
    except Exception:
        out["friction_drag_over_sl"] = 0.0

    # dist_from_ema_norm
    try:
        _sigma_price = _safe(ad.E_therm, fi) * p
        _ema = _safe(ad.ema200, ci, default=p)
        out["dist_from_ema_norm"] = (p - _ema) / max(_sigma_price, 1e-12)
    except Exception:
        out["dist_from_ema_norm"] = 0.0

    return out


def classify(ad, sig, touch_window, bounce_window):
    """Return 'accepted', 'no_touch', or 'no_bounce'."""
    spm = int(ad.sub_per_main)
    if spm < 2:
        return None
    try:
        target0 = core._backtest_entry_target(sig, ad)
    except Exception:
        return None

    sm = sig.close_idx + 1
    max_main = max(1, (touch_window + bounce_window) // spm + 1)
    em = min(sm + max_main, ad.sub_highs.shape[0])
    if em <= sm:
        return None

    sh = ad.sub_highs[sm:em].reshape(-1)
    sl = ad.sub_lows[sm:em].reshape(-1)
    sc = ad.sub_closes[sm:em].reshape(-1)
    nf = sh.size

    tk = -1
    for k in range(min(touch_window, nf)):
        if not (np.isfinite(sh[k]) and np.isfinite(sl[k])):
            continue
        if sig.action == "BUY" and sl[k] <= target0:
            tk = k; break
        if sig.action == "SELL" and sh[k] >= target0:
            tk = k; break
    if tk < 0:
        return "no_touch"

    b0 = tk + 1
    b1 = min(b0 + bounce_window, nf)
    for k in range(b0, b1):
        c = sc[k]
        if not np.isfinite(c):
            continue
        if sig.action == "BUY" and c > target0:
            return "accepted"
        if sig.action == "SELL" and c < target0:
            return "accepted"
    return "no_bounce"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--history-days", type=int, default=730)
    ap.add_argument("--nassets", type=int, default=100)
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--touch-window", type=int, default=20)
    ap.add_argument("--bounce-window", type=int, default=4)
    a = ap.parse_args()

    import ccxt
    ex = ccxt.binance({'enableRateLimit': True,
                       'options': {'defaultType': 'future'}})
    cfg = core.CFG
    cfg.mode = "backtest"
    cfg.timeframe = a.timeframe
    cfg.INITIAL_CAPITAL = a.capital
    cfg.n_assets = a.nassets
    cfg.PO_FIXED_PRICE = False
    cfg.REVERSAL_CONFIRM_ENABLED = True
    cfg.REVERSAL_TOUCH_WINDOW = a.touch_window
    cfg.REVERSAL_BOUNCE_WINDOW = a.bounce_window
    cfg.SL_WIDEN_MULT = 0.7
    cfg.TP_MULT = 2.0

    cfg.TF_SCALE, cfg.TF_SECONDS, cfg.TF_HOURS = core.compute_tf_scale(
        ex, cfg.timeframe)
    _tfh = max(cfg.TF_HOURS, 1e-6)
    cfg.N = max(cfg.N, int(np.ceil(cfg.N_HOURS / _tfh)))
    cfg.W = max(cfg.W, int(np.ceil(cfg.W_HOURS / _tfh)))
    cfg.L = max(cfg.L, int(np.ceil(cfg.L_HOURS / _tfh)))
    cfg.ADV_BARS = max(1, int(round(cfg.ADV_HOURS / _tfh)))
    hd, *_ = core._resolve_data_params(cfg, "backtest", cfg.TF_HOURS,
                                       user_history_days=a.history_days)
    cfg.history_days = int(hd)

    syms = core._default_assets()[:cfg.n_assets]
    print(f"[Diag] {len(syms)} syms, {cfg.history_days}d, {a.timeframe}")

    raw, raw_sub = core.fetch_all_with_subbars(
        syms, ex, cfg.timeframe, cfg.history_days, workers=5)

    assets = {}
    for s, df in raw.items():
        ad = core.process_asset(s, df, current_capital=a.capital,
                                 sub_df=raw_sub.get(s) if raw_sub else None)
        if ad is not None:
            assets[s] = ad
    print(f"[Diag] {len(assets)} assets")

    sigs = core.build_signals(assets, mode="backtest")
    print(f"[Diag] {len(sigs)} signals")

    # Classification + feature extraction
    buckets = {"accepted": [], "no_touch": [], "no_bounce": []}
    for sig in sigs:
        ad = assets.get(sig.symbol)
        if ad is None or ad.sub_highs is None:
            continue
        cls = classify(ad, sig, a.touch_window, a.bounce_window)
        if cls is None:
            continue
        feat = extract_features(ad, sig)
        buckets[cls].append(feat)

    n_acc = len(buckets["accepted"])
    n_nt = len(buckets["no_touch"])
    n_nb = len(buckets["no_bounce"])
    tot = n_acc + n_nt + n_nb
    print(f"\n[Diag] Classification (total={tot}):")
    print(f"  Accepted : {n_acc:6d}  ({n_acc/max(tot,1)*100:.1f}%)")
    print(f"  No-touch : {n_nt:6d}  ({n_nt/max(tot,1)*100:.1f}%)")
    print(f"  No-bounce: {n_nb:6d}  ({n_nb/max(tot,1)*100:.1f}%)")

    def stats(lst, key):
        vals = [f[key] for f in lst if key in f and np.isfinite(f[key])]
        if not vals:
            return None
        arr = np.array(vals, dtype=np.float64)
        return arr.mean(), np.median(arr), arr.std(ddof=1) if len(arr) > 1 else 0.0

    print(f"\n[Diag] Feature comparison")
    header = (f"{'feature':22s}"
              f"{'ACC μ':>10s}{'ACC med':>10s}"
              f"{'NB μ':>10s}{'NB med':>10s}"
              f"{'|d|':>8s}{'verdict':>10s}")
    print(header)
    print("-" * len(header))

    for label, key in FEATURES:
        s_a = stats(buckets["accepted"], key)
        s_n = stats(buckets["no_bounce"], key)
        if s_a is None or s_n is None:
            continue
        a_mean, a_med, a_std = s_a
        n_mean, n_med, n_std = s_n
        pooled = np.sqrt((a_std ** 2 + n_std ** 2) / 2.0) + 1e-12
        d = abs(a_mean - n_mean) / pooled
        if d >= 0.5:
            v = "STRONG"
        elif d >= 0.2:
            v = "moderate"
        else:
            v = "weak"
        print(f"{label:22s}"
              f"{a_mean:10.4f}{a_med:10.4f}"
              f"{n_mean:10.4f}{n_med:10.4f}"
              f"{d:8.2f}{v:>10s}")

    # Simple decision-rule sanity check: pick the top-3 features by |d|
    # and see if a threshold on one of them could separate.
    print(f"\n[Diag] Single-feature split check (top candidates)")
    ranked = []
    for label, key in FEATURES:
        s_a = stats(buckets["accepted"], key)
        s_n = stats(buckets["no_bounce"], key)
        if s_a is None or s_n is None:
            continue
        pooled = np.sqrt((s_a[2] ** 2 + s_n[2] ** 2) / 2.0) + 1e-12
        d = abs(s_a[0] - s_n[0]) / pooled
        ranked.append((d, label, key, s_a[0], s_n[0]))
    ranked.sort(reverse=True)
    for d, label, key, a_mu, n_mu in ranked[:3]:
        print(f"  {label:22s}  d={d:.2f}  ACC μ={a_mu:.4f}  NB μ={n_mu:.4f}")


if __name__ == "__main__":
    main()
