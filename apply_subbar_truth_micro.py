#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_subbar_truth_micro.py
===========================
Sub-Bar Truth Layer for trading_2_live4_claude2_v4_micro_pro.py

WHAT IT DOES
------------
Uses the existing 5m sub-bars (ad.sub_highs/sub_lows/sub_closes) to add
three independent quality layers to every signal:

  Layer 1 (Direction):   Reject signals whose meso/micro trend opposes
                         the macro (4h) direction. Meso = last 1h, micro
                         = last 30min of sub-bars.

  Layer 2 (Entry):       Don't fill on touch — wait for sub-bar rejection.
                         BUY  : touch low ≤ tunnel AND close > tunnel+κσ_sub
                         SELL : touch high ≥ tunnel AND close < tunnel−κσ_sub
                         Otherwise cancel and wait for next bar.

  Layer 3 (SL):          Replace physics SL with structural swing SL when
                         a valid swing low/high exists within the entry bar.

All three layers are OPT-IN — default OFF. Toggle with --subbar-truth.

Patches:
  1. Config: 6 new fields
  2. Global dict for entry sub-bar indices
  3. New functions: _subbar_direction_score, _check_subbar_rejection,
     _compute_structural_sl
  4. build_signals: Layer 1 (direction filter)
  5. precompute_entry_fills: Layer 2 (rejection entry)
  6. simulate_portfolio: Layer 3 (structural SL)
  7. _promote_pending_to_position: Layer 3 (live structural SL)
  8. CLI: --subbar-truth, --no-subbar-direction, --no-subbar-entry,
           --no-subbar-sl
  9. main(): wiring

Guarantees:
  Idempotent | backup | syntax check | no external data needed
"""

import argparse, ast, os, re, shutil, sys, time
from pathlib import Path

DEFAULT_TARGET = "trading_2_live4_claude2_v4_micro.py"


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
NEW_FUNCTIONS = '''# ═══════════════════════════════════════════════════════════════
# [SUBBAR-TRUTH-LAYER] — shared state + helpers
# ═══════════════════════════════════════════════════════════════
_SUBBAR_ENTRY_MAP: Dict = {}   # (sym, close_idx) -> rejection sub_idx


def _subbar_direction_score(ad, ci, action, cfg):
    """
    Layer 1 — Return alignment ∈ [0, 1] of meso/micro with macro direction.
    Uses sub-bars of the signal bar (ci):
      meso  = last 12 sub-bars (1 hour on 4h/5m)
      micro = last  6 sub-bars (30 min)
    """
    try:
        if ad.sub_closes is None or ad.sub_per_main < 4:
            return 1.0
        if ci < 0 or ci >= ad.sub_closes.shape[0]:
            return 1.0
        bar = ad.sub_closes[ci]
        valid = bar[~np.isnan(bar)]
        if len(valid) < 18:
            return 1.0
        meso = valid[-12:]
        micro = valid[-6:]

        def _trend(prices):
            if len(prices) < 3:
                return 0.5
            x = np.arange(len(prices), dtype=float)
            y = np.log(np.maximum(prices / prices[0], 1e-9))
            try:
                s, _, r, _, _ = linregress(x, y)
            except Exception:
                return 0.5
            r2 = r * r
            sign = 1.0 if action == "BUY" else -1.0
            eff = s * sign
            total = eff * len(prices)
            if total > 0.003 and r2 > 0.15:
                return 1.0
            if total < -0.003:
                return 0.0
            return 0.5

        ms = _trend(meso)
        xs = _trend(micro)
        if ms >= 0.8 and xs >= 0.8:
            return 1.0
        if ms >= 0.8 and xs >= 0.5:
            return 0.6
        if ms >= 0.8 and xs < 0.5:
            return 0.3
        if ms < 0.5 and xs < 0.5:
            return 0.0
        if ms < 0.5:
            return 0.2
        return 0.5
    except Exception:
        return 1.0


def _check_subbar_rejection(ad, bar, target_px, action, cfg):
    """
    Layer 2 — Look for a sub-bar rejection in the entry bar `bar`.
    Returns (fill_px, sub_idx) or None.
    """
    try:
        if ad.sub_closes is None or ad.sub_per_main < 2:
            return None
        if bar < 0 or bar >= ad.sub_closes.shape[0]:
            return None
        max_wait = int(getattr(cfg, 'SUBBAR_ENTRY_MAX_WAIT_SUBBARS', 6))
        max_wait = max(2, min(max_wait, ad.sub_per_main))

        main_sigma = 0.01
        try:
            fi = bar - ad.feat_start
            if 0 <= fi < len(ad.E_therm):
                _s = float(ad.E_therm[fi])
                if np.isfinite(_s) and _s > 1e-6:
                    main_sigma = _s
        except Exception:
            pass
        sub_sigma = main_sigma / max(float(np.sqrt(ad.sub_per_main)), 1.0)
        kappa = float(getattr(cfg, 'SUBBAR_BOUNCE_KAPPA', 0.20))
        bounce_thr = kappa * sub_sigma * target_px

        lows = ad.sub_lows[bar]
        highs = ad.sub_highs[bar]
        closes = ad.sub_closes[bar]

        for j in range(max_wait):
            try:
                if action == "BUY":
                    if (np.isfinite(lows[j]) and np.isfinite(closes[j])
                            and lows[j] <= target_px
                            and closes[j] > target_px + bounce_thr):
                        return (float(closes[j]), int(j))
                else:
                    if (np.isfinite(highs[j]) and np.isfinite(closes[j])
                            and highs[j] >= target_px
                            and closes[j] < target_px - bounce_thr):
                        return (float(closes[j]), int(j))
            except Exception:
                continue
        return None
    except Exception:
        return None


def _compute_structural_sl(ad, entry_ci, entry_px, action,
                             physics_sl, physics_sl_dist, cfg,
                             max_sub_idx=None):
    """
    Layer 3 — Return the nearest structural swing low/high as SL,
    or physics_sl if none is found within clamps.
    """
    try:
        if ad.sub_lows is None or ad.sub_per_main < 3:
            return physics_sl
        if entry_ci < 0 or entry_ci >= ad.sub_lows.shape[0]:
            return physics_sl

        limit_j = (ad.sub_per_main if max_sub_idx is None
                   else min(int(max_sub_idx) + 1, ad.sub_per_main))
        buffer = float(getattr(cfg, 'SUBBAR_SL_BUFFER', 0.003))

        swings = []
        for ci_off in (max(0, entry_ci - 1), entry_ci):
            sub_highs = ad.sub_highs[ci_off]
            sub_lows = ad.sub_lows[ci_off]
            for j in range(1, limit_j - 1):
                try:
                    if action == "BUY":
                        lp, lc, ln = sub_lows[j-1], sub_lows[j], sub_lows[j+1]
                        if not (np.isfinite(lp) and np.isfinite(lc)
                                and np.isfinite(ln)):
                            continue
                        if lc < lp and lc < ln and lc < entry_px:
                            swings.append(float(lc))
                    else:
                        hp, hc, hn = sub_highs[j-1], sub_highs[j], sub_highs[j+1]
                        if not (np.isfinite(hp) and np.isfinite(hc)
                                and np.isfinite(hn)):
                            continue
                        if hc > hp and hc > hn and hc > entry_px:
                            swings.append(float(hc))
                except Exception:
                    continue

        if not swings:
            return physics_sl

        main_sigma = 0.01
        try:
            fi = entry_ci - ad.feat_start
            if 0 <= fi < len(ad.E_therm):
                _s = float(ad.E_therm[fi])
                if np.isfinite(_s) and _s > 1e-6:
                    main_sigma = _s
        except Exception:
            pass

        if action == "BUY":
            nearest = max(swings)
            cand_sl = nearest * (1.0 - buffer)
            cand_dist = entry_px - cand_sl
        else:
            nearest = min(swings)
            cand_sl = nearest * (1.0 + buffer)
            cand_dist = cand_sl - entry_px

        min_d = 0.5 * main_sigma * entry_px
        max_d = 3.0 * main_sigma * entry_px
        if cand_dist < min_d or cand_dist > max_d:
            return physics_sl

        if action == "BUY":
            return max(cand_sl, physics_sl) if cand_sl < entry_px else physics_sl
        else:
            return min(cand_sl, physics_sl) if cand_sl > entry_px else physics_sl
    except Exception:
        return physics_sl


'''


# ══════════════════════════════════════════════════════════════
#  PATCHES
# ══════════════════════════════════════════════════════════════

# ── 1. Config fields ──
CFG_ANCHOR = "SL_WIDEN_MULT: float = 1.5"
CFG_NEW_FIELDS = [
    "SUBBAR_TRUTH_ENABLED: bool = False",
    "SUBBAR_DIRECTION_CHECK: bool = True",
    "SUBBAR_ENTRY_CONFIRM: bool = True",
    "SUBBAR_STRUCTURAL_SL: bool = True",
    "SUBBAR_DIRECTION_MIN_ALIGN: float = 0.60",
    "SUBBAR_ENTRY_MAX_WAIT_SUBBARS: int = 6",
    "SUBBAR_BOUNCE_KAPPA: float = 0.20",
    "SUBBAR_SL_BUFFER: float = 0.003",
]

# ── 2. Insert new functions before compute_geodesic_kelly ──
FUNC_ANCHOR = "def compute_geodesic_kelly(ad, fi, cfg):\n"
FUNC_NEW = NEW_FUNCTIONS + FUNC_ANCHOR

# ── 3. build_signals — Layer 1 (direction filter) ──
BUILD_DIR_OLD = """            action = "BUY" if _z_dev < 0 else "SELL"

            # ══ [SELL-RND] بوابة SELL المستقلة ══
"""
BUILD_DIR_NEW = """            action = "BUY" if _z_dev < 0 else "SELL"

            # ══ [SUBBAR-TRUTH-LAYER 1] Direction filter ══
            if (getattr(CFG, 'SUBBAR_TRUTH_ENABLED', False)
                    and getattr(CFG, 'SUBBAR_DIRECTION_CHECK', True)):
                _align = _subbar_direction_score(ad, ci, action, CFG)
                _min_a = float(getattr(CFG, 'SUBBAR_DIRECTION_MIN_ALIGN', 0.60))
                if _align < _min_a:
                    log.debug(
                        f"[SubBarDir] {sym} {action} reject: "
                        f"align={_align:.2f} < {_min_a:.2f}"
                    )
                    continue

            # ══ [SELL-RND] بوابة SELL المستقلة ══
"""

# ── 4. precompute_entry_fills — Layer 2 (rejection entry) ──
PREFILL_OLD = """                if sig.action == "BUY":
                    # Live semantics: order sits AT eff_target; fills when
                    # market price reaches it (low ≤ eff_target).
                    if ad.lows[bar] <= eff_target:
                        fill_px = eff_target if use_time_decay_price \\
                                  else target0
                        stage1_fill = (bar, fill_px)
                        break
                else:
                    # Live semantics: order sits AT eff_target; fills when
                    # market price reaches it (high ≥ eff_target).
                    if ad.highs[bar] >= eff_target:
                        fill_px = eff_target if use_time_decay_price \\
                                  else target0
                        stage1_fill = (bar, fill_px)
                        break
"""
PREFILL_NEW = """                # ══ [SUBBAR-TRUTH-LAYER 2] Rejection-confirmed entry ══
                if (getattr(CFG, 'SUBBAR_TRUTH_ENABLED', False)
                        and getattr(CFG, 'SUBBAR_ENTRY_CONFIRM', True)):
                    if sig.action == "BUY" and ad.lows[bar] <= eff_target:
                        _rej = _check_subbar_rejection(
                            ad, bar, eff_target, "BUY", CFG)
                        if _rej is not None:
                            _fill_px, _sub_idx = _rej
                            _SUBBAR_ENTRY_MAP[(str(sym),
                                               int(sig.close_idx))] = int(_sub_idx)
                            stage1_fill = (bar, _fill_px)
                            break
                    elif sig.action == "SELL" and ad.highs[bar] >= eff_target:
                        _rej = _check_subbar_rejection(
                            ad, bar, eff_target, "SELL", CFG)
                        if _rej is not None:
                            _fill_px, _sub_idx = _rej
                            _SUBBAR_ENTRY_MAP[(str(sym),
                                               int(sig.close_idx))] = int(_sub_idx)
                            stage1_fill = (bar, _fill_px)
                            break
                else:
                    if sig.action == "BUY":
                        if ad.lows[bar] <= eff_target:
                            fill_px = eff_target if use_time_decay_price \\
                                      else target0
                            stage1_fill = (bar, fill_px)
                            break
                    else:
                        if ad.highs[bar] >= eff_target:
                            fill_px = eff_target if use_time_decay_price \\
                                      else target0
                            stage1_fill = (bar, fill_px)
                            break
"""

# ── 5. simulate_portfolio — Layer 3 (structural SL) ──
SIM_SL_OLD = """        if sig.action == "BUY":
            sig.sl  = opt_px - _design_sl_dist
            sig.tp1 = opt_px + _design_tp_dist
        else:
            sig.sl  = opt_px + _design_sl_dist
            sig.tp1 = opt_px - _design_tp_dist
"""
SIM_SL_NEW = """        if sig.action == "BUY":
            sig.sl  = opt_px - _design_sl_dist
            sig.tp1 = opt_px + _design_tp_dist
        else:
            sig.sl  = opt_px + _design_sl_dist
            sig.tp1 = opt_px - _design_tp_dist

        # ══ [SUBBAR-TRUTH-LAYER 3] Structural SL replacement ══
        if (getattr(CFG, 'SUBBAR_TRUTH_ENABLED', False)
                and getattr(CFG, 'SUBBAR_STRUCTURAL_SL', True)):
            _physics_sl = float(sig.sl)
            _map_key = (str(sym), int(sig.close_idx))
            _max_j = _SUBBAR_ENTRY_MAP.get(_map_key, None)
            _struct_sl = _compute_structural_sl(
                ad, opt_ci, opt_px, sig.action,
                _physics_sl, _design_sl_dist, CFG, max_sub_idx=_max_j
            )
            if sig.action == "BUY" and _struct_sl > _physics_sl and _struct_sl < opt_px:
                sig.sl = _struct_sl
                _design_sl_dist = opt_px - _struct_sl
                log.debug(
                    f"[SubBarSL] {sym} BUY SL {_physics_sl:.6f}->{_struct_sl:.6f} "
                    f"(dist {_design_sl_dist:.6f})"
                )
            elif sig.action == "SELL" and _struct_sl < _physics_sl and _struct_sl > opt_px:
                sig.sl = _struct_sl
                _design_sl_dist = _struct_sl - opt_px
                log.debug(
                    f"[SubBarSL] {sym} SELL SL {_physics_sl:.6f}->{_struct_sl:.6f} "
                    f"(dist {_design_sl_dist:.6f})"
                )
"""

# ── 6. _promote_pending_to_position — Layer 3 in live ──
PROMOTE_OLD = """    if rec['action'] == 'BUY':
        adapted_sl = entry_price - orig_sl_dist
        adapted_tp = entry_price + orig_tp_dist
    else:
        adapted_sl = entry_price + orig_sl_dist
        adapted_tp = entry_price - orig_tp_dist
"""
PROMOTE_NEW = """    if rec['action'] == 'BUY':
        adapted_sl = entry_price - orig_sl_dist
        adapted_tp = entry_price + orig_tp_dist
    else:
        adapted_sl = entry_price + orig_sl_dist
        adapted_tp = entry_price - orig_tp_dist

    # ══ [SUBBAR-TRUTH-LAYER 3 — LIVE] Structural SL ══
    if (getattr(CFG, 'SUBBAR_TRUTH_ENABLED', False)
            and getattr(CFG, 'SUBBAR_STRUCTURAL_SL', True)):
        _ad_ref = rec.get('ad_ref')
        _eci = int(rec.get('close_idx') or 0)
        if _ad_ref is not None and _eci > 0:
            _map_key = (str(sym), int(rec.get('close_idx') or 0))
            _max_j = _SUBBAR_ENTRY_MAP.get(_map_key, None)
            _struct_sl = _compute_structural_sl(
                _ad_ref, _eci, entry_price, rec['action'],
                adapted_sl, orig_sl_dist, CFG, max_sub_idx=_max_j
            )
            if (rec['action'] == 'BUY' and _struct_sl > adapted_sl
                    and _struct_sl < entry_price):
                _old = adapted_sl
                adapted_sl = _struct_sl
                orig_sl_dist = entry_price - _struct_sl
                log.info(f"[SubBarSL-LV] {sym} BUY SL {_old:.6f}->{_struct_sl:.6f}")
            elif (rec['action'] == 'SELL' and _struct_sl < adapted_sl
                    and _struct_sl > entry_price):
                _old = adapted_sl
                adapted_sl = _struct_sl
                orig_sl_dist = _struct_sl - entry_price
                log.info(f"[SubBarSL-LV] {sym} SELL SL {_old:.6f}->{_struct_sl:.6f}")
"""

# ── 7. CLI ──
CLI_OLD = """    p.add_argument("--tp-mult", type=float, default=None,
                   help="Override TP_MULT")
"""
CLI_NEW = """    p.add_argument("--tp-mult", type=float, default=None,
                   help="Override TP_MULT")
    p.add_argument("--subbar-truth", action="store_true",
                   help="Enable Sub-Bar Truth Layer (direction + rejection + structural SL)")
    p.add_argument("--no-subbar-direction", action="store_true",
                   help="Disable Layer 1 (direction filter)")
    p.add_argument("--no-subbar-entry", action="store_true",
                   help="Disable Layer 2 (rejection entry)")
    p.add_argument("--no-subbar-sl", action="store_true",
                   help="Disable Layer 3 (structural SL)")
"""

# ── 8. Wiring ──
WIRING_OLD = """    if getattr(args, "tp_mult", None) is not None:
        CFG.TP_MULT = float(args.tp_mult)
        log.info(f"[Ablation] TP_MULT = {CFG.TP_MULT}")
"""
WIRING_NEW = """    if getattr(args, "tp_mult", None) is not None:
        CFG.TP_MULT = float(args.tp_mult)
        log.info(f"[Ablation] TP_MULT = {CFG.TP_MULT}")
    if getattr(args, "subbar_truth", False):
        CFG.SUBBAR_TRUTH_ENABLED = True
        if getattr(args, "no_subbar_direction", False):
            CFG.SUBBAR_DIRECTION_CHECK = False
        if getattr(args, "no_subbar_entry", False):
            CFG.SUBBAR_ENTRY_CONFIRM = False
        if getattr(args, "no_subbar_sl", False):
            CFG.SUBBAR_STRUCTURAL_SL = False
        log.info(
            f"[SubBarTruth] ENABLED | "
            f"direction={CFG.SUBBAR_DIRECTION_CHECK} "
            f"entry={CFG.SUBBAR_ENTRY_CONFIRM} "
            f"sl={CFG.SUBBAR_STRUCTURAL_SL}"
        )
        if CFG.SUBBAR_ENTRY_CONFIRM:
            log.info(
                f"[SubBarTruth] Layer 2 requires Stage-1 rejection; "
                f"Stage 2 (market) still active as fallback. "
                f"Use --no-unified-stage2 to disable it."
            )
    else:
        log.info("[SubBarTruth] DISABLED (use --subbar-truth to enable)")
"""


# ══════════════════════════════════════════════════════════════
#  Build patch list
# ══════════════════════════════════════════════════════════════

def build_patches():
    patches = []
    # Config fields: chain insert after each one
    prev_anchor = CFG_ANCHOR
    for field in CFG_NEW_FIELDS:
        name = field.split(":")[0].strip()
        patches.append({
            "name": f"Config: + {name}",
            "kind": "add_field",
            "decl": field,
            "after": prev_anchor,
        })
        prev_anchor = name

    # Functions
    patches.append({
        "name": "Add 3 SubBar functions + global map",
        "kind": "exact",
        "old": FUNC_ANCHOR,
        "new": FUNC_NEW,
        "marker": "[SUBBAR-TRUTH-LAYER]",
    })

    # Direction filter
    patches.append({
        "name": "build_signals: Layer 1 (direction)",
        "kind": "exact",
        "old": BUILD_DIR_OLD,
        "new": BUILD_DIR_NEW,
        "marker": "[SUBBAR-TRUTH-LAYER 1]",
    })

    # Entry rejection
    patches.append({
        "name": "precompute_entry_fills: Layer 2 (rejection)",
        "kind": "exact",
        "old": PREFILL_OLD,
        "new": PREFILL_NEW,
        "marker": "[SUBBAR-TRUTH-LAYER 2]",
    })

    # Structural SL
    patches.append({
        "name": "simulate_portfolio: Layer 3 (structural SL)",
        "kind": "exact",
        "old": SIM_SL_OLD,
        "new": SIM_SL_NEW,
        "marker": "[SUBBAR-TRUTH-LAYER 3] Structural SL replacement",
    })

    # Live structural SL
    patches.append({
        "name": "_promote_pending: Layer 3 in live",
        "kind": "exact",
        "old": PROMOTE_OLD,
        "new": PROMOTE_NEW,
        "marker": "[SUBBAR-TRUTH-LAYER 3 — LIVE]",
    })

    # CLI
    patches.append({
        "name": "CLI: --subbar-truth + 3 disablers",
        "kind": "exact",
        "old": CLI_OLD,
        "new": CLI_NEW,
        "marker": "--subbar-truth",
    })

    # Wiring
    patches.append({
        "name": "main(): wiring",
        "kind": "exact",
        "old": WIRING_OLD,
        "new": WIRING_NEW,
        "marker": "[SubBarTruth] ENABLED",
    })

    return patches


# ══════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_TARGET)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--verbose", action="store_true")
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
        print(f"[ERROR] pre-patch syntax: {err}", file=sys.stderr)
        return 3
    print("[OK] Original syntax verified.\n")

    text = original
    results = []
    for p in build_patches():
        try:
            if p["kind"] == "add_field":
                text, st = _add_field(text, p["decl"], p["after"])
            else:
                text, st = _apply_exact(text, p["old"], p["new"], p["marker"])
        except Exception as e:
            st = f"EXCEPTION:{e}"
        results.append((p["name"], st))
        icon = {"applied": "✅", "already_applied": "⏭️"}.get(st, "❌")
        print(f"  {icon} {p['name']:48s} [{st}]")

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
        print(f"\n[ERROR] post-patch syntax: {err}", file=sys.stderr)
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
    print("\nNext:")
    print("  python3 trading_2_live4_claude2_v4_micro_pro.py ... --subbar-truth")
    print("  (all three layers active; disable individually with")
    print("   --no-subbar-direction / --no-subbar-entry / --no-subbar-sl)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
