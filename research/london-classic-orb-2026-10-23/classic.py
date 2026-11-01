"""Classic London ORB hypothesis and no-volume-filter control.
Synthetic bid/ask cost scenarios; no broker fills or live API calls.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
DATA=ROOT/'data/full_2025_study/prices_utc'
SYMBOLS=['EUR/USD','GBP/USD','USD/JPY','USD/CAD','USD/CHF','NZD/USD']
MONTHS=['2025-01','2025-06','2025-11']

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pip(symbol):return .01 if symbol.endswith('/JPY') else .0001

def opening_features(m15,date):
    t=pd.Timestamp(f'{date} 08:00',tz='Europe/London').tz_convert('UTC')
    row=m15[m15.datetime==t]
    if len(row)!=1:return None
    clock=m15.datetime.dt.tz_convert('Europe/London')
    previous=m15[(clock.dt.hour==8)&(clock.dt.minute==0)&(m15.datetime<t)]
    previous=previous[previous.volume>0].tail(14)
    if len(previous)<14:return None
    b=row.iloc[0];mean=float(previous.volume.mean())
    return dict(start=t,high=float(b.high),low=float(b.low),direction=1 if b.close>b.open else (-1 if b.close<b.open else 0),rvol=float(b.volume)/mean)

def trade_day(symbol,m1,date,features,mult=1.):
    start=features['start']+pd.Timedelta(minutes=15)
    cutoff=pd.Timestamp(f'{date} 12:00',tz='Europe/London').tz_convert('UTC')
    eod=pd.Timestamp(f'{date} 16:00',tz='Europe/London').tz_convert('UTC')
    g=m1[(m1.datetime>=start)&(m1.datetime<eod)]
    grid=pd.date_range(start,eod,freq='min',inclusive='left')
    if len(g)!=len(grid) or not np.array_equal(g.datetime.to_numpy(),grid.to_numpy()):return dict(status='INCOMPLETE_SESSION')
    direction=features['direction'];hi=features['high'];lo=features['low']
    if not direction or hi<=lo:return dict(status='DOJI_OR_INVALID_RANGE')
    spread=pip(symbol)*1.*mult;slip=pip(symbol)*.1*mult
    entered=False;entry=risk=sl=target=0.;entry_at=None
    for b in g.itertuples(index=False):
        fresh=False
        if not entered:
            if b.datetime>=cutoff:break
            triggered=b.high>=hi if direction==1 else b.low<=lo
            if not triggered:continue
            entry=(max(b.open,hi)+spread+slip) if direction==1 else (min(b.open,lo)-slip)
            sl=lo if direction==1 else hi+spread
            risk=abs(entry-sl);target=entry+direction*2*risk
            entered=True;fresh=True;entry_at=b.datetime
        stop_hit=b.low<=sl if direction==1 else b.high+spread>=sl
        if stop_hit:
            if direction==1:exit_price=(sl if fresh else min(b.open,sl))-slip
            else:exit_price=(sl if fresh else max(b.open+spread,sl))+slip
            reason='SL';exit_at=b.datetime+pd.Timedelta(minutes=1);break
        target_hit=b.high>=target if direction==1 else b.low+spread<=target
        if target_hit and not fresh:
            exit_price=target-slip*direction;reason='TP2';exit_at=b.datetime+pd.Timedelta(minutes=1);break
    else:
        if entered:
            b=g.iloc[-1];exit_price=float(b.close)-(slip if direction==1 else -spread-slip)
            reason='EOD';exit_at=eod
    if not entered:return dict(status='NO_BREAK_BEFORE_NOON')
    # A filled position always reaches SL,TP or EOD; no overnight carrying.
    quote_per_usd=1. if symbol.endswith('/USD') else entry
    commission=4.*quote_per_usd/100000*mult
    gross=direction*(exit_price-entry)/risk;fee=commission/risk
    return dict(status='CLOSED',entry=float(entry),stop=float(sl),target=float(target),risk=float(risk),
        direction=int(direction),entry_at=str(entry_at),exit_at=str(exit_at),reason=reason,
        price_net_before_commission_r=float(gross),commission_r=float(fee),net_r=float(gross-fee),
        spread_pips=float(mult),slippage_pips_each_side=float(.1*mult))

def summary(rows):
    trades=[r for r in rows if r['outcome']['status']=='CLOSED'];v=np.array([r['outcome']['net_r'] for r in trades])
    dates=pd.DatetimeIndex([d for m in MONTHS for d in pd.bdate_range(m+'-01',pd.Timestamp(m+'-01')+pd.offsets.MonthEnd(0))]);daily=pd.Series(0.,index=dates)
    for r in trades:daily.loc[pd.Timestamp(r['date'])]+=r['outcome']['net_r']
    rng=np.random.default_rng(173);n=len(daily);boot=[]
    for _ in range(10000):
        starts=rng.integers(0,n,size=(n+4)//5);ix=((starts[:,None]+np.arange(5))%n).ravel()[:n];boot.append(daily.to_numpy()[ix].sum())
    loss=-v[v<0].sum()
    return dict(eligible_pair_days=len(rows),fills=len(trades),net_r=float(v.sum()),mean_r=float(v.mean()) if len(v) else None,
        win_pct=float((v>0).mean()*100) if len(v) else None,pf=float(v[v>0].sum()/loss) if loss else None,
        reasons=pd.Series([r['outcome'].get('reason',r['outcome']['status']) for r in rows]).value_counts().to_dict(),
        by_month={m:float(sum(r['outcome']['net_r'] for r in trades if r['date'][:7]==m)) for m in MONTHS},
        without_best5=float(np.sort(v)[:-5].sum()) if len(v)>=5 else None,block_total_ci95=np.quantile(boot,[.025,.975]).tolist())

def run():
    declaration=dict(symbols=SYMBOLS,months=MONTHS,hypotheses=['CLASSIC_ALL','CLASSIC_RVOL_GE1'],
        rules='08:00-08:15Londonbidrange;breakONLYopeningcandledirection;onefirstbreakpairdaybefore12London;SLoppositerange;fullTP2R(noTP1);EOD16London;no retest,EMA,AsianrangeorHTFfilters',
        activity='opening15minbroker_tickvolume/meanprevious14available08:00LondonM15volumes;threshold>=1predeclared;proxyNOTconsolidatedFXvolume;controlsameentrywithoutfilter',
        costs='syntheticask=bid+1pip;0.1pipslippageeachside;$4roundtripper100kunitsconvertedtoquotecurrency;scaleby1/1.5/2;conservativebidtriggerforbothdirections;entrybarstopfirst/noTPcredit;gapstopworseopen;historicalbidaskunverified',
        inference='all5newmechanicalvariantsincludingearlier3reported;notOOS;individualunitRopportunitiesnotsharedriskportfolio;63observedday5dayblockbootstrap10000seed173;no selectionadjustment',
        exclusions='requirecompleteM1grid08:15-16London;missingdataexcludedexplicitly;no invented flat return;first14sameclockhistoricalM15volumesrequired',
        source_urls=['https://alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content','https://the5ers.com/faqs/what-are-the-spreads-and-commissions/'],
        files={str(p):sha(p) for p in [Path(__file__),BASE/'test_classic.py']},inputs={str(DATA/f'{s.replace("/", "")}_{tf}.csv.gz'):sha(DATA/f'{s.replace("/", "")}_{tf}.csv.gz') for s in SYMBOLS for tf in ['1m','15m']},live_approved=False)
    p=BASE/'protocol_frozen.json'
    if p.exists():raise RuntimeError('Already frozen')
    p.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=declaration),indent=2),encoding='utf8')
    rows=[];excluded=[];features_audit=[]
    for s in SYMBOLS:
        m1=pd.read_csv(DATA/f'{s.replace("/", "")}_1m.csv.gz');m15=pd.read_csv(DATA/f'{s.replace("/", "")}_15m.csv.gz')
        for f in [m1,m15]:
            f.datetime=pd.to_datetime(f.datetime,utc=True)
            if f.datetime.duplicated().any() or not f.datetime.is_monotonic_increasing:raise RuntimeError('Bad clock')
        for month in MONTHS:
            for date in pd.bdate_range(month+'-01',pd.Timestamp(month+'-01')+pd.offsets.MonthEnd(0)):
                day=str(date.date());features=opening_features(m15,day)
                if features is None:excluded.append(dict(symbol=s,date=day,reason='NO_OPENING_OR_14DAY_VOLUME'));continue
                features_audit.append(dict(symbol=s,date=day,**features))
                for mult in [1.,1.5,2.]:
                    outcome=trade_day(s,m1,day,features,mult)
                    rows.append(dict(symbol=s,date=day,multiplier=mult,rvol=features['rvol'],outcome=outcome))
        print(s,'done',flush=True)
    results={name:{str(m):summary([r for r in rows if r['multiplier']==m and (name=='CLASSIC_ALL' or r['rvol']>=1.)]) for m in [1.,1.5,2.]} for name in ['CLASSIC_ALL','CLASSIC_RVOL_GE1']}
    for path,digest in declaration['files'].items():
        if sha(Path(path))!=digest:raise RuntimeError('Source changed')
    (BASE/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    (BASE/'outcomes.json').write_text(json.dumps(rows,default=str,indent=2),encoding='utf8')
    (BASE/'exclusions.json').write_text(json.dumps(excluded,indent=2),encoding='utf8')
    (BASE/'opening_features.json').write_text(json.dumps(features_audit,default=str,indent=2),encoding='utf8')

if __name__=='__main__':run()
