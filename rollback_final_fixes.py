#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rollback B1-B5 from trading_live_v2.py (keep test-file fixes).
Restores the file to the state before apply_final_fixes.py ran.
"""

import os
import shutil
import sys

BOT = "trading_live_v2.py"
BACKUP_DIR = ".patches_backup"


def log(m):
    print(f"[rollback] {m}", flush=True)


def find_backup():
    if not os.path.isdir(BACKUP_DIR):
        return None
    cands = [f for f in os.listdir(BACKUP_DIR)
             if f.startswith(BOT + ".") and f.endswith(".bak")]
    if not cands:
        return None
    cands.sort(reverse=True)
    return os.path.join(BACKUP_DIR, cands[0])


def restore_full(backup):
    """Copy backup over the current file."""
    # Save a copy of the current state first (safety)
    if os.path.exists(BOT):
        safety = BOT + ".broken_" + str(int(os.path.getmtime(BOT)))
        shutil.copy2(BOT, safety)
        log(f"Current saved to: {safety}")
    shutil.copy2(backup, BOT)
    log(f"Restored from: {backup}")


def remove_inserted_block(source, start_marker, end_marker):
    """Remove a block of code between two markers (inclusive of start)."""
    i = source.find(start_marker)
    if i == -1:
        return source, False
    # Include any leading blank lines
    j = i
    while j > 0 and source[j - 1] in "\n\r":
        j -= 1
    k = source.find(end_marker, i)
    if k == -1:
        return source, False
    return source[:j] + source[k:], True


def remove_b1(source):
    """Remove _get_min_notional + cache."""
    start = "# ══ [MIN_NOTIONAL CACHE] ══"
    end = "# ════════════════════════════════════════════════════════════════\n# [LIQ AWARENESS]"
    if start not in source:
        return source, "not_found"
    i = source.find(start)
    # find preceding blank lines
    j = i
    while j > 0 and source[j - 1] in "\n\r":
        j -= 1
    # find the end (LIQ AWARENESS section header)
    k = source.find(end, i)
    if k == -1:
        # fallback: find "def _lv_preflight_check"
        k = source.find("def _lv_preflight_check", i)
        if k == -1:
            return source, "end_not_found"
    return source[:j] + "\n\n\n" + source[k:], "removed"


def remove_b2(source):
    """Remove the MIN-NOTIONAL CHECK block from place_pending_entry."""
    block = '''    # ══ [MIN-NOTIONAL CHECK] قبل إرسال الأمر ══
    _min_notional_actual = _get_min_notional(exchange, sym)
    _notional_est = float(qty) * float(target)
    if _notional_est < _min_notional_actual * 1.05:
        log.warning(
            f"[Pending] {sym} notional ${_notional_est:.2f} < "
            f"min ${_min_notional_actual:.2f} (x1.05 buffer) -- "
            f"refusing order"
        )
        return None

'''
    if block not in source:
        return source, "not_found"
    return source.replace(block, "", 1), "removed"


def remove_b3(source):
    """Revert the dynamic MIN_NOTIONAL check in run_live."""
    new_block = '''                    _min_notional_live = _get_min_notional(exchange, sym)
                    if qty * lmt < _min_notional_live * 1.05:
                        log.debug(
                            f"[Notional] {sym} too small: "
                            f"${qty*lmt:.2f} < ${_min_notional_live:.2f}"
                        )
                        continue'''
    old_block = '''                    if qty * lmt < cfg.MIN_NOTIONAL:
                        continue'''
    if new_block not in source:
        return source, "not_found"
    return source.replace(new_block, old_block, 1), "removed"


def remove_b4(source):
    """Remove the SAFETY check from _lv_ensure_protection."""
    block = '''    # ══ [SAFETY] تحقق من وجود المركز على البورصة قبل وضع أوامر حماية ══
    # testnet وبعض البيئات قد لا تفرض reduceOnly. نحمي أنفسنا.
    try:
        _pos_map = _lv_fetch_positions(exchange, [sym])
        if _pos_map is None:
            log.debug(f"[Prot] {sym} position check failed -- proceeding")
        elif sym not in _pos_map:
            log.warning(
                f"[Prot] {sym} no exchange position -- "
                f"skipping protective placement"
            )
            return
    except Exception as _e_pos:
        log.debug(f"[Prot] {sym} pre-check error: {_e_pos}")

'''
    if block not in source:
        return source, "not_found"
    return source.replace(block, "", 1), "removed"


def remove_b5(source):
    """Revert _lv_preflight_check to its original globals() guard."""
    new_block = '''    try:
        _min_notional = float(_get_min_notional(exchange, sym))
    except Exception:
        _min_notional = float(getattr(CFG, 'MIN_NOTIONAL', 5.0))'''
    old_block = '''    try:
        _min_notional = float(_get_min_notional(exchange, sym)) \\
            if '_get_min_notional' in globals() else 5.0
    except Exception:
        _min_notional = 5.0'''
    if new_block not in source:
        return source, "not_found"
    return source.replace(new_block, old_block, 1), "removed"


def main():
    if not os.path.exists(BOT):
        log(f"Not found: {BOT}")
        return 1

    # ── Strategy 1: full file restore from backup ──
    backup = find_backup()
    if backup:
        log(f"Latest backup: {backup}")
        ans = input("Restore full file from backup? [Y/n] ").strip().lower()
        if ans in ("", "y", "yes"):
            restore_full(backup)
            try:
                compile(open(BOT, encoding="utf-8").read(), BOT, "exec")
                log("Syntax check: OK")
                log("Done. Run: python trading_live_v2.py --help")
                return 0
            except SyntaxError as e:
                log(f"Syntax error after restore: {e}")
                return 2

    # ── Strategy 2: targeted removal ──
    log("No backup restore chosen — trying targeted removal")
    with open(BOT, encoding="utf-8") as f:
        src = f.read()

    actions = [
        ("B1", remove_b1),
        ("B2", remove_b2),
        ("B3", remove_b3),
        ("B4", remove_b4),
        ("B5", remove_b5),
    ]

    removed_count = 0
    for name, fn in actions:
        src, status = fn(src)
        log(f"  {name}: {status}")
        if status == "removed":
            removed_count += 1

    if removed_count == 0:
        log("Nothing to remove — patches may already be gone.")
        return 0

    # Syntax check
    try:
        compile(src, BOT, "exec")
        log("Syntax check: OK")
    except SyntaxError as e:
        log(f"Syntax error: {e}")
        log("Aborting — file unchanged.")
        return 3

    # Save
    tmp = BOT + ".rollback_tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src)
    os.replace(tmp, BOT)
    log(f"Wrote {BOT} ({removed_count} block(s) removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
