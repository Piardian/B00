# SFP incelemesi: tamamlanan veri ve sinyal sıklığı çalışması

## Neden az işlem?

Sayım yalnızca EURUSD, GBPUSD ve XAUUSD üzerindeki SFP kolunu kapsar.2025Ocak–Kasım,15dakikalık karar anları, iki seans penceresi. Orijinal zorunlu iFVG modeli8sinyal; iFVG kapalı mevcut CE araştırma varyantı57sinyal üretiyor.

| Aşama | Karar penceresi / aday |
|---|---:|
| Planlı seans taraması | 28.560 |
| Veri mevcut ve HTF yönü uygun | 18.860 |
| Uygun fitil | 9.798 |
| Uygun havuzda süpürme ve seviye içine kapanış | 694 |
| Sweep ucu korunmuş | 429 |
| Kırılım daha önce olmamış | 342 |
| Güncel M15 kapanışında ilk kırılım | 70 |
| Kırılım mumunda yeterli gövde | 63 |
| Breaker ve mevcut CE girişi; iFVG kapalı | 57 |
| Orijinal zorunlu iFVG/CE modeli son kabul | 8 |

Ara aşamalar eşsiz karar pencereleridir;694işlem veya694bağımsız kurulum anlamına gelmez. Aynı sweep birkaç pencerede görülebilir.18.860kararda sayaç eklenmiş fonksiyonun çıktısı eski kayıtla birebir karşılaştırıldı. Hiçbir koşul değiştirilmedi.

En büyük doğal daralma likidite süpürmesinin seyrekliği. Sweep sonrası aynı uç bozulmadan1–3M15mum içinde, sweep/önceki mum bandının ötesinde ilk kapanış şartı ek bir güçlü daralma yaratıyor. Breaker63→57ile küçük eleme; zorunlu iFVG/CE57→8ile güçlü eleme. Mevcut katı SFP kolunda hacim analiz olarak raporlanıyor, ayrıca hacim veto koşulu uygulanmıyor.

Limit girişler de adayların tamamında dolmuyor. Yeni kotasyonlarla iFVG kapalı varyantta38dolum ölçülebiliyor;17emrin süre içinde dolmadığı fiyat kaydından görüldü. İki altın kaydı süre sonu kapanış aralığı nedeniyle ayrı varsayım kategorisinde tutuldu. Canlı makro/haber/aktifpozisyon engelleri burada uygulanmadığı için gerçek operasyonel sayı daha düşük olabilir.

## Veri ve fiyat düzeltmesi sonrası ölçüm

51varlık-gün kotasyon arşivinin tamamı fiyat/saat QA kontrolünü geçti. Önceden çözülen84senaryo kaydı84/84birebir eşleşti. Nominal ve fiyat-adımına uyarlanmış girişler aynı yeni kotasyonlarda baştan oynatıldı.

| Dönem | Fiyat-adımı uyumlu dolum |1.5xmaliyetli ortalama60dk markout |
|---|---:|---:|
| DEVELOPMENT | 26 | -0.124054R |
| VALIDATION | 12 | -0.220214R |

**Bu tablo işlem net kârı değildir.** Markout dolumdan60dk sonraki ilk kotasyondur; stop/TP ve erken çıkış uygulanmaz.38dolumun19unda ilk stop bir saat içinde aşıldı. Tam sistem kârlılığı veya canlı uygunluk iddia edilmedi. Her iki dönemde stresli giriş göstergesi negatif; fiyat yuvarlama düzeltmesi tek başına avantaj oluşturmadı.

İlk strict5s sınırı korunur. Ayrı event-time denetiminde ilk gerçek kotasyon5.078–7.46s geç geldiğinde bu kotasyon kullanıldı; azami60s ve iç boşluk<=60s koşulu korundu. Daha iyi fiyat seçilmedi. Altındaki iki kapanış varsayımı2025takvim sertifikası değildir. [The5ers mevcut resmi saatleri](https://the5ers.com/faqs/market-trading-hours/)2026güncellemesidir; tarihsel tick/M15 kapanışıyla uyumu destekleyici kanıt olarak kullanıldı.

## Çözüm yönü

Bu kol üzerinde daha fazla TP/SL/iFVG eşiği taraması yapılmamalı. Sonraki ölçülebilir soru: M15 yapı teyidi beklenirken fiyatın yön avantajı zaten tüketiliyor mu? Bunu aynı likidite havuzu ve sweep tanımı korunarak ayrı, önceden kilitli zamanlama araştırmasında ölçmek gerekir. Daha çok aday, daha iyi beklenti anlamına gelmez. Üretimde otomatik değişiklik yapılmadı.

Ayrıntılar: FUNNEL.md / funnel.json; REPORT.md / summary.json ilk katı sınır; EVENT_TIME.md / event_summary.json sonraki gerçek kotasyon; completion.json tamamlanma ve sınırlar.7yeni anlamlı test geçti. Ücretli API kullanılmadı.
