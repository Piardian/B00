import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'london-quote-validation-2026-10-23'))
import quote_engine
from path_audit import reconstruct,aggregate

def frame(short=False):
    times=pd.date_range('2025-02-03 08:00Z','2025-02-03 16:00Z',freq='30s')
    bid=np.full(len(times),1.001 if not short else .999)
    opening=times<pd.Timestamp('2025-02-03 08:15Z')
    bid[opening]=np.linspace(1.,1.001 if not short else .999,opening.sum())
    return pd.DataFrame(dict(time=times,bid=bid,ask=bid+.0001,flags=2))

def original(f,short=False,mult=1.5):
    old=quote_engine.replay(f,'EURUSD','2025-02-03',mult)
    return dict(symbol='EURUSD',date='2025-02-03',scenario='COST_STRESS_1.5x' if mult==1.5 else 'OBSERVED_QUOTES_1x',rvol=1.2,outcome=old)

def test_long_stop_after_profit_uses_costs_and_stops_path_at_exit():
    f=frame();f.loc[f.time>=pd.Timestamp('2025-02-03 08:16Z'),['bid','ask']]=[1.002,1.0021]
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:17Z'),['bid','ask']]=[.9999,1.]
    f.loc[f.time>=pd.Timestamp('2025-02-03 09:00Z'),['bid','ask']]=[1.01,1.0101]
    r=reconstruct(f,original(f));assert r['category']=='SL_after_0.5netR'
    assert r['mfe_net_r']<1 and r['to_eod_mfe_net_r_hindsight']>2
    assert r['stopped_then_original_target_later_hindsight'] and r['returned_inside_before_exit']
    assert r['immediate_liquidation_net_r']<0 and r['minutes_to_0.5_net_r']==1

def test_short_requires_ask_target_and_caps_favourable_gap():
    f=frame(short=True)
    f.loc[f.time>=pd.Timestamp('2025-02-03 08:16Z'),['bid','ask']]=[.99,.9901]
    r=reconstruct(f,original(f,True));assert r['reason']=='TP2'
    assert r['mfe_net_r']<2 and r['to_eod_mfe_net_r_hindsight']>2

def test_same_timestamp_order_reproduces_first_stop_before_later_recovery():
    f=frame();ix=f.index[f.time==pd.Timestamp('2025-02-03 08:16Z')][0]
    extra=f.iloc[[ix]].copy();extra[['bid','ask']]=[.999, .9991]
    f=pd.concat([f.iloc[:ix],extra,f.iloc[ix:]],ignore_index=True)
    r=reconstruct(f,original(f));assert r['reason']=='SL' and r['exit_quote_index']==ix
    assert r['category']=='SL_without_0.5netR'

def test_eod_and_threshold_summary_have_correct_denominators():
    f=frame();r=reconstruct(f,original(f));assert r['reason']=='EOD'
    s=aggregate([r]);assert s['all']['n']==1 and s['stopped']['n']==0
    assert s['losers']['n']==1 and s['all']['reached']['0.5']==0

def test_parity_detects_modified_reference_result():
    import pytest
    f=frame();row=original(f);row['outcome']['net_r']+=.01
    with pytest.raises(AssertionError):reconstruct(f,row)

def test_no_external_trading_or_live_modules():
    import ast
    source=Path(__file__).with_name('path_audit.py').read_text(encoding='utf8')
    tree=ast.parse(source)
    modules={n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module}
    modules|={a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
    assert modules<={'pathlib','sys','json','hashlib','csv','datetime','collections','numpy','pandas'}
