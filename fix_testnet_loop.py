#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_testnet_loop.py — إصلاحات ما بعد التشخيص
1. Rejection memory (يمنع الحلقة اللانهائية)
2. log.info للـ GTX rejection (بدل debug)
3. Capital cap (testnet parity)

التشغيل:
    python3 fix_testnet_loop.py --dry-run
    python3 fix_testnet_loop.py
"""

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Fix #1: Rejection memory
# ═══════════════════════════════════════════════════════════════

FIX1_MARKER = "_REJECTED_SIGNALS: Dict[Tuple[str, int], float] = {}"

FIX1_ANCHOR = (
    "_PENDING_ORDERS: Dict[str, Dict] = {}\n"
    "_PENDING_ORDERS_PATH: str = \"\""
)

FIX1_INSERT = (
    "_PENDING_ORDERS: Dict[str, Dict] = {}\n"
    "_PENDING_ORDERS_PATH: str = \"\"\n"
    "\n"
    "# ══ [REJECTION-MEMORY] يمنع إعادة معالجة نفس الإشارة كل 5 ثوان.\n"
    "# Key = (symbol, close_idx). TTL = شمعة واحدة (close_idx يتغير تلقائياً).\n"
    "_REJECTED_SIGNALS: Dict[Tuple[str, int], float] = {}\n"
    "\n"
    "\n"
    "def _prune_rejected_signals(max_age_s: float = 3600.0) -> int:\n"
    "    \"\"\"احذف الإدخالات الأقدم من max_age_s. يُعيد العدد المحذوف.\"\"\"\n"
    "    global _REJECTED_SIGNALS\n"
    "    if not _REJECTED_SIGNALS:\n"
    "        return 0\n"
    "    now = time.time()\n"
    "    old = [k for k, t in _REJECTED_SIGNALS.items()\n"
    "           if now - t > max_age_s]\n"
    "    for k in old:\n"
    "        _REJECTED_SIGNALS.pop(k, None)\n"
    "    return len(old)"
)


# ═══════════════════════════════════════════════════════════════
# Fix #2: Rejection memory hook in run_live
# ═══════════════════════════════════════════════════════════════

FIX2_MARKER = "# [REJECTION-MEMORY] check before place_pending_entry"

FIX2_PAT = re.compile(
    r'(?P<indent>[ \t]+)rec = place_pending_entry\(\s*\n'
    r'(?P=indent)\s+exchange, sym, sd, qty, sig,\s*\n'
    r'(?P=indent)\s+timeout_s=_timeout_s,\s*\n'
    r'(?P=indent)\s+leverage=int\(dynamic_leverage\),\s*\n'
    r'(?P=indent)\s+ad=assets\[sym\],\s*\n'
    r'(?P=indent)\)\s*\n'
    r'(?P=indent)if rec is None:\s*\n'
    r'(?P=indent)\s+log\.info\(f"\[Pending\] \{sym\} rejected — skip"\)\s*\n'
    r'(?P=indent)\s+continue',
    re.MULTILINE,
)


def fix2_replace(m):
    ind = m.group('indent')
    return (
        f"{ind}# [REJECTION-MEMORY] check before place_pending_entry\n"
        f"{ind}_sig_rej_key = (sym, int(sig.close_idx))\n"
        f"{ind}if _sig_rej_key in _REJECTED_SIGNALS:\n"
        f"{ind}    continue\n"
        f"{ind}rec = place_pending_entry(\n"
        f"{ind}    exchange, sym, sd, qty, sig,\n"
        f"{ind}    timeout_s=_timeout_s,\n"
        f"{ind}    leverage=int(dynamic_leverage),\n"
        f"{ind}    ad=assets[sym],\n"
        f"{ind})\n"
        f"{ind}if rec is None:\n"
        f"{ind}    _REJECTED_SIGNALS[_sig_rej_key] = time.time()\n"
        f"{ind}    log.info(f\"[Pending] {{sym}} rejected — skip \"\n"
        f"{ind}             f\"(will not retry until next bar)\")\n"
        f"{ind}    continue"
    )


# ═══════════════════════════════════════════════════════════════
# Fix #3: GTX rejection log.debug → log.info
# ═══════════════════════════════════════════════════════════════

FIX3_MARKER = "GTX rejected (info)"

FIX3_PAT = re.compile(
    r'log\.debug\(f"\[Pending\] \{sym\} GTX rejected @ \{target:\.6f\}: \{e\}"\)'
)

FIX3_REPLACEMENT = (
    'log.info(f"[Pending] {sym} GTX rejected (info) @ "'
    ' f"{target:.6f}: {e}")'
)


# ═══════════════════════════════════════════════════════════════
# Fix #4: Capital cap
# ═══════════════════════════════════════════════════════════════

FIX4_MARKER = "# [CAPITAL-CAP] testnet parity"

FIX4_PAT = re.compile(
    r"cap_live = float\(bal\['USDT'\]\.get\('total'\) or bal\['USDT'\]\.get\('free'\) or 0\)"
)

FIX4_REPLACEMENT = (
    "# [CAPITAL-CAP] testnet parity\n"
    "                _bal_raw = float(bal['USDT'].get('total') "
    "or bal['USDT'].get('free') or 0)\n"
    "                _cap_mult = float(getattr(CFG, 'LIVE_CAPITAL_CAP_MULT', 1.5))\n"
    "                if _cap_mult > 0:\n"
    "                    cap_live = min(_bal_raw, "
    "float(CFG.INITIAL_CAPITAL) * _cap_mult)\n"
    "                else:\n"
    "                    cap_live = _bal_raw"
)


# ═══════════════════════════════════════════════════════════════
# محرك التطبيق
# ═══════════════════════════════════════════════════════════════

def try_fix(text, marker, pattern, replacer, name, dry_run=False):
    """يُعيد (new_text, status)."""
    if marker in text:
        return text, f"⏭️  {name}: مُطبَّق مسبقاً"
    m = pattern.search(text)
    if not m:
        return text, f"❌ {name}: لم يُعثر على النمط"
    count = len(pattern.findall(text))
    if count != 1:
        return text, f"⚠️  {name}: {count} مطابقة (متوقع 1)"
    if dry_run:
        return text, f"✅ {name}: جاهز (dry)"
    if callable(replacer):
        text = pattern.sub(replacer, text, count=1)
    else:
        text = pattern.sub(replacer, text, count=1)
    return text, f"✅ {name}: طُبِّق"


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
    print("  fix_testnet_loop.py")
    print("═" * 70)
    print()

    # ── Fix #1: Rejection memory declaration ──
    if FIX1_MARKER in text:
        print(f"  ⏭️  Fix #1: _REJECTED_SIGNALS مُطبَّق مسبقاً")
    elif FIX1_ANCHOR not in text:
        print(f"  ❌ Fix #1: anchor غير موجود")
        print(f"     (هل عدّلت _PENDING_ORDERS يدوياً؟)")
        return 2
    else:
        text = text.replace(FIX1_ANCHOR, FIX1_INSERT, 1)
        print(f"  ✅ Fix #1: أُضيف _REJECTED_SIGNALS + _prune_rejected_signals")
        text, _ = try_fix(text, "__NEVER__", re.compile(r"__NEVER__"),
                          "", "", dry_run=True)

    # ── Fix #2: Rejection memory hook ──
    text, status = try_fix(text, FIX2_MARKER, FIX2_PAT, fix2_replace,
                            "Fix #2: rejection memory hook",
                            dry_run=args.dry_run)
    print(f"  {status}")

    # ── Fix #3: GTX log.info ──
    text, status = try_fix(text, FIX3_MARKER, FIX3_PAT, FIX3_REPLACEMENT,
                            "Fix #3: GTX rejection → log.info",
                            dry_run=args.dry_run)
    print(f"  {status}")

    # ── Fix #4: Capital cap ──
    text, status = try_fix(text, FIX4_MARKER, FIX4_PAT, FIX4_REPLACEMENT,
                            "Fix #4: Capital cap",
                            dry_run=args.dry_run)
    print(f"  {status}")

    # ── التحقق ──
    try:
        ast.parse(text)
        print()
        print(f"  ✅ الصياغة صحيحة (ast.parse)")
    except SyntaxError as e:
        print()
        print(f"  ❌ خطأ صياغة: {e.lineno}: {e.text}")
        return 3

    if text == original:
        print()
        print("  ℹ️  لا تعديلات جديدة.")
        return 0

    if args.dry_run:
        print()
        print("═" * 70)
        print("  ℹ️  Dry run — لم يُكتب أي شيء")
        print("═" * 70)
        return 0

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = p.with_suffix(p.suffix + f'.bak_loop_{ts}')
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
    return 0


if __name__ == '__main__':
    sys.exit(main())
