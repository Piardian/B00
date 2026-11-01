"""Read-only native-M15 consistency check for tick-derived opening features."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];sys.path.insert(0,str(ROOT))
from scripts.normalize_broker_history import broker_to_utc
from collect_mt5 import TERMINAL,SYMBOLS,schedule
from native_volume_audit import native_opening
def main():
    manifest=json.loads((BASE/'quote_manifest_frozen.json').read_text());rows=[];native=[]
    if not mt5.initialize(TERMINAL,timeout=10000):raise RuntimeError(str(mt5.last_error()))
    try:
        if mt5.account_info().server!='FivePercentOnline-Real':raise RuntimeError('Wrongbroker')
        for symbol in SYMBOLS:
            raw=mt5.copy_rates_range(symbol,mt5.TIMEFRAME_M15,pd.Timestamp('2025-01-13T00:00Z').to_pydatetime(),pd.Timestamp('2025-04-02T00:00Z').to_pydatetime())
            if raw is None:raise RuntimeError('Nativehistorymissing')
            f=pd.DataFrame(raw);f['time_utc']=broker_to_utc(pd.to_datetime(f.time,unit='s',utc=True));native.append(f.assign(symbol=symbol))
            point=manifest['symbol_specs'][symbol]['trade_tick_size']
            for date,warmup in schedule():
                tape=pd.read_parquet(manifest['files'][f'{symbol}_{date}']['path']);feat=native_opening(tape,date)
                target=f[f.time_utc==feat['start']]
                if len(target)!=1:raise RuntimeError('Missingnativebar'+symbol+date)
                b=target.iloc[0]
                rows.append(dict(symbol=symbol,date=date,volume_native=int(b.tick_volume),volume_tick=int(feat['volume']),
                    volume_exact=int(b.tick_volume)==feat['volume'],high_match=abs(float(b.high)-feat['high'])<=point+1e-12,
                    low_match=abs(float(b.low)-feat['low'])<=point+1e-12,
                    direction_match=int(np.sign(float(b.close-b.open)))==feat['direction']))
    finally:mt5.shutdown()
    pd.concat(native).to_parquet(BASE/'native_m15_reference.parquet',compression='zstd')
    df=pd.DataFrame(rows);df.to_csv(BASE/'native_bar_check.csv',index=False)
    result=dict(checked=len(df),exact_volume=int(df.volume_exact.sum()),matching_high=int(df.high_match.sum()),matching_low=int(df.low_match.sum()),matching_direction=int(df.direction_match.sum()),passed=bool(df[['volume_exact','high_match','low_match','direction_match']].all().all()))
    (BASE/'native_bar_qa.json').write_text(json.dumps(result,indent=2));print(result)
    if not result['passed']:raise SystemExit(1)
if __name__=='__main__':main()
