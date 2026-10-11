import datetime as dt
import unittest

from preprocessing.policy_expectations import build_policy_expectations


class PolicyExpectationsTests(unittest.TestCase):
    def base_fred(self):
        return {"DFF": 4.33, "SOFR": 4.31}

    def test_missing_optional_curves_are_explicitly_unavailable(self):
        result = build_policy_expectations(self.base_fred())
        self.assertEqual(result["effective_policy_rate"]["sofr_minus_dff_bps"], -2.0)
        self.assertEqual(result["front_fed_funds_future"]["status"], "UNAVAILABLE")
        self.assertEqual(result["fed_funds_futures_curve"]["status"], "UNAVAILABLE")
        self.assertEqual(result["usd_ois_curve"]["status"], "UNAVAILABLE")
        self.assertTrue(result["interpretation_guardrails"]["no_synthetic_ois"])

    def test_front_fed_funds_future_conversion_and_repricing(self):
        market = {
            "FED_FUNDS_FUTURES": {
                "value": 96.25,
                "prev": 96.20,
                "val_5d_ago": 96.05,
                "contract_month": "2024-04",
                "source": "CME test fixture",
            }
        }
        result = build_policy_expectations(self.base_fred(), market)
        panel = result["front_fed_funds_future"]
        self.assertEqual(panel["status"], "AVAILABLE")
        self.assertEqual(panel["market_implied_rate_pct"], 3.75)
        self.assertEqual(panel["vs_dff_bps"], -58.0)
        self.assertEqual(panel["reprice_1d_bps"], -5.0)
        self.assertEqual(panel["reprice_5d_bps"], -20.0)
        self.assertEqual(panel["contract"], "2024-04")

    def test_multiple_futures_contracts_are_not_reduced_to_a_probability(self):
        market = {
            "FED_FUNDS_FUTURES_CURVE": [
                {"contract": "2024-06", "price": 95.75},
                {"contract": "2024-05", "price": 96.00},
                {"contract": "2024-07", "price": 95.50},
            ]
        }
        result = build_policy_expectations(self.base_fred(), market)
        curve = result["fed_funds_futures_curve"]
        self.assertEqual(curve["status"], "AVAILABLE")
        self.assertEqual([row["contract"] for row in curve["contracts"]], ["2024-05", "2024-06", "2024-07"])
        self.assertEqual(curve["contracts"][0]["implied_rate_pct"], 4.0)
        self.assertTrue(result["interpretation_guardrails"]["no_meeting_probability_inference"])

    def test_ois_curve_is_passed_through_without_synthesis(self):
        market = {
            "USD_OIS_CURVE": {"1M": 4.30, "3M": 4.20, "6M": 4.05, "1Y": 3.90},
            "USD_OIS_CURVE_SOURCE": "test OIS provider",
        }
        result = build_policy_expectations(self.base_fred(), market)
        curve = result["usd_ois_curve"]
        self.assertEqual(curve["status"], "AVAILABLE")
        self.assertEqual(curve["source"], "test OIS provider")
        self.assertEqual(curve["tenors"][1]["rate_pct"], 4.20)

    def test_panel_is_deterministic(self):
        market = {
            "FED_FUNDS_FUTURES": {"value": 96.25, "prev": 96.20, "val_5d_ago": 96.05},
            "FED_FUNDS_FUTURES_CURVE": {"2024-05": 96.0, "2024-06": 95.75},
            "USD_OIS_CURVE": {"1M": 4.30, "3M": 4.20},
        }
        first = build_policy_expectations(self.base_fred(), market)
        second = build_policy_expectations(self.base_fred(), market)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
