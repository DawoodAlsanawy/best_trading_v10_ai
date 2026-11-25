#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patch script #2 for trading_published_pro_1h_fixed.py

Fixes remaining arbitrary-exit bugs in run_live:
  1. Closed-bar exits (BEEsc, Apex, Topo-Div) must ONLY evaluate bars
     that opened strictly AFTER entry_ts (prevents firing on pre-entry
     bars right after opening a position).
  2. BEEsc in live also verifies live `price` is still in the loss zone
     (prevents stale closed-bar close from closing an already-recovered trade)
     and respects `_signal_sl_above_beesc`.
  3. Removes the duplicate Topo-Div block in run_live.
  4. Enforces CFG.TRAIL_MIN_STEP in run_live trailing (parity with backtest)
     and avoids sending an already-crossed SL to Binance protective sync.
"""

import argparse
import os
import py_compile
import shutil
import sys
from datetime import datetime

PATCH_MARKER = "# [LIVE-EXITS-PARITY-FIX-APPLIED]"


def apply_patch(target_path: str, dry_run: bool = False) -> None:
    if not os.path.exists(target_path):
        print(f"[ERROR] Target file not found: {target_path}", file=sys.stderr)
        sys.exit(1)

    with open(target_path, "r", encoding="utf-8") as f:
        src = f.read()

    if PATCH_MARKER in src:
        print(f"[OK] Patch already applied ({PATCH_MARKER} found). Nothing to do.")
        return

    replacements = [
        (
            "patch marker 2",
            "# [LIVE-TRAIL-PROT-FIX-APPLIED]",
            "# [LIVE-TRAIL-PROT-FIX-APPLIED]\n" + PATCH_MARKER,
        ),
        (
            "BEEsc post-entry bar + live loss-zone guard",
            '''                # ══ [BREAKEVEN ESCAPE — Price Trigger — Live] ══
                if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                        and not pos.get('_be_esc_done', False)
                        and float(pos.get('sl_dist_initial', 0)) > 0):
                    _sl_d0_be = float(pos['sl_dist_initial'])
                    _ci_now_be = (max(0, len(ad.closes) - 2)
                                  if ad is not None else 0)
                    # [PARITY] use last CLOSED bar close to match backtest.
                    # Ticker would trigger BEEsc more often than backtest.
                    _be_price = (float(ad.closes[_ci_now_be])
                                 if ad is not None
                                 and 0 <= _ci_now_be < len(ad.closes)
                                 else float(price))
                    _be_trig, _be_rsn = _should_breakeven_escape(
                        ad, _ci_now_be, _be_price,
                        pos['action'], float(pos['entry']),
                        _sl_d0_be, sig_opp=None,
                        pos=pos,   # ← يُمكّن MFE-guard من _hi/_lo
                    )''',
            '''                # Helper: closed bar opened strictly after position entry_ts
                _bar_post_entry = False
                if ad is not None and entry_ts > 0 and 0 <= (len(ad.closes) - 2) < len(ad.timestamps):
                    try:
                        _bts = pd.Timestamp(ad.timestamps[len(ad.closes) - 2])
                        if _bts.tz is None:
                            _bts = _bts.tz_localize('UTC')
                        _bar_post_entry = (float(_bts.timestamp()) > float(entry_ts))
                    except Exception:
                        _bar_post_entry = False

                # ══ [BREAKEVEN ESCAPE — Price Trigger — Live] ══
                _be_live_in_loss = (
                    (pos['action'] == 'BUY' and float(price) < float(pos['entry']))
                    or (pos['action'] == 'SELL' and float(price) > float(pos['entry']))
                )
                if (getattr(CFG, 'BREAKEVEN_ESCAPE_ENABLED', False)
                        and _bar_post_entry
                        and _be_live_in_loss
                        and not pos.get('_be_esc_done', False)
                        and not pos.get('_signal_sl_above_beesc', False)
                        and float(pos.get('sl_dist_initial', 0)) > 0):
                    _sl_d0_be = float(pos['sl_dist_initial'])
                    _ci_now_be = max(0, len(ad.closes) - 2)
                    # [PARITY] use last CLOSED bar close to match backtest.
                    # Ticker would trigger BEEsc more often than backtest.
                    _be_price = float(ad.closes[_ci_now_be])
                    _be_trig, _be_rsn = _should_breakeven_escape(
                        ad, _ci_now_be, _be_price,
                        pos['action'], float(pos['entry']),
                        _sl_d0_be, sig_opp=None,
                        pos=pos,   # ← يُمكّن MFE-guard من _hi/_lo
                    )''',
        ),
        (
            "Apex & Topo-Div post-entry bar guard + deduplicate Topo-Div",
            '''                # ── Physics-based exits (require ad) ──
                # [APEX-PARITY] Physics checks use the CLOSED bar's price
                # to match the backtest exactly. SL/TP/Liq still use the
                # live ticker (price) — only Apex/TopoDiv need parity.
                if ad is not None:
                    _apex_ci = fi + ad.feat_start
                    _apex_price = (float(ad.closes[_apex_ci])
                                   if 0 <= _apex_ci < len(ad.closes)
                                   else float(price))
                    # Apex
                    is_apex, apex_rsn = False, ""
                    if getattr(CFG, 'APEX_ENABLED', True):
                        is_apex, apex_rsn = check_thermodynamic_apex(
                            pos['action'], pos['entry'], _apex_price, ad, fi
                        )
                    if is_apex:
                        ex = True; rsn = apex_rsn

                    # Topo-Div
                    if not ex and fi > 0:
                        div_t = (ad.V[fi] - ad.V[fi-1]) / (ad.V[fi-1] + 1e-12)
                        if div_t > cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0:
                            ex = True; rsn = f"Topo-Div({div_t:.3f})"

                # ── Topo-Div ──
                if not ex and ad is not None and fi > 0:
                    div_t = (ad.V[fi] - ad.V[fi-1]) / (ad.V[fi-1] + 1e-12)
                    if div_t > cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0:
                        ex = True; rsn = f"Topo-Div({div_t:.3f})"''',
            '''                # ── Physics-based exits (require ad & strictly post-entry closed bar) ──
                # [APEX-PARITY] Physics checks use the CLOSED bar's price
                # to match the backtest exactly. SL/TP/Liq still use the
                # live ticker (price) — only Apex/TopoDiv need parity.
                if ad is not None and _bar_post_entry:
                    _apex_ci = fi + ad.feat_start
                    _apex_price = (float(ad.closes[_apex_ci])
                                   if 0 <= _apex_ci < len(ad.closes)
                                   else float(price))
                    # Apex
                    is_apex, apex_rsn = False, ""
                    if getattr(CFG, 'APEX_ENABLED', True):
                        is_apex, apex_rsn = check_thermodynamic_apex(
                            pos['action'], pos['entry'], _apex_price, ad, fi
                        )
                    if is_apex:
                        ex = True; rsn = apex_rsn

                    # Topo-Div (single check, post-entry bar only)
                    if not ex and fi > 0:
                        div_t = (ad.V[fi] - ad.V[fi-1]) / (ad.V[fi-1] + 1e-12)
                        if div_t > cfg.TOPO_DIV_THRESHOLD and ad.dH[fi] > 0:
                            ex = True; rsn = f"Topo-Div({div_t:.3f})"''',
        ),
        (
            "Trailing SL min-step + safe protective sync guard",
            '''                        if _mfe >= _ta:
                            if pos['action'] == "BUY":
                                new_sl = cur_peak * (1.0 - _td)
                                if new_sl > pos['sl']:
                                    pos['sl'] = new_sl
                            else:
                                new_sl = cur_peak * (1.0 + _td)
                                if new_sl < pos['sl']:
                                    pos['sl'] = new_sl
                        
                        if (getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True)
                                and abs(float(pos['sl']) - _sl_before) > 1e-12):
                            try:
                                _sync_protective_orders(exchange, sym, pos)
                            except Exception as _e:
                                log.debug(f"[Prot] {sym} sync error: {_e}")''',
            '''                        if _mfe >= _ta:
                            if pos['action'] == "BUY":
                                new_sl = cur_peak * (1.0 - _td)
                                if new_sl > pos['sl'] * (1.0 + CFG.TRAIL_MIN_STEP):
                                    pos['sl'] = new_sl
                            else:
                                new_sl = cur_peak * (1.0 + _td)
                                if new_sl < pos['sl'] * (1.0 - CFG.TRAIL_MIN_STEP):
                                    pos['sl'] = new_sl

                        _sl_valid_for_exch = (
                            (pos['action'] == "BUY" and float(pos['sl']) < float(price))
                            or (pos['action'] == "SELL" and float(pos['sl']) > float(price))
                        )
                        if (getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True)
                                and _sl_valid_for_exch
                                and abs(float(pos['sl']) - _sl_before) > 1e-12):
                            try:
                                _sync_protective_orders(exchange, sym, pos)
                            except Exception as _e:
                                log.debug(f"[Prot] {sym} sync error: {_e}")''',
        ),
    ]

    for name, old, _ in replacements:
        cnt = src.count(old)
        if cnt != 1:
            print(
                f"[ERROR] Hunk '{name}' matched {cnt} times (expected 1). Aborting.",
                file=sys.stderr,
            )
            sys.exit(2)

    patched = src
    for name, old, new in replacements:
        patched = patched.replace(old, new, 1)
        print(f"[PATCH] Applied: {name}")

    if dry_run:
        print("[DRY-RUN] All hunks matched cleanly. No files were modified.")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{target_path}.bak_{ts}"
    shutil.copy2(target_path, backup_path)
    print(f"[BACKUP] Created: {backup_path}")

    tmp_path = f"{target_path}.patched.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(patched)
        py_compile.compile(tmp_path, doraise=True)
        os.replace(tmp_path, target_path)
        print(f"[SUCCESS] Patched & syntax-verified: {target_path}")
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        print(f"[ERROR] Verification failed, original file untouched: {e}", file=sys.stderr)
        sys.exit(3)


def main():
    parser = argparse.ArgumentParser(description="Patch remaining live arbitrary-exit parity bugs")
    parser.add_argument("--target", default="trading_published_pro_1h_fixed.py", help="Path to target script")
    parser.add_argument("--dry-run", action="store_true", help="Verify matches without modifying file")
    args = parser.parse_args()
    apply_patch(args.target, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
