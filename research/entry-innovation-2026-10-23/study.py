"""Finite, frozen, research-only comparison. No broker/API imports."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import pandas as pd
from quote_engine import replay
from price_rules import normalize_targets

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
POLICIES=['passive','reaction_retest','break_retest']
SPREADS=[.2,.5,.9,1.5]
SYMBOLS=['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD']


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')


def freeze():
    protocol_path=HERE/'protocol.json'
    if protocol_path.exists():raise RuntimeError('Protocol already exists; preserve frozen run')
    shutil.copy2(ROOT/'research/london-opening-only-2026-10-23/candidate_audit.json',HERE/'candidates_frozen.json')
    paths=[HERE/n for n in ['study.py','quote_engine.py','price_rules.py','test_quote_engine.py','candidates_frozen.json']]
    paths += [ROOT/f'data/full_2025_study/prices_utc/{s}_1m.csv.gz' for s in SYMBOLS]
    protocol=dict(version=1,frozen_at=str(pd.Timestamp.now(tz='UTC')),policies=POLICIES,
      spreads_pips=SPREADS,primary_spread_pips=.5,market_exit_slippage_pips=.2,commission_usd_roundtrip_per_100k=4,
      candidates='Existing opening-only audit; first normalized setup per symbol/London date, chosen before outcomes; consumes date even if no order',
      target_correction='Outward tick rounding to minimum 1.2R/2R; original entry and stop unchanged',
      quotes='Canonical bid M1 plus assumed constant ask spread. Strict one tick penetration. Not historical spread calibration.',
      lifecycle='All policies retain adverse fill-bar reaction exit, stop-first, no fill-bar TP. Half at TP1; BE then 1.5R activation for .75R trailing, subsequent bars only.',
      new_exit='Flatten at London 16:30 M1 open; pending expires min(noon, availability+4h). New research contract, not original production lifecycle.',
      primary_cohort='All first daily setups; paired identical candidate set across policies and costs',
      secondary_cohort='Predefined HTF-aligned and engine-session-open among same first daily setups',
      evaluation='January/June 2025 development, November retrospective check; all previously observed, no genuine OOS claim',
      missing_data='Any missing minute before terminal outcome unresolved; no profit assigned; closed sums not valid whole basket if unresolved',
      limitations=['No macro/news gates, shared risk, funding or swap; new intraday flatten avoids overnight swap','Independent candidate research, not full-bot or executable portfolio','Constant spread assumptions and 1m ambiguity, not broker tick fills','No parameter search beyond predeclared policies and cost sensitivity'],
      decision='No live promotion. Candidate for next separate validation only if positive at primary and adverse costs with no unresolved cases and positive retrospective month; never call small N edge proof.',
      hashes={str(p.relative_to(ROOT)):digest(p) for p in paths})
    write(protocol_path,protocol)


def stats(rows):
    filled=[r for r in rows if r['filled_at']]
    resolved=[r for r in filled if r['status']=='CLOSED']
    values=[r['net_r'] for r in resolved]
    gains=sum(v for v in values if v>0);loss=-sum(v for v in values if v<0)
    return dict(setups=len(rows),fills=len(filled),closed_fills=len(resolved),unresolved=sum(r['status']!='CLOSED' for r in rows),
      net_r=sum(values),gross_r=sum(r['gross_r'] for r in resolved),commission_r=sum(r['commission_r'] for r in resolved),
      pf=gains/loss if loss else None,wins=sum(v>0 for v in values),
      reasons={reason:sum(r['reason']==reason for r in rows) for reason in sorted({r['reason'] for r in rows})},
      monthly={m:sum(r['net_r'] for r in resolved if r['month']==m) for m in ['2025-01','2025-06','2025-11']})


def run():
    protocol=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    for name,sha in protocol['hashes'].items():
        if digest(ROOT/name)!=sha:raise RuntimeError('Frozen hash changed: '+name)
    candidates=json.loads((HERE/'candidates_frozen.json').read_text(encoding='utf-8'))
    selected=[];used=set()
    for c in sorted(candidates,key=lambda c:(c['available_at'],c['signal']['symbol'])):
        s=c['signal'];symbol=s['symbol'].replace('/','')
        day=str(pd.Timestamp(c['available_at']).tz_convert('Europe/London').date())
        key=(symbol,day)
        if key in used:continue
        s=normalize_targets(s,.001 if symbol=='USDJPY' else .00001)
        used.add(key);selected.append({**c,'signal':s,'day':day})
    write(HERE/'selected_setups.json',selected)
    prices={s:pd.read_csv(ROOT/f'data/full_2025_study/prices_utc/{s}_1m.csv.gz',parse_dates=['datetime']) for s in SYMBOLS}
    outcomes=[]
    for c in selected:
        s=c['signal'];symbol=s['symbol'].replace('/','')
        for spread in SPREADS:
            for policy in POLICIES:
                r=replay(s,c['available_at'],prices[symbol],policy,spread_pips=spread)
                outcomes.append(dict(**r,symbol=symbol,day=c['day'],month=c['day'][:7],policy=policy,spread_pips=spread,
                    secondary=bool(c['htf_aligned'] and c['engine_session_open']),available_at=c['available_at']))
    summary=[]
    for cohort in ['core','htf_session']:
        for spread in SPREADS:
            for policy in POLICIES:
                group=[r for r in outcomes if r['policy']==policy and r['spread_pips']==spread and (cohort=='core' or r['secondary'])]
                summary.append(dict(cohort=cohort,spread_pips=spread,policy=policy,**stats(group)))
    write(HERE/'outcomes.json',outcomes);write(HERE/'summary.json',summary)
    print(json.dumps([r for r in summary if r['cohort']=='core'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','run']);args=parser.parse_args()
    freeze() if args.action=='freeze' else run()
