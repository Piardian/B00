import pandas as pd
import pytest
from execution import replay


S=dict(symbol='EUR/USD',direction='LONG',entry=1.,stop_loss=.99,tp1=1.012,tp2=1.02,entry_deadline_utc='2025-02-03 12:00Z')


def bars(n=31):
    return pd.DataFrame(dict(datetime=pd.date_range('2025-02-03 09:00Z',periods=n,freq='min'),open=1.002,high=1.003,low=1.001,close=1.002))


def touch(f,i):f.loc[i,['open','high','low','close']]=[1.001,1.003,.999,1.002]


def test_deadline_is_exclusive_no_fill_at15():
    f=bars();touch(f,15)
    out=replay(S,f.datetime[0],f,'passive',pending_ttl_minutes=15)
    assert out['reason']=='NO_FILL_DEADLINE' and out['filled_at'] is None
    assert out['net_r']==0 and out['commission_r']==0


def test_minute14_can_fill_and_remain_open_after_expiry():
    f=bars();touch(f,14);f.loc[20,['open','high','low','close']]=[1.01,1.03,1.001,1.025]
    out=replay(S,f.datetime[0],f,'passive',pending_ttl_minutes=15)
    assert out['filled_at']==str(f.datetime[14]) and out['reason']=='TP2'
    assert out['closed_at']==str(f.datetime[20]+pd.Timedelta(minutes=1))


def test_late_fill_would_be_real_and_charged_in_reference():
    f=bars();touch(f,16);f.loc[17,['open','high','low','close']]=[1.,1.001,.98,.985]
    ref=replay(S,f.datetime[0],f,'passive')
    assert ref['filled_at']==str(f.datetime[16]) and ref['net_r']<-1
    short=replay(S,f.datetime[0],f,'passive',pending_ttl_minutes=15)
    assert short['filled_at'] is None and short['net_r']==0


def test_noon_deadline_still_wins_over_ttl():
    f=bars();f.datetime=f.datetime+pd.Timedelta(hours=3)
    out=replay(S,f.datetime[0],f,'passive',pending_ttl_minutes=15)
    assert out['filled_at'] is None and out['reason']=='NO_FILL_DEADLINE'


def test_missing_minute_before_expiry_is_unresolved():
    f=bars().drop(index=5)
    out=replay(S,f.datetime.iloc[0],f,'passive',pending_ttl_minutes=15)
    assert out['status']=='UNRESOLVED' and out['net_r'] is None


def test_stop_before_expiry_still_dominates_targets():
    f=bars();f.loc[3,['open','high','low','close']]=[1.,1.03,.98,1.02]
    out=replay(S,f.datetime[0],f,'passive',pending_ttl_minutes=15)
    assert out['reason']=='FILL_BAR_STOP' and out['net_r']<-1


@pytest.mark.parametrize('ttl',[0,-1,float('inf'),float('nan')])
def test_invalid_ttl_rejected(ttl):
    f=bars()
    with pytest.raises(ValueError):replay(S,f.datetime[0],f,'passive',pending_ttl_minutes=ttl)
