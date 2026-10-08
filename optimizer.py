#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
optimizer.py — Multi-Stage Hyperparameter Optimizer
===================================================
يُحسّن معاملات بوت التداول عبر 4 مراحل:
    1. LHS Screening (تغطية شاملة سريعة)
    2. Bayesian Optimization (GP + Expected Improvement)
    3. Local Refinement (Powell)
    4. Walk-Forward Validation (robustness check)

الاستخدام:
    python optimizer.py --bot-file trading_2_complete4.py \\
                        --n-assets 8 --workers 4 \\
                        --stage1-samples 100 --stage2-iter 100

    # تخطي مراحل معينة (لاختبار سريع)
    python optimizer.py --skip-stage3 --skip-stage4 --stage1-samples 20
"""

import argparse
import copy
import importlib.util
import json
import os
import sys
import time
import traceback
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import multiprocessing as mp
import numpy as np

warnings.filterwarnings("ignore")

# ── Dependencies ──
try:
    from scipy.stats import qmc, norm
    from scipy.optimize import minimize
except ImportError:
    print("ERROR: pip install scipy")
    sys.exit(1)

try:
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel, Matern
except ImportError:
    print("ERROR: pip install scikit-learn")
    sys.exit(1)

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False
    def tqdm(x, **kw): return x


# ═══════════════════════════════════════════════════════════════════════
# 1. PARAMETER SPACE — 10 أبعاد للتحسين
# ═══════════════════════════════════════════════════════════════════════

PARAM_SPACE = {
    # name:                     (min,    max,   type)
    "WATCH_OFFSET_VOL_KAPPA": (0.005,  0.050, "float"),
    "PO_PENETRATION_BPS":     (0.3,    5.0,   "float"),
    "FRICTION_DIP_KAPPA":     (2.0,    8.0,   "float"),
    "PO_MAX_DRIFT_BPS":       (2.0,   10.0,   "float"),
    "SL_MIN_SIGMA":           (2.0,    6.0,   "float"),
    "SL_REF_KAPPA":           (0.5,    1.5,   "float"),
    "SL_WIDEN_MULT":          (1.0,    2.5,   "float"),
    "TP_MULT":                (2.0,    8.0,   "float"),
    "PARTIAL_TP_R":           (1.0,    3.0,   "float"),
    "PARTIAL_TP_PCT":         (0.30,   0.70,  "float"),
}
PARAM_NAMES = list(PARAM_SPACE.keys())
N_PARAMS = len(PARAM_NAMES)
PARAM_LOWER = np.array([PARAM_SPACE[k][0] for k in PARAM_NAMES])
PARAM_UPPER = np.array([PARAM_SPACE[k][1] for k in PARAM_NAMES])


def arr_to_params(x: np.ndarray) -> Dict[str, float]:
    return {name: float(x[i]) for i, name in enumerate(PARAM_NAMES)}


def params_to_arr(p: Dict[str, float]) -> np.ndarray:
    return np.array([p[name] for name in PARAM_NAMES], dtype=np.float64)


# ═══════════════════════════════════════════════════════════════════════
# 2. FIXED CONFIG (لا تُحسَّن)
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_FIXED = {
    "mode": "backtest",
    "PARALLEL_PROCESSING": False,     # تجنّب nested pools
    "SUBBARS_ENABLED": False,          # أسرع
    "GAUGE_FILTER_ENABLED": True,
    "GAUGE_DISABLE_SELL": True,
    "SELL_ENABLED": False,
    "TRAIL_ENABLED": True,
    "PARTIAL_TP_ENABLED": True,
    "APEX_ENABLED": True,
    "BUDGET_ENABLED": True,
    "LIQ_ENABLED": True,
    "PROTECTIVE_ORDERS_ENABLED": False,  # لا معنى في backtest
    "PO_FIXED_PRICE": False,              # نُحسّن لـ --no-fixed-price
    "UNIFIED_ENTRY_ENABLED": True,
}


# ═══════════════════════════════════════════════════════════════════════
# 3. WORKER — يعمل في subprocess
# ═══════════════════════════════════════════════════════════════════════

_WORKER_BOT = None
_WORKER_INITIAL_CFG = None
_WORKER_LOG_DIR = None


def _worker_init(bot_dir: str, bot_file: str, log_dir: str):
    """تُنفَّذ مرة واحدة في كل worker عند بدء الـ pool."""
    global _WORKER_BOT, _WORKER_INITIAL_CFG, _WORKER_LOG_DIR

    try:
        # عزل cwd داخل الـ worker
        bot_dir_abs = os.path.abspath(bot_dir)
        os.chdir(bot_dir_abs)

        # Import the bot module
        module_name = Path(bot_file).stem
        spec = importlib.util.spec_from_file_location(
            module_name, os.path.join(bot_dir_abs, bot_file)
        )
        bot = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = bot
        spec.loader.exec_module(bot)

        # Warmup numba
        try:
            bot._warmup_numba_kernels()
        except Exception:
            pass

        # Silence plot + logger
        try:
            bot.plot_results = lambda *a, **kw: None
        except Exception:
            pass
        import logging
        logging.getLogger("QTT6").setLevel(logging.CRITICAL)

        # احسب TF params (لا تُنفَّذ عند import)
        try:
            import ccxt
            _probe = ccxt.binance()
            bot.CFG.TF_SCALE, bot.CFG.TF_SECONDS, bot.CFG.TF_HOURS = \
                bot.compute_tf_scale(_probe, bot.CFG.timeframe)
        except Exception:
            pass

        # Snapshot CFG
        _WORKER_INITIAL_CFG = copy.deepcopy(dict(bot.CFG.__dict__))
        _WORKER_BOT = bot
        _WORKER_LOG_DIR = log_dir

    except Exception as e:
        print(f"[Worker Init] FATAL: {e}", flush=True)
        traceback.print_exc()
        _WORKER_BOT = None


def _evaluate_one(args: Dict) -> Dict:
    """تقييم معاملات واحدة — تعمل في subprocess."""
    if _WORKER_BOT is None:
        return {"error": "worker_not_initialized",
                "objective": -100.0, "n_trades": 0}

    run_id = args["run_id"]
    params = args["params"]
    config = args["config"]
    log_dir = args.get("log_dir") or _WORKER_LOG_DIR or "."
    log_path = os.path.join(log_dir, f"trades_{run_id}.jsonl")

    try:
        # 1. Reset CFG
        for k, v in _WORKER_INITIAL_CFG.items():
            try:
                setattr(_WORKER_BOT.CFG, k, v)
            except Exception:
                pass

        # 2. Apply config overrides
        for k, v in config.items():
            if k.startswith("_"):
                continue
            try:
                setattr(_WORKER_BOT.CFG, k, v)
            except Exception:
                pass

        # 3. Apply params
        for k, v in params.items():
            try:
                setattr(_WORKER_BOT.CFG, k, v)
            except Exception:
                pass

        _WORKER_BOT.CFG.mode = "backtest"

        # 4. Clean log
        if os.path.exists(log_path):
            os.remove(log_path)

        try:
            _WORKER_BOT._trade_log_init("backtest", log_path)
        except Exception:
            pass

        # 5. Suppress stdout
        import io
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()

        t0 = time.time()
        try:
            _WORKER_BOT.run_backtest(_WORKER_BOT.CFG)
        finally:
            sys.stdout = old_stdout
        duration = time.time() - t0

        # 6. Read trades
        trades = []
        if os.path.exists(log_path):
            with open(log_path) as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if rec.get("_meta"):
                        continue
                    trades.append(rec)
            try:
                os.remove(log_path)
            except Exception:
                pass

        # 7. Compute metrics
        metrics = _compute_metrics(trades)
        metrics["run_id"] = run_id
        metrics["params"] = params
        metrics["config"] = config
        metrics["duration_s"] = duration
        metrics["objective"] = _objective(metrics, config)
        return metrics

    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc()[:1500],
            "run_id": run_id,
            "params": params,
            "n_trades": 0,
            "objective": -100.0,
        }


# ═══════════════════════════════════════════════════════════════════════
# 4. METRICS + OBJECTIVE
# ═══════════════════════════════════════════════════════════════════════

def _compute_metrics(trades: List[Dict]) -> Dict:
    n = len(trades)
    if n == 0:
        return {"n_trades": 0, "mean_lr": 0.0, "std_lr": 0.0,
                "sharpe": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
                "max_dd": 0.0, "sum_pnl": 0.0, "exit_dist": {}}

    pnls = np.array([float(t.get("net_pnl", 0.0)) for t in trades])
    lrs = np.array([float(t.get("log_return", 0.0)) for t in trades])

    mean_lr = float(np.mean(lrs))
    std_lr = float(np.std(lrs, ddof=1)) if n > 1 else 1.0
    sharpe = (mean_lr / std_lr * np.sqrt(252)
              if std_lr > 1e-12 else 0.0)

    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    wr = float(len(wins) / n)
    pf = (float(wins.sum() / abs(losses.sum()))
          if len(losses) > 0 and losses.sum() != 0 else 999.0)

    # Max drawdown من رأس مال 100
    cap = 100.0
    peak = cap
    max_dd = 0.0
    for p in pnls:
        cap += p
        peak = max(peak, cap)
        dd = (peak - cap) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    exit_dist: Dict[str, int] = {}
    for t in trades:
        r = str(t.get("exit_reason", "?"))
        if "(" in r:
            r = r.split("(")[0].strip()
        exit_dist[r] = exit_dist.get(r, 0) + 1

    return {
        "n_trades": n,
        "mean_lr": mean_lr,
        "std_lr": std_lr,
        "sharpe": float(sharpe),
        "win_rate": wr,
        "profit_factor": pf,
        "max_dd": float(max_dd),
        "sum_pnl": float(pnls.sum()),
        "avg_pnl": float(pnls.mean()),
        "exit_dist": exit_dist,
    }


def _objective(metrics: Dict, config: Dict) -> float:
    """دالة الهدف — كلما ارتفعت، كان أفضل."""
    n = metrics.get("n_trades", 0)
    min_trades = config.get("_min_trades", 20)

    if n < min_trades:
        return -100.0

    mean_lr = metrics.get("mean_lr", 0.0)
    max_dd = metrics.get("max_dd", 1.0)
    wr = metrics.get("win_rate", 0.0)
    sharpe = metrics.get("sharpe", 0.0)

    # دالة أساسية
    J = mean_lr * np.sqrt(n) * (1.0 - max_dd)

    # عقوبات
    if max_dd > 0.7:
        J -= (max_dd - 0.7) * 5.0
    if wr < 0.25:
        J -= (0.25 - wr) * 2.0
    if sharpe < 0:
        J -= abs(sharpe) * 0.5

    return float(J)


# ═══════════════════════════════════════════════════════════════════════
# 5. POOL WRAPPER
# ═══════════════════════════════════════════════════════════════════════

class OptimizerPool:
    def __init__(self, bot_dir: str, bot_file: str,
                 log_dir: str, n_workers: int):
        self.bot_dir = os.path.abspath(bot_dir)
        self.bot_file = bot_file
        self.log_dir = log_dir
        self.n_workers = n_workers
        self._ctx = mp.get_context("spawn")
        self._ex: Optional[ProcessPoolExecutor] = None

    def __enter__(self):
        print(f"[Pool] Starting {self.n_workers} workers...", flush=True)
        self._ex = ProcessPoolExecutor(
            max_workers=self.n_workers,
            mp_context=self._ctx,
            initializer=_worker_init,
            initargs=(self.bot_dir, self.bot_file, self.log_dir),
        )
        return self

    def __exit__(self, *args):
        if self._ex is not None:
            self._ex.shutdown(wait=True)
            self._ex = None

    def evaluate_batch(self, tasks: List[Dict],
                       desc: str = "Evaluating") -> List[Dict]:
        if not tasks:
            return []
        futures = [self._ex.submit(_evaluate_one, t) for t in tasks]
        results = []
        itr = as_completed(futures)
        if _HAS_TQDM:
            itr = tqdm(itr, total=len(futures), desc=desc)
        for fut in itr:
            try:
                results.append(fut.result(timeout=1800))
            except Exception as e:
                results.append({"error": str(e),
                                "objective": -100.0,
                                "n_trades": 0})
        return results


# ═══════════════════════════════════════════════════════════════════════
# 6. STAGE 1 — LHS Screening
# ═══════════════════════════════════════════════════════════════════════

def stage1_lhs(pool: OptimizerPool, n_samples: int,
               config: Dict, log_file: str) -> List[Dict]:
    print(f"\n{'=' * 70}")
    print(f"STAGE 1: LHS Screening ({n_samples} samples × {N_PARAMS}D)")
    print(f"{'=' * 70}")

    sampler = qmc.LatinHypercube(d=N_PARAMS, seed=42)
    samples = qmc.scale(sampler.random(n_samples),
                        PARAM_LOWER, PARAM_UPPER)

    tasks = [
        {"run_id": f"s1_{i:04d}",
         "params": arr_to_params(x),
         "config": config}
        for i, x in enumerate(samples)
    ]

    results = pool.evaluate_batch(tasks, desc="Stage 1 (LHS)")
    _append_log(log_file, results, "s1")

    valid = [r for r in results
             if r.get("n_trades", 0) >= config.get("_min_trades", 20)]
    valid.sort(key=lambda r: -r.get("objective", -100.0))

    print(f"\n  ✓ Valid: {len(valid)}/{len(results)}")
    if valid:
        top = valid[0]
        print(f"  ✓ Best obj:      {top['objective']:+.6f}")
        print(f"  ✓ Best trades:   {top['n_trades']}")
        print(f"  ✓ Best mean_lr:  {top['mean_lr']:+.6f}")
        print(f"  ✓ Best sharpe:   {top.get('sharpe', 0):.3f}")
        print(f"  ✓ Best max_dd:   {top['max_dd']:.3f}")

    n_keep = max(8, len(valid) // 3)
    return valid[:n_keep]


# ═══════════════════════════════════════════════════════════════════════
# 7. STAGE 2 — Bayesian Optimization
# ═══════════════════════════════════════════════════════════════════════

def _expected_improvement(X: np.ndarray,
                           gp: GaussianProcessRegressor,
                           y_best: float,
                           xi: float = 0.01) -> np.ndarray:
    mu, sigma = gp.predict(X, return_std=True)
    sigma = sigma.reshape(-1)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (mu - y_best - xi) / (sigma + 1e-12)
        ei = (mu - y_best - xi) * norm.cdf(z) + sigma * norm.pdf(z)
        ei[sigma < 1e-9] = 0.0
    return ei


def stage2_bayes(pool: OptimizerPool, seed_points: List[Dict],
                  n_iter: int, config: Dict,
                  log_file: str) -> List[Dict]:
    print(f"\n{'=' * 70}")
    print(f"STAGE 2: Bayesian Optimization ({n_iter} iterations)")
    print(f"{'=' * 70}")

    if not seed_points:
        print("  ✗ No seed points — skipping")
        return []

    # Build initial data
    X_obs, y_obs = [], []
    for r in seed_points:
        if "params" in r and "objective" in r:
            X_obs.append(params_to_arr(r["params"]))
            y_obs.append(r["objective"])

    X_obs = np.array(X_obs)
    y_obs = np.array(y_obs)
    y_best = float(np.max(y_obs))

    print(f"  Initial data: {len(X_obs)} points, y_best={y_best:+.6f}")

    kernel = (ConstantKernel(1.0, (1e-3, 1e3))
              * Matern(length_scale=np.ones(N_PARAMS),
                       length_scale_bounds=(1e-2, 1e2),
                       nu=2.5))

    all_results = list(seed_points)

    for it in range(n_iter):
        # Fit GP
        try:
            gp = GaussianProcessRegressor(
                kernel=kernel,
                n_restarts_optimizer=2,
                alpha=1e-6,
                normalize_y=True,
                random_state=42 + it,
            )
            gp.fit(X_obs, y_obs)
        except Exception as e:
            print(f"  [iter {it}] GP fit failed: {e}")
            break

        # Candidate pool: LHS + local perturbations
        n_cand = 3000
        sampler = qmc.LatinHypercube(d=N_PARAMS, seed=100 + it)
        cand = qmc.scale(sampler.random(n_cand),
                          PARAM_LOWER, PARAM_UPPER)

        # أضف اضطرابات موضعية حول الأفضل
        n_top = min(5, len(X_obs))
        top_idx = np.argsort(y_obs)[-n_top:]
        span = PARAM_UPPER - PARAM_LOWER
        for idx in top_idx:
            local = X_obs[idx] + np.random.randn(50, N_PARAMS) * 0.05 * span
            local = np.clip(local, PARAM_LOWER, PARAM_UPPER)
            cand = np.vstack([cand, local])

        # EI
        ei = _expected_improvement(cand, gp, y_best)
        x_next = cand[int(np.argmax(ei))]
        params = arr_to_params(x_next)

        # Evaluate
        task = {"run_id": f"s2_{it:04d}",
                "params": params,
                "config": config}
        result = pool.evaluate_batch([task],
                                      desc=f"Stage 2 [{it + 1}/{n_iter}]")[0]
        _append_log(log_file, [result], "s2")
        all_results.append(result)

        if "objective" in result and "error" not in result:
            X_obs = np.vstack([X_obs, x_next])
            y_obs = np.append(y_obs, result["objective"])
            if result["objective"] > y_best:
                y_best = result["objective"]
                print(f"  ★ [{it + 1:3d}] NEW BEST "
                      f"obj={y_best:+.6f} "
                      f"trades={result.get('n_trades', 0)} "
                      f"lr={result.get('mean_lr', 0):+.6f}")
            else:
                print(f"    [{it + 1:3d}] obj={result['objective']:+.6f} "
                      f"(best={y_best:+.6f})")
        else:
            print(f"    [{it + 1:3d}] FAILED: "
                  f"{result.get('error', '?')[:60]}")

    valid = [r for r in all_results
             if r.get("n_trades", 0) >= config.get("_min_trades", 20)]
    valid.sort(key=lambda r: -r.get("objective", -100.0))
    return valid[:10]


# ═══════════════════════════════════════════════════════════════════════
# 8. STAGE 3 — Local Refinement (Powell)
# ═══════════════════════════════════════════════════════════════════════

def stage3_refine(pool: OptimizerPool, seeds: List[Dict],
                   n_iter: int, config: Dict,
                   log_file: str) -> List[Dict]:
    print(f"\n{'=' * 70}")
    print(f"STAGE 3: Local Refinement (top {min(5, len(seeds))})")
    print(f"{'=' * 70}")

    refined = []
    _rc = [0]  # run counter

    for k, seed in enumerate(seeds[:5]):
        if "params" not in seed:
            continue

        x0 = params_to_arr(seed["params"])
        print(f"\n  → Refining seed #{k + 1} "
              f"(obj={seed.get('objective', -100):+.6f})")

        def obj_fn(x):
            x = np.clip(x, PARAM_LOWER, PARAM_UPPER)
            _rc[0] += 1
            task = {"run_id": f"s3_{k}_{_rc[0]:03d}",
                    "params": arr_to_params(x),
                    "config": config}
            r = pool.evaluate_batch(
                [task], desc=f"  seed {k + 1} eval"
            )[0]
            _append_log(log_file, [r], "s3")
            return -r.get("objective", -100.0)

        try:
            res = minimize(
                obj_fn, x0, method="Powell",
                options={"maxiter": n_iter,
                         "xtol": 1e-3,
                         "ftol": 1e-3},
            )
            x_opt = np.clip(res.x, PARAM_LOWER, PARAM_UPPER)
            task = {"run_id": f"s3_final_{k}",
                    "params": arr_to_params(x_opt),
                    "config": config}
            r_final = pool.evaluate_batch([task],
                                           desc="  final")[0]
            _append_log(log_file, [r_final], "s3_final")
            refined.append(r_final)
            print(f"    ✓ Final: obj={r_final.get('objective', -100):+.6f}, "
                  f"trades={r_final.get('n_trades', 0)}, "
                  f"lr={r_final.get('mean_lr', 0):+.6f}")
        except Exception as e:
            print(f"    ✗ Refinement failed: {e}")

    refined.sort(key=lambda r: -r.get("objective", -100.0))
    return refined


# ═══════════════════════════════════════════════════════════════════════
# 9. STAGE 4 — Walk-Forward Validation
# ═══════════════════════════════════════════════════════════════════════

def stage4_validate(pool: OptimizerPool, candidates: List[Dict],
                     config: Dict, log_file: str,
                     folds: int = 4) -> List[Dict]:
    print(f"\n{'=' * 70}")
    print(f"STAGE 4: Walk-Forward Validation ({folds} folds)")
    print(f"{'=' * 70}")

    if not candidates:
        print("  ✗ No candidates — skipping")
        return []

    # تواريخ النوافذ
    now = datetime.now(timezone.utc)
    fold_dates = [
        (now - timedelta(days=90 * i)).strftime("%Y-%m-%d")
        for i in range(folds)
    ]
    print(f"  Folds: {fold_dates}")

    # بناء المهام
    tasks = []
    for k, cand in enumerate(candidates[:5]):
        if "params" not in cand:
            continue
        for f, date in enumerate(fold_dates):
            fold_cfg = dict(config)
            fold_cfg["BACKTEST_END_DATE"] = date
            fold_cfg["history_days"] = 180
            tasks.append({
                "run_id": f"s4_c{k}_f{f}",
                "params": cand["params"],
                "config": fold_cfg,
                "_cand_idx": k,
                "_fold_idx": f,
            })

    all_results = pool.evaluate_batch(tasks,
                                       desc="Stage 4 (walk-forward)")

    # جمّع بحسب المرشح
    by_cand: Dict[int, List[Dict]] = {}
    for r in all_results:
        idx = r.get("_cand_idx")
        if idx is None:
            continue
        by_cand.setdefault(idx, []).append(r)

    # احسب robustness
    scored = []
    for k, results in by_cand.items():
        if not results:
            continue
        objs = [r.get("objective", -100.0) for r in results]
        mean_obj = float(np.mean(objs))
        std_obj = float(np.std(objs)) if len(objs) > 1 else 0.0
        min_obj = float(np.min(objs))
        robust = mean_obj - 0.5 * std_obj

        scored.append({
            "candidate_idx": k,
            "params": candidates[k]["params"],
            "folds": len(results),
            "mean_obj": mean_obj,
            "std_obj": std_obj,
            "min_obj": min_obj,
            "robust_score": robust,
        })

    scored.sort(key=lambda r: -r["robust_score"])

    print(f"\n  Robustness Ranking:")
    for i, s in enumerate(scored):
        print(f"    #{i + 1}: mean={s['mean_obj']:+.6f} "
              f"std={s['std_obj']:.6f} min={s['min_obj']:+.6f} "
              f"→ robust={s['robust_score']:+.6f}")

    _append_log(log_file, scored, "s4")
    return scored


# ═══════════════════════════════════════════════════════════════════════
# 10. LOGGING
# ═══════════════════════════════════════════════════════════════════════

_LOG_LOCK = None

def _append_log(log_file: str, records: List[Dict], stage: str):
    try:
        with open(log_file, "a") as f:
            for r in records:
                entry = dict(r)
                entry["_stage"] = stage
                entry["_ts"] = time.time()
                f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        print(f"[Log] write failed: {e}")


# ═══════════════════════════════════════════════════════════════════════
# 11. MAIN
# ═══════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(
        description="Multi-Stage Hyperparameter Optimizer"
    )
    p.add_argument("--bot-dir", default=".")
    p.add_argument("--bot-file", default="trading_2_complete4.py")
    p.add_argument("--output", default="optimizer_out")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--n-assets", type=int, default=8)
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--history-days", type=int, default=365)
    p.add_argument("--stage1-samples", type=int, default=100)
    p.add_argument("--stage2-iter", type=int, default=150)
    p.add_argument("--stage3-iter", type=int, default=30)
    p.add_argument("--stage4-folds", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--min-trades", type=int, default=20)
    p.add_argument("--skip-stage1", action="store_true")
    p.add_argument("--skip-stage2", action="store_true")
    p.add_argument("--skip-stage3", action="store_true")
    p.add_argument("--skip-stage4", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    np.random.seed(args.seed)

    # Output dir
    out_dir = Path(args.output).absolute()
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = str(out_dir / "runs.jsonl")
    result_file = str(out_dir / "best_params.json")

    print("╔" + "═" * 68 + "╗")
    print("║  Multi-Stage Optimizer for Quantum Thermodynamic Bot" +
          " " * 16 + "║")
    print("╚" + "═" * 68 + "╝")
    print(f"  Bot:        {args.bot_dir}/{args.bot_file}")
    print(f"  Output:     {out_dir}")
    print(f"  Workers:    {args.workers}")
    print(f"  Params:     {N_PARAMS} dims")
    print(f"  TF:         {args.timeframe}")
    print(f"  History:    {args.history_days}d")
    print(f"  N assets:   {args.n_assets}")
    print(f"  Min trades: {args.min_trades}")
    print()

    # Config
    config = dict(DEFAULT_FIXED)
    config["n_assets"] = args.n_assets
    config["timeframe"] = args.timeframe
    config["history_days"] = args.history_days
    config["_min_trades"] = args.min_trades

    t_start = time.time()

    with OptimizerPool(args.bot_dir, args.bot_file,
                        str(out_dir), args.workers) as pool:

        # ── Warmup ──
        print("\n[Warmup] Pre-loading data + JIT compilation...")
        warmup_params = {
            name: (lo + hi) / 2
            for name, (lo, hi, _) in PARAM_SPACE.items()
        }
        wr = pool.evaluate_batch([{
            "run_id": "warmup",
            "params": warmup_params,
            "config": config,
        }], desc="Warmup")[0]
        print(f"  Warmup: trades={wr.get('n_trades', 0)}, "
              f"obj={wr.get('objective', -100):+.6f}, "
              f"time={wr.get('duration_s', 0):.1f}s")
        if "error" in wr:
            print(f"  ⚠️  Warmup error: {wr['error']}")

        # ── Stage 1 ──
        if not args.skip_stage1:
            s1_top = stage1_lhs(pool, args.stage1_samples,
                                 config, log_file)
        else:
            s1_top = [wr] if wr.get("n_trades", 0) > 0 else []

        if not s1_top:
            print("\n[!] Stage 1 produced no valid candidates. Aborting.")
            _save_summary(result_file, {}, {}, config, 0, time.time() - t_start)
            return

        # ── Stage 2 ──
        if not args.skip_stage2:
            s2_top = stage2_bayes(pool, s1_top, args.stage2_iter,
                                   config, log_file)
            if not s2_top:
                s2_top = s1_top
        else:
            s2_top = s1_top

        # ── Stage 3 ──
        if not args.skip_stage3:
            s3_top = stage3_refine(pool, s2_top, args.stage3_iter,
                                    config, log_file)
            if not s3_top:
                s3_top = s2_top
        else:
            s3_top = s2_top

        # ── Stage 4 ──
        if not args.skip_stage4:
            s4_top = stage4_validate(pool, s3_top, config,
                                      log_file, folds=args.stage4_folds)
            if not s4_top:
                s4_top = [
                    {"candidate_idx": i,
                     "params": r.get("params", {}),
                     "robust_score": r.get("objective", -100),
                     "mean_obj": r.get("objective", -100),
                     "std_obj": 0.0,
                     "min_obj": r.get("objective", -100),
                     "folds": 0}
                    for i, r in enumerate(s3_top)
                ]
        else:
            s4_top = [
                {"candidate_idx": i,
                 "params": r.get("params", {}),
                 "robust_score": r.get("objective", -100),
                 "mean_obj": r.get("objective", -100),
                 "std_obj": 0.0,
                 "min_obj": r.get("objective", -100),
                 "folds": 0}
                for i, r in enumerate(s3_top)
            ]

    # ── Save results ──
    elapsed = time.time() - t_start
    _save_summary(result_file, s4_top, config, elapsed)

    print("\n╔" + "═" * 68 + "╗")
    print("║                    OPTIMIZATION COMPLETE                    ║")
    print("╚" + "═" * 68 + "╝")
    print(f"  Elapsed: {elapsed / 60:.1f} minutes")
    print(f"  Log:     {log_file}")
    print(f"  Result:  {result_file}")

    if s4_top:
        best = s4_top[0]
        print("\n  🏆 BEST PARAMETERS (by robustness):")
        print("  " + "─" * 60)
        for k, v in best.get("params", {}).items():
            print(f"    {k:30s} = {v:.6f}")
        print("  " + "─" * 60)
        print(f"    robust_score = {best.get('robust_score', 0):+.6f}")
        print(f"    mean_obj     = {best.get('mean_obj', 0):+.6f}")
        print(f"    std_obj      = {best.get('std_obj', 0):.6f}")
        print(f"    min_obj      = {best.get('min_obj', 0):+.6f}")


def _save_summary(result_file, s4_top, config, elapsed):
    """حفظ النتائج النهائية."""
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_min": elapsed / 60 if elapsed else 0,
        "config": {k: v for k, v in config.items()
                   if not k.startswith("_")},
        "param_space": {
            k: {"min": v[0], "max": v[1]}
            for k, v in PARAM_SPACE.items()
        },
        "top5": [
            {
                "params": s.get("params", {}),
                "robust_score": s.get("robust_score", 0),
                "mean_obj": s.get("mean_obj", 0),
                "std_obj": s.get("std_obj", 0),
                "min_obj": s.get("min_obj", 0),
            }
            for s in s4_top[:5]
        ] if s4_top else [],
    }
    if s4_top:
        output["best_params"] = s4_top[0].get("params", {})

    try:
        with open(result_file, "w") as f:
            json.dump(output, f, indent=2, default=str)
    except Exception as e:
        print(f"[Save] failed: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user")
        sys.exit(1)
