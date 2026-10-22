#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_live_backtest.py

يستخرج صفقات الـ Live/Testnet من آخر 48 ساعة عبر Binance API،
ويشغّل الـ Backtest بنفس رأس المال الصغير ($2)، ثم يقارن:
  - عدد الصفقات
  - العمولات الفعلية vs النموذجية
  - الانزلاقات الفعلية vs النموذجية
  - الأداء (PnL، Win Rate، Sharpe)

Usage:
    python compare_live_backtest.py --mode testnet --hours 48 --capital 2
    python compare_live_backtest.py --mode live    --hours 48 --capital 2
"""
import argparse, json, os, sys, time
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# 1) استخراج الصفقات من البورصة
# ═══════════════════════════════════════════════════════════════
def fetch_live_trades(exchange, hours: int = 48) -> pd.DataFrame:
    """يجلب كل الـ fills من آخر N ساعة عبر fetch_my_trades."""
    since_ms = int((time.time() - hours * 3600) * 1000)
    print(f"[Live] Fetching trades since {datetime.fromtimestamp(since_ms/1000, tz=timezone.utc)}")

    # 1. جلب كل الرموز
    try:
        positions_hist = exchange.fetch_positions()
    except Exception:
        positions_hist = []
    try:
        bal = exchange.fetch_balance()
        assets = [a for a in bal.get("total", {}) if bal["total"][a] and bal["total"][a] > 0]
    except Exception:
        assets = []

    # 2. جلب الرموز المتداولة (من الماركتس + آخر الصفقات)
    symbols = set()
    try:
        all_mkts = exchange.load_markets()
        # نفحص فقط أزواج USDT-M Futures
        for s, m in all_mkts.items():
            if m.get("swap") and m.get("quote") == "USDT" and m.get("linear"):
                symbols.add(s)
    except Exception as e:
        print(f"[Live] load_markets failed: {e}")
        return pd.DataFrame()

    # نحدد الأصول التي لها نشاط (له رصيد أو مركز أو fill)
    active = set()
    for s in symbols:
        base = s.split("/")[0]
        if base in assets:
            active.add(s)
    for p in positions_hist:
        if abs(float(p.get("info", {}).get("positionAmt", 0) or 0)) > 0:
            s = p.get("symbol", "")
            s = s.split(":")[0] if ":" in s else s
            active.add(s)

    # نوسّع: إذا لم نجد نشاط، نستعرض آخر 20 رمزاً شائعاً
    if not active:
        common = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
                  "BNB/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT",
                  "ADA/USDT:USDT", "AVAX/USDT:USDT", "LINK/USDT:USDT",
                  "DOT/USDT:USDT"]
        for s in common:
            if s in symbols:
                active.add(s)

    print(f"[Live] Scanning {len(active)} symbols...")
    all_fills = []
    for sym in active:
        try:
            trades = exchange.fetch_my_trades(sym, since=since_ms, limit=1000)
            for t in trades or []:
                all_fills.append({
                    "symbol":       sym.split(":")[0],
                    "timestamp":    int(t.get("timestamp") or 0),
                    "datetime":     t.get("datetime"),
                    "side":         t.get("side"),
                    "price":        float(t.get("price") or 0),
                    "amount":       float(t.get("amount") or 0),
                    "cost":         float(t.get("cost") or 0),
                    "fee_cost":     float((t.get("fee") or {}).get("cost") or 0),
                    "fee_currency": (t.get("fee") or {}).get("currency"),
                    "order_id":     t.get("order"),
                    "is_maker":     t.get("info", {}).get("maker", None),
                })
        except Exception as e:
            print(f"[Live] {sym} fetch_my_trades failed: {e}")
        time.sleep(0.15)  # rate limit

    df = pd.DataFrame(all_fills)
    if df.empty:
        print("[Live] No fills found in the last 48h.")
        return df
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    print(f"[Live] Found {len(df)} fills across {df['symbol'].nunique()} symbols.")
    return df


# ═══════════════════════════════════════════════════════════════
# 2) تحليل العمولات والانزلاق من الـ Live
# ═══════════════════════════════════════════════════════════════
def analyze_live_fees_slips(df: pd.DataFrame, entry_ref_prices: dict) -> dict:
    """
    يحلل كل fill:
      - العمولة (fee_cost / cost)
      - النوع (maker/taker) — تقديري من is_maker
      - الانزلاق (price vs entry_ref)
    """
    if df.empty:
        return {}
    df = df.copy()
    df["fee_bps"] = (df["fee_cost"] / df["cost"].clip(lower=1e-9)) * 1e4

    maker_fills = df[df["is_maker"] == True]  if "is_maker" in df else pd.DataFrame()
    taker_fills = df[df["is_maker"] == False] if "is_maker" in df else pd.DataFrame()

    slips_bps = []
    for _, row in df.iterrows():
        ref = entry_ref_prices.get(row["symbol"])
        if ref is None or ref <= 0:
            continue
        # الانزلاق النسبي عن المرجع (sign حسب الاتجاه)
        if row["side"] == "buy":
            slip = (row["price"] - ref) / ref * 1e4
        else:
            slip = (ref - row["price"]) / ref * 1e4
        slips_bps.append(slip)

    out = {
        "n_fills":        len(df),
        "n_symbols":      int(df["symbol"].nunique()),
        "total_cost":     float(df["cost"].sum()),
        "total_fee":      float(df["fee_cost"].sum()),
        "avg_fee_bps":    float(df["fee_bps"].mean()),
        "median_fee_bps": float(df["fee_bps"].median()),
        "n_maker":        int(len(maker_fills)),
        "n_taker":        int(len(taker_fills)),
        "pct_maker":      float(len(maker_fills) / max(len(df), 1) * 100),
        "avg_slip_bps":   float(np.mean(slips_bps)) if slips_bps else 0.0,
        "median_slip_bps": float(np.median(slips_bps)) if slips_bps else 0.0,
        "n_slip_valid":   len(slips_bps),
    }
    return out


# ═══════════════════════════════════════════════════════════════
# 3) تحليل صفقات الـ Backtest
# ═══════════════════════════════════════════════════════════════
def load_backtest_trades(mode: str = "backtest") -> pd.DataFrame:
    """يقرأ trades_log_<mode>.jsonl."""
    path = f"trades_log_{mode}.jsonl"
    if not os.path.exists(path):
        print(f"[Backtest] {path} not found.")
        return pd.DataFrame()
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("_meta"):
                continue
            rows.append(r)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    print(f"[Backtest] Loaded {len(df)} trades from {path}")
    return df


def analyze_backtest_trades(df: pd.DataFrame) -> dict:
    """يحلل العمولات والانزلاقات من الـ backtest."""
    if df.empty:
        return {}
    fees = []
    slips = []
    for _, r in df.iterrows():
        ep = float(r.get("entry_price", 0))
        qty = float(r.get("pos_size", 0))
        cost = ep * qty
        if cost <= 0:
            continue
        # في الباكتيست: MAKER + TAKER على الدخول والخروج
        # الدخول: MAKER = 0.02%، الخروج: TAKER = 0.05% (خروج طارئ)
        # لكن الباكتيست يحسب بالفعل داخل _close
        net = float(r.get("net_pnl", 0))
        gross = float(r.get("gross_pnl", 0))
        fee_est = gross - net
        if cost > 0:
            fees.append(abs(fee_est) / cost * 1e4)
        # انزلاق: في الباكتيست = 0 للمـ maker، صغير للتاكر
        # لكن signal_price و entry_price قد يختلفان بسبب offset
        sp = float(r.get("signal_price", 0))
        if sp > 0:
            if r.get("action") == "BUY":
                slip = (ep - sp) / sp * 1e4
            else:
                slip = (sp - ep) / sp * 1e4
            slips.append(slip)

    out = {
        "n_trades":       len(df),
        "n_wins":         int((df["is_win"] == True).sum()) if "is_win" in df else 0,
        "win_rate_pct":   float((df["is_win"] == True).mean() * 100) if "is_win" in df else 0.0,
        "avg_fee_bps":    float(np.mean(fees)) if fees else 0.0,
        "median_fee_bps": float(np.median(fees)) if fees else 0.0,
        "avg_slip_bps":   float(np.mean(slips)) if slips else 0.0,
        "median_slip_bps": float(np.median(slips)) if slips else 0.0,
        "total_pnl":      float(df["net_pnl"].sum()) if "net_pnl" in df else 0.0,
        "final_cap":      float(df["capital_after"].iloc[-1]) if "capital_after" in df else 0.0,
    }
    return out


# ═══════════════════════════════════════════════════════════════
# 4) جدول المقارنة
# ═══════════════════════════════════════════════════════════════
def print_comparison(live: dict, bt: dict, capital: float):
    print("\n" + "═" * 78)
    print(f"  📊  مقارنة Live vs Backtest  (capital = ${capital:.2f})")
    print("═" * 78)

    if not live or not bt:
        print("  ⚠️  بيانات ناقصة — لا يمكن المقارنة")
        return

    print(f"\n{'المؤشر':<35}{'Live':>18}{'Backtest':>18}")
    print("─" * 72)

    def row(label, lv, bv, fmt="{:>18.4f}"):
        lvs = fmt.format(lv) if lv is not None else "—".rjust(18)
        bvs = fmt.format(bv) if bv is not None else "—".rjust(18)
        print(f"{label:<35}{lvs}{bvs}")

    # عدد الصفقات
    row("عدد الـ fills / trades",
        live.get("n_fills"), bt.get("n_trades"), "{:>18d}")

    # العمولات
    row("متوسط العمولة (bps)",
        live.get("avg_fee_bps"), bt.get("avg_fee_bps"))
    row("وسيط العمولة (bps)",
        live.get("median_fee_bps"), bt.get("median_fee_bps"))

    # الانزلاق
    row("متوسط الانزلاق (bps)",
        live.get("avg_slip_bps"), bt.get("avg_slip_bps"))
    row("وسيط الانزلاق (bps)",
        live.get("median_slip_bps"), bt.get("median_slip_bps"))

    # النوع
    if live.get("n_maker") is not None:
        print(f"\n{'─ Live maker/taker':<35}"
              f"  maker={live.get('n_maker',0)}  "
              f"taker={live.get('n_taker',0)}  "
              f"({live.get('pct_maker',0):.1f}% maker)")

    # الأداء
    if "total_pnl" in bt:
        row("إجمالي PnL (Backtest)", None, bt["total_pnl"],
            "{:>18.4f}$")

    # Win Rate
    row("Win Rate %", None, bt.get("win_rate_pct"), "{:>18.2f}")

    # التوصيات
    print("\n" + "─" * 72)
    print("  🎯 التوصيات:")
    if live.get("avg_fee_bps") is not None:
        live_fee = live["avg_fee_bps"]
        bt_fee = bt.get("avg_fee_bps", 0)
        if live_fee > bt_fee * 1.5:
            print(f"     ⚠️  عمولة Live ({live_fee:.2f} bps) أعلى من "
                  f"Backtest ({bt_fee:.2f} bps) — راجع نوع الأوامر")
        else:
            print(f"     ✅ العمولات متقاربة ({live_fee:.2f} vs {bt_fee:.2f})")

    if live.get("avg_slip_bps") is not None:
        live_slip = live["avg_slip_bps"]
        bt_slip = bt.get("avg_slip_bps", 0)
        if abs(live_slip - bt_slip) > 5:
            print(f"     ⚠️  الانزلاق: Live {live_slip:.2f} bps vs "
                  f"Backtest {bt_slip:.2f} bps")
        else:
            print(f"     ✅ الانزلاق متقارب ({live_slip:.2f} vs {bt_slip:.2f})")

    print("═" * 78 + "\n")


# ═══════════════════════════════════════════════════════════════
# 5) استخراج entry reference prices من trades log
# ═══════════════════════════════════════════════════════════════
def build_entry_ref_from_log(mode: str) -> dict:
    """
    يقرأ trades_log_<mode>.jsonl ويبني {symbol: signal_price}
    لاستخدامه كمرجع لحساب الانزلاق.
    """
    path = f"trades_log_{mode}.jsonl"
    refs = {}
    if not os.path.exists(path):
        return refs
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("_meta"):
                continue
            sym = r.get("symbol")
            sp = r.get("signal_price") or r.get("entry_price")
            if sym and sp:
                refs[sym] = float(sp)
    return refs


# ═══════════════════════════════════════════════════════════════
# 6) تشغيل Backtest برأس مال صغير
# ═══════════════════════════════════════════════════════════════
def run_small_capital_backtest(capital: float, mode_out: str = "small_cap") -> None:
    """يشغّل البوت بـ --mode backtest --capital X مع log مختلف."""
    import subprocess
    cmd = [
        sys.executable, "trading_2_live4.py",
        "--mode", "backtest",
        "--capital", str(capital),
        "--timeframe", "1h",
        "--history-days", "30",
        "--nassets", "100",
        "--maxcon", "1",
        "--workers", "1",
        "--no-fixed-price",
        "--no-trailing",
        "--enable-sell",
        "--sell-gauge-pct", "85",
        "--tp-mult", "7",
        "--sl-widen-mult", "0.15",
        "--no-apex",
        "--partial-tp-r", "7",
        "--reversal-confirm",
        "--reversal-mode", "sigma_bounce",
        "--reversal-kappa", "0.8",
        "--reversal-touch-subbars", "20",
        "--reversal-bounce-subbars", "20",
        "--trade-log", f"trades_log_{mode_out}.jsonl",
    ]
    print(f"[BT] Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=False, timeout=1800)
    except Exception as e:
        print(f"[BT] Backtest failed: {e}")


# ═══════════════════════════════════════════════════════════════
# 7) main
# ═══════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="testnet",
                    choices=["testnet", "live"])
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--capital", type=float, default=2.0)
    ap.add_argument("--skip-backtest", action="store_true",
                    help="Skip running backtest; use existing trade log")
    ap.add_argument("--api-key", default=os.environ.get("BINANCE_TESTNET_KEY", ""))
    ap.add_argument("--api-secret", default=os.environ.get("BINANCE_TESTNET_SECRET", ""))
    a = ap.parse_args()

    # 1. الاتصال بالبورصة
    try:
        import ccxt
    except ImportError:
        print("[ERR] pip install ccxt")
        return
    ex = ccxt.binance({
        "apiKey": a.api_key,
        "secret": a.api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })
    if a.mode == "testnet":
        ex.enable_demo_trading(True)

    # 2. تحقق من الاتصال
    try:
        ex.fetch_time()
        print("[Live] Connected.")
    except Exception as e:
        print(f"[Live] Connection failed: {e}")
        return

    # 3. جلب fills من آخر N ساعة
    live_df = fetch_live_trades(ex, hours=a.hours)

    # 4. مرجع الانزلاق = signal_price من trades log
    entry_refs = build_entry_ref_from_log(a.mode)
    print(f"[Ref] {len(entry_refs)} symbols in trade log for slip reference")

    # 5. تحليل Live
    live_stats = analyze_live_fees_slips(live_df, entry_refs) if not live_df.empty else {}

    # 6. تشغيل الباكتيست برأس مال صغير
    if not a.skip_backtest:
        run_small_capital_backtest(a.capital, mode_out="small_cap")
        bt_stats = analyze_backtest_trades(load_backtest_trades("small_cap"))
    else:
        bt_stats = analyze_backtest_trades(load_backtest_trades("small_cap"))

    # 7. مقارنة
    print_comparison(live_stats, bt_stats, a.capital)

    # 8. حفظ raw data
    if not live_df.empty:
        out = f"live_fills_{a.mode}_{int(time.time())}.csv"
        live_df.to_csv(out, index=False)
        print(f"[Save] Live fills → {out}")


if __name__ == "__main__":
    main()
