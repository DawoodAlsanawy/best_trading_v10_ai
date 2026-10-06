#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_ablation_flags_v2.py — نسخة regex مرنة
"""

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def find_line(lines, pattern):
    """يُعيد فهارس الأسطر المطابقة للـ regex."""
    r = re.compile(pattern)
    return [i for i, l in enumerate(lines) if r.search(l)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"ERR: {args.file} not found")
        return 1

    text = p.read_text(encoding='utf-8')
    lines = text.split('\n')
    changes = []

    # ═══ Patch 1: GAUGE_DISABLE_BUY في Config ═══
    cfg_idx = find_line(lines, r'GAUGE_DISABLE_SELL\s*:\s*bool')
    if not cfg_idx:
        print("ERR: GAUGE_DISABLE_SELL not found in Config")
        return 2
    i = cfg_idx[0]
    if 'GAUGE_DISABLE_BUY' not in text:
        # أضف السطر بعد GAUGE_DISABLE_SELL
        match = re.match(r'^(\s*)', lines[i])
        indent = match.group(1) if match else '    '
        new_line = f"{indent}GAUGE_DISABLE_BUY: bool = False   # [ABL] True → SELL-only mode"
        lines.insert(i + 1, new_line)
        changes.append(f"Config: أُضيف GAUGE_DISABLE_BUY بعد السطر {i+1}")

    text = '\n'.join(lines)
    lines = text.split('\n')

    # ═══ Patch 2: build_signals hook ═══
    # ابحث عن السطر الذي يحتوي "GAUGE_DISABLE_SELL" داخل build_signals
    bs_hooks = find_line(lines, r"if\s+action\s*==\s*['\"]SELL['\"]\s+and\s+getattr\(CFG,\s*['\"]GAUGE_DISABLE_SELL['\"]")
    if bs_hooks:
        i = bs_hooks[0]
        # احصل على indent
        match = re.match(r'^(\s*)', lines[i])
        indent = match.group(1) if match else '                '
        # هل السطر التالي يحتوي على continue؟
        if i + 1 < len(lines) and 'continue' in lines[i + 1]:
            # أضف سطرين بعد continue
            match_c = re.match(r'^(\s*)', lines[i + 1])
            indent_c = match_c.group(1) if match_c else indent + '    '
            new_lines = [
                f"{indent}if action == \"BUY\" and getattr(CFG, 'GAUGE_DISABLE_BUY', False):",
                f"{indent_c}continue",
            ]
            lines[i + 2:i + 2] = new_lines
            changes.append(f"build_signals: أُضيف BUY-disable بعد السطر {i+1}")
    else:
        print("WARN: build_signals hook not found — may be OK if already exists")

    text = '\n'.join(lines)
    lines = text.split('\n')

    # ═══ Patch 3: argparse flags ═══
    if '--no-apex' not in text:
        # ابحث عن gauge-disable-sell في argparse
        ap_idx = find_line(lines, r'p\.add_argument\(["\']--gauge-disable-sell["\']')
        if ap_idx:
            i = ap_idx[0]
            # ابحث عن نهاية التعريف (قد يمتد لأكثر من سطر)
            j = i
            while j < len(lines) and not lines[j].rstrip().endswith(')'):
                j += 1
            # indent
            match = re.match(r'^(\s*)', lines[i])
            indent = match.group(1) if match else '    '
            new_block = [
                "",
                f"{indent}# [ABLATION-FLAGS]",
                f"{indent}p.add_argument(\"--no-apex\", action=\"store_true\",",
                f"{indent}               help=\"Disable Apex exit\")",
                f"{indent}p.add_argument(\"--no-partial\", action=\"store_true\",",
                f"{indent}               help=\"Disable Partial TP\")",
                f"{indent}p.add_argument(\"--no-breakeven\", action=\"store_true\",",
                f"{indent}               help=\"Disable Breakeven SL\")",
                f"{indent}p.add_argument(\"--tp-mult\", type=float, default=None,",
                f"{indent}               help=\"Override TP_MULT\")",
                f"{indent}p.add_argument(\"--sell-only\", action=\"store_true\",",
                f"{indent}               help=\"SELL-only mode\")",
            ]
            lines[j + 1:j + 1] = new_block
            changes.append(f"argparse: أُضيفت 5 flags بعد السطر {j+1}")
        else:
            print("ERR: gauge-disable-sell argparse not found")
            return 3

    text = '\n'.join(lines)

    # ═══ Patch 4: main() wiring ═══
    if 'args.no_apex' not in text:
        # ابحث عن معالجة gauge_disable_sell في main
        gds = find_line(lines, r'if\s+args\.gauge_disable_sell')
        if gds:
            i = gds[0]
            match = re.match(r'^(\s*)', lines[i])
            indent = match.group(1) if match else '    '
            # ابحث عن نهاية الكتلة
            j = i + 1
            while j < len(lines):
                if lines[j].strip() and not lines[j].startswith(indent + ' ') \
                   and not lines[j].startswith(indent + '\t'):
                    break
                j += 1
            new_block = [
                f"{indent}# [ABLATION-FLAGS]",
                f"{indent}if getattr(args, \"no_apex\", False):",
                f"{indent}    CFG.APEX_ENABLED = False",
                f"{indent}    log.info(\"[Ablation] APEX DISABLED\")",
                f"{indent}if getattr(args, \"no_partial\", False):",
                f"{indent}    CFG.PARTIAL_TP_ENABLED = False",
                f"{indent}    log.info(\"[Ablation] PARTIAL_TP DISABLED\")",
                f"{indent}if getattr(args, \"no_breakeven\", False):",
                f"{indent}    CFG.BREAKEVEN_ENABLED = False",
                f"{indent}    log.info(\"[Ablation] BREAKEVEN DISABLED\")",
                f"{indent}if getattr(args, \"tp_mult\", None) is not None:",
                f"{indent}    CFG.TP_MULT = float(args.tp_mult)",
                f"{indent}    log.info(f\"[Ablation] TP_MULT = {{CFG.TP_MULT}}\")",
                f"{indent}if getattr(args, \"sell_only\", False):",
                f"{indent}    CFG.GAUGE_DISABLE_BUY = True",
                f"{indent}    log.info(\"[Ablation] BUY DISABLED — SELL-only mode\")",
            ]
            lines[j:j] = new_block
            changes.append(f"main: أُضيف wiring بعد السطر {j}")

    text = '\n'.join(lines)

    # ═══ Verify ═══
    try:
        ast.parse(text)
        print("OK: ast.parse passed")
    except SyntaxError as e:
        print(f"ERR: syntax error at {e.lineno}: {e.text}")
        return 4

    print()
    print("═══ Changes ═══")
    for c in changes:
        print(f"  ✅ {c}")

    if not changes:
        print("  (لا تعديلات)")
        return 0

    if args.dry_run:
        print("\nDry run — nothing written")
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_abl2_{ts}')
    shutil.copy2(p, backup)
    p.write_text(text, encoding='utf-8')
    print(f"\nBackup: {backup}")
    print(f"Written: {p}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
