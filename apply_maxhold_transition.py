#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_maxhold_transition.py — MAX_HOLD Behavior Transition Patch
═══════════════════════════════════════════════════════════════════════════════

المطلوب:
  عند انتهاء MAX_HOLD بدل الإغلاق الفوري:
    • إذا كانت الصفقة في خسارة → تفعيل BEEsc (نقل TP إلى نقطة الدخول)
    • إذا كانت الصفقة في ربح   → تفعيل trailing فوراً من السعر الحالي

يعمل في backtest و live بنفس المنطق.
الافتراضي: مُفعَّل (MAXHOLD_TRANSITION_ENABLED = True)
للتعطيل: --no-maxhold-transition

═══════════════════════════════════════════════════════════════════════════════

الاستخدام:
    python apply_maxhold_transition.py --dry-run       # معاينة
    python apply_maxhold_transition.py                 # تطبيق
    python apply_maxhold_transition.py --verify-only   # تحقق
    python apply_maxhold_transition.py --rollback      # تراجع

بعد التطبيق:
    # نفس أمرك الحالي — لا تحتاج أي flag إضافي
    python trading_final.py [args] --analytics

    # لتعطيل السلوك الجديد (الرجوع للإغلاق الفوري):
    python trading_final.py [args] --no-maxhold-transition
"""

import argparse
import ast
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

TARGET = "trading_final.py"
PATCH_VERSION = "1.0.0"
MANIFEST = ".maxhold_transition_patches.json"


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG FIELD
# ═══════════════════════════════════════════════════════════════════════════

CONFIG_PAYLOAD = '''
    # ══ [MAXHOLD-TRANSITION] ══
    # عند انتهاء MAX_HOLD بدل إغلاق الصفقة فوراً:
    #   - إذا في خسارة: نقل TP إلى نقطة الدخول (BEEsc)
    #   - إذا في ربح:  تفعيل trailing فوراً من السعر الحالي
    MAXHOLD_TRANSITION_ENABLED: bool = True
    # ══ [MAXHOLD-TRANSITION end] ══
'''


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST — MaxHold block replacement (in _advance)
# ═══════════════════════════════════════════════════════════════════════════

BACKTEST_MAXHOLD_OLD = '''        # 3. MaxHold (close-based)
        # ══ [TF-FIX] scale bar-count to preserve real-time duration ══
        if cidx - pos.entry_ci > effective_bars(CFG.MAX_HOLD_BARS):
            pos.trail_sl = trail_sl; pos.current_ci = cidx
            return p, "MaxHold", cidx
'''

BACKTEST_MAXHOLD_NEW = '''        # 3. MaxHold with transition (BEEsc in loss / trailing in profit)
        # ══ [TF-FIX] scale bar-count to preserve real-time duration ══
        # ══ [MAXHOLD-TRANSITION] ══
        if cidx - pos.entry_ci > effective_bars(CFG.MAX_HOLD_BARS):
            if getattr(CFG, 'MAXHOLD_TRANSITION_ENABLED', True):
                if not getattr(pos, '_maxhold_transitioned', False):
                    _mh_pnl = ((p - pos.entry_px) / pos.entry_px
                               if sig.action == "BUY"
                               else (pos.entry_px - p) / pos.entry_px)
                    if _mh_pnl <= 0:
                        _mh_g = (float(getattr(
                            CFG, 'BREAKEVEN_ESCAPE_MIN_PROFIT_R', 0.0))
                            * pos.sl_dist_initial)
                        if sig.action == "BUY":
                            _mh_tp = pos.entry_px + _mh_g
                            if _mh_tp < float(sig.tp1):
                                pos._be_orig_tp1 = float(sig.tp1)
                                sig.tp1 = _mh_tp
                                pos._be_esc_done = True
                                pos._be_cancelled = False
                                pos._be_low = float(p)
                                log.info(
                                    f"[MaxHold-BEEsc-BT] {sig.symbol} "
                                    f"{sig.action} loss={_mh_pnl*100:.2f}% "
                                    f"TP={_mh_tp:.6f}")
                        else:
                            _mh_tp = pos.entry_px - _mh_g
                            if _mh_tp > float(sig.tp1):
                                pos._be_orig_tp1 = float(sig.tp1)
                                sig.tp1 = _mh_tp
                                pos._be_esc_done = True
                                pos._be_cancelled = False
                                pos._be_high = float(p)
                                log.info(
                                    f"[MaxHold-BEEsc-BT] {sig.symbol} "
                                    f"{sig.action} loss={_mh_pnl*100:.2f}% "
                                    f"TP={_mh_tp:.6f}")
                    else:
                        if sig.action == "BUY":
                            _mh_pk = max(float(getattr(
                                pos, 'peak_price', pos.entry_px)), float(p))
                        else:
                            _mh_pk = min(float(getattr(
                                pos, 'peak_price', pos.entry_px)), float(p))
                        pos.peak_price = _mh_pk
                        if pos.sl_dist_initial > 0:
                            if sig.action == "BUY":
                                _mh_R = (_mh_pk - pos.entry_px) / pos.sl_dist_initial
                            else:
                                _mh_R = (pos.entry_px - _mh_pk) / pos.sl_dist_initial
                            pos.trail_peak_R = max(float(getattr(
                                pos, 'trail_peak_R', 0.0)), _mh_R)
                        pos._maxhold_trail_immediate = True
                        log.info(
                            f"[MaxHold-Trail-BT] {sig.symbol} {sig.action} "
                            f"profit={_mh_pnl*100:.2f}% peak={_mh_pk:.6f} "
                            f"trailing activated")
                        if not getattr(CFG, 'TRAIL_ENABLED', True):
                            log.warning(
                                f"[MaxHold-Trail-BT] {sig.symbol} "
                                f"TRAIL_ENABLED=False - trailing will "
                                f"not activate")
                    pos._maxhold_transitioned = True
                # Continue - do NOT close
            else:
                pos.trail_sl = trail_sl; pos.current_ci = cidx
                return p, "MaxHold", cidx
'''


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST — Trailing activation override (sub-bar mode)
# ═══════════════════════════════════════════════════════════════════════════

BACKTEST_SUBBAR_OLD = '''                _ta_eff = _sl_frac_init * _act_at_r
                if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:
'''

BACKTEST_SUBBAR_NEW = '''                _ta_eff = _sl_frac_init * _act_at_r
                if getattr(pos, '_maxhold_trail_immediate', False):
                    _ta_eff = 0.0
                if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:
'''


# ═══════════════════════════════════════════════════════════════════════════
# BACKTEST — Trailing activation override (main-bar mode)
# ═══════════════════════════════════════════════════════════════════════════

BACKTEST_MAINBAR_OLD = '''            _ta_eff = _sl_frac_init * _act_at_r
            if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:
'''

BACKTEST_MAINBAR_NEW = '''            _ta_eff = _sl_frac_init * _act_at_r
            if getattr(pos, '_maxhold_trail_immediate', False):
                _ta_eff = 0.0
            if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:
'''


# ═══════════════════════════════════════════════════════════════════════════
# LIVE — MaxHold block replacement
# ═══════════════════════════════════════════════════════════════════════════

LIVE_MAXHOLD_OLD = '''                        if bars_held > effective_bars(cfg.MAX_HOLD_BARS):
                            ex = True
                            rsn = f"MaxHold({int(bars_held)}bars)"
'''

LIVE_MAXHOLD_NEW = '''                        if bars_held > effective_bars(cfg.MAX_HOLD_BARS):
                            if getattr(CFG, 'MAXHOLD_TRANSITION_ENABLED', True):
                                if not pos.get('_maxhold_transitioned', False):
                                    _mh_e = float(pos.get('entry', 0) or 0)
                                    _mh_sd = float(pos.get('sl_dist_initial', 0) or 0)
                                    _mh_a = str(pos.get('action', 'BUY'))
                                    if _mh_e > 0:
                                        _mh_pnl = ((price - _mh_e) / _mh_e
                                                   if _mh_a == 'BUY'
                                                   else (_mh_e - price) / _mh_e)
                                        if _mh_pnl <= 0:
                                            _mh_g = (float(getattr(
                                                CFG, 'BREAKEVEN_ESCAPE_MIN_PROFIT_R', 0.0))
                                                * _mh_sd)
                                            _mh_tp_cur = float(pos.get('tp1', 0) or 0)
                                            if _mh_a == 'BUY':
                                                _mh_tp = _mh_e + _mh_g
                                                _mh_ok = ((_mh_tp < _mh_tp_cur)
                                                          if _mh_tp_cur > 0 else True)
                                            else:
                                                _mh_tp = _mh_e - _mh_g
                                                _mh_ok = ((_mh_tp > _mh_tp_cur)
                                                          if _mh_tp_cur > 0 else True)
                                            if _mh_ok:
                                                pos['_be_orig_tp1'] = _mh_tp_cur
                                                pos['tp1'] = _mh_tp
                                                pos['_be_esc_done'] = True
                                                pos['_be_cancelled'] = False
                                                if _mh_a == 'BUY':
                                                    pos.setdefault('_be_low', float(price))
                                                else:
                                                    pos.setdefault('_be_high', float(price))
                                                log.info(
                                                    f"[MaxHold-BEEsc-LV] {sym} "
                                                    f"{_mh_a} loss={_mh_pnl*100:.2f}% "
                                                    f"TP={_mh_tp:.6f}")
                                                if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
                                                    try:
                                                        _sync_protective_orders(exchange, sym, pos)
                                                    except Exception as _e_mh:
                                                        log.debug(
                                                            f"[MaxHold-BEEsc-LV] "
                                                            f"prot sync: {_e_mh}")
                                        else:
                                            _mh_pk_cur = float(pos.get('peak_price', _mh_e))
                                            if _mh_a == 'BUY':
                                                _mh_pk = max(_mh_pk_cur, float(price))
                                            else:
                                                _mh_pk = min(_mh_pk_cur, float(price))
                                            pos['peak_price'] = _mh_pk
                                            if _mh_sd > 0:
                                                if _mh_a == 'BUY':
                                                    _mh_R = (_mh_pk - _mh_e) / _mh_sd
                                                else:
                                                    _mh_R = (_mh_e - _mh_pk) / _mh_sd
                                                pos['_trail_peak_R'] = max(
                                                    float(pos.get('_trail_peak_R', 0) or 0),
                                                    _mh_R)
                                            pos['_maxhold_trail_immediate'] = True
                                            log.info(
                                                f"[MaxHold-Trail-LV] {sym} "
                                                f"{_mh_a} profit={_mh_pnl*100:.2f}% "
                                                f"peak={_mh_pk:.6f} "
                                                f"trailing activated")
                                            if not getattr(CFG, 'TRAIL_ENABLED', True):
                                                log.warning(
                                                    f"[MaxHold-Trail-LV] {sym} "
                                                    f"TRAIL_ENABLED=False - "
                                                    f"trailing will not activate")
                                        pos['_maxhold_transitioned'] = True
                                        try:
                                            _lv_save_state(state_file, open_pos_live)
                                        except Exception:
                                            pass
                            else:
                                ex = True
                                rsn = f"MaxHold({int(bars_held)}bars)"
'''


# ═══════════════════════════════════════════════════════════════════════════
# LIVE — Trailing activation override
# ═══════════════════════════════════════════════════════════════════════════

LIVE_TRAIL_OLD = '''                        _act_at_r = float(getattr(
                            CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
                        _ta = _sl_frac_init * _act_at_r
'''

LIVE_TRAIL_NEW = '''                        _act_at_r = float(getattr(
                            CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
                        _ta = _sl_frac_init * _act_at_r
                        if pos.get('_maxhold_trail_immediate', False):
                            _ta = 0.0
'''


# ═══════════════════════════════════════════════════════════════════════════
# CLI FLAG
# ═══════════════════════════════════════════════════════════════════════════

CLI_FLAG_PAYLOAD = '''
    p.add_argument("--no-maxhold-transition", action="store_true",
                   help="Disable MAX_HOLD transition "
                        "(revert to immediate close at expiry)")
'''


# ═══════════════════════════════════════════════════════════════════════════
# CLI PROCESS
# ═══════════════════════════════════════════════════════════════════════════

CLI_PROCESS_PAYLOAD = '''
    # ══ [MAXHOLD-TRANSITION] process CLI flag ══
    if getattr(args, "no_maxhold_transition", False):
        CFG.MAXHOLD_TRANSITION_ENABLED = False
        log.info("[MaxHold] transition DISABLED - legacy close-at-expiry")
    else:
        log.info(
            f"[MaxHold] transition ENABLED (loss->BEEsc, profit->trailing) "
            f"max_hold={CFG.MAX_HOLD_BARS}h")
'''


# ═══════════════════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════════════════

PATCHES = [
    {
        "id": "mht_config",
        "description": "Add MAXHOLD_TRANSITION_ENABLED config field",
        "unique_marker": "MAXHOLD_TRANSITION_ENABLED: bool = True",
        "anchor": "    MAX_HOLD_BARS: int = 2000\n",
        "position": "after",
        "payload": CONFIG_PAYLOAD,
    },
    {
        "id": "mht_backtest_block",
        "description": "Replace backtest MaxHold close with transition logic",
        "unique_marker": "# ══ [MAXHOLD-TRANSITION] ══",
        "anchor": BACKTEST_MAXHOLD_OLD,
        "position": "replace",
        "payload": BACKTEST_MAXHOLD_NEW,
    },
    {
        "id": "mht_backtest_subbar_gate",
        "description": "Override trailing activation gate (sub-bar mode)",
        "unique_marker": "_maxhold_trail_immediate', False):\n                    _ta_eff = 0.0",
        "anchor": BACKTEST_SUBBAR_OLD,
        "position": "replace",
        "payload": BACKTEST_SUBBAR_NEW,
    },
    {
        "id": "mht_backtest_mainbar_gate",
        "description": "Override trailing activation gate (main-bar mode)",
        "unique_marker": "_maxhold_trail_immediate', False):\n                _ta_eff = 0.0",
        "anchor": BACKTEST_MAINBAR_OLD,
        "position": "replace",
        "payload": BACKTEST_MAINBAR_NEW,
    },
    {
        "id": "mht_live_block",
        "description": "Replace live MaxHold close with transition logic",
        "unique_marker": "# [MaxHold-BEEsc-LV]",
        "anchor": LIVE_MAXHOLD_OLD,
        "position": "replace",
        "payload": LIVE_MAXHOLD_NEW,
    },
    {
        "id": "mht_live_trail_gate",
        "description": "Override live trailing activation gate",
        "unique_marker": "if pos.get('_maxhold_trail_immediate', False):\n                            _ta = 0.0",
        "anchor": LIVE_TRAIL_OLD,
        "position": "replace",
        "payload": LIVE_TRAIL_NEW,
    },
    {
        "id": "mht_cli_flag",
        "description": "Add --no-maxhold-transition CLI flag",
        "unique_marker": 'p.add_argument("--no-maxhold-transition"',
        "anchor": '    p.add_argument("--max-hold",    type=int,   default=None)\n',
        "position": "after",
        "payload": CLI_FLAG_PAYLOAD,
    },
    {
        "id": "mht_cli_process",
        "description": "Process MAXHOLD transition CLI flag",
        "unique_marker": "CFG.MAXHOLD_TRANSITION_ENABLED = False",
        "anchor": "    if args.max_hold  is not None: CFG.MAX_HOLD_BARS = args.max_hold\n",
        "position": "after",
        "payload": CLI_PROCESS_PAYLOAD,
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def _file_hash(s):
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _atomic_write(path, content):
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _verify_syntax(content):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def _apply_single(content, patch):
    if patch["unique_marker"] in content:
        return content, "already_applied"
    anchor = patch["anchor"]
    pos = patch["position"]
    if pos == "replace":
        cnt = content.count(anchor)
        if cnt == 0:
            return content, "anchor_not_found"
        if cnt > 1:
            return content, f"ambiguous({cnt})"
        return content.replace(anchor, patch["payload"], 1), "applied"
    idx = content.find(anchor)
    if idx < 0:
        return content, "anchor_not_found"
    cnt = content.count(anchor)
    if cnt > 1:
        return content, f"ambiguous({cnt})"
    if pos == "before":
        return content[:idx] + patch["payload"] + content[idx:], "applied"
    if pos == "after":
        end = idx + len(anchor)
        return content[:end] + patch["payload"] + content[end:], "applied"
    return content, f"bad_position:{pos}"


def _load_manifest(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": PATCH_VERSION, "applied": [], "backups": []}


def _save_manifest(path, manifest):
    _atomic_write(path, json.dumps(manifest, indent=2))


def _preflight(content):
    issues = []
    for i, patch in enumerate(PATCHES, 1):
        if patch["unique_marker"] in content:
            continue
        anchor = patch["anchor"]
        cnt = content.count(anchor)
        if cnt == 0:
            issues.append((i, patch["id"], "anchor_not_found"))
        elif cnt > 1:
            issues.append((i, patch["id"], f"ambiguous({cnt})"))
    return issues


def main():
    p = argparse.ArgumentParser(
        description="MAX_HOLD Behavior Transition Patch",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument("--file", default=TARGET)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    if not os.path.exists(args.file):
        print(f"✗ Not found: {args.file}")
        return 1

    with open(args.file, "r", encoding="utf-8") as f:
        original = f.read()

    print(f"Target:     {args.file}")
    print(f"Size:       {len(original):,} chars")
    print(f"Hash:       {_file_hash(original)}")
    print(f"Patches:    {len(PATCHES)}")
    print()

    if args.verify_only:
        ok, err = _verify_syntax(original)
        print(f"Syntax: {'✓ valid' if ok else '✗ ' + err}")
        print()
        for i, patch in enumerate(PATCHES, 1):
            present = patch["unique_marker"] in original
            mark = "✓ applied" if present else "·  pending"
            print(f"  [{mark:10s}] {i}. {patch['id']}")
        return 0

    if args.rollback:
        manifest = _load_manifest(MANIFEST)
        backups = manifest.get("backups", [])
        if not backups:
            print("✗ No backups found")
            return 1
        latest = backups[-1]
        if not os.path.exists(latest):
            print(f"✗ Backup missing: {latest}")
            return 1
        shutil.copy2(latest, args.file)
        manifest["applied"] = []
        _save_manifest(MANIFEST, manifest)
        print(f"✓ Rolled back from {latest}")
        return 0

    # Preflight
    issues = _preflight(original)
    if issues:
        print("✗ Preflight detected issues:")
        for i, pid, reason in issues:
            print(f"    [{i}] {pid}: {reason}")
        print("\n  No changes written.")
        return 1
    print("✓ Preflight: all anchors present and unique")

    # Apply
    manifest = _load_manifest(MANIFEST)
    already = set(manifest.get("applied", []))
    current = original
    applied_n = 0
    skipped_n = 0
    failed = []

    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        if pid in already and not args.force:
            skipped_n += 1
            if args.verbose:
                print(f"[{i}/{len(PATCHES)}] SKIP  {pid}")
            continue
        new_content, status = _apply_single(current, patch)
        if status == "applied":
            current = new_content
            applied_n += 1
            print(f"[{i}/{len(PATCHES)}] ✓ APPLY {pid}")
        elif status == "already_applied":
            skipped_n += 1
            if args.verbose:
                print(f"[{i}/{len(PATCHES)}] SKIP  {pid}")
        else:
            failed.append((pid, status))
            print(f"[{i}/{len(PATCHES)}] ✗ FAIL  {pid}: {status}")

    if failed:
        print()
        print(f"✗ {len(failed)} patch(es) failed. No changes written.")
        for pid, st in failed:
            print(f"    {pid}: {st}")
        return 1

    ok, err = _verify_syntax(current)
    if not ok:
        print(f"\n✗ Syntax error after patching: {err}")
        print("  No changes written.")
        return 1
    print(f"\n✓ Syntax valid ({applied_n} applied, {skipped_n} skipped)")

    if args.dry_run:
        print()
        print("── DRY RUN — no files written ──")
        print(f"Would write: {args.file}")
        print(f"Size change: {len(original):,} → {len(current):,} "
              f"({len(current) - len(original):+,})")
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{args.file}.preMHT_{ts}.bak"
    shutil.copy2(args.file, backup)
    print(f"Backup: {backup}")

    _atomic_write(args.file, current)
    print(f"✓ Wrote {args.file}")

    for patch in PATCHES:
        if patch["id"] not in manifest["applied"]:
            manifest["applied"].append(patch["id"])
    manifest["backups"].append(backup)
    manifest["version"] = PATCH_VERSION
    manifest["last_run"] = datetime.now().isoformat()
    manifest["last_hash"] = _file_hash(current)
    _save_manifest(MANIFEST, manifest)

    print()
    print("═" * 68)
    print(f"✓ MAXHOLD-Transition v{PATCH_VERSION} applied successfully")
    print(f"  Backup:   {backup}")
    print(f"  Manifest: {MANIFEST}")
    print()
    print("السلوك الجديد عند MAX_HOLD expiry:")
    print("  • إذا في خسارة  → TP يُنقل إلى نقطة الدخول (BEEsc)")
    print("  • إذا في ربح    → trailing يُفعَّل فوراً من السعر الحالي")
    print("  • لا إغلاق قهري — الصفقة تستمر مع الإدارة الجديدة")
    print()
    print("اختبار:")
    print("  python trading_final.py [أمرك] --analytics")
    print()
    print("معاينة السلوك في الـ log:")
    print("  ابحث عن: [MaxHold-BEEsc-BT] أو [MaxHold-Trail-BT]")
    print("  (backtest) [MaxHold-BEEsc-LV] أو [MaxHold-Trail-LV] (live)")
    print()
    print("تعطيل السلوك الجديد (الرجوع للإغلاق الفوري):")
    print("  python trading_final.py [أمرك] --no-maxhold-transition")
    print()
    print("تراجع كامل:")
    print("  python apply_maxhold_transition.py --rollback")
    print("═" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
