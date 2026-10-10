#!/bin/bash
# 7 SELL strategies × 3 years = 21 backtests
set -e
cd ~/all/projects/AI/best_trading_v10_ai
mkdir -p results/sell_ablation

# Strategy definitions (CLI flags)
S1="--enable-sell --sell-gauge-pct 0.95"
S2="--enable-sell --sell-gauge-pct 0.98"
S3="--enable-sell --sell-min-score 5 --sell-gauge-pct 0.95"
S4="--enable-sell --sell-min-zdev 2.5 --sell-gauge-pct 0.95"
S5="--enable-sell --sell-require-ema-down --sell-gauge-pct 0.95"
S6="--enable-sell --sell-major-only --sell-gauge-pct 0.95"
S7="--enable-sell --sell-min-atr-frac 0.02 --sell-gauge-pct 0.95"

for SID in 1 2 3 4 5 6 7; do
    eval "FLAGS=\$S$SID"
    for YEAR in 2024 2025 2026; do
        END="${YEAR}-12-31"
        [ "$YEAR" = "2026" ] && END="2026-10-01"
        echo "═══ S$SID / $YEAR ═══"
        OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
        MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
        VECLIB_MAXIMUM_THREADS=1 \
        python3 trading_2.py \
            --mode backtest --capital 100 --nassets 100 \
            --timeframe 4h --no-fixed-price --no-trailing \
            --end-date "$END" --history-days 365 \
            $FLAGS \
            --trade-log "results/sell_ablation/S${SID}_${YEAR}.jsonl" \
            2>&1 | tee "results/sell_ablation/S${SID}_${YEAR}.log" \
                  | grep -E "شارب|نهائي:" || true
    done
done
echo "✅ Done"
