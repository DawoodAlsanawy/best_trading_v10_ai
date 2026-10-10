# 📊 دليل مراقبة وضبط SL + الدخول

## 🎯 المبدأ الأساسي

```
1. اجمع بيانات كافية (≥ 100 صفقة)
2. استخرج 7 مؤشرات حاسمة
3. صنّف المشكلة بدقة
4. عدّل معاملاً واحداً فقط
5. أعد القياس بعد 100 صفقة
6. إذا تحسّن → احتفظ. إذا ساء → ارجع
```

**قاعدة ذهبية**: **لا تُعدّل أكثر من معامل واحد في الوقت الواحد**.

---

## 📍 الخطوة 1: تفعيل التسجيل التفصيلي

### 1.1 الملفات التي تحتاجها

البوت يُنتج تلقائياً:
```
trades_log_testnet.jsonl   ← كل صفقة
live_state_testnet.json    ← المراكز المفتوحة
pending_orders_testnet.json ← الأوامر المعلقة
```

### 1.2 تحقق من وجود الحقول الحاسمة

```bash
python -c "
import json
with open('trades_log_testnet.jsonl') as f:
    for line in f:
        rec = json.loads(line)
        if rec.get('_meta'): continue
        # الحقول التي نحتاجها
        required = ['entry_price', 'exit_price', 'exit_reason',
                    'net_pnl', 'mfe_frac', 'hold_bars',
                    'sl_dist_initial', 'score', 'entry_ci', 'exit_ci']
        missing = [k for k in required if k not in rec]
        print('Missing:', missing if missing else 'NONE ✅')
        break
"
```

إذا كان **NONE** → جاهز للتحليل.

---

## 📍 الخطوة 2: المؤشرات الحاسمة السبعة

### جدول المؤشرات

| # | المؤشر | الصيغة | الأهمية |
|---|---|---|---|
| **1** | SL Hit Rate | `count(SL_hits) / total` | عام |
| **2** | Avg MFE at SL | `mean(mfe for SL trades)` | تشخيص جودة SL |
| **3** | Entry Age at Fill | `fill_bar - signal_bar` | تشخيص `--no-fixed-price` |
| **4** | Post-Fill Drawdown | `-min(0, mfe)` بعد الدخول | تشخيص توقيت الدخول |
| **5** | Fill Ratio | `filled / attempted` | كفاءة التنفيذ |
| **6** | Rejection Reasons | `groupby(reason)` | تشخيص Sanity Gate |
| **7** | TP:SL Ratio | `count(TP) / count(SL)` | صحة R:R |

### لكل مؤشر: نطاق صحي

| المؤشر | صحي | مقلق | كارثي |
|---|---|---|---|
| SL Hit Rate | 35-45% | 50-55% | > 60% |
| Avg MFE at SL | 0.3-0.6R | 0.15-0.3R أو 0.6-0.8R | < 0.1R |
| Entry Age | 0-2 bars | 3-6 bars | > 8 bars |
| Post-Fill DD | 0.2-0.5R | 0.6-0.8R | > 0.9R |
| Fill Ratio | 50-70% | 30-50% أو 70-85% | < 20% |
| TP:SL Ratio | 1.0-1.5 | 0.7-1.0 | < 0.5 |

---

## 📍 الخطوة 3: سكربت استخراج مؤشرات SL

**احفظه باسم**: `sl_monitor.py`

```python
#!/usr/bin/env python3
import json, sys
from collections import defaultdict
import numpy as np

LOG = sys.argv[1] if len(sys.argv) > 1 else "trades_log_testnet.jsonl"

trades = []
with open(LOG) as f:
    for line in f:
        rec = json.loads(line)
        if rec.get("_meta"): continue
        trades.append(rec)

if not trades:
    print("No trades"); sys.exit(0)

n = len(trades)
sl_hits = [t for t in trades if "Emergency SL" in t.get("exit_reason", "")]
tp_hits = [t for t in trades if "Hard TP" in t.get("exit_reason", "")]
apex   = [t for t in trades if "Apex" in t.get("exit_reason", "")]
topo   = [t for t in trades if "Topo" in t.get("exit_reason", "")]
maxhold = [t for t in trades if "MaxHold" in t.get("exit_reason", "")]
eod    = [t for t in trades if "EndOfData" in t.get("exit_reason", "")]

# ═══ 1. SL Hit Rate ═══
sl_rate = len(sl_hits) / n
print(f"═══ SL Health ═══")
print(f"Total trades         : {n}")
print(f"SL hits              : {len(sl_hits)} ({sl_rate*100:.1f}%)")
print(f"TP hits              : {len(tp_hits)} ({len(tp_hits)/n*100:.1f}%)")
print(f"Apex/Topo exits      : {len(apex)+len(topo)}")
print(f"MaxHold              : {len(maxhold)}")
print(f"EndOfData            : {len(eod)}")
print()

# ═══ 2. Avg MFE at SL (normalized by R) ═══
mfe_at_sl = []
for t in sl_hits:
    entry = float(t.get("entry_price", 0))
    sl_d0 = float(t.get("sl_dist_initial", 0))
    mfe_f = float(t.get("mfe_frac", 0))
    if sl_d0 > 0 and entry > 0:
        r_units = (mfe_f * entry) / sl_d0
        mfe_at_sl.append(r_units)

if mfe_at_sl:
    mfe_at_sl = np.array(mfe_at_sl)
    print(f"═══ MFE at SL (R-units) ═══")
    print(f"  mean   : {mfe_at_sl.mean():.3f} R")
    print(f"  median : {np.median(mfe_at_sl):.3f} R")
    print(f"  max    : {mfe_at_sl.max():.3f} R")
    # توزيع
    for lo, hi, label in [
        (0, 0.1, "★ SL ضيق جداً (السعر لم يتحرك)"),
        (0.1, 0.3, "⚠ SL ضيق (تحرك قليل)"),
        (0.3, 0.6, "✅ طبيعي"),
        (0.6, 0.9, "⚠ ربح ضائع (Trailing متأخر)"),
        (0.9, 10, "🔴 ربح كان ممكن (Breakeven)">
    ]:
        cnt = ((mfe_at_sl >= lo) & (mfe_at_sl < hi)).sum()
        pct = cnt / len(mfe_at_sl) * 100
        if pct > 0:
            print(f"  {lo:.1f}-{hi:.1f}R : {cnt:4d} ({pct:5.1f}%) {label}")
print()

# ═══ 3. SL distance stats ═══
sl_dists = []
for t in trades:
    entry = float(t.get("entry_price", 0))
    sl_d0 = float(t.get("sl_dist_initial", 0))
    if entry > 0 and sl_d0 > 0:
        sl_dists.append(sl_d0 / entry * 100)  # % of entry

if sl_dists:
    sl_dists = np.array(sl_dists)
    print(f"═══ SL Distance (% of entry) ═══")
    print(f"  mean   : {sl_dists.mean():.3f}%")
    print(f"  median : {np.median(sl_dists):.3f}%")
    print(f"  min    : {sl_dists.min():.3f}%")
    print(f"  max    : {sl_dists.max():.3f}%")
    print(f"  p10/p90: {np.percentile(sl_dists,10):.3f}% / "
          f"{np.percentile(sl_dists,90):.3f}%")
print()

# ═══ 4. Avg PnL per category ═══
print(f"═══ Average PnL per Exit Reason ═══")
by_reason = defaultdict(list)
for t in trades:
    reason = t.get("exit_reason", "?").split("(")[0].strip()
    by_reason[reason].append(float(t.get("net_pnl", 0)))

for reason, pnls in sorted(by_reason.items(),
                            key=lambda x: -len(x[1])):
    pnls = np.array(pnls)
    print(f"  {reason:30s}: n={len(pnls):4d}  "
          f"avg=${pnls.mean():+.4f}  "
          f"sum=${pnls.sum():+.2f}")
print()

# ═══ 5. WR by SL width bucket ═══
print(f"═══ WR vs SL Width ═══")
buckets = [(0, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 2.5), (2.5, 99)]
for lo, hi in buckets:
    in_b = [t for t in trades
            if lo <= (float(t.get("sl_dist_initial", 0)) /
                       max(float(t.get("entry_price", 1)), 1e-9) * 100) < hi]
    if not in_b: continue
    wr = sum(1 for t in in_b if float(t.get("net_pnl", 0)) > 0) / len(in_b)
    avg = np.mean([float(t.get("net_pnl", 0)) for t in in_b])
    print(f"  SL {lo:.1f}-{hi:.1f}% : n={len(in_b):4d}  "
          f"WR={wr*100:5.1f}%  avg=${avg:+.4f}")
```

**التشغيل**:
```bash
python sl_monitor.py trades_log_testnet.jsonl
```

---

## 📍 الخطوة 4: سكربت استخراج مؤشرات الدخول

**احفظه باسم**: `entry_monitor.py`

```python
#!/usr/bin/env python3
import json, sys
from collections import defaultdict, Counter
import numpy as np

LOG = sys.argv[1] if len(sys.argv) > 1 else "trades_log_testnet.jsonl"

trades = []
with open(LOG) as f:
    for line in f:
        rec = json.loads(line)
        if rec.get("_meta"): continue
        trades.append(rec)

if not trades:
    print("No trades"); sys.exit(0)

# ═══ 1. Entry Age Distribution ═══
ages = []
for t in trades:
    ci_in = int(t.get("entry_ci", 0))
    ci_sig = int(t.get("close_idx", 0))  # signal close_idx
    if ci_in > 0 and ci_sig > 0:
        ages.append(ci_in - ci_sig)

if ages:
    ages = np.array(ages)
    print(f"═══ Entry Age (bars from signal to fill) ═══")
    print(f"  mean   : {ages.mean():.2f} bars")
    print(f"  median : {np.median(ages):.1f} bars")
    print(f"  max    : {ages.max()} bars")
    for lo, hi, label in [(0,1,"✅ فوري"), (1,3,"✅ سريع"),
                           (3,6,"⚠ بطيء"), (6,12,"🔴 قديم"),
                           (12, 999, "💀 ميت")]:
        cnt = ((ages >= lo) & (ages < hi)).sum()
        pct = cnt / len(ages) * 100
        if pct > 0:
            print(f"  {lo:>2}-{hi:>3} bars : {cnt:4d} ({pct:5.1f}%) {label}")
print()

# ═══ 2. Win Rate vs Entry Age ═══
print(f"═══ WR vs Entry Age ═══")
buckets = [(0,1), (1,2), (2,4), (4,8), (8, 999)]
for lo, hi in buckets:
    in_b = [t for t in trades
            if lo <= (int(t.get("entry_ci",0)) - int(t.get("close_idx",0))) < hi]
    if not in_b: continue
    wr = sum(1 for t in in_b if float(t.get("net_pnl", 0)) > 0) / len(in_b)
    avg = np.mean([float(t.get("net_pnl", 0)) for t in in_b])
    print(f"  Age {lo:>2}-{hi:>3} : n={len(in_b):4d}  "
          f"WR={wr*100:5.1f}%  avg=${avg:+.4f}")
print()

# ═══ 3. Post-Fill Adverse Excursion ═══
# approximated by: for winners, how much did they dip first?
# (approximated from MFE + final state)
print(f"═══ Hold Time Distribution ═══")
holds = np.array([int(t.get("hold_bars", 0)) for t in trades])
if len(holds):
    print(f"  mean   : {holds.mean():.1f} bars")
    print(f"  median : {np.median(holds):.1f} bars")
    print(f"  p10/p90: {np.percentile(holds,10):.0f} / "
          f"{np.percentile(holds,90):.0f}")
print()

# ═══ 4. Score Distribution vs WR ═══
print(f"═══ Score Bucket vs WR ═══")
score_buckets = defaultdict(list)
for t in trades:
    s = int(round(float(t.get("score", 0))))
    score_buckets[s].append(t)
for s in sorted(score_buckets):
    grp = score_buckets[s]
    wr = sum(1 for t in grp if float(t.get("net_pnl", 0)) > 0) / len(grp)
    avg = np.mean([float(t.get("net_pnl", 0)) for t in grp])
    print(f"  Score {s} : n={len(grp):4d}  WR={wr*100:5.1f}%  "
          f"avg=${avg:+.4f}")
print()

# ═══ 5. Action Split ═══
print(f"═══ BUY vs SELL ═══")
for act in ["BUY", "SELL"]:
    grp = [t for t in trades if t.get("action") == act]
    if not grp: continue
    wr = sum(1 for t in grp if float(t.get("net_pnl", 0)) > 0) / len(grp)
    avg = np.mean([float(t.get("net_pnl", 0)) for t in grp])
    print(f"  {act:5s} : n={len(grp):4d}  WR={wr*100:5.1f}%  "
          f"avg=${avg:+.4f}")
```

**التشغيل**:
```bash
python entry_monitor.py trades_log_testnet.jsonl
```

---

## 📍 الخطوة 5: جدول التشخيص

بعد تشغيل السكربتين، طابق الأعراض:

### جدول SL

| العرض | السبب | المعامل للتعديل | الاتجاه |
|---|---|---|---|
| SL Rate > 55% + Avg MFE < 0.2R | SL **ضيق جداً** | `SL_WIDEN_MULT` | ↑ 1.5 → 1.8 |
| SL Rate > 55% + Avg MFE 0.4-0.6R | Trailing متأخر | `TRAIL_ACTIVATE_AT_R` | ↓ 2.5 → 1.5 |
| SL Rate > 55% + Avg MFE > 0.8R | Breakeven غائب | `BREAKEVEN_ENABLED` | تأكد من True |
| SL Rate < 25% + Avg Win < 1.5R | SL **واسع جداً** | `SL_WIDEN_MULT` | ↓ 1.5 → 1.2 |
| SL Rate 30-45% + Avg MFE 0.3-0.6R | ✅ صحي | لا تغيير | — |
| SL على % توزيع قمة عند حد معيّن | Side-specific issue | راجع `SL_MIN_SIGMA` | — |

### جدول الدخول

| العرض | السبب | المعامل للتعديل | الاتجاه |
|---|---|---|---|
| Age median > 4 bars | Sanity Gate فضفاض | `PO_MAX_DRIFT_BPS` | ↓ 5.0 → 3.0 |
| Age median > 4 bars + WR منخفض | `--no-fixed-price` بطيء | `PO_PENETRATION_BPS` | ↑ 1.0 → 2.0 |
| WR(age 0-1) > WR(age 4-8) بـ 15%+ | الإشارات القديمة سيّئة | أضف فحص عمر | — |
| Fill Ratio < 30% | Sanity Gate متشدد | `PO_MAX_DRIFT_BPS` | ↑ 5.0 → 8.0 |
| Fill Ratio > 85% + Age عالي | GTX يقبل كل شيء | `PO_MAX_DRIFT_BPS` | ↓ 5.0 → 3.0 |
| Score 3 → WR < 40% | أدنى عتبة | `MIN_SCORE` | ↑ 3 → 4 |

---

## 📍 الخطوة 6: التعديلات الملموسة — جدول القرار

### لضبط SL

```python
# في Config، هذه المعاملات في ترتيب الأولوية:

# 1. الأكثر تأثيراً
SL_WIDEN_MULT: float = 1.5    # 1.2 → 2.0

# 2. القيم الفيزيائية
SL_MIN_SIGMA: float = 3.0     # أدنى حد (بوحدة σ)
SL_MAX_SIGMA: float = 8.0     # أقصى حد
SL_REF_KAPPA: float = 0.8     # المعامل الأساسي

# 3. الحماية بعد الوصول لربح
TRAIL_ACTIVATE_AT_R: float = 2.5    # ↓ 1.5
BREAKEVEN_ENABLED: bool = True      # تأكد
BREAKEVEN_AT_R: float = 1.0         # 1.0 → 0.8
```

### لضبط الدخول

```python
# عتبات Sanity Gate
PO_MAX_DRIFT_BPS: float = 5.0        # ↓ 3.0 أو ↑ 8.0
PO_PENETRATION_BPS: float = 1.0      # ↑ 2.0 إذا Fill منخفض
PO_MAX_ATTEMPTS: int = 3             # 3 → 5

# عتبات Wait
UNIFIED_WAIT_BARS_1H: int = 8        # 8 → 12 (صبر أكثر)
UNIFIED_MAX_AGE_BARS_1H: int = 12    # 12 → 8 (رفض أقدم)

# دخول
FILL_ENTRY_MAX_WAIT_BARS: int = 25   # backtest فقط
```

---

## 📍 الخطوة 7: مثال عملي كامل

### الحالة الأولى: SL يُلمس كثيراً

**القياس**:
```
SL Hit Rate = 58% (كارثي)
Avg MFE at SL = 0.18R (تحرك قليل جداً)
SL distance = 1.2% (متوسط)
```

**التشخيص**: SL **ضيق جداً** — السعر لم يتحرك حتى 0.2R قبل لمس SL.

**التعديل**:
```python
SL_WIDEN_MULT: float = 1.5 → 1.9
```

**إعادة القياس بعد 100 صفقة**:
```
SL Hit Rate = 47% ✅
Avg MFE at SL = 0.42R ✅
Avg PnL = -$0.02 → +$0.15 ✅
```

**القرار**: احتفظ بـ 1.9.

### الحالة الثانية: Signal Age عالي

**القياس**:
```
Entry Age median = 6 bars (على 1h = 6 ساعات)
WR(age 0-1) = 55%
WR(age 6+) = 28% ← كارثي!
```

**التشخيص**: الإشارات القديمة خاسرة بشكل منهجي — `--no-fixed-price` يقبلها فمتأخراً.

**التعديل**:
```python
PO_MAX_DRIFT_BPS: float = 5.0 → 2.5
```

**إعادة القياس**:
```
Entry Age median = 2 bars ✅
WR(age 0-1) = 52%
Fill Ratio = 45% (انخفض من 60% — مقبول)
```

**القرار**: احتفظ بـ 2.5، أو جرّب 3.0 إذا Fill Ratio منخفض جداً.

---

## 📍 الخطوة 8: القيود الذهبية

### ⚠️ 5 قواعد لا تتجاوزها

1. **لا تُعدّل قبل 50 صفقة**
   - بيانات أقل من ذلك ضجيج

2. **لا تُعدّل معاملين في نفس الوقت**
   - لن تعرف أي واحد أثّر

3. **لا تُعدّل أكثر من 30% في المرة**
   - `1.5 → 1.95` ✅، `1.5 → 3.0` ❌

4. **احتفظ بسجل التعديلات**
   - `adjustments.log` مع التاريخ والقيمة والقرار

5. **بعد التعديل، انتظر 100 صفقة**
   - لا تقيّم النتائج على 20 صفقة

### 🛡️ Safety Rails

```python
# لا تلمس هذه أبداً بدون سبب
LIQ_SAFETY_MULT: float = 1.5      # ← خط أحمر
CAPITAL_FLOOR: float = 0.15        # ← يحمي رأس المال
```

---

## 📍 الخطوة 9: ماذا تفعل مع `--no-fixed-price` تحديداً

بناءً على سؤالك السابق، هذا هو **السيناريو المُرجّح**:

### عرض
- الإشارات تُرفض لفترات طويلة
- ثم تُقبل **بعد تأخر** عندما يقترب السعر
- الدخول يحدث والسعر يلامس SL قصيراً ثم يرتد

### التشخيص المحتمل
1. **Signal Age عالي** (4-8 bars) → الإشارات الميتة تُقبل
2. **Sanity Gate فضفاض** → يمرر إشارات قديمة
3. **لا فحص عمر فيزيائي** → البوت لا يعرف أن `P_activation` انخفضت

### الحل الأمثل (بعد القياس)

**إذا أثبتت البيانات أن العمر مشكلة**:
```python
# في place_pending_entry، قبل Sanity Gate
if _age_bars > effective_bars(CFG.UNIFIED_MAX_AGE_BARS_1H) // 2:
    log.info(f"[Pending] {sym} signal aging "
             f"({_age_bars} bars > {effective_bars(CFG.UNIFIED_MAX_AGE_BARS_1H)//2})")
    return None
```

**بدلاً من** ببساطة ضبط `PO_MAX_DRIFT_BPS`، التحقق المباشر من العمر أنظف.

---

## 📍 الخطوة 10: الـ Feedback Loop

```
        ┌─────────────────────┐
        │  شغّل 100 صفقة      │
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │  sl_monitor.py      │
        │  entry_monitor.py   │
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │  جدول التشخيص       │
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │  عدّل معامل واحد    │
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │  شغّل 100 صفقة      │
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │  قارن النتائج       │
        └──────────┬──────────┘
                   ↓
        ┌─────────────────────┐
        │  احتفظ / ارجع        │
        └─────────────────────┘
```

---

## 📊 التلخيص النهائي

| الطبقة | ما تقيسه | السكربت |
|---|---|---|
| **SL** | MFE عند SL، SL Rate، المسافة | `sl_monitor.py` |
| **الدخول** | Age، Fill، Score، Action | `entry_monitor.py` |
| **التشخيص** | جدول الأعراض | هذا الملف |
| **التعديل** | معامل واحد، ≤ 30% | Config |
| **التقييم** | 100 صفقة، مقارنة | كرر |

**العملية الأبسط**:

```bash
# 1. شغّل 100 صفقة
# 2. حلّل
python sl_monitor.py trades_log_testnet.jsonl > sl_report.txt
python entry_monitor.py trades_log_testnet.jsonl > entry_report.txt

# 3. اقرأ التقريرين
# 4. طبّق قاعدة واحدة من جدول التشخيص
# 5. عدّل معاملاً واحداً
# 6. كرر
```

**بعد 3-4 دورات**، ستصل إلى إعدادات **مُعايَرة لبياناتك** — لا تخمين.

---

هل تريد أن أساعدك في:
1. **تشغيل هذين السكربتين** على ملف موجود لديك؟
2. **كتابة سكربت مقارنة** testnet vs live بعد أول 100 صفقة live؟
3. **كتابة FIX-26** الذي يضيف فحص عمر الإشارة في `--no-fixed-price`؟
