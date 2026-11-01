"""One predeclared existing-entry-model comparison, never a live engine."""
from pathlib import Path
import argparse, copy, importlib, json, shutil, sys
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=HERE.parent/'sfp-direction-2026-10-24'
sys.path.insert(0,str(HERE))

def measure():return importlib.import_module('measure')

def freeze():
    if (HERE/'protocol.json').exists():raise RuntimeError('Already frozen')
    shutil.copyfile(BASE/'study.py',HERE/'measure.py')
    m=measure()
    parent=m.read(BASE/'protocol.json')
    # Check the whole preserved reference, not only its eight positive/negative cases.
    for name,digest in m.read(BASE/'artifact_manifest.json').items():
        if m.sha(BASE/name)!=digest:raise RuntimeError('Reference artifact changed: '+name)
    for name,digest in parent['source_hashes'].items():
        if m.sha(ROOT/name)!=digest:raise RuntimeError('Reference price input changed: '+name)
    declaration=m.read(BASE/'next_hypothesis_predeclared.json')
    assert declaration['baseline_protocol_sha256']==m.sha(BASE/'protocol.json')
    assert declaration['status']=='DECLARED_NOT_EXECUTED'
    package=HERE/'frozen_engine';package.mkdir()
    for source in (BASE/'frozen_engine').glob('*.py'):shutil.copyfile(source,package/source.name)
    config=package/'config.py';raw=config.read_bytes();original=config.read_text(encoding='utf8')
    before='USE_IFVG_ENTRY = True';after='USE_IFVG_ENTRY = False'
    assert original.count(before)==1
    config.write_bytes(raw.replace(before.encode(),after.encode(),1))
    assert config.read_text(encoding='utf8').replace(after,before)==original
    shutil.copyfile(BASE/'normalize_clock.py',HERE/'normalize_clock.py')
    shutil.copyfile(BASE/'next_hypothesis_predeclared.json',HERE/'hypothesis_frozen.json')
    for source in BASE.glob('quote_manifest_*_frozen.json'):shutil.copyfile(source,HERE/source.name)
    protocol=copy.deepcopy(parent)
    protocol.update(created_utc=str(pd.Timestamp.now(tz='UTC')),
      name='SFP existing sweep-wick CE entry with mandatory IFVG disabled',
      scope='Isolated research variant of frozen SFP; only USE_IFVG_ENTRY=False. Not original unchanged live strategy, not a pure filter ablation. The flag changes confirmation zone and entry/risk geometry. No macro/news/occupancy/cooldown or SL/TP lifecycle. Conditional markouts are NOT trade profit.',
      improvements='Exactly the predeclared existing-entry-model comparison. No additional flag, threshold, asset, month or horizon search. Raw direction changes in price/basispoints reported alongside R because risk can change.',
      coverage_amendment=parent.get('coverage_amendment'),
      parent_protocol_sha256=m.sha(BASE/'protocol.json'),hypothesis_sha256=m.sha(BASE/'next_hypothesis_predeclared.json'))
    protocol['effective_config']['USE_IFVG_ENTRY']=False
    protocol['source_hashes'].update({str((BASE/name).relative_to(ROOT)):m.sha(BASE/name) for name in [
       'protocol.json','signals.json','summary.json','quote_markouts.json','coverage.json',
       'artifact_manifest.json','next_hypothesis_predeclared.json']})
    protocol['source_hashes'].update({str(p.relative_to(ROOT)):m.sha(p) for p in HERE.glob('quote_manifest_*_frozen.json')})
    protocol['source_hashes'][str((HERE/'hypothesis_frozen.json').relative_to(ROOT))]=m.sha(HERE/'hypothesis_frozen.json')
    protocol['frozen_source_hashes']={str(p.relative_to(HERE)):m.sha(p) for p in package.glob('*.py')}
    protocol['code_hashes']={p.name:m.sha(p) for p in HERE.glob('*.py')}
    m.write(HERE/'protocol.json',protocol)
    m.write(HERE/'status.json',dict(stage='FROZEN',paid_API_budget_USD=0,live_changed=False))
    print('FROZEN one flag: USE_IFVG_ENTRY True -> False; all entry helpers byte-identical')

def direction_rows(cases):
    rows=[]
    for c in cases:
        d=c['direction'];sgn=1 if c['signal']['direction']=='LONG' else -1
        delta=sgn*(d['future_bid']-d['origin_bid']) if d['status']=='MEASURED' else None
        rows.append(dict(case_id=c['case_id'],day=c['day'],symbol=c['symbol'],period=c['period'],
            month=c['month'],signed_r=d['signed_r'],signed_price=delta,
            signed_bps=delta/d['origin_bid']*10000 if delta is not None else None,
            original_risk=abs(c['signal']['entry']-c['signal']['stop_loss'])))
    return rows

def direction_stats(rows):
    m=measure();valid=[r for r in rows if r['signed_r'] is not None]
    result=dict(setups=len(rows),measured=len(valid),positive=sum(r['signed_r']>0 for r in valid),
        mean_r=float(np.mean([r['signed_r'] for r in valid])) if valid else None,
        mean_bps=float(np.mean([r['signed_bps'] for r in valid])) if valid else None,
        day95_r=m.bootstrap(valid,'signed_r'),day95_bps=m.bootstrap(valid,'signed_bps'))
    result['by_symbol']={s:dict(n=sum(r['symbol']==s for r in valid),
        mean_price=float(np.mean([r['signed_price'] for r in valid if r['symbol']==s])) if any(r['symbol']==s for r in valid) else None,
        mean_bps=float(np.mean([r['signed_bps'] for r in valid if r['symbol']==s])) if any(r['symbol']==s for r in valid) else None)
        for s in m.SYMBOLS}
    return result

def quote_stats(rows):
    m=measure();fills=[r for r in rows if r['status']=='FILLED_MARKOUT']
    counts={v:sum(r['status']==v for r in rows) for v in sorted({r['status'] for r in rows})}
    return dict(setups=len(rows),fills=len(fills),fill_days=len({r['day'] for r in fills}),status_counts=counts,
        unresolved=sum(r['status'].startswith(('UNRESOLVED','INVALID')) for r in rows),
        mean_conditional_markout_r=float(np.mean([r['net_markout_r'] for r in fills])) if fills else None,
        mean_day95=m.bootstrap(fills,'net_markout_r'),
        original_stop_crossed=sum(r['original_stop_crossed'] for r in fills),
        marketable_first_quote=sum(r['marketable_at_first'] for r in fills),
        wait_minutes_median=float(np.median([r['wait_minutes'] for r in fills])) if fills else None,
        fee_burden_mean_r=float(np.mean([r['commission_r']+r['slip_r'] for r in fills])) if fills else None,
        mfe_mean_r=float(np.mean([r['mfe_r'] for r in fills])) if fills else None,
        mae_mean_r=float(np.mean([r['mae_r'] for r in fills])) if fills else None)

def verify():
    m=measure();p=m.verify()
    for name,digest in m.read(BASE/'artifact_manifest.json').items():assert m.sha(BASE/name)==digest,name
    actual=(HERE/'frozen_engine/config.py').read_text(encoding='utf8')
    expected=(BASE/'frozen_engine/config.py').read_text(encoding='utf8').replace('USE_IFVG_ENTRY = True','USE_IFVG_ENTRY = False')
    assert actual==expected
    for path in (BASE/'frozen_engine').glob('*.py'):
        if path.name!='config.py':assert m.sha(HERE/'frozen_engine'/path.name)==m.sha(path)
    c,d,e=m.engine()
    assert c.USE_IFVG_ENTRY is False and d.USE_IFVG_ENTRY is False
    assert c.REQUIRE_STRUCTURAL_BREAKER and c.REQUIRE_PRO_TREND_AAA
    cases=m.read(HERE/'signals.json');quotes=m.read(HERE/'quote_markouts.json');coverage=m.read(HERE/'coverage.json')
    detector=d.SFPDetector();causal=0;reproduced=0
    for symbol in m.SYMBOLS:
        bars,hourly,audit=m.load_prices(symbol)
        assert audit['m15_conflicting_fields']==0 and audit['h1_conflicting_fields']==0
        assert bars.datetime.is_monotonic_increasing and not bars.datetime.duplicated().any()
        assert hourly.datetime.is_monotonic_increasing and not hourly.datetime.duplicated().any()
        selected=[r for r in cases if r['symbol']==symbol]
        controls=[pd.Timestamp(f'2025-{mo:02}-15 10:00',tz='UTC') for mo in range(1,12)]
        def snapshot(b,h,at):
            return (b[b.datetime+pd.Timedelta(minutes=15)<=at].tail(300).reset_index(drop=True),
                    h[h.datetime+pd.Timedelta(hours=1)<=at].tail(1000).reset_index(drop=True))
        for at in [pd.Timestamp(r['available_at']) for r in selected]+controls:
            hist,h=snapshot(bars,hourly,at)
            if hist.empty:continue
            trend=e.higher_timeframe_trend(h,at)
            observed=detector.detect_sfp(hist,symbol[:3]+'/'+symbol[3:],htf_trend=trend)
            mc=bars.copy();hc=hourly.copy()
            mc.loc[mc.datetime+pd.Timedelta(minutes=15)>at,['open','high','low','close']]*=17
            hc.loc[hc.datetime+pd.Timedelta(hours=1)>at,['open','high','low','close']]*=.13
            mutated,mutated_h=snapshot(mc,hc,at)
            trend2=e.higher_timeframe_trend(mutated_h,at)
            got=detector.detect_sfp(mutated,symbol[:3]+'/'+symbol[3:],htf_trend=trend2)
            assert trend==trend2 and json.dumps(observed,sort_keys=True,default=str)==json.dumps(got,sort_keys=True,default=str)
            causal+=1
        for row in selected:
            at=pd.Timestamp(row['available_at']);hist,h=snapshot(bars,hourly,at)
            got=detector.detect_sfp(hist,symbol[:3]+'/'+symbol[3:],htf_trend=e.higher_timeframe_trend(h,at))
            assert json.dumps(got,sort_keys=True,default=str)==json.dumps(row['signal'],sort_keys=True,default=str)
            assert pd.Timestamp(got['datetime'])+pd.Timedelta(minutes=15)==at
            assert not got['ifvg_confirmed'] and got['breaker_confirmed']
            assert got['entry_source'] in ['SWEEP_WICK_50_CE','SWEEP_WICK_50_CE_FALLBACK']
            assert e.validate_signal(got) is None
            assert m.direction(got,at,bars)==row['direction']
            reproduced+=1
    assert sum(r['validated'] for r in coverage)==len(cases)
    assert len(coverage)==33 and len({r['case_id'] for r in cases})==len(cases)
    assert len(quotes)==len(cases)*3
    for r in quotes:
        if r['status']=='FILLED_MARKOUT':
            assert np.isclose(r['net_markout_r'],r['price_markout_r']-r['commission_r']-r['slip_r'])
            assert pd.Timestamp(r['marked_at'])>=pd.Timestamp(r['filled_at'])+pd.Timedelta(hours=1)
        else:assert r['net_markout_r'] is None
    used=m.read(HERE/'used_tape_hashes.json')
    for path,digest in used.items():
        assert m.sha(path)==digest
        f=pd.read_parquet(path);assert f.time.is_monotonic_increasing
        assert ((f.bid>0)&(f.ask>=f.bid)).all()
    m.write(HERE/'integrity.json',dict(passed=True,single_flag_only=True,baseline_artifacts_unchanged=True,
        signals_reproduced=reproduced,prefix_future_mutation_checks=causal,
        quote_records=len(quotes),quote_tapes_verified=len(used),coverage_asset_months=33,
        frozen_input_hashes_verified=True,live_changed=False))
    print(m.read(HERE/'integrity.json'))

def report():
    m=measure();p=m.verify();integrity=m.read(HERE/'integrity.json');assert integrity['passed']
    a=m.read(BASE/'signals.json');b=m.read(HERE/'signals.json');q=m.read(HERE/'quote_markouts.json')
    baseline_q=m.read(BASE/'quote_markouts.json');da=direction_rows(a);db=direction_rows(b)
    periods={};gate={}
    for period in ['DEVELOPMENT','VALIDATION']:
        aa=[r for r in da if r['period']==period];bb=[r for r in db if r['period']==period]
        ai={r['case_id']:r for r in aa};bi={r['case_id']:r for r in bb};common=sorted(set(ai)&set(bi))
        comparisons=[dict(case_id=k,baseline_risk=ai[k]['original_risk'],variant_risk=bi[k]['original_risk'],
            risk_ratio=bi[k]['original_risk']/ai[k]['original_risk'],
            raw_bps_delta=bi[k]['signed_bps']-ai[k]['signed_bps']) for k in common]
        r=dict(baseline_direction=direction_stats(aa),variant_direction=direction_stats(bb),common=len(common),
            variant_only=len(set(bi)-set(ai)),baseline_only=len(set(ai)-set(bi)),paired_geometry=comparisons,
            variant_only_direction=direction_stats([r for r in bb if r['case_id'] not in ai]),
            baseline_quotes={},variant_quotes={})
        gate[period]={}
        for label in ['OBSERVED','STRESS_1_5X','STRESS_FLOOR']:
            r['baseline_quotes'][label]=quote_stats([x for x in baseline_q if x['period']==period and x['scenario']==label])
            stats=quote_stats([x for x in q if x['period']==period and x['scenario']==label]);r['variant_quotes'][label]=stats
            if label!='OBSERVED':
                gate[period][label]=dict(at_least30fills=stats['fills']>=30,at_least15days=stats['fill_days']>=15,
                    no_unresolved=stats['unresolved']==0,positive_mean=stats['mean_conditional_markout_r'] is not None and stats['mean_conditional_markout_r']>0,
                    positive_day95_lower=stats['mean_day95'] is not None and stats['mean_day95'][0]>0)
        periods[period]=r
    support=all(all(flags.values()) for r in gate.values() for flags in r.values())
    summary=dict(periods=periods,gates=gate,total_reference=len(a),total_variant=len(b),
        variant_by_symbol={symbol:sum(r['symbol']==symbol for r in b) for symbol in m.SYMBOLS},
        monthly={mo:dict(reference=sum(r['month']==mo for r in a),variant=sum(r['month']==mo for r in b)) for mo in m.MONTHS},
        diagnostic_only=True,full_lifecycle_backtest=False)
    m.write(HERE/'summary.json',summary);m.write(HERE/'direction_details.json',dict(baseline=da,variant=db))
    decision=dict(status='FULL_LIFECYCLE_FOLLOWUP_SUPPORTED' if support else 'NO_FULL_LIFECYCLE_ESCALATION',
        edge_proven=False,live_approved=False,demo_started=False,live_changed=False,
        hypothesis='One predeclared mandatory-IFVG-off existing-entry-model comparison executed; no tuning.',
        gates=gate,scope='Conditional60min quote markouts and signal direction, not real strategy return. Quote missingness is explicit. All history previously observed; not pristineOOS.',
        action='Proceed to exact original lifecycle only if support gates pass. Otherwise retain measurement, do not optimize TP/SL or change production based on extra signal count.')
    m.write(HERE/'decision.json',decision)
    lines=['# SFP: zorunlu iFVG ile mevcut CE alternatifi karşılaştırması','',
        '**Bu çalışma tam sistem kâr backtesti değildir.** Önceden kilitlenen tek değişiklik, araştırma kopyasında USE_IFVG_ENTRY=False. Yeni giriş fonksiyonu yazılmadı; mevcut sweep-wick midpoint CE yolu kullanıldı. Breaker, HTF trendi, seans, TP/SL oranları, semboller ve süre aynı. Bayrak giriş geometrisini de etkiler; saf filtre katkısı diye yorumlanamaz.','',
        'Ocak–Haziran geliştirme; Temmuz–Kasım tarihsel kontrol. Veriler önceki araştırmalarda görüldü; temiz OOS veya ileri test değil.','',
        '| Dönem | Referans sinyal | Varyant sinyal | Referans 60dk yön R | Varyant 60dk yön R | Referans / varyant yön bp |',
        '|---|---:|---:|---:|---:|---:|']
    def fmt(x):return '—' if x is None else f'{x:.4f}'
    for period,r in periods.items():
        aa=r['baseline_direction'];bb=r['variant_direction']
        lines.append(f"| {period} | {aa['setups']} | {bb['setups']} | {fmt(aa['mean_r'])} | {fmt(bb['mean_r'])} | {fmt(aa['mean_bps'])} / {fmt(bb['mean_bps'])} |")
    lines+=['','60dk yön puanı sinyal kapanışından itibaren fiyat hareketidir; limit dolduğunu varsaymaz ve işlem getirisi değildir. R paydası farklılaşabildiği için bp ve sembol başına ham fiyat hareketi direction_details.json / summary.json içinde ayrıca verildi.','',
        '| Dönem | Senaryo | Ölçülen dolum | Dolmayan emir | Belirsiz | Dolum sonrası ortalama 60dk markout R | Stop aşılmış dolum |',
        '|---|---|---:|---:|---:|---:|---:|']
    for period,r in periods.items():
        for label,v in r['variant_quotes'].items():
            lines.append(f"| {period} | {label} | {v['fills']} | {v['status_counts'].get('NO_FILL',0)} | {v['unresolved']} | {fmt(v['mean_conditional_markout_r'])} | {v['original_stop_crossed']} |")
    lines+=['','**Markout, gerçek işlem kârı değildir.** Dolumdan60dk sonraki fiyatı gözler; ilk stopu, TP1/TP2, kısmi kapatmayı, erken çıkışı ve portföy/makro/haber engellerini uygulamaz. Pozitif markout, stop olmuş bir işlemi kazançlı gösteremez; stop aşımı ayrıca sayılır. Eksik kotasyonlar sıfır getiri veya dolmayan emir sayılmadı.','',
        'Maliyet: arşivdeki bid/ask spreadi; FX4USD/100k roundtrip ve0.2pip çıkış kayması; altın max(.08USD/ons,2×giriş×.001/100) roundtrip ve.05USD/ons çıkış kayması varsayımları. Stres1.5x; ek spread tabanı FX.5pip / altın.30USD. Komisyon ve kayma tarihsel makbuz değildir.','',
        'Karar: '+decision['status']+'. Sinyal sayısının artması tek başına başarı değildir. Giriş için yeterli ve iki dönemde de tekrarlanan maliyet sonrası kanıt olmadan TP/SL taraması yapılmayacak.','',
        f"Doğrulama: {integrity['signals_reproduced']} sinyal yeniden üretildi; {integrity['prefix_future_mutation_checks']} prefix/gelecek-mutasyonu kontrolü; {integrity['quote_records']} senaryo kaydı; {integrity['quote_tapes_verified']} kotasyon dosyası hash kontrolü. Referans dosyaları korundu. Üretim koduna, sürece, emirlere müdahale edilmedi.",
        '', 'Ayrıntı: protocol.json, hypothesis_frozen.json, summary.json, decision.json, integrity.json, direction_details.json, signals.json, quote_markouts.json.']
    (HERE/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    m.write(HERE/'status.json',dict(stage='COMPLETE',signals=len(b),live_changed=False,paid_API_spend_USD=0))
    m.write(HERE/'artifact_manifest.json',{str(p.relative_to(HERE)):m.sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ['artifact_manifest.json','run.log','run_errors.log']})
    print(json.dumps(dict(reference=len(a),variant=len(b),periods=periods,decision=decision),indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','scan','quotes','verify','report']);args=parser.parse_args()
    if args.action in ['scan','quotes']:getattr(measure(),args.action)()
    else:globals()[args.action]()
