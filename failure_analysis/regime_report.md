# Stage 3A — Regime Detector + Stability Filter

**Generated**: 2026-10-20 01:07 UTC

## 🎯 Executive Summary

- **Total trades analyzed**: 6,650
- **Trades with valid GMM features**: 6,650 (100.0%)
- **GMM k selected**: 3
- **Regime balance**: largest=50.6%, smallest=13.2%, entropy_ratio=0.89
- **Features stable**: 18 accepted, 26 rejected

## 🌊 Regime Distribution × Category

| Regime | n | % total | P(A) | P(B) | P(D) | Mean confidence |
|--------|---|---------|------|------|------|-----------------|
| 0.0 | 3367 | 50.6% | 53.1% | 36.5% | 10.4% | 0.947 |
| 1.0 | 876 | 13.2% | 42.2% | 35.8% | 21.9% | 0.903 |
| 2.0 | 2407 | 36.2% | 57.1% | 34.2% | 8.6% | 0.962 |

**🎯 Best regime (lowest P(A))**: `1.0` (P(A)=42.2%, n=876)
**🚨 Worst regime (highest P(A))**: `2.0` (P(A)=57.1%, n=2407)

**Separation (P(A)_worst - P(A)_best)**: 14.9 pp
⚠️ **Regime detection has moderate signal** — some separation exists.

## 🔬 Feature Stability Results

**Thresholds**: mean_ks<0.1, max_ks<0.15, unstable_ratio<0.3

### ✅ Accepted (stable) features

| Feature | mean_ks | max_ks | unstable_ratio | n_windows |
|---------|---------|--------|----------------|-----------|
| `V` | 0.000 | 0.000 | 0.00 | 24 |
| `gap_count_5` | 0.004 | 0.014 | 0.00 | 24 |
| `tri_val` | 0.032 | 0.064 | 0.00 | 24 |
| `C` | 0.050 | 0.080 | 0.00 | 24 |
| `vol_accel` | 0.049 | 0.086 | 0.00 | 24 |
| `atr` | 0.055 | 0.104 | 0.04 | 24 |
| `vol_ratio_3_20` | 0.065 | 0.106 | 0.08 | 24 |
| `dH` | 0.056 | 0.112 | 0.04 | 24 |
| `dF` | 0.058 | 0.114 | 0.08 | 24 |
| `geodesic_accel` | 0.058 | 0.114 | 0.08 | 24 |
| `gauge_force` | 0.073 | 0.120 | 0.21 | 24 |
| `score` | 0.059 | 0.122 | 0.08 | 24 |
| `body_ratio_avg` | 0.070 | 0.126 | 0.12 | 24 |
| `adv_usd` | 0.065 | 0.132 | 0.08 | 24 |
| `delta_gap` | 0.056 | 0.136 | 0.04 | 24 |
| `friction` | 0.071 | 0.148 | 0.12 | 24 |
| `H_over_Hmax` | 0.071 | 0.148 | 0.12 | 24 |
| `H` | 0.071 | 0.148 | 0.12 | 24 |

### ❌ Rejected (unstable) features

| Feature | max_ks | Reasons |
|---------|--------|---------|
| `btc_ema_slope` | 0.498 | mean_ks=0.286>0.1; max_ks=0.498>0.15; unstable_ratio=1.00>0.3 |
| `btc_ret_24` | 0.396 | mean_ks=0.247>0.1; max_ks=0.396>0.15; unstable_ratio=0.96>0.3 |
| `dynamic_risk` | 0.396 | mean_ks=0.267>0.1; max_ks=0.396>0.15; unstable_ratio=0.92>0.3 |
| `dist_high_100` | 0.380 | mean_ks=0.180>0.1; max_ks=0.380>0.15; unstable_ratio=0.67>0.3 |
| `dist_low_100` | 0.376 | mean_ks=0.177>0.1; max_ks=0.376>0.15; unstable_ratio=0.79>0.3 |
| `dist_from_ema_norm` | 0.374 | mean_ks=0.182>0.1; max_ks=0.374>0.15; unstable_ratio=0.71>0.3 |
| `ema_slope` | 0.346 | mean_ks=0.161>0.1; max_ks=0.346>0.15; unstable_ratio=0.58>0.3 |
| `btc_ret_6` | 0.336 | mean_ks=0.178>0.1; max_ks=0.336>0.15; unstable_ratio=0.88>0.3 |
| `atr_pctile` | 0.332 | mean_ks=0.125>0.1; max_ks=0.332>0.15; unstable_ratio=0.46>0.3 |
| `ret_24` | 0.326 | mean_ks=0.156>0.1; max_ks=0.326>0.15; unstable_ratio=0.75>0.3 |
| `ret_12` | 0.320 | mean_ks=0.143>0.1; max_ks=0.320>0.15; unstable_ratio=0.71>0.3 |
| `ret_6` | 0.294 | mean_ks=0.140>0.1; max_ks=0.294>0.15; unstable_ratio=0.62>0.3 |
| `ret_3` | 0.266 | mean_ks=0.116>0.1; max_ks=0.266>0.15; unstable_ratio=0.46>0.3 |
| `ema_slope_against` | 0.248 | max_ks=0.248>0.15; unstable_ratio=0.33>0.3 |
| `wick_upper_avg` | 0.244 | max_ks=0.244>0.15; unstable_ratio=0.42>0.3 |
| `friction_drag_over_sl` | 0.242 | mean_ks=0.137>0.1; max_ks=0.242>0.15; unstable_ratio=0.62>0.3 |
| `sl_sigma` | 0.242 | mean_ks=0.137>0.1; max_ks=0.242>0.15; unstable_ratio=0.62>0.3 |
| `rr_design` | 0.234 | mean_ks=0.137>0.1; max_ks=0.234>0.15; unstable_ratio=0.62>0.3 |
| `T_info` | 0.234 | mean_ks=0.137>0.1; max_ks=0.234>0.15; unstable_ratio=0.62>0.3 |
| `E_therm` | 0.234 | mean_ks=0.137>0.1; max_ks=0.234>0.15; unstable_ratio=0.62>0.3 |
| `T_info_val` | 0.234 | mean_ks=0.137>0.1; max_ks=0.234>0.15; unstable_ratio=0.62>0.3 |
| `dyn_sl_factor` | 0.234 | mean_ks=0.137>0.1; max_ks=0.234>0.15; unstable_ratio=0.62>0.3 |
| `sl_dist_frac` | 0.232 | mean_ks=0.138>0.1; max_ks=0.232>0.15; unstable_ratio=0.62>0.3 |
| `accel_3_6` | 0.228 | max_ks=0.228>0.15; unstable_ratio=0.46>0.3 |
| `wick_lower_avg` | 0.180 | max_ks=0.180>0.15; unstable_ratio=0.33>0.3 |
| `bb_width_pct` | 0.168 | max_ks=0.168>0.15; unstable_ratio=0.33>0.3 |

## 🎯 Recommendations for Stage 3B

⚠️ **Regime detection signal is weak.** Before proceeding:
- Try different n_components or GMM covariance type
- Add more discriminating features
- Consider hierarchical clustering instead of GMM

## 📁 Files produced

- `regimes.csv`: per-trade regime + confidence + GMM features
- `stable_features.json`: list of stable features for Stage 3B
- `stability_analysis.csv`: full feature-by-feature stability table