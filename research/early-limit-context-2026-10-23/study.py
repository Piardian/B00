"""Frozen descriptive regime measurements plus actual decision quote audit.

Grouped PNL labels remain the prior modeled reference; quote snapshots do not
reconstruct complete bid/ask fills, commissions or full system profitability.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from measurement import context,decision_measurement

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SYMBOLS=['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')


def freeze():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already frozen')
    source=ROOT/'research/structure-room-2026-10-23/outcomes.json'
    outcomes=json.loads(source.read_text(encoding='utf-8'))
    write(HERE/'reference_frozen.json',[r for r in outcomes if r['variant']=='reference'])
    local=list(HERE.glob('*.py'))+[HERE/'reference_frozen.json',HERE/'setups_frozen.json']
    write(HERE/'protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),
      scope='Descriptive conditions of all33 prior early-limit setups. Previously observed Jan/Nov2025, no new OOS or full-system claim.',
      partitions={'timing':'London decision before09 vs09-noon','htf':'Existing setup flag aligned vs not aligned',
                  'asia':'Asia range/daily ATR <=.35 vs>.35, unknown explicit',
                  'cost_group':'Observed decision spread + assumed USD4/100k and .2pip exit slip, normalized risk <=.10R /(.10,.20]R />.20R; unpriced explicit'},
      purpose='Measure context and costs, not fit/promote filters. Partitions fixed before grouped output, after previous aggregate results already known.',
      quote_collection='All33 decisions,61seconds backward each. Existing explicit FivePercentOnline-Real terminal, no trading or credential changes. Read-only broker access; no paid API.',
      quote_quality='Last quote at or before decision age<=5seconds, positive finite noncrossed bid/ask; previous-minute bid OHLC within2 broker ticks of canonical M1. Inherited UTC+2/3 broker mapping; match is consistency check, not independent clock proof.',
      pnl='Read unchanged modeled reference at .2/.5/.9/1.5pip; actual decision snapshots never retroactively substitute for lifecycle bid/ask. No missing cost imputation.',
      uncertainty='10000 London-day cluster resamples;95% percentile CI mean modeled R per accepted setup, only if>=5 distinct days. Exploratory, no multiplicity correction, not causal evidence.',
      seed=20261024,promotion=False,
      source_outcomes_sha256=sha(source),local_hashes={p.name:sha(p) for p in local},
      price_hashes={str((ROOT/f'data/full_2025_study/prices_utc/{s}_1m.csv.gz').relative_to(ROOT)):sha(ROOT/f'data/full_2025_study/prices_utc/{s}_1m.csv.gz') for s in SYMBOLS}))


def verify():
    p=json.loads((HERE/'protocol_v2.json' if (HERE/'protocol_v2.json').exists() else HERE/'protocol.json').read_text(encoding='utf-8'))
    for n,h in p['local_hashes'].items():
        if sha(HERE/n)!=h:raise RuntimeError('Frozen local mismatch:'+n)
    for n,h in p['price_hashes'].items():
        if sha(ROOT/n)!=h:raise RuntimeError('Frozen price mismatch:'+n)


def stats(rows,seed=20261024):
    closed=[r for r in rows if r['status']=='CLOSED' and r['filled_at']]
    returns=[r['net_r'] for r in closed];gains=sum(x for x in returns if x>0);losses=-sum(x for x in returns if x<0)
    days=sorted({r['day'] for r in rows});ci=None
    if len(days)>=5:
        totals=np.array([sum(r['net_r'] for r in rows if r['day']==d and r['net_r'] is not None) for d in days])
        counts=np.array([sum(r['day']==d for r in rows) for d in days])
        selected=np.random.default_rng(seed).integers(0,len(days),size=(10000,len(days)))
        samples=totals[selected].sum(axis=1)/counts[selected].sum(axis=1)
        ci=[float(v) for v in np.quantile(samples,[.025,.975])]
    return dict(setups=len(rows),fills=len(closed),days=len(days),net_r=sum(returns),
      pf=gains/losses if losses else None,mean_r_per_setup=sum(returns)/len(rows) if rows else None,
      exploratory_day_bootstrap95_mean_setup_r=ci,
      monthly={m:dict(setups=sum(r['month']==m for r in rows),fills=sum(r['month']==m for r in closed),net_r=sum(r['net_r'] for r in closed if r['month']==m)) for m in ['2025-01','2025-11']})


def run():
    verify();setups=json.loads((HERE/'setups_frozen.json').read_text(encoding='utf-8'))
    references=json.loads((HERE/'reference_frozen.json').read_text(encoding='utf-8'))
    manifest_path=HERE/'decision_quote_manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else dict(files={})
    locked=HERE/'decision_quote_manifest_frozen.json'
    if locked.exists() and json.loads(locked.read_text(encoding='utf-8'))!=manifest:raise RuntimeError('Decision quote manifest changed; preserve current study')
    if not locked.exists():write(locked,manifest)
    frames={s:pd.read_csv(ROOT/f'data/full_2025_study/prices_utc/{s}_1m.csv.gz',parse_dates=['datetime']) for s in SYMBOLS}
    measurements=[];enriched=[]
    for i,c in enumerate(setups):
        s=c['signal'];symbol=s['symbol'].replace('/','');meta=manifest['files'].get(str(i))
        if meta is None or meta['status']!='CAPTURED':measurement=dict(status='UNPRICED',reason='MISSING_DECISION_TAPE')
        else:
            p=HERE/meta['path']
            if sha(p)!=meta['sha256']:raise RuntimeError('Decision tape hash changed')
            tape=pd.read_parquet(p)
            measurement=decision_measurement(s,c['available_at'],tape,frames[symbol],meta['point'])
        features=context(c);features['cost_group']=measurement.get('cost_group','UNPRICED')
        measurements.append(dict(setup_id=i,symbol=symbol,day=c['day'],features=features,measurement=measurement))
        for r in references:
            if r['setup_id']==i:enriched.append(dict(**r,context=features))
    summaries=[]
    for sp in [.2,.5,.9,1.5]:
        sample=[r for r in enriched if r['spread_pips']==sp]
        summaries.append(dict(spread_pips=sp,family='ALL',group='ALL',**stats(sample)))
        for family in ['timing','htf','asia','cost_group']:
            for group in sorted({r['context'][family] for r in sample}):
                summaries.append(dict(spread_pips=sp,family=family,group=group,**stats([r for r in sample if r['context'][family]==group])))
    priced=[m['measurement'] for m in measurements if m['measurement']['status']=='OBSERVED_ONLY']
    overview=dict(decisions=len(measurements),priced=len(priced),unpriced=len(measurements)-len(priced),
      unpriced_reasons={reason:sum(m['measurement'].get('reason')==reason for m in measurements) for reason in sorted({m['measurement']['reason'] for m in measurements if m['measurement']['status']!='OBSERVED_ONLY'})},
      spread_pips_median=float(np.median([m['spread_pips'] for m in priced])) if priced else None,
      spread_pips_p95=float(np.quantile([m['spread_pips'] for m in priced],.95)) if priced else None,
      zero_spread_decisions=sum(m['spread_pips']==0 for m in priced),
      median_assumed_cost_budget_r=float(np.median([m['total_cost_budget_r'] for m in priced])) if priced else None,
      caveat='Actual decision quote snapshots only; grouped PNL remains prior assumed-spread lifecycle replay, not realized broker net profit.')
    verify();write(HERE/'measurements.json',measurements);write(HERE/'group_results.json',summaries);write(HERE/'quote_summary.json',overview)
    print(json.dumps(overview,indent=2));print(json.dumps([r for r in summaries if r['spread_pips']==.5],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','verify']);a=p.parse_args()
    {'freeze':freeze,'run':run,'verify':verify}[a.action]()
