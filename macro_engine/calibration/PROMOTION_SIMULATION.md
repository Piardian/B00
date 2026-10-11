# Promotion Simulation Layer

This layer is research-only. It does not change production gates or execution behavior.

## Frozen holdout

The promotion threshold is permanently frozen at `abs(dominant_z_mad) >= 1.0`. The holdout evaluator refuses any other threshold and never recalibrates on holdout data.

The intended holdout windows are:

- 2025 H2: 2025-07-01 through 2025-12-31 UTC
- 2026 YTD: 2026-01-01 through the current cutoff UTC

The report distinguishes `PASS_DATA` from `INSUFFICIENT_DATA`. Missing post-training coverage is never treated as a passing result.

## Execution stress

`simulate_trade_path()` supports two fixed execution modes:

- `T0_MARKET`: enter on the eligible bar open with adverse half-spread plus slippage.
- `T5_RETEST_LIMIT`: wait one bar, then place a non-optimizing limit order at the midpoint of the SMC entry zone for up to a fixed number of bars.

The default stress scenarios are fixed at 10, 30, and 50 bps spread with predetermined slippage assumptions. These are scenario assumptions, not claims about realized broker spread.

OHLC ambiguity is fail-closed. When both stop and target are touched inside the same bar, the result is classified as `AMBIGUOUS` and excluded from performance PnL rather than resolved in favor of the strategy.

## Incremental SMC alpha

`evaluate_incremental_smc_alpha()` compares an external SMC trade ledger with and without the frozen macro gate:

`macro_direction == smc_direction AND abs(Z_MAD) >= 1.0`

It reports trade count, hit rate, mean R, profit factor, maximum drawdown, and an unannualized per-trade Sharpe statistic. The latter is a diagnostic proxy and is not an annualized portfolio Sharpe ratio.

The incremental test intentionally requires a populated SMC trade ledger containing realized R outcomes and macro fields. The small benchmark journal is not sufficient evidence for production promotion because it is not a complete historical strategy backtest.

## Promotion contract

No production promotion is emitted by this module. A production candidate needs:

1. Complete 2025 H2 and 2026 holdout coverage.
2. Execution results using actual M5/M1 broker data or a validated tick-level execution model.
3. A complete SMC historical trade ledger for an apples-to-apples baseline and SMC+macro comparison.
4. Stable results across pre-registered stress scenarios without threshold retuning.
