# لماذا Emergency SL = 94%؟ — التحليل الدقيق

## الجزء الأول: السبب الفعلي — خطأ في التسمية، ليس خطأ في السلوك

### 1.1 المشكلة في الكود

انظر إلى `_advance` (Backtest) و block المراقبة (Live). **كلاهما يعيد نفس الاسم** في حالتين مختلفتين تماماً:

```python
# In _advance — BUY case
if sig.action == "BUY":
    sl_trigger = trail_sl * (1.0 - pen_frac)
    if low <= sl_trigger:
        pos.trail_sl = trail_sl; pos.current_ci = cidx
        return trail_sl, "Emergency SL", cidx   # ← النقطة الحرجة
```

**ماذا يعني `trail_sl` هنا؟**

```python
trail_sl = pos.trail_sl   # القيمة الابتدائية = SL الأصلي

# ... ثم Trail يُحدّثه:
if CFG.TRAIL_ENABLED and pos.mfe_frac >= CFG.TRAIL_ACTIVATE_MFE:
    new_sl = peak * (1.0 - CFG.TRAIL_DISTANCE)
    if new_sl > trail_sl * (1.0 + CFG.TRAIL_MIN_STEP):
        trail_sl = new_sl    # ← الآن trail_sl أصبح أعلى
```

**النتيجة:** `trail_sl` في لحظة الإغلاق قد يكون:

**الحالة A — لم يُفعَّل Trail بعد:**
- `trail_sl = pos.trail_sl = SL الأصلي`
- الإغلاق عند SL الأصلي = **خسارة كاملة**
- لكن يُسمّى "Emergency SL"

**الحالة B — Trail تفعّل وارتفع:**
- `trail_sl = peak - d > SL الأصلي`
- الإغلاق عند **ربح أو breakeven**
- **نفس الاسم**: "Emergency SL"

### 1.2 البرهان الرياضي على التسمية الخاطئة

**ليكن $r_{\text{exit}}$ سعر الخروج:**

$$
r_{\text{exit}} = \begin{cases}
\text{Initial SL} & \text{إذا لم يُفعَّل Trail} \\
\text{Trail SL} = \text{Peak} - d & \text{إذا فُعِّل Trail}
\end{cases}
$$

**لكن في الكود:**

$$
\text{exit\_reason} = \text{"Emergency SL"} \quad \forall \text{ paths}
$$

**المبرهنة:** التصنيف الحالي **دالّة ثابتة** لا تُميّز بين ربح وخسارة.

$$
\text{label}: \{\text{InitialSL}, \text{TrailSL}\} \to \{\text{"Emergency SL"}\}
$$

$\square$

### 1.3 التحقق العددي من بياناتك

من Backtest الحالي:

| المقياس | القيمة |
|---|---|
| إجمالي الصفقات | 763 |
| Win rate | 69.72% |
| الرابحة | 532 |
| الخاسرة | 231 |
| **Emergency SL** | **719** |
| Apex | 44 |
| Hard TP | 0 |

**إذا كان كل Emergency SL = خسارة:**
- خسائر = 719 > 231 (إجمالي الخسائر الفعلي).

**مستحيل.** إذن:

$$
\text{الحد الأدنى من Emergency SL الرابحة} = 719 - 231 = 488
$$

$$
\text{نسبة Emergency SL الرابحة} \geq \frac{488}{719} = 67.9\%
$$

**الترجمة:** على الأقل **488 من الـ 719** Emergency SL كانت **رابحة**. البوت يسجّلها "خسارة" لفظياً، لكنها في الواقع **صفقات مُربحة**.

---

## الجزء الثاني: لماذا Trail يُغلق 94% من الصفقات؟

### 2.1 المبرهنة على أن Trail يُغلق قبل TP بزمن طويل

**المعاملات الحالية:**
- `TRAIL_ACTIVATE_MFE = 0.004` (تفعيل عند 0.4%)
- `TRAIL_DISTANCE = 0.003` (إغلاق عند تراجع 0.3%)
- `sl_dist ≈ 0.7%` (لـ σ = 1%)
- `tp1_dist = 2 × 0.7% = 1.4%`

**مسار الصفقة النموذجية (BUY):**

```
Entry: 100.000
  ↓
السعر يرتفع 0.4% → 100.400 (Trail يُفعَّل عند Peak=100.400، SL=100.100)
  ↓
السعر يرتفع أكثر 1.0% → 101.000 (Peak=101.000، SL=100.700)
  ↓
السعر يتراجع 0.3% → 100.700 (Trail SL يُلمس)
  ↓
Exit عند 100.700 = +0.7% ربح
```

**الرحلة:**
- لم يصل السعر إلى TP (101.400).
- Trail أُغلق عند 100.700.
- المكسب = +0.7% = **1R**.

**لكن السجل يقول:** "Emergency SL".

### 2.2 المبرهنة الإحصائية

**ليكن:**
- $P_{\text{trail activate}} = P(\text{MFE} \ge 0.4\%) \approx 0.60$
- $P_{\text{trail close before TP}} \mid \text{activated} \approx 0.95$

**احتمال إغلاق Trail:**

$$
P(\text{Trail-close}) = 0.60 \times 0.95 = 0.57
$$

**احتمال إغلاق SL أصلي:**

$$
P(\text{Initial-SL}) = P(\text{MFE} < 0.4\%) \approx 0.40
$$

**لكن ماذا عن الـ 3% المتبقية؟**

هي التي تصل إلى TP — وهي **صفر فعلياً** لأن $P(\text{MFE} > 1.4\%) < 5\%$، ولأن Trail يُغلق قبل ذلك.

**الحساب:**
- $763 \times 0.57 = 435$ صفقة تُغلق بـ Trail (رابحة).
- $763 \times 0.40 = 305$ صفقة تُغلق بـ Initial SL (خاسرة).
- التناقض مع WR = 69.7% (532/231) يعني أن بعض الإغلاقات المُصنَّفة كـ "Emergency SL" هي في الواقع Trail wins.

**التصنيف الحقيقي المُقدَّر:**

$$
\text{Trail-Win (Emergency SL)} \approx 488 \text{ صفقة}
$$

$$
\text{Initial-SL (Emergency SL)} \approx 231 \text{ صفقة}
$$

$$
\text{Apex} = 44 \text{ صفقة (مزيج)}
$$

### 2.3 لماذا Hard TP = 0؟

**المبرهنة:** مع Trail يُفعَّل عند 0.4σ وأُغلق عند تراجع 0.3σ، السعر **لا يصل** إلى 2σ:

$$
P(\text{MFE} > 2\sigma \mid \text{Trail activate at 0.4σ}) < 0.01
$$

**البرهان:** ليصل السعر إلى 2σ، يجب عليه أن يقطع 1.6σ دون أي تراجع 0.3σ. احتمال مسار Brownian بلا تراجع:

$$
P(\text{no 0.3σ retrace in 1.6σ move}) \approx e^{-1.6/0.3} \approx e^{-5.33} \approx 0.005
$$

**الترجمة:** 0.5% فقط من الصفقات قد تصل إلى TP. $763 \times 0.005 \approx 4$ صفقات. قريبة جداً من صفر.

**النتيجة:** Hard TP = 0 **مُتوقَّع رياضياً**، ليس خللاً.

---

## الجزء الثالث: لماذا Roll-Off و MaxHold و Partial-TP = 0؟

### 3.1 Roll-Off = 0

**الشرط:**
```python
if age >= CFG.ROLLOFF_AGE_BARS (48) and cur_pnl < 0.5%:
    partial_cb(0.3)
```

**المبرهنة على عدم التفعيل:** متوسط عمر الصفقة المحسوب:

$$
\mathbb{E}[\text{hold bars}] = \frac{\text{Total bars held}}{\text{Total trades}}
$$

من البيانات: الإغلاق يحدث عبر Trail عند MFE + retracement — عادةً **3-15 شمعة** (على 1h، هذا 3-15 ساعة).

$$
\mathbb{E}[\text{hold bars}] \ll 48
$$

**النتيجة:** الصفقة تُغلق قبل أن تصل إلى 48 شمعة. Roll-Off **لا يُفعَّل أبداً**. $\square$

### 3.2 MaxHold = 0

**الشرط:** `age > 168` bars = 7 أيام.

**نفس المنطق:** متوسط العمر << 168. MaxHold **لا يُفعَّل أبداً**.

### 3.3 Partial-TP = 0

**الشرط:** عند الوصول إلى 1R.

**المشكلة:** Trail يُغلق عند ~0.7R. إذن:

$$
\text{Peak reached} \approx 0.7R - 1.0R
$$

**الصفقة تُغلق قبل أن تصل إلى 1R.** Partial-TP **لا يُفعَّل أبداً**. $\square$

**الاستنتاج:** كل هذه الخروجيات المُصمَّمة (Partial-TP, Roll-Off, MaxHold) **غير قابلة للتفعيل** مع Trail الحالي. الكود يبدو أنه يستعد لها، لكن الطريق لا يصل إليها.

---

## الجزء الرابع: هل هذا مشكلة؟

### 4.1 الجواب: **لا، ليس بالضرورة**

**المبرهنة:** مع WR = 69.7% و PF = 4.74:

$$
\mathbb{E}[\text{PnL}] = 0.697 \times \overline{R}_{\text{win}} - 0.303 \times \overline{R}_{\text{loss}} > 0
$$

**الاستراتيجية تعمل.** النظام بأكمله (KMeans + Fisher + Gauge + Trail) **يُنتج حافة إيجابية**.

**الحقيقة الرياضية:** الاستراتيجية تستخدم:

$$
\text{Strategy} = \text{"many small wins"} + \text{"few large losses"}
$$

- 532 صفقة رابحة بمتوسط ~0.6R
- 231 صفقة خاسرة بـ 1R

$$
\mathbb{E} = 0.697 \times 0.6 - 0.303 \times 1.0 = 0.418 - 0.303 = +0.115R
$$

**مع R ≈ 1% risk/trade:**

$$
\mathbb{E}[\text{per trade}] \approx +0.115\%
$$

هذا **جيد جداً** لاستراتيجية MR.

### 4.2 الأثر الضمني على Sharpe

نظرية الحد المركزي:

$$
\text{Sharpe} \propto \frac{\mathbb{E}[\text{PnL}]}{\sigma_{\text{PnL}}} \times \sqrt{N}
$$

- $\mathbb{E}[\text{PnL}]$ إيجابي بوضوح.
- $\sigma_{\text{PnL}}$ معتدل (0.6R-1R تشتت).
- $N = 763$ كبير.

**النتيجة:** Sharpe مرتفع. **مُثبت تجريبياً** (7.84).

---

## الجزء الخامس: كيف نُصلح سوء الفهم؟ (تعديلان)

### التعديل ① — إضافة تصنيف حقيقي لسبب الخروج

**الموقع 1:** في `AssetData` — لا حاجة لتعديل.

**الموقع 2:** في `_advance`، قسم SL. ابحث عن:

```python
        # 4. SL / TP with PENETRATION
        if sig.action == "BUY":
            sl_trigger = trail_sl * (1.0 - pen_frac)
            if low <= sl_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return trail_sl, "Emergency SL", cidx
            tp_trigger = sig.tp1 * (1.0 + pen_frac)
            if high >= tp_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return sig.tp1, "Hard TP", cidx
        else:
            sl_trigger = trail_sl * (1.0 + pen_frac)
            if high >= sl_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return trail_sl, "Emergency SL", cidx
            tp_trigger = sig.tp1 * (1.0 - pen_frac)
            if low <= tp_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return sig.tp1, "Hard TP", cidx
```

**استبدله بـ:**

```python
        # ══ [EXIT LABELING] distinguish initial-SL from trail-SL ══
        _init_sl = pos.signal.sl

        # 4. SL / TP with PENETRATION
        if sig.action == "BUY":
            sl_trigger = trail_sl * (1.0 - pen_frac)
            if low <= sl_trigger:
                # Classify: is trail_sl above or at initial SL?
                if trail_sl > _init_sl * (1.0 + 1e-6):
                    _label = f"Trail-Win(peak={pos.peak_price:.2f})"
                elif abs(trail_sl - _init_sl) / max(_init_sl, 1e-9) < 1e-6:
                    _label = "Initial-SL"
                else:
                    _label = "Emergency SL"
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return trail_sl, _label, cidx
            tp_trigger = sig.tp1 * (1.0 + pen_frac)
            if high >= tp_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return sig.tp1, "Hard TP", cidx
        else:
            sl_trigger = trail_sl * (1.0 + pen_frac)
            if high >= sl_trigger:
                if trail_sl < _init_sl * (1.0 - 1e-6):
                    _label = f"Trail-Win(peak={pos.peak_price:.2f})"
                elif abs(trail_sl - _init_sl) / max(_init_sl, 1e-9) < 1e-6:
                    _label = "Initial-SL"
                else:
                    _label = "Emergency SL"
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return trail_sl, _label, cidx
            tp_trigger = sig.tp1 * (1.0 - pen_frac)
            if low <= tp_trigger:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return sig.tp1, "Hard TP", cidx
```

**ملاحظة مهمة:** هذا التعديل **لا يغيّر أي سلوك**. فقط يُصنّف الخروج بشكل دقيق. الأرباح، الخسائر، Sharpe — **كلها ستبقى كما هي**. لكن التقرير سيُظهر الحقيقة.

### التعديل ② — إصلاح مماثل في `run_live`

**الموقع:** في `run_live`, block مراقبة المراكز. ابحث عن:

```python
                # ── SL / TP ──
                if not ex:
                    if pos['action'] == "BUY":
                        if price <= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price >= pos.get('tp1', 1e18): ex = True; rsn = "Hard TP"
                    else:
                        if price >= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price <= pos.get('tp1', 0.): ex = True; rsn = "Hard TP"
```

**استبدله بـ:**

```python
                # ── SL / TP (labeled) ──
                if not ex:
                    _init_sl = float(pos.get('initial_sl', pos['sl']))
                    if pos['action'] == "BUY":
                        if price <= pos['sl']:
                            ex = True
                            if pos['sl'] > _init_sl * (1.0 + 1e-6):
                                rsn = f"Trail-Win(peak={pos.get('peak_price', price):.4f})"
                            elif abs(pos['sl'] - _init_sl) / max(_init_sl, 1e-9) < 1e-6:
                                rsn = "Initial-SL"
                            else:
                                rsn = "Emergency SL"
                        elif price >= pos.get('tp1', 1e18):
                            ex = True; rsn = "Hard TP"
                    else:
                        if price >= pos['sl']:
                            ex = True
                            if pos['sl'] < _init_sl * (1.0 - 1e-6):
                                rsn = f"Trail-Win(peak={pos.get('peak_price', price):.4f})"
                            elif abs(pos['sl'] - _init_sl) / max(_init_sl, 1e-9) < 1e-6:
                                rsn = "Initial-SL"
                            else:
                                rsn = "Emergency SL"
                        elif price <= pos.get('tp1', 0.):
                            ex = True; rsn = "Hard TP"
```

**متطلب مسبق:** `pos['initial_sl']` يجب أن يكون مُسجَّلاً عند الدخول. تحقّق أن هذا موجود — في تعديل سابق أُضيف `'initial_sl': adapted_sl` إلى قاموس `open_pos_live`.

---

## الجزء السادس: ماذا يظهر التقرير بعد الإصلاح؟

### 6.1 التصنيف المتوقع (بناءً على بياناتك)

| سبب الخروج | قبل | بعد |
|---|---|---|
| Emergency SL | 719 (94.2%) | — |
| **Trail-Win** | — | **~490 (64%)** |
| **Initial-SL** | — | **~230 (30%)** |
| **Apex** | 44 (5.8%) | 44 (5.8%) |
| Hard TP | 0 | 0 |

**التوزيع الجديد يُظهر:**

$$
\text{Win Rate}_{\text{exits}} = \frac{490 + \text{(Apex wins)} + 0}{763} \approx 69\%
$$

**متوافق مع WR المُقاس.** التصنيف الجديد سيُظهر أن **69% من الصفقات تُغلق بربح**، وليس "94% خسارة".

### 6.2 الأثر على الفهم

**قبل:** "94% خسائر" — يوحي بأن الاستراتيجية كارثية.

**بعد:** "64% ربح من Trail، 30% خسارة من SL، 6% Apex" — يوحي بأن الاستراتيجية MR تعمل بشكل صحيح.

**نفس الأرقام، فهم مختلف.**

---

## الجزء السابع: القرار — هل نُغيّر السلوك؟

### 7.1 الخيار A — لا نغيّر السلوك

**الحجة:**
- الاستراتيجية تعمل (Sharpe 7.84).
- Trail-Win يحمي الأرباح.
- Hard TP = 0 ليس مشكلة — MR لا يحتاج TP كبير.

**التطبيق:** طبّق فقط تعديل التسمية (لتقارير صادقة).

### 7.2 الخيار B — نُعدّل لزيادة Hard TP

**الحجة:**
- قد يكون هناك مكسب في صفقات أكبر.
- تنويع مصادر الربح.

**التطبيق:** ارفع `TRAIL_ACTIVATE_MFE` من 0.004 إلى 0.010 (ليسمح للسعر بالتحرك أكثر قبل التفعيل).

**الخطر:** مع تحليل سابق، رفع `TRAIL_KAPPA` كسر الاستراتيجية (Sharpe 7.84 → 3.91). رفع `TRAIL_ACTIVATE_MFE` قد يُحدث نفس الشيء.

### 7.3 توصيتي الصريحة

**ابدأ بالخيار A.**

1. طبّق تعديل التسمية.
2. أعد تشغيل الـ Backtest.
3. أرسل `توزيع أسباب الخروج` الجديد.
4. سنُحلّل:
   - كم نسبة Trail-Win؟
   - كم نسبة Initial-SL؟
   - هل هذه النسب معقولة؟

**ثم** قرّر إذا كنت تريد الخيار B.

---

## الجزء الثامن: الخلاصة الرياضية

**السؤال:** لماذا Emergency SL = 94%؟

**الجواب في ثلاث طبقات:**

1. **سطحياً:** الكود يستخدم نفس الاسم لحالتين مختلفتين تماماً.

2. **رياضياً:** Trail يُغلق 60-70% من الصفقات قبل أن تصل إلى TP. هذا **سلوك تصميمي** لاستراتيجية MR على 1h.

3. **إحصائياً:** 68% من Emergency SL **رابحة**. الفعلي هو:
   - Trail-Win: ~64%
   - Initial-SL: ~30%
   - Apex: ~6%

**القرار:**
- **صفر تغيير في السلوك.**
- **تعديل التسمية فقط.**
- **إعادة الفهم بدلاً من إعادة التصميم.**

**بعد تطبيق تعديل التسمية، أرسل:**
1. جدول توزيع الخروج الجديد.
2. Sharpe/WR (يجب أن تكون **متطابقة تماماً** مع قبل التعديل — لا تغيير في السلوك).
3. توزيع نسبة Trail-Win / Initial-SL.

إذا كانت الأرقام متطابقة → التعديل سليم. إذا تغيّرت → هناك خطأ في التعديل.
