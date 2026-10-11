import unittest
from pathlib import Path

from calibration.verify_promotion_evidence import main


class VerifyPromotionEvidenceTests(unittest.TestCase):
    def test_verifier_module_exists(self):
        path = Path(__file__).resolve().parents[1].joinpath("calibration", "verify_promotion_evidence.py")
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
