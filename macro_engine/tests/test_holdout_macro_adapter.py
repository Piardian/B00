import datetime as dt
import unittest
from pathlib import Path

from calibration.holdout_macro_adapter import (
    FROZEN_CALIBRATION_CUTOFF,
    adapt_holdout_observations,
    compute_frozen_sigmas,
    validate_observation_row,
)
from calibration.run_promotion_readiness import load_records, main as run_readiness_main
from calibration.promotion_simulation import evaluate_frozen_holdout

UTC = dt.timezone.utc


class HoldoutMacroAdapterTests(unittest.TestCase):
    def test_pit_validation_accepts_valid_row(self):
        row = {
            "date": "2025-07-03",
            "event_timestamp_utc": "2025-07-03T12:30:00+00:00",
            "indicator_type": "nfp",
            "event": "Non-Farm Employment Change",
            "actual": "147000.0",
            "forecast": "111000.0",
            "previous": "144000.0",
            "source": "ForexFactory / BLS",
            "source_url": "https://www.bls.gov",
            "point_in_time": "True",
        }
        valid, reason = validate_observation_row(row)
        self.assertTrue(valid)
        self.assertIsNone(reason)

    def test_pit_validation_rejects_non_pit_or_missing_provenance(self):
        # Case 1: point_in_time is False
        row1 = {
            "event_timestamp_utc": "2025-07-03T12:30:00+00:00",
            "indicator_type": "nfp",
            "actual": "147000.0",
            "forecast": "111000.0",
            "source": "BLS",
            "source_url": "https://www.bls.gov",
            "point_in_time": "False",
        }
        valid, reason = validate_observation_row(row1)
        self.assertFalse(valid)
        self.assertIn("point_in_time", reason)

        # Case 2: missing source_url
        row2 = {
            "event_timestamp_utc": "2025-07-03T12:30:00+00:00",
            "indicator_type": "nfp",
            "actual": "147000.0",
            "forecast": "111000.0",
            "source": "BLS",
            "source_url": "",
            "point_in_time": "True",
        }
        valid, reason = validate_observation_row(row2)
        self.assertFalse(valid)
        self.assertIn("missing required field", reason)

        # Case 3: unrecognized indicator
        row3 = {
            "event_timestamp_utc": "2025-07-03T12:30:00+00:00",
            "indicator_type": "random_sentiment_index",
            "actual": "50.0",
            "forecast": "48.0",
            "source": "Blog",
            "source_url": "https://example.com",
            "point_in_time": "True",
        }
        valid, reason = validate_observation_row(row3)
        self.assertFalse(valid)
        self.assertIn("unrecognized indicator_type", reason)

    def test_frozen_calibration_cutoff_is_july_2025(self):
        self.assertEqual(FROZEN_CALIBRATION_CUTOFF, dt.datetime(2025, 7, 1, 0, 0, 0, tzinfo=UTC))

    def test_adapt_holdout_observations_computes_exact_horizons(self):
        event_time = dt.datetime(2025, 7, 3, 12, 30, tzinfo=UTC)
        rows = [
            {
                "date": "2025-07-03",
                "event_timestamp_utc": event_time.isoformat(),
                "indicator_type": "unemployment",
                "actual": 4.1,
                "forecast": 4.3,
                "previous": 4.2,
                "source": "BLS",
                "source_url": "https://www.bls.gov",
                "point_in_time": True,
            }
        ]
        mad_sigmas = {"unemployment": 0.1483}
        std_sigmas = {"unemployment": 0.6298}
        # Synthetic bar map for testing exact horizon
        # event bar open = 1.2000
        # +30m bar open (at 12:30) has close = 1.1950 -> return = (1.2000 - 1.1950)/1.2000 * 10000 = +41.67 bps
        bar_map = {
            dt.datetime(2025, 7, 3, 12, 30, tzinfo=UTC): {
                "open": 1.2000,
                "high": 1.2010,
                "low": 1.1940,
                "close": 1.1950,
            },
            dt.datetime(2025, 7, 3, 13, 0, tzinfo=UTC): {
                "open": 1.1950,
                "high": 1.1970,
                "low": 1.1930,
                "close": 1.1960,
            },
            dt.datetime(2025, 7, 3, 16, 0, tzinfo=UTC): {
                "open": 1.1940,
                "high": 1.1980,
                "low": 1.1920,
                "close": 1.1930,
            },
        }
        records = adapt_holdout_observations(
            rows,
            mad_sigmas,
            std_sigmas,
            bar_map,
            timeframe_minutes=30,
            horizons=[30],
            pre_windows=[],
        )
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["indicators"], "unemployment")
        # unemployment surprise is -0.2 (lower is bullish USD), direction=-1 -> signed surprise = +0.2
        # Z_MAD = +0.2 / 0.1483 = 1.3486
        self.assertGreaterEqual(rec["dominant_z_mad"], 1.0)
        self.assertTrue(rec["dominant_mad_actionable"])
        self.assertAlmostEqual(rec["post_30m_usd_bps"], 41.6667, places=2)
        self.assertTrue(rec["post_30m_hit"])

    def test_run_readiness_partial_holdout_marked_insufficient(self):
        records, holdout_info = load_records()
        self.assertTrue(holdout_info["integrated"])
        self.assertGreater(len(records), 196)

        # 4 clusters in 2025_H2 is less than 15 required -> status must be INSUFFICIENT_DATA
        holdout = evaluate_frozen_holdout(records, min_window_rows=15)
        self.assertEqual(holdout["windows"]["2025_H2"]["status"], "INSUFFICIENT_DATA")
        self.assertTrue(holdout["windows"]["2025_H2"]["partial_data"])
        self.assertEqual(holdout["windows"]["2026_YTD"]["status"], "INSUFFICIENT_DATA")
        self.assertFalse(holdout["production_activation"])


if __name__ == "__main__":
    unittest.main()
