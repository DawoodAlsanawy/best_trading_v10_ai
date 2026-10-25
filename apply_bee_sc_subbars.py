#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_bee_sc_subbars.py — BEEsc Sub-Bar Upgrade
================================================
يُطوّر BEEsc ليعمل على sub-bars (15m) بدلاً من انتظار إغلاق الشمعة الرئيسية (4h).

يُطبّق:
  1. Config: BE_ESC_SUBBARS_ENABLED, BE_ESC_PERSIST_BARS,
            BE_ESC_ORDERBOOK_ENABLED, BE_ESC_ORDERBOOK_IMBALANCE_THR
  2. دالة `_should_breakeven_escape_subbars` — persistence wrapper
  3. دالة `_be_esc_orderbook_check` — live-only opt-in filter
  4. `_advance` sub-bar loop — BEEsc على كل sub-bar مع persistence
  5. `run_live` — BEEsc على sub-bars (fetched once per sub-bar close)
  6. CLI flags: --be-esc-subbars, --be-esc-persist, --be-esc-orderbook
  7. argparse handling

الفلسفة:
  • Parity-safe: sub-bar BEEsc يستخدم بيانات محلية في backtest
    و sub-bar closes في live — كلاهما من نفس الـ timeframe (15m)
  • Order book filter اختياري — delay-only، لا يُسرّع (اتجاه آمن)
  • Default OFF — user opt-in فقط

الاستخدام:
  python3 apply_bee_sc_subbars.py --dry-run --verbose
  python3 apply_bee_sc_subbars.py

  ثم في التشغيل:
  --be-esc-subbars                    # تفعيل
  --be-esc-persist 2                  # sub-bars مطلوبة (default 2)
  --be-esc-orderbook                  # [LIVE] order book filter (opt-in)
"""

import ast, os, shutil, sys
from datetime import datetime

MARKER = "# [BEESC-SUBBARS-UPGRADE-APPLIED]"
DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"
VERBOSE = False


def log(msg, level="INFO"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def vlog(msg):
    if VERBOSE:
        log(msg, "DEBUG")


def fail(msg):
    log(msg, "FAIL")
    raise SystemExit(1)


def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_bee_sc_{ts}"
    shutil.copy2(path, bak)
    log(f"  نسخة احتياطية: {bak}")
    return bak


def verify_syntax(content, label=""):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        ctx = ""
        if e.lineno:
            lines = content.split("\n")
            lo, hi = max(0, e.lineno - 9), min(len(lines), e.lineno + 8)
            ctx = f"\n{label} Context:\n"
            for i in range(lo, hi):
                m = ">>> " if i == e.lineno - 1 else "    "
                ctx += f"{m}{i+1:6d}: {lines[i]}\n"
        return False, f"line {e.lineno}: {e.msg}\n{ctx}"


def must_replace(content, old, new, label):
    n = content.count(old)
    if n == 0:
        fail(f"[{label}] anchor not found")
    if n > 1:
        fail(f"[{label}] ambiguous ({n} matches)")
    vlog(f"    [{label}] replaced")
    return content.replace(old, new, 1)


def must_insert_before(content, anchor, block, label):
    idx = content.find(anchor)
    if idx < 0:
        fail(f"[{label}] anchor not found")
    if content.count(anchor) > 1:
        fail(f"[{label}] anchor ambiguous ({content.count(anchor)})")
    vlog(f"    [{label}] inserted ({len(block)} chars)")
    return content[:idx] + block + content[idx:]


# ═══════════════════════════════════════════════════════════════
# CODE BLOCKS
# ═══════════════════════════════════════════════════════════════

CONFIG_BLOCK = '''    # ══ [BEEsc Sub-Bar Mode] ══
    # Opt-in sub-bar BEEsc: trigger on sub-bar (e.g. 15m) closes with
    # persistence filter, instead of waiting for main bar (e.g. 4h) close.
    # Parity-safe: both backtest and live use the same sub-bar timeframe.
    BE_ESC_SUBBARS_ENABLED: bool = False       # master switch (opt-in)
    BE_ESC_PERSIST_BARS: int = 2                # consecutive sub-bars required
    BE_ESC_ORDERBOOK_ENABLED: bool = False      # [LIVE ONLY] order book filter
    BE_ESC_ORDERBOOK_IMBALANCE_THR: float = 0.30  # bid/ask imbalance threshold
'''

FUNCTIONS_BLOCK = r'''

def _should_breakeven_escape_subbars(ad, main_ci, sub_closes_arr,
                                       action, entry, sl_dist0, sig_opp=None):
    """
    [BEEsc-SubBar] Check BEEsc across N consecutive sub-bar closes.

    Parameters
    ----------
    ad : AssetData
    main_ci : int
        Main bar index (for EMA lookup in _should_breakeven_escape)
    sub_closes_arr : array-like
        Sequence of sub-bar closes (most recent last)
    action, entry, sl_dist0 : position parameters
    sig_opp : optional opposite signal

    Returns
    -------
    (triggered: bool, reason: str, last_idx: int)
        last_idx = -1 if not triggered.
    """
    if not getattr(CFG, 'BE_ESC_SUBBARS_ENABLED', False):
        return False, "subbars_disabled", -1
    if not getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False):
        return False, "be_escape_disabled", -1
    if ad is None or main_ci < 0 or entry <= 0 or sl_dist0 <= 0:
        return False, "invalid_inputs", -1

    persist = max(1, int(getattr(CFG, 'BE_ESC_PERSIST_BARS', 2)))
    n = len(sub_closes_arr)
    if n < persist:
        return False, f"insufficient({n}<{persist})", -1

    # Require the LAST `persist` sub-bars to ALL trigger consecutively
    for j in range(n - persist, n):
        try:
            p = float(sub_closes_arr[j])
        except Exception:
            return False, f"invalid_at_{j}", -1
        if not np.isfinite(p) or p <= 0:
            return False, f"invalid_price_at_{j}", -1
        trig, rsn = _should_breakeven_escape(
            ad, main_ci, p, action, entry, sl_dist0, sig_opp
        )
        if not trig:
            return False, f"no_trigger_at_{j}({rsn})", -1

    return True, f"persist={persist}", n - 1


def _be_esc_orderbook_check(exchange, sym, action, current_price,
                              entry, sl_dist0):
    """
    [BEEsc-OrderBook] Live-only confirmation filter (opt-in).

    Delay-only philosophy: this filter can POSTPONE BEEsc but cannot
    ACCELERATE it. Ensures live never exits before backtest (safe parity).

    Returns
    -------
    (verdict, reason, imbalance) where verdict is:
      'confirm' — order book confirms adverse move -> activate BEEsc
      'hold'    — order book shows support -> delay BEEsc one sub-bar
      'neutral' — no clear signal -> activate (default behavior)
    """
    if not getattr(CFG, 'BE_ESC_ORDERBOOK_ENABLED', False):
        return 'neutral', 'ob_disabled', 0.0

    try:
        ob = exchange.fetch_order_book(sym, limit=20)
        bids = ob.get('bids') or []
        asks = ob.get('asks') or []
        if not bids or not asks:
            return 'neutral', 'ob_empty', 0.0

        bid_sz = sum(float(x[1]) for x in bids[:5])
        ask_sz = sum(float(x[1]) for x in asks[:5])
        total = bid_sz + ask_sz
        if total <= 0:
            return 'neutral', 'ob_zero_volume', 0.0

        imbalance = (bid_sz - ask_sz) / total
        thr = float(getattr(CFG, 'BE_ESC_ORDERBOOK_IMBALANCE_THR', 0.30))

        if action == "BUY":
            # BUY losing (price < entry). BEEsc wants to exit.
            # Heavy bids -> support -> HOLD (delay BEEsc)
            if imbalance > thr:
                return 'hold', f'bids_strong({imbalance:+.2f})', float(imbalance)
            # Heavy asks -> selling pressure -> CONFIRM (exit now)
            if imbalance < -thr:
                return 'confirm', f'asks_strong({imbalance:+.2f})', float(imbalance)
        else:  # SELL
            if imbalance < -thr:
                return 'hold', f'asks_strong({imbalance:+.2f})', float(imbalance)
            if imbalance > thr:
                return 'confirm', f'bids_strong({imbalance:+.2f})', float(imbalance)

        return 'neutral', f'balanced({imbalance:+.2f})', float(imbalance)
    except Exception as e:
        return 'neutral', f'error:{e}', 0.0
'''


ADVANCE_OLD = '''        if _use_sub:
            # Sub-bar iteration
            for j in range(j_start, j_end):
                s_high = ad.sub_highs[cidx, j]
                s_low = ad.sub_lows[cidx, j]
                if not np.isfinite(s_high) or not np.isfinite(s_low):
                    continue

                # MFE update from sub-bar extremes'''

ADVANCE_NEW = '''        if _use_sub:
            # Sub-bar iteration
            for j in range(j_start, j_end):
                s_high = ad.sub_highs[cidx, j]
                s_low = ad.sub_lows[cidx, j]
                s_close = (ad.sub_closes[cidx, j]
                           if ad.sub_closes is not None else np.nan)
                if not np.isfinite(s_high) or not np.isfinite(s_low):
                    continue

                # ══ [BEEsc-SubBar] early trigger on sub-bar closes ══
                if (getattr(CFG, 'BE_ESC_SUBBARS_ENABLED', False)
                        and not getattr(pos, '_be_esc_done', False)
                        and pos.sl_dist_initial > 0
                        and np.isfinite(s_close) and s_close > 0):
                    _be_persist_n = max(1, int(getattr(CFG, 'BE_ESC_PERSIST_BARS', 2)))
                    _be_seq_start = max(j_start, j - _be_persist_n + 1)
                    _be_seq_len = j - _be_seq_start + 1
                    if _be_seq_len >= _be_persist_n:
                        _be_seq = ad.sub_closes[cidx, _be_seq_start:j + 1]
                        _be_trig_sb, _be_rsn_sb, _be_idx_sb = _should_breakeven_escape_subbars(
                            ad, cidx, _be_seq, sig.action,
                            pos.entry_px, pos.sl_dist_initial, sig_opp=None
                        )
                        if _be_trig_sb:
                            _tp_old_sb = float(sig.tp1)
                            _tp_new_sb = _apply_breakeven_escape(
                                sig.action, pos.entry_px, pos.sl_dist_initial,
                                _tp_old_sb,
                                bool(getattr(pos, 'partial_taken', False))
                            )
                            if _tp_new_sb is not None:
                                sig.tp1 = _tp_new_sb
                                pos._be_esc_done = True
                                pos._be_orig_tp1 = _tp_old_sb
                                if sig.action == "BUY":
                                    pos._be_low = float(s_close)
                                else:
                                    pos._be_high = float(s_close)
                                log.debug(
                                    f"[BEEsc-SubBar-BT] {sig.symbol} {sig.action} "
                                    f"TP {_tp_old_sb:.6f}->{_tp_new_sb:.6f} "
                                    f"({_be_rsn_sb})"
                                )

                # MFE update from sub-bar extremes'''


LIVE_SUBBARS_BLOCK = '''                # ══ [BEEsc-SubBar-Live] ══ (earlier than main-bar close)
                if (getattr(CFG, 'BE_ESC_SUBBARS_ENABLED', False)
                        and not pos.get('_be_esc_done', False)
                        and float(pos.get('sl_dist_initial', 0)) > 0
                        and ad is not None):
                    try:
                        _be_sub_tf_lv = _get_subbars_tf(CFG.timeframe) or "15m"
                        try:
                            import ccxt as _ccxt_be_lv
                            _be_sub_sec_lv = int(_ccxt_be_lv.binance().parse_timeframe(_be_sub_tf_lv))
                        except Exception:
                            _be_sub_sec_lv = {"1m": 60, "5m": 300, "15m": 900,
                                              "30m": 1800, "1h": 3600}.get(_be_sub_tf_lv, 900)
                        _be_persist_lv = max(1, int(getattr(CFG, 'BE_ESC_PERSIST_BARS', 2)))
                        _be_now_ms_lv = int(time.time() * 1000)
                        _be_cur_open_lv = (_be_now_ms_lv // (_be_sub_sec_lv * 1000)) * (_be_sub_sec_lv * 1000)
                        _be_last_lv = int(pos.get('_be_last_sub_fetch_ms', 0))
                        if _be_cur_open_lv > _be_last_lv:
                            _be_since_lv = _be_cur_open_lv - (_be_persist_lv + 2) * _be_sub_sec_lv * 1000
                            _be_raw_lv = exchange.fetch_ohlcv(
                                sym, _be_sub_tf_lv, since=_be_since_lv,
                                limit=_be_persist_lv + 5
                            )
                            if _be_raw_lv:
                                _be_closed_lv = [
                                    float(c[4]) for c in _be_raw_lv
                                    if int(c[0]) + _be_sub_sec_lv * 1000 <= _be_now_ms_lv
                                ]
                                if len(_be_closed_lv) >= _be_persist_lv:
                                    _be_ci_lv = max(0, len(ad.closes) - 2)
                                    _be_trig_lv, _be_rsn_lv, _ = _should_breakeven_escape_subbars(
                                        ad, _be_ci_lv, _be_closed_lv[-_be_persist_lv:],
                                        pos['action'], float(pos['entry']),
                                        float(pos['sl_dist_initial']), sig_opp=None
                                    )
                                    if _be_trig_lv:
                                        _be_ob_ok_lv = True
                                        if getattr(CFG, 'BE_ESC_ORDERBOOK_ENABLED', False):
                                            _ob_v, _ob_r, _ = _be_esc_orderbook_check(
                                                exchange, sym, pos['action'],
                                                float(price), float(pos['entry']),
                                                float(pos['sl_dist_initial'])
                                            )
                                            if _ob_v == 'hold':
                                                _be_ob_ok_lv = False
                                                log.debug(f"[BEEsc-OB] {sym} held: {_ob_r}")
                                        if _be_ob_ok_lv:
                                            _be_sd0_lv = float(pos['sl_dist_initial'])
                                            _tp_old_lv = float(pos['tp1'])
                                            _tp_new_lv = _apply_breakeven_escape(
                                                pos['action'], float(pos['entry']),
                                                _be_sd0_lv, _tp_old_lv,
                                                bool(pos.get('_partial_taken', False))
                                            )
                                            if _tp_new_lv is not None:
                                                pos['tp1'] = _tp_new_lv
                                                pos['_be_esc_done'] = True
                                                pos['_be_orig_tp1'] = _tp_old_lv
                                                _be_last_close_lv = float(_be_closed_lv[-1])
                                                if pos['action'] == "BUY":
                                                    pos['_be_low'] = _be_last_close_lv
                                                else:
                                                    pos['_be_high'] = _be_last_close_lv
                                                log.info(
                                                    f"[BEEsc-SubBar-LV] {sym} {pos['action']} "
                                                    f"TP {_tp_old_lv:.6f}->{_tp_new_lv:.6f} "
                                                    f"({_be_rsn_lv})"
                                                )
                                                try:
                                                    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
                                                        _sync_protective_orders(exchange, sym, pos)
                                                except Exception as _e:
                                                    log.debug(f"[BEEsc-SubBar-LV] {sym} prot: {_e}")
                                                try:
                                                    _lv_save_state(state_file, open_pos_live)
                                                except Exception:
                                                    pass
                            pos['_be_last_sub_fetch_ms'] = _be_cur_open_lv
                    except Exception as _e:
                        log.debug(f"[BEEsc-SubBar-LV] {sym} error: {_e}")

'''


LIVE_ANCHOR = '''                # ══ [BREAKEVEN ESCAPE — Price Trigger — Live] ══
                if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)'''


CLI_BLOCK = '''    p.add_argument("--be-esc-subbars", action="store_true",
                   help="[BEEsc] Enable sub-bar BEEsc (e.g. 15m) with "
                        "persistence filter — faster than main-bar (4h)")
    p.add_argument("--be-esc-persist", type=int, default=None,
                   help="[BEEsc] Consecutive sub-bars required (default 2)")
    p.add_argument("--be-esc-orderbook", action="store_true",
                   help="[BEEsc] [LIVE ONLY] Use order book to confirm/hold "
                        "BEEsc — delay-only, opt-in, breaks strict parity")
'''


CLI_ANCHOR = '''    p.add_argument("--be-escape-move-r", type=float, default=None,
                   help="Adverse move in R units to trigger escape "
                        "(default 0.30)")
'''


ARGPARSE_BLOCK = '''
    if getattr(args, "be_esc_subbars", False):
        CFG.BE_ESC_SUBBARS_ENABLED = True
        log.info("[BEEsc-SubBar] ENABLED (sub-bar closes with persistence)")
    if getattr(args, "be_esc_persist", None) is not None:
        CFG.BE_ESC_PERSIST_BARS = max(1, int(args.be_esc_persist))
        log.info(f"[BEEsc-SubBar] Persistence = {CFG.BE_ESC_PERSIST_BARS} sub-bars")
    if getattr(args, "be_esc_orderbook", False):
        if CFG.mode not in ("live", "testnet"):
            log.warning("[BEEsc-OB] --be-esc-orderbook ignored in backtest "
                        "(live-only feature)")
        else:
            CFG.BE_ESC_ORDERBOOK_ENABLED = True
            log.info("[BEEsc-OB] Order book filter ENABLED "
                     "(delay-only, breaks strict parity)")
'''


ARGPARSE_ANCHOR = '''    if getattr(args, "be_escape_move_r", None) is not None:
        CFG.BREAKEVEN_ESCAPE_PRICE_MOVE_R = float(args.be_escape_move_r)
'''


# ═══════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════

def patch_01_config(content):
    if "BE_ESC_SUBBARS_ENABLED: bool = False" in content:
        log("  [config] already present — skip")
        return content
    anchor = '''    BREAKEVEN_ESCAPE_CANCEL_SR_CHECK: bool = False
    BREAKEVEN_ESCAPE_CANCEL_SR_LOOKBACK: int = 60
'''
    if anchor not in content:
        fail("[config] anchor not found")
    return must_replace(content, anchor, anchor + CONFIG_BLOCK, "config")


def patch_02_functions(content):
    if "def _should_breakeven_escape_subbars(" in content:
        log("  [functions] already present — skip")
        return content
    anchor = '''    return float(tp_new)

# ═══════════════════════════════════════════════════════════════
'''
    if anchor not in content:
        fail("[functions] anchor not found")
    replacement = '''    return float(tp_new)
''' + FUNCTIONS_BLOCK + '''
# ═══════════════════════════════════════════════════════════════
'''
    return must_replace(content, anchor, replacement, "functions")


def patch_03_advance(content):
    if "# ══ [BEEsc-SubBar] early trigger on sub-bar closes ══" in content:
        log("  [advance-subbars] already applied — skip")
        return content
    return must_replace(content, ADVANCE_OLD, ADVANCE_NEW, "advance-subbars")


def patch_04_live_subbars(content):
    if "# ══ [BEEsc-SubBar-Live] ══ (earlier than main-bar close)" in content:
        log("  [live-subbars] already applied — skip")
        return content
    return must_insert_before(content, LIVE_ANCHOR, LIVE_SUBBARS_BLOCK, "live-subbars")


def patch_05_cli_flags(content):
    if 'p.add_argument("--be-esc-subbars"' in content:
        log("  [cli-flags] already present — skip")
        return content
    return must_replace(content, CLI_ANCHOR, CLI_ANCHOR + CLI_BLOCK, "cli-flags")


def patch_06_argparse(content):
    if 'CFG.BE_ESC_SUBBARS_ENABLED = True' in content and \
       'getattr(args, "be_esc_subbars", False)' in content:
        log("  [argparse] already applied — skip")
        return content
    return must_replace(content, ARGPARSE_ANCHOR, ARGPARSE_ANCHOR + ARGPARSE_BLOCK,
                        "argparse")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=DEFAULT_TARGET)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose

    path = args.target
    if not os.path.exists(path):
        fail(f"File not found: {path}")

    content = open(path, "r", encoding="utf-8").read()

    if MARKER in content and not args.force:
        log("BEEsc sub-bar upgrade already applied. Use --force to re-apply.")
        return 0

    ok, err = verify_syntax(content, "PRE-UPGRADE")
    if not ok:
        fail(f"File has syntax errors: {err}")

    log(f"File: {path} ({len(content)} chars, {content.count(chr(10))} lines)")

    if not args.dry_run:
        backup(path)

    try:
        content = patch_01_config(content)
        content = patch_02_functions(content)
        content = patch_03_advance(content)
        content = patch_04_live_subbars(content)
        content = patch_05_cli_flags(content)
        content = patch_06_argparse(content)

        content = MARKER + "\n" + content

        ok, err = verify_syntax(content, "POST-UPGRADE")
        if not ok:
            fail(f"Result has syntax errors: {err}")

        if args.dry_run:
            log("DRY RUN: syntax OK. Would write to file.")
            return 0

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
        log(f"Saved: {path}  ({content.count(chr(10))} lines)")
        log("=" * 60)
        log("BEEsc Sub-Bar Upgrade complete.")
        log("")
        log("New flags:")
        log("  --be-esc-subbars     → enable sub-bar BEEsc (parity-safe)")
        log("  --be-esc-persist N   → consecutive sub-bars required (default 2)")
        log("  --be-esc-orderbook   → [LIVE] order book filter (delay-only, opt-in)")
        log("")
        log("Backward compatible: omitting all flags keeps original behavior.")
        log("=" * 60)
        return 0

    except SystemExit:
        raise
    except Exception as e:
        log(f"Upgrade FAILED: {e}", "FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
