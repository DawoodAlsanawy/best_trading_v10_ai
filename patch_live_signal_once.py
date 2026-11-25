#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch script #5: Once-per-signal guard in Live mode.

Prevents run_live from re-entering the EXACT SAME bar signal within the
same candle hour when --no-reentry-cooldown is active (a critical gap
that would otherwise cause repeated re-entries after an early SL/TP/BEEsc
exit on the same bar).

Still honors --no-reentry-cooldown for ANY NEW signal on the next bar,
matching backtest 1:1.

Usage:
  python patch_live_signal_once.py --dry-run
  python patch_live_signal_once.py
"""

import argparse
import os
import py_compile
import shutil
import sys
from datetime import datetime

PATCH_MARKER = "# [LIVE-SIGNAL-ONCE-APPLIED]"


def _default_target() -> str:
    for cand in (
        "trading_published_pro_1h_fixed_LV.py",
        "trading_published_pro_1h_fixed.py",
        "trading_published_pro_1h.py",
    ):
        if os.path.exists(cand):
            return cand
    return "trading_published_pro_1h_fixed_LV.py"


def apply_patch(target_path: str, dry_run: bool = False) -> None:
    if not os.path.exists(target_path):
        print(f"[ERROR] Target file not found: {target_path}", file=sys.stderr)
        sys.exit(1)

    with open(target_path, "r", encoding="utf-8") as f:
        src = f.read()

    if PATCH_MARKER in src:
        print(f"[OK] Patch already applied ({PATCH_MARKER} found). Nothing to do.")
        return

    replacements = [
        (
            "patch marker 5",
            "# [LIVE-PARITY-SPEED-APPLIED]",
            "# [LIVE-PARITY-SPEED-APPLIED]\n" + PATCH_MARKER,
        ),
        (
            "consumed signals ledger & helpers",
            "_LIVE_KM_CACHE: Dict[str, Dict] = {}   # {sym: {'km', 'k', 'k_req', 'ts'}}",
            r'''_LIVE_KM_CACHE: Dict[str, Dict] = {}   # {sym: {'km', 'k', 'k_req', 'ts'}}
_LIVE_CONSUMED_SIGNALS: Dict[str, float] = {}
_LIVE_CONSUMED_PATH: str = ""
_LIVE_SIG_FAIL_COUNTS: Dict[str, int] = {}


def _live_sig_key(sym: str, sig) -> str:
    try:
        _ts = pd.Timestamp(sig.timestamp)
        if _ts.tz is None:
            _ts = _ts.tz_localize('UTC')
        return f"{sym}|{int(_ts.timestamp())}|{sig.action}"
    except Exception:
        return f"{sym}|{int(getattr(sig, 'close_idx', 0))}|{getattr(sig, 'action', '?')}"


def _load_live_consumed_signals(mode: str) -> None:
    global _LIVE_CONSUMED_SIGNALS, _LIVE_CONSUMED_PATH
    _LIVE_CONSUMED_PATH = f"live_consumed_signals_{mode}.json"
    _LIVE_CONSUMED_SIGNALS = {}
    if os.path.exists(_LIVE_CONSUMED_PATH):
        try:
            with open(_LIVE_CONSUMED_PATH, "r", encoding="utf-8") as _f:
                raw = json.load(_f)
            now = time.time()
            _LIVE_CONSUMED_SIGNALS = {
                str(k): float(v)
                for k, v in raw.items()
                if now - float(v) < 172800.0
            }
            log.info(f"[LiveSig] Restored {len(_LIVE_CONSUMED_SIGNALS)} consumed signal keys")
        except Exception as _e:
            log.warning(f"[LiveSig] load failed: {_e}")
            _LIVE_CONSUMED_SIGNALS = {}


def _save_live_consumed_signals() -> None:
    if not _LIVE_CONSUMED_PATH:
        return
    try:
        now = time.time()
        for _k in [k for k, v in _LIVE_CONSUMED_SIGNALS.items() if now - float(v) >= 172800.0]:
            _LIVE_CONSUMED_SIGNALS.pop(_k, None)
        _json_write_if_changed(_LIVE_CONSUMED_PATH, _LIVE_CONSUMED_SIGNALS, indent=1)
    except Exception as _e:
        log.debug(f"[LiveSig] save failed: {_e}")


def _is_live_signal_consumed(sym: str, sig) -> bool:
    return _live_sig_key(sym, sig) in _LIVE_CONSUMED_SIGNALS


def _mark_live_signal_consumed(sym: str, sig) -> None:
    _k = _live_sig_key(sym, sig)
    _LIVE_CONSUMED_SIGNALS[_k] = time.time()
    _LIVE_SIG_FAIL_COUNTS.pop(_k, None)''',
        ),
        (
            "run_live load consumed signals at startup",
            "    load_pending_orders(cfg.mode)",
            "    load_pending_orders(cfg.mode)\n    _load_live_consumed_signals(cfg.mode)",
        ),
        (
            "run_live skip already-consumed signals",
            r'''                for sig in reversed(sigs):
                    sym = sig.symbol
                    if sym in open_pos_live: continue''',
            r'''                for sig in reversed(sigs):
                    sym = sig.symbol
                    if sym in open_pos_live: continue
                    if _is_live_signal_consumed(sym, sig):
                        continue''',
        ),
        (
            "run_live mark signal consumed after placement",
            r'''                            rec = place_pending_entry(
                                exchange, sym, sd, qty, sig,
                                timeout_s=_timeout_s,
                                leverage=int(dynamic_leverage),
                                ad=assets[sym],
                            )
                            if rec is None:
                                log.info(f"[Pending] {sym} rejected — skip")
                                continue
                            try:
                                save_pending_orders()
                            except Exception:
                                pass
                            continue''',
            r'''                            rec = place_pending_entry(
                                exchange, sym, sd, qty, sig,
                                timeout_s=_timeout_s,
                                leverage=int(dynamic_leverage),
                                ad=assets[sym],
                            )
                            if rec is None:
                                _sk = _live_sig_key(sym, sig)
                                _LIVE_SIG_FAIL_COUNTS[_sk] = _LIVE_SIG_FAIL_COUNTS.get(_sk, 0) + 1
                                if _LIVE_SIG_FAIL_COUNTS[_sk] >= 3:
                                    _mark_live_signal_consumed(sym, sig)
                                    _save_live_consumed_signals()
                                log.info(f"[Pending] {sym} rejected — skip")
                                continue
                            _mark_live_signal_consumed(sym, sig)
                            _save_live_consumed_signals()
                            try:
                                save_pending_orders()
                            except Exception:
                                pass
                            continue''',
        ),
    ]

    for name, old, _ in replacements:
        cnt = src.count(old)
        if cnt != 1:
            print(
                f"[ERROR] Hunk '{name}' matched {cnt} times (expected 1). Aborting.",
                file=sys.stderr,
            )
            sys.exit(2)

    patched = src
    for name, old, new in replacements:
        patched = patched.replace(old, new, 1)
        print(f"[PATCH] Applied: {name}")

    if dry_run:
        print("[DRY-RUN] All hunks matched cleanly. No files were modified.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{target_path}.bak_{ts}"
    shutil.copy2(target_path, backup_path)
    print(f"[BACKUP] Created: {backup_path}")

    tmp_path = f"{target_path}.patched.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(patched)
        py_compile.compile(tmp_path, doraise=True)
        os.replace(tmp_path, target_path)
        print(f"[SUCCESS] Patched & syntax-verified: {target_path}")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"[ERROR] Verification failed, original file untouched: {e}", file=sys.stderr)
        sys.exit(3)


def main():
    parser = argparse.ArgumentParser(description="Patch run_live to consume each bar signal at most once")
    parser.add_argument("--target", default=_default_target(), help="Path to target script")
    parser.add_argument("--dry-run", action="store_true", help="Verify matches without modifying file")
    args = parser.parse_args()
    apply_patch(args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
