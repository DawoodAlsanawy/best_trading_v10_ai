#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anchors Diagnostic
يُظهر السياق الحقيقي في الملف حول كل anchor، ويقترح البديل الصحيح.
"""

import argparse
import sys
import re


def find_anchor_context(source, anchor_first_line, window=3):
    """يبحث عن أول سطر من الـ anchor ويطبع 3 أسطر قبله و10 بعده."""
    lines = source.split('\n')
    needle = anchor_first_line.strip()
    hits = []
    for i, ln in enumerate(lines):
        if needle in ln:
            hits.append(i)
    return hits, lines


def show_context(lines, idx, before=3, after=10):
    start = max(0, idx - before)
    end = min(len(lines), idx + after + 1)
    for i in range(start, end):
        marker = " >>>" if i == idx else "    "
        # escape غير مرئي
        display = lines[i].replace('\t', '→')
        # اظهر طول السطر (كشف مسافات زائدة)
        print(f"  {i+1:5d}{marker} {display!r}")


def show_anchor(name, anchor, source):
    print(f"\n{'═' * 78}")
    print(f"  ANCHOR: {name}")
    print(f"{'═' * 78}")
    anchor_lines = anchor.split('\n')
    first = anchor_lines[0]
    print(f"  Looking for first line: {first!r}")
    hits, lines = find_anchor_context(source, first)
    if not hits:
        print(f"  ✗ NOT FOUND: {first!r}")
        # جرّب أول 40 حرف فقط
        short = first.strip()[:40]
        print(f"  Trying short form: {short!r}")
        if short and len(short) > 10:
            hits, _ = find_anchor_context(source, short)
        if not hits:
            print(f"  ✗ Still not found. Trying key substring...")
            # extract a distinctive keyword
            for kw in ['SELL_MAJOR_PAIRS', 'result[\'market_price\']',
                       'place_pending_entry(', 'rec = place_pending_entry']:
                if kw in first:
                    hits, _ = find_anchor_context(source, kw)
                    if hits:
                        print(f"  Found using keyword: {kw!r}")
                        break
        if not hits:
            return
    print(f"  ✓ Found {len(hits)} match(es)")
    for idx in hits[:3]:
        print(f"\n  Context around line {idx+1}:")
        show_context(lines, idx, before=3, after=12)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default="trading_2_live2_1.py")
    args = p.parse_args()

    with open(args.target, "r", encoding="utf-8") as f:
        source = f.read()

    print(f"File: {args.target}")
    print(f"Size: {len(source)} chars, {source.count(chr(10))+1} lines")

    # ═══ F1: Config ═══
    F1 = '''    SELL_MAJOR_PAIRS: Tuple = ("BTC/USDT", "ETH/USDT",
                                "SOL/USDT", "BNB/USDT")

CFG = Config()'''
    show_anchor("F1_Config", F1, source)

    # ═══ F2: CoilFunctions ═══
    F2 = '''    result['market_price'] = micro['mid']
    return result


def run_live(cfg, exchange):'''
    show_anchor("F2_CoilFunctions", F2, source)

    # ═══ F4: LiveHook ═══
    F4 = '''                        rec = place_pending_entry(
                            exchange, sym, sd, qty, sig,
                            timeout_s=_timeout_s,
                            leverage=int(dynamic_leverage),
                            ad=assets[sym],
                        )'''
    show_anchor("F4_LiveHook", F4, source)

    # إضافي: اطبع كل الأسطر التي تحتوي على "SELL_MAJOR_PAIRS"
    print(f"\n{'═' * 78}")
    print(f"  SEARCH: 'SELL_MAJOR_PAIRS'")
    print(f"{'═' * 78}")
    hits, lines = find_anchor_context(source, "SELL_MAJOR_PAIRS")
    for idx in hits[:5]:
        print(f"\n  Line {idx+1}:")
        show_context(lines, idx, before=1, after=5)

    print(f"\n{'═' * 78}")
    print(f"  SEARCH: 'def run_live'")
    print(f"{'═' * 78}")
    hits, lines = find_anchor_context(source, "def run_live")
    for idx in hits[:5]:
        print(f"\n  Line {idx+1}:")
        show_context(lines, idx, before=4, after=2)

    print(f"\n{'═' * 78}")
    print(f"  SEARCH: 'rec = place_pending_entry'")
    print(f"{'═' * 78}")
    hits, lines = find_anchor_context(source, "rec = place_pending_entry")
    for idx in hits[:3]:
        print(f"\n  Line {idx+1}:")
        show_context(lines, idx, before=2, after=12)

    return 0


if __name__ == "__main__":
    sys.exit(main())
