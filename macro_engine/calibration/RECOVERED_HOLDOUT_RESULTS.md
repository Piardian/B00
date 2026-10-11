# Recovered Macro Holdout (July 2025) Out-of-Sample Evaluation Report

**Document Version:** `recovered-holdout-v1`  
**Execution Timestamp:** 2026-09-17T22:15:00 UTC  
**Scope:** Research and partial holdout sanity check only  
**Production Activation:** `false`  
**Promotion Gate Decision:** `BLOCKED_PENDING_DATA`  

---

## 1. Executive Summary & Statistical Language Notice

This document reports the deterministic out-of-sample (OOS) evaluation of 6 point-in-time (PIT) macroeconomic observations recovered for July 2025. 

> [!CAUTION]
> **Statistical Significance & Sample Size Limitation:**
> * The data represents **only 6 observations (4 unique event clusters)** spanning July 1, 2025 to July 17, 2025 (~2.5 weeks).
> * This sample size is strictly **an insufficient sample** to draw definitive econometric conclusions, demonstrate statistical proof, or confirm a production-ready edge.
> * This evaluation serves solely as **partial holdout evidence** and an empirical **sanity check** against real broker data.
> * The promotion pipeline strictly classifies 2025 H2 as `INSUFFICIENT_DATA` and keeps production activation **disabled (`false`)**.

---

## 2. Recovered Observations & Point-in-Time (PIT) Provenance Audit

All 6 recovered observations have been independently verified against official US statistical agency releases (BLS, US Census Bureau, ISM) and point-in-time web captures. Zero observations were rejected during ingestion.

| # | Date (UTC) | Indicator | Event Name | Actual | Forecast | Previous | Raw Surprise | Signed Surprise | Source & Provenance URL | PIT Verified | Status |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| 1 | 2025-07-01 14:00 | `pmi` | ISM Manufacturing PMI | 49.0 | 48.8 | 48.5 | +0.20 | +0.20 | [ISM / ForexFactory](https://www.forexfactory.com/calendar?week=jun29.2025) | Yes | **ACCEPTED** |
| 2 | 2025-07-03 12:30 | `nfp` | Non-Farm Employment Change | 147,000 | 111,000 | 144,000 | +36,000 | +36,000 | [BLS News Release](https://www.bls.gov/news.release/empsit.nr0.htm) | Yes | **ACCEPTED** |
| 3 | 2025-07-03 12:30 | `unemployment` | Unemployment Rate | 4.1% | 4.3% | 4.2% | -0.20% | +0.20% | [BLS News Release](https://www.bls.gov/news.release/empsit.nr0.htm) | Yes | **ACCEPTED** |
| 4 | 2025-07-15 12:30 | `cpi` | CPI m/m | 0.3% | 0.3% | 0.1% | 0.00% | 0.00% | [BLS CPI Summary](https://www.forexfactory.com/calendar?week=jul13.2025) | Yes | **ACCEPTED** |
| 5 | 2025-07-15 12:30 | `core_cpi` | Core CPI m/m | 0.2% | 0.3% | 0.1% | -0.10% | -0.10% | [BLS CPI Summary](https://www.forexfactory.com/calendar?week=jul13.2025) | Yes | **ACCEPTED** |
| 6 | 2025-07-17 12:30 | `retail_sales` | Retail Sales m/m | 0.6% | 0.1% | -0.9% | +0.50% | +0.50% | [US Census Bureau](https://www.forexfactory.com/calendar?week=jul13.2025) | Yes | **ACCEPTED** |

* **Total Processed Rows:** 6  
* **Accepted Rows:** 6 (100%)  
* **Rejected Rows:** 0 (0%)  

---

## 3. Frozen Calibration & Zero-Leakage Constraint

Calibration parameters were fitted strictly on canonical data **prior to 2025-07-01 00:00:00 UTC**. Zero July 2025 observations entered the fitting pool.

### Frozen Sigmas ($\text{Cutoff} < \text{2025-07-01}$):
* `pmi`: $\sigma_{MAD} = 1.6309$ | $\sigma_{STD} = 1.6562$
* `nfp`: $\sigma_{MAD} = 86,732.10$ | $\sigma_{STD} = 996,871.26$
* `unemployment`: $\sigma_{MAD} = 0.1483$ | $\sigma_{STD} = 0.6298$
* `cpi`: $\sigma_{MAD} = 0.1483$ | $\sigma_{STD} = 0.1339$
* `core_cpi`: $\sigma_{MAD} = 0.1483$ | $\sigma_{STD} = 0.1361$
* `retail_sales`: $\sigma_{MAD} = 0.4448$ | $\sigma_{STD} = 1.3171$
* `gdp`: $\sigma_{MAD} = 0.5930$ | $\sigma_{STD} = 0.8794$

---

## 4. Event Clustering & Frozen $|Z_{MAD}| \ge 1.0$ Filter Decision

Observations occurring at identical release timestamps form a unified event cluster:

| Cluster Date (UTC) | Indicators in Cluster | Cluster Signal | Coherence | Dominant Indicator | Dominant $Z_{MAD}$ | Dominant $Z_{STD}$ | Filter Decision ($|Z_{MAD}| \ge 1.0$) |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| 2025-07-01 14:00 | `pmi` | +1 (USD Bullish) | 1.00 | `pmi` | $+0.12$ | $+0.12$ | **FILTERED OUT (Gated)** |
| 2025-07-03 12:30 | `nfp` + `unemployment` | +1 (USD Bullish) | 1.00 | `unemployment` | $+1.35$ | $+0.32$ | **ACTIONABLE (Passes Filter)** |
| 2025-07-15 12:30 | `cpi` + `core_cpi` | -1 (USD Bearish) | 0.50 | `core_cpi` | $-0.67$ | $-0.73$ | **FILTERED OUT (Gated)** |
| 2025-07-17 12:30 | `retail_sales` | +1 (USD Bullish) | 1.00 | `retail_sales` | $+1.12$ | $+0.38$ | **ACTIONABLE (Passes Filter)** |

* **Total Event Clusters:** 4  
* **Actionable Clusters ($|Z_{MAD}| \ge 1.0$):** 2 (50.0%)  
* **Filtered Out Clusters ($|Z_{MAD}| < 1.0$):** 2 (50.0%)  

---

## 5. Exact-Horizon Market Response (EURUSD & XAUUSD)

Outcomes are computed from local broker MT5 M30 bars (`MetaQuotes-Demo`), converted from server timezone (`Europe/Helsinki`) to UTC. $p_0$ is the OPEN price of the event release bar. Exact horizon $H$ is the CLOSE price of the bar opening at $t_0 + H - \text{interval}$.

### A) EURUSD Exact Horizon (USD-Strength Return in bps)

$$\text{USD Return (bps)} = \frac{p_0 - \text{Close}_H}{p_0} \times 10,000$$

| Event Date | Cluster | Signal | $|Z| \ge 1.0$ | $p_0$ | +30m Return | +30m MFE / MAE | +60m Return | +240m Return | Gross Directional Hit (+30m) |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| 2025-07-01 14:00 | `pmi` | +1 | Filtered | 1.18014 | $+7.97\text{ bps}$ | $+15.76\text{ / } -0.25$ | $+18.73\text{ bps}$ | $+16.18\text{ bps}$ | Hit (Filtered) |
| 2025-07-03 12:30 | `nfp` + `unemp` | +1 | **Pass** | 1.17859 | **$+40.73\text{ bps}$** | $+58.63\text{ / } 0.00$ | $+18.92\text{ bps}$ | $+34.62\text{ bps}$ | **Hit (Actionable)** |
| 2025-07-15 12:30 | `cpi` + `core_cpi` | -1 | Filtered | 1.16650 | $-10.80\text{ bps}$ | $+2.74\text{ / } -21.86$ | $-1.46\text{ bps}$ | $+53.24\text{ bps}$ | Miss (Filtered) |
| 2025-07-17 12:30 | `retail_sales` | +1 | **Pass** | 1.15754 | **$-9.76\text{ bps}$** | $+16.50\text{ / } -14.43$ | $-11.23\text{ bps}$ | $-21.68\text{ bps}$ | Miss (Actionable) |

### B) XAUUSD (Gold) Exact Horizon (USD-Strength Return in bps)

| Event Date | Cluster | Signal | $|Z| \ge 1.0$ | $p_0$ | +30m Return | +30m MFE / MAE | +60m Return | +240m Return | Gross Directional Hit (+30m) |
| :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| 2025-07-01 14:00 | `pmi` | +1 | Filtered | 3350.80 | $-2.36\text{ bps}$ | $+10.03\text{ / } -10.65$ | $+15.31\text{ bps}$ | $+33.04\text{ bps}$ | Miss (Filtered) |
| 2025-07-03 12:30 | `nfp` + `unemp` | +1 | **Pass** | 3349.66 | **$+75.20\text{ bps}$** | $+113.35\text{ / } -0.03$ | $+51.74\text{ bps}$ | $+63.11\text{ bps}$ | **Hit (Actionable)** |
| 2025-07-15 12:30 | `cpi` + `core_cpi` | -1 | Filtered | 3354.46 | $+16.84\text{ bps}$ | $+23.97\text{ / } -16.81$ | $+40.45\text{ bps}$ | $+85.71\text{ bps}$ | Hit (Filtered) |
| 2025-07-17 12:30 | `retail_sales` | +1 | **Pass** | 3324.32 | **$+33.84\text{ bps}$** | $+43.38\text{ / } -7.64$ | $+20.33\text{ bps}$ | $-43.71\text{ bps}$ | **Hit (Actionable)** |

---

## 6. Simulated Cost-Adjusted Performance (15 bps Cost)

Simulated performance on EURUSD at 15.0 bps transaction cost:

| Strategy Slice | Trade Count | Hit Rate (%) | Mean Net Return | Profit Factor | Max Drawdown | Trade Sharpe |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: |
| **Unfiltered Baseline** | 4 | 25.0% | $-2.57\text{ bps}$ | 0.71 | $28.96\text{ bps}$ | -0.28 |
| **Frozen MAD ($|Z_{MAD}| \ge 1.0$)** | 2 | 50.0% | **$+0.48\text{ bps}$** | **1.04** | $24.76\text{ bps}$ | +0.03 |
| **Filtered Pool ($|Z_{MAD}| < 1.0$)** | 2 | 0.0% | $-5.62\text{ bps}$ | 0.00 | $11.23\text{ bps}$ | -5.60 |

### Empirical Observation:
* The 2 events eliminated by the frozen MAD filter (`pmi` and `cpi`) generated net negative returns after 15 bps cost ($-7.03\text{ bps}$ and $-4.20\text{ bps}$ net).
* The 2 actionable events produced 1 substantial win (NFP: $+25.73\text{ bps}$ net) and 1 loss (Retail Sales: $-24.76\text{ bps}$ net), yielding a positive net mean ($+0.48\text{ bps}$).
* However, with $N = 2$, this difference cannot be considered statistically significant; it constitutes **partial holdout evidence** and an exploratory **sanity check**.

---

## 7. Promotion Readiness Runner Integration

The canonical promotion runner (`calibration.run_promotion_readiness`) has integrated this dataset via `calibration.holdout_macro_adapter`. 

### Current Promotion Checks:
* `threshold_frozen`: **TRUE** (1.0)
* `no_holdout_fitting`: **TRUE**
* `holdout_2025_h2_populated`: **FALSE** (`status: INSUFFICIENT_DATA` — 4 clusters vs 15 required)
* `holdout_2026_ytd_populated`: **FALSE** (`status: INSUFFICIENT_DATA` — 0 clusters)
* `smc_ledger_available`: **FALSE** (missing historical execution ledger)
* `execution_data_available`: **FALSE** (missing M1/M5 bar cache)
* **Overall Promotion Status:** `BLOCKED_PENDING_DATA`
* **Production Activation:** `false`
