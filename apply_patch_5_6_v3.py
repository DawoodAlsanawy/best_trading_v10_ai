#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_patch_5_6_v3.py - نسخة نهائية متسامحة مع الفراغات
يطبق 4 تعديلات (5a, 5b, 5c, 6) ويحفظ فقط إذا نجحت كلها.
"""

import sys, os, shutil, subprocess, re
from datetime import datetime

BOT = sys.argv[1] if len(sys.argv) > 1 else "trading_2_live4_claude2_v4_mic.py"

if not os.path.exists(BOT):
    print(f"❌ Not found: {BOT}"); sys.exit(1)

with open(BOT, 'r', encoding='utf-8') as f:
    content = f.read()
original = content

applied, skipped, failed = [], [], []


def patch_regex(name, pattern_str, repl_str):
    """Try regex; skip if already applied; use count=1."""
    global content
    if repl_str.strip() and repl_str.strip() in content:
        if not re.search(pattern_str, content, re.MULTILINE):
            skipped.append(name); print(f"  ⏭  {name}: already applied"); return
    pat = re.compile(pattern_str, re.MULTILINE)
    matches = list(pat.finditer(content))
    if len(matches) == 0:
        failed.append(f"{name}: 0 matches")
        print(f"  ❌ {name}: 0 matches")
        return
    if len(matches) > 1:
        failed.append(f"{name}: {len(matches)} matches (want 1)")
        print(f"  ❌ {name}: {len(matches)} matches")
        return
    content = pat.sub(repl_str, content, count=1)
    applied.append(name)
    print(f"  ✅ {name}")


# ══════════════════════════════════════════════════════════════
# PATCH 5a — Clip block
# ══════════════════════════════════════════════════════════════
print("\n[5a] Clip block → theoretical")
patch_regex(
    "5a_clip",
    r'        # Clip SL to max_sl_frac × opt_px \(entry-based cap\)\n'
    r"        _max_sl_frac = 0\.015 \* float\(getattr\(CFG, 'SL_WIDEN_MULT', 1\.0\)\)\n"
    r'        if _design_sl_dist > opt_px \* _max_sl_frac:\n'
    r'            _rr = _design_tp_dist / max\(_design_sl_dist, 1e-12\)\n'
    r'            _design_sl_dist = opt_px \* _max_sl_frac\n'
    r'            _design_tp_dist = _design_sl_dist \* _rr',
    '        # Clip SL to max_sl_frac × sig.price (theoretical anchor)\n'
    '        _theoretical_px = float(sig.price)\n'
    "        _max_sl_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))\n"
    '        if _design_sl_dist > _theoretical_px * _max_sl_frac:\n'
    '            _rr = _design_tp_dist / max(_design_sl_dist, 1e-12)\n'
    '            _design_sl_dist = _theoretical_px * _max_sl_frac\n'
    '            _design_tp_dist = _design_sl_dist * _rr'
)


# ══════════════════════════════════════════════════════════════
# PATCH 5b — Rebuild block
# ══════════════════════════════════════════════════════════════
print("\n[5b] Rebuild block → theoretical")
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


# ══════════════════════════════════════════════════════════════
# PATCH 5c — FLEXIBLE whitespace regex (FIXED)
# ══════════════════════════════════════════════════════════════
print("\n[5c] Duplicate sl_h → single (flexible whitespace)")
patch_regex(
    "5c_sl_h_dupe",
    # [ \t]*\n = any whitespace (0-N spaces/tabs) then newline
    r'        sl_distance = _design_sl_dist\n'
    r'        tp_distance = _design_tp_dist\n'
    r'[ \t]*\n'                                 # blank line 1
    r'        if sig\.action == "BUY":\n'
    r'            sl_h = opt_px - sl_distance\n'
    r'        else:\n'
    r'            sl_h = opt_px \+ sl_distance\n'
    r'[ \t]*\n'                                 # blank line 2
    r'        if sig\.action == "BUY":\n'
    r'            sl_h = opt_px - sl_distance\n'
    r'        else:\n'
    r'            sl_h = opt_px \+ sl_distance\n'
    r'[ \t]*\n'                                 # trailing blank line (12 spaces)
    r'        delta = abs\(opt_px - sl_h\)\n'
    r'        if delta < 1e-8: continue',
    '        sl_distance = _design_sl_dist\n'
    '        tp_distance = _design_tp_dist\n'
    '\n'
    '        # ══ [THEORETICAL ANCHOR] SL is at sig.sl ══\n'
    '        sl_h = float(sig.sl)\n'
    '        delta = abs(opt_px - sl_h)   # actual risk: entry → theoretical SL\n'
    '        if delta < 1e-8: continue'
)


# ══════════════════════════════════════════════════════════════
# PATCH 6 — Post-slippage
# ══════════════════════════════════════════════════════════════
print("\n[6] Post-slippage → SL stays at sig.sl")
patch_regex(
    "6_post_slip",
    r'        # تعديل إحداثيات الوقف بناءً على سعر الدخول الفعلي بعد انزلاق الشبكة\n'
    r'        if sig\.action == "BUY":\n'
    r'            sl_h = eff_px - sl_distance\n'
    r'        else:\n'
    r'            sl_h = eff_px \+ sl_distance\n'
    r'[ \t]*\n'
    r'        delta = abs\(eff_px - sl_h\)\n'
    r'        if delta < 1e-8: continue',
    '        # ══ [THEORETICAL ANCHOR] SL stays at sig.sl after slippage ══\n'
    '        sl_h = float(sig.sl)\n'
    '        delta = abs(eff_px - sl_h)   # actual risk from effective entry\n'
    '        if delta < 1e-8: continue'
)


# ══════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════
print("\n" + "═" * 72)
print(f"  ✅ Applied: {len(applied)}")
print(f"  ⏭  Skipped: {len(skipped)}")
print(f"  ❌ Failed : {len(failed)}")
if failed:
    print("\n  Failed:")
    for f in failed:
        print(f"    - {f}")
    print("\n  ⚠️  لم أحفظ الملف. أرسل هذا الإخراج.")
    sys.exit(1)

if content == original:
    print("\n⏸  لا تغيير."); sys.exit(0)

# Save
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"{BOT}.backup_{ts}"
shutil.copy2(BOT, backup)
print(f"\n💾 Backup: {backup}")

with open(BOT, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"✅ Written: {BOT}")


# ══════════════════════════════════════════════════════════════
# Syntax check
# ══════════════════════════════════════════════════════════════
print("\n⏳ Verifying syntax...")
res = subprocess.run(
    [sys.executable, "-c",
     f"import ast; ast.parse(open(r'{BOT}', encoding='utf-8').read())"],
    capture_output=True, text=True
)
if res.returncode != 0:
    print("❌ SYNTAX ERROR:")
    print(res.stderr)
    shutil.copy2(backup, BOT)
    print(f"🔄 Rolled back")
    sys.exit(1)
print("✅ Syntax OK")


# ══════════════════════════════════════════════════════════════
# Final verification
# ══════════════════════════════════════════════════════════════
print("\n" + "═" * 72)
print("🔎 POST-PATCH VERIFICATION")
print("═" * 72)

new_checks = {
    "_theoretical_px = float(sig.price)": 1,
    "sig.sl  = _theoretical_px": 2,   # in BUY and SELL branches
    "sl_h = float(sig.sl)": 2,        # pre-slippage AND post-slippage
    "THEORETICAL ANCHOR": 2,
}
old_checks = {
    "Rebuild sig.sl / sig.tp1 from opt_px": 0,
    "sl_h = opt_px - sl_distance": 0,
    "sl_h = opt_px + sl_distance": 0,
    "sl_h = eff_px - sl_distance": 0,
    "sl_h = eff_px + sl_distance": 0,
}

ok = True
print("\n  NEW markers:")
for k, want in new_checks.items():
    got = content.count(k)
    s = "✅" if got >= want else "❌"
    if got < want: ok = False
    print(f"    {s} '{k}': {got} (want ≥{want})")

print("\n  OLD markers (must be 0):")
for k, want in old_checks.items():
    got = content.count(k)
    s = "✅" if got == 0 else "⚠️"
    if got > 0: ok = False
    print(f"    {s} '{k}': {got}")

print("\n" + "═" * 72)
if ok:
    print("🎉 SUCCESS — جميع التعديلات مطبقة بشكل صحيح")
    print(f"Rollback: cp {backup} {BOT}")
else:
    print("⚠️  بعض الفحوصات فشلت — لكن الملف محفوظ")
    print("   أرسل هذا الإخراج لمراجعة الفروق")
print("═" * 72)
