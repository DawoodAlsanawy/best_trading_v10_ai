#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  train_adaptive_regime.py  —  Stage 3A                                       ║
║                                                                              ║
║  المهمة:                                                                     ║
║    1. حساب 5 features GMM لتصنيف النظام (ADX, BB_width, ATR%, EMA_slope, ret_12) ║
║    2. تدريب GMM تلقائياً (n_components متكيف حسب التوازن)                     ║
║    3. تصنيف كل صفقة إلى نظام + confidence                                    ║
║    4. قياس استقرار ~28 ميزة (KS test عبر نوافذ زمنية متدحرجة)               ║
║    5. إنتاج: regimes.csv, stable_features.json, report.md                   ║
║                                                                              ║
║  المدخلات:                                                                   ║
║    - failure_analysis/trades_enriched.csv (من Stage 1)                       ║
║    - market_data_cache/{SYMBOL}_4h.parquet (لحساب ADX/BB)                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from collections import defaultdict
from scipy import stats
import warnings

warnings.filterwarnings('ignore')


# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

CFG = {
    'input_csv':       'failure_analysis/trades_enriched.csv',
    'cache_dir':       'market_data_cache',
    'out_dir':         'failure_analysis',
    'timeframe':       '4h',
    # GMM fitting
    'gmm_min_k':       3,
    'gmm_max_k':       6,
    'gmm_max_frac':    0.60,   # أي عنقود > 60% = غير مقبول
    'gmm_min_frac':    0.05,   # أي عنقود < 5% = غير مقبول
    'gmm_conf_ok':     0.60,   # عتبة "النظام محدد"
    # Stability analysis
    'stab_window':     500,    # حجم نافذة KS
    'stab_stride':     250,    # خطوة بين النوافذ
    'stab_min_samples': 100,   # أدنى عينات في النافذة
    'stab_mean_ks':    0.10,   # عتبة القبول: mean KS < 0.10
    'stab_max_ks':     0.15,   # عتبة القبول: max KS < 0.15
    'stab_unstable_ratio': 0.30,  # عتبة القبول: نسبة النوافذ غير المستقرة
    'stab_ks_single':  0.10,   # عتبة "نافذة غير مستقرة"
}

# الميزات المستبعدة من تحليل الاستقرار (دورية بطبيعتها)
UNSTABLE_BY_NATURE = {
    'hour_utc', 'dow', 'is_weekend', 'asia_session', 'us_session',
    'n_prior_sym', 'wr_prior_sym', 'bars_since_sym',
}

# الميزات المطلوبة للـ GMM (يجب أن تكون موجودة أو تُحسب)
GMM_FEATURES = ['adx', 'bb_width_abs', 'atr_pct', 'ema200_slope_pct', 'ret_12']


# ═══════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════

def log(msg, level='INFO'):
    prefix = {'INFO': 'ℹ', 'OK': '✓', 'WARN': '⚠', 'ERR': '✗', 'STEP': '→'}
    print(f"{prefix.get(level, '•')} {msg}")


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# Parquet loading
# ═══════════════════════════════════════════════════════════════════════

def load_parquets(cache_dir, tf, symbols):
    """Load all needed parquet files (no slicing — we need history for ADX/EMA)."""
    log(f"Loading {len(symbols)} parquets from {cache_dir} ...")
    data = {}
    for sym in symbols:
        fp = os.path.join(cache_dir, f"{sym.replace('/','_')}_{tf}.parquet")
        if not os.path.exists(fp):
            continue
        try:
            df = pd.read_parquet(fp)
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC')
            else:
                df.index = df.index.tz_convert('UTC')
            if len(df) >= 250:  # need 200+ for EMA200
                data[sym] = df
        except Exception as e:
            log(f"  {sym}: {e}", 'WARN')
    log(f"Loaded {len(data)}/{len(symbols)} parquets", 'OK')
    return data


def find_bar_index(pdf, ts, tol_s=3600.0):
    """Find bar index by timestamp with tolerance (default: 1 bar)."""
    if pdf is None or len(pdf) == 0:
        return -1
    if ts.tz is None:
        ts = ts.tz_localize('UTC')
    
    # Ensure DataFrame index and ts are same type
    idx = pdf.index.searchsorted(ts)
    if idx < len(pdf):
        diff = abs((pdf.index[idx] - ts).total_seconds())
        if diff < tol_s:
            return int(idx)
    if idx > 0:
        diff = abs((pdf.index[idx-1] - ts).total_seconds())
        if diff < tol_s:
            return int(idx - 1)
    return -1


# ═══════════════════════════════════════════════════════════════════════
# GMM feature computation (5 features per trade)
# ═══════════════════════════════════════════════════════════════════════

def compute_gmm_features(pdf, ci):
    """
    Compute 5 GMM features at bar ci using ONLY bars <= ci (no look-ahead).
    Returns dict or None if insufficient history.
    """
    if pdf is None or ci < 220:
        return None
    
    highs  = pdf['High'].values[:ci+1]
    lows   = pdf['Low'].values[:ci+1]
    closes = pdf['Close'].values[:ci+1]
    n = len(closes)
    
    # ── ADX(14) ──
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        h, l, pc = highs[i], lows[i], closes[i-1]
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        if up > down and up > 0:
            plus_dm[i] = up
        elif down > up and down > 0:
            minus_dm[i] = down
    
    _alpha = 1.0 / 14.0
    atr = pd.Series(tr).ewm(alpha=_alpha, adjust=False).mean().values
    plus_di  = 100.0 * pd.Series(plus_dm).ewm(alpha=_alpha, adjust=False).mean().values / np.maximum(atr, 1e-12)
    minus_di = 100.0 * pd.Series(minus_dm).ewm(alpha=_alpha, adjust=False).mean().values / np.maximum(atr, 1e-12)
    dx  = 100.0 * np.abs(plus_di - minus_di) / np.maximum(plus_di + minus_di, 1e-12)
    adx = pd.Series(dx).ewm(alpha=_alpha, adjust=False).mean().values
    
    adx_now = float(adx[-1])
    if not np.isfinite(adx_now):
        adx_now = 0.0
    
    # ── BB_width ──
    ma20 = pd.Series(closes).rolling(20).mean().values
    sd20 = pd.Series(closes).rolling(20).std().values
    if np.isfinite(ma20[-1]) and ma20[-1] > 0:
        bb_width = 4.0 * sd20[-1] / ma20[-1]
    else:
        bb_width = 0.0
    
    # ── ATR% ──
    atr_now = float(atr[-1])
    atr_pct = atr_now / max(closes[-1], 1e-12)
    
    # ── EMA200 slope (% over 24 bars) ──
    ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values
    if ci >= 24 and ema200[ci-24] > 0:
        ema200_slope_pct = (ema200[ci] - ema200[ci-24]) / ema200[ci-24]
    else:
        ema200_slope_pct = 0.0
    
    # ── ret_12 ──
    if ci >= 12 and closes[ci-12] > 0:
        ret_12 = (closes[ci] - closes[ci-12]) / closes[ci-12]
    else:
        ret_12 = 0.0
    
    return {
        'adx':              float(adx_now),
        'bb_width_abs':     float(bb_width),
        'atr_pct':          float(atr_pct),
        'ema200_slope_pct': float(ema200_slope_pct),
        'ret_12':           float(ret_12),
    }


# ═══════════════════════════════════════════════════════════════════════
# GMM fit with adaptive n_components
# ═══════════════════════════════════════════════════════════════════════

def evaluate_balance(labels, k):
    counts = np.bincount(labels, minlength=k)
    total = counts.sum()
    if total == 0:
        return {'entropy_ratio': 0.0, 'largest_frac': 1.0, 'smallest_frac': 0.0}
    p = counts / total
    entropy = -np.sum(p * np.log2(p + 1e-12))
    max_entropy = np.log2(k)
    return {
        'entropy_ratio': float(entropy / max_entropy) if max_entropy > 0 else 0.0,
        'largest_frac':  float(p.max()),
        'smallest_frac': float(p.min()),
    }


def fit_gmm_adaptive(X, min_k, max_k, max_frac, min_frac):
    """Try k values from max_k down to min_k, pick first with acceptable balance."""
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    chosen = None
    for k in range(max_k, min_k - 1, -1):
        try:
            gmm = GaussianMixture(
                n_components=k, covariance_type='full',
                random_state=42, n_init=3, max_iter=100,
            )
            gmm.fit(X_scaled)
            labels = gmm.predict(X_scaled)
            bal = evaluate_balance(labels, k)
            
            if bal['largest_frac'] <= max_frac and bal['smallest_frac'] >= min_frac:
                log(f"  GMM k={k}: entropy={bal['entropy_ratio']:.2f}, "
                    f"largest={bal['largest_frac']*100:.1f}%, "
                    f"smallest={bal['smallest_frac']*100:.1f}% ✓", 'OK')
                chosen = {'gmm': gmm, 'scaler': scaler, 'k': k, 'balance': bal}
                break
            else:
                log(f"  GMM k={k}: REJECTED — largest={bal['largest_frac']*100:.1f}% "
                    f"(> {max_frac*100:.0f}%) or smallest={bal['smallest_frac']*100:.1f}% "
                    f"(< {min_frac*100:.0f}%)", 'WARN')
        except Exception as e:
            log(f"  GMM k={k}: failed ({e})", 'WARN')
            continue
    
    if chosen is None:
        # Fallback: force k=4
        log("  All k values failed balance test — falling back to k=4", 'WARN')
        gmm = GaussianMixture(n_components=4, covariance_type='full',
                              random_state=42, n_init=3)
        gmm.fit(X_scaled)
        labels = gmm.predict(X_scaled)
        chosen = {
            'gmm': gmm, 'scaler': scaler, 'k': 4,
            'balance': evaluate_balance(labels, 4),
        }
    
    return chosen


# ═══════════════════════════════════════════════════════════════════════
# Stability analysis (KS across rolling windows)
# ═══════════════════════════════════════════════════════════════════════

def compute_stability(series, window, stride, min_samples, ks_single):
    """
    Return stability metrics: mean_ks, max_ks, unstable_ratio.
    series: 1D array of feature values (sorted by time).
    """
    arr = np.asarray(series, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < window + stride:
        return {'mean_ks': 0.0, 'max_ks': 0.0, 'unstable_ratio': 0.0, 'n_windows': 0}
    
    ks_values = []
    start = 0
    while start + window + stride <= n:
        w1 = arr[start:start+window]
        w2 = arr[start+stride:start+stride+window]
        if len(w1) >= min_samples and len(w2) >= min_samples:
            try:
                ks_stat, _ = stats.ks_2samp(w1, w2)
                ks_values.append(float(ks_stat))
            except Exception:
                pass
        start += stride
    
    if not ks_values:
        return {'mean_ks': 0.0, 'max_ks': 0.0, 'unstable_ratio': 0.0, 'n_windows': 0}
    
    arr_ks = np.array(ks_values)
    return {
        'mean_ks':          float(arr_ks.mean()),
        'max_ks':           float(arr_ks.max()),
        'unstable_ratio':   float((arr_ks > ks_single).mean()),
        'n_windows':        len(ks_values),
    }


def analyze_all_features(df, exclude_cols):
    """Compute stability for all numeric features except excluded."""
    log("Analyzing feature stability across rolling windows ...")
    results = []
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    for col in numeric_cols:
        if col in exclude_cols or col in UNSTABLE_BY_NATURE:
            continue
        # Skip obvious metadata
        if col.startswith('_') or col in ('entry_ci', 'exit_ci', 'hold_bars',
                                          'feat_idx', 'close_idx', 'computed_bar_idx'):
            continue
        
        st = compute_stability(
            df[col].values,
            window=CFG['stab_window'],
            stride=CFG['stab_stride'],
            min_samples=CFG['stab_min_samples'],
            ks_single=CFG['stab_ks_single'],
        )
        
        # Verdict
        rejected_reasons = []
        if st['mean_ks'] > CFG['stab_mean_ks']:
            rejected_reasons.append(f"mean_ks={st['mean_ks']:.3f}>{CFG['stab_mean_ks']}")
        if st['max_ks'] > CFG['stab_max_ks']:
            rejected_reasons.append(f"max_ks={st['max_ks']:.3f}>{CFG['stab_max_ks']}")
        if st['unstable_ratio'] > CFG['stab_unstable_ratio']:
            rejected_reasons.append(f"unstable_ratio={st['unstable_ratio']:.2f}>{CFG['stab_unstable_ratio']}")
        
        results.append({
            'feature':        col,
            'mean_ks':        st['mean_ks'],
            'max_ks':         st['max_ks'],
            'unstable_ratio': st['unstable_ratio'],
            'n_windows':      st['n_windows'],
            'stable':         len(rejected_reasons) == 0,
            'reasons':        "; ".join(rejected_reasons) if rejected_reasons else "OK",
        })
    
    return pd.DataFrame(results).sort_values('max_ks', ascending=False).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════

def write_report(path, gmm_info, regime_table, stab_df, gmm_df, n_total, n_gmm):
    lines = []
    add = lines.append
    
    add("# Stage 3A — Regime Detector + Stability Filter\n")
    add(f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
    
    # ── Summary
    add("## 🎯 Executive Summary\n")
    add(f"- **Total trades analyzed**: {n_total:,}")
    add(f"- **Trades with valid GMM features**: {n_gmm:,} "
        f"({n_gmm/max(n_total,1)*100:.1f}%)")
    add(f"- **GMM k selected**: {gmm_info['k']}")
    add(f"- **Regime balance**: largest={gmm_info['balance']['largest_frac']*100:.1f}%, "
        f"smallest={gmm_info['balance']['smallest_frac']*100:.1f}%, "
        f"entropy_ratio={gmm_info['balance']['entropy_ratio']:.2f}")
    n_stable = int(stab_df['stable'].sum())
    n_rejected = int((~stab_df['stable']).sum())
    add(f"- **Features stable**: {n_stable} accepted, {n_rejected} rejected")
    add("")
    
    # ── Regime distribution
    add("## 🌊 Regime Distribution × Category\n")
    if regime_table is not None and len(regime_table) > 0:
        add("| Regime | n | % total | P(A) | P(B) | P(D) | Mean confidence |")
        add("|--------|---|---------|------|------|------|-----------------|")
        for _, r in regime_table.iterrows():
            add(f"| {r['regime_id']} | {int(r['n'])} | "
                f"{r['n_pct']*100:.1f}% | "
                f"{r['p_A']*100:.1f}% | "
                f"{r['p_B']*100:.1f}% | "
                f"{r['p_D']*100:.1f}% | "
                f"{r['mean_conf']:.3f} |")
        add("")
        
        # Identify best/worst regimes
        if 'p_A' in regime_table.columns and len(regime_table) > 1:
            best = regime_table.sort_values('p_A').iloc[0]
            worst = regime_table.sort_values('p_A', ascending=False).iloc[0]
            add(f"**🎯 Best regime (lowest P(A))**: `{best['regime_id']}` "
                f"(P(A)={best['p_A']*100:.1f}%, n={int(best['n'])})")
            add(f"**🚨 Worst regime (highest P(A))**: `{worst['regime_id']}` "
                f"(P(A)={worst['p_A']*100:.1f}%, n={int(worst['n'])})")
            add("")
            
            spread = (worst['p_A'] - best['p_A']) * 100
            add(f"**Separation (P(A)_worst - P(A)_best)**: {spread:.1f} pp")
            if spread > 20:
                add("✅ **Regime detection has meaningful signal** — different regimes have very different failure rates.")
            elif spread > 10:
                add("⚠️ **Regime detection has moderate signal** — some separation exists.")
            else:
                add("❌ **Regime detection has weak signal** — regimes aren't differentiating failures well.")
            add("")
    
    # ── Stability results
    add("## 🔬 Feature Stability Results\n")
    add(f"**Thresholds**: mean_ks<{CFG['stab_mean_ks']}, "
        f"max_ks<{CFG['stab_max_ks']}, "
        f"unstable_ratio<{CFG['stab_unstable_ratio']}\n")
    
    add("### ✅ Accepted (stable) features\n")
    stable_df = stab_df[stab_df['stable']].sort_values('max_ks')
    if len(stable_df) > 0:
        add("| Feature | mean_ks | max_ks | unstable_ratio | n_windows |")
        add("|---------|---------|--------|----------------|-----------|")
        for _, r in stable_df.iterrows():
            add(f"| `{r['feature']}` | {r['mean_ks']:.3f} | "
                f"{r['max_ks']:.3f} | {r['unstable_ratio']:.2f} | {r['n_windows']} |")
    else:
        add("_No features passed the stability test._")
    add("")
    
    add("### ❌ Rejected (unstable) features\n")
    rejected_df = stab_df[~stab_df['stable']].sort_values('max_ks', ascending=False)
    if len(rejected_df) > 0:
        add("| Feature | max_ks | Reasons |")
        add("|---------|--------|---------|")
        for _, r in rejected_df.iterrows():
            add(f"| `{r['feature']}` | {r['max_ks']:.3f} | {r['reasons']} |")
    else:
        add("_All features were stable._")
    add("")
    
    # ── Recommendation
    add("## 🎯 Recommendations for Stage 3B\n")
    
    if spread > 15 and n_stable >= 5:
        add("✅ **System ready for Stage 3B.** Regime detection shows good signal, "
            "and sufficient features passed stability.")
        add("")
        add(f"**Next steps:**")
        add(f"1. Use **{n_stable} stable features** for per-regime ML models")
        add(f"2. Train LightGBM per regime on rolling windows")
        add(f"3. Implement Confidence Gate + Kill Switches")
    elif n_stable < 5:
        add("⚠️ **Too few stable features** — the model may overfit. "
            "Consider:")
        add("- Relaxing thresholds (mean_ks<0.12, max_ks<0.20)")
        add("- Adding engineered features (ratios, derivatives)")
        add("- Using only `score`, `E_therm`, `T_info`, `sl_sigma` (known stable)")
    else:
        add("⚠️ **Regime detection signal is weak.** Before proceeding:")
        add("- Try different n_components or GMM covariance type")
        add("- Add more discriminating features")
        add("- Consider hierarchical clustering instead of GMM")
    
    add("")
    add("## 📁 Files produced\n")
    add("- `regimes.csv`: per-trade regime + confidence + GMM features")
    add("- `stable_features.json`: list of stable features for Stage 3B")
    add("- `stability_analysis.csv`: full feature-by-feature stability table")
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    log(f"Report: {path}", 'OK')


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default=CFG['input_csv'])
    p.add_argument('--cache', default=CFG['cache_dir'])
    p.add_argument('--out',   default=CFG['out_dir'])
    p.add_argument('--timeframe', default=CFG['timeframe'])
    p.add_argument('--stab-window', type=int, default=CFG['stab_window'])
    p.add_argument('--stab-mean-ks', type=float, default=CFG['stab_mean_ks'])
    p.add_argument('--stab-max-ks', type=float, default=CFG['stab_max_ks'])
    args = p.parse_args()
    
    CFG['input_csv']    = args.input
    CFG['cache_dir']    = args.cache
    CFG['out_dir']      = args.out
    CFG['timeframe']    = args.timeframe
    CFG['stab_window']  = args.stab_window
    CFG['stab_mean_ks'] = args.stab_mean_ks
    CFG['stab_max_ks']  = args.stab_max_ks
    
    ensure_dir(CFG['out_dir'])
    
    print("═" * 72)
    print("  🔬 Stage 3A — Regime Detector + Stability Filter")
    print("═" * 72)
    
    # ── 1. Load trades
    if not os.path.exists(CFG['input_csv']):
        log(f"Not found: {CFG['input_csv']}", 'ERR')
        sys.exit(1)
    
    df = pd.read_csv(CFG['input_csv'], parse_dates=['entry_dt'])
    df = df.sort_values('entry_dt').reset_index(drop=True)
    log(f"Loaded {len(df)} trades", 'OK')
    
    # ── 2. Load parquets
    symbols = df['symbol'].unique().tolist()
    parquets = load_parquets(CFG['cache_dir'], CFG['timeframe'], symbols)
    
    if not parquets:
        log("No parquets loaded — aborting", 'ERR')
        sys.exit(1)
    
    # ── 3. Compute GMM features per trade
    log("Computing GMM features (ADX, BB, ATR%, EMA200_slope, ret_12) ...")
    gmm_rows = []
    n_skipped_no_parquet = 0
    n_skipped_no_bar = 0
    n_skipped_insufficient = 0
    
    for _, row in df.iterrows():
        sym = row['symbol']
        ts = row['entry_dt']
        
        if sym not in parquets:
            n_skipped_no_parquet += 1
            gmm_rows.append({'trade_idx': row.name, **{f: np.nan for f in GMM_FEATURES}})
            continue
        
        pdf = parquets[sym]
        ci = find_bar_index(pdf, ts)
        if ci < 0:
            n_skipped_no_bar += 1
            gmm_rows.append({'trade_idx': row.name, **{f: np.nan for f in GMM_FEATURES}})
            continue
        
        feats = compute_gmm_features(pdf, ci)
        if feats is None:
            n_skipped_insufficient += 1
            gmm_rows.append({'trade_idx': row.name, **{f: np.nan for f in GMM_FEATURES}})
            continue
        
        gmm_rows.append({'trade_idx': row.name, **feats})
    
    gmm_df = pd.DataFrame(gmm_rows).set_index('trade_idx')
    n_gmm_valid = gmm_df[GMM_FEATURES].dropna().shape[0]
    log(f"GMM features: {n_gmm_valid} valid "
        f"(skipped: no_parquet={n_skipped_no_parquet}, "
        f"no_bar={n_skipped_no_bar}, insufficient={n_skipped_insufficient})", 'OK')
    
    if n_gmm_valid < 200:
        log(f"Too few valid trades ({n_gmm_valid}) for GMM — aborting", 'ERR')
        sys.exit(1)
    
    # ── 4. Fit GMM
    log("Fitting GMM (adaptive n_components) ...", 'STEP')
    valid_mask = gmm_df[GMM_FEATURES].notna().all(axis=1)
    X_gmm = gmm_df.loc[valid_mask, GMM_FEATURES].values
    
    gmm_info = fit_gmm_adaptive(
        X_gmm,
        min_k=CFG['gmm_min_k'],
        max_k=CFG['gmm_max_k'],
        max_frac=CFG['gmm_max_frac'],
        min_frac=CFG['gmm_min_frac'],
    )
    
    gmm = gmm_info['gmm']
    scaler = gmm_info['scaler']
    k = gmm_info['k']
    
    # ── 5. Assign regimes
    X_scaled = scaler.transform(X_gmm)
    labels = gmm.predict(X_scaled)
    probs = gmm.predict_proba(X_scaled)
    confs = probs.max(axis=1)
    
    # Save per-trade regime
    regime_df = pd.DataFrame({
        'regime_id': labels,
        'regime_confidence': confs,
    }, index=gmm_df.index[valid_mask])
    
    gmm_df['regime_id'] = np.nan
    gmm_df['regime_confidence'] = np.nan
    gmm_df.loc[valid_mask, 'regime_id'] = labels
    gmm_df.loc[valid_mask, 'regime_confidence'] = confs
    
    # Merge back to main df (renaming any overlapping GMM columns with _gmm suffix)
    df_out = df.join(
        gmm_df[['regime_id', 'regime_confidence'] + GMM_FEATURES],
        how='left',
        rsuffix='_gmm',
    )
    
    # Log which columns were renamed (if any)
    renamed = [f'{f}_gmm' for f in GMM_FEATURES if f'{f}_gmm' in df_out.columns]
    if renamed:
        log(f"  Overlapping GMM features renamed: {renamed}", 'WARN')

    df_out['regime_id'] = df_out['regime_id'].fillna(-1).astype(int)
    df_out.loc[df_out['regime_id'] == -1, 'regime_confidence'] = 0.0
    
    # ── 6. Regime × category cross-tab
    log("Analyzing regime × category ...", 'STEP')
    ct = pd.crosstab(df_out['regime_id'], df_out['category'])
    ct = ct.reindex(columns=['A', 'B', 'D'], fill_value=0)
    
    regime_rows = []
    for rid in sorted(df_out['regime_id'].unique()):
        if rid == -1:
            continue
        sub = df_out[df_out['regime_id'] == rid]
        n = len(sub)
        n_A = int((sub['category'] == 'A').sum())
        n_B = int((sub['category'] == 'B').sum())
        n_D = int((sub['category'] == 'D').sum())
        regime_rows.append({
            'regime_id':   int(rid),
            'n':           n,
            'n_pct':       n / max(len(df_out), 1),
            'p_A':         n_A / max(n, 1),
            'p_B':         n_B / max(n, 1),
            'p_D':         n_D / max(n, 1),
            'mean_conf':   float(sub['regime_confidence'].mean()),
        })
    regime_table = pd.DataFrame(regime_rows)
    
    # ── 7. Stability analysis
    log("Analyzing feature stability ...", 'STEP')
    
    exclude_cols = {
        'category', 'entry_price', 'exit_price', 'pos_size',
        'net_pnl', 'log_return', 'cap_delta_since_entry',
        'partial_pnl', 'capital_before', 'capital_after', 'is_win',
        'mfe_frac', 'sl_dist_initial',
        'regime_id', 'regime_confidence',
        # GMM input features (from join) — excluded from stability analysis
        'adx', 'bb_width_abs', 'atr_pct', 'ema200_slope_pct', 'ret_12_gmm',
        'signal_price', 'signal_sl', 'signal_tp1',
    }
    
    stab_df = analyze_all_features(df_out, exclude_cols)
    n_stable = int(stab_df['stable'].sum())
    log(f"Stability: {n_stable} stable, {len(stab_df) - n_stable} rejected", 'OK')
    
    # ── 8. Save outputs
    df_out.to_csv(os.path.join(CFG['out_dir'], 'regimes.csv'), index=False)
    stab_df.to_csv(os.path.join(CFG['out_dir'], 'stability_analysis.csv'), index=False)
    regime_table.to_csv(os.path.join(CFG['out_dir'], 'regime_distribution.csv'), index=False)
    
    # Stable features JSON
    stable_features = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'thresholds': {
            'mean_ks':  CFG['stab_mean_ks'],
            'max_ks':   CFG['stab_max_ks'],
            'unstable_ratio': CFG['stab_unstable_ratio'],
        },
        'gmm': {
            'k': gmm_info['k'],
            'features': GMM_FEATURES,
            'balance': gmm_info['balance'],
        },
        'stable':   stab_df[stab_df['stable']]['feature'].tolist(),
        'rejected': [
            {'feature': r['feature'], 'reasons': r['reasons']}
            for _, r in stab_df[~stab_df['stable']].iterrows()
        ],
    }
    with open(os.path.join(CFG['out_dir'], 'stable_features.json'), 'w') as f:
        json.dump(stable_features, f, indent=2)
    
    # ── 9. Report
    write_report(
        os.path.join(CFG['out_dir'], 'regime_report.md'),
        gmm_info, regime_table, stab_df, gmm_df, len(df), n_gmm_valid,
    )
    
    # ── 10. Console summary
    print()
    print("═" * 72)
    print("  ✅ Stage 3A complete")
    print("═" * 72)
    print(f"  GMM: k={gmm_info['k']}, "
          f"balance: largest={gmm_info['balance']['largest_frac']*100:.1f}%, "
          f"smallest={gmm_info['balance']['smallest_frac']*100:.1f}%")
    print(f"  Regimes: {len(regime_table)}")
    if len(regime_table) > 1:
        best = regime_table.sort_values('p_A').iloc[0]
        worst = regime_table.sort_values('p_A', ascending=False).iloc[0]
        print(f"  Best:  regime {int(best['regime_id'])} — P(A)={best['p_A']*100:.1f}% (n={int(best['n'])})")
        print(f"  Worst: regime {int(worst['regime_id'])} — P(A)={worst['p_A']*100:.1f}% (n={int(worst['n'])})")
        print(f"  Separation: {(worst['p_A'] - best['p_A'])*100:.1f} pp")
    print(f"  Features stable: {n_stable}/{len(stab_df)}")
    print()
    print(f"  Output: {CFG['out_dir']}/")
    print(f"    - regime_report.md")
    print(f"    - regimes.csv")
    print(f"    - stable_features.json")
    print(f"    - stability_analysis.csv")
    print(f"    - regime_distribution.csv")


if __name__ == '__main__':
    main()
