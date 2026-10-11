import unittest

from calibration.promotion_simulation import evaluate_frozen_holdout


class PromotionIntegrationTests(unittest.TestCase):
    def test_holdout_evaluator_has_explicit_non_promotion_state(self):
        report = evaluate_frozen_holdout([])
        self.assertFalse(report["production_activation"])
        self.assertIn("2025_H2", report["windows"])
        self.assertIn("2026_YTD", report["windows"])
        self.assertEqual(report["windows"]["2025_H2"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(report["windows"]["2026_YTD"]["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
