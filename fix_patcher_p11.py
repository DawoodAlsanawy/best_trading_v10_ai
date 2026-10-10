#!/usr/bin/env python3
"""Fix the P11_INNER_OLD / P11_INNER_NEW constants in the patcher."""

from pathlib import Path
import sys

target = Path("patch_live2_smart_protection.py")
if not target.exists():
    print(f"ERROR: {target} not found")
    sys.exit(1)

content = target.read_text(encoding='utf-8')
print(f"File size: {len(content)} bytes")

# Locate the region: P11_INNER_OLD = ... up to P12_OLD =
start_marker = "P11_INNER_OLD = "
end_marker = "P12_OLD = "

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)

if start_idx < 0 or end_idx < 0:
    print(f"ERROR: markers not found (start={start_idx}, end={end_idx})")
    sys.exit(1)

print(f"Replacing {end_idx - start_idx} chars from offset {start_idx}")

# New clean definitions using triple-double-quote (no escaping needed)
clean_block = '''P11_INNER_OLD = """        if action not in ('BUY', 'SELL') or sl <= 0 or tp <= 0 or qty <= 0:
            return False

        close_side = 'sell' if action == 'BUY' else 'buy'
"""


P11_INNER_NEW = """        if action not in ('BUY', 'SELL') or sl <= 0 or tp <= 0 or qty <= 0:
            return False

        # SMART-CHECK: if the exchange already has matching SL and TP,
        # leave them untouched and return success immediately.
        _ex_has_sl, _ex_has_tp = _lv_check_protective_on_exchange(
            exchange, sym, sl, tp
        )
        if _ex_has_sl and _ex_has_tp:
            log.debug(
                f"[Prot] {sym} SL@{sl:.6f} and TP@{tp:.6f} already "
                f"exist on exchange -- no action"
            )
            return True
        if _ex_has_sl or _ex_has_tp:
            log.info(
                f"[Prot] {sym} partial protection "
                f"(sl_exists={_ex_has_sl}, tp_exists={_ex_has_tp}) -- "
                f"will cancel remaining and re-place both"
            )

        close_side = 'sell' if action == 'BUY' else 'buy'
"""


# ══════════════════════════════════════════════════════════════════════════
# P12 — _lv_adopt accepts state_hint
# ══════════════════════════════════════════════════════════════════════════

'''

new_content = content[:start_idx] + clean_block + content[end_idx:]

# Verify syntax BEFORE writing
try:
    compile(new_content, str(target), 'exec')
    print("✓ Syntax OK")
except SyntaxError as e:
    print(f"✗ Syntax error in new content: {e}")
    print("Aborting — file NOT modified")
    sys.exit(1)

target.write_text(new_content, encoding='utf-8')
print(f"Written {len(new_content)} bytes")
print()
print("Next steps:")
print(f"  1. python3 -m py_compile {target.name}")
print(f"  2. python3 {target.name} --dry-run")
