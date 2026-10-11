from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping

from statistics import pstdev

from core.deterministic_controls import chronological_split, fit_surprise_sigmas, signed_surprise_zscore
from data_quality import DataUnavailableError


REQUIRED_COLUMNS = {
    "date",
    "event_timestamp_utc",
    "indicator_type",
    "actual",
    "forecast",
    "provider",
    "point_in_time",
}


def _parse_date(value: Any) -> dt.date:
    try:
        return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid calibration date: {value!r}") from exc


def _parse_timestamp(value: Any) -> dt.datetime:
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid event timestamp: {value!r}") from exc
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def _parse_number(field: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"Non-finite {field}: {value!r}")
    return number


def load_observations_csv(path: Path) -> list[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Calibration dataset is empty")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise ValueError("Calibration dataset missing columns: " + ", ".join(sorted(missing)))

    validated: list[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        if not str(row.get("indicator_type", "")).strip():
            raise ValueError(f"Row {index}: indicator_type is required")
        provider = str(row.get("provider", "")).strip()
        if provider not in ("TradingEconomics", "ForexFactory"):
            raise DataUnavailableError(f"Row {index}: provider must be TradingEconomics or ForexFactory")
        if str(row.get("point_in_time", "")).strip().lower() not in ("true", "1"):
            raise DataUnavailableError(f"Row {index}: point_in_time must be true")

        event_date = _parse_date(row.get("date"))
        event_timestamp = _parse_timestamp(row.get("event_timestamp_utc"))
        if event_timestamp.date() != event_date:
            raise ValueError(f"Row {index}: date and event_timestamp_utc disagree")

        validated.append({
            **row,
            "date": event_date.isoformat(),
            "event_timestamp_utc": event_timestamp.isoformat(),
            "indicator_type": str(row["indicator_type"]).strip().lower(),
            "actual": _parse_number("actual", row.get("actual")),
            "forecast": _parse_number("forecast", row.get("forecast")),
            "provider": provider,
            "point_in_time": True,
        })
    return validated


def evaluate_validation_performance(
    sigmas: Mapping[str, float],
    validation_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    grouped_z: Dict[str, List[float]] = {}
    all_z: List[float] = []

    for row in validation_rows:
        kind = str(row.get("indicator_type", "")).lower()
        if kind not in sigmas:
            continue
        actual = row.get("actual")
        forecast = row.get("forecast")
        if actual in (None, "") or forecast in (None, ""):
            continue
        try:
            z = signed_surprise_zscore(kind, float(actual), float(forecast), sigmas[kind], clip=10.0)
        except (TypeError, ValueError):
            continue
        grouped_z.setdefault(kind, []).append(z)
        all_z.append(z)

    by_indicator: Dict[str, Any] = {}
    for kind, zs in grouped_z.items():
        n = len(zs)
        if n == 0:
            continue
        msnr = sum(z**2 for z in zs) / n
        std_z = pstdev(zs)
        in_1sig = sum(1 for z in zs if abs(z) <= 1.0) / n * 100.0
        in_2sig = sum(1 for z in zs if abs(z) <= 2.0) / n * 100.0
        by_indicator[kind] = {
            "sample_count": n,
            "std_z": round(std_z, 4),
            "msnr": round(msnr, 4),
            "pct_within_1sigma": round(in_1sig, 2),
            "pct_within_2sigma": round(in_2sig, 2),
            "max_abs_z": round(max(abs(z) for z in zs), 2),
        }

    agg_n = len(all_z)
    aggregate = {
        "sample_count": agg_n,
        "std_z": round(pstdev(all_z), 4) if agg_n > 0 else 0.0,
        "msnr": round(sum(z**2 for z in all_z) / agg_n, 4) if agg_n > 0 else 0.0,
        "pct_within_1sigma": round(sum(1 for z in all_z if abs(z) <= 1.0) / agg_n * 100.0, 2) if agg_n > 0 else 0.0,
        "pct_within_2sigma": round(sum(1 for z in all_z if abs(z) <= 2.0) / agg_n * 100.0, 2) if agg_n > 0 else 0.0,
    }
    return {
        "aggregate": aggregate,
        "by_indicator": by_indicator,
    }


def calibrate_from_csv(
    path: Path,
    calibration_end: dt.date,
    validation_end: dt.date,
    min_observations: int = 30,
    required_indicators: tuple[str, ...] = (),
    filter_covid_shock: bool = False,
    method: str = "mad",
) -> Dict[str, Any]:
    if min_observations <= 1:
        raise ValueError("min_observations must be > 1")
    rows = load_observations_csv(path)
    if filter_covid_shock:
        covid_start = dt.date(2020, 3, 1)
        covid_end = dt.date(2020, 7, 31)
        rows = [r for r in rows if not (covid_start <= dt.date.fromisoformat(str(r["date"])) <= covid_end)]

    split = chronological_split(rows, calibration_end, validation_end)
    sigmas = fit_surprise_sigmas(split["calibration"], min_observations=min_observations, method=method)
    missing_indicators = [
        indicator for indicator in required_indicators if indicator.lower() not in sigmas
    ]
    if missing_indicators:
        raise ValueError(
            "Insufficient calibration observations for: " + ", ".join(sorted(missing_indicators))
        )
    if not sigmas:
        raise ValueError("No empirical sigma could be fitted from the calibration partition")

    val_perf = evaluate_validation_performance(sigmas, split["validation"])

    return {
        "method": f"empirical_{method}" + ("_ex_covid" if filter_covid_shock else ""),
        "scale_estimator": method,
        "filter_covid_shock": filter_covid_shock,
        "calibration_end": calibration_end.isoformat(),
        "validation_end": validation_end.isoformat(),
        "sample_counts": {key: len(value) for key, value in split.items()},
        "sigmas": sigmas,
        "required_indicators": list(required_indicators),
        "validation_performance": val_perf,
        "validation_rows": split["validation"],
        "out_of_sample_rows": split["out_of_sample"],
    }


def write_calibration_profile(profile: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def load_calibration_profile(path: Path) -> Dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sigmas = payload.get("sigmas")
    if not isinstance(sigmas, dict) or not sigmas:
        raise ValueError("Calibration profile has no fitted sigmas")
    result: Dict[str, float] = {}
    for key, value in sigmas.items():
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"Invalid calibrated sigma for {key}: {value!r}")
        result[str(key)] = number
    return result
