import json
import sys
from types import SimpleNamespace

import pytest

from macro_engine.calibration.research_api_diagnostics import (
    record_provider_outcomes, ResearchDailyQuotaExhausted,
)


@pytest.mark.parametrize('enabled,code,message,expected', [
    ('1', 429, 'GenerateRequestsPerDay private_test_key', ResearchDailyQuotaExhausted),
    ('0', 429, 'GenerateRequestsPerDay private_test_key', RuntimeError),
    ('1', 429, 'GenerateRequestsPerMinute private_test_key', RuntimeError),
    ('1', 503, 'Temporary unavailable private_test_key', RuntimeError),
])
def test_only_daily_quota_aborts_bounded_research(tmp_path, monkeypatch, enabled, code, message, expected):
    error = RuntimeError(message)
    error.code = code
    def generate(**kwargs):
        raise error
    factory = lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    manager = SimpleNamespace(genai=SimpleNamespace(Client=factory))
    monkeypatch.setitem(sys.modules, 'core', SimpleNamespace(key_manager=manager))
    monkeypatch.setenv('BEGONYA_RESEARCH_STOP_ON_DAILY_QUOTA', enabled)
    with record_provider_outcomes(tmp_path, SimpleNamespace(keys=['private_test_key'])):
        with pytest.raises(expected):
            manager.genai.Client().models.generate_content(model='original_model', contents='original_prompt')
    saved = (tmp_path/'research_provider_attempts.jsonl').read_text()
    assert 'private_test_key' not in saved
    record = json.loads(saved)
    assert record['code'] == code and record['model'] == 'original_model'
