#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_remaining_parity.py
=======================
FIX-20 → FIX-22 + comprehensive parity audit.

يُصلح 3 أنماط متبقية ويقدّم تقريراً عن حالة كل الـ 25 إصلاحاً.

FIX-20: globals()  →  module-level _GLOBAL_STATE dict
FIX-21: hardcoded 3  →  Config.PO_MAX_FORCE_MARKET_ATTEMPTS
FIX-22: MaxHold wall-clock  →  bar-index anchor (يحل parity حقيقي)

الاستخدام:
    python fix_remaining_parity.py \
        --input  trading_2_final_all.py \
        --output trading_2_complete.py
"""

import argparse
import os
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# Helper
# ════════════════════════════════════════════════════════════════

def _has(src, marker):
    return marker in src


def _once(src, old, new, tag, already_marker=None):
    """Idempotent exact replace. Returns (src, applied_bool)."""
    if already_marker and already_marker in src:
        print(f"   ℹ️  [{tag}] already applied")
        return src, True
    n = src.count(old)
    if n == 0:
        print(f"   ❌ [{tag}] anchor NOT found")
        return src, False
    if n > 1:
        print(f"   ⚠️  [{tag}] anchor appears {n}× — replacing first only")
    return src.replace(old, new, 1), True


# ════════════════════════════════════════════════════════════════
# STEP 1 — AUDIT (read-only)
# ════════════════════════════════════════════════════════════════

AUDIT_CHECKS = {
    # Round 1 (19)
    "R1-01 leverage-snap":       "Snap to Binance valid tier",
    "R1-02 step-size":           "def _get_step_size",
    "R1-03 qty-sanitize":        "Sanitize qty + notional",
    "R1-04 gtx-fallback":        "# [FIX-4.1]",
    "R1-05b cap-read":           "Read capital from run_live",
    "R1-05c cap-publish":        "Publish to module-level",
    "R1-06b partial-accurate":   "Only mark partial as taken",
    "R1-07 physics-fi":          "points to last CLOSED bar",
    "R1-08 dup-topo":            "Topo-Div already checked above",
    "R1-09 info-line":           "[Exit] {sym} position already",
    "R1-10b fees":               "Entry is always maker",
    "R1-11b cleanup":            "Removed redundant cleanup",
    "R1-12 pending-stale":       "stale cancel {sym} oid",
    "R1-13 reconcile-prot":      "protective orders placed",
    "R1-14 exit-retry":          "forcing MARKET after",
    "R1-15 snapshot":            "[FIX-15] Trail params snapshot",
    "R1-16 promote-trail":       "Prefer snapshot in rec",
    "R1-17 partial-fees":        "subtract fees from partial",
    "R1-18 rate-tracker":        "Count actual exchange rate-limit hits",
    "R1-19 prot-rollback":       "rolling back any placed TP",
    # Round 4 (FIX-01-PROPER)
    "R4 tier cache":             "_SYMBOL_LEV_TIERS",
    "R4 static ladder":          "_STATIC_MAX_LEVERAGE",
    "R4 prefetch":               "def prefetch_all_leverage_tiers",
    # Round 5 (FIX-09-PROPER)
    "R5 pos-cache":              "_POSITION_CACHE: Dict",
    "R5 fake-list":              "def _fake_pos_list(",
    "R5 invalidate":             "def _invalidate_position_cache(",
}


def step1_audit(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  AUDIT: All fixes from rounds 1-5                           ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    present = 0
    missing = []
    for tag, marker in AUDIT_CHECKS.items():
        ok = _has(src, marker)
        print(f"   {'✅' if ok else '❌'} {tag}")
        if ok:
            present += 1
        else:
            missing.append(tag)
    total = len(AUDIT_CHECKS)
    print(f"\n   Summary: {present}/{total} present")
    if missing:
        print(f"   Missing: {missing}")
    return present == total


# ════════════════════════════════════════════════════════════════
# STEP 2 — FIX-20: globals() → _GLOBAL_STATE dict
# ════════════════════════════════════════════════════════════════

def step2_fix_globals(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-20: globals()  →  _GLOBAL_STATE dict                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    if "_GLOBAL_STATE: Dict = {}" in src:
        print("   ℹ️  already applied")
        return src, True

    # 2a. Inject _GLOBAL_STATE definition before _POSITION_CACHE
    anchor_def = "_POSITION_CACHE: Dict = {"
    if anchor_def not in src:
        print("   ❌ _POSITION_CACHE anchor not found")
        return src, False
    injection = (
        "# [FIX-20] Module-level state singleton — replaces globals()\n"
        "_GLOBAL_STATE: Dict = {}\n"
        "\n"
        "_POSITION_CACHE: Dict = {"
    )
    src = src.replace(anchor_def, injection, 1)
    print("   ✅ _GLOBAL_STATE defined")

    # 2b. Replace read
    old_read = ("        _cap_snapshot = float("
                "globals().get('_LAST_KNOWN_CAP', 0.0) or 0.0)")
    new_read = ("        _cap_snapshot = float("
                "_GLOBAL_STATE.get('last_cap', 0.0) or 0.0)")
    if old_read in src:
        src = src.replace(old_read, new_read, 1)
        print("   ✅ read site updated")
    else:
        print("   ⚠️  read site not found (may already be patched)")

    # 2c. Replace bootstrap check
    old_boot = ("            if ad is not None and not "
                "globals().get('_CAP_BOOTSTRAPPED', False):")
    new_boot = ("            if ad is not None and not "
                "_GLOBAL_STATE.get('cap_bootstrapped', False):")
    if old_boot in src:
        src = src.replace(old_boot, new_boot, 1)
        print("   ✅ bootstrap check updated")
    else:
        print("   ⚠️  bootstrap check not found")

    # 2d. Replace bootstrap writes
    old_w = ("                globals()['_LAST_KNOWN_CAP'] = _cap_snapshot\n"
             "                globals()['_CAP_BOOTSTRAPPED'] = True")
    new_w = ("                _GLOBAL_STATE['last_cap'] = _cap_snapshot\n"
             "                _GLOBAL_STATE['cap_bootstrapped'] = True")
    if old_w in src:
        src = src.replace(old_w, new_w, 1)
        print("   ✅ bootstrap writes updated")
    else:
        print("   ⚠️  bootstrap writes not found")

    # 2e. Replace publisher
    old_pub = ("                globals()['_LAST_KNOWN_CAP'] = "
               "float(cap_live)")
    new_pub = ("                _GLOBAL_STATE['last_cap'] = "
               "float(cap_live)")
    if old_pub in src:
        src = src.replace(old_pub, new_pub, 1)
        print("   ✅ publisher updated")
    else:
        print("   ⚠️  publisher not found")

    return src, True


# ════════════════════════════════════════════════════════════════
# STEP 3 — FIX-21: PO_MAX_FORCE_MARKET_ATTEMPTS config
# ════════════════════════════════════════════════════════════════

def step3_fix_retry_config(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-21: hardcoded 3  →  Config field                       ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    marker = "PO_MAX_FORCE_MARKET_ATTEMPTS"

    # 3a. Add to Config
    if marker in src:
        print("   ℹ️  Config field already present")
    else:
        cfg_anchor = "    MAX_HOLD_BARS: int = 168"
        if cfg_anchor not in src:
            print("   ❌ MAX_HOLD_BARS anchor not found")
            return src, False
        injection = (
            "    MAX_HOLD_BARS: int = 168\n"
            "    # [FIX-21] configurable retry threshold (was hardcoded 3)\n"
            "    PO_MAX_FORCE_MARKET_ATTEMPTS: int = 3"
        )
        src = src.replace(cfg_anchor, injection, 1)
        print("   ✅ Config field added")

    # 3b. Replace hardcoded check
    old_check = "                            if _retry_cnt >= 3:"
    new_check = ("                            _force_at = int(getattr("
                 "CFG, 'PO_MAX_FORCE_MARKET_ATTEMPTS', 3))\n"
                 "                            if _retry_cnt >= _force_at:")
    if old_check in src:
        src = src.replace(old_check, new_check, 1)
        print("   ✅ retry check made configurable")
    else:
        print("   ⚠️  retry check pattern not found "
              "(may already be patched)")

    return src, True


# ════════════════════════════════════════════════════════════════
# STEP 4 — FIX-22: MaxHold bar-index anchor (parity)
# ════════════════════════════════════════════════════════════════

def step4_fix_maxhold_anchor(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-22: MaxHold bar-index anchor (parity)                  ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    if "[FIX-22] bar-index anchor" in src:
        print("   ℹ️  already applied")
        return src, True

    # 4a. Add _entry_ci to the MAIN live entry dict
    #     (the one that also has fill_ratio — main entry path only)
    old_entry = ("                    'entry_ts': time.time(),\n"
                 "                    'fill_ratio': fill_ratio,")
    new_entry = ("                    'entry_ts': time.time(),\n"
                 "                    '_entry_ci': int(sig.close_idx),  "
                 "# [FIX-22] bar-index anchor\n"
                 "                    'fill_ratio': fill_ratio,")
    if old_entry in src:
        src = src.replace(old_entry, new_entry, 1)
        print("   ✅ _entry_ci added to main live entry")
    else:
        print("   ⚠️  main entry dict anchor not found "
              "(other paths unchanged — backward-compat)")

    # 4b. Replace the MaxHold wall-clock check with hybrid
    old_mh = (
        "                # \u2500\u2500 MaxHold \u2500\u2500\n"
        "                if not ex:\n"
        "                    entry_ts = pos.get('entry_ts', 0)\n"
        "                    if entry_ts > 0:\n"
        "                        tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600\n"
        "                        bars_held = (time.time() - entry_ts) / tf_sec\n"
        "                        if bars_held > effective_bars(cfg.MAX_HOLD_BARS):\n"
        "                            ex = True\n"
        "                            rsn = f\"MaxHold({int(bars_held)}bars)\""
    )
    new_mh = (
        "                # \u2500\u2500 MaxHold \u2500\u2500 [FIX-22] bar-index anchor\n"
        "                if not ex:\n"
        "                    _entry_ci_mh = int(pos.get('_entry_ci', 0) or 0)\n"
        "                    _ci_now_mh = ((len(ad.closes) - 2)\n"
        "                                   if ad is not None else 0)\n"
        "                    if _entry_ci_mh > 0 and _ci_now_mh > _entry_ci_mh:\n"
        "                        bars_held = _ci_now_mh - _entry_ci_mh\n"
        "                    else:\n"
        "                        # Fallback: wall-clock (old positions)\n"
        "                        _ets = pos.get('entry_ts', 0)\n"
        "                        _tf_s = (CFG.TF_SECONDS\n"
        "                                  if CFG.TF_SECONDS > 0 else 3600)\n"
        "                        bars_held = ((time.time() - _ets) / _tf_s\n"
        "                                      if _ets > 0 else 0)\n"
        "                    if bars_held > effective_bars(cfg.MAX_HOLD_BARS):\n"
        "                        ex = True\n"
        "                        rsn = f\"MaxHold({int(bars_held)}bars)\""
    )
    if old_mh in src:
        src = src.replace(old_mh, new_mh, 1)
        print("   ✅ MaxHold check replaced (hybrid anchor)")
    else:
        # Try with regular dash instead of \u2500
        old_mh2 = old_mh.replace("\u2500\u2500", "──")
        if old_mh2 in src:
            new_mh2 = new_mh.replace("\u2500\u2500", "──")
            src = src.replace(old_mh2, new_mh2, 1)
            print("   ✅ MaxHold check replaced (dash variant)")
        else:
            print("   ❌ MaxHold block not found")
            print("      Please send me this diagnostic:")
            idx = src.find("MaxHold")
            if idx > 0:
                print(f"      context: {src[max(0,idx-200):idx+200]!r}")
            return src, False

    return src, True


# ════════════════════════════════════════════════════════════════
# STEP 5 — Verify
# ════════════════════════════════════════════════════════════════

def step5_verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = {
        "FIX-20 _GLOBAL_STATE dict": "_GLOBAL_STATE: Dict = {}",
        "FIX-20 no bare globals()":  "globals()['_LAST_KNOWN_CAP']",
        "FIX-20 read via dict":      "_GLOBAL_STATE.get('last_cap'",
        "FIX-21 config field":       "PO_MAX_FORCE_MARKET_ATTEMPTS: int = 3",
        "FIX-21 runtime read":       "'PO_MAX_FORCE_MARKET_ATTEMPTS', 3",
        "FIX-22 entry_ci field":     "'_entry_ci': int(sig.close_idx)",
        "FIX-22 MaxHold hybrid":     "FIX-22] bar-index anchor",
    }
    all_ok = True
    for tag, marker in checks.items():
        ok = marker in src
        # Inverse check for FIX-20
        if tag == "FIX-20 no bare globals()":
            ok = not ok
        print(f"   {'✅' if ok else '❌'} {tag}")
        if not ok:
            all_ok = False

    # Count remaining globals() usages of that key
    n_globals = src.count("globals()['_LAST_KNOWN_CAP']")
    n_cap_boot = src.count("globals()['_CAP_BOOTSTRAPPED']")
    n_cap_get = src.count("globals().get('_LAST_KNOWN_CAP'")
    n_boot_get = src.count("globals().get('_CAP_BOOTSTRAPPED'")
    print(f"\n   leftover globals() (should all be 0):")
    print(f"      [..]='_LAST_KNOWN_CAP'  : {n_globals}")
    print(f"      [..]='_CAP_BOOTSTRAPPED': {n_cap_boot}")
    print(f"      .get('_LAST_KNOWN_CAP') : {n_cap_get}")
    print(f"      .get('_CAP_BOOTSTRAPPED'): {n_boot_get}")

    return all_ok


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_final_all.py")
    ap.add_argument("--output", default="trading_2_complete.py")
    ap.add_argument("--audit-only", action="store_true",
                    help="Only audit, do not patch or write output")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} bytes)")

    # Audit
    audit_ok = step1_audit(src)

    if args.audit_only:
        print(f"\n{'='*62}")
        print(f"Audit complete. No files modified.")
        sys.exit(0 if audit_ok else 1)

    # Apply FIX-20
    src, ok20 = step2_fix_globals(src)

    # Apply FIX-21
    src, ok21 = step3_fix_retry_config(src)

    # Apply FIX-22
    src, ok22 = step4_fix_maxhold_anchor(src)

    # Verify
    verify_ok = step5_verify(src)

    # Syntax
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  SYNTAX CHECK                                               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    try:
        compile(src, args.output, "exec")
        print("   ✅ compiles OK")
        syntax_ok = True
    except SyntaxError as e:
        print(f"   ❌ SyntaxError at line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text!r}")
        syntax_ok = False

    if not (ok20 and ok21 and ok22 and verify_ok and syntax_ok):
        print(f"\n╔══════════════════════════════════════════════════════════════╗")
        print(f"║  ❌ ABORTED                                                 ║")
        print(f"╚══════════════════════════════════════════════════════════════╝")
        print(f"   FIX-20:  {'OK' if ok20 else 'FAILED'}")
        print(f"   FIX-21:  {'OK' if ok21 else 'FAILED'}")
        print(f"   FIX-22:  {'OK' if ok22 else 'FAILED'}")
        print(f"   verify:  {'OK' if verify_ok else 'FAILED'}")
        print(f"   syntax:  {'OK' if syntax_ok else 'FAILED'}")
        print(f"\n   Output NOT written. Input unchanged.")
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine\n"
        "#  FULL PARITY BUILD — final\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  This build adds:\n"
        "#    FIX-20: _GLOBAL_STATE dict (was globals())\n"
        "#    FIX-21: PO_MAX_FORCE_MARKET_ATTEMPTS config\n"
        "#    FIX-22: MaxHold bar-index anchor (parity)\n"
        "#\n"
        "#  Patch history (5 rounds):\n"
        "#    1. apply_live_parity_fixes.py     (19 fixes)\n"
        "#    2. fix_parity_issues.py           (6 corrections)\n"
        "#    3. fix_remaining_issues.py        (2 surgical)\n"
        "#    4. fix_leverage_tiers.py          (FIX-01-PROPER)\n"
        "#    5. fix_position_cache.py          (FIX-09-PROPER)\n"
        "#    6. fix_remaining_parity.py        (FIX-20/21/22)\n"
        "# ═══════════════════════════════════════════════════════\n"
    )

    if src.startswith("#!"):
        first_nl = src.index("\n")
        src_out = header + src[first_nl + 1:]
    else:
        src_out = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src_out)

    with open(args.output, "r", encoding="utf-8") as f:
        written = f.read()
    try:
        compile(written, args.output, "exec")
        write_ok = True
    except SyntaxError as e:
        write_ok = False
        print(f"   ❌ written file broken at line {e.lineno}: {e.msg}")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                        DONE                                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"   Input:   {args.input}  ({len(src):,} bytes)")
    print(f"   Output:  {args.output}  ({len(src_out):,} bytes)")
    print(f"   FIX-20:  {'✅' if ok20 else '❌'}")
    print(f"   FIX-21:  {'✅' if ok21 else '❌'}")
    print(f"   FIX-22:  {'✅' if ok22 else '❌'}")
    print(f"   verify:  {'✅' if verify_ok else '❌'}")
    print(f"   syntax:  {'✅' if syntax_ok else '❌'}")
    print(f"   written: {'✅' if write_ok else '❌'}")

    if not write_ok:
        sys.exit(3)

    print(f"\n   ▶ Run:")
    print(f"     python {args.output} --mode backtest ...")
    print(f"     python {args.output} --mode testnet "
          f"--api-key ... --api-secret ...")


if __name__ == "__main__":
    main()
