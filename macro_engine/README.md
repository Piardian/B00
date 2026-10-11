# Macro Multi-AGI Army: Institutional Macro Regime & Risk Engine

Macro regime and risk engine combining deterministic market/FRED metrics with LLM-based analysis. Deterministic metrics are authoritative for execution gates; LLM outputs are advisory explanations only.

## Architecture & Workflow

1. **Ingestion (`ingestion/`)**
   - Market data from the configured MT5/Yahoo path with fail-closed validation.
   - FRED observations with explicit current/prior observation dates and an explicit replay vintage end date.
   - Economic activity, inflation, labor and Treasury-curve observations are ingested as a separate required provider-backed panel.
   - High-impact economic calendar with fail-closed availability semantics.

2. **Deterministic preprocessing (`preprocessing/`)**
   - Yield-curve, real-yield, liquidity, credit, volatility and cross-asset metrics.
   - Separate deterministic economic dimensions: inflation, labor, growth, PMI/activity, policy and rate-curve state.
   - Explicit replay clock and explicit previous regime state.
   - Input range/anomaly checks, freshness checks and provenance metadata.
   - Return-based cross-asset correlation rather than price-level correlation.
   - The economic panel does not collapse correlated observations into an arbitrary composite score.
   - Policy expectations are kept separate from economic state: DFF/SOFR, front 30-Day Fed Funds futures, an optional multi-contract Fed Funds futures curve, and an optional provider-supplied USD OIS curve.

3. **LLM analysis (`agents/`)**
   - Specialist and strategist models consume deterministic metrics.
   - Structured LLM output remains advisory. It does not authorize execution.

4. **Execution gate (`gateways/`)**
   - Gate precedence is deterministic: EVENT_FREEZE > SYSTEMIC_STRESS > BASE_BIAS.
   - Execution bridge accepts only `deterministic_metrics_only` gates and rejects stale/untrusted gate files.
   - Gate publication remains atomic so downstream execution never reads a partially written JSON file.

5. **Calibration and replay (`calibration/`, `tests/`)**
   - Surprise calibration uses provider-backed actual/consensus observations with provenance and point-in-time flags.
   - FRED replay requests are constrained to the replay vintage date to reduce revision leakage.
   - Calibration is split chronologically into calibration, validation and out-of-sample partitions.
   - Existing crisis fixtures are synthetic rule-execution fixtures, not provider-backed historical performance evidence.
   - No economic edge is claimed until a real historical dataset is loaded and evaluated out-of-sample.

## Economic Regime Panel

The extended deterministic panel adds four inflation measures (`CPI`, `core CPI`, `PCE`, `core PCE`), labor indicators (`PAYEMS`, `UNRATE`, average hourly earnings, initial claims), real-economy indicators (`real GDP q/q SAAR`, industrial production, retail sales), the Treasury curve (`3M`, `2Y`, `5Y`, `10Y`, `30Y`, `2s10s`, `3m10y`), and separate PMI/activity measures.

For manufacturing, the feed uses the FRED `NAPM` series. For services, the feed uses the FRED `NMFBAI` Non-Manufacturing Business Activity Index as a services activity proxy. Begonya does **not** fabricate a headline Services PMI from that sub-index. Manufacturing and services are reported separately and combined only into broad labels such as `BROAD_EXPANSION`, `BROAD_CONTRACTION`, or `MIXED`.

The panel reports current levels, four-week changes, source observation ages and point-in-time vintage metadata. When a required economic observation is missing or stale, the economic narrative is withheld rather than replaced with a synthetic baseline.

## Policy Expectations

`DFF` is the effective federal funds rate observation. `SOFR` is consumed as a money-market anchor and is not treated as a forward OIS curve.

The optional front 30-Day Fed Funds futures input is converted deterministically as `100 - price`. A single front contract describes the market-implied average effective federal funds rate for its delivery month; it is not a full meeting-probability curve.

A multi-contract `FED_FUNDS_FUTURES_CURVE` can be supplied to preserve the market-implied policy path across delivery months. Begonya reports those contract-implied rates without inventing meeting probabilities.

A provider-backed `USD_OIS_CURVE` can also be supplied. Begonya passes that curve through with provenance and does not synthesize OIS rates from Treasury yields, SOFR, or the Fed Funds futures curve.

The front futures and full curves are optional inputs. The core macro pipeline does not fail solely because those optional market-implied policy feeds are unavailable.

## Setup & Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` and provide the required API keys:
```bash
cp .env.example .env
```

### 3. Run Pipeline
```bash
python main.py
```

### 4. Run Tests
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

### 5. Collect Historical Surprise Observations
Trading Economics historical calendar data is the configured provider-backed source for calibration. Its calendar API provides historical actual values and consensus/forecast fields, including point-in-time data for backtesting.

Set `TRADING_ECONOMICS_API_KEY`, then run:
```bash
python -m calibration.collect_surprises --start 2015-01-01 --end 2025-12-31
```

The collector writes only rows containing numeric `actual` and `forecast` values and stores provider provenance, source URL, event timestamp and the point-in-time flag. It does not silently substitute the provider's proprietary `TEForecast` for the consensus `Forecast` field.

### 6. Fit Surprise Sigmas
Choose chronological cutoffs so the calibration period precedes validation, and validation precedes out-of-sample data:
```bash
python -m calibration.fit_sigmas \
  --calibration-end 2020-12-31 \
  --validation-end 2023-12-31 \
  --min-observations 30 \
  --required-indicator cpi \
  --required-indicator core_cpi \
  --required-indicator nfp \
  --required-indicator unemployment \
  --required-indicator pmi \
  --required-indicator gdp \
  --required-indicator retail_sales
```

The fitter refuses malformed rows, non-PIT rows, non-Trading-Economics rows, insufficient sample sizes, and missing empirical sigmas. The resulting JSON profile can be loaded into `MacroMetricsCalculator(surprise_sigmas=...)`; the built-in values remain explicitly labeled as uncalibrated compatibility defaults until such a profile is supplied.

The checked-in CSV is intentionally empty until provider-backed data is collected; no fabricated observations are committed.
