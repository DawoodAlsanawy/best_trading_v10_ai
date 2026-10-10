#!/usr/bin/env bash
# run_rr_grid_fast.sh — 50 assets, serial
set -e
mkdir -p results/rr_grid_fast
cd "$(dirname "$0")"

export NUMBA_NUM_THREADS=2
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

for TAG in A1 A2 A3 B1 B2 B3 C1 C2 C3; do
    echo "════════ [$(date +%H:%M:%S)] START ${TAG} ════════"
    python3 "trading_2_rr_${TAG}.py" \
        --mode backtest --capital 100 --nassets 50 \
        --timeframe 4h --no-fixed-price --no-trailing \
        --history-days 730 --no-cache \
        --trade-log "results/rr_grid_fast/trades_rr_${TAG}.jsonl" \
        > "results/rr_grid_fast/bt_rr_${TAG}.log" 2>&1
    echo "════════ [$(date +%H:%M:%S)] DONE  ${TAG} ════════"
    sync
    sleep 2
done

echo "ALL DONE"
