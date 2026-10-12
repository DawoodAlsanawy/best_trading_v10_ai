#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create SELL-enabled copy — with validated Tinfo_or_gf filter
"""
import argparse
import os
import shutil
import sys
import time

DEFAULT_TARGET = "trading_2_live2_1.py"
DEFAULT_OUTPUT = "trading_2_live2_1_sell.py"


BASE_CHANGES = [
    {
        "name": "SELL_ENABLED",
        "old": "    SELL_ENABLED: bool = False              # master switch",
        "new": "    SELL_ENABLED: bool = True               # [SELL-COPY] ON",
        "idem": "[SELL-COPY] ON",
    },
    {
        "name": "GAUGE_DISABLE_SELL",
        "old": "    GAUGE_DISABLE_SELL: bool = True    # Default: BUY-only",
        "new": "    GAUGE_DISABLE_SELL: bool = False   # [SELL-COPY] allow SELL",
        "idem": "[SELL-COPY] allow SELL",
    },
]


FILTER_ANCHOR = """                if abs(_z_dev) < float(getattr(CFG, 'SELL_MIN_ZDEV', 1.5)):
                    continue"""

FILTER_TINFO_OR_GF = """
                # ══ [SELL-FILTER] Walk-Forward validated (6/8 windows) ══
                # Union: T_info ∈ [4.86, 6.32] OR gauge_force ∈ [0.105, 0.129]
                # Mean edge +15.5%, coverage 60%+
                _T_info_sell = float(ad.T_info[fi])
                _gf_sell = float(ad.gauge_force[fi])
                _pass_tinfo = (4.86 <= _T_info_sell <= 6.32)
                _pass_gf = (0.105 <= _gf_sell <= 0.129)
                if not (_pass_tinfo or _pass_gf):
                    continue"""

FILTER_TINFO_ONLY = """
                # ══ [SELL-FILTER] T_info only (4/5 windows on 5-split) ══
                _T_info_sell = float(ad.T_info[fi])
                if not (4.86 <= _T_info_sell <= 6.32):
                    continue"""

FILTER_SIGMA_ONLY = """
                # ══ [SELL-FILTER] sigma only ══
                _sigma_sell = float(ad.E_therm[fi])
                if not (0.0097 <= _sigma_sell <= 0.0133):
                    continue"""

FILTERS = {
    "none": "",
    "tinfo": FILTER_TINFO_ONLY,
    "sigma": FILTER_SIGMA_ONLY,
    "tinfo_or_gf": FILTER_TINFO_OR_GF,
}


FILTER_MARKERS = {
    "tinfo": "[SELL-FILTER] T_info only",
    "sigma": "[SELL-FILTER] sigma only",
    "tinfo_or_gf": "[SELL-FILTER] Walk-Forward validated",
}


def log(msg, level="INFO"):
    print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}", flush=True)


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass
    os.replace(tmp, path)


def apply_base(source):
    current = source
    for ch in BASE_CHANGES:
        if ch["idem"] in current:
            log(f"  [SKIP] {ch['name']}: already modified")
            continue
        if ch["old"] not in current:
            log(f"  [FAIL] {ch['name']}: anchor not found", level="ERROR")
            return None
        cnt = current.count(ch["old"])
        if cnt > 1:
            log(f"  [FAIL] {ch['name']}: appears {cnt}×", level="ERROR")
            return None
        current = current.replace(ch["old"], ch["new"], 1)
        log(f"  [OK  ] {ch['name']}")
    return current


def apply_filter(source, filter_name):
    if filter_name == "none":
        return source
    marker = FILTER_MARKERS.get(filter_name, "")
    if marker and marker in source:
        log(f"  [SKIP] filter: {filter_name} already applied")
        return source
    if FILTER_ANCHOR not in source:
        log(f"  [FAIL] filter: anchor not found", level="ERROR")
        return None
    cnt = source.count(FILTER_ANCHOR)
    if cnt > 1:
        log(f"  [FAIL] filter: appears {cnt}×", level="ERROR")
        return None
    inject = FILTERS[filter_name]
    source = source.replace(FILTER_ANCHOR, FILTER_ANCHOR + inject, 1)
    log(f"  [OK  ] filter={filter_name}")
    return source


def cmd_create(target, output, filter_name):
    if not os.path.exists(target):
        log(f"Target not found: {target}", level="ERROR")
        return 1
    if os.path.exists(output):
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = f"{output}.{ts}.bak"
        shutil.copy2(output, backup)
        log(f"Backup: {backup}")
    log(f"Reading {target}")
    src = read_file(target)
    log(f"  {len(src)} chars\n")

    log("Base changes:")
    src = apply_base(src)
    if src is None:
        return 2

    log(f"\nFilter: {filter_name}")
    src = apply_filter(src, filter_name)
    if src is None:
        return 3

    try:
        compile(src, output, "exec")
        log(f"\nSyntax check: OK")
    except SyntaxError as e:
        log(f"Syntax error: {e}", level="ERROR")
        return 4

    write_file(output, src)
    log(f"\n✓ Created: {output}  ({len(src)} chars)")
    return 0


def cmd_verify(output, filter_name):
    if not os.path.exists(output):
        log(f"Not found: {output}", level="ERROR")
        return 1
    src = read_file(output)
    ok = True
    for ch in BASE_CHANGES:
        if ch["idem"] in src:
            print(f"  [OK  ] {ch['name']}")
        else:
            print(f"  [MISS] {ch['name']}")
            ok = False
    if filter_name != "none":
        marker = FILTER_MARKERS.get(filter_name, "")
        if marker and marker in src:
            print(f"  [OK  ] filter={filter_name}")
        else:
            print(f"  [MISS] filter={filter_name}")
            ok = False
    return 0 if ok else 1


def cmd_rollback(output):
    if os.path.exists(output):
        os.remove(output)
        log(f"Removed: {output}")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default=DEFAULT_TARGET)
    p.add_argument("--output", default=DEFAULT_OUTPUT)
    p.add_argument("--filter",
                   choices=["none", "tinfo", "sigma", "tinfo_or_gf"],
                   default="tinfo_or_gf")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--rollback", action="store_true")
    args = p.parse_args()

    if args.rollback:
        return cmd_rollback(args.output)
    if args.verify_only:
        return cmd_verify(args.output, args.filter)
    return cmd_create(args.target, args.output, args.filter)


if __name__ == "__main__":
    sys.exit(main())
