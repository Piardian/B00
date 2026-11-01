"""Re-fetch only two unknown entry windows; never alter frozen tapes/outcomes."""
from pathlib import Path
from zoneinfo import ZoneInfo
import sys,json,hashlib
import pandas as pd
import MetaTrader5 as mt5
import study

BASE=Path(__file__).resolve().parent
def main():
    rows=[r for r in study.read(BASE/'outcomes.json') if r['scenario']=='OBSERVED_QUOTES_1x' and r['outcome']['status']=='BLOCKED_ENTRY_COVERAGE']
    manifests={**study.read(study.PRIOR/'quote_manifest_frozen.json')['files'],**study.read(study.EXT/'quote_manifest_frozen.json')['files']}
    requests=[]
    for row in rows:
        p=Path(manifests[row['symbol']+'_'+row['date']]['path']);frame=pd.read_parquet(p);frame.time=pd.to_datetime(frame.time,utc=True);captured={}
        def trace(call,event,arg):
            if call.f_code is study.prepare.__code__ and event=='return':captured.update(call.f_locals)
            return trace
        sys.settrace(trace)
        try:plan=study.prepare(frame,row['date'])
        finally:sys.settrace(None)
        assert plan['status']=='BLOCKED_ENTRY_COVERAGE'
        available=captured['available'];next_quote=captured['times'][captured['candidates'][0]]
        requests.append((row,frame,available,next_quote))
    if not mt5.initialize('C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe',timeout=10000):raise RuntimeError(str(mt5.last_error()))
    output=[]
    try:
        assert mt5.account_info().server=='FivePercentOnline-Real'
        for row,frame,available,next_quote in requests:
            start=available-pd.Timedelta(seconds=30);end=available+pd.Timedelta(seconds=30)
            offset=2+int(bool(available.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
            raw=mt5.copy_ticks_range(row['symbol'],(start+pd.Timedelta(hours=offset)).to_pydatetime(),(end+pd.Timedelta(hours=offset)).to_pydatetime(),mt5.COPY_TICKS_ALL)
            if raw is None or not len(raw):raise RuntimeError('No verification quotes'+str(mt5.last_error()))
            n=pd.DataFrame(raw);fresh=pd.DataFrame(dict(time=pd.to_datetime(n.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=offset),bid=n.bid,ask=n.ask,flags=n['flags']))
            fresh=fresh[(fresh.time>=start)&(fresh.time<=end)].reset_index(drop=True)
            original=frame[(frame.time>=start)&(frame.time<=end)].reset_index(drop=True)
            same=len(fresh)==len(original) and all(fresh[k].equals(original[k]) for k in ['time','bid','ask','flags'])
            future=fresh[fresh.time>=available]
            output.append(dict(symbol=row['symbol'],date=row['date'],confirmation_available_at=str(available),stored_next_quote=str(next_quote),
                fresh_next_quote=str(future.time.iloc[0]) if len(future) else None,delay_seconds=float((future.time.iloc[0]-available).total_seconds()) if len(future) else None,
                fresh_quote_within_5seconds=bool(len(future) and future.time.iloc[0]<=available+pd.Timedelta(seconds=5)),
                frozen_window_rows=len(original),refetched_window_rows=len(fresh),refetch_exact_match=same,raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest()))
    finally:mt5.shutdown()
    study.save(BASE/'entry_coverage_verification.json',dict(read_only=True,server='FivePercentOnline-Real',script_sha256=study.sha(Path(__file__)),rows=output))
    print(json.dumps(output,indent=2))

if __name__=='__main__':main()
