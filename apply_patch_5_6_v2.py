#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_patch_5_6_v2.py - تصحيح التعديلين الفاشلين (simulate_portfolio)
يعتمد على regex + fallbacks للتعامل مع:
  • em-dash (—) في التعليقات
  • الكتلة المكررة sl_h
  • trailing whitespace على السطور الفارغة
"""

import sys, os, shutil, subprocess, re
from datetime import datetime

BOT = sys.argv[1] if len(sys.argv) > 1 else "trading_2_live4_claude2_v4_mic.py"

if not os.path.exists(BOT):
    print(f"❌ Not found: {BOT}")
    sys.exit(1)

with open(BOT, 'r', encoding='utf-8') as f:
    content = f.read()
original = content

applied, skipped, failed = [], [], []


def patch_regex(name, pattern_str, repl_str, expected=1):
    global content
    if repl_str.strip() and repl_str.strip() in content and not re.search(pattern_str, content):
        skipped.append(name); print(f"  ⏭  {name}: already applied"); return
    pat = re.compile(pattern_str, re.MULTILINE)
    matches = list(pat.finditer(content))
    if len(matches) != expected:
        failed.append(f"{name} (matched {len(matches)}, expected {expected})")
        print(f"  ❌ {name}: matched {len(matches)}, expected {expected}")
        return
    content = pat.sub(repl_str, content)
    applied.append(name)
    print(f"  ✅ {name}")


# ══════════════════════════════════════════════════════════════
# PATCH 5a — Clip block: opt_px → _theoretical_px
# ══════════════════════════════════════════════════════════════
print("\n[5a/4] Clip block → sig.price (theoretical)")

patch_regex(
    "5a_clip",
    # Exact chars: × (U+00D7) in comment
    r'        # Clip SL to max_sl_frac × opt_px \(entry-based cap\)\n'
    r"        _max_sl_frac = 0\.015 \* float\(getattr\(CFG, 'SL_WIDEN_MULT', 1\.0\)\)\n"
    r'        if _design_sl_dist > opt_px \* _max_sl_frac:\n'
    r'            _rr = _design_tp_dist / max\(_design_sl_dist, 1e-12\)\n'
    r'            _design_sl_dist = opt_px \* _max_sl_frac\n'
    r'            _design_tp_dist = _design_sl_dist \* _rr',
    # replacement
    '        # Clip SL to max_sl_frac × sig.price (theoretical anchor)\n'
    '        _theoretical_px = float(sig.price)\n'
    "        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))\n"
    '        if _design_sl_dist > _theoretical_px * _max_sl_frac:\n'
    '            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)\n'
    '            _design_sl_dist = _theoretical_px * _max_sl_frac\n'
    '            _design_tp_dist = _design_sl_dist * _rr'
)


# ══════════════════════════════════════════════════════════════
# PATCH 5b — Rebuild block → keep theoretical anchor
# ══════════════════════════════════════════════════════════════
print("\n[5b/4] Rebuild block → theoretical anchor")

patch_regex(
    "5b_rebuild",
    r'        # ══ \[CRITICAL FIX\] Rebuild sig\.sl / sig\.tp1 from opt_px ══\n'
    r'        # This is what the LIVE code already does in\n'
    r'        # _promote_pending_to_position\. Without this, when\n'
    r'        # PO_FIXED_PRICE=False and entry ≠ sig\.price, TP ends up\n'
    r'        # BELOW entry \(for BUY\) → "Hard TP" exits are actually losses\.\n'
    r'        if sig\.action == "BUY":\n'
    r'            sig\.sl  = opt_px - _design_sl_dist\n'
    r'            sig\.tp1 = opt_px \+ _design_tp_dist\n'
    r'        else:\n'
    r'            sig\.sl  = opt_px \+ _design_sl_dist\n'
    r'            sig\.tp1 = opt_px - _design_tp_dist',
    (
        '        # ══ [THEORETICAL ANCHOR] SL/TP anchored to sig.price ══\n'
        '        # sig.sl/sig.tp1 from build_signals are preserved.\n'
        '        # Entry slippage does NOT shift SL/TP levels.\n'
        '        if sig.action == "BUY":\n'
        '            sig.sl  = _theoretical_px - _design_sl_dist\n'
        '            sig.tp1 = _theoretical_px + _design_tp_dist\n'
        '        else:\n'
        '            sig.sl  = _theoretical_px + _design_sl_dist\n'
        '            sig.tp1 = _theoretical_px - _design_tp_dist'
    )
)


# ══════════════════════════════════════════════════════════════
# PATCH 5c — Remove duplicate sl_h block, use sig.sl directly
# ══════════════════════════════════════════════════════════════
print("\n[5c/4] Duplicate sl_h → single sl_h = sig.sl")

patch_regex(
    "5c_sl_h_dupe",
    # Match the WHOLE block including the DUPLICATE
    r'        sl_distance = _design_sl_dist\n'
    r'        tp_distance = _design_tp_dist\n'
    r'        \n'
    r'        if sig\.action == "BUY":\n'
    r'            sl_h = opt_px - sl_distance\n'
    r'        else:\n'
    r'            sl_h = opt_px \+ sl_distance\n'
    r'        \n'
    r'        if sig\.action == "BUY":\n'
    r'            sl_h = opt_px - sl_distance\n'
    r'        else:\n'
    r'            sl_h = opt_px \+ sl_distance\n'
    r'            \n'
    r'        delta = abs\(opt_px - sl_h\)\n'
    r'        if delta < 1e-8: continue',
    (
        '        sl_distance = _design_sl_dist\n'
        '        tp_distance = _design_tp_dist\n'
        '\n'
        '        # ══ [THEORETICAL ANCHOR] SL is at sig.sl ══\n'
        '        sl_h = float(sig.sl)\n'
        '        delta = abs(opt_px - sl_h)   # actual risk: entry → theoretical SL\n'
        '        if delta < 1e-8: continue'
    )
)


# ══════════════════════════════════════════════════════════════
# PATCH 6 — Post-slippage: SL stays at sig.sl
# ══════════════════════════════════════════════════════════════
print("\n[6/4] Post-slippage → SL stays at sig.sl")

patch_regex(
    "6_post_slip",
    # Arabic comment + block; whitespace resilient
    r'        # تعديل إحداثيات الوقف بناءً على سعر الدخول الفعلي بعد انزلاق الشبكة\n'
    r'        if sig\.action == "BUY":\n'
    r'            sl_h = eff_px - sl_distance\n'
    r'        else:\n'
    r'            sl_h = eff_px \+ sl_distance\n'
    r'        \s*\n'
    r'        delta = abs\(eff_px - sl_h\)\n'
    r'        if delta < 1e-8: continue',
    (
        '        # ══ [THEORETICAL ANCHOR] SL stays at sig.sl after slippage ══\n'
        '        sl_h = float(sig.sl)\n'
        '        delta = abs(eff_px - sl_h)   # actual risk from effective entry\n'
        '        if delta < 1e-8: continue'
    )
)


# ══════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════
print("\n" + "═" * 72)
print(f"  ✅ Applied: {len(applied)}")
print(f"  ⏭  Skipped: {len(skipped)}")
print(f"  ❌ Failed : {len(failed)}")
if failed:
    print("\n  Failed items:")
    for f in failed:
        print(f"    - {f}")
    print("\n  ⚠️  لم تُطبَّق جميع التعديلات. لن أحفظ الملف.")
    print("     أرسل لي هذا الإخراج لأصنع patch مخصص لكل نمط.")
    sys.exit(1)

if content == original:
    print("\n⏸  لم يتغير شيء.")
    sys.exit(0)

# Backup + Write
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"{BOT}.backup_{ts}"
shutil.copy2(BOT, backup)
print(f"\n💾 Backup: {backup}")

with open(BOT, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"✅ Written: {BOT}")


# ══════════════════════════════════════════════════════════════
# SYNTAX VERIFICATION + AUTO-ROLLBACK
# ══════════════════════════════════════════════════════════════
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
    print(f"🔄 Rolled back from {backup}")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════
# FINAL VERIFICATION: Re-scan the file
# ══════════════════════════════════════════════════════════════
print("\n" + "═" * 72)
print("🔎 POST-PATCH VERIFICATION")
print("═" * 72)

checks = {
    "sig.sl  = _theoretical_px": "sig.sl  = _theoretical_px",
    "sig.tp1 = _theoretical_px": "sig.tp1 = _theoretical_px",
    "sl_h = float(sig.sl)":       "sl_h = float(sig.sl)",
    "_theoretical_px = float(sig.price)": "_theoretical_px = float(sig.price)",
    "THEORETICAL ANCHOR":         "THEORETICAL ANCHOR",
}
for desc, pat in checks.items():
    cnt = content.count(pat)
    status = "✅" if cnt > 0 else "❌"
    print(f"  {status} '{desc}': {cnt} occurrence(s)")

# Check old code is GONE
old_checks = {
    "Rebuild sig.sl / sig.tp1 from opt_px": "Rebuild sig.sl / sig.tp1 from opt_px",
    "sl_h = opt_px - sl_distance":           "sl_h = opt_px - sl_distance",
    "sl_h = eff_px - sl_distance":           "sl_h = eff_px - sl_distance",
}
for desc, pat in old_checks.items():
    cnt = content.count(pat)
    status = "✅" if cnt == 0 else "⚠️"
    print(f"  {status} OLD '{desc}': {cnt} occurrence(s) (want 0)")

print("\n" + "═" * 72)
print("✨ Done. Rollback: cp " + backup + " " + BOT)
print("═" * 72)
