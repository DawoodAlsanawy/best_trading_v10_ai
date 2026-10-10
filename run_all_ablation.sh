#!/bin/bash
# ============================================================
# run_all_ablation.sh — كل شيء في سكربت واحد، تسلسلي، آمن
#
# يقوم بكل شيء:
#   1. يتحقق من وجود الـ flags
#   2. يُشغّل 18 اختباراً بالتسلسل (1 في المرة)
#   3. يحفظ log + trades لكل حالة
#   4. يُنظّف الذاكرة بين التشغيلات
#   5. يُحلّل النتائج تلقائياً
#   6. يعرض جدول نهائي
#
# الوقت المتوقع: 2.5-4 ساعات
# RAM المتوقعة: 2-3 GB (تسلسلي، لا crash)
# ============================================================

set -u
cd "$(dirname "$0")"

# ═══ الإعدادات ═══
OUT_DIR="results/ablation_v2"
LOG_DIR="$OUT_DIR/logs"
TRADES_DIR="$OUT_DIR/trades"
MAIN_LOG="results/ablation_master.log"
PY="python3"
TIMEOUT_PER_RUN=1200  # 20 دقيقة لكل اختبار

# ═══ التحقق من الـ flags أولاً ═══
echo "═══════════════════════════════════════════════════════"
echo "  Step 0: التحقق من وجود ablation flags"
echo "═══════════════════════════════════════════════════════"

if ! grep -q "no-apex" trading_2.py; then
    echo "❌ flags غير موجودة. شغّل add_ablation_flags_v2.py أولاً"
    exit 1
fi

FLAG_COUNT=$(grep -c "no-apex\|no-partial\|no-breakeven\|tp-mult\|sell-only" trading_2.py)
echo "  ✅ وُجدت ${FLAG_COUNT} مرجع للـ flags"
echo ""

# ═══ إنشاء المجلدات ═══
mkdir -p "$OUT_DIR" "$LOG_DIR" "$TRADES_DIR"

# ═══ تسجيل بداية ═══
START_TIME=$(date +%s)
echo "═══════════════════════════════════════════════════════" | tee "$MAIN_LOG"
echo "  Ablation Run — $(date)" | tee -a "$MAIN_LOG"
echo "  Sequential mode (1 run at a time)" | tee -a "$MAIN_LOG"
echo "═══════════════════════════════════════════════════════" | tee -a "$MAIN_LOG"
echo "" | tee -a "$MAIN_LOG"

# ═══ المصفوفة ═══
WINDOWS=(
    "2024-12-31:2024"
    "2025-12-31:2025"
    "2026-10-01:2026"
)
CONFIGS=(
    "A_full:"
    "B_no_apex:--no-apex"
    "C_no_apex_partial:--no-apex --no-partial"
    "D_pure_signal:--no-apex --no-partial --no-breakeven"
    "E_tp3:--no-apex --no-partial --no-breakeven --tp-mult 3.0"
    "F_tp1.5:--no-apex --no-partial --no-breakeven --tp-mult 1.5"
)

TOTAL=$((${#WINDOWS[@]} * ${#CONFIGS[@]}))
N=0
SUCCESS=0
FAIL=0

# ═══ الدالة الرئيسية ═══
run_one() {
    local END_DATE="$1" YEAR="$2" NAME="$3" FLAGS="$4"
    local LOG="${LOG_DIR}/${YEAR}_${NAME}.log"
    local TRADES="${TRADES_DIR}/${YEAR}_${NAME}.jsonl"

    # تخطّي إذا كان موجوداً ومكتمل
    if [ -f "$LOG" ] && grep -q "اكتمل" "$LOG" 2>/dev/null; then
        local s=$(grep -oP "شارب \(سنوي\)\s+:\s+\K[\d.\-]+" "$LOG" | head -1)
        echo "[SKIP] ${YEAR} ${NAME} (done, sharpe=${s:-?})"
        return 0
    fi

    echo ""
    echo "───────────────────────────────────────────────────────"
    echo "  [${N}/${TOTAL}] ${YEAR} ${NAME}"
    echo "  flags: ${FLAGS:-none}"
    echo "  start: $(date +%H:%M:%S)"
    echo "───────────────────────────────────────────────────────"

    # تنظيف ذاكرة قبل التشغيل
    sync && echo 1 > /proc/sys/vm/drop_caches 2>/dev/null || true

    # تشغيل بأولوية منخفضة، timeout، تسلسلي
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
    nice -n 15 timeout "$TIMEOUT_PER_RUN" \
        $PY trading_2.py \
            --mode backtest --capital 100 --nassets 100 \
            --timeframe 4h --no-fixed-price --no-trailing \
            --end-date "$END_DATE" --history-days 365 \
            --no-cache $FLAGS \
            --trade-log "$TRADES" \
            > "$LOG" 2>&1

    local rc=$?

    if [ $rc -eq 0 ] && grep -q "اكتمل" "$LOG"; then
        local s=$(grep -oP "شارب \(سنوي\)\s+:\s+\K[\d.\-]+" "$LOG" | head -1)
        local f=$(grep -oP "نهائي:\s+\\\$\K[\d,.]+" "$LOG" | head -1)
        echo "  ✅ DONE — Sharpe: ${s:-?}  Final: \$${f:-?}"
        echo "[DONE] ${YEAR} ${NAME} sharpe=${s} final=${f}" | tee -a "$MAIN_LOG"
        SUCCESS=$((SUCCESS+1))
    elif [ $rc -eq 124 ]; then
        echo "  ⏱️  TIMEOUT after ${TIMEOUT_PER_RUN}s"
        echo "[TIMEOUT] ${YEAR} ${NAME}" | tee -a "$MAIN_LOG"
        FAIL=$((FAIL+1))
    else
        echo "  ❌ FAIL (exit=$rc)"
        tail -3 "$LOG" | sed 's/^/     /'
        echo "[FAIL] ${YEAR} ${NAME} exit=$rc" | tee -a "$MAIN_LOG"
        FAIL=$((FAIL+1))
    fi

    # تنظيف ذاكرة بعد التشغيل
    sleep 5
}

# ═══ الحلقة الرئيسية ═══
for w in "${WINDOWS[@]}"; do
    END_DATE="${w%%:*}"
    YEAR="${w##*:}"
    for c in "${CONFIGS[@]}"; do
        NAME="${c%%:*}"
        FLAGS="${c#*:}"
        N=$((N+1))
        run_one "$END_DATE" "$YEAR" "$NAME" "$FLAGS"

        # تقدم
        ELAPSED=$(( $(date +%s) - START_TIME ))
        echo "  [Progress: ${N}/${TOTAL}, elapsed: $((ELAPSED/60))m]"
    done
done

# ═══ الملخّص ═══
TOTAL_TIME=$(( $(date +%s) - START_TIME ))
echo ""
echo "═══════════════════════════════════════════════════════" | tee -a "$MAIN_LOG"
echo "  ✅ اكتمل التشغيل" | tee -a "$MAIN_LOG"
echo "  Success: $SUCCESS / $TOTAL" | tee -a "$MAIN_LOG"
echo "  Failed:  $FAIL / $TOTAL" | tee -a "$MAIN_LOG"
echo "  Time:    $((TOTAL_TIME/60)) minutes" | tee -a "$MAIN_LOG"
echo "═══════════════════════════════════════════════════════" | tee -a "$MAIN_LOG"

# ═══ التحليل التلقائي ═══
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  تشغيل التحليل ..."
echo "═══════════════════════════════════════════════════════"

# نسخ results للشكل الذي يتوقعه analyze_ablation_v2.py
mkdir -p results/ablation_v2/_compat
for f in "$LOG_DIR"/*.log; do
    [ -f "$f" ] && cp "$f" "results/ablation_v2/$(basename "$f")"
done

if [ -f analyze_ablation_v2.py ]; then
    python3 analyze_ablation_v2.py 2>&1 | tee results/ablation_v2_analysis.log
else
    echo "⚠️  analyze_ablation_v2.py غير موجود — تخطّي التحليل"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  انتهى كل شيء."
echo "  Logs:    $LOG_DIR"
echo "  Trades:  $TRADES_DIR"
echo "  Master:  $MAIN_LOG"
echo "  Analysis: results/ablation_v2_analysis.log"
echo "═══════════════════════════════════════════════════════"
