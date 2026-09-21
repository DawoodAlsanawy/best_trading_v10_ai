#!/usr/bin/env python3
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
os.environ["LOKY_MAX_CPU_COUNT"] = "4"
# [Level-1] Prevent BLAS/OpenMP thread oversubscription in workers
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
CACHE_DIR = "market_data_cache"
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
    W_HMM: float=2.0; W_FREE_E: float=1.0; MIN_SCORE: int=5.5

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
    CAPITAL_FLOOR: float = 5.0    # قوة التنافر اللانهائية (نقطة استحالة التصفية)
    MAKER_FEE: float = 0.0    # (-) تعني أننا نكسب عمولة الصانع لأننا سنستخدم النفق الكمي!
    MAX_CHUNK_USD: float = 10000.0 # أقصى حجم للحزمة الكمومية الواحدة بالدولار لتجنب صدمة دفتر الأوامر
    MIN_NOTIONAL: float = 5.0
    SL_FACTOR: float = 0.15
    TP_BETAS: Tuple = (1.5,)

    FUNDING_RATE_COST: float = 0.0001
    FUNDING_INTERVAL_BARS: int = 8

    MAX_DRAWDOWN_HALT: float   = 1.00
    REDUCED_RISK_MULT: float   = 0.25
    REDUCED_RISK_MULT_50: float= 0.10
    REDUCED_RISK_MULT_70: float= 0.05
    DRAWDOWN_REDUCE_AT:  float = 0.30
    DRAWDOWN_REDUCE_AT_50: float=0.50
    DRAWDOWN_REDUCE_AT_70: float=0.70

    MAX_CONCURRENT_ASSETS: int   = 5
    CORRELATION_THRESHOLD: float = 0.70

    MAX_HOLD_BARS: int = 168

    TOPO_DIV_THRESHOLD: float = 0.05

    K_MIN: int = 4
    K_MAX: int = 12
    KQUANT_ALPHA: float = 100.0

    COSMOLOGICAL_CONSTANT: float = 0

    OPTIMAL_ENTRY_WAIT: int=8; OPTIMAL_ENTRY_DIP: float=0.3

    REVERSAL_MIN_SCORE: int=3; LYA_WINDOW: int=20
    LYA_THRESHOLD_MULT: float=2.0

    SLIP_BASE: float=0.0003; SLIP_IMPACT: float=0.02
    MAX_SLIPPAGE_FRACTION: float=0.0002

    MAX_ADV_FRACTION: float=0.01

    TRAIN_FRACTION: float=0.50

    LIVE_POLL_SECS: int=60; LIVE_ORDER_TYPE: str = "MARKET"
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
    FILL_ENTRY_MAX_WAIT_BARS: int = 15           # order lifetime in backtest
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
    PO_MAX_WAIT_S: int = 30              # entry wait time (per attempt)
    PO_EXIT_MAX_WAIT_S: int = 30          # reduced from 180 to prevent long blocking
    PO_REPRICE_S: float = 3.0            # cancel/replace interval
    PO_FILL_THRESHOLD: float = 0.50      # accept partial if ≥ 50%
    PO_EXIT_FALLBACK_MARKET: bool = True # exit → market after timeout
    PO_DRIFT_BPS: float = 0.5            # reprice if target drifts > this

    # ══ [TRAILING STOP] ══
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
    RECONCILE_INTERVAL_S: int = 30
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
    PO_FIXED_PRICE: bool = True              # use sig.price, hold it fixed
    # ══ [ATOMIC FILL ACCOUNTING] ══
    PO_MAX_ATTEMPTS: int = 3              # reduced from 5 (rate-limit safety)
    PO_MAX_DRIFT_BPS: float = 5.0
    PO_MIN_ACCEPT_RATIO: float = 0.50     # reject below 50% (was 0.15, comment was misleading)

    # ══ [NON-BLOCKING PENDING ORDERS] ══
    PENDING_ENABLED: bool = True
    PENDING_FILE_PREFIX: str = "pending_orders"
    PENDING_MAX_PER_CYCLE: int = 3        # cap new placements per loop
    PENDING_REST_CHECK_EVERY: int = 2     # check each pending order every N loops

    # ══ [SMART OHLCV FETCH] ══
    SMART_OHLCV_ENABLED: bool = True

CFG = Config()


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
#            "XAG/USDT","TRX/USDT","TON/USDT","BCH/USDT","NEAR/USDT",
#            "APT/USDT","HBAR/USDT","VET/USDT",
#            "STX/USDT","AAVE/USDT","ARB/USDT",
#            "OP/USDT","INJ/USDT","SUI/USDT","TIA/USDT","SEI/USDT",
#            "ALGO/USDT","GRT/USDT","FET/USDT","RENDER/USDT",
#            "LDO/USDT","KAS/USDT","WIF/USDT","THETA/USDT","EGLD/USDT",
#            "SAND/USDT","MANA/USDT","AXS/USDT","XLM/USDT","CHZ/USDT"]
def _default_assets():
    # أعلى 50 عملة من حيث القيمة السوقية مع قبول رافعة 50x على Binance Futures
    return [
        "BTC/USDT",   # بيتكوين - أعلى سيولة، رافعة 125x
        "ETH/USDT",   # إيثيريوم - ثاني أعلى سيولة، رافعة 100x
        "BNB/USDT",   # بيнанс كوين - رافعة 75x
        "SOL/USDT",   # سولانا - رافعة 50x
        "XRP/USDT",   # ريبل - رافعة 50x
        "DOGE/USDT",  # دوجكوين - رافعة 50x
        "ADA/USDT",   # كاردانو - رافعة 50x
        "AVAX/USDT",  # أفالانش - رافعة 50x
        "LINK/USDT",  # تشين لينك - رافعة 50x
        "DOT/USDT",   # بولكادوت - رافعة 50x
        "LTC/USDT",   # لايتكوين - رافعة 50x
        "UNI/USDT",   # يونيسواب - رافعة 50x
        "ATOM/USDT",  # كوزموس - رافعة 50x
        "ETC/USDT",   # إيثيريوم كلاسيك - رافعة 50x
        "TRX/USDT",   # ترون - رافعة 50x
        "TON/USDT",   # تون كوين - رافعة 50x
        "BCH/USDT",   # بيتكوين كاش - رافعة 50x
        "NEAR/USDT",  # نير بروتوكول - رافعة 50x
        "APT/USDT",   # أبتوس - رافعة 50x
        "HBAR/USDT",  # هيدرا - رافعة 50x
        "VET/USDT",   # في تشين - رافعة 50x
        "STX/USDT",   # ستاكس - رافعة 50x
        "AAVE/USDT",  # آفي - رافعة 50x
        "ARB/USDT",   # أربيتروم - رافعة 50x
        "OP/USDT",    # أوبتيميزم - رافعة 50x
        "INJ/USDT",   # إنجكتيف - رافعة 50x
        "SUI/USDT",   # سوي - رافعة 50x
        "TIA/USDT",   # سيليستيا - رافعة 50x
        "SEI/USDT",   # ساي - رافعة 50x
        "ALGO/USDT",  # ألجوراند - رافعة 50x
        "GRT/USDT",   # ذا غراف - رافعة 50x
        "FET/USDT",   # فيتشد أيه آي - رافعة 50x
        "RENDER/USDT",# ريندر - رافعة 50x
        "LDO/USDT",   # ليدو داو - رافعة 50x
        "KAS/USDT",   # كاسبا - رافعة 50x
        "WIF/USDT",   # دوج ويف هات - رافعة 50x
        "THETA/USDT", # ثيتا - رافعة 50x
        "EGLD/USDT",  # مولتي فيرس إكس - رافعة 50x
        "SAND/USDT",  # ذا ساندبوكس - رافعة 50x
        "MANA/USDT",  # ديسنترالاند - رافعة 50x
        "AXS/USDT",   # أكسي إنفينيتي - رافعة 50x
        "XLM/USDT",   # ستيلر - رافعة 50x
        "CHZ/USDT",   # تشيليز - رافعة 50x
        "POL/USDT",   # بوليجون (سابقاً MATIC) - رافعة 50x
        "FIL/USDT",   # فيل كوين - رافعة 50x
        "QNT/USDT",   # كوانت - رافعة 50x
        "DASH/USDT",  # داش - رافعة 50x
        "ZEC/USDT",   # زدكاش - رافعة 50x
        "XMR/USDT",   # مونيرو - رافعة 50x
#        "EOS/USDT"    # إيوس - رافعة 50x
    ]

# "ADA/USDT"
def scan_top_assets(exchange, n=None) -> List[str]:
    n = n or CFG.n_assets
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log.warning(f"scan_top_assets: {e}")
        return _default_assets()[:n]

    scored = []
    for sym, t in tickers.items():
        if not sym.endswith("/USDT"):
            continue
        base = sym.replace("/USDT","")
        if any(ex in base for ex in CFG.exclude_tokens):
            continue
        qv  = float(t.get("quoteVolume", 0) or 0)
        if qv < CFG.min_quote_vol_usd:
            continue
        chg = abs(float(t.get("percentage",0) or 0))
        scored.append((qv*(chg+1.0), sym))

    scored.sort(key=lambda x: -x[0])
    sel = [s for _,s in scored[:n]]
    if not sel:
        return _default_assets()[:n]
    log.info(f"مسح الأصول: {len(sel)} عملة مختارة")
    return sel

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
# § 2  جلب البيانات مع كاش (متوازٍ)
# ════════════════════════════════════════════════════════════════

def _load_cached(symbol, exchange, timeframe, days):
    fp  = os.path.join(CACHE_DIR, f"{symbol.replace('/','_')}_{timeframe}.parquet")
    min_rows = CFG.N + CFG.W + 100
    since_full = exchange.parse8601(
        (datetime.now(timezone.utc)-timedelta(days=days)).isoformat()+"Z")

    if os.path.exists(fp):
        df_old = pd.read_parquet(fp)
        if df_old.index.tz is None:
            df_old.index = pd.to_datetime(df_old.index, utc=True)
        last_ts = df_old.index.max()
        # ══ [TF-FIX] Use actual timeframe bar duration, not hardcoded 1h ══
        _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
        since   = exchange.parse8601(
            (last_ts+timedelta(seconds=_tf_sec)).isoformat()+"Z")
        rows = []
        try:
            while True:
                chunk = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
                if not chunk: break
                rows.extend(chunk); since = chunk[-1][0]+1; time.sleep(0.06)
        except Exception as e:
            log.warning(f"{symbol} update: {e}")
        if rows:
            df_new = pd.DataFrame(rows, columns=['ts','Open','High','Low','Close','Volume'])
            df_new['ts'] = pd.to_datetime(df_new['ts'], unit='ms', utc=True)
            df_new = df_new.set_index('ts').drop_duplicates().astype(float)
            df = pd.concat([df_old, df_new])
            df = df[~df.index.duplicated(keep='last')].sort_index()
        else:
            df = df_old
        if len(df) >= min_rows:
            df.to_parquet(fp); return df
        os.remove(fp)

    rows = []
    try:
        since = since_full
        while True:
            chunk = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not chunk: break
            rows.extend(chunk); since = chunk[-1][0]+1; time.sleep(0.06)
    except Exception as e:
        log.warning(f"{symbol} full fetch: {e}")
    if len(rows) < min_rows: return None
    df = pd.DataFrame(rows, columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').drop_duplicates().astype(float)
    df.to_parquet(fp); return df


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

def compute_dynamic_k(current_capital: float, adv_usd: np.ndarray) -> int:
    """
    التعديل ③: K(C) = max(K_MIN, floor(K_MAX · exp(-α · C/ADV)))
    
    الفيزياء: دقة القياس ∝ 1/كتلة_الجسيم
    رأس المال الكبير = جسيم ثقيل = K صغير (تجاهل الضجيج الصغير)
    رأس المال الصغير = جسيم خفيف = K كبير (رصد الفرص المجهرية)
    """
    adv_mean = float(np.mean(adv_usd[adv_usd > 0])) if np.any(adv_usd > 0) else 1e6
    capital_ratio = current_capital / (adv_mean + CFG.EPSILON)
    dynamic_k = int(np.floor(CFG.K_MAX * np.exp(-CFG.KQUANT_ALPHA * capital_ratio)))
    dynamic_k = max(CFG.K_MIN, min(CFG.K_MAX, dynamic_k))
    return dynamic_k


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
# § 10  نموذج الانزلاق (كايل)
# ════════════════════════════════════════════════════════════════

def apply_slippage(price, qty, adv_usd, action, mode="backtest"):
    """
    [تعديل التوصيل الفائق]: الانزلاق صفر لأننا نستخدم أوامر Limit (Maker).
    يتم تنفيذ السعر كما هو بالضبط دون احتكاك.
    """
    return price  # لا يوجد انزلاق (Zero Slippage)

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
    gauge_force: np.ndarray     # معيار اللاتناظرية لحقل المقياس F
    friction: np.ndarray        # الاحتكاك الإنتروبي Γ(S)
    delta_gap: np.ndarray       # فجوة التوازن الإحصائي Δ(n)
    geodesic_accel: np.ndarray  # التسارع الجيوديسي النهائي d/dτ(λ_dot)

@dataclass
class Signal:
    timestamp: pd.Timestamp; symbol: str; price: float; score: float
    action: str; sl: float; tp1: float; tp2: float; tp3: float
    atr: float; lam: float; close_idx: int; feat_idx: int
    adv_usd: float; tri_val: float
    dynamic_risk: float  # ← جديد: المخاطرة الديناميكية (التعديل ①)
    T_info_val: float    # ← جديد: درجة الحرارة عند الإشارة
    dyn_sl_factor: float = 0.1  # ← جديد: الوقف الديناميكي

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
    trail_dist_frac: float = 0.003       # ← جديد
    trail_activate_frac: float = 0.004   # ← جديد


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

def process_asset(symbol, df, km_ext=None, current_capital=None):
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
    adv_raw = pd.Series(vols*closes).rolling(24, min_periods=1).mean().values
    cap_now = current_capital if current_capital else CFG.INITIAL_CAPITAL
    dyn_k   = compute_dynamic_k(cap_now, adv_raw[:train_end+feat_start])
    # ══════════════════════════════════════════════════════════

    km = km_ext if km_ext else fit_kmeans(X[:train_end], k=dyn_k)
    sym_q = assign(X, km)

    H   = entropy_series(sym_q, k=dyn_k)
    dH  = np.diff(H,  prepend=H[0])
    d2H = np.diff(dH, prepend=dH[0])

    lr_full = np.diff(np.log(np.maximum(closes,1e-12)))
    E_therm = np.zeros(n)
    for i in range(n):
        ci = feat_start+i
        if ci >= N:
            w = lr_full[ci-N:ci]
            E_therm[i] = float(np.std(w,ddof=1)) if len(w)>=2 else 0.

    F  = E_therm - H
    dF = np.diff(F, prepend=F[0])

    # ══ التعديل ①: درجة الحرارة المعلوماتية ══════════════════
    T_info_raw = np.abs(dF / (np.abs(dH) + 1e-9))
    T_abs = E_therm * 400.0   # تضاعف التأثير
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

    h = np.ones(n, dtype=np.int32)
    h[dH >  CFG.DH_HMM_UPPER] = 0
    h[dH <  CFG.DH_HMM_LOWER] = 2

    # تقييم نقاط القوة بناءً على القوة الجيوديسية الصافية بدلاً من الترجيح الخطي العشوائي
    sc = np.zeros(n)
    sc += np.abs(geodesic_accel) * 10.0  
    sc += CFG.W_CURV    * (C > CFG.CURV_THRESHOLD).astype(float)
    sc += CFG.W_VOL     * (V < V_q20a).astype(float)
    sc += CFG.W_ENTROPY * ((dH < CFG.DH_ENTROPY_THRESHOLD) & (d2H < 0)).astype(float)
    sc += CFG.W_HMM     * ((h==2)|((h==0)&(dH<-CFG.DH_ENTROPY_THRESHOLD))).astype(float)
    sc += CFG.W_FREE_E  * (dF < CFG.DF_FREE_E_THRESHOLD).astype(float)
    # ══════════════════════════════════════════════════════════

    # ══ حساب EMA وتسارعه (التعديل ⑤) ════════════════════════
    ema200_series = pd.Series(closes).ewm(span=CFG.EMA_SPAN, adjust=False).mean().values
    ema_diff  = np.diff(ema200_series, prepend=ema200_series[0])
    ema_accel = np.diff(ema_diff,      prepend=ema_diff[0])
    # ══════════════════════════════════════════════════════════

    tr  = np.maximum(highs[1:]-lows[1:],
          np.maximum(np.abs(highs[1:]-closes[:-1]), np.abs(lows[1:]-closes[:-1])))
    tr  = np.concatenate([[tr[0]],tr])
    atr = pd.Series(tr).rolling(CFG.ATR_PERIOD, min_periods=1).mean().values
    adv = pd.Series(vols*closes).rolling(24, min_periods=1).mean().values

    ed  = compute_energy_dynamics(closes, lr_full, X, feat_start)
    KE  = ed['KE']; dKE = ed['dKE']
    PE  = compute_PE(X, km, H)
    ME  = KE+PE
    tri = compute_tri(dH, d2H, dF, dKE, ed['lya'])

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
        delta_gap=delta_gap, geodesic_accel=geodesic_accel
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


def compute_geodesic_stop(entry_price, ad, fi, cfg):
    """
    الطور الخامس: حساب الوقف بنصف قطر فيشر (Decoherence Edge).
    المسافة تتسع طردياً مع حجم عدم اليقين (V) وتتقلص مع الاحتكاك ولزوجة دفتر الأوامر.
    """
    # ad.V يمثل محدد مصفوفة التغاير (مقياس تشتت المعلومات)
    uncertainty = np.clip(ad.V[fi] / (np.mean(ad.V) + 1e-9), 0.5, 3.0)
    friction = float(ad.friction[fi]) + 1e-6
    
    # كلما قل الاحتكاك، زادت احتمالية الاختراق، فنضع وقفاً يتناسب عكسياً مع لزوجة السوق
    sl_pct = (0.012 * uncertainty) / (1.0 + friction * 5.0)
    sl_dist = entry_price * sl_pct
    
    # تقييد المسافة بين 0.5% و 5% من سعر الدخول لحماية الجسيم الصغير من الذيول الطارئة
    return float(np.clip(sl_dist, 0.005 * entry_price, 0.05 * entry_price))

def compute_dynamic_leverage(capital, cfg):
    """
    ③ الرافعة الديناميكية تتناقص مع نمو رأس المال:
    
    Lev(C) = LEVERAGE_BASE / √(C / C₀)
    
    فيزيائياً: الجسيم الأثقل (رأس مال أكبر) يتجاهل التقلبات الصغيرة
    → رافعة أقل تعني حماية أكثر عند نمو الثروة.
    """
    C0 = cfg.INITIAL_CAPITAL
    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))
    return int(np.clip(round(lev), cfg.LEVERAGE_MIN, cfg.LEVERAGE_MAX))

def build_signals(assets, mode="backtest"):
    """
    محرك استشعار الإشارات الكمي:
    1. Boltzmann Activation: يمرر القوة والحرارة لحساب احتمال حدوث الاختراق.
    2. Phase-Matched Entry: يضع أمر معلق Limit Maker عند نقطة سكون الهبوط المتوقعة.
    """
    sigs = []
    for sym, ad in assets.items():
        n = len(ad.score)
        for fi in range(ad.train_end+1, n):
            ci = ad.feat_start + fi
            
            # كسر سجن الزمن
            if mode == "backtest":
                if ci >= len(ad.closes) - 1: continue
            else:
                # Live: use only the last CLOSED candle.
                # In live data, closes[-1] is the currently-FORMING candle;
                # closes[-2] is the last CLOSED candle.
                # This matches backtest semantics exactly.
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

            # المزامنة الطورية: زخم السعر الميكروي السريع لتحديد اتجاه التدفق
            micro_momentum = p - ad.closes[ci - 1]
            if micro_momentum == 0: continue
            action = "BUY" if micro_momentum > 0 else "SELL"

            if ad.score[fi] < CFG.MIN_SCORE: continue

            # [التعديل ②]: Phase-Matched Entry (تجنب السكين الساقطة)
            # نضع أمر الـ Limit عند مستوى امتصاص الاحتكاك الميكروي (10% من معامل الاحتكاك الفعلي)
            friction_drag = fric_val * p * 0.1
            tunnel_entry_p = p - friction_drag if action == "BUY" else p + friction_drag
            
            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
            sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist
            tp1 = tunnel_entry_p + (sl_dist * 2.0) if action == "BUY" else tunnel_entry_p - (sl_dist * 2.0)
            
            # حظر الصفقات الهشة التي تكون تكلفتها أكبر من ربحها
            if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue

            dynamic_risk = compute_geodesic_kelly(ad, fi, CFG)

            sigs.append(Signal(
                timestamp=ad.timestamps[ci], symbol=sym, 
                price=tunnel_entry_p, # 🚀 الدخول معلق عند السعر الموزون طورياً
                score=float(ad.score[fi]), action=action,
                sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                dynamic_risk=dynamic_risk, T_info_val=T_info,
                dyn_sl_factor=sl_dist / tunnel_entry_p
            ))
            
    sigs.sort(key=lambda s: (s.timestamp, -s.score))
    return sigs

def deduplicate_signals(sigs):
    """
    TF-aware dedup: groups signals by (symbol, time bucket).
    The bucket is derived from CFG.TF_SECONDS so 1m/5m/1h all work correctly.
    """
    if not sigs:
        return sigs

    # Determine bucket label from TF_SECONDS
    tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
    if tf_sec <= 60:
        bucket = '1m'
    elif tf_sec <= 300:
        bucket = '5m'
    elif tf_sec <= 900:
        bucket = '15m'
    elif tf_sec <= 3600:
        bucket = '1h'
    elif tf_sec <= 14400:
        bucket = '4h'
    else:
        bucket = '1d'

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


# ════════════════════════════════════════════════════════════════
# § 15  محاكاة المحفظة (التعديلات ①②)
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# § 14.5  Precompute Realistic Entry Fills (Backtest Only)
# ════════════════════════════════════════════════════════════════

def precompute_entry_fills(assets, signals, max_wait_bars, pen_bps):
    """
    For each signal, find the bar index where the limit entry would ACTUALLY fill.
    A fill requires the market to PENETRATE the limit price by `pen_bps`.

    Deadline = min(sig.close_idx + max_wait_bars, next_signal_ci_for_same_symbol)
    so we never fill after the next signal has already superseded this one.

    Returns dict: signal_index → fill_ci | None
    """
    by_symbol = defaultdict(list)
    for i, s in enumerate(signals):
        by_symbol[s.symbol].append((i, s))

    pen_frac = pen_bps * 1e-4
    result = {}

    for sym, sig_list in by_symbol.items():
        if sym not in assets:
            for idx, _ in sig_list:
                result[idx] = None
            continue
        ad = assets[sym]
        n_bars = len(ad.closes)

        for j, (sig_i, sig) in enumerate(sig_list):
            # Deadline
            deadline = min(sig.close_idx + max_wait_bars, n_bars - 1)
            if j + 1 < len(sig_list):
                next_sig = sig_list[j + 1][1]
                deadline = min(deadline, next_sig.close_idx)

            start = sig.close_idx + 1
            if start >= deadline:
                result[sig_i] = None
                continue

            target = sig.price
            fill_ci = None

            if sig.action == "BUY":
                need_low = target * (1.0 - pen_frac)
                window = ad.lows[start:deadline]
                idx = np.where(window <= need_low)[0]
                if len(idx) > 0:
                    fill_ci = start + int(idx[0])
            else:  # SELL
                need_high = target * (1.0 + pen_frac)
                window = ad.highs[start:deadline]
                idx = np.where(window >= need_high)[0]
                if len(idx) > 0:
                    fill_ci = start + int(idx[0])

            result[sig_i] = fill_ci

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

def _advance(pos, ad, to_ci):
    """
    Walk bars from current_ci+1 to to_ci.
    - SL / TP require penetration by FILL_PENETRATION_BPS.
    - Time-based exits (Apex, Topo-Div, MaxHold) use close price.
    """
    sig = pos.signal
    trail_sl = pos.trail_sl
    start = pos.current_ci + 1
    end = min(to_ci, len(ad.closes) - 1)

    # Nothing to advance (e.g., entry_ci is in the future relative to to_ci)
    if start > end:
        return 0., "", -1

    pen_frac = CFG.FILL_PENETRATION_BPS * 1e-4 if CFG.FILL_APPLY_TO_EXITS else 0.0

    for cidx in range(start, end+1):
        p = ad.closes[cidx]
        high = ad.highs[cidx]
        low  = ad.lows[cidx]
        fi = cidx - ad.feat_start

        # ── Update MFE (max favorable excursion) ──
        if sig.action == "BUY":
            mfe_cand = (high - pos.entry_px) / pos.entry_px
        else:
            mfe_cand = (pos.entry_px - low) / pos.entry_px
        if mfe_cand > pos.mfe_frac:
            pos.mfe_frac = mfe_cand

        # ── Trailing Stop (protection layer, runs parallel to Apex) ──
        # Uses per-position volatility-scaled parameters
        _td = pos.trail_dist_frac if pos.trail_dist_frac > 0 else CFG.TRAIL_DISTANCE
        _ta = pos.trail_activate_frac if pos.trail_activate_frac > 0 else CFG.TRAIL_ACTIVATE_MFE

        if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta:
            if sig.action == "BUY":
                peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                if high > peak:
                    peak = high
                    pos.peak_price = peak
                new_sl = peak * (1.0 - _td)
                if new_sl > trail_sl * (1.0 + CFG.TRAIL_MIN_STEP):
                    trail_sl = new_sl
            else:  # SELL
                peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                if low < peak or peak == 0:
                    peak = low
                    pos.peak_price = peak
                new_sl = peak * (1.0 + _td)
                if new_sl < trail_sl * (1.0 - CFG.TRAIL_MIN_STEP):
                    trail_sl = new_sl

        # 1. Apex (close-based, no penetration)
        is_apex, apex_rsn = check_thermodynamic_apex(
            sig.action, pos.entry_px, p, ad, fi
        )
        if is_apex:
            pos.trail_sl = trail_sl; pos.current_ci = cidx
            return p, apex_rsn, cidx

        # 2. Topo-Div (close-based)
        if 0 < fi < len(ad.V) and cidx > 0:
            V_curr  = ad.V[fi]
            V_prev  = ad.V[fi - 1] if fi > 0 else V_curr
            div_t   = (V_curr - V_prev) / (V_prev + 1e-12)
            dH_curr = ad.dH[fi] if fi < len(ad.dH) else 0.
            if div_t > CFG.TOPO_DIV_THRESHOLD and dH_curr > 0:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return p, f"Topo-Div({div_t:.3f})", cidx

        # 3. MaxHold (close-based)
        # ══ [TF-FIX] scale bar-count to preserve real-time duration ══
        if cidx - pos.entry_ci > effective_bars(CFG.MAX_HOLD_BARS):
            pos.trail_sl = trail_sl; pos.current_ci = cidx
            return p, "MaxHold", cidx

        # 4. SL / TP with PENETRATION
        if sig.action == "BUY":
            # SL (stop order): trigger when low pierces SL
            sl_trigger = trail_sl * (1.0 - pen_frac)
            if low <= sl_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return trail_sl, "Emergency SL", cidx
            # TP (limit order): fill when high pierces TP
            tp_trigger = sig.tp1 * (1.0 + pen_frac)
            if high >= tp_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return sig.tp1, "Hard TP", cidx
        else:  # SELL
            sl_trigger = trail_sl * (1.0 + pen_frac)
            if high >= sl_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return trail_sl, "Emergency SL", cidx
            tp_trigger = sig.tp1 * (1.0 - pen_frac)
            if low <= tp_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return sig.tp1, "Hard TP", cidx

    pos.trail_sl = trail_sl
    pos.current_ci = max(end, pos.current_ci)
    return 0., "", -1


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
        except Exception:
            pass
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
    fill_map = precompute_entry_fills(
        assets, signals,
        max_wait_bars=effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS),   # ══ [TF-FIX]
        pen_bps=CFG.FILL_PENETRATION_BPS,
    )
    n_total_sigs = len(signals)
    n_would_fill = sum(1 for v in fill_map.values() if v is not None)
    log.info(f"  [Backtest Realism] Entry fills: "
             f"{n_would_fill:,}/{n_total_sigs:,} "
             f"({100*n_would_fill/max(n_total_sigs,1):.1f}%) "
             f"[pen={CFG.FILL_PENETRATION_BPS}bps, "
             f"wait={CFG.FILL_ENTRY_MAX_WAIT_BARS}bars]")

    def _close(pos, ad, exit_px, exit_rsn, exit_ci):
        nonlocal capital, peak_cap
        sig         = pos.signal
        exit_act    = "SELL" if sig.action=="BUY" else "BUY"
        adv_here    = ad.adv_usd[min(exit_ci, len(ad.adv_usd)-1)]
        exit_eff    = apply_slippage(exit_px, pos.pos_size, adv_here, exit_act, mode)
        slip_x      = abs(exit_eff-exit_px)*pos.pos_size

        if sig.action=="BUY": 
            gross = (exit_eff - pos.entry_px) * pos.pos_size
        else:                  
            gross = (pos.entry_px - exit_eff) * pos.pos_size

        # رسوم الصانع المعكوسة (نربح عمولة توفير السيولة Maker Rebate)
        fee  = pos.pos_size * (pos.entry_px + exit_eff) * CFG.MAKER_FEE
        
        # رسوم التمويل الزمنية
        # ══ [FUNDING FIX] Apply to both BUY and SELL (conservative) ══
        hold_bars = exit_ci - pos.entry_ci
        funding_payments = max(0, hold_bars) // CFG.FUNDING_INTERVAL_BARS
        # Both directions pay the same rate in this conservative model.
        # (In reality, shorts may receive or pay depending on funding sign.)
        funding_cost = pos.pos_size * pos.entry_px * CFG.FUNDING_RATE_COST * funding_payments

        net  = gross - fee - slip_x - funding_cost
        cap0 = pos.entry_cap
        capital = max(capital+net, 0.)
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
            mfe_frac=pos.mfe_frac   # ← أضف هذا السطر
        ))

    for sig_i, sig in enumerate(signals):
        # حاجز أمان مطلق: يستحيل بدء تداول جديد إذا اقترب الجسيم من عتبة الفناء (5.1$)
        if capital <= CFG.CAPITAL_FLOOR + 0.1:
            break

        # 1. تحديث ومراقبة الفضاء للمراكز المفتوحة (التقدم في الزمكان)
        to_close = []
        for sym, pos in open_pos.items():
            ad   = assets[sym]
            toci = _ts_to_ci(ad, sig.timestamp)
            ep, er, ec = _advance(pos, ad, toci)
            if ep > 0:
                _close(pos, ad, ep, er, ec)
                to_close.append(sym)
                # ══ [RE-ENTRY COOLDOWN] Record exit bar ══
                last_exit_ci[sym] = int(ec)
        for sym in to_close:
            del open_pos[sym]

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

        # ══ [BACKTEST REALISM] Look up actual fill bar ══
        fill_ci = fill_map.get(sig_i)
        if fill_ci is None:
            # Order never penetrated — skip this signal entirely
            continue

        # 🚀 التوافق السببي: الدخول يتم عند الشمعة التي اخترق فيها السوق السعر
        opt_ci = fill_ci
        opt_px = sig.price  # limit order fills exactly at limit (conservative)
        opt_entry = False

        # مسافة الوقف الجيوديسي المحددة مسبقاً في الإشارة
        sl_distance = abs(sig.price - sig.sl)
        
        if sig.action == "BUY":
            sl_h = opt_px - sl_distance
        else:
            sl_h = opt_px + sl_distance
            
        delta = abs(opt_px - sl_h)
        if delta < 1e-8: continue

        # ══ [PORTFOLIO RISK BUDGET] ══
        # Portfolio-coordinated sizing: heat budget + fair share + strength weighting
        free_ratio = max(0.0, (capital - CFG.CAPITAL_FLOOR) / capital)
        power_law_scale = np.sqrt(free_ratio)

        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)
        if risk_frac <= 0.0:
            log.debug(f"[Budget] {sym} skipped: no heat budget available")
            continue

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
        dynamic_leverage = compute_dynamic_leverage(capital, CFG)
        max_notional = capital * dynamic_leverage
        qty = min(qty, max_notional / opt_px)

        # ══ [NOTIONAL CAP] ══
        qty = cap_notional(qty, opt_px)

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
        )

    for sym, pos in list(open_pos.items()):
        ad = assets[sym]
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
    print(f"\n{sep}\n")
    


def plot_results(trades, equity, m, out="quantum_v6_results.png"):
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
    for k, v in cfg_dict.items():
        try:
            setattr(CFG, k, v)
        except Exception:
            pass


def _process_asset_worker(args):
    """
    Top-level worker for ProcessPoolExecutor.
    Returns: (sym, AssetData | None, err | None, source ∈ {'cache','computed'})
    """
    sym, df, cap, timeframe, cfg_dict = args

    # Restore CFG in child (needed for spawn/forkserver; harmless on fork)
    for k, v in cfg_dict.items():
        try:
            setattr(CFG, k, v)
        except Exception:
            pass

    # 1. Try cache
    ad = _load_asset_cache(sym, timeframe, df, CFG)
    if ad is not None:
        return (sym, ad, None, 'cache')

    # 2. Compute fresh
    try:
        ad = process_asset(sym, df, current_capital=cap)
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
    raw = fetch_all(syms, exchange, cfg.timeframe, cfg.history_days, workers=5)
    if not raw: log.error("لا بيانات."); return

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
            (sym, df, cfg.INITIAL_CAPITAL, cfg.timeframe, cfg_dict)
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

            for fut, (sym, df, *_rest) in zip(futures, tasks):
                pass  # placeholder — we'll iterate differently below

            # Iterate with symbol association so we can retry failed ones serially
            fut_to_sym = {ex.submit(_process_asset_worker, t): t[0] for t in tasks}
            # NOTE: we already submitted above; reconstruct the mapping is unnecessary
            # since we track via as_completed. Instead: use a dict keyed by future.

            # The original submission above already exists; here we re-iterate results:
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
                ad = process_asset(sym, df, current_capital=cfg.INITIAL_CAPITAL)
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
    sigs = build_signals(assets)
    sigs = deduplicate_signals(sigs)

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

    m = compute_metrics(trades, equity, cfg.INITIAL_CAPITAL)

    log.info("§7  انحدار الإنتروبيا...")
    for sym, ad in list(assets.items())[:4]:
        H_t = ad.H[ad.train_end:]
        if len(H_t)>10:
            r = entropy_regression(H_t)
            log.info(f"  {sym:14s}: b={r['slope']:+.5f}  R²={r['r2']:.3f}  [{r['trend']}]")

    print_report(m, "backtest")
    plot_results(trades, equity, m)
    log.info("✅ اكتمل.")
    log.info(f"   E[ln(1+fR)] = {m.get('mean_log_return',0):+.6f}")
    log.info(f"   MaxDrawdown  = {m.get('max_drawdown_pct',0):.2f}%")
    log.info(f"   Topo-Exits   = {m.get('topo_exit_pct',0):.1f}%")
    log.info(f"   AvgRisk      = {m.get('avg_dynamic_risk',0)*100:.3f}%")
    # ══ [MFE Analysis] ══
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
        except Exception:
            pass
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
        except Exception:
            pass

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
            except Exception:
                pass
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

# ════════════════════════════════════════════════════════════════
# § 18.5  بروتوكول مايسنر لمنع الانزلاق (Quantum Chunking)
# ════════════════════════════════════════════════════════════════
def execute_post_only(exchange, symbol: str, side: str, qty: float,
                      penetration_bps: float = None,
                      max_wait_s: int = None,
                      reprice_s: float = None,
                      fallback_market: bool = False,
                      fixed_target: Optional[float] = None):
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
    active = None           # {'id','price','qty','counted_fill','counted_cost','terminal'}
    total_filled = 0.0
    total_cost = 0.0
    remaining = qty
    attempts = 0
    last_bid = 0.0
    last_ask = 0.0

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

            # 2. Target
            # Defensive: if PO_FIXED_PRICE is True but caller didn't pass
            # fixed_target, lock the FIRST observed target and never chase.
            _fixed = (fixed_target is not None and fixed_target > 0)
            if _fixed:
                target = float(fixed_target)
            elif getattr(CFG, 'PO_FIXED_PRICE', False):
                # Lock target on first iteration
                if not hasattr(execute_post_only, '_locked_target'):
                    execute_post_only._locked_target = {}
                lock_key = f"{symbol}:{side}"
                if lock_key not in execute_post_only._locked_target:
                    execute_post_only._locked_target[lock_key] = (
                        last_bid * (1.0 - pen) if side == 'buy'
                        else last_ask * (1.0 + pen)
                    )
                target = execute_post_only._locked_target[lock_key]
                _fixed = True
            else:
                target = (last_bid * (1.0 - pen)) if side == 'buy' \
                         else (last_ask * (1.0 + pen))

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
                        except Exception:
                            pass
                        active = None
                        break
                    # REPLACE
                    try:
                        exchange.cancel_order(active['id'], symbol)
                    except Exception:
                        pass
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
                    o = exchange.create_order(
                        symbol, 'limit', side, remaining, target,
                        params={'timeInForce': 'GTX'}
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
                except Exception:
                    pass
                time.sleep(0.3)
                _refresh_active()
            active = None

        # ── Result ──
        if total_filled <= 0:
            if fallback_market:
                try:
                    mp = last_ask if side == 'buy' else last_bid
                    o = exchange.create_order(symbol, 'market', side, qty)
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
        except Exception:
            pass  # trades are optional
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
            except Exception:
                pass

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
                    pass  # drop
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
    global _SYMBOL_META
    meta = _SYMBOL_META.get(sym, {})

    # Fast path: already set up with matching leverage
    if meta.get('setup_done') and int(meta.get('leverage', 0)) == target_leverage:
        return True

    # 1. Check for existing position
    has_pos = False
    try:
        positions = exchange.fetch_positions([sym])
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
            confirmed = int(lev_info.get('leverage', target_leverage))
            if confirmed != target_leverage:
                log.warning(f"[Setup] {sym} leverage mismatch: "
                            f"got {confirmed}x, wanted {target_leverage}x")
        except Exception:
            pass

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
        except Exception:
            pass
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


def load_pending_orders(mode: str) -> Dict[str, Dict]:
    """Restore pending orders from disk."""
    global _PENDING_ORDERS, _PENDING_ORDERS_PATH
    _PENDING_ORDERS_PATH = f"{CFG.PENDING_FILE_PREFIX}_{mode}.json"
    if os.path.exists(_PENDING_ORDERS_PATH):
        try:
            with open(_PENDING_ORDERS_PATH) as f:
                _PENDING_ORDERS = json.load(f)
            log.info(f"[Pending] Restored {len(_PENDING_ORDERS)} pending orders")
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
        with open(tmp, 'w') as f:
            json.dump(_PENDING_ORDERS, f, indent=2, default=str)
        os.replace(tmp, _PENDING_ORDERS_PATH)
    except Exception as e:
        log.warning(f"[Pending] save failed: {e}")


def _pending_drop_stale(max_age_s: float = 3600.0) -> int:
    """Remove pending entries older than max_age_s (safety)."""
    now = time.time()
    removed = 0
    for sym in list(_PENDING_ORDERS.keys()):
        rec = _PENDING_ORDERS[sym]
        if now - float(rec.get('placed_at', 0.0)) > max_age_s:
            oid = rec.get('order_id')
            if oid:
                try:
                    # best-effort cancel
                    pass
                except Exception:
                    pass
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


def _promote_pending_to_position(sym: str, rec: Dict,
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
    max_sl_frac = 0.015
    if orig_sl_dist > entry_price * max_sl_frac:
        orig_sl_dist = entry_price * max_sl_frac
        orig_tp_dist = orig_sl_dist * rr

    if rec['action'] == 'BUY':
        adapted_sl = entry_price - orig_sl_dist
        adapted_tp = entry_price + orig_tp_dist
    else:
        adapted_sl = entry_price + orig_sl_dist
        adapted_tp = entry_price - orig_tp_dist

    # σ-scaled trailing params at entry
    trail_d, trail_a = (0.003, 0.004)
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
    }
    log.info(
        f"✅ [Pending→Entry] {rec['action']} {sym} @ {entry_price:.6f} "
        f"qty={filled_qty:.6f} (fill={fill_ratio*100:.0f}%) "
        f"sl={adapted_sl:.6f} tp={adapted_tp:.6f}"
    )
    return True


def monitor_pending_orders(exchange, open_pos_live: Dict,
                           loop_iter: int = 0) -> None:
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

        # ── Terminal: filled → promote ──
        if status == 'closed':
            filled = float(rec.get('filled') or 0.0)
            total = float(rec.get('qty') or 0.0)
            if total > 0 and filled >= total * 0.98:
                ok = _promote_pending_to_position(sym, rec, open_pos_live)
                if not ok:
                    log.info(f"[Pending] {sym} dropped after non-promotable fill")
                _PENDING_ORDERS.pop(sym, None)
            else:
                # Partial close on exchange side; treat as filled and adapt
                ok = _promote_pending_to_position(sym, rec, open_pos_live)
                if not ok:
                    log.info(f"[Pending] {sym} dropped after partial fill")
                _PENDING_ORDERS.pop(sym, None)
            continue

        # ── Terminal: canceled/expired/rejected → drop ──
        if status in ('canceled', 'expired', 'rejected'):
            log.info(f"[Pending] {sym} {rec.get('action')} → {status}")
            _PENDING_ORDERS.pop(sym, None)
            continue

        # ── Timeout → cancel + drop ──
        timeout_s = float(rec.get('timeout_s') or CFG.PO_MAX_WAIT_S)
        elapsed = now - float(rec.get('placed_at') or now)
        if elapsed > timeout_s:
            oid = rec.get('order_id')
            if oid:
                try:
                    exchange.cancel_order(oid, sym)
                except Exception:
                    pass
                time.sleep(0.2)
                # Final sweep
                _sweep_pending_once(exchange, sym)
                rec2 = _PENDING_ORDERS.get(sym)
                if rec2 and str(rec2.get('status')) == 'closed':
                    _promote_pending_to_position(sym, rec2, open_pos_live)
            log.info(f"[Pending] {sym} {rec.get('action')} timeout "
                     f"({elapsed:.0f}s > {timeout_s:.0f}s)")
            _PENDING_ORDERS.pop(sym, None)
            continue


def place_pending_entry(exchange, sym: str, side: str, qty: float,
                        sig, timeout_s: float, leverage: int,
                        ad=None) -> Optional[Dict]:
    """
    Place a single Post-Only order and register it as pending (non-blocking).
    Returns the pending record or None on failure.
    """
    target = float(sig.price)
    try:
        o = exchange.create_order(
            sym, 'limit', side, qty, target,
            params={'timeInForce': 'GTX'}
        )
    except Exception as e:
        log.debug(f"[Pending] {sym} GTX rejected @ {target:.6f}: {e}")
        return None

    entry_fi = 0
    try:
        if ad is not None:
            entry_fi = max(0, min(sig.feat_idx, len(ad.E_therm) - 1))
    except Exception:
        entry_fi = 0

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
        # NOTE: ad_ref is intentionally NOT serialized; it is lost on restart.
        # On restart, trail params fall back to defaults.
        'ad_ref': ad,
    }
    _PENDING_ORDERS[sym] = rec
    log.info(f"[Pending] {sig.action} {sym} @ {target:.6f} qty={qty:.6f} "
             f"id={rec['order_id']} (timeout={timeout_s:.0f}s)")
    return rec

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
        except Exception as e:
            log.warning(f"  [State] load failed: {e}")

    # ══ [State] Load persistent symbol metadata (leverage/margin/setup) ══
    load_symbol_meta(cfg.mode)
    # ══ [Pending] Load persisted pending orders ══
    load_pending_orders(cfg.mode)
    _stale = _pending_drop_stale(max_age_s=max(3600.0, CFG.PO_MAX_WAIT_S * 4))
    if _stale > 0:
        log.info(f"[Pending] Dropped {_stale} stale entries on startup")
    log.info(f"  [Pending] Active pending orders: {len(_PENDING_ORDERS)}")

    # ══ [State] Initial reconciliation with exchange ══
    _pre_syms = list(open_pos_live.keys()) or scan_top_assets(exchange)
    open_pos_live = reconcile_state_machine(exchange, open_pos_live, _pre_syms)
    log.info(f"  [State] After initial sync: {len(open_pos_live)} positions")

    # ══ [RE-ENTRY COOLDOWN] track last exit time per symbol ══
    last_exit_time: Dict[str, float] = {}

    corr_cache: Dict = {}

    log.info("⏳ جلب الزمكان المالي التاريخي (هذه العملية تحدث مرة واحدة فقط)...")
    top_syms = scan_top_assets(exchange)
    cached_data = fetch_all(top_syms, exchange, cfg.timeframe, days=60, workers=5)

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
            loop_iter += 1

            # ══ [Pending] Sweep pending orders every cycle ══
            try:
                monitor_pending_orders(exchange, open_pos_live, loop_iter)
            except Exception as _e:
                log.warning(f"[Pending] monitor error: {_e}")
            
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
                cap_live = float(bal['USDT']['free'])
                _last_known_cap = cap_live
            except Exception as e:
                log.warning(f"[Balance] fetch failed ({e}); using last known "
                            f"${_last_known_cap:.2f}")
                cap_live = _last_known_cap

            peak_cap_live = max(peak_cap_live, cap_live)
            if int(time.time() / 60) % 5 == 0:  # once per 5 minutes
                open_pos_live = reconcile_positions(exchange, open_pos_live)
            assets = {}
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
                        if ad is None:
                            ad = process_asset(sym, cached_data[sym],
                                                current_capital=cap_live)
                            if ad is not None:
                                _live_cache_put(sym, cfg.timeframe, _lc_ts, ad)
                        if ad:
                            assets[sym] = ad
                        continue

                    new_candles = exchange.fetch_ohlcv(sym, cfg.timeframe, limit=3)
                    _ohlcv_fetched += 1
                    df_new = pd.DataFrame(new_candles, columns=['ts','Open','High','Low','Close','Volume'])
                    df_new['ts'] = pd.to_datetime(df_new['ts'], unit='ms', utc=True)
                    df_new = df_new.set_index('ts').astype(float)
                    df_combined = pd.concat([cached_data[sym], df_new])
                    cached_data[sym] = df_combined[~df_combined.index.duplicated(keep='last')].sort_index().tail(cfg.N + cfg.W + 1000)

                    # ══ [LIVE CACHE] Look up by (sym, tf, last_closed_ts) ══
                    _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                    _lc_ts = _last_closed_bar_ts(cached_data[sym], _tf_sec)
                    _current_last_closed[sym] = _lc_ts

                    ad = _live_cache_get(sym, cfg.timeframe, _lc_ts)
                    if ad is None:
                        ad = process_asset(sym, cached_data[sym], current_capital=cap_live)
                        if ad is not None:
                            _live_cache_put(sym, cfg.timeframe, _lc_ts, ad)
                    if ad: assets[sym] = ad
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
                if sym not in assets: continue

                ad = assets[sym]
                fi = len(ad.score) - 1

                price = ad.closes[-1]
                ex = False
                rsn = ""

                # ── Apex ──
                is_apex, apex_rsn = check_thermodynamic_apex(
                    pos['action'], pos['entry'], price, ad, fi
                )
                if is_apex:
                    ex = True; rsn = apex_rsn

                # ── Topo-Div ──
                if not ex and fi > 0:
                    div_t = (ad.V[fi] - ad.V[fi-1]) / (ad.V[fi-1] + 1e-12)
                    if div_t > cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0:
                        ex = True; rsn = f"Topo-Div({div_t:.3f})"

                # ── MaxHold ──
                if not ex:
                    entry_ts = pos.get('entry_ts', 0)
                    if entry_ts > 0:
                        # ══ [TF-FIX] use TF_SECONDS instead of if-else on 1m/1h ══
                        tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                        bars_held = (time.time() - entry_ts) / tf_sec
                        if bars_held > effective_bars(cfg.MAX_HOLD_BARS):
                            ex = True
                            rsn = f"MaxHold({int(bars_held)}bars)"

                # ── Trailing SL (dynamic σ-scaled) ──
                if not ex:
                    entry_px = pos['entry']
                    _td = float(pos.get('trail_dist_frac', CFG.TRAIL_DISTANCE))
                    _ta = float(pos.get('trail_activate_frac', CFG.TRAIL_ACTIVATE_MFE))

                    # Update peak from live price
                    if pos['action'] == "BUY":
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price > cur_peak:
                            pos['peak_price'] = price
                            cur_peak = price
                        if (cur_peak - entry_px) / entry_px >= _ta:
                            new_sl = cur_peak * (1.0 - _td)
                            if new_sl > pos['sl']:
                                pos['sl'] = new_sl
                    else:
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price < cur_peak or cur_peak == entry_px:
                            pos['peak_price'] = price
                            cur_peak = price
                        if (entry_px - cur_peak) / entry_px >= _ta:
                            new_sl = cur_peak * (1.0 + _td)
                            if new_sl < pos['sl']:
                                pos['sl'] = new_sl

                # ── SL / TP ──
                if not ex:
                    if pos['action'] == "BUY":
                        if price <= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price >= pos.get('tp1', 1e18): ex = True; rsn = "Hard TP"
                    else:
                        if price >= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price <= pos.get('tp1', 0.): ex = True; rsn = "Hard TP"

                if not ex:
                    continue

                # ── Execute exit ──
                try:
                    s = 'sell' if pos['action'] == 'BUY' else 'buy'
                    is_emergency = 'Emergency' in rsn

                    if is_emergency:
                        # Emergency → market directly
                        try:
                            o = exchange.create_order(sym, 'market', s, pos['qty'])
                            v = verify_fill(exchange, o['id'], sym, timeout_s=1.5)
                            exec_price = v['avg_price'] if v and v['filled'] else price
                            exit_reason = f"{rsn} (market)"
                        except Exception as e:
                            log.error(f"[Exit] market failed {sym}: {e}")
                            continue
                    else:
                        # ══ [TF-FIX] use actual bar duration ══
                        _tf_sec_wait = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
#                        result = execute_limit_wait(
#                            exchange, sym, sd, qty, sig.price,
#                            wait_s=CFG.FILL_ENTRY_MAX_WAIT_BARS * _tf_sec_wait
#                        )
                        result = execute_post_only(
                            exchange, sym, s, pos['qty'],
                            max_wait_s=CFG.PO_EXIT_MAX_WAIT_S,
                            fallback_market=CFG.PO_EXIT_FALLBACK_MARKET,
                        )

                        if not result['filled_qty'] or result['filled_qty'] <= 0:
                            log.warning(f"⚠️ [Exit] {sym} no fill "
                                        f"({result['reason']}) — retry next loop")
                            continue
                        exec_price = result['avg_price']
                        exit_reason = f"{rsn} ({result['reason']})"

                    del open_pos_live[sym]
                    # ══ [RE-ENTRY COOLDOWN] record exit time ══
                    last_exit_time[sym] = time.time()
                    log.info(f"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]")
                except Exception as e:
                    log.error(f"خطأ أثناء الإغلاق لـ {sym}: {e}")

            # 2. اقتناص ودخول صفقات جديدة
            # ══ [SAFETY] Dynamic concurrent limit based on drawdown ══
            dd_live = (peak_cap_live - cap_live) / (peak_cap_live + 1e-12)
            if dd_live > 0.10:
                effective_max = max(1, cfg.MAX_CONCURRENT_ASSETS // 2)
            elif dd_live > 0.05:
                effective_max = max(2, cfg.MAX_CONCURRENT_ASSETS - 1)
            else:
                effective_max = cfg.MAX_CONCURRENT_ASSETS

            if len(open_pos_live) < effective_max:
                # توليد الإشارة يمرر وضعية التداول اللحظية لكسر وهم الزمن
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

                for sig in reversed(sigs):
                    sym = sig.symbol
                    if sym in open_pos_live: continue
                    if len(open_pos_live) >= cfg.MAX_CONCURRENT_ASSETS: break

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
                    
                    # 🚀 التزامن السببي: السعر المستهدف للدخول هو سعر النفق المعلق مباشرة
                    lmt = sig.price 
                    delta = abs(lmt - sig.sl)
                    if delta < 1e-8: continue
                    if cap_live <= cfg.CAPITAL_FLOOR + 0.1: continue
                    
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
                        log.debug(f"[Budget] {sym} skipped: no heat budget")
                        continue

                    risk_frac *= power_law_scale
                    risk_frac = float(np.clip(risk_frac,
                                                CFG.MIN_RISK_PER_TRADE if CFG.BUDGET_ENABLED else CFG.MIN_RISK,
                                                CFG.MAX_RISK_PER_TRADE if CFG.BUDGET_ENABLED else CFG.MAX_RISK))

                    equity_base = max(cap_live - cfg.CAPITAL_FLOOR, 0.0)
                    risk_amt = equity_base * risk_frac

                    qty_risk_based = risk_amt / delta

                    dynamic_leverage = compute_dynamic_leverage(cap_live, cfg)
                    max_notional = cap_live * dynamic_leverage
                    qty_leverage_based = max_notional / lmt

                    qty = min(qty_risk_based, qty_leverage_based)

                    # ══ [NOTIONAL CAP] ══
                    qty = cap_notional(qty, lmt)

                    if qty * lmt < cfg.MIN_NOTIONAL:
                        continue

                    # Store effective risk for heat tracking
                    sig.dynamic_risk = float(risk_frac)
                    
                    try:
                        sd = 'buy' if sig.action == 'BUY' else 'sell'

                        # ══ 1. Setup ONCE — leverage/margin ══
                        if not ensure_symbol_setup(exchange, sym, dynamic_leverage,
                                                    margin_mode='isolated'):
                            log.warning(f"[Entry] {sym} setup failed — skip")
                            continue

                        # ══ 2. Anti-stacking: cancel stale entry orders ══
                        try:
                            for o in exchange.fetch_open_orders(sym):
                                if o['side'] == sd:
                                    try:
                                        exchange.cancel_order(o['id'], sym)
                                    except Exception:
                                        pass
                        except Exception:
                            pass

                        # ══ 3. Entry — Non-Blocking Pending Order ══
                        if getattr(CFG, 'PENDING_ENABLED', True):
                            # Respect cap on placements per cycle
                            if len(_PENDING_ORDERS) >= int(CFG.MAX_CONCURRENT_ASSETS):
                                log.debug(f"[Pending] cap reached, skipping {sym}")
                                continue

                            # ══ [Parity] Entry timeout = bars × bar-duration ══
                            _tf_sec_w = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                            _bars_wait = int(effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS))
                            _timeout_s = float(_bars_wait * _tf_sec_w)
                            # Optional hard cap from PO_MAX_WAIT_S if > 0
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
                                log.info(f"[Pending] {sym} rejected by exchange — skip")
                                continue
                            # Persist immediately; promotion happens in monitor
                            try:
                                save_pending_orders()
                            except Exception:
                                pass
                            # Do NOT register in open_pos_live here.
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
                        max_sl_frac = 0.015
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
                            'leverage': _SYMBOL_META.get(sym, {}).get('leverage', dynamic_leverage),
                            'trail_dist_frac': trail_d,
                            'trail_activate_frac': trail_a,
                        }

                        log.info(f"✅ [Entry] {sig.action} {sym} @ {entry_price:.6f} "
                                 f"qty={actual_qty:.6f} (fill={fill_ratio*100:.1f}%) "
                                 f"sl={adapted_sl:.6f} tp={adapted_tp:.6f} "
                                 f"lev={_SYMBOL_META.get(sym, {}).get('leverage', '?')}x")

                        # ══ 7. Persist immediately ══
                        try:
                            with open(state_file, 'w') as f:
                                json.dump(open_pos_live, f, indent=2)
                        except Exception:
                            pass

                    except Exception as e:
                        log.error(f"[Entry] {sym} exception: {e}")

            # ══ Periodic reconcile (every RECONCILE_INTERVAL_S) ══
            if not hasattr(run_live, '_last_reconcile'):
                run_live._last_reconcile = 0.0
            if time.time() - run_live._last_reconcile > CFG.RECONCILE_INTERVAL_S:
                open_pos_live = reconcile_state_machine(
                    exchange, open_pos_live, top_syms
                )
                run_live._last_reconcile = time.time()

            # ══ Persist state ══
            try:
                with open(state_file, 'w') as f:
                    json.dump(open_pos_live, f, indent=2)
            except Exception:
                pass
            save_pending_orders()
            save_symbol_meta()
            
            # استرخاء المحرك للمزامنة الزمنية
            sleep_time = max(0, cfg.LIVE_POLL_SECS - (time.time() - t0))
            time.sleep(sleep_time)
            
        except KeyboardInterrupt: 
            log.info("تم إيقاف الروبوت يدوياً.")
            break
        except Exception as e: 
            log.error(f"خطأ غير متوقع في حلقة التداول: {e}")
            time.sleep(10)


# ════════════════════════════════════════════════════════════════
# § 20  نقطة الدخول
# ════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Quantum Thermo Trader v6.0 – Singularity Engine")
    p.add_argument("--mode",        default="backtest", choices=["backtest","testnet","live"])
    p.add_argument("--api-key",     default=os.environ.get("BINANCE_API_KEY",""))
    p.add_argument("--api-secret",  default=os.environ.get("BINANCE_API_SECRET",""))
    p.add_argument("--capital",     type=float, default=None)
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
    args = p.parse_args()

    CFG.mode = args.mode
    CFG.api_key = args.api_key
    CFG.api_secret = args.api_secret
    if args.capital   is not None: CFG.INITIAL_CAPITAL = args.capital
    if args.base_risk is not None: CFG.BASE_RISK = args.base_risk; CFG.RISK_PER_TRADE = args.base_risk
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
    if args.po_pen_bps is not None:  CFG.PO_PENETRATION_BPS = args.po_pen_bps
    if args.po_wait_s is not None:   CFG.PO_MAX_WAIT_S = args.po_wait_s
    if args.heat_max is not None: CFG.PORTFOLIO_HEAT_MAX = args.heat_max
    if args.no_numba: CFG.NUMBA_ENABLED = False

    # ══ [Level-2] Compile Numba kernels before starting ══
    _warmup_numba_kernels()
    if args.nassets     is not None: CFG.n_assets = args.nassets
    if args.maxcon     is not None: CFG.MAX_CONCURRENT_ASSETS = args.maxcon
    if args.fill_mode is not None: CFG.FILL_ENTRY_MODE = args.fill_mode
    if args.fill_target is not None: CFG.FILL_TARGET = float(args.fill_target)
    if args.no_parallel:  CFG.PARALLEL_PROCESSING = False
    if args.workers:      CFG.PARALLEL_WORKERS = args.workers
    if args.no_cache:     CFG.ASSET_CACHE_ENABLED = False
    if args.clear_cache:
        import shutil
        if os.path.exists(CFG.ASSET_CACHE_DIR):
            shutil.rmtree(CFG.ASSET_CACHE_DIR)
            log.info(f"[Cache] cleared {CFG.ASSET_CACHE_DIR}")
        os.makedirs(CFG.ASSET_CACHE_DIR, exist_ok=True)
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

    if CFG.mode == "testnet":
        # تم تحديث الدالة لتدعم خوادم Demo Trading الجديدة الخاصة بـ Binance
        exchange.enable_demo_trading(True) 

    run_live(CFG, exchange)

if __name__=="__main__":
    main()

# to run the project use the command 
# python trading.py--mode testnet --api-key $BINANCE_API_KEY --api-secret $BINANCE_API_SECRET --capital 55 --nassets 50 --maxcon 5 --rule-filter --rule-min-score 2 --po-wait-s 500 --no-fixed-price
