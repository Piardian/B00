import unittest

from calibration.historical_filter_lab import run_walk_forward_filter_lab


class TestHistoricalFilterLab(unittest.TestCase):
    def test_thresholds_are_learned_from_prior_years_only(self):
        dataset = [
            {"year": 2021, "event_time_utc": "2021-01-01T00:00:00+00:00", "cluster_signal": 1, "cluster_all_aligned": True, "dominant_mad_actionable": True, "pre_60m_abs_bps": 10, "pre_realized_vol_bps": 2, "pre_atr_bps": 3, "pre_60m_aligned": False, "post_30m_usd_bps": 20},
            {"year": 2021, "event_time_utc": "2021-02-01T00:00:00+00:00", "cluster_signal": 1, "cluster_all_aligned": False, "dominant_mad_actionable": False, "pre_60m_abs_bps": 20, "pre_realized_vol_bps": 4, "pre_atr_bps": 6, "pre_60m_aligned": True, "post_30m_usd_bps": -20},
            {"year": 2022, "event_time_utc": "2022-01-01T00:00:00+00:00", "cluster_signal": 1, "cluster_all_aligned": True, "dominant_mad_actionable": True, "pre_60m_abs_bps": 11, "pre_realized_vol_bps": 2.5, "pre_atr_bps": 3.5, "pre_60m_aligned": False, "post_30m_usd_bps": 15},
            {"year": 2022, "event_time_utc": "2022-02-01T00:00:00+00:00", "cluster_signal": 1, "cluster_all_aligned": False, "dominant_mad_actionable": False, "pre_60m_abs_bps": 1000, "pre_realized_vol_bps": 1000, "pre_atr_bps": 1000, "pre_60m_aligned": True, "post_30m_usd_bps": -15},
            {"year": 2023, "event_time_utc": "2023-01-01T00:00:00+00:00", "cluster_signal": -1, "cluster_all_aligned": True, "dominant_mad_actionable": True, "pre_60m_abs_bps": 12, "pre_realized_vol_bps": 2.5, "pre_atr_bps": 3.5, "pre_60m_aligned": False, "post_30m_usd_bps": -12},
        ]

        report = run_walk_forward_filter_lab(dataset, test_years=(2022, 2023), quantile=0.75)
        self.assertEqual(set(report["by_year"].keys()), {"2022", "2023"})
        # 2022 thresholds are learned from only the two 2021 rows, not the huge 2022 outlier.
        self.assertLess(report["by_year"]["2022"]["train_thresholds"]["pre_60m_abs_bps_q"], 1000)
        self.assertEqual(report["by_year"]["2022"]["filters"]["baseline_sign"]["0"]["trade_count"], 2)
        self.assertEqual(report["by_year"]["2022"]["filters"]["coherent_events"]["0"]["trade_count"], 1)
        self.assertEqual(report["pooled_oos"]["baseline_sign"]["0"]["trade_count"], 3)


if __name__ == "__main__":
    unittest.main()
