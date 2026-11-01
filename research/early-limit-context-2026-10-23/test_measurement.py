import pandas as pd
import pytest
from measurement import context,decision_measurement

AT=pd.Timestamp('2025-01-02 09:00Z')
S=dict(symbol='EUR/USD',direction='LONG',entry=1.1,stop_loss=1.099,tp1=1.1012,tp2=1.102)


def data():
    f=pd.DataFrame(dict(time=[AT-pd.Timedelta(seconds=60),AT-pd.Timedelta(seconds=1)],bid=[1.1,1.1001],ask=[1.10005,1.10015]))
    m=pd.DataFrame([dict(datetime=AT-pd.Timedelta(minutes=1),open=1.1,high=1.1001,low=1.1,close=1.1001,volume=2)])
    return f,m


def test_uses_only_quote_available_at_decision():
    f,m=data();before=decision_measurement(S,AT,f,m,.00001)
    f=pd.concat([f,pd.DataFrame([dict(time=AT+pd.Timedelta(seconds=1),bid=2.,ask=2.5)])],ignore_index=True)
    after=decision_measurement(S,AT,f,m,.00001)
    assert before==after and before['spread_pips']==pytest.approx(.5)


def test_clock_mismatch_unpriced():
    f,m=data();m['high']=1.102
    assert decision_measurement(S,AT,f,m,.00001)['reason']=='BID_CLOCK_OR_PRICE_MISMATCH'


def test_old_quote_not_forward_filled():
    f,m=data();f=f.iloc[:1]
    assert decision_measurement(S,AT,f,m,.00001)['reason']=='STALE_DECISION_QUOTE'


def test_crossed_quote_rejected():
    f,m=data();f.loc[0,'ask']=1.
    assert decision_measurement(S,AT,f,m,.00001)['reason']=='INVALID_QUOTES'


def test_no_clock_reference_not_assumed_valid():
    f,m=data();m=m.iloc[:0]
    assert decision_measurement(S,AT,f,m,.00001)['status']=='UNPRICED'


def test_zero_spread_does_not_make_commission_free():
    f,m=data();f['ask']=f.bid
    r=decision_measurement(S,AT,f,m,.00001)
    assert r['spread_pips']==0 and r['total_cost_budget_r']>0


def test_local_clock_handles_summer():
    c=dict(available_at='2025-06-02 08:00Z',htf_aligned=True,signal=dict(london_context=dict(asia_atr_ratio=.35)))
    r=context(c)
    assert r['timing']=='09_TO_NOON' and r['asia']=='LE_0_35_ATR'


def test_missing_compression_unknown():
    c=dict(available_at='2025-01-02 08:30Z',htf_aligned=False,signal={})
    assert context(c)['asia']=='UNKNOWN'
