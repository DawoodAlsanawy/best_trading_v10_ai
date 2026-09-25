#!/usr/bin/env bash
# =============================================================
# extract_code.sh — استخراج الدوال والأقسام الحرجة من trading.py
# الاستخدام:  ./extract_code.sh [path/to/trading.py]
# =============================================================

SRC="${1:-trading.py}"
OUT="trading_extract.txt"

if [[ ! -f "$SRC" ]]; then
    echo "❌ not found: $SRC"
    exit 1
fi

python3 - "$SRC" "$OUT" <<'PYEOF'
import sys, re
from datetime import datetime, timezone

src_path = sys.argv[1]
out_path = sys.argv[2]

with open(src_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

total = len(lines)

def find_block(name):
    """Return (start, end) for the top-level `def name` or `class name`."""
    start = None
    for i, line in enumerate(lines):
        if re.match(r'^(def|class)\s+' + re.escape(name) + r'\b', line):
            start = i
            break
    if start is None:
        return None
    end = total
    for j in range(start + 1, total):
        line = lines[j]
        if re.match(r'^(def|class)\s+', line):
            end = j
            break
        if re.match(r'^@', line) and j + 1 < total and \
           re.match(r'^(def|class)\s+', lines[j + 1]):
            end = j
            break
    return (start, end)

def find_between(start_sub, end_sub, max_len=2000):
    """Return (start, end) between two substrings."""
    start = None
    for i, line in enumerate(lines):
        if start_sub in line:
            start = i
            break
    if start is None:
        return None
    limit = min(total, start + max_len)
    for j in range(start + 1, limit):
        if end_sub in lines[j]:
            return (start, j)
    return (start, limit)

def write_block(w, title, start, end):
    w.write("\n" + "─" * 72 + "\n")
    w.write(f"  {title}   (lines {start + 1}–{end})\n")
    w.write("─" * 72 + "\n")
    w.writelines(lines[start:end])

# ══ الدوال والمكونات المطلوبة ═══════════════════════════════
TOP_BLOCKS = [
    "Config",
    "_compute_entry_dip",
    "_regime_entry_mult",
    "_find_nearest_swing",
    "compute_geodesic_stop",
    "compute_geodesic_target",
    "compute_geodesic_kelly",
    "compute_dynamic_leverage",
    "build_signals",
    "process_asset",
    "compute_entropy_friction",
    "_advance",
    "simulate_portfolio",
    "_promote_pending_to_position",
    "place_pending_entry",
    "monitor_pending_orders",
    "compute_portfolio_risk_frac",
    "cap_notional",
    "_compute_advanced_trail_core",
    "compute_advanced_trail",
    "_taker_slippage_bps",
    "_exit_is_taker",
    "apply_slippage",
    "_backtest_entry_target",
    "precompute_entry_fills",
]

with open(out_path, 'w', encoding='utf-8') as w:
    w.write("=" * 72 + "\n")
    w.write(f"  EXTRACT: {src_path}\n")
    w.write(f"  DATE: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
    w.write(f"  TOTAL LINES: {total}\n")
    w.write("=" * 72 + "\n")

    for name in TOP_BLOCKS:
        r = find_block(name)
        if r is None:
            w.write(f"\n### NOT FOUND: {name} ###\n")
            continue
        write_block(w, f"BLOCK: {name}", r[0], r[1])

    # ══ أقسام run_live الحرجة ═══════════════════════════════
    r = find_between("اقتناص ودخول صفقات جديدة", "استرخاء المحرك", max_len=1500)
    if r:
        write_block(w, "RUN_LIVE — ENTRY SECTION", r[0], r[1])
    else:
        w.write("\n### run_live entry section not found ###\n")

    r = find_between("# ── Execute exit ──", "# 2.", max_len=300)
    if r:
        write_block(w, "RUN_LIVE — EXIT SECTION", r[0], r[1])

    # ══ Version markers ══════════════════════════════════════
    w.write("\n\n" + "=" * 72 + "\n")
    w.write("  VERSION MARKERS\n")
    w.write("=" * 72 + "\n")
    text = "".join(lines)
    markers = [
        "SL_WIDEN_MULT", "TP_R_MULT", "SL_R_MULT", "MAX_SL_FRAC_LIVE",
        "SUBBARS_ENABLED", "ENTRY_ATR_MULT", "ENTRY_TIME_DECAY_ENABLED",
        "K_SKIP_IF_DEGENERATE", "K_DEGENERATE_H_RATIO",
        "DH_ENTROPY_Z", "DF_FREE_E_Z",
        "DH_ENTROPY_THRESHOLD", "DF_FREE_E_THRESHOLD",
        "USE_ABSOLUTE_THRESHOLDS",
        "MIN_SCORE: int",
        "MAKER_FEE", "TAKER_FEE",
        "_compute_entry_dip", "friction_drag = fric_val",
        "LIQ_ENABLED", "PROTECTIVE_ORDERS_ENABLED",
        "_place_protective_orders", "LIVE_PRICE_ENABLED",
        "BREAKEVEN_ENABLED", "TRAIL_ADVANCED_ENABLED",
        "TRAIL_CHANDELIER_K", "TRAIL_LEGACY_FLOOR_ENABLED",
        "TRAIL_RATCHET_LEVELS",
        "MAX_SL_FRAC_LIVE",
        "PO_FIXED_PRICE",
        "PENDING_ENABLED",
    ]
    for m in markers:
        cnt = text.count(m)
        w.write(f"  {m:<45s} : {cnt}\n")

    w.write("\n" + "=" * 72 + "\n")
    w.write("  END OF EXTRACT\n")
    w.write("=" * 72 + "\n")

print(f"✅ Wrote: {out_path}")
PYEOF

echo "─────────────────────────────────────────────────────────"
echo "Lines : $(wc -l < "$OUT")"
echo "Size  : $(du -h "$OUT" | cut -f1)"
echo "─────────────────────────────────────────────────────────"
echo "Send this file: $OUT"
