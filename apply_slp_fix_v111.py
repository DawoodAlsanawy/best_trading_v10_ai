#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_slp_fix_v111.py — إصلاح نهائي لـ apply_slp_patch.py
═══════════════════════════════════════════════════════════════════════════

يُصلح هذا السكريبت مشكلتين في apply_slp_patch.py:

    [FIX-A] patch 11 (slp_live_exposure): anchor بمسافة 20 بدل 36
            → في كل مرة يفشل مع anchor_not_found → abort
            → نُصلح بـ regex يُطابق أي مسافة

    [FIX-B] patch 9 (slp_live_monitor): unique_marker يُطابق دالة مساعدة
            → يُتخطّى بصمت → monitor لا يُضاف إلى run_live
            → نُغيّر marker إلى نص تعليق فريد

لا يُلمس trading_final.py إطلاقاً.

الاستخدام:
    python apply_slp_fix_v111.py --dry-run
    python apply_slp_fix_v111.py
    python apply_slp_fix_v111.py --verify-only
    python apply_slp_fix_v111.py --rollback

بعد التطبيق، نفّذ:
    python apply_slp_patch.py --dry-run     # يجب: كل 15 patch تنجح
    python apply_slp_patch.py               # تطبيق فعلي
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

TARGET = "apply_slp_patch.py"
FIX_VERSION = "1.1.1"
FIX_MANIFEST = ".slp_fix_v111.json"


# ═══════════════════════════════════════════════════════════════════════════
# FIX DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════
# كل إصلاح: pattern (regex يُطابق نصاً موجوداً) + replacement + marker (كشف تطبيق مسبق)
# نستخدم regex بدل string match لأننا لا نعرف عدد المسافات البادئة بدقة
# ═══════════════════════════════════════════════════════════════════════════

FIXES = [
    # ─── FIX-A: patch 11 anchor + payload indentation ───
    {
        "id": "fix_a_live_exposure",
        "description": "Fix slp_live_exposure: anchor and payload indentation (20→36 spaces)",
        # marker: نتحقق من أن الإصلاح مُطبَّق بالفعل
        "marker_check": lambda txt: bool(re.search(
            r'"anchor":\s*"\s{30,}_total_exposure = \(len\(_PENDING_ORDERS\)',
            txt
        )),
        # pattern: نُطابق patch 11 بأي مسافة بادئة حالية
        "pattern": re.compile(
            r'    \{\s*\n'
            r'        "id": "slp_live_exposure",.*?\n    \},',
            re.DOTALL
        ),
        # replacement: patch 11 بإصلاح indentation
        "replacement": (
            '    {\n'
            '        "id": "slp_live_exposure",\n'
            '        "description": "Include SLP orders in total exposure count",\n'
            '        "unique_marker": "len(_PENDING_ORDERS) + len(_SLP_ORDERS)",\n'
            '        "anchor": "                                    _total_exposure = (len(_PENDING_ORDERS)\\n                                                       + len(open_pos_live)\\n                                                       + len(_WATCHED_SIGNALS))\\n",\n'
            '        "position": "replace",\n'
            '        "payload": """                                    _total_exposure = (len(_PENDING_ORDERS)\n'
            '                                                       + len(open_pos_live)\n'
            '                                                       + len(_WATCHED_SIGNALS)\n'
            '                                                       + (len(_SLP_ORDERS)\n'
            "                                                          if getattr(CFG, 'SLP_ENABLED', False)\n"
            '                                                          else 0))\n'
            '""",\n'
            '    },'
        ),
    },

    # ─── FIX-B: patch 9 unique_marker (avoid collision with helper function def) ───
    {
        "id": "fix_b_live_monitor_marker",
        "description": "Fix slp_live_monitor: use unique marker (avoid helper def collision)",
        "marker_check": lambda txt: '# ══ [SLP] Smart Ladder Pending monitor ══' in txt,
        "pattern": re.compile(
            r'    \{\s*\n'
            r'        "id": "slp_live_monitor",.*?\n    \},',
            re.DOTALL
        ),
        "replacement": (
            '    {\n'
            '        "id": "slp_live_monitor",\n'
            '        "description": "Call SLP monitor in run_live loop",\n'
            '        "unique_marker": "# ══ [SLP] Smart Ladder Pending monitor ══",\n'
            '        "anchor": "            # ══ [Pending] Sweep pending orders every cycle ══\\n",\n'
            '        "position": "after",\n'
            '        "payload": """            # ══ [SLP] Smart Ladder Pending monitor ══\n'
            "            if getattr(CFG, 'SLP_ENABLED', False):\n"
            '                try:\n'
            '                    monitor_smart_ladder_pending(\n'
            "                        exchange, open_pos_live, loop_iter,\n"
            "                        assets=assets if 'assets' in dir() else None\n"
            '                    )\n'
            '                except Exception as _e:\n'
            '                    log.warning(f"[SLP] monitor error: {_e}")\n'
            '""",\n'
            '    },'
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def _file_hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def _atomic_write(path: str, content: str) -> None:
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


def _verify_syntax(content: str):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def _apply_fixes(content: str):
    """Return (new_content, applied, skipped, failed)."""
    applied = 0
    skipped = 0
    failed = []
    for fix in FIXES:
        # Check if already applied
        try:
            if fix["marker_check"](content):
                skipped += 1
                continue
        except Exception as e:
            failed.append((fix["id"], f"marker_error: {e}"))
            continue
        # Apply via regex
        pat = fix["pattern"]
        if not pat.search(content):
            failed.append((fix["id"], "pattern_not_found"))
            continue
        if len(pat.findall(content)) > 1:
            failed.append((fix["id"], "pattern_ambiguous"))
            continue
        new_content = pat.sub(fix["replacement"], content, count=1)
        if new_content == content:
            failed.append((fix["id"], "no_change_after_sub"))
            continue
        content = new_content
        applied += 1
    return content, applied, skipped, failed


def _load_manifest(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": FIX_VERSION, "backups": []}


def _save_manifest(path, manifest):
    _atomic_write(path, json.dumps(manifest, indent=2))


# ═══════════════════════════════════════════════════════════════════════════
# DIAGNOSTIC: verify all 15 patches will succeed against trading_final.py
# ═══════════════════════════════════════════════════════════════════════════

def _preflight_check(target_patch_file: str, trading_file: str = "trading_final.py"):
    """
    Parse PATCHES from apply_slp_patch.py, verify each anchor exists in
    trading_final.py. This catches anchor issues BEFORE running.
    """
    if not os.path.exists(trading_file):
        print(f"  ⚠ trading_final.py not found — skipping preflight")
        return True

    # Read PATCHES list by importing as a module (safe — no top-level exec)
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_slp_patch_mod", target_patch_file)
        mod = importlib.util.module_from_spec(spec)
        # Prevent main() from running (only define PATCHES)
        _orig_name = mod.__dict__.get("__name__", "")
        # Temporarily patch sys.argv to satisfy argparse if needed
        _orig_argv = sys.argv
        sys.argv = ["_dummy_", "--help"]
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.argv = _orig_argv
    except SystemExit:
        # argparse called exit(0) — but PATCHES should still be loaded
        pass
    except Exception as e:
        print(f"  ⚠ Import failed: {e}")
        return True

    patches = getattr(mod, "PATCHES", None)
    if patches is None:
        print(f"  ⚠ PATCHES list not found in module")
        return True

    with open(trading_file, "r", encoding="utf-8") as f:
        target_content = f.read()

    print(f"\n  Preflight anchor check against {trading_file}:")
    print(f"  {'#':<3} {'id':<28} {'status'}")
    print(f"  {'─'*3} {'─'*28} {'─'*30}")

    ok_count = 0
    fail_list = []
    for i, patch in enumerate(patches, 1):
        pid = patch.get("id", "?")
        pos = patch.get("position", "?")
        # Skip check if marker already present (will skip in apply)
        marker = patch.get("unique_marker", "")
        if marker and marker in target_content:
            print(f"  {i:<3} {pid:<28} [skip] marker present")
            ok_count += 1
            continue

        if pos == "replace":
            anchor = patch.get("anchor", "")
            if anchor in target_content:
                cnt = target_content.count(anchor)
                if cnt > 1:
                    print(f"  {i:<3} {pid:<28} ⚠ ambiguous ({cnt}x)")
                    fail_list.append((pid, f"ambiguous({cnt})"))
                else:
                    print(f"  {i:<3} {pid:<28} ✓ will apply")
                    ok_count += 1
            else:
                print(f"  {i:<3} {pid:<28} ✗ anchor not found")
                fail_list.append((pid, "anchor_not_found"))
        else:
            anchor = patch.get("anchor", "")
            if anchor in target_content:
                print(f"  {i:<3} {pid:<28} ✓ will apply")
                ok_count += 1
            else:
                print(f"  {i:<3} {pid:<28} ✗ anchor not found")
                fail_list.append((pid, "anchor_not_found"))

    print()
    if fail_list:
        print(f"  ✗ {len(fail_list)}/{len(patches)} patches will fail:")
        for pid, reason in fail_list:
            print(f"      {pid}: {reason}")
        return False
    print(f"  ✓ All {len(patches)} patches will succeed")
    return True


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="Fix apply_slp_patch.py (patch 11 anchor + patch 9 marker)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument("--file", default=TARGET,
                   help=f"Target patch script (default: {TARGET})")
    p.add_argument("--trading", default="trading_final.py",
                   help="Trading file for preflight check")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rollback", action="store_true")
    p.add_argument("--no-preflight", action="store_true",
                   help="Skip preflight anchor check")
    args = p.parse_args()

    if not os.path.exists(args.file):
        print(f"✗ Not found: {args.file}")
        return 1

    with open(args.file, "r", encoding="utf-8") as f:
        original = f.read()

    # Sanity check v1.0 + v1.1 are present
    _required = [
        '"id": "slp_live_exposure"',
        '"id": "slp_live_monitor"',
        'CONFIG_SLP_PAYLOAD',
        'HELPERS_SLP_PAYLOAD',
    ]
    _missing = [m for m in _required if m not in original]
    if _missing and not args.verify_only:
        print("✗ apply_slp_patch.py missing required markers:")
        for m in _missing:
            print(f"    · {m}")
        return 1

    print(f"Target:   {args.file}")
    print(f"Size:     {len(original):,} chars")
    print(f"Hash:     {_file_hash(original)}")
    print(f"Fixes:    {len(FIXES)}")
    print()

    # ── verify-only ──
    if args.verify_only:
        ok, err = _verify_syntax(original)
        print(f"Syntax: {'✓ valid' if ok else '✗ ' + err}")
        print()
        for fix in FIXES:
            try:
                applied = fix["marker_check"](original)
            except Exception:
                applied = False
            status = "✓ applied" if applied else "· not applied"
            print(f"  [{status}] {fix['id']}: {fix['description']}")
        return 0

    # ── rollback ──
    if args.rollback:
        manifest = _load_manifest(FIX_MANIFEST)
        backups = manifest.get("backups", [])
        if not backups:
            print("✗ No backups found")
            return 1
        latest = backups[-1]
        if not os.path.exists(latest):
            print(f"✗ Backup missing: {latest}")
            return 1
        shutil.copy2(latest, args.file)
        print(f"✓ Rolled back from {latest}")
        return 0

    # ── apply ──
    new_content, applied, skipped, failed = _apply_fixes(original)

    if failed:
        print(f"✗ {len(failed)} fix(es) failed:")
        for fid, st in failed:
            print(f"    {fid}: {st}")
        print("\n  No changes written.")
        return 1

    # Syntax check
    ok, err = _verify_syntax(new_content)
    if not ok:
        print(f"✗ Syntax error after fixes: {err}")
        print("  No changes written.")
        return 1

    print(f"✓ Applied: {applied}   Skipped: {skipped}")
    print(f"✓ Syntax valid")
    print()

    # Dry-run
    if args.dry_run:
        print("── DRY RUN — no files written ──")
        print(f"Would write: {args.file}")
        print(f"Size change: {len(original):,} → {len(new_content):,} "
              f"({len(new_content) - len(original):+,})")
        return 0

    # Backup + write
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{args.file}.v111_{ts}.bak"
    shutil.copy2(args.file, backup)
    print(f"Backup: {backup}")

    _atomic_write(args.file, new_content)
    print(f"✓ Wrote {args.file}")

    manifest = _load_manifest(FIX_MANIFEST)
    manifest["version"] = FIX_VERSION
    manifest["last_run"] = datetime.now().isoformat()
    manifest["backups"].append(backup)
    manifest["last_hash"] = _file_hash(new_content)
    _save_manifest(FIX_MANIFEST, manifest)

    # Preflight check against trading_final.py
    if not args.no_preflight:
        print()
        try:
            ok = _preflight_check(args.file, args.trading)
            if not ok:
                print()
                print("⚠ Preflight found issues. Rollback recommended:")
                print(f"    python {os.path.basename(__file__)} --rollback")
                return 2
        except Exception as e:
            print(f"⚠ Preflight failed: {e}")

    print()
    print("═" * 64)
    print(f"✓ SLP Fix v{FIX_VERSION} applied")
    print(f"  Backup: {backup}")
    print()
    print("الخطوات التالية:")
    print("  1. python apply_slp_patch.py --dry-run     # كل 15 patch تنجح")
    print("  2. python apply_slp_patch.py               # تطبيق على trading")
    print("  3. python trading_final.py [args] --analytics   # baseline")
    print("  4. python trading_final.py [args] --slp --analytics")
    print()
    print("التراجع:")
    print(f"  python {os.path.basename(__file__)} --rollback")
    print(f"  python apply_slp_patch.py --rollback")
    print("═" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ═══════════════════════════════════════════════════════════════════════════
# CHANGELOG
# ═══════════════════════════════════════════════════════════════════════════
"""
v1.1.1 (هذا الإصدار):
  [+] FIX-A: patch 11 (slp_live_exposure) — يستخدم regex بدل string anchor
             → يطابق أي indentation حالية ويستبدلها بـ 36/55 الصحيحة
  [+] FIX-B: patch 9 (slp_live_monitor) — unique_marker جديد
             → يستخدم "# ══ [SLP] Smart Ladder Pending monitor ══"
             → لا يتعارض مع دالة monitor_smart_ladder_pending المساعدة
  [+] preflight check يتحقق من نجاح جميع الـ 15 patch قبل التطبيق الفعلي

v1.1.0 (السابق):
  [+] إصلاح anchor patch 3 (AFTER PARITY)
  [+] إضافة v11_simulate_branch + v11_position_meta
  [+] إصلاح _slp_write_stats
  [+] إصلاح time-decay في backtest
  [+] إضافة _slp_startup_recover
  [+] conflict guard
  [+] --clear-cache stats

v1.0.0:
  الإصدار الأول (يحتوي على bugين حرجين: patch 11 anchor، patch 9 marker)
"""
