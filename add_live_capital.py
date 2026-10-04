#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_live_capital.py — يُضيف --live-capital flag للتحكم برأس المال المتداول.

- Config: LIVE_TRADING_CAPITAL = 0 (يعني: استخدم free من البورصة)
- CLI: --live-capital <float>
- run_live: cap_live = LIVE_TRADING_CAPITAL if > 0 else free

لا يمس أي منطق فيزيائي، لا يمس الباكتيست.
"""

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# 1. Config: LIVE_TRADING_CAPITAL
# ═══════════════════════════════════════════════════════════════

CONFIG_ANCHOR = "    INITIAL_CAPITAL: float = 10.0 # الانطلاق بـ 10$"
CONFIG_NEW = (
    "    INITIAL_CAPITAL: float = 10.0 # الانطلاق بـ 10$\n"
    "    # ══ [LIVE-CAPITAL] رأس المال المتداول في Live/Testnet.\n"
    "    # 0 = استخدم free من البورصة (السلوك الافتراضي).\n"
    "    # >0 = رأس مال ثابت للـ sizing (لا يتأثر بحركة margin).\n"
    "    LIVE_TRADING_CAPITAL: float = 0.0"
)


# ═══════════════════════════════════════════════════════════════
# 2. CLI: --live-capital
# ═══════════════════════════════════════════════════════════════

CLI_ANCHOR = '    p.add_argument("--capital",     type=float, default=None)'
CLI_NEW = (
    '    p.add_argument("--capital",     type=float, default=None)\n'
    '    p.add_argument("--live-capital", type=float, default=None,\n'
    '                   help="Fixed trading capital for live/testnet '
    'sizing (overrides exchange free balance)")'
)

# تطبيق الـ arg
ARGS_ANCHOR = "    if args.capital   is not None: CFG.INITIAL_CAPITAL = args.capital"
ARGS_NEW = (
    "    if args.capital   is not None: CFG.INITIAL_CAPITAL = args.capital\n"
    "    if args.live_capital is not None: "
    "CFG.LIVE_TRADING_CAPITAL = float(args.live_capital)"
)


# ═══════════════════════════════════════════════════════════════
# 3. run_live: استخدام LIVE_TRADING_CAPITAL
# ═══════════════════════════════════════════════════════════════

# ابحث عن كتلة fetch_balance في run_live
CAP_BLOCK_PAT = re.compile(
    r"try:\s*\n"
    r"(?P<ind1>[ \t]+)bal = exchange\.fetch_balance\(\)\s*\n"
    r"(?P=ind1)# \[CAPITAL-CAP-V2\][^\n]*\n"
    r"(?P=ind1)_bal_raw = float\(bal\['USDT'\]\.get\('total'\) "
    r"or bal\['USDT'\]\.get\('free'\) or 0\)\s*\n"
    r"(?P=ind1)_cap_mult = float\(getattr\(CFG, "
    r"'LIVE_CAPITAL_CAP_MULT', 1\.5\)\)\s*\n"
    r"(?P=ind1)_bot_cap = float\(CFG\.INITIAL_CAPITAL\)\s*\n"
    r"(?P=ind1)if _cap_mult > 0 and _bal_raw > _bot_cap \* _cap_mult:\s*\n"
    r"(?P=ind1)    cap_live = _bot_cap\s*\n"
    r"(?P=ind1)else:\s*\n"
    r"(?P=ind1)    cap_live = _bal_raw\s*\n"
    r"(?P=ind1)_last_known_cap = cap_live\s*\n",
    re.MULTILINE,
)

# نمط قديم من النسخة السابقة (قبل CAPITAL-CAP-V2)
CAP_BLOCK_OLD_PAT = re.compile(
    r"try:\s*\n"
    r"(?P<ind1>[ \t]+)bal = exchange\.fetch_balance\(\)\s*\n"
    r"(?P=ind1)cap_live = float\(bal\['USDT'\]\.get\('total'\) "
    r"or bal\['USDT'\]\.get\('free'\) or 0\)\s*\n"
    r"(?P=ind1)_last_known_cap = cap_live\s*\n",
    re.MULTILINE,
)

# نمط أصلي بسيط
CAP_BLOCK_SIMPLE_PAT = re.compile(
    r"try:\s*\n"
    r"(?P<ind1>[ \t]+)bal = exchange\.fetch_balance\(\)\s*\n"
    r"(?P=ind1)cap_live = float\(bal\['USDT'\]\['free'\]\)\s*\n"
    r"(?P=ind1)_last_known_cap = cap_live\s*\n",
    re.MULTILINE,
)


def make_cap_block(match):
    ind = match.group('ind1')
    return (
        f"try:\n"
        f"{ind}bal = exchange.fetch_balance()\n"
        f"{ind}# ══ [LIVE-CAPITAL] استخدم LIVE_TRADING_CAPITAL إن كان مضبوطاً.\n"
        f"{ind}_bal_free = float(bal['USDT'].get('free') or 0)\n"
        f"{ind}_bal_total = float(bal['USDT'].get('total') or 0)\n"
        f"{ind}_fixed_cap = float(getattr(CFG, 'LIVE_TRADING_CAPITAL', 0.0))\n"
        f"{ind}if _fixed_cap > 0:\n"
        f"{ind}    cap_live = _fixed_cap\n"
        f"{ind}else:\n"
        f"{ind}    # السلوك الافتراضي: free (الحد المتداول الفعلي)\n"
        f"{ind}    cap_live = _bal_free\n"
        f"{ind}_last_known_cap = cap_live\n"
    )


# ═══════════════════════════════════════════════════════════════
# التطبيق
# ═══════════════════════════════════════════════════════════════

def apply_patch(text, anchor, replacement, name):
    if replacement.strip() in text:
        return text, f"⏭️  {name}: مُطبَّق مسبقاً"
    if anchor not in text:
        return text, f"❌ {name}: anchor غير موجود"
    text = text.replace(anchor, replacement, 1)
    return text, f"✅ {name}: طُبِّق"


def apply_cap_block(text):
    # جرّب الأنماط بالترتيب
    for pat, label in [(CAP_BLOCK_PAT, "v2"),
                       (CAP_BLOCK_OLD_PAT, "old"),
                       (CAP_BLOCK_SIMPLE_PAT, "simple")]:
        m = pat.search(text)
        if m:
            # فحص idempotency
            block_start = m.start()
            look = text[block_start:block_start + 500]
            if "[LIVE-CAPITAL]" in look:
                return text, f"⏭️  CAP block: مُطبَّق مسبقاً"
            text = pat.sub(make_cap_block, text, count=1)
            return text, f"✅ CAP block: طُبِّق (pattern={label})"
    return text, "❌ CAP block: لم يُعثر على نمط مطابق"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', default='trading_2.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"❌ {args.file} غير موجود")
        return 1

    original = p.read_text(encoding='utf-8')
    text = original

    print("═" * 70)
    print("  add_live_capital.py")
    print("═" * 70)
    print()

    text, s = apply_patch(text, CONFIG_ANCHOR, CONFIG_NEW,
                          "Config: LIVE_TRADING_CAPITAL")
    print(f"  {s}")

    text, s = apply_patch(text, CLI_ANCHOR, CLI_NEW,
                          "CLI: --live-capital flag")
    print(f"  {s}")

    text, s = apply_patch(text, ARGS_ANCHOR, ARGS_NEW,
                          "CLI: تطبيق --live-capital على CFG")
    print(f"  {s}")

    text, s = apply_cap_block(text)
    print(f"  {s}")

    # التحقق
    try:
        ast.parse(text)
        print()
        print("  ✅ الصياغة صحيحة (ast.parse)")
    except SyntaxError as e:
        print()
        print(f"  ❌ خطأ صياغة: {e.lineno}: {e.text}")
        return 3

    if text == original:
        print()
        print("  ℹ️  لا تعديلات جديدة")
        return 0

    if args.dry_run:
        print()
        print("═" * 70)
        print("  ℹ️  Dry run — لم يُكتب أي شيء")
        print("═" * 70)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_lc_{ts}')
    shutil.copy2(p, backup)
    print()
    print(f"  💾 Backup: {backup}")

    p.write_text(text, encoding='utf-8')
    print(f"  ✏️  كُتب: {p}")
    print()
    print("═" * 70)
    print("  ✅ تم")
    print("═" * 70)
    print(f"  للتراجع: cp {backup.name} {p.name}")
    print()
    print("  الاستخدام بعد التطبيق:")
    print("    python3 trading_2.py --mode testnet --live-capital 300 ...")
    return 0


if __name__ == '__main__':
    sys.exit(main())
