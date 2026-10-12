#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#  build_trading_final.sh
#  Patches trading_2_live2.py → trading_final.py with edge-tuned gates
#  Derived from brain_raw.py analysis (90d 4h, 20 assets, z-scan 0..3)
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

SRC="trading_2_live2.py"
DST="trading_final.py"

if [ ! -f "$SRC" ]; then
    echo "✗ $SRC not found in $(pwd)" >&2
    exit 1
fi

echo "→ Copying $SRC → $DST"
cp "$SRC" "$DST"

echo "→ Applying edge-tuned patches..."
python3 - "$DST" << 'PYEOF'
import sys, hashlib

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

def patch(old, new, label, count=1, required=True):
    global src
    n = src.count(old)
    if n < count:
        if required:
            print(f"  ✗ {label}: pattern not found ({n} matches)", file=sys.stderr)
            sys.exit(2)
        print(f"  ⚠ {label}: skipped (pattern not found)")
        return
    src = src.replace(old, new, count)
    print(f"  ✓ {label}")

# ═══════════════════════════════════════════════════════════════════
# 1. CFG FLAGS — disable suppressing filters, enable SELL
# ═══════════════════════════════════════════════════════════════════
patch(
    "MIN_SCORE: int=3",
    "MIN_SCORE: int=0",
    "MIN_SCORE: 3 → 0  (empirically reverse-correlated)"
)

patch(
    "GAUGE_FILTER_ENABLED: bool = True",
    "GAUGE_FILTER_ENABLED: bool = False",
    "GAUGE_FILTER: ON → OFF  (was hiding real edges)"
)

patch(
    "SELL_ENABLED: bool = False              # master switch",
    "SELL_ENABLED: bool = True               # [FINAL] edge-tuned",
    "SELL_ENABLED: False → True"
)

patch(
    "SELL_MIN_SCORE: int = 3                 # independent from BUY",
    "SELL_MIN_SCORE: int = 0                 # [FINAL] off",
    "SELL_MIN_SCORE: 3 → 0"
)

patch(
    "SELL_MIN_ZDEV: float = 1.5              # independent from BUY",
    "SELL_MIN_ZDEV: float = 0.0              # [FINAL] z-gate handles",
    "SELL_MIN_ZDEV: 1.5 → 0"
)

# ═══════════════════════════════════════════════════════════════════
# 2. Z-RANGE + PHYSICS GATES inside build_signals()
# ═══════════════════════════════════════════════════════════════════
Z_OLD = """            # [ABLATION-2c] softer deviation gate
            if abs(_z_dev) < 1.5:
                continue
            action = "BUY" if _z_dev < 0 else "SELL\""""

Z_NEW = """            # ═══ [FINAL EDGE GATES — from brain_raw.py analysis] ═══
            # BUY  edge: |z| in [1.5, 2.5] + T_info > 6.0   → Sharpe ~11
            # SELL edge:  z  in [2.5, 3.2] + gauge  > 0.12   → Sharpe ~7.5
            if _z_dev > 0:
                if _z_dev < 2.5 or _z_dev > 3.2:
                    continue
                _gf_now = float(ad.gauge_force[fi]) \\
                          if fi < len(ad.gauge_force) else 0.0
                if _gf_now < 0.12:
                    continue
                action = "SELL"
            else:
                _absz = abs(_z_dev)
                if _absz < 1.5 or _absz > 2.5:
                    continue
                _ti_now = float(ad.T_info[fi]) \\
                          if fi < len(ad.T_info) else 0.0
                if _ti_now < 6.0:
                    continue
                action = "BUY\""""

patch(Z_OLD, Z_NEW, "z-range + physics gates in build_signals()")

# ═══════════════════════════════════════════════════════════════════
# 3. ARGPARSE DEFAULTS — zero-arg run
# ═══════════════════════════════════════════════════════════════════
patch(
    'p.add_argument("--history-days",       type=int,   default=None)',
    'p.add_argument("--history-days",       type=int,   default=90)',
    "argparse: --history-days default=90"
)

patch(
    'p.add_argument("--nassets",       type=int,   default=15)',
    'p.add_argument("--nassets",       type=int,   default=20)',
    "argparse: --nassets default=20"
)

patch(
    'p.add_argument("--maxcon",       type=int,   default=2)',
    'p.add_argument("--maxcon",       type=int,   default=5)',
    "argparse: --maxcon default=5"
)

# ═══════════════════════════════════════════════════════════════════
# 4. HEADER BANNER (cosmetic — marks the build)
# ═══════════════════════════════════════════════════════════════════
H_OLD = "\u2554\u2550" * 0  # placeholder no-op
H_OLD = '║      محرك التداول الثرموديناميكي الكمي – الإصدار 6.1 (محرك التفرد المطور)    ║'
H_NEW = '║   FINAL v6.2 — Edge-Tuned  (BUY z∈[-2.5,-1.5] | SELL z∈[+2.5,+3.2])         ║'
patch(H_OLD, H_NEW, "header banner", required=False)

# ═══════════════════════════════════════════════════════════════════
# 5. WRITE
# ═══════════════════════════════════════════════════════════════════
with open(path, "w", encoding="utf-8") as f:
    f.write(src)

if src == orig:
    print("\n⚠  No patches applied — check source file", file=sys.stderr)
    sys.exit(3)

h = hashlib.sha256(src.encode()).hexdigest()[:12]
print(f"\n✓  {path} written  |  {len(src):,} bytes  |  sha256={h}")
PYEOF

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✓ Build complete: $DST"
echo "  → Run:  python $DST"
echo "═══════════════════════════════════════════════════════════"
