#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_unified_v2.py
===================
نسخة مُصحَّحة من apply_unified.py.

التغيير الوحيد:
    Edit 3 يستخدم anchor سطر واحد إنجليزي فريد
    بدل anchor سطرين يعبر النص العربي.
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
        head = old[:60].split("\n")[0]
        idx = src.find(head)
        if idx >= 0:
            print(f"      near: {src[max(0, idx-120):idx+240]!r}")
        return src, False
    n = src.count(old)
    if n > 1:
        print(f"   ⚠️  [{label}] anchor ×{n}, replacing first")
    src = src.replace(old, new, 1)
    print(f"   ✅ [{label}]")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# UNIFIED block — نفس المحتوى من السكربت الأول
# ══════════════════════════════════════════════════════════════════════

# [سنستخدم نفس الكتلة من apply_unified.py حرفياً]
# سنقرأها من الملف الأصلي إن وُجد، أو نُدرجها كاملة هنا.

# لتبسيط الأمر، سأجعل السكربت يقرأ الكتلة من apply_unified.py إذا كان موجوداً.
# هذا يجعل السكربت قصيراً وموثوقاً.

def _load_unified_block_from_src():
    """يستخرج UNIFIED_BLOCK من apply_unified.py"""
    src_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "apply_unified.py")
    if not os.path.exists(src_file):
        return None
    try:
        with open(src_file, "r", encoding="utf-8") as f:
            content = f.read()
        # ابحث عن UNIFIED_BLOCK = r''' ... '''
        start_marker = "UNIFIED_BLOCK = r'''"
        start = content.find(start_marker)
        if start < 0:
            return None
        start += len(start_marker)
        end = content.find("'''", start)
        if end < 0:
            return None
        return content[start:end]
    except Exception as e:
        print(f"   ❌ Failed to extract block: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════
# Edit 1: insert block
# ══════════════════════════════════════════════════════════════════════

def edit1_insert_block(src):
    print("\n▶ Edit 1: insert UNIFIED block")
    anchor = "def load_symbol_meta(mode: str) -> Dict[str, Dict]:"
    if anchor not in src:
        print("   ❌ anchor not found")
        return src, False
    if "[UNIFIED DECISION ENGINE] — v1" in src:
        print("   ℹ️  already applied")
        return src, True

    block = _load_unified_block_from_src()
    if block is None:
        print("   ❌ failed to load UNIFIED block from apply_unified.py")
        return src, False

    src = src.replace(anchor, block + anchor, 1)
    print(f"   ✅ inserted ({len(block):,} chars)")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 2: store _sig_ref
# ══════════════════════════════════════════════════════════════════════

def edit2_store_sig_ref(src):
    print("\n▶ Edit 2: store _sig_ref in position dict")
    old = (
        "                            '_sym': sym,\n"
        "                            '_orig_score': float(sig.score),\n"
        "                        }"
    )
    new = (
        "                            '_sym': sym,\n"
        "                            '_orig_score': float(sig.score),\n"
        "                            '_sig_ref': sig,\n"
        "                        }"
    )
    return _replace_once(src, old, new, "store-sig-ref",
                          marker="'_sig_ref': sig,")


# ══════════════════════════════════════════════════════════════════════
# Edit 3 — المُصحَّح: anchor سطر واحد فقط
# ══════════════════════════════════════════════════════════════════════

def edit3_insert_live_hook_FIXED(src):
    print("\n▶ Edit 3 (FIXED): insert unified decision in run_live")
    if "[UNIFIED] Compute decision" in src:
        print("   ℹ️  already applied")
        return src, True

    # ═══ Anchor: سطر واحد إنجليزي فريد ═══
    anchor = "                    # ══ [SAFETY] Drawdown-aware risk reduction ══"

    if anchor not in src:
        print("   ❌ anchor '[SAFETY] Drawdown-aware' not found")
        # جرّب بـ indent أقل
        anchor = "                    # ══ [SAFETY] Drawdown-aware risk reduction ══"
        for indent in [" " * 20, " " * 24, " " * 16]:
            test = indent + "# ══ [SAFETY] Drawdown-aware risk reduction ══"
            if test in src:
                anchor = test
                print(f"   ℹ️  found with indent={len(indent)}")
                break
        else:
            print("   ❌ failed to find anchor with any indent")
            return src, False

    n = src.count(anchor)
    if n > 1:
        print(f"   ⚠️  anchor ×{n} — replacing first")

    injection = (
        "                    # ══ [UNIFIED] Compute decision ══\n"
        "                    _u_decision = None\n"
        "                    if _UNIFIED_ENABLED:\n"
        "                        try:\n"
        "                            _u_decision = compute_unified_decision(\n"
        "                                sym=sym, sig=sig, capital=cap_live,\n"
        "                                peak=peak_cap_live,\n"
        "                                open_pos_live=open_pos_live,\n"
        "                                corr_cache=corr_cache,\n"
        "                                exchange=exchange,\n"
        "                                ad=assets.get(sym), cfg=cfg,\n"
        "                            )\n"
        "                        except Exception as _ue:\n"
        "                            log.warning(f\"[Unified] {sym} error: {_ue}\")\n"
        "                            _u_decision = None\n"
        "                        if _u_decision is not None and not _u_decision[\"accept\"]:\n"
        "                            log.debug(f\"[Unified] {sym} rejected: {_u_decision['reason']}\")\n"
        "                            continue\n"
        "                    \n"
        + anchor
    )

    src = src.replace(anchor, injection, 1)
    print("   ✅ hook inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 4: bypass risk continue
# ══════════════════════════════════════════════════════════════════════

def edit4_bypass_risk_continue(src):
    print("\n▶ Edit 4: bypass risk_frac<=0")
    if "[UNIFIED] override risk_frac" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
        "                    if risk_frac <= 0.0:\n"
        "                        log.debug(f\"[Budget] {sym} skipped: no heat budget\")\n"
        "                        continue"
    )
    new = (
        "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
        "                    if risk_frac <= 0.0:\n"
        "                        # [UNIFIED] override risk_frac if unified accepts\n"
        "                        if _u_decision is not None and _u_decision.get(\"accept\"):\n"
        "                            risk_frac = float(_u_decision[\"f_actual\"])\n"
        "                        else:\n"
        "                            log.debug(f\"[Budget] {sym} skipped: no heat budget\")\n"
        "                            continue"
    )
    return _replace_once(src, old, new, "bypass-risk-continue")


# ══════════════════════════════════════════════════════════════════════
# Edit 5: override qty
# ══════════════════════════════════════════════════════════════════════

def edit5_override_qty(src):
    print("\n▶ Edit 5: override qty/leverage/risk")
    if "[UNIFIED] Apply qty/leverage/risk override" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        "                    # ══ [NOTIONAL CAP] ══\n"
        "                    qty = cap_notional(qty, lmt)\n"
        "\n"
        "                    if qty * lmt < cfg.MIN_NOTIONAL:\n"
        "                        continue"
    )
    new = (
        "                    # ══ [NOTIONAL CAP] ══\n"
        "                    qty = cap_notional(qty, lmt)\n"
        "\n"
        "                    # ══ [UNIFIED] Apply qty/leverage/risk override ══\n"
        "                    if _u_decision is not None and _u_decision.get(\"accept\"):\n"
        "                        qty = float(_u_decision[\"qty\"])\n"
        "                        dynamic_leverage = int(_u_decision[\"leverage\"])\n"
        "                        risk_frac = float(_u_decision[\"f_actual\"])\n"
        "\n"
        "                    if qty * lmt < cfg.MIN_NOTIONAL:\n"
        "                        continue"
    )
    return _replace_once(src, old, new, "override-qty")


# ══════════════════════════════════════════════════════════════════════
# Edit 6: record outcome
# ══════════════════════════════════════════════════════════════════════

def edit6_record_outcome(src):
    print("\n▶ Edit 6: record trade outcome")
    if "[UNIFIED] Record live trade outcome" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "                    del open_pos_live[sym]\n"
        "                    last_exit_time[sym] = time.time()\n"
        "                    log.info(f\"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]\")"
    )
    if anchor not in src:
        print("   ❌ exit anchor not found")
        return src, False

    injection = (
        "                    # ══ [UNIFIED] Record live trade outcome ══\n"
        "                    if _UNIFIED_ENABLED:\n"
        "                        try:\n"
        "                            _entry_px_u = float(pos.get('entry') or 0)\n"
        "                            _sl_d0_u = float(pos.get('sl_dist_initial') or 0)\n"
        "                            _exit_px_u = float(exec_price or 0)\n"
        "                            if (_entry_px_u > 0 and _sl_d0_u > 0\n"
        "                                    and _exit_px_u > 0):\n"
        "                                if pos.get('action') == 'BUY':\n"
        "                                    _pnl_frac_u = (_exit_px_u - _entry_px_u) / _entry_px_u\n"
        "                                else:\n"
        "                                    _pnl_frac_u = (_entry_px_u - _exit_px_u) / _entry_px_u\n"
        "                                _sl_frac_u = _sl_d0_u / _entry_px_u\n"
        "                                _R_u = _pnl_frac_u / _sl_frac_u if _sl_frac_u > 0 else 0.0\n"
        "                                _sig_u = pos.get('_sig_ref') if isinstance(pos, dict) else None\n"
        "                                _ad_u = assets.get(sym) if 'assets' in dir() else None\n"
        "                                _unified_record_trade(_sig_u, _ad_u, float(_R_u), _R_u > 0.5)\n"
        "                        except Exception as _re:\n"
        "                            log.debug(f\"[Unified] record failed: {_re}\")\n"
        "\n"
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ outcome recording inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 7: stats logger
# ══════════════════════════════════════════════════════════════════════

def edit7_wire_stats(src):
    print("\n▶ Edit 7: wire unified stats logger")
    if "# [UNIFIED] stats logger" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()"
    )
    if anchor not in src:
        print("   ❌ pos-cache anchor not found")
        return src, False

    new = (
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()\n"
        "            # [UNIFIED] stats logger\n"
        "            _unified_log_stats()"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ stats logger wired")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 8: CLI args
# ══════════════════════════════════════════════════════════════════════

def edit8_add_cli(src):
    print("\n▶ Edit 8: add CLI args")
    if 'p.add_argument("--unified"' in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = "    args = p.parse_args()"
    if anchor not in src:
        print("   ❌ parse_args anchor not found")
        return src, False

    injection = (
        '    # ══ [UNIFIED] CLI args ══\n'
        '    p.add_argument("--unified", action="store_true",\n'
        '                   help="Enable Unified Decision Engine")\n'
        '    p.add_argument("--unified-weights", type=str, default=None,\n'
        '                   help="Path to unified weights JSON")\n'
        '    p.add_argument("--unified-epsilon", type=float, default=None,\n'
        '                   help="Ruin tolerance (default 0.001)")\n'
        '    p.add_argument("--unified-shrinkage", type=float, default=None,\n'
        '                   help="Kelly shrinkage factor (default 0.5)")\n'
        '\n'
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ CLI args added")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 9: wire CLI
# ══════════════════════════════════════════════════════════════════════

def edit9_wire_cli(src):
    print("\n▶ Edit 9: wire CLI to globals")
    if "# [UNIFIED] CLI wiring" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = "    args = p.parse_args()"
    if anchor not in src:
        print("   ❌ parse_args anchor not found")
        return src, False

    injection = anchor + (
        "\n"
        "    # [UNIFIED] CLI wiring\n"
        "    try:\n"
        "        if getattr(args, 'unified', False):\n"
        "            globals()['_UNIFIED_ENABLED'] = True\n"
        "            if getattr(args, 'unified_weights', None):\n"
        "                globals()['_UNIFIED_WEIGHTS_PATH'] = str(args.unified_weights)\n"
        "            if getattr(args, 'unified_epsilon', None) is not None:\n"
        "                globals()['_UNIFIED_EPSILON'] = float(args.unified_epsilon)\n"
        "            if getattr(args, 'unified_shrinkage', None) is not None:\n"
        "                globals()['_UNIFIED_SHRINKAGE'] = float(args.unified_shrinkage)\n"
        "            _unified_load_state()\n"
        "            log.info(\n"
        "                f\"[Unified] ENABLED \"\n"
        "                f\"(ε={_UNIFIED_EPSILON}, shrink={_UNIFIED_SHRINKAGE})\"\n"
        "            )\n"
        "        else:\n"
        "            log.info(\"[Unified] Disabled (use --unified to enable)\")\n"
        "    except Exception as _e:\n"
        "        log.warning(f\"[Unified] CLI wiring failed: {_e}\")"
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ CLI wired")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = [
        ("UNIFIED block",           "[UNIFIED DECISION ENGINE] — v1"),
        ("_UNIFIED_ENABLED",        "_UNIFIED_ENABLED: bool = False"),
        ("main decision",           "def compute_unified_decision("),
        ("store sig_ref",           "'_sig_ref': sig,"),
        ("live hook",               "[UNIFIED] Compute decision"),
        ("bypass risk continue",    "[UNIFIED] override risk_frac"),
        ("qty override",            "[UNIFIED] Apply qty/leverage/risk override"),
        ("record live outcome",     "[UNIFIED] Record live trade outcome"),
        ("stats wired",             "# [UNIFIED] stats logger"),
        ("CLI arg --unified",       'p.add_argument("--unified"'),
        ("CLI wiring",              "# [UNIFIED] CLI wiring"),
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
        ("def main", "def main(", 1),
        ("def build_signals", "def build_signals(", 1),
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
    ap.add_argument("--input", default="trading_2_mfal.py")
    ap.add_argument("--output", default="trading_2_unified.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} chars)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  UNIFIED DECISION ENGINE — v2 (fixed anchor)                ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: insert block",       edit1_insert_block),
        ("Edit 2: store sig_ref",      edit2_store_sig_ref),
        ("Edit 3: hook (FIXED)",       edit3_insert_live_hook_FIXED),
        ("Edit 4: bypass risk",        edit4_bypass_risk_continue),
        ("Edit 5: override qty",       edit5_override_qty),
        ("Edit 6: record outcome",     edit6_record_outcome),
        ("Edit 7: wire stats",         edit7_wire_stats),
        ("Edit 8: CLI args",           edit8_add_cli),
        ("Edit 9: wire CLI",           edit9_wire_cli),
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
        "#  UNIFIED DECISION ENGINE Build\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  Unified Decision Engine replaces the sequential\n"
        "#  (risk → leverage → qty) pipeline with a single\n"
        "#  constrained Bayesian optimization:\n"
        "#\n"
        "#      (qty*, L*, a*) = argmax a·E[log W_T]\n"
        "#      subject to all constraints simultaneously.\n"
        "#\n"
        "#  Default: DISABLED. Enable with --unified flag.\n"
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
    print("  ▶ Run with UNIFIED enabled:")
    print(f"     python {args.output} --mode testnet --unified --api-key ... "
          f"--api-secret ...")

    if not write_ok:
        sys.exit(3)


if __name__ == "__main__":
    main()
