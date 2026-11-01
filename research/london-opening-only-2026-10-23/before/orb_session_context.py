"""Causal London session geometry and explicit daily ATR normalization."""
import numpy as np
import pandas as pd

def london_bounds(date, session, range_minutes):
    zone=session['timezone']
    start=pd.Timestamp(f"{date} {session['open_local']}",tz=zone).tz_convert('UTC')
    end=pd.Timestamp(f"{date} {session['close_local']}",tz=zone).tz_convert('UTC')
    return start,start+pd.Timedelta(minutes=range_minutes),end

def prior_daily_atr(hourly, day_start, periods=14):
    """SMA true range of14 completed UTC days with >=20 observed H1 bars.

    Thin Sunday/holiday fragments excluded. Broker/source completeness remains
    a separate data-certification issue; missing H1 history never grants entry.
    """
    if hourly is None or hourly.empty:return None
    f=hourly.copy();f['datetime']=pd.to_datetime(f.datetime,utc=True)
    if f.datetime.duplicated().any():return None
    f=f[(f.datetime+pd.Timedelta(hours=1)<=day_start)&(f.datetime>=day_start-pd.Timedelta(days=45))].sort_values('datetime')
    if f.empty:return None
    if not np.isfinite(f[['open','high','low','close']].to_numpy()).all():return None
    if (f.high<f.low).any():return None
    d=f.groupby(f.datetime.dt.floor('D')).agg(high=('high','max'),low=('low','min'),close=('close','last'),n=('datetime','size'))
    d=d[d.n>=20]
    if len(d)<periods+1:return None
    # An old cache must not stand in for the last completed trading day.
    if (day_start-d.index[-1]).days>4:return None
    previous=d.close.shift(1)
    tr=pd.concat([d.high-d.low,(d.high-previous).abs(),(d.low-previous).abs()],axis=1).max(axis=1)
    atr=float(tr.iloc[-periods:].mean())
    return atr if np.isfinite(atr) and atr>0 else None

def london_context(df,hourly,session,range_minutes,as_of,compression_limit=.7,atr_periods=14):
    if range_minutes<=0 or range_minutes%15:raise ValueError('London ORB requires whole M15 intervals')
    now=pd.Timestamp(as_of)
    now=now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    f=df.copy();f['datetime']=pd.to_datetime(f.datetime,utc=True)
    if f.datetime.duplicated().any() or not f.datetime.is_monotonic_increasing:return None
    f=f[f.datetime+pd.Timedelta(minutes=15)<=now]
    if f.empty:return None
    last=f.iloc[-1].datetime
    day=last.floor('D');start,orb_end,end=london_bounds(last.date(),session,range_minutes)
    if not (orb_end<=last<end):return None
    if now-last>pd.Timedelta(minutes=45):return None
    grid=pd.date_range(start,orb_end,freq='15min',inclusive='left')
    orb=f[f.datetime.isin(grid)]
    if len(orb)!=len(grid):return None
    # Freeze pre-London Asia at00:00-06:00UTC; never include later trend bars.
    asia_grid=pd.date_range(day,day+pd.Timedelta(hours=6),freq='15min',inclusive='left')
    asia=f[f.datetime.isin(asia_grid)]
    if len(asia)!=len(asia_grid):return None
    atr=prior_daily_atr(hourly,day,atr_periods)
    if atr is None:return None
    asian_range=float(asia.high.max()-asia.low.min())
    if asian_range>compression_limit*atr:return None
    post=f[(f.datetime>=orb_end)&(f.datetime<end)]
    # The preceding close must be the immediately preceding completed M15.
    previous=post.iloc[-2] if len(post)>=2 else orb.iloc[-1]
    if last-previous.datetime!=pd.Timedelta(minutes=15):return None
    return dict(orb=orb,post=post,start=start,end=orb_end,daily_atr=atr,asian_range=asian_range,ratio=asian_range/atr)
