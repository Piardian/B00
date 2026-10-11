import datetime as dt
import unittest

from core.deterministic_controls import DataUnavailableError
from preprocessing.metrics import MacroMetricsCalculator


class FredFreshnessContractTests(unittest.TestCase):
    def test_dfii10_accepts_normal_weekly_observation_gap(self):
        calc = MacroMetricsCalculator()
        fred = {
            "data_quality": {
                "observation_dates": {"DFII10": "2024-09-27"}
            }
        }
        result = calc._validate_fred_freshness(fred, __import__("datetime").date(2024, 10, 1))
        self.assertEqual(result["DFII10"], 4)

    def test_wtregen_accepts_normal_weekly_observation_gap(self):
        calculator = MacroMetricsCalculator(as_of_date=dt.date(2024, 10, 1))
        fred = {"data_quality": {"observation_dates": {"WTREGEN": "2024-09-25"}}}
        freshness = calculator._validate_fred_freshness(fred, dt.date(2024, 10, 1))
        self.assertEqual(freshness["WTREGEN"], 6)

    def test_wtregen_still_rejects_excessive_weekly_staleness(self):
        calculator = MacroMetricsCalculator(as_of_date=dt.date(2024, 10, 1))
        fred = {"data_quality": {"observation_dates": {"WTREGEN": "2024-09-20"}}}
        with self.assertRaises(DataUnavailableError):
            calculator._validate_fred_freshness(fred, dt.date(2024, 10, 1))

    def test_nfci_accepts_known_provider_release_lag(self):
        calculator = MacroMetricsCalculator(as_of_date=dt.date(2024, 10, 1))
        fred = {"data_quality": {"observation_dates": {"NFCI": "2024-09-20"}}}
        freshness = calculator._validate_fred_freshness(fred, dt.date(2024, 10, 1))
        self.assertEqual(freshness["NFCI"], 11)

    def test_m2sl_accepts_normal_month_start_release_lag(self):
        calculator = MacroMetricsCalculator(as_of_date=dt.date(2024, 10, 1))
        fred = {"data_quality": {"observation_dates": {"M2SL": "2024-08-01"}}}
        freshness = calculator._validate_fred_freshness(fred, dt.date(2024, 10, 1))
        self.assertEqual(freshness["M2SL"], 61)

    def test_m2sl_still_rejects_excessive_staleness(self):
        calculator = MacroMetricsCalculator(as_of_date=dt.date(2024, 10, 1))
        fred = {"data_quality": {"observation_dates": {"M2SL": "2024-07-01"}}}
        with self.assertRaises(DataUnavailableError):
            calculator._validate_fred_freshness(fred, dt.date(2024, 10, 1))

    def test_de10y_accepts_normal_month_start_release_lag(self):
        calculator = MacroMetricsCalculator(as_of_date=dt.date(2024, 10, 1))
        fred = {"data_quality": {"observation_dates": {"DE10Y": "2024-08-01"}}}
        freshness = calculator._validate_fred_freshness(fred, dt.date(2024, 10, 1))
        self.assertEqual(freshness["DE10Y"], 61)

    def test_de10y_still_rejects_excessive_staleness(self):
        calculator = MacroMetricsCalculator(as_of_date=dt.date(2024, 10, 1))
        fred = {"data_quality": {"observation_dates": {"DE10Y": "2024-07-01"}}}
        with self.assertRaises(DataUnavailableError):
            calculator._validate_fred_freshness(fred, dt.date(2024, 10, 1))

    def test_nfci_still_rejects_excessive_staleness(self):
        calculator = MacroMetricsCalculator(as_of_date=dt.date(2024, 10, 1))
        fred = {"data_quality": {"observation_dates": {"NFCI": "2024-09-16"}}}
        with self.assertRaises(DataUnavailableError):
            calculator._validate_fred_freshness(fred, dt.date(2024, 10, 1))


if __name__ == "__main__":
    unittest.main()
