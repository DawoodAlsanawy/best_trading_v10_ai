#!/bin/bash
# ============================================================
# run_missing_parallel.sh — يُشغّل الحالات الناقصة بالتوازي
# 4 workers, ~20 دقيقة للـ 15 حالة المتبقية
# ============================================================

cd "$(dirname "$0")"
OUT_DIR="results/ablation_v2"
mkdir -p "$OUT_DIR"

# ═══ دوال التشغيل (خارج السكربت الرئيسي) ═══

run_one() {
    local END_DATE="$1" YEAR="$2" NAME="$3" FLAGS="$4"
    local LOG="${OUT_DIR}/${YEAR}_${NAME}.log"
    local TRADES="${OUT_DIR}/${YEAR}_${NAME}.jsonl"

    # تخطّي إذا كان الملف موجوداً ومكتمل
    if [ -f "$LOG" ] && grep -q "اكتمل" "$LOG" 2>/dev/null; then
        echo "[SKIP] ${YEAR} ${NAME} (already done)"
        return 0
    fi

    echo "[START] ${YEAR} ${NAME} pid=$$"
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
    timeout 900 python3 trading_2.py \
        --mode backtest --capital 100 --nassets 100 \
        --timeframe 4h --no-fixed-price --no-trailing \
        --end-date "$END_DATE" --history-days 365 \
        --no-cache $FLAGS \
        --trade-log "$TRADES" \
        > "$LOG" 2>&1

    local rc=$?
    if [ $rc -eq 0 ]; then
        local s=$(grep -oP "شارب \(سنوي\)\s+:\s+\K[\d.\-]+" "$LOG" | head -1)
        echo "[DONE] ${YEAR} ${NAME} sharpe=${s}"
    else
        echo "[FAIL] ${YEAR} ${NAME} exit=$rc"
    fi
}

export -f run_one
export OUT_DIR

# ═══ بناء قائمة المهام ═══

TASKFILE=$(mktemp)
trap "rm -f $TASKFILE" EXIT

WINDOWS=("2024-12-31|2024" "2025-12-31|2025" "2026-10-01|2026")
CONFIGS=(
    "A_full|"
    "B_no_apex|--no-apex"
    "C_no_apex_partial|--no-apex --no-partial"
    "D_pure_signal|--no-apex --no-partial --no-breakeven"
    "E_tp3|--no-apex --no-partial --no-breakeven --tp-mult 3.0"
    "F_tp1.5|--no-apex --no-partial --no-breakeven --tp-mult 1.5"
)

for w in "${WINDOWS[@]}"; do
    END="${w%%|*}"; YEAR="${w##*|}"
    for c in "${CONFIGS[@]}"; do
        NAME="${c%%|*}"; FLAGS="${c#*|}"
        echo "${END}|${YEAR}|${NAME}|${FLAGS}" >> "$TASKFILE"
    done
done

TOTAL=$(wc -l < "$TASKFILE")
echo "═══════════════════════════════════════════════════════"
echo "  Total tasks: ${TOTAL}"
echo "  Parallel workers: 4"
echo "  Output: ${OUT_DIR}"
echo "═══════════════════════════════════════════════════════"
echo ""

# ═══ تشغيل بالتوازي ═══

START=$(date +%s)

while IFS='|' read -r END YEAR NAME FLAGS; do
    # انتظر إذا كان عدد المهام النشطة ≥ 4
    while [ "$(jobs -r | wc -l)" -ge 4 ]; do
        sleep 2
    done
    run_one "$END" "$YEAR" "$NAME" "$FLAGS" &
done < "$TASKFILE"

wait

ELAPSED=$(( $(date +%s) - START ))
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ Completed in ${ELAPSED}s ($((ELAPSED/60))m)"
echo "═══════════════════════════════════════════════════════"

# ═══ ملخّص سريع ═══

echo ""
echo "  Files present:"
ls -1 "$OUT_DIR"/*.log 2>/dev/null | wc -l
echo "  Expected: 18"
