import pandas as pd
import pytest
from quote_engine import replay


def signal():
    return dict(symbol='EUR/USD',direction='LONG',entry=1.,stop_loss=.99,tp1=1.012,tp2=1.02,entry_deadline_utc='2025-01-02 12:00:00+00:00')


def bars(rows, start='2025-01-02 09:00:00+00:00'):
    return pd.DataFrame([dict(datetime=t,open=o,high=h,low=l,close=c) for t,(o,h,l,c) in zip(pd.date_range(start,periods=len(rows),freq='min'),rows)])


def test_ask_penetration_required():
    b=bars([(1.001,1.002,.99998,1.001),(1.001,1.002,.9999,1.001)])
    r=replay(signal(),b.datetime[0],b,'passive',spread_pips=.5)
    assert r['filled_at']==str(b.datetime[1])


def test_confirmation_is_not_retroactive_fill():
    b=bars([(1.001,1.002,.999,1.0015),(1.002,1.003,1.001,1.0025),(1.001,1.002,.999,1.001)])
    r=replay(signal(),b.datetime[0],b,'reaction_retest')
    assert r['filled_at']==str(b.datetime[2])
    assert r['confirmed_at']==str(b.datetime[1])


def test_break_then_later_retest():
    b=bars([(1.001,1.002,.999,1.0015),(1.001,1.004,.999,1.003),(1.001,1.002,.999,1.001)])
    r=replay(signal(),b.datetime[0],b,'break_retest')
    assert r['filled_at']==str(b.datetime[2])


def test_stop_wins_and_pays_commission():
    b=bars([(1.001,1.03,.98,1.02)])
    r=replay(signal(),b.datetime[0],b,'passive')
    assert r['reason']=='FILL_BAR_STOP'
    assert r['gross_r']<-1 and r['commission_r']>0


def test_bad_reaction_is_paid_exit():
    b=bars([(1.001,1.001,.999, .9991)])
    r=replay(signal(),b.datetime[0],b,'passive')
    assert r['reason']=='REACTION_EXIT' and r['net_r']<0 and r['commission_r']>0


def test_no_fill_bar_target_credit_and_partial_fees():
    b=bars([(1.001,1.03,.999,1.025),(1.025,1.03,1.01,1.025)])
    r=replay(signal(),b.datetime[0],b,'passive')
    assert r['closed_at']==str(b.datetime[1]+pd.Timedelta(minutes=1))
    assert r['gross_r']==pytest.approx(1.6)
    assert sum(p['qty'] for p in r['parts'])==pytest.approx(1)
    assert r['commission_r']==pytest.approx(.004)


def test_missing_bar_has_no_net_claim():
    b=bars([(1.001,1.002,.999,1.001)]*3).drop(index=1)
    r=replay(signal(),b.datetime.iloc[0],b,'passive')
    assert r['status']=='UNRESOLVED' and r['net_r'] is None


def test_deadline_prevents_new_fill():
    b=bars([(1.001,1.002,.999,1.001)],start='2025-01-02 12:00:00+00:00')
    r=replay(signal(),b.datetime[0],b,'passive')
    assert r['filled_at'] is None and r['net_r']==0


def test_flatten_at_london_close():
    b=bars([(1.001,1.002,.999,1.001),(1.002,1.003,1.001,1.002)],start='2025-01-02 16:29:00+00:00')
    s=signal();s['entry_deadline_utc']='2025-01-02 17:00:00+00:00'
    r=replay(s,b.datetime[0],b,'passive')
    assert r['reason']=='INTRADAY_FLAT'


def test_short_ask_stop_and_usd_quote_commission():
    s=dict(symbol='USD/JPY',direction='SHORT',entry=150.,stop_loss=151.,tp1=148.8,tp2=148.,entry_deadline_utc='2025-01-02 12:00:00+00:00')
    b=bars([(150.,151.,149.9,150.8)])
    r=replay(s,b.datetime[0],b,'passive')
    assert r['reason']=='FILL_BAR_STOP'
    assert r['commission_r']==pytest.approx((150+151.002)*2/100000)


def test_negative_cost_rejected():
    with pytest.raises(ValueError):replay(signal(),'2025-01-02 09:00:00+00:00',bars([]),'passive',spread_pips=-1)
