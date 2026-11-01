"""Fail-closed validation; no outcomes until the full locked quote set exists."""
from pathlib import Path
import json,hashlib
import pandas as pd
import numpy as np
from protocol import freeze
from collect_mt5 import SYMBOLS,schedule
from quote_engine import replay,opening
BASE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def summary(rows):
    closed=[x for x in rows if x['outcome']['status']=='CLOSED'];values=np.array([x['outcome']['net_r'] for x in closed])
    loss=-values[values<0].sum();calendar=pd.DatetimeIndex([d for m in ['2025-02','2025-03'] for d in pd.bdate_range(m+'-01',pd.Timestamp(m+'-01')+pd.offsets.MonthEnd(0))])
    daily=pd.Series(0.,index=calendar)
    for x in closed:daily.loc[pd.Timestamp(x['date'])]+=x['outcome']['net_r']
    rng=np.random.default_rng(173);n=len(daily);boot=[]
    for _ in range(10000):
        starts=rng.integers(0,n,size=(n+4)//5);ix=((starts[:,None]+np.arange(5))%n).ravel()[:n];boot.append(daily.to_numpy()[ix].sum())
    return dict(fills=len(closed),net_r=float(values.sum()),pf=float(values[values>0].sum()/loss) if loss else None,
        by_month={m:float(sum(x['outcome']['net_r'] for x in closed if x['date'][:7]==m)) for m in ['2025-02','2025-03']},
        block_total_ci95=np.quantile(boot,[.025,.975]).tolist(),
        statuses=pd.Series([x['outcome']['status'] for x in rows]).value_counts().to_dict())

def run():
    freeze();manifest_path=BASE/'quote_manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else dict(files={},complete=False)
    required=[f'{s}_{day}' for s in SYMBOLS for day,warmup in schedule()]
    missing=[k for k in required if k not in manifest['files']]
    if missing or not manifest.get('complete'):
        (BASE/'validation_status.json').write_text(json.dumps(dict(status='BLOCKED_MISSING_REAL_QUOTES',required=len(required),present=len(required)-len(missing),missing=missing,performance_computed=False),indent=2),encoding='utf8')
        print('BLOCKED: missing real quote files',len(missing));return
    if manifest.get('broker_server')!='FivePercentOnline-Real':raise RuntimeError('OnlyThe5ersserverallowed')
    for meta in manifest['files'].values():
        if sha(Path(meta['path']))!=meta['sha256']:raise RuntimeError('Quote input changed')
    lock=BASE/'quote_manifest_frozen.json'
    if lock.exists():
        if json.loads(lock.read_text())!=manifest:raise RuntimeError('Frozen quote manifest changed')
    else:lock.write_text(json.dumps(manifest,indent=2),encoding='utf8')
    rows=[];feature_rows=[]
    for s in SYMBOLS:
        previous=[]
        for day,warmup in schedule():
            f=pd.read_parquet(manifest['files'][f'{s}_{day}']['path']);f.time=pd.to_datetime(f.time,utc=True)
            feat=opening(f,day)
            if not warmup:
                if len(previous)<14:raise RuntimeError('No14daywarmup')
                rvol=feat['volume']/np.mean(previous[-14:]);feature_rows.append(dict(symbol=s,date=day,rvol=float(rvol)))
                for name,m,floor in [('OBSERVED_QUOTES_1x',1.,0.),('COST_STRESS_1.5x',1.5,0.),('COST_STRESS_2x',2.,0.),('MIN_SPREAD_1PIP',1.,1.)]:
                    result=replay(f,s,day,m,floor)
                    rows.append(dict(symbol=s,date=day,rvol=float(rvol),scenario=name,outcome=result))
            previous.append(feat['volume'])
        print(s,'replayed',flush=True)
    complete=not any(x['outcome']['status'] in ['BLOCKED_TAPE_COVERAGE','UNPRICED_OPEN_POSITION'] for x in rows)
    results={cohort:{scenario:summary([x for x in rows if x['scenario']==scenario and(cohort=='CLASSIC_ALL' or x['rvol']>=1)]) for scenario in sorted({x['scenario'] for x in rows})} for cohort in ['CLASSIC_ALL','CLASSIC_RVOL_GE1']}
    p=json.loads((BASE/'protocol_frozen.json').read_text())['declaration']
    for path,digest in p['files'].items():
        if sha(Path(path))!=digest:raise RuntimeError('Frozen source changed')
    (BASE/'results.json').write_text(json.dumps(dict(status='COMPLETE_QUOTE_REPLAY' if complete else 'INCOMPLETE_QUOTE_COVERAGE_KNOWN_SUBTOTALS_ONLY',results=results),indent=2),encoding='utf8')
    (BASE/'outcomes.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
    (BASE/'opening_features.json').write_text(json.dumps(feature_rows,indent=2),encoding='utf8')
    (BASE/'validation_status.json').write_text(json.dumps(dict(status='COMPLETE_QUOTE_REPLAY' if complete else 'INCOMPLETE_QUOTE_COVERAGE',performance_computed=True),indent=2),encoding='utf8')

if __name__=='__main__':run()
