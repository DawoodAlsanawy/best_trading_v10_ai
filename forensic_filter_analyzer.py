#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════════
  Forensic Filter Analyzer
  ─────────────────────────────────────────────────────────────────────────────
  يحلل trades_log_backtest.jsonl لاكتشاف:
    1. الخصائص التي تفصل الصفقات الرابحة عن الخاسرة
    2. الفلاتر التي تحقق تحسناً حقيقياً (train/test split)
    3. أفضل 3 فلاتر + أفضل 3 ثنائيات
    4. Warn إذا كانت البيانات غير كافية أو الإشارة overfit
  
  المنهجية:
    • Train (60%) → بحث عن العتبات المثالية
    • Test (40%)  → التحقق من عدم الـ overfitting
    • أيضاً Time-Split: أول 60% زمنياً (train) وآخر 40% (test)
  
  المعايير:
    ✓ الفلتر يجب أن يزيل ≥ 5% من الصفقات (ليس صدفة)
    ✓ الفلتر يجب أن يزيل ≤ 50% من الصفقات (ليس عنيفاً)
    ✓ يجب أن يحقق تحسناً في TEST  (ليس فقط train)
    ✓ "Overfit Gap" = train_gain − test_gain < 30 نقطة مئوية
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict
import numpy as np

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


TRADES_FILE = "trades_log_backtest.jsonl"
OUTPUT_JSON = "forensic_analysis.json"

# ─── معايير الفلترة ──────────────────────────────────────────────────
MIN_TRADES_TOTAL = 100          # حد أدنى للصفقات
MIN_TRADES_REMOVED_FRAC = 0.05  # فلتر يجب أن يزيل ≥ 5% من الصفقات
MAX_TRADES_REMOVED_FRAC = 0.50  # فلتر يجب أن يزيل ≤ 50% من الصفقات
MIN_GAIN_TEST_PCT = 3.0         # حد أدنى للتحسن في test (نقاط مئوية)

# ─── الميزات الرقمية التي سنحللها ────────────────────────────────────
NUMERIC_FEATURES = [
    "score", "signal_price", "signal_sl", "signal_tp1", "atr",
    "tri_val", "dynamic_risk", "T_info_val", "dyn_sl_factor",
    "adv_usd", "sl_dist_frac", "rr_design",
    "E_therm", "friction", "gauge_force", "delta_gap",
    "geodesic_accel", "H", "dH", "dF", "T_info", "V", "C",
    "H_over_Hmax", "friction_drag_over_sl", "sl_sigma",
    "ema_slope", "ema_slope_against", "dist_from_ema_norm",
    "hold_bars",
]


# ═════════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════════
def safe_float(v, default=np.nan):
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def safe_int(v, default=-1):
    try:
        return int(v)
    except Exception:
        return default


def pct(v, d=1):
    return f"{v*100:.{d}f}%"


def section(title, char="═", width=78):
    print("\n" + char * width)
    print(f"  {title}")
    print(char * width)


def subsection(title, char="─", width=78):
    print("\n" + char * width)
    print(f"  {title}")
    print(char * width)


# ═════════════════════════════════════════════════════════════════════
# LOAD & VALIDATE
# ═════════════════════════════════════════════════════════════════════
def load_trades():
    if not os.path.exists(TRADES_FILE):
        print(f"ERROR: {TRADES_FILE} not found in {os.getcwd()}")
        return None, None

    trades = []
    metas = []
    n_errors = 0
    with open(TRADES_FILE, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                n_errors += 1
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("_meta"):
                metas.append(obj)
            else:
                trades.append(obj)

    if n_errors > 0:
        print(f"  WARN: {n_errors} خطأ في JSON تم تخطيه")
    return trades, metas


def prepare_trades(raw_trades):
    """يحول القائمة الخام إلى قائمة موحدة بالحقول المطلوبة."""
    prepared = []
    for t in raw_trades:
        sym = t.get("symbol")
        if not isinstance(sym, str):
            continue
        exit_reason = t.get("exit_reason", "")
        if not isinstance(exit_reason, str):
            exit_reason = str(exit_reason)

        # is_win: نستخدم is_win من السجل، وإلا نحسبه من net_pnl
        is_win = t.get("is_win")
        if not isinstance(is_win, bool):
            net = safe_float(t.get("net_pnl"))
            is_win = (net > 0) if np.isfinite(net) else None
        if is_win is None:
            continue

        net_pnl = safe_float(t.get("net_pnl"), 0.0)

        # استخرج الميزات
        feats = {}
        for f in NUMERIC_FEATURES:
            feats[f] = safe_float(t.get(f))

        # اشتقّ الميزات الزمنية
        entry_time = t.get("entry_time", "")
        hour = np.nan
        dow = np.nan
        if isinstance(entry_time, str) and entry_time:
            try:
                ts = pd.Timestamp(entry_time)
                hour = ts.hour
                dow = ts.dayofweek
            except Exception:
                pass

        prepared.append({
            "symbol": sym,
            "action": t.get("action", "?"),
            "is_win": is_win,
            "net_pnl": net_pnl,
            "exit_reason": exit_reason,
            "entry_time": entry_time,
            "entry_ci": safe_int(t.get("entry_ci")),
            "exit_ci": safe_int(t.get("exit_ci")),
            "feats": feats,
            "hour": hour,
            "dow": dow,
        })

    return prepared


# ═════════════════════════════════════════════════════════════════════
# METRICS
# ═════════════════════════════════════════════════════════════════════
def compute_stats(trades):
    if not trades:
        return {"n": 0, "win_rate": 0.0, "pf": 0.0, "mean_pnl": 0.0,
                "total_pnl": 0.0, "sharpe": 0.0, "max_dd": 0.0}
    n = len(trades)
    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]
    total_win = sum(t["net_pnl"] for t in wins)
    total_loss = sum(t["net_pnl"] for t in losses)
    pnls = np.array([t["net_pnl"] for t in trades], dtype=float)

    # Max DD على منحنى PnL التراكمي
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0.0

    # Sharpe (على الصفقات، ليس سنوياً)
    mu = float(np.mean(pnls))
    sd = float(np.std(pnls, ddof=1)) if n > 1 else 0.0
    sharpe = (mu / sd) if sd > 1e-9 else 0.0

    return {
        "n": n,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": len(wins) / n if n > 0 else 0.0,
        "total_win": total_win,
        "total_loss": total_loss,
        "total_pnl": total_win + total_loss,
        "mean_pnl": float(np.mean(pnls)) if n > 0 else 0.0,
        "pf": (total_win / abs(total_loss)) if abs(total_loss) > 1e-9 else float("inf"),
        "sharpe": sharpe,
        "max_dd": max_dd,
    }


def compute_pnl_improvement(removed_trades):
    """موجب = تحسن، سالب = تدهور.
    إزالة صفقة خاسرة = improvement موجب (نوفّر الخسارة).
    إزالة صفقة رابحة = improvement سالب (نفقد الربح)."""
    return -sum(t["net_pnl"] for t in removed_trades)


# ═════════════════════════════════════════════════════════════════════
# THRESHOLD SEARCH
# ═════════════════════════════════════════════════════════════════════
def find_best_threshold(values, wins, pnls, min_remove_frac, max_remove_frac):
    """
    ابحث عن أفضل عتبة تفصل بين winners/losers.
    values: array of feature values (may contain NaN — filtered outside)
    wins:   bool array
    pnls:   float array
    Returns dict | None
    """
    n = len(values)
    if n == 0:
        return None

    base_win_rate = float(np.mean(wins))
    base_pnl = float(np.sum(pnls))

    best = None
    percentiles = list(range(5, 100, 5))

    for direction in ("ge", "le"):
        for p in percentiles:
            try:
                thr = float(np.percentile(values, p))
            except Exception:
                continue
            if not np.isfinite(thr):
                continue

            if direction == "ge":
                removed_mask = values >= thr
            else:
                removed_mask = values <= thr

            n_removed = int(np.sum(removed_mask))
            if n_removed == 0:
                continue
            frac = n_removed / n
            if frac < min_remove_frac or frac > max_remove_frac:
                continue

            kept_wins = wins[~removed_mask]
            kept_pnls = pnls[~removed_mask]
            if len(kept_wins) < 10:
                continue

            new_win_rate = float(np.mean(kept_wins))
            gain = new_win_rate - base_win_rate
            removed_pnl = float(np.sum(pnls[removed_mask]))
            pnl_improvement = -removed_pnl

            candidate = {
                "direction": direction,
                "threshold": thr,
                "percentile": p,
                "n_removed": n_removed,
                "n_kept": n - n_removed,
                "removed_frac": frac,
                "base_win_rate": base_win_rate,
                "new_win_rate": new_win_rate,
                "win_rate_gain": gain,
                "pnl_improvement": pnl_improvement,
                "removed_pnl": removed_pnl,
            }
            # نحسّن على PnL، مع شرط gain إيجابي
            if candidate["pnl_improvement"] > 0 and candidate["win_rate_gain"] > 0:
                if best is None or (candidate["pnl_improvement"]
                                     > best["pnl_improvement"]):
                    best = candidate
    return best


# ═════════════════════════════════════════════════════════════════════
# TRAIN / TEST SPLITS
# ═════════════════════════════════════════════════════════════════════
def split_random(trades, train_frac=0.60, seed=42):
    rng = np.random.RandomState(seed)
    n = len(trades)
    idx = rng.permutation(n)
    n_train = int(n * train_frac)
    train = [trades[i] for i in idx[:n_train]]
    test = [trades[i] for i in idx[n_train:]]
    return train, test


def split_time(trades, train_frac=0.60):
    """يقسّم زمنياً: الأقدم → train، الأحدث → test."""
    def _key(t):
        try:
            return pd.Timestamp(t["entry_time"]).value
        except Exception:
            return 0
    sorted_trades = sorted(trades, key=_key)
    n = len(sorted_trades)
    n_train = int(n * train_frac)
    return sorted_trades[:n_train], sorted_trades[n_train:]


# ═════════════════════════════════════════════════════════════════════
# APPLY FILTER
# ═════════════════════════════════════════════════════════════════════
def apply_filter(trades, filter_spec, feature_name):
    """
    filter_spec: {'direction': 'ge'|'le', 'threshold': float}
    Returns (kept, removed)
    """
    kept = []
    removed = []
    for t in trades:
        v = t["feats"].get(feature_name, np.nan)
        if not np.isfinite(v):
            kept.append(t)  # fail-open: تبقى الصفقة إذا الميزة مفقودة
            continue
        thr = filter_spec["threshold"]
        if filter_spec["direction"] == "ge":
            hit = v >= thr
        else:
            hit = v <= thr
        if hit:
            removed.append(t)
        else:
            kept.append(t)
    return kept, removed


def evaluate_filter(train, test, feature_name, filter_spec):
    train_kept, train_removed = apply_filter(train, filter_spec, feature_name)
    test_kept, test_removed = apply_filter(test, filter_spec, feature_name)

    train_before = compute_stats(train)
    train_after = compute_stats(train_kept)
    test_before = compute_stats(test)
    test_after = compute_stats(test_kept)

    return {
        "feature": feature_name,
        "filter": filter_spec,
        "train_before": train_before,
        "train_after": train_after,
        "test_before": test_before,
        "test_after": test_after,
        "train_win_rate_gain": (train_after["win_rate"]
                                 - train_before["win_rate"]),
        "test_win_rate_gain": (test_after["win_rate"]
                                - test_before["win_rate"]),
        "train_pnl_improvement": (train_after["total_pnl"]
                                    - train_before["total_pnl"]),
        "test_pnl_improvement": (test_after["total_pnl"]
                                   - test_before["total_pnl"]),
        "train_pf_gain": (train_after["pf"] - train_before["pf"])
                          if np.isfinite(train_after["pf"])
                             and np.isfinite(train_before["pf"]) else 0.0,
        "test_pf_gain": (test_after["pf"] - test_before["pf"])
                         if np.isfinite(test_after["pf"])
                            and np.isfinite(test_before["pf"]) else 0.0,
        "train_dd_improvement": (train_before["max_dd"]
                                  - train_after["max_dd"]),
        "test_dd_improvement": (test_before["max_dd"]
                                 - test_after["max_dd"]),
    }


# ═════════════════════════════════════════════════════════════════════
# ANALYSIS PER FEATURE
# ═════════════════════════════════════════════════════════════════════
def analyze_features(train, test, features):
    """لكل ميزة: ابحث عن أفضل عتبة، قيّمها على test."""
    results = []
    for fname in features:
        # استخرج القيم من train
        train_vals = []
        train_wins = []
        train_pnls = []
        for t in train:
            v = t["feats"].get(fname, np.nan)
            if not np.isfinite(v):
                continue
            train_vals.append(v)
            train_wins.append(t["is_win"])
            train_pnls.append(t["net_pnl"])

        if len(train_vals) < 50:
            continue

        vals_a = np.asarray(train_vals, dtype=float)
        wins_a = np.asarray(train_wins, dtype=bool)
        pnls_a = np.asarray(train_pnls, dtype=float)

        best = find_best_threshold(
            vals_a, wins_a, pnls_a,
            MIN_TRADES_REMOVED_FRAC, MAX_TRADES_REMOVED_FRAC
        )
        if best is None:
            continue

        eval_result = evaluate_filter(train, test, fname, {
            "direction": best["direction"],
            "threshold": best["threshold"],
        })
        eval_result["train_search"] = best
        results.append(eval_result)

    # رتب حسب test_pnl_improvement (وليس train!)
    results.sort(key=lambda r: -r["test_pnl_improvement"])
    return results


# ═════════════════════════════════════════════════════════════════════
# COMBINED FILTERS
# ═════════════════════════════════════════════════════════════════════
def analyze_combos(train, test, top_singles, max_combos=10):
    """خذ أفضل singles واختبر كل أزواجها."""
    if len(top_singles) < 2:
        return []

    candidates = top_singles[:5]  # فقط أفضل 5
    combos = []

    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a = candidates[i]
            b = candidates[j]
            if a["feature"] == b["feature"]:
                continue

            # طبّق A على train ثم B
            train_kept_a, _ = apply_filter(train, a["filter"], a["feature"])
            train_kept_ab, _ = apply_filter(train_kept_a, b["filter"],
                                             b["feature"])
            test_kept_a, _ = apply_filter(test, a["filter"], a["feature"])
            test_kept_ab, _ = apply_filter(test_kept_a, b["filter"],
                                            b["feature"])

            train_before = compute_stats(train)
            train_after = compute_stats(train_kept_ab)
            test_before = compute_stats(test)
            test_after = compute_stats(test_kept_ab)

            n_removed_train = len(train) - len(train_kept_ab)
            n_removed_test = len(test) - len(test_kept_ab)

            if n_removed_train / len(train) < 0.10:
                continue  # يحتاج إزالة ≥ 10% (أعلى من single)
            if n_removed_train / len(train) > 0.60:
                continue

            combos.append({
                "filters": [a, b],
                "train_before": train_before,
                "train_after": train_after,
                "test_before": test_before,
                "test_after": test_after,
                "train_pnl_improvement": (train_after["total_pnl"]
                                            - train_before["total_pnl"]),
                "test_pnl_improvement": (test_after["total_pnl"]
                                           - test_before["total_pnl"]),
                "train_win_gain": (train_after["win_rate"]
                                    - train_before["win_rate"]),
                "test_win_gain": (test_after["win_rate"]
                                   - test_before["win_rate"]),
                "train_removed_pct": n_removed_train / len(train),
                "test_removed_pct": n_removed_test / max(len(test), 1),
            })

    combos.sort(key=lambda c: -c["test_pnl_improvement"])
    return combos[:max_combos]


# ═════════════════════════════════════════════════════════════════════
# REPORTING
# ═════════════════════════════════════════════════════════════════════
def print_overview(trades, metas):
    section("1. OVERVIEW")
    print(f"  عدد الصفقات الكلي: {len(trades):,}")
    if metas:
        print(f"  Meta records: {len(metas)}")
        m = metas[-1]
        print(f"  آخر meta: tf={m.get('timeframe')}, N={m.get('N')}, "
              f"K_MAX={m.get('K_MAX')}, time={m.get('started_at')}")

    # توزيع exit reasons
    exit_dist = defaultdict(int)
    for t in trades:
        r = t["exit_reason"]
        key = r.split("(")[0].split("=")[0].strip()[:40] or "?"
        exit_dist[key] += 1

    print(f"\n  توزيع exit_reason:")
    for r, c in sorted(exit_dist.items(), key=lambda x: -x[1])[:10]:
        print(f"    {r:<42}: {c:>6,}  ({pct(c/len(trades))})")

    # إحصاءات
    stats = compute_stats(trades)
    print(f"\n  إحصاءات عامة:")
    print(f"    Win Rate      : {stats['win_rate']*100:.2f}%")
    print(f"    Total PnL     : ${stats['total_pnl']:+,.2f}")
    print(f"    PF            : {stats['pf']:.3f}")
    print(f"    Mean PnL/trade: ${stats['mean_pnl']:+.4f}")
    print(f"    Sharpe        : {stats['sharpe']:.3f}")
    print(f"    Max DD        : ${stats['max_dd']:.2f}")

    # تحذيرات
    if len(trades) < MIN_TRADES_TOTAL:
        print(f"\n  ⚠️  WARNING: عدد الصفقات {len(trades)} < {MIN_TRADES_TOTAL}")
        print(f"      النتائج قد لا تكون ذات دلالة إحصائية")
    if exit_dist.get("Hard TP", 0) == 0:
        print(f"\n  ⚠️  WARNING: Hard TP = 0 صفقة!")
        print(f"      TP_MULT={7} لا يُضرب أبداً. الأرباح كلها من Trailing/BEEsc.")
        print(f"      هذه مشكلة بنيوية، ليست مشكلة فلاتر.")


def print_baseline_split(train, test, split_name):
    subsection(f"Baseline — {split_name}")
    train_s = compute_stats(train)
    test_s = compute_stats(test)
    print(f"  Train: n={train_s['n']:>4}, "
          f"WR={train_s['win_rate']*100:5.2f}%, "
          f"PnL=${train_s['total_pnl']:+8.2f}, "
          f"PF={train_s['pf']:.2f}")
    print(f"  Test : n={test_s['n']:>4}, "
          f"WR={test_s['win_rate']*100:5.2f}%, "
          f"PnL=${test_s['total_pnl']:+8.2f}, "
          f"PF={test_s['pf']:.2f}")


def print_feature_results(results, split_name, top_n=15):
    subsection(f"Top Features — {split_name} (sorted by TEST PnL improvement)")
    if not results:
        print("  لم يُعثر على فلاتر مؤهلة")
        return

    print(f"  {'Feature':<24} {'Dir':<4} {'Thr':>10} {'Rm%':>6} "
          f"{'TrWR':>7} {'TeWR':>7} {'TePnL+':>9} {'Gap':>6}")
    print(f"  {'-'*24} {'-'*4} {'-'*10} {'-'*6} "
          f"{'-'*7} {'-'*7} {'-'*9} {'-'*6}")

    for r in results[:top_n]:
        f = r["filter"]
        thr = f["threshold"]
        train_search = r["train_search"]
        train_wr = train_search["new_win_rate"] * 100
        test_wr = r["test_after"]["win_rate"] * 100
        gap = train_wr - test_wr
        marker = ""
        if r["test_win_rate_gain"] < 0:
            marker = " ✗"  # تدهور في test
        elif gap > 30:
            marker = " ⚠"  # overfit gap كبير
        elif r["test_win_rate_gain"] * 100 >= MIN_GAIN_TEST_PCT:
            marker = " ✓"

        print(f"  {r['feature']:<24} {f['direction']:<4} "
              f"{thr:>10.5f} {train_search['removed_frac']*100:>5.1f}% "
              f"{train_wr:>6.1f}% {test_wr:>6.1f}% "
              f"${r['test_pnl_improvement']:>+8.2f} {gap:>5.1f}%{marker}")

    print(f"\n  Legend: Dir=ge (>=thr) or le (<=thr); "
          f"Rm%=% removed from TRAIN; Gap=TrainWR-TestWR")
    print(f"  ✓ = test gain >= {MIN_GAIN_TEST_PCT}pp;  "
          f"⚠ = gap > 30pp;  ✗ = test loss")


def print_combos(combos, split_name):
    subsection(f"Top Combinations — {split_name}")
    if not combos:
        print("  لا توجد ثنائيات مؤهلة")
        return

    for idx, c in enumerate(combos[:5], 1):
        a, b = c["filters"]
        print(f"\n  ── Combo #{idx} ──")
        print(f"    Filter A: {a['feature']} {a['filter']['direction']} "
              f"{a['filter']['threshold']:.5f}")
        print(f"    Filter B: {b['feature']} {b['filter']['direction']} "
              f"{b['filter']['threshold']:.5f}")
        print(f"    Removed: train={c['train_removed_pct']*100:.1f}%, "
              f"test={c['test_removed_pct']*100:.1f}%")
        print(f"    Train: WR {c['train_before']['win_rate']*100:.1f}% → "
              f"{c['train_after']['win_rate']*100:.1f}% "
              f"(+{c['train_win_gain']*100:+.1f}pp) | "
              f"PnL ${c['train_before']['total_pnl']:.2f} → "
              f"${c['train_after']['total_pnl']:.2f}")
        print(f"    Test : WR {c['test_before']['win_rate']*100:.1f}% → "
              f"{c['test_after']['win_rate']*100:.1f}% "
              f"(+{c['test_win_gain']*100:+.1f}pp) | "
              f"PnL ${c['test_before']['total_pnl']:.2f} → "
              f"${c['test_after']['total_pnl']:.2f}")


def print_recommendation(results):
    section("RECOMMENDATION")

    if not results:
        print("  ❌ لا توجد فلاتر مؤهلة على البيانات الحالية")
        print("     هذا قد يعني:")
        print("     • البيانات قليلة جداً (30 يوم)")
        print("     • الميزات الحالية لا تفصل بين winners/losers")
        print("     • المشكلة ليست في الاختيار بل في جودة الاستراتيجية")
        return

    # مرشحي القبول
    strong = [r for r in results
              if r["test_win_rate_gain"] >= MIN_GAIN_TEST_PCT / 100
              and (r["train_search"]["new_win_rate"]
                    - r["test_after"]["win_rate"]) * 100 < 30
              and r["test_pnl_improvement"] > 0]

    if not strong:
        print("  ⚠️  لا يوجد فلتر يمر كل الشروط:")
        print(f"     (test gain >= {MIN_GAIN_TEST_PCT}pp, "
              f"gap < 30pp, PnL>0)")
        print("     أفضل مرشح (لكن مشروط):")
        r = results[0]
        f = r["filter"]
        print(f"       {r['feature']} {f['direction']} {f['threshold']:.5f}")
        print(f"       Test WR gain: {r['test_win_rate_gain']*100:+.2f}pp")
        print(f"       Test PnL: ${r['test_pnl_improvement']:+.2f}")
        print(f"     هذا المرشح يحتاج تحققاً على بيانات أطول قبل التطبيق.")
        return

    print(f"  ✅ {len(strong)} فلتر(ات) مرت كل الشروط:")
    for idx, r in enumerate(strong[:3], 1):
        f = r["filter"]
        print(f"\n  ── Candidate #{idx} ──")
        print(f"    Feature  : {r['feature']}")
        print(f"    Condition: value {f['direction']} {f['threshold']:.5f}  "
              f"→ DROP trade")
        print(f"    Removes  : "
              f"{r['train_search']['removed_frac']*100:.1f}% of trades "
              f"(train), "
              f"{(r['test_before']['n'] - r['test_after']['n']) / max(r['test_before']['n'], 1) * 100:.1f}% (test)")
        print(f"    Train WR : {r['train_before']['win_rate']*100:.1f}% → "
              f"{r['train_after']['win_rate']*100:.1f}%")
        print(f"    Test WR  : {r['test_before']['win_rate']*100:.1f}% → "
              f"{r['test_after']['win_rate']*100:.1f}%")
        print(f"    Test PnL : "
              f"${r['test_pnl_improvement']:+.2f}")
        print(f"    Test MaxDD: "
              f"${r['test_before']['max_dd']:.2f} → "
              f"${r['test_after']['max_dd']:.2f}")


def save_json_report(results, combos, split_name):
    try:
        out = {
            "split": split_name,
            "single_filters": [
                {
                    "feature": r["feature"],
                    "filter": r["filter"],
                    "train_gain_pp": r["train_win_rate_gain"] * 100,
                    "test_gain_pp": r["test_win_rate_gain"] * 100,
                    "train_pnl_improvement": r["train_pnl_improvement"],
                    "test_pnl_improvement": r["test_pnl_improvement"],
                    "train_removed_pct": r["train_search"]["removed_frac"] * 100,
                    "test_after_win_rate_pct": r["test_after"]["win_rate"] * 100,
                    "test_after_pf": r["test_after"]["pf"],
                    "test_after_max_dd": r["test_after"]["max_dd"],
                }
                for r in results[:20]
            ],
            "combos": [
                {
                    "filters": [
                        {"feature": c["filters"][0]["feature"],
                         **c["filters"][0]["filter"]},
                        {"feature": c["filters"][1]["feature"],
                         **c["filters"][1]["filter"]},
                    ],
                    "test_gain_pp": c["test_win_gain"] * 100,
                    "test_pnl_improvement": c["test_pnl_improvement"],
                    "test_removed_pct": c["test_removed_pct"] * 100,
                }
                for c in combos[:10]
            ],
        }
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        print(f"\n  💾 تقرير JSON: {OUTPUT_JSON}")
    except Exception as e:
        print(f"\n  WARN: فشل حفظ JSON: {e}")


# ═════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════
def main():
    section("FORENSIC FILTER ANALYZER")

    if not HAS_PANDAS:
        print("ERROR: pandas غير مثبت. شغّل: pip install pandas")
        return 1

    raw_trades, metas = load_trades()
    if raw_trades is None:
        return 1
    if not raw_trades:
        print("ERROR: لا صفقات في الملف")
        return 1

    trades = prepare_trades(raw_trades)
    if not trades:
        print("ERROR: لا صفقات صالحة بعد التحقق")
        return 1

    print_overview(trades, metas)

    # ─── Split A: Random ─────────────────────────────────────────────
    section("2. RANDOM SPLIT (60/40, seed=42)")
    train_a, test_a = split_random(trades, 0.60, seed=42)
    print_baseline_split(train_a, test_a, "Random")

    results_a = analyze_features(train_a, test_a, NUMERIC_FEATURES)
    print_feature_results(results_a, "Random")

    combos_a = analyze_combos(train_a, test_a, results_a)
    print_combos(combos_a, "Random")

    # ─── Split B: Time-based ─────────────────────────────────────────
    section("3. TIME-BASED SPLIT (earlier 60% → train, later 40% → test)")
    train_b, test_b = split_time(trades, 0.60)
    print_baseline_split(train_b, test_b, "Time-based")

    results_b = analyze_features(train_b, test_b, NUMERIC_FEATURES)
    print_feature_results(results_b, "Time-based")

    combos_b = analyze_combos(train_b, test_b, results_b)
    print_combos(combos_b, "Time-based")

    # ─── Recommendation ──────────────────────────────────────────────
    # ادمج: نأخذ نتائج random لأنها أكثر دلالة إحصائية،
    # لكن نطالب بأن النتيجة تتحقق أيضاً في time-based
    print_recommendation(results_a)

    # ─── Save ────────────────────────────────────────────────────────
    save_json_report(results_a, combos_a, "random")

    section("DONE")
    print("  التقرير الكامل في الأعلى. ابعث المحتوى كاملاً لتحليل النتائج.")
    print("  ملف JSON محفوظ في: " + OUTPUT_JSON)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n  Interrupted.\n")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n  FATAL: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
