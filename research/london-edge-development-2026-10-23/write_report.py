from pathlib import Path
import hashlib,json,sys
import pandas as pd
BASE=Path(__file__).resolve().parent;CLASSIC=BASE.parent/'london-classic-orb-2026-10-23'
mechanics=json.loads((BASE/'results.json').read_text());classic=json.loads((CLASSIC/'results.json').read_text())
for folder in [BASE,CLASSIC]:
    p=json.loads((folder/'protocol_frozen.json').read_text())['declaration']
    for group in ['files','inputs']:
        for path,digest in p[group].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    rows=json.loads((folder/'outcomes.json').read_text())
    pd.DataFrame([{k:v for k,v in x.items() if k!='outcome'}|x['outcome'] for x in rows]).to_csv(folder/'outcomes.csv',index=False)
lines=['# London ORB: dürüst değerlendirme ve kontrollü geliştirme','',
'**Sonuç: ORB ailesinin bazı piyasalarda kârlı geçmiş araştırmaları vardır; fakat bizim London Forex uygulamasında, bu turdaki beş sabit varyantın hiçbirinde maliyet sonrası pozitif edge doğrulanmadı. Üretim stratejisi bu sonuçlara göre değiştirilmedi.**','',
'## ORB ile kazanılabiliyor mu?','',
'Zarattini/Barbon/Aziz çalışması, 2016–2023 ABD hisselerinde özellikle olağandışı açılış hacmiyle seçilen hisselerde olumlu maliyet sonrası sonuçlar bildiriyor. Bu, sıradan her enstrümanda aralık kırılımının kârlı olduğu veya London Forex için aynı avantajın bulunduğu anlamına gelmez. Makale bir tarihsel backtesttir; kişisel gerçekleşmiş veya gelecekte garanti getiri belgesi değildir. [Birincil araştırma](https://alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content).','',
'Forex aracıların tick hacmi, borsadaki toplam işlem hacmi değildir. Ayrıca London açılışında hacim Asya saatlerinden doğal olarak daha yüksek olabilir; son20mum ortalamasına göre2x olmak, o günün tarihsel London açılışlarına göre olağandışı olduğunu göstermez. Bu nedenle aynı saatle hacim karşılaştırması ayrıca kuruldu.','',
'## Önce giriş/çıkış mekanizmasını ayırdık','',
'Üç hipotez sonuçlardan önce sabitlendi. Hepsi aynı36London adayından başlar ve her parite-günde ilk geçerli tek denemeyi kullanır. Hedefler gerçek giriş/stop mesafesinden minimum1.2R/2Ryi koruyacak biçimde dışa yuvarlandı. Araştırma fiyat adımı varsayımı FX için0.00001,JPY için0.001; gerçek broker sembol-spesifikasyonunun doğrulaması değildir.','',
'| Varyant | 1,5x dolum | 1,5x netR | PF | 2x netR |','|---|---:|---:|---:|---:|']
names={'ROUNDING_REFERENCE':'Yuvarlaması düzeltilmiş referans','NO_REACTION_EXIT':'Aynı giriş, tepki çıkışı kaldırılmış','M1_BREAK_CONFIRMATION':'Retest + M1 tepe/dip kapanış teyidi'}
for name,v in mechanics.items():
    a=v['costs']['1.5'];b=v['costs']['2.0']
    lines.append(f"| {names[name]} | {a['closed_filled']} | {a['net_r']:+.2f} | {a['pf']:.2f} | {b['net_r']:+.2f} |")
lines+=['','Referansta33geçerli günlük deneme vardır. Adayları matematiksel olarak geçerli hale getirmek önceki15denemeyi33e çıkarır; bu yüzden eski−2.84R ile yeni referans doğrudan aynı işlem sepeti değildir. Tepki çıkışı ablasyonu ise bu yeni referansla aynı aday/girişlerde kıyaslanır; tek başına çıkışı kaldırmak pozitif beklenti sağlamadı.','',
'M1 tanımı: limit seviyesine temas görüldükten sonraki bir M1 mumu, önceki tamamlanmış M1 mumunun tepe/dibini işlem yönünde kapanışla aşar; giriş sonraki M1 açılışındadır. Aynı temas mumunda teyit yazılmaz, gelecek mumun yüksek/düşük bilgisi girişi seçmez. İlk stop korunur; yeni giriş mesafesinden hedefler yeniden hesaplanır. Girişten önce stop yapısı kırılırsa setup iptal olur. Bu, kullanıcının görsel swing seçiminin birebir taklidi değil, açık mekanik araştırma tanımıdır.','',
'Bu üç test mevcutpaper sürtünme modelini kullanır; gerçek bid/ask belgesi değildir. Bütün gruplarda brütR de negatifti: zayıflık yalnız ücret düşülmesinden kaynaklanmıyor.','',
'## Sonra klasik ORByi ayrı ölçtük','',
'M15açılış aralığı08:00–08:15Europe/London. İlk mum yeşilse yalnız üst aralık kırılımına long, kırmızıysa yalnız alt kırılıma short. Parite başına ilk kırılım, giriş12:00den önce; stop karşı bantta; pozisyonun tamamı2Rhedefte veya16:00London’da çıkar. TP1/BE/trailing ve retest yoktur. Bu, önceki botun aynısı değil; tek bir sabit yeni strateji hipotezidir.','',
'Filtresiz kontrol ve RVOL≥1 sürümü birlikte raporlanır. RVOL, bugünün ilk15dakika tick hacminin önceki14mevcutLondon08:00M15hacmine oranıdır. Bugün/geçmiş sonrasındaki hacim, normalizasyon paydasına girmez. Eşik optimizasyonu yapılmadı.','',
'| Klasik ORB | 1,5x dolum | 1,5x netR | PF | 2x netR |','|---|---:|---:|---:|---:|']
for name,c in classic.items():
    a=c['1.5'];b=c['2.0'];label='Filtresiz kontrol' if name=='CLASSIC_ALL' else 'Aynı saat RVOL≥1'
    lines.append(f"| {label} | {a['fills']} | {a['net_r']:+.2f} | {a['pf']:.2f} | {b['net_r']:+.2f} |")
lines+=['','Altı parite×63hafta içi gün=378parite-gününde açılış girdileri ve08:15–16:00LondonM1gridi mevcuttu. Bu örneklemde eksik seans nedeniyle dışlama olmadı; doji veya12:00den önce kırılma olmaması ayrıca kaydedildi. M1mumu içindeki sıralama belirsizse stop öncelikli; giriş mumunda hedef kredisi yok; stop üzerinden gap olursa daha kötü açılış fiyatı kullanılır. Gece pozisyonu yoktur.','',
'### Maliyet modeli','',
'The5ers güncel resmi sayfası Forex için4USD/lot round-trip komisyon ve normal koşullarda majörlerde0.2–0.9pip spread bildirir; tarihsel2025kişisel spread serisi bu değildir. [Resmi maliyet kaynağı](https://the5ers.com/faqs/what-are-the-spreads-and-commissions/).','',
'Klasik testte baştan sabitlenen temel senaryo:1pip sentetik spread, her yönde0.1pip kayma ve100000birim başına4USDround-trip komisyon. Ücret quote para birimine çevrilir; USD-bazlı paritelerde giriş kuru yaklaşımı kullanılır. BidM1den sentetikask üretilir.1.5x/2x stres spread, kayma ve komisyonu birlikte çarpar; giriş fiyatı, risk mesafesi, hedef ve kapanışlar bu yüzden değişebilir. Gerçek emir defteri veya geçmiş bid/ask replikasyonu değildir. İki test motorunun maliyet varsayımları farklıdır; netRleri tek bir portföyde toplamayın.','',
'## Neyi geliştirdik, neyi geliştiremedik?','',
'Araştırma sürümünde RR/fiyat adımı tutarlılığı, nedensel M1teyit yolu, karşılaştırılabilir tepki-kuralı ablasyonu, aynı-saat hacim özelliği ve gap/spread/komisyonu açık klasikORBmotoru hazırlandı. Bunlar sistemin ölçülebilirliğini geliştirir. Kârlılığı garanti eden bir kod değişikliği bulunmadı. Bu sonuçlarla LondonForexORB’yi üretime terfi ettirmek veya rastgele yeni eşikler taramak doğru olmaz.','',
'Bütün varyantlar aynı görülmüş üç aydadır; yeni testler önceki denemeleri unutturan bağımsız kanıtlar değildir. Sonuçlar birimR fırsat toplamlarıdır, eşzamanlı para/risk/marjı uygulayan gerçek portföy getirisi değildir.100işlemden fazla örnek olması tek başına edge kanıtı değildir.5günlükblokbootstrap aralıkları results.jsonda bulunur; geçmiş çoklu seçimleri düzeltmez.','',
'Bir sonraki anlamlı kapı, yeni kuralları tekrar ayarlamadan farklı dönemlerde ve gerçek bid/ask+maliyet girdileriyle sınamaktır. Açılış hacmi ve gün seçimi avantajının başka piyasada bulunması da ayrı evren/veri hipotezi olarak ele alınmalıdır. ABDstocks-in-play çalışmasını uygulamak için geçmiş hisse evreni, M1hacim, şirket olayları ve shortgerçekleşmeleri gerekir; elimizdeki altıForexparite bunu temsil etmez.','',
'## Doğrulama ve dosyalar','',
'Yeni12nedensellik/muhasebe testi geçti. M1teyit için sonraki açılış, açık mum/futureextreme ayrımı ve stop önceliği; klasikORB için maliyetliSL/TP, gap, eksik dakika, saat sınırı, aynı-saatRVOLnedenselliği ve shortaskstop kontrol edildi. Kaynak ve bütünM1/M15veri hashleri sonuç sonunda yeniden doğrulandı. Kaynakların dondurulmuş kopyaları frozen_sources/ altında.','',
'Üretim kodu, çalışan bot ve canlı emir ayarları bu turda değiştirilmedi. Yeni otomasyon veya bildirim başlatılmadı.','',
'Bu klasörde protocol_frozen.json, results.json, outcomes.json/CSV ve confirmation_audit.json üç mekanik varyantı içerir. ../london-classic-orb-2026-10-23/ klasörü klasikORBprotokolünü, iki kontrol sonucunu, seans özelliklerini ve işlem dökümünü içerir.']
(BASE/'SONUC.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print('Five variants fully reported; source/data hashes verified')
