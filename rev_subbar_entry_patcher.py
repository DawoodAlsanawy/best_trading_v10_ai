#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  REV Sub-Bar Entry — Automated Patcher                                       ║
║  الدخول المبكر عند إغلاق شمعة تأكيد الانعكاس (sub-bar)                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  يطبّق 6 تعديلات ذرية على trading_2_live4_claude2_v4.py:                     ║
║                                                                              ║
║    1. Config fields: REV_SUBBAR_ENTRY_*                                      ║
║    2. _rev_scan: حفظ confirm_close_px عند التأكيد                            ║
║    3. _rev_handle_ready: تعيين entry_mode + target_entry_px                  ║
║    4. _rev_advance_filling: وضع Limit maker عند سعر شمعة التأكيد             ║
║    5. CLI args: --rev-subbar-entry + tuning flags                            ║
║    6. CLI wiring: ربط args بالـ Config                                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  USAGE:                                                                      ║
║    python3 rev_subbar_entry_patcher.py                 # apply              ║
║    python3 rev_subbar_entry_patcher.py --dry-run       # preview            ║
║    python3 rev_subbar_entry_patcher.py --verify-only   # check              ║
║    python3 rev_subbar_entry_patcher.py --rollback      # restore latest     ║
║    python3 rev_subbar_entry_patcher.py --target FILE   # custom target      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  SAFETY:                                                                     ║
║    • Timestamped backup before write                                         ║
║    • ast.parse() syntax validation                                           ║
║    • Idempotent (safe to re-run)                                             ║
║    • Atomic write (tmp → os.replace)                                         ║
║    • Every anchor must match EXACTLY ONCE                                    ║
║    • Auto-rollback on failure                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"
MARKER = "# ═══ [REV-SUBBAR-ENTRY-APPLIED] ═══"


# ═══════════════════════════════════════════════════════════════════════════════
# PATCH DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

PATCHES = [

    # ═══════════════════════════════════════════════════════════════════════
    # P01 — Config fields for Sub-Bar Entry
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P01-config-fields",
        "desc": "Add REV_SUBBAR_ENTRY_* config fields",
        "old": (
            "    REV_REPRICE_S: float = 5.0                # cancel/replace cadence (post-only at best bid/ask)\n"
            "    REV_MAX_CHASE_KAPPA: float = 0.15         # max chase above/below confirm close, in sigma_bar*px\n"
        ),
        "new": (
            "    REV_REPRICE_S: float = 5.0                # cancel/replace cadence (post-only at best bid/ask)\n"
            "    # ══ [SUB-BAR ENTRY] الدخول عند إغلاق شمعة التأكيد ══\n"
            "    # True  → Limit maker عند سعر إغلاق شمعة التأكيد (مطابق للـ backtest)\n"
            "    # False → Marketable limit عند best bid/ask (السلوك الأصلي)\n"
            "    # ملاحظة: الدخول يكون فقط إذا لم يتحرك السعر أكثر من\n"
            "    # REV_SUBBAR_ENTRY_MAX_DRIFT_BPS منذ إغلاق شمعة التأكيد.\n"
            "    REV_SUBBAR_ENTRY_ENABLED: bool = True\n"
            "    REV_SUBBAR_ENTRY_PEN_BPS: float = 2.0          # 0.02% انزلاق نحو السوق\n"
            "    REV_SUBBAR_ENTRY_MAX_DRIFT_BPS: float = 15.0   # 0.15% drift قبل التحول لـ marketable\n"
            "    REV_SUBBAR_ENTRY_MARKETABLE: bool = False      # True → Limit + تقاطع السبريد (taker)\n"
            "    # ══ [SUB-BAR ENTRY end] ══\n"
            "    REV_MAX_CHASE_KAPPA: float = 0.15         # max chase above/below confirm close, in sigma_bar*px\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P02 — _rev_scan: save confirm_close_px at confirmation
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P02-rev-scan-confirm-px",
        "desc": "Store confirm_close_px when bounce is confirmed in _rev_scan",
        "old": (
            "            # 3. التأكيد (Bounce Confirm)\n"
            "            if np.isfinite(c) and _bar_confirms_bounce(w, c):\n"
            "                w[\"status\"] = \"READY_TO_FILL\"\n"
            "                w[\"confirm_k\"] = k\n"
            "                w[\"ref_px\"] = float(c)\n"
            "                w[\"confirm_close_ts\"] = ts + sub_sec\n"
            "                w[\"prev_close\"] = c\n"
            "                w[\"last_scan_ts\"] = ts\n"
            "                log.info(f\"[LiveRev] {sym} BOUNCE confirmed k={k} close={c:.6f}\")\n"
            "                break\n"
        ),
        "new": (
            "            # 3. التأكيد (Bounce Confirm)\n"
            "            if np.isfinite(c) and _bar_confirms_bounce(w, c):\n"
            "                w[\"status\"] = \"READY_TO_FILL\"\n"
            "                w[\"confirm_k\"] = k\n"
            "                w[\"ref_px\"] = float(c)\n"
            "                w[\"confirm_close_ts\"] = ts + sub_sec\n"
            "                w[\"prev_close\"] = c\n"
            "                w[\"last_scan_ts\"] = ts\n"
            "                # ══ [SUB-BAR ENTRY] حفظ سعر إغلاق شمعة التأكيد ══\n"
            "                w[\"confirm_close_px\"] = float(c)\n"
            "                w[\"confirm_bar_close_ts\"] = float(ts + sub_sec)\n"
            "                log.info(f\"[LiveRev] {sym} BOUNCE confirmed k={k} close={c:.6f}\")\n"
            "                break\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P03 — _rev_handle_ready: set entry_mode + target_entry_px
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P03-rev-handle-ready-entry-mode",
        "desc": "Set entry_mode and target_entry_px in _rev_handle_ready",
        "old": (
            "    w[\"qty_eff\"] = qty\n"
            "    w[\"status\"] = \"FILLING\"\n"
            "    w[\"fill_started\"] = now\n"
            "    w[\"fill_deadline\"] = now + float(_revc(\"REV_FILL_MAX_WAIT_S\", 90.0))\n"
            "    w[\"last_reprice\"] = 0.0\n"
            "    log.info(f\"[LiveRev] {sym} FILLING qty={qty:.6f} ref={w['ref_px']:.6f}\")\n"
        ),
        "new": (
            "    w[\"qty_eff\"] = qty\n"
            "    w[\"status\"] = \"FILLING\"\n"
            "    w[\"fill_started\"] = now\n"
            "    w[\"fill_deadline\"] = now + float(_revc(\"REV_FILL_MAX_WAIT_S\", 90.0))\n"
            "    w[\"last_reprice\"] = 0.0\n"
            "    # ══ [SUB-BAR ENTRY] اختيار نمط التنفيذ ══\n"
            "    _subbar_mode = bool(getattr(CFG, 'REV_SUBBAR_ENTRY_ENABLED', True))\n"
            "    _confirm_px = w.get(\"confirm_close_px\")\n"
            "    if _subbar_mode and _confirm_px:\n"
            "        w[\"entry_mode\"] = \"subbar_close\"\n"
            "        w[\"target_entry_px\"] = float(_confirm_px)\n"
            "        log.info(f\"[LiveRev] {sym} FILLING qty={qty:.6f} \"\n"
            "                 f\"entry_mode=subbar_close target={_confirm_px:.6f}\")\n"
            "    else:\n"
            "        w[\"entry_mode\"] = \"marketable\"\n"
            "        log.info(f\"[LiveRev] {sym} FILLING qty={qty:.6f} \"\n"
            "                 f\"entry_mode=marketable ref={w['ref_px']:.6f}\")\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P04 — _rev_advance_filling: sub-bar limit path
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P04-rev-advance-filling-subbar",
        "desc": "Add sub-bar close entry path in _rev_advance_filling",
        "old": (
            "    w[\"attempt\"] = int(w.get(\"attempt\", 0)) + 1\n"
            "    cid = _rev_cid(sym, float(w[\"sig_epoch\"]), int(w[\"attempt\"]))\n"
            "    w[\"cid\"] = cid\n"
            "    w[\"cid_sent\"] = True\n"
            "    \n"
            "    # ════════════════════════════════════════════════════════════════\n"
            "    # [SMART EXECUTION v2] Marketable Limit with Dynamic Slippage Cap\n"
            "    # ════════════════════════════════════════════════════════════════\n"
            "    # حساب المسافة الأصلية للوقف للحفاظ على التناسب\n"
            "    orig_sl_dist = float(w.get(\"orig_sl_dist\", ref_px * 0.015))\n"
            "    \n"
            "    # أقصى انزلاق مسموح هو 15% من مسافة الـ Stop Loss \n"
            "    # (بحيث لا يتشوه الـ Risk:Reward الخاص بك)\n"
            "    max_slip_allowed = orig_sl_dist * 0.15 \n"
            "    \n"
            "    if action == \"BUY\":\n"
            "        # في الشراء: نرسل أمر ليمت أعلى من أفضل سعر بيع (Best Ask) بقليل\n"
            "        marketable_px = px + max_slip_allowed\n"
            "    else:\n"
            "        # في البيع: نرسل أمر ليمت أقل من أفضل سعر شراء (Best Bid) بقليل\n"
            "        marketable_px = px - max_slip_allowed\n"
            "        \n"
            "    # تقريب السعر ليتوافق مع شروط البورصة\n"
            "    marketable_px = _rev_snap_price(exchange, sym, marketable_px, side)\n"
            "    \n"
            "    w[\"order_px\"] = marketable_px\n"
            "    w[\"last_reprice\"] = now\n"
            "    save_reversal_watchers()            # persist BEFORE the order exists\n"
            "    \n"
            "    try:\n"
            "        # إرسال الأمر بدون GTX (ليتمكن من اقتحام السبريد كأمر Market)\n"
            "        # ولكن بحد أقصى للسعر يمنع الانزلاق الكارثي\n"
            "        o = _rev_api(exchange.create_order, sym, \"limit\", side, q, marketable_px,\n"
            "                     params={\"clientOrderId\": cid})\n"
            "        w[\"order_id\"] = str(o.get(\"id\") or \"\")\n"
            "        w[\"cid_sent\"] = False\n"
            "        log.info(f\"[LiveRev-Smart] {sym} Marketable Limit {side} {q} @ {marketable_px:.6f} (Current Ask/Bid: {px:.6f})\")\n"
            "    except Exception as e:\n"
            "        msg = str(e)\n"
            "        if (\"-5022\" in msg or \"Post Only\" in msg or \"post only\" in msg\n"
            "                or \"immediately match\" in msg):\n"
            "            w[\"rejects\"] = int(w.get(\"rejects\", 0)) + 1\n"
            "            _rev_clear_order(w)\n"
            "            log.info(f\"[LiveRev] {sym} GTX rejected (retry): {msg[:120]}\")\n"
            "        elif any(c in msg for c in (\"-2019\", \"-4164\", \"-1111\", \"-4003\",\n"
            "                                    \"-2027\", \"-4028\")):\n"
            "            _rev_clear_order(w)\n"
            "            log.warning(f\"[LiveRev] {sym} order refused: {msg[:160]}\")\n"
            "            _rev_finish(exchange, sym, w, open_pos_live, assets,\n"
            "                        \"order_refused\")\n"
            "        else:\n"
            "            # ambiguous (timeout etc.): keep cid, resolve by lookup next cycle\n"
            "            log.warning(f\"[LiveRev] {sym} create_order ambiguous: {msg[:160]}\")\n"
            "    save_reversal_watchers()\n"
        ),
        "new": (
            "    w[\"attempt\"] = int(w.get(\"attempt\", 0)) + 1\n"
            "    cid = _rev_cid(sym, float(w[\"sig_epoch\"]), int(w[\"attempt\"]))\n"
            "    w[\"cid\"] = cid\n"
            "    w[\"cid_sent\"] = True\n"
            "    \n"
            "    # ════════════════════════════════════════════════════════════════\n"
            "    # [SUB-BAR ENTRY] مسار الدخول عند إغلاق شمعة التأكيد\n"
            "    # ════════════════════════════════════════════════════════════════\n"
            "    _entry_mode = w.get(\"entry_mode\", \"marketable\")\n"
            "    if _entry_mode == \"subbar_close\" and w.get(\"target_entry_px\"):\n"
            "        _subbar_px = float(w[\"target_entry_px\"])\n"
            "        _pen_bps = float(getattr(CFG, 'REV_SUBBAR_ENTRY_PEN_BPS', 2.0))\n"
            "        _pen_frac = _pen_bps * 1e-4\n"
            "        _marketable_override = bool(getattr(CFG, 'REV_SUBBAR_ENTRY_MARKETABLE', False))\n"
            "        _max_drift = float(getattr(CFG, 'REV_SUBBAR_ENTRY_MAX_DRIFT_BPS', 15.0))\n"
            "        \n"
            "        # drift = |best_px - subbar_close| / subbar_close\n"
            "        _drift_bps = abs(px - _subbar_px) / max(_subbar_px, 1e-12) * 1e4\n"
            "        \n"
            "        if _drift_bps > _max_drift:\n"
            "            log.info(f\"[LiveRev-SubBar] {sym} drifted \"\n"
            "                     f\"{_drift_bps:.1f}bps > {_max_drift:.1f}bps \"\n"
            "                     f\"-> falling back to marketable\")\n"
            "            w[\"entry_mode\"] = \"marketable\"\n"
            "        else:\n"
            "            # سعر الأمر: subbar_close ± pen\n"
            "            if action == \"BUY\":\n"
            "                entry_px = _subbar_px * (1.0 + _pen_frac)\n"
            "            else:\n"
            "                entry_px = _subbar_px * (1.0 - _pen_frac)\n"
            "            entry_px = _rev_snap_price(exchange, sym, entry_px, side)\n"
            "            \n"
            "            if _marketable_override:\n"
            "                # Limit crosses the spread (taker)\n"
            "                _ord_params = {\"clientOrderId\": cid}\n"
            "                _ord_desc = \"Marketable-SubBar\"\n"
            "            else:\n"
            "                # Post-Only GTX (maker)\n"
            "                _ord_params = {\"clientOrderId\": cid, \"timeInForce\": \"GTX\"}\n"
            "                _ord_desc = \"PostOnly-SubBar\"\n"
            "            \n"
            "            w[\"order_px\"] = entry_px\n"
            "            w[\"last_reprice\"] = now\n"
            "            save_reversal_watchers()\n"
            "            \n"
            "            try:\n"
            "                o = _rev_api(exchange.create_order, sym, \"limit\",\n"
            "                             side, q, entry_px, params=_ord_params)\n"
            "                w[\"order_id\"] = str(o.get(\"id\") or \"\")\n"
            "                w[\"cid_sent\"] = False\n"
            "                log.info(f\"[LiveRev-SubBar] {sym} {_ord_desc} {side} {q} \"\n"
            "                         f\"@ {entry_px:.6f} \"\n"
            "                         f\"(subbar_close={_subbar_px:.6f}, \"\n"
            "                         f\"drift={_drift_bps:.1f}bps, \"\n"
            "                         f\"best_px={px:.6f})\")\n"
            "                return\n"
            "            except Exception as e:\n"
            "                msg = str(e)\n"
            "                if (\"-5022\" in msg or \"Post Only\" in msg\n"
            "                        or \"post only\" in msg\n"
            "                        or \"immediately match\" in msg):\n"
            "                    log.info(f\"[LiveRev-SubBar] {sym} GTX rejected \"\n"
            "                             f\"(price moved) -> retry marketable: {msg[:100]}\")\n"
            "                    w[\"entry_mode\"] = \"marketable\"\n"
            "                    _rev_clear_order(w)\n"
            "                    save_reversal_watchers()\n"
            "                    return\n"
            "                elif any(c in msg for c in (\"-2019\", \"-4164\", \"-1111\", \"-4003\",\n"
            "                                            \"-2027\", \"-4028\")):\n"
            "                    _rev_clear_order(w)\n"
            "                    log.warning(f\"[LiveRev-SubBar] {sym} order refused: {msg[:160]}\")\n"
            "                    _rev_finish(exchange, sym, w, open_pos_live, assets,\n"
            "                                \"order_refused\")\n"
            "                    save_reversal_watchers()\n"
            "                    return\n"
            "                else:\n"
            "                    log.warning(f\"[LiveRev-SubBar] {sym} ambiguous: {msg[:160]}\")\n"
            "                    save_reversal_watchers()\n"
            "                    return\n"
            "    \n"
            "    # ════════════════════════════════════════════════════════════════\n"
            "    # [SMART EXECUTION v2] Marketable Limit (الأصلي — fallback)\n"
            "    # ════════════════════════════════════════════════════════════════\n"
            "    orig_sl_dist = float(w.get(\"orig_sl_dist\", ref_px * 0.015))\n"
            "    max_slip_allowed = orig_sl_dist * 0.15 \n"
            "    \n"
            "    if action == \"BUY\":\n"
            "        marketable_px = px + max_slip_allowed\n"
            "    else:\n"
            "        marketable_px = px - max_slip_allowed\n"
            "        \n"
            "    marketable_px = _rev_snap_price(exchange, sym, marketable_px, side)\n"
            "    \n"
            "    w[\"order_px\"] = marketable_px\n"
            "    w[\"last_reprice\"] = now\n"
            "    save_reversal_watchers()\n"
            "    \n"
            "    try:\n"
            "        o = _rev_api(exchange.create_order, sym, \"limit\", side, q, marketable_px,\n"
            "                     params={\"clientOrderId\": cid})\n"
            "        w[\"order_id\"] = str(o.get(\"id\") or \"\")\n"
            "        w[\"cid_sent\"] = False\n"
            "        log.info(f\"[LiveRev-Smart] {sym} Marketable Limit {side} {q} @ {marketable_px:.6f} (Current Ask/Bid: {px:.6f})\")\n"
            "    except Exception as e:\n"
            "        msg = str(e)\n"
            "        if (\"-5022\" in msg or \"Post Only\" in msg or \"post only\" in msg\n"
            "                or \"immediately match\" in msg):\n"
            "            w[\"rejects\"] = int(w.get(\"rejects\", 0)) + 1\n"
            "            _rev_clear_order(w)\n"
            "            log.info(f\"[LiveRev] {sym} GTX rejected (retry): {msg[:120]}\")\n"
            "        elif any(c in msg for c in (\"-2019\", \"-4164\", \"-1111\", \"-4003\",\n"
            "                                    \"-2027\", \"-4028\")):\n"
            "            _rev_clear_order(w)\n"
            "            log.warning(f\"[LiveRev] {sym} order refused: {msg[:160]}\")\n"
            "            _rev_finish(exchange, sym, w, open_pos_live, assets,\n"
            "                        \"order_refused\")\n"
            "        else:\n"
            "            log.warning(f\"[LiveRev] {sym} create_order ambiguous: {msg[:160]}\")\n"
            "    save_reversal_watchers()\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P05 — CLI args: --rev-subbar-entry + tuning flags
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P05-cli-args",
        "desc": "Add CLI flags for sub-bar entry",
        "old": (
            "    # ══ [REV-FIX v3] Maker Ladder (Phase 1) ══\n"
            "    p.add_argument(\"--rev-ladder\", action=\"store_true\",\n"
        ),
        "new": (
            "    # ══ [SUB-BAR ENTRY] ══\n"
            "    p.add_argument(\"--rev-subbar-entry\", action=\"store_true\", default=None,\n"
            "                   help=\"[SubBar Entry] الدخول عند إغلاق شمعة التأكيد \"\n"
            "                        \"(Limit maker بدل marketable). مطابق للـ backtest.\")\n"
            "    p.add_argument(\"--no-rev-subbar-entry\", action=\"store_true\",\n"
            "                   help=\"[SubBar Entry] تعطيل الدخول عند إغلاق شمعة التأكيد\")\n"
            "    p.add_argument(\"--rev-subbar-entry-pen-bps\", type=float, default=None,\n"
            "                   help=\"[SubBar Entry] انزلاق نحو السوق (default 2.0 bps)\")\n"
            "    p.add_argument(\"--rev-subbar-entry-max-drift-bps\", type=float, default=None,\n"
            "                   help=\"[SubBar Entry] أقصى drift قبل التحول لـ marketable \"\n"
            "                        \"(default 15.0 bps)\")\n"
            "    p.add_argument(\"--rev-subbar-entry-marketable\", action=\"store_true\",\n"
            "                   help=\"[SubBar Entry] استخدم Limit عند subbar_close مع \"\n"
            "                        \"تقاطع السبريد (taker) بدل Post-Only GTX (maker)\")\n"
            "    # ══ [REV-FIX v3] Maker Ladder (Phase 1) ══\n"
            "    p.add_argument(\"--rev-ladder\", action=\"store_true\",\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P06 — CLI wiring: bind args to Config
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P06-cli-wiring",
        "desc": "Wire CLI flags into CFG",
        "old": (
            "    # ══ [REV-FIX v3] Maker Ladder wiring ══\n"
            "    if getattr(args, \"rev_ladder\", False):\n"
        ),
        "new": (
            "    # ══ [SUB-BAR ENTRY] wiring ══\n"
            "    if getattr(args, \"no_rev_subbar_entry\", False):\n"
            "        CFG.REV_SUBBAR_ENTRY_ENABLED = False\n"
            "        log.info(\"[SubBar-Entry] DISABLED (using marketable)\")\n"
            "    elif getattr(args, \"rev_subbar_entry\", None):\n"
            "        CFG.REV_SUBBAR_ENTRY_ENABLED = True\n"
            "        log.info(\"[SubBar-Entry] ENABLED (limit at confirm bar close)\")\n"
            "    if getattr(args, \"rev_subbar_entry_pen_bps\", None) is not None:\n"
            "        CFG.REV_SUBBAR_ENTRY_PEN_BPS = float(args.rev_subbar_entry_pen_bps)\n"
            "    if getattr(args, \"rev_subbar_entry_max_drift_bps\", None) is not None:\n"
            "        CFG.REV_SUBBAR_ENTRY_MAX_DRIFT_BPS = float(\n"
            "            args.rev_subbar_entry_max_drift_bps\n"
            "        )\n"
            "    if getattr(args, \"rev_subbar_entry_marketable\", False):\n"
            "        CFG.REV_SUBBAR_ENTRY_MARKETABLE = True\n"
            "    if CFG.REV_SUBBAR_ENTRY_ENABLED:\n"
            "        _mkt = 'marketable (taker)' if CFG.REV_SUBBAR_ENTRY_MARKETABLE else 'Post-Only (maker)'\n"
            "        log.info(f\"[SubBar-Entry] pen={CFG.REV_SUBBAR_ENTRY_PEN_BPS:.1f}bps \"\n"
            "                 f\"max_drift={CFG.REV_SUBBAR_ENTRY_MAX_DRIFT_BPS:.1f}bps \"\n"
            "                 f\"mode={_mkt}\")\n"
            "    # ══ [REV-FIX v3] Maker Ladder wiring ══\n"
            "    if getattr(args, \"rev_ladder\", False):\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P07 — Strict mode config flag
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P07-strict-config",
        "desc": "Add REV_SUBBAR_ENTRY_STRICT config field",
        "old": (
            "    REV_SUBBAR_ENTRY_MARKETABLE: bool = False      # True → Limit + تقاطع السبريد (taker)\n"
            "    # ══ [SUB-BAR ENTRY end] ══\n"
        ),
        "new": (
            "    REV_SUBBAR_ENTRY_MARKETABLE: bool = False      # True → Limit + تقاطع السبريد (taker)\n"
            "    # ══ [SUB-BAR STRICT] Post-Only only + no reprice + no marketable fallback ══\n"
            "    # True → الأمر لا يُلغى/يُعاد، ولا يُحوَّل لـ marketable أبداً.\n"
            "    # إذا رُفض GTX بسبب تحرك السعر → يُعاد المحاولة بنفس السعر\n"
            "    # حتى REV_MAX_REJECTS ثم ينتهي الأمر (بدون دخول).\n"
            "    REV_SUBBAR_ENTRY_STRICT: bool = False\n"
            "    # ══ [SUB-BAR ENTRY end] ══\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P08 — Skip reprice entirely in strict mode
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P08-skip-reprice-strict",
        "desc": "In strict mode, never reprice the existing order",
        "old": (
            "        else:\n"
            "            if now >= float(w[\"fill_deadline\"]) or w.get(\"cancel_req\"):\n"
            "                if not _rev_cancel_and_confirm(exchange, sym, w):\n"
            "                    return\n"
            "            elif now - float(w.get(\"last_reprice\", 0.0)) >= float(\n"
            "                    _revc(\"REV_REPRICE_S\", 5.0)):\n"
            "                w[\"last_reprice\"] = now\n"
            "                try:\n"
            "                    px = _rev_best_px(exchange, sym, action)\n"
            "                except Exception as e:\n"
            "                    log.debug(f\"[LiveRev] {sym} book error: {e}\")\n"
            "                    return\n"
            "                if px is None:\n"
            "                    return\n"
        ),
        "new": (
            "        else:\n"
            "            # ══ [SUB-BAR STRICT] in strict mode, NEVER reprice ══\n"
            "            _is_strict = (w.get(\"entry_mode\") == \"subbar_close\"\n"
            "                          and bool(getattr(CFG, 'REV_SUBBAR_ENTRY_STRICT', False)))\n"
            "            if now >= float(w[\"fill_deadline\"]) or w.get(\"cancel_req\"):\n"
            "                if not _rev_cancel_and_confirm(exchange, sym, w):\n"
            "                    return\n"
            "            elif _is_strict:\n"
            "                # Order stays put until deadline\n"
            "                return\n"
            "            elif now - float(w.get(\"last_reprice\", 0.0)) >= float(\n"
            "                    _revc(\"REV_REPRICE_S\", 5.0)):\n"
            "                w[\"last_reprice\"] = now\n"
            "                try:\n"
            "                    px = _rev_best_px(exchange, sym, action)\n"
            "                except Exception as e:\n"
            "                    log.debug(f\"[LiveRev] {sym} book error: {e}\")\n"
            "                    return\n"
            "                if px is None:\n"
            "                    return\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P09 — GTX rejection in strict mode: retry at same price, no marketable
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P09-gtx-reject-strict",
        "desc": "In strict mode, GTX rejection → retry at same price (never marketable)",
        "old": (
            "                if (\"-5022\" in msg or \"Post Only\" in msg\n"
            "                        or \"post only\" in msg\n"
            "                        or \"immediately match\" in msg):\n"
            "                    log.info(f\"[LiveRev-SubBar] {sym} GTX rejected \"\n"
            "                             f\"(price moved) -> retry marketable: {msg[:100]}\")\n"
            "                    w[\"entry_mode\"] = \"marketable\"\n"
            "                    _rev_clear_order(w)\n"
            "                    save_reversal_watchers()\n"
            "                    return\n"
        ),
        "new": (
            "                if (\"-5022\" in msg or \"Post Only\" in msg\n"
            "                        or \"post only\" in msg\n"
            "                        or \"immediately match\" in msg):\n"
            "                    _is_strict_rej = bool(getattr(CFG, 'REV_SUBBAR_ENTRY_STRICT', False))\n"
            "                    if _is_strict_rej:\n"
            "                        w[\"rejects\"] = int(w.get(\"rejects\", 0)) + 1\n"
            "                        _max_r = int(_revc(\"REV_MAX_REJECTS\", 30))\n"
            "                        if w[\"rejects\"] >= _max_r:\n"
            "                            log.warning(\n"
            "                                f\"[LiveRev-SubBar] {sym} GTX rejected \"\n"
            "                                f\"{w['rejects']}× → expire (strict mode, no marketable)\"\n"
            "                            )\n"
            "                            _rev_finish(exchange, sym, w, open_pos_live,\n"
            "                                        assets, \"gtx_rejected_strict\")\n"
            "                        else:\n"
            "                            log.info(\n"
            "                                f\"[LiveRev-SubBar] {sym} GTX rejected \"\n"
            "                                f\"(#{w['rejects']}/{_max_r}) → retry at same price\"\n"
            "                            )\n"
            "                            _rev_clear_order(w)\n"
            "                        save_reversal_watchers()\n"
            "                        return\n"
            "                    else:\n"
            "                        log.info(f\"[LiveRev-SubBar] {sym} GTX rejected \"\n"
            "                                 f\"(price moved) -> retry marketable: {msg[:100]}\")\n"
            "                        w[\"entry_mode\"] = \"marketable\"\n"
            "                        _rev_clear_order(w)\n"
            "                        save_reversal_watchers()\n"
            "                        return\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P10 — CLI flag: --rev-subbar-strict
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P10-cli-strict",
        "desc": "Add --rev-subbar-strict CLI flag",
        "old": (
            "    p.add_argument(\"--rev-subbar-entry-marketable\", action=\"store_true\",\n"
            "                   help=\"[SubBar Entry] استخدم Limit عند subbar_close مع \"\n"
            "                        \"تقاطع السبريد (taker) بدل Post-Only GTX (maker)\")\n"
        ),
        "new": (
            "    p.add_argument(\"--rev-subbar-strict\", action=\"store_true\",\n"
            "                   help=\"[SubBar Strict] Post-Only only + no reprice + \"\n"
            "                        \"no marketable fallback. Order sits at confirm \"\n"
            "                        \"bar close until fill or timeout.\")\n"
            "    p.add_argument(\"--rev-subbar-entry-marketable\", action=\"store_true\",\n"
            "                   help=\"[SubBar Entry] استخدم Limit عند subbar_close مع \"\n"
            "                        \"تقاطع السبريد (taker) بدل Post-Only GTX (maker)\")\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P11 — CLI wiring: --rev-subbar-strict
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P11-cli-strict-wiring",
        "desc": "Wire --rev-subbar-strict into CFG",
        "old": (
            "    if getattr(args, \"rev_subbar_entry_marketable\", False):\n"
            "        CFG.REV_SUBBAR_ENTRY_MARKETABLE = True\n"
        ),
        "new": (
            "    if getattr(args, \"rev_subbar_strict\", False):\n"
            "        CFG.REV_SUBBAR_ENTRY_STRICT = True\n"
            "        CFG.REV_SUBBAR_ENTRY_ENABLED = True\n"
            "        CFG.REV_SUBBAR_ENTRY_MARKETABLE = False\n"
            "        CFG.REV_SUBBAR_ENTRY_MAX_DRIFT_BPS = 999999.0\n"
            "        CFG.REV_REPRICE_S = 999999.0\n"
            "        log.info(\n"
            "            \"[SubBar-Strict] ENABLED — Post-Only GTX only, \"\n"
            "            \"no reprice, no marketable fallback, order fixed \"\n"
            "            \"at confirm bar close\"\n"
            "        )\n"
            "        log.info(\n"
            "            f\"[SubBar-Strict] pen={CFG.REV_SUBBAR_ENTRY_PEN_BPS:.1f}bps \"\n"
            "            f\"max_rejects={CFG.REV_MAX_REJECTS} \"\n"
            "            f\"fill_timeout={CFG.REV_FILL_MAX_WAIT_S:.0f}s\"\n"
            "        )\n"
            "    if getattr(args, \"rev_subbar_entry_marketable\", False):\n"
            "        CFG.REV_SUBBAR_ENTRY_MARKETABLE = True\n"
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _count_occurrences(text: str, pattern: str) -> int:
    if not pattern:
        return 0
    return text.count(pattern)


def _apply_one_patch(content: str, patch: dict):
    """Returns (new_content, status, detail)."""
    old = patch["old"]
    new = patch["new"]
    pid = patch["id"]

    # Fast path: already applied?
    if _count_occurrences(content, new) == 1:
        return content, "already_applied", f"{pid}: already applied"

    old_count = _count_occurrences(content, old)
    if old_count == 0:
        return content, "not_found", (
            f"{pid}: anchor not found "
            f"(file may differ, or already patched differently)"
        )
    if old_count > 1:
        return content, "ambiguous", (
            f"{pid}: anchor appears {old_count} times (must be exactly 1)"
        )

    new_content = content.replace(old, new, 1)
    return new_content, "applied", f"{pid}: OK"


def _verify_syntax(content: str):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


def _is_already_patched(content: str) -> bool:
    return MARKER in content


def run_patch(target: Path, dry_run: bool = False) -> int:
    print(f"\n{'═' * 74}")
    print(f"  REV Sub-Bar Entry — Patcher")
    print(f"  Target: {target}")
    print(f"  Mode  : {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target file not found: {target}")
        return 1

    original = target.read_text(encoding="utf-8")
    print(f"  📄 Loaded {len(original):,} chars "
          f"({original.count(chr(10)):,} lines)\n")

    # Early exit: already patched?
    if _is_already_patched(original):
        print(f"  ⚠️  File already contains marker: {MARKER}")
        print(f"     Verifying all patches present...")
        all_present = True
        for patch in PATCHES:
            if _count_occurrences(original, patch["new"]) != 1:
                print(f"     ❌ {patch['id']}: missing or duplicated")
                all_present = False
        if all_present:
            print(f"  ✅ All {len(PATCHES)} patches verified present.\n")
            return 0
        else:
            print(f"  ⚠️  Some patches missing despite marker — "
                  f"consider --rollback.\n")
            return 2

    # Apply sequentially
    content = original
    applied = []
    skipped = []
    failed = []

    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        print(f"  [{i:02d}/{len(PATCHES)}] {pid} ... ", end="", flush=True)
        new_content, status, detail = _apply_one_patch(content, patch)
        if status == "applied":
            content = new_content
            applied.append(patch)
            print(f"✅ applied")
        elif status == "already_applied":
            skipped.append(patch)
            print(f"⏭️  already applied")
        else:
            failed.append((patch, detail))
            print(f"❌ {status}")
            print(f"        └─ {detail}")

    print(f"\n{'─' * 74}")
    print(f"  Summary: {len(applied)} applied, {len(skipped)} already, "
          f"{len(failed)} failed")
    print(f"{'─' * 74}\n")

    if failed:
        print(f"  ❌ Patching aborted — {len(failed)} patch(es) failed.")
        print(f"     No file was modified. Inspect the anchors below:\n")
        for patch, detail in failed:
            print(f"     • {patch['id']}")
            print(f"       {patch['desc']}")
            print(f"       → {detail}\n")
        return 3

    # ── No changes needed? ──
    if len(applied) == 0:
        print(f"  ✅ File already fully patched — nothing to write.\n")
        return 0

    # ── Add marker if not present (P07 implicit) ──
    if MARKER not in content:
        # Insert marker before the first line
        _lines = content.split("\n", 1)
        if len(_lines) == 2:
            content = f"{MARKER}\n{_lines[0]}\n{_lines[1]}"
        else:
            content = f"{MARKER}\n{content}"
        print(f"  ✅ Marker inserted: {MARKER}")

    # ── Syntax validation ──
    print(f"  🔍 Validating syntax (ast.parse)...")
    ok, err = _verify_syntax(content)
    if not ok:
        print(f"  ❌ Syntax validation FAILED: {err}")
        print(f"     No file was modified. This is a patcher bug — "
              f"please report.\n")
        return 4
    print(f"  ✅ Syntax OK\n")

    # ── Dry-run: stop here ──
    if dry_run:
        print(f"  🧪 DRY-RUN — would write {len(content):,} chars "
              f"to {target}")
        print(f"     Diff summary (before/after first lines):\n")
        for patch in applied:
            print(f"     ── {patch['id']} ──")
            print(f"       OLD: {patch['old'].splitlines()[0][:70]}...")
            print(f"       NEW: {patch['new'].splitlines()[0][:70]}...")
        print()
        return 0

    # ── Backup original ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target.with_suffix(
        target.suffix + f".rev_subbar_backup_{ts}"
    )
    try:
        shutil.copy2(target, backup_path)
        print(f"  💾 Backup: {backup_path.name}")
    except Exception as e:
        print(f"  ❌ Backup failed: {e}")
        print(f"     Aborting — no file modified.\n")
        return 5

    # ── Atomic write (tmp → os.replace) ──
    tmp_path = target.with_suffix(target.suffix + ".rev_subbar_tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        _ = tmp_path.read_text(encoding="utf-8")
        os.replace(tmp_path, target)
        print(f"  ✅ Written: {target}")
        print(f"     Backup : {backup_path.name}\n")
    except Exception as e:
        print(f"  ❌ Write failed: {e}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        try:
            if backup_path.exists():
                shutil.copy2(backup_path, target)
                print(f"  🔄 Auto-rollback from backup complete.\n")
        except Exception as rb_err:
            print(f"  ⚠️  Auto-rollback also failed: {rb_err}\n")
        return 6

    # ── Success banner ──
    print(f"{'═' * 74}")
    print(f"  ✅ REV Sub-Bar Entry successfully applied!")
    print(f"{'═' * 74}")
    print(f"  Behavior:")
    print(f"    • On bounce confirmation, the entry order is placed as a")
    print(f"      Post-Only Limit at the CLOSE of the confirm sub-bar.")
    print(f"    • Matches backtest's _check_reversal_fill_subbars exactly.")
    print(f"    • Falls back to marketable if price drifted > MAX_DRIFT_BPS.")
    print(f"")
    print(f"  To enable at runtime:")
    print(f"      python3 {target.name} --mode testnet --reversal-confirm \\")
    print(f"          --rev-subbar-entry")
    print(f"")
    print(f"  To disable (legacy marketable):")
    print(f"      python3 {target.name} --mode testnet --reversal-confirm \\")
    print(f"          --no-rev-subbar-entry")
    print(f"")
    print(f"  To use marketable-at-subbar-close (taker, faster fill):")
    print(f"      python3 {target.name} --mode testnet --reversal-confirm \\")
    print(f"          --rev-subbar-entry --rev-subbar-entry-marketable")
    print(f"")
    print(f"  To rollback:")
    print(f"      python3 {Path(__file__).name} --rollback --target {target.name}")
    print(f"{'═' * 74}\n")
    return 0


def run_verify(target: Path) -> int:
    """Verify-only mode: check whether all patches are applied."""
    print(f"\n{'═' * 74}")
    print(f"  REV Sub-Bar Entry — Verification")
    print(f"  Target: {target}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target not found: {target}\n")
        return 1

    content = target.read_text(encoding="utf-8")
    has_marker = _is_already_patched(content)
    print(f"  Marker present : {'✅ YES' if has_marker else '❌ NO'}")
    print(f"  File size      : {len(content):,} chars "
          f"({content.count(chr(10)):,} lines)\n")

    ok_count = 0
    bad_count = 0
    for patch in PATCHES:
        pid = patch["id"]
        new_count = _count_occurrences(content, patch["new"])
        old_count = _count_occurrences(content, patch["old"])
        if new_count == 1:
            print(f"  ✅ {pid:35s} applied")
            ok_count += 1
        elif new_count > 1:
            print(f"  ⚠️  {pid:35s} applied {new_count}× (dup?)")
            bad_count += 1
        elif old_count == 1:
            print(f"  ❌ {pid:35s} NOT applied (anchor intact)")
            bad_count += 1
        elif old_count > 1:
            print(f"  ❌ {pid:35s} anchor {old_count}× (ambiguous)")
            bad_count += 1
        else:
            print(f"  ⚠️  {pid:35s} anchor missing (modified externally?)")
            bad_count += 1

    print(f"\n{'─' * 74}")
    if ok_count == len(PATCHES):
        print(f"  ✅ All {len(PATCHES)} patches verified — Sub-Bar Entry active.")
        print(f"{'─' * 74}\n")
        return 0
    else:
        print(f"  ⚠️  {ok_count}/{len(PATCHES)} verified, "
              f"{bad_count} issue(s).")
        print(f"{'─' * 74}\n")
        return 2


def run_rollback(target: Path) -> int:
    """Rollback mode: restore the most recent backup."""
    print(f"\n{'═' * 74}")
    print(f"  REV Sub-Bar Entry — Rollback")
    print(f"  Target: {target}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target not found: {target}\n")
        return 1

    backups = sorted(
        target.parent.glob(target.name + ".rev_subbar_backup_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not backups:
        print(f"  ❌ No backups found in {target.parent}")
        print(f"     Looking for: {target.name}.rev_subbar_backup_*\n")
        return 1

    latest = backups[0]
    print(f"  🔍 Found {len(backups)} backup(s). Latest:")
    print(f"     {latest.name}")
    print(f"     {latest.stat().st_size:,} bytes, "
          f"mtime={datetime.fromtimestamp(latest.stat().st_mtime)}")

    # Verify backup is valid Python
    try:
        backup_content = latest.read_text(encoding="utf-8")
        ok, err = _verify_syntax(backup_content)
        if not ok:
            print(f"  ⚠️  Backup fails syntax check: {err}")
            print(f"     Restoring anyway (safest available state).\n")
    except Exception as e:
        print(f"  ❌ Cannot read backup: {e}\n")
        return 2

    # Safety: back up current state before overwriting
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_rollback = target.with_suffix(
        target.suffix + f".pre_rollback_{ts}"
    )
    try:
        shutil.copy2(target, pre_rollback)
        print(f"  💾 Pre-rollback snapshot: {pre_rollback.name}")
    except Exception as e:
        print(f"  ❌ Pre-rollback snapshot failed: {e}\n")
        return 3

    try:
        shutil.copy2(latest, target)
        print(f"  ✅ Rolled back: {target}")
        print(f"     Restored from: {latest.name}")
        print(f"     Snapshot kept: {pre_rollback.name}\n")
    except Exception as e:
        print(f"  ❌ Rollback failed: {e}")
        print(f"     Pre-rollback snapshot is safe at: {pre_rollback.name}\n")
        return 4

    # Verify restored file
    try:
        restored = target.read_text(encoding="utf-8")
        ok, err = _verify_syntax(restored)
        if ok:
            print(f"  ✅ Restored file passes syntax check.")
            print(f"     RASE marker present: "
                  f"{'yes (unexpected!)' if _is_already_patched(restored) else 'no (expected)'}\n")
        else:
            print(f"  ⚠️  Restored file FAILS syntax: {err}")
            print(f"     Restore {pre_rollback.name} manually.\n")
            return 5
    except Exception as e:
        print(f"  ⚠️  Could not verify restored file: {e}\n")

    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="REV Sub-Bar Entry — Automated Patcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 rev_subbar_entry_patcher.py                 # apply\n"
            "  python3 rev_subbar_entry_patcher.py --dry-run       # preview\n"
            "  python3 rev_subbar_entry_patcher.py --verify-only   # check\n"
            "  python3 rev_subbar_entry_patcher.py --rollback      # restore\n"
            "  python3 rev_subbar_entry_patcher.py --target foo.py # custom\n"
        ),
    )
    parser.add_argument(
        "--target", type=str, default=DEFAULT_TARGET,
        help=f"Target file to patch (default: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without writing",
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Check if patches are applied, no write",
    )
    parser.add_argument(
        "--rollback", action="store_true",
        help="Restore the most recent backup",
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()

    try:
        if args.rollback:
            return run_rollback(target)
        if args.verify_only:
            return run_verify(target)
        return run_patch(target, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n\n  ⏹️  Interrupted by user.\n")
        return 130
    except Exception as e:
        print(f"\n  💥 Unexpected error: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
