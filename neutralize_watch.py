#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
neutralize_watch.py — v2
إزالة Watch وظيفياً. v2 يدعم توقيعات متعددة الأسطر (مثل monitor_watch_signals).
"""

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


BANNER_MARKER = "# ══ [WATCH-REMOVED-MASTER]"
BANNER_TEXT = '''

# ══ [WATCH-REMOVED-MASTER] ═══════════════════════════════════════════
# Watch-then-trigger mode has been permanently disabled.
# All watch code paths (state files, signal registration, monitoring)
# short-circuit at entry via this flag. The functions themselves are
# preserved (some share utilities with legacy paths), but they are
# provably dead code now.
#
# To temporarily re-enable watch (NOT recommended):
#   Set WATCH_REMOVED = False and WATCH_MODE_ENABLED = True in Config.
# ═════════════════════════════════════════════════════════════════════
WATCH_REMOVED = True
# ═════════════════════════════════════════════════════════════════════
'''


def find_anchor_for_banner(text):
    for a in ('warnings.filterwarnings("ignore")',
              "warnings.filterwarnings('ignore')"):
        if a in text:
            return a
    return None


def insert_banner(text):
    if BANNER_MARKER in text:
        return text, False
    anchor = find_anchor_for_banner(text)
    if anchor is None:
        return text, False
    return text.replace(anchor, anchor + BANNER_TEXT, 1), True


GETATTR_PAT = re.compile(
    r"getattr\(CFG,\s*['\"]WATCH_MODE_ENABLED['\"],\s*True\)"
)
GETATTR_REPLACEMENT = (
    "(not WATCH_REMOVED) and getattr(CFG, 'WATCH_MODE_ENABLED', False)"
)


def fix_getattr_defaults(text):
    n = len(GETATTR_PAT.findall(text))
    if n == 0:
        return text, 0
    return GETATTR_PAT.sub(GETATTR_REPLACEMENT, text), n


# ═══════════════════════════════════════════════════════════════
# find_function_block — يدعم توقيعات متعددة الأسطر
# ═══════════════════════════════════════════════════════════════

def find_function_block(text, fname):
    """
    يجد نهاية توقيع دالة (position of the newline after the colon).
    يدعم: def f(a,\n b,\n c) -> T:
    Returns: (def_indent_str, position_of_newline_after_colon) or None
    """
    pat = re.compile(
        rf"^(?P<indent>[ \t]*)def[ \t]+{re.escape(fname)}[ \t]*\(",
        re.MULTILINE,
    )
    m = pat.search(text)
    if not m:
        return None

    def_indent = m.group('indent')
    paren_start = m.end() - 1   # position of '('

    # عد الأقواس
    depth = 0
    i = paren_start
    while i < len(text):
        c = text[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                break
        i += 1
    else:
        return None

    # بعد القوس المُغلق: إما ':' أو '-> ...:'
    j = i + 1
    while j < len(text) and text[j] in ' \t':
        j += 1

    if text[j:j+2] == '->':
        # تخطّي نوع العودة — نبحث عن ':' بعد ذلك
        colon = text.find(':', j)
        if colon < 0:
            return None
        j = colon

    if j >= len(text) or text[j] != ':':
        return None

    # موقع الـ newline بعد الـ ':'
    newline_pos = text.find('\n', j)
    if newline_pos < 0:
        newline_pos = len(text)

    return def_indent, newline_pos


GUARDS = [
    ('load_watched_signals', 'return {}'),
    ('save_watched_signals', 'return None'),
    ('register_watch_signal', 'return False'),
    ('monitor_watch_signals', 'return None'),
]


def add_function_guards(text):
    applied = []
    for fname, retval in GUARDS:
        # ── idempotency: هل الـ guard موجود؟ ──
        # ابحث عن تعريف الدالة أولاً
        found = find_function_block(text, fname)
        if found is None:
            continue
        def_indent, newline_pos = found

        # افحص أول 300 حرف بعد التوقيع
        look_ahead = text[newline_pos:newline_pos + 300]
        if 'if WATCH_REMOVED:' in look_ahead[:200]:
            continue

        body_indent = def_indent + '    '
        guard = (
            f"\n{body_indent}if WATCH_REMOVED:\n"
            f"{body_indent}    {retval}"
        )

        text = text[:newline_pos] + guard + text[newline_pos:]
        applied.append(fname)

    return text, applied


# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"❌ {args.file} غير موجود")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("═" * 70)
    print("  neutralize_watch.py (v2)")
    print("═" * 70)
    print()

    # 1. البانر
    text, banner_added = insert_banner(text)
    if banner_added:
        print("  ✅ [1/3] أدخلت WATCH_REMOVED = True (master switch)")
    elif BANNER_MARKER in original:
        print("  ⏭️  [1/3] البانر موجود مسبقاً")
    else:
        print("  ❌ [1/3] لم أجد anchor للبانر — توقف")
        return 2

    # 2. getattr fix
    text, n_getattr = fix_getattr_defaults(text)
    if n_getattr > 0:
        print(f"  ✅ [2/3] أصلحت {n_getattr} موضع getattr")
    elif GETATTR_REPLACEMENT in original:
        print("  ⏭️  [2/3] getattr مُصلَح مسبقاً")
    else:
        print("  ⚠️  [2/3] لم أجد أي getattr")

    # 3. Guards
    text, guarded = add_function_guards(text)
    if guarded:
        print(f"  ✅ [3/3] أضفت guards إلى: {', '.join(guarded)}")
    else:
        print("  ⏭️  [3/3] guards موجودة مسبقاً")
    print(f"      (المجموع: {len(guarded)}/4 دوال)")

    # تحقق syntax
    try:
        ast.parse(text)
    except SyntaxError as e:
        print()
        print(f"  ❌ خطأ صياغة: {e}")
        print(f"     السطر {e.lineno}: {e.text}")
        return 3

    print("  ✅ الصياغة صحيحة (ast.parse نجح)")
    print()

    if text == original:
        print("  ℹ️  لا حاجة لأي تعديل — كل شيء مُطبَّق مسبقاً")
        return 0

    if args.dry_run:
        print("═" * 70)
        print("  ℹ️  Dry run — لم يُكتب أي شيء")
        print("═" * 70)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_watch_{ts}')
    shutil.copy2(p, backup)
    print(f"  💾 Backup: {backup}")

    p.write_text(text, encoding='utf-8')
    print(f"  ✏️  كُتب: {p}")
    print()
    print("═" * 70)
    print("  ✅ تم")
    print("═" * 70)
    print(f"  للتراجع: cp {backup.name} {p.name}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
