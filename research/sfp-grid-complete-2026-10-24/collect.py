"""Read-only narrow broker history repair; no orders or terminal restarts."""
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib,shutil,time
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
import complete as s

def clock_qa(f,reference,start,end,step):
    bars=f.set_index('time').bid.resample('15min').last().dropna()
    bars=bars[(bars.index>=start)&(bars.index+pd.Timedelta(minutes=15)<=end)]
    ref=reference.set_index('datetime').close
    joined=pd.concat([bars.rename('quote'),ref.rename('native')],axis=1).dropna()
    errors=abs(joined.quote-joined.native)
    fraction=float((errors<=2*step+step*1e-6).mean()) if len(errors) else 0.
    return dict(passed=bool(len(errors)>=8 and fraction>=.95),compared_bars=len(errors),
        fraction_within2steps=fraction,max_abs_error=float(errors.max()) if len(errors) else None)

def main():
    m=s.measure();p=m.verify();cases=m.read(s.HERE/'cases_frozen.json');index=m.tape_index()
    tasks={}
    for c in cases:
        key=c['symbol']+'_'+c['day'];start=pd.Timestamp(c['available_at']);end=start+pd.Timedelta(hours=5,seconds=5)
        if key not in tasks:tasks[key]=dict(symbol=c['symbol'],day=c['day'],start=start,end=end)
        else:tasks[key]['start']=min(tasks[key]['start'],start);tasks[key]['end']=max(tasks[key]['end'],end)
    file=s.HERE/'quote_manifest.json';manifest=m.read(file) if file.exists() else dict(files={},complete=False)
    directory=s.HERE/'tapes';directory.mkdir(exist_ok=True)
    prices={sym:m.load_prices(sym)[0] for sym in m.SYMBOLS}
    terminal='C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe'
    assert mt5.initialize(terminal,timeout=10000),str(mt5.last_error())
    try:
        account=mt5.account_info();info=mt5.terminal_info()
        assert account is not None and account.server=='FivePercentOnline-Real'
        assert info is not None and info.connected
        initial_free=shutil.disk_usage(s.HERE).free
        m.write(s.HERE/'data_session.json',dict(server=account.server,connected=True,read_only_calls=True,no_orders=True,
            terminal_restarted=False,paid_API_spend_USD=0,requested_symbol_days=len(tasks)))
        for number,(key,t) in enumerate(tasks.items(),1):
            if key in manifest['files']:
                old=manifest['files'][key]
                if old.get('path'):assert m.sha(Path(old['path']))==old['sha256']
                continue
            free=shutil.disk_usage(s.HERE).free
            if free<2*1024**3 or initial_free-free>1.5*1024**3:
                m.write(file,manifest);raise RuntimeError('Read-only collection storage budget exceeded')
            sym=t['symbol'];start=t['start'];end=t['end'];step=.01 if sym=='XAUUSD' else .00001
            candidates=index.get((sym,t['day']),[]);best=None
            for old in candidates:
                path=Path(old['path'])
                if not path.exists():continue
                if m.sha(path)!=old['sha256']:raise RuntimeError('Frozen existing tape changed '+str(path))
                f=pd.read_parquet(path);f.time=pd.to_datetime(f.time,utc=True)
                if not f.empty and f.time.min()<=start+pd.Timedelta(seconds=5) and f.time.max()>=end:
                    best=(f,path,old);break
            if best:
                f,path,old=best;attempts=[];method='REUSED_COMPLETE_FROZEN_TAPE';raw_digest=old.get('raw_sha256',old.get('raw_numpy_sha256'))
            else:
                offset=2+int(bool(start.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
                raw=None;attempts=[]
                for attempt in range(3):
                    raw=mt5.copy_ticks_range(sym,(start+pd.Timedelta(hours=offset)).to_pydatetime(),
                        (end+pd.Timedelta(hours=offset,seconds=5)).to_pydatetime(),mt5.COPY_TICKS_ALL)
                    attempts.append(dict(attempt=attempt+1,rows=0 if raw is None else len(raw),error=str(mt5.last_error())))
                    if raw is not None and len(raw):break
                    time.sleep(1)
                if raw is None or not len(raw):
                    manifest['files'][key]=dict(status='MISSING_BROKER_QUOTES',attempts=attempts,requested_start=str(start),requested_end=str(end))
                    m.write(file,manifest);print('MISSING',key,flush=True);continue
                r=pd.DataFrame(raw);raw_digest=hashlib.sha256(raw.tobytes()).hexdigest()
                f=pd.DataFrame(dict(time=pd.to_datetime(r.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=offset),bid=r.bid,ask=r.ask,flags=r['flags']))
                f=f[(f.time>=start)&(f.time<=end)].reset_index(drop=True)
                path=directory/(key+'.parquet');assert not path.exists()
                temp=path.with_suffix('.partial');f.to_parquet(temp,index=False,compression='zstd',compression_level=6);temp.replace(path)
                method='MT5_READ_ONLY_RANGE'
            assert not f.empty and f.time.is_monotonic_increasing
            assert ((f.bid>0)&(f.ask>=f.bid)&np.isfinite(f.bid)&np.isfinite(f.ask)).all()
            if not((f.time.dt.year==2025).all()):raise RuntimeError('Quote calendar invalid')
            qa=clock_qa(f,prices[sym],start,end,step)
            manifest['files'][key]=dict(status='AVAILABLE',path=str(path),sha256=m.sha(path),raw_numpy_sha256=raw_digest,
                method=method,attempts=attempts,rows=len(f),first=str(f.time.min()),last=str(f.time.max()),
                requested_start=str(start),requested_end=str(end),clock_qa=qa,
                max_gap_seconds=float(f.time.diff().dt.total_seconds().max()),median_spread=float((f.ask-f.bid).median()))
            m.write(file,manifest);print('COLLECT',number,len(tasks),key,len(f),method,'CLOCK',qa['passed'],flush=True)
        manifest['complete']=len(manifest['files'])==len(tasks)
        manifest['all_clock_qa_passed']=all(v['status']=='AVAILABLE' and v['clock_qa']['passed'] for v in manifest['files'].values())
        m.write(file,manifest);m.write(s.HERE/'quote_manifest_frozen.json',manifest)
        m.write(s.HERE/'status.json',dict(stage='COLLECTED',symbol_days=len(tasks),all_clock_qa_passed=manifest['all_clock_qa_passed']))
        print('COLLECTION_FINISHED',manifest['complete'],'CLOCK',manifest['all_clock_qa_passed'],flush=True)
    finally:mt5.shutdown()

if __name__=='__main__':main()
