#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
أداة تشخيص الحافة (Edge Diagnostic) لمحرك trading_medum_fixed.py

الاستخدام (نفس وسائط التشغيل المعتادة للمحرك):
    python diagnose_edge.py --mode backtest [أي وسائط أخرى]

تشغّل الباكتست كالمعتاد، ثم تطبع تشخيصاً يفصل:
  1) هل لاتجاه الإشارة قدرة تنبؤية؟      (عوائد أمامية + اختبار t)
  2) هل الدخول المعلّق يضيف انتقاءً عكسياً؟ (سوق مقابل Limit)
  3) كم تأكل التكاليف من الحافة؟          (بوحدة R)
لا تعدّل أي شيء في الاستراتيجية.
"""
import sys, importlib.util, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_target = os.path.join(HERE, "trading_medum_fixed.py")
if not os.path.exists(_target):
    _target = os.path.join(HERE, "trading_medum.py")
spec = importlib.util.spec_from_file_location("tm", _target)
tm = importlib.util.module_from_spec(spec)
sys.modules["tm"] = tm
spec.loader.exec_module(tm)

HORIZONS = (1, 3, 6, 12, 24)
MAX_BARS = 48          # أقصى مدة لحاجز ثلاثي
LIMIT_WAIT = 6         # عدد الشموع لانتظار تعبئة الـ Limit


def _triple_barrier(ad, ci, entry, d_sl, d_tp, side, start, max_bars=MAX_BARS):
    """نتيجة بوحدة R. SL قبل TP عند التزامن (تحفظ). side=+1 شراء، -1 بيع."""
    n = len(ad.closes)
    end = min(start + max_bars, n - 1)
    sl = entry - side * d_sl
    tp = entry + side * d_tp
    for k in range(start, end + 1):
        hi, lo = ad.highs[k], ad.lows[k]
        sl_hit = (lo <= sl) if side > 0 else (hi >= sl)
        tp_hit = (hi >= tp) if side > 0 else (lo <= tp)
        if sl_hit:
            return -1.0, "SL"
        if tp_hit:
            return d_tp / d_sl, "TP"
    if end <= start:
        return None, "NA"
    return side * (ad.closes[end] - entry) / d_sl, "TO"


def _t_stat(x):
    x = np.asarray(x, float)
    if len(x) < 3 or np.std(x, ddof=1) == 0:
        return 0.0
    return float(np.mean(x) / (np.std(x, ddof=1) / np.sqrt(len(x))))


def diagnose(signals, assets):
    cfg = tm.CFG
    print("\n" + "=" * 72)
    print("  تشخيص الحافة (Edge Diagnostic)")
    print("=" * 72)
    print(f"  عدد الإشارات: {len(signals):,}   عدد الأصول: {len(assets)}")

    # ── 1) عوائد أمامية باتجاه الإشارة ──
    print("\n[1] العوائد الأمامية (بعد الإشارة، باتجاهها، قبل التكاليف) — بالنقاط الأساسية")
    print(f"    {'أفق (شمعة)':>12} {'المتوسط bps':>12} {'t-stat':>8} {'نسبة صواب':>10} {'خط الأساس':>10}")
    for h in HORIZONS:
        rets, base = [], []
        for s in signals:
            ad = assets[s.symbol]
            ci = int(s.close_idx)
            if ci + h >= len(ad.closes):
                continue
            side = 1 if s.action == "BUY" else -1
            r = side * np.log(ad.closes[ci + h] / ad.closes[ci])
            rets.append(r * 1e4)
            # خط الأساس: متوسط العائد غير المشروط لنفس الأصل/الأفق باتجاه الإشارة
            seg = np.log(ad.closes[h:] / ad.closes[:-h])
            base.append(side * float(np.mean(seg)) * 1e4)
        if rets:
            print(f"    {h:>12} {np.mean(rets):>12.2f} {_t_stat(np.array(rets) - np.array(base)):>8.2f} "
                  f"{100*np.mean(np.array(rets) > 0):>9.1f}% {np.mean(base):>10.2f}")
    print("    (t-stat محسوب بعد طرح الانجراف غير المشروط؛ |t|<2 = لا دليل على تنبؤ)")

    # ── 2) حواجز ثلاثية: سوق / معكوس / Limit ──
    res = {"market": [], "flipped": [], "limit": []}
    sl_fracs, rr_list, fills, tried = [], [], 0, 0
    for s in signals:
        ad = assets[s.symbol]
        ci = int(s.close_idx)
        if ci + 2 >= len(ad.closes):
            continue
        side = 1 if s.action == "BUY" else -1
        d_sl = abs(s.price - s.sl)
        d_tp = abs(s.tp1 - s.price)
        if d_sl <= 0 or d_tp <= 0:
            continue
        rr_list.append(d_tp / d_sl)
        p0 = float(ad.closes[ci])
        sl_fracs.append(d_sl / s.price)

        r, _ = _triple_barrier(ad, ci, p0, d_sl, d_tp, side, ci + 1)
        if r is not None:
            res["market"].append(r)
        r, _ = _triple_barrier(ad, ci, p0, d_sl, d_tp, -side, ci + 1)
        if r is not None:
            res["flipped"].append(r)

        # Limit عند سعر النفق (كما تفعل الاستراتيجية)
        tried += 1
        lim = float(s.price)
        fill_k = None
        for k in range(ci + 1, min(ci + 1 + LIMIT_WAIT, len(ad.closes))):
            if (side > 0 and ad.lows[k] <= lim) or (side < 0 and ad.highs[k] >= lim):
                fill_k = k
                break
        if fill_k is not None:
            fills += 1
            # شمعة التعبئة نفسها: نفحص SL فقط (ترتيب اللمس مجهول → تحفظ)،
            # ثم نكمل من الشمعة التالية بالحاجز الكامل.
            _sl_px = lim - side * d_sl
            _fb_sl = (ad.lows[fill_k] <= _sl_px) if side > 0 else (ad.highs[fill_k] >= _sl_px)
            if _fb_sl:
                res["limit"].append(-1.0)
            else:
                r, _ = _triple_barrier(ad, ci, lim, d_sl, d_tp, side, fill_k + 1)
                if r is not None:
                    res["limit"].append(r)

    rr_mean = float(np.mean(rr_list)) if rr_list else 0.0
    base_wr = 1.0 / (1.0 + rr_mean) if rr_mean > 0 else 0.0
    print("\n[2] حواجز ثلاثية (SL/TP كما صمّمتها الاستراتيجية، قبل التكاليف)")
    print(f"    متوسط R:R = {rr_mean:.2f}  →  نسبة النجاح لو كان السوق عشوائياً = {100*base_wr:.1f}%")
    print(f"    {'السيناريو':<26}{'n':>7}{'نجاح%':>8}{'متوسط R':>9}{'t':>7}")
    names = {"market": "دخول سوقي باتجاه الإشارة",
             "flipped": "دخول سوقي عكس الإشارة",
             "limit": "Limit (كالاستراتيجية)"}
    for k in ("market", "flipped", "limit"):
        a = np.array(res[k])
        if len(a) == 0:
            continue
        wr = 100 * np.mean(a > 0)
        print(f"    {names[k]:<26}{len(a):>7}{wr:>8.1f}{a.mean():>9.3f}{_t_stat(a):>7.2f}")
    print(f"    نسبة تعبئة الـ Limit: {100*fills/max(tried,1):.1f}%")
    print("    تفسير: إن كان «باتجاه الإشارة» ≈ «عكسها» ≈ 0 → لا قدرة اتجاهية.")
    print("           وإن كان Limit أسوأ من السوقي → انتقاء عكسي في الدخول.")

    # ── 3) وزن التكاليف بوحدة R ──
    if sl_fracs:
        sl_f = float(np.median(sl_fracs))
        rt = cfg.MAKER_FEE + cfg.TAKER_FEE            # دخول Maker + خروج Taker (SL/TP)
        # انزلاق تقريبي: bps حسب السيولة (وحدة يومية) × 1 جهة
        slip = 0.0
        try:
            vals = [tm._taker_slippage_bps(float(np.mean(ad.adv_usd)) * 86400.0 /
                                            max(cfg.TF_SECONDS, 1)) for ad in assets.values()]
            slip = float(np.mean(vals)) * 1e-4
        except Exception:
            pass
        cost_frac = rt + slip
        print("\n[3] وزن التكاليف")
        print(f"    الوسيط لمسافة SL = {100*sl_f:.3f}% من السعر")
        print(f"    تكلفة الدورة (رسوم + انزلاق Taker) ≈ {100*cost_frac:.3f}%  =  {cost_frac/sl_f:.3f} R لكل صفقة")
        if res["market"]:
            g = float(np.mean(res["market"]))
            print(f"    متوسط R الإجمالي (سوقي) = {g:+.3f}  →  بعد التكاليف ≈ {g - cost_frac/sl_f:+.3f} R")
        print("    القاعدة: لازم تتجاوز الحافة الإجمالية التكلفة بالـ R، وإلا فالنتيجة سالبة حتماً.")
    print("=" * 72 + "\n")


# ── ربط بالباكتست: التقاط (signals, assets) ثم التشخيص ──
_orig_sim = tm.simulate_portfolio
_captured = {}


def _hook(signals, assets, corr_matrix, mode="backtest"):
    _captured["signals"] = list(signals)
    _captured["assets"] = assets
    return _orig_sim(signals, assets, corr_matrix, mode)


tm.simulate_portfolio = _hook

if __name__ == "__main__":
    try:
        tm.main()
    finally:
        if "signals" in _captured:
            diagnose(_captured["signals"], _captured["assets"])
