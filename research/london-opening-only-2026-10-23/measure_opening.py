"""User-locked London noon deadline and one accepted attempt per pair/day."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib,logging
import pandas as pd
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(BASE.parent/'london-orb-pnl-2026-10-23'))
from measure import replay_one,stats,geometry_rejection
from scripts.replay_live_system import source_hashes
from sfp_orb_engine import config
from sfp_orb_engine.orb_detector import ORBDetector
from sfp_orb_engine.execution_policy import higher_timeframe_trend,orb_daily_key
DATA=ROOT/'data/full_2025_study/prices_utc';OLD=BASE.parent/'london-orb-fix-2026-10-23/candidates.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run():
    raw=json.loads(OLD.read_text());symbols=sorted({x['signal']['symbol'] for x in raw})
    declaration=dict(user_rule='London08:00-08:15range;newORBavailablebefore12:00Europe/London;oneacceptedlimitperpairperLondondateindependentofdirection;unfilledusesday;pendingexpiresat12;filledexittrackingcontinues',
        scope='setup-only R measurements with daily attempt cap;no macro/news/SFPpriority/sharedportfoliorisk;notfullbot',
        selection='firstgeometry-validcandidateeachpairday;secondarycohortfirstsession+HTFalignedvalidcandidateeachpairday;no hindsight or outcome-basedselection',
        costs='same paper1/1.5/2spread+fee policy;originalM1tracker;no brokerexecution certificate',
        rules_frozen_before_new_outcomes=True,sample='sameJanJunNov2025;notOOS;no cutoff optimization',
        source_hashes=source_hashes(),
        files={str(p):sha(p) for p in [Path(__file__),ROOT/'tests/test_london_opening_only.py',BASE.parent/'london-orb-pnl-2026-10-23/measure.py',ROOT/'scripts/historical_market_calendar.py',OLD]},
        inputs={str(DATA/f'{s.replace("/", "")}_{tf}.csv.gz'):sha(DATA/f'{s.replace("/", "")}_{tf}.csv.gz') for s in symbols for tf in ['1m','15m','1h']},live_approved=False)
    p=BASE/'protocol_frozen.json'
    if p.exists():raise RuntimeError('Already frozen; do not overwrite')
    p.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=declaration),indent=2),encoding='utf8')
    logging.getLogger('Begonya00.OutcomeTracker').setLevel(logging.ERROR)
    frames={}
    for s in symbols:
        for tf in ['1m','15m','1h']:
            f=pd.read_csv(DATA/f'{s.replace("/", "")}_{tf}.csv.gz');f.datetime=pd.to_datetime(f.datetime,utc=True)
            if f.datetime.duplicated().any() or not f.datetime.is_monotonic_increasing:raise RuntimeError('Bad dates')
            frames[s,tf]=f
    detector=ORBDetector();candidates=[];audit=[]
    for x in sorted(raw,key=lambda x:(x['available_at'],x['signal']['symbol'])):
        at=pd.Timestamp(x['available_at']);s=x['signal']['symbol'];f=frames[s,'15m'];h=frames[s,'1h']
        stop=int(f.datetime.searchsorted(at,side='left'));df=f.iloc[max(0,stop-300):stop]
        hs=int(h.datetime.searchsorted(at,side='right'));hourly=h.iloc[max(0,hs-1000):hs]
        signal=detector.detect_orb(df,s,hourly_history=hourly,as_of=at)
        if not signal:continue
        for k in ['entry','stop_loss','tp1','tp2']:
            assert signal[k]==x['signal'][k],(s,at,k)
        trend=higher_timeframe_trend(hourly,at);expected='BULLISH' if signal['direction']=='LONG' else 'BEARISH'
        candidates.append(dict(signal=signal,available_at=str(at),engine_session_open=x['engine_session_open'],htf_aligned=trend==expected,geometry_rejection=geometry_rejection(signal)))
    results={};outcomes=[]
    for cohort in ['OPENING_CORE','SESSION_HTF']:
        used=set();selected=[];geometry_rejects=cap_skips=cohort_skips=0
        for i,c in enumerate(candidates):
            if cohort=='SESSION_HTF' and not(c['engine_session_open'] and c['htf_aligned']):
                cohort_skips+=1;continue
            if c['geometry_rejection']:
                geometry_rejects+=1;continue
            sig=c['signal'];key=orb_daily_key(sig['symbol'],c['available_at'])
            if key in used:cap_skips+=1;continue
            used.add(key);selected.append((i,c))
        sample=[]
        for i,c in selected:
            for m in [1.,1.5,2.]:
                outcome=replay_one(c['signal'],c['available_at'],frames[c['signal']['symbol'],'1m'],m)
                sample.append(dict(cohort=cohort,candidate_id=i,available_at=c['available_at'],symbol=c['signal']['symbol'],multiplier=m,outcome=outcome))
        results[cohort]=dict(raw_window_candidates=len(candidates),geometry_rejects=geometry_rejects,daily_cap_skips=cap_skips,cohort_skips=cohort_skips,accepted_attempts=len(selected),costs={str(m):stats([r for r in sample if r['multiplier']==m],m) for m in [1.,1.5,2.]})
        base=[r for r in sample if r['multiplier']==1. and r['outcome']['status']=='CLOSED' and r['outcome']['trade'].get('filled_at')]
        results[cohort]['frozen_fill_fee_stress']={str(m):sum(r['outcome']['trade']['gross_r']-.08*m for r in base) for m in [1.,1.5,2.]}
        outcomes+=sample
        print(cohort,'attempts',len(selected),'net1.5',results[cohort]['costs']['1.5']['net_r'],flush=True)
    (BASE/'candidate_audit.json').write_text(json.dumps(candidates,default=str,indent=2),encoding='utf8')
    (BASE/'outcomes.json').write_text(json.dumps(outcomes,default=str,indent=2),encoding='utf8')
    (BASE/'results.json').write_text(json.dumps(results,default=str,indent=2),encoding='utf8')

if __name__=='__main__':run()
