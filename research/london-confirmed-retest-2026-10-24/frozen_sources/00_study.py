"""One causal confirmed-retest hypothesis. Offline historical quotes only."""
from pathlib import Path
from datetime import datetime, timezone
import sys,json,hashlib,csv
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parent
PRIOR=BASE.parent/'london-quote-validation-2026-10-23'
EXT=BASE.parent/'london-extension-2026-10-24'
SCENARIOS=[('OBSERVED_QUOTES_1x',1.,0.),('COST_STRESS_1.5x',1.5,0.),('COST_STRESS_2x',2.,0.),('MIN_SPREAD_1PIP',1.,1.)]
MONTHS=['2025-02','2025-03','2025-04','2025-05','2025-09','2025-10']

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,indent=2,default=str),encoding='utf8')

def freeze():
    paths=[Path(__file__),BASE/'test_study.py',PRIOR/'quote_engine.py',PRIOR/'native_outcomes.json',PRIOR/'quote_manifest_frozen.json',EXT/'outcomes.json',EXT/'quote_manifest_frozen.json',BASE.parent/'london-path-audit-2026-10-24/results.json',BASE.parent/'entry-innovation-2026-10-23/REPORT.md',BASE.parent/'london-edge-development-2026-10-23/SONUC.md']
    declaration=dict(
        hypothesis='One new entry hypothesis on classicORB candidates, not the prior midpoint-limit production setups: complete1mcloseoutsideopeningrange, then subsequentquote retestofbrokenouterboundary, then a latercompleted1mcandle closesbeyondpreviouscompleted1mhigh/low AND outsideopeningrange; buy/sellfirstquoteatnextminute',
        before_outcomes='Entry rules frozen after path diagnostics; all six months previously seen. This is DEVELOPMENT, not new OOS, independent confirmation or edge proof.',
        unchanged='SixFXmajors;08:00-08:15LondonBIDrange;openingdirection;RVOL>=1primary,allvolumecontrol;oppositeBIDbandsyntheticstructuralstop;full2R;EOD16London;oneattemptperpairday;entrystrictlybefore12London',
        causal='Firstcompleted1mbreakoutafter08:15; cannotretestwithinthebreakoutbar; retestbarcannotconfirm; confirmationusesonlypreviouscompletedbarhigh/low; entryonfirstquote>=confirmationclose,<=5slate; nofillwithconfirmationbarhigh/low; originalstopviolatedafterbreakoutandbeforeentrycancelsday; nosecondsetup; noexpiryextension',
        missing='Opening<=5s,EOD<=5s,maxgap60s as old engine. NeedednativeBID1mbarmissing =>BLOCKED_FEATURE. Missingentryquote<=5s =>BLOCKED_ENTRY_COVERAGE. No flat/profit imputation.',
        fees='SameobservedBIDASK,0.1pip/sideadverseslippageand$4/100kroundtripassumptions;scenarioswidenspread,slippageandcommission;shortstopBIDtriggeraskexit;notrealbrokerstoporfills',
        scenarios=SCENARIOS,months=MONTHS,
        compare='SamepairdayuniverseandRVOLselection; directentryfrozenbaselinevsconfirmedretest; abstentionsretainedasnoentry; blockedunknownsnotzeros; allmonthsandsymbolsreportedwithoutselection',
        gate='Fullcoverage,>=100primaryfills,positive1.5x/2x/min1pip,primary1.5x5dayblockCIlo>0. Also report paired daily netR delta versus baseline, including abstentions. Passing means candidate for new validation only, never livepromotion.',
        statistics='10k5observedweekdaycircularblocksseed173,allpairsadaytogether,nomultiplicitycorrection;discontinuoustimeblocks;unitRopportunitiesnotaccountreturns',
        prior_failures='EarlierM1retestonmidpointcandidateswasnegative; this classicouterboundaryexperimentdoesnoteraseit. NoTP/SL/volume/timeparametersearch.',
        read_only=True,live_approved=False,hashes={str(p):sha(p) for p in paths})
    normalized=json.loads(json.dumps(declaration));p=BASE/'protocol_frozen.json'
    if p.exists():assert read(p)['declaration']==normalized,'Frozen rules changed'
    else:
        save(p,dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=normalized));(BASE/'frozen_sources').mkdir(exist_ok=True)
        for i,source in enumerate(paths):(BASE/'frozen_sources'/f'{i:02}_{source.name}').write_bytes(source.read_bytes())
    return declaration

def prepare(frame,date):
    f=frame.reset_index(drop=True);times=pd.DatetimeIndex(f.time)
    start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');end=pd.Timestamp(date+' 16:00',tz='Europe/London').tz_convert('UTC');deadline=start+pd.Timedelta(hours=4)
    bid=f.bid.to_numpy(float)
    if not times.is_monotonic_increasing or not np.isfinite(f[['bid','ask']]).all().all() or not ((f.bid>0)&(f.ask>=f.bid)).all():return dict(status='BLOCKED_TAPE_COVERAGE')
    if not len(f) or times[0]>start+pd.Timedelta(seconds=5) or times[-1]<end or times[-1]>end+pd.Timedelta(seconds=5) or f.time.diff().max()>pd.Timedelta(seconds=60):return dict(status='BLOCKED_TAPE_COVERAGE')
    native=f[(f['flags'].astype('int64')&2)!=0].set_index('time').bid
    opening=native[(native.index>=start)&(native.index<start+pd.Timedelta(minutes=15))]
    if opening.empty:return dict(status='BLOCKED_FEATURE')
    hi,lo=float(opening.max()),float(opening.min());direction=int(np.sign(opening.iloc[-1]-opening.iloc[0]))
    if not direction or hi<=lo:return dict(status='DOJI_OR_INVALID_RANGE')
    bars=native.resample('1min').ohlc();break_end=None
    for minute in pd.date_range(start+pd.Timedelta(minutes=15),deadline-pd.Timedelta(minutes=2),freq='1min'):
        if minute not in bars.index or bars.loc[minute].isna().any():return dict(status='BLOCKED_FEATURE')
        close=float(bars.loc[minute,'close'])
        if close>hi if direction==1 else close<lo:
            break_end=minute+pd.Timedelta(minutes=1);break
    if break_end is None:return dict(status='NO_COMPLETED_BREAKOUT')
    window=(times>=break_end)&(times<deadline)
    stop_mask=(bid<=lo) if direction==1 else (bid>=hi)
    stops=np.flatnonzero(window&stop_mask);first_stop=int(stops[0]) if len(stops) else None
    retest_mask=(bid<=hi) if direction==1 else (bid>=lo)
    touches=np.flatnonzero(window&retest_mask)
    base=dict(breakout_available_at=str(break_end),direction=direction,stop_bid=lo if direction==1 else hi)
    if not len(touches):return dict(status='NO_RETEST',**base)
    touch_i=int(touches[0]);touch_time=times[touch_i];base['retest_time']=str(touch_time)
    if first_stop is not None and first_stop<=touch_i:return dict(status='INVALIDATED_BEFORE_ENTRY',**base)
    for minute in pd.date_range(touch_time.floor('min')+pd.Timedelta(minutes=1),deadline-pd.Timedelta(minutes=2),freq='1min'):
        available=minute+pd.Timedelta(minutes=1)
        if first_stop is not None and times[first_stop]<=available:return dict(status='INVALIDATED_BEFORE_ENTRY',**base)
        previous=minute-pd.Timedelta(minutes=1)
        if minute not in bars.index or previous not in bars.index or bars.loc[[previous,minute]].isna().any().any():return dict(status='BLOCKED_FEATURE',**base)
        close=float(bars.loc[minute,'close'])
        confirmed=(close>float(bars.loc[previous,'high']) and close>hi) if direction==1 else (close<float(bars.loc[previous,'low']) and close<lo)
        if not confirmed:continue
        candidates=np.flatnonzero((times>=available)&(times<deadline))
        if not len(candidates) or times[candidates[0]]>available+pd.Timedelta(seconds=5):return dict(status='BLOCKED_ENTRY_COVERAGE',**base)
        entry_i=int(candidates[0])
        if first_stop is not None and first_stop<=entry_i:return dict(status='INVALIDATED_BEFORE_ENTRY',**base)
        return dict(status='ENTRY_READY',entry_index=entry_i,confirmation_available_at=str(available),**base)
    return dict(status='INVALIDATED_BEFORE_ENTRY' if first_stop is not None else 'NO_CONFIRMATION_BEFORE_NOON',**base)

def execute(frame,symbol,date,plan,mult=1.,floor_pips=0.):
    if plan['status']!='ENTRY_READY':return dict(plan)
    times=pd.DatetimeIndex(frame.time);bid=frame.bid.to_numpy(float)
    point=.01 if symbol.endswith('JPY') else .0001;slip=point*.1*mult
    ask=bid+np.maximum((frame.ask.to_numpy(float)-bid)*mult,point*floor_pips)
    i=plan['entry_index'];d=plan['direction'];stop=plan['stop_bid'];entry=ask[i]+slip if d==1 else bid[i]-slip
    risk=entry-stop if d==1 else stop+(ask[i]-bid[i])-entry
    if risk<=0:return dict(status='INVALID_ENTRY_GEOMETRY')
    target=entry+d*2*risk;end=pd.Timestamp(date+' 16:00',tz='Europe/London').tz_convert('UTC')
    stops=bid<=stop if d==1 else bid>=stop;targets=bid>=target if d==1 else ask<=target
    terminal=(times>=end)|stops|targets;terminal[:i+1]=False;ix=np.flatnonzero(terminal)
    if not len(ix):return dict(status='UNPRICED_OPEN_POSITION')
    j=int(ix[0]);reason='EOD' if times[j]>=end else 'SL' if stops[j] else 'TP2'
    exit_price=target-slip*d if reason=='TP2' else bid[j]-slip if d==1 else ask[j]+slip
    commission=4.*(1. if symbol.endswith('USD') else entry)/100000*mult
    return dict(status='CLOSED',entry_time=str(times[i]),exit_time=str(times[j]),entry=entry,exit=exit_price,
        stop_bid=stop,initial_risk=risk,target=target,reason=reason,commission_r=commission/risk,
        price_net_r=d*(exit_price-entry)/risk,net_r=d*(exit_price-entry)/risk-commission/risk,
        breakout_available_at=plan['breakout_available_at'],retest_time=plan['retest_time'],confirmation_available_at=plan['confirmation_available_at'])

def calendar():return pd.DatetimeIndex([d for m in MONTHS for d in pd.bdate_range(m+'-01',pd.Timestamp(m+'-01')+pd.offsets.MonthEnd(0))])
def ci(daily):
    v=np.asarray(daily);rng=np.random.default_rng(173);n=len(v);totals=[]
    for _ in range(10000):
        starts=rng.integers(0,n,size=(n+4)//5);ix=((starts[:,None]+np.arange(5))%n).ravel()[:n];totals.append(v[ix].sum())
    return np.quantile(totals,[.025,.975]).tolist()
def daily(rows):
    out=pd.Series(0.,index=calendar())
    for row in rows:
        if row['outcome']['status']=='CLOSED':out.loc[pd.Timestamp(row['date'])]+=row['outcome']['net_r']
    return out
def summary(rows,baseline):
    closed=[r for r in rows if r['outcome']['status']=='CLOSED'];v=np.array([r['outcome']['net_r'] for r in closed]);loss=-v[v<0].sum();day=daily(rows);delta=day-daily(baseline)
    return dict(fills=len(v),net_r=float(v.sum()),pf=float(v[v>0].sum()/loss) if loss else None,by_month={m:float(day[day.index.strftime('%Y-%m')==m].sum()) for m in MONTHS},
        block_total_ci95=ci(day),paired_delta_net_r=float(delta.sum()),paired_delta_ci95=ci(delta),baseline_net_r=float(daily(baseline).sum()),
        statuses=pd.Series([r['outcome']['status'] for r in rows]).value_counts().to_dict())

def run():
    declaration=freeze();old=read(PRIOR/'native_outcomes.json')+read(EXT/'outcomes.json')
    manifests={**read(PRIOR/'quote_manifest_frozen.json')['files'],**read(EXT/'quote_manifest_frozen.json')['files']}
    universes={r['symbol']+'_'+r['date']:r for r in old if r['scenario']=='OBSERVED_QUOTES_1x'}
    rows=[];digests={};last_symbol=None
    for key,row in sorted(universes.items()):
        p=Path(manifests[key]['path']);assert sha(p)==manifests[key]['sha256'],key
        frame=pd.read_parquet(p);frame.time=pd.to_datetime(frame.time,utc=True);plan=prepare(frame,row['date'])
        for name,mult,floor in SCENARIOS:
            rows.append(dict(symbol=row['symbol'],date=row['date'],scenario=name,rvol=row['rvol'],outcome=execute(frame,row['symbol'],row['date'],plan,mult,floor)))
        digests[str(p)]=manifests[key]['sha256']
        if row['symbol']!=last_symbol:last_symbol=row['symbol'];print('RETEST',last_symbol,flush=True)
    unknown={'BLOCKED_TAPE_COVERAGE','BLOCKED_FEATURE','BLOCKED_ENTRY_COVERAGE','UNPRICED_OPEN_POSITION','INVALID_ENTRY_GEOMETRY'}
    complete=not any(r['outcome']['status'] in unknown for r in rows)
    save(BASE/'outcomes.json',rows)
    result={cohort:{name:summary([r for r in rows if r['scenario']==name and (cohort=='control' or r['rvol'] is not None and r['rvol']>=1)],
        [r for r in old if r['scenario']==name and (cohort=='control' or r['rvol'] is not None and r['rvol']>=1)]) for name,_,_ in SCENARIOS} for cohort in ['primary','control']}
    primary=result['primary'];checks=dict(complete_coverage=complete,at_least_100_primary_fills=primary['COST_STRESS_1.5x']['fills']>=100,
        positive_1_5x=primary['COST_STRESS_1.5x']['net_r']>0,positive_2x=primary['COST_STRESS_2x']['net_r']>0,positive_min_1pip=primary['MIN_SPREAD_1PIP']['net_r']>0,
        stressed_ci_lower_positive=primary['COST_STRESS_1.5x']['block_total_ci95'][0]>0)
    save(BASE/'results.json',dict(complete_coverage=complete,results=result,gate=dict(passed=all(checks.values()),checks=checks),live_approved=False))
    for p,digest in {**declaration['hashes'],**digests}.items():assert sha(Path(p))==digest,p
    save(BASE/'integrity_check.json',dict(passed=True,sources=len(declaration['hashes']),tapes=len(digests),all_rehashed_after=True))
    flat=[{**{k:v for k,v in r.items() if k!='outcome'},**r['outcome']} for r in rows];fields=sorted(set().union(*(r.keys() for r in flat)))
    with (BASE/'outcomes.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(flat)
    print('RETEST_COMPLETE',complete,checks,flush=True)

if __name__=='__main__':{'freeze':freeze,'run':run}[sys.argv[1]]()
