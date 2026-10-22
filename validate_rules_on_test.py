#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  validate_rules_on_test.py  —  Out-of-Sample Validation (Stage 2)            ║
║                                                                              ║
║  المنهجية:                                                                   ║
║    1. يحمّل trades_enriched.csv (من Stage 1)                                ║
║    2. يعيد التقسيم الزمني 70/30 (نفس Stage 1)                                ║
║    3. يطبق القواعد الست المُستخرجة على TEST فقط (out-of-sample)              ║
║    4. يقيس Catch/Kill Rate + Sharpe + PnL                                    ║
║    5. يفحص Covariate Shift (هل test نفس توزيع train؟)                       ║
║    6. يختبر جميع تركيبات القواعد ويُرسم Pareto frontier                      ║
║                                                                              ║
║  قواعد الاستخراج: Rule 1..6 (hardcoded من Stage 1)                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from itertools import combinations
from scipy import stats

# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

CFG = {
    'input_csv':         'failure_analysis/trades_enriched.csv',
    'out_dir':           'failure_analysis',
    'train_frac':        0.70,
    'min_remaining':     200,    # أدنى عدد صفقات بعد الفلترة
    'min_blocked':       30,     # أدنى عدد صفقات محجوبة لتقييم القاعدة
    'category_A_value': -0.003375,  # mean log_return A (for benefit/cost)
    'category_B_value': +0.001778,  # mean log_return B
    'category_D_value': +0.020442,  # mean log_return D
}

# ═══════════════════════════════════════════════════════════════════════
# Rules (hardcoded from Stage 1 output)
# ═══════════════════════════════════════════════════════════════════════
# Format: list of (feature, op, threshold)
# NaN handling: fail-open (trade not blocked if feature is NaN)

RULES = {
    'R1': [
        ('E_therm',       '<=',  0.0188),
        ('btc_ret_24',    '<=',  0.0717),
        ('T_info',        '<=',  3.7230),
        ('dist_high_100', '<=', -0.0657),
        ('btc_ret_24',    '<=', -0.0031),
    ],
    'R2': [
        ('E_therm',       '<=',  0.0188),
        ('btc_ret_24',    '<=',  0.0717),
        ('T_info',        '<=',  3.7230),
        ('dist_high_100', '>',  -0.0657),
        ('rr_design',     '>',   9.3717),
    ],
    'R3': [
        ('E_therm',       '<=',  0.0188),
        ('btc_ret_24',    '<=',  0.0717),
        ('T_info',        '>',   3.7230),
        ('ret_24',        '<=', -0.0368),
        ('score',         '>',   5.1406),
    ],
    'R4': [
        ('E_therm',       '>',   0.0188),
        ('ret_24',        '<=', -0.0434),
        ('dist_high_100', '<=', -0.2552),
        ('btc_ret_24',    '<=', -0.0749),
        ('ret_12',        '>',  -0.1396),
    ],
    'R5': [
        ('E_therm',       '>',   0.0188),
        ('ret_24',        '<=', -0.0434),
        ('dist_high_100', '>',  -0.2552),
        ('btc_ret_6',     '>',  -0.0590),
        ('ret_3',         '>',  -0.0685),
    ],
    'R6': [
        ('E_therm',       '>',   0.0188),
        ('ret_24',        '>',  -0.0434),
        ('T_info',        '<=',  7.3626),
        ('dynamic_risk',  '<=',  0.0190),
        ('btc_ema_slope', '<=', -0.0363),
    ],
}

# Training set counts from Stage 1 (for reference only)
STAGE1_TRAIN = {
    'R1': {'n': 308, 'n_A': 284, 'n_D': 24},
    'R2': {'n': 224, 'n_A': 221, 'n_D': 3},
    'R3': {'n': 128, 'n_A': 124, 'n_D': 4},
    'R4': {'n': 77,  'n_A': 76,  'n_D': 1},
    'R5': {'n': 122, 'n_A': 120, 'n_D': 2},
    'R6': {'n': 48,  'n_A': 48,  'n_D': 0},
}


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def log(msg, level='INFO'):
    prefix = {'INFO': 'ℹ', 'OK': '✓', 'WARN': '⚠', 'ERR': '✗', 'STEP': '→'}
    print(f"{prefix.get(level, '•')} {msg}")


def compute_sharpe(log_returns):
    """Same formula as bot: mean/std * sqrt(252)."""
    lr = np.asarray(log_returns, dtype=float)
    lr = lr[np.isfinite(lr)]
    if len(lr) < 2:
        return 0.0
    sd = lr.std(ddof=1)
    if sd < 1e-12:
        return 0.0
    return float(lr.mean() / sd * np.sqrt(252))


def apply_rule(df, rule_conditions):
    """
    Apply rule as boolean mask.
    NaN → False (fail-open: trade not blocked if feature is NaN).
    """
    mask = pd.Series(True, index=df.index)
    for feat, op, thresh in rule_conditions:
        if feat not in df.columns:
            return pd.Series(False, index=df.index)
        col = pd.to_numeric(df[feat], errors='coerce')
        if op == '<=':
            cond = col <= thresh
        elif op == '<':
            cond = col < thresh
        elif op == '>=':
            cond = col >= thresh
        elif op == '>':
            cond = col > thresh
        else:
            raise ValueError(f"Unknown operator: {op}")
        mask = mask & cond.fillna(False)
    return mask


def compute_metrics(df):
    """Compute standard metrics on a trade subset."""
    if len(df) == 0:
        return {
            'n': 0, 'n_A': 0, 'n_B': 0, 'n_D': 0,
            'win_rate': 0.0, 'sharpe': 0.0,
            'mean_lr': 0.0, 'sum_pnl': 0.0,
            'benefit_cost_ratio': None,
        }
    lr = pd.to_numeric(df['log_return'], errors='coerce').dropna().values
    pnl = pd.to_numeric(df['net_pnl'], errors='coerce').dropna().values
    n_A = int((df['category'] == 'A').sum())
    n_B = int((df['category'] == 'B').sum())
    n_D = int((df['category'] == 'D').sum())
    return {
        'n': len(df),
        'n_A': n_A, 'n_B': n_B, 'n_D': n_D,
        'win_rate': n_D / max(len(df), 1),
        'sharpe': compute_sharpe(lr),
        'mean_lr': float(lr.mean()) if len(lr) > 0 else 0.0,
        'sum_pnl': float(pnl.sum()) if len(pnl) > 0 else 0.0,
    }


def benefit_cost_ratio(n_A_caught, n_B_blocked, n_D_killed):
    """
    Economic ratio: money saved by blocking A / money lost by blocking B,D.
    Uses category mean log_returns from Stage 1.
    """
    benefit = n_A_caught * abs(CFG['category_A_value'])
    cost = (n_B_blocked * CFG['category_B_value']
            + n_D_killed * CFG['category_D_value'])
    if cost <= 1e-12:
        return float('inf') if benefit > 0 else 0.0
    return benefit / cost


# ═══════════════════════════════════════════════════════════════════════
# Main analysis
# ═══════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input',  default=CFG['input_csv'])
    p.add_argument('--out',    default=CFG['out_dir'])
    p.add_argument('--train-frac', type=float, default=CFG['train_frac'])
    args = p.parse_args()

    CFG['input_csv'] = args.input
    CFG['out_dir']   = args.out
    CFG['train_frac'] = args.train_frac
    os.makedirs(CFG['out_dir'], exist_ok=True)

    print("═" * 72)
    print("  🔬 Stage 2 — Out-of-Sample Validation of Stage 1 Rules")
    print("═" * 72)

    # ── 1. Load enriched trades
    if not os.path.exists(CFG['input_csv']):
        log(f"File not found: {CFG['input_csv']}", 'ERR')
        sys.exit(1)

    df = pd.read_csv(CFG['input_csv'], parse_dates=['entry_dt'])
    log(f"Loaded {len(df)} trades from {CFG['input_csv']}", 'OK')

    # ── 2. Ensure chronological sort
    df = df.sort_values('entry_dt').reset_index(drop=True)

    # ── 3. Split (identical to Stage 1)
    n = len(df)
    split_idx = int(n * CFG['train_frac'])
    train = df.iloc[:split_idx].reset_index(drop=True)
    test  = df.iloc[split_idx:].reset_index(drop=True)

    log(f"Train: {len(train)} trades  |  Test: {len(test)} trades", 'OK')
    log(f"Test period: {test['entry_dt'].min()} → {test['entry_dt'].max()}", 'INFO')

    # ── 4. Baseline metrics
    base_train = compute_metrics(train)
    base_test  = compute_metrics(test)

    log(f"\n  Train baseline: n={base_train['n']}, "
        f"A={base_train['n_A']}, B={base_train['n_B']}, D={base_train['n_D']}, "
        f"Sharpe={base_train['sharpe']:.3f}, WinRate={base_train['win_rate']*100:.1f}%",
        'INFO')
    log(f"  Test  baseline: n={base_test['n']}, "
        f"A={base_test['n_A']}, B={base_test['n_B']}, D={base_test['n_D']}, "
        f"Sharpe={base_test['sharpe']:.3f}, WinRate={base_test['win_rate']*100:.1f}%",
        'INFO')

    # ── 5. Covariate shift check
    log("\n[1/4] Covariate shift check on rule features ...", 'STEP')
    rule_features = set()
    for conds in RULES.values():
        for f, _, _ in conds:
            rule_features.add(f)

    shift_rows = []
    for f in sorted(rule_features):
        if f not in df.columns:
            shift_rows.append({'feature': f, 'train_mean': np.nan,
                              'test_mean': np.nan, 'ks_stat': np.nan,
                              'ks_p': np.nan, 'drift': 'MISSING'})
            continue
        tr_vals = pd.to_numeric(train[f], errors='coerce').dropna().values
        ts_vals = pd.to_numeric(test[f],  errors='coerce').dropna().values
        if len(tr_vals) < 30 or len(ts_vals) < 30:
            shift_rows.append({'feature': f, 'train_mean': np.nan,
                              'test_mean': np.nan, 'ks_stat': np.nan,
                              'ks_p': np.nan, 'drift': 'INSUFFICIENT'})
            continue
        ks_stat, ks_p = stats.ks_2samp(tr_vals, ts_vals)
        drift = 'SIGNIFICANT' if ks_p < 0.01 else 'OK'
        shift_rows.append({
            'feature': f,
            'train_mean': float(tr_vals.mean()),
            'test_mean':  float(ts_vals.mean()),
            'ks_stat':    float(ks_stat),
            'ks_p':       float(ks_p),
            'drift':      drift,
        })

    shift_df = pd.DataFrame(shift_rows)
    n_drift = int((shift_df['drift'] == 'SIGNIFICANT').sum())
    log(f"  {n_drift} features show significant drift (p<0.01)", 
        'WARN' if n_drift > 0 else 'OK')

    # ── 6. Per-rule evaluation on TEST
    log("\n[2/4] Per-rule out-of-sample evaluation ...", 'STEP')
    rule_results = []
    rule_masks_test = {}

    for rule_name, conds in RULES.items():
        mask_test = apply_rule(test, conds)
        rule_masks_test[rule_name] = mask_test

        blocked = test[mask_test]
        passed  = test[~mask_test]

        n_blocked = len(blocked)
        if n_blocked < CFG['min_blocked']:
            rule_results.append({
                'rule': rule_name,
                'status': 'insufficient_data',
                'blocked_n': n_blocked,
                'test_catch_A': 0, 'test_kill_D': 0,
                'test_catch_rate': 0.0, 'test_kill_rate': 0.0,
                'test_precision_A': 0.0,
                'train_blocked_n': STAGE1_TRAIN[rule_name]['n'],
                'train_precision_A': STAGE1_TRAIN[rule_name]['n_A'] / STAGE1_TRAIN[rule_name]['n'],
                'precision_drop_pp': 0.0,
                'remaining_n': len(passed),
                'remaining_sharpe': compute_sharpe(pd.to_numeric(passed['log_return'], errors='coerce').dropna()),
                'sharpe_delta_pct': 0.0,
                'benefit_cost_ratio': None,
            })
            log(f"  {rule_name}: blocked={n_blocked} (insufficient)", 'WARN')
            continue

        n_caught_A = int((blocked['category'] == 'A').sum())
        n_blocked_B = int((blocked['category'] == 'B').sum())
        n_killed_D = int((blocked['category'] == 'D').sum())

        catch_rate = n_caught_A / max(base_test['n_A'], 1)
        kill_rate  = n_killed_D / max(base_test['n_D'], 1)
        precision_A = n_caught_A / max(n_blocked, 1)

        remaining = passed
        remaining_metrics = compute_metrics(remaining)
        sharpe_delta = (
            (remaining_metrics['sharpe'] - base_test['sharpe'])
            / max(abs(base_test['sharpe']), 1e-6) * 100
        )

        bc_ratio = benefit_cost_ratio(n_caught_A, n_blocked_B, n_killed_D)

        train_blocked_n = STAGE1_TRAIN[rule_name]['n']
        train_precision = STAGE1_TRAIN[rule_name]['n_A'] / STAGE1_TRAIN[rule_name]['n']
        precision_drop_pp = (train_precision - precision_A) * 100

        rule_results.append({
            'rule': rule_name,
            'status': 'ok',
            'blocked_n': n_blocked,
            'test_catch_A': n_caught_A,
            'test_kill_D': n_killed_D,
            'test_catch_rate': catch_rate,
            'test_kill_rate': kill_rate,
            'test_precision_A': precision_A,
            'train_blocked_n': train_blocked_n,
            'train_precision_A': train_precision,
            'precision_drop_pp': precision_drop_pp,
            'remaining_n': remaining_metrics['n'],
            'remaining_sharpe': remaining_metrics['sharpe'],
            'sharpe_delta_pct': sharpe_delta,
            'benefit_cost_ratio': bc_ratio,
        })

        log(f"  {rule_name}: "
            f"blocked={n_blocked:>4} | "
            f"catch_A={n_caught_A:>4} ({catch_rate*100:>5.1f}%) | "
            f"kill_D={n_killed_D:>3} ({kill_rate*100:>5.1f}%) | "
            f"precision_A={precision_A*100:>5.1f}% "
            f"(train={train_precision*100:.1f}%) | "
            f"Sharpe={remaining_metrics['sharpe']:.3f} "
            f"(Δ={sharpe_delta:+.0f}%) | "
            f"BC={bc_ratio:.1f}" if bc_ratio is not None else "BC=inf",
            'OK' if precision_A > 0.7 else 'WARN')

    rules_df = pd.DataFrame(rule_results)

    # ── 7. Rule combinations
    log("\n[3/4] Testing rule combinations on TEST ...", 'STEP')
    all_rules = list(RULES.keys())
    combo_results = []

    # All non-empty subsets (2^6 - 1 = 63 combos)
    for size in range(1, len(all_rules) + 1):
        for subset in combinations(all_rules, size):
            # Union of masks: block if ANY rule fires
            union_mask = pd.Series(False, index=test.index)
            for r in subset:
                union_mask = union_mask | rule_masks_test[r]

            blocked = test[union_mask]
            passed  = test[~union_mask]

            if len(blocked) < CFG['min_blocked']:
                continue
            if len(passed) < CFG['min_remaining']:
                continue

            n_caught_A = int((blocked['category'] == 'A').sum())
            n_blocked_B = int((blocked['category'] == 'B').sum())
            n_killed_D = int((blocked['category'] == 'D').sum())

            catch_rate  = n_caught_A / max(base_test['n_A'], 1)
            kill_rate   = n_killed_D / max(base_test['n_D'], 1)
            precision_A = n_caught_A / max(len(blocked), 1)

            remaining_metrics = compute_metrics(passed)
            sharpe_delta = (
                (remaining_metrics['sharpe'] - base_test['sharpe'])
                / max(abs(base_test['sharpe']), 1e-6) * 100
            )
            bc_ratio = benefit_cost_ratio(n_caught_A, n_blocked_B, n_killed_D)

            combo_results.append({
                'rules': '+'.join(subset),
                'n_rules': len(subset),
                'blocked_n': len(blocked),
                'test_catch_A': n_caught_A,
                'test_kill_D': n_killed_D,
                'test_catch_rate': catch_rate,
                'test_kill_rate': kill_rate,
                'test_precision_A': precision_A,
                'remaining_n': remaining_metrics['n'],
                'remaining_sharpe': remaining_metrics['sharpe'],
                'remaining_win_rate': remaining_metrics['win_rate'],
                'sharpe_delta_pct': sharpe_delta,
                'benefit_cost_ratio': bc_ratio,
            })

    combos_df = pd.DataFrame(combo_results)
    if len(combos_df) > 0:
        combos_df = combos_df.sort_values('remaining_sharpe', ascending=False).reset_index(drop=True)
    log(f"  Evaluated {len(combos_df)} valid combinations", 'OK')

    # ── 8. Pareto frontier (Sharpe vs remaining_n)
    pareto_rows = []
    if len(combos_df) > 0:
        sorted_by_n = combos_df.sort_values('remaining_n', ascending=False)
        best_sharpe_so_far = -np.inf
        for _, row in sorted_by_n.iterrows():
            if row['remaining_sharpe'] > best_sharpe_so_far:
                best_sharpe_so_far = row['remaining_sharpe']
                pareto_rows.append(row)
    pareto_df = pd.DataFrame(pareto_rows) if pareto_rows else pd.DataFrame()

    # ── 9. Recommendations
    log("\n[4/4] Generating recommendations ...", 'STEP')

    # Best rules by benefit/cost ratio (with min samples)
    viable = rules_df[
        (rules_df['status'] == 'ok') &
        (rules_df['blocked_n'] >= CFG['min_blocked'])
    ].copy()

    best_single = None
    best_combo = None

    if len(viable) > 0:
        best_single = viable.sort_values(
            'benefit_cost_ratio', ascending=False
        ).iloc[0]

    if len(combos_df) > 0:
        # Best combo: highest Sharpe with bc_ratio > 3
        viable_combos = combos_df[combos_df['benefit_cost_ratio'] > 3.0].copy()
        if len(viable_combos) > 0:
            best_combo = viable_combos.iloc[0]
        else:
            best_combo = combos_df.iloc[0]

    # ── 10. Write outputs
    rules_df.to_csv(os.path.join(CFG['out_dir'], 'validation_rules.csv'), index=False)
    combos_df.to_csv(os.path.join(CFG['out_dir'], 'validation_combos.csv'), index=False)
    shift_df.to_csv(os.path.join(CFG['out_dir'], 'validation_covariate_shift.csv'), index=False)
    if len(pareto_df) > 0:
        pareto_df.to_csv(os.path.join(CFG['out_dir'], 'validation_pareto.csv'), index=False)

    # ── 11. Write report
    report_path = os.path.join(CFG['out_dir'], 'validation_report.md')
    write_report(report_path, base_train, base_test, rules_df, combos_df,
                 pareto_df, shift_df, best_single, best_combo)

    # ── 12. Console summary
    print()
    print("═" * 72)
    print("  ✅ Validation complete")
    print("═" * 72)
    print(f"  Train (n={base_train['n']}, Sharpe={base_train['sharpe']:.3f})")
    print(f"  Test  (n={base_test['n']}, Sharpe={base_test['sharpe']:.3f})")
    print()
    if best_single is not None:
        print(f"  Best single rule: {best_single['rule']}")
        print(f"    Catch {best_single['test_catch_rate']*100:.1f}% of A, "
              f"Kill {best_single['test_kill_rate']*100:.1f}% of D")
        print(f"    Sharpe: {best_single['remaining_sharpe']:.3f} "
              f"({best_single['sharpe_delta_pct']:+.0f}%)")
    if best_combo is not None:
        print(f"  Best combo: {best_combo['rules']}")
        print(f"    Catch {best_combo['test_catch_rate']*100:.1f}% of A, "
              f"Kill {best_combo['test_kill_rate']*100:.1f}% of D")
        print(f"    Sharpe: {best_combo['remaining_sharpe']:.3f} "
              f"({best_combo['sharpe_delta_pct']:+.0f}%)")
    print()
    print(f"  Output: {CFG['out_dir']}/")
    print(f"    - validation_report.md")
    print(f"    - validation_rules.csv")
    print(f"    - validation_combos.csv")
    print(f"    - validation_covariate_shift.csv")
    if len(pareto_df) > 0:
        print(f"    - validation_pareto.csv")


# ═══════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════

def write_report(path, base_train, base_test, rules_df, combos_df,
                 pareto_df, shift_df, best_single, best_combo):
    lines = []
    add = lines.append

    add("# Stage 2 — Out-of-Sample Validation\n")
    add(f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")

    # Executive summary
    add("## 🎯 Executive Summary\n")
    add(f"**Baseline (no filter)**")
    add(f"- Train: n={base_train['n']}, Sharpe={base_train['sharpe']:.3f}, "
        f"WinRate={base_train['win_rate']*100:.1f}%")
    add(f"- Test:  n={base_test['n']}, Sharpe={base_test['sharpe']:.3f}, "
        f"WinRate={base_test['win_rate']*100:.1f}%")
    add("")

    if best_single is not None:
        add(f"**🏆 Best Single Rule (by benefit/cost): `{best_single['rule']}`**")
        add(f"- Catches **{best_single['test_catch_A']}** A "
            f"({best_single['test_catch_rate']*100:.1f}% of test A)")
        add(f"- Kills **{best_single['test_kill_D']}** D "
            f"({best_single['test_kill_rate']*100:.1f}% of test D)")
        add(f"- Precision-A: **{best_single['test_precision_A']*100:.1f}%** "
            f"(train was {best_single['train_precision_A']*100:.1f}%)")
        add(f"- **Sharpe: {base_test['sharpe']:.3f} → "
            f"{best_single['remaining_sharpe']:.3f}** "
            f"({best_single['sharpe_delta_pct']:+.0f}%)")
        add(f"- Benefit/cost ratio: **{best_single['benefit_cost_ratio']:.1f}x**")
        add("")

    if best_combo is not None:
        add(f"**🏆 Best Combination: `{best_combo['rules']}`**")
        add(f"- Catches **{best_combo['test_catch_A']}** A "
            f"({best_combo['test_catch_rate']*100:.1f}% of test A)")
        add(f"- Kills **{best_combo['test_kill_D']}** D "
            f"({best_combo['test_kill_rate']*100:.1f}% of test D)")
        add(f"- **Sharpe: {base_test['sharpe']:.3f} → "
            f"{best_combo['remaining_sharpe']:.3f}** "
            f"({best_combo['sharpe_delta_pct']:+.0f}%)")
        add(f"- Remaining trades: {best_combo['remaining_n']}")
        add(f"- Benefit/cost ratio: **{best_combo['benefit_cost_ratio']:.1f}x**")
        add("")

    # Covariate shift
    add("## 📊 Covariate Shift (Train vs Test)\n")
    if shift_df is not None and len(shift_df) > 0:
        drifted = shift_df[shift_df['drift'] == 'SIGNIFICANT']
        if len(drifted) > 0:
            add(f"**⚠️ {len(drifted)} features show significant distribution shift** "
                f"(KS test p<0.01). Rules depending on these features may generalize poorly.\n")
        else:
            add("**✅ No significant distribution shift detected.** "
                "Rules should generalize.\n")
        
        add("| Feature | Train mean | Test mean | KS p-value | Drift |")
        add("|---------|-----------|-----------|-----------|-------|")
        for _, r in shift_df.iterrows():
            if pd.isna(r['ks_p']):
                continue
            add(f"| `{r['feature']}` | {r['train_mean']:.4f} | "
                f"{r['test_mean']:.4f} | {r['ks_p']:.2e} | {r['drift']} |")
        add("")

    # Per-rule table
    add("## 🎯 Per-Rule Out-of-Sample Results\n")
    add("| Rule | Blocked | Caught A | Killed D | Catch% | Kill% | "
        "Precision-A | Train-P-A | Drop | Sharpe | Δ% | B/C |")
    add("|------|---------|----------|----------|--------|-------|"
        "------------|-----------|------|--------|-----|-----|")
    for _, r in rules_df.iterrows():
        if r['status'] != 'ok':
            add(f"| {r['rule']} | {r['blocked_n']} | — | — | — | — | "
                f"— | — | — | — | — | — |")
            continue
        bc = r['benefit_cost_ratio']
        bc_str = f"{bc:.1f}" if bc is not None and np.isfinite(bc) else "∞"
        add(f"| {r['rule']} | {r['blocked_n']} | {r['test_catch_A']} | "
            f"{r['test_kill_D']} | {r['test_catch_rate']*100:.1f}% | "
            f"{r['test_kill_rate']*100:.1f}% | "
            f"{r['test_precision_A']*100:.1f}% | "
            f"{r['train_precision_A']*100:.1f}% | "
            f"{r['precision_drop_pp']:+.1f}pp | "
            f"{r['remaining_sharpe']:.3f} | "
            f"{r['sharpe_delta_pct']:+.0f}% | {bc_str} |")
    add("")

    # Top combos
    add("## 🏆 Top Combinations (by Sharpe)\n")
    if combos_df is not None and len(combos_df) > 0:
        add("| Combo | Rules | Blocked | Caught A | Killed D | "
            "Sharpe | Δ% | Remaining | B/C |")
        add("|-------|-------|---------|----------|----------|"
            "--------|-----|-----------|-----|")
        top = combos_df.head(10)
        for _, r in top.iterrows():
            bc = r['benefit_cost_ratio']
            bc_str = f"{bc:.1f}" if bc is not None and np.isfinite(bc) else "∞"
            add(f"| {r['rules']} | {r['n_rules']} | {r['blocked_n']} | "
                f"{r['test_catch_A']} | {r['test_kill_D']} | "
                f"{r['remaining_sharpe']:.3f} | "
                f"{r['sharpe_delta_pct']:+.0f}% | "
                f"{r['remaining_n']} | {bc_str} |")
        add("")

    # Pareto
    add("## 📈 Pareto Frontier (Sharpe vs Throughput)\n")
    if pareto_df is not None and len(pareto_df) > 0:
        add("Optimal trade-offs between Sharpe improvement and trade count:\n")
        add("| Rules | Remaining n | Sharpe | Δ% | Blocked | Kill% | B/C |")
        add("|-------|-------------|--------|-----|---------|-------|-----|")
        for _, r in pareto_df.iterrows():
            bc = r['benefit_cost_ratio']
            bc_str = f"{bc:.1f}" if bc is not None and np.isfinite(bc) else "∞"
            add(f"| {r['rules']} | {r['remaining_n']} | "
                f"{r['remaining_sharpe']:.3f} | "
                f"{r['sharpe_delta_pct']:+.0f}% | "
                f"{r['blocked_n']} | {r['test_kill_rate']*100:.1f}% | {bc_str} |")
        add("")

    # Recommendations
    add("## 🎯 Recommendations for Stage 3\n")
    recs = []

    if best_single is not None and best_single['benefit_cost_ratio'] > 5.0:
        recs.append(
            f"1. **Adopt Rule {best_single['rule']}** as pre-entry filter. "
            f"B/C={best_single['benefit_cost_ratio']:.1f}x, "
            f"kills only {best_single['test_kill_D']} winners in test."
        )

    if best_combo is not None and best_combo['benefit_cost_ratio'] > 3.0:
        recs.append(
            f"2. **Consider combo {best_combo['rules']}** if willing to lose "
            f"{best_combo['remaining_n']} trades ({best_combo['blocked_n']} blocked) "
            f"for Sharpe {best_combo['remaining_sharpe']:.3f}."
        )

    if len(shift_df) > 0:
        drifted = shift_df[shift_df['drift'] == 'SIGNIFICANT']
        if len(drifted) > 0:
            drifted_feats = ', '.join(f"`{x}`" for x in drifted['feature'].tolist())
            recs.append(
                f"3. **⚠️ Covariate shift detected** in {drifted_feats}. "
                f"Consider re-training on more recent data or excluding rules "
                f"depending on these features."
            )

    if not recs:
        recs.append("**No strong generalization confirmed.** Rules may be overfit. "
                    "Consider collecting more data or re-training.")

    for r in recs:
        add(r)
    add("")

    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    log(f"Report: {path}", 'OK')


if __name__ == '__main__':
    main()
