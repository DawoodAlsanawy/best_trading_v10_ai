#!/usr/bin/env python3
"""Fix the misplaced `global` declaration in patch_live2_mfal.py."""

from pathlib import Path
import sys

target = Path("patch_live2_mfal.py")
if not target.exists():
    print(f"ERROR: {target} not found")
    sys.exit(1)

content = target.read_text(encoding='utf-8')
print(f"File size: {len(content)} bytes")

# ─── The problematic block in M2_BLOCK ───
broken = """        x0 = np.concatenate([_MFAL_WEIGHTS, [_MFAL_BIAS]])
        res = _scipy_min(_loss, x0, method="L-BFGS-B",
                          options={"maxiter": 100})

        global _MFAL_WEIGHTS, _MFAL_BIAS
        _MFAL_WEIGHTS = 0.8 * _MFAL_WEIGHTS + 0.2 * res.x[:-1]
        _MFAL_BIAS = 0.8 * _MFAL_BIAS + 0.2 * float(res.x[-1])"""

fixed = """        x0 = np.concatenate([_MFAL_WEIGHTS, [_MFAL_BIAS]])
        res = _scipy_min(_loss, x0, method="L-BFGS-B",
                          options={"maxiter": 100})

        _MFAL_WEIGHTS = 0.8 * _MFAL_WEIGHTS + 0.2 * res.x[:-1]
        _MFAL_BIAS = 0.8 * _MFAL_BIAS + 0.2 * float(res.x[-1])"""

n1 = content.count(broken)
if n1 > 0:
    content = content.replace(broken, fixed)
    print(f"  Removed misplaced 'global' line: {n1} occurrence(s)")

# ─── Add 'global' at the TOP of _mfal_retrain ───
broken2 = """def _mfal_retrain():
    if not os.path.exists(_MFAL_HISTORY_PATH):
        return"""

fixed2 = """def _mfal_retrain():
    global _MFAL_WEIGHTS, _MFAL_BIAS
    if not os.path.exists(_MFAL_HISTORY_PATH):
        return"""

n2 = content.count(broken2)
if n2 > 0:
    content = content.replace(broken2, fixed2)
    print(f"  Added 'global' at top of _mfal_retrain: {n2} occurrence(s)")

if n1 == 0 and n2 == 0:
    print("No changes needed -- patcher may already be fixed.")

# Verify syntax
try:
    compile(content, str(target), 'exec')
    print("✓ Syntax OK")
except SyntaxError as e:
    print(f"✗ Syntax error: {e}")
    sys.exit(1)

target.write_text(content, encoding='utf-8')
print(f"Written {len(content)} bytes")
print()
print("Next steps:")
print(f"  1. python3 -m py_compile {target.name}")
print(f"  2. python3 {target.name} --dry-run")
