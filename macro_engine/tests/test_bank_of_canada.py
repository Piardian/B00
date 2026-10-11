import datetime as dt
import json
import unittest
from unittest.mock import patch

from ingestion.bank_of_canada import BankOfCanadaDataIngestion


PAYLOAD = {
    "observations": [
        {"d": "2025-01-28", "V39079": {"v": "3.25"}},
        {"d": "2025-03-12", "V39079": {"v": "2.75"}},
        {"d": "2025-04-16", "V39079": {"v": "2.75"}},
    ]
}


class BankOfCanadaTests(unittest.TestCase):
    def test_extract_rows(self):
        rows = BankOfCanadaDataIngestion._extract_rows(PAYLOAD)
        self.assertEqual(rows[-1], (dt.date(2025, 4, 16), 2.75))

    def test_intraday_replay_uses_prior_daily_policy_value(self):
        ingestion = BankOfCanadaDataIngestion()
        with patch("ingestion.bank_of_canada.urllib.request.urlopen") as mocked:
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return json.dumps(PAYLOAD).encode("utf-8")

            mocked.return_value = Response()
            result = ingestion.fetch_policy_rate(
                dt.datetime(2025, 4, 16, 10, tzinfo=dt.timezone.utc)
            )

        self.assertEqual(result["value"], 2.75)
        self.assertEqual(result["observation_date"], "2025-03-12")

    def test_source_metadata_is_explicit(self):
        ingestion = BankOfCanadaDataIngestion()
        with patch("ingestion.bank_of_canada.urllib.request.urlopen") as mocked:
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return json.dumps(PAYLOAD).encode("utf-8")

            mocked.return_value = Response()
            result = ingestion.fetch_policy_rate(
                dt.datetime(2025, 5, 1, tzinfo=dt.timezone.utc)
            )

        self.assertEqual(result["status"], "AVAILABLE")
        self.assertIn("Bank of Canada official", result["source"])

    def test_fetch_2y_yield(self):
        ingestion = BankOfCanadaDataIngestion()
        yield_payload = {
            "observations": [
                {"d": "2025-04-10", "BD.CDN.2YR.DQ.YLD": {"v": "3.10"}},
                {"d": "2025-04-15", "BD.CDN.2YR.DQ.YLD": {"v": "3.15"}},
                {"d": "2025-04-16", "BD.CDN.2YR.DQ.YLD": {"v": "3.20"}},
            ]
        }
        with patch("ingestion.bank_of_canada.urllib.request.urlopen") as mocked:
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return json.dumps(yield_payload).encode("utf-8")

            mocked.return_value = Response()
            res = ingestion.fetch_2y_yield(dt.datetime(2025, 4, 16, tzinfo=dt.timezone.utc))

        self.assertEqual(res["value"], 3.20)
        self.assertEqual(res["prev"], 3.15)
        self.assertEqual(res["status"], "AVAILABLE")
        self.assertFalse(res["fallback_used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
