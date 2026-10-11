"""Deterministic historical macro-event research dataset builder.

Research-only layer for discovering conditions that separate better and worse macro
signals. It does not activate production filters. All pre-event features use only data
strictly before the scheduled release. Outcome fields use exact event-horizon closes.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from calibration.event_horizon import target_bar_open
from calibration.market_response_validation_v2 import (
    BROKER_TZ,
    fetch_mt5_bars,
    parse_observation_event_utc,
)
from core.deterministic_controls import INDICATOR_DIRECTIONS, fit_surprise_sigmas

UTC = dt.timezone.utc
DEFAULT_YEARS = tuple(range(2021, 2026))
DEFAULT_HORIZONS = (30, 60, 240)
DEFAULT_PRE_WINDOWS = (30, 60, 240)
DEFAULT_VOL_LOOKBACK_BARS = 8


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


def _window_return_bps(
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    start: dt.datetime,
    end: dt.datetime,
) -> Optional[float]:
    """USD-strength return from start-bar close to end-bar open."""
    start_bar = bar_map.get(start)
    end_bar = bar_map.get(end)
    if start_bar is None or end_bar is None:
        return None
    p0 = float(start_bar["close"])
    p1 = float(end_bar["open"])
    if p0 <= 0 or not _finite(p0) or not _finite(p1):
        return None
    return (p0 - p1) / p0 * 10000.0


def _prior_returns_bps(
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    event_time: dt.datetime,
    interval_minutes: int,
    lookback_bars: int,
) -> List[float]:
    values: List[float] = []
    for i in range(lookback_bars, 0, -1):
        start = event_time - dt.timedelta(minutes=i * interval_minutes)
        end = event_time - dt.timedelta(minutes=(i - 1) * interval_minutes)
        start_bar = bar_map.get(start)
        end_bar = bar_map.get(end)
        if start_bar is None or end_bar is None:
            continue
        p0 = float(start_bar["close"])
        p1 = float(end_bar["close"])
        if p0 <= 0 or not _finite(p0) or not _finite(p1):
            continue
        values.append((p0 - p1) / p0 * 10000.0)
    return values


def _realized_vol_bps(
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    event_time: dt.datetime,
    interval_minutes: int,
    lookback_bars: int,
) -> Optional[float]:
    values = _prior_returns_bps(bar_map, event_time, interval_minutes, lookback_bars)
    if len(values) < 3:
        return None
    return pstdev(values)


def _atr_bps(
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    event_time: dt.datetime,
    interval_minutes: int,
    lookback_bars: int,
) -> Optional[float]:
    values: List[float] = []
    for i in range(lookback_bars, 0, -1):
        t = event_time - dt.timedelta(minutes=i * interval_minutes)
        prev_t = t - dt.timedelta(minutes=interval_minutes)
        bar = bar_map.get(t)
        prev = bar_map.get(prev_t)
        if bar is None or prev is None:
            continue
        prev_close = float(prev["close"])
        high = float(bar["high"])
        low = float(bar["low"])
        if prev_close <= 0 or not all(_finite(v) for v in (prev_close, high, low)):
            continue
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        values.append(tr / prev_close * 10000.0)
    if len(values) < 3:
        return None
    return mean(values)


def _outcome_path(
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    event_time: dt.datetime,
    interval_minutes: int,
    horizon_minutes: int,
) -> Optional[Tuple[float, float, float, int]]:
    """Return final USD return, MFE, MAE and bar count through exact horizon H."""
    base = bar_map.get(event_time)
    if base is None:
        return None
    p0 = float(base["open"])
    if p0 <= 0 or not _finite(p0):
        return None

    target = target_bar_open(event_time, interval_minutes, horizon_minutes)
    bar_count = horizon_minutes // interval_minutes
    highs: List[float] = []
    lows: List[float] = []
    final_close: Optional[float] = None

    for i in range(bar_count):
        t = event_time + dt.timedelta(minutes=i * interval_minutes)
        bar = bar_map.get(t)
        if bar is None:
            return None
        highs.append(float(bar["high"]))
        lows.append(float(bar["low"]))
        if t == target:
            final_close = float(bar["close"])

    if final_close is None:
        return None

    usd_final = (p0 - final_close) / p0 * 10000.0
    mfe = (p0 - min(lows)) / p0 * 10000.0
    mae = (p0 - max(highs)) / p0 * 10000.0
    return usd_final, mfe, mae, bar_count


def _cluster_observations(rows: Sequence[Mapping[str, Any]]) -> List[List[Mapping[str, Any]]]:
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        key = parse_observation_event_utc(row).isoformat()
        groups.setdefault(key, []).append(row)
    return [group for _, group in sorted(groups.items())]


def _cluster_signal(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    signed: List[int] = []
    for row in rows:
        kind = str(row.get("indicator_type", "")).strip().lower()
        try:
            raw = (float(row["actual"]) - float(row["forecast"])) * INDICATOR_DIRECTIONS.get(kind, 1.0)
        except (KeyError, TypeError, ValueError):
            continue
        signed.append(_sign(raw))
    if not signed:
        return {"cluster_signal": 0, "cluster_coherence": 0.0, "cluster_all_aligned": False}
    avg = mean(signed)
    return {
        "cluster_signal": _sign(avg),
        "cluster_coherence": round(abs(avg), 4),
        "cluster_all_aligned": abs(avg) == 1.0,
    }


def build_historical_event_dataset(
    observations_path: Path,
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    *,
    timeframe_minutes: int,
    test_years: Sequence[int] = DEFAULT_YEARS,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
    pre_windows: Sequence[int] = DEFAULT_PRE_WINDOWS,
    min_observations: int = 15,
    vol_lookback_bars: int = DEFAULT_VOL_LOOKBACK_BARS,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Build one research row per unique release timestamp."""
    with observations_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    years = tuple(sorted({int(v) for v in test_years}))
    diagnostics: Dict[str, Any] = {
        "observation_rows_total": len(rows),
        "selected_years": list(years),
        "selected_observation_rows": 0,
        "event_clusters_total": 0,
        "event_clusters_matched": 0,
        "missing_event_bar": 0,
        "missing_outcome": 0,
        "invalid_observation_rows": 0,
        "cluster_histogram": {},
    }

    selected_by_year: Dict[int, List[Mapping[str, Any]]] = {y: [] for y in years}
    for row in rows:
        try:
            year = dt.date.fromisoformat(str(row["date"])).year
        except (KeyError, ValueError):
            diagnostics["invalid_observation_rows"] += 1
            continue
        if year in selected_by_year:
            selected_by_year[year].append(row)
            diagnostics["selected_observation_rows"] += 1

    dataset: List[Dict[str, Any]] = []

    for year in years:
        mad_sigma = fit_surprise_sigmas(
            [r for r in rows if dt.date.fromisoformat(str(r["date"])).year < year],
            min_observations=min_observations,
            method="mad",
        )
        std_sigma = fit_surprise_sigmas(
            [r for r in rows if dt.date.fromisoformat(str(r["date"])).year < year],
            min_observations=min_observations,
            method="std",
        )

        clusters = _cluster_observations(selected_by_year[year])
        diagnostics["event_clusters_total"] += len(clusters)

        for group in clusters:
            event_time = parse_observation_event_utc(group[0])
            base = bar_map.get(event_time)
            if base is None:
                diagnostics["missing_event_bar"] += 1
                continue

            signal_info = _cluster_signal(group)
            signal = int(signal_info["cluster_signal"])
            indicators = sorted({str(r.get("indicator_type", "")).strip().lower() for r in group})
            mad_zs: List[float] = []
            std_zs: List[float] = []
            signed_surprises: List[float] = []

            for row in group:
                kind = str(row.get("indicator_type", "")).strip().lower()
                if kind not in mad_sigma or kind not in std_sigma:
                    diagnostics["invalid_observation_rows"] += 1
                    continue
                try:
                    raw = (float(row["actual"]) - float(row["forecast"])) * INDICATOR_DIRECTIONS.get(kind, 1.0)
                    signed_surprises.append(raw)
                    mad_zs.append(raw / mad_sigma[kind])
                    std_zs.append(raw / std_sigma[kind])
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    diagnostics["invalid_observation_rows"] += 1

            if not mad_zs:
                continue

            dominant = max(range(len(mad_zs)), key=lambda idx: abs(mad_zs[idx]))
            record: Dict[str, Any] = {
                "event_time_utc": event_time.isoformat(),
                "year": year,
                "indicators": "+".join(indicators),
                "cluster_size": len(group),
                "cluster_signal": signal,
                "cluster_coherence": signal_info["cluster_coherence"],
                "cluster_all_aligned": signal_info["cluster_all_aligned"],
                "mean_signed_surprise": round(mean(signed_surprises), 8),
                "mean_abs_mad_z": round(mean(abs(z) for z in mad_zs), 6),
                "max_abs_mad_z": round(max(abs(z) for z in mad_zs), 6),
                "dominant_z_mad": round(mad_zs[dominant], 6),
                "dominant_z_std": round(std_zs[dominant], 6),
            }

            # Features known strictly before release.
            for minutes in sorted({int(v) for v in pre_windows}):
                if minutes <= 0 or minutes % timeframe_minutes != 0:
                    continue
                start = event_time - dt.timedelta(minutes=minutes)
                pre = _window_return_bps(bar_map, start, event_time)
                record[f"pre_{minutes}m_usd_bps"] = None if pre is None else round(pre, 4)
                record[f"pre_{minutes}m_abs_bps"] = None if pre is None else round(abs(pre), 4)
                record[f"pre_{minutes}m_aligned"] = None if pre is None or signal == 0 else (_sign(pre) == signal)

            record["pre_realized_vol_bps"] = _realized_vol_bps(
                bar_map, event_time, timeframe_minutes, vol_lookback_bars
            )
            record["pre_atr_bps"] = _atr_bps(
                bar_map, event_time, timeframe_minutes, vol_lookback_bars
            )

            # Exact event-horizon outcomes. No bar after H is included.
            outcome_complete = True
            for horizon in sorted({int(v) for v in horizons}):
                if horizon <= 0 or horizon % timeframe_minutes != 0:
                    diagnostics["invalid_observation_rows"] += 1
                    outcome_complete = False
                    break
                outcome = _outcome_path(bar_map, event_time, timeframe_minutes, horizon)
                if outcome is None:
                    diagnostics["missing_outcome"] += 1
                    outcome_complete = False
                    break
                usd_final, mfe, mae, bar_count = outcome
                record[f"post_{horizon}m_usd_bps"] = round(usd_final, 4)
                record[f"post_{horizon}m_mfe_bps"] = round(mfe, 4)
                record[f"post_{horizon}m_mae_bps"] = round(mae, 4)
                record[f"post_{horizon}m_hit"] = bool(signal != 0 and signal * usd_final > 0)
                record[f"post_{horizon}m_observed_bars"] = bar_count

            if not outcome_complete:
                continue

            for horizon in sorted({int(v) for v in horizons}):
                ret = record[f"post_{horizon}m_usd_bps"]
                if signal != 0:
                    record[f"trade_{horizon}m_gross_bps"] = round(signal * ret, 4)

            record["dominant_mad_actionable"] = abs(mad_zs[dominant]) >= 1.0
            record["dominant_mad_directional_hit_30m"] = bool(
                signal != 0
                and abs(mad_zs[dominant]) >= 1.0
                and 30 in horizons
                and signal * record.get("post_30m_usd_bps", 0.0) > 0
            )

            diagnostics["event_clusters_matched"] += 1
            cluster_key = str(len(group))
            diagnostics["cluster_histogram"][cluster_key] = diagnostics["cluster_histogram"].get(cluster_key, 0) + 1
            dataset.append(record)

    dataset.sort(key=lambda r: str(r["event_time_utc"]))
    diagnostics["dataset_rows"] = len(dataset)
    diagnostics["coverage_pct"] = round(
        diagnostics["event_clusters_matched"] / diagnostics["event_clusters_total"] * 100.0,
        2,
    ) if diagnostics["event_clusters_total"] else 0.0
    diagnostics["broker_timezone_contract"] = str(BROKER_TZ)
    return dataset, diagnostics


def summarize_dataset(dataset: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not dataset:
        return {"sample_count": 0}

    by_year: Dict[str, List[Mapping[str, Any]]] = {}
    by_indicator: Dict[str, List[Mapping[str, Any]]] = {}
    for row in dataset:
        by_year.setdefault(str(row["year"]), []).append(row)
        for indicator in str(row["indicators"]).split("+"):
            by_indicator.setdefault(indicator, []).append(row)

    def hit(rows: Sequence[Mapping[str, Any]], key: str) -> Optional[float]:
        values = [bool(r[key]) for r in rows if key in r]
        if not values:
            return None
        return round(mean(values) * 100.0, 2)

    return {
        "sample_count": len(dataset),
        "by_year": {
            year: {
                "count": len(rows),
                "30m_hit_rate_pct": hit(rows, "post_30m_hit"),
                "mean_30m_trade_bps": round(mean(float(r.get("trade_30m_gross_bps", 0.0)) for r in rows), 4),
            }
            for year, rows in sorted(by_year.items())
        },
        "by_indicator": {
            indicator: {
                "cluster_membership_count": len(rows),
                "30m_hit_rate_pct": hit(rows, "post_30m_hit"),
                "mean_abs_mad_z": round(mean(float(r["mean_abs_mad_z"]) for r in rows), 4),
            }
            for indicator, rows in sorted(by_indicator.items())
        },
    }


def write_csv(dataset: Sequence[Mapping[str, Any]], path: Path) -> None:
    columns = sorted({key for row in dataset for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(dataset)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build historical macro event research dataset")
    parser.add_argument("--observations", type=Path, default=Path(__file__).with_name("surprise_observations.csv"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("historical_event_research.json"))
    parser.add_argument("--csv-output", type=Path, default=Path(__file__).with_name("historical_event_research.csv"))
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="M30", choices=["M15", "M30", "H1"])
    parser.add_argument("--count", type=int, default=65000)
    parser.add_argument("--years", nargs="+", type=int, default=list(DEFAULT_YEARS))
    args = parser.parse_args()

    interval = {"M15": 15, "M30": 30, "H1": 60}[args.timeframe.upper()]
    horizons = tuple(h for h in DEFAULT_HORIZONS if h % interval == 0)
    pre_windows = tuple(w for w in DEFAULT_PRE_WINDOWS if w % interval == 0)

    bars = fetch_mt5_bars(args.symbol, timeframe=args.timeframe.upper(), count=args.count)
    if not bars:
        raise SystemExit("MT5 bars unavailable; run this command on the Windows/MT5 environment.")

    dataset, diagnostics = build_historical_event_dataset(
        args.observations,
        bars,
        timeframe_minutes=interval,
        test_years=args.years,
        horizons=horizons,
        pre_windows=pre_windows,
    )
    report = {
        "metadata": {
            "symbol": args.symbol,
            "timeframe": args.timeframe.upper(),
            "time_basis": "scheduled US release in America/New_York converted to UTC",
            "bar_horizon_definition": "H-minute outcome is the CLOSE of the bar opening at H-interval",
            "feature_cutoff": "pre-event features use bars strictly before event_time",
            "walk_forward": "MAD/STD calibrated strictly before each validation year",
            "scope": "research only; no automatic production filter activation",
        },
        "diagnostics": diagnostics,
        "summary": summarize_dataset(dataset),
        "records": dataset,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(dataset, args.csv_output)
    print(json.dumps({"output": str(args.output), "csv_output": str(args.csv_output), "diagnostics": diagnostics, "summary": report["summary"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
