#!/usr/bin/env bash
set -e
mkdir -p results

# 4a & 4b: apply patches
python3 apply_abl4a.py
python3 apply_abl4b.py

# 4c: no code patch — use trading_2.py (3c) with TRAIL enabled

# ── 4a: PARTIAL_TP_R = 1.5, no trailing ──
echo "════════ RUN abl4a ════════"
python3 trading_2_abl4a.py \
    --mode backtest --capital 100 --nassets 100 \
    --maxcon 5 --timeframe 4h --no-fixed-price --no-trailing \
    --history-days 730 --no-cache \
    --trade-log results/trades_abl4a.jsonl \
    2>&1 | tee results/bt_abl4a.log

# ── 4b: BREAKEVEN_AT_R = 0.5, no trailing ──
echo "════════ RUN abl4b ════════"
python3 trading_2_abl4b.py \
    --mode backtest --capital 100 --nassets 100 \
    --maxcon 5 --timeframe 4h --no-fixed-price --no-trailing \
    --history-days 730 --no-cache \
    --trade-log results/trades_abl4b.jsonl \
    2>&1 | tee results/bt_abl4b.log

# ── 4c: TRAIL enabled, no other change ──
echo "════════ RUN abl4c ════════"
python3 trading_2.py \
    --mode backtest --capital 100 --nassets 100 \
    --maxcon 5 --timeframe 4h --no-fixed-price \
    --history-days 730 --no-cache \
    --trade-log results/trades_abl4c.jsonl \
    2>&1 | tee results/bt_abl4c.log

echo "════════ SUMMARY ════════"
for TAG in 4a 4b 4c; do
    echo "--- abl${TAG} ---"
    grep -E "E\[ln|MaxDrawdown|PF|نسبة النجاح|عدد الصفقات|شارب|رأس المال" \
        results/bt_abl${TAG}.log | head -10
done
