📖 الشرح الشامل لكل Option — مع العلاقات والأثر على الأداء

هذا الدليل مُنظَّم في 13 مجموعة وظيفية. لكل option: ما يفعله، القيم المقبولة، القيمة الافتراضية، الأثر، العلاقات، ماذا يجب أن يتغير معه.

---

المجموعة 1: وضع التشغيل والمصادقة

1.1 --mode {backtest, testnet, live}

ما يفعله: يحدد وضع تشغيل البوت بالكامل.

القيمة ما يحدث
backtest قراءة تاريخية، محاكاة، رسم، تقرير — لا اتصال بالبورصة
testnet اتصال بـ Binance Demo Trading، تنفيذ أوامر ورقية
live اتصال بـ Binance الحقيقي، أموال حقيقية

الأثر الجوهري:

· backtest يستخدم ProcessPoolExecutor (متعدد الأنوية)
· live/testnet يستخدم حلقة while True مع LIVE_POLL_SECS (كل 5 ثوان)
· LIVE_POLL_SECS لا يعمل في الباكتيست — لأن الباكتيست يحاكي كل شمعة دفعة واحدة

العلاقات:

· --mode live يتطلب --api-key و --api-secret
· --mode backtest يُتجاهل فيه --api-key و --api-secret
· --mode backtest يستخدم CFG.history_days (من --history-days)
· --mode live يستخدم CFG.LIVE_HISTORY_DAYS (يُحسب تلقائياً أو من --history-days)

ماذا يجب أن يتغير معه:

· --mode live → يجب أن يكون --max-notional صغيراً ومناسباً للسيولة
· --mode backtest → يمكن أن يكون --max-notional كبيراً (محاكاة)
· --mode backtest → --end-date مهم للـ reproducibility

---

1.2 --api-key API_KEY و --api-secret API_SECRET

ما يفعله: مفاتيح Binance API للمصادقة.

الأثر:

· مطلوب في live و testnet
· يُتجاهل في backtest
· إذا لم تُمرَّر، يمكن استخدام BINANCE_API_KEY و BINANCE_API_SECRET من متغيرات البيئة

العلاقات:

· مع --mode live/testnet → إلزامي
· مع --kill-secret → كلاهما أسرار يجب تأمينها

⚠️ تحذير أمني:

· لا تمرر هذه المفاتيح في سطر الأوامر (تظهر في ps). استخدم env vars
· أعط المفاتيح صلاحيات قراءة + تداول فقط (لا سحب)

---

المجموعة 2: رأس المال

2.1 --capital CAPITAL

ما يفعله: رأس المال الأولي (في backtest) أو الحد الأدنى للـ sizing (في live).

القيمة الافتراضية: $10 (من CFG.INITIAL_CAPITAL)

الأثر:

· في الباكتيست: نقطة البداية للحساب (compounding)
· في الـ live: يُستخدم فقط إذا لم يُمرَّر --live-capital

العلاقات:

· --capital $100 → --leverage قد تنخفض تلقائياً (من LEVERAGE_BASE / sqrt(capital/10))
· --capital صغير ($1) → ستحتاج --max-risk 0.15 و --maxcon 2 (كما في patch micro-capital)
· --capital كبير ($10,000+) → قد تحتاج --max-notional أصغر (سيولة محدودة)

ماذا يجب أن يتغير معه:

· $1-$10 → --max-risk 0.10-0.15، --maxcon 1-2، --leverage 25-50
· $10-$100 → --max-risk 0.05، --maxcon 3، --leverage 20-50
· $100-$1000 → --max-risk 0.03، --maxcon 5، --leverage 10-25
· $1000+ → --max-risk 0.015، --maxcon 5-10، --leverage 5-15

---

2.2 --live-capital LIVE_CAPITAL

ما يفعله: رأس مال ثابت للـ sizing في live/testnet، بدلاً من استخدام free balance من البورصة.

القيمة الافتراضية: 0 (يعني: استخدم free من البورصة)

لماذا يهم؟:

· free ينخفض عند فتح صفقات → البوت "يعتقد" أن رأس المال نقص → يصغّر الصفقات القادمة
· --live-capital يثبّت الرقم → sizing ثابت ومستقر

العلاقات:

· --live-capital 100 مع --capital 100 → sizing متطابق
· --live-capital 0 → استخدام free الحقيقي (قد يتقلب)

ماذا يجب أن يتغير معه:

· --live-capital > 0 → --max-risk يعمل كالمعتاد
· --live-capital = 0 → قد تحتاج --max-risk أعلى قليلاً (لتعويض تقلب free)

---

المجموعة 3: المخاطرة (Risk)

3.1 --base-risk BASE_RISK

ما يفعله: المخاطرة "الأساسية" في معادلة Kelly. لكنه غير مستخدم فعلياً في الحساب النهائي — يُستبدل بـ MIN_RISK و MAX_RISK.

القيمة الافتراضية: 0.02 (2%)

الأثر: لا شيء عملياً — legacy parameter.

العلاقات: يُتجاهل.

---

3.2 --max-risk MAX_RISK

ما يفعله: الحد الأقصى للمخاطرة في معادلة Kelly (قبل Budget).

القيمة الافتراضية: 0.05 (5%)

الأثر:

· يحدد السقف العلوي لـ f* من compute_geodesic_kelly
· كلما زاد، زادت المخاطرة على الصفقات القوية

العلاقات:

· مع --max-risk-per-trade: MAX_RISK هو سقف Kelly، MAX_RISK_PER_TRADE (من --heat-max والـ budget) هو السقف النهائي
· مع --leverage: إذا MAX_RISK عالٍ، قد تحتاج --leverage أقل (لأن qty = risk_amt / sl_dist)
· مع --max-notional: MAX_RISK قد ينتج qty كبير، ثم --max-notional يقطعه

ماذا يجب أن يتغير معه:

· --max-risk 0.10 → --maxcon ≤ 3 (لتجنب Heat عالٍ)
· --max-risk 0.15 → --maxcon ≤ 2
· --max-risk 0.05 → --maxcon ≤ 10

---

3.3 --min-risk MIN_RISK

ما يفعله: الحد الأدنى للمخاطرة في معادلة Kelly.

القيمة الافتراضية: 0.01 (1%)

الأثر:

· يحدد الأرضية لـ f* — لا تنزل تحتها
· يمنع الصفقات "الميتة" (حجم صغير جداً)

العلاقات:

· مع --min-risk-per-trade: MIN_RISK لـ Kelly، MIN_RISK_PER_TRADE (0.005 = 0.5%) هو الحد الأدنى النهائي
· إذا MIN_RISK < MIN_RISK_PER_TRADE، قد تُرفض الصفقات الضعيفة

ماذا يجب أن يتغير معه:

· --min-risk 0.02 → يجب --min-risk-per-trade ≤ 0.02
· --min-risk 0.05 → يجب --min-risk-per-trade ≤ 0.05

---

3.4 --lambda-k LAMBDA_K

ما يفعله: تخميد Kelly — يقلل المخاطرة عند رأس مال كبير.

القيمة الافتراضية: 0.05

الأثر:

· لكن: LAMBDA_KELLY غير مستخدم في compute_geodesic_kelly الحالي!
· البوت يستخدم thermal_damp بدلاً منه
· يعمل فقط في النسخ القديمة

العلاقات: يُتجاهل حالياً.

ماذا يجب أن يتغير معه: لا شيء (legacy).

---

المجموعة 4: الرافعة (Leverage)

4.1 --leverage LEVERAGE

ما يفعله: مضاعف أساسي للرافعة. القيمة الفعلية = LEVERAGE_BASE / sqrt(capital/INITIAL_CAPITAL).

القيمة الافتراضية: 5 (لكن LEVERAGE_BASE = 50 و LEVERAGE_MAX = 50)

الأثر:

· --leverage 20 → LEVERAGE_MAX = 20 → الرافعة لا تتجاوز 20x
· --leverage 5 → رافعة منخفضة، مخاطرة أقل، رسوم أقل، أرباح أقل

العلاقات:

· مع --capital: رأس مال كبير → L_dynamic منخفضة تلقائياً
· مع --max-risk: رافعة عالية + مخاطرة عالية = تصفية سريعة
· مع --sl-widen-mult: SL واسع + رافعة عالية = Liq أقرب
· مع --max-notional: رافعة عالية تسمح بمركز كبير، لكن --max-notional قد يقطعه

ماذا يجب أن يتغير معه:

· --leverage 50 → --sl-widen-mult 0.8-1.0 (SL ضيق لتناسب Liq)
· --leverage 20 → --sl-widen-mult 1.5-2.0
· --leverage 5 → --sl-widen-mult 2.5-3.0

⚠️ تحذير: --leverage أعلى من LevCap (محسوب من MMR) يُقصّ تلقائياً. لا فائدة من رقم أعلى من المسموح.

---

المجموعة 5: الفيزياء الأساسية

5.1 --sl-factor SL_FACTOR

ما يفعله: غير مستخدم حالياً في compute_geodesic_stop (الذي يستخدم SL_REF_KAPPA). Legacy parameter.

القيمة الافتراضية: 0.5

الأثر: لا شيء.

العلاقات: يُتجاهل.

---

5.2 --min-score MIN_SCORE

ما يفعله: الحد الأدنى لدرجة الإشارة (sig.score) للقبول.

القيمة الافتراضية: -6 (سخي جداً — يقبل معظم الإشارات)

الأثر:

· -6 → يقبل كل الإشارات (لا فلترة)
· 0 → يقبل نصف الإشارات
· 2 → يقبل فقط الإشارات القوية
· 5 → صارم جداً (قليل من الصفقات)

العلاقات:

· مع --gauge-filter: إذا مفعّل، gauge_force يفلتر قبل --min-score
· مع --rule-filter: إذا مفعّل، rule_score يفلتر إضافياً
· مع --confirm-entry: إذا مفعّل، min_score يطبق قبل التأكيد
· مع --reversal-confirm: min_score لا يتفاعل مباشرة

ماذا يجب أن يتغير معه:

· --min-score 0 → قد تحتاج --maxcon أعلى (صفقات أكثر)
· --min-score 3 → قد تحتاج --maxcon أقل (صفقات أقل، أدق)

---

5.3 --max-hold MAX_HOLD

ما يفعله: أقصى عدد شموع للاحتفاظ بصفقة قبل الإغلاق القسري.

القيمة الافتراضية: 2000 (عدد الشموع، بدون TF_SCALE)

الأثر:

· مع --timeframe 4h → 2000 شمعة = 333 يوم. MaxHold نادراً ما يُفعّل.
· مع --max-hold 100 → 100 شمعة × 4h = 400 ساعة = 16 يوم. معقول.
· مع --max-hold 20 → 20 شمعة × 4h = 80 ساعة = 3.3 يوم. سريع.

العلاقات:

· مع --timeframe: effective_bars(MAX_HOLD) يُطبَّق داخلياً
· مع --time-kill: --max-hold = أقصى مدة، --time-kill = خروج مبكر

ماذا يجب أن يتغير معه:

· --max-hold 2000 (افتراضي) → لا شيء
· --max-hold 50 → قد تحتاج --time-kill لتفعيل خروج مبكر أذكى

---

5.4 --topo-div TOPO_DIV

ما يفعله: عتبة Topo-Divergence — إذا (V_t - V_{t-1}) / V_{t-1} > TOPO_DIV و dH > 0، اخرج.

القيمة الافتراضية: 0.05 (5%)

الأثر:

· 0.05 → خروج نادر (5% توسع في V = 5% في محدد التغاير)
· 0.02 → خروج أكثر تكراراً
· 0.10 → خروج نادر جداً

العلاقات:

· مع --no-apex: إذا Topo-Div مفعّل، قد يغطي جزءاً من Apex
· مع --trailing: Topo-Div قد يُغلق قبل Trailing

ماذا يجب أن يتغير معه:

· --topo-div 0.02 → قد يقصر عمر الصفقات، راقب Hard TP
· --topo-div 0.10 → قد يترك صفقات أطول

---

5.5 --cosm-const COSM_CONST

ما يفعله: الثابت الكوني (Cosmological constant) — غير مستخدم حالياً في الفيزياء. Legacy.

القيمة الافتراضية: 0

الأثر: لا شيء.

العلاقات: يُتجاهل.

---

5.6 --k-min K_MIN و --k-max K_MAX

ما يفعلهما: حدود عدد الحالات في KMeans.

القيمة الافتراضية: K_MIN = 25، K_MAX = 50

الأثر:

· K الفعلي = min(K_MAX, max(K_MIN, K_capital, K_data))
· K أعلى → حالات أدق، إنتروبيا أعلى، إشارات أكثر
· K أقل → حالات أعرض، إنتروبيا أقل، إشارات أقل

العلاقات:

· مع --history-days: بيانات قليلة → K_data منخفض → K الفعلي منخفض
· مع --no-numba: KMeans أبطأ بدون numba
· مع --timeframe: 4h يحتاج K أقل من 1h

ماذا يجب أن يتغير معه:

· --k-max 50 → --history-days ≥ 200 (لضمان بيانات كافية)
· --k-max 100 → --history-days ≥ 500

---

المجموعة 6: البيانات والأداء

6.1 --timeframe {1m, 5m, 15m, 30m, 1h, 4h, 1d}

ما يفعله: الإطار الزمني للشموع.

القيمة الافتراضية: 4h

الأثر:

· 1m → صفقات كثيرة، رسوم عالية، slippage
· 4h → توازن (الافتراضي)
· 1d → صفقات قليلة، فرص أقل

العلاقات:

· مع --history-days: 4h يحتاج 730 يوم، 1d يحتاج 1000+ يوم
· مع --max-hold: effective_bars يعوّض TF_SCALE
· مع --sl-widen-mult: 4h يحتاج SL أوسع من 1h
· مع --k-min/max: 4h يحتاج K أقل

ماذا يجب أن يتغير معه:

TF --sl-widen-mult --maxcon --k-max --history-days
1m 0.5 10 50 30
5m 0.8 8 50 60
15m 1.0 6 40 200
1h 1.2 5 30 400
4h 2.5 5-10 25 730
1d 3.0 3-5 20 1000+

---

6.2 --history-days HISTORY_DAYS

ما يفعله: عدد أيام التاريخ لجلب البيانات.

القيمة الافتراضية: None (auto-calculated based على mode و TF)

الأثر:

· قليل جداً → KMeans degenerate، إشارات سيئة
· كثير جداً → يبطئ البداية، قد يخلط أنظمة قديمة

العلاقات:

· مع --timeframe: 4h يحتاج ≥ 730، 1d يحتاج ≥ 1000
· مع --k-max: K_data = n_train / min_pts. إذا --k-max 50، تحتاج n_train ≥ 5000 → history_days ≥ 500 (4h)

ماذا يجب أن يتغير معه:

· --history-days 200 → قلل --k-max إلى 30
· --history-days 730 → --k-max 50 آمن

---

6.3 --end-date END_DATE

ما يفعله: نهاية نافذة البيانات (تنسيق YYYY-MM-DD).

القيمة الافتراضية: None (يعني now())

الأثر:

· للـ reproducibility: نفس البيانات = نفس النتائج
· للـ walk-forward: تدريب على فترة، اختبار على أخرى

العلاقات:

· مع --history-days: النافذة = [end_date - history_days, end_date]
· مع --mode backtest: يُطبَّق فقط في الباكتيست

---

6.4 --no-numba

ما يفعله: يعطّل numba (JIT compilation).

الأثر:

· بدون numba: الباكتيست أبطأ 10-50×
· مع numba: أسرع، لكن قد يفشل في بيئات معينة (مثل Nuitka standalone)
· لا يؤثر على الـ live (لأن live لا يستخدم numba في الحلقة الرئيسية)

العلاقات:

· مع --mode backtest: قد تحتاج --workers أقل (لتجنب oversubscription)
· مع --no-parallel: إذا عطّلت numba و parallelism، الباكتيست بطيء جداً

---

6.5 --nassets NASSETS

ما يفعله: عدد الأصول المرشحة من scan_top_assets.

القيمة الافتراضية: 15

الأثر:

· قليل (5) → أصول أقل، فرص أقل، سيولة أعلى
· كثير (100) → أصول أكثر، فرص أكثر، سيولة أقل، KMeans أبطأ

العلاقات:

· مع --maxcon: إذا --nassets 100، قد تحتاج --maxcon 5-10
· مع --workers: --nassets 100 → --workers 4-8
· مع --max-notional: أصول أقل سيولة → --max-notional أصغر

ماذا يجب أن يتغير معه:

· --nassets 5 → --maxcon 2-3
· --nassets 100 → --maxcon 5-10, --workers 4+, --max-notional ≤ 20000

---

6.6 --maxcon MAXCON

ما يفعله: أقصى عدد مراكز متزامنة.

القيمة الافتراضية: 3 (من Config)، لكن يمكن تعديلها.

الأثر:

· قليل (2) → تنويع أقل، تركيز أعلى، مخاطرة إجمالية أقل
· كثير (10) → تنويع أعلى، كل صفقة أصغر (لأن heat مقيّد)

العلاقات:

· مع --heat-max: risk_per_slot = heat_max / maxcon. إذا --maxcon 10 و --heat-max 0.10 → 1% لكل صفقة
· مع --capital: $1 → --maxcon 1-2. $1000 → --maxcon 5-10
· مع --leverage: --maxcon عالٍ قد يستهلك rate limit أسرع

ماذا يجب أن يتغير معه:

· --maxcon 2 → --heat-max 0.20 (تركيز أعلى لكل صفقة)
· --maxcon 10 → --heat-max 0.10 (توزيع أوسع)

---

6.7 --workers WORKERS

ما يفعله: عدد العمليات المتوازية (ProcessPoolExecutor).

القيمة الافتراضية: 0 (auto = min(cpu_count, n_assets))

الأثر:

· 0 → auto (موصى به)
· 1 → serial (أبطأ بكثير، لكن أوضح للتشخيص)
· 8 → أسرع، لكن استهلاك ذاكرة أعلى

العلاقات:

· مع --no-parallel: if true، --workers يُتجاهل
· مع --nassets: 100 أصل → تحتاج 4+ عمال
· مع --no-numba: بدون numba، كل عامل يستخدم CPU أكثر

---

6.8 --no-cache و --clear-cache

ما يفعلهما:

· --no-cache: يعطّل asset_cache و market_data_cache (يعيد الحساب من الصفر)
· --clear-cache: يمسح الكاش قبل البدء

الأثر:

· بدون cache: أبطأ 2-5×
· مع cache: أسرع، لكن قد يستخدم بيانات قديمة

العلاقات:

· مع --end-date: إذا غيّرت --end-date، الـ cache يصبح غير صالح (يُعاد حسابه تلقائياً)
· مع --timeframe: تغيير TF = cache جديد

---

6.9 --no-parallel

ما يفعله: يعطّل ProcessPoolExecutor.

الأثر:

· Serial processing = أبطأ 4-8×
· مفيد للتشخيص أو debug

العلاقات:

· مع --workers: --workers يُتجاهل
· مع --no-numba: بدون numba + no-parallel = باكتيست بطيء جداً

---

المجموعة 7: التنفيذ (Execution)

7.1 --fill-mode {maker, taker, hybrid}

ما يفعله: نمط تنفيذ الدخول.

القيمة ما يحدث
maker Post-only GTX فقط (رسوم 0.02%)
taker Market order (رسوم 0.05%)
hybrid Maker أولاً، ثم Taker إذا فشل

القيمة الافتراضية: hybrid

الأثر:

· maker → رسوم أقل، لكن fill rate أقل (قد لا يُملأ)
· taker → مضمون، رسوم أعلى
· hybrid → توازن (الافتراضي)

العلاقات:

· مع --po-wait-s: maker/hybrid يستخدمان هذا الـ timeout
· مع --po-pen-bps: يحدد الاختراق
· مع --fill-target: يستخدمه AdaptiveFillEngine

ماذا يجب أن يتغير معه:

· --fill-mode maker → --po-wait-s 30-60 (وقت انتظار أطول)
· --fill-mode taker → --po-wait-s يُتجاهل

---

7.2 --fill-target FILL_TARGET

ما يفعله: نسبة الـ fill المستهدفة في AdaptiveFillEngine.

القيمة الافتراضية: 0.90 (90%)

الأثر:

· 0.95 → ينتظر أطول لملء (fill rate أعلى، لكن وقت أطول)
· 0.70 → يقبل fill جزئي (أسرع، لكن رسوم أعلى)

العلاقات:

· مع --fill-mode: يعمل فقط في hybrid أو maker
· مع --po-wait-s: يعمل معه

---

7.3 --no-fill-engine

ما يفعله: يعطّل AdaptiveFillEngine (يستخدم execute_post_only القديم).

الأثر:

· بدون fill engine: تنفيذ أبسط، لكن fill rate أقل
· مع fill engine: تنفيذ ذكي، fill rate أعلى، لكن أبطأ قليلاً

العلاقات:

· مع --fill-mode: --fill-mode يُتجاهل
· مع --fill-target: يُتجاهل

---

7.4 --po-pen-bps PO_PEN_BPS

ما يفعله: اختراق السعر بعد لمس (bps) لوضع أمر Post-Only.

القيمة الافتراضية: 1.0 (1 bps = 0.01%)

الأثر:

· 1.0 → أمر قريب جداً من السوق (قد يُرفض GTX)
· 5.0 → أمر أبعد (قد يُملأ، لكن سعر أسوأ)
· يُضاف إلى PO_USE_TICK_PENETRATION: إذا True، يستخدم max(pen_bps, 1 tick)

العلاقات:

· مع --po-wait-s: pen أصغر + wait أطول = fill أفضل
· مع --fill-target: pen أصغر + target أعلى = مقايضة

---

7.5 --po-wait-s PO_WAIT_S

ما يفعله: وقت انتظار Post-Only قبل الإلغاء.

القيمة الافتراضية: 30 (30 ثانية)

الأثر:

· 10 → أوامر تُلغى بسرعة (fill rate أقل)
· 60 → أوامر تنتظر أطول (fill rate أعلى، لكن وقت أطول)
· في الباكتيست: يُترجم إلى FILL_ENTRY_MAX_WAIT_BARS

العلاقات:

· مع --fill-mode: يعمل في maker/hybrid
· مع --po-pen-bps: مقايضة
· مع --maxcon: إذا --maxcon 10، --po-wait-s 60 = تراكم أوامر

---

7.6 --po-max-attempts PO_MAX_ATTEMPTS

ما يفعله: أقصى عدد محاولات إعادة التسعير قبل الإلغاء.

القيمة الافتراضية: 3

الأثر:

· 3 → 3 محاولات، ثم إلغاء
· 10 → انتظار أطول، fill rate أعلى

العلاقات:

· مع --po-wait-s: wait ÷ attempts = وقت كل محاولة
· مع --po-max-drift-bps: إذا drift > max, abort

---

7.7 --po-max-drift-bps PO_MAX_DRIFT_BPS

ما يفعله: أقصى انحراف سعري قبل الإلغاء.

القيمة الافتراضية: 5.0 (5 bps)

الأثر:

· 5.0 → يلغي إذا السعر انحرف 5 bps
· 20.0 → ينتظر أطول (fill rate أعلى، لكن قد يُملأ بسعر سيئ)

العلاقات:

· مع --po-pen-bps: إذا pen = 1 و drift = 5، الفرق كبير → إلغاء متكرر
· مع --po-wait-s: مع wait طويل، drift صغير = إلغاء سريع

---

7.8 --po-min-accept PO_MIN_ACCEPT

ما يفعله: أدنى نسبة fill مقبولة (partial fills).

القيمة الافتراضية: 0.50 (50%)

الأثر:

· 0.50 → يقبل 50%+ (fill أصغر مقبول)
· 0.90 → يقبل 90%+ فقط (fill كامل تقريباً)

العلاقات:

· مع --fill-mode: يعمل في hybrid
· مع --po-wait-s: wait أطول → fill أعلى → قبول أعلى

---

7.9 --no-pending

ما يفعله: يعطّل Non-Blocking Pending Orders (يستخدم التنفيذ المتزامن القديم).

الأثر:

· مع pending: تنفيذ غير متزامن، عدة أوامر معلقة
· بدون pending: تنفيذ متزامن (blocking)، أمر واحد في المرة

العلاقات:

· مع --fill-mode: --fill-mode يبقى يعمل
· مع --maxcon: بدون pending، --maxcon يُطبَّق بحذر

---

7.10 --no-smart-ohlcv

ما يفعله: يعطّل Smart OHLCV Fetch (الذي يجلب البيانات فقط عند إغلاق شمعة جديدة).

الأثر:

· مع smart: _needs_ohlcv_refresh يتحقق من tf_sec — يجلب فقط عند شمعة جديدة
· بدون smart: يجلب بيانات كل دورة (بطيء + rate limit)

العلاقات:

· مع --timeframe: tf_sec يحدد متى يجلب
· مع LIVE_POLL_SECS: بدون smart، rate limit ينفجر

⚠️ لا تستخدمه إلا للتشخيص.

---

المجموعة 8: الحماية والحدود

8.1 --heat-max HEAT_MAX

ما يفعله: ميزانية الحرارة القصوى (مجموع dynamic_risk لكل المراكز).

القيمة الافتراضية: 0.10 (10%)

الأثر:

· 0.10 → 10% إجمالي. مع --maxcon 3 = ~3.3% لكل صفقة
· 0.20 → 20% إجمالي. مع --maxcon 3 = ~6.7% لكل صفقة

العلاقات:

· مع --maxcon: risk_per_slot = heat / maxcon
· مع --max-risk: MAX_RISK سقف Kelly، heat/maxcon سقف Budget
· مع --capital: رأس مال صغير → heat أعلى قليلاً

ماذا يجب أن يتغير معه:

· --heat-max 0.20 → --maxcon 2-3 (تركيز)
· --heat-max 0.05 → --maxcon 5-10 (توزيع)

---

8.2 --no-budget

ما يفعله: يعطّل Portfolio Risk Budget (يستخدم المخاطرة الفردية فقط).

الأثر:

· بدون budget: sig.dynamic_risk يُستخدم مباشرة (قد يصل 5%)
· مع budget: heat و maxcon و strength معاً (أكثر تحفظاً)

العلاقات:

· مع --heat-max: --heat-max يُتجاهل
· مع --maxcon: --maxcon لا يحدّ المخاطرة (بل فقط عدد المراكز)

⚠️ خطر: بدون budget، المخاطرة الإجمالية قد تصل 50% (5% × 10 مراكز). لا تستخدمه إلا إذا كنت تعرف ما تفعل.

---

8.3 --max-notional MAX_NOTIONAL

ما يفعله: سقف قيمة المركز بالدولار.

القيمة الافتراضية: 100_000

الأثر:

· 100_000 → سقف عالٍ (لا يقطر معظم الصفقات)
· 5_000 → سقف منخفض (يقطع الصفقات الكبيرة)

العلاقات:

· مع --capital: $1 → --max-notional 5. $10,000 → --max-notional 20,000
· مع --leverage: qty × price قد يصل إلى capital × leverage. --max-notional يقطع أعلى
· مع --nassets: أصول قليلة السيولة → --max-notional أصغر

ماذا يجب أن يتغير معه:

· --capital 1 → --max-notional 5
· --capital 100 → --max-notional 500-1000
· --capital 10000 → --max-notional 20000-50000

---

8.4 --no-kill-switch

ما يفعله: يعطّل Kill Switch (لا يتحقق من kill_switch.json).

الأثر:

· بدون kill switch: لا يمكن إيقاف البوت إلا بـ Ctrl+C أو SIGTERM
· مع kill switch: يمكن إيقافه عن بُعد عبر ملف HMAC

العلاقات:

· مع --kill-secret: بدون --kill-secret، kill switch لا يعمل (يُتجاهل)
· مع --no-kill-switch: --kill-secret يُتجاهل

---

8.5 --kill-secret KILL_SECRET

ما يفعله: HMAC secret للتحقق من kill_switch.json.

القيمة الافتراضية: "" (لا شيء)

الأثر:

· بدون secret: kill switch لا يعمل
· مع secret: يمكن إيقاف البوت بكتابة ملف JSON صحيح

العلاقات:

· مع --no-kill-switch: --no-kill-switch يُعطّل التحقق

---

المجموعة 9: Trailing Stop Loss

9.1 --no-dynamic-trail

ما يفعله: يعطّل TRAIL_DYNAMIC (يستخدم TRAIL_DISTANCE الثابت بدلاً من σ × TRAIL_KAPPA).

الأثر:

· ديناميكي (default): trail_d = clip(TRAIL_KAPPA × σ, min, max). على 4h, TRAIL_KAPPA = 0.30 → 0.273% → clip إلى 0.40%.
· ثابت: trail_d = TRAIL_DISTANCE = 0.30%. أضيق.

العلاقات:

· مع --trail-kappa: في الديناميكي، TRAIL_KAPPA × σ. في الثابت، TRAIL_KAPPA يُتجاهل.
· مع --timeframe: 4h يحتاج min_d = 0.40%. الثابت 0.30% أضيق.

ماذا يجب أن يتغير معه:

· --no-dynamic-trail → --trailing قد تكون كافية (SL = 0.30% fixed)
· ملاحظة من تجربتك: --no-dynamic-trail أعطى أفضل النتائج! هذا مقصود — التريل الثابت أضيق، يحمي الأرباح أسرع.

---

9.2 --no-trailing

ما يفعله: يعطّل Trailing كلياً. SL يبقى ثابتاً عند مستواه الأصلي.

الأثر:

· بدون trailing: SL لا يتحرك بعد الدخول
· مع trailing: SL يرتفع مع Peak (BUY) أو ينخفض (SELL)

العلاقات:

· مع --breakeven: إذا --no-trailing، --breakeven يبقى يعمل (عند +1R)
· مع --partial-tp: Partial TP يعمل بغض النظر

ماذا يجب أن يتغير معه:

· --no-trailing → قد تحتاج --breakeven مفعّلاً (لحماية الأرباح)
· --no-trailing → قد تحتاج --be-escape مفعّلاً (للهروب إلى entry)

---

9.3 --trailing

ما يفعله: يفرض تفعيل Trailing (يتجاوز CFG.TRAIL_ENABLED = False).

الأثر:

· مفيد إذا كنت تريد --trailing بعد تعديل يدوي على Config

العلاقات:

· مع --no-trailing: --no-trailing يأخذ الأولوية (يُعطّل)

---

9.4 --trail-kappa TRAIL_KAPPA

ما يفعله: مضاعف σ في Trailing الديناميكي.

القيمة الافتراضية: 1.5 (في الـ flag)، لكن Config يضع 0.30

الأثر:

· على 4h مع σ = 0.91%:
  · TRAIL_KAPPA = 0.30 → 0.273% → clip إلى min_d = 0.40%
  · TRAIL_KAPPA = 1.5 → 1.365% → clip إلى min_d = 1.365%
  · TRAIL_KAPPA = 2.0 → 1.82% → clip إلى max_d = 1.6% → 1.6%
· أعلى → SL أوسع، حماية أقل، أرباح أكثر
· أقل → SL أضيق، حماية أكثر، أرباح أقل

العلاقات:

· مع --no-dynamic-trail: --trail-kappa يُتجاهل (يستخدم TRAIL_DISTANCE)
· مع --trail-dynamic: يعمل فقط في الديناميكي
· مع --timeframe: 4h يحتاج TRAIL_KAPPA أعلى من 1h (لأن σ_4h ≈ 4 × σ_1h)

ماذا يجب أن يتغير معه:

· --trail-kappa 1.5 → لا حاجة لتغيير --trail-activate-mfe
· --trail-kappa 0.3 → قد تحتاج --trail-activate-mfe أعلى (لتجنب تفعيل مبكر)

---

المجموعة 10: Re-entry & Cooldown

10.1 --reentry-cooldown REENTRY_COOLDOWN

ما يفعله: عدد الشموع للانتظار بعد الخروج قبل إعادة الدخول على نفس الرمز.

القيمة الافتراضية: 3 شموع

الأثر:

· 3 → انتظار 3 شموع × 4h = 12 ساعة
· 6 → 24 ساعة (أكثر تحفظاً)
· 0 → دخول فوري (خطر whipsaw)

العلاقات:

· مع --no-reentry-cooldown: يُعطّل
· مع --timeframe: 4h × 3 = 12 ساعة. 1h × 3 = 3 ساعات.
· مع --maxcon: cooldown طويل → فرص أقل

ماذا يجب أن يتغير معه:

· --reentry-cooldown 6 → قد تحتاج --maxcon أعلى (فرص أقل لكل رمز)
· --reentry-cooldown 0 → قد تحتاج --no-reentry-cooldown بدلاً منه

---

10.2 --no-reentry-cooldown

ما يفعله: يعطّل cooldown تماماً (دخول فوري بعد الخروج).

⚠️ خطر: قد يؤدي إلى whipsaw (دخول بعد خروج مباشرة بنفس الاتجاه).

العلاقات:

· مع --reentry-cooldown: --no-reentry-cooldown يُعطّل

---

المجموعة 11: Reversal-Confirm (نظام فرعي متقدم)

هذه المجموعة تتحكم في نظام "Touch-and-Bounce" الذي يختلف عن النظام الأساسي. معطّل افتراضياً.

11.1 --reversal-confirm

ما يفعله: يفعّل REVERSAL_CONFIRM_ENABLED = True. يفعّل نظام Touch-and-Bounce بدلاً من Entry Limit التقليدي.

الأثر:

· بديل للـ Entry Limit: ينتظر "لمس" السعر لـ tunnel، ثم "ارتداد" بـ sub-bars
· بديل للـ Pending Orders: يستخدم _REVERSAL_WATCHERS بدلاً من _PENDING_ORDERS

العلاقات:

· مع --reversal-touch-subbars: تحدد مرحلة Touch
· مع --reversal-bounce-subbars: تحدد مرحلة Bounce
· مع --reversal-mode: يحدد شكل التأكيد
· ⚠️ لا يعمل مع --watch: WATCH_REMOVED = True

⚠️ تحذير: هذا نظام كامل بديل، يحتاج اختبار مستقل.

---

11.2 --reversal-touch-subbars REVERSAL_TOUCH_SUBBARS

ما يفعله: أقصى عدد sub-bars لانتظار لمس الهدف.

القيمة الافتراضية: 20 (20 × 15m = 5 ساعات على 4h)

العلاقات:

· مع --reversal-bounce-subbars: مجموع = مدة النظام
· مع --reversal-mode: يعمل معه

---

11.3 --reversal-bounce-subbars REVERSAL_BOUNCE_SUBBARS

ما يفعله: أقصى عدد sub-bars بعد اللمس لتأكيد الارتداد.

القيمة الافتراضية: 4 (4 × 15m = ساعة)

---

11.4 --reversal-max-hours REVERSAL_MAX_HOURS

ما يفعله: عمر الإشارة قبل إلغائها (بالساعات).

القيمة الافتراضية: 24

---

11.5 --reversal-mode {close_back, two_bar, sigma_bounce, bar_color}

ما يفعله: شكل التأكيد:

· close_back: close يعبر الـ target
· two_bar: شمعتان consecutive
· sigma_bounce: close > target + κ × σ_bar
· bar_color: close > close السابق

---

11.6 --reversal-kappa REVERSAL_KAPPA

ما يفعله: κ في sigma_bounce mode.

القيمة الافتراضية: 0.20 (20% من σ_bar)

---

11.7 --reversal-fill {target, close, best}

ما يفعله: مصدر سعر الـ fill:

· target: سعر الـ tunnel (المُحسوب)
· close: سعر الـ close للـ sub-bar
· best: أفضل سعر متاح

---

المجموعة 12: BEEsc (Breakeven Escape)

12.1 --be-escape

ما يفعله: يفعّل BEEsc (TP يتحرك إلى entry عند انعكاس).

الأثر:

· مع BEEsc: TP → entry عند 0.30R حركة عكسية
· بدون BEEsc: TP ثابت عند 2.5R

العلاقات:

· مع --be-escape-move-r: عتبة التفعيل
· مع --be-escape-cancel-kappa: إلغاء BEEsc
· مع --no-be-escape: معطّل

---

12.2 --no-be-escape

ما يفعله: يعطّل BEEsc.

العلاقات:

· مع --be-escape: --no-be-escape يأخذ الأولوية

---

12.3 --be-escape-move-r BE_ESCAPE_MOVE_R

ما يفعله: عتبة الحركة العكسية (بوحدات R).

القيمة الافتراضية: 0.30 (30% من SL)

الأثر:

· 0.30 → BEEsc يتفعّل عند -0.30R
· 0.20 → يتفعّل أسرع (حماية أسرع، لكن يقطع الصفقات في الضجيج)
· 0.50 → يتفعّل أبطأ (ينتظر حركة كبيرة ضدنا)

العلاقات:

· مع --be-escape-min-profit-r: --be-escape-min-profit-r يحدد أين يوضع TP الجديد
· مع --no-be-escape-ema: بدون EMA، يتفعّل بسرعة
· مع --be-escape-cancel-kappa: إذا ارتد بقوة، قد يُلغى

---

12.4 --be-escape-min-profit-r BE_ESCAPE_MIN_PROFIT_R

ما يفعله: الربح المضمون عند الخروج (بوحدات R).

القيمة الافتراضية: 0.0 (تعادل تام)

الأثر:

· 0.0 → TP = entry (تعادل)
· 0.1 → TP = entry + 0.1 × sl_dist (ربح صغير)
· -0.2 → TP = entry - 0.2 × sl_dist (خسارة صغيرة)

العلاقات:

· مع --be-escape-move-r: move-r = متى يتفعّل، min-profit-r = أين يذهب TP

---

12.5 --be-escape-ema-lookback BE_ESCAPE_EMA_LOOKBACK

ما يفعله: عدد شموع EMA-200 لمقارنة الميل.

القيمة الافتراضية: 50 (50 شمعة)

الأثر:

· 50 على 4h = 200 ساعة = 8.3 أيام. بطيء.
· 25 على 4h = 100 ساعة = 4.2 أيام. أسرع.
· 100 = 16.6 أيام. أبطأ.

---

12.6 --no-be-escape-ema

ما يفعله: يعطّل شرط EMA-flip (BEEsc يتفعّل على السعر فقط).

الأثر:

· بدون EMA: BEEsc يتفعّل عند 0.30R حركة فقط
· مع EMA: BEEsc يتفعّل عند 0.30R + EMA flip

الأثر العملي: بدون EMA، BEEsc يتفعّل أكثر.

---

12.7 --be-escape-cancel-kappa BE_ESCAPE_CANCEL_KAPPA

ما يفعله: عتبة إلغاء BEEsc إذا ارتد السعر.

القيمة الافتراضية: 0.0 (معطّل)

الأثر:

· 0.0 → BEEsc لا يُلغى (السلوك الأصلي)
· 0.5 → BEEsc يُلغى إذا ارتد السعر بـ 0.5σ من القاع
· 1.0 → BEEsc يُلغى إذا ارتد بـ 1σ (أكثر تحفظاً)

العلاقات:

· مع --be-cancel-close-only: يستخدم close بدل wick/ticker
· مع --be-cancel-sr-check: يفلتر أكثر

---

12.8 --no-apex-parity

ما يفعله: يعطّل إصلاح Apex/Topo-Div parity.

الأثر:

· بدون parity: Apex/Topo-Div يخرج كـ GTX (قد لا يُملأ في live)
· مع parity: Apex/Topo-Div يخرج كـ taker في backtest و marketable في live

⚠️ لا تعطّله — قد تعلق في live.

---

المجموعة 13: الفلاتر (Filters)

13.1 --ml-filter

ما يفعله: يفعّل ML_FILTER_ENABLED = True (فلتر ML).

الأثر:

· مع ML: يحمّل نموذج من --ml-model، يفلتر الإشارات
· بدون ML: لا فلترة

العلاقات:

· مع --ml-model: إذا لم يوجد الملف، الفلتر يُعطَّل
· مع --ml-threshold: عتبة القبول

---

13.2 --ml-model ML_MODEL

ما يفعله: مسار النموذج المُدرَّب.

القيمة الافتراضية: ml_filter.pkl

---

13.3 --ml-threshold ML_THRESHOLD

ما يفعله: عتبة p_win للقبول.

القيمة الافتراضية: 0.45

الأثر:

· 0.45 → يقبل 45%+ (معتدل)
· 0.55 → صارم (قليل من الإشارات)

---

13.4 --rule-filter

ما يفعله: يفعّل RULE_FILTER_ENABLED = True (فلتر Rule-Based بدون ML).

الأثر: 4 قواعد (rvol24, dist_high, tf_std, range_pos). يرفض إذا 3+ تحققت.

العلاقات:

· مع --rule-min-score: عدد القواعد المطلوبة للرفض
· مع --filter: يعملان معاً (فلتران مستقلان)

---

13.5 --rule-min-score RULE_MIN_SCORE

ما يفعله: عدد القواعد المطلوبة للرفض (من 4).

القيمة الافتراضية: 2

الأثر:

· 2 → يرفض إذا 2+ تحققت (معتدل)
· 3 → يرفض إذا 3+ تحققت (صارم)
· 4 → يرفض فقط إذا 4 (نادراً)

---

13.6 --filter

ما يفعله: يفعّل FILTER_ENABLED = True (فلتر Trade Filter).

الأثر: يحسب أصوات رفض (ema_slope, high_atr, friction). يرفض إذا >= filter_min_votes.

العلاقات:

· مع --filter-min-votes: عدد الأصوات المطلوبة
· مع --filter-no-ema, --filter-no-atr, --filter-no-friction: تعطيل أصوات فردية

---

13.7 --filter-min-votes FILTER_MIN_VOTES

ما يفعله: الحد الأدنى للأصوات للرفض.

القيمة الافتراضية: 2

---

13.8 --filter-atr-max FILTER_ATR_MAX

ما يفعله: عتبة atr_frac للرفض.

القيمة الافتراضية: 0.024 (2.4%)

---

13.9 --filter-friction-max FILTER_FRICTION_MAX

ما يفعله: عتبة friction_drag / sl_dist للرفض.

القيمة الافتراضية: 2.5

---

13.10 --gauge-filter

ما يفعله: يفعّل GAUGE_FILTER_ENABLED = True (فلتر Gauge Force).

الأثر: BUY يحتاج gauge > p60، SELL يحتاج gauge > p95.

العلاقات:

· مع --gauge-buy-pct: عتبة BUY
· مع --gauge-sell-pct: عتبة SELL

---

13.11 --gauge-buy-pct GAUGE_BUY_PCT

ما يفعله: عتبة Gauge للـ BUY.

القيمة الافتراضية: 0.60 (60th percentile)

الأثر: أعلى → فلترة أكثر.

---

13.12 --gauge-sell-pct GAUGE_SELL_PCT

ما يفعله: عتبة Gauge للـ SELL.

القيمة الافتراضية: 0.85 (85th percentile) — لكن SELL معطّل افتراضياً

---

13.13 --gauge-disable-sell

ما يفعله: يعطّل SELL.

⚠️ DEPRECATED: SELL معطّل افتراضياً بواسطة GAUGE_DISABLE_SELL = True.

---

13.14 --sr-filter

ما يفعله: يفعّل SR_FILTER_ENABLED = True (فلتر S/R).

الأثر: يرفض الإشارات التي ليس لها S/R بين الدخول والـ SL.

العلاقات:

· مع --sr-strength: عتبة قوة S/R
· مع --sr-proximity: أقصى مسافة بين SL و S/R

---

13.15 --sr-strength SR_STRENGTH

ما يفعله: عتبة قوة S/R (touches × decay × volume).

القيمة الافتراضية: 1.0

---

13.16 --sr-proximity SR_PROXIMITY

ما يفعله: أقصى نسبة بين SL و S/R.

القيمة الافتراضية: 0.006 (0.6%)

---

المجموعة 14: SELL

14.1 --sell-only

ما يفعله: يفعّل SELL_ONLY = True (يرفض BUY).

العلاقات:

· مع --enable-sell: لا يتعارضان. --sell-only يرفض BUY، --enable-sell يفعّل SELL.

---

14.2 --enable-sell

ما يفعله: يفعّل SELL (يتجاوز GAUGE_DISABLE_SELL = True).

الأثر: SELL إشارات تبدأ تظهر.

العلاقات:

· مع --sell-gauge-pct: عتبة gauge للـ SELL
· مع --sell-min-score: score أدنى للـ SELL
· مع --sell-min-zdev: z-dev أدنى للـ SELL

---

14.3 --sell-min-score SELL_MIN_SCORE

القيمة الافتراضية: 3

14.4 --sell-min-zdev SELL_MIN_ZDEV

القيمة الافتراضية: 1.5

14.5 --sell-gauge-pct SELL_GAUGE_PCT

القيمة الافتراضية: 0.95

14.6 --sell-require-ema-down

ما يفعله: يشترط EMA-200 هابط للـ SELL.

14.7 --sell-major-only

ما يفعله: يقصر SELL على BTC/ETH/SOL/BNB.

14.8 --sell-min-atr-frac SELL_MIN_ATR_FRAC

ما يفعله: أدنى تقلب للـ SELL.

---

المجموعة 15: Overrides

15.1 --tp-mult TP_MULT

ما يفعله: يضاعف TP_MULT (R:R ratio).

القيمة الافتراضية: 2.5 (لكن Config يضع 5.0)

الأثر:

· 2.5 → TP على +2.5R
· 5.0 → TP على +5R (نادراً ما يتحقق)
· 7.0 → TP على +7R (نادر جداً)

العلاقات:

· مع --partial-tp-r: --partial-tp-r يجب أن يكون < --tp-mult
· مع --sl-widen-mult: TP يُوسَّع بنفس النسبة

---

15.2 --partial-tp-r PARTIAL_TP_R

ما يفعله: عتبة Partial TP (بيع 50% عند +R).

القيمة الافتراضية: 1.5

الأثر:

· 1.5 → partial at +1.5R
· 3.0 → partial at +3R (أبعد)

العلاقات:

· مع --tp-mult: --partial-tp-r < --tp-mult
· مع --be-escape: partial قد يحدث قبل BEEsc

---

15.3 --sl-widen-mult SL_WIDEN_MULT

ما يفعله: يضاعف مسافة SL.

القيمة الافتراضية: 1.5

الأثر:

· 1.0 → SL على 1.5% × 1.0 = 1.5%
· 2.5 → SL على 1.5% × 2.5 = 3.75% (أوسع)
· 0.8 → SL على 1.5% × 0.8 = 1.2% (أضيق، لكن قد يُقص إلى 1.5%)

العلاقات:

· مع --tp-mult: كلما وسّعت SL، يمكنك توسيع TP
· مع --leverage: SL أوسع → Liq أبعد → يمكنك رافعة أعلى
· مع --max-risk: SL أوسع → qty أقل → مخاطرة أقل

ماذا يجب أن يتغير معه:

· --sl-widen-mult 2.5 → --tp-mult 2.5 (R:R = 1.0)
· --sl-widen-mult 3.0 → --leverage 10-20 (SL أوسع، رافعة أقل)

---

المجموعة 16: Adaptive TP

16.1 --opp-tp

ما يفعله: يفعّل OPP_TP_ENABLED = True (نقل TP عند إشارة معاكسة).

الأثر: إذا ظهرت إشارة معاكسة قوية، TP الحالي ينتقل إلى tunnel_entry_p للإشارة المعاكسة.

العلاقات:

· مع --opp-tp-score-mult: قوة الإشارة المعاكسة
· مع --opp-tp-min-profit-r: ربح مضمون

---

16.2 --opp-tp-score-mult OPP_TP_SCORE_MULT

القيمة الافتراضية: 1.20

16.3 --opp-tp-min-profit-r OPP_TP_MIN_PROFIT_R

القيمة الافتراضية: 0.5

16.4 --opp-tp-min-delta-r OPP_TP_MIN_DELTA_R

القيمة الافتراضية: 0.3

16.5 --opp-tp-max-age-bars OPP_TP_MAX_AGE_BARS

القيمة الافتراضية: 4

---

المجموعة 17: MFAL (Multi-Factor Adaptive Leverage)

17.1 --mfal

ما يفعله: يفعّل _MFAL_ENABLED = True (رافعة تكيفية متعددة العوامل).

الأثر: L = L_core × Q × R × T × M.

العلاقات:

· مع --mfal-no-micro: يعطّل عامل M
· مع --mfal-no-time: يعطّل عامل T
· مع --mfal-no-learn: يعطّل التعلم
· مع --mfal-weights: مسار الأوزان

---

17.2 --mfal-no-micro / --mfal-no-time / --mfal-no-learn

ما يفعلهما: تعطيل عوامل MFAL الفردية.

17.3 --mfal-weights MFAL_WEIGHTS

ما يفعله: مسار ملف الأوزان JSON.

---

المجموعة 18: أدوات التطوير

18.1 --trade-log TRADE_LOG

ما يفعله: مسار ملف trades_log.jsonl.

القيمة الافتراضية: trades_log_{mode}.jsonl

18.2 --sing-timing / --sing-active / --sing-funding-guard / --sing-risk-boost

ما يفعلهما: تفعيل طبقات Singularity (تحتاج --sing-timing كأساس).

⚠️ معطّلة افتراضياً — نظام متقدم يحتاج اختبار مستقل.

---

🎯 جدول العلاقات الحرجة (يجب أن تتذكرها)

إذا غيّرت... يجب أن تغيّر معه... السبب
--capital --max-risk, --maxcon, --leverage, --max-notional حجم رأس المال يحدد المخاطرة/الرافعة
--timeframe --history-days, --sl-widen-mult, --maxcon, --k-max كل TF له مقاييسه
--max-risk --maxcon, --heat-max مجموع المخاطرة محدود
--leverage --sl-widen-mult, --max-notional Liq + Notional
--sl-widen-mult --tp-mult, --max-risk, --leverage R:R + Risk
--tp-mult --partial-tp-r, --sl-widen-mult Partial < TP
--partial-tp-r --tp-mult Partial < TP
--heat-max --maxcon, --max-risk risk_per_slot = heat/maxcon
--maxcon --heat-max, --max-risk, --workers التوزيع
--history-days --k-max, --timeframe البيانات تحدد K
--k-max --history-days K يحتاج بيانات كافية
--nassets --maxcon, --workers عدد الأصول
--be-escape-move-r --be-escape-min-profit-r, --be-escape-cancel-kappa BEEsc thresholds
--fill-mode --po-wait-s, --po-pen-bps, --fill-target Execution
--trail-kappa --trail-activate-at-r Trailing thresholds
--mode live --api-key, --api-secret, --max-notional المصادقة + السيولة

---

🏆 5 خلاصات ذهبية

1. --capital هو المتحكم الأول — كل شيء آخر يتغير معه
2. --timeframe يحتاج إعادة معايرة كاملة — لا تفترض أن إعدادات 4h تعمل على 1h
3. --max-risk و --maxcon و --heat-max — ثلاثية مترابطة لا تنفصل
4. --leverage و --sl-widen-mult — كل زيادة في الرافعة تحتاج SL أضيق
5. --mode live يضيف قيوداً — --max-notional للسيولة، --api-key للمصادقة

---

هل تريد أن أشرح أي مجموعة بتفصيل أعمق، أو أن أعطيك قيم موصى بها لأوامر تشغيل محددة (مثل: micro-capital، أو high-risk، أو conservative)؟ 😊
