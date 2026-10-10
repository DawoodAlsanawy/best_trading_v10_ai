#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_sell_only_rnd.py — إنشاء نسخة R&D للبحث على SELL حصراً.

التغييرات عن production:
  1. رأس تعريفي جديد
  2. Config: BUY_DISABLED flag (جديد)
  3. Config: SELL_ENABLED = True افتراضياً
  4. build_signals: بوابة BUY
  5. حالة ملفات مستقلة (suffix: _sellrnd)
  6. Trade log افتراضي مستقل
"""

import argparse, ast, shutil, sys
from datetime import datetime
from pathlib import Path


RND_HEADER = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════
  TRADING R&D — SELL-ONLY
═══════════════════════════════════════════════════════════════════════

  ⚠️  هذا ملف البحث والتطوير.
  ⚠️  لا تستخدمه في الإنتاج. استخدم: trading_prod_buy_only.py
  ⚠️  BUY مُعطَّل تماماً. فقط SELL يُنتج إشارات.

  الهدف:
    • إيجاد أفضل إعداد لـ SELL حصراً.
    • عندما يصل SELL لأداء مُرضي (Min Sharpe ≥ 1.55)،
      ندمجه في production بعد اختبار دقيق.

  تاريخ الإنشاء: {date}
  المصدر: {source}

═══════════════════════════════════════════════════════════════════════
"""
'''


# ═══════════════════════════════════════════════════════════════
# Patch 1: BUY_DISABLED config
# ═══════════════════════════════════════════════════════════════

P1_ANCHOR = '    SELL_ENABLED: bool = False              # master switch'
P1_NEW = '''    SELL_ENABLED: bool = True               # [SELL-ONLY R&D] on
    BUY_DISABLED: bool = True               # [SELL-ONLY R&D] BUY off'''
P1_MARK = 'BUY_DISABLED: bool = True'


# ═══════════════════════════════════════════════════════════════
# Patch 2: BUY gate in build_signals
# ═══════════════════════════════════════════════════════════════

P2_ANCHOR = '''            # ══ [SELL-RND] بوابة SELL المستقلة ══
            # BUY لا يُلمَس. SELL فقط يُمرّر عبر هذه البوابة.
            if action == "SELL":'''

P2_NEW = '''            # ══ [SELL-ONLY-RND] بوابة BUY ══
            # BUY_DISABLED=True → كل إشارات BUY تُرفض.
            if action == "BUY":
                if getattr(CFG, 'BUY_DISABLED', False):
                    continue

            # ══ [SELL-RND] بوابة SELL المستقلة ══
            # BUY لا يُلمَس. SELL فقط يُمرّر عبر هذه البوابة.
            if action == "SELL":'''

P2_MARK = "# ══ [SELL-ONLY-RND] بوابة BUY"


# ═══════════════════════════════════════════════════════════════
# Patch 3: state files suffix
# ═══════════════════════════════════════════════════════════════

P3_ANCHOR_STATE = '''    state_file = f"live_state_{cfg.mode}.json"'''
P3_NEW_STATE = '''    state_file = f"live_state_{cfg.mode}_sellrnd.json"'''

P3_ANCHOR_PEND = '''    _PENDING_ORDERS_PATH = f"{CFG.PENDING_FILE_PREFIX}_{mode}.json"'''
P3_NEW_PEND = '''    _PENDING_ORDERS_PATH = f"{CFG.PENDING_FILE_PREFIX}_{mode}_sellrnd.json"'''

P3_ANCHOR_WATCH = '''    _WATCHED_SIGNALS_PATH = f"{CFG.WATCH_FILE_PREFIX}_{mode}.json"'''
P3_NEW_WATCH = '''    _WATCHED_SIGNALS_PATH = f"{CFG.WATCH_FILE_PREFIX}_{mode}_sellrnd.json"'''

P3_ANCHOR_META = '''    _SYMBOL_META_PATH = f"{CFG.SYMBOL_META_FILE}_{mode}.json"'''
P3_NEW_META = '''    _SYMBOL_META_PATH = f"{CFG.SYMBOL_META_FILE}_{mode}_sellrnd.json"'''


# ═══════════════════════════════════════════════════════════════
# Patch 4: trade log default
# ═══════════════════════════════════════════════════════════════

P4_ANCHOR = '''        _TRADE_LOG_PATH = f"trades_log_{mode}.jsonl"'''
P4_NEW = '''        _TRADE_LOG_PATH = f"trades_log_{mode}_sellrnd.jsonl"'''


# ═══════════════════════════════════════════════════════════════

def apply(text, old, new, marker, name):
    if marker and marker in text:
        return text, f"SKIP: {name}"
    if old not in text:
        return text, f"ERR: {name} (anchor not found)"
    return text.replace(old, new, 1), f"OK: {name}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default='trading_2.py')
    ap.add_argument('--target', default='trading_rnd_sell_only.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    src = Path(args.source)
    dst = Path(args.target)

    if not src.exists():
        print(f"ERR: {args.source} not found")
        return 1

    text = src.read_text(encoding='utf-8')

    print("=" * 70)
    print("  create_sell_only_rnd.py")
    print("=" * 70)
    print()

    # ── Patches on the body ──
    text, s = apply(text, P1_ANCHOR, P1_NEW, P1_MARK,
                    "Config: BUY_DISABLED + SELL_ENABLED")
    print(f"  {s}")

    text, s = apply(text, P2_ANCHOR, P2_NEW, P2_MARK,
                    "build_signals: BUY gate")
    print(f"  {s}")

    text, s = apply(text, P3_ANCHOR_STATE, P3_NEW_STATE, "_sellrnd.json",
                    "state file suffix")
    print(f"  {s}")

    text, s = apply(text, P3_ANCHOR_PEND, P3_NEW_PEND, None, "")
    print(f"  {s}")

    text, s = apply(text, P3_ANCHOR_WATCH, P3_NEW_WATCH, None, "")
    print(f"  {s}")

    text, s = apply(text, P3_ANCHOR_META, P3_NEW_META, None, "")
    print(f"  {s}")

    text, s = apply(text, P4_ANCHOR, P4_NEW, None,
                    "trade log default")
    print(f"  {s}")

    # ── Header ──
    header = RND_HEADER.format(
        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        source=args.source,
    )
    # Remove original shebang + encoding
    import re
    body = re.sub(
        r"^#!/usr/bin/env python3\n# -\*- coding: utf-8 -\*-\n",
        "", text, count=1
    )
    final = header + "\n" + body

    # ── Syntax check ──
    try:
        ast.parse(final)
        print("\n  OK: ast.parse")
    except SyntaxError as e:
        print(f"\n  ERR: syntax at {e.lineno}: {e.text}")
        return 3

    if args.dry_run:
        print(f"\n  Dry run - would write {dst}")
        return 0

    dst.write_text(final, encoding='utf-8')
    print(f"\n  OK: wrote {dst}")
    print(f"  Size: {len(final):,} chars")
    print()
    print("  Test:")
    print(f"    python3 {dst} --mode backtest --capital 100 \\")
    print(f"        --nassets 100 --timeframe 4h \\")
    print(f"        --no-fixed-price --no-trailing \\")
    print(f"        --end-date 2025-12-31 --history-days 365")
    return 0


if __name__ == '__main__':
    sys.exit(main())
