
---

## <a name="tuning"></a>29. توصيات المعايرة

### للتشغيل الحالي (1h MR)

**ثوابت لا تُلمَس:**
- `timeframe = "1h"`
- `TF_SCALE = 1.0` (يُحسَب)
- `TRAIL_KAPPA = 0.30`
- `TRAIL_ACT_KAPPA = 0.40`
- `PO_PENETRATION_BPS = FILL_PENETRATION_BPS = 1.0`
- `MAX_ABS_NOTIONAL = 100k` (أو أقل)

**ثوابت يجب معايرتها:**

| الثابت | القيمة الحالية | المقترح | السبب |
|---|---|---|---|
| `MAX_ABS_NOTIONAL` | 100k | **20k** | واقعية سيولة |
| `PO_MAX_WAIT_S` | 30 | **900** | parity مع backtest |
| `RULE_MIN_SCORE` | 2 | 2 (مُجرَّب) | Sharpe 7.84 → 8.34 |
| `SL_WIDTH_KAPPA` | 1.5 | **1.0** | تجربة رفعت Sharpe ثم أخفضته |
| `TRAIL_KAPPA` | 0.30 | 0.30 | استقر |
| `MAX_RISK_PER_TRADE` | 0.030 | 0.030 | مقيد بـ HEAT |

### للانتقال إلى 15m

**إلزامي:**
- تعديل `FUNDING_INTERVAL_BARS` من 8 إلى 32 (8h / 15m = 32).
- إعادة تدريب ML filter على 15m.
- إعادة قياس σ الـ timeframes.

### للانتقال إلى 4h

- `FUNDING_INTERVAL_BARS = 2` (8h / 4h).
- `MAX_HOLD_BARS = 42` (7 أيام).
- `N, W, K` يجب مراجعتها (المعنى الزمني يتغيّر).

---

## الخلاصة الرياضية

**البوت له 3 أنواع من الثوابت:**

1. **ثوابت بلا بُعد** (κ-like): `TRAIL_KAPPA`, `SL_WIDTH_KAPPA`, `RULE_MIN_SCORE`, `KAPPA`. **لا تتغير مع الفريم**.

2. **ثوابت لها بُعد زمني** (bar counts): `N`, `W`, `MAX_HOLD_BARS`, `ROLLOFF_AGE_BARS`. **تحتاج `effective_bars()`**.

3. **ثوابت لها بُعد نقدي** (USD): `INITIAL_CAPITAL`, `MIN_NOTIONAL`, `MAX_ABS_NOTIONAL`, `CAPITAL_FLOOR`. **تحتاج معايرة صريحة**.

**القاعدة الذهبية:**

$$
\boxed{\text{أي ثابت يعتمد على } \sigma \text{ يجب أن يكون } \kappa \cdot \sigma}
$$

حيث $\kappa$ عديم البعد. هذا يُعطي **ثباتاً فيزيائياً** عبر الأصول والفريمات.

**التحذير الأخير:** التعديل على أي ثابت من النوع الثاني أو الثالث **بدون تعديل ما يتصل به** يكسر الاستراتيجية. المعايرة صحيحة فقط ضمن مصفوفة الترابطات أعلاه.
