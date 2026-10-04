#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_testnet.py — تشخيص شامل لسلوك Testnet.
يقرأ فقط — لا يُعدّل شيئاً.
التشغيل: python3 diagnose_testnet.py
"""

import os
import re
import sys
import json
from pathlib import Path
from datetime import datetime


SEP = "═" * 70


def section(title):
    print(f"\n{SEP}")
    print(f" {title}")
    print(SEP)


# ═══════════════════════════════════════════════════════════════
# 1. البيئة
# ═══════════════════════════════════════════════════════════════

section("1. متغيرات البيئة")
key = os.environ.get('BINANCE_TESTNET_KEY', '')
sec = os.environ.get('BINANCE_TESTNET_SECRET', '')
ks = os.environ.get('KILL_SWITCH_SECRET', '')

print(f"  BINANCE_TESTNET_KEY:    {'موجود (' + str(len(key)) + ' chars)' if key else '❌ مفقود'}")
print(f"  BINANCE_TESTNET_SECRET: {'موجود (' + str(len(sec)) + ' chars)' if sec else '❌ مفقود'}")
print(f"  KILL_SWITCH_SECRET:     {'موجود (' + str(len(ks)) + ' chars)' if ks else '⚠️ مفقود (اختياري)'}")

if not key or not sec:
    print("\n❌ لا يمكن المتابعة بدون مفاتيح API.")
    print("   export BINANCE_TESTNET_KEY='...'")
    print("   export BINANCE_TESTNET_SECRET='...'")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# 2. الاتصال بالبورصة
# ═══════════════════════════════════════════════════════════════

section("2. الاتصال بـ Binance Testnet")

try:
    import ccxt
except ImportError:
    print("  ❌ ccxt غير مثبّت. شغّل: pip install ccxt")
    sys.exit(2)

try:
    ex = ccxt.binance({
        'apiKey': key,
        'secret': sec,
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    })
    ex.enable_demo_trading(True)
    print("  ✅ كائن ccxt أُنشئ")
except Exception as e:
    print(f"  ❌ فشل إنشاء ccxt: {e}")
    sys.exit(3)


# ═══════════════════════════════════════════════════════════════
# 3. الرصيد
# ═══════════════════════════════════════════════════════════════

section("3. الرصيد الفعلي على Testnet")

try:
    bal = ex.fetch_balance()
    usdt = bal.get('USDT', {})
    total = usdt.get('total', 0) or 0
    free = usdt.get('free', 0) or 0
    used = usdt.get('used', 0) or 0

    print(f"  USDT total: ${total:,.2f}")
    print(f"  USDT free:  ${free:,.2f}")
    print(f"  USDT used:  ${used:,.2f}")
    print()

    if total > 500:
        print(f"  ⚠️  الرصيد أعلى من $500.")
        print(f"      الباكتيست يستخدم $100 كـ INITIAL_CAPITAL.")
        print(f"      سيكون هناك عدم تطابق في أحجام المراكز.")
        print(f"      الحل: إما سحب الفائض، أو تفعيل capital cap في الكود.")
    elif total < 50:
        print(f"  ⚠️  الرصيد منخفض جداً (< $50).")
        print(f"      قد لا تكفي بعض المراكز للـ MIN_NOTIONAL.")
    else:
        print(f"  ✅ الرصيد مناسب للمقارنة مع الباكتيست.")

except Exception as e:
    print(f"  ❌ فشل جلب الرصيد: {e}")
    print(f"     (قد يكون مشكلة صلاحيات API أو شبكة)")


# ═══════════════════════════════════════════════════════════════
# 4. فحص الرموز المهمة
# ═══════════════════════════════════════════════════════════════

section("4. فحص SOL/USDT على Testnet")

symbol_variants = ['SOL/USDT', 'SOL/USDT:USDT', 'SOLUSDT', 'SOL-PERP']
found_market = None
for sym in symbol_variants:
    try:
        m = ex.market(sym)
        if m:
            print(f"  ✅ {sym} → market موجود")
            print(f"     - id: {m.get('id')}")
            print(f"     - symbol: {m.get('symbol')}")
            print(f"     - type: {m.get('type')}")
            print(f"     - active: {m.get('active')}")
            print(f"     - contract: {m.get('contract')}")
            print(f"     - limits.amount.min: {m.get('limits', {}).get('amount', {}).get('min')}")
            print(f"     - limits.cost.min:   {m.get('limits', {}).get('cost', {}).get('min')}")
            prec = m.get('precision', {})
            print(f"     - precision.price: {prec.get('price')}")
            print(f"     - precision.amount: {prec.get('amount')}")
            found_market = sym
            break
    except Exception:
        continue

if not found_market:
    print("  ❌ SOL/USDT غير موجود بأي صيغة!")
    print("     هذا هو سبب رفض الأوامر.")
    print("     الحل: استبدل SOL/USDT برمز آخر على testnet.")


# ═══════════════════════════════════════════════════════════════
# 5. اختبار GTX (post-only) — بدون إرسال فعلي
# ═══════════════════════════════════════════════════════════════

if found_market:
    section("5. اختبار GTX منطقياً (بدون إرسال)")
    try:
        ob = ex.fetch_order_book(found_market, limit=5)
        best_bid = float(ob['bids'][0][0])
        best_ask = float(ob['asks'][0][0])
        mid = (best_bid + best_ask) / 2.0
        spread_bps = (best_ask - best_bid) / mid * 1e4

        print(f"  Best bid: {best_bid:.4f}")
        print(f"  Best ask: {best_ask:.4f}")
        print(f"  Mid:      {mid:.4f}")
        print(f"  Spread:   {spread_bps:.2f} bps")
        print()

        # محاكاة GTX لـ BUY عند سعر tunnel + offset
        # GTX لـ BUY يتطلب target < best_ask
        print("  محاكاة GTX BUY:")
        for offset_bps in [5, 10, 20, 30]:
            target = mid * (1 - offset_bps * 1e-4)
            would_fill = target < best_ask
            status = "✅ post-only" if would_fill else "❌ يقطع السبريد → GTX rejected"
            print(f"    offset={offset_bps} bps → target={target:.4f} → {status}")

        print()
        print("  محاكاة GTX SELL:")
        for offset_bps in [5, 10, 20, 30]:
            target = mid * (1 + offset_bps * 1e-4)
            would_fill = target > best_bid
            status = "✅ post-only" if would_fill else "❌ يقطع السبريد → GTX rejected"
            print(f"    offset={offset_bps} bps → target={target:.4f} → {status}")

    except Exception as e:
        print(f"  ❌ فشل: {e}")


# ═══════════════════════════════════════════════════════════════
# 6. تحليل الـ log
# ═══════════════════════════════════════════════════════════════

section("6. تحليل testnet_run.log")

log_paths = ['testnet_run.log', 'results/testnet_run.log', 'live.log']
log_file = None
for p in log_paths:
    if Path(p).exists():
        log_file = p
        break

if not log_file:
    print("  ⚠️  لا يوجد ملف log. شغّل testnet مرة أولاً.")
else:
    print(f"  📄 الملف: {log_file}")
    try:
        text = Path(log_file).read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f"  ❌ قراءة فشلت: {e}")
        text = ''

    # إحصاء
    rejections = len(re.findall(r'\[Pending\]\s+\S+\s+rejected — skip', text))
    sl_clips = len(re.findall(r'SL-Clip-Live', text))
    successful_entries = len(re.findall(r'✅ \[Entry\]', text))
    watch_disabled = '[Watch] Watch-then-trigger DISABLED (Config default)' in text

    print(f"  عدد سطور الرفض:     {rejections}")
    print(f"  عدد SL-Clip:        {sl_clips}")
    print(f"  عدد الدخول الناجحة: {successful_entries}")
    print(f"  Watch معطّل:        {'✅ نعم' if watch_disabled else '❌ لا'}")
    print()

    # الرموز التي رُفضت
    symbols_rejected = re.findall(r'\[Pending\]\s+(\S+)\s+rejected', text)
    from collections import Counter
    sym_counts = Counter(symbols_rejected)
    print(f"  الرموز المرفوضة (أعلى 10):")
    for sym, cnt in sym_counts.most_common(10):
        print(f"    {sym:15s}: {cnt:5d} مرة")

    # آخر 20 سطر unique من نوع rejection
    print()
    print(f"  آخر 10 أسطر رفض (فريدة):")
    seen = set()
    count = 0
    for line in text.split('\n'):
        if 'rejected' in line and line not in seen:
            seen.add(line)
            print(f"    {line.strip()[:120]}")
            count += 1
            if count >= 10:
                break

    # كشف نمط الحلقة اللانهائية
    print()
    sol_lines = [l for l in text.split('\n') if 'SOL/USDT' in l and 'SL-Clip' in l]
    if len(sol_lines) >= 10:
        # هل كلها نفس القيم؟
        prices = re.findall(r'SL clipped [\d.]+ → [\d.]+', '\n'.join(sol_lines))
        unique_prices = set(prices)
        if len(unique_prices) == 1:
            print(f"  🔴 حلقة لا نهائية مؤكدة: SOL/USDT يرفض بنفس القيم {len(sol_lines)} مرة")
            print(f"     القيمة: {list(unique_prices)[0]}")


# ═══════════════════════════════════════════════════════════════
# 7. الحكم
# ═══════════════════════════════════════════════════════════════

section("7. الحكم والتوصيات")

issues = []
if not found_market:
    issues.append("SOL/USDT غير موجود على testnet")
if log_file and rejections > 50:
    issues.append(f"حلقة لا نهائية ({rejections} رفض)")
if 'bal' in dir():
    try:
        if total > 500:
            issues.append(f"رأس المال كبير (${total:.0f}) — قد لا يتطابق مع الباكتيست")
    except Exception:
        pass

if not issues:
    print("  ✅ لا مشاكل واضحة. النظام يعمل بشكل طبيعي.")
else:
    print("  ⚠️  المشاكل المكتشفة:")
    for i, issue in enumerate(issues, 1):
        print(f"    {i}. {issue}")
    print()
    print("  التوصيات:")
    if not found_market:
        print("    → استبدل SOL/USDT في _default_assets() برمز آخر")
    if log_file and rejections > 50:
        print("    → طبّق fix_testnet_loop.py (يمنع الحلقة)")
    if 'total' in dir() and total > 500:
        print(f"    → اسحب الفائض أو فعّل capital cap")

print()
print(SEP)
print(f"  انتهى التشخيص في {datetime.now().strftime('%H:%M:%S')}")
print(SEP)
