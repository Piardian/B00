"""Fixed-rule extension to four predeclared historical months. No orders."""
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch
import sys,json,hashlib,shutil
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
PRIOR=BASE.parent/'london-quote-validation-2026-10-23'
sys.path.insert(0,str(PRIOR));sys.path.insert(0,str(ROOT))
import quote_engine
from scripts.normalize_broker_history import broker_to_utc
SYMBOLS=['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD']
MONTHS=['2025-04','2025-05','2025-09','2025-10']
SCENARIOS=[('OBSERVED_QUOTES_1x',1.,0.),('COST_STRESS_1.5x',1.5,0.),('COST_STRESS_2x',2.,0.),('MIN_SPREAD_1PIP',1.,1.)]
TERMINAL='C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe'
REFERENCE=Path('C:/Users/piard/Desktop/MegalordProject/audit/daytrade-session-2026-10-22/evidence/twelvedata_EURUSD_15m.csv.gz')
ORIGINAL_OPENING=quote_engine.opening

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,payload):
    temp=path.with_suffix('.partial');temp.write_text(json.dumps(payload,indent=2,default=str),encoding='utf8');temp.replace(path)
def schedule():
    rows=[]
    for first,last in [('2025-04','2025-05'),('2025-09','2025-10')]:
        begin=pd.Timestamp(first+'-01');end=pd.Timestamp(last+'-01')+pd.offsets.MonthEnd(0)
        rows += [(str(x.date()),True) for x in pd.bdate_range(end=begin-pd.Timedelta(days=1),periods=14)]
        rows += [(str(x.date()),False) for x in pd.bdate_range(begin,end)]
    return rows

def native_opening(frame,date):
    if 'flags' not in frame:raise ValueError('Native BID flags missing')
    return ORIGINAL_OPENING(frame[(frame['flags'].astype('int64')&2)!=0],date)

def freeze():
    prior=json.loads((PRIOR/'protocol_frozen.json').read_text())['declaration']
    expected=prior['files'][str(PRIOR/'quote_engine.py')]
    if sha(PRIOR/'quote_engine.py')!=expected:raise RuntimeError('Original quote engine changed')
    files=[Path(__file__),BASE/'test_extension.py',PRIOR/'quote_engine.py',ROOT/'scripts/normalize_broker_history.py',REFERENCE]
    d=dict(months=MONTHS,symbols=SYMBOLS,scenarios=SCENARIOS,
        user_constraints='OnlyThe5ers,onlyhistoricaldata,no live or paper orders',
        unchanged='Exactpriorquote_engine.pyhash;nativeBID-flagopening14-dayRVOL>=1;controlwithoutfilter;08:00-08:15Londonrange,openingdirection,onepairday,entrybefore12London,oppositebidbandvirtualSL,full2R,EOD16London',
        selection='Fixed4monthsbeforeoutcomes,noearlystoponsuccess;priorFebMarretainedseparatelyandcombinedall6months;notprospectiveandnotgloballyuntouchedOOS',
        quality='Samefirstquote<=5s/EODfirstquote<=5s/maxtapegap60s;missingfailedcoverageisunknownnotflat;nativeM15OHLCvolumematch;independentM15clockcorr>=.7margin>=.15min16bars,>=20strongdaysoverall>=8eachmonth,noconflicts',
        statistics='5observeddaycircularblockbootstrap10000seed173;yearmonthwindowsallreported;pairedfiltered-minus-controlannualizationnotused;priortrialsnotmultiplicityadjusted;notaccountportfolio',
        fees='Unchangedassumed$4/100kunitsroundtrip+0.1pip/yourside;observedbidask;1.5/2xfactor;1pipminspreadstress;not verified historical personal account charges',
        gate='Completecoverage,clockandnativebarQA,>=100primaryfills,newfourmonthnetpositiveat1.5/2xand1pipfloor,newperiodCIlo>0;6monthcombinedalsoevaluated;passingnotliveapproval',
        source_files={str(p):sha(p) for p in files},prior_native_protocol_sha256=sha(PRIOR/'native_volume_protocol.json'),prior_outcomes_sha256=sha(PRIOR/'native_outcomes.json'),
        collector_read_only=True,live_approved=False)
    path=BASE/'protocol_frozen.json'
    if path.exists():
        if json.loads(path.read_text())['declaration']!=json.loads(json.dumps(d)):raise RuntimeError('Frozen extension changed')
    else:
        save(path,dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=d))
        for i,p in enumerate(files):(BASE/'frozen_sources'/f'{i:02}_{p.name}').write_bytes(p.read_bytes())
    return d

def collect():
    freeze();out=BASE/'tapes';out.mkdir(exist_ok=True)
    path=BASE/'quote_manifest.json';manifest=json.loads(path.read_text()) if path.exists() else dict(provider='The5ers',files={},complete=False)
    previous=json.loads((PRIOR/'quote_manifest_frozen.json').read_text())
    if not mt5.initialize(TERMINAL,timeout=10000):raise RuntimeError(str(mt5.last_error()))
    try:
        if mt5.account_info().server!='FivePercentOnline-Real':raise RuntimeError('Wrongbroker')
        manifest['broker_server']='FivePercentOnline-Real';manifest['terminal']=TERMINAL
        for symbol in SYMBOLS:
            spec=mt5.symbol_info(symbol)
            manifest.setdefault('symbol_specs',{})[symbol]={k:getattr(spec,k,None) for k in ['digits','trade_tick_size','trade_contract_size','currency_profit']}
            for date,warmup in schedule():
                key=symbol+'_'+date
                if key in manifest['files']:
                    m=manifest['files'][key]
                    if m.get('path') and sha(Path(m['path']))!=m['sha256']:raise RuntimeError('Tapechanged'+key)
                    continue
                if key in previous['files']:
                    m=dict(previous['files'][key]);assert sha(Path(m['path']))==m['sha256'];m.update(warmup=warmup,reused_prior=True,status='AVAILABLE');manifest['files'][key]=m;save(path,manifest);continue
                if shutil.disk_usage(BASE).free<1.5*1024**3:raise RuntimeError('Diskheadroom below1.5GiB;no files deleted')
                start=pd.Timestamp(f'{date} 08:00',tz='Europe/London').tz_convert('UTC')
                end=start+pd.Timedelta(minutes=15) if warmup else pd.Timestamp(f'{date} 16:00',tz='Europe/London').tz_convert('UTC')+pd.Timedelta(seconds=5)
                offset=2+int(bool(start.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
                raw=mt5.copy_ticks_range(symbol,(start+pd.Timedelta(hours=offset)).to_pydatetime(),(end+pd.Timedelta(hours=offset)).to_pydatetime(),mt5.COPY_TICKS_ALL)
                if raw is None or not len(raw):
                    manifest['files'][key]=dict(symbol=symbol,date=date,warmup=warmup,status='MISSING_BROKER_QUOTES',error=str(mt5.last_error()));save(path,manifest);continue
                f=pd.DataFrame(raw);stamp=pd.to_datetime(f.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=offset)
                f=pd.DataFrame(dict(time=stamp,bid=f.bid,ask=f.ask,flags=f['flags']));f=f[(f.time>=start)&(f.time<=end)].reset_index(drop=True)
                if f.empty or not f.time.is_monotonic_increasing or not ((f.bid>0)&(f.ask>=f.bid)).all():raise RuntimeError('Invalidquotes'+key)
                target=out/f'{key}.parquet';temp=target.with_suffix('.partial');f.to_parquet(temp,compression='zstd',use_dictionary=False);temp.replace(target)
                spread=f.ask-f.bid
                manifest['files'][key]=dict(path=str(target),sha256=sha(target),raw_numpy_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),
                    symbol=symbol,date=date,warmup=warmup,status='AVAILABLE',rows=len(f),first=str(f.time.iloc[0]),last=str(f.time.iloc[-1]),
                    broker_offset_hours=offset,zero_spread_fraction=float((spread==0).mean()),max_gap_seconds=float(f.time.diff().dt.total_seconds().max()))
                save(path,manifest)
            print('COLLECTED',symbol,'files',sum(k.startswith(symbol+'_') for k in manifest['files']),'freeGiB',round(shutil.disk_usage(BASE).free/1024**3,2),flush=True)
        manifest['complete']=True;save(path,manifest)
    finally:mt5.shutdown()

def features_and_native_qa():
    freeze();manifest=json.loads((BASE/'quote_manifest.json').read_text());features=[];qa=[]
    if not mt5.initialize(TERMINAL,timeout=10000):raise RuntimeError(str(mt5.last_error()))
    try:
        if mt5.account_info().server!='FivePercentOnline-Real':raise RuntimeError('Wrongbroker')
        for symbol in SYMBOLS:
            natives=[]
            for begin,end in [('2025-03-01','2025-06-02'),('2025-08-01','2025-11-03')]:
                raw=mt5.copy_rates_range(symbol,mt5.TIMEFRAME_M15,pd.Timestamp(begin,tz='UTC').to_pydatetime(),pd.Timestamp(end,tz='UTC').to_pydatetime())
                if raw is None:raise RuntimeError('No native M15')
                n=pd.DataFrame(raw);n['time_utc']=broker_to_utc(pd.to_datetime(n.time,unit='s',utc=True));natives.append(n)
            native=pd.concat(natives).drop_duplicates('time_utc').set_index('time_utc')
            volumes=[];last_block=None
            for date,warmup in schedule():
                block=0 if date<'2025-06' else 1
                if block!=last_block:volumes=[];last_block=block
                m=manifest['files'].get(symbol+'_'+date,{})
                if m.get('status')!='AVAILABLE':
                    features.append(dict(symbol=symbol,date=date,warmup=warmup,status='MISSING_QUOTES'));volumes.append(None);continue
                f=pd.read_parquet(m['path']);f.time=pd.to_datetime(f.time,utc=True);feat=native_opening(f,date)
                n=native.loc[feat['start']] if feat['start'] in native.index else None;point=manifest['symbol_specs'][symbol]['trade_tick_size']
                match=n is not None and int(n.tick_volume)==feat['volume'] and abs(float(n.high)-feat['high'])<=point+1e-12 and abs(float(n.low)-feat['low'])<=point+1e-12 and int(np.sign(float(n.close-n.open)))==feat['direction']
                qa.append(dict(symbol=symbol,date=date,passed=bool(match)))
                ready=len(volumes)>=14 and all(v is not None for v in volumes[-14:])
                rvol=feat['volume']/np.mean(volumes[-14:]) if ready else None
                features.append(dict(symbol=symbol,date=date,warmup=warmup,status='READY' if (warmup or ready) and match else 'BLOCKED_FEATURE',rvol=rvol,volume=feat['volume']))
                volumes.append(feat['volume'])
            print('NATIVE_QA',symbol,flush=True)
    finally:mt5.shutdown()
    save(BASE/'features.json',features);save(BASE/'native_qa.json',dict(checked=len(qa),passed=all(x['passed'] for x in qa),rows=qa))
    if not all(x['passed'] for x in qa):raise RuntimeError('Native feature disagreement')

def clock_qa():
    freeze();ref=pd.read_csv(REFERENCE);ref.index=pd.to_datetime(ref.datetime,utc=True);ref_return=np.log(ref.close/ref.open).rename('reference')
    manifest=json.loads((BASE/'quote_manifest.json').read_text());rows=[]
    for date,warmup in schedule():
        if warmup:continue
        m=manifest['files'].get('EURUSD_'+date,{})
        if m.get('status')!='AVAILABLE':continue
        f=pd.read_parquet(m['path']).set_index('time');f=f[f.index.tz_convert('Europe/London').hour<16]
        bars=f.bid.resample('15min').ohlc().dropna();value=np.log(bars.close/bars.open)
        for shift in range(-3,4):
            x=value.copy();x.index+=pd.Timedelta(hours=shift)
            joined=pd.concat([x.rename('broker'),ref_return],axis=1,sort=True).dropna()
            if len(joined)>=16:rows.append(dict(date=date,shift=shift,n=len(joined),corr=float(joined.broker.corr(joined.reference))))
    scores=pd.DataFrame(rows);scores.to_csv(BASE/'clock_scores.csv',index=False);winners=[]
    for day,g in scores.groupby('date'):
        g=g.sort_values('corr',ascending=False)
        if g.iloc[0]['corr']>=.7 and g.iloc[0]['corr']-g.iloc[1]['corr']>=.15:winners.append(dict(date=day,shift=int(g.iloc[0]['shift']),corr=float(g.iloc[0]['corr'])))
    per_month={m:sum(x['date'].startswith(m) for x in winners) for m in MONTHS};conflicts=[x for x in winners if x['shift']!=0]
    passed=len(winners)>=20 and min(per_month.values())>=8 and not conflicts
    save(BASE/'clock_qa.json',dict(passed=passed,strong_days=len(winners),by_month=per_month,conflicts=conflicts,winners=winners));print('CLOCK_QA',passed,per_month)
    if not passed:raise RuntimeError('Clock QA failed')

def summary(rows,months):
    closed=[x for x in rows if x['outcome']['status']=='CLOSED'];values=np.array([x['outcome']['net_r'] for x in closed]);loss=-values[values<0].sum()
    calendar=pd.DatetimeIndex([d for m in months for d in pd.bdate_range(m+'-01',pd.Timestamp(m+'-01')+pd.offsets.MonthEnd(0))]);daily=pd.Series(0.,index=calendar)
    for x in closed:daily.loc[pd.Timestamp(x['date'])]+=x['outcome']['net_r']
    rng=np.random.default_rng(173);n=len(daily);boots=[];v=daily.to_numpy()
    for _ in range(10000):
        starts=rng.integers(0,n,size=(n+4)//5);ix=((starts[:,None]+np.arange(5))%n).ravel()[:n];boots.append(v[ix].sum())
    return dict(fills=len(closed),net_r=float(values.sum()),pf=float(values[values>0].sum()/loss) if loss else None,
        mean_net_r=float(values.mean()) if len(values) else None,win_pct=float((values>0).mean()*100) if len(values) else None,
        by_month={m:sum(x['outcome']['net_r'] for x in closed if x['date'].startswith(m)) for m in months},
        block_total_ci95=np.quantile(boots,[.025,.975]).tolist(),without_best5=float(np.sort(values)[:-5].sum()) if len(values)>=5 else None,
        statuses=pd.Series([x['outcome']['status'] for x in rows]).value_counts().to_dict())

def replay():
    declaration=freeze();manifest=json.loads((BASE/'quote_manifest.json').read_text())
    assert manifest['complete'] and json.loads((BASE/'clock_qa.json').read_text())['passed'] and json.loads((BASE/'native_qa.json').read_text())['passed']
    for m in manifest['files'].values():
        if m.get('path') and sha(Path(m['path']))!=m['sha256']:raise RuntimeError('Tape changed')
    save(BASE/'quote_manifest_frozen.json',manifest)
    features=json.loads((BASE/'features.json').read_text());lookup={(x['symbol'],x['date']):x for x in features};rows=[]
    for symbol in SYMBOLS:
        checkpoint=BASE/f'checkpoint_{symbol}.json'
        if checkpoint.exists():rows+=json.loads(checkpoint.read_text());continue
        per_symbol=[]
        for day,warmup in schedule():
            if warmup:continue
            meta=manifest['files'][symbol+'_'+day];feat=lookup[symbol,day]
            if feat['status']!='READY':
                for name,m,floor in SCENARIOS:per_symbol.append(dict(symbol=symbol,date=day,scenario=name,rvol=None,outcome=dict(status='BLOCKED_FEATURE')))
                continue
            f=pd.read_parquet(meta['path']);f.time=pd.to_datetime(f.time,utc=True)
            for name,m,floor in SCENARIOS:
                with patch.object(quote_engine,'opening',native_opening):result=quote_engine.replay(f,symbol,day,m,floor)
                per_symbol.append(dict(symbol=symbol,date=day,scenario=name,rvol=feat['rvol'],outcome=result))
        save(checkpoint,per_symbol);rows+=per_symbol;print('REPLAYED',symbol,flush=True)
    for path,digest in declaration['source_files'].items():
        if sha(Path(path))!=digest:raise RuntimeError('Source changed')
    prior=json.loads((PRIOR/'native_outcomes.json').read_text());combined=prior+rows
    result={}
    for label,data,months in [('extension',rows,MONTHS),('combined',combined,sorted(['2025-02','2025-03']+MONTHS))]:
        result[label]={cohort:{name:summary([x for x in data if x['scenario']==name and(cohort=='CLASSIC_ALL' or x['rvol'] is not None and x['rvol']>=1)],months) for name,m,floor in SCENARIOS} for cohort in ['CLASSIC_ALL','CLASSIC_RVOL_GE1']}
    complete=all(x['outcome']['status'] not in ['BLOCKED_FEATURE','BLOCKED_TAPE_COVERAGE','UNPRICED_OPEN_POSITION'] for x in rows)
    save(BASE/'outcomes.json',rows);save(BASE/'results.json',dict(complete_coverage=complete,results=result))
    print('EXTENSION_COMPLETE',complete,flush=True)

if __name__=='__main__':{'freeze':freeze,'collect':collect,'native':features_and_native_qa,'clock':clock_qa,'replay':replay}[sys.argv[1]]()
