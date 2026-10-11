import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from gateways.execution_bias_bridge import ExecutionBiasBridge
from graph.macro_graph import MacroWorkflowEngine


class ExecutionGateTests(unittest.TestCase):
    def _write_gate(self, payload):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "gate.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return tmp, path

    def test_untrusted_gate_source_fails_closed(self):
        tmp, path = self._write_gate({
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "execution_bias_gates": {"XAUUSD": "LONG_ONLY"},
        })
        try:
            bridge = ExecutionBiasBridge(path)
            allowed, _ = bridge.is_trade_allowed("XAUUSD", "BUY")
            self.assertFalse(allowed)
        finally:
            tmp.cleanup()

    def test_stale_gate_fails_closed(self):
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=61)
        tmp, path = self._write_gate({
            "timestamp": old.isoformat(),
            "deterministic_gate_source": "deterministic_metrics_only",
            "deterministic_execution_bias_gates": {"XAUUSD": "LONG_ONLY"},
        })
        try:
            bridge = ExecutionBiasBridge(path)
            allowed, _ = bridge.is_trade_allowed("XAUUSD", "BUY")
            self.assertFalse(allowed)
        finally:
            tmp.cleanup()

    def test_valid_deterministic_gate_controls_direction(self):
        tmp, path = self._write_gate({
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "deterministic_gate_source": "deterministic_metrics_only",
            "deterministic_execution_bias_gates": {"XAUUSD": "LONG_ONLY"},
        })
        try:
            bridge = ExecutionBiasBridge(path)
            self.assertTrue(bridge.is_trade_allowed("XAUUSD", "BUY")[0])
            self.assertFalse(bridge.is_trade_allowed("XAUUSD", "SELL")[0])
        finally:
            tmp.cleanup()

    def test_unknown_symbol_fails_closed(self):
        tmp, path = self._write_gate({
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "deterministic_gate_source": "deterministic_metrics_only",
            "deterministic_execution_bias_gates": {"XAUUSD": "LONG_ONLY"},
        })
        try:
            bridge = ExecutionBiasBridge(path)
            self.assertFalse(bridge.is_trade_allowed("UNKNOWN", "BUY")[0])
        finally:
            tmp.cleanup()

    def test_workflow_gate_boundary_ignores_llm_gate_values(self):
        metrics = {
            "cross_pairs_analysis": {
                "event_freeze": {"active": False},
                "cross_gates": {"XAUUSD": "LONG_ONLY"},
            },
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "btc_decoupling_analysis": {"recommended_btc_gate": "LONG_ONLY_ALLOWED_IF_DEBASEMENT"},
        }
        gates = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(gates["execution_bias_gates"]["XAUUSD"], "NEUTRAL_RANGE")
        self.assertEqual(gates["source"], "deterministic_metrics_only")
        self.assertTrue(gates["llm_execution_gates_ignored"])


    def test_xau_gate_uses_real_yield_regime(self):
        metrics = {
            "real_yield_info": {"real_yield_pct": 2.10},
            "yield_curve": {"regime": "Range-bound Slope", "delta_10y_5d_bps": 2.0},
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "cross_pairs_analysis": {"event_freeze": {"active": False}, "cross_gates": {}},
            "btc_decoupling_analysis": {"recommended_btc_gate": "LONG_ONLY_ALLOWED_IF_DEBASEMENT"},
            "equity_short_regime": {"equity_short_allowed": False},
        }
        result = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(result["base_gates"]["XAUUSD"], "NEUTRAL_RANGE")

    def test_xau_gate_can_be_long_when_real_yield_is_supportive(self):
        metrics = {
            "real_yield_info": {"real_yield_pct": 0.80},
            "yield_curve": {"regime": "Range-bound Slope", "delta_10y_5d_bps": 1.0},
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "cross_pairs_analysis": {"event_freeze": {"active": False}, "cross_gates": {}},
            "liquidity_dynamics": {"delta_liquidity_billion": 10.0},
            "btc_decoupling_analysis": {"recommended_btc_gate": "LONG_ONLY_ALLOWED_IF_DEBASEMENT"},
            "equity_short_regime": {"equity_short_allowed": False},
        }
        result = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(result["base_gates"]["XAUUSD"], "LONG_ONLY")

    def test_eurusd_uses_euro_area_policy_evidence(self):
        metrics = {
            "real_yield_info": {"real_yield_pct": 1.5},
            "yield_curve": {"regime": "Range-bound Slope", "delta_10y_5d_bps": 1.0},
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "btc_decoupling_analysis": {"recommended_btc_gate": "LONG_ONLY_ALLOWED_IF_DEBASEMENT"},
            "cross_pairs_analysis": {"event_freeze": {"active": False}, "cross_gates": {}},
            "terms_of_trade_energy_analysis": {"eurusd_energy_penalty": False},
            "transatlantic_analysis": {"spread_bps": 190.0},
            "dxy_trend_analysis": {"delta_20d_pct": 0.80},
            "economic_regime_snapshot": {
                "euro_area_macro": {
                    "us_minus_ecb_policy_spread_bps": 165.0,
                    "hicp_direction": "FALLING",
                }
            },
            "equity_short_regime": {"equity_short_allowed": False},
        }
        result = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(result["base_gates"]["EURUSD"], "SHORT_ONLY")

    def test_eurusd_requires_dollar_confirmation_for_short(self):
        metrics = {
            "real_yield_info": {"real_yield_pct": 1.5},
            "yield_curve": {"regime": "Range-bound Slope", "delta_10y_5d_bps": 1.0},
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "btc_decoupling_analysis": {"recommended_btc_gate": "LONG_ONLY_ALLOWED_IF_DEBASEMENT"},
            "cross_pairs_analysis": {"event_freeze": {"active": False}, "cross_gates": {}},
            "terms_of_trade_energy_analysis": {"eurusd_energy_penalty": False},
            "transatlantic_analysis": {"spread_bps": 190.0},
            "dxy_trend_analysis": {"delta_20d_pct": 0.20},
            "equity_short_regime": {"equity_short_allowed": False},
        }
        result = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(result["base_gates"]["EURUSD"], "NEUTRAL_RANGE")

        metrics["dxy_trend_analysis"]["delta_20d_pct"] = 0.80
        result = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(result["base_gates"]["EURUSD"], "SHORT_ONLY")

    def test_eurusd_can_be_long_only_with_two_bullish_conditions(self):
        metrics = {
            "real_yield_info": {"real_yield_pct": 1.0},
            "yield_curve": {"regime": "Range-bound Slope", "delta_10y_5d_bps": 1.0},
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "btc_decoupling_analysis": {"recommended_btc_gate": "LONG_ONLY_ALLOWED_IF_DEBASEMENT"},
            "cross_pairs_analysis": {"event_freeze": {"active": False}, "cross_gates": {}},
            "terms_of_trade_energy_analysis": {"eurusd_energy_penalty": False},
            "transatlantic_analysis": {"spread_bps": -20.0},
            "dxy_trend_analysis": {"delta_20d_pct": -0.80},
            "economic_regime_snapshot": {
                "euro_area_macro": {
                    "us_minus_ecb_policy_spread_bps": 80.0,
                    "hicp_direction": "RISING",
                }
            },
            "equity_short_regime": {"equity_short_allowed": False},
        }
        result = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(result["base_gates"]["EURUSD"], "LONG_ONLY")

    def test_gbpusd_requires_uk_policy_confirmation(self):
        metrics = {
            "real_yield_info": {"real_yield_pct": 1.0},
            "yield_curve": {"regime": "Range-bound Slope", "delta_10y_5d_bps": 1.0},
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "btc_decoupling_analysis": {"recommended_btc_gate": "NEUTRAL_RANGE"},
            "cross_pairs_analysis": {
                "event_freeze": {"active": False},
                "cross_gates": {"GBPUSD": "SHORT_ONLY"},
            },
            "terms_of_trade_energy_analysis": {"eurusd_energy_penalty": False},
            "transatlantic_analysis": {"spread_bps": 100.0},
            "dxy_trend_analysis": {"delta_20d_pct": 0.80},
            "liquidity_dynamics": {"delta_liquidity_billion": 10.0},
            "financial_conditions_analysis": {"nfci_value": -0.2},
            "credit_spread_analysis": {"stress_level": "Sakin / Düşük Kredi Stresi"},
            "economic_regime_snapshot": {
                "uk_policy": {"us_minus_uk_policy_spread_bps": 10.0}
            },
            "equity_short_regime": {"equity_short_allowed": False},
        }
        result = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(result["base_gates"].get("GBPUSD"), "NEUTRAL_RANGE")

        metrics["economic_regime_snapshot"]["uk_policy"]["us_minus_uk_policy_spread_bps"] = 50.0
        metrics["cross_pairs_analysis"]["cross_gates"]["GBPUSD"] = "SHORT_ONLY"
        result = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(result["base_gates"]["GBPUSD"], "SHORT_ONLY")

    def test_workflow_event_freeze_overrides_base_gate(self):
        metrics = {
            "cross_pairs_analysis": {
                "event_freeze": {"active": True},
                "cross_gates": {"XAUUSD": "LONG_ONLY", "EURUSD": "SHORT_ONLY"},
            },
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "btc_decoupling_analysis": {"recommended_btc_gate": "LONG_ONLY_ALLOWED_IF_DEBASEMENT"},
        }
        gates = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(gates["execution_bias_gates"]["XAUUSD"], "NO_TRADE")
        self.assertEqual(gates["execution_bias_gates"]["EURUSD"], "NO_TRADE")

    def test_spx_can_be_long_only_in_reflationary_benign_credit_regime(self):
        metrics = {
            "equity_short_regime": {"equity_short_allowed": False},
            "credit_spread_analysis": {"hy_oas_spread_pct": 2.68, "stress_level": "Sakin / Düşük Risk"},
            "financial_conditions_analysis": {"nfci_value": -0.56},
            "liquidity_dynamics": {"delta_liquidity_billion": 77.2},
            "cycle_diagnosis": {"primary_regime": "Reflationary Growth with High Real Rates"},
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "cross_pairs_analysis": {"event_freeze": {"active": False}, "cross_gates": {}},
            "btc_decoupling_analysis": {"recommended_btc_gate": "NEUTRAL_RANGE"},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
        }
        gates = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(gates["execution_bias_gates"]["SPX"], "LONG_ONLY")

    def test_btc_can_be_long_only_with_liquidity_expansion_and_loose_nfci(self):
        metrics = {
            "real_yield_info": {"real_yield_pct": 2.68},
            "liquidity_dynamics": {"delta_liquidity_billion": 77.2},
            "financial_conditions_analysis": {"nfci_value": -0.56},
            "yield_curve": {"regime": "Range-bound Slope", "delta_10y_5d_bps": 2.0},
            "t0_fast_stress_analysis": {"fast_stress_override": False},
            "gold_fiscal_dominance": {"gold_short_allowed": False},
            "cross_pairs_analysis": {"event_freeze": {"active": False}, "cross_gates": {}},
            "btc_decoupling_analysis": {"recommended_btc_gate": "LONG_ONLY_ALLOWED_IF_DEBASEMENT"},
            "equity_short_regime": {"equity_short_allowed": False},
        }
        gates = MacroWorkflowEngine._build_deterministic_gates(metrics)
        self.assertEqual(gates["execution_bias_gates"]["BTC"], "LONG_ONLY")

