"""Independent London opportunities replayed through the original M1 tracker.

Not full-engine/macro performance or an executable portfolio. No network IO.
"""
from pathlib import Path
from datetime import datetime,timezone
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
import sys,json,hashlib,copy,logging
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT))
from sfp_orb_engine import config,outcome_tracker as tracker,execution_policy as policy
from scripts.historical_market_calendar import broker_market_is_open
from scripts.replay_live_system import Clock,NullNotifier,source_hashes
FIX=BASE.parent/'london-orb-fix-2026-10-23';DATA=ROOT/'data/full_2025_study/prices_utc'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def freeze():
    candidates=json.loads((FIX/'candidates.json').read_text())
    symbols=sorted({x['signal']['symbol'] for x in candidates})
    paths=[Path(__file__),BASE/'test_measure.py',ROOT/'scripts/historical_market_calendar.py']
    declaration=dict(scope='INDEPENDENT_OPPORTUNITIES_ORIGINAL_TRACKER_NOT_PORTFOLIO_OR_FULL_BOT',
        candidates_sha256=sha(FIX/'candidates.json'),candidate_source_protocol=sha(FIX/'protocol_frozen.json'),
        rules='All102 original fixed-detector candidates disclosed;check actual roundedlevelgeometry;each starts separate emptytracker withunitrisk;no macro,news,SFP priority,cooldown or sharedrisk simulation;not humanM1break policy',
        cohorts=['ALL_LONDON','MORNING_UTC_BEFORE12','SESSION_AND_HTF_ALIGNED'],
        friction='Original paper config spread_ratio0.0002 andfee0.08R;1/1.5/2x policy stress changesfills;also frozen1xclosedfills extrafee stress;not historical broker bidask/commissions',
        lifecycle='Original passive-limit-v3 M1 tracker;fillbarstopsfirst/noTPcredit;partialTP1,BE,trailing unchanged;allow overnight as productiondoes;swap absent;monthendsnotforcedclosed;missingminutehaltsunknownoutcome',
        uncertainty='5observedday circularblockbootstrap10000seed173 on daily netR over63weekdaycalendar;conditional selectedsample,notmultipletrialadjusted;incompleteoutcomesnotzero',
        files={str(p):sha(p) for p in paths},source_hashes=source_hashes(),
        inputs={str(DATA/f'{s.replace("/", "")}_{tf}.csv.gz'):sha(DATA/f'{s.replace("/", "")}_{tf}.csv.gz') for s in symbols for tf in ['1m','1h']},
        live_approved=False,unseen_oos=False)
    p=BASE/'protocol_frozen.json'
    if p.exists():
        if json.loads(p.read_text())['declaration']!=declaration:raise RuntimeError('Frozen inputs changed')
    else:p.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=declaration),indent=2),encoding='utf8')
    return candidates

def geometry_rejection(signal):
    # The pure-setup test explicitly excludes HTF. Real price/RR checks remain.
    with patch.object(config,'REQUIRE_PRO_TREND_AAA',False):return policy.validate_signal(signal)

def replay_one(signal,available_at,m1,multiplier=1.):
    at=pd.Timestamp(available_at);end=at.floor('D').replace(day=1)+pd.offsets.MonthBegin(1)
    clock=Clock(at);friction=tracker.get_friction_config(signal['symbol'])
    original_save=tracker.OutcomeTracker._save_json
    gap_crosses=0
    with ExitStack() as stack:
        stack.enter_context(patch.object(tracker,'datetime',clock.datetime_type()))
        stack.enter_context(patch.object(tracker,'time',SimpleNamespace(time=lambda:clock.current.timestamp())))
        stack.enter_context(patch.object(tracker,'get_friction_config',lambda s:{k:v*multiplier for k,v in friction.items()}))
        stack.enter_context(patch.object(tracker,'is_market_open',broker_market_is_open))
        # Disk and notification methods are transport only. Trade logic is intact.
        stack.enter_context(patch.object(tracker.OutcomeTracker,'_load_json',lambda *a:[]))
        stack.enter_context(patch.object(tracker.OutcomeTracker,'_save_json',lambda *a:None))
        stack.enter_context(patch.object(tracker.OutcomeTracker,'_notify_lifecycle',lambda *a:None))
        obj=tracker.OutcomeTracker(notifier=NullNotifier())
        obj.register_trade(copy.deepcopy(signal))
        start=int(m1.datetime.searchsorted(at,side='left'));stop=int(m1.datetime.searchsorted(end,side='left'))
        for b in m1.iloc[start:stop].to_dict('records'):
            clock.current=(b['datetime']+pd.Timedelta(minutes=1)).to_pydatetime()
            t=obj.active_trades[0]
            if t['status']!='PENDING_LIMIT':
                sl=t['current_sl'];gap_crosses+=int(b['open']<sl if t['direction']=='LONG' else b['open']>sl)
            obj.check_trade_progress(signal['symbol'],b)
            if obj.closed_trades:
                t=obj.closed_trades[0]
                t['gap_open_beyond_active_stop_bars']=gap_crosses
                return dict(status='CLOSED',trade=t)
            if obj.active_trades[0].get('tracking_gap_at'):
                return dict(status='UNRESOLVED_M1_GAP',trade=obj.active_trades[0])
        t=obj.active_trades[0]
        # Month-end missing open-market data remains unknown, never a flat close.
        expected=policy.utc_time(t.get('last_processed_bar') or t['opened_at'])
        if t.get('last_processed_bar'):expected+=pd.Timedelta(minutes=1)
        while expected<end and not broker_market_is_open(signal['symbol'],expected):expected+=pd.Timedelta(minutes=1)
        if expected<end:t['unpriced_tail_from']=str(expected)
        return dict(status='OPEN_AT_MONTH_END',trade=t)
    assert tracker.OutcomeTracker._save_json is original_save

def stats(rows,multiplier):
    closed=[r for r in rows if r['outcome']['status']=='CLOSED']
    filled=[r for r in closed if r['outcome']['trade']['close_reason'] not in policy.NO_FILL_REASONS]
    r=np.array([x['outcome']['trade']['net_r'] for x in filled],dtype=float)
    curve=np.r_[0,np.cumsum(r)];loss=-r[r<0].sum()
    days=pd.DatetimeIndex([d for month in ['2025-01','2025-06','2025-11'] for d in pd.bdate_range(month+'-01',pd.Timestamp(month+'-01')+pd.offsets.MonthEnd(0))])
    daily=pd.Series(0.,index=days)
    for x in filled:
        day=pd.Timestamp(x['available_at']).tz_localize(None).normalize()
        daily.loc[day]+=x['outcome']['trade']['net_r']
    rng=np.random.default_rng(173);n=len(daily);boot=[]
    for _ in range(10000):
        starts=rng.integers(0,n,size=(n+4)//5);ix=((starts[:,None]+np.arange(5))%n).ravel()[:n]
        boot.append(daily.to_numpy()[ix].sum())
    return dict(candidates=len(rows),closed_filled=len(filled),closed_unfilled=len(closed)-len(filled),
        unresolved=sum(x['outcome']['status']!='CLOSED' for x in rows),gross_r=float(sum(x['outcome']['trade']['gross_r'] for x in filled)),
        net_r=float(r.sum()),win_pct=float((r>0).mean()*100) if len(r) else None,
        pf=float(r[r>0].sum()/loss) if loss else None,mean_net_r=float(r.mean()) if len(r) else None,
        closed_result_sequence_dd_r=float((np.maximum.accumulate(curve)-curve).max()),
        without_best5_net_r=float(np.sort(r)[:-5].sum()) if len(r)>=5 else None,
        block_total_r_ci95=np.quantile(boot,[.025,.975]).tolist(),
        overnight_filled=sum(pd.Timestamp(x['outcome']['trade']['closed_at']).date()!=pd.Timestamp(x['outcome']['trade'].get('filled_at',x['available_at'])).date() for x in filled),
        gaps_past_stop=sum(x['outcome']['trade'].get('gap_open_beyond_active_stop_bars',0) for x in filled),
        close_reasons=pd.Series([x['outcome']['trade']['close_reason'] for x in closed]).value_counts().to_dict(),
        by_month={m:float(sum(x['outcome']['trade']['net_r'] for x in filled if x['available_at'][:7]==m)) for m in ['2025-01','2025-06','2025-11']})

def run():
    candidates=freeze();m1={};h1={};rows=[];logging.getLogger('Begonya00.OutcomeTracker').setLevel(logging.ERROR)
    for s in sorted({x['signal']['symbol'] for x in candidates}):
        for tf,dest in [('1m',m1),('1h',h1)]:
            f=pd.read_csv(DATA/f'{s.replace("/", "")}_{tf}.csv.gz');f.datetime=pd.to_datetime(f.datetime,utc=True)
            if f.datetime.duplicated().any() or not f.datetime.is_monotonic_increasing:raise RuntimeError('Bad timestamps')
            if not np.isfinite(f[['open','high','low','close']]).all().all():raise RuntimeError('Bad prices')
            dest[s]=f
    for i,x in enumerate(sorted(candidates,key=lambda x:(x['available_at'],x['signal']['symbol']))):
        sig=x['signal'];s=sig['symbol'];at=pd.Timestamp(x['available_at']);rejection=geometry_rejection(sig)
        stop=int(h1[s].datetime.searchsorted(at,side='right'));hourly=h1[s].iloc[max(0,stop-1000):stop]
        trend=policy.higher_timeframe_trend(hourly,at);expected='BULLISH' if sig['direction']=='LONG' else 'BEARISH'
        common=dict(candidate_id=i,symbol=s,available_at=str(at),morning=at.hour<12,session=bool(x['engine_session_open']),htf_aligned=trend==expected,htf=trend,geometry_rejection=rejection)
        if rejection:
            rows.append(dict(**common,multiplier=None,outcome=dict(status='REJECTED_GEOMETRY',trade={})));continue
        for m in [1.,1.5,2.]:rows.append(dict(**common,multiplier=m,outcome=replay_one(sig,at,m1[s],m)))
    (BASE/'outcomes.json').write_text(json.dumps(rows,default=str,indent=2),encoding='utf8')
    results={}
    for name,select in [('ALL_LONDON',lambda r:True),('MORNING_UTC_BEFORE12',lambda r:r['morning']),('SESSION_AND_HTF_ALIGNED',lambda r:r['session'] and r['htf_aligned'])]:
        cohort=[r for r in rows if select(r)];results[name]={}
        for m in [1.,1.5,2.]:
            sample=[r for r in cohort if r['multiplier']==m]
            results[name][str(m)]=stats(sample,m)
            results[name][str(m)]['geometry_rejected']=sum(r['multiplier'] is None for r in cohort)
        base=[r for r in cohort if r['multiplier']==1. and r['outcome']['status']=='CLOSED' and r['outcome']['trade']['close_reason'] not in policy.NO_FILL_REASONS]
        results[name]['frozen_fill_fee_stress']={str(m):float(sum(r['outcome']['trade']['gross_r']-.08*m for r in base)) for m in [1.,1.5,2.]}
    (BASE/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print(json.dumps(results,indent=2))

if __name__=='__main__':run()
