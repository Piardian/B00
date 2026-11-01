"""Read-only FivePercent tick collector, explicit terminal, no order methods."""
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import json,hashlib,shutil,argparse
import pandas as pd
import MetaTrader5 as mt5
BASE=Path(__file__).resolve().parent
TERMINAL='C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe'
SYMBOLS=['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD']
MONTHS=['2025-02','2025-03']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def schedule():
    first=pd.Timestamp('2025-02-01')
    warmup=pd.bdate_range(end=first-pd.Timedelta(days=1),periods=14)
    rows=[(str(d.date()),True) for d in warmup]
    for month in MONTHS:
        rows += [(str(d.date()),False) for d in pd.bdate_range(month+'-01',pd.Timestamp(month+'-01')+pd.offsets.MonthEnd(0))]
    return rows

def collect():
    manifest_path=BASE/'quote_manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else dict(provider='The5ers',terminal=TERMINAL,files={},complete=False)
    if not mt5.initialize(TERMINAL,timeout=10000):raise RuntimeError('The5ers connection failed: '+str(mt5.last_error()))
    out=BASE/'tapes';out.mkdir(exist_ok=True)
    try:
        account=mt5.account_info()
        if account is None or account.server!='FivePercentOnline-Real':raise RuntimeError('Unexpected server; no alternate account used')
        manifest['broker_server']=account.server
        for symbol in SYMBOLS:
            spec=mt5.symbol_info(symbol)
            if spec is None:raise RuntimeError('Symbol unavailable: '+symbol)
            manifest.setdefault('symbol_specs',{})[symbol]={k:getattr(spec,k,None) for k in ['digits','trade_tick_size','trade_contract_size','currency_profit']}
            for date,warmup in schedule():
                key=f'{symbol}_{date}';path=out/f'{key}.parquet'
                if key in manifest['files']:
                    if not path.exists() or sha(path)!=manifest['files'][key]['sha256']:raise RuntimeError('Stored tape changed '+key)
                    continue
                if shutil.disk_usage(BASE).free<1.5*1024**3:raise RuntimeError('Disk headroom below1.5GiB; preserve data and stop')
                start=pd.Timestamp(f'{date} 08:00',tz='Europe/London').tz_convert('UTC')
                end=start+pd.Timedelta(minutes=15) if warmup else pd.Timestamp(f'{date} 16:00',tz='Europe/London').tz_convert('UTC')+pd.Timedelta(seconds=5)
                offset=2+int(bool(start.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
                a=start+pd.Timedelta(hours=offset);b=end+pd.Timedelta(hours=offset)
                ticks=mt5.copy_ticks_range(symbol,a.to_pydatetime(),b.to_pydatetime(),mt5.COPY_TICKS_ALL)
                if ticks is None or not len(ticks):raise RuntimeError('Missing real tick history '+key+' '+str(mt5.last_error()))
                raw_hash=hashlib.sha256(ticks.tobytes()).hexdigest();f=pd.DataFrame(ticks)
                time=pd.to_datetime(f.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=offset)
                f=pd.DataFrame(dict(time=time,bid=f.bid,ask=f.ask,flags=f['flags']))
                f=f[(f.time>=start)&(f.time<=end)].reset_index(drop=True)
                if f.empty or not f.time.is_monotonic_increasing or not ((f.bid>0)&(f.ask>=f.bid)).all():raise RuntimeError('Invalid quotes '+key)
                tmp=path.with_suffix('.partial');f.to_parquet(tmp,compression='zstd',use_dictionary=False);tmp.replace(path)
                spread=f.ask-f.bid
                manifest['files'][key]=dict(path=str(path),sha256=sha(path),raw_numpy_sha256=raw_hash,
                    rows=len(f),warmup=warmup,date=date,symbol=symbol,first=str(f.time.iloc[0]),last=str(f.time.iloc[-1]),
                    broker_clock_offset_hours=offset,clock_policy='Verified same-broker US-DST UTC+2/3, fixed per weekday session',
                    zero_spread_fraction=float((spread==0).mean()),median_spread_price=float(spread.median()),max_gap_seconds=float(f.time.diff().dt.total_seconds().max()))
                manifest['captured_utc']=datetime.now(timezone.utc).isoformat()
                manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf8')
                if not warmup:print('TAPE',key,'ticks',len(f),'freeGiB',round(shutil.disk_usage(BASE).free/1024**3,2),flush=True)
        manifest['complete']=True;manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf8')
    finally:mt5.shutdown()

if __name__=='__main__':collect()
