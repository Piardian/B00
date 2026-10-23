# 17–18 Ekim 2026 hafta sonu kârının adli incelemesi

İnceleme 23 Ekim 2026 tarihinde tamamlandı. Bu çalışma kayıtlı sinyallerin icra edilebilirliğini inceler; yeni giriş üretmez ve tam sistem backtesti veya broker ekstresi değildir. Canlı ayarlar ve özgün defter değiştirilmedi.

**Sonuç: Fiyat dönüşlerini yakalayan sinyaller var; fakat ekrandaki +19,15R, doğrulanmış broker kârı değil. Önemli kısmında nominal limit giriş fiyatına geri dönüş görülmüyor.**

## Kârın aritmetiği ve nerede toplandığı

21 kapanmış işlem, 17 pozitif sonuç, 4 stop; brüt +20.83R, kayıtlı gider 1,68R, net +19.15R. 4 dolmayan emir bu sayıya dahil değil. 17 Ekim kapanışları +12,52R; 18 Ekim +6,63R. Tüm işlemler kripto ve SFP. Hafta içi karşılaştırması ağırlıkla Forex olduğundan gün ile varlık etkisi ayrıştırılmış değildir.

| Ayrım | İşlem | Kayıtlı net R |
|---|---:|---:|
| SHORT | 11 | +16.93 |
| LONG | 10 | +2.22 |
| PDH süpürmesi | 9 | +13.82 |
| Asya zirvesi süpürmesi | 2 | +3.11 |

5 TP2 toplam +13,77R; 10 trailing kapanışı +8,86R; 2 kısmi kâr sonrası BE +0,84R; 4 stop −4,32R. Büyük görünen başarı, çoğunlukla üst likidite seviyeleri sonrasındaki short hareketlerinde ve kısmi kâr/trailing kayıtlarında toplanmış. Fiyatın o yönde hareket etmesi ile belirtilen limitten pozisyona girmek farklı konulardır.

## Gerçek dakika verisiyle giriş kontrolü

Canlı sağlayıcının kullandığı Binance spot kaynağının resmi günlük M1 arşivlerinden 15 sembol × 2 gün = 30 ZIP alındı; her dosyanın SHA256 CHECKSUM değeri resmi dosyayla eşleşti. Her işlemde açılış dakikasından kayıtlı kapanış dakikasına kadar bütün M1 dakikaları mevcut. İlk ve son kısmi dakikanın tüm aralığı bile dahil edildi: böylece girişin hiç görülmemesi bulgusu sınır dakikalarında aşırı sert bir varsayıma dayanmıyor.

Naif açılış saatleri TRT kabul edildi; işlem ID epoch değeriyle fark bütün işlemlerde 1 saniyenin altında. Sinyal telemetrisi sembol, yön ve giriş fiyatıyla eşleşti; en yakın olaylar saniyenin küçük bir bölümünde aynı kayda karşılık geliyor.

**10 pozitif kayıtta nominal giriş fiyatına gereken yönde hiç erişilmemiş. Bu kayıtların yazdığı toplam +18.39R.** Bunun içindeki AVAX ve INJ farkları yalnızca yarım fiyat adımı mertebesinde olduğundan tarihsel fiyat adımı/yuvarlama kontrolü olmadan kesin dolumsuz sayılmamalı. Bu iki sınır örnek dışarıda tutulduğunda bile **8 kayıt ve +12.26R** için girişe dönüşü destekleyen fiyat yok.

| Kayıt | Yön | Nominal giriş | Açılış–kapanış aralığı yüksek / düşük | Yazılmış net R |
|---|---|---:|---:|---:|
| AVAXUSD_1792230557 | SHORT | 10.0405 | 10.04 / 9.929 | +2.25 |
| PENDLEUSD_1792236155 | SHORT | 2.113 | 2.106 / 2.079 | +2.05 |
| LTCUSD_1792233133 | LONG | 59.425 | 59.71 / 59.47 | +1.09 |
| WLDUSD_1792236681 | SHORT | 0.51825 | 0.5176 / 0.5099 | +2.01 |
| PENGUUSD_1792245976 | LONG | 0.007497 | 0.007559 / 0.007516 | +0.80 |
| NEARUSD_1792243776 | LONG | 5.0085 | 5.11 / 5.019 | +0.80 |
| INJUSD_1792235856 | SHORT | 8.7545 | 8.754 / 8.442 | +3.88 |
| WIFUSD_1792235799 | SHORT | 0.2032 | 0.2024 / 0.1964 | +3.58 |
| SOLUSD_1792314959 | LONG | 103.52 | 104.37 / 103.63 | +1.13 |
| XRPUSD_1792314091 | LONG | 1.2919 | 1.3041 / 1.2941 | +0.80 |

Örnek: WIF SHORT girişi 0,2032. Kayıtlı yaşamı boyunca görülen en yüksek fiyat 0,2024; buna rağmen +3,58R yazılmış. PENDLE SHORT girişi 2,113 iken aralıktaki en yüksek fiyat 2,106; +2,05R yazılmış. XRP LONG girişi 1,2919 iken en düşük 1,2941; +0,80R yazılmış. Fiyat beklendik yönde gitmiş, ancak bu limitlerden dolumu doğrulamıyor.

Binance OHLC, gerçek kişisel borsa emri/fill kaydı değildir. Bu denetim nominal limit modelinin gerekli fiyat koşulunu test eder; spread, sıra önceliği veya emir büyüklüğü için gerçek dolum kanıtı sunmaz. Rakamları basitçe silip yeni bir doğru kâr toplamı üretmedim: doğru takip, bekleyen emirler, zaman aşımı ve sonraki sinyallerle birlikte yeniden yürütülmelidir.

## Kod geçmişi neden bunu açıklıyor?

17 Ekim kaynak sürümünde `register_trade` sinyali doğrudan OPEN olarak kaydediyor; limit retesti beklenmiyor. PENDING_LIMIT retest doğrulaması 18 Ekim 12:44:39 TRT tarihli `b5c9cfb` commitinde geliyor. Nominal girişi görülmeyen on kaydın tamamı bu commit saatinden önce açılmış ve hiçbirinde `filled_at` bulunmuyor. Commit saati kesin dağıtım saati değildir; fakat kaynak davranışı, şema ve fiyat bulgusu birbirini destekliyor. Daha sonraki iki SAND kaydında filled_at var ve nominal giriş de fiyat yolunda görülüyor.

15 dakikalık mumun tekrar değerlendirilmesi ve geçmiş yüksek/düşüklerin TP/BE/trailing zincirine etki etmesi de o dönem kodunda mümkün. Yeni adli Forex/Altın incelemesindeki giriş öncesi TP2 sorunu başka bir simülatörde benzer bir icra tutarlılığı eksikliğidir; aynı işlem kümesi değildir.

## Nötr makro, işlem yoğunluğu ve çıkarım sınırı

Bütün 21 işlem NEUTRAL_RANGE kapısından geçmiş. Telemetrideki çarpanla sonuçları sonradan ölçeklemek yaklaşık +11.00125R verir; bu gerçek portföy getiri kaydı değildir, çünkü eski defter pozisyon boyutunu taşımıyor. Aynı anda en çok 8 kayıt açık. Dolayısıyla 21 sonuç bağımsız bahisler gibi yorumlanamaz; ilişkili kripto hareketine yığılan maruziyet kârı da zararı da büyütebilir.

NEUTRAL_RANGE bazı altcoinlerde eşlenmemiş sembolün varsayılanı olabilir; tek başına gerçek bir yatay piyasa rejimi kanıtı değildir. Teknik nötr sinyallerin kayıtlı toplamı +16,57R; pro-trend 3 kaydın toplamı +2,58R. Hacim anomalisi olmayan 17 kayıt +12,88R, anomalili 4 kayıt +6,27R. Bu küçük ve dolum kusurları taşıyan örnek üzerinden hangi filtreyi kaldıracağımızı seçmek doğru olmaz.

Genel nötr veto kuralı bu eski kayıtların tamamını, kazanan ve kaybeden birlikte, engellerdi. Bu nedenle o kuralın kârlılığı iyileştirdiği hafta sonu verisiyle doğrulanmış değildir. Bununla birlikte, doğrulanmamış eski kârı korumak için veto hemen kaldırılmamalı. Önce gerçek dolum ve zaman sıralı fiyat takibi doğrulanmalı; sonra kripto hafta sonu ve Forex hafta içi ayrı gruplarda incelenmeli.

## Pragmatik yorum

Peşinden gidilecek aday, özellikle üst likidite sonrasındaki short SFP dönüşleridir. Bu fiyat fikrini koruyup gerçek retest, doğru fiyat adımı ve sonraki mum takibiyle sınamak gerekir. Mevcut +19,15R ekran toplamını strateji avantajının kanıtı saymak doğru değil. Bu bulgu projeyi değersiz yapmaz; sinyal fikrinin performansını, iyimser icra kaydının etkisinden ayırmamız gerektiğini gösterir.

Kanıtlar: `recorded_trade_audit.json`, `entry_price_checks.json`, `price_manifest.json`, kopyalanmış özgün defter/telemetri ve resmi kaynak ZIP dosyaları. Resmi arşiv biçimi: https://github.com/binance/binance-public-data/blob/master/README.md .
