import pandas as pd
import numpy as np
from experiment import confirmation,targets,market_replay,geometry_rejection

def signal():
    return dict(symbol='EUR/USD',strategy='ORB_SESSION_BREAKOUT',direction='LONG',entry=1.,stop_loss=.99,tp1=1.0119,tp2=1.0199,risk_pips=.01,entry_deadline_utc='2025-06-16 11:00Z')

def frame():
    f=pd.DataFrame([[1.,1.001,.9995,1.0002],[1.0002,1.0022,1.0001,1.002],[1.0025,1.003,1.002,1.0028]],columns=['open','high','low','close'])
    f['datetime']=pd.date_range('2025-06-16 07:30Z',periods=len(f),freq='min');return f

def test_targets_retain_entry_and_stop_and_satisfy_real_rr():
    s=signal();t=targets(s)
    assert (t['entry'],t['stop_loss'])==(s['entry'],s['stop_loss'])
    assert geometry_rejection(t) is None and t['tp1']>=1.012 and t['tp2']>=1.02

def test_confirmation_uses_later_close_and_next_open():
    c=confirmation(targets(signal()),'2025-06-16 07:30Z',frame(),1.)
    assert c['status']=='CONFIRMED'
    assert c['entry_at']==pd.Timestamp('2025-06-16 07:32Z')
    assert c['signal']['entry']==1.0025
    assert c['signal']['stop_loss']==.99

def test_future_entry_bar_extremes_do_not_leak_into_confirmation():
    f=frame();g=f.copy();g.loc[2,['high','low','close']]=[99.,.001,50.]
    a=confirmation(targets(signal()),'2025-06-16 07:30Z',f,1.)
    b=confirmation(targets(signal()),'2025-06-16 07:30Z',g,1.)
    assert a==b

def test_touch_bar_cannot_confirm_itself():
    f=frame().iloc[:1]
    c=confirmation(targets(signal()),'2025-06-16 07:30Z',f,1.)
    assert c['status']=='NO_CONFIRMATION_BEFORE_CUTOFF'

def test_missing_next_open_and_preentry_stop_are_not_fake_winners():
    f=frame();f.loc[2,'datetime']+=pd.Timedelta(minutes=1)
    assert confirmation(targets(signal()),'2025-06-16 07:30Z',f,1.)['status']=='UNRESOLVED_PREENTRY_GAP'
    f=frame();f.loc[0,'low']=.98
    assert confirmation(targets(signal()),'2025-06-16 07:30Z',f,1.)['status']=='INVALIDATED_BEFORE_ENTRY'

def test_market_entry_stop_uses_entry_bar_and_charges_fee():
    f=frame();s=targets(signal());f.loc[0,['open','low','high','close']]=[1.,.98,1.03,1.02]
    r=market_replay(s,'2025-06-16 07:30Z',f,1.5)
    assert r['status']=='CLOSED' and r['trade']['net_r']==-1.12
