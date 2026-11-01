"""Hourly independent clock check. Strategy quotes remain only The5ers."""
from pathlib import Path
import hashlib,json
import pandas as pd
import numpy as np
BASE=Path(__file__).resolve().parent
REF=BASE/'clock_reference_EURUSD_Yahoo_H1.parquet'
def main():
    plan=dict(reference='Yahoo EURUSD=X H1 via yfinance; clock comparison ONLY, not strategy prices',reference_sha256=hashlib.sha256(REF.read_bytes()).hexdigest(),
        expected_shift=0,shift_hours=list(range(-3,4)),min_joined_hours_day=6,strong_corr=.7,min_margin=.15,min_strong_days=20,
        reason='Prior independentM15archive has only2overlappingvalidationdays; that coverage gate failed, not a detected clock mismatch')
    (BASE/'clock_h1_plan.json').write_text(json.dumps(plan,indent=2))
    ref=pd.read_parquet(REF);reference=np.log(ref.Close/ref.Open);reference.index=reference.index.tz_convert('UTC')
    rows=[];all_pairs=[]
    for p in sorted((BASE/'tapes').glob('EURUSD_2025-0[23]-*.parquet')):
        f=pd.read_parquet(p).set_index('time');f=f[f.index.tz_convert('Europe/London').hour<16]
        bars=f.bid.resample('h').ohlc().dropna();values=np.log(bars.close/bars.open)
        for shift in plan['shift_hours']:
            x=values.copy();x.index+=pd.Timedelta(hours=shift)
            joined=pd.concat([x.rename('broker'),reference.rename('reference')],axis=1,sort=True).dropna()
            if len(joined)>=6:
                rows.append(dict(date=p.stem[-10:],shift=shift,n=len(joined),corr=float(joined.broker.corr(joined.reference))))
                if shift==0:all_pairs.append(joined)
    scores=pd.DataFrame(rows);scores.to_csv(BASE/'clock_h1_scores.csv',index=False);strong=[]
    for day,g in scores.groupby('date'):
        g=g.sort_values('corr',ascending=False)
        if g.iloc[0]['corr']>=.7 and g.iloc[0]['corr']-g.iloc[1]['corr']>=.15:
            strong.append(dict(date=day,shift=int(g.iloc[0]['shift']),corr=float(g.iloc[0]['corr'])))
    conflicts=[x for x in strong if x['shift']!=0];pooled=pd.concat(all_pairs)
    result=dict(passed=len(strong)>=20 and not conflicts,strong_days=len(strong),conflicts=conflicts,winners=strong,pooled_corr=float(pooled.broker.corr(pooled.reference)),plan=plan)
    (BASE/'clock_h1_qa.json').write_text(json.dumps(result,indent=2));print('H1 Clock QA',result['passed'],'strong_days',len(strong),'conflicts',len(conflicts),'pooled_corr',result['pooled_corr'])
    if not result['passed']:raise SystemExit(1)
if __name__=='__main__':main()
