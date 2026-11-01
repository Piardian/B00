import ast
from pathlib import Path
import importlib.util
import sys

# Several frozen experiments intentionally use study.py; isolate imports when
# pytest collects them together instead of sharing the first study module.
base=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('seasonal_study_under_test',base/'study.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
prior=sys.modules.get('study')
try:
    sys.modules['study']=s
    spec=importlib.util.spec_from_file_location('seasonal_cost_gate_under_test',base/'cost_gate.py')
    c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
finally:
    if prior is None:sys.modules.pop('study',None)
    else:sys.modules['study']=prior

def test_cost_gate_ignores_future_outcomes_and_has_fixed_boundary():
    out=dict(initial_risk=10,assumed_commission_usd_per_lot_roundtrip=8,net_r=2,exit=99999)
    a=c.decision(out,.2,1)
    assert a[0] and abs(a[1]-.038)<1e-12
    out.update(net_r=-999,exit=0)
    assert c.decision(out,.2,1)==a
    assert not c.decision(out,.4,1)[0]

def test_gate_cost_stress_cannot_improve_projected_cost_at_same_risk():
    out=dict(initial_risk=10,assumed_commission_usd_per_lot_roundtrip=8)
    assert c.decision(out,.2,2)[1]>c.decision(out,.2,1)[1]

def test_calendar_not_labeled_two_full_years_and_no_adaptive_season():
    assert len(s.MONTHS)==21 and s.MONTHS[0]=='2025-01' and s.MONTHS[-1]=='2026-09'
    assert len(s.MONTHS[:12])==12 and len(s.MONTHS[12:])==9
    assert len(set(s.g.dates(s.MONTHS)))==len(s.g.dates(s.MONTHS))

def test_new_collector_calls_only_data_apis():
    tree=ast.parse(Path(s.__file__).read_text())
    calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Attribute) and n.func.value.attr=='mt5'}
    assert calls<={'initialize','last_error','account_info','terminal_info','copy_rates_range','copy_ticks_range','shutdown'}
    assert 'copy_ticks_range' in calls
