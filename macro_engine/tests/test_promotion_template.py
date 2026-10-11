import json
import unittest
from pathlib import Path


class PromotionTemplateTests(unittest.TestCase):
    def test_template_is_explicitly_blocked_until_evidence_exists(self):
        path = Path(__file__).resolve().parents[1].joinpath("calibration", "PROMOTION_EVIDENCE_TEMPLATE.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(data["production_activation"])
        self.assertFalse(data["promotion_ready"])
        self.assertEqual(data["decision"], "HOLDOUT_INCOMPLETE")
        self.assertEqual(data["holdout"]["2025_H2"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(data["holdout"]["2026_YTD"]["status"], "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
