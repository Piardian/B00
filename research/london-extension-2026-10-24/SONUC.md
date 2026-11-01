# London ORB: dört yeni ay ve altı aylık birleşik denetim

**Karar: bu testte doğrulanmış edge yok; önceden belirlenen araştırma kapısı geçilmedi.**

Yeni dönemler sonuçlar görülmeden Nisan, Mayıs, Eylül ve Ekim 2025 olarak sabitlendi. Önceki Şubat–Mart korunarak altı aylık birleşim ayrıca hesaplandı. Altı majör: EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF, NZDUSD. Tarihsel yeniden oynatma; gerçek ileri test veya bütün araştırma geçmişinden bağımsız OOS değildir.

## Değişmeyen kurallar

Londra yerel saatiyle 08:00–08:15 BID aralığı; açılış mumunun yönünde ilk kırılım; parite başına günde bir deneme; yeni giriş 12:00 öncesi. Stop karşı BID bantta sanal/yapısal tetik, hedef tam 2R, gün sonu çıkışı 16:00 Londra. Ana aday: ilk 15 dakika doğal broker BID tick hacmi / önceki 14 uygun gün ortalaması ≥ 1. Kontrol: aynı sistem, hacim filtresiz. Bu klasik araştırma modeli botun retest/M1 teyitli tüm üretim sistemiyle aynı değildir.

Alış ASK, satış BID; uzun çıkış BID, kısa çıkış ASK. Komisyon 100 bin birim için tur başına 4 USD ve kayma taraf başına 0,1 pip varsayımıdır; tarihsel kişisel hesap faturasıyla doğrulanmış değildir. 1,5x/2x senaryoları gözlenen spreadi, kaymayı ve komisyonu ağırlaştırır; değişen spread çıkışları da etkileyebilir. 1 pip taban senaryosu max(gözlenen spread, 1 pip) kullanır. BID stopun özellikle kısa pozisyonda broker ASK stopuyla aynı olmadığı dikkate alınmalıdır.

## Sonuçlar

### Yalnız dört yeni ay

| Model | Maliyet | İşlem | Net R | PF | Kazanma |
|---|---|---:|---:|---:|---:|
| RVOL ≥ 1 | OBSERVED_QUOTES_1x | 176 | -10.16 | 0.912 | %35.8 |
| RVOL ≥ 1 | COST_STRESS_1.5x | 176 | -19.59 | 0.837 | %34.1 |
| RVOL ≥ 1 | COST_STRESS_2x | 176 | -25.83 | 0.789 | %34.1 |
| RVOL ≥ 1 | MIN_SPREAD_1PIP | 176 | -34.82 | 0.719 | %31.8 |
| Hacim filtresiz kontrol | OBSERVED_QUOTES_1x | 483 | -50.73 | 0.846 | %34.6 |
| Hacim filtresiz kontrol | COST_STRESS_1.5x | 483 | -71.07 | 0.792 | %33.5 |
| Hacim filtresiz kontrol | COST_STRESS_2x | 483 | -93.92 | 0.733 | %32.7 |
| Hacim filtresiz kontrol | MIN_SPREAD_1PIP | 483 | -102.62 | 0.704 | %31.3 |

Ana adayın gözlenen maliyette toplam R için %95 blok bootstrap aralığı: **[-47.03, +31.87] R**. En iyi 5 işlemi çıkarınca: **-20.09 R**. Bu çıkarma yalnız duyarlılık tanısıdır, bağımsız bir edge testi değildir.

### Şubat–Mart dahil altı ay

| Model | Maliyet | İşlem | Net R | PF | Kazanma |
|---|---|---:|---:|---:|---:|
| RVOL ≥ 1 | OBSERVED_QUOTES_1x | 254 | +8.78 | 1.054 | %38.2 |
| RVOL ≥ 1 | COST_STRESS_1.5x | 254 | -5.37 | 0.968 | %36.6 |
| RVOL ≥ 1 | COST_STRESS_2x | 254 | -13.29 | 0.923 | %36.6 |
| RVOL ≥ 1 | MIN_SPREAD_1PIP | 254 | -22.82 | 0.868 | %34.6 |
| Hacim filtresiz kontrol | OBSERVED_QUOTES_1x | 701 | -66.86 | 0.863 | %34.5 |
| Hacim filtresiz kontrol | COST_STRESS_1.5x | 701 | -96.60 | 0.808 | %33.7 |
| Hacim filtresiz kontrol | COST_STRESS_2x | 701 | -125.64 | 0.757 | %33.1 |
| Hacim filtresiz kontrol | MIN_SPREAD_1PIP | 701 | -128.66 | 0.746 | %31.8 |

Ana adayın gözlenen maliyette toplam R için %95 blok bootstrap aralığı: **[-38.91, +60.56] R**. En iyi 5 işlemi çıkarınca: **-1.15 R**. Bu çıkarma yalnız duyarlılık tanısıdır, bağımsız bir edge testi değildir.

## Ana adayın aylık dağılımı

| Ay | 1x | 1,5x | 2x | Min. 1 pip |
|---|---:|---:|---:|---:|
| 2025-02 | +4.44 | +3.81 | +3.20 | +3.33 |
| 2025-03 | +14.50 | +10.41 | +9.34 | +8.67 |
| 2025-04 | +7.58 | +6.98 | +6.40 | +4.48 |
| 2025-05 | +4.27 | +3.93 | +2.46 | +4.08 |
| 2025-09 | -14.46 | -18.67 | -21.64 | -28.60 |
| 2025-10 | -7.55 | -11.82 | -13.04 | -14.78 |

## Parite dağılımı (yeni dört ay, ana aday, 1,5x)

| Parite | İşlem | Net R |
|---|---:|---:|
| EURUSD | 28 | +6.94 |
| GBPUSD | 32 | -7.08 |
| USDJPY | 33 | -3.39 |
| USDCAD | 30 | -5.18 |
| USDCHF | 28 | -4.45 |
| NZDUSD | 25 | -6.43 |

Bu parite kırılımı sonuç sonrası betimlemedir. Zararlı pariteleri çıkararak yeni bir doğrulanmış portföy ilan edilmedi.

## Bulguların anlamı

Şubat–Mayıs pozitif, Eylül–Ekim negatiftir. Dört yeni ay gözlenen maliyette bile zarardadır; sorun yalnız ağır maliyet varsayımı değildir. Altı ayın gözlenen maliyetteki küçük artısı maliyet stresinde kaybolur ve güven aralığı sıfırı kapsar. RVOL filtresi kontrolün kaybını azaltmış görünür, ancak tek başına kalıcı pozitif beklenti kanıtı sağlamaz. Nedenin piyasa rejimi olduğu bu sonuçtan kanıtlanamaz.

Bu haliyle klasik ORB + RVOL ≥ 1 adayı canlıya taşınmaz. Sonuç sonrası kötü ay/parite elemek veya eşiği kâra göre değiştirmek mevcut testi kurtarmak sayılmaz. Yeni giriş hipotezi araştırılacaksa ayrı protokol ve bu sonuçlardan bağımsız doğrulama gerektirir.

## Veri, kontroller ve karar kapısı

- 702 parite-gün dosyası (ısınma dahil); doğal M15 hacim/tepe/dip/yön kontrolü 702 / 702 uyumlu.
- Bağımsız fiyat serisiyle saat kontrolü: 87 güçlü gün, 0 saat çelişkisi. Dış veri yalnız saat kontrolünde kullanıldı; işlemler The5ers BID/ASK üzerinde hesaplandı.
- Kapsama durumu: tam. Açılış ve EOD fiyatına 5 saniye sınırı, içeride 60 saniye boşluk sınırı uygulandı.
- Sabit kaynak hashleri yeniden doğrulandı. 14 odaklı test geçti. Hiçbir canlı/paper emir API çağrısı yapılmadı; üretim stratejisi bu genişletmede değiştirilmedi.
- Aynı günün pariteleri birlikte toplanarak 5 gözlenen iş günlü dairesel bloklarla 10.000 örnekleme, seed 173. Ayrı takvim blokları birleşince sınırdaki bitişiklik gerçek kesintisiz takvim değildir. Güven aralığı araştırma boyunca denenmiş bütün stratejiler için çoklu deneme düzeltmesi içermez.

| Kapı | Dört yeni ay | Altı ay birleşik |
|---|---|---|
| complete_coverage | GEÇTİ | GEÇTİ |
| clock_qa | GEÇTİ | GEÇTİ |
| native_qa | GEÇTİ | GEÇTİ |
| frozen_source_integrity | GEÇTİ | GEÇTİ |
| at_least_100_primary_fills | GEÇTİ | GEÇTİ |
| positive_1_5x | KALDI | KALDI |
| positive_2x | KALDI | KALDI |
| positive_min_1pip | KALDI | KALDI |
| observed_block_ci_lower_positive | KALDI | KALDI |

R toplamları bağımsız fırsatların birim risk toplamıdır; gerçek hesap getirisi, eşzamanlı pozisyon/marjin sınırı, prop günlük zarar sınırı veya hesap drawdown ölçümü değildir. Quote kaydı emir dolum garantisi değildir. Önceki negatif mum/sentetik spread deneyleri bu farklı motorun toplamına eklenmedi; önceki araştırma sonuçları geçersiz sayılmadı.

## Tekrar üretme

`protocol_frozen.json`, `quote_manifest_frozen.json`, `native_qa.json`, `clock_qa.json`, `integrity_check.json` girdileri ve denetimi; `outcomes.json` / `outcomes.csv` yeni işlemleri; `results.json` yeni ve birleşik sonuçları; `gate_results.json` karar kapısını içerir. `extension.py replay` aynı hashlerle yeniden hesaplar (parite kontrol noktalarını kullanır). Kaynaklar `frozen_sources/` altında korunur.
