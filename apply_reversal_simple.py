#!/usr/bin/env python3
"""
apply_reversal_simple.py

Adds a minimal Touch-and-Bounce entry filter to trading_2_live2.py
covering ALL three modes (backtest / testnet / live).

Core idea:
    Do NOT place the entry order at the first touch of the target.
    Wait for a sub-bar CLOSE on the correct side of the target,
    then place the order.

Applied patches (all-in-one):
    P1  CFG: 5 new fields
    P2  _align_subbars: return sub_closes
    P3  AssetData: sub_closes field
    P4  process_asset: unpack 3-tuple
    P5  _check_reversal_fill: backtest helper
    P6  precompute_entry_fills: branch on the flag
    P7  live reversal module (state dict + monitor)
    P8  run_live: register instead of immediate entry
    P9  run_live: call monitor each cycle
    P10 argparse: 4 new flags
    P11 main(): wiring

Run:  python apply_reversal_simple.py
"""
import os, sys, shutil, hashlib

SRC = "trading_2_live2_2.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found in {os.getcwd()}", file=sys.stderr)
    sys.exit(1)

if "_check_reversal_fill_simple" in open(SRC).read():
    print("✗ File already patched. Restore from .bak first.",
          file=sys.stderr)
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
# P1 — CFG: new fields
# ═══════════════════════════════════════════════════════════════
ANCHOR_P1 = "    USE_ABSOLUTE_THRESHOLDS: bool = True"
NEW_P1 = ANCHOR_P1 + """

    # ══ [REVERSAL-CONFIRM] Touch-and-Bounce entry filter ══
    # After a signal fires, the entry order is NOT placed until the
    # market (a) touches the target, then (b) closes a sub-bar back
    # on the signal's side. This rejects "broken support" entries.
    REVERSAL_CONFIRM_ENABLED: bool = False
    REVERSAL_TOUCH_WINDOW:    int   = 20    # sub-bars to wait for touch
    REVERSAL_BOUNCE_WINDOW:   int   = 4     # sub-bars to confirm bounce
    REVERSAL_MAX_HOURS:       float = 24.0  # live: max signal age
    # Internal tuning for live throttling (do not change unless needed)
    REVERSAL_LIVE_FETCH_EVERY_S: float = 30.0
    REVERSAL_LIVE_MAX_ACTIVE:    int   = 20"""
patch(ANCHOR_P1, NEW_P1, "P1: CFG fields")


# ═══════════════════════════════════════════════════════════════
# P2 — _align_subbars: return sub_closes
# ═══════════════════════════════════════════════════════════════
OLD_P2 = '''def _align_subbars(main_index, sub_df, sub_per_main, tf_sec):
    """
    Align sub-bars to main-bar grid.

    Returns (sub_highs, sub_lows) with shape (n_main, sub_per_main).
    Missing sub-bars are filled with the main bar's high/low.
    """
    n = len(main_index)
    sub_highs = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    sub_lows  = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    if sub_df is None or len(sub_df) == 0 or sub_per_main <= 0:
        return sub_highs, sub_lows

    try:
        sub_ts_ns = sub_df.index.asi8
        sub_high_vals = sub_df['High'].values.astype(np.float64)
        sub_low_vals  = sub_df['Low'].values.astype(np.float64)
        main_ns = main_index.asi8
        tf_ns = int(tf_sec * 1_000_000_000)

        for i in range(n):
            start_ns = main_ns[i]
            end_ns = start_ns + tf_ns
            lo = int(np.searchsorted(sub_ts_ns, start_ns, side='left'))
            hi = int(np.searchsorted(sub_ts_ns, end_ns, side='left'))
            if hi <= lo:
                continue
            take = min(hi - lo, sub_per_main)
            sub_highs[i, :take] = sub_high_vals[lo:lo+take]
            sub_lows[i, :take]  = sub_low_vals[lo:lo+take]
    except Exception as e:
        log.warning(f"[SubBars] align failed: {e}")
    return sub_highs, sub_lows'''

NEW_P2 = '''def _align_subbars(main_index, sub_df, sub_per_main, tf_sec):
    """
    Align sub-bars to main-bar grid.
    Returns (sub_highs, sub_lows, sub_closes), each (n_main, sub_per_main).
    Missing sub-bars are NaN.
    """
    n = len(main_index)
    sub_highs  = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    sub_lows   = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    sub_closes = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    if sub_df is None or len(sub_df) == 0 or sub_per_main <= 0:
        return sub_highs, sub_lows, sub_closes

    try:
        sub_ts_ns = sub_df.index.asi8
        sub_high_vals  = sub_df['High'].values.astype(np.float64)
        sub_low_vals   = sub_df['Low'].values.astype(np.float64)
        sub_close_vals = sub_df['Close'].values.astype(np.float64)
        main_ns = main_index.asi8
        tf_ns = int(tf_sec * 1_000_000_000)

        for i in range(n):
            start_ns = main_ns[i]
            end_ns = start_ns + tf_ns
            lo = int(np.searchsorted(sub_ts_ns, start_ns, side='left'))
            hi = int(np.searchsorted(sub_ts_ns, end_ns, side='left'))
            if hi <= lo:
                continue
            take = min(hi - lo, sub_per_main)
            sub_highs[i, :take]  = sub_high_vals[lo:lo+take]
            sub_lows[i, :take]   = sub_low_vals[lo:lo+take]
            sub_closes[i, :take] = sub_close_vals[lo:lo+take]
    except Exception as e:
        log.warning(f"[SubBars] align failed: {e}")
    return sub_highs, sub_lows, sub_closes'''
patch(OLD_P2, NEW_P2, "P2: _align_subbars returns 3 arrays")


# ═══════════════════════════════════════════════════════════════
# P3 — AssetData: sub_closes field
# ═══════════════════════════════════════════════════════════════
OLD_P3 = '''    # ══ [SUB-BARS] ══
    sub_highs: Optional[np.ndarray] = None    # shape (n_bars, sub_per_main)
    sub_lows:  Optional[np.ndarray] = None
    sub_per_main: int = 0
    sub_tf: str = ""'''
NEW_P3 = '''    # ══ [SUB-BARS] ══
    sub_highs:  Optional[np.ndarray] = None   # shape (n_bars, sub_per_main)
    sub_lows:   Optional[np.ndarray] = None
    sub_closes: Optional[np.ndarray] = None
    sub_per_main: int = 0
    sub_tf: str = ""'''
patch(OLD_P3, NEW_P3, "P3: AssetData sub_closes")


# ═══════════════════════════════════════════════════════════════
# P4 — process_asset: unpack 3 values
# ═══════════════════════════════════════════════════════════════
OLD_P4A = '''    _sub_h, _sub_l = None, None
    _sub_pm = 0
    _sub_tf_name = ""
    if (getattr(CFG, 'SUBBARS_ENABLED', True)
            and sub_df is not None and len(sub_df) > 0):
        _sub_tf_name = _get_subbars_tf(CFG.timeframe) or ""
        if _sub_tf_name:
            _sub_pm = _sub_per_main(CFG.timeframe, _sub_tf_name)
            if _sub_pm >= 2:
                _sub_h, _sub_l = _align_subbars(
                    ts, sub_df, _sub_pm, int(CFG.TF_SECONDS)
                )'''
NEW_P4A = '''    _sub_h, _sub_l, _sub_c = None, None, None
    _sub_pm = 0
    _sub_tf_name = ""
    if (getattr(CFG, 'SUBBARS_ENABLED', True)
            and sub_df is not None and len(sub_df) > 0):
        _sub_tf_name = _get_subbars_tf(CFG.timeframe) or ""
        if _sub_tf_name:
            _sub_pm = _sub_per_main(CFG.timeframe, _sub_tf_name)
            if _sub_pm >= 2:
                _sub_h, _sub_l, _sub_c = _align_subbars(
                    ts, sub_df, _sub_pm, int(CFG.TF_SECONDS)
                )'''
patch(OLD_P4A, NEW_P4A, "P4a: process_asset unpack 3 values")

OLD_P4B = '''        sub_highs=_sub_h,
        sub_lows=_sub_l,
        sub_per_main=_sub_pm,
        sub_tf=_sub_tf_name,
    )'''
NEW_P4B = '''        sub_highs=_sub_h,
        sub_lows=_sub_l,
        sub_closes=_sub_c,
        sub_per_main=_sub_pm,
        sub_tf=_sub_tf_name,
    )'''
patch(OLD_P4B, NEW_P4B, "P4b: pass sub_closes to AssetData")


# ═══════════════════════════════════════════════════════════════
# P5 — Insert _check_reversal_fill_simple before precompute_entry_fills
# ═══════════════════════════════════════════════════════════════
ANCHOR_P5 = "def precompute_entry_fills(assets, signals, max_wait_bars, pen_bps,"

HELPER_P5 = '''def _check_reversal_fill_simple(ad, sig, target0, cfg,
                                 first_main_ci, deadline_main_ci):
    """
    [REVERSAL-CONFIRM] Simple Touch-and-Bounce on sub-bars.

    Phase 1 — TOUCH:  first sub-bar whose low <= target (BUY) or
                     high >= target (SELL), within TOUCH_WINDOW.
    Phase 2 — BOUNCE: first later sub-bar whose close > target (BUY)
                     or close < target (SELL), within BOUNCE_WINDOW.

    Returns (confirm_main_ci, fill_px) or None.
    """
    if ad.sub_highs is None or ad.sub_closes is None or ad.sub_per_main < 2:
        return None

    action  = sig.action
    sub_pm  = int(ad.sub_per_main)
    start_main = int(sig.close_idx) + 1
    end_main   = min(int(deadline_main_ci), ad.sub_highs.shape[0])
    if end_main <= start_main:
        return None

    sh_flat = ad.sub_highs[start_main:end_main].reshape(-1)
    sl_flat = ad.sub_lows[start_main:end_main].reshape(-1)
    sc_flat = ad.sub_closes[start_main:end_main].reshape(-1)
    n_flat  = sh_flat.size
    if n_flat == 0:
        return None

    touch_win  = max(1, int(getattr(cfg, 'REVERSAL_TOUCH_WINDOW', 20)))
    bounce_win = max(1, int(getattr(cfg, 'REVERSAL_BOUNCE_WINDOW', 4)))

    # ── PHASE 1: TOUCH ──
    _touch_limit = min(touch_win, n_flat)
    touch_k = -1
    for k in range(_touch_limit):
        if not (np.isfinite(sh_flat[k]) and np.isfinite(sl_flat[k])):
            continue
        if action == "BUY" and sl_flat[k] <= target0:
            touch_k = k; break
        if action == "SELL" and sh_flat[k] >= target0:
            touch_k = k; break
    if touch_k < 0:
        return None

    # ── PHASE 2: BOUNCE ──
    b0 = touch_k + 1
    b1 = min(b0 + bounce_win, n_flat)
    if b1 <= b0:
        return None

    confirm_k = -1
    for k in range(b0, b1):
        c = sc_flat[k]
        if not np.isfinite(c):
            continue
        if action == "BUY" and c > target0:
            confirm_k = k; break
        if action == "SELL" and c < target0:
            confirm_k = k; break

    if confirm_k < 0:
        return None

    # ── PHASE 3: FILL ──
    _main_offset = confirm_k // sub_pm
    confirm_main = start_main + _main_offset
    return (int(confirm_main), float(target0))


'''
patch(ANCHOR_P5, HELPER_P5 + ANCHOR_P5, "P5: insert _check_reversal_fill_simple")


# ═══════════════════════════════════════════════════════════════
# P6 — Branch inside precompute_entry_fills
# ═══════════════════════════════════════════════════════════════
OLD_P6 = '''            target0 = _backtest_entry_target(sig, ad)
            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)

            # ── Stage 1 ──'''

NEW_P6 = '''            target0 = _backtest_entry_target(sig, ad)
            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)

            # ═══ [REVERSAL-CONFIRM] backtest branch ═══
            if getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False):
                _tw = int(getattr(CFG, 'REVERSAL_TOUCH_WINDOW', 20))
                _bw = int(getattr(CFG, 'REVERSAL_BOUNCE_WINDOW', 4))
                _sub_pm = int(ad.sub_per_main) if ad.sub_per_main else 1
                _max_flat = _tw + _bw
                _max_main = max(1, int(np.ceil(_max_flat / _sub_pm)))
                _dl_main = min(sig.close_idx + _max_main + 1, n_bars)
                _rev = _check_reversal_fill_simple(
                    ad, sig, target0, CFG,
                    sig.close_idx + 1, _dl_main
                )
                if _rev is None:
                    result[sig_i] = None
                    continue
                _rev_ci, _rev_px = _rev
                result[sig_i] = ('S1', int(_rev_ci), float(_rev_px))
                continue

            # ── Stage 1 ──'''
patch(OLD_P6, NEW_P6, "P6: precompute branch")


# ═══════════════════════════════════════════════════════════════
# P7 — Live reversal module before run_live
# ═══════════════════════════════════════════════════════════════
ANCHOR_P7 = "def run_live(cfg, exchange):"

MODULE_P7 = '''# ═══════════════════════════════════════════════════════════════
# [REVERSAL-CONFIRM LIVE] Minimal Touch-and-Bounce state machine
# ═══════════════════════════════════════════════════════════════
import time as _t_rc


_REVERSAL_STATES: Dict[str, Dict] = {}
_RC_FETCH_THROTTLE: Dict[str, float] = {}


def _sub_tf_seconds_simple(tf: str) -> int:
    _m = {"1m": 60, "3m": 180, "5m": 300, "15m": 900,
          "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400}
    if tf in _m:
        return _m[tf]
    try:
        import ccxt as _cc
        return int(_cc.binance().parse_timeframe(tf))
    except Exception:
        return 900


def _register_reversal_state(exchange, sym, side, qty, sig, leverage, ad):
    if sym in _REVERSAL_STATES or sym in _PENDING_ORDERS:
        return False
    if len(_REVERSAL_STATES) >= int(getattr(CFG, 'REVERSAL_LIVE_MAX_ACTIVE', 20)):
        return False

    sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"
    _now = _t_rc.time()
    _REVERSAL_STATES[sym] = {
        "sym":         sym,
        "side":        side,
        "qty":         float(qty),
        "leverage":    int(leverage),
        "sig":         sig,
        "ad_ref":      ad,
        "target":      float(sig.price),
        "sub_tf":      sub_tf,
        "phase":       "WAITING_TOUCH",
        "touch_ts":    None,
        "last_scan_ts": _now,
        "created_at":  _now,
    }
    log.info(f"[RevConfirm] {sig.action} {sym} registered — "
             f"target={sig.price:.6f}")
    return True


def _monitor_reversal_signals(exchange, open_pos_live):
    if not getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False):
        return
    if not _REVERSAL_STATES:
        return

    max_h  = float(getattr(CFG, 'REVERSAL_MAX_HOURS', 24.0))
    now    = _t_rc.time()
    throttle = float(getattr(CFG, 'REVERSAL_LIVE_FETCH_EVERY_S', 30.0))

    for sym in list(_REVERSAL_STATES.keys()):
        rec = _REVERSAL_STATES[sym]

        if (now - float(rec["created_at"])) > max_h * 3600:
            log.info(f"[RevConfirm] {sym} expired (age>{max_h}h)")
            _REVERSAL_STATES.pop(sym, None)
            continue

        if sym in open_pos_live or sym in _PENDING_ORDERS:
            _REVERSAL_STATES.pop(sym, None)
            continue

        if (now - _RC_FETCH_THROTTLE.get(sym, 0.0)) < throttle:
            continue
        _RC_FETCH_THROTTLE[sym] = now

        try:
            _rate_record(1.0)
            bars_raw = exchange.fetch_ohlcv(sym, rec["sub_tf"], limit=40)
        except Exception as e:
            log.debug(f"[RevConfirm] {sym} fetch failed: {e}")
            continue
        if not bars_raw or len(bars_raw) < 2:
            continue

        df = pd.DataFrame(
            bars_raw,
            columns=["ts", "Open", "High", "Low", "Close", "Volume"],
        )
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts").astype(float)
        df = df.iloc[:-1]   # drop the currently forming bar

        _unix = df.index.astype("int64") // 10**9
        new_bars = df[_unix > int(rec["last_scan_ts"])]
        if len(new_bars) == 0:
            continue

        action = rec["sig"].action
        target = float(rec["target"])
        sub_tf_sec = _sub_tf_seconds_simple(rec["sub_tf"])

        for ts, row in new_bars.iterrows():
            ts_unix = float(ts.value / 1e9)

            if rec["phase"] == "WAITING_TOUCH":
                _hit = ((action == "BUY" and row["Low"] <= target) or
                        (action == "SELL" and row["High"] >= target))
                if _hit:
                    rec["phase"]    = "WAITING_BOUNCE"
                    rec["touch_ts"] = ts_unix
                    log.info(f"[RevConfirm] {sym} TOUCH @ {ts}")

            elif rec["phase"] == "WAITING_BOUNCE":
                bw = int(getattr(CFG, 'REVERSAL_BOUNCE_WINDOW', 4))
                if (ts_unix - float(rec["touch_ts"])) > bw * sub_tf_sec:
                    log.info(f"[RevConfirm] {sym} bounce timeout")
                    _REVERSAL_STATES.pop(sym, None)
                    break

                _conf = ((action == "BUY" and row["Close"] > target) or
                         (action == "SELL" and row["Close"] < target))
                if _conf:
                    log.info(f"[RevConfirm] {sym} BOUNCE @ {ts} — "
                             f"placing pending entry")
                    try:
                        _to_s = float(getattr(CFG, 'PO_MAX_WAIT_S', 0) or 30.0)
                        place_pending_entry(
                            exchange, sym, rec["side"], rec["qty"],
                            rec["sig"],
                            timeout_s=_to_s,
                            leverage=int(rec["leverage"]),
                            ad=rec["ad_ref"],
                        )
                        try:
                            save_pending_orders()
                        except Exception:
                            pass
                    except Exception as e:
                        log.warning(f"[RevConfirm] {sym} place failed: {e}")
                    _REVERSAL_STATES.pop(sym, None)
                    break

            rec["last_scan_ts"] = ts_unix


# ═══════════════════════════════════════════════════════════════


'''
patch(ANCHOR_P7, MODULE_P7 + ANCHOR_P7,
      "P7: insert live reversal module")


# ═══════════════════════════════════════════════════════════════
# P8 — run_live: register instead of immediate entry
# ═══════════════════════════════════════════════════════════════
OLD_P8 = '''                            # ── Legacy immediate placement ──
                            _tf_sec_w = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600'''

NEW_P8 = '''                            # ══ [REVERSAL-CONFIRM LIVE] ══
                            if getattr(CFG, 'REVERSAL_CONFIRM_ENABLED',
                                        False):
                                _r_ok = _register_reversal_state(
                                    exchange, sym, sd, qty, sig,
                                    int(dynamic_leverage), assets[sym]
                                )
                                if _r_ok:
                                    continue

                            # ── Legacy immediate placement ──
                            _tf_sec_w = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600'''
patch(OLD_P8, NEW_P8,
      "P8: run_live register reversal state")


# ═══════════════════════════════════════════════════════════════
# P9 — run_live: call monitor each cycle (after monitor_watch_signals)
# ═══════════════════════════════════════════════════════════════
OLD_P9 = '''            try:
                monitor_watch_signals(
                    exchange, open_pos_live,
                    assets=assets if 'assets' in dir() else None,
                    loop_iter=loop_iter
                )
            except Exception as _e:
                log.warning(f"[Watch] monitor error: {_e}")'''

NEW_P9 = OLD_P9 + '''

            try:
                _monitor_reversal_signals(
                    exchange, open_pos_live
                )
            except Exception as _e:
                log.warning(f"[RevConfirm] monitor error: {_e}")'''
patch(OLD_P9, NEW_P9, "P9: run_live monitor call")


# ═══════════════════════════════════════════════════════════════
# P10 — argparse
# ═══════════════════════════════════════════════════════════════
ANCHOR_P10 = '''    p.add_argument("--no-fixed-price", action="store_true",
                   help="Disable fixed-price entry (allow reprice chasing)")'''

NEW_P10 = ANCHOR_P10 + '''
    p.add_argument("--reversal-confirm", action="store_true",
                   help="Enable Touch-and-Bounce entry filter")
    p.add_argument("--reversal-touch-window", type=int, default=None,
                   help="Sub-bars to wait for target touch (default 20)")
    p.add_argument("--reversal-bounce-window", type=int, default=None,
                   help="Sub-bars to confirm bounce (default 4)")
    p.add_argument("--reversal-max-hours", type=float, default=None,
                   help="Max signal age in hours (live, default 24)")'''
patch(ANCHOR_P10, NEW_P10, "P10: argparse flags")


# ═══════════════════════════════════════════════════════════════
# P11 — main() wiring
# ═══════════════════════════════════════════════════════════════
ANCHOR_P11 = '''    if args.no_fixed_price:
        CFG.PO_FIXED_PRICE = False
        log.info("[Backtest] --no-fixed-price: entry target will be derived "
                 "from close[sig.close_idx] × (1 ± PO_PENETRATION_BPS)")'''

NEW_P11 = ANCHOR_P11 + '''
    if getattr(args, "reversal_confirm", False):
        CFG.REVERSAL_CONFIRM_ENABLED = True
    if getattr(args, "reversal_touch_window", None) is not None:
        CFG.REVERSAL_TOUCH_WINDOW = int(args.reversal_touch_window)
    if getattr(args, "reversal_bounce_window", None) is not None:
        CFG.REVERSAL_BOUNCE_WINDOW = int(args.reversal_bounce_window)
    if getattr(args, "reversal_max_hours", None) is not None:
        CFG.REVERSAL_MAX_HOURS = float(args.reversal_max_hours)
    if CFG.REVERSAL_CONFIRM_ENABLED:
        log.info(f"[RevConfirm] ENABLED  touch={CFG.REVERSAL_TOUCH_WINDOW}sb"
                 f"  bounce={CFG.REVERSAL_BOUNCE_WINDOW}sb"
                 f"  max_age={CFG.REVERSAL_MAX_HOURS}h")'''
patch(ANCHOR_P11, NEW_P11, "P11: main() wiring")


# ═══════════════════════════════════════════════════════════════
# Save
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
