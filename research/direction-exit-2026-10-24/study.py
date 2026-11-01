"""Frozen entry-direction diagnostics and single-rule exit ablations.

Uses all58 previously selected setups, never an out-of-sample proof.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from execution import replay
from direction import score

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SPREADS=[.2,.5,.9,1.5];MODES=['always','never','half_r_adverse']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False,allow_nan=False,default=str),encoding='utf-8')


def freeze():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already frozen')
    discovery=ROOT/'research/structure-room-2026-10-23/setups_frozen.json'
    validation=ROOT/'research/asia-validation-2026-10-24/candidates.json'
    sources=[discovery,validation,ROOT/'research/structure-room-2026-10-23/outcomes.json',ROOT/'research/asia-validation-2026-10-24/outcomes.json']
    cases=[];reference=[]
    for source,path in [('DISCOVERY',discovery),('RECHECK',validation)]:
        for i,c in enumerate(json.loads(path.read_text(encoding='utf-8'))):
            symbol=c['signal']['symbol'].replace('/','')
            cases.append(dict(case_id=source+'_'+str(i),source=source,source_id=i,symbol=symbol,day=c['day'],month=c['day'][:7],signal=c['signal'],available_at=c['available_at']))
    for source,path in [('DISCOVERY',sources[2]),('RECHECK',sources[3])]:
        for r in json.loads(path.read_text(encoding='utf-8')):
            if source=='DISCOVERY' and r['variant']!='reference':continue
            index=r['setup_id'] if source=='DISCOVERY' else r['candidate_id']
            reference.append(dict(case_id=source+'_'+str(index),spread_pips=r['spread_pips'],status=r['status'],reason=r['reason'],filled_at=r['filled_at'],closed_at=r['closed_at'],net_r=r['net_r']))
    assert len(cases)==58 and len(reference)==232
    write(HERE/'cases_frozen.json',cases);write(HERE/'reference_frozen.json',reference)
    prices={}
    for c in cases:
        s=c['symbol'];key=c['source']+'_'+s
        path=ROOT/(f'data/full_2025_study/prices_utc/{s}_1m.csv.gz' if c['source']=='DISCOVERY' else f'research/asia-validation-2026-10-24/prices/{s}_1m.parquet')
        prices[key]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
    write(HERE/'protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),
      sample='All58 first daily setups from Jan/Feb/Mar/Nov2025. All previously observed; post-negative-validation diagnosis, not new OOS or independent profitability proof.',
      entry_direction='At each original availability, measure next60minute bid-open move divided by original entry-stop risk. Original sign versus reversed sign on identical timestamp/risk. All58, no conditioning on fill or future outcome; full61minute grid required. No fee or stop: direction score, NOT trading PNL or executable reversed strategy.',
      exit_rules={'always':'Unchanged adverse fill-bar reaction exit','never':'Only remove reaction exit, keep original entry/stop/targets and all other management','half_r_adverse':'Same reaction failure test but exit only when fill-bar executable close is <=-.5R relative entry, before exit slippage/fee. Close known only after fill minute. Fixed threshold, no sweep.'},
      primary='RECHECK25 Feb/Mar; discovery33 Jan/Nov supporting contrast. Same case set, fills and original risk across all exit modes. Reference must match all232 prior replay records.',
      costs='Prior assumed constant spreads .2/.5/.9/1.5pip; primary.5/adverse1.5. CommissionUSD4/100k roundtrip and.2pip adverse exit slip. Not actual historic ask/fees.',
      invariants='Original stop protection always active, stop-first, no fill-bar targets, same halfTP1/BE/trail andLondon16:30flat, pendingnoon/4h. Never erase filled trade after bad reaction.',
      uncertainty='Day-cluster bootstrap10000(seed20261024)95% mean per accepted setup and paired variant minus reference; diagnosis only, no multiple-research correction. Direction day means also exploratory.',
      decision='No live promotion regardless of result. A useful new exit candidate must improve primary recheck paired mean, remain net positive in BOTH Feb and Mar at.5 and1.5 and avoid unresolved; otherwise reject. Discovery outcome cannot rescue failed recheck. Never label reverse sign profitable strategy.',
      prices=prices,source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources},
      code_hashes={p.name:sha(p) for p in HERE.glob('*.py')},
      input_hashes={p.name:sha(p) for p in [HERE/'cases_frozen.json',HERE/'reference_frozen.json']}))


def verify():
    p=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    for bucket in ['code_hashes','input_hashes']:
        for n,h in p[bucket].items():
            if sha(HERE/n)!=h:raise RuntimeError('Frozen local changed:'+n)
    for n,h in p['source_hashes'].items():
        if sha(ROOT/n)!=h:raise RuntimeError('Source changed:'+n)
    for m in p['prices'].values():
        if sha(ROOT/m['path'])!=m['sha256']:raise RuntimeError('Price changed')
    return p


def ci_day(rows,value):
    days=sorted({r['day'] for r in rows})
    if len(days)<5:return None
    sums=np.array([sum(value(r) for r in rows if r['day']==d) for d in days]);counts=np.array([sum(r['day']==d for r in rows) for d in days])
    picks=np.random.default_rng(20261024).integers(0,len(days),size=(10000,len(days)))
    return [float(v) for v in np.quantile(sums[picks].sum(axis=1)/counts[picks].sum(axis=1),[.025,.975])]


def stats(rows):
    unresolved=sum(r['status']!='CLOSED' for r in rows);closed=[r for r in rows if r['status']=='CLOSED' and r['filled_at']]
    values=[r['net_r'] for r in closed];gain=sum(v for v in values if v>0);loss=-sum(v for v in values if v<0)
    return dict(setups=len(rows),fills=len(closed),unresolved=unresolved,net_r=sum(values) if not unresolved else None,
      pf=gain/loss if loss else None,mean_setup_r=sum(values)/len(rows) if rows and not unresolved else None,
      mean_setup_r_day95=ci_day(rows,lambda r:r['net_r']) if not unresolved else None,
      monthly={m:dict(fills=sum(r['month']==m for r in closed),net_r=sum(r['net_r'] for r in closed if r['month']==m)) for m in sorted({r['month'] for r in rows})},
      reasons={reason:sum(r['reason']==reason for r in rows) for reason in sorted({r['reason'] for r in rows})})


def run():
    plan=verify();cases=json.loads((HERE/'cases_frozen.json').read_text(encoding='utf-8'))
    reference={(r['case_id'],r['spread_pips']):r for r in json.loads((HERE/'reference_frozen.json').read_text(encoding='utf-8'))}
    frames={k:pd.read_parquet(ROOT/m['path']) if m['path'].endswith('parquet') else pd.read_csv(ROOT/m['path'],parse_dates=['datetime']) for k,m in plan['prices'].items()}
    outcomes=[];directions=[]
    for c in cases:
        frame=frames[c['source']+'_'+c['symbol']]
        directions.append(dict(case_id=c['case_id'],source=c['source'],day=c['day'],month=c['month'],symbol=c['symbol'],**score(c['signal'],c['available_at'],frame)))
        for sp in SPREADS:
            filled=None
            for mode in MODES:
                r=replay(c['signal'],c['available_at'],frame,'passive',spread_pips=sp,reaction_exit=mode)
                if mode=='always':
                    old=reference[c['case_id'],sp]
                    for key in ['status','reason','filled_at','closed_at']:
                        if r[key]!=old[key]:raise RuntimeError('Reference lifecycle drift:'+c['case_id']+key)
                    if r['net_r'] is None or abs(r['net_r']-old['net_r'])>1e-9:raise RuntimeError('Reference PNL drift')
                    filled=r['filled_at']
                elif r['filled_at']!=filled:raise RuntimeError('Exit mode changed entry fill')
                outcomes.append(dict(case_id=c['case_id'],source=c['source'],day=c['day'],month=c['month'],symbol=c['symbol'],mode=mode,spread_pips=sp,**r))
    summaries=[];paired=[];direction_summary=[]
    for source in ['ALL','DISCOVERY','RECHECK']:
        for sp in SPREADS:
            for mode in MODES:
                rows=[r for r in outcomes if r['spread_pips']==sp and r['mode']==mode and (source=='ALL' or r['source']==source)]
                summaries.append(dict(source=source,spread_pips=sp,mode=mode,**stats(rows)))
                if mode!='always':
                    matches=[dict(day=r['day'],delta=r['net_r']-reference[r['case_id'],sp]['net_r']) for r in rows if r['status']=='CLOSED']
                    paired.append(dict(source=source,spread_pips=sp,mode=mode,paired_setups=len(matches),
                      total_delta_r=sum(r['delta'] for r in matches),improved=sum(r['delta']>1e-9 for r in matches),worsened=sum(r['delta']< -1e-9 for r in matches),
                      paired_mean_delta_day95=ci_day(matches,lambda r:r['delta']) if len(matches)==len(rows) else None))
        rows=[r for r in directions if r['status']=='MEASURED' and (source=='ALL' or r['source']==source)]
        n=len(rows);values=[r['original_score_r'] for r in rows]
        direction_summary.append(dict(source=source,measured=n,positive=sum(v>0 for v in values),negative=sum(v<0 for v in values),zero=sum(v==0 for v in values),
            original_mean_score_r=sum(values)/n if n else None,reversed_mean_score_r=-sum(values)/n if n else None,
            original_median_score_r=float(np.median(values)) if n else None,
            original_mean_day95=ci_day(rows,lambda r:r['original_score_r']),
            monthly={m:dict(n=sum(r['month']==m for r in rows),original_mean_score_r=float(np.mean([r['original_score_r'] for r in rows if r['month']==m]))) for m in sorted({r['month'] for r in rows})}))
    verify();write(HERE/'outcomes.json',outcomes);write(HERE/'summary.json',summaries);write(HERE/'paired.json',paired)
    write(HERE/'direction_records.json',directions);write(HERE/'direction_summary.json',direction_summary)
    write(HERE/'status.json',dict(cases=len(cases),reference_records_matched=len(reference),outcome_rows=len(outcomes),unresolved=sum(r['status']!='CLOSED' for r in outcomes),direction_unresolved=sum(r['status']!='MEASURED' for r in directions),live_promotion=False))
    print(json.dumps([r for r in summaries if r['source']=='RECHECK' and r['spread_pips'] in [.5,1.5]],indent=2));print(json.dumps(direction_summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','verify']);a=p.parse_args()
    {'freeze':freeze,'run':run,'verify':verify}[a.action]()
