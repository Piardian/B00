import pandas as pd
import pytest
from execution import replay
from direction import score


S=dict(symbol='EUR/USD',direction='LONG',entry=1.,stop_loss=.99,tp1=1.012,tp2=1.02,entry_deadline_utc='2025-02-03 12:00Z')


def bars(rows):
    return pd.DataFrame([dict(datetime=t,open=o,high=h,low=l,close=c) for t,(o,h,l,c) in zip(pd.date_range('2025-02-03 09:00Z',periods=len(rows),freq='min'),rows)])


def test_disabling_reaction_cannot_cancel_stop():
    f=bars([(1.001,1.03,.98,1.02)])
    for mode in ['always','never','half_r_adverse']:
        r=replay(S,f.datetime[0],f,'passive',reaction_exit=mode)
        assert r['reason']=='FILL_BAR_STOP' and r['net_r']<-1


def test_never_rule_retains_real_fill_and_later_loss():
    f=bars([(1.001,1.001,.999,.9991),(.999,.9995,.98,.985)])
    original=replay(S,f.datetime[0],f,'passive')
    altered=replay(S,f.datetime[0],f,'passive',reaction_exit='never')
    assert original['reason']=='REACTION_EXIT' and altered['reason']=='STOP_OR_BE_TRAIL'
    assert original['filled_at']==altered['filled_at'] and altered['commission_r']>0


def test_half_r_rule_waits_on_mild_reaction_not_severe():
    f=bars([(1.001,1.001,.999,.9991),(.999,1.03,.998,1.025)])
    r=replay(S,f.datetime[0],f,'passive',reaction_exit='half_r_adverse')
    assert r['reason']=='TP2'
    severe=bars([(1.001,1.001,.994,.9941)])
    assert replay(S,severe.datetime[0],severe,'passive',reaction_exit='half_r_adverse')['reason']=='REACTION_EXIT'


def test_disabling_reaction_does_not_credit_fill_bar_targets():
    f=bars([(1.001,1.03,.999,1.025),(1.025,1.03,1.01,1.025)])
    r=replay(S,f.datetime[0],f,'passive',reaction_exit='never')
    assert r['closed_at']==str(f.datetime[1]+pd.Timedelta(minutes=1))


def test_direction_not_dependent_on_limit_fill():
    f=bars([(1.02,1.03,1.01,1.02)]*61);f.loc[60,'open']=1.025
    r=score(S,f.datetime[0],f)
    assert r['original_score_r']==pytest.approx(.5)
    assert r['reversed_score_r']==pytest.approx(-.5) and 'net_r' not in r


def test_future_after_horizon_cannot_change_direction_score():
    f=bars([(1.02,1.03,1.01,1.02)]*62)
    r=score(S,f.datetime[0],f);f.loc[61,'open']=999.
    assert score(S,f.datetime[0],f)==r


def test_missing_bar_unresolved():
    f=bars([(1.02,1.03,1.01,1.02)]*61).drop(index=10)
    assert score(S,f.datetime.iloc[0],f)['status']=='UNRESOLVED'


def test_conditional_rule_cannot_trade_without_limit_touch():
    f=bars([(1.02,1.03,1.01,1.02)]*181)
    for mode in ['always','never','half_r_adverse']:
        r=replay(S,f.datetime[0],f,'passive',reaction_exit=mode)
        assert r['filled_at'] is None and r['net_r']==0
