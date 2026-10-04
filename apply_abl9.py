#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_abl9.py — Directional Physics Filter (Self-Calibrating)
==============================================================

يحذف GAUGE_PERCENTILE_BUY و GAUGE_PERCENTILE_SELL (عتبات يدوية)
ويستبدلها بفلتر فيزيائي ذاتي المعايرة:
   threshold(action, t) = 0.50 × (1 ∓ κ × drift)
حيث drift = ميل EMA200 بوحدات σ_price/bar، و κ = GAUGE_DRIFT_SENS.

المعاملات الجديدة:
   GAUGE_DRIFT_SENS   = 0.30
   GAUGE_LOCAL_WINDOW = 200
   GAUGE_LOCAL_MIN    = 100

Idempotent. يرفض أي تطبيق إذا لم يجد النص المتوقع.
"""
import os
import sys

SRC = "trading_2.py"
DST = "trading_2_abl9.py"


# ════════════════════════════════════════════════════════════════
# Patch 1 — Config: add new params after GAUGE_FILTER_ENABLED
# ════════════════════════════════════════════════════════════════
CFG_ADD_OLD = "    GAUGE_FILTER_ENABLED: bool = True\n"
CFG_ADD_NEW = (
    "    GAUGE_FILTER_ENABLED: bool = True\n"
    "    # \u2550\u2550 [DIRECTIONAL PHYSICS FILTER \u2014 Self-Calibrating] \u2550\u2550\n"
    "    # \u0627\u0644\u0639\u062a\u0628\u0629 \u062a\u064f\u062d\u0633\u0628 \u0645\u0646 \u062a\u0648\u0632\u064a\u0639 gauge_force "
    "\u0627\u0644\u062e\u0627\u0635 \u0628\u0643\u0644 \u0623\u0635\u0644 + \u0627\u0646\u062d\u0631\u0627\u0641 EMA200.\n"
    "    # \u0627\u0644\u0648\u0633\u064a\u0637 \u0627\u0644\u0631\u064a\u0627\u0636\u064a = 0.50\u060c "
    "\u0644\u0627 \u0639\u062a\u0628\u0627\u062a \u064a\u062f\u0648\u064a\u0629.\n"
    "    GAUGE_DRIFT_SENS: float = 0.30      "
    "# \u062d\u0633\u0627\u0633\u064a\u0629 \u0627\u0644\u0639\u062a\u0628\u0629 "
    "\u0644\u0644\u0627\u0646\u062d\u0631\u0627\u0641 (0..1)\n"
    "    GAUGE_LOCAL_WINDOW: int = 200       "
    "# \u0646\u0627\u0641\u0630\u0629 percentile \u0627\u0644\u0645\u062d\u0644\u064a\u0629\n"
    "    GAUGE_LOCAL_MIN: int = 100          "
    "# \u0627\u0644\u062d\u062f \u0627\u0644\u0623\u062f\u0646\u0649 "
    "\u0644\u0644\u0646\u0627\u0641\u0630\u0629\n"
)


# ════════════════════════════════════════════════════════════════
# Patch 2 — Config: remove GAUGE_PERCENTILE_BUY
# ════════════════════════════════════════════════════════════════
CFG_RM_BUY_OLD = "    GAUGE_PERCENTILE_BUY: float = 0.60\n"
CFG_RM_BUY_NEW = ""


# ════════════════════════════════════════════════════════════════
# Patch 3 — Config: remove GAUGE_PERCENTILE_SELL (any variant)
# ════════════════════════════════════════════════════════════════
CFG_RM_SELL_CANDIDATES = [
    "    GAUGE_PERCENTILE_SELL: float = 0.95   # [ABL8b] 0.85 -> 0.95\n",
    "    GAUGE_PERCENTILE_SELL: float = 0.95\n",
    "    GAUGE_PERCENTILE_SELL: float = 0.85\n",
]
CFG_RM_SELL_NEW = ""


# ════════════════════════════════════════════════════════════════
# Patch 4 — build_signals: remove global pool block
# ════════════════════════════════════════════════════════════════
POOL_OLD = (
    "    # \u2550\u2550 [GAUGE-FILTER] \u062d\u0633\u0627\u0628 "
    "\u0627\u0644\u0639\u062a\u0628\u0627\u062a \u0627\u0644\u0639\u0627\u0644\u0645\u064a\u0629 "
    "\u0645\u0631\u0629 \u0648\u0627\u062d\u062f\u0629 \u2550\u2550\n"
    "    _gauge_thr_buy = 0.0\n"
    "    _gauge_thr_sell = 0.0\n"
    "    if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):\n"
    "        _gauge_pool = []\n"
    "        for _sym, _ad in assets.items():\n"
    "            try:\n"
    "                gf = getattr(_ad, 'gauge_force', None)\n"
    "                if gf is None or len(gf) == 0:\n"
    "                    continue\n"
    "                # \u0627\u0633\u062a\u062e\u062f\u0627\u0645 \u062c\u0632\u0621 "
    "\u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631 \u0641\u0642\u0637 "
    "(\u0644\u0627 \u062a\u062f\u0631\u064a\u0628)\n"
    "                _valid = gf[_ad.train_end:]\n"
    "                _valid = _valid[_valid > 0]\n"
    "                if len(_valid) > 0:\n"
    "                    _gauge_pool.extend(_valid.tolist())\n"
    "            except Exception:\n"
    "                continue\n"
    "\n"
    "        if len(_gauge_pool) >= int(CFG.GAUGE_MIN_SAMPLES):\n"
    "            _gauge_arr = np.array(_gauge_pool)\n"
    "            _gauge_thr_buy = float(np.percentile(\n"
    "                _gauge_arr, CFG.GAUGE_PERCENTILE_BUY * 100\n"
    "            ))\n"
    "            _gauge_thr_sell = float(np.percentile(\n"
    "                _gauge_arr, CFG.GAUGE_PERCENTILE_SELL * 100\n"
    "            ))\n"
    "            log.info(\n"
    "                f\"[Gauge-Filter] thresholds: \"\n"
    "                f\"BUY>p{int(CFG.GAUGE_PERCENTILE_BUY*100)}=\"\n"
    "                f\"{_gauge_thr_buy:.5f}, \"\n"
    "                f\"SELL>p{int(CFG.GAUGE_PERCENTILE_SELL*100)}=\"\n"
    "                f\"{_gauge_thr_sell:.5f} \"\n"
    "                f\"(pool={len(_gauge_pool)})\"\n"
    "            )\n"
    "        else:\n"
    "            log.warning(\n"
    "                f\"[Gauge-Filter] pool too small ({len(_gauge_pool)}\"\n"
    "                f\"<{CFG.GAUGE_MIN_SAMPLES}) \u2014 filter disabled\"\n"
    "            )\n"
)
POOL_NEW = (
    "    # \u2550\u2550 [DIRECTIONAL PHYSICS FILTER] self-calibrating "
    "per-asset \u2550\u2550\n"
    "    # \u0627\u0644\u0639\u062a\u0628\u0629 \u062a\u064f\u062d\u0633\u0628 "
    "\u062f\u0627\u062e\u0644 \u0627\u0644\u062d\u0644\u0642\u0629 "
    "\u0644\u0643\u0644 \u0623\u0635\u0644 \u0639\u0644\u0649 \u062d\u062f\u0629 "
    "(\u0644\u0627 \u062a\u062c\u0645\u064a\u0639 \u0639\u0627\u0644\u0645\u064a).\n"
)


# ════════════════════════════════════════════════════════════════
# Patch 5 — build_signals: replace in-loop gauge filter
# ════════════════════════════════════════════════════════════════
INLINE_OLD = (
    "            # \u2550\u2550 [GAUGE-FILTER] \u2550\u2550\n"
    "            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):\n"
    "                if action == \"SELL\" and getattr(CFG, 'GAUGE_DISABLE_SELL', False):\n"
    "                    continue\n"
    "                try:\n"
    "                    _gf = float(ad.gauge_force[fi])\n"
    "                    if action == \"BUY\" and _gf < _gauge_thr_buy:\n"
    "                        continue\n"
    "                    if action == \"SELL\" and _gf < _gauge_thr_sell:\n"
    "                        continue\n"
    "                except Exception:\n"
    "                    pass\n"
)
INLINE_NEW = (
    "            # \u2550\u2550 [DIRECTIONAL PHYSICS FILTER] self-calibrating "
    "per-asset \u2550\u2550\n"
    "            # \u0627\u0644\u0639\u062a\u0628\u0629 = 0.50 \u00d7 (1 \u2213 \u03ba \u00d7 drift)\u060c "
    "\u0645\u0634\u062a\u0642\u0629 \u0645\u0646:\n"
    "            #   - \u062a\u0648\u0632\u064a\u0639 gauge_force "
    "\u0627\u0644\u062e\u0627\u0635 \u0628\u0647\u0630\u0627 \u0627\u0644\u0623\u0635\u0644 "
    "(\u0646\u0627\u0641\u0630\u0629 \u0645\u062a\u062f\u062d\u0631\u062c\u0629)\n"
    "            #   - \u0627\u0646\u062d\u0631\u0627\u0641 EMA200 \u0628\u0648\u062d\u062f\u0627\u062a "
    "\u03c3_price/bar\n"
    "            if getattr(CFG, 'GAUGE_FILTER_ENABLED', False):\n"
    "                if action == \"SELL\" and getattr(CFG, 'GAUGE_DISABLE_SELL', False):\n"
    "                    continue\n"
    "                try:\n"
    "                    _win = int(getattr(CFG, 'GAUGE_LOCAL_WINDOW', 200))\n"
    "                    _win_min = int(getattr(CFG, 'GAUGE_LOCAL_MIN', 100))\n"
    "                    _k = float(getattr(CFG, 'GAUGE_DRIFT_SENS', 0.30))\n"
    "                    _w_start = max(0, fi - _win)\n"
    "                    _w_gf = ad.gauge_force[_w_start:fi]\n"
    "                    if len(_w_gf) >= _win_min:\n"
    "                        _gf_now = float(ad.gauge_force[fi])\n"
    "                        _gf_pct = float(np.mean(_w_gf <= _gf_now))\n"
    "\n"
    "                        # \u0627\u0644\u0627\u0646\u062d\u0631\u0627\u0641: "
    "\u0645\u064a\u0644 EMA200 / \u03c3_price\n"
    "                        _drift = 0.0\n"
    "                        _lb = 50\n"
    "                        if ci >= _lb and ci < len(ad.ema200):\n"
    "                            _slope = ((ad.ema200[ci] - ad.ema200[ci - _lb])\n"
    "                                      / float(_lb))\n"
    "                            _sigma_p = (float(ad.E_therm[fi])\n"
    "                                        if 0 <= fi < len(ad.E_therm)\n"
    "                                        else 0.01)\n"
    "                            if not np.isfinite(_sigma_p) or _sigma_p <= 1e-6:\n"
    "                                _sigma_p = 0.01\n"
    "                            _drift = float(np.clip(\n"
    "                                _slope / (_sigma_p * p), -1.0, 1.0\n"
    "                            ))\n"
    "\n"
    "                        if action == \"BUY\":\n"
    "                            _thr = 0.50 * (1.0 - _k * _drift)\n"
    "                        else:\n"
    "                            _thr = 0.50 * (1.0 + _k * _drift)\n"
    "                        _thr = float(np.clip(_thr, 0.10, 0.95))\n"
    "\n"
    "                        if _gf_pct < _thr:\n"
    "                            continue\n"
    "                    # fail-open if window too short\n"
    "                except Exception:\n"
    "                    pass\n"
)


# ════════════════════════════════════════════════════════════════
# Patch engine
# ════════════════════════════════════════════════════════════════

def _try_patch(text, cid, candidates, replacement, required=True):
    """Try each candidate (exact match, count==1). Return (text, ok)."""
    if isinstance(candidates, str):
        candidates = [candidates]

    for old in candidates:
        n = text.count(old)
        if n == 1:
            text = text.replace(old, replacement, 1)
            print(f"-- {cid:15s} -- APPLIED")
            return text, True
        elif n > 1:
            print(f"-- {cid:15s} -- FAIL: AMBIGUOUS ({n} matches)",
                  file=sys.stderr)
            return text, False

    # Nothing matched
    if required:
        print(f"-- {cid:15s} -- FAIL: NOT FOUND", file=sys.stderr)
        for i, old in enumerate(candidates):
            head = old.splitlines()[0] if old else "<empty>"
            print(f"     candidate[{i}]: {head!r}", file=sys.stderr)
        return text, False
    else:
        # Optional: check if new is already present → idempotent
        if replacement and text.count(replacement) >= 1:
            print(f"-- {cid:15s} -- ALREADY APPLIED")
            return text, True
        print(f"-- {cid:15s} -- SKIPPED (optional, not found)")
        return text, True


def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found in cwd.", file=sys.stderr)
        sys.exit(1)

    with open(SRC, encoding="utf-8") as f:
        text = f.read()

    original = text

    # ═══ Apply patches in order ═══
    patches = [
        ("9.CFG-add",    CFG_ADD_OLD,               CFG_ADD_NEW,               True),
        ("9.CFG-rm-buy", CFG_RM_BUY_OLD,            CFG_RM_BUY_NEW,            True),
        ("9.CFG-rm-sell",CFG_RM_SELL_CANDIDATES,    CFG_RM_SELL_NEW,           True),
        ("9.pool",       POOL_OLD,                  POOL_NEW,                  True),
        ("9.inline",     INLINE_OLD,                INLINE_NEW,                True),
    ]

    fail = False
    for cid, old, new, required in patches:
        text, ok = _try_patch(text, cid, old, new, required=required)
        if not ok:
            fail = True

    if fail:
        print("\n\u274c ABORT: some patches failed. No file written.",
              file=sys.stderr)
        sys.exit(2)

    # ═══ Syntax check ═══
    try:
        compile(text, DST, "exec")
    except SyntaxError as e:
        print(f"\u274c SYNTAX ERROR after patch: {e}", file=sys.stderr)
        sys.exit(3)

    # ═══ Verify that the new params exist ═══
    for param in ("GAUGE_DRIFT_SENS", "GAUGE_LOCAL_WINDOW", "GAUGE_LOCAL_MIN"):
        if param not in text:
            print(f"\u274c MISSING param: {param}", file=sys.stderr)
            sys.exit(4)

    # ═══ Write ═══
    with open(DST, "w", encoding="utf-8") as f:
        f.write(text)

    delta = len(text) - len(original)
    print()
    print(f"\u2705 Wrote {DST}  ({len(text):,} chars, delta {delta:+d})")


if __name__ == "__main__":
    main()
