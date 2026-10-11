import unittest
from pathlib import Path


class PromotionChecklistTests(unittest.TestCase):
    def test_checklist_has_all_independent_evidence_requirements(self):
        text = Path(__file__).resolve().parents[1].joinpath("calibration", "PROMOTION_CHECKLIST.md").read_text(encoding="utf-8")
        for token in (
            "2025 H2 holdout",
            "2026 YTD holdout",
            "exact +30m, +60m and +240m outcomes",
            "MAD threshold remains exactly `1.0`",
            "T0 market execution stress",
            "T5 retest/limit execution stress",
            "10/30/50 bps scenarios",
            "Same-bar SL/TP ambiguity is fail-closed",
            "Complete SMC historical trade ledger",
            "SMC baseline and SMC+macro",
        ):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
