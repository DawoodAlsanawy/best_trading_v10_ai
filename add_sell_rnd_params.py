#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_sell_rnd_params.py — إضافة معاملات SELL R&D.

لا تُفعّل SELL. فقط تُضيف البنية التحتية لاختباره.
"""

import argparse, ast, shutil, sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Patch 1: Config parameters
# ═══════════════════════════════════════════════════════════════

P1_ANCHOR = '    GAUGE_DISABLE_SELL: bool = True    # Default: BUY-only'
P1_NEW = '''    GAUGE_DISABLE_SELL: bool = True    # Default: BUY-only

    # ══ [SELL-RND] معاملات بحث SELL المستقل ══
    # عند SELL_ENABLED=False، هذا كله غير مفعّل.
    # BUY غير متأثر إطلاقاً.
    SELL_ENABLED: bool = False              # master switch
    SELL_MIN_SCORE: int = 3                 # independent from BUY
    SELL_MIN_ZDEV: float = 1.5              # independent from BUY
    SELL_GAUGE_PCT: float = 0.95            # current default
    SELL_REQUIRE_EMA_DOWN: bool = False     # trend-aligned SELL
    SELL_MAJOR_ONLY: bool = False           # only BTC/ETH/SOL/BNB
    SELL_MIN_ATR_FRAC: float = 0.0          # 0 = no gate
    SELL_MAJOR_PAIRS: Tuple = ("BTC/USDT", "ETH/USDT",
                                "SOL/USDT", "BNB/USDT")'''

P1_MARK = "# ══ [SELL-RND]"


# ═══════════════════════════════════════════════════════════════
# Patch 2: build_signals — SELL gate logic
# ═══════════════════════════════════════════════════════════════

# الموضع: بعد القرار `action = "BUY" if _z_dev < 0 else "SELL"`
# و قبل gauge filter
P2_ANCHOR = '''            action = "BUY" if _z_dev < 0 else "SELL"

            # ══ [GAUGE-FILTER] ══'''

P2_NEW = '''            action = "BUY" if _z_dev < 0 else "SELL"

            # ══ [SELL-RND] بوابة SELL المستقلة ══
            # BUY لا يُلمَس. SELL فقط يُمرّر عبر هذه البوابة.
            if action == "SELL":
                if not getattr(CFG, 'SELL_ENABLED', False):
                    continue
                if ad.score[fi] < float(getattr(CFG, 'SELL_MIN_SCORE', 3)):
                    continue
                if abs(_z_dev) < float(getattr(CFG, 'SELL_MIN_ZDEV', 1.5)):
                    continue
                # EMA-aligned SELL (only sell into a downtrend)
                if getattr(CFG, 'SELL_REQUIRE_EMA_DOWN', False):
                    _lb_s = 50
                    if ci >= _lb_s:
                        _slope_s = (ad.ema200[ci] -
                                    ad.ema200[ci - _lb_s]) / _lb_s
                        if _slope_s >= 0:
                            continue
                # Liquid pairs only
                if getattr(CFG, 'SELL_MAJOR_ONLY', False):
                    if sym not in getattr(CFG, 'SELL_MAJOR_PAIRS',
                                           ("BTC/USDT", "ETH/USDT",
                                            "SOL/USDT", "BNB/USDT")):
                        continue
                # Volatility gate (higher vol required)
                _atr_frac_s = float(ad.atr14[ci]) / max(float(p), 1e-12) \\
                              if ci < len(ad.atr14) else 0.0
                if _atr_frac_s < float(getattr(CFG,
                                                'SELL_MIN_ATR_FRAC', 0.0)):
                    continue

            # ══ [GAUGE-FILTER] ══'''

P2_MARK = "# ══ [SELL-RND] بوابة SELL"


# ═══════════════════════════════════════════════════════════════
# Patch 3: gauge filter — use SELL_GAUGE_PCT for SELL
# ═══════════════════════════════════════════════════════════════

P3_ANCHOR = '''            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):
                if action == "SELL" and getattr(CFG, 'GAUGE_DISABLE_SELL', False):
                    continue
                try:
                    _gf = float(ad.gauge_force[fi])
                    if action == "BUY" and _gf < _gauge_thr_buy:
                        continue
                    if action == "SELL" and _gf < _gauge_thr_sell:
                        continue
                except Exception:
                    pass'''

P3_NEW = '''            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):
                # [SELL-RND] BUY uses gauge pool; SELL uses
                # SELL_GAUGE_PCT (independent threshold) when SELL_ENABLED.
                if action == "SELL" and not getattr(CFG, 'SELL_ENABLED',
                                                     False):
                    if getattr(CFG, 'GAUGE_DISABLE_SELL', False):
                        continue
                try:
                    _gf = float(ad.gauge_force[fi])
                    if action == "BUY" and _gf < _gauge_thr_buy:
                        continue
                    if action == "SELL":
                        if getattr(CFG, 'SELL_ENABLED', False):
                            # Recompute percentile-based threshold on the fly
                            _pct_s = float(getattr(CFG, 'SELL_GAUGE_PCT',
                                                    0.95))
                            _thr_s = np.percentile(_gauge_arr, _pct_s * 100) \\
                                     if len(_gauge_pool) > 0 else _gauge_thr_sell
                            if _gf < _thr_s:
                                continue
                        else:
                            if _gf < _gauge_thr_sell:
                                continue
                except Exception:
                    pass'''

P3_MARK = "# [SELL-RND] BUY uses gauge pool"


# ═══════════════════════════════════════════════════════════════
# Patch 4: CLI flags
# ═══════════════════════════════════════════════════════════════

P4_ANCHOR = '''    p.add_argument("--enable-sell", action="store_true",
                   help="Re-enable SELL signals (default: BUY-only)")'''

P4_NEW = '''    p.add_argument("--enable-sell", action="store_true",
                   help="Re-enable SELL signals (default: BUY-only)")
    # [SELL-RND] SELL tuning flags
    p.add_argument("--sell-min-score", type=int, default=None)
    p.add_argument("--sell-min-zdev", type=float, default=None)
    p.add_argument("--sell-gauge-pct", type=float, default=None)
    p.add_argument("--sell-require-ema-down", action="store_true")
    p.add_argument("--sell-major-only", action="store_true")
    p.add_argument("--sell-min-atr-frac", type=float, default=None)'''

P4_MARK = 'p.add_argument("--sell-min-score"'


# ═══════════════════════════════════════════════════════════════
# Patch 5: main() wiring
# ═══════════════════════════════════════════════════════════════

P5_ANCHOR = '''    if getattr(args, "enable_sell", False):
        CFG.GAUGE_DISABLE_SELL = False
        log.info("[Gauge] SELL RE-ENABLED — experimental mode")'''

P5_NEW = '''    if getattr(args, "enable_sell", False):
        CFG.GAUGE_DISABLE_SELL = False
        CFG.SELL_ENABLED = True
        log.info("[Gauge] SELL RE-ENABLED — experimental mode")
    # [SELL-RND] wiring
    if args.sell_min_score is not None:
        CFG.SELL_MIN_SCORE = int(args.sell_min_score)
    if args.sell_min_zdev is not None:
        CFG.SELL_MIN_ZDEV = float(args.sell_min_zdev)
    if args.sell_gauge_pct is not None:
        CFG.SELL_GAUGE_PCT = float(args.sell_gauge_pct)
    if args.sell_require_ema_down:
        CFG.SELL_REQUIRE_EMA_DOWN = True
    if args.sell_major_only:
        CFG.SELL_MAJOR_ONLY = True
    if args.sell_min_atr_frac is not None:
        CFG.SELL_MIN_ATR_FRAC = float(args.sell_min_atr_frac)'''

P5_MARK = "# [SELL-RND] wiring"


# ═══════════════════════════════════════════════════════════════

def apply(text, old, new, marker, name):
    if marker and marker in text:
        return text, f"SKIP: {name}"
    if old not in text:
        return text, f"ERR: {name} (anchor not found)"
    return text.replace(old, new, 1), f"OK: {name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"ERR: {args.file} not found")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("=" * 70)
    print("  add_sell_rnd_params.py")
    print("=" * 70)
    print()

    text, s = apply(text, P1_ANCHOR, P1_NEW, P1_MARK, "Config params")
    print(f"  {s}")
    text, s = apply(text, P2_ANCHOR, P2_NEW, P2_MARK, "SELL gate")
    print(f"  {s}")
    text, s = apply(text, P3_ANCHOR, P3_NEW, P3_MARK, "Gauge SELL threshold")
    print(f"  {s}")
    text, s = apply(text, P4_ANCHOR, P4_NEW, P4_MARK, "CLI flags")
    print(f"  {s}")
    text, s = apply(text, P5_ANCHOR, P5_NEW, P5_MARK, "main() wiring")
    print(f"  {s}")

    try:
        ast.parse(text)
        print()
        print("  OK: ast.parse")
    except SyntaxError as e:
        print(f"\n  ERR: syntax at line {e.lineno}: {e.text}")
        return 3

    if text == original:
        print("\n  No changes")
        return 0

    if args.dry_run:
        print("\n" + "=" * 70)
        print("  Dry run - nothing written")
        print("=" * 70)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_sellrnd_{ts}')
    shutil.copy2(p, backup)
    print(f"\n  Backup: {backup}")
    p.write_text(text, encoding='utf-8')
    print(f"  Written: {p}")
    print("\n" + "=" * 70)
    print("  Done")
    print("=" * 70)
    print(f"  Rollback: cp {backup.name} {p.name}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
