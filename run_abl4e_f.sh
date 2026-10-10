#!/usr/bin/env bash
set -e
mkdir -p results

# Ensure 4a is installed first
[ -f trading_2_abl4a.py ] && cp trading_2_abl4a.py trading_2.py

python3 apply_abl4e.py
python3 apply_abl4f.py

for TAG in 4e 4f; do
    echo "════════ RUN abl${TAG} ════════"
    python3 trading_2_abl${TAG}.py \
        --mode backtest --capital 100 --nassets 100 \
        --maxcon 5 --timeframe 4h --no-fixed-price --no-trailing \
        --history-days 730 --no-cache \
        --trade-log results/trades_abl${TAG}.jsonl \
        2>&1 | tee results/bt_abl${TAG}.log
done

echo "════════ SUMMARY ════════"
for TAG in 4e 4f; do
    echo "--- abl${TAG} ---"
    grep -E "E\[ln|MaxDrawdown|PF|نسبة النجاح|عدد الصفقات|شارب" \
        results/bt_abl${TAG}.log | head -8
done
