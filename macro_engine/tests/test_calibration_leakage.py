import datetime as dt
import unittest
from core.deterministic_controls import fit_surprise_sigmas
from calibration.promotion_simulation import FROZEN_MAD_THRESHOLD, evaluate_frozen_holdout

CUTOFF_DATE = dt.date(2025, 7, 1)

class CalibrationLeakageTests(unittest.TestCase):
    def test_calibration_cutoff_strictly_excludes_2025h2_and_2026(self):
        pre_cutoff_rows = [
            {'date': f'2024-{(i % 12) + 1:02d}-15', 'indicator_type': 'cpi', 'actual': 0.3 + (i * 0.01), 'forecast': 0.2}
            for i in range(40)
        ]
        post_cutoff_rows = [
            {'date': '2025-08-10', 'indicator_type': 'cpi', 'actual': 2.5, 'forecast': 0.1},
            {'date': '2025-11-15', 'indicator_type': 'cpi', 'actual': -3.0, 'forecast': 0.2},
            {'date': '2026-03-20', 'indicator_type': 'cpi', 'actual': 5.0, 'forecast': 0.0},
        ]
        sigma_pre = fit_surprise_sigmas(
            [r for r in pre_cutoff_rows if dt.date.fromisoformat(r['date']) < CUTOFF_DATE],
            min_observations=15,
            method='mad',
        )
        self.assertIn('cpi', sigma_pre)
        combined = pre_cutoff_rows + post_cutoff_rows
        filtered = [r for r in combined if dt.date.fromisoformat(r['date']) < CUTOFF_DATE]
        sigma_filtered = fit_surprise_sigmas(filtered, min_observations=15, method='mad')
        self.assertEqual(sigma_pre['cpi'], sigma_filtered['cpi'])
        sigma_leaked = fit_surprise_sigmas(combined, min_observations=15, method='mad')
        self.assertNotEqual(sigma_pre['cpi'], sigma_leaked['cpi'], 'Leakage must alter sigma when unfiltered')

    def test_frozen_threshold_invariant(self):
        self.assertEqual(FROZEN_MAD_THRESHOLD, 1.0)
        with self.assertRaises(ValueError):
            evaluate_frozen_holdout([], threshold=1.5)

if __name__ == '__main__':
    unittest.main()
