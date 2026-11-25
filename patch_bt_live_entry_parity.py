#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch script #3: Make Backtest entry mechanics match Live behavior faithfully.

Adds (when CFG.SIMULATE_LIVE_FAITHFULLY is True):
  1. sub_opens in _align_subbars / AssetData / process_asset (with cache key bump).
  2. Placement latency simulation (CFG.BT_ENTRY_LATENCY_SUBBARS, default=1 sub-bar).
  3. Live's 20 bps drift sanity gate at placement time (CFG.BT_LIVE_DRIFT_GATE).
  4. Live's GTX Post-Only (-5022) cross-book rejection at placement time
     (CFG.BT_LIVE_GTX_CHECK).
  5. Sub-bar-level Stage 1 fill search strictly AFTER placement latency, and
     exact fill sub-bar propagation to simulate_portfolio (plus end-of-bar
     sub_idx for Stage 2 market entries).
  6. CLI flags: --bt-latency-subbars N, --no-bt-entry-parity.

Usage:
  python patch_bt_live_entry_parity.py --target trading_published_pro_1h_fixed_BT.py --dry-run
  python patch_bt_live_entry_parity.py --target trading_published_pro_1h_fixed_BT.py
"""

import argparse
import os
import py_compile
import shutil
import sys
from datetime import datetime

PATCH_MARKER = "# [BT-LIVE-ENTRY-PARITY-APPLIED]"


def _default_target() -> str:
    for cand in (
        "trading_published_pro_1h_fixed_BT.py",
        "trading_published_pro_1h_fixed.py",
        "trading_published_pro_1h.py",
    ):
        if os.path.exists(cand):
            return cand
    return "trading_published_pro_1h_fixed_BT.py"


def apply_patch(target_path: str, dry_run: bool = False) -> None:
    if not os.path.exists(target_path):
        print(f"[ERROR] Target file not found: {target_path}", file=sys.stderr)
        sys.exit(1)

    with open(target_path, "r", encoding="utf-8") as f:
        src = f.read()

    if PATCH_MARKER in src:
        print(f"[OK] Patch already applied ({PATCH_MARKER} found). Nothing to do.")
        return

    replacements = [
        # ── 1. Marker ───────────────────────────────────────────────────
        (
            "patch marker 3",
            "# [LIVE-PARITY-FIXES] applied",
            "# [LIVE-PARITY-FIXES] applied\n" + PATCH_MARKER,
        ),

        # ── 2. Config fields ────────────────────────────────────────────
        (
            "Config BT entry parity knobs",
            "    SIMULATE_LIVE_FAITHFULLY: bool = True",
            """    SIMULATE_LIVE_FAITHFULLY: bool = True
    # ══ [BT-LIVE-ENTRY-PARITY] ══
    # Mirrors live placement conditions inside precompute_entry_fills:
    #   BT_ENTRY_LATENCY_SUBBARS : skip first N sub-bars of first_bar (delay)
    #   BT_LIVE_DRIFT_GATE       : drop if |target - p_at_place| > 4*PO_MAX_DRIFT_BPS
    #   BT_LIVE_GTX_CHECK        : drop if p_at_place already crossed target (-5022)
    BT_ENTRY_LATENCY_SUBBARS: int = 1
    BT_LIVE_DRIFT_GATE: bool = True
    BT_LIVE_GTX_CHECK: bool = True""",
        ),

        # ── 3. _align_subbars: include sub_opens ────────────────────────
        (
            "_align_subbars sub_opens",
            r'''def _align_subbars(main_index, sub_df, sub_per_main, tf_sec):
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

        # ══ [PERF-FIX] Vectorized alignment ══
        # Same result as the per-bar loop, but 50-100× faster.
        _m = len(sub_ts_ns)
        _lo_arr = np.searchsorted(sub_ts_ns, main_ns, side='left')
        _hi_arr = np.searchsorted(sub_ts_ns, main_ns + tf_ns, side='left')
        _counts = np.minimum(_hi_arr - _lo_arr, sub_per_main)
        if len(_counts) > 0:
            _max_k = int(min(int(_counts.max()), sub_per_main))
        else:
            _max_k = 0
        for _k in range(_max_k):
            _mask = _counts > _k
            if not _mask.any():
                continue
            _src_idx = _lo_arr[_mask] + _k
            _valid_2 = _src_idx < _m
            if not _valid_2.all():
                _mask_idx = np.where(_mask)[0][_valid_2]
                _src_idx = _src_idx[_valid_2]
            else:
                _mask_idx = np.where(_mask)[0]
            sub_highs[_mask_idx, _k]  = sub_high_vals[_src_idx]
            sub_lows[_mask_idx, _k]   = sub_low_vals[_src_idx]
            sub_closes[_mask_idx, _k] = sub_close_vals[_src_idx]
    except Exception as e:
        log.warning(f"[SubBars] align failed: {e}")
    return sub_highs, sub_lows, sub_closes''',
            r'''def _align_subbars(main_index, sub_df, sub_per_main, tf_sec):
    """
    Align sub-bars to main-bar grid.
    Returns (sub_opens, sub_highs, sub_lows, sub_closes) each (n_main, sub_per_main).
    Missing sub-bars are NaN.
    """
    n = len(main_index)
    sub_opens  = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    sub_highs  = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    sub_lows   = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    sub_closes = np.full((n, sub_per_main), np.nan, dtype=np.float64)
    if sub_df is None or len(sub_df) == 0 or sub_per_main <= 0:
        return sub_opens, sub_highs, sub_lows, sub_closes

    try:
        sub_ts_ns = sub_df.index.asi8
        sub_open_vals  = sub_df['Open'].values.astype(np.float64)
        sub_high_vals  = sub_df['High'].values.astype(np.float64)
        sub_low_vals   = sub_df['Low'].values.astype(np.float64)
        sub_close_vals = sub_df['Close'].values.astype(np.float64)
        main_ns = main_index.asi8
        tf_ns = int(tf_sec * 1_000_000_000)

        # ══ [PERF-FIX] Vectorized alignment ══
        # Same result as the per-bar loop, but 50-100× faster.
        _m = len(sub_ts_ns)
        _lo_arr = np.searchsorted(sub_ts_ns, main_ns, side='left')
        _hi_arr = np.searchsorted(sub_ts_ns, main_ns + tf_ns, side='left')
        _counts = np.minimum(_hi_arr - _lo_arr, sub_per_main)
        if len(_counts) > 0:
            _max_k = int(min(int(_counts.max()), sub_per_main))
        else:
            _max_k = 0
        for _k in range(_max_k):
            _mask = _counts > _k
            if not _mask.any():
                continue
            _src_idx = _lo_arr[_mask] + _k
            _valid_2 = _src_idx < _m
            if not _valid_2.all():
                _mask_idx = np.where(_mask)[0][_valid_2]
                _src_idx = _src_idx[_valid_2]
            else:
                _mask_idx = np.where(_mask)[0]
            sub_opens[_mask_idx, _k]  = sub_open_vals[_src_idx]
            sub_highs[_mask_idx, _k]  = sub_high_vals[_src_idx]
            sub_lows[_mask_idx, _k]   = sub_low_vals[_src_idx]
            sub_closes[_mask_idx, _k] = sub_close_vals[_src_idx]
    except Exception as e:
        log.warning(f"[SubBars] align failed: {e}")
    return sub_opens, sub_highs, sub_lows, sub_closes''',
        ),

        # ── 4. AssetData: add sub_opens field ───────────────────────────
        (
            "AssetData sub_opens field",
            r'''    # ══ [SUB-BARS] ══
    sub_highs:  Optional[np.ndarray] = None   # shape (n_bars, sub_per_main)
    sub_lows:   Optional[np.ndarray] = None
    sub_closes: Optional[np.ndarray] = None''',
            r'''    # ══ [SUB-BARS] ══
    sub_opens:  Optional[np.ndarray] = None   # shape (n_bars, sub_per_main)
    sub_highs:  Optional[np.ndarray] = None
    sub_lows:   Optional[np.ndarray] = None
    sub_closes: Optional[np.ndarray] = None''',
        ),

        # ── 5. process_asset: store sub_opens ───────────────────────────
        (
            "process_asset sub_opens unpack",
            r'''    # ══ [SUB-BARS] Align finer bars to the main grid ══
    _sub_h, _sub_l, _sub_c = None, None, None
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
                )''',
            r'''    # ══ [SUB-BARS] Align finer bars to the main grid ══
    _sub_o, _sub_h, _sub_l, _sub_c = None, None, None, None
    _sub_pm = 0
    _sub_tf_name = ""
    if (getattr(CFG, 'SUBBARS_ENABLED', True)
            and sub_df is not None and len(sub_df) > 0):
        _sub_tf_name = _get_subbars_tf(CFG.timeframe) or ""
        if _sub_tf_name:
            _sub_pm = _sub_per_main(CFG.timeframe, _sub_tf_name)
            if _sub_pm >= 2:
                _sub_o, _sub_h, _sub_l, _sub_c = _align_subbars(
                    ts, sub_df, _sub_pm, int(CFG.TF_SECONDS)
                )''',
        ),
        (
            "process_asset AssetData sub_opens pass",
            r'''        sub_highs=_sub_h,
        sub_lows=_sub_l,
        sub_closes=_sub_c,''',
            r'''        sub_opens=_sub_o,
        sub_highs=_sub_h,
        sub_lows=_sub_l,
        sub_closes=_sub_c,''',
        ),

        # ── 6. Bump AssetData cache signature ──────────────────────────
        (
            "AssetData cache key bump",
            '        f"LEVMAX={cfg.LEVERAGE_MAX}"\n    )',
            '        f"LEVMAX={cfg.LEVERAGE_MAX}|SBOPEN=1"\n    )',
        ),

        # ── 7. precompute_entry_fills parity gates + sub-bar latency ────
        (
            "precompute_entry_fills parity stats init",
            r'''    _unified = bool(getattr(CFG, 'UNIFIED_ENTRY_ENABLED', True))
    _stage1_bars = effective_bars(
        int(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))
    )
    _max_age_bars = effective_bars(
        int(getattr(CFG, 'UNIFIED_MAX_AGE_BARS_1H', 12))
    )''',
            r'''    _unified = bool(getattr(CFG, 'UNIFIED_ENTRY_ENABLED', True))
    _stage1_bars = effective_bars(
        int(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))
    )
    _max_age_bars = effective_bars(
        int(getattr(CFG, 'UNIFIED_MAX_AGE_BARS_1H', 12))
    )
    _sim_live_pe = bool(getattr(CFG, 'SIMULATE_LIVE_FAITHFULLY', False))
    _lat_sb = (max(0, int(getattr(CFG, 'BT_ENTRY_LATENCY_SUBBARS', 1)))
               if _sim_live_pe else 0)
    _bt_rej_drift = 0
    _bt_rej_gtx = 0
    _bt_rej_window = 0''',
        ),
        (
            "precompute_entry_fills Stage 1 latency, drift gate, GTX check",
            r'''            target0 = _backtest_entry_target(sig, ad)
            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)

            # ═══ [REVERSAL-CONFIRM] Touch-and-Bounce on SUB-BARS ═══
            if getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False):
                _max_h = float(getattr(CFG, 'REVERSAL_MAX_HOURS', 24.0))
                # [REV-FIX v1] main-bar hours (was sub-bar hours -> 96 bars instead of 6)
                _max_main_bars = max(1, int(np.ceil(
                    _max_h / max(float(CFG.TF_HOURS), 1e-6)
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

            # ── Stage 1 ──
            # [PARITY-FIX] Fill criterion now matches live exactly:
            #   Live places the order at `base × (1 ∓ pen)` and the exchange
            #   fills it when the market reaches that price.
            #   Backtest previously required an EXTRA penetration
            #   (need_low = target × (1 - pen)) → ~half the fills of live.
            #   Now: fill when market simply touches the target.
            stage1_fill = None
            for bar in range(first_bar, stage1_last):
                if (time_decay_enabled and ref_px > 0 and base_dip > 0):
                    bars_elapsed = bar - sig.close_idx
                    if bars_elapsed > int(time_decay_bars[2]):
                        mult = float(time_decay_mults[2])
                    elif bars_elapsed > int(time_decay_bars[1]):
                        mult = float(time_decay_mults[1])
                    elif bars_elapsed > int(time_decay_bars[0]):
                        mult = float(time_decay_mults[0])
                    else:
                        mult = 1.0
                    eff_dip = base_dip * mult
                    eff_target = (ref_px - eff_dip) if sig.action == "BUY" \
                                 else (ref_px + eff_dip)
                else:
                    eff_target = target0

                if sig.action == "BUY":
                    # Live semantics: order sits AT eff_target; fills when
                    # market price reaches it (low ≤ eff_target).
                    if ad.lows[bar] <= eff_target:
                        fill_px = eff_target if use_time_decay_price \
                                  else target0
                        stage1_fill = (bar, fill_px)
                        break
                else:
                    # Live semantics: order sits AT eff_target; fills when
                    # market price reaches it (high ≥ eff_target).
                    if ad.highs[bar] >= eff_target:
                        fill_px = eff_target if use_time_decay_price \
                                  else target0
                        stage1_fill = (bar, fill_px)
                        break

            if stage1_fill is not None:
                result[sig_i] = ('S1', stage1_fill[0], stage1_fill[1])
                continue''',
            r'''            target0 = _backtest_entry_target(sig, ad)
            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)
            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)

            # ═══ [REVERSAL-CONFIRM] Touch-and-Bounce on SUB-BARS ═══
            if getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False):
                _max_h = float(getattr(CFG, 'REVERSAL_MAX_HOURS', 24.0))
                # [REV-FIX v1] main-bar hours (was sub-bar hours -> 96 bars instead of 6)
                _max_main_bars = max(1, int(np.ceil(
                    _max_h / max(float(CFG.TF_HOURS), 1e-6)
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

            # ══ [BT-LIVE-ENTRY-PARITY] Determine market price at placement ══
            _use_sub_s1 = (
                ad.sub_highs is not None
                and ad.sub_lows is not None
                and ad.sub_per_main >= 2
                and first_bar < ad.sub_highs.shape[0]
            )
            _sub_opens_arr = getattr(ad, 'sub_opens', None)

            if _sim_live_pe and first_bar < stage1_last:
                _p_at_place = 0.0
                if _use_sub_s1:
                    _pm_s1 = int(ad.sub_per_main)
                    _place_bar = first_bar + (_lat_sb // _pm_s1)
                    _place_k = _lat_sb % _pm_s1
                    if _place_bar >= stage1_last:
                        _bt_rej_window += 1
                        result[sig_i] = None
                        continue
                    if (_sub_opens_arr is not None
                            and _place_bar < _sub_opens_arr.shape[0]):
                        _v_o = float(_sub_opens_arr[_place_bar, _place_k])
                        if np.isfinite(_v_o) and _v_o > 0:
                            _p_at_place = _v_o
                    if _p_at_place <= 0 and ad.sub_closes is not None:
                        _prev_b = _place_bar if _place_k > 0 else (_place_bar - 1)
                        _prev_k = (_place_k - 1) if _place_k > 0 else (_pm_s1 - 1)
                        if 0 <= _prev_b < ad.sub_closes.shape[0]:
                            _v_c = float(ad.sub_closes[_prev_b, _prev_k])
                            if np.isfinite(_v_c) and _v_c > 0:
                                _p_at_place = _v_c
                if _p_at_place <= 0:
                    _p_at_place = float(ad.closes[sig.close_idx])

                # Gate 1: Live's 20 bps drift sanity gate (place_pending_entry)
                if (getattr(CFG, 'BT_LIVE_DRIFT_GATE', True)
                        and not getattr(CFG, 'PO_FIXED_PRICE', True)
                        and _p_at_place > 0):
                    _gap_bps = abs(target0 - _p_at_place) / _p_at_place * 1e4
                    _max_gap = float(getattr(CFG, 'PO_MAX_DRIFT_BPS', 5.0)) * 4.0
                    if _gap_bps > _max_gap:
                        _bt_rej_drift += 1
                        result[sig_i] = None
                        continue

                # Gate 2: Live's GTX Post-Only (-5022) cross-book rejection
                if getattr(CFG, 'BT_LIVE_GTX_CHECK', True) and _p_at_place > 0:
                    if sig.action == "BUY" and _p_at_place <= target0:
                        _bt_rej_gtx += 1
                        result[sig_i] = None
                        continue
                    if sig.action == "SELL" and _p_at_place >= target0:
                        _bt_rej_gtx += 1
                        result[sig_i] = None
                        continue

            # ── Stage 1 ──
            stage1_fill = None
            _sub_wait_cap_k = None
            if (_sim_live_pe and not _unified
                    and float(getattr(CFG, 'PO_MAX_WAIT_S', 0) or 0) > 0
                    and _use_sub_s1):
                _tf_s_pe = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                _sub_s_pe = max(1.0, float(_tf_s_pe) / float(ad.sub_per_main))
                _sub_wait_cap_k = _lat_sb + max(
                    1, int(np.ceil(float(CFG.PO_MAX_WAIT_S) / _sub_s_pe))
                )

            for bar in range(first_bar, stage1_last):
                if (time_decay_enabled and ref_px > 0 and base_dip > 0):
                    bars_elapsed = bar - sig.close_idx
                    if bars_elapsed > int(time_decay_bars[2]):
                        mult = float(time_decay_mults[2])
                    elif bars_elapsed > int(time_decay_bars[1]):
                        mult = float(time_decay_mults[1])
                    elif bars_elapsed > int(time_decay_bars[0]):
                        mult = float(time_decay_mults[0])
                    else:
                        mult = 1.0
                    eff_dip = base_dip * mult
                    eff_target = (ref_px - eff_dip) if sig.action == "BUY" \
                                 else (ref_px + eff_dip)
                else:
                    eff_target = target0

                if _use_sub_s1 and bar < ad.sub_highs.shape[0]:
                    _pm_b = int(ad.sub_per_main)
                    _offset_from_first = (bar - first_bar) * _pm_b
                    _k0 = max(0, _lat_sb - _offset_from_first)
                    _k1 = _pm_b
                    if _sub_wait_cap_k is not None:
                        _k1 = min(_k1, max(0, _sub_wait_cap_k - _offset_from_first))
                    _any_finite_sb = False
                    for _k in range(_k0, _k1):
                        _sh = ad.sub_highs[bar, _k]
                        _sl = ad.sub_lows[bar, _k]
                        if not (np.isfinite(_sh) and np.isfinite(_sl)):
                            continue
                        _any_finite_sb = True
                        if sig.action == "BUY":
                            if _sl <= eff_target:
                                fill_px = eff_target if use_time_decay_price else target0
                                stage1_fill = (bar, fill_px, _k)
                                break
                        else:
                            if _sh >= eff_target:
                                fill_px = eff_target if use_time_decay_price else target0
                                stage1_fill = (bar, fill_px, _k)
                                break
                    if stage1_fill is not None:
                        break
                    # Only fall back to main bar if NO sub-bars were valid and
                    # we didn't intentionally skip the bar via latency/cap
                    if not _any_finite_sb and _k0 == 0 and _k1 == _pm_b:
                        if sig.action == "BUY" and ad.lows[bar] <= eff_target:
                            fill_px = eff_target if use_time_decay_price else target0
                            stage1_fill = (bar, fill_px, -1)
                            break
                        if sig.action == "SELL" and ad.highs[bar] >= eff_target:
                            fill_px = eff_target if use_time_decay_price else target0
                            stage1_fill = (bar, fill_px, -1)
                            break
                else:
                    if sig.action == "BUY":
                        if ad.lows[bar] <= eff_target:
                            fill_px = eff_target if use_time_decay_price \
                                      else target0
                            stage1_fill = (bar, fill_px, -1)
                            break
                    else:
                        if ad.highs[bar] >= eff_target:
                            fill_px = eff_target if use_time_decay_price \
                                      else target0
                            stage1_fill = (bar, fill_px, -1)
                            break

            if stage1_fill is not None:
                result[sig_i] = ('S1', stage1_fill[0], stage1_fill[1], stage1_fill[2])
                continue''',
        ),
        (
            "precompute_entry_fills parity summary log",
            r'''    return result

# ════════════════════════════════════════════════════════════════
# § 14.55  Watch-Mode Backtest Fill Precompute''',
            r'''    if _sim_live_pe:
        log.info(
            f"  [BT-Live-Parity] lat_subbars={_lat_sb} | "
            f"rej_drift={_bt_rej_drift:,} | rej_gtx={_bt_rej_gtx:,} | "
            f"rej_lat_win={_bt_rej_window:,}"
        )
    return result

# ════════════════════════════════════════════════════════════════
# § 14.55  Watch-Mode Backtest Fill Precompute''',
        ),

        # ── 8. simulate_portfolio: handle 4-tuple S1 + S2 end-of-bar sub_idx ──
        (
            "simulate_portfolio unpack S1 4-tuple",
            r'''        _is_stage2 = False
        _stage2_sl = _stage2_tp = _stage2_sl_dist = None

        if len(fill_info) >= 2 and isinstance(fill_info[0], str):
            if fill_info[0] == 'S1':
                _, opt_ci, opt_px = fill_info
            elif fill_info[0] == 'S2':
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist \
                    = fill_info
                _is_stage2 = True
            else:
                continue
        else:
            # توافق مع الصيغة القديمة
            opt_ci, opt_px = fill_info''',
            r'''        _is_stage2 = False
        _stage2_sl = _stage2_tp = _stage2_sl_dist = None
        _fill_sub_idx = -1

        if len(fill_info) >= 2 and isinstance(fill_info[0], str):
            if fill_info[0] == 'S1':
                opt_ci = fill_info[1]
                opt_px = fill_info[2]
                if len(fill_info) >= 4:
                    _fill_sub_idx = int(fill_info[3])
            elif fill_info[0] == 'S2':
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist \
                    = fill_info
                _is_stage2 = True
            else:
                continue
        else:
            # توافق مع الصيغة القديمة
            opt_ci, opt_px = fill_info''',
        ),
        (
            "simulate_portfolio opt_sub_idx parity",
            r'''        opt_sub_idx = 0
        if (ad.sub_highs is not None and ad.sub_lows is not None
                and ad.sub_per_main >= 2
                and 0 <= opt_ci < ad.sub_highs.shape[0]):
            _pen_frac_sb = CFG.FILL_PENETRATION_BPS * 1e-4
            if sig.action == "BUY":
                _need_low = opt_px * (1.0 - _pen_frac_sb)
                _row = ad.sub_lows[opt_ci]
                _idx = np.where(_row <= _need_low)[0]
                if len(_idx) > 0:
                    opt_sub_idx = int(_idx[0])
            else:
                _need_high = opt_px * (1.0 + _pen_frac_sb)
                _row = ad.sub_highs[opt_ci]
                _idx = np.where(_row >= _need_high)[0]
                if len(_idx) > 0:
                    opt_sub_idx = int(_idx[0])''',
            r'''        opt_sub_idx = 0
        if (ad.sub_highs is not None and ad.sub_lows is not None
                and ad.sub_per_main >= 2
                and 0 <= opt_ci < ad.sub_highs.shape[0]):
            if _is_stage2:
                # Stage 2 enters at bar close -> no remaining sub-bars in opt_ci
                opt_sub_idx = int(ad.sub_per_main) - 1
            elif _fill_sub_idx >= 0:
                opt_sub_idx = int(_fill_sub_idx)
            else:
                _pen_frac_sb = CFG.FILL_PENETRATION_BPS * 1e-4
                _sb_start = (int(getattr(CFG, 'BT_ENTRY_LATENCY_SUBBARS', 1))
                             if (_sim_live and opt_ci == sig.close_idx + 1) else 0)
                _sb_start = max(0, min(_sb_start, int(ad.sub_per_main) - 1))
                if sig.action == "BUY":
                    _need_low = opt_px * (1.0 - _pen_frac_sb)
                    _row = ad.sub_lows[opt_ci][_sb_start:]
                    _idx = np.where(_row <= _need_low)[0]
                    if len(_idx) > 0:
                        opt_sub_idx = _sb_start + int(_idx[0])
                else:
                    _need_high = opt_px * (1.0 + _pen_frac_sb)
                    _row = ad.sub_highs[opt_ci][_sb_start:]
                    _idx = np.where(_row >= _need_high)[0]
                    if len(_idx) > 0:
                        opt_sub_idx = _sb_start + int(_idx[0])''',
        ),

        # ── 9. CLI flags in main() ──────────────────────────────────────
        (
            "CLI args for BT live entry parity",
            r'''    p.add_argument("--no-fixed-price", action="store_true",
                   help="Disable fixed-price entry (allow reprice chasing)")''',
            r'''    p.add_argument("--no-fixed-price", action="store_true",
                   help="Disable fixed-price entry (allow reprice chasing)")
    p.add_argument("--bt-latency-subbars", type=int, default=None,
                   help="Backtest entry latency in sub-bars (default 1 = ~5m on 1h)")
    p.add_argument("--no-bt-entry-parity", action="store_true",
                   help="Disable backtest latency, 20bps drift gate & GTX check")''',
        ),
        (
            "CLI wiring for BT live entry parity",
            r'''    if args.no_fixed_price:
        CFG.PO_FIXED_PRICE = False
        log.info("[Backtest] --no-fixed-price: entry target will be derived "
                 "from close[sig.close_idx] × (1 ± PO_PENETRATION_BPS)")''',
            r'''    if args.no_fixed_price:
        CFG.PO_FIXED_PRICE = False
        log.info("[Backtest] --no-fixed-price: entry target will be derived "
                 "from close[sig.close_idx] × (1 ± PO_PENETRATION_BPS)")
    if getattr(args, "bt_latency_subbars", None) is not None:
        CFG.BT_ENTRY_LATENCY_SUBBARS = max(0, int(args.bt_latency_subbars))
        log.info(f"[BT-Live-Parity] BT_ENTRY_LATENCY_SUBBARS = {CFG.BT_ENTRY_LATENCY_SUBBARS}")
    if getattr(args, "no_bt_entry_parity", False):
        CFG.BT_ENTRY_LATENCY_SUBBARS = 0
        CFG.BT_LIVE_DRIFT_GATE = False
        CFG.BT_LIVE_GTX_CHECK = False
        log.info("[BT-Live-Parity] DISABLED via --no-bt-entry-parity")''',
        ),
    ]

    for name, old, _ in replacements:
        cnt = src.count(old)
        if cnt != 1:
            print(
                f"[ERROR] Hunk '{name}' matched {cnt} times (expected 1). Aborting.",
                file=sys.stderr,
            )
            sys.exit(2)

    patched = src
    for name, old, new in replacements:
        patched = patched.replace(old, new, 1)
        print(f"[PATCH] Applied: {name}")

    if dry_run:
        print("[DRY-RUN] All hunks matched cleanly. No files were modified.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{target_path}.bak_{ts}"
    shutil.copy2(target_path, backup_path)
    print(f"[BACKUP] Created: {backup_path}")

    tmp_path = f"{target_path}.patched.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(patched)
        py_compile.compile(tmp_path, doraise=True)
        os.replace(tmp_path, target_path)
        print(f"[SUCCESS] Patched & syntax-verified: {target_path}")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"[ERROR] Verification failed, original file untouched: {e}", file=sys.stderr)
        sys.exit(3)


def main():
    parser = argparse.ArgumentParser(description="Patch backtest entry mechanics to mirror live behavior")
    parser.add_argument("--target", default=_default_target(), help="Path to target script")
    parser.add_argument("--dry-run", action="store_true", help="Verify matches without modifying file")
    args = parser.parse_args()
    apply_patch(args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
