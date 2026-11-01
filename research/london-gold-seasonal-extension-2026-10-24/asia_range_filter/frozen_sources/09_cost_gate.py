"""One entry-information-only cost/risk gate; no seasonal combination or order API."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json
import numpy as np
import pandas as pd
import study as s
g=s.g
BASE=s.BASE/'cost_gate'

def freeze():
    BASE.mkdir(exist_ok=True)
    paths=[Path(__file__),s.BASE/'COZUM_PLANI.md',s.BASE/'protocol_frozen.json',s.BASE/'study.py',s.VALID/'validate.py',s.v.OLD/'study.py']
    g.save(BASE/'protocol_frozen.json',dict(frozen_utc=datetime.now(timezone.utc).isoformat(),
        hypothesis='One same-day first-entry gate: projected roundtrip entryspread+2slippage+commission divided by same initial risk<=0.05. Reject first candidate no second attempt. No summer filter.',
        info='Only timestamp/direction/entry/risk/commission derived from entry geometry; raw entryspread only. Actual future exitspread unknown, so entryspread is roundtrip proxy. Entry fee fixed same frozen policy. Does not use future PnL or exit to select.',
        study_status='Frozen before new2025SepDec/2026 outcomes calculated here. FirstJanAug outcomes already known. Exploratory3-hypothesis research family, not pristine OOS/prospective.',
        comparisons='Same groups/costs as seasonalextension, gate on its own vs unfilteredORB. No threshold tuning, no merging seasonal filter. Full calendar disabled opportunities zero; unknown entry/tape remains unknown.',
        stats='10k circular5day seed173 daily total/delta;98.333333percent two-sided Bonferroni interval for family3. Newperiods positive stress net and paired delta, complete coverage and adequate sample required; passing only motivates independent validation.',
        live_approved=False,hashes={str(p):g.sha(p) for p in paths}))
    print('COST_GATE_FROZEN',flush=True)

def decision(outcome,spread,mult):
    # Explicit whitelist; no exit or outcome field enters eligibility.
    risk=float(outcome['initial_risk']);fee=float(outcome['assumed_commission_usd_per_lot_roundtrip'])/100
    ratio=(float(spread)*mult+2*.05*mult+fee)/risk
    return ratio<=.05,ratio

def interval(daily):
    v=np.asarray(daily);n=len(v);rng=np.random.default_rng(173);totals=[]
    for _ in range(10000):
        starts=rng.integers(0,n,size=(n+4)//5);ix=((starts[:,None]+np.arange(5))%n).ravel()[:n];totals.append(v[ix].sum())
    return np.quantile(totals,[.025/3,1-.025/3]).tolist()

def run():
    p=g.read(BASE/'protocol_frozen.json')
    for path,digest in p['hashes'].items():assert g.sha(Path(path))==digest,path
    rows=s.read('outcomes.json');manifest=s.read('quote_manifest.json');assert s.read('integrity_check.json')['passed']
    gated=[];features=[]
    for date in g.dates(s.MONTHS):
        daily=[r for r in rows if r['date']==date];closed=[r for r in daily if r['outcome']['status']=='CLOSED']
        f=None
        if closed:
            meta=manifest['files'][date];path=Path(meta['path']);assert g.sha(path)==meta['sha256'];f=pd.read_parquet(path)
        for r in daily:
            out=r['outcome'];changed=out.copy()
            if out['status']=='CLOSED':
                name=r['scenario'];mult=dict(g.SCENARIOS)[name];q=f[f.time==pd.Timestamp(out['entry_time'])]
                expected=q.bid+(q.ask-q.bid)*mult+.05*mult if out['direction']==1 else q.bid-.05*mult
                q=q[np.isclose(expected,out['entry'],atol=1e-8,rtol=0)]
                assert len(q),'Entry quote reconciliation '+date
                spread=float(q.ask.iloc[0]-q.bid.iloc[0]);ok,ratio=decision(out,spread,mult)
                features.append(dict(date=date,scenario=name,allowed=bool(ok),projected_entry_cost_r=ratio,entryspread=spread))
                if not ok:changed=dict(status='REJECT_COST_OVER_0_05R')
            gated.append(dict(date=date,scenario=r['scenario'],outcome=changed))
    groups={'known2025JanAug':s.MONTHS[:8],'new2025SepDec':s.MONTHS[8:12],'2025_full':s.MONTHS[:12],'2026JanSep_partial':s.MONTHS[12:],'all21months':s.MONTHS}
    results={}
    for group,months in groups.items():
        calendar=g.dates(months);results[group]={}
        for name,m in g.SCENARIOS:
            a=[r for r in rows if r['scenario']==name and r['date'][:7] in months];b=[r for r in gated if r['scenario']==name and r['date'][:7] in months]
            unknown=[r['date'] for r in a+b if r['outcome']['status'] in g.UNKNOWN]
            if unknown:results[group][name]=dict(complete=False,unknown_dates=sorted(set(unknown)));continue
            baseline=s.v.stats(a,calendar);variant=s.v.stats(b,calendar);delta=pd.Series(0.,index=calendar);daily=pd.Series(0.,index=calendar)
            for r in a:delta.loc[r['date']]-=r['outcome'].get('net_r',0)
            for r in b:
                val=r['outcome'].get('net_r',0);delta.loc[r['date']]+=val;daily.loc[r['date']]+=val
            assert abs(delta.sum()-(variant['net_r']-baseline['net_r']))<1e-9
            results[group][name]=dict(complete=True,baseline=baseline,costgate=variant,paired_delta_net_r=float(delta.sum()),paired_delta_ci98_33=interval(delta),variant_ci98_33=interval(daily))
    g.save(BASE/'results.json',dict(results=results,live_approved=False,orders_sent=False))
    g.save(BASE/'entry_features.json',features);g.save(BASE/'outcomes.json',gated)
    for path,digest in p['hashes'].items():assert g.sha(Path(path))==digest,path
    g.save(BASE/'completion.json',dict(status='COMPLETE',entry_gate_only=True,source_hashes_verified=True,hashes={n:g.sha(BASE/n) for n in ['protocol_frozen.json','results.json','entry_features.json','outcomes.json']}))
    print('COST_GATE_COMPLETE',flush=True)

if __name__=='__main__':{'freeze':freeze,'run':run}[sys.argv[1]]()
