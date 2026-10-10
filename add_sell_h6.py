#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_sell_h6.py — إضافة منطق H6 لـ SELL.

Patch 1: Config — SELL_REQUIRE_EMA_UP + SELL_GAUGE_POOL_PER_ASSET
Patch 2: build_signals — per-asset gauge pool
Patch 3: build_signals — SELL EMA_UP gate
Patch 4: CLI flags
Patch 5: main() wiring

كل التعديلات opt-in. القيم الافتراضية = سلوك حالي (لا تغيير).
"""

import argparse, ast, shutil, sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Patch 1: Config
# ═══════════════════════════════════════════════════════════════

P1_ANCHOR = "    SELL_SL_WIDEN_MULT: float = 1.0"
P1_NEW = """    SELL_SL_WIDEN_MULT: float = 1.0

    # ══ [SELL-H6] الفرضية الجديدة: contrarian SELL في bull market ══
    # SELL_REQUIRE_EMA_UP=True → رفض SELL إذا EMA هابط.
    #   السبب: البيانات تُظهر أن SELL_rبح عندما EMA صاعد
    #   (against Sharpe > aligned Sharpe في 3/3 سنوات).
    SELL_REQUIRE_EMA_UP: bool = False
    SELL_EMA_UP_LOOKBACK: int = 50          # نافذة حساب الميل

    # ══ [SELL-PER-ASSET-POOL] عتبة gauge لكل أصل ══
    # True → لكل أصل عتبته الخاصة (لا عتبة عالمية)
    # False → العتبة العالمية (السلوك الحالي)
    SELL_GAUGE_POOL_PER_ASSET: bool = False
    SELL_GAUGE_POOL_MIN_SAMPLES: int = 200  # أدنى عينات لحساب لكل أصل"""
P1_MARK = "[SELL-H6]"


# ═══════════════════════════════════════════════════════════════
# Patch 2: build_signals — per-asset gauge pool computation
# ═══════════════════════════════════════════════════════════════

P2_ANCHOR = """            _gauge_thr_sell = float(np.percentile(
                _gauge_arr, CFG.GAUGE_PERCENTILE_SELL * 100
            ))"""

P2_NEW = """            _gauge_thr_sell = float(np.percentile(
                _gauge_arr, CFG.GAUGE_PERCENTILE_SELL * 100
            ))

    # ══ [SELL-PER-ASSET-POOL] حساب عتبة مستقلة لكل أصل ══
    _gauge_thr_sell_per_asset = {}
    if (getattr(CFG, 'GAUGE_FILTER_ENABLED', False)
            and getattr(CFG, 'SELL_GAUGE_POOL_PER_ASSET', False)):
        _pct_s = float(getattr(CFG, 'SELL_GAUGE_PCT',
                                CFG.GAUGE_PERCENTILE_SELL))
        _min_samples = int(getattr(CFG, 'SELL_GAUGE_POOL_MIN_SAMPLES', 200))
        for _sym_pa, _ad_pa in assets.items():
            try:
                _gf_pa = getattr(_ad_pa, 'gauge_force', None)
                if _gf_pa is None or len(_gf_pa) == 0:
                    continue
                _valid_pa = _gf_pa[_ad_pa.train_end:]
                _valid_pa = _valid_pa[_valid_pa > 0]
                if len(_valid_pa) < _min_samples:
                    continue
                _thr_pa = float(np.percentile(_valid_pa, _pct_s * 100))
                _gauge_thr_sell_per_asset[_sym_pa] = _thr_pa
            except Exception:
                continue
        log.info(
            f"[SELL-Pool-Per-Asset] thresholds computed for "
            f"{len(_gauge_thr_sell_per_asset)}/{len(assets)} assets "
            f"(pct={_pct_s}, min_samples={_min_samples})"
        )"""
P2_MARK = "[SELL-PER-ASSET-POOL]"


# ═══════════════════════════════════════════════════════════════
# Patch 3: build_signals — SELL logic: EMA_UP + per-asset gauge
# ═══════════════════════════════════════════════════════════════

P3_ANCHOR = """            # ══ [SELL-RND] بوابة SELL المستقلة ══
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
                            continue"""

P3_NEW = """            # ══ [SELL-RND] بوابة SELL المستقلة ══
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
                # ══ [SELL-H6] EMA_UP gate (contrarian) ══
                if getattr(CFG, 'SELL_REQUIRE_EMA_UP', False):
                    _lb_u = int(getattr(CFG, 'SELL_EMA_UP_LOOKBACK', 50))
                    if ci >= _lb_u and ci < len(ad.ema200):
                        _slope_u = (ad.ema200[ci] -
                                    ad.ema200[ci - _lb_u]) / max(_lb_u, 1)
                        if _slope_u <= 0:
                            continue
                    else:
                        continue"""
P3_MARK = "[SELL-H6] EMA_UP gate"


# ═══════════════════════════════════════════════════════════════
# Patch 4: gauge filter — use per-asset threshold for SELL
# ═══════════════════════════════════════════════════════════════

P4_ANCHOR = """                try:
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
                    pass"""

P4_NEW = """                try:
                    _gf = float(ad.gauge_force[fi])
                    if action == "BUY" and _gf < _gauge_thr_buy:
                        continue
                    if action == "SELL":
                        if getattr(CFG, 'SELL_ENABLED', False):
                            # [SELL-PER-ASSET-POOL] use per-asset threshold
                            if getattr(CFG,
                                       'SELL_GAUGE_POOL_PER_ASSET', False):
                                _thr_s = _gauge_thr_sell_per_asset.get(
                                    sym, _gauge_thr_sell)
                            else:
                                _pct_s = float(getattr(CFG,
                                    'SELL_GAUGE_PCT', 0.95))
                                _thr_s = np.percentile(
                                    _gauge_arr, _pct_s * 100) \\
                                    if len(_gauge_pool) > 0 \\
                                    else _gauge_thr_sell
                            if _gf < _thr_s:
                                continue
                        else:
                            if _gf < _gauge_thr_sell:
                                continue
                except Exception:
                    pass"""

P4_MARK = "[SELL-PER-ASSET-POOL] use per-asset threshold"


# ═══════════════════════════════════════════════════════════════
# Patch 5: CLI flags
# ═══════════════════════════════════════════════════════════════

P5_ANCHOR = '    p.add_argument("--sell-sl-widen-mult", type=float, default=None,\n                   help="SL widening factor for SELL only (default 1.0)")'
P5_NEW = '''    p.add_argument("--sell-sl-widen-mult", type=float, default=None,
                   help="SL widening factor for SELL only (default 1.0)")
    # [SELL-H6] flags
    p.add_argument("--sell-require-ema-up", action="store_true")
    p.add_argument("--sell-ema-up-lookback", type=int, default=None)
    p.add_argument("--sell-per-asset-pool", action="store_true")
    p.add_argument("--sell-pool-min-samples", type=int, default=None)'''
P5_MARK = "--sell-require-ema-up"


# ═══════════════════════════════════════════════════════════════
# Patch 6: main() wiring
# ═══════════════════════════════════════════════════════════════

P6_ANCHOR = """    if args.sell_sl_widen_mult is not None:
        CFG.SELL_SL_WIDEN_MULT = float(args.sell_sl_widen_mult)"""
P6_NEW = """    if args.sell_sl_widen_mult is not None:
        CFG.SELL_SL_WIDEN_MULT = float(args.sell_sl_widen_mult)
    if args.sell_require_ema_up:
        CFG.SELL_REQUIRE_EMA_UP = True
    if args.sell_ema_up_lookback is not None:
        CFG.SELL_EMA_UP_LOOKBACK = int(args.sell_ema_up_lookback)
    if args.sell_per_asset_pool:
        CFG.SELL_GAUGE_POOL_PER_ASSET = True
    if args.sell_pool_min_samples is not None:
        CFG.SELL_GAUGE_POOL_MIN_SAMPLES = int(args.sell_pool_min_samples)"""
P6_MARK = "SELL_REQUIRE_EMA_UP = True"


# ═══════════════════════════════════════════════════════════════

def apply(text, old, new, marker, name):
    if marker in text:
        return text, f"SKIP: {name}"
    if old not in text:
        return text, f"ERR: {name} (anchor not found)"
    return text.replace(old, new, 1), f"OK: {name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_rnd_sell_only.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"ERR: {args.file} not found")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("=" * 70)
    print("  add_sell_h6.py")
    print("=" * 70)
    print()

    for old, new, marker, name in [
        (P1_ANCHOR, P1_NEW, P1_MARK, "Config params"),
        (P2_ANCHOR, P2_NEW, P2_MARK, "Per-asset gauge pool"),
        (P3_ANCHOR, P3_NEW, P3_MARK, "SELL EMA_UP gate"),
        (P4_ANCHOR, P4_NEW, P4_MARK, "Gauge filter per-asset"),
        (P5_ANCHOR, P5_NEW, P5_MARK, "CLI flags"),
        (P6_ANCHOR, P6_NEW, P6_MARK, "main wiring"),
    ]:
        text, s = apply(text, old, new, marker, name)
        print(f"  {s}")

    try:
        ast.parse(text)
        print("\n  OK: ast.parse")
    except SyntaxError as e:
        print(f"\n  ERR: syntax at {e.lineno}: {e.text}")
        return 3

    if text == original:
        print("\n  No changes")
        return 0

    if args.dry_run:
        print("\n  Dry run - nothing written")
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_h6_{ts}')
    shutil.copy2(p, backup)
    print(f"\n  Backup: {backup}")
    p.write_text(text, encoding='utf-8')
    print(f"  Written: {p}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
