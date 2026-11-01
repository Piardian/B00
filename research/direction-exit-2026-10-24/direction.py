"""Direction diagnostic, not an executable strategy or PNL backtest.

Fixed60minute bid-open change in units of original entry-stop distance.
Same timestamp/risk, reversed direction negates the score. No fills or costs.
"""
import math
import pandas as pd


def score(signal,available_at,bars):
    at=pd.Timestamp(available_at);end=at+pd.Timedelta(minutes=60)
    risk=abs(signal['entry']-signal['stop_loss'])
    if signal['direction'] not in {'LONG','SHORT'} or not math.isfinite(risk) or risk<=0:raise ValueError('Invalid signal risk/direction')
    sample=bars[(bars.datetime>=at)&(bars.datetime<=end)]
    expected=pd.date_range(at,end,freq='min')
    if not pd.DatetimeIndex(sample.datetime).equals(expected):return dict(status='UNRESOLVED',reason='MISSING_OR_DUPLICATED_DIRECTION_M1')
    prices=sample.open.to_numpy()
    if not all(math.isfinite(x) and x>0 for x in prices):return dict(status='UNRESOLVED',reason='INVALID_DIRECTION_OPEN')
    original=(1 if signal['direction']=='LONG' else -1)*(float(prices[-1])-float(prices[0]))/risk
    return dict(status='MEASURED',original_score_r=original,reversed_score_r=-original,
                start=str(at),end=str(end),start_bid=float(prices[0]),end_bid=float(prices[-1]),
                warning='Unprotected60minute directional bid move; not trading profit, no spread/fee/stop/limit fill.')
