import datetime as dt
import tempfile
import unittest
from pathlib import Path

from calibration.historical_event_research import (
    _cluster_observations,
    _outcome_path,
    build_historical_event_dataset,
)

UTC = dt.timezone.utc


class TestHistoricalEventResearch(unittest.TestCase):
    def test_outcome_path_stops_at_exact_horizon(self):
        event = dt.datetime(2024, 1, 2, 13, 30, tzinfo=UTC)
        bars = {}
        closes = [1.1900, 1.1800, 1.1700, 1.1600]
        for i, close in enumerate(closes):
            t = event + dt.timedelta(minutes=30 * i)
            bars[t] = {"open": 1.2000 if i == 0 else closes[i-1], "high": max(1.2000, close), "low": min(1.2000, close), "close": close}

        result = _outcome_path(bars, event, 30, 30)
        self.assertIsNotNone(result)
        usd_return, _, _, observed = result
        self.assertAlmostEqual(usd_return, (1.2000 - 1.1900) / 1.2000 * 10000.0, places=6)
        self.assertEqual(observed, 1)

        result_60 = _outcome_path(bars, event, 30, 60)
        self.assertIsNotNone(result_60)
        usd_return_60, _, _, observed_60 = result_60
        self.assertAlmostEqual(usd_return_60, (1.2000 - 1.1800) / 1.2000 * 10000.0, places=6)
        self.assertEqual(observed_60, 2)

    def test_simultaneous_observations_cluster_by_reconstructed_event_time(self):
        rows = [
            {"indicator_type": "nfp", "date": "2024-01-04", "event_timestamp_utc": "2024-01-04T20:30:00+00:00"},
            {"indicator_type": "unemployment", "date": "2024-01-04", "event_timestamp_utc": "2024-01-04T20:30:00+00:00"},
            {"indicator_type": "cpi", "date": "2024-01-10", "event_timestamp_utc": "2024-01-10T15:30:00+00:00"},
        ]
        clusters = _cluster_observations(rows)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(len(clusters[0]), 2)
        self.assertEqual(len(clusters[1]), 1)

    def test_dataset_uses_exact_30m_close(self):
        csv_text = """date,event_timestamp_utc,indicator_type,event,country,actual,forecast,previous,revision,unit,importance,calendar_id,ticker,source,source_url,provider,provider_endpoint,point_in_time\n2019-01-03,2019-01-03T20:30:00+00:00,nfp,NFP,United States,150000,100000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n2020-01-03,2020-01-03T20:30:00+00:00,nfp,NFP,United States,200000,50000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n2021-01-08,2021-01-08T20:30:00+00:00,nfp,NFP,United States,180000,80000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "obs.csv"
            path.write_text(csv_text, encoding="utf-8")
            event = dt.datetime(2021, 1, 9, 13, 30, tzinfo=UTC)
            bars = {}
            # 240 minutes pre-event: 8 M30 bars plus one preceding bar for true-range calculation.
            for i in range(-9, 0):
                t = event + dt.timedelta(minutes=30 * i)
                p = 1.2100 + i * 0.0001
                bars[t] = {"open": p, "high": p + 0.0004, "low": p - 0.0004, "close": p + 0.00005}
            # Exact event-to-horizon bars. Event-bar CLOSE is +30m, next bar CLOSE is +60m.
            closes = [1.1900, 1.1850, 1.1800, 1.1750, 1.1700, 1.1680, 1.1660, 1.1650]
            for i, close in enumerate(closes):
                t = event + dt.timedelta(minutes=30 * i)
                bars[t] = {"open": 1.2000 if i == 0 else closes[i-1] + 0.0002, "high": max(1.2000, close) + 0.0002, "low": min(1.2000, close) - 0.0002, "close": close}

            dataset, diagnostics = build_historical_event_dataset(
                path,
                bars,
                timeframe_minutes=30,
                test_years=(2021,),
                horizons=(30, 60, 240),
                pre_windows=(30, 60, 240),
                min_observations=2,
            )
            self.assertEqual(diagnostics["event_clusters_total"], 1)
            self.assertEqual(diagnostics["event_clusters_matched"], 1)
            self.assertEqual(len(dataset), 1)

            row = dataset[0]
            self.assertAlmostEqual(row["post_30m_usd_bps"], (1.2000 - 1.1900) / 1.2000 * 10000.0, places=4)
            self.assertAlmostEqual(row["post_60m_usd_bps"], (1.2000 - 1.1850) / 1.2000 * 10000.0, places=4)
            self.assertEqual(row["post_30m_observed_bars"], 1)
            self.assertEqual(row["post_60m_observed_bars"], 2)


if __name__ == "__main__":
    unittest.main()
