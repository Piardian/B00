import numpy as np
import pandas as pd
import complete as s
from event_audit import event_function,closed_expiry

AT=pd.Timestamp('2025-02-03 08:00',tz='UTC')
def signal():return dict(symbol='EUR/USD',direction='LONG',entry=1.1,stop_loss=1.099)
def tape():
    f=pd.DataFrame(dict(time=pd.date_range(AT,periods=18001,freq='s'),bid=np.full(18001,1.1005),ask=np.full(18001,1.1006)))
    f.loc[60,['bid','ask']]=[1.0998,1.0999]
    return f

def test_first_real_quote7seconds_late_is_audited_not_shifted_to_better_price():
    f=tape().drop(index=range(3660,3667));strict=s.measure().quote_score(signal(),AT,f)
    event=event_function()(signal(),AT,f)
    assert strict['status']=='UNRESOLVED_MARKOUT'
    assert event['status']=='FILLED_MARKOUT'
    assert pd.Timestamp(event['marked_at'])==AT+pd.Timedelta(seconds=3667)

def test_long_gap_stays_unknown():
    f=tape().drop(index=range(3660,3722))
    assert event_function()(signal(),AT,f)['status']=='UNRESOLVED_MARKOUT'

def test_gold_closure_is_explicit_assumption_not_certified_no_fill():
    at=pd.Timestamp('2025-06-05 17:00',tz='UTC')
    ts=pd.date_range(at,'2025-06-05 20:49:59+00:00',freq='s')
    f=pd.DataFrame(dict(time=ts,bid=3000.,ask=3000.3))
    c=dict(symbol='XAUUSD',available_at=str(at),day='2025-06-05')
    meta=dict(requested_end='2025-06-05 22:00:05+00:00')
    ref=pd.DataFrame(dict(datetime=pd.DatetimeIndex([],tz='UTC')))
    got=closed_expiry(c,{},f,meta,ref)
    assert got['status']=='CLOSED_SESSION_EXPIRY_ASSUMPTION'
    assert got['net_markout_r'] is None and not got['archived2025_schedule_verified']
    c['symbol']='EURUSD'
    assert closed_expiry(c,{},f,meta,ref) is None
