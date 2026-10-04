#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_prod_buy_only.py — إنشاء نسخة الإنتاج المُجمَّدة (BUY-only).

التأثير:
  - يُنسخ trading_2.py → trading_prod_buy_only.py
  - يُضاف رأس تعريفي
  - يتحقق من GAUGE_DISABLE_SELL = True
  - لا تعديل على السلوك
"""

import argparse, ast, re, shutil, sys
from datetime import datetime
from pathlib import Path


PROD_HEADER = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════
  TRADING PRODUCTION — BUY-ONLY
═══════════════════════════════════════════════════════════════════════

  ⚠️  هذا ملف الإنتاج المُجمَّد.
  ⚠️  لا تُعدّله أثناء تشغيل Testnet.
  ⚠️  للبحث والتطوير استخدم: trading_rnd_sell_only.py

  الخصائص:
    • GAUGE_DISABLE_SELL = True (BUY-only)
    • SELL_ENABLED = False
    • Sharpe الأدنى عبر 3 سنوات = 1.606
    • GeoMean رأس المال = $1,873

  تاريخ الإنشاء: {date}
  المصدر: {source}

═══════════════════════════════════════════════════════════════════════
"""
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default='trading_2.py')
    ap.add_argument('--target', default='trading_prod_buy_only.py')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    src = Path(args.source)
    dst = Path(args.target)

    if not src.exists():
        print(f"ERR: {args.source} not found")
        return 1

    text = src.read_text(encoding='utf-8')

    # ── تحقق من الإعدادات ──
    checks = [
        (r"GAUGE_DISABLE_SELL:\s*bool\s*=\s*True",
         "GAUGE_DISABLE_SELL = True"),
        (r"SELL_ENABLED:\s*bool\s*=\s*False",
         "SELL_ENABLED = False"),
    ]
    ok = True
    for pattern, name in checks:
        if not re.search(pattern, text):
            print(f"  WARN: {name} غير مضبوط كما هو متوقع")
            ok = False
        else:
            print(f"  OK: {name}")

    if not ok:
        print("\n  ⚠️  الإعدادات لا تطابق توقعات BUY-only.")
        print("     شغّل enable_buy_only_mode.py أولاً.")
        if not args.dry_run:
            return 2

    # ── رأس جديد ──
    header = PROD_HEADER.format(
        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        source=args.source,
    )
    # احذف أول shebang + encoding (سنضع الجديد)
    text_no_header = re.sub(
        r"^#!/usr/bin/env python3\n# -\*- coding: utf-8 -\*-\n",
        "", text, count=1
    )
    new_text = header + "\n" + text_no_header

    # ── تحقق صياغة ──
    try:
        ast.parse(new_text)
        print("  OK: ast.parse")
    except SyntaxError as e:
        print(f"  ERR: syntax at {e.lineno}: {e.text}")
        return 3

    if args.dry_run:
        print(f"\n  Dry run - would write {dst}")
        return 0

    # ── كتابة ──
    dst.write_text(new_text, encoding='utf-8')
    print(f"\n  OK: wrote {dst}")
    print(f"  Size: {len(new_text):,} chars")
    print(f"\n  Next: تثبيت مرجع")
    print(f"        cp {dst} {dst}.v1.0_production")
    return 0


if __name__ == '__main__':
    sys.exit(main())
