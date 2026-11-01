"""Single frozen Asia-range context test on completed The5ers quote tapes."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib
import pandas as pd
import numpy as np
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
sys.path.insert(0,str(BASE))
import study as s
g=s.g
OUT=HERE

def read(p):return g.read(p)
def save(p,x):g.save(p,x)
def freeze():
    assert not (OUT/'protocol_frozen.json').exists()
    files=[Path(__file__),BASE/'study.py',BASE/'protocol_frozen.json',BASE/'native_frozen.json',BASE/'quote_manifest.json',BASE/'quote_manifest_before_repack.json',BASE/'outcomes.json',BASE/'results.json',BASE/'coverage_diagnostics.json',BASE/'cost_gate.py',BASE/'cost_gate/protocol_frozen.json',BASE/'cost_gate/outcomes.json',BASE/'cost_gate/results.json',BASE/'COZUM_PLANI.md',BASE/'SONUC.md',g.ROOT/'scripts/normalize_broker_history.py']
    declaration=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),
        hypothesis='Only allow the unchanged gold London ORB when the completed native London 08:00-08:15 M15 BID close finishes strictly outside the 00:00-08:00 London Asia M15 BID range, above it for long or below it for short.',
        timing='Asia half-open [00:00,08:00) London local; exactly32 consecutive M15 bars required, no missing bars or gaps. Decision uses completed native 08:00 M15 close, before any ORB entry search. Equality, opposite-side close or close within Asia range rejects day. No post-entry/current-day information.',
        unchanged='Same original g.replay for all fills, quote-side, costs, virtual BID structural stop, full2R, one attempt, deadline12:00 and EOD16:00. No summer shutdown and no 0.05R cost gate. Filter rejects whole date and no second candidate.',
        scope='Post-hoc exploratory hypothesis prompted by prior results; exact rule not previously evaluated in this project, dates were seen in other broad research. Not untouched OOS or prospective.2025 full and Sep-Dec separately, 2026 Jan-Sep partial, all21months only if complete.',
        comparison='Paired same date differences Asia-policy minus classic. Rejected otherwise-closed classic entries count zero under Asia policy. Unknown quote/native/Asia coverage excluded from paired estimand and block interval and listed; never imputed. Original classic outcome stays in comparator.',
        costs='Use all three frozen1x,1.5x,2x scenarios; 1.5x primary. Same hypothetical commission envelope and assumed 0.05/ounce/side slippage;2025 tariff not verified.',
        gates='Do not select threshold or season. Report all periods, every scenario, trade counts, PF, paired delta, 95% circular5weekday bootstrap; separately disclose smallN. A positive point estimate with CI crossing0 or <100 trades is candidate only, not demonstrated edge. No live promotion.',
        frozen_source_hashes={str(p):g.sha(p) for p in files},live_approved=False,orders_sent=False)
    save(OUT/'protocol_frozen.json',dict(declaration=declaration))
    sources=OUT/'frozen_sources';sources.mkdir()
    for i,p in enumerate(files):(sources/f'{i:02}_{p.name}').write_bytes(p.read_bytes())
    print('ASIA_PROTOCOL_FROZEN',flush=True)

def evaluate():
    protocol=read(OUT/'protocol_frozen.json')['declaration']
    for path,digest in protocol['frozen_source_hashes'].items():assert g.sha(Path(path))==digest,path
    native=pd.read_parquet(BASE/'gold_m15.parquet');native.index=g.broker_to_utc(pd.to_datetime(native.time,unit='s',utc=True))
    baseline=read(BASE/'outcomes.json');rows=[];features=[]
    for date in g.dates(s.MONTHS):
        london=pd.Timestamp(date+' 00:00',tz='Europe/London').tz_convert('UTC')
        times=pd.date_range(london,london+pd.Timedelta(hours=8),freq='15min',inclusive='left')
        asia=native[native.index.isin(times)]
        daybaseline=[r for r in baseline if r['date']==date]
        if not daybaseline:raise AssertionError('Missing frozen comparator day '+date)
        meta_status=daybaseline[0]['outcome']['status']
        complete=len(asia)==32 and asia.index.equals(times)
        if complete:
            hi=float(asia.high.max());lo=float(asia.low.min())
            openbar=native.loc[london+pd.Timedelta(hours=8)] if london+pd.Timedelta(hours=8) in native.index else None
            if openbar is None:complete=False
        if not complete:
            feature=dict(status='BLOCKED_ASIA_FEATURE',bars=len(asia))
        else:
            f=openbar
            signal=int(np.sign(f.close-f.open))
            matched=[x['outcome'] for x in daybaseline if x['scenario']=='STRESS_1.5x']
            direction=matched[0].get('direction') if matched and matched[0].get('status')=='CLOSED' else signal
            allow=(hi is not None and lo is not None and signal!=0 and direction==signal and ((direction==1 and float(f.close)>hi) or (direction==-1 and float(f.close)<lo)))
            feature=dict(status='ELIGIBLE' if allow else 'REJECT_ASIA_CONTEXT',bars=32,asia_high=hi,asia_low=lo,opening_close=float(f.close),opening_direction=signal,orb_direction=direction,allowed=bool(allow))
        features.append(dict(date=date,**feature))
        for b in daybaseline:
            status=b['outcome']['status']
            if status in g.UNKNOWN:
                outcome=dict(status=status)
            elif feature['status']=='BLOCKED_ASIA_FEATURE':
                outcome=dict(status='BLOCKED_ASIA_FEATURE')
            elif not feature.get('allowed',False):
                outcome=dict(status='NO_ENTRY_ASIA_CONTEXT')
            else:
                outcome=b['outcome'].copy()
            rows.append(dict(date=date,scenario=b['scenario'],outcome=outcome,asia=feature['status']))
    groups={'2025_full':s.MONTHS[:12],'2025_new_SepDec':s.MONTHS[8:12],'2026_JanSep_partial':s.MONTHS[12:],'all21months':s.MONTHS}
    result={}
    for group,months in groups.items():
        calendar=g.dates(months);result[group]={}
        for name,mult in g.SCENARIOS:
            br=[r for r in baseline if r['scenario']==name and r['date'][:7] in months]
            vr=[r for r in rows if r['scenario']==name and r['date'][:7] in months]
            unknown=sorted({r['date'] for r in vr if r['outcome']['status'] in g.UNKNOWN|{'BLOCKED_ASIA_FEATURE'}})
            if unknown:
                common=[d for d in calendar if d not in unknown]
                bc=[r for r in br if r['date'] not in unknown];vc=[r for r in vr if r['date'] not in unknown]
                a=s.v.stats(bc,common);b=s.v.stats(vc,common)
                delta=pd.Series(0.,index=common)
                for x in bc:delta.loc[x['date']]-=x['outcome'].get('net_r',0.)
                for x in vc:delta.loc[x['date']]+=x['outcome'].get('net_r',0.)
                result[group][name]=dict(complete=False,unknown_dates=unknown,known_common_calendar_days=len(common),classic_known_common=a,asia_known_common=b,paired_known_common_delta_r=float(delta.sum()),paired_known_common_ci95=g.block_ci(delta),note='Common resolved days only; not full-period total or edge evidence.')
            else:
                a=s.v.stats(br,calendar);b=s.v.stats(vr,calendar);delta=pd.Series(0.,index=calendar)
                for x in br:delta.loc[x['date']]-=x['outcome'].get('net_r',0.)
                for x in vr:delta.loc[x['date']]+=x['outcome'].get('net_r',0.)
                result[group][name]=dict(complete=True,classic=a,asia=b,paired_delta_r=float(delta.sum()),paired_delta_ci95=g.block_ci(delta))
    save(OUT/'features.json',features);save(OUT/'outcomes.json',rows)
    save(OUT/'results.json',dict(results=result,live_approved=False,orders_sent=False))
    for path,digest in protocol['frozen_source_hashes'].items():assert g.sha(Path(path))==digest,path
    save(OUT/'integrity.json',dict(source_hashes_reverified=True,baseline_row_parity=len(rows)==len(baseline),days=len(features),strategy_engine='unchanged; exact frozen outcomes copied only on Asia-eligible days'))
    report()

def report():
    res=read(OUT/'results.json');features=read(OUT/'features.json')
    lines=['# London XAUUSD ORB: Asya araligi baglami','',
      '**Hipotez:** London 08:00-08:15 M15 kapanisi yonunde Asya 00:00-08:00 araligini terk etmisse ORB denemesi yap. Tam32nativeM15 bar yoksa o gunu bilinmeyen say.',
      '','Esik veya seans degistirilmedi; yaz tatili ve maliyet filtresi eklenmedi. Giris/stop/2R/EOD ve maliyetler orijinal motorla ayni. Bu kural daha once genis arastirmada tarihleri gorulmus veride post-hoc kesif hipotezidir; ileri test/OOS degildir.','',
      '| Donem | Maliyet | Bilinen gun | Uygun gun | Islem | NetR | PF | Eslesik fark | Fark CI95 |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for period,groups in res['results'].items():
      for scenario,m in g.SCENARIOS:
        x=groups[scenario]
        if x['complete']:
          a=x['classic'];b=x['asia'];ng=sum(f['date'][:7] in (s.MONTHS[:12] if period=='2025_full' else s.MONTHS[8:12] if period=='2025_new_SepDec' else s.MONTHS[12:] if period=='2026_JanSep_partial' else s.MONTHS) and f['status']=='ELIGIBLE' for f in features)
          lines.append(f"| {period} | {m:g}x | tam | {ng} | {b['fills']} | {b['net_r']:+.2f} | {b['pf']:.2f} | {x['paired_delta_r']:+.2f} | [{x['paired_delta_ci95'][0]:+.2f},{x['paired_delta_ci95'][1]:+.2f}] |")
        else:
          a=x['classic_known_common'];b=x['asia_known_common']
          candidates=sum(f['date'][:7] in (s.MONTHS[12:] if period=='2026_JanSep_partial' else s.MONTHS) and f['status']=='ELIGIBLE' and f['date'] not in x['unknown_dates'] for f in features)
          lines.append(f"| {period} | {m:g}x | {x['known_common_calendar_days']}/{len(s.g.dates(s.MONTHS[:12] if period=='2025_full' else s.MONTHS[8:12] if period=='2025_new_SepDec' else s.MONTHS[12:] if period=='2026_JanSep_partial' else s.MONTHS))} | {candidates} | {b['fills']} | {b['net_r']:+.2f}* | {b['pf']:.2f}* | {x['paired_known_common_delta_r']:+.2f}* | [{x['paired_known_common_ci95'][0]:+.2f},{x['paired_known_common_ci95'][1]:+.2f}]* |")
    lines += ['', '* Tam donem degil: bilinmeyen gunler her iki politikadan da cikarilmis ortak gun alt orneklemi.', '',
      'Uygun gun sayisi yuksek getiri demek degildir. Filtresiz ORB ile ayni takvim gunlerinde fark ve bootstrap belirsizligi karar icin onemlidir. Tam veri olmayan2026/21aylik toplamlar ileri surulmez.',
      '',f"Asya bar kapsami: {sum(f['status']=='ELIGIBLE' for f in features)} uygun, {sum(f['status']=='REJECT_ASIA_CONTEXT' for f in features)} baglam reddi, {sum(f['status']=='BLOCKED_ASIA_FEATURE' for f in features)} eksik aralik.",'',
      '2026-03-16 icin eski karsilastirici native/quote kalitesi nedeniyle zaten bilinmeyendi.2026-04-03te 32 Asya bar bulunmadigi icin yeni filtre sonucu da bilinmeyen kalir. Komisyon2025numeric tarifesi dogrulanmamistir. Short stop halen sanal BID tetik/ASK cikistir.',
      '', '**Yorum:** Nokta tahmin pozitif olsa da 100+ islem, guven araliginin sifirin ustu, donemler arasi tutarlilik olmadan aday Edge diye adlandirilmaz. Olumsuzsa, tum ORB ailesini degil bu Asya-kontekst varyantini eler.','',
      'Siradaki onceden tanimlanan aday M1 kapanis/retest/tepe-dip kirilimidir; bu calisma sonucuna gore kural veya esik secilmeyecektir. Canli emir yok.']
    (OUT/'SONUC.md').write_text('\n'.join(lines),encoding='utf8')
    save(OUT/'completion.json',dict(status='COMPLETE_RESEARCH_WITH_KNOWN_COVERAGE_LIMITS',days=len(features),orders_sent=False,live_approved=False,sha256={n:g.sha(OUT/n) for n in ['protocol_frozen.json','features.json','outcomes.json','results.json','integrity.json','SONUC.md']}))

if __name__=='__main__':freeze();evaluate()
