#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_heisenberg_fix_pro.py
===========================
Applies the Heisenberg-fix + small-capital-safety patches to the ORIGINAL
version: trading_2_live4_claude2_v4_pro.py

Fixes:
  1) SL_WIDEN_MULT becomes a REAL multiplier (was a cap → swallowed physics)
  2) Apex becomes R-based (was absolute 0.5% → killed winners with wide SL)
  3) Topo-Div becomes R-based (was absolute → same issue)
  4) _get_min_notional() reads exchange-per-symbol value
  5) scan_top_assets: micro-capital filter picks only tradeable symbols
  6) Config values rebalanced for SL=3-6% physics
  7) Safety cap MAX_SL_SAFETY_FRAC = 15% of price (absolute)

Idempotent. Backup + syntax check. Usage:
    python3 apply_heisenberg_fix_pro.py            # apply
    python3 apply_heisenberg_fix_pro.py --check    # verify
    python3 apply_heisenberg_fix_pro.py --dry-run  # plan
"""

import argparse, ast, os, re, shutil, sys, time
from pathlib import Path

TARGET = "trading_2_live4_claude2_v4.py"


# ────────────────────────────────────────────────────────────
#  I/O helpers
# ────────────────────────────────────────────────────────────
def _read(p):
    with open(p, "r", encoding="utf-8", newline="") as f:
        return f.read()

def _write(p, t):
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(t)
    os.replace(tmp, p)

def _syntax_ok(t):
    try:
        ast.parse(t); return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"

def _backup(p):
    bak = p.with_name(f"{p.name}.bak.{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(p, bak); return bak

def _find_func_range(text, name):
    m = re.search(rf"^def {re.escape(name)}\(", text, re.MULTILINE)
    if not m: return None
    s = m.start(); rest = text[s+1:]
    nxt = re.search(r"\n(?=def [A-Za-z_]|class [A-Za-z_]|# [\u2550=])", rest)
    return (s, s + 1 + nxt.start() + 1) if nxt else (s, len(text))


def _apply_exact(text, old, new, marker):
    if marker and marker in text:
        return text, "already_applied"
    if old in text:
        return text.replace(old, new, 1), "applied"
    return text, "ANCHOR_NOT_FOUND"


def _apply_func(text, fname, body, marker):
    rng = _find_func_range(text, fname)
    if rng is None:
        return text, "FUNCTION_NOT_FOUND"
    s, e = rng
    if marker and marker in text[s:e]:
        return text, "already_applied"
    return text[:s] + body.rstrip() + "\n\n" + text[e:], "applied"


def _set_field(text, field, value):
    pat = rf"^(\s*{re.escape(field)}\s*:\s*\w+\s*=\s*)([^\s#]+)(\s*#.*)?$"
    m = re.search(pat, text, re.MULTILINE)
    if not m: return text, "FIELD_NOT_FOUND"
    if m.group(2).strip() == value.strip():
        return text, "already_applied"
    return re.sub(pat, lambda mm: f"{mm.group(1)}{value}{mm.group(3) or ''}",
                  text, count=1, flags=re.MULTILINE), "applied"


def _add_field(text, decl, after_field):
    name = decl.split(":")[0].strip()
    if re.search(rf"^\s*{re.escape(name)}\s*:", text, re.MULTILINE):
        return text, "already_applied"
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if re.match(rf"^\s*{re.escape(after_field)}\s*:", ln):
            lines.insert(i + 1, f"    {decl}")
            return "\n".join(lines), "applied"
    return text, "AFTER_FIELD_NOT_FOUND"


# ────────────────────────────────────────────────────────────
#  New function bodies
# ────────────────────────────────────────────────────────────

GET_MIN_NOTIONAL_NEW = '''_MIN_NOTIONAL_CACHE: Dict[str, float] = {}


def _get_min_notional(exchange, sym: str) -> float:
    """[MIN-NOTIONAL-FIX] read the real per-symbol minimum notional."""
    if sym in _MIN_NOTIONAL_CACHE:
        return _MIN_NOTIONAL_CACHE[sym]
    try:
        mkt = exchange.market(sym)
        if mkt is not None:
            for f in (mkt.get('info') or {}).get('filters') or []:
                if f.get('filterType') == 'MIN_NOTIONAL':
                    v = float(f.get('notional') or 0)
                    if v > 0:
                        _MIN_NOTIONAL_CACHE[sym] = v
                        return v
            cost = float(((mkt.get('limits') or {}).get('cost') or {}).get('min') or 0)
            if cost > 0:
                _MIN_NOTIONAL_CACHE[sym] = cost
                return cost
    except Exception:
        pass
    fb = float(getattr(CFG, 'MIN_NOTIONAL', 5.0))
    _MIN_NOTIONAL_CACHE[sym] = fb
    return fb


'''


APEX_NEW = '''def check_thermodynamic_apex(pos_action, entry_price, current_price, ad, fi,
                              sl_dist_frac=None):
    """
    Apex detector.
    [APEX-R-BASED] when sl_dist_frac is given, thresholds are in R-units
    (kappa * sl_dist_frac). Otherwise falls back to the sigma-based
    absolute mode (legacy).
    """
    if fi < 3:
        return False, ""
    try:
        sigma = float(ad.E_therm[fi]) if fi < len(ad.E_therm) else 0.01
        if not np.isfinite(sigma) or sigma <= 1e-6:
            sigma = 0.01
    except Exception:
        sigma = 0.01

    # R-based reference scale
    if sl_dist_frac is not None and sl_dist_frac > 0:
        ref = float(sl_dist_frac)
    else:
        ref = sigma

    if getattr(CFG, 'APEX_SIGMA_SCALED', True):
        KP = float(getattr(CFG, 'APEX_KAPPA_PNL', 0.5))
        KE = float(getattr(CFG, 'APEX_KAPPA_ENERGY', 0.5))
        KA = float(getattr(CFG, 'APEX_KAPPA_ACCEL', 0.3))
        min_pnl, energy_thr, accel_thr = KP * ref, KE * ref, KA * ref
    else:
        min_pnl, energy_thr, accel_thr = 0.005, 0.005, 0.003

    pnl = ((current_price - entry_price) / entry_price
           if pos_action == "BUY"
           else (entry_price - current_price) / entry_price)
    if pnl < min_pnl:
        return False, ""

    sum_dF = float(np.sum(ad.dF[fi - 2:fi + 1]))
    accel_mean = float(np.mean(ad.geodesic_accel[fi - 2:fi + 1]))
    energy_exhausted = (sum_dF > energy_thr)

    if pos_action == "BUY" and energy_exhausted and accel_mean < accel_thr:
        return True, "Apex: Action Integral Exhaustion"
    if pos_action == "SELL" and energy_exhausted and accel_mean > -accel_thr:
        return True, "Apex: Action Integral Exhaustion"
    return False, ""
'''


# ────────────────────────────────────────────────────────────
#  Exact-block patches
# ────────────────────────────────────────────────────────────

SCAN_FILTER_NEW = '''    if not sel:
        return _default_assets()[:n]

    # ══ [MICRO-CAPITAL FILTER] keep only tradeable symbols ══
    _cap = float(getattr(CFG, 'INITIAL_CAPITAL', 10.0))
    if _cap < 20.0:
        _max_eff_min = _cap * 5.0
        _keep = []
        _rejected = 0
        for _sym in sel:
            try:
                _mkt = exchange.market(_sym)
                _min_qty = float(
                    ((_mkt.get('limits') or {}).get('amount') or {})
                    .get('min') or 0)
                _tkr = tickers.get(_sym, {})
                _px = float(_tkr.get('last') or _tkr.get('close') or 0)
                _mn = _get_min_notional(exchange, _sym)
                _eff = (max(_mn, _min_qty * _px) if _px > 0 else _mn)
                if _eff <= _max_eff_min:
                    _keep.append(_sym)
                else:
                    _rejected += 1
                    log.debug(f"[MicroCap] {_sym} rejected: "
                              f"eff_min=${_eff:.2f} > ${_max_eff_min:.2f}")
            except Exception:
                _keep.append(_sym)
        if _keep:
            log.warning(f"[MicroCap] capital=${_cap:.2f} → "
                        f"{len(_keep)}/{len(sel)} pass "
                        f"(rejected {_rejected})")
            sel = _keep

    log.info(f"مسح الأصول: {len(sel)} عملة مختارة")
    return sel
'''

SCAN_FILTER_ANCHOR = '''    if not sel:
        return _default_assets()[:n]
    log.info(f"مسح الأصول: {len(sel)} عملة مختارة")
    return sel
'''


SIM_SL_OLD = """        # Clip SL to max_sl_frac × opt_px (entry-based cap)
        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        if _design_sl_dist > opt_px * _max_sl_frac:
            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)
            _design_sl_dist = opt_px * _max_sl_frac
            _design_tp_dist = _design_sl_dist * _rr
"""

SIM_SL_NEW = """        # [SL-WIDEN-FIX] SL_WIDEN_MULT is a real multiplier, not a cap
        _mult = float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        _design_sl_dist = _design_sl_dist * _mult
        _design_tp_dist = _design_tp_dist * _mult
        _hard_cap = float(getattr(CFG, 'MAX_SL_SAFETY_FRAC', 0.15))
        if _design_sl_dist > opt_px * _hard_cap:
            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)
            _design_sl_dist = opt_px * _hard_cap
            _design_tp_dist = _design_sl_dist * _rr
"""


SIM_MICRO_OLD = """        # ══ [MICRO-CAPITAL FIX] Force MIN_NOTIONAL ══
        if not_ < CFG.MIN_NOTIONAL:
            _forced_qty = CFG.MIN_NOTIONAL / opt_px
            _forced_risk_amt = _forced_qty * delta
            _forced_risk_frac = _forced_risk_amt / max(capital, 1e-9)
            if _forced_risk_frac > 2.0 * CFG.MAX_RISK_PER_TRADE:
                log.debug(
                    f"[MicroCap] {sym} REJECT: forced "
                    f"${CFG.MIN_NOTIONAL:.2f} needs "
                    f"{_forced_risk_frac*100:.1f}% risk "
                    f"(> {2*CFG.MAX_RISK_PER_TRADE*100:.1f}%)")
                continue
            qty = _forced_qty
            risk_frac = _forced_risk_frac
            not_ = CFG.MIN_NOTIONAL
            log.info(
                f"[MicroCap] {sym} forced to "
                f"${CFG.MIN_NOTIONAL:.2f} notional "
                f"(actual risk {_forced_risk_frac*100:.1f}%)")
"""

SIM_MICRO_NEW = """        # ══ [MICRO-CAPITAL FIX] Use exchange-per-symbol min notional ══
        _sym_min_notional = float(getattr(CFG, 'MIN_NOTIONAL', 5.0))  # backtest fallback
        if not_ < _sym_min_notional:
            _forced_qty = _sym_min_notional / opt_px
            _forced_risk_amt = _forced_qty * delta
            _forced_risk_frac = _forced_risk_amt / max(capital, 1e-9)
            _safety = float(getattr(CFG, 'MICRO_MIN_NOTIONAL_MULT', 2.0))
            if _forced_risk_frac > _safety * CFG.MAX_RISK_PER_TRADE:
                log.debug(
                    f"[MicroCap] {sym} REJECT: forced "
                    f"${_sym_min_notional:.2f} needs "
                    f"{_forced_risk_frac*100:.1f}% risk "
                    f"(> {_safety*CFG.MAX_RISK_PER_TRADE*100:.1f}%)")
                continue
            qty = _forced_qty
            risk_frac = _forced_risk_frac
            not_ = _sym_min_notional
            log.info(
                f"[MicroCap] {sym} forced to "
                f"${_sym_min_notional:.2f} notional "
                f"(actual risk {_forced_risk_frac*100:.1f}%)")
"""


LIVE_MICRO_OLD = """                    # ══ [MICRO-CAPITAL FIX] Force MIN_NOTIONAL ══
                    _notional_now = qty * lmt
                    if _notional_now < cfg.MIN_NOTIONAL:
                        _forced_qty = cfg.MIN_NOTIONAL / lmt
                        _forced_risk_amt = _forced_qty * delta
                        _forced_risk_frac = (
                            _forced_risk_amt / max(cap_live, 1e-9))
                        if _forced_risk_frac > 2.0 * CFG.MAX_RISK_PER_TRADE:
                            log.debug(
                                f"[MicroCap] {sym} REJECT: forced "
                                f"${cfg.MIN_NOTIONAL:.2f} needs "
                                f"{_forced_risk_frac*100:.1f}% risk")
                            continue
                        qty = _forced_qty
                        risk_frac = _forced_risk_frac
                        log.info(
                            f"[MicroCap] {sym} forced to "
                            f"${cfg.MIN_NOTIONAL:.2f} notional "
                            f"(actual risk {_forced_risk_frac*100:.1f}%)")
"""

LIVE_MICRO_NEW = """                    # ══ [MICRO-CAPITAL FIX] Use per-symbol min notional ══
                    _notional_now = qty * lmt
                    _sym_min_notional = float(_get_min_notional(exchange, sym))
                    if _notional_now < _sym_min_notional:
                        _forced_qty = _sym_min_notional / lmt
                        _forced_risk_amt = _forced_qty * delta
                        _forced_risk_frac = (
                            _forced_risk_amt / max(cap_live, 1e-9))
                        _safety = float(getattr(CFG, 'MICRO_MIN_NOTIONAL_MULT', 2.0))
                        if _forced_risk_frac > _safety * CFG.MAX_RISK_PER_TRADE:
                            log.debug(
                                f"[MicroCap] {sym} REJECT: forced "
                                f"${_sym_min_notional:.2f} needs "
                                f"{_forced_risk_frac*100:.1f}% risk")
                            continue
                        qty = _forced_qty
                        risk_frac = _forced_risk_frac
                        log.info(
                            f"[MicroCap] {sym} forced to "
                            f"${_sym_min_notional:.2f} notional "
                            f"(actual risk {_forced_risk_frac*100:.1f}%)")
"""


LV_CLIP_OLD = """def _lv_clip_sl(sig, sym='?') -> None:
    # backtest clips SL (and TP, keeping R:R) to max_sl_frac BEFORE sizing; live did it after.
    try:
        frac = 0.015 * float(_lv_cfg('SL_WIDEN_MULT', 1.0))
        px = float(sig.price)
        d = abs(px - float(sig.sl))
        if px > 0 and d > px * frac:
            rr = abs(float(sig.tp1) - px) / max(d, 1e-12)
            nd = px * frac
            if sig.action == 'BUY':
                sig.sl, sig.tp1 = px - nd, px + nd * rr
            else:
                sig.sl, sig.tp1 = px + nd, px - nd * rr
            log.info(f"[SL-Clip-Live] {sym} SL clipped {d:.6f} -> {nd:.6f} (before sizing)")
    except Exception as e:
        log.debug(f"[LV] clip failed: {e}")
"""

LV_CLIP_NEW = """def _lv_clip_sl(sig, sym='?') -> None:
    # [SL-WIDEN-FIX] Safety gate on raw physics distance.
    # MULT is applied later in place_pending_entry; this clip pre-cap so the
    # multiplied result stays under MAX_SL_SAFETY_FRAC.
    try:
        _mult = float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        _max_after = float(getattr(CFG, 'MAX_SL_SAFETY_FRAC', 0.15))
        frac = _max_after / max(_mult, 1e-9)
        px = float(sig.price)
        d = abs(px - float(sig.sl))
        if px > 0 and d > px * frac:
            rr = abs(float(sig.tp1) - px) / max(d, 1e-12)
            nd = px * frac
            if sig.action == 'BUY':
                sig.sl, sig.tp1 = px - nd, px + nd * rr
            else:
                sig.sl, sig.tp1 = px + nd, px - nd * rr
            log.info(f"[SL-Clip-Live] {sym} SL clipped {d:.6f} -> {nd:.6f} (raw cap)")
    except Exception as e:
        log.debug(f"[LV] clip failed: {e}")
"""


LV_ADOPT_OLD = """    max_sl_frac = 0.015 * float(_lv_cfg('SL_WIDEN_MULT', 1.0))
"""
LV_ADOPT_NEW = """    max_sl_frac = float(getattr(CFG, 'MAX_SL_SAFETY_FRAC', 0.15))
"""


PROMOTE_OLD = """    # Cap scales with widening so the loosened SL isn't re-clipped.
    max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
"""
PROMOTE_NEW = """    # Cap scales with widening so the loosened SL isn't re-clipped.
    max_sl_frac = float(getattr(CFG, 'MAX_SL_SAFETY_FRAC', 0.15))
"""


REV_FINALIZE_OLD = """    _max_sl_frac = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
    if orig_sl_dist > entry_px * _max_sl_frac:
        _rr = orig_tp_dist / max(orig_sl_dist, 1e-12)
        orig_sl_dist = entry_px * _max_sl_frac
        orig_tp_dist = orig_sl_dist * _rr
"""

REV_FINALIZE_NEW = """    _max_sl_frac = float(getattr(CFG, "MAX_SL_SAFETY_FRAC", 0.15))
    if orig_sl_dist > entry_px * _max_sl_frac:
        _rr = orig_tp_dist / max(orig_sl_dist, 1e-12)
        orig_sl_dist = entry_px * _max_sl_frac
        orig_tp_dist = orig_sl_dist * _rr
"""


LAD_OLD = """    mx = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
"""
LAD_NEW = """    mx = float(getattr(CFG, "MAX_SL_SAFETY_FRAC", 0.15))
"""


# place_pending_entry stores orig distances multiplied by MULT
PEND_STORE_OLD = """        'orig_sl_dist': float(abs(sig.price - sig.sl)),
        'orig_tp_dist': float(abs(sig.tp1 - sig.price)),
"""

PEND_STORE_NEW = """        'orig_sl_dist': float(abs(sig.price - sig.sl)) * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0)),
        'orig_tp_dist': float(abs(sig.tp1 - sig.price)) * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0)),
"""


# _register_reversal_watcher stores orig distances multiplied by MULT
REV_REG_OLD = """        "orig_sl_dist": float(abs(sig.price - sig.sl)),
        "orig_tp_dist": float(abs(sig.tp1 - sig.price)),
"""

REV_REG_NEW = """        "orig_sl_dist": float(abs(sig.price - sig.sl)) * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0)),
        "orig_tp_dist": float(abs(sig.tp1 - sig.price)) * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0)),
"""


APEX_CALL_BT_OLD = """        # ── Physics-based exits (close-only, per main bar) ──
        is_apex, apex_rsn = False, ""
        if getattr(CFG, 'APEX_ENABLED', True):
            is_apex, apex_rsn = check_thermodynamic_apex(
                sig.action, pos.entry_px, p, ad, fi
            )
"""

APEX_CALL_BT_NEW = """        # ── Physics-based exits (close-only, per main bar) ──
        is_apex, apex_rsn = False, ""
        if getattr(CFG, 'APEX_ENABLED', True):
            _apex_sl_frac = (pos.sl_dist_initial / pos.entry_px
                             if pos.entry_px > 0 and pos.sl_dist_initial > 0
                             else None)
            is_apex, apex_rsn = check_thermodynamic_apex(
                sig.action, pos.entry_px, p, ad, fi,
                sl_dist_frac=_apex_sl_frac,
            )
"""


APEX_CALL_LV_OLD = """                    # Apex
                    is_apex, apex_rsn = False, ""
                    if getattr(CFG, 'APEX_ENABLED', True):
                        is_apex, apex_rsn = check_thermodynamic_apex(
                            pos['action'], pos['entry'], _apex_price, ad, fi
                        )
"""

APEX_CALL_LV_NEW = """                    # Apex
                    is_apex, apex_rsn = False, ""
                    if getattr(CFG, 'APEX_ENABLED', True):
                        _apex_sl_frac = (
                            float(pos.get('sl_dist_initial', 0))
                            / float(pos.get('entry', 1))
                            if pos.get('entry', 0) > 0 else None)
                        is_apex, apex_rsn = check_thermodynamic_apex(
                            pos['action'], pos['entry'], _apex_price, ad, fi,
                            sl_dist_frac=_apex_sl_frac,
                        )
"""


TOPO_BT_OLD = """        if 0 < fi < len(ad.V) and cidx > 0:
            V_curr = ad.V[fi]
            V_prev = ad.V[fi - 1] if fi > 0 else V_curr
            div_t = (V_curr - V_prev) / (V_prev + 1e-12)
            dH_curr = ad.dH[fi] if fi < len(ad.dH) else 0.
            if div_t > CFG.TOPO_DIV_THRESHOLD and dH_curr > 0:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return p, f"Topo-Div({div_t:.3f})", cidx
"""

TOPO_BT_NEW = """        if 0 < fi < len(ad.V) and cidx > 0:
            V_curr = ad.V[fi]
            V_prev = ad.V[fi - 1] if fi > 0 else V_curr
            div_t = (V_curr - V_prev) / (V_prev + 1e-12)
            dH_curr = ad.dH[fi] if fi < len(ad.dH) else 0.
            # [TOPO-R-BASED] require >= TOPO_MIN_R_TO_EXIT R before Topo can exit
            _fi_sl_frac = (pos.sl_dist_initial / pos.entry_px
                           if pos.entry_px > 0 and pos.sl_dist_initial > 0
                           else 0.01)
            _fi_pnl_frac = ((p - pos.entry_px) / pos.entry_px
                            if sig.action == "BUY"
                            else (pos.entry_px - p) / pos.entry_px)
            _fi_R = _fi_pnl_frac / max(_fi_sl_frac, 1e-9)
            _topo_min_R = float(getattr(CFG, 'TOPO_MIN_R_TO_EXIT', 0.5))
            if (div_t > CFG.TOPO_DIV_THRESHOLD and dH_curr > 0
                    and _fi_R >= _topo_min_R):
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return p, f"Topo-Div({div_t:.3f},R={_fi_R:.1f})", cidx
"""


TOPO_LV_OLD = """                    # Topo-Div
                    if not ex and fi > 0:
                        div_t = (ad.V[fi] - ad.V[fi-1]) / (ad.V[fi-1] + 1e-12)
                        if div_t > cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0:
                            ex = True; rsn = f"Topo-Div({div_t:.3f})"
"""

TOPO_LV_NEW = """                    # Topo-Div
                    if not ex and fi > 0:
                        div_t = (ad.V[fi] - ad.V[fi-1]) / (ad.V[fi-1] + 1e-12)
                        _lv_sl_frac = (
                            float(pos.get('sl_dist_initial', 0))
                            / float(pos.get('entry', 1))
                            if pos.get('entry', 0) > 0 else 0.01)
                        _lv_pnl_frac = (
                            (float(price) - float(pos['entry'])) / float(pos['entry'])
                            if pos['action'] == "BUY"
                            else (float(pos['entry']) - float(price)) / float(pos['entry']))
                        _lv_R = _lv_pnl_frac / max(_lv_sl_frac, 1e-9)
                        _topo_min_R = float(getattr(CFG, 'TOPO_MIN_R_TO_EXIT', 0.5))
                        if (div_t > cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0
                                and _lv_R >= _topo_min_R):
                            ex = True; rsn = f"Topo-Div({div_t:.3f},R={_lv_R:.1f})"
"""


# ────────────────────────────────────────────────────────────
#  Patch list
# ────────────────────────────────────────────────────────────

PATCHES = [
    # ── Config value overrides ──
    {"name": "Config: SL_REF_KAPPA 4 → 2.5",
     "kind": "set_field", "field": "SL_REF_KAPPA", "value": "2.5"},
    {"name": "Config: SL_MIN_SIGMA 3.0 → 1.5",
     "kind": "set_field", "field": "SL_MIN_SIGMA", "value": "1.5"},
    {"name": "Config: SL_MAX_SIGMA 8.0 → 6.0",
     "kind": "set_field", "field": "SL_MAX_SIGMA", "value": "6.0"},
    {"name": "Config: SL_WIDEN_MULT 1.5 → 1.0",
     "kind": "set_field", "field": "SL_WIDEN_MULT", "value": "1.0"},
    {"name": "Config: TP_MULT 5.0 → 2.0",
     "kind": "set_field", "field": "TP_MULT", "value": "2.0"},
    {"name": "Config: PARTIAL_TP_R 1.5 → 1.0",
     "kind": "set_field", "field": "PARTIAL_TP_R", "value": "1.0"},
    {"name": "Config: LEVERAGE_BASE 50.0 → 20.0",
     "kind": "set_field", "field": "LEVERAGE_BASE", "value": "20.0"},
    {"name": "Config: MIN_NOTIONAL 5.0 → 2.0",
     "kind": "set_field", "field": "MIN_NOTIONAL", "value": "2.0"},

    # ── New config fields ──
    {"name": "Config: + MAX_SL_SAFETY_FRAC",
     "kind": "add_field",
     "decl": "MAX_SL_SAFETY_FRAC: float = 0.15",
     "after": "SL_WIDEN_MULT"},
    {"name": "Config: + MICRO_MIN_NOTIONAL_MULT",
     "kind": "add_field",
     "decl": "MICRO_MIN_NOTIONAL_MULT: float = 2.0",
     "after": "MAX_SL_SAFETY_FRAC"},
    {"name": "Config: + TOPO_MIN_R_TO_EXIT",
     "kind": "add_field",
     "decl": "TOPO_MIN_R_TO_EXIT: float = 0.5",
     "after": "MICRO_MIN_NOTIONAL_MULT"},

    # ── Add _get_min_notional() before scan_top_assets ──
    {"name": "New func: _get_min_notional",
     "kind": "exact",
     "old": "def scan_top_assets(exchange, n=None) -> List[str]:\n",
     "new": GET_MIN_NOTIONAL_NEW + "def scan_top_assets(exchange, n=None) -> List[str]:\n",
     "marker": "_get_min_notional"},

    # ── Micro-capital filter in scan_top_assets ──
    {"name": "scan_top_assets: micro-capital filter",
     "kind": "exact",
     "old": SCAN_FILTER_ANCHOR,
     "new": SCAN_FILTER_NEW,
     "marker": "[MICRO-CAPITAL FILTER]"},

    # ── Replace check_thermodynamic_apex ──
    {"name": "Func: check_thermodynamic_apex (R-based)",
     "kind": "func", "name_arg": "check_thermodynamic_apex",
     "body": APEX_NEW, "marker": "sl_dist_frac=None"},

    # ── simulate_portfolio ──
    {"name": "simulate: SL_WIDEN_MULT as multiplier",
     "kind": "exact", "old": SIM_SL_OLD, "new": SIM_SL_NEW,
     "marker": "[SL-WIDEN-FIX] SL_WIDEN_MULT is a real multiplier"},

    {"name": "simulate: per-symbol min notional",
     "kind": "exact", "old": SIM_MICRO_OLD, "new": SIM_MICRO_NEW,
     "marker": "MICRO_MIN_NOTIONAL_MULT"},

    # ── run_live micro-capital block ──
    {"name": "run_live: per-symbol min notional",
     "kind": "exact", "old": LIVE_MICRO_OLD, "new": LIVE_MICRO_NEW,
     "marker": "_get_min_notional(exchange, sym)"},

    # ── SL clipping helpers ──
    {"name": "_lv_clip_sl: raw-cap semantics",
     "kind": "exact", "old": LV_CLIP_OLD, "new": LV_CLIP_NEW,
     "marker": "[SL-WIDEN-FIX] Safety gate on raw physics distance"},

    {"name": "_lv_adopt: cap uses MAX_SL_SAFETY_FRAC",
     "kind": "exact", "old": LV_ADOPT_OLD, "new": LV_ADOPT_NEW,
     "marker": "max_sl_frac = float(getattr(CFG, 'MAX_SL_SAFETY_FRAC', 0.15))"},

    {"name": "_promote_pending: cap uses MAX_SL_SAFETY_FRAC",
     "kind": "exact", "old": PROMOTE_OLD, "new": PROMOTE_NEW,
     "marker": "max_sl_frac = float(getattr(CFG, 'MAX_SL_SAFETY_FRAC', 0.15))"},

    {"name": "_rev_finalize: cap uses MAX_SL_SAFETY_FRAC",
     "kind": "exact", "old": REV_FINALIZE_OLD, "new": REV_FINALIZE_NEW,
     "marker": '_max_sl_frac = float(getattr(CFG, "MAX_SL_SAFETY_FRAC", 0.15))'},

    {"name": "_lad_sl_tp: cap uses MAX_SL_SAFETY_FRAC",
     "kind": "exact", "old": LAD_OLD, "new": LAD_NEW,
     "marker": 'mx = float(getattr(CFG, "MAX_SL_SAFETY_FRAC", 0.15))'},

    # ── orig distance multiplied at storage time ──
    {"name": "place_pending_entry: MULT in orig_sl_dist",
     "kind": "exact", "old": PEND_STORE_OLD, "new": PEND_STORE_NEW,
     "marker": "'orig_sl_dist': float(abs(sig.price - sig.sl)) * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))"},

    {"name": "_register_reversal_watcher: MULT in orig_sl_dist",
     "kind": "exact", "old": REV_REG_OLD, "new": REV_REG_NEW,
     "marker": '"orig_sl_dist": float(abs(sig.price - sig.sl)) * float(getattr(CFG, \'SL_WIDEN_MULT\', 1.0))'},

    # ── Apex call sites ──
    {"name": "Apex backtest call: sl_dist_frac",
     "kind": "exact", "old": APEX_CALL_BT_OLD, "new": APEX_CALL_BT_NEW,
     "marker": "sl_dist_frac=_apex_sl_frac,"},

    {"name": "Apex live call: sl_dist_frac",
     "kind": "exact", "old": APEX_CALL_LV_OLD, "new": APEX_CALL_LV_NEW,
     "marker": "sl_dist_frac=_apex_sl_frac,"},

    # ── Topo-Div blocks ──
    {"name": "Topo-Div backtest: R-based",
     "kind": "exact", "old": TOPO_BT_OLD, "new": TOPO_BT_NEW,
     "marker": "[TOPO-R-BASED]"},

    {"name": "Topo-Div live: R-based",
     "kind": "exact", "old": TOPO_LV_OLD, "new": TOPO_LV_NEW,
     "marker": "_topo_min_R = float(getattr(CFG, 'TOPO_MIN_R_TO_EXIT', 0.5))"},
]


# ────────────────────────────────────────────────────────────
#  Main
# ────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=TARGET)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[ERROR] not found: {path}", file=sys.stderr); return 2

    print(f"[*] Target: {path}")
    print(f"[*] Size  : {path.stat().st_size:,} bytes")

    original = _read(path)
    ok, err = _syntax_ok(original)
    if not ok:
        print(f"[ERROR] pre-patch syntax: {err}", file=sys.stderr); return 3
    print("[OK] Original syntax verified.\n")

    text = original
    results = []
    for p in PATCHES:
        try:
            if p["kind"] == "set_field":
                text, st = _set_field(text, p["field"], p["value"])
            elif p["kind"] == "add_field":
                text, st = _add_field(text, p["decl"], p["after"])
            elif p["kind"] == "func":
                text, st = _apply_func(text, p["name_arg"], p["body"], p["marker"])
            elif p["kind"] == "exact":
                text, st = _apply_exact(text, p["old"], p["new"], p["marker"])
            else:
                st = f"UNKNOWN_KIND:{p['kind']}"
        except Exception as e:
            st = f"EXCEPTION:{e}"
        results.append((p["name"], st))
        icon = {"applied": "✅", "already_applied": "⏭️"}.get(st, "❌")
        print(f"  {icon} {p['name']:48s} [{st}]")

    failed = [r for r in results if "NOT_FOUND" in r[1] or "EXCEPTION" in r[1]]
    if failed:
        print(f"\n[ERROR] {len(failed)} patch(es) failed — nothing written.",
              file=sys.stderr)
        for n, s in failed: print(f"    • {n}: {s}", file=sys.stderr)
        if args.verbose:
            print("\n[INFO] Preview anchors of failed patches above.")
        return 4

    if text == original:
        print("\n[OK] No changes — file already patched.")
        return 0

    ok, err = _syntax_ok(text)
    if not ok:
        print(f"\n[ERROR] post-patch syntax: {err}", file=sys.stderr); return 5
    print("\n[OK] Patched syntax verified.")

    if args.check:
        print("[CHECK] All checks passed; write skipped.")
        return 0

    if args.dry_run:
        d = len(text.encode("utf-8")) - len(original.encode("utf-8"))
        print(f"[DRY-RUN] Would write {len(text.encode('utf-8')):,} "
              f"bytes (delta {d:+,})")
        return 0

    if not args.no_backup:
        bak = _backup(path); print(f"[OK] Backup: {bak}")

    _write(path, text)
    print(f"[OK] Wrote {len(text.encode('utf-8')):,} bytes")

    n_ap = sum(1 for _, s in results if s == "applied")
    n_sk = sum(1 for _, s in results if s == "already_applied")
    print(f"\n═══ Summary: {n_ap} applied, {n_sk} skipped ═══")
    return 0


if __name__ == "__main__":
    sys.exit(main())
