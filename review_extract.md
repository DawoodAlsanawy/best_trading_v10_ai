# 🔍 Review Extract — trading_2_live4_claude_v3.py
**أسطر:** 18,455  |  **حجم:** 814,952 bytes

## 1️⃣ حقول Config الحرجة
```
   230:     MIN_NOTIONAL: float = 5.0
   231:     SL_FACTOR: float = 0.5
   232:     TP_BETAS: Tuple = (1.5,)
   245:     MAX_CONCURRENT_ASSETS: int   = 3   # [ABL6] 5 -> 3
   250:     TOPO_DIV_THRESHOLD: float = 0.05
   260:     REVERSAL_MIN_SCORE: int=3; LYA_WINDOW: int=20
   326:     PO_PENETRATION_BPS: float = 1.0      # match backtest's FILL_PENETRATION_BPS
   327:     PO_MAX_WAIT_S: int = 0 # 200              # entry wait time (per attempt)
   328:     PO_EXIT_MAX_WAIT_S: int = 45          # reduced from 180 to prevent long blocking
   329:     PO_REPRICE_S: float = 3.0            # cancel/replace interval
   330:     PO_FILL_THRESHOLD: float = 0.50      # accept partial if ≥ 50%
   331:     PO_EXIT_FALLBACK_MARKET: bool = True # exit → market after timeout
   332:     PO_DRIFT_BPS: float = 0.5            # reprice if target drifts > this
   341:     TRAIL_ENABLED: bool = True
   342:     TRAIL_ACTIVATE_MFE: float = 0.004    # activate after 0.4% MFE
   343:     TRAIL_DISTANCE: float = 0.003        # trail 0.3% below peak
   344:     TRAIL_MIN_STEP: float = 0.0005       # only move SL if improvement ≥ 0.05%
   371:     TRAIL_DYNAMIC: bool = True
   372:     TRAIL_KAPPA: float = 0.30                # tuned to 1h timeframe
   373:     TRAIL_MIN_FRAC: float = 0.002
   374:     TRAIL_MAX_FRAC: float = 0.008
   375:     TRAIL_ACT_KAPPA: float = 0.40            # tuned to 1h timeframe
   376:     TRAIL_ACT_MIN_FRAC: float = 0.003
   377:     TRAIL_ACT_MAX_FRAC: float = 0.012
   379:     APEX_SIGMA_SCALED: bool = True
   380:     APEX_KAPPA_PNL: float = 0.5
   381:     APEX_KAPPA_ENERGY: float = 0.5
   382:     APEX_KAPPA_ACCEL: float = 0.3
   397:     PO_FIXED_PRICE: bool = False              # use sig.price, hold it fixed
   402: #    SL_REF_KAPPA: float = 2.0             # SL/σ = κ × uncertainty / (1 + fric×5)
   403: #    SL_MIN_SIGMA: float = 1.0             # أدنى SL بوحدة σ
   404: #    SL_MAX_SIGMA: float = 5.0             # أقصى SL بوحدة σ
   405:     SL_REF_KAPPA: float = 0.8     # كان 2.0
   406:     SL_MIN_SIGMA: float = 3.0     # كان 1.0
   407:     SL_MAX_SIGMA: float = 8.0     # كان 5.0
   426:     PO_MAX_ATTEMPTS: int = 3              # reduced from 5 (rate-limit safety)
   427:     PO_MAX_DRIFT_BPS: float = 5.0
   428:     PO_MIN_ACCEPT_RATIO: float = 0.01     # reject below 50% (was 0.15, comment was misleading)
   450:     SR_SL_PROXIMITY: float = 0.008        # 0.8% max gap SL↔level
   490:     SL_WIDEN_MULT: float = 1.5
   494:     PO_USE_TICK_PENETRATION: bool = True
   507:     LIQ_SAFETY_MULT: float = 1.5          # SL gap × this < Liq gap
   508:     LIQ_EMERGENCY_PROGRESS: float = 0.7    # 70% toward Liq → emergency exit
   509:     LIQ_FALLBACK_MMR: float = 0.02         # 2% if exchange MMR unavailable
   510:     LIQ_ENABLED: bool = True               # master switch (for testing)
   512:     PROTECTIVE_ORDERS_ENABLED: bool = True
   513:     PROTECTIVE_WORKING_TYPE: str = "MARK_PRICE"
   514:     PROTECTIVE_SYNC_MIN_STEP_FRAC: float = 0.001   # 0.1% SL movement → resync
   515:     PROTECTIVE_MAX_RETRIES: int = 2
   525:     LIQ_EMERGENCY_ENABLED: bool = True
   527:     LIQ_EMERGENCY_REFRESH_AT: float = 0.40
   529:     LIQ_EMERGENCY_REFRESH_COOLDOWN_S: int = 30
   531:     LIQ_EMERGENCY_WARN_AT: int = 5
   570:     TRAIL_ADVANCED_ENABLED: bool = True
   572:     TRAIL_CHANDELIER_K: float = 0.50
   573:     TRAIL_ACTIVATE_SIGMA_MULT: float = 0.40
   574:     TRAIL_RATCHET_LEVELS: Tuple = (
   585:     TRAIL_MIN_R_FRACTION: float = 0.3
   586:     TRAIL_PHYSICS_ENABLED: bool = True
   587:     TRAIL_ACCEL_SCALE: float = 0.005
   588:     TRAIL_FRICTION_SCALE: float = 0.15
   589:     TRAIL_GAUGE_SCALE: float = 0.20
   590:     TRAIL_PHYSICS_CLAMP: Tuple = (0.7, 1.3)
   591:     TRAIL_REGIME_ENABLED: bool = True
   592:     TRAIL_REGIME_LOOKBACK: int = 100
   593:     TRAIL_REGIME_EXPLOSIVE_MULT: float = 1.1
   594:     TRAIL_REGIME_TRENDING_MULT: float = 1.0
   595:     TRAIL_REGIME_RANGING_MULT: float = 0.9
   596:     TRAIL_LEGACY_FLOOR_ENABLED: bool = True
   598:     TRAIL_STRUCTURE_ENABLED: bool = True
   599:     TRAIL_STRUCTURE_LOOKBACK: int = 50
   600:     TRAIL_STRUCTURE_BUFFER_SIGMA: float = 0.3
   602:     TRAIL_TIME_DECAY_ENABLED: bool = True
   603:     TRAIL_TIME_DECAY_BARS: int = 20
   604:     TRAIL_TIME_DECAY_FACTOR: float = 0.85
   605:     TRAIL_TIME_DECAY_MIN_MULT: float = 0.5
   607:     TRAIL_MIN_STEP_FRAC: float = 0.0015
   608:     TRAIL_UPDATE_MIN_INTERVAL_S: int = 3
   614:     PO_EXIT_MAX_WAIT_S: int = 12            # was 45 (still used for soft exits)
   615:     PO_EXIT_URGENT_WAIT_S: int = 4          # for SL/TP/LiqProximity
   616:     PO_EXIT_URGENT_CROSS_SPREAD: bool = True
   630:     TRAIL_ACTIVATE_AT_R: float = 2.5    # activate at +1R of profit
   648:     PARTIAL_TP_ENABLED: bool = True
   649:     PARTIAL_TP_R: float = 1.5           # [ABL4a] 3.0 -> 1.5
   650:     PARTIAL_TP_PCT: float = 0.50         # close 50% at that level
   651:     TP_MULT: float = 5.0    # كان 2.0 → الآن 1.5 (R:R = 1.5)
   652:     APEX_ENABLED: bool = True     # عطّله مؤقتاً حتى نضبط عتباته
   657:     BREAKEVEN_ENABLED: bool = True
   658:     BREAKEVEN_AT_R: float = 1.0
   741:     OPP_TP_ENABLED: bool = False
   742:     OPP_TP_SCORE_MULT: float = 1.20          # score_opp ≥ 1.2 × score_entry
   743:     OPP_TP_MIN_PROFIT_R: float = 0.5         # ربح أدنى مضمون بوحدات R
   744:     OPP_TP_MIN_DELTA_R: float = 0.3          # تحسّن أدنى لنقل TP
   745:     OPP_TP_MAX_AGE_BARS: int = 4             # عمر الإشارة المعاكسة
   746:     OPP_TP_RESPECT_PARTIAL: bool = True      # لا تنقل TP تحت trigger partial
   812:     REVERSAL_CONFIRM_ENABLED: bool = False
   813:     REVERSAL_TOUCH_SUBBARS:  int   = 20       # 5h @ 15m sub-bar
   814:     REVERSAL_BOUNCE_SUBBARS: int   = 4        # 1h @ 15m sub-bar
   815:     REVERSAL_MAX_HOURS:      float = 24.0     # signal validity window
   816:     REVERSAL_CONFIRM_MODE:   str   = "close_back"
   817:     REVERSAL_CONFIRM_KAPPA:  float = 0.20     # for sigma_bounce mode
   818:     REVERSAL_FILL_AT:        str   = "target"  # [REV-FIX v1] realizable: confirm-bar close (was "target")
   825:     REVERSAL_ESCAPE_ENABLED: bool = True
   826:     REVERSAL_ESCAPE_D_SIGMA_MIN: float = 1.0
   827:     REVERSAL_ESCAPE_D_SIGMA_MAX: float = 2.0
   828:     REVERSAL_ESCAPE_RHO_THRESHOLD: float = 1.5
   829:     REVERSAL_ESCAPE_CHECK_INTERVAL_S: float = 5.0   # [REV-FIX v1] escape logic removed (unused)
   831:     REV_WATCHER_CAP: int = 50                 # memory cap ONLY (watchers never use position slots)
   832:     REV_FILL_MAX_WAIT_S: float = 90.0         # total time budget of the non-blocking FILLING state
   833:     REV_REPRICE_S: float = 5.0                # cancel/replace cadence (post-only at best bid/ask)
   834:     REV_MAX_CHASE_KAPPA: float = 0.15         # max chase above/below confirm close, in sigma_bar*px
   835:     REV_MAX_CONFIRM_AGE_SUBBARS: int = 2      # confirm bar older than this -> drop (stale)
   836:     REV_ENTRY_LATENCY_SUBBARS: int = 0        # extra sub-bars of latency (backtest + live window)
   837:     REV_MAX_REJECTS: int = 30                 # GTX (-5022) rejects before giving up
   838:     REV_PARITY_NO_SOFTCAP: bool = True        # live uses flat MAX_CONCURRENT_ASSETS like the backtest
   839:     REV_FLATTEN_ON_UNPROTECTED: bool = True   # no SL/TP after N tries -> reduce-only market flatten
   840:     REV_PROTECT_RETRIES: int = 3
   841:     REV_MAX_FETCH_PER_CYCLE: int = 10         # sub-bar REST fetches per loop iteration
   842:     REV_LEDGER_TTL_S: float = 172800.0        # once-per-signal ledger retention
   843:     REV_MIN_FILL_RATIO: float = 0.0           # >0: flatten fills below this ratio of target qty
   844:     REV_RESIZE_AT_FILL: bool = True           # rescale qty by capital(now)/capital(at signal)
   861:     REV_UNIV_BACKGROUND: bool = True          # universe refresh in a background thread
   865:     REV_LADDER_ENABLED: bool = False
   866:     REV_LADDER_OFFSETS_SIGMA: tuple = (0.0, 0.3, 0.6)   # levels below target, in sigma_bar*target
   867:     REV_LADDER_WEIGHTS: tuple = (0.40, 0.35, 0.25)      # share of qty per level (normalised)
   868:     REV_LADDER_QP_PCT: float = 0.05                     # queue-priority order at target (out of L0); 0 = off
   869:     REV_LADDER_MAX_WAIT_S: float = 21600.0              # hard stop after the bounce confirms (6h)
   870:     REV_LADDER_POLL_S: float = 10.0                     # queue-priority order polling cadence
   871:     REV_LADDER_MIN_FILL_RATIO: float = 0.0              # >0: flatten ladders that end below this ratio
```

## 2️⃣ الدوال الكاملة (Reversal / Ladder / Apex)

### 📌 `_bar_confirms_bounce` — lines 14281–14311 (31 سطر)
```python
def _bar_confirms_bounce(w: Dict, close: float) -> bool:
    action = w["action"]
    target = float(w["target"])
    mode = str(CFG.REVERSAL_CONFIRM_MODE)

    if mode == "close_back":
        return (action == "BUY" and close > target) or \
               (action == "SELL" and close < target)

    if mode == "sigma_bounce":
        kappa = float(CFG.REVERSAL_CONFIRM_KAPPA)
        sigma = float(w.get("sigma_bar", 0.01))
        thr = kappa * sigma * target
        if action == "BUY":
            return (close - target) > thr
        return (target - close) > thr

    if mode == "bar_color":
        # prev_close is maintained by the scanner for EVERY sub-bar
        prev = w.get("prev_close")
        if prev is None:
            return False
        return (action == "BUY" and close > float(prev)) or \
               (action == "SELL" and close < float(prev))

    if mode == "two_bar":
        ok = (close > target) if action == "BUY" else (close < target)
        w["two_bar_count"] = (int(w.get("two_bar_count", 0)) + 1) if ok else 0
        return w["two_bar_count"] >= 2

    return False
```

### 📌 `_lad_all_recs` — lines 15494–15495 (2 سطر)
```python
def _lad_all_recs(w: Dict) -> List[Dict]:
    return ([w["qp"]] if w.get("qp") else []) + list(w.get("ladder") or [])
```

### 📌 `_lad_apply` — lines 15543–15553 (11 سطر)
```python
def _lad_apply(r: Dict, o: Dict) -> None:
    r["filled"] = float(o.get("filled") or 0.0)
    a = o.get("average")
    try:
        a = float(a) if a else 0.0
    except Exception:
        a = 0.0
    r["avg"] = a if a > 0 else float(o.get("price") or r["px"])
    r["order_id"] = str(o.get("id") or r.get("order_id") or "")
    if str(o.get("status") or "open") in _REV_TERMINAL:
        r["status"] = "done"
```

### 📌 `_lad_book` — lines 15531–15540 (10 سطر)
```python
def _lad_book(exchange, sym: str):
    try:
        ob = _rev_api(exchange.fetch_order_book, sym, 5, weight=2.0)
        bids, asks = ob.get("bids") or [], ob.get("asks") or []
        if not bids or not asks:
            return None, None
        return float(bids[0][0]), float(asks[0][0])
    except Exception as e:
        log.debug(f"[Ladder] {sym} book error: {e}")
        return None, None
```

### 📌 `_lad_cancel` — lines 15624–15648 (25 سطر)
```python
def _lad_cancel(exchange, sym: str, rec: Dict) -> bool:
    """True once the record is TERMINAL (no live order left)."""
    if rec.get("status") == "new":
        rec["status"] = "done"
        return True
    if rec.get("status") != "open" or not rec.get("cid"):
        return True
    try:
        if rec.get("order_id"):
            _rev_api(exchange.cancel_order, rec["order_id"], sym)
        else:
            _rev_api(exchange.cancel_order, None, sym,
                     params={"origClientOrderId": rec["cid"]})
    except Exception as e:
        if not _rev_is_not_found(e):
            log.debug(f"[Ladder] {sym} cancel error: {e}")
    try:
        o = _rev_find_order(exchange, sym, rec["cid"], rec.get("order_id"))
    except Exception:
        return False
    if o is None:
        rec["status"] = "done"
        return True
    _lad_apply(rec, o)
    return rec["status"] == "done"
```

### 📌 `_lad_cid` — lines 15483–15485 (3 سطر)
```python
def _lad_cid(sym: str, w: Dict, tag: str, attempt: int) -> str:
    h = _hl_rev.md5(sym.encode()).hexdigest()[:8]
    return f"rev{int(w['sig_epoch'])}x{h}x{tag}{int(attempt)}"[:36]
```

### 📌 `_lad_finish` — lines 15875–15896 (22 سطر)
```python
def _lad_finish(exchange, sym: str, w: Dict, open_pos_live: Dict,
                reason: str) -> None:
    f, c = _lad_totals(w)
    qt = float(w.get("qty_eff") or w["qty"])
    _lad_stats(w, reason)
    if f <= 0:
        _rev_expire(w, f"ladder:{reason}")
        return
    min_ratio = float(_cfg3("REV_LADDER_MIN_FILL_RATIO", 0.0))
    if min_ratio > 0 and f / max(qt, 1e-12) < min_ratio:
        pos = open_pos_live.get(sym)
        if pos is not None and _lad_flatten(exchange, sym, w["action"],
                                            float(pos["qty"])):
            open_pos_live.pop(sym, None)
            if _REV_STATE_FILE:
                _lv_save_state(_REV_STATE_FILE, open_pos_live)
            _rev_expire(w, "ladder:min_fill_flatten")
            return
    w["status"] = "FILLED"
    w["entry"] = c / f
    log.info(f"✅ [Ladder] {sym} done ({reason}): fill {f:.6f}/{qt:.6f} "
             f"vwap={c / f:.6f}")
```

### 📌 `_lad_flatten` — lines 15705–15724 (20 سطر)
```python
def _lad_flatten(exchange, sym: str, action: str, qty: float) -> bool:
    try:
        ex = _rev_exch_position(exchange, sym)
        if ex:
            qty = float(ex.get("qty") or qty)
    except Exception:
        pass
    try:
        _rev_api(exchange.create_order, sym, "market",
                 "sell" if action == "BUY" else "buy",
                 _snap_qty(exchange, sym, qty) or qty, None,
                 params={"reduceOnly": True})
    except Exception as e:
        log.error(f"[Ladder] {sym} flatten FAILED: {e}")
        return False
    try:
        _cancel_all_protective_orders(exchange, sym)
    except Exception:
        pass
    return True
```

### 📌 `_lad_levels` — lines 15466–15472 (7 سطر)
```python
def _lad_levels():
    offs = list(_cfg3("REV_LADDER_OFFSETS_SIGMA", (0.0, 0.3, 0.6)))
    wts = list(_cfg3("REV_LADDER_WEIGHTS", (0.40, 0.35, 0.25)))
    n = min(len(offs), len(wts))
    offs, wts = offs[:n], wts[:n]
    tot = float(sum(wts)) or 1.0
    return [(float(o), float(x) / tot) for o, x in zip(offs, wts)]
```

### 📌 `_lad_liq` — lines 15668–15676 (9 سطر)
```python
def _lad_liq(w: Dict, entry_px: float):
    if not getattr(CFG, "LIQ_ENABLED", True):
        return None
    try:
        return compute_liquidation_price(entry_px, w["action"],
                                         int(w["leverage"]),
                                         float(w.get("mmr", 0.02)))
    except Exception:
        return None
```

### 📌 `_lad_new_pos` — lines 15679–15702 (24 سطر)
```python
def _lad_new_pos(sym: str, w: Dict, entry_px: float, qty: float, assets) -> Dict:
    sl, tp, osd = _lad_sl_tp(w, entry_px)
    sb = float(w.get("sigma_bar", 0.01))
    td = float(np.clip(CFG.TRAIL_KAPPA * sb, CFG.TRAIL_MIN_FRAC, CFG.TRAIL_MAX_FRAC))
    ta = float(np.clip(CFG.TRAIL_ACT_KAPPA * sb, CFG.TRAIL_ACT_MIN_FRAC,
                       CFG.TRAIL_ACT_MAX_FRAC))
    if ta <= td:
        ta = td * 1.2
    _ad = assets.get(sym) if isinstance(assets, dict) else None
    ci_now = (len(_ad.closes) - 2) if _ad is not None else 0
    qt = float(w.get("qty_eff") or w["qty"])
    return {
        "action": w["action"], "entry": entry_px, "qty": qty, "sl": sl,
        "tp1": tp, "T_info": float(w.get("T_info", 0.0)),
        "dyn_risk": float(w.get("dyn_risk", 0.01)), "entry_ts": _t_rev.time(),
        "fill_ratio": qty / max(qt, 1e-9), "leverage": int(w["leverage"]),
        "trail_dist_frac": td, "trail_activate_frac": ta,
        "liq_price_estimated": _lad_liq(w, entry_px),
        "mmr": float(w.get("mmr", 0.02)), "sl_dist_initial": float(osd),
        "_entry_ci": int(max(int(w.get("close_idx", 0)), ci_now)),
        "_trail_bars_held": 0, "_trail_peak_R": 0.0,
        "_trail_last_update_ts": 0.0, "_sym": sym,
        "_orig_score": float(w.get("score", 0.0)), "stage": "REVERSAL",
    }
```

### 📌 `_lad_new_rec` — lines 15488–15491 (4 سطر)
```python
def _lad_new_rec(name: str, px: float, qty: float) -> Dict:
    return {"name": name, "cid": None, "order_id": None, "cid_sent": False,
            "px": float(px), "qty": float(qty), "filled": 0.0, "avg": 0.0,
            "status": "new", "rejects": 0, "attempt": 0}
```

### 📌 `_lad_place` — lines 15556–15593 (38 سطر)
```python
def _lad_place(exchange, sym: str, w: Dict, rec: Dict, bid, ask,
               clamp: bool = True) -> str:
    side = w["side_ccxt"]
    px = float(rec["px"])
    if clamp:                       # never cross the book (post-only)
        if side == "buy" and bid is not None:
            px = min(px, bid)
        if side == "sell" and ask is not None:
            px = max(px, ask)
        px = _rev_snap_price(exchange, sym, px, side)
    rec["attempt"] = int(rec.get("attempt", 0)) + 1
    cid = _lad_cid(sym, w, rec["name"], rec["attempt"])
    rec.update(cid=cid, cid_sent=True, px=px, status="open")
    save_reversal_watchers()        # persist BEFORE the order exists
    try:
        o = _rev_api(exchange.create_order, sym, "limit", side, rec["qty"], px,
                     params={"timeInForce": "GTX", "clientOrderId": cid})
        rec["order_id"] = str(o.get("id") or "")
        rec["cid_sent"] = False
        log.info(f"[Ladder] {sym} {rec['name']} GTX {side} {rec['qty']} @ {px} "
                 f"cid={cid}")
        return "placed"
    except Exception as e:
        msg = str(e)
        if ("-5022" in msg or "Post Only" in msg or "post only" in msg
                or "immediately match" in msg):
            rec["rejects"] = int(rec.get("rejects", 0)) + 1
            rec.update(cid=None, cid_sent=False, status="new")
            if rec["rejects"] >= int(_revc("REV_MAX_REJECTS", 30)):
                rec["status"] = "done"
            return "reject"
        if any(c in msg for c in ("-2019", "-4164", "-1111", "-4003",
                                  "-2027", "-4028")):
            rec.update(cid=None, cid_sent=False, status="done")
            log.warning(f"[Ladder] {sym} {rec['name']} refused: {msg[:140]}")
            return "fatal"
        log.warning(f"[Ladder] {sym} {rec['name']} create ambiguous: {msg[:140]}")
        return "ambiguous"          # stays 'open' with cid; poll resolves it
```

### 📌 `_lad_poll` — lines 15596–15621 (26 سطر)
```python
def _lad_poll(exchange, sym: str, recs: List[Dict]) -> None:
    live = [r for r in recs if r.get("status") == "open" and r.get("cid")]
    if not live:
        return
    try:
        open_list = _rev_api(exchange.fetch_open_orders, sym) or []
    except Exception as e:
        log.debug(f"[Ladder] {sym} open-orders error: {e}")
        return
    by_cid = {}
    for o in open_list:
        k = str(o.get("clientOrderId")
                or (o.get("info") or {}).get("clientOrderId") or "")
        by_cid[k] = o
    for r in live:
        o = by_cid.get(r["cid"])
        if o is None:
            try:
                o = _rev_find_order(exchange, sym, r["cid"], r.get("order_id"))
            except Exception as e:
                log.debug(f"[Ladder] {sym} lookup error: {e}")
                continue
            if o is None:           # create never reached the exchange
                r.update(cid=None, order_id=None, cid_sent=False, status="new")
                continue
        _lad_apply(r, o)
```

### 📌 `_lad_protect` — lines 15727–15745 (19 سطر)
```python
def _lad_protect(exchange, sym: str, pos: Dict, grown: bool) -> bool:
    if not getattr(CFG, "PROTECTIVE_ORDERS_ENABLED", True):
        return True
    if grown:                       # leg quantities changed -> rebuild the legs
        try:
            _cancel_all_protective_orders(exchange, sym)
        except Exception as e:
            log.debug(f"[Ladder] {sym} protective cancel error: {e}")
    retries = int(_revc("REV_PROTECT_RETRIES", 3))
    for k in range(max(1, retries)):
        try:
            if _place_protective_orders(exchange, sym, pos):
                pos["_prot_last_sl"] = float(pos["sl"])
                pos["_prot_last_tp"] = float(pos["tp1"])
                return True
        except Exception as e:
            log.warning(f"[Ladder] prot {sym} try{k + 1}: {e}")
        _t_rev.sleep(0.5 * (k + 1))
    return False
```

### 📌 `_lad_px` — lines 15475–15480 (6 سطر)
```python
def _lad_px(exchange, sym: str, w: Dict, off_sigma: float) -> float:
    tgt = float(w["target"])
    sp = float(w.get("sigma_bar", 0.01)) * tgt
    if w["action"] == "BUY":
        return _rev_snap_price(exchange, sym, tgt - off_sigma * sp, "buy")
    return _rev_snap_price(exchange, sym, tgt + off_sigma * sp, "sell")
```

### 📌 `_lad_sl_tp` — lines 15652–15665 (14 سطر)
```python
def _lad_sl_tp(w: Dict, entry_px: float):
    osd = float(w["orig_sl_dist"])
    otd = float(w["orig_tp_dist"])
    if osd <= 1e-12:
        osd = entry_px * 0.015
        otd = osd * float(getattr(CFG, "TP_MULT", 2.0))
    mx = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
    if osd > entry_px * mx:
        rr = otd / max(osd, 1e-12)
        osd = entry_px * mx
        otd = osd * rr
    if w["action"] == "BUY":
        return entry_px - osd, entry_px + otd, osd
    return entry_px + osd, entry_px - otd, osd
```

### 📌 `_lad_stats` — lines 15846–15872 (27 سطر)
```python
def _lad_stats(w: Dict, reason: str) -> None:
    try:
        f, c = _lad_totals(w)
        qt = float(w.get("qty_eff") or w["qty"])
        vwap = (c / f) if f > 0 else 0.0
        tgt = float(w["target"])
        sign = 1.0 if w["action"] == "BUY" else -1.0
        slip = ((vwap - tgt) / tgt * 1e4 * sign) if f > 0 else 0.0
        lv = ";".join(f"{r['name']}:{r.get('filled', 0.0):.6g}/{r['qty']:.6g}"
                      for r in _lad_all_recs(w))
        path = f"ladder_stats_{CFG.mode}.csv"
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as fh:
            wr = _csv3.writer(fh)
            if new:
                wr.writerow(["iso", "sym", "action", "target", "ref_px",
                             "qty_target", "filled", "fill_ratio", "vwap",
                             "slip_bps_vs_target(+worse)", "levels", "qp_pos",
                             "duration_s", "reason"])
            wr.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), w["sym"],
                         w["action"], tgt, w.get("ref_px"), qt, f,
                         round(f / max(qt, 1e-12), 4), vwap, round(slip, 2),
                         lv, bool(w.get("qp_pos")),
                         round(time.time() - float(w.get("ladder_t0", time.time())), 1),
                         reason])
    except Exception as e:
        log.debug(f"[Ladder] stats write failed: {e}")
```

### 📌 `_lad_sync_position` — lines 15748–15786 (39 سطر)
```python
def _lad_sync_position(exchange, sym: str, w: Dict, open_pos_live: Dict,
                       assets, filled: float, cost: float) -> str:
    """Create the position at the first fill, grow it on later fills.
    Returns noop | created | grown | flattened."""
    sq = float(w.get("pos_synced_qty", 0.0))
    sc = float(w.get("pos_synced_cost", 0.0))
    dq = filled - sq
    if dq <= 1e-12:
        return "noop"
    dc = cost - sc
    pos = open_pos_live.get(sym)
    grown = pos is not None
    if pos is None:
        pos = _lad_new_pos(sym, w, dc / dq, dq, assets)
        open_pos_live[sym] = pos
    else:
        nq = float(pos["qty"]) + dq
        ne = (float(pos["entry"]) * float(pos["qty"]) + dc) / nq
        sl, tp, osd = _lad_sl_tp(w, ne)
        pos.update(qty=nq, entry=ne, sl=sl, tp1=tp, sl_dist_initial=float(osd),
                   liq_price_estimated=_lad_liq(w, ne))
        pos["fill_ratio"] = nq / max(float(w.get("qty_eff") or w["qty"]), 1e-9)
    w["pos_synced_qty"], w["pos_synced_cost"] = filled, cost
    if _REV_STATE_FILE:
        _lv_save_state(_REV_STATE_FILE, open_pos_live)
    if not _lad_protect(exchange, sym, pos, grown):
        if _revc("REV_FLATTEN_ON_UNPROTECTED", True):
            log.error(f"[Ladder] {sym} UNPROTECTED — emergency flatten")
            if _lad_flatten(exchange, sym, w["action"], float(pos["qty"])):
                open_pos_live.pop(sym, None)
                if _REV_STATE_FILE:
                    _lv_save_state(_REV_STATE_FILE, open_pos_live)
                return "flattened"
    elif _REV_STATE_FILE:
        _lv_save_state(_REV_STATE_FILE, open_pos_live)
    log.info(f"[Ladder] {sym} position {'grown' if grown else 'created'}: "
             f"qty={pos['qty']:.6f} entry={pos['entry']:.6f} "
             f"sl={pos['sl']:.6f} tp={pos['tp1']:.6f}")
    return "grown" if grown else "created"
```

### 📌 `_lad_totals` — lines 15498–15504 (7 سطر)
```python
def _lad_totals(w: Dict):
    q = c = 0.0
    for r in _lad_all_recs(w):
        f = float(r.get("filled") or 0.0)
        q += f
        c += f * float(r.get("avg") or 0.0)
    return q, c
```

### 📌 `_register_reversal_watcher` — lines 14315–14435 (121 سطر)
```python
def _register_reversal_watcher(exchange, sym: str, side: str,
                                qty: float, sig, leverage: int,
                                ad=None, cap_ref=None) -> bool:
    if sym in _REVERSAL_WATCHERS:
        return False
    if sym in _PENDING_ORDERS:
        return False
    if len(_REVERSAL_WATCHERS) >= int(_revc("REV_WATCHER_CAP", 50)):
        return False

    ts = pd.Timestamp(sig.timestamp)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    sig_epoch = float(ts.timestamp())            # bar OPEN time
    key = f"{sym}|{int(sig_epoch)}|{sig.action}"
    if key in _REV_LEDGER:
        return False                             # once per signal

    sub_tf, sub_sec = _rev_sub_info()
    main_sec = _rev_main_sec()
    tw = int(getattr(CFG, "REVERSAL_TOUCH_SUBBARS", 20))
    bw = int(getattr(CFG, "REVERSAL_BOUNCE_SUBBARS", 4))
    lat = int(_revc("REV_ENTRY_LATENCY_SUBBARS", 0))
    start_ts = sig_epoch + main_sec              # first sub-bar of bar N+1
    expire_ts = start_ts + (tw + bw + lat + 2) * sub_sec

    _REV_LEDGER[key] = _t_rev.time()
    _rev_ledger_save()
    if _t_rev.time() >= expire_ts:
        log.debug(f"[LiveRev] {sym} signal already outside window — skip")
        return False

    sigma_bar = 0.01
    friction_v, accel_v, gauge_v = 0.2, 0.05, 0.1
    if ad is not None:
        try:
            fi = int(sig.feat_idx)
            if 0 <= fi < len(ad.E_therm):
                _s = float(ad.E_therm[fi])
                if np.isfinite(_s) and _s > 1e-9:
                    sigma_bar = _s
            if 0 <= fi < len(ad.friction):
                friction_v = float(ad.friction[fi])
            if 0 <= fi < len(ad.geodesic_accel):
                accel_v = float(ad.geodesic_accel[fi])
            if 0 <= fi < len(ad.gauge_force):
                gauge_v = float(ad.gauge_force[fi])
        except Exception:
            pass

    try:
        _mmr = float(_get_mmr_for_symbol(exchange, sym))
    except Exception:
        _mmr = float(getattr(CFG, "LIQ_FALLBACK_MMR", 0.02))

    try:
        _bt_target = float(_backtest_entry_target(sig, ad))
    except Exception:
        _bt_target = float(sig.price)

    # ════════════════════════════════════════════════════════════════
    # [IMMEDIATE TOUCH BYPASS] فكرة المستخدم العبقرية
    # إذا كان السعر الحالي قد تجاوز الهدف بالفعل، انتقل فوراً لانتظار الارتداد
    # ════════════════════════════════════════════════════════════════
    current_px = float(ad.closes[-1]) if ad is not None else float(sig.price)
    already_touched = False
    
    if sig.action == "BUY" and current_px <= _bt_target:
        already_touched = True
    elif sig.action == "SELL" and current_px >= _bt_target:
        already_touched = True
        
    initial_status = "WAITING_BOUNCE" if already_touched else "WAITING_TOUCH"
    initial_touch_k = 0 if already_touched else -1

    w = {
        "sym": sym,
        "side": side,
        "side_ccxt": "buy" if sig.action == "BUY" else "sell",
        "action": sig.action,
        "target": _bt_target,
        "qty": float(qty),
        "cap_ref": (float(cap_ref) if cap_ref else None),
        "leverage": int(leverage),
        "mmr": _mmr,
        "dyn_risk": float(sig.dynamic_risk),
        "T_info": float(sig.T_info_val),
        "score": float(getattr(sig, "score", 0.0) or 0.0),
        "sigma_bar": float(sigma_bar),
        "friction": float(friction_v),
        "accel": float(accel_v),
        "gauge_force": float(gauge_v),
        "close_idx": int(sig.close_idx),
        "sig_epoch": sig_epoch,
        "start_ts": start_ts,
        "expire_ts": expire_ts,
        "created_at": _t_rev.time(),
        "status": initial_status,
        "touch_k": initial_touch_k,
        "last_scan_ts": start_ts - 1.0,
        "next_fetch_ts": start_ts + sub_sec + 2.0,
        "sig_ts": str(sig.timestamp),
        "sig_price": float(sig.price),
        "sig_sl": float(sig.sl),
        "sig_tp1": float(sig.tp1),
        "orig_sl_dist": float(abs(sig.price - sig.sl)),
        "orig_tp_dist": float(abs(sig.tp1 - sig.price)),
        "two_bar_count": 0,
        "prev_close": None,
        "banked_qty": 0.0, "banked_cost": 0.0,
        "cur_filled": 0.0, "cur_avg": 0.0,
        "attempt": 0, "rejects": 0, "err": 0,
        "cid": None, "order_id": None, "cid_sent": False,
        "order_px": 0.0, "cancel_req": False,
    }
    _REVERSAL_WATCHERS[sym] = w
    log.info(f"[LiveRev] {sig.action} {sym} registered — "
             f"target={_bt_target:.6f} (curr={current_px:.6f}) "
             f"status={initial_status} "
             f"sl={sig.sl:.6f} tp={sig.tp1:.6f}")
    return True
```

### 📌 `_rev_advance_filling` — lines 14557–14709 (153 سطر)
```python
def _rev_advance_filling(exchange, sym: str, w: Dict, open_pos_live: Dict,
                         assets, now: float) -> None:
    action = w["action"]
    side = w["side_ccxt"]
    qty_target = float(w.get("qty_eff") or w["qty"])
    ref_px = float(w.get("ref_px") or w["target"])
    sigma = float(w.get("sigma_bar", 0.01))
    chase = float(_revc("REV_MAX_CHASE_KAPPA", 0.15)) * sigma * ref_px

    if not w.get("setup_done"):
        try:
            ensure_symbol_setup(exchange, sym, int(w["leverage"]),
                                margin_mode="isolated")
            w["setup_done"] = True
        except Exception as e:
            w["setup_fail"] = int(w.get("setup_fail", 0)) + 1
            log.warning(f"[LiveRev] setup {sym}: {e}")
            if w["setup_fail"] >= 3:
                _rev_expire(w, "setup_failed")
            return

    if getattr(CFG, "REV_LADDER_ENABLED", False):        # [REV-FIX v3]
        return _rev_ladder_advance(exchange, sym, w, open_pos_live, assets, now)

    # ── 1) an entry order may exist (possibly after a restart) ──
    if w.get("cid"):
        try:
            o = _rev_find_order(exchange, sym, w["cid"], w.get("order_id"))
        except Exception as e:
            log.debug(f"[LiveRev] {sym} order lookup failed: {e}")
            return                      # unsure -> never place a new one
        if o is None:
            _rev_clear_order(w)         # create never reached the exchange
        else:
            w["order_id"] = str(o.get("id") or w.get("order_id") or "")
            _rev_cur_from_order(w, o)
            if str(o.get("status") or "open") in _REV_TERMINAL:
                _rev_bank(w)
                _rev_clear_order(w)
            else:
                if now >= float(w["fill_deadline"]) or w.get("cancel_req"):
                    if not _rev_cancel_and_confirm(exchange, sym, w):
                        return
                elif now - float(w.get("last_reprice", 0.0)) >= float(
                        _revc("REV_REPRICE_S", 5.0)):
                    w["last_reprice"] = now
                    try:
                        px = _rev_best_px(exchange, sym, action)
                    except Exception as e:
                        log.debug(f"[LiveRev] {sym} book error: {e}")
                        return
                    if px is None:
                        return
                    if _rev_beyond_chase(action, px, ref_px, chase):
                        w["stop_reason"] = "chase_cap"
                        if not _rev_cancel_and_confirm(exchange, sym, w):
                            w["cancel_req"] = True
                            return
                    elif abs(_rev_marketable_px(exchange, sym, w, action, side, px, ref_px)
                             - float(w.get("order_px", 0.0))) > 0.0:   # [REV-FIX v3]
                        if not _rev_cancel_and_confirm(exchange, sym, w):
                            w["cancel_req"] = True
                            return
                    else:
                        return
                else:
                    return
    if w.get("cid"):
        return                          # cancel not yet confirmed

    # ── 2) decide: finish or (re)place ──
    banked = float(w.get("banked_qty", 0.0))
    remaining = qty_target - banked
    min_notional = float(getattr(CFG, "MIN_NOTIONAL", 5.0))
    stop = w.get("stop_reason")
    if (stop or now >= float(w["fill_deadline"])
            or remaining * ref_px < min_notional
            or int(w.get("rejects", 0)) >= int(_revc("REV_MAX_REJECTS", 30))):
        _rev_finish(exchange, sym, w, open_pos_live, assets,
                    stop or ("filled" if remaining * ref_px < min_notional
                             else "fill_timeout"))
        return
    try:
        px = _rev_best_px(exchange, sym, action)
    except Exception as e:
        log.debug(f"[LiveRev] {sym} book error: {e}")
        return
    if px is None:
        return
    if _rev_beyond_chase(action, px, ref_px, chase):
        w["stop_reason"] = "chase_cap"
        return
    q = _snap_qty(exchange, sym, remaining)
    if q <= 0:
        _rev_finish(exchange, sym, w, open_pos_live, assets, "qty_below_min")
        return
    if not _rate_can_place():
        return
        
    w["attempt"] = int(w.get("attempt", 0)) + 1
    cid = _rev_cid(sym, float(w["sig_epoch"]), int(w["attempt"]))
    w["cid"] = cid
    w["cid_sent"] = True
    
    # ════════════════════════════════════════════════════════════════
    # [SMART EXECUTION v2] Marketable Limit with Dynamic Slippage Cap
    # ════════════════════════════════════════════════════════════════
    # حساب المسافة الأصلية للوقف للحفاظ على التناسب
    orig_sl_dist = float(w.get("orig_sl_dist", ref_px * 0.015))
    
    # أقصى انزلاق مسموح هو 15% من مسافة الـ Stop Loss 
    # (بحيث لا يتشوه الـ Risk:Reward الخاص بك)
    max_slip_allowed = orig_sl_dist * 0.15 
    
    if action == "BUY":
        # في الشراء: نرسل أمر ليمت أعلى من أفضل سعر بيع (Best Ask) بقليل
        marketable_px = px + max_slip_allowed
    else:
        # في البيع: نرسل أمر ليمت أقل من أفضل سعر شراء (Best Bid) بقليل
        marketable_px = px - max_slip_allowed
        
    # تقريب السعر ليتوافق مع شروط البورصة
    marketable_px = _rev_snap_price(exchange, sym, marketable_px, side)
    
    w["order_px"] = marketable_px
    w["last_reprice"] = now
    save_reversal_watchers()            # persist BEFORE the order exists
    
    try:
        # إرسال الأمر بدون GTX (ليتمكن من اقتحام السبريد كأمر Market)
        # ولكن بحد أقصى للسعر يمنع الانزلاق الكارثي
        o = _rev_api(exchange.create_order, sym, "limit", side, q, marketable_px,
                     params={"clientOrderId": cid})
        w["order_id"] = str(o.get("id") or "")
        w["cid_sent"] = False
        log.info(f"[LiveRev-Smart] {sym} Marketable Limit {side} {q} @ {marketable_px:.6f} (Current Ask/Bid: {px:.6f})")
    except Exception as e:
        msg = str(e)
        if ("-5022" in msg or "Post Only" in msg or "post only" in msg
                or "immediately match" in msg):
            w["rejects"] = int(w.get("rejects", 0)) + 1
            _rev_clear_order(w)
            log.info(f"[LiveRev] {sym} GTX rejected (retry): {msg[:120]}")
        elif any(c in msg for c in ("-2019", "-4164", "-1111", "-4003",
                                    "-2027", "-4028")):
            _rev_clear_order(w)
            log.warning(f"[LiveRev] {sym} order refused: {msg[:160]}")
            _rev_finish(exchange, sym, w, open_pos_live, assets,
                        "order_refused")
        else:
            # ambiguous (timeout etc.): keep cid, resolve by lookup next cycle
            log.warning(f"[LiveRev] {sym} create_order ambiguous: {msg[:160]}")
    save_reversal_watchers()
```

### 📌 `_rev_atomic_dump` — lines 14015–14016 (2 سطر)
```python
def _rev_atomic_dump(path: str, obj) -> None:
    _json_write_if_changed(path, obj, indent=1)   # [REV-FIX v2]
```

### 📌 `_rev_bank` — lines 14209–14216 (8 سطر)
```python
def _rev_bank(w: Dict) -> None:
    f = float(w.get("cur_filled") or 0.0)
    a = float(w.get("cur_avg") or 0.0)
    if f > 0 and a > 0:
        w["banked_qty"] = float(w.get("banked_qty", 0.0)) + f
        w["banked_cost"] = float(w.get("banked_cost", 0.0)) + f * a
    w["cur_filled"] = 0.0
    w["cur_avg"] = 0.0
```

### 📌 `_rev_best_px` — lines 14255–14265 (11 سطر)
```python
def _rev_best_px(exchange, sym: str, action: str):
    ob = _rev_api(exchange.fetch_order_book, sym, 5, weight=2.0)
    bids = ob.get("bids") or []
    asks = ob.get("asks") or []
    if action == "BUY":
        if not bids:
            return None
        return _rev_snap_price(exchange, sym, float(bids[0][0]), "buy")
    if not asks:
        return None
    return _rev_snap_price(exchange, sym, float(asks[0][0]), "sell")
```

### 📌 `_rev_beyond_chase` — lines 14268–14270 (3 سطر)
```python
def _rev_beyond_chase(action: str, px: float, ref_px: float,
                      chase: float) -> bool:
    return (px > ref_px + chase) if action == "BUY" else (px < ref_px - chase)
```

### 📌 `_rev_cancel_and_confirm` — lines 14227–14252 (26 سطر)
```python
def _rev_cancel_and_confirm(exchange, sym: str, w: Dict) -> bool:
    """Cancel the live entry order; True only once it is TERMINAL."""
    try:
        if w.get("order_id"):
            _rev_api(exchange.cancel_order, w["order_id"], sym)
        else:
            _rev_api(exchange.cancel_order, None, sym,
                     params={"origClientOrderId": w["cid"]})
    except Exception as e:
        if not _rev_is_not_found(e):
            log.debug(f"[LiveRev] {sym} cancel error: {e}")
    try:
        o = _rev_find_order(exchange, sym, w["cid"], w.get("order_id"))
    except Exception as e:
        log.debug(f"[LiveRev] {sym} cancel verify error: {e}")
        return False
    if o is None:
        _rev_bank(w)
        _rev_clear_order(w)
        return True
    _rev_cur_from_order(w, o)
    if str(o.get("status") or "open") in _REV_TERMINAL:
        _rev_bank(w)
        _rev_clear_order(w)
        return True
    return False
```

### 📌 `_rev_cid` — lines 14157–14159 (3 سطر)
```python
def _rev_cid(sym: str, sig_epoch: float, attempt: int) -> str:
    h = _hl_rev.md5(sym.encode()).hexdigest()[:8]
    return f"rev{int(sig_epoch)}x{h}x{int(attempt)}"[:36]
```

### 📌 `_rev_clear_order` — lines 14219–14224 (6 سطر)
```python
def _rev_clear_order(w: Dict) -> None:
    w["cid"] = None
    w["order_id"] = None
    w["cid_sent"] = False
    w["order_px"] = 0.0
    w["cancel_req"] = False
```

### 📌 `_rev_cur_from_order` — lines 14196–14206 (11 سطر)
```python
def _rev_cur_from_order(w: Dict, o: Dict) -> None:
    f = float(o.get("filled") or 0.0)
    a = o.get("average")
    try:
        a = float(a) if a else 0.0
    except Exception:
        a = 0.0
    if a <= 0:
        a = float(o.get("price") or w.get("order_px") or w.get("target") or 0.0)
    w["cur_filled"] = f
    w["cur_avg"] = a
```

### 📌 `_rev_exch_position` — lines 14162–14167 (6 سطر)
```python
def _rev_exch_position(exchange, sym: str):
    """-> dict {'qty','entry','side'} | {} (flat) | None (API failure)."""
    res = _lv_fetch_positions(exchange, [sym])
    if res is None:
        return None
    return res.get(sym.split(":")[0]) or {}
```

### 📌 `_rev_expire` — lines 14273–14277 (5 سطر)
```python
def _rev_expire(w: Dict, reason: str) -> None:
    if w.get("status") not in ("EXPIRED", "FILLED"):
        w["status"] = "EXPIRED"
        w["reason"] = str(reason)
        log.info(f"[LiveRev] {w.get('sym')} EXPIRED ({reason})")
```

### 📌 `_rev_finalize` — lines 14721–14868 (148 سطر)
```python
def _rev_finalize(exchange, sym: str, w: Dict, open_pos_live: Dict, assets,
                  reason: str) -> None:
    action = w["action"]
    filled = float(w.get("banked_qty", 0.0))
    cost = float(w.get("banked_cost", 0.0))
    entry_px = (cost / filled) if (filled > 0 and cost > 0) else 0.0

    ex = None
    try:
        ex = _rev_exch_position(exchange, sym)
    except Exception:
        ex = None
    if ex is not None:                      # exchange is the source of truth
        if not ex or ex.get("side") != action:
            if filled > 0:
                log.warning(f"[LiveRev] {sym} fills={filled} but exchange "
                            f"shows no {action} position")
            _rev_expire(w, f"{reason}:no_position")
            return
        ex_qty = float(ex["qty"])
        if filled <= 0 or abs(ex_qty - filled) > max(1e-9, 0.02 * filled):
            log.warning(f"[LiveRev] {sym} qty mismatch local={filled} "
                        f"exchange={ex_qty} — adopting exchange")
            filled = ex_qty
            if float(ex.get("entry") or 0.0) > 0:
                entry_px = float(ex["entry"])
    if filled <= 0 or entry_px <= 0:
        _rev_expire(w, f"{reason}:no_fill")
        return

    min_ratio = float(_revc("REV_MIN_FILL_RATIO", 0.0))
    qty_target = float(w.get("qty_eff") or w["qty"])
    if min_ratio > 0 and filled / max(qty_target, 1e-12) < min_ratio:
        try:
            _rev_api(exchange.create_order, sym, "market",
                     "sell" if action == "BUY" else "buy", filled, None,
                     params={"reduceOnly": True})
            log.warning(f"[LiveRev] {sym} fill ratio below "
                        f"{min_ratio:.2f} — flattened")
            _rev_expire(w, f"{reason}:fill_ratio_flatten")
            return
        except Exception as e:
            log.error(f"[LiveRev] {sym} flatten failed: {e}")

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

    _sb = float(w.get("sigma_bar", 0.01))
    _td = float(np.clip(CFG.TRAIL_KAPPA * _sb,
                        CFG.TRAIL_MIN_FRAC, CFG.TRAIL_MAX_FRAC))
    _ta = float(np.clip(CFG.TRAIL_ACT_KAPPA * _sb,
                        CFG.TRAIL_ACT_MIN_FRAC, CFG.TRAIL_ACT_MAX_FRAC))
    if _ta <= _td:
        _ta = _td * 1.2

    _lev = int(w["leverage"])
    _mmr = float(w.get("mmr", getattr(CFG, "LIQ_FALLBACK_MMR", 0.02)))
    _liq = None
    if getattr(CFG, "LIQ_ENABLED", True):
        try:
            _liq = compute_liquidation_price(entry_px, action, _lev, _mmr)
        except Exception:
            _liq = None

    _ad = assets.get(sym) if isinstance(assets, dict) else None
    _ci_now = (len(_ad.closes) - 2) if _ad is not None else 0
    _entry_ci = int(max(int(w.get("close_idx", 0)), _ci_now))

    open_pos_live[sym] = {
        "action": action,
        "entry": entry_px,
        "qty": filled,
        "sl": new_sl,
        "tp1": new_tp,
        "T_info": float(w.get("T_info", 0.0)),
        "dyn_risk": float(w.get("dyn_risk", 0.01)),
        "entry_ts": _t_rev.time(),
        "fill_ratio": filled / max(qty_target, 1e-9),
        "leverage": _lev,
        "trail_dist_frac": _td,
        "trail_activate_frac": _ta,
        "liq_price_estimated": _liq,
        "mmr": _mmr,
        "sl_dist_initial": float(abs(entry_px - new_sl)),
        "_entry_ci": _entry_ci,
        "_trail_bars_held": 0,
        "_trail_peak_R": 0.0,
        "_trail_last_update_ts": 0.0,
        "_sym": sym,
        "_orig_score": float(w.get("score", 0.0)),
        "stage": "REVERSAL",
    }
    if _REV_STATE_FILE:                      # persist IMMEDIATELY
        _lv_save_state(_REV_STATE_FILE, open_pos_live)

    if getattr(CFG, "PROTECTIVE_ORDERS_ENABLED", True):
        ok = False
        retries = int(_revc("REV_PROTECT_RETRIES", 3))
        for k in range(max(1, retries)):
            try:
                ok = bool(_place_protective_orders(exchange, sym,
                                                   open_pos_live[sym]))
            except Exception as e:
                log.warning(f"[LiveRev] prot {sym} try{k + 1}: {e}")
                ok = False
            if ok:
                break
            _t_rev.sleep(0.5 * (k + 1))
        if ok:
            open_pos_live[sym]["_prot_last_sl"] = float(new_sl)
            open_pos_live[sym]["_prot_last_tp"] = float(new_tp)
        elif _revc("REV_FLATTEN_ON_UNPROTECTED", True):
            log.error(f"[LiveRev] {sym} UNPROTECTED after {retries} tries "
                      f"— emergency flatten")
            try:
                _rev_api(exchange.create_order, sym, "market",
                         "sell" if action == "BUY" else "buy",
                         _snap_qty(exchange, sym, filled) or filled, None,
                         params={"reduceOnly": True})
                open_pos_live.pop(sym, None)
                if _REV_STATE_FILE:
                    _lv_save_state(_REV_STATE_FILE, open_pos_live)
                _rev_expire(w, "unprotected_flatten")
                return
            except Exception as e:
                log.error(f"[LiveRev] {sym} emergency flatten FAILED: {e}")
        if _REV_STATE_FILE:
            _lv_save_state(_REV_STATE_FILE, open_pos_live)

    log.info(f"✅ [LiveRev] {action} {sym} @ {entry_px:.6f} "
             f"qty={filled:.6f}/{qty_target:.6f} sl={new_sl:.6f} "
             f"tp={new_tp:.6f} ({reason})")
    w["status"] = "FILLED"
    w["entry"] = entry_px
```

### 📌 `_rev_find_order` — lines 14170–14193 (24 سطر)
```python
def _rev_find_order(exchange, sym: str, cid: str, order_id=None):
    """Order dict | None (does not exist). Raises on transient API errors."""
    if order_id:
        try:
            return _rev_api(exchange.fetch_order, order_id, sym)
        except Exception as e:
            if not _rev_is_not_found(e):
                raise
    try:
        for o in _rev_api(exchange.fetch_open_orders, sym) or []:
            oc = str(o.get("clientOrderId")
                     or (o.get("info") or {}).get("clientOrderId") or "")
            if oc == cid:
                return o
    except Exception as e:
        if not _rev_is_not_found(e):
            raise
    try:
        return _rev_api(exchange.fetch_order, None, sym,
                        params={"origClientOrderId": cid})
    except Exception as e:
        if _rev_is_not_found(e):
            return None
        raise
```

### 📌 `_rev_handle_ready` — lines 14517–14553 (37 سطر)
```python
def _rev_handle_ready(exchange, sym: str, w: Dict, open_pos_live: Dict,
                      now: float, sub_sec: int, cap_now, corr_cache) -> None:
    max_age = float(_revc("REV_MAX_CONFIRM_AGE_SUBBARS", 2)) * sub_sec
    if now - float(w.get("confirm_close_ts", 0.0)) > max_age:
        _rev_expire(w, "stale_confirm")
        return
    if sym in open_pos_live and not w.get("qp_pos"):     # [REV-FIX v3] QP-owned position is ours
        _rev_expire(w, "pos_open")
        return
    n_infl = _rev_inflight_other(sym, open_pos_live)
    if (len(open_pos_live) - (1 if w.get("qp_pos") else 0) + n_infl
            >= int(CFG.MAX_CONCURRENT_ASSETS)):
        _rev_expire(w, "slots_full")
        return
    if corr_cache is not None and open_pos_live:
        try:
            thr = CFG.CORRELATION_THRESHOLD * (
                (0.85 ** len(open_pos_live))
                if getattr(CFG, "LIVE_ADAPTIVE_CORR", False) else 1.0)
            if any(abs(corr_cache.get((sym, s), 0.0)) > thr
                   for s in open_pos_live):
                _rev_expire(w, "corr_guard")
                return
        except Exception:
            pass
    qty = float(w["qty"])
    if (_revc("REV_RESIZE_AT_FILL", True) and cap_now
            and w.get("cap_ref")):
        ratio = float(np.clip(float(cap_now) / float(w["cap_ref"]),
                              0.25, 1.25))
        qty *= ratio
    w["qty_eff"] = qty
    w["status"] = "FILLING"
    w["fill_started"] = now
    w["fill_deadline"] = now + float(_revc("REV_FILL_MAX_WAIT_S", 90.0))
    w["last_reprice"] = 0.0
    log.info(f"[LiveRev] {sym} FILLING qty={qty:.6f} ref={w['ref_px']:.6f}")
```

### 📌 `_rev_inflight_other` — lines 15518–15528 (11 سطر)
```python
def _rev_inflight_other(sym: str, open_pos_live: Dict) -> int:
    """Symbols (other than `sym`) that hold or reserve a slot WITHOUT being in
    open_pos_live yet: FILLING watchers and resting queue-priority orders."""
    n = 0
    for s2, w2 in _REVERSAL_WATCHERS.items():
        if s2 == sym or s2 in open_pos_live:
            continue
        qp = w2.get("qp")
        if w2.get("status") == "FILLING" or (qp and qp.get("status") == "open"):
            n += 1
    return n
```

### 📌 `_rev_known_cids` — lines 15507–15515 (9 سطر)
```python
def _rev_known_cids() -> set:
    s = set()
    for w in _REVERSAL_WATCHERS.values():
        if w.get("cid"):
            s.add(str(w["cid"]))
        for r in _lad_all_recs(w):
            if r.get("cid"):
                s.add(str(r["cid"]))
    return s
```

### 📌 `_rev_ladder_advance` — lines 15899–15963 (65 سطر)
```python
def _rev_ladder_advance(exchange, sym: str, w: Dict, open_pos_live: Dict,
                        assets, now: float) -> None:
    qty_target = float(w.get("qty_eff") or w["qty"])
    side = w["side_ccxt"]
    min_notional = float(getattr(CFG, "MIN_NOTIONAL", 5.0))

    if w.get("ladder") is None:                     # build once
        qp_qty = float(w["qp"]["qty"]) if w.get("qp") else 0.0
        recs: List[Dict] = []
        for i, (off, wt) in enumerate(_lad_levels()):
            q = max(qty_target * wt - (qp_qty if i == 0 else 0.0), 0.0)
            q = _snap_qty(exchange, sym, q) if q > 0 else 0.0
            px = _lad_px(exchange, sym, w, off)
            if q <= 0:
                continue
            if q * px < min_notional and recs:      # too small -> merge into prev
                recs[-1]["qty"] = _snap_qty(exchange, sym, recs[-1]["qty"] + q)
                continue
            recs.append(_lad_new_rec(f"L{i}", px, q))
        w["ladder"] = recs
        w["ladder_started"] = True
        w["ladder_t0"] = now
        w["ladder_deadline"] = now + float(_cfg3("REV_LADDER_MAX_WAIT_S", 21600.0))
        log.info(f"[Ladder] {sym} built {len(recs)} levels "
                 f"{[(r['name'], r['px'], r['qty']) for r in recs]} "
                 f"qp={qp_qty}")
        save_reversal_watchers()
        if not recs and not w.get("qp"):
            _rev_expire(w, "ladder:no_levels")
            return

    recs = w["ladder"]
    pending = [r for r in recs if r["status"] == "new"]
    if pending and _rate_can_place():
        bid, ask = _lad_book(exchange, sym)
        if bid is not None:
            for r in pending[:3]:
                _lad_place(exchange, sym, w, r, bid, ask, clamp=True)

    _lad_poll(exchange, sym, _lad_all_recs(w))

    f, c = _lad_totals(w)
    res = _lad_sync_position(exchange, sym, w, open_pos_live, assets, f, c)
    if res == "flattened":
        for r in _lad_all_recs(w):
            _lad_cancel(exchange, sym, r)
        _lad_stats(w, "unprotected_flatten")
        _rev_expire(w, "ladder:unprotected_flatten")
        return

    allrecs = _lad_all_recs(w)
    all_done = all(r["status"] == "done" for r in allrecs)
    if all_done or now >= float(w["ladder_deadline"]):
        if not all_done:
            ok = True
            for r in allrecs:
                if r["status"] in ("open", "new") and not _lad_cancel(
                        exchange, sym, r):
                    ok = False
            if not ok:
                return                       # retry next cycle
            f, c = _lad_totals(w)            # late fills while cancelling
            _lad_sync_position(exchange, sym, w, open_pos_live, assets, f, c)
        _lad_finish(exchange, sym, w, open_pos_live,
                    "complete" if all_done else "deadline")
```

### 📌 `_rev_ladder_cleanup` — lines 15966–15996 (31 سطر)
```python
def _rev_ladder_cleanup(exchange, sym: str, w: Dict,
                        open_pos_live: Dict) -> bool:
    """Called before a FILLED/EXPIRED watcher is dropped: no resting order may
    survive, and an UNCONFIRMED queue-priority fill is flattened."""
    recs = _lad_all_recs(w)
    if not recs and not w.get("qp_pos"):
        return True
    ok = True
    for r in recs:
        if r.get("status") in ("open", "new") and not _lad_cancel(exchange, sym, r):
            ok = False
    if not ok:
        w["cleanup_tries"] = int(w.get("cleanup_tries", 0)) + 1
        if w["cleanup_tries"] >= 30:
            log.error(f"[Ladder] {sym} cleanup gave up — resting order may remain")
            _send_alert("CRITICAL", f"{sym}: ladder cleanup failed, check open orders")
            return True
        return False
    if (w.get("status") == "EXPIRED" and sym in open_pos_live
            and not w.get("ladder_started")):
        pos = open_pos_live.get(sym)
        log.warning(f"[Ladder] {sym} bounce never confirmed — flattening the "
                    f"queue-priority fill ({w.get('reason')})")
        if _lad_flatten(exchange, sym, w["action"], float((pos or {}).get("qty", 0.0))):
            open_pos_live.pop(sym, None)
            if _REV_STATE_FILE:
                _lv_save_state(_REV_STATE_FILE, open_pos_live)
        else:
            w["cleanup_tries"] = int(w.get("cleanup_tries", 0)) + 1
            return w["cleanup_tries"] >= 30
    return True
```

### 📌 `_rev_ledger_purge` — lines 14062–14066 (5 سطر)
```python
def _rev_ledger_purge() -> None:
    ttl = float(_revc("REV_LEDGER_TTL_S", 172800.0))
    now = _t_rev.time()
    for k in [k for k, v in _REV_LEDGER.items() if now - v > ttl]:
        _REV_LEDGER.pop(k, None)
```

### 📌 `_rev_ledger_save` — lines 14069–14075 (7 سطر)
```python
def _rev_ledger_save() -> None:
    if not _REV_LEDGER_PATH:
        return
    try:
        _rev_atomic_dump(_REV_LEDGER_PATH, _REV_LEDGER)
    except Exception as e:
        log.warning(f"[LiveRev] ledger save failed: {e}")
```

### 📌 `_rev_main_sec` — lines 14009–14011 (3 سطر)
```python
def _rev_main_sec() -> int:
    _s = int(getattr(CFG, "TF_SECONDS", 0) or 0)
    return _s if _s > 0 else int(_sub_tf_seconds(CFG.timeframe))
```

### 📌 `_rev_marketable_px` — lines 15454–15462 (9 سطر)
```python
def _rev_marketable_px(exchange, sym: str, w: Dict, action: str, side: str,
                       px: float, ref_px: float) -> float:
    """Price the 'Smart Execution' marketable limit uses (best bid/ask +- 15%
    of the original SL distance) - the reprice check must compare THIS value,
    not the raw best bid/ask (it used to cancel/replace a resting order every
    reprice tick)."""
    sl_d = float(w.get("orig_sl_dist", ref_px * 0.015))
    m = (px + sl_d * 0.15) if action == "BUY" else (px - sl_d * 0.15)
    return _rev_snap_price(exchange, sym, m, side)
```

### 📌 `_rev_qp_step` — lines 15790–15842 (53 سطر)
```python
def _rev_qp_step(exchange, sym: str, w: Dict, open_pos_live: Dict, assets,
                 now: float) -> None:
    if not _cfg3("REV_LADDER_ENABLED", False):
        return
    qp = w.get("qp")
    if qp is None:
        if w.get("qp_tried") or w.get("status") != "WAITING_TOUCH":
            return
        w["qp_tried"] = True
        pct = float(_cfg3("REV_LADDER_QP_PCT", 0.05))
        if pct <= 0:
            return
        if len(open_pos_live) + _rev_inflight_other(sym, open_pos_live) \
                >= int(CFG.MAX_CONCURRENT_ASSETS):
            log.debug(f"[Ladder] {sym} no free slot for queue-priority order")
            return
        if not _rate_can_place():
            w["qp_tried"] = False
            return
        bid, ask = _lad_book(exchange, sym)
        if bid is None:
            w["qp_tried"] = False
            return
        tgt = float(w["target"])
        side = w["side_ccxt"]
        if (side == "buy" and tgt >= ask) or (side == "sell" and tgt <= bid):
            log.debug(f"[Ladder] {sym} target not resting-side of the book "
                      f"— no queue-priority order")
            return
        q = _snap_qty(exchange, sym, float(w["qty"]) * pct)
        if q <= 0:
            return
        rec = _lad_new_rec("Q", _rev_snap_price(exchange, sym, tgt, side), q)
        w["qp"] = rec
        if _lad_place(exchange, sym, w, rec, bid, ask, clamp=False) in (
                "reject", "fatal"):
            w["qp"] = None
        return
    if qp.get("status") != "open":
        return
    if now - float(w.get("qp_last_poll", 0.0)) < float(
            _cfg3("REV_LADDER_POLL_S", 10.0)):
        return
    w["qp_last_poll"] = now
    _lad_poll(exchange, sym, [qp])
    f, c = _lad_totals(w)
    if f > 0:
        res = _lad_sync_position(exchange, sym, w, open_pos_live, assets, f, c)
        if res in ("created", "grown"):
            w["qp_pos"] = True
        elif res == "flattened":
            w["qp_pos"] = False
            _rev_expire(w, "qp_unprotected")
```

### 📌 `_rev_scan` — lines 14439–14513 (75 سطر)
```python
def _rev_scan(exchange, sym: str, w: Dict, sub_tf: str, sub_sec: int,
              now: float) -> None:
    tw = int(getattr(CFG, "REVERSAL_TOUCH_SUBBARS", 20))
    bw = int(getattr(CFG, "REVERSAL_BOUNCE_SUBBARS", 4))
    start_ts = float(w["start_ts"])
    last = float(w["last_scan_ts"])
    need = int((now - last) / sub_sec) + 3
    limit = int(min(max(need, 5), 300))
    raw = _rev_api(exchange.fetch_ohlcv, sym, sub_tf,
                   int((last + 1.0) * 1000), limit,
                   weight=(1.0 if limit < 100 else 2.0))
    bars = {}
    for r in raw or []:
        ts = float(r[0]) / 1000.0
        if ts <= last or ts + sub_sec > now - 1.0:
            continue                       # already seen / still forming
        bars[ts] = (float(r[2]), float(r[3]), float(r[4]))   # H, L, C
    action = w["action"]
    target = float(w["target"])
    for ts in sorted(bars):
        h, l, c = bars[ts]
        k = int(round((ts - start_ts) / sub_sec))
        if k < 0:
            w["last_scan_ts"] = ts
            continue
        st = w["status"]
        if st == "WAITING_TOUCH":
            if k >= tw:
                _rev_expire(w, "touch_window")
                w["last_scan_ts"] = ts
                break
            if np.isfinite(h) and np.isfinite(l):
                if ((action == "BUY" and l <= target)
                        or (action == "SELL" and h >= target)):
                    w["status"] = "WAITING_BOUNCE"
                    w["touch_k"] = k
                    log.info(f"[LiveRev] {sym} TOUCH k={k} "
                             f"@ {pd.Timestamp(ts, unit='s', tz='UTC')}")
        # ── BOUNCE & FAST-FAIL ──
        elif st == "WAITING_BOUNCE":
            # 1. صمام الأمان السعري (Fast-Fail) - فكرتك العبقرية
            # إذا ابتعد السعر عن الهدف في الاتجاه المعاكس بمقدار 1σ، لا تنتظر الزمن!
            sigma_bar = float(w.get("sigma_bar", 0.01))
            target_px = float(w["target"])
            escape_dist = sigma_bar * target_px * 1.0 # معامل k=1.0 كما ناقشنا
            
            is_broken = ((action == "BUY" and c < target_px - escape_dist) or
                         (action == "SELL" and c > target_px + escape_dist))
            
#            if is_broken:
#                _rev_expire(w, "price_break_1sigma")
#                w["last_scan_ts"] = ts
#                break
            
            # 2. مؤقت الزمن (Backstop)
            if k > int(w["touch_k"]) + bw:
                _rev_expire(w, "bounce_timeout")
                w["last_scan_ts"] = ts
                break
                
            # 3. التأكيد (Bounce Confirm)
            if np.isfinite(c) and _bar_confirms_bounce(w, c):
                w["status"] = "READY_TO_FILL"
                w["confirm_k"] = k
                w["ref_px"] = float(c)
                w["confirm_close_ts"] = ts + sub_sec
                w["prev_close"] = c
                w["last_scan_ts"] = ts
                log.info(f"[LiveRev] {sym} BOUNCE confirmed k={k} close={c:.6f}")
                break
        w["prev_close"] = c
        w["last_scan_ts"] = ts
    if w["status"] in ("WAITING_TOUCH", "WAITING_BOUNCE"):
        nb_open = (int(float(w["last_scan_ts"]) // sub_sec) + 1) * sub_sec
        w["next_fetch_ts"] = nb_open + sub_sec + 2.0
```

### 📌 `_rev_snap_price` — lines 14127–14138 (12 سطر)
```python
def _rev_snap_price(exchange, sym: str, px: float, side: str) -> float:
    """Directional tick snap: BUY floors, SELL ceils (never crosses book)."""
    tick = _rev_tick(exchange, sym)
    if tick and tick > 0:
        d = _Dec_rev(str(px))
        t = _Dec_rev(str(tick))
        mode = _RF_rev if side == "buy" else _RC_rev
        return float((d / t).to_integral_value(rounding=mode) * t)
    try:
        return float(exchange.price_to_precision(sym, px))
    except Exception:
        return float(px)
```

### 📌 `_rev_startup_recover` — lines 14872–14930 (59 سطر)
```python
def _rev_startup_recover(exchange, open_pos_live: Dict) -> None:
    now = _t_rev.time()
    dropped = 0
    for sym in list(_REVERSAL_WATCHERS.keys()):
        w = _REVERSAL_WATCHERS[sym]
        st = w.get("status")
        legacy = "start_ts" not in w
        if legacy or st in ("FILLED", "EXPIRED"):
            _REVERSAL_WATCHERS.pop(sym, None)
            dropped += 1
            continue
        if st in ("WAITING_TOUCH", "WAITING_BOUNCE") \
                and now > float(w.get("expire_ts", 0.0)):
            _REVERSAL_WATCHERS.pop(sym, None)
            dropped += 1
            continue
        if st == "FILLING" and sym in open_pos_live and not w.get("ladder"):
            # crash between position persist and watcher save
            try:
                if w.get("cid"):
                    _rev_cancel_and_confirm(exchange, sym, w)
            except Exception:
                pass
            _REVERSAL_WATCHERS.pop(sym, None)
            dropped += 1
    # orphan 'rev*' entry orders with no owning watcher
    _opt = getattr(exchange, "options", None)
    _old_warn = None
    try:
        if isinstance(_opt, dict):
            _old_warn = _opt.get("warnOnFetchOpenOrdersWithoutSymbol")
            _opt["warnOnFetchOpenOrdersWithoutSymbol"] = False
        known = _rev_known_cids()      # [REV-FIX v3] includes ladder / queue-priority cids
        n_orph = 0
        for o in _rev_api(exchange.fetch_open_orders, weight=40.0) or []:
            cid = str(o.get("clientOrderId")
                      or (o.get("info") or {}).get("clientOrderId") or "")
            if not cid.startswith("rev") or cid in known:
                continue
            if o.get("reduceOnly"):
                continue
            try:
                _rev_api(exchange.cancel_order, o.get("id"), o.get("symbol"))
                n_orph += 1
            except Exception as e:
                log.warning(f"[LiveRev] orphan cancel failed {cid}: {e}")
        if n_orph:
            log.warning(f"[LiveRev] cancelled {n_orph} orphan entry orders")
    except Exception as e:
        log.warning(f"[LiveRev] orphan sweep skipped: {e}")
    finally:
        if isinstance(_opt, dict):
            if _old_warn is None:
                _opt.pop("warnOnFetchOpenOrdersWithoutSymbol", None)
            else:
                _opt["warnOnFetchOpenOrdersWithoutSymbol"] = _old_warn
    if dropped:
        log.info(f"[LiveRev] dropped {dropped} stale/legacy watchers on startup")
    save_reversal_watchers()
```

### 📌 `_rev_sub_info` — lines 14004–14006 (3 سطر)
```python
def _rev_sub_info():
    sub_tf = _get_subbars_tf(CFG.timeframe) or "15m"
    return sub_tf, int(_sub_tf_seconds(sub_tf))
```

### 📌 `_rev_tick` — lines 14110–14124 (15 سطر)
```python
def _rev_tick(exchange, sym: str):
    try:
        import ccxt as _cc
        p = (exchange.market(sym).get("precision") or {}).get("price")
        if p is None:
            return None
        p = float(p)
        mode = getattr(exchange, "precisionMode", None)
        if mode == getattr(_cc, "TICK_SIZE", 4):
            return p if p > 0 else None
        if mode == getattr(_cc, "DECIMAL_PLACES", 2):
            return 10.0 ** (-int(p))
    except Exception:
        pass
    return None
```

### 📌 `_snap_qty` — lines 14141–14154 (14 سطر)
```python
def _snap_qty(exchange, sym: str, qty: float) -> float:
    """[REV-FIX] was referenced but never defined (NameError)."""
    q = float(qty)
    try:
        q = float(exchange.amount_to_precision(sym, q))
    except Exception:
        pass
    try:
        mn = _lv_min_amount(exchange, sym)
        if mn and q < mn:
            return 0.0
    except Exception:
        pass
    return q
```

### 📌 `check_thermodynamic_apex` — lines 10010–10063 (54 سطر)
```python
def check_thermodynamic_apex(pos_action, entry_price, current_price, ad, fi):
    """
    مستشعر الأوج — σ-scaled thresholds when APEX_SIGMA_SCALED=True.

    Thresholds:
      - min_pnl:      κ_pnl × σ_bar  (default κ_pnl = 0.5)
      - energy_thr:   κ_e × σ_bar    (default κ_e = 0.5)
      - accel_thr:    κ_a × σ_bar    (default κ_a = 0.3)

    Falls back to absolute values (0.005, 0.005, 0.003) when flag is off.
    """
    if fi < 3:
        return False, ""

    # ── σ-scaled base ──
    try:
        sigma = float(ad.E_therm[fi]) if fi < len(ad.E_therm) else 0.01
        if not np.isfinite(sigma) or sigma <= 1e-6:
            sigma = 0.01
    except Exception:
        sigma = 0.01

    if getattr(CFG, 'APEX_SIGMA_SCALED', True):
        KAPPA_PNL = float(getattr(CFG, 'APEX_KAPPA_PNL', 0.5))
        KAPPA_E   = float(getattr(CFG, 'APEX_KAPPA_ENERGY', 0.5))
        KAPPA_A   = float(getattr(CFG, 'APEX_KAPPA_ACCEL', 0.3))
        min_pnl    = KAPPA_PNL * sigma
        energy_thr = KAPPA_E   * sigma
        accel_thr  = KAPPA_A   * sigma
    else:
        min_pnl    = 0.005
        energy_thr = 0.005
        accel_thr  = 0.003

    pnl = ((current_price - entry_price) / entry_price
           if pos_action == "BUY"
           else (entry_price - current_price) / entry_price)
    if pnl < min_pnl:
        return False, ""

    dF_window = ad.dF[fi - 2:fi + 1]
    sum_dF = np.sum(dF_window)

    accel_window = ad.geodesic_accel[fi - 2:fi + 1]
    accel_mean = np.mean(accel_window)

    energy_exhausted = (sum_dF > energy_thr)

    if pos_action == "BUY" and energy_exhausted and accel_mean < accel_thr:
        return True, "Apex: Action Integral Exhaustion"
    if pos_action == "SELL" and energy_exhausted and accel_mean > -accel_thr:
        return True, "Apex: Action Integral Exhaustion"

    return False, ""
```

### 📌 `load_reversal_watchers` — lines 14019–14047 (29 سطر)
```python
def load_reversal_watchers(mode: str) -> Dict[str, Dict]:
    global _REVERSAL_WATCHERS, _REVERSAL_WATCHERS_PATH
    global _REV_LEDGER, _REV_LEDGER_PATH, _REV_STATE_FILE
    _REVERSAL_WATCHERS_PATH = f"reversal_watchers_{mode}.json"
    _REV_LEDGER_PATH = f"reversal_ledger_{mode}.json"
    _REV_STATE_FILE = f"live_state_{mode}.json"
    _REVERSAL_WATCHERS = {}
    _REV_LEDGER = {}
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
    if os.path.exists(_REV_LEDGER_PATH):
        try:
            with open(_REV_LEDGER_PATH) as f:
                _REV_LEDGER = {str(k): float(v)
                               for k, v in json.load(f).items()}
        except Exception as e:
            log.warning(f"[LiveRev] ledger load failed: {e}")
            _REV_LEDGER = {}
    _rev_ledger_purge()
    return _REVERSAL_WATCHERS
```

### 📌 `monitor_reversal_watchers` — lines 14934–15035 (102 سطر)
```python
def monitor_reversal_watchers(exchange, open_pos_live: Dict,
                                assets: Optional[Dict] = None,
                                cap_now=None, corr_cache=None) -> None:
    if not getattr(CFG, "REVERSAL_CONFIRM_ENABLED", False):
        return
    if not _REVERSAL_WATCHERS:
        return
    now = _t_rev.time()
    if now < _REV_BACKOFF_UNTIL:
        return
    sub_tf, sub_sec = _rev_sub_info()
    tw = int(getattr(CFG, "REVERSAL_TOUCH_SUBBARS", 20))
    bw = int(getattr(CFG, "REVERSAL_BOUNCE_SUBBARS", 4))
    max_fetch = int(_revc("REV_MAX_FETCH_PER_CYCLE", 10))
    dirty = False
    starts = 0
    fetched = 0
    scan_syms = []

    for sym in list(_REVERSAL_WATCHERS.keys()):
        w = _REVERSAL_WATCHERS[sym]
        st = w.get("status", "WAITING_TOUCH")
        try:
            if st in ("FILLED", "EXPIRED"):
                if _rev_ladder_cleanup(exchange, sym, w, open_pos_live):   # [REV-FIX v3]
                    _REVERSAL_WATCHERS.pop(sym, None)
                dirty = True
                continue
            if st == "FILLING":
                _rev_advance_filling(exchange, sym, w, open_pos_live,
                                     assets, now)
                dirty = True
                continue
            if st == "READY_TO_FILL":
                if starts < _REV_MAX_PER_CYCLE:
                    _rev_handle_ready(exchange, sym, w, open_pos_live, now,
                                      sub_sec, cap_now, corr_cache)
                    if w["status"] == "FILLING":
                        starts += 1
                        _rev_advance_filling(exchange, sym, w,
                                             open_pos_live, assets, now)
                    dirty = True
                continue
            if getattr(CFG, "REV_LADDER_ENABLED", False):       # [REV-FIX v3]
                _rev_qp_step(exchange, sym, w, open_pos_live, assets, now)
                if w.get("status") == "EXPIRED":
                    dirty = True
                    continue
            # waiting states — time-based hard expiry (never stuck)
            start_ts = float(w["start_ts"])
            if now > float(w.get("expire_ts", 0.0)):
                _rev_expire(w, "max_age")
                dirty = True
                continue
            if st == "WAITING_TOUCH" and \
                    now > start_ts + (tw + 3) * sub_sec:
                _rev_expire(w, "touch_window_time")
                dirty = True
                continue
            if st == "WAITING_BOUNCE" and \
                    now > start_ts + (int(w["touch_k"]) + bw + 4) * sub_sec:
                _rev_expire(w, "bounce_time")
                dirty = True
                continue
            if now >= float(w.get("next_fetch_ts", 0.0)):
                scan_syms.append(sym)
        except Exception as e:
            w["err"] = int(w.get("err", 0)) + 1
            log.warning(f"[LiveRev] {sym} step error #{w['err']}: {e}")
            if w["err"] >= 20 and w.get("status") not in ("FILLING",):
                _rev_expire(w, "errors")
                dirty = True

    scan_syms.sort(key=lambda s: float(
        _REVERSAL_WATCHERS[s].get("next_fetch_ts", 0.0)))
    for sym in scan_syms:
        if fetched >= max_fetch or _t_rev.time() < _REV_BACKOFF_UNTIL:
            break
        w = _REVERSAL_WATCHERS.get(sym)
        if w is None or w.get("status") not in ("WAITING_TOUCH",
                                                "WAITING_BOUNCE"):
            continue
        try:
            fetched += 1
            _rev_scan(exchange, sym, w, sub_tf, sub_sec, now)
            dirty = True
            if w["status"] == "READY_TO_FILL" and starts < _REV_MAX_PER_CYCLE:
                _rev_handle_ready(exchange, sym, w, open_pos_live, now,
                                  sub_sec, cap_now, corr_cache)
                if w["status"] == "FILLING":
                    starts += 1
                    _rev_advance_filling(exchange, sym, w, open_pos_live,
                                         assets, now)
        except Exception as e:
            w["next_fetch_ts"] = now + 5.0
            w["err"] = int(w.get("err", 0)) + 1
            log.debug(f"[LiveRev] {sym} scan error #{w['err']}: {e}")
            if w["err"] >= 40:
                _rev_expire(w, "errors")
                dirty = True
    if dirty:
        save_reversal_watchers()
```

### 📌 `save_reversal_watchers` — lines 14050–14059 (10 سطر)
```python
def save_reversal_watchers() -> None:
    if not _REVERSAL_WATCHERS_PATH:
        return
    try:
        ser = {}
        for sym, w in _REVERSAL_WATCHERS.items():
            ser[sym] = {k: v for k, v in w.items() if k != "signal_ref"}
        _rev_atomic_dump(_REVERSAL_WATCHERS_PATH, ser)
    except Exception as e:
        log.warning(f"[LiveRev] save failed: {e}")
```

### ⚠️ دوال مطلوبة غير موجودة (1)
```
_last_closed_subbar_close
```

## 3️⃣ CLI Flags
```
 17670:     p.add_argument("--mode",        default="backtest", choices=["backtest","testnet","live"])
 17671:     p.add_argument("--api-key",     default=os.environ.get("BINANCE_API_KEY",""))
 17672:     p.add_argument("--api-secret",  default=os.environ.get("BINANCE_API_SECRET",""))
 17673:     p.add_argument("--capital",     type=float, default=None)
 17674:     p.add_argument("--live-capital", type=float, default=None,
 17676:     p.add_argument("--base-risk",   type=float, default=None)
 17677:     p.add_argument("--max-risk",    type=float, default=None)
 17678:     p.add_argument("--min-risk",    type=float, default=None)
 17679:     p.add_argument("--lambda-k",    type=float, default=None)
 17680:     p.add_argument("--leverage",    type=int,   default=None)
 17681:     p.add_argument("--sl-factor",   type=float, default=None)
 17682:     p.add_argument("--min-score",   type=int,   default=None)
 17683:     p.add_argument("--max-hold",    type=int,   default=None)
 17684:     p.add_argument("--topo-div",    type=float, default=None)
 17685:     p.add_argument("--cosm-const",  type=float, default=None)
 17686:     p.add_argument("--k-min",       type=int,   default=None)
 17687:     p.add_argument("--k-max",       type=int,   default=None)
 17688:     p.add_argument("--timeframe",
 17691:     p.add_argument("--history-days",       type=int,   default=None)
 17692:     p.add_argument("--end-date", type=str, default=None,
 17694:     p.add_argument("--no-numba", action="store_true",
 17696:     p.add_argument("--nassets",       type=int,   default=15)
 17697:     p.add_argument("--maxcon",       type=int,   default=2)
 17698:     p.add_argument("--fill-mode",   choices=["maker", "taker", "hybrid"], default=None,
 17700:     p.add_argument("--fill-target", type=float, default=None,
 17702:     p.add_argument("--no-fill-engine", action="store_true",
 17704:     p.add_argument("--no-parallel", action="store_true",
 17706:     p.add_argument("--workers", type=int, default=0,
 17708:     p.add_argument("--no-cache", action="store_true",
 17710:     p.add_argument("--clear-cache", action="store_true",
 17712:     p.add_argument("--po-pen-bps", type=float, default=None,
 17714:     p.add_argument("--po-wait-s", type=int, default=None,
 17717:     p.add_argument("--heat-max", type=float, default=None,
 17719:     p.add_argument("--no-budget", action="store_true",
 17721:     p.add_argument("--ml-filter", action="store_true",
 17723:     p.add_argument("--ml-model", type=str, default=None,
 17725:     p.add_argument("--ml-threshold", type=float, default=None,
 17727:     p.add_argument("--rule-filter", action="store_true",
 17729:     p.add_argument("--rule-min-score", type=int, default=None,
 17731:     p.add_argument("--max-notional", type=float, default=None,
 17733:     p.add_argument("--no-dynamic-trail", action="store_true",
 17735:     p.add_argument("--no-trailing", action="store_true",
 17737:     p.add_argument("--trailing", action="store_true",
 17739:     p.add_argument("--trail-kappa", type=float, default=None,
 17741:     p.add_argument("--reentry-cooldown", type=int, default=None,
 17743:     p.add_argument("--no-reentry-cooldown", action="store_true",
 17745:     p.add_argument("--no-live-cache", action="store_true",
 17747:     p.add_argument("--live-cache-size", type=int, default=None,
 17749:     p.add_argument("--no-fixed-price", action="store_true",
 17752:     p.add_argument("--reversal-confirm", action="store_true",
 17754:     p.add_argument("--reversal-touch-subbars", type=int, default=None,
 17756:     p.add_argument("--reversal-bounce-subbars", type=int, default=None,
 17758:     p.add_argument("--reversal-max-hours", type=float, default=None,
 17760:     p.add_argument("--reversal-mode", type=str, default=None,
 17764:     p.add_argument("--reversal-kappa", type=float, default=None,
 17766:     p.add_argument("--reversal-fill", type=str, default=None,
 17770:     p.add_argument("--rev-ladder", action="store_true",
 17772:     p.add_argument("--rev-ladder-qp", type=float, default=None,
 17774:     p.add_argument("--rev-ladder-wait-h", type=float, default=None,
 17776:     p.add_argument("--confirm-entry", action="store_true",
 17780:     p.add_argument("--confirm-kappa", type=float, default=None,
 17783:     p.add_argument("--po-max-attempts", type=int, default=None,
 17785:     p.add_argument("--po-max-drift-bps", type=float, default=None,
 17787:     p.add_argument("--po-min-accept", type=float, default=None,
 17789:     p.add_argument("--no-pending", action="store_true",
 17791:     p.add_argument("--no-smart-ohlcv", action="store_true",
 17793:     p.add_argument("--sr-filter", action="store_true",
 17795:     p.add_argument("--sr-strength", type=float, default=None,
 17797:     p.add_argument("--sr-proximity", type=float, default=None,
 17799:     p.add_argument("--kill-secret", type=str,
 17802:     p.add_argument("--trade-log", type=str, default=None,
 17806:     p.add_argument("--sing-timing", action="store_true",
 17809:     p.add_argument("--sing-active", action="store_true",
 17813:     p.add_argument("--sing-funding-guard", action="store_true",
 17817:     p.add_argument("--sing-risk-boost", action="store_true",
 17821:     p.add_argument("--filter", action="store_true",
 17823:     p.add_argument("--filter-action-bias", action="store_true",
 17826:     p.add_argument("--filter-no-ema", action="store_true",
 17828:     p.add_argument("--filter-no-atr", action="store_true",
 17830:     p.add_argument("--filter-no-friction", action="store_true",
 17832:     p.add_argument("--filter-min-votes", type=int, default=None,
 17834:     p.add_argument("--filter-atr-max", type=float, default=None,
 17836:     p.add_argument("--filter-friction-max", type=float, default=None,
 17838:     p.add_argument("--filter-log", action="store_true",
 17840:     p.add_argument("--no-kill-switch", action="store_true",
 17842:     p.add_argument("--no-watch", action="store_true",
 17845:     p.add_argument("--gauge-filter", action="store_true",
 17847:     p.add_argument("--gauge-buy-pct", type=float, default=None,
 17849:     p.add_argument("--gauge-sell-pct", type=float, default=None,
 17851:     p.add_argument("--gauge-disable-sell", action="store_true",
 17855:     p.add_argument("--no-apex", action="store_true",
 17857:     p.add_argument("--no-partial", action="store_true",
 17859:     p.add_argument("--no-breakeven", action="store_true",
 17861:     p.add_argument("--tp-mult", type=float, default=None,
 17863:     p.add_argument("--partial-tp-r", type=float, default=None,
 17865:     p.add_argument("--sl-widen-mult", type=float, default=None,
 17867:     p.add_argument("--sell-only", action="store_true",
 17869:     p.add_argument("--enable-sell", action="store_true",
 17872:     p.add_argument("--sell-min-score", type=int, default=None)
 17873:     p.add_argument("--sell-min-zdev", type=float, default=None)
 17874:     p.add_argument("--sell-gauge-pct", type=float, default=None)
 17875:     p.add_argument("--sell-require-ema-down", action="store_true")
 17876:     p.add_argument("--sell-major-only", action="store_true")
 17877:     p.add_argument("--sell-min-atr-frac", type=float, default=None)
 17878:     p.add_argument("--opp-tp", action="store_true",
 17882:     p.add_argument("--opp-tp-score-mult", type=float, default=None,
 17885:     p.add_argument("--opp-tp-min-profit-r", type=float, default=None,
 17888:     p.add_argument("--opp-tp-min-delta-r", type=float, default=None,
 17891:     p.add_argument("--opp-tp-max-age-bars", type=int, default=None,
 17894:     p.add_argument("--mfal", action="store_true",
 17896:     p.add_argument("--mfal-no-micro", action="store_true",
 17898:     p.add_argument("--mfal-no-time", action="store_true",
 17900:     p.add_argument("--mfal-no-learn", action="store_true",
 17902:     p.add_argument("--mfal-weights", type=str, default=None,
```

## 4️⃣ Wiring في main()
```
 17752:     p.add_argument("--reversal-confirm", action="store_true",
 17754:     p.add_argument("--reversal-touch-subbars", type=int, default=None,
 17756:     p.add_argument("--reversal-bounce-subbars", type=int, default=None,
 17758:     p.add_argument("--reversal-max-hours", type=float, default=None,
 17760:     p.add_argument("--reversal-mode", type=str, default=None,
 17764:     p.add_argument("--reversal-kappa", type=float, default=None,
 17766:     p.add_argument("--reversal-fill", type=str, default=None,
 17988:             "reversal_watchers_live.json",
 17989:             "reversal_watchers_testnet.json",
 17990:             "reversal_ledger_live.json",
 17991:             "reversal_ledger_testnet.json",
 18143:     if getattr(args, "reversal_confirm", False):
 18144:         CFG.REVERSAL_CONFIRM_ENABLED = True
 18145:     if getattr(args, "reversal_touch_subbars", None) is not None:
 18146:         CFG.REVERSAL_TOUCH_SUBBARS = int(args.reversal_touch_subbars)
 18147:     if getattr(args, "reversal_bounce_subbars", None) is not None:
 18148:         CFG.REVERSAL_BOUNCE_SUBBARS = int(args.reversal_bounce_subbars)
 18149:     if getattr(args, "reversal_max_hours", None) is not None:
 18150:         CFG.REVERSAL_MAX_HOURS = float(args.reversal_max_hours)
 18151:     if getattr(args, "reversal_mode", None) is not None:
 18152:         CFG.REVERSAL_CONFIRM_MODE = str(args.reversal_mode)
 18153:     if getattr(args, "reversal_kappa", None) is not None:
 18154:         CFG.REVERSAL_CONFIRM_KAPPA = float(args.reversal_kappa)
 18155:     if getattr(args, "reversal_fill", None) is not None:
 18156:         CFG.REVERSAL_FILL_AT = str(args.reversal_fill)
 18158:     if getattr(args, "rev_ladder", False):
 18159:         CFG.REV_LADDER_ENABLED = True
 18160:     if getattr(args, "rev_ladder_qp", None) is not None:
 18161:         CFG.REV_LADDER_QP_PCT = float(args.rev_ladder_qp)
 18162:     if getattr(args, "rev_ladder_wait_h", None) is not None:
 18163:         CFG.REV_LADDER_MAX_WAIT_S = float(args.rev_ladder_wait_h) * 3600.0
 18164:     if CFG.REV_LADDER_ENABLED:
 18165:         if not CFG.REVERSAL_CONFIRM_ENABLED:
 18166:             log.warning("[Ladder] --rev-ladder needs --reversal-confirm; ladder disabled")
 18167:             CFG.REV_LADDER_ENABLED = False
 18169:             log.info(f"[Ladder] ENABLED levels={CFG.REV_LADDER_OFFSETS_SIGMA} "
 18170:                      f"weights={CFG.REV_LADDER_WEIGHTS} qp={CFG.REV_LADDER_QP_PCT} "
 18171:                      f"wait={CFG.REV_LADDER_MAX_WAIT_S/3600:.1f}h  "
 18173:     if CFG.REVERSAL_CONFIRM_ENABLED:
 18175:                  f"touch={CFG.REVERSAL_TOUCH_SUBBARS}sb "
 18176:                  f"bounce={CFG.REVERSAL_BOUNCE_SUBBARS}sb "
 18177:                  f"max={CFG.REVERSAL_MAX_HOURS}h "
 18178:                  f"mode={CFG.REVERSAL_CONFIRM_MODE} "
 18179:                  f"fill={CFG.REVERSAL_FILL_AT}")
 18233:         CFG.APEX_ENABLED = False
 18256:         CFG.APEX_ENABLED = False
```

## 5️⃣ أجزاء من دوال أخرى (للتحقق)

### 📄 `_advance` (lines 5851–5865) — أول 15 سطر
```python
  5851: def _advance(pos, ad, to_ci, partial_cb=None):
  5852:     """
  5853:     Walk bars from current_ci+1 to to_ci.
  5854: 
  5855:     SUB-BAR MODE (when ad.sub_highs is available):
  5856:         The entry bar is iterated from `pos.entry_sub_idx + 1` through
  5857:         the last sub-bar. Subsequent bars are iterated fully. This
  5858:         resolves the intrabar path ambiguity:
  5859:             - If SL touches before TP → real exit
  5860:             - If TP touches first         → real exit
  5861:             - Both within one sub-bar     → pessimistic (SL first)
  5862: 
  5863:     MAIN-BAR MODE (fallback):
  5864:         Legacy: skip entry bar entirely. SL is checked before TP
  5865:         (pessimistic).
    ... (+224 سطر لم تُعرَض)
```

### 📄 `main` (lines 17668–17682) — أول 15 سطر
```python
 17668: def main():
 17669:     p = argparse.ArgumentParser(description="Quantum Thermo Trader v6.0 – Singularity Engine")
 17670:     p.add_argument("--mode",        default="backtest", choices=["backtest","testnet","live"])
 17671:     p.add_argument("--api-key",     default=os.environ.get("BINANCE_API_KEY",""))
 17672:     p.add_argument("--api-secret",  default=os.environ.get("BINANCE_API_SECRET",""))
 17673:     p.add_argument("--capital",     type=float, default=None)
 17674:     p.add_argument("--live-capital", type=float, default=None,
 17675:                    help="Fixed trading capital for live/testnet sizing (overrides exchange free balance)")
 17676:     p.add_argument("--base-risk",   type=float, default=None)
 17677:     p.add_argument("--max-risk",    type=float, default=None)
 17678:     p.add_argument("--min-risk",    type=float, default=None)
 17679:     p.add_argument("--lambda-k",    type=float, default=None)
 17680:     p.add_argument("--leverage",    type=int,   default=None)
 17681:     p.add_argument("--sl-factor",   type=float, default=None)
 17682:     p.add_argument("--min-score",   type=int,   default=None)
    ... (+765 سطر لم تُعرَض)
```

### 📄 `run_live` (lines 16002–16016) — أول 15 سطر
```python
 16002: def run_live(cfg, exchange):
 16003:     """
 16004:     محرك التداول الحي والـ Testnet عالي التردد (HFT):
 16005:     - يلتزم بميكانيكا التكميم والسببية المستمرة ومعدل استقصاء 5 ثوانٍ.
 16006:     - يقرأ مستشعر الأوج للتكامل الحركي (Action Integral) في الوقت الفعلي.
 16007:     - يطبق قانون القوة لـ بئر دريخليه (10$ لحماية رأس المال المجهري).
 16008:     """
 16009:     log.info(f"🔴 [{cfg.mode.upper()}] بدء التشغيل (State Machine v2)")
 16010:     state_file = f"live_state_{cfg.mode}.json"
 16011:     open_pos_live: Dict[str, Dict] = {}
 16012: 
 16013:     # ══ [State] Load persistent positions ══
 16014:     if os.path.exists(state_file):
 16015:         try:
 16016:             with open(state_file) as f:
    ... (+1621 سطر لم تُعرَض)
```

### 📄 `simulate_portfolio` (lines 6287–6301) — أول 15 سطر
```python
  6287: def simulate_portfolio(signals, assets, corr_matrix, mode="backtest"):
  6288:     """
  6289:     محاكاة المحفظة متعددة المراكز (Backtest Engine):
  6290:     - تطبق قانون القوة (Power-Law Scaling) لتعديل المخاطرة ديناميكياً.
  6291:     - تقضي على انحياز النظر للمستقبل (Causality Enforcement) بالدخول اللحظي بسعر النفق.
  6292:     - تحاكي الوقف والهدف بناءً على حركات ذيول الشموع اللحظية (High/Low).
  6293:     """
  6294:     capital  = CFG.INITIAL_CAPITAL
  6295:     peak_cap = capital
  6296:     equity   = [capital]
  6297:     trades_out: List[Trade] = []
  6298:     open_pos: Dict[str, OpenPosition] = {}
  6299:     # ══ [RE-ENTRY COOLDOWN] Track last exit bar per symbol ══
  6300:     last_exit_ci: Dict[str, int] = {}
  6301:     # ══ [BACKTEST REALISM] Precompute which entries actually fill ══
    ... (+467 سطر لم تُعرَض)
```

## 6️⃣ مؤشرات (grep)

### `REV_FIX_MARKERS` — 35 نتيجة

```

   138:     """[REV-FIX v2] stdout + size-rotated file, full dates (multi-week runs).

   818:     REVERSAL_FILL_AT:        str   = "target"  # [REV-FIX v1] realizable: confirm-bar close (was "target")

   829:     REVERSAL_ESCAPE_CHECK_INTERVAL_S: float = 5.0   # [REV-FIX v1] escape logic removed (unused)

   830:     # ══ [REV-FIX v1] reversal-confirm live/backtest parity knobs ══

   845:     # ══ [REV-FIX v2] long-run hardening knobs ══

   864:     # ══ [REV-FIX v3] Maker Ladder (Phase 1) - opt-in ══

  5195: _REV_ENTRY_SUB = {}   # [REV-FIX v1] (symbol, close_idx) -> entry sub-bar index inside the entry main bar

  5303: ##    # [REV-FIX v1] live can only enter AFTER the confirm bar closes:

  5522:                 # [REV-FIX v1] main-bar hours (was sub-bar hours -> 96 bars instead of 6)

  6573:         # [REV-FIX v1] reversal-confirm: SL/TP are evaluated only from the

 10620:     # [REV-FIX v2] bans expire (was: banned for the whole process lifetime)

 12941:     # write-then-rename (crash-safe) and [REV-FIX v2] skipped when unchanged

 13966: # [LIVE REVERSAL] [REV-FIX v1] Touch-and-Bounce on sub-bars (non-blocking)

 14016:     _json_write_if_changed(path, obj, indent=1)   # [REV-FIX v2]

 14142:     """[REV-FIX] was referenced but never defined (NameError)."""

 14523:     if sym in open_pos_live and not w.get("qp_pos"):     # [REV-FIX v3] QP-owned position is ours

 14578:     if getattr(CFG, "REV_LADDER_ENABLED", False):        # [REV-FIX v3]

 14616:                              - float(w.get("order_px", 0.0))) > 0.0:   # [REV-FIX v3]

 14904:         known = _rev_known_cids()      # [REV-FIX v3] includes ladder / queue-priority cids

 14958:                 if _rev_ladder_cleanup(exchange, sym, w, open_pos_live):   # [REV-FIX v3]

 14977:             if getattr(CFG, "REV_LADDER_ENABLED", False):       # [REV-FIX v3]

 15042: # [REV-FIX v2] Long-run hardening

 15433: # [REV-FIX v3] Maker Ladder — Phase 1 (opt-in, default OFF)

 16047:     # ══ [LiveRev] [REV-FIX v1] startup recovery: stale/legacy watchers, orphan entry orders ══

 16170:             # ══ [REV-FIX v2] hourly time sync / 6-hourly markets reload ══

 16251:             # [REV-FIX v2] background refresh + atomic swap (no multi-minute blackout)

 16360:                     # [REV-FIX v2] catches up after missed bars (was: always last 3)

 16986:             # [REV-FIX v1] parity: the backtest gates on the flat MAX_CONCURRENT_ASSETS

 17002:             # [REV-FIX v1] reversal mode: keep scanning/registering even when all slots

 17390:                                 # [REV-FIX v1] watchers NEVER consume position slots

... +5 أكثر

```

### `SUBBAR_ONLY` — 0 نتيجة

### `REV_LADDER_ENABLED` — 7 نتيجة

```

   865:     REV_LADDER_ENABLED: bool = False

 14578:     if getattr(CFG, "REV_LADDER_ENABLED", False):        # [REV-FIX v3]

 14977:             if getattr(CFG, "REV_LADDER_ENABLED", False):       # [REV-FIX v3]

 15792:     if not _cfg3("REV_LADDER_ENABLED", False):

 18159:         CFG.REV_LADDER_ENABLED = True

 18164:     if CFG.REV_LADDER_ENABLED:

 18167:             CFG.REV_LADDER_ENABLED = False

```

### `GTX_usage` — 7 نتيجة

```

  9530:                     _ord_params = {} if cross_spread else {'timeInForce': 'GTX'}

  9777:                     params={'timeInForce': 'GTX'}

 11896:                             params={'timeInForce': 'GTX'}

 12001:                                     params={'timeInForce': 'GTX'}

 12081:                             params={'timeInForce': 'GTX'}

 12553:                 params={'timeInForce': 'GTX'}

 15572:                      params={"timeInForce": "GTX", "clientOrderId": cid})

```

### `marketable_usage` — 38 نتيجة

```

   612:     # for post-only. They cross the spread (marketable limit) — cost is

  2962:           (marketable limit or market order)

  2982:     - Taker fills (market, marketable-limit, stop-market) → adverse

  5463:             # ══ [SING-TIMING Layer 2] ACTIVE → marketable فوري ══

  9529:                     # for marketable limit — the exchange would reject.

 11758:                                     != "marketable"

 11785:                                 # 3) place marketable

 11832:                                         rec['execution_mode'] = "marketable"

 11833:                                         rec['marketable_px'] = float(_mk_px)

 11840:                                             f"upgraded GTX → marketable "

 11848:                                         f"marketable upgrade failed: "

 12342:     # كل من Layer 1 (timeout) و Layer 2 (marketable). ══

 12494:     _marketable_px = None

 12511:                 _marketable_px = _best_ask * (1.0 + _pen_frac)

 12513:                 _marketable_px = _best_bid * (1.0 - _pen_frac)

 12515:             # فحص الانزلاق: كم يبعد الـ marketable عن sig.price؟

 12516:             _slip_bps = (abs(_marketable_px - sig.price)

 12530:                     sym, 'limit', side, qty, _marketable_px,

 12533:                 _exec_mode = "marketable"

 12534:                 target = _marketable_px

 12537:                     f"(rho={_sing_rho:+.3f}) → marketable @ "

 12538:                     f"{_marketable_px:.6f} (slip={_slip_bps:.1f}bps, "

 12543:                 f"[Sing-Timing-L2] {sym} marketable failed: {_e} "

 12691:         'marketable_px': (float(_marketable_px)

 12692:                            if _marketable_px is not None else 0.0),

 14615:                     elif abs(_rev_marketable_px(exchange, sym, w, action, side, px, ref_px)

 14673:         marketable_px = px + max_slip_allowed

 14676:         marketable_px = px - max_slip_allowed

 14679:     marketable_px = _rev_snap_price(exchange, sym, marketable_px, side)

 14681:     w["order_px"] = marketable_px

... +8 أكثر

```

### `snap_qty_calls` — 8 نتيجة

```

 12393:         qty = float(_snap_qty(exchange, sym, qty))

 14141: def _snap_qty(exchange, sym: str, qty: float) -> float:

 14649:     q = _snap_qty(exchange, sym, remaining)

 14852:                          _snap_qty(exchange, sym, filled) or filled, None,

 15715:                  _snap_qty(exchange, sym, qty) or qty, None,

 15819:         q = _snap_qty(exchange, sym, float(w["qty"]) * pct)

 15910:             q = _snap_qty(exchange, sym, q) if q > 0 else 0.0

 15915:                 recs[-1]["qty"] = _snap_qty(exchange, sym, recs[-1]["qty"] + q)

```

### `lad_place_calls` — 3 نتيجة

```

 15556: def _lad_place(exchange, sym: str, w: Dict, rec: Dict, bid, ask,

 15824:         if _lad_place(exchange, sym, w, rec, bid, ask, clamp=False) in (

 15936:                 _lad_place(exchange, sym, w, r, bid, ask, clamp=True)

```

### `_bar_confirms_calls` — 2 نتيجة

```

 14281: def _bar_confirms_bounce(w: Dict, close: float) -> bool:

 14500:             if np.isfinite(c) and _bar_confirms_bounce(w, c):

```

### `apex_calls` — 3 نتيجة

```

  6048:             is_apex, apex_rsn = check_thermodynamic_apex(

 10010: def check_thermodynamic_apex(pos_action, entry_price, current_price, ad, fi):

 16558:                         is_apex, apex_rsn = check_thermodynamic_apex(

```

### `monitor_rev_calls` — 4 نتيجة

```

 11252: #def monitor_reversal_watchers(exchange, open_pos_live: Dict,

 14934: def monitor_reversal_watchers(exchange, open_pos_live: Dict,

 15343:             monitor_reversal_watchers(exchange, open_pos_live, assets=assets,

 16224:                 monitor_reversal_watchers(

```

## 7️⃣ إحصاءات
- **عدد الدوال/الفئات الكلي:** 360
- **دوال reversal/ladder الموجودة:** 54/55
- **إصدارات REV-FIX:** 35
