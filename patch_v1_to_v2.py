#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v1_to_v2.py
=================
يستبدل edit3 + edit5 في adaptive_capital_v1.py بالنسختين المُصححتين.

الاستخدام:
    python patch_v1_to_v2.py
"""

import os
import re
import sys


SRC = "adaptive_capital_v1.py"
DST = "adaptive_capital_v2.py"


# ════════════════════════════════════════════════════════════════
# النسخ المُصحّحة (تُدرج في الملف)
# ════════════════════════════════════════════════════════════════

NEW_EDIT3 = '''def edit3_filter_symbols_in_live(src):
    print("\\n\u25b6 Edit 3: filter symbols in run_live")
    if "[CAPITAL-ADAPTIVE] filter in run_live" in src:
        print("   \u2139\ufe0f  already applied")
        return src, True

    # v2 FIX: ASCII-only anchor. Arabic anchors are fragile due to
    # RTL rendering + Unicode parentheses variants.
    anchor = (
        "    top_syms = scan_top_assets(exchange)\\n"
        "\\n"
        "    # \u2550\u2550 [DATA-LENGTH-FIX]"
    )

    if anchor not in src:
        print("   \u274c ASCII anchor not found \\u2014 trying fallback")
        simple = "    top_syms = scan_top_assets(exchange)\\n"
        if simple not in src:
            print("   \u274c fallback failed too")
            return src, False
        insert_after = simple
        insertion = (
            "    # \u2550\u2550 [CAPITAL-ADAPTIVE] filter in run_live "
            "\u2550\u2550\\n"
            "    _cap_for_filter = float(\\n"
            "        getattr(CFG, \\"LIVE_TRADING_CAPITAL\\", 0.0)\\n"
            "        or getattr(CFG, \\"INITIAL_CAPITAL\\", 100.0)\\n"
            "    )\\n"
            "    if _cap_for_filter > 0:\\n"
            "        _filtered = _filter_symbols_for_capital(\\n"
            "            exchange, list(top_syms), _cap_for_filter, CFG\\n"
            "        )\\n"
            "        if _filtered:\\n"
            "            top_syms = _filtered\\n"
            "        else:\\n"
            "            log.error(\\n"
            "                \\"[CapitalAdapt] NO symbols tradeable \\"\\n"
            "                \\"at this capital. Aborting.\\"\\n"
            "            )\\n"
            "            return\\n"
        )
        src = src.replace(simple, insert_after + insertion, 1)
        print("   \u2705 filter inserted (fallback)")
        return src, True

    replacement = (
        "    top_syms = scan_top_assets(exchange)\\n"
        "    # \u2550\u2550 [CAPITAL-ADAPTIVE] filter in run_live \u2550\u2550\\n"
        "    _cap_for_filter = float(\\n"
        "        getattr(CFG, \\"LIVE_TRADING_CAPITAL\\", 0.0)\\n"
        "        or getattr(CFG, \\"INITIAL_CAPITAL\\", 100.0)\\n"
        "    )\\n"
        "    if _cap_for_filter > 0:\\n"
        "        _filtered = _filter_symbols_for_capital(\\n"
        "            exchange, list(top_syms), _cap_for_filter, CFG\\n"
        "        )\\n"
        "        if _filtered:\\n"
        "            top_syms = _filtered\\n"
        "        else:\\n"
        "            log.error(\\n"
        "                \\"[CapitalAdapt] NO symbols tradeable \\"\\n"
        "                \\"at this capital. Aborting.\\"\\n"
        "            )\\n"
        "            return\\n"
        "\\n"
        "    # \u2550\u2550 [DATA-LENGTH-FIX]"
    )
    src = src.replace(anchor, replacement, 1)
    print("   \u2705 filter inserted (proper)")
    return src, True


'''


NEW_EDIT5 = '''def edit5_stats_logger(src):
    print("\\n\u25b6 Edit 5: wire stats logger")
    # v2 FIX: check for call-site marker, not function definition
    if "# [CAPITAL-ADAPTIVE] stats" in src:
        print("   \u2139\ufe0f  already applied")
        return src, True

    anchor = (
        "            # [FIX-09-PROPER] pos-cache stats\\n"
        "            _pos_cache_log_stats()"
    )
    if anchor not in src:
        print("   \u274c pos-cache anchor not found")
        return src, False

    replacement = (
        "            # [FIX-09-PROPER] pos-cache stats\\n"
        "            _pos_cache_log_stats()\\n"
        "            # [CAPITAL-ADAPTIVE] stats\\n"
        "            _capital_adapt_log_stats()"
    )
    src = src.replace(anchor, replacement, 1)
    print("   \u2705 stats logger wired")
    return src, True


'''


# ════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ════════════════════════════════════════════════════════════════

def find_function_bounds(src, func_name):
    """
    Locate a function's start and end (next top-level `def` or `if __name__`).
    Returns (start, end) character indices, or None if not found.
    """
    # Find function start: `def name(`
    start_pat = re.compile(
        r"^def " + re.escape(func_name) + r"\(",
        re.MULTILINE
    )
    m = start_pat.search(src)
    if not m:
        return None

    start = m.start()

    # Find end: next line starting with `def ` or `class ` or `if __name__`
    # at column 0, AFTER the current function
    end_pat = re.compile(
        r"^(?:def |class |if __name__)",
        re.MULTILINE
    )
    m2 = end_pat.search(src, m.end())
    end = m2.start() if m2 else len(src)

    return start, end


def patch(src):
    # Patch edit3
    bounds = find_function_bounds(src, "edit3_filter_symbols_in_live")
    if bounds is None:
        print("❌ edit3_filter_symbols_in_live not found")
        return None
    start, end = bounds
    src = src[:start] + NEW_EDIT3 + src[end:]
    print(f"✅ edit3 replaced (chars {start}..{end})")

    # Patch edit5
    bounds = find_function_bounds(src, "edit5_stats_logger")
    if bounds is None:
        print("❌ edit5_stats_logger not found")
        return None
    start, end = bounds
    src = src[:start] + NEW_EDIT5 + src[end:]
    print(f"✅ edit5 replaced (chars {start}..{end})")

    return src


def main():
    if not os.path.exists(SRC):
        print(f"❌ {SRC} not found")
        sys.exit(1)

    with open(SRC, encoding="utf-8") as f:
        src = f.read()

    print(f"📖 Loaded {SRC} ({len(src):,} chars)")

    new_src = patch(src)
    if new_src is None:
        sys.exit(1)

    # Syntax check
    try:
        compile(new_src, DST, "exec")
        print("✅ Syntax OK")
    except SyntaxError as e:
        print(f"❌ SyntaxError at line {e.lineno}: {e.msg}")
        print(f"   Text: {e.text!r}")
        sys.exit(2)

    with open(DST, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"✅ Written: {DST} ({len(new_src):,} chars)")


if __name__ == "__main__":
    main()
