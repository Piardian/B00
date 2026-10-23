import json
from datetime import datetime, timedelta, timezone

import pytest

from sfp_orb_engine.config import MACRO_GATE_MAX_AGE_SECONDS
from sfp_orb_engine.macro_gate_client import MacroGateClient


@pytest.mark.parametrize('timestamp,allowed', [
    ('2025-01-01T12:00:00Z', True),
    ('2025-01-01T15:00:00', True),  # legacy TRT export
    ('2025-01-01T07:00:00+00:00', True),  # exact five-hour boundary
    ('2025-01-01T06:59:59Z', False),
    ('2025-01-01T12:00:01Z', False),
    ('2000-01-01T00:00:00', False),
    ('broken', False), (None, False),
])
def test_decision_timestamp_controls_entry(tmp_path, timestamp, allowed):
    path = tmp_path/'gate.json'
    path.write_text(json.dumps({'timestamp': timestamp,
                               'execution_bias_gates': {'EURUSD': 'LONG_ONLY'}}))
    now = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    client = MacroGateClient(path, now=lambda: now)
    result = client.evaluate_gate('EUR/USD', 'LONG')
    assert result['allowed'] is allowed
    if not allowed:
        assert result['risk_multiplier'] == 0


def test_same_file_expires_without_rewriting(tmp_path):
    path = tmp_path/'gate.json'
    now = datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    path.write_text(json.dumps({'timestamp': now.isoformat(),
                               'execution_bias_gates': {'EURUSD': 'LONG_ONLY'}}))
    before = path.read_bytes()
    client = MacroGateClient(path, now=lambda: now)
    assert client.evaluate_gate('EUR/USD', 'LONG')['allowed']
    now += timedelta(seconds=MACRO_GATE_MAX_AGE_SECONDS + 1)
    assert not client.evaluate_gate('EUR/USD', 'LONG')['allowed']
    assert path.read_bytes() == before
