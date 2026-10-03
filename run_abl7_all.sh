#!/usr/bin/env bash
set -e
mkdir -p results

python3 apply_abl7a.py
python3 apply_abl7b.py
python3 apply_abl7c.py

for TAG in 7a 7b 7c; do
    echo "════════ RUN abl${TAG} ════════"
    python3 trading_2_abl${TAG}.py \
        --mode backtest --capital 100 --nassets 100 \
        --timeframe 4h --no-fixed-price --no-trailing \
        --history-days 730 --no-cache \
        --trade-log results/trades_abl${TAG}.jsonl \
        2>&1 | tee results/bt_abl${TAG}.log
    echo "  --- exit breakdown ---"
    grep -A 8 "توزيع أسباب الخروج" results/bt_abl${TAG}.log
done

echo "════════ SUMMARY ════════"
for TAG in 7a 7b 7c; do
    echo "--- abl${TAG} ---"
    grep -E "E\[ln|MaxDrawdown|PF|نسبة النجاح|عدد الصفقات|شارب|رأس المال" \
        results/bt_abl${TAG}.log | head -10
done
