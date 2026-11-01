import pandas as pd
from audit import audit

S=dict(symbol='EUR/USD',direction='LONG',entry=1.,entry_deadline_utc='2025-02-03 12:00Z')
START=pd.Timestamp('2025-02-03 09:00Z')


def tape():
    return pd.DataFrame(dict(time=pd.date_range(START,periods=181,freq='min'),bid=1.001,ask=1.00105))


def test_long_requires_actual_ask_penetration():
    f=tape();f.loc[2,['bid','ask']]=[.9999,1.0001];f.loc[3,['bid','ask']]=[.9999,.99995]
    r=audit(S,START,f,.00001)
    assert r['wait_minutes']==3 and r['accepted_by_ttl15']


def test_exact15minute_fill_is_excluded():
    f=tape();f.loc[15,['bid','ask']]=[.9999,.99995]
    r=audit(S,START,f,.00001)
    assert r['wait_minutes']==15 and not r['accepted_by_ttl15']


def test_subminute_fill_before15_is_included():
    f=tape();f.loc[15,'time']-=pd.Timedelta(milliseconds=1);f.loc[15,['bid','ask']]=[.9999,.99995]
    assert audit(S,START,f,.00001)['accepted_by_ttl15']


def test_short_uses_bid_not_ask():
    f=tape();f['bid']=.9998;f['ask']=1.0002;f.loc[4,['bid','ask']]=[1.00002,1.00005]
    s=dict(S,direction='SHORT')
    assert audit(s,START,f,.00001)['wait_minutes']==4


def test_gap_before_hit_not_assumed_no_fill():
    f=tape().drop(index=[2,3]);f.loc[5,['bid','ask']]=[.9999,.99995]
    assert audit(S,START,f,.00001)['status']=='UNPRICED'


def test_no_fill_requires_feed_through_deadline():
    f=tape().iloc[:100]
    assert audit(S,START,f,.00001)['reason']=='NO_QUOTE_COVERAGE_AT_EXPIRY'


def test_quote_after_deadline_cannot_create_fill():
    f=tape();f.loc[180,['bid','ask']]=[.9999,.99995]
    r=audit(S,START,f,.00001)
    assert r['group']=='NO_FILL' and r['first_possible_fill'] is None


def test_gap_after_first_hit_does_not_change_fill_audit():
    f=tape();f.loc[1,['bid','ask']]=[.9999,.99995]
    r=audit(S,START,f.iloc[:2],.00001)
    assert r['wait_minutes']==1 and r['status']=='MEASURED'
