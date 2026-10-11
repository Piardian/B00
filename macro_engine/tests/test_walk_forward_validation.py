import datetime as dt
import unittest

from calibration.walk_forward_validation import evaluate_rows, run_expanding_walk_forward


class WalkForwardValidationTests(unittest.TestCase):
    def test_evaluate_rows_reports_mean_z(self):
        rows = [
            {"indicator_type": "nfp", "actual": 110.0, "forecast": 100.0},
            {"indicator_type": "nfp", "actual": 90.0, "forecast": 100.0},
        ]
        result = evaluate_rows({"nfp": 10.0}, rows)
        self.assertEqual(result["sample_count"], 2)
        self.assertAlmostEqual(result["mean_z"], 0.0, places=4)
        self.assertAlmostEqual(result["std_z"], 1.0, places=4)
        self.assertAlmostEqual(result["msnr"], 1.0, places=4)

    def test_evaluate_rows_exposes_location_bias(self):
        rows = [
            {"indicator_type": "nfp", "actual": 120.0, "forecast": 100.0},
            {"indicator_type": "nfp", "actual": 120.0, "forecast": 100.0},
        ]
        result = evaluate_rows({"nfp": 10.0}, rows)
        self.assertAlmostEqual(result["mean_z"], 2.0, places=4)
        self.assertAlmostEqual(result["std_z"], 0.0, places=4)
        self.assertAlmostEqual(result["msnr"], 4.0, places=4)

    def test_expanding_walk_forward_creates_one_fold_per_year(self):
        rows = []
        for year in range(2016, 2026):
            for i in range(30):
                rows.append({
                    "date": f"{year}-01-{(i % 28) + 1:02d}",
                    "indicator_type": "nfp",
                    "actual": 100.0 + (i % 3),
                    "forecast": 100.0,
                })
        report = run_expanding_walk_forward(
            rows,
            calibration_start=dt.date(2016, 1, 1),
            first_validation_year=2020,
            last_validation_year=2025,
            min_observations=30,
            required_indicators=("nfp",),
        )
        self.assertEqual(len(report["folds"]), 6)
        self.assertEqual(report["folds"][0]["validation_year"], 2020)
        self.assertEqual(report["folds"][-1]["validation_year"], 2025)
        self.assertEqual(report["folds"][0]["methods"]["mad"]["status"], "ok")
        self.assertEqual(report["folds"][0]["methods"]["std"]["status"], "ok")
        self.assertIsNotNone(report["folds"][0]["delta_std_target_error"])

    def test_evaluate_rows_flags_small_sample_and_unclipped_z(self):
        # 10 observations with large surprise: should NOT be clipped to 4.0 or 10.0
        rows = [
            {"indicator_type": "cpi", "actual": 25.0, "forecast": 0.0}
            for _ in range(10)
        ]
        result = evaluate_rows({"cpi": 1.0}, rows)
        self.assertTrue(result["small_sample"])
        self.assertEqual(result["sample_count"], 10)
        # Raw unclipped Z should be exactly 25.0
        self.assertAlmostEqual(result["mean_z"], 25.0, places=4)
        self.assertIn("cpi", result["by_indicator"])
        self.assertEqual(result["by_indicator"]["cpi"]["sample_count"], 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
