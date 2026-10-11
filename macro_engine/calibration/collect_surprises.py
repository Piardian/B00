from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from calibration.trading_economics import TradingEconomicsCalendarClient, write_csv


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect provider-backed historical economic surprises.")
    parser.add_argument("--start", required=True, type=parse_date, help="Inclusive start date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, type=parse_date, help="Inclusive end date, YYYY-MM-DD")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("surprise_observations.csv"),
        help="Output CSV path",
    )
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("--start must be <= --end")

    client = TradingEconomicsCalendarClient()
    rows = client.collect_us_indicators(args.start, args.end)
    count = write_csv(rows, args.output)
    print(f"Wrote {count} provider-backed PIT observations to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
