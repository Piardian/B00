"""Three predeclared mechanics hypotheses; no live promotion or search grid."""
from pathlib import Path
from datetime import datetime,timezone
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
import json,hashlib,sys,copy,logging
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(BASE.parent/'london-orb-pnl-2026-10-23'))
sys.path.insert(0,str(BASE.parent/'net-expectancy-2026-10-23'))
from measure import replay_one,stats,geometry_rejection
from price_rules import normalize_targets
from scripts.replay_live_system import Clock,NullNotifier,source_hashes
from scripts.historical_market_calendar import broker_market_is_open
from sfp_orb_engine import config,outcome_tracker as tracker
from sfp_orb_engine.execution_policy import orb_daily_key
OLD=BASE.parent/'london-opening-only-2026-10-23/candidate_audit.json'
DATA=ROOT/'data/full_2025_study/prices_utc'
VARIANTS=['ROUNDING_REFERENCE','NO_REACTION_EXIT','M1_BREAK_CONFIRMATION']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def step(symbol):return .001 if symbol.endswith('/JPY') else .00001
def targets(signal):return normalize_targets(signal,step(signal['symbol']))

def confirmation(signal,at,m1,multiplier):
    """Retest, then a LATER M1 close breaks preceding completed M1 extreme.

    Execution is the next M1 open. No claim to reconstruct human swing choice.
    """
    at=pd.Timestamp(at);deadline=pd.Timestamp(signal['entry_deadline_utc'])
    start=int(m1.datetime.searchsorted(at,side='left'));stop=int(m1.datetime.searchsorted(deadline,side='left'))
    touch=None;long=signal['direction']=='LONG';sl=signal['stop_loss'];entry=signal['entry']
    spread=entry*tracker.get_friction_config(signal['symbol'])['spread_ratio']*multiplier
    previous_time=None
    for i in range(start,stop):
        b=m1.iloc[i];known=b.datetime+pd.Timedelta(minutes=1)
        expected=at if previous_time is None else previous_time+pd.Timedelta(minutes=1)
        while expected<b.datetime and not broker_market_is_open(signal['symbol'],expected):expected+=pd.Timedelta(minutes=1)
        if expected<b.datetime:return dict(status='UNRESOLVED_PREENTRY_GAP')
        previous_time=b.datetime
        if known>=deadline:break
        if b.low<=sl if long else b.high>=sl:return dict(status='INVALIDATED_BEFORE_ENTRY')
        if touch is None:
            if b.low<=entry-spread if long else b.high>=entry+spread:touch=i
            continue
        prev=m1.iloc[i-1]
        if b.datetime-prev.datetime!=pd.Timedelta(minutes=1):return dict(status='UNRESOLVED_PREENTRY_GAP')
        broke=b.close>prev.high if long else b.close<prev.low
        if not broke:continue
        if i+1>=len(m1):return dict(status='UNRESOLVED_PREENTRY_GAP')
        nxt=m1.iloc[i+1]
        if nxt.datetime!=known:return dict(status='UNRESOLVED_PREENTRY_GAP')
        price=float(nxt.open)
        if not(sl<price if long else sl>price):return dict(status='INVALID_ENTRY_GEOMETRY')
        revised=copy.deepcopy(signal);revised['entry']=price
        risk=abs(price-sl);sign=1 if long else -1
        revised['tp1']=price+sign*1.2*risk;revised['tp2']=price+sign*2*risk
        revised['risk_pips']=risk;revised=targets(revised)
        return dict(status='CONFIRMED',signal=revised,entry_at=known,confirmation_bar=str(b.datetime))
    return dict(status='NO_CONFIRMATION_BEFORE_CUTOFF')

def market_replay(signal,at,m1,multiplier):
    """Only entry transport differs; original OPEN-position tracker exits."""
    at=pd.Timestamp(at);clock=Clock(at);cost=tracker.get_friction_config(signal['symbol'])
    with ExitStack() as stack:
        stack.enter_context(patch.object(tracker,'datetime',clock.datetime_type()))
        stack.enter_context(patch.object(tracker,'time',SimpleNamespace(time=lambda:clock.current.timestamp())))
        stack.enter_context(patch.object(tracker,'get_friction_config',lambda s:{k:v*multiplier for k,v in cost.items()}))
        stack.enter_context(patch.object(tracker,'is_market_open',broker_market_is_open))
        stack.enter_context(patch.object(tracker.OutcomeTracker,'_load_json',lambda *a:[]))
        stack.enter_context(patch.object(tracker.OutcomeTracker,'_save_json',lambda *a:None))
        stack.enter_context(patch.object(tracker.OutcomeTracker,'_notify_lifecycle',lambda *a:None))
        obj=tracker.OutcomeTracker(notifier=NullNotifier());obj.register_trade(signal)
        obj.active_trades[0].update(status='OPEN',filled_at=at.isoformat(),fill_model='NEXT_M1_OPEN_AFTER_LATER_BAR_CONFIRMATION')
        end=at.floor('D').replace(day=1)+pd.offsets.MonthBegin(1)
        start=int(m1.datetime.searchsorted(at));stop=int(m1.datetime.searchsorted(end))
        for b in m1.iloc[start:stop].to_dict('records'):
            clock.current=(b['datetime']+pd.Timedelta(minutes=1)).to_pydatetime()
            obj.check_trade_progress(signal['symbol'],b)
            if obj.closed_trades:return dict(status='CLOSED',trade=obj.closed_trades[0])
            if obj.active_trades[0].get('tracking_gap_at'):return dict(status='UNRESOLVED_M1_GAP',trade=obj.active_trades[0])
        return dict(status='OPEN_AT_MONTH_END',trade=obj.active_trades[0])

def freeze(candidates):
    files=[Path(__file__),BASE/'test_experiment.py',OLD,BASE.parent/'london-orb-pnl-2026-10-23/measure.py',BASE.parent/'net-expectancy-2026-10-23/price_rules.py',ROOT/'scripts/historical_market_calendar.py']
    files += [ROOT/'sfp_orb_engine'/f'{name}.py' for name in source_hashes()]
    symbols=sorted({x['signal']['symbol'] for x in candidates})
    declaration=dict(variants=VARIANTS,
        method='firstgeometry-validcandidatepairday;entrycutoff12London;all6pairsJanJunNov2025;same36candidates;targetsoutward1e-5FX/1e-3JPY;nohandpickedwinners',
        m1='afterretesttouch,latercompletedM1closebreakspreviouscompletedM1high/low;nextM1open;retainsoriginalSL,recompute1.2/2Rtargets;structuralstopbrokenbeforeentryinvalidatescausally;notuserhuman-swingreplication',
        ablation='referencecorrectsroundedRRonly;noReactionchangesonlyREQUIRE_ENTRY_REACTIONFalse;M1variantchangesentry,notexittracker',
        costs='originalpaper1/1.5/2spread+fee;marketvariantspreadtargetbufferandfixedfee,notbidaskexecution;noorderfillsproved',
        infer='allthreehypothesesdisclosed,observedexploratorydata,notOOS,noautomatedpromotion;blockbootstrapnotfullselectioncorrection',
        stage_gate='noedgeclaimwithoutnetpositive1.5and2costs,positiveall3months,atleast100fillsinnewdataanduncertaintylower>0;currentdataonlydiagnosis',
        files={str(p):sha(p) for p in files},inputs={str(DATA/f'{s.replace("/", "")}_1m.csv.gz'):sha(DATA/f'{s.replace("/", "")}_1m.csv.gz') for s in symbols},live_approved=False)
    p=BASE/'protocol_frozen.json'
    if p.exists():raise RuntimeError('Do not overwrite frozen experiment')
    p.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=declaration),indent=2),encoding='utf8')
    for i,file in enumerate(files):(BASE/'frozen_sources'/f'{i:02}_{file.name}').write_bytes(file.read_bytes())

def run():
    candidates=json.loads(OLD.read_text());freeze(candidates)
    logging.getLogger('Begonya00.OutcomeTracker').setLevel(logging.ERROR)
    frames={}
    for s in sorted({x['signal']['symbol'] for x in candidates}):
        f=pd.read_csv(DATA/f'{s.replace("/", "")}_1m.csv.gz');f.datetime=pd.to_datetime(f.datetime,utc=True);frames[s]=f
    results={};out=[]
    for variant in VARIANTS:
        used=set();selected=[]
        for i,x in enumerate(sorted(candidates,key=lambda x:(x['available_at'],x['signal']['symbol']))):
            s=targets(x['signal'])
            if geometry_rejection(s):raise RuntimeError('Outward target normalization failed')
            key=orb_daily_key(s['symbol'],x['available_at'])
            if key in used:continue
            used.add(key);selected.append((i,x,s))
        sample=[];unfilled={};confirm_log=[]
        for m in [1.,1.5,2.]:
            unfilled[str(m)]={}
            for i,x,s in selected:
                at=x['available_at'];f=frames[s['symbol']]
                if variant=='M1_BREAK_CONFIRMATION':
                    conf=confirmation(s,at,f,m);confirm_log.append(dict(candidate_id=i,multiplier=m,**conf))
                    if conf['status']!='CONFIRMED':
                        unfilled[str(m)][conf['status']]=unfilled[str(m)].get(conf['status'],0)+1
                        continue
                    outcome=market_replay(conf['signal'],conf['entry_at'],f,m)
                else:
                    with patch.object(config,'REQUIRE_ENTRY_REACTION',variant!='NO_REACTION_EXIT'):
                        outcome=replay_one(s,at,f,m)
                sample.append(dict(variant=variant,candidate_id=i,available_at=at,symbol=s['symbol'],multiplier=m,outcome=outcome))
            print(variant,m,'processed',len([r for r in sample if r['multiplier']==m]),flush=True)
        results[variant]=dict(accepted_attempts=len(selected),costs={str(m):stats([r for r in sample if r['multiplier']==m],m) for m in [1.,1.5,2.]},preentry_outcomes=unfilled)
        out+=sample
        if confirm_log:(BASE/'confirmation_audit.json').write_text(json.dumps(confirm_log,default=str,indent=2),encoding='utf8')
    # A file change invalidates comparison, regardless of whether the result looks good.
    p=json.loads((BASE/'protocol_frozen.json').read_text())['declaration']
    for path,digest in p['files'].items():
        if sha(Path(path))!=digest:raise RuntimeError('Source changed during run: '+path)
    (BASE/'results.json').write_text(json.dumps(results,default=str,indent=2),encoding='utf8')
    (BASE/'outcomes.json').write_text(json.dumps(out,default=str,indent=2),encoding='utf8')

if __name__=='__main__':run()
