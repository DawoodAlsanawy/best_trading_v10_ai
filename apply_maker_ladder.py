#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_maker_ladder.py  [REV-FIX v3]  - Maker Ladder Phase 1 (opt-in) + reprice-compat fix

Requires [REV-FIX v1] and [REV-FIX v2] already applied.
Usage:
    python apply_maker_ladder.py trading_2_live4.py --inplace
    python apply_maker_ladder.py trading_2_live4.py --dry-run
Enable at runtime with:  --rev-ladder [--rev-ladder-qp 0.05] [--rev-ladder-wait-h 6]
Default OFF: applying the patch changes nothing except the reprice-compat fix.
Every anchor must match EXACTLY ONCE or nothing is written.
"""
import argparse, ast, os, py_compile, shutil, sys, time

MARK = "[REV-FIX v3]"
NEW_V3_BLOCK = '# ═══════════════════════════════════════════════════════════════\n# [REV-FIX v3] Maker Ladder — Phase 1 (opt-in, default OFF)\n#   * post-bounce ladder: 3 post-only (GTX) levels  mu, mu-0.3s, mu-0.6s\n#     weights 40/35/25 (BUY; mirrored above mu for SELL), s = sigma_bar*target\n#   * optional "queue priority" order (default 5% of qty, taken out of L0)\n#     resting AT target from registration (pre-touch)\n#   * every level is its own GTX order (clientOrderId idempotent, crash-safe)\n#   * position is created at the FIRST fill and grown on every later fill\n#     (SL/TP re-anchored on the VWAP, protective legs refreshed)\n#   * a symbol with resting orders RESERVES one MAX_CONCURRENT slot, so the\n#     asynchronous fills can never exceed the open-position cap\n#   * hard deadline (REV_LADDER_MAX_WAIT_S): everything cancelled\n#   * ladder_stats_<mode>.csv: one row per ladder for the testnet evaluation\n# NOT possible on Binance USDT-M futures: icebergQty (spot only) -> not built.\n# ═══════════════════════════════════════════════════════════════\nimport csv as _csv3\n\n\ndef _cfg3(name: str, default):\n    return getattr(CFG, name, default)\n\n\ndef _rev_marketable_px(exchange, sym: str, w: Dict, action: str, side: str,\n                       px: float, ref_px: float) -> float:\n    """Price the \'Smart Execution\' marketable limit uses (best bid/ask +- 15%\n    of the original SL distance) - the reprice check must compare THIS value,\n    not the raw best bid/ask (it used to cancel/replace a resting order every\n    reprice tick)."""\n    sl_d = float(w.get("orig_sl_dist", ref_px * 0.015))\n    m = (px + sl_d * 0.15) if action == "BUY" else (px - sl_d * 0.15)\n    return _rev_snap_price(exchange, sym, m, side)\n\n\n# ───────────────────────── ladder primitives ─────────────────────────\ndef _lad_levels():\n    offs = list(_cfg3("REV_LADDER_OFFSETS_SIGMA", (0.0, 0.3, 0.6)))\n    wts = list(_cfg3("REV_LADDER_WEIGHTS", (0.40, 0.35, 0.25)))\n    n = min(len(offs), len(wts))\n    offs, wts = offs[:n], wts[:n]\n    tot = float(sum(wts)) or 1.0\n    return [(float(o), float(x) / tot) for o, x in zip(offs, wts)]\n\n\ndef _lad_px(exchange, sym: str, w: Dict, off_sigma: float) -> float:\n    tgt = float(w["target"])\n    sp = float(w.get("sigma_bar", 0.01)) * tgt\n    if w["action"] == "BUY":\n        return _rev_snap_price(exchange, sym, tgt - off_sigma * sp, "buy")\n    return _rev_snap_price(exchange, sym, tgt + off_sigma * sp, "sell")\n\n\ndef _lad_cid(sym: str, w: Dict, tag: str, attempt: int) -> str:\n    h = _hl_rev.md5(sym.encode()).hexdigest()[:8]\n    return f"rev{int(w[\'sig_epoch\'])}x{h}x{tag}{int(attempt)}"[:36]\n\n\ndef _lad_new_rec(name: str, px: float, qty: float) -> Dict:\n    return {"name": name, "cid": None, "order_id": None, "cid_sent": False,\n            "px": float(px), "qty": float(qty), "filled": 0.0, "avg": 0.0,\n            "status": "new", "rejects": 0, "attempt": 0}\n\n\ndef _lad_all_recs(w: Dict) -> List[Dict]:\n    return ([w["qp"]] if w.get("qp") else []) + list(w.get("ladder") or [])\n\n\ndef _lad_totals(w: Dict):\n    q = c = 0.0\n    for r in _lad_all_recs(w):\n        f = float(r.get("filled") or 0.0)\n        q += f\n        c += f * float(r.get("avg") or 0.0)\n    return q, c\n\n\ndef _rev_known_cids() -> set:\n    s = set()\n    for w in _REVERSAL_WATCHERS.values():\n        if w.get("cid"):\n            s.add(str(w["cid"]))\n        for r in _lad_all_recs(w):\n            if r.get("cid"):\n                s.add(str(r["cid"]))\n    return s\n\n\ndef _rev_inflight_other(sym: str, open_pos_live: Dict) -> int:\n    """Symbols (other than `sym`) that hold or reserve a slot WITHOUT being in\n    open_pos_live yet: FILLING watchers and resting queue-priority orders."""\n    n = 0\n    for s2, w2 in _REVERSAL_WATCHERS.items():\n        if s2 == sym or s2 in open_pos_live:\n            continue\n        qp = w2.get("qp")\n        if w2.get("status") == "FILLING" or (qp and qp.get("status") == "open"):\n            n += 1\n    return n\n\n\ndef _lad_book(exchange, sym: str):\n    try:\n        ob = _rev_api(exchange.fetch_order_book, sym, 5, weight=2.0)\n        bids, asks = ob.get("bids") or [], ob.get("asks") or []\n        if not bids or not asks:\n            return None, None\n        return float(bids[0][0]), float(asks[0][0])\n    except Exception as e:\n        log.debug(f"[Ladder] {sym} book error: {e}")\n        return None, None\n\n\ndef _lad_apply(r: Dict, o: Dict) -> None:\n    r["filled"] = float(o.get("filled") or 0.0)\n    a = o.get("average")\n    try:\n        a = float(a) if a else 0.0\n    except Exception:\n        a = 0.0\n    r["avg"] = a if a > 0 else float(o.get("price") or r["px"])\n    r["order_id"] = str(o.get("id") or r.get("order_id") or "")\n    if str(o.get("status") or "open") in _REV_TERMINAL:\n        r["status"] = "done"\n\n\ndef _lad_place(exchange, sym: str, w: Dict, rec: Dict, bid, ask,\n               clamp: bool = True) -> str:\n    side = w["side_ccxt"]\n    px = float(rec["px"])\n    if clamp:                       # never cross the book (post-only)\n        if side == "buy" and bid is not None:\n            px = min(px, bid)\n        if side == "sell" and ask is not None:\n            px = max(px, ask)\n        px = _rev_snap_price(exchange, sym, px, side)\n    rec["attempt"] = int(rec.get("attempt", 0)) + 1\n    cid = _lad_cid(sym, w, rec["name"], rec["attempt"])\n    rec.update(cid=cid, cid_sent=True, px=px, status="open")\n    save_reversal_watchers()        # persist BEFORE the order exists\n    try:\n        o = _rev_api(exchange.create_order, sym, "limit", side, rec["qty"], px,\n                     params={"timeInForce": "GTX", "clientOrderId": cid})\n        rec["order_id"] = str(o.get("id") or "")\n        rec["cid_sent"] = False\n        log.info(f"[Ladder] {sym} {rec[\'name\']} GTX {side} {rec[\'qty\']} @ {px} "\n                 f"cid={cid}")\n        return "placed"\n    except Exception as e:\n        msg = str(e)\n        if ("-5022" in msg or "Post Only" in msg or "post only" in msg\n                or "immediately match" in msg):\n            rec["rejects"] = int(rec.get("rejects", 0)) + 1\n            rec.update(cid=None, cid_sent=False, status="new")\n            if rec["rejects"] >= int(_revc("REV_MAX_REJECTS", 30)):\n                rec["status"] = "done"\n            return "reject"\n        if any(c in msg for c in ("-2019", "-4164", "-1111", "-4003",\n                                  "-2027", "-4028")):\n            rec.update(cid=None, cid_sent=False, status="done")\n            log.warning(f"[Ladder] {sym} {rec[\'name\']} refused: {msg[:140]}")\n            return "fatal"\n        log.warning(f"[Ladder] {sym} {rec[\'name\']} create ambiguous: {msg[:140]}")\n        return "ambiguous"          # stays \'open\' with cid; poll resolves it\n\n\ndef _lad_poll(exchange, sym: str, recs: List[Dict]) -> None:\n    live = [r for r in recs if r.get("status") == "open" and r.get("cid")]\n    if not live:\n        return\n    try:\n        open_list = _rev_api(exchange.fetch_open_orders, sym) or []\n    except Exception as e:\n        log.debug(f"[Ladder] {sym} open-orders error: {e}")\n        return\n    by_cid = {}\n    for o in open_list:\n        k = str(o.get("clientOrderId")\n                or (o.get("info") or {}).get("clientOrderId") or "")\n        by_cid[k] = o\n    for r in live:\n        o = by_cid.get(r["cid"])\n        if o is None:\n            try:\n                o = _rev_find_order(exchange, sym, r["cid"], r.get("order_id"))\n            except Exception as e:\n                log.debug(f"[Ladder] {sym} lookup error: {e}")\n                continue\n            if o is None:           # create never reached the exchange\n                r.update(cid=None, order_id=None, cid_sent=False, status="new")\n                continue\n        _lad_apply(r, o)\n\n\ndef _lad_cancel(exchange, sym: str, rec: Dict) -> bool:\n    """True once the record is TERMINAL (no live order left)."""\n    if rec.get("status") == "new":\n        rec["status"] = "done"\n        return True\n    if rec.get("status") != "open" or not rec.get("cid"):\n        return True\n    try:\n        if rec.get("order_id"):\n            _rev_api(exchange.cancel_order, rec["order_id"], sym)\n        else:\n            _rev_api(exchange.cancel_order, None, sym,\n                     params={"origClientOrderId": rec["cid"]})\n    except Exception as e:\n        if not _rev_is_not_found(e):\n            log.debug(f"[Ladder] {sym} cancel error: {e}")\n    try:\n        o = _rev_find_order(exchange, sym, rec["cid"], rec.get("order_id"))\n    except Exception:\n        return False\n    if o is None:\n        rec["status"] = "done"\n        return True\n    _lad_apply(rec, o)\n    return rec["status"] == "done"\n\n\n# ───────────────────────── position creation / growth ─────────────────────────\ndef _lad_sl_tp(w: Dict, entry_px: float):\n    osd = float(w["orig_sl_dist"])\n    otd = float(w["orig_tp_dist"])\n    if osd <= 1e-12:\n        osd = entry_px * 0.015\n        otd = osd * float(getattr(CFG, "TP_MULT", 2.0))\n    mx = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))\n    if osd > entry_px * mx:\n        rr = otd / max(osd, 1e-12)\n        osd = entry_px * mx\n        otd = osd * rr\n    if w["action"] == "BUY":\n        return entry_px - osd, entry_px + otd, osd\n    return entry_px + osd, entry_px - otd, osd\n\n\ndef _lad_liq(w: Dict, entry_px: float):\n    if not getattr(CFG, "LIQ_ENABLED", True):\n        return None\n    try:\n        return compute_liquidation_price(entry_px, w["action"],\n                                         int(w["leverage"]),\n                                         float(w.get("mmr", 0.02)))\n    except Exception:\n        return None\n\n\ndef _lad_new_pos(sym: str, w: Dict, entry_px: float, qty: float, assets) -> Dict:\n    sl, tp, osd = _lad_sl_tp(w, entry_px)\n    sb = float(w.get("sigma_bar", 0.01))\n    td = float(np.clip(CFG.TRAIL_KAPPA * sb, CFG.TRAIL_MIN_FRAC, CFG.TRAIL_MAX_FRAC))\n    ta = float(np.clip(CFG.TRAIL_ACT_KAPPA * sb, CFG.TRAIL_ACT_MIN_FRAC,\n                       CFG.TRAIL_ACT_MAX_FRAC))\n    if ta <= td:\n        ta = td * 1.2\n    _ad = assets.get(sym) if isinstance(assets, dict) else None\n    ci_now = (len(_ad.closes) - 2) if _ad is not None else 0\n    qt = float(w.get("qty_eff") or w["qty"])\n    return {\n        "action": w["action"], "entry": entry_px, "qty": qty, "sl": sl,\n        "tp1": tp, "T_info": float(w.get("T_info", 0.0)),\n        "dyn_risk": float(w.get("dyn_risk", 0.01)), "entry_ts": _t_rev.time(),\n        "fill_ratio": qty / max(qt, 1e-9), "leverage": int(w["leverage"]),\n        "trail_dist_frac": td, "trail_activate_frac": ta,\n        "liq_price_estimated": _lad_liq(w, entry_px),\n        "mmr": float(w.get("mmr", 0.02)), "sl_dist_initial": float(osd),\n        "_entry_ci": int(max(int(w.get("close_idx", 0)), ci_now)),\n        "_trail_bars_held": 0, "_trail_peak_R": 0.0,\n        "_trail_last_update_ts": 0.0, "_sym": sym,\n        "_orig_score": float(w.get("score", 0.0)), "stage": "REVERSAL",\n    }\n\n\ndef _lad_flatten(exchange, sym: str, action: str, qty: float) -> bool:\n    try:\n        ex = _rev_exch_position(exchange, sym)\n        if ex:\n            qty = float(ex.get("qty") or qty)\n    except Exception:\n        pass\n    try:\n        _rev_api(exchange.create_order, sym, "market",\n                 "sell" if action == "BUY" else "buy",\n                 _snap_qty(exchange, sym, qty) or qty, None,\n                 params={"reduceOnly": True})\n    except Exception as e:\n        log.error(f"[Ladder] {sym} flatten FAILED: {e}")\n        return False\n    try:\n        _cancel_all_protective_orders(exchange, sym)\n    except Exception:\n        pass\n    return True\n\n\ndef _lad_protect(exchange, sym: str, pos: Dict, grown: bool) -> bool:\n    if not getattr(CFG, "PROTECTIVE_ORDERS_ENABLED", True):\n        return True\n    if grown:                       # leg quantities changed -> rebuild the legs\n        try:\n            _cancel_all_protective_orders(exchange, sym)\n        except Exception as e:\n            log.debug(f"[Ladder] {sym} protective cancel error: {e}")\n    retries = int(_revc("REV_PROTECT_RETRIES", 3))\n    for k in range(max(1, retries)):\n        try:\n            if _place_protective_orders(exchange, sym, pos):\n                pos["_prot_last_sl"] = float(pos["sl"])\n                pos["_prot_last_tp"] = float(pos["tp1"])\n                return True\n        except Exception as e:\n            log.warning(f"[Ladder] prot {sym} try{k + 1}: {e}")\n        _t_rev.sleep(0.5 * (k + 1))\n    return False\n\n\ndef _lad_sync_position(exchange, sym: str, w: Dict, open_pos_live: Dict,\n                       assets, filled: float, cost: float) -> str:\n    """Create the position at the first fill, grow it on later fills.\n    Returns noop | created | grown | flattened."""\n    sq = float(w.get("pos_synced_qty", 0.0))\n    sc = float(w.get("pos_synced_cost", 0.0))\n    dq = filled - sq\n    if dq <= 1e-12:\n        return "noop"\n    dc = cost - sc\n    pos = open_pos_live.get(sym)\n    grown = pos is not None\n    if pos is None:\n        pos = _lad_new_pos(sym, w, dc / dq, dq, assets)\n        open_pos_live[sym] = pos\n    else:\n        nq = float(pos["qty"]) + dq\n        ne = (float(pos["entry"]) * float(pos["qty"]) + dc) / nq\n        sl, tp, osd = _lad_sl_tp(w, ne)\n        pos.update(qty=nq, entry=ne, sl=sl, tp1=tp, sl_dist_initial=float(osd),\n                   liq_price_estimated=_lad_liq(w, ne))\n        pos["fill_ratio"] = nq / max(float(w.get("qty_eff") or w["qty"]), 1e-9)\n    w["pos_synced_qty"], w["pos_synced_cost"] = filled, cost\n    if _REV_STATE_FILE:\n        _lv_save_state(_REV_STATE_FILE, open_pos_live)\n    if not _lad_protect(exchange, sym, pos, grown):\n        if _revc("REV_FLATTEN_ON_UNPROTECTED", True):\n            log.error(f"[Ladder] {sym} UNPROTECTED — emergency flatten")\n            if _lad_flatten(exchange, sym, w["action"], float(pos["qty"])):\n                open_pos_live.pop(sym, None)\n                if _REV_STATE_FILE:\n                    _lv_save_state(_REV_STATE_FILE, open_pos_live)\n                return "flattened"\n    elif _REV_STATE_FILE:\n        _lv_save_state(_REV_STATE_FILE, open_pos_live)\n    log.info(f"[Ladder] {sym} position {\'grown\' if grown else \'created\'}: "\n             f"qty={pos[\'qty\']:.6f} entry={pos[\'entry\']:.6f} "\n             f"sl={pos[\'sl\']:.6f} tp={pos[\'tp1\']:.6f}")\n    return "grown" if grown else "created"\n\n\n# ───────────────────────── queue-priority order (pre-touch) ─────────────────────────\ndef _rev_qp_step(exchange, sym: str, w: Dict, open_pos_live: Dict, assets,\n                 now: float) -> None:\n    if not _cfg3("REV_LADDER_ENABLED", False):\n        return\n    qp = w.get("qp")\n    if qp is None:\n        if w.get("qp_tried") or w.get("status") != "WAITING_TOUCH":\n            return\n        w["qp_tried"] = True\n        pct = float(_cfg3("REV_LADDER_QP_PCT", 0.05))\n        if pct <= 0:\n            return\n        if len(open_pos_live) + _rev_inflight_other(sym, open_pos_live) \\\n                >= int(CFG.MAX_CONCURRENT_ASSETS):\n            log.debug(f"[Ladder] {sym} no free slot for queue-priority order")\n            return\n        if not _rate_can_place():\n            w["qp_tried"] = False\n            return\n        bid, ask = _lad_book(exchange, sym)\n        if bid is None:\n            w["qp_tried"] = False\n            return\n        tgt = float(w["target"])\n        side = w["side_ccxt"]\n        if (side == "buy" and tgt >= ask) or (side == "sell" and tgt <= bid):\n            log.debug(f"[Ladder] {sym} target not resting-side of the book "\n                      f"— no queue-priority order")\n            return\n        q = _snap_qty(exchange, sym, float(w["qty"]) * pct)\n        if q <= 0:\n            return\n        rec = _lad_new_rec("Q", _rev_snap_price(exchange, sym, tgt, side), q)\n        w["qp"] = rec\n        if _lad_place(exchange, sym, w, rec, bid, ask, clamp=False) in (\n                "reject", "fatal"):\n            w["qp"] = None\n        return\n    if qp.get("status") != "open":\n        return\n    if now - float(w.get("qp_last_poll", 0.0)) < float(\n            _cfg3("REV_LADDER_POLL_S", 10.0)):\n        return\n    w["qp_last_poll"] = now\n    _lad_poll(exchange, sym, [qp])\n    f, c = _lad_totals(w)\n    if f > 0:\n        res = _lad_sync_position(exchange, sym, w, open_pos_live, assets, f, c)\n        if res in ("created", "grown"):\n            w["qp_pos"] = True\n        elif res == "flattened":\n            w["qp_pos"] = False\n            _rev_expire(w, "qp_unprotected")\n\n\n# ───────────────────────── the ladder (post-bounce) ─────────────────────────\ndef _lad_stats(w: Dict, reason: str) -> None:\n    try:\n        f, c = _lad_totals(w)\n        qt = float(w.get("qty_eff") or w["qty"])\n        vwap = (c / f) if f > 0 else 0.0\n        tgt = float(w["target"])\n        sign = 1.0 if w["action"] == "BUY" else -1.0\n        slip = ((vwap - tgt) / tgt * 1e4 * sign) if f > 0 else 0.0\n        lv = ";".join(f"{r[\'name\']}:{r.get(\'filled\', 0.0):.6g}/{r[\'qty\']:.6g}"\n                      for r in _lad_all_recs(w))\n        path = f"ladder_stats_{CFG.mode}.csv"\n        new = not os.path.exists(path)\n        with open(path, "a", newline="", encoding="utf-8") as fh:\n            wr = _csv3.writer(fh)\n            if new:\n                wr.writerow(["iso", "sym", "action", "target", "ref_px",\n                             "qty_target", "filled", "fill_ratio", "vwap",\n                             "slip_bps_vs_target(+worse)", "levels", "qp_pos",\n                             "duration_s", "reason"])\n            wr.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), w["sym"],\n                         w["action"], tgt, w.get("ref_px"), qt, f,\n                         round(f / max(qt, 1e-12), 4), vwap, round(slip, 2),\n                         lv, bool(w.get("qp_pos")),\n                         round(time.time() - float(w.get("ladder_t0", time.time())), 1),\n                         reason])\n    except Exception as e:\n        log.debug(f"[Ladder] stats write failed: {e}")\n\n\ndef _lad_finish(exchange, sym: str, w: Dict, open_pos_live: Dict,\n                reason: str) -> None:\n    f, c = _lad_totals(w)\n    qt = float(w.get("qty_eff") or w["qty"])\n    _lad_stats(w, reason)\n    if f <= 0:\n        _rev_expire(w, f"ladder:{reason}")\n        return\n    min_ratio = float(_cfg3("REV_LADDER_MIN_FILL_RATIO", 0.0))\n    if min_ratio > 0 and f / max(qt, 1e-12) < min_ratio:\n        pos = open_pos_live.get(sym)\n        if pos is not None and _lad_flatten(exchange, sym, w["action"],\n                                            float(pos["qty"])):\n            open_pos_live.pop(sym, None)\n            if _REV_STATE_FILE:\n                _lv_save_state(_REV_STATE_FILE, open_pos_live)\n            _rev_expire(w, "ladder:min_fill_flatten")\n            return\n    w["status"] = "FILLED"\n    w["entry"] = c / f\n    log.info(f"✅ [Ladder] {sym} done ({reason}): fill {f:.6f}/{qt:.6f} "\n             f"vwap={c / f:.6f}")\n\n\ndef _rev_ladder_advance(exchange, sym: str, w: Dict, open_pos_live: Dict,\n                        assets, now: float) -> None:\n    qty_target = float(w.get("qty_eff") or w["qty"])\n    side = w["side_ccxt"]\n    min_notional = float(getattr(CFG, "MIN_NOTIONAL", 5.0))\n\n    if w.get("ladder") is None:                     # build once\n        qp_qty = float(w["qp"]["qty"]) if w.get("qp") else 0.0\n        recs: List[Dict] = []\n        for i, (off, wt) in enumerate(_lad_levels()):\n            q = max(qty_target * wt - (qp_qty if i == 0 else 0.0), 0.0)\n            q = _snap_qty(exchange, sym, q) if q > 0 else 0.0\n            px = _lad_px(exchange, sym, w, off)\n            if q <= 0:\n                continue\n            if q * px < min_notional and recs:      # too small -> merge into prev\n                recs[-1]["qty"] = _snap_qty(exchange, sym, recs[-1]["qty"] + q)\n                continue\n            recs.append(_lad_new_rec(f"L{i}", px, q))\n        w["ladder"] = recs\n        w["ladder_started"] = True\n        w["ladder_t0"] = now\n        w["ladder_deadline"] = now + float(_cfg3("REV_LADDER_MAX_WAIT_S", 21600.0))\n        log.info(f"[Ladder] {sym} built {len(recs)} levels "\n                 f"{[(r[\'name\'], r[\'px\'], r[\'qty\']) for r in recs]} "\n                 f"qp={qp_qty}")\n        save_reversal_watchers()\n        if not recs and not w.get("qp"):\n            _rev_expire(w, "ladder:no_levels")\n            return\n\n    recs = w["ladder"]\n    pending = [r for r in recs if r["status"] == "new"]\n    if pending and _rate_can_place():\n        bid, ask = _lad_book(exchange, sym)\n        if bid is not None:\n            for r in pending[:3]:\n                _lad_place(exchange, sym, w, r, bid, ask, clamp=True)\n\n    _lad_poll(exchange, sym, _lad_all_recs(w))\n\n    f, c = _lad_totals(w)\n    res = _lad_sync_position(exchange, sym, w, open_pos_live, assets, f, c)\n    if res == "flattened":\n        for r in _lad_all_recs(w):\n            _lad_cancel(exchange, sym, r)\n        _lad_stats(w, "unprotected_flatten")\n        _rev_expire(w, "ladder:unprotected_flatten")\n        return\n\n    allrecs = _lad_all_recs(w)\n    all_done = all(r["status"] == "done" for r in allrecs)\n    if all_done or now >= float(w["ladder_deadline"]):\n        if not all_done:\n            ok = True\n            for r in allrecs:\n                if r["status"] in ("open", "new") and not _lad_cancel(\n                        exchange, sym, r):\n                    ok = False\n            if not ok:\n                return                       # retry next cycle\n            f, c = _lad_totals(w)            # late fills while cancelling\n            _lad_sync_position(exchange, sym, w, open_pos_live, assets, f, c)\n        _lad_finish(exchange, sym, w, open_pos_live,\n                    "complete" if all_done else "deadline")\n\n\ndef _rev_ladder_cleanup(exchange, sym: str, w: Dict,\n                        open_pos_live: Dict) -> bool:\n    """Called before a FILLED/EXPIRED watcher is dropped: no resting order may\n    survive, and an UNCONFIRMED queue-priority fill is flattened."""\n    recs = _lad_all_recs(w)\n    if not recs and not w.get("qp_pos"):\n        return True\n    ok = True\n    for r in recs:\n        if r.get("status") in ("open", "new") and not _lad_cancel(exchange, sym, r):\n            ok = False\n    if not ok:\n        w["cleanup_tries"] = int(w.get("cleanup_tries", 0)) + 1\n        if w["cleanup_tries"] >= 30:\n            log.error(f"[Ladder] {sym} cleanup gave up — resting order may remain")\n            _send_alert("CRITICAL", f"{sym}: ladder cleanup failed, check open orders")\n            return True\n        return False\n    if (w.get("status") == "EXPIRED" and sym in open_pos_live\n            and not w.get("ladder_started")):\n        pos = open_pos_live.get(sym)\n        log.warning(f"[Ladder] {sym} bounce never confirmed — flattening the "\n                    f"queue-priority fill ({w.get(\'reason\')})")\n        if _lad_flatten(exchange, sym, w["action"], float((pos or {}).get("qty", 0.0))):\n            open_pos_live.pop(sym, None)\n            if _REV_STATE_FILE:\n                _lv_save_state(_REV_STATE_FILE, open_pos_live)\n        else:\n            w["cleanup_tries"] = int(w.get("cleanup_tries", 0)) + 1\n            return w["cleanup_tries"] >= 30\n    return True\n\n\n# ═══════════════════════════════════════════════════════════════\n\n\n'

PATCHES = []
def P(name, old, new):
    PATCHES.append((name, old, new))

P("cfg.v3",
  "    UNIVERSE_RETRY_S: float = 600.0\n",
  "    UNIVERSE_RETRY_S: float = 600.0\n"
  "    # ══ [REV-FIX v3] Maker Ladder (Phase 1) - opt-in ══\n"
  "    REV_LADDER_ENABLED: bool = False\n"
  "    REV_LADDER_OFFSETS_SIGMA: tuple = (0.0, 0.3, 0.6)   # levels below target, in sigma_bar*target\n"
  "    REV_LADDER_WEIGHTS: tuple = (0.40, 0.35, 0.25)      # share of qty per level (normalised)\n"
  "    REV_LADDER_QP_PCT: float = 0.05                     # queue-priority order at target (out of L0); 0 = off\n"
  "    REV_LADDER_MAX_WAIT_S: float = 21600.0              # hard stop after the bounce confirms (6h)\n"
  "    REV_LADDER_POLL_S: float = 10.0                     # queue-priority order polling cadence\n"
  "    REV_LADDER_MIN_FILL_RATIO: float = 0.0              # >0: flatten ladders that end below this ratio\n")

P("cli.args",
  '    p.add_argument("--reversal-fill", type=str, default=None,\n'
  '                   choices=["target","close","best"],\n'
  '                   help="Fill price source (default target)")\n',
  '    p.add_argument("--reversal-fill", type=str, default=None,\n'
  '                   choices=["target","close","best"],\n'
  '                   help="Fill price source (default target)")\n'
  '    # ══ [REV-FIX v3] Maker Ladder (Phase 1) ══\n'
  '    p.add_argument("--rev-ladder", action="store_true",\n'
  '                   help="Post-bounce 3-level maker ladder (40/35/25 at mu, mu-0.3s, mu-0.6s) instead of the single marketable limit")\n'
  '    p.add_argument("--rev-ladder-qp", type=float, default=None,\n'
  '                   help="Queue-priority share resting at target from registration (default 0.05, 0=off)")\n'
  '    p.add_argument("--rev-ladder-wait-h", type=float, default=None,\n'
  '                   help="Hours the ladder may rest after the bounce confirms (default 6)")\n')

P("cli.wire",
  '    if getattr(args, "reversal_fill", None) is not None:\n'
  '        CFG.REVERSAL_FILL_AT = str(args.reversal_fill)\n',
  '    if getattr(args, "reversal_fill", None) is not None:\n'
  '        CFG.REVERSAL_FILL_AT = str(args.reversal_fill)\n'
  '    # ══ [REV-FIX v3] Maker Ladder wiring ══\n'
  '    if getattr(args, "rev_ladder", False):\n'
  '        CFG.REV_LADDER_ENABLED = True\n'
  '    if getattr(args, "rev_ladder_qp", None) is not None:\n'
  '        CFG.REV_LADDER_QP_PCT = float(args.rev_ladder_qp)\n'
  '    if getattr(args, "rev_ladder_wait_h", None) is not None:\n'
  '        CFG.REV_LADDER_MAX_WAIT_S = float(args.rev_ladder_wait_h) * 3600.0\n'
  '    if CFG.REV_LADDER_ENABLED:\n'
  '        if not CFG.REVERSAL_CONFIRM_ENABLED:\n'
  '            log.warning("[Ladder] --rev-ladder needs --reversal-confirm; ladder disabled")\n'
  '            CFG.REV_LADDER_ENABLED = False\n'
  '        else:\n'
  '            log.info(f"[Ladder] ENABLED levels={CFG.REV_LADDER_OFFSETS_SIGMA} "\n'
  '                     f"weights={CFG.REV_LADDER_WEIGHTS} qp={CFG.REV_LADDER_QP_PCT} "\n'
  '                     f"wait={CFG.REV_LADDER_MAX_WAIT_S/3600:.1f}h  "\n'
  '                     f"NOTE: backtest does not model the ladder; evaluate ladder_stats_<mode>.csv")\n')

# ladder branch inside the fill engine (replaces the single marketable limit)
P("adv.ladder_branch",
  '    # ── 1) an entry order may exist (possibly after a restart) ──\n'
  '    if w.get("cid"):\n',
  '    if getattr(CFG, "REV_LADDER_ENABLED", False):        # [REV-FIX v3]\n'
  '        return _rev_ladder_advance(exchange, sym, w, open_pos_live, assets, now)\n\n'
  '    # ── 1) an entry order may exist (possibly after a restart) ──\n'
  '    if w.get("cid"):\n')

# reprice compat: compare the marketable price, not the raw best bid/ask
P("adv.reprice_compare",
  '                    elif abs(px - float(w.get("order_px", 0.0))) > 0.0:\n',
  '                    elif abs(_rev_marketable_px(exchange, sym, w, action, side, px, ref_px)\n'
  '                             - float(w.get("order_px", 0.0))) > 0.0:   # [REV-FIX v3]\n')

# fill gate: QP-owned positions / slot reservations
P("ready.gate",
  '    if sym in open_pos_live:\n'
  '        _rev_expire(w, "pos_open")\n'
  '        return\n'
  '    n_infl = sum(1 for s2, w2 in _REVERSAL_WATCHERS.items()\n'
  '                 if s2 != sym and w2.get("status") == "FILLING")\n'
  '    if len(open_pos_live) + n_infl >= int(CFG.MAX_CONCURRENT_ASSETS):\n',
  '    if sym in open_pos_live and not w.get("qp_pos"):     # [REV-FIX v3] QP-owned position is ours\n'
  '        _rev_expire(w, "pos_open")\n'
  '        return\n'
  '    n_infl = _rev_inflight_other(sym, open_pos_live)\n'
  '    if (len(open_pos_live) - (1 if w.get("qp_pos") else 0) + n_infl\n'
  '            >= int(CFG.MAX_CONCURRENT_ASSETS)):\n')

# monitor: cleanup before dropping, QP step for waiting watchers
P("mon.cleanup",
  '            if st in ("FILLED", "EXPIRED"):\n'
  '                _REVERSAL_WATCHERS.pop(sym, None)\n'
  '                dirty = True\n'
  '                continue\n',
  '            if st in ("FILLED", "EXPIRED"):\n'
  '                if _rev_ladder_cleanup(exchange, sym, w, open_pos_live):   # [REV-FIX v3]\n'
  '                    _REVERSAL_WATCHERS.pop(sym, None)\n'
  '                dirty = True\n'
  '                continue\n')

P("mon.qp",
  '            # waiting states — time-based hard expiry (never stuck)\n'
  '            start_ts = float(w["start_ts"])\n',
  '            if getattr(CFG, "REV_LADDER_ENABLED", False):       # [REV-FIX v3]\n'
  '                _rev_qp_step(exchange, sym, w, open_pos_live, assets, now)\n'
  '                if w.get("status") == "EXPIRED":\n'
  '                    dirty = True\n'
  '                    continue\n'
  '            # waiting states — time-based hard expiry (never stuck)\n'
  '            start_ts = float(w["start_ts"])\n')

# restart safety
P("start.known",
  '        known = {str(w.get("cid")) for w in _REVERSAL_WATCHERS.values()\n'
  '                 if w.get("cid")}\n',
  '        known = _rev_known_cids()      # [REV-FIX v3] includes ladder / queue-priority cids\n')

P("start.filling",
  '        if st == "FILLING" and sym in open_pos_live:\n',
  '        if st == "FILLING" and sym in open_pos_live and not w.get("ladder"):\n')

P("v3.block",
  "def run_live(cfg, exchange):\n",
  NEW_V3_BLOCK + "def run_live(cfg, exchange):\n")


def _once(src, old, name):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"[ABORT] anchor '{name}' matched {n} times (expected exactly 1). "
                         f"The file differs from the audited version - nothing was written.")


def apply(src):
    if MARK in src:
        raise SystemExit("[ABORT] file already contains [REV-FIX v3] - nothing to do.")
    for m in ("[REV-FIX v1]", "[REV-FIX v2]"):
        if m not in src:
            raise SystemExit(f"[ABORT] {m} is not applied - apply v1 then v2 first.")
    for name, old, new in PATCHES:
        _once(src, old, name)
    for name, old, new in PATCHES:
        src = src.replace(old, new, 1)
    return src


def _undefined_names(path):
    try:
        import io
        from pyflakes.api import check
        from pyflakes.reporter import Reporter
        o, e = io.StringIO(), io.StringIO()
        check(open(path, encoding="utf-8").read(), path, Reporter(o, e))
        return sorted({l.split("undefined name")[1].strip() for l in o.getvalue().splitlines()
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
    ast.parse(new)
    print(f"[OK] {len(PATCHES)} anchors applied; syntax OK")
    if a.dry_run:
        return
    out = a.src if a.inplace else (a.out or os.path.splitext(a.src)[0] + "_v3.py")
    if a.inplace:
        bak = f"{a.src}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(a.src, bak)
        print(f"[OK] backup -> {bak}")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    py_compile.compile(tmp, doraise=True)
    os.replace(tmp, out)
    print(f"[OK] written -> {out}")
    u0, u1 = _undefined_names(a.src), _undefined_names(out)
    if u0 is not None and u1 is not None:
        print(f"[pyflakes] undefined before: {u0}")
        print(f"[pyflakes] undefined after : {u1}")
        if set(u1) - set(u0):
            print("[WARN] NEW undefined names:", sorted(set(u1) - set(u0)))
            sys.exit(2)


if __name__ == "__main__":
    main()
