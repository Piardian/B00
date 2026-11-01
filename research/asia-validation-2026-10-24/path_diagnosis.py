"""Post-validation price-path diagnosis. Ex-post labels, never entry features.

No new strategy PNL. Compare initial TP1 and initial stop until fixed16:30.
Same-bar ordering unknown is explicit; fill-bar TP gets no credit.
"""
import argparse,json
import pandas as pd
from study import HERE,write,sha,verify


def path(signal,filled_at,bars,spread_pips=.5):
    start=pd.Timestamp(filled_at);day=start.tz_convert('Europe/London').date()
    end=pd.Timestamp(f'{day} 16:30',tz='Europe/London').tz_convert('UTC')
    long=signal['direction']=='LONG';spread=spread_pips*(.01 if 'JPY' in signal['symbol'] else .0001)
    expected=start
    for b in bars[(bars.datetime>=start)&(bars.datetime<end)].to_dict('records'):
        at=b['datetime']
        if at!=expected:return dict(label='UNKNOWN_MISSING_M1',at=str(expected))
        expected=at+pd.Timedelta(minutes=1)
        high=b['high']+(0 if long else spread);low=b['low']+(0 if long else spread)
        stop=low<=signal['stop_loss'] if long else high>=signal['stop_loss']
        target=high>=signal['tp1'] if long else low<=signal['tp1']
        if at==start:
            if stop:return dict(label='INITIAL_STOP_FIRST',at=str(at),fill_bar_conservative=True)
            continue
        if stop and target:return dict(label='AMBIGUOUS_STOP_TP1_SAME_M1',at=str(at))
        if stop:return dict(label='INITIAL_STOP_FIRST',at=str(at))
        if target:return dict(label='TP1_FIRST',at=str(at))
    if expected<end:return dict(label='UNKNOWN_MISSING_TAIL',at=str(expected))
    return dict(label='NEITHER_BY_FLAT',at=str(end))


def after_exit(signal,closed_at,bars,spread_pips=.5):
    # No fill-bar suppression here: this is the path after the modeled exit.
    start=pd.Timestamp(closed_at);long=signal['direction']=='LONG';day=start.tz_convert('Europe/London').date()
    end=pd.Timestamp(f'{day} 16:30',tz='Europe/London').tz_convert('UTC')
    spread=spread_pips*(.01 if 'JPY' in signal['symbol'] else .0001);expected=start
    for b in bars[(bars.datetime>=start)&(bars.datetime<end)].to_dict('records'):
        at=b['datetime']
        if at!=expected:return dict(label='UNKNOWN_MISSING_M1',at=str(expected))
        expected=at+pd.Timedelta(minutes=1)
        high=b['high']+(0 if long else spread);low=b['low']+(0 if long else spread)
        stop=low<=signal['stop_loss'] if long else high>=signal['stop_loss'];target=high>=signal['tp1'] if long else low<=signal['tp1']
        if stop and target:return dict(label='AMBIGUOUS_STOP_TP1_SAME_M1',at=str(at))
        if stop:return dict(label='INITIAL_STOP_FIRST',at=str(at))
        if target:return dict(label='TP1_FIRST',at=str(at))
    return dict(label='NEITHER_BY_FLAT' if expected>=end else 'UNKNOWN_MISSING_TAIL',at=str(expected))


def freeze():
    verify()
    if (HERE/'diagnostic_protocol.json').exists():raise RuntimeError('Already frozen')
    write(HERE/'diagnostic_protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),
      scope='All21TIGHT filled trades at primary.5pip after validation result, not independent verification.',
      question='Initial structural stop before TP1, or TP1 before stop? For reaction exits, same question after exit. No profit attached to hypothetical continuation.',
      rules='Existing initial entry/stop/TP1,exit-side bid/assumedaskM1;stop precedence fillbar,no fillbarTP;later sameM1stop/target labeledAMBIGUOUS. FixedLondon16:30 cutoff. MissingbarsUNKNOWN.',
      prohibition='No replacement rules,optimization,live gate,price future as entry feature or counterfactual PNL.',
      hashes={p.name:sha(p) for p in [HERE/'path_diagnosis.py',HERE/'outcomes.json',HERE/'candidates.json',HERE/'price_manifest_frozen.json']}))


def run():
    verify();plan=json.loads((HERE/'diagnostic_protocol.json').read_text())
    for name,h in plan['hashes'].items():
        if sha(HERE/name)!=h:raise RuntimeError('Diagnostic frozen mismatch')
    outcomes=json.loads((HERE/'outcomes.json').read_text());candidates=json.loads((HERE/'candidates.json').read_text())
    records=[];frames={}
    for o in outcomes:
        if not(o['group']=='TIGHT' and o['spread_pips']==.5 and o['filled_at']):continue
        c=candidates[o['candidate_id']];symbol=c['symbol']
        if symbol not in frames:frames[symbol]=pd.read_parquet(HERE/'prices'/(symbol+'_1m.parquet'))
        f=frames[symbol]
        records.append(dict(candidate_id=o['candidate_id'],symbol=symbol,day=c['day'],actual_modeled_exit=o['reason'],actual_modeled_net_r=o['net_r'],
                            initial_path=path(c['signal'],o['filled_at'],f),
                            after_reaction_exit=after_exit(c['signal'],o['closed_at'],f) if o['reason']=='REACTION_EXIT' else None))
    count=lambda rows,key:{label:sum(r[key]['label']==label for r in rows) for label in sorted({r[key]['label'] for r in rows})}
    reactions=[r for r in records if r['after_reaction_exit'] is not None]
    result=dict(fills=len(records),initial_geometry=count(records,'initial_path'),reaction_exits=len(reactions),after_reaction=count(reactions,'after_reaction_exit'),
                reaction_actual_modeled_net_r=sum(r['actual_modeled_net_r'] for r in reactions),
                caveat='Ex-post competing level events; no new entry filter or hypothetical strategy profits. Model spread remains assumed.')
    write(HERE/'path_records.json',records);write(HERE/'path_summary.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run']);a=p.parse_args()
    freeze() if a.action=='freeze' else run()
