# Promotion Policy

The macro research layer may inform a production gate only after evidence has passed three independent controls: untouched holdout, execution realism, and incremental value against the existing SMC strategy.

## Frozen rule

The only admissible macro gate for this promotion candidate is:

`macro_direction == smc_direction AND abs(dominant_z_mad) >= 1.0`

No alternate threshold, learned holdout threshold, or post-hoc event subset is admissible in the promotion report.

## Holdout rule

Both `2025_H2` and `2026_YTD` must contain valid observations and complete exact-horizon outcomes. A missing window is a blocking condition, not a neutral result.

## Execution rule

Execution must be stress-tested under the pre-registered `CALM_10BP`, `NEWS_30BP`, and `NEWS_50BP` scenarios. The implementation must fail closed on OHLC ambiguity. A limit-entry improvement is not evidence unless the same fixed mechanism survives the complete holdout without retuning.

## Incremental rule

The SMC+macro subset must be evaluated from a complete historical SMC ledger. The metric comparison must be apples-to-apples on realized R and must not reuse a benchmark journal as if it were a full backtest.

## Production rule

`production_activation` remains `false` in all research artifacts. The research layer may output `REQUIRES_EXECUTION_VALIDATION`, but it must not emit or set a live trading permission.
