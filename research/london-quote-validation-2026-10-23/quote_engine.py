"""Fixed classic London ORB on chronological executable quote pairs.

Only1x uses observed spreads. Stress widens observed ask-bid; commission and
slippage remain assumptions, not reconciled historical account charges.
"""
import numpy as np
import pandas as pd

def validate_tape(tape,start,end):
    if not {'time','bid','ask'}<=set(tape):raise ValueError('time/bid/ask required')
    f=tape.copy();f.time=pd.to_datetime(f.time,utc=True)
    if not f.time.is_monotonic_increasing:raise ValueError('Chronological tick order required')
    if not np.isfinite(f[['bid','ask']]).all().all() or not ((f.bid>0)&(f.ask>=f.bid)).all():raise ValueError('Invalid bid/ask')
    f=f[(f.time>=start)&(f.time<=end+pd.Timedelta(seconds=5))]
    if f.empty:raise ValueError('No quotes')
    if f.iloc[0].time>start+pd.Timedelta(seconds=5):raise ValueError('Opening quotes missing')
    if f.iloc[-1].time<end:raise ValueError('Unpriced EOD')
    if f.time.diff().max()>pd.Timedelta(seconds=60):raise ValueError('Quote gap over60seconds')
    return f

def opening(tape,date):
    start=pd.Timestamp(f'{date} 08:00',tz='Europe/London').tz_convert('UTC')
    f=tape[(tape.time>=start)&(tape.time<start+pd.Timedelta(minutes=15))]
    if f.empty:raise ValueError('No opening quotes')
    bid=f.bid
    return dict(start=start,high=float(bid.max()),low=float(bid.min()),
        direction=int(np.sign(float(bid.iloc[-1]-bid.iloc[0]))),volume=len(f))

def replay(tape,symbol,date,spread_mult=1.,spread_floor_pips=0.):
    start=pd.Timestamp(f'{date} 08:00',tz='Europe/London').tz_convert('UTC')
    deadline=pd.Timestamp(f'{date} 12:00',tz='Europe/London').tz_convert('UTC')
    end=pd.Timestamp(f'{date} 16:00',tz='Europe/London').tz_convert('UTC')
    try:f=validate_tape(tape,start,end);features=opening(f,date)
    except ValueError as exc:return dict(status='BLOCKED_TAPE_COVERAGE',reason=str(exc))
    direction=features['direction'];hi=features['high'];lo=features['low']
    if not direction or hi<=lo:return dict(status='DOJI_OR_INVALID_RANGE')
    slip=(.01 if symbol.endswith('JPY') else .0001)*.1*spread_mult
    entered=False
    for q in f[f.time>=start+pd.Timedelta(minutes=15)].itertuples(index=False):
        bid=float(q.bid);point=.01 if symbol.endswith('JPY') else .0001
        ask=bid+max((float(q.ask)-bid)*spread_mult,point*spread_floor_pips)
        if not entered:
            if q.time>=deadline:return dict(status='NO_ENTRY_BEFORE_NOON')
            hit=bid>=hi if direction==1 else bid<=lo
            if not hit:continue
            entry=ask+slip if direction==1 else bid-slip
            # Preserve prior model's opposite BID-band structural trigger.
            stop=lo if direction==1 else hi
            risk=entry-stop if direction==1 else stop+(ask-bid)-entry
            if risk<=0:return dict(status='INVALID_ENTRY_GEOMETRY')
            target=entry+direction*2*risk;entry_time=q.time;entered=True
            # Exit only on a subsequent quote; same-ms records retain order.
            continue
        if q.time>=end:
            exit_price=bid-slip if direction==1 else ask+slip;reason='EOD';exit_time=q.time;break
        stop_hit=bid<=stop if direction==1 else bid>=stop
        if stop_hit:
            exit_price=bid-slip if direction==1 else ask+slip;reason='SL';exit_time=q.time;break
        target_hit=bid>=target if direction==1 else ask<=target
        if target_hit:
            exit_price=target-slip*direction;reason='TP2';exit_time=q.time;break
    else:return dict(status='UNPRICED_OPEN_POSITION' if entered else 'NO_ENTRY_BEFORE_NOON')
    quote_per_usd=1. if symbol.endswith('USD') else entry
    commission=4.*quote_per_usd/100000*spread_mult
    gross=direction*(exit_price-entry)/risk
    return dict(status='CLOSED',entry_time=str(entry_time),exit_time=str(exit_time),entry=entry,
        exit=exit_price,stop_bid=stop,initial_risk=risk,target=target,reason=reason,
        price_net_r=float(gross),commission_r=float(commission/risk),net_r=float(gross-commission/risk))
