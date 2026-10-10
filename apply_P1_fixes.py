#!/usr/bin/env python3
"""
apply_P1_fixes.py — Surgical patches for trading_2.py

Applies 5 unique exact-string patches:
    P1.1            — fix double-count of partial_pnl in capital
    P1.1-L.a(sig)   — extend _trade_log_from_backtest signature
    P1.1-L.a(body)  — correct net/lr computation, define _cap_delta
    P1.1-L.a(rec)   — add cap_delta_since_entry + partial_pnl keys
    P1.1-L.b(call)  — pass net_pnl / log_return to logger
    N6-FIX          — advance positions before EndOfData close

Exits non-zero (without writing DST) if any target is missing or ambiguous.
Idempotent: a re-run on an already-patched file reports "already applied".
"""
import os
import sys

SRC = "trading_2.py"
DST = "trading_2_clean.py"


PATCHES = [
    # ── P1.1 ────────────────────────────────────────────────
    (
        "P1.1",
        "        # Include any accumulated partial-TP profit in the final trade PnL\n"
        "        net  = gross - fee - funding_cost + float(getattr(pos, 'partial_pnl', 0.0))\n"
        "        cap0 = pos.entry_cap\n"
        "        capital = max(capital+net, 0.)\n",
        "        # [P1.1] partial_pnl already booked into capital in _partial_tp\n"
        "        # \u2192 exclude it from the capital delta\n"
        "        _partial = float(getattr(pos, 'partial_pnl', 0.0))\n"
        "        net = gross - fee - funding_cost + _partial   # trade-level PnL (unchanged)\n"
        "        cap0 = pos.entry_cap\n"
        "        capital = max(capital + (net - _partial), 0.)\n",
    ),
    # ── P1.1-L.a — signature ─────────────────────────────────
    (
        "P1.1-L.a(sig)",
        "def _trade_log_from_backtest(pos, ad, exit_px, exit_rsn, exit_ci,\n"
        "                              capital_before, capital_after):\n",
        "def _trade_log_from_backtest(pos, ad, exit_px, exit_rsn, exit_ci,\n"
        "                              capital_before, capital_after,\n"
        "                              net_pnl=None, log_return=None):\n",
    ),
    # ── P1.1-L.a — body ──────────────────────────────────────
    (
        "P1.1-L.a(body)",
        "        sig = pos.signal\n"
        "        net = float(capital_after - capital_before)\n"
        "        lr = float(np.log(capital_after / capital_before)) \\\n"
        "            if capital_before > 0 else 0.0\n",
        "        sig = pos.signal\n"
        "        # [P1.1-L] trade-level PnL when supplied by _close; capital-delta\n"
        "        # is polluted by concurrent trades (see N4)\n"
        "        _cap_delta = float(capital_after - capital_before)\n"
        "        net = float(net_pnl) if net_pnl is not None else _cap_delta\n"
        "        if log_return is not None:\n"
        "            lr = float(log_return)\n"
        "        else:\n"
        "            lr = float(np.log(capital_after / capital_before)) \\\n"
        "                if capital_before > 0 else 0.0\n",
    ),
    # ── P1.1-L.a — record keys (+ LOG.partial) ───────────────
    (
        "P1.1-L.a(rec) + LOG.partial",
        "            'pos_size': float(pos.pos_size),\n"
        "            'net_pnl': net,\n"
        "            'log_return': lr,\n"
        "            'capital_before': float(capital_before),\n",
        "            'pos_size': float(pos.pos_size),\n"
        "            'net_pnl': net,\n"
        "            'log_return': lr,\n"
        "            'cap_delta_since_entry': _cap_delta,\n"
        "            'partial_pnl': float(getattr(pos, 'partial_pnl', 0.0)),\n"
        "            'capital_before': float(capital_before),\n",
    ),
    # ── P1.1-L.b — call site ─────────────────────────────────
    (
        "P1.1-L.b(call)",
        "            _trade_log_from_backtest(\n"
        "                pos, ad, exit_eff, exit_rsn, exit_ci,\n"
        "                pos.entry_cap, capital\n"
        "            )\n",
        "            _trade_log_from_backtest(\n"
        "                pos, ad, exit_eff, exit_rsn, exit_ci,\n"
        "                pos.entry_cap, capital,\n"
        "                net_pnl=net, log_return=lr\n"
        "            )\n",
    ),
    # ── N6-FIX ───────────────────────────────────────────────
    (
        "N6-FIX",
        "    for sym, pos in list(open_pos.items()):\n"
        "        ad = assets[sym]\n"
        "        ep = ad.closes[-1]\n"
        "        _close(pos, ad, ep, \"EndOfData\", len(ad.closes)-1)\n",
        "    for sym, pos in list(open_pos.items()):\n"
        "        ad = assets[sym]\n"
        "        # [N6-FIX] simulate SL/TP/MaxHold on remaining bars before\n"
        "        # closing at the final price. Matches live broker behaviour.\n"
        "        _advance(pos, ad, len(ad.closes) - 1, partial_cb=_partial_tp)\n"
        "        ep = ad.closes[-1]\n"
        "        _close(pos, ad, ep, \"EndOfData\", len(ad.closes)-1)\n",
    ),
]


def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found in cwd.", file=sys.stderr)
        sys.exit(1)

    with open(SRC, encoding="utf-8") as f:
        text = f.read()

    original_text = text
    fail = False

    for change_id, old, new in PATCHES:
        n_old = text.count(old)
        n_new = text.count(new)
        print(f"-- {change_id} --")
        if n_old == 1:
            text = text.replace(old, new, 1)
            print("  status : APPLIED")
            print(f"  old[0] : {old.splitlines()[0].strip()[:70]}")
            print(f"  new[0] : {new.splitlines()[0].strip()[:70]}")
        elif n_old == 0 and n_new >= 1:
            print(f"  status : ALREADY APPLIED (new present {n_new}x, "
                  f"old 0x)")
            print(f"  new[0] : {new.splitlines()[0].strip()[:70]}")
        elif n_old == 0 and n_new == 0:
            print("  status : NOT FOUND (old=0, new=0)", file=sys.stderr)
            print("  expected old snippet:", file=sys.stderr)
            for ln in old.splitlines():
                print(f"    | {ln}", file=sys.stderr)
            fail = True
        else:
            print(f"  status : AMBIGUOUS (old appears {n_old}x)",
                  file=sys.stderr)
            fail = True
        print()

    if fail:
        print("Aborting: one or more targets not uniquely matched. "
              "No file written.", file=sys.stderr)
        sys.exit(2)

    # Syntax check before writing
    try:
        compile(text, DST, "exec")
    except SyntaxError as e:
        print(f"SYNTAX ERROR after applying patches: {e}", file=sys.stderr)
        sys.exit(3)

    with open(DST, "w", encoding="utf-8") as f:
        f.write(text)

    delta = len(text) - len(original_text)
    print(f"Wrote {DST}  ({len(text):,} chars, delta {delta:+d})")


if __name__ == "__main__":
    main()
