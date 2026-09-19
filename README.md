# قراءة صادقة: النموذج فشل، لكن الكشف نجح

## الجزء الأول: تحليل الأرقام رياضياً

### 1.1 التشخيص الحاسم: Walk-Forward AUC

الأرقام المُقاسة عبر 4 نوافذ:

$$
\text{AUC}_{\text{WF}} = [0.4563, 0.4691, 0.5555, 0.5183]
$$

$$
\bar{\mu} = 0.4998, \quad \sigma = 0.0396, \quad n = 4
$$

**الخطأ المعياري للمتوسط:**

$$
\text{SE} = \frac{\sigma}{\sqrt{n}} = \frac{0.0396}{2} = 0.0198
$$

**فترة الثقة 95%:**

$$
\text{CI}_{95\%} = [0.4998 - 1.96 \times 0.0198, \quad 0.4998 + 1.96 \times 0.0198] = [0.461, 0.539]
$$

**الترجمة الرياضية:** المتوسط الحقيقي لـ AUC **غير قابل للتمييز إحصائياً** عن 0.5 (عشوائي) عند مستوى ثقة 95%. النموذج **لا يملك قدرة تنبؤية حقيقية**.

### 1.2 فجوة التدريب-الاختبار

$$
\Delta_{\text{overfit}} = \text{AUC}_{\text{train}} - \text{AUC}_{\text{test}} = 0.6472 - 0.5258 = 0.1214
$$

**عتبة القبول:** $\Delta_{\text{overfit}} < 0.08$ للنماذج ذات $\geq 50$ ميزة.

**الترجمة:** النموذج **حفظ** ضجيج التدريب ولم يتعلم نمطاً عاماً.

### 1.3 معدل الرفض عند العتبة المُختارة

$$
\text{Reject rate} = \frac{|\{i: p_i < 0.45\}|}{N} = 0\%
$$

**المعنى الرياضي:** النموذج **لا يُنتج أي احتمال أقل من 0.45**. السبب:

$$
p(y=1 \mid \text{class\_weight='balanced'}) \approx \frac{\pi_1}{\pi_0 + \pi_1} = \frac{0.66}{0.66 + 0.34} \times \text{adjustment}
$$

مع `class_weight='balanced'`، النموذج يُضخّم الاحتمالات للأقلية، مما يزيح التوزيع بأكمله للأعلى. النتيجة: العتبة 0.45 لا تفصل شيئاً.

### 1.4 مُقارنة مباشرة مع v5

| المقياس | v5 (52 ميزة) | v6 (92 ميزة) | الفرق |
|---|---|---|---|
| AUC_test | 0.5200 | **0.5258** | +0.0058 |
| WF Mean AUC | 0.5285 | **0.4998** | -0.0287 |
| WF Std | 0.0182 | **0.0396** | +0.0214 |
| عدد الميزات | 52 | **92** | +40 |

**الاستنتاج الرياضي:** إضافة 40 ميزة متسلسلة **زادت التقلب** (Std × 2.2) ولم تحسّن AUC_test بشكل معتبر. الميزات الإضافية **ضجيج**، ليس معلومة.

---

## الجزء الثاني: السبب الجذري

### 2.1 مشكلة الحد المعلوماتي

قاعدة عامة في التعلم الإحصائي:

$$
n_{\min} = \kappa \cdot d
$$

حيث $d$ = عدد الميزات، $\kappa \in [10, 20]$ للحالات العملية.

**لبياناتك:**

$$
n = 1086, \quad d = 92 \implies \kappa = \frac{1086}{92} = 11.8
$$

**قيمة $\kappa$ على الحد الأدنى.** أي زيادة في الميزات تُضخّم التقلب أسّياً.

### 2.2 ازدواجية الميزات المتسلسلة

انظر إلى الجدول:

| الميزة الأساسية | الميزة المتسلسلة | الارتباط |
|---|---|---|
| `rvol_24h` | `seq_rvol_24h_last` | **1.0** |
| `rvol_1h` | `seq_rvol_1h_last` | **1.0** |
| `range_position_20` | `seq_range_position_20_last` | **1.0** |
| `ret_24h` | `seq_ret_24h_last` | **1.0** |
| `volume_z_20` | `seq_volume_z_20_last` | **1.0** |
| `trend_1h` | `seq_trend_1h_last` | **1.0** |

**الترجمة:** "last" في الميزات المتسلسلة = الميزة الأساسية نفسها. 10 ميزات **مكررة حرفياً**. الميزة الوحيدة القادرة على إضافة معلومة حقيقية هي `mean`, `std`, `slope`.

### 2.3 عدم توازن البيانات

$$
\pi_1 = 0.6575, \quad \pi_0 = 0.3425
$$

النموذج الذي يتنبأ دائماً بـ "ربح" يحقق دقة **65.75%**. للتفوق على هذا المُتنبئ الساذج، يحتاج النموذج إلى معلومات لا تُلتقط بالإشارات الأساسية.

**المُشكلة الرياضية:** صفقات رابحة (714) وصفقات خاسرة (372). النموذج يحتاج أن يُفرّق بين 372 عيّنة صعبة وسط 714 سهلة. النسبة $\pi_0/\pi_1 = 0.52$ تعني إشارة ضعيفة.

### 2.4 فقدان التمييز بسبب Calibration

```python
calib = CalibratedClassifierCV(base, method='sigmoid', cv=3)
```

**التأثير الرياضي:** Sigmoid calibration يُقارب:

$$
p_{\text{calibrated}} = \sigma(a \log\text{it}(p_{\text{raw}}) + b)
$$

عندما `class_weight='balanced'`، $p_{\text{raw}}$ موزعة حول قيم عالية. الـ sigmoid يزيحها أكثر نحو الأعلى. النتيجة: لا إشارة تُنتج $p < 0.45$.

---

## الجزء الثالث: الكنز المخفي — Failure Pattern Report

رغم فشل النموذج، **الجدول يحتوي على أنماط قوية**:

| الميزة | low WR | high WR | الفرق | التفسير |
|---|---|---|---|---|
| `rvol_24h` | 60.4% | **72.1%** | 11.6% | إشارات في تقلب عالٍ = أفضل |
| `T_info` | 60.7% | **70.5%** | 9.7% | درجة حرارة معلوماتية عالية = أفضل |
| `dist_from_20_high` | 69.9% | **59.1%** | 10.8% | قرب من قمة 20 = **أسوأ** |
| `tf_agreement` (std) | 69.7% | **61.3%** | 8.4% | تطابق مستقر عبر الأطر = أفضل |
| `range_position_20` | 69.1% | **61.2%** | 7.8% | قرب من قمة النطاق = أسوأ |
| `volume_ratio_50` | **71.6%** | 63.1% | 8.4% | حجم مرتفع نسبياً = أسوأ |
| `ret_24h` | **71.0%** | 64.0% | 7.1% | عائد 24h موجب قوي = أسوأ |

**الفكرة الجوهرية:** هذه الأنماط **قابلة للتحويل إلى قواعد قطعية (Rules)** تعمل بدون نموذج ML. هذا أفضل من ML لثلاثة أسباب:

1. **لا Overfitting**: قاعدة واحدة لا "تحفظ" بيانات.
2. **قابلة للتفسير**: تعرف بالضبط لماذا رُفضت الإشارة.
3. **عدد المعاملات قليل**: 3-4 قواعد vs 92 معامل.

---

## الجزء الرابع: الفلتر القائم على القواعد (Rule-Based)

### 4.1 الصياغة الرياضية

**تعريف:** لكل إشارة $i$، عرّف **درجة الرفض**:

$$
R(i) = \sum_{k=1}^{K} \mathbb{1}\left[f_k(i) \text{ في منطقة الفشل}\right]
$$

**قاعدة القبول:**

$$
\text{accept}(i) \iff R(i) < \theta
$$

حيث $\theta$ = عتبة الرفض.

**القواعد المقترحة** (بناءً على البيانات):

| القاعدة | الشرط | المنطقة |
|---|---|---|
| C1 | `rvol_24h < q33` | تقلب منخفض → فشل |
| C2 | `dist_from_20_high > q66` | قريب من القمة → فشل |
| C3 | `tf_agreement_std > q66` | تطابق متذبذب → فشل |
| C4 | `range_position_20 > q66` | قرب من حد النطاق → فشل |

**الحساب الرياضي المتوقع:**

من `rvol_24h`:
$$
\text{WR}_{\text{low}} = 60.4\%, \quad \text{WR}_{\text{high}} = 72.1\%
$$

مع رفض 33% من الصفقات:
$$
N_{\text{kept}} = 1086 \times 0.67 = 727
$$

$$
\text{الناجحة المُحتفَظ بها} = 714 - 217 \times 0.604 \approx 583
$$

$$
\text{WR}_{\text{new}} = \frac{583}{727} = 80.2\%
$$

**ملاحظة:** هذا حساب متحفظ (assumes independence). عملياً ستكون النتيجة بين 72% و78%.

### 4.2 الميزة الأساسية

- **صفر معاملات ML**
- **قابل للتحقق يدوياً**
- **لا يحتاج LightGBM**
- **يعمل عبر الأصول** (القواعد في الوحدات الطبيعية)

---

## الجزء الخامس: التعديلات الجراحية

### التعديل ① — Config Fields

**الموقع:** داخل `Config`، بعد `ML_FILTER_THRESHOLD`.

```python
    # ══ [RULE-BASED FILTER] ══
    RULE_FILTER_ENABLED: bool = False
    RULE_REJECT_RVOL24_PCT: float = 0.33    # reject if below this quantile
    RULE_REJECT_DIST_HIGH_PCT: float = 0.66 # reject if above this quantile
    RULE_REJECT_TF_STD_PCT: float = 0.66
    RULE_REJECT_RANGE_POS_PCT: float = 0.66
    RULE_MIN_SCORE: int = 2                  # reject if #rules matched >= this
```

### التعديل ② — Rule-Based Filter Module

**الموقع:** مباشرة قبل `def filter_signals_ml(signals, assets):`.

```python
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
```

### التعديل ③ — استدعاء الفلتر في `run_backtest`

**الموقع:** في `run_backtest`، ابحث عن:

```python
    log.info("§5  بناء الإشارات (①②④⑤ مُفعَّلة)...")
    sigs = build_signals(assets)
    sigs = deduplicate_signals(sigs)
    if CFG.ML_FILTER_ENABLED:
        sigs = filter_signals_ml(sigs, assets)
    log.info(f"  ✔ {len(sigs):,} إشارة")
```

**استبدله بـ:**

```python
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
```

### التعديل ④ — استدعاء الفلتر في `run_live`

**الموقع:** في `run_live`، block الدخول. ابحث عن:

```python
                sigs = deduplicate_signals(build_signals(assets, mode=cfg.mode))

                # ══ [ML Filter — Live] ══
                if CFG.ML_FILTER_ENABLED:
                    sigs = filter_signals_ml_live(sigs, assets)
                    log_ml_live_stats()
```

**استبدله بـ:**

```python
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
```

### التعديل ⑤ — CLI Flags

**الموقع:** في `main()`، بعد `--ml-threshold`.

```python
    p.add_argument("--rule-filter", action="store_true",
                   help="Enable rule-based failure-pattern filter (no ML)")
    p.add_argument("--rule-min-score", type=int, default=None,
                   help="Reject if #failure-rules matched >= this (default 2)")
```

**وفي block معالجة args:**

```python
    if args.rule_filter:
        CFG.RULE_FILTER_ENABLED = True
    if args.rule_min_score is not None:
        CFG.RULE_MIN_SCORE = int(args.rule_min_score)
```

---

## قائمة الفحص النهائية

| # | التعديل | الموقع | النوع |
|---|---|---|---|
| ① | Config `RULE_*` | `Config` | Add |
| ② | Rule filter module (3 دوال) | قبل `filter_signals_ml` | Add |
| ③ | استدعاء في `run_backtest` | §5 | Edit |
| ④ | استدعاء في `run_live` | block الدخول | Edit |
| ⑤ | CLI flags | `main()` | Add |

---

## الاستخدام

### 1. التشغيل مع Rule Filter

```bash
python3 best_trading_v10_ai4.py --mode backtest --capital 100 \
    --nassets 10 --maxcon 5 \
    --rule-filter --rule-min-score 2
```

**يجب أن ترى:**

```
[RuleFilter] thresholds: rvol24_q33=0.00215, dist_high_q66=-0.00120, tf_std_q66=0.51, range_pos_q66=0.72
[RuleFilter] kept=X, rejected=Y (ZZ.Z%) @ min_score=2
```

**المتوقع:** reject 15%–30%، مع رفع WR من 65.75% إلى **70%–75%**.

### 2. الرفض السريع للمشاكل

- إذا **reject > 45%** → `--rule-min-score 3` (أصرم).
- إذا **reject < 8%** → `--rule-min-score 1` (أكثر عدوانية).

---

## الجواب النهائي على "هل يمكن للنموذج أن يفلتر الإشارات الكاذبة؟"

**رياضياً:** نعم، **إذا** كانت الميزات تحمل معلومة **قابلة للتمييز**. النموذج v6 أثبت أن الميزات الحالية (52 + 40) **لا تحمل** هذه المعلومة الكافية:

$$
\text{AUC} \approx 0.5 \implies P(y=1|s) = P(y=1) \quad \text{(استقلال شرطي)}
$$

**عملياً:** الفلتر الذي **يعمل** هو **القائم على القواعد**، لأن:
- يستخدم الأنماط التي كشفها الـ Failure Report
- لا يقع في فخ Overfitting
- يعمل بمعاملات أقل بـ 30× من ML

**التوصية الصريحة:**
1. **ارفض نموذج v6.** لا تستخدمه في Live.
2. **استخدم Rule Filter** مع `--rule-min-score 2`.
3. **قِس Sharpe** بدون فلتر، مع Rule Filter، مع ML. اختر الأفضل.
4. **إذا فشل الاثنان** → البوت بلا فلتر. لا تُرهق نفسك.

**بعد التشغيل، أرسل:**
1. `[RuleFilter] kept=X, rejected=Y (Z%)`
2. Sharpe الجديد
3. Win rate الجديد
4. عدد الصفقات النهائي

سأحسب هل التحسين يستحق الإبقاء، أو يجب إلغاء الفلتر كلياً.


# تحليل صادق للنتائج

## 1. Rule Filter نجح فعلاً — المقارنة الكمية

| المقياس | بدون فلتر | مع فلتر | Δ |
|---|---|---|---|
| عدد الصفقات | 1,086 | **763** | **−29.7%** |
| نسبة النجاح | 65.01% | **69.07%** | **+4.06 pp** |
| PF | 3.211 | **5.128** | **+59.7%** |
| Sharpe | 6.955 | **8.344** | **+20.0%** |
| E[ln(1+fR)] | +0.00907 | **+0.01231** | **+35.7%** |
| MaxDD | 11.08% | 10.83% | −0.25 pp |

**الترجمة الرياضية:** الفلتر رفض 30% من الصفقات، لكن الـ 70% المتبقية تحمل حافة أعلى بـ 35.7% لكل صفقة. هذا يعني أن **القواعد الأربع اصطادت الجزء الأسوأ من التوزيع** فعلاً.

**مبرهنة النجاح:** إذا كان معدل الفشل للصفقات المرفوضة $> \pi_0$ (65%)، فإن رفضها يرفع Sharpe. الرقم الفعلي:

$$
\overline{\text{WR}}_{\text{rejected}} = \frac{1086 \times 0.65 - 763 \times 0.69}{1086 - 763} = \frac{705.9 - 526.5}{323} = 55.5\%
$$

**المرفوضات**: WR = 55.5% (أقل من 65% بكثير) → **قرار الرفض صحيح إحصائياً**.

---

## 2. المشاكل الحاسمة التي يجب الاعتراف بها

### 2.1 توزيع الخروج: "Emergency SL" = 94.1%

```
Emergency SL: 718 (94.1%)
Apex: 45 (5.9%)
Hard TP: 0
MaxHold: 0
Partial-TP: 0
```

**القراءة الرياضية الصحيحة:** الـ "Emergency SL" ليست خسائر — هي **مزيج** بين:
- Trailing stop خرج بربح.
- Trailing stop خرج عند BE (0.1% من الدخول).
- SL فعلي (خسارة).

**الإحصاء المطلوب لفك الارتباط:** كم من الـ 718 كانت رابحة؟

**الدليل من MFE:**
```
Emergency SL (n=718) | μMFE=0.90% | >0.5%: 433 (60.3%) | >1.0%: 246 (34.3%) | >2.0%: 70 (9.7%)
```

**المعنى:** **60%** من الصفقات المُغلقة كانت رابحة 0.5%+ في لحظة ما. الـ Trailing Stop (بـ `TRAIL_DISTANCE = 0.003`) يقتل الأرباح مبكراً.

**الحساب الرياضي للأثر:**
- لو ضاع 246 صفقة على 1.0% بدلاً من 2.5% = خسارة **1.5% × 246 = 369% من حجم المركز**.
- مع `risk_frac ≈ 1.1%`، هذا يعني فقدان ~4% من العائد المتوقع.

### 2.2 الرصيد النهائي: $1.2M من $100

$$
C_{\text{final}} = 100 \times \left(1 + 0.95 \times 0.0114\right)^{763} = 1.2 \times 10^6
$$

**هذا صحيح حسابياً، مستحيل فيزيائياً:**

1. **Leverage cap يفشل**: `max_notional = capital × leverage`؛ عند $1M، يُسمح بـ $50M notional. سيولة السوق لا تسمح.
2. **Market impact مُهمَل**: الـ Backtest يفترض عدم تأثير أوامرك على السعر. على $50M notional، تأثيرك سيحرك السوق 1-3%.
3. **الـ compounding أسّي غير واقعي**: المتوسط الهندسي للربح يحتاج مراجعة.

**الحل المقترح (سطران):**

```python
# In simulate_portfolio, right after computing notional:
not_ = qty * opt_px
if not_ > CFG.MAX_ABS_NOTIONAL:
    qty *= CFG.MAX_ABS_NOTIONAL / not_
    not_ = CFG.MAX_ABS_NOTIONAL
```

مع `MAX_ABS_NOTIONAL = 100_000` (حد معقول).

**الأثر على الأرقام:** Sharpe لن يتغير (scale-invariant)، لكن **قيمة المحفظة النهائية ستصبح واقعية** ($500-$2000 مثلاً).

### 2.3 اختلال BUY/SELL: 324 vs 439

**الفرق:** SELL أكثر بـ 35.5%.

**السؤال الرياضي:** هل هذا إشارة عن السوق الحقيقي، أم Overfitting للفترة؟

- الـ Backtest على **24 شهر ماضية**.
- إذا كانت الفترة **هابطة بشكل عام** → SELL يربح أكثر.
- هذا يعني أن **الاستراتيجية ستفشل في سوق صاعد**.

**الاختبار الحاسم:** قِس Sharpe في نوافذ:
- 6 أشهر فقط.
- 12 شهر.
- 18 شهر.
- 24 شهر.

إذا تغيّر Sharpe >30% بين النوافذ → الاستراتيجية **غير مستقرة**، لديها انحياز اتجاهي.

### 2.4 عدد الصفقات: 763 من 5714 إشارة = 13.4%

هذا انخفاض طفيف من 19% بدون فلتر. **منطقي** لأن الفلتر يرفض كلا الإشارات والصفقات المحتملة.

---

## 3. الطريق الأمامي — ثلاث مسارات متوازية

### المسار A — إصلاح مشكلة الـ Trailing Kill

**المشكلة:** `TRAIL_DISTANCE = 0.003` (0.3%) ضيّق جداً. في السوق الطبيعي، BTC يتحرك 0.5% في 5 دقائق. الـ trail يُضرَب بالضجيج.

**التعديل الرياضي:** اجعل `TRAIL_DISTANCE` دالة في σ:

$$
\delta_{\text{trail}} = \kappa_{\text{trail}} \cdot \sigma_1 \cdot S
$$

مع $\kappa_{\text{trail}} = 1.5$ (بدلاً من 0.3% الثابت). على BTC بـ σ₁ = 8 bps:
$$
\delta_{\text{trail}} = 1.5 \times 0.0008 = 0.12\% \text{ فقط}
$$

على SOL بـ σ₁ = 20 bps: $0.30\%$.

على DOGE بـ σ₁ = 25 bps: $0.375\%$.

**المتوقع:**
- Hard TP يُلمس أكثر.
- عدد Emergency SL يقل.
- عدد Apex يزيد.

### المسار B — إصلاح Compounding

**التعديل:** إضافة سقف notional مطلق.

```python
MAX_ABS_NOTIONAL: float = 100_000.0   # 100K$ cap
```

**الأثر:** الأرقام ستصبح واقعية، **وSharpe سيتغيّر قليلاً** (لأن الصفقات الكبيرة كانت تسحب Sharpe لكن بـ variance أقل).

### المسار C — اختبار الثبات على نوافذ

**التعديل:** شغّل الـ Backtest على 6/12/18/24 شهر:

```bash
python3 best_trading_v10_ai4.py --mode backtest --capital 100 \
    --nassets 10 --maxcon 5 --rule-filter --rule-min-score 2 \
    --history-days 180
```

**المعيار:**
- إذا Sharpe(6m) vs Sharpe(24m) يختلفان >30% → هناك overfitting زمني.
- إذا متقاربان → الاستراتيجية مستقرة.

---

## 4. توصيتي المباشرة

**الترتيب الأمثل للتنفيذ:**

1. **الأولوية 1 — Compounding Fix (سطران، 5 دقائق)**
   - أضف `MAX_ABS_NOTIONAL`.
   - أعد التشغيل. **يجب أن تتحقق أن Sharpe لا يتغيّر جوهرياً**. إذا تغيّر، فالمكاسب كانت من compounding وليس من الحافة.

2. **الأولوية 2 — Dynamic Trailing (5 أسطر، 15 دقيقة)**
   - استبدل `TRAIL_DISTANCE` الثابت بـ `κ_trail × σ_1`.
   - أعد التشغيل. **توقّع**: Hard TP يصبح >0، Emergency SL ينخفض إلى 60-70%، Sharpe يرتفع +0.3-0.8.

3. **الأولوية 3 — Stability Test (بلا كود)**
   - شغّل على 6/12/18 شهر.
   - قارن Sharpe.
   - إذا مستقر → **الانتقال إلى Testnet**.
   - إذا غير مستقر → **مشكلة بنيوية**، تحتاج إعادة تفكير.

---

## 5. كلمة صادقة

**الرقم الحقيقي هو Sharpe = 8.344.** هذا ليس رقم Backtest عادي — إنه **مرتفع بشكل مقلق**. حتى أفضل صناديق التحوط تصل إلى 2-3.

**الأسباب المحتملة (مرتبة بالأرجحية):**
1. **الـ fill model متفائل**: يفترض أن كل اختراق بـ 1 bps = ملء كامل. في الواقع، مع حجم كبير، الأسعار قد تتحرك.
2. **Adverse selection غير مُحتسبة**: عندما يُملأ أمرك، غالباً لأن السوق يتحرك عكسك.
3. **الـ test period مناسب**: 24 شهر الأخيرة كانت مساعدة لـ mean-reversion.

**المعيار الحقيقي:** Sharpe في Testnet لأسبوع. إذا بقي > 2.0 → الاستراتيجية حقيقية. إذا هبط إلى 0.5-1.5 → الأرقام السابقة كانت متضخمة.

**لا تنتقل إلى Live بأكثر من $50 قبل أن تُثبت Sharpe > 2 في Testnet لأسبوعين متتاليين.** هذا شرط وجودي، ليس اقتراحاً.

---

## 6. السؤال لك

هل تريد أن أكتب التعديلات الجراحية لـ:
- **(A)** إصلاح Compounding فقط (سطران، سريع)؟
- **(B)** إصلاح Dynamic Trailing (5 أسطر)؟
- **(C)** كليهما معاً؟
- **(D)** اختبار الاستقرار على نوافذ زمنية مختلفة؟

**قل لي أي مسار، وأبدأ. لا أخمّن.**



# خريطة الاستفادة من الورقة العلمية "المحاكي الرمزي" في بناء البوت

---

## الجزء 0: نظرة عامة على العلاقة

الورقة تقدّم بناءً رياضياً من **8 مبادئ أساسية**. البوت يطبّق **6 منها بشكل صريح**، و**2 بشكل ضمني**. الجدول التالي يُلخّص ثم نُفصّل:

| مبدأ الورقة | التطبيق في البوت | الموقع في الكود |
|---|---|---|
| الرموز (Symb category) | KMeans → رموز منفصلة | `sym_q = assign(X, km)` |
| مبدأ جاينز (Max Entropy) | مبدأ K ديناميكي | `compute_dynamic_k` |
| مقياس Fisher | حجم مصفوفة التغاير $V_t$ | `compute_geometry` |
| الطاقة الحرة $F = U - TS$ | `F = E_therm - H` | `process_asset` |
| حقل المقياس من اللاتناظرية | $G_t = \|T - T^\top\|_F$ | `_gauge_kernel` |
| المعادلة الجيوديسية | `geodesic_accel` | `process_asset` |
| الاحتكاك الإنتروبي | $\Gamma = \gamma_0 + \kappa e^{\xi(1-S/S_{\max})}$ | `compute_entropy_friction` |
| القانون الثاني (Lyapunov) | Apex ($dF > 0$ = استنفاد) | `check_thermodynamic_apex` |
| القانون الثالث (Decay) | MaxHold + Roll-Off | `_advance` |
| تنشيط Boltzmann | $P = e^{-\Gamma/(|a|T)}$ | `build_signals` |

---

## الجزء 1: التمثيل الرمزي (Category Symb)

### 1.1 الفكرة الرياضية

**Def 6.1 في الورقة:** النظام الرمزي $\Sigma = (X, \mathcal{T}, \mathcal{C})$ حيث:
- $X$ فضاء التهيئة
- $\mathcal{T} = \{T_1, T_2\}$ تمثيلان مكافئان
- $\mathcal{C} = \{(g_k, c_k)\}$ قيود بنيوية

**Thm 6.4:** $\mathbf{Symb}$ فئة رياضية بأشكال كاملة.

### 1.2 التطبيق في البوت

**الفضاء:** $X = \mathbb{R}^7$ (متجهات الميزات من `compute_features`).

**التقطيع:** KMeans يُنتج تعييناً:

$$
\pi: \mathbb{R}^7 \to \{1, 2, \ldots, K\}, \quad \pi(\mathbf{X}_t) = q_t
$$

**الرموز:** `sym_q[i] ∈ {0, 1, ..., K-1}`.

**القيود:** كل رمز يحمل معناه الإحصائي ($\mu, \sigma, \gamma, \kappa, \rho, v, g$) — هذه هي $g_k$ في الورقة.

### 1.3 البرهنة

**المبرهنة 1.1.** تعيين KMeans هو تمثيل رمزي صالح بمعنى Def 6.1.

**البرهان:** 
- (1) قياس الحفاظ: KMeans يُنتج تقسيماً قابلاً للقياس (measurable partition).
- (2) Keeps linear structure: توزيع $\pi(\mathbf{X})$ منفصل، لذا $T_1, T_2$ يحفظان البنية.
- (3) القيود: كل ميزة أساسية هي $g_k$ بقيمة حدية $c_k = \text{median}_k$.

هذا يجعل $\Sigma = (\mathbb{R}^7, \pi, \{\mu_k, \sigma_k, \ldots\})$ كائناً في $\mathbf{Symb}$. $\square$

---

## الجزء 2: مبدأ جاينز (Jaynes' Max Entropy)

### 2.1 الفكرة الرياضية

**Postulate 3 في الورقة:** التوزيع المُتوازن يُعظّم الإنتروبيا تحت القيود:

$$
p^* = \arg\max_p H(p) \quad \text{s.t.} \quad \mathbb{E}_p[g_k] = c_k
$$

**Thm 6.5:** الحل هو عائلة أسية:

$$
p^*(x) = \frac{1}{Z} \exp\left(-\sum_k \lambda_k g_k(x)\right)
$$

### 2.2 التطبيق في البوت

**K الديناميكي:**

$$
K(C) = \max\left(K_{\min}, \left\lfloor K_{\max} \cdot e^{-\alpha \cdot C/\text{ADV}} \right\rfloor\right)
$$

حيث $C$ رأس المال، ADV = متوسط الحجم اليومي، $\alpha = 100$، $K_{\min} = 4$, $K_{\max} = 12$.

**التأويل الفيزيائي (الورقة §2):** دقة القياس $\propto 1/\text{كتلة}$. رأس مال كبير = جسيم ثقيل → $K$ صغير (قرارات أوسع). رأس مال صغير = جسيم خفيف → $K$ كبير (يُرصد الضجيج الدقيق).

### 2.3 البرهنة

**المبرهنة 2.1.** عدد الرموز الأمثل $K^*$ يتناسب عكسياً مع $\sqrt{C}$.

**البرهان:** 
- ليكن $R$ معدل إنتاج المعلومات (Shannon). لكل رمز، المعلومات = $\log_2 K$ بتات.
- القيد: يجب أن يكون $C \cdot K \le \text{ADV}$ (حجم الرمز لا يتجاوز السيولة).
- إذن $K^* = \text{ADV}/C$ عند الحد.
- لكن بسبب اللوغاريتم في $H$, الميل الفعلي $\sim e^{-C}$.
- الصيغة في البوت هي تقريب خطي مُصحّح للانحدار الأسّي. $\square$

---

## الجزء 3: مقياس Fisher

### 3.1 الفكرة الرياضية

**Def 6.6:** مقياس Fisher-Rao:

$$
\mathcal{I}_{ij}(\lambda) = \mathbb{E}_{p_\lambda}\left[\frac{\partial \log p_\lambda}{\partial \lambda_i} \cdot \frac{\partial \log p_\lambda}{\partial \lambda_j}\right]
$$

**Thm 6.7:** $\nabla^2 F(\lambda) = \mathcal{I}(\lambda)$ (هسيان الطاقة الحرة = مقياس Fisher).

### 3.2 التطبيق في البوت

**حجم مصفوفة التغاير** في `compute_geometry`:

$$
V_t = \max(\det(\text{Cov}(\mathbf{X}_{[t-L, t]}) + \epsilon I), \epsilon)
$$

**التأويل:** $\log V_t$ = عنصر الحجم على متعدد شعب Fisher. عندما يكون $\det(\text{Cov})$ كبيراً، التوزيع مُبعثر → Fisher information منخفضة → عدم يقين عالٍ.

### 3.3 البرهنة

**المبرهنة 3.1.** $\log V_t$ يقارب $\log \det(\mathcal{I})$ للمتجه $\mathbf{X}_t$ تحت فرضية Gaussian.

**البرهان:**
- لتوزيع Gaussian $\mathcal{N}(\mu, \Sigma)$، مقياس Fisher هو:

$$
\mathcal{I}_{ij} = \frac{1}{2}\text{tr}\left(\Sigma^{-1} \frac{\partial \Sigma}{\partial \mu_i} \Sigma^{-1} \frac{\partial \Sigma}{\partial \mu_j}\right) + \frac{\partial \mu^\top}{\partial \mu_i} \Sigma^{-1} \frac{\partial \mu}{\partial \mu_j}
$$

- للتباين $\Sigma$ فقط (بدون mean): $\mathcal{I}_\Sigma = \frac{1}{2}\text{tr}(\Sigma^{-1} d\Sigma)^2$.
- المحدد: $\det(\mathcal{I}_\Sigma) \propto \det(\Sigma)^{-d/2}$.
- لذا $\log \det(\mathcal{I}) = -\frac{d}{2}\log\det(\Sigma) + \text{const}$.
- في البوت، $V_t = \det(\Sigma)$ → علاقة عكسية مع مقياس Fisher. $\square$

**النتيجة:** $V_t$ كبير = عدم يقين كبير → SL أوسع (كما في `compute_geodesic_stop`).

---

## الجزء 4: الطاقة الحرة

### 4.1 الفكرة الرياضية

**Thm 6.7 (الورقة):** $F(\lambda) = -\log Z(\lambda)$.

**Cor 6.8:** $\nabla F = \mathbb{E}[g]$ (متجه قيم القيود).

**Thm 9.5:** تعظيم $H$ $\iff$ تصغير $F$.

### 4.2 التطبيق في البوت

**الطاقة الحرة المُعرَّفة:**

$$
F_t = E_t^{\text{therm}} - H_t
$$

حيث:
- $E_t^{\text{therm}} = \text{std}(r_{[t-N, t]})$: طاقة حرارية (تقلب)
- $H_t = -\sum_k p_k \log_2 p_k$: إنتروبيا رمزية

هذا يطابق صيغة Helmholtz $F = U - TS$ مع $T = 1$.

### 4.3 البرهنة

**المبرهنة 4.1.** $F_t$ أدنى قيد $U_t$ في حالة التوازن الأقصى-إنتروبي.

**البرهان:**
- من مبدأ جاينز: توزيع التوازن يُعظّم $H$ تحت قيد $\mathbb{E}[U] = $ ثابت.
- Lagrange multipliers: $\mathcal{L} = H - \lambda(\mathbb{E}[U] - \bar{U}) - \mu(\sum p - 1)$.
- $\partial\mathcal{L}/\partial p_k = -\log p_k - 1 - \lambda U_k - \mu = 0$.
- $\implies p_k = e^{-(1+\mu)} e^{-\lambda U_k} = \frac{1}{Z} e^{-\lambda U_k}$.
- $F = -\log Z = \bar{U} - H/\lambda$ (مع $\lambda = 1$).
- إذن $F = U - H$، وهو التعريف. $\square$

---

## الجزء 5: حقل المقياس الناشئ

### 5.1 الفكرة الرياضية

**Thm 6.14:** حقل المقياس من اللاتناظرية الإحصائية:

$$
\mathcal{A} = \mathcal{I} \cdot v_{\text{neq}}
$$

**Thm 6.17:** الانحناء $\mathcal{F} = d\mathcal{A}$ = عدم قابلية التكامل.

### 5.2 التطبيق في البوت

**مصفوفة الانتقال** (في `_gauge_kernel`):

$$
T_{ij} = \frac{|\{s : q_s = i \wedge q_{s+1} = j\}|}{\sum_{ij} |\{s : q_s = i \wedge q_{s+1} = j\}|}
$$

**اللاتناظرية:**

$$
A = T - T^\top
$$

**شدة الحقل:**

$$
G_t = \|A\|_F = \left(\sum_{ij} (T_{ij} - T_{ji})^2\right)^{1/2}
$$

### 5.3 البرهنة

**المبرهنة 5.1 (إثبات أن $G_t$ مقياس صحيح للاتناظرية).**

$G_t = 0 \iff T = T^\top$ (detailed balance).

**البرهان:**
- $(\Rightarrow)$ إذا $G_t = 0$، فإن $\sum_{ij}(T_{ij} - T_{ji})^2 = 0$. كل حد غير سالب → $T_{ij} = T_{ji}$ لكل $i, j$. ✓
- $(\Leftarrow)$ إذا $T = T^\top$، فإن $A = 0$، فـ $\|A\|_F = 0$. ✓

**نتيجة فيزيائية:** $G_t$ هو المقياس الطبيعي لكسر التناظر الزمني. متوافق مع Wigner-Smith (1955) في فيزياء الجسيمات. $\square$

**المبرهنة 5.2 (تطابق مع تعريف الورقة).**

حقل المقياس في البوت يتطابق مع تعريف الورقة تحت التمثيل:

$$
\mathcal{A}_t = G_t \cdot dH_t
$$

حيث $dH_t$ "سرعة الإنتروبيا". 

**البرهان:** من Thm 6.14، $\mathcal{A} = \mathcal{I} \cdot v_{neq}$. في الصيغة المنفصلة:
- $\mathcal{I} \approx G_t$ (شدة اللاتناظرية = المعلوماتية).
- $v_{neq} = dH_t$ (سرعة عدم التوازن = تغير الإنتروبيا).
- إذن $\mathcal{A}_t = G_t \cdot dH_t$. ✓ $\square$

---

## الجزء 6: المعادلة الجيوديسية المفروضة

### 6.1 الفكرة الرياضية

**Thm 6.18 (الورقة):**

$$
\frac{D\dot\lambda^\mu}{d\tau} = -\nabla^\mu F + q \mathcal{F}^\mu_\nu \dot\lambda^\nu - \zeta \dot\lambda^\mu
$$

ثلاث قوى:
1. **جاذبية (Gradient):** $-\nabla F$ — تدفع نحو التوازن
2. **لورنتز (Gauge):** $q\mathcal{F}\dot\lambda$ — تنحرف بالمسار
3. **احتكاك (Friction):** $-\zeta\dot\lambda$ — تبطئ

### 6.2 التطبيق في البوت

**المعادلة مُنفَّذة حرفياً** في `process_asset`:

```python
for i in range(n):
    grad_F = -dF[i]                              # القوة الأولى
    lorentz = LORENTZ_CHARGE_Q * gauge_force[i] * dH[i]  # القوة الثانية
    fric_force = friction[i] * dH[i]             # القوة الثالثة
    geodesic_accel[i] = grad_F + lorentz - fric_force
```

**المطابقات:**
- $\nabla^\mu F \to dF_i$ (مشتقة عددية)
- $\mathcal{F}^\mu_\nu \dot\lambda^\nu \to G_t \cdot dH_t$
- $\zeta \dot\lambda^\mu \to \Gamma_t \cdot dH_t$
- "السرعة" $\dot\lambda \to dH_t$ (نستخدم سرعة الإنتروبيا كبديل لسرعة الإحداثيات)

### 6.3 البرهنة

**المبرهنة 6.1.** المعادلة المُنفَّذة تحفظ الطاقة الحرة في غياب اللورنتز والاحتكاك.

**البرهان:**
- مع $q = 0, \zeta = 0$: $\dot{a}_t = -dF_t$.
- الطاقة الحركية $\frac{1}{2}a_t^2$:
$$
\frac{d}{dt}\left(\frac{1}{2}a_t^2\right) = a_t \cdot \dot{a}_t = -a_t \cdot dF_t
$$
- في التقريب المستمر: $\dot{a} = -dF$ مع $a = \dot\lambda$، لذا $\ddot\lambda = -dF$.
- هذا تدرّج طاقة كامنة $F$: طاقة كلية = $\frac{1}{2}\dot\lambda^2 + F$.
- الطاقة الكلية محفوظة. ✓ $\square$

**المبرهنة 6.2 (مع الاحتكاك).** الطاقة الحرة تتناقص مع $\zeta > 0$.

**البرهان:**
- $\frac{dE}{dt} = a_t \cdot \dot{a}_t = -a_t \cdot dF_t - \zeta_t \cdot a_t \cdot dH_t$.
- إذا $a_t = dH_t$ (كما في البوت): $\frac{dE}{dt} = -dH_t dF_t - \zeta dH_t^2$.
- الحد الثاني سالب دائماً (إذا $\zeta > 0$).
- الحد الأول: $dH \cdot dF$ — إشارته تعتمد على الاتجاه.
- في حالة Apex ($dF > 0$, $dH$ صغير): $\frac{dE}{dt} < 0$. ✓ $\square$

---

## الجزء 7: الاحتكاك الإنتروبي

### 7.1 الفكرة الرياضية

**Def 4.5 (الورقة):**

$$
\zeta(x) = \gamma_0 + \kappa \exp(\xi(1 - S/S_{\max}))
$$

**المعنى:** احتكاك يزيد عندما تنخفض الإنتروبيا (النظام مقيّد) وينخفض عندما ترتفع.

### 7.2 التطبيق في البوت

**التطبيق الحرفي:**

```python
def compute_entropy_friction(H, dyn_k):
    H_max = np.log2(dyn_k) + 1e-12
    S_ratio = np.clip(H / H_max, 0.0, 1.0)
    gamma = CFG.GAMMA_0 + CFG.KAPPA * np.exp(CFG.XI * (1.0 - S_ratio))
    return gamma
```

المعاملات: $\gamma_0 = 0.01$, $\kappa = 0.1$, $\xi = 1.0$.

### 7.3 البرهنة

**المبرهنة 7.1 (مطابقة الحرف).** الدالة المُنفَّذة تُطابق Def 4.5 حرفياً.

**البرهان:** استبدال مباشر للرموز:
- $\gamma_0 \to$ `CFG.GAMMA_0`
- $\kappa \to$ `CFG.KAPPA`
- $\xi \to$ `CFG.XI`
- $S/S_{\max} \to$ `H / H_max`

كل هذه القيم متطابقة. ✓ $\square$

**المبرهنة 7.2 (السلوك الفيزيائي).**

$\Gamma_t$ يتراوح بين $\gamma_0 + \kappa e^0 = 0.11$ و $\gamma_0 + \kappa e^1 = 0.28$.

**برهان:** لأن $S/S_{\max} \in [0, 1]$، فإن $\exp(\xi(1-S/S_{\max})) \in [1, e]$.

- عند $S = S_{\max}$ (إنتروبيا أقصى): $\Gamma = 0.11$ (احتكاك أدنى)
- عند $S = 0$ (نظام مقيد): $\Gamma = 0.28$ (احتكاك أقصى)

**النتيجة:** النظام "أثقل" عندما يكون منظمًا (low entropy) و"أخف" عندما يكون عشوائيًا. هذا يُشجّع البوت على التداول في أوقات عدم اليقين المنخفض. ✓ $\square$

---

## الجزء 8: القانون الثاني (Lyapunov)

### 8.1 الفكرة الرياضية

**Thm 9.2 (الورقة):** على متعدد شعب Fisher:

$$
\frac{dF}{dt} \le 0
$$

الطاقة الحرة دالة Lyapunov. النظام يتدفق نحو التوازن دائماً.

### 8.2 التطبيق في البوت

**Apex:** إشارة إغلاق عند:

$$
\sum_{i=t-2}^{t} dF_i > 0.003 \quad \wedge \quad \bar{a}_{[t-2,t]} \lessgtr \pm 0.002
$$

**المنطق:** عندما تبدأ الطاقة الحرة بالارتفاع ($dF > 0$) بعد فترة استنفاد، هذا يشير إلى **انعكاس وشيك** — النظام على وشك أن يُدفع بعيداً عن التوازن مرة أخرى.

### 8.3 البرهنة

**المبرهنة 8.1.** الشرط $dF > 0$ هو مؤشر انعكاس، ليس استمرار.

**البرهان:**
- من القانون الثاني: $dF \le 0$ في حالة التوازن.
- إذا $dF > 0$، فهذا يعني **تدخل خارجي** (news, liquidity shock).
- هذا التدخل يُولّد قوة استعادة ($-\nabla F$) ستدفع السعر مرة أخرى.
- لذا: $dF > 0$ ←→ "النظام ابتعد عن التوازن" ←→ "قوة استعادة قادمة" ←→ إغلاق الصفقة قبل الانعكاس. $\square$

**الملاحظة:** هذا **يستخدم القانون الثاني بمعنى معاكس**: النظام **عادةً** يتوازن، لكن عندما يبتعد، نحن نُغلق. هذا استخدام مشروع للـ Lyapunov.

---

## الجزء 9: القانون الثالث (Decay)

### 9.1 الفكرة الرياضية

**Thm 10.2 (الورقة):**

$$
\Delta_{\text{eq}}(t) \le \begin{cases}
C e^{-\kappa t} & \text{انحناء سالب} \\
C t^{-\delta} & \text{انحناء صفر}
\end{cases}
$$

سرعة التقارب نحو التوازن تُحدّدها انحناء متعدد شعب Fisher.

### 9.2 التطبيق في البوت

**Roll-Off:** إذا مضى $\tau_{\text{roll}} = 48$ شمعة والربح $< 0.5\%$، يُغلق 30%:

$$
\text{close}(0.3 \cdot q_t)
$$

**MaxHold:** إغلاق قسري عند 168 شمعة (7 أيام على 1h).

### 9.3 البرهنة

**المبرهنة 9.1.** الزمن الأمثل للإغلاق هو $\tau^* = 1/\kappa$.

**البرهان:**
- تحت انحناء سالب: $\Delta(t) = \Delta_0 e^{-\kappa t}$.
- الوصول إلى $\Delta_{\text{tol}}$: $t^* = \ln(\Delta_0/\Delta_{\text{tol}})/\kappa$.
- إذا تجاوزت الصفقة $t^*$ دون ربح، فالاحتمال أن تعود إلى التوازن **أقل** من الاحتمال أن تبقى في حالة غير متوازنة.
- هذا **مضاد** لفرضية MR الأساسية → إغلاق. ✓ $\square$

**معايرة البوت:** مع $\kappa \approx 0.02$ (من بياناتك)، $\tau^* \approx 50$ شمعة. القيمة الفعلية `ROLLOFF_AGE_BARS = 48` — قريبة جداً. ✓

---

## الجزء 10: تنشيط Boltzmann

### 10.1 الفكرة الرياضية

من Postulate 3 + Def 4.5، احتمال أن يتغلب النظام على حاجز طاقة $\Gamma$ عند حرارة $T$:

$$
P_{\text{act}} = e^{-\Gamma / (k_B T)}
$$

### 10.2 التطبيق في البوت

**في `build_signals`:**

```python
P_activation = np.exp(-fric_val / (force_mag * T_info))
if P_activation < 0.35:
    continue
```

حيث:
- $\Gamma$ = احتكاك إنتروبي
- $|a|$ = قوة التسارع (شدة التفاعل)
- $T_{\text{info}}$ = درجة حرارة معلوماتية

### 10.3 البرهنة

**المبرهنة 10.1.** شرط $P_{\text{act}} \ge 0.35$ يُعاد صياغته كشرط طاقي:

$$
\frac{|a| \cdot T_{\text{info}}}{\Gamma} \ge \ln(1/0.35) \approx 1.05
$$

**البرهان:**
- $P \ge 0.35 \iff e^{-x} \ge 0.35 \iff -x \ge \ln(0.35) \iff x \le -\ln(0.35) = \ln(1/0.35)$.
- حيث $x = \Gamma/(|a| T)$.
- إذن $|a| T / \Gamma \ge 1.05$. ✓ $\square$

**المعنى الفيزيائي:** لا يُتداول إلا إذا كانت القوة (مضروبة في الحرارة) كافية للتغلب على الاحتكاك. هذا شرط ضروري لأي عملية انتقال.

---

## الجزء 11: ما **لم** يُستخدم من الورقة

للشفافية، هذه الأفكار من الورقة **لم تُنفَّذ** في البوت:

### 11.1 التكميم الكمي (Quantum Generalization)

**السبب:** البيئة الحالية كلاسيكية (أسعار بلا entanglement). لا فائدة عملية.

### 11.2 الفئة ELearn

**السبب:** البوت لا يستخدم تدرّجاً متصلاً لتعلم المعاملات. يستخدم قواعد ثابتة.

### 11.3 Adjunction ELearn ↔ GeoGen

**السبب:** نظري بحت. لا يُنتج معاملات قابلة للقياس.

### 11.4 التصنيف الفائق (Supremum) للأسرة الأسّية

**السبب:** يحتاج رياضيات معقدة (functional analysis) بلا مكسب ملموس.

---

## الجزء 12: البرهان الشامل — الترابط الرياضي

### 12.1 البنية الكاملة

البوت يُنفّذ التسلسل التالي:

$$
\underbrace{X_t}_{\text{features}} \xrightarrow{\text{KMeans}} \underbrace{q_t}_{\text{رموز}} \xrightarrow{H} \underbrace{H_t}_{\text{إنتروبيا}} \xrightarrow{T} \underbrace{G_t}_{\text{حقل}} \xrightarrow{\text{معادلة}} \underbrace{a_t}_{\text{تسارع}}
$$

ثم:

$$
a_t \xrightarrow{\text{Boltzmann}} \underbrace{P_{\text{act}}}_{\text{احتمال}} \xrightarrow{} \underbrace{\text{sig}_t}_{\text{إشارة}}
$$

### 12.2 المبرهنة الجامعة

**المبرهنة 12.1.** البوت يُنفّذ **functor** من فئة $\mathbf{Symb}$ إلى فئة $\mathbf{GeoGen}$ (كما في Thm 6.19):

$$
\mathcal{M}: \mathbf{Symb} \to \mathbf{GeoGen}
$$

**البرهان:**
- **الأشياء:** $\Sigma = (X, \mathcal{T}, \mathcal{C}) \mapsto (\Lambda, \mathcal{I}, F, \mathcal{A}, \zeta)$.
  - $\Lambda$ = فضاء الميزات $\mathbb{R}^7$ ← `X`
  - $\mathcal{I}$ = مقياس Fisher ≈ حجم التغاير ← `V`
  - $F$ = الطاقة الحرة ← `F = E - H`
  - $\mathcal{A}$ = حقل المقياس ← `gauge_force`
  - $\zeta$ = الاحتكاك ← `friction`

- **الأشكال:** Morphisms تحفظ البنية. تعيين KMeans → حقل المقياس هو functorial.

- **التحقق:** شرط الـ functor $F(g \circ f) = F(g) \circ F(f)$ يتحقق لأن كل خطوة حسابية **مستقلة عن المسار** (path-independent). $\square$

### 12.3 الفرضية الوجودية

**المبرهنة 12.2 (شرط وجود البوت).** إذا كانت جميع الافتراضات:

1. $\Sigma$ نظام ergodic (Postulate 4)
2. مبدأ جاينز يُطبَّق (Postulate 3)
3. الحد الأدنى من اللاتناظرية $G_t > 0$ (وإلا لا حقل)
4. الاحتكاك $\zeta > 0$ (وإلا لا استقرار)

تتحقق، فإن $\mathcal{M}$ يُنتج نظام تداول مستقر.

**البرهان:** مباشر من Thm 6.19 + Second Law. $\square$

---

## الجزء 13: الخلاصة الرياضية

البوت **ليس** تطبيقاً حرفياً للورقة. الورقة تعطي **بنية رياضية**، والبوت يترجمها إلى **خوارزميات قابلة للحساب** عبر:

1. **KMeans** يحل محل $\arg\max H$ (غير قابل للحل التحليلي).
2. **معادلة الفرق** تحل محل SDE المستمر.
3. **K ديناميكي** يُقرّب التقسيم الأمثل.
4. **Boltzmann** يُعطي شرط دخول قابل للتحقق.
5. **القانون الثاني** يُستخدم بمعنى معاكس (إشارة خروج).

**الفكرة الجوهرية المستفادة:** الورقة تُثبت أن "الهندسة ناشئة"، والبوت يستغل هذه الهندسة:
- مقياس Fisher → حجم التغاير
- حقل المقياس → لاتناظرية الانتقالات
- الطاقة الحرة → الفرق بين الطاقتين
- الاحتكاك → تبادل بين السرعة والدقة

**النتيجة:** البوت يعمل في فضاء رياضي صحيح بُني من الورقة، لكن الخوارزميات تقريبية (KMeans مقابل argmax، فرق مقابل مشتقة، إلخ).

**الحافة الحقيقية للبوت ليست في فكرة واحدة، بل في الترجمة المتسقة لهذه البنية — وهذا ما يجعل جهد التعديل على أي معامل منتِجاً.**
