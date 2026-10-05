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
