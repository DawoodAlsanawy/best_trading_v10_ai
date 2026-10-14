#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_longrun_fixes.py  [REV-FIX v2]  - long-run hardening (items 1-8)

Requires [REV-FIX v1] to be applied already.
Usage:
    python apply_longrun_fixes.py trading_2_live4.py              # -> trading_2_live4_v2.py
    python apply_longrun_fixes.py trading_2_live4.py --inplace    # backup + overwrite
    python apply_longrun_fixes.py trading_2_live4.py --dry-run

Every anchor must match EXACTLY ONCE or nothing is written.
"""
import argparse, ast, os, py_compile, shutil, sys, time

MARK = "[REV-FIX v2]"
NEW_V2_BLOCK = '# ═══════════════════════════════════════════════════════════════\n# [REV-FIX v2] Long-run hardening\n#   1 loop-error escalation + heartbeat + alerts   5 degenerate-ban TTL\n#   2 periodic time sync (+ -1021 recovery)        6 rotating logs (module top)\n#   3 no multi-minute blackouts (keepalive +       7 write-only-if-changed JSON\n#     background universe refresh)                 8 gap-aware candle refresh\n#   4 periodic markets reload\n# ═══════════════════════════════════════════════════════════════\nimport threading as _th2\nimport traceback as _tb2\nimport urllib.request as _ur2\nimport hashlib as _hl2\n\n_LOOP_ERR: Dict = {"streak": 0, "total": 0, "last": "", "last_ts": 0.0,\n                   "alerted": False}\n_HK: Dict = {"tsync": time.time(), "mkts": time.time(), "hb": 0.0}\n_GAP_BUDGET: Dict = {"n": 0}\n_GAP_ATTEMPTED: set = set()\n_DEGENERATE_BAN_UNTIL: Dict[str, float] = {}\n_JSON_LAST: Dict[str, Tuple[str, float]] = {}\n_KEEPALIVE_LAST: Dict = {"t": 0.0}\n\n\ndef _cfg2(name: str, default):\n    return getattr(CFG, name, default)\n\n\n# ───────────────────────── 7) JSON: write only if changed ─────────────────────────\ndef _json_write_if_changed(path: str, obj, indent: int = 2,\n                           fsync: bool = False) -> bool:\n    """Atomic write that is skipped when the serialized content is unchanged\n    (a forced rewrite still happens every JSON_FORCE_WRITE_S seconds)."""\n    s = json.dumps(obj, indent=indent, default=str)\n    h = _hl2.md5(s.encode("utf-8")).hexdigest()\n    now = time.time()\n    force = float(_cfg2("JSON_FORCE_WRITE_S", 300.0))\n    last = _JSON_LAST.get(path)\n    if (last is not None and last[0] == h and now - last[1] < force\n            and os.path.exists(path)):\n        return False\n    tmp = f"{path}.tmp"\n    with open(tmp, "w") as f:\n        f.write(s)\n        f.flush()\n        if fsync:\n            try:\n                os.fsync(f.fileno())\n            except Exception:\n                pass\n    os.replace(tmp, path)\n    _JSON_LAST[path] = (h, now)\n    return True\n\n\n# ───────────────────────── 1) alerts / heartbeat / loop errors ─────────────────────────\ndef _send_alert(level: str, msg: str) -> None:\n    line = f"{time.strftime(\'%Y-%m-%d %H:%M:%S\')} [{level}] {msg}"\n    try:\n        with open(f"alerts_{CFG.mode}.log", "a", encoding="utf-8") as f:\n            f.write(line + "\\n")\n    except Exception:\n        pass\n    url = os.environ.get("QTT_ALERT_WEBHOOK", "").strip()\n    if not url:\n        return\n\n    def _post():\n        try:\n            data = json.dumps({"text": line}).encode("utf-8")\n            req = _ur2.Request(url, data=data,\n                               headers={"Content-Type": "application/json"})\n            _ur2.urlopen(req, timeout=5).read()\n        except Exception as e:\n            log.debug(f"[Alert] webhook failed: {e}")\n    _th2.Thread(target=_post, daemon=True, name="alert-post").start()\n\n\ndef _heartbeat(extra: Optional[Dict] = None, force: bool = False) -> None:\n    now = time.time()\n    if not force and now - _HK["hb"] < float(_cfg2("HEARTBEAT_EVERY_S", 10.0)):\n        return\n    _HK["hb"] = now\n    payload = {"ts": now, "iso": time.strftime("%Y-%m-%d %H:%M:%S"),\n               "pid": os.getpid(), "err_streak": _LOOP_ERR["streak"],\n               "err_total": _LOOP_ERR["total"], "last_error": _LOOP_ERR["last"]}\n    if extra:\n        payload.update(extra)\n    try:\n        path = f"heartbeat_{CFG.mode}.json"\n        tmp = path + ".tmp"\n        with open(tmp, "w") as f:\n            json.dump(payload, f, default=str)\n        os.replace(tmp, path)\n    except Exception:\n        pass\n\n\ndef _loop_ok(loop_iter: int, open_pos_live: Optional[Dict] = None) -> None:\n    recovered = _LOOP_ERR["streak"] > 0\n    _LOOP_ERR["streak"] = 0\n    _LOOP_ERR["alerted"] = False\n    if recovered:\n        log.info("[LoopError] recovered — loop cycle completed normally")\n    _heartbeat({"state": "ok", "loop_iter": int(loop_iter),\n                "open_positions": len(open_pos_live or {}),\n                "watchers": len(_REVERSAL_WATCHERS)}, force=recovered)\n\n\ndef _loop_error_handler(exchange, e: Exception, open_pos_live=None,\n                        state_file=None) -> None:\n    """Called from the main-loop except block. Escalates persistent errors:\n    full traceback at ERROR, alert, then (optionally) exit non-zero so a\n    supervisor restarts the bot instead of it idling silently."""\n    st = _LOOP_ERR\n    now = time.time()\n    if now - st["last_ts"] > float(_cfg2("LOOP_ERR_RESET_AFTER_S", 900.0)):\n        st["streak"] = 0\n        st["alerted"] = False\n    st["streak"] += 1\n    st["total"] += 1\n    st["last"] = f"{type(e).__name__}: {e}"[:300]\n    st["last_ts"] = now\n    n = st["streak"]\n    msg = str(e)\n    if ("-1021" in msg or "recvWindow" in msg\n            or "Timestamp for this request" in msg):\n        _time_resync(exchange, "error -1021")\n    if n <= 3 or n % 10 == 0:\n        log.error(f"[LoopError #{n}] {st[\'last\']}\\n{_tb2.format_exc()}")\n    else:\n        log.error(f"[LoopError #{n}] {st[\'last\']}")\n    warn_at = int(_cfg2("LOOP_WARN_ERRORS", 5))\n    max_n = int(_cfg2("LOOP_MAX_CONSEC_ERRORS", 30))\n    if n >= warn_at and not st["alerted"]:\n        st["alerted"] = True\n        _send_alert("WARN", f"{n} consecutive loop errors: {st[\'last\']}")\n    _heartbeat({"state": "error"}, force=True)\n    if n >= max_n:\n        _send_alert("CRITICAL",\n                    f"{n} consecutive loop errors — giving up: {st[\'last\']}")\n        try:\n            if state_file is not None and open_pos_live is not None:\n                _lv_save_state(state_file, open_pos_live)\n        except Exception:\n            pass\n        if _cfg2("LOOP_EXIT_ON_ERRORS", True):\n            log.critical("[LoopError] exiting (code 3) so the supervisor can "\n                         "restart; exchange-side SL/TP orders remain active")\n            raise SystemExit(3)\n\n\n# ───────────────────────── 2) time sync / 4) markets / housekeeping ─────────────────────────\ndef _time_resync(exchange, reason: str = "periodic") -> None:\n    try:\n        if hasattr(exchange, "load_time_difference"):\n            exchange.load_time_difference()\n        td = (getattr(exchange, "options", None) or {}).get("timeDifference")\n        log.info(f"[TimeSync] resync ({reason}) timeDifference={td}ms")\n    except Exception as e:\n        log.warning(f"[TimeSync] resync failed ({reason}): {e}")\n    try:\n        _check_time_sync(exchange, float(_cfg2("TIMESYNC_WARN_DRIFT_S", 5.0)))\n    except Exception:\n        pass\n\n\ndef _refresh_markets(exchange, open_pos_live=None) -> None:\n    try:\n        before = set((getattr(exchange, "markets", None) or {}).keys())\n        exchange.load_markets(True)\n        mk = exchange.markets or {}\n        after = set(mk.keys())\n        _TICK_SIZE_CACHE.clear()\n        _MMR_CACHE.clear()\n        _SYMBOL_LEV_TIERS.clear()\n        log.info(f"[Markets] reloaded: {len(after)} markets "\n                 f"(+{len(after - before)} / -{len(before - after)}); "\n                 f"tick/MMR/leverage caches cleared")\n        for s in list(open_pos_live or {}):\n            m = mk.get(s)\n            if m is None or m.get("active") is False:\n                log.error(f"[Markets] held symbol {s} is delisted/inactive")\n                _send_alert("CRITICAL", f"held symbol {s} delisted/inactive")\n    except Exception as e:\n        log.warning(f"[Markets] reload failed: {e}")\n\n\ndef _live_housekeeping(exchange, open_pos_live=None) -> None:\n    now = time.time()\n    _GAP_BUDGET["n"] = 0\n    if now - _HK["tsync"] >= float(_cfg2("TIMESYNC_EVERY_S", 3600.0)):\n        _HK["tsync"] = now\n        _time_resync(exchange, "periodic")\n    if now - _HK["mkts"] >= float(_cfg2("MARKETS_REFRESH_S", 21600.0)):\n        _HK["mkts"] = now\n        _refresh_markets(exchange, open_pos_live)\n\n\n# ───────────────────────── 5) degenerate-symbol ban with TTL ─────────────────────────\ndef _degenerate_banned(sym: str) -> bool:\n    until = _DEGENERATE_BAN_UNTIL.get(sym)\n    if until is not None:\n        if time.time() >= until:\n            _DEGENERATE_BAN_UNTIL.pop(sym, None)\n            _DEGENERATE_STREAK.pop(sym, None)\n            log.info(f"[Degenerate-Ban] {sym} ban expired — retrying")\n            return False\n        return True\n    if _DEGENERATE_STREAK.get(sym, 0) >= _DEGENERATE_BAN_THRESHOLD:\n        _DEGENERATE_BAN_UNTIL[sym] = time.time() + float(\n            _cfg2("DEGENERATE_BAN_TTL_S", 86400.0))\n        return True\n    return False\n\n\n# ───────────────────────── 8) gap-aware candle refresh ─────────────────────────\n_OHLCV_COLS = ["ts", "Open", "High", "Low", "Close", "Volume"]\n\n\ndef _live_fetch_candles(exchange, sym: str, tf: str, df, tf_sec: int):\n    """Normally the last 3 candles (unchanged behaviour). If bars were missed\n    (outage / blocked loop) fetch everything since the last cached bar."""\n    now = time.time()\n    limit, since = 3, None\n    try:\n        if df is not None and len(df):\n            last_ts = float(df.index[-1].timestamp())\n            missing = int((now - last_ts) // max(int(tf_sec), 1)) + 2\n            if missing > 3:\n                limit = int(min(missing, int(_cfg2("LIVE_FETCH_MAX_BARS", 1000))))\n                since = int(last_ts * 1000)\n    except Exception:\n        limit, since = 3, None\n    try:\n        _rate_record(1.0 if limit < 100 else (2.0 if limit < 500 else 5.0))\n    except Exception:\n        pass\n    if since is None:\n        return exchange.fetch_ohlcv(sym, tf, limit=limit)\n    return exchange.fetch_ohlcv(sym, tf, since, limit)\n\n\ndef _find_first_gap(df, tf_sec: int, lookback: int):\n    """Open-time (epoch s) of the last bar BEFORE the first gap, or None."""\n    if df is None or len(df) < 3:\n        return None\n    idx = df.index[-int(lookback):]\n    d = idx.to_series().diff().dt.total_seconds().to_numpy()[1:]\n    bad = np.nonzero(d > 1.5 * float(tf_sec))[0]\n    if len(bad) == 0:\n        return None\n    return float(idx[int(bad[0])].timestamp())\n\n\ndef _live_heal_gaps(exchange, sym: str, tf: str, df, tf_sec: int):\n    if (not _cfg2("LIVE_GAP_HEAL_ENABLED", True) or df is None or len(df) < 3):\n        return df\n    if _GAP_BUDGET["n"] >= int(_cfg2("LIVE_GAP_HEAL_PER_CYCLE", 5)):\n        return df\n    g = _find_first_gap(df, tf_sec, int(_cfg2("LIVE_GAP_LOOKBACK_BARS", 600)))\n    if g is None:\n        return df\n    key = (sym, int(g))\n    if key in _GAP_ATTEMPTED:\n        return df                       # dead gap: tried once, never again\n    if len(_GAP_ATTEMPTED) > 5000:\n        _GAP_ATTEMPTED.clear()\n    _GAP_ATTEMPTED.add(key)\n    _GAP_BUDGET["n"] += 1\n    try:\n        now = time.time()\n        limit = int(min(1000, max(5, int((now - g) // max(int(tf_sec), 1)) + 2)))\n        _rate_record(2.0 if limit < 500 else 5.0)\n        raw = exchange.fetch_ohlcv(sym, tf, int(g * 1000), limit)\n        if not raw:\n            return df\n        dn = pd.DataFrame(raw, columns=_OHLCV_COLS)\n        dn["ts"] = pd.to_datetime(dn["ts"], unit="ms", utc=True)\n        dn = dn.set_index("ts").astype(float)\n        before = len(df)\n        keep = int(_cfg2("LIVE_TAIL_BARS", 8000))\n        m = pd.concat([df, dn])\n        m = m[~m.index.duplicated(keep="last")].sort_index().tail(keep)\n        log.warning(f"[GapHeal] {sym}: gap after "\n                    f"{pd.Timestamp(g, unit=\'s\', tz=\'UTC\')} -> "\n                    f"{len(m) - before:+d} bars")\n        return m\n    except Exception as e:\n        log.debug(f"[GapHeal] {sym} failed: {e}")\n        return df\n\n\n# ───────────────────────── 3) no blackouts ─────────────────────────\ndef _live_keepalive(exchange, open_pos_live, assets, cap_live,\n                    corr_cache) -> None:\n    """Called between retrain items so watchers / heartbeat keep running."""\n    now = time.time()\n    if now - _KEEPALIVE_LAST["t"] < float(_cfg2("LIVE_KEEPALIVE_S", 5.0)):\n        return\n    _KEEPALIVE_LAST["t"] = now\n    try:\n        if getattr(CFG, "REVERSAL_CONFIRM_ENABLED", False):\n            monitor_reversal_watchers(exchange, open_pos_live, assets=assets,\n                                      cap_now=cap_live, corr_cache=corr_cache)\n    except Exception as e:\n        log.debug(f"[KeepAlive] monitor error: {e}")\n    _heartbeat({"state": "retrain", "watchers": len(_REVERSAL_WATCHERS)})\n\n\nclass _UniverseRefresher:\n    """4-hourly universe + deep-history refresh in a background thread; the\n    main loop swaps the result in atomically (no multi-minute blackout)."""\n\n    def __init__(self):\n        self.th = None\n        self.res = None\n        self.err = None\n        self.retry_at = 0.0\n        self.lock = _th2.Lock()\n\n    def maybe_start(self, exchange, cfg, open_pos_live, last_scan_time) -> bool:\n        now = time.time()\n        if self.th is not None:\n            return False\n        if (now - last_scan_time < float(_cfg2("UNIVERSE_REFRESH_S", 14400.0))\n                or now < self.retry_at):\n            return False\n        held = list(open_pos_live.keys())\n        days = int(_cfg2("LIVE_HISTORY_DAYS", 365))\n        tf = cfg.timeframe\n        self.res, self.err = None, None\n\n        def _job():\n            try:\n                syms = list(scan_top_assets(exchange))\n                syms += [s for s in held if s not in syms]\n                data = fetch_all(syms, exchange, tf, days=days, workers=5)\n                with self.lock:\n                    self.res, self.err = (syms, data), None\n            except Exception as e:\n                with self.lock:\n                    self.err = e\n\n        self.th = _th2.Thread(target=_job, daemon=True, name="universe-refresh")\n        self.th.start()\n        log.info("🔄 [Universe] background refresh started")\n        return True\n\n    def poll(self, open_pos_live, cached_data):\n        if self.th is None or self.th.is_alive():\n            return None\n        self.th = None\n        with self.lock:\n            res, err = self.res, self.err\n            self.res = None\n        if err is not None or not res:\n            self.retry_at = time.time() + float(_cfg2("UNIVERSE_RETRY_S", 600.0))\n            log.warning(f"[Universe] refresh failed ({err}); retry later")\n            return None\n        syms, data = res\n        keep = int(_cfg2("LIVE_TAIL_BARS", 8000))\n        merged: Dict = {}\n        for s, df in data.items():\n            if df is None or not len(df):\n                continue\n            old = cached_data.get(s)\n            if old is not None and len(old):\n                newer = old[old.index > df.index[-1]]   # bars appended meanwhile\n                if len(newer):\n                    df = pd.concat([df, newer])\n                    df = df[~df.index.duplicated(keep="last")].sort_index()\n            merged[s] = df.tail(keep)\n        top = [s for s in syms if s in merged]\n        for s in open_pos_live:                         # never drop held symbols\n            if s not in merged and s in cached_data:\n                merged[s] = cached_data[s]\n            if s in merged and s not in top:\n                top.append(s)\n        if not top:\n            self.retry_at = time.time() + float(_cfg2("UNIVERSE_RETRY_S", 600.0))\n            return None\n        log.info(f"[Universe] swapped in {len(top)} symbols")\n        return top, merged\n\n\n_UNIV = _UniverseRefresher()\n\n\n# ═══════════════════════════════════════════════════════════════\n\n\n'

PATCHES = []
def P(name, old, new):
    PATCHES.append((name, old, new))

# ── config knobs ──
P("cfg.v2",
  "    REV_RESIZE_AT_FILL: bool = True           # rescale qty by capital(now)/capital(at signal)\n",
  "    REV_RESIZE_AT_FILL: bool = True           # rescale qty by capital(now)/capital(at signal)\n"
  "    # ══ [REV-FIX v2] long-run hardening knobs ══\n"
  "    LOOP_WARN_ERRORS: int = 5                 # consecutive loop errors -> alert\n"
  "    LOOP_MAX_CONSEC_ERRORS: int = 30          # consecutive loop errors -> give up\n"
  "    LOOP_EXIT_ON_ERRORS: bool = True          # exit(3) so a supervisor restarts the bot\n"
  "    LOOP_ERR_RESET_AFTER_S: float = 900.0     # quiet period that resets the error streak\n"
  "    HEARTBEAT_EVERY_S: float = 10.0           # heartbeat_<mode>.json refresh\n"
  "    TIMESYNC_EVERY_S: float = 3600.0\n"
  "    TIMESYNC_WARN_DRIFT_S: float = 5.0\n"
  "    MARKETS_REFRESH_S: float = 21600.0        # load_markets(reload) + clear tick/MMR/tier caches\n"
  "    DEGENERATE_BAN_TTL_S: float = 86400.0     # degenerate-symbol ban duration\n"
  "    JSON_FORCE_WRITE_S: float = 300.0         # unchanged JSON state is still rewritten this often\n"
  "    LIVE_FETCH_MAX_BARS: int = 1000           # catch-up fetch size after missed bars\n"
  "    LIVE_GAP_HEAL_ENABLED: bool = True\n"
  "    LIVE_GAP_LOOKBACK_BARS: int = 600\n"
  "    LIVE_GAP_HEAL_PER_CYCLE: int = 5\n"
  "    LIVE_KEEPALIVE_S: float = 5.0             # watcher monitoring cadence during retrain\n"
  "    REV_UNIV_BACKGROUND: bool = True          # universe refresh in a background thread\n"
  "    UNIVERSE_REFRESH_S: float = 14400.0\n"
  "    UNIVERSE_RETRY_S: float = 600.0\n")

# ── 6) rotating logs with full dates ──
P("log.setup",
  'logging.basicConfig(level=logging.INFO,\n'
  '                    format="%(asctime)s [%(levelname)s] %(message)s",\n'
  '                    datefmt="%H:%M:%S")\n'
  'log = logging.getLogger("QTT6")\n',
  'def _setup_logging():\n'
  '    """[REV-FIX v2] stdout + size-rotated file, full dates (multi-week runs).\n'
  '    env: QTT_LOG_FILE (default qtt6.log, "off" disables), QTT_LOG_MAX_MB, QTT_LOG_BACKUPS."""\n'
  '    import logging.handlers\n'
  '    root = logging.getLogger()\n'
  '    root.setLevel(logging.INFO)\n'
  '    if any(getattr(h, "_qtt", False) for h in root.handlers):\n'
  '        return\n'
  '    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",\n'
  '                            "%Y-%m-%d %H:%M:%S")\n'
  '    sh = logging.StreamHandler()\n'
  '    sh.setFormatter(fmt)\n'
  '    sh._qtt = True\n'
  '    root.addHandler(sh)\n'
  '    path = os.environ.get("QTT_LOG_FILE", "qtt6.log").strip()\n'
  '    if path and path.lower() not in ("none", "off", "0"):\n'
  '        try:\n'
  '            fh = logging.handlers.RotatingFileHandler(\n'
  '                path,\n'
  '                maxBytes=int(float(os.environ.get("QTT_LOG_MAX_MB", "20")) * 1024 * 1024),\n'
  '                backupCount=int(os.environ.get("QTT_LOG_BACKUPS", "10")),\n'
  '                encoding="utf-8")\n'
  '            fh.setFormatter(fmt)\n'
  '            fh._qtt = True\n'
  '            root.addHandler(fh)\n'
  '        except Exception as _e:\n'
  '            root.warning(f"[Log] file handler disabled: {_e}")\n\n\n'
  '_setup_logging()\n'
  'log = logging.getLogger("QTT6")\n')

# ── 7) write-only-if-changed JSON ──
P("json.lv_atomic",
  "def _lv_atomic_json(path, obj) -> None:\n"
  "    # write-then-rename: a crash can never leave a truncated state file\n"
  "    tmp = f\"{path}.tmp\"\n"
  "    with open(tmp, 'w') as f:\n"
  "        json.dump(obj, f, indent=2, default=str)\n"
  "        f.flush()\n"
  "        try:\n"
  "            os.fsync(f.fileno())\n"
  "        except Exception:\n"
  "            pass\n"
  "    os.replace(tmp, path)\n",
  "def _lv_atomic_json(path, obj) -> None:\n"
  "    # write-then-rename (crash-safe) and [REV-FIX v2] skipped when unchanged\n"
  "    _json_write_if_changed(path, obj, indent=2, fsync=True)\n")

P("json.symbol_meta",
  "        tmp = _SYMBOL_META_PATH + \".tmp\"\n"
  "        with open(tmp, 'w') as f:\n"
  "            json.dump(_SYMBOL_META, f, indent=2)\n"
  "        os.replace(tmp, _SYMBOL_META_PATH)\n",
  "        _json_write_if_changed(_SYMBOL_META_PATH, _SYMBOL_META, indent=2)\n")

P("json.pending",
  "        with open(tmp, 'w') as f:\n"
  "            json.dump(serializable, f, indent=2, default=str)\n"
  "        os.replace(tmp, _PENDING_ORDERS_PATH)\n",
  "        _json_write_if_changed(_PENDING_ORDERS_PATH, serializable, indent=2)\n")

P("json.rev_dump",
  "def _rev_atomic_dump(path: str, obj) -> None:\n"
  "    tmp = path + \".tmp\"\n"
  "    with open(tmp, \"w\") as f:\n"
  "        json.dump(obj, f, default=str, indent=1)\n"
  "    os.replace(tmp, path)\n",
  "def _rev_atomic_dump(path: str, obj) -> None:\n"
  "    _json_write_if_changed(path, obj, indent=1)   # [REV-FIX v2]\n")

# ── 5) degenerate ban with TTL ──
P("ban.put",
  "    _DEGENERATE_STREAK[sym] = _DEGENERATE_STREAK.get(sym, 0) + 1\n",
  "    _DEGENERATE_STREAK[sym] = _DEGENERATE_STREAK.get(sym, 0) + 1\n"
  "    # [REV-FIX v2] bans expire (was: banned for the whole process lifetime)\n"
  "    if (_DEGENERATE_STREAK[sym] >= _DEGENERATE_BAN_THRESHOLD\n"
  "            and sym not in _DEGENERATE_BAN_UNTIL):\n"
  "        _DEGENERATE_BAN_UNTIL[sym] = time.time() + float(\n"
  "            getattr(CFG, 'DEGENERATE_BAN_TTL_S', 86400.0))\n"
  "        log.warning(f\"[Degenerate-Ban] {sym} banned for \"\n"
  "                    f\"{getattr(CFG, 'DEGENERATE_BAN_TTL_S', 86400.0)/3600:.0f}h\")\n")

P("ban.fast",
  "                        if _DEGENERATE_STREAK.get(sym, 0) >= _DEGENERATE_BAN_THRESHOLD:\n"
  "                            continue\n",
  "                        if _degenerate_banned(sym):\n"
  "                            continue\n")

P("ban.slow",
  "                    if _DEGENERATE_STREAK.get(sym, 0) >= _DEGENERATE_BAN_THRESHOLD:\n"
  "                        log.debug(f\"[Degenerate-Ban] {sym} skipped \"\n",
  "                    if _degenerate_banned(sym):\n"
  "                        log.debug(f\"[Degenerate-Ban] {sym} skipped \"\n")

# ── 8) gap-aware candle refresh ──
P("gap.fetch",
  "                    new_candles = exchange.fetch_ohlcv(sym, cfg.timeframe, limit=3)\n"
  "                    _rate_record(1.0)\n",
  "                    # [REV-FIX v2] catches up after missed bars (was: always last 3)\n"
  "                    new_candles = _live_fetch_candles(\n"
  "                        exchange, sym, cfg.timeframe, cached_data[sym], _tf_sec_local)\n")

P("gap.heal",
  "                    ].sort_index().tail(_keep))\n\n"
  "                    _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600\n",
  "                    ].sort_index().tail(_keep))\n"
  "                    cached_data[sym] = _live_heal_gaps(\n"
  "                        exchange, sym, cfg.timeframe, cached_data[sym], _tf_sec_local)\n\n"
  "                    _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600\n")

# ── 3) no blackouts: keepalive between retrain items ──
P("keepalive.parallel",
  "                        _futs = [_ex.submit(_do_retrain, s, lc)\n"
  "                                 for s, lc in _to_retrain]\n"
  "                        for _f in as_completed(_futs):\n",
  "                        _futs = [_ex.submit(_do_retrain, s, lc)\n"
  "                                 for s, lc in _to_retrain]\n"
  "                        for _f in as_completed(_futs):\n"
  "                            _live_keepalive(exchange, open_pos_live, assets,\n"
  "                                            cap_live, corr_cache)\n")

P("keepalive.serial",
  "                    for _sym, _lc_ts in _to_retrain:\n"
  "                        try:\n"
  "                            _ad = process_asset(\n",
  "                    for _sym, _lc_ts in _to_retrain:\n"
  "                        _live_keepalive(exchange, open_pos_live, assets,\n"
  "                                        cap_live, corr_cache)\n"
  "                        try:\n"
  "                            _ad = process_asset(\n")

# ── 3) background universe refresh ──
P("universe.bg",
  "            # تحديث دوري لقائمة الأزواج لتجنب جمود السيولة\n"
  "            if time.time() - last_scan_time > 4 * 3600:\n"
  "                log.info(\"🔄 تحديث قائمة الأصول ومزامنة التاريخ العميق...\")\n",
  "            # تحديث دوري لقائمة الأزواج لتجنب جمود السيولة\n"
  "            # [REV-FIX v2] background refresh + atomic swap (no multi-minute blackout)\n"
  "            if getattr(CFG, 'REV_UNIV_BACKGROUND', True):\n"
  "                _UNIV.maybe_start(exchange, cfg, open_pos_live, last_scan_time)\n"
  "                _uswap = _UNIV.poll(open_pos_live, cached_data)\n"
  "                if _uswap is not None:\n"
  "                    top_syms, cached_data = _uswap\n"
  "                    last_scan_time = time.time()\n"
  "                    corr_cache.clear()\n"
  "            elif time.time() - last_scan_time > 4 * 3600:\n"
  "                log.info(\"🔄 تحديث قائمة الأصول ومزامنة التاريخ العميق...\")\n")

# ── 2/4) periodic housekeeping at loop top ──
P("loop.housekeeping",
  "            t0 = time.time()\n"
  "            # ══ [RateLimit] periodic report ══\n"
  "            _rate_report()\n",
  "            t0 = time.time()\n"
  "            # ══ [REV-FIX v2] hourly time sync / 6-hourly markets reload ══\n"
  "            try:\n"
  "                _live_housekeeping(exchange, open_pos_live)\n"
  "            except Exception as _e:\n"
  "                log.warning(f\"[Housekeeping] failed: {_e}\")\n"
  "            # ══ [RateLimit] periodic report ══\n"
  "            _rate_report()\n")

# ── 1) loop health ──
P("loop.ok",
  "            sleep_time = max(0, cfg.LIVE_POLL_SECS - (time.time() - t0))\n"
  "            time.sleep(sleep_time)\n",
  "            _loop_ok(loop_iter, open_pos_live)   # [REV-FIX v2] resets error streak + heartbeat\n"
  "            sleep_time = max(0, cfg.LIVE_POLL_SECS - (time.time() - t0))\n"
  "            time.sleep(sleep_time)\n")

P("loop.except",
  "            import traceback\n"
  "            log.error(f\"خطأ غير متوقع في حلقة التداول: {e}\")\n"
  "            log.debug(traceback.format_exc())\n"
  "            time.sleep(10)\n",
  "            # [REV-FIX v2] escalate persistent failures (traceback at ERROR, alert, exit)\n"
  "            _loop_error_handler(\n"
  "                exchange, e,\n"
  "                open_pos_live if 'open_pos_live' in dir() else None,\n"
  "                state_file if 'state_file' in dir() else None)\n"
  "            time.sleep(10)\n")

# ── 2) exchange options ──
P("main.exchange",
  "        'enableRateLimit': True,\n"
  "        'options': {'defaultType': 'future'}\n"
  "    })\n"
  "    # ══ [TimeSync] verify before run ══\n",
  "        'enableRateLimit': True,\n"
  "        'options': {'defaultType': 'future',\n"
  "                    'adjustForTimeDifference': True,   # [REV-FIX v2]\n"
  "                    'recvWindow': 20000}\n"
  "    })\n"
  "    # ══ [TimeSync] verify before run ══\n")

# ── helper block, inserted right before run_live ──
P("v2.block",
  "def run_live(cfg, exchange):\n",
  NEW_V2_BLOCK + "def run_live(cfg, exchange):\n")


def _once(src, old, name):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"[ABORT] anchor '{name}' matched {n} times (expected exactly 1). "
                         f"The file differs from the audited version - nothing was written.")


def apply(src):
    if MARK in src:
        raise SystemExit("[ABORT] file already contains [REV-FIX v2] - nothing to do.")
    if "[REV-FIX v1]" not in src:
        raise SystemExit("[ABORT] [REV-FIX v1] is not applied - run apply_reversal_fixes.py first.")
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
    out = a.src if a.inplace else (a.out or os.path.splitext(a.src)[0] + "_v2.py")
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
