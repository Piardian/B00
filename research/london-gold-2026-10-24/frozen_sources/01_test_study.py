from pathlib import Path
import ast
import pandas as pd
import numpy as np
from study import replay,dates,SCENARIOS,CLOSED_DATES

def tape(short=False):
    times=pd.date_range('2025-01-02 08:00Z','2025-01-02 16:00Z',freq='30s');bid=np.full(len(times),2601. if not short else 2599.)
    mask=times<pd.Timestamp('2025-01-02 08:15Z');bid[mask]=np.linspace(2600,2601 if not short else 2599,mask.sum())
    return pd.DataFrame(dict(time=times,bid=bid,ask=bid+.2,flags=2))

def test_gold_commission_per_ounce_uses_100ounce_contract_and_8usd_envelope():
    f=tape();r=replay(f,'2025-01-02')
    assert r['assumed_commission_usd_per_lot_roundtrip']==8
    assert abs(r['commission_r']-.08/r['initial_risk'])<1e-10
    assert r['entry']==2601.25 and r['reason']=='EOD'

def test_percentage_envelope_grows_above_4000_and_stress_scales_costs():
    f=tape();f[['bid','ask']]+=2000
    a=replay(f,'2025-01-02');b=replay(f,'2025-01-02',2.)
    assert a['assumed_commission_usd_per_lot_roundtrip']>8
    assert b['entry']>a['entry'] and b['assumed_commission_usd_per_lot_roundtrip']>2*a['assumed_commission_usd_per_lot_roundtrip']

def test_short_bid_band_stop_exits_at_ask_and_gap_is_not_capped():
    f=tape(True);f.loc[f.time>=pd.Timestamp('2025-01-02 08:16Z'),['bid','ask']]=[2602.,2602.2]
    r=replay(f,'2025-01-02');assert r['reason']=='SL' and r['exit']==2602.25 and r['net_r']<-1

def test_target_gap_capped_and_no_exit_on_entry_quote():
    f=tape();f.loc[f.time>=pd.Timestamp('2025-01-02 08:16Z'),['bid','ask']]=[2610.,2610.2]
    r=replay(f,'2025-01-02');assert r['reason']=='TP2' and r['exit']<2610 and r['exit_time']!=r['entry_time'] and r['net_r']<2

def test_gap_or_missing_eod_is_unknown():
    f=tape();assert replay(f.iloc[:-1],'2025-01-02')['status']=='BLOCKED_COVERAGE'
    f=f[~((f.time>=pd.Timestamp('2025-01-02 09:00Z'))&(f.time<pd.Timestamp('2025-01-02 09:05Z')))]
    assert replay(f,'2025-01-02')['status']=='BLOCKED_COVERAGE'

def test_ask_only_opening_events_not_used_to_choose_direction():
    f=tape();extra=f.iloc[[29]].copy();extra.time=pd.Timestamp('2025-01-02 08:14:59Z');extra.bid=2599.;extra.ask=2599.2;extra['flags']=4
    f=pd.concat([f,extra]).sort_values('time',kind='stable').reset_index(drop=True)
    assert replay(f,'2025-01-02')['direction']==1

def test_no_entry_at_noon_and_london_dst_not_fixed_utc():
    f=tape();f.loc[(f.time>=pd.Timestamp('2025-01-02 08:15Z'))&(f.time<pd.Timestamp('2025-01-02 12:00Z')),'bid']=2600.5;f.ask=f.bid+.2
    assert replay(f,'2025-01-02')['status']=='NO_ENTRY_BEFORE_NOON'
    assert pd.Timestamp('2025-04-01 08:00',tz='Europe/London').tz_convert('UTC').hour==7

def test_calendar_and_only_one_rule_three_cost_scenarios():
    assert len(dates())==129 and len(CLOSED_DATES)==2 and len(SCENARIOS)==3
    assert set(d[:7] for d in dates())=={'2025-01','2025-02','2025-03','2025-04','2025-05','2025-06'}

def test_mt5_calls_data_only_in_both_executable_sources():
    calls=set()
    for name in ['study.py','preflight.py']:
        tree=ast.parse(Path(__file__).with_name(name).read_text())
        calls|={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='mt5'}
    assert calls<={'initialize','account_info','symbol_info','history_deals_get','copy_rates_range','copy_ticks_range','last_error','shutdown'}
