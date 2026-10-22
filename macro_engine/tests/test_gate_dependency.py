from unittest.mock import patch
import pytest
from calibration.gate_dependency import guaranteed_rejection
from graph.macro_graph import MacroWorkflowEngine
from sfp_orb_engine.macro_gate_client import MacroGateClient


@pytest.mark.parametrize('bias',['NEUTRAL_RANGE','SHORT_ONLY','DEFENSIVE_HOLD','NO_TRADE','CASH'])
@pytest.mark.parametrize('preserve',[False,True])
@pytest.mark.parametrize('risk',[0.0,0.25,0.8,1.0])
def test_proved_long_rejection_is_rejected_by_original_client_for_every_model_control(bias,preserve,risk):
    with patch.object(MacroWorkflowEngine,'_build_deterministic_gates',return_value={'execution_bias_gates':{'EURUSD':bias}}):
        assert guaranteed_rejection({},'EUR/USD','LONG') is not None
    client=MacroGateClient.__new__(MacroGateClient)
    client.get_macro_state=lambda:{'active':True,'execution_bias_gates':{'EURUSD':bias},'deterministic_bias_gates':{},
        'gate_conviction_multipliers':{'EURUSD':1.15},'risk_multiplier':risk,'capital_preservation_mode':preserve}
    assert client.evaluate_gate('EUR/USD','LONG')['allowed'] is False


def test_possible_approval_never_gets_a_fabricated_model_control():
    with patch.object(MacroWorkflowEngine,'_build_deterministic_gates',return_value={'execution_bias_gates':{'EURUSD':'LONG_ONLY'}}):
        assert guaranteed_rejection({},'EUR/USD','LONG') is None
