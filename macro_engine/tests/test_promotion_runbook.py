import unittest
from pathlib import Path


class PromotionRunbookTests(unittest.TestCase):
    def test_runbook_freezes_threshold_and_blocks_missing_inputs(self):
        text = Path(__file__).resolve().parents[1].joinpath("calibration", "PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")
        self.assertIn("abs(dominant_z_mad) >= 1.0", text)
        self.assertIn("HOLDOUT_INCOMPLETE", text)
        self.assertIn("CALM_10BP", text)
        self.assertIn("NEWS_30BP", text)
        self.assertIn("NEWS_50BP", text)
        self.assertIn("complete apples-to-apples SMC baseline vs SMC+macro comparison", text)


if __name__ == "__main__":
    unittest.main()
