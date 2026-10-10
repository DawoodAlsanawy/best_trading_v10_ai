#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic tool for F5 anchor mismatch.
Extracts _lv_breakeven() from the target file and shows:
  1. The exact text of the function
  2. The exact bytes of the cancel block
  3. Line-by-line diff with the expected anchor
  4. Character-level differences (whitespace, unicode, etc.)

No assumptions. No patching. Read-only.
"""

import argparse
import difflib
import os
import re
import sys


BOT_FILE = "trading_live_v2.py"


def read_source(path):
    with open(path, "rb") as f:
        raw_bytes = f.read()
    # Detect line ending
    le = "\r\n" if b"\r\n" in raw_bytes else "\n"
    text = raw_bytes.decode("utf-8")
    return text, raw_bytes, le


def extract_function(source, func_name):
    """
    Extract a top-level function body by name.
    Returns (start_line, end_line, lines_list) or None.
    """
    pattern = re.compile(
        r"^def\s+" + re.escape(func_name) + r"\s*\(", re.MULTILINE
    )
    m = pattern.search(source)
    if not m:
        return None
    start = m.start()
    # Find the end: next top-level 'def' or 'class' or EOF
    next_m = re.compile(r"^(def |class )", re.MULTILINE).search(
        source, start + 1
    )
    end = next_m.start() if next_m else len(source)
    func_text = source[start:end]
    lines = func_text.split("\n")
    start_line = source[:start].count("\n") + 1
    end_line = start_line + len(lines) - 1
    return (start_line, end_line, lines)


def print_section(title, color=""):
    reset = "\033[0m" if color else ""
    print(f"\n{color}{'═' * 74}{reset}")
    print(f"{color}  {title}{reset}")
    print(f"{color}{'═' * 74}{reset}")


def show_chars(s):
    """Show each character with its code for whitespace detection."""
    out = []
    for i, ch in enumerate(s):
        if ch == " ":
            out.append(f"<SP>")
        elif ch == "\t":
            out.append(f"<TAB>")
        elif ch == "\r":
            out.append(f"<CR>")
        elif ch == "\n":
            out.append(f"<LF>")
        elif ord(ch) > 127:
            out.append(f"<U+{ord(ch):04X}>")
        else:
            out.append(ch)
    return "".join(out)


def find_substring_similarity(haystack, needle):
    """
    Find the closest matching region in haystack to needle.
    Returns (best_start, ratio, best_match).
    """
    n_len = len(needle)
    if n_len == 0:
        return (0, 0.0, "")
    # Sliding window with variable length (0.7× to 1.3×)
    best = (0, 0.0, "")
    step = max(1, n_len // 20)
    for ln in range(int(n_len * 0.7), int(n_len * 1.3) + 1, max(1, n_len // 20)):
        for start in range(0, len(haystack) - ln + 1, step):
            seg = haystack[start:start + ln]
            r = difflib.SequenceMatcher(None, seg, needle).ratio()
            if r > best[1]:
                best = (start, r, seg)
                if r > 0.95:
                    return best
    return best


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default=BOT_FILE)
    args = p.parse_args()

    if not os.path.exists(args.target):
        print(f"ERROR: {args.target} not found", file=sys.stderr)
        return 1

    source, raw_bytes, le = read_source(args.target)

    print(f"File:           {args.target}")
    print(f"Size (bytes):   {len(raw_bytes):,}")
    print(f"Size (chars):   {len(source):,}")
    print(f"Line ending:    {'CRLF (\\r\\n)' if le == chr(13) + chr(10) else 'LF (\\n)'}")
    print(f"BOM present:    {raw_bytes[:3] == b'\\xef\\xbb\\xbf'}")

    # ═══ 1. Extract _lv_breakeven ═══
    print_section("1. _lv_breakeven() FUNCTION")
    result = extract_function(source, "_lv_breakeven")
    if result is None:
        print("  ✗ Function '_lv_breakeven' NOT FOUND")
        print("\n  Searching for similar names...")
        for m in re.finditer(r"^def\s+(\w+)", source, re.MULTILINE):
            name = m.group(1)
            if "break" in name.lower() or "be" == name[:2]:
                print(f"    → {name}  (line {source[:m.start()].count(chr(10))+1})")
        return 2

    start_line, end_line, func_lines = result
    print(f"  ✓ Found at lines {start_line}..{end_line} "
          f"({len(func_lines)} lines)")
    print()
    for i, ln in enumerate(func_lines):
        print(f"  {start_line + i:6d} | {ln}")

    # ═══ 2. Look for the cancel block ═══
    print_section("2. CANCEL BLOCK INSIDE _lv_breakeven")

    # Find the "for o in _lv_open_orders_all" block
    block_start = None
    block_end = None
    for i, ln in enumerate(func_lines):
        if "_lv_open_orders_all(exchange, sym)" in ln and "for o in" in ln:
            block_start = i
            break

    if block_start is None:
        print("  ✗ 'for o in _lv_open_orders_all(...)' NOT FOUND in function")
        print("\n  Searching for other cancel-related patterns...")
        for i, ln in enumerate(func_lines):
            if "_stale.append" in ln or "cancel" in ln.lower() or \
               "_cancel_stale" in ln:
                print(f"  line {start_line + i:6d} | {ln}")
        return 3

    # Find the end of the for block (next line at same or lower indentation)
    base_indent = len(func_lines[block_start]) - len(
        func_lines[block_start].lstrip()
    )
    for i in range(block_start + 1, len(func_lines)):
        ln = func_lines[i]
        if not ln.strip():
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= base_indent:
            block_end = i
            break
    if block_end is None:
        block_end = len(func_lines)

    print(f"  ✓ Block spans lines {start_line + block_start}"
          f"..{start_line + block_end - 1}")
    print()
    block_lines = func_lines[block_start:block_end]
    for i, ln in enumerate(block_lines):
        print(f"  {start_line + block_start + i:6d} | {ln}")

    # ═══ 3. What F5 expects ═══
    print_section("3. WHAT F5 EXPECTS (the anchor)")
    expected = [
        '        for o in _lv_open_orders_all(exchange, sym):',
        '            if not _is_protective_order(o):',
        '                continue',
        '            _ot = str(o.get(\'type\') or \'\').lower()',
        '            if \'take_profit\' in _ot:',
        '                continue',
        '            _sp = float(',
        '                o.get(\'stopPrice\')',
        '                or o.get(\'triggerPrice\')',
        '                or (o.get(\'info\') or {}).get(\'stopPrice\')',
        '                or 0',
        '            )',
        '            if _sp > 0 and abs(_sp - _exch_sl) / max(abs(_exch_sl), 1e-9) < 1e-4:',
        '                _stale.append(o[\'id\'])',
    ]
    for i, ln in enumerate(expected):
        print(f"  {i:3d}  | {ln}")

    # ═══ 4. Line-by-line diff ═══
    print_section("4. DIFF: EXPECTED vs ACTUAL")
    diff = difflib.unified_diff(
        expected, block_lines,
        fromfile="EXPECTED (F5 anchor)",
        tofile="ACTUAL (file content)",
        lineterm="",
    )
    has_diff = False
    for ln in diff:
        has_diff = True
        print(f"  {ln}")
    if not has_diff:
        print("  ✓ NO DIFF — identical")
    else:
        print("\n  → Lines marked '-' are in expected but not in actual.")
        print("  → Lines marked '+' are in actual but not in expected.")

    # ═══ 5. Character-level analysis of suspicious lines ═══
    print_section("5. CHARACTER-LEVEL ANALYSIS")
    suspicious = []
    for i, ln in enumerate(block_lines):
        stripped = ln.strip()
        if "take_profit" in stripped or "_ot" in stripped or "type" in stripped:
            suspicious.append((i, ln))

    if not suspicious:
        print("  (no suspicious lines found)")
    for i, ln in suspicious:
        print(f"\n  Line {start_line + block_start + i}:")
        print(f"    Raw    : {ln!r}")
        print(f"    Visible: {show_chars(ln)}")
        print(f"    Length : {len(ln)} chars, "
              f"indent={len(ln) - len(ln.lstrip())} spaces")

    # ═══ 6. Search for the closest match across the whole file ═══
    print_section("6. SEARCH WHOLE FILE FOR CLOSEST MATCH")

    # Full anchor as one string
    anchor_str = "\n".join([
        '        for o in _lv_open_orders_all(exchange, sym):',
        '            if not _is_protective_order(o):',
        '                continue',
        '            _ot = str(o.get(\'type\') or \'\').lower()',
        '            if \'take_profit\' in _ot:',
        '                continue',
    ])

    anchor_str = anchor_str.replace("\n", le)

    print(f"  Searching for anchor (with line ending = "
          f"{'CRLF' if le == chr(13)+chr(10) else 'LF'})...")

    # Direct substring
    idx = source.find(anchor_str)
    print(f"  Direct exact match: {'FOUND at position ' + str(idx) if idx >= 0 else 'NOT FOUND'}")

    # Try with LF only (in case file has mixed endings)
    anchor_lf = anchor_str.replace("\r\n", "\n")
    source_lf = source.replace("\r\n", "\n")
    idx_lf = source_lf.find(anchor_lf)
    print(f"  Normalized-LF match: {'FOUND at position ' + str(idx_lf) if idx_lf >= 0 else 'NOT FOUND'}")

    # Fuzzy match the first 5 lines
    needle_first5 = "\n".join(expected[:5]).replace("\n", "\n")
    start, ratio, match = find_substring_similarity(source_lf, needle_first5)
    if ratio > 0.5:
        line_no = source_lf[:start].count("\n") + 1
        print(f"\n  Closest fuzzy match (ratio={ratio:.3f}) at line ~{line_no}:")
        for ln in match.split("\n"):
            print(f"    | {ln}")
        if ratio < 0.98:
            print(f"\n  Diff (needle → match):")
            for d in difflib.unified_diff(
                needle_first5.split("\n"),
                match.split("\n"),
                lineterm="",
            ):
                print(f"    {d}")
    else:
        print(f"\n  No close match (best ratio={ratio:.3f})")

    # ═══ 7. Exact byte examination of _ot line ═══
    print_section("7. EXACT BYTES OF '_ot' LINE")
    for m in re.finditer(r"^.*?_ot.*$", source_lf, re.MULTILINE):
        line_text = m.group(0)
        line_no = source_lf[:m.start()].count("\n") + 1
        print(f"\n  Line {line_no}: {line_text!r}")
        print(f"    bytes: {line_text.encode('utf-8').hex(' ')}")

    # ═══ 8. Summary ═══
    print_section("8. SUMMARY / RECOMMENDATION")
    exact_match = (idx >= 0) or (idx_lf >= 0)
    if exact_match:
        print("  ✓ The anchor EXISTS in the file.")
        print("    The F5 failure might be from:")
        print("    - Ambiguous match (anchor appears multiple times)")
        print("    - Idempotency marker false-positive")
        print("    - Invisible character difference (BOM, non-ASCII space)")
    else:
        print("  ✗ The anchor does NOT exist verbatim.")
        if ratio > 0.85:
            print(f"    Closest match ratio: {ratio:.3f}")
            print("    → Look at section 4 (diff) to see exact differences")
        else:
            print("    → The code structure is significantly different.")
            print("    → Manual inspection needed (see sections 5, 6, 7)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
