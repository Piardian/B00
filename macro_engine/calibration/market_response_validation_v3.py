"""Exact-horizon, event-time aligned macro market-response validation.

This is the canonical research validator. It preserves the established event timestamp
and MT5 broker-time conversion, but fixes a critical bar-close alignment detail:
for a bar interval I and horizon H, the bar whose CLOSE represents H minutes after
the release opens at event_time + H - I.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Mapping, Sequence

from calibration.event_horizon import target_bar_open
from calibration.market_response_validation_v2 import (
    audit_event_timestamp,
    calculate_usd_return_bps,
    fetch_mt5_bars,
    parse_observation_event_utc,
    spearman_rank_ic,
)
from core.deterministic_controls import INDICATOR_DIRECTIONS, fit_surprise_sigmas

HORIZONS_BY_TIMEFRAME = {
    "M5": (5, 15, 30, 60, 240),
    "M15": (15, 30, 60, 240),
    "M30": (30, 60, 240),
    "H1": (60, 240),
}
INTERVALS = {"M5": 5, "M15": 15, "M30": 30, "H1": 60}
UTC = dt.timezone.utc


def _usable_horizons(timeframe: str, requested: Sequence[int] | None = None) -> tuple[int, ...]:
    tf = timeframe.upper()
    interval = INTERVALS[tf]
    candidates = HORIZONS_BY_TIMEFRAME[tf] if requested is None else requested
    return tuple(sorted({int(h) for h in candidates if h > 0 and h % interval == 0}))


def _directional_hit(signal: float, usd_return_bps: float) -> bool:
    return signal != 0 and signal * usd_return_bps > 0


def build_records(
    observations_path: Path,
    bar_map: Mapping[dt.datetime, Mapping[str, float]],
    *,
    timeframe_minutes: int,
    test_years: Sequence[int] = tuple(range(2019, 2026)),
    min_observations: int = 15,
    horizons: Sequence[int] | None = None,
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Create exact-horizon event observations using expanding calibration windows."""
    with observations_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    hs = tuple(sorted(set(int(h) for h in (horizons or HORIZONS_BY_TIMEFRAME[next(tf for tf, n in INTERVALS.items() if n == timeframe_minutes)]))))
    for h in hs:
        if h <= 0 or h % timeframe_minutes != 0:
            raise ValueError(f"Horizon {h} is incompatible with {timeframe_minutes}-minute bars")

    records: List[Dict[str, Any]] = []
    diagnostics = {
        "observations_total": len(rows),
        "matched": 0,
        "missing_event_bar": 0,
        "missing_horizon_bar": 0,
        "invalid_observation": 0,
    }

    for year in sorted(set(int(y) for y in test_years)):
        history = [r for r in rows if dt.date.fromisoformat(str(r["date"])).year < year]
        mad = fit_surprise_sigmas(history, min_observations=min_observations, method="mad")
        std = fit_surprise_sigmas(history, min_observations=min_observations, method="std")

        for row in rows:
            if dt.date.fromisoformat(str(row["date"])).year != year:
                continue
            kind = str(row.get("indicator_type", "")).strip().lower()
            if kind not in mad or kind not in std:
                diagnostics["invalid_observation"] += 1
                continue
            try:
                actual = float(row["actual"])
                forecast = float(row["forecast"])
                event_time = parse_observation_event_utc(row)
                direction = INDICATOR_DIRECTIONS.get(kind, 1.0)
                raw_surprise = (actual - forecast) * direction
                z_mad = raw_surprise / mad[kind]
                z_std = raw_surprise / std[kind]
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                diagnostics["invalid_observation"] += 1
                continue

            base = bar_map.get(event_time)
            if base is None:
                diagnostics["missing_event_bar"] += 1
                continue

            p0 = float(base["open"])
            if not math.isfinite(p0) or p0 <= 0:
                diagnostics["invalid_observation"] += 1
                continue

            record: Dict[str, Any] = {
                "year": year,
                "indicator": kind,
                "event": row.get("event", ""),
                "event_timestamp_utc": event_time.isoformat(),
                "actual": actual,
                "forecast": forecast,
                "raw_surprise": raw_surprise,
                "sign_surprise": 1.0 if raw_surprise > 0 else (-1.0 if raw_surprise < 0 else 0.0),
                "z_mad": z_mad,
                "z_std": z_std,
                "timestamp_audit": audit_event_timestamp(row),
            }

            complete = True
            for h in hs:
                target = target_bar_open(event_time, timeframe_minutes, h)
                bar = bar_map.get(target)
                if bar is None:
                    complete = False
                    diagnostics["missing_horizon_bar"] += 1
                    break
                close = float(bar["close"])
                ret = calculate_usd_return_bps(p0, close)
                record[f"ret_{h}m"] = ret
                record[f"hit_mad_{h}m"] = _directional_hit(z_mad, ret)
                record[f"hit_std_{h}m"] = _directional_hit(z_std, ret)
            if not complete:
                continue

            diagnostics["matched"] += 1
            records.append(record)

    return records, diagnostics


def summarize(
    records: Sequence[Mapping[str, Any]],
    horizons: Sequence[int],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"sample_count": len(records), "horizons": {}}
    for h in horizons:
        key = f"ret_{h}m"
        valid = [r for r in records if key in r]
        if not valid:
            continue
        mad_z = [float(r["z_mad"]) for r in valid]
        std_z = [float(r["z_std"]) for r in valid]
        rets = [float(r[key]) for r in valid]
        out["horizons"][f"{h}m"] = {
            "mad_rank_ic": round(spearman_rank_ic(mad_z, rets), 6),
            "std_rank_ic": round(spearman_rank_ic(std_z, rets), 6),
            "delta_mad_minus_std": round(spearman_rank_ic(mad_z, rets) - spearman_rank_ic(std_z, rets), 6),
            "mad_hit_rate_pct": round(mean(float(r[f"hit_mad_{h}m"]) for r in valid) * 100.0, 3),
            "std_hit_rate_pct": round(mean(float(r[f"hit_std_{h}m"]) for r in valid) * 100.0, 3),
            "mean_mad_signed_return_bps": round(
                mean((1.0 if float(r["z_mad"]) > 0 else -1.0) * float(r[key]) for r in valid if float(r["z_mad"]) != 0),
                6,
            ),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Exact-horizon macro market-response validator")
    parser.add_argument("--observations", type=Path, default=Path(__file__).with_name("surprise_observations.csv"))
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("market_response_validation_v3.json"))
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--timeframe", default="M30", choices=sorted(INTERVALS))
    parser.add_argument("--count", type=int, default=65000)
    args = parser.parse_args()

    tf = args.timeframe.upper()
    interval = INTERVALS[tf]
    horizons = _usable_horizons(tf)
    bars = fetch_mt5_bars(args.symbol, timeframe=tf, count=args.count)
    if not bars:
        raise SystemExit("MT5 bars unavailable; run this command on the Windows/MT5 environment.")

    records, diagnostics = build_records(
        args.observations,
        bars,
        timeframe_minutes=interval,
        horizons=horizons,
    )
    report = {
        "metadata": {
            "symbol": args.symbol,
            "timeframe": tf,
            "horizons_minutes": list(horizons),
            "event_time_basis": "America/New_York scheduled release converted to UTC",
            "horizon_definition": "bar close exactly H minutes after event; target bar opens at H-interval",
            "walk_forward": "calibration strictly before validation year",
        },
        "diagnostics": diagnostics,
        "summary": summarize(records, horizons),
        "records": records,
    }
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "diagnostics": diagnostics, "summary": report["summary"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
