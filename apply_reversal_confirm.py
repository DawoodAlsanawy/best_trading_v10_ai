#!/usr/bin/env python3
"""
apply_reversal_subbars.py

Installs a sub-bar Touch-and-Bounce entry state machine into trading_2_live4.py.

Main TF (e.g. 4h) supplies:
  - action     (BUY / SELL)
  - target     (entry price from _backtest_entry_target)
  - close_idx  (signal bar)

Sub-bar TF (e.g. 15m) runs the state machine:
  PHASE 1 TOUCH  : first sub-bar whose low ≤ target (BUY) / high ≥ target (SELL)
  PHASE 2 BOUNCE : next sub-bars must confirm reversal (4 modes)
  PHASE 3 FILL   : return (confirm_main_ci, fill_px) to simulate_portfolio

Run:  python apply_reversal_subbars.py
"""
import os, re, sys, shutil, hashlib

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found", file=sys.stderr); sys.exit(1)

if "_check_reversal_fill_subbars" in open(SRC).read():
    print("✗ File already patched. Restore from .bak first.", file=sys.stderr)
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
# 1. CFG — 7 reversal parameters
# ═══════════════════════════════════════════════════════════════
CFG_ANCHOR = ("    LIVE_PARALLEL_RETRAIN: bool = True\n"
              "    LIVE_PARALLEL_WORKERS: int = 4")
CFG_NEW = CFG_ANCHOR + """

    # ══ [REVERSAL-CONFIRM] Touch-and-Bounce on SUB-BARS ══
    # Main TF gives (action, target, close_idx).
    # Sub-bar TF confirms entry via TOUCH → BOUNCE.
    REVERSAL_CONFIRM_ENABLED: bool = False
    REVERSAL_TOUCH_SUBBARS:  int   = 20       # 5h @ 15m sub-bar
    REVERSAL_BOUNCE_SUBBARS: int   = 4        # 1h @ 15m sub-bar
    REVERSAL_MAX_HOURS:      float = 24.0     # signal validity window
    REVERSAL_CONFIRM_MODE:   str   = "close_back"
    REVERSAL_CONFIRM_KAPPA:  float = 0.20     # for sigma_bounce mode
    REVERSAL_FILL_AT:        str   = "target" # target|close|best"""
patch(CFG_ANCHOR, CFG_NEW, "CFG: 7 REVERSAL parameters")

# ═══════════════════════════════════════════════════════════════
# 2. _align_subbars — return sub_closes as well
# ═══════════════════════════════════════════════════════════════
OLD_ALIGN = '''def _align_subbars(main_index, sub_df, sub_per_main, tf_sec):
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

NEW_ALIGN = '''def _align_subbars(main_index, sub_df, sub_per_main, tf_sec):
    """
    Align sub-bars to main-bar grid.
    Returns (sub_highs, sub_lows, sub_closes) each (n_main, sub_per_main).
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
patch(OLD_ALIGN, NEW_ALIGN, "_align_subbars: return 3 arrays")

# ═══════════════════════════════════════════════════════════════
# 3. AssetData — add sub_closes field
# ═══════════════════════════════════════════════════════════════
OLD_AD = '''    # ══ [SUB-BARS] ══
    sub_highs: Optional[np.ndarray] = None    # shape (n_bars, sub_per_main)
    sub_lows:  Optional[np.ndarray] = None
    sub_per_main: int = 0
    sub_tf: str = ""'''
NEW_AD = '''    # ══ [SUB-BARS] ══
    sub_highs:  Optional[np.ndarray] = None   # shape (n_bars, sub_per_main)
    sub_lows:   Optional[np.ndarray] = None
    sub_closes: Optional[np.ndarray] = None
    sub_per_main: int = 0
    sub_tf: str = ""'''
patch(OLD_AD, NEW_AD, "AssetData: add sub_closes field")

# ═══════════════════════════════════════════════════════════════
# 4. process_asset — unpack 3 values + pass sub_closes
# ═══════════════════════════════════════════════════════════════
OLD_PA = '''    _sub_h, _sub_l = None, None
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
NEW_PA = '''    _sub_h, _sub_l, _sub_c = None, None, None
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
patch(OLD_PA, NEW_PA, "process_asset: unpack sub_closes")

OLD_RET = '''        sub_highs=_sub_h,
        sub_lows=_sub_l,
        sub_per_main=_sub_pm,
        sub_tf=_sub_tf_name,
    )'''
NEW_RET = '''        sub_highs=_sub_h,
        sub_lows=_sub_l,
        sub_closes=_sub_c,
        sub_per_main=_sub_pm,
        sub_tf=_sub_tf_name,
    )'''
patch(OLD_RET, NEW_RET, "process_asset: pass sub_closes to AssetData")

# ═══════════════════════════════════════════════════════════════
# 5. Helper — _check_reversal_fill_subbars
# ═══════════════════════════════════════════════════════════════
HELPER_ANCHOR = "def precompute_entry_fills(assets, signals, max_wait_bars, pen_bps,"
HELPER = '''def _check_reversal_fill_subbars(ad, sig, target0, cfg,
                                  first_main_ci, deadline_main_ci):
    """
    [REVERSAL-CONFIRM / SUB-BARS] Touch-and-Bounce entry on sub-bars.

    Signal fires at close of main bar `sig.close_idx`.
    Scan sub-bars starting at (sig.close_idx + 1, sub_idx = 0).

    Returns (confirm_main_ci, fill_px) or None.
    """
    if ad.sub_highs is None or ad.sub_closes is None or ad.sub_per_main < 2:
        return None

    action  = sig.action
    sub_pm  = int(ad.sub_per_main)
    start_main = sig.close_idx + 1
    end_main   = min(deadline_main_ci, ad.sub_highs.shape[0])
    if end_main <= start_main:
        return None

    # Flatten sub-bar blocks into single arrays
    sh_flat = ad.sub_highs[start_main:end_main].reshape(-1)
    sl_flat = ad.sub_lows[start_main:end_main].reshape(-1)
    sc_flat = ad.sub_closes[start_main:end_main].reshape(-1)
    n_flat  = sh_flat.size
    if n_flat == 0:
        return None

    touch_win  = max(1, int(getattr(cfg, 'REVERSAL_TOUCH_SUBBARS', 20)))
    bounce_win = max(1, int(getattr(cfg, 'REVERSAL_BOUNCE_SUBBARS', 4)))
    mode = str(getattr(cfg, 'REVERSAL_CONFIRM_MODE', 'close_back'))

    # ── PHASE 1: TOUCH ──
    _touch_limit = min(touch_win, n_flat)
    touch_k = -1
    for k in range(_touch_limit):
        if not np.isfinite(sl_flat[k]) or not np.isfinite(sh_flat[k]):
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

    if mode == "close_back":
        for k in range(b0, b1):
            c = sc_flat[k]
            if not np.isfinite(c):
                continue
            if action == "BUY" and c > target0:
                confirm_k = k; break
            if action == "SELL" and c < target0:
                confirm_k = k; break

    elif mode == "two_bar":
        for k in range(b0, b1 - 1):
            c1, c2 = sc_flat[k], sc_flat[k + 1]
            if not (np.isfinite(c1) and np.isfinite(c2)):
                continue
            if action == "BUY" and c1 > target0 and c2 > target0:
                confirm_k = k + 1; break
            if action == "SELL" and c1 < target0 and c2 < target0:
                confirm_k = k + 1; break

    elif mode == "sigma_bounce":
        fi = int(sig.feat_idx)
        sigma_bar = 0.01
        if 0 <= fi < len(ad.E_therm):
            _s = float(ad.E_therm[fi])
            if np.isfinite(_s) and _s > 1e-9:
                sigma_bar = _s
        thr = (float(getattr(cfg, 'REVERSAL_CONFIRM_KAPPA', 0.20))
               * sigma_bar * float(target0))
        for k in range(b0, b1):
            c = sc_flat[k]
            if not np.isfinite(c):
                continue
            if action == "BUY" and (c - target0) > thr:
                confirm_k = k; break
            if action == "SELL" and (target0 - c) > thr:
                confirm_k = k; break

    elif mode == "bar_color":
        for k in range(b0, b1):
            c = sc_flat[k]
            c_prev = sc_flat[k - 1] if k > 0 else c
            if not (np.isfinite(c) and np.isfinite(c_prev)):
                continue
            if action == "BUY" and c > c_prev:
                confirm_k = k; break
            if action == "SELL" and c < c_prev:
                confirm_k = k; break

    if confirm_k < 0:
        return None

    # Flat index → main bar ci
    _main_offset = confirm_k // sub_pm
    confirm_main = start_main + _main_offset

    # ── PHASE 3: FILL ──
    fill_mode = str(getattr(cfg, 'REVERSAL_FILL_AT', 'target'))
    c_conf = float(sc_flat[confirm_k]) if np.isfinite(sc_flat[confirm_k]) else float(target0)
    if fill_mode == "close":
        fill_px = c_conf
    elif fill_mode == "best":
        fill_px = (min(float(target0), c_conf) if action == "BUY"
                   else max(float(target0), c_conf))
    else:
        fill_px = float(target0)

    return (int(confirm_main), float(fill_px))


'''
patch(HELPER_ANCHOR, HELPER + HELPER_ANCHOR,
      "helper: _check_reversal_fill_subbars")

# ═══════════════════════════════════════════════════════════════
# 6. Branch inside precompute_entry_fills
# ═══════════════════════════════════════════════════════════════
BRANCH_ANCHOR = '''            target0 = _backtest_entry_target(sig, ad)
            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)

            # ── Stage 1 ──'''

BRANCH_NEW = '''            target0 = _backtest_entry_target(sig, ad)
            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)

            # ═══ [REVERSAL-CONFIRM] Touch-and-Bounce on SUB-BARS ═══
            if getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False):
                _max_h = float(getattr(CFG, 'REVERSAL_MAX_HOURS', 24.0))
                _sub_h = CFG.TF_HOURS / max(int(ad.sub_per_main or 16), 1)
                _max_main_bars = max(1, int(np.ceil(
                    _max_h / max(_sub_h, 1e-6)
                )))
                _dl = min(sig.close_idx + _max_main_bars + 1, n_bars)
                _rev = _check_reversal_fill_subbars(
                    ad, sig, target0, CFG,
                    sig.close_idx + 1, _dl
                )
                if _rev is None:
                    result[sig_i] = None
                    continue
                _rev_main, _rev_px = _rev
                result[sig_i] = ('S1', int(_rev_main), float(_rev_px))
                continue

            # ── Stage 1 ──'''

patch(BRANCH_ANCHOR, BRANCH_NEW,
      "precompute_entry_fills: reversal branch")

# ═══════════════════════════════════════════════════════════════
# 7. argparse flags
# ═══════════════════════════════════════════════════════════════
ARG_ANCHOR = '''    p.add_argument("--no-fixed-price", action="store_true",
                   help="Disable fixed-price entry (allow reprice chasing)")'''
ARG_NEW = ARG_ANCHOR + '''
    # ══ [REVERSAL-CONFIRM] Touch-and-Bounce on sub-bars ══
    p.add_argument("--reversal-confirm", action="store_true",
                   help="Enable Touch-and-Bounce entry on sub-bars")
    p.add_argument("--reversal-touch-subbars", type=int, default=None,
                   help="Max sub-bars to wait for target touch (default 20)")
    p.add_argument("--reversal-bounce-subbars", type=int, default=None,
                   help="Max sub-bars after touch to confirm (default 4)")
    p.add_argument("--reversal-max-hours", type=float, default=None,
                   help="Signal validity window in hours (default 24)")
    p.add_argument("--reversal-mode", type=str, default=None,
                   choices=["close_back","two_bar",
                            "sigma_bounce","bar_color"],
                   help="Confirmation mode (default close_back)")
    p.add_argument("--reversal-kappa", type=float, default=None,
                   help="sigma multiplier for sigma_bounce (default 0.20)")
    p.add_argument("--reversal-fill", type=str, default=None,
                   choices=["target","close","best"],
                   help="Fill price source (default target)")'''
patch(ARG_ANCHOR, ARG_NEW, "argparse: 7 reversal flags")

# ═══════════════════════════════════════════════════════════════
# 8. main() wiring
# ═══════════════════════════════════════════════════════════════
WIRE_ANCHOR = '''    if args.no_fixed_price:
        CFG.PO_FIXED_PRICE = False
        log.info("[Backtest] --no-fixed-price: entry target will be derived "
                 "from close[sig.close_idx] × (1 ± PO_PENETRATION_BPS)")'''

WIRE_NEW = WIRE_ANCHOR + '''
    # ══ [REVERSAL-CONFIRM] wiring ══
    if getattr(args, "reversal_confirm", False):
        CFG.REVERSAL_CONFIRM_ENABLED = True
    if getattr(args, "reversal_touch_subbars", None) is not None:
        CFG.REVERSAL_TOUCH_SUBBARS = int(args.reversal_touch_subbars)
    if getattr(args, "reversal_bounce_subbars", None) is not None:
        CFG.REVERSAL_BOUNCE_SUBBARS = int(args.reversal_bounce_subbars)
    if getattr(args, "reversal_max_hours", None) is not None:
        CFG.REVERSAL_MAX_HOURS = float(args.reversal_max_hours)
    if getattr(args, "reversal_mode", None) is not None:
        CFG.REVERSAL_CONFIRM_MODE = str(args.reversal_mode)
    if getattr(args, "reversal_kappa", None) is not None:
        CFG.REVERSAL_CONFIRM_KAPPA = float(args.reversal_kappa)
    if getattr(args, "reversal_fill", None) is not None:
        CFG.REVERSAL_FILL_AT = str(args.reversal_fill)
    if CFG.REVERSAL_CONFIRM_ENABLED:
        log.info(f"[Reversal] ENABLED "
                 f"touch={CFG.REVERSAL_TOUCH_SUBBARS}sb "
                 f"bounce={CFG.REVERSAL_BOUNCE_SUBBARS}sb "
                 f"max={CFG.REVERSAL_MAX_HOURS}h "
                 f"mode={CFG.REVERSAL_CONFIRM_MODE} "
                 f"fill={CFG.REVERSAL_FILL_AT}")'''

patch(WIRE_ANCHOR, WIRE_NEW, "main(): reversal wiring")

# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
if s == orig:
    print("⚠  No changes — check anchors:", file=sys.stderr)
    for line in report: print("   " + line, file=sys.stderr)
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
