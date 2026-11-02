#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_entry_adjust_to_risk.py
=============================
PHILOSOPHY
----------
Don't clip SL. Don't reject. ADJUST THE ENTRY so that
risk = |entry - SL| / entry stays within the hard cap.

Math (BUY):   risk <= r_max  ⟺  entry <= SL / (1 - r_max)
Math (SELL):  risk <= r_max  ⟺  entry >= SL / (1 + r_max)

Config additions:
  PHYSICS_SL_TRUTH     = True   (physics SL, no clipping)
  ENTRY_ADJUST_TO_RISK = True   (adjust entry, not SL)
  RISK_HARD_CAP        = 0.10   (10% max risk per trade)
  RISK_CAP_TOLERANCE   = 0.02   (allow 2pp overshoot)

What gets touched:
  1. Config: 4 new fields
  2. build_signals: entry adjustment + propagate adjusted entry to Signal
  3. simulate_portfolio: skip SL clipping when PHYSICS_SL_TRUTH
  4. run_live: same
  5. CLI + wiring: --physics-sl-truth, --entry-adjust-to-risk,
                    --risk-hard-cap, --no-*
  6. Note: Stage 2 (market entry) still works but is no longer
     the primary path. If entry-adjust keeps the limit pending,
     Stage 2 remains a fallback. To disable Stage 2 entirely,
     pass --no-unified-stage2 (existing flag).

Guarantees:
  Idempotent | backup | syntax check | rollback on failure.
"""

import argparse, ast, os, shutil, sys, time
from pathlib import Path

DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"


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
        ast.parse(t)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def _backup(p):
    bak = p.with_name(f"{p.name}.bak.{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(p, bak)
    return bak


def _apply_exact(text, old, new, marker):
    if marker and marker in text:
        return text, "already_applied"
    if old in text:
        return text.replace(old, new, 1), "applied"
    return text, "ANCHOR_NOT_FOUND"


def _add_field(text, decl, after_field):
    import re
    name = decl.split(":")[0].strip()
    if re.search(rf"^\s*{re.escape(name)}\s*:", text, re.MULTILINE):
        return text, "already_applied"
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if re.match(rf"^\s*{re.escape(after_field)}\s*:", ln):
            lines.insert(i + 1, f"    {decl}")
            return "\n".join(lines), "applied"
    return text, "AFTER_FIELD_NOT_FOUND"


# ══════════════════════════════════════════════════════════════
#  1. build_signals: entry adjustment block
# ══════════════════════════════════════════════════════════════
BUILD_SL_OLD = """            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
            sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist
"""

BUILD_SL_NEW = """            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)
            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)
            sl = tunnel_entry_p - sl_dist if action == "BUY" else tunnel_entry_p + sl_dist

            # ══ [ENTRY-ADJUST-TO-RISK] ══
            # Keep physics SL as-is. If risk > cap, move entry toward SL.
            if getattr(CFG, 'ENTRY_ADJUST_TO_RISK', True):
                _r_max = float(getattr(CFG, 'RISK_HARD_CAP', 0.10)) + \\
                         float(getattr(CFG, 'RISK_CAP_TOLERANCE', 0.02))
                _entry0 = float(tunnel_entry_p)
                _sl0 = float(sl)
                if action == "BUY" and _entry0 > 0 and _sl0 < _entry0:
                    _risk0 = (_entry0 - _sl0) / _entry0
                    if _risk0 > _r_max:
                        _adj = _sl0 / (1.0 - _r_max)
                        if _adj > _sl0 and _adj > 0:
                            tunnel_entry_p = _adj
                            sl_dist = tunnel_entry_p - _sl0
                            log.debug(
                                f"[RiskAdjust] {sym} BUY "
                                f"{_entry0:.6f}->{tunnel_entry_p:.6f} "
                                f"risk {_risk0*100:.2f}%->{_r_max*100:.2f}%"
                            )
                        else:
                            continue
                elif action == "SELL" and _entry0 > 0 and _sl0 > _entry0:
                    _risk0 = (_sl0 - _entry0) / _entry0
                    if _risk0 > _r_max:
                        _adj = _sl0 / (1.0 + _r_max)
                        if _adj < _sl0 and _adj > 0:
                            tunnel_entry_p = _adj
                            sl_dist = _sl0 - tunnel_entry_p
                            log.debug(
                                f"[RiskAdjust] {sym} SELL "
                                f"{_entry0:.6f}->{tunnel_entry_p:.6f} "
                                f"risk {_risk0*100:.2f}%->{_r_max*100:.2f}%"
                            )
                        else:
                            continue
"""


# ══════════════════════════════════════════════════════════════
#  2. simulate_portfolio: skip SL clip when PHYSICS_SL_TRUTH
# ══════════════════════════════════════════════════════════════
SIM_CLIP_OLD = """        # Clip SL to max_sl_frac × opt_px (entry-based cap)
        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        if _design_sl_dist > opt_px * _max_sl_frac:
            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)
            _design_sl_dist = opt_px * _max_sl_frac
            _design_tp_dist = _design_sl_dist * _rr
"""

SIM_CLIP_NEW = """        # ══ [PHYSICS-SL-TRUTH] when enabled, physics SL is used as-is.
        # A hard REJECT is applied if risk still exceeds the cap
        # (should not happen because build_signals already adjusted
        # the entry, but this is a safety net for Stage-2 fills).
        if getattr(CFG, 'PHYSICS_SL_TRUTH', True):
            _r_max_s = float(getattr(CFG, 'RISK_HARD_CAP', 0.10)) + \\
                       float(getattr(CFG, 'RISK_CAP_TOLERANCE', 0.02))
            _implied_risk = _design_sl_dist / opt_px if opt_px > 0 else 1.0
            if _implied_risk > _r_max_s:
                log.warning(
                    f"[PhysicsSL] {sym} REJECT at backtest entry "
                    f"(risk {_implied_risk*100:.2f}% > "
                    f"{_r_max_s*100:.2f}%)"
                )
                continue
            # No clip — use physics SL directly
        else:
            # Legacy: clip to SL_WIDEN_MULT
            _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
            if _design_sl_dist > opt_px * _max_sl_frac:
                _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)
                _design_sl_dist = opt_px * _max_sl_frac
                _design_tp_dist = _design_sl_dist * _rr
"""


# ══════════════════════════════════════════════════════════════
#  3. run_live: same logic for the live SL clip
# ══════════════════════════════════════════════════════════════
LIVE_CLIP_OLD = """                        # [SL-CLIP-CONSISTENCY] Scale with SL_WIDEN_MULT
                        # so the widened SL isn't re-clipped back to 1.5%.
                        max_sl_frac = 0.015 * float(
                            getattr(CFG, 'SL_WIDEN_MULT', 1.0)
                        )
                        if orig_sl_dist > entry_price * max_sl_frac:
                            orig_sl_dist = entry_price * max_sl_frac
                            orig_tp_dist = orig_sl_dist * rr_ratio
"""

LIVE_CLIP_NEW = """                        # ══ [PHYSICS-SL-TRUTH] live parity ══
                        if getattr(CFG, 'PHYSICS_SL_TRUTH', True):
                            _r_max_lv = float(getattr(
                                CFG, 'RISK_HARD_CAP', 0.10)) + \\
                                float(getattr(CFG, 'RISK_CAP_TOLERANCE', 0.02))
                            _risk_lv = orig_sl_dist / max(entry_price, 1e-12)
                            if _risk_lv > _r_max_lv:
                                log.warning(
                                    f"[PhysicsSL-LV] {sym} REJECT "
                                    f"(risk {_risk_lv*100:.2f}% > "
                                    f"{_r_max_lv*100:.2f}%)"
                                )
                                # Close whatever filled (safety)
                                try:
                                    _s_c = 'sell' if sig.action == 'BUY' else 'buy'
                                    exchange.create_order(
                                        sym, 'market', _s_c, actual_qty)
                                except Exception:
                                    pass
                                continue
                            # No clip — use physics SL
                        else:
                            max_sl_frac = 0.015 * float(
                                getattr(CFG, 'SL_WIDEN_MULT', 1.0))
                            if orig_sl_dist > entry_price * max_sl_frac:
                                orig_sl_dist = entry_price * max_sl_frac
                                orig_tp_dist = orig_sl_dist * rr_ratio
"""


# ══════════════════════════════════════════════════════════════
#  4. CLI additions
# ══════════════════════════════════════════════════════════════
CLI_OLD = """    p.add_argument("--tp-mult", type=float, default=None,
                   help="Override TP_MULT")
"""

CLI_NEW = """    p.add_argument("--tp-mult", type=float, default=None,
                   help="Override TP_MULT")
    p.add_argument("--no-physics-sl-truth", action="store_true",
                   help="Revert to legacy SL clipping (SL_WIDEN_MULT). "
                        "Default: physics SL is used directly.")
    p.add_argument("--no-entry-adjust-to-risk", action="store_true",
                   help="Disable entry adjustment. Signals with risk>cap "
                        "will be rejected instead of having their entry "
                        "moved toward SL.")
    p.add_argument("--risk-hard-cap", type=float, default=None,
                   help="Max risk per trade as a fraction (default 0.10)")
    p.add_argument("--risk-cap-tolerance", type=float, default=None,
                   help="Overshoot tolerance on the cap (default 0.02)")
"""


# ══════════════════════════════════════════════════════════════
#  5. Wiring
# ══════════════════════════════════════════════════════════════
WIRING_OLD = """    if getattr(args, "tp_mult", None) is not None:
        CFG.TP_MULT = float(args.tp_mult)
        log.info(f"[Ablation] TP_MULT = {CFG.TP_MULT}")
"""

WIRING_NEW = """    if getattr(args, "tp_mult", None) is not None:
        CFG.TP_MULT = float(args.tp_mult)
        log.info(f"[Ablation] TP_MULT = {CFG.TP_MULT}")
    if getattr(args, "no_physics_sl_truth", False):
        CFG.PHYSICS_SL_TRUTH = False
        log.info("[PhysicsSL] DISABLED — legacy SL clipping active")
    else:
        CFG.PHYSICS_SL_TRUTH = True
        log.info("[PhysicsSL] ENABLED — physics SL used directly")
    if getattr(args, "no_entry_adjust_to_risk", False):
        CFG.ENTRY_ADJUST_TO_RISK = False
        log.info("[RiskAdjust] DISABLED — reject on risk>cap")
    else:
        CFG.ENTRY_ADJUST_TO_RISK = True
        log.info("[RiskAdjust] ENABLED — entry moves toward SL")
    if getattr(args, "risk_hard_cap", None) is not None:
        CFG.RISK_HARD_CAP = float(args.risk_hard_cap)
        log.info(f"[RiskAdjust] risk_hard_cap = {CFG.RISK_HARD_CAP:.3f}")
    if getattr(args, "risk_cap_tolerance", None) is not None:
        CFG.RISK_CAP_TOLERANCE = float(args.risk_cap_tolerance)
        log.info(f"[RiskAdjust] tolerance = {CFG.RISK_CAP_TOLERANCE:.3f}")
"""


# ══════════════════════════════════════════════════════════════
#  Patch list
# ══════════════════════════════════════════════════════════════
PATCHES = [
    {"name": "Config: + PHYSICS_SL_TRUTH",
     "kind": "add_field",
     "decl": "PHYSICS_SL_TRUTH: bool = True",
     "after": "SL_WIDEN_MULT"},

    {"name": "Config: + ENTRY_ADJUST_TO_RISK",
     "kind": "add_field",
     "decl": "ENTRY_ADJUST_TO_RISK: bool = True",
     "after": "PHYSICS_SL_TRUTH"},

    {"name": "Config: + RISK_HARD_CAP",
     "kind": "add_field",
     "decl": "RISK_HARD_CAP: float = 0.10",
     "after": "ENTRY_ADJUST_TO_RISK"},

    {"name": "Config: + RISK_CAP_TOLERANCE",
     "kind": "add_field",
     "decl": "RISK_CAP_TOLERANCE: float = 0.02",
     "after": "RISK_HARD_CAP"},

    {"name": "build_signals: entry adjustment",
     "kind": "exact",
     "old": BUILD_SL_OLD,
     "new": BUILD_SL_NEW,
     "marker": "[ENTRY-ADJUST-TO-RISK]"},

    {"name": "simulate_portfolio: skip SL clip",
     "kind": "exact",
     "old": SIM_CLIP_OLD,
     "new": SIM_CLIP_NEW,
     "marker": "[PHYSICS-SL-TRUTH] when enabled"},

    {"name": "run_live: skip SL clip",
     "kind": "exact",
     "old": LIVE_CLIP_OLD,
     "new": LIVE_CLIP_NEW,
     "marker": "[PHYSICS-SL-TRUTH] live parity"},

    {"name": "CLI: physics-sl / entry-adjust flags",
     "kind": "exact",
     "old": CLI_OLD,
     "new": CLI_NEW,
     "marker": "--no-physics-sl-truth"},

    {"name": "main(): wiring",
     "kind": "exact",
     "old": WIRING_OLD,
     "new": WIRING_NEW,
     "marker": "[RiskAdjust] ENABLED"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_TARGET)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"[ERROR] not found: {path}", file=sys.stderr)
        return 2

    print(f"[*] Target: {path}")
    print(f"[*] Size  : {path.stat().st_size:,} bytes")

    original = _read(path)
    ok, err = _syntax_ok(original)
    if not ok:
        print(f"[ERROR] pre-patch: {err}", file=sys.stderr)
        return 3
    print("[OK] Original syntax verified.\n")

    text = original
    results = []
    for p in PATCHES:
        if p["kind"] == "add_field":
            text, st = _add_field(text, p["decl"], p["after"])
        else:
            text, st = _apply_exact(text, p["old"], p["new"], p["marker"])
        results.append((p["name"], st))
        icon = {"applied": "✅", "already_applied": "⏭️"}.get(st, "❌")
        print(f"  {icon} {p['name']:42s} [{st}]")

    failed = [r for r in results
              if "NOT_FOUND" in r[1] or "EXCEPTION" in r[1]]
    if failed:
        print(f"\n[ERROR] {len(failed)} failed — nothing written.",
              file=sys.stderr)
        for n, s in failed:
            print(f"    • {n}: {s}", file=sys.stderr)
        return 4

    if text == original:
        print("\n[OK] Already patched.")
        return 0

    ok, err = _syntax_ok(text)
    if not ok:
        print(f"\n[ERROR] post-patch: {err}", file=sys.stderr)
        return 5
    print("\n[OK] Patched syntax verified.")

    if args.check:
        print("[CHECK] write skipped.")
        return 0

    if args.dry_run:
        d = len(text.encode("utf-8")) - len(original.encode("utf-8"))
        print(f"[DRY-RUN] delta {d:+,} bytes")
        return 0

    if not args.no_backup:
        print(f"[OK] Backup: {_backup(path)}")

    _write(path, text)
    print(f"[OK] Wrote {len(text.encode('utf-8')):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
