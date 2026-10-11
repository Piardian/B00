import unittest
from pathlib import Path


class PromotionPolicyTests(unittest.TestCase):
    def test_policy_is_non_optimizing_and_non_activating(self):
        text = Path(__file__).resolve().parents[1].joinpath("calibration", "PROMOTION_POLICY.md").read_text(encoding="utf-8")
        self.assertIn("abs(dominant_z_mad) >= 1.0", text)
        self.assertIn("Both `2025_H2` and `2026_YTD`", text)
        self.assertIn("CALM_10BP", text)
        self.assertIn("NEWS_30BP", text)
        self.assertIn("NEWS_50BP", text)
        self.assertIn("production_activation` remains `false`", text)


if __name__ == "__main__":
    unittest.main()
