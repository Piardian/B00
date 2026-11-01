"""Coverage repair and paired nominal/aligned fixed60min diagnostics."""
from pathlib import Path
import argparse,copy,importlib,json,shutil,sys
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
BASE=HERE.parent/'sfp-ifvg-ablation-2026-10-24'
GRID=HERE.parent/'execution-grid-2026-10-24'
sys.path.insert(0,str(HERE))
def measure():return importlib.import_module('measure')

def freeze():
    assert not (HERE/'protocol.json').exists()
    shutil.copyfile(BASE/'measure.py',HERE/'measure.py');m=measure()
    for folder in [BASE,GRID]:
        for name,h in m.read(folder/'artifact_manifest.json').items():assert m.sha(folder/name)==h,name
    for name in ['normalize_clock.py']:shutil.copyfile(BASE/name,HERE/name)
    target=HERE/'frozen_engine';target.mkdir()
    for path in (BASE/'frozen_engine').glob('*.py'):shutil.copyfile(path,target/path.name)
    for path in BASE.glob('quote_manifest_*_frozen.json'):shutil.copyfile(path,HERE/path.name)
    shutil.copyfile(GRID/'price_grid.py',HERE/'price_grid.py')
    shutil.copyfile(BASE/'signals.json',HERE/'cases_frozen.json')
    shutil.copyfile(GRID/'aligned_signal_proposals.json',HERE/'aligned_frozen.json')
    p=copy.deepcopy(m.read(BASE/'protocol.json'))
    p.update(created_utc=str(pd.Timestamp.now(tz='UTC')),
      name='Complete quotes and compare nominal to predeclared price-grid proposals',
      scope='All57 existing noIFVG SFP cases; same fixed60min direction/markout diagnostic, NOT full SL/TP lifecycle or live strategy backtest. All57 original timestamps retained; paired nominal and aligned levels rerun on identical refreshed quotes. No parameter search.',
      collector='Read-only existing FivePercentOnline-Real MT5; request UNION of exact signal through TTL240min+markout60min+5s for every symbol/day, including previously resolved cases. Reuse full verified tapes or collect missing entire ranges; no outcome selection. Max3 technical retries, no orders/account or terminal restart. Stop new reads below2GiB free or >1.5GiB free-space consumption. External paid budget0USD.',
      clock_QA='US-DST broker UTC+2/3 policy frozen from prior independent clock studies. Compare full captured bidM15 closes with original frozen nativeM15: >=8 comparisons, >=95percent within2brokersteps. Failed QA means unresolved, never a return.',
      funnel='Explanatory-only AST instrumentation inserts counters after existing continue gates in _detect_confirmed_sfp. Unique decision windows, not nested pool attempts. Output must match all57 original signals across every18860 scanned window. Same session/history/trend. No rule relaxation or candidate selection.',
      inherited_gate='Same >=30resolvedfills and>=15days EACH temporalperiod, no unresolved, positive stressmean and95dayCI lower>0. Current candidate count can be insufficient; do not weaken this gate to manufacture success.',
      spec_caveat='Price grid uses captured2026 metadata, not archived2025 acceptance; aligned proposals not verified accepted broker orders. Markouts ignore SL/TP and cannot establish net strategy profitability.',
      comparison='Same57setups, scenariosOBSERVED/STRESS1.5/STRESS_FLOOR, same fee/slip model. Report perperiod status transitions and matched-day bootstrap. Never reuse old nominal returns for aligned prices. Preserve old partial reports.',
      previous_partial_protocol_sha256=m.sha(BASE/'protocol.json'))
    refs=[BASE/'signals.json',BASE/'protocol.json',BASE/'quote_markouts.json',BASE/'coverage.json',GRID/'protocol.json',GRID/'aligned_signal_proposals.json']
    p['source_hashes'].update({str(x.relative_to(ROOT)):m.sha(x) for x in refs})
    p['source_hashes'].update({str(x.relative_to(ROOT)):m.sha(x) for x in [HERE/'cases_frozen.json',HERE/'aligned_frozen.json',*HERE.glob('quote_manifest_*_frozen.json')]})
    p['frozen_source_hashes']={str(x.relative_to(HERE)):m.sha(x) for x in target.glob('*.py')}
    p['code_hashes']={x.name:m.sha(x) for x in HERE.glob('*.py')}
    m.write(HERE/'protocol.json',p);m.write(HERE/'status.json',dict(stage='FROZEN',live_changed=False))
    print('FROZEN57pairedcases; original detector, original marks and price-grid proposals preserved')

def replay():
    m=measure();m.verify();manifest=m.read(HERE/'quote_manifest_frozen.json')
    originals=m.read(HERE/'cases_frozen.json');aligned={r['case_id']:r for r in m.read(HERE/'aligned_frozen.json')}
    outcomes=[];hashes={}
    for c in originals:
        key=c['symbol']+'_'+c['day'];meta=manifest['files'][key]
        f=None
        if meta['status']=='AVAILABLE' and meta['clock_qa']['passed']:
            path=Path(meta['path']);assert m.sha(path)==meta['sha256'];hashes[str(path)]=meta['sha256']
            f=pd.read_parquet(path);f.time=pd.to_datetime(f.time,utc=True)
        for model,sig in [('NOMINAL',c['signal']),('ALIGNED',aligned[c['case_id']]['signal'])]:
            for label,mult,floor in [('OBSERVED',1.,False),('STRESS_1_5X',1.5,False),('STRESS_FLOOR',1.5,True)]:
                result=m.quote_score(sig,c['available_at'],f,stress=mult,floor=floor) if f is not None else dict(status='UNRESOLVED_SOURCE_OR_CLOCK',net_markout_r=None)
                outcomes.append({k:c[k] for k in ['case_id','symbol','day','month','period']}|dict(model=model,scenario=label,**result))
        print('REPLAY',c['case_id'],outcomes[-3]['status'],flush=True)
    m.write(HERE/'outcomes.json',outcomes);m.write(HERE/'used_tape_hashes.json',hashes)
    m.write(HERE/'status.json',dict(stage='REPLAYED',records=len(outcomes)))

def stats(rows):
    m=measure();fills=[r for r in rows if r['status']=='FILLED_MARKOUT']
    vals=[r['net_markout_r'] for r in fills]
    return dict(setups=len(rows),fills=len(fills),days=len({r['day'] for r in fills}),
        no_fill=sum(r['status']=='NO_FILL' for r in rows),unresolved=sum(r['status'].startswith(('UNRESOLVED','INVALID')) for r in rows),
        reasons={x:sum(r['status']==x for r in rows) for x in sorted({r['status'] for r in rows})},
        mean_conditional_markout_r=float(np.mean(vals)) if vals else None,day95=m.bootstrap(fills,'net_markout_r'),
        stop_crossed=sum(r['original_stop_crossed'] for r in fills),
        marketable_first_quote=sum(r['marketable_at_first'] for r in fills))

def finish():
    m=measure();p=m.verify();rows=m.read(HERE/'outcomes.json');cases=m.read(HERE/'cases_frozen.json')
    assert len(rows)==342 and len(cases)==57
    lookup={(r['case_id'],r['model'],r['scenario']):r for r in rows}
    for r in rows:
        if r['status']=='FILLED_MARKOUT':
            assert np.isclose(r['net_markout_r'],r['price_markout_r']-r['commission_r']-r['slip_r'])
            assert pd.Timestamp(r['marked_at'])>=pd.Timestamp(r['filled_at'])+pd.Timedelta(hours=1)
        else:assert r['net_markout_r'] is None
    old=m.read(BASE/'quote_markouts.json');parity=[]
    for r in old:
        if r['status'].startswith('UNRESOLVED'):continue
        new=lookup[(r['case_id'],'NOMINAL',r['scenario'])]
        same=r['status']==new['status']
        if same and r['status']=='FILLED_MARKOUT':
            same=all(r[k]==new[k] for k in ['filled_at','marked_at']) and abs(r['net_markout_r']-new['net_markout_r'])<1e-10
        parity.append(dict(case_id=r['case_id'],scenario=r['scenario'],same=bool(same),old_status=r['status'],new_status=new['status']))
    groups={};gates={}
    for period in ['DEVELOPMENT','VALIDATION']:
        groups[period]={};gates[period]={}
        for model in ['NOMINAL','ALIGNED']:
            groups[period][model]={}
            for scenario in ['OBSERVED','STRESS_1_5X','STRESS_FLOOR']:
                ss=stats([r for r in rows if r['period']==period and r['model']==model and r['scenario']==scenario])
                groups[period][model][scenario]=ss
                if model=='ALIGNED' and scenario!='OBSERVED':
                    gates[period][scenario]=dict(at_least30fills=ss['fills']>=30,at_least15days=ss['days']>=15,
                      no_unresolved=ss['unresolved']==0,positive_mean=ss['mean_conditional_markout_r'] is not None and ss['mean_conditional_markout_r']>0,
                      positive_day95_lower=ss['day95'] is not None and ss['day95'][0]>0)
    paired=[]
    for c in cases:
        for scenario in ['OBSERVED','STRESS_1_5X','STRESS_FLOOR']:
            a=lookup[(c['case_id'],'NOMINAL',scenario)];b=lookup[(c['case_id'],'ALIGNED',scenario)]
            paired.append(dict(case_id=c['case_id'],day=c['day'],period=c['period'],scenario=scenario,
                nominal_status=a['status'],aligned_status=b['status'],
                paired_conditional_delta_r=b['net_markout_r']-a['net_markout_r'] if a['status']==b['status']=='FILLED_MARKOUT' else None))
    support=all(all(g.values()) for v in gates.values() for g in v.values())
    manifest=m.read(HERE/'quote_manifest_frozen.json')
    for path,h in m.read(HERE/'used_tape_hashes.json').items():assert m.sha(Path(path))==h
    m.write(HERE/'parity.json',parity);m.write(HERE/'paired.json',paired)
    m.write(HERE/'summary.json',dict(groups=groups,gates=gates,old_resolved_parity_checked=len(parity),
        old_resolved_parity_matched=sum(r['same'] for r in parity),full_lifecycle_backtest=False))
    m.write(HERE/'decision.json',dict(status='ENTRY_FOLLOWUP_SUPPORTED' if support else 'EDGE_NOT_ESTABLISHED',
        live_approved=False,demo_started=False,full_strategy_profit_calculated=False,
        scope='All57 fixed setups, refreshed brokerquotes, paired nominal/aligned fixed60min marks. Costs assumptions; no stop/TP exits, macro/news/sharedrisk or brokerorderreceipt.',gates=gates))
    m.write(HERE/'integrity.json',dict(passed=True,records=len(rows),setups=57,models=2,scenarios=3,
       old_resolved_parity_checked=len(parity),old_resolved_parity_matched=sum(r['same'] for r in parity),
       quote_files_verified=len(m.read(HERE/'used_tape_hashes.json')),live_changed=False))
    lines=['# SFP: tamamlanan kotasyonlar ve fiyat-adımı karşılaştırması','',
      '**Bu çalışma tam sistem kâr backtesti değildir.** Sabit57aday, aynı240dk limit süresi ve dolumdan60dk sonraki fiyat hareketi; ilk stop/TP yönetimi uygulanmaz. Stop aşan markout işlem kârı sayılamaz.','',
      '| Dönem | Model | Senaryo | Dolum | Dolmayan | Belirsiz | Ortalama maliyetli markout R | Stop aşımı |','|---|---|---|---:|---:|---:|---:|---:|']
    for period,models in groups.items():
        for model,scenarios in models.items():
            for scenario,v in scenarios.items():
                mean='—' if v['mean_conditional_markout_r'] is None else f"{v['mean_conditional_markout_r']:.6f}"
                lines.append(f"| {period} | {model} | {scenario} | {v['fills']} | {v['no_fill']} | {v['unresolved']} | {mean} | {v['stop_crossed']} |")
    lines+=['','Komisyon ve kayma önceki deneydeki sabit varsayımlar. Spread arşivden gözlenir;1.5x ve ek spread tabanı senaryoları aynıdır. Fiyat adımı2026 metadata kaydıdır;2025 emir kabulü doğrulanmış değildir. Yeni fiyatlar için dolum ve maliyetler yeniden hesaplandı; eski getiriler taşınmadı.','',
      f"Önceki çözülmüş{len(parity)} senaryo kaydının{sum(r['same'] for r in parity)} tanesi yeni nominal replay ile birebir eşleşti. Tüm yeni dosyalar hash ve saat hizası kontrolünden geçirildi. Eksik/bozuk veri sıfır getiri sayılmadı.",
      '', 'Karar: '+('Sabit giriş incelemesi için ileri araştırma eşiği geçti.' if support else 'Edge kanıtlanmadı; ayrıntılı örnek/kapsam/istikrar koşulları decision.json içinde. Daha fazla işlem tek başına başarı değil.'),
      '', 'Az sinyalin nedenleri funnel.json ve FUNNEL.md içinde ayrı incelenir. Üretim kodu/süreç/emirler değiştirilmedi. Ücretli API kullanılmadı.']
    (HERE/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    m.write(HERE/'status.json',dict(stage='COMPLETE',records=len(rows),live_changed=False,paid_API_spend_USD=0))
    seal();print(json.dumps(groups,indent=2))

def seal():
    m=measure();m.write(HERE/'artifact_manifest.json',{str(x.relative_to(HERE)):m.sha(x) for x in HERE.rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.name not in ['artifact_manifest.json','run.log','collector.log','funnel.log']})

if __name__=='__main__':
    pa=argparse.ArgumentParser();pa.add_argument('action',choices=['freeze','replay','finish','seal']);args=pa.parse_args();globals()[args.action]()
