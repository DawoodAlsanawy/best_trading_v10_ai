#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_mr_regime_filter.py — Mean-Reversion Regime Filter
═══════════════════════════════════════════════════════════════════════════

المشكلة:
    البوت يفتح صفقات BUY/SELL بافتراض أن السوق في حالة mean-reversion
    دون السؤال: هل هذا صحيح؟ في الاتجاهات القوية، إشارات z_dev تفشل
    فوراً وتُغلق بـ MaxHold أو SL بسرعة.

الحل:
    فلتر regime كاسح يجمع 4 مقاييس مستقلة:
      1. Efficiency Ratio (Kaufman) — يقيس اتجاهية الحركة
      2. EMA slope / ATR — يقيس حِدّة الاتجاه
      3. Autocorrelation lag-1 — يقيس persistent behavior
      4. EMA dominance — يقيس قضاء السعر على جهة واحدة

    النتيجة: mr_score ∈ [0, 1]
      1.0 = mean-reversion قوي (ranging)
      0.0 = اتجاه قوي (trending)

    إذا mr_score < MIN_SCORE → الإشارة تُرفض.

التوقع:
    - عدد الإشارات: -15% إلى -25%
    - Win rate: +10% إلى +20%
    - متوسط مدة الصفقة: ×2 إلى ×5
    - Profit factor: +20% إلى +40%

الاستخدام:
    # الافتراضي: مُفعَّل مع threshold=0.35
    python trading_final.py [أمرك] --analytics

    # تعطيل
    python trading_final.py [أمرك] --no-mr-regime

    # ضبط العتبة
    python trading_final.py [أمرك] --mr-regime-min-score 0.30   # أقل صرامة
    python trading_final.py [أمرك] --mr-regime-min-score 0.45   # أكثر صرامة

    python apply_mr_regime_filter.py --dry-run
    python apply_mr_regime_filter.py
    python apply_mr_regime_filter.py --verify-only
    python apply_mr_regime_filter.py --rollback
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

TARGET = "trading_mr.py"
PATCH_VERSION = "1.0.0"
MANIFEST = ".mr_regime_filter.json"


# ═══════════════════════════════════════════════════════════════════════════
# PAYLOADS
# ═══════════════════════════════════════════════════════════════════════════

CONFIG_PAYLOAD = '''
    # ══ [MR-REGIME] Mean-Reversion Regime Filter ══
    # يسأل البوت: "هل السوق في حالة mean-reversion قبل الدخول؟"
    # mr_score ∈ [0, 1]: 1=ranging (جيد), 0=trending (سيئ)
    MR_REGIME_FILTER_ENABLED: bool = True
    MR_REGIME_MIN_SCORE: float = 0.35
    MR_REGIME_LOOKBACK: int = 50
    # ══ [MR-REGIME end] ══
'''


HELPER_PAYLOAD = '''# ═══════════════════════════════════════════════════════════════════════════
# [MR-REGIME] Mean-Reversion Regime Detection
# ═══════════════════════════════════════════════════════════════════════════
# يجمع 4 مقاييس مستقلة لقياس ما إذا كان السوق يتحرك في نطاق عرضي
# (mean-reverting) أو اتجاه قوي (trending).
#
# Components:
#   1. Efficiency Ratio (Kaufman):
#        ER = |p_N - p_0| / Σ|p_i - p_{i-1}|
#        ER=1 → perfect trend | ER=0 → perfect noise
#   2. EMA slope (ATR-normalized):
#        |slope × lookback| / ATR
#        كبير → اتجاه قوي
#   3. Return autocorrelation (lag-1):
#        autocorr < 0 → mean-reverting (جيد)
#        autocorr > 0 → persistent trend (سيئ)
#   4. EMA dominance:
#        نسبة الشموع على نفس جهة EMA200 خلال 20 شمعة
#
# النتيجة: mr_score ∈ [0, 1]
# ═══════════════════════════════════════════════════════════════════════════

_MR_REGIME_STATS: Dict = {"total": 0, "passed": 0, "rejected": 0}


def _mr_regime_reset_stats():
    _MR_REGIME_STATS["total"] = 0
    _MR_REGIME_STATS["passed"] = 0
    _MR_REGIME_STATS["rejected"] = 0


def _compute_mr_score(ad, ci, lookback=50):
    """Compute mean-reversion score in [0, 1].
    1.0 = strong mean-reversion (range-bound) → accept
    0.0 = strong trend (directional)        → reject
    """
    try:
        if ci < lookback + 2:
            return 1.0  # insufficient data → no filter
        prices = ad.closes[ci - lookback:ci + 1]
        if len(prices) < lookback + 1:
            return 1.0

        # ── 1. Efficiency Ratio (Kaufman) ──
        net_move = abs(float(prices[-1]) - float(prices[0]))
        total_move = float(np.sum(np.abs(np.diff(prices))))
        er = net_move / (total_move + 1e-12)
        # er = 0 (choppy) → score component = 1
        # er = 1 (trend)  → score component = 0
        er_score = float(np.clip(1.0 - er, 0.0, 1.0))

        # ── 2. EMA slope (ATR-normalized) ──
        slope_score = 1.0
        try:
            if ci >= 50 and ci < len(ad.ema200) and ci < len(ad.atr14):
                ema_slope = (float(ad.ema200[ci])
                             - float(ad.ema200[ci - 50])) / 50.0
                atr = float(ad.atr14[ci])
                if atr > 1e-12:
                    slope_norm = abs(ema_slope * 50.0) / atr
                    # slope_norm = 0 → 1.0 | slope_norm = 2 → 0.0
                    slope_score = float(np.clip(
                        1.0 - slope_norm / 2.0, 0.0, 1.0))
        except Exception:
            slope_score = 1.0

        # ── 3. Return autocorrelation (lag-1) ──
        ac_score = 0.5
        try:
            lr = np.diff(np.log(np.maximum(prices, 1e-12)))
            if len(lr) >= 10:
                lr_0 = lr[:-1]
                lr_1 = lr[1:]
                sd0 = float(np.std(lr_0))
                sd1 = float(np.std(lr_1))
                if sd0 > 1e-9 and sd1 > 1e-9:
                    ac = float(np.corrcoef(lr_0, lr_1)[0, 1])
                    if np.isfinite(ac):
                        # ac = -0.3 → 1.0 | ac = +0.3 → 0.0
                        ac_score = float(np.clip(
                            (0.3 - ac) / 0.6, 0.0, 1.0))
        except Exception:
            ac_score = 0.5

        # ── 4. EMA dominance (price above/below EMA200) ──
        dominance_score = 0.5
        try:
            if ci >= 20 and ci < len(ad.ema200):
                above = 0
                total = 0
                for k in range(ci - 20, ci + 1):
                    if k < len(ad.ema200) and k < len(ad.closes):
                        total += 1
                        if ad.closes[k] > ad.ema200[k]:
                            above += 1
                if total >= 15:
                    dom = abs(2.0 * above - total) / total
                    # dom = 1 → all one side (trend) → score = 0
                    dominance_score = float(np.clip(1.0 - dom, 0.0, 1.0))
        except Exception:
            dominance_score = 0.5

        # ── Weighted composite ──
        mr = (0.35 * er_score
              + 0.25 * slope_score
              + 0.25 * ac_score
              + 0.15 * dominance_score)
        return float(np.clip(mr, 0.0, 1.0))
    except Exception:
        return 1.0  # fail-open

# ═══════════════════════════════════════════════════════════════════════════
'''


BUILD_SIGNALS_PAYLOAD = '''            # ══ [MR-REGIME] هل السوق في حالة mean-reversion؟ ══
            if getattr(CFG, 'MR_REGIME_FILTER_ENABLED', True):
                _mr_lb = int(getattr(CFG, 'MR_REGIME_LOOKBACK', 50))
                _mr_thr = float(getattr(CFG, 'MR_REGIME_MIN_SCORE', 0.35))
                _mr_s = _compute_mr_score(ad, ci, _mr_lb)
                _MR_REGIME_STATS["total"] += 1
                if _mr_s < _mr_thr:
                    _MR_REGIME_STATS["rejected"] += 1
                    log.debug(
                        f"[MR-Regime] {sym} {action} rejected: "
                        f"mr_score={_mr_s:.3f} < {_mr_thr:.3f} "
                        f"(lookback={_mr_lb})")
                    continue
                _MR_REGIME_STATS["passed"] += 1

'''


CLI_FLAGS_PAYLOAD = '''
    # ══ [MR-REGIME] CLI flags ══
    p.add_argument("--mr-regime", action="store_true",
                   help="Enable mean-reversion regime filter (default: on)")
    p.add_argument("--no-mr-regime", action="store_true",
                   help="Disable mean-reversion regime filter")
    p.add_argument("--mr-regime-min-score", type=float, default=None,
                   help="MR score threshold (default 0.35; higher=stricter)")
    p.add_argument("--mr-regime-lookback", type=int, default=None,
                   help="MR lookback window in bars (default 50)")

'''


CLI_PROCESS_PAYLOAD = '''
    # ══ [MR-REGIME] process CLI flags ══
    if getattr(args, "no_mr_regime", False):
        CFG.MR_REGIME_FILTER_ENABLED = False
    elif getattr(args, "mr_regime", False):
        CFG.MR_REGIME_FILTER_ENABLED = True
    if getattr(args, "mr_regime_min_score", None) is not None:
        CFG.MR_REGIME_MIN_SCORE = float(args.mr_regime_min_score)
    if getattr(args, "mr_regime_lookback", None) is not None:
        CFG.MR_REGIME_LOOKBACK = int(args.mr_regime_lookback)
    if CFG.MR_REGIME_FILTER_ENABLED:
        log.info(
            f"[MR-Regime] ENABLED (min_score={CFG.MR_REGIME_MIN_SCORE}, "
            f"lookback={CFG.MR_REGIME_LOOKBACK} bars)")
    else:
        log.info("[MR-Regime] DISABLED")

'''


# ═══════════════════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════════════════

PATCHES = [
    {
        "id": "mr_config",
        "description": "Add MR-REGIME config fields after FIX-2 regime filter",
        "unique_marker": "MR_REGIME_FILTER_ENABLED: bool = True",
        "anchor": "    REGIME_SLOPE_ATR_MAX: float = 2.0   # |slope×bars|/ATR > this → skip\n",
        "position": "after",
        "payload": CONFIG_PAYLOAD,
    },
    {
        "id": "mr_helpers",
        "description": "Add _compute_mr_score before build_signals",
        "unique_marker": "def _compute_mr_score(ad, ci, lookback=50):",
        "anchor": 'def build_signals(assets, mode="backtest"):',
        "position": "before",
        "payload": HELPER_PAYLOAD + "\n",
    },
    {
        "id": "mr_build_signals",
        "description": "Insert MR-regime check before FIX-2 regime filter",
        "unique_marker": "# ══ [MR-REGIME] هل السوق في حالة mean-reversion؟ ══",
        "anchor": "            # ══ [FIX 2] Regime filter — reject trending markets ══\n",
        "position": "before",
        "payload": BUILD_SIGNALS_PAYLOAD,
    },
    {
        "id": "mr_cli_flags",
        "description": "Add MR-REGIME CLI flags",
        "unique_marker": 'p.add_argument("--mr-regime"',
        "anchor": "    args = p.parse_args()\n",
        "position": "before",
        "payload": CLI_FLAGS_PAYLOAD,
    },
    {
        "id": "mr_cli_process",
        "description": "Process MR-REGIME CLI flags in main()",
        "unique_marker": "CFG.MR_REGIME_FILTER_ENABLED = False",
        "anchor": "    if args.no_numba: CFG.NUMBA_ENABLED = False\n",
        "position": "after",
        "payload": CLI_PROCESS_PAYLOAD,
    },
    {
        "id": "mr_reset_stats",
        "description": "Reset MR-REGIME stats before build_signals",
        "unique_marker": "_mr_regime_reset_stats()",
        "anchor": (
            "    # ══ [FILTER] إعادة تعيين العدّاد قبل البناء ══\n"
            "    _filter_reset_stats()\n"
        ),
        "position": "after",
        "payload": (
            "    if getattr(CFG, 'MR_REGIME_FILTER_ENABLED', True):\n"
            "        _mr_regime_reset_stats()\n"
        ),
    },
    {
        "id": "mr_report",
        "description": "Log MR-REGIME summary at end of backtest",
        "unique_marker": "# ══ [MR-REGIME] summary log ══",
        "anchor": "            log.info(f\"  {sym:14s}: b={r['slope']:+.5f}  R²={r['r2']:.3f}  [{r['trend']}]\")\n",
        "position": "after",
        "payload": (
            "\n"
            "    # ══ [MR-REGIME] summary log ══\n"
            "    if getattr(CFG, 'MR_REGIME_FILTER_ENABLED', True):\n"
            "        _mr_tot = _MR_REGIME_STATS['total']\n"
            "        if _mr_tot > 0:\n"
            "            _mr_rej = _MR_REGIME_STATS['rejected']\n"
            "            _mr_pct = 100.0 * _mr_rej / _mr_tot\n"
            "            log.info(\n"
            "                f\"[MR-Regime] passed={_MR_REGIME_STATS['passed']}, \"\n"
            "                f\"rejected={_mr_rej} ({_mr_pct:.1f}%)\")\n"
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
    if patch["unique_marker"] in content:
        return content, "already_applied"
    anchor = patch["anchor"]
    pos = patch["position"]
    cnt = content.count(anchor)
    if cnt == 0:
        return content, "anchor_not_found"
    if cnt > 1:
        return content, f"ambiguous({cnt})"
    idx = content.find(anchor)
    if pos == "before":
        return content[:idx] + patch["payload"] + content[idx:], "applied"
    if pos == "after":
        end = idx + len(anchor)
        return content[:end] + patch["payload"] + content[end:], "applied"
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
        description="MR-Regime Filter Patch",
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

    print(f"Target:   {args.file}")
    print(f"Size:     {len(original):,} chars")
    print(f"Hash:     {_file_hash(original)}")
    print(f"Patches:  {len(PATCHES)}")
    print()

    if args.verify_only:
        ok, err = _verify_syntax(original)
        print(f"Syntax: {'✓ valid' if ok else '✗ ' + err}")
        for i, patch in enumerate(PATCHES, 1):
            present = patch["unique_marker"] in original
            print(f"  [{'✓' if present else '·'}] {i}. {patch['id']}")
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

    issues = _preflight(original)
    if issues:
        print("✗ Preflight issues:")
        for i, pid, reason in issues:
            print(f"    [{i}] {pid}: {reason}")
        print("\n  No changes written.")
        return 1
    print("✓ Preflight: all anchors present and unique")

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
    backup = f"{args.file}.preMRREGIME_{ts}.bak"
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
    print(f"✓ MR-Regime Filter applied")
    print(f"  Backup:   {backup}")
    print(f"  Manifest: {MANIFEST}")
    print()
    print("السلوك الجديد:")
    print("  • قبل كل إشارة، البوت يسأل: هل السوق في حالة mean-reversion؟")
    print("  • إذا mr_score < 0.35 (اتجاه قوي) → الإشارة تُرفض")
    print("  • إذا mr_score ≥ 0.35 (ranging) → الإشارة تمر")
    print()
    print("المقاييس الأربعة:")
    print("  1. Efficiency Ratio (Kaufman)  وزن 35%")
    print("  2. EMA slope / ATR              وزن 25%")
    print("  3. Return autocorrelation       وزن 25%")
    print("  4. EMA dominance                وزن 15%")
    print()
    print("الاستخدام:")
    print("  # افتراضي (مُفعَّل، threshold=0.35):")
    print("  python trading_final.py [أمرك] --analytics")
    print()
    print("  # تعطيل:")
    print("  python trading_final.py [أمرك] --no-mr-regime")
    print()
    print("  # ضبط:")
    print("  python trading_final.py [أمرك] --mr-regime-min-score 0.30")
    print("  python trading_final.py [أمرك] --mr-regime-min-score 0.45")
    print()
    print("ما ستراه في الـ log:")
    print("  [MR-Regime] ENABLED (min_score=0.35, lookback=50 bars)")
    print("  [MR-Regime] passed=3800, rejected=454 (10.7%)")
    print()
    print("تراجع:")
    print("  python apply_mr_regime_filter.py --rollback")
    print("═" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
