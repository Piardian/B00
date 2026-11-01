# Neden az sinyal üretiyor?

Üç varlık,15dakikalık karar anları, hafta içi07–11:59 ve13–17:59UTC. 28.560planlı varlık-zaman penceresinin160ında karar mumu yok (1Ocak ve altın18Nisan kapanışları);9.540ında4H trendi nötr/hazır değil. Kalan18.860pencereye gerçek dedektör uygulanıyor.

| Koşuldan geçen eşsiz karar penceresi | Sayı |
|---|---:|
| HTF uyumlu tarama | 18860 |
| En azbir uygun fitil | 9798 |
| İzinli likidite havuzu mevcut | 9798 |
| Havuz seansı uygun | 9692 |
| Seviye süpürülüp içinde kapanış | 694 |
| Sweep ucu bozulmamış | 429 |
| Kırılım daha önce gerçekleşmemiş | 342 |
| Güncel kapanışla kırılım | 70 |
| Kırılım mumunda gövde en az%35 | 63 |
| Breaker yapı teyidi | 57 |
| Mevcut CE giriş kaynağı kabul | 57 |
| Orijinal zorunlu iFVG modeliyle son kabul | 8 |

Bu tablo işlem sayısı değildir. Aynı pencerede farklı havuz/sweep yolları denenebilir; her aşamada pencere en fazla bir kez sayılır. Koşulların bağımsız etkisi veya elenenlerin kârlılığı bu sayılardan çıkarılamaz.

15dakikalık mum kapanışı gerekir; süpürme önceki1–3mumda olmalı; fitil en az%45, eskiuç bozulmamış, ilk yapı kırılımı ve en az%35gövde gerekir. Üst trend uyumu ve breaker eklenir. Orijinal model ayrıca iFVG ve uygun CE kaynağı ister. Ardından limitin gerçekten dolması gerekir. Az işlem, bu koşulların birlikte nadir oluşmasının sonucudur; filtreleri azaltmak kârı garanti etmez.

AST yalnızca sayaç çağrıları ekledi; hiçbir koşul değiştirilmedi.18.860kararın tamamında çıktı orijinal kayıtla karşılaştırıldı;57sinyal birebir eşleşti. Canlı makro/haber/aktifpozisyon engelleri eklenirse sayı daha da azalabilir; bu engeller bu tabloda uygulanmadı.
