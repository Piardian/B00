import unittest
from pathlib import Path


class PromotionReadmeTests(unittest.TestCase):
    def test_index_references_all_required_promotion_components(self):
        text = Path(__file__).resolve().parents[1].joinpath("calibration", "README_PROMOTION.md").read_text(encoding="utf-8")
        for token in (
            "promotion_simulation.py",
            "promotion_runner.py",
            "promote_main.py",
            "PROMOTION_POLICY.md",
            "PROMOTION_RUNBOOK.md",
            "HOLDOUT_DATA_CONTRACT.md",
        ):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
