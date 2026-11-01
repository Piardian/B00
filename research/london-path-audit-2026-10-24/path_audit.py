"""Read-only, frozen diagnostic of existing ORB trades; no strategy search."""
from pathlib import Path
import sys, json, hashlib, csv
from datetime import datetime, timezone
from collections import Counter
import numpy as np
import pandas as pd

BASE=Path(__file__).resolve().parent
PRIOR=BASE.parent/'london-quote-validation-2026-10-23'
EXT=BASE.parent/'london-extension-2026-10-24'
SCENARIOS={'OBSERVED_QUOTES_1x':1.,'COST_STRESS_1.5x':1.5}
THRESHOLDS=[0.,.25,.5,1.,1.5]

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,indent=2,default=str),encoding='utf8')

def freeze():
    paths=[Path(__file__),BASE/'test_path_audit.py',PRIOR/'quote_engine.py',PRIOR/'native_outcomes.json',PRIOR/'quote_manifest_frozen.json',EXT/'outcomes.json',EXT/'quote_manifest_frozen.json',EXT/'protocol_frozen.json',BASE.parent/'entry-innovation-2026-10-23/REPORT.md',BASE.parent/'london-edge-development-2026-10-23/SONUC.md']
    declaration=dict(
        task='Describe price paths of all six-month existing classic ORB trades; no order calls, MT5 access, strategy changes or parameter optimization',
        scenarios=list(SCENARIOS),primary='RVOL>=1 at COST_STRESS_1.5x; all-volume control and observed1x shown separately',
        months=['2025-02','2025-03','2025-04','2025-05','2025-09','2025-10'],
        cohorts='All first daily closed opportunities; filtered subset rvol>=1; never exclude losing months or symbols',
        path='Executable liquidation netR at observed bid/ask widened by fixed factor, adverse0.1pip/side*factor, original fixed roundtripcommission; include entry-quote immediate liquidation; TP terminal capped at recorded fill; only up to actual terminal exit for MFE/MAE',
        thresholds=THRESHOLDS,stop_time_minutes=[5,15,30,60],
        later_path='After actualSL continue observing to first16:00Londonquote only as hindsight diagnostic; never count later target as recoverable profit or ignore intervening stop risk',
        return_inside='Strict return within broken BID boundary after entry and before exit; any simple retest must avoid conditioning on future win/loss',
        categories='TP2, SL without+0.5netR, SL after+0.5netR, EOD positive/negative; categories descriptive not causal or alternativeexit returns',
        parity='Reconstruct chronological entry/exit indices, direction/risk/fills/fees and compare all original CLOSED fields; fail on any discrepancy; preserve same-millisecond order; inputs rehash before/after',
        next_step='Do not auto-add BE/TP1 or assume retest profitable from MFE. If only a minority of losers first earn+0.5R, deprioritize profit-management rescue. Retest can be justified for separate experiment only when loser reversal/return differs descriptively from winners; previous negativeM1tests remain relevant. Any future strategy needs frozen causal rules and separate validation.',
        limitations='Already-seen historical periods; no OOS, no fitted threshold, no causal claim, no account equity, no independent fill guarantee',
        hashes={str(p):sha(p) for p in paths})
    target=BASE/'protocol_frozen.json'
    if target.exists():assert read(target)['declaration']==declaration,'Frozen diagnostic changed'
    else:
        save(target,dict(frozen_utc=datetime.now(timezone.utc).isoformat(),declaration=declaration))
        folder=BASE/'frozen_sources';folder.mkdir(exist_ok=True)
        for i,p in enumerate(paths): (folder/f'{i:02}_{p.name}').write_bytes(p.read_bytes())
    return declaration

def reconstruct(frame,row):
    """Vector equivalent of the old engine, with exact quote indices and marks."""
    symbol,date=row['symbol'],row['date']; old=row['outcome']; mult=SCENARIOS[row['scenario']]
    f=frame.reset_index(drop=True);times=pd.DatetimeIndex(f.time)
    start=pd.Timestamp(date+' 08:00',tz='Europe/London').tz_convert('UTC');end=pd.Timestamp(date+' 16:00',tz='Europe/London').tz_convert('UTC')
    deadline=pd.Timestamp(date+' 12:00',tz='Europe/London').tz_convert('UTC')
    bid=f.bid.to_numpy(float);ask=bid+(f.ask.to_numpy(float)-bid)*mult
    flags=f['flags'].to_numpy(np.int64)
    oi=np.flatnonzero((times>=start)&(times<start+pd.Timedelta(minutes=15))&((flags&2)!=0))
    hi,lo=bid[oi].max(),bid[oi].min();direction=int(np.sign(bid[oi[-1]]-bid[oi[0]]))
    point=.01 if symbol.endswith('JPY') else .0001;slip=point*.1*mult
    possible=(times>=start+pd.Timedelta(minutes=15))&(times<deadline)&((bid>=hi) if direction==1 else (bid<=lo))
    entry_i=int(np.flatnonzero(possible)[0]);entry=ask[entry_i]+slip if direction==1 else bid[entry_i]-slip
    stop=lo if direction==1 else hi
    risk=entry-stop if direction==1 else stop+(ask[entry_i]-bid[entry_i])-entry
    target=entry+direction*2*risk
    stop_hits=bid<=stop if direction==1 else bid>=stop
    target_hits=bid>=target if direction==1 else ask<=target
    terminal=(times>=end)|stop_hits|target_hits
    terminal[:entry_i+1]=False
    exit_i=int(np.flatnonzero(terminal)[0])
    reason='EOD' if times[exit_i]>=end else 'SL' if stop_hits[exit_i] else 'TP2'
    exit_price=(bid[exit_i]-slip if direction==1 else ask[exit_i]+slip) if reason!='TP2' else target-slip*direction
    commission=4.*(1. if symbol.endswith('USD') else entry)/100000*mult
    net=direction*(exit_price-entry)/risk-commission/risk
    for key,value in dict(entry=entry,exit=exit_price,initial_risk=risk,stop_bid=stop,target=target,commission_r=commission/risk,net_r=net).items():
        assert np.isclose(value,old[key],rtol=0,atol=1e-10),(symbol,date,key,value,old[key])
    assert reason==old['reason'] and times[entry_i]==pd.Timestamp(old['entry_time']) and times[exit_i]==pd.Timestamp(old['exit_time']),(symbol,date,'time/reason parity')
    # At t=entry include immediate unwind cost. At terminal use recorded exit,
    # particularly TP whose execution is capped rather than favourable gap fill.
    marked=direction*((bid-slip if direction==1 else ask+slip)-entry)/risk-commission/risk
    live=marked[entry_i:exit_i+1].copy();live[-1]=net
    eod_i=int(np.flatnonzero(times>=end)[0])
    whole=marked[entry_i:eod_i+1]
    boundary=hi if direction==1 else lo
    inside=(bid<boundary) if direction==1 else (bid>boundary)
    returned=np.flatnonzero(inside[entry_i+1:exit_i+1])
    first_return=entry_i+1+int(returned[0]) if len(returned) else None
    result=dict(symbol=symbol,date=date,scenario=row['scenario'],rvol=row['rvol'],primary=row['rvol'] is not None and row['rvol']>=1,
        direction=direction,reason=reason,net_r=net,entry_time=str(times[entry_i]),exit_time=str(times[exit_i]),
        held_minutes=float((times[exit_i]-times[entry_i]).total_seconds()/60),mfe_net_r=float(live.max()),mae_net_r=float(live.min()),
        immediate_liquidation_net_r=float(live[0]),commission_r=float(commission/risk),initial_risk_pips=float(risk/point),
        returned_inside_before_exit=first_return is not None,first_return_minutes=None if first_return is None else float((times[first_return]-times[entry_i]).total_seconds()/60),
        to_eod_mfe_net_r_hindsight=float(whole.max()),stopped_then_original_target_later_hindsight=bool(reason=='SL' and target_hits[exit_i+1:eod_i+1].any()),
        entry_quote_index=entry_i,exit_quote_index=exit_i)
    for threshold in THRESHOLDS:
        ix=np.flatnonzero(live>threshold if threshold==0 else live>=threshold)
        result[f'reached_{threshold:g}_net_r']=bool(len(ix))
        result[f'minutes_to_{threshold:g}_net_r']=float((times[entry_i+ix[0]]-times[entry_i]).total_seconds()/60) if len(ix) else None
    result['category']='TP2' if reason=='TP2' else ('SL_after_0.5netR' if live.max()>=.5 else 'SL_without_0.5netR') if reason=='SL' else 'EOD_positive' if net>0 else 'EOD_nonpositive'
    return result

def aggregate(rows):
    stopped=[r for r in rows if r['reason']=='SL'];losers=[r for r in rows if r['net_r']<0];winners=[r for r in rows if r['net_r']>0]
    def subset(group):
        return dict(n=len(group),net_r=sum(r['net_r'] for r in group),returned_inside=sum(r['returned_inside_before_exit'] for r in group),
            reached={str(t):sum(r[f'reached_{t:g}_net_r'] for r in group) for t in THRESHOLDS},
            median_mfe_net_r=float(np.median([r['mfe_net_r'] for r in group])) if group else None,
            median_held_minutes=float(np.median([r['held_minutes'] for r in group])) if group else None)
    return dict(all=subset(rows),stopped=subset(stopped),losers=subset(losers),winners=subset(winners),categories=dict(Counter(r['category'] for r in rows)),
        stopped_by_minutes={str(m):sum(r['held_minutes']<=m for r in stopped) for m in [5,15,30,60]},
        stopped_then_target_later=sum(r['stopped_then_original_target_later_hindsight'] for r in stopped),
        by_month={month:subset([r for r in rows if r['date'].startswith(month)]) for month in sorted(set(r['date'][:7] for r in rows))})

def run():
    declaration=freeze()
    rows=read(PRIOR/'native_outcomes.json')+read(EXT/'outcomes.json')
    manifests={**read(PRIOR/'quote_manifest_frozen.json')['files'],**read(EXT/'quote_manifest_frozen.json')['files']}
    grouped={}
    for row in rows:
        if row['scenario'] in SCENARIOS and row['outcome']['status']=='CLOSED':grouped.setdefault(row['symbol']+'_'+row['date'],[]).append(row)
    paths=[];digests={};last_symbol=None
    for key,group in sorted(grouped.items()):
        meta=manifests[key];p=Path(meta['path']);assert sha(p)==meta['sha256'],key
        frame=pd.read_parquet(p);frame.time=pd.to_datetime(frame.time,utc=True)
        for row in group:paths.append(reconstruct(frame,row))
        digests[str(p)]=meta['sha256']
        if group[0]['symbol']!=last_symbol:
            last_symbol=group[0]['symbol'];print('AUDITING',last_symbol,flush=True)
    save(BASE/'paths.json',paths)
    with (BASE/'paths.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(paths[0]));writer.writeheader();writer.writerows(paths)
    results={}
    for scenario in SCENARIOS:
        results[scenario]={cohort:aggregate([r for r in paths if r['scenario']==scenario and (cohort=='control' or r['primary'])]) for cohort in ['primary','control']}
    for p,digest in {**declaration['hashes'],**digests}.items():assert sha(Path(p))==digest,p
    save(BASE/'results.json',results)
    save(BASE/'integrity_check.json',dict(passed=True,source_files=len(declaration['hashes']),tapes=len(digests),closed_rows_parity=len(paths),all_sources_and_tapes_rehashed_after=True))
    print('PATH_AUDIT_COMPLETE',len(paths),flush=True)

if __name__=='__main__':{'freeze':freeze,'run':run}[sys.argv[1]]()
