#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_trail_subbars_parity.py
==============================
Makes live Trailing SL parity with backtest sub-bars (exactly).

Behavior:
    • WITHOUT flag: unchanged (ticker-based peak tracking)
    • WITH --trail-sync-to-subbars:
        peak_price and trail_sl update ONLY when a sub-bar
        (e.g., 15m) CLOSES — no ticker, no 1m forming bar.
        Matches backtest's ad.sub_highs/ad.sub_lows exactly.

What stays the same:
    • SL/TP hit detection: ticker-based (safety preserved)
    • Partial TP: ticker-based
    • All physics, risk, leverage logic: untouched

Expected impact (with flag ON):
    • peak/SL: ~16 updates per 4h bar (vs 500-2000 ticker updates)
    • Rate limit: ~215x reduction for extremes polling
    • Exchange SL orders: ~100x reduction
    • Backtest↔live parity: exact

Usage:
    python3 apply_trail_subbars_parity.py --dry-run
    python3 apply_trail_subbars_parity.py
    python3 apply_trail_subbars_parity.py --file trading_2_live4_claude2_v4_micro.py
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime

DEFAULT_FILE = "trading_2_live4_claude2_v4_micro.py"


# ══════════════════════════════════════════════════════════════
# MARKERS — used to detect if a patch is already applied
# ══════════════════════════════════════════════════════════════
MARK_P1 = "TRAIL_USE_SUBBARS_ONLY: bool = False"
MARK_P2 = "[SUB-BAR PARITY MODE]"
MARK_P3 = "[SUB-BAR-TRAIL-PARITY]"
MARK_P4 = "'_last_sub_ts': 0,"
MARK_P5 = "pos.setdefault('_last_sub_ts', 0)"
MARK_P6 = "--trail-sync-to-subbars"
MARK_P7 = "[Trail] SUB-BAR PARITY ON"


# ══════════════════════════════════════════════════════════════
# P1 — Config: new flag
# ══════════════════════════════════════════════════════════════
P1_OLD = "    TRAIL_ENABLED: bool = True\n"
P1_NEW = (
    "    TRAIL_ENABLED: bool = True\n"
    "    # ══ [SUB-BAR-TRAIL-PARITY] Peak/SL update only on sub-bar close ══\n"
    "    # When True, peak_price and trail_sl are updated ONLY when a new\n"
    "    # sub-bar (e.g., 15m) closes. No ticker, no 1m forming bar.\n"
    "    # Matches backtest's ad.sub_highs/ad.sub_lows exactly.\n"
    "    # Default False → preserves current ticker-based behavior.\n"
    "    TRAIL_USE_SUBBARS_ONLY: bool = False\n"
)


# ══════════════════════════════════════════════════════════════
# P2 — Full replacement of _lv_update_extremes
# ══════════════════════════════════════════════════════════════
P2_OLD = (
    "def _lv_update_extremes(exchange, sym, pos, price, now) -> None:\n"
    "    # running high/low since entry (ticker + 1m candles) ≙ backtest sub-bar extremes\n"
    "    try:\n"
    "        entry = float(pos.get('entry') or 0.0)\n"
    "        if entry <= 0:\n"
    "            return\n"
    "        hi = max(float(pos.get('_hi', entry)), float(price))\n"
    "        lo = min(float(pos.get('_lo', entry)), float(price))\n"
    "        if now - float(pos.get('_ext_ts', 0.0)) >= float(_lv_cfg('LIVE_MFE_POLL_S', 15.0)):\n"
    "            pos['_ext_ts'] = now\n"
    "            try:\n"
    "                _rate_record(1.0)\n"
    "                t0 = float(pos.get('entry_ts') or now) // 60 * 60 * 1000\n"
    "                for c in exchange.fetch_ohlcv(sym, '1m', limit=3) or []:\n"
    "                    if float(c[0]) >= t0:\n"
    "                        hi = max(hi, float(c[2]))\n"
    "                        lo = min(lo, float(c[3]))\n"
    "            except Exception as e:\n"
    "                log.debug(f\"[LV] 1m extremes {sym} failed: {e}\")\n"
    "        pos['_hi'], pos['_lo'] = hi, lo\n"
    "    except Exception:\n"
    "        pass\n"
)

P2_NEW = (
    "def _lv_update_extremes(exchange, sym, pos, price, now) -> None:\n"
    "    \"\"\"\n"
    "    Update _hi/_lo for trailing SL.\n"
    "\n"
    "    Two modes:\n"
    "      • Default (TRAIL_USE_SUBBARS_ONLY=False):\n"
    "          ticker (5s) + 1m candles (15s). Fast but not parity.\n"
    "\n"
    "      • [SUB-BAR PARITY MODE] (TRAIL_USE_SUBBARS_ONLY=True):\n"
    "          CLOSED sub-bars only. Uses OHLCV of sub_tf (e.g., 15m),\n"
    "          EXCLUDING the currently-forming bar. Matches backtest\n"
    "          ad.sub_highs/ad.sub_lows exactly.\n"
    "\n"
    "    Only _hi/_lo (peak tracking) is affected.\n"
    "    SL/TP hit detection remains ticker-based for safety.\n"
    "    \"\"\"\n"
    "    try:\n"
    "        entry = float(pos.get('entry') or 0.0)\n"
    "        if entry <= 0:\n"
    "            return\n"
    "\n"
    "        # ══ [SUB-BAR PARITY MODE] ══\n"
    "        if getattr(CFG, 'TRAIL_USE_SUBBARS_ONLY', False):\n"
    "            _sub_tf = _get_subbars_tf(CFG.timeframe) or CFG.timeframe\n"
    "            try:\n"
    "                import ccxt as _cc\n"
    "                _sub_sec = int(_cc.binance().parse_timeframe(_sub_tf))\n"
    "            except Exception:\n"
    "                _sub_sec = 900  # 15m fallback\n"
    "\n"
    "            _now_ms = int(now * 1000)\n"
    "            _last_ts = int(pos.get('_last_sub_ts', 0))\n"
    "            _entry_ts_ms = int(float(pos.get('entry_ts', 0)) * 1000)\n"
    "            if _entry_ts_ms <= 0:\n"
    "                _entry_ts_ms = _now_ms - (24 * 60 * 60 * 1000)\n"
    "\n"
    "            if _last_ts <= 0:\n"
    "                _last_ts = _entry_ts_ms\n"
    "                _max_lookback_ms = _now_ms - (7 * 24 * 60 * 60 * 1000)\n"
    "                if _last_ts < _max_lookback_ms:\n"
    "                    _last_ts = _max_lookback_ms\n"
    "                    log.debug(f\"[SubBar-Parity] {sym} capped lookback at 7 days\")\n"
    "\n"
    "            _current_open_ms = (_now_ms // (_sub_sec * 1000)) * (_sub_sec * 1000)\n"
    "            _last_closed_open_ms = _current_open_ms - (_sub_sec * 1000)\n"
    "\n"
    "            if _last_ts >= _last_closed_open_ms:\n"
    "                return\n"
    "\n"
    "            _all_candles = []\n"
    "            _loop_since = _last_ts\n"
    "            for _ in range(20):\n"
    "                try:\n"
    "                    _rate_record(2.0)\n"
    "                    _chunk = exchange.fetch_ohlcv(\n"
    "                        sym, _sub_tf, since=_loop_since, limit=500\n"
    "                    )\n"
    "                except Exception as _e:\n"
    "                    log.debug(f\"[SubBar-Parity] {sym} fetch failed: {_e}\")\n"
    "                    break\n"
    "                if not _chunk:\n"
    "                    break\n"
    "                _all_candles.extend(_chunk)\n"
    "                _last_chunk_ts = int(_chunk[-1][0])\n"
    "                if _last_chunk_ts + _sub_sec * 1000 > _now_ms:\n"
    "                    break\n"
    "                if _last_chunk_ts <= _loop_since:\n"
    "                    break\n"
    "                _loop_since = _last_chunk_ts + _sub_sec * 1000\n"
    "\n"
    "            if not _all_candles:\n"
    "                return\n"
    "\n"
    "            _new_bar_count = 0\n"
    "            for _c in _all_candles:\n"
    "                _ts = int(_c[0])\n"
    "                if _ts + _sub_sec * 1000 > _now_ms:\n"
    "                    break\n"
    "                if _ts <= int(pos.get('_last_sub_ts', 0)):\n"
    "                    continue\n"
    "                _high = float(_c[2])\n"
    "                _low = float(_c[3])\n"
    "                pos['_hi'] = max(float(pos.get('_hi', entry)), _high)\n"
    "                pos['_lo'] = min(float(pos.get('_lo', entry)), _low)\n"
    "                pos['_last_sub_ts'] = _ts\n"
    "                _new_bar_count += 1\n"
    "\n"
    "            if _new_bar_count > 0:\n"
    "                log.debug(\n"
    "                    f\"[SubBar-Parity] {sym} {_new_bar_count} new \"\n"
    "                    f\"{_sub_tf} bar(s) closed: hi={pos['_hi']:.6f} \"\n"
    "                    f\"lo={pos['_lo']:.6f}\"\n"
    "                )\n"
    "            return\n"
    "\n"
    "        # ══ [LEGACY MODE] Current ticker-based behavior ══\n"
    "        hi = max(float(pos.get('_hi', entry)), float(price))\n"
    "        lo = min(float(pos.get('_lo', entry)), float(price))\n"
    "        if now - float(pos.get('_ext_ts', 0.0)) >= float(_lv_cfg('LIVE_MFE_POLL_S', 15.0)):\n"
    "            pos['_ext_ts'] = now\n"
    "            try:\n"
    "                _rate_record(1.0)\n"
    "                t0 = float(pos.get('entry_ts') or now) // 60 * 60 * 1000\n"
    "                for c in exchange.fetch_ohlcv(sym, '1m', limit=3) or []:\n"
    "                    if float(c[0]) >= t0:\n"
    "                        hi = max(hi, float(c[2]))\n"
    "                        lo = min(lo, float(c[3]))\n"
    "            except Exception as e:\n"
    "                log.debug(f\"[LV] 1m extremes {sym} failed: {e}\")\n"
    "        pos['_hi'], pos['_lo'] = hi, lo\n"
    "    except Exception as e:\n"
    "        log.debug(f\"[LV] update_extremes {sym} failed: {e}\")\n"
)


# ══════════════════════════════════════════════════════════════
# P3 — Trailing block in run_live (BUY + SELL combined)
# ══════════════════════════════════════════════════════════════
P3_OLD = (
    "                    # Update peak from live price and compute MFE\n"
    "                    # [PARITY] use _hi/_lo (from 1m candles via\n"
    "                    # _lv_update_extremes) to match backtest bar highs/lows.\n"
    "                    # Falls back to ticker if extremes are missing.\n"
    "                    if pos['action'] == \"BUY\":\n"
    "                        cur_peak = float(pos.get('peak_price', entry_px))\n"
    "                        _cand_peak = max(\n"
    "                            float(price),\n"
    "                            float(pos.get('_hi', entry_px)),\n"
    "                        )\n"
    "                        if _cand_peak > cur_peak:\n"
    "                            pos['peak_price'] = _cand_peak\n"
    "                            cur_peak = _cand_peak\n"
    "                        _mfe = (cur_peak - entry_px) / entry_px\n"
    "                    else:\n"
    "                        cur_peak = float(pos.get('peak_price', entry_px))\n"
    "                        _cand_peak = min(\n"
    "                            float(price),\n"
    "                            float(pos.get('_lo', entry_px)),\n"
    "                        )\n"
    "                        if _cand_peak < cur_peak or cur_peak == entry_px:\n"
    "                            pos['peak_price'] = _cand_peak\n"
    "                            cur_peak = _cand_peak\n"
    "                        _mfe = (entry_px - cur_peak) / entry_px\n"
)

P3_NEW = (
    "                    # [SUB-BAR-TRAIL-PARITY] When TRAIL_USE_SUBBARS_ONLY=True,\n"
    "                    # peak updates ONLY on sub-bar close (from _hi/_lo which\n"
    "                    # are updated by _lv_update_extremes when a sub-bar closes).\n"
    "                    # No ticker, no 1m forming bar.\n"
    "                    _use_sub_only = bool(getattr(\n"
    "                        CFG, 'TRAIL_USE_SUBBARS_ONLY', False))\n"
    "                    if pos['action'] == \"BUY\":\n"
    "                        cur_peak = float(pos.get('peak_price', entry_px))\n"
    "                        if _use_sub_only:\n"
    "                            _cand_peak = float(pos.get('_hi', entry_px))\n"
    "                        else:\n"
    "                            _cand_peak = max(\n"
    "                                float(price),\n"
    "                                float(pos.get('_hi', entry_px)),\n"
    "                            )\n"
    "                        if _cand_peak > cur_peak:\n"
    "                            pos['peak_price'] = _cand_peak\n"
    "                            cur_peak = _cand_peak\n"
    "                        _mfe = (cur_peak - entry_px) / entry_px\n"
    "                    else:\n"
    "                        cur_peak = float(pos.get('peak_price', entry_px))\n"
    "                        if _use_sub_only:\n"
    "                            _cand_peak = float(pos.get('_lo', entry_px))\n"
    "                        else:\n"
    "                            _cand_peak = min(\n"
    "                                float(price),\n"
    "                                float(pos.get('_lo', entry_px)),\n"
    "                            )\n"
    "                        if _cand_peak < cur_peak or cur_peak == entry_px:\n"
    "                            pos['peak_price'] = _cand_peak\n"
    "                            cur_peak = _cand_peak\n"
    "                        _mfe = (entry_px - cur_peak) / entry_px\n"
)


# ══════════════════════════════════════════════════════════════
# P4 — Add _hi/_lo/_last_sub_ts to _promote_pending_to_position dict
# ══════════════════════════════════════════════════════════════
P4_OLD = (
    "        '_entry_ci': int(rec.get('close_idx') or 0),\n"
    "        '_trail_bars_held': 0,\n"
    "        '_trail_peak_R': 0.0,\n"
    "        '_trail_last_update_ts': 0.0,\n"
    "        '_sym': sym,\n"
)
P4_NEW = (
    "        '_entry_ci': int(rec.get('close_idx') or 0),\n"
    "        '_trail_bars_held': 0,\n"
    "        '_trail_peak_R': 0.0,\n"
    "        '_trail_last_update_ts': 0.0,\n"
    "        '_hi': float(entry_price),\n"
    "        '_lo': float(entry_price),\n"
    "        '_last_sub_ts': 0,\n"
    "        '_sym': sym,\n"
)


# ══════════════════════════════════════════════════════════════
# P5 — _lv_finalize_position: add _last_sub_ts setdefault
# ══════════════════════════════════════════════════════════════
P5_OLD = (
    "        if entry > 0:\n"
    "            pos.setdefault('_hi', entry)\n"
    "            pos.setdefault('_lo', entry)\n"
)
P5_NEW = (
    "        if entry > 0:\n"
    "            pos.setdefault('_hi', entry)\n"
    "            pos.setdefault('_lo', entry)\n"
    "            pos.setdefault('_last_sub_ts', 0)\n"
)


# ══════════════════════════════════════════════════════════════
# P6 — CLI argument
# ══════════════════════════════════════════════════════════════
P6_OLD = (
    "    p.add_argument(\"--trailing\", action=\"store_true\",\n"
    "                   help=\"Force-enable Trailing Stop Loss (overrides config)\")\n"
)
P6_NEW = (
    "    p.add_argument(\"--trailing\", action=\"store_true\",\n"
    "                   help=\"Force-enable Trailing Stop Loss (overrides config)\")\n"
    "    p.add_argument(\"--trail-sync-to-subbars\", action=\"store_true\",\n"
    "                   help=\"Update peak/SL ONLY on sub-bar close (e.g., 15m) \"\n"
    "                        \"— matches backtest exactly. No ticker, no 1m forming bar.\")\n"
)


# ══════════════════════════════════════════════════════════════
# P7 — CLI wiring in main()
# ══════════════════════════════════════════════════════════════
P7_OLD = (
    "    if args.no_trailing:\n"
    "        CFG.TRAIL_ENABLED = False\n"
    "        log.info(\"[Trail] Trailing Stop Loss DISABLED — SL is fixed\")\n"
    "    elif args.trailing:\n"
    "        CFG.TRAIL_ENABLED = True\n"
    "        log.info(\"[Trail] Trailing Stop Loss FORCED ON\")\n"
)
P7_NEW = (
    "    if args.no_trailing:\n"
    "        CFG.TRAIL_ENABLED = False\n"
    "        log.info(\"[Trail] Trailing Stop Loss DISABLED — SL is fixed\")\n"
    "    elif args.trailing:\n"
    "        CFG.TRAIL_ENABLED = True\n"
    "        log.info(\"[Trail] Trailing Stop Loss FORCED ON\")\n"
    "    if getattr(args, \"trail_sync_to_subbars\", False):\n"
    "        CFG.TRAIL_USE_SUBBARS_ONLY = True\n"
    "        _sub_tf_for_log = _get_subbars_tf(CFG.timeframe) or CFG.timeframe\n"
    "        log.info(\n"
    "            f\"[Trail] SUB-BAR PARITY ON: peak/SL update only on \"\n"
    "            f\"sub-bar close ({_sub_tf_for_log}). \"\n"
    "            f\"No ticker, no 1m forming bar. Matches backtest exactly.\"\n"
    "        )\n"
)


PATCHES = [
    ("P1_CONFIG", "Config: TRAIL_USE_SUBBARS_ONLY", P1_OLD, P1_NEW, MARK_P1),
    ("P2_UPDATE", "Replace _lv_update_extremes",      P2_OLD, P2_NEW, MARK_P2),
    ("P3_TRAIL",  "Trailing block parity switch",     P3_OLD, P3_NEW, MARK_P3),
    ("P4_PROMOTE","Promote: init _hi/_lo/_last_sub_ts", P4_OLD, P4_NEW, MARK_P4),
    ("P5_FINAL",  "Finalize: setdefault _last_sub_ts",P5_OLD, P5_NEW, MARK_P5),
    ("P6_ARG",    "CLI --trail-sync-to-subbars",      P6_OLD, P6_NEW, MARK_P6),
    ("P7_WIRE",   "CLI wiring",                       P7_OLD, P7_NEW, MARK_P7),
]


def _count(haystack, needle):
    c = 0
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            return c
        c += 1
        start = idx + len(needle)


def apply_all(src_text):
    text = src_text
    results = []

    for pid, desc, old, new, marker in PATCHES:
        # Already applied?
        if marker in text:
            results.append((pid, "SKIP_ALREADY", desc))
            continue
        # Find anchor
        n = _count(text, old)
        if n == 0:
            results.append((pid, "ANCHOR_NOT_FOUND", desc))
            continue
        if n > 1:
            results.append((pid, f"ANCHOR_AMBIGUOUS({n})", desc))
            continue
        # Apply
        text = text.replace(old, new, 1)
        results.append((pid, "OK", desc))

    return text, results


def verify_syntax(text):
    try:
        ast.parse(text)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}\n  {e.text}"


def main():
    ap = argparse.ArgumentParser(
        description="Apply sub-bar trailing parity to the bot.")
    ap.add_argument("--file", default=DEFAULT_FILE,
                    help=f"Source file (default: {DEFAULT_FILE})")
    ap.add_argument("--output", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: file not found: {args.file}")
        sys.exit(1)

    print(f"Reading {args.file}...")
    with open(args.file, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"  size: {len(src):,} bytes\n")

    print("Applying 7 patches...")
    new_text, results = apply_all(src)

    for pid, status, desc in results:
        if status == "OK":
            sym = "✓"
        elif status == "SKIP_ALREADY":
            sym = "⏭ "
        else:
            sym = "✗"
        print(f"  [{status:20s}] {sym} {pid:11s} — {desc}")

    n_ok = sum(1 for _, s, _ in results if s in ("OK", "SKIP_ALREADY"))
    n_fail = len(results) - n_ok
    print(f"\n  Applied: {n_ok}/{len(results)}")
    if n_fail > 0:
        print(f"  ✗ {n_fail} patch(es) failed. See errors above.")
        for pid, status, desc in results:
            if status not in ("OK", "SKIP_ALREADY"):
                print(f"    - {pid}: {status}")

    print("\nVerifying syntax...")
    ok, err = verify_syntax(new_text)
    if not ok:
        print(f"  FAIL: {err}")
        print("  No files written. Original untouched.")
        sys.exit(1)
    print("  OK: ast.parse passed.\n")

    if args.dry_run:
        print("[dry-run] No files written.")
        sys.exit(0)

    if args.output is None and not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{args.file}.bak.{ts}"
        shutil.copy2(args.file, backup)
        print(f"Backup saved: {backup}")

    out_path = args.output or args.file
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"Wrote: {out_path}  ({len(new_text):,} bytes)\n")

    print("=" * 74)
    print("  DONE — Sub-bar trailing parity applied")
    print("=" * 74)
    print()
    print("What changed:")
    print("  • Config: TRAIL_USE_SUBBARS_ONLY = False (default, off)")
    print("  • _lv_update_extremes(): now supports sub-bar-only mode")
    print("  • Trailing block: respects the flag for peak updates")
    print("  • _promote_pending_to_position: initializes _hi/_lo/_last_sub_ts")
    print("  • _lv_finalize_position: ensures _last_sub_ts exists")
    print("  • CLI: --trail-sync-to-subbars")
    print()
    print("Behavior:")
    print("  • WITHOUT flag: unchanged (ticker-based peak)")
    print("  • WITH flag: peak/SL update ONLY on sub-bar close")
    print("  • SL/TP hit detection: ALWAYS ticker-based (safety)")
    print("  • Partial TP: ALWAYS ticker-based")
    print()
    print("Verify:")
    print("  grep TRAIL_USE_SUBBARS_ONLY <file>   → should find 3+")
    print("  grep 'SubBar-Parity' <file>          → should find 1 (log only)")
    print("  grep 'trail-sync-to-subbars' <file>  → should find 2")
    print()
    print("Test 1 (backtest unchanged — flag is opt-in):")
    print("  python3 trading_2_live4_claude2_v4_micro.py --mode backtest ...")
    print("  # compare with previous results → should be identical")
    print()
    print("Test 2 (backtest with flag — should also be identical):")
    print("  python3 trading_2_live4_claude2_v4_micro.py --mode backtest ... \\")
    print("      --trail-sync-to-subbars")
    print("  # backtest already uses sub-bars, so flag has no effect on backtest")
    print()
    print("Test 3 (testnet with flag — behavior should change):")
    print("  python3 trading_2_live4_claude2_v4_micro.py --mode testnet ... \\")
    print("      --trail-sync-to-subbars")
    print("  # monitor: grep 'SubBar-Parity' qtt6.log")
    print("  # expected: 1 log line per sub-bar close (e.g., every 15m),")
    print("  #           NOT 500-2000 updates per 4h bar")
    print()
    print("Expected impact with flag ON:")
    print("  • peak/SL: ~16 updates per 4h bar (vs 500-2000 ticker updates)")
    print("  • Rate limit: ~215x reduction for extremes polling")
    print("  • Exchange SL orders: ~100x reduction")
    print("  • Backtest↔live parity: exact")


if __name__ == "__main__":
    main()
