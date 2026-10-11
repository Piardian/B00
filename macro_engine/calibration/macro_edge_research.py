"""Research-only macro edge layer built on the existing event/replay infrastructure.

This module is intentionally additive. It does not change production macro gates,
LLM prompts, regime logic, or execution behavior.

Core idea:
    economic surprise -> cross-asset repricing -> forward asset return

The dataset keeps pre-release information separate from post-release outcomes and
clusters simultaneous releases so one market move is not counted as multiple
independent events.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Mapping, Optional, Sequence

from calibration.event_horizon import target_bar_open
from calibration.market_response_validation_v2 import fetch_mt5_bars, parse_observation_event_utc
from core.deterministic_controls import INDICATOR_DIRECTIONS, fit_surprise_sigmas

UTC = dt.timezone.utc
DEFAULT_HORIZONS = (5, 15, 30, 60, 240)
SUPPORTED_TIMEFRAMES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60}

# Positive normalized macro surprise means "stronger USD macro impulse" because the
# existing INDICATOR_DIRECTIONS already normalizes unemployment and similar fields.
ASSET_EXPECTED_DIRECTION = {
    "DXY": 1.0,
    "EURUSD": -1.0,
    "XAUUSD": -1.0,
    "US02Y": 1.0,
    "US10Y": 1.0,
}

DEFAULT_COST_BPS = {
    "EURUSD": 10.0,
    "XAUUSD": 15.0,
}


class MacroEdgeResearchError(RuntimeError):
    """Research dataset cannot be constructed consistently."""


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _load_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows


def _cluster_rows(rows: Sequence[Mapping[str, Any]]) -> List[List[Mapping[str, Any]]]:
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        event_time = parse_observation_event_utc(row)
        groups.setdefault(event_time.isoformat(), []).append(row)
    return [groups[key] for key in sorted(groups)]


def _event_features(
    group: Sequence[Mapping[str, Any]],
    mad_sigmas: Mapping[str, float],
    std_sigmas: Mapping[str, float],
) -> Optional[Dict[str, Any]]:
    z_mad: List[float] = []
    z_std: List[float] = []
    normalized_components: List[Dict[str, Any]] = []

    for row in group:
        kind = str(row.get("indicator_type", "")).strip().lower()
        if kind not in mad_sigmas or kind not in std_sigmas:
            continue
        try:
            actual = float(row["actual"])
            forecast = float(row["forecast"])
        except (KeyError, TypeError, ValueError):
            continue
        raw = (actual - forecast) * INDICATOR_DIRECTIONS.get(kind, 1.0)
        mad = raw / float(mad_sigmas[kind])
        std = raw / float(std_sigmas[kind])
        if not _finite(mad) or not _finite(std):
            continue
        z_mad.append(mad)
        z_std.append(std)
        normalized_components.append(
            {
                "indicator": kind,
                "raw_usd_surprise": raw,
                "z_mad": mad,
                "z_std": std,
            }
        )

    if not z_mad:
        return None

    mean_mad = mean(z_mad)
    sign_values = [_sign(z) for z in z_mad if z != 0]
    coherence = abs(mean(sign_values)) if sign_values else 0.0
    signal = _sign(mean_mad)
    dominant_idx = max(range(len(z_mad)), key=lambda idx: abs(z_mad[idx]))

    event_time = parse_observation_event_utc(group[0])
    return {
        "event_timestamp_utc": event_time.isoformat(),
        "year": event_time.year,
        "cluster_size": len(group),
        "indicators": sorted({str(row.get("indicator_type", "")).strip().lower() for row in group}),
        "cluster_signal_usd": signal,
        "cluster_coherence": round(coherence, 4),
        "mean_z_mad": round(mean_mad, 6),
        "mean_z_std": round(mean(z_std), 6),
        "max_abs_z_mad": round(max(abs(value) for value in z_mad), 6),
        "dominant_z_mad": round(z_mad[dominant_idx], 6),
        "components": normalized_components,
    }


def _event_bar_map(
    symbol: str,
    timeframe: str,
    count: int,
) -> Dict[dt.datetime, Dict[str, float]]:
    bars = fetch_mt5_bars(symbol=symbol, timeframe=timeframe, count=count)
    if not bars:
        raise MacroEdgeResearchError(
            f"MT5 bars unavailable for {symbol}; run research on the Windows/MT5 environment."
        )
    return bars


def _asset_price_at_horizon(
    bars: Mapping[dt.datetime, Mapping[str, float]],
    event_time: dt.datetime,
    timeframe_minutes: int,
    horizon_minutes: int,
) -> Optional[float]:
    target = target_bar_open(event_time, timeframe_minutes, horizon_minutes)
    row = bars.get(target)
    if row is None:
        return None
    close = float(row["close"])
    return close if _finite(close) and close > 0 else None


def _base_open(
    bars: Mapping[dt.datetime, Mapping[str, float]],
    event_time: dt.datetime,
) -> Optional[float]:
    row = bars.get(event_time)
    if row is None:
        return None
    value = float(row["open"])
    return value if _finite(value) and value > 0 else None


def _return_bps(base: float, future: float) -> float:
    return (future / base - 1.0) * 10_000.0


def _cross_asset_repricing(
    event_time: dt.datetime,
    timeframe_minutes: int,
    horizon: int,
    symbol_bars: Mapping[str, Mapping[dt.datetime, Mapping[str, float]]],
) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    for symbol, bars in symbol_bars.items():
        base = _base_open(bars, event_time)
        future = _asset_price_at_horizon(bars, event_time, timeframe_minutes, horizon)
        if base is None or future is None:
            out[symbol] = None
        else:
            out[symbol] = round(_return_bps(base, future), 6)
    return out


def build_macro_edge_dataset(
    observations_path: Path,
    symbol_bars: Mapping[str, Mapping[dt.datetime, Mapping[str, float]]],
    *,
    timeframe_minutes: int,
    years: Sequence[int] = tuple(range(2019, 2026)),
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    min_observations: int = 15,
) -> Dict[str, Any]:
    """Build a leakage-aware event-level cross-asset research dataset."""
    if timeframe_minutes <= 0:
        raise ValueError("timeframe_minutes must be > 0")
    normalized_horizons = tuple(sorted({int(h) for h in horizons if int(h) > 0 and int(h) % timeframe_minutes == 0}))
    if not normalized_horizons:
        raise ValueError("No usable horizons for the selected timeframe")

    rows = _load_rows(observations_path)
    years_set = tuple(sorted({int(year) for year in years}))
    dataset: List[Dict[str, Any]] = []
    diagnostics: Dict[str, Any] = {
        "observation_rows_total": len(rows),
        "years": list(years_set),
        "event_clusters_total": 0,
        "event_clusters_matched": 0,
        "missing_event_bar": 0,
        "missing_outcome": 0,
        "invalid_observation": 0,
        "timeframe_minutes": timeframe_minutes,
    }

    for year in years_set:
        history = [r for r in rows if _safe_year(r) < year]
        mad_sigmas = fit_surprise_sigmas(history, min_observations=min_observations, method="mad")
        std_sigmas = fit_surprise_sigmas(history, min_observations=min_observations, method="std")
        current = [r for r in rows if _safe_year(r) == year]
        clusters = _cluster_rows(current)
        diagnostics["event_clusters_total"] += len(clusters)

        for group in clusters:
            event_time = parse_observation_event_utc(group[0])
            event_info = _event_features(group, mad_sigmas, std_sigmas)
            if event_info is None:
                diagnostics["invalid_observation"] += 1
                continue

            required_symbols = list(symbol_bars.keys())
            base_prices = {
                symbol: _base_open(symbol_bars[symbol], event_time)
                for symbol in required_symbols
            }
            if any(value is None for value in base_prices.values()):
                diagnostics["missing_event_bar"] += 1
                continue

            record: Dict[str, Any] = {
                **event_info,
                "assets": required_symbols,
                "base_prices": base_prices,
                "repricing": {},
            }

            complete = True
            for horizon in normalized_horizons:
                repricing = _cross_asset_repricing(
                    event_time,
                    timeframe_minutes,
                    horizon,
                    symbol_bars,
                )
                if any(repricing[symbol] is None for symbol in required_symbols):
                    diagnostics["missing_outcome"] += 1
                    complete = False
                    break

                record["repricing"][str(horizon)] = repricing

                for symbol in required_symbols:
                    value = float(repricing[symbol])
                    record[f"{symbol}_return_{horizon}m_bps"] = value
                    expected_direction = ASSET_EXPECTED_DIRECTION.get(symbol)
                    if event_info["cluster_signal_usd"] != 0 and expected_direction is not None:
                        expected_sign = event_info["cluster_signal_usd"] * expected_direction
                        record[f"{symbol}_directional_hit_{horizon}m"] = bool(
                            expected_sign * value > 0
                        )

            if not complete:
                continue

            diagnostics["event_clusters_matched"] += 1
            dataset.append(record)

    dataset.sort(key=lambda row: str(row["event_timestamp_utc"]))
    diagnostics["dataset_rows"] = len(dataset)
    diagnostics["coverage_pct"] = round(
        diagnostics["event_clusters_matched"] / diagnostics["event_clusters_total"] * 100.0,
        2,
    ) if diagnostics["event_clusters_total"] else 0.0

    return {
        "metadata": {
            "methodology_version": "macro-edge-research-v1",
            "event_unit": "unique scheduled release timestamp",
            "surprise_normalization": "expanding pre-year MAD and STD",
            "point_in_time_rule": "only observations dated strictly before validation year calibrate sigma",
            "horizon_rule": "target bar closes exactly at requested horizon",
            "expected_asset_direction": ASSET_EXPECTED_DIRECTION,
            "production_activation": False,
        },
        "diagnostics": diagnostics,
        "records": dataset,
    }


def summarize_macro_edge(
    dataset: Mapping[str, Any],
    *,
    horizons: Sequence[int],
    costs_bps: Optional[Mapping[str, float]] = None,
) -> Dict[str, Any]:
    """Summarize gross/net directional edge without optimizing thresholds."""
    records = list(dataset.get("records", []))
    costs = dict(DEFAULT_COST_BPS)
    if costs_bps:
        costs.update({str(key): float(value) for key, value in costs_bps.items()})

    output: Dict[str, Any] = {
        "sample_count": len(records),
        "assets": {},
        "methodology": {
            "threshold_optimization": False,
            "costs_bps": costs,
        },
    }

    for asset in (dataset.get("metadata", {}).get("expected_asset_direction", {}) or {}):
        asset_summary: Dict[str, Any] = {"horizons": {}}
        for horizon in horizons:
            ret_key = f"{asset}_return_{int(horizon)}m_bps"
            hit_key = f"{asset}_directional_hit_{int(horizon)}m"
            values = [float(row[ret_key]) for row in records if ret_key in row]
            hits = [bool(row[hit_key]) for row in records if hit_key in row]
            if not values:
                continue
            actionable = [row for row in records if ret_key in row and row.get("cluster_signal_usd", 0) != 0]
            signed_values: List[float] = []
            for row in actionable:
                signal = float(row["cluster_signal_usd"])
                expected_direction = float(ASSET_EXPECTED_DIRECTION[asset])
                signed_values.append(signal * expected_direction * float(row[ret_key]))
            cost = costs.get(asset, 0.0)
            net_values = [value - cost for value in signed_values]
            wins = sum(value > 0 for value in net_values)
            gross_wins = [value for value in signed_values if value > 0]
            gross_losses = [abs(value) for value in signed_values if value < 0]
            asset_summary["horizons"][str(horizon)] = {
                "sample_count": len(signed_values),
                "directional_hit_rate_pct": round(
                    sum(hits) / len(hits) * 100.0, 2
                ) if hits else None,
                "mean_gross_bps": round(mean(signed_values), 4) if signed_values else None,
                "mean_net_bps": round(mean(net_values), 4) if net_values else None,
                "profit_factor_gross": round(
                    sum(gross_wins) / sum(gross_losses), 3
                ) if gross_losses else (999.0 if gross_wins else None),
                "net_positive_rate_pct": round(wins / len(net_values) * 100.0, 2) if net_values else None,
            }
        output["assets"][asset] = asset_summary

    return output


def _safe_year(row: Mapping[str, Any]) -> int:
    try:
        return dt.date.fromisoformat(str(row["date"])).year
    except (KeyError, TypeError, ValueError):
        return -1


def main() -> None:
    parser = argparse.ArgumentParser(description="Research-only Macro Edge Engine v1")
    parser.add_argument("--observations", type=Path, default=Path(__file__).with_name("surprise_observations.csv"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("macro_edge_research.json"))
    parser.add_argument("--timeframe", choices=sorted(SUPPORTED_TIMEFRAMES), default="M5")
    parser.add_argument("--count", type=int, default=65000)
    parser.add_argument("--symbols", nargs="+", default=["XAUUSD", "EURUSD", "DXY", "US02Y", "US10Y"])
    parser.add_argument("--years", nargs="+", type=int, default=list(range(2019, 2026)))
    args = parser.parse_args()

    interval = SUPPORTED_TIMEFRAMES[args.timeframe]
    horizons = tuple(h for h in DEFAULT_HORIZONS if h % interval == 0)
    symbol_bars = {
        symbol: _event_bar_map(symbol, args.timeframe, args.count)
        for symbol in args.symbols
    }
    report = build_macro_edge_dataset(
        args.observations,
        symbol_bars,
        timeframe_minutes=interval,
        years=args.years,
        horizons=horizons,
    )
    report["summary"] = summarize_macro_edge(report, horizons=horizons)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "diagnostics": report["diagnostics"], "summary": report["summary"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
