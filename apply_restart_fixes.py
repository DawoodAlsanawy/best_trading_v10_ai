#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_restart_fixes.py — Comprehensive Restart/Reload Defect Fixes
═══════════════════════════════════════════════════════════════════════════

يُصلح 7 عيوب جوهرية في البوت عند إعادة التشغيل:

  [FIX-C6] compute_dynamic_leverage: في live، استخدم --live-capital أو wallet،
           وليس --capital (لتفادي تغيير الرافعة بلا إعلام)

  [FIX-C5] peak_cap_live: يتتبع wallet وليس cap_live
           (لتفادي تجميد DD عند صفر مع --live-capital)

  [FIX-C5] تحذير عند --live-capital > wallet × 1.1
           (لتفادي over-risk خفي)

  [FIX-C5] dd_live: محسوب من wallet بدل cap_live (موضعان)

  [FIX-C1/C3] التحقق من _entry_ci وإعادة بناء peak_price بعد restart
              (لتفادي Trailing خاطئ و MaxHold فوري)

  [FIX-L1] منع _promote_pending_to_position من الكتابة فوق مركز موجود
           (لتفادي تكرار SL/TP)

═══════════════════════════════════════════════════════════════════════════

الاستخدام:
    python apply_restart_fixes.py --verify-only    # فحص مسبق
    python apply_restart_fixes.py --dry-run        # معاينة
    python apply_restart_fixes.py                  # تطبيق
    python apply_restart_fixes.py --rollback       # تراجع
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

TARGET = "trading_published_micro.py"
PATCH_VERSION = "1.0.0"
MANIFEST = ".restart_fixes_patches.json"


# ═══════════════════════════════════════════════════════════════════════════
# PATCHES
# ═══════════════════════════════════════════════════════════════════════════

PATCHES = [
    # ─── [FIX-C6] compute_dynamic_leverage: use live basis ───
    {
        "id": "fix_c6_leverage_basis",
        "description": "In live, compute leverage from --live-capital or wallet, not --capital",
        "unique_marker": "# [FIX-C6] Live leverage basis",
        "anchor": (
            "    C0 = cfg.INITIAL_CAPITAL\n"
            "    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / C0, 1.0))\n"
        ),
        "position": "replace",
        "payload": (
            "    # [FIX-C6] Live leverage basis: use --live-capital or wallet\n"
            "    _mode_c6 = str(getattr(cfg, 'mode', 'backtest')).lower()\n"
            "    if _mode_c6 in ('live', 'testnet'):\n"
            "        _fixed_c6 = float(getattr(cfg, 'LIVE_TRADING_CAPITAL', 0.0))\n"
            "        if _fixed_c6 > 0:\n"
            "            C0 = _fixed_c6\n"
            "        else:\n"
            "            C0 = max(float(capital), 1.0)\n"
            "    else:\n"
            "        C0 = cfg.INITIAL_CAPITAL\n"
            "    lev = cfg.LEVERAGE_BASE / np.sqrt(max(capital / max(C0, 1e-9), 1.0))\n"
        ),
    },

    # ─── [FIX-C5] Balance block: track _wallet_now separately ───
    {
        "id": "fix_c5_balance_wallet",
        "description": "Track _wallet_now in _LV_STATE (peak basis)",
        "unique_marker": "[FIX-C5] Track wallet separately",
        "anchor": (
            "                _LV_STATE['free'] = _bal_free\n"
            "                _LV_STATE['bal_ok'] = True\n"
            "                _last_known_cap = cap_live\n"
        ),
        "position": "replace",
        "payload": (
            "                _LV_STATE['free'] = _bal_free\n"
            "                _LV_STATE['bal_ok'] = True\n"
            "                _last_known_cap = cap_live\n"
            "                # [FIX-C5] Track wallet separately for peak\n"
            "                _wallet_now = _bal_total if _bal_total > 0 else _bal_free\n"
            "                _LV_STATE['_wallet_now'] = _wallet_now\n"
            "                # [FIX-C5] Warn if --live-capital > wallet\n"
            "                if _fixed_cap > 0 and _bal_total > 0 and _fixed_cap > _bal_total * 1.1:\n"
            "                    log.warning(f\"[FIX-C5] --live-capital (${_fixed_cap:.2f}) > wallet (${_bal_total:.2f}) x1.1 — over-risk!\")\n"
        ),
    },

    # ─── [FIX-C5] Peak block: use _wallet_now, not cap_live ───
    {
        "id": "fix_c5_peak_wallet",
        "description": "Peak tracking uses wallet basis (not fixed cap_live)",
        "unique_marker": "# [FIX-C5] Peak uses wallet basis",
        "anchor": (
            "            if _LV_STATE.get('bal_ok') and not _LV_STATE.get('peak_init'):\n"
            "                peak_cap_live = max(_lv_load_peak(cfg.mode), cap_live)\n"
            "                _LV_STATE['peak_init'] = True\n"
            "                _lv_save_peak(cfg.mode, peak_cap_live)\n"
            "            _lv_pk_prev = peak_cap_live\n"
            "            peak_cap_live = max(peak_cap_live, cap_live)\n"
            "            if _LV_STATE.get('peak_init') and peak_cap_live > _lv_pk_prev + 1e-9:\n"
            "                _lv_save_peak(cfg.mode, peak_cap_live)\n"
        ),
        "position": "replace",
        "payload": (
            "            # [FIX-C5] Peak uses wallet basis (not fixed cap_live)\n"
            "            _pk_basis = float(_LV_STATE.get('_wallet_now', cap_live))\n"
            "            if _pk_basis <= 0:\n"
            "                _pk_basis = cap_live\n"
            "            if _LV_STATE.get('bal_ok') and not _LV_STATE.get('peak_init'):\n"
            "                peak_cap_live = max(_lv_load_peak(cfg.mode), _pk_basis)\n"
            "                _LV_STATE['peak_init'] = True\n"
            "                _lv_save_peak(cfg.mode, peak_cap_live)\n"
            "            _lv_pk_prev = peak_cap_live\n"
            "            peak_cap_live = max(peak_cap_live, _pk_basis)\n"
            "            if _LV_STATE.get('peak_init') and peak_cap_live > _lv_pk_prev + 1e-9:\n"
            "                _lv_save_peak(cfg.mode, peak_cap_live)\n"
        ),
    },

    # ─── [FIX-C5] dd_live (first instance): use wallet ───
    {
        "id": "fix_c5_dd_primary",
        "description": "dd_live in main concurrency block uses wallet basis",
        "unique_marker": "# [FIX-C5] dd_live uses wallet basis (primary)",
        "anchor": (
            "            _n_open = len(open_pos_live)\n"
            "            dd_live = (peak_cap_live - cap_live) / (peak_cap_live + 1e-12)\n"
        ),
        "position": "replace",
        "payload": (
            "            _n_open = len(open_pos_live)\n"
            "            # [FIX-C5] dd_live uses wallet basis (primary)\n"
            "            _dd_basis = float(_LV_STATE.get('_wallet_now', cap_live))\n"
            "            if _dd_basis <= 0:\n"
            "                _dd_basis = cap_live\n"
            "            dd_live = (peak_cap_live - _dd_basis) / (peak_cap_live + 1e-12)\n"
        ),
    },

    # ─── [FIX-C5] dd_live (second instance): use wallet ───
    {
        "id": "fix_c5_dd_entry",
        "description": "dd_live in trade entry block uses wallet basis",
        "unique_marker": "# [FIX-C5] dd_live uses wallet basis (entry)",
        "anchor": (
            "                    # ══ [SAFETY] Drawdown-aware risk reduction ══\n"
            "                    # نحتاج peak_cap — نضيفه كمتغير خارجي\n"
            "                    if 'peak_cap_live' not in dir():\n"
            "                        pass  # placeholder\n"
            "                    dd_live = (peak_cap_live - cap_live) / (peak_cap_live + 1e-12)\n"
            "                    dd_mult = _get_risk_multiplier(dd_live)\n"
        ),
        "position": "replace",
        "payload": (
            "                    # ══ [SAFETY] Drawdown-aware risk reduction ══\n"
            "                    # نحتاج peak_cap — نضيفه كمتغير خارجي\n"
            "                    if 'peak_cap_live' not in dir():\n"
            "                        pass  # placeholder\n"
            "                    # [FIX-C5] dd_live uses wallet basis (entry)\n"
            "                    _dd_basis_e = float(_LV_STATE.get('_wallet_now', cap_live))\n"
            "                    if _dd_basis_e <= 0:\n"
            "                        _dd_basis_e = cap_live\n"
            "                    dd_live = (peak_cap_live - _dd_basis_e) / (peak_cap_live + 1e-12)\n"
            "                    dd_mult = _get_risk_multiplier(dd_live)\n"
        ),
    },

    # ─── [FIX-C1/C3] Post-restart validation (once per process) ───
    {
        "id": "fix_c1c3_validation",
        "description": "Validate _entry_ci + reconstruct peak_price after restart",
        "unique_marker": "# [FIX-C1/C3] Post-restart validation",
        "anchor": (
            "            _LV_ASSETS.clear()\n"
            "            _LV_ASSETS.update(assets)\n"
        ),
        "position": "after",
        "payload": (
            "            # [FIX-C1/C3] Post-restart validation (runs once per process)\n"
            "            if not _LV_STATE.get('_post_restart_validated', False) and open_pos_live:\n"
            "                _LV_STATE['_post_restart_validated'] = True\n"
            "                for _sym_v, _pos_v in list(open_pos_live.items()):\n"
            "                    _ad_v = assets.get(_sym_v)\n"
            "                    if _ad_v is None:\n"
            "                        continue\n"
            "                    try:\n"
            "                        _ci_old = int(_pos_v.get('_entry_ci', -1))\n"
            "                        if _ci_old < 0 or _ci_old >= len(_ad_v.closes):\n"
            "                            _ts_v = float(_pos_v.get('entry_ts', 0))\n"
            "                            if _ts_v > 0:\n"
            "                                _new_ci = int(np.searchsorted(\n"
            "                                    _ad_v.timestamps.asi8,\n"
            "                                    int(_ts_v * 1e9), side='right') - 1)\n"
            "                                _new_ci = max(0, min(_new_ci, len(_ad_v.closes) - 1))\n"
            "                            else:\n"
            "                                _new_ci = max(0, len(_ad_v.closes) - 100)\n"
            "                            _pos_v['_entry_ci'] = _new_ci\n"
            "                            log.warning(f\"[FIX-C3] {_sym_v} _entry_ci {_ci_old} -> {_new_ci}\")\n"
            "                            _ci_old = _new_ci\n"
            "                        if _ci_old >= 0 and _ci_old < len(_ad_v.closes):\n"
            "                            _action_v = str(_pos_v.get('action', 'BUY'))\n"
            "                            _entry_v = float(_pos_v.get('entry', 0))\n"
            "                            if _entry_v > 0:\n"
            "                                if _action_v == 'BUY':\n"
            "                                    _hi_r = float(np.max(_ad_v.highs[_ci_old:]))\n"
            "                                    _lo_r = float(np.min(_ad_v.lows[_ci_old:]))\n"
            "                                    _old_pk = float(_pos_v.get('peak_price', 0))\n"
            "                                    _new_pk = max(_old_pk, _hi_r)\n"
            "                                    if _new_pk > _old_pk:\n"
            "                                        log.info(f\"[FIX-C1] {_sym_v} peak {_old_pk:.6f} -> {_new_pk:.6f}\")\n"
            "                                        _pos_v['peak_price'] = _new_pk\n"
            "                                    _pos_v['_hi'] = max(float(_pos_v.get('_hi', 0)), _hi_r)\n"
            "                                    _pos_v['_lo'] = min(float(_pos_v.get('_lo', _entry_v)), _lo_r)\n"
            "                                else:\n"
            "                                    _lo_r = float(np.min(_ad_v.lows[_ci_old:]))\n"
            "                                    _hi_r = float(np.max(_ad_v.highs[_ci_old:]))\n"
            "                                    _old_pk = float(_pos_v.get('peak_price', 1e18))\n"
            "                                    _new_pk = min(_old_pk, _lo_r)\n"
            "                                    if _new_pk < _old_pk:\n"
            "                                        log.info(f\"[FIX-C1] {_sym_v} peak {_old_pk:.6f} -> {_new_pk:.6f}\")\n"
            "                                        _pos_v['peak_price'] = _new_pk\n"
            "                                    _pos_v['_lo'] = min(float(_pos_v.get('_lo', 1e18)), _lo_r)\n"
            "                                    _pos_v['_hi'] = max(float(_pos_v.get('_hi', _entry_v)), _hi_r)\n"
            "                    except Exception as _e_v:\n"
            "                        log.debug(f\"[FIX-C1] {_sym_v} reconstruct failed: {_e_v}\")\n"
        ),
    },

    # ─── [FIX-L1] Duplicate promote guard ───
    {
        "id": "fix_l1_duplicate_promote",
        "description": "Prevent _promote_pending_to_position from overwriting existing positions",
        "unique_marker": "# [FIX-L1] Prevent duplicate promote",
        "anchor": (
            "def _promote_pending_to_position(exchange, sym: str, rec: Dict,\n"
            "                                 open_pos_live: Dict) -> bool:\n"
            "    \"\"\"Convert a filled pending order into an open position record.\"\"\"\n"
            "    filled_qty = float(rec.get('filled') or 0.0)\n"
            "    total_qty = float(rec.get('qty') or 0.0)\n"
            "    entry_price = float(rec.get('avg_price') or rec.get('price') or 0.0)\n"
            "    if filled_qty <= 0 or entry_price <= 0 or total_qty <= 0:\n"
            "        return False\n"
        ),
        "position": "replace",
        "payload": (
            "def _promote_pending_to_position(exchange, sym: str, rec: Dict,\n"
            "                                 open_pos_live: Dict) -> bool:\n"
            "    \"\"\"Convert a filled pending order into an open position record.\"\"\"\n"
            "    # [FIX-L1] Prevent duplicate promote\n"
            "    if sym in open_pos_live:\n"
            "        _existing_qty = float(open_pos_live[sym].get('qty', 0) or 0)\n"
            "        if _existing_qty > 0:\n"
            "            log.warning(f\"[FIX-L1] {sym} already has position qty={_existing_qty}, skipping duplicate promote\")\n"
            "            return False\n"
            "    filled_qty = float(rec.get('filled') or 0.0)\n"
            "    total_qty = float(rec.get('qty') or 0.0)\n"
            "    entry_price = float(rec.get('avg_price') or rec.get('price') or 0.0)\n"
            "    if filled_qty <= 0 or entry_price <= 0 or total_qty <= 0:\n"
            "        return False\n"
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
        description="Comprehensive restart/reload defect fixes",
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
        print()
        for i, patch in enumerate(PATCHES, 1):
            present = patch["unique_marker"] in original
            cnt = 0 if present else original.count(patch["anchor"])
            status = "✓ applied" if present else (
                f"· pending (anchor×{cnt})" if cnt > 0 else "✗ anchor NOT FOUND")
            print(f"  [{status:30s}] {i}. {patch['id']}")
            if not present and cnt == 0:
                # Show first 60 chars of anchor to help debug
                print(f"       anchor starts: {patch['anchor'][:60]!r}")
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
        print("  شغّل --verify-only لرؤية تفاصيل كل anchor.")
        print("  أرسل المخرجات إذا احتجت تصحيحاً.")
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
    backup = f"{args.file}.preRESTART_{ts}.bak"
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
    print(f"✓ Restart Fixes v{PATCH_VERSION} applied successfully")
    print(f"  Backup:   {backup}")
    print(f"  Manifest: {MANIFEST}")
    print()
    print("═══════════════════════════════════════════════════════════════════")
    print("ما تم إصلاحه:")
    print("═══════════════════════════════════════════════════════════════════")
    print("  [C6] compute_dynamic_leverage: live uses --live-capital/wallet")
    print("  [C5] peak_cap_live: tracks wallet (DD no longer frozen at 0)")
    print("  [C5] Warning: --live-capital > wallet × 1.1 → over-risk alert")
    print("  [C5] dd_live: computed from wallet (2 locations)")
    print("  [C1] peak_price: reconstructed from candles after restart")
    print("  [C3] _entry_ci: validated against data length after restart")
    print("  [L1] Duplicate promote: prevented overwriting existing positions")
    print()
    print("═══════════════════════════════════════════════════════════════════")
    print("الاختبار:")
    print("═══════════════════════════════════════════════════════════════════")
    print(f"  1. python3 {args.file} --mode backtest [أمرك]    # baseline (no change)")
    print(f"  2. python3 {args.file} --mode testnet [أمرك]     # باول قيمة --live-capital")
    print()
    print("  افتح الـ log وابحث عن:")
    print("    [FIX-C5] --live-capital ... over-risk  (إن وُجد)")
    print("    [FIX-C5] DD uses wallet basis  (يظهر في سلوك risk)")
    print("    [FIX-C1] peak reconstructed  (عند restart)")
    print("    [FIX-C3] _entry_ci validated  (عند restart)")
    print("    [FIX-L1] skipping duplicate promote  (إن وُجد)")
    print()
    print("تراجع:")
    print(f"  python apply_restart_fixes.py --rollback")
    print("═" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
