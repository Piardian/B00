import pandas as pd
import pytest
from features import structural_entry, opposing_room, cost_record
from execution import replay


def signal():
    return dict(symbol='EUR/USD',direction='LONG',entry=1.,stop_loss=.99,tp1=1.012,tp2=1.02,entry_deadline_utc='2025-01-02 12:00:00+00:00')


def bars(rows):
    return pd.DataFrame([dict(datetime=t,open=o,high=h,low=l,close=c) for t,(o,h,l,c) in zip(pd.date_range('2025-01-02 09:00:00+00:00',periods=len(rows),freq='min'),rows)])


def ready_bars():return bars([(1.001,1.002,.999,1.0015),(1.002,1.004,1.001,1.003),(1.003,1.006,1.002,1.004)])


def test_next_open_entry_and_structure_stop():
    b=ready_bars();r=structural_entry(signal(),b.datetime[0],b,.5)
    assert r['status']=='READY' and r['at']==str(b.datetime[2])
    assert r['signal']['entry']==pytest.approx(1.00307)
    assert r['signal']['stop_loss']==pytest.approx(.99899)
    assert r['new_risk']<r['original_risk']


def test_future_entry_bar_extremes_cannot_choose_signal():
    b=ready_bars();first=structural_entry(signal(),b.datetime[0],b,.5)
    b.loc[2,['high','low','close']]=[2.,.01,1.5]
    assert structural_entry(signal(),b.datetime[0],b,.5)==first


def test_touched_stop_before_confirmation_invalidates():
    b=ready_bars();b.loc[1,'low']=.998
    assert structural_entry(signal(),b.datetime[0],b,.5)['reason']=='M1_STRUCTURE_BROKEN_BEFORE_ENTRY'


def test_missing_confirmation_minute_unresolved():
    b=ready_bars().drop(index=1)
    assert structural_entry(signal(),b.datetime.iloc[0],b,.5)['status']=='UNRESOLVED'


def test_market_fill_even_without_retest_then_stop_first():
    b=ready_bars();r=structural_entry(signal(),b.datetime[0],b,.5)
    b.loc[2,['high','low','close']]=[1.03,.98,1.02]
    out=replay(r['signal'],r['at'],b,'passive',market_entry=True)
    assert out['filled_at']==r['at'] and out['reason']=='FILL_BAR_STOP' and out['net_r']<-1


def test_market_open_must_match_entry():
    b=ready_bars();s=signal()
    with pytest.raises(ValueError):replay(s,b.datetime[0],b,'passive',market_entry=True)


def hourly():
    return pd.DataFrame(dict(datetime=pd.date_range('2025-01-01 00:00+00:00',periods=8,freq='h'),
                             high=[1.01,1.02,1.04,1.03,1.02,1.02,1.02,9.],
                             low=[.98,.97,.96,.97,.98,.98,.98,.1]))


def test_pivot_needs_two_right_completed_hours():
    h=hourly();s=signal()
    assert opposing_room(s,h,'2025-01-01 04:00+00:00')['status']=='UNKNOWN'
    r=opposing_room(s,h,'2025-01-01 05:00+00:00')
    assert r['level']==1.04 and r['tp1_has_room']


def test_future_hour_does_not_change_room():
    h=hourly();s=signal();at='2025-01-01 05:00+00:00';before=opposing_room(s,h,at)
    h.loc[5:,'high']=99.
    assert opposing_room(s,h,at)==before


def test_room_requires_target_inside_level():
    s=signal();s['tp1']=1.05
    assert not opposing_room(s,hourly(),'2025-01-01 05:00+00:00')['tp1_has_room']


def test_cost_budget_includes_two_market_slips_but_not_replay_debit():
    r=cost_record(signal(),1.,.5,'2025-01-02 09:00+00:00',market=True)
    assert r['total_cost_budget_r']==pytest.approx(.013)
    assert not r['spread_is_historical'] and r['quote_source']=='ASSUMED_SPREAD_ON_BID_M1'


def test_short_structure_stop_and_ask_execution():
    s=dict(symbol='USD/JPY',direction='SHORT',entry=150.,stop_loss=151.,tp1=148.8,tp2=148.,entry_deadline_utc='2025-01-02 12:00+00:00')
    b=bars([(149.99,150.03,149.95,149.97),(149.97,150.0,149.91,149.93),(149.93,149.96,149.9,149.92)])
    r=structural_entry(s,b.datetime[0],b,.5)
    assert r['signal']['entry']==pytest.approx(149.928)
    assert r['signal']['stop_loss']==pytest.approx(150.036)
    out=replay(r['signal'],r['at'],b,'passive',market_entry=True)
    assert out['filled_at']==r['at']
