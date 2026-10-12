#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch: Coil Timing (Corrected v2)
Anchors verified against real file state.
"""

import argparse
import os
import shutil
import sys
import time
from dataclasses import dataclass
from typing import List

DEFAULT_TARGET = "trading_2_live2_1.py"


def log(msg, level="INFO"):
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


# ═════════════════════════════════════════════════════════════════════
# F1 — Config fields (anchor updated: after LIVE_PARALLEL_WORKERS)
# ═════════════════════════════════════════════════════════════════════

F1_ANCHOR = '''    LIVE_PARALLEL_WORKERS: int = 4

CFG = Config()'''

F1_CONTENT = '''    LIVE_PARALLEL_WORKERS: int = 4

    # ══ [COIL-TIMING] فلتر انكماش σ_1m قبل التنفيذ ══
    # عطّله بـ False (افتراضي) أو فعّله بـ --coil-timing
    COIL_TIMING_ENABLED: bool = False
    COIL_THRESHOLD: float = 0.5
    COIL_MAX_WAIT_MIN: int = 5
    COIL_WINDOW_MIN: int = 15
    COIL_BASELINE_MIN: int = 60
    COIL_LIVE_WAIT_S: int = 90

CFG = Config()'''

F1_IDEM = "[COIL-TIMING] فلتر انكماش σ_1m قبل التنفيذ"


# ═════════════════════════════════════════════════════════════════════
# F2 — Coil functions (anchor updated: before def run_live)
# ═════════════════════════════════════════════════════════════════════

F2_ANCHOR = '''# [/LIVE-PARITY v1]



def run_live(cfg, exchange):'''

F2_CONTENT = '''# [/LIVE-PARITY v1]



# ════════════════════════════════════════════════════════════════
# § 18.99  [COIL-TIMING] Intra-bar volatility compression
# ════════════════════════════════════════════════════════════════

def _coil_ts_utc(ts):
    if ts is None:
        return None
    if hasattr(ts, 'tz') and ts.tz is None:
        return ts.tz_localize('UTC')
    return ts


def _coil_fetch_1m(exchange, sym, signal_time,
                   before_min=60, after_min=5):
    if exchange is None:
        return None
    st = _coil_ts_utc(signal_time)
    if st is None:
        return None
    try:
        since_ms = int((st - timedelta(minutes=before_min)).timestamp()
                       * 1000)
        ohlcv = exchange.fetch_ohlcv(
            sym, '1m', since=since_ms,
            limit=int(before_min + after_min + 20))
    except Exception as e:
        log.debug(f"[Coil] fetch_1m {sym} failed: {e}")
        return None
    if not ohlcv:
        return None
    df = pd.DataFrame(
        ohlcv, columns=['ts','Open','High','Low','Close','Volume'])
    df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
    df = df.set_index('ts').astype(float).sort_index()
    end_ts = st + timedelta(minutes=after_min)
    df = df[df.index <= end_ts]
    return df


def _coil_score_from_df(df, window_min=15, baseline_min=60):
    if df is None or len(df) < 20:
        return 0.0, 0.0, 0.0
    try:
        end = df.index[-1]
        w_start = end - pd.Timedelta(minutes=window_min)
        b_start = end - pd.Timedelta(minutes=baseline_min)
        w_df = df[df.index >= w_start]
        b_df = df[df.index >= b_start]
        if len(w_df) < 5 or len(b_df) < 20:
            return 0.0, 0.0, 0.0
        w_c = w_df['Close'].values.astype(np.float64)
        b_c = b_df['Close'].values.astype(np.float64)
        lr_w = np.diff(np.log(np.maximum(w_c, 1e-12)))
        lr_b = np.diff(np.log(np.maximum(b_c, 1e-12)))
        if len(lr_w) < 3 or len(lr_b) < 5:
            return 0.0, 0.0, 0.0
        s_now = float(np.std(lr_w))
        s_base = float(np.std(lr_b))
        if s_base <= 1e-9:
            return 0.0, s_now, 0.0
        score = max(0.0, min(1.0, 1.0 - s_now / s_base))
        return score, s_now, s_base
    except Exception:
        return 0.0, 0.0, 0.0


def _coil_find_moment(m1_df, signal_time, max_wait_min=5,
                      threshold=0.5, window_min=15, baseline_min=60):
    if m1_df is None or len(m1_df) < 20:
        return None
    st = _coil_ts_utc(signal_time)
    if st is None:
        return None
    end = st + timedelta(minutes=max_wait_min)
    window = m1_df[(m1_df.index >= st) & (m1_df.index <= end)]
    if len(window) == 0:
        return None
    for ts, _ in window.iterrows():
        sub = m1_df[m1_df.index <= ts]
        score, s_now, s_base = _coil_score_from_df(
            sub, window_min, baseline_min)
        if score >= threshold:
            return ts, score, s_now, s_base
    return None


def _coil_compute_target(price_at_coil, action, sigma_bar,
                          adv_usd, exchange=None, sym=None, qty=0.0):
    try:
        if price_at_coil <= 0:
            return float(price_at_coil)
        off = _watch_compute_entry_offset(
            tunnel_p=float(price_at_coil),
            sigma_bar=float(sigma_bar) if sigma_bar > 1e-6 else 0.01,
            adv_usd=float(adv_usd) if adv_usd > 0 else 1e8,
            exchange=exchange,
            symbol=sym,
            qty=qty,
        )
        if action == 'BUY':
            return float(price_at_coil - off)
        return float(price_at_coil + off)
    except Exception:
        return float(price_at_coil)


def _coil_wait_for_signal(exchange, sym, sig, ad,
                           max_wait_s=None):
    if not getattr(CFG, 'COIL_TIMING_ENABLED', False):
        return True, 0.0
    try:
        threshold = float(getattr(CFG, 'COIL_THRESHOLD', 0.5))
        window_min = int(getattr(CFG, 'COIL_WINDOW_MIN', 15))
        baseline_min = int(getattr(CFG, 'COIL_BASELINE_MIN', 60))
        wait_s = int(max_wait_s or getattr(CFG, 'COIL_LIVE_WAIT_S', 90))
        poll_s = 8

        log.info(f"[Coil] {sym} waiting up to {wait_s}s for coil "
                 f"(threshold={threshold:.2f})...")
        t0 = time.time()
        while time.time() - t0 < wait_s:
            try:
                m1 = exchange.fetch_ohlcv(
                    sym, '1m', limit=baseline_min + 5)
                if not m1 or len(m1) < 20:
                    time.sleep(poll_s)
                    continue
                df = pd.DataFrame(
                    m1, columns=['ts','Open','High','Low','Close','Volume'])
                df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
                df = df.set_index('ts').astype(float).sort_index()
                score, s_now, s_base = _coil_score_from_df(
                    df, window_min, baseline_min)
                if score >= threshold:
                    px_now = float(df['Close'].iloc[-1])
                    el = time.time() - t0
                    log.info(f"[Coil] {sym} coil detected! "
                             f"score={score:.3f} elapsed={el:.1f}s "
                             f"px={px_now:.6f}")
                    return True, px_now
            except Exception as e:
                log.debug(f"[Coil] {sym} poll error: {e}")
            time.sleep(poll_s)
        log.info(f"[Coil] {sym} timeout ({wait_s}s) -- no coil")
        return False, 0.0
    except Exception as e:
        log.warning(f"[Coil] {sym} wait error: {e} -- fallback")
        return True, 0.0


def _coil_filter_signals(assets, signals, exchange,
                          max_wait_min=None):
    if not getattr(CFG, 'COIL_TIMING_ENABLED', False):
        return signals
    if exchange is None:
        log.warning("[Coil] no exchange -- filter skipped")
        return signals

    threshold = float(getattr(CFG, 'COIL_THRESHOLD', 0.5))
    max_w = int(max_wait_min or getattr(CFG, 'COIL_MAX_WAIT_MIN', 5))
    window_min = int(getattr(CFG, 'COIL_WINDOW_MIN', 15))
    baseline_min = int(getattr(CFG, 'COIL_BASELINE_MIN', 60))

    n_total = len(signals)
    log.info(f"[Coil] filtering {n_total} signals "
             f"(thr={threshold}, wait={max_w}m)...")

    kept = []
    n_kept = 0
    n_no_coil = 0
    n_err = 0

    for i, sig in enumerate(signals):
        if i % 20 == 0 and i > 0:
            log.info(f"  [Coil] {i}/{n_total}...")
        try:
            st = _coil_ts_utc(sig.timestamp)
            if st is None:
                kept.append(sig)
                continue
            m1 = _coil_fetch_1m(
                exchange, sig.symbol, st,
                before_min=baseline_min, after_min=max_w)
            if m1 is None or len(m1) < 20:
                kept.append(sig)
                continue
            coil = _coil_find_moment(
                m1, st,
                max_wait_min=max_w,
                threshold=threshold,
                window_min=window_min,
                baseline_min=baseline_min,
            )
            if coil is not None:
                kept.append(sig)
                n_kept += 1
            else:
                n_no_coil += 1
        except Exception as e:
            log.debug(f"[Coil] {sig.symbol}: {e}")
            kept.append(sig)
            n_err += 1

    log.info(f"[Coil] kept={n_kept}/{n_total}  "
             f"rejected={n_no_coil}  errors={n_err}")
    return kept


def run_live(cfg, exchange):'''

F2_IDEM = "[COIL-TIMING] Intra-bar volatility compression"


# ═════════════════════════════════════════════════════════════════════
# F3 — Backtest hook (unchanged)
# ═════════════════════════════════════════════════════════════════════

F3_ANCHOR = '''    if CFG.ML_FILTER_ENABLED:
        sigs = filter_signals_ml(sigs, assets)

    log.info(f"  ✔ {len(sigs):,} إشارة")'''

F3_CONTENT = '''    if CFG.ML_FILTER_ENABLED:
        sigs = filter_signals_ml(sigs, assets)

    # ══ [COIL-TIMING] filter signals by coil presence ══
    if getattr(CFG, 'COIL_TIMING_ENABLED', False):
        sigs = _coil_filter_signals(assets, sigs, exchange)

    log.info(f"  ✔ {len(sigs):,} إشارة")'''

F3_IDEM = "# ══ [COIL-TIMING] filter signals by coil presence ══"


# ═════════════════════════════════════════════════════════════════════
# F4 — Live hook (anchor updated: 28-space indentation)
# ═════════════════════════════════════════════════════════════════════

F4_ANCHOR = '''                            rec = place_pending_entry(
                                exchange, sym, sd, qty, sig,
                                timeout_s=_timeout_s,
                                leverage=int(dynamic_leverage),
                                ad=assets[sym],
                            )
                            if rec is None:
                                log.info(f"[Pending] {sym} rejected — skip")
                                continue
                            try:
                                save_pending_orders()
                            except Exception:
                                pass
                            continue'''

F4_CONTENT = '''                            # ══ [COIL-TIMING] wait for intra-bar coil ══
                            _coil_target = None
                            if getattr(CFG, 'COIL_TIMING_ENABLED', False):
                                _coil_ok, _coil_px = _coil_wait_for_signal(
                                    exchange, sym, sig, assets[sym],
                                )
                                if not _coil_ok:
                                    log.info(f"[Coil] {sym} rejected -- "
                                             f"no coil in window")
                                    continue
                                try:
                                    _sigma_coil = float(
                                        assets[sym].E_therm[sig.feat_idx])
                                    _adv_coil = float(
                                        assets[sym].adv_usd[sig.close_idx])
                                    _coil_target = _coil_compute_target(
                                        _coil_px, sig.action,
                                        _sigma_coil, _adv_coil,
                                        exchange, sym, qty,
                                    )
                                    log.info(f"[Coil] {sym} target="
                                             f"{_coil_target:.6f} "
                                             f"(coil px={_coil_px:.6f})")
                                except Exception as _e:
                                    log.warning(f"[Coil] {sym} target "
                                                f"err: {_e}")
                                    _coil_target = None

                            rec = place_pending_entry(
                                exchange, sym, sd, qty, sig,
                                timeout_s=_timeout_s,
                                leverage=int(dynamic_leverage),
                                ad=assets[sym],
                                explicit_target=_coil_target,
                            )
                            if rec is None:
                                log.info(f"[Pending] {sym} rejected — skip")
                                continue
                            try:
                                save_pending_orders()
                            except Exception:
                                pass
                            continue'''

F4_IDEM = "# ══ [COIL-TIMING] wait for intra-bar coil ══"


# ═════════════════════════════════════════════════════════════════════
# F5 — CLI argument (unchanged)
# ═════════════════════════════════════════════════════════════════════

F5_ANCHOR = '''    # [ABLATION-FLAGS]
    p.add_argument("--no-apex", action="store_true",
                   help="Disable Apex exit")'''

F5_CONTENT = '''    # [ABLATION-FLAGS]
    p.add_argument("--no-apex", action="store_true",
                   help="Disable Apex exit")
    # ══ [COIL-TIMING] ══
    p.add_argument("--coil-timing", action="store_true",
                   help="Enable Coil Timing (intra-bar volatility filter)")
    p.add_argument("--coil-threshold", type=float, default=None,
                   help="Coil score threshold [0-1] (default 0.5)")
    p.add_argument("--coil-max-wait-min", type=int, default=None,
                   help="Backtest coil search window in minutes "
                        "(default 5)")
    p.add_argument("--coil-live-wait-s", type=int, default=None,
                   help="Live coil wait timeout in seconds (default 90)")'''

F5_IDEM = "    # ══ [COIL-TIMING] ══\n    p.add_argument(\"--coil-timing\", action=\"store_true\","


# ═════════════════════════════════════════════════════════════════════
# F6 — CLI wiring (unchanged)
# ═════════════════════════════════════════════════════════════════════

F6_ANCHOR = '''    print("╔"+"═"*70+"╗")'''

F6_CONTENT = '''    # ══ [COIL-TIMING] CLI wiring ══
    if getattr(args, "coil_timing", False):
        CFG.COIL_TIMING_ENABLED = True
        if getattr(args, "coil_threshold", None) is not None:
            CFG.COIL_THRESHOLD = float(args.coil_threshold)
        if getattr(args, "coil_max_wait_min", None) is not None:
            CFG.COIL_MAX_WAIT_MIN = int(args.coil_max_wait_min)
        if getattr(args, "coil_live_wait_s", None) is not None:
            CFG.COIL_LIVE_WAIT_S = int(args.coil_live_wait_s)
        log.info(
            f"[Coil] ENABLED threshold={CFG.COIL_THRESHOLD:.2f} "
            f"backtest_wait={CFG.COIL_MAX_WAIT_MIN}m "
            f"live_wait={CFG.COIL_LIVE_WAIT_S}s"
        )
    else:
        log.info("[Coil] Disabled (use --coil-timing to enable)")

    print("╔"+"═"*70+"╗")'''

F6_IDEM = "# ══ [COIL-TIMING] CLI wiring ══"


# ═════════════════════════════════════════════════════════════════════

@dataclass
class Fix:
    name: str
    anchor: str
    content: str
    idempotency: str
    required: bool = True


FIXES = [
    Fix("F1_Config",        F1_ANCHOR, F1_CONTENT, F1_IDEM, True),
    Fix("F2_CoilFunctions", F2_ANCHOR, F2_CONTENT, F2_IDEM, True),
    Fix("F3_BacktestHook",  F3_ANCHOR, F3_CONTENT, F3_IDEM, True),
    Fix("F4_LiveHook",      F4_ANCHOR, F4_CONTENT, F4_IDEM, True),
    Fix("F5_CLIArg",        F5_ANCHOR, F5_CONTENT, F5_IDEM, True),
    Fix("F6_CLIWiring",     F6_ANCHOR, F6_CONTENT, F6_IDEM, True),
]


def apply_fix(source, fix):
    if fix.idempotency and fix.idempotency in source:
        return source, "SKIP"
    if fix.anchor not in source:
        return source, "ANCHOR_NOT_FOUND"
    cnt = source.count(fix.anchor)
    if cnt > 1:
        return source, f"AMBIGUOUS({cnt})"
    return source.replace(fix.anchor, fix.content, 1), "OK"


def cmd_dry(path):
    src = read(path)
    log(f"Dry-run: {path} ({len(src)} chars)")
    cur = src
    for fix in FIXES:
        n, st = apply_fix(cur, fix)
        icon = "OK  " if st == "OK" else (
            "SKIP" if st == "SKIP" else "FAIL")
        print(f"  [{icon}] {fix.name:22s} -- {st}")
        if st == "OK":
            cur = n
    try:
        compile(cur, path, "exec")
        print("  [OK  ] syntax check")
    except SyntaxError as e:
        print(f"  [FAIL] syntax: {e}")
        return 1
    return 0


def cmd_apply(path):
    src = read(path)
    log(f"Applying to: {path}")

    os.makedirs(".patches_backup", exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    bkp = f".patches_backup/{os.path.basename(path)}.{ts}.coil.bak"
    shutil.copy2(path, bkp)
    log(f"Backup: {bkp}")

    cur = src
    ok = skip = fail = 0
    for fix in FIXES:
        n, st = apply_fix(cur, fix)
        if st == "OK":
            cur = n
            log(f"  [OK  ] {fix.name}")
            ok += 1
        elif st == "SKIP":
            log(f"  [SKIP] {fix.name}")
            skip += 1
        else:
            log(f"  [FAIL] {fix.name}: {st}", level="ERROR")
            fail += 1
            if fix.required:
                log("Rolling back", level="ERROR")
                return 2

    try:
        compile(cur, path, "exec")
        log("Syntax OK")
    except SyntaxError as e:
        log(f"Syntax error: {e}", level="ERROR")
        return 3

    write(path, cur)
    log(f"Applied={ok} Skipped={skip} Failed={fail}")
    log(f"Backup: {bkp}")
    return 0


def cmd_verify(path):
    src = read(path)
    missing = 0
    for fix in FIXES:
        if fix.idempotency and fix.idempotency in src:
            print(f"  [OK  ] {fix.name}")
        else:
            print(f"  [MISS] {fix.name}")
            missing += 1
    return 0 if missing == 0 else 1


def cmd_rollback(path):
    bdir = ".patches_backup"
    if not os.path.isdir(bdir):
        log("No backup dir", level="ERROR")
        return 1
    base = os.path.basename(path)
    cands = sorted(
        [f for f in os.listdir(bdir)
         if f.startswith(base + ".") and f.endswith(".coil.bak")],
        reverse=True,
    )
    if not cands:
        log("No backups", level="ERROR")
        return 1
    src = os.path.join(bdir, cands[0])
    shutil.copy2(src, path)
    log(f"Restored from {src}")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default=DEFAULT_TARGET)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rollback", action="store_true")
    args = p.parse_args()

    if not os.path.exists(args.target):
        log(f"Not found: {args.target}", level="ERROR")
        return 1

    if args.rollback:
        return cmd_rollback(args.target)
    if args.verify_only:
        return cmd_verify(args.target)
    if args.dry_run:
        return cmd_dry(args.target)
    return cmd_apply(args.target)


if __name__ == "__main__":
    sys.exit(main())
