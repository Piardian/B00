import datetime as dt
import tempfile
import unittest
from pathlib import Path

from calibration.market_response_validation import (
    calculate_usd_returns,
    classify_bucket,
    rank_data,
    resolve_event_datetime,
    spearman_rank_ic,
)
from calibration.market_response_validation_v2 import (
    audit_event_timestamp,
    build_records,
    parse_observation_event_utc,
)


class TestMarketResponseValidation(unittest.TestCase):
    def test_rank_data(self):
        self.assertEqual(rank_data([]), [])
        self.assertEqual(rank_data([42.0]), [1.0])
        self.assertEqual(rank_data([10.0, 20.0, 30.0]), [1.0, 2.0, 3.0])
        self.assertEqual(rank_data([30.0, 20.0, 10.0]), [3.0, 2.0, 1.0])
        self.assertEqual(rank_data([10.0, 20.0, 20.0, 40.0]), [1.0, 2.5, 2.5, 4.0])

    def test_spearman_rank_ic(self):
        self.assertEqual(spearman_rank_ic([], []), 0.0)
        self.assertEqual(spearman_rank_ic([1.0], [2.0]), 0.0)
        self.assertAlmostEqual(spearman_rank_ic([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(spearman_rank_ic([1, 2, 3, 4], [40, 30, 20, 10]), -1.0)
        self.assertEqual(spearman_rank_ic([1, 2, 3], [5, 5, 5]), 0.0)

    def test_release_timestamp_is_dst_safe(self):
        # 2024-02-02 NFP: 08:30 EST = 13:30 UTC.
        row = {
            "indicator_type": "nfp",
            "date": "2024-02-01",
            "event_timestamp_utc": "2024-02-01T20:30:00+00:00",
        }
        event = parse_observation_event_utc(row)
        self.assertEqual(event, dt.datetime(2024, 2, 2, 13, 30, tzinfo=dt.timezone.utc))
        self.assertEqual(resolve_event_datetime(row), (dt.date(2024, 2, 2), 13))
        audit = audit_event_timestamp(row)
        self.assertFalse(audit["timestamp_is_close"])

        # 2024-07-05 NFP: 08:30 EDT = 12:30 UTC.
        summer = {
            "indicator_type": "nfp",
            "date": "2024-07-05",
            "event_timestamp_utc": "2024-07-05T12:30:00+00:00",
        }
        self.assertEqual(
            parse_observation_event_utc(summer),
            dt.datetime(2024, 7, 5, 12, 30, tzinfo=dt.timezone.utc),
        )

    def test_pmi_timestamp(self):
        row = {
            "indicator_type": "pmi",
            "date": "2024-02-01",
            "event_timestamp_utc": "2024-02-01T15:00:00+00:00",
        }
        self.assertEqual(
            parse_observation_event_utc(row),
            dt.datetime(2024, 2, 1, 15, 0, tzinfo=dt.timezone.utc),
        )

    def test_calculate_usd_returns(self):
        ret = calculate_usd_returns(1.1000, 1.0900)
        self.assertAlmostEqual(ret, (0.0100 / 1.1000) * 10000.0, places=3)
        self.assertLess(calculate_usd_returns(1.1000, 1.1100), 0.0)

    def test_classify_bucket(self):
        self.assertEqual(classify_bucket(-2.5), "1_strong_neg")
        self.assertEqual(classify_bucket(-1.5), "2_mod_neg")
        self.assertEqual(classify_bucket(0.0), "3_in_line")
        self.assertEqual(classify_bucket(1.5), "4_mod_pos")
        self.assertEqual(classify_bucket(2.5), "5_strong_pos")

    def test_build_records_uses_exact_m5_event_time(self):
        csv_content = """date,event_timestamp_utc,indicator_type,event,country,actual,forecast,previous,revision,unit,importance,calendar_id,ticker,source,source_url,provider,provider_endpoint,point_in_time
2021-01-07,2021-01-07T20:30:00+00:00,nfp,Non-Farm Employment Change,United States,250000.0,150000.0,140000.0,,persons,High,,,,ForexFactory,,ForexFactory,,True
2021-02-04,2021-02-04T20:30:00+00:00,nfp,Non-Farm Employment Change,United States,80000.0,180000.0,150000.0,,persons,High,,,,ForexFactory,,ForexFactory,,True
2022-01-06,2022-01-06T20:30:00+00:00,nfp,Non-Farm Employment Change,United States,300000.0,200000.0,180000.0,,persons,High,,,,ForexFactory,,ForexFactory,,True
2022-02-03,2022-02-03T20:30:00+00:00,nfp,Non-Farm Employment Change,United States,100000.0,200000.0,180000.0,,persons,High,,,,ForexFactory,,ForexFactory,,True
"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "obs.csv"
            path.write_text(csv_content, encoding="utf-8")

            def bars_for(start):
                result = {}
                for minutes in [0, 5, 15, 30, 60, 240]:
                    t = start + dt.timedelta(minutes=minutes)
                    result[t] = {"open": 1.2000, "high": 1.2010, "low": 1.1990, "close": 1.2000 - minutes / 100000.0}
                return result

            bars = {}
            bars.update(bars_for(dt.datetime(2022, 1, 7, 13, 30, tzinfo=dt.timezone.utc)))
            bars.update(bars_for(dt.datetime(2022, 2, 4, 13, 30, tzinfo=dt.timezone.utc)))

            records, diagnostics = build_records(path, bars, test_years=(2022,), min_observations=2)
            self.assertEqual(len(records), 2)
            self.assertEqual(diagnostics["missing_event_bar"], 0)
            self.assertEqual(records[0]["event_timestamp_utc"], "2022-01-07T13:30:00+00:00")
            self.assertIn("ret_30m", records[0])
            self.assertIn("ret_240m", records[0])


if __name__ == "__main__":
    unittest.main()
