# Holdout Data Contract

The promotion holdout is evidence, not a tuning set.

## Required release window

The canonical forward windows are:

- `2025_H2`: 2025-07-01 through 2025-12-31 UTC
- `2026_YTD`: 2026-01-01 through the current evidence cutoff UTC

## Required row fields

Each event row must include:

- `event_time_utc`
- `year`
- `cluster_signal`
- `dominant_z_mad`
- `post_30m_usd_bps`
- `post_60m_usd_bps`
- `post_240m_usd_bps`
- `post_30m_observed_bars`
- `post_60m_observed_bars`
- `post_240m_observed_bars`

The row must represent a point-in-time event and exact-horizon outcomes. No future feature may be used to compute `dominant_z_mad`.

## Completeness rules

The holdout is complete only when each required window contains valid events and every retained event has all required outcome horizons. Missing bars, invalid timestamps, or absent outcomes are explicit data-quality failures.

A dataset ending before 2026 is not a 2026 holdout. It must be reported as incomplete rather than treated as a successful negative result.

## Frozen research parameters

- MAD threshold: `abs(dominant_z_mad) >= 1.0`
- no holdout recalibration
- no threshold search
- no post-hoc event exclusion
- no cost retuning

## Provenance

The evidence package must record the source observation file hash, market-data source/timezone mapping, generated dataset hash, runner version, and report hash. This makes a future promotion review reproducible.
