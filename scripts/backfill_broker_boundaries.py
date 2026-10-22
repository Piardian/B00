"""Fill real UTC month-end quotes omitted by the broker wall-clock boundary."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import time
import shutil
import sys
import pandas as pd
import MetaTrader5 as mt5

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sfp_orb_engine.config import ACTIVE_SYMBOLS,is_crypto,EXCLUDED_SFP_SYMBOLS
from scripts.prepare_2025_prices import save_frame,COLS


def main():
    root=ROOT/'data/full_2025_study/prices'
    mt5.initialize()
    base=(Path(mt5.terminal_info().data_path)/'bases'/mt5.account_info().server/'ticks').resolve()
    audit=[]
    marker=root/'utc_boundary_manifest.json'
    done=json.loads(marker.read_text()) if marker.exists() else []
    def release(clean):
        directory=(base/clean).resolve()
        if directory.parent!=base:raise RuntimeError('Unverified cache directory')
        if not all((root/f'{clean}_{tf}.csv.gz').exists() for tf in ('1m','15m','1h')):return
        for path in directory.glob('*.tkc'):
            if path.stat().st_ctime<dt.datetime(2026,10,22,19).timestamp() or not path.stem.isdigit() or path.stem>='202610':continue
            resolved=path.resolve()
            if resolved.parent!=directory or not resolved.is_relative_to(base):raise RuntimeError('Cache escaped verified symbol directory')
            record={'path':str(resolved),'bytes':path.stat().st_size}
            try:path.unlink();record['status']='REMOVED_TASK_GENERATED_CACHE'
            except PermissionError:record['status']='PRESERVED_TERMINAL_LOCK'
            audit.append(record)
        (root/'boundary_cache_cleanup.json').write_text(json.dumps(audit,indent=2))
    symbols=[s for s in ACTIVE_SYMBOLS if not is_crypto(s) and s not in EXCLUDED_SFP_SYMBOLS and s not in {'QQQ','SPY','NAS100'}]
    for symbol in symbols:release(symbol.replace('/',''))
    for symbol in symbols:
        clean=symbol.replace('/','');mt5.symbol_select(clean,True)
        for month,end,offset in [('2025-06','2025-07-01',3),('2025-11','2025-12-01',2)]:
            if any(r['symbol']==symbol and r['month']==month for r in done):continue
            release(clean)
            required=1500*1024**2 if clean!='XAUUSD' else 2000*1024**2
            if shutil.disk_usage(root).free<required:raise RuntimeError('Insufficient symbol-specific disk headroom before native terminal cache downloads: '+clean)
            start=pd.Timestamp(end,tz='UTC');stop=start+pd.Timedelta(hours=offset)
            ticks=mt5.copy_ticks_range(clean,start.to_pydatetime(),stop.to_pydatetime(),mt5.COPY_TICKS_ALL)
            if ticks is None:
                time.sleep(2);ticks=mt5.copy_ticks_range(clean,start.to_pydatetime(),stop.to_pydatetime(),mt5.COPY_TICKS_ALL)
            if ticks is None:raise RuntimeError(f'No verified boundary ticks: {symbol} {month}')
            record={'symbol':symbol,'month':month,'native_start':start.isoformat(),'native_end_exclusive':stop.isoformat(),'raw_sha256':hashlib.sha256(ticks.tobytes()).hexdigest()}
            groups={}
            if len(ticks):
                df=pd.DataFrame(ticks);df['datetime']=pd.to_datetime(df.time_msc,unit='ms',utc=True)
                df=df[(df.datetime>=start)&(df.datetime<stop)&(df.bid>0)]
                quotes=df.set_index('datetime').bid
                bars=quotes.resample('1min').ohlc();bars['volume']=quotes.resample('1min').count()
                groups['1m']=bars.dropna().reset_index();record['minutes']=len(groups['1m'])
            else:record['minutes']=0
            for tf,native in [('15m',mt5.TIMEFRAME_M15),('1h',mt5.TIMEFRAME_H1)]:
                rates=mt5.copy_rates_range(clean,native,start.to_pydatetime(),stop.to_pydatetime())
                if rates is not None and len(rates):
                    frame=pd.DataFrame(rates);frame['datetime']=pd.to_datetime(frame.time,unit='s',utc=True)
                    frame=frame[(frame.datetime>=start)&(frame.datetime<stop)]
                    frame['volume']=frame.tick_volume;groups[tf]=frame[COLS]
            for tf,extra in groups.items():
                if extra.empty:continue
                path=root/f'{clean}_{tf}.csv.gz';old=pd.read_csv(path);old.datetime=pd.to_datetime(old.datetime,utc=True)
                save_frame(path,[old,extra])
            done.append(record);marker.write_text(json.dumps(done,indent=2));release(clean)
            print('UTC_BOUNDARY_COMPLETED',symbol,month,record['minutes'],flush=True)


if __name__=='__main__':main()
