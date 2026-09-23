# التعديلات الجراحية — Layer 7 + إصلاحات التأخير

خمسة تعديلات متماسكة. كل واحد في مكانه المحدد. اقرأ كل قسم كاملاً قبل اللصق.

---

## 🔧 التعديل ① — ثوابت جديدة في `Config`

**الموقع:** في `class Config`، بعد كتلة `LIQ_ENABLED: bool = True` مباشرة.

**✅ أضف هذا البلوك:**

```python
    # ══ [LAYER 7 — Broker-side protective orders] ══
    PROTECTIVE_ORDERS_ENABLED: bool = True
    PROTECTIVE_WORKING_TYPE: str = "MARK_PRICE"
    PROTECTIVE_SYNC_MIN_STEP_FRAC: float = 0.001   # 0.1% SL movement → resync
    PROTECTIVE_MAX_RETRIES: int = 2

    # ══ [LATENCY FIX — Exits] ══
    # Urgent exits (Emergency SL, Hard TP, LiqProximity) must not wait
    # for post-only. They cross the spread (marketable limit) — cost is
    # ~1 spread (~2-5 bps), not the 5-25% slippage of a raw market order.
    PO_EXIT_MAX_WAIT_S: int = 12            # was 45 (still used for soft exits)
    PO_EXIT_URGENT_WAIT_S: int = 4          # for SL/TP/LiqProximity
    PO_EXIT_URGENT_CROSS_SPREAD: bool = True
```

**ملاحظة:** `PO_EXIT_MAX_WAIT_S` موجود بالفعل بقيمة 45. استبدل قيمته فقط.

---

## 🔧 التعديل ② — دوال Layer 7 (المستوى العام)

**الموقع:** في المستوى العام، بعد `_estimate_liq_for_position` مباشرة (أي قبل `scan_top_assets`).

**✅ أضف هذا البلوك كاملاً:**

```python
# ════════════════════════════════════════════════════════════════
# [LAYER 7] — Broker-side protective orders (STOP_MARKET + TP)
# ════════════════════════════════════════════════════════════════

_PROTECTIVE_ORDER_TYPES = {"STOP_MARKET", "TAKE_PROFIT_MARKET",
                            "stop_market", "take_profit_market"}


def _is_protective_order(o: Dict) -> bool:
    """True if the order is a protective SL/TP placed by this bot."""
    try:
        t = str(o.get('type') or '').lower()
        return ('stop_market' in t or 'take_profit_market' in t)
    except Exception:
        return False


def _cancel_all_protective_orders(exchange, sym: str) -> int:
    """
    Cancel every STOP_MARKET / TAKE_PROFIT_MARKET on the symbol.
    Returns count cancelled. Silent on errors (best-effort).
    """
    n = 0
    try:
        for o in exchange.fetch_open_orders(sym):
            if _is_protective_order(o):
                try:
                    exchange.cancel_order(o['id'], sym)
                    n += 1
                except Exception as e:
                    log.debug(f"[Prot] cancel {sym} oid={o['id']} failed: {e}")
    except Exception as e:
        log.debug(f"[Prot] fetch_open_orders {sym} failed: {e}")
    return n


def _place_protective_orders(exchange, sym: str, pos: Dict) -> bool:
    """
    Place STOP_MARKET at SL and TAKE_PROFIT_MARKET at TP for the position.

    Design:
      - closePosition=True → Binance auto-sizes and auto-cancels if position
        disappears. No risk of orphan orders when the other side fires.
      - workingType=MARK_PRICE → avoids last-price manipulation and matches
        what Binance uses for liquidation.
      - Fallback to explicit qty + reduceOnly if the exchange rejects
        closePosition (some testnets).
    Returns True on success.
    """
    if not getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        return False
    try:
        action = pos.get('action')
        sl = float(pos.get('sl') or 0)
        tp = float(pos.get('tp1') or 0)
        qty = float(pos.get('qty') or 0)
        if action not in ('BUY', 'SELL') or sl <= 0 or tp <= 0 or qty <= 0:
            return False

        close_side = 'sell' if action == 'BUY' else 'buy'
        wt = str(getattr(CFG, 'PROTECTIVE_WORKING_TYPE', 'MARK_PRICE'))
        max_retries = int(getattr(CFG, 'PROTECTIVE_MAX_RETRIES', 2))

        # Cancel any stale protective orders first (idempotent)
        _cancel_all_protective_orders(exchange, sym)
        time.sleep(0.1)

        placed = {'sl': False, 'tp': False}

        # ── SL ──
        for attempt in range(max_retries):
            try:
                exchange.create_order(
                    sym, 'STOP_MARKET', close_side, None, None,
                    params={
                        'stopPrice': sl,
                        'closePosition': True,
                        'workingType': wt,
                    }
                )
                placed['sl'] = True
                break
            except Exception as e:
                log.debug(f"[Prot] {sym} STOP_MARKET attempt {attempt+1} "
                          f"(closePosition) failed: {e}")
                # Fallback: explicit qty + reduceOnly
                try:
                    exchange.create_order(
                        sym, 'STOP_MARKET', close_side, qty, None,
                        params={
                            'stopPrice': sl,
                            'reduceOnly': True,
                            'workingType': wt,
                        }
                    )
                    placed['sl'] = True
                    break
                except Exception as e2:
                    log.debug(f"[Prot] {sym} STOP_MARKET attempt "
                              f"{attempt+1} (reduceOnly) failed: {e2}")

        # ── TP ──
        for attempt in range(max_retries):
            try:
                exchange.create_order(
                    sym, 'TAKE_PROFIT_MARKET', close_side, None, None,
                    params={
                        'stopPrice': tp,
                        'closePosition': True,
                        'workingType': wt,
                    }
                )
                placed['tp'] = True
                break
            except Exception as e:
                log.debug(f"[Prot] {sym} TAKE_PROFIT_MARKET attempt "
                          f"{attempt+1} (closePosition) failed: {e}")
                try:
                    exchange.create_order(
                        sym, 'TAKE_PROFIT_MARKET', close_side, qty, None,
                        params={
                            'stopPrice': tp,
                            'reduceOnly': True,
                            'workingType': wt,
                        }
                    )
                    placed['tp'] = True
                    break
                except Exception as e2:
                    log.debug(f"[Prot] {sym} TAKE_PROFIT_MARKET attempt "
                              f"{attempt+1} (reduceOnly) failed: {e2}")

        if placed['sl'] and placed['tp']:
            log.info(f"[Prot] {sym} STOP@{sl:.6f} TP@{tp:.6f} placed")
            return True
        log.warning(f"[Prot] {sym} partial: sl={placed['sl']} tp={placed['tp']}")
        return placed['sl'] and placed['tp']
    except Exception as e:
        log.warning(f"[Prot] {sym} place_protective_orders fatal: {e}")
        return False


def _sync_protective_orders(exchange, sym: str, pos: Dict) -> bool:
    """
    Called from trailing when SL changes. Re-places both orders.
    Returns True if SL/TP now match pos.
    """
    if not getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        return False
    try:
        old_sl = pos.get('_prot_last_sl')
        old_tp = pos.get('_prot_last_tp')
        new_sl = float(pos.get('sl') or 0)
        new_tp = float(pos.get('tp1') or 0)
        if old_sl is None or old_tp is None:
            # Never placed before — place now
            ok = _place_protective_orders(exchange, sym, pos)
            if ok:
                pos['_prot_last_sl'] = new_sl
                pos['_prot_last_tp'] = new_tp
            return ok

        # Only resync if SL moved meaningfully
        step = float(getattr(CFG, 'PROTECTIVE_SYNC_MIN_STEP_FRAC', 0.001))
        if (new_sl > 0 and old_sl > 0
                and abs(new_sl - old_sl) / max(old_sl, 1e-12) < step):
            return True
        ok = _place_protective_orders(exchange, sym, pos)
        if ok:
            pos['_prot_last_sl'] = new_sl
            pos['_prot_last_tp'] = new_tp
        return ok
    except Exception as e:
        log.warning(f"[Prot] {sym} sync fatal: {e}")
        return False
```

---

## 🔧 التعديل ③ — إضافة `execute_post_only` خيار `cross_spread`

**الموقع:** توقيع الدالة `execute_post_only`.

**❌ استبدل السطر:**

```python
def execute_post_only(exchange, symbol: str, side: str, qty: float,
                      penetration_bps: float = None,
                      max_wait_s: int = None,
                      reprice_s: float = None,
                      fallback_market: bool = False,
                      fixed_target: Optional[float] = None):
```

**✅ بـ:**

```python
def execute_post_only(exchange, symbol: str, side: str, qty: float,
                      penetration_bps: float = None,
                      max_wait_s: int = None,
                      reprice_s: float = None,
                      fallback_market: bool = False,
                      fixed_target: Optional[float] = None,
                      cross_spread: bool = False):
    """
    cross_spread=True → Marketable limit: place SELL at best_bid,
    BUY at best_ask. Fills immediately as taker at ~1 spread cost
    (typically 2-5 bps). No GTX post-only parameter.
    """
```

**❌ ثم ابحث عن كتلة تحديد `target`:**

```python
            _fixed = (fixed_target is not None and fixed_target > 0)
            if _fixed:
                target = float(fixed_target)
            else:
                _base = last_bid if side == 'buy' else last_ask
                if (getattr(CFG, 'PO_USE_TICK_PENETRATION', True)
                        and _tick and _tick > 0 and _base > 0):
                    # Convert bps to ticks, ensure ≥ 1 tick penetration
                    _pen_abs = max(pen * _base, _tick)
                    _pen_ticks = int(np.ceil(_pen_abs / _tick))
                    _pen_abs = _pen_ticks * _tick
                    target = (_base - _pen_abs if side == 'buy'
                              else _base + _pen_abs)
                else:
                    target = (_base * (1.0 - pen) if side == 'buy'
                              else _base * (1.0 + pen))
```

**✅ استبدلها بـ:**

```python
            _fixed = (fixed_target is not None and fixed_target > 0)
            if _fixed:
                target = float(fixed_target)
            elif cross_spread:
                # Marketable limit — cross the spread for immediate fill.
                # SELL exits: at best_bid. BUY exits: at best_ask.
                _base = last_ask if side == 'buy' else last_bid
                target = float(_base)
            else:
                _base = last_bid if side == 'buy' else last_ask
                if (getattr(CFG, 'PO_USE_TICK_PENETRATION', True)
                        and _tick and _tick > 0 and _base > 0):
                    _pen_abs = max(pen * _base, _tick)
                    _pen_ticks = int(np.ceil(_pen_abs / _tick))
                    _pen_abs = _pen_ticks * _tick
                    target = (_base - _pen_abs if side == 'buy'
                              else _base + _pen_abs)
                else:
                    target = (_base * (1.0 - pen) if side == 'buy'
                              else _base * (1.0 + pen))
```

**❌ ثم ابحث عن بلوك `create_order` الأول (داخل حلقة الإعادة):**

```python
            # 7. Place new order (only if there is meaningful remaining)
            if active is None and remaining > 0:
                if total_filled >= qty * 0.90:
                    break
                try:
                    o = exchange.create_order(
                        symbol, 'limit', side, remaining, target,
                        params={'timeInForce': 'GTX'}
                    )
```

**✅ استبدله بـ:**

```python
            # 7. Place new order (only if there is meaningful remaining)
            if active is None and remaining > 0:
                if total_filled >= qty * 0.90:
                    break
                try:
                    # GTX = post-only (must not cross book). Do NOT use it
                    # for marketable limit — the exchange would reject.
                    _ord_params = {} if cross_spread else {'timeInForce': 'GTX'}
                    o = exchange.create_order(
                        symbol, 'limit', side, remaining, target,
                        params=_ord_params
                    )
```

---

## 🔧 التعديل ④ — تعديل مسار الخروج في `run_live`

**الموقع:** داخل `run_live`، في بلوك `# ── Execute exit ──`.

**❌ استبدل الكتلة كاملة:**

```python
                # ── Execute exit ──
                try:
                    s = 'sell' if pos['action'] == 'BUY' else 'buy'
                    is_emergency = 'Emergency' in rsn

                    if is_emergency:
                        # Emergency → market directly
                        try:
                            o = exchange.create_order(sym, 'market', s, pos['qty'])
                            v = verify_fill(exchange, o['id'], sym, timeout_s=1.5)
                            exec_price = v['avg_price'] if v and v['filled'] else price
                            exit_reason = f"{rsn} (market)"
                        except Exception as e:
                            log.error(f"[Exit] market failed {sym}: {e}")
                            continue
                    else:
                        # ══ [TF-FIX] use actual bar duration ══
                        _tf_sec_wait = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
#                        result = execute_limit_wait(
#                            exchange, sym, sd, qty, sig.price,
#                            wait_s=CFG.FILL_ENTRY_MAX_WAIT_BARS * _tf_sec_wait
#                        )
                        result = execute_post_only(
                            exchange, sym, s, pos['qty'],
                            max_wait_s=CFG.PO_EXIT_MAX_WAIT_S,
                            fallback_market=CFG.PO_EXIT_FALLBACK_MARKET,
                        )

                        if not result['filled_qty'] or result['filled_qty'] <= 0:
                            log.warning(f"⚠️ [Exit] {sym} no fill "
                                        f"({result['reason']}) — retry next loop")
                            continue
                        exec_price = result['avg_price']
                        exit_reason = f"{rsn} ({result['reason']})"

                    del open_pos_live[sym]
                    # ══ [RE-ENTRY COOLDOWN] record exit time ══
                    last_exit_time[sym] = time.time()
                    log.info(f"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]")
                except Exception as e:
                    log.error(f"خطأ أثناء الإغلاق لـ {sym}: {e}")
```

**✅ بـ:**

```python
                # ── Execute exit ──
                try:
                    s = 'sell' if pos['action'] == 'BUY' else 'buy'

                    # ══ [LAYER 7] Cancel protective orders BEFORE any bot exit ══
                    # If we don't, the exchange might fire SL/TP while our
                    # exit order is also in flight → double-close attempt.
                    _cancel_all_protective_orders(exchange, sym)

                    # ══ [LATENCY] Classify urgency ══
                    _urgent = (
                        'Emergency' in rsn
                        or 'Hard TP' in rsn
                        or 'LiqProximity' in rsn
                    )

                    if 'Emergency LiqProximity' in rsn:
                        # Absolute last resort — market (Liq is imminent)
                        try:
                            o = exchange.create_order(sym, 'market', s, pos['qty'])
                            v = verify_fill(exchange, o['id'], sym, timeout_s=1.5)
                            exec_price = v['avg_price'] if v and v['filled'] else price
                            exit_reason = f"{rsn} (market)"
                        except Exception as e:
                            log.error(f"[Exit] market failed {sym}: {e}")
                            continue
                    else:
                        # Marketable limit for urgent, post-only for soft.
                        _cross = bool(_urgent and
                                      getattr(CFG, 'PO_EXIT_URGENT_CROSS_SPREAD', True))
                        _wait = (
                            int(getattr(CFG, 'PO_EXIT_URGENT_WAIT_S', 4))
                            if _urgent
                            else int(CFG.PO_EXIT_MAX_WAIT_S)
                        )
                        result = execute_post_only(
                            exchange, sym, s, pos['qty'],
                            max_wait_s=_wait,
                            fallback_market=False,   # never raw market
                            cross_spread=_cross,
                        )

                        if not result['filled_qty'] or result['filled_qty'] <= 0:
                            log.warning(f"⚠️ [Exit] {sym} no fill "
                                        f"({result['reason']}) — retry next loop")
                            continue
                        exec_price = result['avg_price']
                        exit_reason = f"{rsn} ({result['reason']})"

                    del open_pos_live[sym]
                    last_exit_time[sym] = time.time()
                    log.info(f"⬛ [Exit] {sym} @ {exec_price:.6f} [{exit_reason}]")
                except Exception as e:
                    log.error(f"خطأ أثناء الإغلاق لـ {sym}: {e}")
```

---

## 🔧 التعديل ⑤ — ترقية الدالة `_promote_pending_to_position` لإطلاق Layer 7

**الموقع:** الدالة `_promote_pending_to_position`، بعد بلوك `open_pos_live[sym] = {...}` مباشرة.

**❌ ابحث عن:**

```python
    log.info(
        f"✅ [Pending→Entry] {rec['action']} {sym} @ {entry_price:.6f} "
        f"qty={filled_qty:.6f} (fill={fill_ratio*100:.0f}%) "
        f"sl={adapted_sl:.6f} tp={adapted_tp:.6f}"
    )
    return True
```

**✅ استبدله بـ:**

```python
    log.info(
        f"✅ [Pending→Entry] {rec['action']} {sym} @ {entry_price:.6f} "
        f"qty={filled_qty:.6f} (fill={fill_ratio*100:.0f}%) "
        f"sl={adapted_sl:.6f} tp={adapted_tp:.6f}"
    )

    # ══ [LAYER 7] Place protective orders on the exchange ══
    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        try:
            _ok = _place_protective_orders(exchange, sym, open_pos_live[sym])
            if _ok:
                open_pos_live[sym]['_prot_last_sl'] = float(adapted_sl)
                open_pos_live[sym]['_prot_last_tp'] = float(adapted_tp)
            else:
                log.warning(f"[Prot] {sym} protective orders not placed — "
                            f"bot will monitor manually")
        except Exception as _e:
            log.warning(f"[Prot] {sym} placement error: {_e}")

    return True
```

---

## 🔧 التعديل ⑥ — مزامنة Layer 7 عند تحديث Trailing

**الموقع:** داخل `run_live`، في حلقة المراقبة، بعد بلوك تحديث `pos['sl']` في Trailing.

**❌ ابحث عن نهاية كتلة Trailing:**

```python
                # ── Trailing SL (dynamic σ-scaled) ──
                if not ex:
                    entry_px = pos['entry']
                    _td = float(pos.get('trail_dist_frac', CFG.TRAIL_DISTANCE))
                    _ta = float(pos.get('trail_activate_frac', CFG.TRAIL_ACTIVATE_MFE))

                    # Update peak from live price
                    if pos['action'] == "BUY":
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price > cur_peak:
                            pos['peak_price'] = price
                            cur_peak = price
                        if (cur_peak - entry_px) / entry_px >= _ta:
                            new_sl = cur_peak * (1.0 - _td)
                            if new_sl > pos['sl']:
                                pos['sl'] = new_sl
                    else:
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price < cur_peak or cur_peak == entry_px:
                            pos['peak_price'] = price
                            cur_peak = price
                        if (entry_px - cur_peak) / entry_px >= _ta:
                            new_sl = cur_peak * (1.0 + _td)
                            if new_sl < pos['sl']:
                                pos['sl'] = new_sl
```

**✅ أضف سطراً واحداً قبل نهاية هذه الكتلة — بعد بلوك `if pos['action'] == "BUY": ... else: ...` مباشرة:**

```python
                # ── Trailing SL (dynamic σ-scaled) ──
                if not ex:
                    entry_px = pos['entry']
                    _td = float(pos.get('trail_dist_frac', CFG.TRAIL_DISTANCE))
                    _ta = float(pos.get('trail_activate_frac', CFG.TRAIL_ACTIVATE_MFE))
                    _sl_before = float(pos['sl'])

                    # Update peak from live price
                    if pos['action'] == "BUY":
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price > cur_peak:
                            pos['peak_price'] = price
                            cur_peak = price
                        if (cur_peak - entry_px) / entry_px >= _ta:
                            new_sl = cur_peak * (1.0 - _td)
                            if new_sl > pos['sl']:
                                pos['sl'] = new_sl
                    else:
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price < cur_peak or cur_peak == entry_px:
                            pos['peak_price'] = price
                            cur_peak = price
                        if (entry_px - cur_peak) / entry_px >= _ta:
                            new_sl = cur_peak * (1.0 + _td)
                            if new_sl < pos['sl']:
                                pos['sl'] = new_sl

                    # ══ [LAYER 7] If SL moved, sync protective orders ══
                    if (getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True)
                            and abs(float(pos['sl']) - _sl_before)
                                > 1e-12):
                        try:
                            _sync_protective_orders(exchange, sym, pos)
                        except Exception as _e:
                            log.debug(f"[Prot] {sym} sync error: {_e}")
```

---

## 🔧 التعديل ⑦ — مزامنة Layer 7 عند إعادة التشغيل

**الموقع:** داخل `run_live`، بعد حلقة `reconcile_state_machine` الأولى (بعد `log.info(f"  [State] After initial sync: ...")`).

**❌ ابحث عن:**

```python
    open_pos_live = reconcile_state_machine(exchange, open_pos_live, _pre_syms)
    log.info(f"  [State] After initial sync: {len(open_pos_live)} positions")
```

**✅ استبدله بـ:**

```python
    open_pos_live = reconcile_state_machine(exchange, open_pos_live, _pre_syms)
    log.info(f"  [State] After initial sync: {len(open_pos_live)} positions")

    # ══ [LAYER 7] Ensure every restored position has fresh protective orders ══
    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
        _prot_ok = 0
        _prot_fail = 0
        for _sym_p, _pos_p in open_pos_live.items():
            # Clear stale cache so we force re-place
            _pos_p.pop('_prot_last_sl', None)
            _pos_p.pop('_prot_last_tp', None)
            try:
                if _place_protective_orders(exchange, _sym_p, _pos_p):
                    _pos_p['_prot_last_sl'] = float(_pos_p.get('sl') or 0)
                    _pos_p['_prot_last_tp'] = float(_pos_p.get('tp1') or 0)
                    _prot_ok += 1
                else:
                    _prot_fail += 1
            except Exception as _e:
                log.warning(f"[Prot] restore {_sym_p} failed: {_e}")
                _prot_fail += 1
        log.info(f"  [Prot] restored={_prot_ok} failed={_prot_fail}")
```

---

## 📋 جدول السلوك المتوقع

| الحالة | قبل | بعد |
|---|---|---|
| WIF Hard TP | انتظار 45s + market_fallback | marketable limit، ~1-2s، 1 spread cost |
| Emergency SL في السوق | market + انزلاق | exchange's STOP_MARKET يضرب تلقائياً |
| Trailing SL محدَّث | داخلي فقط | يُلغى STOP القديم ويُوضع جديد |
| البوت يموت | المركز بلا حماية | STOP/TP على البورصة يبقيان نشطين |
| Restart | لا يوجد ربط بـ SL/TP | يُعاد وضع الأوامر تلقائياً |
| Apex/Topo-Div exit | قد يُقاطع SL | يُلغى STOP ثم يُنفَّذ exit |

---

## ✅ التحقق

### 1. فحص الملف
```bash
grep -c "_place_protective_orders" trading.py
# متوقع: 4 (تعريف + 3 استدعاءات)

grep -c "_sync_protective_orders" trading.py
# متوقع: 2 (تعريف + 1 استدعاء)

grep -c "_cancel_all_protective_orders" trading.py
# متوقع: 3 (تعريف + 2 استدعاءات)

grep -c "cross_spread" trading.py
# متوقع: 5 (توقيع + 2 استخدامات + 2 في run_live)
```

### 2. اختبار على testnet
```bash
rm -f live_state_testnet.json pending_orders_testnet.json
python trading.py --mode testnet --timeframe 1h --nassets 30 --maxcon 3 \
  --api-key $KEY --api-secret $SECRET 2>&1 | tee run.txt
```

**ابحث في `run.txt` عن:**
```bash
grep "\[Prot\]" run.txt | head -20
# متوقع: أسطر "STOP@... TP@... placed" لكل مركز جديد

grep "Hard TP" run.txt
# متوقع: (marketable) بدلاً من (market_fallback)

grep -c "market_fallback" run.txt
# متوقع: 0 أو نادر جداً
```

### 3. فحص أوامر البورصة بعد ساعة
على واجهة testnet، افتح صفحة Open Orders. يجب أن ترى لكل مركز:
- أمر STOP_MARKET بـ stopPrice = SL
- أمر TAKE_PROFIT_MARKET بـ stopPrice = TP

إذا رأيت أكثر من 2 لكل رمز → bug في `_cancel_all_protective_orders`. أرسل لي.

---

## ⚠️ تنبيهان حرجان

**التنبيه ① — `closePosition=True`** قد لا يكون مدعوماً على بعض testnets. التعديل ② يتعامل مع هذا: عند فشل `closePosition`، يُجرَّب `reduceOnly + explicit qty`. إذا فشل الاثنان، يسجّل warning ويكمل (البوت يراقب يدوياً).

**التنبيه ② — cancel/replace race**: أثناء تحديث SL، بين cancel القديم و place الجديد، قد تصل لحظة بلا حماية على البورصة. لحماية هذا، `_place_protective_orders` يبقي فحص البوت الداخلي نشطاً كطبقة ثانية. بالتالي حتى لو حدث race، الحماية المزدوجة تغطي.

**التنبيه ③ — orphan orders**: عندما يضرب SL، البورصة تُغلق المركز. لكن TAKE_PROFIT_MARKET يبقى مع `closePosition=True` — Binance يلغيه تلقائياً عند انتهاء المركز. على منصات أخرى، قد يبقى. `reconcile_state_machine` سيكتشف المركز مغلقاً في الدورة التالية، ويمكن إضافة تنظيف تلقائي بعد أسبوع من المراقبة.

بعد التطبيق، شغّل 4 ساعات وأرسل:
1. `grep "\[Prot\]"` كاملاً
2. `grep "Hard TP\|Emergency SL"` (يجب أن تُظهر marketable هذه المرة)
3. أي تحذير `partial` أو `failed`
