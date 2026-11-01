# Dolum gecikmesi: sabit15dakikalık limit ömrü araştırması

**Karar: TTL15_NOT_CONFIRMED. Canlıya terfi yok.** Bütün aşamalarda aynı15dakika sınırı ve kontrol grubu korundu. Sınır eşiği veya parite/ay seçimi sonuçlara göre taranmadı.

## Deney

Sadece bekleyen limit emrin geçerlilik süresi değişti:

-Referans: en fazla240dakika; London12:00 daha erkense orada biter.
-Aday: en fazla15dakika; London12:00 daha erkense orada biter.

Emir `[sinyalin kullanılabilir olduğu an, son geçerlilik anı)` aralığında aktiftir. **Tam15.dakikadaki temas kabul edilmez.** Önceki betimleyici≤15dakika grubu ile bu sınır aynı tanım değildir; eşitlik davranışı sonuçlardan önce sabitlendi. İlk15dakikada dolmuş pozisyon sonrasında normal çıkış kurallarıyla takip edilir;15.dakikada zorla kapanmaz. İptal edilen emir o günün denemesini tüketir; başka adayla değiştirilmez.

Giriş,ilkstop,TP1/TP2,olumsuztepkiçıkışı,kısmi kapatma,BE/trailing veLondon16:30araştırma kapanışı aynı. Stopönceliği ve dolum-mumuTPyasağı korunur. Bu motor üretim botunun tüm makro/haber/SFP/ortakrisk kararları değildir; setup araştırmasıdır. Altın yok.

Maliyetler aynı varsayımlı sözleşme:0.2/0.5/0.9/1.5pip sabitspread,100binbirime4USDround-trip komisyon,0.2pip olumsuz piyasa çıkış kayması. BidM1 gerçektir; tarihsel ask,hesap komisyonu ve kayma gerçekleşmeleri doğrulanmadı. NetR birim ilk fiyat riskine normalize edilmiş fırsat toplamıdır; hesap/portföy getirisi değildir.

## Aşama1: önceki58kurulumda ölçüm

Ocak/Kasım33 ve Şubat/Mart25kurulum değişmeden alındı. Hepsi daha önce görüldü; burada yeni OOS iddiası yok. İki süre için de bütün kurulumlar korunur; iptal/no-fill sıfır getiridir, kazanan işlem değildir.

|Spread|Referans dolum|Referans netR|15dk dolum|15dk netR|FarkR|
|---|---:|---:|---:|---:|---:|
|0.2pip|54|+0.226|42|+1.743|+1.517|
|0.5pip|54|+0.317|42|+3.661|+3.344|
|0.9pip|53|-3.032|39|+0.374|+3.407|
|1.5pip|53|-6.406|39|+0.720|+7.125|

Ana0.5pip senaryosunda 15dk sınırı12geçdolumu eliyor:11zararlı,1kârlı. Toplam4.307Rkayıp engellenirken0.963Rkâr kaçırılıyor; fark+3.344R. Bu, düşürülen işlemlerin hesapta başka işlemle değiştirildiği anlamına gelmez.

Şubat/Mart özelinde23dolum19a indi; dörtelenen dolum da ana ve stres senaryolarında zararlı. Ana sonuç−4.874Rden−3.419Rye iyileşti; **iki ay da hâlâ eksi**.0.2pip senaryosunda Şubat/Mart biraz kötüleşti (−1.707→−1.930R); iyileşme her örneklem/maliyette geçerli değil.

Dört ayın ana15dk sonucu+3.661R; fakat Ocak+10.181R,Şubat−2.064R,Mart−1.355R,Kasım−3.101R. Sadece toplam artıya bakmak rejim bağımlılığını gizler.232önceki referans kaydı birebir yeniden üretildi; kalan erken dolumların bütün yaşam döngüsü ve netRsi değişmedi. Toplam464replaykaydı bağımsız464işlem değildir. Çözümlenmemiş replay:0.

## Aşama2: ayrı dört ayda kontrol

İlk sonuç görüldükten sonra aynı15dk süresi **Nisan,Mayıs,Eylül,Ekim2025** için ayrı followup_protocol.json ile sabitlendi. Aylar mevcut tam tick arşivi olduğu için birlikte seçildi; yeni bu kurulumların sonuçları önceden okunmadı. Fiyatlar başka bir klasikORB araştırmasında kullanılmıştır; dolayısıyla tamamen dokunulmamış proje-geneli OOS veya prospektifforward değildir. Bu süre kuralının ek dönem kontrolüdür.

Altıparite×89haftaiçigün=534parite-günü. AsyaM15,Londonaralığı/giriş gridleri ve geçmişATR girdileri kontrol edildi; yeni65ilk günlük kurulum seçildi. Tüm pariteler ve aylar korunur. NativeH1/M15bağlamı; mevcut tick arşivi ve önbellekteki16–16:31kuyruğundan M1. İnterpolasyon yok. Her paritede89×511=45479LondonM1satırı. Veri eksikleri veya işlem kuyruğu bilinmezliği netkârla doldurulmadı.

|Spread|Referans dolum|Referans netR|15dk dolum|15dk netR|FarkR|
|---|---:|---:|---:|---:|---:|
|0.2pip|48|-10.650|38|-9.067|+1.582|
|0.5pip|48|-12.548|38|-10.849|+1.699|
|0.9pip|48|-13.562|36|-12.958|+0.605|
|1.5pip|46|-12.785|35|-13.837|-1.052|

|Yeni ay|Referans0.5pip netR|15dk0.5pip netR|15dk1.5pip netR|
|---|---:|---:|---:|
|2025-04|-3.422|-3.422|-3.516|
|2025-05|-1.863|-1.893|-2.008|
|2025-09|+1.165|+0.715|-4.019|
|2025-10|-8.427|-6.248|-4.294|

## Önceden sabitlenen karar kapıları

- improves_followup_total_0.5pip: GEÇTİ
- every_followup_month_positive_0.5pip: GEÇMEDİ
- improves_followup_total_1.5pip: GEÇMEDİ
- every_followup_month_positive_1.5pip: GEÇMEDİ
- followup_no_unresolved: GEÇTİ

Başarılı aday saymak için ek dönemde hem0.5hem1.5pip altında toplamı iyileştirmesi ve dört ayın her birinde dolumla pozitif kalması istendi. Daha az zarar veya sıfır işlem başarı sayılmaz. İlk dört ayın toplamı, başarısız ek dönemleri kurtarmak için kullanılmaz. Gatesonucu olumlu olsa bile gerçek maliyet/ileri dönem kanıtı olmadan canlı onayı verilmez.

Gün-küme bootstrap aralıkları comparisons.json ve followup_comparisons.json içindedir:10000örnek,95%yüzdelik,kurulum başına eşleştirilmiş fark. Aynıgün pozisyonları birlikte çekilir. Önceki çoklu hipotezleri ve tam seri bağımlılığı düzeltmez; yeni dört ay da geriye dönüktür. Az sayıdaki silinen işleme dayalı dar aralık edge kanıtı değildir.

## Uygulanabilir çıktı

**Nihai yorum:**15dakika sınırı bağımsız bir kâr kaynağı olarak doğrulanmadı. Ek dönemde ana maliyette zarar−12.548Rden−10.849Rye düşüyor; streste−12.785Rden−13.837Rye büyüyor. Ana senaryoda elenen10geçdolumun2si kârlı,8i zararlı; streste elenen11dolumun5i kârlı,6sı zararlı. Süre sınırı kazanan fırsatları da iptal ediyor. Ek dönem eşleştirilmiş farkının gün-küme aralığı her maliyette sıfırı içeriyor.

Hızlı dolan38işlem de ana modelde−10.849R bırakıyor; komisyon düşülmeden önceki fiyat sonucu dahi−8.862R (spread/kayma hâlâ fiyat içindedir). Bu, sorunun yalnız komisyon veya geçdolum olmadığını gösterir. Bekleme süresini daha da kısaltmanın edge sağlayacağına dair sonuç yok; yeni süre taraması yapılmadı. Bu sabit15dakika kuralı üretime alınmamalı; yararlı bir gözlem alanı olarak dolum gecikmesi kaydı korunabilir. Sonraki yeni strateji araştırması bu giriş setinin yapısal yön/kurulum avantajını değiştiren açık bir hipotez gerektirir; süre/TP/SL ayarıyla kâr varmış gibi sunulamaz.

Bekleyen emre süre koyan araştırma parametresi hazır. Kural yalnız emir dolmadan önce çalışır; dolmuş zararları silmez. Geçdolum sepeti, kaçırılan kazançlar ve önlenen kayıplar ayrı kaydedilir. Bu, sürenin risk etkisini izlenebilir hale getirir. Modelde daha iyi görünen toplamlar tek başına kârlı strateji anlamına gelmez. 10/20/30dakika taraması veya sonuçlara göre yeni giriş/stop/çıkış değişikliği yapılmadı.

## Test ve bütünlük

10test geçti:15dakika sınırında dolum yasağı,14.dakika dolumu, dolmuş pozisyonun süre sonrası takibi, referansta gerçek geçdolum ve ücret,Londonnoon sınırı,eksikM1,stopönceliği ve geçersizsüreler.232referans eşitliği ve korunan dolumların netR/lifecycle eşitliği çalışma içi zorunlu kontrol. Ek dönemde de retainedfill eşitliği ve iptal edilen emrin sıfırdolum/ücreti kontrol edildi.

protocol.json ilk58kurulumu; followup_protocol.json ayrı4ay planını ve kaynaklarını kilitler. summary.json/outcomes.json/paired_records.json/age_groups.json ilk aşama; followup_summary.json/outcomes/pairs/coverage ek aşamadır. Bütün kaynak/veri hashleri tekrar denetlenir.

Üretim kaynağı ve çalışan bot değiştirilmedi; emir, ücretliAPI veya otomatik devam görevi yok. Ek aşamadaki MT5erişimi saltokuma ve mevcutönbellekle sınırlıydı. Küçükbarçıktıları için1GiBboşluk/64MiBnetbüyüme sınırı kullanıldı; hiçbir kullanıcı kaynağı silinmedi.

Tekrar kontrol:

```
python research/fill-delay-2026-10-24/study.py verify
python research/fill-delay-2026-10-24/followup.py check
```
