#!/usr/bin/env bash
set -e
mkdir -p results

python3 apply_abl3a.py
python3 apply_abl3b.py
python3 apply_abl3c.py
python3 apply_abl3d.py

for TAG in 3a 3b 3c 3d; do
    echo "════════ RUN abl${TAG} ════════"
    python3 trading_2_abl${TAG}.py \
        --mode backtest --capital 100 --nassets 100 \
        --maxcon 5 --timeframe 4h --no-fixed-price --no-trailing \
        --history-days 730 --no-cache \
        --trade-log results/trades_abl${TAG}.jsonl \
        2>&1 | tee results/bt_abl${TAG}.log
done

echo "════════ SUMMARY ════════"
for TAG in 3a 3b 3c 3d; do
    echo "--- abl${TAG} ---"
    grep -E "E\[ln|MaxDrawdown|PF|نسبة النجاح|عدد الصفقات|شارب" \
        results/bt_abl${TAG}.log | head -8
done
