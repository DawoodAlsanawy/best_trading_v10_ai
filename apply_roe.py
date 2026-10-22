#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_roe.py  [REV-FIX v4]  - Resting-Option Execution (ROE): the closest live replica of
REVERSAL_FILL_AT="target", plus the backtest-side option-cost estimator.

Requires [REV-FIX v1], [v2] and [v3] already applied.
Usage:
    python apply_roe.py trading_2_live4.py --inplace
    python apply_roe.py trading_2_live4.py --dry-run
Enable at runtime:  --reversal-confirm --rev-roe   (default OFF; the estimator prints at the end of every backtest)
Every anchor must match EXACTLY ONCE or nothing is written.
"""
import argparse, ast, os, py_compile, shutil, sys, time

MARK = "[REV-FIX v4]"
NEW_V4_BLOCK = '# ═══════════════════════════════════════════════════════════════\n# [REV-FIX v4] Resting-Option Execution (ROE) + option-cost estimator\n#\n# WHY: backtest REVERSAL_FILL_AT="target" fills at the TOUCH price but only for\n# touches that later CONFIRM. A live order can only get that price by already\n# resting at target when price touches - i.e. BEFORE the bounce is known.\n# ROE therefore does exactly that, and pays for it explicitly:\n#   register  -> rest a post-only bid at target (front of queue, maker fee)\n#   fill      -> PROVISIONAL position (SL/TP anchored at target, as backtest)\n#   confirm   -> promote to a normal position  (== the backtest trade)\n#   no confirm-> ABORT: flatten at once (== the cost the backtest never pays)\n# roe_stats_<mode>.csv records every outcome; the backtest side prints the\n# expected option cost (R per confirmed trade) with the same rules.\n# ═══════════════════════════════════════════════════════════════\nimport atexit as _atexit4\n\n_LAST_FLATTEN: Dict[str, float] = {}\n\n\ndef _cfg4(name: str, default):\n    return getattr(CFG, name, default)\n\n\ndef _roe_limit_syms() -> int:\n    n = int(_cfg4("REV_ROE_MAX_SYMBOLS", 0))\n    return n if n > 0 else int(CFG.MAX_CONCURRENT_ASSETS)\n\n\n# ───────────────────────── live: statistics ─────────────────────────\ndef _roe_stats_row(w: Dict, outcome: str, exit_px=None) -> None:\n    try:\n        f, c = _lad_totals(w)\n        entry = (c / f) if f > 0 else None\n        qt = float(w.get("qty_eff") or w["qty"])\n        osd = float(w.get("orig_sl_dist") or 0.0)\n        sign = 1.0 if w["action"] == "BUY" else -1.0\n        loss_r = loss_bps = ""\n        if entry and exit_px and osd > 0:\n            loss_r = round((entry - float(exit_px)) * sign / osd, 4)\n            loss_bps = round((entry - float(exit_px)) * sign / entry * 1e4, 2)\n        t_prov = ""\n        if w.get("roe_fill_ts"):\n            t_prov = round(_t_rev.time() - float(w["roe_fill_ts"]), 1)\n        path = f"roe_stats_{CFG.mode}.csv"\n        new = not os.path.exists(path)\n        with open(path, "a", newline="", encoding="utf-8") as fh:\n            wr = _csv3.writer(fh)\n            if new:\n                wr.writerow(["iso", "sym", "action", "target", "qty_target",\n                             "filled", "fill_ratio", "entry", "exit", "outcome",\n                             "loss_R(+=loss)", "loss_bps(+=loss)",\n                             "t_provisional_s", "sig_ts"])\n            wr.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), w["sym"],\n                         w["action"], w["target"], qt, f,\n                         round(f / max(qt, 1e-12), 4),\n                         entry if entry else "", exit_px if exit_px else "",\n                         outcome, loss_r, loss_bps, t_prov, w.get("sig_ts", "")])\n    except Exception as e:\n        log.debug(f"[ROE] stats write failed: {e}")\n\n\ndef _roe_stats_abort(w: Dict, pos: Optional[Dict]) -> None:\n    px = _LAST_FLATTEN.pop(w.get("sym", ""), None)\n    _roe_stats_row(w, f"aborted:{w.get(\'reason\')}", exit_px=px)\n    w["roe_stat_done"] = True\n\n\ndef _roe_cleanup_hook(w: Dict) -> None:\n    """Cleanup start: a watcher that EXPIRED without ever filling."""\n    if (_cfg4("REV_ROE_ENABLED", False) and w.get("qp")\n            and w.get("status") == "EXPIRED" and not w.get("roe_stat_done")):\n        f, _ = _lad_totals(w)\n        if f <= 0:\n            _roe_stats_row(w, f"expired_no_fill:{w.get(\'reason\')}")\n            w["roe_stat_done"] = True\n\n\n# ───────────────────────── live: resting order + provisional position ─────────────────────────\ndef _rev_roe_step(exchange, sym: str, w: Dict, open_pos_live: Dict, assets,\n                  now: float) -> None:\n    if not _cfg4("REV_ROE_ENABLED", False):\n        return\n    qp = w.get("qp")\n    if qp is None:\n        if w.get("qp_tried") or w.get("status") not in ("WAITING_TOUCH",\n                                                       "WAITING_BOUNCE"):\n            return\n        w["qp_tried"] = True\n        frac = float(_cfg4("REV_ROE_FRAC", 1.0))\n        if frac <= 0:\n            return\n        if len(open_pos_live) + _rev_inflight_other(sym, open_pos_live) \\\n                >= _roe_limit_syms():\n            log.debug(f"[ROE] {sym} no free slot for the resting order")\n            return\n        if not _rate_can_place():\n            w["qp_tried"] = False\n            return\n        bid, ask = _lad_book(exchange, sym)\n        if bid is None:\n            w["qp_tried"] = False\n            return\n        tgt = float(w["target"])\n        side = w["side_ccxt"]\n        tick = _rev_tick(exchange, sym) or 0.0\n        off = int(_cfg4("REV_ROE_OFFSET_TICKS", 0)) * tick\n        if side == "buy":\n            px = tgt + off\n            if px >= ask:           # market already at/below target: rest at the bid\n                px = bid\n        else:\n            px = tgt - off\n            if px <= bid:\n                px = ask\n        px = _rev_snap_price(exchange, sym, px, side)\n        q = _snap_qty(exchange, sym, float(w["qty"]) * frac)\n        if q <= 0:\n            return\n        rec = _lad_new_rec("Q", px, q)\n        w["qp"] = rec\n        w["roe_t0"] = now\n        if _lad_place(exchange, sym, w, rec, bid, ask, clamp=False) in (\n                "reject", "fatal"):\n            w["qp"] = None\n        return\n    if qp.get("status") != "open":\n        return\n    _lad_poll(exchange, sym, [qp])                 # every cycle: short naked window\n    f, c = _lad_totals(w)\n    if f <= float(w.get("pos_synced_qty", 0.0)) + 1e-12:\n        return\n    if (sym not in open_pos_live\n            and len(open_pos_live) >= int(CFG.MAX_CONCURRENT_ASSETS)):\n        log.warning(f"[ROE] {sym} filled but all slots are taken — flattening")\n        for r in _lad_all_recs(w):\n            _lad_cancel(exchange, sym, r)\n        f2, _ = _lad_totals(w)\n        _lad_flatten(exchange, sym, w["action"], f2 or f)\n        _roe_stats_row(w, "slot_overflow", exit_px=_LAST_FLATTEN.pop(sym, None))\n        w["roe_stat_done"] = True\n        _rev_expire(w, "roe:slot_overflow")\n        return\n    res = _lad_sync_position(exchange, sym, w, open_pos_live, assets, f, c)\n    if res in ("created", "grown"):\n        w["qp_pos"] = True\n        w.setdefault("roe_fill_ts", now)\n        pos = open_pos_live.get(sym)\n        if pos is not None and not w.get("roe_confirmed"):\n            pos["_provisional"] = True\n            if _REV_STATE_FILE:\n                _lv_save_state(_REV_STATE_FILE, open_pos_live)\n        log.info(f"[ROE] {sym} PROVISIONAL position @ {c / f:.6f} "\n                 f"(target {w[\'target\']:.6f}) — awaiting bounce")\n    elif res == "flattened":\n        w["qp_pos"] = False\n        w["roe_stat_done"] = True\n        _rev_expire(w, "roe:unprotected")\n\n\ndef _rev_roe_on_ready(exchange, sym: str, w: Dict, open_pos_live: Dict, assets,\n                      now: float) -> str:\n    """Bounce confirmed. Returns \'handled\' | \'pass\' (fall through to the\n    normal marketable fill)."""\n    if not _cfg4("REV_ROE_ENABLED", False):\n        return "pass"\n    for r in _lad_all_recs(w):                       # remainder can no longer fill at target\n        if r.get("status") in ("open", "new") and not _lad_cancel(exchange, sym, r):\n            return "handled"                         # retry next cycle (stay READY)\n    f, c = _lad_totals(w)\n    if f > 0:\n        res = _lad_sync_position(exchange, sym, w, open_pos_live, assets, f, c)\n        if res == "flattened":\n            w["roe_stat_done"] = True\n            _rev_expire(w, "roe:unprotected")\n            return "handled"\n        pos = open_pos_live.get(sym)\n        if pos is not None:\n            pos["_provisional"] = False\n            if _REV_STATE_FILE:\n                _lv_save_state(_REV_STATE_FILE, open_pos_live)\n        w["roe_confirmed"] = True\n        w["entry"] = c / f\n        _roe_stats_row(w, "confirmed")\n        w["roe_stat_done"] = True\n        w["status"] = "FILLED"\n        log.info(f"✅ [ROE] {sym} CONFIRMED @ {c / f:.6f} "\n                 f"(target {w[\'target\']:.6f}) qty={f:.6f}")\n        return "handled"\n    _roe_stats_row(w, "confirmed_no_fill")\n    w["roe_stat_done"] = True\n    if str(_cfg4("REV_ROE_FALLBACK", "skip")) == "marketable":\n        w["qp"] = None                               # normal marketable path takes over\n        return "pass"\n    _rev_expire(w, "roe:no_fill_skip")\n    return "handled"\n\n\n# ───────────────────────── backtest: option-cost estimator ─────────────────────────\n_ROE_BT: Dict = {"n": 0, "no_touch": 0, "touched": 0, "confirmed": 0,\n                 "aborted": 0, "ab_window": 0, "ab_fastfail": 0, "ab_sl": 0,\n                 "loss_R": 0.0, "fee_R": 0.0, "lost_by_fastfail": 0,\n                 "prov_dd_R": 0.0, "prov_dd_n": 0, "prov_dd_ge1": 0}\n\n\ndef _roe_bt_account(ad, sig, target0, cfg, first_main_ci, deadline_main_ci,\n                    res) -> None:\n    """Pure bookkeeping (never changes a backtest decision): for every touch\n    that does NOT confirm, what would the ROE abort have cost - same rules\n    the live ROE uses."""\n    if ad.sub_highs is None or ad.sub_closes is None or ad.sub_per_main < 2:\n        return\n    action = sig.action\n    sub_pm = int(ad.sub_per_main)\n    start_main = sig.close_idx + 1\n    end_main = min(deadline_main_ci, ad.sub_highs.shape[0])\n    if end_main <= start_main:\n        return\n    sh = ad.sub_highs[start_main:end_main].reshape(-1)\n    sl = ad.sub_lows[start_main:end_main].reshape(-1)\n    sc = ad.sub_closes[start_main:end_main].reshape(-1)\n    n = sh.size\n    if n == 0:\n        return\n    tw = max(1, int(getattr(cfg, "REVERSAL_TOUCH_SUBBARS", 20)))\n    bw = max(1, int(getattr(cfg, "REVERSAL_BOUNCE_SUBBARS", 4)))\n    S = _ROE_BT\n    S["n"] += 1\n    tk = -1\n    for k in range(min(tw, n)):\n        if not np.isfinite(sl[k]) or not np.isfinite(sh[k]):\n            continue\n        if (action == "BUY" and sl[k] <= target0) or (\n                action == "SELL" and sh[k] >= target0):\n            tk = k\n            break\n    if tk < 0:\n        S["no_touch"] += 1\n        return\n    sl_dist = abs(float(sig.price) - float(sig.sl))\n    if sl_dist <= 0 or tk + 1 >= n:\n        return\n    S["touched"] += 1\n    sign = 1.0 if action == "BUY" else -1.0\n    sigma_bar = 0.01\n    try:\n        fi = int(sig.feat_idx)\n        if 0 <= fi < len(ad.E_therm):\n            _s = float(ad.E_therm[fi])\n            if np.isfinite(_s) and _s > 1e-9:\n                sigma_bar = _s\n    except Exception:\n        pass\n    kappa = float(getattr(cfg, "REV_ABORT_KAPPA", 1.0))\n    brk = target0 - sign * kappa * sigma_bar * target0     # fast-fail level\n\n    def _broken(c):\n        return (c < brk) if action == "BUY" else (c > brk)\n\n    if res is not None:                                    # CONFIRMED trade\n        S["confirmed"] += 1\n        try:\n            ek = (int(res[0]) - start_main) * sub_pm + int(\n                _REV_ENTRY_SUB.get((str(sig.symbol), int(sig.close_idx)), 0))\n        except Exception:\n            ek = tk + 1\n        ek = max(min(ek, n - 1), tk + 1)\n        seg_low = sl[tk:ek + 1] if action == "BUY" else sh[tk:ek + 1]\n        seg_low = seg_low[np.isfinite(seg_low)]\n        if seg_low.size:\n            exc = ((target0 - float(seg_low.min())) if action == "BUY"\n                   else (float(seg_low.max()) - target0)) / sl_dist\n            exc = max(exc, 0.0)\n            S["prov_dd_R"] += exc\n            S["prov_dd_n"] += 1\n            S["prov_dd_ge1"] += 1 if exc >= 1.0 else 0\n        for k in range(tk + 1, ek + 1):                    # winners the fast-fail would kill\n            if np.isfinite(sc[k]) and _broken(sc[k]):\n                S["lost_by_fastfail"] += 1\n                break\n        return\n    k_end = min(tk + bw, n - 1)                            # window ends after bar tk+bw\n    if k_end <= tk:\n        return\n    exit_k, why = k_end, "window"\n    for k in range(tk + 1, k_end + 1):\n        if np.isfinite(sc[k]) and _broken(sc[k]):\n            exit_k, why = k, "fastfail"\n            break\n    sl_px = target0 - sign * sl_dist\n    exit_px = float(sc[exit_k])\n    for k in range(tk, exit_k + 1):\n        lo = sl[k] if action == "BUY" else sh[k]\n        if np.isfinite(lo) and ((action == "BUY" and lo <= sl_px)\n                                or (action == "SELL" and lo >= sl_px)):\n            exit_px, why = sl_px, "sl"\n            break\n    if not np.isfinite(exit_px):\n        return\n    loss = (target0 - exit_px) * sign                      # >0 = loss\n    S["aborted"] += 1\n    S["ab_" + ("fastfail" if why == "fastfail" else "sl" if why == "sl" else "window")] += 1\n    S["loss_R"] += loss / sl_dist\n    fee = (abs(float(getattr(CFG, "MAKER_FEE", 0.0002)))\n           + float(getattr(CFG, "TAKER_FEE", 0.0005))) * target0\n    S["fee_R"] += fee / sl_dist\n\n\ndef _roe_bt_report() -> None:\n    S = _ROE_BT\n    if S["n"] <= 0 or not getattr(CFG, "REV_OPT_REPORT", True):\n        return\n    t, cf, ab = S["touched"], S["confirmed"], S["aborted"]\n    pc = cf / t * 100 if t else 0.0\n    cost = S["loss_R"] + S["fee_R"]\n    per_conf = cost / cf if cf else float("nan")\n    pdn = max(S["prov_dd_n"], 1)\n    print("\\n" + "═" * 70)\n    print("[ROE-Estimator] cost of obtaining the TARGET price live "\n          "(resting order + abort)")\n    print(f"  signals={S[\'n\']}  touched={t} ({t / S[\'n\'] * 100:.1f}%)  "\n          f"confirmed={cf} (p_confirm={pc:.1f}%)  aborted={ab}")\n    print(f"  aborts: window={S[\'ab_window\']}  fast-fail={S[\'ab_fastfail\']}  "\n          f"sl={S[\'ab_sl\']}")\n    print(f"  abort loss = {S[\'loss_R\']:.2f}R  fees = {S[\'fee_R\']:.2f}R  "\n          f"=> option cost = {cost:.2f}R  = {per_conf:.3f}R per CONFIRMED trade")\n    print(f"  => the backtest\'s average R per trade must EXCEED "\n          f"{per_conf:.3f}R for the target-fill result to survive live")\n    print(f"  winners the fast-fail would have killed: {S[\'lost_by_fastfail\']}  |  "\n          f"provisional adverse excursion before confirm: "\n          f"avg {S[\'prov_dd_R\'] / pdn:.2f}R, >=1R in {S[\'prov_dd_ge1\']} trades")\n    print("═" * 70 + "\\n")\n\n\n_atexit4.register(_roe_bt_report)\n\n\n# ═══════════════════════════════════════════════════════════════\n\n\n'

PATCHES = []
def P(name, old, new):
    PATCHES.append((name, old, new))

P("cfg.v4",
  "    REV_LADDER_MIN_FILL_RATIO: float = 0.0              # >0: flatten ladders that end below this ratio\n",
  "    REV_LADDER_MIN_FILL_RATIO: float = 0.0              # >0: flatten ladders that end below this ratio\n"
  "    # ══ [REV-FIX v4] Resting-Option Execution (ROE) ══\n"
  "    REV_ROE_ENABLED: bool = False\n"
  "    REV_ROE_FRAC: float = 1.0                 # share of the size resting at target before the touch (1.0 = full replica)\n"
  "    REV_ROE_OFFSET_TICKS: int = 0             # >0: rest N ticks ABOVE target (BUY) for a higher fill probability\n"
  "    REV_ROE_FALLBACK: str = \"skip\"            # bounce confirmed but nothing filled: skip | marketable\n"
  "    REV_ROE_MAX_SYMBOLS: int = 0              # symbols that may rest/hold provisional exposure (0 = MAX_CONCURRENT_ASSETS)\n"
  "    REV_ABORT_KAPPA: float = 1.0              # abort level: close beyond target -/+ kappa*sigma_bar*target (live + estimator)\n"
  "    REV_OPT_STATS: bool = True                # backtest: account the option cost per touched signal\n"
  "    REV_OPT_REPORT: bool = True               # backtest: print the estimator at exit\n")

P("cli.args",
  '    p.add_argument("--rev-ladder-wait-h", type=float, default=None,\n'
  '                   help="Hours the ladder may rest after the bounce confirms (default 6)")\n',
  '    p.add_argument("--rev-ladder-wait-h", type=float, default=None,\n'
  '                   help="Hours the ladder may rest after the bounce confirms (default 6)")\n'
  '    # ══ [REV-FIX v4] Resting-Option Execution ══\n'
  '    p.add_argument("--rev-roe", action="store_true",\n'
  '                   help="Rest a post-only bid AT target before the touch; provisional position; abort if the bounce never confirms")\n'
  '    p.add_argument("--rev-roe-frac", type=float, default=None,\n'
  '                   help="Share of the size resting at target pre-touch (default 1.0)")\n'
  '    p.add_argument("--rev-roe-offset-ticks", type=int, default=None,\n'
  '                   help="Rest N ticks above target (BUY) for a higher fill probability (default 0)")\n'
  '    p.add_argument("--rev-roe-fallback", type=str, default=None, choices=["skip", "marketable"],\n'
  '                   help="Bounce confirmed but the resting order never filled (default skip)")\n'
  '    p.add_argument("--rev-roe-max-symbols", type=int, default=None,\n'
  '                   help="Symbols allowed to rest/hold provisional exposure (default = --maxcon)")\n'
  '    p.add_argument("--rev-abort-kappa", type=float, default=None,\n'
  '                   help="Abort level in sigma_bar*target beyond target (default 1.0; also used by the estimator)")\n')

P("cli.wire",
  '            log.info(f"[Ladder] ENABLED levels={CFG.REV_LADDER_OFFSETS_SIGMA} "\n'
  '                     f"weights={CFG.REV_LADDER_WEIGHTS} qp={CFG.REV_LADDER_QP_PCT} "\n'
  '                     f"wait={CFG.REV_LADDER_MAX_WAIT_S/3600:.1f}h  "\n'
  '                     f"NOTE: backtest does not model the ladder; evaluate ladder_stats_<mode>.csv")\n',
  '            log.info(f"[Ladder] ENABLED levels={CFG.REV_LADDER_OFFSETS_SIGMA} "\n'
  '                     f"weights={CFG.REV_LADDER_WEIGHTS} qp={CFG.REV_LADDER_QP_PCT} "\n'
  '                     f"wait={CFG.REV_LADDER_MAX_WAIT_S/3600:.1f}h  "\n'
  '                     f"NOTE: backtest does not model the ladder; evaluate ladder_stats_<mode>.csv")\n'
  '    # ══ [REV-FIX v4] ROE wiring ══\n'
  '    if getattr(args, "rev_roe", False):\n'
  '        CFG.REV_ROE_ENABLED = True\n'
  '    if getattr(args, "rev_roe_frac", None) is not None:\n'
  '        CFG.REV_ROE_FRAC = float(args.rev_roe_frac)\n'
  '    if getattr(args, "rev_roe_offset_ticks", None) is not None:\n'
  '        CFG.REV_ROE_OFFSET_TICKS = int(args.rev_roe_offset_ticks)\n'
  '    if getattr(args, "rev_roe_fallback", None) is not None:\n'
  '        CFG.REV_ROE_FALLBACK = str(args.rev_roe_fallback)\n'
  '    if getattr(args, "rev_roe_max_symbols", None) is not None:\n'
  '        CFG.REV_ROE_MAX_SYMBOLS = int(args.rev_roe_max_symbols)\n'
  '    if getattr(args, "rev_abort_kappa", None) is not None:\n'
  '        CFG.REV_ABORT_KAPPA = float(args.rev_abort_kappa)\n'
  '    if CFG.REV_ROE_ENABLED:\n'
  '        if not CFG.REVERSAL_CONFIRM_ENABLED:\n'
  '            log.warning("[ROE] --rev-roe needs --reversal-confirm; ROE disabled")\n'
  '            CFG.REV_ROE_ENABLED = False\n'
  '        else:\n'
  '            if CFG.REV_LADDER_ENABLED:\n'
  '                log.warning("[ROE] ROE and the ladder are mutually exclusive: ladder disabled")\n'
  '                CFG.REV_LADDER_ENABLED = False\n'
  '            log.info(f"[ROE] ENABLED frac={CFG.REV_ROE_FRAC} offset={CFG.REV_ROE_OFFSET_TICKS}tk "\n'
  '                     f"fallback={CFG.REV_ROE_FALLBACK} abort_kappa={CFG.REV_ABORT_KAPPA} "\n'
  '                     f"max_symbols={CFG.REV_ROE_MAX_SYMBOLS or CFG.MAX_CONCURRENT_ASSETS}  "\n'
  '                     f"NOTE: unconfirmed touches are flattened - see roe_stats_<mode>.csv")\n')

P("scan.kappa",
  "            escape_dist = sigma_bar * target_px * 1.0 # معامل k=1.0 كما ناقشنا\n",
  "            escape_dist = sigma_bar * target_px * float(getattr(CFG, 'REV_ABORT_KAPPA', 1.0))  # [REV-FIX v4]\n")

P("mon.roe",
  '            if getattr(CFG, "REV_LADDER_ENABLED", False):       # [REV-FIX v3]\n'
  '                _rev_qp_step(exchange, sym, w, open_pos_live, assets, now)\n'
  '                if w.get("status") == "EXPIRED":\n'
  '                    dirty = True\n'
  '                    continue\n',
  '            if getattr(CFG, "REV_ROE_ENABLED", False):          # [REV-FIX v4]\n'
  '                _rev_roe_step(exchange, sym, w, open_pos_live, assets, now)\n'
  '                if w.get("status") == "EXPIRED":\n'
  '                    dirty = True\n'
  '                    continue\n'
  '            elif getattr(CFG, "REV_LADDER_ENABLED", False):     # [REV-FIX v3]\n'
  '                _rev_qp_step(exchange, sym, w, open_pos_live, assets, now)\n'
  '                if w.get("status") == "EXPIRED":\n'
  '                    dirty = True\n'
  '                    continue\n')

P("ready.roe",
  'def _rev_handle_ready(exchange, sym: str, w: Dict, open_pos_live: Dict,\n'
  '                      now: float, sub_sec: int, cap_now, corr_cache) -> None:\n'
  '    max_age = float(_revc("REV_MAX_CONFIRM_AGE_SUBBARS", 2)) * sub_sec\n',
  'def _rev_handle_ready(exchange, sym: str, w: Dict, open_pos_live: Dict,\n'
  '                      now: float, sub_sec: int, cap_now, corr_cache) -> None:\n'
  '    if getattr(CFG, "REV_ROE_ENABLED", False):            # [REV-FIX v4] before the stale/slot gates:\n'
  '        if _rev_roe_on_ready(exchange, sym, w, open_pos_live, None, now) == "handled":\n'
  '            return                                         # a provisional position must never be dropped as stale\n'
  '    max_age = float(_revc("REV_MAX_CONFIRM_AGE_SUBBARS", 2)) * sub_sec\n')

P("cleanup.hook",
  '    if not recs and not w.get("qp_pos"):\n'
  '        return True\n'
  '    ok = True\n',
  '    if not recs and not w.get("qp_pos"):\n'
  '        return True\n'
  '    _roe_cleanup_hook(w)                                  # [REV-FIX v4] stats for never-filled expiries\n'
  '    ok = True\n')

P("cleanup.cond",
  '    if (w.get("status") == "EXPIRED" and sym in open_pos_live\n'
  '            and not w.get("ladder_started")):\n',
  '    if (w.get("status") == "EXPIRED" and sym in open_pos_live\n'
  '            and w.get("qp_pos") and not w.get("ladder_started")):   # [REV-FIX v4] only OUR provisional fill\n')

P("cleanup.stats",
  '        if _lad_flatten(exchange, sym, w["action"], float((pos or {}).get("qty", 0.0))):\n'
  '            open_pos_live.pop(sym, None)\n',
  '        if _lad_flatten(exchange, sym, w["action"], float((pos or {}).get("qty", 0.0))):\n'
  '            open_pos_live.pop(sym, None)\n'
  '            _roe_stats_abort(w, pos)                       # [REV-FIX v4] what the abort cost\n')

P("flatten.capture",
  '    try:\n'
  '        _rev_api(exchange.create_order, sym, "market",\n'
  '                 "sell" if action == "BUY" else "buy",\n'
  '                 _snap_qty(exchange, sym, qty) or qty, None,\n'
  '                 params={"reduceOnly": True})\n'
  '    except Exception as e:\n'
  '        log.error(f"[Ladder] {sym} flatten FAILED: {e}")\n'
  '        return False\n',
  '    try:\n'
  '        _fo = _rev_api(exchange.create_order, sym, "market",\n'
  '                       "sell" if action == "BUY" else "buy",\n'
  '                       _snap_qty(exchange, sym, qty) or qty, None,\n'
  '                       params={"reduceOnly": True})\n'
  '        try:                                               # [REV-FIX v4] exit price for the stats\n'
  '            _fp = float((_fo or {}).get("average") or (_fo or {}).get("price") or 0.0)\n'
  '            if _fp > 0:\n'
  '                _LAST_FLATTEN[sym] = _fp\n'
  '        except Exception:\n'
  '            pass\n'
  '    except Exception as e:\n'
  '        log.error(f"[Ladder] {sym} flatten FAILED: {e}")\n'
  '        return False\n')

P("start.expired_keep",
  '        if legacy or st in ("FILLED", "EXPIRED"):\n'
  '            _REVERSAL_WATCHERS.pop(sym, None)\n'
  '            dropped += 1\n'
  '            continue\n',
  '        if legacy or (st in ("FILLED", "EXPIRED")\n'
  '                      and not (st == "EXPIRED" and w.get("qp"))):   # [REV-FIX v4] cleanup still owed\n'
  '            _REVERSAL_WATCHERS.pop(sym, None)\n'
  '            dropped += 1\n'
  '            continue\n')

P("start.window_over",
  '        if st in ("WAITING_TOUCH", "WAITING_BOUNCE") \\\n'
  '                and now > float(w.get("expire_ts", 0.0)):\n'
  '            _REVERSAL_WATCHERS.pop(sym, None)\n'
  '            dropped += 1\n'
  '            continue\n',
  '        if st in ("WAITING_TOUCH", "WAITING_BOUNCE") \\\n'
  '                and now > float(w.get("expire_ts", 0.0)):\n'
  '            if w.get("qp"):                                # [REV-FIX v4] resting order / provisional position\n'
  '                _rev_expire(w, "restart_window_over")      # -> monitor cleanup cancels / flattens\n'
  '            else:\n'
  '                _REVERSAL_WATCHERS.pop(sym, None)\n'
  '                dropped += 1\n'
  '            continue\n')

P("bt.wrapper",
  '    _REV_ENTRY_SUB[(str(sig.symbol), int(sig.close_idx))] = int(_entry_sub)\n'
  '    return (int(confirm_main), float(fill_px))\n',
  '    _REV_ENTRY_SUB[(str(sig.symbol), int(sig.close_idx))] = int(_entry_sub)\n'
  '    return (int(confirm_main), float(fill_px))\n'
  '\n\n'
  '# <<REV-FIX v4 wrapper>>\n'
  '_check_reversal_fill_subbars_core = _check_reversal_fill_subbars\n'
  '\n\n'
  'def _check_reversal_fill_subbars(ad, sig, target0, cfg,\n'
  '                                 first_main_ci, deadline_main_ci):\n'
  '    """Same decisions as the core function; additionally accounts the cost of the\n'
  '    touches that would NOT confirm (the price of getting the target fill live)."""\n'
  '    res = _check_reversal_fill_subbars_core(ad, sig, target0, cfg,\n'
  '                                            first_main_ci, deadline_main_ci)\n'
  '    if getattr(cfg, "REV_OPT_STATS", True):\n'
  '        try:\n'
  '            _roe_bt_account(ad, sig, target0, cfg, first_main_ci,\n'
  '                            deadline_main_ci, res)\n'
  '        except Exception:\n'
  '            pass\n'
  '    return res\n'
  '# <</REV-FIX v4 wrapper>>\n')

P("v4.block",
  "def run_live(cfg, exchange):\n",
  NEW_V4_BLOCK + "def run_live(cfg, exchange):\n")


def _once(src, old, name):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"[ABORT] anchor '{name}' matched {n} times (expected exactly 1). "
                         f"The file differs from the audited version - nothing was written.")


def apply(src):
    if MARK in src:
        raise SystemExit("[ABORT] file already contains [REV-FIX v4] - nothing to do.")
    for m in ("[REV-FIX v1]", "[REV-FIX v2]", "[REV-FIX v3]"):
        if m not in src:
            raise SystemExit(f"[ABORT] {m} is not applied - apply v1, v2, v3 first.")
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
    out = a.src if a.inplace else (a.out or os.path.splitext(a.src)[0] + "_v4.py")
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
