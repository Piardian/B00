# XAUUSD London ORB — sabit kurallı geliştirme testi

**Karar: Önceden belirlenen geliştirme kapısı geçilmedi; bu uygulamada edge doğrulanmadı.**

Ocak–Haziran 2025, tek enstrüman ve tek giriş/çıkış modeli. Tarihler ve kurallar sonuçlar görülmeden donduruldu. Bu dönemler önceki geniş araştırmalarda kullanılmıştı; yeni modelin gerçek ileri testi veya bütün geçmiş denemelerden bağımsız OOS verisi değildir.

**Kapsama tam.** Bilinmeyen fiyat günü yok; doğrulanmış iki piyasa tatili işlem fırsatı sayılmadı.

## Sabit kurallar

London yerel 08:00–08:15 yarı açık BID aralığı. İlk mumun yönünde, 08:15 sonrasında bandın ilk BID teması/kırılımı; giriş 12:00’den kesin önce. Günde tek deneme. Stop karşı BID bantta sanal/yapısal tetik; pozisyonun tamamı yeni giriş riskinden 2R hedefte veya 16:00 London ilk quote’unda kapanır. Hacim filtresi, retest, M1 teyidi, TP1, BE ve trailing yok.

Alış ASK + kayma, satış BID − kayma. Uzun çıkış BID, kısa çıkış ASK. Kısa stop tetikleyicisi de BID bandıdır; gerçek broker ASK stop emriyle aynı değildir. Giriş quote’unda çıkış yok; aynı zaman damgasındaki sonraki kayıt kullanılabilir. Stop gap’inde kötü fiyat, hedef gap’inde hedefle sınırlı fiyat kullanılır. 16:00 itibarıyla EOD önceliklidir. R tek işlem başına ilk fiyat riskidir; gerçek hesap/prop kuralı veya bileşik sermaye getirisi değildir.

## Maliyet ve kanıt sınırı

Broker sembolü XAUUSD: kontrat 100 ons, fiyat adımı 0,01 USD, minimum lot ve adım 0,01. [The5ers resmî komisyon açıklaması](https://the5ers.com/faqs/what-are-the-spreads-and-commissions/) altın için yüzde formülü veriyor; sayısal oran yayımlamıyor. [Resmî kontrat tablosu](https://lp.the5ers.com/hub-assets-specifications/) 100 onsu doğruluyor.

Mevcut hesaptaki dokuz Ekim 2026 dolumu taraf başına lot başına 4 USD’ye denk geliyor. Küçük lotlarda taraf başına %0,001 de cent yuvarlamasıyla bu ücretleri açıklıyor. Bu örnekler sayısal yüzdeyi tekil belirlemiyor ve 2025 tarifesini doğrulamıyor. Gözlenen BID/ASK geçmiş quote’tur; emir dolum garantisi değildir.

Baştan sabitlenen ihtiyatlı varsayım: lot başına tur ücreti `max(8 USD, 2 × giriş fiyatı × 100 ons × %0,001)`; risk hesabı için 100’e bölünerek ons başına çevrilir. Kayma taraf başına 0,05 USD/ons (5 fiyat adımı). 1,5x/2x senaryoları gözlenen spreadi, komisyonu ve kaymayı birlikte artırır; bu yüzden giriş riskini ve çıkış yolunu da değiştirebilir. FX’in 4 USD tur komisyonu altına kopyalanmadı.

## Sonuçlar

| Gider | İşlem | Net R | PF | Kazanma | Aynı dolumlar: komisyon öncesi R | Birim R max DD |
|---|---:|---:|---:|---:|---:|---:|
| OBSERVED_1x | 113 | +15.56 | 1.221 | %39.8 | +17.36 | 11.60 |
| STRESS_1.5x | 113 | +14.34 | 1.202 | %39.8 | +16.95 | 11.82 |
| STRESS_2x | 113 | +5.07 | 1.068 | %37.2 | +8.42 | 14.04 |

1,5x ana senaryo: **113 işlem, +14.34R**. Toplam R için 5 günlük blok bootstrap %95 aralığı **[-16.84, +45.96]R**.

Komisyon öncesi R, aynı giriş/çıkışlarda yalnız ücretin çıkarılmadığı tanıdır; spread ve kayma hâlâ fiyatların içindedir. Tam sürtünmesiz model veya farklı dolum yolları üzerinde matematiksel üst sınır değildir.

## Aylık dağılım

| Ay | 1x | 1,5x | 2x |
|---|---:|---:|---:|
| 2025-01 | +1.89 | +1.57 | -1.71 |
| 2025-02 | -5.70 | -5.95 | -6.19 |
| 2025-03 | +6.34 | +6.07 | +0.67 |
| 2025-04 | -2.51 | -2.60 | -2.69 |
| 2025-05 | +13.87 | +13.72 | +13.58 |
| 2025-06 | +1.67 | +1.54 | +1.42 |

En iyi 5 kapalı işlem çıkarılınca 1,5x tanısı: **+4.42R**.

2x stresinde en iyi 5 işlem çıkarılınca **-4.82R**. 1,5x toplamının **%95.6** kadarı Mayıs 2025'ten geliyor.

Bunlar yoğunlaşma tanılarıdır; sonradan kazanan gün/parite seçmek veya yeni filtre belirlemek için kullanılmadı. Tek ay yoğunlaşması, nedenin hangi piyasa rejimi olduğu hakkında tek başına nedensel kanıt değildir.

## Veri ve karar kapısı

- Manifest: 129 hafta içi gün. Kullanılabilir quote dosyası 127; doğrulanmış tatil 2.
- İlk 15 dakika doğal M15 fiyat/yön uyumu: 127/127. BID bayraklı tick sayısı ile doğal hacim uyumu 127/127; hacim girişte kullanılmadı.
- Bağımsız TwelveData EURUSD ile aynı broker saati kontrolü 89 güçlü gün, 0 çelişki; ABD/Avrupa DST farkında 1 gün. Bu, bağımsız altın fiyat serisiyle doğrudan korelasyon testi değildir.
- Açılış/EOD quote’u 5 saniye içinde; seans içi en büyük boşluk 60 saniye. Doji veya öğlene kadar giriş olmaması stratejinin belirli no-entry sonuçlarıdır; veri eksikliği değildir. Bilinmeyenler ayrıca işaretlenir.

| Kontrol | Sonuç |
|---|---|
| complete_coverage | GEÇTİ |
| clock_qa | GEÇTİ |
| native_price_qa | GEÇTİ |
| at_least_100_fills | GEÇTİ |
| positive_1_5x | GEÇTİ |
| positive_2x | GEÇTİ |
| stressed_ci_lower_positive | KALDI |
| four_positive_months | GEÇTİ |
| both_quarters_positive | GEÇTİ |

## Eksik günün ayrı sürümde tamamlanması

İlk 2025-01-02 API çağrısı `(-1, Terminal: Call failed)` döndürmüştü. İlk hesapta kapalı alt toplamlar pozitifti; bu sonuçlar görülmüşken yalnız eksik veri onarımı için `repair_protocol_frozen.json` yazıldı. İlk manifest, rapor ve sonuçlar **attempt_01_incomplete/** içinde hashleriyle saklandı. Sıcak Ocak önbelleğinde yeniden sorgu 209,644 quote verdi; diğer bütün günlerin manifest kayıtları ve strateji/gider kaynak hashleri aynı kaldı. Onarılan gün bir kaybeden işlemdir ve buradaki tam dönem toplamına dahil edildi. Bu işlem, sonuçlara göre gün eleme veya yeni OOS testi değildir.

## Araştırma kararı

Bu tek model geliştirme kapısını geçmedi. Başlangıçta belirlenen politika gereği Temmuz–Ağustos rezervinde performans aranmadı; kapıyı geçmek için tarih, saat, stop/hedef veya filtre değiştirilmedi. Bu London FX/altın ORB araştırma kolu mevcut haliyle canlı adaylığından çıkarılır. Sonuç bütün ORB ailesinin her piyasada çalışamayacağını kanıtlamaz.

## Tekrar üretim ve sınırlamalar

- Toplam saklanan quote: 41,535,190; ağırlıklı sıfır spread oranı %0.00. Brokerın tarihsel sıfır spread kaydı gelecekte/gerçekte aynı dolum garantisi değildir.
- 10 dondurulmuş kaynak/referans hash’i ve kullanılan quote dosyaları başta/sonda doğrulandı. 9 odaklı test geçmişti; kurallar değiştirilmedi.
- Bootstrap 10.000 dairesel 5 hafta içi gün bloğu, seed 173. Tek enstrüman ve görülmüş altı aylık örneklem; önceki strateji/piyasa seçimleri için çoklu deneme düzeltmesi içermez. Pozitif tarihsel toplam tek başına edge değildir.
- İlk veri toplama girişimi disk yüzünden durmuştu. Bu devamda dış disk koruması kullanıldı; mevcut bağlı The5ers oturumuna yalnız tarihsel okuma yapıldı. Mevcut oturumun global otomatik işlem izni açıktı; bu çalışma onu veya başka çalışan botların ayarını değiştirmedi. Araştırma kaynaklarında order_send/order_check/position değiştirme çağrısı yok. Bu çalışmadan canlı/paper emir gönderilmedi.
- `protocol_frozen.json`, `quote_manifest_frozen.json`, `clock_qa.json`, `native_qa.json`, `cost_evidence.json`, `outcomes.json`/CSV, `results.json`, `integrity_check.json` ve `report_diagnostics.json` delil zincirini içerir. Sonuçlar frozen_sources altında korunan tek model içindir.
