import pandas as pd
import numpy as np
from classic import trade_day,opening_features

def setup(direction=1):
    start=pd.Timestamp('2025-01-15 08:00Z')
    f=pd.DataFrame({'datetime':pd.date_range(start+pd.Timedelta(minutes=15),pd.Timestamp('2025-01-15 16:00Z'),freq='min',inclusive='left'),
        'open':1.,'high':1.0001,'low':.9999,'close':1.})
    return f,dict(start=start,high=1.001,low=.999,direction=direction,rvol=1.)

def test_fill_bar_both_sides_assumes_stop_and_charges_actual_price_cost():
    f,c=setup();f.loc[0,['high','low']]=[1.02,.98]
    r=trade_day('EUR/USD',f,'2025-01-15',c)
    assert r['reason']=='SL' and r['net_r']<-1

def test_entry_bar_target_not_credited_then_next_bar_can_take_target():
    f,c=setup();f.loc[0,['open','high','low','close']]=[1.001,1.01,1.,1.002]
    f.loc[1,['open','high','low','close']]=[1.002,1.01,1.001,1.005]
    r=trade_day('EUR/USD',f,'2025-01-15',c)
    assert r['reason']=='TP2' and pd.Timestamp(r['exit_at'])==f.iloc[1].datetime+pd.Timedelta(minutes=1)
    assert 1.9<r['net_r']<2

def test_missing_minute_is_unknown_and_no_late_entry_allowed():
    f,c=setup()
    assert trade_day('EUR/USD',f.drop(index=3),'2025-01-15',c)['status']=='INCOMPLETE_SESSION'
    f.loc[f.datetime>=pd.Timestamp('2025-01-15 12:00Z'),'high']=1.02
    assert trade_day('EUR/USD',f,'2025-01-15',c)['status']=='NO_BREAK_BEFORE_NOON'

def test_gap_stop_uses_worse_open_and_eod_does_not_hold_overnight():
    f,c=setup();f.loc[0,['open','high','low','close']]=[1.001,1.002,1.,1.001]
    f.loc[1,['open','high','low','close']]=[.995,.996,.994,.995]
    assert trade_day('EUR/USD',f,'2025-01-15',c)['net_r']<-2
    f,c=setup();f.loc[0,['open','high','low','close']]=[1.001,1.002,1.,1.001]
    r=trade_day('EUR/USD',f,'2025-01-15',c)
    assert r['reason']=='EOD' and pd.Timestamp(r['exit_at']).hour==16

def test_same_clock_volume_excludes_today_and_future():
    times=pd.date_range('2024-12-01 08:00Z',periods=60,freq='D')
    f=pd.DataFrame(dict(datetime=times,open=1.,high=1.1,low=.9,close=1.01,volume=100.))
    today=pd.Timestamp('2025-01-15 08:00Z');f.loc[f.datetime==today,'volume']=200
    g=f.copy();g.loc[g.datetime>today,'volume']=100000
    assert opening_features(f,'2025-01-15')['rvol']==2
    assert opening_features(g,'2025-01-15')['rvol']==2

def test_short_direction_has_ask_stop_and_costs():
    f,c=setup(-1);f.loc[0,['open','high','low','close']]=[.999,1.002,.998,1.]
    r=trade_day('USD/CHF',f,'2025-01-15',c)
    assert r['reason']=='SL' and r['net_r']<-1
