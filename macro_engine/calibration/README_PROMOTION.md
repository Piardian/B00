# Promotion Evidence Layer

The promotion layer is intentionally separate from production execution.

Use `promotion_simulation.py` for the frozen holdout, execution-stress, and incremental SMC comparison primitives.

Use `promotion_runner.py` to build one auditable evidence report and to block promotion when holdout or SMC inputs are incomplete.

Use `promote_main.py` as the deterministic programmatic entrypoint.

The canonical requirements are documented in `PROMOTION_POLICY.md`, `PROMOTION_RUNBOOK.md`, and `HOLDOUT_DATA_CONTRACT.md`.
