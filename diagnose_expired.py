#!/usr/bin/env python3
"""
diagnose_expired.py — Cost of signals rejected by the reversal filter.

For each signal, run _check_reversal_fill_simple and classify:
    - Accepted    (touch + bounce within windows)
    - No-touch    (price never returned to target)
    - No-bounce   (touch happened but no close on the correct side)

For no-touch signals, simulate what would have happened if we entered
at market (close of the first sub-bar after the signal).
For no-bounce signals, simulate entry at bounce-window expiry.

Reports win%, avg PnL, and median PnL for each alternative.

Usage:
    python3 diagnose_expired.py --history-days 730 --nassets 100
"""
import argparse
import numpy as np
import trading_2_live2_2 as core


def walk(ad, entry_main, entry_sub, entry_px, action, sl_dist, tp_dist, max_hold):
    sh = ad.sub_highs; sl = ad.sub_lows
    spm = int(ad.sub_per_main)
    n = sh.shape[0]

    if action == "BUY":
        sl_px = entry_px - sl_dist
        tp_px = entry_px + tp_dist
    else:
        sl_px = entry_px + sl_dist
        tp_px = entry_px - tp_dist

    m = entry_main
    s = entry_sub + 1
    while True:
        if s >= spm:
            s = 0
            m += 1
        if m >= n:
            break
        if (m - entry_main) > max_hold:
            break
        h = sh[m, s]; l = sl[m, s]
        if np.isfinite(h) and np.isfinite(l):
            if action == "BUY":
                if l <= sl_px: return "SL", sl_px
                if h >= tp_px: return "TP", tp_px
            else:
                if h >= sl_px: return "SL", sl_px
                if l <= tp_px: return "TP", tp_px
        s += 1
    return "MH", entry_px


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--history-days", type=int, default=730)
    ap.add_argument("--nassets", type=int, default=100)
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--touch-window", type=int, default=20)
    ap.add_argument("--bounce-window", type=int, default=4)
    ap.add_argument("--max-hold", type=int, default=30)
    a = ap.parse_args()

    import ccxt
    ex = ccxt.binance({'enableRateLimit': True,
                       'options': {'defaultType': 'future'}})
    cfg = core.CFG
    cfg.mode = "backtest"
    cfg.timeframe = a.timeframe
    cfg.INITIAL_CAPITAL = a.capital
    cfg.n_assets = a.nassets
    cfg.PO_FIXED_PRICE = False
    cfg.REVERSAL_CONFIRM_ENABLED = True
    cfg.REVERSAL_TOUCH_WINDOW = a.touch_window
    cfg.REVERSAL_BOUNCE_WINDOW = a.bounce_window
    cfg.SL_WIDEN_MULT = 0.7
    cfg.TP_MULT = 2.0

    cfg.TF_SCALE, cfg.TF_SECONDS, cfg.TF_HOURS = core.compute_tf_scale(
        ex, cfg.timeframe)
    _tfh = max(cfg.TF_HOURS, 1e-6)
    cfg.N = max(cfg.N, int(np.ceil(cfg.N_HOURS / _tfh)))
    cfg.W = max(cfg.W, int(np.ceil(cfg.W_HOURS / _tfh)))
    cfg.L = max(cfg.L, int(np.ceil(cfg.L_HOURS / _tfh)))
    cfg.ADV_BARS = max(1, int(round(cfg.ADV_HOURS / _tfh)))
    hd, *_ = core._resolve_data_params(cfg, "backtest", cfg.TF_HOURS,
                                       user_history_days=a.history_days)
    cfg.history_days = int(hd)

    syms = core._default_assets()[:cfg.n_assets]
    print(f"[Diag] {len(syms)} syms, {cfg.history_days}d, {a.timeframe}")

    raw, raw_sub = core.fetch_all_with_subbars(
        syms, ex, cfg.timeframe, cfg.history_days, workers=5)

    assets = {}
    for s, df in raw.items():
        ad = core.process_asset(s, df, current_capital=a.capital,
                                 sub_df=raw_sub.get(s) if raw_sub else None)
        if ad is not None:
            assets[s] = ad
    print(f"[Diag] {len(assets)} assets")

    sigs = core.build_signals(assets, mode="backtest")
    print(f"[Diag] {len(sigs)} signals")

    mh = int(core.effective_bars(a.max_hold))

    n_acc = 0; n_nt = 0; n_nb = 0
    alt_nt = []
    alt_nb = []
    accepted_ok = 0; accepted_bad = 0

    for sig in sigs:
        ad = assets.get(sig.symbol)
        if ad is None or ad.sub_highs is None: continue
        if ad.sub_per_main < 2: continue
        try:
            target0 = core._backtest_entry_target(sig, ad)
        except Exception:
            continue

        spm = int(ad.sub_per_main)
        sm = sig.close_idx + 1
        em = min(sig.close_idx + 1 + max(1, (a.touch_window +
                                              a.bounce_window) // spm + 1),
                 ad.sub_highs.shape[0])
        if em <= sm: continue

        sh = ad.sub_highs[sm:em].reshape(-1)
        sl = ad.sub_lows[sm:em].reshape(-1)
        sc = ad.sub_closes[sm:em].reshape(-1)
        nf = sh.size

        tk = -1
        for k in range(min(a.touch_window, nf)):
            if not (np.isfinite(sh[k]) and np.isfinite(sl[k])): continue
            if sig.action == "BUY" and sl[k] <= target0: tk = k; break
            if sig.action == "SELL" and sh[k] >= target0: tk = k; break

        if tk < 0:
            n_nt += 1
            if nf > 0:
                epx = float(sc[0])
                if np.isfinite(epx) and epx > 0:
                    sld = abs(sig.price - sig.sl)
                    tpd = abs(sig.tp1 - sig.price)
                    reason, expx = walk(ad, sm, 0, epx, sig.action,
                                         sld, tpd, mh)
                    pnl = ((expx - epx) / epx if sig.action == "BUY"
                           else (epx - expx) / epx)
                    alt_nt.append((reason, pnl))
            continue

        ck = -1
        b0 = tk + 1
        b1 = min(b0 + a.bounce_window, nf)
        for k in range(b0, b1):
            c = sc[k]
            if not np.isfinite(c): continue
            if sig.action == "BUY" and c > target0: ck = k; break
            if sig.action == "SELL" and c < target0: ck = k; break

        if ck < 0:
            n_nb += 1
            ek = min(tk + 1 + a.bounce_window, nf - 1)
            if ek >= 0:
                epx = float(sc[ek])
                if np.isfinite(epx) and epx > 0:
                    sld = abs(sig.price - sig.sl)
                    tpd = abs(sig.tp1 - sig.price)
                    em_main = sm + ek // spm
                    em_sub = ek % spm
                    reason, expx = walk(ad, em_main, em_sub, epx,
                                         sig.action, sld, tpd, mh)
                    pnl = ((expx - epx) / epx if sig.action == "BUY"
                           else (epx - expx) / epx)
                    alt_nb.append((reason, pnl))
            continue

        n_acc += 1

    print(f"\n[Diag] Filter outcomes:")
    total = n_acc + n_nt + n_nb
    print(f"  Total signals: {total}")
    print(f"  Accepted:      {n_acc}  ({n_acc/max(total,1)*100:.1f}%)")
    print(f"  No-touch:      {n_nt}  ({n_nt/max(total,1)*100:.1f}%)")
    print(f"  No-bounce:     {n_nb}  ({n_nb/max(total,1)*100:.1f}%)")

    def report(name, lst):
        if not lst:
            print(f"\n[Diag] {name}: no data")
            return
        reasons = [r for r, _ in lst]
        pnls = np.array([p for _, p in lst])
        tp = reasons.count("TP"); sl = reasons.count("SL"); mh = reasons.count("MH")
        print(f"\n[Diag] {name}:")
        print(f"  n={len(pnls)}  TP={tp}  SL={sl}  MH={mh}")
        print(f"  win%={tp/len(pnls)*100:.1f}%  "
              f"μPnL={pnls.mean()*100:+.3f}%  "
              f"median={np.median(pnls)*100:+.3f}%  "
              f"std={pnls.std()*100:.3f}%")

    report("No-touch: alt entry at signal+1", alt_nt)
    report("No-bounce: alt entry at bounce-expiry", alt_nb)


if __name__ == "__main__":
    main()
