# Gerçek sonraki kotasyonla zamanlayıcı denetimi

Ayrı duyarlılık çalışması: ilk katı5s sınırı ve sonuçları değişmedi.60dk markout emri zamanlayıcıdan sonraki İLK gerçek kotasyonda ölçüldü; azami60s ve tüm iç kotasyon boşlukları<=60s koşulu korundu. Bu örneklemde ek gecikmeler yalnızca5.078–7.46s; daha iyi fiyat aranmadı.

| Dönem | Model | Senaryo | Dolum | Kanıtlı dolmama | Kapalı seans varsayımı | Belirsiz | Ortalama maliyetli markout R |
|---|---|---|---:|---:|---:|---:|---:|
| DEVELOPMENT | NOMINAL | OBSERVED | 26 | 9 | 1 | 0 | -0.102474 |
| DEVELOPMENT | NOMINAL | STRESS_1_5X | 26 | 9 | 1 | 0 | -0.125023 |
| DEVELOPMENT | NOMINAL | STRESS_FLOOR | 26 | 9 | 1 | 0 | -0.142659 |
| DEVELOPMENT | ALIGNED | OBSERVED | 26 | 9 | 1 | 0 | -0.101725 |
| DEVELOPMENT | ALIGNED | STRESS_1_5X | 26 | 9 | 1 | 0 | -0.124054 |
| DEVELOPMENT | ALIGNED | STRESS_FLOOR | 26 | 9 | 1 | 0 | -0.144825 |
| VALIDATION | NOMINAL | OBSERVED | 12 | 8 | 1 | 0 | -0.209146 |
| VALIDATION | NOMINAL | STRESS_1_5X | 12 | 8 | 1 | 0 | -0.238253 |
| VALIDATION | NOMINAL | STRESS_FLOOR | 12 | 8 | 1 | 0 | -0.244303 |
| VALIDATION | ALIGNED | OBSERVED | 12 | 8 | 1 | 0 | -0.189680 |
| VALIDATION | ALIGNED | STRESS_1_5X | 12 | 8 | 1 | 0 | -0.220214 |
| VALIDATION | ALIGNED | STRESS_FLOOR | 12 | 8 | 1 | 0 | -0.227986 |

Altındaki iki dolmamış emrin süre sonu kapanış aralığına denk geliyor. Mevcut resmi saatler01:05–23:50broker saati; tarihsel tick sonu23:49:57/23:49:59 ve nativeM15 boşluğu bunu destekliyor.2025 seans takvimi arşivlenmiş değildir; bu yüzden bu iki kayıt ayrı varsayım kategorisinde kaldı ve gerçek broker emri kabulü/iptali iddia edilmedi.

[The5ers resmi saatleri,10Haziran2026 güncellemesi](https://the5ers.com/faqs/market-trading-hours/).2026 belgesi2025 için bağımsız tarihsel sertifika değildir.

Markout işlem kârı değildir: stop/TP/erken çıkış uygulanmadı. Kapalı-seans varsayımına ve zaman toleransına rağmen edge kanıtlanmış sayılmaz; ilk strict rapor ve tüm eski dosyalar korunur.
