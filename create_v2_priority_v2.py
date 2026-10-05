#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_v2_priority_v2.py — إصلاح V2 priority queue.

الخطأ الأصلي: heap يتراكم بإشارات قديمة لا تُنفَّذ ولا تُطرَد.
الإصلاح: deque + age-based eviction + highest-score selection.

الفرق الجوهري:
  - V1: كل إشارة لها فرصة واحدة فقط، تفشل أو تنجح.
  - V2 (صحيح): الإشارة تبقى حية max_pending_bars، تُعاد محاولتها
    كل شمعة حتى تُفتح أو يُتجاوز عمرها.
"""

import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path


SRC = "trading_rnd_sell_only.py"
DST = "trading_rnd_v2_priority.py"


# ═══════════════════════════════════════════════════════════════
# Patch 1: Config flags
# ═══════════════════════════════════════════════════════════════

P1_ANCHOR = "    GAUGE_DISABLE_SELL: bool = True    # Default: BUY-only"
P1_NEW = """    GAUGE_DISABLE_SELL: bool = True    # Default: BUY-only

    # ══ [PRIORITY-SIM] محاكاة بقائمة انتظار ══
    SIG_PENDING_MODE: bool = False
    SIG_MAX_PENDING_BARS: int = 8       # أقصى عمر للإشارة في الانتظار"""


# ═══════════════════════════════════════════════════════════════
# Patch 2: Dispatch in simulate_portfolio
# ═══════════════════════════════════════════════════════════════

P2_ANCHOR = '''    """
    محاكاة المحفظة متعددة المراكز (Backtest Engine):
    - تطبق قانون القوة (Power-Law Scaling) لتعديل المخاطرة ديناميكياً.
    - تقضي على انحياز النظر للمستقبل (Causality Enforcement) بالدخول اللحظي بسعر النفق.
    - تحاكي الوقف والهدف بناءً على حركات ذيول الشموع اللحظية (High/Low).
    """
    capital  = CFG.INITIAL_CAPITAL'''

P2_NEW = '''    """
    محاكاة المحفظة متعددة المراكز (Backtest Engine):
    - تطبق قانون القوة (Power-Law Scaling) لتعديل المخاطرة ديناميكياً.
    - تقضي على انحياز النظر للمستقبل (Causality Enforcement) بالدخول اللحظي بسعر النفق.
    - تحاكي الوقف والهدف بناءً على حركات ذيول الشموع اللحظية (High/Low).
    """
    # [PRIORITY-SIM] Dispatch
    if getattr(CFG, 'SIG_PENDING_MODE', False):
        return _simulate_portfolio_priority(
            signals, assets, corr_matrix, mode
        )
    capital  = CFG.INITIAL_CAPITAL'''


# ═══════════════════════════════════════════════════════════════
# Patch 3: New function (corrected algorithm)
# ═══════════════════════════════════════════════════════════════

NEW_FUNC = '''


# ════════════════════════════════════════════════════════════════
# [PRIORITY-SIM] محاكاة بأولوية الإشارة — النسخة المُصلَحة
# ════════════════════════════════════════════════════════════════
def _simulate_portfolio_priority(signals, assets, corr_matrix,
                                   mode="backtest"):
    """
    محاكاة بقائمة انتظار محدودة العمر.

    الفرق عن V1:
      V1: كل إشارة تُعالَج مرة واحدة عند ظهورها. إذا فشلت، تُفقد.
      V2: الإشارة تبقى حية حتى SIG_MAX_PENDING_BARS. كلما شغر slot،
          نختار أعلى score من القائمة الحية. الإشارات القديمة تُطرَد.

    هذا يُعطي كل إشارة فرصة حقيقية للتنفيذ عندما يكون slot متاحاً.
    """
    from collections import deque

    capital = CFG.INITIAL_CAPITAL
    peak_cap = capital
    equity = [capital]
    trades_out = []
    open_pos = {}
    last_exit_ci = {}

    # ── fill_map ──
    _tf_sec = CFG.TF_SECONDS if CFG.TF_SECONDS > 0 else 3600
    _sim_live = bool(getattr(CFG, 'SIMULATE_LIVE_FAITHFULLY', False))
    if _sim_live:
        _live_wait_cap_s = float(getattr(CFG, 'PO_MAX_WAIT_S', 0) or 0)
        if _live_wait_cap_s > 0:
            _bars_from_seconds = max(
                1, int(np.ceil(_live_wait_cap_s / _tf_sec))
            )
        else:
            _bars_from_seconds = effective_bars(
                CFG.FILL_ENTRY_MAX_WAIT_BARS
            )
        _effective_wait_bars = min(
            effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS),
            _bars_from_seconds,
        )
    else:
        _effective_wait_bars = effective_bars(CFG.FILL_ENTRY_MAX_WAIT_BARS)

    _td_enabled = _sim_live and bool(getattr(CFG, 'ENTRY_TIME_DECAY', False))

    if (not WATCH_REMOVED) and getattr(CFG, 'WATCH_MODE_ENABLED', False):
        fill_map = _precompute_watch_fills(assets, signals)
    else:
        fill_map = precompute_entry_fills(
            assets, signals,
            max_wait_bars=_effective_wait_bars,
            pen_bps=CFG.FILL_PENETRATION_BPS,
            time_decay_enabled=_td_enabled,
            time_decay_bars=(CFG.ENTRY_TIME_DECAY_BARS_1,
                             CFG.ENTRY_TIME_DECAY_BARS_2,
                             CFG.ENTRY_TIME_DECAY_BARS_3),
            time_decay_mults=(CFG.ENTRY_TIME_DECAY_MULT_1,
                              CFG.ENTRY_TIME_DECAY_MULT_2,
                              CFG.ENTRY_TIME_DECAY_MULT_3),
            use_time_decay_price=_td_enabled,
        )

    # ── _close ──
    def _close(pos, ad, exit_px, exit_rsn, exit_ci):
        nonlocal capital, peak_cap
        sig = pos.signal
        exit_act = "SELL" if sig.action == "BUY" else "BUY"
        adv_here = ad.adv_usd[min(exit_ci, len(ad.adv_usd) - 1)]
        _is_taker = _exit_is_taker(exit_rsn)
        exit_eff = apply_slippage(exit_px, pos.pos_size, adv_here,
                                   exit_act, mode, is_taker=_is_taker)
        slip_x = abs(exit_eff - exit_px) * pos.pos_size
        if sig.action == "BUY":
            gross = (exit_eff - pos.entry_px) * pos.pos_size
        else:
            gross = (pos.entry_px - exit_eff) * pos.pos_size
        entry_fee = pos.pos_size * pos.entry_px * CFG.MAKER_FEE
        _exit_fee_rate = CFG.TAKER_FEE if _is_taker else CFG.MAKER_FEE
        exit_fee = pos.pos_size * exit_eff * _exit_fee_rate
        fee = entry_fee + exit_fee
        hold_bars = exit_ci - pos.entry_ci
        funding_payments = max(0, hold_bars) // CFG.FUNDING_INTERVAL_BARS
        funding_cost = (pos.pos_size * pos.entry_px *
                        CFG.FUNDING_RATE_COST * funding_payments)
        _partial = float(getattr(pos, 'partial_pnl', 0.0))
        net = gross - fee - funding_cost + _partial
        cap0 = pos.entry_cap
        capital = max(capital + (net - _partial), 0.)
        peak_cap = max(peak_cap, capital)
        equity.append(capital)
        lr = float(np.log((cap0 + net) / cap0)) if cap0 > 0 else 0.
        lw = ((pos.pos_size * pos.entry_px) >
              (adv_here * 24 * CFG.MAX_ADV_FRACTION))
        trades_out.append(Trade(
            symbol=sig.symbol, action=sig.action,
            entry_price=pos.entry_px, exit_price=exit_eff,
            pos_size=pos.pos_size, gross_pnl=gross, fee=fee + slip_x,
            net_pnl=net, capital_after=capital, log_return=lr,
            entry_time=sig.timestamp, exit_reason=exit_rsn,
            score=sig.score, lam=sig.lam, liq_warn=lw,
            slippage_paid=pos.slip_paid + slip_x,
            entry_optimized=pos.opt_entry, tri_at_entry=pos.tri_entry,
            dynamic_risk_used=sig.dynamic_risk,
            T_info_at_entry=sig.T_info_val,
            mfe_frac=pos.mfe_frac,
        ))
        try:
            _trade_log_from_backtest(
                pos, ad, exit_eff, exit_rsn, exit_ci,
                pos.entry_cap, capital,
                net_pnl=net, log_return=lr,
            )
        except Exception:
            pass

    def _partial_tp(pos, px, ci):
        nonlocal capital, peak_cap
        sig = pos.signal
        _pct = float(getattr(CFG, 'PARTIAL_TP_PCT', 0.5))
        _close_qty = pos.pos_size * _pct
        if _close_qty <= 0:
            return
        if sig.action == "BUY":
            _gross = (px - pos.entry_px) * _close_qty
        else:
            _gross = (pos.entry_px - px) * _close_qty
        _entry_fee = _close_qty * pos.entry_px * CFG.MAKER_FEE
        _exit_fee = _close_qty * px * CFG.TAKER_FEE
        _net = _gross - (_entry_fee + _exit_fee)
        capital += _net
        peak_cap = max(peak_cap, capital)
        equity.append(capital)
        pos.partial_pnl += _net
        pos.pos_size -= _close_qty

    # ── _try_open (يدعم priority) ──
    def _try_open(sig, sig_i, current_ci):
        sym = sig.symbol
        if sym in open_pos:
            return False
        if capital <= 0:
            return False
        if CFG.REENTRY_COOLDOWN_ENABLED:
            _last = last_exit_ci.get(sym, -10**9)
            if (current_ci - _last) < CFG.REENTRY_COOLDOWN_BARS:
                return False
        drawdown = (peak_cap - capital) / (peak_cap + 1e-12)
        dd_mult = _get_risk_multiplier(drawdown)
        if len(open_pos) >= CFG.MAX_CONCURRENT_ASSETS:
            return False
        too_corr = any(
            abs(corr_matrix.get((sym, s), 0.)) > CFG.CORRELATION_THRESHOLD
            for s in open_pos
        )
        if too_corr:
            return False
        ad = assets.get(sym)
        if ad is None:
            return False
        fill_info = fill_map.get(sig_i)
        if fill_info is None:
            return False
        _is_stage2 = False
        _stage2_sl = _stage2_tp = _stage2_sl_dist = None
        if len(fill_info) >= 2 and isinstance(fill_info[0], str):
            if fill_info[0] == 'S1':
                _, opt_ci, opt_px = fill_info
            elif fill_info[0] == 'S2':
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist = \
                    fill_info
                _is_stage2 = True
            else:
                return False
        else:
            opt_ci, opt_px = fill_info

        opt_ci = int(opt_ci)
        opt_px = float(opt_px)

        # ★★ حدّث سعر الدخول إلى الوقت الحالي في Priority Mode ★★
        # هذا يمنع دخول صفقات بأسعار قديمة بعد انتظار طويل.
        if getattr(CFG, 'SIG_PENDING_MODE', False):
            ad_closes = ad.closes
            if opt_ci < len(ad_closes):
                current_px = float(ad_closes[opt_ci])
                if current_px > 0:
                    # أعد تكييف SL/TP مع السعر الحالي
                    if _is_stage2:
                        # احتفظ بعقد Stage 2 كما هو (تم حسابه على السعر الفعلي)
                        pass
                    else:
                        # Stage 1: أعد الحساب من السعر الحالي
                        _old_sl_dist = abs(sig.price - sig.sl)
                        _old_tp_dist = abs(sig.tp1 - sig.price)
                        if _old_sl_dist > 1e-12:
                            _rr = _old_tp_dist / _old_sl_dist
                            opt_px = current_px
                            if sig.action == "BUY":
                                sig.sl = opt_px - _old_sl_dist
                                sig.tp1 = opt_px + _old_sl_dist * _rr
                            else:
                                sig.sl = opt_px + _old_sl_dist
                                sig.tp1 = opt_px - _old_sl_dist * _rr

        if _is_stage2:
            sig.sl = float(_stage2_sl)
            sig.tp1 = float(_stage2_tp)

        opt_sub_idx = 0
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
                    opt_sub_idx = int(_idx[0])

        _design_sl_dist = abs(sig.price - sig.sl)
        _design_tp_dist = abs(sig.tp1 - sig.price)
        if _design_sl_dist <= 1e-12:
            return False
        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        if _design_sl_dist > opt_px * _max_sl_frac:
            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)
            _design_sl_dist = opt_px * _max_sl_frac
            _design_tp_dist = _design_sl_dist * _rr
        if sig.action == "BUY":
            sig.sl = opt_px - _design_sl_dist
            sig.tp1 = opt_px + _design_tp_dist
            sl_h = opt_px - _design_sl_dist
        else:
            sig.sl = opt_px + _design_sl_dist
            sig.tp1 = opt_px - _design_tp_dist
            sl_h = opt_px + _design_sl_dist
        sl_distance = _design_sl_dist
        delta = abs(opt_px - sl_h)
        if delta < 1e-8:
            return False

        free_ratio = max(0.0, (capital - CFG.CAPITAL_FLOOR) / capital)
        power_law_scale = np.sqrt(free_ratio)
        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)
        if risk_frac <= 0.0:
            return False
        risk_frac *= dd_mult * power_law_scale
        risk_frac = float(np.clip(
            risk_frac,
            CFG.MIN_RISK_PER_TRADE if CFG.BUDGET_ENABLED else CFG.MIN_RISK,
            CFG.MAX_RISK_PER_TRADE if CFG.BUDGET_ENABLED else CFG.MAX_RISK,
        ))
        equity_base = max(capital - CFG.CAPITAL_FLOOR, 0.0)
        risk_amt = equity_base * risk_frac
        qty = risk_amt / delta
        dynamic_leverage = compute_dynamic_leverage(capital, CFG)
        if _sim_live and getattr(CFG, 'LIQ_ENABLED', True):
            _mmr = float(CFG.LIQ_FALLBACK_MMR)
            _sl_frac_max = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
            _lev_by_liq = compute_max_leverage_by_liq(
                sl_frac_max=_sl_frac_max,
                mmr=_mmr,
                safety_mult=float(CFG.LIQ_SAFETY_MULT),
            )
            if dynamic_leverage > _lev_by_liq:
                dynamic_leverage = max(int(CFG.LEVERAGE_MIN), _lev_by_liq)
            if dynamic_leverage < int(CFG.LEVERAGE_MIN):
                return False
            _liq_px = compute_liquidation_price(
                opt_px, sig.action, dynamic_leverage, _mmr
            )
            _liq_gap = abs(opt_px - _liq_px)
            _sl_gap = abs(opt_px - sl_h)
            if (_liq_gap <= 1e-12 or
                    _sl_gap * float(CFG.LIQ_SAFETY_MULT) > _liq_gap):
                return False
        max_notional = capital * dynamic_leverage
        qty = min(qty, max_notional / opt_px)
        qty = cap_notional(qty, opt_px)
        if qty * opt_px < CFG.MIN_NOTIONAL:
            return False
        sig.dynamic_risk = float(risk_frac)
        eff_px = apply_slippage(opt_px, qty, sig.adv_usd, sig.action, mode)
        slip_paid = abs(eff_px - opt_px) * qty
        if sig.action == "BUY":
            sl_h = eff_px - sl_distance
        else:
            sl_h = eff_px + sl_distance
        delta = abs(eff_px - sl_h)
        if delta < 1e-8:
            return False
        qty = min(risk_amt / delta, max_notional / eff_px)
        qty = cap_notional(qty, eff_px)
        if qty * eff_px < CFG.MIN_NOTIONAL:
            return False
        entry_fi = max(0, min(opt_ci - ad.feat_start,
                              len(ad.E_therm) - 1))
        trail_d, trail_a = compute_trail_params(ad, entry_fi)
        open_pos[sym] = OpenPosition(
            symbol=sym, signal=sig,
            entry_px=eff_px, pos_size=qty, trail_sl=sl_h,
            entry_cap=capital, entry_ci=opt_ci, current_ci=opt_ci,
            slip_paid=slip_paid, opt_entry=False, tri_entry=sig.tri_val,
            trail_dist_frac=trail_d,
            trail_activate_frac=trail_a,
            sl_dist_initial=float(abs(eff_px - sl_h)),
            trail_peak_R=0.0,
            entry_sub_idx=opt_sub_idx,
        )
        return True

    # ═══════════════════════════════════════════════════════════
    # Main loop — priority-based
    # ═══════════════════════════════════════════════════════════
    max_pending_bars = int(getattr(CFG, 'SIG_MAX_PENDING_BARS', 8))

    from collections import defaultdict as _dd
    by_time = _dd(list)
    for i, s in enumerate(signals):
        by_time[s.timestamp].append((i, s))
    sorted_ts = sorted(by_time.keys())

    # pending: list of (sig_i, sig, entry_ts_bar)
    pending = []

    for ts in sorted_ts:
        if capital <= CFG.CAPITAL_FLOOR + 0.1:
            break

        # 1. Advance/close positions
        to_close = []
        for sym in list(open_pos.keys()):
            pos = open_pos[sym]
            ad = assets[sym]
            toci = _ts_to_ci(ad, ts)
            ep, er, ec = _advance(pos, ad, toci, partial_cb=_partial_tp)
            if ep > 0:
                _close(pos, ad, ep, er, ec)
                to_close.append(sym)
                last_exit_ci[sym] = int(ec)
        for sym in to_close:
            del open_pos[sym]

        # 2. Add new signals
        for sig_i, sig in by_time[ts]:
            pending.append([sig_i, sig])

        # 3. Evict old signals
        #    نقيس العمر بـ "شموع الأصل"
        _surviving = []
        for item in pending:
            sig_i, sig = item
            ad_sig = assets.get(sig.symbol)
            if ad_sig is None:
                continue
            cur_ci = _ts_to_ci(ad_sig, ts)
            age = cur_ci - int(sig.close_idx)
            if age < 0:
                continue  # future (shouldn't happen)
            if age <= max_pending_bars:
                _surviving.append(item)
        pending = _surviving

        # 4. Try to open — highest score first
        #    نكرّر حتى slots تمتلئ أو pending تفرغ
        _max_iter = 500  # safety
        _it = 0
        while (pending
               and len(open_pos) < CFG.MAX_CONCURRENT_ASSETS
               and _it < _max_iter):
            _it += 1
            # اختر أعلى score
            best_idx = -1
            best_score = -float('inf')
            for idx, item in enumerate(pending):
                if item[1].score > best_score:
                    best_score = item[1].score
                    best_idx = idx
            if best_idx < 0:
                break
            item = pending.pop(best_idx)
            sig_i, sig = item
            ad_sig = assets.get(sig.symbol)
            if ad_sig is None:
                continue
            cur_ci = _ts_to_ci(ad_sig, ts)
            _try_open(sig, sig_i, cur_ci)

    # End-of-data cleanup
    for sym, pos in list(open_pos.items()):
        ad = assets[sym]
        _advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp)
        ep = ad.closes[-1]
        _close(pos, ad, ep, "EndOfData", len(ad.closes) - 1)

    return trades_out, equity

'''


# ═══════════════════════════════════════════════════════════════
# Patch 4: CLI
# ═══════════════════════════════════════════════════════════════

P4_ANCHOR = '    p.add_argument("--enable-sell", action="store_true",\n                   help="Re-enable SELL signals (default: BUY-only)")'
P4_NEW = '''    p.add_argument("--enable-sell", action="store_true",
                   help="Re-enable SELL signals (default: BUY-only)")
    p.add_argument("--sig-pending-mode", action="store_true",
                   help="[PRIORITY-SIM] Enable priority queue simulation")
    p.add_argument("--sig-max-pending-bars", type=int, default=None,
                   help="[PRIORITY-SIM] Max pending age in bars (default 8)")'''


# ═══════════════════════════════════════════════════════════════
# Patch 5: main wiring
# ═══════════════════════════════════════════════════════════════

P5_ANCHOR = '''    if getattr(args, "enable_sell", False):
        CFG.GAUGE_DISABLE_SELL = False
        CFG.SELL_ENABLED = True
        log.info("[Gauge] SELL RE-ENABLED — experimental mode")'''
P5_NEW = '''    if getattr(args, "enable_sell", False):
        CFG.GAUGE_DISABLE_SELL = False
        CFG.SELL_ENABLED = True
        log.info("[Gauge] SELL RE-ENABLED — experimental mode")
    if getattr(args, "sig_pending_mode", False):
        CFG.SIG_PENDING_MODE = True
        log.info("[PrioritySim] ENABLED — deferred signal processing")
    if getattr(args, "sig_max_pending_bars", None) is not None:
        CFG.SIG_MAX_PENDING_BARS = int(args.sig_max_pending_bars)'''


def apply_patch(text, old, new, name):
    if new.strip() in text:
        return text, f"SKIP: {name}"
    if old not in text:
        return text, f"ERR: {name} (anchor missing)"
    return text.replace(old, new, 1), f"OK: {name}"


def main():
    src = Path(SRC)
    dst = Path(DST)
    if not src.exists():
        print(f"ERR: {SRC} not found")
        return 1

    if dst.exists():
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2(dst, dst.with_suffix(dst.suffix + f'.bak_{ts}'))
        print(f"  Backup: {dst}.bak_{ts}")

    text = src.read_text(encoding='utf-8')
    original = text

    print("=" * 70)
    print("  create_v2_priority_v2.py")
    print("=" * 70)
    print()

    for old, new, name in [
        (P1_ANCHOR, P1_NEW, "Config flags"),
        (P2_ANCHOR, P2_NEW, "Dispatch"),
        (P4_ANCHOR, P4_NEW, "CLI flags"),
        (P5_ANCHOR, P5_NEW, "main() wiring"),
    ]:
        text, s = apply_patch(text, old, new, name)
        print(f"  {s}")

    # Insert function BEFORE simulate_portfolio
    anchor_func = 'def simulate_portfolio(signals, assets, corr_matrix, mode="backtest"):'
    if anchor_func in text and "_simulate_portfolio_priority" not in text:
        text = text.replace(
            anchor_func,
            NEW_FUNC + '\n' + anchor_func,
            1,
        )
        print(f"  OK: Priority function inserted")
    else:
        print(f"  SKIP: Priority function (already present or anchor missing)")

    try:
        ast.parse(text)
        print("\n  OK: ast.parse")
    except SyntaxError as e:
        print(f"\n  ERR: syntax at {e.lineno}: {e.text}")
        return 3

    if text == original:
        print("\n  No changes")
        return 0

    dst.write_text(text, encoding='utf-8')
    print(f"\n  Written: {dst}")
    print(f"  Size: {len(text):,} chars")
    return 0


if __name__ == '__main__':
    sys.exit(main())
