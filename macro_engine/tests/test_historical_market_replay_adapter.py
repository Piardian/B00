import datetime as dt
import unittest
from unittest.mock import patch

import pandas as pd

from calibration.historical_market_replay import HistoricalMarketReplayIngestion


class HistoricalMarketReplayAdapterTests(unittest.TestCase):
    def test_payload_uses_only_historical_closes(self):
        as_of = dt.datetime(2023, 10, 15, 12, tzinfo=dt.timezone.utc)
        payload = HistoricalMarketReplayIngestion._build_payload(
            "DXY",
            [100.0 + (i * 0.25) for i in range(60)],
            as_of,
            "test",
        )
        self.assertEqual(payload["value"], 114.75)
        self.assertEqual(payload["prev"], 114.5)
        self.assertEqual(payload["snapshot_timestamp"], as_of.isoformat())
        self.assertEqual(payload["source"], "test")

    @patch("calibration.historical_market_replay.mt5")
    def test_mt5_replay_excludes_unfinished_current_day(self, mock_mt5):
        as_of = dt.datetime(2023, 10, 15, 12, tzinfo=dt.timezone.utc)
        mock_mt5.TIMEFRAME_D1 = 1
        mock_mt5.copy_rates_from.return_value = [
            {"time": int(dt.datetime(2023, 10, 13, tzinfo=dt.timezone.utc).timestamp()), "close": 105.0},
            {"time": int(dt.datetime(2023, 10, 14, tzinfo=dt.timezone.utc).timestamp()), "close": 110.0},
            {"time": int(dt.datetime(2023, 10, 15, tzinfo=dt.timezone.utc).timestamp()), "close": 120.0},
        ]

        ingestion = HistoricalMarketReplayIngestion()
        with patch.object(ingestion, "_check_connection", return_value=True),              patch.object(ingestion, "find_broker_symbol", return_value="DXY"):
            payload = ingestion._from_mt5("DXY", as_of, 10)

        self.assertEqual(payload["value"], 110.0)
        self.assertEqual(payload["prev"], 105.0)

    @patch("calibration.historical_market_replay.yf.Ticker")
    def test_yahoo_replay_excludes_unfinished_current_day(self, mock_ticker):
        as_of = dt.datetime(2023, 10, 15, 12, tzinfo=dt.timezone.utc)
        index = pd.DatetimeIndex(
            [
                dt.datetime(2023, 10, 13, 0, tzinfo=dt.timezone.utc),
                dt.datetime(2023, 10, 14, 0, tzinfo=dt.timezone.utc),
                dt.datetime(2023, 10, 15, 0, tzinfo=dt.timezone.utc),
            ]
        )
        mock_ticker.return_value.history.return_value = pd.DataFrame(
            {"Close": [105.0, 110.0, 120.0]},
            index=index,
        )

        payload = HistoricalMarketReplayIngestion._from_yfinance("DXY", as_of, 10)
        self.assertEqual(payload["value"], 110.0)

    def test_payload_rejects_implausible_dxy(self):
        with self.assertRaises(ValueError):
            HistoricalMarketReplayIngestion._build_payload(
                "DXY",
                [10.0, 11.0],
                dt.datetime(2023, 10, 15, tzinfo=dt.timezone.utc),
                "test",
            )


if __name__ == "__main__":
    unittest.main()
