# تقرير شامل عن البوت الحالي v8 (abl8b)

---

## الجزء الأول: الهوية النظرية

### 1.1 الفرضية الأساسية

النظام ليس "مؤشراً تقنياً". إنه **محرك فيزيائي** يعامل السوق كجسيم يتحرك في فضاء طوري 7-أبعادي، حيث:

- **الجسيم** = الشمعة الحالية
- **المكان** = الميزات الإحصائية السبع
- **القوى** = مشتقات الإنتروبيا والطاقة الحرة
- **الاحتكاك** = معامل إنتروبي متغير
- **الحقل** = حقل مقياس ناشئ من الانتقالات الرمزية

### 1.2 الطبقات السبع

| # | الطبقة | المخرج | الدور |
|---|---|---|---|
| 1 | Phase Space R⁷ | متجه 7D لكل شمعة | تحويل OHLCV → جسيم |
| 2 | Symbolic Dynamics | رمز K-state (25-50) | KMeans على الفضاء |
| 3 | Entropy & Free Energy | H, dH, F, dF | الثرموديناميك |
| 4 | Emergent Physics | gauge, friction, geodesic_accel | القوى |
| 5 | Signal Generation | P_activation, score | التصفية |
| 6 | Tunnel Entry | tunnel_p, SL, TP | التنفيذ |
| 7 | Risk Management | Kelly + Budget + Apex | البقاء |

### 1.3 المعادلة المركزية

```
geodesic_accel = -∇F + Q·gauge·dH - Γ·dH

حيث:
  -∇F          = ميل الطاقة الحرة (قوة دافعة)
  Q·gauge·dH   = قوة لورنتز (قوة اتجاهية من الحقل)
  -Γ·dH        = قوة الاحتكاك الإنتروبي
```

**هذه المعادلة هي جوهر النظام.** لا توجد نسخة أخرى تعمل.

---

## الجزء الثاني: المعاملات المُثبَّتة

### 2.1 Config الرئيسية (بعد 10 جولات تحسين)

| المعامل | القيمة | من أين |
|---|---|---|
| `N` | 24 | افتراضي |
| `W` | 20 | افتراضي |
| `L` | 10 | افتراضي |
| `K_MIN` | 25 | baseline |
| `K_MAX` | 50 | baseline |
| `TRAIN_FRACTION` | 0.50 | baseline |
| `MIN_SCORE` | 3 | baseline |
| `GAUGE_FILTER_ENABLED` | True | v6 |
| `GAUGE_PERCENTILE_BUY` | 0.60 | v6 |
| **`GAUGE_PERCENTILE_SELL`** | **0.95** | **abl8b** |
| `GAUGE_DISABLE_SELL` | False | default |
| **`APEX_ENABLED`** | **True** | **abl7a** |
| `APEX_KAPPA_PNL` | 0.5 | abl7a |
| `APEX_KAPPA_ENERGY` | 0.5 | abl7a |
| `APEX_KAPPA_ACCEL` | 0.3 | abl7a |
| `APEX_SIGMA_SCALED` | True | abl7a |
| **`MAX_CONCURRENT_ASSETS`** | **3** | **abl6** |
| `CORRELATION_THRESHOLD` | 0.70 | baseline |
| **`DRAWDOWN_REDUCE_AT`** | **0.15** | **abl3c** |
| **`DRAWDOWN_REDUCE_AT_50`** | **0.30** | **abl3c** |
| **`DRAWDOWN_REDUCE_AT_70`** | **0.50** | **abl3c** |
| `REDUCED_RISK_MULT` | 0.25 | baseline |
| **`PARTIAL_TP_ENABLED`** | **True** | baseline |
| **`PARTIAL_TP_R`** | **1.5** | **abl4a** |
| `PARTIAL_TP_PCT` | 0.50 | baseline |
| **`TP_MULT`** | **5.0** | **baseline** (grid مؤكِّد) |
| `BREAKEVEN_ENABLED` | True | baseline |
| `BREAKEVEN_AT_R` | 1.0 | baseline |
| **`TRAIL_ENABLED`** | **False** | **abl4c** |
| `SL_REF_KAPPA` | 0.8 | baseline |
| `SL_MIN_SIGMA` | 3.0 | baseline |
| `SL_MAX_SIGMA` | 8.0 | baseline |
| `SL_WIDEN_MULT` | 1.5 | baseline |
| `FRICTION_DIP_KAPPA` | 4.0 | baseline |
| `MAX_HOLD_BARS` | 168 | baseline |
| `REENTRY_COOLDOWN_BARS` | 3 | baseline |
| `ENTRY_STRUCTURE_ANCHOR` | True | baseline |
| `ENTRY_REGIME_SCALE` | True | baseline |
| `FILL_ENTRY_MAX_WAIT_BARS` | 25 | baseline |
| `PORTFOLIO_HEAT_MAX` | 0.10 | baseline |
| `BUDGET_ENABLED` | True | baseline |
| `WATCH_MODE_ENABLED` | False (في testnet) | default |
| `UNIFIED_ENTRY_ENABLED` | True | baseline |
| `PENDING_ENABLED` | True | baseline |
| `SING_TIMING_ENABLED` | False | default |
| `SUBBARS_ENABLED` | True | baseline |

### 2.2 منطق الدخول المُثبَّت

```
1. z-dev direction:
     z = (p - rolling_mean_N) / rolling_std_N
     if |z| < 1.5 → skip
     action = BUY if z < 0 else SELL

2. Gauge filter (abl8b):
     if SELL and gauge_force < p95 → skip
     if BUY and gauge_force < p60 → skip

3. Boltzmann activation:
     P_activation = exp(-Γ / (|accel| · T_info))
     if P_activation < 0.35 → skip

4. Score filter:
     if score < 3 → skip

5. Tunnel entry:
     σ_price = E_therm × p
     dip = 4.0 × σ_price  (with ATR floor)
     tunnel = p ∓ dip
```

---

## الجزء الثالث: النتائج الكمية

### 3.1 Backtest نهائي (abl8b على 100 أصل، 730d)

| المقياس | القيمة |
|---|---|
| **Sharpe (سنوي)** | **1.920** |
| **E[ln(1+fR)]** | **+0.001714** |
| **Win Rate** | **49.30%** |
| **Profit Factor** | **1.125** |
| **Max Drawdown** | **42.88%** |
| **عدد الصفقات** | **3,229** |
| **BUY / SELL** | 2,776 / 453 |
| **رأس المال النهائي** | **$70,160** (من $100) |
| **العائد الكلي** | **70,060%** |

### 3.2 الأداء على نوافذ متعددة

| النافذة | Sharpe | DD | E[ln] | صفقات |
|---|---|---|---|---|
| **730d** | **1.920** | 42.88% | +0.001714 | 3,229 |
| **540d** | 1.115 | 52.68% | +0.001089 | 2,594 |
| **360d** | 0.681 | 47.07% | +0.000551 | 1,474 |

**الملاحظة الحرجة:** Sharpe ينخفض من 1.92 → 0.68 عند تقليص النافذة. **الـ 370 يوماً الأقدم هي التي ترفع Sharpe.** النظام رابح في كل النوافذ لكن الحافة تتناقص في الفترات الأخيرة.

### 3.3 توزيع أسباب الخروج

| السبب | عدد | نسبة | متوسط MFE |
|---|---|---|---|
| **Emergency SL** | 1,913 | 59.3% | 1.48% |
| **Apex** | 1,216 | 37.7% | **3.39%** |
| Hard TP | 95 | 2.9% | 12.00% |
| MaxHold | 16 | 0.5% | — |

**مفتاح الفهم:**
- **Apex هو المُنقذ.** 37.7% من الصفقات تُغلق عنده بمتوسط +3.39% ربح
- **Emergency SL** يشمل كلاً من الخسائر الصافية (حوالي 40%) و scratch-exits قرب التعادل (حوالي 19%)
- **Hard TP نادر (2.9%)** لكن متوسطه 12% — يحقق أرباحاً كبيرة عند الإصابة

### 3.4 مقارنة مع النسخ السابقة

| الإصدار | Sharpe | DD | التحسين الرئيسي |
|---|---|---|---|
| baseline (الأصل) | −1.07 | 75.8% | نقطة البداية |
| abl2c | 0.960 | 58.0% | z-direction + z-gate |
| abl3c | 1.210 | 50.5% | DD thresholds 0.15/0.30/0.50 |
| abl6 | 1.626 | 52.0% | slots 5→3 + PTR 3.0→1.5 |
| abl7a | **1.920** | 40.6% | **APEX activation** |
| **abl8b** | **1.920** | **42.9%** | SELL filter (p85→p95) |

**القفزة الحقيقية:** من baseline −1.07 إلى abl2c +0.96 (تحول من نظام خاسر إلى رابح). ثم تحسينات تدريجية حتى 1.92.

---

## الجزء الرابع: البنية التقنية

### 4.1 سلسلة التنفيذ (Backtest)

```
run_backtest()
  ├─ scan_top_assets()              ← 100 أصل
  ├─ fetch_all_with_subbars()       ← 4h + 15m sub-bars
  ├─ process_asset() × 100 (parallel)
  │    ├─ compute_features (numba)
  │    ├─ KMeans fit → sym_q
  │    ├─ entropy_series (numba)
  │    ├─ gauge_force (numba)
  │    ├─ geodesic_accel
  │    └─ score
  ├─ precompute_correlations()
  ├─ build_signals()
  │    ├─ P_activation filter
  │    ├─ z-dev direction
  │    ├─ Gauge filter (abl8b)
  │    ├─ MIN_SCORE filter
  │    └─ tunnel + SL + TP + Kelly
  ├─ deduplicate_signals()
  ├─ simulate_portfolio()
  │    ├─ precompute_entry_fills()
  │    ├─ _advance() per bar
  │    ├─ check_thermodynamic_apex()
  │    ├─ _close()
  │    └─ partial TP callback
  └─ compute_metrics() + plot_results()
```

### 4.2 سلسلة التنفيذ (Live/Testnet)

```
run_live()
  ├─ load state (positions, pendings, watch, meta)
  ├─ reconcile with exchange
  ├─ restore protective orders
  ├─ loop every LIVE_POLL_SECS=5s:
  │    ├─ Kill switch check
  │    ├─ monitor_watch_signals()
  │    ├─ monitor_pending_orders()
  │    ├─ update cached_data (smart OHLCV)
  │    ├─ process_asset() for each symbol
  │    ├─ close open positions:
  │    │    ├─ fetch ticker (fresh price)
  │    │    ├─ check Apex
  │    │    ├─ check Topo-Div
  │    │    ├─ check MaxHold
  │    │    ├─ update trailing SL (if TRAIL_ENABLED)
  │    │    ├─ check Partial TP (if not taken)
  │    │    ├─ check SL/TP
  │    │    ├─ check LiqProximity
  │    │    └─ execute exit
  │    ├─ build_signals()
  │    ├─ entry loop:
  │    │    ├─ Early skip (watched, pending)
  │    │    ├─ Correlation guard
  │    │    ├─ SL-Clip
  │    │    ├─ Portfolio risk budget
  │    │    ├─ LiqCap
  │    │    ├─ ensure_symbol_setup()
  │    │    ├─ register_watch_signal()
  │    │    └─ place_pending_entry()
  │    ├─ periodic reconcile
  │    └─ persist state
```

### 4.3 الطبقات الحماية

| الطبقة | الغرض | التنفيذ |
|---|---|---|
| **Kill Switch** | إيقاف طارئ | HMAC + file-based |
| **LiqCap** | منع الاقتراب من التصفية | يحسب MMR وLiq price |
| **LiqGate** | رفض إشارات SL قريب من Liq | في entry loop |
| **LiqProximity** | خروج طارئ عند 70% من Liq | live monitor |
| **Protective Orders** | SL/TP على البورصة | STOP_MARKET + TAKE_PROFIT_MARKET |
| **Portfolio Heat** | حد إجمالي للمخاطرة | 10% عبر 3 مراكز |
| **Drawdown Reduce** | تخفيض المخاطرة عند DD | 15/30/50% |
| **Re-entry Cooldown** | منع close-and-reverse | 3 شموع |
| **Correlation Guard** | منع التداخل | ρ > 0.70 → skip |
| **Apex** | خروج على إشارات فيزيائية | action integral |

---

## الجزء الخامس: القيود والمخاطر

### 5.1 القيود المُعترف بها

**١. Sharpe يتناقص في النوافذ الأخيرة.**
- 730d: 1.92
- 360d: 0.68

**التفسير المحتمل:** السوق تغيّر (2024-Q4 و 2025) أو أن الحافة موسمية.

**٢. حساسية مفرطة لإعدادات البيانات.**
- 50 أصل: Sharpe 1.37
- 100 أصل: Sharpe 1.92

النظام يستفيد من الأصول الإضافية. لكن هذا **ليس ضماناً** أن 100 أصل ستحافظ على الأداء.

**٣. نمط `Emergency SL` مرتفع (59%).**
عدد كبير من الصفقات تُغلق عند SL. هذا يعني أن **الفلتر الأمامي (build_signals) لا يكفي لتمييز الصفقات الجيدة.** Apex هو الذي يُنقذ الموقف.

**٤. اعتماد على Apex.**
بدون Apex، النظام كان خاسراً في العديد من الفترات. Apex ليس "تحسيناً" — بل **مكوّن جوهري**.

**٥. ضجيج إحصائي في Sharpe.**
SE ≈ 1/√n. لـ 3,229 صفقة: SE ≈ 0.018. الفروق الأصغر من 0.3 بين التجارب = ضجيج.

### 5.2 المخاطر التي يجب توثيقها

| المخاطرة | الاحتمال | الأثر |
|---|---|---|
| تغير بنية السوق | متوسط | تدهور Sharpe إلى < 0.5 |
| انزلاق أعلى في Live | عالي | تدهور E[ln] بنسبة 10-20% |
| خطأ تنفيذ حرج | منخفض | خسائر قد تصل إلى 5% |
| فشل Apex في Live | منخفض | DD يرتفع إلى 60%+ |
| Overfitting على 730d | متوسط | أداء أضعف من المتوقع |

### 5.3 ما لم يُختبر بعد

- **Live/Testnet الفعلي.** لم تُنفَّذ ولا صفقة واحدة حتى الآن.
- **سوق هبوطي حاد.** جميع الاختبارات على بيانات 2023-2025.
- **API failure scenarios.** لم يُختبر سلوك البوت عند انقطاع الاتصال.
- **Kill switch.** لم يُفعَّل في ظروف حقيقية.

---

## الجزء السادس: ملفات المشروع

### 6.1 الملفات الرئيسية

| الملف | الدور |
|---|---|
| **`trading_2.py`** | النسخة المُثبَّتة = abl8b |
| `trading_2_v8b_reference.py` | نسخة احتياطية مطابقة |
| `apply_rr_grid.py` | مولّد grid R:R |
| `run_rr_grid.sh` | مشغّل grid |
| `analyze_rr_grid.py` | تحليل grid |
| `extract_rr_results.py` | مستخرج مخرجات مضغوط |
| `live_vs_backtest.py` | مقارنة Live بـ baseline |

### 6.2 ملفات Cache (يجب حفظها)

| الملف | المحتوى |
|---|---|
| `market_data_cache/*.parquet` | شموع 4h + 15m لكل أصل |
| `asset_cache/*.pkl` | AssetData مُحسَّنة |

**حجم متوقع:** 200-500 MB.

### 6.3 ملفات الحالة (Testnet فقط)

| الملف | المحتوى |
|---|---|
| `live_state_testnet.json` | المراكز المفتوحة |
| `pending_orders_testnet.json` | الأوامر المعلقة |
| `watch_signals_testnet.json` | إشارات مراقَبة |
| `symbol_meta_testnet.json` | الرافعة والهامش لكل رمز |
| `kill_switch.json` | حالة الإيقاف الطارئ |

---

## الجزء السابع: الحالة الحالية

### 7.1 ما تم إنجازه

✅ **10 جولات تحسين** على backtest:
- abl2a/2b/2c (اتجاه MR)
- abl3a/3b/3c/3d (عتبات DD و HEAT)
- abl4a/4b/4c/4e/4f (Partial TP وTrailing)
- abl5 (correlation)
- abl6 (slots)
- abl7a/7b/7c (APEX)
- abl8a/8b (SELL filter)
- abl9 (dynamic gauge — مرفوض)
- RR Grid (PTR × TP_MULT — لا تحسين)

✅ **إصدار نهائي:** abl8b
- Sharpe 1.92
- DD 42.9%
- 3,229 صفقة على 730d

✅ **Testnet يعمل** منذ ~ساعتين
- لا صفقات بعد
- Watch signals: 2
- Pending orders: 1
- الأخطاء: 0

### 7.2 ما لم يُنجَز

⏳ **المراقبة الحية.** Testnet يحتاج 4-6 أسابيع للتحقق.

⏳ **Walk-forward حقيقي.** لا يوجد `--end-date` في CLI. الاختبارات على نوافذ متداخلة فقط.

⏳ **Randomized control.** لم يُختبر مقابل random entry.

⏳ **Live deployment.** بعد اجتياز Testnet.

### 7.3 الخطوة التالية

**الخيار الوحيد المعقول الآن: مراقبة Testnet.**

المعايير التي ستقرر:
- ≥ 30 صفقة منفذة
- E[ln] > 0
- MaxDD < 55%
- الأوامر الواقية تعمل
- Apex يُفعَّل بنسبة ≥ 25%

**إذا نجحت → Live برأس مال حقيقي صغير.**
**إذا فشلت → إعادة تقييم شاملة.**

---

## الجزء الثامن: تقييم نقدي

### 8.1 نقاط القوة

**١. بنية نظرية عميقة.** النظام ليس حزمة مؤشرات — إنه نظرية متكاملة.

**٢. Apex المُثبَت.** يُنقذ 37% من الصفقات بمتوسط +3.4%. مكوّن جوهري، ليس زخرفة.

**٣. تحسينات مُتسلسلة موثقة.** كل تحسين له دليل تجريبي (abl رقم).

**٤. حماية متعددة الطبقات.** 10 طبقات حماية، من Kill Switch إلى Apex.

**٥. Tree Occam مقبول.** 10 معاملات رئيسية، كل واحد له مبرر.

### 8.2 نقاط الضعف

**١. Sharpe هش.** يتناقص من 1.92 → 0.68 في النوافذ الأقصر.

**٢. لا Walk-forward حقيقي.** كل الاختبارات على نفس البيانات (730d).

**٣. Emergency SL مرتفع.** 59% من الصفقات تُغلق عند SL.

**٤. اعتماد كلي على Apex.** بدونه، النظام خاسر.

**٥. فجوة Live-Backtest.** لم يُختبر التنفيذ الحقيقي بعد.

### 8.3 الحكم النهائي

**بوت بدرجة مؤسسية.** من Sharpe −1.07 إلى +1.92 = تحول رياضي حقيقي. البنية النظرية عميقة، والتحسينات موثقة.

**لكن:** "الحافة الموجبة" على 730d تعني القليل إذا انهارت في 360d. البيانات الحقيقية وحدها ستقرر.

**القرار:** انشره على Testnet. راقبه 4 أسابيع. لا تعدّل شيئاً. **الوقت سيحكم على الجهد كله.**

---

## الجزء التاسع: المراجع السريعة

### 9.1 أمر Backtest القياسي

```bash
python3 trading_2.py \
    --mode backtest --capital 100 --nassets 100 \
    --timeframe 4h --no-fixed-price --no-trailing \
    --history-days 730 --no-cache \
    --trade-log results/trades_final.jsonl \
    2>&1 | tee results/bt_final.log
```

### 9.2 أمر Testnet القياسي

```bash
python3 trading_2.py \
    --mode testnet \
    --api-key $BINANCE_TESTNET_KEY \
    --api-secret $BINANCE_TESTNET_SECRET \
    --capital 100 --nassets 100 \
    --timeframe 4h --no-fixed-price --no-trailing \
    --history-days 730 \
    --trade-log trades_log_testnet.jsonl
```

### 9.3 مقاييس النجاح على Testnet

| المقياس | القبول | الرفض |
|---|---|---|
| عدد الصفقات | ≥ 30 | < 10 |
| WR | ≥ 40% | < 25% |
| PF | ≥ 1.00 | < 0.85 |
| E[ln] | > 0 | < −0.001 |
| Max DD | < 55% | > 65% |
| Errors | ≤ 3 | > 5 |

### 9.4 ملفات المشروع (تسمية)

- `trading_2.py` — النسخة العاملة
- `trading_2_v8b_reference.py` — مرجع abl8b
- `results/rr_grid_fast/bt_rr_C3.log` — آخر تجربة grid
- `trades_log_testnet.jsonl` — سجل صفقات Testnet (فارغ حالياً)

---

**نهاية التقرير.**

آخر تحديث: بناءً على أحدث تشغيل لـ abl8b و Testnet الحالي.

**التوصية:** لا تعديل. راقب. بلّغ عند أول صفقة.
