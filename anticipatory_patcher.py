#!/usr/bin/env python3
import os

TARGET = "trading_2_live4_v2_GTX.py"

def main():
    print("=" * 65)
    print(" 🔮 QTT Anticipatory Execution Patcher (OFI Trap Engine)")
    print("=" * 65)

    if not os.path.exists(TARGET):
        print(f"[ERROR] '{TARGET}' not found.")
        return

    with open(TARGET, "r", encoding="utf-8") as f:
        lines = f.read().split('\n')

    # ---------------------------------------------------------
    # 1. زرع محرك الـ Anticipatory OFI في الـ Reversal Watchers
    # ---------------------------------------------------------
    start_tk, end_tk = -1, -1
    for i, line in enumerate(lines):
        if '# ══ [BOUNCE-TICKER] live ticker params ══' in line:
            start_tk = i
            for j in range(i + 1, len(lines)):
                if 'if now >= float(w.get("next_fetch_ts", 0.0)):' in lines[j]:
                    end_tk = j
                    break
            break

    if start_tk != -1 and end_tk != -1:
        anticipatory_code = """            # ════════════════════════════════════════════════════════════════
            # 🔮 [ANTICIPATORY OFI TRAP] قراءة استباقية للسيولة وبناء هندسة عكسية
            # ════════════════════════════════════════════════════════════════
            if st == "WAITING_BOUNCE":
                _ticker_throttle = 1.0  # فحص الدفتر كل ثانية واحدة
                _last_tick_ts = float(w.get("last_ticker_ts", 0.0))
                
                if now - _last_tick_ts >= _ticker_throttle:
                    w["last_ticker_ts"] = now
                    try:
                        # جلب دفتر الأوامر اللحظي بدلا من مجرد السعر
                        ob = _rev_api(exchange.fetch_order_book, sym, 5, weight=2.0)
                        best_bid = float(ob['bids'][0][0])
                        best_ask = float(ob['asks'][0][0])
                        bid_vol = sum(float(b[1]) for b in ob['bids'][:3])
                        ask_vol = sum(float(a[1]) for a in ob['asks'][:3])
                        
                        action = w["action"]
                        # حساب مسافة الوقف الفعلية بناءً على معامل التوسعة الخاص بالمستخدم
                        sl_widen_mult = float(getattr(CFG, 'SL_WIDEN_MULT', 1.0))
                        orig_sl_dist = float(w.get("orig_sl_dist", best_bid * 0.015))
                        actual_sl_dist = orig_sl_dist * sl_widen_mult
                        
                        # حساب عدم توازن تدفق الأوامر (OFI) بين -1.0 و 1.0
                        ofi = (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-9)
                        
                        if action == "BUY":
                            # تسجيل القاع المطلق
                            local_ext = min(float(w.get("local_extreme", best_bid)), best_bid)
                            w["local_extreme"] = local_ext
                            
                            # الهندسة العكسية: الدخول المثالي هو 80% من مسافة الوقف فوق القاع
                            # هذا يضمن أن الوقف سيُزرع تحت القاع المطلق بـ 20% من مسافته
                            ideal_entry = local_ext + (actual_sl_dist * 0.8)
                            
                            # شروط الانطلاق الاستباقي:
                            # 1. المشترون يبتلعون الدفتر (OFI > 0.3)
                            # 2. السعر الحالي لا يزال أقل من دخولنا المثالي (يمكننا رمي GTX بأمان)
                            if ofi > 0.3 and best_ask <= ideal_entry * 1.0005:
                                w["status"] = "READY_TO_FILL"
                                w["ref_px"] = ideal_entry
                                w["target"] = ideal_entry  # تثبيت الهندسة
                                w["confirm_close_ts"] = now
                                w["bounce_source"] = "anticipatory_ofi"
                                w["exec_override"] = "gtx" # إجبار البوت على استخدام GTX
                                
                                log.info(f"🔮 [Anticipatory] {sym} BUY Predicted! OFI={ofi:.2f}. "
                                         f"Min={local_ext:.6f} -> Placing GTX Trap @ {ideal_entry:.6f}")
                                dirty = True
                                
                        else: # SELL
                            # تسجيل القمة المطلقة
                            local_ext = max(float(w.get("local_extreme", best_ask)), best_ask)
                            w["local_extreme"] = local_ext
                            
                            ideal_entry = local_ext - (actual_sl_dist * 0.8)
                            
                            if ofi < -0.3 and best_bid >= ideal_entry * 0.9995:
                                w["status"] = "READY_TO_FILL"
                                w["ref_px"] = ideal_entry
                                w["target"] = ideal_entry
                                w["confirm_close_ts"] = now
                                w["bounce_source"] = "anticipatory_ofi"
                                w["exec_override"] = "gtx"
                                
                                log.info(f"🔮 [Anticipatory] {sym} SELL Predicted! OFI={ofi:.2f}. "
                                         f"Max={local_ext:.6f} -> Placing GTX Trap @ {ideal_entry:.6f}")
                                dirty = True
                                
                        # التنفيذ الفوري إذا تحقق الشرط
                        if w["status"] == "READY_TO_FILL" and starts < _REV_MAX_PER_CYCLE:
                            _rev_handle_ready(exchange, sym, w, open_pos_live, now, sub_sec, cap_now, corr_cache)
                            if w["status"] == "FILLING":
                                starts += 1
                                _rev_advance_filling(exchange, sym, w, open_pos_live, assets, now)
                                
                    except Exception as _te:
                        log.debug(f"[LiveRev] {sym} anticipatory error: {_te}")
"""
        lines[start_tk:end_tk] = anticipatory_code.split('\n')
        print("[OK] Anticipatory OFI Trap engine injected successfully.")
    else:
        print("[WARNING] Could not locate Ticker block.")

    # ---------------------------------------------------------
    # 2. إجبار الدالة على احترام الـ exec_override
    # ---------------------------------------------------------
    override_updated = False
    for i, line in enumerate(lines):
        if 'exec_style = str(getattr(CFG, \'REVERSAL_EXEC\'' in line:
            lines[i] = '    exec_style = str(w.get("exec_override", getattr(CFG, \'REVERSAL_EXEC\', \'smart\')))'
            override_updated = True
            break
            
    if override_updated:
        print("[OK] Execution engine updated to respect Anticipatory GTX override.")

    # حفظ الملف
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write('\n'.join(lines))
        
    print(f"\n[SUCCESS] '{TARGET}' is now upgraded with Anticipatory Spatial Execution!")

if __name__ == "__main__":
    main()
