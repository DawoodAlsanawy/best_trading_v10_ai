#!/usr/bin/env python3
"""Fix the unclosed string literal in patch_live2_smart_protection.py"""

from pathlib import Path
import sys

target = Path(sys.argv[1] if len(sys.argv) > 1
              else "patch_live2_smart_protection.py")

if not target.exists():
    print(f"ERROR: {target} not found in current directory")
    sys.exit(1)

content = target.read_text(encoding='utf-8')

# The broken pattern that appears twice in the file:
#   else 'buy\'''
#   else 'buy\''
broken_variants = [
    "'buy\\'''",    # 8 chars: ', b, u, y, \, ', ', '   ← most likely
    "'buy\\''''",   # 9 chars: ', b, u, y, \, ', ', ', '
]
# Correct replacement:
fixed = "'buy'''"

total = 0
for broken in broken_variants:
    n = content.count(broken)
    if n > 0:
        content = content.replace(broken, fixed)
        print(f"  Fixed {n} occurrence(s) of pattern: {broken!r}")
        total += n

if total == 0:
    print("Pattern not found — file may already be fixed.")
    print("Try running: python3 patch_live2_smart_protection.py --dry-run")
    sys.exit(0)

target.write_text(content, encoding='utf-8')
print(f"\nTotal fixes applied: {total}")
print(f"Now try: python3 {target.name} --dry-run")
