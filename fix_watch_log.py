#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
إصلاح السجل الكاذب في trading_2.py — v2 (line-based, robust).
- لا يعتمد على مطابقة نصية حرفية.
- يكتشف الإزاحة ونهاية البيان تلقائياً.
- idempotent: لا يُعيد التطبيق.
- يعمل backup قبل التعديل.
التشغيل: python3 fix_watch_log.py [--file trading_2.py] [--dry-run]
"""

import argparse
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path


ENABLED_MARKER = 'Watch-then-trigger ENABLED'
DONE_MARKER = 'Watch-then-trigger DISABLED (Config default)'


def find_statement_end(lines, start_idx):
    """
    Find the line index where the statement starting at start_idx closes.
    Tracks parens, ignores parens inside strings/comments.
    """
    depth = 0
    seen_open = False
    for i in range(start_idx, len(lines)):
        in_str = None
        in_esc = False
        for ch in lines[i]:
            if in_str:
                if in_esc:
                    in_esc = False
                elif ch == '\\':
                    in_esc = True
                elif ch == in_str:
                    in_str = None
            else:
                if ch in ('"', "'"):
                    in_str = ch
                elif ch == '#':
                    break  # rest of line is comment
                elif ch == '(':
                    depth += 1
                    seen_open = True
                elif ch == ')':
                    depth -= 1
                    if seen_open and depth <= 0:
                        return i
        if seen_open and depth <= 0:
            return i
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"❌ {path} غير موجود.")
        sys.exit(1)

    text = path.read_text(encoding='utf-8')

    # ── Idempotency ──
    if DONE_MARKER in text:
        print(f"✅ {path}: الإصلاح مُطبَّق مسبقاً. لا حاجة لتعديل.")
        return

    lines = text.split('\n')

    # ── Find the ENABLED log.info line ──
    idx_enabled = None
    for i, line in enumerate(lines):
        if ENABLED_MARKER in line and 'log.info' in line:
            idx_enabled = i
            break

    if idx_enabled is None:
        print(f"❌ {path}: لم أجد سطر الـ ENABLED.")
        print("   السطور التي تحوي 'Watch-then-trigger':")
        for i, line in enumerate(lines, 1):
            if 'Watch-then-trigger' in line:
                print(f"   [{i}] {line}")
        sys.exit(2)

    # ── Detect indentation ──
    raw_line = lines[idx_enabled]
    indent_len = len(raw_line) - len(raw_line.lstrip(' '))
    indent = ' ' * indent_len

    # ── Find end of statement ──
    idx_end = find_statement_end(lines, idx_enabled)
    if idx_end is None:
        print(f"❌ لم أستطع تحديد نهاية الـ statement (بدءاً من سطر {idx_enabled + 1}).")
        sys.exit(3)

    block_lines = lines[idx_enabled:idx_end + 1]

    # ── Build new lines ──
    new_lines = []
    new_lines.append(f"{indent}if CFG.WATCH_MODE_ENABLED:")
    for bl in block_lines:
        new_lines.append("    " + bl)   # +4 spaces to each line of the block
    new_lines.append(f"{indent}else:")
    new_lines.append(
        f'{indent}    log.info("[Watch] Watch-then-trigger '
        f'DISABLED (Config default) — "'
    )
    # continuation of the f-string: align at column of opening " after log.info(
    # indent + 4 (else body) + 9 (len of "log.info(") = indent + 13
    new_lines.append(
        f'{indent}             f"legacy immediate placement")'
    )

    # ── Preview ──
    print(f"📄 الملف: {path}")
    print(f"🔍 السطر: {idx_enabled + 1}-{idx_end + 1}  (indent = {indent_len} مسافة)")
    print()
    print("── OLD ──")
    for bl in block_lines:
        print(f"  | {bl}")
    print()
    print("── NEW ──")
    for nl in new_lines:
        print(f"  | {nl}")
    print()

    if args.dry_run:
        print("(لم يُكتب أي شيء — dry run)")
        return

    # ── Backup ──
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = path.with_suffix(path.suffix + f'.bak_{ts}')
    shutil.copy2(path, backup)
    print(f"💾 Backup: {backup}")

    # ── Apply ──
    new_all_lines = lines[:idx_enabled] + new_lines + lines[idx_end + 1:]
    new_text = '\n'.join(new_all_lines)
    path.write_text(new_text, encoding='utf-8')
    print(f"✏️  كُتب {path}")

    # ── Verify syntax ──
    try:
        ast.parse(new_text)
        print("✅ الصياغة صحيحة (ast.parse نجح)")
    except SyntaxError as e:
        print(f"❌ خطأ صياغة: {e}")
        print(f"🔄 تراجع من {backup}")
        shutil.copy2(backup, path)
        sys.exit(4)

    print()
    print("✅ تم الإصلاح.")
    print(f"   للتراجع: cp {backup} {path}")


if __name__ == '__main__':
    main()
