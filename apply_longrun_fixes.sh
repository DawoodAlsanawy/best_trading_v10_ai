#!/usr/bin/env bash
# Usage: ./apply_longrun_fixes.sh [path/to/trading_2_live4.py]   (requires REV-FIX v1 already applied)
set -euo pipefail
SRC="${1:-trading_2_live4.py}"; D="$(cd "$(dirname "$0")" && pwd)"
echo "[1/3] Applying REV-FIX v2 to $SRC (backup is created automatically)"
python3 "$D/apply_longrun_fixes.py" "$SRC" --inplace
echo "[2/3] Running long-run tests (+ v1 regression suite)"
python3 "$D/test_longrun.py" "$SRC"
echo "[3/3] DONE"
