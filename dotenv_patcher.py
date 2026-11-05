#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  DOTENV Patcher — Load API keys + mode from .env file                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  يطبّق 4 تعديلات ذرية:                                                       ║
║    P01: _load_dotenv() helper + استدعاؤه عند تحميل الموديول                   ║
║    P02: --mode default يقرأ من MODE env var                                  ║
║    P03: علامة [DOTENV-APPLIED] في أعلى الملف                                  ║
║    P04: تسجيل حالة .env عند بدء التشغيل                                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  USAGE:                                                                      ║
║    python3 dotenv_patcher.py                 # apply                        ║
║    python3 dotenv_patcher.py --dry-run       # preview                      ║
║    python3 dotenv_patcher.py --verify-only   # check                        ║
║    python3 dotenv_patcher.py --rollback      # restore latest backup        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"
MARKER = "# ═══ [DOTENV-APPLIED] ═══"


PATCHES = [

    # ═══════════════════════════════════════════════════════════════════════
    # P01 — Insert _load_dotenv() helper + call at module load
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P01-dotenv-helper",
        "desc": "Insert _load_dotenv() helper and call it at module load",
        "old": (
            "warnings.filterwarnings(\"ignore\")\n"
            "\n"
            "# ══ [WATCH-REMOVED-MASTER] "
        ),
        "new": (
            "warnings.filterwarnings(\"ignore\")\n"
            "\n"
            "# ══ [DOTENV] Load .env into os.environ at module start ═══════════════\n"
            "# Runs BEFORE _setup_logging() so that env vars from .env\n"
            "# (QTT_LOG_FILE, etc.) influence logging. Searches CWD first,\n"
            "# then the script directory.\n"
            "_DOTENV_LOADED = 0\n"
            "\n"
            "\n"
            "def _load_dotenv(path: str = \".env\") -> int:\n"
            "    \"\"\"Load KEY=VALUE pairs from .env into os.environ.\n"
            "\n"
            "    - Does NOT override existing os.environ entries (dotenv rule).\n"
            "    - Supports: comments (#), quotes, `export KEY=value`.\n"
            "    - Returns: number of NEW env vars added.\n"
            "    \"\"\"\n"
            "    global _DOTENV_LOADED\n"
            "    candidates = [path]\n"
            "    try:\n"
            "        _script_dir = os.path.dirname(os.path.abspath(__file__))\n"
            "        candidates.append(os.path.join(_script_dir, path))\n"
            "    except Exception:\n"
            "        pass\n"
            "    actual = None\n"
            "    for _p in candidates:\n"
            "        if os.path.exists(_p):\n"
            "            actual = _p\n"
            "            break\n"
            "    if actual is None:\n"
            "        _DOTENV_LOADED = 0\n"
            "        return 0\n"
            "    loaded = 0\n"
            "    try:\n"
            "        with open(actual, \"r\", encoding=\"utf-8\") as _f:\n"
            "            for _raw in _f:\n"
            "                _line = _raw.strip()\n"
            "                if not _line or _line.startswith(\"#\"):\n"
            "                    continue\n"
            "                if \"=\" not in _line:\n"
            "                    continue\n"
            "                _k, _, _v = _line.partition(\"=\")\n"
            "                _k = _k.strip()\n"
            "                if _k.startswith(\"export \"):\n"
            "                    _k = _k[len(\"export \"):].strip()\n"
            "                _v = _v.strip()\n"
            "                if (len(_v) >= 2 and _v[0] == _v[-1]\n"
            "                        and _v[0] in (\"\\\"\", \"'\")):\n"
            "                    _v = _v[1:-1]\n"
            "                if not _k:\n"
            "                    continue\n"
            "                if _k not in os.environ:\n"
            "                    os.environ[_k] = _v\n"
            "                    loaded += 1\n"
            "    except Exception as _e:\n"
            "        try:\n"
            "            logging.getLogger(\"QTT6\").warning(\n"
            "                f\"[DotEnv] load failed: {_e}\"\n"
            "            )\n"
            "        except Exception:\n"
            "            pass\n"
            "    _DOTENV_LOADED = loaded\n"
            "    return loaded\n"
            "\n"
            "\n"
            "_load_dotenv()\n"
            "# ══ [DOTENV end] ══════════════════════════════════════════════════════\n"
            "\n"
            "# ══ [WATCH-REMOVED-MASTER] "
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P02 — --mode default reads from MODE env var
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P02-mode-from-env",
        "desc": "Change --mode default to os.environ.get('MODE', 'backtest')",
        "old": (
            "    p.add_argument(\"--mode\",        default=\"backtest\", choices=[\"backtest\",\"testnet\",\"live\"])\n"
        ),
        "new": (
            "    p.add_argument(\"--mode\",        default=os.environ.get(\"MODE\", \"backtest\"), choices=[\"backtest\",\"testnet\",\"live\"])\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P03 — Marker at file top
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P03-marker",
        "desc": "Add [DOTENV-APPLIED] marker at file top",
        "old": (
            "# [RESCUE-EXIT-APPLIED]\n"
            "# [LIVE-PERF-FIX-APPLIED]\n"
        ),
        "new": (
            "# ═══ [DOTENV-APPLIED] ═══\n"
            "# [RESCUE-EXIT-APPLIED]\n"
            "# [LIVE-PERF-FIX-APPLIED]\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P04 — Startup log: confirm .env was loaded
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P04-startup-log",
        "desc": "Log .env load status + masked key presence at startup",
        "old": (
            "    CFG.mode = args.mode\n"
            "    CFG.api_key = args.api_key\n"
            "    CFG.api_secret = args.api_secret\n"
        ),
        "new": (
            "    CFG.mode = args.mode\n"
            "    CFG.api_key = args.api_key\n"
            "    CFG.api_secret = args.api_secret\n"
            "    # ══ [DOTENV] startup info (no secrets logged) ══\n"
            "    try:\n"
            "        if _DOTENV_LOADED > 0:\n"
            "            log.info(f\"[Env] Loaded {_DOTENV_LOADED} variable(s) from .env\")\n"
            "        else:\n"
            "            log.info(\"[Env] No .env file found (using CLI args or shell env)\")\n"
            "        log.info(\n"
            "            f\"[Env] mode={CFG.mode}  \"\n"
            "            f\"api_key={'SET' if CFG.api_key else 'EMPTY'}  \"\n"
            "            f\"api_secret={'SET' if CFG.api_secret else 'EMPTY'}\"\n"
            "        )\n"
            "    except Exception:\n"
            "        pass\n"
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# CORE ENGINE (unchanged from rev_subbar_entry_patcher.py pattern)
# ═══════════════════════════════════════════════════════════════════════════════

def _count_occurrences(text, pattern):
    return text.count(pattern) if pattern else 0


def _apply_one_patch(content, patch):
    old, new, pid = patch["old"], patch["new"], patch["id"]
    if _count_occurrences(content, new) == 1:
        return content, "already_applied", f"{pid}: already applied"
    old_count = _count_occurrences(content, old)
    if old_count == 0:
        return content, "not_found", f"{pid}: anchor not found"
    if old_count > 1:
        return content, "ambiguous", f"{pid}: anchor appears {old_count}×"
    return content.replace(old, new, 1), "applied", f"{pid}: OK"


def _verify_syntax(content):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


def _is_already_patched(content):
    return MARKER in content


def run_patch(target, dry_run=False):
    print(f"\n{'═' * 74}")
    print(f"  DOTENV Patcher")
    print(f"  Target: {target}")
    print(f"  Mode  : {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target file not found: {target}")
        return 1

    original = target.read_text(encoding="utf-8")
    print(f"  📄 Loaded {len(original):,} chars "
          f"({original.count(chr(10)):,} lines)\n")

    if _is_already_patched(original):
        print(f"  ⚠️  File already contains marker: {MARKER}")
        all_present = True
        for patch in PATCHES:
            if _count_occurrences(original, patch["new"]) != 1:
                print(f"     ❌ {patch['id']}: missing or duplicated")
                all_present = False
        if all_present:
            print(f"  ✅ All {len(PATCHES)} patches verified present.\n")
            return 0
        print(f"  ⚠️  Some patches missing despite marker — "
              f"consider --rollback.\n")
        return 2

    content = original
    applied, skipped, failed = [], [], []

    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        print(f"  [{i:02d}/{len(PATCHES)}] {pid} ... ", end="", flush=True)
        new_content, status, detail = _apply_one_patch(content, patch)
        if status == "applied":
            content = new_content
            applied.append(patch)
            print("✅ applied")
        elif status == "already_applied":
            skipped.append(patch)
            print("⏭️  already applied")
        else:
            failed.append((patch, detail))
            print(f"❌ {status}")
            print(f"        └─ {detail}")

    print(f"\n{'─' * 74}")
    print(f"  Summary: {len(applied)} applied, {len(skipped)} already, "
          f"{len(failed)} failed")
    print(f"{'─' * 74}\n")

    if failed:
        print(f"  ❌ Patching aborted — {len(failed)} patch(es) failed.\n")
        for patch, detail in failed:
            print(f"     • {patch['id']}: {detail}")
        return 3

    if len(applied) == 0:
        print(f"  ✅ File already fully patched.\n")
        return 0

    print(f"  🔍 Validating syntax (ast.parse)...")
    ok, err = _verify_syntax(content)
    if not ok:
        print(f"  ❌ Syntax validation FAILED: {err}")
        print(f"     No file was modified.\n")
        return 4
    print(f"  ✅ Syntax OK\n")

    if dry_run:
        print(f"  🧪 DRY-RUN — would write {len(content):,} chars "
              f"to {target}\n")
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target.with_suffix(target.suffix + f".dotenv_backup_{ts}")
    try:
        shutil.copy2(target, backup_path)
        print(f"  💾 Backup: {backup_path.name}")
    except Exception as e:
        print(f"  ❌ Backup failed: {e}\n")
        return 5

    tmp_path = target.with_suffix(target.suffix + ".dotenv_tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, target)
        print(f"  ✅ Written: {target}")
        print(f"     Backup : {backup_path.name}\n")
    except Exception as e:
        print(f"  ❌ Write failed: {e}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        try:
            if backup_path.exists():
                shutil.copy2(backup_path, target)
                print(f"  🔄 Auto-rollback complete.\n")
        except Exception:
            pass
        return 6

    print(f"{'═' * 74}")
    print(f"  ✅ DOTENV successfully applied!")
    print(f"{'═' * 74}")
    print(f"  Create `.env` next to the bot with:")
    print(f"      MODE=live")
    print(f"      BINANCE_API_KEY=your_key")
    print(f"      BINANCE_API_SECRET=your_secret")
    print(f"")
    print(f"  Then run WITHOUT --mode / --api-key / --api-secret:")
    print(f"      python3 {target.name} --nassets 100 --timeframe 4h ...")
    print(f"")
    print(f"  Rollback:")
    print(f"      python3 {Path(__file__).name} --rollback")
    print(f"{'═' * 74}\n")
    return 0


def run_verify(target):
    print(f"\n{'═' * 74}")
    print(f"  DOTENV Verification")
    print(f"  Target: {target}")
    print(f"{'═' * 74}\n")
    if not target.exists():
        print(f"  ❌ Target not found: {target}\n")
        return 1
    content = target.read_text(encoding="utf-8")
    print(f"  Marker present : {'✅ YES' if _is_already_patched(content) else '❌ NO'}\n")
    ok = 0
    bad = 0
    for patch in PATCHES:
        pid = patch["id"]
        if _count_occurrences(content, patch["new"]) == 1:
            print(f"  ✅ {pid:35s} applied")
            ok += 1
        elif _count_occurrences(content, patch["old"]) == 1:
            print(f"  ❌ {pid:35s} NOT applied")
            bad += 1
        else:
            print(f"  ⚠️  {pid:35s} anchor missing")
            bad += 1
    print(f"\n{'─' * 74}")
    if ok == len(PATCHES):
        print(f"  ✅ All {len(PATCHES)} patches verified.\n")
        return 0
    print(f"  ⚠️  {ok}/{len(PATCHES)} verified, {bad} issue(s).\n")
    return 2


def run_rollback(target):
    print(f"\n{'═' * 74}")
    print(f"  DOTENV Rollback")
    print(f"  Target: {target}")
    print(f"{'═' * 74}\n")
    if not target.exists():
        print(f"  ❌ Target not found.\n")
        return 1
    backups = sorted(
        target.parent.glob(target.name + ".dotenv_backup_*"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not backups:
        print(f"  ❌ No backups found.\n")
        return 1
    latest = backups[0]
    print(f"  🔍 Restoring from: {latest.name}")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = target.with_suffix(target.suffix + f".pre_rollback_{ts}")
    try:
        shutil.copy2(target, pre)
        print(f"  💾 Pre-rollback snapshot: {pre.name}")
    except Exception as e:
        print(f"  ❌ Pre-rollback snapshot failed: {e}\n")
        return 2
    try:
        shutil.copy2(latest, target)
        print(f"  ✅ Rolled back: {target}\n")
    except Exception as e:
        print(f"  ❌ Rollback failed: {e}\n")
        return 3
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="DOTENV Patcher — load API keys + mode from .env",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 dotenv_patcher.py                 # apply\n"
            "  python3 dotenv_patcher.py --dry-run       # preview\n"
            "  python3 dotenv_patcher.py --verify-only   # check\n"
            "  python3 dotenv_patcher.py --rollback      # restore\n"
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
