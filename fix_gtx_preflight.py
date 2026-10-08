#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_gtx_preflight.py  (v2)
==========================
FIX-25: GTX pre-flight check against order book.

الإصلاح في v2:
    - verify() يستخدم markers مرنة (لا تعتمد على وجود {sym} أو لا)
    - يطبع حالة الـ src أثناء الفشل (debug info)
    - يكتشف أنه إذا كانت كل العلامات موجودة إلا marker واحد مرن، يفشل تلقائياً
"""

import argparse
import os
import re
import sys
from datetime import datetime


def _once(src, old, new, tag, already_marker=None):
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
# HELPER BLOCK
# ════════════════════════════════════════════════════════════════

HELPER_BLOCK = '''# ════════════════════════════════════════════════════════════════
# [FIX-25] GTX pre-flight check
# ════════════════════════════════════════════════════════════════
#
# Prevents GTX rejections (-2010 / -5022) by adjusting the target
# BEFORE sending the order:
#   BUY : if target > best_bid  →  target = best_bid - tick
#   SELL: if target < best_ask  →  target = best_ask + tick
#
# Preserves maker-only execution (no slippage) and aligns with the
# mean-reversion strategy (BUY waits below market, SELL waits above).

_GTX_PREFLIGHT_ENABLED: bool = True
_GTX_PREFLIGHT_STATS: Dict = {
    "checked": 0,
    "adjusted": 0,
    "fetch_failed": 0,
    "last_report_ts": 0.0,
}


def _gtx_preflight(exchange, sym: str, side: str, target: float,
                    exchange_tick: Optional[float] = None) -> float:
    """[FIX-25] Adjust target so that GTX won't cross the book."""
    if not _GTX_PREFLIGHT_ENABLED:
        return target

    _GTX_PREFLIGHT_STATS["checked"] += 1

    tick = exchange_tick
    if tick is None or tick <= 0:
        try:
            tick = _get_tick_size(exchange, sym) or 0.0
        except Exception:
            tick = 0.0
    if tick <= 0:
        tick = max(target * 1e-6, 1e-8)

    try:
        ob = exchange.fetch_order_book(sym, limit=5)
        _rate_record(2.0)
    except Exception as e:
        _GTX_PREFLIGHT_STATS["fetch_failed"] += 1
        log.debug(f"[GTX-Preflight] {sym} book fetch failed: {e}")
        return target

    try:
        best_bid = float(ob["bids"][0][0])
        best_ask = float(ob["asks"][0][0])
    except (IndexError, ValueError, TypeError):
        return target

    if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
        return target

    if side == "buy":
        if target > best_bid:
            safe = best_bid - tick
            if safe <= 0:
                return target
            log.debug(
                f"[GTX-Preflight] {sym} BUY {target:.8f} \u2192 {safe:.8f} "
                f"(bid={best_bid:.8f}, tick={tick:.8f})"
            )
            _GTX_PREFLIGHT_STATS["adjusted"] += 1
            return float(safe)
    else:
        if target < best_ask:
            safe = best_ask + tick
            log.debug(
                f"[GTX-Preflight] {sym} SELL {target:.8f} \u2192 {safe:.8f} "
                f"(ask={best_ask:.8f}, tick={tick:.8f})"
            )
            _GTX_PREFLIGHT_STATS["adjusted"] += 1
            return float(safe)

    return target


def _gtx_preflight_log_stats() -> None:
    """Log pre-flight stats every 5 minutes."""
    now = time.time()
    if now - float(_GTX_PREFLIGHT_STATS.get("last_report_ts", 0.0)) < 300:
        return
    _GTX_PREFLIGHT_STATS["last_report_ts"] = now
    s = _GTX_PREFLIGHT_STATS
    if s["checked"] == 0:
        return
    log.info(
        f"[GTX-Preflight] checked={s['checked']}, "
        f"adjusted={s['adjusted']}, "
        f"fetch_failed={s['fetch_failed']}"
    )


# ══ end FIX-25 helpers ══


'''


# ════════════════════════════════════════════════════════════════
# Edit 1
# ════════════════════════════════════════════════════════════════

def edit1_add_helpers(src):
    print("\n▶ Edit 1: insert GTX-preflight helpers")
    anchor = "def place_pending_entry(exchange, sym: str, side: str, qty: float,"
    if anchor not in src:
        print("   ❌ anchor 'def place_pending_entry' not found")
        return src, False
    if "[FIX-25] GTX pre-flight check" in src:
        print("   ℹ️  already applied")
        return src, True
    src = src.replace(anchor, HELPER_BLOCK + anchor, 1)
    print("   ✅ helper block inserted")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 2 — GTX block replacement
# ════════════════════════════════════════════════════════════════

OLD_GTX = '''    # ══ وضع الأمر النهائي ══
    if _exec_mode == "gtx":
        try:
            o = exchange.create_order(
                sym, 'limit', side, qty, target,
                params={'timeInForce': 'GTX'}
            )
        except Exception as e:
            _emsg = str(e).lower()
            # [FIX-4.1] عند رفض GTX (post-only would cross):
            # انزلق بعيداً عن السوق بمقدار 1 tick إضافي ثم أعد المحاولة.
            if '-2010' in _emsg or 'post only' in _emsg or 'gtx' in _emsg:
                log.info(f"[Pending] {sym} GTX rejected — "
                         f"falling back with wider offset")
                try:
                    _tick = _get_tick_size(exchange, sym) or target * 1e-5
                    if side == 'buy':
                        target2 = target - _tick
                    else:
                        target2 = target + _tick
                    o = exchange.create_order(
                        sym, 'limit', side, qty, target2,
                        params={'timeInForce': 'GTX'}
                    )
                    target = target2  # للـ rec
                except Exception as e2:
                    log.warning(f"[Pending] {sym} GTX fallback failed: {e2}")
                    return None
            else:
                log.debug(f"[Pending] {sym} order rejected @ "
                          f"{target:.6f}: {e}")
                return None'''

NEW_GTX = '''    # ══ وضع الأمر النهائي ══
    if _exec_mode == "gtx":
        # ══ [FIX-25] Pre-flight: adjust to safe side BEFORE sending ══
        _tick_for_gtx = _get_tick_size(exchange, sym) or 0.0
        _orig_target = target
        target = _gtx_preflight(exchange, sym, side, target,
                                  exchange_tick=_tick_for_gtx)
        if target != _orig_target:
            log.debug(
                f"[FIX-25] {sym} GTX target adjusted "
                f"{_orig_target:.8f} \u2192 {target:.8f}"
            )

        try:
            o = exchange.create_order(
                sym, 'limit', side, qty, target,
                params={'timeInForce': 'GTX'}
            )
        except Exception as e:
            _emsg = str(e).lower()
            # [FIX-25] GTX rejected even after pre-flight.
            # Fetch book freshly and retry with the actual safe price.
            if ('-2010' in _emsg or '-5022' in _emsg
                    or 'post only' in _emsg or 'gtx' in _emsg):
                log.info(
                    f"[FIX-25] {sym} GTX rejected after pre-flight "
                    f"- fetching fresh book"
                )
                try:
                    _ob2 = exchange.fetch_order_book(sym, limit=5)
                    _rate_record(2.0)
                    _bb2 = float(_ob2['bids'][0][0])
                    _ba2 = float(_ob2['asks'][0][0])
                    _tick2 = _tick_for_gtx or target * 1e-5
                    if side == 'buy':
                        target2 = _bb2 - _tick2
                    else:
                        target2 = _ba2 + _tick2
                    log.info(
                        f"[FIX-25] {sym} retry target "
                        f"{target:.8f} \u2192 {target2:.8f} "
                        f"(bid={_bb2:.8f}, ask={_ba2:.8f})"
                    )
                    o = exchange.create_order(
                        sym, 'limit', side, qty, target2,
                        params={'timeInForce': 'GTX'}
                    )
                    target = target2
                except Exception as e2:
                    log.warning(
                        f"[Pending] {sym} GTX fallback failed: {e2}"
                    )
                    return None
            else:
                log.debug(f"[Pending] {sym} order rejected @ "
                          f"{target:.6f}: {e}")
                return None'''


def edit2_modify_gtx_block(src):
    print("\n▶ Edit 2: add GTX pre-flight + improved fallback")
    if "[FIX-25] Pre-flight" in src:
        print("   ℹ️  already applied")
        return src, True
    if OLD_GTX not in src:
        print("   ❌ GTX block not found")
        idx = src.find("وضع الأمر النهائي")
        if idx >= 0:
            print(f"      context: {src[max(0,idx-100):idx+500]!r}")
        return src, False
    src = src.replace(OLD_GTX, NEW_GTX, 1)
    print("   ✅ GTX block updated")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 3
# ════════════════════════════════════════════════════════════════

def edit3_stats_logger(src):
    print("\n▶ Edit 3: wire stats logger into main loop")
    if "_gtx_preflight_log_stats()" in src:
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
        "            # [FIX-25] GTX pre-flight stats\n"
        "            _gtx_preflight_log_stats()"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ stats logger wired")
    return src, True


# ════════════════════════════════════════════════════════════════
# VERIFY — FLEXIBLE MARKERS (v2)
# ════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # Flexible markers: any one of the alternatives passes
    checks = [
        ("FIX-25 helpers", [
            "[FIX-25] GTX pre-flight check",
        ]),
        ("_GTX_PREFLIGHT_ENABLED", [
            "_GTX_PREFLIGHT_ENABLED: bool = True",
        ]),
        ("_GTX_PREFLIGHT_STATS", [
            "_GTX_PREFLIGHT_STATS: Dict = {",
        ]),
        ("_gtx_preflight function", [
            "def _gtx_preflight(",
        ]),
        ("_gtx_preflight_log_stats", [
            "def _gtx_preflight_log_stats(",
        ]),
        ("pre-flight call", [
            "[FIX-25] Pre-flight",
        ]),
        ("improved fallback", [
            "[FIX-25] {sym} retry target",   # actual code marker
            "[FIX-25] retry",                 # alt
            "GTX rejected after pre-flight",  # alt 2
        ]),
        ("-5022 detection", [
            "'-5022' in _emsg",
        ]),
        ("stats logger call", [
            "_gtx_preflight_log_stats()",
        ]),
    ]

    all_ok = True
    for label, alternatives in checks:
        # Pass if ANY alternative is present
        found = None
        for alt in alternatives:
            if alt in src:
                found = alt
                break
        ok = found is not None
        print(f"   {'✅' if ok else '❌'} {label}")
        if ok and found != alternatives[0]:
            print(f"      (matched alt: {found!r})")
        if not ok:
            print(f"      tried: {alternatives}")
        if not ok:
            all_ok = False

    # Sanity checks
    print("\n   Sanity:")
    for label, marker, want in [
        ("place_pending_entry", "def place_pending_entry(", True),
        ("run_live", "def run_live(", True),
        ("old FIX-4.1 comment removed",
         "انزلق بعيداً عن السوق بمقدار 1 tick", False),
    ]:
        present = marker in src
        ok = (present == want)
        print(f"   {'✅' if ok else '❌'} {label}")
        if not ok:
            all_ok = False
    return all_ok


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_complete3.py")
    ap.add_argument("--output", default="trading_2_complete4.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} bytes)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-25: GTX pre-flight check (v2)                          ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: helpers block",       edit1_add_helpers),
        ("Edit 2: GTX block update",    edit2_modify_gtx_block),
        ("Edit 3: stats logger",        edit3_stats_logger),
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
        print(f"   ❌ SyntaxError at line {e.lineno}: {e.msg}")
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

        # ═══ DEBUG: dump snippet of the modified area ═══
        print("\n╔══════════════════════════════════════════════════════════════╗")
        print("║  DEBUG: GTX block in modified src                          ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        idx = src.find("# ══ وضع الأمر النهائي ══")
        if idx >= 0:
            end = min(len(src), idx + 2500)
            print(src[idx:end])
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine\n"
        "#  GTX-Safe Build — FIX-25 (v2)\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "# ═══════════════════════════════════════════════════════\n"
    )

    if src.startswith("#!"):
        first_nl = src.index("\n")
        src_out = header + src[first_nl + 1:]
    else:
        src_out = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src_out)

    # Re-verify written file
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
    print(f"   Input:  {args.input}  ({len(src):,} bytes)")
    print(f"   Output: {args.output}  ({len(src_out):,} bytes)")
    for label, ok in results:
        print(f"   {'✅' if ok else '❌'} {label}")
    print(f"   verify:  {'✅ ALL PASSED' if all_ok else '❌ FAILED'}")
    print(f"   written: {'✅ OK' if write_ok else '❌ FAILED'}")

    if not write_ok:
        sys.exit(3)


if __name__ == "__main__":
    main()
