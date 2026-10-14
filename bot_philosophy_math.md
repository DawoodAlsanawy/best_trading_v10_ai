# الأساس الرياضي-الفيزيائي لمحرك التداول الثرموديناميكي الكمي

## مقدمة: تحديد الفضاء الطوري

لتكن سلسلة الأسعار $\{p_t\}_{t \in \mathbb{Z}}$ عملية عشوائية على $\mathbb{R}_{>0}$، ولتكن $\{r_t\}$ سلسلة اللوغاريتمات:

$$r_t \triangleq \ln\left(\frac{p_t}{p_{t-1}}\right)$$

نُعرِّف الفضاء الطوري للحالة $\mathcal{M} \subset \mathbb{R}^7$ انطلاقاً من الميزات الكمومية $\mathbf{x}_t \in \mathcal{M}$، حيث كل نقطة $\mathbf{x}_t$ تحمل المعلومات الإحصائية للنافذة $[t-N, t]$.

---

## العمود الأول: الأسواق كنظام ثرموديناميكي

### 1.1 الطاقة الحرارية

لنمذجة التقلب كمقياس حراري، نُعرِّف:

$$E_{\text{therm}}(t) = \sqrt{\frac{1}{N-1}\sum_{k=t-N}^{t-1}\left(r_k - \bar{r}\right)^2}$$

هذه كمية موجبة، تماثل درجة الحرارة $T$ في نظام إحصائي. الشكلية $\sqrt{\cdot}$ ضرورية لأن $r$ مقياس لوغاريتمي، و$\sqrt{Var(r)}$ يماثل الانحراف المعياري النسبي.

### 1.2 الإنتروبيا الرمزية

ليكن $\Sigma = \{s_1, \ldots, s_K\}$ فضاءً رمزياً منتهياً ناتجاً عن التكميم، ولتكن $q_t \in \Sigma$ السلسلة الرمزية. الإنتروبيا على نافذة $W$:

$$H(t) = -\sum_{k=1}^{K} \hat{p}_k(t) \log_2 \hat{p}_k(t), \quad \hat{p}_k(t) = \frac{1}{W}\sum_{j=t-W+1}^{t} \mathbb{1}[q_j = s_k]$$

القيمة العليا $H_{\max} = \log_2 K$ تمثل الفوضى المطلقة، والقيمة الدنيا $H_{\min} = 0$ تمثل نظاماً رتيباً.

### 1.3 الطاقة الحرة (Helmholtz)

بتطبيق التماثل $F = U - TS$ مع اعتبار $T = 1$ كوحدة قياسية:

$$\boxed{F(t) = E_{\text{therm}}(t) - H(t)}$$

**مفارقة كاتمة البخار**: عندما $E_{\text{therm}} \uparrow$ بينما $H \downarrow$، يتراكم $F$ بشكل غير خطي. هذا يعني نظاماً يحتفظ بطاقة حركية عالية في فضاء طوري مضغوط — وهو الشرط الضروري للانتقال الطوري (Phase Transition) الحتمي.

**مؤشر الانفجار**: $dF(t) = F(t) - F(t-1) < \theta_F$ حيث $\theta_F = -0.01$ يعني أن الضغط الحراري تجاوز عتبة الاستقرار.

---

## العمود الثاني: الهندسة الريمانية وحقل المقياس

### 2.1 متعدد الشعب المعلوماتي

نُعرِّف متعدد شعب ريماني $(\mathcal{M}, g)$ حيث المترية $g_{ij}$ تُستنتج من مصفوفة التغاير المحلية:

$$g_{ij}(t) = \text{Cov}\left(\partial_i \mathbf{x}, \partial_j \mathbf{x}\right)_{[t-L, t]}$$

حيث $L = 10$ هو نافذة الهندسة. حجم ريمان:

$$V(t) = \sqrt{\det\left(g(t) + \varepsilon \mathbb{I}\right)}, \quad \varepsilon = 10^{-9}$$

هذا يقيس "الحجم الفعال" للفضاء المتاح للحركة.

### 2.2 حقل المقياس المنبثق

ليكن $T_{ab}(t)$ مصفوفة الانتقال الرمزية على نافذة $W$:

$$T_{ab}(t) = \frac{\#\{j : q_{j-1} = s_a, q_j = s_b\}}{W}, \quad a,b \in \{1,\ldots,K\}$$

نُعرِّف شدة حقل المقياس كانحراف فروبينيوس للجزء اللاتماثلي:

$$\boxed{\mathcal{F}_{\text{gauge}}(t) = \left\| T(t) - T(t)^\top \right\|_F = \sqrt{\sum_{a,b}\left(T_{ab} - T_{ba}\right)^2}}$$

هذا يقيس **عكوسية الزمن** في الانتقالات الرمزية. $\mathcal{F} = 0$ يعني عمليات متماثلة زمنياً (توازن تفصيلي)، بينما $\mathcal{F} > 0$ يكشف تدفقاً نحو الأمام — وهو توقيع لنظام غير متوازن.

### 2.3 معامل الاحتكاك الإنتروبي

$$\boxed{\Gamma(t) = \gamma_0 + \kappa \cdot \exp\left(\xi \cdot \left(1 - \frac{H(t)}{H_{\max}}\right)\right)}$$

مع $\gamma_0 = 0.01$، $\kappa = 0.1$، $\xi = 1.0$. عندما $H \to 0$ (نظام مرتب)، $\Gamma \to \gamma_0 + \kappa e^\xi \approx 0.28$ — أي أن الأنظمة المرتبة تُبدي احتكاكاً عالياً ضد أي تغيير في اتجاهها.

### 2.4 المعادلة الجيوديسية التفاضلية القسرية

المعادلة الأم للمحرك:

$$\boxed{\ddot{D}(t) = -\nabla F(t) + q \cdot \mathcal{F}_{\text{gauge}}(t) \cdot \dot{\lambda}(t) - \Gamma(t) \cdot \dot{\lambda}(t)}$$

حيث:
- $\dot{\lambda}(t) \triangleq dH(t)$ = معدل التغير الرمزي
- $q = 1.0$ = شحنة لورنتز

في التطبيق العددي:

$$\text{geodesic\_accel}(t) = -dF(t) + q \cdot \mathcal{F}_{\text{gauge}}(t) \cdot dH(t) - \Gamma(t) \cdot dH(t)$$

**تفسير الفيزيائي**:
| الحد | الرمز | التفسير |
|------|-------|---------|
| $-\nabla F$ | قوة استعادة | النظام يتحرك نحو توازن الطاقة الحرة |
| $+q \mathcal{F}_g \dot{\lambda}$ | قوة لورنتز | انحراف مسار بسبب اللاعكوسية الزمنية |
| $-\Gamma \dot{\lambda}$ | تبدد | الاحتكاك الإنتروبي يمتص الطاقة |

---

## العمود الثالث: التكميم الكمومي

### 3.1 كمومية K-Means

عامل التكميم $\mathcal{Q}_K : \mathcal{M} \to \Sigma$:

$$\mathcal{Q}_K(\mathbf{x}) = \arg\min_{k \in \{1,\ldots,K\}} \left\| \mathbf{x} - \boldsymbol{\mu}_k \right\|_2$$

حيث $\{\boldsymbol{\mu}_k\}$ هي مراكز الـ K-Means المُدرَّبة على النافذة $[1, \tau]$ مع $\tau = \lfloor 0.5 \cdot n_{\text{total}} \rfloor$.

### 3.2 قانون القوة للتكميم الديناميكي

$$\boxed{K(t) = \left\lfloor K_{\max} \cdot \exp\left(-\alpha_K \cdot \frac{C(t)}{\overline{\text{ADV}}}\right) \right\rfloor \in [K_{\min}, K_{\max}]}$$

مع $\alpha_K = 100$, $K_{\min}=25$, $K_{\max}=50$.

**القيد الإحصائي** (Shannon-Nyquist الكمومي):
$$K_{\text{data}} = \left\lfloor \frac{n_{\text{train}}}{N_{\text{points/cluster}}} \right\rfloor, \quad N_{\text{points/cluster}} = 100$$

فـ $K(t) \leftarrow \min(K_C, K_{\text{data}})$.

### 3.3 كشف التدهور (Degeneracy Detection)

نقيس **كفاءة التكميم** بـ:

$$\eta(t) = \frac{\mathbb{E}[H|_{[1,\tau]}]}{\log_2 K(t)}$$

إذا $\eta < 0.25$ → التكميم منحل (كل النقاط في cluster واحد) → الرفض.

---

## العمود الرابع: الارتداد المرن (Elastic Mean-Reversion)

### 4.1 دالة الطاقة الكامنة

نمذجة "الشريط المطاطي" بدالة كمون متناسق:

$$V(\mathbf{x}) = \frac{1}{2} \kappa_E \left\| \mathbf{x} - \boldsymbol{\mu}(t) \right\|^2$$

حيث $\boldsymbol{\mu}(t) = \mathbb{E}[\mathbf{x}|_{[t-N,t]}]$. الانحراف المعياري المُعاير:

$$z(t) = \frac{p_t - \bar{p}_N(t)}{\sigma_N(t)}, \quad \bar{p}_N = \frac{1}{N}\sum_{k=t-N}^{t-1} p_k$$

### 4.2 شرط الانحراف الأدنى

$$\boxed{|z(t)| \geq z_{\text{crit}} = 1.5}$$

هذا يضمن أن الانحراف يتجاوز ضوضاء القياس المحلية بـ 1.5σ — أي "بمقدار إحصائي".

### 4.3 هدف المسار الجيوديسي (Tunnel Entry)

$$\boxed{p_{\text{tunnel}} = p_t \mp \underbrace{\left(\kappa_{\text{fd}} \cdot \sigma_{\text{price}}\right)}_{\text{friction drag}} \cdot \text{sign}(z(t))}$$

مع:
- $\sigma_{\text{price}} = E_{\text{therm}}(t) \cdot p_t$
- $\kappa_{\text{fd}} = 2.0$ (حالياً) أو $4.0$ (أصلية)

هذه نقطة **توازن القوى**: القوة الدافعة (momentum) = قوة الاحتكاك ($\Gamma \cdot \sigma_{\text{price}}$).

### 4.4 نصف قطر فشر (Fisher Decoherence Radius)

$$\boxed{\Delta_{\text{SL}} = \left(\kappa_{\text{SL}} \cdot \mathcal{U}(t)\right) \cdot \frac{\sigma_{\text{price}}}{1 + 5\Gamma(t)}}$$

حيث مُعامل عدم اليقين:
$$\mathcal{U}(t) = \text{clip}\left(\frac{V(t)}{\overline{V}}, 0.5, 3.0\right)$$

**المنطق الفيزيائي**: هذا يمثل المسافة التي يتحركها النظام قبل أن يفقد تماسكه مع المسار الجيوديسي.

### 4.5 شرط التأكيد اللحظي (Ticker-Based Bounce)

بعد لمس $p_{\text{tunnel}}$، لا ندخل فوراً. ننتظر تأكيد الارتداد:

$$\boxed{\left|p(t + \tau) - p_{\text{tunnel}}\right| > \kappa_{\text{bounce}} \cdot \sigma_{\text{price}} \cdot \mathbb{1}[\text{sign}(p - p_{\text{tunnel}}) = \text{sign}(\text{action})]}$$

مع $\kappa_{\text{bounce}} = 1.0$ (قيمة الـ `reversal-kappa`).

**الحتمية**: هذا يمنع الدخول على "لمس عابر". يطلب إثباتاً فيزيائياً أن النظام بدأ فعلاً بالعودة إلى التوازن.

---

## العمود الخامس: مستشعر الأوج (Thermodynamic Apex)

### 5.1 تكامل الفعل

في الميكانيكا التحليلية، الفعل هو:
$$\mathcal{S}[q] = \int_{t_0}^{t} \mathcal{L}(q, \dot{q}, t) \, dt$$

في المحرك: $\mathcal{S}(t) = \sum_{k=t-2}^{t} dF(k)$

### 5.2 شرط استنفاد الطاقة

$$\boxed{\mathcal{S}(t) > \kappa_E \cdot \sigma_{\text{bar}} \quad \text{and} \quad \bar{a}(t) < \kappa_a \cdot \sigma_{\text{bar}}}$$

حيث $\bar{a}(t) = \text{mean}(a(t-2), a(t-1), a(t))$ و $a$ هو التسارع الجيوديسي.

**التفسير**: "الحجر في الهواء" يصل إلى الأوج عندما يصل تكامل الفعل ذروته ويهبط التسارع إلى الصفر. البوت يخرج في هذه اللحظة، **قبل** أن يسقط السعر.

### 5.3 مُخمِّد الاهتزاز (Debouncer)

لمنع الخروج على ضوضاء لحظية، نطلب تأكيداً زمنياً:
$$\text{Exit} \iff \text{Apex}_{t-1} \land \text{Apex}_t \land \text{Apex}_{t+1}$$

---

## العمود السادس: كيلي الثرموديناميكي

### 6.1 درجة الحرارة المعلوماتية

$$\boxed{T_{\text{info}}(t) = \frac{|dF(t)|}{|dH(t)| + \varepsilon} + E_{\text{therm}}(t) \cdot 400 \cdot \sqrt{\text{TF}_{\text{scale}}}}$$

الحد الأول يقيس "سرعة تبديد الفوضى"، والحد الثاني يضمن سيادة $\sigma$ كحرارة مطلقة (المقياس الطوري).

ثم: $T_{\text{info}} \leftarrow \text{clip}(T_{\text{info}}, 0.5, 20.0)$

### 6.2 معامل Kelly الثرموديناميكي

$$\boxed{f^*(t) = f_{\min} + (f_{\max} - f_{\min}) \cdot \sigma\left(\Phi(t)\right)}$$

حيث:
$$\Phi(t) = \left(\frac{|a(t)|}{\Gamma(t)}\right) \cdot e^{-0.01 / T_{\text{info}}(t)} - 2.0$$

و $\sigma(x) = (1 + e^{-x})^{-1}$ هي دالة اللوجستيك.

| المعامل | القيمة |
|---------|--------|
| $f_{\min}$ | $0.01$ (1%) |
| $f_{\max}$ | $0.05$ (5%) |

**التفسير**:
- $\frac{|a|}{\Gamma}$ = نسبة القوة الدافعة إلى الاحتكاك (Signal-to-Noise الفيزيائي)
- $e^{-0.01/T}$ = تخميد حراري (تقلبات أقل عند حرارة منخفضة)
- $\Phi - 2$ = تحويل متمركز حول "القوة الطبيعية"
- $\sigma(\Phi)$ = احتمال فعّال للنجاح

### 6.3 توسيع المحفظة (Power-Law Correction)

$$\boxed{f_{\text{eff}}(t) = f^*(t) \cdot \sqrt{\frac{C(t) - C_{\text{floor}}}{C(t)}} \cdot M_{dd}(t)}$$

حيث $C_{\text{floor}} = 0.15\$ و$M_{dd}$ معامل الانخفاض المتدرج.

**التفسير**: $\sqrt{\text{free}}$ يمثل قانون القوة على مقاس "الجسيم الحقيقي" — كلما صغر رأس المال، كلما زاد "التنافر" مع الحافة.

### 6.4 تجميع المخاطر المحفظية

$$\boxed{\mathcal{H}_{\max} \geq \sum_{i \in \text{open}} f_{\text{eff}}^{(i)} \quad \Rightarrow \quad f_{\text{new}} = \min\left(f_{\text{eff}}, \frac{\mathcal{H}_{\max} - \mathcal{H}_{\text{used}}}{n_{\text{slots}}}\right)}$$

مع $\mathcal{H}_{\max} = 0.10$ (10% heat إجمالي).

---

## التوليف النهائي: قانون الحركة الحاكم

نجمع الأعمدة الستة في **مبدأ واحد**:

$$\boxed{\delta \mathcal{A} = 0, \quad \mathcal{A} = \int_{t_0}^{t_f} \left[ \frac{1}{2}\dot{\lambda}^2 - V(\lambda) + q \mathcal{F}_g(\lambda) \dot{\lambda} - \Gamma \dot{\lambda} \right] dt}$$

حيث $\mathcal{A}$ هو تكامل الفعل الفعال، و$\lambda$ هو الإحداثي الرمزي.

**مبدأ هاملتون الموسَّع**:
1. **النظام يبحث عن المسار الأقل فعلاً** ($\delta \mathcal{A} = 0$) — هذا قانون الطبيعة.
2. **البوت لا يتنبأ بالسعر**، بل يحسب **حل المعادلة التفاضلية** ويتنبأ بمكان التوازن.
3. **نقطة الدخول** $p_{\text{tunnel}}$ هي حيث يُصبح $\dot{\lambda} = 0$ (نقطة سكون)، وقوة الاحتكاك تساوي القوة الدافعة.
4. **نقطة الخروج** (Apex) هي حيث يُشبع تكامل الفعل.

---

## المبرهنة الحاكمة

**المبرهنة**: في نظام مالي يُنمذج بـ $(\mathcal{M}, g, \Gamma, \mathcal{F}_g)$، إذا:
1. $E_{\text{therm}} \uparrow$ (حرارة مرتفعة)
2. $H \downarrow$ (نظام مرتب)
3. $\mathcal{F}_g > 0$ (لاعكوسية زمنية)
4. $|\nabla F| \gg \Gamma$

فإن النظام **مُقيَّد** لتفريغ الطاقة الحرة عبر انتقال طوري خلال أفق زمني $\mathcal{T} \sim 1/\sqrt{|dF|}$.

**البوت**:
- **يكشف** المرحلة 1-4 رياضياً
- **ينتظر** عند نقطة الجيوديسي
- **يستفيد** من الانتقال الطوري
- **يخرج** عند استنفاد تكامل الفعل
- **يُوازن** المخاطرة بحرارة النظام

---

## قاعدة الإبستمولوجيا

> **"الأسواق ليست عشوائية، بل تُنمذج بعملية عشوائية غير خطية ذات طاقة حرة محدودة. البوت لا يراهن على اتجاه، بل على انحدار رياضي للطاقة الحرة نحو أدنى محلي — وهو انحدار حتمي بمقتضى القانون الثاني للثرموديناميك."**

النموذج الرياضي للمحرك:

$$\boxed{\mathcal{B} : (\mathcal{M}, g) \mapsto \mathbb{R}, \quad \mathcal{B}(\mathbf{x}) = \mathbb{E}\left[\text{PnL} \mid \nabla F, \mathcal{F}_g, \Gamma, T_{\text{info}}\right]}$$

البوت يُقدِّر دالة القيمة $\mathcal{B}$ ويُعظِّمها عبر قرارات دخول/خروج مبنية على حل معادلة أويلر-لاغرانج:

$$\frac{d}{dt}\left(\frac{\partial \mathcal{L}}{\partial \dot{\lambda}}\right) - \frac{\partial \mathcal{L}}{\partial \lambda} = 0$$

**هذا كل شيء.** البوت لا يقوم بأكثر من حل هذه المعادلة رقمياً على بيانات السوق في الزمن الحقيقي، ثم يتصرف بمقتضى الحل.
