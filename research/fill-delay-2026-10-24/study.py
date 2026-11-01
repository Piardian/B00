"""Fixed15minute pending-order lifetime research. No live imports/network."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from execution import replay

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SPREADS=[.2,.5,.9,1.5];VARIANTS={'REFERENCE_240':240,'TTL_15':15}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False,allow_nan=False,default=str),encoding='utf-8')


def freeze():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already frozen')
    prior=ROOT/'research/direction-exit-2026-10-24/protocol.json'
    old=json.loads(prior.read_text(encoding='utf-8'))
    for n in ['cases_frozen.json','reference_frozen.json']:
        if sha(HERE/n)!=old['input_hashes'][n]:raise RuntimeError('Prior sample changed')
    write(HERE/'protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),
      sample='Same58 first daily setups Jan/Feb/Mar/Nov2025. All observed; new diagnostic hypothesis, no genuine OOS. RECHECK25 Feb/Mar primary; DISCOVERY33 Jan/Nov supporting.',
      hypothesis='Limit setup may become stale. Only compare pending lifespan240min versus15min, each capped by existingLondonnoon. No entry/stop/target/exit modification.',
      expiry='Order active in [available_at, min(available_at+TTL,Londonnoon)). Exactly15minute fill rejected in15variant; previous descriptive <=15bin is not identical. Already filled position managed normally beyond pending expiry.',
      selection='Same original first daily setup retained, canceled/unfilled consumes date; no later candidate replacement.',
      invariants='Reaction exit always on, same stop-first,fillbarTPban,halfTP1,BE/trail,London16:30flat. Retained early fills must reproduce reference entire lifecycle/netR. Canceled late orders must have no fill/fees. No filled loss can be erased retrospectively.',
      costs='Same assumed spreads.2/.5/.9/1.5pip,primary.5/adverse1.5,USD4/100kroundtrip,.2pipmarketexit slip. Historical bidM1 only; actualask/fees not validated.',
      analysis='All baseline fills split wait<15 versus>=15 (boundary explicit), canceled winners/losers separately, counterfactual savedPnl=-removedbaselinePnl. Avoidedloss is not revenue; original basket opportunity total, no portfolio/redeployment claim.',
      uncertainty='10000 London-day cluster resamples95%paired mean netR delta per accepted setup;seed20261024;exploratory and no multiple-research correction.',
      decision='No live promotion. Candidate survives screen only if15TTL improves RECHECK total AND is positive in BOTH Feb/Mar at.5 and1.5pip with no unresolved, nonzero retainedfills in both months. Merely fewer losses/zero trades not edge.',
      prices=old['prices'],prior_protocol_sha256=sha(prior),
      code_hashes={p.name:sha(p) for p in HERE.glob('*.py')},input_hashes={n:sha(HERE/n) for n in ['cases_frozen.json','reference_frozen.json']}))


def verify():
    p=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    for bucket in ['code_hashes','input_hashes']:
        for n,h in p[bucket].items():
            if sha(HERE/n)!=h:raise RuntimeError('Frozen local mismatch:'+n)
    for m in p['prices'].values():
        if sha(ROOT/m['path'])!=m['sha256']:raise RuntimeError('Price hash mismatch')
    return p


def day_ci(rows,value):
    days=sorted({r['day'] for r in rows})
    if len(days)<5:return None
    sums=np.array([sum(value(r) for r in rows if r['day']==d) for d in days]);n=np.array([sum(r['day']==d for r in rows) for d in days])
    draws=np.random.default_rng(20261024).integers(0,len(days),size=(10000,len(days)))
    return [float(v) for v in np.quantile(sums[draws].sum(axis=1)/n[draws].sum(axis=1),[.025,.975])]


def stats(rows):
    unresolved=sum(r['status']!='CLOSED' for r in rows);filled=[r for r in rows if r['filled_at'] and r['status']=='CLOSED']
    values=[r['net_r'] for r in filled];gain=sum(v for v in values if v>0);loss=-sum(v for v in values if v<0)
    return dict(setups=len(rows),fills=len(filled),unresolved=unresolved,net_r=sum(values) if not unresolved else None,pf=gain/loss if loss else None,
      mean_per_setup_r=sum(values)/len(rows) if rows and not unresolved else None,
      monthly={m:dict(setups=sum(r['month']==m for r in rows),fills=sum(r['month']==m for r in filled),closed_only_r=sum(r['net_r'] for r in filled if r['month']==m)) for m in sorted({r['month'] for r in rows})},
      reasons={reason:sum(r['reason']==reason for r in rows) for reason in sorted({r['reason'] for r in rows})})


def run():
    plan=verify();cases=json.loads((HERE/'cases_frozen.json').read_text(encoding='utf-8'))
    old={(r['case_id'],r['spread_pips']):r for r in json.loads((HERE/'reference_frozen.json').read_text(encoding='utf-8'))}
    frames={k:pd.read_parquet(ROOT/m['path']) if m['path'].endswith('parquet') else pd.read_csv(ROOT/m['path'],parse_dates=['datetime']) for k,m in plan['prices'].items()}
    outcomes=[];matched=0
    for c in cases:
        for sp in SPREADS:
            baseline=None
            for variant,ttl in VARIANTS.items():
                r=replay(c['signal'],c['available_at'],frames[c['source']+'_'+c['symbol']],'passive',spread_pips=sp,reaction_exit='always',pending_ttl_minutes=ttl)
                if variant=='REFERENCE_240':
                    baseline=r;prior=old[c['case_id'],sp]
                    for key in ['status','reason','filled_at','closed_at']:
                        if r[key]!=prior[key]:raise RuntimeError('Reference lifecycle mismatch')
                    if r['net_r'] is None or abs(r['net_r']-prior['net_r'])>1e-9:raise RuntimeError('Reference PNL mismatch')
                    matched+=1
                elif r['status']=='CLOSED':
                    keep=baseline['filled_at'] is not None and pd.Timestamp(baseline['filled_at'])<pd.Timestamp(c['available_at'])+pd.Timedelta(minutes=15)
                    if keep:
                        for key in ['filled_at','closed_at','reason','net_r']:
                            if r[key]!=baseline[key]:raise RuntimeError('TTL changed retained lifecycle')
                    elif r['filled_at'] is not None or r['commission_r']!=0 or r['net_r']!=0:raise RuntimeError('Canceled order created fill or costs')
                wait=None if r['filled_at'] is None else (pd.Timestamp(r['filled_at'])-pd.Timestamp(c['available_at'])).total_seconds()/60
                outcomes.append(dict(case_id=c['case_id'],source=c['source'],day=c['day'],month=c['month'],symbol=c['symbol'],variant=variant,spread_pips=sp,wait_minutes=wait,**r))
    index={(r['case_id'],r['spread_pips'],r['variant']):r for r in outcomes};pairs=[]
    for c in cases:
        for sp in SPREADS:
            ref=index[c['case_id'],sp,'REFERENCE_240'];short=index[c['case_id'],sp,'TTL_15']
            removed=ref['filled_at'] is not None and short['filled_at'] is None
            delta=short['net_r']-ref['net_r'] if ref['net_r'] is not None and short['net_r'] is not None else None
            pairs.append(dict(case_id=c['case_id'],source=c['source'],day=c['day'],month=c['month'],spread_pips=sp,
              baseline_wait_minutes=ref['wait_minutes'],baseline_net_r=ref['net_r'],ttl15_net_r=short['net_r'],delta_r=delta,
              removed=removed,boundary15=ref['wait_minutes']==15,filled_reference=ref['filled_at'] is not None,
              age_group='UNFILLED' if ref['filled_at'] is None else ('BEFORE15' if ref['wait_minutes']<15 else 'AT_OR_AFTER15')))
    summaries=[];comparisons=[];age_groups=[]
    for source in ['ALL','DISCOVERY','RECHECK']:
        for sp in SPREADS:
            sample=[r for r in pairs if r['spread_pips']==sp and (source=='ALL' or r['source']==source)]
            for variant in VARIANTS:
                summaries.append(dict(source=source,spread_pips=sp,variant=variant,**stats([r for r in outcomes if r['variant']==variant and r['spread_pips']==sp and (source=='ALL' or r['source']==source)])))
            removed=[r for r in sample if r['removed']];delta=sum(r['delta_r'] for r in sample if r['delta_r'] is not None)
            removed_net=sum(r['baseline_net_r'] for r in removed)
            if all(r['delta_r'] is not None for r in sample) and abs(delta+removed_net)>1e-9:raise RuntimeError('Removed basket accounting mismatch')
            comparisons.append(dict(source=source,spread_pips=sp,removed_fills=len(removed),boundary15_removed=sum(r['boundary15'] for r in removed),
              missed_winners=sum(r['baseline_net_r']>0 for r in removed),avoided_losers=sum(r['baseline_net_r']<0 for r in removed),
              missed_profit_r=sum(r['baseline_net_r'] for r in removed if r['baseline_net_r']>0),avoided_loss_r=-sum(r['baseline_net_r'] for r in removed if r['baseline_net_r']<0),
              net_delta_r=delta,paired_mean_delta_day95=day_ci(sample,lambda r:r['delta_r']) if all(r['delta_r'] is not None for r in sample) else None))
            for group in ['BEFORE15','AT_OR_AFTER15','UNFILLED']:
                rows=[r for r in sample if r['age_group']==group]
                age_groups.append(dict(source=source,spread_pips=sp,age_group=group,count=len(rows),reference_net_r=sum(r['baseline_net_r'] for r in rows if r['baseline_net_r'] is not None)))
    verify();write(HERE/'outcomes.json',outcomes);write(HERE/'summary.json',summaries);write(HERE/'paired_records.json',pairs)
    write(HERE/'comparisons.json',comparisons);write(HERE/'age_groups.json',age_groups)
    write(HERE/'status.json',dict(cases=len(cases),reference_records_matched=matched,unresolved=sum(r['status']!='CLOSED' for r in outcomes),outcome_rows=len(outcomes),live_promotion=False))
    print(json.dumps([r for r in summaries if r['source']=='RECHECK' and r['spread_pips'] in [.5,1.5]],indent=2))
    print(json.dumps([r for r in comparisons if r['source']=='RECHECK' and r['spread_pips'] in [.5,1.5]],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','verify']);a=p.parse_args()
    {'freeze':freeze,'run':run,'verify':verify}[a.action]()
