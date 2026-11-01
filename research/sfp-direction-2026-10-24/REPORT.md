# Begonya00 — mevcut SFP giriş mekanizması

Bu çalışma tam sistem backtesti değildir. Gerçek SFP tespit ve giriş seviyeleri korunur; makro/haber/portföy ve çıkış yönetimi uygulanmaz. 60 dakikalık yön puanı ve koşullu dolum sonrası markout, işlem kârı değildir.

Ocak–Haziran geliştirme; Temmuz–Kasım ayrı tarihsel kontrol. Veriler başka çalışmalarda görülmüştür; temiz OOS veya ileri test değildir.

| Dönem | Geçerli sinyal | 60dk yön ortalaması (R) | Pozitif yön | Gözlenen kotasyonla ölçülebilen dolum |
|---|---:|---:|---:|---:|
| DEVELOPMENT | 6 | -0.3273155650635083 | 3/6 | 2 |
| VALIDATION | 2 | -0.41962886552064005 | 1/2 | 1 |

Fiyat yön puanı sinyal kapanışından başlar; limitin dolduğunu varsaymaz. Kotasyon markoutu, limit dolumundan 60dk sonrasını ölçer ve stop aşılmasına izin verir; bu nedenle kazanç gibi kullanılamaz.

Eksik kotasyonlar sıfır getiri veya dolmayan emir sayılmaz. Kapsam, dolanlarda dolum+60dk; dolmayanlarda 4 saatlik limit süresinin sonuna kadar gerekir. Bu kapsam düzeltmesi kotasyon sonuçlarına bakılmadan protocol_initial.json üzerine kaydedilmiştir. Tarihsel spread gözlenir; komisyon ve kayma varsayımdır. Altın ve FX maliyetleri ayrıdır.

Sinyal zamanı girdileri yalnızca tamamlanmış barlardır. Üst zaman dilimi mevcut kodun son1000 H1, 4H EMA50/200 yöntemidir. Altında ek dönem H1 barları mevcut M15 arşivinden türetilmiştir; örtüşme kontrolü price_audit.json içindedir.

Karar: Giriş edge’i kanıtlanmadı. Eksik kapsam/az örnek ve negatif bulgular summary.json içinde ayrı gösterilir; bu karar tüm SFP olasılıklarının reddi değildir.

ORB kolunda yeni süre/TP/SL taraması yapılmadı. Üretim koduna, çalışan sürece ve emirlere müdahale edilmedi.

Ayrıntı: summary.json, signals.json, rejections.json, coverage.json, price_audit.json, quote_markouts.json ve protocol.json.

## Sinyal sayısını daraltan koşullar

Toplam 28560 planlı tarama penceresi: 160 pencerede tamamlanmış karar mumu yok; 9540 pencerede HTF nötr/hazır değil; 18860 pencere gerçek SFP dedektörüne girdi.

Eksik160 pencere: üç varlıkta1Ocak, altında18Nisan. Bunlar hafta içi seans takvimi ile broker kapanışı arasındaki farktır; sıfır getirili işlem olarak sayılmadı. Diğer planlı karar mumları mevcut.

Yapı teyidine ulaşan 70 iç kontrol denemesinin 63 tanesinde breaker, 13 tanesinde iFVG, 10 tanesinde ikisi birlikte var. Bunlar farklı havuzları aynı mumda kontrol edebilen denemelerdir; benzersiz işlem adedi değildir. iFVG sinyal sıklığı açısından belirgin dar boğaz; kaldırılması kârlılığı artırır sonucu çıkmaz.

10 ortak teyidin ikisi mevcut CE giriş kaynağı kontrolünü geçmedi; sekiz sinyal kaldı. Mevcut katı SFP yolunda hacim analizi çıktıya ekleniyor, ayrıca hacim veto şartı uygulanmıyor. Dolayısıyla önceki farklı hacim stratejisi raporları bu kolu kanıtlamaz.

## Ölçümün pratik sonucu ve geliştirme

1. Mevcut SFP için iki dönemde de pozitif bir saatlik sinyal-yön ortalaması bulunmadı. Sekiz örnek stratejiyi kesin reddetmeye de kanıtlamaya da yetmez.
2. Kotasyonla üç dolumun60dk markoutu ölçülebildi; bir emir dört saatte dolmadı; dört sinyalin yeterli bid/ask arşivi yok. Pozitif altküme tüm sisteme genellenmedi. Bu aşamada TP/SL ayarı aramak için dayanak yok.
3. Sonraki tek hipotez next_hypothesis_predeclared.json içinde kilitlendi: iFVG zorunluluğunun katkısını mevcut kodun kendi sweep-wick CE alternatifiyle karşılaştırmak. Bu yeni araştırma varyantıdır; henüz çalıştırılmadı. Bayrak hem teyidi hem giriş geometrisini etkilediğinden saf filtre testi diye sunulmayacak.

## Doğrulama

13 anlamlı birim testi geçti. Sekiz sinyal aynen yeniden üretildi; 41 prefix/gelecek-mutasyonu kontrolü geçti. 24 kotasyon senaryo kaydının muhasebesi ve kullanılan dört kotasyon dosyasının hashleri doğrulandı. Altında türetilen H1 barları örtüşen4614 doğal H1 barının OHLC değerleriyle birebir eşleşti.

protocol_initial.json ve study_initial.py, kotasyon sonucu görülmeden yapılan terminal-kapsam düzeltmesinin öncesini korur. integrity.json doğrulamayı; bottlenecks.json sayımları; next_hypothesis_predeclared.json sonraki deneyin sınırlarını içerir.
