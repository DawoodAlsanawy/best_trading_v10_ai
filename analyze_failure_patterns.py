#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  analyze_failure_patterns.py  —  Stage 1: Failure Pattern Discovery          ║
║                                                                              ║
║  يقرأ:  trades_log_backtest.jsonl  +  market_data_cache/*.parquet            ║
║  يصنّف: A (Direct Fail) / B (Partial+SL) / D (Winner) / O (Other)            ║
║  يحلّل: Regime، 40+ feature، SHAP importances، Simple Rules، Walk-forward    ║
║  يُخرج: failure_analysis/report.md + CSVs + PNGs                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import glob
import argparse
import warnings
from datetime import datetime, timezone
from collections import defaultdict

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

CFG = {
    'log_path':      'trades_log_backtest.jsonl',
    'cache_dir':     'market_data_cache',
    'out_dir':       'failure_analysis',
    'timeframe':     '4h',
    'history_days':  730,
    'swing_lookback': 60,
    'volume_window':  20,
    'extreme_lookback': 100,
    'bb_window':      20,
    'atr_window':     14,
    'ret_windows':    [3, 6, 12, 24],
    'wick_window':    10,
    'gap_window':     5,
    'train_frac':     0.70,
    'min_rule_n':     30,
    'min_p_A':        0.60,
    'max_p_D':        0.10,
}

# ═══════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════

def _log(msg, level='INFO'):
    prefix = {'INFO': 'ℹ', 'OK': '✓', 'WARN': '⚠', 'ERR': '✗', 'STEP': '→'}
    print(f"{prefix.get(level, '•')} {msg}")


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _fmt_pct(x, decimals=2):
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x*100:.{decimals}f}%"


def _fmt_num(x, decimals=4):
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x:.{decimals}f}"


# ═══════════════════════════════════════════════════════════════════════
# Load trades
# ═══════════════════════════════════════════════════════════════════════

def load_trades(log_path):
    """Load ONLY the trades from the last run (after last _meta line)."""
    if not os.path.exists(log_path):
        raise FileNotFoundError(f"Not found: {log_path}")
    
    with open(log_path, 'r', encoding='utf-8') as f:
        records = [json.loads(l) for l in f if l.strip()]
    
    last_meta_idx = -1
    meta = None
    for i, r in enumerate(records):
        if r.get('_meta'):
            last_meta_idx = i
            meta = r
    
    trades = records[last_meta_idx + 1:]
    if not trades:
        raise RuntimeError("No trades after last _meta")
    
    df = pd.DataFrame(trades)
    df['entry_dt'] = pd.to_datetime(df['entry_time'], utc=True, errors='coerce')
    df = df[df['entry_dt'].notna()].copy()
    df = df.sort_values('entry_dt').reset_index(drop=True)
    
    _log(f"Loaded {len(df)} trades from last run", 'OK')
    if meta:
        _log(f"Run metadata: TF={meta.get('timeframe')}, "
             f"initial_capital=${meta.get('INITIAL_CAPITAL')}, "
             f"started_at={meta.get('started_at')}")
    
    return df, meta


# ═══════════════════════════════════════════════════════════════════════
# Classification
# ═══════════════════════════════════════════════════════════════════════

def classify_trades(df):
    """
    A = Emergency SL, partial_pnl == 0   (Direct Fail)
    B = Emergency SL, partial_pnl >  0   (Partial Taken, then SL)
    D = Hard TP                          (Winner)
    O = Other exits                      (EndOfData)
    """
    df = df.copy()
    df['partial_pnl'] = pd.to_numeric(df.get('partial_pnl', 0),
                                       errors='coerce').fillna(0.0)
    df['net_pnl']     = pd.to_numeric(df['net_pnl'], errors='coerce').fillna(0.0)
    df['log_return']  = pd.to_numeric(df.get('log_return', 0),
                                       errors='coerce').fillna(0.0)
    df['exit_reason'] = df['exit_reason'].astype(str)
    
    def _cls(row):
        rsn = row['exit_reason']
        if 'Hard TP' in rsn:
            return 'D'
        if 'Emergency SL' in rsn:
            return 'B' if row['partial_pnl'] > 1e-6 else 'A'
        return 'O'
    
    df['category'] = df.apply(_cls, axis=1)
    
    counts = df['category'].value_counts()
    _log(f"Classification: "
         f"A={counts.get('A', 0):,}  "
         f"B={counts.get('B', 0):,}  "
         f"D={counts.get('D', 0):,}  "
         f"O={counts.get('O', 0):,}", 'OK')
    
    return df


# ═══════════════════════════════════════════════════════════════════════
# Market data loading
# ═══════════════════════════════════════════════════════════════════════

def load_parquet(cache_dir, tf, symbols, history_days):
    """Load sliced parquet for given symbols (matching backtest window)."""
    _log(f"Loading {len(symbols)} parquet files from {cache_dir} ...")
    data = {}
    _end_dt   = datetime.now(timezone.utc)
    _start_dt = _end_dt - pd.Timedelta(days=history_days)
    
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
            df = df[(df.index >= _start_dt) & (df.index <= _end_dt)]
            if len(df) > 0:
                data[sym] = df
        except Exception as e:
            _log(f"  {sym}: {e}", 'WARN')
    
    _log(f"Loaded {len(data)}/{len(symbols)} parquet files", 'OK')
    return data


def find_bar_index(parquet_df, entry_ts, tol_s=1.0):
    """Find bar index by timestamp (searchsorted + tolerance)."""
    if parquet_df is None or len(parquet_df) == 0:
        return -1
    if entry_ts.tz is None:
        entry_ts = entry_ts.tz_localize('UTC')
    
    idx = parquet_df.index.searchsorted(entry_ts)
    if idx < len(parquet_df):
        diff = abs((parquet_df.index[idx] - entry_ts).total_seconds())
        if diff < tol_s:
            return int(idx)
    if idx > 0:
        diff = abs((parquet_df.index[idx-1] - entry_ts).total_seconds())
        if diff < tol_s:
            return int(idx - 1)
    return -1


# ═══════════════════════════════════════════════════════════════════════
# Feature computation — Tier 2 (pre-entry path)
# ═══════════════════════════════════════════════════════════════════════

def compute_tier2_features(pdf, ci):
    """Pre-entry path features from market data. All safe (bars <= ci)."""
    n = len(pdf)
    if ci < 1 or ci >= n:
        return {}
    
    closes  = pdf['Close'].values
    highs   = pdf['High'].values
    lows    = pdf['Low'].values
    opens   = pdf['Open'].values
    volumes = pdf['Volume'].values
    
    f = {}
    
    # Returns over windows
    for w in CFG['ret_windows']:
        if ci >= w:
            base = closes[ci - w]
            f[f'ret_{w}'] = float((closes[ci] - base) / max(abs(base), 1e-12))
        else:
            f[f'ret_{w}'] = 0.0
    
    # Acceleration (short vs medium velocity)
    if ci >= 6:
        v3 = (closes[ci] - closes[ci-3]) / max(abs(closes[ci-3]), 1e-12)
        v6 = (closes[ci] - closes[ci-6]) / max(abs(closes[ci-6]), 1e-12)
        f['accel_3_6'] = float(v3 - v6)
    else:
        f['accel_3_6'] = 0.0
    
    # Wick profile (last N bars)
    w0 = max(0, ci - CFG['wick_window'] + 1)
    wu = wl = br = 0.0
    cnt = 0
    for i in range(w0, ci + 1):
        rng = highs[i] - lows[i]
        if rng <= 1e-12:
            continue
        o, c = opens[i], closes[i]
        wu += (highs[i] - max(o, c)) / rng
        wl += (min(o, c) - lows[i]) / rng
        br += abs(c - o) / rng
        cnt += 1
    if cnt > 0:
        f['wick_upper_avg'] = float(wu / cnt)
        f['wick_lower_avg'] = float(wl / cnt)
        f['body_ratio_avg'] = float(br / cnt)
    else:
        f['wick_upper_avg'] = 0.0
        f['wick_lower_avg'] = 0.0
        f['body_ratio_avg'] = 0.0
    
    # Volume ratio (recent vs baseline)
    vw = CFG['volume_window']
    if ci >= vw:
        v_recent = float(volumes[ci-2:ci+1].mean())
        v_base   = float(volumes[ci-vw:ci+1].mean()) + 1e-12
        f['vol_ratio_3_20'] = v_recent / v_base
    else:
        f['vol_ratio_3_20'] = 1.0
    
    # Volume acceleration
    if ci >= 6:
        v3 = float(volumes[ci-2:ci+1].mean())
        vp = float(volumes[ci-5:ci-2].mean()) + 1e-12
        f['vol_accel'] = (v3 - vp) / vp
    else:
        f['vol_accel'] = 0.0
    
    # Distance from extremes
    eb = CFG['extreme_lookback']
    if ci >= eb:
        h100 = float(highs[ci-eb+1:ci+1].max())
        l100 = float(lows[ci-eb+1:ci+1].min())
        f['dist_high_100'] = (closes[ci] - h100) / max(h100, 1e-12)
        f['dist_low_100']  = (closes[ci] - l100) / max(l100, 1e-12)
    else:
        f['dist_high_100'] = 0.0
        f['dist_low_100']  = 0.0
    
    # BB width percentile (compression)
    bbn = CFG['bb_window']
    if ci >= bbn + 50:
        cl_win = closes[ci-bbn+1:ci+1]
        ma_now = float(cl_win.mean())
        sd_now = float(cl_win.std())
        bb_now = 2 * sd_now / max(ma_now, 1e-12)
        hist = []
        for j in range(ci - 100, ci - bbn):
            if j < 0:
                continue
            w = closes[j:j+bbn]
            if len(w) < bbn:
                continue
            m = float(w.mean())
            s = float(w.std())
            hist.append(2 * s / max(m, 1e-12))
        if hist:
            f['bb_width_pct'] = float(sum(1 for h in hist if h < bb_now) / len(hist))
        else:
            f['bb_width_pct'] = 0.5
    else:
        f['bb_width_pct'] = 0.5
    
    # Gap count in last 5 bars
    gn = CFG['gap_window']
    if ci >= gn:
        gaps = 0
        for i in range(ci-gn+1, ci+1):
            if i < 1:
                continue
            gf = abs(opens[i] - closes[i-1]) / max(abs(closes[i-1]), 1e-12)
            if gf > 0.003:
                gaps += 1
        f['gap_count_5'] = float(gaps)
    else:
        f['gap_count_5'] = 0.0
    
    # ATR percentile (recent vol vs history)
    atr_n = CFG['atr_window']
    if ci >= 100:
        s0 = ci - 100
        seg = pd.DataFrame({
            'high':  highs[s0:ci+1],
            'low':   lows[s0:ci+1],
            'close': closes[s0:ci+1],
        })
        tr = pd.concat([
            seg['high'] - seg['low'],
            (seg['high'] - seg['close'].shift(1)).abs(),
            (seg['low']  - seg['close'].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_series = tr.rolling(atr_n, min_periods=1).mean().dropna().values
        if len(atr_series) >= 5:
            atr_now = float(atr_series[-1])
            pct = float((atr_series < atr_now).mean())
            f['atr_pctile'] = pct
        else:
            f['atr_pctile'] = 0.5
    else:
        f['atr_pctile'] = 0.5
    
    return f


# ═══════════════════════════════════════════════════════════════════════
# Feature computation — Tier 3 (BTC context)
# ═══════════════════════════════════════════════════════════════════════

def compute_tier3_features(btc_pdf, ts):
    """BTC context features. All safe (bars <= ts)."""
    if btc_pdf is None or len(btc_pdf) < 30:
        return {}
    
    ci = find_bar_index(btc_pdf, ts)
    if ci < 0:
        return {}
    
    f = {}
    closes = btc_pdf['Close'].values
    
    for w in [6, 24]:
        if ci >= w:
            f[f'btc_ret_{w}'] = float(
                (closes[ci] - closes[ci-w]) / max(abs(closes[ci-w]), 1e-12)
            )
        else:
            f[f'btc_ret_{w}'] = 0.0
    
    # BTC 24-bar EMA slope sign
    if ci >= 24:
        ma_now = float(closes[ci-23:ci+1].mean())
        ma_prev = float(closes[ci-47:ci-23].mean()) if ci >= 47 else ma_now
        f['btc_ema_slope'] = (ma_now - ma_prev) / max(abs(ma_prev), 1e-12)
    else:
        f['btc_ema_slope'] = 0.0
    
    return f


# ═══════════════════════════════════════════════════════════════════════
# Feature computation — Tier 4 (temporal)
# ═══════════════════════════════════════════════════════════════════════

def compute_tier4_features(ts):
    return {
        'hour_utc':      int(ts.hour),
        'dow':           int(ts.dayofweek),
        'is_weekend':    float(ts.dayofweek >= 5),
        'asia_session':  float(0 <= ts.hour < 8),
        'us_session':    float(14 <= ts.hour < 22),
    }


# ═══════════════════════════════════════════════════════════════════════
# Regime classification
# ═══════════════════════════════════════════════════════════════════════

def classify_regime(df, lookback=100):
    """Classify each trade's market regime using pre-entry price action."""
    regimes = []
    
    for _, row in df.iterrows():
        vol_ratio = row.get('vol_ratio_3_20', 1.0)
        atr_pct   = row.get('atr_pctile', 0.5)
        ret_24    = row.get('ret_24', 0.0)
        accel     = row.get('accel_3_6', 0.0)
        
        if vol_ratio > 2.0 and atr_pct > 0.75:
            r = 'Volatile_Spike'
        elif vol_ratio < 0.6 and atr_pct < 0.30:
            r = 'Squeeze'
        elif abs(ret_24) > 0.03 or abs(accel) > 0.01:
            r = 'Trending_Strong'
        elif abs(ret_24) > 0.015:
            r = 'Trending_Weak'
        else:
            r = 'Ranging'
        
        regimes.append(r)
    
    return regimes


# ═══════════════════════════════════════════════════════════════════════
# Tier 5 — Walk-forward trade history per symbol
# ═══════════════════════════════════════════════════════════════════════

def compute_tier5_features(df):
    """For each trade: stats of PRIOR trades on same symbol (walk-forward safe)."""
    df = df.copy().reset_index(drop=True)          # ← السطر الجوهري
    n_prior    = np.zeros(len(df))
    wr_prior   = np.full(len(df), 0.5)
    bars_since = np.full(len(df), -1.0)

    by_sym = defaultdict(list)  # sym -> list of (pos, close_idx, is_win)
    for i, row in df.iterrows():                    # الآن i == position
        sym = row['symbol']
        is_win = row['category'] == 'D'
        prior = by_sym[sym]
        n_prior[i] = len(prior)
        if prior:
            wins = sum(1 for p in prior if p[2])
            wr_prior[i] = wins / len(prior)
            bars_since[i] = row.get('close_idx', 0) - prior[-1][1]
        by_sym[sym].append((i, row.get('close_idx', 0), is_win))

    df['n_prior_sym']    = n_prior
    df['wr_prior_sym']   = wr_prior
    df['bars_since_sym'] = bars_since
    return df


# ═══════════════════════════════════════════════════════════════════════
# Build full feature matrix
# ═══════════════════════════════════════════════════════════════════════

def build_feature_matrix(df, parquets, btc_parquet):
    _log("Building feature matrix ...")
    rows = []
    skipped_no_parquet = 0
    skipped_no_bar     = 0
    
    for _, row in df.iterrows():
        sym = row['symbol']
        ts  = row['entry_dt']
        
        if sym not in parquets:
            skipped_no_parquet += 1
            continue
        
        pdf = parquets[sym]
        ci  = find_bar_index(pdf, ts)
        if ci < 0:
            skipped_no_bar += 1
            continue
        
        # Tier 2: pre-entry path
        t2 = compute_tier2_features(pdf, ci)
        
        # Tier 3: BTC context
        t3 = compute_tier3_features(btc_parquet, ts)
        
        # Tier 4: temporal
        t4 = compute_tier4_features(ts)
        
        # Combine
        combined = {**t2, **t3, **t4}
        combined['_row_idx'] = row.name
        combined['_bar_idx'] = ci
        rows.append(combined)
    
    _log(f"Feature matrix: {len(rows)} rows "
         f"(skipped: no_parquet={skipped_no_parquet}, "
         f"no_bar={skipped_no_bar})", 'OK')
    
    if not rows:
        return df.iloc[:0].copy()
    
    feat_df = pd.DataFrame(rows).set_index('_row_idx')
    merged = df.join(feat_df, how='inner')
    merged = merged.rename(columns={'_bar_idx': 'computed_bar_idx'})
    return merged


# ═══════════════════════════════════════════════════════════════════════
# Statistical analysis
# ═══════════════════════════════════════════════════════════════════════

def cohens_d(a, b):
    if len(a) < 2 or len(b) < 2:
        return 0.0
    sp = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
    if sp < 1e-12:
        return 0.0
    return float((a.mean() - b.mean()) / sp)


def compute_effect_sizes(df, features):
    """Cohen's d for A vs D on each feature."""
    A = df[df['category'] == 'A']
    D = df[df['category'] == 'D']
    results = []
    for f in features:
        if f not in df.columns:
            continue
        av = pd.to_numeric(A[f], errors='coerce').dropna().values
        dv = pd.to_numeric(D[f], errors='coerce').dropna().values
        if len(av) < 20 or len(dv) < 20:
            continue
        d = cohens_d(av, dv)
        results.append({
            'feature': f,
            'mean_A': float(av.mean()),
            'mean_D': float(dv.mean()),
            'cohens_d': d,
            'abs_d': abs(d),
            'n_A': len(av),
            'n_D': len(dv),
        })
    return pd.DataFrame(results).sort_values('abs_d', ascending=False).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════
# Model training + feature importance
# ═══════════════════════════════════════════════════════════════════════

def train_model(df, feature_cols, train_mask):
    """Train RandomForest (for importances) + DecisionTree (for interpretable rules)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.tree import DecisionTreeClassifier
    
    sub = df[df['category'].isin(['A', 'D'])].copy()
    X = sub[feature_cols].apply(pd.to_numeric, errors='coerce').fillna(0.0)
    y = (sub['category'] == 'A').astype(int).values
    train_ok = train_mask[sub.index].values
    
    X_train, y_train = X[train_ok], y[train_ok]
    
    if len(X_train) < 100 or y_train.sum() < 20:
        _log(f"Not enough training data for model", 'WARN')
        return None, None, None
    
    # (أ) RandomForest — لاستخراج Feature Importances
    rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=5,
        min_samples_leaf=20,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(X_train, y_train)
    
    # (ب) DecisionTree — لاستخراج قواعد قابلة للتفسير
    dt = DecisionTreeClassifier(
        max_depth=5,
        min_samples_leaf=15,
        class_weight='balanced',
        random_state=42,
    )
    dt.fit(X_train, y_train)
    
    _log(f"Models trained: n_train={len(X_train)}, n_positive={y_train.sum()}, "
         f"dt_leaves={dt.get_n_leaves()}", 'OK')
    return rf, dt, X.columns.tolist()


def compute_feature_importance(clf, feature_names):
    """Return DataFrame of feature importances."""
    imp = pd.DataFrame({
        'feature': feature_names,
        'importance': clf.feature_importances_,
    }).sort_values('importance', ascending=False).reset_index(drop=True)
    return imp


# ═══════════════════════════════════════════════════════════════════════
# Rule discovery (interpretable decision tree leaves)
# ═══════════════════════════════════════════════════════════════════════

def extract_pure_failures(clf, feature_names, X_full, y_full, min_samples=30):
    """Extract leaves with P(A) >= threshold and P(D) <= max."""
    tree = clf.tree_
    leaves = clf.apply(X_full)
    
    rules = []
    for leaf_id in range(tree.node_count):
        if tree.children_left[leaf_id] != -1:
            continue  # not a leaf
        
        idx = np.where(leaves == leaf_id)[0]
        n = len(idx)
        if n < min_samples:
            continue
        
        n_A = int(y_full[idx].sum())
        n_D = n - n_A
        p_A = n_A / n
        p_D = n_D / n
        
        if p_A < CFG['min_p_A'] or p_D > CFG['max_p_D']:
            continue
        
        # Build condition path
        conds = []
        node = leaf_id
        while node != 0:
            parent = np.where(tree.children_left == node)[0]
            if len(parent) == 0:
                parent = np.where(tree.children_right == node)[0]
            if len(parent) == 0:
                break
            parent = parent[0]
            feat = feature_names[tree.feature[parent]]
            thr  = tree.threshold[parent]
            if tree.children_left[parent] == node:
                conds.append((feat, '<=', float(thr)))
            else:
                conds.append((feat, '>',  float(thr)))
            node = parent
        
        rules.append({
            'n': int(n),
            'n_A': n_A,
            'n_D': n_D,
            'p_A': float(p_A),
            'p_D': float(p_D),
            'conditions': list(reversed(conds)),
        })
    
    return rules


# ═══════════════════════════════════════════════════════════════════════
# Walk-forward validation
# ═══════════════════════════════════════════════════════════════════════

def walk_forward_split(df, n_windows=3):
    """Split df into n_windows chronologically."""
    n = len(df)
    splits = []
    for i in range(n_windows):
        lo = (i * n) // n_windows
        hi = ((i + 1) * n) // n_windows
        splits.append((lo, hi))
    return splits


# ═══════════════════════════════════════════════════════════════════════
# Report generation
# ═══════════════════════════════════════════════════════════════════════

def write_report(out_path, df, meta, effect_df, importance_df, rules, 
                 regime_table, symbol_table):
    lines = []
    add = lines.append
    
    add("# Failure Pattern Analysis — Stage 1\n")
    add(f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if meta:
        add(f"**Source run**: started_at=`{meta.get('started_at','?')}`, "
            f"TF=`{meta.get('timeframe','?')}`, "
            f"capital=`${meta.get('INITIAL_CAPITAL','?')}`")
    add("")
    
    # Executive summary
    add("## 🎯 Executive Summary\n")
    n_total = len(df)
    counts = df['category'].value_counts()
    n_A, n_B, n_D = (counts.get('A', 0), counts.get('B', 0), counts.get('D', 0))
    
    add(f"- **Total analyzed**: {n_total:,} trades")
    add(f"- **A (Direct Fail)**: {n_A:,} ({n_A/max(n_total,1)*100:.1f}%)")
    add(f"- **B (Partial+SL)**: {n_B:,} ({n_B/max(n_total,1)*100:.1f}%)")
    add(f"- **D (Winner)**: {n_D:,} ({n_D/max(n_total,1)*100:.1f}%)")
    add("")
    
    # Current metrics
    lr = df['log_return'].values
    sh = lr.mean() / max(lr.std(ddof=1), 1e-10) * np.sqrt(252)
    add(f"- **Current Sharpe**: {sh:.3f}")
    add(f"- **Mean log_return**: {lr.mean():.6f}")
    add(f"- **Total net_pnl**: ${df['net_pnl'].sum():,.2f}")
    add("")
    
    # Category economics
    add("### Category Economics\n")
    add("| Category | n | mean log_return | mean net_pnl | mean MFE |")
    add("|----------|---|-----------------|--------------|----------|")
    for cat in ['A', 'B', 'D']:
        sub = df[df['category'] == cat]
        if len(sub) == 0:
            continue
        m_lr = sub['log_return'].mean()
        m_pnl = sub['net_pnl'].mean()
        m_mfe = pd.to_numeric(sub.get('mfe_frac', 0), errors='coerce').mean()
        add(f"| {cat} | {len(sub):,} | {m_lr:.6f} | ${m_pnl:,.2f} | {m_mfe*100:.2f}% |")
    add("")
    
    # Counterfactual: block all A
    add("### Counterfactual: Block ALL A (upper bound)\n")
    kept = df[df['category'] != 'A']['log_return'].values
    if len(kept) > 10:
        sh_kept = kept.mean() / max(kept.std(ddof=1), 1e-10) * np.sqrt(252)
        add(f"- **Sharpe if A blocked**: {sh_kept:.3f} (vs current {sh:.3f})")
        add(f"- **Mean log_return**: {kept.mean():.6f} (vs current {lr.mean():.6f})")
    add("")
    
    # Regime breakdown
    add("## 🌊 Regime Analysis\n")
    if regime_table is not None and len(regime_table) > 0:
        add("| Regime | n | P(A) | P(B) | P(D) |")
        add("|--------|---|------|------|------|")
        for _, r in regime_table.iterrows():
            add(f"| {r['regime']} | {r['n']:,} | "
                f"{r['p_A']*100:.1f}% | {r['p_B']*100:.1f}% | {r['p_D']*100:.1f}% |")
        add("")
        
        # Recommendation
        worst = regime_table.sort_values('p_A', ascending=False).iloc[0]
        if worst['p_A'] > 0.50 and worst['n'] >= 100:
            add(f"**⚠️ Regime `{worst['regime']}` has P(A)={worst['p_A']*100:.1f}% "
                f"across {worst['n']:,} trades — candidate for exclusion.**\n")
    
    # Feature effect sizes
    add("## 🔬 Feature Effect Sizes (A vs D)\n")
    if effect_df is not None and len(effect_df) > 0:
        add("| Feature | mean A | mean D | Cohen's d |")
        add("|---------|--------|--------|-----------|")
        for _, r in effect_df.head(20).iterrows():
            add(f"| `{r['feature']}` | {r['mean_A']:.4f} | {r['mean_D']:.4f} | {r['cohens_d']:+.3f} |")
        add("")
        add("**Interpretation**: |d|>0.5 = strong, |d|>0.3 = moderate, "
            "|d|<0.2 = weak.\n")
    
    # Feature importances
    add("## 📊 Feature Importances (Random Forest)\n")
    if importance_df is not None and len(importance_df) > 0:
        add("| Rank | Feature | Importance |")
        add("|------|---------|------------|")
        for i, r in importance_df.head(20).iterrows():
            add(f"| {i+1} | `{r['feature']}` | {r['importance']:.4f} |")
        add("")
    
    # Discovered rules
    add("## 🎯 Discovered Rules (Pure A-enriched)\n")
    if rules:
        add(f"Found **{len(rules)}** rules with P(A) ≥ {CFG['min_p_A']*100:.0f}% "
            f"and P(D) ≤ {CFG['max_p_D']*100:.0f}%, min_n={CFG['min_rule_n']}.\n")
        
        add("| # | Conditions | n | P(A) | P(D) |")
        add("|---|-----------|---|------|------|")
        for i, r in enumerate(rules[:15]):
            conds_str = " AND ".join(
                f"{f} {op} {v:.4f}" for f, op, v in r['conditions']
            )
            add(f"| {i+1} | {conds_str} | {r['n']} | "
                f"{r['p_A']*100:.1f}% | {r['p_D']*100:.1f}% |")
        add("")
    else:
        add("**⚠ No pure A-enriched rules found.** Filter may not be reliable.\n")
    
    # Symbol analysis
    add("## 💱 Symbol-level Analysis\n")
    if symbol_table is not None and len(symbol_table) > 0:
        add("Top 10 loss-heavy symbols:\n")
        add("| Symbol | n | n_A | n_D | P(A) | Total PnL |")
        add("|--------|---|-----|-----|------|-----------|")
        worst = symbol_table.sort_values('total_pnl').head(10)
        for _, r in worst.iterrows():
            add(f"| {r['symbol']} | {int(r['n_trades'])} | "
                f"{int(r['n_A'])} | {int(r['n_D'])} | "
                f"{r['p_A']*100:.1f}% | ${r['total_pnl']:,.2f} |")
        add("")
    
    # Recommendations
    add("## 🎯 Recommendations for Stage 2\n")
    recs = []
    
    if rules:
        best = rules[0]
        conds_str = " AND ".join(f"{f} {op} {v:.4f}" for f, op, v in best['conditions'])
        recs.append(f"1. **Implement top rule** as pre-entry filter: `{conds_str}` "
                    f"(catches {best['n_A']} A, kills {best['n_D']} D over "
                    f"{best['n']} trades).")
    
    if regime_table is not None and len(regime_table) > 0:
        worst_r = regime_table.sort_values('p_A', ascending=False).iloc[0]
        if worst_r['p_A'] > 0.50:
            recs.append(f"2. **Exclude regime `{worst_r['regime']}`** "
                        f"(P(A)={worst_r['p_A']*100:.1f}%).")
    
    if symbol_table is not None and len(symbol_table) > 0:
        worst_syms = symbol_table[symbol_table['total_pnl'] < 0].head(3)
        if len(worst_syms) > 0:
            syms = ", ".join(worst_syms['symbol'].tolist())
            recs.append(f"3. **Consider excluding {syms}** (negative PnL).")
    
    if not recs:
        recs.append("**No strong signals found.** Consider ML-based composite model.")
    
    for r in recs:
        add(r)
    add("")
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    _log(f"Report saved: {out_path}", 'OK')


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--log',        default=CFG['log_path'])
    p.add_argument('--cache',      default=CFG['cache_dir'])
    p.add_argument('--out',        default=CFG['out_dir'])
    p.add_argument('--timeframe',  default=CFG['timeframe'])
    p.add_argument('--history-days', type=int, default=CFG['history_days'])
    args = p.parse_args()
    
    CFG['log_path']     = args.log
    CFG['cache_dir']    = args.cache
    CFG['out_dir']      = args.out
    CFG['timeframe']    = args.timeframe
    CFG['history_days'] = args.history_days
    
    _ensure_dir(CFG['out_dir'])
    
    print("═" * 72)
    print("  🔍 Failure Pattern Analysis — Stage 1")
    print("═" * 72)
    
    # 1. Load & classify
    df, meta = load_trades(CFG['log_path'])
    df = classify_trades(df)
    
    # Keep only A/B/D for main analysis
    df_analysis = df[df['category'].isin(['A', 'B', 'D'])].copy()
    _log(f"Kept {len(df_analysis)} trades for analysis (A/B/D only)", 'OK')
    
    # 2. Load parquet
    parquets = load_parquet(
        CFG['cache_dir'], CFG['timeframe'],
        df_analysis['symbol'].unique().tolist(),
        CFG['history_days'],
    )
    if not parquets:
        _log("No parquet data — aborting", 'ERR')
        return
    
    # BTC for tier 3
    btc_key = 'BTC/USDT'
    btc_parquet = parquets.get(btc_key)
    if btc_parquet is None:
        _log("BTC parquet missing — tier 3 features disabled", 'WARN')
    
    # 3. Build features
    df_feat = build_feature_matrix(df_analysis, parquets, btc_parquet)
    if len(df_feat) < 100:
        _log(f"Insufficient features ({len(df_feat)}) — aborting", 'ERR')
        return
    
    # 4. Tier 5 (walk-forward trade history)
    df_feat = compute_tier5_features(df_feat)
    
    # 5. Regime classification
    df_feat['regime'] = classify_regime(df_feat)
    
    # 6. Determine feature columns
    exclude = {
        'symbol', 'entry_time', 'entry_dt', 'action', 'exit_reason',
        'category', 'regime', '_meta',
        'entry_price', 'exit_price', 'pos_size', 'net_pnl',
        'log_return', 'cap_delta_since_entry', 'partial_pnl',
        'capital_before', 'capital_after', 'is_win',
        'mfe_frac', 'entry_ci', 'exit_ci', 'hold_bars',
        'sl_dist_initial', 'computed_bar_idx',
        'signal_price', 'signal_sl', 'signal_tp1',
        'feat_idx', 'close_idx',
    }
    feature_cols = [
        c for c in df_feat.columns
        if c not in exclude and df_feat[c].dtype in ['float64', 'int64', 'float32', 'int32']
    ]
    # Add existing numeric physics features from log
    for extra in ['score', 'E_therm', 'H', 'dH', 'dF', 'friction',
                  'gauge_force', 'delta_gap', 'geodesic_accel', 'V', 'C',
                  'T_info', 'H_over_Hmax', 'friction_drag_over_sl',
                  'sl_sigma', 'ema_slope', 'ema_slope_against',
                  'dist_from_ema_norm', 'dynamic_risk', 'tri_val']:
        if extra in df_feat.columns and extra not in feature_cols:
            feature_cols.append(extra)
    
    _log(f"Feature columns: {len(feature_cols)}", 'OK')
    
    # 7. Effect sizes
    effect_df = compute_effect_sizes(df_feat, feature_cols)
    _log(f"Effect sizes computed: {len(effect_df)} features", 'OK')
    
    # 8. Train/test split (chronological 70/30)
    n = len(df_feat)
    split_idx = int(n * CFG['train_frac'])
    train_mask = pd.Series(False, index=df_feat.index)
    train_mask.iloc[:split_idx] = True
    
    # 9. Train models (RF for importances, DT for interpretable rules)
    rf, dt, feat_names = train_model(df_feat, feature_cols, train_mask)
    importance_df = None
    rules = []
    
    if rf is not None:
        importance_df = compute_feature_importance(rf, feat_names)
        
        # Extract rules on TRAIN portion only
        sub_train = df_feat[train_mask].copy()
        sub_train = sub_train[sub_train['category'].isin(['A', 'D'])]
        X_tr = sub_train[feat_names].apply(pd.to_numeric, errors='coerce').fillna(0.0)
        y_tr = (sub_train['category'] == 'A').astype(int).values
        
        rules = extract_pure_failures(
            dt, feat_names, X_tr.values, y_tr,
            min_samples=CFG['min_rule_n'],
        )
        _log(f"Rules discovered on train (DT): {len(rules)}", 'OK')
    
    # 10. Regime table
    regime_table = df_feat.groupby('regime').agg(
        n=('category', 'size'),
    ).reset_index()
    for cat in ['A', 'B', 'D']:
        regime_table[f'n_{cat}'] = df_feat.groupby('regime').apply(
            lambda g, c=cat: (g['category'] == c).sum()
        ).values
    regime_table['p_A'] = regime_table['n_A'] / regime_table['n']
    regime_table['p_B'] = regime_table['n_B'] / regime_table['n']
    regime_table['p_D'] = regime_table['n_D'] / regime_table['n']
    regime_table = regime_table.sort_values('p_A', ascending=False).reset_index(drop=True)
    
    # 11. Symbol table
    symbol_table = df_feat.groupby('symbol').agg(
        n_trades=('category', 'size'),
        n_A=('category', lambda s: (s == 'A').sum()),
        n_D=('category', lambda s: (s == 'D').sum()),
        total_pnl=('net_pnl', 'sum'),
    ).reset_index()
    symbol_table['p_A'] = symbol_table['n_A'] / symbol_table['n_trades']
    
    # 12. Save outputs
    df_feat.to_csv(os.path.join(CFG['out_dir'], 'trades_enriched.csv'), index=False)
    effect_df.to_csv(os.path.join(CFG['out_dir'], 'feature_effect_sizes.csv'), index=False)
    if importance_df is not None:
        importance_df.to_csv(os.path.join(CFG['out_dir'], 'feature_importances.csv'), index=False)
    regime_table.to_csv(os.path.join(CFG['out_dir'], 'regime_breakdown.csv'), index=False)
    symbol_table.to_csv(os.path.join(CFG['out_dir'], 'symbol_analysis.csv'), index=False)
    
    if rules:
        rules_df = pd.DataFrame([
            {
                'n': r['n'],
                'n_A': r['n_A'],
                'n_D': r['n_D'],
                'p_A': r['p_A'],
                'p_D': r['p_D'],
                'conditions': " AND ".join(
                    f"{f} {op} {v:.4f}" for f, op, v in r['conditions']
                ),
            }
            for r in rules
        ])
        rules_df.to_csv(os.path.join(CFG['out_dir'], 'rules.csv'), index=False)
    
    # 13. Write report
    write_report(
        os.path.join(CFG['out_dir'], 'report.md'),
        df_feat, meta, effect_df, importance_df, rules,
        regime_table, symbol_table,
    )
    
    # Final summary
    print()
    print("═" * 72)
    print("  ✅ Analysis complete")
    print("═" * 72)
    print(f"  Output directory: {CFG['out_dir']}/")
    print(f"  - report.md              (main report)")
    print(f"  - trades_enriched.csv    ({len(df_feat)} trades with features)")
    print(f"  - feature_effect_sizes.csv")
    print(f"  - feature_importances.csv")
    print(f"  - regime_breakdown.csv")
    print(f"  - symbol_analysis.csv")
    print(f"  - rules.csv              ({len(rules)} rules)")


if __name__ == '__main__':
    main()
