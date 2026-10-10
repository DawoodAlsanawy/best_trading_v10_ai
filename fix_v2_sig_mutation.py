#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_v2_sig_mutation.py — إصلاح تلوث كائن الإشارة.

المشكلة: _try_open يُعدّل sig.sl و sig.tp1 → المحاولات التالية تفشل.

الإصلاح:
  1. كل محاولة تعمل على copy.copy(sig)
  2. لا تُعدّل sig الأصلي
  3. عند النجاح، تُحدَّث القيم فقط في OpenPosition
"""

import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path

FILE = "trading_rnd_v2_priority.py"


# ═══════════════════════════════════════════════════════════════
# Patch 1: استبدال _try_open بنسخة نظيفة
# ═══════════════════════════════════════════════════════════════

# سطر بداية الدالة
TRY_OPEN_HEADER = "    def _try_open(sig, sig_i, current_ci):"

# الوصف يُظهر الاستبدال
NEW_TRY_OPEN = '''    def _try_open(sig_orig, sig_i, current_ci):
        """
        [MUTATION-FIX] يعمل على نسخة من الإشارة، لا يُعدّل الأصل.
        """
        import copy as _copy
        sig = _copy.copy(sig_orig)

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
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist = \\
                    fill_info
                _is_stage2 = True
            else:
                return False
        else:
            opt_ci, opt_px = fill_info

        opt_ci = int(opt_ci)
        opt_px = float(opt_px)

        # تحديث السعر إلى الوقت الحالي
        if getattr(CFG, 'SIG_PENDING_MODE', False):
            ad_closes = ad.closes
            if opt_ci < len(ad_closes):
                current_px = float(ad_closes[opt_ci])
                if current_px > 0 and not _is_stage2:
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
'''


def find_function_boundaries(text, header, next_marker):
    """يجد بداية ونهاية دالة داخل ملف."""
    start = text.find(header)
    if start < 0:
        return None, None
    # ابحث عن السطر التالي بمستوى indent أقل
    rest = text[start + len(header):]
    # next_marker هو أي سطر بمستوى indent 4 يبدأ دالة أخرى
    end_rel = rest.find(next_marker)
    if end_rel < 0:
        return start, None
    return start, start + len(header) + end_rel


def main():
    p = Path(FILE)
    if not p.exists():
        print(f"ERR: {FILE} not found")
        return 1

    text = p.read_text(encoding="utf-8")

    if "[MUTATION-FIX]" in text:
        print("SKIP: already applied")
        return 0

    # ابحث عن نهاية _try_open (الدالة التالية بعدها)
    start, end = find_function_boundaries(
        text, TRY_OPEN_HEADER, "    # ═══════════════════════════════════════════════════════════"
    )
    if start is None:
        print(f"ERR: header not found: {TRY_OPEN_HEADER}")
        return 2
    if end is None:
        print(f"ERR: end of function not found")
        return 3

    # استبدل الدالة القديمة بالجديدة
    text = text[:start] + NEW_TRY_OPEN + "\n" + text[end:]

    # تحقق
    try:
        ast.parse(text)
        print("OK: ast.parse")
    except SyntaxError as e:
        print(f"ERR: syntax at {e.lineno}: {e.text}")
        return 4

    # Backup
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_mut_{ts}')
    shutil.copy2(p, backup)
    print(f"Backup: {backup}")

    p.write_text(text, encoding="utf-8")
    print(f"OK: written {p}")
    print(f"Verification:")
    print(f"  - [MUTATION-FIX]: {text.count('[MUTATION-FIX]')}")
    print(f"  - def _try_open: {text.count('def _try_open')}")
    print(f"  - _copy.copy(sig_orig): {text.count('_copy.copy(sig_orig)')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
