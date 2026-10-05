#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_parity_v2.py
================
نسخة مُصحَّحة من fix_remaining_parity.py بعد تشخيص الفشل السابق:

  1. FIX-20: pattern للـ read site يحتاج 4 مسافات (لا 8).
  2. FIX-22a: لم تكن ضرورية — _entry_ci موجود أصلاً.
  3. Audit R1-01: استخدام marker فريد (def _standard_ladder).

الإصلاحات المطبَّقة:
  - FIX-20: globals() → _GLOBAL_STATE dict
  - FIX-21: hardcoded 3 → Config field
  - FIX-22: MaxHold bar-index anchor (hybrid)
"""

import argparse
import os
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# STEP 1: Audit (corrected markers)
# ════════════════════════════════════════════════════════════════

AUDIT_CHECKS = {
    # Round 1
    "R1-01 leverage-snap":       "def _standard_ladder",   # ← fix: FIX-01-PROPER marker
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
    # Round 4
    "R4 tier cache":             "_SYMBOL_LEV_TIERS",
    "R4 static ladder":          "_STATIC_MAX_LEVERAGE",
    "R4 prefetch":               "def prefetch_all_leverage_tiers",
    # Round 5
    "R5 pos-cache":              "_POSITION_CACHE: Dict",
    "R5 fake-list":              "def _fake_pos_list(",
    "R5 invalidate":             "def _invalidate_position_cache(",
}


def step1_audit(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  AUDIT                                                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    present, missing = 0, []
    for tag, marker in AUDIT_CHECKS.items():
        ok = marker in src
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
# STEP 2: FIX-20 — globals() → _GLOBAL_STATE
# ════════════════════════════════════════════════════════════════

def step2_fix_globals(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-20: globals() → _GLOBAL_STATE dict                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    if "_GLOBAL_STATE: Dict = {}" in src:
        print("   ℹ️  already applied")
        return src, True

    # 2a. Inject definition
    anchor = "_POSITION_CACHE: Dict = {"
    if anchor not in src:
        print("   ❌ _POSITION_CACHE anchor not found")
        return src, False
    injection = (
        "# [FIX-20] Module-level state singleton (replaces globals())\n"
        "_GLOBAL_STATE: Dict = {}\n"
        "\n"
        "_POSITION_CACHE: Dict = {"
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ _GLOBAL_STATE defined")

    # 2b. Read site — 4 spaces (function body level)
    old_read = ("    _cap_snapshot = float("
                "globals().get('_LAST_KNOWN_CAP', 0.0) or 0.0)")
    new_read = ("    _cap_snapshot = float("
                "_GLOBAL_STATE.get('last_cap', 0.0) or 0.0)")
    if old_read not in src:
        print("   ❌ read site (4-space) NOT found")
        idx = src.find("_cap_snapshot = float")
        if idx >= 0:
            print(f"      context: {src[idx-10:idx+120]!r}")
        return src, False
    src = src.replace(old_read, new_read, 1)
    print("   ✅ read site updated")

    # 2c. Bootstrap check — 12 spaces
    old_boot = ("            if ad is not None and not "
                "globals().get('_CAP_BOOTSTRAPPED', False):")
    new_boot = ("            if ad is not None and not "
                "_GLOBAL_STATE.get('cap_bootstrapped', False):")
    if old_boot not in src:
        print("   ❌ bootstrap check (12-space) NOT found")
        return src, False
    src = src.replace(old_boot, new_boot, 1)
    print("   ✅ bootstrap check updated")

    # 2d. Bootstrap writes — 16 spaces
    old_w = ("                globals()['_LAST_KNOWN_CAP'] = "
             "_cap_snapshot\n"
             "                globals()['_CAP_BOOTSTRAPPED'] = True")
    new_w = ("                _GLOBAL_STATE['last_cap'] = "
             "_cap_snapshot\n"
             "                _GLOBAL_STATE['cap_bootstrapped'] = True")
    if old_w not in src:
        print("   ❌ bootstrap writes (16-space) NOT found")
        return src, False
    src = src.replace(old_w, new_w, 1)
    print("   ✅ bootstrap writes updated")

    # 2e. Publisher — 16 spaces
    old_pub = ("                globals()['_LAST_KNOWN_CAP'] = "
               "float(cap_live)")
    new_pub = ("                _GLOBAL_STATE['last_cap'] = "
               "float(cap_live)")
    if old_pub not in src:
        print("   ❌ publisher (16-space) NOT found")
        return src, False
    src = src.replace(old_pub, new_pub, 1)
    print("   ✅ publisher updated")

    return src, True


# ════════════════════════════════════════════════════════════════
# STEP 3: FIX-21 — retry threshold config
# ════════════════════════════════════════════════════════════════

def step3_fix_retry_config(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-21: PO_MAX_FORCE_MARKET_ATTEMPTS config                ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    if "PO_MAX_FORCE_MARKET_ATTEMPTS" in src:
        print("   ℹ️  already applied")
        return src, True

    cfg_anchor = "    MAX_HOLD_BARS: int = 168"
    if cfg_anchor not in src:
        print("   ❌ MAX_HOLD_BARS anchor not found")
        return src, False
    injection = (
        "    MAX_HOLD_BARS: int = 168\n"
        "    # [FIX-21] configurable retry threshold\n"
        "    PO_MAX_FORCE_MARKET_ATTEMPTS: int = 3"
    )
    src = src.replace(cfg_anchor, injection, 1)
    print("   ✅ Config field added")

    old_check = "                            if _retry_cnt >= 3:"
    new_check = (
        "                            _force_at = int(getattr("
        "CFG, 'PO_MAX_FORCE_MARKET_ATTEMPTS', 3))\n"
        "                            if _retry_cnt >= _force_at:"
    )
    if old_check not in src:
        print("   ❌ retry check NOT found")
        idx = src.find("_retry_cnt")
        if idx >= 0:
            print(f"      context: {src[idx-80:idx+200]!r}")
        return src, False
    src = src.replace(old_check, new_check, 1)
    print("   ✅ retry check made configurable")
    return src, True


# ════════════════════════════════════════════════════════════════
# STEP 4: FIX-22 — MaxHold hybrid (entry_ci already exists)
# ════════════════════════════════════════════════════════════════

def step4_fix_maxhold(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-22: MaxHold hybrid anchor                              ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    if "[FIX-22] bar-index anchor" in src:
        print("   ℹ️  already applied")
        return src, True

    if "'_entry_ci': int(sig.close_idx)" in src:
        print("   ✅ _entry_ci already present in main entry "
              "(no additional patch needed)")
    else:
        print("   ⚠️  _entry_ci missing in main entry — "
              "fallback to wall-clock will apply")

    # Replace the wall-clock MaxHold check
    old_mh = (
        "                # ── MaxHold ──\n"
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
        "                # ── MaxHold ── [FIX-22] bar-index anchor\n"
        "                if not ex:\n"
        "                    _entry_ci_mh = int(pos.get('_entry_ci', 0) or 0)\n"
        "                    _ci_now_mh = ((len(ad.closes) - 2)\n"
        "                                   if ad is not None else 0)\n"
        "                    if _entry_ci_mh > 0 and _ci_now_mh > _entry_ci_mh:\n"
        "                        bars_held = _ci_now_mh - _entry_ci_mh\n"
        "                    else:\n"
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
        print("   ✅ MaxHold hybrid applied")
        return src, True

    # Try ASCII dashes variant
    old_mh_ascii = old_mh.replace("──", "--")
    if old_mh_ascii in src:
        new_mh_ascii = new_mh.replace("──", "--")
        src = src.replace(old_mh_ascii, new_mh_ascii, 1)
        print("   ✅ MaxHold hybrid applied (ASCII variant)")
        return src, True

    print("   ❌ MaxHold anchor NOT found (both Unicode and ASCII)")
    idx = src.find("MaxHold")
    if idx > 0:
        print(f"      actual context: {src[max(0,idx-250):idx+250]!r}")
    return src, False


# ════════════════════════════════════════════════════════════════
# STEP 5: Verify
# ════════════════════════════════════════════════════════════════

def step5_verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    checks = {
        "FIX-20 _GLOBAL_STATE defined":  ("_GLOBAL_STATE: Dict = {}", True),
        "FIX-20 read via dict":          ("_GLOBAL_STATE.get('last_cap'", True),
        "FIX-20 publish via dict":       ("_GLOBAL_STATE['last_cap']", True),
        "FIX-20 no globals[] '_LAST'":   ("globals()['_LAST_KNOWN_CAP']", False),
        "FIX-20 no globals.get('_LAST')":("globals().get('_LAST_KNOWN_CAP'", False),
        "FIX-21 config field":           ("PO_MAX_FORCE_MARKET_ATTEMPTS: int = 3", True),
        "FIX-21 runtime read":           ("'PO_MAX_FORCE_MARKET_ATTEMPTS', 3", True),
        "FIX-22 MaxHold hybrid":         ("[FIX-22] bar-index anchor", True),
        "FIX-22 _entry_ci in main":      ("'_entry_ci': int(sig.close_idx)", True),
    }

    all_ok = True
    for tag, (marker, want_present) in checks.items():
        present = marker in src
        ok = (present == want_present)
        print(f"   {'✅' if ok else '❌'} {tag}")
        if not ok:
            all_ok = False
    return all_ok


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_final_all.py")
    ap.add_argument("--output", default="trading_2_complete.py")
    ap.add_argument("--audit-only", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} bytes)")

    audit_ok = step1_audit(src)

    if args.audit_only:
        print(f"\n{'='*62}")
        print(f"Audit complete. No files modified.")
        sys.exit(0 if audit_ok else 1)

    src, ok20 = step2_fix_globals(src)
    src, ok21 = step3_fix_retry_config(src)
    src, ok22 = step4_fix_maxhold(src)

    verify_ok = step5_verify(src)

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  SYNTAX CHECK                                               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    try:
        compile(src, args.output, "exec")
        print("   ✅ compiles OK")
        syntax_ok = True
    except SyntaxError as e:
        print(f"   ❌ SyntaxError line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text!r}")
        syntax_ok = False

    if not (ok20 and ok21 and ok22 and verify_ok and syntax_ok):
        print(f"\n╔══════════════════════════════════════════════════════════════╗")
        print(f"║  ❌ ABORTED                                                 ║")
        print(f"╚══════════════════════════════════════════════════════════════╝")
        print(f"   FIX-20: {ok20}  FIX-21: {ok21}  FIX-22: {ok22}")
        print(f"   verify: {verify_ok}  syntax: {syntax_ok}")
        print(f"\n   Output NOT written. Input unchanged.")
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine — COMPLETE\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  Patch rounds (6):\n"
        "#    1. apply_live_parity_fixes.py    (19 fixes)\n"
        "#    2. fix_parity_issues.py          (6 corrections)\n"
        "#    3. fix_remaining_issues.py       (2 surgical)\n"
        "#    4. fix_leverage_tiers.py         (FIX-01-PROPER)\n"
        "#    5. fix_position_cache.py         (FIX-09-PROPER)\n"
        "#    6. fix_parity_v2.py              (FIX-20/21/22)\n"
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
        print(f"   ❌ written file broken at line {e.lineno}")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                        DONE                                 ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"   Input:   {args.input}  ({len(src):,} bytes)")
    print(f"   Output:  {args.output}  ({len(src_out):,} bytes)")
    print(f"   FIX-20:  {'✅' if ok20 else '❌'}")
    print(f"   FIX-21:  {'✅' if ok21 else '❌'}")
    print(f"   FIX-22:  {'✅' if ok22 else '❌'}")
    print(f"   verify:  {'✅' if verify_ok else '❌'}")
    print(f"   written: {'✅' if write_ok else '❌'}")

    if not write_ok:
        sys.exit(3)

    print(f"\n   ▶ Run:")
    print(f"     python {args.output} --mode backtest ...")
    print(f"     python {args.output} --mode testnet "
          f"--api-key ... --api-secret ...")


if __name__ == "__main__":
    main()
