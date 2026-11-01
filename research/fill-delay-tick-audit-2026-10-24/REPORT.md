# Dolum gecikmesi: bid/ask tick denetimi

**Sonuç:** dolumun ilk15dakikada mümkün olup olmadığına dair mum-modeli sınıflandırması, mevcut broker tick arşiviyle90kurulumun89unda uyuşuyor. Dolum gecikmesi önceki modelin tamamen uydurduğu bir etki görünmüyor. Ancak bu,15dakika iptal kuralının kârlı olduğunu göstermez; önceki negatif kârlılık doğrulamasını değiştirmiyoruz.

## Kapsam ve sabit kurallar

Şubat/Mart25 ve Nisan/Mayıs/Eylül/Ekim65 olmak üzere **90kurulum**. Ocak/Kasım için bu kilitli kaynakta tam-seans bid/ask tapesi olmadığından o aylar bu denetime eklenmedi; kötü/iyi performansa göre örnek seçilmedi. Bütün veriler tarihsel ve daha önce araştırıldı; yeni OOS veya broker gerçekleşme belgesi yok.

Kurulum,ilk giriş fiyatı,Londonnoon/240dakika sonu ve15dakika alternatif sınırı değişmedi. Long için arşivdeki ask, girişin bir tick altına; short için bid, girişin bir tick üstüne geçtiği ilk quote kaydedildi. Bir ticklik seviyede kayan nokta temsil hatası için tickin1e-7si tolerans kullanıldı; ekonomik fiyat eşiği genişletilmedi. Sinyal sonrası ilk teklif en fazla5saniye gecikmeli olmalı; ilk olası doluma veya süre sonuna kadar60saniyeden büyük quote boşluğu olmamalı. Dolumsuz kayıt için süre sonunun quote kapsamı da aranır.90kurulumun tamamı bu kontrollerden geçti.

Bu olay **mümkün olan ilk fiyat temasıdır**. Emir gönderimi,brokerkabulü,kuyruk,gecikme,likidite veya gerçekleşmiş dolum fişi yoktur. Gerçek tick kaynaklı olması sınırsız ve garantili dolum anlamına gelmez. Bir kotasyonda bir tick penetrasyonu küçük pasif emir için araştırma varsayımıdır.

## Sayılar

|Ölçüm|Sonuç|
|---|---:|
|İncelenen kurulum|90|
|Tickte ilk15dakikada olası dolum|58|
|Tickte15dakika veya sonrasında olası dolum|14|
|Geçerlilik süresinde temas bulunmayan|18|
|Eski0.5pip modelindeki toplam dolum|71|
|Tickte toplam dolum fırsatı|72|
|15dakika sınıflandırması uyuşan|89/90|
|Her ikisinde dolum bulunan kayıtlarda dakika eşleşmesi|65/71|
|Fiyat/zaman kapsamı nedeniyle fiyatlanamayan|0|

Altı kurulumda aynı emir doluyor fakat ilk dolum fırsatı farklı dakikada. Gerçek spreadin değişmesi, sabit0.5pip spread ve fiyat hassasiyeti varsayımları bu farkta önemlidir; farkların tamamını yalnız mum zaman çözünürlüğüne bağlamıyoruz. İlk olayın M1içinde ne zaman olduğu ayrıca kaydedildi. Yeni zamanla dolup eski modelde dolmayan kayıt1; eski modelde dolup tick denetiminde hiç temas bulunmayan kayıt0.

## Somut farklar

- **GBPUSD,2025-05-23:** önceki0.5pip modelinde dolum yok. Arşivde07:32:57.034UTC'de giriş seviyesinin bir tick ötesine geçen ask var; sinyalden2.951dakika sonra.15dakika grubuna ekleniyor. Yeni dolumun kârı/zararı hesaplanmadı; eski no-fill kayda kâr atanmadı.
- **GBPUSD,2025-09-09:** sinyal sonrası ilk quote(08:30:00.025UTC) karşısında limit fiyatı pasif bekleme yerine hemen işlem görebilecek konumda. Bu, tüm pasif emir varsayımının broker kabul/gerçekleşme kaydı olmadan doğrulanamayacağını gösteren bir kayıt bayrağıdır; brokerin emri kesin reddedeceği veya kesin dolduracağı iddiası yok.
- En belirgin dakika farklarından biri GBPUSD,2025-03-12: model09:14M1dolumu, arşivde ilk fiyat fırsatı09:03:17.985UTC. Bu tip farklarda dolum mumu tepki koşulu da değişebilir; eski çıkış/getiri sonucu yeni doluma taşınamaz.

72olası dolumun31inde arşiv ask-bid farkı sıfır; medyan0.1pip. Bunlar arşivin gösterdiği anlık farklardır. Broker hesabında ücretsiz işlem veya komisyonsuz dolum iddiası değildir; bağımsız gerçek spread/likidite sertifikası da değildir. Gerçekleşmiş komisyon,kayma ve çıkışlar bu denetimin kapsamında değil.

## Araştırma için uygulanabilir sonuç

1.15dakika kuralına ilişkin önceki kötü sonuç, basitçe “mum verisi bütün geç dolumları yanlış sınıflandırmış” açıklamasıyla ortadan kalkmıyor.90kurulumda yalnız bir15dakika sınıflandırması değişti. Yine de PNLnin aynı kalacağı söylenemez: altı dolum mumu ve bir ek dolum farklıdır, dolum sonrası yol tekrar hesaplanmalıdır.
2.Bir sonraki icra doğrulamasında **emrin pasif kalıp kalmadığı**, **ilk mümkün dolumun milisaniye zamanı**, **o andaki bid/ask** ve **model-tick farkı** birlikte kaydedilmeli. Bu alanlar records.jsonda hazırdır. Bunlar canlı veto veya emir yönlendirmesi değildir.
3.Tekliflerden netgetiri hesaplanacaksa tepki çıkışı/kısmi çıkış/stop/hedef sıralaması ve gerçekleşmiş maliyetler ayrıca modellenmeli. Eski mum-PNLsini yeni tick dolumuna bağlayarak olumlu sonuç üretilmedi. Bu tur bir dolum denetimidir; tam tick yaşam döngüsü backtesti değildir.

**Karar:** üretime15dakika sınırı eklemek için yeni kârlılık kanıtı yok. Önceki fill-delay araştırmasının sonucu geçerlidir: ek dört ayda ana senaryoda zarar azalırken stres altında büyüyordu. Dolum gecikmesi kayıtlarını korumak yararlı; bu etkiyi tek başına edge diye terfi ettirmek desteklenmiyor.

## Dosyalar ve test

protocol.json sonuçlardan önce kaynak,kural,90kurulum ve gerekli tape hashlerini kilitler. cases_frozen.json girişleri ve önceki0.5pipmodel dolumlarını; records.json her olay/farkı; summary.json her dönem ve toplam ölçümleri içerir.

8test geçti: longask/shortbidpenetrasyonu, tam15dakika sınırı,15dakikadan1milisaniyeönce dolum, dolum öncesi quote boşluğu, dolumsuz kayıt için süre sonu kapsamı, süre sonrasında temasın dolum yazılmaması ve ilk temastan sonraki boşluğun ilk temas denetimini değiştirmemesi.

Bütün90tape ve kod/girdi hashleri kontrol edildi. Yeni indirme,ücretliAPI,emir,üretim kodu değişikliği veya otomatik devam görevi yok. Tekrar kontrol:

```
python research/fill-delay-tick-audit-2026-10-24/study.py verify
python research/fill-delay-tick-audit-2026-10-24/study.py run
```
