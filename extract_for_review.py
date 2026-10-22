#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_for_review.py

يستخرج كل الأكواد المتعلقة بـ:
  - reversal-confirm (kappa, bounce, touch)
  - maker ladder
  - APEX
  - config fields
  - CLI flags + wiring
  - monitor_reversal_watchers

الناتج: review_extract.md (قابل للمشاركة)
"""
import ast
import re
import sys
from pathlib import Path
from collections import OrderedDict


SRC = "trading_2_live4_claude_v3.py"
OUT = "review_extract.md"


# ═══════════════════════════════════════════════════════════════
# 1) القوائم: أسماء الدوال/الفئات التي نريدها
# ═══════════════════════════════════════════════════════════════
PREFIXES = (
    "_rev_", "_lad_", "_lv_", "_watch_",
    "monitor_reversal", "load_reversal", "save_reversal",
)

SPECIFIC = {
    # الفئات والدوال الأساسية
    "Config", "main", "run_live", "run_backtest",
    "simulate_portfolio", "precompute_entry_fills",
    "_check_reversal_fill_subbars", "_advance",
    "build_signals", "_compute_entry_target",
    "_backtest_entry_target", "_precompute_watch_fills",
    "check_thermodynamic_apex",
    "_bar_confirms_bounce",
    "_register_reversal_watcher",
    # الإصلاحات الأخيرة
    "_snap_qty", "_rev_snap_price", "_rev_tick",
    "_rev_cid", "_rev_exch_position", "_rev_find_order",
    "_rev_cur_from_order", "_rev_bank", "_rev_clear_order",
    "_rev_cancel_and_confirm", "_rev_best_px", "_rev_beyond_chase",
    "_rev_expire", "_rev_known_cids", "_rev_inflight_other",
    "_rev_marketable_px", "_rev_sub_info", "_rev_main_sec",
    "_rev_atomic_dump", "_rev_ledger_purge", "_rev_ledger_save",
    "_rev_scan", "_rev_advance_filling", "_rev_handle_ready",
    "_rev_finalize", "_rev_qp_step", "_rev_ladder_advance",
    "_rev_ladder_cleanup", "_rev_startup_recover",
    "_last_closed_subbar_close",
}


# ═══════════════════════════════════════════════════════════════
# 2) استخراج line-ranges لكل def/class
# ═══════════════════════════════════════════════════════════════
def collect_ranges(tree, src_lines):
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            if (name.startswith(PREFIXES)
                    or name in SPECIFIC
                    or "rev" in name.lower()
                    or "lad" in name.lower()):
                start = node.lineno - 1
                end = getattr(node, "end_lineno", start + 1)
                ranges.append((start, end, name, type(node).__name__))
    ranges.sort()
    return ranges


# ═══════════════════════════════════════════════════════════════
# 3) استخراج حقول Config (كلها أو المهمة)
# ═══════════════════════════════════════════════════════════════
def extract_config_fields(src_lines, tree):
    """يستخرج كامل class Config."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Config":
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 1)
            return "\n".join(src_lines[start:end])
    return ""


# ═══════════════════════════════════════════════════════════════
# 4) استخراج CLI flags (argparse section)
# ═══════════════════════════════════════════════════════════════
def extract_cli_flags(src_lines):
    """يجمع كل p.add_argument من السطر الذي يبدأ فيه argparse."""
    lines = []
    in_argparse = False
    for i, line in enumerate(src_lines):
        if "p.add_argument" in line or "ap.add_argument" in line:
            in_argparse = True
        if in_argparse:
            # نجمع أيضاً الأسطر التالية (multi-line args)
            lines.append(f"{i+1:6d}: {line.rstrip()}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 5) البحث عن أنماط معينة (regex) في الملف كاملاً
# ═══════════════════════════════════════════════════════════════
REGEX_PATTERNS = {
    "REV_SUBBAR_ONLY": r"REV_SUBBAR_ONLY",
    "REV_LADDER_ENABLED": r"REV_LADDER_ENABLED",
    "REVERSAL_CONFIRM_ENABLED": r"REVERSAL_CONFIRM_ENABLED",
    "APEX_ENABLED": r"APEX_ENABLED",
    "check_thermodynamic_apex": r"check_thermodynamic_apex\(",
    "_bar_confirms_bounce": r"_bar_confirms_bounce\(",
    "_lad_levels": r"_lad_levels\(",
    "_lad_place": r"_lad_place\(",
    "marketable": r"marketable",
    "GTX": r"['\"]GTX['\"]",
}


def grep_regex(src_lines, pattern):
    hits = []
    rx = re.compile(pattern)
    for i, line in enumerate(src_lines):
        if rx.search(line):
            hits.append(f"{i+1:6d}: {line.rstrip()}")
    return hits


# ═══════════════════════════════════════════════════════════════
# 6) بناء التقرير
# ═══════════════════════════════════════════════════════════════
def build_report(src_path: Path) -> str:
    src = src_path.read_text(encoding="utf-8")
    src_lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return f"# ERROR: syntax error in {src_path}\n\n{e}"

    out = []
    out.append(f"# 🔍 Code Review Extract — {src_path.name}")
    out.append(f"**Total lines:** {len(src_lines):,}")
    out.append(f"**File size:** {src_path.stat().st_size:,} bytes")
    out.append("")

    # ── Section 1: Config class ──
    out.append("## 1️⃣ `class Config` — كامل")
    out.append("")
    cfg = extract_config_fields(src_lines, tree)
    out.append("```python")
    out.append(cfg)
    out.append("```")
    out.append("")

    # ── Section 2: جميع دالات reversal / ladder / apex ──
    out.append("## 2️⃣ دالات Reversal / Ladder / APEX")
    out.append("")
    ranges = collect_ranges(tree, src_lines)

    # tree-grouping: نجمع الدوال المتقاربة (أسطر بينها < 3)
    groups = []
    cur = []
    for r in ranges:
        if cur and r[0] - cur[-1][1] <= 2:
            cur.append(r)
        else:
            if cur:
                groups.append(cur)
            cur = [r]
    if cur:
        groups.append(cur)

    for g in groups:
        g_start = g[0][0]
        g_end = g[-1][1]
        names = ", ".join(r[2] for r in g)
        out.append(f"### 📌 Lines {g_start+1}–{g_end} — {names}")
        out.append("")
        out.append("```python")
        out.append("\n".join(src_lines[g_start:g_end]))
        out.append("```")
        out.append("")

    # ── Section 3: CLI argparse ──
    out.append("## 3️⃣ CLI Flags (argparse)")
    out.append("")
    cli = extract_cli_flags(src_lines)
    out.append("```python")
    out.append(cli if cli else "(no argparse found)")
    out.append("```")
    out.append("")

    # ── Section 4: Wiring in main() ──
    out.append("## 4️⃣ Wiring in main()")
    out.append("")
    for i, node in enumerate(ast.walk(tree)):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            start = node.lineno - 1
            end = getattr(node, "end_lineno", start + 1)
            body = src_lines[start:end]
            # ابحث عن أقسام REV/LADDER/APEX wiring
            in_section = False
            section_lines = []
            for j, line in enumerate(body):
                if any(k in line for k in [
                    "REV_LADDER", "REV_SUBBAR", "REVERSAL_CONFIRM",
                    "APEX", "rev_ladder", "reversal",
                ]):
                    in_section = True
                if in_section:
                    section_lines.append(f"{start+j+1:6d}: {line.rstrip()}")
                    # اخرج عند نهاية الكتلة (سطرين فارغين)
                    if len(section_lines) > 1 and line.strip() == "" and \
                       section_lines[-2].strip().endswith(""):
                        # اتركه يستمر لسطرين فقط
                        pass
            out.append("```python")
            out.append("\n".join(section_lines) if section_lines else "(no wiring found)")
            out.append("```")
            break
    out.append("")

    # ── Section 5: grep-regex hits ──
    out.append("## 5️⃣ مؤشرات مهمة (grep)")
    out.append("")
    for name, pattern in REGEX_PATTERNS.items():
        hits = grep_regex(src_lines, pattern)
        out.append(f"### `{name}` — {len(hits)} نتيجة")
        out.append("")
        if hits:
            out.append("```")
            out.append("\n".join(hits[:60]))   # cap at 60 lines
            if len(hits) > 60:
                out.append(f"... +{len(hits)-60} أكثر")
            out.append("```")
        out.append("")

    # ── Section 6: ملخص ──
    out.append("## 6️⃣ ملخص الإحصاءات")
    out.append("")
    out.append(f"- **حجم الملف**: {len(src_lines):,} سطر")
    out.append(f"- **عدد الدالات/الفئات المتعلقة**: {len(ranges)}")
    out.append(f"- **عدد أقسام Config**: "
               f"{len(re.findall(r'^    [A-Z_]+:', src, flags=re.M))}")
    out.append("")

    return "\n".join(out)


# ═══════════════════════════════════════════════════════════════
# 7) main
# ═══════════════════════════════════════════════════════════════
def main():
    src_path = Path(sys.argv[1] if len(sys.argv) > 1 else SRC)
    if not src_path.exists():
        print(f"✗ {src_path} not found", file=sys.stderr)
        sys.exit(1)

    report = build_report(src_path)
    Path(OUT).write_text(report, encoding="utf-8")
    size = Path(OUT).stat().st_size
    print(f"✓ written → {OUT} ({size:,} bytes, ~{size//4:,} tokens تقريباً)")
    print()
    print("📤 أرسل لي محتوى الملف بالكامل وستتمكن من رؤية كل شيء.")


if __name__ == "__main__":
    main()
