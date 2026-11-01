"""Read-only cached16:00-16:31bid/ask tails for all90locked cases."""
import json,hashlib,shutil
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import MetaTrader5 as mt5
from normalize_clock import broker_to_utc

HERE=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):p.write_text(json.dumps(j,indent=2),encoding='utf-8')


def main():
    plan=json.loads((HERE/'protocol.json').read_text())
    for n,h in plan['code_hashes'].items():
        if sha(HERE/n)!=h:raise RuntimeError('Frozen code changed')
    cases=json.loads((HERE/'cases_frozen.json').read_text(encoding='utf-8'))
    path=HERE/'tail_manifest.json';manifest=json.loads(path.read_text()) if path.exists() else dict(files={},complete=False)
    out=HERE/'tails';out.mkdir(exist_ok=True)
    if not mt5.initialize('C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe',timeout=10000):raise RuntimeError('Existing broker terminal unavailable')
    try:
        account=mt5.account_info();info=mt5.terminal_info()
        if account is None or account.server!='FivePercentOnline-Real':raise RuntimeError('Unexpected broker server')
        initial_free=shutil.disk_usage(HERE).free
        for c in cases:
            key=c['case_id']
            if key in manifest['files']:
                if sha(HERE/manifest['files'][key]['path'])!=manifest['files'][key]['sha256']:raise RuntimeError('Tail changed')
                continue
            free=shutil.disk_usage(HERE).free
            if free<512*1024**2 or initial_free-free>64*1024**2:raise RuntimeError('Small cached-read disk budget exceeded')
            cache=Path(info.data_path)/'bases'/account.server/'ticks'/c['symbol']/(c['day'][:7].replace('-','')+'.tkc')
            if not cache.exists():raise RuntimeError('Month cache missing; no broad download permitted')
            start=pd.Timestamp(c['day']+' 16:00',tz='Europe/London').tz_convert('UTC');end=start+pd.Timedelta(minutes=31)
            offset=2+int(bool(start.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
            raw=mt5.copy_ticks_range(c['symbol'],(start+pd.Timedelta(hours=offset)).to_pydatetime(),(end+pd.Timedelta(hours=offset)).to_pydatetime(),mt5.COPY_TICKS_ALL)
            if raw is None or not len(raw):raise RuntimeError('Missing real quote tail')
            f=pd.DataFrame(raw);f=pd.DataFrame(dict(time=broker_to_utc(pd.to_datetime(f.time_msc,unit='ms',utc=True)),bid=f.bid,ask=f.ask,flags=f['flags']))
            f=f[(f.time>=start)&(f.time<end)].reset_index(drop=True)
            if f.empty or not f.time.is_monotonic_increasing or not ((f.bid>0)&(f.ask>=f.bid)).all():raise RuntimeError('Invalid quote tail')
            p=out/(key+'.parquet');f.to_parquet(p,index=False)
            manifest['files'][key]=dict(path=str(p.relative_to(HERE)),sha256=sha(p),raw_numpy_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),rows=len(f),first=str(f.time.iloc[0]),last=str(f.time.iloc[-1]),broker_clock_offset_hours=offset)
            write(path,manifest)
            if len(manifest['files'])%15==0:print('TAILS',len(manifest['files']),flush=True)
        manifest['complete']=True;write(path,manifest)
    finally:mt5.shutdown()


if __name__=='__main__':main()
