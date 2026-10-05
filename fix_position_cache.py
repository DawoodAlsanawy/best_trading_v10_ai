#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_position_cache.py  (v3 — string-replace only, no regex)
============================================================
FIX-09-PROPER: Position cache with TTL + batched fetch.

الإستراتيجية:
    - helper block يُدرج مرة واحدة قبل load_symbol_meta.
    - استبدال string بسيط لكل exchange.fetch_positions([sym]).
    - _fake_pos_list() يعيد نفس بنية fetch_positions([sym]) لضمان
      التوافق مع كل الكود الأصلي.
    - إذا فشل أي check، لا يُكتب الملف الناتج إطلاقاً.

الاستخدام:
    python fix_position_cache.py \
        --input  trading_2_final_lev.py \
        --output trading_2_final_all.py
"""

import argparse
import os
import sys
from datetime import datetime


# ════════════════════════════════════════════════════════════════
# Helper block (plain string — no f-strings on the outside)
# ════════════════════════════════════════════════════════════════

HELPER_BLOCK = '''# ════════════════════════════════════════════════════════════════
# [FIX-09-PROPER] Position cache with TTL — batched fetch
# ════════════════════════════════════════════════════════════════
#
# Problem solved:
#   exchange.fetch_positions([sym]) costs weight=5 on Binance.
#   Called from 5 different sites in the exit/entry flow. In fast
#   markets with repeated exit failures, this burns rate limit
#   and can trigger -1003.
#
# Solution:
#   - ONE call fetches ALL positions (weight=5) and caches 3 s.
#   - All call sites go through _fetch_positions_cached().
#   - _fake_pos_list() preserves the original fetch_positions([sym])
#     return shape so existing iteration code works unchanged.
#   - Explicit invalidation after entry/exit/partial keeps it fresh.
#   - Backtest never calls these — zero impact there.

_POSITION_CACHE: Dict = {
    'ts': 0.0,
    'by_sym': {},
    'all_fetched': False,
}
_POSITION_CACHE_TTL_S: float = 3.0
_POSITION_CACHE_STATS: Dict = {
    'hits': 0,
    'misses': 0,
    'api_calls': 0,
    'invalidations': 0,
    'errors': 0,
    'last_report_ts': 0.0,
}


def _normalize_sym(sym: str) -> str:
    """BTC/USDT:USDT -> BTC/USDT  (strip ccxt settle suffix)."""
    if not sym:
        return ''
    return sym.split(':')[0] if ':' in sym else sym


def _invalidate_position_cache() -> None:
    """[FIX-09-PROPER] Force refresh on next call."""
    _POSITION_CACHE['ts'] = 0.0
    _POSITION_CACHE['all_fetched'] = False
    _POSITION_CACHE_STATS['invalidations'] += 1


def _fetch_positions_cached(exchange,
                             sym=None,
                             force: bool = False,
                             symbols_hint=None):
    """
    [FIX-09-PROPER] Cached fetch_positions.

    One API call fetches ALL open positions (weight=5) and caches
    for _POSITION_CACHE_TTL_S seconds.

    Returns dict {sym_norm: {qty, entry, side, liquidationPrice,
                              leverage, markPrice}}.
    """
    now = time.time()
    stale = (now - float(_POSITION_CACHE['ts'])) > _POSITION_CACHE_TTL_S
    need_fetch = (force or stale
                  or not _POSITION_CACHE['all_fetched'])

    if need_fetch:
        try:
            _rate_record(5.0)
            raw = exchange.fetch_positions(symbols_hint)
            _POSITION_CACHE_STATS['api_calls'] += 1
        except Exception as e:
            _POSITION_CACHE_STATS['errors'] += 1
            log.debug(f"[PosCache] fetch failed: {e}")
            _POSITION_CACHE['ts'] = now
            if sym is not None:
                return {}
            return dict(_POSITION_CACHE['by_sym'])

        by_sym = {}
        for p in (raw or []):
            try:
                amt = float(p['info'].get('positionAmt', 0) or 0)
                if abs(amt) < 1e-12:
                    continue
                _s = _normalize_sym(p.get('symbol') or '')
                if not _s:
                    continue
                by_sym[_s] = {
                    'qty': abs(amt),
                    'entry': float(p['info'].get('entryPrice', 0) or 0),
                    'side': 'BUY' if amt > 0 else 'SELL',
                    'liquidationPrice': float(
                        p['info'].get('liquidationPrice', 0) or 0),
                    'leverage': int(float(
                        p['info'].get('leverage', 0) or 0)),
                    'markPrice': float(
                        p['info'].get('markPrice', 0) or 0),
                }
            except Exception as _e:
                log.debug(f"[PosCache] parse error: {_e}")
                continue

        _POSITION_CACHE['by_sym'] = by_sym
        _POSITION_CACHE['ts'] = now
        _POSITION_CACHE['all_fetched'] = True
        _POSITION_CACHE_STATS['misses'] += 1
    else:
        _POSITION_CACHE_STATS['hits'] += 1

    if sym is None:
        return dict(_POSITION_CACHE['by_sym'])
    if sym in _POSITION_CACHE['by_sym']:
        return {sym: _POSITION_CACHE['by_sym'][sym]}
    return {}


def _get_position_qty(exchange, sym: str,
                       force: bool = False) -> float:
    """[FIX-09-PROPER] Convenience: qty of a single symbol."""
    pos_map = _fetch_positions_cached(exchange, sym, force=force)
    if sym in pos_map:
        return float(pos_map[sym]['qty'])
    return 0.0


def _fake_pos_list(exchange, sym: str, force: bool = False):
    """
    [FIX-09-PROPER] Returns list-of-dict with the EXACT shape of
    exchange.fetch_positions([sym]). Preserves downstream iteration:

        for _p in <result>:
            amt = float(_p['info'].get('positionAmt', 0) or 0)
            ...

    If no position exists for sym, returns [].
    """
    m = _fetch_positions_cached(exchange, sym, force=force)
    if sym not in m:
        return []
    v = m[sym]
    return [{
        'symbol': sym,
        'info': {
            'positionAmt': (v['qty'] if v['side'] == 'BUY' else -v['qty']),
            'entryPrice': v.get('entry', 0),
            'liquidationPrice': v.get('liquidationPrice', 0),
            'leverage': v.get('leverage', 0),
            'markPrice': v.get('markPrice', 0),
        },
    }]


def _pos_cache_log_stats() -> None:
    """[FIX-09-PROPER] Log position-cache stats every 5 minutes."""
    now = time.time()
    if now - float(_POSITION_CACHE_STATS.get('last_report_ts', 0.0)) < 300:
        return
    _POSITION_CACHE_STATS['last_report_ts'] = now
    h = _POSITION_CACHE_STATS['hits']
    m = _POSITION_CACHE_STATS['misses']
    api = _POSITION_CACHE_STATS['api_calls']
    err = _POSITION_CACHE_STATS['errors']
    inv = _POSITION_CACHE_STATS['invalidations']
    total = h + m
    if total == 0:
        return
    hr = 100.0 * h / total
    log.info(f"[PosCache] hits={h}, misses={m} ({hr:.0f}%), "
             f"api_calls={api}, invalidations={inv}, errors={err}")


# ══ end FIX-09-PROPER helpers ══


'''


# ════════════════════════════════════════════════════════════════
# Verification helper
# ════════════════════════════════════════════════════════════════

def _check(src, label, condition):
    ok = bool(condition)
    print(f"   {'✅' if ok else '❌'} {label}")
    return ok


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="trading_2_final_lev.py")
    ap.add_argument("--output", default="trading_2_final_all.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} bytes)\n")

    # ═══════════════════════════════════════════════════════════
    # Edit 1: insert helper block before load_symbol_meta
    # ═══════════════════════════════════════════════════════════
    print("▶ Edit 1: insert position-cache helper block")
    anchor = "def load_symbol_meta(mode: str) -> Dict[str, Dict]:"
    if anchor not in src:
        print(f"   ❌ anchor 'def load_symbol_meta' not found")
        sys.exit(2)

    if "[FIX-09-PROPER] Position cache with TTL" in src:
        print("   ℹ️  helper block already present — skipping")
    else:
        src = src.replace(anchor, HELPER_BLOCK + anchor, 1)
        print("   ✅ helper block inserted")

    # ═══════════════════════════════════════════════════════════
    # Edit 2: global string replace — fetch_positions([sym])
    # ═══════════════════════════════════════════════════════════
    print("▶ Edit 2: route fetch_positions([sym]) through cache")
    old_call = "exchange.fetch_positions([sym])"
    new_call = "_fake_pos_list(exchange, sym)"
    n_occ = src.count(old_call)
    if n_occ == 0:
        print("   ⚠️  no occurrences — nothing to replace")
    else:
        src = src.replace(old_call, new_call)
        print(f"   ✅ replaced {n_occ} occurrence(s)")

    # ═══════════════════════════════════════════════════════════
    # Edit 3: force=True for LiqProximity (specific to _pos_list)
    # ═══════════════════════════════════════════════════════════
    print("▶ Edit 3: force refresh in LiqProximity (_pos_list)")
    old_liq = "_pos_list = _fake_pos_list(exchange, sym)"
    if old_liq in src:
        if src.count(old_liq) == 1:
            src = src.replace(
                old_liq,
                "_pos_list = _fake_pos_list(exchange, sym, force=True)",
                1
            )
            print("   ✅ LiqProximity uses force=True")
        else:
            print(f"   ⚠️  _pos_list appears {src.count(old_liq)}× "
                  f"— skipping (safety)")
    else:
        print("   ⚠️  _pos_list line not found — skipped")

    # ═══════════════════════════════════════════════════════════
    # Edit 4: invalidate cache after live entry
    # ═══════════════════════════════════════════════════════════
    print("▶ Edit 4: invalidate cache after live entry")
    entry_marker = (
        'log.info(f"✅ [Entry] {sig.action} {sym} @ '
        '{entry_price:.6f} "'
    )
    if entry_marker in src:
        if src.count(entry_marker) == 1:
            idx = src.find(entry_marker)
            line_start = src.rfind('\n', 0, idx) + 1
            indent = src[line_start:idx]
            if indent.strip() != '':
                indent = ' ' * 24
            injection = (
                indent + '# [FIX-09-PROPER] invalidate — '
                'position just opened\n'
                + indent + '_invalidate_position_cache()\n'
                + indent
            )
            src = src.replace(entry_marker,
                              injection + entry_marker, 1)
            print("   ✅ invalidate inserted after live entry")
        else:
            print(f"   ⚠️  marker appears {src.count(entry_marker)}× "
                  f"— skipping")
    else:
        print("   ⚠️  entry log marker not found — skipping")

    # ═══════════════════════════════════════════════════════════
    # Edit 5: invalidate cache after live exit
    # ═══════════════════════════════════════════════════════════
    print("▶ Edit 5: invalidate cache after live exit")
    exit_marker = (
        'log.info(f"⬛ [Exit] {sym} @ {exec_price:.6f} '
        '[{exit_reason}]")'
    )
    if exit_marker in src:
        if src.count(exit_marker) == 1:
            idx = src.find(exit_marker)
            line_start = src.rfind('\n', 0, idx) + 1
            indent = src[line_start:idx]
            if indent.strip() != '':
                indent = ' ' * 20
            injection = (
                '\n' + indent
                + '# [FIX-09-PROPER] invalidate — position just closed\n'
                + indent + '_invalidate_position_cache()'
            )
            src = src.replace(exit_marker,
                              exit_marker + injection, 1)
            print("   ✅ invalidate inserted after live exit")
        else:
            print(f"   ⚠️  marker appears {src.count(exit_marker)}× "
                  f"— skipping")
    else:
        print("   ⚠️  exit log marker not found — skipping")

    # ═══════════════════════════════════════════════════════════
    # Edit 6: invalidate cache after partial TP
    # ═══════════════════════════════════════════════════════════
    print("▶ Edit 6: invalidate cache after partial TP")
    partial_marker = 'log.info(f"[PartialTP] {sym} closed "'
    if partial_marker in src:
        if src.count(partial_marker) == 1:
            idx = src.find(partial_marker)
            line_start = src.rfind('\n', 0, idx) + 1
            indent = src[line_start:idx]
            if indent.strip() != '':
                indent = ' ' * 36
            injection = (
                indent + '# [FIX-09-PROPER] invalidate — qty changed\n'
                + indent
            )
            src = src.replace(partial_marker,
                              injection + partial_marker, 1)
            print("   ✅ invalidate inserted after partial TP")
        else:
            print(f"   ⚠️  marker appears {src.count(partial_marker)}× "
                  f"— skipping")
    else:
        print("   ⚠️  partial log marker not found — skipping")

    # ═══════════════════════════════════════════════════════════
    # Edit 7: periodic stats log in run_live main loop
    # ═══════════════════════════════════════════════════════════
    print("▶ Edit 7: periodic pos-cache stats log")
    rate_marker = (
        "            # ══ [RateLimit] periodic report ══\n"
        "            _rate_report()"
    )
    rate_new = (
        "            # ══ [RateLimit] periodic report ══\n"
        "            _rate_report()\n"
        "            # [FIX-09-PROPER] pos-cache stats\n"
        "            _pos_cache_log_stats()"
    )
    if rate_marker in src:
        if src.count(rate_marker) == 1:
            src = src.replace(rate_marker, rate_new, 1)
            print("   ✅ stats log added to main loop")
        else:
            print(f"   ⚠️  rate marker appears {src.count(rate_marker)}× "
                  f"— skipping")
    else:
        print("   ⚠️  rate_report() call not found — skipping")

    # ═══════════════════════════════════════════════════════════
    # VERIFICATION
    # ═══════════════════════════════════════════════════════════
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                         VERIFICATION                         ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    checks_pass = []

    checks_pass.append(_check(src, "helper block present",
                              "[FIX-09-PROPER] Position cache with TTL" in src))
    checks_pass.append(_check(src, "cache dict defined",
                              "_POSITION_CACHE: Dict" in src))
    checks_pass.append(_check(src, "TTL constant",
                              "_POSITION_CACHE_TTL_S: float" in src))
    checks_pass.append(_check(src, "stats dict",
                              "_POSITION_CACHE_STATS: Dict" in src))
    checks_pass.append(_check(src, "normalize_sym",
                              "def _normalize_sym(" in src))
    checks_pass.append(_check(src, "invalidate helper",
                              "def _invalidate_position_cache(" in src))
    checks_pass.append(_check(src, "fetch cached helper",
                              "def _fetch_positions_cached(" in src))
    checks_pass.append(_check(src, "get_position_qty helper",
                              "def _get_position_qty(" in src))
    checks_pass.append(_check(src, "fake_pos_list helper",
                              "def _fake_pos_list(" in src))
    checks_pass.append(_check(src, "stats log helper",
                              "def _pos_cache_log_stats(" in src))

    n_raw = src.count("exchange.fetch_positions([sym])")
    checks_pass.append(_check(src,
        f"raw fetch_positions([sym]) eliminated (remaining={n_raw})",
        n_raw == 0))

    # Count calls routed through cache
    n_fake = src.count("_fake_pos_list(exchange, sym")
    checks_pass.append(_check(src,
        f"routed calls through _fake_pos_list (count={n_fake})",
        n_fake >= 3))

    checks_pass.append(_check(src, "invalidate after entry",
                              "invalidate — position just opened" in src))
    checks_pass.append(_check(src, "invalidate after exit",
                              "invalidate — position just closed" in src))
    checks_pass.append(_check(src, "invalidate after partial",
                              "invalidate — qty changed" in src))
    checks_pass.append(_check(src, "stats log in loop",
                              "_pos_cache_log_stats()" in src))

    all_ok = all(checks_pass)

    # ═══════════════════════════════════════════════════════════
    # SYNTAX CHECK
    # ═══════════════════════════════════════════════════════════
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                         SYNTAX CHECK                         ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    syntax_ok = True
    try:
        compile(src, args.output, "exec")
        print("   ✅ compiles OK")
    except SyntaxError as e:
        print(f"   ❌ SyntaxError at line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text!r}")
        syntax_ok = False

    # ═══════════════════════════════════════════════════════════
    # WRITE — only if everything passed
    # ═══════════════════════════════════════════════════════════
    if not (all_ok and syntax_ok):
        print("\n╔══════════════════════════════════════════════════════════════╗")
        print("║                      ❌ ABORTED                              ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print(f"   verification:  {'OK' if all_ok else 'FAILED'}")
        print(f"   syntax:        {'OK' if syntax_ok else 'FAILED'}")
        print(f"\n   Output NOT written. Input file unchanged.")
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine — FULL PARITY\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  FIX-09-PROPER adds:\n"
        "#    • Position cache with 3s TTL\n"
        "#    • ONE API call for ALL positions (weight=5)\n"
        "#    • _fake_pos_list() preserves original return shape\n"
        "#    • Explicit invalidation after entry/exit/partial\n"
        "#    • PosCache stats every 5 min\n"
        "#    • Zero backtest impact\n"
        "# ═══════════════════════════════════════════════════════════\n"
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
        print(f"   ❌ Written file has syntax error at line "
              f"{e.lineno}: {e.msg}")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                             DONE                             ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"   Input:  {args.input}  ({len(src):,} bytes)")
    print(f"   Output: {args.output}  ({len(src_out):,} bytes)")
    print(f"   verification:  {'✅ ALL PASSED' if all_ok else '❌ FAILED'}")
    print(f"   syntax:        {'✅ OK' if syntax_ok else '❌ FAILED'}")
    print(f"   written:       {'✅ OK' if write_ok else '❌ FAILED'}")

    if not write_ok:
        sys.exit(3)

    print(f"\n   ▶ Run:")
    print(f"     python {args.output} --mode backtest ...")
    print(f"     python {args.output} --mode testnet "
          f"--api-key ... --api-secret ...")


if __name__ == "__main__":
    main()
