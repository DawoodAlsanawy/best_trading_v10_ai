#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_patch_failures_v2.py
==============================
Fixed version of the diagnostic tool.

Bug fix: replaced fake-match lambdas with simple (start, end) tuples.
Added: per-section try/except so one failure doesn't kill everything.

Usage:
    python3 diagnose_patch_failures_v2.py --file trading_2_live4_claude2_v4_micro.py
    python3 diagnose_patch_failures_v2.py --file trading_2_live4_claude2_v4_micro.py --verbose
"""

import argparse
import os
import re
import sys
import traceback


DEFAULT_FILE = "trading_2_live4_claude2_v4_micro.py"


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════
def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def find_all_matches(text, pattern, label, max_show=5):
    """Find all occurrences of pattern (plain string). Print context. Return count."""
    print(f"\n  ── {label} ──")

    positions = []
    start = 0
    while True:
        idx = text.find(pattern, start)
        if idx < 0:
            break
        positions.append(idx)
        start = idx + len(pattern)

    if not positions:
        print(f"    ❌ NOT FOUND")
        return 0

    print(f"    ✅ Found {len(positions)} match(es)")

    for i, pos in enumerate(positions[:max_show]):
        line_no = text[:pos].count('\n') + 1
        end_pos = pos + min(len(pattern), 120)
        snippet = text[pos:end_pos].replace('\n', '\\n')
        print(f"    [{i+1}] line {line_no}: {snippet}")

    if len(positions) > max_show:
        print(f"    ... and {len(positions) - max_show} more")
    return len(positions)


def print_context_around(text, needle, before=3, after=3, label=""):
    """Print context lines around first occurrence of needle."""
    idx = text.find(needle)
    if idx < 0:
        print(f"  ❌ '{needle[:60]}' NOT FOUND")
        return False

    lines = text.split('\n')
    line_no = text[:idx].count('\n')
    start = max(0, line_no - before)
    end = min(len(lines), line_no + after + 1)

    if label:
        print(f"\n  ── {label} (line {line_no + 1}) ──")
    else:
        print(f"\n  ── Context around line {line_no + 1} ──")
    for i in range(start, end):
        marker = ">>>" if i == line_no else "   "
        content = lines[i][:140]
        print(f"  {marker} {i+1:5d}: {content}")
    return True


def fuzzy_search(text, keywords, max_results=10):
    """Search for lines containing ALL keywords (case-insensitive)."""
    results = []
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if all(kw.lower() in line.lower() for kw in keywords):
            results.append((i + 1, line[:150]))
            if len(results) >= max_results:
                break
    return results


def print_fuzzy(text, keywords, label, max_results=10):
    print(f"\n  ── Fuzzy: {label} ──")
    print(f"  keywords: {keywords}")
    results = fuzzy_search(text, keywords, max_results)
    if not results:
        print(f"    ❌ No lines contain ALL keywords")
        return
    for line_no, content in results:
        print(f"    L{line_no:5d}: {content}")


def find_block_extent(text, start_marker, max_lines=200):
    """Find start_marker, return (start_idx, end_line_no, end_marker, preview)."""
    idx = text.find(start_marker)
    if idx < 0:
        return None, None, None, []

    lines = text.split('\n')
    start_line_no = text[:idx].count('\n')
    end_line_no = min(len(lines), start_line_no + max_lines)
    preview = lines[start_line_no:end_line_no]

    end_markers = [
        "                ex = False",
        "            ex = False",
        "        ex = False",
        "    ex = False",
        "ex = False",
    ]
    for marker in end_markers:
        for j in range(start_line_no + 1, end_line_no):
            if lines[j].startswith(marker.rstrip()):
                return idx, j, marker, preview[:j - start_line_no + 1]

    return idx, end_line_no, None, preview


def print_extended_context(text, marker, before=5, after=40):
    idx = text.find(marker)
    if idx < 0:
        print(f"  ❌ '{marker}' NOT FOUND")
        return
    lines = text.split('\n')
    line_no = text[:idx].count('\n')
    start = max(0, line_no - before)
    end = min(len(lines), line_no + after + 1)
    for i in range(start, end):
        marker_sym = ">>>" if i == line_no else "   "
        print(f"  {marker_sym} {i+1:5d}: {lines[i][:150]}")


# ══════════════════════════════════════════════════════════════
# Diagnostic sections
# ══════════════════════════════════════════════════════════════
def diagnose_p1_config(text):
    print("\n" + "=" * 74)
    print("  P1 — Config (BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY)")
    print("=" * 74)

    if "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False" in text:
        print("\n  ✅ Already applied")
        print_context_around(text, "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY", 2, 2)
        return

    print("\n  ⏳ Not yet applied (expected since --dry-run)")
    find_all_matches(
        text, "BREAKEVEN_ESCAPE_CANCEL_KAPPA: float =",
        "Anchor: BREAKEVEN_ESCAPE_CANCEL_KAPPA Config line"
    )
    print_context_around(
        text, "BREAKEVEN_ESCAPE_CANCEL_KAPPA", 2, 6,
        "Config area"
    )


def diagnose_p2_backtest(text):
    print("\n" + "=" * 74)
    print("  P2 — Backtest BEEsc-Cancel block")
    print("=" * 74)

    if "mode={'close' if _be_use_close else 'wick'}" in text:
        print("\n  ✅ Already applied")
        return

    print("\n  ⏳ Not yet applied")
    find_all_matches(
        text, "# ══ [BEEsc-CANCEL] track extremes + cancel on strong bounce ══",
        "Block start marker"
    )
    find_all_matches(
        text, "# ── Determine sub-bar iteration range for this bar ──",
        "Block end marker"
    )

    marker = "# ══ [BEEsc-CANCEL] track extremes + cancel on strong bounce ══"
    start_idx, end_line, end_marker, preview = find_block_extent(text, marker)
    if start_idx is not None:
        print(f"\n  Block extent: end_marker = {end_marker!r}")
        print(f"  First 3 lines:")
        for line in preview[:3]:
            print(f"    {line[:140]}")
        print(f"  Last 3 lines:")
        for line in preview[-3:]:
            print(f"    {line[:140]}")

    print_fuzzy(text, ["BEEsc-CANCEL", "backtest"],
                "Alternative backtest block markers")
    print_fuzzy(text, ["_be_cancelled", "pos._be_orig_tp1"],
                "Where BEEsc cancel logic lives (backtest)")


def diagnose_p3_live(text):
    print("\n" + "=" * 74)
    print("  P3 — Live BEEsc-Cancel block  ⚠ REPORTED AS FAILED")
    print("=" * 74)

    if "mode={'close' if _be_use_close else 'ticker'}" in text:
        print("\n  ✅ Already applied")
        return

    print("\n  ⏳ Not yet applied")

    expected_marker = "# ══ [BEEsc-Cancel-Live] track extremes + cancel ══"
    count = find_all_matches(text, expected_marker, "Expected marker (exact)")

    if count == 0:
        print("\n  ⚠ Expected marker NOT FOUND. Searching alternatives...")
        print_fuzzy(text, ["BEEsc-Cancel-Live"], "Anything with 'BEEsc-Cancel-Live'")
        print_fuzzy(text, ["BEEsc-CANCEL"], "Anything with 'BEEsc-CANCEL' (uppercase)")
        print_fuzzy(text, ["BEEsc", "cancel", "track"],
                    "Lines with BEEsc + cancel + track")
        print_fuzzy(text, ["_be_orig_tp1", "pos"],
                    "Where BEEsc cancel logic lives (live, pos['_be_orig_tp1'])")
        print_fuzzy(text, ["_be_cancelled", "pos"],
                    "Where _be_cancelled is set on pos dict")

    print("\n  ── 'ex = False' occurrences (candidate end markers) ──")
    lines = text.split('\n')
    found_ex = False
    for i, line in enumerate(lines):
        if 'ex = False' in line:
            found_ex = True
            indent = len(line) - len(line.lstrip())
            print(f"    L{i+1:5d} (indent={indent:2d}): {line[:100]}")
    if not found_ex:
        print("    ❌ 'ex = False' NOT FOUND anywhere")

    print_fuzzy(text, ["_be_esc_done", "pos.get"],
                "Live BEEsc armed check (pos.get('_be_esc_done'))")

    if count > 0:
        print_context_around(text, expected_marker, 5, 30,
                              "Expected block context")


def diagnose_p4_args(text):
    print("\n" + "=" * 74)
    print("  P4 — CLI args (--be-cancel-close-only)  ⚠ REPORTED AS FAILED")
    print("=" * 74)

    if "--be-cancel-close-only" in text:
        print("\n  ✅ Already applied")
        return

    print("\n  ⏳ Not yet applied")

    expected = '    p.add_argument("--be-escape-cancel-kappa", type=float, default=None,\n'
    find_all_matches(text, expected, "Expected anchor (exact)")

    print_fuzzy(text, ["be-escape-cancel-kappa"],
                "All lines with 'be-escape-cancel-kappa'")

    print_fuzzy(text, ["add_argument", "be-escape"],
                "All add_argument with be-escape")

    idx = text.find('"--be-escape-cancel-kappa"')
    if idx >= 0:
        print_context_around(text, '"--be-escape-cancel-kappa"', 2, 8,
                              "Actual --be-escape-cancel-kappa arg context")
    else:
        print("\n  ❌ '\"--be-escape-cancel-kappa\"' (with quotes) NOT FOUND")


def diagnose_p5_wiring(text):
    print("\n" + "=" * 74)
    print("  P5 — CLI wiring  ⚠ REPORTED AS FAILED")
    print("=" * 74)

    if "CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True" in text:
        print("\n  ✅ Already applied")
        return

    print("\n  ⏳ Not yet applied")

    expected = (
        '    if getattr(args, "be_escape_cancel_kappa", None) is not None:\n'
        '        CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA = float(\n'
        '            args.be_escape_cancel_kappa)\n'
        '        if CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA > 0:\n'
    )
    find_all_matches(text, expected, "Expected anchor (exact)")

    print_fuzzy(text, ["be_escape_cancel_kappa"],
                "All lines with 'be_escape_cancel_kappa'")

    print_fuzzy(text, ["BREAKEVEN_ESCAPE_CANCEL_KAPPA", "=", "float"],
                "Where BREAKEVEN_ESCAPE_CANCEL_KAPPA is assigned")

    idx = text.find('be_escape_cancel_kappa')
    if idx >= 0:
        print_context_around(text, "be_escape_cancel_kappa", 3, 15,
                              "Actual be_escape_cancel_kappa context")


def diagnose_overall_state(text):
    print("\n" + "=" * 74)
    print("  Overall state of BEEsc / be-escape / be-cancel features")
    print("=" * 74)

    checks = [
        ("BEEsc base (BREAKEVEN_ESCAPE_ENABLED)", "BREAKEVEN_ESCAPE_ENABLED: bool"),
        ("BEEsc move-r", "BREAKEVEN_ESCAPE_PRICE_MOVE_R"),
        ("BEEsc cancel kappa", "BREAKEVEN_ESCAPE_CANCEL_KAPPA"),
        ("BEEsc cancel close-only", "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY"),
        ("BEEsc cancel sr-check", "BREAKEVEN_ESCAPE_CANCEL_SR_CHECK"),
        ("BEEsc trigger func", "def _should_breakeven_escape"),
        ("BEEsc apply func", "def _apply_breakeven_escape"),
        ("BEEsc find swing", "def _find_recent_swing"),
        ("Live BEEsc-Cancel code", "pos.get('_be_esc_done'"),
        ("Live BEEsc-Cancel set", "pos['_be_cancelled'] = True"),
        ("BT BEEsc-Cancel set", "pos._be_cancelled = True"),
    ]

    print("\n  Feature presence check:")
    for label, pattern in checks:
        count = text.count(pattern)
        mark = "✅" if count > 0 else "❌"
        print(f"    {mark} {label:42s}: {count} occurrence(s)")

    print("\n  Log message markers:")
    log_markers = [
        "[BEEsc]", "[BEEsc-BT]", "[BEEsc-BT-Sig]",
        "[BEEsc-LV]", "[BEEsc-LV-Sig]",
        "[BEEsc-Cancel-BT]", "[BEEsc-Cancel-LV]", "[BEEsc-Cancel-SR]",
    ]
    for marker in log_markers:
        count = text.count(marker)
        mark = "✅" if count > 0 else "❌"
        print(f"    {mark} {marker:22s}: {count}")


def suggest_fixes(text):
    print("\n" + "=" * 74)
    print("  🔧 Suggestions")
    print("=" * 74)

    if "mode={'close' if _be_use_close else 'ticker'}" not in text:
        if "# ══ [BEEsc-Cancel-Live]" in text:
            print("\n  P3 — Live block:")
            print("    ✅ Marker '# ══ [BEEsc-Cancel-Live]' exists")
            print("    → Regex might fail due to whitespace or line endings.")
        elif "BEEsc-Cancel-Live" in text:
            print("\n  P3 — Live block:")
            print("    ⚠ 'BEEsc-Cancel-Live' exists but not as start marker.")
            print("    → Find exact line with: grep -n 'BEEsc-Cancel-Live'")
        else:
            print("\n  P3 — Live block:")
            print("    ❌ 'BEEsc-Cancel-Live' does NOT exist at all.")
            print("    → Live BEEsc-Cancel code was never added.")
            print("    → Need to apply apply_bee_cancel_patch.py first.")

    if "--be-cancel-close-only" not in text:
        if 'be-escape-cancel-kappa' in text:
            print("\n  P4 — CLI args:")
            print("    ✅ 'be-escape-cancel-kappa' exists")
            print("    → Exact help text differs. Fuzzy match needed.")
        else:
            print("\n  P4 — CLI args:")
            print("    ❌ 'be-escape-cancel-kappa' NOT found")

    if "CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True" not in text:
        if 'be_escape_cancel_kappa' in text:
            print("\n  P5 — Wiring:")
            print("    ✅ 'be_escape_cancel_kappa' exists")
            print("    → Exact block differs. Fuzzy match needed.")
        else:
            print("\n  P5 — Wiring:")
            print("    ❌ 'be_escape_cancel_kappa' NOT found")


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════
def safe_run(label, func, *args, **kwargs):
    """Run a diagnostic section; catch exceptions so others still run."""
    try:
        func(*args, **kwargs)
    except Exception as e:
        print(f"\n  ⚠ SECTION FAILED: {label}: {type(e).__name__}: {e}")
        print(f"  Traceback:")
        for line in traceback.format_exc().split('\n')[:6]:
            print(f"    {line}")


def main():
    ap = argparse.ArgumentParser(
        description="Diagnose apply_bee_cancel_close_parity.py failures.")
    ap.add_argument("--file", default=DEFAULT_FILE,
                    help=f"File to analyze (default: {DEFAULT_FILE})")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="Print extended context blocks")
    args = ap.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: file not found: {args.file}")
        sys.exit(1)

    print("=" * 74)
    print(f"  DIAGNOSTIC REPORT — {args.file}")
    print("=" * 74)
    print(f"\n  File size: {os.path.getsize(args.file):,} bytes")

    text = read_file(args.file)
    print(f"  Total lines: {len(text.split(chr(10))):,}")

    # Each section is wrapped in try/except so one failure doesn't stop others
    safe_run("P1_CONFIG", diagnose_p1_config, text)
    safe_run("P2_BT", diagnose_p2_backtest, text)
    safe_run("P3_LV", diagnose_p3_live, text)
    safe_run("P4_ARGS", diagnose_p4_args, text)
    safe_run("P5_WIRE", diagnose_p5_wiring, text)
    safe_run("OVERALL", diagnose_overall_state, text)
    safe_run("SUGGEST", suggest_fixes, text)

    if args.verbose:
        print("\n" + "=" * 74)
        print("  Extended contexts (--verbose)")
        print("=" * 74)

        print("\n  ── First 'BEEsc-Cancel' occurrence (extended) ──")
        safe_run("EXT1", print_extended_context, text,
                 "BEEsc-Cancel", before=2, after=40)

        print("\n  ── First 'be-escape-cancel-kappa' occurrence (extended) ──")
        safe_run("EXT2", print_extended_context, text,
                 "be-escape-cancel-kappa", before=2, after=10)

        print("\n  ── First 'be_escape_cancel_kappa' occurrence (extended) ──")
        safe_run("EXT3", print_extended_context, text,
                 "be_escape_cancel_kappa", before=2, after=20)

    # Final summary
    print("\n" + "=" * 74)
    print("  SUMMARY")
    print("=" * 74)

    p1_ok = "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False" in text
    p2_ok = "mode={'close' if _be_use_close else 'wick'}" in text
    p3_ok = "mode={'close' if _be_use_close else 'ticker'}" in text
    p4_ok = "--be-cancel-close-only" in text
    p5_ok = "CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True" in text

    print(f"\n  P1_CONFIG : {'✅ applied' if p1_ok else '⏳ not applied'}")
    print(f"  P2_BT     : {'✅ applied' if p2_ok else '⏳ not applied'}")
    print(f"  P3_LV     : {'✅ applied' if p3_ok else '❌ FAILED'}")
    print(f"  P4_ARGS   : {'✅ applied' if p4_ok else '❌ FAILED'}")
    print(f"  P5_WIRE   : {'✅ applied' if p5_ok else '❌ FAILED'}")

    print(f"\n  📋 Next steps:")
    if p3_ok and p4_ok and p5_ok:
        print("     ✅ All patches applied. Test A/B/C.")
    else:
        print("     1. Copy this entire output and share it.")
        print("     2. A corrected patch will be generated based on this.")
        print("     3. No files were modified (read-only diagnostic).")


if __name__ == "__main__":
    main()
