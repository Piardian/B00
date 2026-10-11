import datetime as dt
import json
import unittest
from unittest.mock import patch

from ingestion.ecb_data import ECBDataIngestion


ECB_PAYLOAD = {
    "dataSets": [
        {
            "series": {
                "0:0:0:0:0:0:0": {
                    "observations": {
                        "0": [3.10],
                        "1": [3.15],
                        "2": [3.20],
                    }
                }
            }
        }
    ],
    "structure": {
        "dimensions": {
            "observation": [
                {
                    "values": [
                        {"id": "2026-09-10"},
                        {"id": "2026-09-11"},
                        {"id": "2026-09-12"},
                    ]
                }
            ]
        }
    },
}


class ECBDataIngestionTests(unittest.TestCase):
    def test_fetch_2y_yield(self):
        ingestion = ECBDataIngestion()
        with patch("ingestion.ecb_data.urllib.request.urlopen") as mocked:
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return json.dumps(ECB_PAYLOAD).encode("utf-8")

            mocked.return_value = Response()
            res = ingestion.fetch_2y_yield(dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc))

        self.assertEqual(res["value"], 3.20)
        self.assertEqual(res["prev"], 3.15)
        self.assertEqual(res["status"], "AVAILABLE")
        self.assertFalse(res["fallback_used"])
        self.assertIn("ECB Data Portal", res["source"])

    def test_fetch_2y_yield_with_cache_fallback(self):
        ingestion = ECBDataIngestion()
        with patch("ingestion.ecb_data.urllib.request.urlopen", side_effect=Exception("Connection timed out")):
            with patch.object(ingestion, "_load_cache", return_value={
                "value": 3.1065,
                "prev": 3.1592,
                "val_5d_ago": 3.2294,
                "source": "ECB Data Portal AAA Government 2Y Spot Rate (B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y)",
                "status": "AVAILABLE",
                "fallback_used": False,
            }):
                res = ingestion.fetch_2y_yield(dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc))
                self.assertEqual(res["value"], 3.1065)
                self.assertEqual(res["status"], "AVAILABLE")
                self.assertFalse(res["fallback_used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
