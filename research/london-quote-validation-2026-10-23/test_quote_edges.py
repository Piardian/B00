import pandas as pd
from quote_engine import replay
from test_quotes import tape

def test_short_target_requires_ask_not_bid_only():
    f=tape();f.loc[f.time==pd.Timestamp('2025-02-03 08:14:59Z'),'bid']=.999
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:15Z'),'bid']=.999
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:16Z'),'bid']=.9967
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:17Z'),'bid']=.9965
    f.ask=f.bid+.0001
    r=replay(f,'EURUSD','2025-02-03')
    assert r['reason']=='TP2' and pd.Timestamp(r['exit_time'])==pd.Timestamp('2025-02-03 08:17Z')

def test_zero_spread_tape_has_predeclared_floor_stress():
    f=tape();f.loc[f.time>=pd.Timestamp('2025-02-03 08:15Z'),'bid']=1.001
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:16Z'),'bid']=1.005
    f.ask=f.bid
    a=replay(f,'EURUSD','2025-02-03');b=replay(f,'EURUSD','2025-02-03',spread_floor_pips=1.)
    assert b['entry']>a['entry'] and b['initial_risk']>a['initial_risk']
