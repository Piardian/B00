import ast
from pathlib import Path
import numpy as np
import pandas as pd
from extension import schedule,MONTHS,SYMBOLS,native_opening,summary

def test_predeclared_calendar_has_two_blocks_and_no_overlap_with_old_evaluation():
    rows=schedule();dates=[d for d,w in rows if not w]
    assert len(dates)==89 and len(set(dates))==89
    assert len([d for d,w in rows if w])==28
    assert {d[:7] for d in dates}==set(MONTHS)
    assert not any(d[:7] in ['2025-02','2025-03'] for d in dates)
    assert len(SYMBOLS)==6

def test_native_volume_keeps_only_bid_updates():
    f=pd.DataFrame(dict(time=pd.to_datetime(['2025-04-01 07:00Z','2025-04-01 07:01Z','2025-04-01 07:02Z']),bid=[1.,1.,1.01],ask=[1.001,1.002,1.011],flags=[2,4,6]))
    r=native_opening(f,'2025-04-01')
    assert r['volume']==2 and r['direction']==1 and r['high']==1.01

def test_dynamic_summary_uses_new_months_and_marks_blocked_status():
    rows=[dict(date='2025-04-01',outcome=dict(status='CLOSED',net_r=2.)),dict(date='2025-05-01',outcome=dict(status='CLOSED',net_r=-1.)),dict(date='2025-09-01',outcome=dict(status='BLOCKED_TAPE_COVERAGE'))]
    r=summary(rows,MONTHS)
    assert r['fills']==2 and r['net_r']==1 and r['pf']==2
    assert r['by_month']['2025-04']==2 and r['by_month']['2025-05']==-1
    assert r['statuses']['BLOCKED_TAPE_COVERAGE']==1

def test_only_market_data_mt5_calls_allowed():
    source=Path(__file__).with_name('extension.py').read_text();tree=ast.parse(source)
    calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='mt5'}
    assert calls<= {'initialize','account_info','symbol_info','copy_ticks_range','copy_rates_range','last_error','shutdown'}
    assert {'copy_ticks_range','copy_rates_range'}<=calls
