# وثيقة إعادة إنشاء المحرك الثرموديناميكي الكمي v6.1

> **الغرض:** وثيقة رياضية-فيزيائية-برمجية كاملة تُمكّن خبيراً واحداً (رياضيات + فيزياء + برمجة + خوارزميات) من إعادة بناء المحرك من الصفر.
>
> **الفلسفة الحاكمة:** السوق نظام فيزيائي مفتوح، يُمثَّل برمزية رمزية-انتروبية، ويُقاس بحقل مقياس ناشئ، وتُتحَّذ القرارات عبر معادلة جيوديسية.

---

## الجزء الأول — الأسس النظرية

### 1.1 الفرضية الفيزيائية الأساسية

نمثّل السوق الفيزيائي كفضاء طوري رمزي ذي 7 أبعاد:

$$\mathcal{M} = \{x_i \in \mathbb{R}^7\}_{i=1}^{n}$$

حيث كل نقطة $x_i$ هي متجهة ميزات مستخرجة من نافذة منزلقة على بيانات OHLCV.

**المبدأ الأول (الانتروبيا الإنتروبية):** النظام الرمزي يمتلك إنتروبيا $H(t)$ تتغير مع الزمن. الانخفاض في $H$ يعني أن السوق ينتقل من نظام فوضوي إلى نظام مهيكل — وهذه إشارة على اقتراب حركة اتجاهية.

**المبدأ الثاني (الاحتكاك الإنتروبي):** لكل نقطة إنتروبيا $H$ يقابلها احتكاك $\Gamma(H)$ يعيق الحركة في الفضاء الطوري. الاحتكاك يتبع قانوناً أسّياً معكوساً.

**المبدأ الثالث (القوة الجيوديسية):** الحركة الفعلية في الفضاء الطوري تتبع معادلة جيوديسية مضغوطة بثلاث قوى:
$$\ddot{x} = -\nabla F + q \cdot F_{\text{gauge}} \cdot \dot{x} - \Gamma \cdot \dot{x}$$

**المبدأ الرابع (المقياس الناشئ):** من مصفوفة الانتقال $T$ بين الرموز، يظهر حقل مقياس $F_{\text{gauge}}$ يقيس درجة عدم التناظرية في الحركة الرمزية.

### 1.2 معادلات الحركة في الفضاء الطوري

| الرمز | المعنى | الوحدة |
|---|---|---|
| $x$ | نقطة في $\mathbb{R}^7$ | متجهة |
| $t$ | الزمن | الشمعة |
| $\nabla F$ | تدرّج الطاقة الحرة | طاقة/بعد |
| $F_{\text{gauge}}$ | حقل المقياس | عديم البعد |
| $\Gamma$ | الاحتكاك الإنتروبي | 1/بعد |
| $q$ | شحنة لورنتز | عديم البعد |
| $H$ | إنتروبيا شانون | بت |
| $\lambda$ | الأسّي ليابونوف | 1/شمعة |

---

## الجزء الثاني — استخراج الرموز (Feature Extraction)

### 2.1 استخراج الميزات الأساسية

لكل نافذة $i \in [N, n)$، تُحسب المتجهة $v_i \in \mathbb{R}^7$:

$$
v_i = \begin{bmatrix}
\mu_r \\ \sigma_r \\ s_r \\ k_r \\ R_p \\ \bar{v} \\ r_{N}
\end{bmatrix}
$$

حيث:
- $r_j = \ln(c_j / c_{j-1})$: عوائد لوغاريتمية
- $\mu_r = \frac{1}{N}\sum_{j=i-N+1}^{i} r_j$: متوسط
- $\sigma_r = \sqrt{\frac{1}{N-1}\sum (r_j - \mu_r)^2}$: انحراف معياري
- $s_r$: التواء (skewness, bias=False)
- $k_r$: تفرطح (kurtosis, bias=False)
- $R_p = \max(p) - \min(p)$: مدى السعر
- $\bar{v}$: متوسط الحجم
- $r_N = (c_i - c_{i-N})/c_{i-N}$: العائد الكلي

**التطبيع:** إذا كان $\|v_i\|_2 > 1$، نُطبّع $v_i \leftarrow v_i/\|v_i\|_2$.

### 2.2 تكميم KMeans الديناميكي

نُدرّب KMeans على الجزء التدريبي $X_{train} = \{v_i\}_{i=N}^{N+T}$ حيث $T = \lfloor 0.5 n \rfloor$، مع عدد المجموعات الديناميكي:

$$K = \min\left(K_{\max}, \left\lfloor \frac{T}{P_{\min}} \right\rfloor, \left\lfloor K_{\max} \cdot e^{-\alpha \cdot C/\text{ADV}} \right\rfloor\right)$$

حيث:
- $K_{\max} = 12$: الحد الأقصى
- $K_{\min} = 4$: الحد الأدنى
- $P_{\min} = 100$: أقل عدد نقاط لكل مجموعة
- $C$: رأس المال الحالي
- $\text{ADV}$: متوسط حجم التداول اليومي
- $\alpha = 100$: ثابت التكميم

**النتيجة:** كل نقطة $v_i$ تُعيَّن إلى رمز $q_i \in \{0, 1, \ldots, K-1\}$.

### 2.3 فحص الانحطاط الرمزي

قبل المتابعة، نحسب الإنتروبيا التدريبية:

$$\bar{H}_{train} = \frac{1}{T}\sum_{i=1}^{T} H_i$$

حيث $H_i$ إنتروبيا شانون على نافذة $W$ (معرّفة أدناه). إذا:

$$\frac{\bar{H}_{train}}{\log_2 K} < 0.25$$

نرفض الأصل (clustering متدهور، الإشارات لا معنى لها).

---

## الجزء الثالث — الإنتروبيا والاحتكاك

### 3.1 إنتروبيا شانون المنزلقة

على تسلسل الرموز $\{q_i\}$، لكل نافذة $W = 20$:

$$H(t) = -\sum_{k=0}^{K-1} p_k(t) \log_2 p_k(t)$$

حيث $p_k(t) = \frac{1}{W} \sum_{j=t-W+1}^{t} \mathbb{1}[q_j = k]$.

**المشتقات:**
$$\dot{H}(t) = H(t) - H(t-1)$$
$$\ddot{H}(t) = \dot{H}(t) - \dot{H}(t-1)$$

### 3.2 الاحتكاك الإنتروبي

$$\Gamma(H) = \gamma_0 + \kappa \cdot \exp\left(\xi \cdot \left(1 - \frac{H}{H_{\max}}\right)\right)$$

حيث:
- $H_{\max} = \log_2 K$: الإنتروبيا القصوى
- $\gamma_0 = 0.01$: الاحتكاك الأدنى
- $\kappa = 0.1$: معامل التضخيم
- $\xi = 1.0$: الأسّي

**التفسير:** كلما انخفضت $H$ (نظام مهيكل)، ارتفع $\Gamma$ (احتكاك أكبر).

### 3.3 حقل المقياس الناشئ

لكل نافذة $W$، نبني مصفوفة الانتقال الرمزية $T \in \mathbb{R}^{K \times K}$:

$$T_{ab} = \frac{N_{ab}}{\sum_{a',b'} N_{a'b'}}$$

حيث $N_{ab}$ عدد الانتقالات من الرمز $a$ إلى $b$ في النافذة.

**حقل المقياس (Frobenius norm):**
$$F_{\text{gauge}}(t) = \|T - T^T\|_F = \sqrt{\sum_{a,b} (T_{ab} - T_{ba})^2}$$

**فجوة التوازن:**
$$\Delta(t) = \max_k |p_k(t) - 1/K|$$

### 3.4 الطاقة الحرارية والطاقة الحرة

**الطاقة الحركية الحرارية:**
$$E_{\text{therm}}(t) = \sigma_r(t) = \text{std}\left(\{r_j\}_{j=t-N+1}^{t}\right)$$

**الطاقة الحرة:**
$$F(t) = E_{\text{therm}}(t) - H(t)$$

**تدرّج الطاقة الحرة:**
$$\nabla F(t) = \dot{F}(t) = F(t) - F(t-1)$$

**درجة الحرارة المعلوماتية:**
$$T_{\text{info}}(t) = \left|\frac{\dot{F}}{\dot{H} + \varepsilon}\right| + 400 \cdot E_{\text{therm}}$$

ثم نُقيّد: $T_{\text{info}} \leftarrow \text{clip}(T_{\text{info}}, 0.5, 20)$.

---

## الجزء الرابع — المعادلة الجيوديسية

### 4.1 المعادلة الأساسية للحركة

$$\boxed{\;a(t) = -\nabla F(t) + q \cdot F_{\text{gauge}}(t) \cdot \dot{H}(t) - \Gamma(H) \cdot \dot{H}(t)\;}$$

هذا **التسارع الجيوديسي** $a(t)$. كل حدّ له تفسير فيزيائي:

| الحد | الاسم | الدور |
|---|---|---|
| $-\nabla F$ | قوة الطاقة الحرة | تدفع نحو انخفاض الطاقة |
| $+q F_{\text{gauge}} \dot{H}$ | قوة لورنتز | تحرف المسار حسب حقل المقياس |
| $-\Gamma \dot{H}$ | مقاومة الاحتكاك | تكبح الحركة |

### 4.2 قوة لورنتز

في الأصل، قوة لورنتز $\mathbf{F} = q(\mathbf{v} \times \mathbf{B})$. هنا نستبدل:
- $\mathbf{v} \to \dot{H}$
- $\mathbf{B} \to F_{\text{gauge}}$
- الجداء الاتجاهي يُستبدل بالجداء العددي (تقريب 1D)

### 4.3 الطاقة الكلية

$$E_{\text{kin}}(t) = \frac{1}{2}\sigma_r^2 \quad \text{(الطاقة الحركية)}$$
$$E_{\text{pot}}(t) = \|v - \mu_{\text{cluster}}\| \cdot \left(1 - \frac{H}{H_{\max}}\right) \quad \text{(الطاقة الكامنة)}$$
$$E_{\text{mech}} = E_{\text{kin}} + E_{\text{pot}}$$

### 4.4 أُسّي ليابونوف

لكل نقطة $t$ في النافذة $[t-60, t]$، نحسب:

$$\lambda(t) = \frac{1}{s}\left\langle \ln\frac{\|x_{j+s} - x_{j'+s}\|}{\|x_j - x_{j'}\|}\right\rangle_{j, j'}$$

حيث $j'$ هو أقرب جار لـ $j$ بشرط $|j - j'| > 10$، و $s = 5$ خطوات.

**التفسير:** $\lambda > 0$ يعني فوضى، $\lambda < 0$ يعني استقرار.

---

## الجزء الخامس — بناء النقاط

### 5.1 درجات القوة (Score)

$$S(t) = 10|a(t)| + W_{\text{curv}} \mathbb{1}[C > \epsilon] + W_{\text{vol}} \mathbb{1}[V < V_{q20}] + W_{\text{ent}} \mathbb{1}[\dot{H} < \epsilon_H \wedge \ddot{H} < 0] + W_{\text{HMM}} \mathbb{1}[h = 2 \vee (h=0 \wedge \dot{H} < -\epsilon_H)] + W_{\text{free}} \mathbb{1}[\dot{F} < \epsilon_F]$$

حيث:
- $C$: تقوّس المسار (متوسط سالب لمسافات الخطوات)
- $V$: محدد مصفوفة التغاير (حجم عدم اليقين)
- $V_{q20}$: المئين 20 لـ $V$ على الجزء التدريبي
- $h \in \{0, 1, 2\}$: حالة HMM (state 2 = انخفاض إنتروبيا)

**الأوزان:**
$$W_{\text{curv}} = 1, \; W_{\text{vol}} = 1, \; W_{\text{ent}} = 2, \; W_{\text{HMM}} = 2, \; W_{\text{free}} = 1$$

**العتبات:**
$$\epsilon_H = 0.005, \; \epsilon_F = -0.01, \; \epsilon_{\text{curv}} = 0.01$$

### 5.2 التقوّس والتغاير

$$C(s) = -\frac{1}{L}\sum_{j=1}^{L} \|x_{s+j} - x_{s+j-1}\|_2$$

$$V(s) = \det\left(\Sigma(s) + \varepsilon I\right)$$

حيث $\Sigma$ مصفوفة تغاير على نافذة $L = 10$.

### 5.3 الطاقة الكامنة

$$\text{PE}(t) = \|x_t - \mu_{q_t}\| \cdot \left(1 - \frac{H}{H_{\max}}\right)$$

حيث $\mu_{q_t}$ مركز المجموعة التي تنتمي إليها النقطة.

---

## الجزء السادس — توليد الإشارات

### 6.1 شرط التنشيط البولتزماني

$$\boxed{\;P_{\text{activation}}(t) = \exp\left(-\frac{\Gamma(t)}{|a(t)| \cdot T_{\text{info}}(t) + \varepsilon}\right) \geq 0.35\;}$$

**التفسير:** احتمال أن القوة الجيوديسية $|a|$ المضروبة في الحرارة $T_{\text{info}}$ تتغلب على الاحتكاك $\Gamma$.

### 6.2 شرط الانتروبيا

$$S(t) \geq S_{\min} = 5.5$$

### 6.3 الاتجاه (Phase Alignment)

$$\text{micro_momentum}(t) = c_t - c_{t-1}$$

- BUY إذا > 0
- SELL إذا < 0

### 6.4 نظرية الدخول في الطور (Phase-Matched Entry)

**الانزلاق الاحتكاكي:**
$$\delta_{\text{friction}} = 0.1 \cdot \Gamma(t) \cdot c_t$$

**سعر النفق:**
$$p_{\text{tunnel}} = \begin{cases} c_t - \delta_{\text{friction}} & \text{BUY} \\ c_t + \delta_{\text{friction}} & \text{SELL} \end{cases}$$

**التفسير:** السوق يُنتظر أن يهبط بمقدار 10% من الاحتكاك الحالي قبل أن يُدخل. هذا يعطي نقطة انعكاس معقولة.

### 6.5 الوقف الجيوديسي

**نصف قطر فيشر:**
$$r_{\text{fisher}} = \frac{0.012 \cdot \text{clip}(V_t / \bar{V}, 0.5, 3.0)}{1 + 5\Gamma}$$

$$d_{\text{SL}} = \text{clip}(r_{\text{fisher}} \cdot p_{\text{tunnel}}, 0.005 \cdot p_{\text{tunnel}}, 0.05 \cdot p_{\text{tunnel}})$$

**التوسيع الاختياري:**
$$d_{\text{SL}} \leftarrow d_{\text{SL}} \cdot \lambda_{\text{widen}}$$
$$d_{\text{TP}} \leftarrow 2 d_{\text{SL}}$$

حيث $\lambda_{\text{widen}} = 2$ افتراضياً.

**المستويات:**
$$\text{SL} = \begin{cases} p_{\text{tunnel}} - d_{\text{SL}} & \text{BUY} \\ p_{\text{tunnel}} + d_{\text{SL}} & \text{SELL} \end{cases}$$
$$\text{TP} = \begin{cases} p_{\text{tunnel}} + d_{\text{TP}} & \text{BUY} \\ p_{\text{tunnel}} - d_{\text{TP}} & \text{SELL} \end{cases}$$

### 6.6 Kelly الجيوديسي

**نسبة القوة الخام:**
$$r_{\text{force}} = \frac{|a|}{\Gamma + \varepsilon}$$

**التخميد الحراري:**
$$\eta(T) = \exp\left(-\frac{0.01}{T_{\text{info}} + \varepsilon}\right)$$

**التحويل اللوجستي:**
$$x = r_{\text{force}} \cdot \eta - 2$$
$$f^* = f_{\min} + (f_{\max} - f_{\min}) \cdot \frac{1}{1 + e^{-x}}$$

**التقييد:** $f^* \leftarrow \text{clip}(f^*, f_{\min}, f_{\max})$ حيث $f_{\min} = 0.01$, $f_{\max} = 0.05$.

### 6.7 الرافعة الديناميكية

$$\text{Lev}(C) = \text{clip}\left(\frac{L_0}{\sqrt{C/C_0}}, L_{\min}, L_{\max}\right)$$

حيث:
- $L_0 = 50$: الرافعة الأساسية
- $C_0 = 10$: رأس المال الابتدائي
- $L_{\min} = 5$, $L_{\max} = 50$

**التفسير:** الجسيم الأثقل (رأس مال أكبر) يتجاهل التقلبات الصغيرة.

---

## الجزء السابع — إدارة المخاطر

### 7.1 سقف الرافعة بحد التصفية

**سعر التصفية (Binance USDT-M):**
$$\text{Liq} = \begin{cases} p \cdot \frac{1 - 1/L}{1 - \text{MMR}} & \text{BUY} \\ p \cdot \frac{1 + 1/L}{1 + \text{MMR}} & \text{SELL} \end{cases}$$

**شرط SL الآمن:**
$$d_{\text{SL}} \cdot \lambda_{\text{safety}} < |p - \text{Liq}|$$

حيث $\lambda_{\text{safety}} = 1.5$.

**سقف الرافعة:**
$$L_{\max}^{\text{liq}} = \left\lfloor \frac{1}{1 - (1-\text{MMR})(1 - f_{\text{SL}} \cdot \lambda_{\text{safety}})} \right\rfloor$$

### 7.2 تخصيص المخاطرة

**درجة الإشارة:**
$$w = \text{clip}\left(\frac{S - S_{\min}}{2 S_{\min} - S_{\min}}, 0, 1\right)$$

**الحصة لكل خانة:**
$$f_{\text{base}} = \frac{H_{\max}}{N_{\text{slots}}}$$

**المضاعف حسب القوة:**
$$m(w) = 0.5 + 1.0 \cdot w$$

**التخصيص النهائي:**
$$f_{\text{final}} = \min\left(\frac{H_{\text{max}}}{N_{\text{slots}}} \cdot m(w), H_{\text{remaining}}, f_{\text{max}}\right)$$

**القيم:** $H_{\max} = 0.10$, $N_{\text{slots}} = 5$, $f_{\max} = 0.03$.

### 7.3 قانون القوة (Power-Law)

عند انخفاض رأس المال عن المتوسط، نُخفض المخاطرة:

$$\text{PowerScale}(C) = \sqrt{\frac{\max(C - C_{\text{floor}}, 0)}{C}}$$

حيث $C_{\text{floor}} = 5$ (قاع رأس المال).

**التفسير:** الجسيم القريب من الفناء يفقد كتلته، فيتفاعل بحذر.

### 7.4 دائرة الحماية المتدرجة

| الشرط | مضاعف المخاطرة |
|---|---|
| $\text{DD} \geq 0.70$ | $0.05$ |
| $\text{DD} \geq 0.50$ | $0.10$ |
| $\text{DD} \geq 0.30$ | $0.25$ |
| $\text{DD} < 0.30$ | $1.0$ |

حيث $\text{DD} = (C_{\text{peak}} - C)/C_{\text{peak}}$.

---

## الجزء الثامن — الوقف المتحرك

### 8.1 حساس الأوج (Apex Sensor)

$$\text{pnl}(t) = \frac{p_t - p_{\text{entry}}}{p_{\text{entry}}} \cdot \text{sgn}$$

**شرط التنشيط:**
$$|\text{pnl}| \geq \kappa_{\text{pnl}} \cdot \sigma_{\text{bar}}$$

**شرط استنفاد الطاقة:**
$$\sum_{j=t-2}^{t} \dot{F}(j) > \kappa_E \cdot \sigma_{\text{bar}}$$

**شرط تلاشي التسارع:**
$$|\bar{a}(t)| < \kappa_a \cdot \sigma_{\text{bar}}$$

إذا تحققت الشروط الثلاثة → **إغلاق**.

**القيم:** $\kappa_{\text{pnl}} = 0.5$, $\kappa_E = 0.5$, $\kappa_a = 0.3$.

### 8.2 الوقف المتحرك الديناميكي

**المسافة المبدئية:**
$$d_{\text{trail}} = \text{clip}(\kappa_{\text{trail}} \cdot \sigma_{\text{bar}}, d_{\min}, d_{\max})$$

حيث $\kappa_{\text{trail}} = 0.30$, $d_{\min} = 0.002$, $d_{\max} = 0.008$.

**التنشيط:**
$$d_{\text{act}} = \text{clip}(\kappa_{\text{act}} \cdot \sigma_{\text{bar}}, d_{\text{act,min}}, d_{\text{act,max}})$$

حيث $\kappa_{\text{act}} = 0.40$, $d_{\text{act,min}} = 0.003$, $d_{\text{act,max}} = 0.012$.

**تحديث SL:**
$$\text{SL}_{\text{new}} = \begin{cases} P_{\text{peak}} \cdot (1 - d_{\text{trail}}) & \text{BUY} \\ P_{\text{trough}} \cdot (1 + d_{\text{trail}}) & \text{SELL} \end{cases}$$

بشرط $|\text{SL}_{\text{new}} - \text{SL}_{\text{old}}| / \text{SL}_{\text{old}} > 0.0005$.

**التنشيط:** يبدأ التحديث عندما $\text{MFE} \geq d_{\text{act}}$.

### 8.3 Topo-Div (كاشف الانعكاس التبولوجي)

$$\text{div}(t) = \frac{V(t) - V(t-1)}{V(t-1) + \varepsilon}$$

إذا $\text{div}(t) > 0.05$ و $\dot{H}(t) > 0$ → **إغلاق**.

**التفسير:** توسّع سريع في عدم اليقين + ارتفاع الإنتروبيا = انعكاس وشيك.

### 8.4 MaxHold

إذا مضى $168$ شمعة (7 أيام على 1h) → **إغلاق**.

---

## الجزء التاسع — التنفيذ (Post-Only Execution)

### 9.1 المنطق الأساسي

1. ضع أمر Limit بـ `timeInForce: GTX` (Post-Only) عند السعر المستهدف.
2. انتظر انقضاء `PO_MAX_WAIT_S` ثانية.
3. كل `PO_REPRICE_S` ثوانٍ:
   - إذا انحرف السعر عن الهدف بـ $> \text{PO\_DRIFT\_BPS}$ → ألغِ وأعد.
   - إذا وصل عدد المحاولات $\geq \text{PO\_MAX\_ATTEMPTS}$ → ألغِ.

### 9.2 أولوية السعر (PO_FIXED_PRICE)

عند `PO_FIXED_PRICE = True`: استخدم `sig.price` (tunnel) بلا تغيير.
عند `False`: استخدم دفتر الأوامر الحي:
$$p_{\text{target}} = \begin{cases} \text{bid} \cdot (1 - \text{pen}) & \text{BUY} \\ \text{ask} \cdot (1 + \text{pen}) & \text{SELL} \end{cases}$$

حيث $\text{pen} = \text{PO\_PENETRATION\_BPS} \cdot 10^{-4}$.

### 9.3 اختراق الحد الأدنى بـ Ticks

$$n_{\text{ticks}} = \lceil \text{pen} \cdot p / \text{tick\_size} \rceil$$
$$p_{\text{target}} = \begin{cases} \text{bid} - n_{\text{ticks}} \cdot \text{tick\_size} & \text{BUY} \\ \text{ask} + n_{\text{ticks}} \cdot \text{tick\_size} & \text{SELL} \end{cases}$$

### 9.4 الأوامر المعلّقة غير المحجوبة

بدلاً من انتظار التنفيذ، البوت:
1. يضع الأمر.
2. **يُسجّل الحالة** في `_PENDING_ORDERS`.
3. يعود للحلقة الرئيسية فوراً.
4. `monitor_pending_orders` يفحص كل دورة.

### 9.5 Time-Decay (اختياري، معطّل افتراضياً)

عند التفعيل، كل $N$ شمعة يُقلَّص الانزلاق:
$$\delta(t) = \delta_0 \cdot \prod_{k=1}^{s} m_k$$

حيث $s$ هو الـ stage الحالي و $m_k \in \{0.7, 0.5, 0.3\}$.

**التحذير:** مع dip كبير، time-decay يدمر الحافة الأصلية. معطّل افتراضياً.

---

## الجزء العاشر — إدارة المخاطر الحية

### 10.1 Layer 7 — أوامر الحماية على البورصة

عند فتح المركز، تُوضع فوراً:
- `STOP_MARKET` عند SL
- `TAKE_PROFIT_MARKET` عند TP

كلاهما بـ:
- `closePosition: True` (البورصة تُدير الحجم تلقائياً)
- `workingType: MARK_PRICE`
- `reduceOnly: True` (احتياطي)

**التزامن:** عند تحرك SL، يُلغى القديم ويُوضع الجديد، بشرط:
$$|\text{SL}_{\text{new}} - \text{SL}_{\text{last}}| / \text{SL}_{\text{last}} > 0.001$$

### 10.2 Layer 5 — الخروج الطارئ عند اقتراب Liq

**التقدم نحو Liq:**
$$\pi(t) = \frac{|P_{\text{entry}} - p_t|}{|P_{\text{entry}} - \text{Liq}|}$$

إذا $\pi > 0.7$ → **خروج market فوراً**.

### 10.3 Layer 4 — السعر الحي

عند فحص SL/TP:
- استخدم `ticker.last` الحي (ليس `closes[-1]`).
- تحديث كل 5 ثوانٍ.
- عند فشل الـ ticker: ارجع إلى `closes[-1]` كاحتياطي.

### 10.4 تنظيم الحالة (State Machine)

**ملفات الحالة الدائمة:**
- `live_state_{mode}.json`: المراكز المفتوحة
- `pending_orders_{mode}.json`: الأوامر المعلّقة
- `symbol_meta_{mode}.json`: الرافعة والهامش لكل رمز

**المزامنة مع البورصة:**
كل 60 ثانية (افتراضياً)، `reconcile_state_machine`:
- يقارن المراكز المحلية مع `fetch_positions`.
- يتبنى المراكز الشبحية.
- يحذف المراكز المغلقة.

---

## الجزء الحادي عشر — Backtest الحقيقي

### 11.1 محاكاة الدخول (Entry Fill Simulation)

لكل إشارة، ابحث عن أول شمعة $j > \text{close\_idx}$ ضمن نافذة $w$ بحيث:

$$p_{\text{low}}(j) \leq p_{\text{target}} \cdot (1 - \epsilon) \quad \text{(BUY)}$$
$$p_{\text{high}}(j) \geq p_{\text{target}} \cdot (1 + \epsilon) \quad \text{(SELL)}$$

حيث $\epsilon = \text{FILL\_PENETRATION\_BPS} \cdot 10^{-4}$.

**Deadline:** $\min(\text{close\_idx} + w, \text{next\_signal\_idx})$.

### 11.2 Sub-Bars (دقة داخل الشمعة)

عند توفر شموع 5m، الشمعة 1h تُقسَّم إلى 12 شمعة فرعية. تُستخدم لتحل مشكلة "أي حدث أولاً" داخل الشمعة:
- إذا ضُرب SL و TP في نفس الشمعة → **افتراض SL أولاً** (متشائم).
- تُحدَّد نقطة الدخول بدقة 5m.

### 11.3 محاكاة الخروج (Exit Simulation)

`_advance` تفحص كل شمعة من `current_ci + 1` إلى `to_ci`:
- **SL/TP**: يستخدمان `low`/`high` مع penetration.
- **Apex/Topo-Div/MaxHold**: يعتمدان على `close`.

### 11.4 الرسوم والانزلاق

**رسوم الصانع:**
$$\text{Fee}_m = 0.0002 \cdot \text{notional}$$

**رسوم Taker:**
$$\text{Fee}_t = 0.0005 \cdot \text{notional}$$

**انزلاق Taker (دالة في السيولة):**

| ADV (USD) | bps |
|---|---|
| $\geq 5 \times 10^{10}$ | 1.0 |
| $\geq 5 \times 10^{9}$ | 1.5 |
| $\geq 10^{9}$ | 2.5 |
| $\geq 10^{8}$ | 5.0 |
| $\geq 10^{7}$ | 10.0 |
| $< 10^{7}$ | 20.0 |

$$p_{\text{eff}} = \begin{cases} p \cdot (1 + \text{bps} \cdot 10^{-4}) & \text{BUY} \\ p \cdot (1 - \text{bps} \cdot 10^{-4}) & \text{SELL} \end{cases}$$

### 11.5 الرسوم الزمنية (Funding)

$$\text{Funding} = \text{notional} \cdot 0.0001 \cdot \left\lfloor \frac{\Delta t}{8} \right\rfloor$$

حيث $\Delta t$ عدد الشموع المحتفظ بها، و 8 شموع على 1h = 8 ساعات (دورة تمويل واحدة).

---

## الجزء الثاني عشر — المقاييس الإحصائية

### 12.1 المقياس الأساسي

$$\boxed{\;E[\ln(1 + f R)] = \frac{1}{n}\sum_{i=1}^{n} \ln\left(\frac{C_i}{C_{i-1}}\right)\;}$$

حيث $C_i$ رأس المال بعد الصفقة $i$.

**القاعدة:** إذا > 0 → حافة موجبة. إذا < 0 → خاسر.

### 12.2 Sharpe السنوي

$$\text{Sharpe} = \frac{\mu_{\ln r}}{\sigma_{\ln r}} \cdot \sqrt{252}$$

### 12.3 عامل الربح

$$\text{PF} = \frac{\sum_{\text{wins}} \text{net}}{\left|\sum_{\text{losses}} \text{net}\right|}$$

### 12.4 أقصى انخفاض

$$\text{DD}(t) = \frac{\max_{s \leq t} C_s - C_t}{\max_{s \leq t} C_s}$$

### 12.5 تحليل MFE

$$\text{MFE}_i = \max_{t \in [\text{entry}, \text{exit}]} \left(\frac{p_t}{p_{\text{entry}}} - 1\right) \cdot \text{sgn}$$

يُحسب لكل مجموعة خروج منفصلة (Emergency SL, Hard TP, ...).

---

## الجزء الثالث عشر — القرارات المعمارية الحاكمة

### 13.1 القيود الصارمة

1. **لا تعديل على SL بعد الفتح**: SL يُحدَّد مرة عند الفتح، يُرفع فقط بـ trailing.
2. **لا تغيير للرافعة أثناء المركز**: في isolated mode، الرافعة قفل.
3. **لا تجميد للحلقة الرئيسية**: كل عملية O(1) لكل مركز.
4. **كل قرار مسجَّل**: لا استثناءات صامتة.
5. **الطبقة الاستراتيجية منفصلة عن التنفيذ**: `build_signals` لا يعرف شيئاً عن البورصة، و`place_pending_entry` لا يعدّل الإشارة.

### 13.2 التسلسل في `run_live`

```
while True:
    t0 = time.time()
    1. فحص Kill Switch
    2. مراقبة الأوامر المعلّقة (monitor_pending_orders)
    3. مزامنة ميتاداتا الرموز (كل 6 ساعات)
    4. تحديث قائمة الأصول (كل 4 ساعات)
    5. جلب الرصيد الحي
    6. مزامنة المراكز مع البورصة (كل 60 ثانية)
    7. جلب البيانات لكل رمز (fetch_ohlcv فقط عند شمعة جديدة)
    8. process_asset للرموز المتغيرة
    9. مراقبة المراكز المفتوحة:
       - تحديث السعر الحي
       - Apex، Topo-Div، MaxHold
       - Trailing SL + Layer 7 sync
       - SL/TP + Layer 5
       - تنفيذ الخروج
    10. اقتناص صفقات جديدة:
        - توليد الإشارات
        - فلترة (Rule، ML)
        - فحص التعرّض الكلي
        - فحص الارتباط
        - حساب المخاطرة (Kelly + Power-Law)
        - فحص LevCap + LiqGate
        - وضع أمر معلّق
    11. حفظ الحالة
    12. sleep (LIVE_POLL_SECS - elapsed)
```

### 13.3 ثوابت الأداء

| الثابت | القيمة | السبب |
|---|---|---|
| `LIVE_POLL_SECS` | 5 | توازن بين الاستجابة والـ API |
| `RECONCILE_INTERVAL_S` | 3600 | مزامنة كاملة كل ساعة |
| `PO_MAX_WAIT_S` | 200 | مهلة الأمر المعلّق |
| `FILL_ENTRY_MAX_WAIT_BARS` | 25 | مهلة Backtest |
| `NUMBA_ENABLED` | True | تسريع 50-200× |
| `PARALLEL_PROCESSING` | True | معالجة متعددة الأصول |

---

## الجزء الرابع عشر — القيم الافتراضية الكاملة

### 14.1 النوافذ الزمنية

| الرمز | القيمة | الوصف |
|---|---|---|
| $N$ | 24 | نافذة الميزات |
| $W$ | 20 | نافذة الإنتروبيا |
| $L$ | 10 | نافذة الهندسة |
| $K$ | 8 | عدد المجموعات الافتراضي |
| $K_{\min}$ | 4 | الحد الأدنى |
| $K_{\max}$ | 12 | الحد الأقصى |

### 14.2 المخاطرة

| الرمز | القيمة |
|---|---|
| $f_{\min}$ | 0.01 (1%) |
| $f_{\max}$ | 0.05 (5%) |
| $H_{\max}$ | 0.10 (10%) |
| $f_{\text{per-trade,min}}$ | 0.005 |
| $f_{\text{per-trade,max}}$ | 0.03 |

### 14.3 الشراء/البيع

| الرمز | القيمة |
|---|---|
| $S_{\min}$ | 5.5 |
| $P_{\text{activation,min}}$ | 0.35 |
| $\epsilon_H$ | 0.005 |
| $\epsilon_F$ | -0.01 |
| $\lambda_{\text{widen}}$ | 2.0 |

### 14.4 الفيزياء

| الرمز | القيمة |
|---|---|
| $\gamma_0$ | 0.01 |
| $\kappa$ | 0.1 |
| $\xi$ | 1.0 |
| $q$ | 1.0 |
| $H_{\text{ratio,min}}$ | 0.25 |

---

## الجزء الخامس عشر — مبدأ التحقق

### 15.1 اختبار الاتساق

الوثيقة صحيحة إذا وفقط إذا استطاع المُنفّذ:

1. تشغيل `process_asset` على بيانات BTC/USDT 1h لمدة 90 يوم، والحصول على:
   - $K \in [4, 12]$
   - $H_{\text{ratio}} \geq 0.25$
   - $\bar{S} \in [2, 3]$
   - $Q_{95}(S) \in [5.7, 6.1]$

2. تشغيل `build_signals` والحصول على $\sim 3,000$ إشارة لكل 5 رموز × 90 يوم على 1h.

3. تشغيل `simulate_portfolio` والحصول على:
   - Fill rate $\in [15\%, 30\%]$ (مع wait=25)
   - Mean dip $\approx 2\%$
   - R/R $\approx 2.0$

### 15.2 عدم الاتساق = فشل التنفيذ

إذا خرجت أي من هذه الأرقام بشكل مختلف، فهناك خطأ في إعادة البناء. راجع:
- `compute_entropy_friction` (Γ)
- `compute_gauge_force_and_gap` (F_gauge)
- `build_signals` (P_activation، score)

---

## الجزء السادس عشر — ملاحظات أخيرة

### 16.1 ما هذه الاستراتيجية فعلاً

**بعد التجريد من الفيزياء:**
- تصنيف KMeans على 7 ميزات
- إنتروبيا منزلقة على الرموز
- شروط مركّبة: انخفاض إنتروبيا + انخفاض طاقة حرة + قوة تسارع
- دخول عند انزلاق 2% من السعر
- SL/TP بنسبة 1:2
- مخاطرة Kelly معدّلة

**هذا ليس فيزياء جديدة** — إنه **مزيج من mean-reversion وانتروبيا المعلومات مع تسمية فيزيائية**.

### 16.2 الحدود الحقيقية

- **لا يوجد دليل** على أن السوق يتبع معادلة جيوديسية.
- **`F_gauge` و`friction` مفاهيم مستعارة**، لا نتائج من نظرية قياس حقيقية.
- **`P_activation` شكل بولتزماني مخصص**، لا مبدأ فيزيائي.

### 16.3 القيمة الحقيقية

مع ذلك، البوت **يعمل** إذا:
- dip = 2% (mean-reversion)
- SL = 0.6% (قصير)
- TP = 1.2%
- Kelly معدّل 1%
- Risk budget محفظي

**هذه إعدادات مكافئة لـ "mean-reversion scalper" بميزات انتروبية**. القيمة الفعلية في **التنفيذ المنضبط**، ليس في الفيزياء.

---

**نهاية الوثيقة.**

هذه الوثيقة، إذا قرأها خبير واحد، يستطيع إعادة بناء المحرك كاملاً في أي لغة (Python, C++, Rust, Julia). كل معادلة قابلة للحساب مباشرة، وكل ثابت محدد بدقة، وكل قرار معماري له مبرر.

**تحذير نهائي:** الوثيقة تصف **ما هو الكود**، لا **ما ينبغي أن يكون**. إذا كانت الفيزياء زخرفية، فالخبير المُنفّذ سيعرف ذلك. القيمة الحقيقية في **الانضباط التنفيذي** (Layer 7، LiqGate، Power-Law) وليس في النظرية.
