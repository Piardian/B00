import datetime as dt
import unittest

from calibration.event_horizon import target_bar_open, target_bar_sequence


class TestEventHorizon(unittest.TestCase):
    def setUp(self):
        self.t = dt.datetime(2024, 1, 2, 13, 30, tzinfo=dt.timezone.utc)

    def test_m30_horizons_use_bar_close_at_requested_time(self):
        self.assertEqual(
            target_bar_open(self.t, 30, 30),
            dt.datetime(2024, 1, 2, 13, 30, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(
            target_bar_open(self.t, 30, 60),
            dt.datetime(2024, 1, 2, 14, 0, tzinfo=dt.timezone.utc),
        )
        self.assertEqual(
            target_bar_open(self.t, 30, 240),
            dt.datetime(2024, 1, 2, 17, 0, tzinfo=dt.timezone.utc),
        )

    def test_m15_horizon(self):
        self.assertEqual(
            target_bar_open(self.t, 15, 15),
            self.t,
        )
        self.assertEqual(
            target_bar_open(self.t, 15, 30),
            dt.datetime(2024, 1, 2, 13, 45, tzinfo=dt.timezone.utc),
        )

    def test_sequence_contains_only_bars_inside_horizon(self):
        self.assertEqual(
            target_bar_sequence(self.t, 30, 60),
            [
                dt.datetime(2024, 1, 2, 13, 30, tzinfo=dt.timezone.utc),
                dt.datetime(2024, 1, 2, 14, 0, tzinfo=dt.timezone.utc),
            ],
        )

    def test_rejects_invalid_horizon(self):
        with self.assertRaises(ValueError):
            target_bar_open(self.t, 30, 45)
        with self.assertRaises(ValueError):
            target_bar_open(dt.datetime(2024, 1, 2, 13, 30), 30, 60)


if __name__ == "__main__":
    unittest.main()
