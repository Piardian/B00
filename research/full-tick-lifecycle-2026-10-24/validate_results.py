"""Post-replay ledger and quote-audit parity assertions."""
import json
from study import HERE,ROOT,verify,sha,write


def main():
    verify();rows=json.loads((HERE/'outcomes.json').read_text(encoding='utf-8'))
    prior=ROOT/'research/fill-delay-tick-audit-2026-10-24/records.json'
    audit={r['case_id']:r for r in json.loads(prior.read_text(encoding='utf-8'))}
    index={(r['case_id'],r['scenario'],r['ttl']):r for r in rows};parity=0;retained=0
    terminal={'TP1','TP2','FILL_TICK_STOP','STOP_OR_BE_TRAIL','REACTION_EXIT','INTRADAY_FLAT'}
    for r in rows:
        if r['status']!='CLOSED':continue
        assert abs(r['net_r']-(r['gross_r']-r['commission_r']))<1e-10
        fees=sum(e.get('commission_r',0.) for e in r['events'])
        assert abs(fees-r['commission_r'])<1e-10
        if r['filled_at']:
            assert sum(e['qty'] for e in r['events'] if e['type']=='LIMIT_FILL')==1
            assert sum(e['qty'] for e in r['events'] if e['type'] in terminal)==1
            assert abs(r['remaining_qty'])<1e-12
        else:assert r['net_r']==0 and r['commission_r']==0 and not r['events']
        if r['scenario']=='OBSERVED_QUOTES' and r['ttl']=='REFERENCE_240':
            assert r['filled_at']==audit[r['case_id']]['audit']['first_possible_fill'];parity+=1
        if r['ttl']=='TTL_15' and r['filled_at']:
            ref=index[r['case_id'],r['scenario'],'REFERENCE_240']
            for key in ['filled_at','closed_at','reason','gross_r','commission_r','net_r','events']:assert r[key]==ref[key]
            retained+=1
    write(HERE/'integrity.json',dict(status='PASSED',rows=len(rows),observed_tick_fill_parity=parity,
      retained_ttl_lifecycles_identical=retained,checks=['fee ledger','entry/exit quantity conservation','net=gross-fee','unfilled no fees','observed fill audit parity','retained TTL lifecycle equality'],
      outcome_sha256=sha(HERE/'outcomes.json'),audit_source_sha256=sha(prior)))
    print('Integrity passed:',len(rows),'rows;',parity,'observed fills matched prior quote audit;',retained,'retained TTL lifecycles identical')


if __name__=='__main__':main()
