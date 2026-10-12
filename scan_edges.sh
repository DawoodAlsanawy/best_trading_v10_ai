#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  scan_edges.sh — pure-edge sweep for BUY and SELL
#  All adaptive exits OFF: no trail, no apex, no breakeven, no partial
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

TF="${1:-4h}"
HIST="${2:-90}"
NASSETS="${3:-20}"

echo "═══════════════════════════════════════════════════════════"
echo "  Edge sweep: tf=$TF hist=$HIST nassets=$NASSETS"
echo "  Exits OFF: trail / apex / breakeven / partial"
echo "═══════════════════════════════════════════════════════════"

# Fresh CSV each run
rm -f edges_scan.csv

for Z in 0.5 1.0 1.5 2.0 2.5 3.0; do
    echo ""
    echo "──── z_min=$Z ────"
    python brain_raw.py \
        --side BOTH \
        --z-min "$Z" \
        --timeframe "$TF" \
        --history-days "$HIST" \
        --nassets "$NASSETS" \
        --no-trail \
        --no-apex \
        --no-breakeven \
        --no-partial \
        --tag "pure_z${Z}_${TF}_${HIST}d" \
        2>&1 | tail -25
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ Scan complete → edges_scan.csv"
echo "═══════════════════════════════════════════════════════════"
