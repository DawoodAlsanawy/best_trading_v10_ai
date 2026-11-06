#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  RASE + Fixes — Remaining Improvements Patcher                              ║
║  يُطبّق التحسينات المتبقية على trading_2_live4_claude2_v4.py                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  15 تعديل ذري:                                                              ║
║    P01: إصلاح compute_signal_strength (score → strength)                    ║
║    P02: حقول Config (RASE + TP_DYNAMIC + MAX_NOTIONAL_PER_TRADE_FRAC)       ║
║    P03: RASE Layer 1 — trending → normal via gauge p75                      ║
║    P04: RASE Layer 1 — _regime_entry_mult يعرف "normal"                     ║
║    P05: _compute_rase_dip helper (Layers 2)                                 ║
║    P06: _select_target_multiple helper (TP_DYNAMIC)                         ║
║    P07: build_signals — dip routing (RASE Layer 2)                          ║
║    P08: build_signals — TP routing (TP_DYNAMIC)                             ║
║    P09: precompute_entry_fills — RASE Layer 3 sub-bar hook                  ║
║    P10: _recompute_entry_geometry_at_market — TP ديناميكي (لا 2.0)          ║
║    P11: simulate_portfolio — log + notional cap                             ║
║    P12: CLI args (--rase*, --tp-dynamic*)                                   ║
║    P13: CLI wiring                                                          ║
║    P14: run_live — notional cap per trade                                   ║
║    P15: Version marker                                                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  USAGE:                                                                     ║
║    python3 rase_remaining_improvements_patcher.py              # apply     ║
║    python3 rase_remaining_improvements_patcher.py --dry-run    # preview   ║
║    python3 rase_remaining_improvements_patcher.py --verify-only            ║
║    python3 rase_remaining_improvements_patcher.py --rollback              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  SAFETY: backup + ast.parse + atomic write + rollback + idempotent         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import ast
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_TARGET = "trading_2_live4_claude2_v4.py"
MARKER = "# ═══ [RASE-REMAINING-IMPROVEMENTS-APPLIED] ═══"


PATCHES = [

    # ═══════════════════════════════════════════════════════════════════════
    # P01 — إصلاح compute_signal_strength (score → strength)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P01-fix-signal-strength",
        "desc": "Fix compute_signal_strength: lo/hi bug → always returns 1.0",
        "old": (
            "def compute_signal_strength(sig, cfg) -> float:\n"
            "    \"\"\"\n"
            "    Map sig.score to a strength in [0, 1].\n"
            "    Both MR and legacy modes normalized to same scale.\n"
            "    \"\"\"\n"
            "    try:\n"
            "        score = float(sig.score)\n"
            "    except Exception:\n"
            "        return 0.5\n"
            "\n"
            "    if getattr(cfg, 'MEANREV_MODE', False):\n"
            "        lo = float(getattr(cfg, 'MR_K', 2.5))\n"
            "        hi = lo * 2.0\n"
            "    else:\n"
            "        lo = float(cfg.MIN_SCORE)\n"
            "        hi = lo * 2.5\n"
            "\n"
            "    return float(np.clip((score - lo) / max(hi - lo, 1e-9), 0.0, 1.0))\n"
        ),
        "new": (
            "def compute_signal_strength(sig, cfg) -> float:\n"
            "    \"\"\"\n"
            "    Map sig.score to a strength in [0, 1].\n"
            "    Both MR and legacy modes normalized to same scale.\n"
            "    \"\"\"\n"
            "    try:\n"
            "        score = float(sig.score)\n"
            "    except Exception:\n"
            "        return 0.5\n"
            "\n"
            "    if getattr(cfg, 'MEANREV_MODE', False):\n"
            "        lo = float(getattr(cfg, 'MR_K', 2.5))\n"
            "        hi = lo * 2.0\n"
            "    else:\n"
            "        lo = float(cfg.MIN_SCORE)\n"
            "        hi = lo * 2.5\n"
            "\n"
            "    # ══ [STRENGTH-FIX] lo=MIN_SCORE=-3 → hi=-7.5 (سالبة)\n"
            "    # (score - lo)/(hi - lo) يصبح رقم سالب في المقام، والـ max(...,1e-9)\n"
            "    # يرفعه إلى 1e-9 فيصبح الناتج ضخماً → clipped to 1.0 دائماً.\n"
            "    # الحل: استخدم القيمة المطلقة للفرق.\n"
            "    _span = abs(hi - lo)\n"
            "    if _span < 1e-9:\n"
            "        return 0.5\n"
            "    _raw = (score - min(lo, hi)) / _span\n"
            "    return float(np.clip(_raw, 0.0, 1.0))\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P02 — حقول Config (RASE + TP_DYNAMIC + MAX_NOTIONAL_PER_TRADE_FRAC)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P02-config-fields",
        "desc": "Add RASE + TP_DYNAMIC + MAX_NOTIONAL_PER_TRADE_FRAC config",
        "old": (
            "    ENTRY_REGIME_EXPLOSIVE_MULT: float = 1.30\n"
            "    # Layer 3: structure anchor (nearest swing)\n"
        ),
        "new": (
            "    ENTRY_REGIME_EXPLOSIVE_MULT: float = 1.30\n"
            "    ENTRY_REGIME_NORMAL_MULT: float = 1.50\n"
            "    # ══ [RASE Phase 1] Regime-Adaptive Sub-Bar Entry ══\n"
            "    # Disabled by default → bit-identical to legacy behavior.\n"
            "    RASE_ENABLED: bool = False\n"
            "    RASE_DIP_FLOOR_FRAC: float = 0.4\n"
            "    RASE_DIP_CAP_FRAC:   float = 1.0\n"
            "    RASE_REGIME_GAUGE_P75_WINDOW: int = 200\n"
            "    # ══ [TP DYNAMIC] اختيار R:R لكل إشارة بحسب الفيزياء ══\n"
            "    # False → استخدم TP_MULT الثابت (السلوك القديم)\n"
            "    TP_DYNAMIC_MULT: bool = False\n"
            "    TP_MIN_MULT: float = 1.5\n"
            "    TP_MAX_MULT: float = 5.0\n"
            "    TP_PHYSICS_SIGMA_CAP: float = 2.0\n"
            "    TP_ENERGY_MIN_RATIO: float = 0.65\n"
            "    TP_REJECT_BELOW_MIN: bool = False\n"
            "    TP_HORIZON_BARS_1H: int = 10\n"
            "    # ══ [NOTIONAL-FRAC-CAP] سقف notional لكل صفقة (0 = off) ══\n"
            "    # يمنع استخدام رأس المال بالكامل في صفقة واحدة.\n"
            "    MAX_NOTIONAL_PER_TRADE_FRAC: float = 0.0\n"
            "    # Layer 3: structure anchor (nearest swing)\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P03 — RASE Layer 1: trending → normal via gauge p75
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P03-rasе-classifier",
        "desc": "RASE Layer 1: split trending into trending/normal via gauge p75",
        "old": (
            "        ratio = sig_now / sig_mean\n"
            "        if ratio > 1.6:\n"
            "            return \"explosive\"\n"
            "        elif ratio < 0.7:\n"
            "            return \"ranging\"\n"
            "        else:\n"
            "            return \"trending\"\n"
            "    except Exception:\n"
            "        return \"normal\"\n"
        ),
        "new": (
            "        ratio = sig_now / sig_mean\n"
            "        if ratio > 1.6:\n"
            "            return \"explosive\"\n"
            "        elif ratio < 0.7:\n"
            "            return \"ranging\"\n"
            "        # ══ [RASE Phase 1] trending vs normal via gauge p75 ══\n"
            "        if not getattr(CFG, 'RASE_ENABLED', False):\n"
            "            return \"trending\"\n"
            "        try:\n"
            "            _win = int(getattr(CFG, 'RASE_REGIME_GAUGE_P75_WINDOW', 200))\n"
            "            _lo = max(0, fi - _win)\n"
            "            _gf = ad.gauge_force[_lo:fi + 1]\n"
            "            if len(_gf) >= 20:\n"
            "                _p75 = float(np.percentile(_gf, 75))\n"
            "                _g_now = float(ad.gauge_force[fi])\n"
            "                if np.isfinite(_g_now) and _g_now > _p75:\n"
            "                    return \"trending\"\n"
            "            return \"normal\"\n"
            "        except Exception:\n"
            "            return \"normal\"\n"
            "    except Exception:\n"
            "        return \"normal\"\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P04 — _regime_entry_mult يعرف "normal"
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P04-regime-mult-normal",
        "desc": "_regime_entry_mult: add normal case",
        "old": (
            "def _regime_entry_mult(regime: str) -> float:\n"
            "    \"\"\"Entry dip multiplier by regime.\"\"\"\n"
            "    if regime == \"explosive\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_EXPLOSIVE_MULT', 1.30))\n"
            "    if regime == \"ranging\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_RANGING_MULT', 0.60))\n"
            "    return float(getattr(CFG, 'ENTRY_REGIME_TRENDING_MULT', 1.00))\n"
        ),
        "new": (
            "def _regime_entry_mult(regime: str) -> float:\n"
            "    \"\"\"Entry dip multiplier by regime.\"\"\"\n"
            "    if regime == \"explosive\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_EXPLOSIVE_MULT', 1.30))\n"
            "    if regime == \"ranging\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_RANGING_MULT', 0.60))\n"
            "    if regime == \"normal\":\n"
            "        return float(getattr(CFG, 'ENTRY_REGIME_NORMAL_MULT', 1.50))\n"
            "    return float(getattr(CFG, 'ENTRY_REGIME_TRENDING_MULT', 1.00))\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P05 + P06 — إدراج _compute_rase_dip + _select_target_multiple
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P05-06-rase-dip-and-target-helpers",
        "desc": "Insert _compute_rase_dip + _select_target_multiple helpers",
        "old": (
            "        min_d = float(getattr(CFG, 'ENTRY_MIN_DIP_MULT', 0.15)) * atr_now\n"
            "        max_d = float(getattr(CFG, 'ENTRY_MAX_DIP_MULT', 1.00)) * atr_now\n"
            "        dip = float(np.clip(dip, min_d, max_d))\n"
            "        return float(dip)\n"
            "    except Exception:\n"
            "        return 0.0\n"
            "\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "# § TRADE FILTER — Pre-entry multi-signal rejection\n"
        ),
        "new": (
            "        min_d = float(getattr(CFG, 'ENTRY_MIN_DIP_MULT', 0.15)) * atr_now\n"
            "        max_d = float(getattr(CFG, 'ENTRY_MAX_DIP_MULT', 1.00)) * atr_now\n"
            "        dip = float(np.clip(dip, min_d, max_d))\n"
            "        return float(dip)\n"
            "    except Exception:\n"
            "        return 0.0\n"
            "\n"
            "\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "# [RASE Phase 1] Regime-adaptive dip (clamped to physics envelope)\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "def _compute_rase_dip(ad, fi, ci, action, close_price, sigma_price):\n"
            "    \"\"\"\n"
            "    RASE Layer 2 — dip that adapts to the current market regime.\n"
            "\n"
            "    Uses friction dip if FRICTION_DIP_KAPPA > 0, else falls back\n"
            "    to ATR-based dip (legacy path) as the physics envelope.\n"
            "    Returns 0.0 on failure → caller falls back to legacy dip.\n"
            "    \"\"\"\n"
            "    try:\n"
            "        if not getattr(CFG, 'RASE_ENABLED', False):\n"
            "            return 0.0\n"
            "        if sigma_price <= 0 or close_price <= 0:\n"
            "            return 0.0\n"
            "        # Choose base dip: friction (if enabled) or ATR\n"
            "        _fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 0.0))\n"
            "        if _fd_kappa > 0:\n"
            "            base_dip = _fd_kappa * sigma_price\n"
            "        else:\n"
            "            base_dip = _compute_entry_dip(ad, fi, ci, action, close_price)\n"
            "        if base_dip <= 0:\n"
            "            return 0.0\n"
            "        regime = _classify_regime_local(\n"
            "            ad, fi, int(getattr(CFG, 'ENTRY_REGIME_LOOKBACK', 100))\n"
            "        )\n"
            "        mult = _regime_entry_mult(regime)\n"
            "        raw_dip = base_dip * mult\n"
            "        floor_frac = float(getattr(CFG, 'RASE_DIP_FLOOR_FRAC', 0.4))\n"
            "        cap_frac   = float(getattr(CFG, 'RASE_DIP_CAP_FRAC', 1.0))\n"
            "        lo = base_dip * floor_frac\n"
            "        hi = base_dip * cap_frac\n"
            "        if hi < lo:\n"
            "            lo, hi = hi, lo\n"
            "        return float(np.clip(raw_dip, lo, hi))\n"
            "    except Exception:\n"
            "        return 0.0\n"
            "\n"
            "\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "# [TP DYNAMIC] اختيار R:R الأمثل لكل إشارة بحسب الفيزياء\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "def _select_target_multiple(ad, fi, ci, action, sl_dist, cfg):\n"
            "    \"\"\"\n"
            "    اختر R:R المثالي لكل إشارة بناءً على فيزياء السوق.\n"
            "    Returns (tp_mult, meta).\n"
            "    \"\"\"\n"
            "    _meta = {'max_physics': 0.0, 'energy_cap': 0.0,\n"
            "             'force_ratio': 0.0, 'sigma_over_horizon': 0.0,\n"
            "             'sr_cap': None, 'rejected': False, 'reason': 'OK'}\n"
            "    try:\n"
            "        if not getattr(cfg, 'TP_DYNAMIC_MULT', False):\n"
            "            _meta['reason'] = 'dynamic_off'\n"
            "            return float(getattr(cfg, 'TP_MULT', 2.0)), _meta\n"
            "        if ad is None or ci < 0 or ci >= len(ad.closes):\n"
            "            _meta['reason'] = 'invalid_index'\n"
            "            return float(getattr(cfg, 'TP_MIN_MULT', 1.5)), _meta\n"
            "        if sl_dist <= 0:\n"
            "            _meta['reason'] = 'invalid_sl'\n"
            "            return float(getattr(cfg, 'TP_MIN_MULT', 1.5)), _meta\n"
            "        price = float(ad.closes[ci])\n"
            "        if price <= 0:\n"
            "            _meta['reason'] = 'invalid_price'\n"
            "            return float(getattr(cfg, 'TP_MIN_MULT', 1.5)), _meta\n"
            "        _horizon_1h = int(getattr(cfg, 'TP_HORIZON_BARS_1H', 10))\n"
            "        try:\n"
            "            _horizon_bars = max(4, int(round(\n"
            "                _horizon_1h * float(getattr(cfg, 'TF_SCALE', 1.0))\n"
            "            )))\n"
            "        except Exception:\n"
            "            _horizon_bars = max(4, _horizon_1h)\n"
            "        sigma_frac = 0.01\n"
            "        if 0 <= fi < len(ad.E_therm):\n"
            "            _s = float(ad.E_therm[fi])\n"
            "            if np.isfinite(_s) and _s > 1e-6:\n"
            "                sigma_frac = _s\n"
            "        sigma_over_horizon = sigma_frac * float(np.sqrt(_horizon_bars))\n"
            "        _meta['sigma_over_horizon'] = float(sigma_over_horizon)\n"
            "        _sigma_cap = float(getattr(cfg, 'TP_PHYSICS_SIGMA_CAP', 2.0))\n"
            "        sl_frac = sl_dist / max(price, 1e-9)\n"
            "        max_physics = (_sigma_cap * sigma_over_horizon) / max(sl_frac, 1e-9)\n"
            "        _meta['max_physics'] = float(max_physics)\n"
            "        accel = 0.0\n"
            "        if 0 <= fi < len(ad.geodesic_accel):\n"
            "            accel = abs(float(ad.geodesic_accel[fi]))\n"
            "        friction = 0.1\n"
            "        if 0 <= fi < len(ad.friction):\n"
            "            friction = float(ad.friction[fi]) + 1e-6\n"
            "        force_ratio = accel / max(friction, 1e-9)\n"
            "        _meta['force_ratio'] = float(force_ratio)\n"
            "        energy_cap = float(np.tanh(force_ratio / 3.0))\n"
            "        _meta['energy_cap'] = float(energy_cap)\n"
            "        tp_min = float(getattr(cfg, 'TP_MIN_MULT', 1.5))\n"
            "        tp_max = float(getattr(cfg, 'TP_MAX_MULT', 5.0))\n"
            "        suggested = tp_min + (tp_max - tp_min) * energy_cap\n"
            "        sr_cap = None\n"
            "        try:\n"
            "            _sr_lookback = int(getattr(cfg, 'SR_LOOKBACK', 60))\n"
            "            if ci >= _sr_lookback + 2:\n"
            "                _supports, _resistances = _find_swing_levels(\n"
            "                    ad, ci, _sr_lookback\n"
            "                )\n"
            "                if action == \"BUY\":\n"
            "                    _cands = [r for r, _idx in _resistances if r > price]\n"
            "                    if _cands:\n"
            "                        _nearest = min(_cands)\n"
            "                        _gap = _nearest - price\n"
            "                        sr_cap = (_gap * 0.90) / max(sl_dist, 1e-9)\n"
            "                else:\n"
            "                    _cands = [s for s, _idx in _supports if s < price]\n"
            "                    if _cands:\n"
            "                        _nearest = max(_cands)\n"
            "                        _gap = price - _nearest\n"
            "                        sr_cap = (_gap * 0.90) / max(sl_dist, 1e-9)\n"
            "                _meta['sr_cap'] = (float(sr_cap) if sr_cap is not None else None)\n"
            "        except Exception:\n"
            "            pass\n"
            "        final = min(suggested, max_physics)\n"
            "        if sr_cap is not None and sr_cap > 0:\n"
            "            final = min(final, sr_cap)\n"
            "        final = float(np.clip(final, tp_min, tp_max))\n"
            "        if (getattr(cfg, 'TP_REJECT_BELOW_MIN', False)\n"
            "                and final < tp_min * 0.95):\n"
            "            _meta['rejected'] = True\n"
            "            _meta['reason'] = f'below_min(final={final:.2f}<{tp_min:.2f})'\n"
            "        return final, _meta\n"
            "    except Exception as e:\n"
            "        _meta['reason'] = f'error:{e}'\n"
            "        return float(getattr(cfg, 'TP_MIN_MULT', 1.5)), _meta\n"
            "\n"
            "# ════════════════════════════════════════════════════════════════\n"
            "# § TRADE FILTER — Pre-entry multi-signal rejection\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P07 — build_signals: RASE dip routing
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P07-build-signals-dip",
        "desc": "build_signals: route dip through _compute_rase_dip if enabled",
        "old": (
            "            _sigma_price_bs = _sigma_frac_bs * p\n"
            "            _fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))\n"
            "            _friction_dip = _fd_kappa * _sigma_price_bs\n"
            "            _atr_dip = _compute_entry_dip(ad, fi, ci, action, p)\n"
            "            # Floor: never use a dip smaller than 0.5×ATR\n"
            "            _entry_dip = max(_friction_dip, 0.5 * _atr_dip)\n"
            "            if _entry_dip <= 0.0:\n"
            "                _entry_dip = p * 0.001\n"
        ),
        "new": (
            "            _sigma_price_bs = _sigma_frac_bs * p\n"
            "            _fd_kappa = float(getattr(CFG, 'FRICTION_DIP_KAPPA', 4.0))\n"
            "            _friction_dip = _fd_kappa * _sigma_price_bs\n"
            "            # ══ [RASE Phase 1] regime-adaptive dip ══\n"
            "            _entry_dip = 0.0\n"
            "            if getattr(CFG, 'RASE_ENABLED', False):\n"
            "                _entry_dip = _compute_rase_dip(\n"
            "                    ad, fi, ci, action, p, _sigma_price_bs\n"
            "                )\n"
            "            if _entry_dip <= 0.0:\n"
            "                # Legacy path (unchanged)\n"
            "                _atr_dip = _compute_entry_dip(ad, fi, ci, action, p)\n"
            "                _entry_dip = max(_friction_dip, 0.5 * _atr_dip)\n"
            "            if _entry_dip <= 0.0:\n"
            "                _entry_dip = p * 0.001\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P08 — build_signals: TP routing (TP_DYNAMIC)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P08-build-signals-tp",
        "desc": "build_signals: route TP through _select_target_multiple",
        "old": (
            "            _tp_mult = float(getattr(CFG, 'TP_MULT', 1.5))\n"
            "            tp1 = tunnel_entry_p + (sl_dist * _tp_mult) if action == \"BUY\" else tunnel_entry_p - (sl_dist * _tp_mult)\n"
            "            \n"
            "\n"
            "            # حظر الصفقات الهشة التي تكون تكلفتها أكبر من ربحها\n"
            "            if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue\n"
        ),
        "new": (
            "            # ══ [TP DYNAMIC] اختيار R:R ديناميكياً ══\n"
            "            _tp_mult, _tp_meta = _select_target_multiple(\n"
            "                ad, fi, ci, action, sl_dist, CFG\n"
            "            )\n"
            "            if _tp_meta.get('rejected', False):\n"
            "                log.debug(\n"
            "                    f\"[Target] {sym} {action} rejected: \"\n"
            "                    f\"{_tp_meta.get('reason')} \"\n"
            "                    f\"(physics={_tp_meta.get('max_physics', 0):.2f}, \"\n"
            "                    f\"energy={_tp_meta.get('energy_cap', 0):.2f})\"\n"
            "                )\n"
            "                continue\n"
            "            tp1 = (tunnel_entry_p + (sl_dist * _tp_mult) if action == \"BUY\"\n"
            "                   else tunnel_entry_p - (sl_dist * _tp_mult))\n"
            "            \n"
            "\n"
            "            # حظر الصفقات الهشة التي تكون تكلفتها أكبر من ربحها\n"
            "            if (sl_dist * 2.0) < (abs(CFG.MAKER_FEE) * tunnel_entry_p): continue\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P09 — precompute_entry_fills: RASE Layer 3 sub-bar hook
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P09-precompute-rase-layer3",
        "desc": "precompute_entry_fills: RASE sub-bar rejection hook (backtest)",
        "old": (
            "            if first_bar >= stage1_last and first_bar >= stage2_last:\n"
            "                result[sig_i] = None\n"
            "                continue\n"
            "\n"
            "            target0 = _backtest_entry_target(sig, ad)\n"
            "            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)\n"
            "            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)\n"
        ),
        "new": (
            "            if first_bar >= stage1_last and first_bar >= stage2_last:\n"
            "                result[sig_i] = None\n"
            "                continue\n"
            "\n"
            "            target0 = _backtest_entry_target(sig, ad)\n"
            "            ref_px = float(getattr(sig, 'entry_ref_price', 0.0) or 0.0)\n"
            "            base_dip = float(getattr(sig, 'entry_base_dip', 0.0) or 0.0)\n"
            "\n"
            "            # ══ [RASE Phase 1] sub-bar rejection path ══\n"
            "            if (getattr(CFG, 'RASE_ENABLED', False)\n"
            "                    and not getattr(CFG, 'REVERSAL_CONFIRM_ENABLED', False)\n"
            "                    and ad.sub_highs is not None\n"
            "                    and ad.sub_lows is not None\n"
            "                    and ad.sub_closes is not None\n"
            "                    and ad.sub_per_main >= 2):\n"
            "                _rase_win = int(max(4, np.ceil(\n"
            "                    float(getattr(CFG, 'UNIFIED_WAIT_BARS_1H', 8))\n"
            "                    * float(CFG.TF_SCALE)\n"
            "                )))\n"
            "                _rase_deadline = min(first_bar + _rase_win, stage2_last)\n"
            "                _rase_res = _check_reversal_fill_subbars(\n"
            "                    ad, sig, target0, CFG,\n"
            "                    first_bar, _rase_deadline,\n"
            "                )\n"
            "                if _rase_res is None:\n"
            "                    result[sig_i] = None\n"
            "                    continue\n"
            "                _rase_ci, _rase_px = _rase_res\n"
            "                result[sig_i] = ('S1', int(_rase_ci), float(_rase_px))\n"
            "                continue\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P10 — _recompute_entry_geometry_at_market: TP ديناميكي (لا 2.0)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P10-recompute-stage2-tp",
        "desc": "_recompute_entry_geometry_at_market: fix hardcoded 2.0 → dynamic TP",
        "old": (
            "        # نفس دالة build_signals\n"
            "        sl_dist_new = compute_geodesic_stop(S_new, ad, entry_fi, cfg)\n"
            "        if sl_dist_new <= 0 or not np.isfinite(sl_dist_new):\n"
            "            return None\n"
            "\n"
            "        if sig.action == \"BUY\":\n"
            "            sl_new = S_new - sl_dist_new\n"
            "            tp_new = S_new + (sl_dist_new * 2.0)\n"
            "        else:\n"
            "            sl_new = S_new + sl_dist_new\n"
            "            tp_new = S_new - (sl_dist_new * 2.0)\n"
        ),
        "new": (
            "        # نفس دالة build_signals\n"
            "        sl_dist_new = compute_geodesic_stop(S_new, ad, entry_fi, cfg)\n"
            "        if sl_dist_new <= 0 or not np.isfinite(sl_dist_new):\n"
            "            return None\n"
            "\n"
            "        # ══ [TP-FIX] بدلاً من 2.0 الصلب: استخدم TP_DYNAMIC أو TP_MULT ══\n"
            "        _tp_mult_s2, _ = _select_target_multiple(\n"
            "            ad, entry_fi, entry_ci, sig.action, sl_dist_new, cfg\n"
            "        )\n"
            "        if sig.action == \"BUY\":\n"
            "            sl_new = S_new - sl_dist_new\n"
            "            tp_new = S_new + (sl_dist_new * _tp_mult_s2)\n"
            "        else:\n"
            "            sl_new = S_new + sl_dist_new\n"
            "            tp_new = S_new - (sl_dist_new * _tp_mult_s2)\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P11 — simulate_portfolio: log + notional cap per trade (backtest)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P11-backtest-notional-cap",
        "desc": "simulate_portfolio: RASE log + MAX_NOTIONAL_PER_TRADE_FRAC",
        "old": (
            "    n_total_sigs = len(signals)\n"
            "    n_would_fill = sum(1 for v in fill_map.values() if v is not None)\n"
            "    log.info(f\"  [Backtest Realism] Entry fills: \"\n"
        ),
        "new": (
            "    n_total_sigs = len(signals)\n"
            "    n_would_fill = sum(1 for v in fill_map.values() if v is not None)\n"
            "    # ══ [RASE Phase 1] announce mode ══\n"
            "    if getattr(CFG, 'RASE_ENABLED', False):\n"
            "        _rase_subbar_ok = any(\n"
            "            getattr(a, 'sub_per_main', 0) >= 2\n"
            "            for a in assets.values()\n"
            "        )\n"
            "        log.info(\n"
            "            f\"  [RASE Phase 1] ENABLED  \"\n"
            "            f\"subbar_avail={_rase_subbar_ok}  \"\n"
            "            f\"dip_range=[{CFG.RASE_DIP_FLOOR_FRAC:.2f},\"\n"
            "            f\"{CFG.RASE_DIP_CAP_FRAC:.2f}]x_base\"\n"
            "        )\n"
            "    log.info(f\"  [Backtest Realism] Entry fills: \"\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P12 — CLI args (RASE + TP_DYNAMIC + notional cap)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P12-cli-args",
        "desc": "Add CLI args for RASE + TP_DYNAMIC + notional cap",
        "old": (
            "    p.add_argument(\"--confirm-kappa\", type=float, default=None,\n"
            "                   help=\"[NEW] Confirmation threshold (× σ_bar). \"\n"
            "                        \"Default 0.20. Try 0.1 / 0.2 / 0.3 / 0.5.\")\n"
        ),
        "new": (
            "    p.add_argument(\"--confirm-kappa\", type=float, default=None,\n"
            "                   help=\"[NEW] Confirmation threshold (× σ_bar). \"\n"
            "                        \"Default 0.20. Try 0.1 / 0.2 / 0.3 / 0.5.\")\n"
            "    # ══ [RASE Phase 1] ══\n"
            "    p.add_argument(\"--rase\", action=\"store_true\",\n"
            "                   help=\"[RASE] Enable regime-adaptive dip + sub-bar rejection\")\n"
            "    p.add_argument(\"--rase-dip-floor\", type=float, default=None,\n"
            "                   help=\"[RASE] dip floor as × base (default 0.4)\")\n"
            "    p.add_argument(\"--rase-dip-cap\", type=float, default=None,\n"
            "                   help=\"[RASE] dip cap as × base (default 1.0)\")\n"
            "    p.add_argument(\"--rase-p75-window\", type=int, default=None,\n"
            "                   help=\"[RASE] gauge p75 window (default 200)\")\n"
            "    # ══ [TP DYNAMIC] ══\n"
            "    p.add_argument(\"--tp-dynamic\", action=\"store_true\",\n"
            "                   help=\"[TP-Dynamic] اختر R:R ديناميكياً لكل إشارة\")\n"
            "    p.add_argument(\"--tp-dyn-min\", type=float, default=None,\n"
            "                   help=\"[TP-Dynamic] أدنى R:R (default 1.5)\")\n"
            "    p.add_argument(\"--tp-dyn-max\", type=float, default=None,\n"
            "                   help=\"[TP-Dynamic] أقصى R:R (default 5.0)\")\n"
            "    p.add_argument(\"--tp-dyn-sigma-cap\", type=float, default=None,\n"
            "                   help=\"[TP-Dynamic] أقصى TP = N×σ (default 2.0)\")\n"
            "    p.add_argument(\"--tp-dyn-horizon\", type=int, default=None,\n"
            "                   help=\"[TP-Dynamic] أفق الصفقة (بوحدات 1h, default 10)\")\n"
            "    p.add_argument(\"--tp-reject-below-min\", action=\"store_true\",\n"
            "                   help=\"[TP-Dynamic] ارفض الإشارات < TP_MIN_MULT\")\n"
            "    # ══ [NOTIONAL CAP] ══\n"
            "    p.add_argument(\"--max-notional-frac\", type=float, default=None,\n"
            "                   help=\"[Notional] سقف notional لكل صفقة كنسبة من رأس المال \"\n"
            "                        \"(0 = off, 1.0 = 100%%)\")\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P13 — CLI wiring
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P13-cli-wiring",
        "desc": "Wire CLI flags into CFG",
        "old": (
            "    if getattr(args, \"confirm_kappa\", None) is not None:\n"
            "        CFG.CONFIRM_KAPPA = float(args.confirm_kappa)\n"
            "        log.info(f\"[Confirm] CONFIRM_KAPPA = {CFG.CONFIRM_KAPPA}\")\n"
        ),
        "new": (
            "    if getattr(args, \"confirm_kappa\", None) is not None:\n"
            "        CFG.CONFIRM_KAPPA = float(args.confirm_kappa)\n"
            "        log.info(f\"[Confirm] CONFIRM_KAPPA = {CFG.CONFIRM_KAPPA}\")\n"
            "    # ══ [RASE Phase 1] CLI wiring ══\n"
            "    if getattr(args, \"rase\", False):\n"
            "        CFG.RASE_ENABLED = True\n"
            "        log.info(\"[RASE] Phase 1 ENABLED — regime-adaptive dip + sub-bar rejection\")\n"
            "    if getattr(args, \"rase_dip_floor\", None) is not None:\n"
            "        CFG.RASE_DIP_FLOOR_FRAC = float(args.rase_dip_floor)\n"
            "    if getattr(args, \"rase_dip_cap\", None) is not None:\n"
            "        CFG.RASE_DIP_CAP_FRAC = float(args.rase_dip_cap)\n"
            "    if getattr(args, \"rase_p75_window\", None) is not None:\n"
            "        CFG.RASE_REGIME_GAUGE_P75_WINDOW = int(args.rase_p75_window)\n"
            "    if CFG.RASE_ENABLED:\n"
            "        if CFG.RASE_DIP_CAP_FRAC < CFG.RASE_DIP_FLOOR_FRAC:\n"
            "            CFG.RASE_DIP_FLOOR_FRAC, CFG.RASE_DIP_CAP_FRAC = (\n"
            "                CFG.RASE_DIP_CAP_FRAC, CFG.RASE_DIP_FLOOR_FRAC\n"
            "            )\n"
            "        log.info(f\"[RASE] floor={CFG.RASE_DIP_FLOOR_FRAC:.2f} \"\n"
            "                 f\"cap={CFG.RASE_DIP_CAP_FRAC:.2f} \"\n"
            "                 f\"p75_window={CFG.RASE_REGIME_GAUGE_P75_WINDOW}\")\n"
            "    # ══ [TP DYNAMIC] CLI wiring ══\n"
            "    if getattr(args, \"tp_dynamic\", False):\n"
            "        CFG.TP_DYNAMIC_MULT = True\n"
            "        log.info(\"[TP-Dynamic] ENABLED\")\n"
            "    if getattr(args, \"tp_dyn_min\", None) is not None:\n"
            "        CFG.TP_MIN_MULT = float(args.tp_dyn_min)\n"
            "    if getattr(args, \"tp_dyn_max\", None) is not None:\n"
            "        CFG.TP_MAX_MULT = float(args.tp_dyn_max)\n"
            "    if getattr(args, \"tp_dyn_sigma_cap\", None) is not None:\n"
            "        CFG.TP_PHYSICS_SIGMA_CAP = float(args.tp_dyn_sigma_cap)\n"
            "    if getattr(args, \"tp_dyn_horizon\", None) is not None:\n"
            "        CFG.TP_HORIZON_BARS_1H = int(args.tp_dyn_horizon)\n"
            "    if getattr(args, \"tp_reject_below_min\", False):\n"
            "        CFG.TP_REJECT_BELOW_MIN = True\n"
            "    if CFG.TP_DYNAMIC_MULT:\n"
            "        if CFG.TP_MIN_MULT > CFG.TP_MAX_MULT:\n"
            "            CFG.TP_MIN_MULT, CFG.TP_MAX_MULT = CFG.TP_MAX_MULT, CFG.TP_MIN_MULT\n"
            "        log.info(f\"[TP-Dynamic] min={CFG.TP_MIN_MULT:.2f} \"\n"
            "                 f\"max={CFG.TP_MAX_MULT:.2f} \"\n"
            "                 f\"sigma_cap={CFG.TP_PHYSICS_SIGMA_CAP:.2f} \"\n"
            "                 f\"reject={CFG.TP_REJECT_BELOW_MIN}\")\n"
            "    # ══ [NOTIONAL-FRAC-CAP] ══\n"
            "    if getattr(args, \"max_notional_frac\", None) is not None:\n"
            "        CFG.MAX_NOTIONAL_PER_TRADE_FRAC = float(args.max_notional_frac)\n"
            "        if CFG.MAX_NOTIONAL_PER_TRADE_FRAC < 0:\n"
            "            CFG.MAX_NOTIONAL_PER_TRADE_FRAC = 0.0\n"
            "        log.info(f\"[Notional] per-trade cap = {CFG.MAX_NOTIONAL_PER_TRADE_FRAC*100:.0f}% of capital\")\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P14 — Live notional cap per trade
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P14-live-notional-cap",
        "desc": "run_live: apply MAX_NOTIONAL_PER_TRADE_FRAC after cap_notional",
        "old": (
            "                    qty = min(qty_risk_based, qty_leverage_based)\n"
            "\n"
            "                    # ══ [NOTIONAL CAP] ══\n"
            "                    qty = cap_notional(qty, lmt)\n"
            "\n"
            "                    if qty * lmt < cfg.MIN_NOTIONAL:\n"
            "                        continue\n"
        ),
        "new": (
            "                    qty = min(qty_risk_based, qty_leverage_based)\n"
            "\n"
            "                    # ══ [NOTIONAL CAP] ══\n"
            "                    qty = cap_notional(qty, lmt)\n"
            "\n"
            "                    # ══ [NOTIONAL-FRAC-CAP] سقف صريح لكل صفقة ══\n"
            "                    _frac_cap = float(getattr(CFG, 'MAX_NOTIONAL_PER_TRADE_FRAC', 0.0))\n"
            "                    if _frac_cap > 0 and cap_live > 0:\n"
            "                        _cap_usd = cap_live * _frac_cap\n"
            "                        if qty * lmt > _cap_usd:\n"
            "                            qty = _cap_usd / lmt\n"
            "\n"
            "                    if qty * lmt < cfg.MIN_NOTIONAL:\n"
            "                        continue\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P15 — Backtest notional cap per trade (simulate_portfolio)
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P15-backtest-notional-cap",
        "desc": "simulate_portfolio: apply MAX_NOTIONAL_PER_TRADE_FRAC",
        "old": (
            "        # ══ [NOTIONAL CAP] ══\n"
            "        qty = cap_notional(qty, eff_px)\n"
            "\n"
            "        not_ = qty * eff_px\n"
            "\n"
            "        if not_ < CFG.MIN_NOTIONAL: continue\n"
        ),
        "new": (
            "        # ══ [NOTIONAL CAP] ══\n"
            "        qty = cap_notional(qty, eff_px)\n"
            "\n"
            "        # ══ [NOTIONAL-FRAC-CAP] سقف صريح لكل صفقة ══\n"
            "        _frac_cap = float(getattr(CFG, 'MAX_NOTIONAL_PER_TRADE_FRAC', 0.0))\n"
            "        if _frac_cap > 0 and capital > 0:\n"
            "            _cap_usd = capital * _frac_cap\n"
            "            if qty * eff_px > _cap_usd:\n"
            "                qty = _cap_usd / eff_px\n"
            "\n"
            "        not_ = qty * eff_px\n"
            "\n"
            "        if not_ < CFG.MIN_NOTIONAL: continue\n"
        ),
    },

    # ═══════════════════════════════════════════════════════════════════════
    # P16 — Version marker
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": "P16-marker",
        "desc": "Add RASE-REMAINING-IMPROVEMENTS marker at file top",
        "old": (
            "# ═══ [REV-SUBBAR-ENTRY-APPLIED] ═══\n"
            "# ═══ [DOTENV-APPLIED] ═══\n"
        ),
        "new": (
            "# ═══ [RASE-REMAINING-IMPROVEMENTS-APPLIED] ═══\n"
            "# ═══ [REV-SUBBAR-ENTRY-APPLIED] ═══\n"
            "# ═══ [DOTENV-APPLIED] ═══\n"
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def _count_occurrences(text, pattern):
    return text.count(pattern) if pattern else 0


def _apply_one_patch(content, patch):
    old, new, pid = patch["old"], patch["new"], patch["id"]
    if _count_occurrences(content, new) == 1:
        return content, "already_applied", f"{pid}: already applied"
    old_count = _count_occurrences(content, old)
    if old_count == 0:
        return content, "not_found", f"{pid}: anchor not found"
    if old_count > 1:
        return content, "ambiguous", f"{pid}: anchor appears {old_count}×"
    return content.replace(old, new, 1), "applied", f"{pid}: OK"


def _verify_syntax(content):
    try:
        ast.parse(content)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"


def _is_already_patched(content):
    return MARKER in content


def run_patch(target, dry_run=False):
    print(f"\n{'═' * 74}")
    print(f"  RASE + Fixes — Remaining Improvements Patcher")
    print(f"  Target: {target}")
    print(f"  Mode  : {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"{'═' * 74}\n")

    if not target.exists():
        print(f"  ❌ Target file not found: {target}\n")
        return 1

    original = target.read_text(encoding="utf-8")
    print(f"  📄 Loaded {len(original):,} chars "
          f"({original.count(chr(10)):,} lines)\n")

    if _is_already_patched(original):
        print(f"  ⚠️  File already contains marker: {MARKER}")
        all_present = True
        for patch in PATCHES:
            if _count_occurrences(original, patch["new"]) != 1:
                print(f"     ❌ {patch['id']}: missing or duplicated")
                all_present = False
        if all_present:
            print(f"  ✅ All {len(PATCHES)} patches verified present.\n")
            return 0
        print(f"  ⚠️  Some patches missing despite marker — consider --rollback.\n")
        return 2

    content = original
    applied, skipped, failed = [], [], []

    for i, patch in enumerate(PATCHES, 1):
        pid = patch["id"]
        print(f"  [{i:02d}/{len(PATCHES)}] {pid} ... ", end="", flush=True)
        new_content, status, detail = _apply_one_patch(content, patch)
        if status == "applied":
            content = new_content
            applied.append(patch)
            print("✅")
        elif status == "already_applied":
            skipped.append(patch)
            print("⏭️  already")
        else:
            failed.append((patch, detail))
            print(f"❌ {status}")
            print(f"        └─ {detail}")

    print(f"\n{'─' * 74}")
    print(f"  Summary: {len(applied)} applied, {len(skipped)} already, "
          f"{len(failed)} failed")
    print(f"{'─' * 74}\n")

    if failed:
        print(f"  ❌ Patching aborted — {len(failed)} patch(es) failed.")
        print(f"     No file was modified.\n")
        for patch, detail in failed:
            print(f"     • {patch['id']}: {detail}")
            print(f"       {patch['desc']}\n")
        return 3

    if len(applied) == 0:
        print(f"  ✅ File already fully patched.\n")
        return 0

    print(f"  🔍 Validating syntax (ast.parse)...")
    ok, err = _verify_syntax(content)
    if not ok:
        print(f"  ❌ Syntax validation FAILED: {err}")
        print(f"     No file was modified.\n")
        return 4
    print(f"  ✅ Syntax OK\n")

    if dry_run:
        print(f"  🧪 DRY-RUN — would write {len(content):,} chars "
              f"to {target}\n")
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = target.with_suffix(target.suffix + f".rase_rm_backup_{ts}")
    try:
        shutil.copy2(target, backup_path)
        print(f"  💾 Backup: {backup_path.name}")
    except Exception as e:
        print(f"  ❌ Backup failed: {e}\n")
        return 5

    tmp_path = target.with_suffix(target.suffix + ".rase_rm_tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, target)
        print(f"  ✅ Written: {target}")
        print(f"     Backup : {backup_path.name}\n")
    except Exception as e:
        print(f"  ❌ Write failed: {e}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        try:
            if backup_path.exists():
                shutil.copy2(backup_path, target)
                print(f"  🔄 Auto-rollback complete.\n")
        except Exception:
            pass
        return 6

    print(f"{'═' * 74}")
    print(f"  ✅ All improvements applied successfully!")
    print(f"{'═' * 74}")
    print(f"  To enable RASE:")
    print(f"      --rase")
    print(f"  To enable TP_DYNAMIC:")
    print(f"      --tp-dynamic --tp-dyn-min 2.0 --tp-dyn-max 5.0")
    print(f"  To enable per-trade notional cap:")
    print(f"      --max-notional-frac 0.5  (50% max per trade)")
    print(f"")
    print(f"  Rollback:")
    print(f"      python3 {Path(__file__).name} --rollback")
    print(f"{'═' * 74}\n")
    return 0


def run_verify(target):
    print(f"\n{'═' * 74}")
    print(f"  RASE + Fixes Verification")
    print(f"  Target: {target}")
    print(f"{'═' * 74}\n")
    if not target.exists():
        print(f"  ❌ Target not found.\n")
        return 1
    content = target.read_text(encoding="utf-8")
    print(f"  Marker present : {'✅ YES' if _is_already_patched(content) else '❌ NO'}\n")
    ok, bad = 0, 0
    for patch in PATCHES:
        pid = patch["id"]
        if _count_occurrences(content, patch["new"]) == 1:
            print(f"  ✅ {pid:35s} applied")
            ok += 1
        elif _count_occurrences(content, patch["old"]) == 1:
            print(f"  ❌ {pid:35s} NOT applied")
            bad += 1
        else:
            print(f"  ⚠️  {pid:35s} anchor missing")
            bad += 1
    print(f"\n{'─' * 74}")
    if ok == len(PATCHES):
        print(f"  ✅ All {len(PATCHES)} patches verified.\n")
        return 0
    print(f"  ⚠️  {ok}/{len(PATCHES)} verified, {bad} issue(s).\n")
    return 2


def run_rollback(target):
    print(f"\n{'═' * 74}")
    print(f"  RASE + Fixes Rollback")
    print(f"  Target: {target}")
    print(f"{'═' * 74}\n")
    if not target.exists():
        print(f"  ❌ Target not found.\n")
        return 1
    backups = sorted(
        target.parent.glob(target.name + ".rase_rm_backup_*"),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    if not backups:
        print(f"  ❌ No backups found.\n")
        return 1
    latest = backups[0]
    print(f"  🔍 Restoring from: {latest.name}")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = target.with_suffix(target.suffix + f".pre_rollback_{ts}")
    try:
        shutil.copy2(target, pre)
        print(f"  💾 Pre-rollback snapshot: {pre.name}")
    except Exception as e:
        print(f"  ❌ Pre-rollback failed: {e}\n")
        return 2
    try:
        shutil.copy2(latest, target)
        print(f"  ✅ Rolled back: {target}\n")
    except Exception as e:
        print(f"  ❌ Rollback failed: {e}\n")
        return 3
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="RASE + Fixes — Remaining Improvements Patcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 rase_remaining_improvements_patcher.py\n"
            "  python3 rase_remaining_improvements_patcher.py --dry-run\n"
            "  python3 rase_remaining_improvements_patcher.py --verify-only\n"
            "  python3 rase_remaining_improvements_patcher.py --rollback\n"
        ),
    )
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv)
    target = Path(args.target).resolve()
    try:
        if args.rollback:
            return run_rollback(target)
        if args.verify_only:
            return run_verify(target)
        return run_patch(target, dry_run=args.dry_run)
    except KeyboardInterrupt:
        print("\n\n  ⏹️  Interrupted.\n")
        return 130
    except Exception as e:
        print(f"\n  💥 Unexpected error: {type(e).__name__}: {e}\n")
        import traceback
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())
