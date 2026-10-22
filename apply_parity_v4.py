#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_parity_v4.py  [REV-FIX v4]

يطبق 4 تعديلات جراحية:
  1. REVERSAL_FILL_AT → "close"  (Parity حقيقي مع Live)
  2. REV_SUBBAR_ONLY flag + helper + APEX sub-bar close
  3. SL-Hybrid (Live + Ladder + Backtest): يحمي من "SL فوق الدعم"
  4. already_touched fix: closes[-1] → closes[close_idx]

Usage:
    python apply_parity_v4.py trading_2_live4.py --inplace
    python apply_parity_v4.py trading_2_live4.py --dry-run
"""
import argparse, ast, os, py_compile, shutil, sys, time

MARK = "[REV-FIX v4]"


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════
def _once(src, old, name):
    n = src.count(old)
    if n != 1:
        raise SystemExit(
            f"[ABORT] anchor '{name}' matched {n} times (expected 1). "
            f"الملف يختلف — لم يُكتب شيء."
        )


# ═══════════════════════════════════════════════════════════════
# PATCH 1 — REVERSAL_FILL_AT = "close"
# ═══════════════════════════════════════════════════════════════
P1_OLD = '    REVERSAL_FILL_AT:        str   = "target"  # [REV-FIX v1] realizable: confirm-bar close (was "target")\n'
P1_NEW = '    REVERSAL_FILL_AT:        str   = "close"   # [REV-FIX v4] realizable: confirm-bar close\n'


# ═══════════════════════════════════════════════════════════════
# PATCH 2A — REV_SUBBAR_ONLY flag + helper
# ═══════════════════════════════════════════════════════════════
P2A_OLD = (
    "    REV_LADDER_MIN_FILL_RATIO: float = 0.0              # >0: flatten ladders that end below this ratio\n"
)
P2A_NEW = (
    "    REV_LADDER_MIN_FILL_RATIO: float = 0.0              # >0: flatten ladders that end below this ratio\n"
    "    # ══ [REV-FIX v4] SUB-BAR PARITY — Live uses closed sub-bars only ══\n"
    "    # True  → APEX + physics exits use last closed sub-bar close\n"
    "    #         (matches backtest, ignores ticker noise)\n"
    "    # False → legacy ticker-based (faster, but drifts from backtest)\n"
    "    REV_SUBBAR_ONLY: bool = True\n"
)

# helper: added just before run_live
P2A_HELPER_ANCHOR = "def run_live(cfg, exchange):\n"
P2A_HELPER_BLOCK = '''def _last_closed_subbar_close(exchange, sym: str, sub_tf: str,
                               sub_sec: int):
    """
    [REV-FIX v4] آخر شمعة sub-bar مغلقة.
    يستخدم _fetch_live_subbars (throttle 30s) لتقليل API calls.
    Returns float أو None.
    """
    try:
        df = _fetch_live_subbars(exchange, sym, sub_tf, keep_bars=5)
        if df is None or len(df) == 0:
            return None
        df_c = _only_closed_subbars(df, sub_sec)
        if df_c is None or len(df_c) == 0:
            return None
        return float(df_c["Close"].iloc[-1])
    except Exception as e:
        log.debug(f"[Subbar-Parity] {sym} close fetch failed: {e}")
        return None


'''


# ═══════════════════════════════════════════════════════════════
# PATCH 2B — APEX uses sub-bar close when flag enabled
# ═══════════════════════════════════════════════════════════════
P2B_OLD = '''                # ── Physics-based exits (require ad) ──
                if ad is not None:
                    # Apex
                    is_apex, apex_rsn = False, ""
                    if getattr(CFG, 'APEX_ENABLED', True):
                        is_apex, apex_rsn = check_thermodynamic_apex(
                            pos['action'], pos['entry'], price, ad, fi
                        )
                    if is_apex:
                        ex = True; rsn = apex_rsn
'''

P2B_NEW = '''                # ── Physics-based exits (require ad) ──
                if ad is not None:
                    # Apex
                    is_apex, apex_rsn = False, ""
                    if getattr(CFG, 'APEX_ENABLED', True):
                        # [REV-FIX v4] SUB-BAR PARITY: use last closed
                        # sub-bar close when REV_SUBBAR_ONLY is on.
                        _apex_px = price
                        if getattr(CFG, "REV_SUBBAR_ONLY", False):
                            _sub_tf_a = _get_subbars_tf(CFG.timeframe) or "15m"
                            _sub_sec_a = _sub_tf_seconds(_sub_tf_a)
                            _sb_close = _last_closed_subbar_close(
                                exchange, sym, _sub_tf_a, _sub_sec_a
                            )
                            if _sb_close is not None and _sb_close > 0:
                                _apex_px = _sb_close
                        is_apex, apex_rsn = check_thermodynamic_apex(
                            pos['action'], pos['entry'], _apex_px, ad, fi
                        )
                    if is_apex:
                        ex = True; rsn = apex_rsn
'''


# ═══════════════════════════════════════════════════════════════
# PATCH 3A — SL-Hybrid in _rev_finalize (Live)
# ═══════════════════════════════════════════════════════════════
P3A_OLD = '''    orig_sl_dist = float(w["orig_sl_dist"])
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
'''

P3A_NEW = '''    orig_sl_dist = float(w["orig_sl_dist"])
    orig_tp_dist = float(w["orig_tp_dist"])
    if orig_sl_dist <= 1e-12:
        orig_sl_dist = entry_px * 0.015
        orig_tp_dist = orig_sl_dist * float(getattr(CFG, "TP_MULT", 2.0))
    _max_sl_frac = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
    if orig_sl_dist > entry_px * _max_sl_frac:
        _rr = orig_tp_dist / max(orig_sl_dist, 1e-12)
        orig_sl_dist = entry_px * _max_sl_frac
        orig_tp_dist = orig_sl_dist * _rr

    # ═══════════════════════════════════════════════════════════════
    # [REV-FIX v4] SL-HYBRID: Signal levels vs Rebuilt levels
    # ---------------------------------------------------------------
    # إذا الدخول بقي قريباً من target (≤ 30% من orig_sl_dist):
    #   استخدم مستويات الإشارة (SL تحت الدعم الحقيقي)
    # إذا الدخول ابتعد أكثر:
    #   أعد بناء SL/TP من entry_px مع الحفاظ على المسافات (R:R)
    # ═══════════════════════════════════════════════════════════════
    _sig_sl_v = float(w.get("sig_sl", 0.0) or 0.0)
    _sig_tp_v = float(w.get("sig_tp1", 0.0) or 0.0)
    _tgt_v    = float(w.get("target", 0.0) or 0.0)
    _max_drift = 0.30 * orig_sl_dist
    _drift = abs(entry_px - _tgt_v) if _tgt_v > 0 else float("inf")

    _use_signal = (
        _sig_sl_v > 0 and _sig_tp_v > 0 and _tgt_v > 0
        and _drift <= _max_drift
        and (
            (action == "BUY"  and _sig_sl_v < entry_px < _sig_tp_v)
            or (action == "SELL" and _sig_tp_v < entry_px < _sig_sl_v)
        )
    )

    if _use_signal:
        new_sl = _sig_sl_v
        new_tp = _sig_tp_v
        _sl_d = abs(entry_px - new_sl)
        if _sl_d > entry_px * _max_sl_frac:
            _tp_d = abs(new_tp - entry_px)
            _rr_s = _tp_d / max(_sl_d, 1e-12)
            _new_sl_d = entry_px * _max_sl_frac
            _new_tp_d = _new_sl_d * _rr_s
            if action == "BUY":
                new_sl = entry_px - _new_sl_d
                new_tp = entry_px + _new_tp_d
            else:
                new_sl = entry_px + _new_sl_d
                new_tp = entry_px - _new_tp_d
        log.debug(f"[SL-Hybrid-Live] {sym} signal levels "
                  f"drift={_drift:.6f}/{_max_drift:.6f}")
    else:
        if action == "BUY":
            new_sl = entry_px - orig_sl_dist
            new_tp = entry_px + orig_tp_dist
        else:
            new_sl = entry_px + orig_sl_dist
            new_tp = entry_px - orig_tp_dist
        log.debug(f"[SL-Hybrid-Live] {sym} rebuilt "
                  f"drift={_drift:.6f}/{_max_drift:.6f}")
'''


# ═══════════════════════════════════════════════════════════════
# PATCH 3B — SL-Hybrid in _lad_sl_tp (Ladder)
# ═══════════════════════════════════════════════════════════════
P3B_OLD = '''def _lad_sl_tp(w: Dict, entry_px: float):
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
'''

P3B_NEW = '''def _lad_sl_tp(w: Dict, entry_px: float):
    """
    [REV-FIX v4] SL-HYBRID: نفس منطق _rev_finalize.
    إذا الدخول قريب من target → مستويات الإشارة (تحمي الدعم).
    إذا الدخول بعيد → إعادة بناء (تحفظ R:R).
    """
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

    # ── [REV-FIX v4] Hybrid logic ──
    action = w["action"]
    _sig_sl_v = float(w.get("sig_sl", 0.0) or 0.0)
    _sig_tp_v = float(w.get("sig_tp1", 0.0) or 0.0)
    _tgt_v    = float(w.get("target", 0.0) or 0.0)
    _max_drift = 0.30 * osd
    _drift = abs(entry_px - _tgt_v) if _tgt_v > 0 else float("inf")
    _use_signal = (
        _sig_sl_v > 0 and _sig_tp_v > 0 and _tgt_v > 0
        and _drift <= _max_drift
        and (
            (action == "BUY"  and _sig_sl_v < entry_px < _sig_tp_v)
            or (action == "SELL" and _sig_tp_v < entry_px < _sig_sl_v)
        )
    )
    if _use_signal:
        _sl_px = _sig_sl_v
        _tp_px = _sig_tp_v
        _sl_d = abs(entry_px - _sl_px)
        if _sl_d > entry_px * mx:
            _tp_d = abs(_tp_px - entry_px)
            _rr_s = _tp_d / max(_sl_d, 1e-12)
            _new_sl_d = entry_px * mx
            _new_tp_d = _new_sl_d * _rr_s
            if action == "BUY":
                _sl_px = entry_px - _new_sl_d
                _tp_px = entry_px + _new_tp_d
            else:
                _sl_px = entry_px + _new_sl_d
                _tp_px = entry_px - _new_tp_d
        _sl_dist_final = abs(entry_px - _sl_px)
        return _sl_px, _tp_px, _sl_dist_final

    if action == "BUY":
        return entry_px - osd, entry_px + otd, osd
    return entry_px + osd, entry_px - otd, osd
'''


# ═══════════════════════════════════════════════════════════════
# PATCH 3C — SL-Hybrid in simulate_portfolio (Backtest)
# ═══════════════════════════════════════════════════════════════
P3C_OLD = '''        # ══ [CRITICAL FIX] Rebuild sig.sl / sig.tp1 from opt_px ══
        # This is what the LIVE code already does in
        # _promote_pending_to_position. Without this, when
        # PO_FIXED_PRICE=False and entry ≠ sig.price, TP ends up
        # BELOW entry (for BUY) → "Hard TP" exits are actually losses.
        if sig.action == "BUY":
            sig.sl  = opt_px - _design_sl_dist
            sig.tp1 = opt_px + _design_tp_dist
        else:
            sig.sl  = opt_px + _design_sl_dist
            sig.tp1 = opt_px - _design_tp_dist
'''

P3C_NEW = '''        # ═══════════════════════════════════════════════════════════════
        # [REV-FIX v4] SL-HYBRID (Backtest parity with Live)
        # ---------------------------------------------------------------
        # إذا الدخول قريب من target (≤ 30% من _design_sl_dist):
        #   استخدم مستويات الإشارة (sig.price target, sig.sl الأصلية)
        # إذا الدخول ابتعد أكثر:
        #   أعد بناء SL/TP من opt_px (R:R محفوظ)
        # ═══════════════════════════════════════════════════════════════
        _sig_sl_v_bt = float(sig.sl)
        _sig_tp_v_bt = float(sig.tp1)
        _tgt_v_bt    = float(sig.price)
        _max_drift_bt = 0.30 * _design_sl_dist
        _drift_bt = abs(opt_px - _tgt_v_bt) if _tgt_v_bt > 0 else float("inf")
        _use_signal_bt = (
            _sig_sl_v_bt > 0 and _sig_tp_v_bt > 0 and _tgt_v_bt > 0
            and _drift_bt <= _max_drift_bt
            and (
                (sig.action == "BUY"  and _sig_sl_v_bt < opt_px < _sig_tp_v_bt)
                or (sig.action == "SELL" and _sig_tp_v_bt < opt_px < _sig_sl_v_bt)
            )
        )
        if _use_signal_bt:
            sig.sl  = _sig_sl_v_bt
            sig.tp1 = _sig_tp_v_bt
            _sl_d_bt = abs(opt_px - sig.sl)
            if _sl_d_bt > opt_px * _max_sl_frac:
                _tp_d_bt = abs(sig.tp1 - opt_px)
                _rr_s_bt = _tp_d_bt / max(_sl_d_bt, 1e-12)
                _new_sl_d_bt = opt_px * _max_sl_frac
                _new_tp_d_bt = _new_sl_d_bt * _rr_s_bt
                if sig.action == "BUY":
                    sig.sl  = opt_px - _new_sl_d_bt
                    sig.tp1 = opt_px + _new_tp_d_bt
                else:
                    sig.sl  = opt_px + _new_sl_d_bt
                    sig.tp1 = opt_px - _new_tp_d_bt
            log.debug(f"[SL-Hybrid-BT] {sym} signal levels "
                      f"drift={_drift_bt:.6f}/{_max_drift_bt:.6f}")
        else:
            if sig.action == "BUY":
                sig.sl  = opt_px - _design_sl_dist
                sig.tp1 = opt_px + _design_tp_dist
            else:
                sig.sl  = opt_px + _design_sl_dist
                sig.tp1 = opt_px - _design_tp_dist
            log.debug(f"[SL-Hybrid-BT] {sym} rebuilt "
                      f"drift={_drift_bt:.6f}/{_max_drift_bt:.6f}")
'''


# ═══════════════════════════════════════════════════════════════
# PATCH 4 — already_touched fix (closes[-1] → closes[close_idx])
# ═══════════════════════════════════════════════════════════════
P4_OLD = '''    current_px = float(ad.closes[-1]) if ad is not None else float(sig.price)
    already_touched = False
'''

P4_NEW = '''    # [REV-FIX v4] use last CLOSED bar (not closes[-1] which may be forming)
    if ad is not None:
        try:
            _ci_reg = int(sig.close_idx)
            if 0 <= _ci_reg < len(ad.closes):
                current_px = float(ad.closes[_ci_reg])
            else:
                current_px = float(ad.closes[-2]) if len(ad.closes) >= 2 \\
                             else float(sig.price)
        except Exception:
            current_px = float(ad.closes[-2]) if len(ad.closes) >= 2 \\
                         else float(sig.price)
    else:
        current_px = float(sig.price)
    already_touched = False
'''


# ═══════════════════════════════════════════════════════════════
# Apply
# ═══════════════════════════════════════════════════════════════
PATCHES = [
    ("P1.FILL_AT",        P1_OLD,  P1_NEW,  True),
    ("P2A.flag",          P2A_OLD, P2A_NEW, True),
    ("P2A.helper",        P2A_HELPER_ANCHOR, P2A_HELPER_BLOCK + P2A_HELPER_ANCHOR, True),
    ("P2B.apex",          P2B_OLD, P2B_NEW, True),
    ("P3A.finalize",      P3A_OLD, P3A_NEW, True),
    ("P3B.lad_sl_tp",     P3B_OLD, P3B_NEW, True),
    ("P3C.backtest",      P3C_OLD, P3C_NEW, True),
    ("P4.touched",        P4_OLD,  P4_NEW,  True),
]


def apply(src):
    if MARK in src:
        raise SystemExit("[ABORT] file already contains [REV-FIX v4].")
    for name, old, new, _req in PATCHES:
        _once(src, old, name)
    for name, old, new, _req in PATCHES:
        src = src.replace(old, new, 1)
    return src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default="trading_2_live4.py")
    ap.add_argument("--inplace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(a.src, "r", encoding="utf-8") as f:
        src = f.read()
    new = apply(src)

    # syntax gate
    ast.parse(new)
    print(f"[OK] {len(PATCHES)} anchors applied; syntax OK")

    if a.dry_run:
        return

    if a.inplace:
        bak = f"{a.src}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(a.src, bak)
        print(f"[OK] backup -> {bak}")
        out = a.src
    else:
        out = a.src.replace(".py", "_v4.py")

    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    py_compile.compile(tmp, doraise=True)
    os.replace(tmp, out)
    print(f"[OK] written -> {out}")


if __name__ == "__main__":
    main()
