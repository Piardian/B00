"""Second declared stage: isolate narrower stop from later market entry.

Declared after stage-one results. Not independent confirmation or new OOS.
Same confirmation eligibility and times; retain original stop instead of M1 stop.
"""
import argparse
import json
import pandas as pd
from study import HERE,ROOT,SYMBOLS,SPREADS,sha,write,verify,stats,skipped
from features import structural_entry,cost_record
from price_rules import normalize_targets
from execution import replay


def freeze():
    verify()
    if (HERE/'stop_control_protocol.json').exists():raise RuntimeError('Already frozen')
    paths=[HERE/'stop_control.py',HERE/'protocol.json',HERE/'summary.json',HERE/'setups_frozen.json']
    write(HERE/'stop_control_protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),
      stage='Explicit post-stage-one diagnosis; new hypotheses, not independent validation.',
      variants=['m1_original_stop','m1_original_stop_cost'],spreads_pips=SPREADS,
      rule='Reuse identical M1 structural confirmation eligibility and market entry time/price; only replace stop by original ORB stop. Recompute targets >=1.2/2R from new entry/risk; keep common exits and costs.',
      cost_cap_r=.20,comparison='Matched timing control isolates stop choice among ready setups. Same first daily setup; no replacement. Retains stage-one pre-entry M1 invalidation.',
      hashes={str(p.relative_to(ROOT)):sha(p) for p in paths}))


def run():
    verify();protocol=json.loads((HERE/'stop_control_protocol.json').read_text(encoding='utf-8'))
    for name,expected in protocol['hashes'].items():
        if sha(ROOT/name)!=expected:raise RuntimeError('Frozen control mismatch: '+name)
    setups=json.loads((HERE/'setups_frozen.json').read_text(encoding='utf-8'))
    frames={s:pd.read_csv(ROOT/f'data/full_2025_study/prices_utc/{s}_1m.csv.gz',parse_dates=['datetime']) for s in SYMBOLS}
    outcomes=[]
    for i,c in enumerate(setups):
        original=c['signal'];symbol=original['symbol'].replace('/','');bars=frames[symbol]
        for spread in SPREADS:
            prepared=structural_entry(original,c['available_at'],bars,spread)
            for variant in protocol['variants']:
                observation=None
                if prepared['status']!='READY':out=skipped(prepared['reason'],prepared['status'])
                else:
                    s=dict(prepared['signal']);s['stop_loss']=original['stop_loss']
                    sign=1 if s['direction']=='LONG' else -1;risk=sign*(s['entry']-s['stop_loss'])
                    if risk<=0:out=skipped('ORIGINAL_STOP_INVALID_AT_NEW_ENTRY')
                    else:
                        s['tp1']=s['entry']+sign*1.2*risk;s['tp2']=s['entry']+sign*2*risk
                        s=normalize_targets(s,.001 if symbol=='USDJPY' else .00001)
                        observation=cost_record(s,prepared['bid'],spread,pd.Timestamp(prepared['at']),market=True)
                        if variant.endswith('_cost') and observation['total_cost_budget_r']>.20:out=skipped('COST_BUDGET_EXCEEDS_0_20R')
                        else:out=replay(s,prepared['at'],bars,'passive',spread_pips=spread,market_entry=True)
                outcomes.append(dict(setup_id=i,symbol=symbol,day=c['day'],month=c['day'][:7],variant=variant,spread_pips=spread,cost=observation,**out))
    summaries=[dict(variant=v,spread_pips=sp,**stats([r for r in outcomes if r['variant']==v and r['spread_pips']==sp])) for sp in SPREADS for v in protocol['variants']]
    write(HERE/'stop_control_outcomes.json',outcomes);write(HERE/'stop_control_summary.json',summaries)
    print(json.dumps([r for r in summaries if r['spread_pips'] in [.5,1.5]],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args()
    freeze() if a.action=='freeze' else run()
