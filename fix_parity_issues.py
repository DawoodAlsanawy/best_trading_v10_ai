#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_parity_issues.py
====================
يصحّح المشاكل التي أدخلتها النسخة السابقة من apply_live_parity_fixes.py.

يعمل على trading_2_fixed.py (المُخرَج السابق) ويُنتج trading_2_fixed_v2.py.

الوظائف:
  1. يتحقق فعلياً من وجود كل إصلاح (لا يفترض النجاح).
  2. يُصلح FIX-05/06/10/11.
  3. يطبع تقريراً مفصّلاً بالحالة الفعلية لكل إصلاح.

الاستخدام:
  python fix_parity_issues.py --input trading_2_fixed.py --output trading_2_fixed_v2.py
"""

import argparse
import os
import re
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

def _replace_once(src, old, new, tag):
    if old not in src:
        print(f"   ⚠️  [{tag}] pattern not found")
        return src, False
    if src.count(old) > 1:
        print(f"   ⚠️  [{tag}] pattern appears {src.count(old)}× — "
              f"replacing first only")
    return src.replace(old, new, 1), True


def _verify(src, marker, tag):
    present = marker in src
    icon = "✅" if present else "❌"
    print(f"   {icon} [{tag}] marker {'present' if present else 'MISSING'}")
    return present


# ════════════════════════════════════════════════════════════════
# STEP 1: Verify which prior fixes were actually applied
# ════════════════════════════════════════════════════════════════

PRIOR_FIX_MARKERS = {
    "FIX-01 snap leverage":     "Snap to Binance valid tier",
    "FIX-02 step size helper":  "_get_step_size(exchange, symbol: str)",
    "FIX-03 qty sanitize":      "[FIX-4.2/4.3] Sanitize qty + notional",
    "FIX-04 GTX fallback":      "GTX rejected — falling back with wider offset",
    "FIX-05a cap snapshot":     "[FIX-4.7] Capital snapshot for Stage-2 sizing",
    "FIX-05b cap field":        "_cap_snapshot if '_cap_snapshot' in dir()",
    "FIX-06 partial_taken":     "Broker-side partial TP is now placed",
    "FIX-07 physics fi":        "points to last CLOSED bar to avoid",
    "FIX-08 dup Topo-Div":      "(Topo-Div already checked above — removed duplicate)",
    "FIX-09 reduceOnly -2022":  "position already closed on exchange",
    "FIX-10 live fees PnL":     "احسب net_pnl مع الرسوم",
    "FIX-11 cancel prot exit":  "Force-clean ALL protective orders",
    "FIX-12 pending stale":     "stale cancel {sym} oid",
    "FIX-13 reconcile prot":    "protective orders placed ",
    "FIX-14 exit retry":        "forcing MARKET after",
    "FIX-15 adv snapshot":      "snapshot trail params to avoid needing ad_ref",
    "FIX-16 promote trail":     "Prefer snapshot in rec; fall back to ad_ref",
    "FIX-17 partial fees":      "subtract fees from partial",
    "FIX-18 rate tracker":      "Count actual exchange rate-limit hits",
    "FIX-19 prot rollback":     "rolling back any placed TP",
}


def step1_verify(src):
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  STEP 1: Verify prior fixes actually applied            ║")
    print("╚══════════════════════════════════════════════════════════╝")
    counts = {"present": 0, "missing": 0}
    for name, marker in PRIOR_FIX_MARKERS.items():
        ok = _verify(src, marker, name)
        counts["present" if ok else "missing"] += 1
    print(f"\n   Summary: {counts['present']} present, "
          f"{counts['missing']} missing")
    return counts


# ════════════════════════════════════════════════════════════════
# FIX-05b: Remove extra fetch_balance() call
# ════════════════════════════════════════════════════════════════

def fix_05b_remove_extra_balance(src):
    """
    FIX-05a أضاف fetch_balance() في place_pending_entry، وهذا يستهلك
    weight إضافي على كل أمر. الحل: نقرأ رأس المال من متغير عام
    يُحدَّث مرة واحدة في كل دورة run_live.
    """
    # Also support unpatched source (in case FIX-05a didn't apply)
    old_block = '''    # [FIX-4.7] Capital snapshot for Stage-2 sizing
    _cap_snapshot = 0.0
    try:
        if ad is not None:
            _bal_snap = exchange.fetch_balance()
            _cap_snapshot = float(_bal_snap['USDT'].get('free') or 0.0)
    except Exception:
        _cap_snapshot = 0.0'''

    new_block = '''    # [FIX-05b] Read capital from run_live's published snapshot.
    # The original patch (FIX-05a) called fetch_balance() here on
    # every placement, burning rate-limit weight unnecessarily.
    # run_live() now publishes cap_live → _LAST_KNOWN_CAP after each
    # balance fetch; we reuse it.
    _cap_snapshot = float(globals().get('_LAST_KNOWN_CAP', 0.0) or 0.0)
    if _cap_snapshot <= 0.0:
        # One-time bootstrap (only on first call before run_live
        # publishes anything). Cheap because it happens once.
        try:
            if ad is not None and not globals().get('_CAP_BOOTSTRAPPED', False):
                _bal_snap = exchange.fetch_balance()
                _cap_snapshot = float(
                    _bal_snap['USDT'].get('free') or 0.0
                )
                globals()['_LAST_KNOWN_CAP'] = _cap_snapshot
                globals()['_CAP_BOOTSTRAPPED'] = True
        except Exception:
            _cap_snapshot = 0.0'''

    src, ok = _replace_once(src, old_block, new_block, "FIX-05b")
    return src, ok


# ════════════════════════════════════════════════════════════════
# FIX-05c: Publish cap_live in run_live loop
# ════════════════════════════════════════════════════════════════

def fix_05c_publish_cap(src):
    old = '''                if _fixed_cap > 0:
                    cap_live = _fixed_cap
                else:
                    # السلوك الافتراضي: free (الحد المتداول الفعلي)
                    cap_live = _bal_free
                _last_known_cap = cap_live'''

    new = '''                if _fixed_cap > 0:
                    cap_live = _fixed_cap
                else:
                    # السلوك الافتراضي: free (الحد المتداول الفعلي)
                    cap_live = _bal_free
                _last_known_cap = cap_live
                # [FIX-05c] Publish to module-level so place_pending_entry
                # can read it without an extra fetch_balance() call.
                globals()['_LAST_KNOWN_CAP'] = float(cap_live)'''

    src, ok = _replace_once(src, old, new, "FIX-05c")
    return src, ok


# ════════════════════════════════════════════════════════════════
# FIX-06b: Accurate _partial_taken flag
# ════════════════════════════════════════════════════════════════

def fix_06b_accurate_partial_flag(src):
    """
    FIX-06 الأصلي كان يعتمد على CFG.PARTIAL_TP_ENABLED فقط.
    لكن _place_protective_orders قد ترفض partial TP إذا كانت
    price_partial >= price_full (أي لا معنى لها). الحل: نتحقق من
    أن partial TP فعلاً مُنطبق (partial_price < tp_full لـ BUY).
    """
    old = '''                    _prot_ok = True
                    # [FIX-5.3] Broker-side partial TP is now placed.
                    # Mark it taken so the bot doesn't double-fire.
                    if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                            and float(getattr(CFG, 'PARTIAL_TP_PCT', 0.0)) > 0):
                        open_pos_live[sym]['_partial_taken'] = True
                        open_pos_live[sym]['_partial_pnl'] = float(
                            open_pos_live[sym].get('_partial_pnl', 0.0)
                        )
                    break'''

    new = '''                    _prot_ok = True
                    # [FIX-06b] Only mark partial as taken if the
                    # broker-side partial TP was ACTUALLY placed.
                    # _place_protective_orders disables partial when
                    # partial_price >= full TP (BUY) or <= (SELL).
                    # We replicate that exact check here.
                    _pct_cfg = float(getattr(CFG, 'PARTIAL_TP_PCT', 0.0))
                    if (getattr(CFG, 'PARTIAL_TP_ENABLED', False)
                            and 0.0 < _pct_cfg < 1.0):
                        _ptr = float(getattr(CFG, 'PARTIAL_TP_R', 1.5))
                        _sl0 = float(open_pos_live[sym].get(
                            'sl_dist_initial', 0) or 0)
                        _entry_ = float(open_pos_live[sym].get('entry', 0))
                        _tp_full = float(open_pos_live[sym].get('tp1', 0))
                        _partial_valid = False
                        if _sl0 > 0 and _entry_ > 0 and _tp_full > 0:
                            _act = open_pos_live[sym].get('action')
                            if _act == 'BUY':
                                _pp = _entry_ + _sl0 * _ptr
                                _partial_valid = (_pp < _tp_full)
                            else:
                                _pp = _entry_ - _sl0 * _ptr
                                _partial_valid = (_pp > _tp_full)
                        if _partial_valid:
                            open_pos_live[sym]['_partial_taken'] = True
                            open_pos_live[sym]['_partial_pnl'] = float(
                                open_pos_live[sym].get('_partial_pnl', 0.0)
                            )
                            log.debug(f"[Prot] {sym} partial marked taken")
                        else:
                            log.debug(f"[Prot] {sym} partial TP not "
                                      f"applicable — bot-side partial "
                                      f"remains enabled")
                    break'''

    src, ok = _replace_once(src, old, new, "FIX-06b")
    return src, ok


# ════════════════════════════════════════════════════════════════
# FIX-10b: Accurate exit fee (maker vs taker)
# ════════════════════════════════════════════════════════════════

def fix_10b_accurate_exit_fee(src):
    old = '''                        # Maker fee on entry, taker on exit (SL/TP)
                        _entry_fee_lg = _qty_lg * _entry_px_lg * CFG.MAKER_FEE
                        _exit_fee_lg  = _qty_lg * _exit_px_lg * CFG.TAKER_FEE'''

    new = '''                        # [FIX-10b] Entry is always maker (GTX).
                        # Exit fee depends on reason:
                        #   SL / TP / LiqProximity → taker
                        #   Apex / Topo / MaxHold / EndOfData → maker
                        _entry_fee_lg = _qty_lg * _entry_px_lg * CFG.MAKER_FEE
                        _is_taker_exit = _exit_is_taker(exit_reason)
                        _exit_fee_rate = (CFG.TAKER_FEE
                                          if _is_taker_exit
                                          else CFG.MAKER_FEE)
                        _exit_fee_lg = _qty_lg * _exit_px_lg * _exit_fee_rate'''

    src, ok = _replace_once(src, old, new, "FIX-10b")
    return src, ok


# ════════════════════════════════════════════════════════════════
# FIX-11b: Remove redundant cleanup
# ════════════════════════════════════════════════════════════════

def fix_11b_remove_redundant_cleanup(src):
    """
    FIX-11 أضاف cancel إضافي بعد نجاح الخروج. لكن الكود الأصلي
    يفعل نفس الإلغاء قبل بضعة أسطر. الحل: احذف الكتلة المكررة.
    """
    old = '''                    # [FIX-9.2] Force-clean ALL protective orders
                    try:
                        _left = _cancel_all_protective_orders(exchange, sym)
                        if _left > 0:
                            log.debug(f"[Prot] {sym} post-exit cleaned "
                                      f"{_left} residual order(s)")
                    except Exception as _e:
                        log.debug(f"[Prot] {sym} post-exit cleanup: {_e}")

                    del open_pos_live[sym]'''

    new = '''                    # [FIX-11b] Removed redundant cleanup — the
                    # post-exit protective cancel above already handles
                    # this via closePosition=True auto-cancel + the
                    # _cancel_all_protective_orders defensive sweep.
                    del open_pos_live[sym]'''

    src, ok = _replace_once(src, old, new, "FIX-11b")
    return src, ok


# ════════════════════════════════════════════════════════════════
# FIX-15b: Ensure trail snapshot variables exist before use
# ════════════════════════════════════════════════════════════════

def fix_15b_trail_snapshot_bootstrap(src):
    """
    FIX-15a أضاف snapshot trail params في place_pending_entry، لكن
    لاحظت أن النسخة القديمة قد تفشل إذا لم تكن compute_trail_params
    متاحة (مثلاً عند import فقط). نضمن أن القيم تُحسب دائماً.
    """
    # التحقق أن FIX-15a موجود فعلاً
    if "[FIX-15] Trail params snapshot" not in src:
        print("   ℹ️  [FIX-15b] FIX-15a not present — applying full block")
        old2 = '''    rec = {
        'order_id': str(o['id']),
        'sym': sym,
        'side': side,'''

        new2 = '''    # [FIX-15b] Trail params snapshot (robust version)
    _trail_d_snapshot, _trail_a_snapshot = 0.003, 0.004
    try:
        if ad is not None and hasattr(ad, 'E_therm') and len(ad.E_therm) > 0:
            _fi_snap = max(0, min(int(getattr(sig, 'feat_idx', 0)),
                                  len(ad.E_therm) - 1))
            _td_snap, _ta_snap = compute_trail_params(ad, _fi_snap)
            if _td_snap > 0 and _ta_snap > 0:
                _trail_d_snapshot = float(_td_snap)
                _trail_a_snapshot = float(_ta_snap)
    except Exception as _e:
        log.debug(f"[FIX-15b] trail snapshot failed: {_e}")

    rec = {
        'order_id': str(o['id']),
        'sym': sym,
        'side': side,'''

        src, ok = _replace_once(src, old2, new2, "FIX-15b")
        return src, ok
    else:
        print("   ℹ️  [FIX-15b] FIX-15a already present — no action")
        return src, True


# ════════════════════════════════════════════════════════════════
# STEP 2: Add missing critical fixes (in case FIX-02..19 didn't apply)
# ════════════════════════════════════════════════════════════════

def ensure_critical_helpers(src):
    """
    يضمن أن `_exit_is_taker` موجودة (FIX-10b يعتمد عليها).
    وإلا نضيف نسخة محلية.
    """
    if "def _exit_is_taker(" in src:
        print("   ✅ [_exit_is_taker] already defined")
        return src, True

    print("   ⚠️  [_exit_is_taker] MISSING — adding helper")
    anchor = "# ══ [Cache-Health] إحصائيات عامة للجلسة ══"
    if anchor not in src:
        anchor = "logging.basicConfig(level=logging.INFO,"

    helper = '''def _exit_is_taker(exit_rsn: str) -> bool:
    """
    [PARITY-HELPER] Classify exit as taker or maker.
    Matches backtest's _exit_is_taker.
    """
    r = str(exit_rsn or "")
    if ("Emergency" in r) or ("Hard TP" in r) or ("LiqProximity" in r):
        return True
    return False


'''

    if anchor in src:
        src = src.replace(anchor, helper + anchor, 1)
    else:
        # Insert after the module docstring
        src = helper + src
    return src, True


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="trading_2_fixed.py")
    ap.add_argument("--output", default="trading_2_fixed_v2.py")
    ap.add_argument("--force", action="store_true",
                    help="Apply all fixes regardless of prior state")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()

    print(f"📖 Loaded {len(src):,} bytes from {args.input}")

    # STEP 1: verify
    counts = step1_verify(src)

    # STEP 2: apply corrected fixes
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  STEP 2: Apply corrected fixes                          ║")
    print("╚══════════════════════════════════════════════════════════╝")

    results = {}

    print("\n▶ FIX-05b: remove extra fetch_balance in place_pending_entry")
    src, results['FIX-05b'] = fix_05b_remove_extra_balance(src)

    print("\n▶ FIX-05c: publish cap_live as module-level snapshot")
    src, results['FIX-05c'] = fix_05c_publish_cap(src)

    print("\n▶ FIX-06b: accurate _partial_taken flag")
    src, results['FIX-06b'] = fix_06b_accurate_partial_flag(src)

    print("\n▶ FIX-10b: accurate exit fee (maker vs taker)")
    src, results['FIX-10b'] = fix_10b_accurate_exit_fee(src)

    print("\n▶ FIX-11b: remove redundant protective cleanup")
    src, results['FIX-11b'] = fix_11b_remove_redundant_cleanup(src)

    print("\n▶ FIX-15b: robust trail snapshot bootstrap")
    src, results['FIX-15b'] = fix_15b_trail_snapshot_bootstrap(src)

    print("\n▶ ENSURE: _exit_is_taker helper exists")
    src, results['exit_is_taker'] = ensure_critical_helpers(src)

    # STEP 3: verify corrections
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  STEP 3: Verify corrections landed                      ║")
    print("╚══════════════════════════════════════════════════════════╝")

    CORRECTED_MARKERS = {
        "FIX-05b":      "[FIX-05b] Read capital from run_live's published snapshot",
        "FIX-05c":      "[FIX-05c] Publish to module-level",
        "FIX-06b":      "[FIX-06b] Only mark partial as taken if the",
        "FIX-10b":      "[FIX-10b] Entry is always maker (GTX)",
        "FIX-11b":      "[FIX-11b] Removed redundant cleanup",
        "FIX-15b":      "[FIX-15b] Trail params snapshot (robust version)",
        "exit_is_taker": "def _exit_is_taker(",
    }

    all_ok = True
    for tag, marker in CORRECTED_MARKERS.items():
        present = marker in src
        icon = "✅" if present else "❌"
        print(f"   {icon} [{tag}]")
        if not present:
            all_ok = False

    # STEP 4: Add header, write output
    header = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  trading_2_fixed_v2.py — Corrected Live/Backtest Parity Build
#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
#  Base: {args.input}
#
#  Corrections applied on top of the first patch round:
#    - FIX-05b: no extra fetch_balance() in place_pending_entry
#    - FIX-05c: run_live publishes _LAST_KNOWN_CAP
#    - FIX-06b: _partial_taken only set when partial TP is valid
#    - FIX-10b: exit fee uses maker/taker classification
#    - FIX-11b: removed redundant post-exit cleanup
#    - FIX-15b: robust trail snapshot bootstrap
#    - ENSURE:  _exit_is_taker helper guaranteed present
# ════════════════════════════════════════════════════════════════════
"""

    # Preserve shebang
    if src.startswith("#!"):
        first_nl = src.index("\n")
        src = header + src[first_nl+1:]
    else:
        src = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src)

    # STEP 5: syntax check
    print(f"\n╔══════════════════════════════════════════════════════════╗")
    print(f"║  STEP 4: Syntax check                                    ║")
    print(f"╚══════════════════════════════════════════════════════════╝")
    try:
        compile(src, args.output, "exec")
        print(f"   ✅ {args.output} compiles OK")
    except SyntaxError as e:
        print(f"   ❌ Syntax error at line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text}")
        sys.exit(2)

    # STEP 6: import smoke test (parse only, don't execute)
    print(f"\n╔══════════════════════════════════════════════════════════╗")
    print(f"║  STEP 5: Cross-check critical symbols exist             ║")
    print(f"╚══════════════════════════════════════════════════════════╝")
    required = [
        "def _exit_is_taker",
        "def _get_step_size",
        "def _round_qty",
        "def _get_min_notional",
        "def compute_dynamic_leverage",
        "def place_pending_entry",
        "def monitor_pending_orders",
        "def _promote_pending_to_position",
        "def _place_protective_orders",
        "def _cancel_all_protective_orders",
        "def _sync_protective_orders",
        "def run_live",
        "def run_backtest",
    ]
    missing = [sym for sym in required if sym not in src]
    if missing:
        print(f"   ⚠️  Missing symbols: {missing}")
    else:
        print(f"   ✅ All {len(required)} critical symbols present")

    # Final summary
    print(f"\n{'='*64}")
    print(f"✅ Done")
    print(f"   Output: {args.output}")
    print(f"   Size:   {len(src):,} bytes")
    print(f"{'='*64}\n")

    if not all_ok:
        print("⚠️  WARNING: some corrections failed to apply.")
        print("   Re-check the input file (it may already be in a")
        print("   different state than expected).")
        sys.exit(1)


if __name__ == "__main__":
    main()
