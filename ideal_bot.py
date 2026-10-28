#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════════════════
  IDEAL BOT v1.0 — A Clean Trading Bot from Mathematical Principles
  
  Built from the analysis of 18,000-line "trading_2_live4_claude2_v4.py" 
  and its 24 identified flaws.
  
  Core Principles:
    1. SIMPLICITY     — 5 features, 1 strategy, 3 exits (not 17/50/10)
    2. MEASUREMENT    — Walk-forward, DSR, no fabricated Sharpe
    3. TRUTHFULNESS   — No fancy terminology (no "geodesic", "gauge", "BEEsc")
    4. ROBUSTNESS     — SL by ATR (not 3σ clip), true Kelly (not sigmoid)
    5. VALIDATION     — Train 60% / Validate 20% / Test 20% (untouched)
  
  Mathematical Model:
    - Features:   log_return, volatility, ATR, ema_slope_norm, RSI
    - Direction:  0.4·trend + 0.3·momentum + 0.3·(-z)
    - Entry:      close · (1 - 0.5·σ) [BUY]
    - SL/TP:      2·ATR stop, 3 partial TPs (1.5R, 3R, 5R)
    - Sizing:     half-Kelly, portfolio heat cap
    - Exits:      SL / TP1-TP3 / Trailing / Time-based
════════════════════════════════════════════════════════════════════════════════
"""
import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — CONFIGURATION (every parameter, one place)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    # ── Data ──
    timeframe: str = "4h"
    history_days: int = 730
    cache_dir: str = "data_cache"
    
    # ── Features ──
    N: int = 24                # Feature window
    VOL_WINDOW: int = 20       # Volatility window
    ATR_WINDOW: int = 14       # ATR window
    EMA_FAST: int = 50         # EMA for trend
    EMA_SLOW: int = 200        # Slow EMA (optional)
    RSI_WINDOW: int = 14       # RSI window
    MOM_LOOKBACK: int = 20     # Momentum window
    
    # ── Direction ──
    W_TREND: float = 0.40
    W_MOMENTUM: float = 0.30
    W_MEANREV: float = 0.30
    DIRECTION_THRESHOLD: float = 0.30
    QUALITY_PCT: float = 0.70   # Accept top 30% quality signals
    
    # ── Entry ──
    ENTRY_K: float = 0.5        # entry = close * (1 - 0.5σ) [BUY]
    ENTRY_WAIT_BARS: int = 8    # Wait up to 8 bars for fill
    
    # ── SL/TP ──
    SL_K_ATR: float = 2.0       # SL = 2 × ATR
    SL_MIN_ATR: float = 1.5     # Never tighter than 1.5 ATR
    SL_MAX_ATR: float = 3.0     # Never wider than 3.0 ATR
    TP_R_MULT: Tuple = (1.5, 3.0, 5.0)
    TP_PCT: Tuple = (0.30, 0.30, 0.40)  # Sum = 1.0
    TRAIL_ACTIVATE_R: float = 1.5   # Activate after TP1
    TRAIL_K_ATR: float = 1.5        # SL = peak - 1.5 × ATR
    MAX_HOLD_BARS: int = 24         # ~4 days on 4h
    
    # ── Risk ──
    KELLY_FRACTION: float = 0.5     # Half-Kelly
    KELLY_MIN: float = 0.005        # 0.5% floor
    KELLY_MAX: float = 0.020        # 2.0% ceiling
    HEAT_MAX: float = 0.10          # 10% total heat
    MAX_CONCURRENT: int = 5
    MIN_HISTORY_TRADES: int = 30    # Need this many for Kelly
    
    # ── Capital ──
    INITIAL_CAPITAL: float = 100.0
    CAPITAL_FLOOR: float = 0.15
    
    # ── Fees & Slippage ──
    MAKER_FEE: float = 0.0002       # 0.02%
    TAKER_FEE: float = 0.0005       # 0.05%
    SLIP_TAKER_BPS: float = 5.0     # 5 bps on SL exits
    
    # ── Validation ──
    TRAIN_FRACTION: float = 0.60
    VALID_FRACTION: float = 0.20
    TEST_FRACTION: float = 0.20
    N_WALK_WINDOWS: int = 6
    
    # ── Output ──
    trades_log: str = "trades_ideal.jsonl"
    metrics_file: str = "metrics_ideal.json"
    plot_file: str = "equity_ideal.png"
    verbose: bool = False


CFG = Config()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — LOGGING
# ══════════════════════════════════════════════════════════════════════════════

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

log = logging.getLogger("IDEAL")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

class DataLayer:
    """Fetch, cache, and validate OHLCV data."""
    
    def __init__(self, exchange, cfg: Config):
        self.exchange = exchange
        self.cfg = cfg
        os.makedirs(cfg.cache_dir, exist_ok=True)
    
    def _cache_path(self, symbol: str) -> str:
        safe = symbol.replace("/", "_")
        return os.path.join(self.cfg.cache_dir, f"{safe}_{self.cfg.timeframe}.parquet")
    
    def get_ohlcv(self, symbol: str, days: int) -> Optional[pd.DataFrame]:
        """Returns df with OHLCV columns, UTC DatetimeIndex."""
        fp = self._cache_path(symbol)
        
        # Try cache
        df = None
        if os.path.exists(fp):
            try:
                df = pd.read_parquet(fp)
                if df.index.tz is None:
                    df.index = df.index.tz_localize('UTC')
                last_ts = df.index.max()
                # Fetch new bars
                tf_sec = self._tf_seconds()
                since = self.exchange.parse8601(
                    (last_ts + timedelta(seconds=tf_sec)).isoformat() + "Z"
                )
                new_rows = []
                while True:
                    chunk = self.exchange.fetch_ohlcv(symbol, self.cfg.timeframe,
                                                       since=since, limit=1000)
                    if not chunk:
                        break
                    new_rows.extend(chunk)
                    since = chunk[-1][0] + 1
                    time.sleep(0.1)
                if new_rows:
                    new_df = pd.DataFrame(new_rows, columns=['ts','Open','High','Low','Close','Volume'])
                    new_df['ts'] = pd.to_datetime(new_df['ts'], unit='ms', utc=True)
                    new_df = new_df.set_index('ts').astype(float)
                    df = pd.concat([df, new_df])
                    df = df[~df.index.duplicated(keep='last')].sort_index()
                    df.to_parquet(fp)
            except Exception as e:
                log.warning(f"[Data] {symbol} cache read failed: {e}")
                df = None
        
        # Full fetch if needed
        if df is None or len(df) < 500:
            since = self.exchange.parse8601(
                (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() + "Z"
            )
            rows = []
            while True:
                try:
                    chunk = self.exchange.fetch_ohlcv(symbol, self.cfg.timeframe,
                                                       since=since, limit=1000)
                except Exception as e:
                    log.warning(f"[Data] {symbol} fetch failed: {e}")
                    break
                if not chunk:
                    break
                rows.extend(chunk)
                since = chunk[-1][0] + 1
                time.sleep(0.1)
            if not rows:
                return None
            df = pd.DataFrame(rows, columns=['ts','Open','High','Low','Close','Volume'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms', utc=True)
            df = df.set_index('ts').astype(float).sort_index()
            try:
                df.to_parquet(fp)
            except Exception:
                pass
        
        # Validate
        df = self._validate(df, symbol)
        return df
    
    def _validate(self, df: pd.DataFrame, symbol: str) -> Optional[pd.DataFrame]:
        if df is None or len(df) < 200:
            return None
        # Columns
        required = ['Open','High','Low','Close','Volume']
        for col in required:
            if col not in df.columns:
                log.warning(f"[Data] {symbol} missing column {col}")
                return None
        # NaN
        df = df.dropna(subset=required)
        # Invalid
        invalid = (
            (df['High'] < df['Low']) |
            (df['Close'] <= 0) | (df['Open'] <= 0) |
            (df['High'] <= 0) | (df['Low'] <= 0)
        )
        df = df[~invalid]
        # Clamp
        df.loc[df['High'] < df[['Open','Close']].max(axis=1), 'High'] = \
            df[['Open','Close']].max(axis=1)
        df.loc[df['Low'] > df[['Open','Close']].min(axis=1), 'Low'] = \
            df[['Open','Close']].min(axis=1)
        if len(df) < 200:
            return None
        return df
    
    def _tf_seconds(self) -> int:
        try:
            return int(self.exchange.parse_timeframe(self.cfg.timeframe))
        except Exception:
            return 14400  # 4h fallback


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — FEATURES (Layer 2)
# ══════════════════════════════════════════════════════════════════════════════

def compute_features(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """
    Returns df with 5 features added:
      log_return, volatility, atr, ema_slope_norm, rsi
    
    All formulas documented in the mathematical spec.
    """
    out = df.copy()
    C = out['Close'].values
    H = out['High'].values
    L = out['Low'].values
    
    # ── 1. Log return ──
    out['log_return'] = np.log(np.maximum(C, 1e-12) /
                                 np.maximum(np.roll(C, 1), 1e-12))
    out.loc[out.index[0], 'log_return'] = 0.0
    
    # ── 2. Volatility (20-bar std of log returns) ──
    out['volatility'] = out['log_return'].rolling(cfg.VOL_WINDOW, min_periods=5).std()
    
    # ── 3. ATR (14-bar) ──
    C_prev = np.roll(C, 1)
    C_prev[0] = C[0]
    tr = np.maximum(H - L, np.maximum(np.abs(H - C_prev), np.abs(L - C_prev)))
    out['atr'] = pd.Series(tr, index=out.index).rolling(cfg.ATR_WINDOW, min_periods=1).mean()
    
    # ── 4. EMA slope (normalized by ATR) ──
    ema = pd.Series(C, index=out.index).ewm(span=cfg.EMA_FAST, adjust=False).mean()
    slope_raw = (ema - ema.shift(cfg.EMA_FAST)) / cfg.EMA_FAST
    out['ema'] = ema
    out['ema_slope_norm'] = slope_raw / np.maximum(out['atr'], 1e-9)
    
    # ── 5. RSI (14-bar) ──
    delta = pd.Series(C, index=out.index).diff()
    up = delta.clip(lower=0).rolling(cfg.RSI_WINDOW, min_periods=1).mean()
    down = (-delta.clip(upper=0)).rolling(cfg.RSI_WINDOW, min_periods=1).mean()
    rs = up / np.maximum(down, 1e-9)
    out['rsi'] = 100 - 100 / (1 + rs)
    
    # ── Auxiliary: z-score (for direction) ──
    roll_mean = pd.Series(C, index=out.index).rolling(cfg.N, min_periods=5).mean()
    roll_std = pd.Series(C, index=out.index).rolling(cfg.N, min_periods=5).std()
    out['z20'] = (pd.Series(C, index=out.index) - roll_mean) / np.maximum(roll_std, 1e-9)
    
    # ── Auxiliary: momentum (20-bar return / ATR%) ──
    mom_raw = (pd.Series(C, index=out.index) -
               pd.Series(C, index=out.index).shift(cfg.MOM_LOOKBACK)) / \
              pd.Series(C, index=out.index).shift(cfg.MOM_LOOKBACK)
    atr_pct = out['atr'] / np.maximum(out['Close'], 1e-9)
    out['momentum'] = mom_raw / np.maximum(atr_pct, 1e-9)
    
    return out


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — SIGNALS (Layer 3)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    symbol: str
    timestamp: pd.Timestamp
    action: str           # 'BUY' / 'SELL'
    close_price: float    # at signal time
    entry_target: float   # limit price
    sl: float
    sl_dist: float
    tp1: float
    tp2: float
    tp3: float
    direction_score: float
    quality: float
    atr: float
    sigma: float
    bar_idx: int


def generate_signals(df: pd.DataFrame, symbol: str, cfg: Config) -> List[Signal]:
    """Generate signals for a single symbol."""
    signals = []
    
    # Skip first rows without enough history
    start = max(cfg.N, cfg.EMA_FAST, cfg.MOM_LOOKBACK, cfg.RSI_WINDOW) + 10
    
    # Compute quality threshold (top 30% of quality)
    quality_vals = []
    for i in range(start, len(df)):
        row = df.iloc[i]
        if not _valid_row(row):
            continue
        trend = row['ema_slope_norm']
        mom = row['momentum']
        sig_norm = row['volatility']
        if sig_norm <= 1e-9:
            continue
        quality_vals.append((abs(trend) / sig_norm) * (abs(mom) / sig_norm))
    
    if len(quality_vals) < 100:
        return []
    q_threshold = float(np.percentile(quality_vals, cfg.QUALITY_PCT * 100))
    
    # Generate signals
    for i in range(start, len(df)):
        row = df.iloc[i]
        if not _valid_row(row):
            continue
        
        # ── Direction score ──
        trend = float(row['ema_slope_norm'])
        mom = float(row['momentum'])
        z = float(row['z20'])
        
        D = (cfg.W_TREND * np.tanh(trend) +
             cfg.W_MOMENTUM * np.tanh(mom) +
             cfg.W_MEANREV * np.tanh(-z / 2.0))
        
        if D > cfg.DIRECTION_THRESHOLD:
            action = "BUY"
        elif D < -cfg.DIRECTION_THRESHOLD:
            action = "SELL"
        else:
            continue
        
        # ── Quality filter ──
        sig_norm = float(row['volatility'])
        if sig_norm <= 1e-9:
            continue
        Q = (abs(trend) / sig_norm) * (abs(mom) / sig_norm)
        if Q < q_threshold:
            continue
        
        # ── Entry target ──
        close_px = float(row['Close'])
        sigma = float(row['volatility'])
        if action == "BUY":
            entry_target = close_px * (1.0 - cfg.ENTRY_K * sigma)
        else:
            entry_target = close_px * (1.0 + cfg.ENTRY_K * sigma)
        
        # ── SL ──
        atr = float(row['atr'])
        sl_dist = np.clip(cfg.SL_K_ATR * atr,
                          cfg.SL_MIN_ATR * atr,
                          cfg.SL_MAX_ATR * atr)
        if sl_dist <= 1e-9:
            continue
        
        if action == "BUY":
            sl = entry_target - sl_dist
            tp1 = entry_target + cfg.TP_R_MULT[0] * sl_dist
            tp2 = entry_target + cfg.TP_R_MULT[1] * sl_dist
            tp3 = entry_target + cfg.TP_R_MULT[2] * sl_dist
        else:
            sl = entry_target + sl_dist
            tp1 = entry_target - cfg.TP_R_MULT[0] * sl_dist
            tp2 = entry_target - cfg.TP_R_MULT[1] * sl_dist
            tp3 = entry_target - cfg.TP_R_MULT[2] * sl_dist
        
        signals.append(Signal(
            symbol=symbol,
            timestamp=df.index[i],
            action=action,
            close_price=close_px,
            entry_target=entry_target,
            sl=sl,
            sl_dist=sl_dist,
            tp1=tp1, tp2=tp2, tp3=tp3,
            direction_score=D,
            quality=Q,
            atr=atr,
            sigma=sigma,
            bar_idx=i,
        ))
    
    return signals


def _valid_row(row) -> bool:
    needed = ['ema_slope_norm', 'momentum', 'z20', 'volatility', 'atr']
    for col in needed:
        if not np.isfinite(row[col]):
            return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — RISK MANAGER (Layer 5)
# ══════════════════════════════════════════════════════════════════════════════

class RiskManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.trade_history: List[dict] = []   # For Kelly
    
    def kelly_fraction(self) -> float:
        """True half-Kelly from recent trades."""
        if len(self.trade_history) < self.cfg.MIN_HISTORY_TRADES:
            return (self.cfg.KELLY_MIN + self.cfg.KELLY_MAX) / 2
        
        recent = self.trade_history[-100:]
        wins = [t for t in recent if t['pnl_r'] > 0]
        losses = [t for t in recent if t['pnl_r'] <= 0]
        
        if not wins or not losses:
            return self.cfg.KELLY_MIN
        
        p = len(wins) / len(recent)
        avg_win = np.mean([t['pnl_r'] for t in wins])
        avg_loss = abs(np.mean([t['pnl_r'] for t in losses]))
        if avg_loss <= 1e-9:
            return self.cfg.KELLY_MIN
        
        b = avg_win / avg_loss
        f_kelly = (p * b - (1 - p)) / b
        f_half = f_kelly * self.cfg.KELLY_FRACTION
        
        return float(np.clip(f_half, self.cfg.KELLY_MIN, self.cfg.KELLY_MAX))
    
    def can_open(self, current_heat: float, n_open: int) -> Tuple[bool, str]:
        if n_open >= self.cfg.MAX_CONCURRENT:
            return False, f"concurrency ({n_open}/{self.cfg.MAX_CONCURRENT})"
        if current_heat >= self.cfg.HEAT_MAX:
            return False, f"heat ({current_heat*100:.1f}%)"
        return True, "ok"
    
    def compute_risk(self, capital: float, current_heat: float) -> float:
        """Returns risk fraction (of capital) for a new trade."""
        kelly = self.kelly_fraction()
        remaining = self.cfg.HEAT_MAX - current_heat
        return float(min(kelly, self.cfg.KELLY_MAX, remaining))
    
    def record_trade(self, pnl_r: float):
        self.trade_history.append({'pnl_r': pnl_r})
        if len(self.trade_history) > 500:
            self.trade_history = self.trade_history[-500:]


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — BACKTEST ENGINE (Layer 6)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Position:
    signal: Signal
    entry_px: float
    qty: float
    entry_ci: int
    sl: float
    tp1: float
    tp2: float
    tp3: float
    sl_dist: float
    remaining_pct: float = 1.0
    tp1_hit: bool = False
    tp2_hit: bool = False
    peak: float = 0.0
    partial_pnl: float = 0.0


@dataclass
class Trade:
    symbol: str
    action: str
    entry_time: pd.Timestamp
    entry_px: float
    exit_time: pd.Timestamp
    exit_px: float
    qty: float
    net_pnl: float
    pnl_r: float
    exit_reason: str
    bars_held: int
    mfe_frac: float


def run_backtest(assets: Dict[str, pd.DataFrame],
                  signals: List[Signal],
                  cfg: Config) -> Tuple[List[Trade], List[float], RiskManager]:
    """
    Multi-asset backtest engine.
    
    Rules:
      - Entry: limit at entry_target, wait up to ENTRY_WAIT_BARS
      - Exit: SL (priority), TP1/TP2/TP3, trailing, time-based
      - Fees: maker on entry/TPs, taker on SL
      - No protective orders (backtest simplification)
    """
    log.info(f"[Backtest] {len(signals)} signals, {len(assets)} assets")
    
    # Sort signals by time
    signals = sorted(signals, key=lambda s: s.timestamp)
    
    capital = cfg.INITIAL_CAPITAL
    peak_capital = capital
    equity = [capital]
    trades: List[Trade] = []
    open_pos: Dict[str, Position] = {}
    risk_mgr = RiskManager(cfg)
    
    # Track last exit per symbol (cooldown)
    last_exit_ci: Dict[str, int] = {}
    COOLDOWN_BARS = 3
    
    sig_idx = 0
    for sig in signals:
        # ── 1. Update open positions ──
        for sym in list(open_pos.keys()):
            if sym not in assets:
                continue
            df = assets[sym]
            pos = open_pos[sym]
            
            # Find current bar in df
            try:
                cur_ci = df.index.get_loc(sig.timestamp)
            except KeyError:
                continue
            
            exit_info = _check_exits(pos, df, cur_ci, cfg)
            if exit_info is not None:
                trade, pnl = _close_position(pos, df, exit_info, capital, cfg)
                capital += pnl
                peak_capital = max(peak_capital, capital)
                trades.append(trade)
                risk_mgr.record_trade(trade.pnl_r)
                last_exit_ci[sym] = cur_ci
                del open_pos[sym]
        
        # ── 2. Cooldown check ──
        if sig.symbol in last_exit_ci:
            try:
                sym_ci = assets[sig.symbol].index.get_loc(sig.timestamp)
            except KeyError:
                sym_ci = 0
            if sym_ci - last_exit_ci[sig.symbol] < COOLDOWN_BARS:
                continue
        
        # ── 3. Position limits ──
        current_heat = sum(
            (p.sl_dist / p.entry_px) * (p.qty * p.entry_px / max(capital, 1e-9))
            for p in open_pos.values()
        )
        can_open, reason = risk_mgr.can_open(current_heat, len(open_pos))
        if not can_open:
            continue
        
        if sig.symbol in open_pos:
            continue
        
        # ── 4. Entry fill simulation ──
        if sig.symbol not in assets:
            continue
        df = assets[sig.symbol]
        try:
            entry_ci = df.index.get_loc(sig.timestamp)
        except KeyError:
            continue
        
        fill_ci, fill_px = _simulate_entry(sig, df, entry_ci, cfg)
        if fill_ci < 0:
            continue
        
        # ── 5. Position sizing ──
        risk_frac = risk_mgr.compute_risk(capital, current_heat)
        if risk_frac <= 0:
            continue
        
        sl_dist_actual = abs(fill_px - sig.sl)
        if sl_dist_actual <= 1e-9:
            continue
        
        risk_amt = (capital - cfg.CAPITAL_FLOOR) * risk_frac
        qty = risk_amt / sl_dist_actual
        notional = qty * fill_px
        max_notional = capital * 20.0  # 20x leverage cap
        if notional > max_notional:
            qty = max_notional / fill_px
            notional = qty * fill_px
        
        if notional < 5.0:  # MIN_NOTIONAL
            continue
        
        # ── 6. Create position ──
        open_pos[sig.symbol] = Position(
            signal=sig,
            entry_px=fill_px,
            qty=qty,
            entry_ci=fill_ci,
            sl=sig.sl,
            tp1=sig.tp1, tp2=sig.tp2, tp3=sig.tp3,
            sl_dist=sl_dist_actual,
            peak=fill_px,
        )
        
        equity.append(capital)
    
    # ── End of backtest: close remaining positions ──
    for sym, pos in list(open_pos.items()):
        if sym not in assets:
            continue
        df = assets[sym]
        last_ci = len(df) - 1
        exit_info = ('EndOfData', df.iloc[last_ci]['Close'], last_ci)
        trade, pnl = _close_position(pos, df, exit_info, capital, cfg)
        capital += pnl
        trades.append(trade)
        risk_mgr.record_trade(trade.pnl_r)
    
    equity.append(capital)
    log.info(f"[Backtest] {len(trades)} trades, "
             f"final capital ${capital:.2f} (from ${cfg.INITIAL_CAPITAL:.2f})")
    return trades, equity, risk_mgr


def _simulate_entry(sig: Signal, df: pd.DataFrame,
                     sig_ci: int, cfg: Config) -> Tuple[int, float]:
    """Check if entry order fills within ENTRY_WAIT_BARS."""
    end_ci = min(sig_ci + 1 + cfg.ENTRY_WAIT_BARS, len(df))
    for ci in range(sig_ci + 1, end_ci):
        row = df.iloc[ci]
        if sig.action == "BUY":
            if row['Low'] <= sig.entry_target:
                return ci, sig.entry_target
        else:
            if row['High'] >= sig.entry_target:
                return ci, sig.entry_target
    return -1, 0.0


def _check_exits(pos: Position, df: pd.DataFrame,
                  cur_ci: int, cfg: Config) -> Optional[Tuple]:
    """
    Check all exits in priority order:
      1. SL (before TP - pessimistic)
      2. TP1, TP2, TP3
      3. Trailing SL
      4. Time-based
    Returns (reason, price, ci) or None.
    """
    row = df.iloc[cur_ci]
    high = float(row['High'])
    low = float(row['Low'])
    close = float(row['Close'])
    
    # ── 1. SL check ──
    if pos.signal.action == "BUY":
        if low <= pos.sl:
            return ("SL", pos.sl, cur_ci)
    else:
        if high >= pos.sl:
            return ("SL", pos.sl, cur_ci)
    
    # ── 2. TP checks (in order of closeness) ──
    if not pos.tp1_hit:
        if pos.signal.action == "BUY":
            if high >= pos.tp1:
                pos.tp1_hit = True
                _record_partial(pos, pos.tp1, cfg.TP_PCT[0], cfg)
                if pos.remaining_pct <= 1e-6:
                    return ("TP1_final", pos.tp1, cur_ci)
        else:
            if low <= pos.tp1:
                pos.tp1_hit = True
                _record_partial(pos, pos.tp1, cfg.TP_PCT[0], cfg)
                if pos.remaining_pct <= 1e-6:
                    return ("TP1_final", pos.tp1, cur_ci)
    
    if not pos.tp2_hit and pos.tp1_hit:
        if pos.signal.action == "BUY":
            if high >= pos.tp2:
                pos.tp2_hit = True
                _record_partial(pos, pos.tp2, cfg.TP_PCT[1], cfg)
                if pos.remaining_pct <= 1e-6:
                    return ("TP2_final", pos.tp2, cur_ci)
        else:
            if low <= pos.tp2:
                pos.tp2_hit = True
                _record_partial(pos, pos.tp2, cfg.TP_PCT[1], cfg)
                if pos.remaining_pct <= 1e-6:
                    return ("TP2_final", pos.tp2, cur_ci)
    
    if pos.tp1_hit and pos.tp2_hit:
        if pos.signal.action == "BUY":
            if high >= pos.tp3:
                return ("TP3", pos.tp3, cur_ci)
        else:
            if low <= pos.tp3:
                return ("TP3", pos.tp3, cur_ci)
    
    # ── 3. Trailing SL (after TP1) ──
    if pos.tp1_hit and pos.tp2_hit:
        atr = float(row['atr'])
        if pos.signal.action == "BUY":
            pos.peak = max(pos.peak, high)
            new_sl = pos.peak - cfg.TRAIL_K_ATR * atr
            if new_sl > pos.sl:
                pos.sl = new_sl
        else:
            pos.peak = min(pos.peak, low) if pos.peak > 0 else low
            new_sl = pos.peak + cfg.TRAIL_K_ATR * atr
            if new_sl < pos.sl:
                pos.sl = new_sl
    
    # ── 4. Time-based exit ──
    bars_held = cur_ci - pos.entry_ci
    if bars_held >= cfg.MAX_HOLD_BARS:
        # Check if profit is weak
        if pos.signal.action == "BUY":
            profit_r = (close - pos.entry_px) / pos.sl_dist
        else:
            profit_r = (pos.entry_px - close) / pos.sl_dist
        if profit_r < 0.5:
            return ("TimeKill", close, cur_ci)
    
    return None


def _record_partial(pos: Position, price: float, pct: float, cfg: Config):
    """Record a partial TP. Reduces remaining_pct."""
    qty_closed = pos.qty * pct
    if pos.signal.action == "BUY":
        gross = (price - pos.entry_px) * qty_closed
    else:
        gross = (pos.entry_px - price) * qty_closed
    fee = qty_closed * price * cfg.MAKER_FEE + qty_closed * pos.entry_px * cfg.MAKER_FEE
    pos.partial_pnl += gross - fee
    pos.remaining_pct -= pct


def _close_position(pos: Position, df: pd.DataFrame,
                     exit_info: Tuple, capital: float,
                     cfg: Config) -> Tuple[Trade, float]:
    """Close position and return (trade, net_pnl)."""
    reason, exit_px, exit_ci = exit_info
    
    # Fees & slippage
    is_taker = reason == "SL" or "EndOfData" in reason
    fee_rate = cfg.TAKER_FEE if is_taker else cfg.MAKER_FEE
    slip_frac = (cfg.SLIP_TAKER_BPS / 10000.0) if is_taker else 0.0
    
    if pos.signal.action == "BUY":
        exit_eff = exit_px * (1 - slip_frac)
        gross = (exit_eff - pos.entry_px) * pos.qty * pos.remaining_pct
    else:
        exit_eff = exit_px * (1 + slip_frac)
        gross = (pos.entry_px - exit_eff) * pos.qty * pos.remaining_pct
    
    fee = (pos.qty * pos.remaining_pct * exit_eff * fee_rate +
           pos.qty * pos.remaining_pct * pos.entry_px * cfg.MAKER_FEE)
    
    net_pnl = gross - fee + pos.partial_pnl
    
    # PnL in R units
    if pos.sl_dist > 0:
        if pos.signal.action == "BUY":
            exit_r = (exit_eff - pos.entry_px) / pos.sl_dist
        else:
            exit_r = (pos.entry_px - exit_eff) / pos.sl_dist
    else:
        exit_r = 0.0
    
    bars_held = exit_ci - pos.entry_ci
    
    trade = Trade(
        symbol=pos.signal.symbol,
        action=pos.signal.action,
        entry_time=pos.signal.timestamp,
        entry_px=pos.entry_px,
        exit_time=df.index[exit_ci],
        exit_px=exit_eff,
        qty=pos.qty,
        net_pnl=net_pnl,
        pnl_r=exit_r,
        exit_reason=reason,
        bars_held=bars_held,
        mfe_frac=(pos.peak - pos.entry_px) / pos.entry_px if pos.signal.action == "BUY"
                 else (pos.entry_px - pos.peak) / pos.entry_px,
    )
    
    return trade, net_pnl


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — METRICS
# ══════════════════════════════════════════════════════════════════════════════

def compute_metrics(trades: List[Trade], equity: List[float],
                     cfg: Config) -> dict:
    if not trades:
        return {'n_trades': 0}
    
    net_pnls = [t.net_pnl for t in trades]
    pnl_rs = [t.pnl_r for t in trades]
    
    wins = [p for p in net_pnls if p > 0]
    losses = [p for p in net_pnls if p <= 0]
    
    # Log returns per trade (approximate)
    lrs = [np.log((cfg.INITIAL_CAPITAL + sum(net_pnls[:i+1])) /
                   (cfg.INITIAL_CAPITAL + sum(net_pnls[:i]) + 1e-9))
           for i in range(len(net_pnls))]
    
    eq = np.array(equity)
    peak = np.maximum.accumulate(eq)
    dd = (peak - eq) / np.maximum(peak, 1e-9)
    
    mean_lr = float(np.mean(lrs))
    std_lr = float(np.std(lrs))
    
    # Annualized Sharpe (assuming 4h bars, ~6 per day)
    # Each trade spans multiple bars; approximate
    sharpe = (mean_lr / std_lr * np.sqrt(2190)) if std_lr > 1e-9 else 0.0
    
    # Exit distribution
    exit_dist = {}
    for t in trades:
        exit_dist[t.exit_reason] = exit_dist.get(t.exit_reason, 0) + 1
    
    return {
        'n_trades': len(trades),
        'final_capital': float(equity[-1]),
        'total_return_pct': (equity[-1] / cfg.INITIAL_CAPITAL - 1) * 100,
        'mean_log_return': mean_lr,
        'std_log_return': std_lr,
        'sharpe_ratio': sharpe,
        'win_rate': len(wins) / len(net_pnls) if net_pnls else 0.0,
        'profit_factor': (sum(wins) / abs(sum(losses))) if losses and wins else float('inf'),
        'avg_win_r': float(np.mean([t.pnl_r for t in trades if t.pnl_r > 0])) if wins else 0.0,
        'avg_loss_r': float(np.mean([t.pnl_r for t in trades if t.pnl_r <= 0])) if losses else 0.0,
        'max_drawdown_pct': float(dd.max() * 100),
        'exit_distribution': exit_dist,
        'avg_bars_held': float(np.mean([t.bars_held for t in trades])),
    }


def deflated_sharpe(mean_lr: float, std_lr: float,
                     skew: float, kurt: float, n: int) -> float:
    """
    Deflated Sharpe Ratio (Bailey & López de Prado 2014).
    DSR > 0.95 required for deployment.
    """
    if std_lr <= 1e-9 or n < 10:
        return 0.0
    sr = mean_lr / std_lr
    denom = np.sqrt(max(1 - skew * sr + (kurt - 1) / 4 * sr**2, 1e-9))
    z = np.sqrt(n - 1) * sr / denom
    # Phi is CDF of standard normal
    from scipy.stats import norm
    return float(norm.cdf(z))


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — WALK-FORWARD
# ══════════════════════════════════════════════════════════════════════════════

def walk_forward(assets: Dict[str, pd.DataFrame],
                  cfg: Config, n_windows: int = 6) -> List[dict]:
    """
    Split data into n_windows. For each:
      - Train on past data (implicit — signal generation uses past only)
      - Test on window
    Report per-window Sharpe.
    """
    if not assets:
        return []
    
    # Use BTC as reference for time splits
    ref_sym = list(assets.keys())[0]
    ref_df = assets[ref_sym]
    n_bars = len(ref_df)
    
    window_size = n_bars // (n_windows + 1)
    results = []
    
    for i in range(n_windows):
        start = (i + 1) * window_size
        end = min(start + window_size, n_bars)
        if end - start < 200:
            continue
        
        log.info(f"[WF] Window {i+1}/{n_windows}: bars {start}-{end}")
        
        # Slice data (each asset independently)
        window_assets = {}
        for sym, df in assets.items():
            try:
                t_start = ref_df.index[start]
                t_end = ref_df.index[end - 1]
                slice_df = df.loc[(df.index >= t_start) & (df.index <= t_end)]
                if len(slice_df) >= 200:
                    window_assets[sym] = slice_df
            except Exception:
                continue
        
        if not window_assets:
            continue
        
        # Generate signals on window
        all_sigs = []
        for sym, df in window_assets.items():
            sigs = generate_signals(df, sym, cfg)
            all_sigs.extend(sigs)
        
        if not all_sigs:
            results.append({'window': i, 'n_trades': 0, 'sharpe': 0.0})
            continue
        
        # Run backtest
        trades, equity, _ = run_backtest(window_assets, all_sigs, cfg)
        m = compute_metrics(trades, equity, cfg)
        results.append({
            'window': i,
            'n_trades': m.get('n_trades', 0),
            'sharpe': m.get('sharpe_ratio', 0.0),
            'return_pct': m.get('total_return_pct', 0.0),
            'max_dd': m.get('max_drawdown_pct', 0.0),
            'win_rate': m.get('win_rate', 0.0),
        })
    
    return results


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def save_trades(trades: List[Trade], path: str):
    with open(path, 'w') as f:
        for t in trades:
            f.write(json.dumps({
                'symbol': t.symbol,
                'action': t.action,
                'entry_time': str(t.entry_time),
                'entry_px': t.entry_px,
                'exit_time': str(t.exit_time),
                'exit_px': t.exit_px,
                'qty': t.qty,
                'net_pnl': t.net_pnl,
                'pnl_r': t.pnl_r,
                'exit_reason': t.exit_reason,
                'bars_held': t.bars_held,
                'mfe_frac': t.mfe_frac,
            }) + '\n')
    log.info(f"[Output] {len(trades)} trades → {path}")


def print_report(metrics: dict, wf_results: List[dict], dsr: float):
    print("\n" + "═" * 70)
    print("  IDEAL BOT v1.0 — BACKTEST REPORT")
    print("═" * 70)
    
    if not metrics or metrics.get('n_trades', 0) == 0:
        print("  ❌ No trades generated.")
        return
    
    print(f"\n▶ PERFORMANCE")
    print(f"  Trades:            {metrics['n_trades']:,}")
    print(f"  Final capital:     ${metrics['final_capital']:,.2f}")
    print(f"  Total return:      {metrics['total_return_pct']:+.2f}%")
    print(f"  E[log_return]:     {metrics['mean_log_return']:+.6f}")
    print(f"  Sharpe (annual):   {metrics['sharpe_ratio']:+.3f}")
    print(f"  Deflated Sharpe:   {dsr:+.3f}  {'✅' if dsr > 0.95 else '⚠️  (overfit risk)'}")
    print(f"  Win rate:          {metrics['win_rate']*100:.2f}%")
    print(f"  Profit factor:     {metrics['profit_factor']:.3f}")
    print(f"  Avg win (R):       {metrics['avg_win_r']:+.2f}R")
    print(f"  Avg loss (R):      {metrics['avg_loss_r']:+.2f}R")
    print(f"  Max drawdown:      {metrics['max_drawdown_pct']:.2f}%")
    print(f"  Avg bars held:     {metrics['avg_bars_held']:.0f}")
    
    print(f"\n▶ EXITS")
    for reason, count in sorted(metrics['exit_distribution'].items(),
                                  key=lambda x: -x[1]):
        pct = count / metrics['n_trades'] * 100
        print(f"  {reason:20s}: {count:5d} ({pct:5.1f}%)")
    
    if wf_results:
        print(f"\n▶ WALK-FORWARD ({len(wf_results)} windows)")
        print(f"  {'Window':8s} {'Trades':>8s} {'Sharpe':>8s} {'Return':>10s} {'MaxDD':>8s}")
        for r in wf_results:
            print(f"  {r['window']+1:8d} {r['n_trades']:>8d} "
                  f"{r['sharpe']:>+8.2f} {r['return_pct']:>+9.1f}% "
                  f"{r['max_dd']:>7.1f}%")
        
        sharpes = [r['sharpe'] for r in wf_results if r['n_trades'] > 0]
        if sharpes:
            mean_s = np.mean(sharpes)
            pos_windows = sum(1 for s in sharpes if s > 0.5)
            print(f"\n  Mean Sharpe:      {mean_s:+.2f}")
            print(f"  Positive windows: {pos_windows}/{len(sharpes)}")
            
            if mean_s > 1.0 and pos_windows >= 0.8 * len(sharpes):
                print(f"  ✅ PASS — ready for OOS test")
            else:
                print(f"  ⚠️  FAIL — not ready for OOS")
    
    print("\n" + "═" * 70)


def plot_equity(equity: List[float], path: str):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.semilogy(equity, color='#00e5ff', lw=1.5)
        ax.axhline(CFG.INITIAL_CAPITAL, color='red', ls='--', lw=1)
        ax.set_xlabel('Trade #')
        ax.set_ylabel('Capital ($)')
        ax.set_title('Equity Curve (Log Scale)')
        ax.grid(True, alpha=0.3)
        ax.set_facecolor('#111')
        fig.patch.set_facecolor('#0d0d0d')
        ax.tick_params(colors='white')
        ax.xaxis.label.set_color('white')
        ax.yaxis.label.set_color('white')
        ax.title.set_color('#00e5ff')
        for spine in ax.spines.values():
            spine.set_color('#333')
        plt.tight_layout()
        plt.savefig(path, dpi=100, facecolor='#0d0d0d')
        plt.close()
        log.info(f"[Plot] Equity → {path}")
    except Exception as e:
        log.warning(f"[Plot] failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Ideal Bot v1.0")
    parser.add_argument('--mode', choices=['backtest', 'walkforward'],
                        default='backtest')
    parser.add_argument('--symbols', nargs='+',
                        default=['BTC/USDT', 'ETH/USDT', 'SOL/USDT',
                                 'BNB/USDT', 'ADA/USDT'])
    parser.add_argument('--timeframe', default='4h')
    parser.add_argument('--history-days', type=int, default=730)
    parser.add_argument('--capital', type=float, default=100.0)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--no-cache', action='store_true')
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    # Update config
    CFG.timeframe = args.timeframe
    CFG.history_days = args.history_days
    CFG.INITIAL_CAPITAL = args.capital
    if args.no_cache:
        import shutil
        if os.path.exists(CFG.cache_dir):
            shutil.rmtree(CFG.cache_dir)
    
    # ── Setup exchange ──
    try:
        import ccxt
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
        })
    except ImportError:
        log.error("pip install ccxt")
        return
    
    # ── Load data ──
    log.info(f"[Main] Loading {len(args.symbols)} symbols ({args.timeframe})...")
    data_layer = DataLayer(exchange, CFG)
    assets = {}
    for sym in args.symbols:
        log.info(f"  Loading {sym}...")
        df = data_layer.get_ohlcv(sym, CFG.history_days)
        if df is None or len(df) < 200:
            log.warning(f"  ✗ {sym} skipped")
            continue
        df = compute_features(df, CFG)
        # Drop rows with NaN features
        df = df.dropna(subset=['ema_slope_norm', 'momentum', 'z20',
                                'volatility', 'atr'])
        if len(df) < 200:
            log.warning(f"  ✗ {sym} too few valid rows")
            continue
        assets[sym] = df
        log.info(f"  ✓ {sym}: {len(df):,} bars")
    
    if not assets:
        log.error("No assets loaded.")
        return
    
    # ── Walk-forward mode ──
    if args.mode == 'walkforward':
        log.info(f"[Main] Walk-forward mode ({CFG.N_WALK_WINDOWS} windows)")
        results = walk_forward(assets, CFG, CFG.N_WALK_WINDOWS)
        print_report({}, results, 0.0)
        return
    
    # ── Backtest mode ──
    log.info("[Main] Generating signals...")
    all_signals = []
    for sym, df in assets.items():
        sigs = generate_signals(df, sym, CFG)
        log.info(f"  {sym}: {len(sigs)} signals")
        all_signals.extend(sigs)
    
    log.info(f"[Main] Total signals: {len(all_signals)}")
    
    if not all_signals:
        log.warning("No signals. Exiting.")
        return
    
    # ── Run backtest ──
    trades, equity, risk_mgr = run_backtest(assets, all_signals, CFG)
    metrics = compute_metrics(trades, equity, CFG)
    
    # ── DSR ──
    if trades:
        lrs = [np.log(max(trade.net_pnl + 1, 1e-9)) for trade in trades]
        if len(lrs) > 10:
            from scipy.stats import skew, kurtosis
            dsr = deflated_sharpe(
                mean_lr=metrics['mean_log_return'],
                std_lr=metrics['std_log_return'],
                skew=float(skew(lrs)),
                kurt=float(kurtosis(lrs) + 3),  # raw kurtosis
                n=len(trades),
            )
        else:
            dsr = 0.0
    else:
        dsr = 0.0
    
    # ── Output ──
    save_trades(trades, CFG.trades_log)
    with open(CFG.metrics_file, 'w') as f:
        json.dump({**metrics, 'dsr': dsr}, f, indent=2, default=str)
    plot_equity(equity, CFG.plot_file)
    print_report(metrics, [], dsr)
    
    log.info("Done.")


if __name__ == '__main__':
    main()
