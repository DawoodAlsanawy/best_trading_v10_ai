#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smart_trailing.py — Multi-Tier ATR Trailing with Close Confirmation

يستبدل أي trailing بسيط في البوت. المبدأ:
  - لا trail قبل ربح كافٍ (trail_activation_atr)
  - مسافة تتبع واسعة (trail_distance_atr) لتحمّل التصحيحات
  - Peak مأخوذ من close لا high (لا إبر)
  - خروج مؤكَّد بإغلاق شمعتين تحت المستوى
  - Ratchet: SL لا يتراجع أبدًا
"""

from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TrailingCfg:
    # Breakeven
    be_atr: float = 1.0
    be_buffer_atr: float = 0.2

    # Trail activation & distance
    trail_activation_atr: float = 1.5
    trail_distance_atr: float = 2.5

    # Tightening near TP
    tighten_trigger_atr: float = 2.0
    tighten_distance_atr: float = 1.0

    # Confirmation
    confirm_bars: int = 2
    use_close_confirmation: bool = True

    # Partial handling: بعد partial، نستخدم مسافة أضيق للجزء المتبقي
    trail_distance_atr_post_partial: float = 0.8


# ═══════════════════════════════════════════════════════════════════════
# Trade state (يُحفظ بين الشموع)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TrailState:
    stage: str = 'INITIAL'          # INITIAL | BE | TRAIL | TIGHTEN
    peak_price: float = 0.0         # أعلى close (long) / أدنى close (short)
    closed_bars: list = field(default_factory=list)  # آخر N close
    partial_taken: bool = False
    last_update_ts: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
# Core update
# ═══════════════════════════════════════════════════════════════════════

def update_trailing(
    *,
    is_long: bool,
    entry_price: float,
    current_sl: float,
    tp_price: float,
    close_now: float,
    atr: float,
    state: TrailState,
    cfg: TrailingCfg,
    bar_ts: Optional[str] = None,
) -> tuple[float, bool]:
    """
    تحديث SL بعد إغلاق شمعة.

    Returns:
        (new_sl, should_exit_now)
        - new_sl: مستوى SL الجديد (ratchet، لن يتراجع)
        - should_exit_now: True إذا انطبق شرط الخروج المؤكَّد
    """

    d = 1.0 if is_long else -1.0

    # ─── 0) تهيئة peak عند أول استدعاء ───
    if state.peak_price == 0.0:
        state.peak_price = entry_price

    # ─── 1) تحديث peak من close ───
    if is_long:
        state.peak_price = max(state.peak_price, close_now)
    else:
        state.peak_price = min(state.peak_price, close_now)

    # ─── 2) حساب ATR-ربح ───
    if atr <= 1e-12:
        return current_sl, False

    profit_atr = (state.peak_price - entry_price) * d / atr
    tp_dist_atr = abs(tp_price - close_now) / atr

    new_sl = current_sl

    # ─── 3) Breakeven ───
    if state.stage == 'INITIAL' and profit_atr >= cfg.be_atr:
        be_sl = entry_price + cfg.be_buffer_atr * atr * d
        if (is_long and be_sl > new_sl) or (not is_long and be_sl < new_sl):
            new_sl = be_sl
        state.stage = 'BE'

    # ─── 4) Trail activation ───
    if state.stage in ('BE', 'TRAIL') and profit_atr >= cfg.trail_activation_atr:
        dist = (cfg.trail_distance_atr_post_partial
                if state.partial_taken
                else cfg.trail_distance_atr)
        trail_sl = state.peak_price - dist * atr * d
        if (is_long and trail_sl > new_sl) or (not is_long and trail_sl < new_sl):
            new_sl = trail_sl
        state.stage = 'TRAIL'

    # ─── 5) Tightening near TP ───
    if (state.stage == 'TRAIL'
            and tp_dist_atr < cfg.tighten_trigger_atr
            and profit_atr >= cfg.trail_activation_atr):
        tighten_sl = close_now - cfg.tighten_distance_atr * atr * d
        if (is_long and tighten_sl > new_sl) or (not is_long and tighten_sl < new_sl):
            new_sl = tighten_sl
        state.stage = 'TIGHTEN'

    # ─── 6) Ratchet guarantee (defensive) ───
    if is_long:
        new_sl = max(new_sl, current_sl)
    else:
        new_sl = min(new_sl, current_sl)

    # ─── 7) Close confirmation ───
    should_exit = False
    if cfg.use_close_confirmation and state.stage in ('TRAIL', 'TIGHTEN'):
        # آخر (confirm_bars - 1) شموع مغلقة + الحالية
        recent = state.closed_bars[-(cfg.confirm_bars - 1):] + [close_now]
        if len(recent) >= cfg.confirm_bars:
            breaches = [(c - new_sl) * d < 0 for c in recent]
            if all(breaches):
                should_exit = True

    # ─── 8) حدّث سجل الشموع ───
    state.closed_bars.append(close_now)
    if len(state.closed_bars) > max(cfg.confirm_bars + 5, 10):
        state.closed_bars.pop(0)

    if bar_ts:
        state.last_update_ts = bar_ts

    return new_sl, should_exit


# ═══════════════════════════════════════════════════════════════════════
# Serialization (لحفظ الحالة بين إعادة التشغيل)
# ═══════════════════════════════════════════════════════════════════════

def state_to_dict(s: TrailState) -> dict:
    return {
        'stage': s.stage,
        'peak_price': s.peak_price,
        'closed_bars': list(s.closed_bars),
        'partial_taken': s.partial_taken,
        'last_update_ts': s.last_update_ts,
    }


def state_from_dict(d: dict) -> TrailState:
    if not d:
        return TrailState()
    return TrailState(
        stage=d.get('stage', 'INITIAL'),
        peak_price=float(d.get('peak_price', 0.0)),
        closed_bars=list(d.get('closed_bars', [])),
        partial_taken=bool(d.get('partial_taken', False)),
        last_update_ts=d.get('last_update_ts'),
    )


# ═══════════════════════════════════════════════════════════════════════
# ATR helper (إن لم يكن لديك واحد)
# ═══════════════════════════════════════════════════════════════════════

def compute_atr(df, window: int = 14) -> float:
    """ATR على آخر شمعة في df. df يجب أن يحتوي High/Low/Close."""
    if len(df) < window + 1:
        return 0.0
    high = df['High'].values
    low = df['Low'].values
    close = df['Close'].values
    tr = []
    for i in range(1, len(df)):
        tr.append(max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        ))
    tr = tr[-window:]
    return float(sum(tr) / len(tr)) if tr else 0.0
