import ast, glob, json, logging, os, re, subprocess, sys, tempfile, threading, time as _real_time
import time
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

SRC = sys.argv[1]
src = open(SRC, encoding="utf-8").read()
tree = ast.parse(src)
HERE = os.path.dirname(os.path.abspath(__file__))

def seg(name):
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(src, n)
    raise KeyError(name)

a = src.index("# [REV-FIX v2] Long-run hardening")
a = src.rfind("\n", 0, a - 1) + 1
b = src.index("def run_live(cfg, exchange):")
BLOCK = src[a:b]

# ───────────────────────── fakes ─────────────────────────
class FT:
    """controllable clock"""
    def __init__(self, t): self.t = float(t)
    def time(self): return self.t
    def sleep(self, s): self.t += s
    strftime = staticmethod(_real_time.strftime)
CLK = FT(1_700_000_000)

class Cfg: pass
CFG = Cfg(); CFG.mode = "testnet"
CFG.LOOP_WARN_ERRORS = 3; CFG.LOOP_MAX_CONSEC_ERRORS = 6; CFG.LOOP_EXIT_ON_ERRORS = True
CFG.LOOP_ERR_RESET_AFTER_S = 900; CFG.REVERSAL_CONFIRM_ENABLED = True

CALLS = {"rate": 0.0, "save_state": [], "monitor": [], "tsync_check": 0}
def _rr(w=1.0): CALLS["rate"] += w
ns = dict(time=CLK, json=json, os=os, np=np, pd=pd, logging=logging, Dict=Dict, Tuple=Tuple,
          Optional=Optional, List=List, CFG=CFG, log=logging.getLogger("T"),
          _REVERSAL_WATCHERS={}, _rate_record=_rr,
          _TICK_SIZE_CACHE={"X": 1}, _MMR_CACHE={"X": 1}, _SYMBOL_LEV_TIERS={"X": (5, [1])},
          _DEGENERATE_STREAK={}, _DEGENERATE_BAN_THRESHOLD=10, _DEGENERATE_CACHE={},
          _DEGENERATE_CACHE_MAX=5000)
ns["_check_time_sync"] = lambda ex, thr=30.0: CALLS.__setitem__("tsync_check", CALLS["tsync_check"] + 1) or True
ns["_lv_save_state"] = lambda p, o: CALLS["save_state"].append(p)
def _mon(ex, opl, assets=None, cap_now=None, corr_cache=None): CALLS["monitor"].append((assets, cap_now))
ns["monitor_reversal_watchers"] = _mon
ns["scan_top_assets"] = lambda ex: ["A", "B"]
ns["fetch_all"] = lambda syms, ex, tf, days=365, workers=5: {}
exec(compile(BLOCK, "v2_block", "exec"), ns)
for fn in ("_lv_atomic_json", "_degenerate_put", "_setup_logging"):
    exec(compile(seg(fn), fn, "exec"), ns)

tmpd = tempfile.mkdtemp(); os.chdir(tmpd)
ok = lambda m: print("OK ", m)

# ───────────────────────── T1: logging (rotation, dates, no duplicates) ─────────────────────────
os.environ["QTT_LOG_FILE"] = os.path.join(tmpd, "q.log")
os.environ["QTT_LOG_MAX_MB"] = "0.002"; os.environ["QTT_LOG_BACKUPS"] = "3"
root = logging.getLogger(); before = list(root.handlers)
ns["_setup_logging"](); ns["_setup_logging"]()
mine = [h for h in root.handlers if getattr(h, "_qtt", False)]
assert len(mine) == 2, mine                             # stream + rotating file, once
lg = logging.getLogger("QTT6")
for i in range(200): lg.info("x" * 60 + str(i))
for h in mine: h.flush()
files = sorted(glob.glob(os.path.join(tmpd, "q.log*")))
assert len(files) >= 2 and len(files) <= 4, files        # rotated, bounded by backupCount
assert re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \[INFO\]", open(files[0]).readline())
for h in mine: root.removeHandler(h); h.close()
ok(f"T1 logging: {len(files)} rotated files, dated lines, no duplicate handlers")

# ───────────────────────── T2: loop-error escalation ─────────────────────────
class Ex:
    def __init__(self): self.options = {}; self.td = 0; self.markets = {}; self.reload = 0
    def load_time_difference(self): self.td += 1; return 0
    def load_markets(self, reload=False): self.reload += 1; self.markets = dict(self.next_markets); return self.markets
EX = Ex(); EX.next_markets = {}
H0 = ns["_loop_error_handler"]
class _Cap(logging.Handler):
    def __init__(self): super().__init__(); self.msgs = []
    def emit(self, r): self.msgs.append(self.format(r))
CAP = _Cap(); ns["log"].addHandler(CAP); ns["log"].setLevel(logging.DEBUG)
def H(ex, exc, opl, sf):
    try:
        raise exc                      # real except-context so format_exc() has a traceback
    except Exception as e:
        H0(ex, e, opl, sf)
for i in range(2): H(EX, ValueError("boom"), {"A": {}}, "state.json")
assert any("Traceback (most recent call last)" in m and "boom" in m for m in CAP.msgs), "traceback not logged at ERROR"
assert ns["_LOOP_ERR"]["streak"] == 2 and not os.path.exists("alerts_testnet.log")
H(EX, ValueError("boom"), {"A": {}}, "state.json")
assert "[WARN]" in open("alerts_testnet.log").read()
hb = json.load(open("heartbeat_testnet.json")); assert hb["err_streak"] == 3 and hb["state"] == "error"
H(EX, Exception('binance {"code":-1021,"msg":"Timestamp for this request is outside of the recvWindow"}'), {}, "state.json")
assert EX.td == 1, "no time resync on -1021"
H(EX, ValueError("boom"), {}, "state.json")
try:
    H(EX, ValueError("boom"), {"A": {}}, "state.json"); raise AssertionError("no exit")
except SystemExit as e:
    assert e.code == 3
assert CALLS["save_state"] and "[CRITICAL]" in open("alerts_testnet.log").read()
ns["_loop_ok"](10, {"A": {}}); assert ns["_LOOP_ERR"]["streak"] == 0
assert json.load(open("heartbeat_testnet.json"))["state"] == "ok"
CFG.LOOP_EXIT_ON_ERRORS = False
for i in range(8): H(EX, ValueError("x"), {}, "s")        # never raises when disabled
CFG.LOOP_EXIT_ON_ERRORS = True
CLK.t += 1000; H(EX, ValueError("x"), {}, "s"); assert ns["_LOOP_ERR"]["streak"] == 1   # quiet period resets
ok("T2 loop errors: traceback+alert+heartbeat, -1021 resync, exit code 3, reset logic")

# ───────────────────────── T3: housekeeping (time sync + markets) ─────────────────────────
for k in ("tsync", "mkts"): ns["_HK"][k] = CLK.t
EX = Ex(); EX.next_markets = {"BTC/USDT": {"active": True}}
EX.markets = {"BTC/USDT": {"active": True}, "OLD/USDT": {"active": True}}
CALLS["tsync_check"] = 0; ns["_GAP_BUDGET"]["n"] = 4
CLK.t += 3599; ns["_live_housekeeping"](EX, {"OLD/USDT": {}})
assert EX.td == 0 and EX.reload == 0 and ns["_GAP_BUDGET"]["n"] == 0
CLK.t += 2; ns["_live_housekeeping"](EX, {"OLD/USDT": {}})
assert EX.td == 1 and CALLS["tsync_check"] == 1 and EX.reload == 0
CLK.t += 21600; ns["_live_housekeeping"](EX, {"OLD/USDT": {}})
assert EX.reload == 1 and not ns["_TICK_SIZE_CACHE"] and not ns["_MMR_CACHE"] and not ns["_SYMBOL_LEV_TIERS"]
assert "held symbol OLD/USDT delisted" in open("alerts_testnet.log").read()
ok("T3 housekeeping: hourly time sync, 6h markets reload, caches cleared, delisted-held alert")

# ───────────────────────── T4: degenerate ban TTL ─────────────────────────
for i in range(9): ns["_degenerate_put"]("DEG", "4h", i)
assert not ns["_degenerate_banned"]("DEG")
ns["_degenerate_put"]("DEG", "4h", 99)
assert ns["_degenerate_banned"]("DEG") and "DEG" in ns["_DEGENERATE_BAN_UNTIL"]
CLK.t += 86399; assert ns["_degenerate_banned"]("DEG")
CLK.t += 2;     assert not ns["_degenerate_banned"]("DEG") and "DEG" not in ns["_DEGENERATE_STREAK"]
ok("T4 degenerate ban: banned 24h, auto-unbanned with fresh streak")

# ───────────────────────── T5: JSON write-if-changed ─────────────────────────
p = os.path.join(tmpd, "j.json"); W = ns["_json_write_if_changed"]
assert W(p, {"a": 1}) and not W(p, {"a": 1}) and W(p, {"a": 2}) and not W(p, {"a": 2})
CLK.t += 301; assert W(p, {"a": 2}), "forced refresh missing"
os.remove(p); assert W(p, {"a": 2}), "must rewrite a deleted file"
q = os.path.join(tmpd, "s.json"); obj = {"k": [1, 2], "t": pd.Timestamp("2026-01-01")}
ns["_lv_atomic_json"](q, obj); m1 = os.stat(q).st_mtime_ns
assert open(q).read() == json.dumps(obj, indent=2, default=str)      # byte-identical format
_real_time.sleep(0.02); ns["_lv_atomic_json"](q, obj); assert os.stat(q).st_mtime_ns == m1, "rewrote unchanged state"
ns["_lv_atomic_json"](q, {"k": 3}); assert json.loads(open(q).read()) == {"k": 3}
ok("T5 json: unchanged skipped, changes/forced/deleted rewritten, format identical")

# ───────────────────────── T6: gap-aware fetch / heal ─────────────────────────
TF = 14400
class GEx:
    def __init__(self, full): self.full = full; self.calls = []
    def fetch_ohlcv(self, sym, tf, since=None, limit=None, params=None):
        self.calls.append((since, limit))
        rows = [r for r in self.full if since is None or r[0] >= since]
        return rows[-limit:] if since is None else rows[:limit]
base = (int(CLK.t) // TF) * TF
ts_all = [base - TF * k for k in range(80, -1, -1)]
full = [[t * 1000, 1, 2, 0.5, 1.5, 10] for t in ts_all]
def mkdf(rows):
    d = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    d["ts"] = pd.to_datetime(d["ts"], unit="ms", utc=True); return d.set_index("ts").astype(float)
df_full = mkdf(full)
assert ns["_find_first_gap"](df_full, TF, 600) is None
holes = [r for i, r in enumerate(full) if not (40 <= i <= 43)]
df_gap = mkdf(holes)
g = ns["_find_first_gap"](df_gap, TF, 600); assert g == ts_all[39], (g, ts_all[39])
gx = GEx(full); ns["_GAP_BUDGET"]["n"] = 0
healed = ns["_live_heal_gaps"](gx, "S", "4h", df_gap, TF)
assert len(healed) == len(df_full) and ns["_find_first_gap"](healed, TF, 600) is None and len(gx.calls) == 1
n_calls = len(gx.calls); ns["_live_heal_gaps"](gx, "S", "4h", df_gap, TF)
assert len(gx.calls) == n_calls, "same gap retried"                   # dead-gap protection
ns["_GAP_ATTEMPTED"].clear(); ns["_GAP_BUDGET"]["n"] = 5
ns["_live_heal_gaps"](gx, "S", "4h", df_gap, TF); assert len(gx.calls) == n_calls, "budget ignored"
# normal cycle: last bar one tf behind -> classic limit=3 ; 3 bars behind -> since-fetch
CLK.t = base + 120
gx = GEx(full); df_n = mkdf(full[:-1]); ns["_live_fetch_candles"](gx, "S", "4h", df_n, TF)
assert gx.calls[-1] == (None, 3), gx.calls
CLK.t = base + 3 * TF + 120
gx = GEx(full); df_o = mkdf(full[:-1]); ns["_live_fetch_candles"](gx, "S", "4h", df_o, TF)
since, lim = gx.calls[-1]; assert since is not None and lim >= 5, gx.calls
ok("T6 gaps: detect, heal once, dead-gap & budget guards, 3-candle fast path kept, catch-up fetch")

# ───────────────────────── T7: keepalive ─────────────────────────
CALLS["monitor"].clear(); ns["_KEEPALIVE_LAST"]["t"] = 0.0
CLK.t += 100
ns["_live_keepalive"](EX, {}, {"A": 1}, 123.0, {}); assert len(CALLS["monitor"]) == 1 and CALLS["monitor"][0][1] == 123.0
ns["_live_keepalive"](EX, {}, {}, 1.0, {}); assert len(CALLS["monitor"]) == 1          # throttled
CLK.t += 6; ns["_live_keepalive"](EX, {}, {}, 1.0, {}); assert len(CALLS["monitor"]) == 2
assert json.load(open("heartbeat_testnet.json"))["state"] == "retrain"
ok("T7 keepalive: throttled watcher monitoring + heartbeat during retrain")

# ───────────────────────── T8: background universe refresh ─────────────────────────
def idx(n, end):
    return pd.date_range(end=end, periods=n, freq="4h", tz="UTC")
t_end = pd.Timestamp("2026-03-01 08:00", tz="UTC")
newA = pd.DataFrame({"Close": range(10)}, index=idx(10, t_end))
newB = pd.DataFrame({"Close": range(10)}, index=idx(10, t_end))
oldA = pd.concat([newA, pd.DataFrame({"Close": [99.0]}, index=[t_end + pd.Timedelta("4h")])])   # appended meanwhile
oldH = pd.DataFrame({"Close": range(5)}, index=idx(5, t_end))
def slow_scan(ex): _real_time.sleep(0.3); return ["A", "B"]
ns["scan_top_assets"] = slow_scan
ns["fetch_all"] = lambda syms, ex, tf, days=365, workers=5: {"A": newA, "B": newB}
U = ns["_UniverseRefresher"](); cfg_ = Cfg(); cfg_.timeframe = "4h"
t0 = _real_time.time()
started = U.maybe_start(EX, cfg_, {"H": {}}, CLK.t - 20000)
assert started and _real_time.time() - t0 < 0.15, "refresh blocked the caller"
assert U.poll({"H": {}}, {"A": oldA, "H": oldH}) is None                 # still running
assert not U.maybe_start(EX, cfg_, {"H": {}}, CLK.t - 20000)             # no double start
U.th.join(); res = U.poll({"H": {}}, {"A": oldA, "H": oldH})
assert res is not None; top, merged = res
assert "H" in top and "H" in merged, "held symbol dropped"
assert merged["A"].iloc[-1]["Close"] == 99.0, "bars appended during refresh were lost"
# failure path -> no swap, retry back-off
ns["scan_top_assets"] = lambda ex: (_ for _ in ()).throw(RuntimeError("net down"))
U2 = ns["_UniverseRefresher"](); U2.maybe_start(EX, cfg_, {}, CLK.t - 20000); U2.th.join()
assert U2.poll({}, {}) is None and U2.retry_at > CLK.t
assert not U2.maybe_start(EX, cfg_, {}, CLK.t - 20000)
CLK.t += 601; ns["scan_top_assets"] = lambda ex: ["A"]
assert U2.maybe_start(EX, cfg_, {}, CLK.t - 20000); U2.th.join()
ok("T8 universe refresh: non-blocking, atomic merge, held kept, appended bars kept, retry back-off")

# ───────────────────────── T9: patched call sites present / old ones gone ─────────────────────────
must = ["_loop_error_handler(", "_live_housekeeping(exchange", "_UNIV.maybe_start", "_UNIV.poll",
        "_live_keepalive(exchange", "_degenerate_banned(sym)", "_live_fetch_candles(", "_live_heal_gaps(",
        "adjustForTimeDifference", "_loop_ok(loop_iter", "_setup_logging()", "_json_write_if_changed("]
for m in must: assert m in src, f"missing {m}"
assert src.count("_live_keepalive(exchange") == 3 and src.count("_degenerate_banned(sym)") == 2
assert "log.debug(traceback.format_exc())" not in src
assert "fetch_ohlcv(sym, cfg.timeframe, limit=3)" not in src
ok("T9 call sites wired")

# ───────────────────────── T10: v1 suite still green on the v2 file ─────────────────────────
r = subprocess.run([sys.executable, os.path.join(HERE, "test_revfix.py"), SRC],
                   capture_output=True, text=True)
assert "ALL TESTS PASSED" in r.stdout, r.stdout[-800:] + r.stderr[-800:]
ok("T10 v1 regression suite: ALL TESTS PASSED")
print("ALL LONG-RUN TESTS PASSED")
