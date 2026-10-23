#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_patch_failures.py
==========================
Diagnostic tool for apply_bee_cancel_close_parity.py failures.

Analyzes the file and reports:
  1. What's actually present around key anchors
  2. Line numbers and exact text
  3. Similar patterns found (fuzzy search)
  4. The state of BEEsc / be-escape / be-cancel related code
  5. Suggestions for correct anchors

Usage:
    python3 diagnose_patch_failures.py --file trading_2_live4_claude2_v4_micro.py

No writes to the file. Read-only.
"""

import argparse
import os
import re
import sys


DEFAULT_FILE = "trading_2_live4_claude2_v4_micro.py"


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════
def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def find_all_matches(text, pattern, label, is_regex=False):
    """Find all occurrences of pattern. Print context. Return count."""
    print(f"\n  ── {label} ──")
    if is_regex:
        try:
            matches = list(re.finditer(pattern, text))
        except re.error as e:
            print(f"    REGEX ERROR: {e}")
            return 0
    else:
        matches = []
        start = 0
        while True:
            idx = text.find(pattern, start)
            if idx < 0:
                break
            matches.append(type('M', (), {'start': lambda i=idx: i,
                                           'end': lambda i=idx+len(pattern): i+len(pattern)})())
            start = idx + len(pattern)

    if not matches:
        print(f"    ❌ NOT FOUND")
        return 0

    print(f"    ✅ Found {len(matches)} match(es)")

    # For each match, print line number and short preview
    lines = text.split('\n')
    for i, m in enumerate(matches[:5]):  # limit to first 5
        line_no = text[:m.start()].count('\n') + 1
        snippet = text[m.start():m.end()][:120].replace('\n', '\\n')
        print(f"    [{i+1}] line {line_no}: {snippet}...")

    if len(matches) > 5:
        print(f"    ... and {len(matches) - 5} more")
    return len(matches)


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
        line_content = lines[i][:140]
        print(f"  {marker} {i+1:5d}: {line_content}")
    return True


def fuzzy_search(text, keywords, max_results=10):
    """
    Search for lines containing ALL keywords (case-insensitive).
    Returns list of (line_no, line_content).
    """
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
    """
    Find start_marker, then find natural end of block.
    Returns (start_idx, end_idx, end_marker_found, preview_lines).
    """
    idx = text.find(start_marker)
    if idx < 0:
        return None, None, None, []

    lines = text.split('\n')
    start_line_no = text[:idx].count('\n')

    # Extract up to max_lines
    end_line_no = min(len(lines), start_line_no + max_lines)
    preview = lines[start_line_no:end_line_no]

    # Find natural end markers
    end_markers = [
        "                ex = False",
        "            ex = False",
        "        ex = False",
        "    ex = False",
        "ex = False",
        "                if not ex:",
        "            if not ex:",
        "                # ──",
        "            # ──",
    ]
    for marker in end_markers:
        for j in range(start_line_no + 1, end_line_no):
            if lines[j].startswith(marker.rstrip()):
                return idx, j, marker, preview[:j - start_line_no + 1]

    return idx, end_line_no, None, preview


# ══════════════════════════════════════════════════════════════
# Diagnostic sections
# ══════════════════════════════════════════════════════════════
def diagnose_p1_config(text):
    """Check P1 anchors and applied state."""
    print("\n" + "=" * 74)
    print("  P1 — Config (BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY)")
    print("=" * 74)

    if "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY: bool = False" in text:
        print("\n  ✅ Already applied")
        print_context_around(
            text, "BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY", 2, 2
        )
    else:
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
    """Check P2 backtest block."""
    print("\n" + "=" * 74)
    print("  P2 — Backtest BEEsc-Cancel block")
    print("=" * 74)

    # Check if already applied
    if "mode={'close' if _be_use_close else 'wick'}" in text:
        print("\n  ✅ Already applied")
        return

    print("\n  ⏳ Not yet applied")

    # Look for block markers
    find_all_matches(
        text, "# ══ [BEEsc-CANCEL] track extremes + cancel on strong bounce ══",
        "Block start marker"
    )
    find_all_matches(
        text, "# ── Determine sub-bar iteration range for this bar ──",
        "Block end marker"
    )

    # Show extent
    marker = "# ══ [BEEsc-CANCEL] track extremes + cancel on strong bounce ══"
    start_idx, end_idx, end_marker, preview = find_block_extent(text, marker)
    if start_idx is not None:
        print(f"\n  Block extent: found end_marker = {end_marker!r}")
        print(f"  First 5 lines:")
        for line in preview[:5]:
            print(f"    {line[:140]}")
        print(f"  Last 5 lines of block:")
        for line in preview[-5:]:
            print(f"    {line[:140]}")

    # Fuzzy search for variations
    print_fuzzy(text, ["BEEsc-CANCEL", "backtest"],
                "Alternative backtest block markers")
    print_fuzzy(text, ["_be_cancelled", "pos._be_orig_tp1"],
                "Where BEEsc cancel logic lives (backtest)")


def diagnose_p3_live(text):
    """Check P3 live block — the key failure."""
    print("\n" + "=" * 74)
    print("  P3 — Live BEEsc-Cancel block  ⚠ REPORTED AS FAILED")
    print("=" * 74)

    # Check if already applied
    if "mode={'close' if _be_use_close else 'ticker'}" in text:
        print("\n  ✅ Already applied")
        return

    print("\n  ⏳ Not yet applied")
    print("\n  Expected regex start marker:")
    print("    '                # ══ [BEEsc-Cancel-Live] track extremes + cancel ══'")
    print("  Expected regex end marker:")
    print("    '                ex = False'")

    # Search for the expected marker (exact)
    expected_marker = "# ══ [BEEsc-Cancel-Live] track extremes + cancel ══"
    count = find_all_matches(text, expected_marker, "Expected marker (exact)")

    if count == 0:
        print("\n  ⚠ Expected marker NOT FOUND. Searching alternatives...")
        print_fuzzy(text, ["BEEsc-Cancel-Live"],
                    "Anything with 'BEEsc-Cancel-Live'")
        print_fuzzy(text, ["BEEsc-CANCEL"],
                    "Anything with 'BEEsc-CANCEL' (uppercase)")
        print_fuzzy(text, ["BEEsc", "cancel", "track"],
                    "Lines with BEEsc + cancel + track")
        print_fuzzy(text, ["_be_orig_tp1", "pos"],
                    "Where BEEsc cancel logic lives (live, pos['_be_orig_tp1'])")
        print_fuzzy(text, ["_be_cancelled", "pos"],
                    "Where _be_cancelled is set on pos dict")

    # Find "ex = False" occurrences and their context
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

    # Find the pos.get('_be_esc_done') block
    print_fuzzy(text, ["_be_esc_done", "pos.get"],
                "Live BEEsc armed check (pos.get('_be_esc_done'))")

    # Show context around BEEsc live logic
    if count > 0:
        print_context_around(text, expected_marker, 5, 30,
                              "Expected block context")


def diagnose_p4_args(text):
    """Check P4 CLI args."""
    print("\n" + "=" * 74)
    print("  P4 — CLI args (--be-cancel-close-only)  ⚠ REPORTED AS FAILED")
    print("=" * 74)

    if "--be-cancel-close-only" in text:
        print("\n  ✅ Already applied")
        return

    print("\n  ⏳ Not yet applied")

    # Look for --be-escape-cancel-kappa argument
    print("\n  Searching for --be-escape-cancel-kappa argument...")
    expected = '    p.add_argument("--be-escape-cancel-kappa", type=float, default=None,\n'
    find_all_matches(text, expected, "Expected anchor (exact)")

    # Fuzzy: find all lines with --be-escape-cancel-kappa
    print_fuzzy(text, ["be-escape-cancel-kappa"],
                "All lines with 'be-escape-cancel-kappa'")

    # Find all p.add_argument("--be-escape
    print_fuzzy(text, ["add_argument", "be-escape"],
                "All add_argument with be-escape")

    # Show context around the actual add_argument
    idx = text.find('"--be-escape-cancel-kappa"')
    if idx >= 0:
        print_context_around(text, '"--be-escape-cancel-kappa"', 2, 8,
                              "Actual --be-escape-cancel-kappa arg context")
    else:
        print("\n  ❌ '\"--be-escape-cancel-kappa\"' (with quotes) NOT FOUND")


def diagnose_p5_wiring(text):
    """Check P5 CLI wiring."""
    print("\n" + "=" * 74)
    print("  P5 — CLI wiring  ⚠ REPORTED AS FAILED")
    print("=" * 74)

    if "CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True" in text:
        print("\n  ✅ Already applied")
        return

    print("\n  ⏳ Not yet applied")

    # Look for the expected anchor
    expected = (
        '    if getattr(args, "be_escape_cancel_kappa", None) is not None:\n'
        '        CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA = float(\n'
        '            args.be_escape_cancel_kappa)\n'
        '        if CFG.BREAKEVEN_ESCAPE_CANCEL_KAPPA > 0:\n'
    )
    find_all_matches(text, expected, "Expected anchor (exact)")

    # Fuzzy: all lines with be_escape_cancel_kappa
    print_fuzzy(text, ["be_escape_cancel_kappa"],
                "All lines with 'be_escape_cancel_kappa'")

    # Fuzzy: where BREAKEVEN_ESCAPE_CANCEL_KAPPA is set
    print_fuzzy(text, ["BREAKEVEN_ESCAPE_CANCEL_KAPPA", "=", "float"],
                "Where BREAKEVEN_ESCAPE_CANCEL_KAPPA is assigned")

    # Show context around first be_escape_cancel_kappa
    idx = text.find('be_escape_cancel_kappa')
    if idx >= 0:
        print_context_around(text, "be_escape_cancel_kappa", 3, 15,
                              "Actual be_escape_cancel_kappa context")


def diagnose_overall_state(text):
    """Print overall state of related features."""
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

    # Count BEEsc-related log lines
    print("\n  Log message markers:")
    log_markers = [
        "[BEEsc]",
        "[BEEsc-BT]",
        "[BEEsc-BT-Sig]",
        "[BEEsc-LV]",
        "[BEEsc-LV-Sig]",
        "[BEEsc-Cancel-BT]",
        "[BEEsc-Cancel-LV]",
        "[BEEsc-Cancel-SR]",
    ]
    for marker in log_markers:
        count = text.count(marker)
        mark = "✅" if count > 0 else "❌"
        print(f"    {mark} {marker:22s}: {count}")


def suggest_fixes(text):
    """Suggest specific fixes for P3/P4/P5 based on what's found."""
    print("\n" + "=" * 74)
    print("  🔧 Suggestions")
    print("=" * 74)

    # P3 suggestion
    if "mode={'close' if _be_use_close else 'ticker'}" not in text:
        if "# ══ [BEEsc-Cancel-Live]" in text:
            print("\n  P3 — Live block:")
            print("    ✅ Marker '# ══ [BEEsc-Cancel-Live]' exists")
            print("    → The regex might fail due to line endings or")
            print("      subtle whitespace. Try adjusting the regex.")
        elif "BEEsc-Cancel-Live" in text:
            print("\n  P3 — Live block:")
            print("    ⚠ 'BEEsc-Cancel-Live' exists but not as start marker.")
            print("    → Find exact line with: grep -n 'BEEsc-Cancel-Live'")
        else:
            print("\n  P3 — Live block:")
            print("    ❌ 'BEEsc-Cancel-Live' does NOT exist at all.")
            print("    → The live BEEsc-Cancel code was never added.")
            print("    → Need to first apply apply_bee_cancel_patch.py")

    # P4 suggestion
    if "--be-cancel-close-only" not in text:
        if 'be-escape-cancel-kappa' in text:
            print("\n  P4 — CLI args:")
            print("    ✅ 'be-escape-cancel-kappa' exists")
            print("    → The exact help text differs from expected.")
            print("    → Will need fuzzy match or manual injection.")
        else:
            print("\n  P4 — CLI args:")
            print("    ❌ 'be-escape-cancel-kappa' NOT found")
            print("    → The --be-escape-cancel-kappa arg was never added.")

    # P5 suggestion
    if "CFG.BREAKEVEN_ESCAPE_CANCEL_CLOSE_ONLY = True" not in text:
        if 'be_escape_cancel_kappa' in text:
            print("\n  P5 — Wiring:")
            print("    ✅ 'be_escape_cancel_kappa' exists")
            print("    → The exact block differs. Will need fuzzy match.")
        else:
            print("\n  P5 — Wiring:")
            print("    ❌ 'be_escape_cancel_kappa' NOT found")
            print("    → The wiring code was never added.")


def print_extended_context(text, marker, before=5, after=40):
    """Print a large context block."""
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
# Main
# ══════════════════════════════════════════════════════════════
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
    print(f"  Total lines: {len(read_file(args.file).split(chr(10))):,}")

    text = read_file(args.file)

    # Run all diagnostics
    diagnose_p1_config(text)
    diagnose_p2_backtest(text)
    diagnose_p3_live(text)
    diagnose_p4_args(text)
    diagnose_p5_wiring(text)
    diagnose_overall_state(text)
    suggest_fixes(text)

    # Extra context if verbose
    if args.verbose:
        print("\n" + "=" * 74)
        print("  Extended contexts (--verbose)")
        print("=" * 74)

        print("\n  ── First 'BEEsc-Cancel' occurrence (extended) ──")
        print_extended_context(text, "BEEsc-Cancel", before=2, after=40)

        print("\n  ── First 'be-escape-cancel-kappa' occurrence (extended) ──")
        print_extended_context(text, "be-escape-cancel-kappa",
                                before=2, after=10)

        print("\n  ── First 'be_escape_cancel_kappa' occurrence (extended) ──")
        print_extended_context(text, "be_escape_cancel_kappa",
                                before=2, after=20)

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
