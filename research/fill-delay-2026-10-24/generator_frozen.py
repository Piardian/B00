"""Locked temporal validation of Asia compression on original early limit setup.

Same research lifecycle and cost model as discovery; never a full-bot claim.
"""
import argparse,hashlib,json,os
from pathlib import Path
import numpy as np
import pandas as pd
import math
from execution import replay
from price_rules import normalize_targets

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SYMBOLS=['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD']
MONTHS=['2025-02','2025-03'];SPREADS=[.2,.5,.9,1.5]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False,allow_nan=False,default=str),encoding='utf-8')


def classify_ratio(value):
    if not math.isfinite(value) or value<0 or value>.70+1e-12:raise ValueError('Invalid base-detector compression ratio')
    return 'TIGHT' if value<=.35 else 'LOOSE'


def freeze():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already frozen')
    old=json.loads((ROOT/'research/london-opening-only-2026-10-23/protocol_frozen.json').read_text())['declaration']['source_hashes']
    for name in ['config','orb_detector','orb_session_context','entry_mechanics','volume_anomaly']:
        if sha(HERE/'frozen_engine'/(name+'.py'))!=old[name]:raise RuntimeError('Detector differs from discovery: '+name)
    local=list(HERE.glob('*.py'))+list((HERE/'frozen_engine').glob('*.py'))
    write(HERE/'protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),symbols=SYMBOLS,months=MONTHS,
      scope='Additional temporal sample for <=.35 Asia/ATR hypothesis; Feb/Mar prices previously used by separate classic ORB research. Not pristine project-wide OOS, not prospective forward.',
      hypothesis='Same first normalized daily detector setup. Tight Asia<=.35 dailyATR versus loose(.35,.70]. Base detector cap.70 unchanged; threshold never tuned.',
      detector='Byte-identical frozen ORB/config/entry/volume/context from discovery. London08-08:15local,2xvolume,Asia00-06UTC,prior14validUTCdailyTR,entry availability before12local. First daily setup even if unfilled; no replacement after new compression filter.',
      lifecycle='Unmodified discovery execution.py: passive fixed entry/stop, outward target correction>=1.2/2R, halfTP1,BE/trail,fill-bar adverse reaction,stop-first,no fill-bar TP, London16:30 flat; noon/4h pending deadline.',
      costs='Same four assumed constant spreads .2/.5/.9/1.5pip; primary.5, adverse1.5; USD4/100k roundtrip,.2pip market exit slippage. New native broker bidM1 checked against tick bid samples. Not actual historic charges/ask replay.',
      coverage='All41weekdays x6symbols; no missing weekday or input silently treated no signal. Asia24M15+opening and every decision bar coverage required; ATR warmup available separately. Replay missingM1 unresolved; any unresolved forbids complete-basket claims.',
      primary='Mean netR per tight-group accepted setup including no-fill zeros; month signs and adverse costs; compare loose group under same schedule.',
      decision='Hypothesis survives screen only if tight group positive in both months at.5 and1.5pip with no coverage/replay unresolved and outperform loose mean at both costs. At least30closedtightfills required even to regard as a substantive follow-up candidate; this is a heuristic sample gate, not edge proof. No live promotion under any result.',
      uncertainty='10000 day-cluster resamples of accepted setup mean;95%percentiles. Exploratory validation after multiple earlier hypotheses, no multiplicity correction.',
      prohibited='No parameter/asset/month search, no macro imputation, no live orders or paid API.',
      forced_research_environment=dict(ENTRY_MODEL='MIDPOINT',LIMIT_EXPIRY_BARS='16'),
      code_hashes={str(p.relative_to(HERE)):sha(p) for p in local}))


def verify():
    plan=json.loads((HERE/'protocol_v2.json' if (HERE/'protocol_v2.json').exists() else HERE/'protocol.json').read_text(encoding='utf-8'))
    for name,h in plan['code_hashes'].items():
        if sha(HERE/name)!=h:raise RuntimeError('Frozen source changed:'+name)
    return plan


def stats(rows):
    closed=[r for r in rows if r['filled_at'] and r['status']=='CLOSED'];values=[r['net_r'] for r in closed]
    gains=sum(v for v in values if v>0);loss=-sum(v for v in values if v<0)
    unresolved=sum(r['status']!='CLOSED' for r in rows);ci=None
    days=sorted({r['day'] for r in rows})
    if len(days)>=5 and not unresolved:
        totals=np.array([sum(r['net_r'] for r in rows if r['day']==d) for d in days]);counts=np.array([sum(r['day']==d for r in rows) for d in days])
        pick=np.random.default_rng(20261024).integers(0,len(days),size=(10000,len(days)))
        ci=[float(x) for x in np.quantile(totals[pick].sum(axis=1)/counts[pick].sum(axis=1),[.025,.975])]
    return dict(setups=len(rows),fills=len(closed),unresolved=unresolved,net_r=sum(values) if not unresolved else None,
      closed_only_r=sum(values),pf=gains/loss if loss else None,mean_r_per_setup=sum(values)/len(rows) if rows and not unresolved else None,
      day_cluster95_mean_setup_r=ci,
      monthly={m:dict(setups=sum(r['month']==m for r in rows),fills=sum(r['month']==m for r in closed),closed_only_r=sum(r['net_r'] for r in closed if r['month']==m)) for m in MONTHS},
      reasons={reason:sum(r['reason']==reason for r in rows) for reason in sorted({r['reason'] for r in rows})})


def generate(frames):
    # Frozen imports cannot use a running production checkout or its .env.
    os.environ['ENTRY_MODEL']='MIDPOINT';os.environ['LIMIT_EXPIRY_BARS']='16'
    from frozen_engine.orb_detector import ORBDetector
    from frozen_engine.config import ORB_SESSIONS
    from frozen_engine.orb_session_context import london_bounds,prior_daily_atr
    detector=ORBDetector();candidates=[];coverage=[]
    for symbol in SYMBOLS:
        f=frames[symbol,'15m'];h=frames[symbol,'1h'];slash=symbol[:3]+'/'+symbol[3:]
        for month in MONTHS:
            for d in pd.bdate_range(month+'-01',pd.Timestamp(month+'-01')+pd.offsets.MonthEnd(0)):
                day=pd.Timestamp(str(d.date()),tz='UTC');start,orb_end,end=london_bounds(d.date(),ORB_SESSIONS['LONDON'],15)
                deadline=pd.Timestamp(f'{d.date()} 12:00',tz='Europe/London').tz_convert('UTC')
                required=pd.date_range(day,day+pd.Timedelta(hours=6),freq='15min',inclusive='left').append(pd.date_range(start,deadline,freq='15min',inclusive='left'))
                missing=required.difference(pd.DatetimeIndex(f.datetime))
                atr=prior_daily_atr(h,day)
                row=dict(symbol=symbol,day=str(d.date()),missing_m15=len(missing),atr_ready=atr is not None,raw_candidates=0)
                coverage.append(row)
                if len(missing) or atr is None:continue
                accepted=None
                for at in pd.date_range(orb_end+pd.Timedelta(minutes=15),deadline,freq='15min',inclusive='left'):
                    k=int(f.datetime.searchsorted(at,side='left'));df=f.iloc[max(0,k-300):k].reset_index(drop=True)
                    hk=int(h.datetime.searchsorted(at,side='left'));hourly=h.iloc[max(0,hk-1000):hk]
                    signal=detector.detect_orb(df,slash,hourly_history=hourly,as_of=at)
                    if signal is None:continue
                    row['raw_candidates']+=1
                    if accepted is not None:continue
                    corrected=normalize_targets(signal,.001 if symbol=='USDJPY' else .00001)
                    ratio=corrected['london_context']['asia_atr_ratio']
                    accepted=dict(symbol=symbol,day=str(d.date()),month=month,available_at=str(at),signal=corrected,ratio=ratio,group=classify_ratio(ratio))
                    candidates.append(accepted)
        print('SCAN',symbol,'selected',sum(c['symbol']==symbol for c in candidates),flush=True)
    return candidates,coverage


def run():
    verify();manifest=json.loads((HERE/'price_manifest.json').read_text())
    if not manifest.get('complete'):raise RuntimeError('Price collection incomplete')
    lock=HERE/'price_manifest_frozen.json'
    if lock.exists() and json.loads(lock.read_text())!=manifest:raise RuntimeError('Price manifest changed')
    if not lock.exists():write(lock,manifest)
    frames={}
    for key,m in manifest['files'].items():
        if sha(HERE/m['path'])!=m['sha256']:raise RuntimeError('Price hash mismatch')
        symbol,tf=key.split('_');frames[symbol,tf]=pd.read_parquet(HERE/m['path'])
    candidates,coverage=generate(frames);write(HERE/'candidates.json',candidates);write(HERE/'coverage.json',coverage)
    gaps=[r for r in coverage if r['missing_m15'] or not r['atr_ready']]
    if gaps:
        write(HERE/'status.json',dict(status='BLOCKED_INPUT_COVERAGE',affected_pair_days=len(gaps)));print('BLOCKED input pairdays',len(gaps));return
    outcomes=[]
    for i,c in enumerate(candidates):
        for sp in SPREADS:
            result=replay(c['signal'],c['available_at'],frames[c['symbol'],'1m'],'passive',spread_pips=sp)
            outcomes.append(dict(candidate_id=i,symbol=c['symbol'],day=c['day'],month=c['month'],group=c['group'],spread_pips=sp,**result))
    summaries=[dict(group=g,spread_pips=sp,**stats([r for r in outcomes if r['spread_pips']==sp and (g=='ALL' or r['group']==g)])) for sp in SPREADS for g in ['ALL','TIGHT','LOOSE']]
    write(HERE/'outcomes.json',outcomes);write(HERE/'summary.json',summaries)
    verify();write(HERE/'status.json',dict(status='REPLAY_COMPLETE' if not any(r['status']!='CLOSED' for r in outcomes) else 'REPLAY_UNRESOLVED',pair_days=len(coverage),candidates=len(candidates)))
    print(json.dumps([r for r in summaries if r['spread_pips'] in [.5,1.5]],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','verify']);a=p.parse_args()
    {'freeze':freeze,'run':run,'verify':verify}[a.action]()
