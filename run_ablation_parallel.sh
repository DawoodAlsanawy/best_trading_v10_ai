#!/bin/bash
cd "$(dirname "$0")"
OUT_DIR="results/ablation_v2"
mkdir -p "$OUT_DIR"

WINDOWS=("2024-12-31:2024" "2025-12-31:2025" "2026-10-01:2026")
CONFIGS=(
    "A_full:"
    "B_no_apex:--no-apex"
    "D_pure_signal:--no-apex --no-partial --no-breakeven"
)

run_one() {
    local END="$1" YEAR="$2" NAME="$3" FLAGS="$4"
    local LOG="${OUT_DIR}/${YEAR}_${NAME}.log"
    local TRADES="${OUT_DIR}/${YEAR}_${NAME}.jsonl"
    echo "[START] $YEAR $NAME"
    OMP_NUM_THREADS=1 timeout 900 python3 trading_2.py \
        --mode backtest --capital 100 --nassets 100 \
        --timeframe 4h --no-fixed-price --no-trailing \
        --end-date "$END" --history-days 365 \
        --no-cache $FLAGS \
        --trade-log "$TRADES" > "$LOG" 2>&1
    echo "[DONE] $YEAR $NAME"
}

for w in "${WINDOWS[@]}"; do
    END="${w%%:*}"; YEAR="${w##*:}"
    for c in "${CONFIGS[@]}"; do
        NAME="${c%%:*}"; FLAGS="${c#*:}"
        ( run_one "$END" "$YEAR" "$NAME" "$FLAGS" ) &
        while [ "$(jobs -r | wc -l)" -ge 3 ]; do sleep 2; done
    done
done
wait

echo "════════ Done. Results in $OUT_DIR ════════"
