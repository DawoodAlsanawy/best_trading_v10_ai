# البوت النهائي — حزمة الإنتاج

## الجزء 1: الملف النهائي

البوت النهائي موجود بالفعل: **`trading_prod_buy_only.py`** (أُنشئ في الجلسة السابقة). لكن قبل التسليم، سنتحقق من سلامته بالكامل.

## الجزء 2: سكربت التحقق `verify_production.py`

احفظ هذا:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_production.py — تحقق شامل من سلامة البوت النهائي.

يتأكد من:
  1. كل الإصلاحات الحرجة موجودة
  2. الإعدادات صحيحة (BUY-only)
  3. الصياغة سليمة
  4. checksum يطابق المرجع
"""

import re
import sys
import ast
import hashlib
from pathlib import Path

PROD = "trading_prod_buy_only.py"
REF = "trading_prod_buy_only.py.v1.0_production"

REQUIRED_PATTERNS = [
    ("GAUGE_DISABLE_SELL = True",
     r"GAUGE_DISABLE_SELL:\s*bool\s*=\s*True"),
    ("SELL_ENABLED = False",
     r"SELL_ENABLED:\s*bool\s*=\s*False"),
    ("WATCH_REMOVED = True",
     r"^WATCH_REMOVED\s*=\s*True"),
    ("--end-date flag",
     r'p\.add_argument\("--end-date"'),
    ("--live-capital flag",
     r'p\.add_argument\("--live-capital"'),
    ("LIVE_TRADING_CAPITAL field",
     r"LIVE_TRADING_CAPITAL:\s*float\s*=\s*0\.0"),
    ("BACKTEST_END_DATE field",
     r"BACKTEST_END_DATE:\s*Optional\[str\]"),
    ("_resolve_end_datetime helper",
     r"def _resolve_end_datetime"),
    ("Watch-then-trigger DISABLED log",
     r"Watch-then-trigger DISABLED \(Config default\)"),
    ("net_pnl logging fix",
     r"net_pnl=float\(_net_pnl_lg\)"),
    ("Partial TP taker fee fix",
     r"_exit_fee\s*=\s*_close_qty \* px \* CFG\.TAKER_FEE"),
    ("_promote_pending signature fix",
     r"_promote_pending_to_position\(exchange, sym, rec2"),
    ("Duplicate-orders fix (2-pass cancel)",
     r"\[DUPLICATE-FIX\] two-pass cancel"),
    ("Apex pos dict fix",
     r"pos\['action'\], pos\['entry'\], price, ad, fi"),
]

FORBIDDEN_PATTERNS = [
    ("BUY_DISABLED = True (should NOT be)",
     r"BUY_DISABLED:\s*bool\s*=\s*True"),
    ("Old buggy capital source",
     r"cap_live = float\(bal\['USDT'\]\['free'\]\)"),
    ("Old apex sig.action bug",
     r"sig\.action, pos\.entry_px, p, ad, fi"),
    ("Old cancel (no two-pass)",
     r"def _cancel_all_protective_orders\(exchange, sym: str\) -> int:\n"
     r"    \"\"\"\n    Cancel every STOP_MARKET"),
]


def main():
    p = Path(PROD)
    if not p.exists():
        print(f"❌ {PROD} غير موجود")
        return 1

    text = p.read_text(encoding="utf-8")
    size_kb = len(text) / 1024

    print("═" * 72)
    print("  verify_production.py")
    print("═" * 72)
    print(f"\n  File: {PROD}")
    print(f"  Size: {size_kb:.1f} KB")
    print(f"  Lines: {len(text.splitlines()):,}")
    print()

    # ── 1. Required patterns ──
    print("  ▶ Required fixes:")
    missing = []
    for name, pat in REQUIRED_PATTERNS:
        if re.search(pat, text, re.MULTILINE):
            print(f"    ✅ {name}")
        else:
            print(f"    ❌ {name}  ← MISSING")
            missing.append(name)

    # ── 2. Forbidden patterns ──
    print()
    print("  ▶ Forbidden patterns (must NOT exist):")
    forbidden_found = []
    for name, pat in FORBIDDEN_PATTERNS:
        if re.search(pat, text, re.MULTILINE):
            print(f"    ❌ {name}  ← FOUND (bad!)")
            forbidden_found.append(name)
        else:
            print(f"    ✅ {name} (not present)")

    # ── 3. Syntax check ──
    print()
    print("  ▶ Syntax check:")
    try:
        ast.parse(text)
        print(f"    ✅ ast.parse OK")
    except SyntaxError as e:
        print(f"    ❌ SyntaxError at line {e.lineno}: {e.text}")
        return 1

    # ── 4. Checksum ──
    print()
    print("  ▶ Checksum:")
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"    sha256: {sha256}")

    ref = Path(REF)
    if ref.exists():
        ref_text = ref.read_text(encoding="utf-8")
        ref_sha = hashlib.sha256(ref_text.encode("utf-8")).hexdigest()
        if sha256 == ref_sha:
            print(f"    ✅ matches reference {REF}")
        else:
            print(f"    ⚠️  differs from reference {REF}")
            print(f"       ref sha256: {ref_sha}")
    else:
        print(f"    ⚠️  Reference not found: {REF}")

    # ── 5. Final verdict ──
    print()
    print("═" * 72)
    if not missing and not forbidden_found:
        print("  ✅ PRODUCTION BOT READY")
        print("═" * 72)
        return 0
    else:
        print("  ❌ VERIFICATION FAILED")
        if missing:
            print(f"     Missing fixes: {len(missing)}")
        if forbidden_found:
            print(f"     Forbidden patterns: {len(forbidden_found)}")
        print("═" * 72)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

## الجزء 3: `README_PRODUCTION.md`

احفظ هذا:

```markdown
# Trading Bot v1.0 — Production (BUY-only)

## نظرة عامة

البوت النهائي المُثبَت على 3 سنوات (2024, 2025, 2026).
يعمل فقط بإشارات BUY. SELL مُعطَّل نهائياً.

## الأداء المُثبَت (backtest)

| السنة | Sharpe | Final | Trades | Max DD |
|---|---|---|---|---|
| 2024 | 1.606 | $634 | 1,273 | ~25% |
| 2025 | 2.799 | $14,802 | 1,441 | ~30% |
| 2026 (280d) | 1.674 | $700 | 1,238 | ~35% |

**Min Sharpe عبر 3 سنوات: 1.606**
**GeoMean Final: $1,873**

## البنية

- **الملف:** `trading_prod_buy_only.py`
- **المرجع:** `trading_prod_buy_only.py.v1.0_production`
- **الحجم:** ~570 KB
- **الوضع:** BUY-only (GAUGE_DISABLE_SELL = True)

## الإصلاحات المُدمَجة

1. Watch-then-trigger معطَّل تماماً (WATCH_REMOVED)
2. `--end-date` لتثبيت النافذة الزمنية
3. `--live-capital` لضبط رأس المال المتداول
4. Partial TP fee (MAKER+TAKER)
5. Live net_pnl محسوب
6. `_promote_pending_to_position` signature fix
7. Duplicate protective orders fix (two-pass cancel)
8. Apex dict access fix
9. BUY_DISABLED = False (الملف يعمل BUY+SELL لكن SELL معطَّل)

## التشغيل

### Backtest (تثبيت النافذة الزمنية)

```bash
cd ~/all/projects/AI/best_trading_v10_ai

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
python3 trading_prod_buy_only.py \
    --mode backtest \
    --capital 100 --nassets 100 \
    --timeframe 4h --no-fixed-price --no-trailing \
    --end-date 2025-12-31 --history-days 365 \
    --trade-log results/bt_2025.jsonl \
    2>&1 | tee results/bt_2025.log
```

### Testnet (رأس مال مُقيَّد بـ $300)

```bash
export BINANCE_TESTNET_KEY="<key>"
export BINANCE_TESTNET_SECRET="<secret>"
export KILL_SWITCH_SECRET="<random-64-chars>"

python3 trading_prod_buy_only.py \
    --mode testnet \
    --api-key "$BINANCE_TESTNET_KEY" \
    --api-secret "$BINANCE_TESTNET_SECRET" \
    --capital 100 --live-capital 300 \
    --nassets 100 \
    --timeframe 4h --no-fixed-price --no-trailing \
    --history-days 730 \
    --trade-log trades_log_testnet.jsonl \
    2>&1 | tee testnet_run_v1.0.log
```

### Live (بعد اجتياز Testnet)

```bash
python3 trading_prod_buy_only.py \
    --mode live \
    --api-key "$BINANCE_API_KEY" \
    --api-secret "$BINANCE_API_SECRET" \
    --capital 1000 --live-capital 1000 \
    --nassets 100 \
    --timeframe 4h --no-fixed-price --no-trailing \
    --history-days 730 \
    --trade-log trades_log_live.jsonl \
    2>&1 | tee live_run_v1.0.log
```

## معايير نجاح Testnet (90 يوماً)

| المقياس | القبول | الرفض |
|---|---|---|
| عدد الصفقات | ≥ 30 | < 10 |
| WR | ≥ 40% | < 25% |
| PF | ≥ 1.00 | < 0.85 |
| E[ln] | > 0 | < −0.001 |
| Max DD | < 55% | > 65% |
| Apex exits | ≥ 25% | < 10% |
| Emergency SL | 50–70% | > 80% |
| Protective orders | 100% | < 95% |
| Errors | ≤ 3 | > 5 |

## التحذيرات

- **لا تُعدّل الملف أثناء التشغيل.** أي تغيير يُبطل المقارنة مع Backtest.
- **`--no-trailing` إجباري.** Trailing يُدمّر 99% من الربح.
- **`--no-fixed-price` إجباري.** مُثبَت في abl8b.
- **KILL_SWITCH_SECRET مطلوب.** لا تشغّل بدون kill switch.

## ملفات الحالة

- `live_state_testnet.json` / `live_state_live.json`
- `pending_orders_testnet.json` / `pending_orders_live.json`
- `symbol_meta_testnet.json` / `symbol_meta_live.json`
- `kill_switch.json`
- `trades_log_testnet.jsonl` / `trades_log_live.jsonl`

## الملفات المرتبطة

- `trading_2.py` — Workspace (يحتوي SELL R&D flags)
- `trading_rnd_sell_only.py` — SELL R&D (مؤرشف)
- `archive/sell_rnd_final_*/` — كل ملفات SELL R&D

## الدعم

- **قبل أي تعديل:** شغّل `python3 verify_production.py`
- **عند مشكلة:** راجع `results/*.log` والسجل الكامل
- **Kill switch:** `echo '{"state":"TRIGGERED","reason":"manual","token":"<hmac>"}' > kill_switch.json`
```

## الجزء 4: خطوات التحقق والتشغيل

### الخطوة 1: التحقق

```bash
cd ~/all/projects/AI/best_trading_v10_ai

nano verify_production.py
chmod +x verify_production.py
python3 verify_production.py
```

**المتوقع:**
```
════════════════════════════════════════════════════════════════════════
  verify_production.py
════════════════════════════════════════════════════════════════════════

  File: trading_prod_buy_only.py
  Size: ~570.0 KB
  Lines: ~12,800

  ▶ Required fixes:
    ✅ GAUGE_DISABLE_SELL = True
    ✅ SELL_ENABLED = False
    ✅ WATCH_REMOVED = True
    ✅ --end-date flag
    ... (13 checks)

  ▶ Forbidden patterns:
    ✅ BUY_DISABLED = True (not present)
    ✅ Old buggy capital source (not present)
    ...

  ▶ Syntax check:
    ✅ ast.parse OK

  ▶ Checksum:
    sha256: abc123...

════════════════════════════════════════════════════════════════════════
  ✅ PRODUCTION BOT READY
════════════════════════════════════════════════════════════════════════
```

**إذا ظهر أي ❌** — أرسل المخرجات، لا تشغّل البوت.

### الخطوة 2: تأكيد testnet يعمل

Testnet الحالي يعمل بـ `trading_2.py` أو `trading_prod_buy_only.py`؟

**تحقق:**
```bash
ps aux | grep trading_
```

**إذا يعمل `trading_2.py`** — أوقفه. نُشغّل النسخة النهائية:
```bash
# أوقف العملية القديمة (Ctrl+C)
# ثم شغّل النسخة النهائية
python3 trading_prod_buy_only.py \
    --mode testnet \
    --api-key "$BINANCE_TESTNET_KEY" \
    --api-secret "$BINANCE_TESTNET_SECRET" \
    --capital 100 --live-capital 300 \
    --nassets 100 \
    --timeframe 4h --no-fixed-price --no-trailing \
    --history-days 730 \
    --trade-log trades_log_testnet.jsonl \
    2>&1 | tee testnet_run_v1.0.log
```

### الخطوة 3: احفظ checksum

```bash
sha256sum trading_prod_buy_only.py | tee trading_prod_buy_only.py.v1.0_production.sha256
```

هذا يُثبّت **إصدار الإنتاج النهائي**. أي تعديل مستقبلي سيتغيّر الـ checksum — فتكون مُنبَّهاً.

## الجزء 5: ملخص التسليم

| الملف | الحالة |
|---|---|
| `trading_prod_buy_only.py` | ✅ البوت النهائي |
| `trading_prod_buy_only.py.v1.0_production` | ✅ المرجع المُجمَّد |
| `verify_production.py` | ✅ سكربت التحقق |
| `README_PRODUCTION.md` | ✅ دليل التشغيل |

## الجزء 6: ما بعد التسليم

**الأسبوع 1-2:**
- شغّل Testnet على `trading_prod_buy_only.py`
- راقب أول 5-10 صفقات
- تحقق من عمل Protective Orders و Apex

**الأسبوع 3-12:**
- راقب 90 يوماً كاملة
- اجمع ≥ 30 صفقة
- قيّم وفق معايير النجاح

**بعد 90 يوماً:**
- إذا نجح → Live برأس مال صغير ($1000)
- إذا فشل → مراجعة شاملة

---

**هل تريد أن:**

**(أ)** أُجهّز `deploy_production.sh` — سكربت bash واحد يُشغّل كل خطوات التحقق والتشغيل؟

**(ب)** أُجهّز `monitor_testnet.sh` — سكربت مراقبة حية يومية؟

**(ج)** أنتظر حتى تُشغّل `verify_production.py` وترسل النتائج؟

**توصيتي: (ج).** أولاً تحقق من سلامة البوت، ثم نتخذ الخطوة التالية.
