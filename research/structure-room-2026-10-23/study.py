"""Finite structural-entry/cost/room experiments. No live imports or network."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from execution import replay
from features import structural_entry, opposing_room, cost_record

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SYMBOLS=['EURUSD','GBPUSD','USDJPY','USDCAD','USDCHF','NZDUSD']
SPREADS=[.2,.5,.9,1.5]
VARIANTS=['reference','reference_room','m1_structure','m1_structure_cost','m1_structure_cost_room']
COST_CAP=.20


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')


def freeze():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already frozen')
    paths=list(HERE.glob('*.py'))+[HERE/'setups_frozen.json']
    paths += [ROOT/f'data/full_2025_study/prices_utc/{s}_{tf}.csv.gz' for s in SYMBOLS for tf in ['1m','1h']]
    write(HERE/'protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),
      sample='33 first-daily normalized opening setups imported unchanged from prior study; January/November 2025 only. No fresh scan or true OOS.',
      variants=VARIANTS,spreads_pips=SPREADS,primary_spread_pips=.5,cost_budget_cap_r=COST_CAP,
      costs='Synthetic ask from bid M1; USD4/100k round trip; .2 pip exit slip and additional .2 pip adverse entry slip for market variant. Assumptions, not certified 2025 broker fees.',
      structural_entry='Original-level penetration and reaction close; later M1 close beyond that reaction high/low; enter only next open at ask+.2pip LONG / bid-.2pip SHORT. Stop beyond reaction low LONG / ask-equivalent high SHORT by one tick. Earlier structural break cancels an unplaced order.',
      target='New entry/stop risk; half TP1 >=1.2R and half TP2 >=2R outward tick rounding. Fill-bar reaction exits retained; same reference exit engine. No fill-bar targets. London16:30 flat.',
      room='Nearest opposing strictly confirmed 2-left/2-right H1 pivot in last100 completed bars, five-bar pivot window must be continuous. TP1 must be at least one tick before pivot. Unknown room rejects only room variants.',
      cost='At signal decision and executable entry open, diagnostic spread+slippage+commission divided by initial stop risk. Limit budget has exit .2pip; market budget has total .4pip. Budget is not subtracted again from replay PNL.',
      comparison='Same first daily setup retained even when filter rejects it. No replacement setup. Separate incremental variants isolate room and cost. No symbol/month optimization.',
      selection_guard='Pivot completion <= decision time; only next open used to choose market entry, never entry-bar high/low/close. Missing M1 unresolved, never profitable by default.',
      decision='No live promotion. Positive aggregate alone insufficient: November and adverse spread must also be positive with resolved records; sparse samples and zero trades never establish edge.',
      limitations=['Setup-only; no macro/news/shared portfolio/SFP priority','R quote-risk normalized, not account return','Costs synthetic, no historical ask','Previously observed data; hypotheses informed by earlier research'],
      hashes={str(p.relative_to(ROOT)):sha(p) for p in paths}))


def verify():
    p=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    for name,expected in p['hashes'].items():
        if sha(ROOT/name)!=expected:raise RuntimeError('Frozen hash mismatch: '+name)


def skipped(reason,status='SKIPPED'):
    return dict(status=status,reason=reason,filled_at=None,net_r=None if status=='UNRESOLVED' else 0.,gross_r=0.,commission_r=0.)


def stats(rows):
    filled=[r for r in rows if r['filled_at']]
    resolved=[r for r in filled if r['status']=='CLOSED']
    values=[r['net_r'] for r in resolved];gain=sum(v for v in values if v>0);loss=-sum(v for v in values if v<0)
    return dict(setups=len(rows),fills=len(filled),closed_fills=len(resolved),unresolved=sum(r['status']=='UNRESOLVED' for r in rows),
      net_r=sum(values),pf=gain/loss if loss else None,wins=sum(v>0 for v in values),
      monthly={m:dict(setups=sum(r['month']==m for r in rows),fills=sum(r['month']==m for r in filled),net_r=sum(r['net_r'] for r in resolved if r['month']==m)) for m in ['2025-01','2025-11']},
      reasons={reason:sum(r['reason']==reason for r in rows) for reason in sorted({r['reason'] for r in rows})})


def run():
    verify();setups=json.loads((HERE/'setups_frozen.json').read_text(encoding='utf-8'))
    frames={}
    for s in SYMBOLS:
        for tf in ['1m','1h']:
            f=pd.read_csv(ROOT/f'data/full_2025_study/prices_utc/{s}_{tf}.csv.gz',parse_dates=['datetime'])
            if f.datetime.duplicated().any() or not f.datetime.is_monotonic_increasing:raise ValueError('Invalid chronology')
            frames[s,tf]=f
    outcomes=[];observations=[]
    for i,c in enumerate(setups):
        original=c['signal'];symbol=original['symbol'].replace('/','');m1=frames[symbol,'1m'];h1=frames[symbol,'1h'];at=pd.Timestamp(c['available_at'])
        for spread in SPREADS:
            prepared=structural_entry(original,at,m1,spread)
            feature_cache={}
            for variant in VARIANTS:
                market=variant.startswith('m1_')
                if market and prepared['status']!='READY':
                    outcome=skipped(prepared['reason'],prepared['status']);features=None
                else:
                    s=prepared['signal'] if market else original
                    decision=pd.Timestamp(prepared['at']) if market else at
                    quotes=m1[m1.datetime==decision]
                    if quotes.empty:
                        outcome=skipped('MISSING_DECISION_QUOTE','UNRESOLVED');features=None
                    else:
                        cachekey='market' if market else 'limit'
                        if cachekey not in feature_cache:
                            cost=cost_record(s,float(quotes.iloc[0]['open']),spread,decision,market=market)
                            room=opposing_room(s,h1,decision)
                            feature_cache[cachekey]=dict(cost=cost,room=room,decision_at=str(decision),signal=s)
                            observations.append(dict(setup_id=i,symbol=symbol,day=c['day'],spread_pips=spread,entry_kind=cachekey,**feature_cache[cachekey]))
                        features=feature_cache[cachekey]
                        if 'cost' in variant and features['cost']['total_cost_budget_r']>COST_CAP:
                            outcome=skipped('COST_BUDGET_EXCEEDS_0_20R')
                        elif 'room' in variant and features['room']['status']=='UNKNOWN':
                            outcome=skipped('UNKNOWN_TARGET_ROOM')
                        elif 'room' in variant and not features['room']['tp1_has_room']:
                            outcome=skipped('OPPOSING_PIVOT_BEFORE_TP1')
                        else:
                            outcome=replay(s,decision,m1,'passive',spread_pips=spread,market_entry=market)
                outcomes.append(dict(setup_id=i,symbol=symbol,day=c['day'],month=c['day'][:7],variant=variant,spread_pips=spread,
                                     structural_preparation=prepared if market else None,features=features,**outcome))
    summaries=[dict(variant=v,spread_pips=sp,**stats([r for r in outcomes if r['variant']==v and r['spread_pips']==sp])) for sp in SPREADS for v in VARIANTS]
    primary=next(r for r in summaries if r['variant']=='reference' and r['spread_pips']==.5)
    if abs(primary['net_r']-5.190387221887223)>1e-9:raise RuntimeError('Reference drift from previous study')
    verify()
    write(HERE/'outcomes.json',outcomes);write(HERE/'summary.json',summaries)
    with (HERE/'cost_room_observations.jsonl').open('w',encoding='utf-8') as f:
        for r in observations:f.write(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps([r for r in summaries if r['spread_pips'] in [.5,1.5]],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','verify']);args=p.parse_args()
    {'freeze':freeze,'run':run,'verify':verify}[args.action]()
