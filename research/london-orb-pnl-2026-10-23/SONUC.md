# Begonya00 London ORB — M1 gerçekleşme ve maliyet ölçümü

**Sonuç: mevcut ORB retest giriş / tepki çıkışı sürümünde bu üç aylık örneklem pozitif edge göstermedi.** Aşağıdaki bağımsız aday ölçümleri tam bot veya gerçekleşmiş hesap getirisi değildir. Makro/haber/SFP önceliği, sinyal cooldown ve portföy risk etkileşimi ayrıca ölçülmeden aynı sonuçlar tam sisteme atfedilemez.

## Ne ölçüldü?

Düzeltilmiş London dedektörünün altı paritedeki102 adayının tamamı incelendi: EUR/USD, GBP/USD, USD/JPY, USD/CAD, USD/CHF, NZD/USD; Ocak/Haziran/Kasım2025. Her aday kendi boş takip defteri ve birimR riskiyle başladı; aynı gün veya sembolde çakışan adaylar olabilir. Sonuçları toplamak uygulanabilir bir portföy eğrisi oluşturmaz.

Doğrudan orijinal OutcomeTracker.register_trade ve check_trade_progress çağrıldı. Limit penetrasyonu, giriş mumunda stop önceliği, aynı mumda hedef yazılmaması, tepki başarısızsa dolumu silmek yerine kapanışta çıkış, TP1 kısmi çıkış, BE ve trailing kuralları değişmedi. Gerçek kayıt dosyalarına yazma ve bildirim yöntemleri test içinde izole edildi; ağ/model çağrısı yapılmadı.

Bu giriş, kullanıcının ayrıca belirttiği M1 tepe/dip kırılması teyidinin tanımlanmış bir testi değildir. Mevcut botun ORB midpoint/retest limit mekanizmasının ölçümüdür.

## 1,5x paper maliyet sonucu

| Grup | Toplam aday | Seviye/RR reddi | Dolmadan kapanan | Dolmuş/kapanmış | NetR | PF | Net kazanan oranı |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bütün London seansı | 102 | 48 | 23 | 31 | -14.525 | 0.21 | %9.7 |
| UTC12:00 öncesi | 36 | 20 | 6 | 10 | -1.318 | 0.70 | %20.0 |
| Motor saati + HTF uyumlu | 27 | 16 | 2 | 9 | -5.269 | 0.22 | %11.1 |

Her grupta çözülmemişM1 boşluğu veya ay sonunda açık kalan aday sayısı sıfırdır. Geçmiş boşluklar sonuca sıfır olarak eklenmedi. Motor saati+HTF grubu, o anda tamamlanmışH1 verisinden mevcut1000mum görünümüyle hesaplandı; AAA uyumunun aday altkümesidir, makro onayı değildir. Sabah sınırı UTC12:00’dır; DST nedeniyle yerel London08:00’dan itibaren sabit4saatlik pencere sayılmaz.

### Aylık netR — 1,5x

| Grup | Ocak | Haziran | Kasım |
|---|---:|---:|---:|
| Bütün London seansı | -3.754 | -4.882 | -5.889 |
| UTC12:00 öncesi | -0.380 | +0.000 | -0.938 |
| Motor saati + HTF uyumlu | -2.549 | -1.120 | -1.600 |

## Maliyet stresinin iki ayrı anlamı

Mevcut paper sürtünme modeli Forex için spread_ratio=0.0002 ve işlem başına fee_r=0.08 kullanır. Spread oranı doğrudan tarihsel bid/ask serisi değildir; pasif dolum penetrasyonu ve hedef aşım tamponudur. Komisyon/kayma sabitR varsayımıdır. Gerçek The5ers komisyonu, bid/ask ve gerçekleşme makbuzu doğrulanmamıştır. Bu sonuçlara broker maliyetleri birebir düşülmüş gerçek kâr denemez.

| Bütün London grubu | 1x | 1,5x | 2x |
|---|---:|---:|---:|
| Spread+ücret birlikte stres: netR | -14.397 | -14.525 | -16.009 |
| Spread+ücret birlikte stres: dolum | 32 | 31 | 29 |
| Sabit1x dolumlar, yalnız ücret artışı: netR | -14.397 | -15.677 | -16.957 |

Spread stresi aynı işlemlerin maliyetini artırmakla kalmaz; dolan aday ve çıkışlar da değişir. Bu yüzden bazı altgruplarda1,5x sonuç1x’ten daha iyi görünebilir. Bu maliyetlere dayanıklı alfa kanıtı değildir. Sabit dolum ücret stresi ise aynı32 temel dolumun ek0.04R/0.08R ücretle nasıl değiştiğini gösterir; ilave spread/kaymayı tam modellemez.

## Kaybın kaynağı ve yuvarlama engeli

| Kapanış nedeni | Dolum | NetR |
|---|---:|---:|
| ENTRY_REACTION_EXIT_FILLED | 22 | -11.760 |
| STOP_LOSS | 6 | -6.720 |
| TP2_HIT | 2 | +3.086 |
| TRAILING_STOP | 1 | +0.869 |

31dolumun22’si giriş mumunda tepki yetersizliğinden kapanıyor; bu grup toplam−11.760R yazıyor. Bu mekanizmanın kayba önemli katkısını gösterir; tepki kuralını kaldırmanın net kâr sağlayacağını kanıtlamaz. Bu turda kötü sonucu kurtarmak için kurallar değiştirilmedi.

48aday mevcut gerçek seviye/RR denetiminde reddediliyor:46’sında TP1 minimum1.2R altında,2’sinde TP2 minimum2R altında. Dedektör hesaplanan seviyeleri parite fiyat hassasiyetine yuvarladığı için nominal1.2R/2R hedefleri gerçek yuvarlanmış giriş-stop mesafesinde alt sınırı tutmayabiliyor. Bunlar kârsız işlem sayılmadı veya motor kontrolü aşılmadı. Daha sonra bu yuvarlama davranışı düzeltilirse yeni adayların PnL’si ayrı sürüm olarak yeniden ölçülmelidir.

## Belirsizlik ve sınırlar

Adayın oluştuğu güne netR atayıp63gözlem işgünü üzerinde5günlük dairesel blok-bootstrap,10.000tekrar,seed173. ToplamR için koşullu%95aralıklar:

- Bütün London seansı: [-21.25, -7.90]R.
- UTC12:00 öncesi: [-6.34, +3.51]R.
- Motor saati + HTF uyumlu: [-10.06, -0.99]R.

Bunlar çoklu araştırmaları düzelten kesin p-değerleri değildir. Üç seçilmiş tarihsel ay OOS değildir. Sabah grubunda yalnız10dolum olması genelleme yapmayı engeller. Geniş London grubunda bu sürüm için sonuç belirgin biçimde olumsuzdur; LondonORB ailesinin tüm varyantları hakkında hüküm değildir.

1,5x dolumlarda geceye taşınan pozisyon ve aktif stopun ötesinde açıldığı tespit edilen sonraki mum sayısı sıfırdır. Bu, modelin genelde gece/gap riski olmadığı anlamına gelmez: mevcut takipçi gapstopları her zaman gerçek açılış fiyatıyla fiyatlamaz; swap da modellenmez. Hesaplanmış kapalı sonuç dizisi düşüşü gerçek eşzamanlı hesap drawdown’ı olarak sunulmadı.

## Doğrulama

50 test geçti:6yeni M1 replay testi ve44mevcut London/canlı işlem/replay testi. Yeni testler gerçek takipçiyle giriş mumunda SL ve maliyet, dolmadan hedefe gitmenin kazanç sayılmaması, eksik ilk dakikanın çözülmemiş kalması, IOpatchlerinin geri yüklenmesi, minimumRR kontrolü ve spread stresinin dolum seçimini değiştirmesini doğrular. Kaynak kod, aday kümesi ve M1/H1 fiyat hashleri sonuç sonrası yeniden kontrol edildi.

Dosyalar: protocol_frozen.json, results.json, outcomes.json, outcomes.csv, measure.py, test_measure.py. Bu turda üretim kodu veya çalışan süreç değiştirilmedi; canlı/paper emir ya da Telegram bildirimi gönderilmedi.
