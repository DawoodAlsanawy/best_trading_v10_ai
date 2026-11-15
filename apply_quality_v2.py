#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_quality_v2.py — Signal Quality Improvement Patch (v2.1 — CORRECTED)
═══════════════════════════════════════════════════════════════════════════

يُصلح العيوب التي كشفها MAX_HOLD=4:
  ①  P_activation >= 0.35 منفتح جداً
  ②  z_dev >= 1.5 يعطي منتصف الموجة
  ③  score >= -3 يعني "خذ كل شيء"
  ④  لا يوجد سياق regime
  ⑤  لا يوجد تحقق من extreme حديث

الحل: Composite Quality Gate (6 عوامل) + exceptional pass للإشارات القوية.

═══════════════════════════════════════════════════════════════════════════
جميع anchors تم التحقق منها يدوياً على الملف الأصلي (945,916 chars)
بدون افتراضات عن المسافات البادئة في التعليقات
═══════════════════════════════════════════════════════════════════════════

الاستخدام:
    python apply_quality_v2.py --dry-run
    python apply_quality_v2.py
    python apply_quality_v2.py --verify-only
    python apply_quality_v2.py --rollback
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
PATCH_VERSION = "2.1.0"
MANIFEST = ".quality_v2_patches.json"


# ═══════════════════════════════════════════════════════════════════════════
# PAYLOADS
# ═══════════════════════════════════════════════════════════════════════════

CONFIG_PAYLOAD = '''
    # ══ [Quality-V2] Signal quality improvement ══
    # رفع الجودة بدون تقليل الإشارات كثيراً
    # Composite quality gate يجمع 6 عوامل
    QUALITY_V2_ENABLED: bool = False
    QUALITY_V2_THRESHOLD: float = 0.42
    QUALITY_V2_MIN_P: float = 0.45
    QUALITY_V2_MIN_Z: float = 1.8
    QUALITY_V2_MIN_SCORE: int = 0
    QUALITY_V2_EXCEPTIONAL_SCORE: int = 7
    QUALITY_V2_TREND_VETO_SCORE_MULT: float = 2.5
    QUALITY_V2_RECENT_EXTREME_BARS: int = 12
    # ══ [Quality-V2 end] ══
'''


HELPERS_PAYLOAD = '''# ═══════════════════════════════════════════════════════════════════════════
# [Quality-V2] Multi-factor signal quality gate
# ═══════════════════════════════════════════════════════════════════════════

_QV2_STATS: Dict = {
    "total": 0,
    "accepted": 0,
    "rejected": 0,
    "reasons": defaultdict(int),
    "qualities": [],
    "exceptional": 0,
}


def _qv2_reset_stats():
    _QV2_STATS["total"] = 0
    _QV2_STATS["accepted"] = 0
    _QV2_STATS["rejected"] = 0
    _QV2_STATS["reasons"].clear()
    _QV2_STATS["qualities"].clear()
    _QV2_STATS["exceptional"] = 0


def _qv2_norm(val, lo, hi):
    if hi <= lo:
        return 0.0
    return float(np.clip((val - lo) / (hi - lo), 0.0, 1.0))


def _qv2_regime_alignment(ad, ci, action):
    try:
        if ci < 50 or ci >= len(ad.ema200):
            return 0.5
        ema_now = float(ad.ema200[ci])
        ema_prev = float(ad.ema200[ci - 50])
        slope = (ema_now - ema_prev) / 50.0
        atr = float(ad.atr14[ci]) if ci < len(ad.atr14) else 0.0
        if atr <= 1e-12:
            return 0.5
        slope_norm = slope / atr
        if action == "BUY":
            if slope_norm > 0.02:
                return 1.0
            if slope_norm < -0.02:
                return 0.0
        else:
            if slope_norm < -0.02:
                return 1.0
            if slope_norm > 0.02:
                return 0.0
        return 0.5
    except Exception:
        return 0.5


def _qv2_recent_extreme(ad, ci, action, window):
    try:
        lo = max(1, ci - window)
        hi = ci
        if hi - lo < 3:
            return 0.0
        if action == "BUY":
            arr = ad.lows[lo:hi + 1]
            for j in range(len(arr) - 2, 0, -1):
                if arr[j] < arr[j - 1] and arr[j] < arr[j + 1]:
                    return 1.0
        else:
            arr = ad.highs[lo:hi + 1]
            for j in range(len(arr) - 2, 0, -1):
                if arr[j] > arr[j - 1] and arr[j] > arr[j + 1]:
                    return 1.0
        return 0.0
    except Exception:
        return 0.0


def _qv2_gauge_strength(ad, fi):
    try:
        g = float(ad.gauge_force[fi])
        window = ad.gauge_force[max(0, fi - 100):fi + 1]
        valid = window[window > 0]
        if len(valid) < 10:
            return 0.5
        p40 = float(np.percentile(valid, 40))
        p95 = float(np.percentile(valid, 95))
        return _qv2_norm(g, p40, p95)
    except Exception:
        return 0.5


def _qv2_quality_gate(sig, ad, ci, fi):
    if not getattr(CFG, "QUALITY_V2_ENABLED", False):
        return True, 1.0, {}

    _QV2_STATS["total"] += 1

    try:
        p = float(ad.closes[ci])
        geo_accel = float(ad.geodesic_accel[fi])
        fric = float(ad.friction[fi]) + 1e-6
        T_info = float(ad.T_info[fi])
        force_mag = abs(geo_accel) + 1e-9
        P_act = float(np.exp(-fric / (force_mag * T_info)))

        z_win = ad.closes[max(0, ci - CFG.N):ci]
        if len(z_win) < 2:
            return False, 0.0, {"reason": "z_insufficient"}
        z_mu = float(np.mean(z_win))
        z_sd = float(np.std(z_win))
        if z_sd <= 1e-12:
            return False, 0.0, {"reason": "z_zero_sd"}
        z_dev = (p - z_mu) / z_sd

        score = float(sig.score)
        action = sig.action

        if score >= int(getattr(CFG, "QUALITY_V2_EXCEPTIONAL_SCORE", 7)):
            _QV2_STATS["exceptional"] += 1
            return True, 1.0, {"reason": "exceptional_score",
                               "score": score}

        min_p = float(getattr(CFG, "QUALITY_V2_MIN_P", 0.45))
        min_z = float(getattr(CFG, "QUALITY_V2_MIN_Z", 1.8))
        min_s = int(getattr(CFG, "QUALITY_V2_MIN_SCORE", 0))

        if P_act < min_p:
            return False, 0.0, {
                "reason": f"P_act({P_act:.3f}<{min_p})"}
        if abs(z_dev) < min_z:
            return False, 0.0, {
                "reason": f"z_dev({abs(z_dev):.2f}<{min_z})"}
        if score < min_s:
            return False, 0.0, {
                "reason": f"score({score:.1f}<{min_s})"}

        q_P = _qv2_norm(P_act, min_p, 0.95)
        q_z = _qv2_norm(abs(z_dev), min_z, 3.5)
        q_score = _qv2_norm(score, min_s, 10.0)
        q_regime = _qv2_regime_alignment(ad, ci, action)
        q_gauge = _qv2_gauge_strength(ad, fi)
        q_extreme = _qv2_recent_extreme(
            ad, ci, action,
            int(getattr(CFG, "QUALITY_V2_RECENT_EXTREME_BARS", 12)))

        if q_regime == 0.0:
            _veto_thr = (float(getattr(
                CFG, "QUALITY_V2_TREND_VETO_SCORE_MULT", 2.5))
                * max(1, CFG.MIN_SCORE))
            if score < _veto_thr:
                return False, 0.0, {
                    "reason": f"trend_veto(score={score:.1f}<{_veto_thr})"}

        quality = (
            0.25 * q_P +
            0.20 * q_z +
            0.20 * q_score +
            0.15 * q_regime +
            0.10 * q_gauge +
            0.10 * q_extreme
        )

        thr = float(getattr(CFG, "QUALITY_V2_THRESHOLD", 0.42))
        if quality < thr:
            return False, quality, {
                "reason": f"quality({quality:.3f}<{thr})",
                "P": q_P, "z": q_z, "s": q_score,
                "r": q_regime, "g": q_gauge, "e": q_extreme,
            }
        return True, quality, {
            "P": q_P, "z": q_z, "s": q_score,
            "r": q_regime, "g": q_gauge, "e": q_extreme,
        }
    except Exception as e:
        return False, 0.0, {"reason": f"error({str(e)[:40]})"}


def _qv2_report():
    _t = _QV2_STATS["total"]
    if _t == 0:
        return
    _a = _QV2_STATS["accepted"]
    _r = _QV2_STATS["rejected"]
    _x = _QV2_STATS["exceptional"]

    print()
    print("═" * 70)
    print("  [Quality-V2] Signal Quality Report")
    print("═" * 70)
    print(f"  Total candidates  : {_t:,}")
    print(f"  Accepted          : {_a:,} ({_a / _t * 100:.1f}%)")
    print(f"  Rejected          : {_r:,} ({_r / _t * 100:.1f}%)")
    print(f"  Exceptional pass  : {_x:,} ({_x / _t * 100:.1f}%)")

    if _QV2_STATS["qualities"]:
        _q = np.array(_QV2_STATS["qualities"])
        print(f"  Quality  mu / sd  : {_q.mean():.3f} / {_q.std():.3f}")
        print(f"  Quality  p10/50/90: "
              f"{np.percentile(_q, 10):.3f} / "
              f"{np.percentile(_q, 50):.3f} / "
              f"{np.percentile(_q, 90):.3f}")

    print(f"  Top rejection reasons:")
    for _k, _v in sorted(_QV2_STATS["reasons"].items(),
                          key=lambda x: -x[1])[:8]:
        print(f"    {_k:42s}: {_v:6d}")
    print("═" * 70)
    print()

# ═══════════════════════════════════════════════════════════════════════════
'''


INTEGRATION_PAYLOAD = '''            # ══ [Quality-V2] Composite quality gate ══
            if getattr(CFG, 'QUALITY_V2_ENABLED', False):
                _qv2_accept, _qv2_qual, _qv2_info = _qv2_quality_gate(
                    _new_sig, ad, ci, fi
                )
                if not _qv2_accept:
                    _QV2_STATS['rejected'] += 1
                    _QV2_STATS['reasons'][
                        _qv2_info.get('reason', 'unknown')] += 1
                    continue
                _QV2_STATS['accepted'] += 1
                _QV2_STATS['qualities'].append(float(_qv2_qual))

'''


CLI_FLAGS_PAYLOAD = '''
    # ══ [Quality-V2] CLI flags ══
    p.add_argument("--quality-v2", action="store_true",
                   help="Enable Quality-V2 multi-factor signal gate")
    p.add_argument("--qv2-threshold", type=float, default=None,
                   help="Composite quality threshold (default 0.42)")
    p.add_argument("--qv2-min-p", type=float, default=None,
                   help="Minimum P_activation (default 0.45)")
    p.add_argument("--qv2-min-z", type=float, default=None,
                   help="Minimum abs(z_dev) (default 1.8)")
    p.add_argument("--qv2-min-score", type=int, default=None,
                   help="Minimum raw score (default 0)")
    p.add_argument("--qv2-exceptional-score", type=int, default=None,
                   help="Score above which signal bypasses gate (default 7)")
    p.add_argument("--qv2-trend-veto-mult", type=float, default=None,
                   help="Trend veto score multiplier (default 2.5)")
    p.add_argument("--qv2-extreme-bars", type=int, default=None,
                   help="Recent extreme window in bars (default 12)")

'''


CLI_PROCESS_PAYLOAD = '''
    # ══ [Quality-V2] Process CLI flags ══
    if getattr(args, "quality_v2", False):
        CFG.QUALITY_V2_ENABLED = True
    if getattr(args, "qv2_threshold", None) is not None:
        CFG.QUALITY_V2_THRESHOLD = float(args.qv2_threshold)
    if getattr(args, "qv2_min_p", None) is not None:
        CFG.QUALITY_V2_MIN_P = float(args.qv2_min_p)
    if getattr(args, "qv2_min_z", None) is not None:
        CFG.QUALITY_V2_MIN_Z = float(args.qv2_min_z)
    if getattr(args, "qv2_min_score", None) is not None:
        CFG.QUALITY_V2_MIN_SCORE = int(args.qv2_min_score)
    if getattr(args, "qv2_exceptional_score", None) is not None:
        CFG.QUALITY_V2_EXCEPTIONAL_SCORE = int(
            args.qv2_exceptional_score)
    if getattr(args, "qv2_trend_veto_mult", None) is not None:
        CFG.QUALITY_V2_TREND_VETO_SCORE_MULT = float(
            args.qv2_trend_veto_mult)
    if getattr(args, "qv2_extreme_bars", None) is not None:
        CFG.QUALITY_V2_RECENT_EXTREME_BARS = int(args.qv2_extreme_bars)
    if getattr(CFG, "QUALITY_V2_ENABLED", False):
        log.info(
            f"[Quality-V2] ENABLED "
            f"threshold={CFG.QUALITY_V2_THRESHOLD} "
            f"min_P={CFG.QUALITY_V2_MIN_P} "
            f"min_Z={CFG.QUALITY_V2_MIN_Z} "
            f"min_score={CFG.QUALITY_V2_MIN_SCORE} "
            f"exceptional={CFG.QUALITY_V2_EXCEPTIONAL_SCORE} "
            f"trend_veto={CFG.QUALITY_V2_TREND_VETO_SCORE_MULT}x "
            f"extreme_bars={CFG.QUALITY_V2_RECENT_EXTREME_BARS}")

'''


# ═══════════════════════════════════════════════════════════════════════════
# PATCHES — كل anchor تم التحقق منه على الملف الأصلي
# ═══════════════════════════════════════════════════════════════════════════

PATCHES = [
    # ─── 1. Config: insert before "CFG = Config()" (unique statement) ───
    {
        "id": "qv2_config",
        "description": "Add Quality-V2 config fields before CFG = Config()",
        "unique_marker": "QUALITY_V2_ENABLED: bool = False",
        "anchor": "CFG = Config()\n",
        "position": "before",
        "payload": CONFIG_PAYLOAD + "\n",
    },

    # ─── 2. Helpers: insert before "def build_signals(...)" ───
    {
        "id": "qv2_helpers",
        "description": "Add Quality-V2 helper functions before build_signals",
        "unique_marker": "def _qv2_quality_gate(",
        "anchor": 'def build_signals(assets, mode="backtest"):',
        "position": "before",
        "payload": HELPERS_PAYLOAD + "\n",
    },

    # ─── 3. Integration: 12-space indent, before filter stats line ───
    {
        "id": "qv2_integration",
        "description": "Insert quality gate before filter stats",
        "unique_marker": "# ══ [Quality-V2] Composite quality gate ══",
        "anchor": "            _FILTER_STATS['total_signals'] += 1\n",
        "position": "before",
        "payload": INTEGRATION_PAYLOAD,
    },

    # ─── 4. CLI flags: before "args = p.parse_args()" ───
    {
        "id": "qv2_cli_flags",
        "description": "Add Quality-V2 CLI flags",
        "unique_marker": 'p.add_argument("--quality-v2"',
        "anchor": "    args = p.parse_args()\n",
        "position": "before",
        "payload": CLI_FLAGS_PAYLOAD + "\n",
    },

    # ─── 5. CLI processing: after "if args.no_numba..." ───
    {
        "id": "qv2_cli_process",
        "description": "Process Quality-V2 CLI flags",
        "unique_marker": "CFG.QUALITY_V2_ENABLED = True",
        "anchor": "    if args.no_numba: CFG.NUMBA_ENABLED = False\n",
        "position": "after",
        "payload": CLI_PROCESS_PAYLOAD,
    },

    # ─── 6. Reset stats: replace the 2-line pattern in run_backtest ───
    {
        "id": "qv2_reset",
        "description": "Reset Quality-V2 stats before build_signals",
        "unique_marker": "        _qv2_reset_stats()\n",
        "anchor": "    _filter_reset_stats()\n    sigs = build_signals(assets)\n",
        "position": "replace",
        "payload": (
            "    _filter_reset_stats()\n"
            "    if getattr(CFG, 'QUALITY_V2_ENABLED', False):\n"
            "        _qv2_reset_stats()\n"
            "    sigs = build_signals(assets)\n"
        ),
    },

    # ─── 7. Report: after last statement of run_backtest (unique ASCII) ───
    {
        "id": "qv2_report",
        "description": "Print Quality-V2 report at end of backtest",
        "unique_marker": "# ══ [Quality-V2] Print report ══",
        "anchor": '        log.warning(f"[Diagnostic] HIGH REVERSAL RATE: {reversals}/{len(trades)}")\n',
        "position": "after",
        "payload": (
            "\n"
            "    # ══ [Quality-V2] Print report ══\n"
            "    if getattr(CFG, 'QUALITY_V2_ENABLED', False):\n"
            "        try:\n"
            "            _qv2_report()\n"
            "        except Exception as _e_qv2:\n"
            '            log.debug(f"[Quality-V2] report failed: {_e_qv2}")\n'
        ),
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
    marker = patch["unique_marker"]
    if marker in content:
        return content, "already_applied"

    anchor = patch["anchor"]
    pos = patch["position"]

    if pos == "replace":
        if anchor not in content:
            return content, "anchor_not_found"
        cnt = content.count(anchor)
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
    """Verify all anchors present and unique BEFORE writing anything."""
    issues = []
    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        marker = patch["unique_marker"]
        if marker in content:
            continue
        anchor = patch["anchor"]
        cnt = content.count(anchor)
        if cnt == 0:
            issues.append((i, pid, "anchor_not_found"))
        elif cnt > 1:
            issues.append((i, pid, f"ambiguous({cnt})"))
    return issues


def main():
    p = argparse.ArgumentParser(
        description="Quality-V2 Signal Quality Patch",
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
        print("Per-patch status:")
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

    # ── Preflight: verify ALL anchors present and unique BEFORE touching ──
    issues = _preflight(original)
    if issues:
        print("✗ Preflight detected issues:")
        for i, pid, reason in issues:
            print(f"    [{i}] {pid}: {reason}")
        print("\n  No changes written.")
        return 1
    print("✓ Preflight: all anchors present and unique")

    # ── Apply patches ──
    manifest = _load_manifest(MANIFEST)
    already = set(manifest.get("applied", []))

    current = original
    applied_n = 0
    skipped_n = 0
    failed = []

    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        if pid in already and not args.force:
            if args.verbose:
                print(f"[{i}/7] SKIP  {pid}")
            skipped_n += 1
            continue
        new_content, status = _apply_single(current, patch)
        if status == "applied":
            current = new_content
            applied_n += 1
            print(f"[{i}/7] ✓ APPLY {pid}")
        elif status == "already_applied":
            skipped_n += 1
            if args.verbose:
                print(f"[{i}/7] SKIP  {pid} (marker present)")
        else:
            failed.append((pid, status))
            print(f"[{i}/7] ✗ FAIL  {pid}: {status}")

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
    backup = f"{args.file}.preQV2_{ts}.bak"
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
    print(f"✓ Quality-V2 v{PATCH_VERSION} applied successfully")
    print(f"  Backup:   {backup}")
    print(f"  Manifest: {MANIFEST}")
    print()
    print("الخطوات التالية — اختبر بثلاث تكوينات لمقارنة النتائج:")
    print()
    print("  1. baseline (بدون Quality-V2 — يجب أن يطابق الأصلي):")
    print("     python trading_final.py [أمرك] --analytics")
    print()
    print("  2. Quality-V2 معتدل (توصية البداية):")
    print("     python trading_final.py [أمرك] --quality-v2 --analytics")
    print()
    print("  3. Quality-V2 صارم (جودة أعلى، إشارات أقل):")
    print("     python trading_final.py [أمرك] --quality-v2 \\")
    print("       --qv2-threshold 0.55 --qv2-min-p 0.55 \\")
    print("       --qv2-min-score 3 --analytics")
    print()
    print("  ⚠️ بعد تفعيل Quality-V2، جرّب رفع --max-hold:")
    print("     python trading_final.py [أمرك] --quality-v2 --max-hold 40 \\")
    print("       --analytics")
    print()
    print("  التراجع:")
    print("     python apply_quality_v2.py --rollback")
    print("═" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
