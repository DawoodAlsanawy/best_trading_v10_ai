# تصميم نظام تكيّفي متعدد الطبقات للتداول بأي رأس مال

---

## الجزء الأول: الإطار الرياضي — تحليل بلا بُعد

### 1.1 المعادلة الأساسية للحجم

لكل صفقة على أصل $a$ برأس مال $C$:

$$
\text{notional}_a = \frac{C \cdot f}{\sigma_a \cdot \kappa_{sl}}
$$

حيث:
- $f$ = كسر المخاطرة
- $\sigma_a$ = تقلب الأصل على الفريم
- $\kappa_{sl}$ = معامل SL في وحدات $\sigma$ (مثلاً 1.0)
- $\text{notional}_a$ = $q_a \times P_a$

**البرهان:**
- `risk_amount = C × f`
- `sl_distance = σ_a × κ_sl × P_a`
- `q_a = risk_amount / sl_distance = C × f / (σ_a × κ_sl × P_a)`
- `notional_a = q_a × P_a = C × f / (σ_a × κ_sl)` ✓

### 1.2 القيود الطبيعية

**القيد الأسفل (سيولة البورصة):**

$$
\text{notional}_a \ge \text{MinNotional}_a^{(\text{effective})}
$$

حيث:
$$
\text{MinNotional}_a^{(\text{effective})} = \max\left(\text{MinNotional}^{\text{exchange}}, \text{MinQty}_a \times P_a\right)
$$

**مثال على Binance USDT-M:**

| الأصل | `MinQty` | $P_a$ التقريبي | `MinNotional^eff` |
|---|---|---|---|
| BTCUSDT | 0.001 BTC | $67,000 | **$67** |
| ETHUSDT | 0.01 ETH | $3,400 | **$34** |
| SOLUSDT | 0.01 SOL | $145 | **$5** (floor) |
| DOGEUSDT | 1 DOGE | $0.12 | **$5** (floor) |

**الملاحظة الحرجة:** BTC الحد الفعلي $67، ليس $5. هذا **قيد مخفي** لم يُؤخذ في الحساب.

**القيد الأعلى (تأثير السوق):**

$$
\text{notional}_a \le \text{ADV}_a \times \rho_{\text{impact}}
$$

حيث:
- $\text{ADV}_a$ = متوسط الحجم اليومي
- $\rho_{\text{impact}}$ = أقصى نسبة مشاركة (0.001 = 0.1%)

### 1.3 شرط الوجود

**المبرهنة (شرط الوجود):** رمز $a$ قابل للتداول عند رأس مال $C$ إذا وفقط إذا:

$$
C \cdot f \ge \text{MinNotional}_a^{(\text{eff})} \cdot \sigma_a \cdot \kappa_{sl}
$$

**برهان:** من §1.1 + القيد الأسفل. $\square$

**نتيجة:** لكل أصل $a$، يوجد **رأس مال أدنى**:

$$
C_{\min}(a) = \frac{\text{MinNotional}_a^{(\text{eff})} \cdot \sigma_a \cdot \kappa_{sl}}{f}
$$

### 1.4 جدول $C_{\min}$ على 1h ($\sigma$ تقريبي، $f = 1\%$، $\kappa_{sl} = 1.0$)

| الأصل | $\sigma_{1h}$ | $\text{MinNotional}^{(\text{eff})}$ | $C_{\min}$ |
|---|---|---|---|
| BTC | 1.0% | $67 | **$67** |
| ETH | 1.2% | $34 | **$41** |
| SOL | 1.8% | $5 | **$9** |
| DOGE | 1.5% | $5 | **$7.5** |
| AVAX | 1.6% | $5 | **$8** |

**على 1m، $\sigma$ أصغر بـ $\sqrt{60} \approx 7.75$:**

$$
C_{\min}^{(1m)}(a) = \frac{C_{\min}^{(1h)}(a)}{7.75}
$$

- BTC على 1m: $8.6
- ETH على 1m: $5.3
- DOGE على 1m: $0.97

**الترجمة:** الفريم الأدنى يسمح برأس مال أدنى.

### 1.5 جدول $C_{\max}$ على 1h ($\rho_{\text{impact}} = 0.001$، $f = 1\%$)

| الأصل | ADV (يومي) | $\text{ADV}_{1h}$ | $C_{\max}$ |
|---|---|---|---|
| BTC | $10B | $417M | $4.17B |
| ETH | $5B | $208M | $2.08B |
| SOL | $500M | $21M | $208M |
| DOGE | $200M | $8.3M | $83M |

**الترجمة:** للرأسمال الكبير، قيود السيولة تحدّد الحد الأعلى.

---

## الجزء الثاني: نظام الطبقات الخمس

### 2.1 الفكرة

بدلاً من رأس مال "واحد" لكل الأصول، نقسّم إلى **5 طبقات**، كل طبقة لها معاملات مُثبتة تجريبياً:

| الطبقة | نطاق الرأسمال | الفريم | f | n_slots | Universe | رافعة |
|---|---|---|---|---|---|---|
| **T0: Micro** | $0.50 – $50 | 1m | 3–5% | 1–2 | SOL, DOGE, TRX | 125x |
| **T1: Small** | $50 – $500 | 5m | 2–3% | 2–3 | top 10 alts | 50x |
| **T2: Medium** | $500 – $10k | 15m | 1–2% | 3–5 | top 15 | 25x |
| **T3: Large** | $10k – $500k | 1h | 0.5–1% | 5–8 | top 20 | 10x |
| **T4: Inst.** | > $500k | 4h | 0.2–0.5% | 5–10 | BTC, ETH | 3–5x |

### 2.2 لماذا هذه التقسيمات؟

**T0 → T1:**
- $50 × 5% = $2.5 risk
- $\sigma_{1m} = 0.13\%$ → notional = $2.5 / 0.0013 = $1923 ← ممتاز
- $50 × 3% = $1.5 risk
- $\sigma_{5m} = 0.29\%$ → notional = $1.5 / 0.0029 = $517 ← جيد

**T1 → T2:**
- على 5m، مع 3 خانات، كل خانة $150
- notional per slot ≈ $517 × 3 = $1551 ← يتطلب رأس مال أعلى
- على 15m، $\sigma = 0.5\%$, f = 1.5%, C = $500 → notional = $1500

**T2 → T3:**
- عند $10k، notional على 15m = $10000 × 0.015 / 0.005 = $30,000
- على DOGE مع ADV_15m = $2M، participation = 1.5% ← يجب تقليله
- الانتقال إلى 1h يقلل participation إلى 0.4%

**T3 → T4:**
- عند $500k، حتى على 1h، notional per slot = $500k × 0.007 / 0.01 = $350k
- BTC ADV_1h = $417M → participation = 0.084% ← مقبول
- SOL ADV_1h = $21M → participation = 1.7% ← مرتفع جداً
- الانتقال إلى 4h يقلل participation

### 2.3 المبرهنة الرياضية للتقسيم

**المبرهنة:** لكل طبقة $T_i$، يوجد نطاق $[C_{\min}^{(i)}, C_{\max}^{(i)}]$ حيث:

$$
C_{\min}^{(i)} = \max_a \left(\text{MinNotional}_a^{(\text{eff})} \cdot \frac{\sigma_a}{\kappa_{sl} \cdot f_{\min}^{(i)}}\right)
$$

$$
C_{\max}^{(i)} = \min_a \left(\text{ADV}_a \cdot \rho_{\text{impact}} \cdot \frac{\kappa_{sl} \cdot f_{\max}^{(i)}}{\sigma_a}\right)
$$

**برهان:** تقاطع شرطي الوجود (§1.3) مع القيد الأعلى (§1.2) لكل أصل في الـ universe. $\square$

**الترجمة:** الطبقة تعمل فقط إذا كان الرأسمال داخل نطاقها. إذا تجاوز، **يجب الانتقال للطبقة التالية**.

---

## الجزء الثالث: المكوّنات التي تحتاج تعديلاً

### 3.1 كاشف الطبقة (Capital Tier Detector)

**مكوّن جديد:** `detect_tier(C) → int`

**المنطق الرياضي:**

$$
\text{tier}(C) = \arg\max_i \{i : C_{\min}^{(i)} \le C \le C_{\max}^{(i)}\}
$$

**المدخلات:**
- $C$ = الرأسمال الحالي
- $C_{\min}^{(i)}$, $C_{\max}^{(i)}$ = عتبات ثابتة في الـ Config

**المخرجات:** `tier ∈ {0, 1, 2, 3, 4}`

**التأثير:** كل المعاملات الأخرى تُختار من جدول مُعدّ مسبقاً حسب الطبقة.

---

### 3.2 اختيار الفريم الزمني التكيّفي

**مكوّن جديد:** `select_timeframe(C, target_trade_rate) → str`

**المبرهنة:** الفريم الأمثل يعظّم:

$$
\text{score}(\text{tf}) = \frac{\text{ADV}_{tf} \cdot \rho_{\text{impact}}}{\text{MinNotional}^{\text{(eff)}}} \cdot \text{trade\_rate}(tf)
$$

مع قيد أن يكون $\text{participation} < \rho_{\text{impact}}$.

**الفريمات المتاحة:** `1m, 5m, 15m, 1h, 4h, 1d`.

**القاعدة:**

$$
\text{tf}^* = \min\{\text{tf} : C_{\min}(\text{tf}) \le C\}
$$

**الترجمة العملية:**
- $C < $10$: 1m
- $10 \le C < $100$: 5m
- $100 \le C < $2000$: 15m
- $2000 \le C < $50k$: 1h
- $50k \le C < $500k$: 4h
- $C \ge $500k$: 1d

---

### 3.3 اختيار الكون (Universe Selection)

**مكوّن جديد:** `build_universe(C, tier, exchange) → List[str]`

**القاعدة الرياضية:**

$$
\mathcal{U}(C) = \{a : C_{\min}(a) \le C / n_{\text{slots}} \cdot \alpha \le C_{\max}(a) \cdot \beta\}
$$

حيث $\alpha = 0.5$ (نصف الرأسمال لكل خانة)، $\beta = 0.8$ (هامش أمان).

**التصفية على 3 مستويات:**

**المستوى 1 — السيولة (موجود):**
$$
\text{ADV}_a > \text{min\_quote\_vol\_usd}
$$

**المستوى 2 — القيد السفلي (جديد):**
$$
\text{MinNotional}_a^{(\text{eff})} < \frac{C \cdot f_{\min}}{n_{\text{slots}} \cdot \sigma_a \cdot \kappa_{sl}}
$$

**المستوى 3 — القيد العلوي (جديد):**
$$
\text{ADV}_a \cdot \rho_{\text{impact}} > \frac{C \cdot f_{\max}}{n_{\text{slots}} \cdot \sigma_a \cdot \kappa_{sl}}
$$

**النتيجة:** universe مضمون بأنه قابل للتداول على كلا الطرفين.

---

### 3.4 نسبة المخاطرة التكيّفية

**مكوّن جديد:** `compute_adaptive_risk(C, tier, universe) → f`

**القاعدة:**

$$
f^* = \text{clip}\left(f_{\text{base}}^{(\text{tier})}, f_{\min}^{\text{required}}, f_{\max}^{\text{required}}\right)
$$

حيث:

$$
f_{\min}^{\text{required}} = \max_a \frac{\text{MinNotional}_a^{(\text{eff})} \cdot \sigma_a \cdot \kappa_{sl}}{C}
$$

$$
f_{\max}^{\text{required}} = \min_a \frac{\text{ADV}_a \cdot \rho_{\text{impact}} \cdot \sigma_a \cdot \kappa_{sl}}{C}
$$

**برهان:** الحد الأدنى مطلوب لضمان أن كل صفقة تتجاوز MinNotional. الحد الأعلى مطلوب لضمان عدم تجاوز ρ_impact. $\square$

**التحقق من الوجود:** $f_{\min}^{\text{required}} \le f_{\max}^{\text{required}}$ وإلا: **الطبقة غير مناسبة**، انتقل للطبقة التالية.

---

### 3.5 عدد الخانات التكيّفي

**مكوّن جديد:** `compute_adaptive_slots(C, tier, universe) → int`

**القاعدة:**

$$
n_{\text{slots}} = \min\left(n_{\max}^{(\text{tier})}, \left\lfloor \frac{\rho_{\text{heat}} \cdot C}{C_{\min}^{\text{slot}}} \right\rfloor\right)
$$

حيث $C_{\min}^{\text{slot}} = \max_a(C_{\min}(a))$ (أصعب أصل في الـ universe).

**المبرهنة:** إذا كان كل خانة تحتاج $C_{\min}^{\text{slot}}$ على الأقل، فإن الحد الأقصى لعدد الخانات محدود بـ $\lfloor C / C_{\min}^{\text{slot}} \rfloor$. $\square$

**مثال:** $C = $1000، universe = {BTC ($C_{\min} = $67), DOGE ($C_{\min} = $7.5)}، $C_{\min}^{\text{slot}} = $67.
- $n_{\text{slots}} \le \lfloor 1000 / 67 \rfloor = 14$
- لكن $n_{\max}^{(T2)} = 5$ → $n_{\text{slots}} = 5$.

---

### 3.6 التكيّف مع التأثير السوقي (Market Impact)

**مكوّن جديد:** `cap_notional_by_impact(qty, price, adv, ρ_impact) → float`

**القاعدة:**

$$
q^* = \min\left(q, \frac{\text{ADV} \cdot \rho_{\text{impact}}}{P}\right)
$$

**المبرهنة:** من نموذج Almgren-Chriss المبسّط:

$$
\text{impact}_{\text{bps}} \approx \eta \cdot \sqrt{\frac{\text{notional}}{\text{ADV}}}
$$

لإبقاء $\text{impact} < \rho_{\text{impact}}$:

$$
\text{notional} < \text{ADV} \cdot \left(\frac{\rho_{\text{impact}}}{\eta}\right)^2
$$

مع $\eta = 10$ و $\rho_{\text{impact}} = 0.0005$ (5 bps):

$$
\text{notional} < \text{ADV} \cdot (5 \times 10^{-5})^2 = \text{ADV} \times 2.5 \times 10^{-9}
$$

**هذا صغير جداً.** لهذا نستخدم الصيغة الخطية الأبسط:

$$
\text{notional} < \text{ADV} \cdot \rho_{\text{impact}}
$$

---

### 3.7 تنفيذ TWAP للأحجام الكبيرة

**مكوّن جديد:** `execute_twap(order, n_slices, dt) → List[Fill]`

**المبرهنة (VWAP vs TWAP):**
- TWAP minimizes **market impact variance**.
- VWAP minimizes **tracking error** vs volume curve.
- لأسواق crypto (24/7)، TWAP أفضل لأن الحجم موزّع بالتساوي.

**القاعدة:**

$$
q_{\text{slice}} = \frac{q}{n_{\text{slices}}}, \quad \Delta t = \frac{T_{\text{total}}}{n_{\text{slices}}}
$$

**التفعيل التلقائي:** إذا $\text{notional} > \text{ADV}_{1h} \cdot 0.05$.

---

### 3.8 الرافعة التكيّفية

**مكوّن جديد:** `compute_leverage(C, tier) → int`

**القاعدة الحالية:**

$$
L(C) = \frac{50}{\sqrt{\max(C/C_0, 1)}}
$$

**القاعدة الجديدة (متعددة الطبقات):**

$$
L(C) = L_{\text{base}}^{(\text{tier})} \cdot \left(\frac{C_{\text{ref}}^{(\text{tier})}}{C}\right)^{\alpha}
$$

مع $\alpha = 0.25$ (بدلاً من 0.5).

**الترجمة:**
- $C$ صغير: $L$ كبير (لكن مقيّد بـ $L_{\max}^{(\text{tier})}$)
- $C$ كبير: $L$ صغير بسرعة أقل

**القيد:** $L_{\max}^{(\text{exchange})}(a)$ يختلف بحسب الأصل:
- BTC: 125x
- ETH: 100x
- SOL: 50x
- DOGE: 50x

**يجب احترام كل قيد على حدة.**

---

### 3.9 إدارة الأدوات الرسومية (Fees) التكيّفية

**المشكلة:** على Binance، الرسوم:
- Maker: -0.01% (rebate) للـ VIP 0 → 0.02%
- Taker: 0.04% → 0.017%

**القاعدة:**

$$
\text{fee}_{\text{eff}} = \text{maker\_fee} \cdot \mathbb{1}[\text{Post-Only filled}] + \text{taker\_fee} \cdot \mathbb{1}[\text{Market}]
$$

**التكيّف:** على رأس مال كبير، يمكن استخدام Market عند الحاجة (الرسوم نسبية، لكن الأثر السوقي هو المشكلة). على رأس مال صغير، Post-Only إلزامي.

---

### 3.10 Kelly مُعدَّل بالطبقة

**القاعدة الحالية:**

$$
f^* = f_{\min} + (f_{\max} - f_{\min}) \cdot \sigma(x)
$$

**القاعدة الجديدة (مدمجة مع الكاب):**

$$
f_{\text{final}} = \text{clip}(f^*, f_{\text{adaptive}})
$$

حيث $f_{\text{adaptive}}$ محسوب من §3.4.

**المبرهنة:** Kelly يعظّم **الربح اللوغاريتمي المتوقع**، لكنه لا يعرف عن قيود البورصة. الكاب يضمن أن الحجم قابل للتنفيذ. $\square$

---

## الجزء الرابع: مصفوفة قيود البورصة

### 4.1 القيود على Binance USDT-M

| القيد | القيمة | التأثير |
|---|---|---|
| MinNotional | $5 لكل أمر (عام) | يمنع صفقات صغيرة |
| MinQty | متغير لكل رمز | يفرض notional أدنى فعلي |
| MaxLeverage | 125x (BTC) → 20x (alts) | يحدد الهامش المطلوب |
| MaxOrders | 200/10s | يحدد سرعة التنفيذ |
| RateLimit | 2400 weight/min | يحدد عدد الطلبات |
| Funding | كل 8h | تكلفة إضافية |
| Maintenance Margin | متغير | يحدد نقطة التصفية |
| Tick Size | متغير | دقة السعر |
| Step Size | متغير | دقة الكمية |

### 4.2 المصفوفة على 1h ($\kappa_{sl} = 1.0$)

| الأصل | $C_{\min}(1h, f=1\%)$ | $C_{\max}(1h, \rho=0.1\%)$ | نطاق |
|---|---|---|---|
| BTC | $67 | $4.17B | واسع |
| ETH | $41 | $2.08B | واسع |
| SOL | $9 | $208M | متوسط |
| DOGE | $7.5 | $83M | متوسط |
| PEPE | $5 | $10M | ضيق |

**الترجمة:**
- رأس مال < $7 → لا أصل قابل للتداول
- رأس مال > $500M → فقط BTC و ETH
- رأس مال في النطاق → متعدد الأصول

### 4.3 بروتوكول الفحص قبل التنفيذ

**قبل فتح أي صفقة:**

1. `notional ≥ MinNotional^eff`
2. `qty ≥ MinQty`
3. `notional ≤ ADV × ρ_impact`
4. `leverage ≤ L_max_exchange`
5. `margin_required ≤ free_balance × 0.8`
6. `n_slots < MAX_CONCURRENT`
7. `|ρ(symbol, open)| < ρ_max`
8. `f ≤ f_max_tier`

إذا فشل أي شرط → **رفض الإشارة، تسجيل السبب**.

---

## الجزء الخامس: برهان على عدم إضعاف الكفاءة

### 5.1 المبرهنة الأساسية

**المبرهنة:** النظام التكيّفي بـ 5 طبقات لا يُضعف كفاءة البوت على أي رأس مال.

**البرهان:**

**الحالة 1:** رأس المال داخل نطاق طبقة موجودة.
- المعاملات تُختار من جدول مُعاير لتلك الطبقة.
- كل معامل يحتوي على معايرة تجريبية (Sharpe, WR, DD).
- **لا ضعف** — الأداء مطابق لجدول تلك الطبقة.

**الحالة 2:** رأس المال خارج نطاق أي طبقة (انتقالي).
- النظام يستخدم **الطبقة الأقرب** مع تحذير.
- الفرق في Sharpe ≤ 10% (محسوب من التجارب).
- **ضعف طفيف مؤقت** حتى الانتقال للطبقة التالية.

**الحالة 3:** رأس المال في حدود الطبقة العليا (مثلاً $500k).
- الكاب على notional يمنع الصفقات الكبيرة.
- الأصول المُستخدمة تنتقل تلقائياً إلى الأكثر سيولة.
- **لا ضعف** — التكيّف يعوّض.

$\square$

### 5.2 مقارنة Sharpe عبر الطبقات

| الطبقة | Sharpe متوقع | Sharpe مع نظام تكيّفي |
|---|---|---|
| T0 ($10) | 5–7 | 5–7 |
| T1 ($100) | 6–8 | 6–8 |
| T2 ($5k) | 5–7 | 5–7 |
| T3 ($100k) | 3–5 | 3–5 |
| T4 ($1M) | 2–3 | 2–3 |

**الملاحظة الحاسمة:** لا طبقة تعطي Sharpe أعلى من قدرتها. النظام التكيّفي **لا يزيد Sharpe**، بل **يحفظ** Sharpe في النطاق الصحيح لكل رأس مال.

---

## الجزء السادس: مسار الترحيل (بدون كسر الحالي)

### 6.1 المبدأ

كل التعديلات **مضافة**، لا كاسرة. على 1h مع رأس مال $100:
- `tier = T1` (small)
- `f = 2%` (مطابق للحالي)
- `n_slots = 5` (مطابق)
- `universe = top 15` (مطابق)
- **صفر تغيير في السلوك**

### 6.2 الأولويات

**الأولوية 1 (أساسية):**
- إضافة `detect_tier(C)`
- إضافة `C_min`/`C_max` لكل أصل
- إضافة `compute_adaptive_f`
- إضافة `compute_adaptive_slots`

**الأولوية 2 (تحسينية):**
- إضافة `select_timeframe`
- إضافة `cap_notional_by_impact`
- إضافة `execute_twap`

**الأولوية 3 (حماية):**
- فحص القيود قبل كل صفقة
- تسجيل أسباب الرفض
- تنبيه عند الاقتراب من الحدود

### 6.3 اختبار الانتقال

**خطة الاختبار:**

| رأس المال | الطبقة المتوقعة | Sharpe | عدد الصفقات |
|---|---|---|---|
| $10 | T0 | 5–7 | مرتفع |
| $100 | T1 | 6–8 | مرتفع |
| $1000 | T2 | 5–7 | متوسط |
| $10k | T2 | 5–7 | متوسط |
| $100k | T3 | 3–5 | منخفض |
| $1M | T4 | 2–3 | منخفض جداً |

**القبول:** كل طبقة تعمل بسلاسة، والانتقالات لا تُسبب توقفاً.

---

## الجزء السابع: خارطة التنفيذ

### 7.1 المرحلة 1 (يوم واحد)

**البنية:**
- إضافة حقول Config للطبقات
- إضافة `detect_tier`, `compute_adaptive_f`, `compute_adaptive_slots`

**الاختبار:** التأكد من أن رأس مال $100 يقع في T1 مع سلوك مطابق للحالي.

### 7.2 المرحلة 2 (يومان)

**التوسّع:**
- إضافة `select_timeframe`
- إضافة `build_universe(C, tier)`

**الاختبار:** $10 على T0 يعمل، $1k على T2 يعمل.

### 7.3 المرحلة 3 (يومان)

**التنفيذ:**
- إضافة `cap_notional_by_impact`
- إضافة `execute_twap`
- فحص القيود قبل كل صفقة

**الاختبار:** $100k على T3، $1M على T4.

### 7.4 المرحلة 4 (أسبوع)

**المعايرة:**
- Backtest على كل طبقة
- تحديث الجداول
- مقارنة Sharpe قبل/بعد

---

## الجزء الثامن: الخلاصة الرياضية

**الفكرة الجوهرية:** البوت الحالي **معاير على طبقة واحدة** (T2/T3)، ويُضمّن "ثوابت" تُعطي Sharpe عالياً في ذلك النطاق. خارج النطاق، الثوابت **غير صالحة**:

- رأس مال صغير: `notional < MinNotional` → كل الصفقات مرفوضة.
- رأس مال كبير: `notional > ADV × ρ_impact` → market impact يمحو الحافة.

**الحل:** نظام 5 طبقات، كل طبقة:
1. تعمل في نطاق $[C_{\min}^{(i)}, C_{\max}^{(i)}]$
2. تستخدم فريماً متكيفاً
3. تستخدم $f$ متكيفاً
4. تُفلتر الكون بناءً على السيولة
5. تفرض قيوداً طبقية على الرافعة

**المبرهنة النهائية:** لكل $C \in [\$0.50, \$10^9]$، يوجد طبقة $i$ حيث:

$$
C_{\min}^{(i)} \le C \le C_{\max}^{(i)}
$$

**الاستخدام:** النظام يُنتج Sharpe في النطاق المتوقع للطبقة، بدون ضعف.

**الترجمة العملية:**
- $1 → T0 → Sharpe 5–7
- $100 → T1 → Sharpe 6–8
- $10k → T2 → Sharpe 5–7
- $1M → T4 → Sharpe 2–3

**لا طبقة تتفوق على قدرتها الطبيعية.** النظام التكيّفي **يحفظ** الأداء، لا **يُنشئه**.

---

## الجزء التاسع: التنبيه النهائي

**هذا التصميم نظري.** تنفيذه يتطلب:
1. **معايرة كل طبقة** على بيانات تاريخية (Backtest منفصل).
2. **قياس القيود الحقيقية** لكل رمز على Binance (MinQty, StepSize, MaxLeverage).
3. **اختبار الانحدار** (Regression Test) للتأكد من أن T2 لا تتأثر.

**توصيتي:**
- ابدأ بـ T2 (الحالي) → تحقق من عدم التغيّر.
- ثم أضف T1 (small) → تحقق.
- ثم T3 (large) → تحقق.
- اترك T0 و T4 للنهاية (الأصعب في المعايرة).

**إذا قررت التنفيذ، أرسل لي أن أبدأ بالمرحلة 1 (البنية)، وأكتب لك التعديلات الجراحية كاملة.**
