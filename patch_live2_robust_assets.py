#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
╔══════════════════════════════════════════════════════════════════════════╗
║  patch_live2_robust_assets.py                                            ║
║  Fix the "assets empty" cascade in live mode                             ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Root cause chain:                                                       ║
║    * process_asset returns None for a symbol when KMeans produces        ║
║      degenerate clustering (H_train << log2(K)).                         ║
║    * No new entry is stored in LiveCache that cycle.                     ║
║    * _live_cache_prune_stale then deletes the OLD entry (because         ║
║      a newer closed bar exists), leaving the symbol with NO ad.          ║
║    * assets becomes empty → no signals → no trades.                      ║
║    * Gauge pool is empty → warning every 5 seconds.                      ║
║                                                                          ║
║  Fixes:                                                                  ║
║    R1  K-fallback: retry with smaller K instead of giving up             ║
║    R2  Rate-limit "pool too small" warning to once per 5 minutes         ║
║    R3  Keep at least one cached entry per symbol (prune only when a      ║
║        newer entry is already present)                                   ║
║    R4  Loud diagnostic when assets ends up empty                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import argparse, shutil, sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class C:
    GREEN='\033[92m'; RED='\033[91m'; YELLOW='\033[93m'
    CYAN='\033[96m'; GRAY='\033[90m'; BOLD='\033[1m'; END='\033[0m'


# ══════════════════════════════════════════════════════════════════════════
# R1 — K-robust fallback (offset-based replacement)
# ══════════════════════════════════════════════════════════════════════════

R1_START = "    km = km_ext if km_ext else fit_kmeans(X[:train_end], k=dyn_k)"
R1_END   = "    lr_full = np.diff(np.log(np.maximum(closes,1e-12)))"

R1_BODY = '''    # ══ [K-ROBUST] Fit KMeans with automatic K-fallback. ══
    # If the initial K yields degenerate clustering (H_train far below
    # log2(K)), retry with K/2, K/4, ..., K=2. Prevents the catastrophic
    # "assets empty -> no signals" failure mode where every symbol
    # returned None on a transient degenerate fit.
    _k_threshold = float(getattr(CFG, 'K_DEGENERATE_H_RATIO', 0.25))
    _k_skip = getattr(CFG, 'K_SKIP_IF_DEGENERATE', True)

    if km_ext is not None:
        # External KMeans provided -> trust it, keep strict behavior
        km = km_ext
        sym_q = assign(X, km)
        H = entropy_series(sym_q, k=dyn_k)
        dH = np.diff(H, prepend=H[0])
        d2H = np.diff(dH, prepend=dH[0])
        if _k_skip and train_end > 0:
            _H_train_mean = float(np.mean(H[:train_end]))
            _H_theo = np.log2(max(int(dyn_k), 2))
            _ratio = _H_train_mean / max(_H_theo, 1e-9)
            if _ratio < _k_threshold:
                log.warning(
                    f"[K-Fallback] {symbol}: degenerate with km_ext "
                    f"(ratio={_ratio:.3f}, K={dyn_k}) -- returning None"
                )
                return None
    else:
        # Build candidate list: K_initial, K/2, K/4, ..., 2
        _k_initial = int(dyn_k)
        _k_candidates = [_k_initial]
        _k_cur = _k_initial
        while _k_cur > 2:
            _k_cur = max(2, _k_cur // 2)
            if _k_cur not in _k_candidates:
                _k_candidates.append(_k_cur)

        _k_chosen = None
        _km_chosen = None
        _sym_q_chosen = None
        _H_chosen = None
        _last_ratio = None
        _last_k_tried = None

        for _k_try in _k_candidates:
            _last_k_tried = _k_try
            try:
                _km_try = fit_kmeans(X[:train_end], k=_k_try)
                _sym_q_try = assign(X, _km_try)
                _H_try = entropy_series(_sym_q_try, k=_k_try)
                if _k_skip and train_end > 0:
                    _H_mean_try = float(np.mean(_H_try[:train_end]))
                    _H_theo_try = np.log2(max(_k_try, 2))
                    _ratio_try = _H_mean_try / max(_H_theo_try, 1e-9)
                    _last_ratio = _ratio_try
                    if _ratio_try < _k_threshold:
                        log.debug(
                            f"[K-Fallback] {symbol} K={_k_try} "
                            f"degenerate (ratio={_ratio_try:.3f})"
                        )
                        continue
                _k_chosen = _k_try
                _km_chosen = _km_try
                _sym_q_chosen = _sym_q_try
                _H_chosen = _H_try
                break
            except Exception as _e:
                log.debug(
                    f"[K-Fallback] {symbol} fit K={_k_try} failed: {_e}"
                )
                continue

        if _k_chosen is None:
            # Last resort: force K=2 (guaranteed non-degenerate for any
            # non-trivial distribution: H_max = 1, threshold = 0.25).
            try:
                _k_chosen = 2
                _km_chosen = fit_kmeans(X[:train_end], k=2)
                _sym_q_chosen = assign(X, _km_chosen)
                _H_chosen = entropy_series(_sym_q_chosen, k=2)
                log.warning(
                    f"[K-Fallback] {symbol}: all K degenerate "
                    f"(last K={_last_k_tried}, ratio={_last_ratio}) "
                    f"-- forced K=2"
                )
            except Exception as _e:
                log.warning(
                    f"[K-Fallback] {symbol}: K=2 fallback failed: {_e} "
                    f"-- returning None"
                )
                return None

        if _k_chosen != _k_initial:
            log.info(
                f"[K-Fallback] {symbol}: K={_k_initial}->{_k_chosen} "
                f"(ratio={_last_ratio})"
            )

        km = _km_chosen
        sym_q = _sym_q_chosen
        H = _H_chosen
        dH = np.diff(H, prepend=H[0])
        d2H = np.diff(dH, prepend=dH[0])
        dyn_k = int(_k_chosen)   # propagate for downstream uses

'''


# ══════════════════════════════════════════════════════════════════════════
# R2 — Rate-limit "pool too small" warning
# ══════════════════════════════════════════════════════════════════════════

R2_OLD = '''        else:
            log.warning(
                f"[Gauge-Filter] pool too small ({len(_gauge_pool)}"
                f"<{CFG.GAUGE_MIN_SAMPLES}) — filter disabled"
            )'''

R2_NEW = '''        else:
            # [RATE-LIMIT] Warn at most once per 5 minutes to avoid log
            # spam when the pool is persistently empty.
            _gw_now = time.time()
            _gw_last = getattr(build_signals, '_last_pool_warn_ts', 0.0)
            if _gw_now - _gw_last >= 300.0:
                log.warning(
                    f"[Gauge-Filter] pool too small ({len(_gauge_pool)}"
                    f"<{CFG.GAUGE_MIN_SAMPLES}) — filter disabled "
                    f"(rate-limited to 1 per 5min)"
                )
                build_signals._last_pool_warn_ts = _gw_now'''


# ══════════════════════════════════════════════════════════════════════════
# R3 — Robust LiveCache prune (keep at least one per symbol)
# ══════════════════════════════════════════════════════════════════════════

R3_OLD = '''def _live_cache_prune_stale(current_last_closed: Dict[str, int]) -> int:
    """
    Remove entries whose last_closed_ts is older than the current one
    for the same (sym, tf). Called periodically.
    """
    removed = 0
    for key in list(_LIVE_ASSET_CACHE.keys()):
        sym, tf, ts = key
        cur_ts = current_last_closed.get(sym, ts)
        if ts < cur_ts:
            _LIVE_ASSET_CACHE.pop(key, None)
            removed += 1
    return removed'''

R3_NEW = '''def _live_cache_prune_stale(current_last_closed: Dict[str, int]) -> int:
    """
    Remove entries whose last_closed_ts is older than the current one
    for the same (sym, tf), BUT ONLY when a strictly newer entry exists
    for that (sym, tf).

    [ROBUST-PRUNE] Rationale: if process_asset fails transiently this
    cycle (degenerate KMeans, insufficient bars, etc.), no new entry is
    stored. Deleting the old entry would leave the symbol with no ad,
    making assets[sym] empty and cascading into a total signal blackout.
    Keeping the previous entry alive ensures a working fallback until a
    fresh ad is computed.
    """
    removed = 0
    # Map (sym, tf) -> set of timestamps currently present
    _by_sym: Dict = defaultdict(set)
    for key in list(_LIVE_ASSET_CACHE.keys()):
        _sym, _tf, _ts = key
        _by_sym[(_sym, _tf)].add(_ts)

    for key in list(_LIVE_ASSET_CACHE.keys()):
        sym, tf, ts = key
        cur_ts = current_last_closed.get(sym, ts)
        if ts >= cur_ts:
            continue
        # Prune only if a strictly newer entry exists for the same (sym,tf)
        _newer = [t for t in _by_sym.get((sym, tf), set()) if t > ts]
        if _newer:
            _LIVE_ASSET_CACHE.pop(key, None)
            _by_sym[(sym, tf)].discard(ts)
            removed += 1
    return removed'''


# ══════════════════════════════════════════════════════════════════════════
# R4 — Diagnostic when assets is empty
# ══════════════════════════════════════════════════════════════════════════

R4_ANCHOR = '''            # ══ [LIVE CACHE] prune stale + report stats ══'''

R4_INSERT = '''            # ══ [DIAG] Loudly report when assets ends up empty ══
            # Helps debug the "pool too small" cascade in one line.
            if (not assets) and top_syms:
                _diag_now = time.time()
                _diag_last = getattr(run_live, '_last_empty_diag_ts', 0.0)
                if _diag_now - _diag_last >= 300.0:
                    run_live._last_empty_diag_ts = _diag_now
                    _n_cached = sum(
                        1 for s in top_syms if s in cached_data)
                    _n_min = int(getattr(
                        CFG, 'LIVE_MIN_BARS_FOR_PROCESS', 2000))
                    _n_small = sum(
                        1 for s in top_syms
                        if s in cached_data
                        and len(cached_data[s]) < _n_min
                    )
                    _n_deg = len(_DEGENERATE_CACHE)
                    log.critical(
                        f"[DIAG] assets empty for {len(top_syms)} symbols "
                        f"(cached={_n_cached}, too_small={_n_small}, "
                        f"min_needed={_n_min}, degenerate_marked={_n_deg}). "
                        f"Likely cause: process_asset returned None. "
                        f"Check 'K-Fallback' lines above."
                    )

            # ══ [LIVE CACHE] prune stale + report stats ══'''


# ══════════════════════════════════════════════════════════════════════════
# Patcher
# ══════════════════════════════════════════════════════════════════════════

class Patcher:
    def __init__(self, path, dry_run=False):
        self.path = path
        self.dry_run = dry_run
        self.content = None
        self.backup_path = None
        self.results: List[Tuple[str, str]] = []

    def load(self):
        if not self.path.exists():
            print(f"{C.RED}  Not found: {self.path}{C.END}")
            return False
        try:
            self.content = self.path.read_text(encoding='utf-8')
            print(f"{C.CYAN}  Loaded {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Read error: {e}{C.END}")
            return False

    def backup(self):
        if self.dry_run:
            return True
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = self.path.with_suffix(
            self.path.suffix + f'.bak.{ts}')
        try:
            shutil.copy2(self.path, self.backup_path)
            print(f"{C.CYAN}  Backup: {self.backup_path.name}{C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Backup failed: {e}{C.END}")
            return False

    def replace_str(self, name, old, new, marker=None):
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name}")
            return True
        n = self.content.count(old)
        if n == 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name}")
            return False
        if n > 1:
            print(f"  {C.YELLOW}⚠ WARN{C.END}  {name}: {n} occurrences")
        self.content = self.content.replace(old, new)
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name}")
        return True

    def replace_between(self, name, start_m, end_m, new_body, marker=None):
        if marker and marker in self.content:
            self.results.append((name, 'skip'))
            print(f"  {C.GRAY}○ SKIP{C.END}  {name}")
            return True
        s = self.content.find(start_m)
        if s < 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} "
                  f"{C.GRAY}(start not found){C.END}")
            return False
        e = self.content.find(end_m, s + len(start_m))
        if e < 0:
            self.results.append((name, 'fail'))
            print(f"  {C.RED}✗ FAIL{C.END}  {name} "
                  f"{C.GRAY}(end not found){C.END}")
            return False
        self.content = self.content[:s] + new_body + self.content[e:]
        self.results.append((name, 'applied'))
        print(f"  {C.GREEN}✓ OK{C.END}    {name} "
              f"(replaced {e - s} chars)")
        return True

    def save(self):
        if self.dry_run:
            print(f"{C.YELLOW}  DRY RUN -- not written{C.END}")
            return True
        if self.path.suffix == '.py':
            try:
                compile(self.content, str(self.path), 'exec')
            except SyntaxError as e:
                print(f"{C.RED}  Syntax error: {e}{C.END}")
                if self.backup_path and self.backup_path.exists():
                    shutil.copy2(self.backup_path, self.path)
                    print(f"{C.GREEN}  Restored from backup.{C.END}")
                return False
        try:
            self.path.write_text(self.content, encoding='utf-8')
            print(f"{C.GREEN}  Written {self.path.name} "
                  f"({len(self.content):,} bytes){C.END}")
            return True
        except Exception as e:
            print(f"{C.RED}  Write failed: {e}{C.END}")
            return False

    def report(self):
        a = sum(1 for _, s in self.results if s == 'applied')
        s = sum(1 for _, s in self.results if s == 'skip')
        f = sum(1 for _, s in self.results if s == 'fail')
        print(f"\n  {C.BOLD}Summary:{C.END}  "
              f"{C.GREEN}applied={a}{C.END}, "
              f"{C.GRAY}skipped={s}{C.END}, "
              f"{C.RED}failed={f}{C.END}")
        return f


def restore_latest(path):
    backups = sorted(path.parent.glob(path.name + '.bak.*'),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print(f"{C.RED}No backups for {path.name}{C.END}")
        return False
    shutil.copy2(backups[0], path)
    print(f"{C.GREEN}✓ Restored from {backups[0].name}{C.END}")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bot", default="trading_2_live2.py")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--restore", action="store_true")
    args = p.parse_args()

    bot = Path(args.bot).resolve()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    print(f"{C.BOLD}  Robust-Assets Patcher -- {bot.name}{C.END}")
    print(f"{C.BOLD}  Mode: {'DRY-RUN' if args.dry_run else 'APPLY'}{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if args.restore:
        sys.exit(0 if restore_latest(bot) else 1)
    if not bot.exists():
        print(f"{C.RED}File not found: {bot}{C.END}")
        sys.exit(2)

    pt = Patcher(bot, dry_run=args.dry_run)
    if not pt.load() or not pt.backup():
        sys.exit(3)

    print()
    pt.replace_between(
        "R1   K-robust fallback in process_asset",
        R1_START, R1_END, R1_BODY,
        marker="[K-ROBUST] Fit KMeans with automatic K-fallback",
    )

    pt.replace_str(
        "R2   Rate-limit 'pool too small' warning",
        R2_OLD, R2_NEW,
        marker="[RATE-LIMIT] Warn at most once per 5 minutes",
    )

    pt.replace_str(
        "R3   Robust LiveCache prune (keep 1 per symbol)",
        R3_OLD, R3_NEW,
        marker="[ROBUST-PRUNE] Rationale",
    )

    pt.replace_str(
        "R4   Diagnostic when assets empty",
        R4_ANCHOR, R4_INSERT,
        marker="[DIAG] Loudly report when assets ends up empty",
    )

    if not pt.save():
        sys.exit(4)
    failed = pt.report()

    print(f"\n{C.BOLD}{'═' * 76}{C.END}")
    if failed == 0:
        print(f"{C.GREEN}  ALL PATCHES APPLIED SUCCESSFULLY{C.END}")
    else:
        print(f"{C.RED}  {failed} PATCH(ES) FAILED{C.END}")
    print(f"{C.BOLD}{'═' * 76}{C.END}")

    if not failed and not args.dry_run:
        print(f"\n{C.CYAN}Next steps:{C.END}")
        print(f"  1. Verify:  python3 -m py_compile {bot.name}")
        print(f"  2. Grep:    grep -n 'K-Fallback\\|ROBUST-PRUNE\\|"
              f"\\[DIAG\\]' {bot.name}")
        print(f"  3. Run bot. Look for these in logs:")
        print(f"     {C.BOLD}[K-Fallback] XXX: K=50->25 (ratio=0.XX){C.END}")
        print(f"     {C.BOLD}[DIAG] assets empty ...{C.END}  (only if still broken)")
        print(f"  4. Revert:  python3 {Path(__file__).name} --restore")


if __name__ == "__main__":
    main()
