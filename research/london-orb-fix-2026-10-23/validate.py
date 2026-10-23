"""Fixed London revision, original six pairs/three months, candidate counts only."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT))
from sfp_orb_engine import config
from sfp_orb_engine.orb_detector import ORBDetector
from sfp_orb_engine.orb_session_context import london_bounds,prior_daily_atr
SYMBOLS=['EUR/USD','GBP/USD','USD/JPY','USD/CAD','USD/CHF','NZD/USD']
MONTHS=['2025-01','2025-06','2025-11'];DATA=ROOT/'data/full_2025_study/prices_utc'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def freeze():
    source=[ROOT/'sfp_orb_engine'/f'{s}.py' for s in ['orb_detector','orb_session_context','config','engine','entry_mechanics','volume_anomaly']]
    source += [ROOT/'scripts'/s for s in ['prepass_2025_candidates.py','replay_live_system.py']]
    source += [ROOT/'tests/test_london_orb_context.py',Path(__file__)]
    declaration=dict(symbols=SYMBOLS,months=MONTHS,
        parameters='London08:00-16:30local;halfopenfirst15min;Asia00:00-06:00UTC;max70%ofSMA14completedUTCdailyTRfromH1;daily>=20H1bars;15validdaysneeded;minvolume2xhardveto',
        status='Daily ATR normalization is an explicit new hypothesis, not guaranteed bugfix alpha; no parameter search; candidate counts only,not PnL/fullengine',
        sample='Same previously examined three months,NOT OOS; repeat scans not independent trades',
        sources={str(p):sha(p) for p in source},
        before={str(p):sha(p) for p in (BASE/'before').glob('*.py')},
        inputs={str(DATA/f'{s.replace("/", "")}_{tf}.csv.gz'):sha(DATA/f'{s.replace("/", "")}_{tf}.csv.gz') for s in SYMBOLS for tf in ['15m','1h']},live_approved=False)
    p=BASE/'protocol_frozen.json'
    if p.exists():
        if json.loads(p.read_text())['declaration']!=declaration:raise RuntimeError('Frozen revision changed')
    else:p.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=declaration),indent=2),encoding='utf8')

def run():
    freeze();records=[];signals=[];detector=ORBDetector()
    for symbol in SYMBOLS:
        clean=symbol.replace('/','');f=pd.read_csv(DATA/f'{clean}_15m.csv.gz');h=pd.read_csv(DATA/f'{clean}_1h.csv.gz')
        for frame in [f,h]:
            frame.datetime=pd.to_datetime(frame.datetime,utc=True)
            if frame.datetime.duplicated().any() or not frame.datetime.is_monotonic_increasing:raise RuntimeError('Bad time')
        for month in MONTHS:
            start=pd.Timestamp(month+'-01',tz='UTC');end=start+pd.offsets.MonthBegin(1)
            count=raw=outputs=0;atr_ready_days=set();observed=set();morning=0;cache={}
            ix=np.flatnonzero(((f.datetime>=start)&(f.datetime<end)&(f.datetime.dt.dayofweek<5)).to_numpy())
            for i in ix:
                last=f.iloc[i];known=last.datetime+pd.Timedelta(minutes=15)
                date=last.datetime.date();opening,orb_end,session_end=london_bounds(date,config.ORB_SESSIONS['LONDON'],15)
                if not orb_end<=last.datetime<session_end or i<299:continue
                count+=1;observed.add(str(date));df=f.iloc[i-299:i+1].reset_index(drop=True)
                hk=int(h.datetime.searchsorted(known,side='left'));hourly=h.iloc[max(0,hk-1000):hk]
                if date not in cache:cache[date]=prior_daily_atr(hourly,last.datetime.floor('D'))
                if cache[date] is not None:atr_ready_days.add(str(date))
                orb=df[(df.datetime>=opening)&(df.datetime<orb_end)]
                if len(orb)!=1:continue
                prev=df.iloc[-2]
                hi=float(orb.high.max());lo=float(orb.low.min())
                if not ((last.close>hi and prev.close<=hi) or (last.close<lo and prev.close>=lo)):continue
                raw+=1
                signal=detector.detect_orb(df,symbol,hourly_history=hourly,as_of=known)
                if signal and 'london_context' in signal:
                    outputs+=1;morning+=known.hour<12
                    signals.append(dict(available_at=str(known),engine_session_open=config.is_session_active_for_scan(symbol,known.to_pydatetime()),signal=signal))
            records.append(dict(symbol=symbol,month=month,windows=count,observed_days=len(observed),atr_ready_days=len(atr_ready_days),raw_close_crossings=raw,detector_outputs=outputs,morning_outputs=morning))
            print(symbol,month,'crossings',raw,'signals',outputs,flush=True)
    pd.DataFrame(records).to_csv(BASE/'funnel.csv',index=False)
    (BASE/'candidates.json').write_text(json.dumps(signals,default=str,indent=2),encoding='utf8')
    print('TOTAL',pd.DataFrame(records)[['windows','raw_close_crossings','detector_outputs','morning_outputs']].sum().to_dict())

if __name__=='__main__':run()
