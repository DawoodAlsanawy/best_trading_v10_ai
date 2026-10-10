# ملف fix_v2_retention.py
import re
from pathlib import Path

FILE = "trading_rnd_v2_priority.py"

OLD_BLOCK = '''        # Try to open — highest score
        _max_iter = 500
        _it = 0
        while (pending
               and len(open_pos) < CFG.MAX_CONCURRENT_ASSETS
               and _it < _max_iter):
            _it += 1
            best_idx = -1
            best_score = -float('inf')
            for idx, item in enumerate(pending):
                if item[1].score > best_score:
                    best_score = item[1].score
                    best_idx = idx
            if best_idx < 0:
                break
            item = pending.pop(best_idx)
            sig_i, sig = item
            ad_sig = assets.get(sig.symbol)
            if ad_sig is None:
                continue
            cur_ci = _ts_to_ci(ad_sig, ts)
            _try_open(sig, sig_i, cur_ci)'''

NEW_BLOCK = '''        # Try to open — highest score
        # [RETENTION-FIX] احتفظ بالإشارات الفاشلة في pending
        # بدل pop فوري. فقط عند النجاح أو الفشل الدائم.
        _max_iter = 500
        _it = 0
        _tried_this_ts = set()  # indices tried at this timestamp
        while (pending
               and len(open_pos) < CFG.MAX_CONCURRENT_ASSETS
               and _it < _max_iter):
            _it += 1
            # Pick highest score not yet tried at this ts
            best_idx = -1
            best_score = -float('inf')
            for idx, item in enumerate(pending):
                if idx in _tried_this_ts:
                    continue
                if item[1].score > best_score:
                    best_score = item[1].score
                    best_idx = idx
            if best_idx < 0:
                break
            _tried_this_ts.add(best_idx)
            item = pending[best_idx]  # DON'T pop yet
            sig_i, sig = item
            ad_sig = assets.get(sig.symbol)
            if ad_sig is None:
                pending.pop(best_idx)
                continue
            cur_ci = _ts_to_ci(ad_sig, ts)
            ok = _try_open(sig, sig_i, cur_ci)
            if ok:
                pending.pop(best_idx)
                _tried_this_ts = set()  # reset since indices shifted'''


def main():
    p = Path(FILE)
    if not p.exists():
        print(f"ERR: {FILE} not found")
        return 1
    text = p.read_text(encoding="utf-8")
    if "[RETENTION-FIX]" in text:
        print("SKIP: already applied")
        return 0
    if OLD_BLOCK not in text:
        print("ERR: anchor block not found")
        # Print nearby text for debugging
        idx = text.find("Try to open — highest score")
        if idx > 0:
            print("Found 'Try to open' at position:", idx)
            print("Context:", repr(text[idx-50:idx+600]))
        return 2
    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    import ast
    try:
        ast.parse(text)
    except SyntaxError as e:
        print(f"ERR syntax: {e}")
        return 3
    p.write_text(text, encoding="utf-8")
    print("OK: Retention fix applied")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
