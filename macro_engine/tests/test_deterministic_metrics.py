import unittest
from preprocessing.metrics import MacroMetricsCalculator


class DeterministicMacroMetricsTests(unittest.TestCase):
    def setUp(self):
        self.calc = MacroMetricsCalculator()

    def run_metrics(self, market=None, fred=None, events=None, previous_state=None, now=None):
        return self.calc.process_all_macro_data(
            market or self.base_market(),
            fred or self.base_fred(),
            events or [],
            previous_regime_state=previous_state,
            now_utc=now,
        )

    def base_market(self):
        def px(v, p=None, d5=None, d20=None, rank=50.0):
            p = v if p is None else p
            d5 = p if d5 is None else d5
            d20 = d5 if d20 is None else d20
            return {
                "value": v, "prev": p, "val_5d_ago": d5, "month_ago": d20,
                "change_pct": ((v-p)/p*100) if p else 0.0,
                "change_pct_5d": ((v-d5)/d5*100) if d5 else 0.0,
                "change_pct_4w": ((v-d20)/d20*100) if d20 else 0.0,
                "pct_rank_60d": rank,
                "history_close": [p, d5, d20, v],
            }
        return {
            "US10Y": px(4.00, 4.00, 4.00, 4.00), "US02Y": px(4.00, 4.00, 4.00, 4.00),
            "DXY": px(100.0, 100.0, 100.0, 100.0), "BRENT": px(80.0, 80.0, 80.0, 80.0),
            "GOLD": px(2000.0, 2000.0, 2000.0, 2000.0), "COPPER": px(4.0, 4.0, 4.0, 4.0),
            "VIX": px(15.0, 15.0, 15.0, 15.0, 50.0), "HYG": px(80.0, 80.0, 80.0, 80.0),
            "LQD": px(105.0, 105.0, 105.0, 105.0), "BTC": px(60000.0, 60000.0, 60000.0, 60000.0),
            "SOL": px(150.0, 150.0, 150.0, 150.0), "CA02Y": px(3.5, 3.5, 3.5, 3.5),
            "DE02Y": px(2.5, 2.5, 2.5, 2.5), "GB02Y": px(4.0, 4.0, 4.0, 4.0),
            "AU02Y": px(3.5, 3.5, 3.5, 3.5), "NZ02Y": px(3.8, 3.8, 3.8, 3.8),
            "IRON_ORE": px(100.0, 100.0, 100.0, 100.0), "DAIRY_GDT": px(3000.0, 3000.0, 3000.0, 3000.0),
        }

    def base_fred(self):
        return {
            "WALCL": 7000000.0, "WALCL_4W_AGO": 7000000.0,
            "RRPONTSYD": 300.0, "RRPONTSYD_4W_AGO": 300.0,
            "WTREGEN": 700000.0, "WTREGEN_4W_AGO": 700000.0,
            "T10YIE": 2.0, "DFII10": 1.5, "DFF": 4.33,
            "DGS2": 4.00, "DGS10": 4.00,
            "DGS2": 4.00, "DGS10": 4.00,
            "BAMLH0A0HYM2": 3.0, "NFCI": -0.2, "ICSA": 220.0,
            "DE10Y": 2.0, "DE10Y_4W_AGO": 2.0,
        }

    def test_yield_curve_noise_and_boundaries(self):
        quiet = self.calc.evaluate_yield_curve(4.00, 4.00, 4.01, 4.00, 4.01, 4.00, 4.01, 4.00)
        self.assertEqual(quiet["regime"], "Range-bound Slope")
        exact = self.calc.evaluate_yield_curve(4.05, 4.00, 4.00, 4.00, 4.00, 4.00, 4.00, 4.00)
        self.assertTrue(exact["is_trend_significant"])

    def test_yield_curve_regimes(self):
        bear = self.calc.evaluate_yield_curve(4.50, 4.10, 4.45, 4.10, 4.20, 4.10, 4.00, 4.10)
        bull = self.calc.evaluate_yield_curve(3.40, 3.90, 3.70, 4.30, 4.00, 5.00, 3.80, 4.60)
        self.assertEqual(bear["regime"], "Bear Steepening")
        self.assertEqual(bull["regime"], "Bull Steepening")

    def test_surprise_units_and_direction(self):
        self.assertEqual(self.calc.calculate_surprise_zscore("nfp", 200, 150), 1.0)
        self.assertEqual(self.calc.calculate_surprise_zscore("unemployment", 3.5, 3.7), 1.33)
        result = self.run_metrics(events=[{"title": "Non-Farm Employment Change", "actual": "200K", "forecast": "150K"}])
        self.assertEqual(result["surprises"][0]["actual"], 200000.0)

    def test_real_yield_accepts_negative_tips(self):
        result = self.calc.calculate_real_yield(0.70, dfii10_tips=-0.15, breakeven_10y=0.85)
        self.assertEqual(result["real_yield_pct"], -0.15)
        self.assertIn("FRED DFII10", result["yield_source"])

    def test_observed_dff_is_authoritative(self):
        result = self.run_metrics()
        self.assertEqual(result["fed_forward_path_analysis"]["fed_policy_rate_source"], "FRED DFF")
        self.assertFalse(result["data_quality"]["fallback_used"])

    def test_liquidity_delta(self):
        result = self.run_metrics(fred={**self.base_fred(), "WALCL": 7100000.0})
        self.assertEqual(result["liquidity_dynamics"]["delta_liquidity_billion"], 100.0)

    def test_fast_stress_requires_confirmation(self):
        market = self.base_market()
        market["VIX"]["value"] = 23.0
        market["HYG"] = {
            **market["HYG"],
            "prev": 82.0,
            "val_5d_ago": 83.0,
        }
        result = self.run_metrics(market=market)
        self.assertTrue(result["t0_fast_stress_analysis"]["fast_stress_override"])
        self.assertGreaterEqual(result["t0_fast_stress_analysis"]["trigger_count"], 2)

    def test_single_vix_jump_does_not_create_systemic_stress(self):
        market = self.base_market()
        market["VIX"] = {
            **market["VIX"],
            "value": 19.0,
            "change_pct": 16.0,
            "change_pct_5d": 20.0,
        }
        result = self.run_metrics(market=market)
        self.assertFalse(result["t0_fast_stress_analysis"]["fast_stress_override"])

    def test_gold_cash_dash(self):
        market = self.base_market()
        market["VIX"]["value"] = 68.0
        fred = {**self.base_fred(), "BAMLH0A0HYM2": 9.0}
        result = self.run_metrics(market=market, fred=fred)
        self.assertTrue(result["gold_fiscal_dominance"]["is_cash_dash"])
        self.assertTrue(result["gold_fiscal_dominance"]["gold_short_allowed"])

    def test_currency_safe_havens(self):
        market = self.base_market()
        market["VIX"] = {**market["VIX"], "value": 30.0, "pct_rank_60d": 95.0}
        result = self.run_metrics(market=market)
        scores = result["cross_pairs_analysis"]["currency_scores"]
        self.assertEqual(scores["JPY"], 1)
        self.assertEqual(scores["CHF"], 1)

    def test_explicit_hysteresis_state(self):
        market = self.base_market()
        market["BRENT"] = {**market["BRENT"], "value": 83.0, "month_ago": 80.0, "change_pct_4w": 3.75}
        market["COPPER"] = {**market["COPPER"], "value": 3.0, "month_ago": 4.0, "change_pct_4w": -25.0}
        result = self.run_metrics(market=market, previous_state={"energy_penalty_active": True})
        self.assertTrue(result["terms_of_trade_energy_analysis"]["eurusd_energy_penalty"])
        self.assertEqual(result["regime_state"]["state_source"], "explicit_previous_regime_state")

    def test_event_freeze_uses_explicit_clock(self):
        now = __import__("datetime").datetime(2026, 1, 1, 12, 0, tzinfo=__import__("datetime").timezone.utc)
        events = [{"title": "CPI", "impact": "High", "time": "2026-01-01T12:10:00+00:00"}]
        result = self.run_metrics(events=events, now=now)
        self.assertTrue(result["cross_pairs_analysis"]["event_freeze"]["active"])

    def test_return_correlation_method_is_explicit(self):
        result = self.run_metrics()
        self.assertEqual(result["dxy_oil_correlation_method"], "pearson_on_period_returns")


if __name__ == "__main__":
    unittest.main(verbosity=2)
