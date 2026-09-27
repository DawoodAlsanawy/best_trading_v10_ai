# التعديل — الدخول فقط في أول 5 دقائق من كل شمعة

## الفكرة الفيزيائية

البوت حالياً يستطيع وضع أمر معلّق في أي لحظة، لكن الأمر يعيش 200 ثانية فقط (`PO_MAX_WAIT_S`). النتيجة: **يُفتح في اللحظة 55 من الشمعة → يُغلق قبل أن تبدأ الشمعة الجديدة → لا شيء حدث.**

الحل: اقصر نافذة الدخول على **أول 5 دقائق من كل شمعة**. هذا يعطي:

1. **الشمعة الجديدة "طازجة"** — السعر عند فتحها يعكس كل معلومات الشمعة السابقة
2. **كل الأوامر المعلّقة تتزامن** — لا صفقات عشوائية في منتصف الشمعة
3. **التنفيذ يُقارَب بنيوياً** — نعرف بالضبط متى يُقرَّر الدخول

---

## التعديل ① — ثوابت `Config`

**الموقع:** في `class Config`، بعد `OCO_ENTRY_ENABLED`.

**✅ أضف:**

```python
    # ══ [ENTRY WINDOW — first N minutes of each bar] ══
    # Restrict new entries to the first ENTRY_WINDOW_SEC seconds of every
    # closed bar. Prevents the "mid-bar entry, tiny wait" pathology where
    # the 200s order lifetime expires before any meaningful move happens.
    ENTRY_WINDOW_ENABLED: bool = True
    ENTRY_WINDOW_SEC: int = 300            # 5 minutes
    # Tolerance: consider the window open if we're at most this many
    # seconds past the bar open (handles scheduler jitter).
    ENTRY_WINDOW_TOLERANCE_S: int = 15
```

---

## التعديل ② — الحاجز في `run_live`

**الموقع:** داخل `run_live`، قسم **"اقتناص ودخول صفقات جديدة"** — قبل توليد الإشارات مباشرة.

**❌ ابحث عن:**

```python
            # 2. اقتناص ودخول صفقات جديدة
            # ══ [SAFETY] Dynamic concurrent limit based on drawdown ══
            dd_live = (peak_cap_live - cap_live) / (peak_cap_live + 1e-12)
```

**✅ استبدله بـ:**

```python
            # 2. اقتناص ودخول صفقات جديدة
            # ══ [ENTRY WINDOW] Only place new orders in the first N seconds
            # of each bar. This prevents stale mid-bar signals from being
            # executed just before the wait window expires.
            if getattr(CFG, 'ENTRY_WINDOW_ENABLED', True):
                _tf_sec_win = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                _now_ts_win = time.time()
                _bar_open_ts = (_now_ts_win // _tf_sec_win) * _tf_sec_win
                _sec_into_bar = _now_ts_win - _bar_open_ts
                _win_sec = int(getattr(CFG, 'ENTRY_WINDOW_SEC', 300))
                _tol_sec = int(getattr(CFG, 'ENTRY_WINDOW_TOLERANCE_S', 15))
                if _sec_into_bar > (_win_sec + _tol_sec):
                    # Skip entry hunting for the rest of this bar.
                    # Still do reconciliation and persist state at loop end.
                    sleep_time = max(0, cfg.LIVE_POLL_SECS - (time.time() - t0))
                    time.sleep(sleep_time)
                    continue

            # ══ [SAFETY] Dynamic concurrent limit based on drawdown ══
            dd_live = (peak_cap_live - cap_live) / (peak_cap_live + 1e-12)
```

---

## لماذا `continue` وليس `if` بسيط؟

`continue` **يتخطى** كل قسم الدخول (توليد الإشارات، الفلترة، وضع الأوامر) في تلك الدورة، ثم ينام للدورة القادمة. هذا يعطي:

- **لا استدعاء `build_signals`** 55 دقيقة من كل ساعة → توفير CPU و API
- **لا وضع أوامر معلّقة جديدة** خارج النافذة الزمنية
- **مراقبة المراكز المفتوحة** تبقى تعمل (لأنها قبل قسم الدخول) ✅
- **مراقبة الأوامر المعلّقة** تبقى تعمل (`monitor_pending_orders` في بداية الحلقة) ✅

---

## ما لم يتغيّر

- مراقبة المراكز المفتوحة → تعمل كل 5 ثوانٍ
- Trailing SL → يعمل
- Layer 7 (sync أوامر البورصة) → يعمل
- `monitor_pending_orders` → يعمل (يفحص الأوامر المعلّقة كل دورة)
- Kill Switch → يعمل
- Reconcile → يعمل

**فقط توليد إشارات جديدة ووضع أوامر جديدة** مقيَّد بأول 5 دقائق.

---

## التحقق

```bash
grep -c "ENTRY_WINDOW_ENABLED" trading.py
# متوقع: 2-3

grep -c "_sec_into_bar" trading.py
# متوقع: 2 (تعريف + فحص)

grep -n "ENTRY_WINDOW_SEC" trading.py
# متوقع: سطر التعريف + استخدام واحد
```

---

## الاختبار

```bash
rm -rf asset_cache market_data_cache

python trading.py --mode backtest --timeframe 1h --history-days 365 --nassets 30 \
  --as-of 2025-01-01 2>&1 | tee bt_entry_window.txt
```

**⚠️ ملاحظة مهمة:** التعديل يخص **Live فقط** (`run_live`). الـ Backtest لا يستفيد منه مباشرة، لأن Backtest لا يحتوي على حلقة زمنية حقيقية — كل شيء يُحاكى بشكل لحظي.

**لمحاكاة أثر التعديل في Backtest** يجب تعديل `precompute_entry_fills` لقبول الأوامر فقط من الشموع التي تُفتح بها الإشارة. هذا **تعديل منفصل** سأعطيك إياه إذا أردت قياس الأثر في Backtest أولاً.

---

## السؤال الحاسم قبل التطبيق

**هل تريد:**

**(أ)** تطبيق التعديل كما هو — **Live فقط**، وتختبره على Testnet مباشرة.

**(ب)** تطبيقه على الاثنين — أضيف تعديلاً آخر في `precompute_entry_fills` يفرض نفس القيد الزمني في Backtest.

**إذا كان هدفك** حل مشكلة "الدخول في مكان بعيد" — لاحظ أن هذا التعديل **لا يحل تلك المشكلة**. هو فقط يضمن أن الأوامر تُوضع في **وقت** محدد، لا **سعر** محدد. السعر لا يزال `tunnel_price` بعيداً.

**إذا كان هدفك** الحقيقي هو **"الدخول فقط عند فتح الشمعة، بسعر السوق حينها"** — فهذا تعديل مختلف تماماً يحتاج تعطيل `PO_FIXED_PRICE` واستخدام سعر السوق الفعلي عند فتح الشمعة.

**أخبرني أيهما تريد بالضبط، وسأعطيك التعديل الصحيح.**
