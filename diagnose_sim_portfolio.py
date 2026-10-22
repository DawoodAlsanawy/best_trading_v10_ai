#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  diagnose_sim_portfolio.py                                                   ║
║                                                                              ║
║  يشخّص لماذا فشل PATCH 5 و 6:                                                ║
║    • يعرض محتوى دالة simulate_portfolio كما هو فعلياً في الملف               ║
║    • يُظهر رقم السطر + repr() لكشف المسافات/tabs                             ║
║    • يبحث عن العلامات الحرجة: _design_sl_dist, opt_px, sl_h, delta...       ║
║    • يقارن مع النص المتوقع ويشرح الفرق                                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import re

BOT = sys.argv[1] if len(sys.argv) > 1 else "trading_2_live4_claude2_v4_mic.py"

if not os.path.exists(BOT):
    print(f"❌ File not found: {BOT}")
    sys.exit(1)

with open(BOT, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("═" * 78)
print(f"🔍 Diagnosing: {BOT}")
print(f"   Total lines: {len(lines)}")
print("═" * 78)


# ═════════════════════════════════════════════════════════════
# 1. Locate simulate_portfolio function
# ═════════════════════════════════════════════════════════════
func_start = None
func_name = None
for i, ln in enumerate(lines):
    m = re.match(r'^def (simulate_portfolio)\s*\(', ln)
    if m:
        func_start = i
        func_name = m.group(1)
        break

if func_start is None:
    print("❌ simulate_portfolio NOT FOUND")
    sys.exit(1)

# Find function end (next top-level def at column 0)
func_end = len(lines)
for i in range(func_start + 1, len(lines)):
    if re.match(r'^def \w+\s*\(', lines[i]) or re.match(r'^class \w+', lines[i]):
        func_end = i
        break

print(f"\n✓ Found '{func_name}' at line {func_start + 1}, ends at line {func_end}")
print(f"   Length: {func_end - func_start} lines")


# ═════════════════════════════════════════════════════════════
# 2. Search for critical markers
# ═════════════════════════════════════════════════════════════
markers = [
    "SL/TP SETUP",
    "_design_sl_dist",
    "_design_tp_dist",
    "opt_px * _max_sl_frac",
    "Rebuild sig.sl",
    "CRITICAL FIX",
    "sl_h = opt_px",
    "sl_h = eff_px",
    "sl_h = float(sig.sl)",
    "delta = abs(opt_px",
    "delta = abs(eff_px",
    "delta = abs(sig",
    "sig.sl  = opt_px",
    "sig.tp1 = opt_px",
    "sig.sl  = _theoretical_px",
    "sl_distance = _design_sl_dist",
    "sl_distance = abs(opt_px",
    "sl_distance = abs(sig",
    "eff_px - sl_distance",
    "eff_px + sl_distance",
    "THEORETICAL ANCHOR",
]

print("\n" + "─" * 78)
print("📊 Marker scan inside simulate_portfolio")
print("─" * 78)

found_markers = {}
for marker in markers:
    hits = []
    for i in range(func_start, func_end):
        if marker in lines[i]:
            hits.append(i + 1)  # 1-based line numbers
    if hits:
        found_markers[marker] = hits
        print(f"  ✅ line(s) {hits}: {marker!r}")
    else:
        print(f"  ❌ NOT FOUND: {marker!r}")


# ═════════════════════════════════════════════════════════════
# 3. Auto-locate the SL/TP setup block by keyword
# ═════════════════════════════════════════════════════════════
print("\n" + "─" * 78)
print("🎯 Auto-located SL/TP setup region")
print("─" * 78)

# Find the line with _design_sl_dist assignment (the anchor)
anchor_line = None
for i in range(func_start, func_end):
    if re.search(r'_design_sl_dist\s*=\s*abs\(sig\.price\s*-\s*sig\.sl\)', lines[i]):
        anchor_line = i
        break

if anchor_line is None:
    # Try the alternative pattern
    for i in range(func_start, func_end):
        if "_design_sl_dist" in lines[i] and "=" in lines[i] and "abs" in lines[i]:
            anchor_line = i
            break

if anchor_line is None:
    print("  ❌ Cannot auto-locate _design_sl_dist assignment")
    print("  → The code structure may differ significantly.")
    print("\n  Print full function for manual inspection:")
    print("─" * 78)
    for i in range(func_start, func_end):
        ln = lines[i]
        print(f"{i+1:5d}: {ln.rstrip()}")
    sys.exit(0)

print(f"  Anchor at line {anchor_line + 1}")
print(f"\n  Context (±30 lines):")
print("─" * 78)

start_ctx = max(func_start, anchor_line - 30)
end_ctx = min(func_end, anchor_line + 50)

for i in range(start_ctx, end_ctx):
    ln = lines[i]
    num = i + 1
    # Highlight indentation issues
    stripped = ln.rstrip('\n')
    # Show whitespace visible: tabs as ␉, trailing spaces as ·
    visible = stripped.replace('\t', '␉').replace(' ', '·')
    marker = "→" if i == anchor_line else " "
    print(f"{num:5d}{marker}|{visible}")


# ═════════════════════════════════════════════════════════════
# 4. Show EXACT repr of the critical lines
# ═════════════════════════════════════════════════════════════
print("\n" + "─" * 78)
print("🔬 Exact repr() of critical lines (to reveal whitespace)")
print("─" * 78)

critical_lines = []
for i in range(max(func_start, anchor_line - 5), min(func_end, anchor_line + 40)):
    if any(kw in lines[i] for kw in [
        "_design_sl_dist", "_design_tp_dist", "opt_px",
        "sl_h", "delta", "sl_distance", "sig.sl", "sig.tp1",
        "_max_sl_frac", "_rr",
    ]):
        critical_lines.append(i)

if not critical_lines:
    print("  ❌ No critical lines found in the region")
else:
    for i in critical_lines[:30]:
        print(f"\n  Line {i+1}:")
        print(f"    repr: {lines[i]!r}")


# ═════════════════════════════════════════════════════════════
# 5. Check for previous partial patches
# ═════════════════════════════════════════════════════════════
print("\n" + "─" * 78)
print("🔎 Partial-patch indicators")
print("─" * 78)

indicators = {
    "THEORETICAL ANCHOR marker": "THEORETICAL ANCHOR",
    "_theoretical_px variable": "_theoretical_px",
    "sl_h = float(sig.sl)": "sl_h = float(sig.sl)",
    "sig.sl  = _theoretical_px": "sig.sl  = _theoretical_px",
    "actual risk comment": "actual risk",
    "theoretical (signal) price clip": "theoretical (signal) price",
}

for desc, pattern in indicators.items():
    count = sum(1 for i in range(func_start, func_end) if pattern in lines[i])
    status = "✅" if count > 0 else "❌"
    print(f"  {status} {desc}: {count} occurrence(s)")


# ═════════════════════════════════════════════════════════════
# 6. Check file-wide for unexpected context (indentation)
# ═════════════════════════════════════════════════════════════
print("\n" + "─" * 78)
print("📐 Indentation profile (most common prefixes)")
print("─" * 78)

indent_counts = {}
for i in range(func_start, func_end):
    ln = lines[i]
    if not ln.strip():
        continue
    # Count leading whitespace
    m = re.match(r'^(\s+)', ln)
    if m:
        prefix = m.group(1)
        indent_counts[prefix] = indent_counts.get(prefix, 0) + 1

for prefix, cnt in sorted(indent_counts.items(), key=lambda x: -x[1])[:10]:
    visible = prefix.replace('\t', '␉').replace(' ', '·')
    print(f"  {cnt:4d}× {visible!r}")


# ═════════════════════════════════════════════════════════════
# 7. Suggest next action
# ═════════════════════════════════════════════════════════════
print("\n" + "═" * 78)
print("💡 توصية")
print("═" * 78)

has_theoretical = any("THEORETICAL ANCHOR" in lines[i] or "_theoretical_px" in lines[i]
                       for i in range(func_start, func_end))
has_old_rebuild = any("Rebuild sig.sl" in lines[i] or "opt_px - _design_sl_dist" in lines[i]
                       for i in range(func_start, func_end))

if has_theoretical:
    print("  ✅ الملف يبدو أنه طُبّق عليه PATCH 5 أو تعديل مشابه مسبقاً.")
    print("     → ابحث عن '_theoretical_px' داخل simulate_portfolio للتأكد.")
elif has_old_rebuild:
    print("  ⚠️  ما زال يحتوي الكود القديم (Rebuild من opt_px).")
    print("     → الفشل بسبب اختلاف في المسافات أو التعليقات.")
    print("     → أرسل مخرجات هذا السكريبت كاملة، وسأصنع patch مخصص.")
else:
    print("  ❓ لم أجد أي من النسختين (القديمة أو الجديدة) في المنطقة المتوقعة.")
    print("     → ربما تم نقل الكود أو إعادة تسمية متغيرات.")
    print("     → أرسل المخرجات كاملة.")


# ═════════════════════════════════════════════════════════════
# 8. Print FULL function body (compressed) for pattern matching
# ═════════════════════════════════════════════════════════════
print("\n" + "═" * 78)
print("📄 FULL BODY of simulate_portfolio (for precise matching)")
print("═" * 78)
print("(This is what I need to see to write the exact patch)")

for i in range(func_start, func_end):
    print(f"{i+1:5d}|{lines[i].rstrip()}")

print("\n" + "═" * 78)
print("✅ Diagnostics complete. Send the ENTIRE output above.")
print("═" * 78)
