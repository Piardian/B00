"""Post-result diagnostics, never used to select candidates or tune rules."""
import json
from pathlib import Path
import pandas as pd
from study import digest, ROOT, HERE, SYMBOLS


def main():
    rows=json.loads((HERE/'outcomes.json').read_text(encoding='utf-8'))
    selected=json.loads((HERE/'selected_setups.json').read_text(encoding='utf-8'))
    coverage={}
    for symbol in SYMBOLS:
        frame=pd.read_csv(ROOT/f'data/full_2025_study/prices_utc/{symbol}_1m.csv.gz',parse_dates=['datetime'])
        if frame.datetime.duplicated().any() or not frame.datetime.is_monotonic_increasing:raise ValueError('Invalid chronology: '+symbol)
        coverage[symbol]={m:int(frame.datetime.dt.strftime('%Y-%m').eq(m).sum()) for m in ['2025-01','2025-06','2025-11']}
    baseline=[r for r in rows if r['policy']=='passive' and r['spread_pips']==.5 and r['filled_at']]
    total=sum(r['net_r'] for r in baseline)
    best=sorted(baseline,key=lambda r:r['net_r'],reverse=True)[:4]
    primary=[r for r in rows if r['spread_pips']==.5]
    diagnostics=dict(price_rows_by_month=coverage,
      selected_setups_by_month={m:sum(c['day'].startswith(m) for c in selected) for m in ['2025-01','2025-06','2025-11']},
      month_warning='June has price rows but zero candidates in the imported opening-only export; no June entry-policy effectiveness measurement. Do not render zero as a profitable or stable month.',
      primary_net_minus_largest_four=total-sum(r['net_r'] for r in best),largest_four=[dict(day=r['day'],symbol=r['symbol'],net_r=r['net_r']) for r in best],
      per_symbol_primary_baseline={s:sum(r['net_r'] for r in baseline if r['symbol']==s) for s in SYMBOLS},
      primary_reaction_exit_net={p:sum(r['net_r'] for r in primary if r['policy']==p and r['reason']=='REACTION_EXIT') for p in ['passive','reaction_retest','break_retest']},
      primary_month_fills={p:{m:sum(bool(r['filled_at']) for r in primary if r['policy']==p and r['month']==m) for m in ['2025-01','2025-11']} for p in ['passive','reaction_retest','break_retest']},
      decision='NO_LIVE_PROMOTION; promising historical branch under moderate assumed costs, negative November and adverse cost scenario; confirmation alternatives failed primary comparison.',
      artifact_hashes={p.name:digest(p) for p in HERE.glob('*.py')})
    (HERE/'diagnostics.json').write_text(json.dumps(diagnostics,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in diagnostics.items() if k not in ['price_rows_by_month','artifact_hashes']},indent=2))


if __name__=='__main__':main()
