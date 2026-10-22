#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              analyze_bleeding.py  —  تحليل تشخيصي لفترات النزيف              ║
║                                                                              ║
║  يقرأ:                                                                       ║
║    • trades_log_backtest.jsonl   (سجل الصفقات)                               ║
║    • market_data_cache/*.parquet (أسعار OHLCV)                               ║
║                                                                              ║
║  يكتب:                                                                       ║
║    • analysis_output/report.md       (تقرير مفصل)                            ║
║    • analysis_output/trades_enriched.csv (كل صفقة بكل الميزات)               ║
║    • analysis_output/plots/*.png     (رسوم بيانية)                            ║
║                                                                              ║
║  لا يعدّل البوت إطلاقاً. تحليل قراءة فقط.                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import glob
import argparse
from datetime import datetime, timezone
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ══════════════════════════════════════════════════════════════════════════════
# § 0  الإعدادات الافتراضية
# ══════════════════════════════════════════════════════════════════════════════

DEFAULTS = {
    "log":       "trades_log_backtest.jsonl",
    "cache":     "market_data_cache",
    "outdir":    "analysis_output",
    "dd_thr":    0.10,     # عتبة DD لتعريف فترة النزيف
    "min_tr":    20,       # أدنى عدد صفقات في الفترة
    "swing_lb":  60,       # نافذة البحث عن swing levels
    "range_lb":  20,       # نافذة حساب range position
}

# الميزات الفيزيائية المطلوب مقارنتها
PHYSICS_FEATURES = [
    "score", "E_therm", "H", "dH", "dF", "friction", "gauge_force",
    "delta_gap", "geodesic_accel", "V", "C", "T_info", "H_over_Hmax",
    "sl_sigma", "friction_drag_over_sl", "ema_slope", "ema_slope_against",
    "dist_from_ema_norm", "mfe_frac", "sl_dist_frac", "rr_design",
    "dynamic_risk", "tri_val", "atr",
]


# ══════════════════════════════════════════════════════════════════════════════
# § 1  تحميل البيانات
# ══════════════════════════════════════════════════════════════════════════════

def load_last_run(jsonl_path: str):
    """
    JSONL قد يحتوي على عدة تشغيلات (append mode).
    نُعيد فقط صفقات آخر تشغيل + بياناته الوصفية.

    Returns
    -------
    (pd.DataFrame, dict|None)
    """
    if not os.path.exists(jsonl_path):
        raise FileNotFoundError(f"لم يُعثر على {jsonl_path}")

    with open(jsonl_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # ابحث عن آخر سطر _meta
    last_meta_idx = -1
    last_meta = None
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("_meta"):
            last_meta_idx = i
            last_meta = r

    # حمّل الصفقات بعد آخر _meta
    if last_meta_idx < 0:
        start_idx = 0
    else:
        start_idx = last_meta_idx + 1

    trades = []
    for line in lines[start_idx:]:
        line = line.strip()
        if not line:
            continue
        try:
            trades.append(json.loads(line))
        except Exception:
            continue

    df = pd.DataFrame(trades)
    if len(df) == 0:
        raise RuntimeError("لا صفقات في آخر تشغيل.")

    # تحويل entry_time إلى datetime
    try:
        df["entry_dt"] = pd.to_datetime(df["entry_time"], utc=True)
    except Exception:
        df["entry_dt"] = pd.NaT

    # ترتيب حسب وقت الدخول (أساس للتحليل الزمني)
    df = df.sort_values(["entry_dt", "entry_ci"], na_position="last").reset_index(drop=True)

    return df, last_meta


def load_price_cache(cache_dir: str, symbols: list, timeframe: str):
    """
    حمّل parquet لكل رمز مطلوب.
    Returns {symbol: DataFrame}  (DataFrame بـ index=ts, OHLCV)
    """
    cache = {}
    for sym in symbols:
        path = os.path.join(cache_dir, f"{sym.replace('/', '_')}_{timeframe}.parquet")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_parquet(path)
            if not isinstance(df.index, pd.DatetimeIndex):
                continue
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            cache[sym] = df
        except Exception as e:
            print(f"  [WARN] {sym}: {e}")
    return cache


# ══════════════════════════════════════════════════════════════════════════════
# § 2  منحنى الأسهم واكتشاف فترات النزيف
# ══════════════════════════════════════════════════════════════════════════════

def build_equity_curve(df: pd.DataFrame):
    """
    أضف عمودي `equity` (capital_after) و `running_peak`.
    نبني curve بمقياس "event": كل صفقة حدث ينتقل بالرصيد.
    """
    df = df.copy()
    # capital_after = الرصيد الإجمالي بعد إغلاق هذه الصفقة
    df["equity"] = pd.to_numeric(df["capital_after"], errors="coerce").fillna(
        pd.to_numeric(df.get("capital_before", 0.0), errors="coerce")
    )
    # إذا كانت equity تبدأ من 0، أعِد البناء من net_pnl
    if (df["equity"] <= 0).all():
        # بناء تراكمي
        net = pd.to_numeric(df["net_pnl"], errors="coerce").fillna(0.0)
        df["equity"] = net.cumsum() + 100.0  # initial
    df["running_peak"] = df["equity"].cummax()
    df["drawdown"] = (df["running_peak"] - df["equity"]) / (df["running_peak"] + 1e-12)
    return df


def find_bleeding_episodes(df: pd.DataFrame, dd_thr: float, min_trades: int):
    """
    اكتشف فترات النزيف كـ peak-to-trough episodes:
      - DD >= dd_thr
      - >= min_trades صفقة
      - تنتهي عند أول قمة جديدة أو عند نهاية السلسلة

    Returns
    -------
    list[dict] with keys:
        start_idx, end_idx (exclusive), peak_idx, trough_idx,
        dd, n_trades, start_time, end_time, end_reason
    """
    eq = df["equity"].values
    times = df["entry_dt"].values
    n = len(eq)
    if n < 2:
        return []

    episodes = []
    peak_val = eq[0]
    peak_idx = 0
    in_bleed = False
    bleed_start = None
    bleed_peak_val = None
    bleed_peak_idx = None

    for i in range(1, n):
        if eq[i] > peak_val:
            # قمة جديدة
            if in_bleed:
                # أنهِ episode
                seg = eq[bleed_start:i]
                trough_local = int(np.argmin(seg))
                trough_idx = bleed_start + trough_local
                dd = (bleed_peak_val - eq[trough_idx]) / (bleed_peak_val + 1e-12)
                n_tr = i - bleed_start
                if dd >= dd_thr and n_tr >= min_trades:
                    episodes.append({
                        "start_idx": bleed_start,
                        "end_idx": i,
                        "peak_idx": bleed_peak_idx,
                        "trough_idx": trough_idx,
                        "dd": float(dd),
                        "n_trades": n_tr,
                        "start_time": times[bleed_start] if bleed_start < len(times) else None,
                        "end_time": times[i - 1] if i - 1 < len(times) else None,
                        "end_reason": "peak",
                    })
            peak_val = eq[i]
            peak_idx = i
            in_bleed = False
            bleed_start = None
        else:
            cur_dd = (peak_val - eq[i]) / (peak_val + 1e-12)
            if cur_dd >= dd_thr and not in_bleed:
                in_bleed = True
                bleed_start = i
                bleed_peak_val = peak_val
                bleed_peak_idx = peak_idx

    # episode مفتوح حتى النهاية
    if in_bleed:
        seg = eq[bleed_start:]
        trough_local = int(np.argmin(seg))
        trough_idx = bleed_start + trough_local
        dd = (bleed_peak_val - eq[trough_idx]) / (bleed_peak_val + 1e-12)
        n_tr = n - bleed_start
        if dd >= dd_thr and n_tr >= min_trades:
            episodes.append({
                "start_idx": bleed_start,
                "end_idx": n,
                "peak_idx": bleed_peak_idx,
                "trough_idx": trough_idx,
                "dd": float(dd),
                "n_trades": n_tr,
                "start_time": times[bleed_start] if bleed_start < len(times) else None,
                "end_time": times[-1] if len(times) > 0 else None,
                "end_reason": "end_of_data",
            })

    return episodes


def label_trades_by_episode(df: pd.DataFrame, episodes: list):
    """أضف عمود in_bleeding=True لكل صفقة داخل episode."""
    df = df.copy()
    df["in_bleeding"] = False
    for ep in episodes:
        df.loc[ep["start_idx"]:ep["end_idx"] - 1, "in_bleeding"] = True
    return df


# ══════════════════════════════════════════════════════════════════════════════
# § 3  مقارنة الميزات (Mann-Whitney U + Cohen's d)
# ══════════════════════════════════════════════════════════════════════════════

def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Effect size: Cohen's d = (mean_a - mean_b) / pooled_std"""
    if len(a) < 2 or len(b) < 2:
        return 0.0
    sp = np.sqrt((a.std(ddof=1) ** 2 + b.std(ddof=1) ** 2) / 2.0)
    if sp <= 1e-12:
        return 0.0
    return float((a.mean() - b.mean()) / sp)


def compare_features(df: pd.DataFrame, features: list, label_col: str = "in_bleeding"):
    """
    لكل ميزة: Bleeding vs Normal + Mann-Whitney U + Cohen's d.
    Returns DataFrame مرتّب حسب |d| تنازلياً.
    """
    bleed = df[df[label_col] == True]
    normal = df[df[label_col] == False]
    if len(bleed) < 5 or len(normal) < 5:
        return pd.DataFrame()

    rows = []
    for f in features:
        if f not in df.columns:
            continue
        b = pd.to_numeric(bleed[f], errors="coerce").dropna().values
        n = pd.to_numeric(normal[f], errors="coerce").dropna().values
        if len(b) < 5 or len(n) < 5:
            continue

        try:
            u_stat, p_val = mannwhitneyu(b, n, alternative="two-sided")
        except Exception:
            continue

        d = cohens_d(b, n)
        rows.append({
            "feature": f,
            "mean_bleed": float(np.mean(b)),
            "mean_norm":  float(np.mean(n)),
            "median_bleed": float(np.median(b)),
            "median_norm":  float(np.median(n)),
            "p_value": float(p_val),
            "cohens_d": d,
            "abs_d": abs(d),
            "n_bleed": len(b),
            "n_norm": len(n),
            "significant_0.05": p_val < 0.05,
            "significant_0.01": p_val < 0.01,
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("abs_d", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# § 4  H6 — تحليل MFE (الفرضية الأقوى من الفحص الأولي)
# ══════════════════════════════════════════════════════════════════════════════

def analyze_mfe(df: pd.DataFrame):
    """
    H6: "67% من الصفقات الخاسرة مرّت بـ +2% MFE"
    نُفصّل أكثر: أي نطاق MFE يتركز فيه النزيف؟
    """
    if "mfe_frac" not in df.columns or "exit_reason" not in df.columns:
        return {}

    df2 = df.copy()
    df2["mfe_frac"] = pd.to_numeric(df2["mfe_frac"], errors="coerce")
    df2 = df2.dropna(subset=["mfe_frac"])

    sl = df2[df2["exit_reason"].astype(str).str.contains("Emergency SL", na=False)]
    tp = df2[df2["exit_reason"].astype(str).str.contains("Hard TP", na=False)]

    # نطاقات MFE (نسبة)
    bins = [0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.05, 0.10, 0.20, 1.0]
    labels = ["0-0.5%", "0.5-1%", "1-1.5%", "1.5-2%", "2-3%",
              "3-5%", "5-10%", "10-20%", ">20%"]
    sl_bins = pd.cut(sl["mfe_frac"], bins=bins, labels=labels, include_lowest=True)
    tp_bins = pd.cut(tp["mfe_frac"], bins=bins, labels=labels, include_lowest=True)

    sl_dist = sl_bins.value_counts().reindex(labels).fillna(0).astype(int)
    tp_dist = tp_bins.value_counts().reindex(labels).fillna(0).astype(int)

    # نسبة الـ SL التي مرّت بـ ≥ 2% MFE
    n_sl = len(sl)
    n_sl_2pct = int((sl["mfe_frac"] >= 0.02).sum())
    n_sl_1pct = int((sl["mfe_frac"] >= 0.01).sum())
    n_sl_05pct = int((sl["mfe_frac"] >= 0.005).sum())

    # نسبة الـ SL التي مرّت بـ ≥ 1R (نحتاج sl_dist)
    n_sl_1R = None
    if "sl_dist_frac" in sl.columns:
        sl_d = pd.to_numeric(sl["sl_dist_frac"], errors="coerce")
        ratio = (sl["mfe_frac"] / sl_d.replace(0, np.nan)).dropna()
        if len(ratio) > 0:
            n_sl_1R = int((ratio >= 1.0).sum())

    # متوسط زمن الاحتفاظ
    hold_sl = pd.to_numeric(sl.get("hold_bars", 0), errors="coerce").mean()
    hold_tp = pd.to_numeric(tp.get("hold_bars", 0), errors="coerce").mean()

    return {
        "n_sl": n_sl,
        "n_tp": len(tp),
        "sl_mean_mfe": float(sl["mfe_frac"].mean()) if n_sl else 0.0,
        "sl_median_mfe": float(sl["mfe_frac"].median()) if n_sl else 0.0,
        "tp_mean_mfe": float(tp["mfe_frac"].mean()) if len(tp) else 0.0,
        "n_sl_above_0.5pct": n_sl_05pct,
        "n_sl_above_1pct": n_sl_1pct,
        "n_sl_above_2pct": n_sl_2pct,
        "n_sl_above_1R": n_sl_1R,
        "pct_sl_above_0.5pct": 100 * n_sl_05pct / max(n_sl, 1),
        "pct_sl_above_1pct": 100 * n_sl_1pct / max(n_sl, 1),
        "pct_sl_above_2pct": 100 * n_sl_2pct / max(n_sl, 1),
        "pct_sl_above_1R": 100 * n_sl_1R / max(n_sl, 1) if n_sl_1R is not None else None,
        "sl_hold_bars_mean": float(hold_sl) if not pd.isna(hold_sl) else 0.0,
        "tp_hold_bars_mean": float(hold_tp) if not pd.isna(hold_tp) else 0.0,
        "sl_mfe_distribution": dict(zip(labels, sl_dist.tolist())),
        "tp_mfe_distribution": dict(zip(labels, tp_dist.tolist())),
        "breakeven_at_1R_would_help": int(n_sl_1R) if n_sl_1R is not None else 0,
        "partial_0.5R_would_help": int((sl["mfe_frac"] >= 0.01).sum()),
    }


# ══════════════════════════════════════════════════════════════════════════════
# § 5  H-UNIFIED — Regime + Gauge (يحتاج parquet للـ E_therm series)
# ══════════════════════════════════════════════════════════════════════════════

def compute_regime_column(df: pd.DataFrame, price_cache: dict,
                          lookback: int = 100):
    """
    أضف عمود `regime` لكل صفقة (explosive / ranging / trending / unknown).
    يُحاكي `_classify_regime_local` لكن من parquet.
    """
    regimes = []
    for _, row in df.iterrows():
        sym = row["symbol"]
        ci = row.get("entry_ci")
        if sym not in price_cache or pd.isna(ci):
            regimes.append("unknown")
            continue
        try:
            parq = price_cache[sym]
            ci = int(ci)
            if ci < 5 or ci >= len(parq):
                regimes.append("unknown")
                continue
            closes = parq["Close"].values.astype(float)
            # E_therm محلي: rolling std للـ log-returns
            # (N = 24 شمعة حسب CFG.N، لكن نستخدم نافذة ملائمة)
            lr = np.diff(np.log(np.maximum(closes, 1e-12)), prepend=np.log(closes[0]))
            N = 24
            if ci < N + 5:
                regimes.append("unknown")
                continue
            eth = pd.Series(lr).rolling(N, min_periods=N // 2).std().values
            sig_now = float(eth[ci])
            start = max(0, ci - lookback)
            sig_mean = float(np.nanmean(eth[start:ci]))
            if not np.isfinite(sig_now) or not np.isfinite(sig_mean) or sig_mean <= 1e-9:
                regimes.append("unknown")
                continue
            ratio = sig_now / sig_mean
            if ratio > 1.6:
                regimes.append("explosive")
            elif ratio < 0.7:
                regimes.append("ranging")
            else:
                regimes.append("trending")
        except Exception:
            regimes.append("unknown")

    out = df.copy()
    out["regime"] = regimes
    return out


def analyze_regime(df: pd.DataFrame):
    """توزيع exit_reason × regime."""
    if "regime" not in df.columns:
        return {}
    df2 = df.copy()
    if "exit_reason" not in df2.columns:
        return {}
    df2["exit_category"] = df2["exit_reason"].apply(_categorize_exit)

    # جدول تقاطعي
    ct = pd.crosstab(df2["regime"], df2["exit_category"])

    # نسبة SL في كل نظام
    result = {}
    for reg in ["trending", "ranging", "explosive"]:
        if reg not in ct.index:
            continue
        total = int(ct.loc[reg].sum())
        if total == 0:
            continue
        sl_pct = 100 * ct.loc[reg, "SL"] / total if "SL" in ct.columns else 0.0
        tp_pct = 100 * ct.loc[reg, "TP"] / total if "TP" in ct.columns else 0.0
        result[reg] = {
            "n": total,
            "sl_pct": float(sl_pct),
            "tp_pct": float(tp_pct),
            "apex_pct": 100 * ct.loc[reg, "Apex"] / total if "Apex" in ct.columns else 0.0,
        }

    result["_crosstab"] = ct
    return result


def _categorize_exit(reason) -> str:
    if pd.isna(reason):
        return "unknown"
    r = str(reason)
    if "Emergency SL" in r:    return "SL"
    if "Hard TP" in r:         return "TP"
    if "Apex" in r:            return "Apex"
    if "Topo" in r:            return "Topo"
    if "MaxHold" in r:         return "MaxHold"
    if "TimeKill" in r:        return "TimeKill"
    if "EndOfData" in r:       return "EoD"
    if "LiqProximity" in r:    return "Liq"
    return "other"


# ══════════════════════════════════════════════════════════════════════════════
# § 6  H7 — Fibonacci / Range Position
# ══════════════════════════════════════════════════════════════════════════════

def find_recent_swings(highs, lows, end_ci, lookback=60):
    """
    آخر swing high وآخر swing low داخل [end_ci-lookback, end_ci).
    Returns (high_price, high_idx, low_price, low_idx) أو None.
    """
    start = max(1, end_ci - lookback)
    end = min(end_ci, len(highs) - 1)
    if end - start < 3:
        return None, -1, None, -1

    last_h = None
    last_l = None
    last_h_idx = -1
    last_l_idx = -1

    for j in range(end - 1, start, -1):
        if j - 1 < 0 or j + 1 >= len(highs):
            continue
        if last_h is None and highs[j] > highs[j - 1] and highs[j] > highs[j + 1]:
            last_h = float(highs[j])
            last_h_idx = j
        if last_l is None and lows[j] < lows[j - 1] and lows[j] < lows[j + 1]:
            last_l = float(lows[j])
            last_l_idx = j
        if last_h is not None and last_l is not None:
            break

    return last_h, last_h_idx, last_l, last_l_idx


def compute_range_position(entry_px, ci, parq, lookback=20):
    """
    موقع السعر في نطاق آخر lookback شمعة:
        0.0 = عند القاع، 1.0 = عند القمة.
    """
    if parq is None:
        return np.nan
    ci = int(ci) if not pd.isna(ci) else -1
    if ci < lookback or ci >= len(parq):
        return np.nan
    h = float(parq["High"].values[ci - lookback:ci + 1].max())
    l = float(parq["Low"].values[ci - lookback:ci + 1].min())
    if h <= l + 1e-12:
        return np.nan
    return float((entry_px - l) / (h - l))


def compute_fib_retracement(entry_px, action, last_swing_h, last_swing_l,
                            prev_swing_h, prev_swing_l):
    """
    نسبة فيبوناتشي الكلاسيكية:
      للموجة X → Y (اندفاع)، النسبة = |entry - Y| / |Y - X|

    نحاول اختيار الأفضل حسب اتجاه الحركة:
      - إذا آخر قمة < آخر قاع => الموجة صاعدة (منخفض→مرتفع)
        التصحيح نحو الأسفل
      - إذا آخر قمة > آخر قاع => الموجة هابطة (مرتفع→منخفض)
        التصحيح نحو الأعلى
    """
    if last_swing_h is None or last_swing_l is None:
        return np.nan

    if last_swing_h > last_swing_l:
        # الموجة صاعدة: من low إلى high
        impulse = last_swing_h - last_swing_l
        if impulse <= 1e-12:
            return np.nan
        # التصحيح من high إلى entry
        return float(abs(entry_px - last_swing_h) / impulse)
    else:
        # الموجة هابطة: من high إلى low
        impulse = last_swing_h - last_swing_l  # سالب
        impulse = abs(impulse)
        if impulse <= 1e-12:
            return np.nan
        # التصحيح من low إلى entry
        return float(abs(entry_px - last_swing_l) / impulse)


def analyze_fibonacci_and_swings(df: pd.DataFrame, price_cache: dict,
                                 swing_lb: int = 60, range_lb: int = 20):
    """
    أضف لكل صفقة:
      - range_pos: موقع السعر في نطاق 20 شمعة
      - fib_retr: نسبة فيبوناتشي للتصحيح الحالي
      - swing_dist_h: المسافة % من آخر swing high
      - swing_dist_l: المسافة % من آخر swing low
      - swing_bars_h: عدد شموع منذ آخر swing high
      - swing_bars_l: عدد شموع منذ آخر swing low
    """
    out = df.copy()
    n = len(out)
    range_pos = np.full(n, np.nan)
    fib_retr = np.full(n, np.nan)
    sw_h_px = np.full(n, np.nan)
    sw_l_px = np.full(n, np.nan)
    sw_h_bars = np.full(n, np.nan)
    sw_l_bars = np.full(n, np.nan)

    for i, row in out.iterrows():
        sym = row.get("symbol")
        ci = row.get("entry_ci")
        if sym not in price_cache or pd.isna(ci):
            continue
        parq = price_cache[sym]
        ci = int(ci)
        if ci < 5 or ci >= len(parq):
            continue

        entry_px = float(row.get("entry_price") or 0)
        if entry_px <= 0:
            continue

        highs = parq["High"].values
        lows = parq["Low"].values

        # Range position
        range_pos[i] = compute_range_position(entry_px, ci, parq, range_lb)

        # Swings
        h_px, h_idx, l_px, l_idx = find_recent_swings(highs, lows, ci, swing_lb)
        if h_px is not None:
            sw_h_px[i] = h_px
            sw_h_bars[i] = ci - h_idx
        if l_px is not None:
            sw_l_px[i] = l_px
            sw_l_bars[i] = ci - l_idx

        # Fibonacci retracement (يحتاج swing + entry + action)
        if h_px is not None and l_px is not None:
            fib_retr[i] = compute_fib_retracement(
                entry_px, row.get("action", "?"),
                h_px, l_px, None, None
            )

    out["range_pos"] = range_pos
    out["fib_retr"] = fib_retr
    out["swing_h_px"] = sw_h_px
    out["swing_l_px"] = sw_l_px
    out["swing_h_bars"] = sw_h_bars
    out["swing_l_bars"] = sw_l_bars

    # المسافة % من كل swing
    out["swing_h_dist_pct"] = (out["swing_h_px"] - out["entry_price"]) / out["entry_price"]
    out["swing_l_dist_pct"] = (out["entry_price"] - out["swing_l_px"]) / out["entry_price"]

    return out


def analyze_fib_distribution(df: pd.DataFrame):
    """
    قارن توزيع `fib_retr` و `range_pos` بين الصفقات الرابحة/الخاسرة.
    ابحث عن ذُرى قرب 0.382 / 0.5 / 0.618 (نسب فيبوناتشي).
    """
    if "fib_retr" not in df.columns:
        return {}

    df2 = df.copy()
    df2["net_pnl"] = pd.to_numeric(df2["net_pnl"], errors="coerce")
    df2 = df2.dropna(subset=["fib_retr", "net_pnl"])

    # تصنيف: ربح > 0 vs خسارة
    win = df2[df2["net_pnl"] > 0]
    loss = df2[df2["net_pnl"] <= 0]

    result = {
        "n_win": len(win), "n_loss": len(loss),
        "fib_mean_win":  float(win["fib_retr"].mean())  if len(win) else 0.0,
        "fib_mean_loss": float(loss["fib_retr"].mean()) if len(loss) else 0.0,
        "fib_median_win":  float(win["fib_retr"].median())  if len(win) else 0.0,
        "fib_median_loss": float(loss["fib_retr"].median()) if len(loss) else 0.0,
    }

    # نسبة الصفقات في نطاقات فيبوناتشي
    def fib_bucket(x):
        if pd.isna(x):
            return None
        if x < 0.236:  return "<0.236"
        if x < 0.382:  return "0.236-0.382"
        if x < 0.500:  return "0.382-0.5"
        if x < 0.618:  return "0.5-0.618"
        if x < 0.786:  return "0.618-0.786"
        return ">0.786"

    bins_win = win["fib_retr"].apply(fib_bucket).value_counts(normalize=True) * 100
    bins_loss = loss["fib_retr"].apply(fib_bucket).value_counts(normalize=True) * 100
    result["bucket_win_pct"] = bins_win.to_dict()
    result["bucket_loss_pct"] = bins_loss.to_dict()

    # Mann-Whitney U
    try:
        if len(win) >= 5 and len(loss) >= 5:
            _, p = mannwhitneyu(win["fib_retr"], loss["fib_retr"], alternative="two-sided")
            result["fib_mw_p"] = float(p)
    except Exception:
        pass

    # range_pos
    if "range_pos" in df2.columns:
        rw = df2[df2["net_pnl"] > 0]["range_pos"].dropna()
        rl = df2[df2["net_pnl"] <= 0]["range_pos"].dropna()
        if len(rw) >= 5 and len(rl) >= 5:
            result["range_mean_win"] = float(rw.mean())
            result["range_mean_loss"] = float(rl.mean())
            try:
                _, p2 = mannwhitneyu(rw, rl, alternative="two-sided")
                result["range_mw_p"] = float(p2)
            except Exception:
                pass

    return result


# ══════════════════════════════════════════════════════════════════════════════
# § 7  الرسوم البيانية
# ══════════════════════════════════════════════════════════════════════════════

DARK_BG = "#0d0d0d"
DARK_AX = "#111111"
TEXT = "#e0e0e0"
GRID = "#2a2a2a"
CYAN = "#00e5ff"
RED = "#ef5350"
GREEN = "#66bb6a"
ORANGE = "#ffa726"
PURPLE = "#ab47bc"

plt.rcParams.update({
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT, "ytick.color": TEXT,
    "font.family": "DejaVu Sans",
})


def _setup_ax(ax, title=""):
    ax.set_facecolor(DARK_AX)
    ax.grid(True, color=GRID, lw=0.4)
    if title:
        ax.set_title(title, fontsize=10, pad=8)


def plot_equity_with_bleeding(df, episodes, out_path):
    """منحنى الأسهم مع تظليل فترات النزيف."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), facecolor=DARK_BG,
                                     gridspec_kw={"height_ratios": [2, 1]})
    eq = df["equity"].values
    x = np.arange(len(eq))

    ax1.semilogy(x, eq, color=CYAN, lw=0.8, label="Equity")
    for ep in episodes:
        ax1.axvspan(ep["start_idx"], ep["end_idx"], alpha=0.25, color=RED,
                    label=f"DD {ep['dd']*100:.1f}% ({ep['n_trades']}tr)" if ep == episodes[0] else None)
        ax1.axvline(ep["trough_idx"], color=ORANGE, lw=0.8, ls=":")
    ax1.axhline(eq[0], color=RED, ls="--", lw=0.6, alpha=0.6)
    _setup_ax(ax1, f"Equity Curve — {len(episodes)} Bleeding Episodes")
    ax1.set_ylabel("Capital (log)")
    ax1.legend(loc="upper left", fontsize=8, framealpha=0.3)

    # Drawdown
    dd = (df["running_peak"] - df["equity"]) / df["running_peak"]
    ax2.fill_between(x, 0, -dd * 100, color=RED, alpha=0.5)
    for ep in episodes:
        ax2.axvspan(ep["start_idx"], ep["end_idx"], alpha=0.25, color=RED)
    ax2.axhline(-10, color=ORANGE, ls="--", lw=0.7, label="10% threshold")
    _setup_ax(ax2, "Drawdown %")
    ax2.set_xlabel("Trade index")
    ax2.set_ylabel("DD %")
    ax2.legend(fontsize=8, loc="lower left")

    plt.tight_layout()
    plt.savefig(out_path, dpi=110, facecolor=DARK_BG, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path}")


def plot_feature_distributions(df, features, top_k=8, out_path=None):
    """KDE/hist للصفقات الخاسرة vs الرابحة لأهم الميزات."""
    if features.empty:
        return
    top = features.head(top_k)
    n = len(top)
    cols = 4
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.2 * rows),
                              facecolor=DARK_BG)
    axes = axes.flatten() if n > 1 else [axes]

    bleed = df[df["in_bleeding"] == True]
    norm = df[df["in_bleeding"] == False]

    for i, (_, row) in enumerate(top.iterrows()):
        ax = axes[i]
        f = row["feature"]
        b = pd.to_numeric(bleed.get(f, pd.Series()), errors="coerce").dropna()
        n_ = pd.to_numeric(norm.get(f, pd.Series()), errors="coerce").dropna()

        if len(b) > 0:
            ax.hist(b, bins=40, alpha=0.65, color=RED, label="Bleeding", density=True)
        if len(n_) > 0:
            ax.hist(n_, bins=40, alpha=0.55, color=GREEN, label="Normal", density=True)
        _setup_ax(ax, f"{f}\n(d={row['cohens_d']:+.2f}, p={row['p_value']:.2e})")
        ax.legend(fontsize=7, framealpha=0.3)

    for j in range(n, len(axes)):
        axes[j].axis("off")

    plt.tight_layout()
    if out_path:
        plt.savefig(out_path, dpi=110, facecolor=DARK_BG, bbox_inches="tight")
        print(f"  ✓ {out_path}")
    plt.close()


def plot_mfe_distribution(mfe_data, out_path):
    """رسم توزيع MFE للصفقات المنتهية بـ SL."""
    if not mfe_data or "sl_mfe_distribution" not in mfe_data:
        return
    labels = list(mfe_data["sl_mfe_distribution"].keys())
    sl_vals = list(mfe_data["sl_mfe_distribution"].values())
    tp_vals = list(mfe_data["tp_mfe_distribution"].values())

    fig, ax = plt.subplots(figsize=(12, 5), facecolor=DARK_BG)
    x = np.arange(len(labels))
    w = 0.38
    ax.bar(x - w / 2, sl_vals, w, color=RED, alpha=0.85, label=f"SL exits (n={mfe_data['n_sl']})")
    ax.bar(x + w / 2, tp_vals, w, color=GREEN, alpha=0.85, label=f"TP exits (n={mfe_data['n_tp']})")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.axvline(labels.index("2-3%"), color=ORANGE, ls="--", lw=1, label="2% mark")
    _setup_ax(ax, f"MFE distribution — {mfe_data['pct_sl_above_2pct']:.1f}% of SLs passed +2% MFE")
    ax.set_ylabel("# trades")
    ax.legend(fontsize=9, framealpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=110, facecolor=DARK_BG, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path}")


def plot_fib_distribution(df, out_path):
    """توزيع fib_retr للرابحة vs الخاسرة."""
    if "fib_retr" not in df.columns:
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), facecolor=DARK_BG)

    df2 = df.dropna(subset=["fib_retr", "net_pnl"])
    win = df2[df2["net_pnl"] > 0]["fib_retr"]
    loss = df2[df2["net_pnl"] <= 0]["fib_retr"]

    bins = np.linspace(0, 1, 41)
    ax1.hist(win, bins=bins, alpha=0.6, color=GREEN, label=f"Win (n={len(win)})", density=True)
    ax1.hist(loss, bins=bins, alpha=0.5, color=RED, label=f"Loss (n={len(loss)})", density=True)
    for lvl, name in [(0.382, "38.2%"), (0.5, "50%"), (0.618, "61.8%")]:
        ax1.axvline(lvl, color=ORANGE, ls="--", lw=1, alpha=0.7)
        ax1.text(lvl, ax1.get_ylim()[1] * 0.9, name, color=ORANGE, fontsize=8, ha="center")
    _setup_ax(ax1, "Fibonacci Retracement at Entry")
    ax1.set_xlabel("Retracement ratio")
    ax1.legend(fontsize=8, framealpha=0.3)

    if "range_pos" in df2.columns:
        win_r = df2[df2["net_pnl"] > 0]["range_pos"].dropna()
        loss_r = df2[df2["net_pnl"] <= 0]["range_pos"].dropna()
        ax2.hist(win_r, bins=bins, alpha=0.6, color=GREEN, label=f"Win", density=True)
        ax2.hist(loss_r, bins=bins, alpha=0.5, color=RED, label=f"Loss", density=True)
        _setup_ax(ax2, "Range Position at Entry (20-bar)")
        ax2.set_xlabel("0=bottom, 1=top of range")
        ax2.legend(fontsize=8, framealpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=110, facecolor=DARK_BG, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path}")


def plot_regime_breakdown(regime_data, out_path):
    """Bar chart: % SL لكل نظام."""
    if not regime_data or "_crosstab" not in regime_data:
        return
    ct = regime_data["_crosstab"]
    if ct.empty:
        return

    regimes = [r for r in ["trending", "ranging", "explosive"] if r in ct.index]
    if not regimes:
        return

    exit_cats = list(ct.columns)
    fig, ax = plt.subplots(figsize=(10, 5), facecolor=DARK_BG)

    x = np.arange(len(regimes))
    w = 0.8 / max(len(exit_cats), 1)
    colors = {"SL": RED, "TP": GREEN, "Apex": PURPLE,
              "Topo": CYAN, "MaxHold": ORANGE, "TimeKill": "#ff9800",
              "EoD": "#78909c", "Liq": "#b71c1c", "other": "#616161"}

    for i, cat in enumerate(exit_cats):
        vals = [int(ct.loc[r, cat]) if cat in ct.columns else 0 for r in regimes]
        ax.bar(x + i * w - w * len(exit_cats) / 2, vals, w,
               color=colors.get(cat, "#888"), alpha=0.85, label=cat)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{r}\n(n={sum(int(ct.loc[r, c]) for c in ct.columns)})" for r in regimes])
    _setup_ax(ax, "Exit reason × Regime")
    ax.set_ylabel("# trades")
    ax.legend(fontsize=8, ncol=3, framealpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=110, facecolor=DARK_BG, bbox_inches="tight")
    plt.close()
    print(f"  ✓ {out_path}")


# ══════════════════════════════════════════════════════════════════════════════
# § 8  توليد التقرير
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_pct(x):
    return f"{x*100:.2f}%" if isinstance(x, (int, float)) and np.isfinite(x) else "—"


def write_report(out_path, meta, df, episodes, feat_table, mfe_data,
                 regime_data, fib_data):
    """تقرير Markdown شامل."""
    lines = []
    add = lines.append

    add("# 📊 تحليل تشخيصي لفترات النزيف\n")
    add(f"**تاريخ التحليل**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if meta:
        add(f"**التشغيل**: started_at = `{meta.get('started_at','?')}`, "
            f"TF = `{meta.get('timeframe','?')}`, "
            f"Initial capital = ${meta.get('INITIAL_CAPITAL','?')}")
    add("")

    # ── ملخص تنفيذي ──
    add("## 🎯 الملخص التنفيذي\n")
    add(f"- **عدد الصفقات الكلي**: {len(df):,}")
    add(f"- **رأس المال النهائي**: ${df['equity'].iloc[-1]:,.2f}")
    add(f"- **Max Drawdown**: {df['drawdown'].max()*100:.2f}%")
    add(f"- **عدد فترات النزيف** (DD≥{DEFAULTS['dd_thr']*100:.0f}%, ≥{DEFAULTS['min_tr']} صفقة): {len(episodes)}")
    add("")

    if episodes:
        add("### فترات النزيف المكتشفة\n")
        add("| # | عدد الصفقات | DD | تاريخ البداية | السبب |")
        add("|---|---|---|---|---|")
        for i, ep in enumerate(episodes, 1):
            st = ep["start_time"]
            st_s = st.strftime("%Y-%m-%d") if isinstance(st, pd.Timestamp) else str(st)[:10]
            add(f"| {i} | {ep['n_trades']} | {ep['dd']*100:.2f}% | {st_s} | {ep['end_reason']} |")
        add("")

    # ── Feature comparison ──
    add("## 🔬 مقارنة الميزات الفيزيائية (Bleeding vs Normal)\n")
    if feat_table is not None and len(feat_table) > 0:
        add("مرتّبة حسب حجم الأثر (Cohen's d). `d>0.3` = أثر متوسط، `d>0.5` = أثر كبير.\n")
        add("| الميزة | μ (Bleeding) | μ (Normal) | d | p-value | الدلالة |")
        add("|---|---|---|---|---|---|")
        for _, r in feat_table.head(20).iterrows():
            sig = "✅" if r["significant_0.01"] else ("⚠" if r["significant_0.05"] else "")
            add(f"| `{r['feature']}` | {r['mean_bleed']:.4g} | {r['mean_norm']:.4g} | "
                f"{r['cohens_d']:+.2f} | {r['p_value']:.2e} | {sig} |")
        add("")
        # التوصية
        top_sig = feat_table[
            (feat_table["significant_0.05"]) & (feat_table["abs_d"] > 0.3)
        ]
        if len(top_sig) > 0:
            add(f"**🎯 {len(top_sig)} ميزة ذات دلالة إحصائية وأثر متوسط/كبير.** هذه مرشحات محتملة للفلترة.\n")
        else:
            add("**⚠ لا ميزة فردية تُميّز النزيف بقوة.** قد تحتاج مركّب (composite) من عدة ميزات.\n")
    else:
        add("_لا بيانات كافية._\n")

    # ── H6: MFE ──
    add("## 🔍 H6 — تحليل MFE (الفرضية الأقوى)\n")
    if mfe_data:
        add(f"- عدد الصفقات المنتهية بـ SL: **{mfe_data['n_sl']:,}**")
        add(f"- متوسط MFE لها: **{mfe_data['sl_mean_mfe']*100:.2f}%**  "
            f"(وسيط: {mfe_data['sl_median_mfe']*100:.2f}%)")
        add(f"- عدد الصفقات التي تجاوزت +0.5% MFE: {mfe_data['n_sl_above_0.5pct']:,} "
            f"({mfe_data['pct_sl_above_0.5pct']:.1f}%)")
        add(f"- عدد الصفقات التي تجاوزت +1.0% MFE: {mfe_data['n_sl_above_1pct']:,} "
            f"({mfe_data['pct_sl_above_1pct']:.1f}%)")
        add(f"- عدد الصفقات التي تجاوزت +2.0% MFE: {mfe_data['n_sl_above_2pct']:,} "
            f"({mfe_data['pct_sl_above_2pct']:.1f}%)")
        if mfe_data.get("n_sl_above_1R") is not None:
            add(f"- **عدد الصفقات التي تجاوزت +1R**: {mfe_data['n_sl_above_1R']:,} "
                f"({mfe_data['pct_sl_above_1R']:.1f}%)")
            add(f"  → لو كان `BREAKEVEN_ENABLED=True`، لكانت هذه الصفقات "
                f"خُرجت بـ breakeven بدل خسارة كاملة.")
        add("")
        add("**التفسير**: نسبة عالية من الصفقات الخاسرة كانت في ربح غير محقق. "
            "المشكلة في **الخروج** لا في الدخول.")
        add("")
    else:
        add("_لا بيانات MFE._\n")

    # ── H-UNIFIED: Regime ──
    add("## 🌊 H-UNIFIED — Regime × Exit\n")
    if regime_data and "_crosstab" in regime_data:
        ct = regime_data["_crosstab"]
        add("| Regime | n | % SL | % TP | % Apex |")
        add("|---|---|---|---|---|")
        for reg in ["trending", "ranging", "explosive"]:
            if reg in ct.index:
                d = regime_data[reg]
                add(f"| {reg} | {d['n']} | {d['sl_pct']:.1f}% | "
                    f"{d['tp_pct']:.1f}% | {d['apex_pct']:.1f}% |")
        add("")

        # توصية
        if "trending" in regime_data:
            tr_sl = regime_data["trending"]["sl_pct"]
            rg_sl = regime_data.get("ranging", {}).get("sl_pct", 0)
            if tr_sl > rg_sl * 1.3:
                add(f"**🎯 نظام `trending` يُنتج SL بنسبة {tr_sl:.1f}% "
                    f"مقابل {rg_sl:.1f}% في `ranging`.**  \n"
                    f"→ التوصية: تفعيل `--filter-no-ema` (رفض إشارات ضد ميل EMA) "
                    f"أو `REGIME_FILTER_ENABLED=True`.")
                add("")
    else:
        add("_لا بيانات نظام (قد يكون parquet مفقوداً)._\n")

    # ── H7: Fibonacci ──
    add("## 🌀 H7 — Fibonacci / Range Position\n")
    if fib_data and "fib_mw_p" in fib_data:
        add(f"- عدد الرابحة: {fib_data['n_win']:,}  |  الخاسرة: {fib_data['n_loss']:,}")
        add(f"- متوسط `fib_retr` — الرابحة: **{fib_data['fib_mean_win']:.3f}**  |  "
            f"الخاسرة: **{fib_data['fib_mean_loss']:.3f}**")
        add(f"- Mann-Whitney p-value: **{fib_data['fib_mw_p']:.2e}**")
        if fib_data["fib_mw_p"] < 0.05:
            add("→ ✅ **فرق ذو دلالة إحصائية.** نسبة فيبوناتشي لها قيمة تنبؤية.")
        else:
            add("→ ⚠ **لا فرق ذو دلالة.** قد تحتاج تقسيم أدق (per-action أو per-TF).")
        add("")

        add("### توزيع نطاقات فيبوناتشي\n")
        add("| النطاق | % رابحة | % خاسرة |")
        add("|---|---|---|")
        for bucket in ["<0.236", "0.236-0.382", "0.382-0.5", "0.5-0.618",
                       "0.618-0.786", ">0.786"]:
            w = fib_data["bucket_win_pct"].get(bucket, 0.0)
            l = fib_data["bucket_loss_pct"].get(bucket, 0.0)
            add(f"| {bucket} | {w:.1f}% | {l:.1f}% |")
        add("")

        # توصية
        best_w = max(fib_data["bucket_win_pct"].items(), key=lambda x: x[1])
        best_l = max(fib_data["bucket_loss_pct"].items(), key=lambda x: x[1])
        if best_w[0] != best_l[0]:
            add(f"**🎯 الصفقات الرابحة تتركز عند `{best_w[0]}` ({best_w[1]:.1f}%) "
                f"بينما الخاسرة عند `{best_l[0]}` ({best_l[1]:.1f}%).**  \n"
                f"→ يمكن بناء فلتر: رفض الإشارات التي تقع في `{best_l[0]}`.")
            add("")
    elif fib_data and "range_mw_p" in fib_data:
        add(f"- `range_pos` — الرابحة: μ={fib_data['range_mean_win']:.3f}  |  "
            f"الخاسرة: μ={fib_data['range_mean_loss']:.3f}")
        add(f"- p-value: {fib_data['range_mw_p']:.2e}")
        add("")
    else:
        add("_لا بيانات كافية (قد يكون parquet مفقوداً لبعض الرموز)._\n")

    # ── التوصيات النهائية ──
    add("## 🎯 التوصيات المقترحة للمرحلة 2\n")
    recs = []

    if mfe_data and mfe_data.get("pct_sl_above_1R", 0) and mfe_data["pct_sl_above_1R"] > 30:
        recs.append(
            f"1. **إعادة تفعيل Breakeven** (أزل `--no-breakeven`). "
            f"{mfe_data['pct_sl_above_1R']:.1f}% من الخاسرات مرّت بـ +1R، "
            f"لو كان Breakeven نشطاً لخرجت بربح صغير بدل خسارة كاملة."
        )

    if mfe_data and mfe_data["pct_sl_above_0.5pct"] > 50:
        recs.append(
            f"2. **خفّض `--partial-tp-r`** من {1.5} إلى `0.8`. "
            f"{mfe_data['pct_sl_above_0.5pct']:.1f}% من الخاسرات مرّت بـ +0.5%."
        )

    if feat_table is not None and len(feat_table) > 0:
        top = feat_table.iloc[0]
        if top["abs_d"] > 0.3 and top["significant_0.05"]:
            recs.append(
                f"3. **فعّل فلتر على `{top['feature']}`** (d={top['cohens_d']:+.2f}, "
                f"p={top['p_value']:.2e}). رفض الصفقات التي تقع في منطقة النزيف."
            )

    if regime_data and "trending" in regime_data:
        if regime_data["trending"]["sl_pct"] > regime_data.get("ranging", {}).get("sl_pct", 0) * 1.3:
            recs.append(
                "4. **فعّل `REGIME_FILTER_ENABLED=True`** أو `--filter-no-ema` "
                "لرفض الإشارات في أسواق الاتجاه القوي."
            )

    if not recs:
        recs.append("_لا توصيات قوية — البيانات لا تكفي. جرّب عتبات DD مختلفة أو split حسب الرمز._")

    for r in recs:
        add(r)
    add("")

    add("## 📁 الملفات الإضافية\n")
    add("- `trades_enriched.csv` — كل صفقة مع كل الميزات المُشتقّة")
    add("- `plots/` — كل الرسوم البيانية")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  ✓ {out_path}")


# ══════════════════════════════════════════════════════════════════════════════
# § 9  main()
# ══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="تحليل تشخيصي لفترات النزيف")
    p.add_argument("--log",       default=DEFAULTS["log"])
    p.add_argument("--cache",     default=DEFAULTS["cache"])
    p.add_argument("--outdir",    default=DEFAULTS["outdir"])
    p.add_argument("--dd-threshold", type=float, default=DEFAULTS["dd_thr"])
    p.add_argument("--min-trades",   type=int,   default=DEFAULTS["min_tr"])
    p.add_argument("--swing-lookback", type=int, default=DEFAULTS["swing_lb"])
    p.add_argument("--range-lookback", type=int, default=DEFAULTS["range_lb"])
    p.add_argument("--timeframe", type=str, default=None,
                   help="يُستنتج من meta إن لم يُحدد")
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    plots_dir = os.path.join(args.outdir, "plots")
    os.makedirs(plots_dir, exist_ok=True)

    print("═" * 72)
    print("  🔍 تحليل تشخيصي لفترات النزيف")
    print("═" * 72)

    # ── 1. تحميل الصفقات ──
    print(f"\n[1/7] تحميل {args.log} ...")
    df, meta = load_last_run(args.log)
    print(f"  ✓ {len(df):,} صفقة (آخر تشغيل)")

    tf = args.timeframe or (meta.get("timeframe") if meta else None) or "4h"
    print(f"  ✓ timeframe = {tf}")

    # ── 2. منحنى الأسهم ──
    print(f"\n[2/7] بناء منحنى الأسهم ...")
    df = build_equity_curve(df)

    # ── 3. اكتشاف فترات النزيف ──
    print(f"\n[3/7] اكتشاف فترات النزيف (DD≥{args.dd_threshold*100:.0f}%, "
          f"≥{args.min_trades} صفقة) ...")
    episodes = find_bleeding_episodes(df, args.dd_threshold, args.min_trades)
    print(f"  ✓ {len(episodes)} فترة مكتشفة")
    for i, ep in enumerate(episodes, 1):
        print(f"     [{i}] {ep['n_trades']} صفقة, DD={ep['dd']*100:.2f}%, "
              f"ends={ep['end_reason']}")
    df = label_trades_by_episode(df, episodes)
    print(f"  ✓ {df['in_bleeding'].sum():,} صفقة في فترات النزيف")

    # ── 4. تحميل parquet ──
    print(f"\n[4/7] تحميل market_data_cache/{tf} ...")
    symbols = df["symbol"].unique().tolist()
    price_cache = load_price_cache(args.cache, symbols, tf)
    print(f"  ✓ {len(price_cache)}/{len(symbols)} رمز محمّل")

    # ── 5. مقارنة الميزات ──
    print(f"\n[5/7] مقارنة الميزات (Mann-Whitney U) ...")
    feat_table = compare_features(df, PHYSICS_FEATURES, label_col="in_bleeding")
    if len(feat_table) > 0:
        print(f"  ✓ {len(feat_table)} ميزة حللتها")
        top3 = feat_table.head(3)
        for _, r in top3.iterrows():
            sig = "✅" if r["significant_0.01"] else ("⚠" if r["significant_0.05"] else "")
            print(f"     {sig} {r['feature']}: d={r['cohens_d']:+.2f}, "
                  f"p={r['p_value']:.2e}")

    # ── 6. الفرضيات ──
    print(f"\n[6/7] اختبار الفرضيات ...")

    print(f"  ▶ H6 (MFE) ...")
    mfe_data = analyze_mfe(df)
    if mfe_data:
        print(f"     {mfe_data['pct_sl_above_2pct']:.1f}% من SL مرّت بـ +2% MFE")

    print(f"  ▶ H-UNIFIED (Regime) ...")
    df = compute_regime_column(df, price_cache, lookback=100)
    regime_data = analyze_regime(df)
    if "trending" in regime_data:
        print(f"     trending: n={regime_data['trending']['n']}, "
              f"SL={regime_data['trending']['sl_pct']:.1f}%")
    if "ranging" in regime_data:
        print(f"     ranging:  n={regime_data['ranging']['n']}, "
              f"SL={regime_data['ranging']['sl_pct']:.1f}%")

    print(f"  ▶ H7 (Fibonacci) ...")
    df = analyze_fibonacci_and_swings(
        df, price_cache,
        swing_lb=args.swing_lookback,
        range_lb=args.range_lookback
    )
    fib_data = analyze_fib_distribution(df)
    if "fib_mw_p" in fib_data:
        print(f"     fib_retr μ_win={fib_data['fib_mean_win']:.3f}, "
              f"μ_loss={fib_data['fib_mean_loss']:.3f}, "
              f"p={fib_data['fib_mw_p']:.2e}")

    # ── 7. الحفظ ──
    print(f"\n[7/7] حفظ الملفات ...")

    # CSV مُثرى
    enrich_cols = ["symbol", "action", "entry_time", "entry_price", "exit_price",
                   "exit_reason", "net_pnl", "mfe_frac", "hold_bars",
                   "in_bleeding", "equity", "drawdown",
                   "regime", "range_pos", "fib_retr",
                   "swing_h_px", "swing_l_px", "swing_h_bars", "swing_l_bars",
                   "swing_h_dist_pct", "swing_l_dist_pct"]
    enrich_cols += [f for f in PHYSICS_FEATURES if f in df.columns]
    enrich_cols = [c for c in enrich_cols if c in df.columns]
    csv_path = os.path.join(args.outdir, "trades_enriched.csv")
    df[enrich_cols].to_csv(csv_path, index=False)
    print(f"  ✓ {csv_path}")

    # تقرير
    report_path = os.path.join(args.outdir, "report.md")
    write_report(report_path, meta, df, episodes, feat_table,
                 mfe_data, regime_data, fib_data)

    # رسوم
    print(f"\n  ▶ رسوم بيانية ...")
    plot_equity_with_bleeding(df, episodes,
                              os.path.join(plots_dir, "equity_bleeding.png"))
    if feat_table is not None and len(feat_table) > 0:
        plot_feature_distributions(
            df, feat_table, top_k=8,
            out_path=os.path.join(plots_dir, "features_distributions.png")
        )
    if mfe_data:
        plot_mfe_distribution(mfe_data,
                              os.path.join(plots_dir, "mfe_distribution.png"))
    if regime_data and "_crosstab" in regime_data:
        plot_regime_breakdown(regime_data,
                              os.path.join(plots_dir, "regime_breakdown.png"))
    if "fib_retr" in df.columns:
        plot_fib_distribution(df,
                              os.path.join(plots_dir, "fibonacci_distribution.png"))

    print("\n" + "═" * 72)
    print("  ✅ اكتمل التحليل")
    print(f"  📄 التقرير: {report_path}")
    print(f"  📊 CSV:    {csv_path}")
    print(f"  🖼️  Plots:  {plots_dir}/")
    print("═" * 72)


if __name__ == "__main__":
    main()
