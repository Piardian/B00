import datetime as dt
import tempfile
import unittest
from pathlib import Path

from calibration.market_response_validation_v3 import build_records

UTC = dt.timezone.utc


class TestMarketResponseValidationV3(unittest.TestCase):
    def test_30m_is_event_bar_close_not_next_bar_close(self):
        csv_text = """date,event_timestamp_utc,indicator_type,event,country,actual,forecast,previous,revision,unit,importance,calendar_id,ticker,source,source_url,provider,provider_endpoint,point_in_time\n2019-01-03,2019-01-03T20:30:00+00:00,nfp,NFP,United States,150000,100000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n2020-01-03,2020-01-03T20:30:00+00:00,nfp,NFP,United States,200000,50000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n2021-01-08,2021-01-08T20:30:00+00:00,nfp,NFP,United States,180000,80000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "obs.csv"
            path.write_text(csv_text, encoding="utf-8")
            event = dt.datetime(2021, 1, 9, 13, 30, tzinfo=UTC)
            bars = {}
            closes = [1.1900, 1.1850, 1.1800, 1.1750, 1.1700, 1.1680, 1.1660, 1.1650]
            for i, close in enumerate(closes):
                t = event + dt.timedelta(minutes=30 * i)
                bars[t] = {"open": 1.2000 if i == 0 else closes[i-1], "high": max(1.2000, close) + 0.0002, "low": min(1.2000, close) - 0.0002, "close": close}

            records, diagnostics = build_records(
                path,
                bars,
                timeframe_minutes=30,
                test_years=(2021,),
                min_observations=2,
                horizons=(30, 60, 240),
            )

            self.assertEqual(diagnostics["matched"], 1)
            self.assertEqual(len(records), 1)
            row = records[0]
            self.assertAlmostEqual(row["ret_30m"], (1.2000 - 1.1900) / 1.2000 * 10000.0, places=6)
            self.assertAlmostEqual(row["ret_60m"], (1.2000 - 1.1850) / 1.2000 * 10000.0, places=6)
            self.assertAlmostEqual(row["ret_240m"], (1.2000 - 1.1650) / 1.2000 * 10000.0, places=6)


if __name__ == "__main__":
    unittest.main()
