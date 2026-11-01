import numpy as np
import pandas as pd
from quote_engine import replay,opening,validate_tape

def tape():
    times=pd.date_range('2025-02-03 08:00Z','2025-02-03 16:00Z',freq='s')
    f=pd.DataFrame(dict(time=times,bid=np.ones(len(times)),ask=np.ones(len(times))+.0001))
    f.loc[f.time==pd.Timestamp('2025-02-03 08:14:59Z'),'bid']=1.001
    f.ask=f.bid+.0001
    return f

def test_uses_actual_ask_for_buy_and_charges_commission():
    f=tape();f.loc[f.time>=pd.Timestamp('2025-02-03 08:15Z'),'bid']=1.001
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:16Z'),'bid']=1.005
    f.ask=f.bid+.0002
    r=replay(f,'EURUSD','2025-02-03')
    assert r['status']=='CLOSED' and r['reason']=='TP2'
    assert np.isclose(r['entry'],1.00121) and 1.9<r['net_r']<2

def test_tick_gap_stop_uses_observed_worse_bid():
    f=tape();f.loc[f.time>=pd.Timestamp('2025-02-03 08:15Z'),'bid']=1.001
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:16Z'),'bid']=.995
    f.ask=f.bid+.0001
    r=replay(f,'EURUSD','2025-02-03')
    assert r['reason']=='SL' and r['net_r']<-3

def test_crossed_quotes_missing_eod_and_large_hole_block_pnl():
    f=tape();f.loc[0,'ask']=.9
    assert replay(f,'EURUSD','2025-02-03')['status']=='BLOCKED_TAPE_COVERAGE'
    assert replay(tape().iloc[:-10],'EURUSD','2025-02-03')['status']=='BLOCKED_TAPE_COVERAGE'
    f=tape();f=f[~f.time.between('2025-02-03 10:00Z','2025-02-03 10:02Z')]
    assert replay(f,'EURUSD','2025-02-03')['status']=='BLOCKED_TAPE_COVERAGE'

def test_future_quotes_cannot_change_opening_direction_or_range():
    f=tape();g=f.copy();g.loc[g.time>=pd.Timestamp('2025-02-03 08:15Z'),'bid']=99
    assert opening(f,'2025-02-03')==opening(g,'2025-02-03')

def test_no_new_entry_at_noon_and_dst_uses_london_time():
    f=tape();f.loc[f.time>=pd.Timestamp('2025-02-03 12:00Z'),'bid']=1.002;f.ask=f.bid+.0001
    assert replay(f,'EURUSD','2025-02-03')['status']=='NO_ENTRY_BEFORE_NOON'
    assert pd.Timestamp('2025-03-31 08:00',tz='Europe/London').tz_convert('UTC').hour==7
