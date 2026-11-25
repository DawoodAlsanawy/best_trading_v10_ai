#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch script #4: Live Speed & Execution Parity with Backtest.

Fixes why Live misses trades that the fixed Backtest catches:
  1. Parallel OHLCV fetch (ThreadPoolExecutor) + defer gap healing away
     from candle-close hot cycle.
  2. Cache KMeans model per symbol for LIVE_KM_CACHE_HOURS (12h) and pass
     via km_ext (with dyn_k synced to km.n_clusters), eliminating the
     multi-symbol KMeans retrain bottleneck every hour.
  3. Align loop sleep to wake right at candle close + 0.4s.
  4. Replace the fixed 20 bps drift killer gate in place_pending_entry
     with a volatility-scaled sanity guard (3 * sigma_bar).
  5. When market price already crossed target (or Binance rejects GTX
     with -5022), fall back to a regular Limit order capped at `target`
     so the trade fills at `target` or better instead of being dropped.
  6. Fetch exchange positions once before the signal entry loop (avoiding
     N sequential REST calls) and fix Stage 2 capital basis to honor
     LIVE_TRADING_CAPITAL / wallet balance.

Usage:
  python patch_live_parity_speed.py --dry-run
  python patch_live_parity_speed.py
"""

import argparse
import os
import py_compile
import shutil
import sys
from datetime import datetime

PATCH_MARKER = "# [LIVE-PARITY-SPEED-APPLIED]"


def _default_target() -> str:
    for cand in (
        "trading_published_pro_1h_fixed_LV.py",
        "trading_published_pro_1h_fixed_LV.py",
    ):
        if os.path.exists(cand):
            return cand
    return "trading_published_pro_1h_fixed_LV.py"


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
            "patch marker 4",
            "# [LIVE-PARITY-FIXES] applied",
            "# [LIVE-PARITY-FIXES] applied\n" + PATCH_MARKER,
        ),

        # ── 2. Config knobs ─────────────────────────────────────────────
        (
            "Config live speed & execution parity knobs",
            r'''    # ══ [PERF-FIX] Parallel retrain via ThreadPoolExecutor ══
    # sklearn KMeans releases the GIL → concurrent calls scale on multi-core.
    LIVE_PARALLEL_RETRAIN: bool = True
    LIVE_PARALLEL_WORKERS: int = 4''',
            r'''    # ══ [PERF-FIX] Parallel retrain via ThreadPoolExecutor ══
    # sklearn KMeans releases the GIL → concurrent calls scale on multi-core.
    LIVE_PARALLEL_RETRAIN: bool = True
    LIVE_PARALLEL_WORKERS: int = 4
    # ══ [LIVE-PARITY-SPEED] Low-latency candle close & entry parity ══
    LIVE_PARALLEL_OHLCV: bool = True
    LIVE_OHLCV_WORKERS: int = 8
    LIVE_KM_CACHE_HOURS: float = 12.0      # reuse KMeans model unless K changes
    LIVE_WAKE_ON_CLOSE: bool = True        # wake right at candle close + 0.4s
    LIVE_MAX_ENTRY_GAP_SIGMA: float = 3.0  # sanity cap in sigma_bar (0=disabled)
    LIVE_ALLOW_CROSSED_LIMIT: bool = True  # on crossed target / -5022 -> Limit @ target''',
        ),

        # ── 3. Sync dyn_k to km_ext.n_clusters in process_asset ─────────
        (
            "process_asset km_ext dyn_k sync",
            r'''    if km_ext is not None:
        # External KMeans provided -> trust it, keep strict behavior
        km = km_ext
        sym_q = assign(X, km)''',
            r'''    if km_ext is not None:
        # External KMeans provided -> trust it & keep cluster count in sync
        km = km_ext
        dyn_k = int(getattr(km, 'n_clusters', dyn_k))
        sym_q = assign(X, km)''',
        ),

        # ── 4. Add _LIVE_KM_CACHE dict near _LIVE_ASSET_CACHE ───────────
        (
            "_LIVE_KM_CACHE global dict",
            "_LIVE_ASSET_CACHE: Dict[Tuple[str, str, int], \"AssetData\"] = {}",
            "_LIVE_ASSET_CACHE: Dict[Tuple[str, str, int], \"AssetData\"] = {}\n"
            "_LIVE_KM_CACHE: Dict[str, Dict] = {}   # {sym: {'km', 'k', 'k_req', 'ts'}}",
        ),

        # ── 5. Stage 2 capital basis in monitor_pending_orders ──────────
        (
            "monitor_pending_orders Stage 2 capital basis",
            r'''                                    _cap_now = float(rec.get('capital_at_placement')
                                                     or 0)
                                    if _cap_now <= 0:
                                        try:
                                            _bal = exchange.fetch_balance()
                                            _cap_now = float(
                                                _bal['USDT']['free']
                                            )
                                        except Exception:
                                            _cap_now = 0.0''',
            r'''                                    _cap_now = float(rec.get('capital_at_placement')
                                                     or 0)
                                    if _cap_now <= 0:
                                        _fixed_c2 = float(getattr(CFG, 'LIVE_TRADING_CAPITAL', 0.0))
                                        if _fixed_c2 > 0:
                                            _cap_now = _fixed_c2
                                        else:
                                            try:
                                                _bal = exchange.fetch_balance()
                                                _free_b = float(_bal['USDT'].get('free') or 0.0)
                                                _cap_now = _lv_wallet_usdt(_bal, fallback=_free_b)
                                            except Exception:
                                                _cap_now = 0.0''',
        ),

        # ── 6. place_pending_entry: sigma drift gate + crossed Limit ────
        (
            "place_pending_entry sigma drift gate",
            r'''        # Sanity gate: live-only (backtest has no live mid).
        # Applies in --no-fixed-price mode only.
        if not getattr(CFG, 'PO_FIXED_PRICE', True):
            try:
                ob = exchange.fetch_order_book(sym, limit=5)
                _mid = (float(ob['bids'][0][0])
                        + float(ob['asks'][0][0])) / 2.0
                if _mid > 0:
                    _gap_bps = abs(target - _mid) / _mid * 1e4
                    _max_gap = float(
                        getattr(CFG, 'PO_MAX_DRIFT_BPS', 5.0)
                    ) * 4.0
                    if _gap_bps > _max_gap:
                        log.info(
                            f"[Pending] {sym} target {target:.6f} "
                            f"is {_gap_bps:.1f}bps from mid "
                            f"(> {_max_gap:.1f}) — skip"
                        )
                        return None
            except Exception:
                pass''',
            r'''        # Sanity gate + capture top-of-book to detect already-crossed targets.
        _ob_bid = 0.0
        _ob_ask = 0.0
        try:
            ob = exchange.fetch_order_book(sym, limit=5)
            _ob_bid = float(ob['bids'][0][0])
            _ob_ask = float(ob['asks'][0][0])
            _mid = (_ob_bid + _ob_ask) / 2.0
            if (not getattr(CFG, 'PO_FIXED_PRICE', True)) and _mid > 0:
                _gap_bps = abs(target - _mid) / _mid * 1e4
                _gap_sig_mult = float(getattr(CFG, 'LIVE_MAX_ENTRY_GAP_SIGMA', 3.0))
                if _gap_sig_mult > 0:
                    _max_gap = max(
                        float(getattr(CFG, 'PO_MAX_DRIFT_BPS', 5.0)) * 4.0,
                        _gap_sig_mult * _sig_for_off * 1e4,
                    )
                    if _gap_bps > _max_gap:
                        log.info(
                            f"[Pending] {sym} target {target:.6f} "
                            f"is {_gap_bps:.1f}bps from mid "
                            f"(> {_max_gap:.1f}) — skip"
                        )
                        return None
        except Exception:
            pass''',
        ),
        (
            "place_pending_entry crossed-limit & -5022 fallback",
            r'''    # ══ وضع الأمر النهائي ══
    if _exec_mode == "gtx":
        try:
            o = exchange.create_order(
                sym, 'limit', side, qty, target,
                params={'timeInForce': 'GTX'}
            )
        except Exception as e:
            log.debug(f"[Pending] {sym} GTX rejected @ {target:.6f}: {e}")
            return None''',
            r'''    # ══ وضع الأمر النهائي ══
    if _exec_mode == "gtx":
        _allow_crossed = bool(getattr(CFG, 'LIVE_ALLOW_CROSSED_LIMIT', True))
        _already_crossed = _allow_crossed and (
            (side == 'buy' and _ob_ask > 0 and target >= _ob_ask)
            or (side == 'sell' and _ob_bid > 0 and target <= _ob_bid)
        )
        if _already_crossed:
            try:
                o = exchange.create_order(
                    sym, 'limit', side, qty, target, params={}
                )
                _exec_mode = "limit_capped"
                log.info(
                    f"[Pending] {sym} market already at target "
                    f"(bid={_ob_bid:.6f}, ask={_ob_ask:.6f}) -> "
                    f"Limit @ {target:.6f}"
                )
            except Exception as e:
                log.debug(f"[Pending] {sym} capped limit failed @ {target:.6f}: {e}")
                return None
        else:
            try:
                o = exchange.create_order(
                    sym, 'limit', side, qty, target,
                    params={'timeInForce': 'GTX'}
                )
            except Exception as e:
                _emsg = str(e)
                if _allow_crossed and (
                    "-5022" in _emsg or "Post Only" in _emsg
                    or "post only" in _emsg or "immediately match" in _emsg
                ):
                    try:
                        o = exchange.create_order(
                            sym, 'limit', side, qty, target, params={}
                        )
                        _exec_mode = "limit_capped"
                        log.info(
                            f"[Pending] {sym} GTX -5022 -> Limit @ {target:.6f}"
                        )
                    except Exception as e2:
                        log.debug(f"[Pending] {sym} fallback limit failed @ {target:.6f}: {e2}")
                        return None
                else:
                    log.debug(f"[Pending] {sym} GTX rejected @ {target:.6f}: {e}")
                    return None''',
        ),

        # ── 7. run_live: parallel OHLCV + KMeans cache + deferred heal ──
        (
            "run_live parallel OHLCV fetch & cached KMeans retrain",
            r'''            _to_retrain = []
            for sym in top_syms:
                if sym not in cached_data: continue
                try:
                    # ── Fast path: no new bar ──
                    if _smart and not _needs_ohlcv_refresh(cached_data[sym], _tf_sec_local):
                        _ohlcv_skipped += 1
                        _tf_sec_s = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                        _lc_ts = _last_closed_bar_ts(cached_data[sym], _tf_sec_s)
                        _current_last_closed[sym] = _lc_ts
                        ad = _live_cache_get(sym, cfg.timeframe, _lc_ts)
                        if ad is not None:
                            assets[sym] = ad
                            continue
                        if _degenerate_get(sym, cfg.timeframe, _lc_ts):
                            continue
                        if _degenerate_banned(sym):
                            continue
                        _min_bars = int(getattr(CFG, 'LIVE_MIN_BARS_FOR_PROCESS', 2000))
                        if len(cached_data[sym]) < _min_bars:
                            log.debug(f"[Warmup] {sym} has "
                                      f"{len(cached_data[sym])} bars "
                                      f"(< {_min_bars}) — skip")
                            continue
                        _to_retrain.append((sym, _lc_ts))
                        continue

                    # ── Slow path: new bar → fetch OHLCV (serial, rate-limited) ──
                    # [REV-FIX v2] catches up after missed bars (was: always last 3)
                    new_candles = _live_fetch_candles(
                        exchange, sym, cfg.timeframe, cached_data[sym], _tf_sec_local)
                    _ohlcv_fetched += 1
                    df_new = pd.DataFrame(new_candles, columns=['ts','Open','High','Low','Close','Volume'])
                    df_new['ts'] = pd.to_datetime(df_new['ts'], unit='ms', utc=True)
                    df_new = df_new.set_index('ts').astype(float)
                    df_combined = pd.concat([cached_data[sym], df_new])
                    _keep = int(getattr(CFG, 'LIVE_TAIL_BARS', 8000))
                    cached_data[sym] = (df_combined[
                        ~df_combined.index.duplicated(keep='last')
                    ].sort_index().tail(_keep))
                    cached_data[sym] = _live_heal_gaps(
                        exchange, sym, cfg.timeframe, cached_data[sym], _tf_sec_local)

                    _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
                    _lc_ts = _last_closed_bar_ts(cached_data[sym], _tf_sec)
                    _current_last_closed[sym] = _lc_ts

                    ad = _live_cache_get(sym, cfg.timeframe, _lc_ts)
                    if ad is not None:
                        assets[sym] = ad
                        continue
                    if _degenerate_get(sym, cfg.timeframe, _lc_ts):
                        continue
                    if _degenerate_banned(sym):
                        log.debug(f"[Degenerate-Ban] {sym} skipped "
                                  f"(streak={_DEGENERATE_STREAK.get(sym, 0)})")
                        continue
                    _min_bars = int(getattr(CFG, 'LIVE_MIN_BARS_FOR_PROCESS', 2000))
                    if len(cached_data[sym]) < _min_bars:
                        log.debug(f"[Warmup] {sym} has "
                                  f"{len(cached_data[sym])} bars "
                                  f"(< {_min_bars}) — skip")
                        continue
                    _to_retrain.append((sym, _lc_ts))
                except Exception as e:
                    log.warning(f"فشل التحديث اللحظي لـ {sym}: {e}")

            # ══ [PHASE 2] Parallel retrain (GIL-releasing KMeans) ══
            if _to_retrain:
                _use_par = bool(getattr(CFG, 'LIVE_PARALLEL_RETRAIN', True))
                _max_w = int(getattr(CFG, 'LIVE_PARALLEL_WORKERS', 4))
                _n_w = min(_max_w, len(_to_retrain)) if _use_par else 1

                if _n_w > 1:
                    _t_rt = time.time()
                    _cache_snap = {s: cached_data[s] for s, _ in _to_retrain}

                    def _do_retrain(_sym, _lc_ts):
                        try:
                            _ad = process_asset(
                                _sym, _cache_snap[_sym],
                                current_capital=cap_live,
                            )
                            return (_sym, _lc_ts, _ad, None)
                        except Exception as _e:
                            return (_sym, _lc_ts, None, str(_e))

                    log.info(f"[ParallelRetrain] {len(_to_retrain)} "
                             f"symbols, {_n_w} workers")
                    with ThreadPoolExecutor(max_workers=_n_w) as _ex:
                        _futs = [_ex.submit(_do_retrain, s, lc)
                                 for s, lc in _to_retrain]
                        for _f in as_completed(_futs):
                            _live_keepalive(exchange, open_pos_live, assets,
                                            cap_live, corr_cache)
                            try:
                                _sym, _lc_ts, _ad, _err = _f.result()
                            except Exception as _e:
                                log.warning(
                                    f"[ParallelRetrain] future failed: {_e}")
                                continue
                            if _err:
                                log.warning(
                                    f"[ParallelRetrain] {_sym}: {_err}")
                                continue
                            if _ad is not None:
                                _live_cache_put(_sym, cfg.timeframe,
                                                _lc_ts, _ad)
                                _DEGENERATE_STREAK.pop(_sym, None)
                                assets[_sym] = _ad
                            else:
                                _degenerate_put(_sym, cfg.timeframe, _lc_ts)
                    _el = time.time() - _t_rt
                    log.info(f"[ParallelRetrain] done in {_el:.1f}s "
                             f"({_el/max(len(_to_retrain),1):.2f}s/sym)")
                else:
                    for _sym, _lc_ts in _to_retrain:
                        _live_keepalive(exchange, open_pos_live, assets,
                                        cap_live, corr_cache)
                        try:
                            _ad = process_asset(
                                _sym, cached_data[_sym],
                                current_capital=cap_live)
                            if _ad is not None:
                                _live_cache_put(_sym, cfg.timeframe,
                                                _lc_ts, _ad)
                                _DEGENERATE_STREAK.pop(_sym, None)
                                assets[_sym] = _ad
                            else:
                                _degenerate_put(_sym, cfg.timeframe, _lc_ts)
                        except Exception as _e:
                            log.warning(f"فشل retrain {_sym}: {_e}")''',
            r'''            _to_retrain = []
            _need_fetch_syms = []
            for sym in top_syms:
                if sym not in cached_data: continue
                if _smart and not _needs_ohlcv_refresh(cached_data[sym], _tf_sec_local):
                    _ohlcv_skipped += 1
                    _lc_ts = _last_closed_bar_ts(cached_data[sym], _tf_sec_local)
                    _current_last_closed[sym] = _lc_ts
                    ad = _live_cache_get(sym, cfg.timeframe, _lc_ts)
                    if ad is not None:
                        assets[sym] = ad
                        continue
                    if _degenerate_get(sym, cfg.timeframe, _lc_ts):
                        continue
                    if _degenerate_banned(sym):
                        continue
                    _min_bars = int(getattr(CFG, 'LIVE_MIN_BARS_FOR_PROCESS', 2000))
                    if len(cached_data[sym]) < _min_bars:
                        log.debug(f"[Warmup] {sym} has "
                                  f"{len(cached_data[sym])} bars "
                                  f"(< {_min_bars}) — skip")
                        continue
                    _to_retrain.append((sym, _lc_ts))
                else:
                    _need_fetch_syms.append(sym)

            # ══ [PHASE 1] Parallel OHLCV fetch on candle-close cycles ══
            if _need_fetch_syms:
                _t_oh = time.time()
                _fetched_map = {}
                _par_ohlcv = bool(getattr(CFG, 'LIVE_PARALLEL_OHLCV', True))
                _oh_workers = min(
                    max(1, int(getattr(CFG, 'LIVE_OHLCV_WORKERS', 8))),
                    len(_need_fetch_syms),
                ) if _par_ohlcv else 1

                def _fetch_sym_ohlcv(_s):
                    try:
                        _nc = _live_fetch_candles(
                            exchange, _s, cfg.timeframe, cached_data[_s], _tf_sec_local
                        )
                        return (_s, _nc, None)
                    except Exception as _fe:
                        return (_s, None, _fe)

                if _oh_workers > 1:
                    with ThreadPoolExecutor(max_workers=_oh_workers) as _ox:
                        for _res in _ox.map(_fetch_sym_ohlcv, _need_fetch_syms):
                            _fetched_map[_res[0]] = (_res[1], _res[2])
                else:
                    for _s in _need_fetch_syms:
                        _r = _fetch_sym_ohlcv(_s)
                        _fetched_map[_r[0]] = (_r[1], _r[2])

                _defer_heal = (len(_need_fetch_syms) > 10)
                _keep = int(getattr(CFG, 'LIVE_TAIL_BARS', 8000))
                _min_bars = int(getattr(CFG, 'LIVE_MIN_BARS_FOR_PROCESS', 2000))
                for sym in _need_fetch_syms:
                    new_candles, _ferr = _fetched_map.get(sym, (None, None))
                    if _ferr is not None or not new_candles:
                        if _ferr is not None:
                            log.warning(f"فشل التحديث اللحظي لـ {sym}: {_ferr}")
                        continue
                    try:
                        _ohlcv_fetched += 1
                        df_new = pd.DataFrame(new_candles, columns=['ts','Open','High','Low','Close','Volume'])
                        df_new['ts'] = pd.to_datetime(df_new['ts'], unit='ms', utc=True)
                        df_new = df_new.set_index('ts').astype(float)
                        df_combined = pd.concat([cached_data[sym], df_new])
                        cached_data[sym] = (df_combined[
                            ~df_combined.index.duplicated(keep='last')
                        ].sort_index().tail(_keep))
                        if not _defer_heal:
                            cached_data[sym] = _live_heal_gaps(
                                exchange, sym, cfg.timeframe, cached_data[sym], _tf_sec_local)

                        _lc_ts = _last_closed_bar_ts(cached_data[sym], _tf_sec_local)
                        _current_last_closed[sym] = _lc_ts

                        ad = _live_cache_get(sym, cfg.timeframe, _lc_ts)
                        if ad is not None:
                            assets[sym] = ad
                            continue
                        if _degenerate_get(sym, cfg.timeframe, _lc_ts):
                            continue
                        if _degenerate_banned(sym):
                            log.debug(f"[Degenerate-Ban] {sym} skipped "
                                      f"(streak={_DEGENERATE_STREAK.get(sym, 0)})")
                            continue
                        if len(cached_data[sym]) < _min_bars:
                            log.debug(f"[Warmup] {sym} has "
                                      f"{len(cached_data[sym])} bars "
                                      f"(< {_min_bars}) — skip")
                            continue
                        _to_retrain.append((sym, _lc_ts))
                    except Exception as e:
                        log.warning(f"فشل التحديث اللحظي لـ {sym}: {e}")
                if len(_need_fetch_syms) > 5:
                    log.info(f"[ParallelOHLCV] {_ohlcv_fetched}/{len(_need_fetch_syms)} "
                             f"fetched in {time.time()-_t_oh:.2f}s (workers={_oh_workers})")

            # ══ [PHASE 2] Parallel retrain with KMeans model reuse ══
            if _to_retrain:
                _use_par = bool(getattr(CFG, 'LIVE_PARALLEL_RETRAIN', True))
                _cpu_n = os.cpu_count() or 4
                _max_w = max(
                    int(getattr(CFG, 'LIVE_PARALLEL_WORKERS', 4)),
                    min(12, _cpu_n),
                )
                _n_w = min(_max_w, len(_to_retrain)) if _use_par else 1
                _km_ttl = float(getattr(CFG, 'LIVE_KM_CACHE_HOURS', 12.0)) * 3600.0
                _now_km = time.time()
                _km_snap = {}
                for _s, _ in _to_retrain:
                    _ke = _LIVE_KM_CACHE.get(_s)
                    if _ke is not None and (_now_km - float(_ke.get('ts', 0.0))) < _km_ttl:
                        _km_snap[_s] = _ke.get('km')

                def _run_retrain_one(_sym, _df_s, _km_cached):
                    _used_cached = False
                    if _km_cached is not None:
                        _ad = process_asset(
                            _sym, _df_s,
                            km_ext=_km_cached,
                            current_capital=cap_live,
                        )
                        if _ad is not None:
                            _used_cached = True
                            return _ad, _used_cached
                    _ad = process_asset(
                        _sym, _df_s,
                        current_capital=cap_live,
                    )
                    return _ad, False

                if _n_w > 1:
                    _t_rt = time.time()
                    _cache_snap = {s: cached_data[s] for s, _ in _to_retrain}

                    def _do_retrain(_sym, _lc_ts):
                        try:
                            _ad, _used_c = _run_retrain_one(
                                _sym, _cache_snap[_sym], _km_snap.get(_sym)
                            )
                            return (_sym, _lc_ts, _ad, _used_c, None)
                        except Exception as _e:
                            return (_sym, _lc_ts, None, False, str(_e))

                    log.info(f"[ParallelRetrain] {len(_to_retrain)} "
                             f"symbols, {_n_w} workers (km_cached={len(_km_snap)})")
                    with ThreadPoolExecutor(max_workers=_n_w) as _ex:
                        _futs = [_ex.submit(_do_retrain, s, lc)
                                 for s, lc in _to_retrain]
                        for _f in as_completed(_futs):
                            _live_keepalive(exchange, open_pos_live, assets,
                                            cap_live, corr_cache)
                            try:
                                _sym, _lc_ts, _ad, _used_c, _err = _f.result()
                            except Exception as _e:
                                log.warning(
                                    f"[ParallelRetrain] future failed: {_e}")
                                continue
                            if _err:
                                log.warning(
                                    f"[ParallelRetrain] {_sym}: {_err}")
                                continue
                            if _ad is not None:
                                _live_cache_put(_sym, cfg.timeframe,
                                                _lc_ts, _ad)
                                if not _used_c and getattr(_ad, 'km', None) is not None:
                                    _LIVE_KM_CACHE[_sym] = {
                                        'km': _ad.km,
                                        'k': int(_ad.dynamic_k),
                                        'ts': time.time(),
                                    }
                                _DEGENERATE_STREAK.pop(_sym, None)
                                assets[_sym] = _ad
                            else:
                                _degenerate_put(_sym, cfg.timeframe, _lc_ts)
                    _el = time.time() - _t_rt
                    log.info(f"[ParallelRetrain] done in {_el:.1f}s "
                             f"({_el/max(len(_to_retrain),1):.2f}s/sym)")
                else:
                    for _sym, _lc_ts in _to_retrain:
                        _live_keepalive(exchange, open_pos_live, assets,
                                        cap_live, corr_cache)
                        try:
                            _ad, _used_c = _run_retrain_one(
                                _sym, cached_data[_sym], _km_snap.get(_sym)
                            )
                            if _ad is not None:
                                _live_cache_put(_sym, cfg.timeframe,
                                                _lc_ts, _ad)
                                if not _used_c and getattr(_ad, 'km', None) is not None:
                                    _LIVE_KM_CACHE[_sym] = {
                                        'km': _ad.km,
                                        'k': int(_ad.dynamic_k),
                                        'ts': time.time(),
                                    }
                                _DEGENERATE_STREAK.pop(_sym, None)
                                assets[_sym] = _ad
                            else:
                                _degenerate_put(_sym, cfg.timeframe, _lc_ts)
                        except Exception as _e:
                            log.warning(f"فشل retrain {_sym}: {_e}")''',
        ),

        # ── 8. Cache exchange positions once before signal entry loop ───
        (
            "run_live batch fetch_positions before signal loop",
            r'''                for sig in reversed(sigs):
                    sym = sig.symbol''',
            r'''                _cycle_exch_positions = None
                if sigs:
                    _cycle_exch_positions = _lv_fetch_positions(exchange, None)

                for sig in reversed(sigs):
                    sym = sig.symbol''',
        ),
        (
            "run_live reuse _cycle_exch_positions in STEP 1",
            r'''                        _has_exch_pos = False
                        try:
                            _rate_record(5.0)
                            for _p in exchange.fetch_positions([sym]):
                                _amt = float(
                                    _p['info'].get('positionAmt', 0) or 0
                                )
                                if abs(_amt) > 0:
                                    _has_exch_pos = True
                                    break
                        except Exception as _e:
                            log.debug(f"[Entry-Cleanup] {sym} position "
                                      f"check failed: {_e}")
                            _has_exch_pos = True''',
            r'''                        _has_exch_pos = False
                        if _cycle_exch_positions is not None:
                            _has_exch_pos = (sym in _cycle_exch_positions)
                        else:
                            try:
                                _rate_record(5.0)
                                for _p in exchange.fetch_positions([sym]):
                                    _amt = float(
                                        _p['info'].get('positionAmt', 0) or 0
                                    )
                                    if abs(_amt) > 0:
                                        _has_exch_pos = True
                                        break
                            except Exception as _e:
                                log.debug(f"[Entry-Cleanup] {sym} position "
                                          f"check failed: {_e}")
                                _has_exch_pos = True''',
        ),

        # ── 9. Align sleep to wake right at next candle close + 0.4s ────
        (
            "run_live wake-on-candle-close alignment",
            r'''            _loop_ok(loop_iter, open_pos_live)   # [REV-FIX v2] resets error streak + heartbeat
            sleep_time = max(0, cfg.LIVE_POLL_SECS - (time.time() - t0))
            time.sleep(sleep_time)''',
            r'''            _loop_ok(loop_iter, open_pos_live)   # [REV-FIX v2] resets error streak + heartbeat
            sleep_time = max(0.0, cfg.LIVE_POLL_SECS - (time.time() - t0))
            if getattr(CFG, 'LIVE_WAKE_ON_CLOSE', True) and _tf_sec_local >= 60:
                _now_w = time.time()
                _next_close_w = ((int(_now_w) // _tf_sec_local) + 1) * _tf_sec_local + 0.4
                _to_close_w = _next_close_w - _now_w
                if 0.0 < _to_close_w < sleep_time:
                    sleep_time = _to_close_w
            time.sleep(sleep_time)''',
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
    parser = argparse.ArgumentParser(description="Patch live mode for low-latency candle close and backtest entry parity")
    parser.add_argument("--target", default=_default_target(), help="Path to target script")
    parser.add_argument("--dry-run", action="store_true", help="Verify matches without modifying file")
    args = parser.parse_args()
    apply_patch(args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
