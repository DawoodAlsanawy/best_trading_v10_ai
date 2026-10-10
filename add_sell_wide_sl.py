#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""add_sell_wide_sl.py — مضاعف SL مستقل لـ SELL."""

import argparse, ast, shutil, sys
from datetime import datetime
from pathlib import Path


# Patch 1: Config
P1_ANCHOR = "    SELL_FRICTION_PCT: float = 0.25             # للنافذة"
P1_NEW = """    SELL_FRICTION_PCT: float = 0.25             # للنافذة

    # ══ [SELL-WIDE-SL] مضاعف وقف الخسارة لـ SELL فقط ══
    # 1.0 = نفس SL الخاص بـ BUY
    # 2.0 = مساحة تنفس مضاعفة
    # 5.0 = عملياً بدون SL (نعتمد على Apex فقط)
    SELL_SL_WIDEN_MULT: float = 1.0"""
P1_MARK = "[SELL-WIDE-SL]"


# Patch 2: build_signals
P2_ANCHOR = """            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
            sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist"""
P2_NEW = """            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
            # [SELL-WIDE-SL] مضاعف خاص بـ SELL
            if action == "SELL":
                _slm = float(getattr(CFG, 'SELL_SL_WIDEN_MULT', 1.0))
                if _slm > 0:
                    sl_dist *= _slm
            sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist"""
P2_MARK = "[SELL-WIDE-SL] مضاعف خاص بـ SELL"


# Patch 3: _recompute_entry_geometry_at_market (Stage 2)
P3_ANCHOR = """        # نفس دالة build_signals
        sl_dist_new = compute_geodesic_stop(S_new, ad, entry_fi, cfg)
        if sl_dist_new <= 0 or not np.isfinite(sl_dist_new):
            return None"""
P3_NEW = """        # نفس دالة build_signals
        sl_dist_new = compute_geodesic_stop(S_new, ad, entry_fi, cfg)
        if sig.action == "SELL":
            _slm_g = float(getattr(cfg, 'SELL_SL_WIDEN_MULT', 1.0))
            if _slm_g > 0:
                sl_dist_new *= _slm_g
        if sl_dist_new <= 0 or not np.isfinite(sl_dist_new):
            return None"""
P3_MARK = "SELL-WIDE-SL"


# Patch 4: simulate_portfolio SL clip
P4_ANCHOR = """        # Clip SL to max_sl_frac × opt_px (entry-based cap)
        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        if _design_sl_dist > opt_px * _max_sl_frac:"""
P4_NEW = """        # Clip SL to max_sl_frac × opt_px (entry-based cap)
        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        # [SELL-WIDE-SL] رفع السقف لـ SELL بنفس المضاعف
        if sig.action == "SELL":
            _max_sl_frac *= float(getattr(CFG, 'SELL_SL_WIDEN_MULT', 1.0))
        if _design_sl_dist > opt_px * _max_sl_frac:"""
P4_MARK = "[SELL-WIDE-SL] رفع السقف"


# Patch 5: CLI
P5_ANCHOR = '    p.add_argument("--sell-friction-pct", type=float, default=None)'
P5_NEW = '''    p.add_argument("--sell-friction-pct", type=float, default=None)
    p.add_argument("--sell-sl-widen-mult", type=float, default=None,
                   help="SL widening factor for SELL only (default 1.0)")'''
P5_MARK = "--sell-sl-widen-mult"


# Patch 6: main
P6_ANCHOR = """    if args.sell_friction_pct is not None:
        CFG.SELL_FRICTION_PCT = float(args.sell_friction_pct)"""
P6_NEW = """    if args.sell_friction_pct is not None:
        CFG.SELL_FRICTION_PCT = float(args.sell_friction_pct)
    if args.sell_sl_widen_mult is not None:
        CFG.SELL_SL_WIDEN_MULT = float(args.sell_sl_widen_mult)"""
P6_MARK = "SELL_SL_WIDEN_MULT = float(args.sell_sl_widen_mult)"


def apply(text, old, new, marker, name):
    if marker in text:
        return text, f"SKIP: {name}"
    if old not in text:
        return text, f"ERR: {name} (anchor not found)"
    return text.replace(old, new, 1), f"OK: {name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_rnd_sell_only.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"ERR: {args.file} not found")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("=" * 70)
    print("  add_sell_wide_sl.py")
    print("=" * 70)
    print()

    for patch in [
        (P1_ANCHOR, P1_NEW, P1_MARK, "Config: SELL_SL_WIDEN_MULT"),
        (P2_ANCHOR, P2_NEW, P2_MARK, "build_signals: apply multiplier"),
        (P3_ANCHOR, P3_NEW, P3_MARK, "Stage-2 geometry multiplier"),
        (P4_ANCHOR, P4_NEW, P4_MARK, "simulate: raise SELL clip cap"),
        (P5_ANCHOR, P5_NEW, P5_MARK, "CLI flag"),
        (P6_ANCHOR, P6_NEW, P6_MARK, "main wiring"),
    ]:
        text, s = apply(text, *patch)
        print(f"  {s}")

    try:
        ast.parse(text)
        print("\n  OK: ast.parse")
    except SyntaxError as e:
        print(f"\n  ERR: syntax at {e.lineno}: {e.text}")
        return 3

    if text == original:
        print("\n  No changes")
        return 0

    if args.dry_run:
        print("\n  Dry run - nothing written")
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_widesl_{ts}')
    shutil.copy2(p, backup)
    print(f"\n  Backup: {backup}")
    p.write_text(text, encoding='utf-8')
    print(f"  Written: {p}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
