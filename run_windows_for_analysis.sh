#!/bin/bash
# يجمع trade logs من 3 نوافذ مستقلة
set -e

cd ~/all/projects/AI/best_trading_v10_ai

for YEAR in 2024 2025 2026; do
    END_DATE="${YEAR}-12-31"
    if [ "$YEAR" = "2026" ]; then
        END_DATE="2026-10-01"
    fi

    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  Window ${YEAR} (end-date: ${END_DATE})"
    echo "═══════════════════════════════════════════════════"

    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 \
    python3 trading_2.py \
        --mode backtest --capital 100 --nassets 100 \
        --timeframe 4h --no-fixed-price --no-trailing \
        --end-date "$END_DATE" --history-days 365 \
        --no-cache \
        --trade-log "results/trades_${YEAR}.jsonl" \
        2>&1 | tee "results/window_${YEAR}_full.log" | tail -6
done

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅ Done. Files:"
echo "═══════════════════════════════════════════════════"
ls -la results/trades_*.jsonl
