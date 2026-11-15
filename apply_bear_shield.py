#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_bear_shield.py — Bear Market Survival Shield (v1.1)
═══════════════════════════════════════════════════════════════════════════

v1.1 — FIX: bs_report anchor يستخدم سياقاً كاملاً (3 أسطر) بدل سطر واحد
        لتفادي ambiguous(2) بين print_report في early-return و natural-end

التشخيص أكد:
  - bs_report كان Anchor يطابق سطرين: 10399 (8 مسافات) و 10409 (4 مسافات)
  - الحل: anchor يشمل السطر قبل + بعد بحيث لا يطابق إلا موقع واحد

الاستخدام:
    python apply_bear_shield.py --dry-run
    python apply_bear_shield.py
    python apply_bear_shield.py --verify-only
    python apply_bear_shield.py --rollback
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
PATCH_VERSION = "1.1.0"
MANIFEST = ".bear_shield_patches.json"


CONFIG_PAYLOAD = '''
    # ══ [BEAR-SHIELD] Bear market survival ══
    BEAR_SHIELD_ENABLED: bool = True
    BEAR_MIN_Z: float = 2.5
    BEAR_MIN_SCORE: int = 0
    BEAR_GAUGE_BOOST: float = 1.3
    BEAR_RISK_MULT: float = 0.30
    BEAR_MAX_CONCURRENT: int = 3
    BEAR_EMA_SLOPE_LOOKBACK: int = 30
    BEAR_RETURN_LOOKBACK_DAYS: int = 30
    BEAR_RETURN_THRESHOLD: float = -0.15
    # ══ [BEAR-SHIELD end] ══
'''


HELPER_PAYLOAD = '''# ═══════════════════════════════════════════════════════════════════════════
# [BEAR-SHIELD] Bear Market Detection
# ═══════════════════════════════════════════════════════════════════════════

def _asset_bias_at_index(ad, fi: int) -> float:
    """Compute bear/bull bias at bar fi using ONLY data up to fi (no look-ahead)."""
    try:
        if ad is None or fi < 200:
            return 0.0
        if fi >= len(ad.closes) or fi >= len(ad.ema200):
            return 0.0
        current = float(ad.closes[fi])
        ema = float(ad.ema200[fi])
        if current <= 0 or ema <= 0:
            return 0.0
        c1 = current < ema
        lb = int(getattr(CFG, 'BEAR_EMA_SLOPE_LOOKBACK', 30))
        c2 = False
        if fi >= lb:
            try:
                c2 = ema < float(ad.ema200[fi - lb])
            except Exception:
                c2 = False
        days = int(getattr(CFG, 'BEAR_RETURN_LOOKBACK_DAYS', 30))
        bars = max(30, int(days * 24 / max(CFG.TF_HOURS, 1e-6)))
        c3 = False
        if fi >= bars:
            try:
                past_px = float(ad.closes[fi - bars])
                if past_px > 0:
                    ret = current / past_px - 1.0
                    c3 = ret < float(getattr(CFG, 'BEAR_RETURN_THRESHOLD', -0.15))
            except Exception:
                c3 = False
        bear_count = int(c1) + int(c2) + int(c3)
        if bear_count >= 2:
            return -1.0
        if bear_count == 0:
            return 1.0
        return 0.0
    except Exception:
        return 0.0


def _asset_bias_at_bar(ad, target_ts) -> float:
    """Compute bias at the nearest bar to target_ts (no look-ahead)."""
    if ad is None:
        return 0.0
    try:
        idx = int(np.searchsorted(
            ad.timestamps.asi8,
            pd.Timestamp(target_ts).value,
            side='right'
        ) - 1)
        idx = max(0, min(idx, len(ad.closes) - 1))
        return _asset_bias_at_index(ad, idx)
    except Exception:
        return 0.0

# ═══════════════════════════════════════════════════════════════════════════
'''


PATCHES = [
    {
        "id": "bs_config",
        "description": "Add BEAR_SHIELD config fields",
        "unique_marker": "BEAR_SHIELD_ENABLED: bool = True",
        "anchor": "    MAX_HOLD_BARS: int = 2000\n",
        "position": "after",
        "payload": CONFIG_PAYLOAD,
    },
    {
        "id": "bs_helpers",
        "description": "Add bear bias detection helpers",
        "unique_marker": "def _asset_bias_at_index(ad, fi: int) -> float:",
        "anchor": 'def build_signals(assets, mode="backtest"):',
        "position": "before",
        "payload": HELPER_PAYLOAD + "\n",
    },
    {
        "id": "bs_sig_init",
        "description": "Init BTC reference in build_signals",
        "unique_marker": "_btc_ref_sig = assets.get('BTC/USDT')",
        "anchor": "    sigs = []\n",
        "position": "after",
        "payload": (
            "\n"
            "    # ══ [BEAR-SHIELD] BTC reference for market bias ══\n"
            "    _btc_ref_sig = (assets.get('BTC/USDT')\n"
            "                    or assets.get('BTC/USDT:USDT'))\n"
        ),
    },
    {
        "id": "bs_sig_filter",
        "description": "Apply bear filters (z_dev) per signal",
        "unique_marker": "# ══ [BEAR-SHIELD] Bear mode filter ══",
        "anchor": (
            "            if abs(_z_dev) < 1.5:\n"
            "                continue\n"
            '            action = "BUY" if _z_dev < 0 else "SELL"\n'
        ),
        "position": "replace",
        "payload": (
            "            # ══ [BEAR-SHIELD] Bear mode filter ══\n"
            "            _bear_now = False\n"
            "            if (getattr(CFG, 'BEAR_SHIELD_ENABLED', True)\n"
            "                    and _btc_ref_sig is not None):\n"
            "                try:\n"
            "                    _b = _asset_bias_at_bar(\n"
            "                        _btc_ref_sig, ad.timestamps[ci])\n"
            "                    _bear_now = (_b < 0)\n"
            "                except Exception:\n"
            "                    _bear_now = False\n"
            "            if _bear_now and _z_dev < 0:\n"
            "                _bmz = float(getattr(CFG, 'BEAR_MIN_Z', 2.5))\n"
            "                if abs(_z_dev) < _bmz:\n"
            "                    continue\n"
            "            if abs(_z_dev) < 1.5:\n"
            "                continue\n"
            '            action = "BUY" if _z_dev < 0 else "SELL"\n'
        ),
    },
    {
        "id": "bs_sig_score",
        "description": "Raise score floor in bear mode",
        "unique_marker": "# ══ [BEAR-SHIELD] Bear score floor ══",
        "anchor": "            if ad.score[fi] < _min_score: continue\n",
        "position": "replace",
        "payload": (
            "            # ══ [BEAR-SHIELD] Bear score floor ══\n"
            "            if _bear_now:\n"
            "                _min_score = max(_min_score,\n"
            "                    float(getattr(CFG, 'BEAR_MIN_SCORE', 0)))\n"
            "            if ad.score[fi] < _min_score: continue\n"
        ),
    },
    {
        "id": "bs_sig_gauge",
        "description": "Raise gauge threshold in bear mode",
        "unique_marker": "# ══ [BEAR-SHIELD] Bear gauge boost ══",
        "anchor": (
            '                    if action == "BUY" and _gf < _gauge_thr_buy:\n'
            '                        continue\n'
        ),
        "position": "replace",
        "payload": (
            "                    # ══ [BEAR-SHIELD] Bear gauge boost ══\n"
            "                    _eff_gf_thr = _gauge_thr_buy\n"
            "                    if _bear_now:\n"
            "                        _eff_gf_thr *= float(getattr(\n"
            "                            CFG, 'BEAR_GAUGE_BOOST', 1.3))\n"
            '                    if action == "BUY" and _gf < _eff_gf_thr:\n'
            "                        continue\n"
        ),
    },
    {
        "id": "bs_sim_init",
        "description": "Init BTC reference in simulate_portfolio",
        "unique_marker": "_btc_ref_sim = assets.get('BTC/USDT')",
        "anchor": (
            "    capital  = CFG.INITIAL_CAPITAL\n"
            "    peak_cap = capital\n"
        ),
        "position": "after",
        "payload": (
            "    # ══ [BEAR-SHIELD] BTC reference ══\n"
            "    _btc_ref_sim = (assets.get('BTC/USDT')\n"
            "                    or assets.get('BTC/USDT:USDT'))\n"
        ),
    },
    {
        "id": "bs_sim_bias",
        "description": "Compute bear bias per signal in simulation loop",
        "unique_marker": "# ══ [BEAR-SHIELD] Bias for this signal ══",
        "anchor": (
            "        # حاجز أمان مطلق: يستحيل بدء تداول جديد إذا اقترب الجسيم من عتبة الفناء (5.1$)\n"
            "        if capital <= CFG.CAPITAL_FLOOR + 0.1:\n"
            "            break\n"
        ),
        "position": "after",
        "payload": (
            "\n"
            "        # ══ [BEAR-SHIELD] Bias for this signal ══\n"
            "        _bear_sig = False\n"
            "        if (getattr(CFG, 'BEAR_SHIELD_ENABLED', True)\n"
            "                and _btc_ref_sim is not None):\n"
            "            try:\n"
            "                _b_sig = _asset_bias_at_bar(\n"
            "                    _btc_ref_sim, sig.timestamp)\n"
            "                _bear_sig = (_b_sig < 0)\n"
            "            except Exception:\n"
            "                _bear_sig = False\n"
        ),
    },
    {
        "id": "bs_sim_risk",
        "description": "Lower concurrency cap in bear mode",
        "unique_marker": "# ══ [BEAR-SHIELD] Bear concurrency cap ══",
        "anchor": "        if len(open_pos) >= CFG.MAX_CONCURRENT_ASSETS: continue\n",
        "position": "replace",
        "payload": (
            "        # ══ [BEAR-SHIELD] Bear concurrency cap ══\n"
            "        _eff_max_sim = CFG.MAX_CONCURRENT_ASSETS\n"
            "        if _bear_sig:\n"
            "            _eff_max_sim = min(_eff_max_sim,\n"
            "                int(getattr(CFG, 'BEAR_MAX_CONCURRENT', 3)))\n"
            "        if len(open_pos) >= _eff_max_sim: continue\n"
        ),
    },
    {
        "id": "bs_sim_riskmult",
        "description": "Compute bear risk multiplier",
        "unique_marker": "# ══ [BEAR-SHIELD] Risk reduction ══",
        "anchor": (
            "        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)\n"
            "        if risk_frac <= 0.0:\n"
        ),
        "position": "before",
        "payload": (
            "        # ══ [BEAR-SHIELD] Risk reduction ══\n"
            "        if _bear_sig:\n"
            "            _risk_mult_sim = float(getattr(CFG, 'BEAR_RISK_MULT', 0.30))\n"
            "        else:\n"
            "            _risk_mult_sim = 1.0\n"
        ),
    },
    {
        "id": "bs_sim_apply",
        "description": "Apply bear risk multiplier to computed risk_frac",
        "unique_marker": "if _bear_sig:\n            risk_frac *= _risk_mult_sim",
        "anchor": (
            "        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)\n"
            "        if risk_frac <= 0.0:\n"
            '            log.debug(f"[Budget] {sym} skipped: no heat budget available")\n'
            "            continue\n"
        ),
        "position": "replace",
        "payload": (
            "        risk_frac = compute_portfolio_risk_frac(sig, capital, open_pos, CFG)\n"
            "        if risk_frac <= 0.0:\n"
            '            log.debug(f"[Budget] {sym} skipped: no heat budget available")\n'
            "            continue\n"
            "        # ══ [BEAR-SHIELD] Risk reduction ══\n"
            "        if _bear_sig:\n"
            "            risk_frac *= _risk_mult_sim\n"
        ),
    },
    {
        "id": "bs_live_bias",
        "description": "Compute bear state each live cycle",
        "unique_marker": "# ══ [BEAR-SHIELD] Current cycle bear state ══",
        "anchor": (
            "            _LV_ASSETS.clear()\n"
            "            _LV_ASSETS.update(assets)\n"
        ),
        "position": "after",
        "payload": (
            "            # ══ [BEAR-SHIELD] Current cycle bear state ══\n"
            "            _bear_live = False\n"
            "            _bias_live = 0.0\n"
            "            if getattr(CFG, 'BEAR_SHIELD_ENABLED', True):\n"
            "                _btc_live = (assets.get('BTC/USDT')\n"
            "                             or assets.get('BTC/USDT:USDT'))\n"
            "                if _btc_live is not None:\n"
            "                    try:\n"
            "                        _bias_live = _asset_bias_at_index(\n"
            "                            _btc_live, len(_btc_live.closes) - 1)\n"
            "                        _bear_live = (_bias_live < 0)\n"
            "                    except Exception:\n"
            "                        pass\n"
            "            if _bear_live:\n"
            "                log.info(f\"[BearShield] BEAR MODE (bias={_bias_live:+.1f}) \"\n"
            "                         f\"— risk×{getattr(CFG, 'BEAR_RISK_MULT', 0.30):.0%}, \"\n"
            "                         f\"max_concurrent={getattr(CFG, 'BEAR_MAX_CONCURRENT', 3)}\")\n"
        ),
    },
    {
        "id": "bs_live_concurrency",
        "description": "Lower concurrency cap in live bear mode",
        "unique_marker": "# ══ [BEAR-SHIELD] Lower cap in bear ══",
        "anchor": (
            "                            else:\n"
            "                                _total_exposure = (len(_PENDING_ORDERS)\n"
            "                                                   + len(open_pos_live)\n"
            "                                                   + len(_WATCHED_SIGNALS))\n"
            "                                _exp_cap = int(CFG.MAX_CONCURRENT_ASSETS)\n"
        ),
        "position": "replace",
        "payload": (
            "                            else:\n"
            "                                _total_exposure = (len(_PENDING_ORDERS)\n"
            "                                                   + len(open_pos_live)\n"
            "                                                   + len(_WATCHED_SIGNALS))\n"
            "                                _exp_cap = int(CFG.MAX_CONCURRENT_ASSETS)\n"
            "                                # ══ [BEAR-SHIELD] Lower cap in bear ══\n"
            "                                if _bear_live:\n"
            "                                    _exp_cap = min(_exp_cap,\n"
            "                                        int(getattr(CFG, 'BEAR_MAX_CONCURRENT', 3)))\n"
        ),
    },
    {
        "id": "bs_live_risk",
        "description": "Compute bear risk reduction in live",
        "unique_marker": "# ══ [BEAR-SHIELD] Live risk reduction ══",
        "anchor": (
            "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
            "                    if risk_frac <= 0.0:\n"
        ),
        "position": "before",
        "payload": (
            "                    # ══ [BEAR-SHIELD] Live risk reduction ══\n"
            "                    if _bear_live:\n"
            "                        _risk_mult_live = float(getattr(\n"
            "                            CFG, 'BEAR_RISK_MULT', 0.30))\n"
            "                    else:\n"
            "                        _risk_mult_live = 1.0\n"
        ),
    },
    {
        "id": "bs_live_apply",
        "description": "Apply bear risk multiplier in live",
        "unique_marker": "if _bear_live:\n                        risk_frac *= _risk_mult_live",
        "anchor": (
            "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
            "                    if risk_frac <= 0.0:\n"
            '                        log.debug(f"[Budget] {sym} skipped: no heat budget")\n'
            "                        continue\n"
        ),
        "position": "replace",
        "payload": (
            "                    risk_frac = compute_portfolio_risk_frac(sig, cap_live, _open_for_budget, CFG)\n"
            "                    if risk_frac <= 0.0:\n"
            '                        log.debug(f"[Budget] {sym} skipped: no heat budget")\n'
            "                        continue\n"
            "                    # ══ [BEAR-SHIELD] Risk reduction ══\n"
            "                    if _bear_live:\n"
            "                        risk_frac *= _risk_mult_live\n"
        ),
    },
    {
        "id": "bs_cli_flags",
        "description": "Add Bear Shield CLI flags",
        "unique_marker": 'p.add_argument("--no-bear-shield"',
        "anchor": "    args = p.parse_args()\n",
        "position": "before",
        "payload": (
            "\n"
            "    # ══ [BEAR-SHIELD] CLI ══\n"
            '    p.add_argument("--no-bear-shield", action="store_true",\n'
            '                   help="Disable bear market protection")\n'
            '    p.add_argument("--bear-min-z", type=float, default=None,\n'
            '                   help="Min |z_dev| for BUY in bear (default 2.5)")\n'
            '    p.add_argument("--bear-risk-mult", type=float, default=None,\n'
            '                   help="Risk multiplier in bear (default 0.30)")\n'
            '    p.add_argument("--bear-max-concurrent", type=int, default=None,\n'
            '                   help="Max concurrent positions in bear (default 3)")\n'
            '    p.add_argument("--bear-min-score", type=int, default=None,\n'
            '                   help="Min score in bear (default 0)")\n'
            "\n"
        ),
    },
    {
        "id": "bs_cli_process",
        "description": "Process Bear Shield CLI flags",
        "unique_marker": "CFG.BEAR_SHIELD_ENABLED = False",
        "anchor": "    if args.no_numba: CFG.NUMBA_ENABLED = False\n",
        "position": "after",
        "payload": (
            "\n"
            "    # ══ [BEAR-SHIELD] Process CLI flags ══\n"
            '    if getattr(args, "no_bear_shield", False):\n'
            "        CFG.BEAR_SHIELD_ENABLED = False\n"
            '    if getattr(args, "bear_min_z", None) is not None:\n'
            "        CFG.BEAR_MIN_Z = float(args.bear_min_z)\n"
            '    if getattr(args, "bear_risk_mult", None) is not None:\n'
            "        CFG.BEAR_RISK_MULT = float(args.bear_risk_mult)\n"
            '    if getattr(args, "bear_max_concurrent", None) is not None:\n'
            "        CFG.BEAR_MAX_CONCURRENT = int(args.bear_max_concurrent)\n"
            '    if getattr(args, "bear_min_score", None) is not None:\n'
            "        CFG.BEAR_MIN_SCORE = int(args.bear_min_score)\n"
            "    if CFG.BEAR_SHIELD_ENABLED:\n"
            "        log.info(\n"
            '            f"[BearShield] ENABLED: min_z={CFG.BEAR_MIN_Z}, "\n'
            '            f"min_score={CFG.BEAR_MIN_SCORE}, "\n'
            '            f"risk_mult={CFG.BEAR_RISK_MULT:.0%}, "\n'
            '            f"max_concurrent={CFG.BEAR_MAX_CONCURRENT}")\n'
            "    else:\n"
            '        log.info("[BearShield] DISABLED")\n'
            "\n"
        ),
    },
    # ═══════════════════════════════════════════════════════════════════════
    # bs_report — الإصلاح الجوهري في v1.1
    # ═══════════════════════════════════════════════════════════════════════
    # الـ anchor القديم كان: '    print_report(m, "backtest")\n'
    # هذا يطابق السطر 10399 (8 مسافات) وأيضاً السطر 10409 (4 مسافات) → ambiguous(2)
    #
    # الـ anchor الجديد: يشمل السطر 10409 + السطر الفارغ 10410 + السطر 10411
    #                (print_report → '' → [Analytics] finalize)
    # هذا فريد 100% لأنه لا يوجد سياق آخر بنفس هذا التسلسل
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "bs_report",
        "description": "Log final market bias at end of backtest (v1.1 — full-context anchor)",
        "unique_marker": "# ══ [BEAR-SHIELD] Final bias report ══",
        "anchor": (
            '    print_report(m, "backtest")\n'
            "    \n"
            "    # ══ [Analytics] finalize backtest ══\n"
        ),
        "position": "replace",
        "payload": (
            '    print_report(m, "backtest")\n'
            "    \n"
            "    # ══ [BEAR-SHIELD] Final bias report ══\n"
            "    if getattr(CFG, 'BEAR_SHIELD_ENABLED', True):\n"
            "        _btc_final = (assets.get('BTC/USDT')\n"
            "                      or assets.get('BTC/USDT:USDT'))\n"
            "        if _btc_final is not None:\n"
            "            try:\n"
            "                _fb = _asset_bias_at_index(\n"
            "                    _btc_final, len(_btc_final.closes) - 1)\n"
            "                _lbl = ('BEAR' if _fb < 0 else\n"
            "                        ('BULL' if _fb > 0 else 'NEUTRAL'))\n"
            '                log.info(f"[BearShield] Final market bias: "\n'
            '                         f"{_fb:+.1f} ({_lbl})")\n'
            "            except Exception:\n"
            "                pass\n"
            "    \n"
            "    # ══ [Analytics] finalize backtest ══\n"
        ),
    },
]


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
        description="Bear Shield v1.1 — Bear Market Survival",
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
    print(f"Version:  {PATCH_VERSION}")
    print()

    if args.verify_only:
        ok, err = _verify_syntax(original)
        print(f"Syntax: {'✓ valid' if ok else '✗ ' + err}")
        for i, patch in enumerate(PATCHES, 1):
            present = patch["unique_marker"] in original
            cnt = 0 if present else original.count(patch["anchor"])
            status = "✓ applied" if present else (
                f"· pending (anchor×{cnt})" if cnt > 0 else "✗ anchor not found")
            print(f"  [{status:30s}] {i}. {patch['id']}")
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
        print("\n  No changes written.")
        return 1
    print("✓ Preflight: all 18 anchors present and unique")
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
    backup = f"{args.file}.preBEARSHIELD_{ts}.bak"
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
    print(f"✓ Bear Shield v{PATCH_VERSION} applied successfully")
    print(f"  Backup:   {backup}")
    print(f"  Manifest: {MANIFEST}")
    print()
    print("═══════════════════════════════════════════════════════════════════")
    print("اختبار Bear Shield — 3 مراحل")
    print("═══════════════════════════════════════════════════════════════════")
    print()
    print("1. سوق 2022 (الهابط الحاد — الاختبار الحقيقي):")
    print("   python trading_final.py --mode backtest [أمرك] \\")
    print("     --history-days 400 --end-date 2022-12-31")
    print()
    print("2. سوق 2023 (الصاعد — يجب ألا يتراجع):")
    print("   python trading_final.py --mode backtest [أمرك] \\")
    print("     --history-days 400 --end-date 2023-12-31")
    print()
    print("3. الفترة الكاملة (730 يوم — مقارنة مع baseline):")
    print("   python trading_final.py --mode backtest [أمرك]")
    print()
    print("═══════════════════════════════════════════════════════════════════")
    print("معايير النجاح:")
    print("═══════════════════════════════════════════════════════════════════")
    print("  2022 قبل: -30% إلى -50%  |  بعد: -5% إلى -15%")
    print("  2023 قبل: +50% إلى +100% |  بعد: لا تراجع (≥ 90% من الأداء)")
    print("  730d قبل: +X%           |  بعد: +X% أو أعلى")
    print()
    print("═══════════════════════════════════════════════════════════════════")
    print("الضبط (إذا الحاجة):")
    print("═══════════════════════════════════════════════════════════════════")
    print("  2022 لا يزال يخسر:  --bear-min-z 3.0 --bear-risk-mult 0.15 --bear-max-concurrent 2")
    print("  2023 تراجع:        --bear-min-z 2.0 --bear-risk-mult 0.50 --bear-max-concurrent 5")
    print("  لتعطيل:            --no-bear-shield")
    print()
    print("تراجع:")
    print("  python apply_bear_shield.py --rollback")
    print("═" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
