"""Diagnose original London ORB. Candidate funnel, not a return backtest."""
from pathlib import Path
import sys,json,hashlib
from datetime import datetime,timezone
from unittest.mock import patch
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT))
from sfp_orb_engine import config,orb_detector
from sfp_orb_engine.orb_detector import ORBDetector

SYMBOLS=['EUR/USD','GBP/USD','USD/JPY','USD/CAD','USD/CHF','NZD/USD']
MONTHS=['2025-01','2025-06','2025-11']
DATA=ROOT/'data/full_2025_study/prices_utc'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def clock_at(t):
    class Frozen(datetime):
        @classmethod
        def now(cls,tz=None):return t.to_pydatetime().astimezone(tz or timezone.utc)
    return Frozen

def geometry(df):
    """Mirror the exact original London range and compression gate only."""
    last=df.iloc[-1];day=df[df.datetime.dt.date==last.datetime.date()]
    minutes=day.datetime.dt.hour*60+day.datetime.dt.minute
    orb=day[(minutes>=420)&(minutes<=435)]
    asia=day[(minutes>=0)&(minutes<=360)]
    post=day[minutes>435]
    if orb.empty or post.empty:return None
    hi=float(orb.high.max());lo=float(orb.low.min())
    prior=float(post.iloc[-2].close if len(post)>1 else orb.iloc[-1].close)
    close=float(last.close)
    direction='LONG' if close>hi and prior<=hi else ('SHORT' if close<lo and prior>=lo else None)
    mean_range=float((df.high-df.low).tail(14).mean())
    ar=float(asia.high.max()-asia.low.min()) if len(asia) else None
    veto=len(asia)>=4 and mean_range>0 and ar>mean_range*.7
    return dict(direction=direction,orb_bars=len(orb),asia_bars=len(asia),asian_range=ar,
        mean_m15_range=mean_range,ratio_asia_to_m15=ar/mean_range if ar is not None and mean_range>0 else None,
        compression_veto=bool(veto))

def freeze():
    declaration=dict(symbols=SYMBOLS,months=MONTHS,scope='ORIGINAL_LONDON_DETECTOR_FUNNEL_NOT_PNL',
        method='300 completed M15 bars; exact fixed07:00-15:30UTC baseline; breakout defined using original inclusive07:00/07:15 range; no SFP/HTF/macro/news/execution gating yet',
        rationale='First establish if London detector generates usable candidates before claiming entry edge;6available majorFX;AUDUSD excluded by live config and absent in normalized dataset; no parameter optimization',
        alternatives='Only structural diagnostics: London08:00 local anchor, halfopen15minute interval; no optimized variant PnL',
        sources={str(ROOT/'sfp_orb_engine'/f'{s}.py'):sha(ROOT/'sfp_orb_engine'/f'{s}.py') for s in ['orb_detector','config','entry_mechanics','volume_anomaly']},
        inputs={str(DATA/f'{s.replace("/", "")}_15m.csv.gz'):sha(DATA/f'{s.replace("/", "")}_15m.csv.gz') for s in SYMBOLS},
        provenance_sha256=sha(DATA/'provenance.json'),code_sha256=sha(Path(__file__)),
        live_approved=False,not_oos=True)
    p=BASE/'protocol_frozen.json'
    if p.exists():
        if json.loads(p.read_text())['declaration']!=declaration:raise RuntimeError('Frozen sources changed')
    else:p.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=declaration),indent=2),encoding='utf8')

def run():
    freeze();rows=[];summary=[];candidates=[];detector=ORBDetector()
    for symbol in SYMBOLS:
        f=pd.read_csv(DATA/f'{symbol.replace("/", "")}_15m.csv.gz')
        f.datetime=pd.to_datetime(f.datetime,utc=True)
        if f.datetime.duplicated().any() or not f.datetime.is_monotonic_increasing:raise RuntimeError('Bad clock')
        for month in MONTHS:
            start=pd.Timestamp(month+'-01',tz='UTC');end=start+pd.offsets.MonthBegin(1)
            minutes=f.datetime.dt.hour*60+f.datetime.dt.minute
            selected=(f.datetime>=start)&(f.datetime<end)&(f.datetime.dt.dayofweek<5)&(minutes>435)&(minutes<=930)
            count=breaks=vetoes=outputs=0;ratios=[];full_days=set();observed_days=set()
            for i in np.flatnonzero(selected.to_numpy()):
                if i<299:continue
                df=f.iloc[i-299:i+1].reset_index(drop=True)
                g=geometry(df)
                if g is None:continue
                count+=1;vetoes+=g['compression_veto'];observed_days.add(str(df.iloc[-1].datetime.date()))
                if g['orb_bars']==2:full_days.add(str(df.iloc[-1].datetime.date()))
                if g['ratio_asia_to_m15'] is not None:ratios.append(g['ratio_asia_to_m15'])
                if not g['direction']:continue
                breaks+=1
                known=df.iloc[-1].datetime+pd.Timedelta(minutes=15)
                with patch.object(orb_detector,'datetime',clock_at(known)):
                    result=detector.detect_orb(df,symbol)
                # Compression is an absolute veto in exact detector, tested here.
                if g['compression_veto'] and result is not None and result.get('session_name')==config.ORB_SESSIONS['LONDON']['name']:
                    raise AssertionError('Compression mirror disagrees')
                if result is not None and result.get('session_name')==config.ORB_SESSIONS['LONDON']['name']:
                    outputs+=1;candidates.append(dict(available_at=str(known),signal=result))
                rows.append(dict(symbol=symbol,month=month,bar_open=str(df.iloc[-1].datetime),available_at=str(known),engine_session_open=config.is_session_active_for_scan(symbol,known.to_pydatetime()),morning_window=known.hour<12,**g,original_london_signal=bool(result and result.get('session_name')==config.ORB_SESSIONS['LONDON']['name'])))
            summary.append(dict(symbol=symbol,month=month,observed_days=len(observed_days),days_with_two_range_bars=len(full_days),windows=count,compression_veto_windows=vetoes,raw_close_crossings=breaks,london_detector_outputs=outputs,median_asia_to_m15=float(np.median(ratios)) if ratios else None))
            print(symbol,month,'windows',count,'crossings',breaks,'signals',outputs,flush=True)
    pd.DataFrame(rows).to_csv(BASE/'crossing_diagnostics.csv',index=False)
    pd.DataFrame(summary).to_csv(BASE/'funnel.csv',index=False)
    (BASE/'candidates.json').write_text(json.dumps(candidates,default=str,indent=2),encoding='utf8')
    anchors=[]
    for date in ['2025-01-15','2025-06-16','2025-11-17','2025-03-28','2025-10-27']:
        t=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC')
        anchors.append(dict(date=date,actual_london08_utc=str(t),fixed_code_utc=date+' 07:00Z'))
    (BASE/'session_anchors.json').write_text(json.dumps(anchors,indent=2),encoding='utf8')
    print('TOTAL',pd.DataFrame(summary)[['windows','compression_veto_windows','raw_close_crossings','london_detector_outputs']].sum().to_dict())

if __name__=='__main__':run()
