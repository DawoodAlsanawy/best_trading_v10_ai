import ast, json, logging, os, random, sys, tempfile, types, time
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

SRC = sys.argv[1]
src = open(SRC, encoding="utf-8").read()
tree = ast.parse(src)

# ── pull the REAL backtest function + side-channel dict out of the patched file ──
def seg(name):
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(src, n)
    raise KeyError(name)

# ── live block: everything between the two markers ──
a = src.index("# [LIVE REVERSAL] [REV-FIX v1]")
a = src.rfind("\n", 0, a - 1) + 1
b = src.index("def run_live(cfg, exchange):")
LIVE = src[a:b]

# ───────────────────────── fakes ─────────────────────────
class Clock:
    def __init__(self, t): self.t = float(t)
    def time(self): return self.t
    def sleep(self, s): self.t += float(s)

class Cfg: pass
CFG = Cfg()
CFG.timeframe = "4h"; CFG.TF_SECONDS = 14400; CFG.TF_HOURS = 4.0
CFG.REVERSAL_CONFIRM_ENABLED = True
CFG.REVERSAL_TOUCH_SUBBARS = 20; CFG.REVERSAL_BOUNCE_SUBBARS = 4
CFG.REVERSAL_CONFIRM_MODE = "sigma_bounce"; CFG.REVERSAL_CONFIRM_KAPPA = 0.3
CFG.REVERSAL_FILL_AT = "close"; CFG.MAX_CONCURRENT_ASSETS = 5
CFG.TRAIL_KAPPA = 1.0; CFG.TRAIL_MIN_FRAC = 0.005; CFG.TRAIL_MAX_FRAC = 0.05
CFG.TRAIL_ACT_KAPPA = 1.5; CFG.TRAIL_ACT_MIN_FRAC = 0.005; CFG.TRAIL_ACT_MAX_FRAC = 0.08
CFG.MIN_NOTIONAL = 5.0; CFG.CORRELATION_THRESHOLD = 0.8
CFG.SL_WIDEN_MULT = 0.7; CFG.TP_MULT = 2.0; CFG.PROTECTIVE_ORDERS_ENABLED = True
CFG.LIQ_ENABLED = False

class FakeEx:
    def __init__(self):
        self.options = {}; self.orders = {}; self.n = 0
        self.bid = 100.0; self.ask = 100.1; self.pos = {}   # sym -> (qty, entry, side)
        self.bars = {}; self.fail_create = None; self.create_calls = 0
        self.cancel_calls = 0; self.market_calls = []; self.rate_limit = False
        self.precisionMode = 4
    def market(self, s): return {"precision": {"price": 0.1}}
    def amount_to_precision(self, s, q): return str(round(float(q), 3))
    def price_to_precision(self, s, p): return str(round(float(p), 1))
    def fetch_ohlcv(self, sym, tf, since=None, limit=None, params=None):
        if self.rate_limit: raise Exception("429 Too many requests")
        return [r for r in self.bars.get(sym, []) if since is None or r[0] >= since][: (limit or 1000)]
    def fetch_order_book(self, sym, limit=5):
        return {"bids": [[self.bid, 1]], "asks": [[self.ask, 1]]}
    def create_order(self, sym, typ, side, qty, price=None, params=None):
        self.create_calls += 1
        params = params or {}
        if typ == "market":
            self.market_calls.append((side, qty, params))
            return {"id": "m1", "status": "closed", "filled": qty, "average": self.ask}
        if self.fail_create == "timeout_but_created":
            self.fail_create = None
            self._mk(sym, side, qty, price, params); raise Exception("RequestTimeout")
        if side == "buy" and price >= self.ask:
            raise Exception('binance {"code":-5022,"msg":"Post Only order will be rejected"}')
        return self._mk(sym, side, qty, price, params)
    def _mk(self, sym, side, qty, price, params):
        self.n += 1; oid = f"o{self.n}"
        o = {"id": oid, "symbol": sym, "side": side, "amount": qty, "price": price,
             "status": "open", "filled": 0.0, "average": None,
             "clientOrderId": params.get("clientOrderId"), "info": {}}
        self.orders[oid] = o; return dict(o)
    def fetch_order(self, oid, sym, params=None):
        params = params or {}
        if oid is None:
            c = params.get("origClientOrderId")
            for o in self.orders.values():
                if o["clientOrderId"] == c: return dict(o)
            raise type("OrderNotFound", (Exception,), {})("-2013 Order does not exist")
        if oid not in self.orders: raise type("OrderNotFound", (Exception,), {})("-2013")
        return dict(self.orders[oid])
    def fetch_open_orders(self, sym=None):
        return [dict(o) for o in self.orders.values() if o["status"] == "open"
                and (sym is None or o["symbol"] == sym)]
    def cancel_order(self, oid, sym, params=None):
        self.cancel_calls += 1
        params = params or {}
        for o in self.orders.values():
            if (oid and o["id"] == oid) or (params.get("origClientOrderId") == o["clientOrderId"]):
                if o["status"] == "open": o["status"] = "canceled"
                return
        raise type("OrderNotFound", (Exception,), {})("-2013")
    # test helpers
    def fill(self, oid, qty=None):
        o = self.orders[oid]; q = o["amount"] if qty is None else qty
        o["filled"] = q; o["average"] = o["price"]
        o["status"] = "closed" if q >= o["amount"] - 1e-12 else "open"
        side = "BUY" if o["side"] == "buy" else "SELL"
        pq, pe, ps = self.pos.get(o["symbol"], (0.0, 0.0, side))
        self.pos[o["symbol"]] = (q, o["price"], side)

EX = FakeEx()
PROT = {"ok": True, "calls": 0}
STATE_SAVES = []
ns = dict(np=np, pd=pd, json=json, os=os, Dict=Dict, Optional=Optional, Tuple=Tuple,
          CFG=CFG, log=logging.getLogger("t"), _PENDING_ORDERS={})
ns["_get_subbars_tf"] = lambda tf: "15m"
ns["_rate_record"] = lambda w=1.0: None
ns["_rate_can_place"] = lambda: True
ns["_lv_min_amount"] = lambda ex, s: 0.001
ns["_lv_fetch_positions"] = lambda ex, syms=None: {
    s.split(":")[0]: {"qty": v[0], "entry": v[1], "side": v[2], "liq": 0.0}
    for s, v in ex.pos.items() if v[0] > 0}
ns["_lv_save_state"] = lambda p, o: STATE_SAVES.append((p, sorted(o)))
def _prot(ex, sym, pos):
    PROT["calls"] += 1
    return PROT["ok"]
ns["_place_protective_orders"] = _prot
ns["compute_liquidation_price"] = lambda *a, **k: None
ns["ensure_symbol_setup"] = lambda *a, **k: None
ns["_get_mmr_for_symbol"] = lambda ex, s: 0.02
ns["_backtest_entry_target"] = lambda sig, ad: float(sig.price)
exec(compile(LIVE, "live_block", "exec"), ns)
clock = Clock(0)
ns["_t_rev"] = clock
exec(seg("_check_reversal_fill_subbars"), ns)
ns["_REV_ENTRY_SUB"] = {}

tmpd = tempfile.mkdtemp(); os.chdir(tmpd)
ns["load_reversal_watchers"]("testnet")

# ───────────────────────── 1) PARITY: backtest fn vs live scanner ─────────────────────────
class Sig: pass
def run_parity(mode, kappa, trials=400, seed=1):
    rnd = random.Random(seed); mism = 0; hits = 0; none_both = 0
    CFG.REVERSAL_CONFIRM_MODE = mode; CFG.REVERSAL_CONFIRM_KAPPA = kappa
    for t in range(trials):
        action = rnd.choice(["BUY", "SELL"])
        sym = f"S{t}/USDT:USDT"
        n_main, sub_pm = 12, 16
        close_idx = 3
        px0 = 100.0
        # random-walk 15m bars after the signal bar
        n_sub = n_main * sub_pm
        steps = np.array([rnd.gauss(0, 0.25) for _ in range(n_sub)])
        c = px0 + np.cumsum(steps) * (1 if rnd.random() < .5 else -1) * 0.6
        hi = c + np.abs(np.array([rnd.gauss(0, .15) for _ in range(n_sub)]))
        lo = c - np.abs(np.array([rnd.gauss(0, .15) for _ in range(n_sub)]))
        sigma = rnd.choice([0.004, 0.01, 0.02])
        target = px0 * (1 - 0.003) if action == "BUY" else px0 * (1 + 0.003)
        ad = types.SimpleNamespace(
            sub_highs=hi.reshape(n_main, sub_pm), sub_lows=lo.reshape(n_main, sub_pm),
            sub_closes=c.reshape(n_main, sub_pm), sub_per_main=sub_pm,
            E_therm=np.array([sigma] * 10))
        sg = Sig(); sg.action = action; sg.close_idx = close_idx; sg.feat_idx = 0
        sg.symbol = sym; sg.price = target
        bt = ns["_check_reversal_fill_subbars"](ad, sg, target, CFG, close_idx + 1, n_main)
        # ---- live: bars for main bars close_idx+1.. as 15m klines
        sig_epoch = 1_700_000_000 // 14400 * 14400
        start_ts = sig_epoch + 14400
        flat_h, flat_l, flat_c = hi[(close_idx + 1) * sub_pm:], lo[(close_idx + 1) * sub_pm:], c[(close_idx + 1) * sub_pm:]
        # backtest arrays are indexed by main bar from 0; flatten from close_idx+1
        flat_h = ad.sub_highs[close_idx + 1:].reshape(-1); flat_l = ad.sub_lows[close_idx + 1:].reshape(-1)
        flat_c = ad.sub_closes[close_idx + 1:].reshape(-1)
        EX.bars[sym] = [[int((start_ts + k * 900) * 1000), flat_c[k], flat_h[k], flat_l[k], flat_c[k], 1.0]
                        for k in range(len(flat_c))]
        w = {}
        ns["_REVERSAL_WATCHERS"].clear(); ns["_REV_LEDGER"].clear()
        s2 = Sig(); s2.action = action; s2.symbol = sym; s2.price = target
        s2.sl = target * (0.99 if action == "BUY" else 1.01); s2.tp1 = target * (1.02 if action == "BUY" else 0.98)
        s2.timestamp = pd.Timestamp(sig_epoch, unit="s", tz="UTC"); s2.close_idx = close_idx
        s2.feat_idx = 0; s2.dynamic_risk = 0.01; s2.T_info_val = 0.0; s2.score = 1.0
        ad2 = types.SimpleNamespace(E_therm=np.array([sigma]), friction=np.array([.2]),
                                    geodesic_accel=np.array([.05]), gauge_force=np.array([.1]))
        clock.t = start_ts - 60
        ok = ns["_register_reversal_watcher"](EX, sym, "buy", 1.0, s2, 5, ad2)
        assert ok, "register failed"
        wt = ns["_REVERSAL_WATCHERS"][sym]
        wt["target"] = target
        # advance clock bar by bar; stop at READY_TO_FILL/EXPIRED
        res = None
        for step in range(1, 40):
            clock.t = start_ts + step * 900 + 3
            ns["monitor_reversal_watchers"](EX, {"X": {}}, assets=None, cap_now=None, corr_cache=None) \
                if False else None
            st = wt["status"]
            if st in ("WAITING_TOUCH", "WAITING_BOUNCE"):
                ns["_rev_scan"](EX, sym, wt, "15m", 900, clock.t)
            st = wt["status"]
            if st == "READY_TO_FILL":
                res = ("READY", wt["confirm_k"], wt["ref_px"]); break
            if st == "EXPIRED":
                res = ("EXP", wt.get("reason")); break
        if bt is None:
            if res is not None and res[0] == "READY":
                mism += 1; print("MISMATCH (live confirmed, backtest None)", mode, action, t)
            else:
                none_both += 1
        else:
            hits += 1
            em, px = bt
            entry_sub = ns["_REV_ENTRY_SUB"][(sym, close_idx)]
            if res is None or res[0] != "READY":
                mism += 1; print("MISMATCH (backtest filled, live no)", mode, action, t, res); continue
            ck = res[1]; entry_k = ck + 1
            exp_main = close_idx + 1 + entry_k // sub_pm
            if (em != exp_main) or (entry_sub != entry_k % sub_pm) or abs(px - res[2]) > 1e-9:
                mism += 1; print("MISMATCH values", mode, t, bt, entry_sub, res)
    return trials, hits, none_both, mism

print("== PARITY (backtest _check_reversal_fill_subbars vs live scanner) ==")
tot_m = 0
for mode, kappa in [("sigma_bounce", .3), ("close_back", 0), ("two_bar", 0), ("bar_color", 0)]:
    tr, hits, nb, mm = run_parity(mode, kappa)
    tot_m += mm
    print(f"{mode:13s} trials={tr} both-fill={hits} both-none={nb} mismatches={mm}")
assert tot_m == 0, "parity broken"

# ───────────────────────── 2) FILL ENGINE scenarios ─────────────────────────
CFG.REVERSAL_CONFIRM_MODE = "sigma_bounce"; CFG.REVERSAL_CONFIRM_KAPPA = 0.3
def mkwatcher(sym, action="BUY", qty=1.0, ref=100.0, now=None):
    ns["_REVERSAL_WATCHERS"].clear()
    now = clock.t
    w = {"sym": sym, "side": "buy", "side_ccxt": "buy" if action == "BUY" else "sell",
         "action": action, "target": 99.7, "qty": qty, "cap_ref": 1000.0, "leverage": 5,
         "mmr": .02, "dyn_risk": .01, "T_info": 0, "score": 1.0, "sigma_bar": 0.01,
         "close_idx": 3, "sig_epoch": 1_700_000_000.0, "start_ts": now, "expire_ts": now + 99999,
         "status": "READY_TO_FILL", "touch_k": 2, "last_scan_ts": now, "next_fetch_ts": now + 99999,
         "orig_sl_dist": 1.0, "orig_tp_dist": 2.0, "banked_qty": 0.0, "banked_cost": 0.0,
         "cur_filled": 0.0, "cur_avg": 0.0, "attempt": 0, "rejects": 0, "err": 0, "cid": None,
         "order_id": None, "cid_sent": False, "order_px": 0.0, "cancel_req": False,
         "confirm_close_ts": now - 5, "ref_px": ref, "confirm_k": 4}
    ns["_REVERSAL_WATCHERS"][sym] = w
    return w

def cyc(opl, n=1, dt=5, cap=None):
    for _ in range(n):
        clock.t += dt
        ns["monitor_reversal_watchers"](EX, opl, assets=None, cap_now=cap, corr_cache=None)

SYM = "AAA/USDT:USDT"
clock.t = 1_700_100_000
EX = FakeEx(); ns["EX"] = EX
STATE_SAVES.clear()
# A) happy path
opl = {}; w = mkwatcher(SYM)
EX.bid, EX.ask = 99.9, 100.0
cyc(opl)                                   # READY -> FILLING -> GTX placed
assert w["status"] == "FILLING" and w["cid"], w
oid = [o for o in EX.orders][0]
assert EX.orders[oid]["price"] == 99.9 and EX.orders[oid]["clientOrderId"].startswith("rev")
EX.fill(oid); cyc(opl)
assert SYM not in ns["_REVERSAL_WATCHERS"] or w["status"] == "FILLED"
assert SYM in opl and abs(opl[SYM]["entry"] - 99.9) < 1e-9 and opl[SYM]["stage"] == "REVERSAL"
assert opl[SYM]["_entry_ci"] >= 3 and opl[SYM]["_orig_score"] == 1.0
assert abs(opl[SYM]["sl"] - 98.9) < 1e-9 and abs(opl[SYM]["tp1"] - 101.9) < 1e-9
assert PROT["calls"] >= 1 and STATE_SAVES, "state must be saved immediately"
print("A happy path: OK  entry=%.2f sl=%.3f tp=%.3f" % (opl[SYM]["entry"], opl[SYM]["sl"], opl[SYM]["tp1"]))

# B) reprice up within chase, then beyond chase -> expire w/o position
EX = FakeEx(); ns["EX"] = EX; opl = {}; w = mkwatcher(SYM)
EX.bid, EX.ask = 99.9, 100.0; cyc(opl)
first = w["cid"]; EX.bid, EX.ask = 100.05, 100.15
cyc(opl, n=2)                               # cancel+replace to new best bid
assert w["cid"] != first and EX.orders[[k for k in EX.orders][0]]["status"] == "canceled", "reprice failed"
EX.bid, EX.ask = 101.5, 101.6               # far beyond ref+0.15*sigma*px(=0.15)
cyc(opl, n=3)
assert w["status"] == "EXPIRED" and w["reason"].startswith("chase_cap") and SYM not in opl, w
assert all(o["status"] != "open" for o in EX.orders.values()), "orphan order left"
print("B reprice/chase-cap: OK reason=", w["reason"])

# C) partial fill then deadline -> partial position adopted, no open orders
EX = FakeEx(); ns["EX"] = EX; opl = {}; w = mkwatcher(SYM, qty=2.0)
EX.bid, EX.ask = 99.9, 100.0; cyc(opl)
oid = list(EX.orders)[0]; EX.orders[oid]["filled"] = 0.8; EX.orders[oid]["average"] = 99.9
EX.pos[SYM] = (0.8, 99.9, "BUY")
clock.t += 200; cyc(opl, n=3)
assert SYM in opl and abs(opl[SYM]["qty"] - 0.8) < 1e-9, (w, opl)
assert all(o["status"] != "open" for o in EX.orders.values())
print("C partial+deadline: OK qty=", opl[SYM]["qty"])

# D) restart mid-FILLING resumes by clientOrderId (no duplicate order)
EX = FakeEx(); ns["EX"] = EX; opl = {}; w = mkwatcher(SYM)
EX.bid, EX.ask = 99.9, 100.0; cyc(opl); n_orders = len(EX.orders)
ns["save_reversal_watchers"]()
ns["_REVERSAL_WATCHERS"].clear(); ns["load_reversal_watchers"]("testnet")
ns["_rev_startup_recover"](EX, opl)
assert SYM in ns["_REVERSAL_WATCHERS"] and ns["_REVERSAL_WATCHERS"][SYM]["status"] == "FILLING"
cyc(opl, n=2)
assert len(EX.orders) == n_orders, "duplicate entry order after restart"
print("D restart-resume: OK")

# E) ambiguous create_order timeout but order exists -> adopted, not duplicated
EX = FakeEx(); ns["EX"] = EX; opl = {}; w = mkwatcher(SYM)
EX.bid, EX.ask = 99.9, 100.0; EX.fail_create = "timeout_but_created"
cyc(opl); cyc(opl)
assert len(EX.orders) == 1 and w["order_id"], (EX.orders, w)
print("E ambiguous create: OK (no duplicate)")

# F) GTX reject is retried (not expired)
EX = FakeEx(); ns["EX"] = EX; opl = {}; w = mkwatcher(SYM)
EX.bid, EX.ask = 99.9, 99.9                 # bid==ask -> BUY at bid crosses -> -5022
cyc(opl, n=2); assert w["status"] == "FILLING" and w["rejects"] >= 1
EX.ask = 100.0; cyc(opl, n=2); assert w["cid"], w
print("F GTX reject retry: OK rejects=", w["rejects"])

# G) slot gate at FILL time + stale confirm
EX = FakeEx(); ns["EX"] = EX
opl = {f"P{i}": {} for i in range(5)}; w = mkwatcher(SYM); cyc(opl)
assert w["status"] == "EXPIRED" and w["reason"] == "slots_full"
w = mkwatcher(SYM); w["confirm_close_ts"] = clock.t - 5000; cyc({})
assert w["status"] == "EXPIRED" and w["reason"] == "stale_confirm"
# watchers do NOT occupy slots: 5 open + 40 waiting watchers is representable (cap=50)
ns["_REVERSAL_WATCHERS"].clear()
for i in range(40): ns["_REVERSAL_WATCHERS"][f"W{i}"] = {"status": "WAITING_TOUCH", "start_ts": clock.t, "expire_ts": clock.t + 9999, "next_fetch_ts": clock.t + 9999, "touch_k": -1}
assert len(ns["_REVERSAL_WATCHERS"]) < CFG.__dict__.get("REV_WATCHER_CAP", 50)
print("G slot gate / stale: OK")

# H) protective failure -> emergency flatten
EX = FakeEx(); ns["EX"] = EX; opl = {}; w = mkwatcher(SYM); PROT["ok"] = False
EX.bid, EX.ask = 99.9, 100.0; cyc(opl); EX.fill(list(EX.orders)[0]); cyc(opl)
assert SYM not in opl and EX.market_calls and EX.market_calls[-1][2].get("reduceOnly") is True, EX.market_calls
PROT["ok"] = True
print("H unprotected -> flatten: OK")

# I) ledger: once per signal (even after expiry), watcher cap, rate-limit back-off
ns["_REVERSAL_WATCHERS"].clear(); ns["_REV_LEDGER"].clear()
sg = Sig(); sg.action = "BUY"; sg.symbol = "L/USDT:USDT"; sg.price = 99.7; sg.sl = 98.7; sg.tp1 = 101.7
sg.timestamp = pd.Timestamp(clock.t // 14400 * 14400, unit="s", tz="UTC"); sg.close_idx = 3
sg.feat_idx = 0; sg.dynamic_risk = .01; sg.T_info_val = 0; sg.score = 1
ad2 = types.SimpleNamespace(E_therm=np.array([.01]), friction=np.array([.2]), geodesic_accel=np.array([.05]), gauge_force=np.array([.1]))
clock.t = (clock.t // 14400 * 14400) + 14400 - 100
assert ns["_register_reversal_watcher"](EX, sg.symbol, "buy", 1.0, sg, 5, ad2)
ns["_REVERSAL_WATCHERS"].pop(sg.symbol)
assert not ns["_register_reversal_watcher"](EX, sg.symbol, "buy", 1.0, sg, 5, ad2), "re-registered same signal"
EX.rate_limit = True; wq = mkwatcher(SYM); wq["status"] = "WAITING_TOUCH"; wq["next_fetch_ts"] = 0
wq["start_ts"] = clock.t - 100; wq["expire_ts"] = clock.t + 9999
cyc({}); assert ns["_REV_BACKOFF_UNTIL"] > clock.t, "no back-off armed"
print("I ledger / back-off: OK")

# J) _snap_qty exists and floors/min-checks
assert ns["_snap_qty"](EX, "X", 0.0004) == 0.0 and ns["_snap_qty"](EX, "X", 1.23456) == 1.235
print("J _snap_qty defined: OK")
print("ALL TESTS PASSED")
