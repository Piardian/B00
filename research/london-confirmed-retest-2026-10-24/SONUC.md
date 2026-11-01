# London ORB: kapanış + retest + M1 kırılım keşif denemesi

**Karar: önceden belirlenen geliştirme kapısı geçilmedi; bu varyantta doğrulanmış edge yok.**

**Kapsama eksik: iki parite-günde teyit sonrası 5 saniye içinde quote yok. Aşağıdaki R/PF değerleri yalnız çözümlenmiş kapalı işlemlerin alt toplamlarıdır; tam altı aylık sonuç değildir. Eksik günlere sıfır veya hayali dolum atanmadı.**

Bu çalışma, kullanıcının izin verdiği sınırlı araştırma turundaki tek yeni giriş hipotezidir. Altı ayın sonuçları ve fiyat yolu teşhisi zaten görüldü. Dolayısıyla burada pozitif sonuç çıksa bile OOS/bağımsız doğrulama sayılmaz. Basit retest temasının kazananı kaybedenden ayırdığına dair teşhiste kanıt çıkmadı; bu çalışma onu başarılı kabul etmiyor. Mum kapanışıyla kırılım ve sonraki teyit, ayrı bir keşif hipotezidir.

## Sabit giriş kuralı

1. London yerel 08:00–08:15 doğal BID aralığı ve açılış yönü korunur. İlk tamamlanmış M1 mumunun bu yönde aralık dışında **kapanması** beklenir. İlk kırılım 08:15 mumundan itibaren olabilir.
2. Kırılım mumu tamamlandıktan sonraki quote’larda fiyatın kırılan dış banda dönmesi beklenir. Kırılım mumundaki temas kullanılamaz.
3. Retest mumundan sonraki tamamlanmış bir M1 mumu önceki tamamlanmış M1 tepe/dibini işlem yönünde kapanışla aşmalı ve açılış aralığının dışında kapanmalıdır. Bu, görsel swing seçiminin birebir taklidi değildir.
4. Giriş, teyit kapanışından sonraki dakikanın ilk quote’unda (en fazla 5 saniye gecikmeyle), 12:00 London’dan kesin önce yapılır. Teyit mumunun tepe/dibi içinde geriye dönük dolum verilmez.
5. İlk kapanış kırılımından girişe kadar karşı BID stop bandı bozulursa gün iptal olur; ikinci setup aranmaz. Her parite-günde tek deneme.
6. Stop karşı BID bantta; hedef yeni giriş riskinden tam 2R; EOD 16:00 London. TP1/BE/trailing yok. Önceki doğrudan girişle aynı quote kaynağı ve gider varsayımları.

Önceki negatif M1 teyit testleri orta bant/pasif limit adayları ve farklı yaşam döngülerindeydi. Bu denemede klasik dış aralık sınırı ve tam 2R çıkış kullanılır. Önceki sonuçlar silinmez ve farklı motorların R toplamları birleştirilmez.

## Altı aylık penceredeki bilinen kapalı işlemler

| Grup | Maliyet | Bilinen dolum | Bilinen net R | PF | Ortak çözümlenmiş günlerde doğrudan girişe fark |
|---|---|---:|---:|---:|---:|
| RVOL ≥ 1 | OBSERVED_QUOTES_1x | 200 | -5.17 | 0.959 | -13.08 |
| RVOL ≥ 1 | COST_STRESS_1.5x | 200 | -9.12 | 0.929 | -2.94 |
| RVOL ≥ 1 | COST_STRESS_2x | 200 | -12.98 | 0.901 | +1.05 |
| RVOL ≥ 1 | MIN_SPREAD_1PIP | 200 | -12.01 | 0.906 | +11.68 |
| Hacim filtresiz kontrol | OBSERVED_QUOTES_1x | 548 | -82.75 | 0.782 | -15.02 |
| Hacim filtresiz kontrol | COST_STRESS_1.5x | 548 | -100.74 | 0.742 | -3.34 |
| Hacim filtresiz kontrol | COST_STRESS_2x | 548 | -114.40 | 0.714 | +11.99 |
| Hacim filtresiz kontrol | MIN_SPREAD_1PIP | 548 | -111.15 | 0.713 | +18.38 |

Ana senaryo 1,5x: **200 bilinen kapalı işlemde -9.12R**. Toplam 289 uygun parite-günün 2 tanesi çözümlenmedi. Yalnız ortak çözümlenmiş 287 günde doğrudan girişe fark **-2.94R**; bu alt örneklem farkının %95 blok aralığı **[-31.47, +24.61]R**. Daha az zarar etmek pozitif edge değildir. İki girişte farklı ilk risk mesafeleri olduğundan fark dolar veya gerçek hesap getirisi değildir.

`results.json` içindeki toplam CI ve ham paired_delta alanları bilinmeyen günlerin pozisyonları eksik olduğu için tam dönem doğrulamasında kullanılmaz. Bu rapordaki eşleştirme `coverage_audit.json` ile iki günde her iki politikayı da karşılaştırmadan çıkarır; bu seçilmiş alt örneklem de tam dönem yerine geçmez.

## Ana grubun aylık bilinen kapalı işlem alt toplamları

| Ay | 1x | 1,5x | 2x | En az 1 pip spread |
|---|---:|---:|---:|---:|
| 2025-02 | +7.51 | +7.12 | +6.74 | +7.25 |
| 2025-03 | +19.64 | +18.91 | +18.19 | +16.61 |
| 2025-04 | +6.37 | +6.00 | +5.64 | +6.20 |
| 2025-05 | -2.43 | -2.75 | -3.07 | -5.65 |
| 2025-09 | -24.80 | -25.83 | -26.83 | -24.84 |
| 2025-10 | -11.46 | -12.57 | -13.65 | -11.58 |

Eylül ve Ekim alt toplamlarında birer bilinmeyen parite-gün vardır. Bu iki ay için tam aylık net getiri iddiası yok.

## Ana grup 1,5x: girişin oluşmama nedenleri

| Durum | Parite-gün |
|---|---:|---:|
| CLOSED | 200 |
| NO_COMPLETED_BREAKOUT | 49 |
| INVALIDATED_BEFORE_ENTRY | 25 |
| NO_RETEST | 11 |
| BLOCKED_ENTRY_COVERAGE | 2 |
| DOJI_OR_INVALID_RANGE | 1 |
| NO_CONFIRMATION_BEFORE_NOON | 1 |

## Karar kapısı

| Kontrol | Sonuç |
|---|---|
| complete_coverage | KALDI |
| at_least_100_primary_fills | GEÇTİ |
| positive_1_5x | KALDI |
| positive_2x | KALDI |
| positive_min_1pip | KALDI |
| stressed_ci_lower_positive | KALDI |

## Sınırlar ve doğrulama

- Kapsama: EKSİK: kapalı işlem alt toplamı tam dönem sonucu değildir. İlk quote/EOD 5 saniye, seans içi boşluk 60 saniye; gerekli M1 BID barı yoksa bilinmeyen olarak bloklanır.
- Gözlenen BID/ASK; 100 bin birim için tur başına 4 USD komisyon ve taraf başına 0,1 pip kayma varsayımı. Kişisel tarihsel hesap faturasıyla doğrulanmış değil. 1,5x/2x spread, komisyon ve kaymayı ağırlaştırır; en az 1 pip senaryosu max(gözlenen spread, 1 pip) kullanır. Kısa stop BID tetik/ASK çıkıştır; gerçek broker ASK stop emri değildir.
- 11 odaklı test geçti: teyit sonrası giriş, aynı retest mumunda teyit yasağı, stop öncesi iptal, eksik dakika, 12:00 sınırı, kısa simetri, mevcut motorla EOD/TP/SL maliyet eşleşmesi, gap fiyatları ve salt okuma bağımlılıkları.
- Kaynaklar ve kullanılan 780 quote dosyası başta/sonda SHA256 ile doğrulandı. Emir API çağrısı veya canlı/paper işlem yok. Üretim stratejisi ve çalışan süreçler değiştirilmedi.
- Aynı gün bütün pariteler birlikte: 5 gözlenen iş günü blokları, 10.000 örnekleme, seed 173. Takvim blokları kesintilidir; çoklu araştırma düzeltmesi yok. R bağımsız fırsat toplamıdır; eşzamanlı risk, marjin, prop zarar sınırı veya hesap drawdown modeli değildir.

## İki bilinmeyen girişin brokerdan tekrar kontrolü

The5ers terminalinden yalnız bu iki birer dakikalık pencere yeniden okundu. NZDUSD 2025-10-09 teyit 09:54:00 UTC: ilk quote 6,217 saniye sonra. USDCAD 2025-09-08 teyit 07:20:00 UTC: ilk quote 5,087 saniye sonra. Yeniden alınan pencereler dondurulmuş kayıtla birebir aynı (59 ve 111 quote); veri indirme hatası gösterilmedi. Bu, emirlerin gerçek dolumunu kanıtlamaz. Sabit 5 saniye kuralı gevşetilmedi; bilinmeyenler korundu. Ayrıntı `entry_coverage_verification.json`.

Sonraki karar: bu varyant kapıyı geçmediyse bu turda eşik, saat, hedef veya parite seçerek kurtarılmayacak. Klasik London FX ORB ve bu teyit varyantı canlı adayı olarak rafa kalkar. Eksik kapsama nedeniyle tam dönem beklenen getirinin kesin olarak negatif olduğu da iddia edilmez; mevcut kanıt terfi için yetersizdir. Geçtiyse de önce ayrı, henüz bu giriş politikasıyla değerlendirilmemiş dönem protokolü gerekir.

Dosyalar: `protocol_frozen.json`, `outcomes.json` / `outcomes.csv`, `results.json`, `integrity_check.json`; kaynaklar `frozen_sources/` altında. Tekrar hesaplama: `python study.py run` (aynı klasörden).
