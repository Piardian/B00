# Erken limit girişleri: koşul ve gerçek karar teklifi ölçümü

## Ne ölçüldü?

Önceki London ORB araştırmasındaki **33 ilk günlük kurulum** değişmeden alındı: Ocak2025 23, Kasım2025 10. Yeni aday seçilmedi; işlem sonucu kullanılarak teklif örneği seçilmedi. Tam bot/makro/haber/ortak risk veya yeni aylık tarama değildir. Altın örneği yok; veri daha önce görülmüş olduğu için OOS iddiası yok.

İki ayrı veri türü kullanıldı:

1. **Yeni gerçek broker teklif ölçümü:** çalışan açık The5ers terminalinden her kararın önceki61saniyesi okundu. 33 kararda toplam dosya boyutu177664bayt. Önceden mevcut aylık önbellekler kullanıldı; ücretli API, emir veya hesap değişikliği yok.
2. **Değişmeyen model getiri etiketleri:** önceki referans replay'in 0.2/0.5/0.9/1.5pip sabit spread varsayımlı sonuçları. Yeni gerçek karar teklifleri, işlem yaşam döngüsünün tamamını veya gerçekleşmiş broker maliyetlerini sağlamaz. Aşağıdaki netR tabloları bu modele aittir; gerçek hesap kârı değildir.

Saat, HTF uyumu, Asya sıkışması ve maliyet grupları bu turun grup sonuçlarından önce sabitlendi. Önceki toplam sonuçlar zaten biliniyordu; bu geçmiş veride keşifsel ayrımdır, bağımsız hipotez doğrulaması değildir.

## Karar anındaki spread/maliyet

| Ölçüm | Sonuç |
|---|---:|
| İstenen / alınan karar penceresi | 33 / 33 |
| Teklif yaşı ve fiyat hizalaması geçen | **32** |
| Fiyatlanamayan | **1** |
| Karar anı spread medyanı | **0.00pip** |
| Karar anı spread %95 yüzdeliği | **0.245pip** |
| Sıfır spreadli karar örneği | 19 / 32 |
| Varsayımlı toplam maliyet bütçesi medyanı | **0.0633R** |

Fiyatlanamayan: USDCHF,2025-11-12; son teklif karar anından10.77saniye eski. Beş saniyelik sınır korundu; bu kayda maliyet atanmıyor.

Geçen32örnekte önceki dakikanın ticklerden türetilen bidOHLC'si kanonik M1 ile kayan nokta hassasiyetinde eşleşti (maksimum hata yaklaşık2.22e-11tick). Bu, kullanılan UTC+2/3 broker saat eşlemesinin örnek bazında tutarlılık kontrolüdür; bağımsız broker-saat sertifikası veya tüm ticklerin eksiksizliği kanıtı değildir. Teyit, olumlu sonuca bakılarak seçilmedi.

**Yorum:** Bu karar örneklerinde önceki0.5pip sabit spread varsayımı gözlenen spreadlerden yüksek. Ancak “gerçek maliyetler düşük, kâr kanıtlandı” sonucu çıkmaz: işlem dolumu/çıkışındaki spread, haber genişlemesi, komisyon ve kayma ayrıca ölçülmeli. Sıfır bid/ask farkı ücretsiz işlem veya gerçekleşebilir dolum garantisi değildir.0.0633R bütçede komisyon100binbirim başına4USD ve çıkış kayması0.2pip hâlâ varsayımdır; gerçekleşmiş hesap ücreti değildir. Eski replay'e bu snapshot spreadi bütün gün geçerliymiş gibi uygulanmadı.

## Piyasa koşullarına göre referans model sonucu

Ana0.5pip model, aynı giriş/stop/çıkış kuralları ve komisyon/kayma varsayımları:

| Girişte bilinen koşul | Kurulum | Dolum | Ocak netR | Kasım netR | Toplam netR |
|---|---:|---:|---:|---:|---:|
| Tüm referans | 33 | 31 | +7.677 | −2.487 | +5.190 |
| Asya aralığı / günlük ATR ≤0.35 | 24 | 22 | +9.372 | −1.904 | **+7.468** |
| Asya aralığı / günlük ATR >0.35 | 9 | 9 | −1.694 | −0.583 | **−2.277** |
| London09:00'dan önce | 17 | 16 | +5.364 | −2.744 | +2.620 |
| London09:00–12:00 | 16 | 15 | +2.314 | +0.257 | +2.570 |
| Mevcut H1 yönüyle uyumlu | 9 | 9 | +0.200 | işlem yok | +0.200 |
| Mevcut H1 yönüyle uyumsuz | 24 | 22 | +7.477 | −2.487 | +4.990 |

Bu satırlar ayrı alternatif koşul gruplarıdır; birbirine eklenmez. HTF uyumsuz gruptaki geçmiş artı, yön filtresinin canlıdan kaldırılması için kanıt değildir. Aynı gün/para biriminde ilişkili işlemler vardır; sonuç bağımsız portföy getirisi değildir.

## Sıkışma ipucunun maliyet dayanıklılığı

| Model spreadi | Asya≤0.35ATR toplamR | Aynı grubun KasımR | Asya>0.35ATR toplamR |
|---|---:|---:|---:|
|0.2pip|+4.177|−3.633|−2.243|
|0.5pip|+7.468|−1.904|−2.277|
|0.9pip|+3.869|−3.207|−1.681|
|1.5pip|+2.863|−4.386|−4.214|

**Araştırma önceliği olarak en anlamlı ipucu Asya sıkışması.** Fakat iki ayda istikrarlı bir filtre bulunmadı: daha sıkışık grupta Kasım her spread senaryosunda eksi. London09sonrası grup yalnız ana senaryoda iki ay pozitif; diğer spreadlerde Kasım negatif. Güzel görünen tek hücre seçilmedi.

Spread artarken model sonuçlarının monoton olmaması, sabit limitin farklı dakikada dolması ve farklı çıkış yoluna girmesiyle mümkündür. En iyi spread seçilerek sonuç sunulmadı.

## Belirsizlik

10000London-günü küme bootstrap örneği,95%yüzdelik aralığı; istatistik kabul edilen kurulum başına modelR. Aynı günün işlemleri beraber örneklenir; beş farklı günden küçük gruplarda aralık gösterilmez.

- Tüm referans ortalama+0.157R/kurulum; aralık **[−0.189,+0.500]**.
- Asya≤0.35ATR ortalama+0.311R/kurulum; aralık **[−0.034,+0.641]**.
- Asya>0.35ATR ortalama−0.253R/kurulum; aralık **[−0.643,+0.348]**.

Aralıklar sıfırı içeriyor. Günler arası seri bağımlılık, önceki çoklu araştırmalar ve değişen piyasa koşulları için tam düzeltme yok. Bu, anlamlı edge veya nedensellik testi değildir. Yeni veri olmadan bu ayları daha fazla bölerek güvenilirlik kazanılmaz.

## Sonraki doğrulama için somut çıktı

`measurements.json` kurulum bazında gerçek karar teklifi ve koşul etiketlerini içerir. `group_results.json` bütün grupları/dört maliyeti, `quote_summary.json` teklif kalitesini saklar. İşlem sayıları veya kötü gruplar gizlenmedi. Fiyatlanamayan teklif grubunun modelPNL'si saklıdır fakat gerçek maliyetli PNL diye etiketlenmez.

Bir sonraki ayrı dönemde **Asya≤0.35ATR / >0.35ATR ayrımı aynı tanımla** izlenebilir. Eşiği0.30/0.40vb taramak veya saat+HTF+pariteyi sonuçlara göre birleştirmek bu çalışmanın parçası değildir. Bütün uygun kurulumlar ve kontrol grubu korunmalı; tam dolum/çıkış bid/ask ve gerçekleşmiş ücret kayıtlarıyla ölçülmelidir. Yeni kurallar veya otomatik canlı veto uygulanmadı.

## Protokol, disk ve yeniden çalışma

İlk protokolün3GiB disk eşiği, herhangi bir teklif okunmadan işlemi durdurdu. Hedef aylık önbelleklerin tamamının mevcut olduğu görüldü. Sonuçlara bakılmadan `protocol_v2.json` ile toplama mevcut önbelleklerle sınırlandı: en az2GiB boşluk ve128MiB büyüme sınırı. İlk protokol korundu; grup tanımları ve modelPNL girdileri değiştirilmedi. Hiçbir kullanıcı kaynağı veya başka çalışmanın dosyası silinmedi.

Kaynaklar, kanonikM1, adaylar ve referans etiketleri hashlerle kilitli. Karar tekliflerinin manifesti analizde ayrıca donduruldu. Yeniden ölçüm:

```
python research/early-limit-context-2026-10-23/study.py verify
python research/early-limit-context-2026-10-23/study.py run
```

Ölçüm ve grup muhasebesi için12test: karar sonrası veriden ayrım, yanlış saat/fiyat eşleşmesi, eski/çapraz teklif, eksik referans, sıfırspreadde ücret, DST/saat grubu, eksik sıkışma, işlemsiz kayıt, ay/toplam tutarlılığı ve gün kümeleri. Üretim modülleri/çalışan bot değişmedi. Hiçbir ücretli API veya işlem emri kullanılmadı.
