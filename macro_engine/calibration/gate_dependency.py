"""Prove rejections independent of LLM outputs; never manufacture an approval."""
from graph.macro_graph import MacroWorkflowEngine
from sfp_orb_engine.macro_gate_client import MacroGateClient

_normalizer=MacroGateClient.__new__(MacroGateClient)


def guaranteed_rejection(processed_metrics,symbol,direction):
    gates=MacroWorkflowEngine._build_deterministic_gates(processed_metrics)['execution_bias_gates']
    normalized=_normalizer._normalize_symbol(symbol)
    expected='LONG_ONLY' if direction=='LONG' else 'SHORT_ONLY'
    if normalized=='SOL':
        parent=gates.get('BTC','NEUTRAL_RANGE')
        if parent!=expected:
            return {'basis':'Original rotation target direction cannot approve this side from the BTC parent',
                    'parent_gate':parent,'symbol':symbol,'direction':direction}
        return None
    bias=gates.get(normalized,'NEUTRAL_RANGE')
    if bias!=expected:
        return {'basis':'Original deterministic export and MacroGateClient reject this side for every capital-preservation flag and risk multiplier',
                'deterministic_bias':bias,'symbol':symbol,'direction':direction}
    return None
