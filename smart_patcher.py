#!/usr/bin/env python3
import os

TARGET = "trading_2_live4_v2_GTX.py"

# ألوان التيرمنال لبيئة Linux
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'

def main():
    print("=" * 60)
    print(f"{GREEN} 🧠 QTT Smart-Chase Auto-Patcher (Linux Edition){RESET}")
    print("=" * 60)

    if not os.path.exists(TARGET):
        print(f"{RED}[ERROR] Could not find '{TARGET}' in the current directory.{RESET}")
        return

    with open(TARGET, "r", encoding="utf-8") as f:
        lines = f.read().split('\n')

    # ---------------------------------------------------------
    # 1. تحديث خيارات سطر الأوامر (CLI Options)
    # ---------------------------------------------------------
    arg_updated = False
    for i, line in enumerate(lines):
        if 'p.add_argument("--reversal-exec"' in line:
            lines[i] = '    p.add_argument("--reversal-exec", type=str, default="smart",'
            lines[i+1] = '                   choices=["gtx", "aggressive", "smart"],'
            lines[i+2] = '                   help="Execution style for reversal confirm (default: smart)")'
            arg_updated = True
            break
            
    if arg_updated:
        print(f"{GREEN}[OK] ✔️ CLI Options updated successfully.{RESET}")
    else:
        print(f"{YELLOW}[WARNING] Could not find argparse --reversal-exec to update.{RESET}")

    # ---------------------------------------------------------
    # 2. تحديث هندسة الصفقة (Dynamic Geometry) لتدعم Smart
    # ---------------------------------------------------------
    geom_updated = False
    for i, line in enumerate(lines):
        if 'if is_reversal and exec_style == "aggressive":' in line:
            lines[i] = line.replace('== "aggressive"', 'in ["aggressive", "smart"]')
            geom_updated = True
            break
            
    if geom_updated:
        print(f"{GREEN}[OK] ✔️ Dynamic Geometry patched to support Smart mode.{RESET}")
    else:
        print(f"{YELLOW}[WARNING] Could not locate Dynamic Geometry block.{RESET}")

    # ---------------------------------------------------------
    # 3. تحديث محرك الباكتيست (Phase 3: Fill)
    # ---------------------------------------------------------
    start_bt, end_bt = -1, -1
    return_count = 0
    for i, line in enumerate(lines):
        if '# ── PHASE 3: FILL ──' in line:
            start_bt = i
        if start_bt != -1 and i > start_bt and 'return (int(fill_main), float(fill_px))' in line:
            return_count += 1
            if return_count == 2:  # نبحث عن الـ return الثانية لقص البلوك بالكامل
                end_bt = i
                break

    if start_bt != -1 and end_bt != -1:
        bt_code = """    exec_style = str(getattr(cfg, 'REVERSAL_EXEC', 'smart'))

    if exec_style in ["aggressive", "smart"]:
        # وضع يحاكي التقاط السعر بشكل هجومي (أو ذكي)
        fill_px = float(sc_flat[confirm_k]) if np.isfinite(sc_flat[confirm_k]) else float(target0)
        fill_main = start_main + (confirm_k // sub_pm)
        _entry_sub = confirm_k % sub_pm
        
        _REV_ENTRY_SUB[(str(sig.symbol), int(sig.close_idx))] = int(_entry_sub)
        return (int(fill_main), float(fill_px))
        
    else:
        # وضع الـ GTX الواقعي: ننتظر السعر ليعود إلينا لتجنب الرسوم
        limit_px = float(sc_flat[confirm_k]) if np.isfinite(sc_flat[confirm_k]) else float(target0)
        fill_k = -1
        max_wait_subbars = 12 
        search_end = min(confirm_k + 1 + max_wait_subbars, n_flat)
        
        for j in range(confirm_k + 1, search_end):
            if not np.isfinite(sl_flat[j]) or not np.isfinite(sh_flat[j]):
                continue
            if action == "BUY" and sl_flat[j] <= limit_px:
                fill_k = j; break
            elif action == "SELL" and sh_flat[j] >= limit_px:
                fill_k = j; break
                
        if fill_k < 0:
            return None # السعر لم يعد، ضاعت الصفقة
            
        fill_px = limit_px
        fill_main = start_main + (fill_k // sub_pm)
        _entry_sub = fill_k % sub_pm
        
        _REV_ENTRY_SUB[(str(sig.symbol), int(sig.close_idx))] = int(_entry_sub)
        return (int(fill_main), float(fill_px))"""
        
        lines[start_bt+1 : end_bt+1] = bt_code.split('\n')
        print(f"{GREEN}[OK] ✔️ Backtest Phase 3 (FILL) logic patched successfully.{RESET}")
    else:
        print(f"{YELLOW}[WARNING] Could not locate Backtest Phase 3 block.{RESET}")

    # ---------------------------------------------------------
    # 4. تحديث محرك الـ Live (Smart Chase)
    # ---------------------------------------------------------
    start_lv, end_lv = -1, -1
    for i, line in enumerate(lines):
        if 'w["cid_sent"] = True' in line and 'w["cid"] = cid' in lines[i-1]:
            start_lv = i
            # نبحث للأمام عن الدالة التالية كحد فاصل
            for j in range(i + 1, len(lines)):
                if 'def _rev_finish(' in lines[j]:
                    # نرجع للخلف للعثور على آخر save_reversal_watchers()
                    for k in range(j - 1, i, -1):
                        if 'save_reversal_watchers()' in lines[k]:
                            end_lv = k
                            break
                    break
            if end_lv != -1:
                break

    if start_lv != -1 and end_lv != -1:
        lv_code = """    exec_style = str(getattr(CFG, 'REVERSAL_EXEC', 'smart'))
    
    if exec_style == "aggressive":
        target_px = float(w.get("target") or ref_px)
        orig_sl_dist = float(w.get("orig_sl_dist", target_px * 0.015))
        max_slip_allowed = orig_sl_dist * 0.15 
        
        if action == "BUY":
            marketable_px = px + max_slip_allowed
            marketable_px = max(marketable_px, px * 1.0001)
        else:
            marketable_px = px - max_slip_allowed
            marketable_px = min(marketable_px, px * 0.9999)
            
        marketable_px = _rev_snap_price(exchange, sym, marketable_px, side)
        w["order_px"] = marketable_px
        w["last_reprice"] = now
        save_reversal_watchers() 
        
        try:
            o = _rev_api(exchange.create_order, sym, "limit", side, q, marketable_px,
                         params={"clientOrderId": cid})
            w["order_id"] = str(o.get("id") or "")
            w["cid_sent"] = False
            log.info(f"⚡ [Rev-Aggressive] {sym} {side} {q} @ {marketable_px:.6f}")
        except Exception as e:
            _rev_clear_order(w)
            
    elif exec_style == "smart":
        target_px = float(w.get("target") or ref_px)
        orig_sl_dist = float(w.get("orig_sl_dist", target_px * 0.015))
        max_slip_allowed = orig_sl_dist * 0.15 
        
        gtx_px = float(px)
        w["order_px"] = gtx_px
        w["last_reprice"] = now
        save_reversal_watchers()
        
        try:
            o = _rev_api(exchange.create_order, sym, "limit", side, q, gtx_px,
                         params={"timeInForce": "GTX", "clientOrderId": cid})
            w["order_id"] = str(o.get("id") or "")
            w["cid_sent"] = False
            w["smart_attempts"] = int(w.get("smart_attempts", 0)) + 1
            log.info(f"🧠 [Rev-Smart] Maker Attempt {w['smart_attempts']} for {sym} @ {gtx_px:.6f}")
            
        except Exception as e:
            msg = str(e)
            if ("-5022" in msg or "Post Only" in msg):
                w["rejects"] = int(w.get("rejects", 0)) + 1
                _rev_clear_order(w)
                
                if int(w.get("rejects", 0)) >= 1:
                    log.info(f"⚠️ [Rev-Smart] السعر يهرب في {sym}! نتحول للهجوم الفوري.")
                    if action == "BUY":
                        marketable_px = px + max_slip_allowed
                    else:
                        marketable_px = px - max_slip_allowed
                    marketable_px = _rev_snap_price(exchange, sym, marketable_px, side)
                    
                    try:
                        o2 = _rev_api(exchange.create_order, sym, "limit", side, q, marketable_px)
                        w["order_id"] = str(o2.get("id") or "")
                        log.info(f"💥 [Rev-Smart-Taker] تم الالتقاط الهجومي @ {marketable_px:.6f}")
                    except Exception as e2:
                        log.error(f"[Rev-Smart] الهجوم فشل: {e2}")
                        _rev_finish(exchange, sym, w, open_pos_live, assets, "smart_chase_failed")
            else:
                _rev_clear_order(w)

    else:
        gtx_px = float(px)
        w["order_px"] = gtx_px
        w["last_reprice"] = now
        save_reversal_watchers() 
        
        try:
            o = _rev_api(exchange.create_order, sym, "limit", side, q, gtx_px,
                         params={"timeInForce": "GTX", "clientOrderId": cid})
            w["order_id"] = str(o.get("id") or "")
            w["cid_sent"] = False
            log.info(f"🛡️ [Rev-GTX Maker] {sym} {side} {q} @ {gtx_px:.6f}")
        except Exception as e:
            msg = str(e)
            if ("-5022" in msg or "Post Only" in msg):
                w["rejects"] = int(w.get("rejects", 0)) + 1
                _rev_clear_order(w)
                log.info(f"[Rev-GTX] السعر تحرك ضدنا (تم رفض GTX) - سيعاد المحاولة ببرود.")
            else:
                _rev_clear_order(w)
                
    save_reversal_watchers()"""
        
        lines[start_lv+1 : end_lv+1] = lv_code.split('\n')
        print(f"{GREEN}[OK] ✔️ Live Engine (Smart/Aggressive/GTX) logic patched successfully.{RESET}")
    else:
        print(f"{YELLOW}[WARNING] Could not locate Live Engine block.{RESET}")

    # ---------------------------------------------------------
    # حفظ الملف
    # ---------------------------------------------------------
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"\n{GREEN}[SUCCESS] '{TARGET}' is now fully upgraded to Smart-Chase!{RESET}")
    print("=" * 60)

if __name__ == "__main__":
    main()
