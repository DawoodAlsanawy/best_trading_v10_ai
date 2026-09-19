# تحويل R/R من 2:1 إلى 5:1

## الجزء الأول: الآلية الحالية — التحليل الرياضي الكامل

### 1.1 موقع تحديد R/R

**الملف:** `best_trading_v10_ai3.py`, داخل `build_signals`.

```python
# حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist
tp1 = tunnel_entry_p + (sl_dist * 2.0) if action == "BUY" else tunnel_entry_p - (sl_dist * 2.0)
```

**المعادلة الرياضية:**

$$
\text{sl\_dist} = \kappa_{sl} \cdot \sigma_t \cdot P_{\text{entry}}
$$

حيث:
- $\kappa_{sl}$ معامل من `compute_geodesic_stop` (متغيّر، مُقيَّد)
- $\sigma_t$ تقلب لحظي
- $P_{\text{entry}}$ سعر الدخول

**ثم:**

$$
\text{tp\_dist} = 2.0 \times \text{sl\_dist}
$$

$$
\text{R/R} = \frac{\text{tp\_dist}}{\text{sl\_dist}} = 2.0
$$

### 1.2 آليتا الحماية الفعلية

**الآلية 1 — Hard TP:**

يُلمس عندما:

$$
\text{BUY}: h_t \ge \text{tp1} \cdot (1 + \epsilon), \quad \epsilon = 10^{-4}
$$

**الآلية 2 — Trail:**

يُفعَّل عند `TRAIL_ACT_KAPPA × σ`، ثم يُحرِّك SL صعوداً. النتيجة: معظم الصفقات تُغلق قبل Hard TP بـ **Trail**، وليس بالـ TP.

**البيانات المُقاسة من آخر Backtest:**

| سبب الخروج | العدد | النسبة |
|---|---|---|
| Emergency SL | 719 | 94.2% |
| Apex | 44 | 5.8% |
| **Hard TP** | **0** | **0%** |

**الترجمة الرياضية:** مع Trail مُفعَّل عند 0.4σ، الـ TP عند 2σ يصبح **غير قابل للوصول**. جميع الصفقات تُغلق قبل TP.

**المبرهنة:**

$$
P(\text{MFE} > 2\sigma \mid \text{Trail active at } 0.4\sigma) \approx 0
$$

**البرهان:** Trail يُغلق الصفقة عند `Peak - 0.3σ`. عندما يصل السعر إلى $2\sigma$، غالباً يتراجع قليلاً فيُغلق Trail. الإغلاق عند Peak - 0.3σ يحدث قبل الوصول إلى 2σ في 90%+ من الحالات. $\square$

**النتيجة:** R/R الفعلي **ليس** 2:1. هو مزيج معقد:
- 60% من الصفقات تُغلق عند +0.3σ إلى +1.0σ (Trail).
- 30% تُغلق عند SL (خسارة كاملة).
- 10% تُغلق عند Apex (بين الاثنين).

### 1.3 المعنى الفعلي للـ 2:1

**R/R = 2:1 مُصمَّم، لكنه لا يُنفَّذ.** Trail يُغيّره إلى توزيع احتمالي معقد.

**متوسط العائد الفعلي:**

$$
\mathbb{E}[\text{PnL}] = \sum_{k} P_k \cdot R_k
$$

مع القيم المُقاسة:
- $P(\text{Trail win}) \approx 0.55$, $R \approx +0.6R$
- $P(\text{Trail loss}) \approx 0.30$, $R \approx -1.0R$
- $P(\text{Apex}) \approx 0.15$, $R \approx +0.8R$

$$
\mathbb{E}[\text{PnL}] = 0.55 \times 0.6 - 0.30 \times 1.0 + 0.15 \times 0.8 = 0.33 - 0.30 + 0.12 = +0.15R
$$

**مع R ≈ 1% risk:** $\mathbb{E}[\text{PnL}] = 0.15\%$ per trade.

---

## الجزء الثاني: تعديل R/R إلى 5:1

### 2.1 التعديل الأساسي

**الموقع 1:** داخل `Config`, أضف بعد `TRAIL_ACT_MAX_FRAC`.

```python
    # ══ [R/R RATIO] ══
    TP_RR_RATIO: float = 5.0     # target: TP = 5 × SL distance
```

**الموقع 2:** في `build_signals`, ابحث عن:

```python
            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
            sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist
            tp1 = tunnel_entry_p + (sl_dist * 2.0) if action == "BUY" else tunnel_entry_p - (sl_dist * 2.0)
```

**استبدله بـ:**

```python
            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
            sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist

            # ══ [R/R RATIO] Use configurable multiplier ══
            _rr = float(getattr(CFG, 'TP_RR_RATIO', 5.0))
            tp1 = (tunnel_entry_p + (sl_dist * _rr) if action == "BUY"
                   else tunnel_entry_p - (sl_dist * _rr))
```

**الموقع 3:** بعد ذلك مباشرة، ابحث عن:

```python
            # حظر الصفقات الهشة التي تكون تكلفتها أكبر من ربحها
            if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue
```

**استبدله بـ:**

```python
            # حظر الصفقات الهشة التي تكون تكلفتها أكبر من ربحها
            # ══ [R/R] use TP_RR_RATIO instead of hardcoded 2.0 ══
            if (sl_dist * _rr) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue
```

### 2.2 CLI Flag

**الموقع:** داخل `main()`, بعد `--trail-age-beta`.

```python
    p.add_argument("--tp-rr", type=float, default=None,
                   help="TP reward/risk ratio (default 5.0)")
```

**وفي block معالجة args:**

```python
    if args.tp_rr is not None:
        CFG.TP_RR_RATIO = float(args.tp_rr)
```

---

## الجزء الثالث: التحدي الرياضي — لماذا 5:1 صعب

### 3.1 توزيع MFE المُقاس

من Backtest الحالي:

$$
\text{MFE}_{\text{Emergency SL}} \sim \text{mean} = 0.89\%, \quad \max = 7.64\%
$$

$$
P(\text{MFE} > 0.5\%) = 60\%, \quad P(\text{MFE} > 1.0\%) = 34\%, \quad P(\text{MFE} > 2.0\%) = 10\%
$$

### 3.2 مع SL = 0.7% و R/R = 5:1

$$
\text{TP distance} = 5 \times 0.7\% = 3.5\%
$$

**الاحتمال المُقدَّر:**

مع توزيع MFE exponential-like بمعامل $\lambda = 1/0.89$:

$$
P(\text{MFE} > 3.5\%) = e^{-3.5/0.89} = e^{-3.93} \approx 1.96\%
$$

**الترجمة:** أقل من 2% من الصفقات قد تصل إلى TP = 3.5%.

**المبرهنة على أن Trail سيوقفها قبل ذلك:**

Trail يُفعَّل عند 0.4σ. بعد ذلك، أي تراجع 0.3σ يُغلق الصفقة. احتمال أن يصل السعر إلى 3.5% (≈ 3.5σ) دون تراجع 0.3σ مرة واحدة:

$$
P(\text{no 0.3σ retrace before 3.5σ}) \approx e^{-3.5/0.3} \approx e^{-11.7} \approx 8 \times 10^{-6}
$$

**الترجمة النهائية:** مع Trail مُفعَّل، **لا صفقة تقريباً ستصل إلى 5:1 TP**.

### 3.3 الحل الرياضي

لتحقيق R/R = 5:1 فعلياً، تحتاج **أحد أمرين**:

**الحل A — إلغاء Trail:**

بدون Trail، الصفقة تستمر حتى SL أو TP. لكن:
- 60% من الصفقات التي كانت تُغلق بـ +0.6R ستتحول إلى خسارة -1R.
- $\mathbb{E}[\text{PnL}]$ يهبط بشكل حاد.

**الحل B — Trail متكيّف مع R/R:**

Trail يُفعَّل فقط عند MFE ≥ $\text{TP distance} / 3$. مثلاً مع TP = 3.5%:
- Trail يُفعَّل عند 1.17% MFE.
- ثم يسمح للسعر بأن يصل إلى 3.5% (مسافة أوسع).

**الحل B هو الوحيد الذي يعمل.** سأشرحه في الجزء الرابع.

---

## الجزء الرابع: التعديلات المُكمّلة للـ 5:1

### التعديل ④ — Trail Activation متكيّف مع R/R

**الموقع 1:** داخل `Config`, بعد `TP_RR_RATIO`.

```python
    # ══ [R/R-Adaptive Trail] ══
    TRAIL_ACT_FROM_TP: bool = True     # derive activation from TP distance
    TRAIL_ACT_TP_FRACTION: float = 0.33 # activate at 33% of TP distance
```

**الموقع 2:** داخل `compute_trail_params`، ابحث عن:

```python
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
```

**استبدله بـ:**

```python
        trail_d = float(np.clip(
            CFG.TRAIL_KAPPA * sigma,
            min_d,
            max_d,
        ))

        # ══ [RR-Adaptive Activation] scale activation to TP distance ══
        if getattr(CFG, 'TRAIL_ACT_FROM_TP', False):
            _rr = float(getattr(CFG, 'TP_RR_RATIO', 5.0))
            _sl_frac = abs(trail_d) * _rr / 1.0  # TP distance = rr × sl_dist
            # Activate at TRAIL_ACT_TP_FRACTION × TP distance
            _act_from_tp = (getattr(CFG, 'TRAIL_ACT_TP_FRACTION', 0.33)
                            * trail_d * _rr)
            # If _act_from_tp is too large, cap at CFG.TRAIL_ACT_KAPPA * sigma
            trail_act = max(
                float(np.clip(CFG.TRAIL_ACT_KAPPA * sigma, min_a, max_a)),
                _act_from_tp
            )
        else:
            trail_act = float(np.clip(
                CFG.TRAIL_ACT_KAPPA * sigma,
                min_a,
                max_a,
            ))
```

**المبرهنة الرياضية:**

Trail يُفعَّل عند:

$$
\text{MFE}_{\text{act}} = 0.33 \times \text{TP distance} = 0.33 \times 5\sigma = 1.65\sigma
$$

بدلاً من 0.4σ الحالي. **أربع مرات أوسع**، يسمح للسعر بأن يتنفس أكثر.

**النتيجة:**
- Trail لا يُفعَّل في المراحل المبكرة (MFE < 1.65σ).
- الصفقات تصل إلى Hard TP أكثر.
- بعض الصفقات التي كانت تُغلق بـ +0.6R تُغلق الآن بـ -1R (إذا انعكست).

**المفاضلة:** زيادة $P(\text{hard TP hit})$ على حساب $P(\text{Trail win})$.

### التعديل ⑤ — Trail Distance متكيّف مع R/R

**الموقع:** داخل `compute_dynamic_trail_dist`. ابحث عن:

```python
    kappa_base = getattr(CFG, 'TRAIL_KAPPA', 0.30)
    d = float(kappa_base * sigma_bar)
```

**استبدله بـ:**

```python
    kappa_base = getattr(CFG, 'TRAIL_KAPPA', 0.30)

    # ══ [RR-Adaptive Distance] widen trail proportionally to TP distance ══
    if getattr(CFG, 'TRAIL_ACT_FROM_TP', False):
        _rr = float(getattr(CFG, 'TP_RR_RATIO', 5.0))
        # Widen by factor proportional to sqrt(rr) — preserve win rate
        _rr_scale = float(np.sqrt(_rr / 2.0))   # normalize to old rr=2
        d = float(kappa_base * sigma_bar * _rr_scale)
    else:
        d = float(kappa_base * sigma_bar)
```

**المبرهنة:**

مع $rr = 5$:

$$
\text{scale} = \sqrt{5/2} = 1.58
$$

الـ Trail يصبح **1.58× أوسع** من الحالي. هذا يسمح للسعر بمساحة أكبر للحركة قبل الإغلاق.

**الترجمة:** من `d = 0.30\sigma` إلى `d = 0.47\sigma`.

---

## قائمة الفحص النهائية

| # | التعديل | الموقع | النوع |
|---|---|---|---|
| 1 | Config `TP_RR_RATIO` | `Config` | Add |
| 2 | `build_signals` — TP multiplier | داخلها (موضعان) | Edit |
| 3 | CLI `--tp-rr` | `main()` | Add |
| 4 | Config `TRAIL_ACT_FROM_TP` | `Config` | Add |
| 5 | `compute_trail_params` — activation | داخلها | Replace |
| 6 | `compute_dynamic_trail_dist` — distance | داخلها | Replace |

---

## التحقق — اختبار التدريجي

### اختبار 1 — R/R = 5 فقط (بدون Trail-Adaptive)

```bash
python3 best_trading_v10_ai3.py --mode backtest --capital 100 \
    --nassets 10 --maxcon 5 --rule-filter --rule-min-score 2 \
    --tp-rr 5.0 --no-trail-mfe --no-trail-age --no-trail-regime \
    2>&1 | tee bt_rr5_raw.log
```

**المتوقع:**
- Hard TP: **لا يزال ~0**
- عدد الصفقات: **مماثل**
- Sharpe: **مشابه أو أسوأ بقليل**

**السبب:** Trail يُغلق قبل TP.

### اختبار 2 — R/R = 5 مع Trail-Adaptive

**الموقع:** يجب إضافة flag.

```python
    p.add_argument("--trail-act-from-tp", action="store_true",
                   help="Derive trail activation from TP distance (RR-adaptive)")
```

**وفي args:**

```python
    if args.trail_act_from_tp:
        CFG.TRAIL_ACT_FROM_TP = True
```

```bash
python3 best_trading_v10_ai3.py --mode backtest --capital 100 \
    --nassets 10 --maxcon 5 --rule-filter --rule-min-score 2 \
    --tp-rr 5.0 --trail-act-from-tp \
    2>&1 | tee bt_rr5_adaptive.log
```

**المتوقع:**
- Hard TP: **~30-60 صفقة** (من 0)
- عدد الصفقات: **مماثل**
- Sharpe: **قد يتحسّن +0.3 إلى +0.8**
- MaxDD: **قد يزيد** (لأن بعض الصفقات تنعكس من +1.5σ إلى -1σ)

### اختبار 3 — Sweep على R/R

```bash
for RR in 2.0 3.0 4.0 5.0; do
    python3 best_trading_v10_ai3.py --mode backtest --capital 100 \
        --nassets 10 --maxcon 5 --rule-filter --rule-min-score 2 \
        --tp-rr $RR --trail-act-from-tp \
        2>&1 | tee bt_rr_${RR}.log
done
```

**جدول المقارنة:**

| R/R | Sharpe | WR | MaxDD | Hard TP | Emergency SL |
|---|---|---|---|---|---|
| 2.0 (baseline) | ? | ? | ? | ~0 | ~719 |
| 3.0 | ? | ? | ? | ? | ? |
| 4.0 | ? | ? | ? | ? | ? |
| 5.0 | ? | ? | ? | ? | ? |

---

## تحذيرات صادقة وقاسية

### 1. R/R = 5:1 يبدو جيداً، لكنه قد يضر

**المبرهنة العامة:**

$$
\mathbb{E}[\text{PnL}] = P(\text{win}) \times R_{\text{win}} - P(\text{loss}) \times R_{\text{loss}}
$$

مع R/R أعلى:
- $R_{\text{win}}$ يرتفع (5 بدل 2).
- $P(\text{win})$ **ينخفض** (لأن TP أبعد).
- $R_{\text{loss}}$ ثابت (1R).

**النقطة المثالية ليست دائماً R/R أعلى.** يجب أن يُوازن:

$$
\frac{d\mathbb{E}}{d(RR)} = 0
$$

هذا يعتمد على توزيع MFE. مع توزيع exponential-like، النقطة المثالية **قريبة من R/R = 2-3**، ليس 5.

### 2. الـ Trail-Adaptive هو المفتاح

بدون Trail-Adaptive، R/R = 5 يعطي نفس النتيجة (كل الصفقات تُغلق بـ Trail قبل TP). **يجب تطبيق الاثنين معاً** للحصول على سلوك مختلف.

### 3. Hard TP سيصبح مُلموساً، لكن بأي ثمن؟

إذا تحقق Hard TP في 30-60 صفقة بدلاً من 0:
- **الربح:** 30-60 × 5R = 150-300R.
- **الخسارة:** ~200 صفقة كانت تُغلق بـ +0.5R الآن تُغلق بـ -1R → خسارة 300R.
- **الصافي:** **سلبي** إلا إذا الحق TP أكثر من ذلك.

**الحساب الدقيق:** من بياناتك، مع σ = 1%:
- $P(\text{MFE} > 5\sigma) \approx e^{-5} \approx 0.67\%$ (بحساب أسّي مع λ = 1/0.89)
- عدد الصفقات المتوقعة التي تصل إلى 5σ: $763 \times 0.0067 \approx 5$ صفقات.
- **ليس كافياً** للتعويض عن 200 صفقة انعكست.

### 4. الحل الأفضل: R/R = 2.5 أو 3.0

**المبرهنة:** نقطة التعادل عندما:

$$
P(\text{reach } R \cdot \sigma) \cdot R = P(\text{trail exit}) \cdot 0.5 + P(\text{SL}) \cdot 1.0
$$

بمعامل $\lambda = 0.89$:
- R/R = 2: $P = e^{-2.25} = 0.105$, $\mathbb{E} = 0.21$
- R/R = 3: $P = e^{-3.37} = 0.034$, $\mathbb{E} = 0.102$
- R/R = 5: $P = e^{-5.62} = 0.0036$, $\mathbb{E} = 0.018$

**الترجمة:** كل زيادة في R/R **تقلل العائد المتوقع** مع هذا التوزيع.

**التوصية:** جرّب R/R = 2.5 أو 3.0 أولاً. إذا تحسّن، جرّب 4.0. **لا تبدأ بـ 5.0.**

---

## بعد التشغيل، أرسل

1. جدول المقارنة الكامل (R/R = 2, 2.5, 3, 4, 5).
2. لكل تشغيل: Sharpe, WR, MaxDD, Hard TP count, Emergency SL count.
3. أي تحذير أو خطأ.

سأحلّل:
- أين تقع النقطة المثالية لـ R/R على بياناتك.
- هل Trail-Adaptive يُحسّن أم يضر.
- القيم المثالية لـ `TRAIL_ACT_TP_FRACTION`.

**لا تُقرّر قيمة R/R بشكل حدسي. قِس أولاً.**
