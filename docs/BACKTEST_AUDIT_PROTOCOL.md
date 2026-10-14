# Begonya 00 — Backtest Audit Protocol

This protocol separates a report audit from a strategy validation.

## Run

From the repository root:

```bash
python scripts/audit_backtest_results.py
```

The command is read-only. It does not change strategy parameters, historical data, order routing, or the live process.

## Required checks before interpreting results

1. Record the commit SHA and the exact report path.
2. Record the period, symbol universe, entry/exit model, risk percentage, spread/slippage/commission assumptions, and whether macro gating is enabled.
3. Compare gated and ungated runs only when all other inputs and execution assumptions match.
4. Treat negative net R as negative performance even if a short period has a high win rate.
5. Treat any strategy leg with zero trades as unvalidated, not as successful.
6. Re-run from raw candles with explicit no-look-ahead checks before making claims about edge. This summary audit does not validate raw data, fills, or intrabar assumptions.

## Current known coverage gap

The published 2025-10-11 to 2026-10-11 optimized report lists 0 trades for `ORB_LONDON_FOREX_ONLY`. That means the report does not validate the ORB leg. The audit script will flag zero-trade strategy components without modifying them.
