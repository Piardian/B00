from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

from core.deterministic_controls import parse_numeric
from calibration.trading_economics import OUTPUT_FIELDS

logger = logging.getLogger("CollectForexFactorySurprises")

DEFAULT_DATASET_URL = (
    "https://huggingface.co/datasets/Ehsanrs2/Forex_Factory_Calendar/resolve/main/forex_factory_cache.csv"
)

DEFAULT_US_EVENT_MAPPING = {
    "Non-Farm Employment Change": "nfp",
    "CPI m/m": "cpi",
    "Core CPI m/m": "core_cpi",
    "Unemployment Rate": "unemployment",
    "ISM Manufacturing PMI": "pmi",
    "Advance GDP q/q": "gdp",
    "Retail Sales m/m": "retail_sales",
}


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def collect_forexfactory_rows(
    start: dt.date,
    end: dt.date,
    source_url_or_path: str = DEFAULT_DATASET_URL,
    event_mapping: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    mapping = event_mapping or DEFAULT_US_EVENT_MAPPING
    rows: List[Dict[str, Any]] = []

    if source_url_or_path.startswith("http://") or source_url_or_path.startswith("https://"):
        logger.info("Streaming Forex Factory dataset from %s", source_url_or_path)
        resp = requests.get(
            source_url_or_path,
            stream=True,
            timeout=30,
            headers={"User-Agent": "BegonyaCalibration/1.0"},
        )
        resp.raise_for_status()
        line_iter = resp.iter_lines(decode_unicode=True)
    else:
        logger.info("Reading Forex Factory dataset from local path %s", source_url_or_path)
        local_path = Path(source_url_or_path)
        line_iter = iter(local_path.read_text(encoding="utf-8").splitlines())

    header_line = next(line_iter)
    header_reader = csv.reader([header_line])
    headers = [h.strip() for h in next(header_reader)]

    for line in line_iter:
        if not line or not line.strip():
            continue
        try:
            row_items = next(csv.reader([line]))
        except Exception:
            continue
        if len(row_items) < 6:
            continue

        row_dict = dict(zip(headers, row_items))
        currency = row_dict.get("Currency", "").strip()
        if currency != "USD":
            continue

        event_name = row_dict.get("Event", "").strip()
        if event_name not in mapping:
            continue

        actual_raw = row_dict.get("Actual", "").strip()
        forecast_raw = row_dict.get("Forecast", "").strip()
        if not actual_raw or not forecast_raw:
            continue

        raw_dt = row_dict.get("DateTime", "").strip()
        try:
            event_dt = dt.datetime.fromisoformat(raw_dt)
        except Exception:
            continue

        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=dt.timezone.utc)
        event_utc = event_dt.astimezone(dt.timezone.utc)
        event_date = event_utc.date()

        if not (start <= event_date <= end):
            continue

        try:
            actual_val = parse_numeric(actual_raw)
            forecast_val = parse_numeric(forecast_raw)
            prev_raw = row_dict.get("Previous", "").strip()
            prev_val = parse_numeric(prev_raw) if prev_raw else None
        except Exception:
            continue

        indicator_type = mapping[event_name]
        rows.append(
            {
                "date": event_date.isoformat(),
                "event_timestamp_utc": event_utc.isoformat(),
                "indicator_type": indicator_type,
                "event": event_name,
                "country": "United States",
                "actual": actual_val,
                "forecast": forecast_val,
                "previous": prev_val if prev_val is not None else "",
                "revision": "",
                "unit": "persons" if indicator_type == "nfp" else ("index" if indicator_type == "pmi" else "percent"),
                "importance": row_dict.get("Impact", "High"),
                "calendar_id": "",
                "ticker": "",
                "source": "ForexFactory",
                "source_url": "https://www.forexfactory.com/calendar",
                "provider": "ForexFactory",
                "provider_endpoint": source_url_or_path,
                "point_in_time": True,
            }
        )

    rows.sort(key=lambda r: (r["date"], r["indicator_type"], r["event"]))
    return rows


def write_observations_csv(rows: List[Dict[str, Any]], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row.get(f, "") for f in OUTPUT_FIELDS})
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Forex Factory historical economic surprises.")
    parser.add_argument("--start", type=parse_date, default=dt.date(2016, 1, 1), help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=parse_date, default=dt.date(2025, 12, 31), help="End date YYYY-MM-DD")
    parser.add_argument("--source", type=str, default=DEFAULT_DATASET_URL, help="HF URL or local CSV path")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("surprise_observations.csv"),
        help="Output CSV path",
    )
    args = parser.parse_args()

    if args.start > args.end:
        parser.error("--start must be before or equal to --end")

    rows = collect_forexfactory_rows(args.start, args.end, source_url_or_path=args.source)
    count = write_observations_csv(rows, args.output)
    print(f"Successfully collected {count} ForexFactory PIT observations into {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
