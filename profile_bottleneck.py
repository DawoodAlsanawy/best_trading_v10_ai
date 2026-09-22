#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║  profile_bottleneck.py — يحدد أين تذهب الثواني داخل process_asset   ║
║  الاستخدام:  python profile_bottleneck.py                            ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os, sys, time, cProfile, pstats, io, statistics
from datetime import datetime, timedelta, timezone

# ═══════════════════════════════════════════════════════════════
# 0) تأكيد وجود numba قبل أي شيء
# ═══════════════════════════════════════════════════════════════
try:
    import numba
    print(f"✅ numba = {numba.__version__}")
except ImportError:
    print("❌ numba غير مثبّت!  →  pip install numba")
    print("   (هذا وحده سيفسّر البطء)")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# 1) استيراد trading.py — تأكد أنك في نفس المجلد
# ═══════════════════════════════════════════════════════════════
try:
    import trading as T
    print(f"✅ imported: {T.__file__}")
except Exception as e:
    print(f"❌ failed to import trading: {e}")
    sys.exit(1)

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════
# 2) جلب بيانات حقيقية من الكاش (لا API calls)
# ═══════════════════════════════════════════════════════════════
CACHE_DIR = "market_data_cache"
if not os.path.exists(CACHE_DIR):
    print(f"❌ no cache dir {CACHE_DIR}")
    print("   شغّل trading.py مرة واحدة على الأقل لبناء الكاش.")
    sys.exit(1)

files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".parquet")]
if not files:
    print(f"❌ cache dir empty")
    sys.exit(1)

# اختر أول ملف (BTC عادةً)
target = None
for f in files:
    if "BTC" in f.upper():
        target = os.path.join(CACHE_DIR, f)
        break
if target is None:
    target = os.path.join(CACHE_DIR, files[0])

print(f"\n📂 loading: {os.path.basename(target)}")
df = pd.read_parquet(target)
if df.index.tz is None:
    df.index = pd.to_datetime(df.index, utc=True)
print(f"   rows = {len(df):,}")
print(f"   range = {df.index[0]}  →  {df.index[-1]}")

# ═══════════════════════════════════════════════════════════════
# 3) تهيئة CFG — بما يطابق تشغيلك الفعلي
# ═══════════════════════════════════════════════════════════════
T.CFG.timeframe = "1h"
T.CFG.TF_SCALE = 1.0
T.CFG.TF_SECONDS = 3600
T.CFG.TF_HOURS = 1.0
T.CFG.NUMBA_ENABLED = True
T.CFG.PARALLEL_PROCESSING = False   # نقيس في-process
T.CFG.LIVE_ASSET_CACHE_ENABLED = False

# ═══════════════════════════════════════════════════════════════
# 4) Warmup Numba (يجب أن يُستدعى قبل القياس)
# ═══════════════════════════════════════════════════════════════
print("\n🔥 Numba warmup...")
t0 = time.time()
T._warmup_numba_kernels()
print(f"   warmup: {time.time()-t0:.2f}s")

# ═══════════════════════════════════════════════════════════════
# 5) قياس كل دالة منفصلة — القسم الحاسم
# ═══════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print("  قياس الدوال الفرعية على هذا الأصل")
print("═"*70)

closes = df['Close'].values.astype(np.float64)
highs  = df['High'].values.astype(np.float64)
lows   = df['Low'].values.astype(np.float64)
vols   = df['Volume'].values.astype(np.float64)
N = T.CFG.N

# ─── (a) compute_features ───
print("\n[1/8] compute_features ...", end=" ", flush=True)
t0 = time.time()
X = T.compute_features(closes, vols, N)
t_feat = time.time() - t0
print(f"{t_feat:.3f}s   (X.shape={X.shape})")

n = len(X)
train_end = int(n * T.CFG.TRAIN_FRACTION)

# ─── (b) KMeans fit ───
print("[2/8] KMeans.fit ...", end=" ", flush=True)
t0 = time.time()
km = T.fit_kmeans(X[:train_end], k=T.CFG.K)
t_km = time.time() - t0
print(f"{t_km:.3f}s   (k={T.CFG.K})")

# ─── (c) KMeans predict (assign) ───
print("[3/8] km.predict (assign) ...", end=" ", flush=True)
t0 = time.time()
sym_q = T.assign(X, km)
t_assign = time.time() - t0
print(f"{t_assign:.3f}s")

# ─── (d) entropy_series ───
print("[4/8] entropy_series ...", end=" ", flush=True)
t0 = time.time()
H = T.entropy_series(sym_q, k=T.CFG.K)
t_entropy = time.time() - t0
print(f"{t_entropy:.3f}s")

# ─── (e) gauge_force ───
print("[5/8] compute_gauge_force_and_gap ...", end=" ", flush=True)
t0 = time.time()
gf, dg = T.compute_gauge_force_and_gap(sym_q, T.CFG.K, T.CFG.W)
t_gauge = time.time() - t0
print(f"{t_gauge:.3f}s")

# ─── (f) compute_geometry ───
print("[6/8] compute_geometry ...", end=" ", flush=True)
t0 = time.time()
C, V = T.compute_geometry(X)
t_geom = time.time() - t0
print(f"{t_geom:.3f}s")

# ─── (g) compute_energy_dynamics (يحوي lyapunov) ───
print("[7/8] compute_energy_dynamics (incl. Lyapunov) ...", end=" ", flush=True)
lr_full = np.diff(np.log(np.maximum(closes, 1e-12)))
t0 = time.time()
ed = T.compute_energy_dynamics(closes, lr_full, X, N)
t_energy = time.time() - t0
print(f"{t_energy:.3f}s")

# ─── (h) PE ───
print("[8/8] compute_PE ...", end=" ", flush=True)
t0 = time.time()
PE = T.compute_PE(X, km, H)
t_pe = time.time() - t0
print(f"{t_pe:.3f}s")

# ─── (i) process_asset الكامل ───
print("\n[FULL] process_asset ...", end=" ", flush=True)
t0 = time.time()
ad = T.process_asset("BTC/USDT", df, current_capital=55.0)
t_full = time.time() - t0
print(f"{t_full:.3f}s   (ad={'OK' if ad else 'None'})")

# ═══════════════════════════════════════════════════════════════
# 6) الجدول النهائي
# ═══════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print("  الجدول التفصيلي (ثواني)")
print("═"*70)

measured = {
    "compute_features":      t_feat,
    "KMeans.fit":            t_km,
    "km.predict (assign)":   t_assign,
    "entropy_series":        t_entropy,
    "gauge_force_and_gap":   t_gauge,
    "compute_geometry":      t_geom,
    "compute_energy_dyn":    t_energy,
    "compute_PE":            t_pe,
}
sum_measured = sum(measured.values())
sum_full = t_full

print(f"{'Function':<26} {'Seconds':>10}  {'% of full':>10}  Bar")
print("-" * 70)
for name, sec in sorted(measured.items(), key=lambda x: -x[1]):
    pct = 100.0 * sec / max(sum_full, 1e-9)
    bar = "█" * int(pct / 2)
    print(f"{name:<26} {sec:>10.3f}  {pct:>9.1f}%  {bar}")
print("-" * 70)
print(f"{'SUM (measured)':<26} {sum_measured:>10.3f}  "
      f"{100*sum_measured/sum_full:>9.1f}%")
print(f"{'FULL process_asset':<26} {sum_full:>10.3f}  "
      f"{'100.0%':>9}")

unaccounted = sum_full - sum_measured
print(f"{'Unaccounted (glue)':<26} {unaccounted:>10.3f}  "
      f"{100*unaccounted/max(sum_full,1e-9):>9.1f}%")

# ═══════════════════════════════════════════════════════════════
# 7) cProfile على process_asset — تفصيل أعمق
# ═══════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print("  cProfile — أعلى 25 دالة استهلاكاً للوقت")
print("═"*70)

pr = cProfile.Profile()
pr.enable()
_ = T.process_asset("BTC/USDT", df, current_capital=55.0)
pr.disable()

sio = io.StringIO()
ps = pstats.Stats(pr, stream=sio).sort_stats('cumulative')
ps.print_stats(25)
print(sio.getvalue())

# ═══════════════════════════════════════════════════════════════
# 8) التوصية التلقائية
# ═══════════════════════════════════════════════════════════════
print("\n" + "═"*70)
print("  التشخيص والتوصية")
print("═"*70)

if t_energy > 0.5 * t_full:
    print("🔥 العنق: compute_energy_dynamics (Lyapunov)")
    print("   → تأكد أن Numba يعمل (يجب أن يكون <0.5s للأصل الواحد)")
    print("   → إذا كان >2s، فالكيرن لم يُترجم، شغّل warmup أولاً")
elif t_feat > 0.3 * t_full:
    print("🔥 العنق: compute_features (Python loop، غير مُسرَّع بـ Numba)")
    print("   → التوصية: انقل الحلقة إلى @njit")
elif t_geom > 0.3 * t_full:
    print("🔥 العنق: compute_geometry (Python loop، غير مُسرَّع)")
    print("   → التوصية: انقل الحلقة إلى @njit")
elif t_km + t_assign > 0.3 * t_full:
    print("🔥 العنق: KMeans (sklearn — C-backed, لكن قد يكون K كبيراً)")
    print(f"   → K={T.CFG.K}، جرّب تصغيره أو استخدام MiniBatchKMeans")
elif sum_full < 1.0:
    print("✅ الأداء ممتاز — process_asset < 1s/رمز")
    print("   → المشكلة ليست في CPU بل في شيء آخر (API/ioloop)")
else:
    print("⚠️  وقت موزّع، لا عنق واحد")
    print("   راجع جدول cProfile أعلاه")

print("\n💡 لتشغيل هذا على 30 رمزاً متوقعاً:")
print(f"   الوقت المتوقع = 30 × {t_full:.2f}s = {30*t_full:.1f}s")
print(f"   إذا كان >90s، فالمشكلة حقيقية.")

print("\n✅ اكتمل التشخيص.")
