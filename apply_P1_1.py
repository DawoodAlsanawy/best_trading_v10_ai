#!/usr/bin/env python3
"""apply_P1_1.py          -> trading_2_clean.py    (P1.1-V + P1.1 + P1.1-L, exact-match edits)
apply_P1_1.py --only-V  -> trading_2_baseline.py (RECON print only, for the baseline run)"""
import sys, os
SRC = "trading_2.py"
ONLY_V = "--only-V" in sys.argv
DST = "trading_2_baseline.py" if ONLY_V else "trading_2_clean.py"
EDITS = [
("P1.1-V reconciliation print",
'''        _close(pos, ad, ep, "EndOfData", len(ad.closes)-1)

    return trades_out, equity
''',
'''        _close(pos, ad, ep, "EndOfData", len(ad.closes)-1)

    # [P1.1-V] read-only reconciliation check (no behavioural change)
    _sum_net = sum(t.net_pnl for t in trades_out)
    _dcap = capital - CFG.INITIAL_CAPITAL
    print(f"[RECON] n_trades={len(trades_out)} sum_net_pnl={_sum_net:.8f} "
          f"final_cap={capital:.8f} delta_cap={_dcap:.8f} "
          f"abs_diff={abs(_sum_net-_dcap):.3e}", flush=True)

    return trades_out, equity
'''),
("P1.1 capital fix in _close",
'''        net  = gross - fee - funding_cost + float(getattr(pos, 'partial_pnl', 0.0))
        cap0 = pos.entry_cap
        capital = max(capital+net, 0.)
''',
'''        # [P1.1] partial already booked into capital in _partial_tp -> exclude from capital delta
        _partial = float(getattr(pos, 'partial_pnl', 0.0))
        net  = gross - fee - funding_cost + _partial      # trade-level PnL (formula unchanged)
        cap0 = pos.entry_cap
        capital = max(capital + (net - _partial), 0.)
'''),
("P1.1-L.1a writer signature",
'''def _trade_log_from_backtest(pos, ad, exit_px, exit_rsn, exit_ci,
                              capital_before, capital_after):
''',
'''def _trade_log_from_backtest(pos, ad, exit_px, exit_rsn, exit_ci,
                              capital_before, capital_after,
                              net_pnl=None, log_return=None):
'''),
("P1.1-L.1b net/lr in writer",
'''        net = float(capital_after - capital_before)
        lr = float(np.log(capital_after / capital_before)) \\
            if capital_before > 0 else 0.0
''',
'''        # [P1.1-L] trade-level PnL when supplied by _close; the capital delta
        # since entry is polluted by concurrent trades (see N4)
        _cap_delta = float(capital_after - capital_before)
        net = float(net_pnl) if net_pnl is not None else _cap_delta
        if log_return is not None:
            lr = float(log_return)
        else:
            lr = float(np.log(capital_after / capital_before)) \\
                if capital_before > 0 else 0.0
'''),
("P1.1-L.1c record field",
'''            'log_return': lr,
            'capital_before': float(capital_before),
''',
'''            'log_return': lr,
            'cap_delta_since_entry': _cap_delta,
            'capital_before': float(capital_before),
'''),
("P1.1-L.2 call site in _close",
'''                pos, ad, exit_eff, exit_rsn, exit_ci,
                pos.entry_cap, capital
            )
''',
'''                pos, ad, exit_eff, exit_rsn, exit_ci,
                pos.entry_cap, capital,
                net_pnl=net, log_return=lr
            )
'''),
]
EDITS = EDITS[:1] if ONLY_V else EDITS

def die(msg): print(f"ERROR: {msg}"); sys.exit(1)
if not os.path.exists(SRC): die(f"{SRC} not found in {os.getcwd()}")
with open(SRC, encoding="utf-8", newline="") as f: src = f.read()
nl = "\r\n" if "\r\n" in src else "\n"
out = src
for name, old, new in EDITS:
    old, new = old.replace("\n", nl), new.replace("\n", nl)
    n = out.count(old)
    if n == 0: die(f"[{name}] target snippet NOT FOUND (file already modified or different version?). Nothing written.")
    if n > 1: die(f"[{name}] target snippet found {n} times (must be unique). Nothing written.")
    out = out.replace(old, new, 1)
    print(f"--- {name}: OK\n  OLD:\n" + "".join("    - " + l + "\n" for l in old.splitlines())
          + "  NEW:\n" + "".join("    + " + l + "\n" for l in new.splitlines()))
try: compile(out, DST, "exec")
except SyntaxError as e: die(f"SyntaxError in result: {e}. Nothing written.")
if os.path.exists(DST):
    with open(DST, encoding="utf-8", newline="") as f:
        if f.read() == out: print(f"{DST} already exists and is identical. Nothing to do."); sys.exit(0)
with open(DST, "w", encoding="utf-8", newline="") as f: f.write(out)
print(f"Wrote {DST}: {len(EDITS)} replacement(s) applied, syntax check passed.")
