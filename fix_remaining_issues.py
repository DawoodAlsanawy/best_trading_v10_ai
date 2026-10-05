#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_remaining_issues.py
=======================
سكربت جراحي يستكمل FIX-04 و FIX-09 التي لم تُطبَّق،
ويُنظّف التحقق من FIX-15b الزائف.

الاستخدام:
  python fix_remaining_issues.py \
      --input trading_2_fixed_v2.py \
      --output trading_2_final.py
"""

import argparse
import os
import re
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# STEP 0: Locate the exact text around missing anchors
# ════════════════════════════════════════════════════════════════

def dump_context(src, marker_substring, label, window=600):
    """Print context around a substring so we can see exact format."""
    idx = src.find(marker_substring)
    if idx < 0:
        print(f"   ⚠️  [{label}] substring '{marker_substring[:50]}' "
              f"NOT found in source")
        return None
    start = max(0, idx - 100)
    end = min(len(src), idx + window)
    snippet = src[start:end]
    print(f"   ℹ️  [{label}] found at offset {idx}")
    print(f"   ───── CONTEXT (repr) ─────")
    # Show repr of a limited window to expose hidden chars
    print(repr(snippet[:400]))
    print(f"   ──────────────────────────")
    return idx


# ════════════════════════════════════════════════════════════════
# FIX-04 (retry): GTX fallback — robust with regex
# ════════════════════════════════════════════════════════════════

def fix_04_retry(src):
    """
    يبحث عن الكتلة الحالية لأمر GTX عبر regex مرن،
    يستبدلها بإصدار يدعم fallback.
    """

    # نبحث عن أبسط مرساة: السطر الذي يحتوي 'GTX rejected' متبوعاً بـ return None
    # مع أي مسافات بادئة.
    pattern = re.compile(
        r'(?P<indent>[ ]+)(?P<comment># ══ وضع الأمر النهائي ══\s*\n)'
        r'(?P<indent2>[ ]+)if _exec_mode == "gtx":\s*\n'
        r'(?P<indent3>[ ]+)try:\s*\n'
        r'(?P<indent4>[ ]+)o = exchange\.create_order\(\s*\n'
        r'(?P<indent5>[ ]+)sym, \'limit\', side, qty, target,\s*\n'
        r'(?P<indent6>[ ]+)params=\{\'timeInForce\': \'GTX\'\}\s*\n'
        r'(?P<indent7>[ ]+)\)\s*\n'
        r'(?P<indent8>[ ]+)except Exception as e:\s*\n'
        r'(?P<indent9>[ ]+)log\.debug\(f"\[Pending\] \{sym\} GTX rejected.*?\)\s*\n'
        r'(?P<indent10>[ ]+)return None',
        re.MULTILINE | re.DOTALL
    )

    m = pattern.search(src)
    if not m:
        print("   ❌ [FIX-04-retry] block pattern not matched — "
              "dumping diagnostic context")
        dump_context(src, "GTX rejected", "FIX-04-retry")
        return src, False

    indent = m.group('indent')          # usually 4 spaces
    I = indent                          # shorthand

    new_block = (
        f'{I}# ══ وضع الأمر النهائي ══\n'
        f'{I}if _exec_mode == "gtx":\n'
        f'{I}    try:\n'
        f'{I}        o = exchange.create_order(\n'
        f'{I}            sym, \'limit\', side, qty, target,\n'
        f'{I}            params={{\'timeInForce\': \'GTX\'}}\n'
        f'{I}        )\n'
        f'{I}    except Exception as e:\n'
        f'{I}        _emsg = str(e).lower()\n'
        f'{I}        # [FIX-4.1] GTX rejected because it would cross '
        f'the book.\n'
        f'{I}        # Slide 1 tick further and retry once.\n'
        f'{I}        if (\'-2010\' in _emsg or \'post only\' in _emsg\n'
        f'{I}                or \'gtx\' in _emsg):\n'
        f'{I}            log.info(f"[Pending] {{sym}} GTX rejected — "\n'
        f'{I}                     f"falling back with wider offset")\n'
        f'{I}            try:\n'
        f'{I}                _tick = _get_tick_size(exchange, sym) '
        f'or target * 1e-5\n'
        f'{I}                if side == \'buy\':\n'
        f'{I}                    target2 = target - _tick\n'
        f'{I}                else:\n'
        f'{I}                    target2 = target + _tick\n'
        f'{I}                o = exchange.create_order(\n'
        f'{I}                    sym, \'limit\', side, qty, target2,\n'
        f'{I}                    params={{\'timeInForce\': \'GTX\'}}\n'
        f'{I}                )\n'
        f'{I}                target = target2\n'
        f'{I}            except Exception as e2:\n'
        f'{I}                log.warning(f"[Pending] {{sym}} GTX "\n'
        f'{I}                            f"fallback failed: {{e2}}")\n'
        f'{I}                return None\n'
        f'{I}        else:\n'
        f'{I}            log.debug(f"[Pending] {{sym}} order rejected @ "\n'
        f'{I}                      f"{{target:.6f}}: {{e}}")\n'
        f'{I}            return None'
    )

    src = src[:m.start()] + new_block + src[m.end():]
    return src, True


# ════════════════════════════════════════════════════════════════
# FIX-09 (retry): -2022 handling — surgical insertion
# ════════════════════════════════════════════════════════════════

def fix_09_retry(src):
    """
    يبحث عن الكتلة التي تحتوي '⚠️ [Exit]' و'no fill' بعد 'reduceOnly'
    يدوياً عبر regex أكثر مرونة. تمييز FIX-14 vs FIX-09 anchor:

    - FIX-14 غيّر إلى: "attempt {_retry_cnt}/3"
    - FIX-09 كان يبحث عن: "protective orders INTACT on exchange"

    الحل: نبحث عن أي كتلة warning لـ no-fill، ونحقن فحص المركز
    في بدايتها.
    """

    # نبحث عن أي occurrence لهذا النمط (بعد FIX-14):
    #   log.warning(f"⚠️ [Exit] {sym} no fill ... continue
    pattern = re.compile(
        r'(?P<indent>[ ]+)if not _exit_ok:\s*\n'
        r'(?P<indent2>[ ]+)log\.warning\(\s*\n'
        r'(?P<indent3>[ ]+)f"[^\n]*\[Exit\][^\n]*no fill[^\n]*"\s*\n'
        r'(?P<indent4>[ ]+)\)\s*\n'
        r'(?P<indent5>[ ]+)continue',
        re.MULTILINE
    )

    m = pattern.search(src)
    if not m:
        print("   ❌ [FIX-09-retry] no-fill block not found — "
              "dumping diagnostic context")
        dump_context(src, "no fill", "FIX-09-retry")
        return src, False

    I = m.group('indent')          # indentation of `if not _exit_ok:`

    new_block = (
        f'{I}if not _exit_ok:\n'
        f'{I}    # [FIX-7.7] Check if exchange already closed the '
        f'position\n'
        f'{I}    # (broker-side STOP_MARKET). If yes, treat as '
        f'success.\n'
        f'{I}    try:\n'
        f'{I}        _pos_chk = exchange.fetch_positions([sym])\n'
        f'{I}        _exch_amt = 0.0\n'
        f'{I}        for _pp in _pos_chk:\n'
        f'{I}            _amt_pp = float(_pp[\'info\'].get(\n'
        f'{I}                \'positionAmt\', 0) or 0)\n'
        f'{I}            if abs(_amt_pp) > 0:\n'
        f'{I}                _exch_amt = abs(_amt_pp)\n'
        f'{I}                break\n'
        f'{I}        if _exch_amt <= 0:\n'
        f'{I}            log.info(\n'
        f'{I}                f"✅ [Exit] {{sym}} position already "\n'
        f'{I}                f"closed on exchange (protective "\n'
        f'{I}                f"order fired) — removing local"\n'
        f'{I}            )\n'
        f'{I}            try:\n'
        f'{I}                _cancel_all_protective_orders(\n'
        f'{I}                    exchange, sym)\n'
        f'{I}            except Exception:\n'
        f'{I}                pass\n'
        f'{I}            del open_pos_live[sym]\n'
        f'{I}            last_exit_time[sym] = time.time()\n'
        f'{I}            continue\n'
        f'{I}    except Exception as _e:\n'
        f'{I}        log.debug(f"[Exit] position check "\n'
        f'{I}                  f"failed {{sym}}: {{_e}}")\n'
        f'{I}    # ── Fall through to existing warning + continue ──\n'
        f'{I}    log.warning(\n'
        f'{I}        f"⚠️ [Exit] {{sym}} no fill — position stays, "\n'
        f'{I}        f"protective orders INTACT on exchange"\n'
        f'{I}    )\n'
        f'{I}    continue'
    )

    src = src[:m.start()] + new_block + src[m.end():]
    return src, True


# ════════════════════════════════════════════════════════════════
# FIX-15b (retry): robust trail snapshot
# ════════════════════════════════════════════════════════════════

def fix_15b_retry(src):
    """
    FIX-15a موجود لكن يفتقد الحماية الكاملة. نضيف bootstrap
    قبل `rec = {` في place_pending_entry إذا لم يكن موجوداً.
    """
    if "[FIX-15b] Trail params snapshot (robust version)" in src:
        print("   ✅ [FIX-15b-retry] already present")
        return src, True

    # ابحث عن "rec = {\n        'order_id'" (بداية بناء rec)
    pattern = re.compile(
        r'(?P<indent>[ ]+)rec = \{\s*\n'
        r'(?P<indent2>[ ]+)\'order_id\': str\(o\[\'id\'\]\),',
        re.MULTILINE
    )
    m = pattern.search(src)
    if not m:
        print("   ⚠️  [FIX-15b-retry] rec = { anchor not found")
        return src, False

    I = m.group('indent')

    bootstrap = (
        f'{I}# [FIX-15b] Trail params snapshot (robust version)\n'
        f'{I}_trail_d_snapshot, _trail_a_snapshot = 0.003, 0.004\n'
        f'{I}try:\n'
        f'{I}    if ad is not None and hasattr(ad, \'E_therm\') \\\n'
        f'{I}            and len(ad.E_therm) > 0:\n'
        f'{I}        _fi_snap = max(0, min(int(getattr(sig, '
        f'\'feat_idx\', 0)),\n'
        f'{I}                              len(ad.E_therm) - 1))\n'
        f'{I}        _td_snap, _ta_snap = compute_trail_params(ad, '
        f'_fi_snap)\n'
        f'{I}        if _td_snap > 0 and _ta_snap > 0:\n'
        f'{I}            _trail_d_snapshot = float(_td_snap)\n'
        f'{I}            _trail_a_snapshot = float(_ta_snap)\n'
        f'{I}except Exception as _e:\n'
        f'{I}    log.debug(f"[FIX-15b] trail snapshot failed: {{_e}}")\n'
        f'\n'
    )

    src = src[:m.start()] + bootstrap + src[m.start():]
    return src, True


# ════════════════════════════════════════════════════════════════
# STEP 2: Comprehensive verification
# ════════════════════════════════════════════════════════════════

def verify_all(src):
    """التحقق الشامل من كل الإصلاحات الحرجة."""
    checks = {
        # core
        "snap-leverage":          "Snap to Binance valid tier",
        "step-size":              "def _get_step_size",
        "round-qty":              "def _round_qty",
        "min-notional":           "def _get_min_notional",
        # FIX-03
        "qty-sanitize":           "[FIX-4.2/4.3] Sanitize qty + notional",
        # FIX-04
        "gtx-fallback":           "[FIX-4.1] GTX rejected because it would cross",
        # FIX-05
        "cap-snapshot-read":      "[FIX-05b] Read capital from run_live",
        "cap-publish":            "[FIX-05c] Publish to module-level",
        # FIX-06
        "partial-accurate":       "[FIX-06b] Only mark partial as taken if",
        # FIX-07
        "physics-fi":             "points to last CLOSED bar",
        # FIX-08
        "dup-topo":               "(Topo-Div already checked above",
        # FIX-09
        "reduceonly-2022":        "[FIX-7.7] Check if exchange already closed",
        # FIX-10
        "fee-entry":              "[FIX-10.1] احسب net_pnl مع الرسوم"
                                  if False else
                                  "[FIX-10b] Entry is always maker",
        # FIX-11
        "clean-after-exit":       "[FIX-11b] Removed redundant cleanup",
        # FIX-12
        "pending-stale":          "stale cancel {sym} oid",
        # FIX-13
        "reconcile-prot":         "protective orders placed",
        # FIX-14
        "exit-retry":             "forcing MARKET after",
        # FIX-15
        "adv-snapshot":           "[FIX-15b] Trail params snapshot (robust version)",
        # FIX-16
        "promote-trail":          "Prefer snapshot in rec",
        # FIX-17
        "partial-fees":           "subtract fees from partial",
        # FIX-18
        "rate-tracker":           "Count actual exchange rate-limit hits",
        # FIX-19
        "prot-rollback":          "rolling back any placed TP",
        # helper
        "exit_is_taker":          "def _exit_is_taker",
    }

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  VERIFY: All critical fixes present                     ║")
    print("╚══════════════════════════════════════════════════════════╝")

    results = {}
    for tag, marker in checks.items():
        present = marker in src
        icon = "✅" if present else "❌"
        print(f"   {icon} [{tag}]")
        results[tag] = present
    n_ok = sum(1 for v in results.values() if v)
    print(f"\n   Summary: {n_ok}/{len(checks)} present")
    return results


# ════════════════════════════════════════════════════════════════
# STEP 3: Sanity checks (no accidental damage)
# ════════════════════════════════════════════════════════════════

def sanity_check(src):
    """فحوصات أن البنية العامة سليمة."""
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  SANITY: Structural integrity                           ║")
    print("╚══════════════════════════════════════════════════════════╝")

    checks = {
        "class Config":            src.count("class Config:"),
        "def run_live":            src.count("def run_live("),
        "def run_backtest":        src.count("def run_backtest("),
        "def build_signals":       src.count("def build_signals("),
        "def simulate_portfolio":  src.count("def simulate_portfolio("),
        "def place_pending_entry": src.count("def place_pending_entry("),
        "def _place_protective_orders":
            src.count("def _place_protective_orders("),
        "def execute_post_only":   src.count("def execute_post_only("),
    }
    all_ok = True
    for name, cnt in checks.items():
        ok = cnt == 1
        icon = "✅" if ok else "⚠️"
        print(f"   {icon} {name}: {cnt}")
        if not ok:
            all_ok = False
    return all_ok


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_fixed_v2.py")
    ap.add_argument("--output", default="trading_2_final.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {len(src):,} bytes from {args.input}")

    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  APPLY: Remaining surgical fixes                        ║")
    print("╚══════════════════════════════════════════════════════════╝")

    print("\n▶ FIX-04 (retry): GTX rejection fallback")
    src, ok04 = fix_04_retry(src)
    print(f"   {'✅ applied' if ok04 else '❌ failed'}")

    print("\n▶ FIX-09 (retry): -2022 / exchange-already-closed detection")
    src, ok09 = fix_09_retry(src)
    print(f"   {'✅ applied' if ok09 else '❌ failed'}")

    print("\n▶ FIX-15b (retry): robust trail snapshot")
    src, ok15 = fix_15b_retry(src)
    print(f"   {'✅ applied' if ok15 else '⚠️  skipped'}")

    # Verify all
    results = verify_all(src)

    # Sanity
    sanity_ok = sanity_check(src)

    # Write output (only if syntax OK)
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  WRITE: Output + syntax check                           ║")
    print("╚══════════════════════════════════════════════════════════╝")

    header = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════
#  trading_2_final.py — Live/Backtest Parity Build (final)
#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
#  Base: {args.input}
#
#  All 19 original fixes + 6 corrections + 2 surgical retries:
#    FIX-04 retry : GTX rejection fallback (was missing)
#    FIX-09 retry : -2022 / exchange-closed detection (was missing)
#    FIX-15b retry: robust trail snapshot bootstrap
# ════════════════════════════════════════════════════════════════════
"""
    if src.startswith("#!"):
        first_nl = src.index("\n")
        src_out = header + src[first_nl+1:]
    else:
        src_out = header + src

    try:
        compile(src_out, args.output, "exec")
        print(f"   ✅ compiles OK")
    except SyntaxError as e:
        print(f"   ❌ Syntax error at line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text}")
        sys.exit(2)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src_out)
    print(f"   💾 saved: {args.output} ({len(src_out):,} bytes)")

    # Final verdict
    n_missing = sum(1 for v in results.values() if not v)
    print(f"\n{'='*62}")
    if n_missing == 0 and sanity_ok:
        print(f"✅ SUCCESS — all fixes applied, structure intact")
        print(f"   Run: python {args.output} --mode testnet --api-key ... "
              f"--api-secret ...")
    else:
        print(f"⚠️  PARTIAL — {n_missing} fixes still missing")
        for tag, v in results.items():
            if not v:
                print(f"     - {tag}")
        if not sanity_ok:
            print(f"   ⚠️  Structural issue detected — review output")
        sys.exit(1)


if __name__ == "__main__":
    main()
