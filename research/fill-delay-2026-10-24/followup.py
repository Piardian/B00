"""Additional locked months for15minute TTL, using existing broker tape cache.

Declared after58case screen, before new candidate or PNL computation. Retrospective,
not pristine project-wide OOS: tapes previously used by separate classic ORB work.
"""
import argparse,hashlib,json,shutil
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
from study import HERE,ROOT,sha,write,verify,stats,day_ci,SPREADS,VARIANTS
from execution import replay
from normalize_clock import broker_to_utc

MONTHS=['2025-04','2025-05','2025-09','2025-10']
SYMBOLS=['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD']


def freeze():
    verify()
    if (HERE/'followup_protocol.json').exists():raise RuntimeError('Already frozen')
    paths=list(HERE.glob('*.py'))+list((HERE/'frozen_engine').glob('*.py'))
    write(HERE/'followup_protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),months=MONTHS,symbols=SYMBOLS,
      stage='After first58case results. Before these additional months candidate/PNL results. Same15TTL, no threshold search. Existing prices used previously for separate classicORB; not pristine OOS or prospective.',
      selection='All4months with existing complete quote archive chosen together, all6samepairs; first daily normalized detector setup; cancellation consumes day,no later replacement.',
      rules='Same frozen detector/generator and replay; only pendingTTL240 versus15. Original reaction exit always. Exactly15min excluded; filled positions continue original lifecycle,London16:30flat.',
      costs='Same .2/.5/.9/1.5pip assumed spread,USD4/100kroundtrip,.2pip exit slip. Primary.5,stress1.5. ActualbidM1,not actualask/fee lifecycle.',
      data='Native brokerH1/M15Jan-Nov2025 for warmup/input. Existing lockedLondon08-16tick tapes plus cached16-16:31tails for all selected days. No interpolation. Read-only existing explicitThe5ersterminal, no paidAPI.',
      disk='Small bar outputs only. Existing tick-month caches required, free>=1GiB and cumulative netgrowth<=64MiB during tail reads; stop if guard exceeded. No user file deletion.',
      success_gate='15TTL must outperform reference overall at.5/1.5 and have positive returns with at least one fill in EACH of4months at BOTH costs; no coverage/replay unknown. Positive combined old data cannot rescue failed followup. Even passing is not live permission or edge proof.',
      source_manifest_sha256=sha(HERE/'followup_source_manifest.json'),
      hashes={str(p.relative_to(HERE)):sha(p) for p in paths}))


def check():
    verify();p=json.loads((HERE/'followup_protocol.json').read_text(encoding='utf-8'))
    for n,h in p['hashes'].items():
        if sha(HERE/n)!=h:raise RuntimeError('Frozen followup source mismatch:'+n)
    if sha(HERE/'followup_source_manifest.json')!=p['source_manifest_sha256']:raise RuntimeError('Quote manifest changed')
    return p


def collect():
    import MetaTrader5 as mt5
    check();out=HERE/'followup_prices';out.mkdir(exist_ok=True)
    mpath=HERE/'followup_price_manifest.json';m=json.loads(mpath.read_text()) if mpath.exists() else dict(files={},complete=False)
    tapes=json.loads((HERE/'followup_source_manifest.json').read_text())['files']
    days=[d for month in MONTHS for d in pd.bdate_range(month+'-01',pd.Timestamp(month+'-01')+pd.offsets.MonthEnd(0))]
    if not mt5.initialize('C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe',timeout=10000):raise RuntimeError('Existing The5ers unavailable')
    try:
        account=mt5.account_info();info=mt5.terminal_info()
        if account is None or account.server!='FivePercentOnline-Real':raise RuntimeError('Wrong server')
        initial_free=shutil.disk_usage(HERE).free
        for symbol in SYMBOLS:
            for tf,kind in [('1h',mt5.TIMEFRAME_H1),('15m',mt5.TIMEFRAME_M15),('1m',None)]:
                key=symbol+'_'+tf
                if key in m['files']:
                    if sha(HERE/m['files'][key]['path'])!=m['files'][key]['sha256']:raise RuntimeError('Stored followup data changed')
                    continue
                free=shutil.disk_usage(HERE).free
                if free<1024**3 or initial_free-free>64*1024**2:raise RuntimeError('Small cached read disk budget exceeded')
                if tf!='1m':
                    raw=mt5.copy_rates_range(symbol,kind,pd.Timestamp('2025-01-01 02:00Z').to_pydatetime(),pd.Timestamp('2025-11-01 03:00Z').to_pydatetime())
                    if raw is None or not len(raw):raise RuntimeError('Missing native history')
                    f=pd.DataFrame(raw);f['datetime']=broker_to_utc(pd.to_datetime(f.time,unit='s',utc=True));f['volume']=f.tick_volume
                    f=f[(f.datetime>=pd.Timestamp('2025-01-01',tz='UTC'))&(f.datetime<pd.Timestamp('2025-11-01',tz='UTC'))][['datetime','open','high','low','close','volume']]
                    provenance=dict(raw_numpy_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),method='Native bidOHLC andtick_volume; US-DSTbrokerclock normalized')
                else:
                    parts=[];sources=[]
                    for d in days:
                        free=shutil.disk_usage(HERE).free
                        if free<1024**3 or initial_free-free>64*1024**2:raise RuntimeError('Cached tail disk budget exceeded')
                        date=str(d.date());meta=tapes[symbol+'_'+date];p=Path(meta['path'])
                        if sha(p)!=meta['sha256']:raise RuntimeError('Existing quote tape changed')
                        f0=pd.read_parquet(p);end=pd.Timestamp(date+' 16:00',tz='Europe/London').tz_convert('UTC')
                        cache=Path(info.data_path)/'bases'/account.server/'ticks'/symbol/(d.strftime('%Y%m')+'.tkc')
                        if not cache.exists():raise RuntimeError('Required tick month not cached')
                        offset=2+int(bool(end.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
                        a=end+pd.Timedelta(hours=offset);b=a+pd.Timedelta(minutes=31)
                        raw=mt5.copy_ticks_range(symbol,a.to_pydatetime(),b.to_pydatetime(),mt5.COPY_TICKS_ALL)
                        if raw is None or not len(raw):raise RuntimeError('Missing quote tail')
                        r=pd.DataFrame(raw);tail=pd.DataFrame(dict(time=broker_to_utc(pd.to_datetime(r.time_msc,unit='ms',utc=True)),bid=r.bid))
                        combined=pd.concat([f0.loc[f0.time<end,['time','bid']],tail.loc[(tail.time>=end)&(tail.time<end+pd.Timedelta(minutes=31)),['time','bid']]],ignore_index=True)
                        if not combined.time.is_monotonic_increasing or not (combined.bid>0).all():raise RuntimeError('Invalid source tape')
                        groups=combined.set_index('time').bid.resample('min');bars=groups.ohlc();bars['volume']=groups.size()
                        parts.append(bars.dropna().reset_index().rename(columns={'time':'datetime'}))
                        sources.append(dict(date=date,tape_sha256=meta['sha256'],tail_raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest()))
                    f=pd.concat(parts,ignore_index=True);provenance=dict(method='Bid tick-derived M1, no interpolation',sources=sources)
                if f.empty or f.datetime.duplicated().any() or not f.datetime.is_monotonic_increasing:raise RuntimeError('Invalid final bar chronology')
                dest=out/(key+'.parquet');f.to_parquet(dest,index=False)
                m['files'][key]=dict(path=str(dest.relative_to(HERE)),sha256=sha(dest),rows=len(f),**provenance)
                write(mpath,m);print('FOLLOWUP_BARS',key,len(f),flush=True)
        m['complete']=True;write(mpath,m)
    finally:mt5.shutdown()


def run():
    check();m=json.loads((HERE/'followup_price_manifest.json').read_text())
    if not m.get('complete'):raise RuntimeError('Incomplete followup prices')
    lock=HERE/'followup_price_manifest_frozen.json'
    if lock.exists() and json.loads(lock.read_text())!=m:raise RuntimeError('Followup manifest changed')
    if not lock.exists():write(lock,m)
    frames={}
    for key,v in m['files'].items():
        if sha(HERE/v['path'])!=v['sha256']:raise RuntimeError('Followup price changed')
        symbol,tf=key.split('_');frames[symbol,tf]=pd.read_parquet(HERE/v['path'])
    import generator_frozen as generator
    generator.MONTHS=MONTHS;generator.SYMBOLS=SYMBOLS
    candidates,coverage=generator.generate(frames)
    write(HERE/'followup_candidates.json',candidates);write(HERE/'followup_coverage.json',coverage)
    if any(r['missing_m15'] or not r['atr_ready'] for r in coverage):
        write(HERE/'followup_status.json',dict(status='BLOCKED_COVERAGE'));print('FOLLOWUP BLOCKED coverage');return
    outcomes=[]
    for i,c in enumerate(candidates):
        for sp in SPREADS:
            for variant,ttl in VARIANTS.items():
                result=replay(c['signal'],c['available_at'],frames[c['symbol'],'1m'],'passive',spread_pips=sp,pending_ttl_minutes=ttl)
                outcomes.append(dict(case_id=str(i),source='FOLLOWUP',day=c['day'],month=c['month'],symbol=c['symbol'],variant=variant,spread_pips=sp,**result))
    summaries=[dict(spread_pips=sp,variant=v,**stats([r for r in outcomes if r['spread_pips']==sp and r['variant']==v])) for sp in SPREADS for v in VARIANTS]
    index={(r['case_id'],r['spread_pips'],r['variant']):r for r in outcomes};pairs=[]
    for i,c in enumerate(candidates):
        for sp in SPREADS:
            ref=index[str(i),sp,'REFERENCE_240'];short=index[str(i),sp,'TTL_15']
            if short['filled_at']:
                for field in ['filled_at','closed_at','reason','net_r']:
                    if short[field]!=ref[field]:raise RuntimeError('Followup retained lifecycle changed')
            if not short['filled_at'] and short['status']=='CLOSED' and(short['net_r']!=0 or short['commission_r']!=0):raise RuntimeError('Canceled order incurs fee/profit')
            pairs.append(dict(day=c['day'],month=c['month'],spread_pips=sp,case_id=str(i),removed=bool(ref['filled_at'] and not short['filled_at']),
              delta_r=short['net_r']-ref['net_r'] if short['net_r'] is not None and ref['net_r'] is not None else None))
    check();write(HERE/'followup_outcomes.json',outcomes);write(HERE/'followup_summary.json',summaries);write(HERE/'followup_pairs.json',pairs)
    write(HERE/'followup_status.json',dict(status='COMPLETE' if all(r['status']=='CLOSED' for r in outcomes) else 'UNRESOLVED',pair_days=len(coverage),candidates=len(candidates),outcome_rows=len(outcomes),live_promotion=False))
    print(json.dumps([r for r in summaries if r['spread_pips'] in [.5,1.5]],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','collect','run','check']);a=p.parse_args()
    {'freeze':freeze,'collect':collect,'run':run,'check':check}[a.action]()
