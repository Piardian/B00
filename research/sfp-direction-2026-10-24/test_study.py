import numpy as np
import pandas as pd
import pytest
from study import direction,quote_score,merge

AT=pd.Timestamp('2025-02-03 08:00',tz='UTC')

def signal(long=True):
    return dict(symbol='EUR/USD',direction='LONG' if long else 'SHORT',entry=1.1,
                stop_loss=1.099 if long else 1.101,market_close_entry=1.1005)

def tape(bid=1.1005,spread=.0001):
    times=pd.date_range(AT,periods=18001,freq='s')
    return pd.DataFrame(dict(time=times,bid=np.full(len(times),bid),ask=np.full(len(times),bid+spread)))

def test_direction_exact_horizon_and_not_original_limit_fill():
    f=pd.DataFrame(dict(datetime=pd.date_range(AT,periods=5,freq='15min'),close=[1.1,1.1,1.1,1.1015,99.]))
    r=direction(signal(),AT,f)
    assert r['signed_r']==pytest.approx(1.)
    assert r['future_bid']==1.1015
    # Future bar mutations beyond the fixed horizon must not affect the result.
    f.loc[4,'close']=-99
    assert direction(signal(),AT,f)==r

def test_missing_forward_bar_is_unknown():
    f=pd.DataFrame(dict(datetime=pd.date_range(AT,periods=4,freq='15min'),close=[1.1]*4)).drop(index=1)
    assert direction(signal(),AT,f)['signed_r'] is None

def test_bid_touch_without_ask_penetration_is_not_long_fill():
    f=tape(bid=1.09995,spread=.0001)
    assert quote_score(signal(),AT,f)['status']=='NO_FILL'

def test_quote_coverage_cannot_be_replaced_with_no_fill():
    f=tape().iloc[:3601]
    assert quote_score(signal(),AT,f)['status']=='UNRESOLVED_COVERAGE'

def test_long_nominal_entry_fee_and_slip():
    f=tape();f.loc[60,['bid','ask']]=[1.0998,1.0999]
    r=quote_score(signal(),AT,f)
    assert r['status']=='FILLED_MARKOUT'
    assert r['wait_minutes']==1
    assert r['price_markout_r']==pytest.approx(.5)
    assert r['commission_r']==pytest.approx(.04)
    assert r['slip_r']==pytest.approx(.02)
    assert r['net_markout_r']==pytest.approx(.44)

def test_short_exit_uses_ask_and_stress_changes_exit():
    f=tape(bid=1.0995,spread=.0001);f.loc[60,['bid','ask']]=[1.1001,1.1002]
    r=quote_score(signal(False),AT,f)
    assert r['price_markout_r']==pytest.approx(.4)
    assert quote_score(signal(False),AT,f,stress=1.5)['net_markout_r']<r['net_markout_r']

def test_stop_crossing_flag_is_not_hidden_by_positive_markout():
    f=tape();f.loc[60,['bid','ask']]=[1.0998,1.0999];f.loc[100,['bid','ask']]=[1.0988,1.0989]
    r=quote_score(signal(),AT,f)
    assert r['original_stop_crossed'] is True
    assert r['net_markout_r']>0

def test_quote_gap_unresolved_even_if_fill_before_gap():
    f=tape();f.loc[60,['bid','ask']]=[1.0998,1.0999]
    f=f.drop(index=range(100,200))
    assert quote_score(signal(),AT,f)['status']=='UNRESOLVED_QUOTE_GAP'

def test_duplicate_price_conflict_detected():
    a=pd.DataFrame(dict(datetime=[AT],open=[1.],high=[2.],low=[.5],close=[1.5],volume=[1]))
    b=a.copy();b['close']=1.6
    _,n=merge([a,b]);assert n==1

def test_fill_at_expiry_not_allowed():
    f=tape();f.loc[14400,['bid','ask']]=[1.0998,1.0999]
    assert quote_score(signal(),AT,f)['status']=='NO_FILL'

def test_resolved_fill_needs_only_terminal_horizon():
    f=tape();f.loc[60,['bid','ask']]=[1.0998,1.0999]
    assert quote_score(signal(),AT,f.iloc[:3661])['status']=='FILLED_MARKOUT'

def test_no_fill_needs_expiry_not_extra_unused_hour():
    assert quote_score(signal(),AT,tape().iloc[:14401])['status']=='NO_FILL'

def test_quote_gap_after_terminal_cannot_erase_known_markout():
    f=tape();f.loc[60,['bid','ask']]=[1.0998,1.0999]
    f=f.drop(index=range(4000,4100))
    assert quote_score(signal(),AT,f)['status']=='FILLED_MARKOUT'
