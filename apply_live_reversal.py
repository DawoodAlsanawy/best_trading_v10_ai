#!/usr/bin/env python3
"""
apply_live_reversal.py

Installs the LIVE equivalent of the sub-bar Touch-and-Bounce entry state
machine into trading_2_live4.py.

Reuses the SAME confirmation logic as the backtest
(_check_reversal_fill_subbars in precompute_entry_fills) but for live:

  * Rolling 15m sub-bar cache per symbol
  * Persistent _REVERSAL_WATCHERS state machine on disk
  * Per-cycle monitor that scans newly-closed sub-bars
  * Fills via market or GTX-limit, then _place_protective_orders

Backtest behavior is unchanged.

Run:  python apply_live_reversal.py
"""
import os, sys, shutil, hashlib

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found", file=sys.stderr); sys.exit(1)

marker = "_REVERSAL_WATCHERS"
if marker in open(SRC).read():
    print(f"✗ {SRC} already patched. Restore from .bak first.", file=sys.stderr)
    sys.exit(3)

shutil.copy2(SRC, SRC + ".bak")
print(f"✓ backup → {SRC}.bak\n")

with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()
orig = s
report = []

def patch(old, new, label, required=True):
    global s
    if old not in s:
        report.append(("✗" if required else "⚠") + f" {label}")
        return False
    s = s.replace(old, new, 1)
    report.append("✓ " + label)
    return True

# ═══════════════════════════════════════════════════════════════
# 1. Insert entire Live Reversal module before run_live
# ═══════════════════════════════════════════════════════════════
ANCHOR_RL = "def run_live(cfg, exchange):"

MODULE = '''# ═══════════════════════════════════════════════════════════════
# [LIVE REVERSAL] Touch-and-Bounce on sub-bars, live execution
# ═══════════════════════════════════════════════════════════════
import time as _t_rev


_REVERSAL_WATCHERS: Dict[str, Dict] = {}
_REVERSAL_WATCHERS_PATH: str = ""
_SUBBAR_LIVE_CACHE: Dict[str, pd.DataFrame] = {}
_SUBBAR_FETCH_THROTTLE: Dict[str, float] = {}
_REV_FETCH_EVERY_S: float = 30.0
_REV_MAX_PER_CYCLE: int = 3


def _sub_tf_seconds(sub_tf: str) -> int:
    try:
        import ccxt as _cc
        return int(_cc.binance().parse_timeframe(sub_tf))
    except Exception:
        return {"1m": 60, "5m": 300, "15m": 900,
                "30m": 1800, "1h": 3600, "4h": 14400}.get(sub_tf, 900)


def load_reversal_watchers(mode: str) -> Dict[str, Dict]:
    global _REVERSAL_WATCHERS, _REVERSAL_WATCHERS_PATH
    _REVERSAL_WATCHERS_PATH = f"reversal_watchers_{mode}.json"
    if os.path.exists(_REVERSAL_WATCHERS_PATH):
        try:
            with open(_REVERSAL_WATCHERS_PATH) as f:
                raw = json.load(f)
            for _sym, _w in raw.items():
                _w.pop("signal_ref", None)
            _REVERSAL_WATCHERS = raw
            log.info(f"[LiveRev] Restored {len(_REVERSAL_WATCHERS)} watchers")
        except Exception as e:
            log.warning(f"[LiveRev] load failed: {e}")
            _REVERSAL_WATCHERS = {}
    return _REVERSAL_WATCHERS


def save_reversal_watchers() -> None:
    if not _REVERSAL_WATCHERS_PATH:
        return
    try:
        tmp = _REVERSAL_WATCHERS_PATH + ".tmp"
        ser = {}
        for sym, w in _REVERSAL_WATCHERS.items():
            _w = {k: v for k, v in w.items() if k != "signal_ref"}
            ser[sym] = _w
        with open(tmp, "w") as f:
            json.dump(ser, f, default=str, indent=2)
        os.replace(tmp, _REVERSAL_WATCHERS_PATH)
    except Exception as e:
        log.debug(f"[LiveRev] save failed: {e}")


def _fetch_live_subbars(exchange, sym: str, sub_tf: str,
                         keep_bars: int = 200) -> Optional[pd.DataFrame]:
    now = _t_rev.time()
    _last = _SUBBAR_FETCH_THROTTLE.get(sym, 0.0)
    if now - _last < _REV_FETCH_EVERY_S:
        return _SUBBAR_LIVE_CACHE.get(sym)
    _SUBBAR_FETCH_THROTTLE[sym] = now
    try:
        _rate_record(1.0)
        bars = exchange.fetch_ohlcv(sym, sub_tf, limit=min(keep_bars, 300))
    except Exception as e:
        log.debug(f"[LiveRev] fetch {sym} {sub_tf}: {e}")
        return _SUBBAR_LIVE_CACHE.get(sym)
    if not bars:
        return _SUBBAR_LIVE_CACHE.get(sym)
    df_new = pd.DataFrame(bars,
                          columns=["ts", "Open", "High", "Low",
                                    "Close", "Volume"])
    df_new["ts"] = pd.to_datetime(df_new["ts"], unit="ms", utc=True)
    df_new = df_new.set_index("ts").astype(float).sort_index()
    old = _SUBBAR_LIVE_CACHE.get(sym)
    if old is not None:
        df_new = pd.concat([old, df_new])
    df_new = df_new[~df_new.index.duplicated(keep="last")].sort_index()
    if len(df_new) > keep_bars:
        df_new = df_new.iloc[-keep_bars:]
    _SUBBAR_LIVE_CACHE[sym] = df_new
    return df_new


def _only_closed_subbars(df: pd.DataFrame, tf_sec: int) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(seconds=int(tf_sec))
    return df[df.index <= cutoff]


def _bar_confirms_bounce(w: Dict, close: float) -> bool:
    action = w["action"]
    target = float(w["target"])
    mode = str(CFG.REVERSAL_CONFIRM_MODE)

    if mode == "close_back":
        return (action == "BUY" and close > target) or \\
               (action == "SELL" and close < target)

    if mode == "sigma_bounce":
        kappa = float(CFG.REVERSAL_CONFIRM_KAPPA)
        sigma = float(w.get("sigma_bar", 0.01))
        thr = kappa * sigma * target
        if action == "BUY":
            return (close - target) > thr
        return (target - close) > thr

    if mode == "bar_color":
        prev = w.get("prev_close")
        w["prev_close"] = close
        if prev is None:
            return False
        return (action == "BUY" and close > float(prev)) or \\
               (action == "SELL" and close < float(prev))

    if mode == "two_bar":
        ok = (close > target) if action == "BUY" else (close < target)
        w["two_bar_count"] = (int(w.get("two_bar_count", 0)) + 1) if ok else 0
        return w["two_bar_count"] >= 2

    return False


def _execute_reversal_fill(exchange, sym: str, w: Dict,
                            open_pos_live: Dict) -> None:
    action = w["action"]
    target = float(w["target"])
    qty = float(w["qty"])
    side = "buy" if action == "BUY" else "sell"

    try:
        _rate_record(2.0)
        tk = exchange.fetch_ticker(sym)
        current = float(tk.get("last") or 0)
    except Exception:
        current = target

    fill_mode = str(getattr(CFG, "REVERSAL_FILL_AT", "target"))
    if fill_mode == "close" and current > 0:
        fill_px = current
    elif fill_mode == "best" and current > 0:
        fill_px = (min(target, current) if action == "BUY"
                   else max(target, current))
    else:
        fill_px = target

    # Leverage / margin
    try:
        ensure_symbol_setup(exchange, sym, int(w["leverage"]),
                             margin_mode="isolated")
    except Exception as e:
        log.warning(f"[LiveRev] setup {sym}: {e}")
        w["status"] = "EXPIRED"
        return

    drift = (abs(current - target) / max(target, 1e-9)
             if current > 0 else 0.0)
    entry_px = 0.0
    actual_qty = 0.0

    if drift > 0.003:
        # Market fill — price moved too far from target
        try:
            o = exchange.create_order(sym, "market", side, qty, None)
            v = verify_fill(exchange, o["id"], sym, timeout_s=2.5)
            if not (v and v.get("filled")):
                log.warning(f"[LiveRev] {sym} market no fill")
                w["status"] = "EXPIRED"
                return
            entry_px = float(v.get("avg_price") or fill_px)
            actual_qty = float(v.get("qty") or qty)
        except Exception as e:
            log.error(f"[LiveRev] {sym} market failed: {e}")
            w["status"] = "EXPIRED"
            return
    else:
        # GTX limit at fill_px (maker)
        result = execute_post_only(
            exchange, sym, side, qty,
            fixed_target=float(fill_px),
            fallback_market=False,
            reduce_only=False,
        )
        if not result.get("filled_qty") or result["filled_qty"] <= 0:
            log.warning(f"[LiveRev] {sym} GTX no fill "
                        f"({result.get('reason')})")
            w["status"] = "EXPIRED"
            return
        entry_px = float(result["avg_price"])
        actual_qty = float(result["filled_qty"])

    if entry_px <= 0 or actual_qty <= 0:
        log.warning(f"[LiveRev] {sym} invalid fill (px={entry_px} "
                    f"qty={actual_qty})")
        w["status"] = "EXPIRED"
        return

    # SL / TP — rebuild from actual entry using same physics as backtest
    orig_sl_dist = float(w["orig_sl_dist"])
    orig_tp_dist = float(w["orig_tp_dist"])
    if orig_sl_dist <= 1e-12:
        orig_sl_dist = entry_px * 0.015
        orig_tp_dist = orig_sl_dist * float(getattr(CFG, "TP_MULT", 2.0))

    _max_sl_frac = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
    if orig_sl_dist > entry_px * _max_sl_frac:
        _rr = orig_tp_dist / max(orig_sl_dist, 1e-12)
        orig_sl_dist = entry_px * _max_sl_frac
        orig_tp_dist = orig_sl_dist * _rr

    if action == "BUY":
        new_sl = entry_px - orig_sl_dist
        new_tp = entry_px + orig_tp_dist
    else:
        new_sl = entry_px + orig_sl_dist
        new_tp = entry_px - orig_tp_dist

    # Trail params from stored sigma_bar (matches backtest compute_trail_params)
    _sb = float(w.get("sigma_bar", 0.01))
    _td = float(np.clip(CFG.TRAIL_KAPPA * _sb,
                         CFG.TRAIL_MIN_FRAC, CFG.TRAIL_MAX_FRAC))
    _ta = float(np.clip(CFG.TRAIL_ACT_KAPPA * _sb,
                         CFG.TRAIL_ACT_MIN_FRAC, CFG.TRAIL_ACT_MAX_FRAC))
    if _ta <= _td:
        _ta = _td * 1.2

    open_pos_live[sym] = {
        "action": action,
        "entry": entry_px,
        "qty": actual_qty,
        "sl": new_sl,
        "tp1": new_tp,
        "T_info": float(w.get("T_info", 0.0)),
        "dyn_risk": float(w.get("dyn_risk", 0.01)),
        "entry_ts": _t_rev.time(),
        "fill_ratio": 1.0,
        "leverage": int(w["leverage"]),
        "trail_dist_frac": _td,
        "trail_activate_frac": _ta,
        "sl_dist_initial": float(abs(entry_px - new_sl)),
        "mmr": float(w.get("mmr", CFG.LIQ_FALLBACK_MMR)),
        "_entry_ci": 0,
        "_trail_bars_held": 0,
        "_trail_peak_R": 0.0,
        "_trail_last_update_ts": 0.0,
        "_sym": sym,
        "_orig_score": 0.0,
        "stage": "REVERSAL",
    }

    if getattr(CFG, "PROTECTIVE_ORDERS_ENABLED", True):
        try:
            if _place_protective_orders(exchange, sym, open_pos_live[sym]):
                open_pos_live[sym]["_prot_last_sl"] = float(new_sl)
                open_pos_live[sym]["_prot_last_tp"] = float(new_tp)
        except Exception as e:
            log.warning(f"[LiveRev] prot {sym}: {e}")

    log.info(f"✅ [LiveRev] {action} {sym} @ {entry_px:.6f} "
             f"qty={actual_qty:.6f} sl={new_sl:.6f} tp={new_tp:.6f}")
    w["status"] = "FILLED"


def _register_reversal_watcher(exchange, sym: str, side: str,
                                qty: float, sig, leverage: int,
                                ad=None) -> bool:
    if sym in _REVERSAL_WATCHERS:
        return False
    if sym in _PENDING_ORDERS:
        return False

    close_ts = _t_rev.time()
    try:
        ts = pd.Timestamp(sig.timestamp)
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        close_ts = float(ts.timestamp())
    except Exception:
        pass

    sigma_bar = 0.01
    if ad is not None:
        try:
            fi = int(sig.feat_idx)
            if 0 <= fi < len(ad.E_therm):
                _s = float(ad.E_therm[fi])
                if np.isfinite(_s) and _s > 1e-9:
                    sigma_bar = _s
        except Exception:
            pass

    try:
        _mmr = float(_get_mmr_for_symbol(exchange, sym))
    except Exception:
        _mmr = float(getattr(CFG, "LIQ_FALLBACK_MMR", 0.02))

    w = {
        "sym": sym,
        "side": side,
        "action": sig.action,
        "target": float(sig.price),
        "qty": float(qty),
        "leverage": int(leverage),
        "mmr": _mmr,
        "dyn_risk": float(sig.dynamic_risk),
        "T_info": float(sig.T_info_val),
        "sigma_bar": float(sigma_bar),
        "close_idx": int(sig.close_idx),
        "close_ts": float(close_ts),
        "created_at": _t_rev.time(),
        "status": "WAITING_TOUCH",
        "touch_ts": 0.0,
        "last_scan_ts": float(close_ts),
        "signal_ref": sig,
        "sig_ts": str(sig.timestamp),
        "sig_price": float(sig.price),
        "sig_sl": float(sig.sl),
        "sig_tp1": float(sig.tp1),
        "orig_sl_dist": float(abs(sig.price - sig.sl)),
        "orig_tp_dist": float(abs(sig.tp1 - sig.price)),
        "two_bar_count": 0,
        "prev_close": None,
    }
    _REVERSAL_WATCHERS[sym] = w
    log.info(f"[LiveRev] {sig.action} {sym} registered — "
             f"target={sig.price:.6f} sl={sig.sl:.6f} tp={sig.tp1:.6f}")
    return True


def monitor_reversal_watchers(exchange, open_pos_live: Dict,
                                assets: Optional[Dict] = None) -> None:
    if not getattr(CFG, "REVERSAL_CONFIRM_ENABLED", False):
        return
    if not _REVERSAL_WATCHERS:
        return

    sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"
    tf_sec = _sub_tf_seconds(sub_tf)
    now = _t_rev.time()
    fills_this_cycle = 0

    for sym in list(_REVERSAL_WATCHERS.keys()):
        w = _REVERSAL_WATCHERS[sym]
        status = w.get("status", "WAITING_TOUCH")

        if status in ("FILLED", "EXPIRED"):
            _REVERSAL_WATCHERS.pop(sym, None)
            continue

        age_h = (now - float(w.get("close_ts", now))) / 3600.0
        if age_h > float(CFG.REVERSAL_MAX_HOURS):
            log.info(f"[LiveRev] {sym} expired (age={age_h:.1f}h)")
            _REVERSAL_WATCHERS.pop(sym, None)
            continue

        if sym in open_pos_live:
            log.info(f"[LiveRev] {sym} already has position — dropping")
            _REVERSAL_WATCHERS.pop(sym, None)
            continue

        df = _fetch_live_subbars(exchange, sym, sub_tf, keep_bars=200)
        if df is None or len(df) < 3:
            continue
        df_closed = _only_closed_subbars(df, tf_sec)
        if df_closed is None or len(df_closed) == 0:
            continue

        last_scan_ts = float(w.get("last_scan_ts", 0.0))
        new_bars = df_closed[
            (df_closed.index.astype("int64") // 10**9) > last_scan_ts
        ]
        if len(new_bars) == 0:
            continue

        for ts, row in new_bars.iterrows():
            ts_unix = float(ts.value / 1e9)
            high = float(row["High"])
            low = float(row["Low"])
            close = float(row["Close"])
            action = w["action"]
            target = float(w["target"])

            # ── TOUCH ──
            if w["status"] == "WAITING_TOUCH":
                touched = ((action == "BUY" and low <= target) or
                            (action == "SELL" and high >= target))
                if touched:
                    w["status"] = "WAITING_BOUNCE"
                    w["touch_ts"] = ts_unix
                    log.info(f"[LiveRev] {sym} TOUCH @ {ts}")
                    w["last_scan_ts"] = ts_unix
                    continue

            # ── BOUNCE ──
            if w["status"] == "WAITING_BOUNCE":
                bounce_elapsed = ts_unix - float(w["touch_ts"])
                if bounce_elapsed > int(CFG.REVERSAL_BOUNCE_SUBBARS) * tf_sec:
                    w["status"] = "EXPIRED"
                    log.info(f"[LiveRev] {sym} bounce timeout")
                    break
                if _bar_confirms_bounce(w, close):
                    w["status"] = "READY_TO_FILL"
                    log.info(f"[LiveRev] {sym} BOUNCE confirmed @ {ts}")

            # ── FILL ──
            if w["status"] == "READY_TO_FILL":
                _execute_reversal_fill(exchange, sym, w, open_pos_live)
                fills_this_cycle += 1
                break

            w["last_scan_ts"] = ts_unix

        if w.get("status") in ("FILLED", "EXPIRED"):
            continue
        if fills_this_cycle >= _REV_MAX_PER_CYCLE:
            break


# ═══════════════════════════════════════════════════════════════


'''

patch(ANCHOR_RL, MODULE + ANCHOR_RL,
      "insert Live Reversal module before run_live")

# ═══════════════════════════════════════════════════════════════
# 2. run_live: load watchers on startup (after load_pending_orders)
# ═══════════════════════════════════════════════════════════════
LOAD_ANCHOR = "    load_pending_orders(cfg.mode)"
LOAD_NEW = (LOAD_ANCHOR + "\n"
            "    # ══ [LiveRev] Load persisted reversal watchers ══\n"
            "    load_reversal_watchers(cfg.mode)\n"
            "    log.info(f\"  [LiveRev] Active watchers: \"\n"
            "             f\"{len(_REVERSAL_WATCHERS)}\")")
patch(LOAD_ANCHOR, LOAD_NEW, "run_live: load watchers at startup")

# ═══════════════════════════════════════════════════════════════
# 3. run_live: add monitor call after monitor_pending_orders
# ═══════════════════════════════════════════════════════════════
MON_ANCHOR = '''            try:
                monitor_pending_orders(
                    exchange, open_pos_live, loop_iter,
                    assets=assets if 'assets' in dir() else None
                )
            except Exception as _e:
                log.warning(f"[Pending] monitor error: {_e}")'''

MON_NEW = MON_ANCHOR + '''
            try:
                monitor_reversal_watchers(
                    exchange, open_pos_live,
                    assets=assets if 'assets' in dir() else None
                )
            except Exception as _e:
                log.warning(f"[LiveRev] monitor error: {_e}")'''

patch(MON_ANCHOR, MON_NEW, "run_live: monitor watchers each cycle")

# ═══════════════════════════════════════════════════════════════
# 4. run_live: save watchers at end of loop
# ═══════════════════════════════════════════════════════════════
SAVE_ANCHOR = "            save_pending_orders()\n            save_watched_signals()\n            save_symbol_meta()"
SAVE_NEW = ("            save_pending_orders()\n"
            "            save_reversal_watchers()\n"
            "            save_watched_signals()\n"
            "            save_symbol_meta()")
patch(SAVE_ANCHOR, SAVE_NEW, "run_live: save watchers each cycle")

# ═══════════════════════════════════════════════════════════════
# 5. run_live: replace entry path when REVERSAL enabled
# ═══════════════════════════════════════════════════════════════
ENTRY_ANCHOR = '''                            # ── Legacy immediate placement ──
                            _tf_sec_w = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600'''

ENTRY_NEW = '''                            # ══ [LiveRev] register watcher instead ══
                            if getattr(CFG, "REVERSAL_CONFIRM_ENABLED", False):
                                _ok = _register_reversal_watcher(
                                    exchange, sym, sd, qty, sig,
                                    int(dynamic_leverage), assets[sym]
                                )
                                if _ok:
                                    try:
                                        save_reversal_watchers()
                                    except Exception:
                                        pass
                                continue

                            # ── Legacy immediate placement ──
                            _tf_sec_w = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600'''

patch(ENTRY_ANCHOR, ENTRY_NEW,
      "run_live: reversal watcher replaces pending entry")

# ═══════════════════════════════════════════════════════════════
# 6. Exposure guard: include watchers
# ═══════════════════════════════════════════════════════════════
EXPO_ANCHOR = '''                            _total_exposure = (len(_PENDING_ORDERS)
                                               + len(open_pos_live)
                                               + len(_WATCHED_SIGNALS))'''
EXPO_NEW = '''                            _total_exposure = (len(_PENDING_ORDERS)
                                               + len(open_pos_live)
                                               + len(_WATCHED_SIGNALS)
                                               + len(_REVERSAL_WATCHERS))'''
patch(EXPO_ANCHOR, EXPO_NEW, "run_live: count watchers in exposure")

# ═══════════════════════════════════════════════════════════════
# 7. run_live: startup cleanup of stale watchers
# ═══════════════════════════════════════════════════════════════
CLEAN_ANCHOR = '''    _stale = _lv_pending_drop_stale(exchange, max_age_s=float(getattr(CFG, 'LIVE_PENDING_GRACE_S', 600.0)))'''
CLEAN_NEW = '''    # ══ [LiveRev] Drop watchers older than REVERSAL_MAX_HOURS ══
    if _REVERSAL_WATCHERS:
        _now_rev = _t_rev.time()
        _max_s = float(CFG.REVERSAL_MAX_HOURS) * 3600.0
        _dropped = 0
        for _s in list(_REVERSAL_WATCHERS.keys()):
            _w = _REVERSAL_WATCHERS[_s]
            if _now_rev - float(_w.get("close_ts", _now_rev)) > _max_s:
                _REVERSAL_WATCHERS.pop(_s, None)
                _dropped += 1
        if _dropped:
            log.info(f"[LiveRev] Dropped {_dropped} stale watchers on startup")
            save_reversal_watchers()

''' + CLEAN_ANCHOR
patch(CLEAN_ANCHOR, CLEAN_NEW, "run_live: startup stale watcher cleanup")

# ═══════════════════════════════════════════════════════════════
# 8. Wipe caches when --clear-cache is used (already covered in main)
#    — nothing to add; the file list already includes live_state etc.
#    We just also clear reversal_watchers_*.json here for safety.
# ═══════════════════════════════════════════════════════════════
CC_ANCHOR = '''            "symbol_meta_live.json", "symbol_meta_testnet.json",
            "kill_switch.json",'''
CC_NEW = '''            "symbol_meta_live.json", "symbol_meta_testnet.json",
            "reversal_watchers_live.json",
            "reversal_watchers_testnet.json",
            "kill_switch.json",'''
patch(CC_ANCHOR, CC_NEW, "clear-cache: also wipe watchers",
      required=False)

# ═══════════════════════════════════════════════════════════════
# Write + report
# ═══════════════════════════════════════════════════════════════
if s == orig:
    print("⚠  No changes applied:", file=sys.stderr)
    for line in report:
        print("   " + line, file=sys.stderr)
    sys.exit(2)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 68)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 68)
for line in report:
    print("   " + line)
print("═" * 68)
print("   Run testnet:  python3 " + SRC + " --mode testnet ... "
      "--reversal-confirm")
print("═" * 68)
