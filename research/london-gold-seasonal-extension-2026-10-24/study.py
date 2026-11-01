"""Frozen extension of gold ORB and fixed June-August shutdown. Data APIs only."""
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import sys,json,hashlib,shutil
import pandas as pd
import numpy as np
BASE=Path(__file__).resolve().parent
VALID=BASE.parent/'london-gold-validation-2026-10-24'
sys.path.insert(0,str(VALID))
import validate as v
g=v.g
MONTHS=list(pd.period_range('2025-01','2026-09',freq='M').astype(str))
NEW=MONTHS[8:]
HOLIDAYS={'2025-01-01','2025-04-18','2025-12-25','2026-01-01','2026-04-03'}

def save(name,obj):g.save(BASE/name,obj)
def read(name):return g.read(BASE/name)
def verify():
    p=read('protocol_frozen.json')
    for path,digest in p['hashes'].items():assert g.sha(Path(path))==digest,path
    return p
def freeze():
    assert not (BASE/'protocol_frozen.json').exists()
    paths=[Path(__file__),BASE/'guarded_collect.ps1',BASE/'readonly.ini',VALID/'validate.py',v.OLD/'study.py',v.OLD/'outcomes.json',VALID/'outcomes.json',v.OLD/'quote_manifest_frozen.json',VALID/'quote_manifest.json',v.OLD/'clock_qa.json',g.ROOT/'scripts/normalize_broker_history.py']
    save('protocol_frozen.json',dict(created_utc=datetime.now(timezone.utc).isoformat(),months=MONTHS,new_months=NEW,
        policies=['always_on','off_June_July_August'],hypothesis='Calendar shutdown JuneAugust exactly; no August-only or alternate season selection.',
        strategy='Exact hash-frozen original gold.replay, all timing cost and structural BID stop rules unchanged. No M1 or cost filter introduced in this seasonal experiment.',
        classification='Posthoc seasonality idea based on JanAug2025 outcomes. SepDec2025 and JanSep2026 not previously evaluated with this exact gold rule here, but earlier broad research saw historical data. Not prospective or pristine global OOS.',
        comparisons='2025full, 2025SepDec extension alone, 2026JanSep separate partial year, total21months descriptive. Never label2026full. Original JanAug results unchanged.',
        stats='Same10k circular5weekday bootstrap seed173 on full calendar; disabled days zero. Paired daily shutdown-minus-always delta and95CI. Calendar selection ignores outcome. Unknowns prevent full total/CI claims; resolved subtotals explicitly marked.',
        gate='Not live promotion. Research support requires complete price/clock QA, positive offsummer1.5x and2x separately2025 and2026partial, positive paired delta eachyear, positive new2025SepDec1.5x, combined offsummer1.5xCIlo>0, and no dependence on2025May alone. Failure means hypothesis unsupported, no further calendar optimization this turn.',
        clock='Previously validated UTC+2/+3 US DST; fresh EURUSD reference correlation offsets-3..3 assessed all overlapping days; require>=20strong zero-shift days in new period, no strong conflicts; report peryear counts and inherited vs direct evidence.',
        holidays=sorted(HOLIDAYS),holiday_policy='Only listed full closures if nativeD1 and LondonM15 both absent. Other missing weekdays unknown; no invented PnL.',
        storage='Warm caches all months only; external 0.5s guard1GiB; initial>=2GiB. Save exact compressed daily quotes+SHA and raw arraySHA; reuse first8months no copies. No cold history2024 request.',
        terminal='Attempt01 stopped before collection because existing external terminal was found. Attach read-only to existing session without changing its settings or closing it; record actual trade_allowed. Only if absent launch own terminal with ExpertsEnabled0 and close owned terminal after collection. No order API in task.',
        numeric_2025_commission_verified=False,live_approved=False,hashes={str(p):g.sha(p) for p in paths}))
    print('FROZEN',flush=True)

def collect():
    verify()
    for m in NEW:assert (v.CACHE/(m.replace('-','')+'.tkc')).stat().st_size>0
    assert g.mt5.initialize(g.TERMINAL,timeout=10000),g.mt5.last_error()
    try:
        assert g.mt5.account_info().server=='FivePercentOnline-Real'
        ti=g.mt5.terminal_info()
        save('terminal_session.json',dict(server='FivePercentOnline-Real',trade_allowed=ti.trade_allowed,tradeapi_disabled=ti.tradeapi_disabled,orders_sent=False))
        for symbol,tf,label in [('XAUUSD',g.mt5.TIMEFRAME_M15,'gold_m15'),('XAUUSD',g.mt5.TIMEFRAME_D1,'gold_d1'),('EURUSD',g.mt5.TIMEFRAME_M15,'clock_eurusd_m15')]:
            target=BASE/(label+'.parquet')
            if not target.exists():
                raw=g.mt5.copy_rates_range(symbol,tf,datetime(2025,1,1,tzinfo=timezone.utc),datetime(2026,10,2,tzinfo=timezone.utc))
                assert raw is not None and len(raw),g.mt5.last_error()
                pd.DataFrame(raw).to_parquet(target,compression='zstd')
        hashes={str(BASE/(s+'.parquet')):g.sha(BASE/(s+'.parquet')) for s in ['gold_m15','gold_d1','clock_eurusd_m15']}
        if (BASE/'native_frozen.json').exists():assert read('native_frozen.json')==hashes
        else:save('native_frozen.json',hashes)
        n=pd.read_parquet(BASE/'gold_m15.parquet');n.index=g.broker_to_utc(pd.to_datetime(n.time,unit='s',utc=True))
        d1=pd.read_parquet(BASE/'gold_d1.parquet');d1days=set(pd.to_datetime(d1.time,unit='s',utc=True).dt.strftime('%Y-%m-%d'))
        folder=BASE/'tapes';folder.mkdir(exist_ok=True)
        manifest=read('quote_manifest.json') if (BASE/'quote_manifest.json').exists() else dict(files={},complete=False)
        oldfiles={**g.read(v.OLD/'quote_manifest_frozen.json')['files'],**g.read(VALID/'quote_manifest.json')['files']}
        for date in g.dates(MONTHS):
            if date in manifest['files']:continue
            if date in oldfiles:
                meta=oldfiles[date].copy();meta.setdefault('status','AVAILABLE')
                if meta.get('path'):assert g.sha(Path(meta['path']))==meta['sha256']
                meta['reused']=True;manifest['files'][date]=meta;save('quote_manifest.json',manifest);continue
            assert shutil.disk_usage(BASE).free>1100*1024**2,'Storage limit'
            start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');end=start+pd.Timedelta(hours=8)
            if date in HOLIDAYS and date not in d1days and n[(n.index>=start)&(n.index<end)].empty:
                manifest['files'][date]=dict(status='CONFIRMED_HOLIDAY_CLOSED');save('quote_manifest.json',manifest);continue
            offset=2+int(bool(start.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
            raw=g.mt5.copy_ticks_range('XAUUSD',(start+pd.Timedelta(hours=offset)).to_pydatetime(),(end+pd.Timedelta(hours=offset,seconds=5)).to_pydatetime(),g.mt5.COPY_TICKS_ALL)
            if raw is None or not len(raw):
                manifest['files'][date]=dict(status='MISSING_BROKER_QUOTES',error=str(g.mt5.last_error()));save('quote_manifest.json',manifest);continue
            r=pd.DataFrame(raw);f=pd.DataFrame(dict(time=pd.to_datetime(r.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=offset),bid=r.bid,ask=r.ask,flags=r['flags']))
            f=f[(f.time>=start)&(f.time<=end+pd.Timedelta(seconds=5))].reset_index(drop=True)
            target=folder/f'XAUUSD_{date}.parquet';tmp=target.with_suffix('.partial')
            f.to_parquet(tmp,compression='zstd',compression_level=9,use_dictionary=False,use_byte_stream_split=['bid','ask']);tmp.replace(target)
            manifest['files'][date]=dict(status='AVAILABLE',path=str(target),sha256=g.sha(target),raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),rows=len(f),offset=offset)
            save('quote_manifest.json',manifest)
            print('COLLECT',date,len(f),'freeGiB',round(shutil.disk_usage(BASE).free/1024**3,2),flush=True)
        manifest['complete']=True;save('quote_manifest.json',manifest)
    finally:g.mt5.shutdown()

def clock():
    f=pd.read_parquet(BASE/'clock_eurusd_m15.parquet');f.index=g.broker_to_utc(pd.to_datetime(f.time,unit='s',utc=True));value=np.log(f.close/f.open)
    ref=pd.read_csv(g.REFERENCE);ref.index=pd.to_datetime(ref.datetime,utc=True);reference=np.log(ref.close/ref.open)
    winners=[]
    for date in g.dates(NEW):
        day=value[value.index.strftime('%Y-%m-%d')==date];scores=[]
        for shift in range(-3,4):
            z=day.copy();z.index+=pd.Timedelta(hours=shift)
            joined=pd.concat([z.rename('b'),reference.rename('r')],axis=1,sort=True).dropna()
            if len(joined)>=32:scores.append(dict(date=date,shift=shift,n=len(joined),corr=float(joined.b.corr(joined.r))))
        scores.sort(key=lambda x:x['corr'],reverse=True)
        if len(scores)>1 and scores[0]['corr']>=.7 and scores[0]['corr']-scores[1]['corr']>=.15:winners.append(scores[0])
    conflicts=[w for w in winners if w['shift']!=0]
    result=dict(passed=len(winners)>=20 and not conflicts,strong_days=len(winners),conflicts=conflicts,winners=winners,per_year={y:sum(w['date'].startswith(y) for w in winners) for y in ['2025','2026']},note='No independent gold feed; 2026 clock evidence may be inherited same broker regime if no reference overlap.')
    save('clock_qa.json',result);return result

def evaluate():
    verify();manifest=read('quote_manifest.json');assert manifest['complete']
    for path,digest in read('native_frozen.json').items():assert g.sha(Path(path))==digest
    cq=clock();n=pd.read_parquet(BASE/'gold_m15.parquet');n.index=g.broker_to_utc(pd.to_datetime(n.time,unit='s',utc=True))
    oldrows=g.read(v.OLD/'outcomes.json')+g.read(VALID/'outcomes.json');old={(r['date'],r['scenario']):r['outcome'] for r in oldrows}
    rows=[];qa=[]
    for date in g.dates(MONTHS):
        meta=manifest['files'][date]
        if meta['status']!='AVAILABLE':
            for name,m in g.SCENARIOS:rows.append(dict(date=date,scenario=name,outcome=dict(status=meta['status'])))
            continue
        path=Path(meta['path']);assert g.sha(path)==meta['sha256'];f=pd.read_parquet(path)
        start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC')
        op=f[(f.time>=start)&(f.time<start+pd.Timedelta(minutes=15))&((f['flags'].astype('int64')&2)!=0)]
        bar=n.loc[start] if start in n.index else None
        values=dict(open=float(op.bid.iloc[0]),high=float(op.bid.max()),low=float(op.bid.min()),close=float(op.bid.iloc[-1])) if len(op) else {}
        match=bar is not None and bool(values) and all(abs(values[k]-float(bar[k]))<=.010000001 for k in values) and np.sign(values['close']-values['open'])==np.sign(bar.close-bar.open)
        qa.append(dict(date=date,price_match=bool(match),volume_match=bool(bar is not None and len(op)==bar.tick_volume)))
        for name,m in g.SCENARIOS:
            outcome=g.replay(f,date,m) if match else dict(status='BLOCKED_NATIVE_FEATURE')
            if (date,name) in old:assert outcome==old[(date,name)],'Prior parity mismatch '+date
            rows.append(dict(date=date,scenario=name,outcome=outcome))
        if date.endswith('28'):print('REPLAY',date,flush=True)
    save('outcomes.json',rows);save('native_qa.json',qa)
    pd.DataFrame([dict(date=r['date'],scenario=r['scenario'],**r['outcome']) for r in rows]).to_csv(BASE/'outcomes.csv',index=False)
    groups={'2025_full':MONTHS[:12],'2025_new_SepDec':MONTHS[8:12],'2026_JanSep_partial':MONTHS[12:],'all_21months':MONTHS}
    results={}
    for group,months in groups.items():
        calendar=g.dates(months);results[group]={}
        for name,m in g.SCENARIOS:
            allrows=[r for r in rows if r['scenario']==name and r['date'][:7] in months]
            active=[r for r in allrows if r['date'][5:7] not in ['06','07','08']]
            unknown=[r['date'] for r in allrows if r['outcome']['status'] in g.UNKNOWN]
            unknown_active=[r['date'] for r in active if r['outcome']['status'] in g.UNKNOWN]
            result=dict(unknown_always=unknown,unknown_summeroff=unknown_active,complete_always=not unknown,complete_summeroff=not unknown_active)
            if not unknown:
                a=v.stats(allrows,calendar);b=v.stats(active,calendar)
                daily=pd.Series(0.,index=calendar)
                for r in allrows:
                    if r['date'][5:7] in ['06','07','08']:daily.loc[r['date']]-=r['outcome'].get('net_r',0)
                result.update(always_on=a,summer_off=b,paired_delta_net_r=float(daily.sum()),paired_delta_ci95=g.block_ci(daily),summeroff_without_2025May_r=sum(r['outcome'].get('net_r',0) for r in active if r['date'][:7]!='2025-05'))
            else:
                result.update(resolved_closed_always_net_r=sum(r['outcome'].get('net_r',0) for r in allrows),resolved_closed_summeroff_net_r=sum(r['outcome'].get('net_r',0) for r in active),note='Incomplete coverage: no full total/PF/CI claim')
            results[group][name]=result
    complete=all(r['outcome']['status'] not in g.UNKNOWN for r in rows)
    checks=dict(complete=complete,native=all(q['price_match'] for q in qa),clock=cq['passed'])
    if complete:
        for y in ['2025_full','2026_JanSep_partial']:
            checks[y+'_off_positive_1_5x']=results[y]['STRESS_1.5x']['summer_off']['net_r']>0
            checks[y+'_off_positive_2x']=results[y]['STRESS_2x']['summer_off']['net_r']>0
            checks[y+'_paired_delta_positive']=results[y]['STRESS_1.5x']['paired_delta_net_r']>0
        checks['new_2025SepDec_positive']=results['2025_new_SepDec']['STRESS_1.5x']['summer_off']['net_r']>0
        checks['combined_off_ci_lower_positive']=results['all_21months']['STRESS_1.5x']['summer_off']['block_total_ci95'][0]>0
        checks['without2025May_positive']=results['all_21months']['STRESS_1.5x']['summeroff_without_2025May_r']>0
    save('results.json',dict(results=results,checks=checks,all_checks_pass=all(checks.values()),complete=complete,live_approved=False,orders_sent=False))
    verify();save('integrity_check.json',dict(passed=True,days=len(manifest['files']),prior_parity_days=173,sources_rehashed=True,native_hashes=read('native_frozen.json')))
    print('EVALUATION_COMPLETE',json.dumps(checks),flush=True)

if __name__=='__main__':{'freeze':freeze,'collect':collect,'evaluate':evaluate}[sys.argv[1]]()
