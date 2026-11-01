"""Versioned repair of one failed API read. No parameter/outcome-based selection."""
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import json,hashlib,shutil,time
import pandas as pd
import MetaTrader5 as mt5
import study

BASE=Path(__file__).resolve().parent
def main():
    declaration=study.freeze();manifest=study.read(BASE/'quote_manifest.json')
    missing=[date for date,m in manifest['files'].items() if m['status']=='MISSING_BROKER_QUOTES']
    assert missing==['2025-01-02'],'Only the already documented first-call API failure may be repaired'
    # Month already populated by the other January session reads. Refuse a new
    # cold-history request under the smaller retry storage gate.
    cache=Path('C:/Users/piard/AppData/Roaming/MetaQuotes/Terminal/10CE948A1DFC9A8C27E56E827008EBD4/bases/FivePercentOnline-Real/ticks/XAUUSD/202501.tkc')
    assert cache.exists() and cache.stat().st_size>0,'Missing warm month cache'
    attempt=BASE/'attempt_01_incomplete';assert not attempt.exists(),'Do not overwrite first-attempt evidence';attempt.mkdir()
    names=['protocol_frozen.json','quote_manifest.json','quote_manifest_frozen.json','outcomes.json','outcomes.csv','results.json','native_qa.json','integrity_check.json','report_diagnostics.json','SONUC.md','execution_status.json','replay.log','clock_qa.json']
    preserved={}
    for name in names:
        p=BASE/name
        if p.exists():shutil.copy2(p,attempt/name);preserved[name]=study.sha(p)
    protocol=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),reason='Initial Jan2 copy_ticks_range returned(-1,Terminal:Callfailed); all other dates collected. Repair missing data only; initial profitable partial outcomes already seen. No OOS claim.',
        dates=missing,maximum_retries=3,strategy_changed=False,cost_changed=False,first_attempt_sha256=preserved,
        repair_script_sha256=study.sha(Path(__file__)),study_script_sha256=study.sha(BASE/'study.py'),existing_warm_cache_bytes=cache.stat().st_size,
        no_orders=True,all_other_tapes_must_remain_identical=True)
    study.save(BASE/'repair_protocol_frozen.json',protocol)
    if not mt5.initialize(study.TERMINAL,timeout=10000):raise RuntimeError(str(mt5.last_error()))
    try:
        assert mt5.account_info().server=='FivePercentOnline-Real'
        date=missing[0];start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');end=start+pd.Timedelta(hours=8)
        offset=2+int(bool(start.to_pydatetime().astimezone(ZoneInfo('America/New_York')).dst()))
        raw=None;attempts=[]
        for i in range(3):
            raw=mt5.copy_ticks_range('XAUUSD',(start+pd.Timedelta(hours=offset)).to_pydatetime(),(end+pd.Timedelta(hours=offset,seconds=5)).to_pydatetime(),mt5.COPY_TICKS_ALL)
            attempts.append(dict(number=i+1,rows=0 if raw is None else len(raw),error=str(mt5.last_error())))
            if raw is not None and len(raw):break
            time.sleep(2)
        if raw is None or not len(raw):
            study.save(BASE/'repair_result.json',dict(repaired=False,attempts=attempts));raise RuntimeError('Quote recovery failed; keep incomplete coverage')
        r=pd.DataFrame(raw);f=pd.DataFrame(dict(time=pd.to_datetime(r.time_msc,unit='ms',utc=True)-pd.Timedelta(hours=offset),bid=r.bid,ask=r.ask,flags=r['flags']))
        f=f[(f.time>=start)&(f.time<=end+pd.Timedelta(seconds=5))].reset_index(drop=True)
        assert not f.empty and f.time.is_monotonic_increasing and ((f.bid>0)&(f.ask>=f.bid)).all()
        target=BASE/'tapes'/f'XAUUSD_{date}.parquet';assert not target.exists();temp=target.with_suffix('.partial')
        f.to_parquet(temp,compression='zstd',compression_level=9,use_dictionary=False,use_byte_stream_split=['bid','ask']);temp.replace(target)
        manifest['files'][date]=dict(date=date,status='AVAILABLE',path=str(target),sha256=study.sha(target),raw_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),rows=len(f),
            first=str(f.time.iloc[0]),last=str(f.time.iloc[-1]),offset_hours=offset,zero_spread_fraction=float((f.ask==f.bid).mean()),median_spread_usd=float((f.ask-f.bid).median()),max_gap_seconds=float(f.time.diff().dt.total_seconds().max()),repair_protocol='repair_protocol_frozen.json')
        before=study.read(attempt/'quote_manifest.json')
        for day,meta in before['files'].items():
            if day!=date:assert manifest['files'][day]==meta
        study.save(BASE/'quote_manifest.json',manifest)
        for p,digest in declaration['hashes'].items():assert study.sha(Path(p))==digest
        study.save(BASE/'repair_result.json',dict(repaired=True,date=date,rows=len(f),attempts=attempts,recovered_quote_sha256=study.sha(target),all_other_manifest_entries_unchanged=True,strategy_hash_unchanged=True))
        print('REPAIRED',date,len(f),flush=True)
    finally:mt5.shutdown()

if __name__=='__main__':main()
