# Canlı işlem korumaları — 22 Ekim 2026

## Uygulanan davranış

- SFP için son üç mumda süpürme, ardından ilk yapı kırılımı, breaker ve iFVG teyidi gerekiyor. iFVG bulunmayınca fitil girişine geçilmiyor. Yeni strateji adı `SFP_IFVG_BREAKER`.
- Trend, kapanmış gerçek UTC 4H mumlarından EMA50/200 ile hesaplanıyor; 200 tamamlanmış 4H mum olmadan yeni giriş yok. Canlı ve custom backtest aynı trend hesabını ve yapı/iFVG teyit yardımcısını kullanıyor. Backtest ısınma verisi 65 güne çıkarıldı.
- Makro kapı eksik, bozuk veya nötrse yeni giriş yok. Adayın gerçek fiyatlarından TP1 minimum 1R ve TP2 minimum 3R kontrol ediliyor. Etikette yazan RR yeterli değil.
- Gerçekleşmiş günlük net sonuç −3R veya altında olduğunda ya da aynı TRT gününde art arda üç stop olduğunda yeni emir engelleniyor. Bekleyen emirler de dolum öncesi bu kontrolü tekrar yapıyor. Bu sınırlar açık pozisyonları zorla kapatmaz; mevcut açık risk nedeniyle eşik aşılabilir.
- Bekleyen emirler dahil toplam risk üst sınırı 3R; aynı para birimini paylaşan işlemlerde sınır 2R. Risk çarpanı pozisyona kaydediliyor. Eski kayıtlar için çarpan 1 varsayılarak muhafazakâr kontrol yapılıyor. Günlük zarar freni ağırlıklandırılmamış R kullanıyor.
- Pozisyon takibi, haber/seans/yeni giriş filtrelerinden önce çalışıyor. Yalnızca kapanmış 1m mumlar, zaman sırasıyla ve bir kez işleniyor. Eksik mum varsa boşluk kaydedilip veri tamamlanana kadar ilerlenmiyor; bu sırada yeni portföy riski alınmıyor.
- Tepkisiz geçiş ve teyit öncesi stop ihlali bekleyen emri sıfır sonuçla iptal ediyor. Tepki teyitli paper dolumu mum kapanışında aktifleşiyor; aynı mumun eski fitilleriyle sonradan TP/SL yazılmıyor. Sonraki mumlarda hem stop hem hedef görülürse muhafazakâr olarak önceden yürürlükte olan stop önce kabul ediliyor. Yeni BE/trailing stop sonraki mumdan geçerli.
- Limit zaman aşımı ayardaki `LIMIT_EXPIRY_BARS` ile uyumlu: varsayılan 32 × 15 dakika, yani 8 saat.
- Yeni kapanışlara `weighted_net_r` ekleniyor. Eski ledger tutarları yeniden yazılmıyor. Dolmayan ve iptal edilen emirler işlem başarı oranına dahil edilmiyor.

## Doğrulama ve sınırlar

`python -m pytest tests -q --basetemp=<yeni test klasörü>`: 18 test geçti. İki yönde gerçek sentetik iFVG kurulumu, eksik iFVG, nötr makro, gerçek hedef mesafesi, kapanmış 4H veri, tekrar işleme, eksik veri ve yeniden başlatma, aynı mumda dolum/çıkış, belirsiz TP/SL sırası, haber sırasında takip, günlük zarar ve ortak para birimi riski kapsandı.

Ek olarak makro motorunun giriş mekaniği ve kapı testleri çalıştırıldı: 22 geçti, 1 eski test başarısız. `test_calculate_ce_entry_short_fvg` 1.1020 bekliyor; mevcut yakınlık filtresi 1.1015 fitil girişine dönüyor. Aynı çağrı değiştirilmemiş `git show HEAD:sfp_orb_engine/entry_mechanics.py` üzerinde de 1.1015 üretiyor. Bu dosya ve test değiştirilmedi.

EUR/USD ve XAU/USD üzerinde sağlayıcının 1m/15m/1h veri döndürdüğü ve gerçek 4H hesabının sonuç ürettiği ayrıca doğrulandı. Veri bayatsa yeni emir açılmıyor.

Bu değişiklikler kârlılık veya tam canlı/backtest sonuç eşitliği kanıtı değildir. Eski raporlar yeniden üretilmedi. Custom backtestin geçmiş makro tablosu, bar çözünürlüğü ve portföy/çıkış modeli canlı paper takipçisiyle tamamen aynı değildir; eski performans rakamları yeni sürümün doğrulaması olarak kullanılamaz. Broker dolumu modellenmiyor; tepki teyitli limit dolumu paper modelidir. Veri boşluğu kendiliğinden doldurulamıyorsa takip bekler ve `tracking_gap_at` alanı ile uyarı kaydı bırakır.

İşletim sınırları `sfp_orb_engine/config.py` içinde; bu haftaya göre optimize edilmedi. Açık işlem bulunmadığı kontrol edildikten sonra yalnızca SFP/ORB alt süreci yeniden başlatılarak sürüm etkinleştirilir. Makro motoru ve geçmiş sonuç dosyaları bu geçişte değiştirilmez.

## Etkinleştirme kaydı

22 Ekim 2026, 16:13 TRT: açık işlem listesi boşken eski SFP/ORB alt süreci durduruldu; mevcut supervisor yeni süreci başlattı. `EXECUTION_POLICY_ACTIVE` telemetri kaydı `confirmed-v2`, PID 42408, 1m kapanış takibi ve tüm dört risk sınırını doğruladı. Runtime kilidi aynı PID ile güncellendi. Ardından GBP/USD için nötr 4H trendin `HTF_NOT_READY` kaydıyla engellendiği görüldü.
