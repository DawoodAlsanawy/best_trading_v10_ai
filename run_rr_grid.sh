#!/usr/bin/env bash
# run_rr_grid.sh — SERIAL with memory guard
set -e
mkdir -p results/rr_grid
cd "$(dirname "$0")"

# تحقق من الملفات
for TAG in A1 A2 A3 B1 B2 B3 C1 C2 C3; do
    [ -f "trading_2_rr_${TAG}.py" ] || {
        echo "MISSING: trading_2_rr_${TAG}.py" >&2
        exit 1
    }
done

# انتظار ذكي: يتوقف حتى يتوفر X MB
mem_wait() {
    local need_mb="${1:-2000}"
    while :; do
        local free_mb
        free_mb=$(free -m | awk '/^Mem:/{print $7}')
        if [ "$free_mb" -ge "$need_mb" ]; then
            echo "  [mem] free=${free_mb} MB — OK"
            return 0
        fi
        echo "  [mem-wait] free=${free_mb} MB < ${need_mb} MB — sleeping 30s"
        sleep 30
    done
}

# تقليل استهلاك numba للذاكرة (multithreaded pools)
export NUMBA_NUM_THREADS=2
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

START=$(date +%s)
for TAG in A1 A2 A3 B1 B2 B3 C1 C2 C3; do
    mem_wait 2000
    echo "════════ [$(date +%H:%M:%S)] START ${TAG} ════════"
    python3 "trading_2_rr_${TAG}.py" \
        --mode backtest --capital 100 --nassets 100 \
        --timeframe 4h --no-fixed-price --no-trailing \
        --history-days 730 --no-cache \
        --trade-log "results/rr_grid/trades_rr_${TAG}.jsonl" \
        > "results/rr_grid/bt_rr_${TAG}.log" 2>&1
    ELAPSED=$(( $(date +%s) - START ))
    echo "════════ [$(date +%H:%M:%S)] DONE  ${TAG} (total ${ELAPSED}s) ════════"
    sync
    sleep 3
done

echo
echo "ALL DONE in $(( $(date +%s) - START ))s"
python3 analyze_rr_grid.py
