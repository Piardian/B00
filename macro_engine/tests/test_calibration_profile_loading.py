import tempfile
import unittest
from pathlib import Path

from data_quality import DataUnavailableError
from preprocessing.metrics import MacroMetricsCalculator


class CalibrationProfileLoadingTests(unittest.TestCase):
    def test_missing_profile_fails_closed_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            with self.assertRaises(DataUnavailableError) as ctx:
                MacroMetricsCalculator.from_calibration_profile(path)
            self.assertIn("Calibration profile unavailable", str(ctx.exception))

    def test_default_fallback_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            calculator = MacroMetricsCalculator.from_calibration_profile(
                path, allow_default_fallback=True
            )
            self.assertEqual(calculator.surprise_sigmas, calculator.DEFAULT_SURPRISE_SIGMAS)

    def test_existing_profile_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text('{"sigmas":{"cpi":0.125,"nfp":85000.0}}', encoding="utf-8")
            calculator = MacroMetricsCalculator.from_calibration_profile(path)
            self.assertEqual(calculator.surprise_sigmas["cpi"], 0.125)
            self.assertEqual(calculator.surprise_sigmas["nfp"], 85000.0)


if __name__ == "__main__":
    unittest.main()
