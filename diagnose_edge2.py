#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diagnose_edge2.py — تشخيص موسّع (بعد التكاليف) لقرار أفق الخروج والاتجاه.
الاستخدام:  python diagnose_edge2.py --mode backtest [نفس الوسائط]
لا يغيّر الاستراتيجية. يطبع:
 [A] صافي العائد بعد التكاليف لخروج زمني عند آفاق 6..48 (BUY/SELL منفصلين)
 [B] استقرار النصف الأول مقابل الثاني من التاريخ لكل أصل
 [C] متغيرات الاتجاه: إشارة البوت / عكسها / محاذاة EMA200 / عائد k شمعة
"""
import sys, importlib.util, os
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
_t = os.path.join(HERE, "trading_medum_fixed3.py")
spec = importlib.util.spec_from_file_location("tm", _t)
tm = importlib.util.module_from_spec(spec); sys.modules["tm"] = tm
spec.loader.exec_module(tm)

HZ = (6, 12, 18, 24, 36, 48)


def _t(x):
    x = np.asarray(x, float)
    if len(x) < 3 or np.std(x, ddof=1) == 0: return 0.0
    return float(np.mean(x) / (np.std(x, ddof=1) / np.sqrt(len(x))))


def _ema(c, span):
    a = 2.0 / (span + 1); out = np.empty_like(c); out[0] = c[0]
    for i in range(1, len(c)): out[i] = a * c[i] + (1 - a) * out[i - 1]
    return out


def _cost_bps(side, h, cfg, tf_sec):
    c = (cfg.MAKER_FEE + cfg.TAKER_FEE) * 1e4          # دخول Maker + خروج Taker
    c += 2.0                                            # انزلاق تقريبي محافظ
    if side > 0:                                        # تمويل للشراء فقط (تحفظ)
        c += (h * tf_sec / 28800.0) * 1.0               # ~1bp لكل فترة تمويل 8h
    return c


def _ret(ad, ci, h, side):
    if ci + h >= len(ad.closes): return None
    return side * np.log(ad.closes[ci + h] / ad.closes[ci]) * 1e4


def diagnose(signals, assets):
    cfg = tm.CFG; tf = max(cfg.TF_SECONDS, 1)
    print("\n" + "=" * 72 + "\n  تشخيص موسّع (صافي بعد التكاليف)\n" + "=" * 72)
    print(f"  إشارات: {len(signals):,}")

    print("\n[A] صافي bps لخروج زمني — حسب الاتجاه")
    print(f"    {'أفق':>5} {'جهة':>5} {'N':>6} {'صافي bps':>10} {'t':>6} {'نجاح%':>7}")
    for h in HZ:
        for name, sd in (("BUY", 1), ("SELL", -1)):
            r = []
            for s in signals:
                if s.action != name: continue
                v = _ret(assets[s.symbol], int(s.close_idx), h, sd)
                if v is not None: r.append(v - _cost_bps(sd, h, cfg, tf))
            if r:
                print(f"    {h:>5} {name:>5} {len(r):>6} {np.mean(r):>+10.1f} {_t(r):>6.2f} {100*np.mean(np.array(r)>0):>6.1f}")

    print("\n[B] استقرار زمني (أفق 24، صافي) — النصف الأول مقابل الثاني")
    for half, lab in ((0, "النصف الأول"), (1, "النصف الثاني")):
        r = []
        for s in signals:
            ad = assets[s.symbol]; ci = int(s.close_idx)
            if (ci >= len(ad.closes) // 2) != bool(half): continue
            sd = 1 if s.action == "BUY" else -1
            v = _ret(ad, ci, 24, sd)
            if v is not None: r.append(v - _cost_bps(sd, 24, cfg, tf))
        if r: print(f"    {lab:>14}: N={len(r):>5}  صافي={np.mean(r):+7.1f} bps  t={_t(r):5.2f}")

    print("\n[C] متغيرات الاتجاه (أفق 24، صافي)")
    ema_cache = {}
    variants = {"إشارة البوت": [], "عكس الإشارة": [], "EMA200 محاذٍ فقط": [],
                "عائد 6 شمعات": [], "عائد 24 شمعة": []}
    for s in signals:
        ad = assets[s.symbol]; ci = int(s.close_idx)
        if ci < 200 or ci + 24 >= len(ad.closes): continue
        e = ema_cache.setdefault(s.symbol, _ema(np.asarray(ad.closes, float), 200))
        base = 1 if s.action == "BUY" else -1
        fwd = lambda sd: _ret(ad, ci, 24, sd) - _cost_bps(sd, 24, cfg, tf)
        variants["إشارة البوت"].append(fwd(base))
        variants["عكس الإشارة"].append(fwd(-base))
        if (ad.closes[ci] > e[ci]) == (base > 0):
            variants["EMA200 محاذٍ فقط"].append(fwd(base))
        for k, key in ((6, "عائد 6 شمعات"), (24, "عائد 24 شمعة")):
            sd = 1 if ad.closes[ci] > ad.closes[ci - k] else -1
            variants[key].append(fwd(sd))
    for k, v in variants.items():
        if v: print(f"    {k:>18}: N={len(v):>5}  صافي={np.mean(v):+7.1f} bps  t={_t(v):5.2f}")
    print("\n  القاعدة: لا تعتمد إلا ما كان صافيه موجباً وt>2 في النصفين معاً.")
    print("=" * 72 + "\n")


_orig = tm.simulate_portfolio
_cap = {}


def _hook(signals, assets, corr_matrix, mode="backtest"):
    _cap["s"] = list(signals); _cap["a"] = assets
    return _orig(signals, assets, corr_matrix, mode)


tm.simulate_portfolio = _hook

if __name__ == "__main__":
    try:
        tm.main()
    finally:
        if "s" in _cap: diagnose(_cap["s"], _cap["a"])
