import json
import tempfile
import unittest
from pathlib import Path

from calibration.promotion_runner import build_promotion_report


class PromotionRunnerTests(unittest.TestCase):
    def test_holdout_is_incomplete_when_2026_is_missing(self):
        rows = [
            {
                "event_time_utc": "2025-07-03T12:00:00+00:00",
                "cluster_signal": 1,
                "dominant_z_mad": 1.4,
                "post_30m_usd_bps": 20.0,
            }
        ]
        report = build_promotion_report(rows)
        self.assertFalse(report["promotion_ready"])
        self.assertEqual(report["decision"], "HOLDOUT_INCOMPLETE")
        self.assertEqual(report["holdout_coverage"]["windows"]["2025_H2"]["status"], "PASS_DATA")
        self.assertEqual(report["holdout_coverage"]["windows"]["2026_YTD"]["status"], "INSUFFICIENT_DATA")
        self.assertFalse(report["production_activation"])

    def test_runner_accepts_complete_holdout_and_smc_ledger(self):
        holdout = [
            {
                "event_time_utc": "2025-08-01T12:00:00+00:00",
                "cluster_signal": 1,
                "dominant_z_mad": 1.4,
                "post_30m_usd_bps": 20.0,
            },
            {
                "event_time_utc": "2026-02-01T12:00:00+00:00",
                "cluster_signal": -1,
                "dominant_z_mad": -1.2,
                "post_30m_usd_bps": 15.0,
            },
        ]
        smc = [
            {"smc_direction": "LONG", "macro_direction": "LONG", "dominant_z_mad": 1.5, "realized_r": 1.5},
            {"smc_direction": "SHORT", "macro_direction": "LONG", "dominant_z_mad": 2.0, "realized_r": -1.0},
        ]
        report = build_promotion_report(holdout, smc_trades=smc)
        self.assertTrue(report["promotion_ready"])
        self.assertEqual(report["decision"], "REQUIRES_EXECUTION_VALIDATION")
        self.assertEqual(report["incremental_smc_status"], "PASS_DATA")
        self.assertEqual(report["incremental_smc_alpha"]["smc_plus_macro"]["trade_count"], 1)
        self.assertFalse(report["production_activation"])

    def test_runner_schema_is_json_serializable(self):
        report = build_promotion_report([])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "promotion_report.json"
            path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
