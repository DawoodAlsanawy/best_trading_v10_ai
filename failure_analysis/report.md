# Failure Pattern Analysis — Stage 1

**Generated**: 2026-10-20 00:45 UTC
**Source run**: started_at=`2026-10-20 00:25:45`, TF=`4h`, capital=`$100.0`

## 🎯 Executive Summary

- **Total analyzed**: 6,650 trades
- **A (Direct Fail)**: 3,533 (53.1%)
- **B (Partial+SL)**: 2,366 (35.6%)
- **D (Winner)**: 751 (11.3%)

- **Current Sharpe**: 1.445
- **Mean log_return**: 0.001148
- **Total net_pnl**: $207,004.50

### Category Economics

| Category | n | mean log_return | mean net_pnl | mean MFE |
|----------|---|-----------------|--------------|----------|
| A | 3,533 | -0.003375 | $-160.83 | 0.32% |
| B | 2,366 | 0.001778 | $76.22 | 3.36% |
| D | 751 | 0.020442 | $792.11 | 9.08% |

### Counterfactual: Block ALL A (upper bound)

- **Sharpe if A blocked**: 6.316 (vs current 1.445)
- **Mean log_return**: 0.006275 (vs current 0.001148)

## 🌊 Regime Analysis

| Regime | n | P(A) | P(B) | P(D) |
|--------|---|------|------|------|
| Trending_Weak | 276 | 61.2% | 30.8% | 8.0% |
| Squeeze | 152 | 57.9% | 32.9% | 9.2% |
| Ranging | 283 | 56.2% | 35.7% | 8.1% |
| Trending_Strong | 5,544 | 53.1% | 35.9% | 11.0% |
| Volatile_Spike | 395 | 43.5% | 35.7% | 20.8% |

**⚠️ Regime `Trending_Weak` has P(A)=61.2% across 276 trades — candidate for exclusion.**

## 🔬 Feature Effect Sizes (A vs D)

| Feature | mean A | mean D | Cohen's d |
|---------|--------|--------|-----------|
| `T_info_val` | 4.1714 | 5.2801 | -0.534 |
| `T_info` | 4.1714 | 5.2801 | -0.534 |
| `E_therm` | 0.0159 | 0.0214 | -0.521 |
| `dyn_sl_factor` | 0.0476 | 0.0643 | -0.521 |
| `sl_dist_frac` | 0.0198 | 0.0297 | -0.501 |
| `sl_sigma` | 1.1126 | 1.2642 | -0.429 |
| `ret_24` | 0.0212 | 0.0729 | -0.323 |
| `ret_12` | 0.0178 | 0.0577 | -0.318 |
| `ret_6` | 0.0144 | 0.0409 | -0.298 |
| `dist_low_100` | 0.1726 | 0.2644 | -0.263 |
| `vol_ratio_3_20` | 1.2856 | 1.5079 | -0.249 |
| `ret_3` | 0.0099 | 0.0250 | -0.243 |
| `H_over_Hmax` | 0.4188 | 0.3886 | +0.220 |
| `friction` | 0.1904 | 0.1962 | -0.219 |
| `H` | 1.9434 | 1.8031 | +0.218 |
| `accel_3_6` | -0.0044 | -0.0159 | +0.216 |
| `delta_gap` | 0.4111 | 0.4451 | -0.186 |
| `atr_pctile` | 0.5061 | 0.5569 | -0.153 |
| `wr_prior_sym` | 0.1221 | 0.1379 | -0.147 |
| `dist_from_ema_norm` | -3.0210 | -1.7482 | -0.132 |

**Interpretation**: |d|>0.5 = strong, |d|>0.3 = moderate, |d|<0.2 = weak.

## 📊 Feature Importances (Random Forest)

| Rank | Feature | Importance |
|------|---------|------------|
| 1 | `T_info_val` | 0.0739 |
| 2 | `T_info` | 0.0655 |
| 3 | `dyn_sl_factor` | 0.0632 |
| 4 | `ret_12` | 0.0529 |
| 5 | `btc_ret_24` | 0.0518 |
| 6 | `rr_design` | 0.0513 |
| 7 | `E_therm` | 0.0439 |
| 8 | `sl_dist_frac` | 0.0414 |
| 9 | `dist_low_100` | 0.0377 |
| 10 | `ret_24` | 0.0373 |
| 11 | `btc_ret_6` | 0.0304 |
| 12 | `accel_3_6` | 0.0294 |
| 13 | `friction_drag_over_sl` | 0.0289 |
| 14 | `ret_3` | 0.0266 |
| 15 | `ret_6` | 0.0263 |
| 16 | `sl_sigma` | 0.0257 |
| 17 | `dist_from_ema_norm` | 0.0235 |
| 18 | `wick_upper_avg` | 0.0233 |
| 19 | `btc_ema_slope` | 0.0221 |
| 20 | `dist_high_100` | 0.0187 |

## 🎯 Discovered Rules (Pure A-enriched)

Found **6** rules with P(A) ≥ 60% and P(D) ≤ 10%, min_n=30.

| # | Conditions | n | P(A) | P(D) |
|---|-----------|---|------|------|
| 1 | E_therm <= 0.0188 AND btc_ret_24 <= 0.0717 AND T_info <= 3.7230 AND dist_high_100 <= -0.0657 AND btc_ret_24 <= -0.0031 | 308 | 92.2% | 7.8% |
| 2 | E_therm <= 0.0188 AND btc_ret_24 <= 0.0717 AND T_info <= 3.7230 AND dist_high_100 > -0.0657 AND rr_design > 9.3717 | 224 | 98.7% | 1.3% |
| 3 | E_therm <= 0.0188 AND btc_ret_24 <= 0.0717 AND T_info > 3.7230 AND ret_24 <= -0.0368 AND score > 5.1406 | 128 | 96.9% | 3.1% |
| 4 | E_therm > 0.0188 AND ret_24 <= -0.0434 AND dist_high_100 <= -0.2552 AND btc_ret_24 <= -0.0749 AND ret_12 > -0.1396 | 77 | 98.7% | 1.3% |
| 5 | E_therm > 0.0188 AND ret_24 <= -0.0434 AND dist_high_100 > -0.2552 AND btc_ret_6 > -0.0590 AND ret_3 > -0.0685 | 122 | 98.4% | 1.6% |
| 6 | E_therm > 0.0188 AND ret_24 > -0.0434 AND T_info <= 7.3626 AND dynamic_risk <= 0.0190 AND btc_ema_slope <= -0.0363 | 48 | 100.0% | 0.0% |

## 💱 Symbol-level Analysis

Top 10 loss-heavy symbols:

| Symbol | n | n_A | n_D | P(A) | Total PnL |
|--------|---|-----|-----|------|-----------|
| NMR/USDT | 72 | 49 | 1 | 68.1% | $-3,176.18 |
| BNB/USDT | 92 | 63 | 3 | 68.5% | $-2,497.00 |
| NEO/USDT | 75 | 49 | 3 | 65.3% | $-2,399.87 |
| TIA/USDT | 59 | 37 | 3 | 62.7% | $-2,105.05 |
| ZK/USDT | 61 | 36 | 4 | 59.0% | $-2,001.49 |
| MANA/USDT | 68 | 37 | 3 | 54.4% | $-1,975.96 |
| G/USDT | 59 | 38 | 2 | 64.4% | $-1,826.06 |
| TRX/USDT | 52 | 38 | 2 | 73.1% | $-1,780.38 |
| ETH/USDT | 68 | 40 | 1 | 58.8% | $-1,558.02 |
| SNX/USDT | 68 | 38 | 4 | 55.9% | $-1,541.20 |

## 🎯 Recommendations for Stage 2

1. **Implement top rule** as pre-entry filter: `E_therm <= 0.0188 AND btc_ret_24 <= 0.0717 AND T_info <= 3.7230 AND dist_high_100 <= -0.0657 AND btc_ret_24 <= -0.0031` (catches 284 A, kills 24 D over 308 trades).
2. **Exclude regime `Trending_Weak`** (P(A)=61.2%).
3. **Consider excluding ALGO/USDT, BAND/USDT, BNB/USDT** (negative PnL).
