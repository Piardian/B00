import json
import tempfile
import unittest
from pathlib import Path

from calibration.promote_main import run


class PromoteMainTests(unittest.TestCase):
    def test_run_writes_deterministic_report(self):
        holdout = {
            "records": [
                {
                    "event_time_utc": "2025-08-01T12:00:00+00:00",
                    "cluster_signal": 1,
                    "dominant_z_mad": 1.4,
                    "post_30m_usd_bps": 20.0,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            holdout_path = root / "holdout.json"
            output_path = root / "report.json"
            holdout_path.write_text(json.dumps(holdout), encoding="utf-8")
            report = run(holdout_path, output_path=output_path)
            self.assertEqual(report["decision"], "HOLDOUT_INCOMPLETE")
            self.assertTrue(output_path.exists())
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["decision"], "HOLDOUT_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
