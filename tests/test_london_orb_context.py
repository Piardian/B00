from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from sfp_orb_engine import config
from sfp_orb_engine.orb_detector import ORBDetector
from sfp_orb_engine.orb_session_context import prior_daily_atr,london_bounds,london_context

def history(day='2025-06-16'):
    end=pd.Timestamp(day,tz='UTC')
    times=pd.date_range(end=end-pd.Timedelta(hours=1),periods=40*24,freq='h')
    return pd.DataFrame(dict(datetime=times,open=1.,high=1.1,low=.9,close=1.,volume=100.))

def bars(day='2025-06-16',direction='LONG'):
    start,orb_end,_=london_bounds(day,config.ORB_SESSIONS['LONDON'],15)
    times=pd.date_range(pd.Timestamp(day,tz='UTC'),orb_end,freq='15min')
    f=pd.DataFrame(dict(datetime=times,open=1.,high=1.01,low=.99,close=1.,volume=100.))
    f.loc[len(f)-1,['open','high','low','close']]=[1.,1.04,.999,1.039] if direction=='LONG' else [1.,1.001,.96,.961]
    return f

@pytest.mark.parametrize('day,hour',[('2025-01-15',8),('2025-06-16',7),('2025-03-28',8),('2025-10-27',8)])
def test_dst_and_halfopen_range(day,hour):
    f=bars(day);now=f.iloc[-1].datetime+pd.Timedelta(minutes=15)
    c=london_context(f,history(day),config.ORB_SESSIONS['LONDON'],15,now)
    assert c is not None and len(c['orb'])==1 and c['start'].hour==hour
    assert c['post'].iloc[-1].datetime==c['end']

def test_atr_uses_completed_days_not_current_or_future_prices():
    day=pd.Timestamp('2025-06-16',tz='UTC');h=history()
    expected=prior_daily_atr(h,day)
    poison=pd.DataFrame(dict(datetime=pd.date_range(day,periods=48,freq='h'),open=1.,high=999.,low=.001,close=900.))
    assert np.isclose(expected,.2)
    assert prior_daily_atr(pd.concat([h,poison]),day)==expected

@pytest.mark.parametrize('direction',['LONG','SHORT'])
def test_detector_reaches_valid_london_break(direction):
    f=bars(direction=direction)
    d=ORBDetector(volume_detector=SimpleNamespace(analyze=lambda *a,**kw:{'spike_ratio':2.1}))
    result=d.detect_orb(f,'EUR/USD',hourly_history=history(),as_of=f.iloc[-1].datetime+pd.Timedelta(minutes=15))
    assert result and result['direction']==direction
    assert result['london_context']['version']=='daily-atr14-v1'
    assert result['orb_high']==1.01 and result['orb_low']==.99

def test_volume_minimum_is_now_a_real_veto():
    f=bars();d=ORBDetector(volume_detector=SimpleNamespace(analyze=lambda *a,**kw:{'spike_ratio':1.8}))
    assert d.detect_orb(f,'EUR/USD',hourly_history=history(),as_of=f.iloc[-1].datetime+pd.Timedelta(minutes=15)) is None

def test_missing_history_or_asian_bars_never_bypasses_filter():
    f=bars();now=f.iloc[-1].datetime+pd.Timedelta(minutes=15);session=config.ORB_SESSIONS['LONDON']
    assert london_context(f,None,session,15,now) is None
    assert london_context(f.drop(index=3),history(),session,15,now) is None
    assert prior_daily_atr(history().tail(100),pd.Timestamp('2025-06-16',tz='UTC')) is None

def test_orb_cannot_include_incomplete_trigger():
    f=bars();now=f.iloc[-1].datetime+pd.Timedelta(minutes=5)
    assert london_context(f,history(),config.ORB_SESSIONS['LONDON'],15,now) is None

def test_too_wide_asia_is_still_rejected():
    f=bars();f.loc[f.datetime.dt.hour<6,['high','low']]=[1.2,.8]
    assert london_context(f,history(),config.ORB_SESSIONS['LONDON'],15,f.iloc[-1].datetime+pd.Timedelta(minutes=15)) is None

def test_h1_gap_true_range_and_duplicate_history():
    h=history();day=pd.Timestamp('2025-06-16',tz='UTC')
    h.loc[h.datetime>=day-pd.Timedelta(days=1),['open','high','low','close']]=[1.5,1.6,1.4,1.5]
    assert prior_daily_atr(h,day)>.2
    assert prior_daily_atr(pd.concat([h,h.iloc[[-1]]]),day) is None
