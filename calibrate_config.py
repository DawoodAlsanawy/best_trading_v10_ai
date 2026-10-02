#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
calibrate_config.py — معايرة إعدادات trading_medum_fixed.py بدون الإفراط في التوفيق.

الاستخدام (نفس وسائط الباكتست المعتادة + وسائط المعايرة):
    python calibrate_config.py --mode backtest --timeframe 4h --history-days 730 \
        --nassets 15 --trials 150 --seed 7

المنهج:
  1) يشغّل خط الأنابيب مرة واحدة (جلب + معالجة الأصول) ويلتقط assets/corr ثم يتوقف.
  2) يقسّم فترة الاختبار زمنياً: 75% للبحث، 25% أخيرة "حجز نهائي" لا تُمسّ أثناء البحث.
  3) كل تجربة = توليد إشارات + محاكاة كاملة، ثم تُقسَّم صفقات فترة البحث إلى 4 كتل زمنية.
     الهدف = متوسط t-stat الكتل − 0.5×الانحراف بينها (يكافئ الاستقرار لا القمة الواحدة)،
     مع عقوبة إن قلّت الصفقات عن الحد الأدنى في أي كتلة.
  4) بحث عشوائي ثم تحسين محلي (تحويرات حول الأفضل). بعدها فحص جيران (±خطوة) للمتانة.
  5) تقييم الأفضل والافتراضي على الحجز النهائي، وكتابة calibrated_overrides.json.
     طبّقه بـ:  python trading_medum_fixed.py ... --config-json calibrated_overrides.json
تحذير: المعايرة لا تصنع حافة غير موجودة. اعتمد النتيجة فقط إذا كان الحجز النهائي موجباً
وقريباً من نتيجة البحث. وإلا فالأفضل ترك الإعدادات الافتراضية.
"""
import sys, os, json, math, time, copy, random, argparse, importlib.util, logging
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("tm", os.path.join(HERE, "trading_medum_fixed3.py"))
tm = importlib.util.module_from_spec(spec); sys.modules["tm"] = tm
spec.loader.exec_module(tm)
CFG = tm.CFG

# ── وسائط المعايرة تُستخرج قبل تمرير الباقي لـ main() ──
_ap = argparse.ArgumentParser(add_help=False)
_ap.add_argument("--trials", type=int, default=150)
_ap.add_argument("--seed", type=int, default=7)
_ap.add_argument("--min-block-trades", type=int, default=25)
_ap.add_argument("--holdout", type=float, default=0.25)
_ap.add_argument("--out", default="calibrated_overrides.json")
_cal, _rest = _ap.parse_known_args()
sys.argv = [sys.argv[0]] + _rest

# ── فضاء البحث: فقط ما يؤثر بعد معالجة الأصول (لا يحتاج إعادة تدريب KMeans) ──
# (النوع، الحد الأدنى، الحد الأعلى، الخطوة)
SPACE = {
    "MIN_SCORE":              ("int",   3,   10,  1),
    "FRICTION_DIP_KAPPA":     ("float", 0.5, 4.0, 0.25),
    "HORIZON_BARS":           ("int",   6,   36,  3),
    "TP_MULT":                ("float", 3.0, 10.0, 0.5),
    "MIN_TP_COST_MULT":       ("float", 2.0, 6.0, 0.5),
    "SL_MIN_SIGMA":           ("float", 1.0, 4.0, 0.5),
    "SL_MAX_SIGMA":           ("float", 4.0, 8.0, 0.5),
    "SL_REF_KAPPA":           ("float", 1.0, 4.0, 0.5),
    "CORRELATION_THRESHOLD":  ("float", 0.3, 0.9, 0.1),
    "MAX_CONCURRENT_ASSETS":  ("int",   2,   8,   1),
}
KEYS = list(SPACE)


def _snap(k, v):
    t, lo, hi, st = SPACE[k]
    v = min(max(v, lo), hi)
    v = lo + round((v - lo) / st) * st
    v = min(max(v, lo), hi)
    return int(round(v)) if t == "int" else round(float(v), 4)


def _rand_params(rng):
    return {k: _snap(k, rng.uniform(SPACE[k][1], SPACE[k][2])) for k in KEYS}


def _mutate(p, rng, strength=0.25):
    q = dict(p)
    for k in rng.sample(KEYS, rng.randint(1, 3)):
        t, lo, hi, st = SPACE[k]
        q[k] = _snap(k, q[k] + rng.gauss(0, strength * (hi - lo)))
    return q


def _fix(p):
    p = dict(p)
    if p["SL_MAX_SIGMA"] < p["SL_MIN_SIGMA"] + 1.0:
        p["SL_MAX_SIGMA"] = min(8.0, p["SL_MIN_SIGMA"] + 1.0)
    return p


def _apply(p):
    for k, v in p.items():
        setattr(CFG, k, v)
    CFG.HORIZON_EXIT_ENABLED = True
    CFG.PARTIAL_TP_ENABLED = False
    CFG.BREAKEVEN_ENABLED = False


def _tstat(x):
    x = np.asarray(x, float)
    if len(x) < 3: return 0.0
    s = np.std(x, ddof=1)
    return 0.0 if s < 1e-12 else float(np.mean(x) / (s / math.sqrt(len(x))))


class Ctx:
    assets = None; corr = None; t0 = None; t1 = None; cut = None


def _signals_for(p):
    _apply(p)
    tm._filter_reset_stats()
    sigs = tm.deduplicate_signals(tm.build_signals(Ctx.assets))
    if CFG.RULE_FILTER_ENABLED:
        tm.compute_rule_thresholds(Ctx.assets)
        sigs = tm.filter_signals_rules(sigs, Ctx.assets)
    if CFG.ML_FILTER_ENABLED:
        sigs = tm.filter_signals_ml(sigs, Ctx.assets)
    return sigs


def _run(p, upto=None):
    """يعيد الصفقات (مرتبة زمنياً). upto: يقصّ الإشارات عند هذا الوقت (للبحث)."""
    sigs = _signals_for(p)
    if upto is not None:
        sigs = [s for s in sigs if pd.Timestamp(s.timestamp) <= upto]
    if len(sigs) < 10:
        return []
    trades, _ = tm.simulate_portfolio(sigs, Ctx.assets, Ctx.corr, "backtest")
    return sorted(trades, key=lambda t: pd.Timestamp(t.entry_time))


def _blocks(trades, t0, t1, nb=4):
    edges = [t0 + (t1 - t0) * i / nb for i in range(nb + 1)]
    out = [[] for _ in range(nb)]
    for t in trades:
        ts = pd.Timestamp(t.entry_time)
        for i in range(nb):
            if edges[i] <= ts <= edges[i + 1]:
                out[i].append(t.log_return); break
    return out


def score_params(p, min_block):
    try:
        tr = _run(p, upto=Ctx.cut)
    except Exception as e:
        return -99.0, {"err": repr(e)[:80]}
    blocks = _blocks(tr, Ctx.t0, Ctx.cut)
    ts = []
    for b in blocks:
        ts.append(_tstat(b) if len(b) >= min_block else -3.0)
    sc = float(np.mean(ts) - 0.5 * np.std(ts))
    allr = [t.log_return for t in tr]
    info = {"n": len(tr), "block_t": [round(x, 2) for x in ts],
            "mean_lr": float(np.mean(allr)) if allr else 0.0}
    return sc, info


def summarize(trades, t_from=None):
    tr = [t for t in trades if t_from is None or pd.Timestamp(t.entry_time) > t_from]
    if not tr: return {"n": 0}
    lr = np.array([t.log_return for t in tr]); pn = np.array([t.net_pnl for t in tr])
    w = pn[pn > 0].sum(); l = -pn[pn <= 0].sum()
    return {"n": len(tr), "mean_lr_bps": round(float(lr.mean()) * 1e4, 1), "t": round(_tstat(lr), 2),
            "win%": round(100 * float((pn > 0).mean()), 1), "PF": round(float(w / l), 2) if l > 0 else float("inf"),
            "sum_lr": round(float(lr.sum()), 3)}


def calibrate():
    rng = random.Random(_cal.seed)
    tm.log.setLevel(logging.WARNING)
    default = {k: getattr(CFG, k, SPACE[k][1]) for k in KEYS}
    default["HORIZON_BARS"] = int(getattr(CFG, "HORIZON_BARS", 24))
    default["TP_MULT"] = float(getattr(CFG, "TP_MULT", 6.0))
    default = _fix({k: _snap(k, v) for k, v in default.items()})

    starts = [pd.Timestamp(ad.timestamps[ad.train_end]) for ad in Ctx.assets.values()]
    ends = [pd.Timestamp(ad.timestamps[-1]) for ad in Ctx.assets.values()]
    Ctx.t0, Ctx.t1 = min(starts), max(ends)
    Ctx.cut = Ctx.t0 + (Ctx.t1 - Ctx.t0) * (1.0 - _cal.holdout)
    print(f"\n[Calib] فترة الاختبار {Ctx.t0.date()} → {Ctx.t1.date()} | بحث حتى {Ctx.cut.date()} | حجز نهائي بعده")

    results = []
    def evaluate(p):
        p = _fix(p)
        sc, info = score_params(p, _cal.min_block_trades)
        results.append((sc, p, info)); return sc

    sc0 = evaluate(default)
    print(f"[Calib] الافتراضي: score={sc0:+.3f}")
    n_rand = max(10, int(_cal.trials * 0.4))
    t_start = time.time()
    for i in range(_cal.trials):
        if i < n_rand or not results:
            p = _rand_params(rng)
        else:
            top = sorted(results, key=lambda r: -r[0])[:5]
            p = _mutate(rng.choice(top)[1], rng, 0.2 if i > _cal.trials * 0.75 else 0.3)
        sc = evaluate(p)
        if (i + 1) % 10 == 0:
            best = max(results, key=lambda r: r[0])
            print(f"  [{i+1:>4}/{_cal.trials}] أفضل score={best[0]:+.3f}  ({time.time()-t_start:.0f}s)")

    results.sort(key=lambda r: -r[0])
    print("\n[Calib] أفضل 5 تجارب (فترة البحث):")
    for sc, p, info in results[:5]:
        print(f"  {sc:+.3f} n={info.get('n')} blocks={info.get('block_t')}  {p}")

    # ── متانة: جيران الأفضل ──
    best_sc, best_p, _ = results[0]
    nb = [score_params(_fix(_mutate(best_p, rng, 0.08)), _cal.min_block_trades)[0] for _ in range(8)]
    robust = float(np.median(nb))
    print(f"\n[Calib] متانة: score الأفضل={best_sc:+.3f} | وسيط الجيران={robust:+.3f}")
    if robust < 0.5 * best_sc:
        print("  ⚠ الأفضل قمة معزولة (تضخّم احتمالي) — فضّل مجموعة أكثر استقراراً أو الافتراضي.")
        # اختر أفضل تجربة ضمن أول 10 بأعلى متانة
        cand = []
        for sc, p, _ in results[:10]:
            m = float(np.median([score_params(_fix(_mutate(p, rng, 0.08)), _cal.min_block_trades)[0] for _ in range(5)]))
            cand.append((min(sc, m), p))
        cand.sort(key=lambda r: -r[0]); best_p = cand[0][1]
        print(f"  اختير الأكثر متانة: {best_p}")

    # ── الحجز النهائي ──
    print("\n[Calib] الحجز النهائي (بيانات لم تُستخدم في البحث):")
    out = {}
    for name, p in (("default", default), ("calibrated", best_p)):
        tr = _run(_fix(p))
        s_all = summarize(tr)
        s_ho = summarize(tr, t_from=Ctx.cut)
        out[name] = s_ho
        print(f"  {name:>10}: بحث+حجز {s_all}\n  {'':>10}  حجز فقط {s_ho}")
    ho_c, ho_d = out["calibrated"], out["default"]
    ok = ho_c.get("n", 0) >= 30 and ho_c.get("mean_lr_bps", -1) > 0 and ho_c.get("t", 0) > 1.0 \
         and ho_c.get("mean_lr_bps", 0) >= ho_d.get("mean_lr_bps", -1e9)
    print("\n[Calib] القرار:", "اعتمد الإعدادات المعايرة ✔" if ok else
          "لا تعتمد — لم تتفوق بوضوح على الحجز النهائي (ابقِ الافتراضي أو لا تتداول).")

    json.dump({"params": _fix(best_p), "accepted": bool(ok), "holdout": out,
               "search_range": [str(Ctx.t0), str(Ctx.cut)]}, open(_cal.out, "w"), indent=2, default=str)
    print(f"[Calib] كُتب الملف: {_cal.out}")
    print("  CFG patch:\n   " + "\n   ".join(f"CFG.{k} = {v}" for k, v in _fix(best_p).items()))


class _Stop(Exception): pass

_orig_sim = tm.simulate_portfolio
def _capture(signals, assets, corr_matrix, mode="backtest"):
    Ctx.assets, Ctx.corr = assets, corr_matrix
    raise _Stop()
tm.simulate_portfolio = _capture

if __name__ == "__main__":
    try:
        tm.main()
    except _Stop:
        pass
    tm.simulate_portfolio = _orig_sim
    if Ctx.assets is None:
        print("لم تُلتقط بيانات — تأكد من وسائط الباكتست."); sys.exit(1)
    calibrate()
