#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_rr_grid.py — Grid Search على R:R الأساسي
=================================================

يولّد 9 نسخ من trading_2.py (الذي هو abl8b) بمصفوفة:

            TP_MULT
         3.0    4.0    5.0
   1.0   A1     A2     A3
P  1.5   B1     B2     B3*    (B3 = baseline abl8b)
T  2.0   C1     C2     C3
_R

الملفات المُولَّدة: trading_2_rr_A1.py ... trading_2_rr_C3.py
لا يُعدّل trading_2.py الأصلي (Testnet يستمر بالعمل).

Idempotent: إعادة التشغيل تُعيد البناء من الصفر (آمن).
"""
import os
import re
import sys

SRC = "trading_2.py"

GRID = [
    ("A1", 1.0, 3.0),
    ("A2", 1.0, 4.0),
    ("A3", 1.0, 5.0),
    ("B1", 1.5, 3.0),
    ("B2", 1.5, 4.0),
    ("B3", 1.5, 5.0),   # ← baseline (abl8b)
    ("C1", 2.0, 3.0),
    ("C2", 2.0, 4.0),
    ("C3", 2.0, 5.0),
]


def _patch_field(text, field_name, new_value):
    """
    يبحث عن سطر `    FIELD: float = <num>` (مع أي تعليق بعده)
    ويستبدل <num> بـ new_value.
    يفشل إذا لم يجد تطابقاً واحداً.
    """
    pattern = rf"(    {re.escape(field_name)}: float = )([0-9]+\.?[0-9]*)(.*\n)"
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise RuntimeError(
            f"FIELD '{field_name}': expected 1 match, got {len(matches)}"
        )
    old_value = matches[0][1]
    tail = matches[0][2]
    new_line = f"    {field_name}: float = {new_value}{tail}"
    return re.sub(pattern, new_line, text, count=1), old_value


def _safe_write(path, text):
    # syntax check قبل الكتابة
    compile(text, path, "exec")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found in cwd.", file=sys.stderr)
        sys.exit(1)

    with open(SRC, encoding="utf-8") as f:
        base_text = f.read()

    # تحقق من القيم الحالية (للتقرير فقط)
    print("=" * 72)
    print("  R:R GRID GENERATOR")
    print("=" * 72)

    try:
        _, old_ptr = _patch_field(base_text, "PARTIAL_TP_R", 1.5)
        _, old_tpm = _patch_field(base_text, "TP_MULT", 5.0)
    except RuntimeError as e:
        print(f"ERROR inspecting base file: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"  Base file     : {SRC}")
    print(f"  Current PTR   : {old_ptr}")
    print(f"  Current TP_MUL: {old_tpm}")
    print("=" * 72)
    print()

    # تحقق أن baseline (B3) مطابق للملف الأصلي
    try:
        b3_text = base_text
        b3_text, _ = _patch_field(b3_text, "PARTIAL_TP_R", 1.5)
        b3_text, _ = _patch_field(b3_text, "TP_MULT", 5.0)
        if b3_text != base_text:
            print("  WARNING: baseline (B3) is NOT identical to base file.",
                  file=sys.stderr)
            print("           (base file may already differ from abl8b defaults)",
                  file=sys.stderr)
        else:
            print("  ✅ baseline B3 (1.5, 5.0) = base file (abl8b).")
    except RuntimeError:
        pass
    print()

    # توليد الملفات التسعة
    for tag, ptr, tpm in GRID:
        text = base_text
        try:
            text, _ = _patch_field(text, "PARTIAL_TP_R", ptr)
            text, _ = _patch_field(text, "TP_MULT", tpm)
        except RuntimeError as e:
            print(f"  ✗ {tag}: {e}", file=sys.stderr)
            continue
        dst = f"trading_2_rr_{tag}.py"
        try:
            _safe_write(dst, text)
            marker = "  ← BASELINE" if tag == "B3" else ""
            print(f"  ✓ {tag}: PTR={ptr}  TP_MULT={tpm}  → {dst}{marker}")
        except SyntaxError as e:
            print(f"  ✗ {tag}: syntax error: {e}", file=sys.stderr)

    print()
    print("Done. Now run:  bash run_rr_grid.sh")


if __name__ == "__main__":
    main()
