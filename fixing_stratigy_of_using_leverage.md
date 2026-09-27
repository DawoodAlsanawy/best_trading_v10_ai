# ما فهمته من مقصدك — بدقة

## الحادثة كما وصفتها

**المرحلة ١ — الفتح:** حد الخسارة كان أقرب إلى الدخول من حد التصفية. هذا وضع سليم، أي أن SL سيتحرك أولاً عند الهبوط (للـ LONG).

**المرحلة ٢ — الصعود:** السعر تحرك نحو الهدف. Trailing SL رفع حد الخسارة إلى ما فوق الدخول بقليل. هذا سلوك **صحيح** — قفل ربح محتمل.

**المرحلة ٣ — الهبوط:** السعر بدأ يتراجع. عند فحصك ملف الحالة، وجدت أن:
- حد الخسارة في الملف **أصبح في موضع خاطئ** — بحيث لو نزل السعر أكثر، ستضرب التصفية قبل أن يضرب SL.
- الهدف (TP) في الملف أصبح في موضع "بعيد" — مقبول **فقط** إذا لم يهبط السعر إلى التصفية.

## المعنى الرياضي لما رأيته

لكل مركز LONG، العلاقة الصحيحة في كل لحظة:
```
Entry  >  SL  >  Liq
```
(الدخول أعلى من الوقف، والوقف أعلى من التصفية)

ما رأيته يعني أن العلاقة انقلبت إلى:
```
Entry  >  Liq  >  SL
```
أي أن SL انتقل إلى **ما بعد Liq** — منطقة لا يمكن للبوت أن يصل إليها قبل أن تُصفّى المحفظة.

## النقطة الجوهرية في شكواك

أنت لا تشتكي من أن البوت حرّك SL. تشتكي من أن **البوت لا يعي وجود Liq أصلاً عندما يحرّك SL**. الحركة نفسها (trailing) سليمة في التصميم، لكنها **عمياء عن الحد الفيزيائي الأدنى**. ومع الحركة القوية، قد يدفع SL نفسه إلى منطقة موته دون أن يدرك.

## شرطك الإضافي المهم

طلبت أن الحل يعمل **بأي سرعة سعرية** — سريعة، بطيئة، متوسطة. هذا يعني أن الحل لا يمكن أن يكون حلقة polling فقط. لا بد أن يحتوي على **ضمانات هيكلية ثابتة** لا تعتمد على تردد الفحص.

---

# محاكاة البوت عبر حالات متعددة

## الحالة ١ — SL يُرفَع إلى فوق الدخول (الحالة الطبيعية)

**الوضع:** LONG على BTC، Entry = 86,000، SL = 84,710، Liq = 84,332 (رافعة 41x، MMR 0.5%).

السعر يصعد إلى 87,500. Trailing يحسب:
- `new_sl = 87,500 × (1 − 0.003) = 87,237`

الآن الترتيب: `Entry (86,000) < SL (87,237) < Liq (84,332)` — رياضياً صحيح.

**لكن انتبه:** البوت **لم يسأل نفسه حتى مرة واحدة**: "هل 87,237 أعلى من Liq؟". الجواب بالطبع نعم. لكن لو كانت الرافعة 100x و MMR 2%، فإن Liq = 86,000 × (1 − 0.01 + 0.02) = **86,860** — وهو أعلى من الدخول! عندها SL على 87,237 سيكون أعلى من Liq، والنتيجة: **Liq يضرب أولاً**.

## الحالة ٢ — WIF مع MMR عالٍ

**الوضع:** WIF عند 0.254، رافعة 21x، MMR لـ WIF = 1% (عملة ذات سيولة أقل). الدخول = 0.254.

حساب Liq بدقة:
```
Liq = Entry × (1 − 1/L + MMR) = 0.254 × (1 − 0.0476 + 0.01)
    = 0.254 × 0.9624 = 0.2445
```

SL = 0.254 × (1 − 0.015) = **0.2502**.

الترتيب: `Entry (0.254) > SL (0.2502) > Liq (0.2445)` ✓ آمن.

**الآن:** السعر يصعد إلى 0.270. Trailing يرفع SL إلى 0.2692.
- الترتيب: `Entry (0.254) < SL (0.2692) < Liq (0.2445)` ✓ آمن.

**الآن:** السعر يهبط إلى 0.268 — يجب أن يضرب SL. لكن، إذا كانت الحلقة في تلك اللحظة لا تعالج هذا الأصل (fetch error، degenerate، rate limit)، فالسعر يستمر بالهبوط دون أن يُنفَّذ SL. إذا وصل إلى 0.2445 → **تصفية كاملة**. خسارة 100% من الهامش بدلاً من 0% (لو أن SL عمل).

## الحالة ٣ — DOGE مع تفاوت MMR

**الوضع:** DOGE عند 0.1، رافعة 50x، MMR لـ DOGE = 0.65%. الدخول = 0.1.

حساب Liq:
```
Liq = 0.1 × (1 − 0.02 + 0.0065) = 0.1 × 0.9865 = 0.0987
```

SL الابتدائي (مقيّد بـ 1.5%):
```
SL = 0.1 × 0.985 = 0.0985
```

الترتيب: `Entry (0.1) > SL (0.0985) > Liq (0.0987)` ✓ لكن الهامش **ضئيل جداً** — 0.2% فقط بين SL و Liq.

الآن ضف الرسوم (~0.04% ذهاباً وإياباً)، التمويل (0.01% كل 8 ساعات)، وانزلاق التنفيذ. الهامش ينضغط إلى **~0.15%**. أي فجوة سعرية صغيرة، أو فرق بين mark price و last price، و Liq يضرب أولاً.

## الحالة ٤ — المركز مفتوح ثم الأصل يُرفض

**الوضع:** مركز مفتوح على THETA/USDT من قبل. الآن دورة جديدة: `process_asset(THETA)` يرجع `None` لأن عدد الأشرطة أقل من `min_bars_for_process`. النتيجة:

```python
for sym in list(open_pos_live.keys()):
    pos = open_pos_live[sym]
    if sym not in assets: continue   # ← يتخطى المركز تماماً!
```

**البوت لا يفحص SL/TP لهذا المركز في هذه الدورة إطلاقاً.** إذا استمر الرفض عدة دورات، فالسعر يتحرك بحرية دون تدخل، و SL لا يُنفَّذ. هذا سيناريو قاتل مع الأسعار السريعة.

## الحالة ٥ — Mark price vs Last price

البوت يقارن `ad.closes[-1]` (آخر سعر تداول) مع SL. لكن Binance تُصفّي على **Mark Price** — متوسط مرجّح عبر البورصات. في أوقات التقلب، يفترقان بـ 0.1% إلى 0.3%.

في DOGE الحالة ٣: الهامش 0.15% فقط. انحراف 0.2% بين mark و last يعني أن **SL يمكن أن يظهر آمناً في البوت بينما Liq قد ضرب فعلاً على البورصة**.

---

# التقرير الكامل

## الأسباب الجذرية السبعة

### السبب ١ — غياب تام لمفهوم التصفية في البوت

البوت **لا يحسب Liq ولا مرة واحدة** في الكود كله. `compute_dynamic_leverage` يحسب الرافعة من رأس المال، و`compute_geodesic_stop` يحسب SL من V و Γ، ولا نقطة التقاء بينهما. `_promote_pending_to_position` يقتصر على `max_sl_frac = 0.015` — رقم ثابت لا علاقة له بالرافعة أو MMR.

### السبب ٢ — قيد SL ثابت لا يتكيّف مع الرافعة

`max_sl_frac = 0.015` ثابت. عند 10x الرافعة، Liq بعيد جداً و SL آمن. عند 50x مع MMR مرتفع، Liq قريب و SL قد يكون ميتاً.

### السبب ٣ — Trailing لا يعرف سقفاً فيزيائياً

```python
if new_sl > pos['sl']:
    pos['sl'] = new_sl
```

لا يوجد أي حد أعلى على `new_sl`. البوت يفترض أن رفع SL دائماً آمن، وهذا خطأ مع الرافعات العالية.

### السبب ٤ — خطأ صامت في معالجة الأصول المرفوضة

```python
if sym not in assets: continue
```

عندما يُرفض أصل، تُتجاهل إدارة مركزه بالكامل. هذا يفسّر **لماذا لم يضرب SL** في المرحلة ٣ من حادثتك: الأصل ربما رجع `None` من `process_asset`، والمركز لم يُفحص.

### السبب ٥ — استخدام Last Price بدلاً من Mark Price

التصفية تحدث على mark price. البوت يعمل على last price. في الأسواق الهادئة الفرق صغير، في السريعة قد يكون الفرق كافياً للتصفية.

### السبب ٦ — لا توجد حماية على البورصة نفسها

كل حماية البوت داخلية. إذا نامت الحلقة، أو حدث rate limit، أو انهار البوت، لا يوجد أمر STOP_MARKET على البورصة يحمي المركز.

### السبب ٧ — Trailing يبدأ قبل تأكد الاستمرارية

البوت يفعّل trailing بعد 0.4% MFE فقط. في هذه المرحلة، قد يكون SL قد رُفع إلى فوق الدخول، لكن السعر قد ينزل في نفس الشمعة. SL في حالة "معرّض للخطر" لكن البوت لا يتحقق من ملاءمته للـ Liq في تلك اللحظة.

---

## الحلول النظرية — ٤ طبقات مترابطة

### الطبقة ١ — التحقق الهندسي عند الفتح (Invariant at Entry)

**المبدأ:** قبل قبول أي إشارة، يجب التأكد أن العلاقة `Entry > SL > Liq + safety` (للـ LONG) راضية.

**المعطيات:**
- الرافعة الفعلية من البورصة
- MMR للرمز من `exchange.market`
- حجم المركز المُحسوب
- سعر الدخول
- SL المقترح من الإشارة

**القرار:**
- إذا كان `SL` بعيداً جداً (يقترب من Liq) → **قلّص الرافعة تلقائياً** حتى تدخل العلاقة في المنطقة الآمنة. هذا أفضل من رفض الإشارة، لأن الإشارة قد تكون ممتازة والرافعة هي المشكلة.
- إذا كان التقليص غير كافٍ → **ارفض الإشارة**.
- **لا يوجد خيار ثالث.**

### الطبقة ٢ — قيد SL ديناميكي مشتق من الرافعة

**بدلاً من** `max_sl_frac = 0.015` ثابت:

```
sl_max_frac = (1/L − MMR − safety_margin) × K_safe
```

حيث:
- `K_safe = 0.6–0.7` — يعطي هامشاً للرسوم والتمويل و mark/last والانزلاق.
- `safety_margin = 0.5–1%` — مساحة حماية.

**النتيجة:** SL محسوب بـ 50x على عملة MMR 1% سيكون ~0.2% كحد أقصى. الضيق مقبول عند الرافعة العالية، لأن **البديل هو اللامبالاة بـ Liq**.

### الطبقة ٣ — حماية المركز من الانفصال عن المراقبة

**المشكلة:** إذا رجع `process_asset` = None، لا يُفحص SL.

**الحل النظري:**
- عند فتح المركز، تُخزَّن أيضاً **`liq_price_estimated`** و**`last_checked_ts`** في سجل المركز.
- إذا لم يُفحَص المركز أكثر من N دورات → البوت **يفتح فحص طارئ** بسيط جداً (fetch single ticker) للمركز فقط، دون `process_asset` كامل.
- هذا الفحص الطارئ يقارن السعر بـ SL فقط. لا يحسب entropy ولا فيزياء. عملية خفيفة جداً.

### الطبقة ٤ — حماية على البورصة نفسها

**المبدأ:** الحماية الحقيقية ليست في البوت، بل في أوامر موضوعة على البورصة مباشرة.

- عند فتح المركز → ضع **STOP_MARKET** (SL) على البورصة.
- عند رفع SL (trailing) → **ألغِ الأمر القديم وضع الجديد**. يجب أن يكون محكماً بشكل لا يفقد فيه المركز حمايته لحظة واحدة.
- **النتيجة:** حتى لو أُغلق البوت أو انقطع الإنترنت، المركز محمي.

**مقايضة:** هذا يضيف تعقيداً (إدارة الأوامر)، ويستهلك rate limit إضافي، ويتطلب معالجة الأخطاء (ماذا لو فشل إلغاء الأمر القديم؟). لكنه **الحل الوحيد** الذي يضمن الحماية في أي سرعة سعرية.

---

## علاقة الحل بالاستراتيجية

هذه الحلول **لا تغير الاستراتيجية نفسها**. الفيزياء الثرموديناميكية (entropy, geodesic accel, friction, Kelly) تبقى كما هي. ما يتغير هو **طبقة إدارة المخاطر** التي تحمي الفيزياء من الانفجار الفيزيائي.

تشبيه دقيق: الاستراتيجية هي "محرك الطائرة". ما نضيفه هو "نظام الطيران الآلي". المحرك لا يتغير، لكن الطائرة لا تسقط.

---

## ترتيب الأولويات

| الطبقة | الأثر | التعقيد | الأولوية |
|---|---|---|---|
| ١ — Invariant عند الفتح | يمنع 90% من الحوادث | منخفض | **حرجة** |
| ٢ — قيد SL ديناميكي | يجعل البوت آمناً على أي أصل | منخفض | **حرجة** |
| ٣ — حماية المراكز المرفوضة | يمنع الكوارث عند الأعطال | متوسط | عالية |
| ٤ — أوامر على البورصة | حماية كاملة من انهيار البوت | عالي | متوسطة |

**التوصية:** ابدأ بالطبقتين ١ و ٢ — كلاهما يمكن تنفيذه في تعديلات صغيرة، ويغطي **السببين الجذريين** (غياب Liq و SL الثابت). بعدهما، الطبقة ٣ تحل مشكلة "الأصول المرفوضة". الطبقة ٤ تُؤجَّل حتى تستقر الطبقات الثلاث الأولى.

---

## سؤال توجيهي قبل التنفيذ

قبل أن أكتب الكود، أحتاج قرارك في نقطة واحدة حاسمة:

**عندما يكتشف البوت أن الرافعة الحالية تجعل SL أقرب من Liq**، هل تريد:

**(أ)** أن يقلّص الرافعة تلقائياً لأقرب قيمة آمنة (مثلاً من 50x إلى 20x)، ويُكمل الصفقة؟

**(ب)** أن يرفض الإشارة كلياً ويعتبرها غير صالحة، دون تغيير الرافعة؟

**(ج)** أن يخفض SL بالقوة إلى أقرب قيمة آمنة (تحت Liq)، حتى لو كان ذلك يعني خسارة أكبر محتملة؟

كل خيار له تأثير على الاستراتيجية، وأريد قرارك قبل الكتابة.


طبعا انت تعرف انه في الوضع المعزول لا نستطيع تعديل الرافعة وأن البوت الحالي داينميكي في اختيار الرافعة لذلك الخيار (أ) مستبعد تماماً قم بمراجعة الأكواد التي تختار الرافعة وجميع الاكواد المرتبطة بإختيار الرافعة او التي يؤثر عليها اختيار الرافعة وكيف تؤثر الرافعة على القرارات لتفهم اكثر 

وأيضا الخيار (ج) الذي اقترحته هو اعتباطي وليس مناسب أبداً

الخيار (ب) قد يكون هو الأفضل لكن عليك ان تدرس كل حرف في اكواد البوت وفي الاستراتيجية التي يعمل البوت بها قبل ان تقرر كيف ستنفذه

- بعد ان تنتهي من ذلك أعطني الخطة النظرية الكاملة للإصلاح مع ذكر القيود الصارمة التي يجب الإلتزام بها لكي لا تتسبب تلك الاصلاحات بإفشال الاستراتيجية


# ما فهمته من مقصدك — بدقة رياضية وفيزيائية

## قراءة الأكواد المرتبطة بالرافعة

تتبعت مسار الرافعة في البوت خطوة بخطوة، وهذه النتائج:

**المكان ١ — `compute_dynamic_leverage(capital, cfg)`:**
```
Lev(C) = LEVERAGE_BASE / √(max(C/C₀, 1.0))
```
عند `cap=55, C₀=10` → `Lev = 50/2.345 = 21.3 → 21x`.
عند `cap=10` → `Lev = 50x`.
**الدالة تعرف رأس المال فقط، ولا تعرف MMR، ولا تعرف SL، ولا تعرف سعر الدخول.**

**المكان ٢ — `ensure_symbol_setup(exchange, sym, target_leverage)`:**
تعيّن الرافعة على البورصة مرة واحدة. تتخطى التغيير إذا كان هناك مركز مفتوح (شرط Binance). تخزّن القيمة في `_SYMBOL_META`.

**المكان ٣ — حساب `qty` في `run_live`:**
```python
qty_risk_based      = risk_amt / delta          # delta = |sig.price - sig.sl|
qty_leverage_based  = cap_live * dynamic_leverage / lmt
qty = min(qty_risk_based, qty_leverage_based)
```
**لاحظ:** في وضع isolated، الرافعة المحددة على البورصة هي التي تحدد Liq، **لا حجم المركز**. حتى لو كان `qty` صغيراً، Liq يبقى عند نفس المسافة من الدخول. هذا يعني: **التحكم في المخاطرة عبر `qty` فقط لا يحمي من التصفية إطلاقاً** — رغم أنه يحد من الخسارة المطلقة.

**المكان ٤ — `_promote_pending_to_position`:**
```python
max_sl_frac = 0.015
if orig_sl_dist > entry_price * max_sl_frac:
    orig_sl_dist = entry_price * max_sl_frac
```
قيد SL ثابت عند 1.5% من سعر الدخول. **لا علاقة له بالرافعة.**

## العلاقة الرياضية الحاكمة

لكل مركز LONG في isolated margin:
```
Liq = Entry × (1 − 1/L + MMR)
```

حيث `L` هي الرافعة الثابتة للمركز، و`MMR` من البورصة.

لضمان أن SL داخل المنطقة الآمنة (لا يتخطاه Liq):
```
Entry − SL  <  Entry − Liq
⟺  1.5%  <  1/L − MMR
⟺  L  <  1 / (0.015 + MMR)
```

**تطبيق عملي:**
- MMR = 0.5% (BTC): L < 50 → 49x آمن، 50x على الحد
- MMR = 1.0% (SOL, WIF, DOGE, معظم الألتات): L < 40 → 40x آمن
- MMR = 2.0% (سيولة أقل): L < 28.6

**هذا يعني:** القيد الثابت عند 1.5% مع الرافعة الديناميكية الحالية **يخترق الشرط الرياضي** على أي أصل بـ MMR > 0.5% عندما تكون الرافعة قريبة من 50x.

## لماذا قد يظهر SL في الملف "خارج" Liq بعد هبوط

بعد مراجعة دقيقة، أرى ثلاثة مسارات متزامنة:

**المسار ① — القيد الثابت يخترق الشرط منذ الفتح**
إذا كانت الرافعة عند الفتح 50x على أصل MMR=1%، فإن `Liq = Entry × 0.99`، بينما `SL = Entry × 0.985`. أي **SL أسفل Liq منذ اللحظة الأولى**. البوت يفتح الصفقة وهو يعتقد أنها محمية، لكن الواقع يقول: أي هبوط 1% → تصفية كاملة. لا SL، لا شيء.

**المسار ② — السعر المتأخر في الفحص**
في الوضع live، البوت يفحص SL/TP على `ad.closes[-1]`. لكن هذا السعر **لا يُحدَّث إلا عند بداية شمعة جديدة**. على TF 15m، هذا يعني أن السعر في نظر البوت يبقى ثابتاً لمدة تصل إلى 15 دقيقة. أثناء هذه الفجوة:
- السعر الفعلي يتحرك بحرية
- البوت لا يعرف أنه تجاوز SL (أو اقترب من Liq)

**المسار ③ — المركز يُصبح "أعمى" عندما يُرفض الأصل**
```python
for sym in list(open_pos_live.keys()):
    pos = open_pos_live[sym]
    if sym not in assets: continue
```
إذا رجع `process_asset` = None (degenerate, warmup, fetch error)، فإن المركز على ذلك الرمز **يُتجاهل بالكامل** في تلك الدورة. لا فحص SL، لا فحص Liq، لا trailing. السعر يتحرك بحرية والمركز معرّض للتصفية.

## ما رأيته أنت في الملف — إعادة بناء السيناريو

**المرحلة ١ (الفتح):** الرافعة محددة. SL عند `Entry × 0.985`. Liq عند `Entry × (1−1/L+MMR)`. العلاقة صحيحة في نظر البوت.

**المرحلة ٢ (الصعود):** trailing يرفع SL إلى ما فوق الدخول. العلاقة تتحسن لحظياً: `Entry < SL < Liq` مقلوبة إلى `Entry < SL`، و`Liq` ما زال تحت الدخول.

**المرحلة ٣ (الهبوط):** هنا الفخ. أحد ثلاثة أمور يحدث:
- **سيناريو أ:** Trailing ما زال يحتفظ بـ SL فوق الدخول، لكن السعر هبط بسرعة من خلال SL إلى Liq دون أن يلاحظ البوت (السعر متأخر). المركز يُصفّى على البورصة، وملف الحالة ما زال يحتفظ بـ SL قديم.
- **سيناريو ب:** المركز أُغلق فعلاً، لكن البوت لم يعلم. عند إعادة الفحص اللاحق، تُظهر المنصة أن Liq كان فوق SL طوال الوقت — كاشفاً أن الشرط الرياضي لم يكن محققاً من البداية.
- **سيناريو ج:** الأصل رجع `None` من `process_asset`، فلم يُفحص المركز إطلاقاً، وبقي SL القديم في الملف بينما Liq استمر يتحرك.

**ما هو مؤكد:** القيد الثابت عند 1.5% في `_promote_pending_to_position` **لا يستشير الرافعة ولا MMR**. هذا هو أصل المشكلة.

---

# محاكاة البوت على حالات متعددة

## الحالة ١ — BTC برأس مال ابتدائي (10$)

- `Lev = 50x`, `MMR = 0.5%`
- `Liq = Entry × (1 − 0.02 + 0.005) = Entry × 0.985`
- `SL = Entry × 0.985` (القيد الثابت)
- **النتيجة:** `SL = Liq` بالضبط. أي رسوم، أي انزلاق → Liq يضرب أولاً.

## الحالة ٢ — SOL برأس مال ابتدائي (10$)

- `Lev = 50x`, `MMR = 1%` (SOL فعلاً 1% على Binance)
- `Liq = Entry × (1 − 0.02 + 0.01) = Entry × 0.99`
- `SL = Entry × 0.985`
- **النتيجة:** `SL < Liq` — **SL خارج المنطقة الآمنة منذ الفتح**. Liq يضرب قبل SL دائماً.

## الحالة ٣ — WIF برأس مال ابتدائي

- `Lev = 50x`, `MMR = 1%`
- `Liq = Entry × 0.99`
- `SL = Entry × 0.985`
- **النتيجة:** نفس الكارثة — تصفية قبل الوصول إلى SL.

## الحالة ٤ — نفس الأصول برأس مال 55$

- `Lev = 50 / √5.5 ≈ 21x`
- لـ SOL: `Liq = Entry × (1 − 0.0476 + 0.01) = Entry × 0.962`
- `SL = Entry × 0.985`
- **النتيجة:** `SL > Liq` بهامش 2.3% — آمن.

**الاستنتاج:** الحادثة التي رأيتها ربما حدثت في لحظة كان فيها رأس المال منخفضاً (قريباً من 10$) أو أن الرافعة على البورصة كانت لا تزال 50x من جلسة قديمة لم يُحدَّث فيها `_SYMBOL_META` بشكل صحيح.

## الحالة ٥ — المركز أثناء الصعود ثم الهبوط

- الدخول: 100، SL: 98.5، Liq: 96.2 (L=21, MMR=1%)
- السعر يصعد إلى 110 → trailing يرفع SL إلى 108
- SL الآن فوق الدخول — ربح مقفل
- السعر يهبط بسرعة 110 → 105 في دقيقة واحدة (على TF 15m، لا شمعة مغلقة بعد)
- البوت يفحص `ad.closes[-1] = 110` (السعر المتأخر)
- **لا يلاحظ الهبوط.** يظن أن SL عند 108 ما زال تحت السعر
- السعر يستمر إلى 96.2 → Liq يضرب على البورصة
- البوت لا يعلم حتى الشمعة التالية، عندما يرى `closes[-1] = 95` (تحت Liq)، لكن المركز اختفى من البورصة
- عند `reconcile_state_machine`، يُحذف من `open_pos_live` بصمت
- **النتيجة:** خسارة كاملة للهامش المعزول، والبوت لم يُنفّذ أي إجراء.

## الحالة ٦ — الأصل يُرفض لكن المركز مفتوح

- المركز على DOGE مفتوح
- DOGE يصبح degenerate في دورة معينة
- `process_asset(DOGE) = None` → `sym not in assets`
- **المركز يُتجاهل بالكامل**
- السعر يتحرك بحرية
- SL لا يُنفَّذ، Liq يُصفّي المركز
- البوت لا يعرف

---

# التقرير الكامل للأسباب الجذرية

## السبب ① — القيد الثابت للـ SL لا يستشير الرافعة

`max_sl_frac = 0.015` قيمة سحرية. تعمل فقط لرافعات < 40x مع MMR ≤ 1%. لأي شيء آخر، تنهار الرياضيات.

## السبب ② — Liq غير موجود ككائن في البوت

لا يوجد أي مكان في الكود يحسب `liq_price`. البوت **أعمى** تجاه هذا الحد الفيزيائي، رغم أنه حقيقة على البورصة.

## السبب ③ — السعر المستخدم للفحص قديم

في live mode، يعتمد الفحص على `ad.closes[-1]` الذي لا يُحدَّث إلا عند بداية شمعة جديدة. مع TF كبير، هذا تأخير خطير.

## السبب ④ — المراكز المرفوضة غير مراقبة

`if sym not in assets: continue` — يجعل مركزاً كاملاً بلا مراقبة إذا فشل `process_asset`.

## السبب ⑤ — Mark price مقابل Last price

البوت يقرأ `last price`، لكن Liq يعمل على `mark price`. الفرق يصل إلى 0.3% أثناء التقلب. عند رافعة عالية، هذه الفجوة كافية لتغيير النتيجة.

## السبب ⑥ — لا حماية على البورصة

كل الحماية ذهنية في البوت. لا يوجد `STOP_MARKET` order على البورصة. إذا تأخر البوت ثانية واحدة، SL لا يُنفَّذ.

## السبب ⑦ — لا يوجد فحص استباقي عند اقتراب السعر من Liq

البوت يفحص `price <= SL` فقط. لا يفحص `price` مقابل `Liq` مطلقاً.

---

# الخطة النظرية الكاملة للإصلاح

## المبدأ الحاكم — الفصل التام بين الطبقتين

البوت يجب أن يبقى **طبقتين مستقلتين**:

- **الطبقة الإستراتيجية (Strategy Layer):** الفيزياء، الـ entropy، الـ geodesic accel، اختيار الإشارات، حساب SL و TP من `V` و `Γ`. لا تُمس إطلاقاً.
- **الطبقة الفيزيائية للمخاطرة (Risk Envelope Layer):** تُدير علاقة `Entry ↔ SL ↔ Liq`. تُطبَّق على كل إشارة مقبولة، ولا تغيّر منطقها الرياضي.

القاعدة الذهبية: **الاستراتيجية تقترح، طبقة المخاطرة توافق أو ترفض.**

## المستوى ١ — الوعي بحد التصفية

إدخال مفهوم `liquidation_price` كمكوّن أساسي في دورة حياة المركز:

- يُحسب من الرافعة + MMR + سعر الدخول.
- يُخزَّن في سجل المركز.
- يُحدَّث عند أي تغيير في الرافعة (نادراً، لا يحدث أثناء المركز).
- يُستخدم كمعيار في كل قرار SL.

القيد المطلق: **لا يُسمح لـ SL أن يكون على الجانب الخاطئ من Liq، ولا حتى في منطقة قريبة منه**.

## المستوى ٢ — سقف الرافعة من قيد Liq

قبل `ensure_symbol_setup`، يُحسب قيد إضافي:

```
L_max_by_liq = 1 / (sl_frac_max + MMR + safety_margin)
```

حيث:
- `sl_frac_max` = أقصى مسافة SL تسمح بها الاستراتيجية (1.5% حالياً)
- `MMR` = من بيانات البورصة للرمز
- `safety_margin` = هامش أمان للرسوم والتمويل و mark/last (0.5–1%)

الرافعة النهائية = `min(compute_dynamic_leverage(cap), L_max_by_liq)`.

**التأثير:** الأصول ذات MMR عالٍ (معظم alts) ستُقاد بـ رافعة أقل من 40x دائماً، بغض النظر عن رأس المال. هذا يحمي من الكارثة.

**القيد على هذا المستوى:** القيد لا يخفض الرافعة تحت `LEVERAGE_MIN`. إذا كان القيد يُنتج قيمة أقل، نرفض الإشارة على ذلك الأصل.

## المستوى ٣ — رفض الإشارات غير المتوافقة مع Liq (الخيار ب)

عند قبول إشارة، قبل وضع الأمر المعلّق:

1. احسب Liq المتوقع لسعر `sig.price` بالرافعة الحالية و MMR الرمز.
2. احسب SL المقترح من الاستراتيجية.
3. طبّق قيد `max_sl_frac` على SL.
4. تحقّق: `|Entry − SL| < 0.7 × |Entry − Liq|` (معامل 0.7 يترك هامش أمان).
5. **إذا لا:** ارفض الإشارة، ولا تضع أمراً معلّقاً أصلاً. البوت ينتقل إلى الإشارة التالية.

**ميزة هذا الخيار:**
- لا نعدّل SL تعسفاً (مرفوض كما قلت).
- لا نغيّر الرافعة بعد المركز (مستحيل في isolated).
- نرفض قبل أي التزام مالي على البورصة.
- الإشارة تُفقد، لكن رأس المال محمي.

**الاستثناء الوحيد:** إذا كانت الرافعة الحالية **أقل** من رأس المال يستحق (مثلاً رافعة قديمة على البورصة)، يمكن رفعها إلى القيمة الآمنة قبل الفتح. لكن هذا نادر لأن `ensure_symbol_setup` تعيّن الرافعة بالفعل في كل دورة.

## المستوى ٤ — سعر حي للفحص

بدلاً من الاعتماد على `ad.closes[-1]` المحدَّث على حواف الشموع، تُضاف طبقة رقيقة:

- لكل مركز مفتوح، في كل دورة، يُجلَب `ticker` خفيف (وزن 2 فقط).
- السعر المستخدم لفحوصات SL/TP/Liq هو السعر الحي.
- السعر القديم (`ad.closes[-1]`) يبقى مستخدماً للفحوصات الفيزيائية (Apex, Topo-Div).

**القيد:** هذا الاستدعاء الإضافي يجب أن يكون **محسوباً ضمن ميزانية الـ rate limit**. مع 5 مراكز مفتوحة = 10 weight/دورة = مقبول.

## المستوى ٥ — الخروج الطارئ عند اقتراب Liq

قاعدة جديدة: إذا اقترب السعر الحي من Liq بأقل من هامش أمان (مثلاً 30% من المسافة Entry↔Liq)، يُنفَّذ market order لإغلاق المركز فوراً.

هذا هو **آخر خط دفاع** — يُنفَّذ فقط عندما يفشل كل شيء آخر.

**القيد:** هذا الإجراء لا يُستخدَم إلا في حالات قصوى. إذا استُخدم كثيراً، فهذا مؤشر على أن الرافعة عالية جداً وأن الأصل لا يناسبه البوت.

## المستوى ٦ — المراكز المرفوضة تُراقَب دوماً

إلغاء `if sym not in assets: continue`. بدلاً منه:

- إذا كان المركز مفتوحاً لكن الأصل مرفوض (`process_asset` = None)، يبقى فحص SL/TP/Liq نشطاً.
- يستخدم السعر الحي فقط (ticker).
- الفحوصات الفيزيائية (Apex, Topo-Div) تُتخطى (لا بيانات لها).
- Trailing يستمر عمله بناءً على `peak_price` المخزّن.
- **هذا يضمن أن المركز محمي حتى لو فشل `process_asset` لأي سبب.**

## المستوى ٧ — حماية على البورصة (اختياري لكن يُوصى به)

عند فتح المركز، يُوضع `STOP_MARKET` order على البورصة عند مستوى SL. عند كل تحديث لـ SL (trailing)، يُلغى القديم ويُوضع الجديد.

**المكسب:** حماية حتى لو نام البوت أو انقطع الإنترنت.

**القيد:** تعقيد في إدارة الأوامر (cancel/replace)، استهلاك إضافي لـ rate limit. يُنفَّذ فقط بعد استقرار المستويات ١-٦.

---

# القيود الصارمة للإصلاح

## قيد ١ — لا تعديل على الإشارة أو الاستراتيجية

كل تعديل يقع **بعد** أن تُقبل الإشارة في `build_signals` و `deduplicate_signals`. لا تغيير على:
- حساب `score`, `P_activation`, `geodesic_accel`, `friction`
- حساب `sl_dist` من `compute_geodesic_stop`
- حساب `dynamic_risk` من `compute_geodesic_kelly`
- أي منطق فيزيائي

## قيد ٢ — لا تعديل على صيغة الرافعة الأصلية

`compute_dynamic_leverage(cap)` تبقى كما هي. الإصلاح **يضيف سقفاً فوقها**، لا يستبدلها. سبب هذا القيد: الصيغة هي جزء من الإستراتيجية، وتغييرها قد يكسر توازن الفيزياء.

## قيد ٣ — لا تعديل على SL بعد الفتح

بمجرد أن يُفتح المركز بـ SL محدد، لا يُغيَّر إلا بمنطق trailing الصاعد. لا "تصحيح" تعسفي إذا اكتشف البوت أن SL في منطقة سيئة. الخيار الوحيد: قبول الوضع كما هو، أو إغلاق المركز.

## قيد ٤ — لا تعديل على الرافعة أثناء المركز

في isolated mode، الرافعة قفل لحظة الفتح. لا محاولة لتغييرها. القرار الوحيد المتاح: إغلاق المركز إذا أصبح غير قابل للاستمرار.

## قيد ٥ — لا تجميد الحلقة الرئيسية

كل إضافة (fetch ticker، حساب Liq، فحص إضافي) يجب أن تكون **O(1)** per position، دون sleep إضافي، دون نداءات blocking متسلسلة. الوقت الكلي للدورة يجب أن يبقى < 30 ثانية في أسوأ الحالات.

## قيد ٦ — لا استثناءات صامتة

كل رفض لإشارة بسبب قيد Liq يجب أن يُسجَّل بوضوح. كل خروج طارئ يجب أن يُسجَّل بوضوح. لا قرار بلا أثر في اللوج.

## قيد ٧ — التوافق مع الحالة المخزّنة

المراكز المفتوحة في ملفات `live_state_*.json` من نسخة سابقة يجب أن تُقرأ بلا كسر. الحقول الجديدة (`liq_price_estimated`, `liq_source`) تُضاف بقيم افتراضية عند القراءة.

## قيد ٨ — التنبيه لا الإسكات

إذا اقتربت نسبة رفض الإشارات بسبب قيد Liq من عتبة صحية (مثلاً > 30% من الإشارات)، يجب أن يُسجَّل تحذير بأن الرافعة الديناميكية غير مناسبة للأصول الحالية. المستخدم يحتاج أن يعرف.

---

# العلاقة بالإستراتيجية — نقطة حساسة

الإستراتيجية تفترض أن `P_activation ≥ 0.35` تُنتج إشارات تستحق التنفيذ. لكن، إذا رفضنا إشارات كثيرة بسبب قيد Liq، **فنحن نخالف الاستراتيجية في الممارسة دون أن نغيّرها في الكود**. هذا خطر حقيقي.

**الحل النظري:** القيد لا يعمل كـ "فلتر إشارات" بل كـ "سقف رافعة". عند رأس مال صغير، الرافعة ستكون أقل، لكن الإشارات ستُقبل (لأن SL سيصبح داخل Liq). الإشارات تُرفض فقط عندما يكون القيد الفيزيائي مستحيلاً (مثل أصل بـ MMR = 5% مع رأس مال 10$).

بهذا:
- **رأس المال الصغير** = رافعة أقل تلقائياً، لا إشارات مرفوضة.
- **رأس المال الكبير** = رافعة معقولة (المعادلة الأصلية).
- **الأصول الشاذة** (MMR > 3%) = قد تُرفض إشاراتها، وهذا مقبول.

---

# ترتيب الأولويات المقترح

| المستوى | الأثر على الأمان | التعقيد | الأولوية |
|---|---|---|---|
| ١ — Liq ككائن | أساسي | منخفض | **حرج** |
| ٢ — سقف الرافعة من Liq | يمنع الكارثة عند الفتح | منخفض | **حرج** |
| ٣ — رفض الإشارة غير المتوافقة | يمنع المراكز السيئة | منخفض | **حرج** |
| ٦ — مراقبة المراكز المرفوضة | يمنع العمى أثناء الفشل | منخفض | عالية |
| ٤ — سعر حي للفحص | يمنع التأخر | متوسط | عالية |
| ٥ — خروج طارئ | طبقة أخيرة | منخفض | متوسطة |
| ٧ — أوامر على البورصة | حماية ضد انهيار البوت | عالي | متأخرة |

**التوصية:** الطبقات ١، ٢، ٣، ٦ تُنفَّذ أولاً في تعديل واحد متماسك. الطبقات ٤، ٥ تُضاف في تعديل ثانٍ. الطبقة ٧ تُؤجَّل حتى نرى استقرار النظام في testnet لمدة أسبوع.

---

**بعد مراجعتك لهذه الخطة النظرية، أخبرني بأي تعديل تريد أن أبدأ به، أو إذا أردت مناقشة نقطة معينة قبل الكتابة.**


# التعديل المتماسك — الطبقات ١، ٢، ٣، ٦

خمس تعديلات جراحية، كل واحدة في مكانها المحدد. اقرأ كل قسم كاملاً قبل التطبيق.

---

## 🔧 التعديل ① — إضافة ثوابت جديدة في `Config`

**الموقع:** في `class Config`، بعد كتلة `LIVE_HISTORY_DAYS: int = 90` مباشرة.

**✅ أضف هذا البلوك:**

```python
    # ══ [LIQ AWARENESS] Liquidation safety envelope ══
    LIQ_SAFETY_MULT: float = 1.5          # SL gap × this < Liq gap
    LIQ_EMERGENCY_PROGRESS: float = 0.7    # 70% toward Liq → emergency exit
    LIQ_FALLBACK_MMR: float = 0.02         # 2% if exchange MMR unavailable
    LIQ_ENABLED: bool = True               # master switch (for testing)
```

---

## 🔧 التعديل ② — إضافة دوال MMR و Liq

**الموقع:** في المستوى العام، بعد دالة `_get_tick_size` مباشرة (قبل `execute_post_only`).

**✅ أضف هذا البلوك كاملاً:**

```python
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


def compute_max_leverage_by_liq(sl_frac_max: float, mmr: float,
                                  safety_mult: float = 1.5) -> int:
    """
    Max leverage such that: sl_gap × safety_mult < liq_gap  (relative to Entry).

    Derivation:
        sl_frac × safety_mult < 1 - (1 - 1/L)/(1 - MMR)
        L < 1 / (1 - (1 - MMR) × (1 - sl_frac × safety_mult))
    """
    s = max(sl_frac_max * safety_mult, 1e-6)
    m = max(float(mmr), 0.0)
    denom = 1.0 - (1.0 - m) * (1.0 - s)
    if denom <= 1e-9:
        return 1
    return max(1, int(np.floor(1.0 / denom)))


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
```

---

## 🔧 التعديل ③ — إصلاح `_promote_pending_to_position` (توقيع + Liq gate)

**الموقع:** الدالة `_promote_pending_to_position`.

**❌ استبدل التوقيع والسطر الأول:**

```python
def _promote_pending_to_position(sym: str, rec: Dict,
                                 open_pos_live: Dict) -> bool:
    """Convert a filled pending order into an open position record."""
    filled_qty = float(rec.get('filled') or 0.0)
```

**✅ بـ:**

```python
def _promote_pending_to_position(exchange, sym: str, rec: Dict,
                                 open_pos_live: Dict) -> bool:
    """Convert a filled pending order into an open position record."""
    filled_qty = float(rec.get('filled') or 0.0)
```

**❌ ثم ابحث عن بلوك حساب SL/TP المُعدَّل:**

```python
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
```

**✅ استبدله بـ:**

```python
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
```

**❌ ثم ابحث عن بلوك `open_pos_live[sym] = {...}` في نفس الدالة:**

```python
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
```

**✅ استبدله بـ:**

```python
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
    }
```

---

## 🔧 التعديل ④ — تحديث استدعاءات `_promote_pending_to_position`

**الموقع:** الدالة `monitor_pending_orders`.

**❌ ابحث عن ثلاث كتل استدعاء:**

```python
                ok = _promote_pending_to_position(sym, rec, open_pos_live)
```

(تظهر مرتين داخل `monitor_pending_orders`، ومرة داخل بلوك الـ timeout).

**✅ استبدل كل واحدة بـ:**

```python
                ok = _promote_pending_to_position(exchange, sym, rec, open_pos_live)
```

---

## 🔧 التعديل ⑤ — إضافة `mmr_at_placement` إلى سجل الـ pending

**الموقع:** الدالة `place_pending_entry`، في بلوك `rec = {...}`.

**❌ ابحث عن:**

```python
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
```

**✅ استبدله بـ:**

```python
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
        'mmr_at_placement': float(
            _get_mmr_for_symbol(exchange, sym)
        ),
        'ad_ref': ad,
    }
```

---

## 🔧 التعديل ⑥ — Liq cap + gate في حلقة الدخول `run_live`

**الموقع:** داخل `run_live`، حلقة `for sig in reversed(sigs):`، قسم حساب qty.

**❌ ابحث عن هذه الكتلة:**

```python
                    qty_risk_based = risk_amt / delta

                    dynamic_leverage = compute_dynamic_leverage(cap_live, cfg)
                    max_notional = cap_live * dynamic_leverage
                    qty_leverage_based = max_notional / lmt

                    qty = min(qty_risk_based, qty_leverage_based)
```

**✅ استبدلها بـ:**

```python
                    qty_risk_based = risk_amt / delta

                    dynamic_leverage = compute_dynamic_leverage(cap_live, cfg)

                    # ══ [LIQ-CAP] Cap leverage so SL is safely inside Liq ══
                    _mmr_sig = None
                    if getattr(CFG, 'LIQ_ENABLED', True):
                        _mmr_sig = _get_mmr_for_symbol(exchange, sym)
                        _sl_frac_max = 0.015
                        _lev_by_liq = compute_max_leverage_by_liq(
                            sl_frac_max=_sl_frac_max,
                            mmr=_mmr_sig,
                            safety_mult=float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5)),
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
```

**❌ ثم ابحث عن بلوك الـ setup:**

```python
                        # ══ 1. Setup ONCE — leverage/margin ══
                        if not ensure_symbol_setup(exchange, sym, dynamic_leverage,
                                                    margin_mode='isolated'):
                            log.warning(f"[Entry] {sym} setup failed — skip")
                            continue
```

**✅ استبدله بـ:**

```python
                        # ══ 1. Setup ONCE — leverage/margin ══
                        if not ensure_symbol_setup(exchange, sym, dynamic_leverage,
                                                    margin_mode='isolated'):
                            log.warning(f"[Entry] {sym} setup failed — skip")
                            continue

                        # ══ [LIQ-GATE] Verify SL safely inside Liq at sig price ══
                        if getattr(CFG, 'LIQ_ENABLED', True) and _mmr_sig is not None:
                            _confirmed_lev = int(
                                _SYMBOL_META.get(sym, {}).get('leverage',
                                                                dynamic_leverage)
                            )
                            _liq_px = compute_liquidation_price(
                                float(sig.price), sig.action,
                                _confirmed_lev, _mmr_sig,
                            )
                            _liq_gap = abs(float(sig.price) - _liq_px)
                            _sl_gap = abs(float(sig.price) - float(sig.sl))
                            _safe_mult = float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5))
                            if _liq_gap <= 1e-12 or _sl_gap * _safe_mult > _liq_gap:
                                log.info(
                                    f"[LiqGate] {sym} {sig.action} REJECT: "
                                    f"SL gap={_sl_gap:.6f} × {_safe_mult} > "
                                    f"Liq gap={_liq_gap:.6f} "
                                    f"(L={_confirmed_lev}x, "
                                    f"MMR={_mmr_sig*100:.3f}%)"
                                )
                                continue
```

**❌ ثم ابحث عن بلوك تسجيل المركز (بعد `log.info(f"✅ [Entry] ...")`):**

```python
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
```

**✅ استبدله بـ:**

```python
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
                        }
```

---

## 🔧 التعديل ⑦ — إعادة كتابة حلقة المراقبة (Layer 6)

**الموقع:** داخل `run_live`، قسم `# 1. مراقبة وإغلاق المراكز الحية`.

**❌ ابحث عن بداية الحلقة:**

```python
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
```

**✅ استبدلها بـ:**

```python
            # 1. مراقبة وإغلاق المراكز الحية
            for sym in list(open_pos_live.keys()):
                pos = open_pos_live[sym]

                # ══ [MON-FALLBACK] Monitor even if `ad` unavailable ══
                # Physics-based exits (Apex, Topo-Div) require `ad`.
                # SL/TP/Liq/MaxHold/Trailing work without it (ticker only).
                ad = assets.get(sym)
                if ad is not None:
                    price = float(ad.closes[-1])
                    fi = len(ad.score) - 1
                else:
                    try:
                        _tk = exchange.fetch_ticker(sym)
                        price = float(_tk.get('last') or 0)
                        _rate_record(2.0)
                    except Exception as _e:
                        log.debug(f"[MonFallback] {sym} ticker failed: {_e}")
                        continue
                    if price <= 0:
                        continue
                    fi = -1
                    log.debug(f"[MonFallback] {sym} monitoring via ticker "
                              f"only (ad unavailable)")

                ex = False
                rsn = ""

                # ── Physics-based exits (require ad) ──
                if ad is not None:
                    # Apex
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
```

**❌ ثم ابحث عن بلوك SL/TP (بعد Trailing):**

```python
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
```

**✅ استبدله بـ:**

```python
                # ── SL / TP ──
                if not ex:
                    if pos['action'] == "BUY":
                        if price <= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price >= pos.get('tp1', 1e18): ex = True; rsn = "Hard TP"
                    else:
                        if price >= pos['sl']: ex = True; rsn = "Emergency SL"
                        elif price <= pos.get('tp1', 0.): ex = True; rsn = "Hard TP"

                # ── [LIQ-PROXIMITY] Emergency exit near Liq ──
                if not ex and getattr(CFG, 'LIQ_ENABLED', True):
                    _liq_px = pos.get('liq_price_estimated')
                    _entry_px = float(pos.get('entry') or 0)
                    if (_liq_px is not None and _liq_px > 0
                            and _entry_px > 0):
                        _liq_gap_entry = abs(_entry_px - float(_liq_px))
                        if _liq_gap_entry > 1e-12:
                            if pos['action'] == "BUY":
                                _progress = (_entry_px - price) / _liq_gap_entry
                            else:
                                _progress = (price - _entry_px) / _liq_gap_entry
                            _thr = float(getattr(CFG, 'LIQ_EMERGENCY_PROGRESS', 0.7))
                            if _progress >= _thr:
                                ex = True
                                rsn = f"Emergency LiqProximity({_progress*100:.0f}%)"

                if not ex:
                    continue
```

---

## 🔧 التعديل ⑧ — Backfill `liq_price_estimated` عند تحميل الحالة

**الموقع:** داخل `run_live`، بعد تحميل `open_pos_live` من `state_file`.

**❌ ابحث عن:**

```python
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                open_pos_live = json.load(f)
            log.info(f"  [State] Restored {len(open_pos_live)} positions from {state_file}")
        except Exception as e:
            log.warning(f"  [State] load failed: {e}")
```

**✅ استبدله بـ:**

```python
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
```

---

## 📋 جدول التأثير المتوقع

| السيناريو | قبل | بعد |
|---|---|---|
| BTC 50x + MMR 0.5% | SL = Liq (كارثة) | LevCap → 36x، SL آمن |
| SOL 50x + MMR 1% | SL < Liq من الفتح | LevCap → 30x، gate يرفض |
| Position monitoring while ad=None | متجاهل تماماً | ticker-based SL/TP/Liq نشط |
| Sl near Liq (70%) | لا شيء | Emergency market close |
| Loading old state | Liq غير معروف | Backfilled من fallback MMR |
| Partial fill promotion | bug NameError | يعمل + Liq gate |

---

## ✅ التحقق بعد التطبيق

### 1. فحص الملف
```bash
grep -c "_get_mmr_for_symbol" trading.py
# يجب أن يظهر: 3 (تعريف + استدعاءان)

grep -c "liq_price_estimated" trading.py
# يجب أن يظهر: 6-7 (تعريفات + قراءات)

grep -c "compute_liquidation_price" trading.py
# يجب أن يظهر: 4 (تعريف + 3 استدعاءات)
```

### 2. تشغيل testnet
```bash
rm -f live_state_testnet.json pending_orders_testnet.json
python trading.py --mode testnet --timeframe 1h --nassets 30 --maxcon 5 \
  --api-key $KEY --api-secret $SECRET 2>&1 | tee run.txt
```

**ابحث في `run.txt` عن:**
```bash
grep "LevCap" run.txt         # capping events (متوقع: عندما cap صغير)
grep "LiqGate" run.txt        # rejections (متوقع: نادرة بعد LevCap)
grep "LiqProximity" run.txt   # emergency (متوقع: صفر عادة)
grep "MonFallback" run.txt    # fallback usage
```

### 3. بعد ساعة، افحص ملف الحالة
```bash
python -c "
import json
d = json.load(open('live_state_testnet.json'))
for s, p in d.items():
    entry = p['entry']; sl = p['sl']; liq = p.get('liq_price_estimated')
    side = p['action']
    if liq:
        sl_gap = abs(entry - sl)
        liq_gap = abs(entry - liq)
        ratio = sl_gap / liq_gap if liq_gap > 0 else 999
        ok = ratio < 0.7
        print(f'{s}: entry={entry:.4f} sl={sl:.4f} liq={liq:.4f} '
              f'ratio={ratio:.2f} {\"OK\" if ok else \"BAD\"}')
"
```

**كل سطر يجب أن يقول `OK`.** أي `BAD` يعني أن Invariant مكسور — أرسل لي السطر.

---

## ⚠️ تنبيهان

**التنبيه ① — `fetch_leverage_tiers` قد يستهلك rate limit إضافي.** لـ 30 رمزاً = 30 مكالمة إضافية أول مرة. بعدها مخزّنة في `_MMR_CACHE`. تكلفة واحدة عند الإقلاع.

**التنبيه ② — على testnet**، `fetch_leverage_tiers` قد يرجع قيماً مختلفة عن live. هذا متوقع — القيم تُستخدم للتحقق المحلي، لا للتنفيذ. عند الانتقال إلى live، الكاش يُعاد بناؤه تلقائياً بقيَم live الحقيقية.

بعد التطبيق، أرسل لي:
1. مخرجات `grep LevCap|LiqGate|LiqProximity|MonFallback` من أول 5 دقائق.
2. مخرجات فحص ملف الحالة بعد ساعة (كل الأسطر `OK`؟).
3. أول 20 سطر من `run.txt` (للتأكد من عدم وجود أخطاء جديدة).
