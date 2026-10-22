#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_minimal.py — استخراج مُركَّز للأجزاء الحرجة فقط.

الناتج: review_extract.md (حجمه عادة 30-60 KB → ~15-30k token)
"""
import ast, re, sys
from pathlib import Path


SRC = "trading_2_live4_claude_v3.py"
OUT = "review_extract.md"

# ═══════════════════════════════════════════════════════════════
# ما نريد استخراجه (بالضبط)
# ═══════════════════════════════════════════════════════════════

# 1) Config fields (regex مطابقة)
CFG_PATTERNS = [
    r"REV_", r"LAD_", r"APEX_", r"REVERSAL_", r"SUBBAR_",
    r"SL_", r"TP_", r"BREAKEVEN_", r"PARTIAL_",
    r"MIN_NOTIONAL", r"MAX_CONCURRENT", r"LIQ_",
    r"PROTECTIVE_", r"TRAIL_", r"PAPER_", r"PO_",
]

# 2) الدوال الكاملة (بالاسم الدقيق)
TARGET_FUNCS = {
    # reversal core
    "_register_reversal_watcher",
    "monitor_reversal_watchers",
    "_rev_scan",
    "_rev_advance_filling",
    "_rev_handle_ready",
    "_rev_finalize",
    "_rev_expire",
    # reversal helpers
    "_rev_snap_price",
    "_rev_tick",
    "_rev_cid",
    "_rev_marketable_px",
    "_rev_best_px",
    "_rev_beyond_chase",
    "_rev_find_order",
    "_rev_cancel_and_confirm",
    "_rev_cur_from_order",
    "_rev_bank",
    "_rev_clear_order",
    "_rev_known_cids",
    "_rev_inflight_other",
    "_rev_sub_info",
    "_rev_main_sec",
    "_rev_exch_position",
    "_rev_atomic_dump",
    "_rev_ledger_purge",
    "_rev_ledger_save",
    "_rev_startup_recover",
    "_rev_qp_step",
    "_rev_ladder_advance",
    "_rev_ladder_cleanup",
    # ladder
    "_lad_levels",
    "_lad_px",
    "_lad_cid",
    "_lad_new_rec",
    "_lad_all_recs",
    "_lad_totals",
    "_lad_book",
    "_lad_apply",
    "_lad_place",
    "_lad_poll",
    "_lad_cancel",
    "_lad_sl_tp",
    "_lad_liq",
    "_lad_new_pos",
    "_lad_flatten",
    "_lad_protect",
    "_lad_sync_position",
    "_lad_stats",
    "_lad_finish",
    # bounce / apex
    "_bar_confirms_bounce",
    "check_thermodynamic_apex",
    # helpers
    "_snap_qty",
    "load_reversal_watchers",
    "save_reversal_watchers",
    "_last_closed_subbar_close",
}

# 3) السطر الأول + أول 5 أسطر من هذه الدوال (للتحقق فقط)
PARTIAL_FUNCS = {
    "run_live",           # يظهر أين يُستدعى apex + monitor
    "simulate_portfolio", # حيث يُعاد بناء SL/TP
    "main",               # wiring
    "_advance",           # حيث يُستدعى apex في backtest
}

# ═══════════════════════════════════════════════════════════════
# التنفيذ
# ═══════════════════════════════════════════════════════════════
def collect_funcs(tree, src_lines):
    """يرجّع dict {name: (start, end)} لكل دالة."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = (node.lineno - 1,
                              getattr(node, "end_lineno", node.lineno))
    return out


def extract_config_fields(src_lines, tree):
    """يستخرج فقط الحقول المطابقة لـ CFG_PATTERNS من class Config."""
    rx = re.compile("|".join(CFG_PATTERNS))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Config":
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 1)
            for i in range(start, end):
                line = src_lines[i]
                if rx.search(line) and ":" in line and "=" in line:
                    out.append(f"{i+1:6d}: {line.rstrip()}")
            break
    return "\n".join(out)


def extract_cli(src_lines):
    """يجمع كل p.add_argument."""
    out = []
    for i, line in enumerate(src_lines):
        if ("p.add_argument" in line or "ap.add_argument" in line):
            out.append(f"{i+1:6d}: {line.rstrip()}")
    return "\n".join(out)


def extract_wiring(src_lines, tree):
    """يجمع أسطر wiring (REV_/LAD_/REVERSAL_) في main()."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 1)
            rx = re.compile(r"REV_|LAD_|REVERSAL_|APEX_|rev_ladder|reversal")
            for i in range(start, end):
                line = src_lines[i]
                if rx.search(line):
                    out.append(f"{i+1:6d}: {line.rstrip()}")
            break
    return "\n".join(out)


def extract_partial(src_lines, tree, name: str, n_lines: int = 12):
    """يستخرج أول N سطر من دالة."""
    funcs = collect_funcs(tree, src_lines)
    if name not in funcs:
        return f"### ❌ `{name}` غير موجودة"
    s, e = funcs[name]
    body = src_lines[s:s + n_lines]
    out = [f"### 📄 `{name}` (lines {s+1}–{min(e, s+n_lines)}) — أول {n_lines} سطر"]
    out.append("```python")
    for j, line in enumerate(body):
        out.append(f"{s+j+1:6d}: {line.rstrip()}")
    if e > s + n_lines:
        out.append(f"    ... (+{e - (s+n_lines)} سطر لم تُعرَض)")
    out.append("```")
    return "\n".join(out)


def grep_markers(src_lines, patterns):
    """يجمع كل الأسطر المطابقة."""
    out = []
    for name, pat in patterns:
        rx = re.compile(pat)
        hits = [f"{i+1:6d}: {line.rstrip()}"
                for i, line in enumerate(src_lines) if rx.search(line)]
        out.append(f"### `{name}` — {len(hits)} نتيجة")
        if hits:
            out.append("```")
            out.extend(hits[:30])
            if len(hits) > 30:
                out.append(f"... +{len(hits)-30} أكثر")
            out.append("```")
    return "\n\n".join(out)


def build_report(src_path: Path) -> str:
    src = src_path.read_text(encoding="utf-8")
    src_lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return f"# ❌ خطأ في الصياغة: {e}"

    funcs = collect_funcs(tree, src_lines)

    out = []
    out.append(f"# 🔍 Review Extract — {src_path.name}")
    out.append(f"**أسطر:** {len(src_lines):,}  |  **حجم:** {src_path.stat().st_size:,} bytes")
    out.append("")

    # ── 1) Config fields ──
    out.append("## 1️⃣ حقول Config الحرجة")
    out.append("```")
    cfg = extract_config_fields(src_lines, tree)
    out.append(cfg if cfg else "(لا نتائج)")
    out.append("```")
    out.append("")

    # ── 2) الدوال الكاملة ──
    out.append("## 2️⃣ الدوال الكاملة (Reversal / Ladder / Apex)")
    out.append("")
    missing = []
    for name in sorted(TARGET_FUNCS):
        if name not in funcs:
            missing.append(name)
            continue
        s, e = funcs[name]
        out.append(f"### 📌 `{name}` — lines {s+1}–{e} ({e-s} سطر)")
        out.append("```python")
        out.extend(src_lines[s:e])
        out.append("```")
        out.append("")

    if missing:
        out.append(f"### ⚠️ دوال مطلوبة غير موجودة ({len(missing)})")
        out.append("```")
        out.append("\n".join(missing))
        out.append("```")
        out.append("")

    # ── 3) CLI ──
    out.append("## 3️⃣ CLI Flags")
    out.append("```")
    out.append(extract_cli(src_lines))
    out.append("```")
    out.append("")

    # ── 4) Wiring في main() ──
    out.append("## 4️⃣ Wiring في main()")
    out.append("```")
    out.append(extract_wiring(src_lines, tree))
    out.append("```")
    out.append("")

    # ── 5) أجزاء مختصرة ──
    out.append("## 5️⃣ أجزاء من دوال أخرى (للتحقق)")
    out.append("")
    for name in sorted(PARTIAL_FUNCS):
        out.append(extract_partial(src_lines, tree, name, n_lines=15))
        out.append("")

    # ── 6) مؤشرات grep ──
    out.append("## 6️⃣ مؤشرات (grep)")
    out.append("")
    markers = [
        ("REV_FIX_MARKERS", r"\[REV-FIX"),
        ("SUBBAR_ONLY", r"SUBBAR_ONLY"),
        ("REV_LADDER_ENABLED", r"REV_LADDER_ENABLED"),
        ("GTX_usage", r"['\"]GTX['\"]"),
        ("marketable_usage", r"marketable"),
        ("snap_qty_calls", r"_snap_qty\("),
        ("lad_place_calls", r"_lad_place\("),
        ("_bar_confirms_calls", r"_bar_confirms_bounce\("),
        ("apex_calls", r"check_thermodynamic_apex\("),
        ("monitor_rev_calls", r"monitor_reversal_watchers\("),
    ]
    out.append(grep_markers(src_lines, markers))
    out.append("")

    # ── 7) إحصاءات ──
    out.append("## 7️⃣ إحصاءات")
    out.append(f"- **عدد الدوال/الفئات الكلي:** {len(funcs)}")
    out.append(f"- **دوال reversal/ladder الموجودة:** "
               f"{sum(1 for n in TARGET_FUNCS if n in funcs)}/{len(TARGET_FUNCS)}")
    out.append(f"- **إصدارات REV-FIX:** "
               f"{len(re.findall(r'REV-FIX', src))}")
    out.append("")

    return "\n".join(out)


if __name__ == "__main__":
    p = Path(sys.argv[1] if len(sys.argv) > 1 else SRC)
    if not p.exists():
        print(f"✗ {p} not found"); sys.exit(1)
    report = build_report(p)
    Path(OUT).write_text(report, encoding="utf-8")
    size = Path(OUT).stat().st_size
    print(f"✓ {OUT}  ({size:,} bytes ≈ {size//4:,} tokens)")
    print(f"  → أرسل محتوى {OUT}")
