# London XAUUSD ORB: Asya araligi baglami

**Hipotez:** London 08:00–08:15 M15 kapanisi, ayni yonde 00:00–08:00 Asya araligini terk etmisse ORB islemine izin ver.

Tam32 ardışık Asya M15 barı istenir. Kapanış long için aralık tepesinin üstünde, short için dibinin altında olmalıdır. Eşitlik ve aralık içinde kapanış reddedilir. Giriş, stop, 2R, 16:00 EOD, komisyon, spread ve slippage aynı dondurulmuş motorla ölçüldü. Yaz ve maliyet filtreleri eklenmedi.

Sonuçlar tarihsel keşif ölçümüdür. Bu kural eski geniş araştırmalarda geçmiş tarihlere uygulanmamış olabilir; bu nedenle tüm veri kümesiyle mutlak OOS/ileri test iddiası yok.

| Dönem | Maliyet | Klasik işlem / netR | Asya işlem / netR / PF | Asya filtresinin farkı [95% CI] | Kapsama |
|---|---:|---:|---:|---:|---|
| 2025_full | 1x | 229 / -2.08R | 22 / +8.71R / 1.77 | +10.79R [-35.47,+55.27] | tam |
| 2025_full | 1.5x | 229 / -4.34R | 22 / +8.51R / 1.75 | +12.85R [-33.56,+57.37] | tam |
| 2025_full | 2x | 229 / -14.60R | 22 / +6.20R / 1.54 | +20.80R [-25.25,+64.22] | tam |
| 2025_new_SepDec | 1x | 78 / -5.30R | 5 / +0.91R / 1.30 | +6.21R [-26.34,+37.36] | tam |
| 2025_new_SepDec | 1.5x | 78 / -5.87R | 5 / +0.88R / 1.28 | +6.75R [-25.84,+37.98] | tam |
| 2025_new_SepDec | 2x | 78 / -6.43R | 5 / +0.84R / 1.27 | +7.27R [-25.40,+38.59] | tam |
| 2026_JanSep_partial | 1x | 178 / -32.78R | 12 / +8.82R / 2.74 | +41.61R [+6.92,+74.28] | ortak gun 193/195; bilinmeyen 2026-03-16, 2026-04-03 |
| 2026_JanSep_partial | 1.5x | 178 / -37.15R | 12 / +8.74R / 2.71 | +45.90R [+11.53,+77.79] | ortak gun 193/195; bilinmeyen 2026-03-16, 2026-04-03 |
| 2026_JanSep_partial | 2x | 178 / -41.20R | 12 / +8.67R / 2.68 | +49.87R [+15.46,+82.07] | ortak gun 193/195; bilinmeyen 2026-03-16, 2026-04-03 |
| all21months | 1x | 407 / -34.86R | 34 / +17.54R / 2.07 | +52.40R [-5.04,+107.92] | ortak gun 454/456; bilinmeyen 2026-03-16, 2026-04-03 |
| all21months | 1.5x | 407 / -41.49R | 34 / +17.25R / 2.05 | +58.75R [+0.91,+114.12] | ortak gun 454/456; bilinmeyen 2026-03-16, 2026-04-03 |
| all21months | 2x | 407 / -55.79R | 34 / +14.87R / 1.89 | +70.67R [+12.99,+125.13] | ortak gun 454/456; bilinmeyen 2026-03-16, 2026-04-03 |

### Ne gösteriyor?

2025 tam yılda Asya filtresi 22 işlemde 1.5x net +8.51R verdi; klasik ORB aynı yıl 229 işlemde -4.34R idi. Ancak eşleştirilmiş farkın %95 aralığı sıfırı kapsıyor ve 22 işlem edge kanıtı için az.
2025 Eylül–Aralık ayrı dönemi 5 işlemde sadece +0.88R verdi.2026 Ocak–Eylül filtresi bilinmeyen iki kış günü çıkarılmış 193 takvim gününde 12 işlem/+8.74R; işlem bazlı blok CI -2.11R ile +20.68R. Eşleştirilmiş fark +45.90R, CI +12.36R ile +77.79R; bu adayın filtresiz ORB günlerinde kayıpları önlediğini düşündüren olumlu fakat küçük örneklemli işarettir.
2025 ve 2026 birlikte 34 işlem ve +17.25R gösteriyor. 2025’in en iyi beş işlemi çıkarılınca +8.51R, -1.38R’ye; 2026’da +8.74R, -1.18R’ye düşüyor. Birleştirilmiş eşleştirilmiş farkın aralığı sıfırın hemen üstünden başlıyor; sonuç az sayıda işleme, birden çok denenmiş fikre ve daha önce görülmüş tarihsel veriye duyarlı. Bu yüzden “edge doğrulandı” demiyorum. Asya aralığı geniş günleri seçiyor; iyileşmenin hangi piyasa mekanizmasından geldiği ayrı kanıtlanmadı.

### Veri ve karar

Dört tam piyasa kapanışı (2025-01-01, 2025-04-18, 2025-12-25, 2026-01-01) için orijinal üç senaryonun hepsi zaten CONFIRMED_HOLIDAY_CLOSED diyordu. Bunları Asya barı yok diye bilinmeyen saymak yerine aynı kapanış etiketiyle taşıdım; hiçbir PnL eklenmedi/değişmedi.2026-04-03te yalnız8Asya barı var ve 2026-03-16da native açılış/quote denetimi başarısız; bu iki günü sıfırlamadım. 2026 ve 21ay toplam/PF/CI iddiası yok.

**Karar: Asya bağlamı şu ana kadarki en güçlü test adayıdır, doğrulanmış edge değildir.** Öncelik bunu yeni ve el değmemiş bir dönemde aynen test etmek. M1 kapanış/retest/tepe-dip hipotezini sonradan ekleyip bu sonucu kurtarmaya çalışmamak. En az100 işlem ve yeni dönemde pozitif sonuç görmeden terfi yok. Canlı emir gönderilmedi.
