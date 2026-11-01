"""Full quote-lifecycle replay, fixed rules and finite cost/TTL comparison."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
from engine import replay

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SCENARIOS={
 'OBSERVED_QUOTES':dict(spread_mult=1.,spread_floor_pips=0.,fee_mult=1.,slip_mult=1.),
 'COST_STRESS_1_5X':dict(spread_mult=1.5,spread_floor_pips=0.,fee_mult=1.5,slip_mult=1.5),
 'SPREAD_FLOOR_1PIP':dict(spread_mult=1.5,spread_floor_pips=1.,fee_mult=1.5,slip_mult=1.5)}
TTLS={'REFERENCE_240':240,'TTL_15':15}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False,allow_nan=False,default=str),encoding='utf-8')


def freeze():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already frozen')
    source=ROOT/'research/fill-delay-tick-audit-2026-10-24/cases_frozen.json'
    if sha(source)!=sha(HERE/'cases_frozen.json'):raise RuntimeError('Case drift')
    cases=json.loads(source.read_text(encoding='utf-8'))
    if len(cases)!=90:raise RuntimeError('All90 cases required')
    for c in cases:
        if sha(Path(c['tape_path']))!=c['tape_sha256']:raise RuntimeError('Base quote changed')
    write(HERE/'protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),scope='All90 locked prior setups Feb/Mar/Apr/May/Sep/Oct2025; retrospective, previously examined, no pristine OOS or full-bot claim.',
      scenarios=SCENARIOS,ttls=TTLS,
      geometry='Original fixed entry/stop/TP1/TP2 exactly retained, same first daily setup. Limit at nominal price on one-tick penetration, favorable improvement ignored. Marketable-at-opening case flagged and separately tested; broker acceptance unknown.',
      lifecycle='Chronological actual quote order. Long exits bid,short exits ask. Initial stop on every quote including fill. No targets in entire fill M1. Adverse reaction uses full completed BID M1 shape, acts on first subsequent quote, never previous close. Stop precedes reaction exit on same quote. HalfTP1 then remainingTP2. BE effective next M1;1.5R->.75R trail only after TP1 bar, effective next M1. London16:30flat first availablequote.',
      execution_difference='Tick ordering resolves M1 high-low uncertainty: TP1 before later same-M1stop legitimately retains partial gain. Signals/levels unchanged. Reaction execution next quote differs from old M1close proxy. Do not call this a byte-identical legacy live bot.',
      costs='Observedspread in executable quote prices, never extra-debited; stress ask widened as scenarios. AssumedUSD4/100k roundtrip(base) chargedUSD2eachside weightedpartials; USDbase converted at respectiveprice; .2pip(base) adverse slip ONLY marketexit, no limit improvement. Rquote risk,notaccountUSDreturn.',
      quality='Positive finite noncrossed quotes, chronological including same-ms row order. Firstquote<=5secafterdecision. No gap>60sec until terminalevent; unresolved means no netR. Pendingexpiry exclusive; alreadyfilled unaffected. All90quote tails requested before any PNL to16:31, from existing cached months, no interpolation.',
      data_collection='Read-only explicitThe5ersterminal, existingtickcacheonly; >=512MiBfree and<=64MiBnetgrowth guard for small tails, no deletion or paidAPI.',
      decision='Demo screen only if a TTL has >=50closedfills observed, positive total in ALL3scenarios and positive RECHECKandFOLLOWUPcohorts all3, >=4of6positive months observedandcoststress, lowerdaycluster95meanobserved>0, no unresolved and removing marketable-opening cases leaves positive totals all3. Historical multiple tests and unverifiedfees still preclude live approval. If neither passes, stop further TTL/TP/SL sweeps on this frozen ORB branch.',
      uncertainty='10000London-day cluster resamples(seed20261024),95%mean per accepted setup, not multiple-testing corrected. Finite cost stress; no threshold fit.',
      cases_sha256=sha(HERE/'cases_frozen.json'),source_cases_sha256=sha(source),
      code_hashes={p.name:sha(p) for p in HERE.glob('*.py')}))


def verify():
    p=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    for n,h in p['code_hashes'].items():
        if sha(HERE/n)!=h:raise RuntimeError('Frozen source mismatch:'+n)
    if sha(HERE/'cases_frozen.json')!=p['cases_sha256']:raise RuntimeError('Frozen cases changed')
    return p


def ci_day(rows):
    if any(r['status']!='CLOSED' for r in rows):return None
    days=sorted({r['day'] for r in rows})
    if len(days)<5:return None
    values=np.array([sum(r['net_r'] for r in rows if r['day']==d) for d in days]);n=np.array([sum(r['day']==d for r in rows) for d in days])
    draw=np.random.default_rng(20261024).integers(0,len(days),size=(10000,len(days)))
    return [float(x) for x in np.quantile(values[draw].sum(axis=1)/n[draw].sum(axis=1),[.025,.975])]


def stats(rows):
    closed=[r for r in rows if r['status']=='CLOSED' and r['filled_at']];unknown=sum(r['status']!='CLOSED' for r in rows)
    values=[r['net_r'] for r in closed];gain=sum(v for v in values if v>0);loss=-sum(v for v in values if v<0)
    return dict(setups=len(rows),fills=len(closed),unresolved=unknown,net_r=sum(values) if not unknown else None,
      closed_only_net_r=sum(values),gross_price_r=sum(r['gross_r'] for r in closed),commission_r=sum(r['commission_r'] for r in closed),
      assumed_market_slippage_r=sum(r['market_slippage_r'] for r in closed),pf=gain/loss if loss else None,
      mean_setup_day95=ci_day(rows),marketable_openings=sum(bool(r['marketable_opening']) for r in rows),
      net_excluding_marketable_cases=sum(r['net_r'] for r in closed if not r['marketable_opening']),
      monthly={m:dict(setups=sum(r['month']==m for r in rows),fills=sum(r['month']==m for r in closed),closed_only_r=sum(r['net_r'] for r in closed if r['month']==m),unresolved=sum(r['month']==m and r['status']!='CLOSED' for r in rows)) for m in sorted({r['month'] for r in rows})},
      reasons={reason:sum(r['reason']==reason for r in rows) for reason in sorted({r['reason'] for r in rows})})


def run():
    verify();cases=json.loads((HERE/'cases_frozen.json').read_text(encoding='utf-8'))
    tails=json.loads((HERE/'tail_manifest.json').read_text())
    if not tails.get('complete') or len(tails['files'])!=90:raise RuntimeError('All90 quote tails required')
    lock=HERE/'tail_manifest_frozen.json'
    if lock.exists() and json.loads(lock.read_text())!=tails:raise RuntimeError('Tail manifest changed')
    if not lock.exists():write(lock,tails)
    outcomes=[]
    for i,c in enumerate(cases):
        base=Path(c['tape_path']);tail=HERE/tails['files'][c['case_id']]['path']
        if sha(base)!=c['tape_sha256'] or sha(tail)!=tails['files'][c['case_id']]['sha256']:raise RuntimeError('Quote tape hash changed')
        a=pd.read_parquet(base);b=pd.read_parquet(tail);cut=pd.Timestamp(c['day']+' 16:00',tz='Europe/London').tz_convert('UTC')
        tape=pd.concat([a[a.time<cut],b[b.time>=cut]],ignore_index=True)
        for scenario,kwargs in SCENARIOS.items():
            for ttl,minutes in TTLS.items():
                r=replay(c['signal'],c['available_at'],tape,c['point'],ttl_minutes=minutes,**kwargs)
                outcomes.append(dict(case_id=c['case_id'],cohort=c['cohort'],symbol=c['symbol'],day=c['day'],month=c['month'],scenario=scenario,ttl=ttl,**r))
        if (i+1)%10==0:print('REPLAY_CASES',i+1,'of90',flush=True)
    summaries=[dict(cohort=g,scenario=s,ttl=t,**stats([r for r in outcomes if r['scenario']==s and r['ttl']==t and (g=='ALL' or r['cohort']==g)])) for g in ['ALL','RECHECK','FOLLOWUP'] for s in SCENARIOS for t in TTLS]
    verify();write(HERE/'outcomes.json',outcomes);write(HERE/'summary.json',summaries)
    write(HERE/'status.json',dict(cases=len(cases),outcomes=len(outcomes),unresolved=sum(r['status']!='CLOSED' for r in outcomes),live_execution=False))
    print(json.dumps([r for r in summaries if r['cohort']=='ALL'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','verify']);a=p.parse_args()
    {'freeze':freeze,'run':run,'verify':verify}[a.action]()
