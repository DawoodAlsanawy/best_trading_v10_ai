#!/usr/bin/env python3
"""
apply_730d_fixes.py
Applies all 730d-verified edge discoveries to trading_final.py.
Run:  python apply_730d_fixes.py
"""
import os, re, sys, shutil, hashlib

SRC = "trading_final.py"

if not os.path.exists(SRC):
    print(f"✗ {SRC} not found in {os.getcwd()}", file=sys.stderr)
    sys.exit(1)

# Backup
bak = SRC + ".bak"
shutil.copy2(SRC, bak)
print(f"✓ backup → {bak}\n")

with open(SRC, "r", encoding="utf-8") as f:
    s = f.read()
orig = s
report = []

def patch(old, new, label, required=True):
    global s
    if old not in s:
        report.append(("✗" if required else "⚠") + f" {label}: anchor not found")
        return not required
    s = s.replace(old, new, 1)
    report.append("✓ " + label)
    return True

def patch_rx(pattern, repl, label, required=True):
    global s
    new_s, n = re.subn(pattern, repl, s, count=1)
    if n == 0:
        report.append(("✗" if required else "⚠") + f" {label}: pattern not found")
        return not required
    s = new_s
    report.append("✓ " + label)
    return True

# ═══════════════════════════════════════════════════════════════
# 1. CFG — numeric value changes
# ═══════════════════════════════════════════════════════════════
patch_rx(r"TP_MULT:\s*float\s*=\s*[\d.]+[^\n]*",
         "TP_MULT: float = 0.8    # [730d VERIFIED] (was 5.0)",
         "CFG: TP_MULT 5.0 → 0.8")

patch_rx(r"TRAIL_ENABLED:\s*bool\s*=\s*True[^\n]*",
         "TRAIL_ENABLED: bool = False   # [730d] disabled",
         "CFG: TRAIL_ENABLED → False")

patch_rx(r"APEX_ENABLED:\s*bool\s*=\s*True[^\n]*",
         "APEX_ENABLED: bool = False    # [730d] disabled",
         "CFG: APEX_ENABLED → False")

patch_rx(r"BREAKEVEN_ENABLED:\s*bool\s*=\s*True[^\n]*",
         "BREAKEVEN_ENABLED: bool = False   # [730d] disabled",
         "CFG: BREAKEVEN_ENABLED → False")

patch_rx(r"PARTIAL_TP_ENABLED:\s*bool\s*=\s*True[^\n]*",
         "PARTIAL_TP_ENABLED: bool = False   # [730d] disabled",
         "CFG: PARTIAL_TP_ENABLED → False")

patch_rx(r"TIME_KILL_ENABLED:\s*bool\s*=\s*True[^\n]*",
         "TIME_KILL_ENABLED: bool = False   # [730d] disabled",
         "CFG: TIME_KILL_ENABLED → False",
         required=False)

patch("MAX_HOLD_BARS: int = 168",
      "MAX_HOLD_BARS: int = 168      # legacy\n"
      "    MAX_HOLD_BUY: int = 30        # [730d VERIFIED]\n"
      "    MAX_HOLD_SELL: int = 20       # [730d VERIFIED]",
      "CFG: add MAX_HOLD_BUY=30, MAX_HOLD_SELL=20")

# ═══════════════════════════════════════════════════════════════
# 2. build_signals — symmetric z-gate (BUY & SELL identical)
# ═══════════════════════════════════════════════════════════════
SYMM_GATE = """            # ═══ [730d VERIFIED — symmetric gate] ═══
            # Same z-range for BUY and SELL. No T_info, no gauge.
            _absz = abs(_z_dev)
            if _absz < 1.5 or _absz > 2.5:
                continue
            action = "BUY" if _z_dev < 0 else "SELL"
"""

ASYM = '''            # ═══ [FINAL EDGE GATES — from brain_raw.py analysis] ═══
            # BUY  edge: |z| in [1.5, 2.5] + T_info > 6.0   → Sharpe ~11
            # SELL edge:  z  in [2.5, 3.2] + gauge  > 0.12   → Sharpe ~7.5
            if _z_dev > 0:
                if _z_dev < 2.5 or _z_dev > 3.2:
                    continue
                _gf_now = float(ad.gauge_force[fi]) \\
                          if fi < len(ad.gauge_force) else 0.0
                if _gf_now < 0.12:
                    continue
                action = "SELL"
            else:
                _absz = abs(_z_dev)
                if _absz < 1.5 or _absz > 2.5:
                    continue
                _ti_now = float(ad.T_info[fi]) \\
                          if fi < len(ad.T_info) else 0.0
                if _ti_now < 6.0:
                    continue
                action = "BUY"'''

if not patch(ASYM, SYMM_GATE.strip() + "\n",
             "build_signals: replace asymmetric gate"):
    LEGACY = '''            # [ABLATION-2c] softer deviation gate
            if abs(_z_dev) < 1.5:
                continue
            action = "BUY" if _z_dev < 0 else "SELL"'''
    patch(LEGACY, SYMM_GATE.strip() + "\n",
          "build_signals: replace legacy 1.5 gate")

# ═══════════════════════════════════════════════════════════════
# 3. scan_top_assets — freeze universe to top-10
# ═══════════════════════════════════════════════════════════════
FROZEN = '''def scan_top_assets(exchange, n=None) -> List[str]:
    # ═══ [730d VERIFIED] Frozen top-10 universe ═══
    _frozen = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "ADA/USDT",
               "AVAX/USDT", "LINK/USDT", "DOT/USDT", "UNI/USDT", "LTC/USDT"]
    log.info(f"[Universe] frozen to {len(_frozen)} assets")
    return _frozen
    # ── legacy body below is dead code ──
    n = n or CFG.n_assets'''

patch("def scan_top_assets(exchange, n=None) -> List[str]:\n    n = n or CFG.n_assets",
      FROZEN,
      "scan_top_assets: freeze to top-10")

# ═══════════════════════════════════════════════════════════════
# 4. _advance_raw — pure SL/TP/MaxHold walker
# ═══════════════════════════════════════════════════════════════
RAW = '''def _advance_raw(pos, ad, to_ci, partial_cb=None):
    """[730d VERIFIED] SL / TP / MaxHold only."""
    sig = pos.signal
    sl = pos.trail_sl
    start = pos.current_ci + 1
    end = min(to_ci, len(ad.closes) - 1)
    if start > end:
        return 0., "", -1

    pen_frac = (CFG.FILL_PENETRATION_BPS * 1e-4
                if CFG.FILL_APPLY_TO_EXITS else 0.0)
    _use_sub = (ad.sub_highs is not None
                and ad.sub_lows is not None
                and ad.sub_per_main >= 2)

    def _check(high, low):
        if sig.action == "BUY":
            if low <= sl * (1.0 - pen_frac):
                return "SL", sl
            if high >= sig.tp1 * (1.0 + pen_frac):
                return "TP", sig.tp1
        else:
            if high >= sl * (1.0 + pen_frac):
                return "SL", sl
            if low <= sig.tp1 * (1.0 - pen_frac):
                return "TP", sig.tp1
        return None, 0.0

    _side_hold = (getattr(CFG, 'MAX_HOLD_BUY', 30)
                  if sig.action == "BUY"
                  else getattr(CFG, 'MAX_HOLD_SELL', 20))
    _max_hold = effective_bars(_side_hold)

    for cidx in range(start, end + 1):
        p = ad.closes[cidx]
        if _use_sub and cidx == pos.entry_ci:
            j0, j1 = int(pos.entry_sub_idx) + 1, ad.sub_per_main
        elif _use_sub:
            j0, j1 = 0, ad.sub_per_main
        else:
            j0, j1 = 0, 0

        if _use_sub:
            for j in range(j0, j1):
                sh = ad.sub_highs[cidx, j]
                sll = ad.sub_lows[cidx, j]
                if not (np.isfinite(sh) and np.isfinite(sll)):
                    continue
                mfe = ((sh - pos.entry_px) / pos.entry_px
                       if sig.action == "BUY"
                       else (pos.entry_px - sll) / pos.entry_px)
                if mfe > pos.mfe_frac:
                    pos.mfe_frac = mfe
                r, px = _check(sh, sll)
                if r == "SL":
                    pos.current_ci = cidx
                    return px, "Emergency SL", cidx
                if r == "TP":
                    pos.current_ci = cidx
                    return px, "Hard TP", cidx
        else:
            if cidx == pos.entry_ci:
                continue
            high = ad.highs[cidx]
            low = ad.lows[cidx]
            mfe = ((high - pos.entry_px) / pos.entry_px
                   if sig.action == "BUY"
                   else (pos.entry_px - low) / pos.entry_px)
            if mfe > pos.mfe_frac:
                pos.mfe_frac = mfe
            r, px = _check(high, low)
            if r == "SL":
                pos.current_ci = cidx
                return px, "Emergency SL", cidx
            if r == "TP":
                pos.current_ci = cidx
                return px, "Hard TP", cidx

        if cidx - pos.entry_ci > _max_hold:
            pos.current_ci = cidx
            return p, "MaxHold", cidx

    pos.current_ci = max(end, pos.current_ci)
    return 0., "", -1


'''

patch("def _advance(pos, ad, to_ci, partial_cb=None):",
      RAW + "def _advance(pos, ad, to_ci, partial_cb=None):",
      "_advance_raw: inserted before _advance")

# ═══════════════════════════════════════════════════════════════
# 5. Final rebind before __main__
# ═══════════════════════════════════════════════════════════════
REBIND = '''# ═══════════════════════════════════════════════════════════════
# [730d VERIFIED] Global rebind — SL/TP/MaxHold ONLY
# ═══════════════════════════════════════════════════════════════
_advance = _advance_raw
log.info("[730d] LOCKED: SL/TP/MaxHold only | TP=0.8 | "
         "MaxHold=30/20 | Trail/Apex/BE/Partial OFF")


'''

patch('if __name__=="__main__":',
      REBIND + 'if __name__=="__main__":',
      "final rebind before __main__")

# ═══════════════════════════════════════════════════════════════
# Write + report
# ═══════════════════════════════════════════════════════════════
if s == orig:
    print("⚠  No changes applied — check anchors:", file=sys.stderr)
    for line in report:
        print("   " + line, file=sys.stderr)
    sys.exit(2)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(s)

h = hashlib.sha256(s.encode()).hexdigest()[:12]
print("═" * 72)
print(f"  ✓ {SRC} patched   sha256={h}   {len(s):,} bytes")
print("═" * 72)
for line in report:
    print("   " + line)
print("═" * 72)
print(f"   Run:  python {SRC}")
print("═" * 72)
