#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  preflight_testnet.sh
#  يجهّز البيئة لاختبار Testnet بشكل نظيف ومتوافق مع abl8b.
#
#  الخطوات:
#    1. فحص الملفات المطلوبة
#    2. إصلاح السجل الكاذب في trading_2.py
#    3. تحقق من الصياغة
#    4. تنظيف ملفات الحالة القديمة (اختياري: --keep-state)
#    5. ضبط Kill Switch (إن لم يكن مضبوطاً)
#    6. تحقق من متغيرات البيئة
#    7. عرض الأمر النهائي للتشغيل (لا يُشغّل تلقائياً بدون --run)
#
#  الاستخدام:
#    bash preflight_testnet.sh              # خطوات 1-7 (توقف قبل التشغيل)
#    bash preflight_testnet.sh --run        # خطوات 1-7 + تشغيل Testnet
#    bash preflight_testnet.sh --keep-state # لا تحذف ملفات الحالة
#    bash preflight_testnet.sh --dry-run    # لا تعدّل، اعرض فقط
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ─── الإعدادات ───
MAIN_FILE="trading_2.py"
BACKUP_FILE="trading_2_v8b_reference.py"
FIX_SCRIPT="fix_watch_log.py"
LOG_OUT="results/preflight_$(date +%Y%m%d_%H%M%S).log"

# ملفات الحالة للتنظيف
STATE_FILES=(
    "live_state_testnet.json"
    "pending_orders_testnet.json"
    "watch_signals_testnet.json"
    "symbol_meta_testnet.json"
    "kill_switch.json"
    "trades_log_testnet.jsonl"
)

# ─── الأعلام ───
DO_RUN=0
KEEP_STATE=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --run)         DO_RUN=1 ;;
        --keep-state)  KEEP_STATE=1 ;;
        --dry-run)     DRY_RUN=1 ;;
        --help|-h)
            grep '^#' "$0" | head -30 | sed 's/^# \?//'
            exit 0 ;;
        *)
            echo "⚠️  flag غير معروف: $arg" ;;
    esac
done

# ─── أدوات مساعدة ───
c_red()   { printf '\033[31m%s\033[0m\n' "$*"; }
c_grn()   { printf '\033[32m%s\033[0m\n' "$*"; }
c_ylw()   { printf '\033[33m%s\033[0m\n' "$*"; }
c_blu()   { printf '\033[34m%s\033[0m\n' "$*"; }
hdr()     { echo; c_blu "═══ $* ═══"; }

mkdir -p results

# ═══════════════════════════════════════════════════════════════
hdr "0. فحص الملفات المطلوبة"
# ═══════════════════════════════════════════════════════════════

if [ ! -f "$MAIN_FILE" ]; then
    c_red "❌ $MAIN_FILE غير موجود."
    exit 1
fi
c_grn "✅ $MAIN_FILE موجود"

if [ -f "$BACKUP_FILE" ]; then
    c_grn "✅ $BACKUP_FILE موجود (مرجع abl8b)"
else
    c_ylw "⚠️  $BACKUP_FILE غير موجود"
fi

if [ ! -f "$FIX_SCRIPT" ]; then
    c_red "❌ $FIX_SCRIPT غير موجود. أنشئه أولاً."
    exit 1
fi
c_grn "✅ $FIX_SCRIPT موجود"

# ═══════════════════════════════════════════════════════════════
hdr "1. إصلاح السجل الكاذب"
# ═══════════════════════════════════════════════════════════════

FIX_ARGS=(--file "$MAIN_FILE")
[ "$DRY_RUN" -eq 1 ] && FIX_ARGS+=(--dry-run)

if ! python3 "$FIX_SCRIPT" "${FIX_ARGS[@]}"; then
    c_red "❌ فشل الإصلاح. توقف."
    exit 2
fi

# ═══════════════════════════════════════════════════════════════
hdr "2. تحقق من الصياغة"
# ═══════════════════════════════════════════════════════════════

if python3 -c "import ast; ast.parse(open('$MAIN_FILE', encoding='utf-8').read())" 2>/dev/null; then
    c_grn "✅ $MAIN_FILE صياغته صحيحة"
else
    c_red "❌ خطأ صياغة في $MAIN_FILE. تراجع!"
    exit 3
fi

# ═══════════════════════════════════════════════════════════════
hdr "3. تنظيف ملفات الحالة"
# ═══════════════════════════════════════════════════════════════

if [ "$KEEP_STATE" -eq 1 ]; then
    c_ylw "⚠️  --keep-state: لن أحذف أي ملف."
    for f in "${STATE_FILES[@]}"; do
        if [ -f "$f" ]; then
            c_ylw "   محفوظ: $f ($(wc -c < "$f") بايت)"
        fi
    done
else
    for f in "${STATE_FILES[@]}"; do
        if [ -f "$f" ]; then
            if [ "$DRY_RUN" -eq 1 ]; then
                c_ylw "   (dry) سيُحذف: $f"
            else
                # احفظ نسخة إن كان الملف يحوي بيانات فعلية
                if [ "$f" = "trades_log_testnet.jsonl" ] && [ "$(wc -l < "$f")" -gt 1 ]; then
                    bk="results/${f}.bak_$(date +%Y%m%d_%H%M%S)"
                    cp "$f" "$bk"
                    c_ylw "   نسخة احتياطية: $bk"
                fi
                rm -f "$f"
                c_grn "   حُذف: $f"
            fi
        fi
    done
fi

# ═══════════════════════════════════════════════════════════════
hdr "4. ضبط Kill Switch"
# ═══════════════════════════════════════════════════════════════

if [ -z "${KILL_SWITCH_SECRET:-}" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
        c_ylw "   (dry) KILL_SWITCH_SECRET غير مضبوط"
    else
        NEW_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
        c_ylw "⚠️  KILL_SWITCH_SECRET غير مضبوط."
        c_ylw "   ولّدت سراً جديداً. احفظه في مكان آمن:"
        echo
        echo "   export KILL_SWITCH_SECRET=\"$NEW_SECRET\""
        echo
        c_ylw "   (لن أضعه في البيئة — نفّذه يدوياً)"
    fi
else
    c_grn "✅ KILL_SWITCH_SECRET مضبوط (طول=${#KILL_SWITCH_SECRET})"
fi

# ═══════════════════════════════════════════════════════════════
hdr "5. فحص متغيرات بيئة Binance Testnet"
# ═══════════════════════════════════════════════════════════════

if [ -z "${BINANCE_TESTNET_KEY:-}" ]; then
    c_ylw "⚠️  BINANCE_TESTNET_KEY غير مضبوط في البيئة."
    c_ylw "   يمكن تمريره عبر --api-key مباشرة."
else
    c_grn "✅ BINANCE_TESTNET_KEY موجود (طول=${#BINANCE_TESTNET_KEY})"
fi

if [ -z "${BINANCE_TESTNET_SECRET:-}" ]; then
    c_ylw "⚠️  BINANCE_TESTNET_SECRET غير مضبوط."
else
    c_grn "✅ BINANCE_TESTNET_SECRET موجود (طول=${#BINANCE_TESTNET_SECRET})"
fi

# ═══════════════════════════════════════════════════════════════
hdr "6. أمر Testnet القياسي (abl8b-equivalent)"
# ═══════════════════════════════════════════════════════════════

RUN_CMD=(
    python3 "$MAIN_FILE"
    --mode testnet
    --api-key "\${BINANCE_TESTNET_KEY}"
    --api-secret "\${BINANCE_TESTNET_SECRET}"
    --capital 100
    --nassets 100
    --timeframe 4h
    --no-fixed-price
    --no-trailing
    --history-days 730
    --trade-log trades_log_testnet.jsonl
)

echo
echo "الأمر:"
echo
printf '  %s \\\n' "${RUN_CMD[@]}" | sed '$ s/ \\$//'
echo
c_blu "ملاحظات:"
echo "  • لا يُمرَّر --no-watch (لا يفعل شيئاً تقنياً)"
echo "  • --no-trailing لأن Trailing يُدمّر 99.6% من الربح (مشكلة #1)"
echo "  • --no-fixed-price لأن abl8b رُوِّض بهذه الطريقة"
echo "  • --history-days 730 مطابق للباكتيست"
echo

# ═══════════════════════════════════════════════════════════════
hdr "7. ملخص جاهزية الإقلاع"
# ═══════════════════════════════════════════════════════════════

READY=1
[ -z "${BINANCE_TESTNET_KEY:-}" ]    && { c_red "   ❌ API key مفقود"; READY=0; }
[ -z "${BINANCE_TESTNET_SECRET:-}" ] && { c_red "   ❌ API secret مفقود"; READY=0; }
[ -z "${KILL_SWITCH_SECRET:-}" ]     && { c_ylw "   ⚠️  Kill Switch secret مفقود (اختياري لكن موصى به)"; }

if [ "$READY" -eq 1 ]; then
    c_grn "   ✅ جاهز للإقلاع"
else
    c_red "   ❌ غير جاهز — اضبط المتغيرات الناقصة أولاً"
fi

# ═══════════════════════════════════════════════════════════════
hdr "8. التنفيذ"
# ═══════════════════════════════════════════════════════════════

if [ "$DO_RUN" -eq 0 ]; then
    c_blu "ℹ️  وضع الإعداد فقط. لم أُشغّل Testnet."
    c_blu "   أعد التشغيل بـ --run للتنفيذ:"
    echo
    echo "   bash preflight_testnet.sh --run"
    echo
    exit 0
fi

if [ "$READY" -eq 0 ]; then
    c_red "❌ لا أستطيع التشغيل — المتغيرات ناقصة."
    exit 4
fi

c_grn "🚀 تشغيل Testnet..."
echo

# تشغيل مع tee لحفظ السجل
python3 "$MAIN_FILE" \
    --mode testnet \
    --api-key "$BINANCE_TESTNET_KEY" \
    --api-secret "$BINANCE_TESTNET_SECRET" \
    --capital 100 \
    --nassets 100 \
    --timeframe 4h \
    --no-fixed-price \
    --no-trailing \
    --history-days 730 \
    --trade-log trades_log_testnet.jsonl \
    2>&1 | tee "$LOG_OUT"
