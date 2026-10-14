#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_reversal_fixes.py  [REV-FIX v1]
Applies the reversal-confirm live/backtest parity fixes to trading_2_live4.py.

Usage:
    python apply_reversal_fixes.py trading_2_live4.py              # -> trading_2_live4_revfix.py
    python apply_reversal_fixes.py trading_2_live4.py --inplace    # backup + overwrite
    python apply_reversal_fixes.py trading_2_live4.py --dry-run    # verify anchors only

Safety: every anchor must match EXACTLY ONCE or nothing is written.
The result is ast-parsed + byte-compiled before it is saved.
"""
import argparse, ast, os, py_compile, shutil, sys, time

MARK = "[REV-FIX v1]"

NEW_LIVE_BLOCK = '# ═══════════════════════════════════════════════════════════════\n# [LIVE REVERSAL] [REV-FIX v1] Touch-and-Bounce on sub-bars (non-blocking)\n#   WAITING_TOUCH -> WAITING_BOUNCE -> READY_TO_FILL -> FILLING\n#                                                    -> FILLED | EXPIRED\n#   * no blocking loops (one REST step per watcher per cycle)\n#   * parity with _check_reversal_fill_subbars (touch window, bounce\n#     window, scan origin = first sub-bar of the bar AFTER the signal)\n#   * once-per-signal ledger, fill-time slot gate, stale-confirm guard\n#   * clientOrderId idempotency + crash-safe resume of FILLING watchers\n# ═══════════════════════════════════════════════════════════════\nimport time as _t_rev\nimport hashlib as _hl_rev\nfrom decimal import Decimal as _Dec_rev, ROUND_FLOOR as _RF_rev, ROUND_CEILING as _RC_rev\n\n\n_REVERSAL_WATCHERS: Dict[str, Dict] = {}\n_REVERSAL_WATCHERS_PATH: str = ""\n_REV_LEDGER: Dict[str, float] = {}\n_REV_LEDGER_PATH: str = ""\n_REV_STATE_FILE: str = ""\n_REV_BACKOFF_UNTIL: float = 0.0\n_REV_BACKOFF_STEP: float = 0.0\n_REV_MAX_PER_CYCLE: int = 3\n_REV_TERMINAL = ("closed", "canceled", "cancelled", "expired", "rejected")\n\n\ndef _revc(name: str, default):\n    return getattr(CFG, name, default)\n\n\ndef _sub_tf_seconds(sub_tf: str) -> int:\n    try:\n        import ccxt as _cc\n        return int(_cc.binance().parse_timeframe(sub_tf))\n    except Exception:\n        return {"1m": 60, "5m": 300, "15m": 900,\n                "30m": 1800, "1h": 3600, "4h": 14400}.get(sub_tf, 900)\n\n\ndef _rev_sub_info():\n    sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"\n    return sub_tf, int(_sub_tf_seconds(sub_tf))\n\n\ndef _rev_main_sec() -> int:\n    _s = int(getattr(CFG, "TF_SECONDS", 0) or 0)\n    return _s if _s > 0 else int(_sub_tf_seconds(CFG.timeframe))\n\n\n# ───────────────────────── persistence ─────────────────────────\ndef _rev_atomic_dump(path: str, obj) -> None:\n    tmp = path + ".tmp"\n    with open(tmp, "w") as f:\n        json.dump(obj, f, default=str, indent=1)\n    os.replace(tmp, path)\n\n\ndef load_reversal_watchers(mode: str) -> Dict[str, Dict]:\n    global _REVERSAL_WATCHERS, _REVERSAL_WATCHERS_PATH\n    global _REV_LEDGER, _REV_LEDGER_PATH, _REV_STATE_FILE\n    _REVERSAL_WATCHERS_PATH = f"reversal_watchers_{mode}.json"\n    _REV_LEDGER_PATH = f"reversal_ledger_{mode}.json"\n    _REV_STATE_FILE = f"live_state_{mode}.json"\n    _REVERSAL_WATCHERS = {}\n    _REV_LEDGER = {}\n    if os.path.exists(_REVERSAL_WATCHERS_PATH):\n        try:\n            with open(_REVERSAL_WATCHERS_PATH) as f:\n                raw = json.load(f)\n            for _sym, _w in raw.items():\n                _w.pop("signal_ref", None)\n            _REVERSAL_WATCHERS = raw\n            log.info(f"[LiveRev] Restored {len(_REVERSAL_WATCHERS)} watchers")\n        except Exception as e:\n            log.warning(f"[LiveRev] load failed: {e}")\n            _REVERSAL_WATCHERS = {}\n    if os.path.exists(_REV_LEDGER_PATH):\n        try:\n            with open(_REV_LEDGER_PATH) as f:\n                _REV_LEDGER = {str(k): float(v)\n                               for k, v in json.load(f).items()}\n        except Exception as e:\n            log.warning(f"[LiveRev] ledger load failed: {e}")\n            _REV_LEDGER = {}\n    _rev_ledger_purge()\n    return _REVERSAL_WATCHERS\n\n\ndef save_reversal_watchers() -> None:\n    if not _REVERSAL_WATCHERS_PATH:\n        return\n    try:\n        ser = {}\n        for sym, w in _REVERSAL_WATCHERS.items():\n            ser[sym] = {k: v for k, v in w.items() if k != "signal_ref"}\n        _rev_atomic_dump(_REVERSAL_WATCHERS_PATH, ser)\n    except Exception as e:\n        log.warning(f"[LiveRev] save failed: {e}")\n\n\ndef _rev_ledger_purge() -> None:\n    ttl = float(_revc("REV_LEDGER_TTL_S", 172800.0))\n    now = _t_rev.time()\n    for k in [k for k, v in _REV_LEDGER.items() if now - v > ttl]:\n        _REV_LEDGER.pop(k, None)\n\n\ndef _rev_ledger_save() -> None:\n    if not _REV_LEDGER_PATH:\n        return\n    try:\n        _rev_atomic_dump(_REV_LEDGER_PATH, _REV_LEDGER)\n    except Exception as e:\n        log.warning(f"[LiveRev] ledger save failed: {e}")\n\n\n# ───────────────────── exchange helpers (rate-aware) ─────────────────────\ndef _rev_api(fn, *args, weight: float = 1.0, **kwargs):\n    """REST wrapper: records weight, arms exponential back-off on 429/418."""\n    global _REV_BACKOFF_UNTIL, _REV_BACKOFF_STEP\n    try:\n        _rate_record(float(weight))\n    except Exception:\n        pass\n    try:\n        out = fn(*args, **kwargs)\n        _REV_BACKOFF_STEP = 0.0\n        return out\n    except Exception as e:\n        s = str(e)\n        n = type(e).__name__\n        if ("429" in s or "418" in s or "RateLimit" in n\n                or "DDoS" in n or "Too many requests" in s):\n            step = min(120.0, max(2.0, _REV_BACKOFF_STEP * 2.0))\n            if "418" in s:\n                step = max(step, 60.0)\n            _REV_BACKOFF_STEP = step\n            _REV_BACKOFF_UNTIL = _t_rev.time() + step\n            log.warning(f"[LiveRev] rate-limit ({n}) — back-off {step:.0f}s")\n        raise\n\n\ndef _rev_is_not_found(e: Exception) -> bool:\n    s = str(e)\n    return (type(e).__name__ == "OrderNotFound" or "-2013" in s\n            or "Unknown order" in s or "Order does not exist" in s)\n\n\ndef _rev_tick(exchange, sym: str):\n    try:\n        import ccxt as _cc\n        p = (exchange.market(sym).get("precision") or {}).get("price")\n        if p is None:\n            return None\n        p = float(p)\n        mode = getattr(exchange, "precisionMode", None)\n        if mode == getattr(_cc, "TICK_SIZE", 4):\n            return p if p > 0 else None\n        if mode == getattr(_cc, "DECIMAL_PLACES", 2):\n            return 10.0 ** (-int(p))\n    except Exception:\n        pass\n    return None\n\n\ndef _rev_snap_price(exchange, sym: str, px: float, side: str) -> float:\n    """Directional tick snap: BUY floors, SELL ceils (never crosses book)."""\n    tick = _rev_tick(exchange, sym)\n    if tick and tick > 0:\n        d = _Dec_rev(str(px))\n        t = _Dec_rev(str(tick))\n        mode = _RF_rev if side == "buy" else _RC_rev\n        return float((d / t).to_integral_value(rounding=mode) * t)\n    try:\n        return float(exchange.price_to_precision(sym, px))\n    except Exception:\n        return float(px)\n\n\ndef _snap_qty(exchange, sym: str, qty: float) -> float:\n    """[REV-FIX] was referenced but never defined (NameError)."""\n    q = float(qty)\n    try:\n        q = float(exchange.amount_to_precision(sym, q))\n    except Exception:\n        pass\n    try:\n        mn = _lv_min_amount(exchange, sym)\n        if mn and q < mn:\n            return 0.0\n    except Exception:\n        pass\n    return q\n\n\ndef _rev_cid(sym: str, sig_epoch: float, attempt: int) -> str:\n    h = _hl_rev.md5(sym.encode()).hexdigest()[:8]\n    return f"rev{int(sig_epoch)}x{h}x{int(attempt)}"[:36]\n\n\ndef _rev_exch_position(exchange, sym: str):\n    """-> dict {\'qty\',\'entry\',\'side\'} | {} (flat) | None (API failure)."""\n    res = _lv_fetch_positions(exchange, [sym])\n    if res is None:\n        return None\n    return res.get(sym.split(":")[0]) or {}\n\n\ndef _rev_find_order(exchange, sym: str, cid: str, order_id=None):\n    """Order dict | None (does not exist). Raises on transient API errors."""\n    if order_id:\n        try:\n            return _rev_api(exchange.fetch_order, order_id, sym)\n        except Exception as e:\n            if not _rev_is_not_found(e):\n                raise\n    try:\n        for o in _rev_api(exchange.fetch_open_orders, sym) or []:\n            oc = str(o.get("clientOrderId")\n                     or (o.get("info") or {}).get("clientOrderId") or "")\n            if oc == cid:\n                return o\n    except Exception as e:\n        if not _rev_is_not_found(e):\n            raise\n    try:\n        return _rev_api(exchange.fetch_order, None, sym,\n                        params={"origClientOrderId": cid})\n    except Exception as e:\n        if _rev_is_not_found(e):\n            return None\n        raise\n\n\ndef _rev_cur_from_order(w: Dict, o: Dict) -> None:\n    f = float(o.get("filled") or 0.0)\n    a = o.get("average")\n    try:\n        a = float(a) if a else 0.0\n    except Exception:\n        a = 0.0\n    if a <= 0:\n        a = float(o.get("price") or w.get("order_px") or w.get("target") or 0.0)\n    w["cur_filled"] = f\n    w["cur_avg"] = a\n\n\ndef _rev_bank(w: Dict) -> None:\n    f = float(w.get("cur_filled") or 0.0)\n    a = float(w.get("cur_avg") or 0.0)\n    if f > 0 and a > 0:\n        w["banked_qty"] = float(w.get("banked_qty", 0.0)) + f\n        w["banked_cost"] = float(w.get("banked_cost", 0.0)) + f * a\n    w["cur_filled"] = 0.0\n    w["cur_avg"] = 0.0\n\n\ndef _rev_clear_order(w: Dict) -> None:\n    w["cid"] = None\n    w["order_id"] = None\n    w["cid_sent"] = False\n    w["order_px"] = 0.0\n    w["cancel_req"] = False\n\n\ndef _rev_cancel_and_confirm(exchange, sym: str, w: Dict) -> bool:\n    """Cancel the live entry order; True only once it is TERMINAL."""\n    try:\n        if w.get("order_id"):\n            _rev_api(exchange.cancel_order, w["order_id"], sym)\n        else:\n            _rev_api(exchange.cancel_order, None, sym,\n                     params={"origClientOrderId": w["cid"]})\n    except Exception as e:\n        if not _rev_is_not_found(e):\n            log.debug(f"[LiveRev] {sym} cancel error: {e}")\n    try:\n        o = _rev_find_order(exchange, sym, w["cid"], w.get("order_id"))\n    except Exception as e:\n        log.debug(f"[LiveRev] {sym} cancel verify error: {e}")\n        return False\n    if o is None:\n        _rev_bank(w)\n        _rev_clear_order(w)\n        return True\n    _rev_cur_from_order(w, o)\n    if str(o.get("status") or "open") in _REV_TERMINAL:\n        _rev_bank(w)\n        _rev_clear_order(w)\n        return True\n    return False\n\n\ndef _rev_best_px(exchange, sym: str, action: str):\n    ob = _rev_api(exchange.fetch_order_book, sym, 5, weight=2.0)\n    bids = ob.get("bids") or []\n    asks = ob.get("asks") or []\n    if action == "BUY":\n        if not bids:\n            return None\n        return _rev_snap_price(exchange, sym, float(bids[0][0]), "buy")\n    if not asks:\n        return None\n    return _rev_snap_price(exchange, sym, float(asks[0][0]), "sell")\n\n\ndef _rev_beyond_chase(action: str, px: float, ref_px: float,\n                      chase: float) -> bool:\n    return (px > ref_px + chase) if action == "BUY" else (px < ref_px - chase)\n\n\ndef _rev_expire(w: Dict, reason: str) -> None:\n    if w.get("status") not in ("EXPIRED", "FILLED"):\n        w["status"] = "EXPIRED"\n        w["reason"] = str(reason)\n        log.info(f"[LiveRev] {w.get(\'sym\')} EXPIRED ({reason})")\n\n\n# ───────────────────────── bounce rule ─────────────────────────\ndef _bar_confirms_bounce(w: Dict, close: float) -> bool:\n    action = w["action"]\n    target = float(w["target"])\n    mode = str(CFG.REVERSAL_CONFIRM_MODE)\n\n    if mode == "close_back":\n        return (action == "BUY" and close > target) or \\\n               (action == "SELL" and close < target)\n\n    if mode == "sigma_bounce":\n        kappa = float(CFG.REVERSAL_CONFIRM_KAPPA)\n        sigma = float(w.get("sigma_bar", 0.01))\n        thr = kappa * sigma * target\n        if action == "BUY":\n            return (close - target) > thr\n        return (target - close) > thr\n\n    if mode == "bar_color":\n        # prev_close is maintained by the scanner for EVERY sub-bar\n        prev = w.get("prev_close")\n        if prev is None:\n            return False\n        return (action == "BUY" and close > float(prev)) or \\\n               (action == "SELL" and close < float(prev))\n\n    if mode == "two_bar":\n        ok = (close > target) if action == "BUY" else (close < target)\n        w["two_bar_count"] = (int(w.get("two_bar_count", 0)) + 1) if ok else 0\n        return w["two_bar_count"] >= 2\n\n    return False\n\n\n# ───────────────────────── registration ─────────────────────────\ndef _register_reversal_watcher(exchange, sym: str, side: str,\n                                qty: float, sig, leverage: int,\n                                ad=None, cap_ref=None) -> bool:\n    if sym in _REVERSAL_WATCHERS:\n        return False\n    if sym in _PENDING_ORDERS:\n        return False\n    if len(_REVERSAL_WATCHERS) >= int(_revc("REV_WATCHER_CAP", 50)):\n        return False\n\n    ts = pd.Timestamp(sig.timestamp)\n    if ts.tz is None:\n        ts = ts.tz_localize("UTC")\n    sig_epoch = float(ts.timestamp())            # bar OPEN time\n    key = f"{sym}|{int(sig_epoch)}|{sig.action}"\n    if key in _REV_LEDGER:\n        return False                             # once per signal\n\n    sub_tf, sub_sec = _rev_sub_info()\n    main_sec = _rev_main_sec()\n    tw = int(getattr(CFG, "REVERSAL_TOUCH_SUBBARS", 20))\n    bw = int(getattr(CFG, "REVERSAL_BOUNCE_SUBBARS", 4))\n    lat = int(_revc("REV_ENTRY_LATENCY_SUBBARS", 0))\n    start_ts = sig_epoch + main_sec              # first sub-bar of bar N+1\n    expire_ts = start_ts + (tw + bw + lat + 2) * sub_sec\n\n    _REV_LEDGER[key] = _t_rev.time()\n    _rev_ledger_save()\n    if _t_rev.time() >= expire_ts:\n        log.debug(f"[LiveRev] {sym} signal already outside window — skip")\n        return False\n\n    sigma_bar = 0.01\n    friction_v, accel_v, gauge_v = 0.2, 0.05, 0.1\n    if ad is not None:\n        try:\n            fi = int(sig.feat_idx)\n            if 0 <= fi < len(ad.E_therm):\n                _s = float(ad.E_therm[fi])\n                if np.isfinite(_s) and _s > 1e-9:\n                    sigma_bar = _s\n            if 0 <= fi < len(ad.friction):\n                friction_v = float(ad.friction[fi])\n            if 0 <= fi < len(ad.geodesic_accel):\n                accel_v = float(ad.geodesic_accel[fi])\n            if 0 <= fi < len(ad.gauge_force):\n                gauge_v = float(ad.gauge_force[fi])\n        except Exception:\n            pass\n\n    try:\n        _mmr = float(_get_mmr_for_symbol(exchange, sym))\n    except Exception:\n        _mmr = float(getattr(CFG, "LIQ_FALLBACK_MMR", 0.02))\n\n    try:\n        _bt_target = float(_backtest_entry_target(sig, ad))\n    except Exception:\n        _bt_target = float(sig.price)\n\n    w = {\n        "sym": sym,\n        "side": side,\n        "side_ccxt": "buy" if sig.action == "BUY" else "sell",\n        "action": sig.action,\n        "target": _bt_target,\n        "qty": float(qty),\n        "cap_ref": (float(cap_ref) if cap_ref else None),\n        "leverage": int(leverage),\n        "mmr": _mmr,\n        "dyn_risk": float(sig.dynamic_risk),\n        "T_info": float(sig.T_info_val),\n        "score": float(getattr(sig, "score", 0.0) or 0.0),\n        "sigma_bar": float(sigma_bar),\n        "friction": float(friction_v),\n        "accel": float(accel_v),\n        "gauge_force": float(gauge_v),\n        "close_idx": int(sig.close_idx),\n        "sig_epoch": sig_epoch,\n        "start_ts": start_ts,\n        "expire_ts": expire_ts,\n        "created_at": _t_rev.time(),\n        "status": "WAITING_TOUCH",\n        "touch_k": -1,\n        "last_scan_ts": start_ts - 1.0,\n        "next_fetch_ts": start_ts + sub_sec + 2.0,\n        "sig_ts": str(sig.timestamp),\n        "sig_price": float(sig.price),\n        "sig_sl": float(sig.sl),\n        "sig_tp1": float(sig.tp1),\n        "orig_sl_dist": float(abs(sig.price - sig.sl)),\n        "orig_tp_dist": float(abs(sig.tp1 - sig.price)),\n        "two_bar_count": 0,\n        "prev_close": None,\n        "banked_qty": 0.0, "banked_cost": 0.0,\n        "cur_filled": 0.0, "cur_avg": 0.0,\n        "attempt": 0, "rejects": 0, "err": 0,\n        "cid": None, "order_id": None, "cid_sent": False,\n        "order_px": 0.0, "cancel_req": False,\n    }\n    _REVERSAL_WATCHERS[sym] = w\n    log.info(f"[LiveRev] {sig.action} {sym} registered — "\n             f"target={_bt_target:.6f} (sig.price={sig.price:.6f}) "\n             f"window=[{start_ts:.0f}, +{tw}+{bw} sub-bars] "\n             f"sl={sig.sl:.6f} tp={sig.tp1:.6f}")\n    return True\n\n\n# ───────────────────────── scanning ─────────────────────────\ndef _rev_scan(exchange, sym: str, w: Dict, sub_tf: str, sub_sec: int,\n              now: float) -> None:\n    tw = int(getattr(CFG, "REVERSAL_TOUCH_SUBBARS", 20))\n    bw = int(getattr(CFG, "REVERSAL_BOUNCE_SUBBARS", 4))\n    start_ts = float(w["start_ts"])\n    last = float(w["last_scan_ts"])\n    need = int((now - last) / sub_sec) + 3\n    limit = int(min(max(need, 5), 300))\n    raw = _rev_api(exchange.fetch_ohlcv, sym, sub_tf,\n                   int((last + 1.0) * 1000), limit,\n                   weight=(1.0 if limit < 100 else 2.0))\n    bars = {}\n    for r in raw or []:\n        ts = float(r[0]) / 1000.0\n        if ts <= last or ts + sub_sec > now - 1.0:\n            continue                       # already seen / still forming\n        bars[ts] = (float(r[2]), float(r[3]), float(r[4]))   # H, L, C\n    action = w["action"]\n    target = float(w["target"])\n    for ts in sorted(bars):\n        h, l, c = bars[ts]\n        k = int(round((ts - start_ts) / sub_sec))\n        if k < 0:\n            w["last_scan_ts"] = ts\n            continue\n        st = w["status"]\n        if st == "WAITING_TOUCH":\n            if k >= tw:\n                _rev_expire(w, "touch_window")\n                w["last_scan_ts"] = ts\n                break\n            if np.isfinite(h) and np.isfinite(l):\n                if ((action == "BUY" and l <= target)\n                        or (action == "SELL" and h >= target)):\n                    w["status"] = "WAITING_BOUNCE"\n                    w["touch_k"] = k\n                    log.info(f"[LiveRev] {sym} TOUCH k={k} "\n                             f"@ {pd.Timestamp(ts, unit=\'s\', tz=\'UTC\')}")\n        elif st == "WAITING_BOUNCE":\n            if k > int(w["touch_k"]) + bw:\n                _rev_expire(w, "bounce_timeout")\n                w["last_scan_ts"] = ts\n                break\n            if np.isfinite(c) and _bar_confirms_bounce(w, c):\n                w["status"] = "READY_TO_FILL"\n                w["confirm_k"] = k\n                w["ref_px"] = float(c)\n                w["confirm_close_ts"] = ts + sub_sec\n                w["prev_close"] = c\n                w["last_scan_ts"] = ts\n                log.info(f"[LiveRev] {sym} BOUNCE confirmed k={k} "\n                         f"close={c:.6f}")\n                break\n        w["prev_close"] = c\n        w["last_scan_ts"] = ts\n    if w["status"] in ("WAITING_TOUCH", "WAITING_BOUNCE"):\n        nb_open = (int(float(w["last_scan_ts"]) // sub_sec) + 1) * sub_sec\n        w["next_fetch_ts"] = nb_open + sub_sec + 2.0\n\n\n# ───────────────────────── fill gate ─────────────────────────\ndef _rev_handle_ready(exchange, sym: str, w: Dict, open_pos_live: Dict,\n                      now: float, sub_sec: int, cap_now, corr_cache) -> None:\n    max_age = float(_revc("REV_MAX_CONFIRM_AGE_SUBBARS", 2)) * sub_sec\n    if now - float(w.get("confirm_close_ts", 0.0)) > max_age:\n        _rev_expire(w, "stale_confirm")\n        return\n    if sym in open_pos_live:\n        _rev_expire(w, "pos_open")\n        return\n    n_infl = sum(1 for s2, w2 in _REVERSAL_WATCHERS.items()\n                 if s2 != sym and w2.get("status") == "FILLING")\n    if len(open_pos_live) + n_infl >= int(CFG.MAX_CONCURRENT_ASSETS):\n        _rev_expire(w, "slots_full")\n        return\n    if corr_cache is not None and open_pos_live:\n        try:\n            thr = CFG.CORRELATION_THRESHOLD * (\n                (0.85 ** len(open_pos_live))\n                if getattr(CFG, "LIVE_ADAPTIVE_CORR", False) else 1.0)\n            if any(abs(corr_cache.get((sym, s), 0.0)) > thr\n                   for s in open_pos_live):\n                _rev_expire(w, "corr_guard")\n                return\n        except Exception:\n            pass\n    qty = float(w["qty"])\n    if (_revc("REV_RESIZE_AT_FILL", True) and cap_now\n            and w.get("cap_ref")):\n        ratio = float(np.clip(float(cap_now) / float(w["cap_ref"]),\n                              0.25, 1.25))\n        qty *= ratio\n    w["qty_eff"] = qty\n    w["status"] = "FILLING"\n    w["fill_started"] = now\n    w["fill_deadline"] = now + float(_revc("REV_FILL_MAX_WAIT_S", 90.0))\n    w["last_reprice"] = 0.0\n    log.info(f"[LiveRev] {sym} FILLING qty={qty:.6f} ref={w[\'ref_px\']:.6f}")\n\n\n# ───────────────────────── fill engine (non-blocking) ─────────────────────────\ndef _rev_advance_filling(exchange, sym: str, w: Dict, open_pos_live: Dict,\n                         assets, now: float) -> None:\n    action = w["action"]\n    side = w["side_ccxt"]\n    qty_target = float(w.get("qty_eff") or w["qty"])\n    ref_px = float(w.get("ref_px") or w["target"])\n    sigma = float(w.get("sigma_bar", 0.01))\n    chase = float(_revc("REV_MAX_CHASE_KAPPA", 0.15)) * sigma * ref_px\n\n    if not w.get("setup_done"):\n        try:\n            ensure_symbol_setup(exchange, sym, int(w["leverage"]),\n                                margin_mode="isolated")\n            w["setup_done"] = True\n        except Exception as e:\n            w["setup_fail"] = int(w.get("setup_fail", 0)) + 1\n            log.warning(f"[LiveRev] setup {sym}: {e}")\n            if w["setup_fail"] >= 3:\n                _rev_expire(w, "setup_failed")\n            return\n\n    # ── 1) an entry order may exist (possibly after a restart) ──\n    if w.get("cid"):\n        try:\n            o = _rev_find_order(exchange, sym, w["cid"], w.get("order_id"))\n        except Exception as e:\n            log.debug(f"[LiveRev] {sym} order lookup failed: {e}")\n            return                      # unsure -> never place a new one\n        if o is None:\n            _rev_clear_order(w)         # create never reached the exchange\n        else:\n            w["order_id"] = str(o.get("id") or w.get("order_id") or "")\n            _rev_cur_from_order(w, o)\n            if str(o.get("status") or "open") in _REV_TERMINAL:\n                _rev_bank(w)\n                _rev_clear_order(w)\n            else:\n                if now >= float(w["fill_deadline"]) or w.get("cancel_req"):\n                    if not _rev_cancel_and_confirm(exchange, sym, w):\n                        return\n                elif now - float(w.get("last_reprice", 0.0)) >= float(\n                        _revc("REV_REPRICE_S", 5.0)):\n                    w["last_reprice"] = now\n                    try:\n                        px = _rev_best_px(exchange, sym, action)\n                    except Exception as e:\n                        log.debug(f"[LiveRev] {sym} book error: {e}")\n                        return\n                    if px is None:\n                        return\n                    if _rev_beyond_chase(action, px, ref_px, chase):\n                        w["stop_reason"] = "chase_cap"\n                        if not _rev_cancel_and_confirm(exchange, sym, w):\n                            w["cancel_req"] = True\n                            return\n                    elif abs(px - float(w.get("order_px", 0.0))) > 0.0:\n                        if not _rev_cancel_and_confirm(exchange, sym, w):\n                            w["cancel_req"] = True\n                            return\n                    else:\n                        return\n                else:\n                    return\n    if w.get("cid"):\n        return                          # cancel not yet confirmed\n\n    # ── 2) decide: finish or (re)place ──\n    banked = float(w.get("banked_qty", 0.0))\n    remaining = qty_target - banked\n    min_notional = float(getattr(CFG, "MIN_NOTIONAL", 5.0))\n    stop = w.get("stop_reason")\n    if (stop or now >= float(w["fill_deadline"])\n            or remaining * ref_px < min_notional\n            or int(w.get("rejects", 0)) >= int(_revc("REV_MAX_REJECTS", 30))):\n        _rev_finish(exchange, sym, w, open_pos_live, assets,\n                    stop or ("filled" if remaining * ref_px < min_notional\n                             else "fill_timeout"))\n        return\n    try:\n        px = _rev_best_px(exchange, sym, action)\n    except Exception as e:\n        log.debug(f"[LiveRev] {sym} book error: {e}")\n        return\n    if px is None:\n        return\n    if _rev_beyond_chase(action, px, ref_px, chase):\n        w["stop_reason"] = "chase_cap"\n        return\n    q = _snap_qty(exchange, sym, remaining)\n    if q <= 0:\n        _rev_finish(exchange, sym, w, open_pos_live, assets, "qty_below_min")\n        return\n    if not _rate_can_place():\n        return\n    w["attempt"] = int(w.get("attempt", 0)) + 1\n    cid = _rev_cid(sym, float(w["sig_epoch"]), int(w["attempt"]))\n    w["cid"] = cid\n    w["cid_sent"] = True\n    w["order_px"] = px\n    w["last_reprice"] = now\n    save_reversal_watchers()            # persist BEFORE the order exists\n    try:\n        o = _rev_api(exchange.create_order, sym, "limit", side, q, px,\n                     params={"timeInForce": "GTX", "clientOrderId": cid})\n        w["order_id"] = str(o.get("id") or "")\n        w["cid_sent"] = False\n        log.info(f"[LiveRev] {sym} GTX {side} {q} @ {px} cid={cid}")\n    except Exception as e:\n        msg = str(e)\n        if ("-5022" in msg or "Post Only" in msg or "post only" in msg\n                or "immediately match" in msg):\n            w["rejects"] = int(w.get("rejects", 0)) + 1\n            _rev_clear_order(w)\n            log.info(f"[LiveRev] {sym} GTX rejected (retry): {msg[:120]}")\n        elif any(c in msg for c in ("-2019", "-4164", "-1111", "-4003",\n                                    "-2027", "-4028")):\n            _rev_clear_order(w)\n            log.warning(f"[LiveRev] {sym} order refused: {msg[:160]}")\n            _rev_finish(exchange, sym, w, open_pos_live, assets,\n                        "order_refused")\n        else:\n            # ambiguous (timeout etc.): keep cid, resolve by lookup next cycle\n            log.warning(f"[LiveRev] {sym} create_order ambiguous: {msg[:160]}")\n    save_reversal_watchers()\n\n\ndef _rev_finish(exchange, sym: str, w: Dict, open_pos_live: Dict, assets,\n                reason: str) -> None:\n    """No more orders: finalise a position if one exists, else expire."""\n    if float(w.get("banked_qty", 0.0)) > 0 or int(w.get("attempt", 0)) > 0:\n        _rev_finalize(exchange, sym, w, open_pos_live, assets, reason)\n    else:\n        _rev_expire(w, reason)\n\n\ndef _rev_finalize(exchange, sym: str, w: Dict, open_pos_live: Dict, assets,\n                  reason: str) -> None:\n    action = w["action"]\n    filled = float(w.get("banked_qty", 0.0))\n    cost = float(w.get("banked_cost", 0.0))\n    entry_px = (cost / filled) if (filled > 0 and cost > 0) else 0.0\n\n    ex = None\n    try:\n        ex = _rev_exch_position(exchange, sym)\n    except Exception:\n        ex = None\n    if ex is not None:                      # exchange is the source of truth\n        if not ex or ex.get("side") != action:\n            if filled > 0:\n                log.warning(f"[LiveRev] {sym} fills={filled} but exchange "\n                            f"shows no {action} position")\n            _rev_expire(w, f"{reason}:no_position")\n            return\n        ex_qty = float(ex["qty"])\n        if filled <= 0 or abs(ex_qty - filled) > max(1e-9, 0.02 * filled):\n            log.warning(f"[LiveRev] {sym} qty mismatch local={filled} "\n                        f"exchange={ex_qty} — adopting exchange")\n            filled = ex_qty\n            if float(ex.get("entry") or 0.0) > 0:\n                entry_px = float(ex["entry"])\n    if filled <= 0 or entry_px <= 0:\n        _rev_expire(w, f"{reason}:no_fill")\n        return\n\n    min_ratio = float(_revc("REV_MIN_FILL_RATIO", 0.0))\n    qty_target = float(w.get("qty_eff") or w["qty"])\n    if min_ratio > 0 and filled / max(qty_target, 1e-12) < min_ratio:\n        try:\n            _rev_api(exchange.create_order, sym, "market",\n                     "sell" if action == "BUY" else "buy", filled, None,\n                     params={"reduceOnly": True})\n            log.warning(f"[LiveRev] {sym} fill ratio below "\n                        f"{min_ratio:.2f} — flattened")\n            _rev_expire(w, f"{reason}:fill_ratio_flatten")\n            return\n        except Exception as e:\n            log.error(f"[LiveRev] {sym} flatten failed: {e}")\n\n    orig_sl_dist = float(w["orig_sl_dist"])\n    orig_tp_dist = float(w["orig_tp_dist"])\n    if orig_sl_dist <= 1e-12:\n        orig_sl_dist = entry_px * 0.015\n        orig_tp_dist = orig_sl_dist * float(getattr(CFG, "TP_MULT", 2.0))\n    _max_sl_frac = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))\n    if orig_sl_dist > entry_px * _max_sl_frac:\n        _rr = orig_tp_dist / max(orig_sl_dist, 1e-12)\n        orig_sl_dist = entry_px * _max_sl_frac\n        orig_tp_dist = orig_sl_dist * _rr\n    if action == "BUY":\n        new_sl = entry_px - orig_sl_dist\n        new_tp = entry_px + orig_tp_dist\n    else:\n        new_sl = entry_px + orig_sl_dist\n        new_tp = entry_px - orig_tp_dist\n\n    _sb = float(w.get("sigma_bar", 0.01))\n    _td = float(np.clip(CFG.TRAIL_KAPPA * _sb,\n                        CFG.TRAIL_MIN_FRAC, CFG.TRAIL_MAX_FRAC))\n    _ta = float(np.clip(CFG.TRAIL_ACT_KAPPA * _sb,\n                        CFG.TRAIL_ACT_MIN_FRAC, CFG.TRAIL_ACT_MAX_FRAC))\n    if _ta <= _td:\n        _ta = _td * 1.2\n\n    _lev = int(w["leverage"])\n    _mmr = float(w.get("mmr", getattr(CFG, "LIQ_FALLBACK_MMR", 0.02)))\n    _liq = None\n    if getattr(CFG, "LIQ_ENABLED", True):\n        try:\n            _liq = compute_liquidation_price(entry_px, action, _lev, _mmr)\n        except Exception:\n            _liq = None\n\n    _ad = assets.get(sym) if isinstance(assets, dict) else None\n    _ci_now = (len(_ad.closes) - 2) if _ad is not None else 0\n    _entry_ci = int(max(int(w.get("close_idx", 0)), _ci_now))\n\n    open_pos_live[sym] = {\n        "action": action,\n        "entry": entry_px,\n        "qty": filled,\n        "sl": new_sl,\n        "tp1": new_tp,\n        "T_info": float(w.get("T_info", 0.0)),\n        "dyn_risk": float(w.get("dyn_risk", 0.01)),\n        "entry_ts": _t_rev.time(),\n        "fill_ratio": filled / max(qty_target, 1e-9),\n        "leverage": _lev,\n        "trail_dist_frac": _td,\n        "trail_activate_frac": _ta,\n        "liq_price_estimated": _liq,\n        "mmr": _mmr,\n        "sl_dist_initial": float(abs(entry_px - new_sl)),\n        "_entry_ci": _entry_ci,\n        "_trail_bars_held": 0,\n        "_trail_peak_R": 0.0,\n        "_trail_last_update_ts": 0.0,\n        "_sym": sym,\n        "_orig_score": float(w.get("score", 0.0)),\n        "stage": "REVERSAL",\n    }\n    if _REV_STATE_FILE:                      # persist IMMEDIATELY\n        _lv_save_state(_REV_STATE_FILE, open_pos_live)\n\n    if getattr(CFG, "PROTECTIVE_ORDERS_ENABLED", True):\n        ok = False\n        retries = int(_revc("REV_PROTECT_RETRIES", 3))\n        for k in range(max(1, retries)):\n            try:\n                ok = bool(_place_protective_orders(exchange, sym,\n                                                   open_pos_live[sym]))\n            except Exception as e:\n                log.warning(f"[LiveRev] prot {sym} try{k + 1}: {e}")\n                ok = False\n            if ok:\n                break\n            _t_rev.sleep(0.5 * (k + 1))\n        if ok:\n            open_pos_live[sym]["_prot_last_sl"] = float(new_sl)\n            open_pos_live[sym]["_prot_last_tp"] = float(new_tp)\n        elif _revc("REV_FLATTEN_ON_UNPROTECTED", True):\n            log.error(f"[LiveRev] {sym} UNPROTECTED after {retries} tries "\n                      f"— emergency flatten")\n            try:\n                _rev_api(exchange.create_order, sym, "market",\n                         "sell" if action == "BUY" else "buy",\n                         _snap_qty(exchange, sym, filled) or filled, None,\n                         params={"reduceOnly": True})\n                open_pos_live.pop(sym, None)\n                if _REV_STATE_FILE:\n                    _lv_save_state(_REV_STATE_FILE, open_pos_live)\n                _rev_expire(w, "unprotected_flatten")\n                return\n            except Exception as e:\n                log.error(f"[LiveRev] {sym} emergency flatten FAILED: {e}")\n        if _REV_STATE_FILE:\n            _lv_save_state(_REV_STATE_FILE, open_pos_live)\n\n    log.info(f"✅ [LiveRev] {action} {sym} @ {entry_px:.6f} "\n             f"qty={filled:.6f}/{qty_target:.6f} sl={new_sl:.6f} "\n             f"tp={new_tp:.6f} ({reason})")\n    w["status"] = "FILLED"\n    w["entry"] = entry_px\n\n\n# ───────────────────────── startup recovery ─────────────────────────\ndef _rev_startup_recover(exchange, open_pos_live: Dict) -> None:\n    now = _t_rev.time()\n    dropped = 0\n    for sym in list(_REVERSAL_WATCHERS.keys()):\n        w = _REVERSAL_WATCHERS[sym]\n        st = w.get("status")\n        legacy = "start_ts" not in w\n        if legacy or st in ("FILLED", "EXPIRED"):\n            _REVERSAL_WATCHERS.pop(sym, None)\n            dropped += 1\n            continue\n        if st in ("WAITING_TOUCH", "WAITING_BOUNCE") \\\n                and now > float(w.get("expire_ts", 0.0)):\n            _REVERSAL_WATCHERS.pop(sym, None)\n            dropped += 1\n            continue\n        if st == "FILLING" and sym in open_pos_live:\n            # crash between position persist and watcher save\n            try:\n                if w.get("cid"):\n                    _rev_cancel_and_confirm(exchange, sym, w)\n            except Exception:\n                pass\n            _REVERSAL_WATCHERS.pop(sym, None)\n            dropped += 1\n    # orphan \'rev*\' entry orders with no owning watcher\n    _opt = getattr(exchange, "options", None)\n    _old_warn = None\n    try:\n        if isinstance(_opt, dict):\n            _old_warn = _opt.get("warnOnFetchOpenOrdersWithoutSymbol")\n            _opt["warnOnFetchOpenOrdersWithoutSymbol"] = False\n        known = {str(w.get("cid")) for w in _REVERSAL_WATCHERS.values()\n                 if w.get("cid")}\n        n_orph = 0\n        for o in _rev_api(exchange.fetch_open_orders, weight=40.0) or []:\n            cid = str(o.get("clientOrderId")\n                      or (o.get("info") or {}).get("clientOrderId") or "")\n            if not cid.startswith("rev") or cid in known:\n                continue\n            if o.get("reduceOnly"):\n                continue\n            try:\n                _rev_api(exchange.cancel_order, o.get("id"), o.get("symbol"))\n                n_orph += 1\n            except Exception as e:\n                log.warning(f"[LiveRev] orphan cancel failed {cid}: {e}")\n        if n_orph:\n            log.warning(f"[LiveRev] cancelled {n_orph} orphan entry orders")\n    except Exception as e:\n        log.warning(f"[LiveRev] orphan sweep skipped: {e}")\n    finally:\n        if isinstance(_opt, dict):\n            if _old_warn is None:\n                _opt.pop("warnOnFetchOpenOrdersWithoutSymbol", None)\n            else:\n                _opt["warnOnFetchOpenOrdersWithoutSymbol"] = _old_warn\n    if dropped:\n        log.info(f"[LiveRev] dropped {dropped} stale/legacy watchers on startup")\n    save_reversal_watchers()\n\n\n# ───────────────────────── main monitor ─────────────────────────\ndef monitor_reversal_watchers(exchange, open_pos_live: Dict,\n                                assets: Optional[Dict] = None,\n                                cap_now=None, corr_cache=None) -> None:\n    if not getattr(CFG, "REVERSAL_CONFIRM_ENABLED", False):\n        return\n    if not _REVERSAL_WATCHERS:\n        return\n    now = _t_rev.time()\n    if now < _REV_BACKOFF_UNTIL:\n        return\n    sub_tf, sub_sec = _rev_sub_info()\n    tw = int(getattr(CFG, "REVERSAL_TOUCH_SUBBARS", 20))\n    bw = int(getattr(CFG, "REVERSAL_BOUNCE_SUBBARS", 4))\n    max_fetch = int(_revc("REV_MAX_FETCH_PER_CYCLE", 10))\n    dirty = False\n    starts = 0\n    fetched = 0\n    scan_syms = []\n\n    for sym in list(_REVERSAL_WATCHERS.keys()):\n        w = _REVERSAL_WATCHERS[sym]\n        st = w.get("status", "WAITING_TOUCH")\n        try:\n            if st in ("FILLED", "EXPIRED"):\n                _REVERSAL_WATCHERS.pop(sym, None)\n                dirty = True\n                continue\n            if st == "FILLING":\n                _rev_advance_filling(exchange, sym, w, open_pos_live,\n                                     assets, now)\n                dirty = True\n                continue\n            if st == "READY_TO_FILL":\n                if starts < _REV_MAX_PER_CYCLE:\n                    _rev_handle_ready(exchange, sym, w, open_pos_live, now,\n                                      sub_sec, cap_now, corr_cache)\n                    if w["status"] == "FILLING":\n                        starts += 1\n                        _rev_advance_filling(exchange, sym, w,\n                                             open_pos_live, assets, now)\n                    dirty = True\n                continue\n            # waiting states — time-based hard expiry (never stuck)\n            start_ts = float(w["start_ts"])\n            if now > float(w.get("expire_ts", 0.0)):\n                _rev_expire(w, "max_age")\n                dirty = True\n                continue\n            if st == "WAITING_TOUCH" and \\\n                    now > start_ts + (tw + 3) * sub_sec:\n                _rev_expire(w, "touch_window_time")\n                dirty = True\n                continue\n            if st == "WAITING_BOUNCE" and \\\n                    now > start_ts + (int(w["touch_k"]) + bw + 4) * sub_sec:\n                _rev_expire(w, "bounce_time")\n                dirty = True\n                continue\n            if now >= float(w.get("next_fetch_ts", 0.0)):\n                scan_syms.append(sym)\n        except Exception as e:\n            w["err"] = int(w.get("err", 0)) + 1\n            log.warning(f"[LiveRev] {sym} step error #{w[\'err\']}: {e}")\n            if w["err"] >= 20 and w.get("status") not in ("FILLING",):\n                _rev_expire(w, "errors")\n                dirty = True\n\n    scan_syms.sort(key=lambda s: float(\n        _REVERSAL_WATCHERS[s].get("next_fetch_ts", 0.0)))\n    for sym in scan_syms:\n        if fetched >= max_fetch or _t_rev.time() < _REV_BACKOFF_UNTIL:\n            break\n        w = _REVERSAL_WATCHERS.get(sym)\n        if w is None or w.get("status") not in ("WAITING_TOUCH",\n                                                "WAITING_BOUNCE"):\n            continue\n        try:\n            fetched += 1\n            _rev_scan(exchange, sym, w, sub_tf, sub_sec, now)\n            dirty = True\n            if w["status"] == "READY_TO_FILL" and starts < _REV_MAX_PER_CYCLE:\n                _rev_handle_ready(exchange, sym, w, open_pos_live, now,\n                                  sub_sec, cap_now, corr_cache)\n                if w["status"] == "FILLING":\n                    starts += 1\n                    _rev_advance_filling(exchange, sym, w, open_pos_live,\n                                         assets, now)\n        except Exception as e:\n            w["next_fetch_ts"] = now + 5.0\n            w["err"] = int(w.get("err", 0)) + 1\n            log.debug(f"[LiveRev] {sym} scan error #{w[\'err\']}: {e}")\n            if w["err"] >= 40:\n                _rev_expire(w, "errors")\n                dirty = True\n    if dirty:\n        save_reversal_watchers()\n\n\n# ═══════════════════════════════════════════════════════════════\n\n\n'

# ─────────────────────────── simple exact-once patches ───────────────────────────
PATCHES = []

def P(name, old, new):
    PATCHES.append((name, old, new))

# P1 — Config: realistic fill model + new knobs
P("cfg.fill_at",
  '    REVERSAL_FILL_AT:        str   = "target" # [DEPRECATED] always target\n',
  '    REVERSAL_FILL_AT:        str   = "close"  # [REV-FIX v1] realizable: confirm-bar close (was "target")\n')

P("cfg.rev_knobs",
  '    REVERSAL_ESCAPE_CHECK_INTERVAL_S: float = 5.0\n',
  '    REVERSAL_ESCAPE_CHECK_INTERVAL_S: float = 5.0   # [REV-FIX v1] escape logic removed (unused)\n'
  '    # ══ [REV-FIX v1] reversal-confirm live/backtest parity knobs ══\n'
  '    REV_WATCHER_CAP: int = 50                 # memory cap ONLY (watchers never use position slots)\n'
  '    REV_FILL_MAX_WAIT_S: float = 90.0         # total time budget of the non-blocking FILLING state\n'
  '    REV_REPRICE_S: float = 5.0                # cancel/replace cadence (post-only at best bid/ask)\n'
  '    REV_MAX_CHASE_KAPPA: float = 0.15         # max chase above/below confirm close, in sigma_bar*px\n'
  '    REV_MAX_CONFIRM_AGE_SUBBARS: int = 2      # confirm bar older than this -> drop (stale)\n'
  '    REV_ENTRY_LATENCY_SUBBARS: int = 0        # extra sub-bars of latency (backtest + live window)\n'
  '    REV_MAX_REJECTS: int = 30                 # GTX (-5022) rejects before giving up\n'
  '    REV_PARITY_NO_SOFTCAP: bool = True        # live uses flat MAX_CONCURRENT_ASSETS like the backtest\n'
  '    REV_FLATTEN_ON_UNPROTECTED: bool = True   # no SL/TP after N tries -> reduce-only market flatten\n'
  '    REV_PROTECT_RETRIES: int = 3\n'
  '    REV_MAX_FETCH_PER_CYCLE: int = 10         # sub-bar REST fetches per loop iteration\n'
  '    REV_LEDGER_TTL_S: float = 172800.0        # once-per-signal ledger retention\n'
  '    REV_MIN_FILL_RATIO: float = 0.0           # >0: flatten fills below this ratio of target qty\n'
  '    REV_RESIZE_AT_FILL: bool = True           # rescale qty by capital(now)/capital(at signal)\n')

# P2 — backtest: entry sub-bar after the confirm bar (+ side channel to the simulator)
P("bt.fn_head",
  'def _check_reversal_fill_subbars(ad, sig, target0, cfg,\n',
  '_REV_ENTRY_SUB = {}   # [REV-FIX v1] (symbol, close_idx) -> entry sub-bar index inside the entry main bar\n\n\n'
  'def _check_reversal_fill_subbars(ad, sig, target0, cfg,\n')

P("bt.entry_index",
  '    # Flat index → main bar ci\n'
  '    _main_offset = confirm_k // sub_pm\n'
  '    confirm_main = start_main + _main_offset\n',
  '    # [REV-FIX v1] live can only enter AFTER the confirm bar closes:\n'
  '    # entry = first sub-bar after the confirm (+ optional latency).\n'
  '    _lat = max(0, int(getattr(cfg, \'REV_ENTRY_LATENCY_SUBBARS\', 0)))\n'
  '    entry_k = confirm_k + 1 + _lat\n'
  '    if entry_k >= n_flat:\n'
  '        return None\n'
  '    confirm_main = start_main + entry_k // sub_pm\n'
  '    _entry_sub = entry_k % sub_pm\n')

P("bt.return",
  '    return (int(confirm_main), float(fill_px))\n',
  '    _REV_ENTRY_SUB[(str(sig.symbol), int(sig.close_idx))] = int(_entry_sub)\n'
  '    return (int(confirm_main), float(fill_px))\n')

# P3 — backtest: deadline unit bug (sub-bar hours used as main-bar hours)
P("bt.deadline_units",
  "                _max_h = float(getattr(CFG, 'REVERSAL_MAX_HOURS', 24.0))\n"
  "                _sub_h = CFG.TF_HOURS / max(int(ad.sub_per_main or 16), 1)\n"
  "                _max_main_bars = max(1, int(np.ceil(\n"
  "                    _max_h / max(_sub_h, 1e-6)\n"
  "                )))\n",
  "                _max_h = float(getattr(CFG, 'REVERSAL_MAX_HOURS', 24.0))\n"
  "                # [REV-FIX v1] main-bar hours (was sub-bar hours -> 96 bars instead of 6)\n"
  "                _max_main_bars = max(1, int(np.ceil(\n"
  "                    _max_h / max(float(CFG.TF_HOURS), 1e-6)\n"
  "                )))\n")

# P4 — backtest simulator: exits start AFTER the entry sub-bar, not at the touch
P("bt.sim_sub_idx",
  "        # ══ [SL/TP SETUP — works for both fixed and no-fix] ══\n",
  "        # [REV-FIX v1] reversal-confirm: SL/TP are evaluated only from the\n"
  "        # entry sub-bar (after the confirm), never from the touch sub-bar.\n"
  "        if (getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False)\n"
  "                and isinstance(fill_info, tuple) and fill_info[0] == 'S1'):\n"
  "            _rk = (str(sym), int(sig.close_idx))\n"
  "            if _rk in _REV_ENTRY_SUB:\n"
  "                opt_sub_idx = int(_REV_ENTRY_SUB[_rk])\n\n"
  "        # ══ [SL/TP SETUP — works for both fixed and no-fix] ══\n")

# P6/P7/P8 — live slot gating (open positions only)
P("live.effective_max",
  "            effective_max = min(\n"
  "                cfg.MAX_CONCURRENT_ASSETS,\n"
  "                max(_soft_cap, _n_open + 1)\n"
  "            )\n",
  "            effective_max = min(\n"
  "                cfg.MAX_CONCURRENT_ASSETS,\n"
  "                max(_soft_cap, _n_open + 1)\n"
  "            )\n"
  "            # [REV-FIX v1] parity: the backtest gates on the flat MAX_CONCURRENT_ASSETS\n"
  "            if (getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False)\n"
  "                    and getattr(CFG, 'REV_PARITY_NO_SOFTCAP', True)):\n"
  "                effective_max = int(cfg.MAX_CONCURRENT_ASSETS)\n")

P("live.scan_gate",
  "            if len(open_pos_live) < effective_max:\n",
  "            # [REV-FIX v1] reversal mode: keep scanning/registering even when all slots\n"
  "            # are taken - slots are enforced at FILL time (like the backtest)\n"
  "            if (len(open_pos_live) < effective_max\n"
  "                    or getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False)):\n")

P("live.exposure_gate_1",
  "                                       + len(_WATCHED_SIGNALS))\n"
  "                    if _total_exposure >= int(cfg.MAX_CONCURRENT_ASSETS):\n",
  "                                       + len(_WATCHED_SIGNALS))\n"
  "                    if (_total_exposure >= int(cfg.MAX_CONCURRENT_ASSETS)\n"
  "                            and not getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False)):\n")

P("live.exposure_gate_2",
  "                            _total_exposure = (len(_PENDING_ORDERS)\n"
  "                                               + len(open_pos_live)\n"
  "                                               + len(_WATCHED_SIGNALS)\n"
  "                                               + len(_REVERSAL_WATCHERS))\n"
  "                            if _total_exposure >= int(CFG.MAX_CONCURRENT_ASSETS):\n"
  "                                log.debug(\n"
  "                                    f\"[Watch] exposure cap \"\n"
  "                                    f\"({_total_exposure}≥\"\n"
  "                                    f\"{CFG.MAX_CONCURRENT_ASSETS}) \"\n"
  "                                    f\"— skip {sym}\"\n"
  "                                )\n"
  "                                continue\n",
  "                            if getattr(CFG, \"REVERSAL_CONFIRM_ENABLED\", False):\n"
  "                                # [REV-FIX v1] watchers NEVER consume position slots\n"
  "                                _total_exposure = len(_REVERSAL_WATCHERS)\n"
  "                                _exp_cap = int(getattr(CFG, 'REV_WATCHER_CAP', 50))\n"
  "                            else:\n"
  "                                _total_exposure = (len(_PENDING_ORDERS)\n"
  "                                                   + len(open_pos_live)\n"
  "                                                   + len(_WATCHED_SIGNALS))\n"
  "                                _exp_cap = int(CFG.MAX_CONCURRENT_ASSETS)\n"
  "                            if _total_exposure >= _exp_cap:\n"
  "                                log.debug(\n"
  "                                    f\"[Watch] exposure cap \"\n"
  "                                    f\"({_total_exposure}≥{_exp_cap}) \"\n"
  "                                    f\"— skip {sym}\"\n"
  "                                )\n"
  "                                continue\n")

# registration call: pass the capital reference for fill-time re-sizing
P("live.register_call",
  "                                    exchange, sym, sd, qty, sig,\n"
  "                                    int(dynamic_leverage), assets[sym]\n"
  "                                )\n",
  "                                    exchange, sym, sd, qty, sig,\n"
  "                                    int(dynamic_leverage), assets[sym],\n"
  "                                    cap_ref=(cap_live if 'cap_live' in dir() else None)\n"
  "                                )\n")

# startup recovery
P("live.startup",
  "    # ══ [LiveRev] Drop watchers older than REVERSAL_MAX_HOURS ══\n"
  "    if _REVERSAL_WATCHERS:\n"
  "        _now_rev = _t_rev.time()\n"
  "        _max_s = float(CFG.REVERSAL_MAX_HOURS) * 3600.0\n"
  "        _dropped = 0\n"
  "        for _s in list(_REVERSAL_WATCHERS.keys()):\n"
  "            _w = _REVERSAL_WATCHERS[_s]\n"
  "            if _now_rev - float(_w.get(\"close_ts\", _now_rev)) > _max_s:\n"
  "                _REVERSAL_WATCHERS.pop(_s, None)\n"
  "                _dropped += 1\n"
  "        if _dropped:\n"
  "            log.info(f\"[LiveRev] Dropped {_dropped} stale watchers on startup\")\n"
  "            save_reversal_watchers()\n",
  "    # ══ [LiveRev] [REV-FIX v1] startup recovery: stale/legacy watchers, orphan entry orders ══\n"
  "    if getattr(CFG, \"REVERSAL_CONFIRM_ENABLED\", False):\n"
  "        try:\n"
  "            _rev_startup_recover(exchange, open_pos_live)\n"
  "        except Exception as _e:\n"
  "            log.warning(f\"[LiveRev] startup recovery failed: {_e}\")\n")

# monitor call: capital + correlation context for the fill-time gate
P("live.monitor_call",
  "                monitor_reversal_watchers(\n"
  "                    exchange, open_pos_live,\n"
  "                    assets=assets if 'assets' in dir() else None\n"
  "                )\n",
  "                monitor_reversal_watchers(\n"
  "                    exchange, open_pos_live,\n"
  "                    assets=assets if 'assets' in dir() else None,\n"
  "                    cap_now=(cap_live if 'cap_live' in dir() else None),\n"
  "                    corr_cache=(corr_cache if 'corr_cache' in dir() else None)\n"
  "                )\n")

# --reset also wipes the ledger
P("cli.reset_files",
  '            "reversal_watchers_testnet.json",\n',
  '            "reversal_watchers_testnet.json",\n'
  '            "reversal_ledger_live.json",\n'
  '            "reversal_ledger_testnet.json",\n')


def _once(src, old, name):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"[ABORT] anchor '{name}' matched {n} times (expected exactly 1). "
                         f"The file differs from the audited version - nothing was written.")


def apply(src: str) -> str:
    if MARK in src:
        raise SystemExit("[ABORT] file already contains [REV-FIX v1] - nothing to do.")
    # 1) simple patches
    for name, old, new in PATCHES:
        _once(src, old, name)
    for name, old, new in PATCHES:
        src = src.replace(old, new, 1)
    # 2) replace the whole old live reversal module
    hdr = "# [LIVE REVERSAL] Touch-and-Bounce on sub-bars, live execution"
    end = "def run_live(cfg, exchange):"
    _once(src, hdr, "live.block.start")
    _once(src, end, "live.block.end")
    i = src.index(hdr)
    start = src.rfind("\n", 0, i - 1) + 1
    if not src[start:].startswith("# ═"):
        raise SystemExit("[ABORT] live block start separator not found")
    j = src.index(end)
    if j <= start:
        raise SystemExit("[ABORT] live block markers out of order")
    removed = src[start:j]
    for gone in ("_execute_reversal_fill", "_physics_escape_decision", "_fetch_live_subbars"):
        if gone not in removed:
            raise SystemExit(f"[ABORT] expected '{gone}' inside the replaced block")
    src = src[:start] + NEW_LIVE_BLOCK + src[j:]
    return src


def _undefined_names(path):
    try:
        from pyflakes.api import check
        from pyflakes.reporter import Reporter
        import io
        out, err = io.StringIO(), io.StringIO()
        check(open(path, encoding="utf-8").read(), path, Reporter(out, err))
        return sorted({l.split("undefined name")[1].strip() for l in out.getvalue().splitlines()
                       if "undefined name" in l})
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default="trading_2_live4.py")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--inplace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(a.src, "r", encoding="utf-8") as f:
        src = f.read()
    new = apply(src)
    ast.parse(new)                       # syntax gate
    print(f"[OK] {len(PATCHES)} anchors + live block replaced; syntax OK")
    if a.dry_run:
        return
    out = a.src if a.inplace else (a.out or os.path.splitext(a.src)[0] + "_revfix.py")
    if a.inplace:
        bak = f"{a.src}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(a.src, bak)
        print(f"[OK] backup -> {bak}")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    py_compile.compile(tmp, doraise=True)   # byte-compile gate
    os.replace(tmp, out)
    print(f"[OK] written -> {out}")
    u0, u1 = _undefined_names(a.src), _undefined_names(out)
    if u0 is not None and u1 is not None:
        print(f"[pyflakes] undefined names before: {u0}")
        print(f"[pyflakes] undefined names after : {u1}")
        if set(u1) - set(u0):
            print("[WARN] NEW undefined names introduced:", sorted(set(u1) - set(u0)))
            sys.exit(2)


if __name__ == "__main__":
    main()
