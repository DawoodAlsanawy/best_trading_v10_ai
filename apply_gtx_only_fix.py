#!/usr/bin/env python3
"""
apply_gtx_only_fix.py

Simplifies _execute_reversal_fill to a pure GTX-limit strategy:

  * Always places a Post-Only (GTX) limit at `target`
  * No market fallback
  * No drift check (a rejected GTX means the bounce failed → EXPIRED)
  * No REVERSAL_FILL_AT variants (target is the only fill price)

Rationale:
  The signal targets a strong support/resistance level where the market
  tends to oscillate. If GTX is rejected (price already crossed back),
  the bounce was not real — the watcher expires instead of chasing.

Requires: apply_live_reversal.py already applied (checks for
_execute_reversal_fill).

Run:  python apply_gtx_only_fix.py
"""
import os, sys, shutil, hashlib

SRC = "trading_2_live4.py"
if not os.path.exists(SRC):
    print(f"✗ {SRC} not found", file=sys.stderr); sys.exit(1)

src_text = open(SRC).read()
if "_execute_reversal_fill" not in src_text:
    print("✗ _execute_reversal_fill not found. Run "
          "apply_live_reversal.py first.", file=sys.stderr)
    sys.exit(2)

if "GTX-ONLY" in src_text:
    print("✗ Already patched. Restore from .bak first.", file=sys.stderr)
    sys.exit(3)

shutil.copy2(SRC, SRC + ".bak")
print(f"✓ backup → {SRC}.bak\n")

with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()
orig = s
report = []

def patch(old, new, label, required=True):
    global s
    if old not in s:
        report.append(("✗" if required else "⚠") + f" {label}")
        return False
    s = s.replace(old, new, 1)
    report.append("✓ " + label)
    return True

# ═══════════════════════════════════════════════════════════════
# Replace the entire block from "fill_mode = ..." through the end
# of the fill branch (right before "if entry_px <= 0 or actual_qty <= 0:")
# ═══════════════════════════════════════════════════════════════

OLD_BLOCK = '''    fill_mode = str(getattr(CFG, "REVERSAL_FILL_AT", "target"))
    if fill_mode == "close" and current > 0:
        fill_px = current
    elif fill_mode == "best" and current > 0:
        fill_px = (min(target, current) if action == "BUY"
                   else max(target, current))
    else:
        fill_px = target

    # Leverage / margin
    try:
        ensure_symbol_setup(exchange, sym, int(w["leverage"]),
                             margin_mode="isolated")
    except Exception as e:
        log.warning(f"[LiveRev] setup {sym}: {e}")
        w["status"] = "EXPIRED"
        return

    drift = (abs(current - target) / max(target, 1e-9)
             if current > 0 else 0.0)
    entry_px = 0.0
    actual_qty = 0.0

    if drift > 0.003:
        # Market fill — price moved too far from target
        try:
            o = exchange.create_order(sym, "market", side, qty, None)
            v = verify_fill(exchange, o["id"], sym, timeout_s=2.5)
            if not (v and v.get("filled")):
                log.warning(f"[LiveRev] {sym} market no fill")
                w["status"] = "EXPIRED"
                return
            entry_px = float(v.get("avg_price") or fill_px)
            actual_qty = float(v.get("qty") or qty)
        except Exception as e:
            log.error(f"[LiveRev] {sym} market failed: {e}")
            w["status"] = "EXPIRED"
            return
    else:
        # GTX limit at fill_px (maker)
        result = execute_post_only(
            exchange, sym, side, qty,
            fixed_target=float(fill_px),
            fallback_market=False,
            reduce_only=False,
        )
        if not result.get("filled_qty") or result["filled_qty"] <= 0:
            log.warning(f"[LiveRev] {sym} GTX no fill "
                        f"({result.get('reason')})")
            w["status"] = "EXPIRED"
            return
        entry_px = float(result["avg_price"])
        actual_qty = float(result["filled_qty"])'''

NEW_BLOCK = '''    # ═══ [GTX-ONLY] Post-Only at target. Nothing else. ═══
    # The signal anchors on a strong support/resistance level where the
    # market oscillates before committing. If GTX is rejected, the
    # bounce was a fake — the watcher expires cleanly.
    fill_px = float(target)

    # Leverage / margin setup (safe: no position exists yet)
    try:
        ensure_symbol_setup(exchange, sym, int(w["leverage"]),
                             margin_mode="isolated")
    except Exception as e:
        log.warning(f"[LiveRev] setup {sym}: {e}")
        w["status"] = "EXPIRED"
        return

    entry_px = 0.0
    actual_qty = 0.0

    result = execute_post_only(
        exchange, sym, side, qty,
        fixed_target=float(fill_px),
        fallback_market=False,
        reduce_only=False,
    )
    if not result.get("filled_qty") or result["filled_qty"] <= 0:
        _reason = result.get("reason", "unknown")
        log.info(f"[LiveRev] {sym} GTX at {fill_px:.6f} not filled "
                 f"({_reason}) — watcher expired")
        w["status"] = "EXPIRED"
        return
    entry_px = float(result["avg_price"])
    actual_qty = float(result["filled_qty"])'''

patch(OLD_BLOCK, NEW_BLOCK, "_execute_reversal_fill: GTX-only")

# ═══════════════════════════════════════════════════════════════
# Mark REVERSAL_FILL_AT as deprecated in Config
# ═══════════════════════════════════════════════════════════════
OLD_CFG = '    REVERSAL_FILL_AT:        str   = "target" # target|close|best'
NEW_CFG = ('    REVERSAL_FILL_AT:        str   = "target" '
           '# [DEPRECATED] always target')
patch(OLD_CFG, NEW_CFG, "CFG: mark REVERSAL_FILL_AT deprecated",
      required=False)

# ═══════════════════════════════════════════════════════════════
# Also drop the fetch_ticker call — no longer needed
# ═══════════════════════════════════════════════════════════════
OLD_TICK = '''    try:
        _rate_record(2.0)
        tk = exchange.fetch_ticker(sym)
        current = float(tk.get("last") or 0)
    except Exception:
        current = target

'''
NEW_TICK = '''    # [GTX-ONLY] No ticker fetch needed — GTX validates itself.
'''
patch(OLD_TICK, NEW_TICK, "_execute_reversal_fill: drop ticker fetch",
      required=False)

# ═══════════════════════════════════════════════════════════════
# Write
# ═══════════════════════════════════════════════════════════════
if s == orig:
    print("⚠  No changes applied:", file=sys.stderr)
    for line in report:
        print("   " + line, file=sys.stderr)
    sys.exit(2)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 68)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 68)
for line in report:
    print("   " + line)
print("═" * 68)
