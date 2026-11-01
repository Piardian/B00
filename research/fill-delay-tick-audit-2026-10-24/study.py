"""Locked actual-quote timing audit of90 historical London limit setups."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from audit import audit

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False,allow_nan=False,default=str),encoding='utf-8')


def freeze():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already frozen')
    sources=[ROOT/'research/asia-validation-2026-10-24/candidates.json',ROOT/'research/fill-delay-2026-10-24/followup_candidates.json',
             ROOT/'research/fill-delay-2026-10-24/outcomes.json',ROOT/'research/fill-delay-2026-10-24/followup_outcomes.json',
             ROOT/'research/london-quote-validation-2026-10-23/quote_manifest_frozen.json',ROOT/'research/fill-delay-2026-10-24/followup_source_manifest.json']
    cases=[]
    for cohort,candidate_path,outcome_path,manifest_path in [('RECHECK',sources[0],sources[2],sources[4]),('FOLLOWUP',sources[1],sources[3],sources[5])]:
        candidates=json.loads(candidate_path.read_text(encoding='utf-8'));outcomes=json.loads(outcome_path.read_text(encoding='utf-8'));manifest=json.loads(manifest_path.read_text())
        if manifest.get('broker_server')!='FivePercentOnline-Real':raise RuntimeError('Broker source mismatch')
        for i,c in enumerate(candidates):
            caseid='RECHECK_'+str(i) if cohort=='RECHECK' else str(i)
            rows=[r for r in outcomes if r['case_id']==caseid and r['spread_pips']==.5]
            ref=next(r for r in rows if r['variant']=='REFERENCE_240');short=next(r for r in rows if r['variant']=='TTL_15')
            symbol=c['symbol'];meta=manifest['files'][symbol+'_'+c['day']];path=Path(meta['path'])
            if sha(path)!=meta['sha256']:raise RuntimeError('Existing quote tape changed')
            point=manifest['symbol_specs'][symbol]['trade_tick_size']
            expected=.001 if symbol=='USDJPY' else .00001
            if abs(point-expected)>1e-12:raise RuntimeError('Tick size mismatch with model')
            cases.append(dict(case_id=cohort+'_'+str(i),cohort=cohort,symbol=symbol,day=c['day'],month=c['day'][:7],
               available_at=c['available_at'],signal=c['signal'],point=point,tape_path=str(path),tape_sha256=meta['sha256'],
               model_reference_filled_at=ref['filled_at'],model_ttl15_filled_at=short['filled_at']))
    if len(cases)!=90:raise RuntimeError('Expected all90 additional-period setups')
    write(HERE/'cases_frozen.json',cases)
    write(HERE/'protocol.json',dict(frozen_at=str(pd.Timestamp.now(tz='UTC')),
      sample='All90 existing first daily setups Feb/Mar/Apr/May/Sep/Oct2025; Jan/Nov excluded because full-day quote tapes not in this locked archive. No selection by PNL or audit result.',
      purpose='Audit fill timing assumptions, NOT new trade PNL, edge proof, live order or latency/queue simulation.',
      quote_rule='Earliest actualask<=buyentry-one tick or actualbid>=sellentry+one tick after original availability, before min(noon,+240min). Same fixed15min cutoff, exclusive boundary. Raw same-ms order preserved.',
      quality='Positive finite noncrossed quotes in pending window;firstpostdecisionquote<=5sec;no gap>60sec before firsthit/expiry;nofill needsquote at expiry within5sec. Stale/unknown UNPRICED, never assumed canceled profit.',
      comparison='Baseline .5pip syntheticspread model fill versus observedquote opportunity; fillminute and TTL15classification. Does not attach old modeledPNL to changed tick fills.',
      caveats=['Archived broker bid/ask quotes, not actual fill receipts or independent executable spread certificate','Many quote records can show zero spread; no free trading inference','Trade entry reaction, exit costs and lifecycle not re-simulated; previous negative profit validation unchanged','Historical observed data; no new OOS claim, no threshold search'],
      source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources},
      code_hashes={p.name:sha(p) for p in HERE.glob('*.py')},cases_sha256=sha(HERE/'cases_frozen.json')))


def verify():
    plan=json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    for n,h in plan['code_hashes'].items():
        if sha(HERE/n)!=h:raise RuntimeError('Audit source changed')
    if sha(HERE/'cases_frozen.json')!=plan['cases_sha256']:raise RuntimeError('Cases changed')
    for n,h in plan['source_hashes'].items():
        if sha(ROOT/n)!=h:raise RuntimeError('Upstream input changed')


def run():
    verify();cases=json.loads((HERE/'cases_frozen.json').read_text(encoding='utf-8'));records=[]
    for c in cases:
        path=Path(c['tape_path'])
        if sha(path)!=c['tape_sha256']:raise RuntimeError('Quote tape changed')
        f=pd.read_parquet(path);result=audit(c['signal'],c['available_at'],f,c['point'])
        comparison=None
        if result['status']=='MEASURED':
            both=bool(c['model_reference_filled_at'] and result['first_possible_fill'])
            comparison=dict(model_full_fill=bool(c['model_reference_filled_at']),tick_full_fill=bool(result['first_possible_fill']),
               model_ttl15=bool(c['model_ttl15_filled_at']),tick_ttl15=result['accepted_by_ttl15'],
               ttl15_disagrees=bool(c['model_ttl15_filled_at'])!=result['accepted_by_ttl15'],
               fill_minute_matches=(pd.Timestamp(c['model_reference_filled_at'])==pd.Timestamp(result['fill_minute'])) if both else None,
               tick_minus_model_minutes=(pd.Timestamp(result['first_possible_fill'])-pd.Timestamp(c['model_reference_filled_at'])).total_seconds()/60 if both else None)
        records.append(dict(case_id=c['case_id'],cohort=c['cohort'],symbol=c['symbol'],day=c['day'],month=c['month'],model_reference_filled_at=c['model_reference_filled_at'],
                            model_ttl15_filled_at=c['model_ttl15_filled_at'],audit=result,comparison=comparison))
    summary=[]
    for cohort in ['ALL','RECHECK','FOLLOWUP']:
        rows=[r for r in records if cohort=='ALL' or r['cohort']==cohort];known=[r for r in rows if r['audit']['status']=='MEASURED']
        hits=[r for r in known if r['audit']['first_possible_fill']];both=[r for r in known if r['comparison']['model_full_fill'] and r['comparison']['tick_full_fill']]
        summary.append(dict(cohort=cohort,cases=len(rows),measured=len(known),unpriced=len(rows)-len(known),
          groups={g:sum(r['audit']['group']==g for r in known) for g in ['BEFORE15','AT_OR_AFTER15','NO_FILL']},
          model_full_fills_on_measured=sum(r['comparison']['model_full_fill'] for r in known),
          model_ttl15_on_measured=sum(r['comparison']['model_ttl15'] for r in known),tick_full_fills=len(hits),
          ttl15_disagreements=sum(r['comparison']['ttl15_disagrees'] for r in known),
          minute_matches=sum(r['comparison']['fill_minute_matches'] is True for r in both),both_filled=len(both),
          tick_fill_without_model=sum(r['comparison']['tick_full_fill'] and not r['comparison']['model_full_fill'] for r in known),
          model_fill_without_tick=sum(r['comparison']['model_full_fill'] and not r['comparison']['tick_full_fill'] for r in known),
          median_observed_fill_spread_pips=float(np.median([r['audit']['first_fill_spread_pips'] for r in hits])) if hits else None,
          zero_spread_fill_quotes=sum(r['audit']['first_fill_spread_pips']==0 for r in hits),
          marketable_opening_quotes=sum(r['audit']['marketable_at_first_post_signal_quote'] for r in known),
          unpriced_reasons={reason:sum(r['audit'].get('reason')==reason for r in rows) for reason in sorted({r['audit']['reason'] for r in rows if r['audit']['status']!='MEASURED'})}))
    verify();write(HERE/'records.json',records);write(HERE/'summary.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','verify']);a=p.parse_args()
    {'freeze':freeze,'run':run,'verify':verify}[a.action]()
