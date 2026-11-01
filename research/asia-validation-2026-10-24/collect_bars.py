"""Read only native broker M15/H1 and bid M1 for locked Feb/Mar2025 study."""
from pathlib import Path
import json,hashlib,shutil
import pandas as pd
import MetaTrader5 as mt5
from normalize_clock import broker_to_utc
from zoneinfo import ZoneInfo

HERE=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):p.write_text(json.dumps(j,indent=2),encoding='utf-8')


def tick_m1(symbol,info,account):
    """Existing full London tapes + cached final31minutes, no price interpolation."""
    manifest=json.loads((HERE/'source_quote_manifest.json').read_text())
    parts=[];sources=[]
    for day in pd.bdate_range('2025-02-01','2025-03-31'):
        date=str(day.date());meta=manifest['files'][symbol+'_'+date];path=Path(meta['path'])
        if sha(path)!=meta['sha256']:raise RuntimeError('Existing quote tape changed')
        tape=pd.read_parquet(path);end=pd.Timestamp(date+' 16:00',tz='Europe/London').tz_convert('UTC')
        cache=Path(info.data_path)/'bases'/account.server/'ticks'/symbol/(day.strftime('%Y%m')+'.tkc')
        if not cache.exists():raise RuntimeError('Tail month not cached')
        if shutil.disk_usage(HERE).free<2*1024**3:raise RuntimeError('Disk headroom below2GiB')
        offset=2+int(bool(end.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
        a=end+pd.Timedelta(hours=offset);b=a+pd.Timedelta(minutes=31)
        raw=mt5.copy_ticks_range(symbol,a.to_pydatetime(),b.to_pydatetime(),mt5.COPY_TICKS_ALL)
        if raw is None or not len(raw):raise RuntimeError('Missing16:00-16:31 tail '+symbol+' '+date)
        r=pd.DataFrame(raw)
        tail=pd.DataFrame(dict(time=broker_to_utc(pd.to_datetime(r.time_msc,unit='ms',utc=True)),bid=r.bid))
        combined=pd.concat([tape.loc[tape.time<end,['time','bid']],tail.loc[(tail.time>=end)&(tail.time<end+pd.Timedelta(minutes=31)),['time','bid']]],ignore_index=True)
        if not combined.time.is_monotonic_increasing or not (combined.bid>0).all():raise RuntimeError('Invalid bid tape')
        grouped=combined.set_index('time').bid.resample('min')
        bars=grouped.ohlc();bars['volume']=grouped.size();bars=bars.dropna().reset_index().rename(columns={'time':'datetime'})
        parts.append(bars);sources.append(dict(date=date,tape_sha256=meta['sha256'],tail_raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest()))
    return pd.concat(parts,ignore_index=True),sources


def main():
    plan=json.loads((HERE/'protocol_v2.json').read_text(encoding='utf-8'))
    for name,h in plan['code_hashes'].items():
        if sha(HERE/name)!=h:raise RuntimeError('Frozen code changed:'+name)
    output=HERE/'prices';output.mkdir(exist_ok=True)
    mpath=HERE/'price_manifest.json';manifest=json.loads(mpath.read_text()) if mpath.exists() else dict(source='FivePercentOnline-Real native bid OHLC, tick_volume; not actual bid/ask lifecycle',files={})
    if not mt5.initialize('C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe',timeout=10000):raise RuntimeError('The5ers unavailable')
    try:
        account=mt5.account_info()
        if account is None or account.server!='FivePercentOnline-Real':raise RuntimeError('Unexpected server')
        info=mt5.terminal_info()
        for symbol in plan['symbols']:
            for tf,native in [('1h',mt5.TIMEFRAME_H1),('15m',mt5.TIMEFRAME_M15),('1m',mt5.TIMEFRAME_M1)]:
                key=symbol+'_'+tf
                if key in manifest['files']:
                    if sha(HERE/manifest['files'][key]['path'])!=manifest['files'][key]['sha256']:raise RuntimeError('Stored prices changed')
                    continue
                if shutil.disk_usage(HERE).free<2*1024**3:raise RuntimeError('Disk headroom below2GiB')
                if tf=='1m':
                    f,sources=tick_m1(symbol,info,account)
                    p=output/(key+'.parquet');f.to_parquet(p,index=False)
                    manifest['files'][key]=dict(path=str(p.relative_to(HERE)),sha256=sha(p),rows=len(f),first=str(f.datetime.iloc[0]),last=str(f.datetime.iloc[-1]),method='Existing tick tapes plus cached31minute tails; bid OHLC and tick-event volume, no interpolation',sources=sources)
                    write(mpath,manifest);print('BARS',key,len(f),flush=True);continue
                start=pd.Timestamp('2025-02-01',tz='UTC') if tf=='1m' else pd.Timestamp('2024-12-01',tz='UTC')
                end=pd.Timestamp('2025-04-01',tz='UTC')
                raw=mt5.copy_rates_range(symbol,native,(start+pd.Timedelta(hours=2)).to_pydatetime(),(end+pd.Timedelta(hours=3)).to_pydatetime())
                if raw is None or not len(raw):raise RuntimeError('Missing rates '+key)
                f=pd.DataFrame(raw);f['datetime']=broker_to_utc(pd.to_datetime(f.time,unit='s',utc=True));f['volume']=f.tick_volume
                f=f[(f.datetime>=start)&(f.datetime<end)][['datetime','open','high','low','close','volume']]
                if f.empty:raise RuntimeError('No normalized bars '+key)
                if f.datetime.duplicated().any() or not f.datetime.is_monotonic_increasing:raise RuntimeError('Invalid broker chronology')
                p=output/(key+'.parquet');f.to_parquet(p,index=False)
                manifest['files'][key]=dict(path=str(p.relative_to(HERE)),sha256=sha(p),raw_numpy_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),rows=len(f),first=str(f.datetime.iloc[0]),last=str(f.datetime.iloc[-1]))
                write(mpath,manifest);print('BARS',key,len(f),flush=True)
        manifest['complete']=True;write(mpath,manifest)
    finally:mt5.shutdown()


if __name__=='__main__':main()
