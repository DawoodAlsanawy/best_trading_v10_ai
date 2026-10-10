#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_psi2.py
=============
Ψ² — Numerical HJB solver with explicit belief state.

Implements the true HJB equation via:

    V(b) = w^T·b - (1/2)·Σ h_i·b_i²

    Ψ²(b) = argmax_a [ R(b,a) + γ·V(b') ]

where:
    b   = Gaussian belief N(μ, diag(σ²)) over market state
    R   = log-utility integrated over belief uncertainty
    w,h = learned parameters (TD updates)

Key improvements over Ψ¹:
    1. Explicit belief with per-dimension variance
    2. Uncertainty penalty (from HJB diffusion term)
    3. Quadratic value function (from Taylor 2nd order)
    4. Bayesian belief update (Kalman-like)
    5. Belief-integrated reward (Laplace approx)

Default: DISABLED. Enable with --psi2.

Usage:
    python apply_psi2.py \\
        --input  trading_2_full_sync.py \\
        --output trading_2_psi2.py
"""

import argparse
import os
import sys
from datetime import datetime


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _replace_once(src, old, new, label, marker=None):
    if marker and marker in src:
        print(f"   ℹ️  [{label}] already applied")
        return src, True
    if old not in src:
        print(f"   ❌ [{label}] anchor not found")
        head = old[:70].split("\n")[0]
        idx = src.find(head)
        if idx >= 0:
            print(f"      near: {src[max(0, idx-120):idx+280]!r}")
        return src, False
    n = src.count(old)
    if n > 1:
        print(f"   ⚠️  [{label}] anchor ×{n}, replacing first")
    src = src.replace(old, new, 1)
    print(f"   ✅ [{label}]")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Ψ² BLOCK — inserted before load_symbol_meta
# ══════════════════════════════════════════════════════════════════════

PSI2_BLOCK = r'''# ══════════════════════════════════════════════════════════════════════
# [Ψ²] Numerical HJB Solver with Explicit Belief State
# ══════════════════════════════════════════════════════════════════════
#
# Mathematical foundation:
#
#   0 = max_a { R(b,a) + <∇V, F> + ½·Tr[Σ·∇²V] - λ·V }
#
# Approximated via 2nd-order Taylor:
#
#   V(b) = w^T·b - ½·Σ_i h_i·b_i²
#
# Decision:
#
#   Ψ²(b) = argmax_a [ R(b,a) + γ·V(b') ]
#
# Learning (TD with quadratic VFA):
#
#   δ = r + γ·V(b') - V(b)
#   w ← w + α·δ·b
#   h ← h + α·δ·b²
#
# Belief update (Kalman-style):
#
#   After observation z:
#     K = σ² / (σ² + r_obs)
#     μ' = μ + K·(z - μ)
#     σ²' = (1 - K)·σ²
#
# ══════════════════════════════════════════════════════════════════════

_PSI2_ENABLED: bool = False
_PSI2_ALPHA_W: float = 0.01       # learning rate for linear coeffs
_PSI2_ALPHA_H: float = 0.005      # learning rate for quadratic coeffs
_PSI2_GAMMA: float = 0.95         # discount factor
_PSI2_LAMBDA: float = 0.02        # HJB discount (1/horizon)
_PSI2_RISK_AVERSION: float = 0.5  # Laplace uncertainty weight
_PSI2_MIN_TRADES: int = 50        # start using learned V after this
_PSI2_STATE_FILE: str = "psi2_state.json"

# Belief dimension = 10
_PSI2_DIM: int = 10
_PSI2_FEATURES: List[str] = [
    "mu_drift",       # 0: estimated edge (from trade outcomes)
    "log_sigma",      # 1: log(volatility)
    "log_n_open",     # 2: log(1 + n_open)
    "heat",           # 3: portfolio heat
    "win_rate",       # 4: recent win rate
    "sharpe",         # 5: recent Sharpe (normalized)
    "log_age",        # 6: log(1 + hours since last exit)
    "p_hat",          # 7: current signal Bayesian edge
    "log_capital",    # 8: log(C / C0)
    "regime",         # 9: normalized regime indicator
]

# ── Mutable state ─────────────────────────────────────────────────────
_PSI2_BELIEF_MU = np.zeros(_PSI2_DIM, dtype=np.float64)
_PSI2_BELIEF_VAR = np.ones(_PSI2_DIM, dtype=np.float64) * 0.25
_PSI2_W = np.zeros(_PSI2_DIM, dtype=np.float64)     # linear weights
_PSI2_H = np.zeros(_PSI2_DIM, dtype=np.float64)     # quadratic weights

_PSI2_STATE: Dict = {
    "n_updates": 0,
    "n_decisions": 0,
    "n_accepts": 0,
    "n_rejects": 0,
    "recent_R": [],
    "recent_wins": [],
    "last_exit_ts": 0.0,
    "last_report_ts": 0.0,
    "delta_history": [],
    "reject_reasons": {},
}

# Pending TD: sig_id → (b_before, r_now)
_PSI2_PENDING: Dict = {}


# ──────────────────────────────────────────────────────────────────────
# Belief update (Kalman-style)
# ──────────────────────────────────────────────────────────────────────

def _psi2_update_belief(mu_new: np.ndarray,
                         var_obs: np.ndarray,
                         decay: float = 1.0) -> None:
    """
    Update belief with new observations.
    Each dimension updated independently (diagonal Kalman).
    """
    global _PSI2_BELIEF_MU, _PSI2_BELIEF_VAR
    try:
        mu_new = np.asarray(mu_new, dtype=np.float64)[:_PSI2_DIM]
        var_obs = np.asarray(var_obs, dtype=np.float64)[:_PSI2_DIM]

        # Growth of uncertainty (predict step)
        _PSI2_BELIEF_VAR = _PSI2_BELIEF_VAR + 0.01 * decay

        # Update step
        for i in range(len(mu_new)):
            v = max(_PSI2_BELIEF_VAR[i], 1e-9)
            r = max(var_obs[i], 1e-9)
            K = v / (v + r)
            _PSI2_BELIEF_MU[i] = (
                _PSI2_BELIEF_MU[i]
                + K * (mu_new[i] - _PSI2_BELIEF_MU[i])
            )
            _PSI2_BELIEF_VAR[i] = (1.0 - K) * v

        _PSI2_STATE["n_updates"] += 1
    except Exception as e:
        log.debug(f"[Ψ²] update_belief failed: {e}")


def _psi2_reset_dim(idx: int) -> None:
    """Reset a belief dimension (e.g., after position change)."""
    if 0 <= idx < _PSI2_DIM:
        _PSI2_BELIEF_MU[idx] = 0.0
        _PSI2_BELIEF_VAR[idx] = 0.25


# ──────────────────────────────────────────────────────────────────────
# φ(b) — feature vector from belief
# ──────────────────────────────────────────────────────────────────────

def _psi2_features() -> np.ndarray:
    """
    φ(b) = [μ, -√σ²]  →  20-dim vector.
    - μ: expected state (from belief mean)
    - -√σ²: uncertainty penalty (from HJB diffusion)
    """
    try:
        mu = _PSI2_BELIEF_MU
        unc = -np.sqrt(np.maximum(_PSI2_BELIEF_VAR, 0.0))
        phi = np.concatenate([mu, unc])
        return np.nan_to_num(phi, nan=0.0, posinf=1.0, neginf=-1.0)
    except Exception:
        return np.zeros(_PSI2_DIM * 2, dtype=np.float64)


# ──────────────────────────────────────────────────────────────────────
# V(b) — quadratic value function
# ──────────────────────────────────────────────────────────────────────

def _psi2_value() -> float:
    """
    V(b) = w^T·b - ½·Σ h_i·b_i²
    (Linear + quadratic terms from Taylor 2nd order)
    """
    try:
        lin = float(np.dot(_PSI2_W, _PSI2_BELIEF_MU))
        quad = -0.5 * float(np.sum(_PSI2_H * (_PSI2_BELIEF_MU ** 2)))
        return lin + quad
    except Exception:
        return 0.0


def _psi2_value_at(mu: np.ndarray) -> float:
    """V at a hypothetical belief mean."""
    try:
        lin = float(np.dot(_PSI2_W, mu))
        quad = -0.5 * float(np.sum(_PSI2_H * (mu ** 2)))
        return lin + quad
    except Exception:
        return 0.0


# ──────────────────────────────────────────────────────────────────────
# R(b, a) — belief-integrated reward
# ──────────────────────────────────────────────────────────────────────

def _psi2_reward(p_hat: float, var_p: float,
                  f: float, rr: float) -> float:
    """
    R(b,a) = E_{p~N(p_hat, var_p)}[p·log(1+f·rr) + (1-p)·log(1-f)]

    First-order: p_hat·u_win + (1-p_hat)·u_loss
    Second-order: -½·var_p·(u_win - u_loss)²·risk_aversion
    """
    if f <= 0 or f >= 1.0 or rr <= 0:
        return 0.0
    p = float(np.clip(p_hat, 1e-6, 1.0 - 1e-6))
    u_win = float(np.log(max(1.0 + f * rr, 1e-9)))
    u_loss = float(np.log(max(1.0 - f, 1e-9)))
    r_mean = p * u_win + (1.0 - p) * u_loss
    spread = u_win - u_loss
    r_penalty = -0.5 * _PSI2_RISK_AVERSION * var_p * spread * spread
    return float(r_mean + r_penalty)


# ──────────────────────────────────────────────────────────────────────
# Build belief from current state
# ──────────────────────────────────────────────────────────────────────

def _psi2_observe_state(capital: float, peak: float,
                          open_pos_live: Dict,
                          p_hat: float, market_sigma: float,
                          regime_indicator: float = 0.0,
                          update_weight: float = 0.3) -> None:
    """
    Update belief from currently observable state.
    Called before each decision and after each trade.
    """
    try:
        c0 = max(float(getattr(CFG, "INITIAL_CAPITAL", 100.0)), 1e-9)
        log_cap = float(np.log(1.0 + capital / c0))
        log_sigma = float(np.log(max(market_sigma, 1e-6)))
        n_open = len(open_pos_live)
        log_n_open = float(np.log(1.0 + n_open))

        heat = 0.0
        for p in open_pos_live.values():
            try:
                heat += float(p.get("dyn_risk", 0.0) or 0.0)
            except Exception:
                pass

        recent_R = _PSI2_STATE.get("recent_R", [])
        if len(recent_R) >= 10:
            r = np.array(recent_R[-50:], dtype=np.float64)
            mu_r = float(np.mean(r))
            sd_r = float(np.std(r, ddof=1)) if len(r) > 1 else 1.0
            sharpe = (mu_r / sd_r * np.sqrt(len(r))
                      if sd_r > 1e-9 else 0.0)
            sharpe = float(np.clip(sharpe, -3.0, 3.0) / 3.0)
        else:
            sharpe = 0.0

        recent_w = _PSI2_STATE.get("recent_wins", [])
        wr = (float(np.mean(recent_w[-20:]))
              if len(recent_w) >= 5 else 0.5)

        last_exit = _PSI2_STATE.get("last_exit_ts", 0.0)
        if last_exit > 0:
            dt_h = max(0.0, time.time() - last_exit) / 3600.0
        else:
            dt_h = 24.0
        log_age = float(np.log(1.0 + dt_h))

        # Observation vector
        mu_obs = np.array([
            _PSI2_BELIEF_MU[0],     # keep drift estimate (learned elsewhere)
            log_sigma,
            log_n_open,
            heat,
            wr,
            sharpe,
            log_age,
            float(np.clip(p_hat, 0.0, 1.0)),
            log_cap,
            float(np.clip(regime_indicator, -1.0, 1.0)),
        ], dtype=np.float64)

        # Observation variances (higher = less confident in observation)
        var_obs = np.array([
            1e6,       # drift: NOT observed directly (kept from learning)
            0.10,      # log_sigma: fairly reliable
            0.05,      # log_n_open: exact
            0.01,      # heat: exact
            0.05,      # win_rate: noisy
            0.10,      # sharpe: noisy
            0.20,      # log_age: noisy
            0.05,      # p_hat: medium
            0.02,      # log_capital: exact
            0.10,      # regime: noisy
        ], dtype=np.float64)

        # Weighted update
        w_mu = update_weight * mu_obs + (1.0 - update_weight) * _PSI2_BELIEF_MU
        w_var = var_obs / max(update_weight, 1e-6)
        _psi2_update_belief(w_mu, w_var, decay=update_weight)

    except Exception as e:
        log.debug(f"[Ψ²] observe_state failed: {e}")


# ──────────────────────────────────────────────────────────────────────
# Ψ² — the decision function
# ──────────────────────────────────────────────────────────────────────

def psi2_decision(sym: str, sig, capital: float, peak: float,
                   open_pos_live: Dict, corr_cache: Dict,
                   exchange, ad, cfg,
                   last_exit_ts: float = 0.0) -> Dict:
    """
    Ψ²(b) = argmax_a [ R(b,a) + γ·V(b') ]
    """
    _PSI2_STATE["n_decisions"] += 1
    reject = {"accept": False, "qty": 0.0,
              "leverage": int(cfg.LEVERAGE_MIN),
              "f_actual": 0.0, "reason": "uninit",
              "phi_before": None, "r_now": 0.0}

    try:
        # 1. Bayesian edge
        fi = int(getattr(sig, "feat_idx", 0))
        x_signal = _unified_signal_x(sig, ad, fi)
        p_hat, var_p = _unified_bayesian_edge(x_signal)
        rr = _unified_get_rr(sig)
        f_sl = _unified_get_f_sl(sig)

        if p_hat <= 0.01 or rr <= 0:
            reject["reason"] = "no_edge"
            _PSI2_STATE["n_rejects"] += 1
            _PSI2_STATE["reject_reasons"]["no_edge"] = \
                _PSI2_STATE["reject_reasons"].get("no_edge", 0) + 1
            return reject

        # 2. Market context
        price = float(getattr(sig, "price", 0.0))
        if price <= 0:
            reject["reason"] = "invalid_price"
            return reject

        MVT = (_unified_compute_mvt(exchange, sym, price)
               if exchange is not None
               else (_mkt_meta_mvt(sym, price)
                     or float(getattr(cfg, "MIN_NOTIONAL", 5.0))))
        adv = _unified_get_adv(sym, ad)
        kappa = _unified_compute_kappa(adv, 5.0)
        mmr = (_unified_get_mmr(exchange, sym)
               if exchange is not None
               else float(getattr(cfg, "LIQ_FALLBACK_MMR", 0.02)))
        L_liq_max = _unified_compute_L_liq_max(mmr, f_sl, symbol=sym)
        H_max = _unified_compute_H_max()

        # 3. Free capital
        free_capital = float(capital)
        for pos in open_pos_live.values():
            try:
                pn = float(pos.get("entry", 0)) * float(pos.get("qty", 0))
                pL = max(int(pos.get("leverage", 1)), 1)
                free_capital -= pn / pL
            except Exception:
                pass
        free_capital = max(0.0, free_capital)

        # 4. Update belief from current observations
        market_sigma = 0.0
        try:
            if ad is not None and fi < len(ad.E_therm):
                market_sigma = float(ad.E_therm[fi])
        except Exception:
            pass
        _psi2_observe_state(
            capital=capital, peak=peak,
            open_pos_live=open_pos_live,
            p_hat=p_hat, market_sigma=market_sigma,
            regime_indicator=0.0, update_weight=0.3,
        )

        # 5. Snapshot belief before action
        phi_before = _psi2_features()
        V_before = _psi2_value()

        # 6. Tiers
        try:
            tiers = _symbol_tiers(sym, cfg)
        except Exception:
            tiers = [int(cfg.LEVERAGE_MIN), int(cfg.LEVERAGE_MAX)]

        # 7. Enumerate actions
        candidates = []
        for L in tiers:
            L = int(L)
            if L > L_liq_max: continue
            if L < int(cfg.LEVERAGE_MIN): continue

            N_by_margin = L * free_capital
            heat_av = max(0.0, H_max - _PSI2_BELIEF_MU[3])
            N_by_heat = heat_av * capital / f_sl if f_sl > 1e-9 else 0.0
            N_by_adv = kappa * adv
            N_by_abs = float(getattr(cfg, "MAX_ABS_NOTIONAL", 1e9))
            N_upper = min(N_by_margin, N_by_heat, N_by_adv, N_by_abs)
            N_lower = MVT
            if N_lower > N_upper:
                continue

            # Sample 7 qty levels
            for frac in (0.0, 0.15, 0.3, 0.5, 0.7, 0.85, 1.0):
                N = N_lower + frac * (N_upper - N_lower)
                f = N * f_sl / capital if capital > 1e-9 else 0.0
                if f > 0.15 or f <= 0:
                    continue

                r_now = _psi2_reward(p_hat, var_p, f, rr)

                # Approximate b' (after trade expected effect)
                mu_next = _PSI2_BELIEF_MU.copy()
                exp_ret = p_hat * (f * rr) - (1.0 - p_hat) * f
                c0 = max(float(getattr(CFG, "INITIAL_CAPITAL", 100.0)), 1e-9)
                mu_next[8] = float(np.log(
                    1.0 + max(capital * (1.0 + exp_ret), 0.0) / c0
                ))
                mu_next[2] = float(np.log(1.0 + len(open_pos_live) + 1))
                mu_next[3] = min(mu_next[3] + f, 1.0)

                V_next = _psi2_value_at(mu_next)
                J = r_now + _PSI2_GAMMA * V_next

                candidates.append({
                    "L": L, "N": N, "f": f,
                    "r": r_now, "V_next": V_next, "J": J,
                    "mu_next": mu_next,
                })

        if not candidates:
            reject["reason"] = "no_feasible"
            _PSI2_STATE["n_rejects"] += 1
            _PSI2_STATE["reject_reasons"]["no_feasible"] = \
                _PSI2_STATE["reject_reasons"].get("no_feasible", 0) + 1
            return reject

        # 8. argmax J
        best = max(candidates, key=lambda c: c["J"])
        best_J = best["J"]
        for c in candidates:
            if abs(c["J"] - best_J) < 1e-6 and c["L"] < best["L"]:
                best = c

        # 9. qty
        qty = best["N"] / price
        try:
            if exchange is not None:
                qty = _round_qty(exchange, sym, qty)
            else:
                qty = _round_qty_cached(sym, qty)
        except Exception:
            pass

        if qty <= 0:
            reject["reason"] = "zero_qty"
            _PSI2_STATE["n_rejects"] += 1
            return reject

        if qty * price < MVT * 0.99:
            reject["reason"] = "qty_below_mvt"
            _PSI2_STATE["n_rejects"] += 1
            _PSI2_STATE["reject_reasons"]["qty_below_mvt"] = \
                _PSI2_STATE["reject_reasons"].get("qty_below_mvt", 0) + 1
            return reject

        # 10. Accept
        _PSI2_STATE["n_accepts"] += 1
        result = {
            "accept": True,
            "qty": float(qty),
            "leverage": int(best["L"]),
            "f_actual": float(best["f"]),
            "reason": (f"J={best['J']:+.5f} "
                       f"r={best['r']:+.5f} V'={best['V_next']:+.5f} "
                       f"V={V_before:+.5f} L={best['L']} "
                       f"p={p_hat:.3f}"),
            "phi_before": phi_before,
            "r_now": float(best["r"]),
        }

        log.debug(
            f"[Ψ²] {sym} ACCEPT qty={qty:.6f} L={best['L']}x "
            f"f={best['f']*100:.2f}% J={best['J']:+.5f} "
            f"(r={best['r']:+.5f} V'={best['V_next']:+.5f})"
        )
        return result

    except Exception as e:
        log.warning(f"[Ψ²] {sym} error: {e}")
        reject["reason"] = f"exception:{str(e)[:40]}"
        return reject


# ──────────────────────────────────────────────────────────────────────
# Learning — TD update + belief update
# ──────────────────────────────────────────────────────────────────────

def psi2_register_pending(sig, phi_before: np.ndarray, r_now: float):
    if not _PSI2_ENABLED or sig is None or phi_before is None:
        return
    try:
        _PSI2_PENDING[id(sig)] = (phi_before, float(r_now))
    except Exception:
        pass


def psi2_learn_from_trade(sym: str, sig, ad,
                            outcome_R: float, success: bool,
                            capital_now: float, peak_now: float,
                            open_pos_live: Dict) -> bool:
    """Called after a trade closes. Updates θ and belief."""
    if not _PSI2_ENABLED:
        return False
    try:
        # Retrieve φ(s_before) and r that were stored at decision time
        entry = _PSI2_PENDING.pop(id(sig), None)
        if entry is None:
            return False
        phi_before, r_at_entry = entry

        # Observe trade outcome → update belief drift estimate
        # The "drift" dimension (index 0) is learned from outcomes
        # Use exponential moving average of R-multiples
        recent_R = _PSI2_STATE["recent_R"]
        recent_R.append(float(outcome_R))
        if len(recent_R) > 200:
            _PSI2_STATE["recent_R"] = recent_R[-100:]
        _PSI2_STATE["recent_wins"].append(1 if success else 0)
        if len(_PSI2_STATE["recent_wins"]) > 200:
            _PSI2_STATE["recent_wins"] = _PSI2_STATE["recent_wins"][-100:]

        # Update belief drift with observed outcome
        _PSI2_BELIEF_MU[0] = (0.9 * _PSI2_BELIEF_MU[0]
                                + 0.1 * float(outcome_R))
        _PSI2_BELIEF_VAR[0] = max(
            _PSI2_BELIEF_VAR[0] * 0.95, 0.01
        )

        # TD update on w and h
        # φ_after is the new belief features (post-update)
        phi_after = _psi2_features()
        V_before = _psi2_value_at(mu=phi_before[:_PSI2_DIM])
        V_after = _psi2_value()

        delta = float(outcome_R
                       + _PSI2_GAMMA * V_after
                       - V_before)

        # Linear update: w ← w + α_w · δ · b
        global _PSI2_W, _PSI2_H
        b_before = _PSI2_BELIEF_MU  # current (post-close) belief is close
        # Use the pre-decision feature slice (first DIM dims = belief mean)
        # We stored phi_before = concat(μ_before, -√σ²_before)
        mu_used = phi_before[:_PSI2_DIM]
        _PSI2_W = _PSI2_W + _PSI2_ALPHA_W * delta * mu_used

        # Quadratic update: h ← h + α_h · δ · b²
        _PSI2_H = _PSI2_H + _PSI2_ALPHA_H * delta * (mu_used ** 2)

        # Clip to prevent explosion
        _PSI2_W = np.clip(_PSI2_W, -10.0, 10.0)
        _PSI2_H = np.clip(_PSI2_H, -5.0, 5.0)

        _PSI2_STATE["delta_history"].append(abs(delta))
        if len(_PSI2_STATE["delta_history"]) > 200:
            _PSI2_STATE["delta_history"] = \
                _PSI2_STATE["delta_history"][-100:]

        # Persist every 20 updates
        if _PSI2_STATE["n_updates"] % 20 == 0:
            _psi2_save_state()

        log.debug(
            f"[Ψ²] {sym} TD δ={delta:+.5f} "
            f"|w|={np.linalg.norm(_PSI2_W):.4f} "
            f"|h|={np.linalg.norm(_PSI2_H):.4f}"
        )
        return True
    except Exception as e:
        log.debug(f"[Ψ²] learn failed: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────
# Persistence
# ──────────────────────────────────────────────────────────────────────

def _psi2_load_state(path: Optional[str] = None) -> bool:
    global _PSI2_W, _PSI2_H, _PSI2_BELIEF_MU, _PSI2_BELIEF_VAR
    p = path or _PSI2_STATE_FILE
    if not os.path.exists(p):
        log.info(f"[Ψ²] No state at {p} — using zeros prior")
        return False
    try:
        with open(p) as f:
            d = json.load(f)
        w = d.get("w")
        h = d.get("h")
        bm = d.get("belief_mu")
        bv = d.get("belief_var")
        if w and len(w) == _PSI2_DIM:
            _PSI2_W = np.array(w, dtype=np.float64)
        if h and len(h) == _PSI2_DIM:
            _PSI2_H = np.array(h, dtype=np.float64)
        if bm and len(bm) == _PSI2_DIM:
            _PSI2_BELIEF_MU = np.array(bm, dtype=np.float64)
        if bv and len(bv) == _PSI2_DIM:
            _PSI2_BELIEF_VAR = np.array(bv, dtype=np.float64)
        _PSI2_STATE["n_updates"] = int(d.get("n_updates", 0))
        _PSI2_STATE["recent_R"] = list(d.get("recent_R", []))[-100:]
        _PSI2_STATE["recent_wins"] = list(d.get("recent_wins", []))[-100:]
        log.info(
            f"[Ψ²] State loaded: |w|={np.linalg.norm(_PSI2_W):.4f}, "
            f"|h|={np.linalg.norm(_PSI2_H):.4f}, "
            f"updates={_PSI2_STATE['n_updates']}"
        )
        return True
    except Exception as e:
        log.warning(f"[Ψ²] Load failed: {e}")
        return False


def _psi2_save_state(path: Optional[str] = None):
    p = path or _PSI2_STATE_FILE
    try:
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump({
                "w": _PSI2_W.tolist(),
                "h": _PSI2_H.tolist(),
                "belief_mu": _PSI2_BELIEF_MU.tolist(),
                "belief_var": _PSI2_BELIEF_VAR.tolist(),
                "n_updates": int(_PSI2_STATE["n_updates"]),
                "recent_R": _PSI2_STATE["recent_R"][-100:],
                "recent_wins": _PSI2_STATE["recent_wins"][-100:],
                "features": list(_PSI2_FEATURES),
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, f, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        log.debug(f"[Ψ²] Save failed: {e}")


# ──────────────────────────────────────────────────────────────────────
# Stats logger
# ──────────────────────────────────────────────────────────────────────

def psi2_log_stats():
    if not _PSI2_ENABLED:
        return
    now = time.time()
    if now - _PSI2_STATE.get("last_report_ts", 0.0) < 300:
        return
    _PSI2_STATE["last_report_ts"] = now
    a = _PSI2_STATE["n_accepts"]
    rj = _PSI2_STATE["n_rejects"]
    delta_hist = _PSI2_STATE.get("delta_history", [])
    avg_delta = float(np.mean(delta_hist[-50:])) if delta_hist else 0.0
    log.info(
        f"[Ψ²] decisions={_PSI2_STATE['n_decisions']} "
        f"accepts={a} rejects={rj} "
        f"updates={_PSI2_STATE['n_updates']} | "
        f"|w|={np.linalg.norm(_PSI2_W):.4f} "
        f"|h|={np.linalg.norm(_PSI2_H):.4f} "
        f"avg|δ|={avg_delta:.5f}"
    )
    reasons = _PSI2_STATE.get("reject_reasons", {})
    if reasons:
        top = sorted(reasons.items(), key=lambda kv: -kv[1])[:3]
        log.info(f"[Ψ²] top rejects: {top}")


# ══ end Ψ² block ══


'''


# ══════════════════════════════════════════════════════════════════════
# Edit 1: Insert block
# ══════════════════════════════════════════════════════════════════════

def edit1_insert_block(src):
    print("\n▶ Edit 1: insert Ψ² block")
    anchor = "def load_symbol_meta(mode: str) -> Dict[str, Dict]:"
    if anchor not in src:
        print("   ❌ anchor not found")
        return src, False
    if "[Ψ²] Numerical HJB Solver" in src:
        print("   ℹ️  already applied")
        return src, True
    src = src.replace(anchor, PSI2_BLOCK + anchor, 1)
    print(f"   ✅ inserted ({len(PSI2_BLOCK):,} chars)")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 2: Delegate inside compute_unified_decision
# ══════════════════════════════════════════════════════════════════════

def edit2_delegate(src):
    print("\n▶ Edit 2: delegate to Ψ² when enabled")
    if "[Ψ²] Delegate" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        '    _UNIFIED_STATS["calls"] += 1\n'
        '    default = {"accept": False, "qty": 0.0,\n'
        '               "leverage": int(cfg.LEVERAGE_MIN),\n'
        '               "f_actual": 0.0, "reason": "uninit", "candidates": []}'
    )
    if anchor not in src:
        print("   ❌ anchor not found")
        return src, False

    injection = anchor + (
        "\n"
        "    # [Ψ²] Delegate to psi2_decision when enabled\n"
        "    if _PSI2_ENABLED:\n"
        "        _p2 = psi2_decision(\n"
        "            sym=sym, sig=sig, capital=capital, peak=peak,\n"
        "            open_pos_live=open_pos_live or {},\n"
        "            corr_cache=corr_cache or {},\n"
        "            exchange=exchange, ad=ad, cfg=cfg,\n"
        "        )\n"
        "        if _p2.get(\"accept\"):\n"
        "            psi2_register_pending(\n"
        "                sig, _p2.get(\"phi_before\"), _p2.get(\"r_now\", 0.0)\n"
        "            )\n"
        "            return {\n"
        "                \"accept\": True,\n"
        "                \"qty\": float(_p2[\"qty\"]),\n"
        "                \"leverage\": int(_p2[\"leverage\"]),\n"
        "                \"f_actual\": float(_p2[\"f_actual\"]),\n"
        "                \"reason\": str(_p2.get(\"reason\", \"psi2\")),\n"
        "                \"candidates\": [],\n"
        "            }\n"
        "        else:\n"
        "            default[\"reason\"] = str(_p2.get(\"reason\", \"psi2_reject\"))\n"
        "            return default"
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ delegation inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 3: TD learning hook (live)
# ══════════════════════════════════════════════════════════════════════

def edit3_td_live(src):
    print("\n▶ Edit 3: Ψ² TD learning hook (live)")
    if "[Ψ²] TD live" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "                    # [Ψ] TD learning on close\n"
        "                    if _PSI_ENABLED:"
    )
    if anchor not in src:
        print("   ❌ anchor not found")
        return src, False

    injection = (
        "                    # [Ψ²] TD live\n"
        "                    if _PSI2_ENABLED:\n"
        "                        try:\n"
        "                            _ep = float(pos.get('entry') or 0)\n"
        "                            _sp = float(pos.get('sl_dist_initial') or 0)\n"
        "                            _xp = float(exec_price or 0)\n"
        "                            if _ep > 0 and _sp > 0 and _xp > 0:\n"
        "                                if pos.get('action') == 'BUY':\n"
        "                                    _pc = (_xp - _ep) / _ep\n"
        "                                else:\n"
        "                                    _pc = (_ep - _xp) / _ep\n"
        "                                _sc = _sp / _ep\n"
        "                                _Rc = _pc / _sc if _sc > 0 else 0.0\n"
        "                                psi2_learn_from_trade(\n"
        "                                    sym=sym,\n"
        "                                    sig=pos.get('_sig_ref') if isinstance(pos, dict) else None,\n"
        "                                    ad=assets.get(sym) if 'assets' in dir() else None,\n"
        "                                    outcome_R=float(_Rc),\n"
        "                                    success=_Rc > 0.5,\n"
        "                                    capital_now=float(cap_live),\n"
        "                                    peak_now=float(peak_cap_live),\n"
        "                                    open_pos_live=open_pos_live,\n"
        "                                )\n"
        "                                _PSI2_STATE['last_exit_ts'] = time.time()\n"
        "                        except Exception as _pe2:\n"
        "                            log.debug(f\"[Ψ²] TD live hook failed: {_pe2}\")\n"
        "\n"
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ TD live hook inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 4: TD learning hook (backtest)
# ══════════════════════════════════════════════════════════════════════

def edit4_td_backtest(src):
    print("\n▶ Edit 4: Ψ² TD learning hook (backtest)")
    if "[Ψ²] TD bt" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "        # [Ψ] TD learning on backtest close\n"
        "        if _PSI_ENABLED:"
    )
    if anchor not in src:
        print("   ❌ anchor not found")
        return src, False

    injection = (
        "        # [Ψ²] TD bt\n"
        "        if _PSI2_ENABLED:\n"
        "            try:\n"
        "                _sl_b = float(getattr(pos, 'sl_dist_initial', 0) or 0)\n"
        "                _en_b = float(pos.entry_px)\n"
        "                _ex_b = float(exit_eff)\n"
        "                if _sl_b > 0 and _en_b > 0:\n"
        "                    if sig.action == \"BUY\":\n"
        "                        _mv_b = _ex_b - _en_b\n"
        "                    else:\n"
        "                        _mv_b = _en_b - _ex_b\n"
        "                    _R_b = _mv_b / _sl_b\n"
        "                    psi2_learn_from_trade(\n"
        "                        sym=sig.symbol, sig=sig, ad=ad,\n"
        "                        outcome_R=float(_R_b),\n"
        "                        success=_R_b > 0.5,\n"
        "                        capital_now=float(capital),\n"
        "                        peak_now=float(peak_cap),\n"
        "                        open_pos_live={},\n"
        "                    )\n"
        "                    _PSI2_STATE['last_exit_ts'] = time.time()\n"
        "            except Exception as _pe_b:\n"
        "                log.debug(f\"[Ψ²] TD bt hook failed: {_pe_b}\")\n"
        "\n"
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ TD backtest hook inserted")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 5: Stats logger
# ══════════════════════════════════════════════════════════════════════

def edit5_wire_stats(src):
    print("\n▶ Edit 5: wire Ψ² stats logger")
    if "# [Ψ²] stats logger" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = (
        "            # [Ψ] stats logger\n"
        "            psi_log_stats()"
    )
    if anchor not in src:
        print("   ❌ anchor not found")
        return src, False

    new = anchor + (
        "\n"
        "            # [Ψ²] stats logger\n"
        "            psi2_log_stats()"
    )
    src = src.replace(anchor, new, 1)
    print("   ✅ stats logger wired")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 6: CLI args
# ══════════════════════════════════════════════════════════════════════

def edit6_add_cli(src):
    print("\n▶ Edit 6: add CLI args")
    if 'p.add_argument("--psi2"' in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = "    args = p.parse_args()"
    if anchor not in src:
        print("   ❌ parse_args anchor not found")
        return src, False

    injection = (
        '    # ══ [Ψ²] CLI args ══\n'
        '    p.add_argument("--psi2", action="store_true",\n'
        '                   help="Enable Ψ² numerical HJB solver")\n'
        '    p.add_argument("--psi2-state", type=str, default=None,\n'
        '                   help="Path to Ψ² state JSON")\n'
        '    p.add_argument("--psi2-alpha-w", type=float, default=None,\n'
        '                   help="Learning rate for linear weights")\n'
        '    p.add_argument("--psi2-alpha-h", type=float, default=None,\n'
        '                   help="Learning rate for quadratic weights")\n'
        '    p.add_argument("--psi2-gamma", type=float, default=None,\n'
        '                   help="Discount factor")\n'
        '\n'
        + anchor
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ CLI args added")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Edit 7: Wire CLI
# ══════════════════════════════════════════════════════════════════════

def edit7_wire_cli(src):
    print("\n▶ Edit 7: wire CLI")
    if "# [Ψ²] CLI wiring" in src:
        print("   ℹ️  already applied")
        return src, True

    anchor = "    args = p.parse_args()"
    if anchor not in src:
        print("   ❌ parse_args anchor not found")
        return src, False

    injection = anchor + (
        "\n"
        "    # [Ψ²] CLI wiring\n"
        "    try:\n"
        "        if getattr(args, 'psi2', False):\n"
        "            globals()['_PSI2_ENABLED'] = True\n"
        "            if getattr(args, 'psi2_state', None):\n"
        "                globals()['_PSI2_STATE_FILE'] = str(args.psi2_state)\n"
        "            if getattr(args, 'psi2_alpha_w', None) is not None:\n"
        "                globals()['_PSI2_ALPHA_W'] = float(args.psi2_alpha_w)\n"
        "            if getattr(args, 'psi2_alpha_h', None) is not None:\n"
        "                globals()['_PSI2_ALPHA_H'] = float(args.psi2_alpha_h)\n"
        "            if getattr(args, 'psi2_gamma', None) is not None:\n"
        "                globals()['_PSI2_GAMMA'] = float(args.psi2_gamma)\n"
        "            _psi2_load_state()\n"
        "            log.info(\n"
        "                f\"[Ψ²] ENABLED (α_w={_PSI2_ALPHA_W}, \"\n"
        "                f\"α_h={_PSI2_ALPHA_H}, γ={_PSI2_GAMMA})\"\n"
        "            )\n"
        "        else:\n"
        "            log.info(\"[Ψ²] Disabled (use --psi2 to enable)\")\n"
        "    except Exception as _e:\n"
        "        log.warning(f\"[Ψ²] CLI wiring failed: {_e}\")"
    )
    src = src.replace(anchor, injection, 1)
    print("   ✅ CLI wired")
    return src, True


# ══════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════

def verify(src):
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  VERIFY                                                     ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    checks = [
        ("Ψ² block",            "[Ψ²] Numerical HJB Solver"),
        ("_PSI2_ENABLED",       "_PSI2_ENABLED: bool = False"),
        ("_PSI2_BELIEF_MU",     "_PSI2_BELIEF_MU = np.zeros"),
        ("_PSI2_BELIEF_VAR",    "_PSI2_BELIEF_VAR = np.ones"),
        ("_PSI2_W",             "_PSI2_W = np.zeros"),
        ("_PSI2_H",             "_PSI2_H = np.zeros"),
        ("update belief",       "def _psi2_update_belief("),
        ("features",            "def _psi2_features("),
        ("value",               "def _psi2_value("),
        ("value_at",            "def _psi2_value_at("),
        ("reward",              "def _psi2_reward("),
        ("observe state",       "def _psi2_observe_state("),
        ("psi2_decision",       "def psi2_decision("),
        ("register pending",    "def psi2_register_pending("),
        ("learn",               "def psi2_learn_from_trade("),
        ("load state",          "def _psi2_load_state("),
        ("save state",          "def _psi2_save_state("),
        ("log stats",           "def psi2_log_stats("),
        ("delegate",            "[Ψ²] Delegate"),
        ("TD live",             "[Ψ²] TD live"),
        ("TD bt",               "[Ψ²] TD bt"),
        ("stats wired",         "# [Ψ²] stats logger"),
        ("CLI arg",             'p.add_argument("--psi2"'),
        ("CLI wiring",          "# [Ψ²] CLI wiring"),
    ]
    all_ok = True
    for label, marker in checks:
        ok = marker in src
        print(f"   {'✅' if ok else '❌'} {label}")
        if not ok:
            all_ok = False

    print("\n   Sanity:")
    for label, marker, expect in [
        ("def run_live", "def run_live(", 1),
        ("def run_backtest", "def run_backtest(", 1),
        ("def simulate_portfolio", "def simulate_portfolio(", 1),
        ("def compute_unified_decision",
            "def compute_unified_decision(", 1),
        ("def main", "def main(", 1),
        ("def _unified_compute_mvt", "def _unified_compute_mvt(", 1),
    ]:
        cnt = src.count(marker)
        ok = (cnt == expect)
        print(f"   {'✅' if ok else '❌'} {label}: {cnt}")
        if not ok:
            all_ok = False
    return all_ok


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="trading_2_full_sync.py")
    ap.add_argument("--output", default="trading_2_psi2.py")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ Input not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        src = f.read()
    print(f"📖 Loaded {args.input} ({len(src):,} chars)")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  Ψ² — Numerical HJB Solver with Explicit Belief State       ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    steps = [
        ("Edit 1: insert block",       edit1_insert_block),
        ("Edit 2: delegate",           edit2_delegate),
        ("Edit 3: TD live",            edit3_td_live),
        ("Edit 4: TD backtest",        edit4_td_backtest),
        ("Edit 5: wire stats",         edit5_wire_stats),
        ("Edit 6: CLI args",           edit6_add_cli),
        ("Edit 7: CLI wiring",         edit7_wire_cli),
    ]
    results = []
    for label, fn in steps:
        try:
            src, ok = fn(src)
            results.append((label, ok))
        except Exception as e:
            print(f"   ❌ {label} exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((label, False))

    all_ok = verify(src)

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  SYNTAX CHECK                                               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    syntax_ok = True
    try:
        compile(src, args.output, "exec")
        print("   ✅ compiles OK")
    except SyntaxError as e:
        print(f"   ❌ SyntaxError line {e.lineno}: {e.msg}")
        print(f"      Text: {e.text!r}")
        syntax_ok = False

    if not (all_ok and syntax_ok):
        print("\n╔══════════════════════════════════════════════════════════════╗")
        print("║  ❌ ABORTED — output NOT written                            ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        for label, ok in results:
            print(f"   {'✅' if ok else '❌'} {label}")
        print(f"   verify:  {'OK' if all_ok else 'FAILED'}")
        print(f"   syntax:  {'OK' if syntax_ok else 'FAILED'}")
        sys.exit(1)

    header = (
        "#!/usr/bin/env python3\n"
        "# -*- coding: utf-8 -*-\n"
        "# ═══════════════════════════════════════════════════════════\n"
        f"#  {os.path.basename(args.output)}\n"
        "#  Quantum Thermodynamic Trading Engine\n"
        "#  Ψ² — Numerical HJB Solver (belief state + quadratic V)\n"
        f"#  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"#  Base: {args.input}\n"
        "#\n"
        "#  Ψ²(b) = argmax_a [ R(b,a) + γ·V(b') ]\n"
        "#  V(b) = w^T·b - ½·Σ h_i·b_i²\n"
        "#  b = N(μ, diag(σ²))  (Gaussian belief)\n"
        "#\n"
        "#  Enable with --psi2.\n"
        "# ═══════════════════════════════════════════════════════════\n"
    )

    if src.startswith("#!"):
        first_nl = src.index("\n")
        src_out = header + src[first_nl + 1:]
    else:
        src_out = header + src

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(src_out)

    with open(args.output, "r", encoding="utf-8") as f:
        written = f.read()
    try:
        compile(written, args.output, "exec")
        write_ok = True
    except SyntaxError as e:
        write_ok = False
        print(f"   ❌ Written file broken at line {e.lineno}")

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║                             DONE                             ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"   Input:  {args.input}  ({len(src):,} chars)")
    print(f"   Output: {args.output}  ({len(src_out):,} chars)")
    for label, ok in results:
        print(f"   {'✅' if ok else '❌'} {label}")
    print(f"   verify:  {'✅ ALL PASSED' if all_ok else '❌ FAILED'}")
    print(f"   written: {'✅ OK' if write_ok else '❌ FAILED'}")
    print()
    print("  ▶ Run backtest with Ψ²:")
    print(f"     python {args.output} --mode backtest --psi2 "
          f"--capital 100 --nassets 5 --maxcon 2 --timeframe 4h --history-days 30")
    print()
    print("  ▶ Run backtest with Unified (baseline):")
    print(f"     python {args.output} --mode backtest --unified "
          f"--capital 100 --nassets 5 --maxcon 2 --timeframe 4h --history-days 30")

    if not write_ok:
        sys.exit(3)


if __name__ == "__main__":
    main()
