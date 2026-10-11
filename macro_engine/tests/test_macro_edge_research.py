import datetime as dt
import tempfile
import unittest
from pathlib import Path

from calibration.macro_edge_research import build_macro_edge_dataset, summarize_macro_edge

UTC = dt.timezone.utc


class TestMacroEdgeResearch(unittest.TestCase):
    def _bars(self, event: dt.datetime, base: float, closes: list[float], interval: int = 5):
        bars = {}
        for i, close in enumerate(closes):
            t = event + dt.timedelta(minutes=interval * i)
            bars[t] = {
                "open": base if i == 0 else close,
                "high": max(base, close),
                "low": min(base, close),
                "close": close,
            }
        return bars

    def test_event_level_dataset_clusters_and_uses_exact_horizon(self):
        csv_text = """date,event_timestamp_utc,indicator_type,event,country,actual,forecast,previous,revision,unit,importance,calendar_id,ticker,source,source_url,provider,provider_endpoint,point_in_time\n2019-01-03,2019-01-03T13:30:00+00:00,nfp,NFP,United States,150000,100000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n2020-01-03,2020-01-03T13:30:00+00:00,nfp,NFP,United States,200000,50000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n2021-01-08,2021-01-08T13:30:00+00:00,nfp,NFP,United States,180000,80000,0,,,,,,,,ForexFactory,,ForexFactory,,True\n2021-01-08,2021-01-08T13:30:00+00:00,unemployment,Unemployment Rate,United States,4.8,5.0,5.0,,,,,,,,ForexFactory,,ForexFactory,,True\n"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "obs.csv"
            path.write_text(csv_text, encoding="utf-8")

            event = dt.datetime(2021, 1, 8, 13, 30, tzinfo=UTC)
            bars = {
                "XAUUSD": self._bars(event, 2000.0, [1990.0, 1980.0, 1970.0, 1960.0]),
                "EURUSD": self._bars(event, 1.2000, [1.1990, 1.1980, 1.1970, 1.1960]),
            }

            report = build_macro_edge_dataset(
                path,
                bars,
                timeframe_minutes=5,
                years=(2021,),
                horizons=(5, 15),
                min_observations=1,
            )

            self.assertEqual(report["diagnostics"]["event_clusters_total"], 1)
            self.assertEqual(report["diagnostics"]["event_clusters_matched"], 1)
            self.assertEqual(len(report["records"]), 1)
            row = report["records"][0]
            self.assertAlmostEqual(row["XAUUSD_return_5m_bps"], -50.0, places=6)
            self.assertAlmostEqual(row["XAUUSD_return_15m_bps"], -150.0, places=6)
            self.assertGreaterEqual(row["cluster_coherence"], 0.99)

    def test_summary_is_research_only_and_cost_adjusted(self):
        dataset = {
            "metadata": {"expected_asset_direction": {"EURUSD": -1.0}},
            "records": [
                {"EURUSD_return_5m_bps": -20.0, "EURUSD_directional_hit_5m": True, "cluster_signal_usd": 1},
                {"EURUSD_return_5m_bps": 10.0, "EURUSD_directional_hit_5m": False, "cluster_signal_usd": 1},
            ],
        }
        summary = summarize_macro_edge(dataset, horizons=(5,), costs_bps={"EURUSD": 5.0})
        h = summary["assets"]["EURUSD"]["horizons"]["5"]
        self.assertEqual(h["sample_count"], 2)
        self.assertEqual(h["directional_hit_rate_pct"], 50.0)
        self.assertEqual(h["mean_net_bps"], 0.0)
        self.assertFalse(summary["methodology"]["threshold_optimization"])


if __name__ == "__main__":
    unittest.main()
