#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_saw_mode.py — Saw Mode (Trend-Aware Directional Trading) v1.2
═══════════════════════════════════════════════════════════════════════════

v1.2 (هذا الإصدار) — يتعامل مع ملف تم تطبيق Bear Shield عليه:
  • saw_direction_gate: anchor مبني على السياق الفعلي بعد Bear Shield
  • saw_report: يستخدم [Analytics] finalize anchor مع position=before
                (يتفادى تعديل Bear Shield block)
  • Preflight: كشف ذكي يتعرف على حالة الملف (نظيف / Bear Shield مطبق)

الاستخدام:
    python apply_saw_mode.py --dry-run
    python apply_saw_mode.py
    python apply_saw_mode.py --verify-only
    python apply_saw_mode.py --rollback
═══════════════════════════════════════════════════════════════════════════
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

DEFAULT_TARGET = "trading_final.py"
PATCH_VERSION = "1.2.0"
MANIFEST = ".saw_mode_patches.json"


# ═══════════════════════════════════════════════════════════════════════════
# PAYLOADS
# ═══════════════════════════════════════════════════════════════════════════

CONFIG_PAYLOAD = '''
    # ══ [SAW-MODE] Trend-aware directional trading ══
    SAW_MODE_ENABLED: bool = True
    SAW_TREND_STRONG: float = 0.7
    SAW_TREND_WEAK: float = 0.3
    SAW_TREND_LOOKBACK: int = 30
    SAW_BUY_Z_STRONG_BULL: float = 1.0
    SAW_SELL_Z_STRONG_BEAR: float = 1.0
    SAW_BUY_RISK_STRONG: float = 1.3
    SAW_SELL_RISK_STRONG: float = 0.7
    SAW_BUY_TP_STRONG: float = 0.0
    SAW_SELL_TP_STRONG: float = 3.0
    # ══ [SAW-MODE end] ══
'''


HELPER_PAYLOAD = '''# ═══════════════════════════════════════════════════════════════════════════
# [SAW-MODE] Trend Strength — per-asset, no look-ahead
# ═══════════════════════════════════════════════════════════════════════════

def _compute_trend_strength(ad, fi: int) -> float:
    """Compute trend strength in [-1, +1] from EMA200 slope + accel agreement."""
    if ad is None:
        return 0.0
    try:
        ci = int(ad.feat_start) + int(fi)
        if ci < 200 or ci >= len(ad.closes) or ci >= len(ad.ema200):
            return 0.0
        current = float(ad.closes[ci])
        ema_now = float(ad.ema200[ci])
        if current <= 0 or ema_now <= 0:
            return 0.0
        lb = int(getattr(CFG, 'SAW_TREND_LOOKBACK', 30))
        if ci < lb:
            return 0.0
        ema_prev = float(ad.ema200[ci - lb])
        if ema_prev <= 0:
            return 0.0
        ema_slope = (ema_now - ema_prev) / ema_prev
        slope_norm = float(np.clip(ema_slope / 0.15, -1.0, 1.0))
        try:
            if 0 <= fi < len(ad.geodesic_accel):
                accel = float(ad.geodesic_accel[fi])
                if accel * slope_norm < 0:
                    return 0.0
        except Exception:
            pass
        return slope_norm
    except Exception:
        return 0.0

# ═══════════════════════════════════════════════════════════════════════════
'''


# ═══════════════════════════════════════════════════════════════════════════
# PATCHES — v1.2 (متوافق مع Bear Shield)
# ═══════════════════════════════════════════════════════════════════════════

PATCHES = [
    # ─── 1. Config ───
    {
        "id": "saw_config",
        "description": "Add SAW_MODE config fields after MAX_HOLD_BARS",
        "unique_marker": "SAW_MODE_ENABLED: bool = True",
        "anchor": "    MAX_HOLD_BARS: int = 2000\n",
        "position": "after",
        "payload": CONFIG_PAYLOAD,
    },

    # ─── 2. Signal dataclass: saw_trend field ───
    {
        "id": "saw_signal_field",
        "description": "Add saw_trend field to Signal dataclass",
        "unique_marker": "saw_trend: float = 0.0",
        "anchor": "    mfal_p_act: float = 0.0\n",
        "position": "after",
        "payload": "    saw_trend: float = 0.0\n",
    },

    # ─── 3. Helper function ───
    {
        "id": "saw_helper",
        "description": "Add _compute_trend_strength before build_signals",
        "unique_marker": "def _compute_trend_strength(ad, fi: int) -> float:",
        "anchor": 'def build_signals(assets, mode="backtest"):',
        "position": "before",
        "payload": HELPER_PAYLOAD + "\n",
    },

    # ─── 4. Init _saw_trend per signal ───
    {
        "id": "saw_init_trend",
        "description": "Compute _saw_trend once per signal",
        "unique_marker": "_saw_trend = _compute_trend_strength(ad, fi)",
        "anchor": "            geo_accel = float(ad.geodesic_accel[fi])\n",
        "position": "before",
        "payload": (
            "            # [SAW-MODE] Compute trend strength once per signal\n"
            "            _saw_trend = 0.0\n"
            "            if getattr(CFG, 'SAW_MODE_ENABLED', False):\n"
            "                _saw_trend = _compute_trend_strength(ad, fi)\n"
            "\n"
        ),
    },

    # ─── 5. Direction gate + dynamic z_dev (v1.2 — post Bear Shield) ───
    # Bear Shield already modified this region. We target ONLY the final
    # z_dev gate + action determination, which are still pristine.
    {
        "id": "saw_direction_gate",
        "description": "Dynamic z_dev threshold + block opposite direction (post-Bear-Shield)",
        "unique_marker": "# [SAW-MODE] Dynamic z_dev threshold",
        "anchor": (
            "            if abs(_z_dev) < 1.5:\n"
            "                continue\n"
            '            action = "BUY" if _z_dev < 0 else "SELL"\n'
        ),
        "position": "replace",
        "payload": (
            "            # [SAW-MODE] Dynamic z_dev threshold\n"
            "            _saw_z_min = 1.5\n"
            "            if getattr(CFG, 'SAW_MODE_ENABLED', False):\n"
            "                if _saw_trend > CFG.SAW_TREND_STRONG:\n"
            "                    _saw_z_min = CFG.SAW_BUY_Z_STRONG_BULL\n"
            "                elif _saw_trend < -CFG.SAW_TREND_STRONG:\n"
            "                    _saw_z_min = CFG.SAW_SELL_Z_STRONG_BEAR\n"
            "            if abs(_z_dev) < _saw_z_min:\n"
            "                continue\n"
            '            action = "BUY" if _z_dev < 0 else "SELL"\n'
            "\n"
            "            # [SAW-MODE] Direction gate: never fight strong trend\n"
            "            _saw_strong_bear = (\n"
            "                getattr(CFG, 'SAW_MODE_ENABLED', False)\n"
            '                and action == "SELL"\n'
            "                and _saw_trend < -CFG.SAW_TREND_STRONG\n"
            "            )\n"
            "            if (getattr(CFG, 'SAW_MODE_ENABLED', False)\n"
            '                    and action == "BUY"\n'
            "                    and _saw_trend < -CFG.SAW_TREND_STRONG):\n"
            "                continue\n"
            "            if (getattr(CFG, 'SAW_MODE_ENABLED', False)\n"
            '                    and action == "SELL"\n'
            "                    and _saw_trend > CFG.SAW_TREND_STRONG):\n"
            "                continue\n"
        ),
    },

    # ─── 6. SELL bypass in strong bear ───
    {
        "id": "saw_sell_bypass",
        "description": "Bypass SELL filters in strong bear (auto-enable SELL)",
        "unique_marker": "# [SAW-MODE] SELL bypass in strong bear",
        "anchor": (
            '            if action == "SELL":\n'
            "                if not getattr(CFG, 'SELL_ENABLED', False):\n"
            "                    continue\n"
            "                if ad.score[fi] < float(getattr(CFG, 'SELL_MIN_SCORE', 3)):\n"
            "                    continue\n"
            "                if abs(_z_dev) < float(getattr(CFG, 'SELL_MIN_ZDEV', 1.5)):\n"
            "                    continue\n"
        ),
        "position": "replace",
        "payload": (
            '            if action == "SELL":\n'
            "                # [SAW-MODE] SELL bypass in strong bear\n"
            "                _sell_allowed = (getattr(CFG, 'SELL_ENABLED', False)\n"
            "                                 or _saw_strong_bear)\n"
            "                if not _sell_allowed:\n"
            "                    continue\n"
            "                if not _saw_strong_bear:\n"
            "                    if ad.score[fi] < float(getattr(CFG, 'SELL_MIN_SCORE', 3)):\n"
            "                        continue\n"
            "                    if abs(_z_dev) < float(getattr(CFG, 'SELL_MIN_ZDEV', 1.5)):\n"
            "                        continue\n"
        ),
    },

    # ─── 7. Gauge bypass for SELL in strong bear ───
    {
        "id": "saw_gauge_bypass",
        "description": "Skip gauge filter for SELL in strong bear",
        "unique_marker": "GAUGE_FILTER_ENABLED', False) and not _saw_strong_bear:",
        "anchor": (
            "            # ══ [GAUGE-FILTER] ══\n"
            "            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):\n"
        ),
        "position": "replace",
        "payload": (
            "            # ══ [GAUGE-FILTER] ══\n"
            "            # [SAW-MODE] Skip gauge filter for SELL in strong bear\n"
            "            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False) and not _saw_strong_bear:\n"
        ),
    },

    # ─── 8. Trend-adjusted TP ───
    {
        "id": "saw_tp_adjust",
        "description": "Use trend-aware TP multiple",
        "unique_marker": "# [SAW-MODE] Trend-aware TP",
        "anchor": (
            "            _tp_mult = float(getattr(CFG, 'TP_MULT', 1.5))\n"
            '            tp1 = tunnel_entry_p + (sl_dist * _tp_mult) if action == "BUY" else tunnel_entry_p - (sl_dist * _tp_mult)\n'
        ),
        "position": "replace",
        "payload": (
            "            # [SAW-MODE] Trend-aware TP\n"
            "            _tp_mult = float(getattr(CFG, 'TP_MULT', 1.5))\n"
            "            if getattr(CFG, 'SAW_MODE_ENABLED', False):\n"
            "                if (action == 'SELL'\n"
            "                        and _saw_strong_bear\n"
            "                        and CFG.SAW_SELL_TP_STRONG > 0):\n"
            "                    _tp_mult = CFG.SAW_SELL_TP_STRONG\n"
            "                elif (action == 'BUY'\n"
            "                        and _saw_trend > CFG.SAW_TREND_STRONG\n"
            "                        and CFG.SAW_BUY_TP_STRONG > 0):\n"
            "                    _tp_mult = CFG.SAW_BUY_TP_STRONG\n"
            '            tp1 = tunnel_entry_p + (sl_dist * _tp_mult) if action == "BUY" else tunnel_entry_p - (sl_dist * _tp_mult)\n'
        ),
    },

    # ─── 9. Signal creation with saw_trend ───
    {
        "id": "saw_signal_create",
        "description": "Pass saw_trend to Signal constructor",
        "unique_marker": "saw_trend=float(_saw_trend),",
        "anchor": (
            "                mfal_x=_mfal_x,\n"
            "                mfal_p_act=float(P_activation),\n"
            "            )\n"
        ),
        "position": "replace",
        "payload": (
            "                mfal_x=_mfal_x,\n"
            "                mfal_p_act=float(P_activation),\n"
            "                saw_trend=float(_saw_trend),\n"
            "            )\n"
        ),
    },

    # ─── 10. Risk multiplier in backtest ───
    {
        "id": "saw_risk_backtest",
        "description": "Apply trend risk multiplier in simulate_portfolio",
        "unique_marker": "# [SAW-MODE] Backtest risk multiplier",
        "anchor": (
            "        # Apply drawdown multiplier + floor protection\n"
            "        risk_frac *= dd_mult * power_law_scale\n"
            "        risk_frac = float(np.clip(risk_frac,\n"
        ),
        "position": "replace",
        "payload": (
            "        # Apply drawdown multiplier + floor protection\n"
            "        risk_frac *= dd_mult * power_law_scale\n"
            "        # [SAW-MODE] Backtest risk multiplier\n"
            "        if getattr(CFG, 'SAW_MODE_ENABLED', False):\n"
            "            _st_bt = float(getattr(sig, 'saw_trend', 0.0))\n"
            "            if sig.action == 'BUY' and _st_bt > CFG.SAW_TREND_STRONG:\n"
            "                risk_frac *= CFG.SAW_BUY_RISK_STRONG\n"
            "            elif sig.action == 'SELL' and _st_bt < -CFG.SAW_TREND_STRONG:\n"
            "                risk_frac *= CFG.SAW_SELL_RISK_STRONG\n"
            "        risk_frac = float(np.clip(risk_frac,\n"
        ),
    },

    # ─── 11. Risk multiplier in live ───
    {
        "id": "saw_risk_live",
        "description": "Apply trend risk multiplier in run_live",
        "unique_marker": "# [SAW-MODE] Live risk multiplier",
        "anchor": (
            "                    risk_frac *= power_law_scale * (\n"
            "                        dd_mult if getattr(CFG, 'LIVE_APPLY_DD_MULT', True) else 1.0)\n"
            "                    risk_frac = float(np.clip(risk_frac,\n"
        ),
        "position": "replace",
        "payload": (
            "                    risk_frac *= power_law_scale * (\n"
            "                        dd_mult if getattr(CFG, 'LIVE_APPLY_DD_MULT', True) else 1.0)\n"
            "                    # [SAW-MODE] Live risk multiplier\n"
            "                    if getattr(CFG, 'SAW_MODE_ENABLED', False):\n"
            "                        _st_lv = float(getattr(sig, 'saw_trend', 0.0))\n"
            "                        if sig.action == 'BUY' and _st_lv > CFG.SAW_TREND_STRONG:\n"
            "                            risk_frac *= CFG.SAW_BUY_RISK_STRONG\n"
            "                        elif sig.action == 'SELL' and _st_lv < -CFG.SAW_TREND_STRONG:\n"
            "                            risk_frac *= CFG.SAW_SELL_RISK_STRONG\n"
            "                    risk_frac = float(np.clip(risk_frac,\n"
        ),
    },

    # ─── 12. CLI flags ───
    {
        "id": "saw_cli_flags",
        "description": "Add Saw Mode CLI flags",
        "unique_marker": 'p.add_argument("--no-saw-mode"',
        "anchor": "    args = p.parse_args()\n",
        "position": "before",
        "payload": (
            "\n"
            "    # ══ [SAW-MODE] CLI ══\n"
            '    p.add_argument("--no-saw-mode", action="store_true",\n'
            '                   help="Disable Saw Mode (trend-aware direction)")\n'
            '    p.add_argument("--saw-trend-strong", type=float, default=None,\n'
            '                   help="Strong trend threshold (default 0.7)")\n'
            '    p.add_argument("--saw-buy-risk", type=float, default=None,\n'
            '                   help="BUY risk multiplier in strong bull (default 1.3)")\n'
            '    p.add_argument("--saw-sell-risk", type=float, default=None,\n'
            '                   help="SELL risk multiplier in strong bear (default 0.7)")\n'
            '    p.add_argument("--saw-sell-tp", type=float, default=None,\n'
            '                   help="SELL TP multiple in strong bear (default 3.0)")\n'
            '    p.add_argument("--saw-buy-z", type=float, default=None,\n'
            '                   help="BUY z_dev in strong bull (default 1.0)")\n'
            '    p.add_argument("--saw-sell-z", type=float, default=None,\n'
            '                   help="SELL z_dev in strong bear (default 1.0)")\n'
            "\n"
        ),
    },

    # ─── 13. CLI process ───
    {
        "id": "saw_cli_process",
        "description": "Process Saw Mode CLI flags",
        "unique_marker": "CFG.SAW_MODE_ENABLED = False",
        "anchor": "    if args.no_numba: CFG.NUMBA_ENABLED = False\n",
        "position": "after",
        "payload": (
            "\n"
            "    # ══ [SAW-MODE] Process CLI flags ══\n"
            '    if getattr(args, "no_saw_mode", False):\n'
            "        CFG.SAW_MODE_ENABLED = False\n"
            '    if getattr(args, "saw_trend_strong", None) is not None:\n'
            "        CFG.SAW_TREND_STRONG = float(args.saw_trend_strong)\n"
            '    if getattr(args, "saw_buy_risk", None) is not None:\n'
            "        CFG.SAW_BUY_RISK_STRONG = float(args.saw_buy_risk)\n"
            '    if getattr(args, "saw_sell_risk", None) is not None:\n'
            "        CFG.SAW_SELL_RISK_STRONG = float(args.saw_sell_risk)\n"
            '    if getattr(args, "saw_sell_tp", None) is not None:\n'
            "        CFG.SAW_SELL_TP_STRONG = float(args.saw_sell_tp)\n"
            '    if getattr(args, "saw_buy_z", None) is not None:\n'
            "        CFG.SAW_BUY_Z_STRONG_BULL = float(args.saw_buy_z)\n"
            '    if getattr(args, "saw_sell_z", None) is not None:\n'
            "        CFG.SAW_SELL_Z_STRONG_BEAR = float(args.saw_sell_z)\n"
            "    if CFG.SAW_MODE_ENABLED:\n"
            "        log.info(\n"
            '            f"[SawMode] ENABLED: strong={CFG.SAW_TREND_STRONG}, "\n'
            '            f"BUY: z>={CFG.SAW_BUY_Z_STRONG_BULL} risk×{CFG.SAW_BUY_RISK_STRONG}, "\n'
            '            f"SELL: z>={CFG.SAW_SELL_Z_STRONG_BEAR} risk×{CFG.SAW_SELL_RISK_STRONG} "\n'
            '            f"tp={CFG.SAW_SELL_TP_STRONG}")\n'
            "    else:\n"
            '        log.info("[SawMode] DISABLED — classic mean-reversion mode")\n'
            "\n"
        ),
    },

    # ─── 14. Report — v1.2 uses "[Analytics] finalize" as unique anchor ───
    # Bear Shield inserted its block between print_report and Analytics.
    # So we insert saw_report RIGHT BEFORE "[Analytics] finalize" using
    # position="before" on that unique comment.
    {
        "id": "saw_report",
        "description": "Log Saw Mode summary before Analytics finalize",
        "unique_marker": "# ══ [SAW-MODE] Backtest summary ══",
        "anchor": "    # ══ [Analytics] finalize backtest ══\n",
        "position": "before",
        "payload": (
            "    # ══ [SAW-MODE] Backtest summary ══\n"
            "    if getattr(CFG, 'SAW_MODE_ENABLED', False):\n"
            "        try:\n"
            "            _saw_buy = sum(1 for t in trades if t.action == 'BUY')\n"
            "            _saw_sell = sum(1 for t in trades if t.action == 'SELL')\n"
            "            _saw_buy_pnl = sum(t.net_pnl for t in trades if t.action == 'BUY')\n"
            "            _saw_sell_pnl = sum(t.net_pnl for t in trades if t.action == 'SELL')\n"
            '            log.info(f"[SawMode] BUY: {_saw_buy} trades, ${_saw_buy_pnl:+.2f}")\n'
            '            log.info(f"[SawMode] SELL: {_saw_sell} trades, ${_saw_sell_pnl:+.2f}")\n'
            "        except Exception:\n"
            "            pass\n"
            "    \n"
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


def _detect_prior_patches(content):
    """Detect which patches have been applied to the file previously."""
    out = {
        "bear_shield": "BEAR_SHIELD_ENABLED: bool = True" in content,
        "saw_mode": "SAW_MODE_ENABLED: bool = True" in content,
        "slp": "SLP_ENABLED: bool = False" in content,
        "quality_v2": "QUALITY_V2_ENABLED: bool = False" in content,
        "agreement": "AGREEMENT_REQUIRED: bool = True" in content,
    }
    return out


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
        description="Saw Mode v1.2 — Trend-Aware Directional Trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    p.add_argument("--file", default=DEFAULT_TARGET)
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
    print(f"Version:  {PATCH_VERSION}")
    print()

    # ── Detection of prior patches ──
    prior = _detect_prior_patches(original)
    print("Prior patches detected:")
    for name, found in prior.items():
        mark = "✓" if found else "·"
        print(f"  [{mark}] {name}")
    print()

    if args.verify_only:
        ok, err = _verify_syntax(original)
        print(f"Syntax: {'✓ valid' if ok else '✗ ' + err}")
        print()
        for i, patch in enumerate(PATCHES, 1):
            present = patch["unique_marker"] in original
            cnt = 0 if present else original.count(patch["anchor"])
            status = "✓ applied" if present else (
                f"· pending (anchor×{cnt})" if cnt > 0 else "✗ anchor not found")
            print(f"  [{status:28s}] {i}. {patch['id']}")
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
        print("✗ Preflight detected issues:")
        for i, pid, reason in issues:
            print(f"    [{i}] {pid}: {reason}")
        print()
        print("  No changes written.")
        print()
        print("  الملف قد يحتوي تعديلات لم يتوقعها الـ patch.")
        print("  شغّل --verify-only وأرسل المخرجات للمراجعة.")
        return 1
    print(f"✓ Preflight: all {len(PATCHES)} anchors present and unique")
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
    backup = f"{args.file}.preSAW_{ts}.bak"
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
    print("═" * 72)
    print(f"✓ Saw Mode v{PATCH_VERSION} applied successfully")
    print(f"  Backup:   {backup}")
    print(f"  Manifest: {MANIFEST}")
    print()
    print("═══════════════════════════════════════════════════════════════════")
    print("Saw Mode + Bear Shield يعملان معاً:")
    print("═══════════════════════════════════════════════════════════════════")
    print("  Bear Shield: كشف Bear + تقليل حجم + تقليل concurrency")
    print("  Saw Mode:    إضافة SELL في Bear + BUY أسهل في Bull")
    print()
    print("  النتيجة:")
    print("    • Strong Bull:  BUY فقط، z=1.0، risk ×1.3")
    print("    • Strong Bear:  SELL فقط، z=1.0، risk ×0.7، TP=3R")
    print("    • Neutral:      السلوك القديم (Bear Shield يتحكم)")
    print()
    print("اختبار بأمرك الحالي (بدون تعديل):")
    print(f"  python3 {args.file} --mode backtest [أمرك]")
    print()
    print("اختبار 2022 (Bear):")
    print(f"  python3 {args.file} --mode backtest [أمرك] \\")
    print("    --history-days 400 --end-date 2022-12-31")
    print()
    print("اختبار 2023 (Bull):")
    print(f"  python3 {args.file} --mode backtest [أمرك] \\")
    print("    --history-days 400 --end-date 2023-12-31")
    print()
    print("تراجع:")
    print(f"  python apply_saw_mode.py --rollback")
    print("═" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
