import unittest
from pathlib import Path


class PromotionReadinessTests(unittest.TestCase):
    def test_snapshot_explicitly_blocks_missing_2026_data(self):
        text = Path(__file__).resolve().parents[1].joinpath("calibration", "PROMOTION_READINESS.md").read_text(encoding="utf-8")
        self.assertIn("2026_YTD", text)
        self.assertIn("production activation: `false`", text)
        self.assertIn("complete 2026 holdout", text)
        self.assertIn("complete historical SMC trade ledger", text)


if __name__ == "__main__":
    unittest.main()
