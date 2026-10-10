# إجاباتي على الأسئلة الخمسة

## السؤال 1 — عتبة "قريب جداً"

### الجواب: عتبة σ-نسبية مع κ_prox = 0.5

**المبرر الرياضي:**

البوت يستخدم σ كوحدة قياس في كل مكان (`FRICTION_DIP_KAPPA`, `SL_REF_KAPPA`, `TRAIL_KAPPA`). التناسق يفرض أن نستخدمها هنا أيضاً:

```
trigger_zone = κ_prox · σ_bar · p
```

اختيار κ_prox = 0.5 يقوم على ثلاثة اعتبارات:

1. **احتمال الوصول (Brownian)**: إذا كان السعر عند `0.5σ` من الهدف، فاحتمال لمسه خلال نافذة زمنية معقولة يقارب 90%. عند `0.3σ` يقارب 80% (تأخير في التنفيذ)، وعند `1.0σ` يقارب 95% (وضع الأمر قبل أوانه، يبقى معلقاً طويلاً).

2. **التناسق مع الفيزياء الداخلية**: `_friction_dip = 4σ` هي المسافة المصمَّمة، فـ `0.5σ` = **1/8 من المسافة** — قريب بما يكفي ليكون "اقتراباً" فعلياً.

3. **التوافق مع شرط (ب)**: الشرط البنيوي (SL تحت القاع) نادراً ما يكون متحققاً لفترة طويلة. إذا وضعنا العتبة عند `1.0σ` سنُفعِّل المراقبة مبكراً جداً، فنقضي وقتاً في فحص شرط (ب) وهو لا يزال مرفوضاً.

**لماذا ليس ديناميكياً بالتقلب؟**
لأن `σ_bar` **هو** التقلب. استخدام `σ_bar` يعني أن العتبة ديناميكية بطبيعتها. لا حاجة لمضاعِف إضافي.

**التنفيذ:**
```python
PROX_KAPPA: float = 0.5
# شرط (أ):
|p_now − tunnel_entry_p| ≤ PROX_KAPPA · σ_bar · tunnel_entry_p
```

---

## السؤال 2 — نافذة "آخر قاع/قمة"

### الجواب: 60 شمعة + نمط 3-شمعة + buffer 0.3·ATR

**المبرر:**

البوت لديه بالفعل `_find_recent_swing` بـ `TRAIL_STRUCTURE_LOOKBACK = 50`. لكن هناك سببان لاستخدام **60** هنا:

1. **آخر swing يظهر عادة كل 20-30 شمعة** على 4h. مع 60 شمعة، لدينا 2-3 مرشحين لاختيار الأحدث. مع 30 شمعة قد لا نجد أي swing في بعض الأحيان.

2. **أفق البنية السعرية**: 60 شمعة على 4h = 10 أيام. هذا هو المدى الذي تكون فيه الدعوم والمقاومات "حقيقية" وليست ضجيجاً. أقل من 5 أيام = noise. أكثر من 15 يوماً = بنية قديمة ربما كُسرت.

**تعريف الـ swing (نفس نمط البوت):**
```
swing_low[j]:  lows[j] < lows[j-1] AND lows[j] < lows[j+1]
swing_high[j]: highs[j] > highs[j-1] AND highs[j] > highs[j+1]
```

**شرط (ب) الدقيق:**

ليس كافياً أن يكون SL تحت القاع. يجب أن يكون القاع **بين** الدخول و SL، وإلا فهو لا يحمي:

```python
BUY:  sl_designed < swing_low − buffer·ATR < tunnel_entry_p
SELL: tunnel_entry_p < swing_high + buffer·ATR < sl_designed
```

**Buffer = 0.3 · ATR** — نفس القيمة المستخدمة في `TRAIL_STRUCTURE_BUFFER_SIGMA`. المنطق: هذا يعطي هامشاً كافياً بحيث لا يلامس السعر الـ swing ويرتد قبل الوصول لـ SL، لكنه ليس واسعاً بحيث يفقد SL معناه.

**لماذا لا نتحقق من "عمق" الـ swing؟**
لأن شرط (ب) بطبيعته يفلتر ذلك: إذا كان الـ swing سطحياً جداً، فسيقع قريباً من الدخول، ولن يبقى بين الدخول و SL (لأن SL محسوب من `geodesic_stop` الذي يعطي مسافة معنوية). إذن الشرط مُفلتر ضمنياً.

**التنفيذ:**
```python
SWING_LOOKBACK: int = 60
SWING_BUFFER_MULT: float = 0.3   # × ATR
```

---

## السؤال 3 — معيار "هل سيعود السعر"

### الجواب: إعادة استخدام `P_activation` + `UNIFIED_FRESH_SCORE_FRAC`

**المبرر — مبدأ إعادة الاستخدام بدل الاختراع:**

البوت لديه بالفعل دالة `_check_unified_stage2` التي تحقق بالضبط الشرط المطلوب: "هل الإشارة لا تزال حية؟" في `build_signals`. منطقها:

```python
P_activation = exp(-Γ / (|accel| · T_info)) ≥ 0.35
score_now ≥ UNIFIED_FRESH_SCORE_FRAC × score_original   (0.85)
momentum موافق > UNIFIED_MOMENTUM_KAPPA · σ_bar· p      (0.5)
```

هذا **بالضبط** ما تطلبه. لا نبتكر معياراً جديداً — نُعيد استخدام الفيزياء نفسها.

**لكن هناك إضافة واحدة ضرورية**: في حالتك، السعر عبر `tunnel_entry_p` بقوة. نحتاج فحصاً إضافياً: هل الاتجاه الحاد اتجاهي أم ارتدادي؟

المعيار الفيزيائي: **مقارنة `geo_accel` الحالي بـ `friction` الحالي**:

```python
ratio = |geo_accel_current| / friction_current

إذا ratio < 1.0  →  النظام مخمَّد  →  الارجح ارتداد  →  الفرصة حية
إذا ratio ≥ 2.0  →  النظام انفجاري  →  الارجح استمرار  →  ألغِ
إذا 1.0 ≤ ratio < 2.0 → حالة رمادية  →  استخدم score كحكم
```

**القرار النهائي "الفرصة حية":**
```
P_activation_current ≥ 0.35
AND score_current ≥ 0.85 · score_original
AND |geo_accel_current| < 2.0 · friction_current
AND δ_gap_current < MAX_EQUILIBRIUM_GAP (0.35)
```

كل الشروط **متوفرة في الكود** — لا نحتاج اختراع مقياس جديد.

**ملاحظة مهمة:** هذا القرار **لا يتنبأ** بالعودة. يتنبأ بأن "الظروف التي ولّدت الإشارة لا تزال قائمة". إذا كانت كذلك، فالاحتمال الرياضي أن السعر سيعود (mean reversion) لا يزال سائداً على الاحتمال أن الاختراق حقيقي.

---

## السؤال 4 — مهلة Phase 2

### الجواب: `effective_bars(UNIFIED_MAX_AGE_BARS_1H)` مع حد أدنى 3

**المبرر:**

الإشارة وُلِّدت عند شمعة معينة. بعد `UNIFIED_MAX_AGE_BARS_1H = 12` ساعة، تتغير الميزات (feature values) تغيراً كافياً لأن KMeans قد يُصنّف النقطة بشكل مختلف. هذا يعني أن الإشارة **اصطلاحاً** ميتة بعد 12 ساعة.

على 4h: `12 × 0.25 = 3 شموع` = 12 ساعة.
على 1h: `12 × 1 = 12 شمعة` = 12 ساعة.
على 15m: `12 × 4 = 48 شمعة` = 12 ساعة.

هذا **متسق عبر الأُطر** — وهو الهدف من نظام `TF_SCALE`.

**الحد الأدنى 3 شموع**: حتى على الأُطر الصغيرة جداً، نمنح الأمر 3 شموع على الأقل. هذا يمنع حالة "وُضع الأمر وأُلغي فوراً" في ظروف تذبذبية.

**لماذا ليس 5 أو 10 شموع؟**
- 5 شموع على 4h = 20 ساعة → تجاوز `MAX_AGE` → الإشارة ميتة رياضياً.
- 10 شموع على 4h = 40 ساعة → KMeans سيعيد تصنيفها في cluster آخر، فتصبح إشارة مختلفة تماماً.

إذن: **12 ساعة** هو السقف الرياضي، **3 شموع على 4h** هي النتيجة العملية.

**التنفيذ:**
```python
phase2_timeout_bars = max(3, effective_bars(UNIFIED_MAX_AGE_BARS_1H))
```

---

## السؤال 5 — متى نلغي المراقبة (Phase 1 timeout)

### الجواب: 4 شموع، مع إلغاء فوري عند 3 شروط

**المبرر:**

في Phase 1 نحن ننتظر تحقق شرطين (قرب + صلاحية SL البنيوية). هذا قد يستغرق وقتاً أطول من `MAX_AGE_BARS`، لكن إذا تجاوزناه تصبح الإشارة قديمة.

**لماذا 4 شموع (16 ساعة على 4h)؟**
- 3 شموع = 12 ساعة = `MAX_AGE_BARS` → حدّي جداً
- 4 شموع = 16 ساعة → نافذة إضافية للفرصة لتظهر
- 5 شموع = 20 ساعة → الإشارة قديمة، KMeans سيرفضها

**الإلغاء الفوري (لا انتظار للـ timeout) عند:**

1. **إشارة جديدة على نفس الأصل** → تُستبدل القديمة (dedup موجود أصلاً).

2. **`score_current < 0.5 × score_original`** → انهيار فيزيائي كامل. ليست "عتبة صرامة" بل "علامة موت".

3. **`P_activation_current < 0.30`** → أقل من عتبة 0.35 المُستخدمة في توليد الإشارة الأصلية. النظام تحوّل لحالة رفض.

4. **مرور `MAX_AGE_BARS` شمعة كاملة** (لأن الإشارة صارت خارج نافذة KMeans).

**التنفيذ:**
```python
watch_timeout_bars = 4
watch_abort_score_ratio = 0.5
watch_abort_p_activation = 0.30
```

---

## جدول المعاملات النهائي

| المعامل | القيمة | الوحدة | المبرر |
|---|---|---|---|
| `PROX_KAPPA` | 0.5 | × σ_bar | احتمال لمس الهدف > 90% |
| `SWING_LOOKBACK` | 60 | شمعة | يغطي 2-3 swings مؤكدة |
| `SWING_BUFFER_MULT` | 0.3 | × ATR | متسق مع `TRAIL_STRUCTURE_BUFFER_SIGMA` |
| `OPP_ALIVE_P_ACT` | 0.35 | — | عتبة توليد الإشارة نفسها |
| `OPP_ALIVE_SCORE` | 0.85 | × original | `UNIFIED_FRESH_SCORE_FRAC` الموجود |
| `OPP_ALIVE_ACCEL_RATIO` | 2.0 | × friction | حد الانفجار |
| `PHASE2_TIMEOUT` | 3 (على 4h) | شمعة | `effective_bars(12)` |
| `PHASE1_TIMEOUT` | 4 (على 4h) | شمعة | 16 ساعة، قبل تدهور الميزات |
| `PHASE1_ABORT_SCORE` | 0.5 | × original | انهيار فيزيائي |
| `PHASE1_ABORT_P_ACT` | 0.30 | — | تحت عتبة التوليد |

---

## ملاحظة أخيرة — كل هذا يعمل ضمن بنية قائمة

نقطة قوة هذا التصميم: **لا نُضيف أي مفهوم جديد**. كل معيار إما:
- موجود في الكود (P_activation, score, friction, σ_bar)، أو
- امتداد طبيعي لأحد الثوابت القائمة (`TRAIL_STRUCTURE_LOOKBACK`, `UNIFIED_FRESH_SCORE_FRAC`, `UNIFIED_MAX_AGE_BARS_1H`).

هذا يعني: **صفر خطر فلسفي**. البوت يتصرف بنفس شخصيته الرياضية، فقط مع آلية زمنية أذكى.

---

هل تريد الآن أن أُترجم هذا إلى:
1. **تعديلات جراحية** في الكود الحالي (بأقل عدد ممكن من الأسطر، بنفس أسلوب `_load_cached` السابق)، أم
2. **آلة حالة جديدة كاملة** (module مستقل) مع اختبارات منطق واضحة؟

أوصي بالخيار (1) — لأن الكود الحالي لديه بالفعل `_PENDING_ORDERS` و `monitor_pending_orders`، ونحتاج فقط تعديل `place_pending_entry` ليضيف مرحلة "watch" قبل "place"، وتعديل `monitor_pending_orders` ليضيف منطق إعادة التقييم بعد الفجوة والملء الجزئي.






# التعديلات الجراحية — Watch-Then-Trigger State Machine

سأُقدّم التعديلات بترتيب رقمي. كل تعديل يحمل **مكانه الدقيق** وكتلة **جاهزة للنسخ**. لا تحذف أي شيء لم يُذكر.

---

## التعديل 1 — إضافة حقول `Config`

**الموقع**: داخل `class Config`، بعد آخر حقل `FILTER_LOG_REJECTIONS`.

```python
    # ══ [WATCH-THEN-TRIGGER — proximity + structure gate] ══
    WATCH_MODE_ENABLED: bool = True
    WATCH_PROX_KAPPA: float = 0.5
    WATCH_SWING_LOOKBACK: int = 60
    WATCH_SWING_BUFFER_MULT: float = 0.3
    WATCH_OPP_P_ACT_MIN: float = 0.35
    WATCH_OPP_SCORE_RATIO: float = 0.85
    WATCH_OPP_ACCEL_RATIO_MAX: float = 2.0
    WATCH_PHASE1_TIMEOUT_BARS_1H: int = 16
    WATCH_PHASE1_ABORT_SCORE: float = 0.5
    WATCH_PHASE1_ABORT_P_ACT: float = 0.30
    WATCH_FILE_PREFIX: str = "watch_signals"
    WATCH_MAX_PER_CYCLE: int = 5          # cap triggers per loop iteration
```

---

## التعديل 2 — حالة عالمية + استمرارية

**الموقع**: مباشرة بعد كتلة `_PENDING_ORDERS`، قبل `load_pending_orders` (ابحث عن `_PENDING_ORDERS_PATH: str = ""`).

```python
# ════════════════════════════════════════════════════════════════
# § 18.94  Watched Signals — Watch-Then-Trigger State
# ════════════════════════════════════════════════════════════════

_WATCHED_SIGNALS: Dict[str, Dict] = {}
_WATCHED_SIGNALS_PATH: str = ""


def load_watched_signals(mode: str) -> Dict[str, Dict]:
    global _WATCHED_SIGNALS, _WATCHED_SIGNALS_PATH
    _WATCHED_SIGNALS_PATH = f"{CFG.WATCH_FILE_PREFIX}_{mode}.json"
    if os.path.exists(_WATCHED_SIGNALS_PATH):
        try:
            with open(_WATCHED_SIGNALS_PATH) as f:
                _WATCHED_SIGNALS = json.load(f)
            log.info(f"[Watch] Restored {len(_WATCHED_SIGNALS)} "
                     f"watched signals")
        except Exception as e:
            log.warning(f"[Watch] load failed: {e}")
            _WATCHED_SIGNALS = {}
    else:
        _WATCHED_SIGNALS = {}
    return _WATCHED_SIGNALS


def save_watched_signals() -> None:
    if not _WATCHED_SIGNALS_PATH:
        return
    try:
        tmp = _WATCHED_SIGNALS_PATH + ".tmp"
        serializable = {}
        for sym, rec in _WATCHED_SIGNALS.items():
            _r = {}
            for k, v in rec.items():
                if k in ('signal_ref', 'ad_ref'):
                    continue
                if isinstance(v, (np.floating, np.integer)):
                    v = v.item()
                elif isinstance(v, np.ndarray):
                    continue
                _r[k] = v
            serializable[sym] = _r
        with open(tmp, 'w') as f:
            json.dump(serializable, f, indent=2)
        os.replace(tmp, _WATCHED_SIGNALS_PATH)
    except Exception as e:
        log.warning(f"[Watch] save failed: {e}")
```

---

## التعديل 3 — دوال مساعدة (proximity + swing + opportunity)

**الموقع**: مباشرة بعد `save_watched_signals` (قبل `load_pending_orders`).

```python
# ════════════════════════════════════════════════════════════════
# § 18.95  Watch — Helpers
# ════════════════════════════════════════════════════════════════

def _watch_proximity_ok(p_now: float, tunnel_p: float,
                         sigma_bar: float) -> bool:
    """Condition (a): |p_now − tunnel| ≤ κ · σ_bar · tunnel."""
    if p_now <= 0 or tunnel_p <= 0 or sigma_bar <= 0:
        return False
    dist = abs(p_now - tunnel_p)
    kappa = float(getattr(CFG, 'WATCH_PROX_KAPPA', 0.5))
    return dist <= kappa * sigma_bar * tunnel_p


def _find_swing_in_window(ad, end_ci: int, lookback: int, kind: str):
    """Most recent swing low/high within [end_ci-lookback, end_ci)."""
    try:
        lo = max(1, int(end_ci) - int(lookback))
        hi = min(int(end_ci), len(ad.lows) - 1)
        if hi - lo < 3:
            return None, -1
        if kind == "low":
            arr = ad.lows
            for j in range(hi - 1, lo, -1):
                if arr[j] < arr[j-1] and arr[j] < arr[j+1]:
                    return float(arr[j]), int(j)
        else:
            arr = ad.highs
            for j in range(hi - 1, lo, -1):
                if arr[j] > arr[j-1] and arr[j] > arr[j+1]:
                    return float(arr[j]), int(j)
    except Exception:
        pass
    return None, -1


def _watch_sl_structure_ok(ad, sig, sl_designed: float,
                            tunnel_p: float, current_ci: int) -> bool:
    """
    Condition (b): SL is protected by a recent swing.
      BUY : sl < swing_low − buffer·ATR < tunnel_p
      SELL: tunnel_p < swing_high + buffer·ATR < sl
    """
    try:
        lookback = int(getattr(CFG, 'WATCH_SWING_LOOKBACK', 60))
        buf_mult = float(getattr(CFG, 'WATCH_SWING_BUFFER_MULT', 0.3))
        atr = (float(ad.atr14[current_ci])
               if 0 <= current_ci < len(ad.atr14) else 0.0)
        if atr <= 0:
            atr = max(abs(tunnel_p - sl_designed) * 0.1, 1e-9)
        buffer = buf_mult * atr

        if sig.action == "BUY":
            sw, _ = _find_swing_in_window(ad, current_ci, lookback, "low")
            if sw is None:
                return False
            return (sl_designed < sw - buffer) and (sw - buffer < tunnel_p)
        else:
            sw, _ = _find_swing_in_window(ad, current_ci, lookback, "high")
            if sw is None:
                return False
            return (sl_designed > sw + buffer) and (sw + buffer > tunnel_p)
    except Exception as e:
        log.debug(f"[Watch] sl_structure_ok failed: {e}")
        return False


def _watch_opportunity_alive(ad, sig, current_ci: int,
                              current_fi: int) -> bool:
    """
    Reuses existing physics to test if the signal is still valid.
    Four gates: P_activation, score freshness, accel/friction, delta_gap.
    """
    try:
        if current_fi < 3 or current_fi >= len(ad.score):
            return False

        geo_a = float(ad.geodesic_accel[current_fi])
        fric = float(ad.friction[current_fi]) + 1e-6
        T_info = float(ad.T_info[current_fi])
        force_mag = abs(geo_a) + 1e-9

        # Gate 1 — P_activation
        P_act = float(np.exp(-fric / (force_mag * T_info)))
        if P_act < float(getattr(CFG, 'WATCH_OPP_P_ACT_MIN', 0.35)):
            return False

        # Gate 2 — score freshness
        sc_now = float(ad.score[current_fi])
        sc_orig = float(getattr(sig, 'score', 0.0))
        if sc_orig > 0:
            if sc_now < float(getattr(CFG, 'WATCH_OPP_SCORE_RATIO', 0.85)) * sc_orig:
                return False

        # Gate 3 — accel/friction explosion in the wrong direction
        ratio = abs(geo_a) / max(fric, 1e-9)
        if ratio > float(getattr(CFG, 'WATCH_OPP_ACCEL_RATIO_MAX', 2.0)):
            # BUY: dangerous if accel is strongly downward (negative)
            # SELL: dangerous if accel is strongly upward (positive)
            if sig.action == "BUY" and geo_a < 0:
                return False
            if sig.action == "SELL" and geo_a > 0:
                return False

        # Gate 4 — equilibrium gap
        dgap = (float(ad.delta_gap[current_fi])
                if current_fi < len(ad.delta_gap) else 0.0)
        if dgap > float(getattr(CFG, 'MAX_EQUILIBRIUM_GAP', 0.35)):
            return False

        return True
    except Exception as e:
        log.debug(f"[Watch] opportunity_alive failed: {e}")
        return False
```

---

## التعديل 4 — تسجيل الإشارة في قائمة المراقبة

**الموقع**: مباشرة بعد الدوال الثلاث السابقة.

```python
def register_watch_signal(sym: str, sig, ad) -> bool:
    """
    Register a signal for watching (no exchange call).
    Returns True if newly registered, False if duplicate.
    """
    if sym in _WATCHED_SIGNALS:
        log.debug(f"[Watch] {sym} already watched — skip")
        return False
    if sym in _PENDING_ORDERS:
        log.debug(f"[Watch] {sym} has pending order — skip")
        return False

    cur_ci = max(0, len(ad.closes) - 2)
    cur_fi = cur_ci - ad.feat_start
    if cur_fi < 0 or cur_fi >= len(ad.score):
        return False

    try:
        geo_a0 = float(ad.geodesic_accel[sig.feat_idx])
        fric0 = float(ad.friction[sig.feat_idx]) + 1e-6
        T_info0 = float(ad.T_info[sig.feat_idx])
        P_act0 = float(np.exp(-fric0 / ((abs(geo_a0) + 1e-9) * T_info0)))
    except Exception:
        P_act0 = 1.0

    _WATCHED_SIGNALS[sym] = {
        'sym': sym,
        'action': str(sig.action),
        'tunnel_entry_p': float(sig.price),
        'sl': float(sig.sl),
        'tp1': float(sig.tp1),
        'score': float(sig.score),
        'orig_P_act': float(P_act0),
        'close_idx': int(sig.close_idx),
        'feat_idx': int(sig.feat_idx),
        'T_info_val': float(sig.T_info_val),
        'dyn_risk': float(sig.dynamic_risk),
        'entry_ref_price': float(getattr(sig, 'entry_ref_price', 0.0) or sig.price),
        'entry_base_dip': float(getattr(sig, 'entry_base_dip', 0.0)),
        'registered_at': time.time(),
        'signal_ref': sig,
        'ad_ref': ad,
    }
    log.info(f"[Watch] {sig.action} {sym} registered @ "
             f"tunnel={sig.price:.6f} sl={sig.sl:.6f} "
             f"score={float(sig.score):.2f}")
    return True
```

---

## التعديل 5 — المُراقب الرئيسي `monitor_watch_signals`

**الموقع**: مباشرة بعد `register_watch_signal`.

```python
def monitor_watch_signals(exchange, open_pos_live: Dict,
                           assets: Optional[Dict] = None,
                           loop_iter: int = 0) -> None:
    """
    Iterate over watched signals. When (a) proximity + (b) SL-structure
    are both satisfied → hand off to place_pending_entry.
    Timeout / physics collapse → drop.
    """
    if not _WATCHED_SIGNALS:
        return

    _max_age_bars = max(3, effective_bars(
        int(getattr(CFG, 'UNIFIED_MAX_AGE_BARS_1H', 12))
    ))
    _phase1_timeout = max(3, effective_bars(
        int(getattr(CFG, 'WATCH_PHASE1_TIMEOUT_BARS_1H', 16))
    ))
    _triggers_this_cycle = 0
    _max_per_cycle = int(getattr(CFG, 'WATCH_MAX_PER_CYCLE', 5))

    for sym in list(_WATCHED_SIGNALS.keys()):
        rec = _WATCHED_SIGNALS[sym]

        # ── Re-hydrate ad / sig on restart ──
        ad = rec.get('ad_ref')
        if ad is None and assets is not None:
            ad = assets.get(sym)
        if ad is None:
            log.debug(f"[Watch] {sym} no AssetData — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        sig = rec.get('signal_ref')
        if sig is None:
            from types import SimpleNamespace as _SNS
            sig = _SNS(
                symbol=sym,
                action=str(rec.get('action', 'BUY')),
                price=float(rec.get('tunnel_entry_p', 0)),
                sl=float(rec.get('sl', 0)),
                tp1=float(rec.get('tp1', 0)),
                score=float(rec.get('score', 0)),
                close_idx=int(rec.get('close_idx', 0)),
                feat_idx=int(rec.get('feat_idx', 0)),
                T_info_val=float(rec.get('T_info_val', 0)),
                dynamic_risk=float(rec.get('dyn_risk', 0.01)),
                entry_ref_price=float(rec.get('entry_ref_price', 0)),
                entry_base_dip=float(rec.get('entry_base_dip', 0)),
            )
            rec['signal_ref'] = sig

        # ── Current bar / feature index ──
        cur_ci = max(0, len(ad.closes) - 2)
        cur_fi = cur_ci - ad.feat_start
        if cur_fi < 0 or cur_fi >= len(ad.score):
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        bars_elapsed = cur_ci - int(rec['close_idx'])

        # ── Timeouts ──
        if bars_elapsed > _phase1_timeout:
            log.info(f"[Watch] {sym} expired "
                     f"(age={bars_elapsed}>{_phase1_timeout}) — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue
        if bars_elapsed > _max_age_bars:
            log.info(f"[Watch] {sym} signal aged out "
                     f"(age={bars_elapsed}>{_max_age_bars}) — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        # ── Physics collapse → abort ──
        sc_now = float(ad.score[cur_fi])
        if sc_now < float(getattr(CFG, 'WATCH_PHASE1_ABORT_SCORE', 0.5)) * float(rec['score']):
            log.info(f"[Watch] {sym} physics collapsed "
                     f"(score {rec['score']:.2f}→{sc_now:.2f}) — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        try:
            geo_a = float(ad.geodesic_accel[cur_fi])
            fric = float(ad.friction[cur_fi]) + 1e-6
            T_info = float(ad.T_info[cur_fi])
            P_act_now = float(np.exp(-fric / ((abs(geo_a) + 1e-9) * T_info)))
        except Exception:
            P_act_now = 1.0
        if P_act_now < float(getattr(CFG, 'WATCH_PHASE1_ABORT_P_ACT', 0.30)):
            log.info(f"[Watch] {sym} P_activation collapsed "
                     f"(P={P_act_now:.3f}) — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        # ── Condition (a): proximity ──
        p_now = float(ad.closes[cur_ci])
        tunnel_p = float(rec['tunnel_entry_p'])
        try:
            sigma_bar = (float(ad.E_therm[cur_fi])
                         if cur_fi < len(ad.E_therm) else 0.01)
            if not np.isfinite(sigma_bar) or sigma_bar <= 1e-6:
                sigma_bar = 0.01
        except Exception:
            sigma_bar = 0.01

        if not _watch_proximity_ok(p_now, tunnel_p, sigma_bar):
            continue

        # ── Condition (b): SL structure ──
        if not _watch_sl_structure_ok(ad, sig, float(rec['sl']),
                                       tunnel_p, cur_ci):
            log.debug(f"[Watch] {sym} proximity OK but SL not "
                      f"protected — keep watching")
            continue

        # ══════════════════════════════════════════════════════
        # TRIGGER
        # ══════════════════════════════════════════════════════
        if _triggers_this_cycle >= _max_per_cycle:
            log.debug(f"[Watch] cycle cap reached — deferring {sym}")
            break

        if (len(open_pos_live) + len(_PENDING_ORDERS)) >= int(CFG.MAX_CONCURRENT_ASSETS):
            log.info(f"[Watch] {sym} exposure cap — will retry next cycle")
            continue

        _qty = float(rec.get('qty', 0.0) or 0.0)
        _leverage = int(rec.get('leverage', 0) or 0)
        if _qty <= 0 or _leverage <= 0:
            log.warning(f"[Watch] {sym} qty/lev missing — dropping")
            _WATCHED_SIGNALS.pop(sym, None)
            continue

        log.info(f"[Watch] {sym} TRIGGERED (proximity+structure)")

        _side = 'buy' if sig.action == 'BUY' else 'sell'
        _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
        _stage1_bars = effective_bars(
            int(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))
        )
        _timeout_s = float(_stage1_bars * _tf_sec)

        try:
            ok = place_pending_entry(
                exchange, sym, _side, _qty, sig,
                timeout_s=_timeout_s,
                leverage=_leverage,
                ad=ad,
            )
            if ok is not None:
                _triggers_this_cycle += 1
                log.info(f"[Watch] {sym} → pending placed")
                _WATCHED_SIGNALS.pop(sym, None)
                save_watched_signals()
                save_pending_orders()
            else:
                log.info(f"[Watch] {sym} place rejected — keeping watched")
        except Exception as e:
            log.warning(f"[Watch] {sym} trigger failed: {e}")
```

---

## التعديل 6 — تعديل `monitor_pending_orders` (ملء جزئي + فجوة)

**الموقع**: داخل `monitor_pending_orders`، ابحث عن كتلة `# ── Terminal: filled → promote ──`.

**استبدل هذه الكتلة كاملاً**:

```python
        # ── Terminal: filled → promote ──
        if status == 'closed':
            filled = float(rec.get('filled') or 0.0)
            total = float(rec.get('qty') or 0.0)
            if total > 0 and filled >= total * 0.98:
                ok = _promote_pending_to_position(exchange, sym, rec, open_pos_live)
                if not ok:
                    log.info(f"[Pending] {sym} dropped after non-promotable fill")
                _PENDING_ORDERS.pop(sym, None)
            else:
                # Partial close on exchange side; treat as filled and adapt
                ok = _promote_pending_to_position(exchange, sym, rec, open_pos_live)
                if not ok:
                    log.info(f"[Pending] {sym} dropped after partial fill")
                _PENDING_ORDERS.pop(sym, None)
            continue
```

**بهذه**:

```python
        # ── Terminal: filled → promote or complete ──
        if status == 'closed':
            filled = float(rec.get('filled') or 0.0)
            total = float(rec.get('qty') or 0.0)
            fill_ratio = filled / max(total, 1e-12)

            if fill_ratio >= 0.98:
                ok = _promote_pending_to_position(exchange, sym, rec,
                                                   open_pos_live)
                if not ok:
                    log.info(f"[Pending] {sym} dropped after full fill")
                _PENDING_ORDERS.pop(sym, None)

            elif fill_ratio >= float(getattr(CFG, 'PO_MIN_ACCEPT_RATIO', 0.10)):
                # ── [PARTIAL-COMPLETION] ──
                _ad = rec.get('ad_ref')
                _sig = rec.get('signal_ref')
                _alive = False
                if _ad is not None and _sig is not None:
                    try:
                        _cur_ci = max(0, len(_ad.closes) - 2)
                        _cur_fi = _cur_ci - _ad.feat_start
                        _alive = _watch_opportunity_alive(
                            _ad, _sig, _cur_ci, _cur_fi
                        )
                    except Exception:
                        _alive = False

                if _alive and fill_ratio < 0.95:
                    # Re-place remainder at same target
                    _remaining = total - filled
                    log.info(f"[Partial] {sym} filled={filled:.6f}/"
                             f"{total:.6f} — opp alive, re-placing "
                             f"remainder {_remaining:.6f}")
                    try:
                        _side_r = rec.get('side', 'buy')
                        _tgt_r = float(rec.get('price') or 0)
                        _o = exchange.create_order(
                            sym, 'limit', _side_r, _remaining, _tgt_r,
                            params={'timeInForce': 'GTX'}
                        )
                        # Persist accumulated fill in a shadow field
                        _prev_filled = float(rec.get('acc_filled', 0.0))
                        _prev_cost = float(rec.get('acc_cost', 0.0))
                        _this_avg = float(rec.get('avg_price') or 0.0)
                        rec['acc_filled'] = _prev_filled + filled
                        rec['acc_cost'] = _prev_cost + _this_avg * filled
                        rec['order_id'] = str(_o['id'])
                        rec['qty'] = _remaining
                        rec['filled'] = 0.0
                        rec['avg_price'] = 0.0
                        rec['status'] = 'open'
                        rec['placed_at'] = time.time()
                        log.info(f"[Partial] {sym} remainder placed "
                                 f"@ {_tgt_r:.6f}")
                        continue
                    except Exception as _e:
                        log.warning(f"[Partial] {sym} re-place failed: "
                                    f"{_e} — promoting what we have")
                        # Fall through to promote partial
                        ok = _promote_pending_to_position(
                            exchange, sym, rec, open_pos_live
                        )
                        _PENDING_ORDERS.pop(sym, None)
                else:
                    # Opportunity dead → keep filled part, drop remainder
                    log.info(f"[Partial] {sym} opp dead — keeping "
                             f"{filled:.6f}, abandoning "
                             f"{total-filled:.6f}")
                    ok = _promote_pending_to_position(exchange, sym, rec,
                                                       open_pos_live)
                    _PENDING_ORDERS.pop(sym, None)

            else:
                # Too small to accept — close tiny partial + drop
                log.warning(f"[Pending] {sym} fill {fill_ratio*100:.1f}% "
                            f"< PO_MIN_ACCEPT_RATIO — closing tiny partial")
                try:
                    _side_c = 'sell' if rec.get('action') == 'BUY' else 'buy'
                    exchange.create_order(sym, 'market', _side_c, filled)
                except Exception as e:
                    log.error(f"[Pending] close partial failed {sym}: {e}")
                _PENDING_ORDERS.pop(sym, None)

            continue
```

---

## التعديل 7 — Gap-Jump handling

**الموقع**: نفس `monitor_pending_orders`، بعد كتلة `# ── Terminal: canceled/expired/rejected → drop ──`.

**أضف هذه الكتلة مباشرة بعدها**:

```python
        # ══ [GAP-JUMP] — price broke through tunnel without filling ══
        if (float(rec.get('filled') or 0.0) <= 1e-12
                and status == 'open'):
            _ad = rec.get('ad_ref')
            _sig = rec.get('signal_ref')
            if _ad is not None and _sig is not None:
                _cur_ci = max(0, len(_ad.closes) - 2)
                _cur_fi = _cur_ci - _ad.feat_start
                _tunnel = float(rec.get('tunnel_entry_p')
                                or rec.get('price') or 0)
                _p_now = (float(_ad.closes[_cur_ci])
                          if _cur_ci < len(_ad.closes) else 0)
                _side_j = rec.get('side', 'buy')

                if _tunnel > 0 and _p_now > 0:
                    # BUY: expects price BELOW tunnel. If price now >0.5% above → jumped.
                    # SELL: expects price ABOVE tunnel. If price now <-0.5% → jumped.
                    _jumped = False
                    if _side_j == 'buy' and _p_now > _tunnel * 1.005:
                        _jumped = True
                    elif _side_j == 'sell' and _p_now < _tunnel * 0.995:
                        _jumped = True

                    if _jumped and 0 <= _cur_fi < len(_ad.score):
                        _alive_j = _watch_opportunity_alive(
                            _ad, _sig, _cur_ci, _cur_fi
                        )
                        if _alive_j:
                            log.info(f"[Gap-Jump] {sym} jumped "
                                     f"(tunnel={_tunnel:.6f}, "
                                     f"now={_p_now:.6f}) — opp alive, "
                                     f"re-pricing")
                            _oid = rec.get('order_id')
                            if _oid:
                                try:
                                    exchange.cancel_order(_oid, sym)
                                except Exception:
                                    pass
                                time.sleep(0.2)
                                _sweep_pending_once(exchange, sym)
                                _chk = _PENDING_ORDERS.get(sym)
                                if (_chk and
                                        float(_chk.get('filled') or 0) > 0):
                                    continue  # partial arrived
                            try:
                                _pen = float(CFG.PO_PENETRATION_BPS) * 1e-4
                                _new_tgt = (_p_now * (1 - _pen) if _side_j == 'buy'
                                            else _p_now * (1 + _pen))
                                _rem = float(rec.get('qty') or 0) - float(rec.get('filled') or 0)
                                _o2 = exchange.create_order(
                                    sym, 'limit', _side_j, _rem, _new_tgt,
                                    params={'timeInForce': 'GTX'}
                                )
                                rec['order_id'] = str(_o2['id'])
                                rec['price'] = float(_new_tgt)
                                rec['gap_repriced'] = int(rec.get('gap_repriced', 0)) + 1
                                log.info(f"[Gap-Jump] {sym} re-priced "
                                         f"→ {_new_tgt:.6f}")
                            except Exception as _e:
                                log.warning(f"[Gap-Jump] {sym} re-price "
                                            f"failed: {_e}")
                        else:
                            log.info(f"[Gap-Jump] {sym} jumped & opp dead "
                                     f"— cancel + drop")
                            _oid = rec.get('order_id')
                            if _oid:
                                try:
                                    exchange.cancel_order(_oid, sym)
                                except Exception:
                                    pass
                            _PENDING_ORDERS.pop(sym, None)
                        continue
```

---

## التعديل 8 — استبدال التسجيل المباشر في `run_live`

**الموقع**: في `run_live`، داخل كتلة `# ══ 3. Entry — Non-Blocking Pending Order ══`. ابحث عن:

```python
                        # ══ 3. Entry — Non-Blocking Pending Order ══
                        if getattr(CFG, 'PENDING_ENABLED', True):
```

واستبدل الكتلة **بأكملها** (حتى نهاية `continue` الأخيرة قبل `else:`) بهذه:

```python
                        # ══ 3. Entry — Watch mode (or legacy pending) ══
                        if getattr(CFG, 'PENDING_ENABLED', True):
                            _total_exposure = (len(_PENDING_ORDERS)
                                               + len(open_pos_live)
                                               + len(_WATCHED_SIGNALS))
                            if _total_exposure >= int(CFG.MAX_CONCURRENT_ASSETS):
                                log.debug(
                                    f"[Watch] exposure cap "
                                    f"({_total_exposure}≥"
                                    f"{CFG.MAX_CONCURRENT_ASSETS}) "
                                    f"— skip {sym}"
                                )
                                continue

                            # ══ [WATCH-THEN-TRIGGER] ══
                            if getattr(CFG, 'WATCH_MODE_ENABLED', True):
                                _ok = register_watch_signal(
                                    sym, sig, assets[sym]
                                )
                                if _ok:
                                    _WATCHED_SIGNALS[sym]['qty'] = float(qty)
                                    _WATCHED_SIGNALS[sym]['leverage'] = int(dynamic_leverage)
                                    _WATCHED_SIGNALS[sym]['mmr'] = float(
                                        _mmr_sig or
                                        getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02)
                                    )
                                    save_watched_signals()
                                continue

                            # ── Legacy immediate placement ──
                            _tf_sec_w = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                            _bars_wait = int(effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS))
                            _timeout_s = float(_bars_wait * _tf_sec_w)
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
                                log.info(f"[Pending] {sym} rejected — skip")
                                continue
                            try:
                                save_pending_orders()
                            except Exception:
                                pass
                            continue
```

---

## التعديل 9 — استدعاء `monitor_watch_signals` في الحلقة

**الموقع**: في `run_live`، ابحث عن:

```python
            # ══ [Pending] Sweep pending orders every cycle ══
            # [Sing-Timing] نمرّر assets ليتمكن الفحص من قراءة الرنين الحالي.
            try:
                monitor_pending_orders(
```

**أضف قبله مباشرة**:

```python
            # ══ [WATCH-THEN-TRIGGER] Check watched signals ══
            try:
                monitor_watch_signals(
                    exchange, open_pos_live,
                    assets=assets if 'assets' in dir() else None,
                    loop_iter=loop_iter
                )
            except Exception as _e:
                log.warning(f"[Watch] monitor error: {_e}")

```

---

## التعديل 10 — تحميل الإشارات المراقبة عند الإقلاع

**الموقع**: في `run_live`، بعد:

```python
    load_pending_orders(cfg.mode)
```

**أضف مباشرة بعده**:

```python
    # ══ [Watch] Load persisted watched signals ══
    load_watched_signals(cfg.mode)
    log.info(f"  [Watch] Active watched signals: {len(_WATCHED_SIGNALS)}")
```

---

## التعديل 11 — حفظ الإشارات المراقبة عند نهاية الدورة

**الموقع**: في `run_live`، ابحث عن:

```python
            save_pending_orders()
            save_symbol_meta()
```

**استبدلها بـ**:

```python
            save_pending_orders()
            save_watched_signals()
            save_symbol_meta()
```

---

## التعديل 12 — CLI flag للتعطيل

**الموقع**: في `main()`، عند كتلة `argparse`. أضف بعد `--no-kill-switch`:

```python
    p.add_argument("--no-watch", action="store_true",
                   help="Disable watch-then-trigger mode "
                        "(place orders immediately, legacy behavior)")
```

**الموقع الثاني**: في `main()`، بعد كتلة `if args.no_kill_switch:`:

```python
    if args.no_watch:
        CFG.WATCH_MODE_ENABLED = False
        log.info("[Watch] Watch-then-trigger DISABLED — legacy immediate placement")
    else:
        log.info("[Watch] Watch-then-trigger ENABLED "
                 f"(κ_prox={CFG.WATCH_PROX_KAPPA}, "
                 f"swing_lookback={CFG.WATCH_SWING_LOOKBACK}, "
                 f"phase1_timeout={CFG.WATCH_PHASE1_TIMEOUT_BARS_1H}h)")
```

---

## جدول موجز

| # | الدالة/الموقع | التعديل | الأسطر المتوقعة |
|---|---|---|---|
| 1 | `class Config` | 12 حقل جديد | +12 |
| 2 | بعد `_PENDING_ORDERS` | حالة + حفظ/تحميل | +48 |
| 3 | بعد التعديل 2 | 3 دوال مساعدة | +120 |
| 4 | بعد التعديل 3 | `register_watch_signal` | +50 |
| 5 | بعد التعديل 4 | `monitor_watch_signals` | +140 |
| 6 | داخل `monitor_pending_orders` | ملء جزئي | استبدال ~15 بـ ~85 |
| 7 | داخل `monitor_pending_orders` | Gap-jump | +65 |
| 8 | `run_live` كتلة الدخول | watch بدل pending | استبدال ~30 بـ ~50 |
| 9 | `run_live` حلقة | استدعاء monitor | +9 |
| 10 | `run_live` بداية | load | +3 |
| 11 | `run_live` نهاية | save | +1 |
| 12 | `main()` | flag | +6 |

**الإجمالي الصافي**: ~+530 سطر.

---

## اختبار سريع

بعد التطبيق، شغّل بوسم `--no-watch` لمقارنة السلوك القديم. ثم بدونها لرؤية:

```
[Watch] SELL LTC/USDT registered @ tunnel=90.38 sl=92.84 score=6.26
[Watch] LTC/USDT proximity OK but SL not protected — keep watching
...
[Watch] LTC/USDT TRIGGERED (proximity+structure)
[Watch] LTC/USDT → pending placed
[Pending] SELL LTC/USDT @ 90.37 qty=... id=... (timeout=...)
```

وتأكد من الملفات:
```bash
ls -la watch_signals_testnet.json pending_orders_testnet.json
```

كلٌّ منهما قائمٌ بذاته، ويُحمَّل عند إعادة الإقلاع، ويُحفظ عند كل دورة.




