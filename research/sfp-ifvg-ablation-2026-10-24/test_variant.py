import copy
import importlib
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parent

def modules():
    import measure
    return measure.engine()

def valid():
    return dict(symbol='EUR/USD',direction='LONG',entry=1.1,stop_loss=1.099,tp1=1.1012,tp2=1.102,
        htf_trend='BULLISH',grade='AAA',strategy='SFP_IFVG_BREAKER',breaker_confirmed=True,
        ifvg_confirmed=False,entry_source='SWEEP_WICK_50_CE')

def test_only_the_declared_flag_changes():
    baseline=HERE.parent/'sfp-direction-2026-10-24/frozen_engine'
    for p in baseline.glob('*.py'):
        other=HERE/'frozen_engine'/p.name
        if p.name=='config.py':
            assert other.read_text(encoding='utf8')==p.read_text(encoding='utf8').replace('USE_IFVG_ENTRY = True','USE_IFVG_ENTRY = False')
        else:assert other.read_bytes()==p.read_bytes()

def test_flags_and_existing_midpoint_are_preserved():
    c,d,e=modules()
    assert not c.USE_IFVG_ENTRY and not d.USE_IFVG_ENTRY
    assert c.REQUIRE_STRUCTURAL_BREAKER and c.REQUIRE_PRO_TREND_AAA
    assert c.ENTRY_MODEL=='MIDPOINT' and c.LIMIT_EXPIRY_BARS==16
    assert e.validate_signal(valid()) is None

def test_breaker_still_required():
    c,d,e=modules();v=valid();v['breaker_confirmed']=False
    assert e.validate_signal(v)=='BREAKER_REQUIRED'

def test_trend_still_required():
    c,d,e=modules();v=valid();v['htf_trend']='BEARISH'
    assert e.validate_signal(v)=='HTF_TREND_REQUIRED'

def test_missing_breaker_does_not_get_rescued_by_ifvg(monkeypatch):
    modules();st=importlib.import_module('frozen_engine.strict_setup')
    monkeypatch.setattr(st,'detect_structural_breaker_long',lambda *a:False)
    monkeypatch.setattr(st,'detect_ifvg_long',lambda *a:(1.,2.))
    assert st.confirm_structure('LONG',3,4,[1]*5,[1]*5,[1]*5,[1]*5,.1,True,False) is None

def test_existing_sweep_wick_helper_is_used():
    modules();em=importlib.import_module('frozen_engine.entry_mechanics')
    v=em.calculate_ce_entry(direction='LONG',peak_or_valley=1.099,trigger_price=1.1003,
        close_price=1.1005,fvg_range=None,atr=.001,sl_buffer_atr=.15,
        entry_model='MIDPOINT',tp1_r=1.2,tp2_r=2.)
    assert v['entry_source']=='SWEEP_WICK_50_CE'
    assert v['entry_price']==pytest.approx((1.099+1.1005)/2)
    assert v['stop_loss']<v['entry_price']<v['tp1']<v['tp2']
