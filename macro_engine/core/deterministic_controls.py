from __future__ import annotations

import datetime as dt
import math
import re
from statistics import mean, median, pstdev
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from data_quality import DataUnavailableError

INDICATOR_DIRECTIONS = {
    "cpi": 1.0,
    "core_cpi": 1.0,
    "nfp": 1.0,
    "unemployment": -1.0,
    "pmi": 1.0,
    "gdp": 1.0,
    "retail_sales": 1.0,
    "generic": 1.0,
}

GATE_VALUES = {
    "LONG_ONLY", "SHORT_ONLY", "NEUTRAL_ALL", "NEUTRAL_RANGE",
    "DEFENSIVE_HOLD", "REDUCE_ONLY", "NO_TRADE",
}

SOURCE_MAX_AGE_DAYS = {
    "daily": 3,
    "weekly": 10,
    "monthly": 45,
    "quarterly": 120,
    "unknown": 7,
}


def resolve_hysteresis(
    brent: float,
    global_mfg_slowing: bool,
    previous_state: Optional[Mapping[str, Any]],
    enter_level: float = 85.0,
    exit_level: float = 81.0,
) -> Dict[str, Any]:
    """Pure hysteresis transition; prior state is explicit and never read from disk."""
    previous_active = bool((previous_state or {}).get("energy_penalty_active", False))
    if previous_active:
        active = not (brent < exit_level)
        note = "previous_state=active; state exits only below exit threshold"
    else:
        active = bool(brent >= enter_level and global_mfg_slowing)
        note = "previous_state=inactive; entry requires level and slowdown"
    return {
        "energy_penalty_active": active,
        "hysteresis_active": previous_active != active or previous_active,
        "hysteresis_note": note,
    }


def event_freeze_status(
    events: Iterable[Mapping[str, Any]],
    now_utc: dt.datetime,
    freeze_before: float = 15.0,
    freeze_after: float = 15.0,
    keywords: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Deterministic event-freeze calculation using an explicit UTC clock.

    A high-impact event with an unavailable or invalid timestamp is treated as uncertain
    and therefore fail-closed: trading is frozen rather than assuming the event is safely
    outside the freeze window.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=dt.timezone.utc)
    else:
        now_utc = now_utc.astimezone(dt.timezone.utc)

    kws = [k.lower() for k in (keywords or [])]
    active = False
    info = ""
    for event in events:
        title = str(event.get("title", ""))
        impact = str(event.get("impact", "")).upper()
        is_high = impact in {"CRITICAL", "HIGH", "RED"} or any(k in title.lower() for k in kws)
        if not is_high:
            continue
        raw_time = event.get("time") or event.get("event_time_utc") or event.get("date")
        if not raw_time:
            return {
                "active": True,
                "uncertain": True,
                "info": f"{title or 'High-impact event'} [event time unavailable; fail-closed]",
            }
        try:
            event_time = dt.datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=dt.timezone.utc)
            event_time = event_time.astimezone(dt.timezone.utc)
        except (TypeError, ValueError):
            return {
                "active": True,
                "uncertain": True,
                "info": f"{title or 'High-impact event'} [event time invalid; fail-closed]",
            }
        diff_min = (event_time - now_utc).total_seconds() / 60.0
        if -float(freeze_after) <= diff_min <= float(freeze_before):
            active = True
            info = f"{title} ({event.get('country', 'USD')}) [Kalan: {diff_min:+.0f} dk]"
            break
    return {"active": active, "uncertain": False, "info": info}


def validate_freshness(
    field: str,
    observation_date: Optional[dt.date],
    as_of: dt.date,
    frequency: str = "unknown",
    max_age_days: Optional[int] = None,
) -> int:
    if observation_date is None:
        raise DataUnavailableError(f"Observation date missing for {field}")
    age = (as_of - observation_date).days
    allowed = max_age_days if max_age_days is not None else SOURCE_MAX_AGE_DAYS.get(frequency, 7)
    if age < 0:
        raise DataUnavailableError(f"Future observation detected for {field}: {observation_date}")
    if age > allowed:
        raise DataUnavailableError(
            f"Stale observation for {field}: age={age}d > allowed={allowed}d ({frequency})"
        )
    return age


def validate_numeric_range(name: str, value: Any, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise DataUnavailableError(f"Non-finite/non-numeric value for {name}: {value!r}")
    numeric = float(value)
    if not minimum <= numeric <= maximum:
        raise DataUnavailableError(
            f"Out-of-range value for {name}: {numeric}; expected [{minimum}, {maximum}]"
        )
    return numeric


def parse_numeric(value: Any) -> float:
    """Parse common calendar units without silently changing sign."""
    if isinstance(value, bool):
        raise ValueError("boolean is not numeric")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "")
    text = text.replace(",", "")
    multiplier = 1.0
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*([KkMmBb]?)", text)
    if not match:
        raise ValueError(f"cannot parse numeric value: {value!r}")
    number, unit = match.groups()
    if unit.lower() == "k":
        multiplier = 1_000.0
    elif unit.lower() == "m":
        multiplier = 1_000_000.0
    elif unit.lower() == "b":
        multiplier = 1_000_000_000.0
    return float(number) * multiplier


def normalize_calendar_event(event: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(event)
    raw_time = result.get("time") or result.get("event_time_utc") or result.get("date")
    if raw_time:
        result["time"] = raw_time
        result["event_time_utc"] = raw_time
    for key in ("actual", "forecast", "previous", "revision"):
        if result.get(key) not in (None, ""):
            try:
                result[key] = parse_numeric(result[key])
            except ValueError:
                result[f"{key}_parse_error"] = True
    return result


def signed_surprise_zscore(
    indicator_type: str,
    actual: float,
    forecast: float,
    sigma: float,
    clip: float = 4.0,
    direction: Optional[float] = None,
) -> float:
    if sigma <= 0 or not math.isfinite(sigma):
        raise ValueError("sigma must be finite and > 0")
    direction_value = INDICATOR_DIRECTIONS.get(indicator_type.lower(), 1.0) if direction is None else float(direction)
    if direction_value not in (-1.0, 1.0):
        raise ValueError("direction must be +1 or -1")
    z = ((float(actual) - float(forecast)) * direction_value) / sigma
    return max(-clip, min(clip, round(z, 2)))


def fit_surprise_sigmas(
    rows: Iterable[Mapping[str, Any]],
    min_observations: int = 30,
    method: str = "mad",
) -> Dict[str, float]:
    """Fit empirical population sigmas (Robust MAD or standard deviation) from a provider-backed observation table."""
    if method not in ("mad", "std"):
        raise ValueError(f"Unknown fitting method: {method!r}, must be 'mad' or 'std'")

    grouped: Dict[str, List[float]] = {}
    for row in rows:
        kind = str(row.get("indicator_type", "generic")).lower()
        actual = row.get("actual")
        forecast = row.get("forecast")
        if actual in (None, "") or forecast in (None, ""):
            continue
        try:
            surprise = (float(actual) - float(forecast)) * INDICATOR_DIRECTIONS.get(kind, 1.0)
        except (TypeError, ValueError):
            continue
        grouped.setdefault(kind, []).append(surprise)

    fitted: Dict[str, float] = {}
    for kind, values in grouped.items():
        if len(values) < min_observations:
            continue
        if method == "mad":
            med = median(values)
            mad = median([abs(v - med) for v in values])
            sigma = 1.4826 * mad
            if sigma <= 0 or not math.isfinite(sigma):
                sigma = pstdev(values)
        else:
            sigma = pstdev(values)

        if sigma > 0 and math.isfinite(sigma):
            fitted[kind] = round(sigma, 8)
    return fitted


def chronological_split(
    rows: Iterable[Mapping[str, Any]],
    calibration_end: dt.date,
    validation_end: dt.date,
) -> Dict[str, List[Mapping[str, Any]]]:
    """Strict chronological split; rows after validation_end are OOS."""
    if calibration_end >= validation_end:
        raise ValueError("calibration_end must be before validation_end")
    out = {"calibration": [], "validation": [], "out_of_sample": []}
    for row in rows:
        raw_date = row.get("date")
        if raw_date is None:
            continue
        try:
            row_date = raw_date if isinstance(raw_date, dt.date) else dt.date.fromisoformat(str(raw_date))
        except ValueError:
            continue
        if row_date <= calibration_end:
            out["calibration"].append(row)
        elif row_date <= validation_end:
            out["validation"].append(row)
        else:
            out["out_of_sample"].append(row)
    return out


def return_series(values: Sequence[float]) -> List[float]:
    if len(values) < 2:
        return []
    out: List[float] = []
    for prev, cur in zip(values, values[1:]):
        if prev == 0:
            out.append(0.0)
        else:
            out.append((cur / prev) - 1.0)
    return out


def pearson_correlation(series_a: Sequence[float], series_b: Sequence[float]) -> float:
    if len(series_a) != len(series_b) or len(series_a) < 3:
        return 0.0
    mean_a = mean(series_a)
    mean_b = mean(series_b)
    var_a = sum((x - mean_a) ** 2 for x in series_a)
    var_b = sum((y - mean_b) ** 2 for y in series_b)
    if var_a == 0 or var_b == 0:
        return 0.0
    cov = sum((series_a[i] - mean_a) * (series_b[i] - mean_b) for i in range(len(series_a)))
    return round(cov / math.sqrt(var_a * var_b), 4)


def return_correlation(values_a: Sequence[float], values_b: Sequence[float]) -> float:
    return pearson_correlation(return_series(values_a), return_series(values_b))


def resolve_execution_gate(
    base_bias: str,
    *,
    event_freeze: bool = False,
    systemic_stress: bool = False,
    risk_score: float = 0.0,
) -> Dict[str, Any]:
    """Deterministic precedence: event freeze > systemic stress > base bias."""
    bias = str(base_bias).upper()
    if bias not in GATE_VALUES:
        bias = "NO_TRADE"
    if event_freeze:
        final = "NO_TRADE"
        reason = "event_freeze has highest precedence"
    elif systemic_stress or risk_score >= 0.90:
        final = "DEFENSIVE_HOLD"
        reason = "systemic stress/risk threshold has precedence"
    else:
        final = bias
        reason = "deterministic base bias"
    return {
        "gate": final,
        "reason": reason,
        "precedence": ["EVENT_FREEZE", "SYSTEMIC_STRESS", "BASE_BIAS"],
        "source": "deterministic_metrics_only",
    }
