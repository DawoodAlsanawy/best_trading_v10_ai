#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_end_date.py — إضافة --end-date لتثبيت نافذة الباكتيست.

التشغيل:
    python3 add_end_date.py --dry-run
    python3 add_end_date.py
"""

import argparse
import ast
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Patch 1: Config field
# ═══════════════════════════════════════════════════════════════

P1_OLD = '    CAPITAL_FLOOR: float = 0.15'
P1_NEW = (
    '    # [END-DATE-FIELD]\n'
    '    BACKTEST_END_DATE: Optional[str] = None\n'
    '    CAPITAL_FLOOR: float = 0.15'
)
P1_MARK = 'BACKTEST_END_DATE: Optional[str]'


# ═══════════════════════════════════════════════════════════════
# Patch 2: resolver helper (بعد CFG = Config())
# ═══════════════════════════════════════════════════════════════

P2_OLD = 'CFG = Config()'
P2_NEW = '''CFG = Config()


def _resolve_end_datetime() -> datetime:
    """[END-DATE-HELPER] يحل نهاية نافذة البيانات."""
    _raw = getattr(CFG, 'BACKTEST_END_DATE', None)
    if _raw:
        try:
            _dt = datetime.strptime(str(_raw), "%Y-%m-%d")
            return (_dt.replace(tzinfo=timezone.utc)
                    + timedelta(days=1)
                    - timedelta(seconds=1))
        except Exception as _e:
            log.warning("[EndDate] parse failed: %s -- using now()" % _e)
    return datetime.now(timezone.utc)'''
P2_MARK = 'def _resolve_end_datetime'


# ═══════════════════════════════════════════════════════════════
# Patch 3: cutoff in both _load_cached AND _load_cached_sub (count=2)
# ═══════════════════════════════════════════════════════════════

P3_OLD = (
    '    now_utc = datetime.now(timezone.utc)\n'
    '    since_full_dt = now_utc - timedelta(days=int(days))'
)
P3_NEW = (
    '    now_utc = datetime.now(timezone.utc)\n'
    '    # [END-DATE-CUTOFF]\n'
    '    _end_dt = _resolve_end_datetime()\n'
    '    since_full_dt = _end_dt - timedelta(days=int(days))'
)
P3_MARK = '# [END-DATE-CUTOFF]'


# ═══════════════════════════════════════════════════════════════
# Patch 4: truncation in both functions (count=2)
# ═══════════════════════════════════════════════════════════════

P4_OLD = '    df_window = df[df.index >= since_full_dt]'
P4_NEW = (
    '    # [END-DATE-TRUNC]\n'
    '    df_window = df[(df.index >= since_full_dt)'
    ' & (df.index <= _end_dt)]'
)
P4_MARK = '# [END-DATE-TRUNC]'


# ═══════════════════════════════════════════════════════════════
# Patch 5: CLI argument
# ═══════════════════════════════════════════════════════════════

P5_OLD = '    p.add_argument("--history-days",       type=int,   default=None)'
P5_NEW = (
    '    p.add_argument("--history-days",       type=int,   default=None)\n'
    '    p.add_argument("--end-date", type=str, default=None,\n'
    '                   help="Backtest end date YYYY-MM-DD for reproducibility")'
)
P5_MARK = 'p.add_argument("--end-date"'


# ═══════════════════════════════════════════════════════════════
# Patch 6: main() wiring
# ═══════════════════════════════════════════════════════════════

P6_OLD = '    if args.history_days     is not None: CFG.history_days = args.history_days'
P6_NEW = (
    '    if args.history_days     is not None: CFG.history_days = args.history_days\n'
    '    if getattr(args, "end_date", None) is not None:\n'
    '        CFG.BACKTEST_END_DATE = str(args.end_date)\n'
    '        log.info(f"[Backtest] end-date pinned to {args.end_date}")'
)
P6_MARK = 'CFG.BACKTEST_END_DATE = str(args.end_date)'


# ═══════════════════════════════════════════════════════════════

def apply_patch(text, old, new, marker, name, count=1):
    if marker and marker in text:
        return text, f"SKIP: {name}"
    n_old = text.count(old)
    if n_old == 0:
        return text, f"ERR: {name} (anchor not found)"
    if n_old < count:
        return text, f"ERR: {name} (found {n_old}, need {count})"
    text = text.replace(old, new, count)
    return text, f"OK: {name} (x{count})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"ERR: {args.file} not found")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("=" * 70)
    print("  add_end_date.py")
    print("=" * 70)
    print()

    text, s = apply_patch(text, P1_OLD, P1_NEW, P1_MARK,
                          "Config field", 1)
    print(f"  {s}")

    text, s = apply_patch(text, P2_OLD, P2_NEW, P2_MARK,
                          "resolver helper", 1)
    print(f"  {s}")

    text, s = apply_patch(text, P3_OLD, P3_NEW, P3_MARK,
                          "cutoff (main + sub)", 2)
    print(f"  {s}")

    text, s = apply_patch(text, P4_OLD, P4_NEW, P4_MARK,
                          "truncation (main + sub)", 2)
    print(f"  {s}")

    text, s = apply_patch(text, P5_OLD, P5_NEW, P5_MARK,
                          "CLI --end-date", 1)
    print(f"  {s}")

    text, s = apply_patch(text, P6_OLD, P6_NEW, P6_MARK,
                          "main() wiring", 1)
    print(f"  {s}")

    try:
        ast.parse(text)
        print()
        print("  OK: ast.parse passed")
    except SyntaxError as e:
        print()
        print(f"  ERR: syntax error at line {e.lineno}: {e.text}")
        return 3

    if text == original:
        print()
        print("  No changes.")
        return 0

    if args.dry_run:
        print()
        print("=" * 70)
        print("  Dry run - nothing written")
        print("=" * 70)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_enddate_{ts}')
    shutil.copy2(p, backup)
    print()
    print(f"  Backup: {backup}")

    p.write_text(text, encoding='utf-8')
    print(f"  Written: {p}")
    print()
    print("=" * 70)
    print("  Done")
    print("=" * 70)
    print(f"  Rollback: cp {backup.name} {p.name}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
