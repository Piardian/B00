import unittest

from data_quality import DataUnavailableError
from gateways.telegram_notifier import (
    format_morning_briefing,
    sanitize_unverified_price_levels,
)
from preprocessing.metrics import MacroMetricsCalculator
from tests.test_deterministic_metrics import DeterministicMacroMetricsTests


class MacroEvidenceHardeningTests(unittest.TestCase):
    def setUp(self):
        self.calc = MacroMetricsCalculator()
        helper = DeterministicMacroMetricsTests("runTest")
        self.market = helper.base_market()
        self.fred = helper.base_fred()

    def test_fred_baseline_is_not_authoritative(self):
        fred = {
            **self.fred,
            "data_quality": {
                "provider": "FRED_BASELINE",
                "fallback_used": True,
            },
        }
        with self.assertRaises(DataUnavailableError):
            self.calc.process_all_macro_data(self.market, fred, [])

    def test_missing_relative_value_data_disables_directional_cross_gates(self):
        market = {
            key: value
            for key, value in self.market.items()
            if key not in {"CA02Y", "DE02Y", "GB02Y", "AU02Y", "NZ02Y"}
        }
        result = self.calc.process_all_macro_data(market, self.fred, [])
        cross = result["cross_pairs_analysis"]
        self.assertEqual(cross["data_quality"]["status"], "UNAVAILABLE")
        self.assertTrue(cross["data_quality"]["directional_gates_disabled"])
        self.assertTrue(all(
            gate == "NEUTRAL_RANGE"
            for gate in cross["cross_gates"].values()
        ))

    def test_cycle_uses_authoritative_unemployment_not_static_default(self):
        fred = {**self.fred, "UNRATE": 5.1}
        result = self.calc.process_all_macro_data(self.market, fred, [])
        self.assertEqual(result["cycle_diagnosis"]["unemployment_rate"], 5.1)
        self.assertFalse(result["cycle_diagnosis"]["is_labor_strong"])
        self.assertNotEqual(result["cycle_diagnosis"]["unemployment_rate"], 4.1)

    def test_treasury_market_and_fred_sources_are_consistent(self):
        result = self.calc.process_all_macro_data(
            self.market,
            self.fred,
            [],
        )
        consistency = result["market_source_consistency"]["treasury_curve"]
        self.assertEqual(consistency["US02Y"]["status"], "ALIGNED")
        self.assertEqual(consistency["US10Y"]["status"], "ALIGNED")

    def test_treasury_source_divergence_is_reported(self):
        market = dict(self.market)
        market["US02Y"] = {**market["US02Y"], "value": 4.40}
        result = self.calc.process_all_macro_data(market, self.fred, [])
        item = result["market_source_consistency"]["treasury_curve"]["US02Y"]
        self.assertEqual(item["status"], "DIVERGENT")
        self.assertIn("differ materially", result["market_source_consistency"]["warning"])

    def test_telegram_uses_deterministic_gate_not_llm_advisory(self):
        pipeline = {
            "final_output": {
                "execution_bias_gates": {
                    "BTC": "LONG_ONLY",
                    "XAUUSD": "LONG_ONLY",
                    "EURUSD": "SHORT_ONLY",
                    "SPX": "NEUTRAL_RANGE",
                },
                "macro_rationale": "",
                "horizon_today": "",
                "horizon_this_week": "",
                "horizon_this_month": "",
            },
            "deterministic_execution_gates": {
                "source": "deterministic_metrics_only",
                "execution_bias_gates": {
                    "BTC": "DEFENSIVE_HOLD",
                    "XAUUSD": "NEUTRAL_RANGE",
                    "EURUSD": "NEUTRAL_RANGE",
                    "SPX": "NEUTRAL_RANGE",
                },
            },
            "processed_metrics": {},
        }
        msg = format_morning_briefing(pipeline)
        self.assertIn("Gate Kaynağı: <b>deterministic_metrics_only</b>", msg)
        btc_pos = msg.find("Bitcoin (BTCUSD)")
        btc_block = msg[btc_pos:btc_pos + 700]
        self.assertIn("DEFENSIVE_HOLD", btc_block)
        self.assertNotIn("SADECE ALIM (LONG_ONLY)", btc_block)


    def test_one_point_currency_edge_remains_neutral(self):
        market = {
            **self.market,
            "BRENT": {
                **self.market["BRENT"],
                "value": 83.2,
                "month_ago": 80.0,
                "change_pct_4w": 4.0,
            },
        }
        result = self.calc.process_all_macro_data(market, self.fred, [])
        # CAD gets a +1 commodity score while AUD remains neutral. The pair
        # must not become directional on a one-point difference.
        self.assertEqual(result["cross_pairs_analysis"]["currency_scores"]["CAD"], 1)
        self.assertEqual(result["cross_pairs_analysis"]["currency_scores"]["AUD"], 0)
        self.assertEqual(
            result["cross_pairs_analysis"]["cross_gates"]["AUDCAD"],
            "NEUTRAL_RANGE",
        )

    def test_unverified_price_levels_are_removed_from_free_form_text(self):
        text = (
            "BTC $66,000 destek bölgesi; XAUUSD 2650-2680 bandı; "
            "DXY 100.50 direnç; BTCUSD=66,500 hedef."
        )
        cleaned = sanitize_unverified_price_levels(text)
        self.assertNotIn("$66,000", cleaned)
        self.assertNotIn("2650-2680", cleaned)
        self.assertNotIn("DXY 100.50", cleaned)
        self.assertNotIn("BTCUSD=66,500", cleaned)
        self.assertIn("Doğrulanmış teknik fiyat seviyesi", cleaned)

    def test_price_sanitizer_preserves_non_price_macro_numbers(self):
        text = "NFCI -0.56, DFF 4.83%, 5G spread +58.2 bps."
        cleaned = sanitize_unverified_price_levels(text)
        self.assertIn("NFCI -0.56", cleaned)
        self.assertIn("DFF 4.83%", cleaned)
        self.assertIn("+58.2 bps", cleaned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
