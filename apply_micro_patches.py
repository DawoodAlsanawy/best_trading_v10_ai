#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  apply_micro_patches.py  —  تحويل البوت للعمل برأس مال $1                    ║
║                                                                              ║
║  يطبق 9 تعديلات على trading_micro.py:                                        ║
║    1. CAPITAL_FLOOR: 0.15 → 0.01                                             ║
║    2. إضافة MICRO_MODE config                                                ║
║    3. MAX_CONCURRENT_ASSETS: 3 → 1                                           ║
║    4. Leverage: BASE 50→100, MIN 5→50, MAX 50→125                            ║
║    5. MAX_ABS_NOTIONAL: 20,000 → 50                                          ║
║    6. إضافة _symbol_allows_micro() helper                                    ║
║    7. MICRO override A في simulate_portfolio()                                ║
║    8. MICRO override B في simulate_portfolio() (بعد slippage)               ║
║    9. MICRO_GUARD في run_live()                                              ║
║                                                                              ║
║  الاستخدام:                                                                  ║
║    python3 apply_micro_patches.py [path_to_bot]                              ║
║    (الافتراضي: trading_micro.py)                                             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import shutil
import subprocess
from datetime import datetime

BOT_PATH = sys.argv[1] if len(sys.argv) > 1 else "trading_micro_2.py"

if not os.path.exists(BOT_PATH):
    print(f"❌ الملف غير موجود: {BOT_PATH}")
    sys.exit(1)

print(f"📂 الملف المستهدف: {BOT_PATH}")

with open(BOT_PATH, 'r', encoding='utf-8') as f:
    content = f.read()
original_content = content

patches_applied = []
patches_skipped = []
patches_failed = []


# ═══════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════

def apply_patch(name, old_str, new_str):
    """Replace exact string (must appear exactly once)."""
    global content
    if new_str in content and old_str not in content:
        patches_skipped.append(name)
        print(f"  ⏭  {name}: already applied")
        return
    count = content.count(old_str)
    if count == 0:
        patches_failed.append(f"{name} (string not found)")
        print(f"  ❌ {name}: NOT FOUND")
        return
    if count > 1:
        patches_failed.append(f"{name} (appears {count}×)")
        print(f"  ⚠️  {name}: found {count} occurrences")
        return
    content = content.replace(old_str, new_str)
    patches_applied.append(name)
    print(f"  ✅ {name}")


def insert_after(name, marker, insert_code):
    """Insert insert_code immediately AFTER marker (idempotent)."""
    global content
    if insert_code.strip() in content:
        patches_skipped.append(name)
        print(f"  ⏭  {name}: already applied")
        return
    idx = content.find(marker)
    if idx == -1:
        patches_failed.append(f"{name} (marker not found)")
        print(f"  ❌ {name}: marker not found")
        return
    if content.count(marker) > 1:
        patches_failed.append(f"{name} (marker appears multiple times)")
        print(f"  ⚠️  {name}: marker appears {content.count(marker)}×")
        return
    idx += len(marker)
    content = content[:idx] + insert_code + content[idx:]
    patches_applied.append(name)
    print(f"  ✅ {name}")


# ═══════════════════════════════════════════════════════════════════
# PATCH 1: CAPITAL_FLOOR
# ═══════════════════════════════════════════════════════════════════

print("\n[1/9] CAPITAL_FLOOR: 0.15 → 0.01")
apply_patch(
    "CAPITAL_FLOOR",
    "CAPITAL_FLOOR: float = 0.15",
    "CAPITAL_FLOOR: float = 0.01    # [MICRO] كان 0.15"
)


# ═══════════════════════════════════════════════════════════════════
# PATCH 2: MICRO settings
# ═══════════════════════════════════════════════════════════════════

print("\n[2/9] Add MICRO_MODE config")
_micro_cfg = """

    # ══ [MICRO-MODE] إعدادات رأس المال الصغير ($1) ══
    # يستخدم Notional ثابت ($5.20) بدلاً من Risk-Based sizing
    MICRO_MODE: bool = True
    MICRO_FIXED_NOTIONAL: float = 5.20  # $5 + 4% أمان (تجاوز -1013)
    MICRO_MAX_RISK_OVERRIDE: float = 0.15  # سقف المخاطرة 15% لكل صفقة
"""
insert_after(
    "MICRO config",
    "CAPITAL_FLOOR: float = 0.01    # [MICRO] كان 0.15",
    _micro_cfg
)


# ═══════════════════════════════════════════════════════════════════
# PATCH 3: MAX_CONCURRENT_ASSETS
# ═══════════════════════════════════════════════════════════════════

print("\n[3/9] MAX_CONCURRENT_ASSETS: 3 → 1")
apply_patch(
    "MAX_CONCURRENT_ASSETS",
    "MAX_CONCURRENT_ASSETS: int   = 3   # [ABL6] 5 -> 3",
    "MAX_CONCURRENT_ASSETS: int   = 1   # [MICRO] كان 3 - مركز واحد فقط"
)


# ═══════════════════════════════════════════════════════════════════
# PATCH 4: Leverage
# ═══════════════════════════════════════════════════════════════════

print("\n[4/9] Leverage: BASE→100, MIN→50, MAX→125")
apply_patch(
    "LEVERAGE_BASE",
    "LEVERAGE_BASE: float = 50.0   # نبدأ بـ 50x بقوة دفع هائلة",
    "LEVERAGE_BASE: float = 100.0   # [MICRO] كان 50x"
)
apply_patch(
    "LEVERAGE_MIN",
    "LEVERAGE_MIN: int = 5",
    "LEVERAGE_MIN: int = 50   # [MICRO] كان 5"
)
apply_patch(
    "LEVERAGE_MAX",
    "LEVERAGE_MAX: int = 50",
    "LEVERAGE_MAX: int = 125   # [MICRO] كان 50"
)


# ═══════════════════════════════════════════════════════════════════
# PATCH 5: MAX_ABS_NOTIONAL
# ═══════════════════════════════════════════════════════════════════

print("\n[5/9] MAX_ABS_NOTIONAL: 20,000 → 50")
apply_patch(
    "MAX_ABS_NOTIONAL",
    "MAX_ABS_NOTIONAL: float = 20_000.0     # tuned for alt liquidity",
    "MAX_ABS_NOTIONAL: float = 50.0     # [MICRO] كان 20,000"
)


# ═══════════════════════════════════════════════════════════════════
# PATCH 6: _symbol_allows_micro helper
# ═══════════════════════════════════════════════════════════════════

print("\n[6/9] Add _symbol_allows_micro() helper")
_micro_helper = '''def _symbol_allows_micro(exchange, symbol: str, min_notional_req: float = 5.0) -> bool:
    """
    [MICRO] تحقق أن الرمز يقبل Notional <= min_notional_req.
    يرفض رموزاً مثل BTC/ETH التي تطلب $100+ (تجنب -1013).
    يمكن استدعاؤها من scan_top_assets أو قبل وضع أي أمر.
    """
    try:
        mkt = exchange.market(symbol)
        if not mkt:
            return False
        info = mkt.get('info') or {}
        for f in (info.get('filters') or []):
            if isinstance(f, dict) and f.get('filterType') == 'MIN_NOTIONAL':
                _min_notional = float(f.get('notional', 5))
                if _min_notional > min_notional_req:
                    return False
        return True
    except Exception:
        return False


'''
apply_patch(
    "_symbol_allows_micro helper",
    "def scan_top_assets(exchange, n=None) -> List[str]:",
    _micro_helper + "def scan_top_assets(exchange, n=None) -> List[str]:"
)


# ═══════════════════════════════════════════════════════════════════
# PATCH 7: MICRO override A in simulate_portfolio (before MIN_NOTIONAL check)
# ═══════════════════════════════════════════════════════════════════

print("\n[7/9] MICRO override A in simulate_portfolio()")
_override_a = """
        # ══ [MICRO-MODE A] Fixed notional override (before first check) ══
        if getattr(CFG, 'MICRO_MODE', False):
            _micro_qty_a = CFG.MICRO_FIXED_NOTIONAL / max(opt_px, 1e-9)
            _micro_risk_a = (_micro_qty_a * delta) / max(equity_base, 1e-9)
            if _micro_risk_a > CFG.MICRO_MAX_RISK_OVERRIDE:
                log.debug(f"[Micro-BT] {sym} skipped: risk {_micro_risk_a*100:.1f}% > {CFG.MICRO_MAX_RISK_OVERRIDE*100:.0f}%")
                continue
            qty = _micro_qty_a
            sig.dynamic_risk = float(_micro_risk_a)
"""
insert_after(
    "MICRO override A",
    "        max_notional = capital * dynamic_leverage\n        qty = min(qty, max_notional / opt_px)",
    _override_a
)


# ═══════════════════════════════════════════════════════════════════
# PATCH 8: MICRO override B in simulate_portfolio (after slippage recalc)
# ═══════════════════════════════════════════════════════════════════

print("\n[8/9] MICRO override B in simulate_portfolio()")
_override_b = """
        # ══ [MICRO-MODE B] Re-apply after slippage recalculation ══
        if getattr(CFG, 'MICRO_MODE', False):
            qty = CFG.MICRO_FIXED_NOTIONAL / max(eff_px, 1e-9)
"""
insert_after(
    "MICRO override B",
    "        qty = min(risk_amt / delta, max_notional / eff_px)",
    _override_b
)


# ═══════════════════════════════════════════════════════════════════
# PATCH 9: MICRO_GUARD in run_live (before MIN_NOTIONAL check)
# ═══════════════════════════════════════════════════════════════════

print("\n[9/9] MICRO_GUARD in run_live()")
_micro_live = """
                    # ══ [MICRO-GUARD] Fixed notional + risk cap ══
                    if getattr(CFG, 'MICRO_MODE', False):
                        _micro_qty_l = CFG.MICRO_FIXED_NOTIONAL / max(lmt, 1e-9)
                        _micro_risk_l = (_micro_qty_l * delta) / max(equity_base, 1e-9)
                        if _micro_risk_l > CFG.MICRO_MAX_RISK_OVERRIDE:
                            log.debug(f"[Micro-Live] {sym} skipped: risk {_micro_risk_l*100:.1f}% > {CFG.MICRO_MAX_RISK_OVERRIDE*100:.0f}%")
                            continue
                        qty = _micro_qty_l
                        risk_frac = _micro_risk_l
                        sig.dynamic_risk = float(_micro_risk_l)
"""
insert_after(
    "MICRO_GUARD live",
    "                    qty = min(qty_risk_based, qty_leverage_based)",
    _micro_live
)


# ═══════════════════════════════════════════════════════════════════
# Summary + Save
# ═══════════════════════════════════════════════════════════════════

print("\n" + "═" * 70)
print("📊 SUMMARY")
print("═" * 70)
print(f"  ✅ Applied:  {len(patches_applied)}")
print(f"  ⏭  Skipped:  {len(patches_skipped)}")
print(f"  ❌ Failed:   {len(patches_failed)}")

if patches_failed:
    print("\n⚠️  Failed patches (manual fix required):")
    for p in patches_failed:
        print(f"    - {p}")

if content == original_content:
    print("\n⏸  No changes needed. File unchanged.")
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════
# Backup + Write
# ═══════════════════════════════════════════════════════════════════

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{BOT_PATH}.backup_{timestamp}"
shutil.copy2(BOT_PATH, backup_path)
print(f"\n💾 Backup saved: {backup_path}")

with open(BOT_PATH, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"✅ File updated: {BOT_PATH}")


# ═══════════════════════════════════════════════════════════════════
# Syntax verification
# ═══════════════════════════════════════════════════════════════════

print("\n⏳ Verifying syntax...")
result = subprocess.run(
    [sys.executable, "-c",
     f"import ast; ast.parse(open(r'{BOT_PATH}', encoding='utf-8').read())"],
    capture_output=True, text=True
)

if result.returncode == 0:
    print("✅ Syntax OK")
else:
    print("❌ Syntax error:")
    print(result.stderr)
    print(f"\n🔄 Restoring from backup...")
    shutil.copy2(backup_path, BOT_PATH)
    print("✅ Restored. Please report the error.")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════
# Next steps
# ═══════════════════════════════════════════════════════════════════

print("\n" + "═" * 70)
print("✨ Done. Next steps:")
print("═" * 70)
print(f"""
1. Test backtest with $1:
   python3 {BOT_PATH} --mode backtest --capital 1 --nassets 100 \\
       --timeframe 4h --history-days 730 --no-fixed-price --enable-sell \\
       --sell-gauge-pct 85 --tp-mult 2.5 --sl-widen-mult 1.5 \\
       --partial-tp-r 1.5 --maxcon 1 --workers 1 --reversal-confirm \\
       --reversal-mode sigma_bounce --reversal-kappa 0.3 \\
       --reversal-touch-subbars 48 --reversal-bounce-subbars 48 \\
       --reversal-fill target --po-wait-s 300 --no-apex --no-trailing

2. Expected: FEWER trades (many will be rejected by MICRO_MAX_RISK_OVERRIDE=15%)
   Look for "[Micro-BT] ... skipped: risk > 15%" in logs.

3. Check the fill count. If < 100 trades over 2 years, the strategy
   is too restricted for $1 — consider increasing MICRO_MAX_RISK_OVERRIDE to 0.20.

4. If fill count is reasonable (>300), run Testnet for 1 week.

5. DO NOT go Live with $1. Read the risks in the chat before proceeding.

6. To revert: cp {backup_path} {BOT_PATH}
""")


# ═══════════════════════════════════════════════════════════════════
# Test backtest with $1 (run automatically)
# ═══════════════════════════════════════════════════════════════════

print("\n" + "═" * 70)
print("🧪 TESTING BACKTEST WITH $1 CAPITAL")
print("═" * 70)
print("Running: (may take 3-8 minutes)")
print()
print(f"  python3 {BOT_PATH} --mode backtest --capital 1 ...")
print()

test_cmd = [
    sys.executable, BOT_PATH,
    "--mode", "backtest",
    "--capital", "1",
    "--nassets", "100",
    "--timeframe", "4h",
    "--history-days", "730",
    "--no-fixed-price",
    "--enable-sell",
    "--sell-gauge-pct", "85",
    "--tp-mult", "2.5",
    "--sl-widen-mult", "1.5",
    "--partial-tp-r", "1.5",
    "--maxcon", "1",
    "--workers", "1",
    "--reversal-confirm",
    "--reversal-mode", "sigma_bounce",
    "--reversal-kappa", "0.3",
    "--reversal-touch-subbars", "48",
    "--reversal-bounce-subbars", "48",
    "--reversal-fill", "target",
    "--po-wait-s", "300",
    "--no-apex",
    "--no-trailing",
]

try:
    result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=1800)
    print(result.stdout[-3000:])  # last 3000 chars
    if result.stderr:
        print("\n--- stderr ---")
        print(result.stderr[-1000:])
except subprocess.TimeoutExpired:
    print("⚠️ Test timed out after 30 minutes (skipped auto-run)")
except Exception as e:
    print(f"⚠️ Auto-run failed: {e}")
    print("Run manually using the command above.")
