#!/usr/bin/env python3
import os

TARGET = "trading_2_live4_v2_GTX.py"

def main():
    print("=" * 65)
    print(" 🚀 QTT Master Patcher (Smart HFT + CLI Options)")
    print("=" * 65)

    if not os.path.exists(TARGET):
        print(f"[ERROR] '{TARGET}' not found.")
        return

    with open(TARGET, "r", encoding="utf-8") as f:
        lines = f.read().split('\n')

    # ---------------------------------------------------------
    # 1. Update Config Default
    # ---------------------------------------------------------
    for i, line in enumerate(lines):
        if 'REVERSAL_EXEC: str = "gtx"' in line:
            lines[i] = '    REVERSAL_EXEC: str = "smart"  # "gtx", "aggressive", or "smart"'
            print("[OK] Config default updated to 'smart'.")
            break

    # ---------------------------------------------------------
    # 2. Update CLI Options
    # ---------------------------------------------------------
    for i, line in enumerate(lines):
        if 'p.add_argument("--reversal-exec"' in line:
            lines[i] = '    p.add_argument("--reversal-exec", type=str, default="smart",'
            lines[i+1] = '                   choices=["gtx", "aggressive", "smart"],'
            lines[i+2] = '                   help="Execution style for reversal confirm (default: smart)")'
            print("[OK] CLI Options updated.")
            break

    # ---------------------------------------------------------
    # 3. Patch Backtest Logic
    # ---------------------------------------------------------
    start_bt, end_bt = -1, -1
    for i, line in enumerate(lines):
        if 'exec_style = str(getattr(cfg, \'REVERSAL_EXEC\', \'gtx\'))' in line:
            start_bt = i
            for j in range(i, len(lines)):
                if 'return (int(confirm_main), float(fill_px))' in lines[j] or 'return (int(fill_main), float(fill_px))' in lines[j]:
                    end_bt = j
                    break
            break

    if start_bt != -1 and end_bt != -1:
        bt_code = """    exec_style = str(getattr(cfg, 'REVERSAL_EXEC', 'smart'))

    if exec_style in ["aggressive", "smart"]:
        fill_px = float(sc_flat[confirm_k]) if np.isfinite(sc_flat[confirm_k]) else float(target0)
        fill_main = start_main + (confirm_k // sub_pm)
        _entry_sub = confirm_k % sub_pm
        
        _REV_ENTRY_SUB[(str(sig.symbol), int(sig.close_idx))] = int(_entry_sub)
        return (int(fill_main), float(fill_px))
        
    else:
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
                
        if fill_k < 0: return None
            
        fill_px = limit_px
        fill_main = start_main + (fill_k // sub_pm)
        _entry_sub = fill_k % sub_pm
        
        _REV_ENTRY_SUB[(str(sig.symbol), int(sig.close_idx))] = int(_entry_sub)
        return (int(fill_main), float(fill_px))"""
        lines[start_bt:end_bt+1] = bt_code.split('\n')
        print("[OK] Backtest engine updated.")

    # ---------------------------------------------------------
    # 4. Patch Live Engine (Smart HFT + Predictive Lead)
    # ---------------------------------------------------------
    start_lv, end_lv = -1, -1
    for i, line in enumerate(lines):
        if 'exec_style = str(getattr(CFG, \'REVERSAL_EXEC\'' in line:
            start_lv = i
            for j in range(i, len(lines)):
                if 'def _rev_finish(' in lines[j]:
                    for k in range(j, i, -1):
                        if 'save_reversal_watchers()' in lines[k]:
                            end_lv = k
                            break
                    break
            if end_lv != -1:
                break

    if start_lv != -1 and end_lv != -1:
        lv_code = """    exec_style = str(w.get("exec_override", getattr(CFG, 'REVERSAL_EXEC', 'smart')))
    
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
            o = _rev_api(exchange.create_order, sym, "limit", side, q, marketable_px, params={"clientOrderId": cid})
            w["order_id"] = str(o.get("id") or "")
            w["cid_sent"] = False
            log.info(f"⚡ [Rev-Aggressive] {sym} {side} {q} @ {marketable_px:.6f}")
        except Exception as e:
            _rev_clear_order(w)

    elif exec_style == "smart":
        target_px = float(w.get("target") or ref_px)
        orig_sl_dist = float(w.get("orig_sl_dist", target_px * 0.015))
        max_slip_allowed = orig_sl_dist * 0.15 
        
        # ── [HFT PREDICTIVE LEAD] حساب السرعة وتأثير الحجم ──
        last_px = float(w.get("prev_px", px))
        last_ts = float(w.get("last_reprice", now - 1.0))
        dt = max(now - last_ts, 0.1)
        velocity = (px - last_px) / dt
        w["prev_px"] = px
        
        latency_s = 0.30 
        size_impact_multiplier = 1.0 + min((q * px) / 20000.0, 0.5) 
        predictive_lead = velocity * latency_s * size_impact_multiplier

        if action == "BUY":
            gtx_px = px + (predictive_lead if predictive_lead > 0 else 0)
            gtx_px = min(gtx_px, px * 1.0001)
        else:
            gtx_px = px + (predictive_lead if predictive_lead < 0 else 0)
            gtx_px = max(gtx_px, px * 0.9999)
            
        gtx_px = _rev_snap_price(exchange, sym, gtx_px, side)
        w["order_px"] = gtx_px
        w["last_reprice"] = now
        save_reversal_watchers()
        
        try:
            o = _rev_api(exchange.create_order, sym, "limit", side, q, gtx_px, params={"timeInForce": "GTX", "clientOrderId": cid})
            w["order_id"] = str(o.get("id") or "")
            w["cid_sent"] = False
            w["smart_attempts"] = int(w.get("smart_attempts", 0)) + 1
            log.info(f"🧠 [Rev-Smart HFT] Predictive Maker {sym} @ {gtx_px:.6f} (Vel: {velocity:.4f})")
            
        except Exception as e:
            msg = str(e)
            if ("-5022" in msg or "Post Only" in msg):
                w["rejects"] = int(w.get("rejects", 0)) + 1
                _rev_clear_order(w)
                if int(w.get("rejects", 0)) >= 1:
                    log.info(f"⚠️ [Rev-Smart HFT] السعر يفلت في {sym}! هجوم استباقي.")
                    if action == "BUY":
                        marketable_px = px + max_slip_allowed + abs(predictive_lead)
                    else:
                        marketable_px = px - max_slip_allowed - abs(predictive_lead)
                    marketable_px = _rev_snap_price(exchange, sym, marketable_px, side)
                    try:
                        o2 = _rev_api(exchange.create_order, sym, "limit", side, q, marketable_px)
                        w["order_id"] = str(o2.get("id") or "")
                        log.info(f"💥 [Rev-Smart-Taker] تم القنص بدقة @ {marketable_px:.6f}")
                    except Exception as e2:
                        _rev_finish(exchange, sym, w, open_pos_live, assets, "smart_chase_failed")
            else:
                _rev_clear_order(w)

    else:
        gtx_px = float(px)
        w["order_px"] = gtx_px
        w["last_reprice"] = now
        save_reversal_watchers() 
        try:
            o = _rev_api(exchange.create_order, sym, "limit", side, q, gtx_px, params={"timeInForce": "GTX", "clientOrderId": cid})
            w["order_id"] = str(o.get("id") or "")
            w["cid_sent"] = False
            log.info(f"🛡️ [Rev-GTX Maker] {sym} {side} {q} @ {gtx_px:.6f}")
        except Exception as e:
            msg = str(e)
            if ("-5022" in msg or "Post Only" in msg):
                w["rejects"] = int(w.get("rejects", 0)) + 1
                _rev_clear_order(w)
            else:
                _rev_clear_order(w)
    save_reversal_watchers()"""
        lines[start_lv:end_lv+1] = lv_code.split('\n')
        print("[OK] Live Engine (Smart HFT) injected successfully.")

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write('\n'.join(lines))
        
    print("\n[SUCCESS] The bot is ready!")

if __name__ == "__main__":
    main()
