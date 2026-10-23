from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from audit_london import geometry,clock_at,orb_detector,ORBDetector

def sample():
    dates=list(pd.date_range('2025-06-15 12:00',periods=25,freq='15min',tz='UTC'))
    dates+=list(pd.date_range('2025-06-16 07:00',periods=3,freq='15min',tz='UTC'))
    f=pd.DataFrame({'datetime':dates,'open':1.,'high':1.01,'low':.99,'close':1.,'volume':100.})
    f.loc[len(f)-2,['open','high','low','close']]=[1.,1.02,1.,1.01]
    f.loc[len(f)-1,['open','high','low','close']]=[1.01,1.05,1.009,1.049]
    return f

def test_original_15minute_range_includes_two_m15_bars():
    g=geometry(sample())
    assert g['orb_bars']==2
    assert g['direction']=='LONG'

def test_declared_twofold_volume_is_not_a_hard_veto():
    d=ORBDetector(min_vol_ratio=2.,volume_detector=SimpleNamespace(analyze=lambda *a,**k:{'spike_ratio':1.8}))
    with patch.object(orb_detector,'datetime',clock_at(pd.Timestamp('2025-06-16 07:45Z'))):
        signal=d.detect_orb(sample(),'EUR/USD')
    assert signal is not None and signal['grade']=='A+'

def test_asian_range_can_veto_an_otherwise_valid_break():
    f=sample()
    asia=pd.DataFrame({'datetime':pd.date_range('2025-06-16 00:00',periods=25,freq='15min',tz='UTC'),
        'open':1.,'high':1.015,'low':.985,'close':1.,'volume':100.})
    f=pd.concat([f,asia],ignore_index=True).sort_values('datetime').reset_index(drop=True)
    assert geometry(f)['compression_veto']
    d=ORBDetector(volume_detector=SimpleNamespace(analyze=lambda *a,**k:{'spike_ratio':3.}))
    with patch.object(orb_detector,'datetime',clock_at(pd.Timestamp('2025-06-16 07:45Z'))):
        assert d.detect_orb(f,'EUR/USD') is None

def test_london_anchor_changes_with_dst():
    assert pd.Timestamp('2025-01-15 08:00',tz='Europe/London').tz_convert('UTC').hour==8
    assert pd.Timestamp('2025-06-16 08:00',tz='Europe/London').tz_convert('UTC').hour==7

def test_future_rows_excluded_from_snapshot():
    f=sample();cut=f.iloc[-1].datetime+pd.Timedelta(minutes=15)
    future=f.iloc[[-1]].copy();future.datetime+=pd.Timedelta(minutes=15);future.high=99
    allrows=pd.concat([f,future],ignore_index=True)
    completed=allrows[allrows.datetime+pd.Timedelta(minutes=15)<=cut]
    assert geometry(completed)==geometry(f)
