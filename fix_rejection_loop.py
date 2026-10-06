#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_rejection_loop.py  (v2)
===========================
FIX-23: حلقة الرفض اللانهائية + بوابة drift اتجاهية.

التغيير في v2:
    Edit 3 يستخدم regex مرن للـ indentation بدل نمط ثابت.
    لم نغيّر أي إصلاح آخر.

التشغيل:
    python fix_rejection_loop.py \
        --input  trading_2_complete.py \
        --output trading_2_rejection_fixed.py
"""

import argparse
import os
import re
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# Helper block
# ════════════════════════════════════════════════════════════════

HELPER_BLOCK = '''# ════════════════════════════════════════════════════════════════
# [FIX-23] Rejection memoization — prevents infinite re-processing
# ════════════════════════════════════════════════════════════════
#
# Problem:
#   When place_pending_entry() rejects a signal, nothing stores
#   the fact that it was rejected. The next cycle regenerates the
#   same signal (same close_idx) and tries again — forever.
#
# Solution:
#   _REJECTED_SIGNALS[(sym, close_idx)] = (reason, ts)
#   Skip any signal whose key is in the cache.
#   Auto-evict entries older than REJECTION_TTL_S (default 15 min).

_REJECTED_SIGNALS: Dict = {}
_REJECTION_TTL_S: float = 900.0
_REJECTION_STATS: Dict = {
    "rejected": 0,
    "skipped_due_to_cache": 0,
    "evicted": 0,
}


def _rejection_key(sym: str, close_idx: int) -> tuple:
    return (str(sym), int(close_idx))


def _mark_rejected(sym: str, close_idx: int, reason: str) -> None:
    """Record a rejected signal so we don't retry it."""
    _REJECTED_SIGNALS[_rejection_key(sym, close_idx)] = (
        str(reason)[:120], time.time()
    )
    _REJECTION_STATS["rejected"] += 1


def _is_rejected(sym: str, close_idx: int) -> bool:
    """True if this (sym, close_idx) was already rejected."""
    key = _rejection_key(sym, close_idx)
    rec = _REJECTED_SIGNALS.get(key)
    if rec is None:
        return False
    reason, ts = rec
    if time.time() - ts > _REJECTION_TTL_S:
        _REJECTED_SIGNALS.pop(key, None)
        _REJECTION_STATS["evicted"] += 1
        return False
    _REJECTION_STATS["skipped_due_to_cache"] += 1
    return True


def _rejection_cache_prune() -> int:
    """Prune stale entries. Called from the main loop periodically."""
    now = time.time()
    removed = 0
    for k in list(_REJECTED_SIGNALS.keys()):
        _, ts = _REJECTED_SIGNALS[k]
        if now - ts > _REJECTION_TTL_S:
            _REJECTED_SIGNALS.pop(k, None)
            removed += 1
    _REJECTION_STATS["evicted"] += removed
    return removed


def _rejection_log_stats() -> None:
    """Log rejection-cache stats every 5 min."""
    if not hasattr(_rejection_log_stats, "_last"):
        _rejection_log_stats._last = 0.0
    now = time.time()
    if now - _rejection_log_stats._last < 300:
        return
    _rejection_log_stats._last = now
    s = _REJECTION_STATS
    total = s["rejected"]
    if total == 0:
        return
    log.info(f"[RejectionCache] rejected={s['rejected']}, "
             f"skipped={s['skipped_due_to_cache']}, "
             f"evicted={s['evicted']}, "
             f"active={len(_REJECTED_SIGNALS)}")


# ══ end FIX-23 helpers ══


'''


def _once_exact(src, old, new, tag, already_marker=None):
    if already_marker and already_marker in src:
        print(f"   ℹ️  [{tag}] already applied")
        return src, True
    if old not in src:
        print(f"   ❌ [{tag}] anchor NOT found")
        return src, False
    n = src.count(old)
    if n > 1:
        print(f"   ⚠️  [{tag}] anchor appears {n}× — replacing first")
    return src.replace(old, new, 1), True


# ════════════════════════════════════════════════════════════════
# Edit 1: helpers
# ════════════════════════════════════════════════════════════════

def edit1_add_helpers(src):
    print("\n▶ Edit 1: add rejection-cache helpers")
    anchor = "def load_symbol_meta(mode: str) -> Dict[str, Dict]:"
    if anchor not in src:
        print("   ❌ anchor 'def load_symbol_meta' not found")
        return src, False
    if "[FIX-23] Rejection memoization" in src:
        print("   ℹ️  already applied")
        return src, True
    src = src.replace(anchor, HELPER_BLOCK + anchor, 1)
    print("   ✅ helper block inserted")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 2: Config
# ════════════════════════════════════════════════════════════════

def edit2_config(src):
    print("\n▶ Edit 2: add MAX_TUNNEL_DISTANCE_BPS config")
    if "MAX_TUNNEL_DISTANCE_BPS" in src:
        print("   ℹ️  already present")
        return src, True
    anchor = "    PO_MAX_DRIFT_BPS: float = 5.0"
    if anchor not in src:
        print("   ❌ PO_MAX_DRIFT_BPS anchor not found")
        return src, False
    new = (
        "    PO_MAX_DRIFT_BPS: float = 5.0\n"
        "    # [FIX-23] Absolute cap on how far the tunnel may sit\n"
        "    # from current mid, in bps. Direction is enforced\n"
        "    # separately (BUY target must be BELOW mid, SELL ABOVE).\n"
        "    MAX_TUNNEL_DISTANCE_BPS: float = 1000.0"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ config field added")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 3 (v2): direction-aware drift gate via regex
# ════════════════════════════════════════════════════════════════

def edit3_drift_gate(src):
    print("\n▶ Edit 3: direction-aware drift gate (regex)")

    if "# [FIX-23] Direction-aware drift gate" in src:
        print("   ℹ️  already applied")
        return src, True

    # Match the entire sanity gate block with flexible indentation.
    # Any Unicode dash variant is accepted for the "(> X bps) — skip"
    # line, and the inner indentation is captured via backreference.
    dash = r'[\u2010\u2011\u2012\u2013\u2014\u2015\-]'
    pattern = re.compile(
        r'(?P<I>[ \t]+)# Sanity gate\n'
        r'(?P=I)try:\n'
        r'(?P=I)    ob = exchange\.fetch_order_book\(sym, limit=5\)\n'
        r'(?P=I)    _mid = \(float\(ob\[\'bids\'\]\[0\]\[0\]\)\n'
        r'(?P=I)            \+ float\(ob\[\'asks\'\]\[0\]\[0\]\)\) '
        r'/ 2\.0\n'
        r'(?P=I)    if _mid > 0:\n'
        r'(?P=I)        _gap_bps = abs\(target - _mid\) / _mid \* 1e4\n'
        r'(?P=I)        _max_gap = float\(\n'
        r'(?P=I)            getattr\(CFG, \'PO_MAX_DRIFT_BPS\', 5\.0\)\n'
        r'(?P=I)        \) \* 4\.0\n'
        r'(?P=I)        if _gap_bps > _max_gap:\n'
        r'(?P=I)            log\.info\(\n'
        r'(?P=I)                f"\[Pending\] \{sym\} target '
        r'\{target:\.6f\} "\n'
        r'(?P=I)                f"is \{_gap_bps:\.1f\}bps from mid "\n'
        r'(?P=I)                f"\(> \{_max_gap:\.1f\}\) ' + dash +
        r' skip"\n'
        r'(?P=I)            \)\n'
        r'(?P=I)            return None\n'
        r'(?P=I)except Exception:\n'
        r'(?P=I)    pass'
    )

    m = pattern.search(src)
    if not m:
        print("   ❌ sanity gate pattern not found")
        idx = src.find("# Sanity gate")
        if idx > 0:
            print(f"      context: {src[max(0,idx-200):idx+400]!r}")
        return src, False

    I = m.group('I')
    new_block = (
        f'{I}# [FIX-23] Direction-aware drift gate\n'
        f'{I}# Reject only if tunnel is on WRONG side of mid OR\n'
        f'{I}# absurdly far (> MAX_TUNNEL_DISTANCE_BPS).\n'
        f'{I}try:\n'
        f'{I}    ob = exchange.fetch_order_book(sym, limit=5)\n'
        f'{I}    _mid = (float(ob[\'bids\'][0][0])\n'
        f'{I}            + float(ob[\'asks\'][0][0])) / 2.0\n'
        f'{I}    if _mid > 0:\n'
        f'{I}        _signed_bps = (target - _mid) / _mid * 1e4\n'
        f'{I}        _max_far = float(getattr(\n'
        f'{I}            CFG, \'MAX_TUNNEL_DISTANCE_BPS\', 1000.0))\n'
        f'{I}        _bad_side = (\n'
        f'{I}            (side == \'buy\' and _signed_bps > 0) or\n'
        f'{I}            (side == \'sell\' and _signed_bps < 0)\n'
        f'{I}        )\n'
        f'{I}        _too_far = abs(_signed_bps) > _max_far\n'
        f'{I}        if _bad_side or _too_far:\n'
        f'{I}            _reason = (\'wrong_side\' if _bad_side\n'
        f'{I}                       else \'too_far\')\n'
        f'{I}            log.debug(\n'
        f'{I}                f"[Pending] {{sym}} target {{target:.6f}} "\n'
        f'{I}                f"signed={{_signed_bps:+.1f}}bps from mid "\n'
        f'{I}                f"({{_reason}}, max={{_max_far:.0f}}bps) "\n'
        f'{I}                f"\u2014 skip"\n'
        f'{I}            )\n'
        f'{I}            return None\n'
        f'{I}except Exception:\n'
        f'{I}    pass'
    )

    src = src[:m.start()] + new_block + src[m.end():]
    print(f"   ✅ gate replaced (detected indent = {len(I)} spaces)")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 4: skip rejected
# ════════════════════════════════════════════════════════════════

def edit4_skip_rejected(src):
    print("\n▶ Edit 4: skip already-rejected signals")
    if "_is_rejected(sym, int(sig.close_idx))" in src:
        print("   ℹ️  already applied")
        return src, True
    anchor = (
        "                    if sym in _WATCHED_SIGNALS:\n"
        "                        log.debug(f\"[Watch] {sym} already watched "
        "— skip\")\n"
        "                        continue"
    )
    if anchor not in src:
        print("   ❌ watch-skip anchor not found")
        return src, False
    new = (
        "                    if sym in _WATCHED_SIGNALS:\n"
        "                        log.debug(f\"[Watch] {sym} already watched "
        "— skip\")\n"
        "                        continue\n"
        "                    # [FIX-23] skip signals already rejected "
        "for this bar\n"
        "                    if _is_rejected(sym, int(sig.close_idx)):\n"
        "                        log.debug(\n"
        "                            f\"[RejectedCache] {sym} \"\n"
        "                            f\"close_idx={sig.close_idx} — skip\"\n"
        "                        )\n"
        "                        continue"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ skip check inserted")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 5: mark rejections
# ════════════════════════════════════════════════════════════════

def edit5_mark_rejections(src):
    print("\n▶ Edit 5: mark rejections at place_pending_entry caller")
    if "'place_pending_rejected'" in src:
        print("   ℹ️  already applied")
        return src, True
    old = (
        "                            rec = place_pending_entry(\n"
        "                                exchange, sym, sd, qty, sig,\n"
        "                                timeout_s=_timeout_s,\n"
        "                                leverage=int(dynamic_leverage),\n"
        "                                ad=assets[sym],\n"
        "                            )\n"
        "                            if rec is None:\n"
        "                                log.info(f\"[Pending] {sym} "
        "rejected — skip\")\n"
        "                                continue"
    )
    if old not in src:
        print("   ❌ place_pending_entry call not found")
        return src, False
    new = (
        "                            rec = place_pending_entry(\n"
        "                                exchange, sym, sd, qty, sig,\n"
        "                                timeout_s=_timeout_s,\n"
        "                                leverage=int(dynamic_leverage),\n"
        "                                ad=assets[sym],\n"
        "                            )\n"
        "                            if rec is None:\n"
        "                                # [FIX-23] memoize so we "
        "don't retry this bar\n"
        "                                _mark_rejected(\n"
        "                                    sym, int(sig.close_idx),\n"
        "                                    'place_pending_rejected'\n"
        "                                )\n"
        "                                log.debug(\n"
        "                                    f\"[Pending] {sym} rejected "
        "— memoized\"\n"
        "                                )\n"
        "                                continue"
    )
    src = src.replace(old, new, 1)
    print("   ✅ rejection marking inserted")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 6: quiet SL-Clip
# ════════════════════════════════════════════════════════════════

def edit6_quiet_sl_clip(src):
    print("\n▶ Edit 6: reduce SL-Clip-Live log level")
    if "# [FIX-23] log at DEBUG" in src:
        print("   ℹ️  already applied")
        return src, True
    # Regex-based: find the log.info( call that contains SL-Clip-Live
    pattern = re.compile(
        r'(?P<I>[ ]+)log\.info\(\n'
        r'(?P=I)    f"\[SL-Clip-Live\] \{sym\} SL clipped "\n'
        r'(?P=I)    f"\{_sl_dist_now:\.6f\} \u2192 \{_new_sl_dist:\.6f\} "\n'
        r'(?P=I)    f"\(\{_max_sl_frac_live\*100:\.1f\}% cap\)"\n'
        r'(?P=I)\)'
    )
    m = pattern.search(src)
    if m:
        I = m.group('I')
        new_block = (
            f'{I}# [FIX-23] log at DEBUG to avoid spam\n'
            f'{I}log.debug(\n'
            f'{I}    f"[SL-Clip-Live] {{sym}} SL clipped "\n'
            f'{I}    f"{{_sl_dist_now:.6f}} \u2192 '
            f'{{_new_sl_dist:.6f}} "\n'
            f'{I}    f"({{_max_sl_frac_live*100:.1f}}% cap)"\n'
            f'{I})'
        )
        src = src[:m.start()] + new_block + src[m.end():]
        print("   ✅ SL-Clip now DEBUG (regex)")
        return src, True

    # Fallback: exact string
    old = (
        "                            log.info(\n"
        "                                f\"[SL-Clip-Live] {sym} SL clipped \"\n"
        "                                f\"{_sl_dist_now:.6f} \u2192 "
        "{_new_sl_dist:.6f} \"\n"
        "                                f\"({_max_sl_frac_live*100:.1f}% "
        "cap)\"\n"
        "                            )"
    )
    if old in src:
        new = (
            "                            # [FIX-23] log at DEBUG to avoid spam\n"
            "                            log.debug(\n"
            "                                f\"[SL-Clip-Live] {sym} SL clipped \"\n"
            "                                f\"{_sl_dist_now:.6f} \u2192 "
            "{_new_sl_dist:.6f} \"\n"
            "                                f\"({_max_sl_frac_live*100:.1f}% "
            "cap)\"\n"
            "                            )"
        )
        src = src.replace(old, new, 1)
        print("   ✅ SL-Clip now DEBUG (exact)")
        return src, True

    print("   ❌ SL-Clip anchor not found (both regex and exact)")
    idx = src.find("[SL-Clip-Live]")
    if idx > 0:
        print(f"      context: {src[max(0,idx-250):idx+250]!r}")
    return src, False


# ════════════════════════════════════════════════════════════════
# Edit 7: main loop
# ════════════════════════════════════════════════════════════════

def edit7_main_loop(src):
    print("\n▶ Edit 7: prune + stats in main loop")
    if "_rejection_cache_prune()" in src and "_rejection_log_stats()" in src:
        print("   ℹ️  already applied")
        return src, True
    anchor = (
        "            # [FIX-09-PROPER] periodic pos-cache stats\n"
        "            _pos_cache_log_stats()"
    )
    if anchor not in src:
        print("   ❌ pos-cache stats anchor not found")
        return src, False
    new = (
        "            # [FIX-09-PROPER] periodic pos-cache stats\n"
        "            _pos_cache_log_stats()\n"
        "            # [FIX-23] prune + log rejection cache\n"
        "            _rejection_cache_prune()\n"
        "            _rejection_log_stats()"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ main loop updated")
    return src, True


# ════════════════════════════════════════════════════════════════
# VERIFY
# ════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = [
        ("FIX-23 helpers",           "[FIX-23] Rejection memoization"),
        ("_REJECTED_SIGNALS",         "_REJECTED_SIGNALS: Dict = {}"),
        ("_mark_rejected",            "def _mark_rejected("),
        ("_is_rejected",              "def _is_rejected("),
        ("_rejection_cache_prune",    "def _rejection_cache_prune("),
        ("MAX_TUNNEL_DISTANCE_BPS",   "MAX_TUNNEL_DISTANCE_BPS: float = 1000.0"),
        ("direction-aware gate",      "[FIX-23] Direction-aware drift gate"),
        ("bad_side logic",            "_bad_side = ("),
        ("skip rejected in loop",     "_is_rejected(sym, int(sig.close_idx))"),
        ("mark rejection on None",    "'place_pending_rejected'"),
        ("SL-Clip at DEBUG",          "# [FIX-23] log at DEBUG"),
        ("cache prune in loop",       "_rejection_cache_prune()"),
    ]
    all_ok = True
    for label, marker in checks:
        ok = marker in src
        print(f"   {'✅' if ok else '❌'} {label}")
        if not ok:
            all_ok = False
    # Inverse: no more INFO for the drift-gate reject
    n_info = src.count("is {_gap_bps:.1f}bps from mid ")
    print(f"\n   leftover INFO drift-gate: {n_info} (should be 0)")
    if n_info > 0:
        all_ok = False
    return all_ok


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_complete.py")
    ap.add_argument("--output", default="trading_2_rejection_fixed.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} bytes)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-23 (v2): rejection loop + drift gate + log spam        ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: helpers block",        edit1_add_helpers),
        ("Edit 2: MAX_TUNNEL config",    edit2_config),
        ("Edit 3: direction-aware gate", edit3_drift_gate),
        ("Edit 4: skip rejected",        edit4_skip_rejected),
        ("Edit 5: mark rejections",      edit5_mark_rejections),
        ("Edit 6: quiet SL-Clip",        edit6_quiet_sl_clip),
        ("Edit 7: prune in main loop",   edit7_main_loop),
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
    try:
        compile(src, args.output, "exec")
        print("   ✅ compiles OK")
        syntax_ok = True
    except SyntaxError as e:
        print(f"   ❌ SyntaxError line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text!r}")
        syntax_ok = False

    if not (all_ok and syntax_ok):
        print(f"\n╔══════════════════════════════════════════════════════════════╗")
        print(f"║  ❌ ABORTED                                                 ║")
        print(f"╚══════════════════════════════════════════════════════════════╝")
        for label, ok in results:
            print(f"   {'✅' if ok else '❌'} {label}")
        print(f"   verify:  {'OK' if all_ok else 'FAILED'}")
        print(f"   syntax:  {'OK' if syntax_ok else 'FAILED'}")
        print(f"\n   Output NOT written. Input unchanged.")
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine\n"
        "#  Rejection-Loop Fix Build — FIX-23\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  FIX-23 adds:\n"
        "#    • _REJECTED_SIGNALS cache — stops infinite re-processing\n"
        "#    • Direction-aware drift gate (BUY below mid, SELL above)\n"
        "#    • MAX_TUNNEL_DISTANCE_BPS = 1000 (physical cap)\n"
        "#    • SL-Clip-Live → DEBUG (was INFO)\n"
        "#    • Rejection stats every 5 min\n"
        "# ═══════════════════════════════════════════════════════\n"
    )
    if src.startswith("#!"):
        first_nl = src.index("\n")
        src_out = header + src[first_nl + 1:]
    else:
        src_out = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src_out)

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                             DONE                             ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"   Input:  {args.input}  ({len(src):,} bytes)")
    print(f"   Output: {args.output}  ({len(src_out):,} bytes)")
    for label, ok in results:
        print(f"   {'✅' if ok else '❌'} {label}")
    print(f"   verify:  {'✅ ALL PASSED' if all_ok else '❌ FAILED'}")
    print(f"   written: ✅ OK")


if __name__ == "__main__":
    main()
