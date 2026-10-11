import tempfile
import unittest
from pathlib import Path

from calibration.promotion_ci_check import validate_evidence_template, validate_report


class PromotionCICheckTests(unittest.TestCase):
    def test_template_passes_contract(self):
        path = Path(__file__).resolve().parents[1].joinpath("calibration", "PROMOTION_EVIDENCE_TEMPLATE.json")
        validate_evidence_template(path)

    def test_report_contract_rejects_activation(self):
        report = {
            "production_activation": False,
            "frozen_parameters": {"mad_threshold_abs_z": 1.0},
            "holdout_coverage": {"windows": {"2025_H2": {"status": "INSUFFICIENT_DATA"}, "2026_YTD": {"status": "INSUFFICIENT_DATA"}}},
        }
        validate_report(report)
        report["production_activation"] = True
        with self.assertRaises(AssertionError):
            validate_report(report)

    def test_missing_window_status_is_rejected(self):
        report = {
            "production_activation": False,
            "frozen_parameters": {"mad_threshold_abs_z": 1.0},
            "holdout_coverage": {"windows": {"2025_H2": {"status": "PASS_DATA"}, "2026_YTD": {}}},
        }
        with self.assertRaises(AssertionError):
            validate_report(report)


if __name__ == "__main__":
    unittest.main()
