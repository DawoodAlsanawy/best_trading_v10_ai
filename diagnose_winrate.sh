#!/bin/bash
# ════════════════════════════════════════════════════════════════
# diagnose_winrate.sh
#
# الغرض: تشخيص انخفاض Win Rate في البوت.
# يستخرج كل ما نحتاجه للحكم بدقة دون افتراضات.
#
# الاستخدام:
#   chmod +x diagnose_winrate.sh
#   ./diagnose_winrate.sh
#
# الإخراج: winrate_diagnosis_YYYYMMDD_HHMMSS.txt
# ════════════════════════════════════════════════════════════════

set +e   # لا تتوقف عند أي خطأ — اجمع كل شيء

BOT_FILE="trading.py"
TS=$(date +%Y%m%d_%H%M%S)
OUTPUT="winrate_diagnosis_${TS}.txt"

# ════════════════════════════════════════════════════════════════
# دوال مساعدة
# ════════════════════════════════════════════════════════════════

extract_function() {
    # يستخرج دالة Python بكاملها
    # $1 = اسم الدالة
    local fname="$1"
    awk -v fn="def ${fname}(" '
        $0 ~ "^"fn {
            found=1
            print
            next
        }
        found {
            # توقف عند أول def في العمود 0 (بدون إزاحة)
            if ($0 ~ /^def / || $0 ~ /^class /) {
                exit
            }
            print
        }
    ' "$BOT_FILE"
}

extract_class() {
    # يستخرج كلاس بكاملها
    local cname="$1"
    awk -v cn="class ${cname}:" '
        $0 ~ "^"cn {
            found=1
            print
            next
        }
        found {
            # توقف عند أول class أو def في العمود 0
            if ($0 ~ /^class / || $0 ~ /^def /) {
                exit
            }
            print
        }
    ' "$BOT_FILE"
}

# ════════════════════════════════════════════════════════════════
# بدء التقرير
# ════════════════════════════════════════════════════════════════

{
    echo "═══════════════════════════════════════════════════════════════════"
    echo "   WIN RATE DIAGNOSIS REPORT"
    echo "═══════════════════════════════════════════════════════════════════"
    echo "Date:      $(date)"
    echo "Hostname:  $(hostname)"
    echo "Working directory: $(pwd)"
    echo "Bot file:  ${BOT_FILE}"
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 1: BOT FILE INFO
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 1: BOT FILE INFORMATION"
    echo "═══════════════════════════════════════════════════════════════════"
    if [ -f "$BOT_FILE" ]; then
        ls -la "$BOT_FILE"
        echo "MD5:  $(md5sum $BOT_FILE | awk '{print $1}')"
        echo "SHA1: $(sha1sum $BOT_FILE | awk '{print $1}')"
        echo "Lines: $(wc -l < $BOT_FILE)"
        echo "Size:  $(wc -c < $BOT_FILE) bytes"
    else
        echo "❌ ERROR: ${BOT_FILE} NOT FOUND"
    fi
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 2: FULL CONFIG CLASS
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 2: CONFIG CLASS (all fields)"
    echo "═══════════════════════════════════════════════════════════════════"
    extract_class "Config"
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 3: CRITICAL PARAMETERS (quick reference)
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 3: CRITICAL PARAMETERS (grep)"
    echo "═══════════════════════════════════════════════════════════════════"
    for param in \
        "TP_MULT" "SL_WIDEN_MULT" "SL_REF_KAPPA" "SL_MIN_SIGMA" "SL_MAX_SIGMA" \
        "K_MAX" "K_MIN" "K_MIN_TRAIN_POINTS_PER_CLUSTER" "TRAIN_FRACTION" \
        "MIN_SCORE" "N:" "W:" "L:" "N_HOURS" "W_HOURS" "L_HOURS" \
        "SING_TIMING_ENABLED" "SING_ACTIVE_MARKETABLE" \
        "SING_FUNDING_GUARD_ENABLED" "SING_RISK_BOOST_ENABLED" \
        "SING_TIME_DETECT_ENABLED" "SING_PCT_EMERGING" "SING_PCT_ACTIVE" \
        "SING_LOOKBACK_BARS" "SING_TIME_FAR_THRESHOLD" \
        "SING_TIME_NEAR_THRESHOLD" "SING_TIME_MED_THRESHOLD" \
        "SING_TIME_RISK_BOOST_NEAR" "SING_TIME_RISK_DAMPEN" \
        "RULE_FILTER_ENABLED" "RULE_MIN_SCORE" "RULE_REJECT_RVOL24_PCT" \
        "RULE_REJECT_DIST_HIGH_PCT" "RULE_REJECT_TF_STD_PCT" \
        "RULE_REJECT_RANGE_POS_PCT" \
        "TRAIL_ENABLED" "TRAIL_DYNAMIC" "TRAIL_ACTIVATE_AT_R" \
        "PARTIAL_TP_ENABLED" "PARTIAL_TP_R" "PARTIAL_TP_PCT" \
        "MIN_RISK_PER_TRADE" "MAX_RISK_PER_TRADE" "PORTFOLIO_HEAT_MAX" \
        "CORRELATION_THRESHOLD" "MAX_CONCURRENT_ASSETS" \
        "FRICTION_DIP_KAPPA" "APEX_ENABLED" "MAX_HOLD_BARS" \
        "PO_FIXED_PRICE" "FILL_PENETRATION_BPS" \
        "UNIFIED_ENTRY_ENABLED" "UNIFIED_WAIT_BARS_1H" \
        "UNIFIED_MAX_AGE_BARS_1H" "UNIFIED_MOMENTUM_KAPPA" \
        "FILTER_ENABLED" "FILTER_MIN_VOTES" "FILTER_USE_ACTION_BIAS" \
        "FILTER_USE_EMA_SLOPE" "FILTER_USE_HIGH_ATR" \
        "FILTER_USE_FRICTION_DRAG" \
        "MIN_RISK" "MAX_RISK" "BASE_RISK" \
        "LEVERAGE_MIN" "LEVERAGE_MAX" "LEVERAGE_BASE" \
        "INITIAL_CAPITAL" "CAPITAL_FLOOR" \
        "MAX_DRAWDOWN_HALT" "DRAWDOWN_REDUCE_AT"
    do
        grep -nE "^\s*${param}" "$BOT_FILE" 2>/dev/null
    done
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 4: CACHE STATE
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 4: CACHE STATE"
    echo "═══════════════════════════════════════════════════════════════════"

    echo "--- market_data_cache/ ---"
    if [ -d "market_data_cache" ]; then
        echo "Total files: $(ls market_data_cache/ 2>/dev/null | wc -l)"
        echo "Total size:  $(du -sh market_data_cache/ 2>/dev/null | awk '{print $1}')"
        echo ""
        echo "First 20 files (with dates and sizes):"
        ls -la market_data_cache/ 2>/dev/null | head -25
        echo ""
        echo "File types breakdown:"
        ls market_data_cache/ 2>/dev/null | \
            sed -E 's/^[^_]+_[0-9]+[mhd]*(_sub)?\.parquet$/&/' | \
            grep -oE '_[0-9]+[mhd]+(_sub)?\.parquet' | \
            sort | uniq -c | sort -rn
    else
        echo "❌ market_data_cache/ NOT FOUND"
    fi
    echo ""

    echo "--- asset_cache/ ---"
    if [ -d "asset_cache" ]; then
        echo "Total files: $(ls asset_cache/ 2>/dev/null | wc -l)"
        echo "Total size:  $(du -sh asset_cache/ 2>/dev/null | awk '{print $1}')"
        echo "First 10 files:"
        ls -la asset_cache/ 2>/dev/null | head -12
    else
        echo "❌ asset_cache/ NOT FOUND"
    fi
    echo ""

    echo "--- state files (JSON) ---"
    ls -la *.json 2>/dev/null
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 5: PARSED CACHE FILES (python)
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 5: CACHE FILES — actual content (first 3 files)"
    echo "═══════════════════════════════════════════════════════════════════"

    python3 << 'PYEOF' 2>&1
import os
import glob
import pandas as pd

cache_dir = "market_data_cache"
if not os.path.isdir(cache_dir):
    print("market_data_cache/ not found")
    raise SystemExit

files = sorted(glob.glob(os.path.join(cache_dir, "*.parquet")))
if not files:
    print("No parquet files found")
    raise SystemExit

# فحص أول 5 ملفات رئيسية (بدون sub)
main_files = [f for f in files if "_sub." not in f][:5]
print(f"Total main parquet files: {len([f for f in files if '_sub.' not in f])}")
print(f"Total sub parquet files:  {len([f for f in files if '_sub.' in f])}")
print()

for fp in main_files:
    try:
        df = pd.read_parquet(fp)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        print(f"FILE: {os.path.basename(fp)}")
        print(f"  Rows:      {len(df):,}")
        print(f"  First ts:  {df.index[0]}")
        print(f"  Last ts:   {df.index[-1]}")
        span_days = (df.index[-1] - df.index[0]).total_seconds() / 86400
        print(f"  Span:      {span_days:.1f} days")
        print(f"  Columns:   {list(df.columns)}")
        print()
    except Exception as e:
        print(f"FILE: {os.path.basename(fp)} — ERROR: {e}")
        print()
PYEOF
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 6: CRITICAL FUNCTIONS
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 6: CRITICAL FUNCTIONS"
    echo "═══════════════════════════════════════════════════════════════════"

    for fn in \
        "compute_dynamic_k" \
        "compute_geodesic_stop" \
        "compute_geodesic_kelly" \
        "_resonance_state_for_direction" \
        "_estimate_explosion_dt" \
        "compute_theta_at" \
        "build_signals" \
        "precompute_entry_fills" \
        "_load_cached" \
        "_load_cached_sub"
    do
        echo "───────────────────────────────────────────────────────────────"
        echo "FUNCTION: ${fn}"
        echo "───────────────────────────────────────────────────────────────"
        extract_function "$fn"
        echo ""
    done

    # ═══════════════════════════════════════════════════════════════
    # SECTION 7: SIMULATE_PORTFOLIO (key parts)
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 7: simulate_portfolio — full"
    echo "═══════════════════════════════════════════════════════════════════"
    extract_function "simulate_portfolio"
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 8: run_backtest (key parts)
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 8: run_backtest"
    echo "═══════════════════════════════════════════════════════════════════"
    extract_function "run_backtest"
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 9: MAIN FUNCTION (argparse + setup)
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 9: main() — argparse and setup"
    echo "═══════════════════════════════════════════════════════════════════"
    extract_function "main"
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 10: RECENT TRADE LOGS
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 10: RECENT TRADE LOGS"
    echo "═══════════════════════════════════════════════════════════════════"

    for lf in trades_log_backtest.jsonl trades_log_testnet.jsonl trades_log_live.jsonl; do
        if [ -f "$lf" ]; then
            echo "--- $lf ---"
            echo "Lines: $(wc -l < $lf)"
            echo "Size:  $(du -h $lf | awk '{print $1}')"
            echo "Last modified: $(stat -c %y $lf 2>/dev/null)"
            echo ""
            echo "Last 5 records:"
            tail -5 "$lf"
            echo ""
            echo "First record (meta):"
            head -1 "$lf"
            echo ""
        fi
    done

    # ═══════════════════════════════════════════════════════════════
    # SECTION 11: RECENT RUN LOGS (if any)
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 11: RECENT RUN LOGS (.log files)"
    echo "═══════════════════════════════════════════════════════════════════"

    for lf in *.log; do
        if [ -f "$lf" ]; then
            echo "--- $lf ---"
            echo "Lines: $(wc -l < $lf)"
            echo "Last 50 lines:"
            tail -50 "$lf"
            echo ""
        fi
    done

    # ═══════════════════════════════════════════════════════════════
    # SECTION 12: GIT STATUS (if git repo)
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 12: GIT STATUS"
    echo "═══════════════════════════════════════════════════════════════════"
    if [ -d ".git" ]; then
        echo "--- git status ---"
        git status 2>&1 | head -30
        echo ""
        echo "--- last 10 commits ---"
        git log --oneline -10 2>&1
        echo ""
        echo "--- uncommitted changes in trading.py ---"
        git diff trading.py 2>&1 | head -200
        echo ""
    else
        echo "Not a git repository"
    fi
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 13: ENVIRONMENT
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 13: ENVIRONMENT"
    echo "═══════════════════════════════════════════════════════════════════"
    echo "Python: $(python3 --version 2>&1)"
    echo ""
    echo "Key packages:"
    python3 -c "
import sys
try:
    import numpy; print(f'  numpy: {numpy.__version__}')
except: print('  numpy: NOT INSTALLED')
try:
    import pandas; print(f'  pandas: {pandas.__version__}')
except: print('  pandas: NOT INSTALLED')
try:
    import sklearn; print(f'  sklearn: {sklearn.__version__}')
except: print('  sklearn: NOT INSTALLED')
try:
    import scipy; print(f'  scipy: {scipy.__version__}')
except: print('  scipy: NOT INSTALLED')
try:
    import ccxt; print(f'  ccxt: {ccxt.__version__}')
except: print('  ccxt: NOT INSTALLED')
try:
    import numba; print(f'  numba: {numba.__version__}')
except: print('  numba: NOT INSTALLED')
" 2>&1
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 14: COMMAND LINE HISTORIQUE
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "SECTION 14: RECENT COMMANDS (from bash history)"
    echo "═══════════════════════════════════════════════════════════════════"
    if [ -f ~/.bash_history ]; then
        grep -a "trading.py" ~/.bash_history 2>/dev/null | tail -20
    else
        echo "~/.bash_history not available"
    fi
    echo ""

    # ═══════════════════════════════════════════════════════════════
    # SECTION 15: END
    # ═══════════════════════════════════════════════════════════════
    echo "═══════════════════════════════════════════════════════════════════"
    echo "END OF REPORT"
    echo "═══════════════════════════════════════════════════════════════════"

} > "$OUTPUT" 2>&1

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  ✅ Report generated: $OUTPUT"
echo "  Size: $(du -h $OUTPUT | awk '{print $1}')"
echo "  Lines: $(wc -l < $OUTPUT)"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "الخطوة التالية:"
echo "  1. راجع الملف محلياً إذا أردت."
echo "  2. أرسل الملف كاملاً."
echo ""
