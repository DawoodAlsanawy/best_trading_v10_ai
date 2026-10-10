#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adaptive_capital_v1.py
======================
CAPITAL-ADAPTIVE: يجعل البوت يعمل مع أي رأس مال (من $1 إلى $1M).

الفلسفة:
    - كل معامل يُشتق من رأس المال الفعلي عند الإقلاع
    - فلترة الرموز حسب MVT (Minimum Viable Trade)
    - Kill switch متدرج حسب tier
    - Runtime guard قبل كل دخول

المكونات:
    1. _compute_symbol_min_capital() — حساب MVT و min-capital لكل رمز
    2. _adapt_config_to_capital() — ضبط CFG حسب tier
    3. _filter_symbols_for_capital() — فلترة الرموز القابلة للتداول
    4. _check_capital_sufficient_for_entry() — فحص runtime

الاستخدام:
    python adaptive_capital_v1.py \\
        --input  trading_2_complete.py \\
        --output trading_2_adaptive.py
"""

import argparse
import os
import sys
from datetime import datetime


def _replace_once(src, old, new, tag, already_marker=None):
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
# [CAPITAL-ADAPTIVE v1] Auto-configure for any initial capital
# ════════════════════════════════════════════════════════════════
#
# Design principles:
#   1. All parameters derive from the actual capital at startup.
#   2. Symbols filtered by Minimum Viable Trade (MVT).
#   3. Kill switch scales by tier (micro→50%, whale→70%).
#   4. Runtime guard blocks entries when capital insufficient.
#
# Tiers:
#   micro  : $0    - $50      1 slot,  high risk, kill@50%
#   small  : $50   - $500     2 slots, med risk,  kill@60%
#   medium : $500  - $5000    3 slots, normal,    kill@70%
#   large  : $5k   - $50k     5 slots, normal,    kill@70%
#   whale  : $50k+           8 slots, low risk,  kill@70%

_CAPITAL_TIER: str = "unknown"
_CAPITAL_ADAPT_STATS: Dict = {
    "adaptations": 0,
    "symbols_filtered_out": 0,
    "blocked_by_capital": 0,
    "last_report_ts": 0.0,
}


def _tier_from_capital(cap: float) -> str:
    if cap < 50:    return "micro"
    if cap < 500:   return "small"
    if cap < 5000:  return "medium"
    if cap < 50000: return "large"
    return "whale"


def _compute_symbol_min_capital(exchange, sym: str,
                                 cfg=None) -> Optional[Dict]:
    """
    [CAPITAL-ADAPTIVE] Compute Minimum Viable Trade info for a symbol.

    Returns dict with:
      mvt            : minimum $ value to place a trade
      binding        : which filter binds (MIN_NOTIONAL / minQty / stepSize)
      max_leverage   : from tier 0
      mmr            : tier 0 maintenance margin rate
      price          : current price
    Returns None on failure.
    """
    try:
        mkt = exchange.market(sym)
    except Exception:
        return None
    if not mkt or not mkt.get("active"):
        return None

    info = mkt.get("info") or {}
    filters = {}
    for f in (info.get("filters") or []):
        ft = f.get("filterType")
        if ft:
            filters[ft] = f

    mn = filters.get("MIN_NOTIONAL", {})
    min_notional = float(mn.get("notional", 5.0) or 5.0)

    lot = filters.get("MARKET_LOT_SIZE", {}) or filters.get("LOT_SIZE", {})
    min_qty = float(lot.get("minQty", 0) or 0)
    step    = float(lot.get("stepSize", 0) or 0)

    try:
        tk = exchange.fetch_ticker(sym)
        price = float(tk.get("last") or 0)
    except Exception:
        return None
    if price <= 0:
        return None

    mvt_by_notional = min_notional
    mvt_by_qty   = min_qty * price if min_qty > 0 else 0.0
    mvt_by_step  = step * price if step > 0 else 0.0

    mvt = max(mvt_by_notional, mvt_by_qty, mvt_by_step)
    if mvt <= 0:
        return None

    if mvt_by_notional >= max(mvt_by_qty, mvt_by_step):
        binding = "MIN_NOTIONAL"
    elif mvt_by_qty >= mvt_by_step:
        binding = "minQty"
    else:
        binding = "stepSize"

    # Max leverage from tier 0
    max_lev = 1
    mmr = float(getattr(CFG, 'LIQ_FALLBACK_MMR', 0.02))
    try:
        tiers = exchange.fetch_leverage_tiers([sym])
        if tiers:
            tl = tiers[0].get("tiers") or []
            if tl:
                max_lev = int(tl[0].get("maxLeverage", 1) or 1)
                mmr = float(tl[0].get("maintenanceMarginRate", mmr) or mmr)
    except Exception:
        pass

    return {
        "symbol": sym,
        "price": price,
        "mvt": mvt,
        "binding": binding,
        "max_leverage": max_lev,
        "mmr": mmr,
    }


def _min_capital_for_symbol(info: Dict, cfg,
                             sl_frac: float = 0.02,
                             risk_frac: float = None) -> float:
    """
    capital needed = max(MVT × sl_frac / risk_frac,  MVT / max_lev)

    Interpretation:
      - We must place a notional ≥ MVT.
      - If we can't size below MVT, the effective risk becomes
        MVT × sl_frac, which must be ≤ capital × risk_frac.
      - Also: MVT must be reachable via leverage.
    """
    if risk_frac is None:
        risk_frac = min(float(getattr(cfg, 'MAX_RISK_PER_TRADE', 0.10)),
                        0.15)
    mvt = info["mvt"]
    lev = max(int(info.get("max_leverage", 1)), 1)
    cap_by_risk = mvt * sl_frac / risk_frac
    cap_by_lev  = mvt / lev
    return float(max(cap_by_risk, cap_by_lev))


def _adapt_config_to_capital(capital: float, cfg=None) -> str:
    """
    [CAPITAL-ADAPTIVE] Adjust CFG based on initial capital.
    Called once at startup (before run_live).
    Returns the tier name.
    """
    global _CAPITAL_TIER
    if cfg is None:
        cfg = CFG

    tier = _tier_from_capital(capital)
    _CAPITAL_TIER = tier

    # ── Risk levels ──
    if tier == "micro":
        cfg.BASE_RISK = 0.03
        cfg.MIN_RISK = 0.02
        cfg.MAX_RISK = 0.08
        cfg.MIN_RISK_PER_TRADE = 0.02
        cfg.MAX_RISK_PER_TRADE = 0.10
        cfg.PORTFOLIO_HEAT_MAX = 0.15
        cfg.RISK_STRENGTH_MIN = 0.7
        cfg.RISK_STRENGTH_MAX = 1.5
    elif tier == "small":
        cfg.BASE_RISK = 0.02
        cfg.MIN_RISK = 0.01
        cfg.MAX_RISK = 0.05
        cfg.MIN_RISK_PER_TRADE = 0.01
        cfg.MAX_RISK_PER_TRADE = 0.05
        cfg.PORTFOLIO_HEAT_MAX = 0.15
    # medium/large/whale → keep defaults

    # ── Leverage ──
    if tier == "micro":
        cfg.LEVERAGE_MIN = 10
        cfg.LEVERAGE_BASE = 50
        cfg.LEVERAGE_MAX = 50
    elif tier == "small":
        cfg.LEVERAGE_MIN = 5
        cfg.LEVERAGE_BASE = 30
        cfg.LEVERAGE_MAX = 50

    # ── Concurrent assets ──
    if tier == "micro":
        cfg.MAX_CONCURRENT_ASSETS = 1
    elif tier == "small":
        cfg.MAX_CONCURRENT_ASSETS = 2
    elif tier == "medium":
        cfg.MAX_CONCURRENT_ASSETS = 3
    elif tier == "large":
        cfg.MAX_CONCURRENT_ASSETS = 5
    # whale → keep 8 or user setting

    # ── Notional cap ──
    if tier == "micro":
        cfg.MAX_ABS_NOTIONAL = 50.0
    elif tier == "small":
        cfg.MAX_ABS_NOTIONAL = 500.0
    elif tier == "medium":
        cfg.MAX_ABS_NOTIONAL = 5000.0

    # ── Capital floor ──
    if tier == "micro":
        cfg.CAPITAL_FLOOR = max(0.05, capital * 0.05)
    elif tier == "small":
        cfg.CAPITAL_FLOOR = max(0.15, capital * 0.03)
    elif tier == "medium":
        cfg.CAPITAL_FLOOR = max(0.5, capital * 0.02)
    # large/whale → keep default 0.15 or user value

    # ── Cooldown ──
    if tier == "micro":
        cfg.REENTRY_COOLDOWN_BARS = 6
    elif tier == "small":
        cfg.REENTRY_COOLDOWN_BARS = 4

    # ── Kill switch ──
    if tier == "micro":
        cfg.MAX_DRAWDOWN_HALT = 0.50
    elif tier == "small":
        cfg.MAX_DRAWDOWN_HALT = 0.60
    else:
        cfg.MAX_DRAWDOWN_HALT = 0.70

    # ── SL widening: keep tighter for small capital ──
    # (smaller SL = smaller $ risk per trade at MVT floor)
    if tier == "micro":
        cfg.SL_WIDEN_MULT = 1.0     # tightest
        cfg.SL_MIN_SIGMA = 2.5
        cfg.SL_MAX_SIGMA = 6.0
    elif tier == "small":
        cfg.SL_WIDEN_MULT = 1.2
        cfg.SL_MIN_SIGMA = 2.8
        cfg.SL_MAX_SIGMA = 7.0
    # medium+ → keep defaults (1.5 / 3.0 / 8.0)

    # ── Log summary ──
    log.info("")
    log.info("╔══════════════════════════════════════════════════════════════╗")
    log.info("║  [CAPITAL-ADAPTIVE] Configuration applied                   ║")
    log.info("╚══════════════════════════════════════════════════════════════╝")
    log.info(f"  Tier            : {tier.upper()}")
    log.info(f"  Capital         : ${capital:.4f}")
    log.info(f"  BASE_RISK       : {cfg.BASE_RISK*100:.2f}%")
    log.info(f"  MIN/MAX_RISK    : "
             f"{cfg.MIN_RISK_PER_TRADE*100:.2f}% / "
             f"{cfg.MAX_RISK_PER_TRADE*100:.2f}%")
    log.info(f"  HEAT_MAX        : {cfg.PORTFOLIO_HEAT_MAX*100:.2f}%")
    log.info(f"  LEVERAGE        : "
             f"[{cfg.LEVERAGE_MIN}, {cfg.LEVERAGE_BASE}, {cfg.LEVERAGE_MAX}]")
    log.info(f"  MAX_CONCURRENT  : {cfg.MAX_CONCURRENT_ASSETS}")
    log.info(f"  MAX_ABS_NOTIONAL: ${cfg.MAX_ABS_NOTIONAL:.2f}")
    log.info(f"  CAPITAL_FLOOR   : ${cfg.CAPITAL_FLOOR:.4f}")
    log.info(f"  KILL_DD         : {cfg.MAX_DRAWDOWN_HALT*100:.0f}%")
    log.info(f"  COOLDOWN_BARS   : {cfg.REENTRY_COOLDOWN_BARS}")
    log.info(f"  SL_WIDEN_MULT   : {cfg.SL_WIDEN_MULT}")
    log.info(f"  SL_SIGMA        : "
             f"[{cfg.SL_MIN_SIGMA}, {cfg.SL_MAX_SIGMA}]")
    log.info("")

    _CAPITAL_ADAPT_STATS["adaptations"] += 1
    return tier


def _filter_symbols_for_capital(exchange, symbols: List[str],
                                  capital: float, cfg=None,
                                  sl_frac: float = 0.02,
                                  risk_frac: float = None) -> List[str]:
    """
    [CAPITAL-ADAPTIVE] Return only symbols tradeable at this capital.
    Sorted by lowest MVT first (best chances for small capital).
    """
    if cfg is None:
        cfg = CFG
    if risk_frac is None:
        risk_frac = min(float(cfg.MAX_RISK_PER_TRADE), 0.15)

    eligible: List[Tuple[str, float]] = []
    n_out = 0

    log.info("[CapitalAdapt] Filtering symbols by capital requirement…")
    for sym in symbols:
        info = _compute_symbol_min_capital(exchange, sym, cfg)
        if info is None:
            n_out += 1
            continue
        min_cap = _min_capital_for_symbol(info, cfg,
                                           sl_frac=sl_frac,
                                           risk_frac=risk_frac)
        if capital >= min_cap:
            eligible.append((sym, min_cap, info["mvt"]))
        else:
            n_out += 1
            log.debug(
                f"[CapitalAdapt] {sym} requires ${min_cap:.4f} "
                f"(MVT=${info['mvt']:.2f}) — skip"
            )

    eligible.sort(key=lambda x: x[2])  # by MVT ascending
    _CAPITAL_ADAPT_STATS["symbols_filtered_out"] += n_out

    result = [s[0] for s in eligible]
    log.info(
        f"[CapitalAdapt] {len(result)}/{len(symbols)} symbols "
        f"tradeable at ${capital:.4f} ({n_out} filtered out)"
    )
    if result:
        log.info(f"[CapitalAdapt] Top 5 (lowest MVT):")
        for sym, min_cap, mvt in eligible[:5]:
            log.info(f"  {sym:<14s}  MVT=${mvt:.2f}  "
                     f"min_cap=${min_cap:.4f}  "
                     f"headroom={capital/min_cap:.2f}x")
    else:
        log.warning(
            "[CapitalAdapt] NO symbols tradeable at this capital! "
            "Increase capital or reduce risk settings."
        )
    return result


def _check_capital_sufficient_for_entry(sym: str, capital: float,
                                          exchange, cfg=None
                                          ) -> Tuple[bool, str]:
    """
    [CAPITAL-ADAPTIVE] Runtime check before placing an entry.
    Returns (ok, reason).
    """
    if cfg is None:
        cfg = CFG
    if capital <= cfg.CAPITAL_FLOOR:
        return False, (f"capital ${capital:.4f} ≤ "
                       f"floor ${cfg.CAPITAL_FLOOR:.4f}")
    try:
        min_notional = _get_min_notional(exchange, sym)
    except Exception:
        min_notional = 5.0
    max_notional = capital * cfg.LEVERAGE_BASE
    if max_notional < min_notional:
        return False, (f"max notional ${max_notional:.2f} < "
                       f"MIN_NOTIONAL ${min_notional:.2f}")
    return True, "OK"


def _capital_adapt_log_stats() -> None:
    """Log capital-adapt stats every 5 min."""
    now = time.time()
    if now - float(_CAPITAL_ADAPT_STATS.get("last_report_ts", 0.0)) < 300:
        return
    _CAPITAL_ADAPT_STATS["last_report_ts"] = now
    s = _CAPITAL_ADAPT_STATS
    if s["blocked_by_capital"] == 0 and s["symbols_filtered_out"] == 0:
        return
    log.info(
        f"[CapitalAdapt] tier={_CAPITAL_TIER} "
        f"blocked={s['blocked_by_capital']} "
        f"filtered_out={s['symbols_filtered_out']} "
        f"adaptations={s['adaptations']}"
    )


# ══ end CAPITAL-ADAPTIVE ══


'''


# ════════════════════════════════════════════════════════════════
# Edit 1 — insert helper block
# ════════════════════════════════════════════════════════════════

def edit1_add_helpers(src):
    print("\n▶ Edit 1: insert capital-adaptive helpers")
    anchor = "def load_symbol_meta(mode: str) -> Dict[str, Dict]:"
    if anchor not in src:
        print("   ❌ anchor 'def load_symbol_meta' not found")
        return src, False
    if "[CAPITAL-ADAPTIVE v1] Auto-configure" in src:
        print("   ℹ️  already applied")
        return src, True
    src = src.replace(anchor, HELPER_BLOCK + anchor, 1)
    print("   ✅ helper block inserted")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 2 — call _adapt_config_to_capital in main()
# ════════════════════════════════════════════════════════════════

def edit2_adapt_in_main(src):
    print("\n▶ Edit 2: call _adapt_config_to_capital in main()")
    if "[CAPITAL-ADAPTIVE] main()" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "    if args.capital   is not None: CFG.INITIAL_CAPITAL = args.capital\n"
        "    if args.live_capital is not None: CFG.LIVE_TRADING_CAPITAL = float(args.live_capital)"
    )
    if anchor not in src:
        print("   ❌ capital-anchor not found in main()")
        return src, False

    replacement = (
        "    if args.capital   is not None: CFG.INITIAL_CAPITAL = args.capital\n"
        "    if args.live_capital is not None: CFG.LIVE_TRADING_CAPITAL = float(args.live_capital)\n"
        "    # ══ [CAPITAL-ADAPTIVE] main() — apply capital-based overrides ══\n"
        "    _adapt_config_to_capital(float(CFG.INITIAL_CAPITAL), CFG)"
    )
    src = src.replace(anchor, replacement, 1)
    print("   ✅ adaptation called in main()")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 3 — filter symbols in run_live
# ════════════════════════════════════════════════════════════════

def edit3_filter_symbols_in_live(src):
    print("\n▶ Edit 3: filter symbols in run_live")
    if "[CAPITAL-ADAPTIVE] filter in run_live" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        '    log.info("⏳ جلب الزمكان المالي التاريخي '
        '(هذه العملية تحدث مرة واحدة فقط...)")\n'
        '    top_syms = scan_top_assets(exchange)'
    )
    if anchor not in src:
        print("   ❌ top_syms anchor not found")
        idx = src.find("top_syms = scan_top_assets")
        if idx >= 0:
            print(f"      context: {src[max(0,idx-200):idx+200]!r}")
        return src, False

    replacement = (
        '    log.info("⏳ جلب الزمكان المالي التاريخي '
        '(هذه العملية تحدث مرة واحدة فقط...)")\n'
        '    top_syms = scan_top_assets(exchange)\n'
        '    # ══ [CAPITAL-ADAPTIVE] filter in run_live ══\n'
        '    _cap_for_filter = float(getattr(CFG, "LIVE_TRADING_CAPITAL", 0.0) or\n'
        '                             getattr(CFG, "INITIAL_CAPITAL", 100.0))\n'
        '    if _cap_for_filter > 0:\n'
        '        _filtered = _filter_symbols_for_capital(\n'
        '            exchange, list(top_syms), _cap_for_filter, CFG\n'
        '        )\n'
        '        if _filtered:\n'
        '            top_syms = _filtered\n'
        '        else:\n'
        '            log.error(\n'
        '                "[CapitalAdapt] NO symbols tradeable — "\n'
        '                "increase capital or adjust risk settings. Aborting."\n'
        '            )\n'
        '            return'
    )
    src = src.replace(anchor, replacement, 1)
    print("   ✅ symbol filter inserted")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 4 — runtime capital guard before entry
# ════════════════════════════════════════════════════════════════

def edit4_runtime_guard(src):
    print("\n▶ Edit 4: runtime capital guard before entry")
    if "[CAPITAL-ADAPTIVE] runtime guard" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "                    # ══ [SR FILTER — Live] ══\n"
        "                    _live_ci = max(0, len(ad.closes) - 2)\n"
        "                    _sr_ok, _sr_reason = _sr_filter_check(sig, ad, _live_ci)\n"
        "                    if not _sr_ok:\n"
        "                        log.info(f\"[SR] {sym} rejected: {_sr_reason}\")\n"
        "                        continue"
    )
    if anchor not in src:
        print("   ❌ SR filter anchor not found")
        return src, False

    replacement = (
        "                    # ══ [CAPITAL-ADAPTIVE] runtime guard ══\n"
        "                    _cap_ok, _cap_reason = "
        "_check_capital_sufficient_for_entry(\n"
        "                        sym, cap_live, exchange, CFG\n"
        "                    )\n"
        "                    if not _cap_ok:\n"
        "                        _CAPITAL_ADAPT_STATS['blocked_by_capital'] += 1\n"
        "                        log.debug(\n"
        "                            f\"[CapitalAdapt] {sym} blocked: \"\n"
        "                            f\"{_cap_reason}\"\n"
        "                        )\n"
        "                        continue\n"
        "\n"
        "                    # ══ [SR FILTER — Live] ══\n"
        "                    _live_ci = max(0, len(ad.closes) - 2)\n"
        "                    _sr_ok, _sr_reason = _sr_filter_check(sig, ad, _live_ci)\n"
        "                    if not _sr_ok:\n"
        "                        log.info(f\"[SR] {sym} rejected: {_sr_reason}\")\n"
        "                        continue"
    )
    src = src.replace(anchor, replacement, 1)
    print("   ✅ runtime guard inserted")
    return src, True


# ════════════════════════════════════════════════════════════════
# Edit 5 — stats logger in main loop
# ════════════════════════════════════════════════════════════════

def edit5_stats_logger(src):
    print("\n▶ Edit 5: wire stats logger")
    if "_capital_adapt_log_stats()" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()"
    )
    if anchor not in src:
        print("   ❌ pos-cache anchor not found")
        return src, False

    replacement = (
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()\n"
        "            # [CAPITAL-ADAPTIVE] stats\n"
        "            _capital_adapt_log_stats()"
    )
    src = src.replace(anchor, replacement, 1)
    print("   ✅ stats logger wired")
    return src, True


# ════════════════════════════════════════════════════════════════
# VERIFY
# ════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = [
        ("helpers block",          "[CAPITAL-ADAPTIVE v1] Auto-configure"),
        ("_CAPITAL_TIER",          "_CAPITAL_TIER: str = "),
        ("_CAPITAL_ADAPT_STATS",   "_CAPITAL_ADAPT_STATS: Dict = {"),
        ("_tier_from_capital",     "def _tier_from_capital("),
        ("_compute_symbol_min_capital",
            "def _compute_symbol_min_capital("),
        ("_min_capital_for_symbol","def _min_capital_for_symbol("),
        ("_adapt_config_to_capital","def _adapt_config_to_capital("),
        ("_filter_symbols_for_capital",
            "def _filter_symbols_for_capital("),
        ("_check_capital_sufficient_for_entry",
            "def _check_capital_sufficient_for_entry("),
        ("main() adaptation call", "[CAPITAL-ADAPTIVE] main()"),
        ("run_live filter",        "[CAPITAL-ADAPTIVE] filter in run_live"),
        ("runtime guard",          "[CAPITAL-ADAPTIVE] runtime guard"),
        ("stats logger",           "_capital_adapt_log_stats()"),
    ]
    all_ok = True
    for label, marker in checks:
        ok = marker in src
        print(f"   {'✅' if ok else '❌'} {label}")
        if not ok:
            all_ok = False

    print("\n   Sanity:")
    for label, marker, want in [
        ("def run_live", "def run_live(", True),
        ("def run_backtest", "def run_backtest(", True),
        ("def main", "def main(", True),
        ("def place_pending_entry", "def place_pending_entry(", True),
        ("def _get_min_notional", "def _get_min_notional(", True),
    ]:
        cnt = src.count(marker)
        ok = (cnt == 1) if want else (cnt == 0)
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
    ap.add_argument("--output", default="trading_2_adaptive.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} bytes)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  CAPITAL-ADAPTIVE v1 — $1 to $1M support                    ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: helpers block",     edit1_add_helpers),
        ("Edit 2: adapt in main()",   edit2_adapt_in_main),
        ("Edit 3: filter in live",    edit3_filter_symbols_in_live),
        ("Edit 4: runtime guard",     edit4_runtime_guard),
        ("Edit 5: stats logger",      edit5_stats_logger),
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
        "#  Capital-Adaptive Build — v1\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  Capital-Adaptive v1 adds:\n"
        "#    • _adapt_config_to_capital() — 5 tiers (micro→whale)\n"
        "#    • _filter_symbols_for_capital() — MVT-based filtering\n"
        "#    • _check_capital_sufficient_for_entry() — runtime guard\n"
        "#    • _compute_symbol_min_capital() — per-symbol MVT\n"
        "#    • Tier-aware risk, leverage, kill switch, cooldown\n"
        "#    • SL_WIDEN_MULT auto-tuned (1.0 → 1.5 by tier)\n"
        "# ═══════════════════════════════════════════════════════\n"
    )

    if src.startswith("#!"):
        first_nl = src.index("\n")
        src_out = header + src[first_nl + 1:]
    else:
        src_out = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src_out)

    # Re-verify written
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

    print("\n  ▶ Run with $1:")
    print(f"     python {args.output} --mode testnet --api-key ... "
          f"--api-secret ... --capital 1 --live-capital 1")


if __name__ == "__main__":
    main()
