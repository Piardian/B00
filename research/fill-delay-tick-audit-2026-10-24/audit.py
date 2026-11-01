"""Earliest executable quote opportunity, not a broker fill guarantee or PNL."""
import math
import pandas as pd


def audit(signal,available_at,tape,point):
    start=pd.Timestamp(available_at);expiry=min(pd.Timestamp(signal['entry_deadline_utc']),start+pd.Timedelta(hours=4))
    short_expiry=min(expiry,start+pd.Timedelta(minutes=15))
    if signal['direction'] not in {'LONG','SHORT'} or not math.isfinite(point) or point<=0:raise ValueError('Invalid contract')
    entry=float(signal['entry'])
    if not math.isfinite(entry) or entry<=0:raise ValueError('Invalid entry')
    # Quotes after the order deadline cannot affect the first-hit decision.
    f=tape[(tape.time>=start)&(tape.time<=expiry+pd.Timedelta(seconds=5))].copy()
    if f.empty:return dict(status='UNPRICED',reason='NO_ORDER_WINDOW_QUOTES')
    if not f.time.is_monotonic_increasing:return dict(status='UNPRICED',reason='UNSORTED_QUOTES')
    if not all(math.isfinite(x) and x>0 for k in ['bid','ask'] for x in f[k]) or (f.ask<f.bid).any():return dict(status='UNPRICED',reason='INVALID_QUOTES')
    if f.iloc[0].time>start+pd.Timedelta(seconds=5):return dict(status='UNPRICED',reason='OPENING_QUOTE_LATE')
    active=f[f.time<expiry]
    long=signal['direction']=='LONG'
    penetration=active.ask<=entry-point+point*1e-7 if long else active.bid>=entry+point-point*1e-7
    hits=active[penetration]
    first=None if hits.empty else hits.iloc[0]
    horizon=expiry if first is None else first.time
    prefix=f[f.time<=horizon]
    if len(prefix)>1 and prefix.time.diff().max()>pd.Timedelta(seconds=60):return dict(status='UNPRICED',reason='GAP_BEFORE_FILL_OR_EXPIRY')
    if first is None:
        tail=f[f.time>=expiry]
        if tail.empty:return dict(status='UNPRICED',reason='NO_QUOTE_COVERAGE_AT_EXPIRY')
        if not prefix.empty and tail.iloc[0].time-prefix.iloc[-1].time>pd.Timedelta(seconds=60):return dict(status='UNPRICED',reason='GAP_ACROSS_EXPIRY')
    opening=f.iloc[0]
    marketable=entry>=opening.ask if long else entry<=opening.bid
    wait=None if first is None else (first.time-start).total_seconds()/60
    pip=.01 if signal['symbol'].replace('/','').endswith('JPY') else .0001
    return dict(status='MEASURED',first_possible_fill=str(first.time) if first is not None else None,
      fill_minute=str(first.time.floor('min')) if first is not None else None,wait_minutes=wait,
      accepted_by_ttl15=bool(first is not None and first.time<short_expiry),
      group='NO_FILL' if first is None else ('BEFORE15' if first.time<short_expiry else 'AT_OR_AFTER15'),
      first_fill_bid=float(first.bid) if first is not None else None,first_fill_ask=float(first.ask) if first is not None else None,
      first_fill_spread_pips=float((first.ask-first.bid)/pip) if first is not None else None,
      marketable_at_first_post_signal_quote=bool(marketable),
      opening_quote_time=str(opening.time),opening_quote_delay_seconds=(opening.time-start).total_seconds(),
      warning='One-tick penetration quote opportunity only; no queue/latency/order rejection/actual fill receipt or lifecycle PNL.')
