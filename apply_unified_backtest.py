#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_unified_backtest.py
=========================
يُطبّق Unified Decision Engine على مسار backtest (simulate_portfolio).

المتطلبات:
    - trading_2_unified.py (من apply_unified_v2.py)
    - apply_unified.py موجود في نفس المجلد (لاستخراج UNIFIED_BLOCK)

الاستخدام:
    python apply_unified_backtest.py \\
        --input  trading_2_unified.py \\
        --output trading_2_unified_full.py
"""

import argparse
import os
import sys
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _replace_once(src, old, new, label, marker=None):
    if marker and marker in src:
        print(f"   ℹ️  [{label}] already applied")
        return src, True
    if old not in src:
        print(f"   ❌ [{label}] anchor not found")
        head = old[:70].split("\n")[0]
        idx = src.find(head)
        if idx >= 0:
            print(f"      near: {src[max(0, idx-120):idx+280]!r}")
        return src, False
    n = src.count(old)
    if n > 1:
        print(f"   ⚠️  [{label}] anchor ×{n}, replacing first")
    src = src.replace(old, new, 1)
    print(f"   ✅ [{label}]")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 1: Patch tiers branch (remove exchange=None path)
# ══════════════════════════════════════════════════════════════════════

def edit1_patch_tiers(src):
    print("\n▶ Edit 1: patch tiers branch in compute_unified_decision")
    if "# [UNIFIED-BT] tiers always from _symbol_tiers" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        "        try:\n"
        "            if exchange is not None:\n"
        "                tiers = _symbol_tiers(sym, cfg)\n"
        "            else:\n"
        "                tiers = list(range(int(cfg.LEVERAGE_MIN),\n"
        "                                    int(cfg.LEVERAGE_MAX) + 1))\n"
        "        except Exception:\n"
        "            tiers = [int(cfg.LEVERAGE_MIN), int(cfg.LEVERAGE_MAX)]"
    )
    new = (
        "        try:\n"
        "            # [UNIFIED-BT] tiers always from _symbol_tiers\n"
        "            # (works with exchange=None because _symbol_tiers\n"
        "            #  reads from _SYMBOL_LEV_TIERS populated by prefetch)\n"
        "            tiers = _symbol_tiers(sym, cfg)\n"
        "        except Exception:\n"
        "            tiers = [int(cfg.LEVERAGE_MIN), int(cfg.LEVERAGE_MAX)]"
    )
    return _replace_once(src, old, new, "tiers-branch")


# ══════════════════════════════════════════════════════════════════════
# Edit 2: Insert unified hook in simulate_portfolio
# ══════════════════════════════════════════════════════════════════════

def edit2_insert_backtest_hook(src):
    print("\n▶ Edit 2: insert unified decision hook in simulate_portfolio")
    if "[UNIFIED-BT] Compute decision" in src:
        print("   ℹ️  already applied")
        return src, True

    # Anchor: risk budget section in simulate_portfolio (8-space indent)
    anchor = (
        "        # ══ [PORTFOLIO RISK BUDGET] ══\n"
        "        # Portfolio-coordinated sizing: heat budget + fair share + strength weighting\n"
        "        free_ratio = max(0.0, (capital - CFG.CAPITAL_FLOOR) / capital)"
    )
    if anchor not in src:
        print("   ❌ portfolio risk budget anchor not found")
        return src, False

    injection = (
        "        # ══ [UNIFIED-BT] Compute decision ══\n"
        "        _u_decision = None\n"
        "        if _UNIFIED_ENABLED:\n"
        "            try:\n"
        "                # Convert OpenPosition objects to dict for unified engine\n"
        "                _bt_pos_dict = {}\n"
        "                for _bsym, _bpos in open_pos.items():\n"
        "                    try:\n"
        "                        _bsig = getattr(_bpos, 'signal', None)\n"
        "                        _bdyn = float(getattr(_bsig, 'dynamic_risk', 0.01)) if _bsig else 0.01\n"
        "                        _bt_pos_dict[_bsym] = {\n"
        "                            'entry': float(getattr(_bpos, 'entry_px', 0)),\n"
        "                            'qty': float(getattr(_bpos, 'pos_size', 0)),\n"
        "                            'leverage': int(CFG.LEVERAGE_BASE or 1),\n"
        "                            'dyn_risk': _bdyn,\n"
        "                        }\n"
        "                    except Exception:\n"
        "                        pass\n"
        "                _u_decision = compute_unified_decision(\n"
        "                    sym=sym, sig=sig, capital=capital,\n"
        "                    peak=peak_cap,\n"
        "                    open_pos_live=_bt_pos_dict,\n"
        "                    corr_cache=corr_matrix,\n"
        "                    exchange=None,\n"
        "                    ad=ad, cfg=CFG,\n"
        "                )\n"
        "            except Exception as _ue:\n"
        "                log.warning(f\"[Unified-BT] {sym} error: {_ue}\")\n"
        "                _u_decision = None\n"
        "            if _u_decision is not None and not _u_decision[\"accept\"]:\n"
        "                log.debug(f\"[Unified-BT] {sym} rejected: {_u_decision['reason']}\")\n"
        "                continue\n"
        "\n"
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ backtest hook inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 3: Override risk_frac in backtest
# ══════════════════════════════════════════════════════════════════════

def edit3_override_risk_frac(src):
    print("\n▶ Edit 3: override risk_frac in backtest")
    if "[UNIFIED-BT] override risk_frac" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        "        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)\n"
        "        if risk_frac <= 0.0:\n"
        "            log.debug(f\"[Budget] {sym} skipped: no heat budget available\")\n"
        "            continue"
    )
    new = (
        "        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)\n"
        "        if risk_frac <= 0.0:\n"
        "            # [UNIFIED-BT] override risk_frac if unified accepts\n"
        "            if _u_decision is not None and _u_decision.get(\"accept\"):\n"
        "                risk_frac = float(_u_decision[\"f_actual\"])\n"
        "            else:\n"
        "                log.debug(f\"[Budget] {sym} skipped: no heat budget available\")\n"
        "                continue"
    )
    return _replace_once(src, old, new, "override-risk-frac")


# ══════════════════════════════════════════════════════════════════════
# Edit 4: Override qty/leverage (first block)
# ══════════════════════════════════════════════════════════════════════

def edit4_override_qty_first(src):
    print("\n▶ Edit 4: override qty/leverage (first block)")
    if "[UNIFIED-BT] override qty (first)" in src:
        print("   ℹ️  already applied")
        return src, True

    # Anchor: the first qty cap block (uses opt_px)
    old = (
        "        max_notional = capital * dynamic_leverage\n"
        "        qty = min(qty, max_notional / opt_px)\n"
        "\n"
        "        # ══ [NOTIONAL CAP] ══\n"
        "        qty = cap_notional(qty, opt_px)\n"
        "\n"
        "        not_ = qty * opt_px\n"
        "\n"
        "        if not_ < CFG.MIN_NOTIONAL:\n"
        "            continue"
    )
    new = (
        "        max_notional = capital * dynamic_leverage\n"
        "        qty = min(qty, max_notional / opt_px)\n"
        "\n"
        "        # ══ [NOTIONAL CAP] ══\n"
        "        qty = cap_notional(qty, opt_px)\n"
        "\n"
        "        # ══ [UNIFIED-BT] override qty (first) ══\n"
        "        if _u_decision is not None and _u_decision.get(\"accept\"):\n"
        "            qty = float(_u_decision[\"qty\"])\n"
        "            dynamic_leverage = int(_u_decision[\"leverage\"])\n"
        "            risk_frac = float(_u_decision[\"f_actual\"])\n"
        "            max_notional = capital * dynamic_leverage\n"
        "            risk_amt = qty * delta\n"
        "\n"
        "        not_ = qty * opt_px\n"
        "\n"
        "        if not_ < CFG.MIN_NOTIONAL:\n"
        "            continue"
    )
    return _replace_once(src, old, new, "override-qty-first")


# ══════════════════════════════════════════════════════════════════════
# Edit 5: Override qty/leverage (second block, uses eff_px)
# ══════════════════════════════════════════════════════════════════════

def edit5_override_qty_second(src):
    print("\n▶ Edit 5: override qty/leverage (second block)")
    if "[UNIFIED-BT] override qty (second)" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        "        # إعادة تقييم حفظ الطاقة وحجم المركز النهائي\n"
        "        qty = min(risk_amt / delta, max_notional / eff_px)\n"
        "\n"
        "        # ══ [NOTIONAL CAP] ══\n"
        "        qty = cap_notional(qty, eff_px)\n"
        "\n"
        "        not_ = qty * eff_px\n"
        "\n"
        "        if not_ < CFG.MIN_NOTIONAL: continue"
    )
    new = (
        "        # إعادة تقييم حفظ الطاقة وحجم المركز النهائي\n"
        "        qty = min(risk_amt / delta, max_notional / eff_px)\n"
        "\n"
        "        # ══ [NOTIONAL CAP] ══\n"
        "        qty = cap_notional(qty, eff_px)\n"
        "\n"
        "        # ══ [UNIFIED-BT] override qty (second) ══\n"
        "        if _u_decision is not None and _u_decision.get(\"accept\"):\n"
        "            qty = float(_u_decision[\"qty\"])\n"
        "\n"
        "        not_ = qty * eff_px\n"
        "\n"
        "        if not_ < CFG.MIN_NOTIONAL: continue"
    )
    return _replace_once(src, old, new, "override-qty-second")


# ══════════════════════════════════════════════════════════════════════
# Edit 6: Record trade outcome in _close
# ══════════════════════════════════════════════════════════════════════

def edit6_record_outcome(src):
    print("\n▶ Edit 6: record trade outcome in _close")
    if "[UNIFIED-BT] Record trade outcome" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "        # ══ [TradeLog] تسجيل الصفقة ══\n"
        "        try:\n"
        "            _trade_log_from_backtest(\n"
        "                pos, ad, exit_eff, exit_rsn, exit_ci,\n"
        "                pos.entry_cap, capital,\n"
        "                net_pnl=net, log_return=lr\n"
        "            )\n"
        "        except Exception as _tle:\n"
        "            log.debug(f\"[TradeLog] backtest hook failed: {_tle}\")"
    )
    if anchor not in src:
        print("   ❌ TradeLog anchor not found")
        return src, False

    injection = anchor + (
        "\n"
        "\n"
        "        # ══ [UNIFIED-BT] Record trade outcome ══\n"
        "        if _UNIFIED_ENABLED:\n"
        "            try:\n"
        "                _sl_d0_u = float(getattr(pos, 'sl_dist_initial', 0) or 0)\n"
        "                _entry_px_u = float(pos.entry_px)\n"
        "                _exit_px_u = float(exit_eff)\n"
        "                if _sl_d0_u > 0 and _entry_px_u > 0:\n"
        "                    if sig.action == \"BUY\":\n"
        "                        _pnl_move_u = _exit_px_u - _entry_px_u\n"
        "                    else:\n"
        "                        _pnl_move_u = _entry_px_u - _exit_px_u\n"
        "                    _R_u = _pnl_move_u / _sl_d0_u\n"
        "                    _unified_record_trade(sig, ad, float(_R_u), _R_u > 0.5)\n"
        "            except Exception as _re:\n"
        "                log.debug(f\"[Unified-BT] record failed: {_re}\")"
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ outcome recording inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 7: Wire stats logger in run_backtest
# ══════════════════════════════════════════════════════════════════════

def edit7_wire_stats(src):
    print("\n▶ Edit 7: wire unified stats in run_backtest")
    if "[UNIFIED-BT] stats logger" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        '    trades, equity = simulate_portfolio(sigs, assets, corr_matrix, "backtest")\n'
        '    log.info(f"  ✔ {len(trades):,} صفقة")'
    )
    if anchor not in src:
        print("   ❌ simulate_portfolio return anchor not found")
        return src, False

    new = anchor + (
        "\n"
        "    # [UNIFIED-BT] stats logger\n"
        "    try:\n"
        "        _unified_log_stats()\n"
        "    except Exception as _se:\n"
        "        log.debug(f\"[Unified-BT] stats failed: {_se}\")"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ stats logger wired")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = [
        ("tiers patch",             "[UNIFIED-BT] tiers always from _symbol_tiers"),
        ("backtest hook",           "[UNIFIED-BT] Compute decision"),
        ("override risk_frac",      "[UNIFIED-BT] override risk_frac"),
        ("override qty (first)",    "[UNIFIED-BT] override qty (first)"),
        ("override qty (second)",   "[UNIFIED-BT] override qty (second)"),
        ("record outcome",          "[UNIFIED-BT] Record trade outcome"),
        ("stats logger",            "[UNIFIED-BT] stats logger"),
    ]
    all_ok = True
    for label, marker in checks:
        ok = marker in src
        print(f"   {'✅' if ok else '❌'} {label}")
        if not ok:
            all_ok = False

    print("\n   Sanity:")
    for label, marker, expect in [
        ("def run_live", "def run_live(", 1),
        ("def run_backtest", "def run_backtest(", 1),
        ("def simulate_portfolio", "def simulate_portfolio(", 1),
        ("def main", "def main(", 1),
        ("def compute_unified_decision",
            "def compute_unified_decision(", 1),
        ("def _close (nested)", "def _close(pos, ad, exit_px", 1),
    ]:
        cnt = src.count(marker)
        ok = (cnt == expect)
        print(f"   {'✅' if ok else '❌'} {label}: {cnt}")
        if not ok:
            all_ok = False
    return all_ok


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="trading_2_unified.py")
    ap.add_argument("--output", default="trading_2_unified_full.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} chars)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  UNIFIED for BACKTEST — Batch Apply                         ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: patch tiers",          edit1_patch_tiers),
        ("Edit 2: backtest hook",        edit2_insert_backtest_hook),
        ("Edit 3: override risk_frac",   edit3_override_risk_frac),
        ("Edit 4: override qty (1st)",   edit4_override_qty_first),
        ("Edit 5: override qty (2nd)",   edit5_override_qty_second),
        ("Edit 6: record outcome",       edit6_record_outcome),
        ("Edit 7: wire stats",           edit7_wire_stats),
    ]
    results = []
    for label, fn in steps:
        try:
            src, ok = fn(src)
            results.append((label, ok))
        except Exception as e:
            print(f"   ❌ {label} exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((label, False))

    all_ok = verify(src)

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  SYNTAX CHECK                                               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    syntax_ok = True
    try:
        compile(src, args.output, "exec")
        print("   ✅ compiles OK")
    except SyntaxError as e:
        print(f"   ❌ SyntaxError line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text!r}")
        syntax_ok = False

    if not (all_ok and syntax_ok):
        print("\n╔══════════════════════════════════════════════════════════════╗")
        print("║  ❌ ABORTED — output NOT written                            ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        for label, ok in results:
            print(f"   {'✅' if ok else '❌'} {label}")
        print(f"   verify:  {'OK' if all_ok else 'FAILED'}")
        print(f"   syntax:  {'OK' if syntax_ok else 'FAILED'}")
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine\n"
        "#  UNIFIED DECISION ENGINE — FULL (live + backtest)\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  Unified decision applied to BOTH:\n"
        "#    • run_live (via apply_unified_v2.py)\n"
        "#    • simulate_portfolio (via this script)\n"
        "#\n"
        "#  Enable with --unified. Works in backtest AND live.\n"
        "# ═══════════════════════════════════════════════════════════\n"
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
        print(f"   ❌ Written file broken at line {e.lineno}")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                             DONE                             ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"   Input:  {args.input}  ({len(src):,} chars)")
    print(f"   Output: {args.output}  ({len(src_out):,} chars)")
    for label, ok in results:
        print(f"   {'✅' if ok else '❌'} {label}")
    print(f"   verify:  {'✅ ALL PASSED' if all_ok else '❌ FAILED'}")
    print(f"   written: {'✅ OK' if write_ok else '❌ FAILED'}")
    print()
    print("  ▶ Run backtest with UNIFIED:")
    print(f"     python {args.output} --mode backtest --unified "
          f"--capital 100 --nassets 5 --maxcon 2 --timeframe 4h --history-days 30")
    print()
    print("  ▶ Run testnet with UNIFIED:")
    print(f"     python {args.output} --mode testnet --unified "
          f"--api-key ... --api-secret ...")

    if not write_ok:
        sys.exit(3)


if __name__ == "__main__":
    main()
