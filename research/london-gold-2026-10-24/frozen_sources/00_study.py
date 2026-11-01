"""Frozen single London XAUUSD ORB, historical quotes only. No order APIs."""
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import sys,json,hashlib,shutil,csv
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT))
from scripts.normalize_broker_history import broker_to_utc
REFERENCE=Path('C:/Users/piard/Desktop/MegalordProject/audit/daytrade-session-2026-10-22/evidence/twelvedata_EURUSD_15m.csv.gz')
PRIOR_CLOCK=REFERENCE.parent.parent/'clock_validation.json'
TERMINAL='C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe'
MONTHS=['2025-01','2025-02','2025-03','2025-04','2025-05','2025-06']
RESERVE=['2025-07','2025-08']
CLOSED_DATES=['2025-01-01','2025-04-18']
SCENARIOS=[('OBSERVED_1x',1.),('STRESS_1.5x',1.5),('STRESS_2x',2.)]
UNKNOWN={'MISSING_BROKER_QUOTES','BLOCKED_COVERAGE','BLOCKED_NATIVE_FEATURE','INVALID_GEOMETRY','UNPRICED_POSITION'}

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):
    tmp=p.with_suffix('.partial');tmp.write_text(json.dumps(obj,indent=2,default=str),encoding='utf8');tmp.replace(p)
def dates(months=MONTHS):
    return [str(d.date()) for m in months for d in pd.bdate_range(m+'-01',pd.Timestamp(m+'-01')+pd.offsets.MonthEnd(0))]

def freeze():
    paths=[Path(__file__),BASE/'test_study.py',BASE/'preflight.py',BASE/'cost_evidence.json',BASE/'gold_m15.parquet',BASE/'gold_d1.parquet',BASE/'clock_eurusd_m15.parquet',ROOT/'scripts/normalize_broker_history.py',REFERENCE,PRIOR_CLOCK]
    evidence=read(BASE/'cost_evidence.json');s=evidence['symbol_spec']
    assert s['trade_contract_size']==100 and s['trade_tick_size']==.01 and s['currency_profit']=='USD'
    declaration=dict(
        symbol='XAUUSD',development_months=MONTHS,reserve_months=RESERVE,
        reserve_policy='Do not inspect reservestrategyoutcomes unless developmentgatepasses. Months seen by older broad research; this is held-aside historical data for this rule, NOT prospective or globally untouchedOOS.',
        model='SingleclassicLondonORB;08:00-08:15Europe/LondonhalfopenBIDrange;nativeBIDopeningcandledirection;firstBIDtouch/breaksameboundaryfrom08:15strictlybefore12:00;oneattempt/day;oppositeBIDbandsyntheticstructuralSL;full2R;EODfirstquote>=16:00within5s;nofilters,RVOL,M1confirmation,BE,partialsortrailing',
        execution='BuyASK+slip/sellBID-slip;longBIDexit/shortASKexit;SLstructuralBIDtriggerforbothdirectionsasoldclassicengine;exitonlynextorderedquote;EODprecedenceat16;SLbeforeTP;TPfavourablegapcappedat2Rtargetminusadverseslip;SLgapworseprice',
        cost='Perounceprice,USDprofit. CommissionRTperlot=max(8USD,2*entry*100ounces*0.001percent/100);divideby100forperounce. CalibratedconservativeASSUMPTION,envelopesflat4USD/sideandpercentage0.001percent/sideconsistentwith9roundedOctober2026fills;notknownhistorical2025tariff. Slippage0.05USD/ounce/side=5brokerstepsASSUMED. Stressmultipliesspread,slippage,commission1.5/2. NeverborrowFX4USDroundtrip.',
        scenarios=SCENARIOS,price_net_diagnostic='Samefillpaths beforecommission, stillincludesbidaskandslippage; ifnegativeunknownpositivecommissioncannotrescuethesesamefills. Notfrictionfreeorstrictupperboundacrossdifferententry/exitmodels.',
        quality='ChronologicalvalidBIDASK;firstopeningquote<=5s,EODquote<=5s,internalgap<=60s;nativeopeningM15OHLCwithinone0.01tickanddirectionequal;BIDflagvolumecomparedbutnotusedinstrategy. Missingunknownsnotflat.',
        holidays='Only2025-01-01and2025-04-18excludableifbothnativeD1andallLondonM15absent;goldNewYear/GoodFriday. Othermissingdatesunknown. Neverexcludeaweekdaysimplybecauseitlost.',
        clock='SamebrokerUTC+2winter/+3USsummerpreviouslyvalidatedagainstindependentEURUSDandNASDAQincludingUS/EUDSTgap. RevalidatepreflightEURUSDM15againstindependentTwelveDatareturnsforoffsets-3..+3:20strongdays>=.7corrand>=.15margin,noconflicts,atleastoneUS/EUDSTdisagreementday. Noindependentgoldfeedclaim.',
        gate='Completecoverage,clockandnativeQA,>=100developmentclosedtrades,positive1.5xand2x,1.5xblockCIlo>0,atleast4of6monthspositiveat1.5x,andbothJanMar/AprJunblockspositiveat1.5x. Onlythenreserve. Numeric2025commissionstillunverified;notliveapproval.',
        statistics='10000circular5weekdayblockstotalRseed173;allbusinessdaysincludingconfirmedholidaysinclocklength;confidenceexploratorynomultiplicitycorrection;independentunitRopportunitiesnotaccountreturnorpropDD',
        disk='Atleast600MiBfreebeforeeachdownload,450MiBnewtapesbudget;noexistingfilesdeleted;nativeMT5cachemaygrow;onlimitstopandpreservepartialmanifestwithoutnetclaim',
        terminal=TERMINAL,read_only=True,live_approved=False,
        hashes={str(p):sha(p) for p in paths})
    canonical=json.loads(json.dumps(declaration));p=BASE/'protocol_frozen.json'
    if p.exists():assert read(p)['declaration']==canonical,'Frozen study changed'
    else:
        save(p,dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=canonical));(BASE/'frozen_sources').mkdir(exist_ok=True)
        for i,source in enumerate(paths):(BASE/'frozen_sources'/f'{i:02}_{source.name}').write_bytes(source.read_bytes())
    return declaration

def native():
    f=pd.read_parquet(BASE/'gold_m15.parquet');f['utc']=broker_to_utc(pd.to_datetime(f.time,unit='s',utc=True));return f.set_index('utc')

def clock():
    freeze();f=pd.read_parquet(BASE/'clock_eurusd_m15.parquet');f.index=broker_to_utc(pd.to_datetime(f.time,unit='s',utc=True));value=np.log(f.close/f.open)
    ref=pd.read_csv(REFERENCE);ref.index=pd.to_datetime(ref.datetime,utc=True);reference=np.log(ref.close/ref.open)
    rows=[];winners=[]
    for date in dates():
        day=value[value.index.strftime('%Y-%m-%d')==date]
        scores=[]
        for shift in range(-3,4):
            v=day.copy();v.index+=pd.Timedelta(hours=shift);joined=pd.concat([v.rename('broker'),reference.rename('reference')],axis=1).dropna()
            if len(joined)>=32:scores.append(dict(date=date,shift=shift,n=len(joined),corr=float(joined.broker.corr(joined.reference))))
        rows+=scores;scores.sort(key=lambda x:x['corr'],reverse=True)
        if len(scores)>1 and scores[0]['corr']>=.7 and scores[0]['corr']-scores[1]['corr']>=.15:winners.append(scores[0])
    conflicts=[x for x in winners if x['shift']!=0]
    dst_gap=[x for x in winners if bool(pd.Timestamp(x['date'],tz='America/New_York').dst())!=bool(pd.Timestamp(x['date'],tz='Europe/London').dst())]
    passed=len(winners)>=20 and not conflicts and len(dst_gap)>=1
    save(BASE/'clock_qa.json',dict(passed=passed,strong_days=len(winners),conflicts=conflicts,us_eu_dst_gap_days=dst_gap,winners=winners))
    pd.DataFrame(rows).to_csv(BASE/'clock_scores.csv',index=False)
    print('CLOCK',passed,len(winners),'DST_GAP',len(dst_gap),flush=True)
    assert passed,'Clock not validated'

def collect():
    freeze();assert read(BASE/'clock_qa.json')['passed']
    folder=BASE/'tapes';folder.mkdir(exist_ok=True);p=BASE/'quote_manifest.json'
    manifest=read(p) if p.exists() else dict(server='FivePercentOnline-Real',symbol='XAUUSD',files={},complete=False)
    n=native();d1=pd.read_parquet(BASE/'gold_d1.parquet');d1days=set(pd.to_datetime(d1.time,unit='s',utc=True).dt.strftime('%Y-%m-%d'))
    if not mt5.initialize(TERMINAL,timeout=10000):raise RuntimeError(str(mt5.last_error()))
    try:
        assert mt5.account_info().server=='FivePercentOnline-Real'
        for date in dates():
            if date in manifest['files']:
                old=manifest['files'][date]
                if old.get('path'):assert sha(Path(old['path']))==old['sha256']
                continue
            start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');end=pd.Timestamp(date+' 16:00',tz='Europe/London').tz_convert('UTC')
            if date in CLOSED_DATES and date not in d1days and n[(n.index>=start)&(n.index<end)].empty:
                manifest['files'][date]=dict(status='CONFIRMED_HOLIDAY_CLOSED',date=date);save(p,manifest);continue
            if shutil.disk_usage(BASE).free<600*1024**2 or sum(x.stat().st_size for x in folder.glob('*.parquet'))>450*1024**2:raise RuntimeError('Storage limit; preserve partial study; no deletion')
            offset=2+int(bool(start.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
            raw=mt5.copy_ticks_range('XAUUSD',(start+pd.Timedelta(hours=offset)).to_pydatetime(),(end+pd.Timedelta(hours=offset,seconds=5)).to_pydatetime(),mt5.COPY_TICKS_ALL)
            if raw is None or not len(raw):
                manifest['files'][date]=dict(date=date,status='MISSING_BROKER_QUOTES',error=str(mt5.last_error()));save(p,manifest);continue
            r=pd.DataFrame(raw);f=pd.DataFrame(dict(time=pd.to_datetime(r.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=offset),bid=r.bid,ask=r.ask,flags=r['flags']))
            f=f[(f.time>=start)&(f.time<=end+pd.Timedelta(seconds=5))].reset_index(drop=True)
            if f.empty or not f.time.is_monotonic_increasing or not np.isfinite(f[['bid','ask']]).all().all() or not ((f.bid>0)&(f.ask>=f.bid)).all():raise RuntimeError('Invalid quotes '+date)
            target=folder/f'XAUUSD_{date}.parquet';temp=target.with_suffix('.partial');f.to_parquet(temp,compression='zstd',compression_level=9,use_dictionary=False,use_byte_stream_split=['bid','ask']);temp.replace(target)
            manifest['files'][date]=dict(date=date,status='AVAILABLE',path=str(target),sha256=sha(target),raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),
                rows=len(f),first=str(f.time.iloc[0]),last=str(f.time.iloc[-1]),offset_hours=offset,
                zero_spread_fraction=float((f.ask==f.bid).mean()),median_spread_usd=float((f.ask-f.bid).median()),max_gap_seconds=float(f.time.diff().dt.total_seconds().max()))
            save(p,manifest)
            if date.endswith(('07','14','21','28')):print('COLLECT',date,'ticks',len(f),'freeGiB',round(shutil.disk_usage(BASE).free/1024**3,2),flush=True)
        manifest['complete']=True;save(p,manifest);print('COLLECT_COMPLETE',len(manifest['files']),flush=True)
    finally:mt5.shutdown()

def replay(frame,date,mult=1.):
    f=frame.reset_index(drop=True);times=pd.DatetimeIndex(f.time);start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');end=start+pd.Timedelta(hours=8);deadline=start+pd.Timedelta(hours=4)
    if f.empty or not times.is_monotonic_increasing or not np.isfinite(f[['bid','ask']]).all().all() or not ((f.bid>0)&(f.ask>=f.bid)).all():return dict(status='BLOCKED_COVERAGE')
    if times[0]>start+pd.Timedelta(seconds=5) or times[-1]<end or times[-1]>end+pd.Timedelta(seconds=5) or f.time.diff().max()>pd.Timedelta(seconds=60):return dict(status='BLOCKED_COVERAGE')
    bid=f.bid.to_numpy(float);ask=bid+(f.ask.to_numpy(float)-bid)*mult;slip=.05*mult
    opening=np.flatnonzero((times>=start)&(times<start+pd.Timedelta(minutes=15))&((f['flags'].to_numpy(np.int64)&2)!=0))
    if not len(opening):return dict(status='BLOCKED_NATIVE_FEATURE')
    hi,lo=bid[opening].max(),bid[opening].min();direction=int(np.sign(bid[opening[-1]]-bid[opening[0]]))
    if direction==0 or hi<=lo:return dict(status='DOJI_OR_INVALID_RANGE')
    entries=np.flatnonzero((times>=start+pd.Timedelta(minutes=15))&(times<deadline)&((bid>=hi) if direction==1 else (bid<=lo)))
    if not len(entries):return dict(status='NO_ENTRY_BEFORE_NOON')
    i=int(entries[0]);entry=ask[i]+slip if direction==1 else bid[i]-slip;stop=lo if direction==1 else hi
    risk=entry-stop if direction==1 else stop+(ask[i]-bid[i])-entry
    if risk<=0:return dict(status='INVALID_GEOMETRY')
    target=entry+direction*2*risk;stop_hits=bid<=stop if direction==1 else bid>=stop;target_hits=bid>=target if direction==1 else ask<=target
    hits=(times>=end)|stop_hits|target_hits;hits[:i+1]=False;ix=np.flatnonzero(hits)
    if not len(ix):return dict(status='UNPRICED_POSITION')
    j=int(ix[0]);reason='EOD' if times[j]>=end else 'SL' if stop_hits[j] else 'TP2'
    exit_price=target-slip*direction if reason=='TP2' else bid[j]-slip if direction==1 else ask[j]+slip
    commission_lot=max(8.,2.*entry*100.*.001/100)*mult;commission_per_ounce=commission_lot/100.
    price_net=direction*(exit_price-entry)/risk
    return dict(status='CLOSED',entry_time=str(times[i]),exit_time=str(times[j]),direction=direction,entry=entry,exit=exit_price,
        stop_bid=stop,initial_risk=risk,target=target,reason=reason,price_net_r=float(price_net),commission_r=float(commission_per_ounce/risk),net_r=float(price_net-commission_per_ounce/risk),
        assumed_commission_usd_per_lot_roundtrip=float(commission_lot),range_usd=float(hi-lo))

def block_ci(daily):
    v=np.asarray(daily);n=len(v);rng=np.random.default_rng(173);totals=[]
    for _ in range(10000):
        starts=rng.integers(0,n,size=(n+4)//5);ix=((starts[:,None]+np.arange(5))%n).ravel()[:n];totals.append(v[ix].sum())
    return np.quantile(totals,[.025,.975]).tolist()
def summarize(rows):
    closed=[r for r in rows if r['outcome']['status']=='CLOSED'];v=np.array([r['outcome']['net_r'] for r in closed]);loss=-v[v<0].sum()
    daily=pd.Series(0.,index=pd.to_datetime(dates()))
    for r in closed:daily.loc[pd.Timestamp(r['date'])]+=r['outcome']['net_r']
    return dict(fills=len(closed),net_r=float(v.sum()),price_net_r_before_commission=float(sum(r['outcome']['price_net_r'] for r in closed)),
        commission_r=float(sum(r['outcome']['commission_r'] for r in closed)),pf=float(v[v>0].sum()/loss) if loss else None,
        win_pct=float((v>0).mean()*100) if len(v) else None,mean_net_r=float(v.mean()) if len(v) else None,
        by_month={m:float(daily[daily.index.strftime('%Y-%m')==m].sum()) for m in MONTHS},block_total_ci95=block_ci(daily),
        without_best5=float(np.sort(v)[:-5].sum()) if len(v)>=5 else None,statuses=pd.Series([r['outcome']['status'] for r in rows]).value_counts().to_dict())

def run():
    declaration=freeze();manifest=read(BASE/'quote_manifest.json');assert manifest['complete'] and read(BASE/'clock_qa.json')['passed']
    save(BASE/'quote_manifest_frozen.json',manifest);n=native();rows=[];qa=[];digests={}
    for date in dates():
        meta=manifest['files'][date]
        if meta['status']!='AVAILABLE':
            for name,m in SCENARIOS:rows.append(dict(date=date,scenario=name,outcome=dict(status=meta['status'])))
            continue
        p=Path(meta['path']);assert sha(p)==meta['sha256'];digests[str(p)]=meta['sha256'];f=pd.read_parquet(p);f.time=pd.to_datetime(f.time,utc=True)
        start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');opening=f[(f.time>=start)&(f.time<start+pd.Timedelta(minutes=15))&((f['flags'].astype('int64')&2)!=0)]
        native_bar=n.loc[start] if start in n.index else None
        values=dict(open=float(opening.bid.iloc[0]),high=float(opening.bid.max()),low=float(opening.bid.min()),close=float(opening.bid.iloc[-1])) if len(opening) else {}
        matches=native_bar is not None and bool(values) and all(abs(values[k]-float(native_bar[k]))<=.010000001 for k in values) and int(np.sign(values['close']-values['open']))==int(np.sign(native_bar.close-native_bar.open))
        qa.append(dict(date=date,price_direction_match=bool(matches),bid_flag_count=len(opening),native_volume=int(native_bar.tick_volume) if native_bar is not None else None,
            volume_match=bool(native_bar is not None and len(opening)==int(native_bar.tick_volume))))
        for name,m in SCENARIOS:rows.append(dict(date=date,scenario=name,outcome=replay(f,date,m) if matches else dict(status='BLOCKED_NATIVE_FEATURE')))
    complete=not any(r['outcome']['status'] in UNKNOWN for r in rows);results={name:summarize([r for r in rows if r['scenario']==name]) for name,m in SCENARIOS};p=results['STRESS_1.5x']
    checks=dict(complete_coverage=complete,clock_qa=read(BASE/'clock_qa.json')['passed'],native_price_qa=all(q['price_direction_match'] for q in qa),
        at_least_100_fills=p['fills']>=100,positive_1_5x=p['net_r']>0,positive_2x=results['STRESS_2x']['net_r']>0,
        stressed_ci_lower_positive=p['block_total_ci95'][0]>0,four_positive_months=sum(v>0 for v in p['by_month'].values())>=4,
        both_quarters_positive=sum(v for k,v in p['by_month'].items() if k<='2025-03')>0 and sum(v for k,v in p['by_month'].items() if k>='2025-04')>0)
    for path,digest in {**declaration['hashes'],**digests}.items():assert sha(Path(path))==digest,path
    save(BASE/'outcomes.json',rows);save(BASE/'native_qa.json',dict(passed=checks['native_price_qa'],rows=qa))
    save(BASE/'results.json',dict(complete_coverage=complete,results=results,gate=dict(passed=all(checks.values()),checks=checks),commission_2025_verified=False,reserve_evaluated=False,live_approved=False))
    flat=[dict(date=r['date'],scenario=r['scenario'],**r['outcome']) for r in rows];fields=sorted(set().union(*(r.keys() for r in flat)))
    with (BASE/'outcomes.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader();writer.writerows(flat)
    save(BASE/'integrity_check.json',dict(passed=True,sources=len(declaration['hashes']),tapes=len(digests),all_rehashed_after=True))
    print('GOLD_COMPLETE',complete,checks,flush=True)

if __name__=='__main__':{'freeze':freeze,'clock':clock,'collect':collect,'run':run}[sys.argv[1]]()
