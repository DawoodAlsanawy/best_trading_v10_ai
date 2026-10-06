#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_orphan_protective.py  (v2)
==============================
FIX-24: تنظيف الأوامر الواقية اليتيمة بعد إغلاق الصفقة.

يستهدف trading_2_complete.py — يستخدم anchors مطابقة للكود الفعلي.
لا regex معقد: فقط backreferences لاكتشاف indentation.

الاستخدام:
    python fix_orphan_protective.py \
        --input  trading_2_complete.py \
        --output trading_2_orphan_fixed.py
"""

import argparse
import os
import re
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

def _indent_block(text: str, indent: str) -> str:
    """Prepend `indent` to every non-empty line of `text`."""
    out = []
    for ln in text.split("\n"):
        if ln.strip():
            out.append(indent + ln)
        else:
            out.append("")
    return "\n".join(out)


def _ok(label: str, applied: bool):
    print(f"   {'✅' if applied else '❌'} {label}")


# ════════════════════════════════════════════════════════════════
# HELPER BLOCK (indent applied at insertion time)
# ════════════════════════════════════════════════════════════════

HELPER_BLOCK_BODY = '''# ════════════════════════════════════════════════════════════════
# [FIX-24] Orphan protective-order cleanup
# ════════════════════════════════════════════════════════════════
#
# Problem
# -------
# When a position closes (SL hit, TP hit, bot exit, or manual),
# protective orders (STOP_MARKET / TAKE_PROFIT_MARKET) can remain
# open on the exchange as orphans. Root causes:
#   - Binance closePosition auto-cancel is not always reliable
#   - partial-fill races between SL / partial-TP / full-TP
#   - exchange hiccups during the exit
#   - cancel_order failures that the bot never retries
#
# Effect
# ------
# An orphan TP later fires on a fresh position, OR trips -2022
# repeatedly. Either way, the position becomes unmanaged.
#
# Solution
# --------
# Global sweep every _ORPHAN_SWEEP_INTERVAL_S seconds.
# One call to fetch_open_orders() returns ALL open orders
# (Binance USDT-M: weight=40).
# Cancel any protective order whose symbol has no open position
# AND no pending order.

_ORPHAN_SWEEP_INTERVAL_S: float = 60.0
_ORPHAN_SWEEP_ENABLED: bool = True
_ORPHAN_SWEEP_STATS: Dict = {
    "sweeps": 0,
    "orphans_found": 0,
    "orphans_cancelled": 0,
    "errors": 0,
    "last_sweep_ts": 0.0,
    "last_report_ts": 0.0,
}


def _orphan_protective_sweep(exchange,
                              open_pos_live: Dict,
                              pending_orders=None) -> int:
    """
    [FIX-24] Cancel protective orders for symbols without a live
    position or pending order. Returns number cancelled.
    """
    if not _ORPHAN_SWEEP_ENABLED:
        return 0
    now = time.time()
    if now - float(_ORPHAN_SWEEP_STATS.get("last_sweep_ts", 0.0)) \\
            < _ORPHAN_SWEEP_INTERVAL_S:
        return 0
    _ORPHAN_SWEEP_STATS["last_sweep_ts"] = now
    _ORPHAN_SWEEP_STATS["sweeps"] += 1

    try:
        all_orders = exchange.fetch_open_orders()
    except Exception as e:
        _ORPHAN_SWEEP_STATS["errors"] += 1
        log.debug(f"[Orphan] fetch_open_orders failed: {e}")
        return 0

    if not all_orders:
        return 0

    # Build whitelist of symbols that legitimately need protection
    symbols_ok = set()
    for sym in (open_pos_live or {}):
        symbols_ok.add(sym)
        if ":" not in sym:
            symbols_ok.add(sym + ":USDT")
    if pending_orders:
        for sym in pending_orders:
            symbols_ok.add(sym)
            if ":" not in sym:
                symbols_ok.add(sym + ":USDT")

    n_cancelled = 0
    for o in all_orders:
        try:
            if not _is_protective_order(o):
                continue
            sym = o.get("symbol") or ""
            sym_norm = sym.split(":")[0] if ":" in sym else sym
            if sym in symbols_ok or sym_norm in symbols_ok:
                continue

            _ORPHAN_SWEEP_STATS["orphans_found"] += 1
            log.warning(
                f"[Orphan] {sym_norm} protective order "
                f"oid={o.get('id')} type={o.get('type')} "
                f"trigger={o.get('stopPrice') or o.get('price')} "
                f"- CANCELLING"
            )
            try:
                exchange.cancel_order(o["id"], sym)
                n_cancelled += 1
                _ORPHAN_SWEEP_STATS["orphans_cancelled"] += 1
            except Exception as _e:
                log.debug(f"[Orphan] cancel {sym_norm} failed: {_e}")
        except Exception as _e:
            _ORPHAN_SWEEP_STATS["errors"] += 1
            log.debug(f"[Orphan] processing failed: {_e}")

    if n_cancelled > 0:
        try:
            _invalidate_position_cache()
        except Exception:
            pass
    return n_cancelled


def _orphan_log_stats() -> None:
    """Log orphan sweep stats every 5 minutes."""
    now = time.time()
    if now - float(_ORPHAN_SWEEP_STATS.get("last_report_ts", 0.0)) < 300:
        return
    _ORPHAN_SWEEP_STATS["last_report_ts"] = now
    s = _ORPHAN_SWEEP_STATS
    if s["sweeps"] == 0:
        return
    log.info(f"[Orphan] sweeps={s['sweeps']}, "
             f"found={s['orphans_found']}, "
             f"cancelled={s['orphans_cancelled']}, "
             f"errors={s['errors']}")


# ══ end FIX-24 helpers ══


'''


# ════════════════════════════════════════════════════════════════
# Edit 1 — insert helper block before load_symbol_meta
# ════════════════════════════════════════════════════════════════

def edit1_add_helpers(src):
    print("\n▶ Edit 1: insert orphan-sweep helpers")
    anchor = "def load_symbol_meta(mode: str) -> Dict[str, Dict]:"
    if anchor not in src:
        print("   ❌ anchor 'def load_symbol_meta' not found")
        return src, False
    if "[FIX-24] Orphan protective-order cleanup" in src:
        print("   ℹ️  already applied")
        return src, True
    src = src.replace(anchor, HELPER_BLOCK_BODY + anchor, 1)
    _ok("helper block inserted", True)
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 2 — add post-cancel verification to _cancel_all_protective_orders
# ════════════════════════════════════════════════════════════════

# Target text (exact from trading_2_complete.py):
#         import time as _t
#         _t.sleep(0.3)
#     return n
# (import at 8 spaces, return at 4 spaces)

def edit2_post_cancel_verify(src):
    print("\n▶ Edit 2: add post-cancel verification")
    if "[FIX-24] post-cancel verification" in src:
        print("   ℹ️  already applied")
        return src, True

    pat = re.compile(
        r"(?P<I1>[ ]+)import time as _t\n"
        r"(?P=I1)_t\.sleep\(0\.3\)\n"
        r"(?P<I2>[ ]+)return n\b"
    )
    m = pat.search(src)
    if not m:
        print("   ❌ anchor not found")
        idx = src.find("import time as _t")
        if idx >= 0:
            print(f"      context: {src[max(0,idx-200):idx+300]!r}")
        return src, False

    I2 = m.group("I2")   # indent of `return n` (function body level, 4)

    body = (
        "# [FIX-24] post-cancel verification\n"
        "try:\n"
        "    _final_check = [\n"
        "        o for o in exchange.fetch_open_orders(sym)\n"
        "        if _is_protective_order(o)\n"
        "    ]\n"
        "    if _final_check:\n"
        "        log.warning(\n"
        "            f\"[Prot] {sym} {len(_final_check)} protective \"\n"
        "            f\"order(s) survived cancel \"\n"
        "            f\"- orphan sweep will retry\"\n"
        "        )\n"
        "except Exception:\n"
        "    pass\n"
        "return n"
    )

    replacement = _indent_block(body, I2)
    src = src[:m.start()] + replacement + src[m.end():]
    _ok("post-cancel verification inserted", True)
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 3 — wire sweep into main loop
# ════════════════════════════════════════════════════════════════

def edit3_main_loop(src):
    print("\n▶ Edit 3: wire sweep into main loop")
    if "[FIX-24] orphan protective sweep" in src:
        print("   ℹ️  already applied")
        return src, True

    # Anchor: the two lines after the rate report
    old = (
        "            # ══ [RateLimit] periodic report ══\n"
        "            _rate_report()\n"
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()"
    )

    if old not in src:
        print("   ❌ main-loop anchor not found")
        idx = src.find("_pos_cache_log_stats()")
        if idx >= 0:
            print(f"      context: {src[max(0,idx-250):idx+150]!r}")
        return src, False

    I = " " * 12   # 12-space indent for the loop body
    body = (
        "# ══ [RateLimit] periodic report ══\n"
        "_rate_report()\n"
        "# [FIX-09-PROPER] pos-cache stats\n"
        "_pos_cache_log_stats()\n"
        "# [FIX-24] orphan protective sweep\n"
        "try:\n"
        "    _orphan_protective_sweep(\n"
        "        exchange, open_pos_live, _PENDING_ORDERS\n"
        "    )\n"
        "    _orphan_log_stats()\n"
        "except Exception as _e:\n"
        "    log.debug(f\"[Orphan] sweep error: {_e}\")"
    )
    replacement = _indent_block(body, I)
    src = src.replace(old, replacement, 1)
    _ok("orphan sweep inserted in main loop", True)
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 4 — enhance exchange-closed cleanup path
# ════════════════════════════════════════════════════════════════

def edit4_enhance_exchange_closed(src):
    print("\n▶ Edit 4: enhance exchange-closed cleanup")
    if "[FIX-24] force clean after exchange-closed" in src:
        print("   ℹ️  already applied")
        return src, True

    # Note: contains an Arabic comment. Match by its distinctive text.
    pat = re.compile(
        r"(?P<I>[ ]+)# نظّف أي أوامر واقية متبقية \(دفاعي\)\n"
        r"(?P=I)try:\n"
        r"(?P=I)    _cancel_all_protective_orders\(exchange, sym\)\n"
        r"(?P=I)except Exception:\n"
        r"(?P=I)    pass"
    )
    m = pat.search(src)
    if not m:
        print("   ⚠️  defensive cleanup block not found — skipping")
        return src, True  # not fatal

    I = m.group("I")
    body = (
        "# [FIX-24] force clean after exchange-closed\n"
        "try:\n"
        "    _n_clean = _cancel_all_protective_orders(exchange, sym)\n"
        "    if _n_clean > 0:\n"
        "        log.info(\n"
        "            f\"[Orphan] {sym} cleaned {_n_clean} residual \"\n"
        "            f\"protective order(s) after exchange close\"\n"
        "        )\n"
        "except Exception as _e:\n"
        "    log.debug(f\"[Orphan] cleanup {sym} failed: {_e}\")"
    )
    src = src[:m.start()] + _indent_block(body, I) + src[m.end():]
    _ok("exchange-closed path enhanced", True)
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 5 — enhance bot-exit cleanup path
# ════════════════════════════════════════════════════════════════

def edit5_enhance_bot_exit(src):
    print("\n▶ Edit 5: enhance bot-exit cleanup")
    if "[FIX-24] force clean after bot exit" in src:
        print("   ℹ️  already applied")
        return src, True

    pat = re.compile(
        r"(?P<I>[ ]+)try:\n"
        r"(?P=I)    _leftovers = _cancel_all_protective_orders\(exchange, sym\)\n"
        r"(?P=I)    if _leftovers > 0:\n"
        r"(?P=I)        log\.debug\(f\"\[Prot\] \{sym\} cleaned \"\n"
        r"(?P=I)                  f\"\{_leftovers\} leftover order\(s\)\"\)\n"
        r"(?P=I)except Exception as _e:\n"
        r"(?P=I)    log\.debug\(f\"\[Prot\] \{sym\} post-exit cleanup: \{_e\}\"\)"
    )
    m = pat.search(src)
    if not m:
        print("   ⚠️  bot-exit cleanup block not found — skipping")
        return src, True

    I = m.group("I")
    body = (
        "# [FIX-24] force clean after bot exit\n"
        "try:\n"
        "    _leftovers = _cancel_all_protective_orders(exchange, sym)\n"
        "    if _leftovers > 0:\n"
        "        log.info(f\"[Orphan] {sym} cleaned \"\n"
        "                  f\"{_leftovers} leftover order(s) \"\n"
        "                  f\"after bot exit\")\n"
        "except Exception as _e:\n"
        "    log.warning(f\"[Orphan] {sym} post-exit cleanup: {_e}\")"
    )
    src = src[:m.start()] + _indent_block(body, I) + src[m.end():]
    _ok("bot-exit path enhanced", True)
    return src, True


# ════════════════════════════════════════════════════════════════
# VERIFY
# ════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = [
        ("helpers block",          "[FIX-24] Orphan protective-order cleanup"),
        ("_ORPHAN_SWEEP_STATS",     "_ORPHAN_SWEEP_STATS: Dict = {"),
        ("_ORPHAN_SWEEP_ENABLED",   "_ORPHAN_SWEEP_ENABLED: bool = True"),
        ("_ORPHAN_SWEEP_INTERVAL",  "_ORPHAN_SWEEP_INTERVAL_S: float = 60.0"),
        ("_orphan_protective_sweep","def _orphan_protective_sweep("),
        ("_orphan_log_stats",       "def _orphan_log_stats("),
        ("post-cancel verify",      "[FIX-24] post-cancel verification"),
        ("main loop wiring",        "[FIX-24] orphan protective sweep"),
        ("exchange-closed path",    "[FIX-24] force clean after exchange-closed"),
        ("bot-exit path",           "[FIX-24] force clean after bot exit"),
    ]
    all_ok = True
    for label, marker in checks:
        ok = marker in src
        print(f"   {'✅' if ok else '❌'} {label}")
        if not ok:
            all_ok = False

    # Safety: ensure we didn't accidentally break the underlying file
    print("\n   Sanity:")
    for label, marker in [
        ("def run_live",                 "def run_live("),
        ("def run_backtest",             "def run_backtest("),
        ("def _place_protective_orders", "def _place_protective_orders("),
        ("def _cancel_all_protective_orders",
            "def _cancel_all_protective_orders("),
        ("def _is_protective_order",     "def _is_protective_order("),
        ("def _invalidate_position_cache",
            "def _invalidate_position_cache("),
    ]:
        cnt = src.count(marker)
        ok = (cnt == 1)
        print(f"   {'✅' if ok else '❌'} {label}: {cnt}")
        if not ok:
            all_ok = False
    return all_ok


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_complete.py")
    ap.add_argument("--output", default="trading_2_orphan_fixed.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} bytes)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  FIX-24: orphan protective-order cleanup                    ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: helpers block",        edit1_add_helpers),
        ("Edit 2: post-cancel verify",   edit2_post_cancel_verify),
        ("Edit 3: main loop wiring",     edit3_main_loop),
        ("Edit 4: exchange-closed path", edit4_enhance_exchange_closed),
        ("Edit 5: bot-exit path",        edit5_enhance_bot_exit),
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
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine\n"
        "#  Orphan-Protective Cleanup Build — FIX-24\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  FIX-24 adds:\n"
        "#    • _orphan_protective_sweep() — global 60s sweep\n"
        "#    • Skips symbols with live positions / pending orders\n"
        "#    • Cancels any orphan STOP_MARKET / TAKE_PROFIT_MARKET\n"
        "#    • Post-cancel verification in _cancel_all_protective_orders\n"
        "#    • Enhanced cleanup in exchange-closed path\n"
        "#    • Enhanced cleanup in bot-exit path\n"
        "#    • Stats: [Orphan] sweeps=N, found=M, cancelled=K\n"
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
        print(f"   ❌ Written file broken at line {e.lineno}: {e.msg}")

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
