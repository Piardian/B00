# Forex / Altın edge ve canlıya hazırlık — bağımsız inceleme

23 Ekim 2026. İncelenen commit: `044e4b3219038ec9965c182fff40b423d856edd1`.

Sonraki kod/rapor düzeltmeleri ve güncel Ocak denemesi: [doğrulama düzeltmeleri](FOREX_GOLD_VALIDATION_FIXES_2026-10-23.md). Aşağıdaki bulgular inceleme anındaki sürüme aittir; makro bayatlığı ve ortak takipçideki geçmişe dönük ücretsiz iptal daha sonra giderildi.

**Karar: EURUSD–GBPUSD–XAUUSD üçlüsü araştırma adayı olarak korunabilir; doğrulanmış istatistiksel edge ve gerçek para ile canlıya geçiş için yeterli kanıt yok.**

Bu inceleme kaynak kodu ve mevcut MT5 Parquet dosyalarını yeniden çalıştırdı. Yayıncının `main()` fonksiyonu çağrılmadı; özgün CSV, rapor, canlı ayarlar ve emirler değiştirilmedi. Ücretli/model/piyasa API çağrısı yapılmadı. Veriler ve incelenen kaynakların SHA256 kayıtları `data/forex_gold_independent_review_20261023/review.json` içindedir.

## 1. P1 — Rapor, ham işlem defterinin sonucu değil

Kaynak `run_symbol()` fonksiyonu üç enstrümanda yeniden çalıştırıldı. Sembol, açılış/kapanış, giriş/stop, brüt/maliyet/net R ve kapanış nedeni alanları mevcut CSV ile birebir eşleşti.

| Metrik | Bildirilen | Ham defterden yeniden hesaplanan |
|---|---:|---:|
| İşlem | 342 | 343 |
| Kazanç / kayıp | 201 / 141 | 201 / 142 |
| Net R | +43,56 | +32,71 |
| PF | 1,28 | 1,20 |
| t | 2,11 | 1,55 |
| İki taraflı p | İlk mesajda 0,0010; raporda 0,0356 | 0,1210 |
| Ortalama işlem R | +0,127 | +0,095 |
| Ortalama için %95 GA | [+0,009; +0,245] | [-0,025; +0,216] |
| Kapanmış işlem eğrisi DD | 12,64R | 14,67R |

Yeniden hesaplanan sütun, kaynak kodunun mevcut dinamik maliyetleridir; 1,5 katsayısı kaynak varsayılanında uygulanmıyor. Çıktıyı 1,5x broker maliyeti diye sunmak doğru değil. Kodun `rep_text` bölümünde 342, +43,56R, t=2,11 ve bootstrap sonuçları hesaplanan değişkenlere bağlanmadan sabit metin olarak bulunuyor (`scripts/audit_forex_gold_hardened.py:537`). Dolayısıyla terminaldeki yeni hesap değişse bile yazılan rapor eski iddiayı tekrar ediyor.

Aynı kaynak bootstrap fonksiyonunun gerçek defterde yeniden hesaplanan %95 toplam R aralığı **[-11,87; +77,12]**; sıfır-altı yeniden örnekleme oranı **%7,66**. Bu oran hipotezin yanlış olma olasılığı değildir. Klasik t hesabı da IID varsayımı taşır; çoklu deneme/seçim düzeltmesi ve bağımsız OOS kanıtı yok.

## 2. P1 — Simüle edilen giriş, canlı Begonya00 girişi değil

İncelenen simülatör yalnız `is_slice_through_candle` yardımcı fonksiyonunu içeri alıyor; asıl SFP/ORB dedektörünü, `validate_signal`, MacroGateClient, NewsGuard, risk frenlerini veya OutcomeTracker yaşam döngüsünü çağırmıyor.

| Boyut | Araştırma simülatörü | Mevcut canlı kaynak |
|---|---|---|
| Likidite seviyesi | Son 30 mumun en yüksek/düşüğü | PDH/PDL ve Asya havuzları + yapı koşulları |
| Giriş | Süpürme ucu ile kapanışın ortası | Breaker + iFVG, FVG %50 CE |
| Yapı | Breaker/MSS/iFVG doğrulaması yok | Zorunlu |
| Hacim | 1,3 × 20 mum ortalaması | Asıl dedektörün hacim/yapı değerlendirmesi |
| Mum takibi | 15 dakika | Kapanmış 1 dakika |
| Makro/haber | Yok | Yön/risk kapısı ve haber vetosu |
| Portföy freni | Sembollere bağımsız uygulama | Günlük/seri kayıp, toplam ve ortak para birimi risk limitleri |
| HTF ısınması | EMA ilk değerlerden başlar | 200 gözlem zorunluluğu |

TP1=1,2R ve TP2=2R değerlerinin eşit olması bu sistemleri aynı yapmaz. `config.py` üçlüye daraltılmış ve bu TP ayarlarına geçirilmiş, ancak araştırma sonucu canlıdaki iFVG/Breaker kurallarını doğrulamıyor. Bu test ayrı bir SFP adayının fırsat simülasyonudur.

Ek hata: iki mumlu sweep koşulunda `p_high > max(highs[i-30:i])` ve simetriği kullanılıyor. Önceki mum bu pencerenin içinde olduğundan bu karşılaştırma hiçbir zaman doğru olamaz. İki mumlu dal gerçekte çalışmıyor.

## 3. P1 — Giriş öncesindeki hareketi aynı mumda TP2 olarak sayma

Defterde **53 TP2**, limitin dolduğu 15 dakikalık mumda yazılmış. Kaynakta dolumdan sonra aynı mumun tüm yüksek/düşüğüyle hedef kontrolü yapılıyor. Stop önceliği, hedefin girişten önce gerçekleşmiş olması sorununu çözmüyor.

Yerel gerçek M1 kaynaklarından 10 örnekte eksiksiz 15 dakika ve M15 OHLC ile birebir geometri eşleşmesi bulundu. **5 örnekte TP2 yalnız girişten önce görülüyor; ilk olası dolum dakikasında ve sonrasında tekrar görülmüyor.** Bu alt küme veri erişimine göre seçildi; tüm 53 işlem için hata oranı tahmini değildir.

| İşlem | Sembol | İlk TP2 (UTC) | İlk olası limit dolumu (UTC) | Deftere yazılmış net R |
|---|---|---|---|---:|
| TR_0103 | EURUSD | 2025-06-06 07:00:00+00:00 | 2025-06-06 07:03:00+00:00 | +1,4333 |
| TR_0187 | EURUSD | 2025-11-06 15:45:00+00:00 | 2025-11-06 15:56:00+00:00 | +1,4824 |
| TR_0194 | EURUSD | 2025-11-21 08:01:00+00:00 | 2025-11-21 08:10:00+00:00 | +1,4421 |
| TR_0191 | GBPUSD | 2025-11-17 11:45:00+00:00 | 2025-11-17 11:52:00+00:00 | +1,4421 |
| TR_0100 | XAUUSD | 2025-06-03 13:30:00+00:00 | 2025-06-03 13:35:00+00:00 | +1,5049 |

Bu beş kayıtta toplam **+7,3048R** var. Bu kazançların doğrulanmaması tüm sonucu aynı miktarda düşürerek düzeltilemez: gerçek takipte işlemler daha uzun açık kalabilir, daha sonra stop olabilir veya başka sinyalleri engelleyebilir. Doğru çözüm zaman sıralı yeniden oynatmadır.

Ek olarak, limit temasını gördükten sonra tam mum kapanışıyla 50 slice-through adayı iptal edilmiş; bunların 50’si de aynı mumda stop seviyesine ulaşmış. Gerçek dinlenen limit emri ile mum kapanışından sonra tepki onayı iki farklı icra sözleşmesidir. Bu koşulları birlikte kullanıp iyi mumlarda dolum/TP yazmak, kötü mumlarda geçmişe dönük emir iptali yapmak tutarlı kötümser icra değildir. Canlıdaki mevcut tepki onayı ve sonraki mumdan takip de bu simülatörden farklıdır.

## 4. Maliyet duyarlılığını gerçekten yeniden çalıştırınca

Katsayı tüm spread mesafelerine, komisyona ve stop kaymasına uygulandı. Sinyal kuralları, TP parametreleri ve kaynak `run_symbol()` değişmedi. Maliyet çarpanı limitin nüfuz şartını da değiştirdiği için her senaryo ham mumlarda yeniden yürütüldü. Bunlar hâlâ yukarıdaki ayrı simülatörün sonuçlarıdır; icra kusuru düzeltilmiş tam sistem sonucu değildir.

| Dinamik maliyet | İşlem | Net R | PF | İki taraflı p |
|---|---:|---:|---:|---:|
| 1,0x | 343 | 32,71 | 1,20 | 0,1210 |
| 1,5x | 343 | 7,15 | 1,04 | 0,7381 |
| 2,0x | 342 | -19,50 | 0,90 | 0,3678 |

Aynı dolum listesini sabit tutup yalnız maliyetleri çarpmak da ayrı olarak hesaplandı: sonuç 1,5x için +7,77R, 2,0x için −17,18R. Bu farklı hesap, yeniden oynatmayla karıştırılmamalı.

Forex ham barlarında spread sütunu EURUSD için yaklaşık %95,51, GBPUSD için %95,05 oranında sıfır. Bu değerler tek başına yanlış veri kanıtı değildir, ancak gerçek giriş/çıkış bid–ask maliyeti ve hesap komisyonu ile doğrulanmadan maliyetin doğrulandığı iddia edilmemelidir. Tick volume, işlem hacmi veya kurumsal banka emir akışı kanıtı değildir.

## 5. P2 — Saat ve HTF başlangıç farkları

Kaynak manifesti fiyatları `MT5 raw broker clock` olarak tanımlıyor. Aynı brokerın metadata ölçümü yaklaşık +10.799 saniye fark gösteriyor. Yükleyici ise bu endeksi doğrudan UTC kabul ediyor; seanslar ve 4H grupları yanlış saatlere bağlanıyor. Yerelde bağımsız fiyat karşılaştırmasıyla doğrulanmış UTC+2/UTC+3 New York DST dönüşümü kullanılarak saat kontrolü yapıldı.

Ayrıca 29 işlem, 200 adet 4H gözlem oluşmadan açılıyor. Aşağıdaki kontroller parametre optimizasyonu değil, bu iki giriş varsayımının etkisini ölçen tekil düzeltmelerdir. Bunlar canlı dedektör paritesi sağlamaz.

| Kontrol | İşlem | Net R | İki taraflı p |
|---|---:|---:|---:|
| Yalnız 200 H4 ısınması | 314 | 29,76 | 0,1416 |
| Yalnız broker → UTC | 337 | 22,39 | 0,2766 |
| Saat + ısınma | 310 | 22,28 | 0,2606 |

## 6. P2 — Makro dosyasının yaşını denetleyen koruma yok

İzole, geçici dosyada `timestamp=2000-01-01`, EURUSD LONG_ONLY ve risk 0,5 verildi. Mevcut MacroGateClient bu kapıya izin verdi. İstemci zaman damgasını okuyor ama yaşını doğrulamıyor. Makro servisi kota veya bağlantı nedeniyle durursa eski kapı yeni işlemleri yetkilendirmeye devam edebilir. Bu testte canlı makro dosyası değiştirilmedi.

## 7. Canlıya geçiş kararı ve somut sonraki sıra

1. Rapor sayıları hesaplanan aynı işlem defterinden otomatik türetilmeli. Tarihli özet ile ham dosya uyuşmazken sermaye kararı verilmemeli.
2. Asıl canlı dedektör, makro/haber kapıları, risk frenleri ve işlem takibi aynı yeniden oynatma yoluna bağlanmalı. Yeni bir giriş modeliyle bu doğrulama yapılmamalı.
3. 53 aynı-mum TP2 dahil dolum/çıkış sırası M1/tick veride çözülmeli; çözülmeyen kayıtlar kâr kanıtı sayılmamalı. Bid/ask ve gerçek hesap maliyetleri ayrıca doğrulanmalı.
4. Saat ve ısınma kuralları ortaklaştırılmalı; makro bayatlığı için açık başarısızlıkta veto davranışı tanımlanmalı.
5. Varlıklar ve parametreler bundan sonra sabitlenip görülmemiş dönemde ve paper forward izlemede doğrulanmalı. İlk 25–50 gerçekleşmiş işlem canlı/test eşleşmesini incelemek için yararlı olabilir; bu sayı tek başına istatistiksel edge kanıtı değildir.

**Olumlu bulgu:** Gerçek ham broker verileriyle tekrar üretilebilen pozitif bir araştırma adayı var; üçlüyü araştırmadan çıkarmak için neden yok. **Eksik olan:** bunun canlı Begonya00’a ait, maliyete dayanıklı ve istatistiksel olarak doğrulanmış bir avantaj olduğu kanıtı. Mevcut bulgular kriptonun bütün koşullarda çalışamayacağını da kanıtlamaz.

Çalıştırma: `python scripts/review_forex_gold_edge.py`. Bu komut yalnız bağımsız inceleme klasörüne yazar.

Kaynaklar: `scripts/audit_forex_gold_hardened.py`, `data/forex_gold_verified_trades.csv`, mevcut canlı kaynaklar, Megalord raw-validation MT5 Parquet/manifest/metadata dosyaları ve geometriyle doğrulanan yerel M1 arşivleri. Tüm kullanılan ana dosya SHA256 değerleri JSON raporundadır. İstatistik tanımı: https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_1samp.html .
