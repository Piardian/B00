import datetime as dt
import unittest

from calibration.promotion_simulation import (
    Bar,
    ExecutionScenario,
    evaluate_frozen_holdout,
    evaluate_incremental_smc_alpha,
    simulate_trade_path,
)


UTC = dt.timezone.utc


class PromotionSimulationTests(unittest.TestCase):
    def test_frozen_holdout_does_not_learn_threshold(self):
        rows = [
            {
                "event_time_utc": "2025-07-03T12:00:00+00:00",
                "cluster_signal": 1,
                "dominant_z_mad": 1.2,
                "post_30m_usd_bps": 20.0,
            },
            {
                "event_time_utc": "2025-08-03T12:00:00+00:00",
                "cluster_signal": -1,
                "dominant_z_mad": 0.8,
                "post_30m_usd_bps": 10.0,
            },
        ]
        report = evaluate_frozen_holdout(rows)
        self.assertEqual(report["frozen_parameters"]["mad_threshold_abs_z"], 1.0)
        self.assertTrue(report["frozen_parameters"]["no_holdout_fitting"])
        result = report["windows"]["2025_H2"]
        self.assertEqual(result["baseline"]["trade_count"], 2)
        self.assertEqual(result["frozen_mad"]["trade_count"], 1)

    def test_t5_retest_limit_can_fill_or_not_fill(self):
        bars = [
            Bar(dt.datetime(2025, 7, 3, 12, 0, tzinfo=UTC), 100.0, 101.0, 99.5, 100.5),
            Bar(dt.datetime(2025, 7, 3, 12, 5, tzinfo=UTC), 100.5, 100.8, 99.0, 100.2),
            Bar(dt.datetime(2025, 7, 3, 12, 10, tzinfo=UTC), 100.2, 102.0, 100.0, 101.5),
        ]
        scenario = ExecutionScenario("TEST", 10.0, 2.5, 1, 2)
        result = simulate_trade_path(
            bars,
            event_time=dt.datetime(2025, 7, 3, 12, 0, tzinfo=UTC),
            side=1,
            entry_zone=(99.5, 100.5),
            stop_loss=98.5,
            take_profit=101.0,
            scenario=scenario,
            mode="T5_RETEST_LIMIT",
        )
        self.assertEqual(result["status"], "EXECUTED")
        self.assertEqual(result["exit_reason"], "TARGET")

    def test_same_bar_stop_and_target_is_fail_closed(self):
        bars = [
            Bar(dt.datetime(2025, 7, 3, 12, 0, tzinfo=UTC), 100.0, 102.0, 98.0, 100.0),
        ]
        scenario = ExecutionScenario("TEST", 10.0, 2.5, 0, 1)
        result = simulate_trade_path(
            bars,
            event_time=dt.datetime(2025, 7, 3, 12, 0, tzinfo=UTC),
            side=1,
            entry_zone=(100.0, 100.0),
            stop_loss=99.0,
            take_profit=101.0,
            scenario=scenario,
            mode="T0_MARKET",
        )
        self.assertEqual(result["status"], "AMBIGUOUS")

    def test_incremental_alpha_requires_macro_alignment_and_frozen_threshold(self):
        trades = [
            {"smc_direction": "LONG", "macro_direction": "LONG", "dominant_z_mad": 1.4, "realized_r": 2.0},
            {"smc_direction": "LONG", "macro_direction": "SHORT", "dominant_z_mad": 2.0, "realized_r": -1.0},
            {"smc_direction": "SHORT", "macro_direction": "SHORT", "dominant_z_mad": 0.7, "realized_r": 1.0},
        ]
        report = evaluate_incremental_smc_alpha(trades)
        self.assertEqual(report["baseline_smc"]["trade_count"], 3)
        self.assertEqual(report["smc_plus_macro"]["trade_count"], 1)
        self.assertAlmostEqual(report["smc_plus_macro"]["mean"], 2.0)
        self.assertEqual(report["incremental"]["coverage_pct"], 33.33)

    def test_threshold_override_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_frozen_holdout([], threshold=1.1)
        with self.assertRaises(ValueError):
            evaluate_incremental_smc_alpha([], threshold=1.1)


if __name__ == "__main__":
    unittest.main()
