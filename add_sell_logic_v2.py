#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""add_sell_logic_v2.py — إضافة شروط منطق SELL المستقلة."""

import argparse, ast, shutil, sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Patch 1: Config params
# ═══════════════════════════════════════════════════════════════

P1_ANCHOR = "    SELL_MAJOR_PAIRS: Tuple = (\n        \"BTC/USDT\", \"ETH/USDT\",\n        \"SOL/USDT\", \"BNB/USDT\"\n    )"
P1_NEW = """    SELL_MAJOR_PAIRS: Tuple = (
        "BTC/USDT", "ETH/USDT",
        "SOL/USDT", "BNB/USDT"
    )

    # ══ [SELL-LOGIC-V2] شروط منطقية جديدة ══
    # كل واحدة تُضيف شرطاً مختلفاً على SELL. لا تُغيّر BUY.
    SELL_REQUIRE_ORDER_EMERGING: bool = False   # dH < 0
    SELL_REQUIRE_DECELERATING: bool = False     # ema_accel < 0
    SELL_REQUIRE_DOWNWARD_FORCE: bool = False   # geodesic_accel < 0
    SELL_REQUIRE_LOW_FRICTION: bool = False     # friction < p25
    SELL_FRICTION_PCT: float = 0.25             # للنافذة"""

P1_MARK = "[SELL-LOGIC-V2]"


# ═══════════════════════════════════════════════════════════════
# Patch 2: build_signals — SELL logic additions
# ═══════════════════════════════════════════════════════════════

P2_ANCHOR = """            # ══ [GAUGE-FILTER] ══
            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):"""

P2_NEW = """            # ══ [SELL-LOGIC-V2] شروط إضافية لـ SELL فقط ══
            if action == "SELL":
                # H1: Order Emergence
                if getattr(CFG, 'SELL_REQUIRE_ORDER_EMERGING', False):
                    if fi < len(ad.dH) and ad.dH[fi] >= 0:
                        continue
                # H2: Trend Deceleration
                if getattr(CFG, 'SELL_REQUIRE_DECELERATING', False):
                    if ci < len(ad.ema_accel) and ad.ema_accel[ci] >= 0:
                        continue
                # H3: Physics Direction Match
                if getattr(CFG, 'SELL_REQUIRE_DOWNWARD_FORCE', False):
                    if ad.geodesic_accel[fi] >= 0:
                        continue
                # H4: Low Friction
                if getattr(CFG, 'SELL_REQUIRE_LOW_FRICTION', False):
                    _fric_pct = float(getattr(CFG, 'SELL_FRICTION_PCT', 0.25))
                    _tr_start = int(getattr(ad, 'train_end', 0))
                    if _tr_start > 0 and _tr_start < len(ad.friction):
                        _fric_thr = float(np.percentile(
                            ad.friction[_tr_start:],
                            _fric_pct * 100.0
                        ))
                        if float(ad.friction[fi]) > _fric_thr:
                            continue

            # ══ [GAUGE-FILTER] ══
            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):"""

P2_MARK = "[SELL-LOGIC-V2]"


# ═══════════════════════════════════════════════════════════════
# Patch 3: CLI flags
# ═══════════════════════════════════════════════════════════════

P3_ANCHOR = '    p.add_argument("--sell-min-atr-frac", type=float, default=None)'
P3_NEW = '''    p.add_argument("--sell-min-atr-frac", type=float, default=None)
    # [SELL-LOGIC-V2] new logic flags
    p.add_argument("--sell-require-order-emerging", action="store_true")
    p.add_argument("--sell-require-decelerating", action="store_true")
    p.add_argument("--sell-require-downward-force", action="store_true")
    p.add_argument("--sell-require-low-friction", action="store_true")
    p.add_argument("--sell-friction-pct", type=float, default=None)'''

P3_MARK = "sell-require-order-emerging"


# ═══════════════════════════════════════════════════════════════
# Patch 4: main() wiring
# ═══════════════════════════════════════════════════════════════

P4_ANCHOR = '''    if args.sell_min_atr_frac is not None:
        CFG.SELL_MIN_ATR_FRAC = float(args.sell_min_atr_frac)'''

P4_NEW = '''    if args.sell_min_atr_frac is not None:
        CFG.SELL_MIN_ATR_FRAC = float(args.sell_min_atr_frac)
    if args.sell_require_order_emerging:
        CFG.SELL_REQUIRE_ORDER_EMERGING = True
    if args.sell_require_decelerating:
        CFG.SELL_REQUIRE_DECELERATING = True
    if args.sell_require_downward_force:
        CFG.SELL_REQUIRE_DOWNWARD_FORCE = True
    if args.sell_require_low_friction:
        CFG.SELL_REQUIRE_LOW_FRICTION = True
    if args.sell_friction_pct is not None:
        CFG.SELL_FRICTION_PCT = float(args.sell_friction_pct)'''

P4_MARK = "SELL_REQUIRE_ORDER_EMERGING = True"


# ═══════════════════════════════════════════════════════════════

def apply(text, old, new, marker, name):
    if marker in text:
        return text, f"SKIP: {name}"
    if old not in text:
        return text, f"ERR: {name}"
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
    print("  add_sell_logic_v2.py")
    print("=" * 70)
    print()

    text, s = apply(text, P1_ANCHOR, P1_NEW, P1_MARK, "Config params")
    print(f"  {s}")
    text, s = apply(text, P2_ANCHOR, P2_NEW, P2_MARK, "SELL logic gates")
    print(f"  {s}")
    text, s = apply(text, P3_ANCHOR, P3_NEW, P3_MARK, "CLI flags")
    print(f"  {s}")
    text, s = apply(text, P4_ANCHOR, P4_NEW, P4_MARK, "main() wiring")
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
    backup = p.with_suffix(p.suffix + f'.bak_logicv2_{ts}')
    shutil.copy2(p, backup)
    print(f"\n  Backup: {backup}")
    p.write_text(text, encoding='utf-8')
    print(f"  Written: {p}")
    print("\n" + "=" * 70)
    print("  Done")
    print("=" * 70)
    return 0


if __name__ == '__main__':
    sys.exit(main())
