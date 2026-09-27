
import json
d = json.load(open('live_state_testnet.json'))
for s, p in d.items():
    entry = p['entry']; sl = p['sl']; liq = p.get('liq_price_estimated')
    side = p['action']
    if liq:
        sl_gap = abs(entry - sl)
        liq_gap = abs(entry - liq)
        ratio = sl_gap / liq_gap if liq_gap > 0 else 999
        ok = ratio < 0.7
        print(f'{s}: entry={entry:.4f} sl={sl:.4f} liq={liq:.4f} '
              f'ratio={ratio:.2f} {"OK" if ok else "BAD"}')

