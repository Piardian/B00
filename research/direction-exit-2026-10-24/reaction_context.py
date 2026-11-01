"""Second-stage descriptive conditions for early exit benefit. No rule fitting."""
import argparse,json
import pandas as pd
from study import HERE,ROOT,sha,write,verify,ci_day
from direction import score


def freeze():
    verify()
    if (HERE/'context_protocol.json').exists():raise RuntimeError('Already frozen')
    write(HERE/'context_protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),
      stage='Declared after aggregate ablation/direction results. Descriptive, not independent validation.',
      sample='All reference reaction exits, at.5 and1.5pip, both periods; no choice by winning/losing later.',
      features={'close_vs_entry':'Executable fill-bar close mark-to-entry >=0R versus<0R, known at exit decision before slip/fee',
                'wait':'Time from original availability to filled M1 start <=15minutes versus>15minutes',
                'asia':'Existing <=.35 versus>.35 ratio for context only; failed filter not revived'},
      benefit='Reference net minus never-exit net, paired same setup/spread; positive means early exit helped. Not an entry signal or new strategy PNL.',
      after_fill_direction='Use fixed60min diagnostic from nextM1open after reference fill minute, not unknown intraminute fill order. Includes trades already exited by then; descriptive price path, not new orders.',
      hashes={p.name:sha(p) for p in [HERE/'reaction_context.py',HERE/'outcomes.json',HERE/'cases_frozen.json',HERE/'direction.py']}))


def run():
    plan=verify();lock=json.loads((HERE/'context_protocol.json').read_text())
    for n,h in lock['hashes'].items():
        if sha(HERE/n)!=h:raise RuntimeError('Frozen context changed')
    cases={c['case_id']:c for c in json.loads((HERE/'cases_frozen.json').read_text())}
    outcomes=json.loads((HERE/'outcomes.json').read_text());index={(r['case_id'],r['spread_pips'],r['mode']):r for r in outcomes}
    frames={k:pd.read_parquet(ROOT/v['path']) if v['path'].endswith('parquet') else pd.read_csv(ROOT/v['path'],parse_dates=['datetime']) for k,v in plan['prices'].items()}
    records=[];after_fills=[]
    for original in outcomes:
        if original['mode']!='always':continue
        c=cases[original['case_id']];s=c['signal'];f=frames[c['source']+'_'+c['symbol']]
        if original['spread_pips']==.5 and original['filled_at']:
            at=pd.Timestamp(original['filled_at'])+pd.Timedelta(minutes=1)
            after_fills.append(dict(case_id=c['case_id'],source=c['source'],day=c['day'],**score(s,at,f)))
        if original['spread_pips'] not in [.5,1.5] or original['reason']!='REACTION_EXIT':continue
        bar=f[f.datetime==pd.Timestamp(original['filled_at'])].iloc[0]
        sign=1 if s['direction']=='LONG' else -1;pip=.01 if c['symbol'].endswith('JPY') else .0001
        executable_close=float(bar['close'])+(original['spread_pips']*pip if sign==-1 else 0)
        close_r=sign*(executable_close-s['entry'])/abs(s['entry']-s['stop_loss'])
        wait=(pd.Timestamp(original['filled_at'])-pd.Timestamp(c['available_at'])).total_seconds()/60
        alt=index[c['case_id'],original['spread_pips'],'never']
        if alt['filled_at']!=original['filled_at']:raise RuntimeError('Unmatched fills')
        records.append(dict(case_id=c['case_id'],source=c['source'],day=c['day'],spread_pips=original['spread_pips'],
                            close_r=close_r,wait_minutes=wait,
                            close_vs_entry='NONNEGATIVE_CLOSE' if close_r>=0 else 'NEGATIVE_CLOSE',
                            wait='LE15MIN' if wait<=15 else 'GT15MIN',
                            asia='LE0_35' if s['london_context']['asia_atr_ratio']<=.35 else 'GT0_35',
                            early_exit_benefit_r=original['net_r']-alt['net_r']))
    groups=[];directions=[]
    for source in ['ALL','DISCOVERY','RECHECK']:
        for spread in [.5,1.5]:
            sample=[r for r in records if r['spread_pips']==spread and (source=='ALL' or r['source']==source)]
            for feature in ['close_vs_entry','wait','asia']:
                for group in sorted({r[feature] for r in sample}):
                    rows=[r for r in sample if r[feature]==group];total=sum(r['early_exit_benefit_r'] for r in rows)
                    groups.append(dict(source=source,spread_pips=spread,feature=feature,group=group,n=len(rows),total_early_exit_benefit_r=total,
                      mean_benefit_r=total/len(rows),helped=sum(r['early_exit_benefit_r']>1e-9 for r in rows),hurt=sum(r['early_exit_benefit_r']< -1e-9 for r in rows),
                      mean_benefit_day95=ci_day(rows,lambda r:r['early_exit_benefit_r'])))
        rows=[r for r in after_fills if r['status']=='MEASURED' and (source=='ALL' or r['source']==source)]
        directions.append(dict(source=source,measured=len(rows),positive=sum(r['original_score_r']>0 for r in rows),
          mean_score_r=sum(r['original_score_r'] for r in rows)/len(rows) if rows else None,
          mean_day95=ci_day(rows,lambda r:r['original_score_r'])))
    write(HERE/'reaction_context_records.json',records);write(HERE/'reaction_context_groups.json',groups)
    write(HERE/'after_fill_direction_records.json',after_fills);write(HERE/'after_fill_direction_summary.json',directions)
    print(json.dumps([r for r in groups if r['source']=='RECHECK'],indent=2));print(json.dumps(directions,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args()
    freeze() if a.action=='freeze' else run()
