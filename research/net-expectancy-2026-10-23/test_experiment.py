import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('net_research_experiment', Path(__file__).with_name('experiment.py'))
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)
price_spec = importlib.util.spec_from_file_location('research_price_rules', Path(__file__).with_name('price_rules.py'))
price_rules = importlib.util.module_from_spec(price_spec)
price_spec.loader.exec_module(price_rules)


def signal(long=True):
    sign = 1 if long else -1
    return dict(symbol='EUR/USD', strategy='ORB_SESSION_BREAKOUT',
                direction='LONG' if long else 'SHORT', entry=100.,
                stop_loss=100.-sign*1.2, tp1=100.+sign*1.44, tp2=100.+sign*2.4,
                orb_high=100. if long else 102., orb_low=98. if long else 100.)


@pytest.mark.parametrize('long', [True, False])
def test_buffer_reduction_preserves_entry_targets_and_structure(long):
    s = signal(long)
    changed, reason = experiment.transform(s, 'half_structural_buffer')
    assert reason is None
    assert changed['entry'] == s['entry'] and changed['tp1'] == s['tp1'] and changed['tp2'] == s['tp2']
    anchor = (s['orb_high']+s['orb_low'])/2
    assert (changed['stop_loss'] < anchor if long else changed['stop_loss'] > anchor)
    assert changed['risk_pips'] < changed['_research_original_risk']
    assert s['stop_loss'] == pytest.approx(98.8 if long else 101.2)


def test_target_extension_preserves_entry_stop_and_first_target():
    s = signal()
    changed, _ = experiment.transform(s, 'target_3r')
    assert changed['entry'] == s['entry'] and changed['stop_loss'] == s['stop_loss']
    assert changed['tp1'] == s['tp1']
    assert changed['tp2'] == pytest.approx(103.6)


def test_cost_cap_uses_available_spread_and_never_creates_entry(monkeypatch):
    s = signal()
    monkeypatch.setattr(experiment.tracking, 'get_friction_config', lambda symbol: {'spread_ratio':.01})
    changed, reason = experiment.transform(s, 'spread_risk_cap')
    assert changed is None and reason


@pytest.mark.parametrize('long', [True, False])
def test_target_rounding_never_weakens_minimum_rr_or_changes_entry(long):
    s = dict(direction='LONG' if long else 'SHORT',entry=1.0307,
             stop_loss=1.0291 if long else 1.0323,
             tp1=1.0326 if long else 1.0288,tp2=1.0338 if long else 1.0276)
    fixed = price_rules.normalize_targets(s, .00001)
    assert fixed['entry'] == s['entry'] and fixed['stop_loss'] == s['stop_loss']
    risk=abs(s['entry']-s['stop_loss'])
    assert abs(fixed['tp1']-s['entry'])/risk >= 1.2-1e-9
    assert abs(fixed['tp2']-s['entry'])/risk >= 2.-1e-9
    assert s['tp1'] == (1.0326 if long else 1.0288)
