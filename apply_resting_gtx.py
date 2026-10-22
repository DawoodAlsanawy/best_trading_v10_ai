#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_resting_gtx.py  [REV-FIX v6]

يجعل البوت بعد تأكيد الانعكاس:
  - يضع GTX عند target (لا marketable، لا chase)
  - ينتظر حتى 6 ساعات (بدل 90 ثانية)
  - لا يُعيد التسعير، لا يُطارد السعر

يطبق على النسخة الحالية بأمان (لا يتعارض مع Ladder).
"""
import argparse, ast, os, py_compile, shutil, sys, time

MARK = "[REV-FIX v6]"


def _once(src, old, name):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"[ABORT] '{name}' matched {n} times (expected 1)")


# ═══════════════════════════════════════════════════════════════
# P1 — Config: change fill wait from 90s to 6h
# ═══════════════════════════════════════════════════════════════
P1_OLD = "    REV_FILL_MAX_WAIT_S: float = 90.0         # total time budget of the non-blocking FILLING state\n"
P1_NEW = (
    "    REV_FILL_MAX_WAIT_S: float = 21600.0      # [REV-FIX v6] 6h resting window\n"
)


# ═══════════════════════════════════════════════════════════════
# P2 — Replace marketable block with resting GTX at target
# ═══════════════════════════════════════════════════════════════
P2_OLD = '''    w["attempt"] = int(w.get("attempt", 0)) + 1
    cid = _rev_cid(sym, float(w["sig_epoch"]), int(w["attempt"]))
    w["cid"] = cid
    w["cid_sent"] = True
    
    # ════════════════════════════════════════════════════════════════
    # [SMART EXECUTION v2] Marketable Limit with Dynamic Slippage Cap
    # ════════════════════════════════════════════════════════════════
    # حساب المسافة الأصلية للوقف للحفاظ على التناسب
    orig_sl_dist = float(w.get("orig_sl_dist", ref_px * 0.015))
    
    # أقصى انزلاق مسموح هو 15% من مسافة الـ Stop Loss 
    # (بحيث لا يتشوه الـ Risk:Reward الخاص بك)
    max_slip_allowed = orig_sl_dist * 0.15 
    
    if action == "BUY":
        # في الشراء: نرسل أمر ليمت أعلى من أفضل سعر بيع (Best Ask) بقليل
        marketable_px = px + max_slip_allowed
    else:
        # في البيع: نرسل أمر ليمت أقل من أفضل سعر شراء (Best Bid) بقليل
        marketable_px = px - max_slip_allowed
        
    # تقريب السعر ليتوافق مع شروط البورصة
    marketable_px = _rev_snap_price(exchange, sym, marketable_px, side)
    
    w["order_px"] = marketable_px
    w["last_reprice"] = now
    save_reversal_watchers()            # persist BEFORE the order exists
    
    try:
        # إرسال الأمر بدون GTX (ليتمكن من اقتحام السبريد كأمر Market)
        # ولكن بحد أقصى للسعر يمنع الانزلاق الكارثي
        o = _rev_api(exchange.create_order, sym, "limit", side, q, marketable_px,
                     params={"clientOrderId": cid})
        w["order_id"] = str(o.get("id") or "")
        w["cid_sent"] = False
        log.info(f"[LiveRev-Smart] {sym} Marketable Limit {side} {q} @ {marketable_px:.6f} (Current Ask/Bid: {px:.6f})")
'''

P2_NEW = '''    w["attempt"] = int(w.get("attempt", 0)) + 1
    cid = _rev_cid(sym, float(w["sig_epoch"]), int(w["attempt"]))
    w["cid"] = cid
    w["cid_sent"] = True

    # ════════════════════════════════════════════════════════════════
    # [REV-FIX v6] RESTING GTX at target — no chase, no reprice.
    # After bounce confirms, place a post-only limit AT target and wait
    # up to REV_FILL_MAX_WAIT_S for the market to come back.
    # ════════════════════════════════════════════════════════════════
    target_px = float(w["target"])
    resting_px = _rev_snap_price(exchange, sym, target_px, side)
    # Clamp so GTX doesn't cross the book (avoid -5022):
    #   BUY:  order must be <= best_bid (px)
    #   SELL: order must be >= best_ask (px)
    if px is not None and px > 0:
        if side == "buy" and resting_px > px:
            resting_px = _rev_snap_price(exchange, sym, px, side)
        elif side == "sell" and resting_px < px:
            resting_px = _rev_snap_price(exchange, sym, px, side)

    w["order_px"] = resting_px
    w["last_reprice"] = now
    save_reversal_watchers()

    try:
        o = _rev_api(exchange.create_order, sym, "limit", side, q, resting_px,
                     params={"timeInForce": "GTX", "clientOrderId": cid})
        w["order_id"] = str(o.get("id") or "")
        w["cid_sent"] = False
        log.info(f"[LiveRev-Resting] {sym} GTX {side} {q} @ {resting_px:.6f} "
                 f"(target={target_px:.6f}, best={px:.6f})")
'''


# ═══════════════════════════════════════════════════════════════
# P3 — Remove the reprice/chase block (just wait)
# ═══════════════════════════════════════════════════════════════
P3_OLD = '''                if now >= float(w["fill_deadline"]) or w.get("cancel_req"):
                    if not _rev_cancel_and_confirm(exchange, sym, w):
                        return
                elif now - float(w.get("last_reprice", 0.0)) >= float(
                        _revc("REV_REPRICE_S", 5.0)):
                    w["last_reprice"] = now
                    try:
                        px = _rev_best_px(exchange, sym, action)
                    except Exception as e:
                        log.debug(f"[LiveRev] {sym} book error: {e}")
                        return
                    if px is None:
                        return
                    if _rev_beyond_chase(action, px, ref_px, chase):
                        w["stop_reason"] = "chase_cap"
                        if not _rev_cancel_and_confirm(exchange, sym, w):
                            w["cancel_req"] = True
                            return
                    elif abs(_rev_marketable_px(exchange, sym, w, action, side, px, ref_px)
                             - float(w.get("order_px", 0.0))) > 0.0:   # [REV-FIX v3]
                        if not _rev_cancel_and_confirm(exchange, sym, w):
                            w["cancel_req"] = True
                            return
                    else:
                        return
                else:
                    return
'''

P3_NEW = '''                # [REV-FIX v6] No reprice, no chase. Just wait for fill.
                if now >= float(w["fill_deadline"]) or w.get("cancel_req"):
                    if not _rev_cancel_and_confirm(exchange, sym, w):
                        return
                else:
                    return
'''


PATCHES = [
    ("P1.wait",     P1_OLD, P1_NEW, True),
    ("P2.place",    P2_OLD, P2_NEW, True),
    ("P3.reprice",  P3_OLD, P3_NEW, True),
]


def apply(src):
    if MARK in src:
        raise SystemExit("[ABORT] already has [REV-FIX v6].")
    for name, old, new, _ in PATCHES:
        _once(src, old, name)
    for name, old, new, _ in PATCHES:
        src = src.replace(old, new, 1)
    return src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", default="trading_2_live4.py")
    ap.add_argument("--inplace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    with open(a.src, "r", encoding="utf-8") as f:
        src = f.read()
    new = apply(src)
    ast.parse(new)
    print(f"[OK] {len(PATCHES)} anchors; syntax OK")

    if a.dry_run:
        return
    if a.inplace:
        bak = f"{a.src}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(a.src, bak)
        print(f"[OK] backup -> {bak}")
        out = a.src
    else:
        out = a.src.replace(".py", "_v6.py")

    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    py_compile.compile(tmp, doraise=True)
    os.replace(tmp, out)
    print(f"[OK] written -> {out}")


if __name__ == "__main__":
    main()
