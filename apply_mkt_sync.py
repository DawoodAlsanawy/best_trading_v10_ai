#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_mkt_sync.py
=================
MKT-SYNC: يضمن تطابق backtest مع live في:
    1. Minimum Viable Trade (MVT) لكل رمز
    2. Round qty إلى stepSize الصحيح
    3. تمرير `symbol` لـ L_liq_max

الحل:
    - Cache عالمي _MARKET_META يُملأ مرة واحدة عند بدء الـ backtest
    - _unified_compute_mvt يقرأ من cache عندما exchange is None
    - _round_qty_cached يقرب qty باستخدام cache stepSize

الاستخدام:
    python apply_mkt_sync.py \\
        --input  trading_2_unified_full.py \\
        --output trading_2_full_sync.py
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
# The MKT-SYNC block
# ══════════════════════════════════════════════════════════════════════

MKT_BLOCK = r'''# ══════════════════════════════════════════════════════════════════════
# [MKT-SYNC] Market metadata cache for backtest-live parity
# ══════════════════════════════════════════════════════════════════════
#
# Problem:
#   In backtest, exchange is None. This causes:
#     • MVT falls back to MIN_NOTIONAL = 5.0 (not per-symbol)
#     • qty is not rounded to stepSize
#     • L_liq_max lacks symbol context
#
# Solution:
#   Load filters once at backtest startup into _MARKET_META.
#   Unified engine reads from cache when exchange is None.
#
# Cache structure:
#   _MARKET_META[symbol] = {
#       "min_notional": float,   # MIN_NOTIONAL filter
#       "min_qty": float,        # LOT_SIZE.minQty
#       "step_size": float,      # LOT_SIZE.stepSize
#       "tick_size": float,      # PRICE_FILTER.tickSize
#   }

_MARKET_META: Dict = {}


def _load_market_meta_backtest(exchange, symbols: List[str]) -> int:
    """
    [MKT-SYNC] Load MIN_NOTIONAL, minQty, stepSize, tickSize
    for each symbol from the exchange.
    Called once at backtest startup.
    """
    global _MARKET_META
    if exchange is None:
        log.warning("[MktMeta] exchange is None — skipping")
        return 0

    try:
        exchange.load_markets()
    except Exception as e:
        log.warning(f"[MktMeta] load_markets failed: {e}")
        return 0

    loaded = 0
    failed = 0
    for sym in symbols:
        try:
            mkt = exchange.market(sym)
            if not mkt:
                failed += 1
                continue

            info = mkt.get("info") or {}
            filters = {}
            for f in (info.get("filters") or []):
                ft = f.get("filterType")
                if ft:
                    filters[ft] = f

            min_notional = float(
                (filters.get("MIN_NOTIONAL") or {}).get(
                    "notional", 5.0) or 5.0
            )
            lot = (filters.get("MARKET_LOT_SIZE")
                   or filters.get("LOT_SIZE") or {})
            min_qty = float(lot.get("minQty", 0) or 0)
            step_size = float(lot.get("stepSize", 0) or 0)
            tick_size = float(
                (filters.get("PRICE_FILTER") or {}).get(
                    "tickSize", 0) or 0
            )

            _MARKET_META[sym] = {
                "min_notional": min_notional,
                "min_qty": min_qty,
                "step_size": step_size,
                "tick_size": tick_size,
            }
            loaded += 1
        except Exception as e:
            log.debug(f"[MktMeta] {sym} failed: {e}")
            failed += 1

    log.info(
        f"[MktMeta] loaded {loaded}/{len(symbols)} symbols "
        f"(failed={failed})"
    )
    return loaded


def _mkt_meta_mvt(sym: str, price: float) -> Optional[float]:
    """
    [MKT-SYNC] Compute MVT from cached metadata.
    Returns None if symbol not in cache.
    """
    if sym not in _MARKET_META:
        return None
    if price <= 0:
        return None
    meta = _MARKET_META[sym]
    try:
        return float(max(
            meta["min_notional"],
            meta["min_qty"] * price if meta["min_qty"] > 0 else 0.0,
            meta["step_size"] * price if meta["step_size"] > 0 else 0.0,
        ))
    except Exception:
        return None


def _round_qty_cached(sym: str, qty: float) -> float:
    """
    [MKT-SYNC] Round qty using cached step_size.
    Falls back to unchanged qty if not in cache.
    """
    if sym not in _MARKET_META:
        return qty
    step = float(_MARKET_META[sym].get("step_size", 0))
    if step <= 0 or qty <= 0:
        return qty
    import math
    return math.floor(qty / step) * step


# ══ end MKT-SYNC ══


'''


# ══════════════════════════════════════════════════════════════════════
# Edit 1: Insert MKT-SYNC block before run_backtest
# ══════════════════════════════════════════════════════════════════════

def edit1_insert_block(src):
    print("\n▶ Edit 1: insert MKT-SYNC block")
    anchor = "def run_backtest(cfg):"
    if anchor not in src:
        print("   ❌ anchor 'def run_backtest' not found")
        return src, False
    if "[MKT-SYNC] Market metadata cache" in src:
        print("   ℹ️  already applied")
        return src, True
    src = src.replace(anchor, MKT_BLOCK + anchor, 1)
    print(f"   ✅ inserted ({len(MKT_BLOCK):,} chars)")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 2: Modify _unified_compute_mvt to use cache
# ══════════════════════════════════════════════════════════════════════

def edit2_patch_compute_mvt(src):
    print("\n▶ Edit 2: patch _unified_compute_mvt")
    if "[MKT-SYNC] cache check" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        'def _unified_compute_mvt(exchange, sym: str, price: float) -> float:\n'
        '    """Dynamic MVT per symbol/price. Falls back to MIN_NOTIONAL."""\n'
        '    if price <= 0:\n'
        '        return float(getattr(CFG, "MIN_NOTIONAL", 5.0))\n'
        '    try:\n'
        '        mkt = exchange.market(sym)\n'
    )
    new = (
        'def _unified_compute_mvt(exchange, sym: str, price: float) -> float:\n'
        '    """Dynamic MVT per symbol/price. Falls back to MIN_NOTIONAL."""\n'
        '    if price <= 0:\n'
        '        return float(getattr(CFG, "MIN_NOTIONAL", 5.0))\n'
        '    # [MKT-SYNC] cache check (backtest path)\n'
        '    if exchange is None:\n'
        '        try:\n'
        '            _cached = _mkt_meta_mvt(sym, price)\n'
        '            if _cached is not None and _cached > 0:\n'
        '                return float(_cached)\n'
        '        except Exception:\n'
        '            pass\n'
        '        return float(getattr(CFG, "MIN_NOTIONAL", 5.0))\n'
        '    try:\n'
        '        mkt = exchange.market(sym)\n'
    )
    return _replace_once(src, old, new, "compute-mvt")


# ══════════════════════════════════════════════════════════════════════
# Edit 3: Modify _unified_compute_L_liq_max signature
# ══════════════════════════════════════════════════════════════════════

def edit3_patch_L_liq_max(src):
    print("\n▶ Edit 3: patch _unified_compute_L_liq_max")
    if "[MKT-SYNC] pass symbol to Liq cap" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        'def _unified_compute_L_liq_max(mmr: float, f_sl: float) -> int:\n'
        '    try:\n'
        '        return int(compute_max_leverage_by_liq(\n'
        '            sl_frac_max=f_sl, mmr=mmr,\n'
        '            safety_mult=_UNIFIED_LIQ_SAFETY,\n'
        '        ))\n'
        '    except Exception:\n'
        '        return int(getattr(CFG, "LEVERAGE_MAX", 50))'
    )
    new = (
        'def _unified_compute_L_liq_max(mmr: float, f_sl: float,\n'
        '                                 symbol: Optional[str] = None) -> int:\n'
        '    try:\n'
        '        # [MKT-SYNC] pass symbol to Liq cap for accurate tiers\n'
        '        return int(compute_max_leverage_by_liq(\n'
        '            sl_frac_max=f_sl, mmr=mmr,\n'
        '            safety_mult=_UNIFIED_LIQ_SAFETY,\n'
        '            symbol=symbol,\n'
        '        ))\n'
        '    except Exception:\n'
        '        return int(getattr(CFG, "LEVERAGE_MAX", 50))'
    )
    return _replace_once(src, old, new, "L-liq-max")


# ══════════════════════════════════════════════════════════════════════
# Edit 4: Update call site of _unified_compute_L_liq_max
# ══════════════════════════════════════════════════════════════════════

def edit4_patch_L_liq_call(src):
    print("\n▶ Edit 4: update L_liq_max call site")
    if "symbol=sym  # [MKT-SYNC]" in src:
        print("   ℹ️  already applied")
        return src, True

    old = "        L_liq_max = _unified_compute_L_liq_max(mmr, f_sl)"
    new = "        L_liq_max = _unified_compute_L_liq_max(mmr, f_sl, symbol=sym)  # [MKT-SYNC]"
    return _replace_once(src, old, new, "L-liq-call")


# ══════════════════════════════════════════════════════════════════════
# Edit 5: Patch qty rounding for backtest
# ══════════════════════════════════════════════════════════════════════

def edit5_patch_qty_round(src):
    print("\n▶ Edit 5: patch qty rounding")
    if "[MKT-SYNC] round qty via cache" in src:
        print("   ℹ️  already applied")
        return src, True

    old = (
        '        qty = best["N_opt"] / price\n'
        '        try:\n'
        '            if exchange is not None:\n'
        '                qty = _round_qty(exchange, sym, qty)\n'
        '        except Exception:\n'
        '            pass\n'
    )
    new = (
        '        qty = best["N_opt"] / price\n'
        '        try:\n'
        '            if exchange is not None:\n'
        '                qty = _round_qty(exchange, sym, qty)\n'
        '            else:\n'
        '                # [MKT-SYNC] round qty via cache for backtest\n'
        '                qty = _round_qty_cached(sym, qty)\n'
        '        except Exception:\n'
        '            pass\n'
    )
    return _replace_once(src, old, new, "qty-round")


# ══════════════════════════════════════════════════════════════════════
# Edit 6: Call loader in run_backtest
# ══════════════════════════════════════════════════════════════════════

def edit6_add_loader_call(src):
    print("\n▶ Edit 6: add loader call in run_backtest")
    if "[MKT-SYNC] load market metadata" in src:
        print("   ℹ️  already applied")
        return src, True

    # Unique anchor (only in run_backtest, has cfg.n_assets arg)
    anchor = "    syms = scan_top_assets(exchange, cfg.n_assets)"
    if anchor not in src:
        print("   ❌ anchor not found")
        return src, False

    new = anchor + (
        "\n"
        "    # [MKT-SYNC] load market metadata for backtest-live parity\n"
        "    try:\n"
        "        _load_market_meta_backtest(exchange, syms)\n"
        "    except Exception as _me:\n"
        "        log.warning(f\"[MktMeta] backtest load failed: {_me}\")"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ loader call added")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = [
        ("MKT-SYNC block",          "[MKT-SYNC] Market metadata cache"),
        ("_MARKET_META",            "_MARKET_META: Dict = {}"),
        ("load market meta",        "def _load_market_meta_backtest("),
        ("mkt_meta_mvt",            "def _mkt_meta_mvt("),
        ("round_qty_cached",        "def _round_qty_cached("),
        ("compute_mvt cache check", "[MKT-SYNC] cache check"),
        ("L_liq_max symbol arg",    "[MKT-SYNC] pass symbol to Liq cap"),
        ("L_liq_max call site",     "symbol=sym)  # [MKT-SYNC]"),
        ("qty round via cache",     "[MKT-SYNC] round qty via cache"),
        ("loader call",             "[MKT-SYNC] load market metadata"),
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
        ("def _unified_compute_mvt", "def _unified_compute_mvt(", 1),
        ("def _unified_compute_L_liq_max",
            "def _unified_compute_L_liq_max(", 1),
        ("def main", "def main(", 1),
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
    ap.add_argument("--input", default="trading_2_unified_full.py")
    ap.add_argument("--output", default="trading_2_full_sync.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} chars)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  MKT-SYNC — Backtest/Live Parity for MVT & stepSize         ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: insert MKT-SYNC block", edit1_insert_block),
        ("Edit 2: patch compute_mvt",      edit2_patch_compute_mvt),
        ("Edit 3: patch L_liq_max",        edit3_patch_L_liq_max),
        ("Edit 4: update L_liq_max call",  edit4_patch_L_liq_call),
        ("Edit 5: patch qty rounding",     edit5_patch_qty_round),
        ("Edit 6: add loader call",        edit6_add_loader_call),
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
        "#  UNIFIED + MKT-SYNC Build (full parity)\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  Adds:\n"
        "#    • _MARKET_META cache (backtest path)\n"
        "#    • MVT per-symbol from cache\n"
        "#    • qty rounding via cache stepSize\n"
        "#    • L_liq_max symbol-aware\n"
        "#\n"
        "#  Result: backtest matches live for MVT and leverage.\n"
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
    print("  ▶ Run backtest (full parity):")
    print(f"     python {args.output} --mode backtest --unified "
          f"--capital 100 --nassets 5 --maxcon 2 --timeframe 4h --history-days 30")

    if not write_ok:
        sys.exit(3)


if __name__ == "__main__":
    main()
