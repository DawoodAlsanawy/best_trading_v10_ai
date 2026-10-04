#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  تشخيص وضع Watch في abl8b والـ Testnet الحالي
#  لا يُعدّل أي ملف — للقراءة فقط
# ═══════════════════════════════════════════════════════════════

echo "═══════════════════════════════════════════════════════════════"
echo " 1. مصدر الحقيقة: trading_2_v8b_reference.py"
echo "═══════════════════════════════════════════════════════════════"

REF="trading_2_v8b_reference.py"
if [ ! -f "$REF" ]; then
    echo "❌ $REF غير موجود. جرب:"
    ls -la trading_2*.py 2>/dev/null
    REF="trading_2.py"
    echo "   سأستخدم $REF بدلاً منه."
fi

echo ""
echo "── 1a. القيمة الافتراضية في Config ──"
grep -n "WATCH_MODE_ENABLED" "$REF"

echo ""
echo "── 1b. منطق argparse (flag --no-watch) ──"
grep -n -A3 "args.no_watch" "$REF" | head -20

echo ""
echo "── 1c. نقاط الاستخدام في المحاكاة والـ live ──"
grep -n "WATCH_MODE_ENABLED" "$REF" | grep -v "Config\|CFG\." | head -20

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " 2. سجل آخر backtest (abl8b)"
echo "═══════════════════════════════════════════════════════════════"

LOG="results/bt_final.log"
if [ ! -f "$LOG" ]; then
    echo "⚠️  $LOG غير موجود. ابحث عن أي سجل:"
    find results/ -name "*.log" -newermt "30 days ago" 2>/dev/null | head -5
    echo "   اختر أحدث ملف وأعد تشغيل هذا الفحص عليه:"
    echo "   grep -E 'Watch|Backtest Watch|Entry fills' <الملف>"
else
    echo "── 2a. هل استُخدم Watch؟ ──"
    grep -n "Backtest Watch" "$LOG" | head -3
    grep -n "watch-then-trigger" "$LOG" | head -3

    echo ""
    echo "── 2b. سطر Entry fills (يُظهر wait mode) ──"
    grep -n "Entry fills" "$LOG" | head -3

    echo ""
    echo "── 2c. إشارات gauge/الأوامر (تأكيد إضافي) ──"
    grep -nE "\[Watch\]|\[Pending\]|\[Gauge-Filter\]" "$LOG" | head -10
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " 3. حالة Testnet الحالية"
echo "═══════════════════════════════════════════════════════════════"

echo "── 3a. ملف watch_signals_testnet.json ──"
if [ -f "watch_signals_testnet.json" ]; then
    echo "   حجم: $(wc -c < watch_signals_testnet.json) بايت"
    echo "   عدد الإشارات: $(python3 -c "import json; print(len(json.load(open('watch_signals_testnet.json'))))" 2>/dev/null)"
    echo "   أول مفتاحين:"
    python3 -c `
import json
d = json.load(open('watch_signals_testnet.json'))
for i, k in enumerate(list(d.keys())[:2]):
    print(f'     {i+1}. {k} → action={d[k].get(\"action\")}, tunnel={d[k].get(\"tunnel_entry_p\")}')
` 2>/dev/null
else
    echo "   (غير موجود — ربما لم يُسجَّل أي watch signal بعد)"
fi

echo ""
echo "── 3b. ملف pending_orders_testnet.json ──"
if [ -f "pending_orders_testnet.json" ]; then
    echo "   حجم: $(wc -c < pending_orders_testnet.json) بايت"
    python3 -c "
import json
d = json.load(open('pending_orders_testnet.json'))
print(f'   عدد الأوامر: {len(d)}')
for k, v in list(d.items())[:3]:
    print(f'     {k}: side={v.get(\"side\")}, px={v.get(\"price\")}, exec_mode={v.get(\"execution_mode\")}')
" 2>/dev/null
else
    echo "   (غير موجود)"
fi

echo ""
echo "── 3c. سجل صفقات Testnet ──"
if [ -f "trades_log_testnet.jsonl" ]; then
    echo "   عدد السطور: $(wc -l < trades_log_testnet.jsonl)"
    echo "   آخر 3 صفقات:"
    tail -3 trades_log_testnet.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        r = json.loads(line)
        if r.get('_meta'): 
            print(f'   META: mode={r.get(\"mode\")}, tf={r.get(\"timeframe\")}')
            continue
        print(f'   {r.get(\"symbol\")} {r.get(\"action\")} net_pnl={r.get(\"net_pnl\")} rsn={r.get(\"exit_reason\")}')
    except: pass
" 2>/dev/null
else
    echo "   (فارغ أو غير موجود — لا صفقات بعد)"
fi

echo ""
echo "── 3d. live_state_testnet.json ──"
if [ -f "live_state_testnet.json" ]; then
    python3 -c "
import json
d = json.load(open('live_state_testnet.json'))
print(f'   عدد المراكز المفتوحة: {len(d)}')
for k, v in d.items():
    print(f'     {k}: {v.get(\"action\")} entry={v.get(\"entry\")} qty={v.get(\"qty\")}')
" 2>/dev/null
else
    echo "   (لا مراكز مفتوحة)"
fi

echo ""
echo "── 3e. logs حيّة من Testnet (إن وُجدت) ──"
for f in testnet.log live.log run.log; do
    if [ -f "$f" ]; then
        echo "   [$f]"
        grep -E "\[Watch\]|\[Pending\]|watch-then-trigger|Watch.*ENABLED" "$f" | tail -10
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " 4. تلخيص سريع"
echo "═══════════════════════════════════════════════════════════════"
echo "انظر أعلاه:"
echo "  • إذا 1a يظهر WATCH_MODE_ENABLED: bool = False"
echo "       و 1b لا يضبط =True"
echo "       و 2a يظهر 'Backtest Watch'"
echo "    → abl8b رُوِّض في Watch mode رغم Config=False"
echo ""
echo "  • إذا 1a False و 2a لا يظهر 'Backtest Watch'"
echo "    → abl8b رُوِّض في Legacy mode"
echo ""
echo "  • إذا 3a يحتوي entries و 3e يظهر [Watch] TRIGGERED"
echo "    → Testnet الحالي يعمل بـ Watch"
echo ""
echo "شغّل هذا السكربت من مجلد المشروع: bash diagnose_mode.sh"
