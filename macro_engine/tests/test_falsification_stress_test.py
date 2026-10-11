import unittest
from calibration.falsification_stress_test import (
    bootstrap_ci,
    calculate_hit_rate,
    calculate_net_returns,
    cluster_simultaneous_events,
    permutation_test_hit_rate,
    permutation_test_ic,
)


class TestFalsificationStressTest(unittest.TestCase):
    def test_bootstrap_ci(self):
        # Degenerate empty
        est, low, high = bootstrap_ci([], lambda x: 0.0)
        self.assertEqual((est, low, high), (0.0, 0.0, 0.0))

        # Sample with clear mean
        data = [10.0, 10.0, 10.0, 10.0, 10.0]
        est, low, high = bootstrap_ci(data, lambda x: sum(x) / len(x), n_resamples=100)
        self.assertEqual(est, 10.0)
        self.assertEqual(low, 10.0)
        self.assertEqual(high, 10.0)

        # Varied sample
        sample = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        est, low, high = bootstrap_ci(sample, lambda x: sum(x) / len(x), n_resamples=200, seed=1)
        self.assertEqual(est, 5.5)
        self.assertLess(low, est)
        self.assertGreater(high, est)

    def test_permutation_test_ic(self):
        # Perfect correlation should have p-value close to 0.0
        x = list(range(20))
        y = [val * 2.0 for val in x]
        p_val = permutation_test_ic(x, y, n_permutations=200, seed=42)
        self.assertLess(p_val, 0.05)

        # Pure uncorrelated noise should have large p-value
        x_noise = [1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 3.0, -3.0]
        y_noise = [-2.0, 3.0, -1.0, 1.0, 4.0, -2.0, 0.0, 1.0]
        p_noise = permutation_test_ic(x_noise, y_noise, n_permutations=200, seed=42)
        self.assertGreater(p_noise, 0.10)

    def test_permutation_test_hit_rate(self):
        # 10 out of 10 wins (100% win rate) should have small p-value
        hits_perfect = [
            {"z": 1.5, "ret": 20.0},
            {"z": 2.0, "ret": 15.0},
            {"z": -1.2, "ret": -10.0},
            {"z": -2.5, "ret": -30.0},
            {"z": 1.1, "ret": 5.0},
            {"z": 1.8, "ret": 25.0},
            {"z": -1.4, "ret": -15.0},
            {"z": 2.2, "ret": 18.0},
            {"z": -1.6, "ret": -12.0},
            {"z": 1.3, "ret": 8.0},
        ]
        p_perfect = permutation_test_hit_rate(hits_perfect, "z", "ret", n_permutations=200, seed=42)
        self.assertLess(p_perfect, 0.05)

        # 50% hit rate should have p-value of 1.0
        hits_50 = [
            {"z": 1.0, "ret": 10.0},
            {"z": 1.0, "ret": -10.0},
        ]
        p_50 = permutation_test_hit_rate(hits_50, "z", "ret")
        self.assertEqual(p_50, 1.0)

    def test_cluster_simultaneous_events(self):
        # Two simultaneous events at 13:30 UTC: NFP (+2.0 Z) and Unemployment (+1.0 Z)
        records = [
            {
                "event_timestamp_utc": "2024-02-02T13:30:00+00:00",
                "year": 2024,
                "indicator": "nfp",
                "z_mad": 2.0,
                "z_std": 1.0,
                "raw_surprise": 166000.0,
                "sign_surprise": 1.0,
                "ret_30m": 70.0,
            },
            {
                "event_timestamp_utc": "2024-02-02T13:30:00+00:00",
                "year": 2024,
                "indicator": "unemployment",
                "z_mad": 1.0,
                "z_std": 0.5,
                "raw_surprise": 0.2,
                "sign_surprise": 1.0,
                "ret_30m": 70.0,
            },
            {
                "event_timestamp_utc": "2024-03-01T15:00:00+00:00",
                "year": 2024,
                "indicator": "pmi",
                "z_mad": -1.0,
                "z_std": -0.8,
                "raw_surprise": -1.5,
                "sign_surprise": -1.0,
                "ret_30m": -15.0,
            },
        ]

        clustered = cluster_simultaneous_events(records)
        self.assertEqual(len(clustered), 2)  # Collapsed 3 events into 2 distinct time instants
        first = clustered[0]
        self.assertEqual(first["cluster_size"], 2)
        self.assertEqual(first["indicators"], ["nfp", "unemployment"])
        self.assertEqual(first["z_mad"], 1.5)  # (2.0 + 1.0) / 2
        self.assertEqual(first["ret_30m"], 70.0)

    def test_calculate_net_returns(self):
        records = [
            {"z_mad": 2.0, "ret_30m": 30.0},   # Pos: +1, Gross: 30 bps, Net (10bps cost): +20 bps
            {"z_mad": -1.5, "ret_30m": -25.0}, # Pos: -1, Gross: 25 bps, Net (10bps cost): +15 bps
            {"z_mad": 1.2, "ret_30m": 5.0},    # Pos: +1, Gross: 5 bps, Net (10bps cost): -5 bps
            {"z_mad": 0.5, "ret_30m": 50.0},   # Filtered out because |Z| < 1.0
        ]

        net_stats = calculate_net_returns(records, "z_mad", "ret_30m", threshold=1.0, cost_bps=10.0)
        self.assertEqual(net_stats["trade_count"], 3)
        self.assertAlmostEqual(net_stats["mean_gross_bps"], (30.0 + 25.0 + 5.0) / 3, places=2)
        self.assertAlmostEqual(net_stats["mean_net_bps"], (20.0 + 15.0 - 5.0) / 3, places=2)
        self.assertAlmostEqual(net_stats["net_win_rate_pct"], (2 / 3) * 100.0, places=1)
        self.assertGreater(net_stats["profit_factor"], 1.0)


if __name__ == "__main__":
    unittest.main()
