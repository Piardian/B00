import copy
import pandas as pd
import numpy as np
from measure import replay_one,geometry_rejection,tracker,stats

def signal():
    return dict(symbol='EUR/USD',strategy='ORB_SESSION_BREAKOUT',direction='LONG',grade='A+',
        datetime='2025-06-16 07:15Z',entry=1.,stop_loss=.99,tp1=1.012,tp2=1.02,risk_pips=.01)

def frame(rows):
    f=pd.DataFrame(rows,columns=['open','high','low','close'])
    f['datetime']=pd.date_range('2025-06-16 07:30Z',periods=len(f),freq='min');return f

def test_fill_bar_stop_and_costs_use_original_tracker():
    f=frame([[1.,1.03,.98,1.02]])
    r=replay_one(signal(),'2025-06-16 07:30Z',f)
    assert r['status']=='CLOSED' and r['trade']['close_reason']=='STOP_LOSS'
    assert r['trade']['net_r']==-1.08
    assert replay_one(signal(),'2025-06-16 07:30Z',f,2.)['trade']['net_r']==-1.16

def test_no_fill_target_does_not_count_as_win_or_charge_fee():
    r=replay_one(signal(),'2025-06-16 07:30Z',frame([[1.005,1.03,1.001,1.02]]))
    assert r['trade']['close_reason']=='EXPIRED_NO_FILL'
    assert r['trade']['net_r']==0 and not r['trade'].get('filled_at')

def test_missing_first_minute_is_unresolved_not_zero_return():
    f=frame([[1.,1.001,.999,1.]])
    f.datetime+=pd.Timedelta(minutes=1)
    r=replay_one(signal(),'2025-06-16 07:30Z',f)
    assert r['status']=='UNRESOLVED_M1_GAP' and 'net_r' not in r['trade']

def test_patches_restore_io_and_cost_functions():
    oldsave=tracker.OutcomeTracker._save_json;oldcost=tracker.get_friction_config
    replay_one(signal(),'2025-06-16 07:30Z',frame([[1.,1.03,.98,1.02]]))
    assert tracker.OutcomeTracker._save_json is oldsave and tracker.get_friction_config is oldcost

def test_invalid_rounded_rr_rejected_before_replay():
    s=signal();s['tp1']=1.011
    assert geometry_rejection(s)=='TP1_BELOW_MINIMUM'
    assert geometry_rejection(signal()) is None

def test_cost_stress_can_change_fill_selection_and_is_reported_separately():
    f=frame([[1.0008,1.002,.99975,1.0015],[1.0015,1.03,1.0003,1.025]])
    base=replay_one(signal(),'2025-06-16 07:30Z',f)
    stress=replay_one(signal(),'2025-06-16 07:30Z',f,1.5)
    assert base['trade'].get('filled_at')
    assert stress['trade']['close_reason']=='EXPIRED_NO_FILL' and not stress['trade'].get('filled_at')
