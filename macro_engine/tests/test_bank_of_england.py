import datetime as dt
import unittest
from unittest.mock import patch

from ingestion.bank_of_england import BankOfEnglandDataIngestion


BOE_CSV = """Date,Bank Rate
01 Aug 24,5.00
19 Sep 24,5.00
07 Nov 24,4.75
06 Feb 25,4.50
"""


class BankOfEnglandTests(unittest.TestCase):
    def test_parse_bank_rate_csv(self):
        rows = BankOfEnglandDataIngestion._parse_csv(BOE_CSV)
        self.assertEqual(rows[-1], (dt.date(2025, 2, 6), 4.50))

    def test_intraday_replay_uses_prior_rate_change(self):
        ingestion = BankOfEnglandDataIngestion()
        with patch(
            "ingestion.bank_of_england.urllib.request.urlopen"
        ) as mocked:
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return BOE_CSV.encode("utf-8")

            mocked.return_value = Response()
            result = ingestion.fetch_bank_rate(
                dt.datetime(2025, 2, 6, 10, 0, tzinfo=dt.timezone.utc)
            )

        self.assertEqual(result["value"], 4.75)
        self.assertEqual(result["observation_date"], "2024-11-07")
        self.assertEqual(result["status"], "AVAILABLE")

    def test_source_metadata_is_explicit(self):
        ingestion = BankOfEnglandDataIngestion()
        with unittest.mock.patch(
            "ingestion.bank_of_england.urllib.request.urlopen"
        ) as mocked:
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return BOE_CSV.encode("utf-8")

            mocked.return_value = Response()
            result = ingestion.fetch_bank_rate(
                dt.datetime(2025, 3, 1, tzinfo=dt.timezone.utc)
            )

        self.assertIn("Bank of England official Bank Rate", result["source"])
        self.assertEqual(result["pit_rule"],
                         "latest rate-change date strictly before replay calendar day")

    def test_fetch_2y_yield(self):
        ingestion = BankOfEnglandDataIngestion()
        sample_csv = "DATE,IUDMNZC\n01 Sep 2026,5.20\n02 Sep 2026,5.25\n"
        with unittest.mock.patch("ingestion.bank_of_england.urllib.request.urlopen") as mocked:
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def read(self):
                    return sample_csv.encode("utf-8")

            mocked.return_value = Response()
            res = ingestion.fetch_2y_yield(dt.datetime(2026, 9, 5, tzinfo=dt.timezone.utc))

        self.assertEqual(res["value"], 5.25)
        self.assertEqual(res["prev"], 5.20)
        self.assertEqual(res["status"], "AVAILABLE")
        self.assertFalse(res["fallback_used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
