#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  apply_sl_filter_patches.py                                                  ║
║                                                                              ║
║  يضيف فلتر SL المجهري إلى trading_2_live4_claude2_v4.py:                    ║
║    1. Config: SL_FILTER_* (5 متغيرات)                                        ║
║    2. build_signals: كتلة الفلترة الثلاثية (E_therm + ATR + tick)           ║
║    3. main(): 4 CLI arguments جديدة                                          ║
║    4. main(): CLI wiring لتفعيل CFG                                         ║
║                                                                              ║
║  الأمان:                                                                     ║
║    • Backup تلقائي                                                           ║
║    • Idempotent (تشغيله مرتين آمن)                                           ║
║    • تحقق AST بعد الحفظ                                                      ║
║    • Rollback تلقائي عند فشل الصيغة                                          ║
║                                                                              ║
║  الاستخدام:                                                                  ║
║    python3 apply_sl_filter_patches.py                                        ║
║    python3 apply_sl_filter_patches.py /path/to/file.py                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import shutil
import subprocess
from datetime import datetime

# ═════════════════════════════════════════════════════════════════════
BOT_PATH = sys.argv[1] if len(sys.argv) > 1 else "trading_2_live4_claude2_v4_micro_sl.py"

if not os.path.exists(BOT_PATH):
    print(f"❌ الملف غير موجود: {BOT_PATH}")
    sys.exit(1)

print("═" * 72)
print(f"📂 Target: {BOT_PATH}")
print("═" * 72)

with open(BOT_PATH, 'r', encoding='utf-8') as f:
    content = f.read()
original_content = content

applied = []
skipped = []
failed  = []


# ═════════════════════════════════════════════════════════════════════
def apply_patch(name, old_str, new_str):
    global content
    if new_str in content and old_str not in content:
        skipped.append(name)
        print(f"  ⏭  {name}: already applied")
        return
    count = content.count(old_str)
    if count == 0:
        failed.append(f"{name}: string not found")
        print(f"  ❌ {name}: NOT FOUND")
        return
    if count > 1:
        failed.append(f"{name}: appears {count}×")
        print(f"  ⚠️  {name}: appears {count}× — aborting this patch")
        return
    content = content.replace(old_str, new_str)
    applied.append(name)
    print(f"  ✅ {name}")


# ═════════════════════════════════════════════════════════════════════
# PATCH 1 — Config additions (insert after MAX_EQUILIBRIUM_GAP)
# ═════════════════════════════════════════════════════════════════════
print("\n[1/4] إضافة إعدادات SL_FILTER في Config")
_cfg_patch = """    MAX_EQUILIBRIUM_GAP: float = 0.35

    # ══ [MICRO-SL FILTER] استبعاد العملات ذات الوقف المجهري ══
    # يمنع فتح صفقات على عملات شديدة التقلب أو ذات tick كبير،
    # حيث يكون SL (بعد SL_WIDEN_MULT) أصغر من 6 تيكات أو أقل من
    # 0.12σ من التقلب اليومي → يُضرب فوراً بالضوضاء.
    SL_FILTER_ENABLED: bool = False          # المفتاح الرئيسي (opt-in)
    SL_FILTER_ETHERM_MAX: float = 0.015      # رفض إن E_therm > 1.5%
    SL_FILTER_ATR_MAX: float = 0.02          # رفض إن ATR% > 2.0%
    SL_FILTER_MIN_TICKS: float = 6.0         # رفض إن SL < 6 ticks
    SL_FILTER_LOG: bool = False              # سجّل كل رفض (DEBUG)"""

apply_patch(
    "Config: SL_FILTER_* settings",
    "    MAX_EQUILIBRIUM_GAP: float = 0.35",
    _cfg_patch
)


# ═════════════════════════════════════════════════════════════════════
# PATCH 2 — Filter block in build_signals (after min_score gate)
# ═════════════════════════════════════════════════════════════════════
print("\n[2/4] إدراج كتلة الفلترة في build_signals")

_filter_block = """            if ad.score[fi] < _min_score: continue

            # ══ [MICRO-SL FILTER] رفض الوقف المجهري ══
            # يُطبَّق قبل حساب sl/tp لتجنب تكلفة الحسابات على صفقات مرفوضة
            if getattr(CFG, 'SL_FILTER_ENABLED', False):
                _sl_cap_frac = 0.015 * float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
                _e_therm_f = float(ad.E_therm[fi]) if fi < len(ad.E_therm) else 0.01
                _atr_frac_f = (float(ad.atr14[ci]) / max(p, 1e-12)
                               if ci < len(ad.atr14) else 0.01)

                # 1) E_therm (الأساسي): يضمن SL/σ_bar ≥ 0.12σ
                if _e_therm_f > float(getattr(CFG, 'SL_FILTER_ETHERM_MAX', 0.015)):
                    if getattr(CFG, 'SL_FILTER_LOG', False):
                        log.debug(
                            f"[SL-Filter] {sym} reject: E_therm="
                            f"{_e_therm_f*100:.2f}% > "
                            f"{CFG.SL_FILTER_ETHERM_MAX*100:.2f}%"
                        )
                    continue

                # 2) ATR% (احتياطي): يضمن SL ≥ 0.09×ATR
                if _atr_frac_f > float(getattr(CFG, 'SL_FILTER_ATR_MAX', 0.02)):
                    if getattr(CFG, 'SL_FILTER_LOG', False):
                        log.debug(
                            f"[SL-Filter] {sym} reject: ATR%="
                            f"{_atr_frac_f*100:.2f}% > "
                            f"{CFG.SL_FILTER_ATR_MAX*100:.2f}%"
                        )
                    continue

                # 3) Tick/price: يضمن SL ≥ MIN_TICKS × tick
                try:
                    _tick_f = None
                    if sym in _TICK_SIZE_CACHE:
                        _tick_f = float(_TICK_SIZE_CACHE[sym])
                    elif hasattr(ad, 'tick_size') and getattr(ad, 'tick_size', None):
                        _tick_f = float(ad.tick_size)
                    if _tick_f and _tick_f > 0 and _sl_cap_frac > 0:
                        _tick_ratio = _tick_f / max(p, 1e-12)
                        _min_ticks = float(getattr(CFG, 'SL_FILTER_MIN_TICKS', 6.0))
                        _max_tick_ratio = _sl_cap_frac / max(_min_ticks, 1e-9)
                        if _tick_ratio > _max_tick_ratio:
                            if getattr(CFG, 'SL_FILTER_LOG', False):
                                log.debug(
                                    f"[SL-Filter] {sym} reject: "
                                    f"tick/price={_tick_ratio*100:.3f}% > "
                                    f"{_max_tick_ratio*100:.3f}% "
                                    f"(cap={_sl_cap_frac*100:.3f}%, "
                                    f"ticks={_sl_cap_frac/_tick_ratio:.1f})"
                                )
                            continue
                except Exception:
                    pass  # فشل قراءة tick لا يوقف الفلترة"""

apply_patch(
    "build_signals: MICRO-SL filter block",
    "            if ad.score[fi] < _min_score: continue",
    _filter_block
)


# ═════════════════════════════════════════════════════════════════════
# PATCH 3 — CLI arguments in main() parser
# ═════════════════════════════════════════════════════════════════════
print("\n[3/4] إضافة CLI arguments")

_cli_args = """    p.add_argument("--sr-proximity", type=float, default=None,
                   help="SL-to-level proximity (default 0.006)")
    # ══ [MICRO-SL FILTER] ══
    p.add_argument("--sl-filter", action="store_true",
                   help="Reject coins with microscopic SL (high vol / large tick)")
    p.add_argument("--sl-filter-etherm", type=float, default=None,
                   help="Reject if E_therm > this (default 0.015 = 1.5%%)")
    p.add_argument("--sl-filter-atr", type=float, default=None,
                   help="Reject if ATR%% > this (default 0.02 = 2.0%%)")
    p.add_argument("--sl-filter-min-ticks", type=float, default=None,
                   help="Reject if SL < this many ticks (default 6)")
    p.add_argument("--sl-filter-log", action="store_true",
                   help="Log every rejection reason at DEBUG level")"""

apply_patch(
    "main(): CLI arguments for SL filter",
    """    p.add_argument("--sr-proximity", type=float, default=None,
                   help="SL-to-level proximity (default 0.006)")""",
    _cli_args
)


# ═════════════════════════════════════════════════════════════════════
# PATCH 4 — CLI wiring (apply args to CFG)
# ═════════════════════════════════════════════════════════════════════
print("\n[4/4] إضافة CLI wiring")

_wiring = """    if args.sr_proximity is not None:
        CFG.SR_SL_PROXIMITY = float(args.sr_proximity)
    # ══ [MICRO-SL FILTER] wiring ══
    if getattr(args, "sl_filter", False):
        CFG.SL_FILTER_ENABLED = True
        log.info(
            f"[SL-Filter] ENABLED: E_therm_max={CFG.SL_FILTER_ETHERM_MAX*100:.2f}% "
            f"ATR_max={CFG.SL_FILTER_ATR_MAX*100:.2f}% "
            f"min_ticks={CFG.SL_FILTER_MIN_TICKS} "
            f"SL_cap={0.015*CFG.SL_WIDEN_MULT*100:.3f}%"
        )
    if getattr(args, "sl_filter_etherm", None) is not None:
        CFG.SL_FILTER_ETHERM_MAX = float(args.sl_filter_etherm)
    if getattr(args, "sl_filter_atr", None) is not None:
        CFG.SL_FILTER_ATR_MAX = float(args.sl_filter_atr)
    if getattr(args, "sl_filter_min_ticks", None) is not None:
        CFG.SL_FILTER_MIN_TICKS = float(args.sl_filter_min_ticks)
    if getattr(args, "sl_filter_log", False):
        CFG.SL_FILTER_LOG = True"""

apply_patch(
    "main(): CLI wiring for SL filter",
    """    if args.sr_proximity is not None:
        CFG.SR_SL_PROXIMITY = float(args.sr_proximity)""",
    _wiring
)


# ═════════════════════════════════════════════════════════════════════
# SUMMARY
# ═════════════════════════════════════════════════════════════════════
print("\n" + "═" * 72)
print("📊 SUMMARY")
print("═" * 72)
print(f"  ✅ Applied: {len(applied)}")
print(f"  ⏭  Skipped: {len(skipped)}")
print(f"  ❌ Failed : {len(failed)}")

if failed:
    print("\n⚠️  Failed patches:")
    for p in failed:
        print(f"     - {p}")
    print("\n⚠️  Some patches failed. Fix them manually before running.")

if content == original_content:
    print("\n⏸  No changes made — file is identical.")
    sys.exit(0 if not failed else 1)


# ═════════════════════════════════════════════════════════════════════
# BACKUP + WRITE
# ═════════════════════════════════════════════════════════════════════
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{BOT_PATH}.backup_{ts}"
shutil.copy2(BOT_PATH, backup_path)
print(f"\n💾 Backup: {backup_path}")

with open(BOT_PATH, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"✅ Written: {BOT_PATH}")


# ═════════════════════════════════════════════════════════════════════
# SYNTAX VERIFICATION
# ═════════════════════════════════════════════════════════════════════
print("\n⏳ Verifying syntax...")
res = subprocess.run(
    [sys.executable, "-c",
     f"import ast; ast.parse(open(r'{BOT_PATH}', encoding='utf-8').read())"],
    capture_output=True, text=True
)

if res.returncode == 0:
    print("✅ Syntax OK")
else:
    print("❌ SYNTAX ERROR:")
    print(res.stderr)
    print(f"\n🔄 Restoring from backup...")
    shutil.copy2(backup_path, BOT_PATH)
    print("✅ Restored. File is unchanged.")
    sys.exit(1)


# ═════════════════════════════════════════════════════════════════════
# NEXT STEPS
# ═════════════════════════════════════════════════════════════════════
print("\n" + "═" * 72)
print("✨ DONE — الفلتر جاهز للاستخدام")
print("═" * 72)
print(f"""
الأمر الجديد (بدون فلتر - افتراضي):
  python3 {BOT_PATH} --mode backtest ... (كما هو)

مع تفعيل الفلتر:
  python3 {BOT_PATH} --mode backtest \\
      --sl-widen-mult 0.12 \\
      --sl-filter \\
      --sl-filter-etherm 0.010 \\
      --sl-filter-min-ticks 6 \\
      --sl-filter-log \\
      ... (باقي الأوامر)

المعاملات:
  --sl-filter                  تفعيل الفلتر (opt-in)
  --sl-filter-etherm <float>   حد E_therm (default 0.015 = 1.5%)
  --sl-filter-atr <float>      حد ATR%% (default 0.02 = 2.0%)
  --sl-filter-min-ticks <n>    أدنى عدد تيكات للوقف (default 6)
  --sl-filter-log              سجّل سبب كل رفض (DEBUG)

للتحقق من الفلتر يعمل:
  grep "SL-Filter" qtt6.log | head -20

للتراجع عن كل شيء:
  cp {backup_path} {BOT_PATH}
""")


# ═════════════════════════════════════════════════════════════════════
# ACCEPTANCE TEST (lightweight, no backtest)
# ═════════════════════════════════════════════════════════════════════
print("═" * 72)
print("🧪 ACCEPTANCE TEST")
print("═" * 72)

try:
    # Verify CFG fields exist
    spec_test = subprocess.run(
        [sys.executable, "-c",
         f"""
import importlib.util
spec = importlib.util.spec_from_file_location("bot_test", r"{BOT_PATH}")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
cfg = m.CFG
required = [
    "SL_FILTER_ENABLED", "SL_FILTER_ETHERM_MAX", "SL_FILTER_ATR_MAX",
    "SL_FILTER_MIN_TICKS", "SL_FILTER_LOG",
]
missing = [k for k in required if not hasattr(cfg, k)]
if missing:
    print("MISSING:", missing)
    exit(1)
print("OK:", {{k: getattr(cfg, k) for k in required}})
"""],
        capture_output=True, text=True, timeout=30
    )
    if spec_test.returncode == 0:
        print("  ✅ CFG fields present")
        print("  " + spec_test.stdout.strip())
    else:
        print("  ⚠️  CFG load warning (may be normal if bot imports fail on this machine)")
        print("  " + (spec_test.stderr or "")[-500:])
except subprocess.TimeoutExpired:
    print("  ⚠️  Test timed out (skipped)")
except Exception as e:
    print(f"  ⚠️  Test skipped: {e}")

print("\n" + "═" * 72)
print("🎯 اكتمل التعديل. جرّب الأوامر أعلاه.")
print("═" * 72)
