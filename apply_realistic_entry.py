#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_realistic_entry.py  [REV-FIX v5]

يستبدل REVERSAL_FILL_AT="close" بنموذج واقعي مطابق لـ Live:
  - الكشف: high > target+κσ  (BUY)  /  low < target-κσ  (SELL)
  - سعر الدخول: target + κσ + slip_bps
  - slip_bps قابل للتعديل (افتراضي 10 bps = 0.10%)
"""
import argparse, ast, os, py_compile, shutil, sys, time

MARK = "[REV-FIX v5]"


def _once(src, old, name):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"[ABORT] '{name}' matched {n} times (expected 1)")


# ═══════════════════════════════════════════════════════════════
# P1 — Config: new mode + slip param
# ═══════════════════════════════════════════════════════════════
P1_OLD = '    REVERSAL_FILL_AT:        str   = "close"   # [REV-FIX v4] realizable: confirm-bar close\n'
P1_NEW = (
    '    REVERSAL_FILL_AT:        str   = "threshold"  # [REV-FIX v5] realistic: target+κσ+slip\n'
    '    REV_ENTRY_SLIP_BPS: float = 10.0    # [REV-FIX v5] entry slippage in bps\n'
)

P1B_OLD = '    REV_SUBBAR_ONLY: bool = True\n'
P1B_NEW = (
    '    REV_SUBBAR_ONLY: bool = True\n'
    '    # [REV-FIX v5] entry-slip: matches Live Marketable Limit taker cost\n'
)


# ═══════════════════════════════════════════════════════════════
# P2 — sigma_bounce detection: close → high/low
# ═══════════════════════════════════════════════════════════════
P2_OLD = '''    elif mode == "sigma_bounce":
        fi = int(sig.feat_idx)
        sigma_bar = 0.01
        if 0 <= fi < len(ad.E_therm):
            _s = float(ad.E_therm[fi])
            if np.isfinite(_s) and _s > 1e-9:
                sigma_bar = _s
        thr = (float(getattr(cfg, 'REVERSAL_CONFIRM_KAPPA', 0.20))
               * sigma_bar * float(target0))
        for k in range(b0, b1):
            c = sc_flat[k]
            if not np.isfinite(c):
                continue
            if action == "BUY" and (c - target0) > thr:
                confirm_k = k; break
            if action == "SELL" and (target0 - c) > thr:
                confirm_k = k; break
'''

P2_NEW = '''    elif mode == "sigma_bounce":
        fi = int(sig.feat_idx)
        sigma_bar = 0.01
        if 0 <= fi < len(ad.E_therm):
            _s = float(ad.E_therm[fi])
            if np.isfinite(_s) and _s > 1e-9:
                sigma_bar = _s
        thr = (float(getattr(cfg, 'REVERSAL_CONFIRM_KAPPA', 0.20))
               * sigma_bar * float(target0))
        # [REV-FIX v5] use bar HIGH/LOW instead of close — matches Live's
        # ticker detection of the crossing moment (5s granularity ≈ high/low)
        for k in range(b0, b1):
            h = sh_flat[k]
            l = sl_flat[k]
            if action == "BUY":
                if np.isfinite(h) and (h - target0) > thr:
                    confirm_k = k; break
            else:
                if np.isfinite(l) and (target0 - l) > thr:
                    confirm_k = k; break
'''


# ═══════════════════════════════════════════════════════════════
# P3 — Phase 3 fill: "threshold" mode
# ═══════════════════════════════════════════════════════════════
P3_OLD = '''    if fill_mode == "close":
        fill_px = c_conf
    elif fill_mode == "threshold":
'''

P3_NEW = '''    if fill_mode == "close":
        fill_px = c_conf
    elif fill_mode == "threshold":
        # [REV-FIX v5] entry = target + κσ + slip (matches Live's
        # Marketable Limit taker fill at the moment of crossing).
        _fi = int(sig.feat_idx)
        _sb = 0.01
        if 0 <= _fi < len(ad.E_therm):
            _s = float(ad.E_therm[_fi])
            if np.isfinite(_s) and _s > 1e-9:
                _sb = _s
        _kappa = float(getattr(cfg, 'REVERSAL_CONFIRM_KAPPA', 0.20))
        _slip_bps = float(getattr(cfg, 'REV_ENTRY_SLIP_BPS', 10.0))
        _thr = _kappa * _sb * float(target0)
        _slip = _slip_bps * 1e-4 * float(target0)
        if action == "BUY":
            fill_px = float(target0) + _thr + _slip
        else:
            fill_px = float(target0) - _thr - _slip
    elif fill_mode == "close_legacy":
'''


# ═══════════════════════════════════════════════════════════════
# P4 — Live _rev_scan: use high/low for detection
# ═══════════════════════════════════════════════════════════════
P4_OLD = '''            # 3. التأكيد (Bounce Confirm)
            if np.isfinite(c) and _bar_confirms_bounce(w, c):
                w["status"] = "READY_TO_FILL"
                w["confirm_k"] = k
                w["ref_px"] = float(c)
                w["confirm_close_ts"] = ts + sub_sec
                w["prev_close"] = c
                w["last_scan_ts"] = ts
                log.info(f"[LiveRev] {sym} BOUNCE confirmed k={k} close={c:.6f}")
                break
'''

P4_NEW = '''            # 3. التأكيد (Bounce Confirm)
            # [REV-FIX v5] use bar HIGH/LOW (matches backtest)
            _bb_ok = False
            _bb_px = 0.0
            if action == "BUY":
                if np.isfinite(h) and (h - target) > 0:
                    # [REV-FIX v5] sigma_bounce: check h > target + κσ
                    if str(CFG.REVERSAL_CONFIRM_MODE) == "sigma_bounce":
                        _sb = float(w.get("sigma_bar", 0.01))
                        _thr = float(CFG.REVERSAL_CONFIRM_KAPPA) * _sb * target
                        if (h - target) > _thr:
                            _bb_ok = True
                            _bb_px = target + _thr
                    elif _bar_confirms_bounce(w, c):
                        _bb_ok = True
                        _bb_px = float(c)
            else:
                if np.isfinite(l) and (target - l) > 0:
                    if str(CFG.REVERSAL_CONFIRM_MODE) == "sigma_bounce":
                        _sb = float(w.get("sigma_bar", 0.01))
                        _thr = float(CFG.REVERSAL_CONFIRM_KAPPA) * _sb * target
                        if (target - l) > _thr:
                            _bb_ok = True
                            _bb_px = target - _thr
                    elif _bar_confirms_bounce(w, c):
                        _bb_ok = True
                        _bb_px = float(c)
            if _bb_ok:
                w["status"] = "READY_TO_FILL"
                w["confirm_k"] = k
                w["ref_px"] = float(_bb_px)
                w["confirm_close_ts"] = ts + sub_sec
                w["prev_close"] = c
                w["last_scan_ts"] = ts
                log.info(f"[LiveRev] {sym} BOUNCE confirmed k={k} "
                         f"trigger_px={_bb_px:.6f}")
                break
'''


# ═══════════════════════════════════════════════════════════════
# P5 — CLI flag
# ═══════════════════════════════════════════════════════════════
P5_OLD = '''    p.add_argument("--reversal-fill", type=str, default=None,
                   choices=["target","close","best"],
                   help="Fill price source (default target)")
'''
P5_NEW = '''    p.add_argument("--reversal-fill", type=str, default=None,
                   choices=["target","close","best","threshold"],
                   help="Fill price source (default target)")
    p.add_argument("--rev-entry-slip-bps", type=float, default=None,
                   help="[REV-FIX v5] entry slippage in bps (default 10)")
'''


# ═══════════════════════════════════════════════════════════════
# P6 — Wiring
# ═══════════════════════════════════════════════════════════════
P6_OLD = '''    if getattr(args, "reversal_fill", None) is not None:
        CFG.REVERSAL_FILL_AT = str(args.reversal_fill)
'''
P6_NEW = '''    if getattr(args, "reversal_fill", None) is not None:
        CFG.REVERSAL_FILL_AT = str(args.reversal_fill)
    if getattr(args, "rev_entry_slip_bps", None) is not None:
        CFG.REV_ENTRY_SLIP_BPS = float(args.rev_entry_slip_bps)
        log.info(f"[REV-FIX v5] REV_ENTRY_SLIP_BPS = {CFG.REV_ENTRY_SLIP_BPS}")
'''


PATCHES = [
    ("P1.fill_mode",   P1_OLD,  P1_NEW,  True),
    ("P2.detect",      P2_OLD,  P2_NEW,  True),
    ("P3.fill_px",     P3_OLD,  P3_NEW,  True),
    ("P4.live_scan",   P4_OLD,  P4_NEW,  True),
    ("P5.cli",         P5_OLD,  P5_NEW,  True),
    ("P6.wire",        P6_OLD,  P6_NEW,  True),
]


def apply(src):
    if MARK in src:
        raise SystemExit("[ABORT] file already contains [REV-FIX v5].")
    for name, old, new, _ in PATCHES:
        _once(src, old, name)
    for name, old, new, _ in PATCHES:
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
    ast.parse(new)
    print(f"[OK] {len(PATCHES)} anchors; syntax OK")

    if a.dry_run:
        return
    if a.inplace:
        bak = f"{a.src}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(a.src, bak)
        print(f"[OK] backup -> {bak}")
        out = a.src
    else:
        out = a.src.replace(".py", "_v5.py")

    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    py_compile.compile(tmp, doraise=True)
    os.replace(tmp, out)
    print(f"[OK] written -> {out}")


if __name__ == "__main__":
    main()
