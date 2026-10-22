# Stage 2 — Out-of-Sample Validation

**Generated**: 2026-10-20 00:52 UTC

## 🎯 Executive Summary

**Baseline (no filter)**
- Train: n=4655, Sharpe=1.682, WinRate=11.6%
- Test:  n=1995, Sharpe=0.943, WinRate=10.5%

**🏆 Best Single Rule (by benefit/cost): `R2`**
- Catches **131** A (11.6% of test A)
- Kills **8** D (3.8% of test D)
- Precision-A: **66.2%** (train was 98.7%)
- **Sharpe: 0.943 → 1.196** (+27%)
- Benefit/cost ratio: **1.6x**

**🏆 Best Combination: `R1+R2+R3+R4+R5+R6`**
- Catches **358** A (31.8% of test A)
- Kills **38** D (18.2% of test D)
- **Sharpe: 0.943 → 1.460** (+55%)
- Remaining trades: 1436
- Benefit/cost ratio: **1.1x**

## 📊 Covariate Shift (Train vs Test)

**⚠️ 11 features show significant distribution shift** (KS test p<0.01). Rules depending on these features may generalize poorly.

| Feature | Train mean | Test mean | KS p-value | Drift |
|---------|-----------|-----------|-----------|-------|
| `E_therm` | 0.0174 | 0.0160 | 7.85e-25 | SIGNIFICANT |
| `T_info` | 4.4908 | 4.1921 | 1.04e-24 | SIGNIFICANT |
| `btc_ema_slope` | -0.0047 | 0.0159 | 1.01e-75 | SIGNIFICANT |
| `btc_ret_24` | -0.0038 | 0.0255 | 3.54e-59 | SIGNIFICANT |
| `btc_ret_6` | -0.0017 | 0.0094 | 5.72e-36 | SIGNIFICANT |
| `dist_high_100` | -0.1517 | -0.0912 | 4.65e-105 | SIGNIFICANT |
| `dynamic_risk` | 0.0228 | 0.0262 | 2.98e-321 | SIGNIFICANT |
| `ret_12` | 0.0153 | 0.0463 | 3.96e-23 | SIGNIFICANT |
| `ret_24` | 0.0176 | 0.0590 | 5.98e-18 | SIGNIFICANT |
| `ret_3` | 0.0092 | 0.0180 | 1.23e-17 | SIGNIFICANT |
| `rr_design` | 10.8807 | 33.8218 | 8.40e-24 | SIGNIFICANT |
| `score` | 4.8643 | 4.8264 | 1.30e-01 | OK |

## 🎯 Per-Rule Out-of-Sample Results

| Rule | Blocked | Caught A | Killed D | Catch% | Kill% | Precision-A | Train-P-A | Drop | Sharpe | Δ% | B/C |
|------|---------|----------|----------|--------|-------|------------|-----------|------|--------|-----|-----|
| R1 | 273 | 171 | 20 | 15.2% | 9.6% | 62.6% | 92.2% | +29.6pp | 1.119 | +19% | 1.0 |
| R2 | 198 | 131 | 8 | 11.6% | 3.8% | 66.2% | 98.7% | +32.5pp | 1.196 | +27% | 1.6 |
| R3 | 50 | 30 | 5 | 2.7% | 2.4% | 60.0% | 96.9% | +36.9pp | 0.946 | +0% | 0.8 |
| R4 | 0 | — | — | — | — | — | — | — | — | — | — |
| R5 | 38 | 26 | 5 | 2.3% | 2.4% | 68.4% | 98.4% | +29.9pp | 0.942 | -0% | 0.8 |
| R6 | 0 | — | — | — | — | — | — | — | — | — | — |

## 🏆 Top Combinations (by Sharpe)

| Combo | Rules | Blocked | Caught A | Killed D | Sharpe | Δ% | Remaining | B/C |
|-------|-------|---------|----------|----------|--------|-----|-----------|-----|
| R1+R2+R3+R4+R5+R6 | 6 | 559 | 358 | 38 | 1.460 | +55% | 1436 | 1.1 |
| R1+R2+R3+R5+R6 | 5 | 559 | 358 | 38 | 1.460 | +55% | 1436 | 1.1 |
| R1+R2+R3+R4+R5 | 5 | 559 | 358 | 38 | 1.460 | +55% | 1436 | 1.1 |
| R1+R2+R3+R5 | 4 | 559 | 358 | 38 | 1.460 | +55% | 1436 | 1.1 |
| R1+R2+R3 | 3 | 521 | 332 | 33 | 1.447 | +54% | 1474 | 1.2 |
| R1+R2+R3+R4 | 4 | 521 | 332 | 33 | 1.447 | +54% | 1474 | 1.2 |
| R1+R2+R3+R4+R6 | 5 | 521 | 332 | 33 | 1.447 | +54% | 1474 | 1.2 |
| R1+R2+R3+R6 | 4 | 521 | 332 | 33 | 1.447 | +54% | 1474 | 1.2 |
| R1+R2+R4+R5 | 4 | 509 | 328 | 33 | 1.439 | +53% | 1486 | 1.2 |
| R1+R2+R5 | 3 | 509 | 328 | 33 | 1.439 | +53% | 1486 | 1.2 |

## 📈 Pareto Frontier (Sharpe vs Throughput)

Optimal trade-offs between Sharpe improvement and trade count:

| Rules | Remaining n | Sharpe | Δ% | Blocked | Kill% | B/C |
|-------|-------------|--------|-----|---------|-------|-----|
| R5 | 1957 | 0.942 | -0% | 38 | 2.4% | 0.8 |
| R3+R4 | 1945 | 0.946 | +0% | 50 | 2.4% | 0.8 |
| R2+R6 | 1797 | 1.196 | +27% | 198 | 3.8% | 1.6 |
| R2+R5+R6 | 1759 | 1.200 | +27% | 236 | 6.2% | 1.4 |
| R2+R3+R4 | 1747 | 1.206 | +28% | 248 | 6.2% | 1.4 |
| R2+R3+R4+R5 | 1709 | 1.211 | +29% | 286 | 8.6% | 1.2 |
| R1+R2 | 1524 | 1.428 | +51% | 471 | 13.4% | 1.2 |
| R1+R2+R5 | 1486 | 1.439 | +53% | 509 | 15.8% | 1.2 |
| R1+R2+R3+R6 | 1474 | 1.447 | +54% | 521 | 15.8% | 1.2 |
| R1+R2+R3+R5+R6 | 1436 | 1.460 | +55% | 559 | 18.2% | 1.1 |

## 🎯 Recommendations for Stage 3

3. **⚠️ Covariate shift detected** in `E_therm`, `T_info`, `btc_ema_slope`, `btc_ret_24`, `btc_ret_6`, `dist_high_100`, `dynamic_risk`, `ret_12`, `ret_24`, `ret_3`, `rr_design`. Consider re-training on more recent data or excluding rules depending on these features.
