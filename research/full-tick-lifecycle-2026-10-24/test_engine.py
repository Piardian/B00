import pandas as pd
import pytest
from engine import replay

S=dict(symbol='EUR/USD',direction='LONG',entry=1.,stop_loss=.99,tp1=1.012,tp2=1.02,entry_deadline_utc='2025-02-03 12:00Z')
START=pd.Timestamp('2025-02-03 09:00Z')


def tape(rows):
    return pd.DataFrame([dict(time=START+pd.Timedelta(seconds=s),bid=b,ask=a) for s,b,a in rows])


def run(f,**kwargs):return replay(S,START,f,.00001,**kwargs)


def test_fill_tick_stop_uses_worse_observed_bid_and_fee():
    r=run(tape([(0,.98,.98005)]))
    assert r['reason']=='FILL_TICK_STOP' and r['gross_r']==pytest.approx(-2.002)
    assert r['commission_r']==pytest.approx(.004) and r['net_r']<r['gross_r']


def test_reaction_exit_uses_next_quote_not_previous_close():
    f=tape([(0,1.001,1.00105),(20,.9999,.99995),(59,.99995,1.),(60.2,.9998,.99985)])
    r=run(f)
    assert r['reason']=='REACTION_EXIT'
    assert r['events'][-1]['price']==pytest.approx(.99978)
    assert r['closed_at']==str(START+pd.Timedelta(seconds=60.2))


def test_no_fill_minute_target_then_full_tp_and_partial_commissions():
    f=tape([(0,.9999,.99995),(20,1.03,1.03005),(59,1.001,1.00105),(60,1.001,1.00105),(120,1.021,1.02105)])
    r=run(f)
    assert r['reason']=='TP2' and r['closed_at']==str(START+pd.Timedelta(seconds=120))
    assert r['gross_r']==pytest.approx(1.6) and r['commission_r']==pytest.approx(.004)
    assert sum(e['qty'] for e in r['events'] if e['type'] in ['TP1','TP2'])==1


def test_be_not_retroactively_active_inside_tp1_minute():
    f=tape([(0,.9999,.99995),(59,1.001,1.00105),(60,1.013,1.01305),(90,.9998,.99985),(120,.9998,.99985)])
    r=run(f)
    assert r['reason']=='STOP_OR_BE_TRAIL' and r['closed_at']==str(START+pd.Timedelta(seconds=120))
    assert [e['type'] for e in r['events']].count('TP1')==1


def test_trail_only_after_tp1_bar_then_effective_next_bar():
    f=tape([(0,.9999,.99995),(59,1.001,1.00105),(60,1.016,1.01605),(119,1.016,1.01605),
            (120,1.016,1.01605),(150,1.006,1.00605),(180,1.006,1.00605)])
    r=run(f)
    assert r['reason']=='STOP_OR_BE_TRAIL' and r['closed_at']==str(START+pd.Timedelta(seconds=180))
    assert r['events'][-1]['stop']==pytest.approx(1.0075)


def test_short_stop_uses_ask():
    s=dict(S,direction='SHORT',stop_loss=1.01,tp1=.988,tp2=.98)
    f=tape([(0,1.00002,1.00007),(20,1.0099,1.0105)])
    r=replay(s,START,f,.00001)
    assert r['reason']=='STOP_OR_BE_TRAIL' and r['events'][-1]['price']==pytest.approx(1.01052)


def test_ttl15_boundary_excludes_late_fill_without_fee():
    f=tape([(i*60,1.001,1.00105) for i in range(16)])
    f.loc[15,['bid','ask']]=[.9999,.99995]
    r=run(f,ttl_minutes=15)
    assert r['filled_at'] is None and r['net_r']==0 and r['commission_r']==0


def test_fill_before_ttl_remains_active_after_expiry():
    rows=[(i*60,1.001,1.00105) for i in range(14)]
    rows += [(840,.9999,.99995),(899,1.001,1.00105),(900,1.021,1.02105)]
    r=run(tape(rows),ttl_minutes=15)
    assert r['reason']=='TP2' and r['filled_at'] is not None


def test_gap_cannot_create_assumed_profit():
    r=run(tape([(0,.9999,.99995),(121,1.03,1.03005)]))
    assert r['status']=='UNRESOLVED' and r['net_r'] is None


def test_spread_floor_changes_quote_side_not_extra_fee_debit():
    f=tape([(0,.99998,.99998),(30,.98,.98)])
    observed=run(f);stress=run(f,spread_floor_pips=1.)
    assert observed['filled_at']!=stress['filled_at']
    assert observed['commission_r']==pytest.approx(stress['commission_r'])


def test_no_terminal_quote_never_reports_partial_profit():
    r=run(tape([(0,.9999,.99995),(59,1.001,1.00105),(60,1.013,1.01305)]))
    assert r['status']=='UNRESOLVED' and r['net_r'] is None and r['remaining_qty']==.5


def test_flat_uses_first_observed_quote_at1630():
    start=pd.Timestamp('2025-02-03 16:29Z');s=dict(S,entry_deadline_utc='2025-02-03 17:00Z')
    f=tape([(0,.9999,.99995),(59,1.001,1.00105),(60.5,1.002,1.00205)]);f.time+=start-START
    r=replay(s,start,f,.00001)
    assert r['reason']=='INTRADAY_FLAT' and r['events'][-1]['price']==pytest.approx(1.00198)


def test_tp1_before_later_stop_in_same_bar_preserves_partial_profit():
    f=tape([(0,.9999,.99995),(59,1.001,1.00105),(60,1.013,1.01305),(80,.989,.98905)])
    r=run(f)
    assert r['reason']=='STOP_OR_BE_TRAIL' and r['gross_r']==pytest.approx(.049)
    assert [e['type'] for e in r['events']]==['LIMIT_FILL','TP1','STOP_OR_BE_TRAIL']


def test_usd_base_partial_fees_use_quote_currency_conversion():
    s=dict(S,symbol='USD/JPY',entry=150.,stop_loss=149.,tp1=151.2,tp2=152.)
    f=tape([(0,149.997,149.998),(59,150.1,150.101),(60,152.1,152.101)])
    r=replay(s,START,f,.001)
    assert r['reason']=='TP2' and r['gross_r']==pytest.approx(1.6)
    assert r['commission_r']==pytest.approx(.006032)
