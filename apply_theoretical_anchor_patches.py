#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  apply_theoretical_anchor_patches.py                                         ║
║                                                                              ║
║  يجعل SL/TP مُثبتة على sig.price (السعر النظري للإشارة) في كل المسارات:    ║
║    Live  : 1) _rev_finalize  2) _promote_pending_to_position                ║
║            3) run_live inline (legacy)  4) _lad_new_pos + _lad_sync         ║
║    BT    : 5) simulate_portfolio (SL/TP setup)                              ║
║            6) simulate_portfolio (post-slippage)                             ║
║            7) LiqGate (_sl_gap uses actual risk)                             ║
║                                                                              ║
║  الأمان: backup + idempotent + AST verification + auto-rollback              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys, os, shutil, subprocess
from datetime import datetime

BOT = sys.argv[1] if len(sys.argv) > 1 else "trading_2_live4_claude2_v4_mic.py"

if not os.path.exists(BOT):
    print(f"❌ Not found: {BOT}")
    sys.exit(1)

with open(BOT, 'r', encoding='utf-8') as f:
    content = f.read()
original = content

applied, skipped, failed = [], [], []


def patch(name, variants, new_str):
    """Try each old variant; apply the unique match; skip if new_str exists."""
    global content
    if new_str in content:
        skipped.append(name); print(f"  ⏭  {name}: already applied"); return
    matches = [(i, v) for i, v in enumerate(variants) if content.count(v) == 1]
    if not matches:
        counts = [content.count(v) for v in variants]
        failed.append(f"{name} (counts={counts})")
        print(f"  ❌ {name}: no unique match (counts={counts})"); return
    i, old = matches[0]
    content = content.replace(old, new_str)
    applied.append(name)
    suffix = f" (variant {i+1})" if len(variants) > 1 else ""
    print(f"  ✅ {name}{suffix}")


# ═══════════════════════════════════════════════════════════════
# PATCH 1 — _rev_finalize (Live ROE path)
# ═══════════════════════════════════════════════════════════════
print("\n[1/7] _rev_finalize → anchor to sig_price")

old1_with_comments = '''    _max_sl_frac = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
    if orig_sl_dist > entry_px * _max_sl_frac:
        _rr = orig_tp_dist / max(orig_sl_dist, 1e-12)
        orig_sl_dist = entry_px * _max_sl_frac
        orig_tp_dist = orig_sl_dist * _rr
#    theoretical_px = float(w["target"])
    if action == "BUY":
        new_sl = entry_px - orig_sl_dist
        new_tp = entry_px + orig_tp_dist
#        new_sl = theoretical_px - orig_sl_dist
#        new_tp = theoretical_px + orig_tp_dist
    else:
        new_sl = entry_px + orig_sl_dist
        new_tp = entry_px - orig_tp_dist
#        new_sl = theoretical_px + orig_sl_dist
#        new_tp = theoretical_px - orig_tp_dist
'''

old1_no_comments = '''    _max_sl_frac = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
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

new1 = '''    _theoretical_px = float(w.get("sig_price") or w.get("target") or entry_px)
    _max_sl_frac = 0.015 * float(getattr(CFG, "SL_WIDEN_MULT", 1.0))
    if orig_sl_dist > _theoretical_px * _max_sl_frac:
        _rr = orig_tp_dist / max(orig_sl_dist, 1e-12)
        orig_sl_dist = _theoretical_px * _max_sl_frac
        orig_tp_dist = orig_sl_dist * _rr
    if action == "BUY":
        new_sl = _theoretical_px - orig_sl_dist
        new_tp = _theoretical_px + orig_tp_dist
    else:
        new_sl = _theoretical_px + orig_sl_dist
        new_tp = _theoretical_px - orig_tp_dist
'''
patch("rev_finalize", [old1_with_comments, old1_no_comments], new1)


# ═══════════════════════════════════════════════════════════════
# PATCH 2 — _promote_pending_to_position (Live pending path)
# ═══════════════════════════════════════════════════════════════
print("\n[2/7] _promote_pending_to_position → anchor to sig_price")

old2 = '''    rr = orig_tp_dist / orig_sl_dist
    # Cap scales with widening so the loosened SL isn't re-clipped.
    max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
    if orig_sl_dist > entry_price * max_sl_frac:
        orig_sl_dist = entry_price * max_sl_frac
        orig_tp_dist = orig_sl_dist * rr

    if rec['action'] == 'BUY':
        adapted_sl = entry_price - orig_sl_dist
        adapted_tp = entry_price + orig_tp_dist
    else:
        adapted_sl = entry_price + orig_sl_dist
        adapted_tp = entry_price - orig_tp_dist
'''

new2 = '''    _theoretical_px = float(rec.get('sig_price') or rec.get('price') or entry_price)
    rr = orig_tp_dist / orig_sl_dist
    # Cap scales with widening so the loosened SL isn't re-clipped.
    max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
    if orig_sl_dist > _theoretical_px * max_sl_frac:
        orig_sl_dist = _theoretical_px * max_sl_frac
        orig_tp_dist = orig_sl_dist * rr

    if rec['action'] == 'BUY':
        adapted_sl = _theoretical_px - orig_sl_dist
        adapted_tp = _theoretical_px + orig_tp_dist
    else:
        adapted_sl = _theoretical_px + orig_sl_dist
        adapted_tp = _theoretical_px - orig_tp_dist
'''
patch("promote_pending", [old2], new2)


# ═══════════════════════════════════════════════════════════════
# PATCH 3 — LiqGate _sl_gap (use actual risk)
# ═══════════════════════════════════════════════════════════════
print("\n[3/7] LiqGate _sl_gap → actual risk")

old3 = '''        _sl_gap = orig_sl_dist
        _safe_mult = float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5))'''

new3 = '''        _sl_gap = abs(entry_price - adapted_sl)  # actual risk, not theoretical
        _safe_mult = float(getattr(CFG, 'LIQ_SAFETY_MULT', 1.5))'''
patch("liqgate_sl_gap", [old3], new3)


# ═══════════════════════════════════════════════════════════════
# PATCH 4 — run_live inline (legacy blocking path)
# ═══════════════════════════════════════════════════════════════
print("\n[4/7] run_live inline (legacy) → anchor to sig.price")

old4 = '''                        rr_ratio = orig_tp_dist / orig_sl_dist
                        # [SL-CLIP-CONSISTENCY] Scale with SL_WIDEN_MULT
                        # so the widened SL isn't re-clipped back to 1.5%.
                        max_sl_frac = 0.015 * float(
                            getattr(CFG, 'SL_WIDEN_MULT', 1.0)
                        )
                        if orig_sl_dist > entry_price * max_sl_frac:
                            orig_sl_dist = entry_price * max_sl_frac
                            orig_tp_dist = orig_sl_dist * rr_ratio

                        if sig.action == "BUY":
                            adapted_sl = entry_price - orig_sl_dist
                            adapted_tp = entry_price + orig_tp_dist
                        else:
                            adapted_sl = entry_price + orig_sl_dist
                            adapted_tp = entry_price - orig_tp_dist
'''

new4 = '''                        _theoretical_px = float(sig.price)
                        rr_ratio = orig_tp_dist / orig_sl_dist
                        # [SL-CLIP-CONSISTENCY] Scale with SL_WIDEN_MULT
                        # so the widened SL isn't re-clipped back to 1.5%.
                        max_sl_frac = 0.015 * float(
                            getattr(CFG, 'SL_WIDEN_MULT', 1.0)
                        )
                        if orig_sl_dist > _theoretical_px * max_sl_frac:
                            orig_sl_dist = _theoretical_px * max_sl_frac
                            orig_tp_dist = orig_sl_dist * rr_ratio

                        if sig.action == "BUY":
                            adapted_sl = _theoretical_px - orig_sl_dist
                            adapted_tp = _theoretical_px + orig_tp_dist
                        else:
                            adapted_sl = _theoretical_px + orig_sl_dist
                            adapted_tp = _theoretical_px - orig_tp_dist
'''
patch("run_live_inline", [old4], new4)


# ═══════════════════════════════════════════════════════════════
# PATCH 5 — simulate_portfolio main SL/TP block (Backtest)
# ═══════════════════════════════════════════════════════════════
print("\n[5/7] simulate_portfolio main block → anchor to sig.price")

old5 = '''        # ══ [SL/TP SETUP — works for both fixed and no-fix] ══
        # Design distances from the original signal (preserves R:R intent).
        _design_sl_dist = abs(sig.price - sig.sl)
        _design_tp_dist = abs(sig.tp1 - sig.price)
        if _design_sl_dist <= 1e-12:
            continue

        # Clip SL to max_sl_frac × opt_px (entry-based cap)
        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        if _design_sl_dist > opt_px * _max_sl_frac:
            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)
            _design_sl_dist = opt_px * _max_sl_frac
            _design_tp_dist = _design_sl_dist * _rr

        # ══ [CRITICAL FIX] Rebuild sig.sl / sig.tp1 from opt_px ══
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

        sl_distance = _design_sl_dist
        tp_distance = _design_tp_dist

        if sig.action == "BUY":
            sl_h = opt_px - sl_distance
        else:
            sl_h = opt_px + sl_distance

        delta = abs(opt_px - sl_h)
        if delta < 1e-8: continue
'''

new5 = '''        # ══ [SL/TP SETUP — theoretical anchor] ══
        # SL/TP anchored to sig.price (theoretical), NOT to opt_px.
        _design_sl_dist = abs(sig.price - sig.sl)
        _design_tp_dist = abs(sig.tp1 - sig.price)
        if _design_sl_dist <= 1e-12:
            continue

        # Clip against theoretical (signal) price, not entry
        _theoretical_px = float(sig.price)
        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
        if _design_sl_dist > _theoretical_px * _max_sl_frac:
            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)
            _design_sl_dist = _theoretical_px * _max_sl_frac
            _design_tp_dist = _design_sl_dist * _rr

        # ══ [THEORETICAL ANCHOR] SL/TP anchored to signal price ══
        if sig.action == "BUY":
            sig.sl  = _theoretical_px - _design_sl_dist
            sig.tp1 = _theoretical_px + _design_tp_dist
        else:
            sig.sl  = _theoretical_px + _design_sl_dist
            sig.tp1 = _theoretical_px - _design_tp_dist

        sl_distance = _design_sl_dist
        tp_distance = _design_tp_dist

        # SL price is theoretical (independent of entry slippage)
        sl_h = float(sig.sl)
        delta = abs(opt_px - sl_h)   # Actual risk from entry to theoretical SL
        if delta < 1e-8: continue
'''
patch("sim_portfolio_main", [old5], new5)


# ═══════════════════════════════════════════════════════════════
# PATCH 6 — simulate_portfolio post-slippage (Backtest)
# ═══════════════════════════════════════════════════════════════
print("\n[6/7] simulate_portfolio post-slippage → SL stays fixed")

old6 = '''        # تعديل إحداثيات الوقف بناءً على سعر الدخول الفعلي بعد انزلاق الشبكة
        if sig.action == "BUY":
            sl_h = eff_px - sl_distance
        else:
            sl_h = eff_px + sl_distance

        delta = abs(eff_px - sl_h)
        if delta < 1e-8: continue
'''

new6 = '''        # ══ [THEORETICAL ANCHOR] SL stays at sig.sl after slippage ══
        sl_h = float(sig.sl)
        delta = abs(eff_px - sl_h)   # Actual risk from effective entry
        if delta < 1e-8: continue
'''
patch("sim_portfolio_post_slip", [old6], new6)


# ═══════════════════════════════════════════════════════════════
# PATCH 7 — Ladder (optional, only used if REV_LADDER_ENABLED=True)
# ═══════════════════════════════════════════════════════════════
print("\n[7/7] Ladder → anchor to sig_price")

old7a = '''    if pos is None:
        pos = _lad_new_pos(sym, w, dc / dq, dq, assets)'''

new7a = '''    if pos is None:
        _theoretical_px_lad = float(w.get("sig_price") or w.get("target") or (dc / dq))
        pos = _lad_new_pos(sym, w, _theoretical_px_lad, dq, assets)'''
patch("ladder_new_pos", [old7a], new7a)

old7b = '''        sl, tp, osd = _lad_sl_tp(w, ne)'''

new7b = '''        _theoretical_px_lad = float(w.get("sig_price") or w.get("target") or ne)
        sl, tp, osd = _lad_sl_tp(w, _theoretical_px_lad)'''
patch("ladder_grow", [old7b], new7b)


# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print("\n" + "═" * 72)
print("📊 SUMMARY")
print("═" * 72)
print(f"  ✅ Applied: {len(applied)}")
print(f"  ⏭  Skipped: {len(skipped)}")
print(f"  ❌ Failed : {len(failed)}")
if failed:
    for p in failed:
        print(f"     - {p}")

if content == original:
    print("\n⏸  No changes made.")
    sys.exit(0 if not failed else 1)

# Backup + write
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"{BOT}.backup_{ts}"
shutil.copy2(BOT, backup)
print(f"\n💾 Backup: {backup}")

with open(BOT, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"✅ Written: {BOT}")

# Syntax check
print("\n⏳ Verifying syntax...")
res = subprocess.run(
    [sys.executable, "-c",
     f"import ast; ast.parse(open(r'{BOT}', encoding='utf-8').read())"],
    capture_output=True, text=True
)
if res.returncode == 0:
    print("✅ Syntax OK")
else:
    print("❌ SYNTAX ERROR:")
    print(res.stderr)
    shutil.copy2(backup, BOT)
    print(f"🔄 Rolled back from backup")
    sys.exit(1)

print("\n" + "═" * 72)
print("✨ Done. Behavior after patch:")
print("═" * 72)
print("""
 • SL/TP are ALWAYS anchored to sig.price (theoretical)
 • Actual entry slippage does NOT shift SL/TP levels
 • qty sizing still respects actual risk = |entry − sig.sl|
 • Backtest and Live produce IDENTICAL SL/TP for the same signal

 ⚠️  Edge case warning:
 If entry crosses theoretical SL (e.g., BUY filled below sig.sl),
 the position will exit at theoretical SL immediately (small gain).
 This is mathematically consistent but may surprise you.
""")
print(f"Rollback: cp {backup} {BOT}")
