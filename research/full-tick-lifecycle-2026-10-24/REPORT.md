# Tam tick yaşam döngüsü: London erken-limit ORB karar raporu

**Karar: STOP_THIS_ORB_PARAMETER_SWEEP. Bu dondurulmuş ORB giriş/çıkış kolunda süre/TP/SL taramasını durduruyoruz; demo başlatılmadı.** Gözlenen bid/ask kullanıldığında da iki limit-süresi seçeneği negatif. Bu karar Begonya00'ın bütün SFP/makro/varlık stratejilerinin matematiksel olarak imkânsızlığı iddiası değildir.

## İstenen sıra tamamlandı

1.90kurulum için dolum,ilkstop,TP1/TP2,kısmi kapatma,BE/trailing,olumsuztepki çıkışı veLondon16:30sonu kronolojikquote düzeyinde yeniden oynatıldı.
2.Aynı giriş/stop/hedef ve kurulum setinde240dakika(noonkapı) ile15dakika(noonkapı) karşılaştırıldı. Saat sınırı münhasır; dolmuş pozisyon süre doldu diye kapatılmadı.
3.Önceden sabitlenen kâr/dayanıklılık kapılarıyla demo/araştırma kararı verildi. Pozitif sonuç elde etmek için ilave eşik taranmadı.

## Sonuçlar

**NetR, gerçekleşmiş hesap getirisi değildir:** arşivdeki gözlenenbid/ask fiyatları + açık komisyon/kayma varsayımlarıyla araştırma simülasyonudur. R ilk kotasyon-fiyat riskine normalize edilir; sermaye,marj ve eşzamanlı risk portföyü uygulanmaz.

|Senaryo|Mevcut süre dolum|Mevcut süre netR|15dk dolum|15dk netR|
|---|---:|---:|---:|---:|
|Gözlenen spread + temel varsayımlar|72|-13.294|58|-11.946|
|Spread/komisyon/kayma1.5x|72|-15.841|58|-14.191|
|1pipspreadtabanı+stres|71|-19.124|55|-16.440|

Temel senaryoda PFler mevcut sürede0.531,15dakikada0.527.15dakika toplam kaybı+1.349Razaltıyor; fakat işlem başına sonuç mevcutta-0.185R,15dakikada-0.206R. Yalnız daha az işlem ve daha küçük toplam zarar, daha kaliteli/pozitif bir giriş seçildiğini göstermiyor.

|Ay,gözlenen spread|Mevcut süre netR|15dk netR|
|---|---:|---:|
|2025-02|+0.438|+0.098|
|2025-03|-2.025|-1.892|
|2025-04|-3.245|-3.245|
|2025-05|-1.810|-1.915|
|2025-09|+1.561|+1.066|
|2025-10|-8.212|-6.058|

Altı ayın ikisi temel senaryoda artı,dördü eksi. Daha önce işaretlenen marketableaçılış vakası çıkarıldığında da temel sonuçlar mevcutta-12.127R,15dakikada-10.779R; kararı o tek vaka belirlemiyor.

Komisyon ve varsayımsal kaymayı aynı işlem yolu üzerinde sıfırlayan muhasebe duyarlılığında bile mevcut sürenin fiyat sonucu **-8.504R**. Gözlenen spread hâlâ fiyatın içindedir. Bu yeni bir giriş/çıkış stratejisi denemesi değil; aynı olay defterinden varsayımsal iki maliyeti geri eklemektir. Sonucu yalnız komisyon tarifesinin belirsizliği açıklamıyor.

## Veri ve değişmeyen strateji seviyeleri

Şubat/Mart25,Nisan/Mayıs/Eylül/Ekim65 olmak üzere90önceden kilitlenmiş ilk-günlük kurulum; altımajörFXparitesi. Ocak/Kasım bu90kurulumda yok. Altın,makro/haber,SFPönceliği ve ortakportföyriski yok; tam Begonya00motor backtesti değildir. Veriler daha önce incelendi; yeni OOS veya prospektifforward iddiası yok.

Giriş/ilkstop/TP1/TP2,önceki cases_frozen.json ile byte düzeyinde aynı veriden alındı. Emir, gerçekaskın buyentryden bir tick aşağısına veya gerçekbidin sellentryden bir tick yukarısına geçtiği ilk kayıtta nominal limit fiyatından dolmuş varsayılır; lehte fiyat iyileşmesi yazılmaz. Likidite/kuyruk/gerçekbroker dolum fişi bilinmez. Marketableaçılış ayrıca işaretlenir; o vakanın çıkarılmasıyla duyarlılık da gösterilir.

Mevcut tamseans tape'leri16:00da bitiyordu.90kurulumun tamamı için seans sonu16:00–16:31gerçekbid/askkuyruğu mevcut aynıbrokerönbelleğinden, getiri hesaplanmadan önce alındı. Veriler birleştirilirken örtüşen16:00kısmı tekrarlanmadı; aynı milisaniyedeki kayıt sırası korundu. İnterpolasyon yok. İlkquote en fazla5saniye sonra; terminalolaya kadar60saniyeden büyük boşluk netR üretmez.

## Tick icrası ve mum proxy'si arasındaki açık farklar

-İlk stop dolum anı dahil herquoteda aktiftir; longbid,shortask tetikler. Gap varsa o anda gözlenen daha kötü fiyat ve varsayımsal olumsuzkayma kullanılır.
-**Dolumun bütün M1mumunda TP kredisi yoktur.** Dolum mumu tepki şekli yalnız tamamlandığında bilinir; olumsuz tepki çıkışı önceki kapanış fiyatından değil sonraki ilk gerçekquotedan olur. Bu örneklemde bu karar ile icra arasındaki en büyük bekleme1.617saniye.
-TP1'deyarı,TP2'dekalan nominalhedef fiyatından kapanır; aynıquote ikihedefi aşarsa iki parçanın nominalseviyeleri kullanılır. Lehte gap kazancı eklenmez.
-M1belirsizliğinin aksine, tickte TP1'in daha sonraki stoptan önce geldiği biliniyorsa kısmi kâr korunur. Stop,target aynıquoteda çakışırsa stopönceliği sürer. Bu, sinyal/hedef değişikliği değil kronolojik icra doğrulamasıdır.
-BE,TP1mumundan sonraki ilkM1quote'da etkin olur.1.5Rde0.75Rtrailing,TP1mumundan sonraki mumlarda aranır ve takipedenM1de etkinleşir; yeni stop geçmişquotelara uygulanmaz.
-London16:30da ilkquote'dan piyasa kapanışı yapılır. Dolumsuz emrin iptali kazanç veya ücret üretmez.

Bu yürütme sözleşmesi önceki araştırma yaşam döngüsünü gerçekquotelara açıkça uyarlar; eski canlıbotla byte düzeyinde aynı icra motoru diye adlandırılmaz. Önceki M1proxy netRleriyle farkı yalnız spread farkına bağlamak da yanlış olur: kronoloji ve tepki çıkış fiyatı da netleşmiştir.

## Maliyet ayrımı

Temel senaryo: gözlenen ask-bid,kontrat100binbirim başına4USDroundtripkomisyon(2açılış+2kapanış,kısmi çıkışlarda ağırlıklı) ve yalnız piyasa çıkışında0.2pip olumsuzkayma. USD-bazlı paritelerde komisyon ilgili fiyatla kotasyon para birimine çevrilir. Tarihsel hesaba ait komisyon/kayma fişleri doğrulanmadı.

1.5xstres ask-bidfarkını,komisyonu ve kaymayı1.5ile çarpar; **1.5pip spread** demek değildir. Ek muhafazakâr senaryoda aynıstresle spreadenaz1pip alınır; hamarşivdeki sıfırspreadlere karşı duyarlılık sağlar. Bu son senaryonun askı sentetiktir; gözlenenask diye etiketlenmez.

Spread,icra fiyatlarının içindedir ve ayrıca tekrar düşülmez. Komisyon,kayma ve olaylar ayrı alanlarda tutulur. Gözlenen spreadin sıfır olması ücretsiz/garantili işlem anlamına gelmez. Hiçbir senaryo gerçek hesap kazancı sertifikası değildir.

## Karar kapıları

Önceden demo adayı sayılabilmek için≥50kapalıdolum,gözlenen senaryoda pozitif gün-küme95%alt sınırı,üçmaliyet altında pozitif toplam ve ikiayrı dönem grubunda pozitiflik,gözlenen/stres altında≥4/6pozitifay,çözümlenmemişkayıt olmaması ve marketablevakalarçıkarılınca artı toplam arandı. Hem mevcut süre hem15dakika başarısız oldu. Bütün kapılar decision.jsonda saklıdır; negatifsonuçta örneklem veya eşik değiştirilmedi.

**Somut karar:** bu dondurulmuş Londonerken-limitORB tanımında yeni süre/TP/SL taraması yapılmayacak; demo başlatılmayacak. Üretim kodunu silmek, çalışanbotu durdurmak veya Begonya00'ın diğerstratejilerini iptal etmek bu kararın parçası değil. Farklı giriş hipotezi araştırılacaksa ayrı protokol ve yeni kanıt gerektirir; mevcutkolu kârlıymış gibi sunmayacağız.

## Kontroller ve tekrar üretim

-14test geçti:long/shortquote tarafı,gapstopu/komisyon,tepkiçıkışınınsonrakiquote'danicrası,dolum-mumuTPyasağı,kısmiücret,BE/trailingzamanı,tickkronolojisikısmiTPsonrastop,TTL15sınırı,dolmuşişleminsüreötesitakibi,quote boşluğu,spreadtabanı,eksikkuyrukta netRvermeme,16:30kapanışveUSDbasekısmiücret.
-90kurulum×3maliyet×2süre=540replaykaydı; bağımsız540işlem değildir. Çözümlenmemiş kayıt:0.
-Gözlenen senaryonun90kurulumundaki ilk-dolum/dolumsuzluk kayıtları önceki bid/asktickdenetimiyle birebir eşleşti. Aynı dolumu koruyan kısa/uzunTTL yollarının bütün olay defterleri de aynı.
-Açılış/kapanış miktarı1,defter ücretleri,net=gross−komisyon,dolumsuzemirde0ücret kontrolleri geçti. integrity.json bu kontrolleri outcomes.jsonhashine bağlar.
-Kaynak,90tamseanstape,90kuyruk ve girdiler hashlerle kilitli.14test, veri/broker dolum sertifikası değil, model davranış kontrolüdür.

Dosyalar:protocol.json,cases_frozen.json,tail_manifest_frozen.json,outcomes.json(olaydefterleri),summary.json,integrity.json,decision.json. Tekrar kontrol:

```
python research/full-tick-lifecycle-2026-10-24/study.py verify
python research/full-tick-lifecycle-2026-10-24/validate_results.py
```

Emir,ücretliAPI,otomatikdevam veya üretimkodudeğişikliği yok. Brokererişimi yalnız önbellekteki teklifleri okumaktı; kullanıcı dosyası silinmedi. Demo ileri test yalnız kapılar geçse hazırlanacaktı; bu çalışmada geçilmedi.
