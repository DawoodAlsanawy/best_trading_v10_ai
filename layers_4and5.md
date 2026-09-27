# التعديلات الجراحية — Layer 4 (سعر حي) + Layer 5 (خروج طارئ عند Liq)

أربعة تعديلات. الأول للثوابت، الثاني يستبدل منطق اختيار السعر في حلقة المراقبة، الثالث يعزّز فحص LiqProximity بسعر Liq الفعلي من البورصة، الرابع عدّاد تحذيرات.

---

## 🔧 التعديل ① — ثوابت جديدة في `Config`

**الموقع:** في `class Config`، بعد كتلة `PROTECTIVE_MAX_RETRIES: int = 2` مباشرة.

**✅ أضف هذا البلوك:**

```python
    # ══ [LAYER 4 — Live price feed for SL/TP checks] ══
    # ad.closes[-1] only refreshes on new bar; on 1h it's frozen for up to
    # 60 min. Ticker gives fresh price every poll (weight=2). Physics
    # checks (Apex, Topo-Div) keep using ad.closes[-1] for reproducibility.
    LIVE_PRICE_ENABLED: bool = True
    LIVE_PRICE_RATE_WEIGHT: float = 2.0
    LIVE_PRICE_FALLBACK_TO_STALE: bool = True

    # ══ [LAYER 5 — Emergency exit near Liq] ══
    LIQ_EMERGENCY_ENABLED: bool = True
    # Refresh exchange-reported Liq when progress crosses this threshold.
    LIQ_EMERGENCY_REFRESH_AT: float = 0.40
    # Cooldown between refreshes of the same symbol.
    LIQ_EMERGENCY_REFRESH_COOLDOWN_S: int = 30
    # Warn user if LiqProximity triggers too often (unsafe leverage regime).
    LIQ_EMERGENCY_WARN_AT: int = 5
```

---

## 🔧 التعديل ② — إعادة كتابة اختيار السعر في حلقة المراقبة (Layer 4)

**الموقع:** داخل `run_live`، قسم `# 1. مراقبة وإغلاق المراكز الحية`، تحديداً كتلة `ad = assets.get(sym)`.

**❌ ابحث عن هذه الكتلة:**

```python
                ad = assets.get(sym)
                if ad is not None:
                    price = float(ad.closes[-1])
                    fi = len(ad.score) - 1
                else:
                    try:
                        _tk = exchange.fetch_ticker(sym)
                        price = float(_tk.get('last') or 0)
                        _rate_record(2.0)
                    except Exception as _e:
                        log.debug(f"[MonFallback] {sym} ticker failed: {_e}")
                        continue
                    if price <= 0:
                        continue
                    fi = -1
                    log.debug(f"[MonFallback] {sym} monitoring via ticker "
                              f"only (ad unavailable)")
```

**✅ استبدلها بـ:**

```python
                ad = assets.get(sym)

                # ══ [LAYER 4] Always prefer live ticker for SL/TP/Liq ══
                # ad.closes[-1] is only refreshed when a new bar opens.
                # On 15m/1h/4h, it can be stale for many minutes. The ticker
                # is fresh every poll. Cost: weight 2 per symbol per cycle.
                price = None
                _live_src = "none"
                if getattr(CFG, 'LIVE_PRICE_ENABLED', True):
                    try:
                        _tk = exchange.fetch_ticker(sym)
                        _rate_record(float(getattr(CFG,
                            'LIVE_PRICE_RATE_WEIGHT', 2.0)))
                        _p = float(_tk.get('last') or 0)
                        if _p > 0:
                            price = _p
                            _live_src = "ticker"
                    except Exception as _e:
                        log.debug(f"[LivePrice] {sym} ticker failed: {_e}")

                # Fallback: stale close from ad if ticker failed
                if (price is None
                        and getattr(CFG, 'LIVE_PRICE_FALLBACK_TO_STALE', True)
                        and ad is not None):
                    try:
                        price = float(ad.closes[-1])
                        _live_src = "stale_close"
                    except Exception:
                        price = None

                if price is None or price <= 0:
                    log.debug(f"[LivePrice] {sym} no price source — skip")
                    continue

                # fi is only needed for physics-based checks
                fi = (len(ad.score) - 1) if ad is not None else -1
```

**الفرق الرئيسي:** الآن `price` دائماً من ticker إن أمكن. `ad.closes[-1]` لم يعد المصدر الأساسي.

---

## 🔧 التعديل ③ — تعزيز فحص LiqProximity بـ Liq الفعلي من البورصة (Layer 5)

**الموقع:** نفس الحلقة، قسم `# ── [LIQ-PROXIMITY] Emergency exit near Liq ──`.

**❌ ابحث عن الكتلة الحالية:**

```python
                # ── [LIQ-PROXIMITY] Emergency exit near Liq ──
                if not ex and getattr(CFG, 'LIQ_ENABLED', True):
                    _liq_px = pos.get('liq_price_estimated')
                    _entry_px = float(pos.get('entry') or 0)
                    if (_liq_px is not None and _liq_px > 0
                            and _entry_px > 0):
                        _liq_gap_entry = abs(_entry_px - float(_liq_px))
                        if _liq_gap_entry > 1e-12:
                            if pos['action'] == "BUY":
                                _progress = (_entry_px - price) / _liq_gap_entry
                            else:
                                _progress = (price - _entry_px) / _liq_gap_entry
                            _thr = float(getattr(CFG, 'LIQ_EMERGENCY_PROGRESS', 0.7))
                            if _progress >= _thr:
                                ex = True
                                rsn = f"Emergency LiqProximity({_progress*100:.0f}%)"
```

**✅ استبدلها بـ:**

```python
                # ── [LAYER 5] LiqProximity with exchange-verified Liq ──
                if not ex and getattr(CFG, 'LIQ_EMERGENCY_ENABLED', True):
                    _entry_px = float(pos.get('entry') or 0)
                    _liq_px = pos.get('liq_price_estimated')

                    # Step 1: compute progress with current estimate
                    _progress = 0.0
                    if (_liq_px is not None and _liq_px > 0
                            and _entry_px > 0):
                        _gap = abs(_entry_px - float(_liq_px))
                        if _gap > 1e-12:
                            if pos['action'] == "BUY":
                                _progress = (_entry_px - price) / _gap
                            else:
                                _progress = (price - _entry_px) / _gap

                    # Step 2: if progress high, refresh Liq from exchange
                    _refresh_thr = float(getattr(CFG,
                        'LIQ_EMERGENCY_REFRESH_AT', 0.40))
                    _cooldown = int(getattr(CFG,
                        'LIQ_EMERGENCY_REFRESH_COOLDOWN_S', 30))
                    _now_ts = time.time()
                    _last_refresh = float(pos.get('_liq_last_refresh_ts', 0.0))

                    if (_progress > _refresh_thr
                            and (_now_ts - _last_refresh) > _cooldown):
                        try:
                            _pos_list = exchange.fetch_positions([sym])
                            for _p in _pos_list:
                                _amt = float(_p['info'].get(
                                    'positionAmt', 0) or 0)
                                if abs(_amt) > 0:
                                    _exch_liq = float(_p['info'].get(
                                        'liquidationPrice', 0) or 0)
                                    if _exch_liq > 0:
                                        # Use whichever is closer to entry
                                        # (more conservative for our check)
                                        if pos['action'] == "BUY":
                                            _cand = max(float(_liq_px or 0),
                                                        _exch_liq)
                                        else:
                                            _cand = min(float(_liq_px or 1e18),
                                                        _exch_liq)
                                        pos['liq_price_estimated'] = _cand
                                        pos['_liq_source'] = 'exchange'
                                        _liq_px = _cand
                                        # Recompute progress with new Liq
                                        _g2 = abs(_entry_px - _cand)
                                        if _g2 > 1e-12:
                                            if pos['action'] == "BUY":
                                                _progress = ((_entry_px - price)
                                                             / _g2)
                                            else:
                                                _progress = ((price - _entry_px)
                                                             / _g2)
                                    break
                        except Exception as _e:
                            log.debug(f"[Liq5] {sym} exchange Liq fetch "
                                      f"failed: {_e}")
                        pos['_liq_last_refresh_ts'] = _now_ts

                    # Step 3: trigger emergency if threshold crossed
                    _thr = float(getattr(CFG, 'LIQ_EMERGENCY_PROGRESS', 0.7))
                    if _progress >= _thr:
                        ex = True
                        rsn = f"Emergency LiqProximity({_progress*100:.0f}%)"
                        _liq_source = pos.get('_liq_source', 'estimated')
                        log.warning(
                            f"[Liq5] {sym} EMERGENCY: progress={_progress*100:.0f}% "
                            f"entry={_entry_px:.6f} liq={float(_liq_px or 0):.6f} "
                            f"price={price:.6f} source={_liq_source}"
                        )
                        # Update warning counter
                        _LIQ_EMERGENCY_STATS['triggers'] += 1
```

---

## 🔧 التعديل ④ — عدّاد التحذيرات لخطر الرافعة

**الموقع:** في المستوى العام، بعد تعريف `_DEGENERATE_CACHE_MAX = 500`.

**✅ أضف هذا البلوك:**

```python
# ══ [LAYER 5] LiqProximity trigger counter ══
_LIQ_EMERGENCY_STATS: Dict = {
    'triggers': 0,
    'last_warned_at': 0.0,
}
```

**الموقع الثاني:** داخل `run_live`، في نهاية الحلقة (قبل الحفظ النهائي للـ state).

**❌ ابحث عن:**

```python
            # ══ Persist state ══
            try:
                with open(state_file, 'w') as f:
                    json.dump(open_pos_live, f, indent=2)
            except Exception as e:
                log.warning(f"[State] end-of-cycle save failed: {e}")
            save_pending_orders()
            save_symbol_meta()
```

**✅ استبدله بـ:**

```python
            # ══ [LAYER 5] Warn if LiqProximity triggers too often ══
            _warn_at = int(getattr(CFG, 'LIQ_EMERGENCY_WARN_AT', 5))
            _trig = _LIQ_EMERGENCY_STATS['triggers']
            if (_trig >= _warn_at
                    and time.time() - _LIQ_EMERGENCY_STATS['last_warned_at']
                        > 600):
                log.warning(
                    f"[Liq5] WARNING: {_trig} emergency LiqProximity exits "
                    f"triggered this session. Leverage on some assets may be "
                    f"too aggressive. Consider reducing MAX_CONCURRENT_ASSETS "
                    f"or checking MMR values."
                )
                _LIQ_EMERGENCY_STATS['last_warned_at'] = time.time()

            # ══ Persist state ══
            try:
                with open(state_file, 'w') as f:
                    json.dump(open_pos_live, f, indent=2)
            except Exception as e:
                log.warning(f"[State] end-of-cycle save failed: {e}")
            save_pending_orders()
            save_symbol_meta()
```

---

## 📋 سلوك البوت المتوقع بعد التعديلات

| الحالة | قبل Layer 4+5 | بعد Layer 4+5 |
|---|---|---|
| مراقبة SL خلال الساعة | سعر ثابت لـ 60 دقيقة (1h) | سعر حي كل 5s |
| Trailing peak على 1h | يتحدّث كل ساعة فقط | يتحدّث كل 5s |
| اكتشاف Hard TP | متأخر حتى إغلاق الشمعة | فوري (≤5s) |
| Liq estimate دقة | ثابت منذ الفتح | يُحدَّث من البورصة عند 40% progress |
| عند 70% نحو Liq | إغلاق market | إغلاق market مع تحذير مفصّل |
| إن تكررت الحوادث | لا تحذير | تحذير بعد 5 حوادث |
| كلفة API إضافية | صفر | 2 weight/مركز/دورة |

---

## ✅ التحقق

### 1. فحص الملف
```bash
grep -c "LIVE_PRICE_ENABLED" trading.py
# متوقع: 2 (تعريف + 1 استخدام)

grep -c "LIQ_EMERGENCY_ENABLED" trading.py
# متوقع: 2 (تعريف + 1 استخدام)

grep -c "_LIQ_EMERGENCY_STATS" trading.py
# متوقع: 3 (تعريف + increment + warn block)

grep -c "_liq_source" trading.py
# متوقع: 2 (تعيين + قراءة)
```

### 2. تشغيل testnet
```bash
rm -f live_state_testnet.json pending_orders_testnet.json
python trading.py --mode testnet --timeframe 1h --nassets 30 --maxcon 3 \
  --api-key $KEY --api-secret $SECRET 2>&1 | tee run.txt
```

**ابحث في `run.txt` عن:**
```bash
grep "\[LivePrice\]" run.txt | head
# متوقع: أسطر "ticker failed" نادرة أو صفر

grep "\[Liq5\]" run.txt
# متوقع: trigger alerts (نادرة)، warning إن تكررت

grep "market_fallback" run.txt | wc -l
# متوقع: صفر (Layer 7 سابقاً حلّها)
```

### 3. اختبار السعر الحي
في اللحظة التي يُنتج فيها البوت `[Pending→Entry]` لأصل ما:
- افتح ملف الحالة `live_state_testnet.json`
- لاحظ `entry`، `sl`، `tp1`
- افتح ticker على testnet لتلك العملة
- قارن `last price` بـ `entry` — يجب أن يكونا قريبين

بعد 30 ثانية، افتح السجل وابحث عن:
```
[Exit] SYMBOL @ X.XXX [Hard TP (marketable)]
```
بدلاً من `(market_fallback)`. هذا يؤكد أن Layer 4 يعمل ويعطي فرصة إغلاق أسرع.

### 4. اختبار السعر الحي في LiqProximity (نادر)
إذا حدث trigger فعلاً، ستظهر في اللوج:
```
[Liq5] SYMBOL EMERGENCY: progress=73% entry=... liq=... price=... source=estimated
```
`source=estimated` يعني التقدير المحلي، `source=exchange` يعني أن البورصة أعطت قيمة مختلفة.

---

## ⚠️ تنبيهات حرجة

**التنبيه ① — Layer 4 يستهلك API إضافي.** 2 weight لكل مركز لكل دورة. مع 5 مراكز و 5s polling = 120 weight/min. إجمالي الميزانية 2400/min. لا مشكلة، لكن راقب `[RateLimit]` في السجل.

**التنبيه ② — Layer 5 يكشف MMR خطأ.** إذا رأيت `source=exchange` بكثرة، فهذا يعني أن `LIQ_FALLBACK_MMR=2%` أعطى تقديراً بعيداً عن الحقيقة. البوت يتعامل معها بذكاء (يأخذ الأكثر تحفظاً)، لكن إذا تكررت، فقد تحتاج تعديل `LIQ_FALLBACK_MMR` أو جلب MMR بشكل مختلف.

**التنبيه ③ — عند عدم توفر ticker.** البوت يرجع إلى `ad.closes[-1]` (مُجمَّد). هذا يعني أن بعض المراكز قد تعمل بأسعار قديمة إذا فشل ticker. يُسجَّل هذا في السجل كـ `fallback to stale close`. راقبه.

**التنبيه ④ — Warning بعد 5 حوادث.** هذا ليس خطأً في البوت، إنه إشارة لك: على الأصول الحالية برأس المال الحالي، الاستراتيجية تُنتج صفقات قريبة جداً من التصفية. قد تحتاج تعديل `LEVERAGE_BASE` إلى قيمة أقل، أو رفع `sl_frac_max` (المسافة بين entry و SL).

**التنبيه ⑤ — الترتيب مع Layer 7.** كلاهما يعمل الآن على نفس المسار. عند Trigger LiqProximity، `Layer 7` يُلغي أوامر STOP/TP أولاً، ثم `Layer 5` يستخدم market. هذا الترتيب ضروري لتجنّب double-close.

---

**بعد التشغيل أرسل لي:**
1. `grep "\[LivePrice\]" | head -20` — للتأكد من أن الأسعار تُجلب بسلاسة
2. أول `[Liq5]` إن ظهر (مع السياق الذي سبقه)
3. `[RateLimit]` آخر سطر بعد 30 دقيقة — للتأكد من أن الاستهلاك معقول
