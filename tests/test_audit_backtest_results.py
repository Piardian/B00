import unittest

from scripts.audit_backtest_results import DEFAULT_REPORTS, audit


class BacktestAuditTests(unittest.TestCase):
    def test_optimized_report_exposes_negative_gated_performance(self):
        lines = "\n".join(audit(DEFAULT_REPORTS[0]))
        self.assertIn("Macro-gated:", lines)
        self.assertIn("negative net R", lines)

    def test_zero_trade_strategy_leg_is_marked_unvalidated(self):
        lines = "\n".join(audit(DEFAULT_REPORTS[1]))
        self.assertIn("ORB_LONDON_FOREX_ONLY", lines)
        self.assertIn("zero reported trades", lines)


if __name__ == "__main__":
    unittest.main()
