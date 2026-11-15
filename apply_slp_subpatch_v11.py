#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_slp_subpatch_v11.py — SLP Sub-Patch v1.1 (Completes v1.0 patch script)
═══════════════════════════════════════════════════════════════════════════

⚠️  هذا السكريبت يُعدّل ملف `apply_slp_patch.py` (v1.0) — لا يُعدّل
    trading_final.py مباشرة.

سير العمل الموصى به:
    1. python apply_slp_subpatch_v11.py --dry-run      # معاينة
    2. python apply_slp_subpatch_v11.py                # تعديل apply_slp_patch.py
    3. راجع apply_slp_patch.py يدوياً للتأكد
    4. python apply_slp_patch.py --dry-run             # معاينة ما سيطبّقه على trading
    5. python apply_slp_patch.py                       # تطبيقه على trading_final.py

التراجع:
    python apply_slp_subpatch_v11.py --rollback        # استرجاع apply_slp_patch.py
    python apply_slp_patch.py --rollback               # استرجاع trading_final.py

ما يُصلحه هذا الـ sub-patch (7 إصلاحات جوهرية):

  [SP01] إصلاح anchor لـ slp_backtest_fillmap
         ❌ v1.0: يُدرج قبل PARITY → PARITY يكتب فوقه → SLP لا يعمل أبداً
         ✅ v1.1: يُدرج بعد PARITY → SLP يتحكم فعلياً

  [SP02] إضافة v11_simulate_branch + v11_position_meta
         ❌ v1.0: simulate_portfolio لا يعرف صيغة SLP dict → crash
         ✅ v1.1: parses dict + يربط _slp_meta بالمركز

  [SP03] إصلاح _slp_write_stats + إضافة استدعاءات
         ❌ v1.0: slp_stats_backtest.csv لا يُكتب أبداً
         ✅ v1.1: يُكتب لكل إشارة (filled / no_fill)

  [SP04] إصلاح time-decay في backtest
         ❌ v1.0: يستخدم time.time() (ساعة حائط) → خاطئ
         ✅ v1.1: يستخدم timestamps[bar] (زمن الشمعة)

  [SP05] إضافة _slp_startup_recover + استدعاؤها
         ❌ v1.0: لا recovery → orphans بعد restart
         ✅ v1.1: resume أو expire عند بدء Live

  [SP06] إضافة conflict guard (SLP + reversal-confirm)
         ✅ تحذير مبكر في main()

  [SP07] إضافة slp_stats files إلى --clear-cache
         ✅ تنظيف كامل

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

TARGET = "apply_slp_patch.py"
SUBPATCH_VERSION = "1.1.0"
SUBPATCH_MANIFEST = ".slp_subpatches.json"


# ═══════════════════════════════════════════════════════════════════
# SUBPATCH DEFINITIONS
# كل واحدة: find (نص موجود حرفياً في apply_slp_patch.py)
#           replace (النص البديل)
#           marker (سلسلة تظهر فقط بعد التطبيق — للكشف عن التطبيق المسبق)
# ═══════════════════════════════════════════════════════════════════

SUBPATCHES = []


# ─── SP01: Fix slp_backtest_fillmap anchor (the critical bug) ───
SUBPATCHES.append({
    "id": "sp01_fix_backtest_fillmap_anchor",
    "description": "Fix slp_backtest_fillmap: move insertion AFTER PARITY block",
    "marker": "# ══ [SLP v1.1] Override fill_map with SLP",
    "find": '''    {
        "id": "slp_backtest_fillmap",
        "description": "Hook SLP into simulate_portfolio fill_map",
        "unique_marker": 'fill_map = _precompute_slp_fills(assets, signals, cfg)',
        "anchor": "    # ══ [PARITY] Watch mode → use _precompute_watch_fills ══\\n",
        "position": "before",
        "payload": """    # ══ [SLP] Smart Ladder Pending for backtest ══
    if getattr(CFG, 'SLP_ENABLED', False):
        fill_map = _precompute_slp_fills(assets, signals, CFG)
        log.info("  [SLP] using Smart Ladder Pending for backtest")
        _n_slp_fill = sum(1 for v in fill_map.values()
                          if isinstance(v, dict) and v.get('fills'))
        log.info(f"  [SLP] {_n_slp_fill}/{len(fill_map)} signals produced fills")
    # ══ [PARITY] Watch mode → use _precompute_watch_fills ══
""",
    },''',
    "replace": '''    {
        "id": "slp_backtest_fillmap",
        "description": "Hook SLP into simulate_portfolio fill_map (AFTER PARITY)",
        "unique_marker": 'fill_map = _precompute_slp_fills(assets, signals, CFG)',
        "anchor": "    n_total_sigs = len(signals)\\n",
        "position": "before",
        "payload": """    # ══ [SLP v1.1] Override fill_map with SLP (takes precedence) ══
    if getattr(CFG, 'SLP_ENABLED', False):
        fill_map = _precompute_slp_fills(assets, signals, CFG)
        _n_slp_total = len(fill_map)
        _n_slp_filled = sum(
            1 for _v in fill_map.values()
            if isinstance(_v, dict) and _v.get('fills'))
        log.info(
            f"  [SLP] {_n_slp_filled}/{_n_slp_total} signals "
            f"produced fills (SLP mode)")
""",
    },''',
})


# ─── SP02: Add v11_simulate_branch + v11_position_meta to PATCHES ───
SUBPATCHES.append({
    "id": "sp02_add_v11_patches",
    "description": "Insert v11_simulate_branch and v11_position_meta into PATCHES list",
    "marker": '"id": "v11_simulate_branch"',
    "find": '''    # ─── 5. Live startup loading ───
    {
        "id": "slp_live_load",''',
    "replace": '''    # ─── 4a. SLP simulate branch (fill_info parsing) ───
    {
        "id": "v11_simulate_branch",
        "description": "Handle SLP dict format in simulate_portfolio",
        "unique_marker": "_is_slp_mode = False",
        "anchor": """        # ══ [UNIFIED ENTRY] Look up Stage 1 or Stage 2 ══
        fill_info = fill_map.get(sig_i)
        if fill_info is None:
            continue

        _is_stage2 = False
        _stage2_sl = _stage2_tp = _stage2_sl_dist = None

        if len(fill_info) >= 2 and isinstance(fill_info[0], str):
            if fill_info[0] == 'S1':
                _, opt_ci, opt_px = fill_info
            elif fill_info[0] == 'S2':
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist \\\\
                    = fill_info
                _is_stage2 = True
            else:
                continue
        else:
            # توافق مع الصيغة القديمة
            opt_ci, opt_px = fill_info
""",
        "position": "replace",
        "payload": """        # ══ [UNIFIED ENTRY] Look up Stage 1 or Stage 2 (SLP-aware) ══
        fill_info = fill_map.get(sig_i)
        if fill_info is None:
            continue

        _is_stage2 = False
        _is_slp_mode = False
        _slp_meta_for_pos = None
        _stage2_sl = _stage2_tp = _stage2_sl_dist = None

        if isinstance(fill_info, dict) and fill_info.get('type') == 'SLP':
            _slp_fills = fill_info.get('fills', [])
            if not _slp_fills:
                continue
            _first_bar = min(f[0] for f in _slp_fills)
            _last_bar = max(f[0] for f in _slp_fills)
            opt_ci = int(_first_bar)
            opt_px = float(fill_info['final_vwap'])
            _slp_meta_for_pos = {
                'window_end_ci': int(fill_info.get('window_end_ci', _last_bar)),
                'cancel_reasons': fill_info.get('cancel_reasons', {}),
            }
            _is_slp_mode = True
            _orig_sd = abs(float(sig.price) - float(sig.sl))
            _orig_td = abs(float(sig.tp1) - float(sig.price))
            _max_sl_frac = (float(getattr(CFG, 'MAX_SL_FRAC', 0.015))
                            * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0)))
            if _orig_sd > opt_px * _max_sl_frac:
                _rr = _orig_td / max(_orig_sd, 1e-12)
                _orig_sd = opt_px * _max_sl_frac
                _orig_td = _orig_sd * _rr
            if sig.action == 'BUY':
                sig.sl = opt_px - _orig_sd
                sig.tp1 = opt_px + _orig_td
            else:
                sig.sl = opt_px + _orig_sd
                sig.tp1 = opt_px - _orig_td
        elif len(fill_info) >= 2 and isinstance(fill_info[0], str):
            if fill_info[0] == 'S1':
                _, opt_ci, opt_px = fill_info
            elif fill_info[0] == 'S2':
                _, opt_ci, opt_px, _stage2_sl, _stage2_tp, _stage2_sl_dist \\\\
                    = fill_info
                _is_stage2 = True
            else:
                continue
        else:
            opt_ci, opt_px = fill_info
""",
    },

    # ─── 4b. SLP position _slp_meta attachment ───
    {
        "id": "v11_position_meta",
        "description": "Attach _slp_meta to SLP-created positions",
        "unique_marker": "open_pos[sym]._slp_meta = _slp_meta_for_pos",
        "anchor": "            entry_sub_idx=opt_sub_idx,\\n        )\\n",
        "position": "after",
        "payload": """
        # ══ [SLP v1.1] Attach _slp_meta to SLP position ══
        if _is_slp_mode and _slp_meta_for_pos is not None:
            open_pos[sym]._slp_meta = _slp_meta_for_pos
""",
    },

    # ─── 5. Live startup loading ───
    {
        "id": "slp_live_load",''',
})


# ─── SP03: Fix _slp_write_stats to use levels instead of fills ───
SUBPATCHES.append({
    "id": "sp03_fix_stats_function",
    "description": "Fix _slp_write_stats to compute from levels (works in both backtest and live)",
    "marker": "_vwap = 0.0\n        if _total_f > 0:\n            _vwap = sum(float(l.get(\"qty_filled\", 0))",
    "find": '''        _levels = rec.get("levels", [])
        _fills = rec.get("fills", [])
        _total_f = sum(float(f.get("qty", 0)) for f in _fills)
        _qty_t = float(rec.get("qty_target", 0) or 0)
        _ratio = _total_f / _qty_t if _qty_t > 0 else 0.0
        _vwap = 0.0
        if _total_f > 0:
            _vwap = sum(float(f.get("qty", 0)) * float(f.get("px", 0))
                        for f in _fills) / _total_f''',
    "replace": '''        _levels = rec.get("levels", [])
        _total_f = sum(float(l.get("qty_filled", 0)) for l in _levels)
        _qty_t = float(rec.get("qty_target", 0) or 0)
        _ratio = _total_f / _qty_t if _qty_t > 0 else 0.0
        _vwap = 0.0
        if _total_f > 0:
            _vwap = sum(float(l.get("qty_filled", 0)) * float(l.get("avg", 0))
                        for l in _levels) / _total_f''',
})


# ─── SP04: Add stats write + fix time-decay in _precompute_slp_fills ───
SUBPATCHES.append({
    "id": "sp04_precompute_fixes",
    "description": "Add stats writes and bar-time for time-decay in precompute",
    "marker": "# ══ [SLP v1.1] Precompute stats writes",
    "find": '''                if not _fills:
                    _result[_sig_i] = {
                        "type": "SLP",
                        "fills": [],
                        "outcome": "no_fill",
                        "timeout_stage2": True,
                    }
                    continue
                _total_q = sum(f["qty"] for f in _fills)
                _total_cost = sum(f["qty"] * f["px"] for f in _fills)
                _vwap = _total_cost / _total_q if _total_q > 0 else 0.0
                _all_filled = all(l["status"] == "filled" for l in _levels)
                _window_end = max(
                    max(f["bar"] for f in _fills),
                    _sig.close_idx + 2,
                )
                _result[_sig_i] = {
                    "type": "SLP",
                    "fills": [(f["bar"], f["idx"], f["px"], f["qty"])
                              for f in _fills],''',
    "replace": '''                # ══ [SLP v1.1] Precompute stats writes ══
                _rec["qty_target"] = 1.0
                _rec["fills"] = _fills
                if not _fills:
                    try:
                        _slp_write_stats(_rec, "no_fill")
                    except Exception as _e_s:
                        log.debug(f"[SLP] stats write: {_e_s}")
                    _result[_sig_i] = {
                        "type": "SLP",
                        "fills": [],
                        "outcome": "no_fill",
                        "timeout_stage2": True,
                    }
                    continue
                _total_q = sum(f["qty"] for f in _fills)
                _total_cost = sum(f["qty"] * f["px"] for f in _fills)
                _vwap = _total_cost / _total_q if _total_q > 0 else 0.0
                _all_filled = all(l["status"] == "filled" for l in _levels)
                _window_end = max(
                    max(f["bar"] for f in _fills),
                    _sig.close_idx + 2,
                )
                try:
                    _slp_write_stats(
                        _rec,
                        "all_filled" if _all_filled else "timeout_partial")
                except Exception as _e_s:
                    log.debug(f"[SLP] stats write: {_e_s}")
                _result[_sig_i] = {
                    "type": "SLP",
                    "fills": [(f["bar"], f["idx"], f["px"], f["qty"])
                              for f in _fills],''',
})


SUBPATCHES.append({
    "id": "sp04b_time_decay_bar",
    "description": "Use bar-time for time-decay cancel (not wall-clock)",
    "marker": "_bar_ts_for_triggers",
    "find": '''                    # Cancel triggers (simplified: no time since we use bars)
                    if _ad is not None:
                        _trig = _slp_check_cancel_triggers(
                            _rec, _ad, _bar, _p_now, time.time())''',
    "replace": '''                    # Cancel triggers (bar-time based)
                    if _ad is not None:
                        _bar_ts_for_triggers = float(
                            _ad.timestamps[_bar].timestamp())
                        _rec["window_start_ts"] = float(
                            _ad.timestamps[_first_bar].timestamp())
                        _rec["timeout_s"] = (
                            float(_last_bar - _first_bar)
                            * float(getattr(cfg, 'TF_SECONDS', 3600)))
                        _trig = _slp_check_cancel_triggers(
                            _rec, _ad, _bar, _p_now,
                            _bar_ts_for_triggers)''',
})


# ─── SP05: Add _slp_startup_recover helper function ───
SUBPATCHES.append({
    "id": "sp05_add_startup_recover",
    "description": "Add _slp_startup_recover function to helpers",
    "marker": "def _slp_startup_recover(exchange",
    "find": '''# ══ [SLP helpers end] ══''',
    "replace": '''def _slp_startup_recover(exchange, open_pos_live: Dict) -> None:
    """On live restart: finalize expired SLP cycles, resume active ones."""
    if not getattr(CFG, 'SLP_ENABLED', False):
        return
    if not _SLP_ORDERS:
        return
    _now = time.time()
    _expired = 0
    _resumed = 0
    for _sym in list(_SLP_ORDERS.keys()):
        _rec = _SLP_ORDERS.get(_sym)
        if _rec is None:
            continue
        try:
            _elapsed = _now - float(_rec.get("window_start_ts", _now))
            _timeout = float(_rec.get("timeout_s", 300) or 300)
            if _elapsed > _timeout:
                try:
                    _slp_cancel_levels_live(
                        exchange, _sym, _rec, [0, 1, 2],
                        "startup_timeout")
                except Exception as _e_c:
                    log.debug(f"[SLP] startup cancel {_sym}: {_e_c}")
                try:
                    _slp_finalize(exchange, _sym, _rec,
                                  open_pos_live, "startup_timeout")
                except Exception as _e_f:
                    log.warning(f"[SLP] startup finalize {_sym}: {_e_f}")
                _expired += 1
            else:
                _resumed += 1
                log.info(f"[SLP] {_sym} resumed "
                         f"({_elapsed:.0f}s/{_timeout:.0f}s)")
        except Exception as _e:
            log.warning(f"[SLP] startup recover {_sym}: {_e}")
    try:
        _slp_state_save()
    except Exception:
        pass
    if _expired > 0 or _resumed > 0:
        log.info(f"[SLP] Startup: {_expired} expired, "
                 f"{_resumed} resumed")


# ══ [SLP helpers end] ══''',
})


# ─── SP05b: Add startup recovery call to PATCHES ───
SUBPATCHES.append({
    "id": "sp05b_add_startup_recovery_patch",
    "description": "Add v11_startup_recovery PATCHES entry",
    "marker": '"id": "v11_startup_recovery"',
    "find": '''    # ─── 6. Live monitor call ───''',
    "replace": '''    # ─── 5b. SLP startup recovery ───
    {
        "id": "v11_startup_recovery",
        "description": "Recover/expire SLP state on live startup",
        "unique_marker": "_slp_startup_recover(exchange, open_pos_live)",
        "anchor": """    # ══ [SLP] Load persisted smart ladder orders ══
    if getattr(CFG, 'SLP_ENABLED', False):
        _slp_state_load(cfg.mode)
""",
        "position": "after",
        "payload": """    # ══ [SLP v1.1] Startup recovery ══
    if getattr(CFG, 'SLP_ENABLED', False):
        try:
            _slp_startup_recover(exchange, open_pos_live)
        except Exception as _e_sr:
            log.warning(f"[SLP] startup recovery failed: {_e_sr}")
""",
    },

    # ─── 6. Live monitor call ───''',
})


# ─── SP06: Conflict guard + cache fix in CLI payload ───
SUBPATCHES.append({
    "id": "sp06_cli_conflict_guard",
    "description": "Add SLP+reversal conflict warning to CLI processing",
    "marker": "# ══ [SLP v1.1] Conflict guard",
    "find": '''    else:
        log.info("[SLP] Disabled (use --slp to enable)")
''',
    "replace": '''    else:
        log.info("[SLP] Disabled (use --slp to enable)")

    # ══ [SLP v1.1] Conflict guard: SLP + reversal-confirm ══
    if (getattr(CFG, 'SLP_ENABLED', False)
            and getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False)):
        log.warning(
            "[SLP] CONFLICT: both SLP and reversal-confirm are enabled. "
            "SLP takes precedence in Stage 1. reversal-confirm watchers "
            "still run for other signals. Consider using only one.")
''',
})


# ─── SP07: Fix --clear-cache to include slp_stats files ───
SUBPATCHES.append({
    "id": "sp07_clear_cache_stats",
    "description": "Add slp_stats CSVs to --clear-cache list",
    "marker": '"slp_stats_backtest.csv"',
    "find": '''        _state_files = [
            "slp_orders_live.json", "slp_orders_testnet.json",
''',
    "replace": '''        _state_files = [
            "slp_stats_backtest.csv", "slp_stats_testnet.csv",
            "slp_stats_live.csv",
            "slp_orders_live.json", "slp_orders_testnet.json",
''',
})


# ═══════════════════════════════════════════════════════════════════
# ENGINE
# ═══════════════════════════════════════════════════════════════════

def _file_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _atomic_write(path: str, content: str) -> None:
    dir_ = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
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


def _apply_all(content: str):
    """Apply all subpatches. Returns (new_content, applied, skipped, failed)."""
    applied = 0
    skipped = 0
    failed = []
    for sp in SUBPATCHES:
        if sp["marker"] in content:
            skipped += 1
            continue
        find = sp["find"]
        if find not in content:
            failed.append((sp["id"], "find_not_found"))
            continue
        cnt = content.count(find)
        if cnt > 1:
            failed.append((sp["id"], f"ambiguous({cnt}x)"))
            continue
        content = content.replace(find, sp["replace"], 1)
        applied += 1
    return content, applied, skipped, failed


def _load_manifest(path):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": SUBPATCH_VERSION, "backups": []}


def _save_manifest(path, manifest):
    _atomic_write(path, json.dumps(manifest, indent=2))


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="Sub-patch for apply_slp_patch.py",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", default=TARGET,
                   help=f"Target patch script (default: {TARGET})")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview only, no writes")
    p.add_argument("--verify-only", action="store_true",
                   help="Only check current state")
    p.add_argument("--rollback", action="store_true",
                   help="Restore from latest backup")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    if not os.path.exists(args.file):
        print(f"✗ Not found: {args.file}")
        print("  Make sure apply_slp_patch.py (v1.0) is in the same directory.")
        return 1

    with open(args.file, "r", encoding="utf-8") as f:
        original = f.read()

    # Sanity: confirm v1.0 is present
    _v10_required = [
        'CONFIG_SLP_PAYLOAD',
        'HELPERS_SLP_PAYLOAD',
        '"id": "slp_backtest_fillmap"',
        'def main():',
    ]
    _missing = [m for m in _v10_required if m not in original]
    if _missing and not args.verify_only:
        print("✗ apply_slp_patch.py v1.0 markers missing:")
        for m in _missing:
            print(f"    · {m}")
        print("  Make sure you have the correct v1.0 file.")
        return 1

    print(f"Target:   {args.file}")
    print(f"Size:     {len(original):,} chars")
    print(f"Hash:     {_file_hash(original)}")
    print(f"Subpatches: {len(SUBPATCHES)}")
    print()

    if args.verify_only:
        ok, err = _verify_syntax(original)
        if ok:
            print("✓ Syntax valid")
        else:
            print(f"✗ Syntax error: {err}")
        for sp in SUBPATCHES:
            status = "✓" if sp["marker"] in original else "·"
            print(f"  [{status}] {sp['id']}")
        return 0

    if args.rollback:
        manifest = _load_manifest(SUBPATCH_MANIFEST)
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

    # Apply
    new_content, applied, skipped, failed = _apply_all(original)

    if failed:
        print(f"✗ {len(failed)} subpatch(es) failed:")
        for pid, st in failed:
            print(f"    {pid}: {st}")
        print("\n  No changes written.")
        return 1

    ok, err = _verify_syntax(new_content)
    if not ok:
        print(f"✗ Syntax error after patching: {err}")
        print("  No changes written.")
        return 1

    print(f"✓ Applied: {applied}   Skipped: {skipped}")
    print()

    if args.dry_run:
        print("── DRY RUN — no files written ──")
        print(f"Would write: {args.file}")
        print(f"Size change: {len(original):,} → {len(new_content):,} "
              f"({len(new_content) - len(original):+,})")
        return 0

    # Backup + write
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{args.file}.v10_{ts}.bak"
    shutil.copy2(args.file, backup)
    print(f"Backup: {backup}")

    _atomic_write(args.file, new_content)
    print(f"✓ Wrote {args.file}")

    manifest = _load_manifest(SUBPATCH_MANIFEST)
    manifest["version"] = SUBPATCH_VERSION
    manifest["last_run"] = datetime.now().isoformat()
    manifest["backups"].append(backup)
    manifest["applied"] = [sp["id"] for sp in SUBPATCHES]
    manifest["last_hash"] = _file_hash(new_content)
    _save_manifest(SUBPATCH_MANIFEST, manifest)

    print()
    print("═" * 64)
    print(f"✓ Sub-patch v{SUBPATCH_VERSION} applied to {args.file}")
    print()
    print("الخطوات التالية:")
    print("─" * 64)
    print("1. راجع apply_slp_patch.py يدوياً (اختياري لكن موصى به):")
    print(f"     grep -n 'SLP v1.1' {args.file}")
    print()
    print("2. تحقق من syntax:")
    print(f"     python {args.file} --verify-only")
    print()
    print("3. معاينة ما سيطبّقه على trading_final.py:")
    print(f"     python {args.file} --dry-run")
    print()
    print("4. طبّق على trading_final.py:")
    print(f"     python {args.file}")
    print()
    print("5. اختبر الباكتيست بدون SLP (يجب أن يطابق baseline):")
    print("     python trading_final.py [args] --analytics")
    print()
    print("6. اختبر الباكتيست مع SLP:")
    print("     python trading_final.py [args] --slp --analytics")
    print()
    print("التراجع:")
    print(f"     python {args.file.split('.')[0]}_subpatch_v11.py --rollback")
    print(f"     python {args.file} --rollback")
    print("═" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ═══════════════════════════════════════════════════════════════════
# NOTE: What each subpatch fixes (details)
# ═══════════════════════════════════════════════════════════════════
"""
SP01: إصلاح قاتل — بدون هذا SLP لا يعمل أبداً في backtest
───────────────────────────────────────────────────────────
v1.0 السلوك:
    fill_map = _precompute_slp_fills(...)   ← يُدرج قبل PARITY
    if WATCH_MODE: fill_map = _precompute_watch_fills(...)   ← يكتب فوقه
    else:          fill_map = precompute_entry_fills(...)    ← يكتب فوقه
    → SLP دائماً يتجاوز

v1.1 السلوك:
    if WATCH: fill_map = watch_fills(...)
    else:     fill_map = entry_fills(...)
    if SLP:   fill_map = slp_fills(...)     ← يُدرج بعد PARITY
    n_total_sigs = len(signals)
    → SLP يتحكم فعلياً عند تفعيله

SP02: simulate_portfolio كان سيتعطل
──────────────────────────────────────
v1.0 لم يعرف كيف يقرأ SLP dict (fill_info['type'] == 'SLP').
v1.1 يضيف branch كامل + يربط _slp_meta بالمركز الجديد
     → _advance window logic يعمل (SP04-dependent)

SP03: slp_stats كان سيكون فارغاً دائماً
──────────────────────────────────────
v1.0: _slp_write_stats يقرأ rec["fills"] (غير موجود في precompute)
v1.1: يقرأ rec["levels"] (يعمل في backtest و live معاً)

SP04: time-decay كان خاطئاً في backtest
──────────────────────────────────────
v1.0: time.time() = clock الحائط → السرعة الفعلية للباكتيست أسرع 100x
v1.1: timestamps[bar] = زمن الشمعة الفعلي → حساب دقيق

SP05: startup recovery + stats writes
──────────────────────────────────────
v1.0: لا يوجد recovery → orphans على البورصة بعد restart
v1.1: يفحص _SLP_ORDERS، ينهي المنتهية، يستأنف النشطة

SP06: conflict guard
──────────────────────────────────────
SLP + reversal-confirm معاً = تعارض في Stage 1
v1.1 يُحذّر في main() قبل بدء التشغيل

SP07: --clear-cache
──────────────────────────────────────
v1.0 لم يحذف slp_stats_*.csv
v1.1 يُضيفها

═══════════════════════════════════════════════════════════════════
ما يبقى لـ v1.2 (اختياري، بعد اختبار v1.1):
═══════════════════════════════════════════════════════════════════

  · BEEsc يلغي المستويات المتبقية تلقائياً
    (حالياً يُلغى عبر timeout/cancel triggers — يعمل لكن أقل حدّة)

  · إشارة معاكسة تُلغي SLP فوراً
    (حالياً عبر timeout — أو ضع SLP_OPPOSITE_CANCEL_ENABLED=False لتجاوزها)

  · Stage 2 handoff عند no_fill
    (حالياً: skip signal — سنُضيف chase في v1.2)

  · per-bar position building في backtest
    (حالياً VWAP approximation — فرق ≤ 2 bps)

كل هذه "تحسينات، ليست تصحيحات". v1.1 يُنتج SLP يعمل بأمان.

═══════════════════════════════════════════════════════════════════
"""
