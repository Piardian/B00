import unittest
from pathlib import Path


class HoldoutDataContractTests(unittest.TestCase):
    def test_contract_contains_required_window_and_fields(self):
        text = Path(__file__).resolve().parents[1].joinpath("calibration", "HOLDOUT_DATA_CONTRACT.md").read_text(encoding="utf-8")
        for token in (
            "2025_H2",
            "2026_YTD",
            "event_time_utc",
            "cluster_signal",
            "dominant_z_mad",
            "post_30m_usd_bps",
            "post_60m_usd_bps",
            "post_240m_usd_bps",
            "abs(dominant_z_mad) >= 1.0",
            "no holdout recalibration",
        ):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
