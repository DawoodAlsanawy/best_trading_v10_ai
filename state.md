# STATE.md — محرك التداول الثرموديناميكي الكمي
**Quantum Thermodynamic Trading Engine (QTT) — v6.1 Singularity**

> **الغرض من هذا الملف**: أن يتمكّن أي شخص — حتى لو لم يقرأ البوت ولا الأساس النظري من قبل — من فهم البوت بالكامل، وتشغيله بأمان، وتعديله بثقة، **دون أن يكسر قلبه الفيزيائي**.

> **الجمهور المستهدف**: مطوّر جديد ينضم للمشروع، أو أنت بعد 6 أشهر من الآن.

> **القاعدة الذهبية قبل أي شيء**: اقرأ **§ 10 — التحذيرات الحمراء** أولاً قبل أي تعديل. هذه المنطقة المقدسة، وأي تلاعب بها **يُفسد البوت بأكمله**.

---

## § 0 — خريطة الملف السريعة

| القسم | الموضوع |
|---|---|
| § 1 | ما هو هذا البوت؟ |
| § 2 | الملفات والبنية |
| § 3 | الأساس النظري — الشرح الكامل |
| § 4 | دورة حياة الصفقة من A إلى Z |
| § 5 | إدارة الرافعة والمخاطرة |
| § 6 | الحماية (SL/TP) — المعمارية الجديدة |
| § 7 | وضع الباكتيست |
| § 8 | وضع Live/Testnet |
| § 9 | الميزات الاختيارية (MFAL, OB Entry, ML Filter) |
| **§ 10** | **التحذيرات الحمراء — ما لا يجب لمسه أبداً** |
| § 11 | المشاكل الشائعة والحلول |
| § 12 | دليل التعديل الآمن |
| § 13 | أوامر التشغيل الشاملة |
| § 14 | سجل التغييرات الكبير |

---

## § 1 — ما هو هذا البوت؟

### 1.1 الجملة الأساسية

> **"السوق نظام ديناميكي على متعدد شعب معلوماتي. نتتبع جسيم (السعر) يتحرك فيه. عندما يمر بحالة منخفضة الإنتروبيا وطاقة حرة سالبة، يكون قد وصل إلى نقطة انعكاس محتملة → ندخل."**

هذا ليس بوت arbitrage، ولا trend-following، ولا ML black box. إنه **نموذج فيزيائي للسوق**.

### 1.2 ما الذي يفعله عملياً

1. يأخذ بيانات OHLCV من Binance USDT-M Futures.
2. يحوّل كل شمعة إلى متجه 7 أبعاد (فضاء الطور).
3. يكمّم الحالة إلى رموز (KMeans).
4. يحسب الإنتروبيا، الطاقة الحرة، الاحتكاك.
5. يبني معادلة الحركة (Langevin).
6. يستخرج احتمال الانعكاس (Boltzmann).
7. يدخل عندما يكون الاحتمال كافياً.
8. يدير SL/TP بحماية متعددة الطبقات.

### 1.3 الفلسفة

البوت **ليس** يبحث عن "trend صاعد". يبحث عن **لحظات تفقد فيها الإنتروبيا توازنها**. هذه اللحظات قصيرة، لكنها **حتمية فيزيائياً** — ولهذا يمكن التداول عليها.

---

## § 2 — الملفات والبنية

### 2.1 الملفات الجوهرية

| الملف | الدور | يُعدَّل؟ |
|---|---|---|
| `trading_live.py` | البوت الكامل | ⚠️ فقط مع فهم § 10 |
| `state.md` | هذا الملف | ✅ نعم، حدّثه عند كل تعديل |
| `الأساس النظري الكامل (نهائي).md` | المرجع النظري | 🚫 للقراءة فقط |

### 2.2 الملفات المُنشأة تلقائياً

| الملف | المحتوى |
|---|---|
| `live_state_{mode}.json` | المراكز المفتوحة |
| `pending_orders_{mode}.json` | الأوامر المعلّقة |
| `symbol_meta_{mode}.json` | الرافعة/margin لكل رمز |
| `live_peak_{mode}.json` | الذروة التاريخية لرأس المال |
| `trades_log_{mode}.jsonl` | سجل كل صفقة |
| `mfal_weights.json` | أوزان MFAL (إن مفعّل) |
| `mfal_history.jsonl` | تاريخ نتائج MFAL |
| `kill_switch.json` | ملف إيقاف الطوارئ |
| `market_data_cache/` | OHLCV parquet cache |
| `asset_cache/` | AssetData pickle cache |

### 2.3 بنية الملف الرئيسي

```
§ 0. Config                    ← الإعدادات
§ 1. scan_top_assets           ← مسح الأصول
§ 2. Cache (OHLCV + SubBars)   ← تحميل البيانات
§ 3. compute_features          ← ℝ⁷ features
§ 4. compute_dynamic_k         ← K الديناميكي
§ 5. entropy_series            ← الإنتروبيا
§ 6. compute_geometry          ← الانحناء والحجم
§ 7. compute_lyapunov_dynamic  ← أس ليابونوف
§ 8. compute_tri               ← كاشف الانعكاس
§ 9. find_optimal_entry        ← نقطة الدخول
§ 10. apply_slippage           ← نموذج الانزلاق
§ 11. Data classes             ← AssetData, Signal, ...
§ 12. process_asset            ← المسار الكامل لأصل واحد
§ 13. build_signals            ← بناء الإشارات
§ 14. correlation              ← مصفوفة الارتباط
§ 15. simulate_portfolio       ← محاكاة المحفظة (backtest)
§ 16. compute_metrics          ← الإحصاءات
§ 17. print_report             ← التقرير
§ 18. Fill Engine + Adaptive   ← تنفيذ Maker
§ 19. Live / Testnet           ← الحلقة الحية
§ 20. main()                   ← نقطة الدخول
```

---

## § 3 — الأساس النظري — الشرح الكامل

### 3.1 فضاء الحالة ℝ⁷

كل شمعة تُحوَّل إلى متجه:

$$\mathbf{x}_t = [\mu_t, \sigma_t, \gamma_{1,t}, \gamma_{2,t}, R_t, \bar{V}_t, \Delta P_t]$$

- $\mu$ = متوسط اللوغاريتمات (الانحراف الاتجاهي)
- $\sigma$ = الانحراف المعياري (الحرارة)
- $\gamma_1$ = الالتواء (عدم التناظر)
- $\gamma_2$ = التفرطح (سمك الذيول)
- $R$ = المدى (max − min)
- $\bar{V}$ = متوسط الحجم
- $\Delta P$ = التغير السعري المتراكم

**التطبيع**: $\hat{x} = x / \|x\|$ إذا $\|x\| > 1$. هذا "compactification" يمنع أي بُعد من الهيمنة.

**في الكود**: `compute_features()` → `_features_kernel()` (numba).

### 3.2 التكميم الرمزي (KMeans)

KMeans يقسم $\mathbb{R}^7$ إلى K مجموعات. كل مجموعة = **رمز** $s \in \{0, ..., K-1\}$.

**K الديناميكي**:
$$K_C = K_{max} \cdot e^{-\alpha \cdot C/A_{DV}}, \quad K_{data} = \frac{n_{train}}{100}$$
$$K = \min(K_C, K_{data})$$

- رأس مال صغير → K كبير (دقة أعلى)
- رأس مال كبير → K صغير (SNR عالي)

**في الكود**: `compute_dynamic_k()`, `fit_kmeans()`, `assign()`.

### 3.3 الإنتروبيا

$$H(t) = -\sum_{k=0}^{K-1} p_k(t) \log_2 p_k(t)$$

- $H = 0$ → سوق **بلوري** (قابل للتنبؤ)
- $H = \log_2 K$ → سوق **غازي** (عشوائي تماماً)
- $H \in (0, \log_2 K)$ → **منطقة الانعكاس**

**المشتقات**: $\dot{H} = dH/dt$, $\ddot{H} = d^2H/dt^2$.

- $\dot{H} < 0$: النظام يتبلور
- $\ddot{H} < 0$: التبلور يتسارع

**في الكود**: `entropy_series()` → `_entropy_kernel()` (numba).

### 3.4 الطاقة الحرة

$$E_{therm} = \sigma(r_{t-N:t}) \quad \text{(طاقة حركية)}$$
$$F = E_{therm} - H \quad \text{(Helmholtz: } F = U - TS \text{)}$$

- $F$ كبير → العمل متاح
- $F$ سالب → النظام في توازن
- **نبحث عن** $\dot{F} < 0$

**في الكود**: `process_asset` — حساب `E_therm`, `F`, `dF`.

### 3.5 قوة المقياس (Gauge Force)

من مصفوفة الانتقال $T_{ij} = P(s_{t+1}=j | s_t=i)$:
$$\mathcal{F} = \|T - T^T\|_F$$

هذا يقيس **انتهاك التناظر الزمني** — الاتجاه.

- $\mathcal{F} = 0$ → زمني متماثل، لا اتجاه
- $\mathcal{F} > 0$ → اتجاه مُفضّل

**في الكود**: `compute_gauge_force_and_gap()` → `_gauge_kernel()` (numba).

### 3.6 الاحتكاك الإنتروبي

$$\Gamma(H) = \gamma_0 + \kappa \cdot e^{\xi(1 - H/H_{max})}$$

- $H = H_{max}$ (فوضى) → $\Gamma \approx 0.11$
- $H = 0$ (بلورة) → $\Gamma \approx 0.28$

**الفكرة**: النظام المنظم يقاوم التغيير أكثر.

**في الكود**: `compute_entropy_friction()`.

### 3.7 التسارع الجيوديسي (Langevin)

$$\ddot{q}(t) = \underbrace{-\nabla F}_{جاذبية} + \underbrace{q \cdot \mathcal{F} \cdot \dot{H}}_{قوة \, المقياس} - \underbrace{\Gamma \cdot \dot{H}}_{احتكاك}$$

- $-\nabla F$: النظام يتجه نحو توازن
- $q \cdot \mathcal{F} \cdot \dot{H}$: يدوّر المسار (مثل قوة لورنتز)
- $-\Gamma \dot{H}$: يبطّئ الحركة

**المجموع**: مسار منحني مبدد — بالضبط سلوك سعر في سوق غير متوازن.

**في الكود**: `process_asset` — حساب `geodesic_accel`.

### 3.8 التفعيل Boltzmann

$$P_{act} = \exp\left(-\frac{\Gamma}{|\ddot{q}| \cdot T_{info}}\right)$$

- **Arrhenius**: $k = A e^{-E_a/k_BT}$
- $E_a = \Gamma$ (طاقة التنشيط)
- $k_B T = |\ddot{q}| T_{info}$ (الطاقة المتاحة)

**عتبة**: $P_{act} < 0.35$ → لا ندخل.

**في الكود**: `build_signals` — أول فحص.

### 3.9 Kelly الديناميكي

$$f^* = f_{min} + (f_{max} - f_{min}) \cdot \sigma\left(\frac{|\ddot{q}|}{\Gamma} e^{-0.01/T} - 2\right)$$

- $\sigma(x) = 1/(1+e^{-x})$ (Sigmoid)
- -2.0: إزاحة لتوسيط الدالة
- $f^* \in [f_{min}, f_{max}]$ دائماً

**في الكود**: `compute_geodesic_kelly()`.

### 3.10 الوقف الجيوديسي (Fisher Stop)

$$d_{SL} = \kappa \cdot \frac{u}{1 + 5\Gamma} \cdot \sigma_{price}, \quad u = \frac{V}{\bar{V}}$$

- $u$ = عدم اليقين (state volume)
- $\Gamma$ = احتكاك
- $\sigma_{price}$ = $E_{therm} \times price$

**clip**: $[3\sigma, 8\sigma]$ حيث 3σ = Fisher coherence length.

**في الكود**: `compute_geodesic_stop()`.

### 3.11 سعر النفق (Tunnel Entry)

$$\tau = p - \max(\kappa \cdot \sigma_{price}, \frac{1}{2} ATR)$$

هذا **حاجز الطاقة** الذي يجب أن يدفعه السوق قبل أن ندخل.

- إذا انخفض السوق إليه → دخلنا (Limit order)
- إذا لم ينخفض → إشارة ميتة (Stage 2 fallback)

**في الكود**: `build_signals` — حساب `tunnel_entry_p`.

### 3.12 جدول الاشتقاق الكامل

| المعامل | المعادلة | النظرية |
|---|---|---|
| $x_t$ | 7-tuple | Phase Space |
| $s_t$ | KMeans | Vector Quantization |
| $H$ | $-\sum p\log p$ | Shannon |
| $\Gamma$ | $\gamma_0 + \kappa e^{\xi(1-H/H_m)}$ | Entropic Friction |
| $F$ | $E - H$ | Helmholtz |
| $\mathcal{F}$ | $\|T-T^T\|_F$ | Yang-Mills Gauge |
| $\ddot{q}$ | $-\nabla F + q\mathcal{F}\dot{H} - \Gamma\dot{H}$ | Langevin |
| $P_{act}$ | $e^{-\Gamma/(|\ddot{q}|T)}$ | Arrhenius |
| $f^*$ | Logistic of $|\ddot{q}|/\Gamma$ | Kelly |
| $d_{SL}$ | $\kappa u \sigma / (1+5\Gamma)$ | Fisher |
| $\tau$ | $p - \max(4\sigma, ATR/2)$ | Energy Barrier |

---

## § 4 — دورة حياة الصفقة من A إلى Z

```
┌──────────────────────────────────────────────────────────────┐
│ 1. LOAD                                                       │
│    - قراءة OHLCV من البورصة (أو الكاش)                        │
│    - تحويل إلى DataFrame                                       │
│    - التحقق المحلي (cache health)                              │
├──────────────────────────────────────────────────────────────┤
│ 2. PROCESS (لكل رمز)                                          │
│    - compute_features → X (N×7)                                │
│    - compute_dynamic_k → K                                     │
│    - KMeans → sym_q                                            │
│    - entropy_series → H, dH, d2H                               │
│    - E_therm, F, dF                                            │
│    - gauge_force, delta_gap                                    │
│    - friction Γ                                                │
│    - geodesic_accel                                            │
│    - compute_geometry → C, V                                   │
│    - score                                                     │
│    - ema200, atr14, adv_usd                                    │
│    - T_info, tri, KE, PE, ME, lya                              │
│    → AssetData                                                 │
├──────────────────────────────────────────────────────────────┤
│ 3. BUILD SIGNALS                                              │
│    - P_activation > 0.35                                       │
│    - Direction from z_dev                                      │
│    - Compute tunnel_entry_p                                    │
│    - sl_dist, sl, tp1                                          │
│    - Dynamic risk (Kelly)                                      │
│    - Filters (SR, ML, trade)                                   │
│    → Signal list                                               │
├──────────────────────────────────────────────────────────────┤
│ 4. DEDUPLICATE                                                 │
│    - حسب (symbol, time bucket)                                 │
├──────────────────────────────────────────────────────────────┤
│ 5. SIMULATE (backtest) or ENTER (live)                        │
│    Backtest: precompute_entry_fills → Stage 1/2                │
│    Live: place_pending_entry → pending_orders                  │
├──────────────────────────────────────────────────────────────┤
│ 6. MONITOR                                                     │
│    - فحص SL/TP كل دورة (LIVE_PRICE_ENABLED)                    │
│    - تحديث Trailing                                            │
│    - Partial TP                                                │
│    - Breakeven                                                 │
│    - LiqProximity                                              │
│    - Reconcile with exchange                                   │
├──────────────────────────────────────────────────────────────┤
│ 7. EXIT                                                        │
│    - SL / TP / Apex / Topo-Div / MaxHold                       │
│    - Cancel protective orders (بعد التأكيد)                    │
│    - Log trade                                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## § 5 — إدارة الرافعة والمخاطرة

### 5.1 الرافعة الديناميكية (الأساسية)

$$L(C) = \text{clip}\left(\frac{L_{BASE}}{\sqrt{C/C_0}}, L_{min}, L_{max}\right)$$

- $L_{BASE} = 50$
- $C_0$ = رأس المال الابتدائي
- تُقرَّب إلى tier صالح للبورصة (`_symbol_tiers`)

**في الكود**: `compute_dynamic_leverage()`, `compute_adaptive_leverage()`.

### 5.2 LevCap (سقف السيولة)

$$L_{liq} = \text{compute\_max\_leverage\_by\_liq}(SL_{frac}, MMR, safety)$$

يمنع الرافعة إذا كانت SL قريبة جداً من Liq.

**في الكود**: `compute_max_leverage_by_liq()`.

### 5.3 Portfolio Heat

$$\text{heat\_used} = \sum_{pos} \text{dyn\_risk}(pos)$$

إذا `heat_used >= PORTFOLIO_HEAT_MAX (10%)` → لا مراكز جديدة.

**في الكود**: `compute_portfolio_risk_frac()`.

### 5.4 Drawdown Multiplier

| Drawdown | Multiplier |
|---|---|
| 0-15% | 1.0 |
| 15-30% | 0.25 |
| 30-50% | 0.10 |
| 50-70% | 0.05 |

**في الكود**: `_get_risk_multiplier()`.

---

## § 6 — الحماية (SL/TP) — المعمارية الجديدة

### 6.1 الفكرة الأساسية

**قبل patch `patch_live2_place_first.py`**: كان البوت يستخدم "cancel-then-place" → نافذة تعرية → SL مفقود، SLs متراكمة.

**بعد الـ patch**: **Place-First** + **Pre-Flight** → لا نافذة تعرية.

### 6.2 التدفق الصحيح

```
_place_protective_orders(exchange, sym, pos):
  1. Pre-flight validate SL/TP targets
     - distance from mark >= MIN_STOP_DISTANCE_BPS (50)
     - side matches
     - notional >= MIN_NOTIONAL
     ↓
     إذا فشل → اخرج، لا تلمس شيئاً
  2. اقرأ الأوامر الواقية الموجودة
  3. صنّف:
     - موجود بسعرنا → keep
     - موجود بسعر مختلف → stale
  4. ضع القطع المفقودة (reduceOnly=True)
     ↓
     إذا فشل SL → اخرج، القديم محفوظ
  5. الآن فقط ألغِ stale (بعد التأكيد)
```

### 6.3 لماذا `reduceOnly` بدل `closePosition`

- `closePosition=True`: Binance يرفض SL ثانياً (لا يمكن تعايش)
- `reduceOnly=True`: يسمح بتعايش SLs متعددة → Place-First ممكن

**النتيجة**: خلال عملية التبديل، لدينا لحظة SLs متعددة. آمن — كلها reduceOnly، أول واحد يُطلَق يُغلق المركز، الباقي Binance يحذفه تلقائياً.

### 6.4 Breakeven الذكي

```
_lv_breakeven(exchange, sym, pos, now):
  1. إذا SL موجود بنفس السعر → no-op
  2. Pre-flight:
     - إذا الجديد قريب جداً من mark → SKIP
     - اترك SL القديم محفوظاً
  3. ضع SL الجديد (reduceOnly)
  4. إذا فشل → اخرج، القديم محفوظ
  5. ألغِ SL القديم (surgical)
```

**لا نافذة تعرية إطلاقاً.**

### 6.5 الحمايات الأخرى

- **Trailing**: يُحدَّث عبر `_sync_protective_orders`
- **Partial TP**: يُنفَّذ على البورصة أو داخلياً
- **Apex**: خروج عند استنفاد التكامل الحركي
- **Topo-Div**: خروج عند انفصال توبولوجي
- **LiqProximity**: خروج طارئ عند 70% من Liq
- **Kill Switch**: HMAC-authenticated طوارئ

---

## § 7 — وضع الباكتيست

### 7.1 الميزات

- بيانات 730 يوم (2 سنة) افتراضياً
- محاكاة دخول Stage 1/2
- Sub-bars لفض ambiguity داخل الشمعة
- Realistic fees (Maker/Taker)
- LevCap + LiqGate للتوافق مع Live
- Trade log JSONL

### 7.2 الأوضاع

```bash
# كلاسيكي
python3 trading_live.py --mode backtest --capital 100 ...

# مع OB entry (لـ --no-fixed-price فقط)
python3 trading_live.py --mode backtest --no-fixed-price \
  --order-book-entry ...
```

### 7.3 المخرجات

- `trades_log_backtest.jsonl`
- `quantum_v6_results.png`
- تقرير مفصّل في stdout

---

## § 8 — وضع Live/Testnet

### 8.1 الميزات

- حلقة كل `LIVE_POLL_SECS = 5` ثواني
- Non-blocking pending orders
- Live price feed (ticker)
- Reconcile مع البورصة
- Persistent state (JSON)
- Rate-limit tracker
- Kill switch (file-based HMAC)

### 8.2 دورة Live

```
1. Kill switch check
2. Read pending_orders → monitor
3. Reconcile symbol_meta
4. Refresh top_syms (كل 4 ساعات)
5. Read balance
6. Reconcile positions
7. Update assets (fetch + cache)
8. Monitor open positions (SL/TP/Trail)
9. Build signals
10. Filter (SR/ML/Rule)
11. Enter new positions (OB or S1/S2)
12. Reconcile state
13. Persist state
14. Sleep
```

### 8.3 الملفات الحساسة

- `live_state_*.json`: المراكز المفتوحة (يُحدَّث تلقائياً)
- `pending_orders_*.json`: الأوامر المعلّقة
- `symbol_meta_*.json`: الرافعة لكل رمز
- `kill_switch.json`: ملف إيقاف الطوارئ

---

## § 9 — الميزات الاختيارية

### 9.1 MFAL — Multi-Factor Adaptive Leverage

**معطّل افتراضياً**. يُفعَّل بـ `--mfal`.

$$L_{final} = L_{core} \cdot Q \cdot R \cdot T \cdot M$$

- $Q$ = جودة الإشارة (logistic، يتعلّم)
- $R$ = قدرة المحفظة (ارتباط، حرارة، drawdown)
- $T$ = وقت اليوم (سيولة)
- $M$ = البنية الدقيقة (spread/depth)

**الملفات**: `mfal_weights.json`, `mfal_history.jsonl`.

### 9.2 OB Entry — Order-Book-Aware Entry

**معطّل افتراضياً**. يُفعَّل بـ `--order-book-entry`.

**القاعدة**: بعد `patch_live2_ob_restrict.py`، يعمل فقط مع `--no-fixed-price`.

**المنطق**:
1. Pre-flight: anchor قريب من mid
2. كشف toxic flow → abort
3. بناء σ-ladder (5 مستويات)
4. GTX placement
5. مراقبة 60s + abort conditions

### 9.3 ML Filter

**معطّل افتراضياً**. يُفعَّل بـ `--ml-filter`.

يستخدم `ml_filter.pkl` (model مُتعلَّم مسبقاً) لرفض الإشارات ذات `P_win < threshold`.

### 9.4 Rule Filter

**معطّل افتراضياً**. يُفعَّل بـ `--rule-filter`.

4 قواعد إحصائية:
- rvol24 أقل من q33
- dist_high أعلى من q66
- tf_std أعلى من q66
- range_pos أعلى من q66

رفض إذا `≥ 2 قواعد` اجتمعت.

### 9.5 Sing-Timing

**معطّل افتراضياً**. يُفعَّل بـ `--sing-timing`.

يكشف حالة الرنين (DORMANT/EMERGING/ACTIVE/DECAYING) بناءً على مرتبة `geodesic_accel`.

**الطبقات**:
- L1: تعديل timeout حسب الحالة
- L2 (`--sing-active`): ترقية GTX إلى marketable عند ACTIVE
- L3A (`--sing-funding-guard`): تجنّب الدخول قبل التمويل
- L3B (`--sing-risk-boost`): رفع المخاطرة × 1.2 عند ACTIVE

---

## § 10 — التحذيرات الحمراء ⚠️

### 🔴 القاعدة الأولى

**لا تعدّل أي معادلة فيزيائية مهما كان السبب.** كل معادلة مشتقة رياضياً. أي تعديل يُفسد البوت بأكمله.

---

### 🔴 المنطقة المقدسة 1: معادلات الفيزياء الأساسية

**هذه المعادلات لا تُلمَس أبداً:**

#### 1.1 `compute_features` — فضاء ℝ⁷

```python
vec = np.array([np.mean(r), s, skew(r,bias=False), kurtosis(r,bias=False),
                np.max(p)-np.min(p), np.mean(v), (closes[i]-closes[i-N])/closes[i-N]])
nm = np.linalg.norm(vec)
if nm > 1.0: vec /= nm
```

**السبب**: هذا **توقيع** السوق في 7 أبعاد. أي تغيير في الأبعاد أو الترتيب أو الصيغة **يُنقِص الفضاء ويجعل KMeans عديم المعنى**.

**ما يمكن تغييره**: فقط `N` (Window) — لكن بحذر.

#### 1.2 `compute_dynamic_k` — K الديناميكي

```python
k_c = int(np.floor(CFG.K_MAX * np.exp(-CFG.KQUANT_ALPHA * capital_ratio)))
k_c = max(CFG.K_MIN, min(CFG.K_MAX, k_c))
k_data = max(CFG.K_MIN, n_train_features // max(min_pts, 1))
k_c = min(k_c, k_data)
```

**السبب**: المعادلة $K_C = K_{max} e^{-\alpha C/ADV}$ مشتقة من تحليل SNR. تغييرها يُزيح نافذة K بعيداً عن القيم المُعايَرة.

#### 1.3 `entropy_series` — Shannon Entropy

```python
H[i] = -np.sum(p * np.log2(p + 1e-12))
```

**السبب**: هذا **قلب البوت**. الإنتروبيا تُستخدم في كل مكان: الاحتكاك، الطاقة الحرة، الكشف عن التبلور. `np.log2` مهم (bits وليس nats).

#### 1.4 `compute_entropy_friction`

```python
gamma = CFG.GAMMA_0 + CFG.KAPPA * np.exp(CFG.XI * (1.0 - S_ratio))
```

**السبب**: الأُس `ξ(1-H/H_m)` هو أساس **الفرق بين النظام المنظم والفوضوي**. تغيير `ξ` يُفسد ميزان الاحتكاك.

#### 1.5 `geodesic_accel` — Langevin

```python
grad_F = -dF[i]
lorentz = CFG.LORENTZ_CHARGE_Q * gauge_force[i] * dH[i]
fric_force = friction[i] * dH[i]
geodesic_accel[i] = grad_F + lorentz - fric_force
```

**السبب**: هذا **معادلة الحركة**. كل حد مشتق من فيزياء معروفة:
- `grad_F`: القانون الثاني
- `lorentz`: قوة المقياس
- `fric_force`: الاحتكاك

**تغيير أي حد** = تحويل نظام فيزيائي إلى نظام آخر.

#### 1.6 `compute_gauge_force_and_gap`

```python
A = T_mat - T_mat.T
gauge_force[i] = np.linalg.norm(A, ord='fro')
```

**السبب**: `T - T^T` يقيس **انتهاك التناظر الزمني** = الاتجاه. هذا هو "البوصلة" الأساسية للبوت.

#### 1.7 `P_activation` في `build_signals`

```python
P_activation = np.exp(-fric_val / (force_mag * T_info))
if P_activation < 0.35: continue
```

**السبب**: Boltzmann activation. **لا تُغيِّر العتبة 0.35** دون اختبار A/B شامل. قد تُفرِغ البوت من الإشارات أو تُغرقُه بها.

#### 1.8 `compute_geodesic_kelly`

```python
force_ratio = accel / fric
thermal_damp = np.exp(-0.01 / (T_info + 1e-6))
x = (force_ratio * thermal_damp) - 2.0
sigmoid = 1.0 / (1.0 + np.exp(-x))
f_star = cfg.MIN_RISK + (cfg.MAX_RISK - cfg.MIN_RISK) * sigmoid
```

**السبب**:
- `Sigmoid` يحفظ $f^* \in [min, max]$
- `-2.0` إزاحة معايرة
- `exp(-0.01/T)` تخميد حراري

**لا تُغيِّر -2.0** دون فهم.

#### 1.9 `compute_geodesic_stop`

```python
uncertainty = np.clip(ad.V[fi] / (np.mean(ad.V) + 1e-9), 0.5, 3.0)
sl_sigma = (_sl_kappa * uncertainty) / (1.0 + friction * 5.0)
sl_sigma = float(np.clip(sl_sigma, _min_s, _max_s))
```

**السبب**: هذا **Fisher coherence length**. تغيير `5.0` يُغيّر كيفية تفاعل الاحتكاك مع SL.

#### 1.10 `tunnel_entry_p`

```python
_friction_dip = _fd_kappa * _sigma_price_bs
_entry_dip = max(_friction_dip, 0.5 * _atr_dip)
tunnel_entry_p = (p - _entry_dip) if action == "BUY" else (p + _entry_dip)
```

**السبب**: النفق هو **حاجز الطاقة**. الطريقة التي يُحسب بها تحدد متى ندخل.

---

### 🔴 المنطقة المقدسة 2: مسار `process_asset`

```python
def process_asset(symbol, df, km_ext=None, current_capital=None, sub_df=None):
    # ...
    X = compute_features(closes, vols, N)
    dyn_k = compute_dynamic_k(...)
    km = fit_kmeans(X[:train_end], k=dyn_k)
    sym_q = assign(X, km)
    H = entropy_series(sym_q, k=dyn_k)
    dH = np.diff(H, prepend=H[0])
    d2H = np.diff(dH, prepend=dH[0])
    # ... (K-Fallback)
    E_therm = ...
    F = E_therm - H
    dF = np.diff(F, prepend=F[0])
    T_info = ...
    gauge_force, delta_gap = compute_gauge_force_and_gap(...)
    friction = compute_entropy_friction(...)
    geodesic_accel = ...
    # ... (score)
```

**لا تُعدِّل ترتيب الحسابات**. كل خطوة تعتمد على السابقة. إذا غيّرت الترتيب، ستحصل على مخرجات خاطئة.

**استثناء وحيد مسموح**: إضافة K-Fallback (كما في `patch_live2_robust_assets.py`) — لأن هذا **استمرارية** للنظرية، ليس تغييراً لها.

---

### 🔴 المنطقة المقدسة 3: عتبات `build_signals`

```python
if P_activation < 0.35: continue
if abs(_z_dev) < 1.5: continue
if ad.score[fi] < CFG.MIN_SCORE: continue
if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue
```

**لا تُغيِّر هذه العتبات** دون:
1. اختبار A/B على الأقل 100 صفقة
2. مقارنة Sharpe قبل/بعد
3. تحديث هذا الـ state.md

**العتبات الحساسة**:
- `P_activation < 0.35`: تفلتر 80% من الإشارات
- `|z_dev| < 1.5`: تفلتر الانحرافات الصغيرة
- `MIN_SCORE`: الجودة الإجمالية
- `sl_dist * 2 < fee × tunnel`: حماية من صفقات غير مربحة

---

### 🔴 المنطقة المقدسة 4: إدارة المخاطرة

```python
# Kelly
f_star = cfg.MIN_RISK + (cfg.MAX_RISK - cfg.MIN_RISK) * sigmoid

# Portfolio heat
heat_available = max(0.0, heat_max - heat_used)

# Drawdown
dd_mult = _get_risk_multiplier(drawdown)

# Sizing
risk_amt = equity_base * risk_frac
qty = risk_amt / delta
```

**لا تُغيِّر صيغة تحديد qty**. هذه مبنية على **حفظ الطاقة**:
$$\text{risk} = \text{equity} \times f^* \Rightarrow \text{qty} = \frac{\text{risk}}{\Delta P}$$

تغييرها = تغيير فيزياء الحجم.

---

### 🔴 المنطقة المقدسة 5: نموذج الانزلاق والرسوم

```python
def apply_slippage(price, qty, adv_usd, action, mode="backtest", is_taker=False):
    if mode != "backtest": return price
    if not is_taker: return price
    bps = _taker_slippage_bps(adv_usd)
    slip_frac = bps * 1e-4
    ...

def _exit_is_taker(exit_rsn: str) -> bool:
    if ("Emergency" in r) or ("Hard TP" in r) or ("LiqProximity" in r):
        return True
    return False
```

**لا تُغيِّر هذا**. يحاكي الواقع بدقة. تغييره يجعل الباكتيست غير متطابق مع Live.

---

### 🔴 المنطقة المقدسة 6: معادلات AssetData

كل حقل في `AssetData`:
- `closes, highs, lows, volumes`: OHLCV
- `X, sym_q`: features و clusters
- `H, dH, d2H`: entropy
- `E_therm, F, dF`: energy
- `C, V`: geometry
- `h, score`: HMM state و score
- `ema200, ema_accel`: EMA
- `atr14, adv_usd`: ATR و ADV
- `KE, PE, ME`: kinetic/potential/mechanical energy
- `dKE, lya`: energy derivative و Lyapunov
- `tri`: TRI sensor
- `T_info`: informational temperature
- `gauge_force, friction, delta_gap, geodesic_accel`: unified theory
- `score_q95_train`: adaptive threshold

**لا تُغيِّر أنواع أو أسماء هذه الحقول**. كل الكود يعتمد عليها.

---

### 🟡 المنطقة الحساسة 1: حماية SL/TP

**بعد `patch_live2_place_first.py`**، أصبحت الحماية:
- Place-First (لا cancel-then-place)
- Pre-flight validation
- reduceOnly بدل closePosition

**لا ترجع** إلى `closePosition=True` أو `_cancel_all_protective_orders` قبل الوضع.

**لا تُزِل**:
- `_lv_preflight_check`
- `_lv_cancel_stale_legs`
- الفحص المسبق في `_lv_breakeven`
- الفحص المسبق في `_lv_ensure_protection`

---

### 🟡 المنطقة الحساسة 2: ccxt 4.x fixes

**لا ترجع** إلى:
- `tiers[0]` (بدل `_extract_tier_entry`)
- `fetch_open_orders(sym)` وحده (بدل `_lv_open_orders_all`)
- `symbol=None` في `compute_dynamic_leverage`

هذه الإصلاحات حيوية لـ:
- MMR الحقيقي
- Leverage tiers الحقيقية
- رؤية الأوامر الشرطية

---

### 🟡 المنطقة الحساسة 3: تكامل Live

**لا تُغيِّر**:
- `_lv_reconcile_state_machine` (adopt orphans)
- `_lv_startup_order_cleanup` (cancel stale only)
- `monitor_pending_orders` (pending lifecycle)
- `_lv_manage_position` (per-cycle position mgmt)
- `_lv_exit_precheck` (double-confirm)

---

### 🟢 مناطق آمنة للتعديل

- `Config`: كل الحقول (لكن انتبه للتحذيرات)
- `argparse`: إضافة flags جديدة
- `print_report`: تنسيق فقط
- `plot_results`: رسم فقط
- `_trade_log_*`: تسجيل فقط
- `_cache_*`: تحسينات cache
- `_rate_*`: rate limit

---

### 🔴 التحذير النهائي

> **البوت مبني على نظرية فيزيائية مترابطة. كل معادلة تعتمد على الأخرى. أي تعديل عشوائي في المعادلات = انهيار النظام بالكامل.**

> **إذا كنت تريد تعديلاً، فاتبع § 12.**

---

## § 11 — المشاكل الشائعة والحلول

### 11.1 مشاكل Live

| الأعراض | السبب | الحل |
|---|---|---|
| `[Gauge-Filter] pool too small` يتكرر | `assets` فارغ | ✅ تم إصلاحه بـ `patch_live2_robust_assets.py` |
| `[DIAG] assets empty` | `process_asset` يُرجع None | نفس الإصلاح |
| SLs متراكمة | cancel-then-place | ✅ `patch_live2_place_first.py` |
| SL مفقود بعد breakeven | pre-flight لم يُطبَّق | ✅ `patch_live2_place_first.py` |
| `-2010` GTX rejected | target يعبر السبريد | `_gtx_preflight` (موجود) |
| `-4028` leverage | tier غير صالح | `_symbol_tiers` (موجود) |
| `-1111` qty precision | step size | `_round_qty` (موجود) |
| `-4164` min notional | order صغير | `_get_min_notional` (موجود) |
| `-2022` reduceOnly | position gone | `_lv_exit_precheck` (موجود) |
| Kill switch triggered | ملف HMAC | افحص `kill_switch.json` |

### 11.2 مشاكل Backtest

| الأعراض | السبب | الحل |
|---|---|---|
| صفر صفقات | فلاتر صارمة | خفّف: `--min-score 2`, `--no-trailing` |
| Drawdown عالٍ | رافعة عالية | خفّض `--max-risk`, `--leverage` |
| Sharpe سلبي | ظروف السوق | استخدم فترة أخرى (`--history-days`) |
| `precompute_entry_fills: 0/0` | لا إشارات | نفس صفر صفقات |

### 11.3 مشاكل الأداء

| الأعراض | السبب | الحل |
|---|---|---|
| بطيء في البدء | fetch history | `--history-days 90` للـ live |
| CPU 100% | `PARALLEL_PROCESSING=False` | شغّل default |
| Memory كبيرة | `LIVE_TAIL_BARS=8000` | خفّض لـ 4000 |

---

## § 12 — دليل التعديل الآمن

### 12.1 قبل أي تعديل

**اقرأ § 10 كاملاً**. تأكد أن تعديلك **ليس** في المنطقة المقدسة.

### 12.2 خطوات التعديل

```bash
# 1. Backup
cp trading_live.py trading_live.py.$(date +%s).bak

# 2. تحقق من الصياغة قبل أي شيء
python3 -m py_compile trading_live.py

# 3. إذا كنت تعدّل معادلة، شغّل اختبار A/B
python3 trading_live.py --mode backtest --history-days 30 ...
python3 trading_live.py --mode backtest --history-days 90 ...

# 4. قارن Sharpe, MaxDD, Win Rate
diff <(tail trades_log_backtest_old.jsonl) \
     <(tail trades_log_backtest_new.jsonl)
```

### 12.3 إذا أردت تغيير معامل

**غيّر معاملاً واحداً فقط** ثم:

1. شغّل backtest 90 يوم
2. قارن `mean_log_return`, `sharpe_ratio`, `max_drawdown_pct`
3. إذا تحسّن، احتفظ بالتغيير
4. إذا ساء، ارجع
5. **لا تُغيّر معاملين معاً** — لن تعرف أيهما السبب

### 12.4 إذا أردت إضافة ميزة

اتبع نمط MFAL:
1. أضف الحقول إلى `Config` (مع defaults متحفظة)
2. أضف المنطق **معطّلاً افتراضياً** (`_MYFEATURE_ENABLED = False`)
3. أضف CLI flag (`--my-feature`)
4. إذا ناجح، فعّله
5. سجّل في § 14

---

## § 13 — أوامر التشغيل الشاملة

### 13.1 Backtest كلاسيكي

```bash
python3 trading_live.py \
  --mode backtest \
  --capital 100 \
  --nassets 50 \
  --maxcon 2 \
  --timeframe 1h \
  --history-days 365 \
  --min-score 3 \
  --no-trailing \
  --tp-mult 5
```

### 13.2 Backtest مع Sell

```bash
python3 trading_live.py \
  --mode backtest \
  --enable-sell \
  --sell-gauge-pct 95 \
  --nassets 50 \
  --history-days 180 \
  --end-date 2026-10-08
```

### 13.3 Backtest مع OB Entry (`--no-fixed-price` فقط)

```bash
python3 trading_live.py \
  --mode backtest \
  --no-fixed-price \
  --order-book-entry \
  --ob-wait-s 60 \
  --ob-anchor-gap-bps 20 \
  --capital 100 \
  --history-days 90
```

### 13.4 Testnet آمن

```bash
export BINANCE_TESTNET_KEY="..."
export BINANCE_TESTNET_SECRET="..."

python3 trading_live.py \
  --mode testnet \
  --api-key $BINANCE_TESTNET_KEY \
  --api-secret $BINANCE_TESTNET_SECRET \
  --capital 100 \
  --live-capital 100 \
  --nassets 10 \
  --maxcon 1 \
  --min-score 3
```

### 13.5 Testnet مع MFAL

```bash
python3 trading_live.py \
  --mode testnet \
  --api-key $BINANCE_TESTNET_KEY \
  --api-secret $BINANCE_TESTNET_SECRET \
  --mfal \
  --capital 100 \
  --maxcon 1
```

### 13.6 Live (بعد اختبار طويل)

```bash
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."

python3 trading_live.py \
  --mode live \
  --api-key $BINANCE_API_KEY \
  --api-secret $BINANCE_API_SECRET \
  --capital 100 \
  --live-capital 100 \
  --nassets 10 \
  --maxcon 1 \
  --min-score 4
```

### 13.7 Kill Switch

```bash
# أيقظ الرقم السري
export KILL_SWITCH_SECRET="my-secret"

# أوقف البوت: أنشئ ملف kill_switch.json
python3 -c "
import json, hmac, hashlib, time
secret = 'my-secret'
reason = 'manual_stop'
token = hmac.new(secret.encode(), reason.encode(), hashlib.sha256).hexdigest()
with open('kill_switch.json', 'w') as f:
    json.dump({'state': 'TRIGGERED', 'reason': reason, 'token': token}, f)
"
```

### 13.8 Clear State

```bash
# بعد إيقاف البوت
python3 trading_live.py --mode backtest --clear-cache
```

---

## § 14 — سجل التغييرات الكبير

| التاريخ | التعديل | النطاق |
|---|---|---|
| 2026-10-07 | الإصدار الأساسي v6.1 | — |
| 2026-10-08 | ccxt 4.x fixes (tier extraction) | بنية تحتية |
| 2026-10-08 | Smart protection (preflight + place-first) | Live SL/TP |
| 2026-10-08 | MFAL (opt-in) | Leverage |
| 2026-10-08 | Unified entry (backtest=live) | Pricing |
| 2026-10-09 | OB Entry (opt-in) | Entry |
| 2026-10-09 | OB restrict to `--no-fixed-price` | Routing |
| 2026-10-09 | Robust assets (K-Fallback + prune) | Live startup |
| 2026-10-09 | Place-first + pre-flight | SL/TP |
| 2026-10-09 | هذا الـ state.md | Documentation |

---

## § 15 — المرجع السريع للمصطلحات

| المصطلح | المعنى |
|---|---|
| **Quantum** | كمية الحالة (رمز KMeans) |
| **N** | نافذة features (24 شمعة) |
| **W** | نافذة entropy (20 شمعة) |
| **L** | نافذة geometry (10 شمعة) |
| **K** | عدد الرموز (dynamic) |
| **E_therm** | طاقة حرارية = σ |
| **F** | طاقة حرة = E − H |
| **Γ** | احتكاك إنتروبي |
| **𝓕** | قوة مقياس (gauge) |
| **q̈** | تسارع جيوديسي |
| **T_info** | حرارة معلوماتية |
| **P_act** | احتمال تفعيل Boltzmann |
| **f\*** | كسر Kelly ديناميكي |
| **τ** | سعر النفق (tunnel) |
| **d_SL** | مسافة SL (Fisher) |
| **Signal** | إشارة دخول |
| **AssetData** | حاوية كل مؤشرات أصل |
| **OpenPosition** | مركز مفتوح (backtest) |
| **MFAL** | Multi-Factor Adaptive Leverage |
| **OB** | Order-Book |
| **GTX** | Post-Only (Binance) |

---

## § 16 — للمطور الجديد: ابدأ من هنا

### إذا كنت جديداً تماماً

1. **اقرأ § 1 و § 3** — فهم الفلسفة والنظرية
2. **اقرأ § 10** — اعرف ما لا يجب لمسه
3. **اقرأ § 4** — فهم دورة حياة الصفقة
4. **جرب backtest** (13.1) — شاهد المخرجات
5. **جرب Testnet** (13.4) — شاهد Live بدون مخاطرة

### إذا أردت تعديل معامل

1. انسخ `trading_live.py` كـ backup
2. غيّر معاملاً واحداً في `Config`
3. شغّل backtest مع `--history-days 30`
4. قارن المخرجات
5. إذا تحسّن، احتفظ. وإلا، ارجع.
6. حدّث § 14

### إذا أردت إضافة ميزة

1. اتبع نمط MFAL (opt-in)
2. اختبرها في backtest أولاً
3. وثّقها في § 9
4. حدّث § 14

### إذا اكتشفت مشكلة

1. افحص § 11 (المشاكل الشائعة)
2. إذا لم تكن موجودة، أضفها
3. إن كان الحل patch، أنشئه ووثّقه

---

## § 17 — الخلاصة الأخيرة

**البوت مبني على:**

> **"السوق نظام ديناميكي على متعدد شعب معلوماتي. نتتبع جسيم (السعر) يتحرك فيه. عندما يمر بحالة منخفضة الإنتروبيا وطاقة حرة سالبة، يكون قد وصل إلى نقطة انعكاس محتملة → ندخل."**

**قلب البوت الفيزيائي (لا يُلمَس أبداً):**
- فضاء ℝ⁷
- KMeans (تكميم)
- Shannon entropy
- Helmholtz free energy
- Yang-Mills gauge force
- Langevin equation
- Arrhenius activation
- Kelly criterion
- Fisher information stop

**كل ما هو خارج هذه القائمة: قابل للتعديل بحذر.**

**القاعدة الذهبية:**
> **لا تُعدِّل معادلة فيزيائية. عدّل تنفيذها فقط.**

---

**آخر تحديث**: 2026-10-09
**الإصدار**: QTT v6.1 Singularity + All Patches
**صاحب المشروع**: أنت
**للاستفسارات**: اقرأ § 3 كاملاً، ثم § 10

---

## ملاحظات على هذا الملف

هذا الملف مُصمَّم ليكون:

1. **قائماً بذاته** — لا يحتاج قراءة الأساس النظري الأصلي بالكامل، لكنه يُحيل إليه
2. **قابلاً للتحديث** — كل تعديل يُسجَّل في § 14
3. **آمناً للمطور الجديد** — يبدأ من § 16، يفهم § 3، يحترم § 10
4. **يحوي كل التحذيرات** — § 10 مفصّل بشكل هرمي (أحمر/أصفر/أخضر)
5. **عملياً** — § 13 يحوي كل أوامر التشغيل

**احفظه باسم `STATE.md`** في جذر المشروع بجانب `trading_live.py`.

**عند أي تعديل مستقبلي**: أضف سطراً في § 14، وحدّث القسم المناسب.
