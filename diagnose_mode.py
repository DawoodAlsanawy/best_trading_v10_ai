#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تشخيص وضع Watch في abl8b والـ Testnet الحالي.
للقراءة فقط — لا يعدّل أي ملف.
التشغيل: python3 diagnose_mode.py
"""

import os
import re
import json
import sys
from pathlib import Path

SEP = "═" * 66


def section(title):
    print(f"\n{SEP}")
    print(f" {title}")
    print(SEP)


def file_exists(path):
    return Path(path).exists()


def grep_file(path, pattern, max_lines=20, context=0):
    """بحث بسيط في ملف نصي. يُعيد قائمة (رقم السطر, النص)."""
    if not file_exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        return [("ERROR", str(e))]

    results = []
    for i, line in enumerate(lines, 1):
        if re.search(pattern, line):
            for c in range(-context, context + 1):
                idx = i - 1 + c
                if 0 <= idx < len(lines):
                    prefix = ">>>" if c == 0 else "   "
                    results.append((idx + 1, f"{prefix} {lines[idx].rstrip()}"))
            if len(results) >= max_lines:
                break
    return results


def load_json_safe(path):
    if not file_exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e)}


def count_jsonl_lines(path):
    if not file_exists(path):
        return 0
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════════
# 1. تحديد ملف المرجع
# ═══════════════════════════════════════════════════════════════
section("0. الملفات الموجودة في المجلد الحالي")
py_files = sorted(Path('.').glob('trading_2*.py'))
for f in py_files:
    size_kb = f.stat().st_size / 1024
    print(f"  • {f.name}  ({size_kb:.1f} KB)")

REF = "trading_2_v8b_reference.py"
if not file_exists(REF):
    print(f"\n⚠️  {REF} غير موجود — سأستخدم trading_2.py")
    REF = "trading_2.py"

print(f"\n  → سأحلل: {REF}")


# ═══════════════════════════════════════════════════════════════
# 2. القيم في ملف المرجع
# ═══════════════════════════════════════════════════════════════
section(f"1. {REF} — القيم الحقيقية")

print("\n── 1a. تعريف WATCH_MODE_ENABLED في Config ──")
r = grep_file(REF, r"WATCH_MODE_ENABLED\s*:\s*bool")
if r:
    for ln, txt in r:
        print(f"  [{ln}] {txt}")
else:
    print("  (لم يُعثر على تعريف صريح)")

print("\n── 1b. كل استخدامات WATCH_MODE_ENABLED ──")
r = grep_file(REF, r"WATCH_MODE_ENABLED", max_lines=40)
if r:
    for ln, txt in r:
        print(f"  [{ln}] {txt}")
else:
    print("  (لا استخدامات)")

print("\n── 1c. منطق argparse: --no-watch ──")
r = grep_file(REF, r"no[_-]watch", max_lines=30)
if r:
    for ln, txt in r:
        print(f"  [{ln}] {txt}")
else:
    print("  (لم يُعثر على --no-watch)")

print("\n── 1d. منطق else في main() — يحوي الكذبة المحتملة ──")
r = grep_file(REF, r"Watch-then-trigger ENABLED", max_lines=15, context=4)
if r:
    for ln, txt in r:
        print(f"  [{ln}] {txt}")
else:
    print("  (لم يُعثر)")

print("\n── 1e. simulate_portfolio: كيف يقرر استخدام Watch ──")
r = grep_file(REF, r"precompute_watch_fills|Backtest Watch",
              max_lines=15, context=2)
if r:
    for ln, txt in r:
        print(f"  [{ln}] {txt}")
else:
    print("  (لم يُعثر)")

print("\n── 1f. run_live: كيف يقرر استخدام Watch ──")
r = grep_file(REF, r"monitor_watch_signals", max_lines=10, context=2)
if r:
    for ln, txt in r:
        print(f"  [{ln}] {txt}")
else:
    print("  (لم يُعثر)")


# ═══════════════════════════════════════════════════════════════
# 3. سجل الباكتيست
# ═══════════════════════════════════════════════════════════════
section("2. سجل آخر backtest")

possible_logs = []
for pattern in ['results/bt_final.log', 'results/*.log',
                'bt_*.log', '*.log']:
    for f in Path('.').glob(pattern):
        if f.is_file():
            possible_logs.append(f)

# حذف التكرار، ترتيب بحسب آخر تعديل
possible_logs = sorted(set(possible_logs),
                       key=lambda p: p.stat().st_mtime,
                       reverse=True)[:5]

if not possible_logs:
    print("⚠️  لم يُعثر على أي ملف .log في المجلد أو results/")
else:
    print(f"أحدث 5 ملفات log:")
    for i, f in enumerate(possible_logs, 1):
        size_kb = f.stat().st_size / 1024
        import datetime
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
        print(f"  {i}. {f}  ({size_kb:.0f} KB, {mtime})")

    # ابحث في كل ملفات log عن مؤشرات Watch
    print("\n── 2a. البحث عن مؤشر Watch في كل السجلات ──")
    found_any = False
    for f in possible_logs:
        hits_watch = grep_file(str(f), r"Backtest Watch|watch-then-trigger",
                               max_lines=3)
        hits_fills = grep_file(str(f), r"Entry fills",
                               max_lines=2)
        if hits_watch:
            print(f"\n  📄 {f}:")
            print(f"     ⚠️  يحتوي على Watch:")
            for ln, txt in hits_watch:
                print(f"       [{ln}] {txt.strip()}")
            found_any = True
        if hits_fills:
            for ln, txt in hits_fills:
                print(f"       Entry fills: {txt.strip()}")
    if not found_any:
        print("  ✅ لم يُعثر على أي مؤشر Watch في أي سجل")
        print("     → abl8b رُوِّض في Legacy mode")


# ═══════════════════════════════════════════════════════════════
# 4. ملفات حالة Testnet
# ═══════════════════════════════════════════════════════════════
section("3. حالة Testnet الحالية")

print("\n── 3a. watch_signals_testnet.json ──")
ws = load_json_safe("watch_signals_testnet.json")
if ws is None:
    print("  (غير موجود)")
elif "_error" in ws:
    print(f"  ⚠️  خطأ قراءة: {ws['_error']}")
else:
    print(f"  عدد الإشارات المُراقَبة: {len(ws)}")
    for i, (k, v) in enumerate(list(ws.items())[:3], 1):
        action = v.get('action', '?')
        tunnel = v.get('tunnel_entry_p', '?')
        score = v.get('score', '?')
        print(f"    {i}. {k} → {action} tunnel={tunnel} score={score}")
    if len(ws) > 0:
        print("  ⚠️  Testnet يستخدم Watch mode (يوجد إشارات مُراقَبة)")
    else:
        print("  ✅ ملف فارغ — لا إشارات مُراقَبة حالياً")

print("\n── 3b. pending_orders_testnet.json ──")
po = load_json_safe("pending_orders_testnet.json")
if po is None:
    print("  (غير موجود)")
elif "_error" in po:
    print(f"  ⚠️  خطأ قراءة: {po['_error']}")
else:
    print(f"  عدد الأوامر المعلقة: {len(po)}")
    for k, v in list(po.items())[:3]:
        side = v.get('side', '?')
        px = v.get('price', '?')
        mode = v.get('execution_mode', '?')
        sing = v.get('sing_state_at_placement', '?')
        print(f"    {k}: side={side} px={px} exec_mode={mode} sing={sing}")

print("\n── 3c. trades_log_testnet.jsonl ──")
if not file_exists("trades_log_testnet.jsonl"):
    print("  (غير موجود)")
else:
    n = count_jsonl_lines("trades_log_testnet.jsonl")
    print(f"  عدد السطور: {n}")
    try:
        with open("trades_log_testnet.jsonl", 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # أول سطر = meta
        if lines:
            meta = json.loads(lines[0])
            if meta.get('_meta'):
                print(f"  META: mode={meta.get('mode')}, "
                      f"tf={meta.get('timeframe')}, "
                      f"nassets={meta.get('n_assets', '?')}, "
                      f"K={meta.get('K_MIN')}-{meta.get('K_MAX')}")
                print(f"        initial_capital={meta.get('INITIAL_CAPITAL')}, "
                      f"PO_FIXED_PRICE={meta.get('PO_FIXED_PRICE')}")
        # آخر 3 صفقات
        trades = [json.loads(l) for l in lines[1:] if l.strip()]
        if trades:
            print(f"  آخر {min(3, len(trades))} صفقات:")
            for t in trades[-3:]:
                sym = t.get('symbol', '?')
                act = t.get('action', '?')
                net = t.get('net_pnl', '?')
                rsn = t.get('exit_reason', '?')
                print(f"    {sym} {act} net_pnl={net} rsn={rsn}")
        else:
            print("  (لا صفقات بعد — الملف يحوي meta فقط)")
    except Exception as e:
        print(f"  ⚠️  خطأ قراءة: {e}")

print("\n── 3d. live_state_testnet.json ──")
ls = load_json_safe("live_state_testnet.json")
if ls is None:
    print("  (غير موجود)")
elif "_error" in ls:
    print(f"  ⚠️  خطأ قراءة: {ls['_error']}")
else:
    print(f"  عدد المراكز المفتوحة: {len(ls)}")
    for k, v in ls.items():
        act = v.get('action', '?')
        entry = v.get('entry', '?')
        qty = v.get('qty', '?')
        stage = v.get('stage', 'S1')
        print(f"    {k}: {act} entry={entry} qty={qty} stage={stage}")

print("\n── 3e. symbol_meta_testnet.json ──")
sm = load_json_safe("symbol_meta_testnet.json")
if sm is None:
    print("  (غير موجود)")
elif "_error" in sm:
    print(f"  ⚠️  خطأ قراءة: {sm['_error']}")
else:
    print(f"  عدد الرموز المسجّلة: {len(sm)}")
    for k, v in list(sm.items())[:5]:
        lev = v.get('leverage', '?')
        mm = v.get('margin_mode', '?')
        done = v.get('setup_done', '?')
        print(f"    {k}: lev={lev}x margin={mm} done={done}")


# ═══════════════════════════════════════════════════════════════
# 5. السجل الحي (testnet log)
# ═══════════════════════════════════════════════════════════════
section("4. سجلات حيّة (testnet)")

live_logs = []
for pattern in ['testnet.log', 'live.log', 'run.log',
                'logs/*.log', 'results/testnet*.log']:
    for f in Path('.').glob(pattern):
        if f.is_file():
            live_logs.append(f)

live_logs = sorted(set(live_logs),
                   key=lambda p: p.stat().st_mtime,
                   reverse=True)[:3]

if not live_logs:
    print("  (لا يوجد سجل حيّ — ربما Testnet يُشغَّل في نافذة أخرى)")
else:
    for f in live_logs:
        print(f"\n  📄 {f}:")
        hits = grep_file(str(f),
                         r"\[Watch\]|\[Pending\]|Watch-then-trigger",
                         max_lines=10)
        if hits:
            for ln, txt in hits:
                print(f"    [{ln}] {txt.strip()}")
        else:
            print("    (لا مؤشرات Watch/Pending في هذا السجل)")


# ═══════════════════════════════════════════════════════════════
# 6. الحكم النهائي
# ═══════════════════════════════════════════════════════════════
section("5. الحكم النهائي")

# استخراج القيمة الافتراضية في Config
config_default = None
r = grep_file(REF, r"WATCH_MODE_ENABLED\s*:\s*bool\s*=\s*(True|False)")
if r:
    for ln, txt in r:
        m = re.search(r"=\s*(True|False)", txt)
        if m:
            config_default = m.group(1)
            break

print(f"\n  Config default في {REF}: WATCH_MODE_ENABLED = {config_default}")

# استخراج نتيجة البحث في سجلات الباكتيست
backtest_used_watch = False
for f in possible_logs:
    hits = grep_file(str(f), r"Backtest Watch", max_lines=1)
    if hits:
        backtest_used_watch = True
        break

print(f"  الباكتيست استخدم Watch؟ "
      f"{'نعم' if backtest_used_watch else 'لا (Legacy)'}")

# استخراج نتيجة حالة Testnet
testnet_uses_watch = (ws is not None
                      and "_error" not in ws
                      and len(ws) > 0)
print(f"  Testnet يستخدم Watch حالياً؟ "
      f"{'نعم' if testnet_uses_watch else 'لا / غير معروف'}")

print()
if backtest_used_watch and testnet_uses_watch:
    print("  ✅ الحالة A: متوافق. لا تعدّل شيئاً.")
elif backtest_used_watch and not testnet_uses_watch:
    print("  ⚠️  الحالة B: عدم توافق. الباكتيست Watch, "
          "Testnet Legacy.")
    print("     → أوقف Testnet وأعد تشغيله بدون --no-watch.")
elif not backtest_used_watch and not testnet_uses_watch:
    print("  ✅ الحالة C: متوافق (Legacy). لا تعدّل شيئاً.")
else:
    print("  ⚠️  الحالة D: عدم توافق. الباكتيست Legacy, "
          "Testnet Watch.")
    print("     → أوقف Testnet وأعد تشغيله بـ --no-watch.")
    print("       أو شغّل الباكتيست مجدداً مع تفعيل Watch "
          "لتأكيد النتائج.")

print()
print(SEP)
print(" للتشغيل:  python3 diagnose_mode.py")
print(SEP)
