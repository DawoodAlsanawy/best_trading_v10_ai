# هيكل ملفات المشروع

## 📦 Production (الإنتاج)

**الملف:** `trading_prod_buy_only.py`
- **الوضع:** BUY-only مُجمَّد
- **الأداء:** Min Sharpe 1.606 عبر 2024/2025/2026
- **المصدر:** نسخة frozen من `trading_2.py` (2026-10-04)
- **الاستخدام:** Testnet، ثم Live
- **التعديل:** ❌ ممنوع أثناء التشغيل

## 🔬 R&D (البحث والتطوير)

**الملف:** `trading_rnd_sell_only.py`
- **الوضع:** SELL-only تجريبي
- **الأداء:** قيد القياس
- **المصدر:** نسخة معدّلة من `trading_2.py`
- **الاستخدام:** Backtest فقط حتى الآن
- **التعديل:** ✅ مرحّب

## 📋 المرجع الأصلي

**الملف:** `trading_2.py`
- **الوضع:** Workspace للتطوير
- **الغرض:** نقطة انطلاق لأي نسخة جديدة
- **الحالة:** يحتوي على SELL_ENABLED flag

## 🔒 ملفات Backup

- `trading_2.py.bak_*` — نسخ احتياطية لكل patch
- `trading_prod_buy_only.py.v1.0_production` — مرجع الإنتاج الأول

## 📊 ملفات الحالة (state files)

**Production:**
- `live_state_testnet.json`
- `pending_orders_testnet.json`
- `symbol_meta_testnet.json`
- `trades_log_testnet.jsonl`

**R&D (SELL-only):**
- `live_state_testnet_sellrnd.json`
- `pending_orders_testnet_sellrnd.json`
- `symbol_meta_testnet_sellrnd.json`
- `trades_log_testnet_sellrnd.jsonl`

**لا تصادم** — كل نسخة تعمل بشكل مستقل.
