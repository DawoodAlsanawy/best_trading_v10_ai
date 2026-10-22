#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  apply_smart_trailing.sh
#  يدمج smart_trailing.py في trading_2_live4_claude2_v4.py
#  - idempotent: يمكن تشغيله أكثر من مرة بأمان
#  - ينشئ backup قبل التعديل
#  - يتحقق من صحة الصياغة بـ py_compile بعد التعديل
#  - يتراجع تلقائياً عند أي خطأ
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

BOT_FILE="${1:-trading_2_live4_claude2_v4_fix_trailing.py}"

if [ ! -f "$BOT_FILE" ]; then
    echo "✗ ERROR: $BOT_FILE غير موجود"
    exit 1
fi

if [ ! -f "smart_trailing.py" ]; then
    echo "✗ ERROR: smart_trailing.py غير موجود في المجلد الحالي"
    exit 1
fi

if grep -q "SMART-TRAILING-APPLIED" "$BOT_FILE"; then
    echo "ℹ  التعديل مطبَّق مسبقاً — لا شيء للقيام به"
    exit 0
fi

BACKUP="$BOT_FILE.bak.$(date +%Y%m%d_%H%M%S)"
cp "$BOT_FILE" "$BACKUP"
echo "✓ Backup: $BACKUP"

BOT_FILE="$BOT_FILE" python3 <<'PYEOF'
import os, sys, re

bot_file = os.environ["BOT_FILE"]
with open(bot_file, "r", encoding="utf-8") as f:
    content = f.read()
original = content
applied, failed = [], []


def replace_once(name, old, new, marker=None):
    """استبدال آمن: يتخطى إذا كان marker موجوداً مسبقاً."""
    global content
    if marker and marker in content:
        applied.append(f"{name} (already present)")
        return True
    if old not in content:
        failed.append(f"{name} — anchor not found")
        return False
    content = content.replace(old, new, 1)
    applied.append(name)
    return True


# ───────────────────────────────────────────────────────────────────────
# PATCH 1: Imports
# ───────────────────────────────────────────────────────────────────────
PATCH1_ANCHOR = 'warnings.filterwarnings("ignore")\n'
PATCH1_ADD = '''
# ═══ [SMART-TRAILING-APPLIED] ═══════════════════════════════════════════
# Smart multi-tier ATR trailing with close-confirmation (see smart_trailing.py)
from smart_trailing import (
    TrailingCfg as SmartTrailingCfg,
    TrailState as SmartTrailState,
    update_trailing as smart_update_trailing,
    state_to_dict as smart_state_to_dict,
    state_from_dict as smart_state_from_dict,
    compute_atr as smart_compute_atr,
)
# ═════════════════════════════════════════════════════════════════════════

'''
replace_once("PATCH 1 (imports)",
             PATCH1_ANCHOR,
             PATCH1_ANCHOR + PATCH1_ADD,
             marker="from smart_trailing import")


# ───────────────────────────────────────────────────────────────────────
# PATCH 2: OpenPosition dataclass — add trail_state / trailing_cfg
# ───────────────────────────────────────────────────────────────────────
PATCH2_OLD = '''    partial_taken: bool = False      # [FIX 4]
    partial_pnl: float = 0.0         # [FIX 4] accumulated partial profit
'''
PATCH2_NEW = '''    partial_taken: bool = False      # [FIX 4]
    partial_pnl: float = 0.0         # [FIX 4] accumulated partial profit
    # ══ [SMART-TRAILING] stateful trailing ══
    trail_state: object = None       # SmartTrailState
    trailing_cfg: object = None      # SmartTrailingCfg
'''
replace_once("PATCH 2 (OpenPosition fields)",
             PATCH2_OLD, PATCH2_NEW,
             marker="trail_state: object = None")


# ───────────────────────────────────────────────────────────────────────
# PATCH 3: Remove sub-bar trailing block in _advance
# ───────────────────────────────────────────────────────────────────────
PATCH3_OLD = '''                # Legacy trailing (uses sub-bar high/low as peak candidate)
                _td = pos.trail_dist_frac if pos.trail_dist_frac > 0 else CFG.TRAIL_DISTANCE
                _ta = pos.trail_activate_frac if pos.trail_activate_frac > 0 else CFG.TRAIL_ACTIVATE_MFE
                # ══ [FIX 1] Activation tied to R-multiple, not fixed MFE ══
                _sl_frac_init = (pos.sl_dist_initial / pos.entry_px
                                 if pos.entry_px > 0 and pos.sl_dist_initial > 0
                                 else 0.01)
                _act_at_r = float(getattr(CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
                _ta_eff = _sl_frac_init * _act_at_r
                if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:
                    if sig.action == "BUY":
                        peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                        if s_high > peak:
                            peak = s_high; pos.peak_price = peak
                        new_sl = peak * (1.0 - _td)
                        if new_sl > trail_sl * (1.0 + CFG.TRAIL_MIN_STEP):
                            trail_sl = new_sl
                    else:
                        peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                        if s_low < peak or peak == 0:
                            peak = s_low; pos.peak_price = peak
                        new_sl = peak * (1.0 + _td)
                        if new_sl < trail_sl * (1.0 - CFG.TRAIL_MIN_STEP):
                            trail_sl = new_sl
'''
PATCH3_NEW = '''                # ══ [SMART-TRAILING] sub-bar peak tracking only (SL moves on bar close) ══
                if sig.action == "BUY":
                    if s_high > pos.peak_price:
                        pos.peak_price = s_high
                else:
                    if pos.peak_price == 0 or s_low < pos.peak_price:
                        pos.peak_price = s_low
'''
replace_once("PATCH 3 (sub-bar trailing removed)",
             PATCH3_OLD, PATCH3_NEW,
             marker="[SMART-TRAILING] sub-bar peak tracking only")


# ───────────────────────────────────────────────────────────────────────
# PATCH 4: Remove main-bar trailing block in _advance
# ───────────────────────────────────────────────────────────────────────
PATCH4_OLD = '''            _td = pos.trail_dist_frac if pos.trail_dist_frac > 0 else CFG.TRAIL_DISTANCE
            _ta = pos.trail_activate_frac if pos.trail_activate_frac > 0 else CFG.TRAIL_ACTIVATE_MFE
            # ══ [FIX 1] Activation tied to R-multiple, not fixed MFE ══
            _sl_frac_init = (pos.sl_dist_initial / pos.entry_px
                             if pos.entry_px > 0 and pos.sl_dist_initial > 0
                             else 0.01)
            _act_at_r = float(getattr(CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
            _ta_eff = _sl_frac_init * _act_at_r
            if CFG.TRAIL_ENABLED and pos.mfe_frac >= _ta_eff:
                if sig.action == "BUY":
                    peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                    if high > peak:
                        peak = high; pos.peak_price = peak
                    new_sl = peak * (1.0 - _td)
                    if new_sl > trail_sl * (1.0 + CFG.TRAIL_MIN_STEP):
                        trail_sl = new_sl
                else:
                    peak = pos.peak_price if pos.peak_price > 0 else pos.entry_px
                    if low < peak or peak == 0:
                        peak = low; pos.peak_price = peak
                    new_sl = peak * (1.0 + _td)
                    if new_sl < trail_sl * (1.0 - CFG.TRAIL_MIN_STEP):
                        trail_sl = new_sl
'''
PATCH4_NEW = '''            # ══ [SMART-TRAILING] main-bar peak tracking only (SL moves below) ══
            if sig.action == "BUY":
                if high > pos.peak_price:
                    pos.peak_price = high
            else:
                if pos.peak_price == 0 or low < pos.peak_price:
                    pos.peak_price = low
'''
replace_once("PATCH 4 (main-bar trailing removed)",
             PATCH4_OLD, PATCH4_NEW,
             marker="[SMART-TRAILING] main-bar peak tracking only")


# ───────────────────────────────────────────────────────────────────────
# PATCH 5: Insert smart-trail update inside _advance (once per bar)
# ───────────────────────────────────────────────────────────────────────
PATCH5_ANCHOR = '''        # ── Physics-based exits (close-only, per main bar) ──
        is_apex, apex_rsn = False, ""
'''
PATCH5_INSERT = '''        # ══ [SMART-TRAILING] Update trailing once per main bar close ══
        # Runs after sub-bar SL/TP checks, before physics exits.
        # Uses bar close (not wick) as close_now, ratchets SL monotonic.
        if (CFG.TRAIL_ENABLED
                and cidx > pos.entry_ci
                and pos.trail_state is not None):
            try:
                _bar_close = float(ad.closes[cidx])
                _bar_atr = float(ad.atr14[cidx]) if cidx < len(ad.atr14) else 0.0
                if _bar_atr <= 0 and fi >= 0 and fi < len(ad.E_therm):
                    _bar_atr = float(ad.E_therm[fi]) * pos.entry_px

                _new_sl, _should_exit = smart_update_trailing(
                    is_long=(sig.action == "BUY"),
                    entry_price=pos.entry_px,
                    current_sl=trail_sl,
                    tp_price=sig.tp1,
                    close_now=_bar_close,
                    atr=_bar_atr,
                    state=pos.trail_state,
                    cfg=pos.trailing_cfg or SmartTrailingCfg(),
                )
                if _new_sl != trail_sl:
                    trail_sl = _new_sl
                    pos.trail_sl = trail_sl
                    log.debug(
                        f"[SmartTrail-BT] {sig.symbol} "
                        f"stage={pos.trail_state.stage} "
                        f"SL={trail_sl:.6f}"
                    )
                if _should_exit:
                    pos.trail_sl = trail_sl
                    pos.current_ci = cidx
                    return _bar_close, "TRAIL_CONFIRMED", cidx
            except Exception as _ste:
                log.debug(f"[SmartTrail-BT] {sig.symbol} err: {_ste}")

        # ── Physics-based exits (close-only, per main bar) ──
        is_apex, apex_rsn = False, ""
'''
replace_once("PATCH 5 (smart trail update in _advance)",
             PATCH5_ANCHOR, PATCH5_INSERT,
             marker="[SMART-TRAILING] Update trailing once per main bar close")


# ───────────────────────────────────────────────────────────────────────
# PATCH 6: Backtest position creation — init trail_state
# ───────────────────────────────────────────────────────────────────────
PATCH6_OLD = '''            sl_dist_initial=float(abs(eff_px - sl_h)),
            trail_peak_R=0.0,
            entry_sub_idx=opt_sub_idx,
        )
'''
PATCH6_NEW = '''            sl_dist_initial=float(abs(eff_px - sl_h)),
            trail_peak_R=0.0,
            entry_sub_idx=opt_sub_idx,
            # ══ [SMART-TRAILING] fresh state per position ══
            trail_state=SmartTrailState(),
            trailing_cfg=SmartTrailingCfg(),
        )
'''
replace_once("PATCH 6 (backtest position init)",
             PATCH6_OLD, PATCH6_NEW,
             marker="trail_state=SmartTrailState()")


# ───────────────────────────────────────────────────────────────────────
# PATCH 7: Live trailing — replace σ-scaled block with smart trailing
# ───────────────────────────────────────────────────────────────────────
PATCH7_OLD = '''                # ── Trailing SL (dynamic σ-scaled) ──
                # [GATE] يُشغّل Trailing فقط إذا كان TRAIL_ENABLED=True.
                # إذا كان False، لا يتحرك SL أبداً بعد الدخول (يبقى كما
                # وُضع عند الدخول). هذا مطابق لسلوك الباكتيست.
                if not ex and getattr(CFG, 'TRAIL_ENABLED', True):
                    entry_px = float(pos['entry'])
                    _sl_before = float(pos['sl'])
                    _td = float(pos.get('trail_dist_frac', CFG.TRAIL_DISTANCE))
                    # ══ [FIX 1] Activation at R-multiple of initial SL ══
                    _sl_dist_init = float(pos.get('sl_dist_initial', 0) or 0)
                    _sl_frac_init = (_sl_dist_init / entry_px
                                     if entry_px > 0 and _sl_dist_init > 0
                                     else 0.01)
                    _act_at_r = float(getattr(CFG, 'TRAIL_ACTIVATE_AT_R', 1.0))
                    _ta = _sl_frac_init * _act_at_r

                    # Update peak from live price and compute MFE
                    if pos['action'] == "BUY":
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price > cur_peak:
                            pos['peak_price'] = price
                            cur_peak = price
                        _mfe = (cur_peak - entry_px) / entry_px
                    else:
                        cur_peak = float(pos.get('peak_price', entry_px))
                        if price < cur_peak or cur_peak == entry_px:
                            pos['peak_price'] = price
                            cur_peak = price
                        _mfe = (entry_px - cur_peak) / entry_px

                    if _mfe >= _ta:
                        if pos['action'] == "BUY":
                            new_sl = cur_peak * (1.0 - _td)
                            if new_sl > pos['sl']:
                                pos['sl'] = new_sl
                        else:
                            new_sl = cur_peak * (1.0 + _td)
                            if new_sl < pos['sl']:
                                pos['sl'] = new_sl

                    # ══ [LAYER 7] If SL moved, sync protective orders ══
                    if (getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True)
                            and abs(float(pos['sl']) - _sl_before) > 1e-12):
                        try:
                            _sync_protective_orders(exchange, sym, pos)
                        except Exception as _e:
                            log.debug(f"[Prot] {sym} sync error: {_e}")
'''
PATCH7_NEW = '''                # ── [SMART-TRAILING] Bar-close confirmed trailing SL ──
                # يُحدَّث مرة واحدة عند إغلاق كل شمعة (لا wick-based).
                # يستخدم close كقمة، ويُحدِّث SL بمقادير واسعة (2.5 ATR)
                # بحيث لا يلتقط التصحيحات الصغيرة.
                if not ex and getattr(CFG, 'TRAIL_ENABLED', True) and ad is not None:
                    try:
                        if len(ad.timestamps) >= 2:
                            _last_closed_ts = int(ad.timestamps[-2].value)
                            _last_update_ts = int(pos.get('_trail_last_bar_ts', 0))
                            if _last_closed_ts > _last_update_ts:
                                _bar_close = float(ad.closes[-2])
                                _bar_atr = (float(ad.atr14[-2])
                                            if len(ad.atr14) >= 2 else 0.0)
                                if _bar_atr <= 0:
                                    _fi_tr = max(0, len(ad.E_therm) - 2)
                                    _bar_atr = (float(ad.E_therm[_fi_tr])
                                                * float(pos['entry'])
                                                if _fi_tr < len(ad.E_therm) else 0.0)

                                _state_d = pos.get('_trail_state')
                                _state = (smart_state_from_dict(_state_d)
                                          if _state_d else SmartTrailState())
                                _cfg_tr = SmartTrailingCfg()

                                _sl_before = float(pos['sl'])
                                _new_sl, _should_exit = smart_update_trailing(
                                    is_long=(pos['action'] == "BUY"),
                                    entry_price=float(pos['entry']),
                                    current_sl=_sl_before,
                                    tp_price=float(pos['tp1']),
                                    close_now=_bar_close,
                                    atr=_bar_atr,
                                    state=_state,
                                    cfg=_cfg_tr,
                                )
                                pos['_trail_state'] = smart_state_to_dict(_state)
                                pos['_trail_last_bar_ts'] = _last_closed_ts

                                if _new_sl != _sl_before:
                                    pos['sl'] = _new_sl
                                    log.info(
                                        f"[SmartTrail-Live] {sym} "
                                        f"stage={_state.stage} "
                                        f"SL {_sl_before:.6f}→{_new_sl:.6f}"
                                    )
                                    if getattr(CFG, 'PROTECTIVE_ORDERS_ENABLED', True):
                                        try:
                                            _sync_protective_orders(exchange, sym, pos)
                                        except Exception as _e:
                                            log.debug(f"[Prot] {sym} sync err: {_e}")

                                if _should_exit:
                                    ex = True; rsn = "TRAIL_CONFIRMED"
                    except Exception as _ste:
                        log.debug(f"[SmartTrail-Live] {sym} err: {_ste}")
'''
replace_once("PATCH 7 (live trailing replaced)",
             PATCH7_OLD, PATCH7_NEW,
             marker="[SMART-TRAILING] Bar-close confirmed trailing SL")


# ───────────────────────────────────────────────────────────────────────
# PATCH 8: Live position creation (immediate) — init trail state
# ───────────────────────────────────────────────────────────────────────
PATCH8_OLD = '''                            '_sym': sym,
                            '_orig_score': float(sig.score),
                        }

                        log.info(f"✅ [Entry] {sig.action} {sym} @ {entry_price:.6f} "
'''
PATCH8_NEW = '''                            '_sym': sym,
                            '_orig_score': float(sig.score),
                            # ══ [SMART-TRAILING] live state ══
                            '_trail_state': None,
                            '_trail_last_bar_ts': 0,
                        }

                        log.info(f"✅ [Entry] {sig.action} {sym} @ {entry_price:.6f} "
'''
replace_once("PATCH 8 (immediate live pos init)",
             PATCH8_OLD, PATCH8_NEW,
             marker="'_trail_last_bar_ts': 0,")


# ───────────────────────────────────────────────────────────────────────
# PATCH 9: _promote_pending_to_position — init trail state
# ───────────────────────────────────────────────────────────────────────
PATCH9_OLD = '''        '_sym': sym,
        '_orig_score': float(rec.get('_orig_score', 0.0)
                             or getattr(rec.get('signal_ref'), 'score', 0.0)),
    }
'''
PATCH9_NEW = '''        '_sym': sym,
        '_orig_score': float(rec.get('_orig_score', 0.0)
                             or getattr(rec.get('signal_ref'), 'score', 0.0)),
        # ══ [SMART-TRAILING] live state ══
        '_trail_state': None,
        '_trail_last_bar_ts': 0,
    }
'''
replace_once("PATCH 9 (promote_pending init)",
             PATCH9_OLD, PATCH9_NEW,
             marker=None)   # marker check unreliable here (shared text)


# ───────────────────────────────────────────────────────────────────────
# Summary
# ───────────────────────────────────────────────────────────────────────
print("\n=== APPLIED ===")
for a in applied:
    print(f"  ✓ {a}")
if failed:
    print("\n=== FAILED ===")
    for f in failed:
        print(f"  ✗ {f}")

if content == original:
    print("\nNo changes written (already up to date?).")
    sys.exit(0)

with open(bot_file, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✓ Written to: {bot_file}")
print(f"  File size: {len(content):,} bytes")
PYEOF

# ───────────────────────────────────────────────────────────────────────
# Verification
# ───────────────────────────────────────────────────────────────────────
echo ""
echo "=== Verifying syntax ==="

if python3 -m py_compile "$BOT_FILE" 2>/tmp/pycompile_err.txt; then
    echo "✓ Syntax OK"
    rm -f /tmp/pycompile_err.txt
else
    echo "✗ Syntax error — rolling back"
    cat /tmp/pycompile_err.txt
    mv "$BACKUP" "$BOT_FILE"
    exit 1
fi

echo ""
echo "=== Markers found ==="
grep -c "SMART-TRAILING" "$BOT_FILE" || echo 0
echo "occurrences of 'SMART-TRAILING'"

echo ""
echo "=== Next steps ==="
cat <<'EOF'
  1. اختبار سريع (backtest):
     python trading_2_live4_claude2_v4.py \
         --mode backtest --capital 100 --nassets 10 \
         --maxcon 1 --timeframe 4h --history-days 30 \
         --no-fixed-price

  2. تحقق من تحسّن النتائج:
     - عدد "Hard TP" يجب أن يرتفع
     - ظهور exit_reason="TRAIL_CONFIRMED" في السجل
     - عدد "Emergency SL" يجب أن ينخفض

  3. عند الحاجة للتراجع:
     mv <BACKUP_FILE> trading_2_live4_claude2_v4.py
EOF
