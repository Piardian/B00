import datetime as dt
import unittest
from unittest.mock import patch

from calibration.trading_economics import (
    TradingEconomicsCalendarClient,
    validate_pit_rows,
    write_csv,
)
from data_quality import DataUnavailableError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class TradingEconomicsCalibrationTests(unittest.TestCase):
    def test_missing_api_key_fails_closed(self):
        client = TradingEconomicsCalendarClient(api_key="")
        with self.assertRaises(DataUnavailableError):
            client.fetch_indicator(
                "United States",
                "Non Farm Payrolls",
                dt.date(2023, 1, 1),
                dt.date(2023, 2, 1),
            )

    @patch("calibration.trading_economics.requests.get")
    def test_historical_rows_are_normalized_and_forecast_is_consensus_field(self, mock_get):
        mock_get.return_value = FakeResponse(
            [
                {
                    "CalendarId": "123",
                    "Date": "2023-01-06T13:30:00",
                    "Country": "United States",
                    "Category": "Non Farm Payrolls",
                    "Event": "Non Farm Payrolls",
                    "Actual": "223K",
                    "Forecast": "200K",
                    "Previous": "256K",
                    "Revised": "261K",
                    "Unit": "K",
                    "Importance": 3,
                    "Ticker": "NFP TCH",
                    "Source": "U.S. Bureau of Labor Statistics",
                    "SourceURL": "https://www.bls.gov/",
                },
                {
                    "CalendarId": "124",
                    "Date": "2023-01-10T13:30:00",
                    "Country": "United States",
                    "Category": "Some Event",
                    "Event": "Some Event",
                    "Actual": "1.0",
                    "Forecast": "",
                },
            ]
        )
        client = TradingEconomicsCalendarClient(api_key="test")
        rows = client.fetch_indicator(
            "United States",
            "Non Farm Payrolls",
            dt.date(2023, 1, 1),
            dt.date(2023, 1, 31),
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["actual"], 223_000.0)
        self.assertEqual(row["forecast"], 200_000.0)
        self.assertEqual(row["indicator_type"], "nfp")
        self.assertEqual(row["provider"], "TradingEconomics")
        self.assertTrue(row["point_in_time"])
        self.assertEqual(row["event_timestamp_utc"], "2023-01-06T13:30:00+00:00")

    def test_untrusted_rows_fail(self):
        with self.assertRaises(DataUnavailableError):
            validate_pit_rows(
                [{
                    "date": "2023-01-06",
                    "event_timestamp_utc": "2023-01-06T13:30:00+00:00",
                    "indicator_type": "nfp",
                    "actual": 223000,
                    "forecast": 200000,
                    "provider": "unknown",
                    "point_in_time": True,
                }]
            )

    def test_csv_writer_requires_pit_provenance(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "observations.csv"
            rows = [{
                "date": "2023-01-06",
                "event_timestamp_utc": "2023-01-06T13:30:00+00:00",
                "indicator_type": "nfp",
                "event": "Non Farm Payrolls",
                "country": "United States",
                "actual": 223000,
                "forecast": 200000,
                "provider": "TradingEconomics",
                "point_in_time": True,
            }]
            count = write_csv(rows, target)
            self.assertEqual(count, 1)
            content = target.read_text(encoding="utf-8")
            self.assertIn("TradingEconomics", content)
            self.assertIn("223000", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
