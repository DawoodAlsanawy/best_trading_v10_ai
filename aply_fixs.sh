#!/usr/bin/env bash
# Usage: ./apply_fixes.sh [path/to/trading_2_live4.py]
set -euo pipefail
SRC="${1:-trading_2_live4.py}"; D="$(cd "$(dirname "$0")" && pwd)"
echo "[1/3] Applying REV-FIX v1 to $SRC (backup is created automatically)"
python3 "$D/apply_reversal_fixes.py" "$SRC" --inplace
echo "[2/3] Running behavioral tests"
python3 "$D/test_revfix.py" "$SRC"
echo "[3/3] DONE"
