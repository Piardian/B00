"""Preserve the original broker-M15 bid-tick volume, not all ask updates.
Revision is an implementation-consistency audit, not a new volume threshold.
Original quote-event-count results remain intact and must be disclosed.
"""
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
import json,hashlib
import numpy as np
import pandas as pd
import quote_engine
from run_validation import summary
from collect_mt5 import SYMBOLS,schedule
BASE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def native_opening(tape,date):
    if 'flags' not in tape:raise ValueError('Original MT5 BID flag required')
    bid_updates=tape[(tape['flags'].astype('int64')&2)!=0]
    return quote_engine_opening(bid_updates,date)
quote_engine_opening=quote_engine.opening

def main():
    manifest=json.loads((BASE/'quote_manifest_frozen.json').read_text())
    declaration=dict(revision='NATIVE_M15_BID_VOLUME_CONSISTENCY_V2',
        reason='Prior classic model used nativeM15bidtickvolume; quoteeventcount also countsask-onlyupdates. ProbeFeb03EURUSD native5136 equals BIDflagcount5136 vs5703allquotes; preserveoriginalfeaturesemantics',
        method='Use onlyMT5BIDflag2updates for first15minuteOHLCandvolume;actualexecutionstillallbidaskquotepairs;14daymeanand>=1unchanged;no rule/threshold/cost/date/symbol tuning',
        disclosure='Original quoteevent-volume results already examined; not a pristine untouched study. Bothversionsretained andreported',
        files={str(p):sha(p) for p in [Path(__file__),BASE/'quote_engine.py',BASE/'run_validation.py']},quote_manifest_sha256=sha(BASE/'quote_manifest_frozen.json'))
    plan=BASE/'native_volume_protocol.json'
    if plan.exists():raise RuntimeError('Do not overwrite implementation audit')
    plan.write_text(json.dumps(dict(at_utc=datetime.now(timezone.utc).isoformat(),declaration=declaration),indent=2))
    original=json.loads((BASE/'outcomes.json').read_text());lookup={(x['symbol'],x['date'],x['scenario']):x for x in original}
    features=[];rows=[];changed=[]
    for symbol in SYMBOLS:
        volumes=[]
        for day,warmup in schedule():
            meta=manifest['files'][f'{symbol}_{day}'];f=pd.read_parquet(meta['path']);f.time=pd.to_datetime(f.time,utc=True)
            native=native_opening(f,day);prior=quote_engine_opening(f,day)
            if not warmup:
                rvol=native['volume']/np.mean(volumes[-14:]);diff=any(native[k]!=prior[k] for k in ['high','low','direction'])
                features.append(dict(symbol=symbol,date=day,native_volume=native['volume'],quote_events=prior['volume'],rvol=float(rvol),price_geometry_changed=diff))
                if diff:changed.append(dict(symbol=symbol,date=day))
                for name,m,floor in [('OBSERVED_QUOTES_1x',1.,0.),('COST_STRESS_1.5x',1.5,0.),('COST_STRESS_2x',2.,0.),('MIN_SPREAD_1PIP',1.,1.)]:
                    if diff:
                        with patch.object(quote_engine,'opening',native_opening):outcome=quote_engine.replay(f,symbol,day,m,floor)
                    else:outcome=lookup[symbol,day,name]['outcome']
                    rows.append(dict(symbol=symbol,date=day,rvol=float(rvol),scenario=name,outcome=outcome))
            volumes.append(native['volume'])
        print('Native-feature audit',symbol,'done',flush=True)
    results={cohort:{scenario:summary([r for r in rows if r['scenario']==scenario and(cohort=='CLASSIC_ALL' or r['rvol']>=1)]) for scenario in sorted({r['scenario'] for r in rows})} for cohort in ['CLASSIC_ALL','CLASSIC_RVOL_GE1']}
    for path,digest in declaration['files'].items():assert sha(Path(path))==digest
    (BASE/'native_results.json').write_text(json.dumps(dict(results=results,geometry_changed_days=changed,status='NATIVE_FEATURE_CONSISTENCY_REPLAY'),indent=2))
    (BASE/'native_outcomes.json').write_text(json.dumps(rows,indent=2));pd.DataFrame(features).to_csv(BASE/'native_feature_audit.csv',index=False)
if __name__=='__main__':main()
