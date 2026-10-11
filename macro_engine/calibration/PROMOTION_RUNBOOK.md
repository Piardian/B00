# Promotion Evidence Runbook

This runbook defines the reproducible final evidence path after the 2022–2025 research phase.

## 1. Freeze

Use `abs(dominant_z_mad) >= 1.0`. Do not tune the threshold, execution delay, cost assumptions, or trade-selection rule after inspecting holdout results.

The production decision must be based on the exact artifacts used for the run. Record their Git SHAs and the report fingerprint.

## 2. Build current holdout

Run on the Windows/MT5 environment that has access to the broker's historical intraday candles:

```powershell
cd macro_engine
python -m calibration.historical_event_research --timeframe M5 --years 2025 2026 --symbol EURUSD
```

The observations source must contain the point-in-time macro releases for both windows. The generated dataset must contain complete exact-horizon outcomes for the requested horizons.

For XAUUSD, repeat with `--symbol XAUUSD`. Do not merge broker feeds with different timestamp or session conventions without recording the mapping.

## 3. Produce promotion report

```powershell
python -m calibration.promotion_runner calibration/historical_event_research.json --output calibration/promotion_report.json
```

A report is not a production pass merely because the evaluator runs. `HOLDOUT_INCOMPLETE` and `INSUFFICIENT_DATA` are explicit blocking states.

## 4. Execution stress

Populate a complete trade-spec ledger with `trade_id`, `event_time_utc`, `side`, `entry_zone`, `stop_loss`, and `take_profit`, plus the matching M5/M1 bar series. Run `compare_execution_modes()` for the fixed scenarios in `promotion_simulation.py`.

The scenarios are deliberately fixed:

- `CALM_10BP`: 10 bps spread, 2.5 bps slippage.
- `NEWS_30BP`: 30 bps spread, 5 bps slippage.
- `NEWS_50BP`: 50 bps spread, 10 bps slippage.

Same-bar stop/target ambiguity must remain excluded rather than resolved optimistically.

## 5. Incremental SMC alpha

Supply a complete historical SMC ledger containing realized R and the corresponding point-in-time macro direction and MAD surprise fields. Run `evaluate_incremental_smc_alpha()` with the frozen threshold.

The small benchmark journal is not a substitute for this ledger.

## 6. Promotion decision

Production activation remains disabled until all of the following exist in the same evidence package:

- complete 2025 H2 + 2026 holdout coverage;
- frozen-parameter holdout results;
- execution results from actual M5/M1 broker data or a validated tick model;
- complete apples-to-apples SMC baseline vs SMC+macro comparison;
- stable results across all pre-registered execution stress scenarios;
- artifact hashes and reproducible report inputs.

No research report is allowed to silently activate production behavior.
