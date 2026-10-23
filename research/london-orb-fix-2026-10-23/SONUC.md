# Begonya00 London ORB — uygulama engeli giderildi

**Sonuç: aynı altı parite ve Ocak/Haziran/Kasım 2025 örnekleminde, London dedektörü önceki 0 yerine 102 aday üretiyor. Bunların 36 tanesi bilginin kullanılabilir olduğu UTC12:00 öncesinde. Bu sonuç kârlılık veya edge kanıtı değildir.**

## Uygulanan değişiklikler

- London açılışı Europe/London yerel08:00, seans bitişi yerel16:30 olarak tanımlandı. IANA yaz/kış dönüşümü kullanılır. Diğer seansların aralık/seans tanımları değiştirilmedi.
- London ilk15dakika aralığı `[açılış, açılış+15dk)` oldu. 07:15/08:15 açılışlı sonraki mum artık aralığın içinde değil; kapanırsa ilk kırılma mumu olabilir. Açık mumlar hesaplamadan çıkarılır.
- Asya00:00–06:00UTC aralığı, önceki tamamlanmış UTC günlerinin14 günlük ortalama true range değeriyle karşılaştırılır. Mevcut %70 eşiği korundu. Gün içindeki London mumları normalizasyona giremez.
- Önceki tekM15mum boyundan günlükATR normalizasyonuna geçmek **yeni ve açık bir strateji varsayımıdır**. Sonuç görüldükten sonra dönem veya eşik taraması yapılmadı. Sinyal üretmesi bu varsayımın kârlı olduğunu göstermez.
- Günlük değerler H1 geçmişinden türetilir. En az20H1 gözlemi olan tamamlanmış UTC günleri kullanılır; thin Sunday/tatil parçaları elenir. Son14TR için15 geçerli gün gerekir. Eksik veya eski tarihçe/eksikAsya mumları girişi onaylamaz. Bu kapsam kuralı broker takviminin veya eksiksiz tick verisinin sertifikası değildir.
- London için minimum2x hacim gerçek veto oldu;1.8x artık A+ üretmez.
- Üst motor ve aday indeksleyici mevcutH1 geçmişini ve tarihsel saatini dedektöre iletir. Yeni bağlam modülü kaynak hashlerine eklendi; eski aday indeksleri sessizce kullanılamaz.
- Her London adayında açılış/aralık bitişi, günlükATR, Asya aralığı ve oranı denetim alanı olarak saklanır.

## Aday üretimi

| Parite | Önceki London çıktısı | Yeni London çıktısı | Yeni UTC12:00 öncesi |
|---|---:|---:|---:|
| EUR/USD | 0 | 23 | 14 |
| GBP/USD | 0 | 22 | 11 |
| NZD/USD | 0 | 16 | 3 |
| USD/CAD | 0 | 17 | 3 |
| USD/CHF | 0 | 13 | 4 |
| USD/JPY | 0 | 11 | 1 |

102 aday, 88 farklı parite-güne dağılmıştır; tekrar kırılmaları bağımsız işlem sayılmaz. Mevcut üst motorun saat kapısı 91 adayın saatinde açıktır. Sabah dışındaki adaylar London seansının sonraki saatlerine aittir;102adayın tamamına 'London açılışında işlem' denemez. Makro/HTF/haber/risk ve SFP önceliği uygulanmış tam motor işlem sayısı bu değildir.

Bütün paritelerde incelenen63er günde günlükATR girdisi hazırdı. Önceki ve yeni tanımlarda aralık/saat değiştiği için ham kırılma kümeleri aynı değildir; sıfırdan102ye artışı yalnız Asya filtresine bağlamak doğru olmaz. Geçmiş üç ay görülmemiş OOS değildir.

## Testler ve işletim durumu

44 test geçti: yeni London saat/aralık, long/short kırılma, H1true-range ve gap, gelecekteki fiyatın geçmişATRyi değiştirmemesi, eksik tarihçenin veto olması, açık mumun kullanılmaması, hacim alt sınırı ve mevcut canlı giriş/takip/replay testleri. Sonuçlardan sonra protokoldeki kod/veri hashleri doğrulandı.

Kaynak kod değişiklikleri hazırdır. Çalışan süreç yeniden başlatılmadı, gerçek veya paper emir açılmadı, bildirim gönderilmedi. Yeni varsayımla canlı başarı iddiası yoktur. Normal bir sonraki başlangıç güncellenmiş kaynakları yükler. Önce ayrı araştırma çıktısında tam maliyetli dolum/takip testi yapılmalıdır; eski makro/aday dosyaları yeni kurallar için onay sayılmaz.

Asıl entry, stop, TP1/TP2 ve OutcomeTracker yaşam döngüsü değiştirilmedi. Kullanıcının ayrıca belirttiği M1 tepe/dip teyidi eklenmiş gibi sunulmadı; bu değişiklik London dedektörünün sinyal engelini giderir.

## Dosyalar

Kaynak: sfp_orb_engine/orb_session_context.py, orb_detector.py, config.py ve engine.py. Entegrasyon: scripts/prepass_2025_candidates.py, replay_live_system.py. Test: tests/test_london_orb_context.py.

Bu klasörde before/ değişiklik öncesi ilgili kaynakları korur; protocol_frozen.json sonuç öncesi kod/veri/parametreleri, funnel.csv ve candidates.json sonuçları saklar. Önceki denetim london-orb-audit-2026-10-23/SONUC.md altında korunur. Başka oturumlardan kalan çalışma ağacı değişiklikleri geri alınmadı.
