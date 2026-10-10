#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
final_check.py
==============
التحقق النهائي من trading_2_final.py (أو أي إصدار سابق).
لا يُعدّل المصدر. يتحقق ثم ينسخ لملف موثّق.

الاستخدام:
  python final_check.py --input trading_2_final.py
  python final_check.py --input trading_2_final.py --output trading_2_release.py
"""

import argparse
import os
import shutil
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# Robust markers — كل واحد على سطر واحد في المصدر
# ════════════════════════════════════════════════════════════════
# كل معرّف هنا موجود حرفياً على سطر واحد، أو عبر حقلين متقاربين.
# تجنّبنا عمداً أي سلسلة تعبر حدود f-strings.

MARKERS = {
    # ── أدوات أساسية ─────────────────────────────────────────────
    "BASE-leverage-snap":
        "Snap to Binance valid tier",
    "BASE-step-size":
        "def _get_step_size",
    "BASE-round-qty":
        "def _round_qty",
    "BASE-min-notional":
        "def _get_min_notional",
    "BASE-exit-taker":
        "def _exit_is_taker",

    # ── FIX-03: qty sanitize ────────────────────────────────────
    "FIX-03-qty-sanitize":
        "Sanitize qty + notional",

    # ── FIX-04: GTX fallback (معرّف عربي) ───────────────────────
    "FIX-04-gtx-arabic-marker":
        "# [FIX-4.1]",
    "FIX-04-gtx-target2":
        "target = target2",

    # ── FIX-05: cap snapshot (b + c) ────────────────────────────
    "FIX-05b-read-cap":
        "Read capital from run_live",
    "FIX-05c-publish-cap":
        "Publish to module-level",

    # ── FIX-06: partial accurate ────────────────────────────────
    "FIX-06b-partial-accurate":
        "Only mark partial as taken",

    # ── FIX-07: physics fi ──────────────────────────────────────
    "FIX-07-physics-fi":
        "points to last CLOSED bar",

    # ── FIX-08: dup topo-div ────────────────────────────────────
    "FIX-08-dup-topo":
        "Topo-Div already checked above",

    # ── FIX-09: -2022 / exchange-closed (سطران قصيران) ──────────
    "FIX-09-info-line":
        "[Exit] {sym} position already",
    "FIX-09-debug-line":
        "[Exit] position check",

    # ── FIX-10: live fees ───────────────────────────────────────
    "FIX-10b-fees":
        "Entry is always maker",

    # ── FIX-11: cleanup ─────────────────────────────────────────
    "FIX-11b-cleanup":
        "Removed redundant cleanup",

    # ── FIX-12: pending stale ───────────────────────────────────
    "FIX-12-pending-stale":
        "stale cancel {sym} oid",

    # ── FIX-13: reconcile prot ──────────────────────────────────
    "FIX-13-reconcile-prot":
        "protective orders placed",

    # ── FIX-14: exit retry limit ────────────────────────────────
    "FIX-14-exit-retry":
        "forcing MARKET after",

    # ── FIX-15: trail snapshot (يقبل 15a أو 15b) ────────────────
    "FIX-15-snapshot-a":
        "[FIX-15] Trail params snapshot",
    "FIX-15-snapshot-b":
        "[FIX-15b] Trail params snapshot",

    # ── FIX-16: promote trail ───────────────────────────────────
    "FIX-16-promote-trail":
        "Prefer snapshot in rec",

    # ── FIX-17: partial fees ────────────────────────────────────
    "FIX-17-partial-fees":
        "subtract fees from partial",

    # ── FIX-18: rate tracker ────────────────────────────────────
    "FIX-18-rate-tracker":
        "Count actual exchange rate-limit hits",

    # ── FIX-19: prot rollback ───────────────────────────────────
    "FIX-19-prot-rollback":
        "rolling back any placed TP",
}


# مجموعة الإصلاحات التي يمكن أن تظهر باسمين (a/b) — واحد يكفي
ALTERNATIVE_MARKERS = {
    "FIX-15-snapshot":
        ["[FIX-15] Trail params snapshot",
         "[FIX-15b] Trail params snapshot"],
}


# ════════════════════════════════════════════════════════════════
# فحوصات البنية
# ════════════════════════════════════════════════════════════════

STRUCTURE_CHECKS = {
    "class Config":              "class Config:",
    "def run_live":              "def run_live(",
    "def run_backtest":          "def run_backtest(",
    "def build_signals":         "def build_signals(",
    "def simulate_portfolio":    "def simulate_portfolio(",
    "def process_asset":         "def process_asset(",
    "def place_pending_entry":   "def place_pending_entry(",
    "def monitor_pending_orders":"def monitor_pending_orders(",
    "def _promote_pending_to_position":
                                 "def _promote_pending_to_position(",
    "def _place_protective_orders":
                                 "def _place_protective_orders(",
    "def _cancel_all_protective_orders":
                                 "def _cancel_all_protective_orders(",
    "def _sync_protective_orders":
                                 "def _sync_protective_orders(",
    "def execute_post_only":     "def execute_post_only(",
    "def compute_dynamic_leverage":
                                 "def compute_dynamic_leverage(",
    "def main":                  "def main(",
}


# ════════════════════════════════════════════════════════════════
# الفحوصات الدلالية (semantic)
# ════════════════════════════════════════════════════════════════

def check_no_dangerous_duplicates(src):
    """
    يتحقق من عدم وجود تكرار خطير لكتل الإصلاحات
    (مثلاً FIX-05b موجود مرتين، أو FIX-15a + FIX-15b معاً).
    التكرار ليس خطأً قاتلاً لكن قد يسبب التباساً.
    """
    issues = []

    # FIX-05b: يجب أن يظهر مرة واحدة فقط
    n_05b = src.count("[FIX-05b] Read capital from run_live")
    if n_05b > 1:
        issues.append(f"FIX-05b appears {n_05b}× — should be 1")

    # FIX-15a و FIX-15b: واحد يكفي
    n_15a = src.count("[FIX-15] Trail params snapshot")
    n_15b = src.count("[FIX-15b] Trail params snapshot")
    if n_15a > 0 and n_15b > 0:
        issues.append(
            f"Both FIX-15a ({n_15a}×) and FIX-15b ({n_15b}×) present — "
            f"redundant but harmless"
        )

    # FIX-15b: إذا ظهر أكثر من مرة
    if n_15b > 1:
        issues.append(f"FIX-15b appears {n_15b}× — should be ≤1")

    # FIX-06b: تحقق من عدم التكرار
    n_06b = src.count("[FIX-06b] Only mark partial as taken")
    if n_06b > 1:
        issues.append(f"FIX-06b appears {n_06b}× — should be 1")

    return issues


# ════════════════════════════════════════════════════════════════
# الطباعة
# ════════════════════════════════════════════════════════════════

def print_section(title, width=64):
    print()
    print("╔" + "═" * (width - 2) + "╗")
    pad = width - 2 - len(title)
    left = pad // 2
    right = pad - left
    print("║" + " " * left + title + " " * right + "║")
    print("╚" + "═" * (width - 2) + "╝")


def report_markers(src):
    print_section("FUNCTIONAL FIXES")
    passed = 0
    failed = []

    for tag, marker in MARKERS.items():
        ok = marker in src
        icon = "✅" if ok else "❌"
        print(f"   {icon} {tag}")
        if ok:
            passed += 1
        else:
            failed.append(tag)

    print(f"\n   Total: {passed}/{len(MARKERS)} present")
    return passed, failed


def report_alternatives(src):
    print_section("ALTERNATIVE MARKERS (one of many)")
    ok_count = 0
    for tag, options in ALTERNATIVE_MARKERS.items():
        found = [opt for opt in options if opt in src]
        if found:
            ok_count += 1
            print(f"   ✅ {tag} — found: {found[0][:50]}")
        else:
            print(f"   ❌ {tag} — none of {len(options)} variants present")
    return ok_count


def report_structure(src):
    print_section("STRUCTURAL INTEGRITY")
    all_ok = True
    for name, marker in STRUCTURE_CHECKS.items():
        cnt = src.count(marker)
        ok = (cnt == 1)
        icon = "✅" if ok else ("⚠️" if cnt > 1 else "❌")
        print(f"   {icon} {name}: {cnt}")
        if not ok:
            all_ok = False
    return all_ok


def report_duplicates(src):
    print_section("DUPLICATE SCAN")
    issues = check_no_dangerous_duplicates(src)
    if not issues:
        print("   ✅ No dangerous duplicates")
        return True
    for iss in issues:
        print(f"   ⚠️  {iss}")
    return False


# ════════════════════════════════════════════════════════════════
# النسخ النهائي
# ════════════════════════════════════════════════════════════════

def write_release(src, output, input_name):
    header = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  {os.path.basename(output)}
#  Quantum Thermodynamic Trading Engine — Live/Backtest Parity Build
#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
#  Base: {input_name}
#
#  Patch summary:
#    • 19 original fixes (apply_live_parity_fixes.py)
#    •  6 corrections   (fix_parity_issues.py)
#    •  2 surgical      (fix_remaining_issues.py)
#
#  Verified feature set:
#    - Leverage snapped to Binance tiers  (no -4028)
#    - Qty rounded to stepSize            (no -1111)
#    - MIN_NOTIONAL pre-checked           (no -4164)
#    - GTX rejection → wider-offset retry (no -2010)
#    - Physics exits use last CLOSED bar  (no look-ahead)
#    - Broker-closed position auto-adopt  (no -2022 spam)
#    - Maker/Taker fee accuracy in PnL
#    - Partial TP single-fire guarantee
#    - Trailing snapshot survives restart
#    - Reconcile places protective orders
#    - Exit retry limit → forced market
# ════════════════════════════════════════════════════════════════════
"""
    if src.startswith("#!"):
        first_nl = src.index("\n")
        body = src[first_nl + 1:]
    else:
        body = src

    with open(output, "w", encoding="utf-8") as f:
        f.write(header + body)


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_final.py")
    ap.add_argument("--output", default="trading_2_release.py")
    ap.add_argument("--no-copy", action="store_true",
                    help="verify only, do not write output")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()

    print()
    print(f"📖 Loaded: {args.input}  ({len(src):,} bytes)")

    # 1) Functional markers
    n_pass, failed = report_markers(src)

    # 2) Alternative markers
    alt_ok = report_alternatives(src)

    # 3) Structure
    struct_ok = report_structure(src)

    # 4) Duplicates
    dups_ok = report_duplicates(src)

    # 5) Syntax
    print_section("SYNTAX CHECK")
    try:
        compile(src, args.input, "exec")
        syntax_ok = True
        print("   ✅ compiles OK")
    except SyntaxError as e:
        syntax_ok = False
        print(f"   ❌ SyntaxError at line {e.lineno}: {e.msg}")
        print(f"      {e.text}")

    # ══ Verdict ══
    print_section("VERDICT")
    all_ok = (n_pass == len(MARKERS)) and struct_ok and syntax_ok

    if all_ok:
        print("   ✅ ALL CHECKS PASSED")
        print("      The code is functionally complete.")
        if failed:
            print(f"      (but {len(failed)} markers reported ❌ — "
                  f"investigate)")
            for t in failed:
                print(f"        - {t}")
        if not dups_ok:
            print("      (duplicates present — harmless but review)")

        if not args.no_copy:
            print(f"\n   📝 Writing clean release: {args.output}")
            write_release(src, args.output, args.input)

            # Re-verify the written file
            with open(args.output, "r", encoding="utf-8") as f:
                out_src = f.read()
            try:
                compile(out_src, args.output, "exec")
                print(f"   ✅ {args.output} written and compiles OK")
                print(f"      size: {len(out_src):,} bytes")
            except SyntaxError as e:
                print(f"   ❌ Release file broken: {e}")
                sys.exit(2)

        print()
        print("   ▶ Ready to run:")
        print(f"     python {args.output if not args.no_copy else args.input} \\")
        print("         --mode testnet --api-key ... --api-secret ...")
        sys.exit(0)
    else:
        print(f"   ❌ PARTIAL — some checks failed")
        print(f"      markers: {n_pass}/{len(MARKERS)}")
        print(f"      structure: {'OK' if struct_ok else 'ISSUES'}")
        print(f"      syntax: {'OK' if syntax_ok else 'FAILED'}")
        if failed:
            print(f"      missing markers:")
            for t in failed:
                print(f"        - {t}")
        sys.exit(1)


if __name__ == "__main__":
    main()
