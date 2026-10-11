from __future__ import annotations

import csv
import datetime as dt
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence
from urllib.parse import quote

import requests

from config import TRADING_ECONOMICS_API_KEY
from core.deterministic_controls import parse_numeric
from data_quality import DataUnavailableError


DEFAULT_US_INDICATORS = {
    "nfp": "Non Farm Payrolls",
    "cpi": "Inflation Rate MoM",
    "core_cpi": "Core Inflation Rate MoM",
    "unemployment": "Unemployment Rate",
    "pmi": "ISM Manufacturing PMI",
    "gdp": "GDP Growth Rate QoQ",
    "retail_sales": "Retail Sales MoM",
}

OUTPUT_FIELDS = (
    "date",
    "event_timestamp_utc",
    "indicator_type",
    "event",
    "country",
    "actual",
    "forecast",
    "previous",
    "revision",
    "unit",
    "importance",
    "calendar_id",
    "ticker",
    "source",
    "source_url",
    "provider",
    "provider_endpoint",
    "point_in_time",
)


def _parse_event_timestamp(value: Any) -> dt.datetime:
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise DataUnavailableError(f"Invalid Trading Economics event date: {value!r}") from exc
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def _numeric_or_none(value: Any) -> float | None:
    if value in (None, "", "."):
        return None
    try:
        number = parse_numeric(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


class TradingEconomicsCalendarClient:
    """Fetch historical calendar observations with provider provenance."""

    BASE_URL = "https://api.tradingeconomics.com/calendar/country"

    def __init__(self, api_key: str = TRADING_ECONOMICS_API_KEY, timeout: int = 15):
        self.api_key = api_key
        self.timeout = timeout

    def _require_key(self) -> None:
        if not self.api_key:
            raise DataUnavailableError("TRADING_ECONOMICS_API_KEY is not configured")

    def fetch_indicator(
        self,
        country: str,
        indicator: str,
        start: dt.date,
        end: dt.date,
    ) -> list[Dict[str, Any]]:
        self._require_key()
        if start > end:
            raise ValueError("start must be <= end")

        endpoint = (
            f"{self.BASE_URL}/{quote(country, safe='')}/indicator/"
            f"{quote(indicator, safe='')}/{start.isoformat()}/{end.isoformat()}"
        )
        try:
            response = requests.get(
                endpoint,
                params={"c": self.api_key, "f": "json"},
                timeout=self.timeout,
                headers={"User-Agent": "BegonyaCalibration/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DataUnavailableError(
                f"Trading Economics request failed for {country}/{indicator}: {exc}"
            ) from exc

        if not isinstance(payload, list):
            raise DataUnavailableError("Trading Economics response is not a list")

        rows: list[Dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            event_time = _parse_event_timestamp(item.get("Date"))
            actual = _numeric_or_none(item.get("Actual"))
            forecast = _numeric_or_none(item.get("Forecast"))
            if actual is None or forecast is None:
                continue
            rows.append(
                {
                    "date": event_time.date().isoformat(),
                    "event_timestamp_utc": event_time.isoformat(),
                    "indicator_type": indicator_type_from_name(indicator),
                    "event": str(item.get("Event") or item.get("Category") or indicator),
                    "country": str(item.get("Country") or country),
                    "actual": actual,
                    "forecast": forecast,
                    "previous": _numeric_or_none(item.get("Previous")),
                    "revision": _numeric_or_none(item.get("Revised")),
                    "unit": str(item.get("Unit") or ""),
                    "importance": item.get("Importance"),
                    "calendar_id": str(item.get("CalendarId") or ""),
                    "ticker": str(item.get("Ticker") or item.get("Symbol") or ""),
                    "source": str(item.get("Source") or ""),
                    "source_url": str(item.get("SourceURL") or ""),
                    "provider": "TradingEconomics",
                    "provider_endpoint": endpoint,
                    "point_in_time": True,
                }
            )
        return rows

    def collect_us_indicators(
        self,
        start: dt.date,
        end: dt.date,
        indicators: Mapping[str, str] | None = None,
    ) -> list[Dict[str, Any]]:
        mapping = indicators or DEFAULT_US_INDICATORS
        all_rows: list[Dict[str, Any]] = []
        for indicator_type, indicator_name in mapping.items():
            rows = self.fetch_indicator("United States", indicator_name, start, end)
            for row in rows:
                row["indicator_type"] = indicator_type.lower()
                all_rows.append(row)
        return sorted(all_rows, key=lambda row: (row["date"], row["indicator_type"], row["event"]))


def indicator_type_from_name(indicator: str) -> str:
    aliases = {
        "non farm payrolls": "nfp",
        "non-farm payrolls": "nfp",
        "unemployment rate": "unemployment",
        "inflation rate mom": "cpi",
        "core inflation rate mom": "core_cpi",
        "ism manufacturing pmi": "pmi",
        "gdp growth rate qoq": "gdp",
        "retail sales mom": "retail_sales",
    }
    return aliases.get(indicator.lower(), indicator.lower().replace(" ", "_"))


def validate_pit_rows(rows: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    """Require provider provenance and actual/consensus data for calibration rows."""
    validated: list[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        for field in ("date", "event_timestamp_utc", "indicator_type", "actual", "forecast", "provider"):
            if row.get(field) in (None, ""):
                raise DataUnavailableError(f"Calibration row {index} missing {field}")
        if str(row.get("provider")) not in ("TradingEconomics", "ForexFactory"):
            raise DataUnavailableError(f"Calibration row {index} has untrusted provider")
        if row.get("point_in_time") is not True:
            raise DataUnavailableError(f"Calibration row {index} is not point-in-time")
        event_time = _parse_event_timestamp(row["event_timestamp_utc"])
        event_date = dt.date.fromisoformat(str(row["date"]))
        if event_time.date() != event_date:
            raise DataUnavailableError(f"Calibration row {index} date/timestamp mismatch")
        actual = float(row["actual"])
        forecast = float(row["forecast"])
        if not math.isfinite(actual) or not math.isfinite(forecast):
            raise DataUnavailableError(f"Calibration row {index} contains non-finite values")
        validated.append(dict(row))
    return validated


def write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> int:
    validated = validate_pit_rows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in validated:
            writer.writerow({field: row.get(field, "") for field in OUTPUT_FIELDS})
    return len(validated)
