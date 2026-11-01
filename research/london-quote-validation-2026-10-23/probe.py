"""Read-only broker history probe. No orders, login changes or cache removal."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
import pandas as pd
import MetaTrader5 as mt5
BASE=Path(__file__).resolve().parent
def main():
    result=dict(probed_utc=datetime.now(timezone.utc).isoformat(),free_disk_gb=shutil.disk_usage(BASE).free/1024**3)
    terminal='C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe'
    result['terminal_path']=terminal
    if not mt5.initialize(terminal,timeout=10000):
        result.update(status='MT5_UNAVAILABLE',error=str(mt5.last_error()))
    else:
        try:
            info=mt5.account_info();result['broker_server']=info.server if info else None
            spec=mt5.symbol_info('EURUSD')
            result['symbol_spec']={k:getattr(spec,k,None) for k in ['digits','point','trade_tick_size','trade_contract_size','currency_profit']}
            a=pd.Timestamp('2025-02-03 10:00Z');b=a+pd.Timedelta(minutes=30)
            raw=mt5.copy_ticks_range('EURUSD',a.to_pydatetime(),b.to_pydatetime(),mt5.COPY_TICKS_ALL)
            result['last_error']=str(mt5.last_error())
            if raw is None or not len(raw):result['status']='NO_QUOTE_HISTORY'
            else:
                f=pd.DataFrame(raw);f.to_parquet(BASE/'probe_raw_EURUSD.parquet')
                valid=(f.bid>0)&(f.ask>=f.bid)
                result.update(status='RAW_BID_ASK_AVAILABLE',rows=len(f),valid_quote_rows=int(valid.sum()),
                    raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),
                    first_native=str(pd.to_datetime(f.time_msc.iloc[0],unit='ms',utc=True)),
                    last_native=str(pd.to_datetime(f.time_msc.iloc[-1],unit='ms',utc=True)),
                    median_spread_price=float((f.ask-f.bid)[valid].median()))
        finally:mt5.shutdown()
    (BASE/'probe.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
