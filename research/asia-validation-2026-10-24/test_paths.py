import pandas as pd
from path_diagnosis import path,after_exit

S=dict(symbol='EUR/USD',direction='LONG',entry=1.,stop_loss=.99,tp1=1.012)


def bars(rows):
    return pd.DataFrame([dict(datetime=t,high=h,low=l) for t,(h,l) in zip(pd.date_range('2025-02-03 09:00Z',periods=len(rows),freq='min'),rows)])


def test_fill_bar_target_not_credited():
    f=bars([(1.02,.999),(1.001,.98)])
    assert path(S,f.datetime[0],f)['label']=='INITIAL_STOP_FIRST'


def test_later_same_bar_ambiguity_explicit():
    f=bars([(1.001,.999),(1.02,.98)])
    assert path(S,f.datetime[0],f)['label']=='AMBIGUOUS_STOP_TP1_SAME_M1'


def test_continuation_can_reach_target_first_but_no_profit_generated():
    f=bars([(1.02,.999)])
    r=after_exit(S,f.datetime[0],f)
    assert r['label']=='TP1_FIRST' and 'net_r' not in r


def test_missing_prices_not_neither_event():
    f=bars([(1.001,.999),(1.001,.999),(1.001,.999)]).drop(index=1)
    assert path(S,f.datetime.iloc[0],f)['label']=='UNKNOWN_MISSING_M1'
