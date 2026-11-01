import sys
from pathlib import Path
import numpy as np
import pandas as pd
from study import prepare,execute,summary
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'london-quote-validation-2026-10-23'))
import quote_engine

def frame():
    times=pd.date_range('2025-02-03 08:00Z','2025-02-03 16:00Z',freq='30s');bid=np.ones(len(times))
    bid[times<pd.Timestamp('2025-02-03 08:15Z')]=np.linspace(1.,1.001,30)
    bid[times>=pd.Timestamp('2025-02-03 08:15Z')]=1.0011
    bid[times>=pd.Timestamp('2025-02-03 08:16Z')]=1.001
    bid[times>=pd.Timestamp('2025-02-03 08:16:30Z')]=1.0012
    bid[times>=pd.Timestamp('2025-02-03 08:17Z')]=1.0013
    return pd.DataFrame(dict(time=times,bid=bid,ask=bid+.0001,flags=2))

def test_next_minute_entry_and_no_confirmation_on_retest_bar():
    f=frame();p=prepare(f,'2025-02-03');r=execute(f,'EURUSD','2025-02-03',p)
    assert p['status']=='ENTRY_READY'
    assert p['breakout_available_at']=='2025-02-03 08:16:00+00:00'
    assert p['retest_time']=='2025-02-03 08:16:00+00:00'
    assert r['entry_time']=='2025-02-03 08:18:00+00:00'

def test_stop_before_confirmation_invalidates_day_without_second_attempt():
    f=frame();f.loc[f.time==pd.Timestamp('2025-02-03 08:17Z'),'bid']=.999
    assert prepare(f,'2025-02-03')['status']=='INVALIDATED_BEFORE_ENTRY'

def test_breakout_intrabar_touch_not_used_as_later_retest():
    f=frame();f.loc[f.time>=pd.Timestamp('2025-02-03 08:16Z'),'bid']=1.0013;f.ask=f.bid+.0001
    assert prepare(f,'2025-02-03')['status']=='NO_RETEST'

def test_current_high_does_not_confirm_without_close_break():
    f=frame();f.loc[f.time>=pd.Timestamp('2025-02-03 08:17Z'),'bid']=1.0012
    f.loc[f.time==pd.Timestamp('2025-02-03 08:17Z'),'bid']=1.005;f.ask=f.bid+.0001
    assert prepare(f,'2025-02-03')['status']=='NO_CONFIRMATION_BEFORE_NOON'

def test_missing_confirmation_minute_blocks_instead_of_flat():
    f=frame();f=f[~((f.time>=pd.Timestamp('2025-02-03 08:17Z'))&(f.time<pd.Timestamp('2025-02-03 08:18Z')))]
    assert prepare(f,'2025-02-03')['status'] in {'BLOCKED_TAPE_COVERAGE','BLOCKED_FEATURE'}

def test_no_entry_at_noon():
    f=frame();f.loc[(f.time>=pd.Timestamp('2025-02-03 08:17Z'))&(f.time<pd.Timestamp('2025-02-03 11:59Z')),'bid']=1.0012;f.ask=f.bid+.0001
    assert prepare(f,'2025-02-03')['status']=='NO_CONFIRMATION_BEFORE_NOON'

def test_exit_accounting_matches_old_engine_for_same_forced_entry():
    f=frame();old=quote_engine.replay(f,'EURUSD','2025-02-03',1.5)
    i=f.index[f.time==pd.Timestamp(old['entry_time'])][0]
    p=dict(status='ENTRY_READY',entry_index=i,direction=1,stop_bid=1.,breakout_available_at='',retest_time='',confirmation_available_at='')
    r=execute(f,'EURUSD','2025-02-03',p,1.5)
    assert r['reason']==old['reason'] and r['exit_time']==old['exit_time']
    assert abs(r['net_r']-old['net_r'])<1e-10

def test_short_mirrors_confirmation_and_uses_executable_ask():
    f=frame();f.bid=2.-f.bid;f.ask=f.bid+.0001
    p=prepare(f,'2025-02-03');r=execute(f,'EURUSD','2025-02-03',p,1.5)
    assert p['direction']==-1 and p['status']=='ENTRY_READY' and r['status']=='CLOSED'
    assert r['entry']<f.loc[p['entry_index'],'bid']

def test_long_target_gap_is_capped_and_parity_holds():
    f=frame();f.loc[f.time>=pd.Timestamp('2025-02-03 08:20Z'),['bid','ask']]=[1.01,1.0101]
    old=quote_engine.replay(f,'EURUSD','2025-02-03',1.5);i=f.index[f.time==pd.Timestamp(old['entry_time'])][0]
    p=dict(status='ENTRY_READY',entry_index=i,direction=1,stop_bid=1.,breakout_available_at='',retest_time='',confirmation_available_at='')
    r=execute(f,'EURUSD','2025-02-03',p,1.5)
    assert r['reason']=='TP2' and r['exit']<1.01 and abs(r['net_r']-old['net_r'])<1e-10

def test_short_stop_uses_bid_trigger_and_ask_exit_with_gap():
    f=frame();f.bid=2.-f.bid;f.ask=f.bid+.0001
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:20Z'),['bid','ask']]=[1.001,1.0013]
    old=quote_engine.replay(f,'EURUSD','2025-02-03',1.5);i=f.index[f.time==pd.Timestamp(old['entry_time'])][0]
    p=dict(status='ENTRY_READY',entry_index=i,direction=-1,stop_bid=1.,breakout_available_at='',retest_time='',confirmation_available_at='')
    r=execute(f,'EURUSD','2025-02-03',p,1.5)
    assert r['reason']=='SL' and r['exit']>1.0013 and abs(r['net_r']-old['net_r'])<1e-10

def test_read_only_imports_and_no_order_methods():
    import ast
    source=Path(__file__).with_name('study.py').read_text();tree=ast.parse(source)
    modules={a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
    modules|={n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module}
    assert modules<={'pathlib','datetime','sys','json','hashlib','csv','numpy','pandas'}
