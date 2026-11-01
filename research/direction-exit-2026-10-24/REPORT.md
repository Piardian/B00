# Giriş yönü ve erken tepki çıkışı: kontrollü araştırma

**Sonuç: yeni bir çıkış kuralı veya güvenilir yön avantajı doğrulanmadı.** Erken çıkışı kaldırmak bazı koşullarda kaybı azaltıyor, başka koşullarda artırıyor. Yeni kuralı üretime almak için gerekçe yok.

## Kapsam

Ocak/Kasım2025'ten33 ve Şubat/Mart2025'ten25 olmak üzere **58sabit ilk günlük kurulum** kullanıldı. Şubat/Mart25kurulum bu turun ana kontrol örneklemidir; önceki sıkışma testindeki yalnız21TIGHTdolumla karıştırılmamalıdır. Bu turda %35filtresi uygulanmadı; aynı dedektörün bütün25kurulumu korundu. Makro/haber/SFPönceliği/portföyriski yok; tam bot veya gerçek hesap performansı değildir. Bütün dönemler daha önce görüldü; bu çalışma yeni OOS kanıtı değildir.

Protokol grup/çıkış sonuçlarından önce donduruldu. Üretim kaynakları değiştirilmedi; önceki araştırma motorunun yerel kopyasında yalnız erken çıkış koşulu değiştirildi. İlk stop,limitdolumu,hedefler,kısmiçıkış,BE/trailing veLondon16:30sonu aynı. Dolum mumunda hedef kredisi yok, stop öncelikli, zararlı dolum silinmiyor. Bütün **232önceki referans kaydının** durum,dolum,kapanış,sebep ve netRsi yeniden eşleşti; çıkış varyantlarında giriş dolumları aynı kaldı.

## 1. Çıkış kuralını tek başına değiştirmek

Üç sabit kural:

-always: mevcut olumsuz dolum-mumu tepki çıkışı.
-never: yalnız bu tepki çıkışı kaldırılır; yapısal stop ve diğer çıkışlar korunur.
-half_r_adverse: aynı olumsuz tepki bulunursa, ancak executable mum kapanışı girişe göre−0.5Rveya daha kötü olduğunda çıkar. Bu mark-to-entry ölçümü çıkış kayması/komisyondan öncedir; kapanışta bilinir. Eşik taranmadı.

NetR, önceki varsayımsal maliyet sözleşmesiyle: sabitspread,100binbirime4USDround-trip komisyon,0.2pip olumsuz piyasa çıkış kayması. Gerçek bid/ask/hesap ücretiyle doğrulanmış netgetiri değildir. Spread senaryosu dolum ve izlenen yolu da değiştirebilir; aynı ücret düşülmüş sabit kazançlar gibi yorumlanmaz.

|Dönem|Çıkış|0.5pip dolum|0.5pip netR|1.5pip netR|
|---|---|---:|---:|---:|
|Ocak/Kasım|Mevcut tepki çıkışı|31|+5.190|-1.352|
|Ocak/Kasım|Tepki çıkışı yok|31|+3.252|+0.641|
|Ocak/Kasım|Tepki çıkışı yalnız≤−0.5R kapanışta|31|+3.252|+0.641|
|Şubat/Mart|Mevcut tepki çıkışı|23|-4.874|-5.054|
|Şubat/Mart|Tepki çıkışı yok|23|-3.768|-7.744|
|Şubat/Mart|Tepki çıkışı yalnız≤−0.5R kapanışta|23|-3.768|-7.744|
|Dört ay|Mevcut tepki çıkışı|54|+0.317|-6.406|
|Dört ay|Tepki çıkışı yok|54|-0.516|-7.103|
|Dört ay|Tepki çıkışı yalnız≤−0.5R kapanışta|54|-0.516|-7.103|

Şubat/Mart ana modelinde tepki çıkışını kaldırmak toplamı+1.105Riyileştiriyor; ama Şubat−0.046R,Mart−3.722R ve toplam−3.768R kalıyor. Stres spreadinde−2.690Rdaha kötü. Ana maliyette6kurulum iyileşti,7kötüleşti; streste3iyileşti,8kötüleşti. Geri kalanlar değişmedi. Eşleştirilmiş ortalama farkın gün-küme95%aralıkları sıfırı içeriyor; istikrarlı iyileştirme kanıtı yok.

−0.5Rkoşullu kural, bu örneklemde never ile aynı sonuçları verdi. Tepki başarısızlığıyla çıkan mumların kapanış kayıpları eşiğe ulaşmadığından bu kural çıkışı tetiklemedi. Bunlar iki bağımsız olumlu/olumsuz kanıt değil, örneklemde aynı yolu üreten iki tanımdır. Eşiği sonradan değiştirmedik.

## 2. Yönün kendisi avantajlı mı?

Her kurulumun orijinal bilgi-kullanılabilirlik anından sonraki sabit60dakikalık bid-open hareketi, giriş-stop mesafesine bölündü. Orijinal sinyal yönü ve ters işaret aynı fiyat/riskte karşılaştırıldı. **Bu yön skoru, stoplu işlem getirisi veya maliyet sonrası kâr değildir.** Limitin dolmasına bağlı örnek seçilmedi. Ters işaret matematiksel kontrol; uygulanabilir ters strateji backtesti değildir.

|Dönem|Ölçüm|Yönünde hareket|Ters hareket|Ortalama yön skoruR|Gün-küme95%aralık|
|---|---:|---:|---:|---:|---|
|Dört ay|58|26|32|+0.075|[-0.327,+0.481]|
|Ocak/Kasım|33|14|19|+0.109|[-0.420,+0.679]|
|Şubat/Mart|25|12|13|+0.030|[-0.560,+0.589]|

Şubat'ta ortalama yön skoru+0.380R,Mart'ta−0.293R. Şubat/Mart toplamında ters-yön skor ortalaması−0.030R; bunun pozitif bir ters-strateji önerisine dönüşmesi mümkün değil. Seçilen60dakika ufkunda tutarlı yön avantajı gösterilemedi; başka her zaman ufku için matematiksel imkânsızlık iddiası yok.

Ek ölçüm, gerçek dolumun M1içindeki sırası bilinmediğinden dolum mumundan **sonraki M1açılışından**60dakika ilerisine yapıldı. Şubat/Mart23dolumun13ünde hareket orijinal yönde; ortalama+0.098R ve gün-küme95%aralık[−0.638,+0.745]. Bu da belirgin üstünlük kanıtı değil. Erken çıkmış işlemler bu fiyat-yolu ölçümünde tutulur; yeni emir veya gerçekleşmiş getiri sayılmaz.

## 3. Erken çıkış hangi koşulda faydalı?

Toplam sonuçlar görüldükten sonra **ayrı context_protocol.json** ile betimleyici ikinci aşama sabitlendi: kapanışın girişe göre işareti,bekleme≤15dakika ve Asya≤0.35. Hiçbiri yeni canlı filtreye dönüştürülmedi. Faydası mevcut tepki çıkışı netRsi eksi aynı dolumda çıkışı kaldıran varyantın netRsidir: pozitif fark, erken çıkışın zararı azalttığını gösterir.

Şubat/Mart'ta sadece orijinaltepkiçıkışları:

|Spread|Doluma kadar bekleme|Örnek|Erken çıkışın toplam faydasıR|Faydalı|Zararlı|
|---|---|---:|---:|---:|---:|
|0.5pip|GT15MIN|3|+1.203|2|1|
|0.5pip|LE15MIN|10|-2.308|5|5|
|1.5pip|GT15MIN|3|+2.466|3|0|
|1.5pip|LE15MIN|8|+0.223|5|3|

15dakikadan geç dolan üçtepkiçıkışında erken kapatma iki maliyette de toplamı korumuş. Fakat **üçörnekten kural doğrulanmaz**. Hızlı dolumlardaki fayda işareti maliyet senaryosuyla değişiyor. Kapanış işareti de bu kontrol grubunu ayırmadı: bütüntepkiçıkışları girişe göre negatif kapanışlı;−0.283Rile−0.018Rarasında. Asya ayrımı önceki başarısız filtreyi kurtarmadı. Koşul grupları ve bütünhücreler reaction_context_groups.json içinde; iyi görünen hücreler tek başına seçilmedi.

Bu kayıtların somut değeri: **dolum gecikmesi, dolum mumu kapanışRsi ve eşleştirilmiş çıkış faydası** artık ayrı alanlarda ölçülüyor. Gelecek kayıtlar aynı alanlarla izlenebilir; gelecekteki gerçekleşmiş fayda geçmişte bilinen bir giriş özelliği gibi kullanılamaz.

## Karar ve geliştirme yönü

Mevcut deneylerde yalnız çıkışı gevşetmek veya sinyal yönünü ters çevirmek çözüm olmadı. Sonraki ayrı hipotez için ölçülebilir aday **kurulumun zamanla eskimesi**: limitin doluma kadar bekleme süresi ve dolum anında kırılım yapısının hâlâ geçerli olması. Bu turda15dakikalık emir iptal kuralı uygulanmadı; böyle bir kuralın kârlı olduğu iddia edilmiyor. Önce yeni dönemde aynı gözlem alanlarıyla kontrol grubu korunmalı. Düşük örnekli geçdolum grubuna bakarak eski aylarda yeni süre/stop eşikleri taranmamalı.

Çıkış değişikliği için önceden istenen ikiayda pozitiflik ve1.5pip dayanıklılığı sağlanmadı. **Canlı terfi yok; edge kanıtlanmadı.** Bu, projenin her olası varyantının başarısız olacağı iddiası değildir; test edilen belirli giriş/çıkış tanımlarına ilişkin ölçümdür.

## Doğrulama ve dosyalar

-58kurulum×4maliyet×3çıkış=696replaykaydı; bağımsız696işlem değildir.
-Çözümlenmemiş replay:0; çözümlenmemiş karar-yönü ölçümü:0.
-8yeni davranıştesti: stopun korunması, dolumun silinmemesi, hafif/ağırtepki ayrımı, dolum-mumuTPyasağı, yönölçümünün limitdolumundan bağımsızlığı,60dakika sonrasıfuturedataayrımı,eksikmum ve dolumsuzkurulum.
-232referans lifecycle/netR eşitliği ve varyantların aynıdolumları koruması çalışma içi zorunlu kontrol.
-protocol.json ana plan; context_protocol.json ikinci betimleyici aşama. outcomes.json/summary.json/paired.json netkarşılaştırmalar; direction_records.json/summary,after_fill_direction_records.json/summary fiyat-yolu ölçümleri; reaction_context_records.json/groups koşul kayıtları.

Üretim kaynağı/çalışan bot değişmedi; ağ isteği, ücretliAPI, emir veya otomasyon kullanılmadı. Yeni girdi indirilmedi. Tekrar kontrol: `python research/direction-exit-2026-10-24/study.py verify`. Tekrar ölçüm `study.py run`; ikinci aşama `reaction_context.py run`. Bütün kurallar ve girdiler hash kilitlidir.
