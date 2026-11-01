"""Read only: 61 seconds of existing The5ers ticks for each locked decision.

No order/login/account-change methods. No full-month downloads requested.
"""
import hashlib
import json
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import MetaTrader5 as mt5

HERE=Path(__file__).resolve().parent
TERMINAL='C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')


def main():
    protocol=json.loads((HERE/'protocol_v2.json' if (HERE/'protocol_v2.json').exists() else HERE/'protocol.json').read_text(encoding='utf-8'))
    for name,expected in protocol['local_hashes'].items():
        if sha(HERE/name)!=expected:raise RuntimeError('Frozen input changed: '+name)
    setups=json.loads((HERE/'setups_frozen.json').read_text(encoding='utf-8'))
    path=HERE/'decision_quote_manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(provider='The5ers',scope='All33 locked candidate decision windows; no PNL selection',files={})
    if not mt5.initialize(TERMINAL,timeout=10000):raise RuntimeError('Existing The5ers terminal unavailable')
    try:
        account=mt5.account_info()
        if account is None or account.server!='FivePercentOnline-Real':raise RuntimeError('Expected broker server required')
        info=mt5.terminal_info()
        initial_free=shutil.disk_usage(HERE).free
        for i,c in enumerate(setups):
            key=str(i)
            if key in manifest['files']:
                stored=manifest['files'][key]
                if stored.get('status')=='CAPTURED' and sha(HERE/stored['path'])!=stored['sha256']:raise RuntimeError('Tape changed')
                continue
            at=pd.Timestamp(c['available_at']);symbol=c['signal']['symbol'].replace('/','')
            cache=Path(info.data_path)/'bases'/account.server/'ticks'/symbol/(at.strftime('%Y%m')+'.tkc')
            if not cache.exists():
                manifest['files'][key]=dict(status='MISSING',reason='NO_EXISTING_MONTH_CACHE',symbol=symbol,as_of=str(at));write(path,manifest)
                continue
            free=shutil.disk_usage(HERE).free
            if free<2*1024**3 or initial_free-free>128*1024**2:raise RuntimeError('Cached-window disk budget exceeded; stop')
            spec=mt5.symbol_info(symbol)
            if spec is None:raise RuntimeError('Symbol specification missing')
            point=float(spec.trade_tick_size)
            if point<=0:raise RuntimeError('Positive broker tick size required')
            offset=2+int(bool(at.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
            a=at-pd.Timedelta(seconds=61)+pd.Timedelta(hours=offset);b=at+pd.Timedelta(hours=offset)
            ticks=mt5.copy_ticks_range(symbol,a.to_pydatetime(),b.to_pydatetime(),mt5.COPY_TICKS_ALL)
            if ticks is None or not len(ticks):
                manifest['files'][key]=dict(status='MISSING',symbol=symbol,as_of=str(at));write(path,manifest)
                print('MISSING',i,symbol,str(at),flush=True);continue
            raw_hash=hashlib.sha256(ticks.tobytes()).hexdigest();raw=pd.DataFrame(ticks)
            f=pd.DataFrame(dict(time=pd.to_datetime(raw.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=offset),bid=raw.bid,ask=raw.ask,flags=raw['flags']))
            f=f[(f.time>=at-pd.Timedelta(seconds=61))&(f.time<=at)].reset_index(drop=True)
            tape=HERE/f'decision_{i:02d}.parquet';f.to_parquet(tape,index=False)
            manifest['files'][key]=dict(status='CAPTURED',symbol=symbol,as_of=str(at),path=tape.name,
                sha256=sha(tape),raw_numpy_sha256=raw_hash,rows=len(f),point=point,
                broker_clock_offset_hours=offset,clock_policy='Inherited same-broker US-DST UTC+2/3; per-window canonical M1 alignment required',
                captured_at=str(pd.Timestamp.now(tz='UTC')))
            write(path,manifest);print('CAPTURED',i,symbol,len(f),flush=True)
    finally:mt5.shutdown()


if __name__=='__main__':main()
