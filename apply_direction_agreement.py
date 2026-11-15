#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_direction_agreement.py — Direction Agreement Filter Patch
═══════════════════════════════════════════════════════════════════════════

المطلوب:
    البوت يحدد الاتجاه بطريقتين:
      • z_dev (mean reversion)  — الطريقة الحالية
      • geodesic_accel         — المحرك الجيوديسي
    
    لا يوضع أمر دخول إلا إذا اتفق الاثنان على نفس الاتجاه.

المنطق:
    BUY  مطلوب: z_dev < 0  AND  geo_accel_z > min_z
    SELL مطلوب: z_dev > 0  AND  geo_accel_z < -min_z

    حيث geo_accel_z = geo_accel[fi] / std(geo_accel[fi-lb:fi+1])

═══════════════════════════════════════════════════════════════════════════

الاستخدام:
    python apply_direction_agreement.py --dry-run
    python apply_direction_agreement.py
    python apply_direction_agreement.py --verify-only
    python apply_direction_agreement.py --rollback

    # بعد التطبيق، نفس أمرك الحالي بدون أي تعديل:
    python3 trading_geo.py --mode backtest [أمرك]

    # للتشديد (جودة أعلى، إشارات أقل):
    python3 trading_geo.py --mode backtest [أمرك] --agreement-min-z 0.3

    # للتخفيف (إذا رفض إشارات كثيرة):
    python3 trading_geo.py --mode backtest [أمرك] --agreement-min-z -0.2

    # لتعطيل الفلتر:
    python3 trading_geo.py --mode backtest [أمرك] --no-agreement

    # لتشخيص أسباب الرفض:
    python3 trading_geo.py --mode backtest [أمرك] --agreement-log-rejections
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

TARGET = "trading_geo.py"
PATCH_VERSION = "1.0.0"
MANIFEST = ".direction_agreement_patches.json"


# ═══════════════════════════════════════════════════════════════════════════
# PAYLOADS
# ═══════════════════════════════════════════════════════════════════════════

CONFIG_PAYLOAD = '''
    # ══ [AGREEMENT] Direction Agreement: z_dev + geodesic_accel ══
    # لا يوضع أمر دخول إلا إذا اتفق كلا الطريقتين على نفس الاتجاه
    # AGREEMENT_MIN_ACCEL_Z:
    #   0.0  → sign only (accel > 0 for BUY, < 0 for SELL)
    #   0.3  → stricter (0.3 std in right direction)
    #  -0.3  → lenient (allows 0.3 std against)
    AGREEMENT_REQUIRED: bool = True
    AGREEMENT_MIN_ACCEL_Z: float = 0.0
    AGREEMENT_LOOKBACK: int = 100
    AGREEMENT_LOG_REJECTIONS: bool = False
    # ══ [AGREEMENT end] ══
'''


HELPER_PAYLOAD = '''# ═══════════════════════════════════════════════════════════════════════════
# [AGREEMENT] Direction Agreement Filter — global stats
# ═══════════════════════════════════════════════════════════════════════════

_AGREEMENT_STATS: Dict = {
    "total": 0,
    "passed": 0,
    "rejected": 0,
    "by_action": {"BUY": 0, "SELL": 0},
}


def _agreement_reset_stats():
    _AGREEMENT_STATS["total"] = 0
    _AGREEMENT_STATS["passed"] = 0
    _AGREEMENT_STATS["rejected"] = 0
    _AGREEMENT_STATS["by_action"]["BUY"] = 0
    _AGREEMENT_STATS["by_action"]["SELL"] = 0


# ═══════════════════════════════════════════════════════════════════════════

'''


BUILD_SIGNALS_ANCHOR = '''            action = "BUY" if _z_dev < 0 else "SELL"

            # ══ [SELL-RND] بوابة SELL المستقلة ══
'''

BUILD_SIGNALS_REPLACEMENT = '''            action = "BUY" if _z_dev < 0 else "SELL"

            # ══ [AGREEMENT] Direction agreement: z_dev + geodesic_accel ══
            # كلا الطريقتين يجب أن تتفقا على الاتجاه قبل وضع أي أمر دخول
            if getattr(CFG, 'AGREEMENT_REQUIRED', True):
                _ag_geo_a = float(ad.geodesic_accel[fi])
                _ag_lb = int(getattr(CFG, 'AGREEMENT_LOOKBACK', 100))
                _ag_start = max(0, fi - _ag_lb)
                _ag_win = ad.geodesic_accel[_ag_start:fi + 1]
                _ag_std = float(np.std(_ag_win)) + 1e-9
                _ag_z = _ag_geo_a / _ag_std
                _ag_min = float(getattr(CFG, 'AGREEMENT_MIN_ACCEL_Z', 0.0))
                _ag_ok = False
                if action == "BUY" and _ag_z > _ag_min:
                    _ag_ok = True
                elif action == "SELL" and _ag_z < -_ag_min:
                    _ag_ok = True
                _AGREEMENT_STATS["total"] += 1
                if not _ag_ok:
                    _AGREEMENT_STATS["rejected"] += 1
                    _AGREEMENT_STATS["by_action"][action] += 1
                    if getattr(CFG, 'AGREEMENT_LOG_REJECTIONS', False):
                        log.debug(
                            f"[Agreement] {sym} {action} rejected: "
                            f"z_dev={_z_dev:+.2f} but "
                            f"geo_accel_z={_ag_z:+.3f} "
                            f"(threshold={_ag_min:+.2f})")
                    continue
                _AGREEMENT_STATS["passed"] += 1

            # ══ [SELL-RND] بوابة SELL المستقلة ══
'''


CLI_FLAGS_PAYLOAD = '''
    # ══ [AGREEMENT] CLI flags ══
    p.add_argument("--no-agreement", action="store_true",
                   help="Disable direction agreement filter "
                        "(z_dev + geo_accel)")
    p.add_argument("--agreement-min-z", type=float, default=None,
                   help="Minimum accel_z for agreement "
                        "(default 0.0; use 0.3 for stricter, "
                        "-0.2 for lenient)")
    p.add_argument("--agreement-lookback", type=int, default=None,
                   help="Window for accel normalization (default 100)")
    p.add_argument("--agreement-log-rejections", action="store_true",
                   help="Log each agreement rejection at DEBUG level")

'''


CLI_PROCESS_PAYLOAD = '''
    # ══ [AGREEMENT] process CLI flags ══
    if getattr(args, "no_agreement", False):
        CFG.AGREEMENT_REQUIRED = False
    if getattr(args, "agreement_min_z", None) is not None:
        CFG.AGREEMENT_MIN_ACCEL_Z = float(args.agreement_min_z)
    if getattr(args, "agreement_lookback", None) is not None:
        CFG.AGREEMENT_LOOKBACK = int(args.agreement_lookback)
    if getattr(args, "agreement_log_rejections", False):
        CFG.AGREEMENT_LOG_REJECTIONS = True
    if CFG.AGREEMENT_REQUIRED:
        log.info(
            f"[Agreement] ENABLED: both z_dev and geodesic_accel "
            f"must agree (min_accel_z={CFG.AGREEMENT_MIN_ACCEL_Z:+.2f}, "
            f"lookback={CFG.AGREEMENT_LOOKBACK})")
    else:
        log.info("[Agreement] DISABLED — direction determined by z_dev only")

'''


REPORT_PAYLOAD = '''
    # ══ [AGREEMENT] summary report ══
    if getattr(CFG, 'AGREEMENT_REQUIRED', True):
        _ag_tot = _AGREEMENT_STATS['total']
        if _ag_tot > 0:
            _ag_p = _AGREEMENT_STATS['passed']
            _ag_r = _AGREEMENT_STATS['rejected']
            _ag_buy_r = _AGREEMENT_STATS['by_action']['BUY']
            _ag_sell_r = _AGREEMENT_STATS['by_action']['SELL']
            log.info(
                f"[Agreement] passed={_ag_p:,} "
                f"rejected={_ag_r:,} ({100.0*_ag_r/_ag_tot:.1f}%) "
                f"[BUY_rej={_ag_buy_r}, SELL_rej={_ag_sell_r}]")
'''


# ═══════════════════════════════════════════════════════════════════════════
# PATCHES — جميع anchors تم التحقق منها على trading_geo.py
# ═══════════════════════════════════════════════════════════════════════════

PATCHES = [
    # 1. Config: after CONFIRM_KAPPA
    {
        "id": "ag_config",
        "description": "Add AGREEMENT config fields after CONFIRM_KAPPA",
        "unique_marker": "AGREEMENT_REQUIRED: bool = True",
        "anchor": "    CONFIRM_KAPPA: float = 0.20\n",
        "position": "after",
        "payload": CONFIG_PAYLOAD,
    },

    # 2. Helper functions: before build_signals
    {
        "id": "ag_helpers",
        "description": "Add _AGREEMENT_STATS + reset before build_signals",
        "unique_marker": "def _agreement_reset_stats():",
        "anchor": 'def build_signals(assets, mode="backtest"):',
        "position": "before",
        "payload": HELPER_PAYLOAD + "\n",
    },

    # 3. build_signals integration: replace action line + SELL-RND comment
    {
        "id": "ag_build_signals",
        "description": "Insert direction agreement check after action determination",
        "unique_marker": "# ══ [AGREEMENT] Direction agreement: z_dev + geodesic_accel ══",
        "anchor": BUILD_SIGNALS_ANCHOR,
        "position": "replace",
        "payload": BUILD_SIGNALS_REPLACEMENT,
    },

    # 4. CLI flags: before args = p.parse_args()
    {
        "id": "ag_cli_flags",
        "description": "Add AGREEMENT CLI flags",
        "unique_marker": 'p.add_argument("--no-agreement"',
        "anchor": "    args = p.parse_args()\n",
        "position": "before",
        "payload": CLI_FLAGS_PAYLOAD + "\n",
    },

    # 5. CLI processing: after numba
    {
        "id": "ag_cli_process",
        "description": "Process AGREEMENT CLI flags in main()",
        "unique_marker": "CFG.AGREEMENT_REQUIRED = False",
        "anchor": "    if args.no_numba: CFG.NUMBA_ENABLED = False\n",
        "position": "after",
        "payload": CLI_PROCESS_PAYLOAD,
    },

    # 6. Reset stats: after _filter_reset_stats()
    {
        "id": "ag_reset_stats",
        "description": "Reset AGREEMENT stats before build_signals",
        "unique_marker": "_agreement_reset_stats()",
        "anchor": (
            "    # ══ [FILTER] إعادة تعيين العدّاد قبل البناء ══\n"
            "    _filter_reset_stats()\n"
        ),
        "position": "after",
        "payload": (
            "    if getattr(CFG, 'AGREEMENT_REQUIRED', True):\n"
            "        _agreement_reset_stats()\n"
        ),
    },

    # 7. Report: after last line of run_backtest
    {
        "id": "ag_report",
        "description": "Log AGREEMENT summary at end of backtest",
        "unique_marker": "# ══ [AGREEMENT] summary report ══",
        "anchor": '        log.warning(f"[Diagnostic] HIGH REVERSAL RATE: {reversals}/{len(trades)}")\n',
        "position": "after",
        "payload": REPORT_PAYLOAD,
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
    cnt = content.count(anchor)
    if cnt == 0:
        return content, "anchor_not_found"
    if cnt > 1:
        return content, f"ambiguous({cnt})"
    if pos == "before":
        idx = content.find(anchor)
        return content[:idx] + patch["payload"] + content[idx:], "applied"
    if pos == "after":
        idx = content.find(anchor) + len(anchor)
        return content[:idx] + patch["payload"] + content[idx:], "applied"
    if pos == "replace":
        return content.replace(anchor, patch["payload"], 1), "applied"
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
    """Verify ALL anchors present and unique BEFORE writing anything."""
    issues = []
    for i, patch in enumerate(PATCHES, 1):
        if patch["unique_marker"] in content:
            continue
        cnt = content.count(patch["anchor"])
        if cnt == 0:
            issues.append((i, patch["id"], "anchor_not_found"))
        elif cnt > 1:
            issues.append((i, patch["id"], f"ambiguous({cnt})"))
    return issues


def main():
    p = argparse.ArgumentParser(
        description="Direction Agreement Filter Patch (trading_geo.py)",
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
        print(f"  Make sure trading_geo.py is in the current directory.")
        return 1

    with open(args.file, "r", encoding="utf-8") as f:
        original = f.read()

    print(f"Target:   {args.file}")
    print(f"Size:     {len(original):,} chars")
    print(f"Hash:     {_file_hash(original)}")
    print(f"Patches:  {len(PATCHES)}")
    print()

    if args.verify_only:
        ok, err = _verify_syntax(original)
        print(f"Syntax: {'✓ valid' if ok else '✗ ' + err}")
        print()
        for i, patch in enumerate(PATCHES, 1):
            present = patch["unique_marker"] in original
            mark = "✓ applied" if present else "·  pending"
            print(f"  [{mark:10s}] {i}. {patch['id']}: {patch['description']}")
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

    # Preflight — check all anchors first
    issues = _preflight(original)
    if issues:
        print("✗ Preflight detected issues:")
        for i, pid, reason in issues:
            print(f"    [{i}] {pid}: {reason}")
        print("\n  No changes written.")
        return 1
    print("✓ Preflight: all anchors present and unique")
    print()

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
                print(f"[{i}/{len(PATCHES)}] SKIP  {pid} (marker present)")
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
    backup = f"{args.file}.preAGREEMENT_{ts}.bak"
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
    print("═" * 70)
    print(f"✓ Direction Agreement Filter applied to {args.file}")
    print(f"  Backup:   {backup}")
    print(f"  Manifest: {MANIFEST}")
    print()
    print("السلوك الجديد:")
    print("  • BUY  مطلوب: z_dev < 0  AND  geo_accel_z > 0")
    print("  • SELL مطلوب: z_dev > 0  AND  geo_accel_z < 0")
    print("  • الإشارة تُرفض إذا اختلفا")
    print()
    print("geo_accel_z = geo_accel[fi] / std(geo_accel[fi-100:fi+1])")
    print()
    print("اختبار بأمرك الحالي (بدون أي تعديل):")
    print(f"  python3 {args.file} --mode backtest [أمرك]")
    print()
    print("للتشديد (جودة أعلى، إشارات أقل):")
    print(f"  python3 {args.file} --mode backtest [أمرك] --agreement-min-z 0.3")
    print()
    print("للتخفيف (إذا رفض إشارات كثيرة):")
    print(f"  python3 {args.file} --mode backtest [أمرك] --agreement-min-z -0.2")
    print()
    print("لتعطيل الفلتر:")
    print(f"  python3 {args.file} --mode backtest [أمرك] --no-agreement")
    print()
    print("لتشخيص أسباب الرفض:")
    print(f"  python3 {args.file} --mode backtest [أمرك] --agreement-log-rejections")
    print()
    print("ما ستراه في الـ log:")
    print("  [Agreement] ENABLED: both z_dev and geodesic_accel must agree")
    print("              (min_accel_z=+0.00, lookback=100)")
    print("  [Agreement] passed=2,100 rejected=1,850 (46.8%) "
          "[BUY_rej=920, SELL_rej=930]")
    print()
    print("تراجع:")
    print(f"  python apply_direction_agreement.py --rollback")
    print("═" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
