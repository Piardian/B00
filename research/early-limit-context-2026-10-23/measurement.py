"""Descriptive decision-time measurements; never selects/promotes live trades."""
import math
import pandas as pd
from cost_observer import observe


def context(c):
    at=pd.Timestamp(c['available_at'])
    local=at.tz_convert('Europe/London')
    ratio=c['signal'].get('london_context',{}).get('asia_atr_ratio')
    return dict(london_time=str(local),
      timing='BEFORE_09' if local.hour<9 else '09_TO_NOON',
      htf='ALIGNED' if c['htf_aligned'] else 'NOT_ALIGNED',
      asia='UNKNOWN' if ratio is None or not math.isfinite(ratio) else ('LE_0_35_ATR' if ratio<=.35 else 'GT_0_35_ATR'),
      asia_atr_ratio=ratio)


def decision_measurement(signal,as_of,tape,canonical,point):
    at=pd.Timestamp(as_of)
    if tape.empty:return dict(status='UNPRICED',reason='NO_QUOTES')
    if not tape.time.is_monotonic_increasing:return dict(status='UNPRICED',reason='NONCHRONOLOGICAL_QUOTES')
    if not all(math.isfinite(v) and v>0 for k in ['bid','ask'] for v in tape[k]) or (tape.ask<tape.bid).any():
        return dict(status='UNPRICED',reason='INVALID_QUOTES')
    past=tape[tape.time<=at]
    if past.empty:return dict(status='UNPRICED',reason='NO_PAST_QUOTE')
    q=past.iloc[-1];age=(at-q.time).total_seconds()
    if age>5:return dict(status='UNPRICED',reason='STALE_DECISION_QUOTE',quote_age_seconds=age)
    minute=past[(past.time>=at-pd.Timedelta(minutes=1))&(past.time<at)]
    reference=canonical[canonical.datetime==at-pd.Timedelta(minutes=1)]
    if minute.empty or reference.empty:return dict(status='UNPRICED',reason='NO_CLOCK_ALIGNMENT_REFERENCE')
    ref=reference.iloc[0]
    observed=[float(minute.bid.iloc[0]),float(minute.bid.max()),float(minute.bid.min()),float(minute.bid.iloc[-1])]
    errors=[abs(x-float(ref[k]))/point for x,k in zip(observed,['open','high','low','close'])]
    # A one-minute match is a consistency test of the inherited clock mapping,
    # not an independent proof of the broker time convention or tick completeness.
    alignment=dict(max_ohlc_error_ticks=max(errors),sampled_ticks=len(minute),canonical_volume=float(ref['volume']))
    if max(errors)>2+1e-7:return dict(status='UNPRICED',reason='BID_CLOCK_OR_PRICE_MISMATCH',alignment=alignment)
    result=observe(signal,float(q.bid),float(q.ask),q.time,at,commission_usd=4.,exit_slip_pips=.2)
    return dict(**result,quote_at=str(q.time),bid=float(q.bid),ask=float(q.ask),alignment=alignment,
                fees='USD4/100k roundtrip and .2pip exit slip assumptions; not realized charges',
                cost_group='LE_0_10R' if result['total_cost_budget_r']<=.10 else ('0_10_TO_0_20R' if result['total_cost_budget_r']<=.20 else 'GT_0_20R'))
