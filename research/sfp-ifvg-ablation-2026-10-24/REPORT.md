# SFP: zorunlu iFVG ile mevcut CE alternatifi karşılaştırması

**Bu çalışma tam sistem kâr backtesti değildir.** Önceden kilitlenen tek değişiklik, araştırma kopyasında USE_IFVG_ENTRY=False. Yeni giriş fonksiyonu yazılmadı; mevcut sweep-wick midpoint CE yolu kullanıldı. Breaker, HTF trendi, seans, TP/SL oranları, semboller ve süre aynı. Bayrak giriş geometrisini de etkiler; saf filtre katkısı diye yorumlanamaz.

Ocak–Haziran geliştirme; Temmuz–Kasım tarihsel kontrol. Veriler önceki araştırmalarda görüldü; temiz OOS veya ileri test değil.

| Dönem | Referans sinyal | Varyant sinyal | Referans 60dk yön R | Varyant 60dk yön R | Referans / varyant yön bp |
|---|---:|---:|---:|---:|---:|
| DEVELOPMENT | 6 | 36 | -0.3273 | -0.1128 | -1.4549 / 0.1638 |
| VALIDATION | 2 | 21 | -0.4196 | -0.2194 | 3.0068 / 3.7587 |

60dk yön puanı sinyal kapanışından itibaren fiyat hareketidir; limit dolduğunu varsaymaz ve işlem getirisi değildir. R paydası farklılaşabildiği için bp ve sembol başına ham fiyat hareketi direction_details.json / summary.json içinde ayrıca verildi.

| Dönem | Senaryo | Ölçülen dolum | Dolmayan emir | Belirsiz | Dolum sonrası ortalama 60dk markout R | Stop aşılmış dolum |
|---|---|---:|---:|---:|---:|---:|
| DEVELOPMENT | OBSERVED | 13 | 7 | 16 | 0.0059 | 4 |
| DEVELOPMENT | STRESS_1_5X | 13 | 7 | 16 | -0.0016 | 4 |
| DEVELOPMENT | STRESS_FLOOR | 13 | 7 | 16 | -0.0026 | 4 |
| VALIDATION | OBSERVED | 4 | 4 | 13 | 1.6502 | 1 |
| VALIDATION | STRESS_1_5X | 4 | 4 | 13 | 1.6406 | 1 |
| VALIDATION | STRESS_FLOOR | 4 | 4 | 13 | 1.6009 | 2 |

**Markout, gerçek işlem kârı değildir.** Dolumdan60dk sonraki fiyatı gözler; ilk stopu, TP1/TP2, kısmi kapatmayı, erken çıkışı ve portföy/makro/haber engellerini uygulamaz. Pozitif markout, stop olmuş bir işlemi kazançlı gösteremez; stop aşımı ayrıca sayılır. Eksik kotasyonlar sıfır getiri veya dolmayan emir sayılmadı.

Maliyet: arşivdeki bid/ask spreadi; FX4USD/100k roundtrip ve0.2pip çıkış kayması; altın max(.08USD/ons,2×giriş×.001/100) roundtrip ve.05USD/ons çıkış kayması varsayımları. Stres1.5x; ek spread tabanı FX.5pip / altın.30USD. Komisyon ve kayma tarihsel makbuz değildir.

Karar: NO_FULL_LIFECYCLE_ESCALATION. Sinyal sayısının artması tek başına başarı değildir. Giriş için yeterli ve iki dönemde de tekrarlanan maliyet sonrası kanıt olmadan TP/SL taraması yapılmayacak.

Doğrulama: 57 sinyal yeniden üretildi; 90 prefix/gelecek-mutasyonu kontrolü; 171 senaryo kaydı; 34 kotasyon dosyası hash kontrolü. Referans dosyaları korundu. Üretim koduna, sürece, emirlere müdahale edilmedi.

Ayrıntı: protocol.json, hypothesis_frozen.json, summary.json, decision.json, integrity.json, direction_details.json, signals.json, quote_markouts.json.

## Bulguların yorumu ve somut sonraki iş

iFVG şartını kaldırmak sinyal kıtlığını azalttı: 8 yerine57 sinyal. Referanstaki8 zamanın tamamı korunuyor;49 ek zaman oluşuyor. Bu, strateji edge kanıtı değil.

Geliştirme döneminde13 ölçülebilen dolumun gözlenen maliyetli60dk markoutu ortalama+0.00594R;1.5x maliyetle−0.00155R. Kontrolde4 dolum üç güne ait;1.5x ortalama+1.64063R. Geliştirme ve kontrol bu nedenle tekrarlanan bir avantaj göstermiyor. Bu markoutların beşinde ilk stop seviyesi bir saat dolmadan aşılmış; gerçek çıkış yönetimi olmadan bunlar işlem kârına çevrilemez.

57 adayın17 dolumu ölçülebildi;11 emir dolmadı;29 adayın bid/ask kapsamı veya dolum+60dk sonu eksik. Dolayısıyla tüm örneklem için net kâr hesaplanmadı. Önceden kilitlenen30 dolum/15 gün/pozitif stresCI koşulları geçmedi; bu örneklemde örnek sayısı kapısını daha fazla ayar yaparak aşmak mümkün değil.

Altında yön puanı geliştirmede14 sinyalde+0.4431R, kontrolde8 sinyalde+0.1993R. Bu, deney sonrası görülen araştırma ipucudur; altın seçilip başarılı strateji ilan edilemez. Kotasyonla altın kontrolünde yalnızca bir dolum ölçülebildi ve bu kayıtta stop aşıldı. Forex tarafı aynı yön ölçümünü desteklemedi.

Ek icra denetimi: varyantta24 giriş ve52 stop fiyatı broker fiyat adımına tam oturmuyor. Bu adımlar mevcut2026 broker metadatasından geliyor;2025 emir kabul kaydı değil. Seviyeleri sonuç lehine yuvarlamadık. Nominal limit markoutları broker tarafından kabul edilmiş emir kanıtı sayılamaz.

Sonraki somut geliştirme fiyat-adımı ve emir geometrisini araştırma katmanında deterministik hale getirmek; ardından eksik29 kotasyon aralığını tamamlamak. İkisinin de yeni protokolü olmalı; bu deneyin girişleri/sonuçları değiştirilmeyecek. Altın için görülen yön ipucu ancak kurallar değişmeden ayrı bir dönem ve tam stop/TP yaşam döngüsüyle sınanırsa ilerleyebilir. Yeni eşik veya TP/SL taraması önerilmiyor.

19 birim testi geçti. Kod/gelecek-mutasyonu testleri araştırma uygulamasının doğruluğunu denetler; stratejinin kârını kanıtlamaz.

## Tamamlanan icra düzeltmesi

Fiyat-adımı adaptörü research/execution-grid-2026-10-24 altında araştırma katmanına eklendi.10 birim testi geçti;57 aday için adımlara uyumlu giriş/stop/hedef önerileri üretildi ve minimum1.2R/2R yeniden kontrol edildi. En büyük risk-mesafesi artışı yaklaşık%2.51. Bu öneriler bu deneyin sonuçlarına uygulanmadı; baştan replay henüz yapılmadı. Eski dolum veya kâr bilgisi taşınmadı.
