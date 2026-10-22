#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  fix_duplicate_tp.sh — يمنع تكرار أوامر TP
#  يعمل على النسخة الأصلية (قبل Smart Trailing) وعلى النسخة المُحسَّنة.
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

BOT_FILE="${1:-trading_2_live4_claude2_v4_fix_dup_order.py}"
[ -f "$BOT_FILE" ] || { echo "✗ $BOT_FILE غير موجود"; exit 1; }

grep -q "DUP-TP-FIX-APPLIED" "$BOT_FILE" && {
    echo "ℹ  التعديل مطبَّق مسبقاً"; exit 0;
}

# تحقق من أن الملف هو النسخة المتوقعة
if ! grep -q "def _place_protective_orders" "$BOT_FILE"; then
    echo "✗ الملف لا يحتوي _place_protective_orders"; exit 1
fi

BACKUP="$BOT_FILE.bak.$(date +%Y%m%d_%H%M%S)"
cp "$BOT_FILE" "$BACKUP"
echo "✓ Backup: $BACKUP"

BOT_FILE="$BOT_FILE" python3 <<'PYEOF'
import os, sys

bot_file = os.environ["BOT_FILE"]
with open(bot_file, "r", encoding="utf-8") as f:
    content = f.read()

original = content
applied, failed = [], []


def replace_once(name, old, new):
    global content
    if old not in content:
        failed.append(f"{name} — anchor not found")
        return False
    content = content.replace(old, new, 1)
    applied.append(name)
    return True


# ───────────────────────────────────────────────────────────────────────
# PATCH 1: Idempotency grace guard
# ───────────────────────────────────────────────────────────────────────
OLD1 = '''        if pos.get('_partial_taken'):
            _partial_enabled = False

        # ── Fetch existing protective orders ──
        try:
            _existing = _lv_open_orders_all(exchange, sym)
'''
NEW1 = '''        if pos.get('_partial_taken'):
            _partial_enabled = False

        # ══ [DUP-TP-FIX-APPLIED / PATCH-1] Idempotency grace guard ══
        # إذا وُضع SL/TP بنفس القيم خلال GRACE_S، تخطَّ — يمنع إعادة الوضع
        # عند كل استدعاء من Trailing / _lv_ensure_protection.
        _grace_s = float(getattr(CFG, 'PROTECTIVE_PLACE_GRACE_S', 90.0))
        _last_place_ts = float(pos.get('_prot_last_place_ts', 0.0))
        _last_sl = pos.get('_prot_last_sl')
        _last_tp = pos.get('_prot_last_tp')
        if (_last_place_ts > 0
                and _last_sl is not None
                and _last_tp is not None
                and (time.time() - _last_place_ts) < _grace_s):
            _sl_match = (abs(float(_last_sl) - float(sl))
                         / max(abs(float(sl)), 1e-9)) < 1e-4
            _tp_match = (abs(float(_last_tp) - float(tp))
                         / max(abs(float(tp)), 1e-9)) < 1e-4
            if _sl_match and _tp_match:
                log.debug(
                    f"[Prot] {sym} within {_grace_s:.0f}s grace "
                    f"(SL={sl:.6f} TP={tp:.6f}) — skip re-placement"
                )
                return True

        # ── Fetch existing protective orders ──
        try:
            _existing = _lv_open_orders_all(exchange, sym)
'''
replace_once("PATCH 1 (idempotency grace guard)", OLD1, NEW1)


# ───────────────────────────────────────────────────────────────────────
# PATCH 2: Tick-aware tolerance
# ───────────────────────────────────────────────────────────────────────
OLD2 = '''        tol = 1e-4
        _ex_sl = None
        _ex_tp_full = None
        _ex_tp_partial = None
        _stale_ids = []

        for o in _prot:
            p = _px(o)
            if p <= 0:
                continue
            if _is_tp(o):
                if (_partial_enabled
                        and abs(p - _partial_price) /
                            max(abs(_partial_price), 1e-9) < tol):
                    _ex_tp_partial = p
                elif abs(p - tp) / max(abs(tp), 1e-9) < tol:
                    _ex_tp_full = p
                else:
                    _stale_ids.append(o['id'])
            else:
                if abs(p - sl) / max(abs(sl), 1e-9) < tol:
                    _ex_sl = p
                else:
                    _stale_ids.append(o['id'])
'''
NEW2 = '''        # ══ [DUP-TP-FIX-APPLIED / PATCH-2] Tick-aware tolerance ══
        # التسامح القديم (1bp) أصغر من tick size على العملات الصغيرة
        # (مثل $0.30 مع tick=$0.0001). النتيجة: عدم كشف TP موجود →
        # وضع TP جديد كل حركة SL. الحل: تسامح بـ 3 ticks أو 3 bps.
        _tick_size = 0.0
        try:
            _tick_size = _get_tick_size(exchange, sym) or 0.0
        except Exception:
            _tick_size = 0.0
        _tol_px = max(
            _tick_size * 3.0,
            max(abs(tp), abs(sl),
                abs(_partial_price if _partial_price > 0 else 0)) * 3e-5,
            1e-9,
        )

        _ex_sl = None
        _ex_tp_full = None
        _ex_tp_partial = None
        _stale_ids = []

        for o in _prot:
            p = _px(o)
            if p <= 0:
                continue
            if _is_tp(o):
                if (_partial_enabled and _partial_price > 0
                        and abs(p - _partial_price) < _tol_px):
                    _ex_tp_partial = p
                elif abs(p - tp) < _tol_px:
                    _ex_tp_full = p
                else:
                    _stale_ids.append(o['id'])
            else:
                if abs(p - sl) < _tol_px:
                    _ex_sl = p
                else:
                    _stale_ids.append(o['id'])
'''
replace_once("PATCH 2 (tick-aware tolerance)", OLD2, NEW2)


# ───────────────────────────────────────────────────────────────────────
# PATCH 3: Abort on cancel failure
# ───────────────────────────────────────────────────────────────────────
OLD3 = '''        # ── Cancel ONLY the stale legs ──
        for _oid in _stale_ids:
            _done = False
            for _prm in ({'trigger': True}, {}):
                try:
                    exchange.cancel_order(_oid, sym, params=_prm)
                    _done = True
                    break
                except Exception as _ce:
                    _m = str(_ce).lower()
                    if '-2011' in _m or 'unknown order' in _m:
                        _done = True
                        break
            if not _done:
                log.warning(f"[Prot] {sym} stale cancel oid={_oid} failed")
        if _stale_ids:
            log.info(f"[Prot] {sym} cancelled {len(_stale_ids)} stale "
                     f"protective order(s) before placement")
            time.sleep(0.4)
'''
NEW3 = '''        # ══ [DUP-TP-FIX-APPLIED / PATCH-3] Abort on cancel failure ══
        # إذا فشل إلغاء أمر قديم، نُجهض العملية بدلاً من وضع أوامر
        # جديدة فوقه — هذا يمنع التراكم.
        _cancel_all_ok = True
        for _oid in _stale_ids:
            _done = False
            _last_err = None
            for _prm in ({'trigger': True}, {}):
                try:
                    exchange.cancel_order(_oid, sym, params=_prm)
                    _done = True
                    break
                except Exception as _ce:
                    _last_err = _ce
                    _m = str(_ce).lower()
                    if '-2011' in _m or 'unknown order' in _m or '-2013' in _m:
                        _done = True
                        break
            if not _done:
                log.warning(
                    f"[Prot] {sym} stale cancel oid={_oid} failed: "
                    f"{_last_err} — ABORTING to prevent duplicates"
                )
                _cancel_all_ok = False
        if not _cancel_all_ok:
            return False
        if _stale_ids:
            log.info(f"[Prot] {sym} cancelled {len(_stale_ids)} stale "
                     f"protective order(s) before placement")
            time.sleep(0.4)
'''
replace_once("PATCH 3 (abort on cancel failure)", OLD3, NEW3)


# ───────────────────────────────────────────────────────────────────────
# PATCH 4: Record timestamp on success
# ───────────────────────────────────────────────────────────────────────
OLD4 = '''        # ── Early return if everything is already in place ──
        if (_ex_sl is not None
                and _ex_tp_full is not None
                and (not _partial_enabled or _ex_tp_partial is not None)):
            log.debug(f"[Prot] {sym} all legs present -- no action")
            pos['_broker_partial'] = bool(_ex_tp_partial is not None)
            return True
'''
NEW4 = '''        # ── Early return if everything is already in place ──
        if (_ex_sl is not None
                and _ex_tp_full is not None
                and (not _partial_enabled or _ex_tp_partial is not None)):
            log.debug(f"[Prot] {sym} all legs present -- no action")
            pos['_broker_partial'] = bool(_ex_tp_partial is not None)
            # [DUP-TP-FIX-APPLIED / PATCH-4a]
            pos['_prot_last_place_ts'] = time.time()
            pos['_prot_last_sl'] = float(sl)
            pos['_prot_last_tp'] = float(tp)
            return True
'''
replace_once("PATCH 4a", OLD4, NEW4)

OLD4B = '''        _ok = (placed['sl'] and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if _ok:
            return True
        log.warning(f"[Prot] {sym} incomplete: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return _ok
'''
NEW4B = '''        _ok = (placed['sl'] and placed['tp']
               and (placed['partial_tp'] or not _partial_enabled))
        if _ok:
            # [DUP-TP-FIX-APPLIED / PATCH-4b]
            pos['_prot_last_place_ts'] = time.time()
            pos['_prot_last_sl'] = float(sl)
            pos['_prot_last_tp'] = float(tp)
            return True
        log.warning(f"[Prot] {sym} incomplete: sl={placed['sl']} "
                    f"tp={placed['tp']} partial={placed['partial_tp']}")
        return _ok
'''
replace_once("PATCH 4b", OLD4B, NEW4B)


# ───────────────────────────────────────────────────────────────────────
# PATCH 5: Fix stale threshold
# ───────────────────────────────────────────────────────────────────────
OLD5 = '''    last = pos.get('_prot_last_sl')
    stale = (last is None) or abs(float(pos.get('sl') or 0.0) - float(last)) > 1e-9 * max(float(pos.get('sl') or 1.0), 1.0)
'''
NEW5 = '''    last = pos.get('_prot_last_sl')
    # ══ [DUP-TP-FIX-APPLIED / PATCH-5] عتبة واقعية بدل 1e-9 ══
    # 1e-9 × SL = صفر عملي → أي ذبذبة لا نهائية = stale → re-place.
    # نستخدم PROTECTIVE_SYNC_MIN_STEP_FRAC (0.1%) — متسق مع
    # _sync_protective_orders.
    _stale_step = float(getattr(CFG, 'PROTECTIVE_SYNC_MIN_STEP_FRAC', 0.001))
    _cur_sl = float(pos.get('sl') or 0.0)
    if last is None:
        stale = True
    elif _cur_sl > 0 and float(last) > 0:
        stale = (abs(_cur_sl - float(last))
                 / max(abs(float(last)), 1e-12)) > _stale_step
    else:
        stale = True
'''
replace_once("PATCH 5 (stale threshold)", OLD5, NEW5)


# ───────────────────────────────────────────────────────────────────────
# PATCH 6: Config
# ───────────────────────────────────────────────────────────────────────
OLD6 = '''    PROTECTIVE_SYNC_MIN_STEP_FRAC: float = 0.001   # 0.1% SL movement → resync
    PROTECTIVE_MAX_RETRIES: int = 2
'''
NEW6 = '''    PROTECTIVE_SYNC_MIN_STEP_FRAC: float = 0.001   # 0.1% SL movement → resync
    PROTECTIVE_MAX_RETRIES: int = 2
    # [DUP-TP-FIX] grace period — prevent duplicate TP placement
    PROTECTIVE_PLACE_GRACE_S: float = 90.0
'''
replace_once("PATCH 6 (config)", OLD6, NEW6)


# ───────────────────────────────────────────────────────────────────────
# Summary
# ───────────────────────────────────────────────────────────────────────
print("\n=== APPLIED ===")
for a in applied:
    print(f"  ✓ {a}")
if failed:
    print("\n=== FAILED ===")
    for f_ in failed:
        print(f"  ✗ {f_}")
    print("\n⚠  بعض التصحيحات فشلت — الملف قد يكون معدلاً. تحقق يدوياً.")
    sys.exit(1)

if content == original:
    print("\nNo changes.")
    sys.exit(0)

with open(bot_file, "w", encoding="utf-8") as f:
    f.write(content)
print(f"\n✓ Written: {bot_file}  ({len(content):,} bytes)")
PYEOF

# Verify
echo ""
echo "=== Verify ==="
if python3 -m py_compile "$BOT_FILE" 2>/tmp/pc.txt; then
    echo "✓ Syntax OK"
    rm -f /tmp/pc.txt
else
    echo "✗ Syntax error — rollback"
    cat /tmp/pc.txt
    mv "$BACKUP" "$BOT_FILE"
    exit 1
fi

echo ""
echo "✓ Done. Backup: $BACKUP"
echo ""
echo "=== Next steps ==="
cat <<'EOF'
  1. (اختياري لكن مستحسن) شغّل التنظيف اليدوي أولاً:
     python3 cleanup_duplicate_tps.py --mode testnet \
         --api-key $KEY --api-secret $SECRET

  2. تحقق من وضعك الحالي:
     python3 diagnose_duplicate_tps.py --mode testnet \
         --api-key $KEY --api-secret $SECRET

  3. شغّل البوت كالمعتاد وراقب:
     grep "\[Prot\]" qtt6.log | tail -50

  المطلوب أن ترى:
    ✓ "FULL-TP placed" مرة واحدة فقط عند فتح المركز
    ✓ "within 90s grace" عند حركات SL المتقاربة
    ✓ "all legs present -- no action" عند الاستقرار
    ✗ لا ترى "FULL-TP placed" متكرر لنفس المركز
EOF
