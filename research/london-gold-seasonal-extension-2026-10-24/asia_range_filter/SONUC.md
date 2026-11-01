# London XAUUSD ORB: Asya araligi baglami

**Hipotez:** London 08:00-08:15 M15 kapanisi yonunde Asya 00:00-08:00 araligini terk etmisse ORB denemesi yap. Tam32nativeM15 bar yoksa o gunu bilinmeyen say.

Esik veya seans degistirilmedi; yaz tatili ve maliyet filtresi eklenmedi. Giris/stop/2R/EOD ve maliyetler orijinal motorla ayni. Bu kural daha once genis arastirmada tarihleri gorulmus veride post-hoc kesif hipotezidir; ileri test/OOS degildir.

| Donem | Maliyet | Bilinen gun | Uygun gun | Islem | NetR | PF | Eslesik fark | Fark CI95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2025_full | 1x | 258/261 | 40 | 22 | +8.71* | 1.77* | +10.79* | [-35.89,+56.61]* |
| 2025_full | 1.5x | 258/261 | 40 | 22 | +8.51* | 1.75* | +12.85* | [-34.02,+58.75]* |
| 2025_full | 2x | 258/261 | 40 | 22 | +6.20* | 1.54* | +20.80* | [-24.95,+65.34]* |
| 2025_new_SepDec | 1x | 87/88 | 40 | 5 | +0.91* | 1.30* | +6.21* | [-26.34,+37.88]* |
| 2025_new_SepDec | 1.5x | 87/88 | 40 | 5 | +0.88* | 1.28* | +6.75* | [-25.86,+38.51]* |
| 2025_new_SepDec | 2x | 87/88 | 40 | 5 | +0.84* | 1.27* | +7.27* | [-25.42,+39.12]* |
| 2026_JanSep_partial | 1x | 192/195 | 15 | 12 | +8.82* | 2.74* | +41.61* | [+7.49,+74.07]* |
| 2026_JanSep_partial | 1.5x | 192/195 | 15 | 12 | +8.74* | 2.71* | +45.90* | [+12.36,+77.84]* |
| 2026_JanSep_partial | 2x | 192/195 | 15 | 12 | +8.67* | 2.68* | +49.87* | [+16.19,+82.03]* |
| all21months | 1x | 450/456 | 40 | 34 | +17.54* | 2.07* | +52.40* | [-5.58,+108.99]* |
| all21months | 1.5x | 450/456 | 40 | 34 | +17.25* | 2.05* | +58.75* | [+0.37,+114.94]* |
| all21months | 2x | 450/456 | 40 | 34 | +14.87* | 1.89* | +70.67* | [+12.83,+126.82]* |

* Tam donem degil: bilinmeyen gunler her iki politikadan da cikarilmis ortak gun alt orneklemi.

Uygun gun sayisi yuksek getiri demek degildir. Filtresiz ORB ile ayni takvim gunlerinde fark ve bootstrap belirsizligi karar icin onemlidir. Tam veri olmayan2026/21aylik toplamlar ileri surulmez.

Asya bar kapsami: 40 uygun, 411 baglam reddi, 5 eksik aralik.

2026-03-16 icin eski karsilastirici native/quote kalitesi nedeniyle zaten bilinmeyendi.2026-04-03te 32 Asya bar bulunmadigi icin yeni filtre sonucu da bilinmeyen kalir. Komisyon2025numeric tarifesi dogrulanmamistir. Short stop halen sanal BID tetik/ASK cikistir.

**Yorum:** Nokta tahmin pozitif olsa da 100+ islem, guven araliginin sifirin ustu, donemler arasi tutarlilik olmadan aday Edge diye adlandirilmaz. Olumsuzsa, tum ORB ailesini degil bu Asya-kontekst varyantini eler.

Siradaki onceden tanimlanan aday M1 kapanis/retest/tepe-dip kirilimidir; bu calisma sonucuna gore kural veya esik secilmeyecektir. Canli emir yok.