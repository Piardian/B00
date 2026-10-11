# Macro Edge Research v1

This is a research-only extension of the existing Begonya macro engine. It does not modify production regime logic, LLM prompts, deterministic execution gates, or SMC behavior.

## Purpose

Measure whether macro economic surprises contain incremental directional information for XAUUSD and EURUSD, and whether the relationship becomes stronger or weaker after observing cross-asset market repricing.

## Research flow

```text
Economic release
      ↓
Point-in-time surprise normalization
      ↓
Event clustering
      ↓
Cross-asset repricing
(DXY + optional US02Y/US10Y proxies + XAUUSD/EURUSD)
      ↓
Forward returns at exact horizons
      ↓
Gross + cost-adjusted edge statistics
      ↓
OOS validation
```

## Current design

The research layer uses expanding pre-year MAD and STD surprise scales. Simultaneous releases are represented as one event timestamp instead of multiple independent observations. Forward outcomes use the existing exact-horizon bar mapping from `calibration.event_horizon`.

Positive normalized surprise means a stronger-US-macro impulse using the existing `INDICATOR_DIRECTIONS` convention. Research-only expected asset direction is explicit:

- DXY: positive
- EURUSD: negative
- XAUUSD: negative
- US02Y: positive
- US10Y: positive

These directions are hypotheses, not production rules. They must survive out-of-sample testing before any production use.

## Example

```bash
python -m calibration.macro_edge_research \
  --timeframe M5 \
  --symbols XAUUSD EURUSD DXY \
  --years 2019 2020 2021 2022 2023 2024 2025
```

If the MT5 environment exposes usable intraday broker symbols for US02Y/US10Y, they can be added explicitly to the `--symbols` list. They are not required for the first XAUUSD/EURUSD research pass.

The output is `macro_edge_research.json` unless another output path is provided.

## Promotion rule

No research result is automatically promoted to a production gate. A candidate relationship must first pass chronological OOS validation, transaction-cost checks, robustness tests, and finally an incremental test against the existing SMC + Macro baseline.

## Canonical Multi-Asset Empirical Results (M30, 2022–2025 OOS, N=162 events)

Evaluated with exact-horizon mapping on broker MT5 historical candles:

| Asset | Horizon | Sample Count | Directional Hit Rate % | Mean Gross (bps) | Cost Assumption | Mean Net (bps) | Profit Factor (Gross) | Net Positive % |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **EURUSD** | +30m | 162 | **69.14%** | **+14.97** | 10 bps | **+4.97** | **3.86** | **53.09%** |
| | +60m | 162 | 68.52% | +14.98 | 10 bps | +4.98 | 3.43 | 52.47% |
| | +240m | 162 | 62.35% | +10.69 | 10 bps | +0.69 | 1.92 | 46.91% |
| **XAUUSD** | +30m | 162 | **67.90%** | **+19.70** | 15 bps | **+4.70** | **3.77** | **50.00%** |
| | +60m | 162 | 64.81% | +18.59 | 15 bps | +3.59 | 3.11 | 47.53% |
| | +240m | 162 | 62.35% | +14.50 | 15 bps | -0.50 | 1.67 | 46.91% |

### Multi-Asset Insights
- **XAUUSD vs EURUSD**: Gold responds with higher absolute amplitude (+19.70 bps at 30m vs +14.97 bps for EURUSD), but incurs higher spread/slippage friction (modeled at 15 bps vs 10 bps). Both assets yield comparable net edge (+4.70 bps vs +4.97 bps) at the 30-minute horizon.
- **Horizon Decay**: Forward edge decays between 60m and 240m across both assets. By +240m, gold becomes net slightly negative (-0.50 bps) after 15 bps friction, showing that macroeconomic surprise edge is front-loaded in the initial 30 to 60 minutes post-release.

