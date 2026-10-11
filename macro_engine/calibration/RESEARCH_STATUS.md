# Macro Event Research Status

## Canonical path

Use `market_response_validation_v3.py` and `historical_event_research.py` for new event-response research.

`event_horizon.py` defines the bar mapping used by both: for bar interval `I` and requested horizon `H`, the bar whose **close** represents exactly `H` minutes after the release opens at `event_time + H - I`.

Example on M30:

- `+30m` = close of the release bar itself.
- `+60m` = close of the next M30 bar.
- `+240m` = close of the bar opening 210 minutes after the release.

## Stale results

Earlier `market_response_validation_v2` and `falsification_stress_test` outputs used the bar at `event_time + H` and then its close. That makes the reported horizon one full bar later than its label. Those historical result JSON files must therefore be treated as **stale research artifacts** and must not be used as evidence for production parameter choices.

The historical findings remain useful as hypotheses, but all IC, hit-rate, and cost figures must be regenerated with the exact-horizon path before being re-used.

## Research workflow

1. Build the historical event dataset from aligned macro observations and MT5 bars.
2. Keep pre-event features separate from forward outcomes.
3. Cluster simultaneous releases by reconstructed event timestamp.
4. Fit MAD/STD strictly before each validation year.
5. Run the pre-registered filter lab on future years only.
6. Compare filters against the `cluster_signal != 0` baseline using gross and net metrics.
7. Do not promote a filter to production without an untouched OOS test and execution-cost validation.

No automatic filter activation is part of this research layer.

## Canonical Exact-Horizon Empirical Results (2022–2025 OOS)

Generated on live MT5 bars (EURUSD M30, Europe/Helsinki converted to UTC) and `surprise_observations.csv`:

### 1. Market Response Validation v3 (EURUSD M30, N=288)

| Horizon | MAD Rank IC | STD Rank IC | Δ (MAD - STD) | MAD Hit Rate % | Mean Signed Return (bps) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **+30m** | **+0.4602** | +0.4532 | +0.0070 | **60.42%** | **+16.09 bps** |
| **+60m** | **+0.4177** | +0.4190 | -0.0013 | 58.33% | +16.21 bps |
| **+240m**| **+0.2139** | +0.2382 | -0.0242 | 54.86% | +12.70 bps |

### 2. Walk-Forward Filter Lab (EURUSD M30, 2022–2025 OOS, N=145 trades)

| Strategy / Filter | Cost (bps) | Trades (N) | Hit Rate % | Mean Gross (bps) | Mean Net (bps) | Profit Factor | Max DD (bps) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline** (`signal != 0`) | 0 bps | 145 | 68.28% | +15.42 | +15.42 | 4.07 | 77.5 |
| | 10 bps | 145 | 53.10% | +15.42 | +5.42 | 1.60 | 225.0 |
| | 15 bps | 145 | 46.90% | +15.42 | **+0.42** | 1.04 | 385.3 |
| **MAD Actionable** (\|Z\| ≥ 1.0) | 0 bps | 50 | **80.00%** | **+28.89** | **+28.89** | **9.70** | **53.5** |
| | 10 bps | 50 | **68.00%** | **+28.89** | **+18.89** | **4.27** | **75.7** |
| | 15 bps | 50 | **62.00%** | **+28.89** | **+13.89** | **2.84** | **102.9** |
| **Coherent & MAD** | 15 bps | 47 | 61.70% | +29.23 | +14.23 | 2.78 | 102.9 |
| **Volatility Not Extreme** | 15 bps | 90 | 34.44% | +6.44 | **-8.56** | **0.29** | 770.8 |

### Key Takeaways
1. **Filter Efficacy**: `mad_actionable` (|Z| ≥ 1.0) filters out 95 noisy/marginal trades. In doing so, it **eliminates 52 losing trades at 10 bps and 58 losing trades at 15 bps** (which averaged -6.67 bps loss per trade in the discarded pool).
2. **Cost Survival**: At realistic news execution costs (15 bps spread + slippage), the unguided Baseline collapses to breakeven (+0.42 bps net, PF 1.04, Max DD 385 bps), whereas `mad_actionable` retains an edge (+13.89 bps net, PF 2.84, Max DD 102.9 bps).
3. **Harmful Filters**: Filtering out high historical volatility (`volatility_not_extreme`) actively destroys edge (net drops to -8.56 bps, PF 0.29). High volatility events are necessary to provide the impulse amplitude that clears transaction spreads.

