"""Post-hoc summer shutdown diagnostic using completed immutable trade ledgers."""
from pathlib import Path
import sys,json,hashlib
from datetime import datetime,timezone
BASE=Path(__file__).resolve().parent
VALID=BASE.parent/'london-gold-validation-2026-10-24'
sys.path.insert(0,str(VALID))
import validate as v

def run():
    sources=[Path(__file__),VALID/'validate.py',v.OLD/'study.py',v.OLD/'outcomes.json',VALID/'outcomes.json',VALID/'completion.json',VALID/'results.json']
    declaration=dict(created_utc=datetime.now(timezone.utc).isoformat(),hypothesis='No entries June July August; all other rules/costs unchanged.',
        classification='POST_HOC descriptive diagnostic, prompted after observing August losses. Not untouched OOS or seasonality evidence.',
        sample='Only Jan-Aug2025 currently replayed; removing JunAug leaves JanMay only. No SeptemberDecember result or second year inferred.',
        method='Filter immutable outcomes by calendar month, no new simulations/orders. Fixed comparator allJanAug, shutdown JunAug, excluded summer separate. Same circular5weekday10000seed173 CI. Full calendar disabled days zero; active calendar CI also reported. May-removed diagnostic predeclared here.',
        live_approved=False,hashes={str(p):v.g.sha(p) for p in sources})
    frozen=BASE/'protocol_frozen.json'
    if frozen.exists():
        declaration=v.g.read(frozen)
        for path,digest in declaration['hashes'].items():assert v.g.sha(Path(path))==digest,path
    else:v.g.save(frozen,declaration)
    complete=v.g.read(VALID/'completion.json')
    for name,digest in complete['hashes'].items():assert v.g.sha(VALID/name)==digest,name
    rows=v.g.read(v.OLD/'outcomes.json')+v.g.read(VALID/'outcomes.json')
    assert len(rows)==3*173
    calendar=v.g.dates()+v.dates();active_dates=[d for d in calendar if d[5:7] not in ['06','07','08']]
    summer_dates=[d for d in calendar if d[5:7] in ['06','07','08']]
    result={}
    for name,m in v.g.SCENARIOS:
        allrows=[r for r in rows if r['scenario']==name]
        active=[r for r in allrows if r['date'][5:7] not in ['06','07','08']]
        summer=[r for r in allrows if r['date'][5:7] in ['06','07','08']]
        full=v.stats(allrows,calendar);filtered=v.stats(active,calendar);off=v.stats(summer,summer_dates)
        assert abs(full['net_r']-filtered['net_r']-off['net_r'])<1e-9
        active_stats=v.stats(active,active_dates)
        net_without_may=sum(r['outcome'].get('net_r',0) for r in active if r['date'][5:7]!='05')
        result[name]=dict(all_jan_aug=full,summer_off=filtered,excluded_summer=off,
            active_calendar_ci95=active_stats['block_total_ci95'],active_months=active_stats['by_month'],
            summer_off_without_may_r=net_without_may,may_share_of_net=active_stats['by_month']['2025-05']/filtered['net_r'] if filtered['net_r'] else None)
    for path,digest in declaration['hashes'].items():assert v.g.sha(Path(path))==digest,path
    v.g.save(BASE/'results.json',dict(results=result,edge_proven=False,seasonality_proven=False,production_changed=False,orders_sent=False))
    text='''# Yaz aylarinda kapatma: sonradan onerilen hipotez

Haziran-Temmuz-Agustos kapali kabul edildi. Giris, cikis ve maliyet kurallari degismedi. Mevcut veri yalniz Ocak-Agustos2025: bu filtre geriye sadece Ocak-Mayis birakir. Eylul-Aralik veya baska yil sonucu uretilmedi.

| Maliyet | Hepsi (151 islem) | Yaz kapali | Islem | PF | Max DD (birim R) |
|---|---:|---:|---:|---:|---:|
'''
    for name,m in v.g.SCENARIOS:
        a=result[name]['all_jan_aug'];b=result[name]['summer_off']
        text+=f"| {m:g}x | {a['net_r']:+.2f}R | {b['net_r']:+.2f}R | {b['fills']} | {b['pf']:.2f} | {b['max_dd_unit_r']:.2f}R |\n"
    a=result['STRESS_1.5x'];b=a['summer_off']
    text+=f'''
1.5x yaz haric net {b['net_r']:+.2f}R, Mayis payi %{a['may_share_of_net']*100:.1f}; Mayis da cikarilirsa {a['summer_off_without_may_r']:+.2f}R. En iyi bes islem cikarilirsa {b['without_best5']:+.2f}R.

1.5x %95 blok bootstrap araligi tum Ocak-Agustos takviminde yazin sifir islemle {b['block_total_ci95']}; sadece aktif Ocak-Mayis takviminde {a['active_calendar_ci95']}. Her ikisi de gorulen bu orneklemden uretilen kesifsel araliklardir.

Haziran ve Temmuz karli, Agustos zararlidir. Dolayisiyla tek bir Agustos kaybindan tum yazlarin kotu oldugu sonucu cikmaz. Bu filtre zarari gorerek onerildigi ve geriye ilk gelistirme doneminin bir alt kumesini biraktigi icin bagimsiz dogrulama sayilamaz. Eylul-Aralik yoklugu butun yillik sonuca genellenemez.

Karar: tarihsel sonuc iyilesiyor, fakat mevsimsel edge kanitlanmadi. Uretim botuna yaz kapatma filtresi eklenmedi, emir gonderilmedi. Sonraki dogru sinama: ayni Haziran-Agustos kapatma kuralini degistirmeden baska tam yillarda acik-kapali karsilastirmak. 2025 sayisal komisyon belirsizligi ve modellenen fill/slippage siniri devam ediyor.
'''
    (BASE/'SONUC.md').write_text(text,encoding='utf8')
    v.g.save(BASE/'completion.json',dict(status='COMPLETE_POST_HOC_DIAGNOSTIC',source_hashes_verified=True,arithmetic_verified=True,hashes={n:v.g.sha(BASE/n) for n in ['analyze.py','protocol_frozen.json','results.json','SONUC.md']}))
    print(json.dumps(result,indent=2))

if __name__=='__main__':run()
