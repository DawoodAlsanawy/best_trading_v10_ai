#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  train_adaptive_filter.py  —  Stage 3B                                       ║
║                                                                              ║
║  هدف واحد: بناء نموذج يتنبأ بـ Category A باستخدام 18 ميزة مستقرة فقط      ║
║           + regime_id، والتحقق منه بـ Walk-Forward حقيقي.                    ║
║                                                                              ║
║  القرارات الحاسمة:                                                          ║
║    • Target: A=1 (Direct Fail), B∪D=0 (Not Fail)                             ║
║    • Features: 18 stable + regime_id + regime_confidence                     ║
║    • Model: LightGBM + Isotonic Calibration                                  ║
║    • Validation: 5 expanding-window folds (train [0,i], test [i,i+Δ])        ║
║    • Cost function: cost(A_miss)=1.0, cost(D_kill)=6.06, cost(B_kill)=0.53   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os, sys, json, argparse, warnings
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from scipy import stats
warnings.filterwarnings('ignore')

# ── Constants
STABLE_FEATURES = [
    'H', 'H_over_Hmax', 'friction', 'delta_gap', 'adv_usd', 'body_ratio_avg',
    'score', 'gauge_force', 'geodesic_accel', 'dF', 'dH', 'vol_ratio_3_20',
    'atr', 'vol_accel', 'C', 'tri_val', 'gap_count_5', 'V',
]
REGIME_FEATURES = ['regime_id', 'regime_confidence']
ALL_FEATURES = STABLE_FEATURES + REGIME_FEATURES

# Cost ratios (from Stage 1 category economics)
COST_A_BLOCKED    = 0.003375   # gain when blocking A
COST_B_BLOCKED    = 0.001778   # loss when blocking B
COST_D_BLOCKED    = 0.020442   # loss when blocking D

# Break-even ratio: to justify blocking, precision_A must exceed
# COST_D_BLOCKED / (COST_A_BLOCKED + COST_D_BLOCKED) ≈ 0.858
# but B is in between; realistic break-even ≈ 0.80
THRESHOLD_SWEEP = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]

# Walk-forward splits: 5 folds (expanding train)
# Fold: train=[0, i), test=[i, i+Δ)
FOLD_SIZE = 1000
MIN_TRAIN = 1500


def log(msg, lvl='INFO'):
    p = {'INFO': 'ℹ', 'OK': '✓', 'WARN': '⚠', 'ERR': '✗', 'STEP': '→'}
    print(f"{p.get(lvl, '•')} {msg}")


def compute_sharpe(lr):
    lr = np.asarray(lr, dtype=float)
    lr = lr[np.isfinite(lr)]
    if len(lr) < 2: return 0.0
    sd = lr.std(ddof=1)
    return float(lr.mean() / sd * np.sqrt(252)) if sd > 1e-12 else 0.0


def economic_value(blocked_df):
    """
    Net log_return value of blocking these trades.
    Positive = blocking was profitable.
    """
    if len(blocked_df) == 0:
        return 0.0
    n_A = (blocked_df['category'] == 'A').sum()
    n_B = (blocked_df['category'] == 'B').sum()
    n_D = (blocked_df['category'] == 'D').sum()
    value = (n_A * COST_A_BLOCKED
             - n_B * COST_B_BLOCKED
             - n_D * COST_D_BLOCKED)
    return float(value)


def fit_fold(train_df, test_df, threshold, label=''):
    """
    Train LightGBM on train_df, predict on test_df, apply threshold.
    Returns dict of metrics.
    """
    import lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression
    
    # Target: A=1, (B or D)=0
    train_mask = train_df['category'].isin(['A', 'B', 'D'])
    test_mask  = test_df['category'].isin(['A', 'B', 'D'])
    tr = train_df[train_mask].copy()
    te = test_df[test_mask].copy()
    
    if len(tr) < 200 or len(te) < 50:
        return None
    
    y_tr = (tr['category'] == 'A').astype(int).values
    y_te = (te['category'] == 'A').astype(int).values
    
    if y_tr.sum() < 30 or (1 - y_tr).sum() < 30:
        return None
    
    X_tr = tr[ALL_FEATURES].apply(pd.to_numeric, errors='coerce').fillna(0.0)
    X_te = te[ALL_FEATURES].apply(pd.to_numeric, errors='coerce').fillna(0.0)
    
    # Train
    model = lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        class_weight='balanced', random_state=42, verbose=-1,
        min_child_samples=20,
    )
    model.fit(X_tr, y_tr)
    
    # Calibration on train (time-split: last 20% for calibration)
    n_cal = max(100, len(X_tr) // 5)
    cal_start = len(X_tr) - n_cal
    model_cal = lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        class_weight='balanced', random_state=42, verbose=-1,
        min_child_samples=20,
    )
    model_cal.fit(X_tr.iloc[:cal_start], y_tr[:cal_start])
    cal_preds = model_cal.predict_proba(X_tr.iloc[cal_start:])[:, 1]
    iso = IsotonicRegression(out_of_bounds='clip')
    iso.fit(cal_preds, y_tr[cal_start:])
    
    # Predict on test
    raw_probs = model.predict_proba(X_te)[:, 1]
    cal_probs = iso.predict(raw_probs)
    
    # Apply threshold
    block_mask = cal_probs > threshold
    
    blocked = te[block_mask]
    kept = te[~block_mask]
    
    n_blocked = len(blocked)
    n_A_blocked = int((blocked['category'] == 'A').sum())
    n_B_blocked = int((blocked['category'] == 'B').sum())
    n_D_blocked = int((blocked['category'] == 'D').sum())
    
    n_A_total = int((te['category'] == 'A').sum())
    n_D_total = int((te['category'] == 'D').sum())
    
    precision_A = n_A_blocked / max(n_blocked, 1)
    recall_A = n_A_blocked / max(n_A_total, 1)
    kill_D_rate = n_D_blocked / max(n_D_total, 1)
    
    base_sharpe = compute_sharpe(te['log_return'].values)
    kept_sharpe = compute_sharpe(kept['log_return'].values) if len(kept) > 10 else 0.0
    
    econ = economic_value(blocked)
    bc_ratio = (n_A_blocked * COST_A_BLOCKED) / max(
        n_B_blocked * COST_B_BLOCKED + n_D_blocked * COST_D_BLOCKED, 1e-9
    )
    
    return {
        'fold': label,
        'n_train': len(tr), 'n_test': len(te),
        'n_blocked': n_blocked, 'n_kept': len(kept),
        'n_A_blocked': n_A_blocked, 'n_B_blocked': n_B_blocked,
        'n_D_blocked': n_D_blocked,
        'n_A_test_total': n_A_total, 'n_D_test_total': n_D_total,
        'precision_A': float(precision_A),
        'recall_A': float(recall_A),
        'kill_D_rate': float(kill_D_rate),
        'base_sharpe': float(base_sharpe),
        'kept_sharpe': float(kept_sharpe),
        'sharpe_delta_pct': float((kept_sharpe - base_sharpe) / max(abs(base_sharpe), 1e-6) * 100),
        'econ_value': float(econ),
        'bc_ratio': float(bc_ratio),
        'threshold': float(threshold),
    }


def walk_forward_validate(df, threshold):
    """Run 5-fold expanding-window walk-forward."""
    n = len(df)
    folds = []
    start = MIN_TRAIN
    while start + FOLD_SIZE <= n:
        train = df.iloc[:start]
        test = df.iloc[start:start + FOLD_SIZE]
        res = fit_fold(train, test, threshold, label=f'WF_{start}_{start+FOLD_SIZE}')
        if res is not None:
            folds.append(res)
        start += FOLD_SIZE
    return folds


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='failure_analysis/regimes.csv')
    p.add_argument('--out',   default='failure_analysis')
    args = p.parse_args()
    
    print("═" * 72)
    print("  🔬 Stage 3B — Adaptive Filter with Walk-Forward Validation")
    print("═" * 72)
    
    # ── Load
    df = pd.read_csv(args.input, parse_dates=['entry_dt'])
    df = df.sort_values('entry_dt').reset_index(drop=True)
    log(f"Loaded {len(df)} trades", 'OK')
    
    # Verify required features exist
    missing = [f for f in ALL_FEATURES if f not in df.columns]
    if missing:
        log(f"Missing features: {missing}", 'ERR')
        sys.exit(1)
    
    # Distribution
    log(f"Categories: A={(df.category=='A').sum()}, "
        f"B={(df.category=='B').sum()}, D={(df.category=='D').sum()}", 'OK')
    log(f"Regimes: {df['regime_id'].value_counts().to_dict()}", 'OK')
    
    # ── Threshold sweep
    log("\nSweeping thresholds via 5-fold walk-forward ...", 'STEP')
    all_results = []
    
    for thr in THRESHOLD_SWEEP:
        folds = walk_forward_validate(df, thr)
        if not folds:
            log(f"  thr={thr:.2f}: no valid folds", 'WARN')
            continue
        
        # Aggregate across folds
        total_blocked = sum(f['n_blocked'] for f in folds)
        total_A_blocked = sum(f['n_A_blocked'] for f in folds)
        total_D_blocked = sum(f['n_D_blocked'] for f in folds)
        total_B_blocked = sum(f['n_B_blocked'] for f in folds)
        total_A_test = sum(f['n_A_test_total'] for f in folds)
        total_D_test = sum(f['n_D_test_total'] for f in folds)
        
        agg_precision = total_A_blocked / max(total_blocked, 1)
        agg_recall = total_A_blocked / max(total_A_test, 1)
        agg_kill_D = total_D_blocked / max(total_D_test, 1)
        
        mean_sharpe_delta = np.mean([f['sharpe_delta_pct'] for f in folds])
        mean_kept_sharpe = np.mean([f['kept_sharpe'] for f in folds])
        mean_base_sharpe = np.mean([f['base_sharpe'] for f in folds])
        std_sharpe_delta = np.std([f['sharpe_delta_pct'] for f in folds])
        
        total_econ = sum(f['econ_value'] for f in folds)
        
        all_results.append({
            'threshold': thr,
            'n_folds': len(folds),
            'total_blocked': total_blocked,
            'total_A_blocked': total_A_blocked,
            'total_B_blocked': total_B_blocked,
            'total_D_blocked': total_D_blocked,
            'agg_precision_A': agg_precision,
            'agg_recall_A': agg_recall,
            'agg_kill_D': agg_kill_D,
            'base_sharpe_mean': mean_base_sharpe,
            'kept_sharpe_mean': mean_kept_sharpe,
            'sharpe_delta_mean': mean_sharpe_delta,
            'sharpe_delta_std': std_sharpe_delta,
            'econ_value_total': total_econ,
        })
        
        log(f"  thr={thr:.2f}: precision={agg_precision*100:.1f}%, "
            f"recall={agg_recall*100:.1f}%, kill_D={agg_kill_D*100:.1f}%, "
            f"Sharpe {mean_base_sharpe:.2f}→{mean_kept_sharpe:.2f} "
            f"({mean_sharpe_delta:+.0f}%), "
            f"econ={total_econ:+.3f}R",
            'OK' if agg_precision > 0.75 and mean_sharpe_delta > 0 else 'WARN')
    
    results_df = pd.DataFrame(all_results)
    results_df.to_csv(os.path.join(args.out, 'stage3b_threshold_sweep.csv'), index=False)
    
    if len(results_df) == 0:
        log("No thresholds produced valid folds", 'ERR')
        sys.exit(1)
    
    # ── Select best threshold
    # Criteria: highest Sharpe gain subject to precision > 0.70 AND kill_D < 0.15
    viable = results_df[
        (results_df['agg_precision_A'] > 0.70) &
        (results_df['agg_kill_D'] < 0.15) &
        (results_df['sharpe_delta_mean'] > 0)
    ]
    
    if len(viable) == 0:
        log("\n⚠  No viable threshold. Relaxing constraints...", 'WARN')
        viable = results_df[results_df['sharpe_delta_mean'] > 0]
    
    if len(viable) == 0:
        log("✗  Model doesn't improve on any fold. Aborting.", 'ERR')
        log("   Conclusion: 18 stable features + regime don't predict A well enough.", 'WARN')
        log("   Recommendation: pivot to bot-level fixes (execution, risk management).", 'WARN')
        sys.exit(0)
    
    best = viable.sort_values('sharpe_delta_mean', ascending=False).iloc[0]
    
    log(f"\n🏆 Best threshold: {best['threshold']:.2f}", 'OK')
    log(f"  Precision: {best['agg_precision_A']*100:.1f}%", 'OK')
    log(f"  Recall:    {best['agg_recall_A']*100:.1f}%", 'OK')
    log(f"  Kill-D:    {best['agg_kill_D']*100:.1f}%", 'OK')
    log(f"  Sharpe:    {best['base_sharpe_mean']:.2f} → {best['kept_sharpe_mean']:.2f} "
        f"({best['sharpe_delta_mean']:+.0f}% ± {best['sharpe_delta_std']:.0f}%)", 'OK')
    log(f"  Econ value: {best['econ_value_total']:+.3f}R total", 'OK')
    
    # ── Detail for best threshold
    log(f"\nDetailed folds at threshold={best['threshold']:.2f}:", 'STEP')
    best_folds = walk_forward_validate(df, best['threshold'])
    
    for f in best_folds:
        log(f"  {f['fold']}: "
            f"blocked={f['n_blocked']:>3} "
            f"(A={f['n_A_blocked']:>3} B={f['n_B_blocked']:>2} D={f['n_D_blocked']:>2}) | "
            f"prec={f['precision_A']*100:>5.1f}% "
            f"recall={f['recall_A']*100:>5.1f}% | "
            f"Sharpe {f['base_sharpe']:.2f}→{f['kept_sharpe']:.2f} "
            f"({f['sharpe_delta_pct']:+.0f}%)",
            'OK' if f['sharpe_delta_pct'] > 0 else 'WARN')
    
    # ── Train FINAL model on ALL data for integration
    log(f"\nTraining final model on all {len(df)} trades ...", 'STEP')
    import lightgbm as lgb
    from sklearn.isotonic import IsotonicRegression
    import pickle
    
    final_train = df[df['category'].isin(['A', 'B', 'D'])].copy()
    y_final = (final_train['category'] == 'A').astype(int).values
    X_final = final_train[ALL_FEATURES].apply(pd.to_numeric, errors='coerce').fillna(0.0)
    
    final_model = lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        class_weight='balanced', random_state=42, verbose=-1,
        min_child_samples=20,
    )
    final_model.fit(X_final, y_final)
    
    # Calibration
    n_cal = max(200, len(X_final) // 5)
    cal_start = len(X_final) - n_cal
    model_cal = lgb.LGBMClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        class_weight='balanced', random_state=42, verbose=-1,
        min_child_samples=20,
    )
    model_cal.fit(X_final.iloc[:cal_start], y_final[:cal_start])
    cal_preds = model_cal.predict_proba(X_final.iloc[cal_start:])[:, 1]
    final_iso = IsotonicRegression(out_of_bounds='clip')
    final_iso.fit(cal_preds, y_final[cal_start:])
    
    # Save
    model_path = os.path.join(args.out, 'adaptive_filter_model.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump({
            'model': final_model,
            'calibrator': final_iso,
            'features': ALL_FEATURES,
            'threshold': float(best['threshold']),
            'trained_at': datetime.now(timezone.utc).isoformat(),
            'expected_precision': float(best['agg_precision_A']),
            'expected_recall': float(best['agg_recall_A']),
        }, f)
    log(f"Saved: {model_path}", 'OK')
    
    # ── Report
    report = [
        "# Stage 3B — Adaptive Filter Validation\n",
        f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n",
        "## 🎯 Executive Summary\n",
        f"- **Best threshold**: {best['threshold']:.2f}",
        f"- **Walk-forward folds**: {len(best_folds)}",
        f"- **Aggregate precision_A**: {best['agg_precision_A']*100:.1f}%",
        f"- **Aggregate recall_A**: {best['agg_recall_A']*100:.1f}%",
        f"- **Aggregate kill_D**: {best['agg_kill_D']*100:.1f}%",
        f"- **Sharpe before**: {best['base_sharpe_mean']:.3f}",
        f"- **Sharpe after**:  {best['kept_sharpe_mean']:.3f}",
        f"- **Sharpe delta**:  {best['sharpe_delta_mean']:+.1f}% "
        f"(±{best['sharpe_delta_std']:.1f}% across folds)",
        f"- **Economic value**: {best['econ_value_total']:+.3f}R total\n",
        "## 📊 Threshold Sweep\n",
        "| Threshold | Precision | Recall | Kill-D | Sharpe Δ | Econ |",
        "|-----------|-----------|--------|--------|----------|------|",
    ]
    for _, r in results_df.iterrows():
        report.append(
            f"| {r['threshold']:.2f} | "
            f"{r['agg_precision_A']*100:.1f}% | "
            f"{r['agg_recall_A']*100:.1f}% | "
            f"{r['agg_kill_D']*100:.1f}% | "
            f"{r['sharpe_delta_mean']:+.0f}% | "
            f"{r['econ_value_total']:+.3f}R |"
        )
    report.append("")
    report.append("## 🔬 Per-Fold Details (Best Threshold)\n")
    report.append("| Fold | Blocked | A | B | D | Precision | Recall | Sharpe Δ |")
    report.append("|------|---------|---|---|---|-----------|--------|----------|")
    for f in best_folds:
        report.append(
            f"| {f['fold']} | {f['n_blocked']} | {f['n_A_blocked']} | "
            f"{f['n_B_blocked']} | {f['n_D_blocked']} | "
            f"{f['precision_A']*100:.1f}% | {f['recall_A']*100:.1f}% | "
            f"{f['sharpe_delta_pct']:+.0f}% |"
        )
    
    report_path = os.path.join(args.out, 'stage3b_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(report))
    log(f"Report: {report_path}", 'OK')
    
    # ── Decision
    print()
    print("═" * 72)
    print("  🎯 DECISION")
    print("═" * 72)
    
    if best['agg_precision_A'] > 0.75 and best['agg_kill_D'] < 0.10:
        print(f"  ✅ FILTER IS VIABLE")
        print(f"     Precision {best['agg_precision_A']*100:.0f}% "
              f"with kill-D {best['agg_kill_D']*100:.1f}%")
        print(f"     → Ready for integration (Stage 3C)")
    elif best['agg_precision_A'] > 0.65 and best['agg_kill_D'] < 0.15:
        print(f"  ⚠️  FILTER IS MARGINAL")
        print(f"     Precision {best['agg_precision_A']*100:.0f}% "
              f"with kill-D {best['agg_kill_D']*100:.1f}%")
        print(f"     → Can integrate with monitoring (Kill Switches critical)")
    else:
        print(f"  ❌ FILTER IS TOO WEAK")
        print(f"     Precision {best['agg_precision_A']*100:.0f}% "
              f"with kill-D {best['agg_kill_D']*100:.1f}%")
        print(f"     → Do NOT integrate. Pivot to bot-level fixes.")
    
    print()


if __name__ == '__main__':
    # Ensure lightgbm available
    try:
        import lightgbm
    except ImportError:
        print("❌ lightgbm not installed. Run: pip install lightgbm")
        sys.exit(1)
    
    main()
