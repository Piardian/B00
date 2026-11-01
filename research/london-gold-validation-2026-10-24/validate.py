"""Separate, predeclared historical validation; read-only broker access."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, json, sys, hashlib, shutil
import pandas as pd
import numpy as np

BASE=Path(__file__).resolve().parent
OLD=BASE.parent/'london-gold-2026-10-24'
spec=importlib.util.spec_from_file_location('frozen_gold',OLD/'study.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
MONTHS=['2025-07','2025-08']
CACHE=Path('C:/Users/piard/AppData/Roaming/MetaQuotes/Terminal/10CE948A1DFC9A8C27E56E827008EBD4/bases/FivePercentOnline-Real/ticks/XAUUSD')

def save(name,obj):g.save(BASE/name,obj)
def load(name):return g.read(BASE/name)
def dates():return g.dates(MONTHS)
def verify():
    p=load('protocol_frozen.json')
    for path,digest in p['hashes'].items():assert g.sha(Path(path))==digest,path
    return p

def freeze():
    assert not (BASE/'protocol_frozen.json').exists()
    assert g.sha(OLD/'study.py')=='110d3b0b0295edc7e0e40596f5356d7c48823053e869062218e74c891e94b6b9'
    paths=[Path(__file__),BASE/'guarded_collect.ps1',OLD/'study.py',OLD/'protocol_frozen.json',OLD/'results.json',OLD/'outcomes.json',OLD/'cost_evidence.json',OLD/'clock_qa.json',g.ROOT/'scripts/normalize_broker_history.py']
    save('protocol_frozen.json',dict(frozen_utc=datetime.now(timezone.utc).isoformat(),months=MONTHS,
        authorization='User explicitly requested separate validation despite original development CI gate failing. Original gate and results remain unchanged.',
        classification='Held aside for this exact gold rule, but dates seen in earlier broad research; NOT pristine global OOS or prospective.',
        strategy='Exact frozen_gold.replay, unchanged entry/stop/target/time/cost/scenarios. Virtual BID-trigger short stop; actual ASK exit. No filters or optimizations.',
        statistics='Same 10000 circular five-businessday bootstrap seed173; reserve separately and combined Jan-Aug. All weekdays, missing coverage blocks conclusions.',
        checks='Complete44days, native opening prices/direction, existing independent broker clock QA; reserve positive at1.5x and2x and both months positive1.5x; combined1.5x CI lower>0. Report each separately, no automatic live promotion.',
        clock='JulyAug broker UTC+3 USsummer, LondonBST; same regime independently verified in original clock QA. Direct JulyAug EURUSD reference overlap additionally measured; absence disclosed, not fabricated.',
        limitations='2025 commission unverified; synthetic fills/slippage; historical and limited sample. Even checks passing are evidence supporting candidate, not guaranteed edge or live approval.',
        disk='Only already nonempty JulyAug caches; start>=2GiB, external emergency1GiB guard; no terminal launch/settings/orders.',
        hashes={str(p):g.sha(p) for p in paths},live_approved=False))
    print('FROZEN',flush=True)

def collect():
    verify()
    for m in MONTHS:assert (CACHE/(m.replace('-','')+'.tkc')).stat().st_size>0
    assert shutil.disk_usage(BASE).free>=2*1024**3
    assert g.mt5.initialize(g.TERMINAL,timeout=10000),g.mt5.last_error()
    try:
        assert g.mt5.account_info().server=='FivePercentOnline-Real'
        ti=g.mt5.terminal_info()
        save('terminal_session.json',dict(read_only_task=True,trade_allowed=ti.trade_allowed,tradeapi_disabled=ti.tradeapi_disabled,settings_changed=False,orders_sent=False))
        for symbol,tf,label in [('XAUUSD',g.mt5.TIMEFRAME_M15,'gold_m15'),('EURUSD',g.mt5.TIMEFRAME_M15,'clock_eurusd_m15')]:
            target=BASE/(label+'.parquet')
            if not target.exists():
                raw=g.mt5.copy_rates_range(symbol,tf,datetime(2025,7,1,tzinfo=timezone.utc),datetime(2025,9,2,tzinfo=timezone.utc))
                assert raw is not None and len(raw),g.mt5.last_error()
                pd.DataFrame(raw).to_parquet(target,compression='zstd')
        native_hashes={str(BASE/(x+'.parquet')):g.sha(BASE/(x+'.parquet')) for x in ['gold_m15','clock_eurusd_m15']}
        if (BASE/'native_frozen.json').exists():assert load('native_frozen.json')==native_hashes
        else:save('native_frozen.json',native_hashes)
        folder=BASE/'tapes';folder.mkdir(exist_ok=True)
        manifest=load('quote_manifest.json') if (BASE/'quote_manifest.json').exists() else dict(files={},complete=False)
        for date in dates():
            if date in manifest['files']:continue
            assert shutil.disk_usage(BASE).free>1100*1024**2
            start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');end=start+pd.Timedelta(hours=8)
            raw=g.mt5.copy_ticks_range('XAUUSD',(start+pd.Timedelta(hours=3)).to_pydatetime(),(end+pd.Timedelta(hours=3,seconds=5)).to_pydatetime(),g.mt5.COPY_TICKS_ALL)
            assert raw is not None and len(raw),(date,g.mt5.last_error())
            r=pd.DataFrame(raw);f=pd.DataFrame(dict(time=pd.to_datetime(r.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=3),bid=r.bid,ask=r.ask,flags=r['flags']))
            f=f[(f.time>=start)&(f.time<=end+pd.Timedelta(seconds=5))].reset_index(drop=True)
            target=folder/f'XAUUSD_{date}.parquet'
            f.to_parquet(target,compression='zstd',compression_level=9,use_dictionary=False,use_byte_stream_split=['bid','ask'])
            manifest['files'][date]=dict(path=str(target),sha256=g.sha(target),raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),rows=len(f))
            save('quote_manifest.json',manifest)
            print('COLLECT',date,len(f),round(shutil.disk_usage(BASE).free/1024**3,2),flush=True)
        manifest['complete']=True;save('quote_manifest.json',manifest)
    finally:g.mt5.shutdown()

def stats(rows,calendar):
    closed=[r for r in rows if r['outcome']['status']=='CLOSED'];v=np.array([r['outcome']['net_r'] for r in closed])
    daily=pd.Series(0.,index=pd.to_datetime(calendar))
    for r in closed:daily.loc[pd.Timestamp(r['date'])]+=r['outcome']['net_r']
    eq=daily.cumsum();loss=-v[v<0].sum()
    return dict(fills=len(v),net_r=float(v.sum()),pf=float(v[v>0].sum()/loss) if loss else None,
        win_pct=float((v>0).mean()*100) if len(v) else None,block_total_ci95=g.block_ci(daily),
        by_month={m:float(daily[daily.index.strftime('%Y-%m')==m].sum()) for m in sorted(set(x[:7] for x in calendar))},
        max_dd_unit_r=float((eq.cummax().clip(lower=0)-eq).max()),without_best5=float(np.sort(v)[:-5].sum()),
        statuses=pd.Series([r['outcome']['status'] for r in rows]).value_counts().to_dict())

def run():
    verify();manifest=load('quote_manifest.json');assert manifest['complete'] and len(manifest['files'])==44
    for path,digest in load('native_frozen.json').items():assert g.sha(Path(path))==digest
    n=pd.read_parquet(BASE/'gold_m15.parquet');n.index=g.broker_to_utc(pd.to_datetime(n.time,unit='s',utc=True))
    rows=[];qa=[]
    for date in dates():
        meta=manifest['files'][date];path=Path(meta['path']);assert g.sha(path)==meta['sha256']
        f=pd.read_parquet(path);start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC')
        op=f[(f.time>=start)&(f.time<start+pd.Timedelta(minutes=15))&((f['flags'].astype('int64')&2)!=0)]
        bar=n.loc[start] if start in n.index else None
        values=dict(open=float(op.bid.iloc[0]),high=float(op.bid.max()),low=float(op.bid.min()),close=float(op.bid.iloc[-1])) if len(op) else {}
        match=bar is not None and bool(values) and all(abs(values[k]-float(bar[k]))<=.010000001 for k in values) and np.sign(values['close']-values['open'])==np.sign(bar.close-bar.open)
        qa.append(dict(date=date,price_direction_match=bool(match),volume_match=bool(bar is not None and len(op)==bar.tick_volume)))
        for name,m in g.SCENARIOS:rows.append(dict(date=date,scenario=name,outcome=g.replay(f,date,m) if match else dict(status='BLOCKED_NATIVE_FEATURE')))
    old=g.read(OLD/'outcomes.json');results={};combined={}
    for name,m in g.SCENARIOS:
        results[name]=stats([r for r in rows if r['scenario']==name],dates())
        combined[name]=stats([r for r in old+rows if r['scenario']==name],g.dates()+dates())
    complete=not any(r['outcome']['status'] in g.UNKNOWN for r in rows)
    ref=pd.read_csv(g.REFERENCE);refdates=set(pd.to_datetime(ref.datetime,utc=True).dt.strftime('%Y-%m-%d'))
    clock=dict(prior_independent_clock_passed=g.read(OLD/'clock_qa.json')['passed'],same_validated_summer_regime=True,direct_reference_overlap_days=len(set(dates())&refdates),direct_gold_reference=False)
    checks=dict(complete_44_days=complete,native_prices=all(q['price_direction_match'] for q in qa),prior_clock=clock['prior_independent_clock_passed'],reserve_positive_1_5x=results['STRESS_1.5x']['net_r']>0,reserve_positive_2x=results['STRESS_2x']['net_r']>0,both_reserve_months_positive=all(v>0 for v in results['STRESS_1.5x']['by_month'].values()),combined_ci_lower_positive=combined['STRESS_1.5x']['block_total_ci95'][0]>0)
    save('outcomes.json',rows);pd.DataFrame([dict(date=r['date'],scenario=r['scenario'],**r['outcome']) for r in rows]).to_csv(BASE/'outcomes.csv',index=False)
    save('native_qa.json',qa);save('results.json',dict(reserve=results,combined=combined,checks=checks,all_checks_pass=all(checks.values()),clock=clock,original_development_gate_passed=False,commission_2025_verified=False,live_approved=False))
    verify();save('integrity_check.json',dict(passed=True,tapes=44,native_hashes=load('native_frozen.json'),protocol_sha256=g.sha(BASE/'protocol_frozen.json')))
    print(json.dumps(load('results.json'),indent=2),flush=True)

if __name__=='__main__':{'freeze':freeze,'collect':collect,'run':run}[sys.argv[1]]()
