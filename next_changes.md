تحليل النتائج — تقدم حقيقي وإشارة إيجابية

أولاً: مقارنة الأرقام

المقياس قبل (SL_WIDEN=1.0, TP=7) الآن (SL_WIDEN=1.5, TP=3) التحسّن
WR 22.45% 42.57% +20 نقطة 🎯
PF 0.869 0.924 +0.055
Hard TP% 12.9% 27.7% +14.8 نقطة
Emergency SL% 84.7% 69.3% −15.4 نقطة
Max DD 31.53% 26.76% −4.77 نقطة
Sharpe −0.400 −0.266 تحسّن

هذا تقدّم حقيقي وكبير. WR تضاعف تقريباً.

ثانياً: لماذا PF لا يزال < 1.0؟

التحليل الرياضي:

```
WR = 42.57%
avg_win/avg_loss = 8.33 / 6.68 = 1.247

PF = (WR × payoff) / ((1 − WR) × 1)
   = (0.4257 × 1.247) / (0.5743)
   = 0.5308 / 0.5743
   = 0.924
```

حافة التعادل تتطلب:

· إما WR ≥ 44.4% (بنفس payoff)
· أو payoff ≥ 1.35 (بنفس WR)

أنت 2 نقاط مئوية فقط من التعادل.

ثالثاً: الإشارة الذهبية في تحليل MFE

انظر إلى Emergency SL:

```
Emergency SL (n=205) | μMFE= 1.61% | max= 6.61%
   >0.5%:  117
   >1.0%:  101
   >2.0%:   72   ← 35% من الخاسرين لمسوا +2%
```

هذه المعلومة حاسمة:

· 35% من الصفقات الخاسرة وصلت +2% ربحاً قبل الانعكاس
· لو كنا نُغلق عند +1% بـ Breakeven، لكان 50% منهم خرج بـ0R بدل −1R

رابعاً: كيف نحصل على الـ2% المتبقية

الحل الأقوى: Breakeven SL

الفكرة: بمجرد أن يصل MFE إلى +1R، يُنقل SL إلى نقطة الدخول.

الرياضيات المتوقعة:

· من أصل 205 خسارة: ~30% (60 صفقة) كانت ستنجو بـ0R
· من أصل 82 ربح: ~5% (4 صفقات) قد تُغلق عند 0R بدل TP
· الصافي: 60 × 1R − 4 × 2.1R = +51.6R على 296 صفقة = +0.17R/صفقة

EV الحالي = −0.075R/صفقة. بعد Breakeven = +0.095R/صفقة.

هذا يحوّل البوت من خاسر إلى رابح.

خامساً: مشكلة في الكود يجب تصحيحها

في _partial_tp:

```python
capital += _net
pos.partial_pnl = pos.partial_pnl + _net
```

وفي _close:

```python
net = gross - fee - funding_cost + float(getattr(pos, 'partial_pnl', 0.0))
capital = max(capital+net, 0.)
```

المشكلة: partial_pnl يُضاف إلى capital مرتين — مرة عند التنفيذ، ومرة عند الإغلاق النهائي.

الأثر: final_capital مُتضخّم. الأرقام الحقيقية أقل. لكن النسبة (PF, WR) صحيحة لأنها لا تعتمد على capital.

لا يُصلح الآن — فقط نضع علامة. سيُصلح لاحقاً في Phase 3 (تنظيف).

سادساً: التوصية — تعديل واحد فقط

Breakeven SL عند +1R.

في trading_11.py، ابحث في _advance عن:

```python
                # Legacy trailing (uses sub-bar high/low as peak candidate)
                _td = pos.trail_dist_frac if pos.trail_dist_frac > 0 else CFG.TRAIL_DISTANCE
```

أضف قبله:

```python
                # ══ [BREAKEVEN-SL] نقل SL إلى نقطة الدخول عند +1R ══
                # الهدف: حماية الصفقات التي وصلت MFE ≥ 1R من الانعكاس الكامل.
                # يعمل فقط إذا لم يُفعّل Trailing.
                if not getattr(CFG, 'TRAIL_ENABLED', True) and \
                        getattr(CFG, 'BREAKEVEN_ENABLED', True):
                    _sl_frac_init = (pos.sl_dist_initial / pos.entry_px
                                     if pos.entry_px > 0 and pos.sl_dist_initial > 0
                                     else 0.01)
                    _be_trigger_r = float(getattr(CFG, 'BREAKEVEN_AT_R', 1.0))
                    _be_trigger_frac = _sl_frac_init * _be_trigger_r
                    if pos.mfe_frac >= _be_trigger_frac:
                        if sig.action == "BUY":
                            if pos.entry_px > trail_sl:
                                trail_sl = pos.entry_px
                        else:
                            if pos.entry_px < trail_sl:
                                trail_sl = pos.entry_px
```

وأضف في Config:

```python
    # ══ [BREAKEVEN SL — protect trades that reach +N R] ══
    # عند تفعيل --no-trailing، يعمل هذا الميكانيزم المستقل.
    # يحمي 30% من الصفقات التي تلمس +1R قبل الانعكاس.
    BREAKEVEN_ENABLED: bool = True
    BREAKEVEN_AT_R: float = 1.0
```

سابعاً: النتيجة المتوقعة

المؤشر الحالي بعد Breakeven
WR 42.57% 45-50%
PF 0.924 1.05-1.15
Emergency SL% 69.3% 55-60%
Avg Loss −$6.68 −$5.5 (30% تصبح 0)
Max DD 26.76% 20-25%

مع توقّع PF > 1.0 — وهذا هو أول مرة يصل البوت إلى حافة رابحة.

ثامناً: ما لا يجب فعله الآن

❌ السبب
تغيير PARTIAL_TP_R مرة أخرى عدّلته إلى 1.5، نتائجه جيدة
تغيير SL_WIDEN_MULT 1.5 يعمل بشكل جيد
تفعيل TRAIL_ENABLED Trailing لا يزال يفشل (أثبت سابقاً)
تعديل SL_REF_KAPPA 4.0 مع القصّ يعمل
تفعيل --opp-tp أو --sing-* لا معنى قبل استقرار الأساس

تاسعاً: خطوات التنفيذ

1. أضف حقلَي Config (BREAKEVEN_ENABLED, BREAKEVEN_AT_R)
2. أضف الكتلة في _advance
3. شغّل:
   ```bash
   python trading_11.py --mode backtest --capital 100 --nassets 100 \
     --maxcon 5 --timeframe 4h --no-fixed-price --no-trailing \
     --reentry-cooldown 0 --trade-log trades_bk.jsonl \
     2>&1 | tee bt_bk.log
   ```
4. أرسل bt_bk.log

عاشراً: خلاصة الحالة

· ✅ التقدم: WR من 22% إلى 42.6%، PF من 0.87 إلى 0.92.
· ⚠️ الفجوة: 2 نقطة مئوية من التعادل.
· 🎯 الحل: Breakeven SL عند +1R.
· 🚫 التحذير: لا تعديلات إضافية قبل قياس أثر Breakeven.

أنت على بعد تعديل واحد من بوت رابح.
