from copy import deepcopy
from decimal import Decimal
import pytest
from price_grid import normalize_for_research,FIELDS

def original(long=True,gold=False):
    if gold:
        return dict(direction='LONG',entry=3000.005,stop_loss=2998.713333,
                    tp1=3001.5550004,tp2=3002.588334,metadata={'unchanged':[1]})
    if long:
        return dict(direction='LONG',entry=1.100005,stop_loss=1.099337,
                    tp1=1.1008066,tp2=1.101341,metadata={'unchanged':[1]})
    return dict(direction='SHORT',entry=1.100005,stop_loss=1.100673,
                tp1=1.0992034,tp2=1.098669,metadata={'unchanged':[1]})

def check_geometry(result,step):
    d={k:Decimal(str(result[k])) for k in FIELDS};e=d['entry'];sl=d['stop_loss'];risk=abs(e-sl)
    for value in d.values():assert value/Decimal(step)==(value/Decimal(step)).to_integral_value()
    assert abs(d['tp1']-e)/risk>=Decimal('1.2')
    assert abs(d['tp2']-e)/risk>=Decimal('2.0')

def test_long_adverse_entry_outward_stop_and_recomputed_targets():
    source=original();before=deepcopy(source)
    result=normalize_for_research(source,'0.00001')
    assert source==before
    assert result['entry']>source['entry'] and result['stop_loss']<source['stop_loss']
    check_geometry(result,'0.00001')
    assert result['research_price_grid']['original_ledger_reusable'] is False

def test_short_rounding_is_symmetric_and_not_favorable():
    source=original(False);result=normalize_for_research(source,'0.00001')
    assert result['entry']<source['entry'] and result['stop_loss']>source['stop_loss']
    check_geometry(result,'0.00001')

def test_gold_uses_its_own_step():
    source=original(gold=True);result=normalize_for_research(source,'0.01')
    assert result['entry']==3000.01 and result['stop_loss']==2998.71
    check_geometry(result,'0.01')

def test_valid_levels_are_stable_on_second_application():
    a=normalize_for_research(original(),'0.00001')
    b=normalize_for_research(a,'0.00001')
    assert {k:a[k] for k in FIELDS}=={k:b[k] for k in FIELDS}

@pytest.mark.parametrize('field,value',[('entry',float('nan')),('stop_loss',float('inf')),('tp1',-1),('tp2',0)])
def test_bad_prices_rejected(field,value):
    v=original();v[field]=value
    with pytest.raises(ValueError):normalize_for_research(v,'0.00001')

def test_invalid_ordering_is_not_repaired_into_new_strategy():
    v=original();v['stop_loss']=v['entry']+.001
    with pytest.raises(ValueError):normalize_for_research(v,'0.00001')

def test_risk_can_change_and_must_not_reuse_old_result():
    source=original();result=normalize_for_research(source,'0.00001')
    old_risk=Decimal(str(source['entry']))-Decimal(str(source['stop_loss']))
    assert Decimal(str(result['risk_distance']))>old_risk
    assert result['research_price_grid']['broker_order_acceptance_verified'] is False
