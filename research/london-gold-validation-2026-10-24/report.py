"""Post-run arithmetic, direct clock diagnostics and human-readable report."""
import validate as v
import pandas as pd
import numpy as np

v.verify()
r=v.load('results.json');rows=v.load('outcomes.json');old=v.g.read(v.OLD/'outcomes.json')
qa=v.load('native_qa.json');manifest=v.load('quote_manifest.json')
assert len(qa)==44 and all(q['price_direction_match'] and q['volume_match'] for q in qa)
assert len(rows)==132
for name,m in v.g.SCENARIOS:
    total=sum(x['outcome'].get('net_r',0) for x in rows if x['scenario']==name)
    prior=sum(x['outcome'].get('net_r',0) for x in old if x['scenario']==name)
    assert abs(total-r['reserve'][name]['net_r'])<1e-10
    assert abs(prior+total-r['combined'][name]['net_r'])<1e-10
    assert abs(sum(r['reserve'][name]['by_month'].values())-total)<1e-10
    assert r['reserve'][name]['fills']==38
f=pd.read_parquet(v.BASE/'clock_eurusd_m15.parquet')
f.index=v.g.broker_to_utc(pd.to_datetime(f.time,unit='s',utc=True));value=np.log(f.close/f.open)
ref=pd.read_csv(v.g.REFERENCE);ref.index=pd.to_datetime(ref.datetime,utc=True);reference=np.log(ref.close/ref.open)
scores=[];winners=[]
for date in v.dates():
    day=value[value.index.strftime('%Y-%m-%d')==date];daily=[]
    for shift in range(-3,4):
        z=day.copy();z.index+=pd.Timedelta(hours=shift)
        joined=pd.concat([z.rename('broker'),reference.rename('reference')],axis=1).dropna()
        if len(joined)>=32:daily.append(dict(date=date,shift=shift,n=len(joined),corr=float(joined.broker.corr(joined.reference))))
    scores+=daily;daily.sort(key=lambda x:x['corr'],reverse=True)
    if len(daily)>1 and daily[0]['corr']>=.7 and daily[0]['corr']-daily[1]['corr']>=.15:winners.append(daily[0])
assert all(x['shift']==0 for x in winners)
v.save('postrun_checks.json',dict(arithmetic_passed=True,native_prices_and_volume_passed=True,tests='9 passed',
    direct_clock_winners=winners,direct_clock_scores=scores,rows=len(rows),ticks=sum(x['rows'] for x in manifest['files'].values()),
    note='Direct reference only two overlapping dates; prior independent clock QA supplies wider regime evidence. No gold independent feed. No live approval.'))
text='''# London XAUUSD ORB: zaman ayrimli dogrulama

**Karar: Bu surumde edge dogrulanmadi. Ayri donem testi basarisiz. Canliya gecis yok.**

Ilk Ocak-Haziran testi istatistiksel esigi gecmemisti. Kullanici talebiyle Temmuz-Agustos icin ayri protokol, sonuclar hesaplanmadan once donduruldu. Eski protokol ve sonuc degistirilmedi. Bu aylar daha eski genis arastirmalarda goruldugu icin tamamen dokunulmamis OOS veya ileri test sayilamaz.

08:00-08:15 London BID araligi, acilis mumunun yonunde ilk kirilim, 12:00 oncesi tek giris, karsi bant sanal stop, 2R hedef ve 16:00 cikis aynen korundu. Gercek broker bid/ask gecmisi kullanildi; emir gerceklesmeleri ve slippage modellenmistir. Short stop BID ile tetiklenen sanal stop, ASK cikisidir; broker ASK stop emriyle esit degildir.

| Maliyet | Temmuz-Agustos (38 islem) | PF | Ocak-Agustos (151 islem) | PF |
|---|---:|---:|---:|---:|
'''
for name,m in v.g.SCENARIOS:
    a=r['reserve'][name];b=r['combined'][name]
    text+=f"| {m:g}x | {a['net_r']:+.2f}R | {a['pf']:.2f} | {b['net_r']:+.2f}R | {b['pf']:.2f} |\n"
p=r['combined']['STRESS_1.5x'];a=r['reserve']['STRESS_1.5x']
text+=f'''
1.5x maliyetle Temmuz {a['by_month']['2025-07']:+.2f}R; Agustos {a['by_month']['2025-08']:+.2f}R. Birlesik %95 bes-isgunu blok bootstrap araligi [{p['block_total_ci95'][0]:+.2f}R, {p['block_total_ci95'][1]:+.2f}R]. En iyi bes islem cikinca birlesik sonuc {p['without_best5']:+.2f}R. Mayis haric toplam {p['net_r']-p['by_month']['2025-05']:+.2f}R. Bunlar ek tani testleridir; yeni filtre secmek icin kullanilmadi.

44/44 isgunu kapsandi: 38 islem, 6 giris yok. Yerel M15 acilis fiyati, yonu ve BID hacmi 44/44 eslesti. Aritmetik, kaynak ve tape hash kontrolleri gecti; mevcut replay motorunun 9 testi gecti. Yeni dogrudan EURUSD referansi ortusmesi yalniz iki gun; daha genis broker saat kaniti ilk arastirmanin bagimsiz kontrolunden gelir. Bagimsiz altin fiyat akisi dogrulamasi yok.

2025 komisyon tarifesi hala dogrulanmadi; onceki dondurulmus muhafazakar komisyon modeli ve taraf basina $0.05/ons slippage aynen kullanildi. R, birim baslangic riski; hesap yuzde getirisi degildir. Mevcut terminalin otomatik islem izni acikti; bu arastirma ayar degistirmedi veya emir gondermedi.

Bu yalın ORB surumu aktif edge adayi olarak elenir. Bu sonuc tum ORB fikirlerinin imkansizligini kanitlamaz; mevcut kuralin donemler arasi tasinmadigini gosterir. Sonuclari gordukten sonra filtre eklemek yeni bir hipotezdir ve yeni, kullanilmamis donem gerektirir.
'''
(v.BASE/'SONUC.md').write_text(text,encoding='utf8')
print('POSTRUN_PASS',len(winners),'DIRECT_CLOCK_DAYS')
