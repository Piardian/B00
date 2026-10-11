# Promotion Readiness Snapshot

As of the current repository state, the promotion framework is implemented and CI-enforced, but production activation remains blocked by missing empirical evidence inputs.

## Current state

- Frozen MAD threshold: `|Z_MAD| >= 1.0`
- Holdout windows: `2025_H2`, `2026_YTD`
- Execution stress: `CALM_10BP`, `NEWS_30BP`, `NEWS_50BP`
- SMC incremental comparison: implemented, complete ledger required
- production activation: `false`

## Blocking evidence

The repository's canonical macro observation dataset currently ends in the 2025 release history used by the existing research package. It therefore cannot honestly be treated as a complete 2026 holdout until new 2026 point-in-time releases and matching broker intraday outcomes are materialized.

The existing benchmark journal is also not a substitute for a complete historical SMC trade ledger.

The correct next data operation is to materialize the 2025 H2 + 2026 holdout with matching broker M5/M1 data, then run `promotion_runner.py` and the execution-stress simulation without changing frozen parameters.
