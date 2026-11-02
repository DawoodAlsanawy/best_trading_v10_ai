#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
geodesic_direction_test.py
==========================
Standalone, honest test: does the sign of the geodesic equation carry
directional predictive power?

READS:   market_data_cache/*.parquet (or *.csv)
         — skips files with '_sub' in the name
         — rejects files with < 300 bars
NO IMPORTS from the bot. Self-contained.

DESIGN (no statistical shortcuts):
  1. Features at bar i use only data ≤ i (no look-ahead).
  2. Median for symbolic quantization uses FIRST-50% only.
  3. Forward return at bar i = log(close[i+h] / close[i]).
  4. |return| < 1e-9 excluded from hit counting.
  5. Multiple testing: Bonferroni-corrected p-values.
  6. Base rates (always BUY / always SELL) always reported.
  7. Split-half consistency required for "real edge".
  8. IC (Pearson) reported alongside hit rate.
  9. 95% confidence interval on hit rate.
 10. Inversion tests (H1b, H2b, H3b) to catch sign errors.

USAGE:
    python3 geodesic_direction_test.py
    python3 geodesic_direction_test.py /path/to/cache

REQUIRES:
    numpy pandas scipy pyarrow
"""

import os
import sys
import glob
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import binomtest, pearsonr, skew, kurtosis

warnings.filterwarnings("ignore")


# ─── Constants (reproduced from bot, not imported) ───────────
N_BARS = 24
W_ENTROPY = 20
K_QUANT = 2
GAMMA_0 = 0.01
KAPPA = 0.1
XI = 1.0
LORENTZ_Q = 1.0
Z_THRESHOLD = 1.5
MIN_BARS = 300
MIN_FEATURES = 100
MIN_SAMPLES = 50


# ─── Features (pure numpy) ───────────────────────────────────
def compute_features(closes, volumes):
    n = len(closes)
    lr = np.diff(np.log(np.maximum(closes, 1e-12)))
    out = np.zeros((n - N_BARS, 7), dtype=np.float64)
    for i in range(N_BARS, n):
        r = lr[i - N_BARS:i]
        p = closes[i - N_BARS:i + 1]
        v = volumes[i - N_BARS:i]
        s = np.std(r, ddof=1)
        if s < 1e-10:
            continue
        vec = np.array([
            np.mean(r), s,
            float(skew(r, bias=False)),
            float(kurtosis(r, bias=False)),
            float(np.max(p) - np.min(p)),
            float(np.mean(v)) if len(v) > 0 else 1.0,
            float((closes[i] - closes[i - N_BARS])
                  / (closes[i - N_BARS] + 1e-12)),
        ], dtype=np.float64)
        nm = np.linalg.norm(vec)
        if nm > 1.0:
            vec /= nm
        out[i - N_BARS] = vec
    return out


def entropy_series(sym_q, k=K_QUANT):
    n = len(sym_q)
    H = np.zeros(n)
    for i in range(W_ENTROPY - 1, n):
        w = sym_q[i - W_ENTROPY + 1:i + 1]
        counts = np.bincount(w, minlength=k).astype(float)
        total = counts.sum()
        if total <= 0:
            continue
        p = counts / total
        nz = p[p > 0]
        H[i] = float(-np.sum(nz * np.log2(nz + 1e-12)))
    return H


def gauge_force_series(sym_q, k=K_QUANT):
    n = len(sym_q)
    gf = np.zeros(n)
    for i in range(W_ENTROPY, n):
        window = sym_q[i - W_ENTROPY:i]
        T = np.zeros((k, k), dtype=np.float64)
        for j in range(1, len(window)):
            T[window[j - 1], window[j]] += 1.0
        s = T.sum()
        if s > 0:
            T /= s
        A = T - T.T
        gf[i] = float(np.linalg.norm(A, ord='fro'))
    return gf


def friction_series(H, k=K_QUANT):
    Hmax = np.log2(k) + 1e-12
    Sr = np.clip(H / Hmax, 0.0, 1.0)
    return GAMMA_0 + KAPPA * np.exp(XI * (1.0 - Sr))


def z_direction(closes):
    n = len(closes)
    out = np.zeros(n, dtype=np.int8)
    
    for ci in range(max(2, N_BARS), n):
        lo = max(0, ci - N_BARS)
        w = closes[lo:ci]
        if len(w) < 2:
            continue
        mu = float(np.mean(w))
        sd = float(np.std(w))
        if sd <= 1e-12:
            continue
        z = (closes[ci] - mu) / sd
        if abs(z) < Z_THRESHOLD:
            continue
        out[ci] = -1 if z < 0 else 1
    return out


# ─── Asset container ─────────────────────────────────────────
@dataclass
class Asset:
    symbol: str
    closes: np.ndarray
    geo_accel: np.ndarray
    dH: np.ndarray
    dF: np.ndarray
    gauge: np.ndarray
    friction: np.ndarray
    z_dir: np.ndarray
    fwd_ret: Dict[int, np.ndarray]


def load_asset(path):
    try:
        if path.endswith('.parquet'):
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception as e:
        print(f"  [skip] {os.path.basename(path)}: read: {e}",
              file=sys.stderr)
        return None

    cols = {str(c).lower(): c for c in df.columns}
    for req in ('open', 'high', 'low', 'close', 'volume'):
        if req not in cols:
            print(f"  [skip] {os.path.basename(path)}: no '{req}'",
                  file=sys.stderr)
            return None

    closes = df[cols['close']].values.astype(np.float64)
    vols = df[cols['volume']].values.astype(np.float64)

    ok = np.isfinite(closes) & (closes > 0) & np.isfinite(vols)
    if not ok.all():
        closes = closes[ok]
        vols = vols[ok]

    n = len(closes)
    if n < MIN_BARS:
        print(f"  [skip] {os.path.basename(path)}: {n} < {MIN_BARS}",
              file=sys.stderr)
        return None

    X = compute_features(closes, vols)
    if len(X) < MIN_FEATURES:
        print(f"  [skip] {os.path.basename(path)}: {len(X)} feats",
              file=sys.stderr)
        return None

    # ── Symbolic quantization: median from FIRST 50% only ──
    norms = np.linalg.norm(X, axis=1)
    train_n = max(len(norms) // 2, 1)
    med = float(np.median(norms[:train_n]))
    sym_q = (norms > med).astype(np.int64)
    k = K_QUANT

    # ── Physics ──
    H = entropy_series(sym_q, k)
    dH = np.diff(H, prepend=H[0])
    gauge = gauge_force_series(sym_q, k)
    friction = friction_series(H, k)

    lr_full = np.diff(np.log(np.maximum(closes, 1e-12)))
    feat_start = N_BARS
    n_f = len(X)
    E_therm = np.zeros(n_f)
    for i in range(n_f):
        ci = feat_start + i
        if ci >= N_BARS:
            w = lr_full[ci - N_BARS:ci]
            E_therm[i] = float(np.std(w, ddof=1)) if len(w) >= 2 else 0.0

    F = E_therm - H
    dF = np.diff(F, prepend=F[0])
    geo_accel = -dF + LORENTZ_Q * gauge * dH - friction * dH

    def _pad(a):
        out = np.zeros(n)
        take = min(len(a), max(0, n - feat_start))
        out[feat_start:feat_start + take] = a[:take]
        return out

    zd = z_direction(closes)

    fwd = {}
    for h in (1, 2, 3, 5):
        r = np.full(n, np.nan)
        for i in range(n - h):
            if closes[i] > 0 and closes[i + h] > 0:
                r[i] = float(np.log(closes[i + h] / closes[i]))
        fwd[h] = r

    base = os.path.basename(path).rsplit('.', 1)[0]
    return Asset(
        symbol=base,
        closes=closes,
        geo_accel=_pad(geo_accel),
        dH=_pad(dH),
        dF=_pad(dF),
        gauge=_pad(gauge),
        friction=_pad(friction),
        z_dir=zd,
        fwd_ret=fwd,
    )


# ─── Evaluation ──────────────────────────────────────────────
@dataclass
class Result:
    name: str
    hits: int
    total: int
    rate: float
    se: float
    ci_lo: float
    ci_hi: float
    p_raw: float
    p_bonf: float
    ic: float
    ic_method: str        # ← حقل جديد: "pearson" | "zero_small_std_r" | "zero_small_std_s" | "zero_out_of_range" | "zero_exception"
    hits_h1: int
    total_h1: int
    hits_h2: int
    total_h2: int


def evaluate(name, sig, ret, n_tests):
    mask = ((sig != 0) &
            np.isfinite(ret) &
            (np.abs(ret) > 1e-9))
    n_total = int(mask.sum())
    if n_total < MIN_SAMPLES:
        return None

    s = sig[mask].astype(np.float64)
    r = ret[mask]

    hits = int((np.sign(s) == np.sign(r)).sum())
    rate = hits / n_total
    se = float(np.sqrt(rate * (1.0 - rate) / n_total))
    ci_lo = rate - 1.96 * se
    ci_hi = rate + 1.96 * se

    try:
        p_raw = float(binomtest(hits, n_total, 0.5,
                                alternative='greater').pvalue)
    except Exception:
        p_raw = 1.0
    p_bonf = min(1.0, p_raw * n_tests)

    # ══ [IC-FIX] حماية من انفجار Pearson ══
    sd_s = float(np.std(s))
    sd_r = float(np.std(r))

    if sd_r < 1e-4:
        # عوائد شبه-صفر → IC غير قابل للحساب، نُرجع 0 بأمانة
        ic = 0.0
        ic_method = "zero_small_std_r"
    elif sd_s < 1e-9:
        # إشارة ثابتة (لا تنوع) → لا ارتباط
        ic = 0.0
        ic_method = "zero_small_std_s"
    else:
        try:
            raw_ic = float(pearsonr(s, r)[0])
            # فحص السلامة: Pearson يجب أن يكون في [-1, +1]
            if not np.isfinite(raw_ic) or abs(raw_ic) > 1.001:
                ic = 0.0
                ic_method = "zero_out_of_range"
            else:
                ic = float(np.clip(raw_ic, -1.0, 1.0))
                ic_method = "pearson"
        except Exception:
            ic = 0.0
            ic_method = "zero_exception"

    half = n_total // 2
    hits_h1 = int((np.sign(s[:half]) == np.sign(r[:half])).sum())
    hits_h2 = int((np.sign(s[half:]) == np.sign(r[half:])).sum())

    return Result(
        name=name, hits=hits, total=n_total, rate=rate,
        se=se, ci_lo=ci_lo, ci_hi=ci_hi,
        p_raw=p_raw, p_bonf=p_bonf,
        ic=ic, ic_method=ic_method,
        hits_h1=hits_h1, total_h1=half,
        hits_h2=hits_h2, total_h2=n_total - half,
    )


# ─── Main ────────────────────────────────────────────────────
def run(cache_dir):
    print("=" * 90)
    print("  GEODESIC DIRECTION TEST")
    print("  Standalone | no look-ahead | Bonferroni | split-half")
    print("=" * 90)

    if not os.path.isdir(cache_dir):
        print(f"[ERROR] {cache_dir} not found", file=sys.stderr)
        return

    files = sorted(glob.glob(os.path.join(cache_dir, "*.parquet")))
    if not files:
        files = sorted(glob.glob(os.path.join(cache_dir, "*.csv")))
    files = [f for f in files if '_sub' not in os.path.basename(f)]

    if not files:
        print(f"[ERROR] no main data in {cache_dir}", file=sys.stderr)
        return

    print(f"\n  Candidates: {len(files)}")
    assets = []
    for f in files:
        a = load_asset(f)
        if a:
            assets.append(a)
            print(f"    ✓ {a.symbol:22s} n={len(a.closes):>7,d}")

    if not assets:
        print("[ERROR] none loaded", file=sys.stderr)
        return

    total_bars = sum(len(a.closes) for a in assets)
    print(f"\n  Loaded: {len(assets)} assets, {total_bars:,} bars")

    # ── Hypotheses ──
    def h1(ad):
        p = ad.geo_accel * ad.dH
        s = np.zeros(len(p))
        s[p > 0] = 1
        s[p < 0] = -1
        return s

    def h1b(ad):
        return -h1(ad)

    def h2(ad):
        return np.sign(ad.geo_accel)

    def h2b(ad):
        return -h2(ad)

    def h3(ad):
        return np.sign(-ad.dF)

    def h3b(ad):
        return np.sign(ad.dF)

    def h4(ad):
        return ad.z_dir.astype(np.float64)

    def h4b(ad):
        return np.ones(len(ad.closes))

    def h4c(ad):
        return -np.ones(len(ad.closes))

    def h4d(ad):
        # Deterministic seed so results are reproducible
        seed = sum(ord(c) for c in ad.symbol) % 0xFFFF
        rng = np.random.default_rng(seed)
        return rng.choice([-1.0, 1.0], size=len(ad.closes))

    hyps = [
        ("H1  sign(accel×dH)>0",   h1),
        ("H1b sign(accel×dH)<0",   h1b),
        ("H2  sign(accel)>0",      h2),
        ("H2b sign(accel)<0",      h2b),
        ("H3  sign(-dF)>0",        h3),
        ("H3b sign(dF)>0",         h3b),
        ("H4  z-score (bot)",      h4),
        ("H4b always BUY",         h4b),
        ("H4c always SELL",        h4c),
        ("H4d random",             h4d),
    ]
    n_tests = len(hyps) * 4

    for h in (1, 2, 3, 5):
        print("\n" + "─" * 90)
        print(f"  HORIZON = {h} bar(s) ahead")
        print("─" * 90)
        print(f"  {'Hypothesis':24s} {'n':>9s} {'hit%':>7s} "
              f"{'95% CI':>15s} {'p_raw':>8s} {'p_bonf':>8s} "
              f"{'IC':>9s} {'h1%':>6s} {'h2%':>6s} {'cons'}")
        print("  " + "─" * 88)

        for name, fn in hyps:
            sigs, rets = [], []
            for a in assets:
                sigs.append(fn(a))
                rets.append(a.fwd_ret[h])
            sig = np.concatenate(sigs)
            ret = np.concatenate(rets)

            r = evaluate(name, sig, ret, n_tests)
            if r is None:
                print(f"  {name:24s} (n < {MIN_SAMPLES})")
                continue

            h1r = r.hits_h1 / max(r.total_h1, 1) * 100
            h2r = r.hits_h2 / max(r.total_h2, 1) * 100
            cons = "YES" if (h1r > 52 and h2r > 52) else "no"

        # ══ [IC-METHOD-TAG] إضافة علامة صغيرة عند IC المحجوب ══
        _ic_str = f"{r.ic:>9.4f}"
        if r.ic_method != "pearson":
            # علامة تحذير صغيرة تشير إلى أن IC حُجب لأمانة إحصائية
            _ic_str = f"{r.ic:>8.4f}*"

        print(f"  {name:24s} {r.total:>9,d} "
              f"{r.rate*100:>6.2f}% "
              f"[{r.ci_lo*100:>5.1f},{r.ci_hi*100:>5.1f}] "
              f"{r.p_raw:>8.4f} {r.p_bonf:>8.4f} "
              f"{_ic_str} "
              f"{h1r:>5.1f}% {h2r:>5.1f}% {cons}")

    # ── Per-asset breakdown (h=1) ──
    print("\n" + "═" * 90)
    print("  PER-ASSET BREAKDOWN (horizon = 1 bar)")
    print("═" * 90)
    print(f"  {'Asset':22s} {'H1_hit':>8s} {'H1_n':>9s} "
          f"{'H4_hit':>8s} {'H4_n':>9s} {'agree':>7s}")
    print("  " + "─" * 88)

    agree_total, agree_n = 0, 0
    for a in assets:
        s1 = h1(a)
        s4 = h4(a)
        r1 = evaluate("h1", s1, a.fwd_ret[1], 1)
        r4 = evaluate("h4", s4, a.fwd_ret[1], 1)
        m = (s1 != 0) & (s4 != 0)
        if m.any():
            ag = int((np.sign(s1[m]) == np.sign(s4[m])).sum())
            n_ag = int(m.sum())
            agree_total += ag
            agree_n += n_ag
            ag_str = f"{100*ag/n_ag:>6.1f}%"
        else:
            ag_str = "    --"

        h1s = f"{r1.rate*100:>7.2f}%" if r1 else "     --"
        h1n = f"{r1.total:>8,d}" if r1 else "     --"
        h4s = f"{r4.rate*100:>7.2f}%" if r4 else "     --"
        h4n = f"{r4.total:>8,d}" if r4 else "     --"
        print(f"  {a.symbol:22s} {h1s} {h1n} {h4s} {h4n} {ag_str}")

    if agree_n > 0:
        print(f"\n  Overall H1↔H4 agreement: "
              f"{agree_total}/{agree_n} = "
              f"{100*agree_total/agree_n:.1f}%")

    print("\n" + "═" * 90)
    print("  HOW TO READ")
    print("═" * 90)
    print("""
  COLUMNS:
    IC       = Pearson(signal, return); |IC|>0.02 = weak edge
           IC marked with '*' means std(ret) < 1e-4 (unreliable)
           or std(sig) < 1e-9 (degenerate); value forced to 0.
    n        = (signal≠0, |return|>1e-9) bars
    hit%     = % of signs matching forward return
    95% CI   = Wald interval on hit%
    p_raw    = binomial, H0: hit_rate = 0.5
    p_bonf   = p_raw × 40  (Bonferroni, honest)
    IC       = Pearson(signal, return); |IC|>0.02 = weak edge
    h1%/h2%  = split-half hit rates
    cons     = "YES" iff both halves > 52%

  FLOOR TO BEAT:
    H4b (always BUY) and H4c (always SELL) reveal the base rate.
    Any hypothesis must EXCEED max(H4b, H4c) + 2pp to count as real.

  RULES FOR A USABLE EDGE:
    ✓ p_bonf  < 0.05
    ✓ hit%    > max(H4b, H4c) + 2pp
    ✓ IC      > +0.02
    ✓ cons    = "YES"

  PITFALLS NOT HIDDEN:
    • Serial correlation (h>1): adjacent bars share returns →
      p-values optimistic by ~√h. Don't over-trust p ≈ 0.01.
    • Non-stationarity: half-splits may differ greatly even with
      a real edge. "cons=YES" is a strict gate.
    • Bonferroni is conservative: very strong signals can still
      fail p_bonf. Use with common sense, but DO NOT relax it
      without a bigger n.

  TYPICAL OUTCOMES:
    H1 ≈ 50%, IC ≈ 0          → geodesic sign is noise
    H1 ≈ 55%, IC ≈ 0.03, cons → weak edge exists
    H1b >> H1                 → equation has signal, WRONG sign
    H1 wins only in half 1    → overfit
    H4 >> H1                  → keep z-score; geodesic is a feature,
                                 not a predictor
""")


if __name__ == "__main__":
    cache = sys.argv[1] if len(sys.argv) > 1 else "market_data_cache"
    run(cache)
