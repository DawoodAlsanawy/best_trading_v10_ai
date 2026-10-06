#!/bin/bash
# ============================================================
# run_ablation_v2.sh — عزل حافة الإشارة
# ============================================================
# 6 configs × 3 نوافذ = 18 تشغيل
# الوقت المتوقع: ~90 دقيقة
# ============================================================

set -e
cd "$(dirname "$0")"

OUT_DIR="results/ablation_v2"
mkdir -p "$OUT_DIR"

# النوافذ
declare -a WINDOWS=(
    "2024-12-31:2024"
    "2025-12-31:2025"
    "2026-10-01:2026"
)

# الحالات
declare -a CONFIGS=(
    "A_full:"
    "B_no_apex:--no-apex"
    "C_no_apex_partial:--no-apex --no-partial"
    "D_pure_signal:--no-apex --no-partial --no-breakeven"
    "E_tp3:--no-apex --no-partial --no-breakeven --tp-mult 3.0"
    "F_tp1.5:--no-apex --no-partial --no-breakeven --tp-mult 1.5"
)

TOTAL=$((${#WINDOWS[@]} * ${#CONFIGS[@]}))
N=0
START_TIME=$(date +%s)

echo "======================================================================"
echo "  Ablation v2 — SELL edge isolation"
echo "  ${TOTAL} runs expected (${#WINDOWS[@]} windows × ${#CONFIGS[@]} configs)"
echo "======================================================================"

for w in "${WINDOWS[@]}"; do
    END_DATE="${w%%:*}"
    YEAR="${w##*:}"

    for c in "${CONFIGS[@]}"; do
        NAME="${c%%:*}"
        FLAGS="${c#*:}"
        N=$((N+1))

        LOG="${OUT_DIR}/${YEAR}_${NAME}.log"
        TRADES="${OUT_DIR}/${YEAR}_${NAME}.jsonl"

        ELAPSED=$(( $(date +%s) - START_TIME ))
        echo ""
        echo "────── [${N}/${TOTAL}] ${YEAR} ${NAME} (elapsed: ${ELAPSED}s) ──────"

        OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
        NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
        python3 trading_2.py \
            --mode backtest --capital 100 --nassets 100 \
            --timeframe 4h --no-fixed-price --no-trailing \
            --end-date "$END_DATE" --history-days 365 \
            --no-cache \
            $FLAGS \
            --trade-log "$TRADES" \
            > "$LOG" 2>&1

        # استخراج سريع
        SHARPE=$(grep -oP "شارب \(سنوي\)\s+:\s+\K[\d.\-]+" "$LOG" | head -1)
        FINAL=$(grep -oP "نهائي:\s+\\\$\K[\d,.]+" "$LOG" | head -1)
        echo "  Sharpe: ${SHARPE:-?}  Final: \$${FINAL:-?}"
    done
done

echo ""
echo "======================================================================"
echo "  ✅ Done in $(( $(date +%s) - START_TIME ))s"
echo "  Logs: $OUT_DIR"
echo "======================================================================"
