"""Independent price-clock QA, never choose a shift from trading profit."""
from pathlib import Path
import json,hashlib
import pandas as pd
import numpy as np
BASE=Path(__file__).resolve().parent
REFERENCE=Path('C:/Users/piard/Desktop/MegalordProject/audit/daytrade-session-2026-10-22/evidence/twelvedata_EURUSD_15m.csv.gz')
def main():
    plan=dict(expected_normalized_shift_hours=0,min_strong_days=20,strong_corr=.7,min_margin=.15,reference_sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),scope='EURUSDcrossfeedclockQAonly;not strategyoutcome')
    (BASE/'clock_qa_plan.json').write_text(json.dumps(plan,indent=2))
    ref=pd.read_csv(REFERENCE);ref.index=pd.to_datetime(ref.datetime,utc=True)
    reference=np.log(ref.close/ref.open).rename('reference');rows=[];tape_hashes={}
    for p in sorted((BASE/'tapes').glob('EURUSD_2025-0[23]-*.parquet')):
        f=pd.read_parquet(p);f=f.set_index('time')
        f=f[f.index.tz_convert('Europe/London').hour<16]
        bars=f.bid.resample('15min').ohlc().dropna();value=np.log(bars.close/bars.open)
        tape_hashes[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
        for shift in [-3,-2,-1,0,1,2,3]:
            x=value.copy();x.index=x.index+pd.Timedelta(hours=shift)
            joined=pd.concat([x.rename('broker'),reference],axis=1).dropna()
            if len(joined)>=16:rows.append(dict(date=p.stem[-10:],shift=shift,n=len(joined),corr=float(joined.broker.corr(joined.reference))))
    scores=pd.DataFrame(rows);scores.to_csv(BASE/'clock_scores.csv',index=False);strong=[]
    if len(scores):
        for day,g in scores.groupby('date'):
            g=g.sort_values('corr',ascending=False)
            if len(g)>1 and g.iloc[0]['corr']>=.7 and g.iloc[0]['corr']-g.iloc[1]['corr']>=.15:
                strong.append(dict(date=day,shift=int(g.iloc[0]['shift']),corr=float(g.iloc[0]['corr'])))
    conflicts=[x for x in strong if x['shift']!=0]
    passed=len(strong)>=20 and not conflicts
    result=dict(passed=passed,strong_days=len(strong),conflicts=conflicts,winners=strong,tape_hashes=tape_hashes,plan=plan)
    (BASE/'clock_qa.json').write_text(json.dumps(result,indent=2))
    print('Clock QA:',passed,'strong_days',len(strong),'conflicts',len(conflicts))
    if not passed:raise SystemExit(1)
if __name__=='__main__':main()
