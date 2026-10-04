#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  ablation_event_tests.sh
#  اختبار 4 إعدادات × 3 نوافذ = 12 backtest
#  الهدف: أي إعداد يعطي أفضل Sharpe عبر السنوات الثلاث؟
# ═══════════════════════════════════════════════════════════════

set -e
cd ~/all/projects/AI/best_trading_v10_ai
mkdir -p results/ablation

echo "═══════════════════════════════════════════════════════════════"
echo "  Event-Driven Ablation"
echo "  4 variants × 3 windows = 12 backtests"
echo "═══════════════════════════════════════════════════════════════"

# Variants (as CLI flag combinations)
declare -A VARIANTS
VARIANTS[baseline]=""                                    # current
VARIANTS[buy_only]="--gauge-disable-sell"                 # remove SELL
VARIANTS[min_score_4]="--min-score 4"                     # stricter filter
VARIANTS[sell_085]="--gauge-sell-pct 0.85"                # abl7a restore

for VARIANT in baseline buy_only min_score_4 sell_085; do
    FLAGS="${VARIANTS[$VARIANT]}"

    for YEAR in 2024 2025 2026; do
        END_DATE="${YEAR}-12-31"
        [ "$YEAR" = "2026" ] && END_DATE="2026-10-01"

        LOG="results/ablation/${VARIANT}_${YEAR}.log"
        TRADES="results/ablation/${VARIANT}_${YEAR}.jsonl"

        echo ""
        echo "─────────────────────────────────────────────────"
        echo "  Variant: $VARIANT  |  Year: $YEAR"
        echo "  Flags: $FLAGS"
        echo "─────────────────────────────────────────────────"

        OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
        MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
        VECLIB_MAXIMUM_THREADS=1 \
        python3 trading_2.py \
            --mode backtest --capital 100 --nassets 100 \
            --timeframe 4h --no-fixed-price --no-trailing \
            --end-date "$END_DATE" --history-days 365 \
            $FLAGS \
            --trade-log "$TRADES" \
            2>&1 | tee "$LOG" | grep -E "شارب|نهائي:|E\[ln" || true
    done
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ✅ All backtests done"
echo "═══════════════════════════════════════════════════════════════"
ls -la results/ablation/*.jsonl | wc -l
