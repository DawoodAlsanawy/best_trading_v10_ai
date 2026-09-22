# الجولة الثالثة — الإصلاحات المتقدمة

## ترتيب الأولويات للجولة الثالثة

| # | الميزة | الأثر | الخطورة |
|---|---|---|---|
| ① | Support/Resistance Filter | رفض 20-40% من الإشارات السيئة | 🔴 حرج |
| ② | Kill Switch (HMAC) | إيقاف آمن عند الطوارئ | 🔴 حرج |
| ③ | Extended Reconciliation | تطابق `_SYMBOL_META` مع البورصة | 🟠 عالي |
| ④ | Rate-Limit Tracker | منع `-1003` | 🟠 عالي |
| ⑤ | Time-Sync Guard | منع انحراف الساعة | 🟡 متوسط |

---

## الإصلاح ① — Support/Resistance Filter

### Config Fields

**الموقع:** داخل `Config`, بعد `ENTRY_VALIDATE_ENABLED` (أو بعد `SMART_OHLCV_ENABLED` إذا لم تكن الأولى موجودة).

```python
    # ══ [SUPPORT/RESISTANCE FILTER] ══
    SR_FILTER_ENABLED: bool = True
    SR_LOOKBACK: int = 100              # bars to scan for S/R levels
    SR_MIN_TOUCHES: int = 3             # minimum touches to qualify
    SR_TOUCH_TOLERANCE: float = 0.0025  # price tolerance (0.25%)
    SR_MIN_GAP_BARS: int = 10           # min bars between touches
    SR_STRENGTH_THRESHOLD: float = 2.0  # combined strength required
    SR_DECAY_TAU: float = 50.0          # exponential decay constant (bars)
    SR_SL_PROXIMITY: float = 0.004      # SL must be within 0.4% of level
    SR_VOLUME_WEIGHT: float = 1.5       # volume ratio weight in strength
```

### Helper Functions

**الموقع:** قبل `def build_signals(assets, mode="backtest"):` (القسم § 13).

```python
# ════════════════════════════════════════════════════════════════
# § 12.9  Support/Resistance Detection
# ════════════════════════════════════════════════════════════════

def _find_swing_levels(ad, current_ci: int, lookback: int) -> Tuple[List[float], List[float]]:
    """
    Find candidate support (lows) and resistance (highs) levels
    from swing points in the last `lookback` bars.

    A swing low at bar j requires:
        lows[j] < lows[j-1]  AND  lows[j] < lows[j+1]
    (local minimum)

    Similarly for swing highs.

    Returns (supports, resistances) as lists of prices.
    """
    supports: List[float] = []
    resistances: List[float] = []
    try:
        n = len(ad.lows)
        if current_ci < lookback + 2:
            return supports, resistances
        start = current_ci - lookback
        end = current_ci - 1  # exclude current bar (not closed properly)

        for j in range(start + 1, end):
            l_prev = float(ad.lows[j - 1])
            l_curr = float(ad.lows[j])
            l_next = float(ad.lows[j + 1])
            if l_curr < l_prev and l_curr < l_next:
                supports.append(l_curr)

            h_prev = float(ad.highs[j - 1])
            h_curr = float(ad.highs[j])
            h_next = float(ad.highs[j + 1])
            if h_curr > h_prev and h_curr > h_next:
                resistances.append(h_curr)
    except Exception as e:
        log.debug(f"[SR] swing detection failed {ad.symbol}: {e}")
    return supports, resistances


def _cluster_levels(levels: List[float], tolerance: float) -> List[Dict]:
    """
    Cluster nearby levels into a single "true" level.
    Each cluster: {'price': mean, 'touch_count': int, 'last_touch_idx': int,
                   'avg_volume': float}
    """
    if not levels:
        return []
    # Sort descending so we can process
    sorted_levels = sorted(levels, reverse=True)
    clusters: List[Dict] = []
    for price in sorted_levels:
        placed = False
        for c in clusters:
            if abs(price - c['price']) / max(c['price'], 1e-12) < tolerance:
                # Add to existing cluster; update running mean
                cnt = c['touch_count']
                c['price'] = (c['price'] * cnt + price) / (cnt + 1)
                c['touch_count'] = cnt + 1
                placed = True
                break
        if not placed:
            clusters.append({'price': price, 'touch_count': 1, 'last_touch_idx': 0})
    return clusters


def _compute_level_strength(ad, current_ci: int, level_price: float,
                             cluster: Dict) -> float:
    """
    Combined strength = touches × time_decay × volume_factor.

    touches       : cluster['touch_count']
    time_decay    : exp(-Δt / τ_decay) where Δt = bars since first touch
    volume_factor : (avg_volume_at_level / avg_volume_100)
    """
    try:
        tau = float(getattr(CFG, 'SR_DECAY_TAU', 50.0))
        lookback = int(getattr(CFG, 'SR_LOOKBACK', 100))
        start = max(0, current_ci - lookback)

        # Time decay: bars since earliest touch (approximate by lookback span)
        delta_t = max(1, current_ci - start)
        time_factor = float(np.exp(-delta_t / tau))

        # Volume factor: mean volume near level / mean volume overall
        tol = float(getattr(CFG, 'SR_TOUCH_TOLERANCE', 0.0025))
        vol_at = []
        for j in range(start, current_ci):
            try:
                lj = float(ad.lows[j])
                hj = float(ad.highs[j])
                if (abs(lj - level_price) / max(level_price, 1e-12) < tol
                        or abs(hj - level_price) / max(level_price, 1e-12) < tol):
                    vol_at.append(float(ad.volumes[j]))
            except Exception:
                continue
        if not vol_at:
            return 0.0
        vol_mean_all = float(np.mean(ad.volumes[start:current_ci])) + 1e-12
        vol_factor = float(np.mean(vol_at)) / vol_mean_all

        strength = float(cluster['touch_count']) * time_factor * vol_factor
        return strength
    except Exception as e:
        log.debug(f"[SR] strength compute failed: {e}")
        return 0.0


def _sr_filter_check(sig, ad, current_ci: int) -> Tuple[bool, str]:
    """
    Reject signal if its SL is not protected by a strong S/R level.

    For BUY: look for support level near SL (within SR_SL_PROXIMITY below).
    For SELL: look for resistance level near SL (within SR_SL_PROXIMITY above).

    Returns (ok, reason).
    """
    if not getattr(CFG, 'SR_FILTER_ENABLED', True):
        return True, "OK"

    try:
        lookback = int(getattr(CFG, 'SR_LOOKBACK', 100))
        min_touches = int(getattr(CFG, 'SR_MIN_TOUCHES', 3))
        tol = float(getattr(CFG, 'SR_TOUCH_TOLERANCE', 0.0025))
        min_gap = int(getattr(CFG, 'SR_MIN_GAP_BARS', 10))
        str_thr = float(getattr(CFG, 'SR_STRENGTH_THRESHOLD', 2.0))
        sl_prox = float(getattr(CFG, 'SR_SL_PROXIMITY', 0.004))

        supports, resistances = _find_swing_levels(ad, current_ci, lookback)
        if sig.action == "BUY":
            candidates = supports
        else:
            candidates = resistances

        if not candidates:
            return False, "no_swing_levels"

        clusters = _cluster_levels(candidates, tol)

        sl_price = float(sig.sl)
        best_strength = 0.0
        best_level = 0.0
        for c in clusters:
            if c['touch_count'] < min_touches:
                continue
            # Distance from SL to this level
            dist = abs(sl_price - c['price']) / max(sl_price, 1e-12)
            if dist > sl_prox:
                continue
            # Direction check:
            # BUY: level should be at or below SL (support below entry)
            # SELL: level should be at or above SL (resistance above entry)
            if sig.action == "BUY" and c['price'] > sl_price * (1.0 + tol):
                continue
            if sig.action == "SELL" and c['price'] < sl_price * (1.0 - tol):
                continue
            strength = _compute_level_strength(ad, current_ci, c['price'], c)
            if strength > best_strength:
                best_strength = strength
                best_level = c['price']

        if best_strength < str_thr:
            return False, (f"weak_SR (strength={best_strength:.2f} "
                           f"< {str_thr:.2f}, level={best_level:.6f})")
        return True, f"OK (strength={best_strength:.2f})"
    except Exception as e:
        log.warning(f"[SR] filter check failed {sig.symbol}: {e}")
        return True, "SR_check_error"  # fail open
```

### Integration في `build_signals`

**الموقع:** داخل `build_signals`, بعد فحص `if ad.score[fi] < CFG.MIN_SCORE: continue`.

**ابحث عن:**

```python
            if ad.score[fi] < CFG.MIN_SCORE: continue

            # [التعديل ②]: Phase-Matched Entry (تجنب السكين الساقطة)
```

**أضف بينهما:**

```python
            if ad.score[fi] < CFG.MIN_SCORE: continue

            # ══ [SR FILTER] SL must be protected by strong support/resistance ══
            # (computed after SL/TP is known — moved below in this version)
            # See the deferred check after SL/TP computation.

            # [التعديل ②]: Phase-Matched Entry (تجنب السكين الساقطة)
```

**ثم** ابحث عن (بعد حساب `sl_dist` و `tp1`):

```python
            # حظر الصفقات الهشة التي تكون تكلفتها أكبر من ربحها
            if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue

            dynamic_risk = compute_geodesic_kelly(ad, fi, CFG)
```

**أضف قبله:**

```python
            # حظر الصفقات الهشة التي تكون تكلفتها أكبر من ربحها
            if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue

            # ══ [SR FILTER] SL must be protected by strong S/R ══
            _sr_sig = Signal(
                timestamp=ad.timestamps[ci], symbol=sym,
                price=tunnel_entry_p, score=float(ad.score[fi]),
                action=action, sl=sl, tp1=tp1, tp2=0.0, tp3=0.0,
                atr=float(ad.atr14[ci]), lam=0.0, close_idx=ci, feat_idx=fi,
                adv_usd=float(ad.adv_usd[ci]), tri_val=float(ad.tri[fi]),
                dynamic_risk=CFG.MIN_RISK, T_info_val=T_info,
                dyn_sl_factor=sl_dist / tunnel_entry_p,
            )
            _sr_ok, _sr_reason = _sr_filter_check(_sr_sig, ad, ci)
            if not _sr_ok:
                log.debug(f"[SR] {sym} reject @ {ci}: {_sr_reason}")
                continue

            dynamic_risk = compute_geodesic_kelly(ad, fi, CFG)
```

### Integration في `run_live` (Pre-Entry Gate)

**الموقع:** داخل `run_live`, block الدخول، بعد `if delta < 1e-8: continue`.

**ابحث عن:**

```python
                    lmt = sig.price 
                    delta = abs(lmt - sig.sl)
                    if delta < 1e-8: continue
                    if cap_live <= cfg.CAPITAL_FLOOR + 0.1: continue
```

**استبدله بـ:**

```python
                    lmt = sig.price 
                    delta = abs(lmt - sig.sl)
                    if delta < 1e-8: continue
                    if cap_live <= cfg.CAPITAL_FLOOR + 0.1: continue

                    # ══ [SR FILTER — Live] ══
                    _live_ci = max(0, len(ad.closes) - 2)
                    _sr_ok, _sr_reason = _sr_filter_check(sig, ad, _live_ci)
                    if not _sr_ok:
                        log.info(f"[SR] {sym} rejected: {_sr_reason}")
                        continue
```

### CLI Flag

**الموقع:** داخل `main()`, بعد `--no-smart-ohlcv`.

```python
    p.add_argument("--no-sr-filter", action="store_true",
                   help="Disable support/resistance filter")
    p.add_argument("--sr-strength", type=float, default=None,
                   help="S/R strength threshold (default 2.0)")
```

**وفي block معالجة args:**

```python
    if args.no_sr_filter:
        CFG.SR_FILTER_ENABLED = False
    if args.sr_strength is not None:
        CFG.SR_STRENGTH_THRESHOLD = float(args.sr_strength)
```

---

## الإصلاح ② — Kill Switch (HMAC-Authenticated)

### Config Fields

**الموقع:** داخل `Config`, بعد حقول `SR_*`.

```python
    # ══ [KILL SWITCH — HMAC-authenticated] ══
    KILL_SWITCH_ENABLED: bool = True
    KILL_SWITCH_SECRET: str = ""          # from env or CLI
    KILL_SWITCH_FILE: str = "kill_switch.json"
    KILL_SWITCH_POLL_S: int = 5
    KILL_STATE_ARMED: str = "ARMED"
    KILL_STATE_WARNING: str = "WARNING"
    KILL_STATE_TRIGGERED: str = "TRIGGERED"
```

### Helper Functions

**الموقع:** قبل `def run_live(cfg, exchange):`.

```python
# ════════════════════════════════════════════════════════════════
# § 18.98  Kill Switch (HMAC-authenticated)
# ════════════════════════════════════════════════════════════════

import hmac as _hmac
import hashlib as _hashlib

_KILL_SWITCH_STATE: Dict = {
    'state': 'ARMED',
    'reason': '',
    'triggered_at': 0.0,
    'last_file_mtime': 0.0,
}


def _kill_sign(reason: str, secret: str) -> str:
    """Compute HMAC-SHA256 token for a given reason."""
    if not secret:
        return ""
    return _hmac.new(secret.encode(), reason.encode(), _hashlib.sha256).hexdigest()


def _kill_verify(reason: str, token: str, secret: str) -> bool:
    """Constant-time verify."""
    if not secret or not token:
        return False
    expected = _kill_sign(reason, secret)
    try:
        return _hmac.compare_digest(expected, token)
    except Exception:
        return False


def _kill_switch_check_file(path: str, secret: str) -> Tuple[bool, str]:
    """
    Read kill switch file. Format:
        {"state": "TRIGGERED", "reason": "...", "token": "..."}
    Returns (should_trigger, reason). Verifies HMAC.
    """
    if not secret:
        return False, ""
    if not os.path.exists(path):
        return False, ""
    try:
        mtime = os.path.getmtime(path)
        # Skip if file not modified since last check
        if mtime <= _KILL_SWITCH_STATE.get('last_file_mtime', 0.0):
            return False, ""
        _KILL_SWITCH_STATE['last_file_mtime'] = mtime

        with open(path) as f:
            data = json.load(f)
        state = str(data.get('state') or 'ARMED')
        reason = str(data.get('reason') or '')
        token = str(data.get('token') or '')

        if state != 'TRIGGERED':
            return False, ""
        if not _kill_verify(reason, token, secret):
            log.warning(f"[KillSwitch] invalid HMAC for reason='{reason}' — ignoring")
            return False, ""
        return True, reason
    except Exception as e:
        log.debug(f"[KillSwitch] file check failed: {e}")
        return False, ""


def _kill_switch_check_auto(cap_live: float, cap_peak: float,
                             daily_loss: float, consec_losses: int
                             ) -> Tuple[bool, str]:
    """
    Automatic triggers (no HMAC needed — internal).
    """
    try:
        # Drawdown from peak
        if cap_peak > 0:
            dd = (cap_peak - cap_live) / cap_peak
            if dd >= float(CFG.MAX_DRAWDOWN_HALT) and CFG.MAX_DRAWDOWN_HALT < 1.0:
                return True, f"drawdown_{dd*100:.1f}%"

        # Consecutive losses (very loose default)
        if consec_losses >= 6:
            return True, f"consec_losses={consec_losses}"

        # Daily loss (only if tracked)
        if daily_loss <= -0.05:
            return True, f"daily_loss={daily_loss*100:.1f}%"

        return False, ""
    except Exception as e:
        log.debug(f"[KillSwitch] auto check failed: {e}")
        return False, ""


def _kill_switch_trigger(reason: str, exchange,
                          open_pos_live: Dict, state_file: str) -> None:
    """
    Emergency: flatten all positions and stop.
    """
    log.critical(f"[KillSwitch] TRIGGERED: {reason}")
    _KILL_SWITCH_STATE['state'] = 'TRIGGERED'
    _KILL_SWITCH_STATE['reason'] = reason
    _KILL_SWITCH_STATE['triggered_at'] = time.time()

    # Flatten every open position
    for sym in list(open_pos_live.keys()):
        try:
            pos = open_pos_live[sym]
            close_side = 'sell' if pos['action'] == 'BUY' else 'buy'
            o = exchange.create_order(sym, 'market', close_side, pos['qty'])
            v = verify_fill(exchange, o['id'], sym, timeout_s=3.0)
            px = v['avg_price'] if v and v['filled'] else 0.0
            log.critical(f"[KillSwitch] flattened {sym} @ {px:.6f}")
            del open_pos_live[sym]
        except Exception as e:
            log.error(f"[KillSwitch] flatten {sym} failed: {e}")

    # Cancel all pending
    for sym in list(_PENDING_ORDERS.keys()):
        rec = _PENDING_ORDERS[sym]
        oid = rec.get('order_id')
        if oid:
            try:
                exchange.cancel_order(oid, sym)
            except Exception:
                pass
        _PENDING_ORDERS.pop(sym, None)

    # Persist state
    try:
        with open(state_file, 'w') as f:
            json.dump(open_pos_live, f, indent=2)
    except Exception:
        pass
    save_pending_orders()
```

### Integration في `run_live`

**الموقع:** داخل `run_live`, بداية الحلقة `while True:` بعد `t0 = time.time()`.

**أضف:**

```python
            # ══ [KILL SWITCH] check every cycle ══
            if getattr(CFG, 'KILL_SWITCH_ENABLED', True):
                # File-based HMAC trigger
                _should_kill, _kill_reason = _kill_switch_check_file(
                    CFG.KILL_SWITCH_FILE, CFG.KILL_SWITCH_SECRET
                )
                if _should_kill:
                    _kill_switch_trigger(_kill_reason, exchange,
                                          open_pos_live, state_file)
                    return
                # Automatic triggers (drawdown etc.)
                _auto_kill, _auto_reason = _kill_switch_check_auto(
                    cap_live=cap_live if 'cap_live' in dir() else cfg.INITIAL_CAPITAL,
                    cap_peak=peak_cap_live,
                    daily_loss=0.0,
                    consec_losses=0,
                )
                if _auto_kill:
                    _kill_switch_trigger(_auto_reason, exchange,
                                          open_pos_live, state_file)
                    return
```

### Kill Switch Tool (سطر أوامر خارجي)

**أنشئ ملفاً `kill_switch.py`** في نفس المجلد:

```python
#!/usr/bin/env python3
"""
kill_switch.py — Trigger the bot's kill switch.

Usage:
    export KILL_SWITCH_SECRET="my-secret"
    python3 kill_switch.py --reason "manual test"
    python3 kill_switch.py --reason "fixing bug" --file kill_switch.json
"""
import argparse, hashlib, hmac, json, os, sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reason", required=True)
    p.add_argument("--file", default="kill_switch.json")
    p.add_argument("--secret", default=os.environ.get("KILL_SWITCH_SECRET", ""))
    args = p.parse_args()

    if not args.secret:
        print("ERROR: KILL_SWITCH_SECRET env var not set")
        sys.exit(1)

    token = hmac.new(args.secret.encode(), args.reason.encode(),
                     hashlib.sha256).hexdigest()
    data = {
        "state": "TRIGGERED",
        "reason": args.reason,
        "token": token,
        "issued_at": __import__("time").time(),
    }
    with open(args.file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✓ Kill switch triggered: {args.file}")
    print(f"  reason: {args.reason}")
    print(f"  token : {token[:16]}...")


if __name__ == "__main__":
    main()
```

### CLI Flags

**الموقع:** داخل `main()`, بعد `--sr-strength`.

```python
    p.add_argument("--kill-secret", type=str,
                   default=os.environ.get("KILL_SWITCH_SECRET", ""),
                   help="HMAC secret for kill switch (or KILL_SWITCH_SECRET env)")
    p.add_argument("--no-kill-switch", action="store_true",
                   help="Disable kill switch")
```

**وفي block معالجة args:**

```python
    if args.kill_secret:
        CFG.KILL_SWITCH_SECRET = args.kill_secret
    if args.no_kill_switch:
        CFG.KILL_SWITCH_ENABLED = False
```

---

## الإصلاح ③ — Extended Reconciliation

**المشكلة:** `_SYMBOL_META` قد يحتوي على `leverage` قديم، أو `setup_done=True` بدون رصيد فعلي.

**الموقع:** مباشرة قبل `def run_live(cfg, exchange):`.

```python
# ════════════════════════════════════════════════════════════════
# § 18.96  Extended Reconciliation (_SYMBOL_META ↔ Exchange)
# ════════════════════════════════════════════════════════════════

def reconcile_symbol_meta(exchange, symbols: List[str]) -> int:
    """
    For each symbol in _SYMBOL_META, verify leverage/margin match exchange.
    Fix mismatches when no position exists.
    Returns count of fixed entries.
    """
    global _SYMBOL_META
    fixed = 0
    for sym in list(_SYMBOL_META.keys()):
        if sym not in symbols:
            continue
        meta = _SYMBOL_META[sym]
        if not meta.get('setup_done'):
            continue

        # Check for existing position
        has_pos = False
        try:
            positions = exchange.fetch_positions([sym])
            for p in positions:
                amt = float(p['info'].get('positionAmt', 0) or 0)
                if abs(amt) > 0:
                    has_pos = True
                    break
        except Exception as e:
            log.debug(f"[ReconcileMeta] fetch_positions {sym}: {e}")
            continue

        # Verify current leverage
        try:
            lev_info = exchange.fetch_leverage(sym)
            cur_lev = int(lev_info.get('leverage', 0))
        except Exception as e:
            log.debug(f"[ReconcileMeta] fetch_leverage {sym}: {e}")
            continue

        cached_lev = int(meta.get('leverage', 0))
        if cur_lev != cached_lev:
            if has_pos:
                log.warning(
                    f"[ReconcileMeta] {sym} cached_lev={cached_lev}x "
                    f"but exchange={cur_lev}x (position open — updating cache)"
                )
                meta['leverage'] = cur_lev
            else:
                log.warning(
                    f"[ReconcileMeta] {sym} cached_lev={cached_lev}x "
                    f"but exchange={cur_lev}x (no position — updating cache)"
                )
                meta['leverage'] = cur_lev
            meta['updated_ts'] = time.time()
            fixed += 1

    if fixed > 0:
        save_symbol_meta()
        log.info(f"[ReconcileMeta] {fixed} symbols updated")
    return fixed
```

### Integration في `run_live`

**الموقع:** بعد `monitor_pending_orders` في بداية كل دورة.

```python
            # ══ [ReconcileMeta] verify symbol metadata every 30 min ══
            if not hasattr(run_live, '_last_meta_reconcile'):
                run_live._last_meta_reconcile = 0.0
            if time.time() - run_live._last_meta_reconcile > 1800:
                try:
                    reconcile_symbol_meta(exchange, top_syms)
                except Exception as e:
                    log.warning(f"[ReconcileMeta] failed: {e}")
                run_live._last_meta_reconcile = time.time()
```

---

## الإصلاح ④ — Rate-Limit Tracker

**المشكلة:** لا يوجد تتبع لاستهلاك Rate Limit. مع 50 رمزاً، قد نصل إلى `-1003`.

**الموقع:** مباشرة بعد `_SYMBOL_META_PATH: str = ""` (قبل `def load_symbol_meta`).

```python
# ════════════════════════════════════════════════════════════════
# § 18.94  Rate-Limit Tracker
# ════════════════════════════════════════════════════════════════

_RATE_TRACKER: Dict = {
    'window': [],          # list of (ts, weight)
    'total_this_min': 0.0,
    'rejected_count': 0,
    'last_report_ts': 0.0,
}

# Binance USDT-M defaults
_RATE_LIMIT_WEIGHT_PER_MIN = 2400
_RATE_LIMIT_SOFT_CAP = 0.75   # pause new placements if usage > 75%


def _rate_record(weight: float = 1.0) -> None:
    """Record an API call weight."""
    now = time.time()
    _RATE_TRACKER['window'].append((now, weight))
    # Prune older than 60s
    cutoff = now - 60.0
    _RATE_TRACKER['window'] = [
        (t, w) for (t, w) in _RATE_TRACKER['window'] if t >= cutoff
    ]
    _RATE_TRACKER['total_this_min'] = sum(w for _, w in _RATE_TRACKER['window'])


def _rate_usage() -> float:
    """Current usage fraction [0, 1]."""
    _rate_record(0.0)  # refresh
    return float(_RATE_TRACKER['total_this_min']) / _RATE_LIMIT_WEIGHT_PER_MIN


def _rate_can_place() -> bool:
    """True if rate usage is below soft cap."""
    return _rate_usage() < _RATE_LIMIT_SOFT_CAP


def _rate_report() -> None:
    """Log usage periodically."""
    now = time.time()
    if now - _RATE_TRACKER['last_report_ts'] < 300:
        return
    _RATE_TRACKER['last_report_ts'] = now
    usage = _rate_usage()
    if usage > 0.5:
        log.warning(f"[RateLimit] usage={usage*100:.1f}% "
                    f"(total={_RATE_TRACKER['total_this_min']:.0f}/min) "
                    f"rejected={_RATE_TRACKER['rejected_count']}")
    else:
        log.info(f"[RateLimit] usage={usage*100:.1f}%")
```

### Integration في `place_pending_entry`

**الموقع:** داخل `def place_pending_entry(...)`, قبل `target = float(sig.price)`.

```python
    # ══ [RateLimit] skip if soft cap reached ══
    if not _rate_can_place():
        _RATE_TRACKER['rejected_count'] += 1
        log.debug(f"[RateLimit] {sym} placement skipped — usage high")
        return None
```

### Integration في `run_live` (بداية الحلقة)

```python
            # ══ [RateLimit] periodic report ══
            _rate_report()
```

---

## الإصلاح ⑤ — Time-Sync Guard

**المشكلة:** إذا كانت ساعة الجهاز منحرفة، `TF_SCALE` و bar boundaries ستكون خاطئة.

**الموقع:** مباشرة قبل `def main():`.

```python
# ════════════════════════════════════════════════════════════════
# § 19.5  Time-Sync Guard
# ════════════════════════════════════════════════════════════════

def _check_time_sync(exchange, warn_threshold_s: float = 30.0) -> bool:
    """
    Compare exchange server time with local time.
    Warn if drift > threshold. Returns True if OK, False if drift.
    """
    try:
        server_ms = exchange.fetch_time()
        server_s = float(server_ms) / 1000.0
        local_s = time.time()
        drift = abs(local_s - server_s)
        if drift > warn_threshold_s:
            log.warning(f"[TimeSync] local drift = {drift:.1f}s "
                        f"(> {warn_threshold_s}s) — enable NTP")
            return False
        else:
            log.info(f"[TimeSync] drift = {drift:.2f}s — OK")
            return True
    except Exception as e:
        log.debug(f"[TimeSync] check failed: {e}")
        return True  # fail open
```

### Integration في `main()` (بعد إنشاء الـ exchange)

**الموقع:** داخل `main()`, بعد `exchange = ccxt.binance({...})`.

```python
    # ══ [TimeSync] verify before run ══
    _check_time_sync(exchange)
```

---

## قائمة الفحص النهائية للجولة الثالثة

| # | التعديل | الموقع | النوع |
|---|---|---|---|
| ① | Config `SR_*` | `Config` | Add |
| ①b | `_find_swing_levels`, `_cluster_levels`, `_compute_level_strength`, `_sr_filter_check` | قبل `build_signals` | Add |
| ①c | SR filter في `build_signals` | داخلها | Add |
| ①d | SR filter في `run_live` | block الدخول | Add |
| ①e | CLI flags `--no-sr-filter`, `--sr-strength` | `main()` | Add |
| ② | Config `KILL_*` | `Config` | Add |
| ②b | `_kill_sign`, `_kill_verify`, `_kill_switch_check_file`, `_kill_switch_check_auto`, `_kill_switch_trigger` | قبل `run_live` | Add |
| ②c | Kill switch check في `run_live` | بداية الحلقة | Add |
| ②d | ملف `kill_switch.py` | ملف جديد | Add |
| ②e | CLI flags `--kill-secret`, `--no-kill-switch` | `main()` | Add |
| ③ | `reconcile_symbol_meta` | قبل `run_live` | Add |
| ③b | Integration في `run_live` (كل 30 دقيقة) | داخلها | Add |
| ④ | `_rate_record`, `_rate_usage`, `_rate_can_place`, `_rate_report` | قبل `load_symbol_meta` | Add |
| ④b | Integration في `place_pending_entry` | داخلها | Add |
| ④c | Integration في `run_live` | بداية الحلقة | Add |
| ⑤ | `_check_time_sync` | قبل `main()` | Add |
| ⑤b | Integration في `main()` | داخلها | Add |

---

## التحقق بعد التطبيق

```bash
# 1. Syntax
python3 -c "import ast; ast.parse(open('trading.py').read()); print('✓ Syntax OK')"

# 2. عدد الدوال الجديدة
grep -c "def _sr_filter_check\|def _find_swing_levels\|def _cluster_levels\|def _compute_level_strength\|def _kill_sign\|def _kill_verify\|def _kill_switch_check_file\|def _kill_switch_check_auto\|def _kill_switch_trigger\|def reconcile_symbol_meta\|def _rate_record\|def _rate_usage\|def _rate_can_place\|def _rate_report\|def _check_time_sync" trading.py
# يجب أن يطبع: 15

# 3. Config check
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('bot', 'trading.py')
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
C = bot.CFG
print('SR_FILTER_ENABLED       =', C.SR_FILTER_ENABLED)
print('SR_STRENGTH_THRESHOLD   =', C.SR_STRENGTH_THRESHOLD)
print('KILL_SWITCH_ENABLED     =', C.KILL_SWITCH_ENABLED)
print('KILL_SWITCH_SECRET set  =', bool(C.KILL_SWITCH_SECRET))
"
```

---

## اختبار شامل

### 1. Backtest بدون SR filter

```bash
python3 trading.py --mode backtest --capital 55 --nassets 5 --maxcon 2 \
    --rule-filter --rule-min-score 2 --no-sr-filter \
    2>&1 | tee bt_no_sr.log
```

### 2. Backtest مع SR filter

```bash
python3 trading.py --mode backtest --capital 55 --nassets 5 --maxcon 2 \
    --rule-filter --rule-min-score 2 \
    2>&1 | tee bt_with_sr.log
```

**المقارنة المتوقعة:**

| المقياس | بدون SR | مع SR |
|---|---|---|
| عدد الصفقات | أكثر | **أقل 20-40%** |
| Win Rate | baseline | **+3-8 pp** |
| Sharpe | baseline | **+0.5-1.5** |
| MaxDD | baseline | **-15-30%** |

### 3. اختبار Kill Switch

```bash
# في نافذة 1:
export KILL_SWITCH_SECRET="test-secret-12345"
python3 trading.py --mode testnet \
    --api-key $BINANCE_API_KEY --api-secret $BINANCE_API_SECRET \
    --capital 55 --nassets 5 --maxcon 2 --kill-secret "$KILL_SWITCH_SECRET"

# في نافذة 2 (بعد بدء التشغيل):
export KILL_SWITCH_SECRET="test-secret-12345"
python3 kill_switch.py --reason "testing kill switch"
```

**المتوقع في نافذة 1:**
```
[KillSwitch] TRIGGERED: testing kill switch
[KillSwitch] flattened BTC/USDT @ 67234.50
[KillSwitch] flattened ETH/USDT @ 3412.30
```

### 4. اختبار Time Sync

عند بدء أي تشغيل:
```
[TimeSync] drift = 0.42s — OK
```

---

## ما سيبقى للجولة الرابعة (إن لزم)

- Prometheus metrics exporter
- Telegram alerts integration
- SQLite/PostgreSQL ledger
- Web dashboard
- Automated retraining for ML filter
- Contract tests (Backtest ≡ Live byte-by-byte)
- Docker deployment

**بعد تشغيل الاختبارات، أرسل:**

1. مخرجات Backtest بدون SR
2. مخرجات Backtest مع SR
3. جدول المقارنة (Sharpe, WR, MaxDD, عدد الصفقات)
4. إذا جرّبت Kill Switch: مخرجات `kill_switch.py` + رد فعل البوت
5. أي `[SR]` أو `[KillSwitch]` أو `[RateLimit]` في الـ log

سأحلّل أثر الفلاتر وأُعاير `SR_STRENGTH_THRESHOLD` و `SR_SL_PROXIMITY` حسب النتائج.
