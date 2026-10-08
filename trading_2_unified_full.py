#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════
#  trading_2_unified_full.py
#  Quantum Thermodynamic Trading Engine
#  UNIFIED DECISION ENGINE — FULL (live + backtest)
#  Generated: 2026-10-07 22:38:09
#  Base: trading_2_unified.py
#
#  Unified decision applied to BOTH:
#    • run_live (via apply_unified_v2.py)
#    • simulate_portfolio (via this script)
#
#  Enable with --unified. Works in backtest AND live.
# ═══════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════
#  trading_2_unified.py
#  Quantum Thermodynamic Trading Engine
#  UNIFIED DECISION ENGINE Build
#  Generated: 2026-10-07 22:35:40
#  Base: trading_2_mfal.py
#
#  Unified Decision Engine replaces the sequential
#  (risk → leverage → qty) pipeline with a single
#  constrained Bayesian optimization:
#
#      (qty*, L*, a*) = argmax a·E[log W_T]
#      subject to all constraints simultaneously.
#
#  Default: DISABLED. Enable with --unified flag.
# ═══════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════
#  trading_2_mfal.py
#  Quantum Thermodynamic Trading Engine
#  MFAL Build — Multi-Factor Adaptive Leverage
#  Generated: 2026-10-07 22:17:34
#  Base: trading_2_complete4.py
#
#  MFAL adds:
#    • Q — Quality Factor (learned signal quality)
#    • R — Risk Factor (portfolio capacity)
#    • T — Time Factor (hour-of-day liquidity)
#    • M — Micro Factor (spread / depth)
#    • Online learning (logistic regression on outcomes)
#    • Persistent weights (mfal_weights.json)
#    • Trade history (mfal_history.jsonl)
#
#  Default: DISABLED. Enable with --mfal flag.
# ═══════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════
#  trading_2_complete4.py
#  Quantum Thermodynamic Trading Engine
#  GTX-Safe Build — FIX-25 (v2)
#  Generated: 2026-10-06 16:21:47
#  Base: trading_2_complete3.py
# ═══════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════
#  trading_2_complete.py
#  Quantum Thermodynamic Trading Engine — COMPLETE
#  Generated: 2026-10-05 14:43:38
#  Base: trading_2_final_all.py
#
#  Patch rounds (6):
#    1. apply_live_parity_fixes.py    (19 fixes)
#    2. fix_parity_issues.py          (6 corrections)
#    3. fix_remaining_issues.py       (2 surgical)
#    4. fix_leverage_tiers.py         (FIX-01-PROPER)
#    5. fix_position_cache.py         (FIX-09-PROPER)
#    6. fix_parity_v2.py              (FIX-20/21/22)
# ═══════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════
#  trading_2_final_all.py
#  Quantum Thermodynamic Trading Engine — FULL PARITY
#  Generated: 2026-10-05 14:37:00
#  Base: trading_2_final_lev.py
#
#  FIX-09-PROPER adds:
#    • Position cache with 3s TTL
#    • ONE API call for ALL positions (weight=5)
#    • _fake_pos_list() preserves original return shape
#    • Explicit invalidation after entry/exit/partial
#    • PosCache stats every 5 min
#    • Zero backtest impact
# ═══════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  trading_2_final_lev.py
#  Quantum Thermodynamic Trading Engine
#  FIX-01-PROPER (symbol-aware leverage tiers)
#  Generated: 2026-10-05 14:26:51
#  Base: trading_2_release.py
#
#  What changed vs previous FIX-01:
#    BEFORE: hardcoded tuple (1,2,3,5,10,20,25,50,75,100,125)
#            applied uniformly to every symbol — often wrong for
#            alt coins whose max leverage is 25x or 20x.
#
#    AFTER:
#      * Live: query exchange.fetch_leverage_tiers([sym]) once per
#        symbol, cache the result, and snap only to those tiers.
#      * Backtest: prefetch all tiers during data-loading phase.
#      * Fallback: static table for well-known symbols; conservative
#        LEVERAGE_MAX otherwise.
#      * LevCap (compute_max_leverage_by_liq) also symbol-aware.
#      * ensure_symbol_setup snaps its target BEFORE calling
#        set_leverage, eliminating -4028 completely.
# ════════════════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  trading_2_release.py
#  Quantum Thermodynamic Trading Engine — Live/Backtest Parity Build
#  Generated: 2026-10-05 14:15:19
#  Base: trading_2_final.py
#
#  Patch summary:
#    • 19 original fixes (apply_live_parity_fixes.py)
#    •  6 corrections   (fix_parity_issues.py)
#    •  2 surgical      (fix_remaining_issues.py)
#
#  Verified feature set:
#    - Leverage snapped to Binance tiers  (no -4028)
#    - Qty rounded to stepSize            (no -1111)
#    - MIN_NOTIONAL pre-checked           (no -4164)
#    - GTX rejection → wider-offset retry (no -2010)
#    - Physics exits use last CLOSED bar  (no look-ahead)
#    - Broker-closed position auto-adopt  (no -2022 spam)
#    - Maker/Taker fee accuracy in PnL
#    - Partial TP single-fire guarantee
#    - Trailing snapshot survives restart
#    - Reconcile places protective orders
#    - Exit retry limit → forced market
# ════════════════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  trading_2_final.py — Live/Backtest Parity Build (final)
#  Generated: 2026-10-05 14:11:15
#  Base: trading_2_fixed_v2.py
#
#  All 19 original fixes + 6 corrections + 2 surgical retries:
#    FIX-04 retry : GTX rejection fallback (was missing)
#    FIX-09 retry : -2022 / exchange-closed detection (was missing)
#    FIX-15b retry: robust trail snapshot bootstrap
# ════════════════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  trading_2_fixed_v2.py — Corrected Live/Backtest Parity Build
#  Generated: 2026-10-05 14:09:52
#  Base: trading_2_fixed.py
#
#  Corrections applied on top of the first patch round:
#    - FIX-05b: no extra fetch_balance() in place_pending_entry
#    - FIX-05c: run_live publishes _LAST_KNOWN_CAP
#    - FIX-06b: _partial_taken only set when partial TP is valid
#    - FIX-10b: exit fee uses maker/taker classification
#    - FIX-11b: removed redundant post-exit cleanup
#    - FIX-15b: robust trail snapshot bootstrap
#    - ENSURE:  _exit_is_taker helper guaranteed present
# ════════════════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  trading_2_fixed.py — Auto-patched for Live/Backtest parity
#  Generated: 2026-10-05 14:05:36
#  Patches applied: 19
#  Source: trading_2.py
# ════════════════════════════════════════════════════════════════════
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      محرك التداول الثرموديناميكي الكمي – الإصدار 6.1 (محرك التفرد المطور)    ║
║    Quantum Thermodynamic Trading Engine – v6.1  (Singularity Engine)         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  تم حل مشاكل الإنزلاق السعري بروتوكولياً عبر تكميم الأوامر (Quantum Chunks)  ║
║  تم ضبط المسافات البادئة وتصحيح منطق الأوامر المعلقة الهجومية لضمان التنفيذ.  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse, json, logging, os, time, warnings
import pickle
import hashlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import traceback
import numpy as np
import pandas as pd
from scipy.stats import kurtosis, linregress, skew
from sklearn.cluster import KMeans

# ══ [LEVEL-2] Numba optional import with graceful fallback ══
try:
    from numba import njit
    _NUMBA_AVAILABLE = True
except ImportError:
    _NUMBA_AVAILABLE = False
    def njit(*args, **kwargs):
        # Fallback: no-op decorator so code still runs without numba
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        def deco(f):
            return f
        return deco

import matplotlib
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# ══ [WATCH-REMOVED-MASTER] ═══════════════════════════════════════════
# Watch-then-trigger mode has been permanently disabled.
# All watch code paths (state files, signal registration, monitoring)
# short-circuit at entry via this flag. The functions themselves are
# preserved (some share utilities with legacy paths), but they are
# provably dead code now.
#
# To temporarily re-enable watch (NOT recommended):
#   Set WATCH_REMOVED = False and WATCH_MODE_ENABLED = True in Config.
# ═════════════════════════════════════════════════════════════════════
WATCH_REMOVED = True
# ═════════════════════════════════════════════════════════════════════

os.environ["LOKY_MAX_CPU_COUNT"] = "4"
# [Level-1] Prevent BLAS/OpenMP thread oversubscription in workers
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
CACHE_DIR = "market_data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# ══ [Cache-Health] إحصائيات عامة للجلسة ══
_CACHE_HEALTH: Dict = {
    'files_scanned': 0,
    'issues_fixed_local': 0,
    'gaps_found': 0,
    'bars_refetched': 0,
    'files_saved': 0,
}
os.makedirs(CACHE_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("QTT6")


# ════════════════════════════════════════════════════════════════
# § 0  الإعدادات المركزية
# ════════════════════════════════════════════════════════════════

@dataclass
class Config:
    mode: str = "backtest"
    api_key: str = ""
    api_secret: str = ""
    testnet_url: str = "https://demo-fapi.binance.com"

    n_assets: int = 15
    min_quote_vol_usd: float = 1e8
    exclude_tokens: List[str] = field(default_factory=lambda: [
        "USDC","BUSD","TUSD","USDP","DAI","FDUSD","BVOL","IBVOL",
        "UP","DOWN","BEAR","BULL","HALF","HEDGE"
    ])

    timeframe: str = "1h"
    history_days: int = 730

    N: int = 24; W: int = 20; L: int = 10; K: int = 8
    EMA_SPAN: int = 200; ATR_PERIOD: int = 14

    W_CURV: float=1.0; W_VOL: float=1.0; W_ENTROPY: float=2.0
    W_HMM: float=2.0; W_FREE_E: float=1.0; MIN_SCORE: int=3

    CURV_THRESHOLD: float=0.01; DH_ENTROPY_THRESHOLD: float=0.005
    DH_HMM_UPPER: float=0.01;  DH_HMM_LOWER: float=-0.01
    DF_FREE_E_THRESHOLD: float=-0.01

    # ══ التعديل ①: Kelly الجيوديسي (f* = |accel|/Γ × e^{-λT}) ════════════
    # تفرد كيلي المخمد (Sigmoid Limits)
    BASE_RISK: float = 0.02       
    MIN_RISK:  float = 0.01       
    MAX_RISK:  float = 0.05       # أقصى مخاطرة 5% لحماية الجسيم الصغير
    LAMBDA_KELLY: float = 0.05    # تخميد (سيصبح ديناميكياً)
    KELLY_SCALE: float = 0.50     # مقياس التحويل (تم رفعه إلى 0.50)
    RISK_PER_TRADE: float = 0.15

    LEVERAGE_BASE: float = 50.0   # نبدأ بـ 50x بقوة دفع هائلة
    LEVERAGE_MIN: int = 5
    LEVERAGE_MAX: int = 50
    LEVERAGE: int = 5
    INITIAL_CAPITAL: float = 10.0 # الانطلاق بـ 10$
    # ══ [LIVE-CAPITAL] رأس المال المتداول في Live/Testnet.
    # 0 = استخدم free من البورصة (السلوك الافتراضي).
    # >0 = رأس مال ثابت للـ sizing (لا يتأثر بحركة margin).
    LIVE_TRADING_CAPITAL: float = 0.0
    # [END-DATE-FIELD]
    BACKTEST_END_DATE: Optional[str] = None
    CAPITAL_FLOOR: float = 0.15    # قوة التنافر اللانهائية (نقطة استحالة التصفية)
    # ══ [REALISTIC FEES — Binance USDT-M Futures VIP0] ══
    # Maker: 0.020% (orders that add liquidity: entry GTX, exit post-only)
    # Taker: 0.050% (orders that cross the book: SL, TP-urgent, market)
    # These apply to BOTH entry and exit; the backtest computes each side
    # separately in _close().
    MAKER_FEE: float = 0.0002
    TAKER_FEE: float = 0.0005
    MAX_CHUNK_USD: float = 1000.0 # أقصى حجم للحزمة الكمومية الواحدة بالدولار لتجنب صدمة دفتر الأوامر
    MIN_NOTIONAL: float = 5.0
    SL_FACTOR: float = 0.5
    TP_BETAS: Tuple = (1.5,)

    FUNDING_RATE_COST: float = 0.0001
    FUNDING_INTERVAL_BARS: int = 8

    MAX_DRAWDOWN_HALT: float   = 1.00
    REDUCED_RISK_MULT: float   = 0.25
    REDUCED_RISK_MULT_50: float= 0.10
    REDUCED_RISK_MULT_70: float= 0.05
    DRAWDOWN_REDUCE_AT:  float = 0.15   # [ABL3c] 0.30 -> 0.15
    DRAWDOWN_REDUCE_AT_50: float=0.30   # [ABL3c] 0.50 -> 0.30
    DRAWDOWN_REDUCE_AT_70: float=0.50   # [ABL3c] 0.70 -> 0.50

    MAX_CONCURRENT_ASSETS: int   = 3   # [ABL6] 5 -> 3
    CORRELATION_THRESHOLD: float = 0.70

    MAX_HOLD_BARS: int = 168
    # [FIX-21] configurable retry threshold
    PO_MAX_FORCE_MARKET_ATTEMPTS: int = 3

    TOPO_DIV_THRESHOLD: float = 0.05

    K_MIN: int = 25
    K_MAX: int = 50
    KQUANT_ALPHA: float = 100.0

    COSMOLOGICAL_CONSTANT: float = 0

    OPTIMAL_ENTRY_WAIT: int=8; OPTIMAL_ENTRY_DIP: float=0.3

    REVERSAL_MIN_SCORE: int=3; LYA_WINDOW: int=20
    LYA_THRESHOLD_MULT: float=2.0

    SLIP_BASE: float=0.0003; SLIP_IMPACT: float=0.02
    MAX_SLIPPAGE_FRACTION: float=0.0002

    MAX_ADV_FRACTION: float=0.01

    TRAIN_FRACTION: float=0.50

    LIVE_POLL_SECS: int=5 ; LIVE_ORDER_TYPE: str = "MARKET"
    EPSILON: float=1e-9

    GAMMA_0: float = 0.01
    KAPPA: float = 0.1
    XI: float = 1.0
    LORENTZ_CHARGE_Q: float = 1.0
    MAX_EQUILIBRIUM_GAP: float = 0.35
    ERGODIC_DH_WINDOW: int = 12
    ERGODIC_DH_THRESHOLD: float = 0.001
    GEO_EXIT_THRESHOLD: float = 0.02   # (لن يستخدم بعد إلغاء GeoExit)

    # ══ [FILL ENGINE v1 — Adaptive Maker Execution] ══
    FILL_ENGINE_ENABLED: bool = True
    FILL_TARGET: float = 0.90           # target fill rate
    FILL_MAX_WAIT_S: int = 60           # max time to wait for fill
    FILL_RECHECK_MS: int = 300          # cancel/replace interval
    FILL_LADDER_WEIGHTS: Tuple = (0.5, 0.3, 0.2)  # 3-level ladder
    FILL_USE_LADDER: bool = True
    FILL_ADAPT_ENABLED: bool = True
    FILL_ADAPT_WINDOW: int = 20
    FILL_ENTRY_MODE: str = "hybrid"     # "maker" | "taker" | "hybrid"
    FILL_TOXICITY_THRESHOLD_BPS: float = 5.0
    # ══ [ADAPTIVE FILL v2 — Microstructure-Aware] ══
    FILL_BOOK_DEPTH: int = 20               # order book levels to fetch
    FILL_QUEUE_DEPTH_USED: int = 5          # depth used for queue estimate
    FILL_SIGMA_FAST_S: int = 5              # fast vol window (seconds)
    FILL_SIGMA_SLOW_S: int = 60             # slow vol window
    FILL_MICRO_MOMENTUM_S: int = 10         # micro-momentum lookback
    FILL_OFI_WINDOW_S: int = 5              # OFI window
    FILL_KALMAN_ALPHA: float = 0.15         # fair-price EMA alpha
    FILL_TOXIC_THRESHOLD: float = 0.65      # cancel if toxic > this
    FILL_MIN_FILL_EDGE_BPS: float = 1.5     # don't quote if edge < this
    FILL_MAX_REPRICE_PER_MIN: int = 40      # rate limit on cancel/replace
    FILL_LADDER_LEVELS: int = 5             # 5 levels instead of 3
    FILL_URGENCY_KAPPA: float = 2.0         # exponential urgency rate
    FILL_ADVERSE_SELECTION_BPS: float = 3.0 # expected adverse cost baseline

    # ══ [BACKTEST REALISM — Penetration & Fill Search] ══
    FILL_PENETRATION_BPS: float = 1.0            # 0.01% penetration required
    # [FILL-WINDOW] 15 bars was too tight: with σ_bar ≈ 1%, the theoretical
    # probability of reaching a 1% dip within 15 bars is only ~40%.
    # 25 bars recovers roughly +15pp fill rate on 1h without letting the
    # signal age past its validity window.
    FILL_ENTRY_MAX_WAIT_BARS: int = 25           # order lifetime in backtest
    FILL_APPLY_TO_EXITS: bool = True             # also apply to SL/TP
    # ══ [LEVEL-1 PERFORMANCE] ══
    PARALLEL_PROCESSING: bool = True
    PARALLEL_WORKERS: int = 0            # 0 = auto (cpu_count)
    ASSET_CACHE_ENABLED: bool = True
    ASSET_CACHE_DIR: str = "asset_cache"

    # ══ [LEVEL-2 PERFORMANCE] ══
    NUMBA_ENABLED: bool = True       # Ignored if numba not installed

    # ══ [POST-ONLY EXECUTION] ══
    PO_PENETRATION_BPS: float = 1.0      # match backtest's FILL_PENETRATION_BPS
    PO_MAX_WAIT_S: int = 0 # 200              # entry wait time (per attempt)
    PO_EXIT_MAX_WAIT_S: int = 45          # reduced from 180 to prevent long blocking
    PO_REPRICE_S: float = 3.0            # cancel/replace interval
    PO_FILL_THRESHOLD: float = 0.50      # accept partial if ≥ 50%
    PO_EXIT_FALLBACK_MARKET: bool = True # exit → market after timeout
    PO_DRIFT_BPS: float = 0.5            # reprice if target drifts > this

    # ══ [TRAILING STOP] ══
    # ══ [TRAILING STOP LOSS — Master Switch] ══
    # True  → SL يتحرك مع السعر بعد الوصول إلى TRAIL_ACTIVATE_AT_R.
    #         يُحدَّث أيضاً على البورصة عبر _sync_protective_orders.
    # False → SL يبقى ثابتاً عند مستواه عند الدخول (لا Trailing).
    #         مطبّق في الباكتيست واللايف بشكل متطابق.
    # CLI: --no-trailing لتعطيله، --trailing لإجباره.
    TRAIL_ENABLED: bool = True
    TRAIL_ACTIVATE_MFE: float = 0.004    # activate after 0.4% MFE
    TRAIL_DISTANCE: float = 0.003        # trail 0.3% below peak
    TRAIL_MIN_STEP: float = 0.0005       # only move SL if improvement ≥ 0.05%

    # ══ [PORTFOLIO RISK BUDGET] ══
    PORTFOLIO_HEAT_MAX: float = 0.10       # 10% total risk-at-SL across all slots
    RISK_STRENGTH_MIN: float = 0.50        # weakest signal → 0.5 × base_per_slot
    RISK_STRENGTH_MAX: float = 1.50        # strongest signal → 1.5 × base_per_slot
    MIN_RISK_PER_TRADE: float = 0.005      # 0.5% floor (skip if below)
    MAX_RISK_PER_TRADE: float = 0.030      # 3.0% ceiling per trade
    BUDGET_ENABLED: bool = True            # master switch
    # ══ [STATE MACHINE — Persistent Symbol Metadata] ══
    SYMBOL_META_FILE: str = "symbol_meta"
    RECONCILE_INTERVAL_S: int = 3600   # [PERF] 30s → 60min
    FAST_MONITOR_SECS: float = 5.0     # [EXIT] فحص سريع للمراكز
    SETUP_VERIFY_LEVERAGE: bool = True
    FILL_VERIFY_TIMEOUT_S: float = 5.0

    # ══ [ML FILTER — optional signal rejection] ══
    ML_FILTER_ENABLED: bool = False       # default OFF
    ML_FILTER_MODEL_PATH: str = "ml_filter.pkl"
    ML_FILTER_THRESHOLD: float = 0.45     # may be overridden by --ml-threshold
    # ══ [TIMEFRAME SCALE — set at startup] ══
    TF_SCALE: float = 1.0         # ratio (1h / current_tf) — for bar counts
    TF_SECONDS: int = 3600        # seconds per bar
    TF_HOURS: float = 1.0         # hours per bar
    # ══ [NOTIONAL CAP — anti-compounding] ══
    MAX_ABS_NOTIONAL: float = 20_000.0     # tuned for alt liquidity
    # ══ [DYNAMIC TRAILING — volatility-scaled] ══
    TRAIL_DYNAMIC: bool = True
    TRAIL_KAPPA: float = 0.30                # tuned to 1h timeframe
    TRAIL_MIN_FRAC: float = 0.002
    TRAIL_MAX_FRAC: float = 0.008
    TRAIL_ACT_KAPPA: float = 0.40            # tuned to 1h timeframe
    TRAIL_ACT_MIN_FRAC: float = 0.003
    TRAIL_ACT_MAX_FRAC: float = 0.012
    # ══ [SIGMA-SCALED APEX] ══
    APEX_SIGMA_SCALED: bool = True
    APEX_KAPPA_PNL: float = 0.5
    APEX_KAPPA_ENERGY: float = 0.5
    APEX_KAPPA_ACCEL: float = 0.3
    # ══ [RULE-BASED FILTER] ══
    RULE_FILTER_ENABLED: bool = False
    RULE_REJECT_RVOL24_PCT: float = 0.33    # reject if below this quantile
    RULE_REJECT_DIST_HIGH_PCT: float = 0.66 # reject if above this quantile
    RULE_REJECT_TF_STD_PCT: float = 0.66
    RULE_REJECT_RANGE_POS_PCT: float = 0.66
    RULE_MIN_SCORE: int = 2                  # reject if #rules matched >= this
    # ══ [RE-ENTRY COOLDOWN — prevents close-and-reverse] ══
    REENTRY_COOLDOWN_BARS: int = 3     # bars to wait after exit on same symbol
    REENTRY_COOLDOWN_ENABLED: bool = True
    # ══ [LIVE ASSET CACHE — reuse AssetData when closed bar unchanged] ══
    LIVE_ASSET_CACHE_ENABLED: bool = True
    LIVE_ASSET_CACHE_MAX: int = 40           # max entries (safety)
    # ══ [FIXED PRICE ENTRY — no chasing] ══
    PO_FIXED_PRICE: bool = False              # use sig.price, hold it fixed
    # ══ [TF-UNIFIED SCALING] ══
    # كل المسافات بوحدة σ_price = E_therm[fi] × price.
    # كل النوافذ بالساعات الحقيقية (تُحوَّل إلى شموع عند الإقلاع).
    FRICTION_DIP_KAPPA: float = 4.0       # friction_drag = κ × σ_price
#    SL_REF_KAPPA: float = 2.0             # SL/σ = κ × uncertainty / (1 + fric×5)
#    SL_MIN_SIGMA: float = 1.0             # أدنى SL بوحدة σ
#    SL_MAX_SIGMA: float = 5.0             # أقصى SL بوحدة σ
    SL_REF_KAPPA: float = 0.8     # كان 2.0
    SL_MIN_SIGMA: float = 3.0     # كان 1.0
    SL_MAX_SIGMA: float = 8.0     # كان 5.0
    N_HOURS: float = 24.0                 # نافذة الميزات (ساعات)
    W_HOURS: float = 20.0                 # نافذة الإنتروبيا
    L_HOURS: float = 10.0                 # نافذة الهندسة
    ADV_HOURS: float = 24.0               # نافذة ADV
    ADV_BARS: int = 24                    # يُضبط ديناميكياً في main()
    # ══ [UNIFIED ENTRY LOGIC] ══
    # منطق موحّد بمرحلتين:
    #   Stage 1: أمر Limit عند tunnel_entry_p، انتظر UNIFIED_WAIT_BARS_1H.
    #   Stage 2: إن لم يمتلئ، وُجد زخم مؤيد + إشارة حيّة → ادخل بسعر
    #            السوق، وأعد بناء SL/TP من S_new = p - friction_drag.
    # عند UNIFIED_ENTRY_ENABLED=False، يعمل البوت كما كان (PO_FIXED_PRICE).
    UNIFIED_ENTRY_ENABLED: bool = True
    UNIFIED_WAIT_BARS_1H: int = 8            # نافذة Stage 1 (بوحدات 1h)
    UNIFIED_MAX_AGE_BARS_1H: int = 12        # أقصى عمر للإشارة (Stage 2)
    UNIFIED_MOMENTUM_KAPPA: float = 0.50     # عتبة الزخم المؤيد (× σ_bar)
    UNIFIED_REQUIRE_FRESH_SIGNAL: bool = True
    UNIFIED_FRESH_SCORE_FRAC: float = 0.85   # حداثة الإشارة (نسبة)
    # ══ [ATOMIC FILL ACCOUNTING] ══
    PO_MAX_ATTEMPTS: int = 3              # reduced from 5 (rate-limit safety)
    PO_MAX_DRIFT_BPS: float = 5.0
    PO_MIN_ACCEPT_RATIO: float = 0.10     # reject below 50% (was 0.15, comment was misleading)

    # ══ [NON-BLOCKING PENDING ORDERS] ══
    PENDING_ENABLED: bool = True
    PENDING_FILE_PREFIX: str = "pending_orders"
    PENDING_MAX_PER_CYCLE: int = 3        # cap new placements per loop
    PENDING_REST_CHECK_EVERY: int = 2     # check each pending order every N loops

    # ══ [SMART OHLCV FETCH] ══
    SMART_OHLCV_ENABLED: bool = True
    # ══ [SUPPORT/RESISTANCE FILTER] ══
    SR_FILTER_ENABLED: bool = False      # disabled by default until tuned
    SR_LOOKBACK: int = 100
    SR_MIN_TOUCHES: int = 2              # relaxed from 3
    SR_TOUCH_TOLERANCE: float = 0.0035   # relaxed from 0.0025 (0.35%)
    SR_MIN_GAP_BARS: int = 10
    SR_STRENGTH_THRESHOLD: float = 1.0   # relaxed from 2.0
    SR_DECAY_TAU: float = 80.0           # slower decay
    SR_SL_PROXIMITY: float = 0.006       # relaxed from 0.004 (0.6%)
    SR_VOLUME_WEIGHT: float = 1.5
    # ══ [KILL SWITCH — HMAC-authenticated] ══
    KILL_SWITCH_ENABLED: bool = True
    KILL_SWITCH_SECRET: str = ""          # from env or CLI
    KILL_SWITCH_FILE: str = "kill_switch.json"
    KILL_SWITCH_POLL_S: int = 5
    KILL_STATE_ARMED: str = "ARMED"
    KILL_STATE_WARNING: str = "WARNING"
    KILL_STATE_TRIGGERED: str = "TRIGGERED"
    # ══ [THRESHOLD MODE] ══
    # True  → use the ABSOLUTE thresholds (DH_ENTROPY_THRESHOLD,
    #         DF_FREE_E_THRESHOLD, DH_HMM_UPPER, DH_HMM_LOWER).
    #         This is the original design.
    # False → use Z-SCORE thresholds (DH_ENTROPY_Z, ...), the experiment.
    # The diagnostic showed the z-score experiment produced 1.8× signals
    # and a different score distribution. Restored to absolute.
    USE_ABSOLUTE_THRESHOLDS: bool = True

    # Z-score thresholds (kept for the opt-in path)
    DH_ENTROPY_Z: float = -1.0
    DF_FREE_E_Z:  float = -1.0
    DH_HMM_UPPER_Z: float = 0.5
    DH_HMM_LOWER_Z: float = -0.5

    # ══ [ADAPTIVE FIX #2] Data-bound K ══
    # Prevents degenerate clustering when train data is small (e.g. 4h TF).
    K_MIN_TRAIN_POINTS_PER_CLUSTER: int = 100
    K_SKIP_IF_DEGENERATE: bool = True
    K_DEGENERATE_H_RATIO: float = 0.25
    # ══ [SL WIDENING — breathing room] ══
    # Multiplier on the geodesic SL/TP distance. Compensates for the fact
    # that compute_geodesic_stop yields 1.0–1.5% on most assets, which is
    # smaller than typical hourly noise. Widen both SL and TP so R/R is
    # preserved while giving trades room to survive normal volatility.
    #   1.0 → original tight SL
    #   1.5 → moderate widening
    #   2.0 → recommended starting point
    #   2.5 → aggressive widening (fewer SL hits, larger drawdowns)
    SL_WIDEN_MULT: float = 0.8

    # ══ [ADAPTIVE FIX #3] Tick-based penetration ══
    # WIF has 0.254 ticks/bps → 1 bps < 1 tick → orders can't fill properly.
    PO_USE_TICK_PENETRATION: bool = True

    # ══ [ADAPTIVE FIX #4] Dynamic MIN_SCORE (per-asset quantile) ══
    DYNAMIC_MIN_SCORE_ENABLED: bool = False   # opt-in
    DYNAMIC_MIN_SCORE_Q: float = 0.95
    # ══ [DATA AUTO-CONFIG] ══
    # These values are IGNORED at runtime — _resolve_data_params() in main()
    # overrides them based on (mode, timeframe, --history-days).
    # Kept only as fallbacks if main() is bypassed (tests, imports).
    LIVE_HISTORY_DAYS: int = 90
    LIVE_TAIL_BARS: int = 800
    LIVE_MIN_BARS_FOR_PROCESS: int = 300
    # ══ [LIQ AWARENESS] Liquidation safety envelope ══
    LIQ_SAFETY_MULT: float = 1.5          # SL gap × this < Liq gap
    LIQ_EMERGENCY_PROGRESS: float = 0.7    # 70% toward Liq → emergency exit
    LIQ_FALLBACK_MMR: float = 0.02         # 2% if exchange MMR unavailable
    LIQ_ENABLED: bool = True               # master switch (for testing)
    # ══ [LAYER 7 — Broker-side protective orders] ══
    PROTECTIVE_ORDERS_ENABLED: bool = True
    PROTECTIVE_WORKING_TYPE: str = "MARK_PRICE"
    PROTECTIVE_SYNC_MIN_STEP_FRAC: float = 0.001   # 0.1% SL movement → resync
    PROTECTIVE_MAX_RETRIES: int = 2
    # ══ [LAYER 4 — Live price feed for SL/TP checks] ══
    # ad.closes[-1] only refreshes on new bar; on 1h it's frozen for up to
    # 60 min. Ticker gives fresh price every poll (weight=2). Physics
    # checks (Apex, Topo-Div) keep using ad.closes[-1] for reproducibility.
    LIVE_PRICE_ENABLED: bool = True
    LIVE_PRICE_RATE_WEIGHT: float = 2.0
    LIVE_PRICE_FALLBACK_TO_STALE: bool = True

    # ══ [LAYER 5 — Emergency exit near Liq] ══
    LIQ_EMERGENCY_ENABLED: bool = True
    # Refresh exchange-reported Liq when progress crosses this threshold.
    LIQ_EMERGENCY_REFRESH_AT: float = 0.40
    # Cooldown between refreshes of the same symbol.
    LIQ_EMERGENCY_REFRESH_COOLDOWN_S: int = 30
    # Warn user if LiqProximity triggers too often (unsafe leverage regime).
    LIQ_EMERGENCY_WARN_AT: int = 5
    # ══ [SMART ENTRY — 4-layer dip model] ══
    # Layer 1: ATR-based base dip
    ENTRY_ATR_MULT: float = 0.40            # base_dip = k × ATR
    ENTRY_MIN_DIP_MULT: float = 0.15        # clamp: ≥ 0.15 × ATR
    ENTRY_MAX_DIP_MULT: float = 1.00        # clamp: ≤ 1.00 × ATR
    # Layer 2: regime scaling
    ENTRY_REGIME_SCALE: bool = True
    ENTRY_REGIME_LOOKBACK: int = 100
    ENTRY_REGIME_RANGING_MULT: float = 0.60
    ENTRY_REGIME_TRENDING_MULT: float = 1.00
    ENTRY_REGIME_EXPLOSIVE_MULT: float = 1.30
    # Layer 3: structure anchor (nearest swing)
    ENTRY_STRUCTURE_ANCHOR: bool = True
    ENTRY_STRUCTURE_MIN_ADV_USD: float = 1e8   # only liquid assets
    ENTRY_STRUCTURE_RANGE_MULT_LO: float = 0.30  # don't anchor closer than this × dip
    ENTRY_STRUCTURE_RANGE_MULT_HI: float = 2.00  # don't anchor farther than this × dip
    ENTRY_STRUCTURE_BUFFER_MULT: float = 0.10    # buffer above support = 0.1 × ATR
    # Layer 4: time decay (applied during repricing)
    # [DISABLED] Restored from diagnostic: with base dip = 0.34%,
    # Stage-3 decays it to 0.10% — essentially a market order.
    # With the restored friction dip (≈2%), time decay would chase
    # the market down and destroy the mean-reversion edge.
    ENTRY_TIME_DECAY: bool = False
    ENTRY_TIME_DECAY_BARS_1: int = 5
    ENTRY_TIME_DECAY_BARS_2: int = 10
    ENTRY_TIME_DECAY_BARS_3: int = 15
    ENTRY_TIME_DECAY_BARS_4: int = 20
    ENTRY_TIME_DECAY_MULT_1: float = 0.70
    ENTRY_TIME_DECAY_MULT_2: float = 0.50
    ENTRY_TIME_DECAY_MULT_3: float = 0.30
    # ══ [SUB-BAR PRECISION] ══
    # Resolves intrabar path ambiguity in backtest by using finer bars
    # around the entry bar and (optionally) exit bars.
    SUBBARS_ENABLED: bool = True
    SUBBARS_REFINE_ENTRY_ONLY: bool = True    # True → refine entry bar only
                                              # False → refine all bars (heavy)
    SUBBARS_MAX_ASSETS: int = 0               # 0 = no cap (all symbols)
    # ══ [ADVANCED TRAILING — Physics-Adaptive Chandelier] ══
    TRAIL_ADVANCED_ENABLED: bool = True
    # Chandelier: SL = peak - k × ATR_current
    TRAIL_CHANDELIER_K: float = 0.50
    TRAIL_ACTIVATE_SIGMA_MULT: float = 0.40
    TRAIL_RATCHET_LEVELS: Tuple = (
        (0.4, 0.10),
        (0.6, 0.30),
        (0.8, 0.50),
        (1.0, 0.70),
        (1.5, 1.20),
        (2.0, 1.70),
        (3.0, 2.70),
        (4.0, 3.70),
        (5.0, 4.70),
    )
    TRAIL_MIN_R_FRACTION: float = 0.3
    TRAIL_PHYSICS_ENABLED: bool = True
    TRAIL_ACCEL_SCALE: float = 0.005
    TRAIL_FRICTION_SCALE: float = 0.15
    TRAIL_GAUGE_SCALE: float = 0.20
    TRAIL_PHYSICS_CLAMP: Tuple = (0.7, 1.3)
    TRAIL_REGIME_ENABLED: bool = True
    TRAIL_REGIME_LOOKBACK: int = 100
    TRAIL_REGIME_EXPLOSIVE_MULT: float = 1.1
    TRAIL_REGIME_TRENDING_MULT: float = 1.0
    TRAIL_REGIME_RANGING_MULT: float = 0.9
    TRAIL_LEGACY_FLOOR_ENABLED: bool = True
    # Structure anchoring
    TRAIL_STRUCTURE_ENABLED: bool = True
    TRAIL_STRUCTURE_LOOKBACK: int = 50
    TRAIL_STRUCTURE_BUFFER_SIGMA: float = 0.3
    # Time decay
    TRAIL_TIME_DECAY_ENABLED: bool = True
    TRAIL_TIME_DECAY_BARS: int = 20
    TRAIL_TIME_DECAY_FACTOR: float = 0.85
    TRAIL_TIME_DECAY_MIN_MULT: float = 0.5
    # API throttling
    TRAIL_MIN_STEP_FRAC: float = 0.0015
    TRAIL_UPDATE_MIN_INTERVAL_S: int = 3

    # ══ [LATENCY FIX — Exits] ══
    # Urgent exits (Emergency SL, Hard TP, LiqProximity) must not wait
    # for post-only. They cross the spread (marketable limit) — cost is
    # ~1 spread (~2-5 bps), not the 5-25% slippage of a raw market order.
    PO_EXIT_MAX_WAIT_S: int = 12            # was 45 (still used for soft exits)
    PO_EXIT_URGENT_WAIT_S: int = 4          # for SL/TP/LiqProximity
    PO_EXIT_URGENT_CROSS_SPREAD: bool = True
    # ══ [BACKTEST↔LIVE PARITY] ══
    # When True, backtest behaves like live:
    #   - Uses the same entry timeout as live (PO_MAX_WAIT_S seconds)
    #   - Applies time-decay repricing (if ENTRY_TIME_DECAY enabled)
    #   - Applies LevCap (caps leverage by MMR)
    #   - Applies LiqGate (rejects signals with SL too close to Liq)
    # Set to False to restore the legacy "generous" backtest.
    SIMULATE_LIVE_FAITHFULLY: bool = True
    # ══ [FIX 1 — TRAILING ACTIVATION AT R-MULTIPLE] ══
    # Old design activated trailing after a fixed MFE (0.4%), which was
    # often BELOW the SL distance. So SL moved above entry on tiny moves
    # and killed 52% of trades with a "profitable SL" that capped gains.
    # New design: trailing only activates after N × sl_dist_initial of MFE.
    TRAIL_ACTIVATE_AT_R: float = 2.5    # activate at +1R of profit

    # ══ [FIX 2 — REGIME FILTER] ══
    # Skip signals when EMA200 slope (over lookback) is too steep
    # relative to ATR. Mean-reversion hates trending markets.
    REGIME_FILTER_ENABLED: bool = False
    REGIME_EMA_LOOKBACK: int = 50
    REGIME_SLOPE_ATR_MAX: float = 2.0   # |slope×bars|/ATR > this → skip

    # ══ [FIX 3 — TIME-BASED KILL] ══
    # If after N bars the trade hasn't reached TIME_KILL_MIN_R, close it.
    TIME_KILL_ENABLED: bool = False
    TIME_KILL_BARS: int = 10            # bars to wait (TF-scaled)
    TIME_KILL_MIN_R: float = 0.5        # must reach +0.5R by then

    # ══ [FIX 4 — PARTIAL TAKE-PROFIT] ══
    # Close PARTIAL_TP_PCT of the position at +PARTIAL_TP_R, let the
    # rest ride with trailing.
    PARTIAL_TP_ENABLED: bool = True
    PARTIAL_TP_R: float = 3.5           # [ABL4a] 3.0 -> 1.5
    PARTIAL_TP_PCT: float = 0.50         # close 50% at that level
    TP_MULT: float = 7.0    # كان 2.0 → الآن 1.5 (R:R = 1.5)
    APEX_ENABLED: bool = False     # عطّله مؤقتاً حتى نضبط عتباته

    # ══ [BREAKEVEN SL — protect trades that reach +N R] ══
    # عند تفعيل --no-trailing، يعمل هذا الميكانيزم المستقل.
    # يحمي 30% من الصفقات التي تلمس +1R قبل الانعكاس.
    BREAKEVEN_ENABLED: bool = True
    BREAKEVEN_AT_R: float = 1.0

    # ══ [SINGULARITY TIMING LAYER 1 — EMERGING] ══
    # طبقة توقيت تكشف الرنين الكسري قبل الانفجار بدقائق وتُعجّل
    # الأمر المعلّق دون تغيير أي منطق آخر. معطّلة افتراضياً.
    SING_TIMING_ENABLED: bool = False       # المفتاح الرئيسي
    # [DEPRECATED — تم استبدالها بالمراتب المئوية]
    # SING_RESONANCE_THETA, SING_JERK_MIN, SING_JERK_LAMBDA,
    # SING_JERK_PERSIST, SING_RHO_EMERGING, SING_RHO_ACTIVE
    # احتُفظ بها للتوافق مع الإصدارات السابقة، لكنها غير مستخدمة.
    SING_PENDING_WAIT_EMERGING: int = 2     # شموع الانتظار في EMERGING
    SING_PENDING_WAIT_ACTIVE: int = 1       # شموع الانتظار في ACTIVE
    # ══ [Percentile Thresholds] ══
    SING_LOOKBACK_BARS: int = 200
    SING_PCT_EMERGING: float = 0.70
    SING_PCT_ACTIVE: float = 0.90
    SING_PCT_AGAINST_DECAY: float = 0.50
    # ══ [SINGULARITY TIMING LAYER 2 — ACTIVE MARKETABLE] ══
    # عند حالة ACTIVE، يستبدل الأمر GTX بأمر Marketable Limit
    # يقطع السبريد جزئياً ليمتلئ فوراً. معطّلة افتراضياً.
    SING_ACTIVE_MARKETABLE: bool = True
    SING_ACTIVE_PENETRATION_BPS: float = 3.0   # اختراق السبريد
    SING_ACTIVE_MAX_SLIP_BPS: float = 15.0     # أقصى انزلاق عن سعر النفق
    SING_ACTIVE_MIN_FILL_RATIO: float = 0.5    # أدنى نسبة امتلاء مقبولة
    # ══ [SINGULARITY TIMING LAYER 3 — Funding Guard + Risk Boost] ══
    # 3A: Funding Guard — تجنّب الدخول قبل موعد التمويل بـ N دقيقة.
    # 3B: Resonance Risk Boost — رفع المخاطرة عند ACTIVE.
    # كلاهما معطّل افتراضياً.
    SING_FUNDING_GUARD_ENABLED: bool = False    # 3A
    SING_FUNDING_GUARD_MINUTES: int = 30         # نافذة التجنّب
    SING_FUNDING_HOURS_UTC: Tuple = (0, 8, 16)   # مواعيد Binance الثابتة
    SING_RISK_BOOST_ENABLED: bool = False        # 3B
    SING_RISK_BOOST_ACTIVE: float = 1.20         # مضاعف المخاطرة في ACTIVE
    SING_RISK_BOOST_EMERGING: float = 1.00       # مضاعف في EMERGING (لا تغيير)
    # ══ [SING-TIMING Layer 1 — Percentile Thresholds] ══
    # بدلاً من عتبات مطلقة (التي لا تتكيف مع تقلب كل أصل)، نستخدم
    # مراتب مئوية محسوبة من نافذة زمنية متدحرجة على geodesic_accel.
    SING_LOOKBACK_BARS: int = 200         # نافذة حساب المراتب
    SING_PCT_EMERGING: float = 0.70       # أعلى 30% → EMERGING
    SING_PCT_ACTIVE: float = 0.90         # أعلى 10% → ACTIVE
    SING_PCT_AGAINST_DECAY: float = 0.50  # إذا كان التسارع في الاتجاه المعاكس

    # ══ [TRADE FILTER — Pre-entry rejection] ══
    # فلتر متعدد الإشارات يعمل داخل build_signals قبل إضافة الإشارة.
    # يقبل الإشارة إلا إذا اجتمع عليها عدد كافٍ من "أصوات الرفض".
    #
    # ملاحظة مهمة: FILTER_USE_ACTION_BIAS معطّل افتراضياً لأن
    # التشخيص أظهر أنه انحياز نظام (85% احتمال) وليس حافة حقيقية.
    # فعّله فقط إذا أثبتت اختبارات الاستقرار الزمني أنه حقيقي.
    FILTER_ENABLED: bool = False        # المفتاح الرئيسي (معطّل افتراضياً)

    # الأصوات الفردية (كل صوت = سبب مستقل للرفض)
    FILTER_USE_ACTION_BIAS: bool = False   # ⚠️ انحياز نظام — معطّل
    FILTER_USE_EMA_SLOPE: bool = True      # ✅ بنيوي — مفعّل
    FILTER_USE_HIGH_ATR: bool = True       # ✅ عام — مفعّل
    FILTER_USE_FRICTION_DRAG: bool = True  # ✅ هندسي — مفعّل

    # العتبات
    FILTER_ATR_FRAC_MAX: float = 0.024      # atr_frac فوق هذا = تقلب مرتفع
    FILTER_FRICTION_DRAG_MAX: float = 2.5   # friction_drag/sl_dist فوق هذا = R:R ضعيف

    # الحد الأدنى للأصوات المطلوبة للرفض
    FILTER_MIN_VOTES: int = 2               # يحتاج صوتين على الأقل

    # التسجيل والتحليل
    FILTER_LOG_REJECTIONS: bool = False     # سجّل كل رفض في LOG
    # ══ [WATCH-THEN-TRIGGER — proximity + structure gate] ══
    WATCH_MODE_ENABLED: bool = False
    WATCH_PROX_KAPPA: float = 0.5
    WATCH_SWING_LOOKBACK: int = 60
    WATCH_SWING_BUFFER_MULT: float = 0.3
    WATCH_OPP_P_ACT_MIN: float = 0.35
    WATCH_OPP_SCORE_RATIO: float = 0.85
    WATCH_OPP_ACCEL_RATIO_MAX: float = 2.0
    WATCH_PHASE1_TIMEOUT_BARS_1H: int = 16
    WATCH_PHASE1_ABORT_SCORE: float = 0.5
    WATCH_PHASE1_ABORT_P_ACT: float = 0.30
    WATCH_FILE_PREFIX: str = "watch_signals"
    WATCH_MAX_PER_CYCLE: int = 5          # cap triggers per loop iteration
    # ══ [OPPOSITE-SIGNAL ADAPTIVE TP] ══
    # عندما تظهر إشارة معاكسة على نفس الأصل لمركز مفتوح،
    # يُنقل TP للمركز إلى موقع tunnel_entry_p للإشارة المعاكسة،
    # بشرط أن يكون ذلك أقرب إلى الدخول (monotonic) وأعلى من حد ربح أدنى.
    OPP_TP_ENABLED: bool = False
    OPP_TP_SCORE_MULT: float = 1.20          # score_opp ≥ 1.2 × score_entry
    OPP_TP_MIN_PROFIT_R: float = 0.5         # ربح أدنى مضمون بوحدات R
    OPP_TP_MIN_DELTA_R: float = 0.3          # تحسّن أدنى لنقل TP
    OPP_TP_MAX_AGE_BARS: int = 4             # عمر الإشارة المعاكسة
    OPP_TP_RESPECT_PARTIAL: bool = True      # لا تنقل TP تحت trigger partial
    # ══ [WATCH ENTRY OFFSET — dynamic, fills on touch] ══
    # الأمر يُوضع في اتجاه يواجه السعر الهابط/الصاعد، ليملأ عند أول تلامس.
    # BUY : order = tunnel + offset  (above)
    # SELL: order = tunnel − offset  (below)
    WATCH_OFFSET_VOL_KAPPA: float = 0.02   # جزء من σ_bar
    WATCH_OFFSET_ADV_TIERS: Tuple = (
        (1e10, 1.0),   # ADV ≥ 10B → ×1.0
        (1e9,  1.3),   # ADV ≥ 1B  → ×1.3
        (1e8,  1.8),   # ADV ≥ 100M → ×1.8
        (1e7,  3.0),   # ADV ≥ 10M → ×3.0
        (0.0,  5.0),   # ADV < 10M → ×5.0
    )
    WATCH_OFFSET_MAX_BPS: float = 30.0
    WATCH_OFFSET_MIN_BPS: float = 1.0
    # ══ [GAUGE FILTER — الأداء المُتحقَّق منه] ══
    # بناءً على تحليل 6973 صفقة على 365 يوم:
    #   BUY + gauge>p60: avg_pnl $99.89 (+178%), Sharpe 2.571
    #   SELL ضعيف دائماً: أفضل حالة top10% = avg $59/صفقة
    # النتيجة: SELL يحتاج عتبة عالية جداً أو إلغاء كامل
    GAUGE_FILTER_ENABLED: bool = True
    GAUGE_PERCENTILE_BUY: float = 0.60
    GAUGE_PERCENTILE_SELL: float = 0.95   # [ABL8b] 0.85 -> 0.95
    GAUGE_MIN_SAMPLES: int = 500       # أدنى عينة لحساب percentile
    # [ABL10] confirmed BUY-only across 2024/2025/2026:
    # Min Sharpe 1.606 (vs 0.937 baseline), GeoFinal $1,873
    GAUGE_DISABLE_SELL: bool = True    # Default: BUY-only

    # ══ [SELL-RND] معاملات بحث SELL المستقل ══
    # عند SELL_ENABLED=False، هذا كله غير مفعّل.
    # BUY غير متأثر إطلاقاً.
    SELL_ENABLED: bool = False              # master switch
    SELL_MIN_SCORE: int = 3                 # independent from BUY
    SELL_MIN_ZDEV: float = 1.5              # independent from BUY
    SELL_GAUGE_PCT: float = 0.95            # current default
    SELL_REQUIRE_EMA_DOWN: bool = False     # trend-aligned SELL
    SELL_MAJOR_ONLY: bool = False           # only BTC/ETH/SOL/BNB
    SELL_MIN_ATR_FRAC: float = 0.0          # 0 = no gate
    SELL_MAJOR_PAIRS: Tuple = ("BTC/USDT", "ETH/USDT",
                                "SOL/USDT", "BNB/USDT")

CFG = Config()


def _resolve_end_datetime() -> datetime:
    """[END-DATE-HELPER] يحل نهاية نافذة البيانات."""
    _raw = getattr(CFG, 'BACKTEST_END_DATE', None)
    if _raw:
        try:
            _dt = datetime.strptime(str(_raw), "%Y-%m-%d")
            return (_dt.replace(tzinfo=timezone.utc)
                    + timedelta(days=1)
                    - timedelta(seconds=1))
        except Exception as _e:
            log.warning("[EndDate] parse failed: %s -- using now()" % _e)
    return datetime.now(timezone.utc)

# ════════════════════════════════════════════════════════════════
# § TRADE LOGGER — Universal (backtest / testnet / live)
# ════════════════════════════════════════════════════════════════
# يسجّل كل صفقة في ملف JSONL موحّد للتحليل الخارجي.
# يعمل في الأوضاع الثلاثة بنفس الصيغة → قابل للمقارنة.

_TRADE_LOG_PATH = None


def _trade_log_init(mode: str, explicit_path: Optional[str] = None):
    """Initialize trade log file for the current run."""
    global _TRADE_LOG_PATH
    if explicit_path:
        _TRADE_LOG_PATH = explicit_path
    else:
        _TRADE_LOG_PATH = f"trades_log_{mode}.jsonl"
    try:
        # [DUPLICATE-FIX] append mode — keep prior trades
        with open(_TRADE_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                '_meta': True,
                'mode': mode,
                'timeframe': CFG.timeframe,
                'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'N': CFG.N, 'W': CFG.W, 'L': CFG.L,
                'K_MAX': CFG.K_MAX, 'K_MIN': CFG.K_MIN,
                'INITIAL_CAPITAL': CFG.INITIAL_CAPITAL,
                'LEVERAGE_BASE': CFG.LEVERAGE_BASE,
                'PO_FIXED_PRICE': CFG.PO_FIXED_PRICE,
                'GAUGE_DISABLE_SELL': CFG.GAUGE_DISABLE_SELL,
                'TRAIL_ENABLED': CFG.TRAIL_ENABLED,
            }, default=str) + "\n")
        log.info(f"[TradeLog] Logging trades to {_TRADE_LOG_PATH}")
    except Exception as e:
        log.warning(f"[TradeLog] init failed: {e}")
        _TRADE_LOG_PATH = None


def _trade_log_write(record: Dict) -> None:
    """Append one trade record (non-blocking, fail-safe)."""
    if _TRADE_LOG_PATH is None:
        return
    try:
        with open(_TRADE_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as e:
        log.debug(f"[TradeLog] write failed: {e}")


def _extract_entry_features_for_log(sig, ad=None) -> Dict:
    """Extract features at entry time (no look-ahead)."""
    out = {}
    try:
        out['score'] = float(getattr(sig, 'score', 0.0))
        out['action'] = str(getattr(sig, 'action', '?'))
        out['signal_price'] = float(getattr(sig, 'price', 0.0))
        out['signal_sl'] = float(getattr(sig, 'sl', 0.0))
        out['signal_tp1'] = float(getattr(sig, 'tp1', 0.0))
        out['atr'] = float(getattr(sig, 'atr', 0.0))
        out['tri_val'] = float(getattr(sig, 'tri_val', 0.0))
        out['dynamic_risk'] = float(getattr(sig, 'dynamic_risk', 0.0))
        out['T_info_val'] = float(getattr(sig, 'T_info_val', 0.0))
        out['dyn_sl_factor'] = float(getattr(sig, 'dyn_sl_factor', 0.0))
        out['adv_usd'] = float(getattr(sig, 'adv_usd', 0.0))
        out['feat_idx'] = int(getattr(sig, 'feat_idx', -1))
        out['close_idx'] = int(getattr(sig, 'close_idx', -1))

        # Geometry
        p = out['signal_price']
        sl = out['signal_sl']
        tp = out['signal_tp1']
        if p > 0:
            out['sl_dist_frac'] = abs(p - sl) / p
            out['rr_design'] = abs(tp - p) / max(abs(p - sl), 1e-12)

        # Asset features at feat_idx
        if ad is not None:
            fi = out['feat_idx']
            if 0 <= fi < len(ad.E_therm):
                out['E_therm'] = float(ad.E_therm[fi])
                out['friction'] = float(ad.friction[fi])
                out['gauge_force'] = float(ad.gauge_force[fi])
                out['delta_gap'] = float(ad.delta_gap[fi])
                out['geodesic_accel'] = float(ad.geodesic_accel[fi])
                out['H'] = float(ad.H[fi])
                out['dH'] = float(ad.dH[fi])
                out['dF'] = float(ad.dF[fi])
                out['T_info'] = float(ad.T_info[fi])
                out['V'] = float(ad.V[fi])
                out['C'] = float(ad.C[fi])
                _dyn_k = max(int(getattr(ad, 'dynamic_k', 2)), 2)
                Hmax = np.log2(_dyn_k) + 1e-12
                out['H_over_Hmax'] = out['H'] / Hmax

                # Sigma-normalized geometry
                sigma_frac = out['E_therm'] if out['E_therm'] > 1e-6 else 0.01
                sigma_price = sigma_frac * p
                fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))
                fd = fd_kappa * sigma_price
                sl_dist = abs(p - sl)
                out['friction_drag_over_sl'] = fd / max(sl_dist, 1e-12)
                out['sl_sigma'] = sl_dist / max(sigma_price, 1e-12)

                # EMA slope against
                ci = out['close_idx']
                if 0 <= ci < len(ad.ema200) and ci >= 50:
                    ema_now = float(ad.ema200[ci])
                    ema_prev = float(ad.ema200[ci - 50])
                    slope = (ema_now - ema_prev) / 50.0
                    out['ema_slope'] = float(slope)
                    out['ema_slope_against'] = 1.0 if (
                        (out['action'] == 'BUY' and slope < 0) or
                        (out['action'] == 'SELL' and slope > 0)
                    ) else 0.0
                    out['dist_from_ema_norm'] = float(
                        (p - ema_now) / max(sigma_price, 1e-12)
                    )
    except Exception as e:
        out['_extract_err'] = str(e)[:80]
    return out


def _trade_log_from_backtest(pos, ad, exit_px, exit_rsn, exit_ci,
                              capital_before, capital_after,
                              net_pnl=None, log_return=None):
    """Called from simulate_portfolio._close()."""
    try:
        sig = pos.signal
        # [P1.1-L] trade-level PnL when supplied by _close; capital-delta
        # is polluted by concurrent trades (see N4)
        _cap_delta = float(capital_after - capital_before)
        net = float(net_pnl) if net_pnl is not None else _cap_delta
        if log_return is not None:
            lr = float(log_return)
        else:
            lr = float(np.log(capital_after / capital_before)) \
                if capital_before > 0 else 0.0
        rec = {
            'mode': 'backtest',
            'symbol': str(sig.symbol),
            'entry_time': str(sig.timestamp),
            'entry_price': float(pos.entry_px),
            'exit_price': float(exit_px),
            'exit_reason': str(exit_rsn),
            'pos_size': float(pos.pos_size),
            'net_pnl': net,
            'log_return': lr,
            'cap_delta_since_entry': _cap_delta,
            'partial_pnl': float(getattr(pos, 'partial_pnl', 0.0)),
            'capital_before': float(capital_before),
            'capital_after': float(capital_after),
            'is_win': bool(net > 0),
            'mfe_frac': float(getattr(pos, 'mfe_frac', 0.0)),
            'entry_ci': int(pos.entry_ci),
            'exit_ci': int(exit_ci),
            'hold_bars': int(exit_ci - pos.entry_ci),
            'sl_dist_initial': float(getattr(pos, 'sl_dist_initial', 0.0)),
        }
        rec.update(_extract_entry_features_for_log(sig, ad))
        _trade_log_write(rec)
    except Exception as e:
        log.debug(f"[TradeLog] backtest log failed: {e}")


def _trade_log_from_live(pos: Dict, exit_px: float, exit_rsn: str,
                          ad=None, net_pnl=None):
    """Called from run_live after successful exit."""
    try:
        rec = {
            'mode': str(CFG.mode),
            'symbol': str(pos.get('_sym') or pos.get('symbol') or '?'),
            'entry_time': str(pos.get('entry_ts', 0)),
            'entry_price': float(pos.get('entry', 0.0)),
            'exit_price': float(exit_px),
            'exit_reason': str(exit_rsn),
            'pos_size': float(pos.get('qty', 0.0)),
            'net_pnl': net_pnl,
            'leverage': int(pos.get('leverage', 0)),
            'dyn_risk': float(pos.get('dyn_risk', 0.0)),
            'T_info_val': float(pos.get('T_info', 0.0)),
            'sl_dist_initial': float(pos.get('sl_dist_initial', 0.0)),
            'fill_ratio': float(pos.get('fill_ratio', 0.0)),
            'action': str(pos.get('action', '?')),
            'stage': str(pos.get('stage', 'S1')),
            '_entry_fi': int(pos.get('_entry_fi', -1)),
            '_entry_ci': int(pos.get('_entry_ci', -1)),
        }
        # Minimal feature extraction from ad if available
        if ad is not None:
            try:
                _fi = rec['_entry_fi']
                _ci = rec['_entry_ci']
                if 0 <= _fi < len(ad.E_therm):
                    rec['E_therm'] = float(ad.E_therm[_fi])
                    rec['friction'] = float(ad.friction[_fi])
                    rec['gauge_force'] = float(ad.gauge_force[_fi])
                    rec['delta_gap'] = float(ad.delta_gap[_fi])
                    rec['geodesic_accel'] = float(ad.geodesic_accel[_fi])
                    rec['H'] = float(ad.H[_fi])
                    rec['T_info'] = float(ad.T_info[_fi])
                    rec['V'] = float(ad.V[_fi])
                    _dyn_k = max(int(getattr(ad, 'dynamic_k', 2)), 2)
                    Hmax = np.log2(_dyn_k) + 1e-12
                    rec['H_over_Hmax'] = rec['H'] / Hmax
                if 0 <= _ci < len(ad.ema200) and _ci >= 50:
                    ema_now = float(ad.ema200[_ci])
                    ema_prev = float(ad.ema200[_ci - 50])
                    slope = (ema_now - ema_prev) / 50.0
                    rec['ema_slope'] = float(slope)
                    rec['ema_slope_against'] = 1.0 if (
                        (rec['action'] == 'BUY' and slope < 0) or
                        (rec['action'] == 'SELL' and slope > 0)
                    ) else 0.0
            except Exception:
                pass
        _trade_log_write(rec)
    except Exception as e:
        log.debug(f"[TradeLog] live log failed: {e}")


def _resolve_data_params(cfg, mode: str, tf_hours: float,
                          user_history_days: Optional[int] = None
                          ) -> Tuple[int, int, int, str, str]:
    """
    Unified resolver for (history_days, tail_bars, min_bars_for_process).
    Works for 1m … 1d and for backtest / testnet / live.

    Design principle:
      - BACKTEST prioritizes statistical power (max useful history).
      - LIVE / TESTNET prioritize lightness (minimum for K=K_max).
      - User override is respected, but physically clamped and quality-warned.

    Physical constants:
      strict_min_bars : minimum n_bars such that K is NOT data-capped
                        = 2 * K_MAX * K_MIN_TRAIN_POINTS_PER_CLUSTER + N
                        (default: 2*12*100 + 24 = 2424)
      MAX_HISTORY_DAYS: 730 (Binance USDT-M futures age)
      MIN_HISTORY_DAYS: 3
      absolute_floor  : max(N + W + 100, 500) — absolute minimum to process

    Mode-dependent hard cap on bars per symbol:
      backtest        : 40000 bars (~40 API pages, ~12 s/symbol)
      live / testnet  : 20000 bars (~20 API pages, ~6 s/symbol)

    Returns:
      (history_days, tail_bars, min_bars, source_label, quality_label)
      quality_label ∈ {"full", "reduced", "degraded"}
    """
    N = int(cfg.N); W = int(cfg.W)
    min_pts = int(getattr(cfg, 'K_MIN_TRAIN_POINTS_PER_CLUSTER', 100))
    K_max = int(cfg.K_MAX)

    # ── Physical constants ──
    strict_min_bars = 2 * K_max * min_pts + N         # 2424
    MAX_HISTORY_DAYS = 730
    MIN_HISTORY_DAYS = 3
    absolute_floor = max(N + W + 100, 500)

    bars_per_day = 24.0 / max(tf_hours, 1e-6)

    # ── Mode-dependent hard cap ──
    if mode == "backtest":
        HARD_CAP_BARS = 40000
    else:
        HARD_CAP_BARS = 20000

    # ── Determine history_days ──
    if user_history_days is not None and user_history_days > 0:
        # User explicit override — respect, but clamp physically
        hd = int(user_history_days)
        capped_high = False
        if hd > MAX_HISTORY_DAYS:
            hd = MAX_HISTORY_DAYS
            capped_high = True
        if hd < MIN_HISTORY_DAYS:
            hd = MIN_HISTORY_DAYS
        source = f"user({user_history_days}d)"
        if capped_high:
            source += f"-cap{hd}"
    else:
        # Auto: derive from mode + TF
        if mode == "backtest":
            # Want as much history as possible, but not more than
            # HARD_CAP_BARS per symbol (fetch time bound).
            days_from_cap = int(HARD_CAP_BARS / bars_per_day)
            # Also ensure ≥1.5× strict_min for statistical margin
            days_from_min = int(np.ceil(strict_min_bars * 1.5 / bars_per_day))
            hd = max(days_from_min, days_from_cap)
            hd = min(hd, MAX_HISTORY_DAYS)
            hd = max(hd, MIN_HISTORY_DAYS)
        else:
            # Live / testnet: minimum with 40% safety margin
            days_needed = int(np.ceil(strict_min_bars * 1.4 / bars_per_day))
            hd = max(MIN_HISTORY_DAYS, days_needed)
            hd = min(hd, MAX_HISTORY_DAYS)
        source = f"auto({mode})"

    # ── tail_bars derived from history_days ──
    tail_bars = int(hd * bars_per_day)
    if tail_bars > HARD_CAP_BARS:
        hd = max(MIN_HISTORY_DAYS, int(np.floor(HARD_CAP_BARS / bars_per_day)))
        tail_bars = int(hd * bars_per_day)
        source += f"-cap{HARD_CAP_BARS}"

    # ── min_bars_for_process ──
    # Want strict_min_bars when possible, but never exceed tail_bars.
    min_bars = max(absolute_floor, min(strict_min_bars, tail_bars))

    # ── Quality assessment ──
    if tail_bars >= strict_min_bars:
        quality = "full"
    elif tail_bars >= strict_min_bars // 2:
        quality = "reduced"
    else:
        quality = "degraded"

    return int(hd), int(tail_bars), int(min_bars), source, quality

# ════════════════════════════════════════════════════════════════
# § 1  مسح الأصول
# ════════════════════════════════════════════════════════════════

#def _default_assets():
#    return ["BTC/USDT","ETH/USDT","BNB/USDT","SOL/USDT","XRP/USDT",
#            "DOGE/USDT","AVAX/USDT","LINK/USDT","DOT/USDT",
#            "LTC/USDT","UNI/USDT","ATOM/USDT","ETC/USDT","POL/USDT"]

#def _default_assets():
#    return ["BTC/USDT","ETH/USDT","BNB/USDT","SOL/USDT","XRP/USDT",
#            "DOGE/USDT","ADA/USDT","AVAX/USDT","LINK/USDT","DOT/USDT",
#            "LTC/USDT","UNI/USDT","ATOM/USDT","ETC/USDT","POL/USDT",
#            "TRX/USDT","TON/USDT","BCH/USDT","NEAR/USDT",
#            "APT/USDT","HBAR/USDT","VET/USDT",
#            "AAVE/USDT","ARB/USDT",
#            "OP/USDT","INJ/USDT","SUI/USDT","TIA/USDT","SEI/USDT",
#            "ALGO/USDT","GRT/USDT","FET/USDT","RENDER/USDT",
#            "LDO/USDT","KAS/USDT","WIF/USDT","THETA/USDT","EGLD/USDT",
#            "SAND/USDT","MANA/USDT","AXS/USDT","XLM/USDT","CHZ/USDT"]
#def _default_assets():
#    # أعلى 50 عملة من حيث القيمة السوقية مع قبول رافعة 50x على Binance Futures
#    return [
#        "BTC/USDT",   # بيتكوين - أعلى سيولة، رافعة 125x
#        "ETH/USDT",   # إيثيريوم - ثاني أعلى سيولة، رافعة 100x
#        "BNB/USDT",   # بيнанс كوين - رافعة 75x
#        "SOL/USDT",   # سولانا - رافعة 50x
#        "XRP/USDT",   # ريبل - رافعة 50x
#        "DOGE/USDT",  # دوجكوين - رافعة 50x
#        "ADA/USDT",   # كاردانو - رافعة 50x
#        "AVAX/USDT",  # أفالانش - رافعة 50x
#        "LINK/USDT",  # تشين لينك - رافعة 50x
#        "DOT/USDT",   # بولكادوت - رافعة 50x
#        "LTC/USDT",   # لايتكوين - رافعة 50x
#        "UNI/USDT",   # يونيسواب - رافعة 50x
#        "ATOM/USDT",  # كوزموس - رافعة 50x
#        "ETC/USDT",   # إيثيريوم كلاسيك - رافعة 50x
#        "TRX/USDT",   # ترون - رافعة 50x
#        "TON/USDT",   # تون كوين - رافعة 50x
#        "BCH/USDT",   # بيتكوين كاش - رافعة 50x
#        "NEAR/USDT",  # نير بروتوكول - رافعة 50x
#        "APT/USDT",   # أبتوس - رافعة 50x
#        "HBAR/USDT",  # هيدرا - رافعة 50x
#        "VET/USDT",   # في تشين - رافعة 50x
#        "STX/USDT",   # ستاكس - رافعة 50x
#        "AAVE/USDT",  # آفي - رافعة 50x
#        "ARB/USDT",   # أربيتروم - رافعة 50x
#        "OP/USDT",    # أوبتيميزم - رافعة 50x
#        "INJ/USDT",   # إنجكتيف - رافعة 50x
#        "SUI/USDT",   # سوي - رافعة 50x
#        "TIA/USDT",   # سيليستيا - رافعة 50x
#        "SEI/USDT",   # ساي - رافعة 50x
#        "ALGO/USDT",  # ألجوراند - رافعة 50x
#        "GRT/USDT",   # ذا غراف - رافعة 50x
#        "FET/USDT",   # فيتشد أيه آي - رافعة 50x
#        "RENDER/USDT",# ريندر - رافعة 50x
#        "LDO/USDT",   # ليدو داو - رافعة 50x
#        "KAS/USDT",   # كاسبا - رافعة 50x
#        "WIF/USDT",   # دوج ويف هات - رافعة 50x
#        "THETA/USDT", # ثيتا - رافعة 50x
#        "EGLD/USDT",  # مولتي فيرس إكس - رافعة 50x
#        "SAND/USDT",  # ذا ساندبوكس - رافعة 50x
#        "MANA/USDT",  # ديسنترالاند - رافعة 50x
#        "AXS/USDT",   # أكسي إنفينيتي - رافعة 50x
#        "XLM/USDT",   # ستيلر - رافعة 50x
#        "CHZ/USDT",   # تشيليز - رافعة 50x
#        "POL/USDT",   # بوليجون (سابقاً MATIC) - رافعة 50x
#        "FIL/USDT",   # فيل كوين - رافعة 50x
#        "QNT/USDT",   # كوانت - رافعة 50x
#        "DASH/USDT",  # داش - رافعة 50x
#        "ZEC/USDT",   # زدكاش - رافعة 50x
#        "XMR/USDT",   # مونيرو - رافعة 50x
##        "EOS/USDT"    # إيوس - رافعة 50x
#    ]

# "ADA/USDT"

def _default_assets():
    # 100 أصل: أعلى القيمة السوقية + دعم رافعة 50x+ على Binance Futures
    return [
        # --- الطبقة الأولى: أعلى سيولة ورافعة (75x-125x) ---
        "BTC/USDT",    # بيتكوين - رافعة 125x
        "ETH/USDT",    # إيثيريوم - رافعة 100x
        "BNB/USDT",    # بيнанс كوين - رافعة 75x
        "SOL/USDT",    # سولانا - رافعة 50x
#        "XRP/USDT",    # ريبل - رافعة 50x
#        "DOGE/USDT",   # دوجكوين - رافعة 50x
        "ADA/USDT",    # كاردانو - رافعة 50x
        "AVAX/USDT",   # أفالانش - رافعة 50x
        "LINK/USDT",   # تشين لينك - رافعة 50x
        "DOT/USDT",    # بولكادوت - رافعة 50x
        "LTC/USDT",    # لايتكوين - رافعة 50x
        "UNI/USDT",    # يونيسواب - رافعة 50x
        "ATOM/USDT",   # كوزموس - رافعة 50x
        "ETC/USDT",    # إيثيريوم كلاسيك - رافعة 50x
        "TRX/USDT",    # ترون - رافعة 50x
        "TON/USDT",    # تون كوين - رافعة 50x
        "BCH/USDT",    # بيتكوين كاش - رافعة 50x
        "NEAR/USDT",   # نير بروتوكول - رافعة 50x
        "APT/USDT",    # أبتوس - رافعة 50x
        "HBAR/USDT",   # هيدرا - رافعة 50x
#        "VET/USDT",    # في تشين - رافعة 50x
        "STX/USDT",    # ستاكس - رافعة 50x
        "AAVE/USDT",   # آفي - رافعة 50x
        "ARB/USDT",    # أربيتروم - رافعة 50x
        "OP/USDT",     # أوبتيميزم - رافعة 50x
#        "INJ/USDT",    # إنجكتيف - رافعة 50x
        "SUI/USDT",    # سوي - رافعة 50x
        "TIA/USDT",    # سيليستيا - رافعة 50x
        "SEI/USDT",    # ساي - رافعة 50x
        "ALGO/USDT",   # ألجوراند - رافعة 50x
        "GRT/USDT",    # ذا غراف - رافعة 50x
        "FET/USDT",    # فيتشد أيه آي - رافعة 50x
        "RENDER/USDT", # ريندر - رافعة 50x
        "LDO/USDT",    # ليدو داو - رافعة 50x
        "KAS/USDT",    # كاسبا - رافعة 50x
        "WIF/USDT",    # دوج ويف هات - رافعة 50x
        "THETA/USDT",  # ثيتا - رافعة 50x
        "SAND/USDT",   # ذا ساندبوكس - رافعة 50x
        "MANA/USDT",   # ديسنترالاند - رافعة 50x
        "AXS/USDT",    # أكسي إنفينيتي - رافعة 50x
        "XLM/USDT",    # ستيلر - رافعة 50x
        "CHZ/USDT",    # تشيليز - رافعة 50x
        "POL/USDT",    # بوليجون - رافعة 50x
        "FIL/USDT",    # فيل كوين - رافعة 50x
        "QNT/USDT",    # كوانت - رافعة 50x
        "DASH/USDT",   # داش - رافعة 50x
#        "EOS/USDT",    # إيوس - رافعة 50x
#        "FTM/USDT",    # فانتوم - رافعة 50x
        "FLOW/USDT",   # فلو - رافعة 50x
        "CAKE/USDT",   # بانكيك سواب - رافعة 50x
        "ROSE/USDT",   # أوايسيس نتوورك - رافعة 50x
#        "ZIL/USDT",    # زيلكا - رافعة 50x
#        "ONE/USDT",    # هارموني - رافعة 50x
        "IOTA/USDT",   # أيوتا - رافعة 50x
        "NEO/USDT",    # نيو - رافعة 50x
        "KAVA/USDT",   # كافا - رافعة 50x
        "CRV/USDT",    # كورف - رافعة 50x
        "SNX/USDT",    # سينثيتيكس - رافعة 50x
        "COMP/USDT",   # كومباووند - رافعة 50x
#        "MKR/USDT",    # ميكر - رافعة 50x
        "SUSHI/USDT",  # سوشي سواب - رافعة 50x
        "YFI/USDT",    # يرن فايننس - رافعة 50x
        "ZRX/USDT",    # زيرو إكس - رافعة 50x
        "BAT/USDT",    # باسيك أتنشن توكن - رافعة 50x
#        "ENJ/USDT",    # إنجين - رافعة 50x
        "ANKR/USDT",   # أنكر - رافعة 50x
#        "OCEAN/USDT",  # أوشن بروتوكول - رافعة 50x
        "BAND/USDT",   # باند بروتوكول - رافعة 50x
        "NMR/USDT",    # نوميرا - رافعة 50x
        "STORJ/USDT",  # ستورج - رافعة 50x
        "KSM/USDT",    # كوساما - رافعة 50x
#        "WAVES/USDT",  # ويفز - رافعة 50x
        "ZEN/USDT",    # هوريزن - رافعة 50x
#        "ICP/USDT",    # إنترنت كمبيوتر - رافعة 50x
        "CELO/USDT",   # سيلو - رافعة 50x
#        "AR/USDT",     # أرويف - رافعة 50x
        "MASK/USDT",   # ماسك نتوورك - رافعة 50x
        "DYDX/USDT",   # دي واي دي إكس - رافعة 50x
        "ENS/USDT",    # إيثيريوم نيم سيرفس - رافعة 50x
        "GMX/USDT",    # جي إم إكس - رافعة 50x
        "MAGIC/USDT",  # ماجيك - رافعة 50x
        "HIGH/USDT",   # هاي - رافعة 50x
        "PENDLE/USDT", # بيندل - رافعة 50x
        "JOE/USDT",    # ترايدر جو - رافعة 50x
        "CYBER/USDT",  # سايبر كونكت - رافعة 50x
        "ARKM/USDT",   # أركهام - رافعة 50x
        "WLD/USDT",    # وورلد كوين - رافعة 50x
        "BLUR/USDT",   # بلور - رافعة 50x
        "ID/USDT",     # سبيس آي دي - رافعة 50x
        "EDU/USDT",    # إيدي - رافعة 50x
#        "PEPE/USDT",   # بيبي - رافعة 50x
#        "FLOKI/USDT",  # فلوكي - رافعة 50x
#        "BONK/USDT",   # بونك - رافعة 50x
#        "MEME/USDT",   # ميم كوين - رافعة 50x
        "ORDI/USDT",   # أوردينالز - رافعة 50x
#        "1000SATS/USDT", # ساتس - رافعة 50x
        "JUP/USDT",    # جوبيتر - رافعة 50x
        "PYTH/USDT",   # بايث - رافعة 50x
        "JTO/USDT",    # جيتو - رافعة 50x
        "DYM/USDT",    # دايمنشن - رافعة 50x
        "STRK/USDT",   # ستارك نت - رافعة 50x
        "MANTA/USDT",  # مانتا - رافعة 50x
        "ALT/USDT",    # ألت لاير - رافعة 50x
        "AEVO/USDT",   # أفيفو - رافعة 50x
        "ETHFI/USDT",  # إيثير فاي - رافعة 50x
#        "BOME/USDT",   # بوك أوف ميم - رافعة 50x
        "W/USDT",      # ورم هول - رافعة 50x
        "SAGA/USDT",   # ساغا - رافعة 50x
#        "OMNI/USDT",   # أومني - رافعة 50x
#        "REZ/USDT",    # رينزو - رافعة 50x
        "BB/USDT",     # باونس بيت - رافعة 50x
        "IO/USDT",     # آي أو نت - رافعة 50x
        "ZK/USDT",     # zkSync - رافعة 50x
        "LISTA/USDT",  # ليستا - رافعة 50x
        "TAIKO/USDT",  # تايكو - رافعة 50x
        "ZRO/USDT",    # لاير زيرو - رافعة 50x
        "G/USDT",      # جي - رافعة 50x
        "RARE/USDT",   # رير - رافعة 50x
        "SYN/USDT",    # سينابس - رافعة 50x
        "MEW/USDT",    # ميو - رافعة 50x
        "MERL/USDT",   # ميرلين - رافعة 50x
        "BANANA/USDT", # بانانا - رافعة 50x
    ]

def _robust_center_scale(x):
    """
    Robust center and scale for z-scoring heavy-tailed features.
    - Center: median (immune to outliers)
    - Scale:  IQR / 1.349 (matches σ for normal distributions)
    - Fallback to mean/std if IQR is degenerate.
    Returns (center, scale) with scale > 0.
    """
    x = np.asarray(x, dtype=np.float64)
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return 0.0, 1.0
    med = float(np.median(x))
    q25, q75 = np.percentile(x, [25, 75])
    iqr = q75 - q25
    if iqr > 1e-12:
        scale = iqr / 1.349
    else:
        scale = float(np.std(x))
        if scale <= 1e-12:
            scale = 1.0
    return med, scale

def scan_top_assets(exchange, n=None) -> List[str]:
#    n = n or CFG.n_assets
#    try:
#        tickers = exchange.fetch_tickers()
#    except Exception as e:
#        log.warning(f"scan_top_assets: {e}")
#        return _default_assets()[:n]
#
#    scored = []
#    for sym, t in tickers.items():
#        if not sym.endswith("/USDT"):
#        # if not "/USDT" in sym:
#            continue
#        base = sym.replace("/USDT","")
#        if any(ex in base for ex in CFG.exclude_tokens):
#            continue
#        qv  = float(t.get("quoteVolume", 0) or 0)
#        if qv < CFG.min_quote_vol_usd:
#            continue
#        chg = abs(float(t.get("percentage",0) or 0))
#        scored.append((qv*(chg+1.0), sym))
#
#    scored.sort(key=lambda x: -x[0])
#    sel = [s for _,s in scored[:n]]
#    if not sel:
#        return _default_assets()[:n]
#    log.info(f"مسح الأصول: {len(sel)} عملة مختارة")
#    return sel
    return _default_assets()[:n]

# ════════════════════════════════════════════════════════════════
# § 2.05  Timeframe Scaling Helpers
# ════════════════════════════════════════════════════════════════

def compute_tf_scale(exchange, timeframe: str) -> Tuple[float, int, float]:
    """
    Return (scale_to_1h, seconds_per_bar, hours_per_bar).

    scale_to_1h = 3600 / seconds_per_bar
    Used to convert bar counts measured on 1h into current timeframe.
    """
    tf_sec = 3600
    try:
        tf_sec = int(exchange.parse_timeframe(timeframe))
    except Exception:
        # Fallback manual parse
        tf = timeframe.strip().lower()
        try:
            if tf.endswith('m'):
                tf_sec = int(tf[:-1]) * 60
            elif tf.endswith('h'):
                tf_sec = int(tf[:-1]) * 3600
            elif tf.endswith('d'):
                tf_sec = int(tf[:-1]) * 86400
        except Exception:
            tf_sec = 3600
    tf_sec = max(tf_sec, 1)
    tf_scale = 3600.0 / tf_sec
    tf_hours = tf_sec / 3600.0
    return tf_scale, tf_sec, tf_hours


def effective_bars(base_bars_1h: int) -> int:
    """
    Scale a bar-count that was calibrated on 1h to the current timeframe.
    Preserves the same real-time duration.

    Example (MAX_HOLD_BARS = 168 = 7 days on 1h):
        1h  → 168 bars = 7 days
        15m → 672 bars = 7 days
        4h  → 42 bars = 7 days
        1d  → 7 bars = 7 days
    """
    return max(1, int(round(base_bars_1h * CFG.TF_SCALE)))

# ════════════════════════════════════════════════════════════════
# § 2.04  Smart OHLCV Refresh Detection
# ════════════════════════════════════════════════════════════════

def _needs_ohlcv_refresh(cached_df, tf_sec: int) -> bool:
    """
    True if a new bar has opened since the last cached bar.
    Saves ~98% of fetch_ohlcv calls on 1h timeframe.
    """
    if cached_df is None or len(cached_df) == 0:
        return True
    try:
        last_bar_open_ts = int(cached_df.index[-1].timestamp())
        now_ts = int(time.time())
        current_open_ts = (now_ts // max(tf_sec, 1)) * max(tf_sec, 1)
        return last_bar_open_ts < current_open_ts
    except Exception:
        return True

# ════════════════════════════════════════════════════════════════
# [SUB-BARS] — Finer timeframe selection + loader
# ════════════════════════════════════════════════════════════════

# Aim: 6–24 sub-bars per main bar (sweet spot for path resolution).
_SUBBARS_TF_MAP = {
    "1m":  None,   # main is already finest
    "3m":  None,
    "5m":  None,
    "15m": "1m",   # 15 sub-bars
    "30m": "5m",   # 6 sub-bars
    "1h":  "5m",   # 12 sub-bars
    "2h":  "15m",  # 8 sub-bars
    "4h":  "15m",  # 16 sub-bars
    "6h":  "30m",  # 12 sub-bars
    "8h":  "30m",  # 16 sub-bars
    "12h": "1h",   # 12 sub-bars
    "1d":  "1h",   # 24 sub-bars
}


def _get_subbars_tf(main_tf: str) -> Optional[str]:
    """Return sub-bar TF for the given main TF, or None if unavailable."""
    return _SUBBARS_TF_MAP.get(str(main_tf).lower())


def _sub_per_main(main_tf: str, sub_tf: str) -> int:
    """Number of sub-bars per main bar."""
    try:
        import ccxt as _ccxt
        _ex = _ccxt.binance()
        main_s = int(_ex.parse_timeframe(main_tf))
        sub_s  = int(_ex.parse_timeframe(sub_tf))
        if sub_s <= 0: return 0
        return max(1, main_s // sub_s)
    except Exception:
        # Fallback table
        _m = {"15m":900,"30m":1800,"1h":3600,"2h":7200,"4h":14400,
              "6h":21600,"8h":28800,"12h":43200,"1d":86400}
        _s = {"1m":60,"5m":300,"15m":900,"30m":1800,"1h":3600}
        m = _m.get(main_tf); s = _s.get(sub_tf)
        if not m or not s: return 0
        return max(1, m // s)


# ════════════════════════════════════════════════════════════════
# § 2.01  Cache Health — Validation & Local Repair
# ════════════════════════════════════════════════════════════════

_REQUIRED_OHLCV = ('Open', 'High', 'Low', 'Close', 'Volume')
_TS_COL_CANDIDATES = ('ts', 'timestamp', 'time', 'date', 'datetime')


def _validate_cache_local(df, symbol: str, timeframe: str, tf_sec: int):
    """
    مرحلة الإصلاح المحلي (بدون شبكة).
    Returns: (cleaned_df | None, gap_ranges: list[(start_ts, end_ts)], issues: dict)
    """
    issues = {
        'naive_tz': 0, 'wrong_index_type': 0, 'unsorted': 0,
        'duplicates': 0, 'dtype_fixed': 0, 'nan_ohlc_dropped': 0,
        'volume_nan_filled': 0, 'invalid_dropped': 0,
        'hl_clamped': 0, 'gaps': 0,
    }
    if df is None or len(df) == 0:
        return None, [], issues

    # ── 1. Index: DateTimeIndex, tz-aware UTC ──
    if not isinstance(df.index, pd.DatetimeIndex):
        _ts_col = None
        for cand in _TS_COL_CANDIDATES:
            if cand in df.columns:
                _ts_col = cand
                break
            for c in df.columns:
                if str(c).lower() == cand:
                    _ts_col = c
                    break
            if _ts_col:
                break
        if _ts_col is not None:
            try:
                df = df.set_index(_ts_col)
                issues['wrong_index_type'] = 1
            except Exception:
                return None, [], issues
        else:
            return None, [], issues

    try:
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC')
            issues['naive_tz'] = 1
        else:
            df.index = df.index.tz_convert('UTC')
    except Exception:
        return None, [], issues

    # ── 2. Columns: ensure OHLCV exist (case-insensitive) ──
    _col_map = {}
    for req in _REQUIRED_OHLCV:
        if req in df.columns:
            continue
        for c in df.columns:
            if str(c).lower() == req.lower():
                _col_map[c] = req
                break
    if _col_map:
        df = df.rename(columns=_col_map)

    for req in _REQUIRED_OHLCV:
        if req not in df.columns:
            return None, [], issues

    # ── 3. Coerce numeric ──
    for col in _REQUIRED_OHLCV:
        if not pd.api.types.is_float_dtype(df[col]):
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                issues['dtype_fixed'] += 1
            except Exception:
                return None, [], issues

    # ── 4. Sort ──
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
        issues['unsorted'] = 1

    # ── 5. Drop duplicates ──
    n_before = len(df)
    df = df[~df.index.duplicated(keep='last')]
    issues['duplicates'] = n_before - len(df)

    # ── 6. Drop NaN in OHLC ──
    n_before = len(df)
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
    issues['nan_ohlc_dropped'] = n_before - len(df)

    # ── 7. Fill NaN in Volume with 0 ──
    vol_na = int(df['Volume'].isna().sum())
    if vol_na > 0:
        df['Volume'] = df['Volume'].fillna(0.0)
        issues['volume_nan_filled'] = vol_na

    # ── 8. Drop impossible rows ──
    n_before = len(df)
    _invalid = (
        (df['High'] < df['Low']) |
        (df['Open'] <= 0) | (df['Close'] <= 0) |
        (df['High'] <= 0) | (df['Low'] <= 0) |
        (df['Volume'] < 0)
    )
    df = df[~_invalid]
    issues['invalid_dropped'] = n_before - len(df)

    if len(df) == 0:
        return None, [], issues

    # ── 9. Clamp High/Low vs Open/Close ──
    _hi_min = df[['Open', 'Close']].max(axis=1)
    _lo_max = df[['Open', 'Close']].min(axis=1)
    _hi_bad = df['High'] < _hi_min
    _lo_bad = df['Low'] > _lo_max
    if _hi_bad.any():
        df.loc[_hi_bad, 'High'] = _hi_min[_hi_bad]
        issues['hl_clamped'] += int(_hi_bad.sum())
    if _lo_bad.any():
        df.loc[_lo_bad, 'Low'] = _lo_max[_lo_bad]
        issues['hl_clamped'] += int(_lo_bad.sum())

    # ── 10. Detect internal gaps ──
    gap_ranges = []
    if len(df) >= 2 and tf_sec > 0:
        expected = pd.Timedelta(seconds=tf_sec)
        diffs = df.index.to_series().diff()
        gap_mask = diffs > expected * 1.5
        gap_idx = np.where(gap_mask.values)[0]
        for gi in gap_idx:
            if gi == 0:
                continue
            start_ts = df.index[gi - 1] + expected
            end_ts = df.index[gi] - expected
            if start_ts <= end_ts:
                gap_ranges.append((start_ts, end_ts))
        issues['gaps'] = len(gap_ranges)

    return df, gap_ranges, issues


def _fetch_ranges(exchange, symbol: str, timeframe: str,
                   ranges: list, tf_sec: int):
    """
    جلب فترات محددة فقط من البورصة. لا يعيد تنزيل ما هو موجود.
    ranges: قائمة (start_ts, end_ts) حيث كلا العنصرين pandas Timestamp.
    """
    if not ranges:
        return None
    all_rows = []
    tf_ms = int(tf_sec) * 1000

    for (start_ts, end_ts) in ranges:
        since_ms = int(start_ts.timestamp() * 1000)
        end_ms = int(end_ts.timestamp() * 1000)
        cursor = since_ms
        _pages = 0
        while cursor <= end_ms and _pages < 500:
            try:
                chunk = exchange.fetch_ohlcv(
                    symbol, timeframe, since=cursor, limit=1000
                )
            except Exception as e:
                log.warning(f"[Cache-Health] {symbol} fetch @ {cursor} "
                            f"failed: {e}")
                break
            if not chunk:
                break
            for c in chunk:
                if since_ms <= c[0] <= end_ms:
                    all_rows.append(c)
            last_ts = chunk[-1][0]
            if last_ts >= end_ms:
                break
            new_cursor = last_ts + tf_ms
            if new_cursor <= cursor:
                break
            cursor = new_cursor
            _pages += 1
            time.sleep(0.06)

    if not all_rows:
        return None
    df = pd.DataFrame(
        all_rows,
        columns=['ts', 'Open', 'High', 'Low', 'Close', 'Volume']
    )
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = (df.set_index('ts')
            .drop_duplicates()
            .astype(float)
            .sort_index())
    return df


def _log_cache_health(symbol: str, timeframe: str,
                       issues: dict, gaps_filled: int = 0,
                       bars_fetched: int = 0):
    """يسجّل ملخصاً موجزاً فقط عند وجود مشاكل."""
    _issues = {k: v for k, v in issues.items() if v > 0}
    if not _issues and gaps_filled == 0:
        return
    _fixes = ", ".join(f"{k}={v}" for k, v in _issues.items()
                        if k != 'gaps')
    if _fixes:
        log.info(f"[Cache-Health] {symbol} {timeframe}: "
                 f"local repair [{_fixes}]")
    if gaps_filled > 0:
        log.info(f"[Cache-Health] {symbol} {timeframe}: "
                 f"filled {bars_fetched} bar(s) across "
                 f"{gaps_filled} gap(s) — network fetch")

    _CACHE_HEALTH['files_scanned'] += 1
    _CACHE_HEALTH['issues_fixed_local'] += sum(
        v for k, v in issues.items() if k != 'gaps'
    )
    _CACHE_HEALTH['gaps_found'] += gaps_filled
    _CACHE_HEALTH['bars_refetched'] += bars_fetched

def _load_cached_sub(symbol, exchange, sub_tf, days):
    """
    [SAFE HISTORY-DAYS SUB-BARS CACHE]

    نفس منطق _load_cached لكن للـ sub-bars.
    """
    fp = os.path.join(CACHE_DIR,
                      f"{symbol.replace('/','_')}_{sub_tf}_sub.parquet")
    min_rows = 500

    _sub_sec = 300
    try:
        _sub_sec = int(exchange.parse_timeframe(sub_tf))
    except Exception:
        pass
    _sub_sec = max(_sub_sec, 1)

    now_utc = datetime.now(timezone.utc)
    # [END-DATE-CUTOFF]
    _end_dt = _resolve_end_datetime()
    since_full_dt = _end_dt - timedelta(days=int(days))
    since_full = exchange.parse8601(since_full_dt.isoformat() + "Z")

    df = None

    # ═══ 1. قراءة الكاش + forward-update ═══
    if os.path.exists(fp):
        try:
            df_old = pd.read_parquet(fp)
            if df_old.index.tz is None:
                df_old.index = pd.to_datetime(df_old.index, utc=True)
            last_ts = df_old.index.max()
            since = exchange.parse8601(
                (last_ts + timedelta(seconds=_sub_sec)).isoformat() + "Z")
            rows = []
            try:
                while True:
                    chunk = exchange.fetch_ohlcv(
                        symbol, sub_tf, since=since, limit=1000
                    )
                    if not chunk:
                        break
                    rows.extend(chunk)
                    since = chunk[-1][0] + 1
                    time.sleep(0.06)
            except Exception as e:
                log.warning(f"[SubBars] {symbol} update: {e}")

            if rows:
                df_new = pd.DataFrame(
                    rows,
                    columns=['ts','Open','High','Low','Close','Volume']
                )
                df_new['ts'] = pd.to_datetime(
                    df_new['ts'], unit='ms', utc=True
                )
                df_new = (df_new.set_index('ts')
                                .drop_duplicates()
                                .astype(float))
                df = pd.concat([df_old, df_new])
                df = (df[~df.index.duplicated(keep='last')]
                        .sort_index())
            else:
                df = df_old

            if len(df) < min_rows:
                try:
                    os.remove(fp)
                except Exception:
                    pass
                df = None
            else:
                try:
                    df.to_parquet(fp)
                except Exception:
                    pass
        except Exception:
            df = None

    # ═══ 2. جلب كامل إن لزم ═══
    if df is None:
        rows = []
        try:
            since = since_full
            while True:
                chunk = exchange.fetch_ohlcv(
                    symbol, sub_tf, since=since, limit=1000
                )
                if not chunk:
                    break
                rows.extend(chunk)
                since = chunk[-1][0] + 1
                time.sleep(0.06)
        except Exception as e:
            log.warning(f"[SubBars] {symbol} {sub_tf} full fetch: {e}")
        if len(rows) < min_rows:
            return None
        df = pd.DataFrame(
            rows, columns=['ts','Open','High','Low','Close','Volume']
        )
        df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
        df = df.set_index('ts').drop_duplicates().astype(float).sort_index()
        try:
            df.to_parquet(fp)
        except Exception:
            pass

    # ═══ 3. back-fill إذا كان الكاش يبدأ بعد النافذة المطلوبة ═══
    first_ts = df.index.min()
    _gap = timedelta(seconds=_sub_sec * 2)
    if first_ts > since_full_dt + _gap:
        try:
            since = since_full
            end_ms = int(first_ts.timestamp() * 1000)
            _bf = []
            _pages = 0
            while since < end_ms:
                chunk = exchange.fetch_ohlcv(
                    symbol, sub_tf, since=since, limit=1000
                )
                if not chunk:
                    break
                chunk = [c for c in chunk if c[0] < end_ms]
                if not chunk:
                    break
                _bf.extend(chunk)
                since = chunk[-1][0] + 1
                time.sleep(0.06)
                _pages += 1
                if _pages > 400:
                    break
            if _bf:
                df_bf = pd.DataFrame(
                    _bf,
                    columns=['ts','Open','High','Low','Close','Volume']
                )
                df_bf['ts'] = pd.to_datetime(
                    df_bf['ts'], unit='ms', utc=True
                )
                df_bf = (df_bf.set_index('ts')
                              .drop_duplicates()
                              .astype(float))
                df = pd.concat([df_bf, df])
                df = (df[~df.index.duplicated(keep='last')]
                        .sort_index())
                try:
                    df.to_parquet(fp)
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"[SubBars] {symbol} backfill: {e}")
    # ═══ 3.5 التحقق والإصلاح المحلي (sub-bars) ═══
    df, gap_ranges, issues = _validate_cache_local(
        df, symbol, sub_tf, _sub_sec
    )
    if df is None or len(df) < min_rows:
        return None

    # ═══ 3.6 جلب فراغات sub-bars فقط ═══
    _gaps_filled = 0
    _bars_fetched = 0
    if issues.get('gaps', 0) > 0 and gap_ranges:
        _relevant = [(s, e) for (s, e) in gap_ranges
                     if e >= since_full_dt]
        if _relevant:
            _n_before = len(df)
            try:
                df_gap = _fetch_ranges(
                    exchange, symbol, sub_tf, _relevant, _sub_sec
                )
            except Exception as e:
                log.warning(f"[Cache-Health-Sub] {symbol} gap fetch "
                            f"failed: {e}")
                df_gap = None
            if df_gap is not None and len(df_gap) > 0:
                df = pd.concat([df, df_gap])
                df = (df[~df.index.duplicated(keep='last')]
                        .sort_index())
                _gaps_filled = len(_relevant)
                _bars_fetched = len(df) - _n_before
                try:
                    df.to_parquet(fp)
                    _CACHE_HEALTH['files_saved'] += 1
                except Exception as e:
                    log.debug(f"[Cache-Health-Sub] {symbol} save "
                              f"failed: {e}")

    _log_cache_health(f"{symbol}({sub_tf})", "sub", issues,
                       gaps_filled=_gaps_filled,
                       bars_fetched=_bars_fetched)

    # ═══ 4. الاقتطاع الصارم للـ sub-bars ═══

    # [STRICT-WINDOW-SUB] نطبق نفس المنطق: نحترم --history-days
    # بدقة للفريم الأصغر أيضاً، حتى لا يدخل الكاش القديم في
    # معالجة الشموع الرئيسية للنافذة المطلوبة فقط.
    # [END-DATE-TRUNC]
    df_window = df[(df.index >= since_full_dt) & (df.index <= _end_dt)]

    if len(df_window) >= min_rows:
        log.debug(f"[StrictWindow-Sub] {symbol} {sub_tf}: "
                  f"using {len(df_window)} sub-bars ({days}d)")
        return df_window

    # النافذة صغيرة جداً → لا نرجع للكاش الكامل
    log.debug(f"[StrictWindow-Sub] {symbol} {sub_tf}: window has "
              f"{len(df_window)} sub-bars (< {min_rows}) — "
              f"sub-bar refinement skipped for this symbol")
    return None


def fetch_all_with_subbars(symbols, exchange, main_tf, days, workers=5):
    """Fetch main + sub in one pass. Returns (main_dict, sub_dict)."""
    main = fetch_all(symbols, exchange, main_tf, days, workers=workers)
    sub_tf = _get_subbars_tf(main_tf)
    if not sub_tf or not getattr(CFG, 'SUBBARS_ENABLED', True):
        return main, {}

    sub = {}
    n_limit = int(getattr(CFG, 'SUBBARS_MAX_ASSETS', 0) or 0)
    targets = list(main.keys())[:n_limit] if n_limit > 0 else list(main.keys())

    def _one_sub(sym):
        try:
            df = _load_cached_sub(sym, exchange, sub_tf, days)
            return sym, df
        except Exception as e:
            log.warning(f"[SubBars] {sym} load failed: {e}")
            return sym, None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one_sub, s): s for s in targets}
        for f in as_completed(futs):
            sym, df = f.result()
            if df is not None and len(df) > 0:
                sub[sym] = df
                log.info(f"  ✓ {sym:14s}: {len(df):,} شمعة {sub_tf}")
    return main, sub

def _align_subbars(main_index, sub_df, sub_per_main, tf_sec):
    """
    Align sub-bars to main-bar grid.

    Returns (sub_highs, sub_lows) with shape (n_main, sub_per_main).
    Missing sub-bars are filled with the main bar's high/low.
    """
    n = len(main_index)
    sub_highs = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    sub_lows  = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    if sub_df is None or len(sub_df) == 0 or sub_per_main <= 0:
        return sub_highs, sub_lows

    try:
        sub_ts_ns = sub_df.index.asi8
        sub_high_vals = sub_df['High'].values.astype(np.float64)
        sub_low_vals  = sub_df['Low'].values.astype(np.float64)
        main_ns = main_index.asi8
        tf_ns = int(tf_sec * 1_000_000_000)

        for i in range(n):
            start_ns = main_ns[i]
            end_ns = start_ns + tf_ns
            lo = int(np.searchsorted(sub_ts_ns, start_ns, side='left'))
            hi = int(np.searchsorted(sub_ts_ns, end_ns, side='left'))
            if hi <= lo:
                continue
            take = min(hi - lo, sub_per_main)
            sub_highs[i, :take] = sub_high_vals[lo:lo+take]
            sub_lows[i, :take]  = sub_low_vals[lo:lo+take]
    except Exception as e:
        log.warning(f"[SubBars] align failed: {e}")
    return sub_highs, sub_lows

# ════════════════════════════════════════════════════════════════
# § 2  جلب البيانات مع كاش (متوازٍ)
# ════════════════════════════════════════════════════════════════

def _load_cached(symbol, exchange, timeframe, days):
    """
    [SAFE HISTORY-DAYS CACHE]

    المنطق:
      1. قراءة الكاش + forward-update (مطابق للأصل).
      2. back-fill إذا كان الكاش يبدأ بعد since_full_dt.
      3. اقتطاع النافذة فقط إذا كانت ≥ strict_min (2424).
      4. إذا كانت < strict_min → استخدام الكاش الكامل (مطابق للأصل).

    النتيجة:
      - --history-days الكبيرة: تتحكم بالحجم.
      - --history-days الصغيرة: تُرجع الكاش الكامل (كما كان سابقاً).
    """
    fp = os.path.join(CACHE_DIR,
                      f"{symbol.replace('/','_')}_{timeframe}.parquet")
    min_rows = CFG.N + CFG.W + 100
    _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600

    # الحد الأدنى لـ KMeans
    _kmin_pts = int(getattr(CFG, 'K_MIN_TRAIN_POINTS_PER_CLUSTER', 100))
    _kmax = int(getattr(CFG, 'K_MAX', 12))
    _strict_min = 2 * _kmax * _kmin_pts + CFG.N

    now_utc = datetime.now(timezone.utc)
    # [END-DATE-CUTOFF]
    _end_dt = _resolve_end_datetime()
    since_full_dt = _end_dt - timedelta(days=int(days))
    since_full = exchange.parse8601(since_full_dt.isoformat() + "Z")

    df = None

    # ═══ 1. قراءة الكاش + forward-update ═══
    if os.path.exists(fp):
        try:
            df_old = pd.read_parquet(fp)
            if df_old.index.tz is None:
                df_old.index = pd.to_datetime(df_old.index, utc=True)
            last_ts = df_old.index.max()
            since = exchange.parse8601(
                (last_ts + timedelta(seconds=_tf_sec)).isoformat() + "Z")
            rows = []
            try:
                while True:
                    chunk = exchange.fetch_ohlcv(
                        symbol, timeframe, since=since, limit=1000
                    )
                    if not chunk:
                        break
                    rows.extend(chunk)
                    since = chunk[-1][0] + 1
                    time.sleep(0.06)
            except Exception as e:
                log.warning(f"{symbol} update: {e}")

            if rows:
                df_new = pd.DataFrame(
                    rows,
                    columns=['ts','Open','High','Low','Close','Volume']
                )
                df_new['ts'] = pd.to_datetime(
                    df_new['ts'], unit='ms', utc=True
                )
                df_new = (df_new.set_index('ts')
                                .drop_duplicates()
                                .astype(float))
                df = pd.concat([df_old, df_new])
                df = (df[~df.index.duplicated(keep='last')]
                        .sort_index())
            else:
                df = df_old

            if len(df) < min_rows:
                try:
                    os.remove(fp)
                except Exception:
                    pass
                df = None
            else:
                try:
                    df.to_parquet(fp)
                except Exception as e:
                    log.warning(f"{symbol} cache write: {e}")
        except Exception as e:
            log.warning(f"{symbol} cache read: {e}")
            df = None

    # ═══ 2. جلب كامل إن لزم ═══
    if df is None:
        rows = []
        try:
            since = since_full
            while True:
                chunk = exchange.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=1000
                )
                if not chunk:
                    break
                rows.extend(chunk)
                since = chunk[-1][0] + 1
                time.sleep(0.06)
        except Exception as e:
            log.warning(f"{symbol} full fetch: {e}")
        if len(rows) < min_rows:
            return None
        df = pd.DataFrame(
            rows, columns=['ts','Open','High','Low','Close','Volume']
        )
        df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
        df = df.set_index('ts').drop_duplicates().astype(float).sort_index()
        try:
            df.to_parquet(fp)
        except Exception:
            pass

    # ═══ 3. back-fill إذا كان الكاش يبدأ بعد النافذة المطلوبة ═══
    first_ts = df.index.min()
    _gap = timedelta(seconds=_tf_sec * 2)
    if first_ts > since_full_dt + _gap:
        try:
            since = since_full
            end_ms = int(first_ts.timestamp() * 1000)
            _bf = []
            _pages = 0
            while since < end_ms:
                chunk = exchange.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=1000
                )
                if not chunk:
                    break
                chunk = [c for c in chunk if c[0] < end_ms]
                if not chunk:
                    break
                _bf.extend(chunk)
                since = chunk[-1][0] + 1
                time.sleep(0.06)
                _pages += 1
                if _pages > 200:
                    break
            if _bf:
                df_bf = pd.DataFrame(
                    _bf,
                    columns=['ts','Open','High','Low','Close','Volume']
                )
                df_bf['ts'] = pd.to_datetime(
                    df_bf['ts'], unit='ms', utc=True
                )
                df_bf = (df_bf.set_index('ts')
                              .drop_duplicates()
                              .astype(float))
                df = pd.concat([df_bf, df])
                df = (df[~df.index.duplicated(keep='last')]
                        .sort_index())
                try:
                    df.to_parquet(fp)
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"{symbol} backfill: {e}")

    # ═══ 3.5 التحقق والإصلاح المحلي ═══
    df, gap_ranges, issues = _validate_cache_local(
        df, symbol, timeframe, _tf_sec
    )
    if df is None or len(df) < min_rows:
        return None

    # ═══ 3.6 جلب الفراغات فقط (إن وُجدت) ═══
    _gaps_filled = 0
    _bars_fetched = 0
    if issues.get('gaps', 0) > 0 and gap_ranges:
        _relevant = [(s, e) for (s, e) in gap_ranges
                     if e >= since_full_dt]
        if _relevant:
            _n_before = len(df)
            try:
                df_gap = _fetch_ranges(
                    exchange, symbol, timeframe, _relevant, _tf_sec
                )
            except Exception as e:
                log.warning(f"[Cache-Health] {symbol} gap fetch "
                            f"failed: {e}")
                df_gap = None

            if df_gap is not None and len(df_gap) > 0:
                df = pd.concat([df, df_gap])
                df = (df[~df.index.duplicated(keep='last')]
                        .sort_index())
                _gaps_filled = len(_relevant)
                _bars_fetched = len(df) - _n_before
                try:
                    df.to_parquet(fp)
                    _CACHE_HEALTH['files_saved'] += 1
                except Exception as e:
                    log.debug(f"[Cache-Health] {symbol} save failed: {e}")

    # سجّل الملخص
    _log_cache_health(symbol, timeframe, issues,
                       gaps_filled=_gaps_filled,
                       bars_fetched=_bars_fetched)

    # ═══ 4. الاقتطاع الصارم — نحترم --history-days بدقة ═══
    # [STRICT-WINDOW] لا نعود أبداً للكاش الكامل بعد الآن.
    # إذا طلب المستخدم نافذة معينة، نحترمها. إذا كانت النافذة
    # غير كافية رياضياً → يُرفض الأصل بدل تضخيم البيانات بصمت.
    # [END-DATE-TRUNC]
    df_window = df[(df.index >= since_full_dt) & (df.index <= _end_dt)]

    # نتحقق فقط أن النافذة قابلة للمعالجة (N+W+100)
    if len(df_window) >= min_rows:
        log.debug(f"[StrictWindow] {symbol} {timeframe}: "
                  f"using {len(df_window)} bars "
                  f"({days}d requested)")
        return df_window

    # النافذة المطلوبة أصغر من الحد الأدنى للمعالجة → ارفض الأصل
    log.debug(f"[StrictWindow] {symbol} {timeframe}: window has "
              f"{len(df_window)} bars (< {min_rows} required) — "
              f"asset skipped")
    return None


def _fetch_one(args):
    sym, exchange, tf, days = args
    try:
        df = _load_cached(sym, exchange, tf, days)
        if df is None or len(df) < CFG.N+CFG.W+100: return sym, None
        return sym, df
    except Exception as e:
        log.warning(f"{sym}: {e}"); return sym, None


def _fetch_one(args):
    sym, exchange, tf, days = args
    try:
        df = _load_cached(sym, exchange, tf, days)
        if df is None or len(df) < CFG.N+CFG.W+100: return sym, None
        return sym, df
    except Exception as e:
        log.warning(f"{sym}: {e}"); return sym, None


def fetch_all(symbols, exchange, tf, days, workers=5):
    result = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one,(s,exchange,tf,days)):s for s in symbols}
        for f in as_completed(futs):
            sym, df = f.result()
            if df is not None:
                result[sym] = df
                log.info(f"  ✓ {sym:14s}: {len(df):,} شمعة")
            else:
                log.warning(f"  ✗ {sym}")
    return result


# ════════════════════════════════════════════════════════════════
# § 3  محرك الميزات R^7
# ════════════════════════════════════════════════════════════════

def compute_features(closes, volumes, N=None):
    N = N or CFG.N

    if _NUMBA_AVAILABLE and CFG.NUMBA_ENABLED:
        closes_f = np.ascontiguousarray(closes, dtype=np.float64)
        volumes_f = np.ascontiguousarray(volumes, dtype=np.float64)
        lr = np.diff(np.log(np.maximum(closes_f, 1e-12)))
        lr = np.ascontiguousarray(lr, dtype=np.float64)
        return _features_kernel(lr, closes_f, volumes_f, int(N))

    # ── Python/scipy fallback (unchanged, only used if numba missing) ──
    n  = len(closes)
    lr = np.diff(np.log(np.maximum(closes, 1e-12)))
    out = []
    for i in range(N, n):
        r = lr[i-N:i]; p = closes[i-N:i+1]; v = volumes[i-N:i]
        s = np.std(r, ddof=1)
        if s < 1e-10: out.append(np.zeros(7)); continue
        vec = np.array([np.mean(r), s,
                        float(skew(r,bias=False)), float(kurtosis(r,bias=False)),
                        float(np.max(p)-np.min(p)),
                        float(np.mean(v)) if len(v)>0 else 1.0,
                        float((closes[i]-closes[i-N])/(closes[i-N]+1e-12))],
                       dtype=np.float64)
        nm = np.linalg.norm(vec)
        if nm > 1.0: vec /= nm
        out.append(vec)
    return np.array(out, dtype=np.float64)


# ════════════════════════════════════════════════════════════════
# § 4  التكميم الديناميكي (التعديل ③)
# ════════════════════════════════════════════════════════════════

def compute_dynamic_k(current_capital: float, adv_usd: np.ndarray,
                       n_train_features: Optional[int] = None) -> int:
    """
    Capital-based K, then capped by data-support bound.

    Capital formula (unchanged):
        K_C = clamp(K_MAX · exp(-α·C/ADV), K_MIN, K_MAX)

    Data-support cap (new):
        K_data = n_train_features / MIN_POINTS_PER_CLUSTER
        K = min(K_C, K_data)

    Rationale: on 4h TF with 930 features and train=465, K=11 produced
    H/theo=0.107 (degenerate). Requiring ≥100 train points per cluster
    yields K_data=4, preventing the collapse.
    """
    adv_mean = float(np.mean(adv_usd[adv_usd > 0])) if np.any(adv_usd > 0) else 1e6
    capital_ratio = current_capital / (adv_mean + CFG.EPSILON)
    k_c = int(np.floor(CFG.K_MAX * np.exp(-CFG.KQUANT_ALPHA * capital_ratio)))
    k_c = max(CFG.K_MIN, min(CFG.K_MAX, k_c))

    if n_train_features is not None and n_train_features > 0:
        min_pts = int(getattr(CFG, 'K_MIN_TRAIN_POINTS_PER_CLUSTER', 100))
        k_data = max(CFG.K_MIN, n_train_features // max(min_pts, 1))
        k_c = min(k_c, k_data)

    return int(k_c)


def fit_kmeans(X, k=None):
    k = k or CFG.K
    km = KMeans(n_clusters=k, n_init=15, random_state=42, max_iter=500)
    km.fit(X); return km

def assign(X, km): return km.predict(X).astype(np.int32)


# ════════════════════════════════════════════════════════════════
# § 5  الثرموديناميك
# ════════════════════════════════════════════════════════════════

def _H(sym, k=None):
    k = k or CFG.K
    c = np.bincount(sym, minlength=k).astype(float)
    p = c/len(sym); nz = p[p>0]
    return float(-np.sum(nz*np.log2(nz+1e-12)))

def entropy_series(sym_q, W=None, k=None):
    """
    Shannon entropy over a sliding window.
    Dispatches to Numba kernel when available (typically 10–30× faster).
    """
    W = W or CFG.W
    k = k or CFG.K

    if _NUMBA_AVAILABLE and CFG.NUMBA_ENABLED:
        sym_q_i = np.ascontiguousarray(sym_q, dtype=np.int64)
        return _entropy_kernel(sym_q_i, int(W), int(k))

    # ── Pure-Python fallback ──
    n = len(sym_q)
    H = np.zeros(n)
    for i in range(W - 1, n):
        H[i] = _H(sym_q[i - W + 1:i + 1], k=k)
    return H

def entropy_regression(H):
    n = len(H)
    if n < 3: return {'slope':0.,'r2':0.,'se':0.,'trend':'neutral'}
    x = np.arange(n,dtype=float)
    sl,_,rv,_,se = linregress(x, H); r2 = rv**2
    if r2 < 0.05: trend='neutral'
    elif sl>0 and (se==0 or sl>2*se): trend='increasing'
    elif sl<0 and (se==0 or abs(sl)>2*se): trend='decreasing'
    else: trend='neutral'
    return {'slope':sl,'r2':r2,'se':se,'trend':trend}


# ════════════════════════════════════════════════════════════════
# § 6  الهندسة
# ════════════════════════════════════════════════════════════════

def compute_geometry(X, step=None):
    step = step or CFG.L; n,d = X.shape
    C = np.zeros(n); V = np.zeros(n)
    for s in range(0,n,step):
        e = min(s+step,n); chunk = X[s:e]
        if len(chunk)<2: C[s:e]=0.; V[s:e]=CFG.EPSILON; continue
        diffs = np.linalg.norm(np.diff(chunk,axis=0),axis=1)
        C[s:e] = -float(np.mean(diffs))
        cov    = np.cov(chunk.T) if chunk.shape[0]>1 else np.eye(d)
        V[s:e] = max(np.linalg.det(cov+CFG.EPSILON*np.eye(d)), CFG.EPSILON)
    return C, V


# ════════════════════════════════════════════════════════════════
# § 6.5  Level-2 Numba Kernels (C-speed hot loops)
# ════════════════════════════════════════════════════════════════

# ─── Kernel 1: Lyapunov dynamic (the biggest bottleneck) ─────────

@njit(cache=True)
def _lyapunov_kernel(X, window, steps, min_dist):
    """
    Numba-compiled version of compute_lyapunov_dynamic's core loop.
    Preserves exact semantics of the pure-Python version.
    """
    n, d = X.shape
    lya = np.zeros(n)
    if n < 2 * min_dist + steps + window:
        return lya

    sr = max(1, window // 20)
    # Preallocated buffer for divergence samples
    max_divs = (window // sr) + 1
    divs = np.empty(max_divs, dtype=np.float64)

    for i in range(window, n):
        st = i - window
        ndivs = 0

        for t in range(0, window, sr):
            ta = st + t
            if ta + steps >= n:
                continue

            bd = 1.0e18
            bj = -1

            for j in range(0, window, sr):
                if abs(t - j) < min_dist:
                    continue
                # Manual euclidean norm (avoids np.linalg.norm overhead)
                dd = 0.0
                for k in range(d):
                    diff = X[ta, k] - X[st + j, k]
                    dd += diff * diff
                dd = dd ** 0.5
                if dd < bd:
                    bd = dd
                    bj = j

            if bj == -1 or bd < 1e-12:
                continue

            ja = st + bj
            if ja + steps >= n:
                continue

            ds = 0.0
            for k in range(d):
                diff = X[ta + steps, k] - X[ja + steps, k]
                ds += diff * diff
            ds = ds ** 0.5

            if bd > 0.0 and ds > 0.0 and ndivs < max_divs:
                divs[ndivs] = np.log(ds / bd)
                ndivs += 1

        if ndivs > 3:
            s = 0.0
            for k in range(ndivs):
                s += divs[k]
            lya[i] = (s / ndivs) / steps

    return lya


# ─── Kernel 2: Gauge force & equilibrium gap ────────────────────

@njit(cache=True)
def _gauge_kernel(sym_q, dyn_k, W):
    """
    Numba-compiled gauge force & delta_gap.
    Reuses scratch buffers to avoid per-iteration allocations.
    """
    n = len(sym_q)
    gauge_force = np.zeros(n)
    delta_gap = np.zeros(n)
    if n <= W:
        return gauge_force, delta_gap

    P_star = 1.0 / dyn_k
    counts = np.zeros(dyn_k, dtype=np.int64)
    T_mat = np.zeros((dyn_k, dyn_k), dtype=np.float64)

    for i in range(W, n):
        # ---- Reset counts ----
        for k in range(dyn_k):
            counts[k] = 0
        # ---- Count occurrences in window [i-W, i) ----
        for j in range(i - W, i):
            counts[sym_q[j]] += 1
        # ---- delta_gap = max |P_n - P_star| ----
        max_dev = 0.0
        for k in range(dyn_k):
            P_n = counts[k] / W
            dev = P_n - P_star
            if dev < 0.0:
                dev = -dev
            if dev > max_dev:
                max_dev = dev
        delta_gap[i] = max_dev

        # ---- Reset transition matrix ----
        for a in range(dyn_k):
            for b in range(dyn_k):
                T_mat[a, b] = 0.0

        # ---- Build transition counts ----
        for j in range(i - W + 1, i):
            a = sym_q[j - 1]
            b = sym_q[j]
            T_mat[a, b] += 1.0

        # ---- Normalize ----
        sum_T = 0.0
        for a in range(dyn_k):
            for b in range(dyn_k):
                sum_T += T_mat[a, b]
        if sum_T > 0.0:
            for a in range(dyn_k):
                for b in range(dyn_k):
                    T_mat[a, b] /= sum_T

        # ---- Frobenius norm of A = T - T^T ----
        frob_sq = 0.0
        for a in range(dyn_k):
            for b in range(dyn_k):
                diff = T_mat[a, b] - T_mat[b, a]
                frob_sq += diff * diff
        gauge_force[i] = frob_sq ** 0.5

    return gauge_force, delta_gap


# ─── Kernel 3: Entropy series ───────────────────────────────────

@njit(cache=True)
def _entropy_kernel(sym_q, W, k):
    """
    Numba-compiled Shannon entropy over a sliding window.
    """
    n = len(sym_q)
    H = np.zeros(n)
    if n < W:
        return H

    counts = np.zeros(k, dtype=np.int64)

    for i in range(W - 1, n):
        for kk in range(k):
            counts[kk] = 0
        for j in range(i - W + 1, i + 1):
            idx = sym_q[j]
            if 0 <= idx < k:
                counts[idx] += 1

        H_val = 0.0
        for kk in range(k):
            c = counts[kk]
            if c > 0:
                p = c / W
                H_val -= p * np.log2(p + 1e-12)
        H[i] = H_val

    return H

# ─── Kernel 0: Features (compute_features bottleneck) ───────────

@njit(cache=True)
def _features_kernel(lr, closes, volumes, N):
    """
    Numba-compiled feature extractor — replaces scipy-heavy Python loop.

    For each i in [N, n):
      r = lr[i-N : i]                      (N log-returns)
      s = std(r, ddof=1)
      vec = [mean(r), s, skew_bias_false(r), kurt_bias_false(r),
             max(p)-min(p), mean(v), (p[i]-p[i-N])/p[i-N]]
      normalize if ||vec|| > 1
      if s < 1e-10 → leave row as zeros

    Formulas verified against scipy 1.13:
      skew  bias=False:  g1 * sqrt(N*(N-1)) / (N-2),  g1 = m3_pop/m2_pop^1.5
      kurt  bias=False:  ((N^2-1)*R - 3*(N-1)^2) / ((N-2)*(N-3)),
                         R = m4_pop / m2_pop^2
    """
    n = len(closes)
    out = np.zeros((n - N, 7), dtype=np.float64)

    for i in range(N, n):
        # ── mean of returns ──
        mean_r = 0.0
        for j in range(N):
            mean_r += lr[i - N + j]
        mean_r /= N

        # ── central moments (single pass) ──
        var_sum = 0.0
        m3_sum = 0.0
        m4_sum = 0.0
        for j in range(N):
            diff = lr[i - N + j] - mean_r
            diff2 = diff * diff
            var_sum += diff2
            m3_sum += diff2 * diff
            m4_sum += diff2 * diff2

        s = np.sqrt(var_sum / (N - 1))
        if s < 1e-10:
            continue

        m2_pop = var_sum / N
        m3_pop = m3_sum / N
        m4_pop = m4_sum / N

        # ── skew (bias=False) ──
        if m2_pop > 0.0 and N > 2:
            g1 = m3_pop / (m2_pop ** 1.5)
            skew_val = g1 * np.sqrt(N * (N - 1.0)) / (N - 2.0)
        else:
            skew_val = 0.0

        # ── kurtosis (bias=False, fisher=True — scipy default) ──
        if m2_pop > 0.0 and N > 3:
            R = m4_pop / (m2_pop * m2_pop)
            kurt_val = (((N * N - 1.0) * R - 3.0 * (N - 1.0) ** 2)
                        / ((N - 2.0) * (N - 3.0)))
        else:
            kurt_val = 0.0

        # ── range of closes[i-N : i+1] ──
        p_min = closes[i - N]
        p_max = closes[i - N]
        for j in range(1, N + 1):
            v = closes[i - N + j]
            if v < p_min:
                p_min = v
            if v > p_max:
                p_max = v

        # ── mean of volumes[i-N : i] ──
        v_mean = 0.0
        for j in range(N):
            v_mean += volumes[i - N + j]
        v_mean /= N
        if v_mean <= 0.0:
            v_mean = 1.0

        pct_change = (closes[i] - closes[i - N]) / (closes[i - N] + 1e-12)

        # ── build & normalize ──
        prange = p_max - p_min
        norm = np.sqrt(mean_r * mean_r + s * s + skew_val * skew_val +
                       kurt_val * kurt_val + prange * prange +
                       v_mean * v_mean + pct_change * pct_change)
        scale = 1.0 / norm if norm > 1.0 else 1.0

        out[i - N, 0] = mean_r * scale
        out[i - N, 1] = s * scale
        out[i - N, 2] = skew_val * scale
        out[i - N, 3] = kurt_val * scale
        out[i - N, 4] = prange * scale
        out[i - N, 5] = v_mean * scale
        out[i - N, 6] = pct_change * scale

    return out

# ════════════════════════════════════════════════════════════════
# Wrapper functions — dispatch to numba or pure-Python depending on
# availability and CFG.NUMBA_ENABLED.
# ════════════════════════════════════════════════════════════════

def _warmup_numba_kernels():
    """
    Trigger JIT compilation once at startup so timing is predictable.
    Uses tiny dummy data — cheap.
    """
    if not (_NUMBA_AVAILABLE and CFG.NUMBA_ENABLED):
        return
    t0 = time.time()
    try:
        _ = _lyapunov_kernel(
            np.random.randn(120, 7).astype(np.float64),
            window=60, steps=5, min_dist=10
        )
        _ = _gauge_kernel(
            np.random.randint(0, 4, size=100).astype(np.int64),
            dyn_k=4, W=20
        )
        _ = _entropy_kernel(
            np.random.randint(0, 4, size=100).astype(np.int64),
            W=20, k=4
        )
        # NEW: features kernel (biggest hot loop)
        _ = _features_kernel(
            np.random.randn(200).astype(np.float64),
            np.random.randn(201).astype(np.float64) + 100.0,
            np.random.rand(201).astype(np.float64) + 1.0,
            24,
        )
        log.info(f"[Level-2] Numba kernels warm (JIT ready in {time.time()-t0:.1f}s)")
    except Exception as e:
        log.warning(f"[Level-2] Numba warmup failed: {e}")

# ════════════════════════════════════════════════════════════════
# § 7  ديناميكا الطاقة
# ════════════════════════════════════════════════════════════════

def compute_lyapunov_dynamic(X, window=60, steps=5, min_dist=10):
    """
    Lyapunov exponent via nearest-neighbor divergence.
    Dispatches to Numba kernel when available (typically 50–200× faster).
    """
    if _NUMBA_AVAILABLE and CFG.NUMBA_ENABLED:
        # Numba expects contiguous float64
        X_f = np.ascontiguousarray(X, dtype=np.float64)
        return _lyapunov_kernel(X_f, window, steps, min_dist)

    # ── Pure-Python fallback (identical to original) ──
    n, d = X.shape
    lya = np.zeros(n)
    if n < 2 * min_dist + steps + window:
        return lya
    sr = max(1, window // 20)
    for i in range(window, n):
        st = i - window
        chunk = X[st:i]
        divs = []
        for t in range(0, window, sr):
            ta = st + t
            if ta + steps >= n:
                continue
            xt = chunk[t]
            bd = float('inf')
            bj = -1
            for j in range(0, window, sr):
                if abs(t - j) < min_dist:
                    continue
                dd = np.linalg.norm(xt - chunk[j])
                if dd < bd:
                    bd = dd
                    bj = j
            if bj == -1 or bd < 1e-12:
                continue
            ja = st + bj
            if ja + steps >= n:
                continue
            ds = np.linalg.norm(X[ta + steps] - X[ja + steps])
            if bd > 0:
                divs.append(np.log(ds / bd))
        if len(divs) > 3:
            lya[i] = np.mean(divs) / steps
    return lya

def compute_energy_dynamics(closes, lr_full, X, feat_start):
    n = len(X); N = CFG.N; KE = np.zeros(n)
    for i in range(n):
        ci = feat_start+i
        if ci>=N: KE[i] = 0.5*float(np.mean(lr_full[ci-N:ci]**2))
    lya  = compute_lyapunov_dynamic(X, window=60, steps=5, min_dist=10)
    dKE  = np.diff(KE,  prepend=KE[0])
    d2KE = np.diff(dKE, prepend=dKE[0])
    return {'KE':KE,'dKE':dKE,'d2KE':d2KE,'lya':lya}

def compute_PE(X, km, H):
    centroids = km.cluster_centers_; labels = km.predict(X)
    k = len(centroids)
    H_max = np.log2(k)
    dists = np.linalg.norm(X-centroids[labels], axis=1)
    order = np.clip(1.-H/(H_max+1e-12), 0., 1.)
    return dists*order


# ════════════════════════════════════════════════════════════════
# § 8  كاشف الانعكاس TRI
# ════════════════════════════════════════════════════════════════

def compute_tri(dH, d2H, dF, dKE, lya):
    q75 = np.percentile(lya[lya>0],75) if np.any(lya>0) else 1.
    thr = q75*CFG.LYA_THRESHOLD_MULT
    tri = np.zeros(len(dH), dtype=np.float32)
    tri += (dF  > 0).astype(np.float32)
    tri += (d2H > 0.01).astype(np.float32)
    tri += (dKE < 0).astype(np.float32)
    tri += (lya > thr).astype(np.float32)
    return tri


# ════════════════════════════════════════════════════════════════
# § 9  نقطة الدخول المثلى
# ════════════════════════════════════════════════════════════════

def find_optimal_entry(ci0, closes, KE, atr, action, feat_start):
    start = ci0+1; end = min(start+CFG.OPTIMAL_ENTRY_WAIT, len(closes)-1)
    if start >= end: return ci0, closes[ci0]
    p0   = closes[ci0]; dip = atr/p0*CFG.OPTIMAL_ENTRY_DIP
    ptgt = p0*(1.-dip) if action=="BUY" else p0*(1.+dip)
    for ci in range(start,end):
        p = closes[ci]
        if action=="BUY"  and p<=ptgt: return ci, p
        if action=="SELL" and p>=ptgt: return ci, p
    ks = max(start-feat_start, 0); ke = min(end-feat_start, len(KE)-1)
    if ke>ks:
        lm = int(np.argmin(KE[ks:ke]))
        bi = start+lm
        if bi < len(closes): return bi, closes[bi]
    return start, closes[start]


# ════════════════════════════════════════════════════════════════
# [BACKTEST REALISM] — Slippage & fee helpers
# ════════════════════════════════════════════════════════════════

def _taker_slippage_bps(adv_usd) -> float:
    """
    Taker slippage (half-spread + small impact) in basis points,
    derived from 24h quote volume. Calibrated to typical Binance
    USDT-M Futures order books:

        adv ≥ 5e10 (BTC)       → 1.0 bps
        adv ≥ 5e9  (ETH)       → 1.5 bps
        adv ≥ 1e9  (SOL, BNB)  → 2.5 bps
        adv ≥ 1e8  (WIF, DOGE) → 5.0 bps
        adv ≥ 1e7  (small alt) → 10.0 bps
        adv <  1e7             → 20.0 bps
    """
    try:
        a = float(adv_usd)
    except Exception:
        return 5.0
    if a >= 5e10: return 1.0
    if a >= 5e9:  return 1.5
    if a >= 1e9:  return 2.5
    if a >= 1e8:  return 5.0
    if a >= 1e7:  return 10.0
    return 20.0


def _exit_is_taker(exit_rsn: str) -> bool:
    """
    Classify the exit reason as taker (crosses the book) or maker.
    Matches Live's classification in run_live():
        - Emergency SL / Hard TP / LiqProximity → taker
          (marketable limit or market order)
        - Apex / Topo-Div / MaxHold / EndOfData → maker
          (post-only GTX exit)
    """
    r = str(exit_rsn or "")
    if ("Emergency" in r) or ("Hard TP" in r) or ("LiqProximity" in r):
        return True
    return False


# ════════════════════════════════════════════════════════════════
# § 10  نموذج الانزلاق (كايل)
# ════════════════════════════════════════════════════════════════

def apply_slippage(price, qty, adv_usd, action, mode="backtest",
                   is_taker=False):
    """
    Realistic slippage model (Backtest only).

    - Maker fills (entry GTX, exit post-only) → 0 slippage.
    - Taker fills (market, marketable-limit, stop-market) → adverse
      slippage from half-spread, scaled by asset liquidity.

    Live (mode != 'backtest') returns price unchanged: the exchange
    applies real slippage.
    """
    if mode != "backtest":
        return price
    if not is_taker:
        return price
    if price <= 0:
        return price

    bps = _taker_slippage_bps(adv_usd)
    slip_frac = bps * 1e-4

    # Adverse: buyer pays more, seller receives less
    if action == "BUY":
        return float(price * (1.0 + slip_frac))
    else:
        return float(price * (1.0 - slip_frac))

# ════════════════════════════════════════════════════════════════
# § 11  بنية البيانات
# ════════════════════════════════════════════════════════════════

@dataclass
class AssetData:
    symbol: str
    closes: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    volumes: np.ndarray
    timestamps: pd.DatetimeIndex
    X: np.ndarray
    sym_q: np.ndarray
    H: np.ndarray
    dH: np.ndarray
    d2H: np.ndarray
    E_therm: np.ndarray
    F: np.ndarray
    dF: np.ndarray
    C: np.ndarray
    V: np.ndarray
    h: np.ndarray
    score: np.ndarray
    ema200: np.ndarray
    ema_accel: np.ndarray  
    atr14: np.ndarray
    adv_usd: np.ndarray
    KE: np.ndarray
    PE: np.ndarray
    ME: np.ndarray
    dKE: np.ndarray
    lya: np.ndarray
    tri: np.ndarray
    T_info: np.ndarray  
    train_end: int
    feat_start: int
    km: KMeans
    dynamic_k: int  
    
    # حقول النظرية الموحدة الإضافية:
    gauge_force: np.ndarray
    friction: np.ndarray
    delta_gap: np.ndarray
    geodesic_accel: np.ndarray
    score_q95_train: float
    # ══ [SUB-BARS] ══
    sub_highs: Optional[np.ndarray] = None    # shape (n_bars, sub_per_main)
    sub_lows:  Optional[np.ndarray] = None
    sub_per_main: int = 0
    sub_tf: str = ""

@dataclass
class Signal:
    timestamp: pd.Timestamp; symbol: str; price: float; score: float
    action: str; sl: float; tp1: float; tp2: float; tp3: float
    atr: float; lam: float; close_idx: int; feat_idx: int
    adv_usd: float; tri_val: float
    dynamic_risk: float
    T_info_val: float
    dyn_sl_factor: float = 0.1
    # ══ [SMART ENTRY] ══
    entry_ref_price: float = 0.0   # close price at signal time (dip ref)
    entry_base_dip: float = 0.0    # |ref_price − price| in price units
    # ══ [MFAL] Signal-time feature vector for Quality factor ══
    mfal_x: Optional[np.ndarray] = None
    mfal_p_act: float = 0.0

@dataclass
class Trade:
    symbol: str; action: str; entry_price: float; exit_price: float
    pos_size: float; gross_pnl: float; fee: float; net_pnl: float
    capital_after: float; log_return: float
    entry_time: pd.Timestamp; exit_reason: str
    score: float; lam: float; liq_warn: bool
    slippage_paid: float; entry_optimized: bool; tri_at_entry: float
    dynamic_risk_used: float
    T_info_at_entry: float
    mfe_frac: float = 0.0   # ← أضف هذا السطر

@dataclass
class OpenPosition:
    symbol: str; signal: Signal
    entry_px: float; pos_size: float; trail_sl: float
    entry_cap: float; entry_ci: int; current_ci: int
    slip_paid: float; opt_entry: bool; tri_entry: float
    mfe_frac: float = 0.0
    peak_price: float = 0.0
    trail_dist_frac: float = 0.003
    trail_activate_frac: float = 0.004
    sl_dist_initial: float = 0.0
    trail_peak_R: float = 0.0
    entry_sub_idx: int = 0
    partial_taken: bool = False      # [FIX 4]
    partial_pnl: float = 0.0         # [FIX 4] accumulated partial profit


# ════════════════════════════════════════════════════════════════
# § النظرية الموحدة: حقل المقياس، الاحتكاك، وفجوة التوازن
# ════════════════════════════════════════════════════════════════

def compute_gauge_force_and_gap(sym_q: np.ndarray, dyn_k: int,
                                W: int = CFG.W) -> Tuple[np.ndarray, np.ndarray]:
    """
    Emergent gauge field strength + equilibrium gap from symbolic transitions.
    Dispatches to Numba kernel when available (typically 10–30× faster).
    """
    if _NUMBA_AVAILABLE and CFG.NUMBA_ENABLED:
        sym_q_i = np.ascontiguousarray(sym_q, dtype=np.int64)
        return _gauge_kernel(sym_q_i, int(dyn_k), int(W))

    # ── Pure-Python fallback (identical to original) ──
    n = len(sym_q)
    gauge_force = np.zeros(n, dtype=np.float64)
    delta_gap = np.zeros(n, dtype=np.float64)
    P_star = 1.0 / dyn_k

    for i in range(W, n):
        window = sym_q[i - W:i]
        counts = np.bincount(window, minlength=dyn_k)
        P_n = counts / W
        delta_gap[i] = np.max(np.abs(P_n - P_star))

        T_mat = np.zeros((dyn_k, dyn_k), dtype=np.float64)
        for j in range(1, len(window)):
            T_mat[window[j - 1], window[j]] += 1

        sum_T = np.sum(T_mat)
        if sum_T > 0:
            T_mat /= sum_T

        A = T_mat - T_mat.T
        gauge_force[i] = np.linalg.norm(A, ord='fro')

    return gauge_force, delta_gap


def compute_entropy_friction(H: np.ndarray, dyn_k: int) -> np.ndarray:
    """
    حساب معامل الاحتكاك الإنتروبي المتغير للأنظمة الرمزية (القسم 4.1).
    Γ(S) = γ0 + κ * exp(ξ * (1 - S/S_max))
    """
    H_max = np.log2(dyn_k) + 1e-12
    # نسبة الإنتروبيا المقيدة ضمن المجال [0, 1]
    S_ratio = np.clip(H / H_max, 0.0, 1.0)
    gamma = CFG.GAMMA_0 + CFG.KAPPA * np.exp(CFG.XI * (1.0 - S_ratio))
    return gamma

# ════════════════════════════════════════════════════════════════
# § 12  معالجة أصل واحد (Pipeline) + تسارع EMA (التعديل ⑤)
# ════════════════════════════════════════════════════════════════

def process_asset(symbol, df, km_ext=None, current_capital=None, sub_df=None):
    closes = df['Close'].values.astype(np.float64)
    highs  = df['High'].values.astype(np.float64)
    lows   = df['Low'].values.astype(np.float64)
    vols   = df['Volume'].values.astype(np.float64)
    ts     = df.index; N = CFG.N
    if len(closes) < N+CFG.W+100: return None

    feat_start = N
    X = compute_features(closes, vols, N)
    n = len(X)
    if n < CFG.W+50: return None

    train_end = int(n*CFG.TRAIN_FRACTION)

    # ══ التعديل ③: K ديناميكي ════════════════════════════════
    _adv_bars_eff = int(getattr(CFG, 'ADV_BARS', 24))
    adv_raw = pd.Series(vols*closes).rolling(_adv_bars_eff, min_periods=1).mean().values
    cap_now = current_capital if current_capital else CFG.INITIAL_CAPITAL
    dyn_k   = compute_dynamic_k(cap_now, adv_raw[:train_end+feat_start],
                                 n_train_features=train_end)
    # ══════════════════════════════════════════════════════════

    km = km_ext if km_ext else fit_kmeans(X[:train_end], k=dyn_k)
    sym_q = assign(X, km)

    H   = entropy_series(sym_q, k=dyn_k)
    dH  = np.diff(H,  prepend=H[0])
    d2H = np.diff(dH, prepend=dH[0])

    # ══ [ADAPTIVE FIX #2b] Degenerate clustering detection ══
    # If training-set entropy is far below theoretical max, KMeans has
    # collapsed to a few effective clusters → features are meaningless.
    # Skip this (symbol, TF) entirely.
    if getattr(CFG, 'K_SKIP_IF_DEGENERATE', True):
        _H_train_mean = float(np.mean(H[:max(train_end, 1)]))
        _H_theo = np.log2(max(int(dyn_k), 2))
        _ratio = _H_train_mean / max(_H_theo, 1e-9)
        if _ratio < float(getattr(CFG, 'K_DEGENERATE_H_RATIO', 0.25)):
            log.warning(
                f"[process_asset] {symbol}: degenerate clustering "
                f"(H_train={_H_train_mean:.3f}, H_theo={_H_theo:.3f}, "
                f"ratio={_ratio:.3f}, K={dyn_k}) — returning None"
            )
            return None

    lr_full = np.diff(np.log(np.maximum(closes,1e-12)))
    E_therm = np.zeros(n)
    for i in range(n):
        ci = feat_start+i
        if ci >= N:
            w = lr_full[ci-N:ci]
            E_therm[i] = float(np.std(w,ddof=1)) if len(w)>=2 else 0.

    F  = E_therm - H
    dF = np.diff(F, prepend=F[0])

    # ══ التعديل ①: درجة الحرارة المعلوماتية (TF-UNIFIED) ══
    # T_abs يجب أن يكون ثابتاً عبر الأُطر. بما أن E_therm ∝ √(TF_SECONDS)،
    # نضرب في √TF_SCALE لجعله مستقلاً عن الإطار.
    T_info_raw = np.abs(dF / (np.abs(dH) + 1e-9))
    _tf_scale_t = max(float(getattr(CFG, 'TF_SCALE', 1.0)), 1e-6)
    T_abs = E_therm * 400.0 * np.sqrt(_tf_scale_t)
    T_info = T_info_raw + T_abs
    T_info = np.clip(T_info, 0.5, 20.0)
    # ══════════════════════════════════════════════════════════

    # ══ حساب المكونات المادية والهندسة الناشئة ═══════════════
    # 1. فجوة التوازن وحقل المقياس
    gauge_force, delta_gap = compute_gauge_force_and_gap(sym_q, dyn_k, CFG.W)
    
    # 2. الاحتكاك التفاضلي Γ
    friction = compute_entropy_friction(H, dyn_k)
    
    # 3. المعادلة الجيوديسية التفاضلية القسرية (القسم 13.5):
    # D_dot(λ_dot) = -∇F + q * F_gauge * λ_dot - Γ * λ_dot
    geodesic_accel = np.zeros(n, dtype=np.float64)
    for i in range(n):
        grad_F = -dF[i]
        lorentz = CFG.LORENTZ_CHARGE_Q * gauge_force[i] * dH[i]
        fric_force = friction[i] * dH[i]
        geodesic_accel[i] = grad_F + lorentz - fric_force

    C, V = compute_geometry(X)
    V_tr = V[:train_end]; vv = V_tr[V_tr>CFG.EPSILON]
    V_q20 = np.percentile(vv,20) if len(vv)>0 else np.percentile(V_tr,20)
    V_q20a = np.full(n, V_q20)

    # ══ [THRESHOLD MODE] Absolute vs z-score for h and score terms ══
    # We always compute the z-scores (cheap) so they remain available
    # if USE_ABSOLUTE_THRESHOLDS is flipped later. The HMM state and
    # score terms use whichever mode is active.
    _dH_mu, _dH_sd = _robust_center_scale(dH[:max(train_end, 1)])
    _dF_mu, _dF_sd = _robust_center_scale(dF[:max(train_end, 1)])
    dH_z = (dH - _dH_mu) / max(_dH_sd, 1e-12)
    dF_z = (dF - _dF_mu) / max(_dF_sd, 1e-12)

    _use_abs = bool(getattr(CFG, 'USE_ABSOLUTE_THRESHOLDS', True))

    if _use_abs:
        # ── HMM state from ABSOLUTE dH ──
        h = np.ones(n, dtype=np.int32)
        h[dH >  CFG.DH_HMM_UPPER] = 0
        h[dH <  CFG.DH_HMM_LOWER] = 2

        # ── Score uses ABSOLUTE thresholds ──
        sc = np.zeros(n)
        sc += np.abs(geodesic_accel) * 10.0
        sc += CFG.W_CURV    * (C > CFG.CURV_THRESHOLD).astype(float)
        sc += CFG.W_VOL     * (V < V_q20a).astype(float)
        sc += CFG.W_ENTROPY * ((dH < CFG.DH_ENTROPY_THRESHOLD) & (d2H < 0)).astype(float)
        sc += CFG.W_HMM     * ((h == 2) | ((h == 0) & (dH < -CFG.DH_ENTROPY_THRESHOLD))).astype(float)
        sc += CFG.W_FREE_E  * (dF < CFG.DF_FREE_E_THRESHOLD).astype(float)
    else:
        # ── HMM state from Z-SCORED dH ──
        h = np.ones(n, dtype=np.int32)
        h[dH_z >  CFG.DH_HMM_UPPER_Z] = 0
        h[dH_z <  CFG.DH_HMM_LOWER_Z] = 2

        # ── Score uses Z-SCORE thresholds ──
        sc = np.zeros(n)
        sc += np.abs(geodesic_accel) * 10.0
        sc += CFG.W_CURV    * (C > CFG.CURV_THRESHOLD).astype(float)
        sc += CFG.W_VOL     * (V < V_q20a).astype(float)
        sc += CFG.W_ENTROPY * ((dH_z < CFG.DH_ENTROPY_Z) & (d2H < 0)).astype(float)
        sc += CFG.W_HMM     * ((h == 2) | ((h == 0) & (dH_z < -CFG.DH_ENTROPY_Z))).astype(float)
        sc += CFG.W_FREE_E  * (dF_z < CFG.DF_FREE_E_Z).astype(float)
    # ══════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════

    # ══ [ADAPTIVE FIX #4] Q95 of score on training portion ══
    _score_q95_train = float(np.percentile(sc[:max(train_end, 1)], 95))

    # ══ حساب EMA وتسارعه (التعديل ⑤) ════════════════════════
    ema200_series = pd.Series(closes).ewm(span=CFG.EMA_SPAN, adjust=False).mean().values
    ema_diff  = np.diff(ema200_series, prepend=ema200_series[0])
    ema_accel = np.diff(ema_diff,      prepend=ema_diff[0])
    # ══════════════════════════════════════════════════════════

    tr  = np.maximum(highs[1:]-lows[1:],
          np.maximum(np.abs(highs[1:]-closes[:-1]), np.abs(lows[1:]-closes[:-1])))
    tr  = np.concatenate([[tr[0]],tr])
    atr = pd.Series(tr).rolling(CFG.ATR_PERIOD, min_periods=1).mean().values
    adv = pd.Series(vols*closes).rolling(_adv_bars_eff, min_periods=1).mean().values

    ed  = compute_energy_dynamics(closes, lr_full, X, feat_start)
    KE  = ed['KE']; dKE = ed['dKE']
    PE  = compute_PE(X, km, H)
    ME  = KE+PE
    tri = compute_tri(dH, d2H, dF, dKE, ed['lya'])

    # ══ [SUB-BARS] Align finer bars to the main grid ══
    _sub_h, _sub_l = None, None
    _sub_pm = 0
    _sub_tf_name = ""
    if (getattr(CFG, 'SUBBARS_ENABLED', True)
            and sub_df is not None and len(sub_df) > 0):
        _sub_tf_name = _get_subbars_tf(CFG.timeframe) or ""
        if _sub_tf_name:
            _sub_pm = _sub_per_main(CFG.timeframe, _sub_tf_name)
            if _sub_pm >= 2:
                _sub_h, _sub_l = _align_subbars(
                    ts, sub_df, _sub_pm, int(CFG.TF_SECONDS)
                )

    return AssetData(
        symbol=symbol, closes=closes, highs=highs, lows=lows,
        volumes=vols, timestamps=ts, X=X, sym_q=sym_q,
        H=H, dH=dH, d2H=d2H, E_therm=E_therm, F=F, dF=dF,
        C=C, V=V, h=h, score=sc,
        ema200=ema200_series, ema_accel=ema_accel,
        atr14=atr, adv_usd=adv,
        KE=KE, PE=PE, ME=ME, dKE=dKE, lya=ed['lya'], tri=tri,
        T_info=T_info,
        train_end=train_end, feat_start=feat_start, km=km,
        dynamic_k=dyn_k,
        gauge_force=gauge_force, friction=friction,
        delta_gap=delta_gap, geodesic_accel=geodesic_accel,
        score_q95_train=_score_q95_train,
        sub_highs=_sub_h,
        sub_lows=_sub_l,
        sub_per_main=_sub_pm,
        sub_tf=_sub_tf_name,
    )


# ════════════════════════════════════════════════════════════════
# § 13  بناء الإشارات (التعديلات ①④⑤)
# ════════════════════════════════════════════════════════════════
def compute_geodesic_target(price, geo_accel, friction, delta_gap, cfg):
    """
    القانون الثالث (مُحسَّن): هدف ربح ديناميكي بدون كبح Δ.
    """
    accel = abs(float(geo_accel))
    fric = float(friction) + 1e-6
    kelly_scale = getattr(cfg, 'KELLY_SCALE', 0.50)  # 0.50 بعد التعديل
    move_ratio = (accel / fric) * kelly_scale  # لا نقسم على Δ
    return float(price * move_ratio)


def compute_geodesic_kelly(ad, fi, cfg):
    """
    الطور الرابع: دالة المخاطرة اللوجستية الثرموديناميكية.
    """
    accel = abs(float(ad.geodesic_accel[fi]))
    fric  = float(ad.friction[fi]) + 1e-6
    T_info = float(ad.T_info[fi])
    
    # 1. القوة الخام
    force_ratio = accel / fric
    
    # 2. التخميد الحراري
    thermal_damp = np.exp(-0.01 / (T_info + 1e-6))
    
    # 3. الدالة اللوجستية (Sigmoid) لتوزيع المخاطرة بنعومة
    # نطرح 2.0 لنجعل مركز الدالة متوازناً مع قوى السوق الطبيعية
    x = (force_ratio * thermal_damp) - 2.0 
    sigmoid = 1.0 / (1.0 + np.exp(-x))
    
    f_star = cfg.MIN_RISK + (cfg.MAX_RISK - cfg.MIN_RISK) * sigmoid
    return float(np.clip(f_star, cfg.MIN_RISK, cfg.MAX_RISK))


# ════════════════════════════════════════════════════════════════
# § SINGULARITY TIMING — Resonance State Detector (Layer 1)
# ════════════════════════════════════════════════════════════════
#
# يكشف حالة الرنين الكسري عند الفهرس fi واتجاه محدد (BUY/SELL).
# الحالات: DORMANT / EMERGING / ACTIVE / DECAYING / INVALID
#
# المنطق الرياضي:
#   a(t) = geodesic_accel[fi]           — التسارع الآني
#   j(t) = a(t) - a(t-1)                — الجيرك (تسارع التسارع)
#   ρ    = (a·sign)/θ  +  λ·(j·sign)/θ_j  — مؤشر الرنين
# حيث sign = +1 للـ BUY و -1 للـ SELL.
#
# التصنيف:
#   ρ < 0                → DORMANT
#   0 ≤ ρ < RHO_EMERGING → DORMANT (لكن Jerk لا يزال ضعيفاً)
#   RHO_EMERGING ≤ ρ < RHO_ACTIVE → EMERGING (إن استمر الجيرك)
#   ρ ≥ RHO_ACTIVE       → ACTIVE  (إن استمر الجيرك)
#   a·sign < -θ أو a·sign ≥ 0.9θ → DECAYING (انفجر أو عكس)
# ════════════════════════════════════════════════════════════════

def _resonance_state_for_direction(ad, fi: int, action: str,
                                     cfg=None) -> Tuple[str, float]:
    """
    يُعيد (state, rho) للاتجاه المطلوب باستخدام مراتب مئوية.

    المنهجية الجديدة:
      - يُحسب توزيع |geodesic_accel| على نافذة متدحرجة (SING_LOOKBACK_BARS).
      - يُصنَّف التسارع الحالي حسب مرتبته ضمن هذا التوزيع.
      - هذا يتكيف تلقائياً مع تقلب كل أصل دون عتبات مطلقة.

    الحالات:
      - DECAYING : التسارع قوي وضد الاتجاه (a1_s < -median)
      - ACTIVE   : |a| في أعلى 10% وjerk مؤيد
      - EMERGING : |a| في أعلى 30% وjerk مؤيد
      - DORMANT  : باقي الحالات
      - INVALID  : بيانات غير كافية
    """
    if cfg is None:
        cfg = CFG

    if not getattr(cfg, 'SING_TIMING_ENABLED', False):
        return "DORMANT", 0.0

    try:
        if fi < 30:
            return "INVALID", 0.0
        if fi >= len(ad.geodesic_accel):
            return "INVALID", 0.0

        # ── نافذة التاريخ ──
        _lookback = int(getattr(cfg, 'SING_LOOKBACK_BARS', 200))
        _start = max(0, fi - _lookback)
        _window = ad.geodesic_accel[_start:fi + 1]

        if len(_window) < 30:
            return "DORMANT", 0.0

        _abs_window = np.abs(_window).astype(np.float64)
        _a_med = float(np.median(_abs_window))
        _a_p70 = float(np.percentile(_abs_window, 70))
        _a_p90 = float(np.percentile(_abs_window, 90))

        if _a_med < 1e-12:
            return "DORMANT", 0.0

        # ── القيم الحالية ──
        a1 = float(ad.geodesic_accel[fi])
        j1 = a1 - float(ad.geodesic_accel[fi - 1])
        sign = 1.0 if action == "BUY" else -1.0
        a1_s = a1 * sign
        j1_s = j1 * sign
        a1_abs = abs(a1)

        # ── DECAYING: التسارع قوي وضد الاتجاه ──
        # إذا كان التسارع > الوسيط وضد الاتجاه → انفجار معاكس
        if a1_s < -_a_med:
            return "DECAYING", float(-a1_abs / max(_a_p90, 1e-12))

        # ── رتبة |a| الحالية في النافذة ──
        pct_rank = float(np.mean(_abs_window <= a1_abs))

        # ── التحقق من اتجاه الجيرك ──
        # Jerk مؤيد = j1_s > 0 (التسارع يزيد في اتجاهنا)
        j1_ok = (j1_s > 0.0)

        # ── ACTIVE: أعلى 10% + jerk مؤيد ──
        if pct_rank >= float(getattr(cfg, 'SING_PCT_ACTIVE', 0.90)) and j1_ok:
            return "ACTIVE", pct_rank

        # ── EMERGING: أعلى 30% + jerk مؤيد ──
        if pct_rank >= float(getattr(cfg, 'SING_PCT_EMERGING', 0.70)) and j1_ok:
            return "EMERGING", pct_rank

        # ── DECAYING: التسارع في اتجاهنا لكنه ضعيف ومتراجع ──
        # (اختياري: إذا كان jerk سلبياً بقوة، قد يعني انتهاء الانفجار)
        if (a1_s > 0.0 and j1_s < -0.3 * _a_med):
            return "DECAYING", pct_rank

        return "DORMANT", pct_rank

    except Exception as e:
        log.debug(f"[Sing-Timing] state error: {e}")
        return "INVALID", 0.0

# ════════════════════════════════════════════════════════════════
# § SINGULARITY LAYER 3 — Funding Guard Helper
# ════════════════════════════════════════════════════════════════
#
# يحسب عدد الدقائق حتى موعد التمويل القادم على Binance USDT-M.
# مواعيد التمويل الثابتة: 00:00، 08:00، 16:00 UTC.
#
# المنطق:
#   current_hour → (hour // 8 + 1) * 8
#   إذا تجاوز 24 → 0 (منتصف الليل غداً)
#   الدقائق المتبقية = delta_hours × 60 − current_minute
#
# Returns
# -------
# int
#   عدد الدقائق حتى التمويل القادم (قد يكون سالباً إذا مرّ الوقت).
# ════════════════════════════════════════════════════════════════

def _minutes_to_next_funding_utc(cfg=None) -> int:
    """
    يحسب الدقائق المتبقية حتى موعد التمويل القادم على Binance.

    إذا كان NOW قبل 00:00، 08:00، أو 16:00 UTC:
        يرجع عدد الدقائق الإيجابية.
    إذا كان NOW عند موعد التمويل بالضبط:
        يرجع 0.
    """
    if cfg is None:
        cfg = CFG
    try:
        funding_hours = tuple(getattr(
            cfg, 'SING_FUNDING_HOURS_UTC', (0, 8, 16)
        ))
        if not funding_hours:
            funding_hours = (0, 8, 16)

        now_utc = datetime.now(timezone.utc)
        h = int(now_utc.hour)
        m = int(now_utc.minute)

        # ابحث عن أول ساعة تمويل ≥ h
        next_h = None
        for fh in sorted(funding_hours):
            if fh > h:
                next_h = fh
                break
            if fh == h and m == 0:
                next_h = fh
                break

        if next_h is None:
            # لا يوجد موعد اليوم → التالي غداً
            next_h = min(funding_hours) + 24

        delta_minutes = (next_h - h) * 60 - m
        return int(delta_minutes)
    except Exception as e:
        log.debug(f"[Funding Guard] minutes calc failed: {e}")
        return 9999  # fail-open (لا حجب)

def compute_geodesic_stop(entry_price, ad, fi, cfg):
    """
    الطور الخامس: حساب الوقف بنصف قطر فيشر (Decoherence Edge).

    [TF-UNIFIED] sl_dist يُحسب بوحدة σ_price = E_therm[fi] × entry_price.
    هذا يضمن أن sl_dist/σ ثابت عبر الأُطر.

    على 1h مع uncertainty=1, friction≈0.18:
        sl_sigma = 2.0 × 1 / (1 + 0.18×5) = 1.05σ
    وهو مطابق لسلوك الإصدار السابق على 1h.
    """
    # مقياس عدم اليقين
    uncertainty = np.clip(ad.V[fi] / (np.mean(ad.V) + 1e-9), 0.5, 3.0)
    friction = float(ad.friction[fi]) + 1e-6

    # σ_price في هذه الشمعة
    try:
        sigma_frac = float(ad.E_therm[fi]) if 0 <= fi < len(ad.E_therm) else 0.01
        if not np.isfinite(sigma_frac) or sigma_frac <= 1e-6:
            sigma_frac = 0.01
    except Exception:
        sigma_frac = 0.01
    sigma_price = sigma_frac * entry_price

    # SL بوحدة σ (عدد الانحرافات المعيارية)
    _sl_kappa = float(getattr(cfg, 'SL_REF_KAPPA', 2.0))
    sl_sigma = (_sl_kappa * uncertainty) / (1.0 + friction * 5.0)

    # clip بوحدة σ
    _min_s = float(getattr(cfg, 'SL_MIN_SIGMA', 1.0))
    _max_s = float(getattr(cfg, 'SL_MAX_SIGMA', 5.0))
    sl_sigma = float(np.clip(sl_sigma, _min_s, _max_s))

    return float(sl_sigma * sigma_price)


# ════════════════════════════════════════════════════════════════
# § 12.85  UNIFIED ENTRY — Geometry Rebuild at Market Price
# ════════════════════════════════════════════════════════════════
#
# عند الدخول بسعر السوق (Stage 2)، لا نستخدم SL/TP القديمة لأنها
# محسوبة من tunnel_entry_p. نُعيد بناءها من نقطة التوازن الجديدة
# S_new = p_current ∓ friction_drag_current، ثم نحسب sl_dist_new
# بنفس دالة compute_geodesic_stop المستخدمة في build_signals.
#
# النتيجة: R:R = 2.0 دائماً، والهندسة طازجة بنيوياً.
# ════════════════════════════════════════════════════════════════

def _recompute_entry_geometry_at_market(sig, ad, entry_ci, entry_fi, cfg):
    """
    يعيد بناء SL/TP من سعر السوق الحالي بنفس فيزياء build_signals.

    Returns
    -------
    dict | None
        {'entry_px', 'S_new', 'sl_dist_new', 'sl', 'tp1'}
        أو None عند الفشل.
    """
    try:
        if entry_ci < 0 or entry_ci >= len(ad.closes):
            return None
        if entry_fi < 0 or entry_fi >= len(ad.friction):
            return None

        p_current = float(ad.closes[entry_ci])
        if p_current <= 0:
            return None

        # friction_drag_current (نفس معادلة build_signals)
        fric_current = float(ad.friction[entry_fi])
        if not np.isfinite(fric_current) or fric_current < 0:
            fric_current = 0.0

        # ══ [TF-UNIFIED] friction_drag بوحدة σ_price (مطابق لـ build_signals) ══
        try:
            _sigma_frac_g = float(ad.E_therm[entry_fi]) if 0 <= entry_fi < len(ad.E_therm) else 0.01
            if not np.isfinite(_sigma_frac_g) or _sigma_frac_g <= 1e-6:
                _sigma_frac_g = 0.01
        except Exception:
            _sigma_frac_g = 0.01
        _sigma_price_g = _sigma_frac_g * p_current
        _fd_kappa_g = float(getattr(cfg, 'FRICTION_DIP_KAPPA', 4.0))
        friction_drag = _fd_kappa_g * _sigma_price_g

        if sig.action == "BUY":
            S_new = p_current - friction_drag
        else:
            S_new = p_current + friction_drag

        # نفس دالة build_signals
        sl_dist_new = compute_geodesic_stop(S_new, ad, entry_fi, cfg)
        if sl_dist_new <= 0 or not np.isfinite(sl_dist_new):
            return None

        if sig.action == "BUY":
            sl_new = S_new - sl_dist_new
            tp_new = S_new + (sl_dist_new * 2.0)
        else:
            sl_new = S_new + sl_dist_new
            tp_new = S_new - (sl_dist_new * 2.0)

        return {
            'entry_px': p_current,
            'S_new': S_new,
            'sl_dist_new': float(sl_dist_new),
            'sl': float(sl_new),
            'tp1': float(tp_new),
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# § 12.86  UNIFIED ENTRY — Stage 2 Conditions
# ════════════════════════════════════════════════════════════════

def _check_unified_stage2(sig, ad, current_ci, current_fi, cfg):
    """
    فحص شروط Stage 2 (الدخول بسعر السوق بعد فشل Stage 1).

    الشروط:
      1. العمر ≤ UNIFIED_MAX_AGE_BARS_1H (بالوحدات الفعلية).
      2. الزخم المؤيد: p_current تحرك في اتجاه الإشارة
         بأكثر من UNIFIED_MOMENTUM_KAPPA × σ_bar.
      3. الإشارة حيّة: score[current_fi] ≥ UNIFIED_FRESH_SCORE_FRAC
         × score[signal_fi].

    Returns
    -------
    (ok, reason, p_current)
    """
    if not getattr(cfg, 'UNIFIED_ENTRY_ENABLED', True):
        return False, "unified_disabled", 0.0

    try:
        age_bars = current_ci - int(sig.close_idx)
        if age_bars <= 0:
            return False, "not_yet", 0.0

        max_age = effective_bars(
            int(getattr(cfg, 'UNIFIED_MAX_AGE_BARS_1H', 12))
        )
        if age_bars > max_age:
            return False, f"too_old({age_bars}>{max_age})", 0.0

        p_current = float(ad.closes[current_ci])
        p_signal = float(ad.closes[int(sig.close_idx)])
        if p_signal <= 0 or p_current <= 0:
            return False, "invalid_prices", 0.0

        # ── σ_bar الحالي ──
        try:
            sigma_bar = float(ad.E_therm[current_fi]) \
                if 0 <= current_fi < len(ad.E_therm) else 0.01
            if not np.isfinite(sigma_bar) or sigma_bar <= 1e-6:
                sigma_bar = 0.01
        except Exception:
            sigma_bar = 0.01

        # ── شرط الزخم ──
        kappa = float(getattr(cfg, 'UNIFIED_MOMENTUM_KAPPA', 0.5))
        threshold = kappa * sigma_bar * p_signal

        if sig.action == "BUY":
            momentum_ok = (p_current - p_signal) > threshold
            move = p_current - p_signal
        else:
            momentum_ok = (p_signal - p_current) > threshold
            move = p_signal - p_current

        if not momentum_ok:
            return False, (f"no_momentum(move={move:.6f}<"
                           f"thr={threshold:.6f})"), 0.0

        # ── شرط حداثة الإشارة ──
        if getattr(cfg, 'UNIFIED_REQUIRE_FRESH_SIGNAL', True):
            try:
                score_now = float(ad.score[current_fi]) \
                    if 0 <= current_fi < len(ad.score) else 0.0
                score_orig = float(sig.score)
                fresh_frac = float(getattr(cfg,
                    'UNIFIED_FRESH_SCORE_FRAC', 0.85))
                if score_orig > 0 and \
                        score_now < score_orig * fresh_frac:
                    return False, (f"stale_score({score_now:.2f}<"
                                   f"{score_orig*fresh_frac:.2f})"), 0.0
            except Exception:
                pass

        return True, "OK", p_current
    except Exception as e:
        return False, f"error:{e}", 0.0

def compute_dynamic_leverage(capital, cfg, symbol=None):
    """
    Dynamic leverage: Lev(C) = LEVERAGE_BASE / √(C/C₀)

    [FIX-01-PROPER] Snap to the symbol's actual valid tiers:
      * If `symbol` is provided and cached → use its tiers
      * Otherwise → fallback ladder clipped to [LEVERAGE_MIN, LEVERAGE_MAX]

    The snap prevents Binance's -4028 (invalid leverage) rejection
    without hardcoding a single global tuple.
    """
    C0 = max(float(cfg.INITIAL_CAPITAL), 1e-9)
    raw_lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    raw_lev = int(np.clip(round(raw_lev),
                          cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))

    # Get the symbol's valid ladder
    tiers = _symbol_tiers(symbol, cfg)

    # Clip to [LEVERAGE_MIN, LEVERAGE_MAX]
    lo = int(cfg.LEVERAGE_MIN)
    hi = int(cfg.LEVERAGE_MAX)
    valid = [int(t) for t in tiers if lo <= int(t) <= hi]
    if not valid:
        return lo

    # Snap to closest tier ≤ raw_lev
    below = [t for t in valid if t <= raw_lev]
    if below:
        return int(below[-1])
    return int(valid[0])



# ════════════════════════════════════════════════════════════════
# § 12.9  Support/Resistance Detection
# ════════════════════════════════════════════════════════════════

def _find_swing_levels(ad, current_ci: int, lookback: int):
    """
    Find candidate support/resistance levels as (price, idx) pairs.

    A swing low at bar j requires:
        lows[j] < lows[j-1]  AND  lows[j] < lows[j+1]
    """
    supports = []
    resistances = []
    try:
        n = len(ad.lows)
        if current_ci < lookback + 2:
            return supports, resistances
        start = current_ci - lookback
        end = current_ci - 1

        for j in range(start + 1, end):
            l_prev = float(ad.lows[j - 1])
            l_curr = float(ad.lows[j])
            l_next = float(ad.lows[j + 1])
            if l_curr < l_prev and l_curr < l_next:
                supports.append((l_curr, j))

            h_prev = float(ad.highs[j - 1])
            h_curr = float(ad.highs[j])
            h_next = float(ad.highs[j + 1])
            if h_curr > h_prev and h_curr > h_next:
                resistances.append((h_curr, j))
    except Exception as e:
        log.debug(f"[SR] swing detection failed {ad.symbol}: {e}")
    return supports, resistances


def _cluster_levels(levels_with_idx, tolerance: float):
    """
    Cluster (price, idx) pairs into a single level per cluster.
    Preserves last_touch_idx = max index among cluster members.
    """
    if not levels_with_idx:
        return []
    # Sort by price descending
    sorted_levels = sorted(levels_with_idx, key=lambda x: -x[0])
    clusters = []
    for price, idx in sorted_levels:
        placed = False
        for c in clusters:
            if abs(price - c['price']) / max(c['price'], 1e-12) < tolerance:
                cnt = c['touch_count']
                c['price'] = (c['price'] * cnt + price) / (cnt + 1)
                c['touch_count'] = cnt + 1
                if idx > c['last_touch_idx']:
                    c['last_touch_idx'] = idx
                placed = True
                break
        if not placed:
            clusters.append({
                'price': price,
                'touch_count': 1,
                'last_touch_idx': idx,
            })
    return clusters


def _compute_level_strength(ad, current_ci: int, cluster: Dict) -> float:
    """
    Combined strength = touches × time_decay × volume_factor.

    time_decay uses bars since LAST touch (not window start):
        time_factor = exp(-Δt / τ_decay)
    """
    try:
        tau = float(getattr(CFG, 'SR_DECAY_TAU', 50.0))
        lookback = int(getattr(CFG, 'SR_LOOKBACK', 100))
        level_price = float(cluster['price'])
        last_idx = int(cluster.get('last_touch_idx', current_ci - lookback))

        delta_t = max(1, current_ci - last_idx)
        time_factor = float(np.exp(-delta_t / tau))

        # Volume factor: mean volume near level / mean volume overall
        tol = float(getattr(CFG, 'SR_TOUCH_TOLERANCE', 0.0025))
        start = max(0, current_ci - lookback)
        vol_at = []
        for j in range(start, current_ci):
            try:
                lj = float(ad.lows[j])
                hj = float(ad.highs[j])
                if (abs(lj - level_price) / max(level_price, 1e-12) < tol
                        or abs(hj - level_price) / max(level_price, 1e-12) < tol):
                    vol_at.append(float(ad.volumes[j]))
            except Exception:
                continue
        if not vol_at:
            return 0.0
        vol_mean_all = float(np.mean(ad.volumes[start:current_ci])) + 1e-12
        vol_factor = float(np.mean(vol_at)) / vol_mean_all

        strength = float(cluster['touch_count']) * time_factor * vol_factor
        return strength
    except Exception as e:
        log.debug(f"[SR] strength compute failed: {e}")
        return 0.0


_SR_REJECT_LOG: Dict[str, int] = defaultdict(int)


def _sr_filter_check(sig, ad, current_ci: int) -> Tuple[bool, str]:
    """
    Reject signal if its SL is not protected by a strong S/R level.
    Logs aggregate rejection reasons for diagnostics.
    """
    if not getattr(CFG, 'SR_FILTER_ENABLED', False):
        return True, "OK"

    try:
        lookback = int(getattr(CFG, 'SR_LOOKBACK', 100))
        min_touches = int(getattr(CFG, 'SR_MIN_TOUCHES', 3))
        tol = float(getattr(CFG, 'SR_TOUCH_TOLERANCE', 0.0025))
        str_thr = float(getattr(CFG, 'SR_STRENGTH_THRESHOLD', 1.5))
        sl_prox = float(getattr(CFG, 'SR_SL_PROXIMITY', 0.004))

        supports, resistances = _find_swing_levels(ad, current_ci, lookback)
        candidates = supports if sig.action == "BUY" else resistances

        if not candidates:
            _SR_REJECT_LOG['no_swings'] += 1
            return False, "no_swing_levels"

        clusters = _cluster_levels(candidates, tol)
        if not clusters:
            _SR_REJECT_LOG['no_clusters'] += 1
            return False, "no_clusters"

        sl_price = float(sig.sl)
        best_strength = 0.0
        best_level = 0.0
        best_dist = 999.0

        for c in clusters:
            if c['touch_count'] < min_touches:
                continue
            dist = abs(sl_price - c['price']) / max(sl_price, 1e-12)
            if dist > sl_prox:
                continue
            if sig.action == "BUY" and c['price'] > sl_price * (1.0 + tol):
                continue
            if sig.action == "SELL" and c['price'] < sl_price * (1.0 - tol):
                continue
            strength = _compute_level_strength(ad, current_ci, c)
            if strength > best_strength:
                best_strength = strength
                best_level = c['price']
                best_dist = dist

        if best_strength < str_thr:
            _SR_REJECT_LOG['weak_strength'] += 1
            # Log first 20 rejections per symbol for diagnosis
            if _SR_REJECT_LOG['weak_strength'] <= 20:
                log.debug(
                    f"[SR] {sig.symbol} {sig.action} weak: "
                    f"strength={best_strength:.2f} < {str_thr:.2f} "
                    f"(level={best_level:.6f}, dist={best_dist*1e4:.1f}bps)"
                )
            return False, f"weak_SR({best_strength:.2f})"
        return True, f"OK(strength={best_strength:.2f})"
    except Exception as e:
        log.warning(f"[SR] check failed {sig.symbol}: {e}")
        return True, "SR_error"  # fail open


# ════════════════════════════════════════════════════════════════
# [SMART ENTRY] — ATR base + regime + structure
# ════════════════════════════════════════════════════════════════

def _regime_entry_mult(regime: str) -> float:
    """Entry dip multiplier by regime."""
    if regime == "explosive":
        return float(getattr(CFG, 'ENTRY_REGIME_EXPLOSIVE_MULT', 1.30))
    if regime == "ranging":
        return float(getattr(CFG, 'ENTRY_REGIME_RANGING_MULT', 0.60))
    return float(getattr(CFG, 'ENTRY_REGIME_TRENDING_MULT', 1.00))


def _find_nearest_swing(ad, ci: int, lookback: int, kind: str):
    """
    Most recent swing low (kind='low') or swing high (kind='high')
    within [ci - lookback, ci - 1]. Returns price or None.
    """
    try:
        end = ci - 1
        start = max(1, ci - lookback)
        if end - start < 3 or ad is None:
            return None
        if kind == "low":
            arr = ad.lows
            for j in range(end - 1, start, -1):
                if arr[j] < arr[j-1] and arr[j] < arr[j+1]:
                    return float(arr[j])
        else:
            arr = ad.highs
            for j in range(end - 1, start, -1):
                if arr[j] > arr[j-1] and arr[j] > arr[j+1]:
                    return float(arr[j])
    except Exception:
        return None
    return None


def _compute_entry_dip(ad, fi: int, ci: int, action: str,
                       close_price: float) -> float:
    """
    Four-layer entry dip (price units, positive).

      Layer 1: base_dip = ENTRY_ATR_MULT × ATR_current
      Layer 2: × regime_multiplier (ranging / trending / explosive)
      Layer 3: structure anchor — snap to nearest swing within a
               reasonable band; otherwise keep ATR dip.
      Layer 4: applied later at repricing time (time decay) — NOT here.

    All layers guarded by ENTRY_* flags. Returns 0.0 on any failure,
    which the caller interprets as "use a tiny fallback dip".
    """
    try:
        if ad is None or ci < 0 or ci >= len(ad.closes):
            return 0.0
        atr_now = float(ad.atr14[ci]) if ci < len(ad.atr14) else 0.0
        if atr_now <= 0 or not np.isfinite(atr_now):
            return 0.0

        # ── Layer 1: ATR base ──
        dip = float(getattr(CFG, 'ENTRY_ATR_MULT', 0.40)) * atr_now

        # ── Layer 2: regime ──
        if getattr(CFG, 'ENTRY_REGIME_SCALE', True) and fi >= 0:
            lookback = int(getattr(CFG, 'ENTRY_REGIME_LOOKBACK', 100))
            regime = _classify_regime_local(ad, fi, lookback)
            dip *= _regime_entry_mult(regime)

        # ── Layer 3: structure anchor ──
        if getattr(CFG, 'ENTRY_STRUCTURE_ANCHOR', True):
            adv_now = float(ad.adv_usd[ci]) if ci < len(ad.adv_usd) else 0.0
            if adv_now >= float(getattr(CFG, 'ENTRY_STRUCTURE_MIN_ADV_USD',
                                         1e8)):
                lookback = int(getattr(CFG, 'ENTRY_REGIME_LOOKBACK', 100))
                lo_mult = float(getattr(CFG,
                    'ENTRY_STRUCTURE_RANGE_MULT_LO', 0.30))
                hi_mult = float(getattr(CFG,
                    'ENTRY_STRUCTURE_RANGE_MULT_HI', 2.00))
                lo_b, hi_b = dip * lo_mult, dip * hi_mult

                if action == "BUY":
                    lvl = _find_nearest_swing(ad, ci, lookback, "low")
                    if lvl is not None and lvl < close_price:
                        dist = close_price - lvl
                        if lo_b <= dist <= hi_b:
                            buf = atr_now * float(getattr(CFG,
                                'ENTRY_STRUCTURE_BUFFER_MULT', 0.10))
                            dip = max(dist - buf, lo_b)
                else:
                    lvl = _find_nearest_swing(ad, ci, lookback, "high")
                    if lvl is not None and lvl > close_price:
                        dist = lvl - close_price
                        if lo_b <= dist <= hi_b:
                            buf = atr_now * float(getattr(CFG,
                                'ENTRY_STRUCTURE_BUFFER_MULT', 0.10))
                            dip = max(dist - buf, lo_b)

        # ── Clamp ──
        min_d = float(getattr(CFG, 'ENTRY_MIN_DIP_MULT', 0.15)) * atr_now
        max_d = float(getattr(CFG, 'ENTRY_MAX_DIP_MULT', 1.00)) * atr_now
        dip = float(np.clip(dip, min_d, max_d))
        return float(dip)
    except Exception:
        return 0.0

# ════════════════════════════════════════════════════════════════
# § TRADE FILTER — Pre-entry multi-signal rejection
# ════════════════════════════════════════════════════════════════

_FILTER_STATS: Dict = {
    'total_signals': 0,
    'kept': 0,
    'rejected': 0,
    'vote_counts': defaultdict(int),   # كم مرة رُفض بسبب كل مزيج
    'vote_singles': defaultdict(int),  # عدد الأصوات لكل صوت منفرد
}


def _filter_reset_stats() -> None:
    """Reset filter statistics (called at start of each run)."""
    _FILTER_STATS['total_signals'] = 0
    _FILTER_STATS['kept'] = 0
    _FILTER_STATS['rejected'] = 0
    _FILTER_STATS['vote_counts'].clear()
    _FILTER_STATS['vote_singles'].clear()


def _trade_filter_check(sig, ad, fi, ci) -> Tuple[bool, str]:
    """
    فحص فلتر الدخول. يعيد (reject, reason).

    المنطق:
      - يحسب "أصوات الرفض" من إشارات مستقلة.
      - يرفض الإشارة إذا كان عدد الأصوات >= FILTER_MIN_VOTES.

    الأصوات:
      1. action_bias  : action == 'BUY' (معطّل افتراضياً)
      2. ema_slope    : ميل EMA200 ضد الإشارة
      3. high_atr     : atr_frac > FILTER_ATR_FRAC_MAX
      4. friction     : friction_drag/sl_dist > FILTER_FRICTION_DRAG_MAX
    """
    if not getattr(CFG, 'FILTER_ENABLED', False):
        return False, ""

    try:
        votes = []
        action = getattr(sig, 'action', '?')
        price = float(getattr(sig, 'price', 0.0))
        sl = float(getattr(sig, 'sl', 0.0))
        atr = float(getattr(sig, 'atr', 0.0))

        if price <= 0:
            return False, ""

        # ── Vote 1: action_bias (BUY) — معطّل افتراضياً ──
        if getattr(CFG, 'FILTER_USE_ACTION_BIAS', False):
            if action == 'BUY':
                votes.append('action_bias')

        # ── Vote 2: EMA slope ضد الإشارة ──
        if getattr(CFG, 'FILTER_USE_EMA_SLOPE', True):
            try:
                if (ad is not None
                        and 0 <= ci < len(ad.ema200)
                        and ci >= 50):
                    ema_now = float(ad.ema200[ci])
                    ema_prev = float(ad.ema200[ci - 50])
                    slope = (ema_now - ema_prev) / 50.0
                    if ((action == 'BUY' and slope < 0) or
                            (action == 'SELL' and slope > 0)):
                        votes.append('ema_slope')
            except Exception:
                pass

        # ── Vote 3: تقلب مرتفع ──
        if getattr(CFG, 'FILTER_USE_HIGH_ATR', True):
            try:
                atr_frac = atr / max(price, 1e-12)
                _thr = float(getattr(CFG, 'FILTER_ATR_FRAC_MAX', 0.024))
                if atr_frac > _thr:
                    votes.append('high_atr')
            except Exception:
                pass

        # ── Vote 4: friction_drag / sl_dist مرتفع ──
        if getattr(CFG, 'FILTER_USE_FRICTION_DRAG', True):
            try:
                sl_dist = abs(price - sl)
                if sl_dist > 1e-12:
                    sigma_frac = float(ad.E_therm[fi]) \
                        if (ad is not None
                            and 0 <= fi < len(ad.E_therm)) else 0.01
                    if not np.isfinite(sigma_frac) or sigma_frac <= 1e-6:
                        sigma_frac = 0.01
                    sigma_price = sigma_frac * price
                    fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))
                    friction_drag = fd_kappa * sigma_price
                    ratio = friction_drag / sl_dist
                    _thr = float(getattr(CFG, 'FILTER_FRICTION_DRAG_MAX', 2.5))
                    if ratio > _thr:
                        votes.append('friction_drag')
            except Exception:
                pass

        # ── القرار ──
        _min_votes = int(getattr(CFG, 'FILTER_MIN_VOTES', 2))
        if len(votes) >= _min_votes:
            reason = '|'.join(votes)
            # إحصاءات
            _FILTER_STATS['vote_counts'][reason] += 1
            for v in votes:
                _FILTER_STATS['vote_singles'][v] += 1
            if getattr(CFG, 'FILTER_LOG_REJECTIONS', False):
                log.debug(f"[Filter] {sig.symbol} {action} rejected: {reason}")
            return True, reason

        return False, ""
    except Exception as e:
        # fail-open: خطأ في الفلتر لا يمنع الصفقة
        log.debug(f"[Filter] exception (fail-open): {e}")
        return False, "filter_error"

def build_signals(assets, mode="backtest"):
    """
    محرك استشعار الإشارات الكمي:
    1. Boltzmann Activation: يمرر القوة والحرارة لحساب احتمال حدوث الاختراق.
    2. Phase-Matched Entry: يضع أمر معلق Limit Maker عند نقطة سكون الهبوط المتوقعة.
    3. Gauge Filter: يفلتر الإشارات بناءً على قوة حقل المقياس.
    """
    sigs = []

    # ══ [GAUGE-FILTER] حساب العتبات العالمية مرة واحدة ══
    _gauge_thr_buy = 0.0
    _gauge_thr_sell = 0.0
    if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):
        _gauge_pool = []
        for _sym, _ad in assets.items():
            try:
                gf = getattr(_ad, 'gauge_force', None)
                if gf is None or len(gf) == 0:
                    continue
                # استخدام جزء الاختبار فقط (لا تدريب)
                _valid = gf[_ad.train_end:]
                _valid = _valid[_valid > 0]
                if len(_valid) > 0:
                    _gauge_pool.extend(_valid.tolist())
            except Exception:
                continue

        if len(_gauge_pool) >= int(CFG.GAUGE_MIN_SAMPLES):
            _gauge_arr = np.array(_gauge_pool)
            _gauge_thr_buy = float(np.percentile(
                _gauge_arr, CFG.GAUGE_PERCENTILE_BUY * 100
            ))
            _gauge_thr_sell = float(np.percentile(
                _gauge_arr, CFG.GAUGE_PERCENTILE_SELL * 100
            ))
            # ══ [SPAM-FIX] اطبع فقط عند تغيّر الـ pool ══
            _pool_size = len(_gauge_pool)
            _last_size = getattr(build_signals, '_last_gauge_pool_size', 0)
            if abs(_pool_size - _last_size) > _pool_size * 0.05:
                log.info(
                    f"[Gauge-Filter] thresholds: "
                    f"BUY>p{int(CFG.GAUGE_PERCENTILE_BUY*100)}="
                    f"{_gauge_thr_buy:.5f}, "
                    f"SELL>p{int(CFG.GAUGE_PERCENTILE_SELL*100)}="
                    f"{_gauge_thr_sell:.5f} "
                    f"(pool={_pool_size})"
                )
                build_signals._last_gauge_pool_size = _pool_size
        else:
            log.warning(
                f"[Gauge-Filter] pool too small ({len(_gauge_pool)}"
                f"<{CFG.GAUGE_MIN_SAMPLES}) — filter disabled"
            )

    for sym, ad in assets.items():
        n = len(ad.score)
        # [PERF-FIX] في live نحتاج قيمة fi واحدة فقط، لا 17,500
        if mode == "backtest":
            fi_range = range(ad.train_end + 1, n)
        else:
            _target_ci = len(ad.closes) - 2
            _target_fi = _target_ci - ad.feat_start
            if _target_fi < ad.train_end + 1 or _target_fi >= n:
                continue
            fi_range = (_target_fi,)

        for fi in fi_range:
            ci = ad.feat_start + fi

            # كسر سجن الزمن
            if mode == "backtest":
                if ci >= len(ad.closes) - 1: continue
            else:
                if ci != len(ad.closes) - 2: continue

            p = ad.closes[ci]
            if p <= 0: continue
            
            geo_accel = float(ad.geodesic_accel[fi])
            fric_val = float(ad.friction[fi]) + 1e-6
            T_info = float(ad.T_info[fi])
            
            # [التعديل ①]: Boltzmann Activation Probability (حل المجاعة المعلوماتية)
            # نعامل القوة الجيوديسية كطاقة تنشيط والحرارة كطاقة حركية للنظام
            force_mag = abs(geo_accel) + 1e-9
            P_activation = np.exp(-fric_val / (force_mag * T_info))
            
            # لا ندخل إلا إذا كان احتمال التفاعل والتغلب على الاحتكاك الحراري أكبر من 35%
            if P_activation < 0.35: 
                continue

            # ══ [ABLATION-1] Direction from mean-reversion in σ units ══
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
            # [ABLATION-2c] softer deviation gate
            if abs(_z_dev) < 1.5:
                continue
            action = "BUY" if _z_dev < 0 else "SELL"

            # ══ [SELL-RND] بوابة SELL المستقلة ══
            # BUY لا يُلمَس. SELL فقط يُمرّر عبر هذه البوابة.
            if action == "SELL":
                if not getattr(CFG, 'SELL_ENABLED', False):
                    continue
                if ad.score[fi] < float(getattr(CFG, 'SELL_MIN_SCORE', 3)):
                    continue
                if abs(_z_dev) < float(getattr(CFG, 'SELL_MIN_ZDEV', 1.5)):
                    continue
                # EMA-aligned SELL (only sell into a downtrend)
                if getattr(CFG, 'SELL_REQUIRE_EMA_DOWN', False):
                    _lb_s = 50
                    if ci >= _lb_s:
                        _slope_s = (ad.ema200[ci] -
                                    ad.ema200[ci - _lb_s]) / _lb_s
                        if _slope_s >= 0:
                            continue
                # Liquid pairs only
                if getattr(CFG, 'SELL_MAJOR_ONLY', False):
                    if sym not in getattr(CFG, 'SELL_MAJOR_PAIRS',
                                           ("BTC/USDT", "ETH/USDT",
                                            "SOL/USDT", "BNB/USDT")):
                        continue
                # Volatility gate (higher vol required)
                _atr_frac_s = float(ad.atr14[ci]) / max(float(p), 1e-12) \
                              if ci < len(ad.atr14) else 0.0
                if _atr_frac_s < float(getattr(CFG,
                                                'SELL_MIN_ATR_FRAC', 0.0)):
                    continue

            # ══ [GAUGE-FILTER] ══
            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):
                # [SELL-RND] BUY uses gauge pool; SELL uses
                # SELL_GAUGE_PCT (independent threshold) when SELL_ENABLED.
                if action == "SELL" and not getattr(CFG, 'SELL_ENABLED',
                                                     False):
                    if getattr(CFG, 'GAUGE_DISABLE_SELL', False):
                        continue
                try:
                    _gf = float(ad.gauge_force[fi])
                    if action == "BUY" and _gf < _gauge_thr_buy:
                        continue
                    if action == "SELL":
                        if getattr(CFG, 'SELL_ENABLED', False):
                            # Recompute percentile-based threshold on the fly
                            _pct_s = float(getattr(CFG, 'SELL_GAUGE_PCT',
                                                    0.95))
                            _thr_s = np.percentile(_gauge_arr, _pct_s * 100) \
                                     if len(_gauge_pool) > 0 else _gauge_thr_sell
                            if _gf < _thr_s:
                                continue
                        else:
                            if _gf < _gauge_thr_sell:
                                continue
                except Exception:
                    pass

            # ══ [FIX 2] Regime filter — reject trending markets ══
            if getattr(CFG, 'REGIME_FILTER_ENABLED', False):
                _lb = int(getattr(CFG, 'REGIME_EMA_LOOKBACK', 50))
                if ci - _lb >= 0 and ci < len(ad.ema200):
                    _slope = (ad.ema200[ci] - ad.ema200[ci - _lb]) / max(_lb, 1)
                    _atr_now = float(ad.atr14[ci]) if ci < len(ad.atr14) else 0.0
                    if _atr_now > 0:
                        _slope_norm = abs(_slope) * _lb / _atr_now
                        _slope_sign = 1.0 if _slope > 0 else -1.0
                        _thr = float(getattr(CFG, 'REGIME_SLOPE_ATR_MAX', 2.0))
                        if _slope_norm > _thr:
                            # Trending — reject regardless of direction.
                            # Mean-reversion should not fight a strong trend.
                            continue

            # ══ [ADAPTIVE FIX #4] dynamic per-asset MIN_SCORE ══
            _min_score = float(CFG.MIN_SCORE)

            if getattr(CFG, 'DYNAMIC_MIN_SCORE_ENABLED', False):
                _min_score = float(getattr(ad, 'score_q95_train',
                                            CFG.MIN_SCORE))
            if ad.score[fi] < _min_score: continue

            # ══ [SR FILTER] SL must be protected by strong support/resistance ══
            # (computed after SL/TP is known — moved below in this version)
            # See the deferred check after SL/TP computation.

            # ══ [MEAN-REVERSION DIP — restores the OLD behavior] ══
            # The dip the market must travel to exhaust its momentum.
            # = friction_cost × 10 = what the market pays in entropy to
            # reverse direction. Empirically:
            #   OLD (friction dip ≈ 2%): fill 18%, 100% TP hit → edge +98
            #   NEW (ATR dip ≈ 0.34%):   fill 46%,  10% TP hit → edge −1
            # The friction dip is the primary signal; ATR is a floor
            # only for very-quiet markets to avoid a near-zero dip.
            # ══ [TF-UNIFIED] friction_drag بوحدة σ_price ══
            # على 1h مع σ≈0.44% و κ=4.0: dip = 1.76% (مطابق للسلوك السابق)
            # على 4h مع σ≈0.91% و κ=4.0: dip = 3.64%
            # على 5m مع σ≈0.09% و κ=4.0: dip = 0.36%
            try:
                _sigma_frac_bs = float(ad.E_therm[fi]) if fi < len(ad.E_therm) else 0.01
                if not np.isfinite(_sigma_frac_bs) or _sigma_frac_bs <= 1e-6:
                    _sigma_frac_bs = 0.01
            except Exception:
                _sigma_frac_bs = 0.01
            _sigma_price_bs = _sigma_frac_bs * p
            _fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))
            _friction_dip = _fd_kappa * _sigma_price_bs
            _atr_dip = _compute_entry_dip(ad, fi, ci, action, p)
            # Floor: never use a dip smaller than 0.5×ATR
            _entry_dip = max(_friction_dip, 0.5 * _atr_dip)
            if _entry_dip <= 0.0:
                _entry_dip = p * 0.001

            tunnel_entry_p = (p - _entry_dip) if action == "BUY" \
                             else (p + _entry_dip)
            
            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
            sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist
            _tp_mult = float(getattr(CFG, 'TP_MULT', 1.5))
            tp1 = tunnel_entry_p + (sl_dist * _tp_mult) if action == "BUY" else tunnel_entry_p - (sl_dist * _tp_mult)
            

            # حظر الصفقات الهشة التي تكون تكلفتها أكبر من ربحها
            if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue

            # ══ [SR FILTER] SL must be protected by strong S/R ══
            _sr_sig = Signal(
                timestamp=ad.timestamps[ci], symbol=sym,
                price=tunnel_entry_p, score=float(ad.score[fi]),
                action=action, sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                dynamic_risk=CFG.MIN_RISK, T_info_val=T_info,
                dyn_sl_factor=sl_dist / tunnel_entry_p,
            )
            _sr_ok, _sr_reason = _sr_filter_check(_sr_sig, ad, ci)
            if not _sr_ok:
                log.debug(f"[SR] {sym} reject @ {ci}: {_sr_reason}")
                continue

            dynamic_risk = compute_geodesic_kelly(ad, fi, CFG)

            # ══ [MFAL] Extract signal features ══
            try:
                _accel_ratio_mfal = abs(geo_accel) / max(fric_val, 1e-9)
                _sl_dist_mfal = abs(tunnel_entry_p - sl)
                _rr_mfal = abs(tp1 - tunnel_entry_p) / max(_sl_dist_mfal, 1e-9)
                _mfal_x = _mfal_signal_features(
                    score=float(ad.score[fi]),
                    p_act=float(P_activation),
                    accel_ratio=float(_accel_ratio_mfal),
                    gauge=float(ad.gauge_force[fi]),
                    z_dev=float(_z_dev),
                    rr=float(_rr_mfal),
                )
            except Exception:
                _mfal_x = None

            # ══ [TRADE FILTER] ══
            _new_sig = Signal(
                timestamp=ad.timestamps[ci], symbol=sym,
                price=tunnel_entry_p,
                score=float(ad.score[fi]), action=action,
                sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                dynamic_risk=dynamic_risk, T_info_val=T_info,
                dyn_sl_factor=sl_dist / tunnel_entry_p,
                entry_ref_price=float(p),
                entry_base_dip=float(_entry_dip),
                mfal_x=_mfal_x,
                mfal_p_act=float(P_activation),
            )

            _FILTER_STATS['total_signals'] += 1

            _rej, _rej_reason = _trade_filter_check(
                _new_sig, ad, fi, ci
            )
            if _rej:
                _FILTER_STATS['rejected'] += 1
                continue

            _FILTER_STATS['kept'] += 1
            sigs.append(_new_sig)
            
    sigs.sort(key=lambda s: (s.timestamp, -s.score))
    return sigs

def deduplicate_signals(sigs):
    """
    TF-aware dedup: groups signals by (symbol, time bucket).
    The bucket is derived from CFG.TF_SECONDS so 1m/5m/1h all work correctly.
    """
    if not sigs:
        return sigs

#    # Determine bucket label from TF_SECONDS
#    tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
#    if tf_sec <= 60:
#        bucket = '1m'
#    elif tf_sec <= 300:
#        bucket = '5m'
#    elif tf_sec <= 900:
#        bucket = '15m'
#    elif tf_sec <= 3600:
#        bucket = '1h'
#    elif tf_sec <= 14400:
#        bucket = '4h'
#    else:
#        bucket = '1d'
    # Determine bucket label from TF_SECONDS.
    # [PANDAS-FIX] 'm' now means month-end in pandas ≥ 2.2.
    # Use 'min' for minutes. Hours/days unchanged.
    tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
    if tf_sec <= 60:
        bucket = '1min'
    elif tf_sec <= 300:
        bucket = '5min'
    elif tf_sec <= 900:
        bucket = '15min'
    elif tf_sec <= 1800:
        bucket = '30min'
    elif tf_sec <= 3600:
        bucket = '1h'
    elif tf_sec <= 14400:
        bucket = '4h'
    elif tf_sec <= 86400:
        bucket = '1D'
    else:
        bucket = '1D'

    groups = defaultdict(list)
    for s in sigs:
        key = (s.symbol, s.timestamp.floor(bucket))
        groups[key].append(s)

    result = []
    for _, grp in groups.items():
        result.append(max(grp, key=lambda s: (s.score, s.lam)))
    result.sort(key=lambda s: s.timestamp)
    return result



# ════════════════════════════════════════════════════════════════
# § 14  مصفوفة الارتباط
# ════════════════════════════════════════════════════════════════

def precompute_correlations(assets) -> Dict[Tuple[str,str], float]:
    syms = list(assets.keys()); cm = {}
    for i,s1 in enumerate(syms):
        for j,s2 in enumerate(syms):
            if i >= j: continue
            c1 = assets[s1].closes[-500:]
            c2 = assets[s2].closes[-500:]
            N  = min(len(c1), len(c2))
            if N < 20: corr = 0.5
            else:
                r1 = np.diff(np.log(np.maximum(c1[-N:],1e-12)))
                r2 = np.diff(np.log(np.maximum(c2[-N:],1e-12)))
                m  = min(len(r1),len(r2))
                corr = float(np.corrcoef(r1[-m:],r2[-m:])[0,1]) if m>10 else 0.5
            cm[(s1,s2)] = corr; cm[(s2,s1)] = corr
    return cm


def _backtest_entry_target(sig, ad) -> float:
    """
    Limit order target in backtest — mirrors Live's two pricing modes.

    PO_FIXED_PRICE=True (default):
        target = sig.price   (the tunnel / phase-matched price)

    PO_FIXED_PRICE=False (--no-fixed-price):
        target ≈ the live best bid/ask at placement time:
          BUY:  closes[sig.close_idx] × (1 − pen_frac)
          SELL: closes[sig.close_idx] × (1 + pen_frac)
        where pen_frac = PO_PENETRATION_BPS × 1e-4.

    Bar-level proxy for Live's live order-book fetch.
    """
    if getattr(CFG, 'PO_FIXED_PRICE', True):
        return float(sig.price)
    try:
        _close_at_sig = float(ad.closes[int(sig.close_idx)])
        _pen_frac = float(getattr(CFG, 'PO_PENETRATION_BPS', 1.0)) * 1e-4
        if sig.action == "BUY":
            return _close_at_sig * (1.0 - _pen_frac)
        else:
            return _close_at_sig * (1.0 + _pen_frac)
    except Exception:
        return float(sig.price)

# ════════════════════════════════════════════════════════════════
# § 15  محاكاة المحفظة (التعديلات ①②)
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# § 14.5  Precompute Realistic Entry Fills (Backtest Only)
# ════════════════════════════════════════════════════════════════

def precompute_entry_fills(assets, signals, max_wait_bars, pen_bps,
                           time_decay_enabled=False,
                           time_decay_bars=(5, 10, 15),
                           time_decay_mults=(0.7, 0.5, 0.3),
                           use_time_decay_price=False):
    """
    [UNIFIED] لكل إشارة:
      - Stage 1: حاول ملء Limit عند sig.price خلال UNIFIED_WAIT_BARS_1H.
      - Stage 2: إن فشل Stage 1، افحص شروط Stage 2 على كل شمعة تالية
                 حتى UNIFIED_MAX_AGE_BARS_1H. إن تحققت، ادخل بسعر السوق
                 وأعد بناء SL/TP.

    Returns
    -------
    dict {sig_i: tuple | None}
        ('S1', fill_ci, fill_px)                         — Stage 1
        ('S2', ci, px, sl_new, tp_new, sl_dist_new)      — Stage 2
        None                                              — skip
    """
    by_symbol = defaultdict(list)
    for i, s in enumerate(signals):
        by_symbol[s.symbol].append((i, s))

    pen_frac = pen_bps * 1e-4
    result = {}

    _unified = bool(getattr(CFG, 'UNIFIED_ENTRY_ENABLED', True))
    _stage1_bars = effective_bars(
        int(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))
    )
    _max_age_bars = effective_bars(
        int(getattr(CFG, 'UNIFIED_MAX_AGE_BARS_1H', 12))
    )

    for sym, sig_list in by_symbol.items():
        if sym not in assets:
            for idx, _ in sig_list:
                result[idx] = None
            continue
        ad = assets[sym]
        n_bars = len(ad.closes)

        for j, (sig_i, sig) in enumerate(sig_list):
            # ══ [SING-TIMING Layer 1] حالة الرنين لهذه الإشارة ══
            _sing_state = "DORMANT"
            _sing_rho = 0.0
            if getattr(CFG, 'SING_TIMING_ENABLED', False):
                try:
                    _sing_state, _sing_rho = _resonance_state_for_direction(
                        ad, int(sig.feat_idx), sig.action, CFG
                    )
                except Exception:
                    _sing_state, _sing_rho = "DORMANT", 0.0

            # DECAYING → رفض الإشارة كلياً (مطابق لـ Live)
            if _sing_state == "DECAYING":
                result[sig_i] = None
                continue

            # ══ [SING-TIMING Layer 3A] Funding Guard ══
            if getattr(CFG, 'SING_FUNDING_GUARD_ENABLED', False):
                try:
                    _ts = sig.timestamp
                    if _ts.tz is None:
                        _ts = _ts.tz_localize('UTC')
                    else:
                        _ts = _ts.tz_convert('UTC')
                    _minutes_now = int(_ts.hour) * 60 + int(_ts.minute)
                    _funding_hours = tuple(getattr(
                        CFG, 'SING_FUNDING_HOURS_UTC', (0, 8, 16)
                    ))
                    _window = int(getattr(
                        CFG, 'SING_FUNDING_GUARD_MINUTES', 30
                    ))
                    _skip_funding = False
                    for _fh in _funding_hours:
                        _fm = int(_fh) * 60
                        _delta = _fm - _minutes_now
                        if _delta < 0:
                            _delta += 24 * 60
                        if 0 <= _delta <= _window:
                            _skip_funding = True
                            break
                    if _skip_funding:
                        result[sig_i] = None
                        continue
                except Exception:
                    pass

            # ══ [SING-TIMING Layer 2] ACTIVE → marketable فوري ══
            if (_sing_state == "ACTIVE"
                    and getattr(CFG, 'SING_ACTIVE_MARKETABLE', False)):
                try:
                    _geom = _recompute_entry_geometry_at_market(
                        sig, ad, int(sig.close_idx), int(sig.feat_idx), CFG
                    )
                    if _geom is not None:
                        _pen_bps = float(getattr(
                            CFG, 'SING_ACTIVE_PENETRATION_BPS', 3.0
                        ))
                        _pen_frac = _pen_bps * 1e-4
                        _entry_px = float(_geom['entry_px'])
                        if sig.action == "BUY":
                            _mk_px = _entry_px * (1.0 + _pen_frac)
                        else:
                            _mk_px = _entry_px * (1.0 - _pen_frac)
                        result[sig_i] = (
                            'S2', int(sig.close_idx), float(_mk_px),
                            float(_geom['sl']), float(_geom['tp1']),
                            float(_geom['sl_dist_new'])
                        )
                        continue
                except Exception:
                    pass

            # ══ [SING-TIMING Layer 1] تعديل المهلة حسب الحالة ══
            _eff_stage1_bars = _stage1_bars
            if _sing_state == "EMERGING":
                _eff_stage1_bars = effective_bars(int(getattr(
                    CFG, 'SING_PENDING_WAIT_EMERGING', 2
                )))
            elif _sing_state == "ACTIVE":
                _eff_stage1_bars = effective_bars(int(getattr(
                    CFG, 'SING_PENDING_WAIT_ACTIVE', 1
                )))

            # Deadline = min(signal + max_wait, next signal)
            first_bar = sig.close_idx + 1
            stage1_last = first_bar + max(1, _eff_stage1_bars)
            stage2_last = first_bar + max(1, _max_age_bars)
            if j + 1 < len(sig_list):
                next_sig = sig_list[j + 1][1]
                stage1_last = min(stage1_last, next_sig.close_idx)
                stage2_last = min(stage2_last, next_sig.close_idx)
            stage1_last = min(stage1_last, n_bars)
            stage2_last = min(stage2_last, n_bars)

            if first_bar >= stage1_last and first_bar >= stage2_last:
                result[sig_i] = None
                continue

            target0 = _backtest_entry_target(sig, ad)
            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)

            # ── Stage 1 ──
            # [PARITY-FIX] Fill criterion now matches live exactly:
            #   Live places the order at `base × (1 ∓ pen)` and the exchange
            #   fills it when the market reaches that price.
            #   Backtest previously required an EXTRA penetration
            #   (need_low = target × (1 - pen)) → ~half the fills of live.
            #   Now: fill when market simply touches the target.
            stage1_fill = None
            for bar in range(first_bar, stage1_last):
                if (time_decay_enabled and ref_px > 0 and base_dip > 0):
                    bars_elapsed = bar - sig.close_idx
                    if bars_elapsed > int(time_decay_bars[2]):
                        mult = float(time_decay_mults[2])
                    elif bars_elapsed > int(time_decay_bars[1]):
                        mult = float(time_decay_mults[1])
                    elif bars_elapsed > int(time_decay_bars[0]):
                        mult = float(time_decay_mults[0])
                    else:
                        mult = 1.0
                    eff_dip = base_dip * mult
                    eff_target = (ref_px - eff_dip) if sig.action == "BUY" \
                                 else (ref_px + eff_dip)
                else:
                    eff_target = target0

                if sig.action == "BUY":
                    # Live semantics: order sits AT eff_target; fills when
                    # market price reaches it (low ≤ eff_target).
                    if ad.lows[bar] <= eff_target:
                        fill_px = eff_target if use_time_decay_price \
                                  else target0
                        stage1_fill = (bar, fill_px)
                        break
                else:
                    # Live semantics: order sits AT eff_target; fills when
                    # market price reaches it (high ≥ eff_target).
                    if ad.highs[bar] >= eff_target:
                        fill_px = eff_target if use_time_decay_price \
                                  else target0
                        stage1_fill = (bar, fill_px)
                        break

            if stage1_fill is not None:
                result[sig_i] = ('S1', stage1_fill[0], stage1_fill[1])
                continue

            # ── Stage 2 ──
            if not _unified:
                result[sig_i] = None
                continue

            stage2_entry = None
            for bar in range(max(first_bar, stage1_last), stage2_last):
                current_fi = bar - ad.feat_start
                if current_fi < 0 or current_fi >= len(ad.score):
                    continue
                ok, reason, p_cur = _check_unified_stage2(
                    sig, ad, bar, current_fi, CFG
                )
                if not ok:
                    continue
                geom = _recompute_entry_geometry_at_market(
                    sig, ad, bar, current_fi, CFG
                )
                if geom is None:
                    continue
                stage2_entry = (
                    'S2', bar, geom['entry_px'],
                    geom['sl'], geom['tp1'], geom['sl_dist_new']
                )
                break

            result[sig_i] = stage2_entry

    return result

# ════════════════════════════════════════════════════════════════
# § 14.55  Watch-Mode Backtest Fill Precompute (Parity with Live)
# ════════════════════════════════════════════════════════════════
#
# يحاكي في الـ backtest نفس ما يفعله monitor_watch_signals في الـ live:
#   1. WATCH: ينتظر أن يقترب السعر من tunnel_entry_p
#   2. TRIGGER: عندما يقترب + SL محمي ببنية، يحسب offset ديناميكي
#      ويضع "أمراً" عند tunnel ± offset
#   3. PENDING: ينتظر أن يلمس السعر الأمر (low ≤ order لـ BUY،
#      high ≥ order لـ SELL)، أو ينتهي timeout
#
# Returns: dict {sig_i: ('S1', fill_ci, fill_px) | None}
# ════════════════════════════════════════════════════════════════

def _precompute_watch_fills(assets, signals):
    """
    Backtest parity for WATCH_MODE_ENABLED live behavior.
    """
    by_symbol = defaultdict(list)
    for i, s in enumerate(signals):
        by_symbol[s.symbol].append((i, s))

    result = {}

    _prox_kappa = float(getattr(CFG, 'WATCH_PROX_KAPPA', 0.5))
    _phase1_timeout = max(3, effective_bars(
        int(getattr(CFG, 'WATCH_PHASE1_TIMEOUT_BARS_1H', 16))
    ))
    _max_age = max(3, effective_bars(
        int(getattr(CFG, 'UNIFIED_MAX_AGE_BARS_1H', 12))
    ))
    _s1_timeout = max(2, effective_bars(
        int(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))
    ))

    for sym, sig_list in by_symbol.items():
        if sym not in assets:
            for idx, _ in sig_list:
                result[idx] = None
            continue
        ad = assets[sym]
        n_bars = len(ad.closes)

        for j, (sig_i, sig) in enumerate(sig_list):
            # Next signal on same symbol caps this signal's window
            _next_ci = (sig_list[j+1][1].close_idx
                        if j+1 < len(sig_list) else n_bars)

            tunnel_p = float(sig.price)
            sl_orig = float(sig.sl)
            sl_dist_orig = abs(sl_orig - tunnel_p)
            if tunnel_p <= 0 or sl_dist_orig <= 0:
                result[sig_i] = None
                continue

            # ── Bar range for watching ──
            first_bar = int(sig.close_idx) + 1
            watch_last = min(first_bar + _phase1_timeout, _next_ci, n_bars)
            if watch_last <= first_bar:
                result[sig_i] = None
                continue

            triggered = False
            order_px = 0.0
            placed_bar = -1

            # ══════ WATCH PHASE ══════
            for bar in range(first_bar, watch_last):
                fi = bar - ad.feat_start
                if fi < 0 or fi >= len(ad.score):
                    continue

                # Physics collapse → drop
                sc_now = float(ad.score[fi])
                if sc_now < float(getattr(CFG, 'WATCH_PHASE1_ABORT_SCORE', 0.5)) * float(sig.score):
                    break

                try:
                    geo_a = float(ad.geodesic_accel[fi])
                    fric = float(ad.friction[fi]) + 1e-6
                    T_info = float(ad.T_info[fi])
                    P_act = float(np.exp(-fric / ((abs(geo_a) + 1e-9) * T_info)))
                except Exception:
                    P_act = 1.0
                if P_act < float(getattr(CFG, 'WATCH_PHASE1_ABORT_P_ACT', 0.30)):
                    break

                # σ_bar at this bar
                try:
                    sigma_bar = float(ad.E_therm[fi]) if fi < len(ad.E_therm) else 0.01
                    if not np.isfinite(sigma_bar) or sigma_bar <= 1e-6:
                        sigma_bar = 0.01
                except Exception:
                    sigma_bar = 0.01

                # ADV at this bar
                try:
                    adv_now = float(ad.adv_usd[bar]) if bar < len(ad.adv_usd) else 1e8
                except Exception:
                    adv_now = 1e8

                # Proximity (condition a)
                p_now = float(ad.closes[bar])
                if abs(p_now - tunnel_p) > _prox_kappa * sigma_bar * tunnel_p:
                    continue

                # Dynamic offset (no exchange → tick fallback = 0.1 bps)
                offset = _watch_compute_entry_offset(
                    tunnel_p=tunnel_p,
                    sigma_bar=sigma_bar,
                    adv_usd=adv_now,
                    exchange=None,
                    symbol=None,
                    qty=0.0,
                )

                if sig.action == "BUY":
                    expected_entry = tunnel_p + offset
                    effective_sl = expected_entry - sl_dist_orig
                else:
                    expected_entry = tunnel_p - offset
                    effective_sl = expected_entry + sl_dist_orig

                # Structure (condition b)
                if not _watch_sl_structure_ok(
                        ad, sig, effective_sl, tunnel_p, bar):
                    continue

                # ═══ TRIGGER ═══
                triggered = True
                order_px = float(expected_entry)
                placed_bar = bar
                break

            if not triggered:
                result[sig_i] = None
                continue

            # ══════ PENDING PHASE ══════
            fill_ci = -1
            fill_px = 0.0
            pending_last = min(placed_bar + _s1_timeout + 1, _next_ci, n_bars)

            # Check the trigger bar itself (price may have been touched
            # intrabar before we "placed" the order — pessimistic: we
            # require the NEXT bar to touch it).
            for bar in range(placed_bar + 1, pending_last):
                lo = float(ad.lows[bar])
                hi = float(ad.highs[bar])
                if sig.action == "BUY":
                    if lo <= order_px:
                        fill_ci = bar
                        fill_px = order_px
                        break
                else:
                    if hi >= order_px:
                        fill_ci = bar
                        fill_px = order_px
                        break

            if fill_ci < 0:
                # Check the trigger bar's own extremes as last resort
                # (order placed mid-bar; touch may have happened after)
                _tb_lo = float(ad.lows[placed_bar])
                _tb_hi = float(ad.highs[placed_bar])
                if sig.action == "BUY" and _tb_lo <= order_px:
                    fill_ci = placed_bar
                    fill_px = order_px
                elif sig.action == "SELL" and _tb_hi >= order_px:
                    fill_ci = placed_bar
                    fill_px = order_px

            if fill_ci < 0:
                result[sig_i] = None
                continue

            result[sig_i] = ('S1', int(fill_ci), float(fill_px))

    return result

def _ts_to_ci(ad, ts):
    idx = int(np.searchsorted(ad.timestamps.asi8, ts.value, side='right') - 1)
    return max(0, min(idx, len(ad.closes)-1))


def _get_risk_multiplier(drawdown):
    """دائرة الحماية المتدرجة (من v5)"""
    if drawdown >= CFG.DRAWDOWN_REDUCE_AT_70: return CFG.REDUCED_RISK_MULT_70
    if drawdown >= CFG.DRAWDOWN_REDUCE_AT_50: return CFG.REDUCED_RISK_MULT_50
    if drawdown >= CFG.DRAWDOWN_REDUCE_AT:    return CFG.REDUCED_RISK_MULT
    return 1.0

# ════════════════════════════════════════════════════════════════
# § 14.55  Dynamic Trailing Parameters
# ════════════════════════════════════════════════════════════════

def compute_trail_params(ad, entry_fi: int) -> Tuple[float, float]:
    """
    Returns (trail_dist_frac, trail_activate_frac) for a position
    based on the volatility proxy (E_therm) at entry time.

    Falls back to fixed CFG.TRAIL_DISTANCE / CFG.TRAIL_ACTIVATE_MFE if:
      - TRAIL_DYNAMIC is False
      - E_therm is missing or invalid
    """
    if not getattr(CFG, 'TRAIL_DYNAMIC', False):
        return float(CFG.TRAIL_DISTANCE), float(CFG.TRAIL_ACTIVATE_MFE)

    try:
        sigma = float(ad.E_therm[entry_fi]) if 0 <= entry_fi < len(ad.E_therm) else 0.0
        if not np.isfinite(sigma) or sigma <= 0:
            return float(CFG.TRAIL_DISTANCE), float(CFG.TRAIL_ACTIVATE_MFE)

        # ══ [TF-FIX] scale clip bounds by √TF_SCALE (σ ∝ √T) ══
        _sqrt_tf = float(np.sqrt(max(CFG.TF_SCALE, 1e-6)))
        min_d  = CFG.TRAIL_MIN_FRAC / _sqrt_tf
        max_d  = CFG.TRAIL_MAX_FRAC / _sqrt_tf
        min_a  = CFG.TRAIL_ACT_MIN_FRAC / _sqrt_tf
        max_a  = CFG.TRAIL_ACT_MAX_FRAC / _sqrt_tf

        trail_d = float(np.clip(
            CFG.TRAIL_KAPPA * sigma,
            min_d,
            max_d,
        ))
        trail_act = float(np.clip(
            CFG.TRAIL_ACT_KAPPA * sigma,
            min_a,
            max_a,
        ))
        # Activation must be strictly greater than trail distance
        if trail_act <= trail_d:
            trail_act = trail_d * 1.2
        return trail_d, trail_act
    except Exception:
        return float(CFG.TRAIL_DISTANCE), float(CFG.TRAIL_ACTIVATE_MFE)

def _advance(pos, ad, to_ci, partial_cb=None):
    """
    Walk bars from current_ci+1 to to_ci.

    SUB-BAR MODE (when ad.sub_highs is available):
        The entry bar is iterated from `pos.entry_sub_idx + 1` through
        the last sub-bar. Subsequent bars are iterated fully. This
        resolves the intrabar path ambiguity:
            - If SL touches before TP → real exit
            - If TP touches first         → real exit
            - Both within one sub-bar     → pessimistic (SL first)

    MAIN-BAR MODE (fallback):
        Legacy: skip entry bar entirely. SL is checked before TP
        (pessimistic).
    """
    sig = pos.signal
    trail_sl = pos.trail_sl
    start = pos.current_ci + 1
    end = min(to_ci, len(ad.closes) - 1)

    if start > end:
        return 0., "", -1

    pen_frac = CFG.FILL_PENETRATION_BPS * 1e-4 if CFG.FILL_APPLY_TO_EXITS else 0.0
    _use_sub = (ad.sub_highs is not None
                and ad.sub_lows is not None
                and ad.sub_per_main >= 2)

    def _check_sl_tp(high, low, close_px, fi):
        """Return ('SL'|'TP'|None, price). SL before TP when both hit."""
        if sig.action == "BUY":
            sl_trig = trail_sl * (1.0 - pen_frac)
            tp_trig = sig.tp1 * (1.0 + pen_frac)
            sl_hit = low <= sl_trig
            tp_hit = high >= tp_trig
        else:
            sl_trig = trail_sl * (1.0 + pen_frac)
            tp_trig = sig.tp1 * (1.0 - pen_frac)
            sl_hit = high >= sl_trig
            tp_hit = low <= tp_trig
        if sl_hit and tp_hit:
            return "SL", trail_sl      # pessimistic
        if sl_hit:
            return "SL", trail_sl
        if tp_hit:
            return "TP", sig.tp1
        return None, 0.0

    for cidx in range(start, end+1):
        p = ad.closes[cidx]
        fi = cidx - ad.feat_start

        # ── Determine sub-bar iteration range for this bar ──
        if _use_sub and cidx == pos.entry_ci:
            j_start = int(pos.entry_sub_idx) + 1
            j_end = ad.sub_per_main
        elif _use_sub:
            j_start, j_end = 0, ad.sub_per_main
        else:
            j_start, j_end = 0, 0  # main-bar mode

        # ── Process this bar ──
        if _use_sub:
            # Sub-bar iteration
            for j in range(j_start, j_end):
                s_high = ad.sub_highs[cidx, j]
                s_low = ad.sub_lows[cidx, j]
                if not np.isfinite(s_high) or not np.isfinite(s_low):
                    continue

                # MFE update from sub-bar extremes
                if sig.action == "BUY":
                    mfe_cand = (s_high - pos.entry_px) / pos.entry_px
                else:
                    mfe_cand = (pos.entry_px - s_low) / pos.entry_px
                if mfe_cand > pos.mfe_frac:
                    pos.mfe_frac = mfe_cand

                # ══ [BREAKEVEN-SL] نقل SL إلى نقطة الدخول عند +1R ══
                # الهدف: حماية الصفقات التي وصلت MFE ≥ 1R من الانعكاس الكامل.
                # يعمل فقط إذا لم يُفعّل Trailing.
                if not getattr(CFG, 'TRAIL_ENABLED', True) and \
                        getattr(CFG, 'BREAKEVEN_ENABLED', True):
                    _sl_frac_init = (pos.sl_dist_initial / pos.entry_px
                                     if pos.entry_px > 0 and pos.sl_dist_initial > 0
                                     else 0.01)
                    _be_trigger_r = float(getattr(CFG, 'BREAKEVEN_AT_R', 1.0))
                    _be_trigger_frac = _sl_frac_init * _be_trigger_r
                    if pos.mfe_frac >= _be_trigger_frac:
                        if sig.action == "BUY":
                            if pos.entry_px > trail_sl:
                                trail_sl = pos.entry_px
                        else:
                            if pos.entry_px < trail_sl:
                                trail_sl = pos.entry_px

                # Legacy trailing (uses sub-bar high/low as peak candidate)
                _td = pos.trail_dist_frac if pos.trail_dist_frac > 0 else CFG.TRAIL_DISTANCE
                _ta = pos.trail_activate_frac if pos.trail_activate_frac > 0 else CFG.TRAIL_ACTIVATE_MFE
                # ══ [FIX 1] Activation tied to R-multiple, not fixed MFE ══
                _sl_frac_init = (pos.sl_dist_initial / pos.entry_px
                                 if pos.entry_px > 0 and pos.sl_dist_initial > 0
                                 else 0.01)
                _act_at_r = float(getattr(CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
                _ta_eff = _sl_frac_init * _act_at_r
                if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:
                    if sig.action == "BUY":
                        peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                        if s_high > peak:
                            peak = s_high; pos.peak_price = peak
                        new_sl = peak * (1.0 - _td)
                        if new_sl > trail_sl * (1.0 + CFG.TRAIL_MIN_STEP):
                            trail_sl = new_sl
                    else:
                        peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                        if s_low < peak or peak == 0:
                            peak = s_low; pos.peak_price = peak
                        new_sl = peak * (1.0 + _td)
                        if new_sl < trail_sl * (1.0 - CFG.TRAIL_MIN_STEP):
                            trail_sl = new_sl

                # ══ [FIX 4] Partial TP trigger ══
                if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                        and not getattr(pos, 'partial_taken', False)
                        and partial_cb is not None
                        and pos.sl_dist_initial > 0):
                    _ptr = float(getattr(CFG, 'PARTIAL_TP_R', 1.0))
                    if sig.action == "BUY":
                        _trig = pos.entry_px + pos.sl_dist_initial * _ptr
                        if s_high >= _trig:
                            pos.partial_taken = True
                            partial_cb(pos, _trig, cidx)
                    else:
                        _trig = pos.entry_px - pos.sl_dist_initial * _ptr
                        if s_low <= _trig:
                            pos.partial_taken = True
                            partial_cb(pos, _trig, cidx)

                # SL / TP check on sub-bar
                res, px = _check_sl_tp(s_high, s_low, p, fi)
                if res == "SL":
                    pos.trail_sl = trail_sl; pos.current_ci = cidx
                    return px, "Emergency SL", cidx
                if res == "TP":
                    pos.trail_sl = trail_sl; pos.current_ci = cidx
                    return px, "Hard TP", cidx

        else:
            # Main-bar fallback — skip entry bar entirely
            if cidx == pos.entry_ci:
                continue
            high = ad.highs[cidx]
            low  = ad.lows[cidx]

            if sig.action == "BUY":
                mfe_cand = (high - pos.entry_px) / pos.entry_px
            else:
                mfe_cand = (pos.entry_px - low) / pos.entry_px
            if mfe_cand > pos.mfe_frac:
                pos.mfe_frac = mfe_cand

            _td = pos.trail_dist_frac if pos.trail_dist_frac > 0 else CFG.TRAIL_DISTANCE
            _ta = pos.trail_activate_frac if pos.trail_activate_frac > 0 else CFG.TRAIL_ACTIVATE_MFE
            # ══ [FIX 1] Activation tied to R-multiple, not fixed MFE ══
            _sl_frac_init = (pos.sl_dist_initial / pos.entry_px
                             if pos.entry_px > 0 and pos.sl_dist_initial > 0
                             else 0.01)
            _act_at_r = float(getattr(CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
            _ta_eff = _sl_frac_init * _act_at_r
            if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:
                if sig.action == "BUY":
                    peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                    if high > peak:
                        peak = high; pos.peak_price = peak
                    new_sl = peak * (1.0 - _td)
                    if new_sl > trail_sl * (1.0 + CFG.TRAIL_MIN_STEP):
                        trail_sl = new_sl
                else:
                    peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                    if low < peak or peak == 0:
                        peak = low; pos.peak_price = peak
                    new_sl = peak * (1.0 + _td)
                    if new_sl < trail_sl * (1.0 - CFG.TRAIL_MIN_STEP):
                        trail_sl = new_sl

            res, px = _check_sl_tp(high, low, p, fi)
            if res == "SL":
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return px, "Emergency SL", cidx
            if res == "TP":
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return px, "Hard TP", cidx

        # ── Physics-based exits (close-only, per main bar) ──
        is_apex, apex_rsn = False, ""
        if getattr(CFG, 'APEX_ENABLED', True):
            is_apex, apex_rsn = check_thermodynamic_apex(
                sig.action, pos.entry_px, p, ad, fi
            )
        if is_apex:
            pos.trail_sl = trail_sl; pos.current_ci = cidx
            return p, apex_rsn, cidx

        if 0 < fi < len(ad.V) and cidx > 0:
            V_curr = ad.V[fi]
            V_prev = ad.V[fi - 1] if fi > 0 else V_curr
            div_t = (V_curr - V_prev) / (V_prev + 1e-12)
            dH_curr = ad.dH[fi] if fi < len(ad.dH) else 0.
            if div_t > CFG.TOPO_DIV_THRESHOLD and dH_curr > 0:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return p, f"Topo-Div({div_t:.3f})", cidx

        # 3. MaxHold (close-based)
        # ══ [TF-FIX] scale bar-count to preserve real-time duration ══
        if cidx - pos.entry_ci > effective_bars(CFG.MAX_HOLD_BARS):
            pos.trail_sl = trail_sl; pos.current_ci = cidx
            return p, "MaxHold", cidx

        # ══ [FIX 3] Time-based kill — if flat after N bars, cut it ══
        if getattr(CFG, 'TIME_KILL_ENABLED', False):
            _tk_bars = effective_bars(int(getattr(CFG, 'TIME_KILL_BARS', 10)))
            if (cidx - pos.entry_ci) >= _tk_bars:
                # Compute current R-multiple
                if pos.sl_dist_initial > 0:
                    if sig.action == "BUY":
                        _pnl_frac = (p - pos.entry_px) / pos.entry_px
                    else:
                        _pnl_frac = (pos.entry_px - p) / pos.entry_px
                    _sl_frac0 = pos.sl_dist_initial / pos.entry_px
                    _r_now = _pnl_frac / _sl_frac0 if _sl_frac0 > 0 else 0.0
                    _min_r = float(getattr(CFG, 'TIME_KILL_MIN_R', 0.5))
                    if _r_now < _min_r:
                        pos.trail_sl = trail_sl; pos.current_ci = cidx
                        return p, f"TimeKill({_r_now:.2f}R)", cidx

    pos.trail_sl = trail_sl
    pos.current_ci = max(end, pos.current_ci)
    return 0., "", -1

# ════════════════════════════════════════════════════════════════
# § 14.35  Opposite-Signal Adaptive TP
# ════════════════════════════════════════════════════════════════
#
# الفكرة: عندما تظهر إشارة معاكسة على نفس الأصل، نستخدم موقع
# tunnel_entry_p الخاص بها كهدف ربح جديد للمركز الحالي.
#
# القيود:
#   1. الإشارة المعاكسة "قوية" (score ≥ mult × score_entry)
#   2. حديثة (age ≤ max_age_bars)
#   3. TP أحادي الاتجاه (monotonic) — لا يعود للخلف
#   4. لا ينزل تحت حد ربح أدنى (min_profit_R)
#   5. لا يعود بتغيير تافه (min_delta_R)
#   6. لا يتخطى trigger partial TP (إن لم يُفعَّل بعد)
# ════════════════════════════════════════════════════════════════

def _opp_tp_decide(action_pos: str, entry: float, sl_dist0: float,
                   tp_old: float, partial_taken: bool,
                   entry_ci: int,
                   sig_opp, current_ci: int):
    """
    Pure decision function. Returns (new_tp: float | None, reason: str).
    None → no change.
    """
    if not getattr(CFG, 'OPP_TP_ENABLED', False):
        return None, "disabled"

    if action_pos == sig_opp.action:
        return None, "same_direction"

    sc_o = float(getattr(sig_opp, 'score', 0.0) or 0.0)
    age = current_ci - int(getattr(sig_opp, 'close_idx', current_ci))
    if age < 0 or age > int(CFG.OPP_TP_MAX_AGE_BARS):
        return None, f"stale_opp(age={age})"

    if entry <= 0 or sl_dist0 <= 0:
        return None, "invalid_geom"

    p_opp = float(getattr(sig_opp, 'price', 0.0) or 0.0)
    if p_opp <= 0:
        return None, "invalid_opp_price"

    min_gain = float(CFG.OPP_TP_MIN_PROFIT_R) * sl_dist0
    min_delta = float(CFG.OPP_TP_MIN_DELTA_R) * sl_dist0

    if action_pos == "BUY":
        tp_new = min(tp_old, p_opp)
        if tp_new < entry + min_gain:
            return None, f"below_min_gain({tp_new:.6f}<{entry+min_gain:.6f})"
        if tp_old - tp_new < min_delta:
            return None, f"delta_too_small({tp_old-tp_new:.6f}<{min_delta:.6f})"
        if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                and not partial_taken
                and getattr(CFG, 'OPP_TP_RESPECT_PARTIAL', True)):
            _p_trig = entry + float(CFG.PARTIAL_TP_R) * sl_dist0
            if tp_new <= _p_trig:
                return None, f"would_skip_partial(trig={_p_trig:.6f})"
    else:  # SELL
        tp_new = max(tp_old, p_opp)
        if tp_new > entry - min_gain:
            return None, f"below_min_gain({tp_new:.6f}>{entry-min_gain:.6f})"
        if tp_new - tp_old < min_delta:
            return None, f"delta_too_small({tp_new-tp_old:.6f}<{min_delta:.6f})"
        if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                and not partial_taken
                and getattr(CFG, 'OPP_TP_RESPECT_PARTIAL', True)):
            _p_trig = entry - float(CFG.PARTIAL_TP_R) * sl_dist0
            if tp_new >= _p_trig:
                return None, f"would_skip_partial(trig={_p_trig:.6f})"

    return float(tp_new), "ok"


def _maybe_adapt_tp_backtest(pos, sig_opp, ad, current_ci: int) -> bool:
    """
    Backtest wrapper for OpenPosition dataclass.
    Modifies pos.signal.tp1 in place.
    """
    try:
        if getattr(pos, 'signal', None) is sig_opp:
            return False
        if int(current_ci) <= int(pos.entry_ci):
            return False

        sc_e = float(pos.signal.score)
        sc_o = float(sig_opp.score)
        if sc_e > 0 and sc_o < float(CFG.OPP_TP_SCORE_MULT) * sc_e:
            return False

        tp_new, reason = _opp_tp_decide(
            action_pos=str(pos.signal.action),
            entry=float(pos.entry_px),
            sl_dist0=float(pos.sl_dist_initial),
            tp_old=float(pos.signal.tp1),
            partial_taken=bool(getattr(pos, 'partial_taken', False)),
            entry_ci=int(pos.entry_ci),
            sig_opp=sig_opp,
            current_ci=int(current_ci),
        )
        if tp_new is None:
            return False

        tp_old = float(pos.signal.tp1)
        pos.signal.tp1 = float(tp_new)
        log.info(f"[OppTP] {pos.symbol} {pos.signal.action} "
                 f"TP {tp_old:.6f} → {tp_new:.6f} "
                 f"(opp score={float(sig_opp.score):.2f} vs {sc_e:.2f})")
        return True
    except Exception as e:
        log.debug(f"[OppTP] backtest adapter failed: {e}")
        return False

# ════════════════════════════════════════════════════════════════
# § 14.7  Portfolio Risk Budget
# ════════════════════════════════════════════════════════════════

def compute_signal_strength(sig, cfg) -> float:
    """
    Map sig.score to a strength in [0, 1].
    Both MR and legacy modes normalized to same scale.
    """
    try:
        score = float(sig.score)
    except Exception:
        return 0.5

    if getattr(cfg, 'MEANREV_MODE', False):
        lo = float(getattr(cfg, 'MR_K', 2.5))
        hi = lo * 2.0
    else:
        lo = float(cfg.MIN_SCORE)
        hi = lo * 2.5

    return float(np.clip((score - lo) / max(hi - lo, 1e-9), 0.0, 1.0))


def compute_portfolio_risk_frac(sig, capital, open_pos_dict, cfg) -> float:
    """
    Coordinated portfolio-aware risk fraction for a new trade.
    Returns fraction of (capital - CAPITAL_FLOOR) to risk.

    Returns 0.0 if no budget available (caller should skip signal).
    """
    if not CFG.BUDGET_ENABLED:
        # Fallback to legacy per-trade risk
        return float(np.clip(sig.dynamic_risk, cfg.MIN_RISK, cfg.MAX_RISK))

    # ── Layer 1: Portfolio heat budget ──
    heat_max = float(cfg.PORTFOLIO_HEAT_MAX)
    heat_used = 0.0
    for pos in open_pos_dict.values():
        try:
            heat_used += float(pos.signal.dynamic_risk)
        except Exception as e:
            log.debug(f"[Budget] heat accumulation failed: {e}")
    heat_available = max(0.0, heat_max - heat_used)
    if heat_available <= 1e-9:
        return 0.0

    # ── Layer 2: Fair share per slot ──
    n_slots = max(int(cfg.MAX_CONCURRENT_ASSETS), 1)
    base_per_slot = heat_max / n_slots

    # ── Layer 3: Weight by signal strength ──
    strength = compute_signal_strength(sig, cfg)
    s_min = float(cfg.RISK_STRENGTH_MIN)
    s_max = float(cfg.RISK_STRENGTH_MAX)
    strength_factor = s_min + (s_max - s_min) * strength
    risk_frac = base_per_slot * strength_factor

    # ── Layer 4: Caps ──
    risk_frac = min(risk_frac, heat_available)
    risk_frac = min(risk_frac, float(cfg.MAX_RISK_PER_TRADE))

    if risk_frac < float(cfg.MIN_RISK_PER_TRADE):
        return 0.0

    return float(risk_frac)

# ════════════════════════════════════════════════════════════════
# § 14.6  Notional Cap (Anti-Compounding)
# ════════════════════════════════════════════════════════════════

def cap_notional(qty: float, price: float) -> float:
    """
    Hard cap on position notional = qty × price.
    Prevents the exponential compounding blowup in backtests.
    """
    if price <= 0 or qty <= 0:
        return qty
    notional = qty * price
    cap = float(CFG.MAX_ABS_NOTIONAL)
    if cap > 0 and notional > cap:
        return cap / price
    return qty

def simulate_portfolio(signals, assets, corr_matrix, mode="backtest"):
    """
    محاكاة المحفظة متعددة المراكز (Backtest Engine):
    - تطبق قانون القوة (Power-Law Scaling) لتعديل المخاطرة ديناميكياً.
    - تقضي على انحياز النظر للمستقبل (Causality Enforcement) بالدخول اللحظي بسعر النفق.
    - تحاكي الوقف والهدف بناءً على حركات ذيول الشموع اللحظية (High/Low).
    """
    capital  = CFG.INITIAL_CAPITAL
    peak_cap = capital
    equity   = [capital]
    trades_out: List[Trade] = []
    open_pos: Dict[str, OpenPosition] = {}
    # ══ [RE-ENTRY COOLDOWN] Track last exit bar per symbol ══
    last_exit_ci: Dict[str, int] = {}
    # ══ [BACKTEST REALISM] Precompute which entries actually fill ══
    # When SIMULATE_LIVE_FAITHFULLY, use the LIVE entry timeout
    # (PO_MAX_WAIT_S seconds converted to bars) instead of the
    # generous backtest window (25 bars).
    _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
    _sim_live = bool(getattr(CFG, 'SIMULATE_LIVE_FAITHFULLY', False))

    if _sim_live:
        _live_wait_cap_s = float(getattr(CFG, 'PO_MAX_WAIT_S', 0) or 0)
        if _live_wait_cap_s > 0:
            _bars_from_seconds = max(1, int(np.ceil(_live_wait_cap_s / _tf_sec)))
        else:
            _bars_from_seconds = effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS)
        _effective_wait_bars = min(
            effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS),
            _bars_from_seconds,
        )
        _wait_label = (f"live={_live_wait_cap_s:.0f}s "
                       f"→ {_effective_wait_bars} bars")
    else:
        _effective_wait_bars = effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS)
        _wait_label = (f"{CFG.FILL_ENTRY_MAX_WAIT_BARS} bars × "
                       f"scale {CFG.TF_SCALE:.2f} = {_effective_wait_bars}")

    # Time-decay: only applied if live-mode is on
    _td_enabled = _sim_live and bool(getattr(CFG, 'ENTRY_TIME_DECAY', False))

    # ══ [PARITY] Watch mode → use _precompute_watch_fills ══
    if (not WATCH_REMOVED) and getattr(CFG, 'WATCH_MODE_ENABLED', False):
        fill_map = _precompute_watch_fills(assets, signals)
        log.info("  [Backtest Watch] using watch-then-trigger parity "
                 "logic (proximity + structure + dynamic offset)")
    else:
        fill_map = precompute_entry_fills(
            assets, signals,
            max_wait_bars=_effective_wait_bars,
            pen_bps=CFG.FILL_PENETRATION_BPS,
            time_decay_enabled=_td_enabled,
            time_decay_bars=(CFG.ENTRY_TIME_DECAY_BARS_1,
                             CFG.ENTRY_TIME_DECAY_BARS_2,
                             CFG.ENTRY_TIME_DECAY_BARS_3),
            time_decay_mults=(CFG.ENTRY_TIME_DECAY_MULT_1,
                              CFG.ENTRY_TIME_DECAY_MULT_2,
                              CFG.ENTRY_TIME_DECAY_MULT_3),
            use_time_decay_price=_td_enabled,
        )
    n_total_sigs = len(signals)
    n_would_fill = sum(1 for v in fill_map.values() if v is not None)
    log.info(f"  [Backtest Realism] Entry fills: "
             f"{n_would_fill:,}/{n_total_sigs:,} "
             f"({100*n_would_fill/max(n_total_sigs,1):.1f}%) "
             f"[pen={CFG.FILL_PENETRATION_BPS}bps, wait={_wait_label}]")

    def _close(pos, ad, exit_px, exit_rsn, exit_ci):
        nonlocal capital, peak_cap
        sig         = pos.signal
        exit_act    = "SELL" if sig.action=="BUY" else "BUY"
        adv_here    = ad.adv_usd[min(exit_ci, len(ad.adv_usd)-1)]

        # ══ [SLIPPAGE] taker exits suffer adverse slippage ══
        _is_taker = _exit_is_taker(exit_rsn)
        exit_eff  = apply_slippage(exit_px, pos.pos_size, adv_here,
                                    exit_act, mode, is_taker=_is_taker)
        slip_x    = abs(exit_eff-exit_px)*pos.pos_size

        if sig.action=="BUY":
            gross = (exit_eff - pos.entry_px) * pos.pos_size
        else:
            gross = (pos.entry_px - exit_eff) * pos.pos_size

        # ══ [FEES] entry is maker (GTX); exit is maker or taker ══
        entry_fee = pos.pos_size * pos.entry_px * CFG.MAKER_FEE
        _exit_fee_rate = CFG.TAKER_FEE if _is_taker else CFG.MAKER_FEE
        exit_fee  = pos.pos_size * exit_eff * _exit_fee_rate
        fee       = entry_fee + exit_fee

        # Funding (unchanged)
        hold_bars = exit_ci - pos.entry_ci
        funding_payments = max(0, hold_bars) // CFG.FUNDING_INTERVAL_BARS
        funding_cost = pos.pos_size * pos.entry_px * CFG.FUNDING_RATE_COST * funding_payments

        # [P1.1] partial_pnl already booked into capital in _partial_tp
        # → exclude it from the capital delta
        _partial = float(getattr(pos, 'partial_pnl', 0.0))
        net = gross - fee - funding_cost + _partial   # trade-level PnL (unchanged)
        cap0 = pos.entry_cap
        capital = max(capital + (net - _partial), 0.)
        peak_cap= max(peak_cap, capital)
        equity.append(capital)

        lr = float(np.log((cap0+net)/cap0)) if cap0>0 else 0.
        lw = (pos.pos_size*pos.entry_px) > (adv_here*24*CFG.MAX_ADV_FRACTION)

        trades_out.append(Trade(
            symbol=sig.symbol, action=sig.action,
            entry_price=pos.entry_px, exit_price=exit_eff,
            pos_size=pos.pos_size, gross_pnl=gross, fee=fee+slip_x,
            net_pnl=net, capital_after=capital, log_return=lr,
            entry_time=sig.timestamp, exit_reason=exit_rsn,
            score=sig.score, lam=sig.lam, liq_warn=lw,
            slippage_paid=pos.slip_paid+slip_x,
            entry_optimized=pos.opt_entry, tri_at_entry=pos.tri_entry,
            dynamic_risk_used=sig.dynamic_risk,
            T_info_at_entry=sig.T_info_val,
            mfe_frac=pos.mfe_frac
        ))

        # ══ [TradeLog] تسجيل الصفقة ══
        try:
            _trade_log_from_backtest(
                pos, ad, exit_eff, exit_rsn, exit_ci,
                pos.entry_cap, capital,
                net_pnl=net, log_return=lr
            )
        except Exception as _tle:
            log.debug(f"[TradeLog] backtest hook failed: {_tle}")

        # ══ [UNIFIED-BT] Record trade outcome ══
        if _UNIFIED_ENABLED:
            try:
                _sl_d0_u = float(getattr(pos, 'sl_dist_initial', 0) or 0)
                _entry_px_u = float(pos.entry_px)
                _exit_px_u = float(exit_eff)
                if _sl_d0_u > 0 and _entry_px_u > 0:
                    if sig.action == "BUY":
                        _pnl_move_u = _exit_px_u - _entry_px_u
                    else:
                        _pnl_move_u = _entry_px_u - _exit_px_u
                    _R_u = _pnl_move_u / _sl_d0_u
                    _unified_record_trade(sig, ad, float(_R_u), _R_u > 0.5)
            except Exception as _re:
                log.debug(f"[Unified-BT] record failed: {_re}")

    # ══ [FIX 4] Partial TP callback ══
    def _partial_tp(pos, px, ci):
        """Record a partial take-profit and reduce the position size."""
        nonlocal capital, peak_cap
        sig = pos.signal
        _pct = float(getattr(CFG, 'PARTIAL_TP_PCT', 0.5))
        _close_qty = pos.pos_size * _pct
        if _close_qty <= 0:
            return
        adv_here = ad_here = pos.entry_cap  # placeholder — see below
        # Compute gross PnL for the partial close
        if sig.action == "BUY":
            _gross = (px - pos.entry_px) * _close_qty
        else:
            _gross = (pos.entry_px - px) * _close_qty
        _entry_fee = _close_qty * pos.entry_px * CFG.MAKER_FEE
        _exit_fee  = _close_qty * px * CFG.TAKER_FEE
        _fee = _entry_fee + _exit_fee
        _net = _gross - _fee
        capital += _net
        peak_cap = max(peak_cap, capital)
        equity.append(capital)
        pos.partial_pnl = pos.partial_pnl + _net
        pos.pos_size -= _close_qty
        log.debug(f"[PartialTP] {sig.symbol} closed {_pct*100:.0f}% "
                  f"@ {px:.6f}  net=${_net:+.4f}  remaining={pos.pos_size:.6f}")

    for sig_i, sig in enumerate(signals):
        # حاجز أمان مطلق: يستحيل بدء تداول جديد إذا اقترب الجسيم من عتبة الفناء (5.1$)
        if capital <= CFG.CAPITAL_FLOOR + 0.1:
            break

        # 1. تحديث ومراقبة الفضاء للمراكز المفتوحة (التقدم في الزمكان)
        to_close = []
        for sym, pos in open_pos.items():
            ad   = assets[sym]
            toci = _ts_to_ci(ad, sig.timestamp)
            ep, er, ec = _advance(pos, ad, toci, partial_cb=_partial_tp)
            if ep > 0:
                _close(pos, ad, ep, er, ec)
                to_close.append(sym)
                # ══ [RE-ENTRY COOLDOWN] Record exit bar ══
                last_exit_ci[sym] = int(ec)
        for sym in to_close:
            del open_pos[sym]

        # ══ [OppTP] نقل TP لمركز مفتوح عند ظهور إشارة معاكسة ══
        if getattr(CFG, 'OPP_TP_ENABLED', False) and sig.symbol in open_pos:
            _maybe_adapt_tp_backtest(
                open_pos[sig.symbol], sig, assets[sig.symbol],
                int(sig.close_idx)
            )

        sym = sig.symbol
        if sym in open_pos: continue
        if capital <= 0: continue

        # ══ [RE-ENTRY COOLDOWN] Block re-entry too soon after exit ══
        if CFG.REENTRY_COOLDOWN_ENABLED:
            _last = last_exit_ci.get(sym, -10**9)
            if (sig.close_idx - _last) < CFG.REENTRY_COOLDOWN_BARS:
                log.debug(f"[Cooldown] {sym} blocked "
                          f"(exit@{_last}, sig@{sig.close_idx}, "
                          f"need≥{CFG.REENTRY_COOLDOWN_BARS})")
                continue

        # تراجع المحفظة (Drawdown Factor)
        drawdown = (peak_cap - capital) / (peak_cap + 1e-12)
        dd_mult  = _get_risk_multiplier(drawdown)

        if len(open_pos) >= CFG.MAX_CONCURRENT_ASSETS: continue

        # تجنب التداخل الطيفي (منع الصفقات المترابطة إحصائياً)
        too_corr = any(
            abs(corr_matrix.get((sym, s), 0.)) > CFG.CORRELATION_THRESHOLD
            for s in open_pos
        )
        if too_corr: continue

        ad = assets[sym]

        # ══ [UNIFIED ENTRY] Look up Stage 1 or Stage 2 ══
        fill_info = fill_map.get(sig_i)
        if fill_info is None:
            continue

        _is_stage2 = False
        _stage2_sl = _stage2_tp = _stage2_sl_dist = None

        if len(fill_info) >= 2 and isinstance(fill_info[0], str):
            if fill_info[0] == 'S1':
                _, opt_ci, opt_px = fill_info
            elif fill_info[0] == 'S2':
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist \
                    = fill_info
                _is_stage2 = True
            else:
                continue
        else:
            # توافق مع الصيغة القديمة
            opt_ci, opt_px = fill_info

        opt_ci = int(opt_ci)
        opt_px = float(opt_px)
        opt_entry = False

        # ══ [STAGE 2] أعد كتابة SL/TP على الإشارة قبل أي حساب ══
        if _is_stage2:
            _old_sl = sig.sl
            _old_tp = sig.tp1
            sig.sl = float(_stage2_sl)
            sig.tp1 = float(_stage2_tp)
            log.debug(
                f"[Unified-S2] {sym} entry@{opt_px:.6f} "
                f"old_sl={_old_sl:.6f}→new_sl={sig.sl:.6f} "
                f"old_tp={_old_tp:.6f}→new_tp={sig.tp1:.6f}"
            )

        # ══ [SUB-BARS] Find the sub-bar within the entry bar where
        # the limit was first touched. This is used by _advance to
        # start SL/TP checks AFTER the fill (not before).
        opt_sub_idx = 0
        if (ad.sub_highs is not None and ad.sub_lows is not None
                and ad.sub_per_main >= 2
                and 0 <= opt_ci < ad.sub_highs.shape[0]):
            _pen_frac_sb = CFG.FILL_PENETRATION_BPS * 1e-4
            if sig.action == "BUY":
                _need_low = opt_px * (1.0 - _pen_frac_sb)
                _row = ad.sub_lows[opt_ci]
                _idx = np.where(_row <= _need_low)[0]
                if len(_idx) > 0:
                    opt_sub_idx = int(_idx[0])
            else:
                _need_high = opt_px * (1.0 + _pen_frac_sb)
                _row = ad.sub_highs[opt_ci]
                _idx = np.where(_row >= _need_high)[0]
                if len(_idx) > 0:
                    opt_sub_idx = int(_idx[0])

        # ══ [SL/TP SETUP — works for both fixed and no-fix] ══
        # Design distances from the original signal (preserves R:R intent).
        _design_sl_dist = abs(sig.price - sig.sl)
        _design_tp_dist = abs(sig.tp1 - sig.price)
        if _design_sl_dist <= 1e-12:
            continue

        # Clip SL to max_sl_frac × opt_px (entry-based cap)
        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        if _design_sl_dist > opt_px * _max_sl_frac:
            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)
            _design_sl_dist = opt_px * _max_sl_frac
            _design_tp_dist = _design_sl_dist * _rr

        # ══ [CRITICAL FIX] Rebuild sig.sl / sig.tp1 from opt_px ══
        # This is what the LIVE code already does in
        # _promote_pending_to_position. Without this, when
        # PO_FIXED_PRICE=False and entry ≠ sig.price, TP ends up
        # BELOW entry (for BUY) → "Hard TP" exits are actually losses.
        if sig.action == "BUY":
            sig.sl  = opt_px - _design_sl_dist
            sig.tp1 = opt_px + _design_tp_dist
        else:
            sig.sl  = opt_px + _design_sl_dist
            sig.tp1 = opt_px - _design_tp_dist

        sl_distance = _design_sl_dist
        tp_distance = _design_tp_dist

        if sig.action == "BUY":
            sl_h = opt_px - sl_distance
        else:
            sl_h = opt_px + sl_distance

        if sig.action == "BUY":
            sl_h = opt_px - sl_distance
        else:
            sl_h = opt_px + sl_distance
            
        delta = abs(opt_px - sl_h)
        if delta < 1e-8: continue

        # ══ [UNIFIED-BT] Compute decision ══
        _u_decision = None
        if _UNIFIED_ENABLED:
            try:
                # Convert OpenPosition objects to dict for unified engine
                _bt_pos_dict = {}
                for _bsym, _bpos in open_pos.items():
                    try:
                        _bsig = getattr(_bpos, 'signal', None)
                        _bdyn = float(getattr(_bsig, 'dynamic_risk', 0.01)) if _bsig else 0.01
                        _bt_pos_dict[_bsym] = {
                            'entry': float(getattr(_bpos, 'entry_px', 0)),
                            'qty': float(getattr(_bpos, 'pos_size', 0)),
                            'leverage': int(CFG.LEVERAGE_BASE or 1),
                            'dyn_risk': _bdyn,
                        }
                    except Exception:
                        pass
                _u_decision = compute_unified_decision(
                    sym=sym, sig=sig, capital=capital,
                    peak=peak_cap,
                    open_pos_live=_bt_pos_dict,
                    corr_cache=corr_matrix,
                    exchange=None,
                    ad=ad, cfg=CFG,
                )
            except Exception as _ue:
                log.warning(f"[Unified-BT] {sym} error: {_ue}")
                _u_decision = None
            if _u_decision is not None and not _u_decision["accept"]:
                log.debug(f"[Unified-BT] {sym} rejected: {_u_decision['reason']}")
                continue

        # ══ [PORTFOLIO RISK BUDGET] ══
        # Portfolio-coordinated sizing: heat budget + fair share + strength weighting
        free_ratio = max(0.0, (capital - CFG.CAPITAL_FLOOR) / capital)
        power_law_scale = np.sqrt(free_ratio)

        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)
        if risk_frac <= 0.0:
            # [UNIFIED-BT] override risk_frac if unified accepts
            if _u_decision is not None and _u_decision.get("accept"):
                risk_frac = float(_u_decision["f_actual"])
            else:
                log.debug(f"[Budget] {sym} skipped: no heat budget available")
                continue

        # ══ [SING-TIMING Layer 3B] Resonance Risk Boost ══
        # مطابق تماماً لمنطق Live: يضاعف المخاطرة في ACTIVE.
        if (getattr(CFG, 'SING_RISK_BOOST_ENABLED', False)
                and getattr(CFG, 'SING_TIMING_ENABLED', False)):
            try:
                _rb_state, _rb_rho = _resonance_state_for_direction(
                    ad, int(sig.feat_idx), sig.action, CFG
                )
                if _rb_state == "ACTIVE":
                    _boost = float(getattr(
                        CFG, 'SING_RISK_BOOST_ACTIVE', 1.20
                    ))
                    risk_frac *= _boost
                elif _rb_state == "EMERGING":
                    _boost = float(getattr(
                        CFG, 'SING_RISK_BOOST_EMERGING', 1.00
                    ))
                    risk_frac *= _boost
            except Exception:
                pass

        # Apply drawdown multiplier + floor protection
        risk_frac *= dd_mult * power_law_scale
        risk_frac = float(np.clip(risk_frac,
                                    CFG.MIN_RISK_PER_TRADE if CFG.BUDGET_ENABLED else CFG.MIN_RISK,
                                    CFG.MAX_RISK_PER_TRADE if CFG.BUDGET_ENABLED else CFG.MAX_RISK))

        equity_base = max(capital - CFG.CAPITAL_FLOOR, 0.0)
        risk_amt = equity_base * risk_frac

        # Required quantity
        qty = risk_amt / delta

        # Leverage cap
        # ══ [MFAL] Adaptive leverage (backtest mode) ══
        dynamic_leverage = compute_adaptive_leverage(
            symbol=sym,
            sig=sig,
            open_pos_live=open_pos,
            capital=capital,
            peak_capital=peak_cap,
            corr_cache=corr_matrix,
            exchange=None,
            cfg=CFG,
        )

        # ══ [LIVE PARITY] Apply LevCap + LiqGate like live does ══
        # Live uses real MMR from the exchange. Backtest uses the
        # LIQ_FALLBACK_MMR (2%) as a proxy — same as live's fallback.
        if _sim_live and getattr(CFG, 'LIQ_ENABLED', True):
            _mmr = float(CFG.LIQ_FALLBACK_MMR)
            _sl_frac_max = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
            _lev_by_liq = compute_max_leverage_by_liq(
                sl_frac_max=_sl_frac_max,
                mmr=_mmr,
                safety_mult=float(CFG.LIQ_SAFETY_MULT),
                symbol=sym,
            )
            if dynamic_leverage > _lev_by_liq:
                dynamic_leverage = max(int(CFG.LEVERAGE_MIN), _lev_by_liq)
            if dynamic_leverage < int(CFG.LEVERAGE_MIN):
                log.debug(f"[LevCap] {sym} leverage below min — skip")
                continue
            # LiqGate: reject if SL too close to Liq
            _liq_px = compute_liquidation_price(
                opt_px, sig.action, dynamic_leverage, _mmr
            )
            _liq_gap = abs(opt_px - _liq_px)
            _sl_gap = abs(opt_px - sl_h)
            if (_liq_gap <= 1e-12 or
                    _sl_gap * float(CFG.LIQ_SAFETY_MULT) > _liq_gap):
                log.debug(f"[LiqGate] {sym} REJECT at backtest entry")
                continue

        max_notional = capital * dynamic_leverage
        qty = min(qty, max_notional / opt_px)

        # ══ [NOTIONAL CAP] ══
        qty = cap_notional(qty, opt_px)

        # ══ [UNIFIED-BT] override qty (first) ══
        if _u_decision is not None and _u_decision.get("accept"):
            qty = float(_u_decision["qty"])
            dynamic_leverage = int(_u_decision["leverage"])
            risk_frac = float(_u_decision["f_actual"])
            max_notional = capital * dynamic_leverage
            risk_amt = qty * delta

        not_ = qty * opt_px

        if not_ < CFG.MIN_NOTIONAL:
            continue

        # Store risk_frac for heat accounting
        sig.dynamic_risk = float(risk_frac)   # ← critical: heat tracking uses this

        # تنفيذ الانزلاق (مساوي لصفر لأننا صانعي سيولة Maker)
        eff_px    = apply_slippage(opt_px, qty, sig.adv_usd, sig.action, mode)
        slip_paid = abs(eff_px-opt_px)*qty

        # تعديل إحداثيات الوقف بناءً على سعر الدخول الفعلي بعد انزلاق الشبكة
        if sig.action == "BUY":
            sl_h = eff_px - sl_distance
        else:
            sl_h = eff_px + sl_distance
            
        delta = abs(eff_px - sl_h)
        if delta < 1e-8: continue
        
        # إعادة تقييم حفظ الطاقة وحجم المركز النهائي
        qty = min(risk_amt / delta, max_notional / eff_px)

        # ══ [NOTIONAL CAP] ══
        qty = cap_notional(qty, eff_px)

        # ══ [UNIFIED-BT] override qty (second) ══
        if _u_decision is not None and _u_decision.get("accept"):
            qty = float(_u_decision["qty"])

        not_ = qty * eff_px

        if not_ < CFG.MIN_NOTIONAL: continue

        # ══ [DYNAMIC TRAIL] compute σ-scaled trail params at entry ══
        entry_fi = max(0, min(opt_ci - ad.feat_start,
                              len(ad.E_therm) - 1))
        trail_d, trail_a = compute_trail_params(ad, entry_fi)

        open_pos[sym] = OpenPosition(
            symbol=sym, signal=sig,
            entry_px=eff_px, pos_size=qty, trail_sl=sl_h,
            entry_cap=capital, entry_ci=opt_ci, current_ci=opt_ci,
            slip_paid=slip_paid, opt_entry=opt_entry, tri_entry=sig.tri_val,
            trail_dist_frac=trail_d,
            trail_activate_frac=trail_a,
            sl_dist_initial=float(abs(eff_px - sl_h)),
            trail_peak_R=0.0,
            entry_sub_idx=opt_sub_idx,
        )

    for sym, pos in list(open_pos.items()):
        ad = assets[sym]
        # [N6-FIX] simulate SL/TP/MaxHold on remaining bars before
        # closing at the final price. Matches live broker behaviour.
        _advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp)
        ep = ad.closes[-1]
        _close(pos, ad, ep, "EndOfData", len(ad.closes)-1)

    return trades_out, equity


# ════════════════════════════════════════════════════════════════
# § 16  المقاييس الإحصائية
# ════════════════════════════════════════════════════════════════

def compute_metrics(trades, equity, init):
    if not trades: return {'n_trades':0}
    pnls  = [t.net_pnl for t in trades]
    lrs   = [t.log_return for t in trades]
    wins  = [p for p in pnls if p>0]; loss=[p for p in pnls if p<=0]
    lw    = sum(1 for t in trades if t.liq_warn)
    opt   = sum(1 for t in trades if t.entry_optimized)
    tri_x = sum(1 for t in trades if t.exit_reason.startswith("TRI"))
    topo_x= sum(1 for t in trades if t.exit_reason.startswith("Topo"))
    eq    = np.array(equity)
    peak  = np.maximum.accumulate(eq)
    dd    = (peak-eq)/(peak+1e-12)*100
    m_lr  = float(np.mean(lrs)); s_lr=float(np.std(lrs,ddof=1))
    sh    = (m_lr/s_lr*np.sqrt(252)) if s_lr>1e-10 else 0.
    ec: Dict[str,int]={}
    for t in trades:
        k = t.exit_reason.split("=")[0] if "=" in t.exit_reason else \
            t.exit_reason.split("(")[0]
        ec[k] = ec.get(k,0)+1

    # إحصاءات التعديلات الجديدة
    avg_T_info   = float(np.mean([t.T_info_at_entry for t in trades]))
    avg_dyn_risk = float(np.mean([t.dynamic_risk_used for t in trades]))
    sell_count   = sum(1 for t in trades if t.action=="SELL")
    buy_count    = sum(1 for t in trades if t.action=="BUY")

    return {
        'mean_log_return': m_lr, 'median_log_return': float(np.median(lrs)),
        'std_log_return':  s_lr, 'n_trades': len(trades),
        'win_rate':   len(wins)/len(pnls), 'sharpe_ratio': sh,
        'profit_factor': (sum(wins)/abs(sum(loss))) if loss and wins else float('inf'),
        'avg_win':  float(np.mean(wins)) if wins else 0.,
        'avg_loss': float(np.mean(loss)) if loss else 0.,
        'initial_capital': init, 'final_capital': equity[-1],
        'total_return_pct': (equity[-1]-init)/init*100,
        'max_drawdown_pct': float(np.max(dd)),
        'max_drawdown_abs': float(np.max(peak-eq)),
        'liq_warnings': lw, 'liq_warn_pct': lw/len(trades)*100,
        'optimal_entries': opt, 'opt_entry_pct': opt/len(trades)*100,
        'tri_exits': tri_x, 'tri_exit_pct': tri_x/len(trades)*100,
        'topo_exits': topo_x, 'topo_exit_pct': topo_x/len(trades)*100,
        'total_slip': sum(t.slippage_paid for t in trades),
        'exit_distribution': ec,
        'avg_T_info': avg_T_info,
        'avg_dynamic_risk': avg_dyn_risk,
        'buy_count': buy_count, 'sell_count': sell_count,
    }


# ════════════════════════════════════════════════════════════════
# § 17  التقرير والرسوم البيانية
# ════════════════════════════════════════════════════════════════

def print_report(m, mode):
    sep = "═"*72
    print(f"\n{sep}")
    print(f"   📊  محرك التداول الثرموديناميكي الكمي v6.0  [{mode.upper()}]")
    print(f"   🌌  محرك التفرد – Singularity Engine")
    print(sep)
    if not m.get('n_trades'):
        print("   لا توجد صفقات."); return

    print(f"\n▶ المقياس الأساسي (م٦): E[ln(1+fR)] لكل صفقة")
    print(f"   متوسط  : {m['mean_log_return']:+.6f}")
    print(f"   وسيط   : {m['median_log_return']:+.6f}")
    print(f"   انحراف : {m['std_log_return']:.6f}")
    print(f"   → {'✅ حافة إيجابية' if m['mean_log_return']>0 else '❌ حافة سلبية'}")

    print(f"\n▶ إحصاءات الصفقات")
    print(f"   عدد الصفقات      : {m['n_trades']:,}")
    print(f"   شراء / بيع        : {m['buy_count']:,} / {m['sell_count']:,}")
    print(f"   نسبة النجاح      : {m['win_rate']*100:.2f}%")
    print(f"   عامل الربح (PF)  : {m['profit_factor']:.3f}")
    print(f"   متوسط الربح      : ${m['avg_win']:,.4f}")
    print(f"   متوسط الخسارة   : ${m['avg_loss']:,.4f}")
    print(f"   شارب (سنوي)      : {m['sharpe_ratio']:.3f}")
    print(f"   دخول مُحسَّن       : {m['optimal_entries']:,}  ({m['opt_entry_pct']:.1f}%)")

    print(f"\n▶ التعديلات الجديدة (v6.0)")
    print(f"   ① متوسط T_info (حرارة معلوماتية) : {m['avg_T_info']:.4f}")
    print(f"   ① متوسط المخاطرة الديناميكية     : {m['avg_dynamic_risk']*100:.3f}%")
    print(f"   ② خروج توبولوجي (Topo-Div)       : {m['topo_exits']:,}  ({m['topo_exit_pct']:.1f}%)")
    print(f"   خروج TRI مبكر                    : {m['tri_exits']:,}  ({m['tri_exit_pct']:.1f}%)")
    print(f"   انزلاق إجمالي                    : ${m['total_slip']:,.2f}")

    print(f"\n▶ رأس المال (مقياس ثانوي)")
    print(f"   ابتدائي: ${m['initial_capital']:.2f}  →  نهائي: ${m['final_capital']:,.2f}")
    print(f"   العائد الكلي     : {m['total_return_pct']:,.1f}%")
    print(f"   أقصى انخفاض     : {m['max_drawdown_pct']:.2f}%  (${m['max_drawdown_abs']:,.2f})")

    lw_pct = m['liq_warn_pct']
    wrn = "⛔ مرتفع" if lw_pct>20 else ("⚠ ملحوظ" if lw_pct>5 else "✅ معقول")
    print(f"\n▶ تحذير السيولة (م٦): {m['liq_warnings']:,} ({lw_pct:.1f}%)  {wrn}")

    print(f"\n▶ توزيع أسباب الخروج")
    for r,c in sorted(m['exit_distribution'].items(), key=lambda x:-x[1]):
        print(f"   {r:25s}: {c:7,}  ({c/m['n_trades']*100:.1f}%)")

    # ══ [FILTER REPORT] ══
    if CFG.FILTER_ENABLED and _FILTER_STATS['total_signals'] > 0:
        _tot = _FILTER_STATS['total_signals']
        _rej = _FILTER_STATS['rejected']
        _kept = _FILTER_STATS['kept']
        print(f"\n▶ فلتر الدخول (TRADE FILTER)")
        print(f"   إشارات مُنتَجة إجمالاً : {_tot:,}")
        print(f"   مقبولة                 : {_kept:,} "
              f"({_kept/max(_tot,1)*100:.1f}%)")
        print(f"   مرفوضة                 : {_rej:,} "
              f"({_rej/max(_tot,1)*100:.1f}%)")
        print(f"   ── الأصوات المُفعَّلة ──")
        print(f"   action_bias            : "
              f"{'ON' if CFG.FILTER_USE_ACTION_BIAS else 'OFF'}")
        print(f"   ema_slope              : "
              f"{'ON' if CFG.FILTER_USE_EMA_SLOPE else 'OFF'}")
        print(f"   high_atr               : "
              f"{'ON' if CFG.FILTER_USE_HIGH_ATR else 'OFF'}")
        print(f"   friction_drag          : "
              f"{'ON' if CFG.FILTER_USE_FRICTION_DRAG else 'OFF'}")
        print(f"   عدد الأصوات المطلوبة    : {CFG.FILTER_MIN_VOTES}")
        print(f"   ── أعلى أسباب الرفض ──")
        _top = sorted(_FILTER_STATS['vote_counts'].items(),
                       key=lambda x: -x[1])[:5]
        for reason, cnt in _top:
            print(f"   {reason:35s}: {cnt:6,}")
        print(f"   ── الأصوات الفردية ──")
        for vote, cnt in sorted(_FILTER_STATS['vote_singles'].items(),
                                 key=lambda x: -x[1]):
            print(f"   {vote:35s}: {cnt:6,}")

    print(f"\n{sep}\n")
    


def plot_results(trades, equity, m, out="quantum_v6_results.png"):
    if not trades or m.get('n_trades', 0) == 0:
        log.info("[Plot] no trades — skipping plot generation")
        return
    fig = plt.figure(figsize=(20,14), facecolor='#0d0d0d')
    gs  = gridspec.GridSpec(3,4, figure=fig, hspace=0.45, wspace=0.38)
    bk,tc,gr = '#111111','#e0e0e0','#2a2a2a'
    plt.rcParams.update({'text.color':tc,'axes.labelcolor':tc,
                         'xtick.color':tc,'ytick.color':tc})
    eq = np.array(equity)

    # منحنى الأسهم (عرض كامل)
    ax1 = fig.add_subplot(gs[0,:])
    ax1.semilogy(eq, c='#00e5ff', lw=0.7, alpha=0.9)
    ax1.fill_between(range(len(eq)), CFG.INITIAL_CAPITAL, eq,
                     where=eq>=CFG.INITIAL_CAPITAL, color='#00e5ff', alpha=0.08)
    ax1.axhline(CFG.INITIAL_CAPITAL, c='#ff6b6b', ls='--', lw=1.)
    ax1.set_facecolor(bk); ax1.grid(True,c=gr,lw=0.4)
    ax1.set_title(
        f"منحنى الأسهم (Log) | v6.0 Singularity Engine | "
        f"{m['n_trades']:,} صفقة | MaxDD={m['max_drawdown_pct']:.1f}%",
        c='#00e5ff', fontsize=11)

    # توزيع ln(1+fR)
    ax2 = fig.add_subplot(gs[1,0])
    lrs=[t.log_return for t in trades]
    ax2.hist(lrs,bins=80,color='#ab47bc',alpha=0.7,edgecolor='none')
    ax2.axvline(0,c='#ff6b6b',lw=1.5,ls='--')
    ax2.axvline(m['mean_log_return'],c='#00e5ff',lw=1.5,
                label=f"μ={m['mean_log_return']:.5f}")
    ax2.set_facecolor(bk); ax2.grid(True,c=gr,lw=0.4)
    ax2.set_title("توزيع ln(1+fR)",c='#ab47bc',fontsize=10)
    ax2.legend(fontsize=8,framealpha=0.3)

    # Drawdown
    ax3 = fig.add_subplot(gs[1,1])
    peak=np.maximum.accumulate(eq); dd=(peak-eq)/(peak+1e-12)*100
    ax3.fill_between(range(len(dd)),0,-dd,color='#ef5350',alpha=0.6)
    ax3.set_facecolor(bk); ax3.grid(True,c=gr,lw=0.4)
    ax3.set_title(f"Drawdown (max={m['max_drawdown_pct']:.1f}%)",c='#ef5350',fontsize=10)

    # ① توزيع T_info (درجة الحرارة المعلوماتية)
    ax4 = fig.add_subplot(gs[1,2])
    T_wins = [t.T_info_at_entry for t in trades if t.net_pnl>0]
    T_loss = [t.T_info_at_entry for t in trades if t.net_pnl<=0]
    ax4.hist(T_wins, bins=40, alpha=0.7, color='#66bb6a', label='رابحة')
    ax4.hist(T_loss, bins=40, alpha=0.7, color='#ef5350', label='خاسرة')
    ax4.axvline(m['avg_T_info'], c='#00e5ff', lw=1.5, label=f"μ={m['avg_T_info']:.3f}")
    ax4.set_facecolor(bk); ax4.grid(True,c=gr,lw=0.4)
    ax4.set_title("① T_info عند الدخول (Boltzmann)",c='#66bb6a',fontsize=10)
    ax4.legend(fontsize=7,framealpha=0.3)

    # أسباب الخروج
    ax5 = fig.add_subplot(gs[1,3])
    labs=list(m['exit_distribution'].keys()); vals=list(m['exit_distribution'].values())
    clrs=['#26c6da','#66bb6a','#ffa726','#ef5350','#ab47bc','#78909c','#ff7043']
    ax5.pie(vals,labels=labs,autopct='%1.1f%%',colors=clrs[:len(labs)],textprops={'color':tc,'fontsize':8})
    ax5.set_title("② أسباب الخروج",c=tc,fontsize=10)

    # BUY vs SELL
    ax6 = fig.add_subplot(gs[2,0])
    buy_pnl  = [t.net_pnl for t in trades if t.action=="BUY"]
    sell_pnl = [t.net_pnl for t in trades if t.action=="SELL"]
    ax6.hist(buy_pnl,  bins=50, alpha=0.7, color='#66bb6a', label=f'BUY  n={len(buy_pnl)}')
    ax6.hist(sell_pnl, bins=50, alpha=0.7, color='#ef5350', label=f'SELL n={len(sell_pnl)}')
    ax6.axvline(0,c='white',lw=1.,ls='--')
    ax6.set_facecolor(bk); ax6.grid(True,c=gr,lw=0.4)
    ax6.set_title("④ BUY vs SELL (Λ-bias)",c=tc,fontsize=10)
    ax6.legend(fontsize=8,framealpha=0.3)

    # نجاح حسب Score
    ax7 = fig.add_subplot(gs[2,1])
    sg={}
    for t in trades: sg.setdefault(int(t.score),[]).append(1. if t.net_pnl>0 else 0.)
    scs=sorted(sg.keys()); wrs=[np.mean(sg[s])*100 for s in scs]; cnts=[len(sg[s]) for s in scs]
    ax7.bar(scs,wrs,color='#26c6da',alpha=0.8)
    ax7.set_facecolor(bk); ax7.grid(True,c=gr,lw=0.4,axis='y')
    ax7.set_title("نجاح حسب Score",c='#26c6da',fontsize=10)
    for s,w,c in zip(scs,wrs,cnts): ax7.text(s,w+.5,f"{c}",ha='center',fontsize=7,color=tc)

    # توزيع المخاطرة الديناميكية
    ax8 = fig.add_subplot(gs[2,2])
    dr_vals = [t.dynamic_risk_used*100 for t in trades]
    ax8.hist(dr_vals, bins=50, color='#ffa726', alpha=0.8, edgecolor='none')
    ax8.axvline(CFG.BASE_RISK*100, c='#ff6b6b', lw=1.5, ls='--', label=f'Base={CFG.BASE_RISK*100}%')
    ax8.set_facecolor(bk); ax8.grid(True,c=gr,lw=0.4)
    ax8.set_title("① توزيع f*(T) الديناميكي",c='#ffa726',fontsize=10)
    ax8.legend(fontsize=8,framealpha=0.3)

    # ملخص إحصائي
    ax9 = fig.add_subplot(gs[2,3]); ax9.axis('off'); ax9.set_facecolor(bk)
    summ=(f"صفقات: {m['n_trades']:,}\n"
          f"نجاح:  {m['win_rate']*100:.1f}%\n"
          f"PF:    {m['profit_factor']:.2f}\n"
          f"Sharpe:{m['sharpe_ratio']:.2f}\n"
          f"MaxDD: {m['max_drawdown_pct']:.1f}%\n"
          f"Topo:  {m['topo_exit_pct']:.1f}%\n"
          f"TRI:   {m['tri_exit_pct']:.1f}%\n"
          f"Opt:   {m['opt_entry_pct']:.1f}%\n"
          f"T_avg: {m['avg_T_info']:.3f}\n"
          f"r_avg: {m['avg_dynamic_risk']*100:.3f}%\n"
          f"Slip:  ${m['total_slip']:,.0f}")
    ax9.text(0.05,0.95,summ,transform=ax9.transAxes,va='top',color=tc,fontsize=9,
             fontfamily='monospace',
             bbox=dict(boxstyle='round',fc='#1e1e1e',alpha=0.85))
    plt.savefig(out,dpi=150,bbox_inches='tight',facecolor='#0d0d0d',edgecolor='none')
    log.info(f"📊 {out}")


# ════════════════════════════════════════════════════════════════
# § 18  وضع الباك-تيست
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# § 17.5  Level-1 Performance: Parallelism + AssetData Cache
# ════════════════════════════════════════════════════════════════

_ASSET_CACHE_DIR = "asset_cache"
os.makedirs(_ASSET_CACHE_DIR, exist_ok=True)


def _asset_cache_key(sym: str, timeframe: str, df, cfg) -> Optional[str]:
    """
    Fingerprint: dataset identity + relevant CFG params that affect AssetData.
    If any of these change, the cache is invalidated.
    """
    n = len(df)
    if n == 0:
        return None
    try:
        first_ts = int(df.index[0].value)
        last_ts = int(df.index[-1].value)
        first_c = float(df['Close'].iloc[0])
        last_c = float(df['Close'].iloc[-1])
    except Exception:
        return None

    cfg_sig = (
        f"N={cfg.N}|W={cfg.W}|K={cfg.K}|"
        f"KMIN={cfg.K_MIN}|KMAX={cfg.K_MAX}|"
        f"KQ={cfg.KQUANT_ALPHA}|TRAIN={cfg.TRAIN_FRACTION}|"
        f"LEVBASE={cfg.LEVERAGE_BASE}|LEVMIN={cfg.LEVERAGE_MIN}|"
        f"LEVMAX={cfg.LEVERAGE_MAX}"
    )
    raw = (f"{sym}|{timeframe}|{n}|{first_ts}|{last_ts}|"
           f"{first_c:.6f}|{last_c:.6f}|{cfg_sig}")
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _asset_cache_path(sym: str, timeframe: str, key: str) -> str:
    safe = sym.replace('/', '_')
    return os.path.join(_ASSET_CACHE_DIR, f"{safe}_{timeframe}_{key}.pkl")


def _load_asset_cache(sym: str, timeframe: str, df, cfg) -> Optional[AssetData]:
    if not cfg.ASSET_CACHE_ENABLED:
        return None
    key = _asset_cache_key(sym, timeframe, df, cfg)
    if key is None:
        return None
    path = _asset_cache_path(sym, timeframe, key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            ad = pickle.load(f)
        # Light validation
        if not hasattr(ad, 'score') or len(ad.closes) != len(df):
            return None
        return ad
    except Exception as e:
        log.warning(f"[Cache] load failed {sym}: {e}")
        return None


def _save_asset_cache(sym: str, timeframe: str, df, ad, cfg) -> None:
    if not cfg.ASSET_CACHE_ENABLED or ad is None:
        return
    key = _asset_cache_key(sym, timeframe, df, cfg)
    if key is None:
        return
    path = _asset_cache_path(sym, timeframe, key)
    try:
        with open(path, 'wb') as f:
            pickle.dump(ad, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        log.warning(f"[Cache] save failed {sym}: {e}")


def _worker_init(cfg_dict: Dict) -> None:
    """Re-apply CFG overrides in child process (no-op on fork)."""
    failed = 0
    for k, v in cfg_dict.items():
        try:
            setattr(CFG, k, v)
        except Exception as e:
            log.debug(f"[Worker] setattr {k} failed: {e}")
            failed += 1
    if failed > 0:
        log.warning(f"[Worker] {failed}/{len(cfg_dict)} CFG fields not applied")


def _process_asset_worker(args):
    """
    Top-level worker for ProcessPoolExecutor.
    Returns: (sym, AssetData | None, err | None, source ∈ {'cache','computed'})
    """
    # [SUB-BARS] args now carries an optional sub_df (may be None)
    if len(args) == 6:
        sym, df, cap, timeframe, cfg_dict, sub_df = args
    else:
        sym, df, cap, timeframe, cfg_dict = args
        sub_df = None

    # Restore CFG in child (needed for spawn/forkserver; harmless on fork)
    failed = 0
    for k, v in cfg_dict.items():
        try:
            setattr(CFG, k, v)
        except Exception as e:
            log.debug(f"[Worker:{sym}] setattr {k} failed: {e}")
            failed += 1
    if failed > 0:
        log.warning(f"[Worker:{sym}] {failed} CFG fields not applied")

    # 1. Try cache
    ad = _load_asset_cache(sym, timeframe, df, CFG)
    if ad is not None:
        return (sym, ad, None, 'cache')

    # 2. Compute fresh
    try:
        ad = process_asset(sym, df, current_capital=cap, sub_df=sub_df)
    except Exception as e:
        import traceback
        return (sym, None, f"{type(e).__name__}: {e}\n{traceback.format_exc()}", 'error')

    # 3. Save to cache
    if ad is not None:
        _save_asset_cache(sym, timeframe, df, ad, CFG)

    return (sym, ad, None, 'computed')

# ════════════════════════════════════════════════════════════════
# § 17.7  ML Filter (Optional)
# ════════════════════════════════════════════════════════════════

_ML_MODEL = None
_ML_SCALER = None
_ML_FEATURE_NAMES: List[str] = []

def _load_ml_filter() -> bool:
    """Load model from disk. Called once at startup when enabled."""
    global _ML_MODEL, _ML_SCALER, _ML_FEATURE_NAMES
    path = CFG.ML_FILTER_MODEL_PATH
    if not os.path.exists(path):
        log.error(f"[ML] model file not found: {path}")
        return False
    try:
        with open(path, 'rb') as f:
            payload = pickle.load(f)
        _ML_MODEL = payload['model']
        _ML_SCALER = payload['scaler']
        _ML_FEATURE_NAMES = payload.get('features', [])
        # Accept 52 (v5) or 92 (v6, sequence-aware). Set expected count globally.
        global _ML_EXPECTED_N
        n_model = len(_ML_FEATURE_NAMES)
        if n_model not in (52, 92):
            log.error(f"[ML] Unsupported feature count: {n_model} "
                      f"(expected 52 or 92)")
            return False
        _ML_EXPECTED_N = n_model
        log.info(f"[ML] Model expects {_ML_EXPECTED_N} features")

        md = payload.get('metadata', {})
        log.info(f"[ML] Loaded model: AUC_test={md.get('auc_test', '?'):.4f}, "
                 f"threshold={payload.get('threshold', '?'):.3f}, "
                 f"reject_rate(train)={md.get('reject_rate', '?')}")
        # If user didn't override, use model's recommended threshold
        if 'threshold' in payload:
            CFG.ML_FILTER_THRESHOLD = float(payload['threshold'])
        return True
    except Exception as e:
        log.error(f"[ML] load failed: {e}")
        return False


# ══ [Sequence Learning — v6] ══
ML_SEQ_WINDOW = 20
ML_SEQ_CORE = [
    "ret_24h", "rvol_1h", "rvol_24h", "tf_agreement", "trend_1h",
    "candle_body_ratio", "upper_wick_ratio", "volume_z_20",
    "range_position_20", "atr_percentile",
]


def _extract_ml_features_v5(sig, ad) -> np.ndarray:
    """52-feature base extractor (identical to ml_filter_trainer_v5)."""
    ci = sig.close_idx
    fi = sig.feat_idx
    try:
        ts = sig.timestamp
        hour = ts.hour; minute = ts.minute; dow = ts.dayofweek
        hour_sin = float(np.sin(2 * np.pi * hour / 24))
        hour_cos = float(np.cos(2 * np.pi * hour / 24))
        dow_sin = float(np.sin(2 * np.pi * dow / 7))
        dow_cos = float(np.cos(2 * np.pi * dow / 7))
        is_weekend = 1.0 if dow >= 5 else 0.0
        minutes_to_funding = (480 - ((hour * 60 + minute) % 480)) / 480.0

        closes = ad.closes; highs = ad.highs; lows = ad.lows; vols = ad.volumes
        opens_arr = getattr(ad, 'opens', None)
        if opens_arr is None:
            opens_arr = np.empty_like(closes)
            opens_arr[0] = closes[0]; opens_arr[1:] = closes[:-1]

        p_now = float(closes[ci]); o_now = float(opens_arr[ci])
        h_now = float(highs[ci]); l_now = float(lows[ci]); v_now = float(vols[ci])

        ret_24h = (p_now - float(closes[ci-24])) / max(float(closes[ci-24]),1e-12) if ci>=24 else 0.0
        ret_1h  = (p_now - float(closes[ci-1]))  / max(float(closes[ci-1]),1e-12)  if ci>=1  else 0.0

        def _rvol(window):
            if ci < window+1: return 0.0
            w = closes[ci-window: ci+1]
            lr = np.diff(np.log(np.maximum(w, 1e-12)))
            return float(np.std(lr))
        rvol_1h = _rvol(20); rvol_24h = _rvol(100)

        ema200_val = float(ad.ema200[ci]) if ci < len(ad.ema200) else p_now
        dist_ema = (p_now - ema200_val) / max(ema200_val, 1e-12)

        if ci >= 50:
            vw = vols[ci-50: ci+1]
            vm = float(np.mean(vw)); vs = float(np.std(vw)) + 1e-12
            vol_z = (v_now - vm) / vs
        else:
            vol_z = 0.0

        rng = h_now - l_now
        if rng > 1e-12:
            candle_body_ratio = abs(p_now - o_now) / rng
            upper_wick_ratio  = (h_now - max(o_now, p_now)) / rng
            lower_wick_ratio  = (min(o_now, p_now) - l_now) / rng
        else:
            candle_body_ratio = upper_wick_ratio = lower_wick_ratio = 0.0

        consec = 0
        if ci >= 1:
            sgn0 = 1 if p_now > o_now else (-1 if p_now < o_now else 0)
            for k in range(1, min(6, ci+1)):
                c_ = closes[ci-k]; o_ = opens_arr[ci-k]
                sg_ = 1 if c_ > o_ else (-1 if c_ < o_ else 0)
                if sg_ == sgn0 and sgn0 != 0: consec += 1
                else: break
        consecutive_same_dir = float(consec)

        candle_dir_agrees = 1.0 if ((p_now > o_now and sig.action=="BUY") or
                                    (p_now < o_now and sig.action=="SELL")) else 0.0

        # ══ NOTE: Names reflect INTENDED horizons at 1m timeframe ══
        # At 1h (default), these represent: 60h=2.5d, 240h=10d, 1440h=60d.
        # The features are internally consistent (same computation) regardless
        # of the actual timeframe; only the semantic meaning of the names shifts.
        # ═══════════════════════════════════════════════════════════
        trend_1h = np.sign(closes[ci] - closes[ci - 60]) if ci >= 60 else 0.0
        trend_4h = np.sign(closes[ci] - closes[ci - 240]) if ci >= 240 else 0.0
        trend_1d = np.sign(closes[ci] - closes[ci - 1440]) if ci >= 1440 else 0.0
        sig_dir  = 1 if sig.action=="BUY" else -1
        tf_agreement = (float(np.sign(trend_1h)==sig_dir) +
                        float(np.sign(trend_4h)==sig_dir) +
                        float(np.sign(trend_1d)==sig_dir)) / 3.0

        if ci >= 20:
            v20 = vols[ci-20: ci+1]
            vm20 = float(np.mean(v20)); vs20 = float(np.std(v20)) + 1e-12
            volume_z_20 = (v_now - vm20) / vs20
            x = np.arange(len(v20), dtype=np.float64); xm = x.mean(); ym = float(np.mean(v20))
            num = float(np.sum((x-xm)*(v20-ym))); den = float(np.sum((x-xm)**2)) + 1e-12
            volume_slope_20 = num / den / (vm20 + 1e-12)
            if len(v20) >= 3:
                w = closes[ci-20: ci+1]
                absr = np.abs(np.diff(np.log(np.maximum(w, 1e-12))))
                vv = vols[ci-19: ci+1]
                if len(absr)==len(vv) and len(vv)>=3:
                    m1 = absr.mean(); m2 = float(np.mean(vv))
                    num2 = np.sum((absr-m1)*(vv-m2))
                    den2 = np.sqrt(np.sum((absr-m1)**2)*np.sum((vv-m2)**2)) + 1e-12
                    volume_price_corr_20 = float(num2/den2)
                else:
                    volume_price_corr_20 = 0.0
            else:
                volume_price_corr_20 = 0.0
        else:
            volume_z_20 = volume_slope_20 = volume_price_corr_20 = 0.0

        volume_ratio_50 = (v_now / (float(np.mean(vols[ci-50: ci+1])) + 1e-12)
                           if ci>=50 else 1.0)

        if ci >= 20:
            h20 = float(np.max(highs[ci-20: ci+1]))
            l20 = float(np.min(lows[ci-20: ci+1]))
            range_position_20 = (p_now - l20) / (h20 - l20 + 1e-12)
            dist_from_20_high = (p_now - h20) / p_now
            dist_from_20_low  = (p_now - l20) / p_now
        else:
            range_position_20 = 0.5; dist_from_20_high = dist_from_20_low = 0.0

        if ci >= 100:
            atr_window = ad.atr14[ci-100: ci+1]
            atr_percentile = float(np.mean(atr_window <= ad.atr14[ci]))
        else:
            atr_percentile = 0.5

        if ci >= 80:
            sig_w = 20; vovs = []
            for k in range(60):
                ii = ci - k
                if ii - sig_w < 0: break
                ww = closes[ii-sig_w: ii+1]
                lrw = np.diff(np.log(np.maximum(ww, 1e-12)))
                vovs.append(np.std(lrw))
            vol_of_vol = float(np.std(vovs)) if len(vovs) >= 5 else 0.0
        else:
            vol_of_vol = 0.0

        range_expansion = (h_now - l_now) / (float(ad.atr14[ci]) + 1e-12)

        v = np.array([
            float(sig.score), float(np.log1p(max(sig.score, 0.0))),
            float(sig.T_info_val), float(sig.dyn_sl_factor), float(sig.dynamic_risk),
            1.0 if sig.action=="BUY" else 0.0,
            float(ad.geodesic_accel[fi]), float(ad.friction[fi]),
            float(ad.gauge_force[fi]), float(ad.delta_gap[fi]),
            float(np.log1p(max(ad.V[fi], 0.0))), float(-ad.C[fi]),
            float(ad.dH[fi]), float(ad.dF[fi]),
            float(sig.atr / max(sig.price, 1e-12)),
            float(ad.adv_usd[ci] / max(ad.closes[ci], 1e-12)),
            float(hour), float(sig.tri_val),
            hour_sin, hour_cos, float(dow), is_weekend,
            float(ret_24h), float(ret_1h), float(rvol_1h), float(rvol_24h),
            float(dist_ema), float(vol_z),
            float(candle_body_ratio), float(upper_wick_ratio), float(lower_wick_ratio),
            float(consecutive_same_dir), float(candle_dir_agrees),
            float(trend_1h), float(trend_4h), float(trend_1d), float(tf_agreement),
            float(volume_z_20), float(volume_slope_20), float(volume_price_corr_20),
            float(volume_ratio_50),
            hour_sin, hour_cos, dow_sin, dow_cos, float(minutes_to_funding),
            float(range_position_20), float(dist_from_20_high), float(dist_from_20_low),
            float(atr_percentile), float(vol_of_vol), float(range_expansion),
        ], dtype=np.float64)
    except Exception:
        return np.zeros(52, dtype=np.float64)
    if not np.all(np.isfinite(v)):
        v = np.where(np.isfinite(v), v, 0.0)
    return v


def _ml_core_at(ad, sig, name: str, idx: int) -> float:
    """Compute a single core feature at arbitrary candle index `idx`."""
    closes = ad.closes; highs = ad.highs; lows = ad.lows; vols = ad.volumes
    try:
        n = len(closes)
        if idx < 0 or idx >= n: return 0.0
        if name == "ret_24h":
            if idx < 24: return 0.0
            return (closes[idx]-closes[idx-24]) / max(closes[idx-24], 1e-12)
        if name == "rvol_1h":
            if idx < 21: return 0.0
            w = closes[idx-20: idx+1]
            return float(np.std(np.diff(np.log(np.maximum(w, 1e-12)))))
        if name == "rvol_24h":
            if idx < 101: return 0.0
            w = closes[idx-100: idx+1]
            return float(np.std(np.diff(np.log(np.maximum(w, 1e-12)))))
        if name == "trend_1h":
            if idx < 60: return 0.0
            return float(np.sign(closes[idx]-closes[idx-60]))
        if name == "tf_agreement":
            t1  = np.sign(closes[idx]-closes[idx-60])   if idx>=60   else 0
            t4  = np.sign(closes[idx]-closes[idx-240])  if idx>=240  else 0
            t1d = np.sign(closes[idx]-closes[idx-1440]) if idx>=1440 else 0
            sd  = 1 if sig.action=="BUY" else -1
            return (float(np.sign(t1)==sd) + float(np.sign(t4)==sd) +
                    float(np.sign(t1d)==sd)) / 3.0
        if name == "candle_body_ratio":
            rng = highs[idx] - lows[idx]
            if rng < 1e-12: return 0.0
            o_ = closes[idx-1] if idx>0 else closes[idx]
            return abs(closes[idx]-o_) / rng
        if name == "upper_wick_ratio":
            rng = highs[idx] - lows[idx]
            if rng < 1e-12: return 0.0
            o_ = closes[idx-1] if idx>0 else closes[idx]
            return (highs[idx] - max(o_, closes[idx])) / rng
        if name == "volume_z_20":
            if idx < 20: return 0.0
            vw = vols[idx-20: idx+1]
            vm = float(np.mean(vw)); vs = float(np.std(vw)) + 1e-12
            return (float(vols[idx])-vm) / vs
        if name == "range_position_20":
            if idx < 20: return 0.5
            h20 = float(np.max(highs[idx-20: idx+1]))
            l20 = float(np.min(lows[idx-20: idx+1]))
            return (float(closes[idx])-l20) / (h20-l20+1e-12)
        if name == "atr_percentile":
            if idx < 100 or idx >= len(ad.atr14): return 0.5
            w = ad.atr14[idx-100: idx+1]
            return float(np.mean(w <= ad.atr14[idx]))
    except Exception:
        return 0.0
    return 0.0


def _ml_seq_stats(ad, sig, name: str, ci: int, W: int):
    if ci < W:
        return 0.0, 0.0, 0.0, 0.0
    vals = np.array([_ml_core_at(ad, sig, name, ci-k) for k in range(W-1, -1, -1)],
                    dtype=np.float64)
    vals = np.where(np.isfinite(vals), vals, 0.0)
    m = float(np.mean(vals)); sd = float(np.std(vals)); last = float(vals[-1])
    x = np.arange(W, dtype=np.float64); xm = x.mean()
    num = float(np.sum((x-xm)*(vals-m)))
    den = float(np.sum((x-xm)**2)) + 1e-12
    slope = num / den
    return m, sd, slope, last


def _extract_ml_features_v6(sig, ad) -> np.ndarray:
    """92-feature: 52 base + 40 sequence."""
    base = _extract_ml_features_v5(sig, ad)
    ci = sig.close_idx
    parts = []
    for name in ML_SEQ_CORE:
        parts.extend(_ml_seq_stats(ad, sig, name, ci, ML_SEQ_WINDOW))
    seq = np.array(parts, dtype=np.float64)
    v = np.concatenate([base, seq])
    if not np.all(np.isfinite(v)):
        v = np.where(np.isfinite(v), v, 0.0)
    return v


# Global: model's expected feature count (set at load time)
_ML_EXPECTED_N = 52


def _extract_ml_features(sig, ad) -> np.ndarray:
    """Dispatcher: always returns 92. Caller slices to model size."""
    return _extract_ml_features_v6(sig, ad)


# ════════════════════════════════════════════════════════════════
# § 17.75  Rule-Based Filter (no ML)
# ════════════════════════════════════════════════════════════════

_RULE_THRESHOLDS: Dict = {}   # {feature: (q33, q66)} — computed at startup


def compute_rule_thresholds(assets) -> None:
    """
    Compute global quantiles from all signals across all assets.
    Called once before backtest/live starts.
    """
    global _RULE_THRESHOLDS
    if not CFG.RULE_FILTER_ENABLED:
        return

    rvol24_vals = []
    dist_high_vals = []
    tf_std_vals = []
    range_pos_vals = []

    for sym, ad in assets.items():
        # rvol_24h at each valid signal time isn't computable here without sigs.
        # Instead use the whole distribution across the asset's history.
        # This is a proxy; in production use signal-time values.
        try:
            closes = ad.closes
            n = len(closes)
            if n < 120:
                continue
            # sample every 10th bar for speed
            for ci in range(100, n, 10):
                w = closes[ci-100: ci+1]
                lr = np.diff(np.log(np.maximum(w, 1e-12)))
                rvol24_vals.append(float(np.std(lr)))
                h20 = float(np.max(ad.highs[ci-20: ci+1]))
                dist_high_vals.append((float(closes[ci]) - h20) / float(closes[ci]))
                # tf_agreement std proxy: rolling std of trend sign over 20 bars
                sigs_20 = []
                for k in range(20):
                    ii = ci - k
                    if ii < 60:
                        break
                    sigs_20.append(np.sign(closes[ii] - closes[ii-60]))
                if len(sigs_20) >= 5:
                    tf_std_vals.append(float(np.std(sigs_20)))
                l20 = float(np.min(ad.lows[ci-20: ci+1]))
                h20b = float(np.max(ad.highs[ci-20: ci+1]))
                range_pos_vals.append((float(closes[ci]) - l20) / (h20b - l20 + 1e-12))
        except Exception:
            continue

    def _q(arr, p):
        if not arr:
            return 0.0
        return float(np.quantile(np.asarray(arr, dtype=np.float64), p))

    _RULE_THRESHOLDS = {
        'rvol24': (_q(rvol24_vals, CFG.RULE_REJECT_RVOL24_PCT), None),
        'dist_high': (None, _q(dist_high_vals, CFG.RULE_REJECT_DIST_HIGH_PCT)),
        'tf_std': (None, _q(tf_std_vals, CFG.RULE_REJECT_TF_STD_PCT)),
        'range_pos': (None, _q(range_pos_vals, CFG.RULE_REJECT_RANGE_POS_PCT)),
    }
    log.info(f"[RuleFilter] thresholds: "
             f"rvol24_q33={_RULE_THRESHOLDS['rvol24'][0]:.5f}, "
             f"dist_high_q66={_RULE_THRESHOLDS['dist_high'][1]:.5f}, "
             f"tf_std_q66={_RULE_THRESHOLDS['tf_std'][1]:.3f}, "
             f"range_pos_q66={_RULE_THRESHOLDS['range_pos'][1]:.3f}")


def _rule_compute_features(sig, ad):
    """Compute the 4 rule-features at signal time."""
    ci = sig.close_idx
    closes = ad.closes; highs = ad.highs; lows = ad.lows
    try:
        # C1: rvol_24h
        if ci < 101:
            rvol24 = 0.0
        else:
            w = closes[ci-100: ci+1]
            rvol24 = float(np.std(np.diff(np.log(np.maximum(w, 1e-12)))))

        # C2: dist from 20-high
        if ci < 20:
            dist_high = 0.0
        else:
            h20 = float(np.max(highs[ci-20: ci+1]))
            dist_high = (float(closes[ci]) - h20) / max(float(closes[ci]), 1e-12)

        # C3: tf_agreement std (over 20 bars)
        sigs_20 = []
        for k in range(20):
            ii = ci - k
            if ii < 60:
                break
            sigs_20.append(np.sign(closes[ii] - closes[ii-60]))
        tf_std = float(np.std(sigs_20)) if len(sigs_20) >= 5 else 0.0

        # C4: range position
        if ci < 20:
            range_pos = 0.5
        else:
            h20b = float(np.max(highs[ci-20: ci+1]))
            l20 = float(np.min(lows[ci-20: ci+1]))
            range_pos = (float(closes[ci]) - l20) / (h20b - l20 + 1e-12)

        return rvol24, dist_high, tf_std, range_pos
    except Exception:
        return 0.0, 0.0, 0.0, 0.5


def _rule_count_matches(sig, ad) -> int:
    """Count how many failure rules match."""
    if not _RULE_THRESHOLDS:
        return 0
    rvol24, dist_high, tf_std, range_pos = _rule_compute_features(sig, ad)
    rvol24_q33 = _RULE_THRESHOLDS['rvol24'][0]
    dist_high_q66 = _RULE_THRESHOLDS['dist_high'][1]
    tf_std_q66 = _RULE_THRESHOLDS['tf_std'][1]
    range_pos_q66 = _RULE_THRESHOLDS['range_pos'][1]

    count = 0
    if rvol24_q33 is not None and rvol24 < rvol24_q33: count += 1
    if dist_high_q66 is not None and dist_high > dist_high_q66: count += 1
    if tf_std_q66 is not None and tf_std > tf_std_q66: count += 1
    if range_pos_q66 is not None and range_pos > range_pos_q66: count += 1
    return count


def filter_signals_rules(signals, assets) -> List:
    """
    Rule-based filter. No ML.
    Rejects signals where >= RULE_MIN_SCORE failure rules match.
    """
    if not CFG.RULE_FILTER_ENABLED or not _RULE_THRESHOLDS:
        return signals

    kept = []
    rejected = 0
    for sig in signals:
        ad = assets.get(sig.symbol)
        if ad is None:
            kept.append(sig)
            continue
        try:
            n_match = _rule_count_matches(sig, ad)
        except Exception:
            kept.append(sig)
            continue
        if n_match >= CFG.RULE_MIN_SCORE:
            rejected += 1
            continue
        kept.append(sig)

    total = len(signals)
    pct = 100.0 * rejected / max(total, 1)
    log.info(f"[RuleFilter] kept={len(kept)}, rejected={rejected} "
             f"({pct:.1f}%) @ min_score={CFG.RULE_MIN_SCORE}")
    return kept

def filter_signals_ml(signals, assets):
    """
    Optional ML filter. If disabled or model missing → no-op (returns all signals).
    Rejects signals with P_win < CFG.ML_FILTER_THRESHOLD.
    """
    if not CFG.ML_FILTER_ENABLED or _ML_MODEL is None or _ML_SCALER is None:
        return signals

    kept, rejected = [], 0
    for sig in signals:
        ad = assets.get(sig.symbol)
        if ad is None:
            kept.append(sig)
            continue
        try:
            feat = _extract_ml_features(sig, ad)[:_ML_EXPECTED_N].reshape(1, -1)
            feat_s = _ML_SCALER.transform(feat)
            p_win = float(_ML_MODEL.predict_proba(feat_s)[0, 1])
        except Exception:
            kept.append(sig)
            continue
        if p_win >= CFG.ML_FILTER_THRESHOLD:
            kept.append(sig)
        else:
            rejected += 1

    total = len(signals)
    pct = 100.0 * rejected / max(total, 1)
    log.info(f"[ML] Filter: kept={len(kept)}, rejected={rejected} "
             f"({pct:.1f}%) @ threshold={CFG.ML_FILTER_THRESHOLD:.3f}")
    return kept

def run_backtest(cfg):
    try:
        import ccxt
    except ImportError:
        log.error("pip install ccxt"); return

    exchange = ccxt.binance({'enableRateLimit':True,'options':{'defaultType':'future'}})

    log.info("§1  مسح أعلى 15 عملة...")
    syms = scan_top_assets(exchange, cfg.n_assets)

    log.info("§2  جلب البيانات (متوازٍ)...")
    # ══ [SUB-BARS] Fetch main + sub together ══
    raw, raw_sub = fetch_all_with_subbars(
        syms, exchange, cfg.timeframe, cfg.history_days, workers=5
    )

    # ══ [FIX-01-PROPER] Prefetch leverage tiers for all symbols ══
    try:
        prefetch_all_leverage_tiers(exchange, list(raw.keys()))
    except Exception as _e:
        log.warning(f"[LevTiers] backtest prefetch failed: {_e}")

    if not raw: log.error("لا بيانات."); return
    if raw_sub:
        _sub_tf_used = _get_subbars_tf(cfg.timeframe) or "?"
        log.info(f"  [SubBars] loaded for {len(raw_sub)} symbols at {_sub_tf_used}")
    else:
        log.info("  [SubBars] disabled or unavailable — using main-bar logic")

    log.info("§3  معالجة فضاء الحالة (K ديناميكي)...")
    assets: Dict[str, AssetData] = {}

    # Snapshot CFG (must be pickleable — plain dict of primitives)
    cfg_dict = {k: v for k, v in cfg.__dict__.items()}

    t_start = time.time()

    if cfg.PARALLEL_PROCESSING and len(raw) > 1:
        n_workers = cfg.PARALLEL_WORKERS or min(
            os.cpu_count() or 4, len(raw)
        )
        log.info(f"  [Parallel] {n_workers} workers × {len(raw)} symbols "
                 f"(cache={'on' if cfg.ASSET_CACHE_ENABLED else 'off'})")

        tasks = [
            (sym, df, cfg.INITIAL_CAPITAL, cfg.timeframe, cfg_dict,
             raw_sub.get(sym) if raw_sub else None)
            for sym, df in raw.items()
        ]

        n_cache_hits = 0
        n_computed = 0
        n_errors = 0

        import multiprocessing as mp
        # 'spawn' avoids OpenMP/sklearn fork hazards at the cost of ~0.5s/worker startup
        _mp_ctx = mp.get_context('spawn')

        with ProcessPoolExecutor(
            max_workers=n_workers,
            mp_context=_mp_ctx,
            initializer=_worker_init,
            initargs=(cfg_dict,)
        ) as ex:
            futures = [ex.submit(_process_asset_worker, t) for t in tasks]
            crashed_syms: List[str] = []

            for fut in as_completed(futures):
                sym_guess = None
                try:
                    sym, ad, err, source = fut.result()
                    sym_guess = sym
                except Exception as e:
                    # Future's symbol is not directly accessible — we handle
                    # via the crashed_syms list populated below
                    log.warning(f"  ✗ worker crashed: {e}")
                    n_errors += 1
                    # We can't recover the symbol here; record failure for serial retry pass
                    crashed_syms.append(None)
                    continue

                if err:
                    log.warning(f"  ✗ {sym}: {err.splitlines()[0]}")
                    n_errors += 1
                    continue
                if ad is None:
                    log.warning(f"  ✗ {sym}: process_asset returned None")
                    n_errors += 1
                    continue

                assets[sym] = ad
                if source == 'cache':
                    n_cache_hits += 1
                else:
                    n_computed += 1

                nt = int(np.sum(ad.score[ad.train_end:] >= cfg.MIN_SCORE))
                log.info(f"  ✓ {sym:14s} | K={ad.dynamic_k} | "
                         f"اختبار={nt:5,} | tri_μ={np.mean(ad.tri):.2f} "
                         f"| [{source}]")

        elapsed = time.time() - t_start
        log.info(f"  [Parallel] done in {elapsed:.1f}s  "
                 f"(cache={n_cache_hits}, computed={n_computed}, errors={n_errors})")

    else:
        # Serial path (fallback when parallel disabled or single symbol)
        log.info("  [Serial] processing symbols one-by-one")
        for sym, df in raw.items():
            ad = _load_asset_cache(sym, cfg.timeframe, df, cfg)
            source = 'cache'

            if ad is None:
                _sb = raw_sub.get(sym) if raw_sub else None
                ad = process_asset(sym, df,
                                    current_capital=cfg.INITIAL_CAPITAL,
                                    sub_df=_sb)
                source = 'computed'
                if ad is not None:
                    _save_asset_cache(sym, cfg.timeframe, df, ad, cfg)

            if ad:
                assets[sym] = ad
                nt = int(np.sum(ad.score[ad.train_end:] >= cfg.MIN_SCORE))
                log.info(f"  ✓ {sym:14s} | K={ad.dynamic_k} | "
                         f"اختبار={nt:5,} | tri_μ={np.mean(ad.tri):.2f} "
                         f"| [{source}]")

        elapsed = time.time() - t_start
        log.info(f"  [Serial] done in {elapsed:.1f}s")

    log.info("§4  مصفوفة الارتباط...")
    corr_matrix = precompute_correlations(assets)
    n_pairs = sum(1 for v in corr_matrix.values() if v > cfg.CORRELATION_THRESHOLD)
    log.info(f"  أزواج مرتبطة (ρ>{cfg.CORRELATION_THRESHOLD}): {n_pairs//2}")

    log.info("§5  بناء الإشارات (①②④⑤ مُفعَّلة)...")
    # ══ [FILTER] إعادة تعيين العدّاد قبل البناء ══
    _filter_reset_stats()
    sigs = build_signals(assets)
    sigs = deduplicate_signals(sigs)


    # ══ [SING-TIMING] تقرير حالة الرنين على الإشارات ══
    if getattr(CFG, 'SING_TIMING_ENABLED', False):
        _sng_stats = {"DORMANT": 0, "EMERGING": 0, "ACTIVE": 0,
                       "DECAYING": 0, "INVALID": 0}
        for _s in sigs:
            _ad_s = assets.get(_s.symbol)
            if _ad_s is None:
                continue
            try:
                _st, _ = _resonance_state_for_direction(
                    _ad_s, int(_s.feat_idx), _s.action, CFG
                )
                _sng_stats[_st] = _sng_stats.get(_st, 0) + 1
            except Exception:
                pass
        _tot = sum(_sng_stats.values()) or 1
        log.info(f"  [Sing-Timing] Distribution on signals:")
        for _st_name, _cnt in _sng_stats.items():
            log.info(f"    {_st_name:10s}: {_cnt:5d} "
                     f"({_cnt/_tot*100:.1f}%)")

    # ══ [Rule Filter] ══
    if CFG.RULE_FILTER_ENABLED:
        compute_rule_thresholds(assets)
        sigs = filter_signals_rules(sigs, assets)

    if CFG.ML_FILTER_ENABLED:
        sigs = filter_signals_ml(sigs, assets)

    log.info(f"  ✔ {len(sigs):,} إشارة")

    # إحصاء T_info للإشارات
    T_vals = [s.T_info_val for s in sigs]
    dr_vals = [s.dynamic_risk for s in sigs]
    buy_sigs = sum(1 for s in sigs if s.action=="BUY")
    sell_sigs = sum(1 for s in sigs if s.action=="SELL")
    log.info(f"  T_info: μ={np.mean(T_vals):.3f} | σ={np.std(T_vals):.3f}")
    log.info(f"  risk_dynamic: μ={np.mean(dr_vals)*100:.3f}% | max={max(dr_vals)*100:.2f}%")
    log.info(f"  BUY={buy_sigs:,} | SELL={sell_sigs:,} (Λ={cfg.COSMOLOGICAL_CONSTANT})")

    log.info("§6  محاكاة المحفظة متعددة المراكز...")
    trades, equity = simulate_portfolio(sigs, assets, corr_matrix, "backtest")
    log.info(f"  ✔ {len(trades):,} صفقة")
    # [UNIFIED-BT] stats logger
    try:
        _unified_log_stats()
    except Exception as _se:
        log.debug(f"[Unified-BT] stats failed: {_se}")

    m = compute_metrics(trades, equity, cfg.INITIAL_CAPITAL)

    if m.get('n_trades', 0) == 0:
        log.warning("⚠️ No trades generated — check signal filters / config")
        print_report(m, "backtest")
        return

    log.info("§7  انحدار الإنتروبيا...")
    for sym, ad in list(assets.items())[:4]:
        H_t = ad.H[ad.train_end:]
        if len(H_t)>10:
            r = entropy_regression(H_t)
            log.info(f"  {sym:14s}: b={r['slope']:+.5f}  R²={r['r2']:.3f}  [{r['trend']}]")

    print_report(m, "backtest")
    plot_results(trades, equity, m)

    # ══ [Cache-Health] تقرير نهائي ══
    if _CACHE_HEALTH['files_scanned'] > 0:
        log.info(
            f"[Cache-Health] Session summary: "
            f"scanned={_CACHE_HEALTH['files_scanned']} files, "
            f"local_fixes={_CACHE_HEALTH['issues_fixed_local']} issues, "
            f"gaps={_CACHE_HEALTH['gaps_found']}, "
            f"bars_refetched={_CACHE_HEALTH['bars_refetched']}, "
            f"files_rewritten={_CACHE_HEALTH['files_saved']}"
        )

    log.info("✅ اكتمل.")
    log.info(f"   E[ln(1+fR)] = {m.get('mean_log_return',0):+.6f}")
    log.info(f"   MaxDrawdown  = {m.get('max_drawdown_pct',0):.2f}%")
    log.info(f"   Topo-Exits   = {m.get('topo_exit_pct',0):.1f}%")
    log.info(f"   AvgRisk      = {m.get('avg_dynamic_risk',0)*100:.3f}%")
    # ══ [MFE Analysis] ══
    if not trades:
        log.info("[MFE] skipped — no trades")
        return
    sl_trades = [t for t in trades if "Emergency SL" in t.exit_reason]
    tp_trades = [t for t in trades if "Hard TP" in t.exit_reason]
    apex_trades = [t for t in trades if "Apex" in t.exit_reason]

    print(f"\n▶ تحليل MFE (أقصى ربح غير مُحقَّق)")
    for label, grp in [("Emergency SL", sl_trades),
                       ("Hard TP",      tp_trades),
                       ("Apex exits",   apex_trades)]:
        if not grp:
            continue
        mfes = [t.mfe_frac for t in grp]
        over_05 = sum(1 for m in mfes if m > 0.005)
        over_10 = sum(1 for m in mfes if m > 0.010)
        over_20 = sum(1 for m in mfes if m > 0.020)
        print(f"   {label:14s} (n={len(grp):4d}) | "
              f"μMFE={np.mean(mfes)*100:5.2f}%  "
              f"max={np.max(mfes)*100:5.2f}%  | "
              f">0.5%: {over_05:4d}  "
              f">1.0%: {over_10:4d}  "
              f">2.0%: {over_20:4d}")
    # ══ [Portfolio Budget Report] ══
    if trades:
        risks = [t.dynamic_risk_used for t in trades]
        print(f"\n▶ ميزانية المخاطرة الكلية")
        print(f"   μ risk/trade : {np.mean(risks)*100:.3f}%")
        print(f"   max risk/trade : {np.max(risks)*100:.3f}%")
        print(f"   min risk/trade : {np.min(risks)*100:.3f}%")

    # ══ [DIAGNOSTIC] Check for close-and-reverse patterns ══
    from collections import defaultdict as _dd
    by_sym_trades = _dd(list)
    for _t in trades:
        by_sym_trades[_t.symbol].append(_t)
    reversals = 0
    for _sym, _lst in by_sym_trades.items():
        _lst.sort(key=lambda x: x.entry_time)
        for _i in range(1, len(_lst)):
            _prev = _lst[_i-1]
            _curr = _lst[_i]
            if (_prev.action != _curr.action
                    and (_curr.entry_time - _prev.entry_time).total_seconds() < 3 * 3600):
                reversals += 1
    log.info(f"[Diagnostic] Close-and-reverse within 3h: {reversals}")
    if reversals > len(trades) * 0.05:
        log.warning(f"[Diagnostic] HIGH REVERSAL RATE: {reversals}/{len(trades)}")

# ════════════════════════════════════════════════════════════════
# § 18.6  Fill Engine v1 Helpers (Adaptive Maker Execution)
# ════════════════════════════════════════════════════════════════

def compute_adaptive_delta(sigma_1m: float, fill_target: float = 0.90,
                            timeout_s: float = 30.0) -> float:
    """
    Solve for delta (fraction) such that:
      P(|price move| > delta within timeout_s) = fill_target.
    Brownian: sigma_T = sigma_1m * sqrt(T/60).
    """
    sigma_T = sigma_1m * np.sqrt(max(timeout_s, 1.0) / 60.0)
    z = -norm.ppf(1.0 - fill_target / 2.0)
    return float(max(z * sigma_T, 1e-6))


def recent_sigma_bps(ad, current_ci: int, window: int = 60) -> float:
    """Recent 1m volatility as a fraction (not bps)."""
    if current_ci < window + 1:
        return 8e-4
    closes = ad.closes[current_ci - window: current_ci]
    if len(closes) < 3:
        return 8e-4
    lr = np.diff(np.log(np.maximum(closes, 1e-12)))
    s = float(np.std(lr))
    if not np.isfinite(s) or s <= 0:
        return 8e-4
    return s


def build_ladder(mid: float, sigma_1m: float, total_qty: float,
                 side: str, spread: float):
    """Split qty into 3 levels at [1-tick, 2-tick, 3-tick] from best side."""
    tick = max(spread / 2.0, mid * 1e-6)
    weights = CFG.FILL_LADDER_WEIGHTS
    levels = []
    for i, w in enumerate(weights):
        price = (mid - (i + 1) * tick) if side == 'buy' else (mid + (i + 1) * tick)
        q = total_qty * w
        if q > 0:
            levels.append({'price': float(price), 'qty': float(q)})
    return levels


def signal_still_valid(ad, sig, current_ci: int, max_age_bars: int = 3):
    """
    Check signal validity by comparing CURRENT market vs ORIGINAL market
    (at signal time), not vs the signal's entry target (which is offset by design).
    """
    # 1. Age check
    if current_ci - sig.close_idx > max_age_bars:
        return False, f"signal_too_old (age={current_ci - sig.close_idx})"

    if current_ci >= len(ad.closes) or sig.close_idx >= len(ad.closes):
        return False, "ci_out_of_range"

    price_now = float(ad.closes[current_ci])
    price_at_sig = float(ad.closes[sig.close_idx])
    if price_at_sig <= 0:
        return False, "invalid_sig_price"

    move_frac = (price_now - price_at_sig) / price_at_sig

    # ══ [TF-FIX] σ-scaled thresholds instead of fixed percentages ══
    # Local per-bar sigma at signal time (from ad.E_therm)
    try:
        _sig_fi = getattr(sig, 'feat_idx', None)
        if _sig_fi is not None and 0 <= _sig_fi < len(ad.E_therm):
            sigma_bar = float(ad.E_therm[_sig_fi])
        else:
            sigma_bar = 0.01
        if not np.isfinite(sigma_bar) or sigma_bar <= 1e-6:
            sigma_bar = 0.01
    except Exception:
        sigma_bar = 0.01

    # κ units (dimensionless) — reproduce 2%/3% on 1h where σ_bar ≈ 1%
    KAPPA_UP = 2.0
    KAPPA_DN = 3.0
    thr_up = KAPPA_UP * sigma_bar
    thr_dn = KAPPA_DN * sigma_bar

    if sig.action == "BUY":
        if move_frac > thr_up:
            return False, (f"rallied {move_frac*100:+.2f}% "
                           f"(> {KAPPA_UP}σ={thr_up*100:.2f}%) — dip unreachable")
        if move_frac < -thr_dn:
            return False, (f"collapsed {move_frac*100:+.2f}% "
                           f"(< -{KAPPA_DN}σ={-thr_dn*100:.2f}%) — momentum broken")
    else:  # SELL
        if move_frac < -thr_up:
            return False, (f"crashed {move_frac*100:+.2f}% "
                           f"(< -{KAPPA_UP}σ={-thr_up*100:.2f}%) — bounce unreachable")
        if move_frac > thr_dn:
            return False, (f"rallied {move_frac*100:+.2f}% "
                           f"(> {KAPPA_DN}σ={thr_dn*100:.2f}%) — momentum broken")

    # 3. Optional MR z-degradation check (only if field exists)
    mr_z = getattr(ad, 'mr_z', None)
    if mr_z is not None and current_ci < len(mr_z) and np.isfinite(mr_z[current_ci]):
        z_now = float(mr_z[current_ci])
        if abs(sig.score) > 0.5 and abs(z_now) < abs(sig.score) * 0.3:
            return False, f"signal_degraded (z={z_now:.2f} vs {sig.score:.2f})"

    return True, "OK"


def verify_fill_sync(exchange, order_id, symbol, timeout_s: float = 2.0):
    """Poll order until closed/canceled or timeout."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            o = exchange.fetch_order(order_id, symbol)
            st = o.get('status')
            if st == 'closed':
                return {
                    'filled': True,
                    'qty': float(o.get('filled') or 0.0),
                    'price': float(o.get('average') or o.get('price') or 0.0),
                    'status': 'closed'
                }
            if st in ('canceled', 'expired', 'rejected'):
                return {'filled': False, 'qty': 0.0, 'price': 0.0, 'status': st}
        except Exception as e:
            log.debug(f"[VerifyFill] fetch_order {order_id} failed: {e}")
        time.sleep(0.1)
    return {'filled': False, 'qty': 0.0, 'price': 0.0, 'status': 'timeout'}

# ════════════════════════════════════════════════════════════════
# § 18.65  Microstructure Tracking Layer
# ════════════════════════════════════════════════════════════════

@dataclass
class MicroState:
    ts: float
    mid: float
    micro_price: float
    fair_price: float
    fair_uncertainty: float
    spread: float
    spread_bps: float
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    imbalance: float          # (bid_sz - ask_sz) / (bid_sz + ask_sz)
    ofi: float                # order flow imbalance (book-delta based)
    trade_intensity: float    # trades per second (rolling)
    sigma_fast: float         # bps, very short horizon
    sigma_slow: float         # bps, 1m horizon
    book_pressure: float      # weighted depth ratio bid/ask
    depth_bid_5: float
    depth_ask_5: float
    toxic_score: float        # 0..1, higher = more toxic flow


class MicroTracker:
    """
    Tracks book snapshots and trade prints, computes MicroState online.
    Thread-safe enough for single-threaded run_live loops.
    """
    def __init__(self, alpha_fair: float = 0.15, max_hist: int = 200):
        self.alpha_fair = alpha_fair
        self.max_hist = max_hist
        self._book_hist: List[Dict] = []      # recent book snapshots
        self._trade_hist: List[Tuple[float, float, float]] = []  # (ts, price, qty)
        self._fair_price: Optional[float] = None
        self._fair_var: float = 0.0
        self._last_ts: Optional[float] = None

    def _prune(self, now: float):
        cutoff_book = now - 30.0
        cutoff_trade = now - 30.0
        while self._book_hist and self._book_hist[0]['ts'] < cutoff_book:
            self._book_hist.pop(0)
        while self._trade_hist and self._trade_hist[0][0] < cutoff_trade:
            self._trade_hist.pop(0)

    def update_book(self, ob: Dict, now: Optional[float] = None) -> None:
        now = now or time.time()
        try:
            bids = ob.get('bids') or []
            asks = ob.get('asks') or []
            if not bids or not asks:
                return
            bid, bid_sz = float(bids[0][0]), float(bids[0][1])
            ask, ask_sz = float(asks[0][0]), float(asks[0][1])
            depth_bid_5 = sum(float(x[1]) for x in bids[:5])
            depth_ask_5 = sum(float(x[1]) for x in asks[:5])
            snap = {
                'ts': now, 'bid': bid, 'ask': ask,
                'bid_sz': bid_sz, 'ask_sz': ask_sz,
                'depth_bid_5': depth_bid_5, 'depth_ask_5': depth_ask_5,
            }
            self._book_hist.append(snap)
            if len(self._book_hist) > self.max_hist:
                self._book_hist = self._book_hist[-self.max_hist:]
            self._prune(now)
        except Exception as e:
            log.debug(f"[MicroTracker] update_book failed: {e}")

    def update_trades(self, trades: List[Dict], now: Optional[float] = None) -> None:
        """trades: list of {'price','amount','side' or 'timestamp'}"""
        now = now or time.time()
        for t in trades:
            try:
                ts = float(t.get('timestamp', now)) / 1000.0 if t.get('timestamp') else now
                p = float(t.get('price') or 0)
                q = float(t.get('amount') or 0)
                if p > 0 and q > 0:
                    self._trade_hist.append((ts, p, q))
            except Exception as e:
                log.debug(f"[MicroTracker] update_trades item failed: {e}")
        if len(self._trade_hist) > 5000:
            self._trade_hist = self._trade_hist[-5000:]
        self._prune(now)

    def state(self, now: Optional[float] = None) -> Optional[MicroState]:
        now = now or time.time()
        if not self._book_hist:
            return None
        last = self._book_hist[-1]

        bid, ask = last['bid'], last['ask']
        mid = (bid + ask) / 2.0
        spread = max(ask - bid, 1e-12)

        # Micro-price (Stoikov): weighted by opposite-side size
        bsz, asz = last['bid_sz'], last['ask_sz']
        denom = bsz + asz + 1e-12
        micro_price = (bid * asz + ask * bsz) / denom

        # Imbalance
        imbalance = (bsz - asz) / denom

        # Book pressure over 5 levels
        db5, da5 = last['depth_bid_5'], last['depth_ask_5']
        book_pressure = (db5 - da5) / (db5 + da5 + 1e-12)

        # Order Flow Imbalance: delta in best-level sizes
        ofi = 0.0
        if len(self._book_hist) >= 2:
            prev = self._book_hist[-2]
            ofi = ((last['bid_sz'] - prev['bid_sz']) -
                   (last['ask_sz'] - prev['ask_sz']))

        # Recent trade intensity (last 5s)
        t5 = [t for t in self._trade_hist if t[0] >= now - 5.0]
        trade_intensity = len(t5) / 5.0

        # Fast sigma (last 5s) from trade prices
        sigma_fast = 8.0  # default bps
        if len(t5) >= 3:
            prices = np.array([t[1] for t in t5])
            if len(prices) >= 2:
                lr = np.diff(np.log(prices))
                sigma_fast = float(np.std(lr) * 1e4)

        # Slow sigma (last 60s)
        t60 = [t for t in self._trade_hist if t[0] >= now - 60.0]
        sigma_slow = sigma_fast
        if len(t60) >= 5:
            prices = np.array([t[1] for t in t60])
            lr = np.diff(np.log(prices))
            sigma_slow = max(float(np.std(lr) * 1e4), 1.0)

        # Kalman-lite fair price update
        if self._fair_price is None:
            self._fair_price = micro_price
            self._fair_var = (spread / 2.0) ** 2
        else:
            pred = self._fair_price
            pred_var = self._fair_var + (sigma_fast * mid / 1e4) ** 2
            K = pred_var / (pred_var + (spread / 2.0) ** 2 + 1e-12)
            self._fair_price = pred + K * (micro_price - pred)
            self._fair_var = (1 - K) * pred_var

        # Toxic score: OFI sign vs imbalance sign agreement + magnitude
        # If OFI strongly negative (sellers hitting) AND imbalance negative
        # (bids thinning), that's toxic SELL flow, bad for our BUY quotes.
        norm_ofi = np.tanh(ofi / (bsz + asz + 1e-12) * 5.0)
        toxic_score = float(np.clip(abs(norm_ofi) * (0.5 + 0.5 * abs(imbalance)), 0, 1))

        return MicroState(
            ts=now, mid=mid, micro_price=micro_price,
            fair_price=self._fair_price,
            fair_uncertainty=float(np.sqrt(self._fair_var)),
            spread=spread, spread_bps=spread / mid * 1e4,
            bid=bid, ask=ask, bid_size=bsz, ask_size=asz,
            imbalance=imbalance, ofi=ofi,
            trade_intensity=trade_intensity,
            sigma_fast=sigma_fast, sigma_slow=sigma_slow,
            book_pressure=book_pressure,
            depth_bid_5=db5, depth_ask_5=da5,
            toxic_score=toxic_score
        )


def estimate_queue_position(micro: MicroState, our_price: float,
                             side: str, our_size: float) -> float:
    """
    Estimate our position in the queue at our_price.
    Returns fraction in [0,1]: 0 = front of queue, 1 = back.
    Simplified: assume we join behind all current depth at that price.
    """
    if side == 'buy':
        # If our_price >= bid, we join at the top -> queue behind existing bid_sz
        if our_price >= micro.bid:
            depth_ahead = micro.bid_size
        else:
            # Deeper than best bid — likely deeper depth, assume moderate
            depth_ahead = micro.bid_size * 0.5
    else:
        if our_price <= micro.ask:
            depth_ahead = micro.ask_size
        else:
            depth_ahead = micro.ask_size * 0.5
    total = depth_ahead + our_size + 1e-12
    return float(np.clip(depth_ahead / total, 0.0, 1.0))


def estimate_fill_probability(delta_bps: float, sigma_bps: float,
                              horizon_s: float, queue_pos: float,
                              intensity: float) -> float:
    """
    Fill probability for a maker order at distance delta_bps from fair.
    - Brownian touch: P(touch) = 2*Phi(-delta / sigma_T) - 1  approx
    - Queue penalty: multiply by (1 - queue_pos)
    - Intensity boost: more trades = faster queue consumption
    """
    if delta_bps <= 0:
        return 0.99
    sigma_T = max(sigma_bps, 0.5) * np.sqrt(max(horizon_s, 1.0) / 60.0)
    z = -delta_bps / sigma_T
    touch = 2.0 * norm.cdf(z)
    # Intensity factor: higher trade rate → faster queue consumption
    inten_factor = 1.0 - np.exp(-max(intensity, 0.1) * horizon_s / 5.0)
    # Combined
    p = (1.0 - queue_pos) * touch * (0.5 + 0.5 * inten_factor)
    return float(np.clip(p, 0.0, 0.99))


def urgency_kappa(t_elapsed: float, t_total: float, kappa: float) -> float:
    """Exponential urgency: fast approach to mid as time runs out."""
    if t_total <= 0:
        return 1.0
    frac = t_elapsed / t_total
    return float(1.0 - np.exp(-kappa * frac))

_TICK_SIZE_CACHE: Dict[str, float] = {}

# ══ [FIX-4.2/4.3] Step size + MIN_NOTIONAL enforcement ══
_STEP_SIZE_CACHE: Dict[str, float] = {}
_MIN_NOTIONAL_CACHE: Dict[str, float] = {}


def _get_step_size(exchange, symbol: str) -> float:
    """Lot size filter — smallest order qty step."""
    if symbol in _STEP_SIZE_CACHE:
        return _STEP_SIZE_CACHE[symbol]
    try:
        mkt = exchange.market(symbol)
        info = mkt.get('info') or {}
        for f in (info.get('filters') or []):
            if f.get('filterType') in ('LOT_SIZE', 'MARKET_LOT_SIZE'):
                step = float(f.get('stepSize', 0))
                if step > 0:
                    _STEP_SIZE_CACHE[symbol] = step
                    return step
    except Exception:
        pass
    _STEP_SIZE_CACHE[symbol] = 1e-6
    return 1e-6


def _get_min_notional(exchange, symbol: str) -> float:
    """MIN_NOTIONAL filter — minimum order value in USDT."""
    if symbol in _MIN_NOTIONAL_CACHE:
        return _MIN_NOTIONAL_CACHE[symbol]
    try:
        mkt = exchange.market(symbol)
        info = mkt.get('info') or {}
        for f in (info.get('filters') or []):
            if f.get('filterType') == 'MIN_NOTIONAL':
                mn = float(f.get('notional', 5.0))
                _MIN_NOTIONAL_CACHE[symbol] = mn
                return mn
    except Exception:
        pass
    _MIN_NOTIONAL_CACHE[symbol] = 5.0
    return 5.0


def _round_qty(exchange, symbol: str, qty: float) -> float:
    """Round qty down to valid step size."""
    step = _get_step_size(exchange, symbol)
    if step <= 0 or qty <= 0:
        return qty
    import math
    return math.floor(qty / step) * step


def _round_price(exchange, symbol: str, price: float, side: str) -> float:
    """Round price to tick size in the correct direction."""
    tick = _get_tick_size(exchange, symbol) or 1e-8
    if tick <= 0 or price <= 0:
        return price
    import math
    if side == 'buy':
        return math.floor(price / tick) * tick
    else:
        return math.ceil(price / tick) * tick


def _get_tick_size(exchange, symbol: str) -> Optional[float]:
    """
    Fetch and cache price tick size for a symbol.

    Priority:
      1. Binance PRICE_FILTER.tickSize (canonical for futures).
      2. ccxt precision['price'] if it's a positive float.

    Returns None if unavailable — caller must fall back to bps math.
    """
    if symbol in _TICK_SIZE_CACHE:
        return _TICK_SIZE_CACHE[symbol]
    try:
        mkt = exchange.market(symbol)
    except Exception:
        return None
    if not mkt:
        return None

    info = mkt.get('info') or {}
    for f in (info.get('filters') or []):
        if isinstance(f, dict) and f.get('filterType') == 'PRICE_FILTER':
            try:
                ts = float(f.get('tickSize', 0))
                if ts > 0 and np.isfinite(ts):
                    _TICK_SIZE_CACHE[symbol] = ts
                    return ts
            except Exception:
                pass

    prec = (mkt.get('precision') or {}).get('price')
    if prec is not None:
        try:
            ts = float(prec)
            if ts > 0 and np.isfinite(ts):
                _TICK_SIZE_CACHE[symbol] = ts
                return ts
        except Exception:
            pass
    return None

# ════════════════════════════════════════════════════════════════
# [LIQ AWARENESS] — MMR fetching + liquidation math
# ════════════════════════════════════════════════════════════════

_MMR_CACHE: Dict[str, float] = {}


def _get_mmr_for_symbol(exchange, symbol: str) -> float:
    """
    Maintenance margin rate for a symbol.
    - Cached per session.
    - Returns tier-0 (smallest notional) MMR, since our positions are small.
    - Falls back to CFG.LIQ_FALLBACK_MMR on any failure.
    """
    if symbol in _MMR_CACHE:
        return _MMR_CACHE[symbol]
    try:
        tiers = exchange.fetch_leverage_tiers([symbol])
        if tiers and len(tiers) > 0:
            t0 = tiers[0]
            tiers_list = t0.get('tiers', []) or []
            if tiers_list:
                mmr = float(tiers_list[0].get('maintenanceMarginRate', 0))
                if mmr > 0:
                    _MMR_CACHE[symbol] = mmr
                    return mmr
    except Exception as e:
        log.debug(f"[MMR] fetch failed for {symbol}: {e}")
    _MMR_CACHE[symbol] = float(getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
    return _MMR_CACHE[symbol]


def compute_liquidation_price(entry: float, side: str,
                                leverage: int, mmr: float) -> float:
    """
    Binance isolated-margin liquidation price.

    Derivation (LONG):
        margin + (Liq - Entry) × qty = MMR × Liq × qty
        Entry/L + Liq - Entry = MMR × Liq
        Liq × (1 - MMR) = Entry × (1 - 1/L)
        Liq = Entry × (1 - 1/L) / (1 - MMR)

    SHORT by symmetry:
        Liq = Entry × (1 + 1/L) / (1 + MMR)
    """
    L = max(int(leverage), 1)
    m = max(float(mmr), 0.0)
    if side == "BUY":
        return float(entry * (1.0 - 1.0 / L) / max(1.0 - m, 1e-6))
    else:
        return float(entry * (1.0 + 1.0 / L) / max(1.0 + m, 1e-6))


# Binance USDT-M valid leverage tiers
_BINANCE_LEVERAGE_TIERS = (1, 2, 3, 5, 10, 20, 25, 50, 75, 100, 125)


# ═════════════════════════════════════════════════════════════════
# [FIX-01-PROPER] Per-symbol leverage tiers
# ═════════════════════════════════════════════════════════════════
# Cache:  symbol → (max_leverage, [valid_tiers])
# Populated:
#   * Live:     lazily inside ensure_symbol_setup()
#   * Backtest: eagerly inside prefetch_all_leverage_tiers()
# Fallback:   standard Binance ladder clipped to cfg.LEVERAGE_MAX.
# ═════════════════════════════════════════════════════════════════

_SYMBOL_LEV_TIERS: Dict[str, Tuple[int, List[int]]] = {}

# Static fallback table for well-known symbols. Used when the exchange
# cannot be queried (offline backtest with cached data, etc.).
_STATIC_MAX_LEVERAGE: Dict[str, int] = {
    "BTC/USDT": 125,  "ETH/USDT": 100,  "BNB/USDT": 75,
    "SOL/USDT": 50,   "XRP/USDT": 50,   "DOGE/USDT": 50,
    "ADA/USDT": 50,   "AVAX/USDT": 50,  "LINK/USDT": 50,
    "DOT/USDT": 50,   "LTC/USDT": 50,   "UNI/USDT": 50,
    "ATOM/USDT": 50,  "ETC/USDT": 50,   "TRX/USDT": 50,
    "TON/USDT": 50,   "BCH/USDT": 50,   "NEAR/USDT": 50,
    "APT/USDT": 50,   "HBAR/USDT": 50,  "AAVE/USDT": 50,
    "ARB/USDT": 50,   "OP/USDT": 50,    "SUI/USDT": 50,
    "TIA/USDT": 50,   "SEI/USDT": 50,   "ALGO/USDT": 50,
    "GRT/USDT": 50,   "FET/USDT": 50,   "RENDER/USDT": 50,
    "LDO/USDT": 50,   "KAS/USDT": 50,   "WIF/USDT": 50,
    "THETA/USDT": 50, "SAND/USDT": 50,  "MANA/USDT": 50,
    "AXS/USDT": 50,   "XLM/USDT": 50,   "CHZ/USDT": 50,
    "POL/USDT": 50,   "FIL/USDT": 50,   "QNT/USDT": 50,
    "DASH/USDT": 50,  "STX/USDT": 50,   "MKR/USDT": 50,
}


def _standard_ladder(max_lev: int) -> List[int]:
    """Binance's standard leverage ladder clipped to max_lev."""
    ladder = (1, 2, 3, 5, 10, 20, 25, 50, 75, 100, 125)
    out = [t for t in ladder if t <= int(max_lev)]
    if not out:
        out = [int(max_lev)]
    return out


def _register_leverage_tiers(symbol: str, max_lev: int) -> None:
    """Cache the max leverage and valid tiers for a symbol."""
    max_lev = int(max_lev)
    if max_lev <= 0:
        return
    _SYMBOL_LEV_TIERS[symbol] = (max_lev, _standard_ladder(max_lev))


def _fallback_max_leverage(symbol: str, cfg) -> int:
    """Static fallback when the exchange is not available."""
    if symbol in _STATIC_MAX_LEVERAGE:
        return _STATIC_MAX_LEVERAGE[symbol]
    # Unknown symbol — use the conservative default
    return int(getattr(cfg, 'LEVERAGE_MAX', 50))


def _symbol_tiers(symbol: Optional[str], cfg) -> List[int]:
    """
    Return the valid leverage ladder for a symbol.
    Priority: cache → static table → standard ladder clipped to cfg.LEVERAGE_MAX.
    """
    if symbol and symbol in _SYMBOL_LEV_TIERS:
        return list(_SYMBOL_LEV_TIERS[symbol][1])
    if symbol:
        max_lev = _fallback_max_leverage(symbol, cfg)
        return _standard_ladder(max_lev)
    # No symbol — use CFG.LEVERAGE_MAX as the upper bound
    return _standard_ladder(int(getattr(cfg, 'LEVERAGE_MAX', 50)))


def fetch_symbol_leverage_tiers(exchange, symbol: str) -> Optional[int]:
    """
    Query the exchange for a symbol's max leverage.
    Returns the max leverage (int) or None on failure.
    """
    try:
        tiers = exchange.fetch_leverage_tiers([symbol])
        if not tiers or len(tiers) == 0:
            return None
        t0 = tiers[0]
        tier_list = t0.get('tiers') or []
        if not tier_list:
            return None
        # Binance returns the smallest-notional tier first,
        # which carries the highest leverage.
        max_lev = int(tier_list[0].get('maxLeverage', 0))
        return max_lev if max_lev > 0 else None
    except Exception as e:
        log.debug(f"[LevTiers] fetch failed for {symbol}: {e}")
        return None


def prefetch_all_leverage_tiers(exchange, symbols: List[str]) -> int:
    """
    Populate _SYMBOL_LEV_TIERS for a batch of symbols.
    Called from run_backtest and run_live once at startup.
    Returns count of successfully resolved symbols.
    """
    n_ok = 0
    for sym in symbols:
        if sym in _SYMBOL_LEV_TIERS:
            n_ok += 1
            continue
        max_lev = fetch_symbol_leverage_tiers(exchange, sym)
        if max_lev is not None:
            _register_leverage_tiers(sym, max_lev)
            n_ok += 1
        else:
            fb = _fallback_max_leverage(sym, CFG)
            _register_leverage_tiers(sym, fb)
            log.debug(f"[LevTiers] {sym} using fallback max={fb}x")
    log.info(f"[LevTiers] prefetched tiers for {n_ok}/{len(symbols)} symbols")
    return n_ok



def compute_max_leverage_by_liq(sl_frac_max: float, mmr: float,
                                  safety_mult: float = 1.5,
                                  symbol: Optional[str] = None) -> int:
    """
    Max leverage such that: sl_gap × safety_mult < liq_gap.

    [FIX-01-PROPER] When `symbol` is given, snap to that symbol's
    actual tiers. Falls back to the standard ladder otherwise.
    """
    s = max(sl_frac_max * safety_mult, 1e-6)
    m = max(float(mmr), 0.0)
    denom = 1.0 - (1.0 - m) * (1.0 - s)
    if denom <= 1e-9:
        return 1
    _raw = int(np.floor(1.0 / denom))

    # Symbol-aware ladder
    try:
        tiers = _symbol_tiers(symbol, CFG)
    except Exception:
        tiers = list(_BINANCE_LEVERAGE_TIERS)
    _candidates = [int(t) for t in tiers if int(t) <= _raw]
    if not _candidates:
        return 1
    return int(_candidates[-1])



def _estimate_liq_for_position(pos: dict, default_leverage: int = 10) -> Optional[float]:
    """
    Best-effort Liq estimate for a position dict. Returns None if not feasible.
    Used when backfilling old positions from state files.
    """
    try:
        entry = float(pos.get('entry') or 0)
        side = pos.get('action') or 'BUY'
        if entry <= 0:
            return None
        lev = int(pos.get('leverage') or default_leverage)
        mmr = float(getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
        return compute_liquidation_price(entry, side, lev, mmr)
    except Exception:
        return None

# ════════════════════════════════════════════════════════════════
# [LAYER 7] — Broker-side protective orders (STOP_MARKET + TP)
# ════════════════════════════════════════════════════════════════

_PROTECTIVE_ORDER_TYPES = {"STOP_MARKET", "TAKE_PROFIT_MARKET",
                            "stop_market", "take_profit_market"}


def _is_protective_order(o: Dict) -> bool:
    """True if the order is a protective SL/TP placed by this bot."""
    try:
        t = str(o.get('type') or '').lower()
        return ('stop_market' in t or 'take_profit_market' in t)
    except Exception:
        return False


def _cancel_all_protective_orders(exchange, sym: str,
                                     max_passes: int = 2) -> int:
    """
    Cancel every STOP_MARKET / TAKE_PROFIT_MARKET on the symbol.

    [DUPLICATE-FIX] two-pass cancel: الأولى تلغي، والثانية تتحقق.
    هذا يمنع بقاء نسخة ثانية من الأوامر على البورصة.
    """
    n = 0
    for pass_idx in range(max_passes):
        try:
            open_orders = exchange.fetch_open_orders(sym)
        except Exception as e:
            log.debug(f"[Prot] fetch_open_orders {sym} failed: {e}")
            break
        prot_orders = [o for o in open_orders if _is_protective_order(o)]
        if not prot_orders:
            break
        if pass_idx == 0:
            log.info(f"[Prot] {sym} cancelling {len(prot_orders)} "
                     f"stale protective order(s)")
        for o in prot_orders:
            try:
                exchange.cancel_order(o['id'], sym)
                n += 1
            except Exception as e:
                log.warning(f"[Prot] cancel {sym} oid={o['id']} failed: {e}")
        import time as _t
        _t.sleep(0.3)
    return n


def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:
    """
    Place STOP_MARKET at SL and TAKE_PROFIT_MARKET at TP for the position.

    Design:
      - closePosition=True → Binance auto-sizes and auto-cancels if position
        disappears. No risk of orphan orders when the other side fires.
      - workingType=MARK_PRICE → avoids last-price manipulation and matches
        what Binance uses for liquidation.
      - Fallback to explicit qty + reduceOnly if the exchange rejects
        closePosition (some testnets).
    Returns True on success.
    """
    if not getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        return False
    try:
        action = pos.get('action')
        sl = float(pos.get('sl') or 0)
        tp = float(pos.get('tp1') or 0)
        qty = float(pos.get('qty') or 0)
        if action not in ('BUY', 'SELL') or sl <= 0 or tp <= 0 or qty <= 0:
            return False

        close_side = 'sell' if action == 'BUY' else 'buy'
        wt = str(getattr(CFG, 'PROTECTIVE_WORKING_TYPE', 'MARK_PRICE'))
        max_retries = int(getattr(CFG, 'PROTECTIVE_MAX_RETRIES', 2))

        # Cancel any stale protective orders first (idempotent)
        # [DUPLICATE-FIX] verify cancel before placing
        _canceled_count = _cancel_all_protective_orders(exchange, sym)
        if _canceled_count > 0:
            log.debug(f"[Prot] {sym} canceled {_canceled_count} "
                      f"stale order(s)")
        time.sleep(0.5)
        try:
            _remaining = [o for o in exchange.fetch_open_orders(sym)
                          if _is_protective_order(o)]
            if _remaining:
                log.warning(
                    f"[Prot] {sym} {len(_remaining)} protective "
                    f"order(s) still open after cancel — retrying"
                )
                _cancel_all_protective_orders(exchange, sym)
                time.sleep(0.5)
        except Exception as _e:
            log.debug(f"[Prot] verify cancel for {sym} failed: {_e}")

        placed = {'sl': False, 'tp': False, 'partial_tp': False}

        # ── SL ──
        for attempt in range(max_retries):
            try:
                exchange.create_order(
                    sym, 'STOP_MARKET', close_side, None, None,
                    params={
                        'stopPrice': sl,
                        'closePosition': True,
                        'workingType': wt,
                    }
                )
                placed['sl'] = True
                break
            except Exception as e:
                log.debug(f"[Prot] {sym} STOP_MARKET attempt {attempt+1} "
                          f"(closePosition) failed: {e}")
                # Fallback: explicit qty + reduceOnly
                try:
                    exchange.create_order(
                        sym, 'STOP_MARKET', close_side, qty, None,
                        params={
                            'stopPrice': sl,
                            'reduceOnly': True,
                            'workingType': wt,
                        }
                    )
                    placed['sl'] = True
                    break
                except Exception as e2:
                    log.debug(f"[Prot] {sym} STOP_MARKET attempt "
                              f"{attempt+1} (reduceOnly) failed: {e2}")

        # ══ [BROKER-SIDE PARTIAL TP] ══
        # نضع أمرين TP:
        #   1. Partial TP عند +PARTIAL_TP_R بـ qty × PARTIAL_TP_PCT
        #   2. Full TP عند TP_MULT بـ qty × (1 − PARTIAL_TP_PCT)
        # هذا يجعل Partial يعمل حتى لو البوت معطّل.
        _partial_pct = float(getattr(CFG, 'PARTIAL_TP_PCT', 0.0))
        _partial_enabled = (
            bool(getattr(CFG, 'PARTIAL_TP_ENABLED', False))
            and 0.0 < _partial_pct < 1.0
        )

        _sl_dist0 = float(pos.get('sl_dist_initial') or 0.0)
        _entry_px = float(pos.get('entry') or 0.0)
        _partial_price = 0.0
        if _partial_enabled and _sl_dist0 > 0 and _entry_px > 0:
            _partial_r = float(getattr(CFG, 'PARTIAL_TP_R', 1.5))
            if action == 'BUY':
                _partial_price = _entry_px + _sl_dist0 * _partial_r
            else:
                _partial_price = _entry_px - _sl_dist0 * _partial_r
            # تأكد أن Partial TP أدنى من Full TP في الاتجاه الصحيح
            if action == 'BUY' and _partial_price >= tp:
                _partial_enabled = False
            elif action == 'SELL' and _partial_price <= tp:
                _partial_enabled = False
        # [FIX-B] إذا لم يُحسب سعر Partial (sl_dist0 = 0)، عطّله
        if _partial_enabled and _partial_price <= 0:
            _partial_enabled = False

        _partial_qty = 0.0
        _full_qty = qty
        if _partial_enabled:
            _partial_qty = qty * _partial_pct
            _full_qty = qty * (1.0 - _partial_pct)

        # ── Partial TP (broker-side) ──
        if _partial_enabled and _partial_qty > 0:
            for attempt in range(max_retries):
                try:
                    exchange.create_order(
                        sym, 'TAKE_PROFIT_MARKET', close_side,
                        _partial_qty, None,
                        params={
                            'stopPrice': _partial_price,
                            'reduceOnly': True,
                            'workingType': wt,
                        }
                    )
                    placed['partial_tp'] = True
                    log.info(f"[Prot] {sym} PARTIAL-TP "
                             f"@{_partial_price:.6f} "
                             f"qty={_partial_qty:.6f} "
                             f"({_partial_pct*100:.0f}%)")
                    break
                except Exception as e:
                    log.debug(f"[Prot] {sym} PARTIAL-TP attempt "
                              f"{attempt+1} failed: {e}")

        # ── Full TP (broker-side) ──
        # إذا فُعِّل Partial، نضع Full TP بـ qty المتبقية (reduceOnly)
        # وإلا نستخدم closePosition (السلوك القديم)
        if _partial_enabled:
            _tp_qty = _full_qty
            _tp_close_pos = False
        else:
            _tp_qty = None
            _tp_close_pos = True

        for attempt in range(max_retries):
            try:
                params_tp = {
                    'stopPrice': tp,
                    'workingType': wt,
                }
                if _tp_close_pos:
                    params_tp['closePosition'] = True
                else:
                    params_tp['reduceOnly'] = True
                exchange.create_order(
                    sym, 'TAKE_PROFIT_MARKET', close_side,
                    _tp_qty, None,
                    params=params_tp,
                )
                placed['tp'] = True
                break
            except Exception as e:
                log.debug(f"[Prot] {sym} FULL-TP attempt "
                          f"{attempt+1} failed: {e}")

        _partial_ok = placed['partial_tp'] or not _partial_enabled
        # [FIX-6.5] If SL failed but TP succeeded, roll back TP to avoid
        # unprotected position with only TP.
        if not placed['sl']:
            log.warning(f"[Prot] {sym} SL placement failed — "
                        f"rolling back any placed TP")
            try:
                _cancel_all_protective_orders(exchange, sym)
            except Exception:
                pass
            return False

        if placed['sl'] and placed['tp'] and _partial_ok:
            if _partial_enabled:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"PARTIAL-TP@{_partial_price:.6f} "
                         f"FULL-TP@{tp:.6f} placed")
            else:
                log.info(f"[Prot] {sym} STOP@{sl:.6f} "
                         f"TP@{tp:.6f} placed")
            return True
        log.warning(f"[Prot] {sym} partial: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return False
    except Exception as e:
        log.warning(f"[Prot] {sym} place_protective_orders fatal: {e}")
        return False


def _sync_protective_orders(exchange, sym: str, pos: Dict) -> bool:
    """
    Called from trailing when SL changes. Re-places both orders.
    Returns True if SL/TP now match pos.
    """
    if not getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        return False
    try:
        old_sl = pos.get('_prot_last_sl')
        old_tp = pos.get('_prot_last_tp')
        new_sl = float(pos.get('sl') or 0)
        new_tp = float(pos.get('tp1') or 0)
        if old_sl is None or old_tp is None:
            # Never placed before — place now
            ok = _place_protective_orders(exchange, sym, pos)
            if ok:
                pos['_prot_last_sl'] = new_sl
                pos['_prot_last_tp'] = new_tp
            return ok

        # Only resync if SL moved meaningfully
        step = float(getattr(CFG, 'PROTECTIVE_SYNC_MIN_STEP_FRAC', 0.001))
        if (new_sl > 0 and old_sl > 0
                and abs(new_sl - old_sl) / max(old_sl, 1e-12) < step):
            return True
        ok = _place_protective_orders(exchange, sym, pos)
        if ok:
            pos['_prot_last_sl'] = new_sl
            pos['_prot_last_tp'] = new_tp
        return ok
    except Exception as e:
        log.warning(f"[Prot] {sym} sync fatal: {e}")
        return False

def _maybe_adapt_tp_live(pos: Dict, sig_opp, ad, exchange) -> bool:
    """
    Live wrapper for dict-based positions. Syncs protective orders.
    """
    try:
        _act = str(pos.get('action', '?'))
        if _act not in ('BUY', 'SELL'):
            return False
        if _act == sig_opp.action:
            return False

        _entry = float(pos.get('entry', 0.0))
        _sl_d0 = float(pos.get('sl_dist_initial', 0.0) or 0.0)
        if _entry <= 0 or _sl_d0 <= 0:
            return False

        _cur_ci = max(0, len(ad.closes) - 2) if ad is not None else int(
            getattr(sig_opp, 'close_idx', 0)
        )

        _entry_ci = int(pos.get('_entry_ci', 0) or 0)
        if _cur_ci <= _entry_ci:
            return False

        # ══ [_orig_score] رقم صافٍ، آمن عبر JSON ══
        sc_e = float(pos.get('_orig_score', 0.0) or 0.0)
        sc_o = float(getattr(sig_opp, 'score', 0.0) or 0.0)

        _tp_old = float(pos.get('tp1', 0.0))
        if _tp_old <= 0:
            return False

        tp_new, reason = _opp_tp_decide(
            action_pos=_act,
            entry=_entry,
            sl_dist0=_sl_d0,
            tp_old=_tp_old,
            partial_taken=bool(pos.get('_partial_taken', False)),
            entry_ci=_entry_ci,
            sig_opp=sig_opp,
            current_ci=_cur_ci,
        )
        if tp_new is None:
            log.debug(f"[OppTP] {pos.get('_sym','?')} skip: {reason}")
            return False

        pos['tp1'] = float(tp_new)
        log.info(f"[OppTP] {pos.get('_sym','?')} {_act} "
                 f"TP {_tp_old:.6f} → {tp_new:.6f} "
                 f"(opp score={sc_o:.2f} vs {sc_e:.2f})")

        if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
            try:
                _sync_protective_orders(exchange, pos['_sym'], pos)
            except Exception as _e:
                log.warning(f"[OppTP] {pos.get('_sym','?')} "
                            f"prot sync failed: {_e}")
        return True
    except Exception as e:
        log.debug(f"[OppTP] live adapter failed: {e}")
        return False

# ════════════════════════════════════════════════════════════════
# [ADVANCED TRAILING] — 5-layer SL optimizer
# ════════════════════════════════════════════════════════════════

def _classify_regime_local(ad, fi: int, lookback: int) -> str:
    """
    Classify current regime using E_therm (local volatility).
    Compares current σ to its rolling mean over `lookback` bars.
    """
    try:
        if fi < 5 or ad is None:
            return "normal"
        start = max(0, fi - lookback)
        sig_now = float(ad.E_therm[fi])
        sig_mean = float(np.mean(ad.E_therm[start:fi]))
        if sig_mean <= 1e-9 or not np.isfinite(sig_now):
            return "normal"
        ratio = sig_now / sig_mean
        if ratio > 1.6:
            return "explosive"
        elif ratio < 0.7:
            return "ranging"
        else:
            return "trending"
    except Exception:
        return "normal"


def _regime_multiplier(regime: str) -> float:
    """Map regime to trail multiplier."""
    if not getattr(CFG, 'TRAIL_REGIME_ENABLED', True):
        return 1.0
    if regime == "explosive":
        return float(getattr(CFG, 'TRAIL_REGIME_EXPLOSIVE_MULT', 1.4))
    if regime == "trending":
        return float(getattr(CFG, 'TRAIL_REGIME_TRENDING_MULT', 1.2))
    if regime == "ranging":
        return float(getattr(CFG, 'TRAIL_REGIME_RANGING_MULT', 0.7))
    return 1.0


def _physics_trail_modifier(ad, fi: int) -> float:
    """
    Physics-based trail modifier in [clamp_lo, clamp_hi].
    Widen when the system is trending with strong signal.
    Tighten when friction / uncertainty dominate.
    """
    if not getattr(CFG, 'TRAIL_PHYSICS_ENABLED', True) or ad is None:
        return 1.0
    try:
        accel = abs(float(ad.geodesic_accel[fi]))
        fric = float(ad.friction[fi])
        gauge = float(ad.gauge_force[fi])
        V_now = float(ad.V[fi]) if fi < len(ad.V) else 1.0
        V_mean = float(np.mean(ad.V[max(0, fi-100):fi+1])) + 1e-12
        v_ratio = V_now / V_mean

        a_s = float(np.tanh(accel / max(CFG.TRAIL_ACCEL_SCALE, 1e-9)))
        f_s = float(np.tanh(fric / max(CFG.TRAIL_FRICTION_SCALE, 1e-9)))
        g_s = float(np.tanh(gauge / max(CFG.TRAIL_GAUGE_SCALE, 1e-9)))
        u_s = float(np.clip(np.log(max(v_ratio, 1e-6)) / np.log(3.0), -1.0, 1.0))

        widen = 0.4 * a_s + 0.3 * g_s - 0.4 * f_s - 0.3 * u_s
        mod = 1.0 + widen
        lo, hi = CFG.TRAIL_PHYSICS_CLAMP
        return float(np.clip(mod, float(lo), float(hi)))
    except Exception:
        return 1.0


def _lock_R_from_peak(peak_R: float) -> float:
    """Interpolate R-ratchet table → current locked R."""
    levels = getattr(CFG, 'TRAIL_RATCHET_LEVELS', ((0.7, 0.0),))
    lock = 0.0
    for thr, lr in levels:
        if peak_R >= float(thr):
            lock = float(lr)
    return lock


def _find_recent_swing(ad, from_ci: int, to_ci: int,
                        side: str) -> Optional[float]:
    """
    Most recent swing point in [from_ci, to_ci] (exclusive to_ci).
    LONG  → latest swing low  (price makes lower low vs both neighbors)
    SHORT → latest swing high
    """
    if not getattr(CFG, 'TRAIL_STRUCTURE_ENABLED', True) or ad is None:
        return None
    try:
        lo = max(1, from_ci)
        hi = min(len(ad.lows) - 1, to_ci)
        if hi - lo < 3:
            return None
        arr_l = ad.lows[lo:hi]
        arr_h = ad.highs[lo:hi]
        if side == "BUY":
            for j in range(len(arr_l) - 2, 0, -1):
                if (arr_l[j] < arr_l[j-1] and arr_l[j] < arr_l[j+1]):
                    return float(arr_l[j])
        else:
            for j in range(len(arr_h) - 2, 0, -1):
                if (arr_h[j] > arr_h[j-1] and arr_h[j] > arr_h[j+1]):
                    return float(arr_h[j])
    except Exception:
        pass
    return None


def _compute_advanced_trail_core(side, entry, current_sl, sl_dist_initial,
                                    peak_price, price, prev_peak_R,
                                    bars_held, ad, current_ci):
    """
    Primitive-based core of the advanced trailing model.
    Returns (new_sl, new_peak_R, reason). new_sl == current_sl if no change.
    Used by BOTH live (dict) and backtest (OpenPosition).
    """
    try:
        if not getattr(CFG, 'TRAIL_ADVANCED_ENABLED', True):
            return current_sl, prev_peak_R, ""
        if sl_dist_initial <= 1e-9:
            return current_sl, prev_peak_R, ""

        if side == "BUY":
            profit_R = (price - entry) / sl_dist_initial
        else:
            profit_R = (entry - price) / sl_dist_initial
        peak_R = max(prev_peak_R, profit_R)

        # Activation: matches the ORIGINAL behaviour.
        # Original activated when MFE >= 0.4 * sigma_entry.
        # We use current sigma (dynamic) at 0.4 multiplier.
        fi = current_ci - ad.feat_start if ad is not None else -1

        # Activation (see block above)
        _act_mult = float(getattr(CFG, 'TRAIL_ACTIVATE_SIGMA_MULT', 0.40))
        _sig_now = 0.01
        if ad is not None and 0 <= fi < len(ad.E_therm):
            _sn = float(ad.E_therm[fi])
            if np.isfinite(_sn) and _sn > 1e-6:
                _sig_now = _sn
        _act_thr = _act_mult * _sig_now
        if side == "BUY":
            _peak_move = (peak_price - entry) / max(abs(entry), 1e-9)
        else:
            _peak_move = (entry - peak_price) / max(abs(entry), 1e-9)
        if _peak_move < _act_thr:
            return current_sl, peak_R, ""
        

        atr_val = 1e-9
        if ad is not None and 0 <= current_ci < len(ad.atr14):
            atr_val = float(ad.atr14[current_ci])
        if atr_val <= 1e-9 and ad is not None and 0 <= fi < len(ad.E_therm):
            atr_val = float(ad.E_therm[fi]) * entry

        physics_mod = _physics_trail_modifier(ad, fi) if fi >= 0 else 1.0
        regime = (_classify_regime_local(ad, fi,
                    int(getattr(CFG, 'TRAIL_REGIME_LOOKBACK', 100)))
                  if fi >= 0 else "normal")
        regime_mod = _regime_multiplier(regime)

        chand_dist = float(CFG.TRAIL_CHANDELIER_K) * atr_val * physics_mod * regime_mod

        if getattr(CFG, 'TRAIL_TIME_DECAY_ENABLED', True):
            td_thr = int(getattr(CFG, 'TRAIL_TIME_DECAY_BARS', 20))
            if bars_held > td_thr and peak_R < 1.5:
                steps = (bars_held - td_thr) // max(td_thr, 1)
                fac = float(getattr(CFG, 'TRAIL_TIME_DECAY_FACTOR', 0.85)) ** steps
                fac = max(fac, float(getattr(CFG, 'TRAIL_TIME_DECAY_MIN_MULT', 0.5)))
                chand_dist *= fac

        chand_dist = max(chand_dist, float(CFG.TRAIL_MIN_R_FRACTION) * sl_dist_initial)

        if side == "BUY":
            c1 = peak_price - chand_dist
        else:
            c1 = peak_price + chand_dist

        lock_R = _lock_R_from_peak(peak_R)
        if side == "BUY":
            c2 = entry + lock_R * sl_dist_initial
        else:
            c2 = entry - lock_R * sl_dist_initial

        c3 = None
        if ad is not None and getattr(CFG, 'TRAIL_STRUCTURE_ENABLED', True):
            lookback = int(getattr(CFG, 'TRAIL_STRUCTURE_LOOKBACK', 50))
            from_ci = max(current_ci - bars_held, current_ci - lookback)
            swing = _find_recent_swing(ad, from_ci, current_ci + 1, side)
            if swing is not None:
                buf = float(getattr(CFG,
                    'TRAIL_STRUCTURE_BUFFER_SIGMA', 0.3)) * atr_val
                c3 = (swing - buf) if side == "BUY" else (swing + buf)

        # ── Candidate 4: Legacy floor ──
        # Guarantee: never less protective than the old formula
        # (peak × (1 − kappa × σ_current)). This makes the advanced
        # trailing at least as tight as the previous working design,
        # while chandelier/ratchet/structure can only tighten further.
        c4 = None
        if getattr(CFG, 'TRAIL_LEGACY_FLOOR_ENABLED', True):
            try:
                if ad is not None and 0 <= fi < len(ad.E_therm):
                    _sig_now = float(ad.E_therm[fi])
                else:
                    _sig_now = sl_dist_initial / max(entry, 1e-9)
                _leg_dist = float(CFG.TRAIL_KAPPA) * _sig_now * entry
                _leg_dist = max(_leg_dist, 0.001 * entry)
                if side == "BUY":
                    c4 = peak_price - _leg_dist
                else:
                    c4 = peak_price + _leg_dist
            except Exception:
                c4 = None

        # ── Fusion (4 candidates) ──
        if side == "BUY":
            cands = [c1, c2] + ([c3] if c3 is not None else []) \
                             + ([c4] if c4 is not None else [])
            new_sl = max(cands)
            new_sl = min(new_sl, price * 0.9999)
            if new_sl <= current_sl * (1.0 + CFG.TRAIL_MIN_STEP_FRAC):
                return current_sl, peak_R, ""
            bits = []
            if abs(new_sl - c1) < 1e-9: bits.append("chand")
            if abs(new_sl - c2) < 1e-9: bits.append(f"ratchet{lock_R:.1f}R")
            if c3 is not None and abs(new_sl - c3) < 1e-9: bits.append("swing")
            if c4 is not None and abs(new_sl - c4) < 1e-9: bits.append("legacy")
            return float(new_sl), peak_R, "+".join(bits)
        else:
            cands = [c1, c2] + ([c3] if c3 is not None else []) \
                             + ([c4] if c4 is not None else [])
            new_sl = min(cands)
            new_sl = max(new_sl, price * 1.0001)
            if new_sl >= current_sl * (1.0 - CFG.TRAIL_MIN_STEP_FRAC):
                return current_sl, peak_R, ""
            bits = []
            if abs(new_sl - c1) < 1e-9: bits.append("chand")
            if abs(new_sl - c2) < 1e-9: bits.append(f"ratchet{lock_R:.1f}R")
            if c3 is not None and abs(new_sl - c3) < 1e-9: bits.append("swing")
            if c4 is not None and abs(new_sl - c4) < 1e-9: bits.append("legacy")
            return float(new_sl), peak_R, "+".join(bits)
    except Exception as e:
        log.debug(f"[AdvTrail] core compute failed: {e}")
        return current_sl, prev_peak_R, ""


def compute_advanced_trail(pos, ad, price, current_ci):
    """
    Live wrapper — reads from dict, calls core, writes back.
    """
    try:
        entry = float(pos['entry'])
        side = pos['action']
        current_sl = float(pos.get('sl') or 0.0)
        sl_dist0 = float(pos.get('sl_dist_initial') or
                          abs(entry - current_sl) or 1e-9)
        peak_price = float(pos.get('peak_price') or entry)
        peak_R_prev = float(pos.get('_trail_peak_R', 0.0))
        bars_held = int(pos.get('_trail_bars_held', 0))

        new_sl, new_peak_R, reason = _compute_advanced_trail_core(
            side=side, entry=entry, current_sl=current_sl,
            sl_dist_initial=sl_dist0, peak_price=peak_price,
            price=price, prev_peak_R=peak_R_prev,
            bars_held=bars_held, ad=ad, current_ci=current_ci,
        )
        pos['_trail_peak_R'] = new_peak_R
        return new_sl, reason
    except Exception as e:
        log.debug(f"[AdvTrail] live wrapper failed: {e}")
        return float(pos.get('sl') or 0.0), ""

# ════════════════════════════════════════════════════════════════
# § 18.5  بروتوكول مايسنر لمنع الانزلاق (Quantum Chunking)
# ════════════════════════════════════════════════════════════════
def execute_post_only(exchange, symbol: str, side: str, qty: float,
                      penetration_bps: float = None,
                      max_wait_s: int = None,
                      reprice_s: float = None,
                      fallback_market: bool = False,
                      fixed_target: Optional[float] = None,
                      cross_spread: bool = False,
                      reduce_only: bool = False):
    """
    reduce_only=True → attach reduceOnly to every order placed.
    Prevents accidental reverse-position if protective orders fire
    simultaneously. Critical for exits.
    """
    """
    cross_spread=True → Marketable limit: place SELL at best_bid,
    BUY at best_ask. Fills immediately as taker at ~1 spread cost
    (typically 2-5 bps). No GTX post-only parameter.
    """
    """
    Post-Only execution with ATOMIC fill accounting.

    Key invariants:
      - total_filled ALWAYS reflects sum of exchange-confirmed fills.
      - remaining = qty - total_filled ALWAYS.
      - Every cancel is preceded by a fresh fetch_order.
      - Bounded chasing: max PO_MAX_ATTEMPTS cancel/replace cycles.
      - Aborts when drift > PO_MAX_DRIFT_BPS or attempts exhausted.
    """
    pen = (penetration_bps if penetration_bps is not None
           else CFG.PO_PENETRATION_BPS) * 1e-4
    wait = (max_wait_s if max_wait_s is not None
            else CFG.PO_MAX_WAIT_S)
    rep = reprice_s if reprice_s is not None else CFG.PO_REPRICE_S
    drift_bps = CFG.PO_DRIFT_BPS
    max_attempts = int(getattr(CFG, 'PO_MAX_ATTEMPTS', 3))
    max_drift = float(getattr(CFG, 'PO_MAX_DRIFT_BPS', 5.0))

    t0 = time.time()
    active = None
    total_filled = 0.0
    total_cost = 0.0
    remaining = qty
    attempts = 0
    last_bid = 0.0
    last_ask = 0.0

    # ══ [ADAPTIVE FIX #3] Fetch tick size once ══
    _tick = _get_tick_size(exchange, symbol)

    def _refresh_active():
        """Fetch latest order state; update total_filled via DELTA only."""
        nonlocal active, total_filled, total_cost, remaining
        if active is None:
            return
        try:
            st = exchange.fetch_order(active['id'], symbol)
        except Exception:
            return
        status = st.get('status')
        fq = float(st.get('filled') or 0.0)
        fp = float(st.get('average') or st.get('price') or active['price'])

        # ══ DELTA-BASED update: never double-count, never miss ══
        prev_f = float(active.get('counted_fill', 0.0))
        prev_c = float(active.get('counted_cost', 0.0))
        delta_f = fq - prev_f
        if delta_f > 0.0:
            cur_cost = fq * fp
            delta_c = max(0.0, cur_cost - prev_c)
            total_filled += delta_f
            total_cost += delta_c
            active['counted_fill'] = fq
            active['counted_cost'] = cur_cost
            remaining = max(0.0, qty - total_filled)

        if status == 'closed':
            active['terminal'] = True
        elif status in ('canceled', 'expired', 'rejected'):
            active['terminal'] = True

    try:
        while time.time() - t0 < wait:
            # 1. Book
            try:
                ob = exchange.fetch_order_book(symbol, limit=5)
                last_bid = float(ob['bids'][0][0])
                last_ask = float(ob['asks'][0][0])
            except Exception:
                time.sleep(1.0)
                continue

            # 2. Target — v10 semantics exactly:
            #    - caller supplies fixed_target → lock to it
            #    - caller supplies None      → quote from live book at edge
            _fixed = (fixed_target is not None and fixed_target > 0)
            if _fixed:
                target = float(fixed_target)
            elif cross_spread:
                # Marketable limit — cross the spread for immediate fill.
                # SELL exits: at best_bid. BUY exits: at best_ask.
                _base = last_ask if side == 'buy' else last_bid
                target = float(_base)
            else:
                _base = last_bid if side == 'buy' else last_ask
                if (getattr(CFG, 'PO_USE_TICK_PENETRATION', True)
                        and _tick and _tick > 0 and _base > 0):
                    _pen_abs = max(pen * _base, _tick)
                    _pen_ticks = int(np.ceil(_pen_abs / _tick))
                    _pen_abs = _pen_ticks * _tick
                    target = (_base - _pen_abs if side == 'buy'
                              else _base + _pen_abs)
                else:
                    target = (_base * (1.0 - pen) if side == 'buy'
                              else _base * (1.0 + pen))

            # 3. Refresh active state (handles ALL statuses)
            _refresh_active()

            # 4. Handle terminal
            if active is not None and active.get('terminal'):
                if active['counted_fill'] >= active['qty'] * 0.99:
                    active = None
                    break   # complete
                # Was canceled externally → drop and decide below
                active = None

            # 5. Exit conditions
            if remaining <= qty * 0.02:
                break
            if total_filled >= qty * CFG.PO_FILL_THRESHOLD:
                break

            # 6. Drift + cancel/replace decision
            if active is not None and not _fixed:
                drift = abs(active['price'] - target) / max(target, 1e-12) * 1e4
                if drift > drift_bps:
                    # ══ MANDATORY: sweep before cancel ══
                    _refresh_active()
                    # Decide: replace or abort?
                    abort = (
                        attempts >= max_attempts
                        or drift > max_drift
                        or total_filled >= qty * 0.90
                    )
                    if abort:
                        log.info(f"[PostOnly] {symbol} ABORT "
                                 f"(attempts={attempts}, drift={drift:.2f}bps, "
                                 f"filled={total_filled:.6f}/{qty:.6f})")
                        # Cancel + final sweep
                        try:
                            exchange.cancel_order(active['id'], symbol)
                        except Exception as e:
                            log.warning(f"[PostOnly] ABORT cancel {symbol} "
                                        f"oid={active['id']} failed: {e}")
                        active = None
                        break
                    # REPLACE
                    try:
                        exchange.cancel_order(active['id'], symbol)
                    except Exception as e:
                        log.warning(f"[PostOnly] REPLACE cancel {symbol} "
                                    f"oid={active['id']} failed: {e}")
                    time.sleep(0.2)
                    _refresh_active()   # catch fills that arrived during cancel
                    active = None
                    attempts += 1
                    log.debug(f"[PostOnly] {symbol} re-place "
                              f"#{attempts} (drift={drift:.2f}bps, "
                              f"remaining={remaining:.6f})")

            # 7. Place new order (only if there is meaningful remaining)
            if active is None and remaining > 0:
                if total_filled >= qty * 0.90:
                    break
                try:
                    # GTX = post-only (must not cross book). Do NOT use it
                    # for marketable limit — the exchange would reject.
                    _ord_params = {} if cross_spread else {'timeInForce': 'GTX'}
                    if reduce_only:
                        _ord_params['reduceOnly'] = True
                    o = exchange.create_order(
                        symbol, 'limit', side, remaining, target,
                        params=_ord_params
                    )
                    active = {
                        'id': o['id'],
                        'price': target,
                        'qty': remaining,
                        'counted_fill': 0.0,
                        'counted_cost': 0.0,
                        'terminal': False,
                    }
                except Exception as e:
                    log.debug(f"[PostOnly] {symbol} GTX rejected: {e}")
                    time.sleep(0.5)
                    continue

            time.sleep(rep)

        # ── FINAL SWEEP (mandatory) ──
        if active is not None:
            _refresh_active()
            if not active.get('terminal'):
                try:
                    exchange.cancel_order(active['id'], symbol)
                except Exception as e:
                    log.warning(f"[PostOnly] FINAL cancel {symbol} "
                                f"oid={active['id']} failed: {e}")
                time.sleep(0.3)
                _refresh_active()
            active = None

        # ── Result ──
        if total_filled <= 0:
            if fallback_market:
                try:
                    mp = last_ask if side == 'buy' else last_bid
                    _fp = {'reduceOnly': True} if reduce_only else {}
                    o = exchange.create_order(symbol, 'market', side, qty,
                                              None, params=_fp)
                    fp = float(o.get('average') or mp)
                    return {
                        'filled_qty': qty, 'avg_price': fp, 'fill_ratio': 1.0,
                        'reason': 'market_fallback', 'market_price': mp,
                        'attempts': attempts,
                    }
                except Exception as e:
                    log.error(f"[PostOnly] market fallback failed {symbol}: {e}")
            return {'filled_qty': 0.0, 'avg_price': 0.0, 'fill_ratio': 0.0,
                    'reason': 'no_fill',
                    'market_price': last_ask if side == 'buy' else last_bid,
                    'attempts': attempts}

        avg = total_cost / total_filled
        fill_ratio = total_filled / qty
        reason = 'filled' if fill_ratio >= 0.98 else 'partial'

        # Optional market top-up for remainder
        if fill_ratio < 0.98 and fallback_market and remaining > 0:
            try:
                mp = last_ask if side == 'buy' else last_bid
                o = exchange.create_order(symbol, 'market', side, remaining)
                fp = float(o.get('average') or mp)
                total_cost += fp * remaining
                total_filled += remaining
                avg = total_cost / total_filled
                return {
                    'filled_qty': total_filled, 'avg_price': avg,
                    'fill_ratio': total_filled / qty,
                    'reason': 'market_fallback', 'market_price': mp,
                    'attempts': attempts,
                }
            except Exception as e:
                log.warning(f"[PostOnly] partial top-up failed {symbol}: {e}")

        return {
            'filled_qty': total_filled,
            'avg_price': avg,
            'fill_ratio': fill_ratio,
            'reason': reason,
            'market_price': last_ask if side == 'buy' else last_bid,
            'attempts': attempts,
        }

    except Exception as e:
        log.error(f"[PostOnly] {symbol} fatal: {e}")
        # Emergency: sweep whatever we can
        try:
            _refresh_active()
        except Exception:
            pass
        if total_filled > 0:
            return {
                'filled_qty': total_filled,
                'avg_price': total_cost / total_filled,
                'fill_ratio': total_filled / qty,
                'reason': 'partial_error',
                'market_price': last_ask if side == 'buy' else last_bid,
                'attempts': attempts,
            }
        return {'filled_qty': 0.0, 'avg_price': 0.0, 'fill_ratio': 0.0,
                'reason': 'error', 'market_price': 0.0, 'attempts': attempts}

# ════════════════════════════════════════════════════════════════
# § 18.7b  AdaptiveFillEngine — Microstructure-Aware Maker Execution
# ════════════════════════════════════════════════════════════════

class AdaptiveFillEngine:
    """
    Sophisticated maker execution engine:
      - Micro-price & fair-price based quoting
      - Queue-position model
      - Toxic flow cancellation
      - Multi-level ladder with EV maximization
      - Online adaptation of urgency & thresholds
    """

    def __init__(self, exchange, symbol: str):
        self.exchange = exchange
        self.symbol = symbol

        # Runtime state
        self.tracker = MicroTracker(alpha_fair=CFG.FILL_KALMAN_ALPHA)
        self.reprice_times: List[float] = []
        self.fill_history: List[Dict] = []
        self.toxicity_history: List[float] = []
        self.last_state: Optional[MicroState] = None

        # Adaptive parameters
        self.urgency_kappa = CFG.FILL_URGENCY_KAPPA
        self.toxic_threshold = CFG.FILL_TOXIC_THRESHOLD
        self.ladder_skew = 0.0  # >0 favors near levels, <0 favors far

    # ─────────────────────────────────────────────────────────────
    def _rate_limit_ok(self) -> bool:
        now = time.time()
        cutoff = now - 60.0
        self.reprice_times = [t for t in self.reprice_times if t >= cutoff]
        return len(self.reprice_times) < CFG.FILL_MAX_REPRICE_PER_MIN

    def _record_reprice(self):
        self.reprice_times.append(time.time())

    # ─────────────────────────────────────────────────────────────
    def _refresh_micro(self) -> Optional[MicroState]:
        """Fetch book + recent trades, update tracker, return state."""
        try:
            ob = self.exchange.fetch_order_book(self.symbol,
                                                limit=CFG.FILL_BOOK_DEPTH)
            self.tracker.update_book(ob)
        except Exception as e:
            log.warning(f"[AFE] book fetch {self.symbol}: {e}")
            return None
        try:
            trades = self.exchange.fetch_trades(self.symbol, limit=50)
            self.tracker.update_trades(trades)
        except Exception as e:
            log.debug(f"[AFE] fetch_trades {self.symbol} failed "
                      f"(optional): {e}")
        st = self.tracker.state()
        self.last_state = st
        return st

    # ─────────────────────────────────────────────────────────────
    def _should_abort_toxic(self, micro: MicroState, side: str) -> bool:
        """
        Toxic flow gate. For BUY: abort if toxic sell pressure dominates.
        For SELL: abort if toxic buy pressure dominates.
        """
        # Use signed toxicity: OFI + imbalance agreement
        signed = micro.ofi * (1.0 + micro.imbalance)
        if side == 'buy' and signed < -1e-6 and micro.toxic_score > self.toxic_threshold:
            return True
        if side == 'sell' and signed > 1e-6 and micro.toxic_score > self.toxic_threshold:
            return True
        return False

    # ─────────────────────────────────────────────────────────────
    def _build_ladder(self, micro: MicroState, side: str, total_qty: float,
                      target_fill: float, horizon_s: float) -> List[Dict]:
        """
        Choose N levels spaced by sigma_fast; allocate qty by expected EV.
        """
        N = max(2, CFG.FILL_LADDER_LEVELS)
        sigma = max(micro.sigma_fast, 0.5)  # bps
        # Baseline spacing: 1× sigma for nearest, growing outward
        spacings_bps = [sigma * (1.0 + 0.5 * i) for i in range(N)]

        fair = micro.fair_price
        side_sign = 1.0 if side == 'buy' else -1.0

        # EV per level: P_fill * edge - P_fill * adverse_cost
        # edge ≈ spacing (we buy below fair, so edge ~ spacing)
        # adverse_cost ≈ expected adverse selection if filled (fraction of spacing)
        adv_frac = CFG.FILL_ADVERSE_SELECTION_BPS / max(sigma, 0.5)

        candidates = []
        for i, sp in enumerate(spacings_bps):
            price = fair * (1.0 - side_sign * sp * 1e-4)
            qp = estimate_queue_position(micro, price, side, total_qty / N)
            pf = estimate_fill_probability(sp, sigma, horizon_s, qp,
                                            micro.trade_intensity)
            edge = sp - adv_frac * sigma   # bps
            ev = pf * edge
            candidates.append({'price': price, 'spacing_bps': sp,
                                'p_fill': pf, 'ev': ev, 'queue_pos': qp})

        # Normalize EV → weights
        evs = np.array([max(c['ev'], 0.0) for c in candidates])
        if evs.sum() <= 1e-9:
            # Fallback: uniform near levels
            weights = np.linspace(1.0, 0.3, N)
        else:
            weights = evs / evs.sum()

        # Apply skew (adaptation)
        skew = np.exp(np.linspace(-self.ladder_skew, self.ladder_skew, N))
        weights = weights * skew
        weights = weights / weights.sum()

        # Drop levels with p_fill < 0.03 (not worth the API call)
        ladder = []
        for c, w in zip(candidates, weights):
            if c['p_fill'] < 0.03:
                continue
            qty_i = total_qty * w
            if qty_i <= 0:
                continue
            ladder.append({
                'price': float(c['price']),
                'qty': float(qty_i),
                'p_fill': float(c['p_fill']),
                'spacing_bps': float(c['spacing_bps'])
            })
        return ladder

    # ─────────────────────────────────────────────────────────────
    def _place_ladder(self, side: str, ladder: List[Dict]) -> List[Dict]:
        """Send each level as Post-Only. Return list of active orders."""
        active = []
        for lvl in ladder:
            try:
                o = self.exchange.create_order(
                    self.symbol, 'limit', side, lvl['qty'], lvl['price'],
                    params={'timeInForce': 'GTX'}
                )
                active.append({
                    'id': o['id'], 'price': lvl['price'], 'qty': lvl['qty'],
                    'p_fill': lvl['p_fill'], 'placed_at': time.time()
                })
                self._record_reprice()
            except Exception as e:
                # Post-Only rejected → skip silently (may happen near touch)
                log.debug(f"[AFE] {self.symbol} level {lvl['price']:.6f} rejected: {e}")
        return active

    # ─────────────────────────────────────────────────────────────
    def _cancel_all(self, active: List[Dict]):
        for o in active:
            try:
                self.exchange.cancel_order(o['id'], self.symbol)
            except Exception as e:
                log.debug(f"[AFE] cancel {self.symbol} "
                          f"oid={o.get('id')} failed: {e}")

    # ─────────────────────────────────────────────────────────────
    def _sweep_fills(self, active: List[Dict], total_filled: float,
                     total_cost: float):
        """Check status of each order; accumulate fills; drop closed orders."""
        still_active = []
        for o in active:
            try:
                st = self.exchange.fetch_order(o['id'], self.symbol)
                status = st.get('status')
                if status == 'closed':
                    fq = float(st.get('filled') or 0.0)
                    fp = float(st.get('average') or st.get('price') or o['price'])
                    total_filled += fq
                    total_cost += fq * fp
                elif status in ('canceled', 'expired', 'rejected'):
                    log.debug(f"[AFE] sweep: {self.symbol} "
                              f"oid={o.get('id')} terminal status={status}")
                else:
                    still_active.append(o)
            except Exception:
                still_active.append(o)
        return still_active, total_filled, total_cost

    # ─────────────────────────────────────────────────────────────
    def _execute_taker(self, side: str, qty: float):
        try:
            o = self.exchange.create_order(self.symbol, 'market', side, qty)
            v = verify_fill_sync(self.exchange, o['id'], self.symbol, timeout_s=1.5)
            if v['filled']:
                return {'filled_qty': v['qty'], 'avg_price': v['price'],
                        'fill_rate': 1.0, 'mode': 'taker'}
            return None
        except Exception as e:
            log.error(f"[AFE] taker {self.symbol}: {e}")
            return None

    # ─────────────────────────────────────────────────────────────
    def _execute_maker(self, side: str, qty: float, sig, ad, current_ci: int):
        """
        Main smart-maker loop.
        """
        # 1. Initialize
        t0 = time.time()
        total_filled = 0.0
        total_cost = 0.0
        active: List[Dict] = []
        last_micro: Optional[MicroState] = None
        entered = False

        # 2. Main loop
        while time.time() - t0 < CFG.FILL_MAX_WAIT_S:
            micro = self._refresh_micro()
            if micro is None:
                time.sleep(0.5)
                continue
            last_micro = micro

            # 2a. Toxic gate (only before first fill)
            if not entered and self._should_abort_toxic(micro, side):
                log.info(f"[AFE] {self.symbol} toxic flow detected "
                         f"(score={micro.toxic_score:.2f}) — abort")
                self._cancel_all(active)
                return None

            # 2b. Sweep existing fills
            active, total_filled, total_cost = self._sweep_fills(
                active, total_filled, total_cost
            )
            if total_filled > 0:
                entered = True

            # 2c. Exit if filled enough
            remaining = qty - total_filled
            if remaining <= max(qty * 0.02, 1e-12):
                break

            # 2d. Check edge — don't quote if edge too thin
            # Edge = distance from fair to our quote
            fair = micro.fair_price
            if side == 'buy':
                target_near = fair * (1 - 2e-4)  # 2 bps
            else:
                target_near = fair * (1 + 2e-4)

            # 2e. Decide reprice / keep
            elapsed = time.time() - t0
            urgency = urgency_kappa(elapsed, CFG.FILL_MAX_WAIT_S, self.urgency_kappa)
            horizon_left = CFG.FILL_MAX_WAIT_S - elapsed

            # Cancel if rate-limit allows and price drifted
            need_reprice = False
            if not active:
                need_reprice = True
            elif last_micro is not None:
                # Check if fair price moved away from our quotes
                avg_price = np.mean([o['price'] for o in active])
                drift_bps = abs(avg_price - micro.fair_price) / micro.fair_price * 1e4
                if drift_bps > max(micro.sigma_fast * 0.5, 2.0):
                    need_reprice = True
            if urgency > 0.9 and not need_reprice:
                # Force closer at the end
                avg_price = np.mean([o['price'] for o in active]) if active else micro.fair_price
                if side == 'buy' and avg_price < target_near:
                    need_reprice = True
                if side == 'sell' and avg_price > target_near:
                    need_reprice = True

            if need_reprice and self._rate_limit_ok():
                self._cancel_all(active)
                active = []
                # Rebuild ladder with remaining qty and adjusted horizon
                ladder = self._build_ladder(
                    micro, side, remaining,
                    target_fill=CFG.FILL_TARGET,
                    horizon_s=max(horizon_left, 3.0)
                )
                if ladder:
                    active = self._place_ladder(side, ladder)
                else:
                    # No viable ladder → try Taker
                    log.info(f"[AFE] {self.symbol} no viable ladder → taker")
                    return self._execute_taker(side, remaining)

            time.sleep(max(CFG.FILL_RECHECK_MS / 1000.0, 0.2))

        # 3. Timeout or filled — cleanup
        active, total_filled, total_cost = self._sweep_fills(
            active, total_filled, total_cost
        )
        self._cancel_all(active)

        if total_filled <= 0:
            return None

        avg_price = total_cost / total_filled
        fill_rate = total_filled / qty

        # 4. Record for adaptation
        self.fill_history.append({
            'fill_rate': fill_rate, 'avg_price': avg_price,
            'elapsed': time.time() - t0, 'ts': time.time(),
            'side': side
        })
        self._adapt()
        return {'filled_qty': total_filled, 'avg_price': avg_price,
                'fill_rate': fill_rate, 'mode': 'maker'}

    # ─────────────────────────────────────────────────────────────
    def _adapt(self):
        """Adapt urgency and thresholds from recent outcomes."""
        if len(self.fill_history) < CFG.FILL_ADAPT_WINDOW:
            return
        recent = self.fill_history[-CFG.FILL_ADAPT_WINDOW:]
        avg_fill = float(np.mean([r['fill_rate'] for r in recent]))
        avg_time = float(np.mean([r['elapsed'] for r in recent]))

        # If fill rate low → increase urgency (approach mid faster)
        if avg_fill < CFG.FILL_TARGET - 0.15:
            self.urgency_kappa = min(self.urgency_kappa * 1.15, 6.0)
        elif avg_fill > CFG.FILL_TARGET + 0.10:
            self.urgency_kappa = max(self.urgency_kappa * 0.92, 0.5)

        # If taking too long, favor near levels (skew > 0)
        if avg_time > 0.7 * CFG.FILL_MAX_WAIT_S:
            self.ladder_skew = min(self.ladder_skew + 0.1, 1.5)
        elif avg_time < 0.3 * CFG.FILL_MAX_WAIT_S:
            self.ladder_skew = max(self.ladder_skew - 0.05, -0.5)

    # ─────────────────────────────────────────────────────────────
    def execute(self, side: str, qty: float, sig, ad, current_ci: int):
        """Entry point. Called from run_live."""
        ok, reason = signal_still_valid(ad, sig, current_ci)
        if not ok:
            log.info(f"[AFE] {self.symbol} skip: {reason}")
            return None

        mode = CFG.FILL_ENTRY_MODE.lower()

        if mode == "taker":
            return self._execute_taker(side, qty)

        if mode == "maker":
            return self._execute_maker(side, qty, sig, ad, current_ci)

        # hybrid
        result = self._execute_maker(side, qty, sig, ad, current_ci)
        if result is None:
            log.info(f"[AFE] {self.symbol} maker failed → taker")
            return self._execute_taker(side, qty)

        if result['fill_rate'] < 0.60:
            remaining = qty - result['filled_qty']
            if remaining > 0:
                topup = self._execute_taker(side, remaining)
                if topup:
                    tq = result['filled_qty'] + topup['filled_qty']
                    tc = (result['avg_price'] * result['filled_qty'] +
                          topup['avg_price'] * topup['filled_qty'])
                    return {'filled_qty': tq, 'avg_price': tc / max(tq, 1e-12),
                            'fill_rate': tq / qty, 'mode': 'hybrid'}
        return result


# ── Cache ────────────────────────────────────────────────────────
_ADAPTIVE_ENGINES: Dict[str, AdaptiveFillEngine] = {}

def _get_fill_engine(exchange, symbol: str) -> AdaptiveFillEngine:
    if symbol not in _ADAPTIVE_ENGINES:
        _ADAPTIVE_ENGINES[symbol] = AdaptiveFillEngine(exchange, symbol)
    return _ADAPTIVE_ENGINES[symbol]


def check_thermodynamic_apex(pos_action, entry_price, current_price, ad, fi):
    """
    مستشعر الأوج — σ-scaled thresholds when APEX_SIGMA_SCALED=True.

    Thresholds:
      - min_pnl:      κ_pnl × σ_bar  (default κ_pnl = 0.5)
      - energy_thr:   κ_e × σ_bar    (default κ_e = 0.5)
      - accel_thr:    κ_a × σ_bar    (default κ_a = 0.3)

    Falls back to absolute values (0.005, 0.005, 0.003) when flag is off.
    """
    if fi < 3:
        return False, ""

    # ── σ-scaled base ──
    try:
        sigma = float(ad.E_therm[fi]) if fi < len(ad.E_therm) else 0.01
        if not np.isfinite(sigma) or sigma <= 1e-6:
            sigma = 0.01
    except Exception:
        sigma = 0.01

    if getattr(CFG, 'APEX_SIGMA_SCALED', True):
        KAPPA_PNL = float(getattr(CFG, 'APEX_KAPPA_PNL', 0.5))
        KAPPA_E   = float(getattr(CFG, 'APEX_KAPPA_ENERGY', 0.5))
        KAPPA_A   = float(getattr(CFG, 'APEX_KAPPA_ACCEL', 0.3))
        min_pnl    = KAPPA_PNL * sigma
        energy_thr = KAPPA_E   * sigma
        accel_thr  = KAPPA_A   * sigma
    else:
        min_pnl    = 0.005
        energy_thr = 0.005
        accel_thr  = 0.003

    pnl = ((current_price - entry_price) / entry_price
           if pos_action == "BUY"
           else (entry_price - current_price) / entry_price)
    if pnl < min_pnl:
        return False, ""

    dF_window = ad.dF[fi - 2:fi + 1]
    sum_dF = np.sum(dF_window)

    accel_window = ad.geodesic_accel[fi - 2:fi + 1]
    accel_mean = np.mean(accel_window)

    energy_exhausted = (sum_dF > energy_thr)

    if pos_action == "BUY" and energy_exhausted and accel_mean < accel_thr:
        return True, "Apex: Action Integral Exhaustion"
    if pos_action == "SELL" and energy_exhausted and accel_mean > -accel_thr:
        return True, "Apex: Action Integral Exhaustion"

    return False, ""

def reconcile_positions(exchange, open_pos_live: Dict) -> Dict:
    """
    Fetch live positions from exchange, compare with local memory.
    - Positions in exchange but not in memory → add (unknown entry)
    - Positions in memory but not in exchange → remove (manual close / SL hit)
    - Positions with size mismatch → adjust
    """
    try:
        live_positions = exchange.fetch_positions()
    except Exception as e:
        log.error(f"[Reconcile] fetch_positions failed: {e}")
        return open_pos_live

    exchange_map = {}
    for p in live_positions:
        try:
            amt = float(p['info'].get('positionAmt', 0))
            if abs(amt) < 1e-12:
                continue
            sym = p['symbol']
            # ccxt symbol may be "BTC/USDT:USDT" — normalize
            sym_norm = sym.split(':')[0] if ':' in sym else sym
            entry_px = float(p['info'].get('entryPrice', 0) or p.get('entryPrice', 0) or 0)
            side = 'BUY' if amt > 0 else 'SELL'
            exchange_map[sym_norm] = {
                'qty': abs(amt),
                'entry': entry_px,
                'action': side
            }
        except Exception as e:
            log.debug(f"[Reconcile] parse error: {e}")

    # Remove from local any not on exchange
    to_del = []
    for sym in open_pos_live:
        if sym not in exchange_map:
            log.warning(f"[Reconcile] {sym} in memory but not on exchange — removing")
            to_del.append(sym)
    for sym in to_del:
        del open_pos_live[sym]

    # Update local quantities from exchange
    for sym, ex_pos in exchange_map.items():
        if sym in open_pos_live:
            local = open_pos_live[sym]
            if abs(local['qty'] - ex_pos['qty']) / max(ex_pos['qty'], 1e-9) > 0.01:
                log.warning(f"[Reconcile] {sym} qty mismatch: "
                            f"local={local['qty']} exchange={ex_pos['qty']}")
                local['qty'] = ex_pos['qty']
            # Fix entry to actual exchange entry
            if ex_pos['entry'] > 0:
                local['entry'] = ex_pos['entry']
        else:
            # Unknown position — adopt it with conservative defaults
            log.warning(f"[Reconcile] {sym} on exchange but not in memory — adopting")
            open_pos_live[sym] = {
                'action': ex_pos['action'],
                'entry': ex_pos['entry'],
                'qty': ex_pos['qty'],
                'sl': ex_pos['entry'] * (0.985 if ex_pos['action'] == 'BUY' else 1.015),
                'tp1': ex_pos['entry'] * (1.03 if ex_pos['action'] == 'BUY' else 0.97),
                'T_info': 0.0,
                'dyn_risk': 0.01,
                'entry_ts': time.time(),
                'adopted': True,
            }

    return open_pos_live

# ════════════════════════════════════════════════════════════════
# § 18.95  Persistent Symbol Metadata (Leverage / Margin / Setup)
# ════════════════════════════════════════════════════════════════

_SYMBOL_META: Dict[str, Dict] = {}
_SYMBOL_META_PATH: str = ""

# ════════════════════════════════════════════════════════════════
# § 18.94  Rate-Limit Tracker
# ════════════════════════════════════════════════════════════════

_RATE_TRACKER: Dict = {
    'window': [],          # list of (ts, weight)
    'total_this_min': 0.0,
    'rejected_count': 0,
    'last_report_ts': 0.0,
    # [FIX-3.7] Count actual exchange rate-limit hits
    'hits_1003': 0,
    'last_hit_ts': 0.0,
}

# Binance USDT-M defaults
_RATE_LIMIT_WEIGHT_PER_MIN = 2400
_RATE_LIMIT_SOFT_CAP = 0.75   # pause new placements if usage > 75%


def _rate_record(weight: float = 1.0) -> None:
    """Record an API call weight."""
    now = time.time()
    _RATE_TRACKER['window'].append((now, weight))
    # Prune older than 60s
    cutoff = now - 60.0
    _RATE_TRACKER['window'] = [
        (t, w) for (t, w) in _RATE_TRACKER['window'] if t >= cutoff
    ]
    _RATE_TRACKER['total_this_min'] = sum(w for _, w in _RATE_TRACKER['window'])


def _rate_usage() -> float:
    """Current usage fraction [0, 1]."""
    _rate_record(0.0)  # refresh
    return float(_RATE_TRACKER['total_this_min']) / _RATE_LIMIT_WEIGHT_PER_MIN


def _rate_can_place() -> bool:
    """True if rate usage is below soft cap."""
    return _rate_usage() < _RATE_LIMIT_SOFT_CAP


def _rate_report() -> None:
    """Log usage periodically."""
    now = time.time()
    if now - _RATE_TRACKER['last_report_ts'] < 300:
        return
    _RATE_TRACKER['last_report_ts'] = now
    usage = _rate_usage()
    if usage > 0.5:
        log.warning(f"[RateLimit] usage={usage*100:.1f}% "
                    f"(total={_RATE_TRACKER['total_this_min']:.0f}/min) "
                    f"rejected={_RATE_TRACKER['rejected_count']}")
    else:
        log.info(f"[RateLimit] usage={usage*100:.1f}%")

# ════════════════════════════════════════════════════════════════
# [FIX-09-PROPER] Position cache with TTL — batched fetch
# ════════════════════════════════════════════════════════════════
#
# Problem solved:
#   _fake_pos_list(exchange, sym) costs weight=5 on Binance.
#   Called from 5 different sites in the exit/entry flow. In fast
#   markets with repeated exit failures, this burns rate limit
#   and can trigger -1003.
#
# Solution:
#   - ONE call fetches ALL positions (weight=5) and caches 3 s.
#   - All call sites go through _fetch_positions_cached().
#   - _fake_pos_list() preserves the original fetch_positions([sym])
#     return shape so existing iteration code works unchanged.
#   - Explicit invalidation after entry/exit/partial keeps it fresh.
#   - Backtest never calls these — zero impact there.

# [FIX-20] Module-level state singleton (replaces globals())
_GLOBAL_STATE: Dict = {}

_POSITION_CACHE: Dict = {
    'ts': 0.0,
    'by_sym': {},
    'all_fetched': False,
}
_POSITION_CACHE_TTL_S: float = 3.0
_POSITION_CACHE_STATS: Dict = {
    'hits': 0,
    'misses': 0,
    'api_calls': 0,
    'invalidations': 0,
    'errors': 0,
    'last_report_ts': 0.0,
}


def _normalize_sym(sym: str) -> str:
    """BTC/USDT:USDT -> BTC/USDT  (strip ccxt settle suffix)."""
    if not sym:
        return ''
    return sym.split(':')[0] if ':' in sym else sym


def _invalidate_position_cache() -> None:
    """[FIX-09-PROPER] Force refresh on next call."""
    _POSITION_CACHE['ts'] = 0.0
    _POSITION_CACHE['all_fetched'] = False
    _POSITION_CACHE_STATS['invalidations'] += 1


def _fetch_positions_cached(exchange,
                             sym=None,
                             force: bool = False,
                             symbols_hint=None):
    """
    [FIX-09-PROPER] Cached fetch_positions.

    One API call fetches ALL open positions (weight=5) and caches
    for _POSITION_CACHE_TTL_S seconds.

    Returns dict {sym_norm: {qty, entry, side, liquidationPrice,
                              leverage, markPrice}}.
    """
    now = time.time()
    stale = (now - float(_POSITION_CACHE['ts'])) > _POSITION_CACHE_TTL_S
    need_fetch = (force or stale
                  or not _POSITION_CACHE['all_fetched'])

    if need_fetch:
        try:
            _rate_record(5.0)
            raw = exchange.fetch_positions(symbols_hint)
            _POSITION_CACHE_STATS['api_calls'] += 1
        except Exception as e:
            _POSITION_CACHE_STATS['errors'] += 1
            log.debug(f"[PosCache] fetch failed: {e}")
            _POSITION_CACHE['ts'] = now
            if sym is not None:
                return {}
            return dict(_POSITION_CACHE['by_sym'])

        by_sym = {}
        for p in (raw or []):
            try:
                amt = float(p['info'].get('positionAmt', 0) or 0)
                if abs(amt) < 1e-12:
                    continue
                _s = _normalize_sym(p.get('symbol') or '')
                if not _s:
                    continue
                by_sym[_s] = {
                    'qty': abs(amt),
                    'entry': float(p['info'].get('entryPrice', 0) or 0),
                    'side': 'BUY' if amt > 0 else 'SELL',
                    'liquidationPrice': float(
                        p['info'].get('liquidationPrice', 0) or 0),
                    'leverage': int(float(
                        p['info'].get('leverage', 0) or 0)),
                    'markPrice': float(
                        p['info'].get('markPrice', 0) or 0),
                }
            except Exception as _e:
                log.debug(f"[PosCache] parse error: {_e}")
                continue

        _POSITION_CACHE['by_sym'] = by_sym
        _POSITION_CACHE['ts'] = now
        _POSITION_CACHE['all_fetched'] = True
        _POSITION_CACHE_STATS['misses'] += 1
    else:
        _POSITION_CACHE_STATS['hits'] += 1

    if sym is None:
        return dict(_POSITION_CACHE['by_sym'])
    if sym in _POSITION_CACHE['by_sym']:
        return {sym: _POSITION_CACHE['by_sym'][sym]}
    return {}


def _get_position_qty(exchange, sym: str,
                       force: bool = False) -> float:
    """[FIX-09-PROPER] Convenience: qty of a single symbol."""
    pos_map = _fetch_positions_cached(exchange, sym, force=force)
    if sym in pos_map:
        return float(pos_map[sym]['qty'])
    return 0.0


def _fake_pos_list(exchange, sym: str, force: bool = False):
    """
    [FIX-09-PROPER] Returns list-of-dict with the EXACT shape of
    _fake_pos_list(exchange, sym). Preserves downstream iteration:

        for _p in <result>:
            amt = float(_p['info'].get('positionAmt', 0) or 0)
            ...

    If no position exists for sym, returns [].
    """
    m = _fetch_positions_cached(exchange, sym, force=force)
    if sym not in m:
        return []
    v = m[sym]
    return [{
        'symbol': sym,
        'info': {
            'positionAmt': (v['qty'] if v['side'] == 'BUY' else -v['qty']),
            'entryPrice': v.get('entry', 0),
            'liquidationPrice': v.get('liquidationPrice', 0),
            'leverage': v.get('leverage', 0),
            'markPrice': v.get('markPrice', 0),
        },
    }]


def _pos_cache_log_stats() -> None:
    """[FIX-09-PROPER] Log position-cache stats every 5 minutes."""
    now = time.time()
    if now - float(_POSITION_CACHE_STATS.get('last_report_ts', 0.0)) < 300:
        return
    _POSITION_CACHE_STATS['last_report_ts'] = now
    h = _POSITION_CACHE_STATS['hits']
    m = _POSITION_CACHE_STATS['misses']
    api = _POSITION_CACHE_STATS['api_calls']
    err = _POSITION_CACHE_STATS['errors']
    inv = _POSITION_CACHE_STATS['invalidations']
    total = h + m
    if total == 0:
        return
    hr = 100.0 * h / total
    log.info(f"[PosCache] hits={h}, misses={m} ({hr:.0f}%), "
             f"api_calls={api}, invalidations={inv}, errors={err}")


# ══ end FIX-09-PROPER helpers ══


# ══════════════════════════════════════════════════════════════════════
# [MFAL] Multi-Factor Adaptive Leverage
# ══════════════════════════════════════════════════════════════════════
#
# Philosophy:
#   Leverage is NOT a single number derived from one formula.
#   It is a DECISION that fuses multiple independent factors:
#
#       L_final = L_core × Q × R × T × M
#
#   where:
#     L_core = physical base (capital + liquidity)
#     Q      = signal quality (learned weights)
#     R      = portfolio capacity (corr, heat, dd, perf)
#     T      = time-of-day liquidity multiplier
#     M      = micro-structure (spread / depth) multiplier
#
#   Hard constraints (Liq cap, symbol max, L_min) applied LAST.
#
# Default state: DISABLED. Enable via --mfal flag.

_MFAL_ENABLED: bool = False
_MFAL_USE_MICRO: bool = True
_MFAL_USE_TIME: bool = True
_MFAL_USE_LEARNING: bool = True
_MFAL_MIN_TRADES_FOR_LEARNING: int = 200
_MFAL_RETRAIN_EVERY: int = 50

_MFAL_WEIGHTS_PATH: str = "mfal_weights.json"
_MFAL_HISTORY_PATH: str = "mfal_history.jsonl"
_MFAL_FEATURE_KEYS = [
    "score", "p_act", "accel_ratio",
    "gauge", "z_dev", "rr", "freshness",
]
_MFAL_DEFAULT_WEIGHTS = np.array(
    [0.30, 0.25, 0.15, 0.10, 0.10, 0.05, 0.05],
    dtype=np.float64,
)
_MFAL_WEIGHTS: np.ndarray = _MFAL_DEFAULT_WEIGHTS.copy()
_MFAL_BIAS: float = 0.0

_MFAL_STATS: Dict = {
    "compute_calls": 0,
    "q_min": float("inf"),
    "q_max": float("-inf"),
    "q_sum": 0.0,
    "r_min": float("inf"),
    "r_max": float("-inf"),
    "r_sum": 0.0,
    "l_core_sum": 0.0,
    "l_final_sum": 0.0,
    "trades_recorded": 0,
    "retrains": 0,
    "last_report_ts": 0.0,
}
_MFAL_RECENT_R: List[float] = []   # آخر 50 نتيجة R-multiple


# ──────────────────────────────────────────────────────────────────────
# Load / Save weights
# ──────────────────────────────────────────────────────────────────────

def _mfal_load_weights(path: Optional[str] = None):
    global _MFAL_WEIGHTS, _MFAL_BIAS
    p = path or _MFAL_WEIGHTS_PATH
    if not os.path.exists(p):
        log.info(f"[MFAL] No weights file at {p} — using defaults")
        return False
    try:
        with open(p, "r") as f:
            data = json.load(f)
        w = data.get("weights", None)
        b = float(data.get("bias", 0.0))
        if w is None or len(w) != len(_MFAL_FEATURE_KEYS):
            log.warning(f"[MFAL] Invalid weights shape in {p}")
            return False
        _MFAL_WEIGHTS = np.array(w, dtype=np.float64)
        _MFAL_BIAS = b
        log.info(f"[MFAL] Loaded weights from {p}: "
                 f"norm={np.linalg.norm(_MFAL_WEIGHTS):.4f}")
        return True
    except Exception as e:
        log.warning(f"[MFAL] Load failed: {e}")
        return False


def _mfal_save_weights(path: Optional[str] = None):
    p = path or _MFAL_WEIGHTS_PATH
    try:
        payload = {
            "weights": _MFAL_WEIGHTS.tolist(),
            "bias": float(_MFAL_BIAS),
            "features": list(_MFAL_FEATURE_KEYS),
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "n_trades_at_save": int(_MFAL_STATS.get("trades_recorded", 0)),
        }
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, p)
        log.debug(f"[MFAL] Weights saved to {p}")
    except Exception as e:
        log.warning(f"[MFAL] Save failed: {e}")


# ──────────────────────────────────────────────────────────────────────
# Feature extraction
# ──────────────────────────────────────────────────────────────────────

def _mfal_signal_features(score, p_act, accel_ratio, gauge,
                          z_dev, rr):
    """
    [MFAL] 7-dimensional feature vector from signal-time data.
    All features normalized to roughly [-1, +1] or [0, 1].
    """
    try:
        x = np.array([
            float(score) / 8.0,
            float(p_act),
            float(np.tanh(accel_ratio / 3.0)),
            float(np.tanh(gauge * 10.0)),
            float(np.tanh(abs(z_dev) / 2.0)),
            float(np.tanh(rr / 3.0)),
            1.0,   # freshness (1.0 for fresh signal)
        ], dtype=np.float64)
        if not np.all(np.isfinite(x)):
            return None
        return x
    except Exception:
        return None


def _mfal_quality(x: Optional[np.ndarray]) -> float:
    """Q = 0.4 + 1.4·σ(w·x), range [0.4, 1.8]."""
    if x is None:
        return 1.0
    try:
        z = float(np.dot(_MFAL_WEIGHTS, x)) + _MFAL_BIAS
        s = 1.0 / (1.0 + np.exp(-np.clip(z, -20.0, 20.0)))
        q = 0.4 + 1.4 * s
        return float(np.clip(q, 0.40, 1.80))
    except Exception:
        return 1.0


def _mfal_time_factor(now_ts: Optional[float] = None) -> float:
    """
    Time-of-day multiplier. Based on typical crypto liquidity:
      Asia night (0-3):    0.75 - 0.85
      London open (7-10):  0.95 - 1.05
      LD/NY overlap (13-16): 1.10 - 1.15
      NY close (20-23):    0.85 - 0.90
    """
    try:
        if now_ts is None:
            now_ts = time.time()
        h = datetime.utcfromtimestamp(now_ts).hour
        table = {
            0: 0.85, 1: 0.80, 2: 0.75, 3: 0.75,
            4: 0.80, 5: 0.85, 6: 0.90, 7: 0.95,
            8: 1.00, 9: 1.05, 10: 1.05, 11: 1.00,
            12: 1.05, 13: 1.10, 14: 1.15, 15: 1.15,
            16: 1.10, 17: 1.05, 18: 1.00, 19: 0.95,
            20: 0.90, 21: 0.90, 22: 0.85, 23: 0.85,
        }
        return float(table.get(h, 1.0))
    except Exception:
        return 1.0


def _mfal_micro_factor(exchange, sym: str) -> float:
    """
    Micro-structure multiplier from current book.
    Uses 5-level book (weight ~5).
    """
    if not _MFAL_USE_MICRO:
        return 1.0
    try:
        ob = exchange.fetch_order_book(sym, limit=5)
        bids = ob.get("bids") or []
        asks = ob.get("asks") or []
        if not bids or not asks:
            return 1.0
        bb = float(bids[0][0])
        ba = float(asks[0][0])
        if bb <= 0 or ba <= 0 or ba < bb:
            return 1.0
        mid = (bb + ba) / 2.0
        spread_bps = (ba - bb) / mid * 1e4

        # depth of top 5 levels
        depth_bid = sum(float(x[1]) for x in bids[:5]) * bb
        depth_ask = sum(float(x[1]) for x in asks[:5]) * ba
        depth_usd = (depth_bid + depth_ask) / 2.0

        # Typical thresholds (very conservative baselines)
        typical_spread = 3.0    # bps
        typical_depth  = 1.0e5  # USD

        f_spread = float(np.clip(
            (typical_spread / max(spread_bps, 0.1)) ** 0.5,
            0.60, 1.20,
        ))
        f_depth = float(np.clip(
            (depth_usd / typical_depth) ** 0.30,
            0.70, 1.10,
        ))
        return float(np.clip(f_spread * f_depth, 0.42, 1.32))
    except Exception as e:
        log.debug(f"[MFAL] micro_factor failed for {sym}: {e}")
        return 1.0


def _mfal_portfolio_factor(sym: str,
                            open_pos_live: Dict,
                            capital: float,
                            peak_capital: float,
                            corr_cache: Dict) -> float:
    """
    Portfolio capacity multiplier:
        R = R_corr × R_heat × R_dd × R_perf
    """
    try:
        # ── R_corr: max correlation with existing positions ──
        if open_pos_live and corr_cache:
            rho_max = 0.0
            for other in open_pos_live.keys():
                rho = abs(float(corr_cache.get((sym, other), 0.0)))
                if rho > rho_max:
                    rho_max = rho
            R_corr = 1.0 - 0.5 * rho_max
        else:
            R_corr = 1.0

        # ── R_heat: portfolio heat usage ──
        heat_max = float(getattr(CFG, "PORTFOLIO_HEAT_MAX", 0.10))
        heat_used = 0.0
        for p in open_pos_live.values():
            try:
                heat_used += float(p.get("dyn_risk", 0.0) or 0.0)
            except Exception:
                pass
        if heat_max > 1e-9:
            R_heat = 1.0 - 0.4 * min(1.0, heat_used / heat_max)
        else:
            R_heat = 1.0

        # ── R_dd: current drawdown ──
        if peak_capital > 1e-9:
            dd = max(0.0, (peak_capital - capital) / peak_capital)
        else:
            dd = 0.0
        R_dd = float(np.exp(-3.0 * dd))

        # ── R_perf: recent rolling Sharpe ──
        if len(_MFAL_RECENT_R) >= 10:
            r = np.array(_MFAL_RECENT_R[-50:], dtype=np.float64)
            mu = float(np.mean(r))
            sd = float(np.std(r, ddof=1)) if len(r) > 1 else 0.0
            if sd > 1e-9:
                sharpe = mu / sd * np.sqrt(len(r))
            else:
                sharpe = 0.0
            R_perf = float(np.clip(0.9 + 0.1 * sharpe, 0.70, 1.20))
        else:
            R_perf = 1.0

        R = R_corr * R_heat * R_dd * R_perf
        return float(np.clip(R, 0.30, 1.30))
    except Exception as e:
        log.debug(f"[MFAL] portfolio_factor failed: {e}")
        return 1.0


# ──────────────────────────────────────────────────────────────────────
# Main entry — combines everything
# ──────────────────────────────────────────────────────────────────────

def compute_adaptive_leverage(symbol: str,
                                sig,
                                open_pos_live: Optional[Dict],
                                capital: float,
                                peak_capital: float,
                                corr_cache: Optional[Dict],
                                exchange,
                                cfg) -> int:
    """
    [MFAL] Adaptive leverage:
        L_final = clamp(L_core × Q × R × T × M, L_min, min(L_liq, L_sym))
    """
    # ── 1. Core (unchanged physics) ──
    L_core = int(compute_dynamic_leverage(capital, cfg, symbol=symbol))

    if not _MFAL_ENABLED:
        return L_core

    # ── 2. Quality factor ──
    x = getattr(sig, "mfal_x", None) if sig is not None else None
    Q = _mfal_quality(x)

    # ── 3. Risk factor ──
    R = _mfal_portfolio_factor(
        sym=symbol,
        open_pos_live=open_pos_live or {},
        capital=capital,
        peak_capital=peak_capital,
        corr_cache=corr_cache or {},
    )

    # ── 4. Time factor ──
    T = _mfal_time_factor() if _MFAL_USE_TIME else 1.0

    # ── 5. Micro factor ──
    M = _mfal_micro_factor(exchange, symbol) if _MFAL_USE_MICRO else 1.0

    # ── 6. Score product ──
    L_scored = L_core * Q * R * T * M

    # ── 7. Hard constraints ──
    try:
        _mmr = _get_mmr_for_symbol(exchange, symbol)
        _sl_frac_max = 0.015 * float(
            getattr(cfg, "SL_WIDEN_MULT", 1.5)
        )
        L_liq = int(compute_max_leverage_by_liq(
            sl_frac_max=_sl_frac_max,
            mmr=_mmr,
            safety_mult=float(getattr(cfg, "LIQ_SAFETY_MULT", 1.5)),
            symbol=symbol,
        ))
    except Exception:
        L_liq = int(cfg.LEVERAGE_MAX)

    try:
        L_sym = int(max(_symbol_tiers(symbol, cfg)))
    except Exception:
        L_sym = int(cfg.LEVERAGE_MAX)

    L_min = int(cfg.LEVERAGE_MIN)
    L_final = int(np.floor(L_scored))
    L_final = max(L_min, min(L_final, L_liq, L_sym))

    # ── 8. Snap to tiers ──
    try:
        tiers = _symbol_tiers(symbol, cfg)
        valid = [int(t) for t in tiers
                 if L_min <= int(t) <= L_final]
        if valid:
            L_final = int(valid[-1])
        else:
            L_final = L_min
    except Exception:
        pass

    # ── 9. Stats ──
    _MFAL_STATS["compute_calls"] += 1
    _MFAL_STATS["q_min"] = min(_MFAL_STATS["q_min"], Q)
    _MFAL_STATS["q_max"] = max(_MFAL_STATS["q_max"], Q)
    _MFAL_STATS["q_sum"] += Q
    _MFAL_STATS["r_min"] = min(_MFAL_STATS["r_min"], R)
    _MFAL_STATS["r_max"] = max(_MFAL_STATS["r_max"], R)
    _MFAL_STATS["r_sum"] += R
    _MFAL_STATS["l_core_sum"] += L_core
    _MFAL_STATS["l_final_sum"] += L_final

    if Q < 0.7 or Q > 1.4 or R < 0.7:
        log.info(
            f"[MFAL] {symbol} L={L_final}x "
            f"(core={L_core}, Q={Q:.2f}, R={R:.2f}, "
            f"T={T:.2f}, M={M:.2f})"
        )

    return int(L_final)


# ──────────────────────────────────────────────────────────────────────
# Trade recording + online learning
# ──────────────────────────────────────────────────────────────────────

def _mfal_record_trade(sig, outcome_R: float, success: bool):
    """يُسجّل نتيجة صفقة في history ويُحدّث stats."""
    try:
        x = getattr(sig, "mfal_x", None) if sig is not None else None
        if x is None:
            return
        record = {
            "ts": time.time(),
            "symbol": str(getattr(sig, "symbol", "?")),
            "x": x.tolist(),
            "outcome_R": float(outcome_R),
            "success": bool(success),
        }
        try:
            with open(_MFAL_HISTORY_PATH, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass

        _MFAL_RECENT_R.append(float(outcome_R))
        if len(_MFAL_RECENT_R) > 200:
            _MFAL_RECENT_R[:] = _MFAL_RECENT_R[-100:]

        _MFAL_STATS["trades_recorded"] += 1

        # Trigger retrain if enough new trades
        if (_MFAL_USE_LEARNING
                and _MFAL_STATS["trades_recorded"]
                    >= _MFAL_MIN_TRADES_FOR_LEARNING
                and _MFAL_STATS["trades_recorded"]
                    % _MFAL_RETRAIN_EVERY == 0):
            _mfal_retrain()
    except Exception as e:
        log.debug(f"[MFAL] record_trade failed: {e}")


def _mfal_retrain():
    """يعيد تدريب الأوزان من history عبر logistic regression."""
    if not os.path.exists(_MFAL_HISTORY_PATH):
        return
    try:
        X, y = [], []
        with open(_MFAL_HISTORY_PATH) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                x = r.get("x")
                if not isinstance(x, list):
                    continue
                if len(x) != len(_MFAL_FEATURE_KEYS):
                    continue
                X.append(x)
                y.append(1.0 if r.get("success") else 0.0)
        if len(X) < _MFAL_MIN_TRADES_FOR_LEARNING:
            return

        Xa = np.array(X, dtype=np.float64)
        ya = np.array(y, dtype=np.float64)

        # Basic sanity: must have both classes
        if ya.sum() < 20 or (1.0 - ya).sum() < 20:
            return

        # Simple logistic regression via scipy
        from scipy.optimize import minimize as _scipy_min

        def _loss(params):
            w = params[:-1]
            b = params[-1]
            z = Xa @ w + b
            # stable sigmoid
            p = np.where(z >= 0,
                          1.0 / (1.0 + np.exp(-z)),
                          np.exp(z) / (1.0 + np.exp(z)))
            eps = 1e-9
            p = np.clip(p, eps, 1.0 - eps)
            nll = -np.mean(ya * np.log(p) + (1 - ya) * np.log(1 - p))
            # L2 regularization
            reg = 0.1 * float(np.sum(w * w))
            return float(nll + reg)

        x0 = np.concatenate([_MFAL_WEIGHTS, [_MFAL_BIAS]])
        res = _scipy_min(_loss, x0, method="L-BFGS-B",
                          options={"maxiter": 100})

        w_new = res.x[:-1]
        b_new = float(res.x[-1])

        # Blend: 80% old, 20% new  (conservative)
        _MFAL_WEIGHTS = 0.8 * _MFAL_WEIGHTS + 0.2 * w_new
        _MFAL_BIAS = 0.8 * _MFAL_BIAS + 0.2 * b_new

        _MFAL_STATS["retrains"] += 1
        _mfal_save_weights()
        log.info(
            f"[MFAL] Retrained #{_MFAL_STATS['retrains']} "
            f"(n={len(X)}, loss={_loss(res.x):.4f}) "
            f"w_norm={np.linalg.norm(_MFAL_WEIGHTS):.4f}"
        )
    except Exception as e:
        log.warning(f"[MFAL] retrain failed: {e}")


def _mfal_log_stats():
    """طبع إحصائيات MFAL كل 5 دقائق."""
    if not _MFAL_ENABLED:
        return
    now = time.time()
    if now - _MFAL_STATS.get("last_report_ts", 0.0) < 300:
        return
    _MFAL_STATS["last_report_ts"] = now
    n = max(_MFAL_STATS["compute_calls"], 1)
    log.info(
        f"[MFAL] calls={n}, "
        f"Q=[{_MFAL_STATS['q_min']:.2f},{_MFAL_STATS['q_max']:.2f}] "
        f"μ={_MFAL_STATS['q_sum']/n:.2f}, "
        f"R=[{_MFAL_STATS['r_min']:.2f},{_MFAL_STATS['r_max']:.2f}] "
        f"μ={_MFAL_STATS['r_sum']/n:.2f}, "
        f"L_core_avg={_MFAL_STATS['l_core_sum']/n:.2f}, "
        f"L_final_avg={_MFAL_STATS['l_final_sum']/n:.2f}, "
        f"trades={_MFAL_STATS['trades_recorded']}, "
        f"retrains={_MFAL_STATS['retrains']}"
    )


# ══ end MFAL block ══


# ══════════════════════════════════════════════════════════════════════
# [UNIFIED DECISION ENGINE] — v1
# ══════════════════════════════════════════════════════════════════════
#
# A single constrained Bayesian optimizer that replaces:
#     risk pipeline (8 layers) → leverage pipeline (3 layers) → min()
#
# With:
#     argmax_{qty, L, accept}  a · E[ log W_T | state ]
#     subject to all constraints SIMULTANEOUSLY
#
# Design principles:
#   1. No sequential pipeline — one decision.
#   2. No hardcoded constants — everything derived from history,
#      capital, and exchange rules (MVT, tiers, MMR).
#   3. Bayesian edge estimation (learns from outcomes).
#   4. Scale-invariant (works for $1 and $1M alike).
#
# Only three "philosophical" inputs remain (owner's choices):
#     • ε  (ruin tolerance)      — default 0.001
#     • λ  (Kelly shrinkage)     — default 0.5
#     • k  (Liq safety margin)   — default 1.5
#
# Default: DISABLED. Enable with --unified flag.

_UNIFIED_ENABLED: bool = False
_UNIFIED_EPSILON: float = 0.001
_UNIFIED_SHRINKAGE: float = 0.5
_UNIFIED_LIQ_SAFETY: float = 1.5
_UNIFIED_KAPPA_BASE: float = 0.01
_UNIFIED_RETRAIN_EVERY: int = 30
_UNIFIED_MIN_TRADES: int = 50

_UNIFIED_STATE: Dict = {
    "feature_names": [
        "score_norm", "p_act", "accel_ratio",
        "gauge", "z_dev", "rr", "freshness",
    ],
    "w_mean": [0.30, 0.25, 0.15, 0.10, 0.10, 0.05, 0.05],
    "w_precision_diag": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    "bias": 0.0,
    "n_observations": 0,
    "recent_R": [],
    "recent_wins": [],
}

_UNIFIED_WEIGHTS_PATH: str = "unified_weights.json"
_UNIFIED_HISTORY_PATH: str = "unified_history.jsonl"

_UNIFIED_STATS: Dict = {
    "calls": 0, "accepts": 0, "rejects": 0,
    "qty_sum": 0.0, "L_sum": 0, "f_sum": 0.0,
    "reject_reasons": {},
    "last_report_ts": 0.0,
    "trades_recorded": 0,
    "retrains": 0,
}


# ──────────────────────────────────────────────────────────────────────
# State persistence
# ──────────────────────────────────────────────────────────────────────

def _unified_load_state(path: Optional[str] = None) -> bool:
    global _UNIFIED_STATE
    p = path or _UNIFIED_WEIGHTS_PATH
    if not os.path.exists(p):
        log.info(f"[Unified] No state at {p} — using prior")
        return False
    try:
        with open(p) as f:
            data = json.load(f)
        for k in ("w_mean", "w_precision_diag", "bias",
                  "n_observations", "recent_R", "recent_wins"):
            if k in data:
                _UNIFIED_STATE[k] = data[k]
        log.info(f"[Unified] State loaded: n_obs="
                 f"{_UNIFIED_STATE['n_observations']}, "
                 f"|w|={np.linalg.norm(_UNIFIED_STATE['w_mean']):.4f}")
        return True
    except Exception as e:
        log.warning(f"[Unified] Load failed: {e}")
        return False


def _unified_save_state(path: Optional[str] = None):
    p = path or _UNIFIED_WEIGHTS_PATH
    try:
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_UNIFIED_STATE, f, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        log.debug(f"[Unified] Save failed: {e}")


# ──────────────────────────────────────────────────────────────────────
# Derived parameters — no hardcoded constants
# ──────────────────────────────────────────────────────────────────────

def _unified_compute_mvt(exchange, sym: str, price: float) -> float:
    """Dynamic MVT per symbol/price. Falls back to MIN_NOTIONAL."""
    if price <= 0:
        return float(getattr(CFG, "MIN_NOTIONAL", 5.0))
    try:
        mkt = exchange.market(sym)
        if not mkt:
            raise ValueError("no market")
        info = mkt.get("info") or {}
        filters = {}
        for f in (info.get("filters") or []):
            ft = f.get("filterType")
            if ft:
                filters[ft] = f
        min_notional = float(
            (filters.get("MIN_NOTIONAL") or {}).get("notional", 5.0) or 5.0
        )
        lot = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE") or {}
        min_qty = float(lot.get("minQty", 0) or 0)
        step_size = float(lot.get("stepSize", 0) or 0)
        return float(max(
            min_notional,
            min_qty * price if min_qty > 0 else 0.0,
            step_size * price if step_size > 0 else 0.0,
        ))
    except Exception:
        return float(getattr(CFG, "MIN_NOTIONAL", 5.0))


def _unified_get_adv(sym: str, ad) -> float:
    try:
        if ad is not None and hasattr(ad, "adv_usd") and len(ad.adv_usd) > 0:
            adv = float(ad.adv_usd[-1])
            if np.isfinite(adv) and adv > 0:
                return adv
    except Exception:
        pass
    return 1e8


def _unified_get_mmr(exchange, sym: str) -> float:
    try:
        return float(_get_mmr_for_symbol(exchange, sym))
    except Exception:
        return float(getattr(CFG, "LIQ_FALLBACK_MMR", 0.02))


def _unified_compute_H_max() -> float:
    """H_max = 2·E[r]/E[r²]·(1-ε), from historical R-multiples."""
    recent = _UNIFIED_STATE.get("recent_R", [])
    if len(recent) < 20:
        return 0.05
    r = np.array(recent[-100:], dtype=np.float64)
    mean_r = float(np.mean(r))
    mean_r2 = float(np.mean(r * r))
    if mean_r <= 0 or mean_r2 <= 1e-9:
        return 0.02
    h = 2.0 * mean_r / mean_r2 * (1.0 - _UNIFIED_EPSILON)
    return float(np.clip(h, 0.01, 0.50))


def _unified_compute_kappa(adv_usd: float, max_slip_bps: float = 5.0) -> float:
    slip_factor = max_slip_bps / 5.0
    return float(np.clip(_UNIFIED_KAPPA_BASE * slip_factor, 0.001, 0.05))


def _unified_compute_L_liq_max(mmr: float, f_sl: float) -> int:
    try:
        return int(compute_max_leverage_by_liq(
            sl_frac_max=f_sl, mmr=mmr,
            safety_mult=_UNIFIED_LIQ_SAFETY,
        ))
    except Exception:
        return int(getattr(CFG, "LEVERAGE_MAX", 50))


# ──────────────────────────────────────────────────────────────────────
# Bayesian edge
# ──────────────────────────────────────────────────────────────────────

def _unified_sigmoid(z):
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def _unified_bayesian_edge(x: Optional[np.ndarray]):
    """Return (p_hat, var_p) via Laplace approximation."""
    if x is None or len(x) != len(_UNIFIED_STATE["feature_names"]):
        return 0.5, 0.25
    w = np.array(_UNIFIED_STATE["w_mean"], dtype=np.float64)
    prec = np.array(_UNIFIED_STATE["w_precision_diag"], dtype=np.float64)
    bias = float(_UNIFIED_STATE["bias"])
    z = float(np.dot(w, x)) + bias
    var_z = float(np.sum((x ** 2) / np.maximum(prec, 1e-6)))
    p_hat = float(_unified_sigmoid(z))
    var_p = p_hat * (1 - p_hat) + (p_hat * (1 - p_hat)) ** 2 * var_z * (np.pi / 8)
    return p_hat, float(np.clip(var_p, 1e-4, 0.25))


def _unified_kelly_bayes(p_hat: float, var_p: float, rr: float) -> float:
    p = float(np.clip(p_hat, 1e-6, 1.0 - 1e-6))
    q = 1.0 - p
    if rr <= 0 or p <= 0.01:
        return 0.0
    denom = p * rr * rr + q
    f_kelly = max(0.0, (p * rr - q) / denom) if denom > 1e-9 else 0.0
    pq = p * q
    penalty = max(0.0, 1.0 - var_p / pq) if pq > 1e-9 else 1.0
    return float(np.clip(f_kelly * penalty * _UNIFIED_SHRINKAGE, 0.0, 0.20))


# ──────────────────────────────────────────────────────────────────────
# Signal features
# ──────────────────────────────────────────────────────────────────────

def _unified_signal_x(sig, ad, fi):
    """7-dim feature vector."""
    try:
        score = float(getattr(sig, "score", 0.0))
        p_act = getattr(sig, "mfal_p_act", None)
        if p_act is None or p_act <= 0:
            try:
                geo = abs(float(ad.geodesic_accel[fi]))
                fric = float(ad.friction[fi]) + 1e-6
                T_info = float(ad.T_info[fi])
                p_act = float(np.exp(-fric / (max(geo, 1e-9) * T_info)))
            except Exception:
                p_act = 0.5
        try:
            accel_ratio = abs(float(ad.geodesic_accel[fi])) / max(float(ad.friction[fi]), 1e-9)
        except Exception:
            accel_ratio = 1.0
        try:
            gauge = float(ad.gauge_force[fi])
        except Exception:
            gauge = 0.0
        try:
            _zw = ad.closes[max(0, fi - 24): fi]
            if len(_zw) >= 2:
                _mu = float(np.mean(_zw))
                _sd = float(np.std(_zw)) + 1e-9
                z_dev = (float(ad.closes[fi]) - _mu) / _sd
            else:
                z_dev = 0.0
        except Exception:
            z_dev = 0.0
        try:
            entry = float(sig.price); sl = float(sig.sl); tp = float(sig.tp1)
            sl_dist = abs(entry - sl)
            tp_dist = abs(tp - entry)
            rr = tp_dist / max(sl_dist, 1e-9)
        except Exception:
            rr = 2.0
        x = np.array([
            score / 8.0,
            float(np.clip(p_act, 0.0, 1.0)),
            float(np.tanh(accel_ratio / 3.0)),
            float(np.tanh(gauge * 10.0)),
            float(np.tanh(abs(z_dev) / 2.0)),
            float(np.tanh(rr / 3.0)),
            1.0,
        ], dtype=np.float64)
        return x if np.all(np.isfinite(x)) else None
    except Exception:
        return None


def _unified_get_f_sl(sig) -> float:
    try:
        entry = float(sig.price); sl = float(sig.sl)
        if entry <= 0:
            return 0.02
        return float(np.clip(abs(entry - sl) / entry, 0.001, 0.10))
    except Exception:
        return 0.02


def _unified_get_rr(sig) -> float:
    try:
        entry = float(sig.price); sl = float(sig.sl); tp = float(sig.tp1)
        return float(abs(tp - entry) / max(abs(entry - sl), 1e-9))
    except Exception:
        return 2.0


# ──────────────────────────────────────────────────────────────────────
# MAIN: Unified Decision
# ──────────────────────────────────────────────────────────────────────

def compute_unified_decision(sym, sig, capital, peak, open_pos_live,
                              corr_cache, exchange, ad, cfg) -> Dict:
    """
    Returns:
        {
            "accept": bool,
            "qty": float, "leverage": int, "f_actual": float,
            "reason": str, "candidates": list,
        }
    """
    _UNIFIED_STATS["calls"] += 1
    default = {"accept": False, "qty": 0.0,
               "leverage": int(cfg.LEVERAGE_MIN),
               "f_actual": 0.0, "reason": "uninit", "candidates": []}
    try:
        fi = int(getattr(sig, "feat_idx", 0))
        x = _unified_signal_x(sig, ad, fi)
        p_hat, var_p = _unified_bayesian_edge(x)
        rr = _unified_get_rr(sig)

        f_kelly = _unified_kelly_bayes(p_hat, var_p, rr)
        if f_kelly <= 0.0:
            r = f"no_edge(p={p_hat:.3f},rr={rr:.2f})"
            default["reason"] = r
            _UNIFIED_STATS["rejects"] += 1
            _UNIFIED_STATS["reject_reasons"][r] = \
                _UNIFIED_STATS["reject_reasons"].get(r, 0) + 1
            return default

        f_sl = _unified_get_f_sl(sig)
        price = float(getattr(sig, "price", 0.0))
        if price <= 0:
            default["reason"] = "invalid_price"
            return default

        MVT = _unified_compute_mvt(exchange, sym, price) if exchange is not None \
              else float(getattr(cfg, "MIN_NOTIONAL", 5.0))
        adv = _unified_get_adv(sym, ad)
        kappa = _unified_compute_kappa(adv, 5.0)
        mmr = _unified_get_mmr(exchange, sym) if exchange is not None \
              else float(getattr(cfg, "LIQ_FALLBACK_MMR", 0.02))
        L_liq_max = _unified_compute_L_liq_max(mmr, f_sl)
        H_max = _unified_compute_H_max()

        free_capital = float(capital)
        for pos in open_pos_live.values():
            try:
                pn = float(pos.get("entry", 0)) * float(pos.get("qty", 0))
                pL = max(int(pos.get("leverage", 1)), 1)
                free_capital -= pn / pL
            except Exception:
                pass
        free_capital = max(0.0, free_capital)

        heat_used = 0.0
        for pos in open_pos_live.values():
            try:
                heat_used += float(pos.get("dyn_risk", 0.0) or 0.0)
            except Exception:
                pass

        try:
            # [UNIFIED-BT] tiers always from _symbol_tiers
            # (works with exchange=None because _symbol_tiers
            #  reads from _SYMBOL_LEV_TIERS populated by prefetch)
            tiers = _symbol_tiers(sym, cfg)
        except Exception:
            tiers = [int(cfg.LEVERAGE_MIN), int(cfg.LEVERAGE_MAX)]

        candidates = []
        for L in tiers:
            L = int(L)
            if L > L_liq_max: continue
            if L < int(cfg.LEVERAGE_MIN): continue

            N_by_margin = L * free_capital
            heat_av = max(0.0, H_max - heat_used)
            N_by_heat = heat_av * capital / f_sl
            N_by_adv = kappa * adv
            N_by_abs = float(getattr(cfg, "MAX_ABS_NOTIONAL", 1e9))

            N_upper = min(N_by_margin, N_by_heat, N_by_adv, N_by_abs)
            N_lower = MVT
            if N_lower > N_upper:
                continue

            N_target = f_kelly * capital / f_sl
            N_opt = float(np.clip(N_target, N_lower, N_upper))
            f_actual = N_opt * f_sl / capital
            U = (p_hat * np.log(1 + f_actual * rr)
                 + (1 - p_hat) * np.log(max(1 - f_actual, 1e-9)))
            p_ruin = (f_actual / 0.20) ** 3 if f_actual > 0 else 1.0
            if p_ruin > _UNIFIED_EPSILON:
                continue
            candidates.append({"leverage": L, "N_opt": N_opt,
                                "f_actual": f_actual, "U": U})

        if not candidates:
            r = "no_feasible"
            default["reason"] = r
            _UNIFIED_STATS["rejects"] += 1
            _UNIFIED_STATS["reject_reasons"][r] = \
                _UNIFIED_STATS["reject_reasons"].get(r, 0) + 1
            return default

        best = max(candidates, key=lambda c: c["U"])
        best_U = best["U"]
        for c in candidates:
            if abs(c["U"] - best_U) < 1e-6 and c["leverage"] < best["leverage"]:
                best = c

        qty = best["N_opt"] / price
        try:
            if exchange is not None:
                qty = _round_qty(exchange, sym, qty)
        except Exception:
            pass

        if qty <= 0:
            default["reason"] = "zero_qty"
            return default
        if qty * price < MVT * 0.99:
            r = f"qty_below_mvt({qty*price:.2f}<{MVT:.2f})"
            default["reason"] = r
            _UNIFIED_STATS["rejects"] += 1
            _UNIFIED_STATS["reject_reasons"][r] = \
                _UNIFIED_STATS["reject_reasons"].get(r, 0) + 1
            return default

        result = {
            "accept": True, "qty": qty,
            "leverage": int(best["leverage"]),
            "f_actual": float(best["f_actual"]),
            "reason": f"U={best['U']:+.4f} p={p_hat:.3f} rr={rr:.2f}",
            "candidates": candidates,
        }
        _UNIFIED_STATS["accepts"] += 1
        _UNIFIED_STATS["qty_sum"] += qty
        _UNIFIED_STATS["L_sum"] += best["leverage"]
        _UNIFIED_STATS["f_sum"] += best["f_actual"]

        log.debug(
            f"[Unified] {sym} ACCEPT qty={qty:.6f} L={best['leverage']}x "
            f"f={best['f_actual']*100:.2f}% "
            f"(p={p_hat:.3f} RR={rr:.2f})"
        )
        return result
    except Exception as e:
        log.warning(f"[Unified] {sym} error: {e}")
        return default


# ──────────────────────────────────────────────────────────────────────
# Recording + Retraining
# ──────────────────────────────────────────────────────────────────────

def _unified_record_trade(sig, ad, outcome_R: float, success: bool):
    try:
        fi = int(getattr(sig, "feat_idx", 0)) if sig is not None else 0
        x = _unified_signal_x(sig, ad, fi) if sig is not None else None
        if x is None:
            return
        try:
            with open(_UNIFIED_HISTORY_PATH, "a") as f:
                f.write(json.dumps({
                    "ts": time.time(),
                    "symbol": str(getattr(sig, "symbol", "?")),
                    "x": x.tolist(),
                    "outcome_R": float(outcome_R),
                    "success": bool(success),
                }) + "\n")
        except Exception:
            pass

        _UNIFIED_STATE["n_observations"] += 1
        _UNIFIED_STATE["recent_R"].append(float(outcome_R))
        _UNIFIED_STATE["recent_wins"].append(1 if success else 0)
        if len(_UNIFIED_STATE["recent_R"]) > 200:
            _UNIFIED_STATE["recent_R"] = _UNIFIED_STATE["recent_R"][-100:]
            _UNIFIED_STATE["recent_wins"] = _UNIFIED_STATE["recent_wins"][-100:]
        _UNIFIED_STATS["trades_recorded"] += 1

        if (_UNIFIED_STATS["trades_recorded"] >= _UNIFIED_MIN_TRADES
                and _UNIFIED_STATS["trades_recorded"] % _UNIFIED_RETRAIN_EVERY == 0):
            _unified_retrain()
            _unified_save_state()
    except Exception as e:
        log.debug(f"[Unified] record failed: {e}")


def _unified_retrain():
    if not os.path.exists(_UNIFIED_HISTORY_PATH):
        return
    try:
        Xl, yl = [], []
        with open(_UNIFIED_HISTORY_PATH) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                xv = r.get("x")
                if not isinstance(xv, list): continue
                if len(xv) != len(_UNIFIED_STATE["feature_names"]): continue
                Xl.append(xv); yl.append(1.0 if r.get("success") else 0.0)
        if len(Xl) < _UNIFIED_MIN_TRADES:
            return
        X = np.array(Xl); y = np.array(yl)
        if y.sum() < 10 or (1 - y).sum() < 10:
            return
        w = np.array(_UNIFIED_STATE["w_mean"], dtype=np.float64)
        b = float(_UNIFIED_STATE["bias"])
        for _ in range(50):
            p = _unified_sigmoid(X @ w + b)
            grad_w = X.T @ (p - y) / len(y) + 0.05 * w
            grad_b = float(np.mean(p - y))
            w -= 0.01 * grad_w
            b -= 0.01 * grad_b
        old_w = np.array(_UNIFIED_STATE["w_mean"], dtype=np.float64)
        _UNIFIED_STATE["w_mean"] = (0.8 * old_w + 0.2 * w).tolist()
        _UNIFIED_STATE["bias"] = 0.8 * float(_UNIFIED_STATE["bias"]) + 0.2 * b
        _UNIFIED_STATE["w_precision_diag"] = [
            1.0 + _UNIFIED_STATE["n_observations"] / 100.0 for _ in w
        ]
        _UNIFIED_STATS["retrains"] += 1
        log.info(f"[Unified] Retrain #{_UNIFIED_STATS['retrains']} "
                 f"(n={len(y)}, |w|={np.linalg.norm(w):.4f})")
    except Exception as e:
        log.warning(f"[Unified] Retrain failed: {e}")


def _unified_log_stats():
    if not _UNIFIED_ENABLED:
        return
    now = time.time()
    if now - _UNIFIED_STATS.get("last_report_ts", 0.0) < 300:
        return
    _UNIFIED_STATS["last_report_ts"] = now
    n = max(_UNIFIED_STATS["calls"], 1)
    a = _UNIFIED_STATS["accepts"]
    r = _UNIFIED_STATS["rejects"]
    log.info(
        f"[Unified] calls={n}, accepts={a}, rejects={r}, "
        f"avg_qty={_UNIFIED_STATS['qty_sum']/max(a,1):.4f}, "
        f"avg_L={_UNIFIED_STATS['L_sum']/max(a,1):.1f}x, "
        f"avg_f={_UNIFIED_STATS['f_sum']/max(a,1)*100:.2f}%, "
        f"n_obs={_UNIFIED_STATE['n_observations']}, "
        f"retrains={_UNIFIED_STATS['retrains']}"
    )
    reasons = _UNIFIED_STATS.get("reject_reasons", {})
    if reasons:
        top = sorted(reasons.items(), key=lambda kv: -kv[1])[:3]
        log.info(f"[Unified] top rejects: {top}")


# ══ end UNIFIED DECISION ENGINE ══


def load_symbol_meta(mode: str) -> Dict[str, Dict]:
    """Load persistent {sym: {leverage, margin_mode, setup_done}} from disk."""
    global _SYMBOL_META, _SYMBOL_META_PATH
    _SYMBOL_META_PATH = f"{CFG.SYMBOL_META_FILE}_{mode}.json"
    if os.path.exists(_SYMBOL_META_PATH):
        try:
            with open(_SYMBOL_META_PATH) as f:
                _SYMBOL_META = json.load(f)
            log.info(f"[Meta] Loaded {len(_SYMBOL_META)} symbols from {_SYMBOL_META_PATH}")
        except Exception as e:
            log.warning(f"[Meta] load failed: {e}")
            _SYMBOL_META = {}
    else:
        _SYMBOL_META = {}
    return _SYMBOL_META


def save_symbol_meta() -> None:
    """Persist symbol metadata atomically."""
    if not _SYMBOL_META_PATH:
        return
    try:
        tmp = _SYMBOL_META_PATH + ".tmp"
        with open(tmp, 'w') as f:
            json.dump(_SYMBOL_META, f, indent=2)
        os.replace(tmp, _SYMBOL_META_PATH)
    except Exception as e:
        log.warning(f"[Meta] save failed: {e}")


def ensure_symbol_setup(exchange, sym: str, target_leverage: int,
                        margin_mode: str = 'isolated') -> bool:
    """
    Ensure (leverage, margin_mode) is set for sym.
    CRITICAL: NEVER call set_leverage if a position exists — Binance rejects -4046.
    Returns True if leverage is now confirmed at target (or a safe value).
    """

    # ══ [FIX-01-PROPER] Snap target to the symbol's actual tiers ══
    try:
        if sym not in _SYMBOL_LEV_TIERS:
            _max_lev = fetch_symbol_leverage_tiers(exchange, sym)
            if _max_lev is None:
                _max_lev = _fallback_max_leverage(sym, CFG)
            _register_leverage_tiers(sym, _max_lev)
            log.debug(f"[Setup] {sym} max_leverage={_max_lev}x cached")

        _tiers_for_sym = _SYMBOL_LEV_TIERS[sym][1]
        _snapped = [t for t in _tiers_for_sym
                    if int(t) <= int(target_leverage)]
        if _snapped:
            _new_lev = int(_snapped[-1])
        else:
            _new_lev = int(_tiers_for_sym[0]) if _tiers_for_sym else 1

        if _new_lev != int(target_leverage):
            log.info(f"[Setup] {sym} snap leverage "
                     f"{target_leverage}x → {_new_lev}x "
                     f"(max={_SYMBOL_LEV_TIERS[sym][0]}x)")
            target_leverage = _new_lev
    except Exception as _e:
        log.warning(f"[Setup] {sym} snap failed: {_e} — "
                    f"using target as-is")

    global _SYMBOL_META
    meta = _SYMBOL_META.get(sym, {})

    # Fast path: already set up with matching leverage
    if meta.get('setup_done') and int(meta.get('leverage', 0)) == target_leverage:
        return True

    # 1. Check for existing position
    has_pos = False
    try:
        positions = _fake_pos_list(exchange, sym)
        for p in positions:
            amt = float(p['info'].get('positionAmt', 0) or 0)
            if abs(amt) > 0:
                has_pos = True
                break
    except Exception as e:
        log.debug(f"[Setup] fetch_positions {sym}: {e}")

    if has_pos:
        # Read current leverage, do NOT change it
        try:
            lev_info = exchange.fetch_leverage(sym)
            cur_lev = int(lev_info.get('leverage', target_leverage))
        except Exception:
            cur_lev = target_leverage
        _SYMBOL_META[sym] = {
            'leverage': cur_lev,
            'margin_mode': margin_mode,
            'setup_done': True,
            'reason': 'position_exists'
        }
        log.info(f"[Setup] {sym} position exists → keeping leverage={cur_lev}x (NOT changing)")
        save_symbol_meta()
        return True

    # 2. No position — safe to set
    try:
        exchange.set_margin_mode(margin_mode, sym)
    except Exception as e:
        msg = str(e).lower()
        if 'no need' not in msg and 'already' not in msg and '-4046' not in msg:
            log.debug(f"[Setup] margin {sym}: {e}")

    try:
        exchange.set_leverage(target_leverage, sym)
    except Exception as e:
        log.warning(f"[Setup] set_leverage {sym}→{target_leverage}x failed: {e}")
        return False

    # 3. Verify
    confirmed = target_leverage
    if CFG.SETUP_VERIFY_LEVERAGE:
        try:
            lev_info = exchange.fetch_leverage(sym)
            if lev_info is None or not hasattr(lev_info, 'get'):
                log.debug(f"[Setup] {sym} leverage verify unavailable on this "
                          f"exchange — assuming {target_leverage}x")
                confirmed = target_leverage
            else:
                confirmed = int(lev_info.get('leverage', target_leverage)
                                or target_leverage)
                if confirmed != target_leverage:
                    log.warning(f"[Setup] {sym} leverage mismatch: "
                                f"got {confirmed}x, wanted {target_leverage}x")
        except Exception as e:
            log.debug(f"[Setup] {sym} fetch_leverage verify failed: {e} "
                      f"(assuming {target_leverage}x)")
            confirmed = target_leverage

    _SYMBOL_META[sym] = {
        'leverage': confirmed,
        'margin_mode': margin_mode,
        'setup_done': True,
        'reason': 'fresh_setup',
        'updated_ts': time.time()
    }
    save_symbol_meta()
    log.info(f"[Setup] {sym} leverage={confirmed}x margin={margin_mode}")
    return True


def verify_fill(exchange, order_id: str, sym: str,
                timeout_s: float = 5.0) -> Optional[Dict]:
    """
    Poll order until terminal state. Returns:
      {'filled': bool, 'qty': float, 'avg_price': float, 'status': str}
    or None if still pending after timeout.
    """
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            o = exchange.fetch_order(order_id, sym)
            status = o.get('status')
            if status == 'closed':
                return {
                    'filled': True,
                    'qty': float(o.get('filled') or 0.0),
                    'avg_price': float(o.get('average') or o.get('price') or 0.0),
                    'status': 'closed'
                }
            if status in ('canceled', 'expired', 'rejected'):
                return {'filled': False, 'qty': 0.0, 'avg_price': 0.0, 'status': status}
        except Exception as e:
            log.debug(f"[VerifyFill] fetch_order {order_id} ({sym}) "
                      f"failed: {e}")
        time.sleep(0.25)
    return None  # still pending


def reconcile_state_machine(exchange, open_pos_live: Dict,
                            symbols: List[str]) -> Dict:
    """
    Full sync between local memory and exchange. Handles:
    - Position exists on exchange but not local → adopt
    - Position exists locally but not exchange → clear
    - Position size mismatch → update
    """
    try:
        live_positions = exchange.fetch_positions(symbols)
    except Exception as e:
        log.warning(f"[Reconcile] fetch_positions failed: {e}")
        return open_pos_live

    exch_map = {}
    for p in live_positions:
        try:
            amt = float(p['info'].get('positionAmt', 0) or 0)
            if abs(amt) < 1e-12:
                continue
            sym_norm = p['symbol'].split(':')[0] if ':' in p['symbol'] else p['symbol']
            exch_map[sym_norm] = {
                'qty': abs(amt),
                'entry': float(p['info'].get('entryPrice', 0) or 0),
                'side': 'BUY' if amt > 0 else 'SELL',
            }
        except Exception:
            continue

    changed = 0

    # Remove local-only positions
    for sym in list(open_pos_live.keys()):
        if sym not in exch_map:
            log.warning(f"[Reconcile] {sym} local-only → removing")
            del open_pos_live[sym]
            changed += 1

    # Adopt / update exchange positions
    for sym, ex in exch_map.items():
        if sym in open_pos_live:
            loc = open_pos_live[sym]
            if abs(loc.get('qty', 0) - ex['qty']) / max(ex['qty'], 1e-9) > 0.01:
                log.warning(f"[Reconcile] {sym} qty: local={loc.get('qty')} → {ex['qty']}")
                loc['qty'] = ex['qty']
                changed += 1
            if ex['entry'] > 0:
                loc['entry'] = ex['entry']
        else:
            log.warning(f"[Reconcile] {sym} exchange-only → adopting")
            # [DUPLICATE-FIX] use pending geometry if available
            _pending_vals = None
            _pending_rec = _PENDING_ORDERS.get(sym)
            if _pending_rec is not None:
                _p_sl_dist = float(_pending_rec.get('orig_sl_dist') or 0)
                _p_tp_dist = float(_pending_rec.get('orig_tp_dist') or 0)
                if _p_sl_dist > 0 and _p_tp_dist > 0:
                    _pending_vals = {
                        'sl_dist': _p_sl_dist,
                        'tp_dist': _p_tp_dist,
                        'T_info': float(_pending_rec.get('T_info') or 0),
                        'dyn_risk': float(_pending_rec.get('dyn_risk') or 0.01),
                    }
                    log.info(
                        f"[Reconcile] {sym} using pending geometry: "
                        f"sl_dist={_p_sl_dist:.6f} tp_dist={_p_tp_dist:.6f}"
                    )

            if _pending_vals is not None:
                if ex['side'] == 'BUY':
                    _adopted_sl = ex['entry'] - _pending_vals['sl_dist']
                    _adopted_tp = ex['entry'] + _pending_vals['tp_dist']
                else:
                    _adopted_sl = ex['entry'] + _pending_vals['sl_dist']
                    _adopted_tp = ex['entry'] - _pending_vals['tp_dist']
                open_pos_live[sym] = {
                    'action': ex['side'],
                    'entry': ex['entry'],
                    'qty': ex['qty'],
                    'sl': _adopted_sl,
                    'tp1': _adopted_tp,
                    'T_info': _pending_vals['T_info'],
                    'dyn_risk': _pending_vals['dyn_risk'],
                    'entry_ts': time.time(),
                    'adopted': True,
                    'sl_dist_initial': _pending_vals['sl_dist'],
                }
                _PENDING_ORDERS.pop(sym, None)
            else:
                open_pos_live[sym] = {
                    'action': ex['side'],
                    'entry': ex['entry'],
                    'qty': ex['qty'],
                    'sl': ex['entry'] * (0.985 if ex['side'] == 'BUY' else 1.015),
                    'tp1': ex['entry'] * (1.03 if ex['side'] == 'BUY' else 0.97),
                    'T_info': 0.0,
                    'dyn_risk': 0.01,
                    'entry_ts': time.time(),
                    'adopted': True,
                }
            changed += 1

    if changed:
        log.info(f"[Reconcile] {changed} changes applied")
    return open_pos_live


# ════════════════════════════════════════════════════════════════
# § 18.97  ML Filter — Live Tracking
# ════════════════════════════════════════════════════════════════

_ML_LIVE_STATS: Dict = {
    'unique_seen': 0,
    'unique_kept': 0,
    'unique_rejected': 0,
    'last_seen': {},      # {(sym, close_idx): 'kept'|'rejected'}
    'last_report_ts': 0.0,
}


def filter_signals_ml_live(signals, assets) -> List:
    """
    Live-mode ML filter with per-(sym, close_idx) memoization.

    Avoids re-evaluating the same signal on every poll. Backtest doesn't
    need this because each signal is evaluated once; Live sees the same
    signal across many polls until a new candle closes.

    Returns signals that pass the filter (or all, if filter disabled).
    """
    if not CFG.ML_FILTER_ENABLED or _ML_MODEL is None or _ML_SCALER is None:
        return signals

    kept = []
    for sig in signals:
        ad = assets.get(sig.symbol)
        if ad is None:
            kept.append(sig)
            continue

        key = (sig.symbol, int(sig.close_idx))

        # Memoization: already evaluated? reuse verdict
        prev = _ML_LIVE_STATS['last_seen'].get(key)
        if prev == 'kept':
            kept.append(sig)
            continue
        if prev == 'rejected':
            continue

        # Fresh evaluation
        try:
            feat = _extract_ml_features(sig, ad)[:_ML_EXPECTED_N].reshape(1, -1)
            feat_s = _ML_SCALER.transform(feat)
            p_win = float(_ML_MODEL.predict_proba(feat_s)[0, 1])
        except Exception as e:
            log.debug(f"[ML-Live] {sig.symbol} feature error: {e}")
            kept.append(sig)
            continue

        _ML_LIVE_STATS['unique_seen'] += 1
        if p_win >= CFG.ML_FILTER_THRESHOLD:
            kept.append(sig)
            _ML_LIVE_STATS['unique_kept'] += 1
            _ML_LIVE_STATS['last_seen'][key] = 'kept'
        else:
            _ML_LIVE_STATS['unique_rejected'] += 1
            _ML_LIVE_STATS['last_seen'][key] = 'rejected'
            # Show top-3 failing pattern indicators
            _feat = feat.flatten()
            _pat = []
            if _feat[28] < 0.2: _pat.append("doji")
            if _feat[29] > 0.6 or _feat[30] > 0.6: _pat.append("wick")
            if _feat[31] >= 3: _pat.append("consec")
            if _feat[35] != 0 and np.sign(_feat[35]) != (1 if sig.action == "BUY" else -1):
                _pat.append("trend_1h_against")
            if _feat[40] < -0.2: _pat.append("vol_price_div")
            if _feat[47] < 0.15 or _feat[47] > 0.85: _pat.append("range_edge")
            if _feat[50] > 0.85: _pat.append("atr_spike")
            _pat_str = ",".join(_pat) if _pat else "none"

            log.info(f"[ML-Live] {sig.symbol} {sig.action} "
                     f"close_idx={sig.close_idx} rejected "
                     f"(p_win={p_win:.3f} < {CFG.ML_FILTER_THRESHOLD:.2f}) "
                     f"[patterns: {_pat_str}]")

    # Prune memo: keep only last 500 entries
    if len(_ML_LIVE_STATS['last_seen']) > 500:
        keys = list(_ML_LIVE_STATS['last_seen'].keys())
        for k in keys[:-200]:
            _ML_LIVE_STATS['last_seen'].pop(k, None)

    return kept


def log_ml_live_stats():
    """Log ML filter stats every ~5 minutes."""
    now = time.time()
    if now - _ML_LIVE_STATS['last_report_ts'] < 300:
        return
    _ML_LIVE_STATS['last_report_ts'] = now

    seen = _ML_LIVE_STATS['unique_seen']
    if seen == 0:
        return

    kept = _ML_LIVE_STATS['unique_kept']
    rej = _ML_LIVE_STATS['unique_rejected']
    rej_pct = 100.0 * rej / seen
    log.info(f"[ML-Live] stats: seen={seen}, kept={kept}, "
             f"rejected={rej} ({rej_pct:.1f}%)")

# ════════════════════════════════════════════════════════════════
# § 18.92  Live AssetData Cache
# ════════════════════════════════════════════════════════════════

_LIVE_ASSET_CACHE: Dict[Tuple[str, str, int], "AssetData"] = {}
_LIVE_ASSET_CACHE_STATS = {
    'hits': 0,
    'misses': 0,
    'evictions': 0,
    'last_report_ts': 0.0,
}
# ══ [DEGENERATE-CACHE] Remember failures per (sym, tf, last_closed_ts) ══
# Prevents reprocessing the same degenerate asset every 5 seconds.
_DEGENERATE_CACHE: Dict[Tuple[str, str, int], float] = {}
_DEGENERATE_CACHE_MAX = 500

# ══ [LAYER 5] LiqProximity trigger counter ══
_LIQ_EMERGENCY_STATS: Dict = {
    'triggers': 0,
    'last_warned_at': 0.0,
}


def _degenerate_get(sym: str, tf: str, last_closed_ts: int) -> bool:
    """True if (sym, tf, bar) was already marked as degenerate."""
    return (sym, tf, last_closed_ts) in _DEGENERATE_CACHE


def _degenerate_put(sym: str, tf: str, last_closed_ts: int) -> None:
    """Mark (sym, tf, bar) as degenerate (auto-evict when cache grows)."""
    _DEGENERATE_CACHE[(sym, tf, last_closed_ts)] = time.time()
    if len(_DEGENERATE_CACHE) > _DEGENERATE_CACHE_MAX:
        # Drop oldest 100 by insertion order
        for k in list(_DEGENERATE_CACHE.keys())[:100]:
            _DEGENERATE_CACHE.pop(k, None)


def _last_closed_bar_ts(df, tf_seconds: int) -> int:
    """
    Timestamp (as int) of the last CLOSED bar in the dataframe.
    Returns 0 if there is no closed bar.

    In Live, df.iloc[-1] is the currently-forming bar. df.iloc[-2]
    is the last closed bar. Its timestamp is stable until the next
    closed bar arrives (i.e., for tf_seconds).
    """
    if df is None or len(df) < 2:
        return 0
    try:
        return int(df.index[-2].value)
    except Exception:
        return 0


def _live_cache_get(sym: str, tf: str, last_closed_ts: int) -> Optional["AssetData"]:
    if not CFG.LIVE_ASSET_CACHE_ENABLED or last_closed_ts == 0:
        return None
    key = (sym, tf, last_closed_ts)
    ad = _LIVE_ASSET_CACHE.get(key)
    if ad is not None:
        _LIVE_ASSET_CACHE_STATS['hits'] += 1
        return ad
    _LIVE_ASSET_CACHE_STATS['misses'] += 1
    return None


def _live_cache_put(sym: str, tf: str, last_closed_ts: int, ad: "AssetData") -> None:
    if not CFG.LIVE_ASSET_CACHE_ENABLED or last_closed_ts == 0 or ad is None:
        return
    key = (sym, tf, last_closed_ts)
    _LIVE_ASSET_CACHE[key] = ad

    # Eviction: cap size
    if len(_LIVE_ASSET_CACHE) > CFG.LIVE_ASSET_CACHE_MAX:
        # Drop oldest entries (FIFO on insertion order)
        overflow = len(_LIVE_ASSET_CACHE) - CFG.LIVE_ASSET_CACHE_MAX
        for old_key in list(_LIVE_ASSET_CACHE.keys())[:overflow]:
            _LIVE_ASSET_CACHE.pop(old_key, None)
            _LIVE_ASSET_CACHE_STATS['evictions'] += 1


def _live_cache_prune_stale(current_last_closed: Dict[str, int]) -> int:
    """
    Remove entries whose last_closed_ts is older than the current one
    for the same (sym, tf). Called periodically.
    """
    removed = 0
    for key in list(_LIVE_ASSET_CACHE.keys()):
        sym, tf, ts = key
        cur_ts = current_last_closed.get(sym, ts)
        if ts < cur_ts:
            _LIVE_ASSET_CACHE.pop(key, None)
            removed += 1
    return removed


def _live_cache_log_stats() -> None:
    now = time.time()
    if now - _LIVE_ASSET_CACHE_STATS['last_report_ts'] < 300:
        return
    _LIVE_ASSET_CACHE_STATS['last_report_ts'] = now
    h = _LIVE_ASSET_CACHE_STATS['hits']
    m = _LIVE_ASSET_CACHE_STATS['misses']
    e = _LIVE_ASSET_CACHE_STATS['evictions']
    total = h + m
    if total == 0:
        return
    hit_rate = 100.0 * h / total
    log.info(f"[LiveCache] hits={h}, misses={m} ({hit_rate:.1f}%), "
             f"evictions={e}, entries={len(_LIVE_ASSET_CACHE)}")

# ════════════════════════════════════════════════════════════════
# § 18.93  Pending Orders (Non-Blocking Entry)
# ════════════════════════════════════════════════════════════════

_PENDING_ORDERS: Dict[str, Dict] = {}
_PENDING_ORDERS_PATH: str = ""

# ════════════════════════════════════════════════════════════════
# § 18.94  Watched Signals — Watch-Then-Trigger State
# ════════════════════════════════════════════════════════════════

_WATCHED_SIGNALS: Dict[str, Dict] = {}
_WATCHED_SIGNALS_PATH: str = ""


def load_watched_signals(mode: str) -> Dict[str, Dict]:
    if WATCH_REMOVED:
        return {}
    global _WATCHED_SIGNALS, _WATCHED_SIGNALS_PATH
    _WATCHED_SIGNALS_PATH = f"{CFG.WATCH_FILE_PREFIX}_{mode}.json"
    if os.path.exists(_WATCHED_SIGNALS_PATH):
        try:
            with open(_WATCHED_SIGNALS_PATH) as f:
                _WATCHED_SIGNALS = json.load(f)
            log.info(f"[Watch] Restored {len(_WATCHED_SIGNALS)} "
                     f"watched signals")
        except Exception as e:
            log.warning(f"[Watch] load failed: {e}")
            _WATCHED_SIGNALS = {}
    else:
        _WATCHED_SIGNALS = {}
    return _WATCHED_SIGNALS


def save_watched_signals() -> None:
    if WATCH_REMOVED:
        return None
    if not _WATCHED_SIGNALS_PATH:
        return
    try:
        tmp = _WATCHED_SIGNALS_PATH + ".tmp"
        serializable = {}
        for sym, rec in _WATCHED_SIGNALS.items():
            _r = {}
            for k, v in rec.items():
                if k in ('signal_ref', 'ad_ref'):
                    continue
                if isinstance(v, (np.floating, np.integer)):
                    v = v.item()
                elif isinstance(v, np.ndarray):
                    continue
                _r[k] = v
            serializable[sym] = _r
        with open(tmp, 'w') as f:
            json.dump(serializable, f, indent=2)
        os.replace(tmp, _WATCHED_SIGNALS_PATH)
    except Exception as e:
        log.warning(f"[Watch] save failed: {e}")

# ════════════════════════════════════════════════════════════════
# § 18.95  Watch — Helpers
# ════════════════════════════════════════════════════════════════

def _watch_proximity_ok(p_now: float, tunnel_p: float,
                         sigma_bar: float) -> bool:
    """Condition (a): |p_now − tunnel| ≤ κ · σ_bar · tunnel."""
    if p_now <= 0 or tunnel_p <= 0 or sigma_bar <= 0:
        return False
    dist = abs(p_now - tunnel_p)
    kappa = float(getattr(CFG, 'WATCH_PROX_KAPPA', 0.5))
    return dist <= kappa * sigma_bar * tunnel_p

def _watch_compute_entry_offset(tunnel_p: float, sigma_bar: float,
                                 adv_usd: float,
                                 exchange=None,
                                 symbol: Optional[str] = None,
                                 qty: float = 0.0) -> float:
    """
    Returns the price offset to place beyond tunnel_entry_p,
    in the direction that guarantees fill on touch.

      BUY : order = tunnel + offset
      SELL: order = tunnel − offset

    The offset is:
      max( tick_size,
           κ_vol × σ_bar × tunnel × adv_mult,
           order_size_impact,
           min_bps × tunnel )
      capped at max_bps × tunnel.
    """
    # ── Floor 1: tick size ──
    tick = 0.0
    if exchange is not None and symbol is not None:
        try:
            tick = _get_tick_size(exchange, symbol) or 0.0
        except Exception:
            tick = 0.0
    if tick <= 0:
        tick = tunnel_p * 1e-6   # 0.1 bps fallback

    # ── Floor 2: σ_bar × κ × ADV multiplier ──
    sig = max(float(sigma_bar), 1e-6)
    vol_off = float(CFG.WATCH_OFFSET_VOL_KAPPA) * sig * tunnel_p

    try:
        _adv = float(adv_usd)
    except Exception:
        _adv = 1e8
    adv_mult = 5.0
    for thresh, mult in getattr(CFG, 'WATCH_OFFSET_ADV_TIERS',
                                 ((1e10, 1.0), (1e9, 1.3), (1e8, 1.8),
                                  (1e7, 3.0), (0.0, 5.0))):
        if _adv >= thresh:
            adv_mult = float(mult)
            break
    vol_off *= adv_mult

    # ── Floor 3: order-size impact ──
    size_off = 0.0
    if qty > 0 and _adv > 0:
        hourly_adv = _adv / 24.0
        participation = (qty * tunnel_p) / max(hourly_adv, 1.0)
        size_off = tunnel_p * min(0.0005, participation * 0.005)

    # ── Combine & clamp ──
    min_abs = tunnel_p * float(CFG.WATCH_OFFSET_MIN_BPS) * 1e-4
    max_abs = tunnel_p * float(CFG.WATCH_OFFSET_MAX_BPS) * 1e-4
    off = max(tick, vol_off, size_off, min_abs)
    off = min(off, max_abs)
    return float(off)

def _find_swing_in_window(ad, end_ci: int, lookback: int, kind: str):
    """Most recent swing low/high within [end_ci-lookback, end_ci)."""
    try:
        lo = max(1, int(end_ci) - int(lookback))
        hi = min(int(end_ci), len(ad.lows) - 1)
        if hi - lo < 3:
            return None, -1
        if kind == "low":
            arr = ad.lows
            for j in range(hi - 1, lo, -1):
                if arr[j] < arr[j-1] and arr[j] < arr[j+1]:
                    return float(arr[j]), int(j)
        else:
            arr = ad.highs
            for j in range(hi - 1, lo, -1):
                if arr[j] > arr[j-1] and arr[j] > arr[j+1]:
                    return float(arr[j]), int(j)
    except Exception:
        pass
    return None, -1


def _watch_sl_structure_ok(ad, sig, sl_to_check: float,
                            tunnel_p: float, current_ci: int) -> bool:
    """
    Condition (b): the SL that will actually be used must be protected
    by a recent swing.
      BUY : sl_to_check < swing_low − buffer < tunnel_p
      SELL: tunnel_p < swing_high + buffer < sl_to_check
    """
    try:
        lookback = int(getattr(CFG, 'WATCH_SWING_LOOKBACK', 60))
        buf_mult = float(getattr(CFG, 'WATCH_SWING_BUFFER_MULT', 0.3))
        atr = (float(ad.atr14[current_ci])
               if 0 <= current_ci < len(ad.atr14) else 0.0)
        if atr <= 0:
            atr = max(abs(tunnel_p - sl_to_check) * 0.1, 1e-9)
        buffer = buf_mult * atr

        if sig.action == "BUY":
            sw, _ = _find_swing_in_window(ad, current_ci, lookback, "low")
            if sw is None:
                return False
            return (sl_to_check < sw - buffer) and (sw - buffer < tunnel_p)
        else:
            sw, _ = _find_swing_in_window(ad, current_ci, lookback, "high")
            if sw is None:
                return False
            return (sl_to_check > sw + buffer) and (sw + buffer > tunnel_p)
    except Exception as e:
        log.debug(f"[Watch] sl_structure_ok failed: {e}")
        return False


def _watch_opportunity_alive(ad, sig, current_ci: int,
                              current_fi: int) -> bool:
    """
    Reuses existing physics to test if the signal is still valid.
    Four gates: P_activation, score freshness, accel/friction, delta_gap.
    """
    try:
        if current_fi < 3 or current_fi >= len(ad.score):
            return False

        geo_a = float(ad.geodesic_accel[current_fi])
        fric = float(ad.friction[current_fi]) + 1e-6
        T_info = float(ad.T_info[current_fi])
        force_mag = abs(geo_a) + 1e-9

        # Gate 1 — P_activation
        P_act = float(np.exp(-fric / (force_mag * T_info)))
        if P_act < float(getattr(CFG, 'WATCH_OPP_P_ACT_MIN', 0.35)):
            return False

        # Gate 2 — score freshness
        sc_now = float(ad.score[current_fi])
        sc_orig = float(getattr(sig, 'score', 0.0))
        if sc_orig > 0:
            if sc_now < float(getattr(CFG, 'WATCH_OPP_SCORE_RATIO', 0.85)) * sc_orig:
                return False

        # Gate 3 — accel/friction explosion in the wrong direction
        ratio = abs(geo_a) / max(fric, 1e-9)
        if ratio > float(getattr(CFG, 'WATCH_OPP_ACCEL_RATIO_MAX', 2.0)):
            # BUY: dangerous if accel is strongly downward (negative)
            # SELL: dangerous if accel is strongly upward (positive)
            if sig.action == "BUY" and geo_a < 0:
                return False
            if sig.action == "SELL" and geo_a > 0:
                return False

        # Gate 4 — equilibrium gap
        dgap = (float(ad.delta_gap[current_fi])
                if current_fi < len(ad.delta_gap) else 0.0)
        if dgap > float(getattr(CFG, 'MAX_EQUILIBRIUM_GAP', 0.35)):
            return False

        return True
    except Exception as e:
        log.debug(f"[Watch] opportunity_alive failed: {e}")
        return False


def register_watch_signal(sym: str, sig, ad) -> bool:
    if WATCH_REMOVED:
        return False
    """
    Register a signal for watching (no exchange call).
    Returns True if newly registered, False if duplicate.
    """
    if sym in _WATCHED_SIGNALS:
        log.debug(f"[Watch] {sym} already watched — skip")
        return False
    if sym in _PENDING_ORDERS:
        log.debug(f"[Watch] {sym} has pending order — skip")
        return False

    cur_ci = max(0, len(ad.closes) - 2)
    cur_fi = cur_ci - ad.feat_start
    if cur_fi < 0 or cur_fi >= len(ad.score):
        return False

    try:
        geo_a0 = float(ad.geodesic_accel[sig.feat_idx])
        fric0 = float(ad.friction[sig.feat_idx]) + 1e-6
        T_info0 = float(ad.T_info[sig.feat_idx])
        P_act0 = float(np.exp(-fric0 / ((abs(geo_a0) + 1e-9) * T_info0)))
    except Exception:
        P_act0 = 1.0

    _WATCHED_SIGNALS[sym] = {
        'sym': sym,
        'action': str(sig.action),
        'tunnel_entry_p': float(sig.price),
        'sl': float(sig.sl),
        'tp1': float(sig.tp1),
        'score': float(sig.score),
        'orig_P_act': float(P_act0),
        'close_idx': int(sig.close_idx),
        'feat_idx': int(sig.feat_idx),
        'T_info_val': float(sig.T_info_val),
        'dyn_risk': float(sig.dynamic_risk),
        'entry_ref_price': float(getattr(sig, 'entry_ref_price', 0.0) or sig.price),
        'entry_base_dip': float(getattr(sig, 'entry_base_dip', 0.0)),
        'registered_at': time.time(),
        'signal_ref': sig,
        'ad_ref': ad,
    }
    log.info(f"[Watch] {sig.action} {sym} registered @ "
             f"tunnel={sig.price:.6f} sl={sig.sl:.6f} "
             f"score={float(sig.score):.2f}")
    return True


def monitor_watch_signals(exchange, open_pos_live: Dict,
                           assets: Optional[Dict] = None,
                           loop_iter: int = 0) -> None:
    if WATCH_REMOVED:
        return None
    """
    Iterate over watched signals. When (a) proximity + (b) SL-structure
    are both satisfied → hand off to place_pending_entry.
    Timeout / physics collapse → drop.
    """
    if not _WATCHED_SIGNALS:
        return

    _max_age_bars = max(3, effective_bars(
        int(getattr(CFG, 'UNIFIED_MAX_AGE_BARS_1H', 12))
    ))
    _phase1_timeout = max(3, effective_bars(
        int(getattr(CFG, 'WATCH_PHASE1_TIMEOUT_BARS_1H', 16))
    ))
    _triggers_this_cycle = 0
    _max_per_cycle = int(getattr(CFG, 'WATCH_MAX_PER_CYCLE', 5))

    for sym in list(_WATCHED_SIGNALS.keys()):
        rec = _WATCHED_SIGNALS[sym]

        # ── Re-hydrate ad / sig on restart ──
        ad = rec.get('ad_ref')
        if ad is None and assets is not None:
            ad = assets.get(sym)
        if ad is None:
            log.debug(f"[Watch] {sym} no AssetData — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        sig = rec.get('signal_ref')
        if sig is None:
            from types import SimpleNamespace as _SNS
            sig = _SNS(
                symbol=sym,
                action=str(rec.get('action', 'BUY')),
                price=float(rec.get('tunnel_entry_p', 0)),
                sl=float(rec.get('sl', 0)),
                tp1=float(rec.get('tp1', 0)),
                score=float(rec.get('score', 0)),
                close_idx=int(rec.get('close_idx', 0)),
                feat_idx=int(rec.get('feat_idx', 0)),
                T_info_val=float(rec.get('T_info_val', 0)),
                dynamic_risk=float(rec.get('dyn_risk', 0.01)),
                entry_ref_price=float(rec.get('entry_ref_price', 0)),
                entry_base_dip=float(rec.get('entry_base_dip', 0)),
            )
            rec['signal_ref'] = sig

        # ── Current bar / feature index ──
        cur_ci = max(0, len(ad.closes) - 2)
        cur_fi = cur_ci - ad.feat_start
        if cur_fi < 0 or cur_fi >= len(ad.score):
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        bars_elapsed = cur_ci - int(rec['close_idx'])

        # ── Timeouts ──
        if bars_elapsed > _phase1_timeout:
            log.info(f"[Watch] {sym} expired "
                     f"(age={bars_elapsed}>{_phase1_timeout}) — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue
        if bars_elapsed > _max_age_bars:
            log.info(f"[Watch] {sym} signal aged out "
                     f"(age={bars_elapsed}>{_max_age_bars}) — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        # ── Physics collapse → abort ──
        sc_now = float(ad.score[cur_fi])
        if sc_now < float(getattr(CFG, 'WATCH_PHASE1_ABORT_SCORE', 0.5)) * float(rec['score']):
            log.info(f"[Watch] {sym} physics collapsed "
                     f"(score {rec['score']:.2f}→{sc_now:.2f}) — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        try:
            geo_a = float(ad.geodesic_accel[cur_fi])
            fric = float(ad.friction[cur_fi]) + 1e-6
            T_info = float(ad.T_info[cur_fi])
            P_act_now = float(np.exp(-fric / ((abs(geo_a) + 1e-9) * T_info)))
        except Exception:
            P_act_now = 1.0
        if P_act_now < float(getattr(CFG, 'WATCH_PHASE1_ABORT_P_ACT', 0.30)):
            log.info(f"[Watch] {sym} P_activation collapsed "
                     f"(P={P_act_now:.3f}) — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        # ── Condition (a): proximity ──
        p_now = float(ad.closes[cur_ci])
        tunnel_p = float(rec['tunnel_entry_p'])
        try:
            sigma_bar = (float(ad.E_therm[cur_fi])
                         if cur_fi < len(ad.E_therm) else 0.01)
            if not np.isfinite(sigma_bar) or sigma_bar <= 1e-6:
                sigma_bar = 0.01
        except Exception:
            sigma_bar = 0.01

        if not _watch_proximity_ok(p_now, tunnel_p, sigma_bar):
            continue

        # ══ [ENTRY-OFFSET] Compute dynamic offset FIRST ══
        # الإزاحة ديناميكية: tick size, σ_bar, ADV, حجم الأمر.
        _qty_tmp = float(rec.get('qty', 0.0) or 0.0)
        _adv_now = 1e8
        try:
            if cur_ci < len(ad.adv_usd):
                _adv_now = float(ad.adv_usd[cur_ci])
        except Exception:
            pass

        _offset = _watch_compute_entry_offset(
            tunnel_p=tunnel_p,
            sigma_bar=sigma_bar,
            adv_usd=_adv_now,
            exchange=exchange,
            symbol=sym,
            qty=_qty_tmp,
        )

        # أمرنا يواجه السعر الهابط/الصاعد ليملأ عند أول تلامس
        if sig.action == "BUY":
            _expected_entry = tunnel_p + _offset
            _effective_sl = _expected_entry - abs(
                float(rec['sl']) - tunnel_p
            )
        else:
            _expected_entry = tunnel_p - _offset
            _effective_sl = _expected_entry + abs(
                float(rec['sl']) - tunnel_p
            )

        # ── Condition (b): SL structure (using effective SL) ──
        if not _watch_sl_structure_ok(
                ad, sig, _effective_sl, tunnel_p, cur_ci):
            log.debug(
                f"[Watch] {sym} proximity OK but effective SL "
                f"{_effective_sl:.6f} not protected — keep watching"
            )
            continue

        # ══════════════════════════════════════════════════════
        # TRIGGER
        # ══════════════════════════════════════════════════════
        if _triggers_this_cycle >= _max_per_cycle:
            log.debug(f"[Watch] cycle cap reached — deferring {sym}")
            break

        if (len(open_pos_live) + len(_PENDING_ORDERS)) >= int(CFG.MAX_CONCURRENT_ASSETS):
            log.info(f"[Watch] {sym} exposure cap — will retry next cycle")
            continue

        _qty = float(rec.get('qty', 0.0) or 0.0)
        _leverage = int(rec.get('leverage', 0) or 0)
        if _qty <= 0 or _leverage <= 0:
            log.warning(f"[Watch] {sym} qty/lev missing — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        log.info(f"[Watch] {sym} TRIGGERED (proximity+structure)")

        _side = 'buy' if sig.action == 'BUY' else 'sell'
        _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
        _stage1_bars = effective_bars(
            int(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))
        )
        _timeout_s = float(_stage1_bars * _tf_sec)

        # ══ [SETUP-AT-TRIGGER] ══
        # ضبط الرافعة/الهامش يحدث الآن فقط، بعد تحقق الشرطين.
        # لو فشل، نُسقط الإشارة بدل إعادة المحاولة كل دورة.
        try:
            if not ensure_symbol_setup(exchange, sym, _leverage,
                                        margin_mode='isolated'):
                log.warning(f"[Watch] {sym} setup failed — dropping")
                _WATCHED_SIGNALS.pop(sym, None)
                save_watched_signals()
                continue
        except Exception as _e:
            log.warning(f"[Watch] {sym} setup exception: {_e} — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            save_watched_signals()
            continue

        # ══ [WATCH-ENTRY-PRICE] استخدم explicit_target ══
        _order_price = (_expected_entry
                        if sig.action == "BUY"
                        else _expected_entry)
        log.info(f"[Watch] {sym} trigger: tunnel={tunnel_p:.6f} "
                 f"offset={_offset:.6f} "
                 f"({_offset/tunnel_p*1e4:.2f}bps) "
                 f"order_px={_order_price:.6f} "
                 f"effective_sl={_effective_sl:.6f}")

        try:
            ok = place_pending_entry(
                exchange, sym, _side, _qty, sig,
                timeout_s=_timeout_s,
                leverage=_leverage,
                ad=ad,
                explicit_target=float(_order_price),
            )
            if ok is not None:
                _triggers_this_cycle += 1
                log.info(f"[Watch] {sym} → pending placed")
                _WATCHED_SIGNALS.pop(sym, None)
                save_watched_signals()
                save_pending_orders()
            else:
                log.info(f"[Watch] {sym} place rejected — keeping watched")
        except Exception as e:
            log.warning(f"[Watch] {sym} trigger failed: {e}")

def load_pending_orders(mode: str) -> Dict[str, Dict]:
    """Restore pending orders from disk."""
    global _PENDING_ORDERS, _PENDING_ORDERS_PATH
    _PENDING_ORDERS_PATH = f"{CFG.PENDING_FILE_PREFIX}_{mode}.json"
    if os.path.exists(_PENDING_ORDERS_PATH):
        try:
            with open(_PENDING_ORDERS_PATH) as f:
                _PENDING_ORDERS = json.load(f)

            # ══ [DESERIALIZE-GUARD] إسقاط الحقول التي كانت كائنات ══
            # قد تكون نصوصاً من إصدار قديم، أو مفقودة.
            _cleaned = 0
            for _sym in list(_PENDING_ORDERS.keys()):
                _rec = _PENDING_ORDERS[_sym]
                for _k in ('ad_ref', 'signal_ref', '_orig_signal_ref'):
                    if _k in _rec and isinstance(_rec[_k], str):
                        _rec.pop(_k, None)
                        _cleaned += 1
                    elif _k in _rec and not isinstance(_rec[_k], str):
                        # كائن حقيقي غير قابل للبقاء عبر JSON
                        _rec.pop(_k, None)
                        _cleaned += 1

            log.info(f"[Pending] Restored {len(_PENDING_ORDERS)} "
                     f"pending orders (cleaned {_cleaned} stale refs)")
        except Exception as e:
            log.warning(f"[Pending] load failed: {e}")
            _PENDING_ORDERS = {}
    else:
        _PENDING_ORDERS = {}
    return _PENDING_ORDERS


def save_pending_orders() -> None:
    """Persist pending orders atomically."""
    if not _PENDING_ORDERS_PATH:
        return
    try:
        tmp = _PENDING_ORDERS_PATH + ".tmp"

        # ══ [SERIALIZATION-GUARD] استبعاد الكائنات غير القابلة للتسلسل ══
        serializable = {}
        for sym, rec in _PENDING_ORDERS.items():
            _r = {}
            for k, v in rec.items():
                if k in ('ad_ref', 'signal_ref',
                         '_orig_signal_ref'):
                    continue
                if isinstance(v, (np.floating, np.integer)):
                    v = v.item()
                elif isinstance(v, np.ndarray):
                    continue
                _r[k] = v
            serializable[sym] = _r

        with open(tmp, 'w') as f:
            json.dump(serializable, f, indent=2, default=str)
        os.replace(tmp, _PENDING_ORDERS_PATH)
    except Exception as e:
        log.warning(f"[Pending] save failed: {e}")


def _pending_drop_stale(exchange=None, max_age_s: float = 3600.0) -> int:
    """
    [FIX-0.1] Remove pending entries older than max_age_s AND
    cancel their exchange-side orders.
    """
    now = time.time()
    removed = 0
    for sym in list(_PENDING_ORDERS.keys()):
        rec = _PENDING_ORDERS[sym]
        if now - float(rec.get('placed_at', 0.0)) > max_age_s:
            oid = rec.get('order_id')
            if oid and exchange is not None:
                try:
                    exchange.cancel_order(oid, sym)
                    log.info(f"[Pending] stale cancel {sym} oid={oid}")
                except Exception as _e:
                    _msg = str(_e).lower()
                    if ('-2011' not in _msg and 'unknown order' not in _msg
                            and '-2013' not in _msg):
                        log.warning(f"[Pending] stale cancel {sym} failed: {_e}")
            _PENDING_ORDERS.pop(sym, None)
            removed += 1
    return removed


def _sweep_pending_once(exchange, sym: str) -> Optional[Dict]:
    """
    Fetch status of a single pending order and update delta fields.
    Returns the record with possibly-updated 'status', 'filled', 'avg_price'.
    """
    rec = _PENDING_ORDERS.get(sym)
    if rec is None:
        return None
    oid = rec.get('order_id')
    if not oid:
        return rec
    try:
        st = exchange.fetch_order(oid, sym)
    except Exception as e:
        log.debug(f"[Pending] fetch_order {sym} failed: {e}")
        return rec
    status = st.get('status', 'unknown')
    fq = float(st.get('filled') or 0.0)
    fp = float(st.get('average') or st.get('price') or rec.get('price') or 0.0)
    rec['status'] = status
    rec['filled'] = fq
    rec['avg_price'] = fp
    rec['updated_ts'] = time.time()
    return rec


def _promote_pending_to_position(exchange, sym: str, rec: Dict,
                                 open_pos_live: Dict) -> bool:
    """Convert a filled pending order into an open position record."""
    filled_qty = float(rec.get('filled') or 0.0)
    total_qty = float(rec.get('qty') or 0.0)
    entry_price = float(rec.get('avg_price') or rec.get('price') or 0.0)
    if filled_qty <= 0 or entry_price <= 0 or total_qty <= 0:
        return False

    fill_ratio = filled_qty / total_qty

    # Reject too-small partial fills
    min_accept = float(getattr(CFG, 'PO_MIN_ACCEPT_RATIO', 0.50))
    if fill_ratio < min_accept:
        log.warning(
            f"[Pending] {sym} fill {fill_ratio*100:.1f}% < "
            f"{min_accept*100:.0f}% — closing tiny partial"
        )
        try:
            close_side = 'sell' if rec['action'] == 'BUY' else 'buy'
            exchange.create_order(sym, 'market', close_side, filled_qty)
        except Exception as e:
            log.error(f"[Pending] close partial failed {sym}: {e}")
        return False

    # Adapt SL/TP to actual fill, preserving original R/R
    orig_sl_dist = float(rec.get('orig_sl_dist') or 0.0)
    orig_tp_dist = float(rec.get('orig_tp_dist') or 0.0)
    if orig_sl_dist <= 1e-12:
        log.warning(f"[Pending] {sym} invalid SL dist — closing")
        try:
            close_side = 'sell' if rec['action'] == 'BUY' else 'buy'
            exchange.create_order(sym, 'market', close_side, filled_qty)
        except Exception:
            pass
        return False

    rr = orig_tp_dist / orig_sl_dist
    # Cap scales with widening so the loosened SL isn't re-clipped.
    max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
    if orig_sl_dist > entry_price * max_sl_frac:
        orig_sl_dist = entry_price * max_sl_frac
        orig_tp_dist = orig_sl_dist * rr

    if rec['action'] == 'BUY':
        adapted_sl = entry_price - orig_sl_dist
        adapted_tp = entry_price + orig_tp_dist
    else:
        adapted_sl = entry_price + orig_sl_dist
        adapted_tp = entry_price - orig_tp_dist

    # ══ [LIQ-GATE-PROMOTE] Final safety check at actual fill price ══
    _lev = int(rec.get('leverage') or 10)
    _mmr = float(rec.get('mmr_at_placement') or
                 getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
    if getattr(CFG, 'LIQ_ENABLED', True) and _lev > 0 and _mmr > 0:
        _liq_px = compute_liquidation_price(entry_price, rec['action'],
                                              _lev, _mmr)
        _liq_gap = abs(entry_price - _liq_px)
        _sl_gap = orig_sl_dist
        _safe_mult = float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5))
        if _liq_gap <= 1e-12 or _sl_gap * _safe_mult > _liq_gap:
            log.warning(
                f"[LiqGate-Promote] {sym} SL unsafe at fill "
                f"(SL gap={_sl_gap:.6f}, Liq gap={_liq_gap:.6f}, "
                f"mult={_safe_mult}, L={_lev}x, MMR={_mmr*100:.3f}%) "
                f"— closing filled position"
            )
            try:
                close_side = 'sell' if rec['action'] == 'BUY' else 'buy'
                exchange.create_order(sym, 'market', close_side, filled_qty)
                log.info(f"[LiqGate-Promote] {sym} closed filled position")
            except Exception as e:
                log.error(f"[LiqGate-Promote] close failed {sym}: {e}")
            return False

    _liq_estimated = None
    if getattr(CFG, 'LIQ_ENABLED', True) and _lev > 0 and _mmr > 0:
        _liq_estimated = compute_liquidation_price(entry_price, rec['action'],
                                                     _lev, _mmr)

    # [FIX-16] Prefer snapshot in rec; fall back to ad_ref; else defaults
    trail_d = float(rec.get('trail_dist_frac') or 0.003)
    trail_a = float(rec.get('trail_activate_frac') or 0.004)
    if trail_d <= 0 or trail_a <= 0:
        try:
            ad = rec.get('ad_ref')
            entry_fi = int(rec.get('entry_fi') or 0)
            if ad is not None:
                trail_d, trail_a = compute_trail_params(ad, entry_fi)
        except Exception:
            pass

    open_pos_live[sym] = {
        'action': rec['action'],
        'entry': entry_price,
        'qty': filled_qty,
        'sl': adapted_sl,
        'tp1': adapted_tp,
        'T_info': float(rec.get('T_info') or 0.0),
        'dyn_risk': float(rec.get('dyn_risk') or 0.01),
        'entry_ts': time.time(),
        'fill_ratio': fill_ratio,
        'leverage': int(rec.get('leverage') or 1),
        'trail_dist_frac': float(trail_d),
        'trail_activate_frac': float(trail_a),
        'liq_price_estimated': _liq_estimated,
        'mmr': _mmr,
        'sl_dist_initial': float(abs(entry_price - adapted_sl)),
        '_entry_ci': int(rec.get('close_idx') or 0),
        '_trail_bars_held': 0,
        '_trail_peak_R': 0.0,
        '_trail_last_update_ts': 0.0,
        '_sym': sym,
        '_orig_score': float(rec.get('_orig_score', 0.0)
                             or getattr(rec.get('signal_ref'), 'score', 0.0)),
    }

    # ══ [LAYER 7] Place protective orders on the exchange ══
    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        _prot_ok = False
        for _attempt in range(3):
            try:
                _ok = _place_protective_orders(exchange, sym,
                                                open_pos_live[sym])
                if _ok:
                    open_pos_live[sym]['_prot_last_sl'] = float(adapted_sl)
                    open_pos_live[sym]['_prot_last_tp'] = float(adapted_tp)
                    _prot_ok = True
                    # [FIX-06b] Only mark partial as taken if the
                    # broker-side partial TP was ACTUALLY placed.
                    # _place_protective_orders disables partial when
                    # partial_price >= full TP (BUY) or <= (SELL).
                    # We replicate that exact check here.
                    _pct_cfg = float(getattr(CFG, 'PARTIAL_TP_PCT', 0.0))
                    if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                            and 0.0 < _pct_cfg < 1.0):
                        _ptr = float(getattr(CFG, 'PARTIAL_TP_R', 1.5))
                        _sl0 = float(open_pos_live[sym].get(
                            'sl_dist_initial', 0) or 0)
                        _entry_ = float(open_pos_live[sym].get('entry', 0))
                        _tp_full = float(open_pos_live[sym].get('tp1', 0))
                        _partial_valid = False
                        if _sl0 > 0 and _entry_ > 0 and _tp_full > 0:
                            _act = open_pos_live[sym].get('action')
                            if _act == 'BUY':
                                _pp = _entry_ + _sl0 * _ptr
                                _partial_valid = (_pp < _tp_full)
                            else:
                                _pp = _entry_ - _sl0 * _ptr
                                _partial_valid = (_pp > _tp_full)
                        if _partial_valid:
                            open_pos_live[sym]['_partial_taken'] = True
                            open_pos_live[sym]['_partial_pnl'] = float(
                                open_pos_live[sym].get('_partial_pnl', 0.0)
                            )
                            log.debug(f"[Prot] {sym} partial marked taken")
                        else:
                            log.debug(f"[Prot] {sym} partial TP not "
                                      f"applicable — bot-side partial "
                                      f"remains enabled")
                    break
                log.warning(f"[Prot] {sym} protective placement "
                            f"attempt {_attempt+1} failed")
                time.sleep(0.5)
            except Exception as _e:
                log.warning(f"[Prot] {sym} attempt {_attempt+1} error: {_e}")
                time.sleep(0.5)
        if not _prot_ok:
            log.warning(f"[Prot] {sym} protective orders NOT placed after "
                        f"3 attempts — bot will monitor manually")

    return True


def monitor_pending_orders(exchange, open_pos_live: Dict,
                           loop_iter: int = 0,
                           assets: Optional[Dict] = None) -> None:
    """
    Sweep all pending orders. Promote filled ones, drop canceled/expired,
    cancel timed-out ones. Bounded to PO_MAX_WAIT_S + grace.
    """
    if not getattr(CFG, 'PENDING_ENABLED', True):
        return
    now = time.time()
    use_rest = (loop_iter % max(int(getattr(CFG, 'PENDING_REST_CHECK_EVERY', 2)), 1) == 0)

    for sym in list(_PENDING_ORDERS.keys()):
        rec = _PENDING_ORDERS[sym]

        # Always try stream first, fall back to REST periodically
        if use_rest:
            _sweep_pending_once(exchange, sym)
            rec = _PENDING_ORDERS.get(sym)
            if rec is None:
                continue

        status = str(rec.get('status') or 'open')

        # ══ [SING-TIMING Layer 1 + Layer 2] فحص حالة الرنين الحالية ══
        if getattr(CFG, 'SING_TIMING_ENABLED', False):
            try:
                _ad_curr = None
                if assets is not None:
                    _ad_curr = assets.get(sym)
                if _ad_curr is None:
                    _ad_curr = rec.get('ad_ref')

                if _ad_curr is not None:
                    # آخر شمعة مغلقة
                    _cur_ci = max(0, len(_ad_curr.closes) - 2)
                    _cur_fi = _cur_ci - _ad_curr.feat_start
                    if 0 <= _cur_fi < len(_ad_curr.geodesic_accel):
                        _st_now, _rho_now = _resonance_state_for_direction(
                            _ad_curr, int(_cur_fi),
                            str(rec.get('action', 'BUY')),
                            CFG
                        )

                        # ══════════════════════════════════════════════
                        # Layer 1: DECAYING → cancel + drop
                        # ══════════════════════════════════════════════
                        if _st_now == "DECAYING":
                            _oid = rec.get('order_id')
                            if _oid:
                                try:
                                    exchange.cancel_order(_oid, sym)
                                except Exception:
                                    pass
                                time.sleep(0.2)
                                _sweep_pending_once(exchange, sym)
                                _rec_chk = _PENDING_ORDERS.get(sym)
                                if (_rec_chk is not None
                                        and float(_rec_chk.get(
                                            'filled', 0.0) or 0.0) > 0.0):
                                    pass  # promotion handles it
                                else:
                                    _PENDING_ORDERS.pop(sym, None)
                                    log.info(
                                        f"[Sing-Timing] {sym} DECAYING "
                                        f"(rho={_rho_now:+.3f}) — pending "
                                        f"cancelled"
                                    )
                                    continue
                            else:
                                _PENDING_ORDERS.pop(sym, None)
                                continue

                        # ══════════════════════════════════════════════
                        # Layer 1: EMERGING/ACTIVE → تقصير المهلة
                        # ══════════════════════════════════════════════
                        if _st_now in ("EMERGING", "ACTIVE"):
                            _bars_limit = int(getattr(
                                CFG,
                                'SING_PENDING_WAIT_EMERGING'
                                if _st_now == "EMERGING"
                                else 'SING_PENDING_WAIT_ACTIVE',
                                2
                            ))
                            _tf_sec_u = (CFG.TF_SECONDS
                                          if CFG.TF_SECONDS > 0 else 3600)
                            _new_timeout = float(_bars_limit * _tf_sec_u)
                            _old_timeout = float(rec.get(
                                'timeout_s', 0.0) or 0.0
                            )
                            if (_old_timeout <= 0.0
                                    or _new_timeout < _old_timeout):
                                rec['timeout_s'] = _new_timeout
                                rec['sing_state_current'] = _st_now
                                rec['sing_rho_current'] = float(_rho_now)
                                log.debug(
                                    f"[Sing-Timing] {sym} {_st_now} — "
                                    f"timeout shortened "
                                    f"{_old_timeout:.0f}s → "
                                    f"{_new_timeout:.0f}s"
                                )

                        # ══════════════════════════════════════════════
                        # Layer 2: ترقية GTX إلى Marketable عند ACTIVE
                        # ══════════════════════════════════════════════
                        if (_st_now == "ACTIVE"
                                and getattr(CFG, 'SING_ACTIVE_MARKETABLE',
                                            False)
                                and str(rec.get('execution_mode', 'gtx'))
                                    != "marketable"
                                and float(rec.get('filled', 0.0) or 0.0)
                                    <= 0.0):
                            _oid = rec.get('order_id')
                            if _oid:
                                # 1) cancel (with sweep)
                                try:
                                    exchange.cancel_order(_oid, sym)
                                except Exception as _ce:
                                    log.debug(
                                        f"[Sing-Timing-L2] {sym} "
                                        f"cancel for upgrade failed: {_ce}"
                                    )
                                time.sleep(0.2)
                                _sweep_pending_once(exchange, sym)
                                _rec_chk = _PENDING_ORDERS.get(sym)
                                # 2) if partial fill arrived, let promotion
                                if (_rec_chk is not None
                                        and float(_rec_chk.get(
                                            'filled', 0.0) or 0.0) > 0.0):
                                    log.info(
                                        f"[Sing-Timing-L2] {sym} "
                                        f"partial fill during upgrade — "
                                        f"keeping order"
                                    )
                                    continue

                                # 3) place marketable
                                try:
                                    ob = exchange.fetch_order_book(
                                        sym, limit=5
                                    )
                                    _bb = float(ob['bids'][0][0])
                                    _ba = float(ob['asks'][0][0])
                                    _pen_bps = float(getattr(
                                        CFG,
                                        'SING_ACTIVE_PENETRATION_BPS',
                                        3.0
                                    ))
                                    _pen_frac = _pen_bps * 1e-4
                                    _side = str(rec.get('side', 'buy'))

                                    if _side == 'buy':
                                        _mk_px = _ba * (1.0 + _pen_frac)
                                    else:
                                        _mk_px = _bb * (1.0 - _pen_frac)

                                    # check slip vs original sig.price
                                    _orig_px = float(rec.get(
                                        'price', _mk_px) or _mk_px)
                                    _slip_bps = (abs(_mk_px - _orig_px)
                                                  / max(_orig_px, 1e-12)
                                                  * 1e4)
                                    _max_slip = float(getattr(
                                        CFG,
                                        'SING_ACTIVE_MAX_SLIP_BPS',
                                        15.0
                                    ))
                                    if _slip_bps > _max_slip:
                                        log.info(
                                            f"[Sing-Timing-L2] {sym} "
                                            f"upgrade skip: slip "
                                            f"{_slip_bps:.1f}bps > "
                                            f"{_max_slip:.1f}bps"
                                        )
                                    else:
                                        _qty = float(rec.get('qty', 0.0)
                                                     or 0.0)
                                        _o2 = exchange.create_order(
                                            sym, 'limit', _side, _qty,
                                            _mk_px, params={}
                                        )
                                        rec['order_id'] = str(_o2['id'])
                                        rec['price'] = float(_mk_px)
                                        rec['execution_mode'] = "marketable"
                                        rec['marketable_px'] = float(_mk_px)
                                        rec['sing_state_current'] = "ACTIVE"
                                        rec['sing_rho_current'] = float(
                                            _rho_now
                                        )
                                        log.info(
                                            f"[Sing-Timing-L2] {sym} "
                                            f"upgraded GTX → marketable "
                                            f"@ {_mk_px:.6f} "
                                            f"(slip={_slip_bps:.1f}bps, "
                                            f"rho={_rho_now:+.3f})"
                                        )
                                except Exception as _oe:
                                    log.warning(
                                        f"[Sing-Timing-L2] {sym} "
                                        f"marketable upgrade failed: "
                                        f"{_oe} — keeping previous order "
                                        f"state"
                                    )
            except Exception as _e:
                log.debug(f"[Sing-Timing] monitor hook failed: {_e}")

        status = str(rec.get('status') or 'open')

        # ── Terminal: filled → promote or complete ──
        if status == 'closed':
            filled = float(rec.get('filled') or 0.0)
            total = float(rec.get('qty') or 0.0)
            fill_ratio = filled / max(total, 1e-12)

            if fill_ratio >= 0.98:
                ok = _promote_pending_to_position(exchange, sym, rec,
                                                   open_pos_live)
                if not ok:
                    log.info(f"[Pending] {sym} dropped after full fill")
                _PENDING_ORDERS.pop(sym, None)

            elif fill_ratio >= float(getattr(CFG, 'PO_MIN_ACCEPT_RATIO', 0.10)):
                # ── [PARTIAL-COMPLETION] ──
                _ad = rec.get('ad_ref')
                _sig = rec.get('signal_ref')
                _alive = False
                if _ad is not None and _sig is not None:
                    try:
                        _cur_ci = max(0, len(_ad.closes) - 2)
                        _cur_fi = _cur_ci - _ad.feat_start
                        _alive = _watch_opportunity_alive(
                            _ad, _sig, _cur_ci, _cur_fi
                        )
                    except Exception:
                        _alive = False

                if _alive and fill_ratio < 0.95:
                    # Re-place remainder at same target
                    _remaining = total - filled
                    log.info(f"[Partial] {sym} filled={filled:.6f}/"
                             f"{total:.6f} — opp alive, re-placing "
                             f"remainder {_remaining:.6f}")
                    try:
                        _side_r = rec.get('side', 'buy')
                        _tgt_r = float(rec.get('price') or 0)
                        _o = exchange.create_order(
                            sym, 'limit', _side_r, _remaining, _tgt_r,
                            params={'timeInForce': 'GTX'}
                        )
                        # Persist accumulated fill in a shadow field
                        _prev_filled = float(rec.get('acc_filled', 0.0))
                        _prev_cost = float(rec.get('acc_cost', 0.0))
                        _this_avg = float(rec.get('avg_price') or 0.0)
                        rec['acc_filled'] = _prev_filled + filled
                        rec['acc_cost'] = _prev_cost + _this_avg * filled
                        rec['order_id'] = str(_o['id'])
                        rec['qty'] = _remaining
                        rec['filled'] = 0.0
                        rec['avg_price'] = 0.0
                        rec['status'] = 'open'
                        rec['placed_at'] = time.time()
                        log.info(f"[Partial] {sym} remainder placed "
                                 f"@ {_tgt_r:.6f}")
                        continue
                    except Exception as _e:
                        log.warning(f"[Partial] {sym} re-place failed: "
                                    f"{_e} — promoting what we have")
                        # Fall through to promote partial
                        ok = _promote_pending_to_position(
                            exchange, sym, rec, open_pos_live
                        )
                        _PENDING_ORDERS.pop(sym, None)
                else:
                    # Opportunity dead → keep filled part, drop remainder
                    log.info(f"[Partial] {sym} opp dead — keeping "
                             f"{filled:.6f}, abandoning "
                             f"{total-filled:.6f}")
                    ok = _promote_pending_to_position(exchange, sym, rec,
                                                       open_pos_live)
                    _PENDING_ORDERS.pop(sym, None)

            else:
                # Too small to accept — close tiny partial + drop
                log.warning(f"[Pending] {sym} fill {fill_ratio*100:.1f}% "
                            f"< PO_MIN_ACCEPT_RATIO — closing tiny partial")
                try:
                    _side_c = 'sell' if rec.get('action') == 'BUY' else 'buy'
                    exchange.create_order(sym, 'market', _side_c, filled)
                except Exception as e:
                    log.error(f"[Pending] close partial failed {sym}: {e}")
                _PENDING_ORDERS.pop(sym, None)

            continue

        # ── Terminal: canceled/expired/rejected → drop ──
        if status in ('canceled', 'expired', 'rejected'):
            log.info(f"[Pending] {sym} {rec.get('action')} → {status}")
            _PENDING_ORDERS.pop(sym, None)
            continue

        # ══ [GAP-JUMP] — price broke through tunnel without filling ══
        if (float(rec.get('filled') or 0.0) <= 1e-12
                and status == 'open'):
            _ad = rec.get('ad_ref')
            _sig = rec.get('signal_ref')
            if _ad is not None and _sig is not None:
                _cur_ci = max(0, len(_ad.closes) - 2)
                _cur_fi = _cur_ci - _ad.feat_start
                _tunnel = float(rec.get('tunnel_entry_p')
                                or rec.get('price') or 0)
                _p_now = (float(_ad.closes[_cur_ci])
                          if _cur_ci < len(_ad.closes) else 0)
                _side_j = rec.get('side', 'buy')

                if _tunnel > 0 and _p_now > 0:
                    # BUY: expects price BELOW tunnel. If price now >0.5% above → jumped.
                    # SELL: expects price ABOVE tunnel. If price now <-0.5% → jumped.
                    _jumped = False
                    if _side_j == 'buy' and _p_now > _tunnel * 1.005:
                        _jumped = True
                    elif _side_j == 'sell' and _p_now < _tunnel * 0.995:
                        _jumped = True

                    if _jumped and 0 <= _cur_fi < len(_ad.score):
                        _alive_j = _watch_opportunity_alive(
                            _ad, _sig, _cur_ci, _cur_fi
                        )
                        if _alive_j:
                            log.info(f"[Gap-Jump] {sym} jumped "
                                     f"(tunnel={_tunnel:.6f}, "
                                     f"now={_p_now:.6f}) — opp alive, "
                                     f"re-pricing")
                            _oid = rec.get('order_id')
                            if _oid:
                                try:
                                    exchange.cancel_order(_oid, sym)
                                except Exception:
                                    pass
                                time.sleep(0.2)
                                _sweep_pending_once(exchange, sym)
                                _chk = _PENDING_ORDERS.get(sym)
                                if (_chk and
                                        float(_chk.get('filled') or 0) > 0):
                                    continue  # partial arrived
                            try:
                                _pen = float(CFG.PO_PENETRATION_BPS) * 1e-4
                                _new_tgt = (_p_now * (1 - _pen) if _side_j == 'buy'
                                            else _p_now * (1 + _pen))
                                _rem = float(rec.get('qty') or 0) - float(rec.get('filled') or 0)
                                _o2 = exchange.create_order(
                                    sym, 'limit', _side_j, _rem, _new_tgt,
                                    params={'timeInForce': 'GTX'}
                                )
                                rec['order_id'] = str(_o2['id'])
                                rec['price'] = float(_new_tgt)
                                rec['gap_repriced'] = int(rec.get('gap_repriced', 0)) + 1
                                log.info(f"[Gap-Jump] {sym} re-priced "
                                         f"→ {_new_tgt:.6f}")
                            except Exception as _e:
                                log.warning(f"[Gap-Jump] {sym} re-price "
                                            f"failed: {_e}")
                        else:
                            log.info(f"[Gap-Jump] {sym} jumped & opp dead "
                                     f"— cancel + drop")
                            _oid = rec.get('order_id')
                            if _oid:
                                try:
                                    exchange.cancel_order(_oid, sym)
                                except Exception:
                                    pass
                            _PENDING_ORDERS.pop(sym, None)
                        continue

        # ══ [TIME-DECAY REPRICE] Progressively bring the order closer ══
        # Applied when: no fills yet, order still open.
        # Stage 0 → 1 → 2 → 3 (each reduces the dip by a fixed factor).
        # Stage 4 = cancel (handled by the timeout block below).
        if (getattr(CFG, 'ENTRY_TIME_DECAY', True)
                and float(rec.get('filled') or 0.0) <= 0.0):
            _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
            _elapsed_bars = (now - float(rec.get('placed_at') or now)) \
                            / max(_tf_sec, 1)
            _stage = int(rec.get('decay_stage') or 0)

            _target_stage = 0
            if _elapsed_bars > CFG.ENTRY_TIME_DECAY_BARS_3:
                _target_stage = 3
            elif _elapsed_bars > CFG.ENTRY_TIME_DECAY_BARS_2:
                _target_stage = 2
            elif _elapsed_bars > CFG.ENTRY_TIME_DECAY_BARS_1:
                _target_stage = 1

            if _target_stage > _stage:
                _ref_px = float(rec.get('entry_ref_price') or 0.0)
                _base_dip = float(rec.get('entry_base_dip') or 0.0)
                _side = rec.get('side', 'buy')
                _qty = float(rec.get('qty') or 0.0)

                if (_ref_px > 0 and _base_dip > 0 and _qty > 0):
                    _mult_map = {
                        1: float(CFG.ENTRY_TIME_DECAY_MULT_1),
                        2: float(CFG.ENTRY_TIME_DECAY_MULT_2),
                        3: float(CFG.ENTRY_TIME_DECAY_MULT_3),
                    }
                    _mult = _mult_map.get(_target_stage, 1.0)
                    _new_dip = _base_dip * _mult
                    if _side == 'buy':
                        _new_target = _ref_px - _new_dip
                    else:
                        _new_target = _ref_px + _new_dip

                    # Cancel current order (with sweep)
                    _oid = rec.get('order_id')
                    if _oid:
                        try:
                            exchange.cancel_order(_oid, sym)
                        except Exception as _e:
                            log.debug(f"[TimeDecay] {sym} cancel failed: {_e}")
                        time.sleep(0.15)
                        _sweep_pending_once(exchange, sym)
                        _rec_chk = _PENDING_ORDERS.get(sym)
                        if _rec_chk is None:
                            continue
                        if float(_rec_chk.get('filled') or 0.0) > 0.0:
                            # Fill arrived during cancel — let promotion handle it
                            continue

                    # Place new order at reduced dip
                    try:
                        _o = exchange.create_order(
                            sym, 'limit', _side, _qty, _new_target,
                            params={'timeInForce': 'GTX'}
                        )
                        rec['order_id'] = str(_o['id'])
                        rec['price'] = float(_new_target)
                        rec['decay_stage'] = int(_target_stage)
                        log.info(
                            f"[TimeDecay] {sym} stage={_target_stage} "
                            f"dip {_base_dip:.6f}→{_new_dip:.6f} "
                            f"({_mult*100:.0f}%) target={_new_target:.6f}"
                        )
                    except Exception as _e:
                        log.debug(f"[TimeDecay] {sym} reprice failed: {_e}")
                        # If reprice fails, keep old order — safer than nothing
                        rec['decay_stage'] = int(_target_stage)
                    # Fall through (don't continue) — timeout check below
                    # may still fire if we've passed stage 4.

        # ── Timeout → Stage 2 (إن مُفعَّل) أو cancel + drop ──
        timeout_s = float(rec.get('timeout_s') or CFG.PO_MAX_WAIT_S)
        elapsed = now - float(rec.get('placed_at') or now)

        if elapsed > timeout_s:
            # ══ [UNIFIED STAGE 2] ══
            _did_stage2 = False
            if getattr(CFG, 'UNIFIED_ENTRY_ENABLED', True):
                try:
                    _ad = rec.get('ad_ref')
                    _filled = float(rec.get('filled') or 0.0)
                    if _ad is not None and _filled <= 0.0:
                        _current_ci = len(_ad.closes) - 2  # آخر شمعة مغلقة
                        _current_fi = _current_ci - _ad.feat_start
                        if 0 <= _current_fi < len(_ad.score):
                            _sig = rec.get('signal_ref')
                            if _sig is None:
                                # إعادة بناء الإشارة من القاموس
                                from types import SimpleNamespace as _SNS
                                _sig = _SNS(
                                    symbol=sym,
                                    action=rec.get('action'),
                                    price=float(rec.get('price') or 0),
                                    sl=float(rec.get('price') or 0)
                                       - float(rec.get('orig_sl_dist') or 0)
                                       if rec.get('action') == 'BUY'
                                       else float(rec.get('price') or 0)
                                       + float(rec.get('orig_sl_dist') or 0),
                                    tp1=float(rec.get('price') or 0)
                                        + float(rec.get('orig_tp_dist') or 0)
                                        if rec.get('action') == 'BUY'
                                        else float(rec.get('price') or 0)
                                        - float(rec.get('orig_tp_dist') or 0),
                                    score=float(rec.get('score_ref') or 0),
                                    close_idx=int(rec.get('close_idx') or 0),
                                    feat_idx=int(rec.get('entry_fi') or 0),
                                )

                            _ok, _reason, _p_cur = _check_unified_stage2(
                                _sig, _ad, _current_ci, _current_fi, CFG
                            )
                            if _ok:
                                _geom = _recompute_entry_geometry_at_market(
                                    _sig, _ad, _current_ci, _current_fi, CFG
                                )
                                if _geom is not None:
                                    # 1) ألغِ الأمر المعلّق
                                    _oid = rec.get('order_id')
                                    if _oid:
                                        try:
                                            exchange.cancel_order(_oid, sym)
                                        except Exception:
                                            pass
                                        time.sleep(0.15)
                                        _sweep_pending_once(exchange, sym)
                                        # تحقق من عدم وجود fill جزئي
                                        _rec_chk = _PENDING_ORDERS.get(sym)
                                        if _rec_chk and \
                                           float(_rec_chk.get('filled') or 0.0) > 0.0:
                                            # fill جزئي وصل أثناء الإلغاء،
                                            # اترك _promote_pending_to_position
                                            # يتولى الأمر
                                            _did_stage2 = True
                                            continue

                                    # 2) نفّذ market order
                                    _qty_m = float(rec.get('qty') or 0)
                                    _side_m = 'buy' if rec.get('action') == 'BUY' \
                                              else 'sell'
                                    try:
                                        _mo = exchange.create_order(
                                            sym, 'market', _side_m, _qty_m,
                                            None,
                                            params={'reduceOnly': False},
                                        )
                                        _fv = verify_fill(
                                            exchange, _mo['id'], sym,
                                            timeout_s=3.0
                                        )
                                        if not (_fv and _fv.get('filled')):
                                            log.warning(
                                                f"[Unified-S2] {sym} market "
                                                f"order failed to fill"
                                            )
                                            _PENDING_ORDERS.pop(sym, None)
                                            continue
                                        _entry_px = float(_fv.get('avg_price')
                                                          or _p_cur)
                                        _actual_qty = float(_fv.get('qty')
                                                            or _qty_m)
                                    except Exception as _e:
                                        log.error(
                                            f"[Unified-S2] {sym} market "
                                            f"order exception: {_e}"
                                        )
                                        _PENDING_ORDERS.pop(sym, None)
                                        continue

                                    # 3) احسب المخاطرة الفعلية
                                    if rec.get('action') == 'BUY':
                                        _actual_risk = _entry_px - _geom['sl']
                                    else:
                                        _actual_risk = _geom['sl'] - _entry_px
                                    if _actual_risk <= 1e-12:
                                        log.warning(
                                            f"[Unified-S2] {sym} invalid "
                                            f"actual_risk after fill"
                                        )
                                        # أغلق فوراً
                                        try:
                                            _side_close = 'sell' \
                                                if rec.get('action') == 'BUY' \
                                                else 'buy'
                                            exchange.create_order(
                                                sym, 'market', _side_close,
                                                _actual_qty
                                            )
                                        except Exception:
                                            pass
                                        _PENDING_ORDERS.pop(sym, None)
                                        continue

                                    # 4) احسب الحجم مع مراعاة المخاطرة الفعلية
                                    _risk_frac = float(rec.get('dyn_risk')
                                                       or 0.01)
                                    _cap_now = float(rec.get('capital_at_placement')
                                                     or 0)
                                    if _cap_now <= 0:
                                        try:
                                            _bal = exchange.fetch_balance()
                                            _cap_now = float(
                                                _bal['USDT']['free']
                                            )
                                        except Exception:
                                            _cap_now = 0.0
                                    if _cap_now > 0:
                                        _equity_base = max(
                                            _cap_now - CFG.CAPITAL_FLOOR, 0.0
                                        )
                                        _risk_amt = _equity_base * _risk_frac
                                        _new_qty = min(
                                            _risk_amt / _actual_risk,
                                            _actual_qty
                                        )
                                        if _new_qty < _actual_qty * 0.95:
                                            _excess = _actual_qty - _new_qty
                                            try:
                                                _side_close = 'sell' \
                                                    if rec.get('action') == 'BUY' \
                                                    else 'buy'
                                                exchange.create_order(
                                                    sym, 'market', _side_close,
                                                    _excess
                                                )
                                                _actual_qty = _new_qty
                                            except Exception:
                                                pass

                                    # 5) احفظ المركز الجديد
                                    _trail_d, _trail_a = compute_trail_params(
                                        _ad, _current_fi
                                    )
                                    open_pos_live[sym] = {
                                        'action': rec.get('action'),
                                        'entry': _entry_px,
                                        'qty': _actual_qty,
                                        'sl': float(_geom['sl']),
                                        'tp1': float(_geom['tp1']),
                                        'T_info': float(rec.get('T_info')
                                                        or 0.0),
                                        'dyn_risk': _risk_frac,
                                        'entry_ts': time.time(),
                                        'fill_ratio': 1.0,
                                        'leverage': int(rec.get('leverage')
                                                        or 1),
                                        'trail_dist_frac': float(_trail_d),
                                        'trail_activate_frac': float(_trail_a),
                                        'sl_dist_initial': float(
                                            abs(_entry_px - _geom['sl'])
                                        ),
                                        'stage': 'S2',
                                    }

                                    log.info(
                                        f"✅ [Unified-S2] {sym} "
                                        f"{rec.get('action')} @ {_entry_px:.6f} "
                                        f"qty={_actual_qty:.6f} "
                                        f"sl={_geom['sl']:.6f} "
                                        f"tp={_geom['tp1']:.6f} "
                                        f"reason={_reason}"
                                    )

                                    # 6) ضع أوامر واقية
                                    try:
                                        _place_protective_orders(
                                            exchange, sym, open_pos_live[sym]
                                        )
                                        open_pos_live[sym]['_prot_last_sl'] \
                                            = float(_geom['sl'])
                                        open_pos_live[sym]['_prot_last_tp'] \
                                            = float(_geom['tp1'])
                                    except Exception as _e:
                                        log.warning(
                                            f"[Unified-S2] {sym} protective "
                                            f"orders failed: {_e}"
                                        )

                                    _PENDING_ORDERS.pop(sym, None)
                                    _did_stage2 = True
                                    continue
                except Exception as _e:
                    log.debug(f"[Unified-S2] {sym} exception: {_e}")

            if _did_stage2:
                continue

            # ── Cancel + drop (السلوك الأصلي) ──
            oid = rec.get('order_id')
            if oid:
                try:
                    exchange.cancel_order(oid, sym)
                except Exception:
                    pass
                time.sleep(0.2)
                _sweep_pending_once(exchange, sym)
                rec2 = _PENDING_ORDERS.get(sym)
                if rec2 and str(rec2.get('status')) == 'closed':
                    _promote_pending_to_position(exchange, sym, rec2, open_pos_live)
            log.info(f"[Pending] {sym} {rec.get('action')} timeout "
                     f"({elapsed:.0f}s > {timeout_s:.0f}s) — dropped")
            _PENDING_ORDERS.pop(sym, None)
            continue


# ════════════════════════════════════════════════════════════════
# [FIX-25] GTX pre-flight check
# ════════════════════════════════════════════════════════════════
#
# Prevents GTX rejections (-2010 / -5022) by adjusting the target
# BEFORE sending the order:
#   BUY : if target > best_bid  →  target = best_bid - tick
#   SELL: if target < best_ask  →  target = best_ask + tick
#
# Preserves maker-only execution (no slippage) and aligns with the
# mean-reversion strategy (BUY waits below market, SELL waits above).

_GTX_PREFLIGHT_ENABLED: bool = True
_GTX_PREFLIGHT_STATS: Dict = {
    "checked": 0,
    "adjusted": 0,
    "fetch_failed": 0,
    "last_report_ts": 0.0,
}


def _gtx_preflight(exchange, sym: str, side: str, target: float,
                    exchange_tick: Optional[float] = None) -> float:
    """[FIX-25] Adjust target so that GTX won't cross the book."""
    if not _GTX_PREFLIGHT_ENABLED:
        return target

    _GTX_PREFLIGHT_STATS["checked"] += 1

    tick = exchange_tick
    if tick is None or tick <= 0:
        try:
            tick = _get_tick_size(exchange, sym) or 0.0
        except Exception:
            tick = 0.0
    if tick <= 0:
        tick = max(target * 1e-6, 1e-8)

    try:
        ob = exchange.fetch_order_book(sym, limit=5)
        _rate_record(2.0)
    except Exception as e:
        _GTX_PREFLIGHT_STATS["fetch_failed"] += 1
        log.debug(f"[GTX-Preflight] {sym} book fetch failed: {e}")
        return target

    try:
        best_bid = float(ob["bids"][0][0])
        best_ask = float(ob["asks"][0][0])
    except (IndexError, ValueError, TypeError):
        return target

    if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
        return target

    if side == "buy":
        if target > best_bid:
            safe = best_bid - tick
            if safe <= 0:
                return target
            log.debug(
                f"[GTX-Preflight] {sym} BUY {target:.8f} → {safe:.8f} "
                f"(bid={best_bid:.8f}, tick={tick:.8f})"
            )
            _GTX_PREFLIGHT_STATS["adjusted"] += 1
            return float(safe)
    else:
        if target < best_ask:
            safe = best_ask + tick
            log.debug(
                f"[GTX-Preflight] {sym} SELL {target:.8f} → {safe:.8f} "
                f"(ask={best_ask:.8f}, tick={tick:.8f})"
            )
            _GTX_PREFLIGHT_STATS["adjusted"] += 1
            return float(safe)

    return target


def _gtx_preflight_log_stats() -> None:
    """Log pre-flight stats every 5 minutes."""
    now = time.time()
    if now - float(_GTX_PREFLIGHT_STATS.get("last_report_ts", 0.0)) < 300:
        return
    _GTX_PREFLIGHT_STATS["last_report_ts"] = now
    s = _GTX_PREFLIGHT_STATS
    if s["checked"] == 0:
        return
    log.info(
        f"[GTX-Preflight] checked={s['checked']}, "
        f"adjusted={s['adjusted']}, "
        f"fetch_failed={s['fetch_failed']}"
    )


# ══ end FIX-25 helpers ══


def place_pending_entry(exchange, sym: str, side: str, qty: float,
                        sig, timeout_s: float, leverage: int,
                        ad=None,
                        explicit_target: Optional[float] = None
                        ) -> Optional[Dict]:
    """
    Place a single Post-Only order and register it as pending (non-blocking).
    Returns the pending record or None on failure.
    """
    # ══ [SING-TIMING] حساب حالة الرنين مرة واحدة، واستخدامها في
    # كل من Layer 1 (timeout) و Layer 2 (marketable). ══
    _sing_state = "DORMANT"
    _sing_rho = 0.0
    _sing_timeout_reason = "default"
    try:
        if (getattr(CFG, 'SING_TIMING_ENABLED', False)
                and ad is not None):
            _sing_state, _sing_rho = _resonance_state_for_direction(
                ad, int(sig.feat_idx), sig.action, CFG
            )
    except Exception as _e:
        log.debug(f"[Sing-Timing] pre-compute state failed: {_e}")

    # ══ [SING-TIMING Layer 3A] Funding Guard ══
    # الغرض: تجنّب الدخول في نافذة N دقيقة قبل موعد التمويل.
    # السبب: الدخول قبل التمويل يعني دفع ~0.01% فوراً (لأن أول
    # دورة تمويل تحسب على أي مركز مفتوح عند اللحظة).
    # هذا يوفر على المدى الطويل ما يعادل ~5-10% من الرسوم.
    if (getattr(CFG, 'SING_FUNDING_GUARD_ENABLED', False)
            and _sing_state not in ("DECAYING", "INVALID")):
        try:
            _min_to_funding = _minutes_to_next_funding_utc(CFG)
            _window = int(getattr(
                CFG, 'SING_FUNDING_GUARD_MINUTES', 30
            ))
            if 0 <= _min_to_funding <= _window:
                log.info(
                    f"[Sing-Timing-L3A] {sym} {sig.action} "
                    f"rejected: funding in {_min_to_funding} min "
                    f"(≤ {_window})"
                )
                return None
        except Exception as _e:
            log.debug(f"[Sing-Timing-L3A] funding guard failed: {_e}")

    # ══ إذا كانت الحالة DECAYING، لا نضع أي أمر إطلاقاً ══
    if _sing_state == "DECAYING":
        log.info(
            f"[Sing-Timing] {sym} {sig.action} DECAYING "
            f"(rho={_sing_rho:+.3f}) — refusing pending order at source"
        )
        return None

    # ══ [RateLimit] skip if soft cap reached ══
    if not _rate_can_place():
        _RATE_TRACKER['rejected_count'] += 1
        log.debug(f"[RateLimit] {sym} placement skipped — usage high")
        return None

    # ══ [DYNAMIC-OFFSET-ALWAYS] ══
    # حساب offset ديناميكي (tick, σ_bar, ADV, order size) في كل المسارات.
    # الاتجاه: BUY → فوق المرجع، SELL → تحت المرجع.
    # هذا يضمن الملء عند أول تلامس، بغض النظر عن Watch mode.
    pen = float(CFG.PO_PENETRATION_BPS) * 1e-4

    # احسب ADV و σ_bar مرة واحدة
    _adv_for_off = 1e8
    try:
        if ad is not None and hasattr(ad, 'adv_usd'):
            _ci_a = int(getattr(sig, 'close_idx', -1))
            if 0 <= _ci_a < len(ad.adv_usd):
                _adv_for_off = float(ad.adv_usd[_ci_a])
    except Exception:
        pass

    _sig_for_off = 0.01
    try:
        _fi_o = int(getattr(sig, 'feat_idx', -1))
        if ad is not None and 0 <= _fi_o < len(ad.E_therm):
            _s = float(ad.E_therm[_fi_o])
            if np.isfinite(_s) and _s > 1e-6:
                _sig_for_off = _s
    except Exception:
        pass

    _dyn_offset = _watch_compute_entry_offset(
        tunnel_p=float(sig.price),
        sigma_bar=_sig_for_off,
        adv_usd=_adv_for_off,
        exchange=exchange,
        symbol=sym,
        qty=qty,
    )

    # ══ [FIX-4.2/4.3] Sanitize qty + notional ══
    qty = _round_qty(exchange, sym, float(qty))
    if qty <= 0:
        log.warning(f"[Pending] {sym} qty rounded to 0 — skip")
        return None
    _min_notional = _get_min_notional(exchange, sym)
    _approx_price = float(sig.price)
    if _approx_price <= 0:
        _approx_price = 1.0
    if qty * _approx_price < _min_notional:
        log.warning(f"[Pending] {sym} notional "
                    f"${qty*_approx_price:.2f} < MIN_NOTIONAL "
                    f"${_min_notional:.2f} — skip")
        return None

    # ══ تحديد الـ target ══
    if explicit_target is not None and explicit_target > 0:
        # Watch mode: يُمرَّر جاهزاً
        target = float(explicit_target)
    elif getattr(CFG, 'PO_FIXED_PRICE', True):
        # Base = tunnel، offset outward
        if side == 'buy':
            target = float(sig.price) + _dyn_offset
        else:
            target = float(sig.price) - _dyn_offset
    else:
        # --no-fixed-price: Base = close[sig.close_idx]، offset outward
        try:
            _base = float(sig.price)
            if ad is not None and hasattr(ad, 'closes'):
                _ci = int(getattr(sig, 'close_idx', -1))
                if 0 <= _ci < len(ad.closes):
                    _base = float(ad.closes[_ci])

            if side == 'buy':
                target = _base + _dyn_offset
            else:
                target = _base - _dyn_offset

            # Sanity gate
            try:
                ob = exchange.fetch_order_book(sym, limit=5)
                _mid = (float(ob['bids'][0][0])
                        + float(ob['asks'][0][0])) / 2.0
                if _mid > 0:
                    _gap_bps = abs(target - _mid) / _mid * 1e4
                    _max_gap = float(
                        getattr(CFG, 'PO_MAX_DRIFT_BPS', 5.0)
                    ) * 4.0
                    if _gap_bps > _max_gap:
                        log.info(
                            f"[Pending] {sym} target {target:.6f} "
                            f"is {_gap_bps:.1f}bps from mid "
                            f"(> {_max_gap:.1f}) — skip"
                        )
                        return None
            except Exception:
                pass
        except Exception as e:
            log.warning(
                f"[Pending] {sym} offset computation failed: {e} — "
                f"falling back to sig.price ± fixed pen"
            )
            _fallback_pen = max(pen, 1e-5)
            target = (float(sig.price) * (1.0 - _fallback_pen)
                      if side == 'buy'
                      else float(sig.price) * (1.0 + _fallback_pen))

    # ══ Log القرار ══
    log.debug(f"[Pending] {sym} base={'tunnel' if explicit_target is None else 'watch'} "
              f"offset={_dyn_offset:.6f} ({_dyn_offset/max(float(sig.price),1e-12)*1e4:.2f}bps) "
              f"target={target:.6f}")

    # ══ [SING-TIMING Layer 2] القرار: GTX أم Marketable ══
    # المنطق:
    #   - إذا SING_TIMING_ENABLED=False → GTX عادي (لا شيء يتغير).
    #   - إذا SING_TIMING_ENABLED=True و SING_ACTIVE_MARKETABLE=False
    #     → GTX عادي (Layer 1 فقط يعمل).
    #   - إذا SING_TIMING_ENABLED=True و SING_ACTIVE_MARKETABLE=True
    #     و _sing_state == "ACTIVE" → Marketable Limit.
    #   - غير ذلك → GTX عادي.
    _exec_mode = "gtx"
    _marketable_px = None

    if (getattr(CFG, 'SING_TIMING_ENABLED', False)
            and getattr(CFG, 'SING_ACTIVE_MARKETABLE', False)
            and _sing_state == "ACTIVE"):
        try:
            ob = exchange.fetch_order_book(sym, limit=5)
            _best_bid = float(ob['bids'][0][0])
            _best_ask = float(ob['asks'][0][0])
            _mid = (_best_bid + _best_ask) / 2.0
            _pen_bps = float(getattr(
                CFG, 'SING_ACTIVE_PENETRATION_BPS', 3.0
            ))
            _pen_frac = _pen_bps * 1e-4

            # BUY يقتحم ask صعوداً، SELL يقتحم bid هبوطاً
            if side == 'buy':
                _marketable_px = _best_ask * (1.0 + _pen_frac)
            else:
                _marketable_px = _best_bid * (1.0 - _pen_frac)

            # فحص الانزلاق: كم يبعد الـ marketable عن sig.price؟
            _slip_bps = (abs(_marketable_px - sig.price)
                          / max(sig.price, 1e-12) * 1e4)
            _max_slip = float(getattr(
                CFG, 'SING_ACTIVE_MAX_SLIP_BPS', 15.0
            ))

            if _slip_bps > _max_slip:
                log.info(
                    f"[Sing-Timing-L2] {sym} {sig.action} ACTIVE "
                    f"but slip {_slip_bps:.1f}bps > {_max_slip:.1f}bps "
                    f"— fallback to GTX"
                )
            else:
                o = exchange.create_order(
                    sym, 'limit', side, qty, _marketable_px,
                    params={}  # بدون GTX → يقطع السبريد كـ taker
                )
                _exec_mode = "marketable"
                target = _marketable_px
                log.info(
                    f"[Sing-Timing-L2] {sym} {sig.action} ACTIVE "
                    f"(rho={_sing_rho:+.3f}) → marketable @ "
                    f"{_marketable_px:.6f} (slip={_slip_bps:.1f}bps, "
                    f"mid={_mid:.6f})"
                )
        except Exception as _e:
            log.warning(
                f"[Sing-Timing-L2] {sym} marketable failed: {_e} "
                f"— falling back to GTX"
            )
            _exec_mode = "gtx"

    # ══ وضع الأمر النهائي ══
    if _exec_mode == "gtx":
        # ══ [FIX-25] Pre-flight: adjust to safe side BEFORE sending ══
        _tick_for_gtx = _get_tick_size(exchange, sym) or 0.0
        _orig_target = target
        target = _gtx_preflight(exchange, sym, side, target,
                                  exchange_tick=_tick_for_gtx)
        if target != _orig_target:
            log.debug(
                f"[FIX-25] {sym} GTX target adjusted "
                f"{_orig_target:.8f} → {target:.8f}"
            )

        try:
            o = exchange.create_order(
                sym, 'limit', side, qty, target,
                params={'timeInForce': 'GTX'}
            )
        except Exception as e:
            _emsg = str(e).lower()
            # [FIX-25] GTX rejected even after pre-flight.
            # Fetch book freshly and retry with the actual safe price.
            if ('-2010' in _emsg or '-5022' in _emsg
                    or 'post only' in _emsg or 'gtx' in _emsg):
                log.info(
                    f"[FIX-25] {sym} GTX rejected after pre-flight "
                    f"- fetching fresh book"
                )
                try:
                    _ob2 = exchange.fetch_order_book(sym, limit=5)
                    _rate_record(2.0)
                    _bb2 = float(_ob2['bids'][0][0])
                    _ba2 = float(_ob2['asks'][0][0])
                    _tick2 = _tick_for_gtx or target * 1e-5
                    if side == 'buy':
                        target2 = _bb2 - _tick2
                    else:
                        target2 = _ba2 + _tick2
                    log.info(
                        f"[FIX-25] {sym} retry target "
                        f"{target:.8f} → {target2:.8f} "
                        f"(bid={_bb2:.8f}, ask={_ba2:.8f})"
                    )
                    o = exchange.create_order(
                        sym, 'limit', side, qty, target2,
                        params={'timeInForce': 'GTX'}
                    )
                    target = target2
                except Exception as e2:
                    log.warning(
                        f"[Pending] {sym} GTX fallback failed: {e2}"
                    )
                    return None
            else:
                log.debug(f"[Pending] {sym} order rejected @ "
                          f"{target:.6f}: {e}")
                return None

    entry_fi = 0
    try:
        if ad is not None:
            entry_fi = max(0, min(sig.feat_idx, len(ad.E_therm) - 1))
    except Exception:
        entry_fi = 0

    # ══ [UNIFIED] اضبط المهلة على Stage 1 إن كان المنطق مفعّلاً ══
    if getattr(CFG, 'UNIFIED_ENTRY_ENABLED', True):
        _tf_sec_u = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
        _stage1_bars_u = effective_bars(
            int(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))
        )
        timeout_s = float(_stage1_bars_u * _tf_sec_u)

    # ══ [SING-TIMING Layer 1] تعديل المهلة حسب الحالة ══
    # (نستخدم _sing_state المحسوبة في بداية الدالة)
    if getattr(CFG, 'SING_TIMING_ENABLED', False):
        try:
            _tf_sec_u = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
            if _sing_state == "EMERGING":
                _bars = int(getattr(
                    CFG, 'SING_PENDING_WAIT_EMERGING', 2
                ))
                timeout_s = float(_bars * _tf_sec_u)
                _sing_timeout_reason = f"emerging({_bars}bars)"
                log.info(
                    f"[Sing-Timing] {sym} {sig.action} EMERGING "
                    f"(rho={_sing_rho:+.3f}) — timeout → "
                    f"{_bars} bars ({timeout_s:.0f}s)"
                )
            elif _sing_state == "ACTIVE":
                _bars = int(getattr(
                    CFG, 'SING_PENDING_WAIT_ACTIVE', 1
                ))
                timeout_s = float(_bars * _tf_sec_u)
                _sing_timeout_reason = f"active({_bars}bars)"
                log.debug(
                    f"[Sing-Timing] {sym} {sig.action} ACTIVE "
                    f"(rho={_sing_rho:+.3f}) — timeout → "
                    f"{_bars} bars ({timeout_s:.0f}s)"
                )
        except Exception as _e:
            log.debug(f"[Sing-Timing] L1 timeout hook failed: {_e}")

    # ══ [SING-TIMING Layer 1] فحص حالة الرنين عند وضع الأمر ══
    # الغرض: تعديل المهلة ديناميكياً حسب حالة الرنين.
    #   - DORMANT   → المهلة الافتراضية (8 شموع)
    #   - EMERGING  → 2 شموع (تسريع الانتظار)
    #   - ACTIVE    → 1 شمعة
    #   - DECAYING  → رفض الأمر نهائياً
    #   - INVALID   → المهلة الافتراضية
    _sing_state = "DORMANT"
    _sing_rho = 0.0
    _sing_timeout_reason = "default"
    try:
        if getattr(CFG, 'SING_TIMING_ENABLED', False) and ad is not None:
            _sing_state, _sing_rho = _resonance_state_for_direction(
                ad, int(sig.feat_idx), sig.action, CFG
            )
            _tf_sec_u = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600

            if _sing_state == "DECAYING":
                log.info(
                    f"[Sing-Timing] {sym} {sig.action} DECAYING "
                    f"(rho={_sing_rho:+.3f}) — refusing pending order"
                )
                return None

            if _sing_state == "EMERGING":
                _bars = int(getattr(
                    CFG, 'SING_PENDING_WAIT_EMERGING', 2
                ))
                timeout_s = float(_bars * _tf_sec_u)
                _sing_timeout_reason = f"emerging({_bars}bars)"
                log.info(
                    f"[Sing-Timing] {sym} {sig.action} EMERGING "
                    f"(rho={_sing_rho:+.3f}) — timeout → "
                    f"{_bars} bars ({timeout_s:.0f}s)"
                )
            elif _sing_state == "ACTIVE":
                _bars = int(getattr(
                    CFG, 'SING_PENDING_WAIT_ACTIVE', 1
                ))
                timeout_s = float(_bars * _tf_sec_u)
                _sing_timeout_reason = f"active({_bars}bars)"
                log.info(
                    f"[Sing-Timing] {sym} {sig.action} ACTIVE "
                    f"(rho={_sing_rho:+.3f}) — timeout → "
                    f"{_bars} bars ({timeout_s:.0f}s)"
                )
    except Exception as _e:
        log.debug(f"[Sing-Timing] place_pending hook failed: {_e}")

    # [FIX-05b] Read capital from run_live's published snapshot.
    # The original patch (FIX-05a) called fetch_balance() here on
    # every placement, burning rate-limit weight unnecessarily.
    # run_live() now publishes cap_live → _LAST_KNOWN_CAP after each
    # balance fetch; we reuse it.
    _cap_snapshot = float(_GLOBAL_STATE.get('last_cap', 0.0) or 0.0)
    if _cap_snapshot <= 0.0:
        # One-time bootstrap (only on first call before run_live
        # publishes anything). Cheap because it happens once.
        try:
            if ad is not None and not _GLOBAL_STATE.get('cap_bootstrapped', False):
                _bal_snap = exchange.fetch_balance()
                _cap_snapshot = float(
                    _bal_snap['USDT'].get('free') or 0.0
                )
                _GLOBAL_STATE['last_cap'] = _cap_snapshot
                _GLOBAL_STATE['cap_bootstrapped'] = True
        except Exception:
            _cap_snapshot = 0.0

    # [FIX-15] Trail params snapshot
    _trail_d_snapshot, _trail_a_snapshot = 0.003, 0.004
    try:
        if ad is not None:
            _trail_d_snapshot, _trail_a_snapshot = compute_trail_params(
                ad, max(0, min(int(sig.feat_idx), len(ad.E_therm) - 1))
            )
    except Exception:
        pass

    # [FIX-15b] Trail params snapshot (robust version)
    _trail_d_snapshot, _trail_a_snapshot = 0.003, 0.004
    try:
        if ad is not None and hasattr(ad, 'E_therm') \
                and len(ad.E_therm) > 0:
            _fi_snap = max(0, min(int(getattr(sig, 'feat_idx', 0)),
                                  len(ad.E_therm) - 1))
            _td_snap, _ta_snap = compute_trail_params(ad, _fi_snap)
            if _td_snap > 0 and _ta_snap > 0:
                _trail_d_snapshot = float(_td_snap)
                _trail_a_snapshot = float(_ta_snap)
    except Exception as _e:
        log.debug(f"[FIX-15b] trail snapshot failed: {_e}")

    rec = {
        'order_id': str(o['id']),
        'sym': sym,
        'side': side,
        'action': sig.action,
        'qty': float(qty),
        'price': target,
        'orig_sl_dist': float(abs(sig.price - sig.sl)),
        'orig_tp_dist': float(abs(sig.tp1 - sig.price)),
        'T_info': float(sig.T_info_val),
        'dyn_risk': float(sig.dynamic_risk),
        'leverage': int(leverage),
        'entry_fi': int(entry_fi),
        'placed_at': time.time(),
        'timeout_s': float(timeout_s),
        'status': 'open',
        'filled': 0.0,
        'avg_price': 0.0,
        'signal_ref': sig,
        '_orig_score': float(getattr(sig, 'score', 0.0)),
        'score_ref': float(sig.score),
        'capital_at_placement': float(
            _cap_snapshot if '_cap_snapshot' in dir() else 0.0
        ),
        'mmr_at_placement': float(
            _get_mmr_for_symbol(exchange, sym)
        ),
        # ══ [TIME-DECAY] Reference state for repricing ══
        'entry_ref_price': float(getattr(sig, 'entry_ref_price', 0.0)
                                  or sig.price),
        'entry_base_dip': float(getattr(sig, 'entry_base_dip', 0.0)
                                 or abs(target - sig.price)),
        'decay_stage': 0,
        'ad_ref': ad,
        # ══ [SING-TIMING Layer 1] لقطة حالة الرنين عند الوضع ══
        'sing_state_at_placement': str(_sing_state),
        'sing_rho_at_placement': float(_sing_rho),
        'sing_timeout_reason': str(_sing_timeout_reason),
        # ══ [SING-TIMING Layer 2] نمط التنفيذ ══
        'execution_mode': str(_exec_mode),
        'marketable_px': (float(_marketable_px)
                           if _marketable_px is not None else 0.0),
        # [FIX-15] snapshot trail params to avoid needing ad_ref later
        'trail_dist_frac': float(_trail_d_snapshot),
        'trail_activate_frac': float(_trail_a_snapshot),
    }
    _PENDING_ORDERS[sym] = rec
    log.info(f"[Pending] {sig.action} {sym} @ {target:.6f} qty={qty:.6f} "
             f"id={rec['order_id']} (timeout={timeout_s:.0f}s)")
    return rec

# ════════════════════════════════════════════════════════════════
# § 18.98  Kill Switch (HMAC-authenticated)
# ════════════════════════════════════════════════════════════════

import hmac as _hmac
import hashlib as _hashlib

_KILL_SWITCH_STATE: Dict = {
    'state': 'ARMED',
    'reason': '',
    'triggered_at': 0.0,
    'last_file_mtime': 0.0,
}


def _kill_sign(reason: str, secret: str) -> str:
    """Compute HMAC-SHA256 token for a given reason."""
    if not secret:
        return ""
    return _hmac.new(secret.encode(), reason.encode(), _hashlib.sha256).hexdigest()


def _kill_verify(reason: str, token: str, secret: str) -> bool:
    """Constant-time verify."""
    if not secret or not token:
        return False
    expected = _kill_sign(reason, secret)
    try:
        return _hmac.compare_digest(expected, token)
    except Exception:
        return False


def _kill_switch_check_file(path: str, secret: str) -> Tuple[bool, str]:
    """
    Read kill switch file. Format:
        {"state": "TRIGGERED", "reason": "...", "token": "..."}
    Returns (should_trigger, reason). Verifies HMAC.
    """
    if not secret:
        return False, ""
    if not os.path.exists(path):
        return False, ""
    try:
        mtime = os.path.getmtime(path)
        # Skip if file not modified since last check
        if mtime <= _KILL_SWITCH_STATE.get('last_file_mtime', 0.0):
            return False, ""
        _KILL_SWITCH_STATE['last_file_mtime'] = mtime

        with open(path) as f:
            data = json.load(f)
        state = str(data.get('state') or 'ARMED')
        reason = str(data.get('reason') or '')
        token = str(data.get('token') or '')

        if state != 'TRIGGERED':
            return False, ""
        if not _kill_verify(reason, token, secret):
            log.warning(f"[KillSwitch] invalid HMAC for reason='{reason}' — ignoring")
            return False, ""
        return True, reason
    except Exception as e:
        log.debug(f"[KillSwitch] file check failed: {e}")
        return False, ""


def _kill_switch_check_auto(cap_live: float, cap_peak: float,
                             daily_loss: float, consec_losses: int
                             ) -> Tuple[bool, str]:
    """
    Automatic triggers (no HMAC needed — internal).
    """
    try:
        # Drawdown from peak
        if cap_peak > 0:
            dd = (cap_peak - cap_live) / cap_peak
            if dd >= float(CFG.MAX_DRAWDOWN_HALT) and CFG.MAX_DRAWDOWN_HALT < 1.0:
                return True, f"drawdown_{dd*100:.1f}%"

        # Consecutive losses (very loose default)
        if consec_losses >= 6:
            return True, f"consec_losses={consec_losses}"

        # Daily loss (only if tracked)
        if daily_loss <= -0.05:
            return True, f"daily_loss={daily_loss*100:.1f}%"

        return False, ""
    except Exception as e:
        log.debug(f"[KillSwitch] auto check failed: {e}")
        return False, ""


def _kill_switch_trigger(reason: str, exchange,
                          open_pos_live: Dict, state_file: str) -> None:
    """
    Emergency: flatten all positions and stop.
    """
    log.critical(f"[KillSwitch] TRIGGERED: {reason}")
    _KILL_SWITCH_STATE['state'] = 'TRIGGERED'
    _KILL_SWITCH_STATE['reason'] = reason
    _KILL_SWITCH_STATE['triggered_at'] = time.time()

    # Flatten every open position
    for sym in list(open_pos_live.keys()):
        try:
            pos = open_pos_live[sym]
            close_side = 'sell' if pos['action'] == 'BUY' else 'buy'
            o = exchange.create_order(sym, 'market', close_side, pos['qty'])
            v = verify_fill(exchange, o['id'], sym, timeout_s=3.0)
            px = v['avg_price'] if v and v['filled'] else 0.0
            log.critical(f"[KillSwitch] flattened {sym} @ {px:.6f}")
            del open_pos_live[sym]
        except Exception as e:
            log.error(f"[KillSwitch] flatten {sym} failed: {e}")

    # Cancel all pending
    for sym in list(_PENDING_ORDERS.keys()):
        rec = _PENDING_ORDERS[sym]
        oid = rec.get('order_id')
        if oid:
            try:
                exchange.cancel_order(oid, sym)
            except Exception:
                pass
        _PENDING_ORDERS.pop(sym, None)

    # Persist state
    try:
        with open(state_file, 'w') as f:
            json.dump(open_pos_live, f, indent=2, default=str)
    except Exception:
        pass
    save_pending_orders()

# ════════════════════════════════════════════════════════════════
# § 18.96  Extended Reconciliation (_SYMBOL_META ↔ Exchange)
# ════════════════════════════════════════════════════════════════

def reconcile_symbol_meta(exchange, symbols: List[str]) -> int:
    """
    For each symbol in _SYMBOL_META, verify leverage/margin match exchange.
    Fix mismatches when no position exists.
    Returns count of fixed entries.
    """
    global _SYMBOL_META
    fixed = 0
    for sym in list(_SYMBOL_META.keys()):
        if sym not in symbols:
            continue
        meta = _SYMBOL_META[sym]
        if not meta.get('setup_done'):
            continue

        # Check for existing position
        has_pos = False
        try:
            positions = _fake_pos_list(exchange, sym)
            for p in positions:
                amt = float(p['info'].get('positionAmt', 0) or 0)
                if abs(amt) > 0:
                    has_pos = True
                    break
        except Exception as e:
            log.debug(f"[ReconcileMeta] fetch_positions {sym}: {e}")
            continue

        # Verify current leverage
        try:
            lev_info = exchange.fetch_leverage(sym)
            cur_lev = int(lev_info.get('leverage', 0))
        except Exception as e:
            log.debug(f"[ReconcileMeta] fetch_leverage {sym}: {e}")
            continue

        cached_lev = int(meta.get('leverage', 0))
        if cur_lev != cached_lev:
            if has_pos:
                log.warning(
                    f"[ReconcileMeta] {sym} cached_lev={cached_lev}x "
                    f"but exchange={cur_lev}x (position open — updating cache)"
                )
                meta['leverage'] = cur_lev
            else:
                log.warning(
                    f"[ReconcileMeta] {sym} cached_lev={cached_lev}x "
                    f"but exchange={cur_lev}x (no position — updating cache)"
                )
                meta['leverage'] = cur_lev
            meta['updated_ts'] = time.time()
            fixed += 1

    if fixed > 0:
        save_symbol_meta()
        log.info(f"[ReconcileMeta] {fixed} symbols updated")
    return fixed

# ════════════════════════════════════════════════════════════════
# § 19  وضع Live / Testnet
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# § 19  وضع Live / Testnet (النسخة المحسنة عالية السرعة - HFT)
# ════════════════════════════════════════════════════════════════

def run_live(cfg, exchange):
    """
    محرك التداول الحي والـ Testnet عالي التردد (HFT):
    - يلتزم بميكانيكا التكميم والسببية المستمرة ومعدل استقصاء 5 ثوانٍ.
    - يقرأ مستشعر الأوج للتكامل الحركي (Action Integral) في الوقت الفعلي.
    - يطبق قانون القوة لـ بئر دريخليه (10$ لحماية رأس المال المجهري).
    """
    log.info(f"🔴 [{cfg.mode.upper()}] بدء التشغيل (State Machine v2)")
    state_file = f"live_state_{cfg.mode}.json"
    open_pos_live: Dict[str, Dict] = {}

    # ══ [State] Load persistent positions ══
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                open_pos_live = json.load(f)
            log.info(f"  [State] Restored {len(open_pos_live)} positions from {state_file}")

            # ══ [LIQ-BACKFILL] Ensure every loaded position has a Liq estimate ══
            _backfilled = 0
            for _sym_bf, _pos_bf in open_pos_live.items():
                if _pos_bf.get('liq_price_estimated') is None:
                    _est = _estimate_liq_for_position(_pos_bf)
                    if _est is not None:
                        _pos_bf['liq_price_estimated'] = _est
                        _backfilled += 1
            if _backfilled > 0:
                log.info(f"  [State] Backfilled liq_price_estimated for "
                         f"{_backfilled} positions (fallback MMR)")
        except Exception as e:
            log.warning(f"  [State] load failed: {e}")

    # ══ [State] Load persistent symbol metadata (leverage/margin/setup) ══
    load_symbol_meta(cfg.mode)
    # ══ [Pending] Load persisted pending orders ══
    load_pending_orders(cfg.mode)

    # ══ [Watch] Load persisted watched signals ══
    load_watched_signals(cfg.mode)
    log.info(f"  [Watch] Active watched signals: {len(_WATCHED_SIGNALS)}")

    _stale = _pending_drop_stale(exchange, max_age_s=max(3600.0, CFG.PO_MAX_WAIT_S * 4))
    if _stale > 0:
        log.info(f"[Pending] Dropped {_stale} stale entries on startup")
    log.info(f"  [Pending] Active pending orders: {len(_PENDING_ORDERS)}")

    # ══ [State] Initial reconciliation with exchange ══
    _pre_syms = list(open_pos_live.keys()) or scan_top_assets(exchange)
    open_pos_live = reconcile_state_machine(exchange, open_pos_live, _pre_syms)
    log.info(f"  [State] After initial sync: {len(open_pos_live)} positions")

    # ══ [LAYER 7] Ensure every restored position has fresh protective orders ══
    # [DUPLICATE-FIX] defer if pending exists — لأن الترقية ستضعها
    # بشكل صحيح، ووضعها الآن يسبب تكراراً على البورصة.
    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        _prot_ok = 0
        _prot_fail = 0
        _prot_deferred = 0
        _prot_dropped_pending = 0
        for _sym_p, _pos_p in list(open_pos_live.items()):
            _pending_rec = _PENDING_ORDERS.get(_sym_p)
            if _pending_rec is not None:
                # جلب الحالة الحديثة
                _status = str(_pending_rec.get('status') or 'open')
                try:
                    _sweep_pending_once(exchange, _sym_p)
                    _pending_rec = _PENDING_ORDERS.get(_sym_p)
                    if _pending_rec is not None:
                        _status = str(_pending_rec.get('status') or 'open')
                except Exception as _e:
                    log.debug(f"[Prot] sweep {_sym_p} failed: {_e}")

                if _status == 'closed':
                    log.info(
                        f"[Prot] {_sym_p} pending already closed — "
                        f"dropping record, placing protection now"
                    )
                    _PENDING_ORDERS.pop(_sym_p, None)
                    _prot_dropped_pending += 1
                    # continue to place protection below
                else:
                    log.info(
                        f"[Prot] {_sym_p} pending status={_status} — "
                        f"deferring protective placement"
                    )
                    _prot_deferred += 1
                    continue

            _pos_p.pop('_prot_last_sl', None)
            _pos_p.pop('_prot_last_tp', None)
            try:
                if _place_protective_orders(exchange, _sym_p, _pos_p):
                    _pos_p['_prot_last_sl'] = float(_pos_p.get('sl') or 0)
                    _pos_p['_prot_last_tp'] = float(_pos_p.get('tp1') or 0)
                    _prot_ok += 1
                else:
                    _prot_fail += 1
            except Exception as _e:
                log.warning(f"[Prot] restore {_sym_p} failed: {_e}")
                _prot_fail += 1
        log.info(f"  [Prot] restored={_prot_ok} "
                 f"deferred={_prot_deferred} "
                 f"dropped={_prot_dropped_pending} "
                 f"failed={_prot_fail}")

    # ══ [RE-ENTRY COOLDOWN] track last exit time per symbol ══
    last_exit_time: Dict[str, float] = {}

    corr_cache: Dict = {}

    log.info("⏳ جلب الزمكان المالي التاريخي (هذه العملية تحدث مرة واحدة فقط)...")
    top_syms = scan_top_assets(exchange)

    # ══ [DATA-LENGTH-FIX] Live needs real history, not 60 days ══
    # Backtest uses 730 days; live used 60 → KMeans collapsed (H_train ≈ 0.2).
    # 365 days on 1h ≈ 8760 bars — enough for stable K=11 clustering.
    # Startup cost: ~5–8 minutes for 50 symbols. One-time only.
    _live_history_days = int(getattr(CFG, 'LIVE_HISTORY_DAYS', 365))
    cached_data = fetch_all(top_syms, exchange, cfg.timeframe,
                            days=_live_history_days, workers=5)

    # ══ [FIX-01-PROPER] Prefetch leverage tiers for all live symbols ══
    try:
        prefetch_all_leverage_tiers(exchange, list(cached_data.keys()))
    except Exception as _e:
        log.warning(f"[LevTiers] live prefetch failed: {_e}")


    # ══ [HELD SYMBOLS] Ensure open positions are always tracked ══
    _held = list(open_pos_live.keys())
    _missing = [s for s in _held if s not in top_syms]
    if _missing:
        log.info(f"[State] {len(_missing)} held symbols not in universe — adding")
        top_syms = list(top_syms) + _missing
        _extra_data = fetch_all(_missing, exchange, cfg.timeframe, days=60, workers=3)
        cached_data.update(_extra_data)
        log.info(f"[State] Added: {_missing}")

    last_scan_time = time.time()
    peak_cap_live = cfg.INITIAL_CAPITAL    
    # ══ [Cap persistence] last known good cap_live ══
    _last_known_cap = float(cfg.INITIAL_CAPITAL)
    if not cached_data:
        log.error("فشل في تحميل التاريخ الأولي، تأكد من الاتصال بالأنترنت.")
        return


    log.info("🚀 تم بناء الذاكرة التاريخية. بدء حلقة التداول اللحظي...")

    loop_iter = 0
    while True:
        try:
            t0 = time.time()
            # ══ [RateLimit] periodic report ══
            _rate_report()
            # [FIX-09-PROPER] pos-cache stats
            _pos_cache_log_stats()
            # [UNIFIED] stats logger
            _unified_log_stats()
            # ══ [KILL SWITCH] check every cycle ══
            if getattr(CFG, 'KILL_SWITCH_ENABLED', True):
                # File-based HMAC trigger
                _should_kill, _kill_reason = _kill_switch_check_file(
                    CFG.KILL_SWITCH_FILE, CFG.KILL_SWITCH_SECRET
                )
                if _should_kill:
                    _kill_switch_trigger(_kill_reason, exchange,
                                          open_pos_live, state_file)
                    return
                # Automatic triggers (drawdown etc.)
                _auto_kill, _auto_reason = _kill_switch_check_auto(
                    cap_live=cap_live if 'cap_live' in dir() else cfg.INITIAL_CAPITAL,
                    cap_peak=peak_cap_live,
                    daily_loss=0.0,
                    consec_losses=0,
                )
                if _auto_kill:
                    _kill_switch_trigger(_auto_reason, exchange,
                                          open_pos_live, state_file)
                    return
            loop_iter += 1

            # ══ [WATCH-THEN-TRIGGER] Check watched signals ══
            try:
                monitor_watch_signals(
                    exchange, open_pos_live,
                    assets=assets if 'assets' in dir() else None,
                    loop_iter=loop_iter
                )
            except Exception as _e:
                log.warning(f"[Watch] monitor error: {_e}")


            # ══ [Pending] Sweep pending orders every cycle ══
            # [Sing-Timing] نمرّر assets ليتمكن الفحص من قراءة الرنين الحالي.
            try:
                monitor_pending_orders(
                    exchange, open_pos_live, loop_iter,
                    assets=assets if 'assets' in dir() else None
                )
            except Exception as _e:
                log.warning(f"[Pending] monitor error: {_e}")
            
            # ══ [ReconcileMeta] verify symbol metadata rarely ══
            # [PERF-FIX] 1) Init to NOW (was 0.0 → ran immediately on first loop
            #              with 50 symbols = 100 API calls = 30-60s freeze)
            #            2) Only held symbols
            #            3) Every 6 hours (was 30 min)
            if not hasattr(run_live, '_last_meta_reconcile'):
                run_live._last_meta_reconcile = time.time()
            _meta_syms = list(set(open_pos_live.keys())
                              | set(_PENDING_ORDERS.keys()))
            if (_meta_syms
                    and time.time() - run_live._last_meta_reconcile > 21600):
                try:
                    reconcile_symbol_meta(exchange, _meta_syms)
                except Exception as e:
                    log.warning(f"[ReconcileMeta] failed: {e}")
                run_live._last_meta_reconcile = time.time()

            # تحديث دوري لقائمة الأزواج لتجنب جمود السيولة
            if time.time() - last_scan_time > 4 * 3600:
                log.info("🔄 تحديث قائمة الأصول ومزامنة التاريخ العميق...")
                _new_syms = scan_top_assets(exchange)
                # Preserve held symbols
                _held_now = list(open_pos_live.keys())
                _add_back = [s for s in _held_now if s not in _new_syms]
                if _add_back:
                    log.info(f"[State] Preserving {len(_add_back)} held symbols: {_add_back}")
                    _new_syms = list(_new_syms) + _add_back
                top_syms = _new_syms
                cached_data = fetch_all(top_syms, exchange, cfg.timeframe,
                                        days=60, workers=5)
                last_scan_time = time.time()
                corr_cache.clear()

            try:
                bal = exchange.fetch_balance()
                # ══ [LIVE-CAPITAL] استخدم LIVE_TRADING_CAPITAL إن كان مضبوطاً.
                _bal_free = float(bal['USDT'].get('free') or 0)
                _bal_total = float(bal['USDT'].get('total') or 0)
                _fixed_cap = float(getattr(CFG, 'LIVE_TRADING_CAPITAL', 0.0))
                if _fixed_cap > 0:
                    cap_live = _fixed_cap
                else:
                    # السلوك الافتراضي: free (الحد المتداول الفعلي)
                    cap_live = _bal_free
                _last_known_cap = cap_live
                # [FIX-05c] Publish to module-level so place_pending_entry
                # can read it without an extra fetch_balance() call.
                _GLOBAL_STATE['last_cap'] = float(cap_live)
            except Exception as e:
                log.warning(f"[Balance] fetch failed: {e}; "
                            f"using last known ${_last_known_cap:.2f}")
                cap_live = _last_known_cap

            peak_cap_live = max(peak_cap_live, cap_live)
            # [PERF-FIX] كان int(time.time()/60)%5 ينفَّذ لكل دورة داخل الدقيقة
            if not hasattr(run_live, '_last_pos_reconcile'):
                run_live._last_pos_reconcile = time.time()
            if (time.time() - run_live._last_pos_reconcile > 1800
                    and len(open_pos_live) > 0):
                try:
                    open_pos_live = reconcile_positions(exchange, open_pos_live)
                except Exception as _e:
                    log.warning(f"[Reconcile] positions failed: {_e}")
                run_live._last_pos_reconcile = time.time()
            assets = {}
            # ══ [LIVE CACHE] track last_closed per symbol ══
            _current_last_closed: Dict[str, int] = {}

            _tf_sec_local = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
            _smart = getattr(CFG, 'SMART_OHLCV_ENABLED', True)
            _ohlcv_fetched = 0
            _ohlcv_skipped = 0

            for sym in top_syms:
                if sym not in cached_data: continue
                try:
                    # ══ [Smart OHLCV] skip fetch if no new bar ══
                    if _smart and not _needs_ohlcv_refresh(cached_data[sym], _tf_sec_local):
                        _ohlcv_skipped += 1
                        # Still use the cached data for this symbol
                        _tf_sec_s = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                        _lc_ts = _last_closed_bar_ts(cached_data[sym], _tf_sec_s)
                        _current_last_closed[sym] = _lc_ts
                        ad = _live_cache_get(sym, cfg.timeframe, _lc_ts)
                        if ad is None and not _degenerate_get(sym, cfg.timeframe, _lc_ts):
                            _min_bars = int(getattr(CFG, 'LIVE_MIN_BARS_FOR_PROCESS', 2000))
                            if len(cached_data[sym]) < _min_bars:
                                log.debug(f"[Warmup] {sym} has "
                                          f"{len(cached_data[sym])} bars "
                                          f"(< {_min_bars}) — skip")
                            else:
                                ad = process_asset(sym, cached_data[sym],
                                                    current_capital=cap_live)
                                if ad is not None:
                                    _live_cache_put(sym, cfg.timeframe, _lc_ts, ad)
                                else:
                                    _degenerate_put(sym, cfg.timeframe, _lc_ts)
                        if ad:
                            assets[sym] = ad
                        continue

                    new_candles = exchange.fetch_ohlcv(sym, cfg.timeframe, limit=3)
                    _rate_record(1.0)
                    _ohlcv_fetched += 1
                    df_new = pd.DataFrame(new_candles, columns=['ts','Open','High','Low','Close','Volume'])
                    df_new['ts'] = pd.to_datetime(df_new['ts'], unit='ms', utc=True)
                    df_new = df_new.set_index('ts').astype(float)
                    df_combined = pd.concat([cached_data[sym], df_new])
                    # ══ [DATA-LENGTH-FIX] tail(1044) was too aggressive ══
                    # KMeans needs thousands of bars to form stable clusters.
                    # 8000 bars on 1h ≈ 11 months — matches the training scale.
                    _keep = int(getattr(CFG, 'LIVE_TAIL_BARS', 8000))
                    cached_data[sym] = (df_combined[
                        ~df_combined.index.duplicated(keep='last')
                    ].sort_index().tail(_keep))

                    # ══ [LIVE CACHE] Look up by (sym, tf, last_closed_ts) ══
                    _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                    _lc_ts = _last_closed_bar_ts(cached_data[sym], _tf_sec)
                    _current_last_closed[sym] = _lc_ts

                    ad = _live_cache_get(sym, cfg.timeframe, _lc_ts)
                    if ad is None and not _degenerate_get(sym, cfg.timeframe, _lc_ts):
                        _min_bars = int(getattr(CFG, 'LIVE_MIN_BARS_FOR_PROCESS', 2000))
                        if len(cached_data[sym]) < _min_bars:
                            log.debug(f"[Warmup] {sym} has "
                                      f"{len(cached_data[sym])} bars "
                                      f"(< {_min_bars}) — skip")
                        else:
                            ad = process_asset(sym, cached_data[sym],
                                                current_capital=cap_live)
                            if ad is not None:
                                _live_cache_put(sym, cfg.timeframe, _lc_ts, ad)
                            else:
                                _degenerate_put(sym, cfg.timeframe, _lc_ts)
                    if ad:
                        assets[sym] = ad
                except Exception as e:
                    log.warning(f"فشل التحديث اللحظي لـ {sym}: {e}")

            # ══ [LIVE CACHE] prune stale + report stats ══
            if _current_last_closed:
                _removed = _live_cache_prune_stale(_current_last_closed)
                if _removed > 0:
                    log.debug(f"[LiveCache] pruned {_removed} stale entries")
                _live_cache_log_stats()

            if not corr_cache: 
                corr_cache = precompute_correlations(assets)

            # 1. مراقبة وإغلاق المراكز الحية
            for sym in list(open_pos_live.keys()):
                pos = open_pos_live[sym]

                # ══ [MON-FALLBACK] Monitor even if `ad` unavailable ══
                # Physics-based exits (Apex, Topo-Div) require `ad`.
                # SL/TP/Liq/MaxHold/Trailing work without it (ticker only).
                ad = assets.get(sym)

                # ══ [LAYER 4] Always prefer live ticker for SL/TP/Liq ══
                # ad.closes[-1] is only refreshed when a new bar opens.
                # On 15m/1h/4h, it can be stale for many minutes. The ticker
                # is fresh every poll. Cost: weight 2 per symbol per cycle.
                price = None
                _live_src = "none"
                if getattr(CFG, 'LIVE_PRICE_ENABLED', True):
                    try:
                        _tk = exchange.fetch_ticker(sym)
                        _rate_record(float(getattr(CFG,
                            'LIVE_PRICE_RATE_WEIGHT', 2.0)))
                        _p = float(_tk.get('last') or 0)
                        if _p > 0:
                            price = _p
                            _live_src = "ticker"
                    except Exception as _e:
                        log.debug(f"[LivePrice] {sym} ticker failed: {_e}")

                # Fallback: stale close from ad if ticker failed
                if (price is None
                        and getattr(CFG, 'LIVE_PRICE_FALLBACK_TO_STALE', True)
                        and ad is not None):
                    try:
                        price = float(ad.closes[-1])
                        _live_src = "stale_close"
                    except Exception:
                        price = None

                if price is None or price <= 0:
                    log.debug(f"[LivePrice] {sym} no price source — skip")
                    continue

                # [FIX-7.1] fi points to last CLOSED bar to avoid
                # look-ahead. In live, ad.closes[-1] is the forming bar.
                fi = (len(ad.score) - 2) if ad is not None else -1
                if fi < 0:
                    fi = 0

                ex = False
                rsn = ""

                # ── Physics-based exits (require ad) ──
                if ad is not None:
                    # Apex
                    is_apex, apex_rsn = False, ""
                    if getattr(CFG, 'APEX_ENABLED', True):
                        is_apex, apex_rsn = check_thermodynamic_apex(
                            pos['action'], pos['entry'], price, ad, fi
                        )
                    if is_apex:
                        ex = True; rsn = apex_rsn

                    # Topo-Div
                    if not ex and fi > 0:
                        div_t = (ad.V[fi] - ad.V[fi-1]) / (ad.V[fi-1] + 1e-12)
                        if div_t > cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0:
                            ex = True; rsn = f"Topo-Div({div_t:.3f})"

                # (Topo-Div already checked above — removed duplicate)

                # ── MaxHold ── [FIX-22] bar-index anchor
                if not ex:
                    _entry_ci_mh = int(pos.get('_entry_ci', 0) or 0)
                    _ci_now_mh = ((len(ad.closes) - 2)
                                   if ad is not None else 0)
                    if _entry_ci_mh > 0 and _ci_now_mh > _entry_ci_mh:
                        bars_held = _ci_now_mh - _entry_ci_mh
                    else:
                        _ets = pos.get('entry_ts', 0)
                        _tf_s = (CFG.TF_SECONDS
                                  if CFG.TF_SECONDS > 0 else 3600)
                        bars_held = ((time.time() - _ets) / _tf_s
                                      if _ets > 0 else 0)
                    if bars_held > effective_bars(cfg.MAX_HOLD_BARS):
                        ex = True
                        rsn = f"MaxHold({int(bars_held)}bars)"

                # ── [FIX 3] Time-based kill ──
                if (not ex
                        and getattr(CFG, 'TIME_KILL_ENABLED', False)
                        and entry_ts > 0):
                    _tk_bars = effective_bars(int(getattr(CFG, 'TIME_KILL_BARS', 10)))
                    _bars_now = (time.time() - entry_ts) / (
                        CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600)
                    if _bars_now >= _tk_bars:
                        _entry_px = float(pos['entry'])
                        _sl_d0 = float(pos.get('sl_dist_initial', 0) or 0)
                        if _sl_d0 > 0 and _entry_px > 0:
                            if pos['action'] == "BUY":
                                _pnl_f = (price - _entry_px) / _entry_px
                            else:
                                _pnl_f = (_entry_px - price) / _entry_px
                            _sl_f0 = _sl_d0 / _entry_px
                            _r_now = _pnl_f / _sl_f0 if _sl_f0 > 0 else 0.0
                            _min_r = float(getattr(CFG, 'TIME_KILL_MIN_R', 0.5))
                            if _r_now < _min_r:
                                ex = True
                                rsn = f"TimeKill({_r_now:.2f}R)"

                # ── Trailing SL (dynamic σ-scaled) ──
                # [GATE] يُشغّل Trailing فقط إذا كان TRAIL_ENABLED=True.
                # إذا كان False، لا يتحرك SL أبداً بعد الدخول (يبقى كما
                # وُضع عند الدخول). هذا مطابق لسلوك الباكتيست.
                if not ex and getattr(CFG, 'TRAIL_ENABLED', True):
                    entry_px = float(pos['entry'])
                    _sl_before = float(pos['sl'])
                    _td = float(pos.get('trail_dist_frac', CFG.TRAIL_DISTANCE))
                    # ══ [FIX 1] Activation at R-multiple of initial SL ══
                    _sl_dist_init = float(pos.get('sl_dist_initial', 0) or 0)
                    _sl_frac_init = (_sl_dist_init / entry_px
                                     if entry_px > 0 and _sl_dist_init > 0
                                     else 0.01)
                    _act_at_r = float(getattr(CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
                    _ta = _sl_frac_init * _act_at_r

                    # Update peak from live price and compute MFE
                    if pos['action'] == "BUY":
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price > cur_peak:
                            pos['peak_price'] = price
                            cur_peak = price
                        _mfe = (cur_peak - entry_px) / entry_px
                    else:
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price < cur_peak or cur_peak == entry_px:
                            pos['peak_price'] = price
                            cur_peak = price
                        _mfe = (entry_px - cur_peak) / entry_px

                    if _mfe >= _ta:
                        if pos['action'] == "BUY":
                            new_sl = cur_peak * (1.0 - _td)
                            if new_sl > pos['sl']:
                                pos['sl'] = new_sl
                        else:
                            new_sl = cur_peak * (1.0 + _td)
                            if new_sl < pos['sl']:
                                pos['sl'] = new_sl

                    # ══ [LAYER 7] If SL moved, sync protective orders ══
                    if (getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True)
                            and abs(float(pos['sl']) - _sl_before) > 1e-12):
                        try:
                            _sync_protective_orders(exchange, sym, pos)
                        except Exception as _e:
                            log.debug(f"[Prot] {sym} sync error: {_e}")

                # ── [FIX 4] Partial TP ──
                if (not ex
                        and getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                        and not pos.get('_partial_taken', False)):
                    _entry_px_p = float(pos['entry'])
                    _sl_d0_p = float(pos.get('sl_dist_initial', 0) or 0)
                    if _sl_d0_p > 0 and _entry_px_p > 0:
                        _ptr = float(getattr(CFG, 'PARTIAL_TP_R', 1.0))
                        _pct = float(getattr(CFG, 'PARTIAL_TP_PCT', 0.5))
                        if pos['action'] == "BUY":
                            _trig_p = _entry_px_p + _sl_d0_p * _ptr
                            _hit_p = price >= _trig_p
                        else:
                            _trig_p = _entry_px_p - _sl_d0_p * _ptr
                            _hit_p = price <= _trig_p
                        if _hit_p:
                            _qty_close = float(pos['qty']) * _pct
                            try:
                                _s_p = 'sell' if pos['action'] == 'BUY' else 'buy'
                                _res_p = execute_post_only(
                                    exchange, sym, _s_p, _qty_close,
                                    max_wait_s=int(getattr(CFG, 'PO_EXIT_URGENT_WAIT_S', 4)),
                                    fallback_market=True,
                                    cross_spread=True,
                                    reduce_only=True,
                                )
                                if (_res_p.get('filled_qty') or 0) > 0:
                                    _filled_q = float(_res_p['filled_qty'])
                                    _avg_px = float(_res_p['avg_price'])
                                    # ══ [FIX] احسب ربح الجزء المُغلق ══
                                    # [FIX-10.2] subtract fees from partial
                                    if pos['action'] == "BUY":
                                        _partial_gross = (_avg_px - float(pos['entry'])) * _filled_q
                                    else:
                                        _partial_gross = (float(pos['entry']) - _avg_px) * _filled_q
                                    _partial_fee = (_filled_q * float(pos['entry']) * CFG.MAKER_FEE
                                                    + _filled_q * _avg_px * CFG.TAKER_FEE)
                                    _partial_net = _partial_gross - _partial_fee
                                    pos['_partial_pnl'] = float(pos.get('_partial_pnl', 0.0)) + _partial_net
                                    pos['qty'] = float(pos['qty']) - _filled_q
                                    pos['_partial_taken'] = True
                                                                        # [FIX-09-PROPER] invalidate — qty changed
                                    log.info(f"[PartialTP] {sym} closed "
                                             f"{_pct*100:.0f}% @ {_avg_px:.6f} "
                                             f"net=${_partial_net:+.4f} "
                                             f"remaining={pos['qty']:.6f}")
                                    # Persist state
                                    try:
                                        with open(state_file, 'w') as _f:
                                            json.dump(open_pos_live, _f,
                                                      indent=2, default=str)
                                    except Exception:
                                        pass
                            except Exception as _e:
                                log.warning(f"[PartialTP] {sym} failed: {_e}")

                # ── SL / TP ──
                if not ex:
                    if pos['action'] == "BUY":
                        if price <= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price >= pos.get('tp1', 1e18): ex = True; rsn = "Hard TP"
                    else:
                        if price >= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price <= pos.get('tp1', 0.): ex = True; rsn = "Hard TP"

                # ── [LAYER 5] LiqProximity with exchange-verified Liq ──
                if not ex and getattr(CFG, 'LIQ_EMERGENCY_ENABLED', True):
                    _entry_px = float(pos.get('entry') or 0)
                    _liq_px = pos.get('liq_price_estimated')

                    # Step 1: compute progress with current estimate
                    _progress = 0.0
                    if (_liq_px is not None and _liq_px > 0
                            and _entry_px > 0):
                        _gap = abs(_entry_px - float(_liq_px))
                        if _gap > 1e-12:
                            if pos['action'] == "BUY":
                                _progress = (_entry_px - price) / _gap
                            else:
                                _progress = (price - _entry_px) / _gap

                    # Step 2: if progress high, refresh Liq from exchange
                    _refresh_thr = float(getattr(CFG,
                        'LIQ_EMERGENCY_REFRESH_AT', 0.40))
                    _cooldown = int(getattr(CFG,
                        'LIQ_EMERGENCY_REFRESH_COOLDOWN_S', 30))
                    _now_ts = time.time()
                    _last_refresh = float(pos.get('_liq_last_refresh_ts', 0.0))

                    if (_progress > _refresh_thr
                            and (_now_ts - _last_refresh) > _cooldown):
                        try:
                            _rate_record(5.0)
                            _pos_list = _fake_pos_list(exchange, sym, force=True)
                            for _p in _pos_list:
                                _amt = float(_p['info'].get(
                                    'positionAmt', 0) or 0)
                                if abs(_amt) > 0:
                                    _exch_liq = float(_p['info'].get(
                                        'liquidationPrice', 0) or 0)
                                    if _exch_liq > 0:
                                        # Use whichever is closer to entry
                                        # (more conservative for our check)
                                        if pos['action'] == "BUY":
                                            _cand = max(float(_liq_px or 0),
                                                        _exch_liq)
                                        else:
                                            _cand = min(float(_liq_px or 1e18),
                                                        _exch_liq)
                                        pos['liq_price_estimated'] = _cand
                                        pos['_liq_source'] = 'exchange'
                                        _liq_px = _cand
                                        # Recompute progress with new Liq
                                        _g2 = abs(_entry_px - _cand)
                                        if _g2 > 1e-12:
                                            if pos['action'] == "BUY":
                                                _progress = ((_entry_px - price)
                                                             / _g2)
                                            else:
                                                _progress = ((price - _entry_px)
                                                             / _g2)
                                    break
                        except Exception as _e:
                            log.debug(f"[Liq5] {sym} exchange Liq fetch "
                                      f"failed: {_e}")
                        pos['_liq_last_refresh_ts'] = _now_ts

                    # Step 3: trigger emergency if threshold crossed
                    _thr = float(getattr(CFG, 'LIQ_EMERGENCY_PROGRESS', 0.7))
                    if _progress >= _thr:
                        ex = True
                        rsn = f"Emergency LiqProximity({_progress*100:.0f}%)"
                        _liq_source = pos.get('_liq_source', 'estimated')
                        log.warning(
                            f"[Liq5] {sym} EMERGENCY: progress={_progress*100:.0f}% "
                            f"entry={_entry_px:.6f} liq={float(_liq_px or 0):.6f} "
                            f"price={price:.6f} source={_liq_source}"
                        )
                        # Update warning counter
                        _LIQ_EMERGENCY_STATS['triggers'] += 1

                if not ex:

                    # ══ [FIX-no_fill] تحقق من وجود المركز على البورصة قبل الخروج ══
                    # السبب: عند فتح المركز، البوت يضع STOP_MARKET و
                    # TAKE_PROFIT_MARKET بـ closePosition=True. عندما يُنفَّذ
                    # أحدهما، تُغلق البورصة المركز تلقائياً. البوت يرى السعر
                    # قد لمس SL/TP، يحاول الإغلاق بـ reduceOnly=True، لكن
                    # المركز صفر → البورصة ترفض → no_fill متكرر لدقائق.
                    # الحل: قبل الإغلاق، اسأل البورصة عن وجود المركز.
                    try:
                        _exch_pos_qty = 0.0
                        _positions = _fake_pos_list(exchange, sym)
                        for _p in _positions:
                            _amt = float(_p['info'].get('positionAmt', 0) or 0)
                            if abs(_amt) > 0:
                                _exch_pos_qty = abs(_amt)
                                break

                        if _exch_pos_qty <= 0:
                            # ── المركز غير موجود على البورصة ──
                            # أُغلق بواسطة الأمر الواقي (أو يدوياً).
                            # احذفه محلياً دون إرسال أي أمر خروج.
                            _close_px = 0.0
                            if 'SL' in rsn or 'Emergency' in rsn:
                                _close_px = float(pos.get('sl') or 0)
                            elif 'TP' in rsn or 'Hard' in rsn:
                                _close_px = float(pos.get('tp1') or 0)
                            if _close_px <= 0:
                                try:
                                    _tk2 = exchange.fetch_ticker(sym)
                                    _close_px = float(_tk2.get('last') or 0)
                                except Exception:
                                    _close_px = float(pos.get('entry') or 0)

                            log.info(
                                f"[Exit-Cleanup] {sym} position already closed "
                                f"on exchange (protective order) — removing "
                                f"local. reason={rsn} px≈{_close_px:.6f}"
                            )
                            del open_pos_live[sym]
                            last_exit_time[sym] = time.time()

                            # نظّف أي أوامر واقية متبقية (دفاعي)
                            try:
                                _cancel_all_protective_orders(exchange, sym)
                            except Exception:
                                pass

                            # احفظ الحالة فوراً
                            try:
                                with open(state_file, 'w') as _f:
                                    json.dump(open_pos_live, _f,
                                              indent=2, default=str)
                            except Exception:
                                pass
                            continue

                        # ── المركز موجود على البورصة ──
                        # زامن الكمية إذا اختلفت (مثلاً partial fill سابق)
                        _local_qty = float(pos.get('qty') or 0)
                        if (_local_qty > 0
                                and abs(_exch_pos_qty - _local_qty) / _local_qty > 0.02):
                            log.info(
                                f"[Exit-Cleanup] {sym} qty sync: "
                                f"local={_local_qty:.6f} → "
                                f"exch={_exch_pos_qty:.6f}"
                            )
                            pos['qty'] = _exch_pos_qty

                    except Exception as _e:
                        # fail-safe: إذا فشل الفحص، نكمل بمحاولة الإغلاق
                        log.debug(
                            f"[Exit-Cleanup] {sym} position check failed: {_e}"
                        )

                    continue

                # ── Execute exit ──
                # ══ [ORDER-OF-OPERATIONS] Design principle ══
                # 1. Exit attempt FIRST (with reduceOnly=True internally)
                # 2. Only cancel protective orders AFTER exit confirms
                # 3. On failure: DO NOT touch protective orders
                # Reason: the exchange's closePosition=True auto-cancels the
                # protective bracket when the position closes. So we don't
                # need to cancel them ourselves. If the exit fails, the
                # protective orders remain and continue to protect.
                try:
                    s = 'sell' if pos['action'] == 'BUY' else 'buy'

                    _urgent = (
                        'Emergency' in rsn
                        or 'Hard TP' in rsn
                        or 'LiqProximity' in rsn
                    )

                    _exit_ok = False
                    exec_price = 0.0
                    exit_reason = ""

                    if 'Emergency LiqProximity' in rsn:
                        # Absolute last resort — market (Liq is imminent)
                        try:
                            # reduceOnly ensures no reverse-position risk
                            o = exchange.create_order(
                                sym, 'market', s, pos['qty'], None,
                                params={'reduceOnly': True},
                            )
                            v = verify_fill(exchange, o['id'], sym, timeout_s=1.5)
                            exec_price = v['avg_price'] if v and v['filled'] else price
                            exit_reason = f"{rsn} (market)"
                            _exit_ok = True
                        except Exception as e:
                            log.error(f"[Exit] market failed {sym}: {e}")
                    else:
                        _cross = bool(_urgent and
                                      getattr(CFG, 'PO_EXIT_URGENT_CROSS_SPREAD', True))
                        _wait = (
                            int(getattr(CFG, 'PO_EXIT_URGENT_WAIT_S', 4))
                            if _urgent
                            else int(CFG.PO_EXIT_MAX_WAIT_S)
                        )
                        result = execute_post_only(
                            exchange, sym, s, pos['qty'],
                            max_wait_s=_wait,
                            fallback_market=False,
                            cross_spread=_cross,
                            reduce_only=True,   # ← NEW param
                        )

                        if not result['filled_qty'] or result['filled_qty'] <= 0:
                            _reason_str = str(result.get('reason', ''))
                            # [FIX-7.7] If exchange rejected with -2022,
                            # the position was already closed by the
                            # broker-side STOP_MARKET. Treat as success.
                            try:
                                _pos_chk = _fake_pos_list(exchange, sym)
                                _exch_amt = 0.0
                                for _pp in _pos_chk:
                                    _amt_pp = float(_pp['info'].get(
                                        'positionAmt', 0) or 0)
                                    if abs(_amt_pp) > 0:
                                        _exch_amt = abs(_amt_pp)
                                        break
                                if _exch_amt <= 0:
                                    log.info(
                                        f"✅ [Exit] {sym} position already "
                                        f"closed on exchange (protective "
                                        f"order fired) — removing local"
                                    )
                                    try:
                                        _cancel_all_protective_orders(
                                            exchange, sym)
                                    except Exception:
                                        pass
                                    del open_pos_live[sym]
                                    last_exit_time[sym] = time.time()
                                    continue
                            except Exception as _e:
                                log.debug(f"[Exit] position check "
                                          f"failed {sym}: {_e}")

                            # [FIX-8.4] After 3 failed attempts, force market
                            _retry_cnt = int(pos.get('_exit_retry', 0)) + 1
                            pos['_exit_retry'] = _retry_cnt
                            _force_at = int(getattr(CFG, 'PO_MAX_FORCE_MARKET_ATTEMPTS', 3))
                            if _retry_cnt >= _force_at:
                                log.warning(
                                    f"[Exit] {sym} forcing MARKET after "
                                    f"{_retry_cnt} failed post-only attempts"
                                )
                                try:
                                    o = exchange.create_order(
                                        sym, 'market', s, pos['qty'], None,
                                        params={'reduceOnly': True},
                                    )
                                    v = verify_fill(exchange, o['id'], sym,
                                                    timeout_s=3.0)
                                    if v and v['filled']:
                                        exec_price = float(v.get('avg_price')
                                                          or price)
                                        exit_reason = f"{rsn} (forced-market)"
                                        _exit_ok = True
                                        # Fall through to cleanup below
                                except Exception as _em:
                                    log.error(f"[Exit] forced market "
                                              f"failed {sym}: {_em}")

                            if not _exit_ok:
                                log.warning(
                                    f"⚠️ [Exit] {sym} no fill "
                                    f"({result['reason']}) — attempt "
                                    f"{_retry_cnt}/3"
                                )
                                continue
                        exec_price = result['avg_price']
                        exit_reason = f"{rsn} ({result['reason']})"
                        _exit_ok = True

                    if not _exit_ok:
                        continue

                    # ══ Position now closed. Clean any leftover protective
                    # orders. With closePosition=True, Binance auto-cancels
                    # them; this is defensive for edge cases (partial fills,
                    # exchange lag). ══
                    try:
                        _leftovers = _cancel_all_protective_orders(exchange, sym)
                        if _leftovers > 0:
                            log.debug(f"[Prot] {sym} cleaned "
                                      f"{_leftovers} leftover order(s)")
                    except Exception as _e:
                        log.debug(f"[Prot] {sym} post-exit cleanup: {_e}")

                    # ══ [TradeLog] سجّل الصفقة قبل الحذف ══
                    try:
                        # [FIX-10.1] احسب net_pnl مع الرسوم
                        _entry_px_lg = float(pos.get('entry') or 0)
                        _exit_px_lg  = float(exec_price or 0)
                        _qty_lg      = float(pos.get('qty') or 0)
                        _partial_lg  = float(pos.get('_partial_pnl', 0.0))
                        if pos.get('action') == 'BUY':
                            _gross_lg = (_exit_px_lg - _entry_px_lg) * _qty_lg
                        else:
                            _gross_lg = (_entry_px_lg - _exit_px_lg) * _qty_lg
                        # [FIX-10b] Entry is always maker (GTX).
                        # Exit fee depends on reason:
                        #   SL / TP / LiqProximity → taker
                        #   Apex / Topo / MaxHold / EndOfData → maker
                        _entry_fee_lg = _qty_lg * _entry_px_lg * CFG.MAKER_FEE
                        _is_taker_exit = _exit_is_taker(exit_reason)
                        _exit_fee_rate = (CFG.TAKER_FEE
                                          if _is_taker_exit
                                          else CFG.MAKER_FEE)
                        _exit_fee_lg = _qty_lg * _exit_px_lg * _exit_fee_rate
                        # Funding (best-effort estimate)
                        _hold_s_lg = time.time() - float(pos.get('entry_ts') or time.time())
                        _fund_pays_lg = max(0, int(_hold_s_lg // 28800))  # 8h
                        _funding_lg = _qty_lg * _entry_px_lg * CFG.FUNDING_RATE_COST * _fund_pays_lg
                        _net_pnl_lg = (_gross_lg - _entry_fee_lg - _exit_fee_lg
                                        - _funding_lg + _partial_lg)
                        _trade_log_from_live(
                            pos, exec_price, exit_reason,
                            ad=assets.get(sym),
                            net_pnl=float(_net_pnl_lg),
                        )
                    except Exception as _tle:
                        log.debug(f"[TradeLog] live hook failed: {_tle}")

                    # [FIX-11b] Removed redundant cleanup — the
                    # post-exit protective cancel above already handles
                    # this via closePosition=True auto-cancel + the
                    # _cancel_all_protective_orders defensive sweep.
                    # ══ [MFAL] Record trade outcome ══
                    try:
                        _entry_px_m = float(pos.get('entry') or 0)
                        _sl_d0_m = float(pos.get('sl_dist_initial') or 0)
                        if _entry_px_m > 0 and _sl_d0_m > 0:
                            _exit_px_m = float(exec_price or 0)
                            if pos.get('action') == 'BUY':
                                _pnl_frac_m = (_exit_px_m - _entry_px_m) / _entry_px_m
                            else:
                                _pnl_frac_m = (_entry_px_m - _exit_px_m) / _entry_px_m
                            _sl_frac_m = _sl_d0_m / _entry_px_m
                            _R_m = _pnl_frac_m / _sl_frac_m if _sl_frac_m > 0 else 0.0
                            _sig_m = None
                            try:
                                _sig_m = getattr(pos, 'signal', None)
                            except Exception:
                                pass
                            if _sig_m is None:
                                _sig_m = pos.get('_sig_ref') if isinstance(pos, dict) else None
                            if _sig_m is None:
                                _sig_m = pos if isinstance(pos, dict) else None
                            _mfal_record_trade(_sig_m, float(_R_m), _R_m > 0.5)
                    except Exception as _me:
                        log.debug(f"[MFAL] record failed: {_me}")

                    # ══ [UNIFIED] Record live trade outcome ══
                    if _UNIFIED_ENABLED:
                        try:
                            _entry_px_u = float(pos.get('entry') or 0)
                            _sl_d0_u = float(pos.get('sl_dist_initial') or 0)
                            _exit_px_u = float(exec_price or 0)
                            if (_entry_px_u > 0 and _sl_d0_u > 0
                                    and _exit_px_u > 0):
                                if pos.get('action') == 'BUY':
                                    _pnl_frac_u = (_exit_px_u - _entry_px_u) / _entry_px_u
                                else:
                                    _pnl_frac_u = (_entry_px_u - _exit_px_u) / _entry_px_u
                                _sl_frac_u = _sl_d0_u / _entry_px_u
                                _R_u = _pnl_frac_u / _sl_frac_u if _sl_frac_u > 0 else 0.0
                                _sig_u = pos.get('_sig_ref') if isinstance(pos, dict) else None
                                _ad_u = assets.get(sym) if 'assets' in dir() else None
                                _unified_record_trade(_sig_u, _ad_u, float(_R_u), _R_u > 0.5)
                        except Exception as _re:
                            log.debug(f"[Unified] record failed: {_re}")

                    del open_pos_live[sym]
                    last_exit_time[sym] = time.time()
                    log.info(f"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]")
                    # [FIX-09-PROPER] invalidate — position just closed
                    _invalidate_position_cache()
                except Exception as e:
                    log.error(f"خطأ أثناء الإغلاق لـ {sym}: {e}")

            # ══ [OppTP] Always-on: adapt existing positions' TP ══
            # يُستدعى حتى لو كان open_pos_live ممتلئًا، لأن الهدف
            # هو إدارة المراكز القائمة لا فتح جديدة.
            if (getattr(CFG, 'OPP_TP_ENABLED', False)
                    and open_pos_live
                    and 'assets' in dir()
                    and assets):
                try:
                    _opp_sigs = deduplicate_signals(
                        build_signals(assets, mode=cfg.mode)
                    )
                    for _sig_o in _opp_sigs:
                        if _sig_o.symbol not in open_pos_live:
                            continue
                        _pos_o = open_pos_live[_sig_o.symbol]
                        if _pos_o.get('action') == _sig_o.action:
                            continue
                        _ad_o = assets.get(_sig_o.symbol)
                        if _ad_o is None:
                            continue
                        _maybe_adapt_tp_live(
                            _pos_o, _sig_o, _ad_o, exchange
                        )
                except Exception as _e:
                    log.debug(f"[OppTP] cycle hook error: {_e}")

            # 2. اقتناص ودخول صفقات جديدة
            # ══ [SAFETY-FIX] Continuous concurrency scaling + recovery floor ══
            # السبب: العتبات الثابتة السابقة (0.05/0.10) أنشأت حلقة مغلقة:
            # عند dd>10% تصبح effective_max=2. إذا كان مركزان مفتوحان،
            # لا يُستدعى build_signals → لا إشارات جديدة → لا تعافٍ.
            #
            # المنهجية الجديدة:
            #   1. تحويل العتبات الحادة إلى منحنى متصل.
            #   2. ضمان أنه إذا كان n_open < MAX، يبقى هناك دائماً
            #      مقعد واحد متاح على الأقل (للتعافي التدريجي).
            _n_open = len(open_pos_live)
            dd_live = (peak_cap_live - cap_live) / (peak_cap_live + 1e-12)

            # منحنى متصل: 1.0 عند dd≤5% → 0.20 عند dd≥50%
            if dd_live <= 0.05:
                _soft_scale = 1.0
            else:
                _soft_scale = 1.0 - (dd_live - 0.05) * (0.80 / 0.45)
                _soft_scale = max(0.20, min(1.0, _soft_scale))

            _soft_cap = int(cfg.MAX_CONCURRENT_ASSETS * _soft_scale + 0.5)
            _soft_cap = max(2, _soft_cap)   # أدنى ناعم: مقعدان

            # ══ ضمان فتحة تعافٍ واحدة على الأقل ══
            # إذا كان n_open < MAX، يبقى دائماً مقعد واحد متاح على الأقل،
            # بغض النظر عن شدة الـ drawdown.
            effective_max = min(
                cfg.MAX_CONCURRENT_ASSETS,
                max(_soft_cap, _n_open + 1)
            )

            # سجل تشخيص كل 5 دقائق (لمعرفة السبب فوراً في المرة القادمة)
            _now_ts_eff = time.time()
            if _now_ts_eff - getattr(run_live, '_last_eff_max_log', 0.0) > 300:
                run_live._last_eff_max_log = _now_ts_eff
                log.info(
                    f"[Concurrency] dd={dd_live*100:.1f}% "
                    f"cap=${cap_live:.2f} peak=${peak_cap_live:.2f} "
                    f"n_open={_n_open} soft_cap={_soft_cap} "
                    f"effective_max={effective_max}"
                )

            if len(open_pos_live) < effective_max:
                # توليد الإشارة يمرر وضعية التداول اللحظية لكسر وهم الزمن
                # [Filter] إعادة التعيين في كل دورة live (عدّاد دوري)
                _filter_reset_stats()
                sigs = deduplicate_signals(build_signals(assets, mode=cfg.mode))

                # ══ [Rule Filter — Live] ══
                if CFG.RULE_FILTER_ENABLED:
                    if not _RULE_THRESHOLDS:
                        compute_rule_thresholds(assets)
                    sigs = filter_signals_rules(sigs, assets)

                # ══ [ML Filter — Live] ══
                if CFG.ML_FILTER_ENABLED:
                    sigs = filter_signals_ml_live(sigs, assets)
                    log_ml_live_stats()

                # ══ [OppTP] Adapt open positions' TP to opposite signals ══
                # يعمل على open_pos_live فقط. لا يتفاعل مع _WATCHED_SIGNALS
                # ولا مع _PENDING_ORDERS — لأن OPP-TP مفهوم يخص المراكز
                # الفعلية، لا الإشارات المُراقبة أو الأوامر المعلّقة.
                if getattr(CFG, 'OPP_TP_ENABLED', False) and open_pos_live:
                    for _sig_o in sigs:
                        if _sig_o.symbol not in open_pos_live:
                            continue
                        _pos_o = open_pos_live[_sig_o.symbol]
                        if _pos_o.get('action') == _sig_o.action:
                            continue
                        _ad_o = assets.get(_sig_o.symbol)
                        if _ad_o is None:
                            continue
                        _maybe_adapt_tp_live(_pos_o, _sig_o, _ad_o, exchange)

                for sig in reversed(sigs):
                    sym = sig.symbol
                    if sym in open_pos_live: continue

                    # ══ [EARLY-SKIP] قبل أي حساب فيزيائي ══
                    # هذا الفحص يمنع تكرار LevCap / SL-Clip / setup في كل دورة.
                    # بعد الدورة الأولى، الرمز يكون في إحدى هذه الحالات
                    # فنتخطاه فوراً بدون أي API call.
                    if sym in _WATCHED_SIGNALS:
                        log.debug(f"[Watch] {sym} already watched — skip")
                        continue
                    if sym in _PENDING_ORDERS:
                        log.debug(f"[Pending] {sym} already has active "
                                  f"pending — skip signal")
                        continue

                    # احتساب التعرّض الإجمالي (مراكز + معلّقات + مُراقَبة)
                    _total_exposure = (len(open_pos_live)
                                       + len(_PENDING_ORDERS)
                                       + len(_WATCHED_SIGNALS))
                    if _total_exposure >= int(cfg.MAX_CONCURRENT_ASSETS):
                        log.debug(f"[Watch] exposure cap reached "
                                  f"({_total_exposure}≥"
                                  f"{cfg.MAX_CONCURRENT_ASSETS}) — "
                                  f"stopping scan")
                        break

                    # ══ [RE-ENTRY COOLDOWN] Block re-entry too soon after exit ══
                    if CFG.REENTRY_COOLDOWN_ENABLED:
                        _last_t = last_exit_time.get(sym, -1e18)
                        _tf_sec_cd = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                        _cd_secs = CFG.REENTRY_COOLDOWN_BARS * _tf_sec_cd
                        _elapsed = time.time() - _last_t
                        if _elapsed < _cd_secs:
                            log.debug(f"[Cooldown] {sym} blocked "
                                      f"({_elapsed:.0f}s < {_cd_secs}s)")
                            continue
                    
                    # ══ [SAFETY] Adaptive correlation threshold ══
                    n_open = len(open_pos_live)
                    # أكثر مراكز → عتبة ارتباط أصرم
                    corr_thresh = cfg.CORRELATION_THRESHOLD * (0.85 ** n_open)
                    if any(abs(corr_cache.get((sym, s), 0.0)) > corr_thresh
                           for s in open_pos_live):
                        log.debug(f"[CorrGuard] {sym} rejected "
                                  f"(threshold={corr_thresh:.3f})")
                        continue
                        
                    ad = assets[sym]
                    
                    lmt = sig.price 
                    delta = abs(lmt - sig.sl)
                    if delta < 1e-8: continue
                    if cap_live <= cfg.CAPITAL_FLOOR + 0.1: continue

                    # ══ [SR FILTER — Live] ══
                    _live_ci = max(0, len(ad.closes) - 2)
                    _sr_ok, _sr_reason = _sr_filter_check(sig, ad, _live_ci)
                    if not _sr_ok:
                        log.info(f"[SR] {sym} rejected: {_sr_reason}")
                        continue
                    
                    # ══ [UNIFIED] Compute decision ══
                    _u_decision = None
                    if _UNIFIED_ENABLED:
                        try:
                            _u_decision = compute_unified_decision(
                                sym=sym, sig=sig, capital=cap_live,
                                peak=peak_cap_live,
                                open_pos_live=open_pos_live,
                                corr_cache=corr_cache,
                                exchange=exchange,
                                ad=assets.get(sym), cfg=cfg,
                            )
                        except Exception as _ue:
                            log.warning(f"[Unified] {sym} error: {_ue}")
                            _u_decision = None
                        if _u_decision is not None and not _u_decision["accept"]:
                            log.debug(f"[Unified] {sym} rejected: {_u_decision['reason']}")
                            continue
                    
                    # ══ [SAFETY] Drawdown-aware risk reduction ══
                    # نحتاج peak_cap — نضيفه كمتغير خارجي
                    if 'peak_cap_live' not in dir():
                        pass  # placeholder
                    dd_live = (peak_cap_live - cap_live) / (peak_cap_live + 1e-12)
                    dd_mult = _get_risk_multiplier(dd_live)

                    # ══ [PORTFOLIO RISK BUDGET] ══
                    free_ratio_live = max(0.0, (cap_live - cfg.CAPITAL_FLOOR) / cap_live)
                    power_law_scale = np.sqrt(free_ratio_live)

                    # Note: build open_pos_for_budget from live positions
                    # Since live dict is different from OpenPosition objects,
                    # we wrap them in a lightweight namespace for the helper.
                    _open_for_budget = {}
                    for _sym, _p in open_pos_live.items():
                        try:
                            _open_for_budget[_sym] = type('P', (), {
                                'signal': type('S', (), {
                                    'dynamic_risk': float(_p.get('dyn_risk', 0.01))
                                })()
                            })()
                        except Exception:
                            pass

                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)
                    if risk_frac <= 0.0:
                        # [UNIFIED] override risk_frac if unified accepts
                        if _u_decision is not None and _u_decision.get("accept"):
                            risk_frac = float(_u_decision["f_actual"])
                        else:
                            log.debug(f"[Budget] {sym} skipped: no heat budget")
                            continue

                    # ══ [SING-TIMING Layer 3B] Resonance Risk Boost ══
                    # الغرض: رفع المخاطرة × N عندما تكون الإشارة في
                    # حالة رنين ACTIVE (أقوى إشارة ممكنة). هذا يستغل
                    # الـ Singularity لزيادة حجم المركز على أفضل الفرص.
                    # تعمل فقط إذا SING_RISK_BOOST_ENABLED=True.
                    if (getattr(CFG, 'SING_RISK_BOOST_ENABLED', False)
                            and getattr(CFG, 'SING_TIMING_ENABLED', False)):
                        try:
                            _cur_ci_rb = max(0, len(ad.closes) - 2)
                            _cur_fi_rb = _cur_ci_rb - ad.feat_start
                            if 0 <= _cur_fi_rb < len(ad.geodesic_accel):
                                _rb_state, _rb_rho = \
                                    _resonance_state_for_direction(
                                        ad, int(_cur_fi_rb),
                                        sig.action, CFG
                                    )
                                _boost = 1.0
                                if _rb_state == "ACTIVE":
                                    _boost = float(getattr(
                                        CFG, 'SING_RISK_BOOST_ACTIVE', 1.20
                                    ))
                                elif _rb_state == "EMERGING":
                                    _boost = float(getattr(
                                        CFG, 'SING_RISK_BOOST_EMERGING', 1.00
                                    ))
                                if _boost != 1.0:
                                    risk_frac *= _boost
                                    log.info(
                                        f"[Sing-Timing-L3B] {sym} "
                                        f"{sig.action} {_rb_state} "
                                        f"(rho={_rb_rho:+.3f}) — risk "
                                        f"boost ×{_boost:.2f}"
                                    )
                        except Exception as _e:
                            log.debug(
                                f"[Sing-Timing-L3B] boost failed: {_e}"
                            )

                    risk_frac *= power_law_scale
                    risk_frac = float(np.clip(risk_frac,
                                                CFG.MIN_RISK_PER_TRADE if CFG.BUDGET_ENABLED else CFG.MIN_RISK,
                                                CFG.MAX_RISK_PER_TRADE if CFG.BUDGET_ENABLED else CFG.MAX_RISK))

                    equity_base = max(cap_live - cfg.CAPITAL_FLOOR, 0.0)
                    risk_amt = equity_base * risk_frac

                    qty_risk_based = risk_amt / delta

                    # ══ [MFAL] Adaptive leverage ══
                    dynamic_leverage = compute_adaptive_leverage(
                        symbol=sym,
                        sig=sig,
                        open_pos_live=open_pos_live,
                        capital=cap_live,
                        peak_capital=peak_cap_live,
                        corr_cache=corr_cache,
                        exchange=exchange,
                        cfg=cfg,
                    )

                    # ══ [LIQ-CAP] Cap leverage so SL is safely inside Liq ══
                    _mmr_sig = None
                    if getattr(CFG, 'LIQ_ENABLED', True):
                        _mmr_sig = _get_mmr_for_symbol(exchange, sym)
                        # Keep this in sync with SL_WIDEN_MULT so LevCap
                        # accounts for the wider actual SL.
                        _sl_frac_max = 0.015 * float(
                            getattr(CFG, 'SL_WIDEN_MULT', 1.0)
                        )
                        _lev_by_liq = compute_max_leverage_by_liq(
                            sl_frac_max=_sl_frac_max,
                            mmr=_mmr_sig,
                            safety_mult=float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5)),
                            symbol=sym,
                        )
                        if dynamic_leverage > _lev_by_liq:
                            log.info(
                                f"[LevCap] {sym} capping "
                                f"{dynamic_leverage}x → {_lev_by_liq}x "
                                f"(MMR={_mmr_sig*100:.3f}%)"
                            )
                            dynamic_leverage = max(
                                int(cfg.LEVERAGE_MIN), _lev_by_liq
                            )

                    if dynamic_leverage < int(cfg.LEVERAGE_MIN):
                        log.info(
                            f"[LevCap] {sym} leverage {dynamic_leverage}x "
                            f"< LEVERAGE_MIN={cfg.LEVERAGE_MIN}x — skip signal"
                        )
                        continue

                    max_notional = cap_live * dynamic_leverage
                    qty_leverage_based = max_notional / lmt

                    qty = min(qty_risk_based, qty_leverage_based)

                    # ══ [NOTIONAL CAP] ══
                    qty = cap_notional(qty, lmt)

                    # ══ [UNIFIED] Apply qty/leverage/risk override ══
                    if _u_decision is not None and _u_decision.get("accept"):
                        qty = float(_u_decision["qty"])
                        dynamic_leverage = int(_u_decision["leverage"])
                        risk_frac = float(_u_decision["f_actual"])

                    if qty * lmt < cfg.MIN_NOTIONAL:
                        continue

                    # Store effective risk for heat tracking
                    sig.dynamic_risk = float(risk_frac)

                    # ══ [WATCH-REGISTRATION-EARLY] ══
                    # التسجيل يحدث قبل STEP 1/STEP 2/Entry.
                    # السبب: STEP 1 قد يفشل (fetch_positions glitch) ويُخرجنا
                    # من الحلقة قبل التسجيل → إعادة معالجة كاملة كل دورة.
                    # التسجيل المبكّر يضمن التقاط الإشارة من أول مرة.
                    if ((not WATCH_REMOVED) and getattr(CFG, 'WATCH_MODE_ENABLED', False)
                            and getattr(CFG, 'PENDING_ENABLED', True)):
                        _ad_w = assets.get(sym)
                        if _ad_w is None:
                            continue
                        if register_watch_signal(sym, sig, _ad_w):
                            _WATCHED_SIGNALS[sym]['qty'] = float(qty)
                            _WATCHED_SIGNALS[sym]['leverage'] = int(
                                dynamic_leverage
                            )
                            _WATCHED_SIGNALS[sym]['mmr'] = float(
                                _mmr_sig or
                                getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02)
                            )
                            save_watched_signals()
                        continue

                    try:
                        sd = 'buy' if sig.action == 'BUY' else 'sell'

                        # ══════════════════════════════════════════════════
                        # STEP 1 — PRE-SETUP CLEANUP (runs BEFORE set_leverage)
                        # ══════════════════════════════════════════════════
                        # Ordering matters:
                        #   set_leverage can fail with -4046 if the exchange
                        #   sees an orphan position OR a protective bracket
                        #   from a prior session. Cleaning first removes that
                        #   risk, so setup is guaranteed a clean symbol.
                        #
                        # Safety:
                        #   - Verify no exchange-side position exists before
                        #     cancelling protective orders. If an orphan
                        #     position IS found → skip entry entirely and let
                        #     reconcile adopt it next cycle.
                        #   - On fetch failure, assume position exists
                        #     (fail-safe, not fail-open).
                        _has_exch_pos = False
                        try:
                            _rate_record(5.0)
                            for _p in _fake_pos_list(exchange, sym):
                                _amt = float(
                                    _p['info'].get('positionAmt', 0) or 0
                                )
                                if abs(_amt) > 0:
                                    _has_exch_pos = True
                                    break
                        except Exception as _e:
                            log.debug(f"[Entry-Cleanup] {sym} position "
                                      f"check failed: {_e}")
                            _has_exch_pos = True

                        if _has_exch_pos:
                            log.warning(
                                f"[Entry-Cleanup] {sym} exchange has an "
                                f"open position not in local state — "
                                f"skipping entry. Next reconcile will "
                                f"adopt it."
                            )
                            continue

                        # No position → all orders on this symbol are stale.
                        try:
                            _cancelled_entries = 0
                            _cancelled_prot = 0
                            for o in exchange.fetch_open_orders(sym):
                                _is_prot = _is_protective_order(o)
                                _is_same_entry = (
                                    (not _is_prot)
                                    and o.get('side') == sd
                                )
                                if not (_is_prot or _is_same_entry):
                                    continue
                                try:
                                    exchange.cancel_order(o['id'], sym)
                                    if _is_prot:
                                        _cancelled_prot += 1
                                        log.info(
                                            f"[Entry-Cleanup] {sym} "
                                            f"cancelled stale "
                                            f"{o.get('type','?')} "
                                            f"id={o['id']} "
                                            f"trigger="
                                            f"{o.get('stopPrice') or o.get('price')}"
                                        )
                                    else:
                                        _cancelled_entries += 1
                                        log.debug(
                                            f"[Entry-Cleanup] {sym} "
                                            f"cancelled same-side entry "
                                            f"id={o['id']}"
                                        )
                                except Exception as _e:
                                    log.warning(
                                        f"[Entry-Cleanup] {sym} cancel "
                                        f"{o['id']} failed: {_e}"
                                    )
                            if _cancelled_prot > 0 or _cancelled_entries > 0:
                                log.info(
                                    f"[Entry-Cleanup] {sym} removed "
                                    f"{_cancelled_entries} entry + "
                                    f"{_cancelled_prot} protective "
                                    f"order(s) before new entry"
                                )
                                time.sleep(0.2)
                        except Exception as _e:
                            log.warning(
                                f"[Entry-Cleanup] {sym} "
                                f"fetch_open_orders failed: {_e}"
                            )

                        # ══════════════════════════════════════════════════
                        # STEP 2 — LEVERAGE / MARGIN SETUP (clean symbol now)
                        # ══════════════════════════════════════════════════
                        if not ensure_symbol_setup(exchange, sym, dynamic_leverage,
                                                    margin_mode='isolated'):
                            log.warning(f"[Entry] {sym} setup failed — skip")
                            continue

                        # ══ [SL-CLIP-LIVE] قصّ SL ليطابق الباكتيست ══
                        # الباكتيست يقصّ SL إلى max_sl_frac قبل LiqGate.
                        # اللايف يفعل نفس الشيء. فحص LiqGate يتم في STEP 3
                        # بعد هذا القص (الترتيب مقصود: قصّ أولاً، ثم فحص).
                        _max_sl_frac_live = 0.015 * float(
                            getattr(CFG, 'SL_WIDEN_MULT', 1.0)
                        )
                        _sl_dist_now = abs(float(sig.price) - float(sig.sl))
                        if _sl_dist_now > float(sig.price) * _max_sl_frac_live:
                            _tp_dist_now = abs(float(sig.tp1) - float(sig.price))
                            _rr_now = (_tp_dist_now / max(_sl_dist_now, 1e-12))
                            _new_sl_dist = float(sig.price) * _max_sl_frac_live
                            _new_tp_dist = _new_sl_dist * _rr_now
                            if sig.action == "BUY":
                                sig.sl = float(sig.price) - _new_sl_dist
                                sig.tp1 = float(sig.price) + _new_tp_dist
                            else:
                                sig.sl = float(sig.price) + _new_sl_dist
                                sig.tp1 = float(sig.price) - _new_tp_dist
                            log.info(
                                f"[SL-Clip-Live] {sym} SL clipped "
                                f"{_sl_dist_now:.6f} → {_new_sl_dist:.6f} "
                                f"({_max_sl_frac_live*100:.1f}% cap)"
                            )

                        # ══ 3. Entry — Watch mode (or legacy pending) ══
                        if getattr(CFG, 'PENDING_ENABLED', True):
                            _total_exposure = (len(_PENDING_ORDERS)
                                               + len(open_pos_live)
                                               + len(_WATCHED_SIGNALS))
                            if _total_exposure >= int(CFG.MAX_CONCURRENT_ASSETS):
                                log.debug(
                                    f"[Watch] exposure cap "
                                    f"({_total_exposure}≥"
                                    f"{CFG.MAX_CONCURRENT_ASSETS}) "
                                    f"— skip {sym}"
                                )
                                continue

                            # ══ [WATCH-THEN-TRIGGER] ══
                            if (not WATCH_REMOVED) and getattr(CFG, 'WATCH_MODE_ENABLED', False):
                                _ok = register_watch_signal(
                                    sym, sig, assets[sym]
                                )
                                if _ok:
                                    _WATCHED_SIGNALS[sym]['qty'] = float(qty)
                                    _WATCHED_SIGNALS[sym]['leverage'] = int(dynamic_leverage)
                                    _WATCHED_SIGNALS[sym]['mmr'] = float(
                                        _mmr_sig or
                                        getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02)
                                    )
                                    save_watched_signals()
                                continue

                            # ── Legacy immediate placement ──
                            _tf_sec_w = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                            _bars_wait = int(effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS))
                            _timeout_s = float(_bars_wait * _tf_sec_w)
                            _cap = float(getattr(CFG, 'PO_MAX_WAIT_S', 0))
                            if _cap > 0:
                                _timeout_s = min(_timeout_s, _cap)

                            rec = place_pending_entry(
                                exchange, sym, sd, qty, sig,
                                timeout_s=_timeout_s,
                                leverage=int(dynamic_leverage),
                                ad=assets[sym],
                            )
                            if rec is None:
                                log.info(f"[Pending] {sym} rejected — skip")
                                continue
                            try:
                                save_pending_orders()
                            except Exception:
                                pass
                            continue
                        else:
                            # Legacy blocking path (fallback)
                            _fixed_target = None
                            if getattr(CFG, 'PO_FIXED_PRICE', True):
                                _fixed_target = float(sig.price)
                            result = execute_post_only(
                                exchange, sym, sd, qty,
                                fallback_market=False,
                                fixed_target=_fixed_target,
                            )
                            if not result.get('filled_qty') or result['filled_qty'] <= 0:
                                continue

                        entry_price = result['avg_price']
                        actual_qty = result['filled_qty']
                        fill_ratio = result['fill_ratio']

                        # ══ [ATOMIC] Reject too-small partial fills ══
                        _min_accept = float(getattr(CFG, 'PO_MIN_ACCEPT_RATIO', 0.50))
                        if fill_ratio < _min_accept:
                            log.warning(
                                f"[PostOnly] {sym} rejecting partial "
                                f"{fill_ratio*100:.1f}% < {_min_accept*100:.0f}% "
                                f"(qty={actual_qty:.6f})"
                            )
                            # Close the tiny partial position
                            try:
                                _s_close = 'sell' if sig.action == 'BUY' else 'buy'
                                exchange.create_order(sym, 'market', _s_close, actual_qty)
                                log.info(f"[PostOnly] closed tiny partial {sym}")
                            except Exception as _e:
                                log.error(f"[PostOnly] failed to close partial: {_e}")
                            continue

                        # ══ 4. Verify fill via fetch_order (safety) ══
                        if entry_price <= 0:
                            log.warning(f"[Entry] {sym} fill reported but price=0 — closing")
                            try:
                                s_close = 'sell' if sig.action == 'BUY' else 'buy'
                                exchange.create_order(sym, 'market', s_close, actual_qty)
                            except Exception:
                                pass
                            continue

                        # ══ 5. Adapt SL/TP to actual fill ══
                        orig_sl_dist = abs(sig.price - sig.sl)
                        orig_tp_dist = abs(sig.tp1 - sig.price)
                        if orig_sl_dist <= 1e-12:
                            log.warning(f"[Entry] {sym} invalid SL dist — closing")
                            try:
                                s_close = 'sell' if sig.action == 'BUY' else 'buy'
                                exchange.create_order(sym, 'market', s_close, actual_qty)
                            except Exception:
                                pass
                            continue

                        rr_ratio = orig_tp_dist / orig_sl_dist
                        # [SL-CLIP-CONSISTENCY] Scale with SL_WIDEN_MULT
                        # so the widened SL isn't re-clipped back to 1.5%.
                        max_sl_frac = 0.015 * float(
                            getattr(CFG, 'SL_WIDEN_MULT', 1.0)
                        )
                        if orig_sl_dist > entry_price * max_sl_frac:
                            orig_sl_dist = entry_price * max_sl_frac
                            orig_tp_dist = orig_sl_dist * rr_ratio

                        if sig.action == "BUY":
                            adapted_sl = entry_price - orig_sl_dist
                            adapted_tp = entry_price + orig_tp_dist
                        else:
                            adapted_sl = entry_price + orig_sl_dist
                            adapted_tp = entry_price - orig_tp_dist

                        # ══ [DYNAMIC TRAIL] compute σ-scaled params at entry ══
                        entry_fi = max(0, min(sig.feat_idx,
                                              len(assets[sym].E_therm) - 1))
                        trail_d, trail_a = compute_trail_params(assets[sym], entry_fi)

                        # ══ 6. Register position ══
                        _lev_reg = int(_SYMBOL_META.get(sym, {}).get('leverage',
                                                                       dynamic_leverage))
                        _mmr_reg = float(_mmr_sig or
                                          getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
                        _liq_est = None
                        if getattr(CFG, 'LIQ_ENABLED', True):
                            _liq_est = compute_liquidation_price(
                                entry_price, sig.action, _lev_reg, _mmr_reg
                            )
                        open_pos_live[sym] = {
                            'action': sig.action,
                            'entry': entry_price,
                            'qty': actual_qty,
                            'sl': adapted_sl,
                            'tp1': adapted_tp,
                            'T_info': sig.T_info_val,
                            'dyn_risk': sig.dynamic_risk,
                            'entry_ts': time.time(),
                            'fill_ratio': fill_ratio,
                            'leverage': _lev_reg,
                            'trail_dist_frac': trail_d,
                            'trail_activate_frac': trail_a,
                            'liq_price_estimated': _liq_est,
                            'mmr': _mmr_reg,
                            'sl_dist_initial': float(abs(entry_price - adapted_sl)),
                            '_entry_ci': int(sig.close_idx),
                            '_trail_bars_held': 0,
                            '_trail_peak_R': 0.0,
                            '_trail_last_update_ts': 0.0,
                            '_sym': sym,
                            '_orig_score': float(sig.score),
                            '_sig_ref': sig,
                        }

                                                # [FIX-09-PROPER] invalidate — position just opened
                        _invalidate_position_cache()
                        log.info(f"✅ [Entry] {sig.action} {sym} @ {entry_price:.6f} "
                                 f"qty={actual_qty:.6f} (fill={fill_ratio*100:.1f}%) "
                                 f"sl={adapted_sl:.6f} tp={adapted_tp:.6f} "
                                 f"lev={_SYMBOL_META.get(sym, {}).get('leverage', '?')}x")

                        # ══ 7. Persist immediately ══
                        try:
                            with open(state_file, 'w') as f:
                                json.dump(open_pos_live, f, indent=2)
                        except Exception as e:
                            log.warning(f"[State] save after entry {sym} "
                                        f"failed: {e}")

                    except Exception as e:
                        log.error(f"[Entry] {sym} exception: {e}")

            # ══ Periodic reconcile ══
            # [PERF-FIX] 1) Init to NOW (not 0.0) — skip on first loop
            #            2) Only held/pending symbols (not all 50)
            if not hasattr(run_live, '_last_reconcile'):
                run_live._last_reconcile = time.time()
            _recon_syms = list(set(open_pos_live.keys())
                               | set(_PENDING_ORDERS.keys()))
            if (_recon_syms
                    and time.time() - run_live._last_reconcile
                        > CFG.RECONCILE_INTERVAL_S):
                _before = set(open_pos_live.keys())
                try:
                    open_pos_live = reconcile_state_machine(
                        exchange, open_pos_live, _recon_syms
                    )
                except Exception as _e:
                    log.warning(f"[Reconcile] state machine failed: {_e}")
                _after = set(open_pos_live.keys())
                # [FIX-72] Ensure newly adopted positions have protective orders
                _newly_adopted = _after - _before
                for _sym_na in _newly_adopted:
                    try:
                        _place_protective_orders(exchange, _sym_na,
                                                 open_pos_live[_sym_na])
                        log.info(f"[Reconcile] protective orders placed "
                                 f"for adopted {_sym_na}")
                    except Exception as _e:
                        log.warning(f"[Reconcile] protective placement "
                                    f"for {_sym_na} failed: {_e}")
                run_live._last_reconcile = time.time()

            # ══ [LAYER 5] Warn if LiqProximity triggers too often ══
            _warn_at = int(getattr(CFG, 'LIQ_EMERGENCY_WARN_AT', 5))
            _trig = _LIQ_EMERGENCY_STATS['triggers']
            if (_trig >= _warn_at
                    and time.time() - _LIQ_EMERGENCY_STATS['last_warned_at']
                        > 600):
                log.warning(
                    f"[Liq5] WARNING: {_trig} emergency LiqProximity exits "
                    f"triggered this session. Leverage on some assets may be "
                    f"too aggressive. Consider reducing MAX_CONCURRENT_ASSETS "
                    f"or checking MMR values."
                )
                _LIQ_EMERGENCY_STATS['last_warned_at'] = time.time()

            # ══ Persist state ══
            try:
                with open(state_file, 'w') as f:
                    json.dump(open_pos_live, f, indent=2, default=str)
            except Exception as e:
                log.warning(f"[State] end-of-cycle save failed: {e}")
            save_pending_orders()
            save_watched_signals()
            save_symbol_meta()
            
            # استرخاء المحرك للمزامنة الزمنية
            sleep_time = max(0, cfg.LIVE_POLL_SECS - (time.time() - t0))
            time.sleep(sleep_time)
            
        except KeyboardInterrupt: 
            log.info("تم إيقاف الروبوت يدوياً.")
            break
        except Exception as e: 
            import traceback
            log.error(f"خطأ غير متوقع في حلقة التداول: {e}")
            log.debug(traceback.format_exc())
            time.sleep(10)

# ════════════════════════════════════════════════════════════════
# § 19.5  Time-Sync Guard
# ════════════════════════════════════════════════════════════════

def _check_time_sync(exchange, warn_threshold_s: float = 30.0) -> bool:
    """
    Compare exchange server time with local time.
    Warn if drift > threshold. Returns True if OK, False if drift.
    """
    try:
        server_ms = exchange.fetch_time()
        server_s = float(server_ms) / 1000.0
        local_s = time.time()
        drift = abs(local_s - server_s)
        if drift > warn_threshold_s:
            log.warning(f"[TimeSync] local drift = {drift:.1f}s "
                        f"(> {warn_threshold_s}s) — enable NTP")
            return False
        else:
            log.info(f"[TimeSync] drift = {drift:.2f}s — OK")
            return True
    except Exception as e:
        log.debug(f"[TimeSync] check failed: {e}")
        return True  # fail open

# ════════════════════════════════════════════════════════════════
# § 20  نقطة الدخول
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Quantum Thermo Trader v6.0 – Singularity Engine")
    p.add_argument("--mode",        default="backtest", choices=["backtest","testnet","live"])
    p.add_argument("--api-key",     default=os.environ.get("BINANCE_API_KEY",""))
    p.add_argument("--api-secret",  default=os.environ.get("BINANCE_API_SECRET",""))
    p.add_argument("--capital",     type=float, default=None)
    p.add_argument("--live-capital", type=float, default=None,
                   help="Fixed trading capital for live/testnet sizing (overrides exchange free balance)")
    p.add_argument("--base-risk",   type=float, default=None)
    p.add_argument("--max-risk",    type=float, default=None)
    p.add_argument("--min-risk",    type=float, default=None)
    p.add_argument("--lambda-k",    type=float, default=None)
    p.add_argument("--leverage",    type=int,   default=None)
    p.add_argument("--sl-factor",   type=float, default=None)
    p.add_argument("--min-score",   type=int,   default=None)
    p.add_argument("--max-hold",    type=int,   default=None)
    p.add_argument("--topo-div",    type=float, default=None)
    p.add_argument("--cosm-const",  type=float, default=None)
    p.add_argument("--k-min",       type=int,   default=None)
    p.add_argument("--k-max",       type=int,   default=None)
    p.add_argument("--timeframe",
                   choices=["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
                   default="4h")
    p.add_argument("--history-days",       type=int,   default=None)
    p.add_argument("--end-date", type=str, default=None,
                   help="Backtest end date YYYY-MM-DD for reproducibility")
    p.add_argument("--no-numba", action="store_true",
                   help="Disable Numba kernels and use pure-Python fallback")
    p.add_argument("--nassets",       type=int,   default=15)
    p.add_argument("--maxcon",       type=int,   default=2)
    p.add_argument("--fill-mode",   choices=["maker", "taker", "hybrid"], default=None,
                   help="Entry execution mode (default: hybrid)")
    p.add_argument("--fill-target", type=float, default=None,
                   help="Target fill rate (0.0–1.0, default 0.90)")
    p.add_argument("--no-fill-engine", action="store_true",
                   help="Disable FillEngine and use legacy execution")
    p.add_argument("--no-parallel", action="store_true",
                   help="Disable multiprocessing (serial processing)")
    p.add_argument("--workers", type=int, default=0,
                   help="Number of parallel workers (0 = auto)")
    p.add_argument("--no-cache", action="store_true",
                   help="Disable AssetData disk cache")
    p.add_argument("--clear-cache", action="store_true",
                   help="Clear asset cache before running")
    p.add_argument("--po-pen-bps", type=float, default=None,
                   help="Post-Only penetration beyond touch (default 1.0)")
    p.add_argument("--po-wait-s", type=int, default=None,
                   help="Post-Only entry wait time (default 30s)")

    p.add_argument("--heat-max", type=float, default=None,
                   help="Portfolio heat budget (default 0.10 = 10%%)")
    p.add_argument("--no-budget", action="store_true",
                   help="Disable portfolio risk budget (legacy per-trade sizing)")
    p.add_argument("--ml-filter", action="store_true",
                   help="Enable ML signal filter (default: OFF)")
    p.add_argument("--ml-model", type=str, default=None,
                   help="Path to trained model (default: ml_filter.pkl)")
    p.add_argument("--ml-threshold", type=float, default=None,
                   help="Override ML threshold (0-1)")
    p.add_argument("--rule-filter", action="store_true",
                   help="Enable rule-based failure-pattern filter (no ML)")
    p.add_argument("--rule-min-score", type=int, default=None,
                   help="Reject if #failure-rules matched >= this (default 2)")
    p.add_argument("--max-notional", type=float, default=None,
                   help="Absolute notional cap in USD (default 100000)")
    p.add_argument("--no-dynamic-trail", action="store_true",
                   help="Use fixed TRAIL_DISTANCE instead of σ-scaled trailing")
    p.add_argument("--no-trailing", action="store_true",
                   help="Disable Trailing Stop Loss entirely (SL stays fixed)")
    p.add_argument("--trailing", action="store_true",
                   help="Force-enable Trailing Stop Loss (overrides config)")
    p.add_argument("--trail-kappa", type=float, default=None,
                   help="Trail multiplier on σ (default 1.5)")
    p.add_argument("--reentry-cooldown", type=int, default=None,
                   help="Bars to wait after exit before re-entry (default 3)")
    p.add_argument("--no-reentry-cooldown", action="store_true",
                   help="Disable re-entry cooldown (allow immediate re-entry)")
    p.add_argument("--no-live-cache", action="store_true",
                   help="Disable Live AssetData cache (always recompute)")
    p.add_argument("--live-cache-size", type=int, default=None,
                   help="Max Live cache entries (default 40)")
    p.add_argument("--no-fixed-price", action="store_true",
                   help="Disable fixed-price entry (allow reprice chasing)")
    p.add_argument("--po-max-attempts", type=int, default=None,
                   help="Max cancel/replace cycles (default 3)")
    p.add_argument("--po-max-drift-bps", type=float, default=None,
                   help="Abort if drift exceeds this (default 5.0)")
    p.add_argument("--po-min-accept", type=float, default=None,
                   help="Min fill ratio to accept partial (default 0.50)")
    p.add_argument("--no-pending", action="store_true",
                   help="Disable non-blocking pending orders (use legacy blocking)")
    p.add_argument("--no-smart-ohlcv", action="store_true",
                   help="Disable smart OHLCV fetch (always fetch every cycle)")
    p.add_argument("--sr-filter", action="store_true",
                   help="Enable support/resistance filter (default OFF)")
    p.add_argument("--sr-strength", type=float, default=None,
                   help="S/R strength threshold (default 1.0)")
    p.add_argument("--sr-proximity", type=float, default=None,
                   help="SL-to-level proximity (default 0.006)")
    p.add_argument("--kill-secret", type=str,
                   default=os.environ.get("KILL_SWITCH_SECRET", ""),
                   help="HMAC secret for kill switch (or KILL_SWITCH_SECRET env)")
    p.add_argument("--trade-log", type=str, default=None,
                   help="Path to trade log file (JSONL). "
                        "Default: trades_log_{mode}.jsonl")
    # ══ [SINGULARITY TIMING] ══
    p.add_argument("--sing-timing", action="store_true",
                   help="Enable Singularity timing layer (Layer 1: "
                        "EMERGING) — adjusts pending window dynamically")
    p.add_argument("--sing-active", action="store_true",
                   help="Enable Singularity timing Layer 2 (ACTIVE) — "
                        "upgrades GTX to marketable limit when resonance "
                        "is ACTIVE. Requires --sing-timing")
    p.add_argument("--sing-funding-guard", action="store_true",
                   help="Enable Singularity Layer 3A: skip entries within "
                        "30 minutes before funding time. Requires "
                        "--sing-timing")
    p.add_argument("--sing-risk-boost", action="store_true",
                   help="Enable Singularity Layer 3B: boost risk × 1.2 "
                        "when resonance is ACTIVE. Requires --sing-timing")
    # ══ [TRADE FILTER] ══
    p.add_argument("--filter", action="store_true",
                   help="Enable pre-entry trade filter (multi-signal)")
    p.add_argument("--filter-action-bias", action="store_true",
                   help="[CAUTION] Include action_buy as a rejection vote "
                        "(regime-bias risk)")
    p.add_argument("--filter-no-ema", action="store_true",
                   help="Disable ema_slope vote")
    p.add_argument("--filter-no-atr", action="store_true",
                   help="Disable high_atr vote")
    p.add_argument("--filter-no-friction", action="store_true",
                   help="Disable friction_drag vote")
    p.add_argument("--filter-min-votes", type=int, default=None,
                   help="Minimum votes to reject (default 2)")
    p.add_argument("--filter-atr-max", type=float, default=None,
                   help="Max ATR fraction (default 0.024)")
    p.add_argument("--filter-friction-max", type=float, default=None,
                   help="Max friction_drag/sl_dist (default 2.5)")
    p.add_argument("--filter-log", action="store_true",
                   help="Log every rejection at DEBUG level")
    p.add_argument("--no-kill-switch", action="store_true",
                   help="Disable kill switch")
    p.add_argument("--no-watch", action="store_true",
                   help="Disable watch-then-trigger mode "
                        "(place orders immediately, legacy behavior)")
    p.add_argument("--gauge-filter", action="store_true",
                   help="Enable Gauge filter (BUY>p60, SELL>p85)")
    p.add_argument("--gauge-buy-pct", type=float, default=None,
                   help="BUY percentile threshold (default 0.60)")
    p.add_argument("--gauge-sell-pct", type=float, default=None,
                   help="SELL percentile threshold (default 0.85)")
    p.add_argument("--gauge-disable-sell", action="store_true",
                   help="[DEPRECATED] SELL already disabled by default")
    # [ABLATION-FLAGS]
    p.add_argument("--no-apex", action="store_true",
                   help="Disable Apex exit")
    p.add_argument("--no-partial", action="store_true",
                   help="Disable Partial TP")
    p.add_argument("--no-breakeven", action="store_true",
                   help="Disable Breakeven SL")
    p.add_argument("--tp-mult", type=float, default=None,
                   help="Override TP_MULT")
    p.add_argument("--partial-tp-r", type=float, default=None,
                   help="Override PARTIAL_TP_R")
    p.add_argument("--sl-widen-mult", type=float, default=None,
                   help="Override SL_WIDEN_MULT")
    p.add_argument("--sell-only", action="store_true",
                   help="SELL-only mode")
    p.add_argument("--enable-sell", action="store_true",
                   help="Re-enable SELL signals (default: BUY-only)")
    # [SELL-RND] SELL tuning flags
    p.add_argument("--sell-min-score", type=int, default=None)
    p.add_argument("--sell-min-zdev", type=float, default=None)
    p.add_argument("--sell-gauge-pct", type=float, default=None)
    p.add_argument("--sell-require-ema-down", action="store_true")
    p.add_argument("--sell-major-only", action="store_true")
    p.add_argument("--sell-min-atr-frac", type=float, default=None)
    p.add_argument("--opp-tp", action="store_true",
                   help="Enable adaptive TP: when an opposite signal "
                        "appears on the same symbol, move the open "
                        "position's TP to the opposite's tunnel entry")
    p.add_argument("--opp-tp-score-mult", type=float, default=None,
                   help="Min score ratio (opp/entry) to trigger TP move "
                        "(default 1.20)")
    p.add_argument("--opp-tp-min-profit-r", type=float, default=None,
                   help="Minimum guaranteed profit in R units "
                        "(default 0.5)")
    p.add_argument("--opp-tp-min-delta-r", type=float, default=None,
                   help="Minimum TP improvement in R units to fire "
                        "(default 0.3)")
    p.add_argument("--opp-tp-max-age-bars", type=int, default=None,
                   help="Max age of opposite signal in bars (default 4)")
    # ══ [MFAL] CLI args ══
    p.add_argument("--mfal", action="store_true",
                   help="Enable Multi-Factor Adaptive Leverage")
    p.add_argument("--mfal-no-micro", action="store_true",
                   help="Disable micro-structure factor M")
    p.add_argument("--mfal-no-time", action="store_true",
                   help="Disable time-of-day factor T")
    p.add_argument("--mfal-no-learn", action="store_true",
                   help="Disable online learning")
    p.add_argument("--mfal-weights", type=str, default=None,
                   help="Path to MFAL weights JSON")

    # ══ [UNIFIED] CLI args ══
    p.add_argument("--unified", action="store_true",
                   help="Enable Unified Decision Engine")
    p.add_argument("--unified-weights", type=str, default=None,
                   help="Path to unified weights JSON")
    p.add_argument("--unified-epsilon", type=float, default=None,
                   help="Ruin tolerance (default 0.001)")
    p.add_argument("--unified-shrinkage", type=float, default=None,
                   help="Kelly shrinkage factor (default 0.5)")

    args = p.parse_args()
    # [UNIFIED] CLI wiring
    try:
        if getattr(args, 'unified', False):
            globals()['_UNIFIED_ENABLED'] = True
            if getattr(args, 'unified_weights', None):
                globals()['_UNIFIED_WEIGHTS_PATH'] = str(args.unified_weights)
            if getattr(args, 'unified_epsilon', None) is not None:
                globals()['_UNIFIED_EPSILON'] = float(args.unified_epsilon)
            if getattr(args, 'unified_shrinkage', None) is not None:
                globals()['_UNIFIED_SHRINKAGE'] = float(args.unified_shrinkage)
            _unified_load_state()
            log.info(
                f"[Unified] ENABLED "
                f"(ε={_UNIFIED_EPSILON}, shrink={_UNIFIED_SHRINKAGE})"
            )
        else:
            log.info("[Unified] Disabled (use --unified to enable)")
    except Exception as _e:
        log.warning(f"[Unified] CLI wiring failed: {_e}")
    # [MFAL] CLI wiring
    try:
        if args.mfal:
            globals()['_MFAL_ENABLED'] = True
            if args.mfal_no_micro:
                globals()['_MFAL_USE_MICRO'] = False
            if args.mfal_no_time:
                globals()['_MFAL_USE_TIME'] = False
            if args.mfal_no_learn:
                globals()['_MFAL_USE_LEARNING'] = False
            if args.mfal_weights:
                globals()['_MFAL_WEIGHTS_PATH'] = str(args.mfal_weights)
            _mfal_load_weights()
            log.info(
                "[MFAL] ENABLED  "
                f"micro={_MFAL_USE_MICRO} "
                f"time={_MFAL_USE_TIME} "
                f"learn={_MFAL_USE_LEARNING}"
            )
        else:
            log.info("[MFAL] Disabled (use --mfal to enable)")
    except Exception as _e:
        log.warning(f"[MFAL] CLI wiring failed: {_e}")

    CFG.mode = args.mode
    CFG.api_key = args.api_key
    CFG.api_secret = args.api_secret
    if args.capital   is not None: CFG.INITIAL_CAPITAL = args.capital
    if args.live_capital is not None: CFG.LIVE_TRADING_CAPITAL = float(args.live_capital)
    if args.base_risk is not None: CFG.BASE_RISK = args.base_risk; CFG.MIN_RISK_PER_TRADE = args.base_risk
    if args.max_risk  is not None: CFG.MAX_RISK  = args.max_risk
    if args.min_risk  is not None: CFG.MIN_RISK  = args.min_risk
    if args.lambda_k  is not None: CFG.LAMBDA_KELLY = args.lambda_k
    if args.leverage  is not None: CFG.LEVERAGE  = args.leverage
    if args.sl_factor is not None: CFG.SL_FACTOR = args.sl_factor
    if args.min_score is not None: CFG.MIN_SCORE = args.min_score
    if args.max_hold  is not None: CFG.MAX_HOLD_BARS = args.max_hold
    if args.topo_div  is not None: CFG.TOPO_DIV_THRESHOLD = args.topo_div
    if args.cosm_const is not None: CFG.COSMOLOGICAL_CONSTANT = args.cosm_const
    if args.k_min     is not None: CFG.K_MIN = args.k_min
    if args.k_max     is not None: CFG.K_MAX = args.k_max
    if args.timeframe     is not None: CFG.timeframe = args.timeframe
    if args.history_days     is not None: CFG.history_days = args.history_days
    if getattr(args, "end_date", None) is not None:
        CFG.BACKTEST_END_DATE = str(args.end_date)
        log.info(f"[Backtest] end-date pinned to {args.end_date}")
    if args.po_pen_bps is not None:  CFG.PO_PENETRATION_BPS = args.po_pen_bps
    if args.po_wait_s is not None:   CFG.PO_MAX_WAIT_S = args.po_wait_s
    if args.heat_max is not None: CFG.PORTFOLIO_HEAT_MAX = args.heat_max
    if args.no_numba: CFG.NUMBA_ENABLED = False

    # ══ [Level-2] Compile Numba kernels before starting ══
    _warmup_numba_kernels()
    if args.nassets     is not None: CFG.n_assets = args.nassets
    # ══ [Cache sizing] ensure capacity ≥ n_assets + safety margin ══
    _min_cache = max(50, int(CFG.n_assets * 1.5))
    if CFG.LIVE_ASSET_CACHE_MAX < _min_cache:
        CFG.LIVE_ASSET_CACHE_MAX = _min_cache
        log.info(f"[Cache] LIVE_ASSET_CACHE_MAX adjusted to {_min_cache}")
    if args.maxcon     is not None: CFG.MAX_CONCURRENT_ASSETS = args.maxcon
    if args.fill_mode is not None: CFG.FILL_ENTRY_MODE = args.fill_mode
    if args.fill_target is not None: CFG.FILL_TARGET = float(args.fill_target)
    if args.no_parallel:  CFG.PARALLEL_PROCESSING = False
    if args.workers:      CFG.PARALLEL_WORKERS = args.workers
    if args.no_cache:     CFG.ASSET_CACHE_ENABLED = False
    if args.clear_cache:
        import shutil
        # 1. Clear AssetData pickle cache
        if os.path.exists(CFG.ASSET_CACHE_DIR):
            shutil.rmtree(CFG.ASSET_CACHE_DIR)
            log.info(f"[Cache] cleared {CFG.ASSET_CACHE_DIR}")
        os.makedirs(CFG.ASSET_CACHE_DIR, exist_ok=True)
        # 2. Clear market OHLCV parquet cache
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
            log.info(f"[Cache] cleared {CACHE_DIR}")
            os.makedirs(CACHE_DIR, exist_ok=True)
        # 3. Clear persistent state files (positions, pendings, meta, kill)
        _state_files = [
            "live_state_live.json", "live_state_testnet.json",
            "pending_orders_live.json", "pending_orders_testnet.json",
            "symbol_meta_live.json", "symbol_meta_testnet.json",
            "kill_switch.json",
        ]
        for _f in _state_files:
            if os.path.exists(_f):
                try:
                    os.remove(_f)
                    log.info(f"[Clean] removed {_f}")
                except Exception as _e:
                    log.warning(f"[Clean] failed to remove {_f}: {_e}")
        # 4. Clear __pycache__ of this file's directory (safety)
        _pc = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "__pycache__")
        if os.path.exists(_pc):
            try:
                shutil.rmtree(_pc)
                log.info(f"[Clean] removed {_pc}")
            except Exception as _e:
                log.debug(f"[Clean] __pycache__ removal skipped: {_e}")
    if args.no_fill_engine: CFG.FILL_ENGINE_ENABLED = False
    if args.no_budget: CFG.BUDGET_ENABLED = False
    # ══ [TIMEFRAME SCALE] initialize before any data fetch ══
    try:
        import ccxt as _ccxt_probe
        _probe = _ccxt_probe.binance()
        CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = compute_tf_scale(_probe, CFG.timeframe)
    except Exception:
        CFG.TF_SCALE, CFG.TF_SECONDS, CFG.TF_HOURS = compute_tf_scale(None, CFG.timeframe)
    log.info(f"[TF] timeframe={CFG.timeframe} "
             f"TF_SCALE={CFG.TF_SCALE:.4f} "
             f"TF_SECONDS={CFG.TF_SECONDS} "
             f"TF_HOURS={CFG.TF_HOURS:.3f}")

    # ══ [TF-UNIFIED WINDOWS] اشتقاق N/W/L/ADV_BARS من الساعات ══
    # النوافذ المُعايَرة على 1h: N=24, W=20, L=10 شمعة = 24h, 20h, 10h.
    # على الأُطر الأصغر، نزيد عدد الشموع للحفاظ على نفس المدة الحقيقية.
    # على الأُطر الأكبر، نبقي العدد كما هو (لأن 24 شمعة على 4h = 96 ساعة
    # وهو كافٍ إحصائياً).
    _tf_h = max(float(CFG.TF_HOURS), 1e-6)
    _tf_scale_u = 1.0 / _tf_h   # 1h → 1.0, 4h → 0.25, 5m → 12.0

    # N/W/L: زد العدد فقط إذا كانت النافذة الحالية أقصر من المطلوب.
    _n_min = int(np.ceil(float(getattr(CFG, 'N_HOURS', 24.0)) / _tf_h))
    _w_min = int(np.ceil(float(getattr(CFG, 'W_HOURS', 20.0)) / _tf_h))
    _l_min = int(np.ceil(float(getattr(CFG, 'L_HOURS', 10.0)) / _tf_h))

    if CFG.N < _n_min:
        log.info(f"[TF-Unified] N: {CFG.N} → {_n_min} "
                 f"(لتغطية {CFG.N_HOURS:.1f}h على {CFG.timeframe})")
        CFG.N = _n_min
    if CFG.W < _w_min:
        log.info(f"[TF-Unified] W: {CFG.W} → {_w_min}")
        CFG.W = _w_min
    if CFG.L < _l_min:
        log.info(f"[TF-Unified] L: {CFG.L} → {_l_min}")
        CFG.L = _l_min

    # ADV_BARS: اضبطه على 24 ساعة بالضبط
    _adv_h = float(getattr(CFG, 'ADV_HOURS', 24.0))
    CFG.ADV_BARS = max(1, int(round(_adv_h / _tf_h)))
    log.info(f"[TF-Unified] N={CFG.N} W={CFG.W} L={CFG.L} "
             f"ADV_BARS={CFG.ADV_BARS} (σ≈{CFG.TF_SCALE:.2f}× 1h)")

    # ══ [SMART DATA AUTO-CONFIG] ══
    # Applies to BOTH backtest and live/testnet. Backtest prioritizes
    # statistical power (max history); live/testnet prioritize lightness.
    # User override via --history-days is respected but physically clamped.
    _user_hd = args.history_days if args.history_days is not None else None
    _hd, _tb, _mb, _src, _qual = _resolve_data_params(
        CFG, CFG.mode, CFG.TF_HOURS, user_history_days=_user_hd
    )

    if CFG.mode == "backtest":
        CFG.history_days = int(_hd)
        log.info(f"[Data] mode=backtest | tf={CFG.timeframe} | "
                 f"history={_hd}d ({_tb} bars/symbol) | "
                 f"quality={_qual} | source={_src}")
    else:
        CFG.LIVE_HISTORY_DAYS         = int(_hd)
        CFG.LIVE_TAIL_BARS            = int(_tb)
        CFG.LIVE_MIN_BARS_FOR_PROCESS = int(_mb)
        log.info(f"[Data] mode={CFG.mode} | tf={CFG.timeframe} | "
                 f"history={_hd}d | tail={_tb} bars/sym | "
                 f"min_for_process={_mb} bars | "
                 f"quality={_qual} | source={_src}")

    # Quality indicators
    _strict = 2 * int(CFG.K_MAX) * int(getattr(CFG, 'K_MIN_TRAIN_POINTS_PER_CLUSTER', 100)) + int(CFG.N)
    if _qual == "full":
        log.info(f"[Data] K can reach K_MAX={CFG.K_MAX} "
                 f"(tail ≥ strict_min={_strict}).")
    elif _qual == "reduced":
        _k_est = max(int(CFG.K_MIN), _tb // 2 // int(getattr(CFG, 'K_MIN_TRAIN_POINTS_PER_CLUSTER', 100)))
        _k_est = min(_k_est, int(CFG.K_MAX))
        log.info(f"[Data] K will be capped near {_k_est} "
                 f"(tail < strict_min={_strict}). "
                 f"Normal for large TFs (4h, 1d) or low --history-days.")
    else:  # degraded
        log.warning(
            f"[Data] degraded quality: tail={_tb} < strict_min/2={_strict//2}. "
            f"Many assets may be skipped by degenerate detection. "
            f"Recommended minimum for {CFG.timeframe}: "
            f"--history-days {int(np.ceil(_strict * 1.4 * CFG.TF_HOURS / 24))}."
        )

    if args.ml_filter:
        CFG.ML_FILTER_ENABLED = True
        if args.ml_model:
            CFG.ML_FILTER_MODEL_PATH = args.ml_model
        if args.ml_threshold is not None:
            CFG.ML_FILTER_THRESHOLD = float(args.ml_threshold)

        if not _load_ml_filter():
            log.error("[ML] failed to load model — disabling filter")
            CFG.ML_FILTER_ENABLED = False
        else:
            # ══ [ML Live Tracking] reset counters ══
            _ML_LIVE_STATS['unique_seen'] = 0
            _ML_LIVE_STATS['unique_kept'] = 0
            _ML_LIVE_STATS['unique_rejected'] = 0
            _ML_LIVE_STATS['last_seen'] = {}
            log.info(f"[ML] Filter enabled @ threshold={CFG.ML_FILTER_THRESHOLD:.3f}")
    if args.rule_filter:
        CFG.RULE_FILTER_ENABLED = True
    if args.rule_min_score is not None:
        CFG.RULE_MIN_SCORE = int(args.rule_min_score)
    if args.max_notional is not None:
        CFG.MAX_ABS_NOTIONAL = float(args.max_notional)
    if args.no_dynamic_trail:
        CFG.TRAIL_DYNAMIC = False
    if args.no_trailing:
        CFG.TRAIL_ENABLED = False
        log.info("[Trail] Trailing Stop Loss DISABLED — SL is fixed")
    elif args.trailing:
        CFG.TRAIL_ENABLED = True
        log.info("[Trail] Trailing Stop Loss FORCED ON")
    if args.trail_kappa is not None:
        CFG.TRAIL_KAPPA = float(args.trail_kappa)
    if args.reentry_cooldown is not None:
        CFG.REENTRY_COOLDOWN_BARS = int(args.reentry_cooldown)
    if args.no_reentry_cooldown:
        CFG.REENTRY_COOLDOWN_ENABLED = False
    if args.no_live_cache:
        CFG.LIVE_ASSET_CACHE_ENABLED = False
    if args.live_cache_size is not None:
        CFG.LIVE_ASSET_CACHE_MAX = int(args.live_cache_size)
    if args.no_fixed_price:
        CFG.PO_FIXED_PRICE = False
        log.info("[Backtest] --no-fixed-price: entry target will be derived "
                 "from close[sig.close_idx] × (1 ± PO_PENETRATION_BPS)")
    if args.po_max_attempts is not None:
        CFG.PO_MAX_ATTEMPTS = int(args.po_max_attempts)
    if args.po_max_drift_bps is not None:
        CFG.PO_MAX_DRIFT_BPS = float(args.po_max_drift_bps)
    if args.po_min_accept is not None:
        CFG.PO_MIN_ACCEPT_RATIO = float(args.po_min_accept)
    if args.no_pending:
        CFG.PENDING_ENABLED = False
    if args.no_smart_ohlcv:
        CFG.SMART_OHLCV_ENABLED = False
    if args.sr_filter:
        CFG.SR_FILTER_ENABLED = True
    if args.sr_strength is not None:
        CFG.SR_STRENGTH_THRESHOLD = float(args.sr_strength)
    if args.sr_proximity is not None:
        CFG.SR_SL_PROXIMITY = float(args.sr_proximity)
    if args.kill_secret:
        CFG.KILL_SWITCH_SECRET = args.kill_secret
    if args.no_kill_switch:
        CFG.KILL_SWITCH_ENABLED = False
    if args.no_watch:
        CFG.WATCH_MODE_ENABLED = False
        log.info("[Watch] Watch-then-trigger DISABLED — legacy immediate placement")
    else:
        if CFG.WATCH_MODE_ENABLED:
            log.info("[Watch] Watch-then-trigger ENABLED "
                     f"(κ_prox={CFG.WATCH_PROX_KAPPA}, "
                     f"swing_lookback={CFG.WATCH_SWING_LOOKBACK}, "
                     f"phase1_timeout={CFG.WATCH_PHASE1_TIMEOUT_BARS_1H}h)")
        else:
            log.info("[Watch] Watch-then-trigger DISABLED (Config default) — "
                     f"legacy immediate placement")

    if args.gauge_filter:
        CFG.GAUGE_FILTER_ENABLED = True
        log.info("[Gauge] Filter ENABLED")
    if args.gauge_buy_pct is not None:
        CFG.GAUGE_PERCENTILE_BUY = float(args.gauge_buy_pct)
    if args.gauge_sell_pct is not None:
        CFG.GAUGE_PERCENTILE_SELL = float(args.gauge_sell_pct)
    if args.gauge_disable_sell:
        CFG.GAUGE_DISABLE_SELL = True
        log.info("[Gauge] SELL DISABLED — BUY-only mode")
    # [ABLATION-FLAGS]
    if getattr(args, "no_apex", False):
        CFG.APEX_ENABLED = False
        log.info("[Ablation] APEX DISABLED")
    if getattr(args, "no_partial", False):
        CFG.PARTIAL_TP_ENABLED = False
        log.info("[Ablation] PARTIAL_TP DISABLED")
    if getattr(args, "no_breakeven", False):
        CFG.BREAKEVEN_ENABLED = False
        log.info("[Ablation] BREAKEVEN DISABLED")
    if getattr(args, "tp_mult", None) is not None:
        CFG.TP_MULT = float(args.tp_mult)
        log.info(f"[Ablation] TP_MULT = {CFG.TP_MULT}")
    if getattr(args, "partial_tp_r", None) is not None:
        CFG.PARTIAL_TP_R = float(args.partial_tp_r)
        log.info(f"[Ablation] PARTIAL_TP_R = {CFG.PARTIAL_TP_R}")
    if getattr(args, "sl_widen_mult", None) is not None:
        CFG.SL_WIDEN_MULT = float(args.sl_widen_mult)
        log.info(f"[Ablation] SL_WIDEN_MULT = {CFG.SL_WIDEN_MULT}")
    if getattr(args, "sell_only", False):
        CFG.GAUGE_DISABLE_BUY = True
        log.info("[Ablation] BUY DISABLED — SELL-only mode")
    # ═══ [ABLATION-FLAGS] ═══
    if getattr(args, "no_apex", False):
        CFG.APEX_ENABLED = False
        log.info("[Ablation] APEX DISABLED")
    if getattr(args, "no_partial", False):
        CFG.PARTIAL_TP_ENABLED = False
        log.info("[Ablation] PARTIAL_TP DISABLED")
    if getattr(args, "no_breakeven", False):
        CFG.BREAKEVEN_ENABLED = False
        log.info("[Ablation] BREAKEVEN DISABLED")
    if getattr(args, "tp_mult", None) is not None:
        CFG.TP_MULT = float(args.tp_mult)
        log.info(f"[Ablation] TP_MULT = {CFG.TP_MULT}")
    if getattr(args, "partial_tp_r", None) is not None:
        CFG.partial_tp_r = float(args.partial_tp_r)
        log.info(f"[Ablation] PARTIAL_TP_R = {CFG.PARTIAL_TP_R}")
    if getattr(args, "sl_widen_mult", None) is not None:
        CFG.SL_WIDEN_MULT = float(args.sl_widen_mult)
        log.info(f"[Ablation] SL_WIDEN_MULT = {CFG.SL_WIDEN_MULT}")
    if getattr(args, "sell_only", False):
        CFG.GAUGE_DISABLE_BUY = True
        log.info("[Ablation] BUY DISABLED — SELL-only mode")
    if getattr(args, "enable_sell", False):
        CFG.GAUGE_DISABLE_SELL = False
        CFG.SELL_ENABLED = True
        log.info("[Gauge] SELL RE-ENABLED — experimental mode")
    # [SELL-RND] wiring
    if args.sell_min_score is not None:
        CFG.SELL_MIN_SCORE = int(args.sell_min_score)
    if args.sell_min_zdev is not None:
        CFG.SELL_MIN_ZDEV = float(args.sell_min_zdev)
    if args.sell_gauge_pct is not None:
        CFG.SELL_GAUGE_PCT = float(args.sell_gauge_pct)
    if args.sell_require_ema_down:
        CFG.SELL_REQUIRE_EMA_DOWN = True
    if args.sell_major_only:
        CFG.SELL_MAJOR_ONLY = True
    if args.sell_min_atr_frac is not None:
        CFG.SELL_MIN_ATR_FRAC = float(args.sell_min_atr_frac)

    # ══ [OppTP] Opposite-Signal Adaptive TP ══
    if args.opp_tp:
        CFG.OPP_TP_ENABLED = True
        if args.opp_tp_score_mult is not None:
            CFG.OPP_TP_SCORE_MULT = float(args.opp_tp_score_mult)
        if args.opp_tp_min_profit_r is not None:
            CFG.OPP_TP_MIN_PROFIT_R = float(args.opp_tp_min_profit_r)
        if args.opp_tp_min_delta_r is not None:
            CFG.OPP_TP_MIN_DELTA_R = float(args.opp_tp_min_delta_r)
        if args.opp_tp_max_age_bars is not None:
            CFG.OPP_TP_MAX_AGE_BARS = int(args.opp_tp_max_age_bars)
        log.info("[OppTP] Opposite-Signal Adaptive TP ENABLED")
        log.info(f"[OppTP]  score_mult={CFG.OPP_TP_SCORE_MULT}, "
                 f"min_profit_R={CFG.OPP_TP_MIN_PROFIT_R}, "
                 f"min_delta_R={CFG.OPP_TP_MIN_DELTA_R}, "
                 f"max_age={CFG.OPP_TP_MAX_AGE_BARS}")
    else:
        log.info("[OppTP] Opposite-Signal Adaptive TP DISABLED")
    # ══ [TRADE FILTER] ══
    if args.filter:
        CFG.FILTER_ENABLED = True
        log.info("[Filter] Trade filter ENABLED")
    if args.filter_action_bias:
        CFG.FILTER_USE_ACTION_BIAS = True
        log.warning("[Filter] action_bias vote ENABLED — regime-bias risk!")
    if args.filter_no_ema:
        CFG.FILTER_USE_EMA_SLOPE = False
    if args.filter_no_atr:
        CFG.FILTER_USE_HIGH_ATR = False
    if args.filter_no_friction:
        CFG.FILTER_USE_FRICTION_DRAG = False
    if args.filter_min_votes is not None:
        CFG.FILTER_MIN_VOTES = int(args.filter_min_votes)
    if args.filter_atr_max is not None:
        CFG.FILTER_ATR_FRAC_MAX = float(args.filter_atr_max)
    if args.filter_friction_max is not None:
        CFG.FILTER_FRICTION_DRAG_MAX = float(args.filter_friction_max)
    if args.filter_log:
        CFG.FILTER_LOG_REJECTIONS = True
    # ══ [SINGULARITY TIMING] ══
    if args.sing_timing:
        CFG.SING_TIMING_ENABLED = True
        log.info("[Sing-Timing] Layer 1 (EMERGING) ENABLED")
        log.info("[Sing-Timing] - DORMANT  → default timeout")
        log.info("[Sing-Timing] - EMERGING → shortened timeout")
        log.info("[Sing-Timing] - ACTIVE   → minimal timeout")
        log.info("[Sing-Timing] - DECAYING → order cancelled")
        # ══ [PARITY-CHECK] التحقق من أن الباكتيست والـ Live
        # سيستخدمان نفس المنطق.
        if CFG.mode == "backtest":
            log.info("[Sing-Timing] Backtest simulation ENABLED "
                     "(precompute_entry_fills + simulate_portfolio)")
    if args.sing_active:
        if not args.sing_timing:
            log.warning(
                "[Sing-Timing] --sing-active requires --sing-timing — "
                "enabling both"
            )
            CFG.SING_TIMING_ENABLED = True
        CFG.SING_ACTIVE_MARKETABLE = True
        log.info("[Sing-Timing] Layer 2 (ACTIVE → Marketable) ENABLED")
        log.info("[Sing-Timing] - ACTIVE + slip ≤ 15bps → marketable limit")
        log.info("[Sing-Timing] - ACTIVE + slip > 15bps → fallback to GTX")
        log.info("[Sing-Timing] - Taker fee applies to marketable fills")

    if args.sing_funding_guard:
        if not args.sing_timing:
            log.warning(
                "[Sing-Timing] --sing-funding-guard requires "
                "--sing-timing — enabling it"
            )
            CFG.SING_TIMING_ENABLED = True
        CFG.SING_FUNDING_GUARD_ENABLED = True
        log.info("[Sing-Timing] Layer 3A (Funding Guard) ENABLED")
        log.info(
            f"[Sing-Timing] - Skip entries within "
            f"{CFG.SING_FUNDING_GUARD_MINUTES} min of funding "
            f"({CFG.SING_FUNDING_HOURS_UTC} UTC)"
        )
    if args.sing_risk_boost:
        if not args.sing_timing:
            log.warning(
                "[Sing-Timing] --sing-risk-boost requires "
                "--sing-timing — enabling it"
            )
            CFG.SING_TIMING_ENABLED = True
        CFG.SING_RISK_BOOST_ENABLED = True
        log.info("[Sing-Timing] Layer 3B (Resonance Risk Boost) ENABLED")
        log.info(
            f"[Sing-Timing] - ACTIVE → risk × "
            f"{CFG.SING_RISK_BOOST_ACTIVE}"
        )
        log.info(
            f"[Sing-Timing] - EMERGING → risk × "
            f"{CFG.SING_RISK_BOOST_EMERGING}"
        )


    print("╔"+"═"*70+"╗")
    print(f"  [Level-1] Parallel: {CFG.PARALLEL_PROCESSING}  "
          f"Cache: {CFG.ASSET_CACHE_ENABLED}")
    print(f"  [Level-2] Numba: {_NUMBA_AVAILABLE and CFG.NUMBA_ENABLED}\n")
    print(f"║  محرك التداول الثرموديناميكي الكمي v6.0 – Singularity Engine     ║")
    print(f"║  الوضع: {CFG.mode.upper():10s}  |  رأس المال: ${CFG.INITIAL_CAPITAL:.2f}              ║")
    print("╠"+"═"*70+"╣")
    print(f"║  ① Boltzmann Kelly: BASE={CFG.BASE_RISK*100:.1f}%  λ={CFG.LAMBDA_KELLY}  [{CFG.MIN_RISK*100:.1f}%–{CFG.MAX_RISK*100:.1f}%]  ║")
    print(f"║  ② Topo-Divergence: ε={CFG.TOPO_DIV_THRESHOLD}  (حتمية هندسية)              ║")
    print(f"║  ③ Dynamic-K:       [{CFG.K_MIN}–{CFG.K_MAX}]  (SNR ∝ 1/m)                     ║")
    print(f"║  ④ Cosmological Λ:  {CFG.COSMOLOGICAL_CONSTANT}  (De Sitter drift)                  ║")
    print(f"║  ⑤ T_sync EMA-accel: فلتر التشابك عبر المقاييس                  ║")
    print("╚"+"═"*70+"╝\n")

    # ══ [Cache-Health] Reset stats ══
    _CACHE_HEALTH['files_scanned'] = 0
    _CACHE_HEALTH['issues_fixed_local'] = 0
    _CACHE_HEALTH['gaps_found'] = 0
    _CACHE_HEALTH['bars_refetched'] = 0
    _CACHE_HEALTH['files_saved'] = 0

    # ══ [TradeLog] تهيئة تسجيل الصفقات ══
    _trade_log_init(CFG.mode, args.trade_log)

    # 1. وضع الباك-تيست
    if CFG.mode == "backtest":
        run_backtest(CFG)
        return

    # 2. وضع Live أو Testnet
    try:
        import ccxt
    except ImportError:
        log.error("pip install ccxt")
        return

    if not CFG.api_key or not CFG.api_secret:
        log.error("--api-key و --api-secret مطلوبان للتداول الحي")
        return

    exchange = ccxt.binance({
        'apiKey': CFG.api_key,
        'secret': CFG.api_secret,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    # ══ [TimeSync] verify before run ══
    _check_time_sync(exchange)

    if CFG.mode == "testnet":
        # تم تحديث الدالة لتدعم خوادم Demo Trading الجديدة الخاصة بـ Binance
        exchange.enable_demo_trading(True) 

    run_live(CFG, exchange)

if __name__=="__main__":
    main()

# to run the project use the command 
# python3  trading_2_complete3.py   --mode   backtest   --api-key   ${BINANCE_TESTNET_KEY}   --api-secret   ${BINANCE_TESTNET_SECRET}   --capital   100   --nassets   100   --timeframe   4h   --no-fixed-price   --no-trailing   --history-days   730   --sell-only --enable-sell --sell-gauge-pct 100 --tp-mult 7 --sl-widen-mult 0.3 --no-apex --history-days 30 --end-date 2026-10-05 --partial-tp-r 7 --maxcon 2
