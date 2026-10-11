import datetime as dt
import unittest
from unittest.mock import patch

from data_quality import DataUnavailableError
from preprocessing.metrics import MacroMetricsCalculator


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        import json
        return json.dumps(self.payload).encode("utf-8")


class DataIntegrityTests(unittest.TestCase):
    def test_negative_tips_is_direct_observation(self):
        result = MacroMetricsCalculator().calculate_real_yield(
            0.70, dfii10_tips=-0.15, breakeven_10y=0.85
        )
        self.assertEqual(result["real_yield_pct"], -0.15)
        self.assertIn("FRED DFII10", result["yield_source"])

    def test_missing_core_market_data_fails_closed(self):
        from ingestion.market_data import MarketDataIngestion
        ingestion = MarketDataIngestion()
        with patch.object(ingestion.mt5_feed, "fetch_symbol_bars", return_value=None), \
             patch("ingestion.market_data_legacy.yf.Ticker") as ticker:
            ticker.return_value.history.side_effect = RuntimeError("feed unavailable")
            with self.assertRaises(DataUnavailableError):
                ingestion.fetch_current_prices()

    def test_replay_clock_is_injected(self):
        calc = MacroMetricsCalculator()
        from tests.test_deterministic_metrics import DeterministicMacroMetricsTests
        helper = DeterministicMacroMetricsTests("runTest")
        market = helper.base_market()
        fred = helper.base_fred()
        as_of = dt.datetime(2023, 9, 20, 12, 0)
        first = calc.process_all_macro_data(
            market,
            fred,
            [],
            as_of_datetime=as_of,
        )
        second = calc.process_all_macro_data(
            market,
            fred,
            [],
            as_of_datetime=as_of,
        )
        self.assertEqual(first, second)

    def test_fed_forward_path_uses_observed_dff(self):
        result = MacroMetricsCalculator.calculate_fed_forward_path(
            us02y=3.80,
            dff=4.33,
            us02y_5d=3.95,
        )
        self.assertEqual(result["fed_policy_rate_pct"], 4.33)
        self.assertEqual(result["fed_policy_rate_source"], "FRED DFF")
        self.assertEqual(result["implied_rate_gap_bps"], -53.0)
        self.assertEqual(result["delta_02y_5d_bps"], -15.0)
        self.assertEqual(result["rate_expectation_signal"], "Market-implied easing")

    def test_fed_policy_spread_is_not_labeled_as_total_cuts(self):
        result = MacroMetricsCalculator.calculate_fed_forward_path(
            us02y=3.80,
            dff=4.33,
            us02y_5d=3.95,
        )
        self.assertIn("market-vs-current-policy spread", result["interpretation_warning"])
        self.assertIn("not a", result["interpretation_warning"])

    def test_missing_satellite_sol_does_not_block_core_macro(self):
        from tests.test_deterministic_metrics import DeterministicMacroMetricsTests
        helper = DeterministicMacroMetricsTests("runTest")
        market = helper.base_market()
        market.pop("SOL")
        fred = helper.base_fred()

        result = MacroMetricsCalculator().process_all_macro_data(market, fred, [])
        self.assertIn("cycle_diagnosis", result)
        self.assertIn("yield_curve", result)

    def test_missing_dff_fails_closed(self):
        from tests.test_deterministic_metrics import DeterministicMacroMetricsTests
        helper = DeterministicMacroMetricsTests("runTest")
        market = helper.base_market()
        fred = helper.base_fred()
        del fred["DFF"]

        with self.assertRaises(DataUnavailableError):
            MacroMetricsCalculator().process_all_macro_data(market, fred, [])

    def test_fred_replay_uses_as_of_as_vintage_end(self):
        from ingestion.fred_data import FredDataIngestion

        payload = {"observations": [{"date": "2023-03-10", "value": "4.20"}]}
        client = FredDataIngestion(api_key="test")
        with patch("ingestion.fred_data.urllib.request.urlopen", return_value=_FakeResponse(payload)) as mocked:
            rows = client._get_observations(
                "DFF",
                dt.date(2023, 3, 1),
                dt.date(2023, 3, 13),
                realtime_end=dt.date(2023, 3, 13),
            )
        self.assertEqual(rows, [(dt.date(2023, 3, 10), 4.20)])
        request = mocked.call_args.args[0]
        self.assertIn("realtime_end=2023-03-13", request.full_url)

    def test_fred_api_key_is_redacted_in_exceptions(self):
        from ingestion.fred_data import _mask_api_key, FredDataIngestion
        fake_key = "secret_api_key_123456789"
        error_msg = f"HTTP Error 400: https://api.stlouisfed.org/fred/series?api_key={fake_key}&series_id=NAPM"
        masked = _mask_api_key(error_msg, fake_key)
        self.assertNotIn(fake_key, masked)
        self.assertIn("REDACTED", masked)

    def test_calendar_offline_triggers_fail_closed_event_freeze(self):
        from ingestion.calendar_event import CalendarEventIngestion
        from core.deterministic_controls import event_freeze_status, resolve_execution_gate
        
        # Simulating fail-closed sentinel event returned when calendar is down
        sentinel = [{
            "title": "Ekonomik Takvim Alınamadı (Fail-Closed Güvenli Devre Kesici)",
            "country": "USD",
            "impact": "CRITICAL",
            "time": None,
            "uncertain": True,
            "fail_closed": True,
        }]
        now = dt.datetime(2026, 9, 17, 12, 0, 0, tzinfo=dt.timezone.utc)
        freeze = event_freeze_status(sentinel, now)
        self.assertTrue(freeze["active"])
        self.assertTrue(freeze["uncertain"])
        
        decision = resolve_execution_gate("LONG_ONLY", event_freeze=freeze["active"])
        self.assertEqual(decision["gate"], "NO_TRADE")
        self.assertEqual(decision["reason"], "event_freeze has highest precedence")

    def test_ism_discontinuation_reported_as_unavailable_without_synthetic_substitution(self):
        from ingestion.fred_data import FredDataIngestion
        client = FredDataIngestion(api_key="mock_key")
        # Ensure _current_and_4w does not return hardcoded 47.2/51.5
        with patch.object(client, "_get_observations", side_effect=DataUnavailableError("Series discontinued")):
            with self.assertRaises(DataUnavailableError):
                client._current_and_4w("NAPM", dt.date(2026, 9, 17))


if __name__ == "__main__":
    unittest.main(verbosity=2)
