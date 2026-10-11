import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from preprocessing.metrics import MacroMetricsCalculator
from calibration.replay import validate_snapshot_no_lookahead
from data_quality import DataUnavailableError
from tests.historical_replay import (
    run_scenario_october_2023,
    run_scenario_march_2023_svb,
    run_scenario_march_2020_covid,
)


class HistoricalReplayAndDeterminismTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.gate_path = Path(self.tmpdir.name) / "macro_bias_gate.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _run_with_fixed_clock(self, scenario):
        fixed_now = dt.datetime(2023, 3, 13, 12, 0, tzinfo=dt.timezone.utc)

        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = fixed_now
                return value if tz is not None else value.replace(tzinfo=None)

        with patch("preprocessing.metrics.dt.datetime", FixedDateTime):
            return scenario()

    def test_october_2023_replay_detects_bear_steepening_or_inversion(self):
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            result = run_scenario_october_2023()
        self.assertIn(result["yield_curve"]["regime"], {"Bear Steepening", "Inverted"})

    def test_october_2023_replay_activates_btc_decoupling(self):
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            result = run_scenario_october_2023()
        self.assertTrue(result["btc_decoupling_analysis"]["btc_decoupling_active"])
        self.assertEqual(result["btc_decoupling_analysis"]["recommended_btc_gate"], "SHORT_ONLY")

    def test_svb_replay_detects_fast_stress(self):
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            result = run_scenario_march_2023_svb()
        self.assertTrue(result["t0_fast_stress_analysis"]["fast_stress_override"])

    def test_svb_replay_detects_bull_steepening_or_inversion(self):
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            result = run_scenario_march_2023_svb()
        self.assertIn("Bull Steepening", result["yield_curve"]["regime"] + " ")

    def test_covid_replay_detects_fast_stress(self):
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            result = run_scenario_march_2020_covid()
        self.assertTrue(result["t0_fast_stress_analysis"]["fast_stress_override"])

    def test_covid_replay_detects_severe_credit_stress(self):
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            result = run_scenario_march_2020_covid()
        self.assertGreater(result["credit_spread_analysis"]["hy_oas_spread_pct"], 5.0)
        self.assertIn("Şiddetli", result["credit_spread_analysis"]["stress_level"])

    def test_same_inputs_with_same_state_are_identical(self):
        gate = {"regime_state": {"energy_penalty_active": True}}
        self.gate_path.write_text(json.dumps(gate), encoding="utf-8")
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            first = self._run_with_fixed_clock(run_scenario_march_2023_svb)
            second = self._run_with_fixed_clock(run_scenario_march_2023_svb)
        self.assertEqual(first, second)

    def test_historical_replay_does_not_require_llm(self):
        self.assertIsInstance(run_scenario_october_2023, object)
        self.assertIsInstance(run_scenario_march_2023_svb, object)
        self.assertIsInstance(run_scenario_march_2020_covid, object)

    def test_historical_replay_has_explicit_scenario_data(self):
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            result = run_scenario_march_2020_covid()
        self.assertIn("yield_curve", result)
        self.assertIn("liquidity_dynamics", result)
        self.assertIn("credit_spread_analysis", result)
        self.assertIn("btc_decoupling_analysis", result)

    def test_replay_scenarios_are_documented_as_synthetic_fixtures(self):
        with patch("preprocessing.metrics.BIAS_GATE_FILE", self.gate_path):
            result = run_scenario_march_2020_covid()
        self.assertEqual(
            result["data_quality"]["fixture_provenance"],
            "SYNTHETIC_TEST_FIXTURE",
        )
        self.assertFalse(result["data_quality"]["fallback_used"])
        self.assertNotIn("DFF", result["data_quality"]["fallback_fields"])

    def test_real_yield_negative_tips_is_not_lost_from_raw_result(self):
        result = MacroMetricsCalculator.calculate_real_yield(
            0.70, dfii10_tips=-0.15, breakeven_10y=0.85
        )
        self.assertEqual(result["real_yield_pct"], -0.15)
        self.assertIn("FRED DFII10", result["yield_source"])

    def test_replay_lookahead_is_rejected(self):
        with self.assertRaises(DataUnavailableError):
            validate_snapshot_no_lookahead(
                {"timestamp": "2023-03-14T00:00:00+00:00"},
                dt.datetime(2023, 3, 13, 12, 0, tzinfo=dt.timezone.utc),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
