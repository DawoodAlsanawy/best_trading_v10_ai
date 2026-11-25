#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════════
  Restore Physics + Fix Stage 2 + Add SL-Sigma Filter — Patcher
═══════════════════════════════════════════════════════════════════════════════
يطبّق 7 تعديلات على trading_published_pro_1h_test.py:
  P01: N: 6 → 24
  P02: TP_MULT: 5.0 → 3.0 + إضافة حقلي فلتر sl_sigma
  P03: إعادة تفعيل بوابة P_activation (عتبة 0.20)
  P04: z_dev threshold: 2.0 → 1.5
  P05: Stage 2 TP يستخدم CFG.TP_MULT بدلاً من 2.0
  P06: إدراج فلتر sl_sigma (0.875σ) في build_signals
  P07: Marker في أعلى الملف

⚠️  مهم: بعد التطبيق، احذف `--tp-mult 7` من أمر التشغيل
     ليصبح TP_MULT = 3.0 من Config فعالاً.
═══════════════════════════════════════════════════════════════════════════════
"""
import argparse
import ast
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_TARGET = "trading_published_pro_1h_test2.py"
MARKER = "# ═══ [RESTORE-PHYSICS-APPLIED] ═══"


PATCHES = [

    # ═════════════════════════════════════════════════════════════════════
    # P01 — N: 6 → 24
    # ═════════════════════════════════════════════════════════════════════
    {
        "id": "P01-N-restore",
        "desc": "N: 6 → 24 (استعادة نافذة z_dev الأصلية)",
        "old": (
            "    N: int = 6; W: int = 20; L: int = 10; K: int = 8\n"
        ),
        "new": (
            "    N: int = 24; W: int = 20; L: int = 10; K: int = 8\n"
        ),
    },

    # ═════════════════════════════════════════════════════════════════════
    # P02 — TP_MULT: 5.0 → 3.0 + إضافة Config fields للفلتر
    # ═════════════════════════════════════════════════════════════════════
    {
        "id": "P02-TP_MULT-and-filter-config",
        "desc": "TP_MULT: 5.0 → 3.0 + إضافة حقلي SL_SIGMA_FILTER",
        "old": (
            "    TP_MULT: float = 5.0    # كان 2.0 → الآن 1.5 (R:R = 1.5)\n"
        ),
        "new": (
            "    TP_MULT: float = 3.0    # [PATCH] R:R = 3.0 (احذف --tp-mult 7 من CLI)\n"
            "    # ══ [SL-SIGMA-FILTER] رفض الصفقات ذات SL < SL_SIGMA_FILTER_MIN × σ ══\n"
            "    SL_SIGMA_FILTER_ENABLED: bool = True\n"
            "    SL_SIGMA_FILTER_MIN: float = 0.875\n"
        ),
    },

    # ═════════════════════════════════════════════════════════════════════
    # P03 — إعادة تفعيل بوابة P_activation
    # ═════════════════════════════════════════════════════════════════════
    {
        "id": "P03-P_activation-restore",
        "desc": "إعادة تفعيل بوابة P_activation (عتبة 0.20)",
        "old": (
            "            force_mag = abs(geo_accel) + 1e-9\n"
            "            P_activation = np.exp(-fric_val / (force_mag * T_info))\n"
        ),
        "new": (
            "            force_mag = abs(geo_accel) + 1e-9\n"
            "            P_activation = np.exp(-fric_val / (force_mag * T_info))\n"
            "            # ══ [PATCH] إعادة تفعيل بوابة P_activation ══\n"
            "            if P_activation < 0.20:\n"
            "                continue\n"
        ),
    },

    # ═════════════════════════════════════════════════════════════════════
    # P04 — z_dev threshold: 2.0 → 1.5
    # ═════════════════════════════════════════════════════════════════════
    {
        "id": "P04-zdev-threshold",
        "desc": "z_dev threshold: 2.0 → 1.5 (متسق مع N=24)",
        "old": (
            "            # [ABLATION-2c] softer deviation gate\n"
            "            if abs(_z_dev) < 2.0:\n"
            "                continue\n"
        ),
        "new": (
            "            # [PATCH] deviation gate: 2.0 → 1.5 (متسق مع N=24)\n"
            "            if abs(_z_dev) < 1.5:\n"
            "                continue\n"
        ),
    },

    # ═════════════════════════════════════════════════════════════════════
    # P05 — Stage 2 TP يستخدم CFG.TP_MULT
    # ═════════════════════════════════════════════════════════════════════
    {
        "id": "P05-stage2-tp",
        "desc": "Stage 2: tp_new يستخدم TP_MULT بدلاً من 2.0 الصلب",
        "old": (
            "        if sig.action == \"BUY\":\n"
            "            sl_new = S_new - sl_dist_new\n"
            "            tp_new = S_new + (sl_dist_new * 2.0)\n"
            "        else:\n"
            "            sl_new = S_new + sl_dist_new\n"
            "            tp_new = S_new - (sl_dist_new * 2.0)\n"
        ),
        "new": (
            "        # ══ [PATCH] Stage 2 TP: استخدام TP_MULT بدلاً من 2.0 الصلب ══\n"
            "        _tp_mult_s2 = float(getattr(cfg, 'TP_MULT', 3.0))\n"
            "        if sig.action == \"BUY\":\n"
            "            sl_new = S_new - sl_dist_new\n"
            "            tp_new = S_new + (sl_dist_new * _tp_mult_s2)\n"
            "        else:\n"
            "            sl_new = S_new + sl_dist_new\n"
            "            tp_new = S_new - (sl_dist_new * _tp_mult_s2)\n"
        ),
    },

    # ═════════════════════════════════════════════════════════════════════
    # P06 — إدراج فلتر sl_sigma في build_signals
    # ═════════════════════════════════════════════════════════════════════
    {
        "id": "P06-sl-sigma-filter",
        "desc": "إدراج فلتر sl_sigma (0.875σ) بعد compute_geodesic_stop",
        "old": (
            "            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)\n"
            "            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)\n"
        ),
        "new": (
            "            # حساب الوقف والهدف بناءً على سعر النفق (Limit Entry)\n"
            "            sl_dist = compute_geodesic_stop(tunnel_entry_p, ad, fi, CFG)\n"
            "            # ══ [PATCH] [SL-SIGMA-FILTER] رفض الصفقات ذات SL < 0.875σ ══\n"
            "            if getattr(CFG, 'SL_SIGMA_FILTER_ENABLED', True):\n"
            "                _ssf_frac = 0.01\n"
            "                if 0 <= fi < len(ad.E_therm):\n"
            "                    _ssf_v = float(ad.E_therm[fi])\n"
            "                    if np.isfinite(_ssf_v) and _ssf_v > 1e-6:\n"
            "                        _ssf_frac = _ssf_v\n"
            "                _ssf_px = _ssf_frac * tunnel_entry_p\n"
            "                if _ssf_px > 0 and sl_dist > 0:\n"
            "                    _sl_sig_act = sl_dist / _ssf_px\n"
            "                    _sl_sig_min = float(getattr(CFG, 'SL_SIGMA_FILTER_MIN', 0.875))\n"
            "                    if _sl_sig_act < _sl_sig_min:\n"
            "                        log.debug(f\"[SL-Sigma-Filter] {sym} {action} \"\n"
            "                                  f\"sl_sigma={_sl_sig_act:.3f} < \"\n"
            "                                  f\"{_sl_sig_min} — skip\")\n"
            "                        continue\n"
        ),
    },

    # ═════════════════════════════════════════════════════════════════════
    # P07 — Marker
    # ═════════════════════════════════════════════════════════════════════
    {
        "id": "P07-marker",
        "desc": "Marker في أعلى الملف",
        "old": (
            "#!/usr/bin/env python3\n"
            "# -*- coding: utf-8 -*-\n"
        ),
        "new": (
            "# ═══ [RESTORE-PHYSICS-APPLIED] ═══\n"
            "#!/usr/bin/env python3\n"
            "# -*- coding: utf-8 -*-\n"
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _cnt(text, pat):
    return text.count(pat) if pat else 0


def _apply(content, patch):
    old, new, pid = patch["old"], patch["new"], patch["id"]
    if _cnt(content, new) == 1:
        return content, "already_applied", f"{pid}: already present"
    oc = _cnt(content, old)
    if oc == 0:
        return content, "not_found", f"{pid}: anchor not found"
    if oc > 1:
        return content, "ambiguous", f"{pid}: anchor appears {oc}×"
    return content.replace(old, new, 1), "applied", f"{pid}: OK"


def _verify_syntax(c):
    try:
        ast.parse(c)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def run_patch(target, dry_run=False):
    print(f"\n{'═' * 74}")
    print(f"  Restore Physics + Fix Stage 2 + SL-Sigma Filter")
    print(f"  Target: {target}")
    print(f"  Mode  : {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target not found: {target}\n")
        return 1

    original = target.read_text(encoding="utf-8")
    print(f"  📄 Loaded {len(original):,} chars "
          f"({original.count(chr(10)):,} lines)\n")

    if MARKER in original:
        if all(_cnt(original, p["new"]) == 1 for p in PATCHES):
            print(f"  ✅ File already fully patched.\n")
            return 0
        print(f"  ⚠️  Marker present but patches incomplete — use --rollback\n")
        return 2

    content = original
    applied, skipped, failed = [], [], []

    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        print(f"  [{i:02d}/{len(PATCHES)}] {pid:<40} ", end="", flush=True)
        nc, st, d = _apply(content, patch)
        if st == "applied":
            content = nc
            applied.append(patch)
            print("✅ applied")
        elif st == "already_applied":
            skipped.append(patch)
            print("⏭️  already")
        else:
            failed.append((patch, d))
            print(f"❌ {st}")
            print(f"      └─ {d}")

    print(f"\n{'─' * 74}")
    print(f"  Summary: {len(applied)} applied, {len(skipped)} already, "
          f"{len(failed)} failed")
    print(f"{'─' * 74}\n")

    if failed:
        print(f"  ❌ Patching aborted — {len(failed)} failed. No file modified.\n")
        for patch, d in failed:
            print(f"     • {patch['id']}: {d}\n")
        return 3

    if not applied:
        print(f"  ✅ Already fully patched.\n")
        return 0

    print(f"  🔍 Validating syntax (ast.parse)...")
    ok, err = _verify_syntax(content)
    if not ok:
        print(f"  ❌ Syntax FAILED: {err}")
        print(f"     No file modified.\n")
        return 4
    print(f"  ✅ Syntax OK\n")

    if dry_run:
        print(f"  🧪 DRY-RUN — would write {len(content):,} chars\n")
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = target.with_suffix(target.suffix + f".restore_physics_{ts}")
    try:
        shutil.copy2(target, bk)
        print(f"  💾 Backup: {bk.name}")
    except Exception as e:
        print(f"  ❌ Backup failed: {e}\n")
        return 5

    tmp = target.with_suffix(target.suffix + ".restore_physics_tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
        print(f"  ✅ Written: {target}\n")
    except Exception as e:
        print(f"  ❌ Write failed: {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        try:
            if bk.exists():
                shutil.copy2(bk, target)
                print(f"  🔄 Auto-rollback complete.\n")
        except Exception:
            pass
        return 6

    print(f"{'═' * 74}")
    print(f"  ✅ All patches applied successfully!")
    print(f"{'═' * 74}")
    print(f"  📋 What changed:")
    print(f"    • N: 6 → 24 (نافذة z_dev الأصلية)")
    print(f"    • TP_MULT: 5.0 → 3.0 (في Config)")
    print(f"    • P_activation gate: أُعيد تفعيله (عتبة 0.20)")
    print(f"    • z_dev threshold: 2.0 → 1.5")
    print(f"    • Stage 2 TP: يستخدم TP_MULT بدلاً من 2.0")
    print(f"    • SL-Sigma Filter: جديد (0.875σ)")
    print(f"")
    print(f"  ⚠️  CRITICAL — يجب تعديل أمر التشغيل:")
    print(f"")
    print(f"     احذف `--tp-mult 7` تماماً من أمر التشغيل")
    print(f"     (وإلا سيبقى TP=7 ويتجاوز Config's 3.0)")
    print(f"")
    print(f"  أمر التشغيل المُوصى به:")
    print(f"     python {target.name} \\")
    print(f"         --nassets 100 --timeframe 1h \\")
    print(f"         --enable-sell --sell-gauge-pct 100 \\")
    print(f"         --sl-widen-mult 0.8 --partial-tp-r 3 \\")
    print(f"         --maxcon 4 --workers 4 --history-days 180 \\")
    print(f"         --po-wait-s 300 \\")
    print(f"         --be-escape --be-escape-move-r 0.3 --be-escape-min-profit-r 0.1 \\")
    print(f"         --no-be-escape-ema --no-dynamic-trail \\")
    print(f"         --heat-max 0.05 --capital 20.06 \\")
    print(f"         --rule-filter --rule-min-score 3 \\")
    print(f"         --no-reentry-cooldown")
    print(f"")
    print(f"  Rollback:")
    print(f"     python3 {Path(__file__).name} --rollback")
    print(f"{'═' * 74}\n")
    return 0


def run_verify(target):
    print(f"\n{'═' * 74}")
    print(f"  Verification — {target}")
    print(f"{'═' * 74}\n")
    if not target.exists():
        print(f"  ❌ Not found\n")
        return 1
    c = target.read_text(encoding="utf-8")
    print(f"  Marker: {'✅ YES' if MARKER in c else '❌ NO'}\n")
    ok, bad = 0, 0
    for p in PATCHES:
        if _cnt(c, p["new"]) == 1:
            print(f"  ✅ {p['id']}")
            ok += 1
        elif _cnt(c, p["old"]) == 1:
            print(f"  ❌ {p['id']} (anchor still present — not applied)")
            bad += 1
        else:
            print(f"  ⚠️  {p['id']} (anchor missing — modified externally)")
            bad += 1
    print(f"\n  {ok}/{len(PATCHES)} verified\n")
    return 0 if ok == len(PATCHES) else 2


def run_rollback(target):
    print(f"\n{'═' * 74}")
    print(f"  Rollback — {target}")
    print(f"{'═' * 74}\n")
    if not target.exists():
        print(f"  ❌ Not found\n")
        return 1
    bks = sorted(
        target.parent.glob(target.name + ".restore_physics_*"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not bks:
        print(f"  ❌ No backups found\n")
        return 1
    latest = bks[0]
    print(f"  🔍 Restoring from: {latest.name}")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = target.with_suffix(target.suffix + f".pre_rollback_{ts}")
    shutil.copy2(target, pre)
    shutil.copy2(latest, target)
    print(f"  ✅ Rolled back\n")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Restore Physics + Fix Stage 2 + SL-Sigma Filter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 restore_physics_patcher.py\n"
            "  python3 restore_physics_patcher.py --dry-run\n"
            "  python3 restore_physics_patcher.py --verify-only\n"
            "  python3 restore_physics_patcher.py --rollback\n"
            "  python3 restore_physics_patcher.py --target custom.py\n"
        ),
    )
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv)
    target = Path(args.target).resolve()
    try:
        if args.rollback:
            return run_rollback(target)
        if args.verify_only:
            return run_verify(target)
        return run_patch(target, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n\n  ⏹️  Interrupted.\n")
        return 130
    except Exception as e:
        print(f"\n  💥 Unexpected error: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
