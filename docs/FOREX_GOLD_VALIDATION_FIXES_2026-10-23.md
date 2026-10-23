# Forex/Altın doğrulama düzeltmeleri — 23 Ekim 2026

**Son durum:** Yeni anahtarla Ocak/Kasım paper yeniden oynatmaları tamamlandı; [sonuç raporu](COMPLETED_BACKTEST_2025_JAN_NOV_2026-10-23.md). Aşağıdaki eksik makro engeli önceki denemeye aittir.

Güncel devam çalışması, yeni kota yanıtı, maliyet stres yolu ve sürüm kaydı: [doğrulama ilerlemesi](VALIDATION_PROGRESS_2026-10-23.md).

Kod ve rapor düzeltildi. Güncel üç paritenin Ocak 2025 yeniden oynatması denendi; gerekli gerçek makro yanıtı eksik olduğundan tam aylık getiri hâlâ hesaplanmış değil. Canlı para için edge doğrulaması tamamlanmadı.

## Yapılanlar

- Eski aday raporunun sabit 342 işlem, +43,56R ve anlamlılık iddiaları kaldırıldı. Rapor artık kaydedilen CSV'yi okuyup Student t testi, güven aralığı, kapanış sırasındaki düşüş ve bootstrap özetini hesaplıyor. CSV SHA256 özeti ekleniyor. Orijinal yayın ve kod bağımsız incelemenin `source_snapshots` klasöründe korunuyor.
- CSV'nin gerçek özeti: **343 işlem, +32,7114R, PF 1,1964, iki taraflı IID p=0,1210**. Bunlar dolum sırası hatalı ayrı aday simülatörünün rakamlarıdır; gerçekleşebilir getiri veya güncel canlı sistem sonucu değildir. Varsayılan maliyet 1.0x; 1.5x etiketi kaldırıldı. Eski M15 simülatörü karşılaştırma için korundu; kendi dolum hatasının giderildiği iddia edilmiyor.
- Makro kararında eksik, bozuk, gelecekte veya **beş saatten eski** zaman damgası yeni girişi engelliyor. Sınır, seans içindeki dört saatlik tazelemeye bir saat hesaplama payıdır; getiriye göre seçilmedi. Saat dilimsiz eski ihracatlar Türkiye saati sayılıyor. Tarihsel yeniden oynatma aynı istemciye tarihsel saat veriyor.
- Ortak `OutcomeTracker` içinde, limit teması görüldükten sonra mum kapanışına bakılarak ücretsiz iptal yazılması giderildi. Stop aynı mumda görülürse -1R ve normal maliyet yazılıyor. Stop görülmeden tepki başarısızsa dolmuş işlem kapanış fiyatından maliyetle kapatılıyor: `ENTRY_REACTION_EXIT_FILLED`. Bu bir **çıkış davranışı düzeltmesidir**. Giriş dedektörü, entry/stop/TP seviyeleri ve parametreler değiştirilmedi.
- Dolum mumundaki hedefler, fiyat sırası bilinmediğinden kâr yazılmıyor. Dolum hassasiyeti bir dakikalık bar olarak kaydediliyor. Tarihsel `ENTRY_REACTION_REJECTED` kayıtları geriye dönük değiştirilmedi; yeni dolmuş işlemler bu ücretsiz etiketi almıyor.
- Yeniden oynatma durursa sebep, kaynak özetleri ve tüketilen makro kararları kaydediliyor; tam ay getirisi üretilmiyor.

## Gerçek veriyle yeniden oynatma

Kapsam, önceki kullanıcı seçimiyle **yalnız Ocak 2025**. Güncel canlı dedektör EURUSD için 11, GBPUSD için 15, XAUUSD için 0 aday verdi. Aday sayısı, işlem sayısı değildir.

`data/full_2025_study/current_three_corrected_20261023/` asıl `BegonyaEngine.scan_symbol`, mevcut giriş filtreleri, haber/risk kapıları, kayıtlı gerçek makro çıktıları ve düzeltilmiş ortak takipçiyi kullandı. Üretim dosyaları ve bildirimler izole edildi. Yeni LLM isteği yapılmadı; yalnız arşiv kullanıldı.

Çalışma **17 Ocak 2025 17:30 UTC** girişinde, **17:00:30 UTC** görüntüsüne ait gerçek stratejist yanıtı eksik olduğundan durdu:

`MISSING_GENUINE_RECORDED_MODEL_RESPONSE role=strategist`

`failure.json` içinde `metrics=null` ve `monthly_return_must_not_be_inferred_from_partial_ledger=true` bulunuyor. İki kapanmış işlemin ara defteri tam ay getirisi değildir. Eksik karara yön veya risk çarpanı uydurulmadı. Kullanılan canlı kaynakların kopyaları kayıtlı SHA256 değerleriyle doğrulanıp çalışmanın `source_snapshots` klasörüne alındı. Sonrasında yalnız takipçinin açıklama metni güncellendi; davranış değişmedi.

Bu paper modelidir: gerçek bid/ask, tick sırası, broker maliyeti ve gecikme doğrulaması tamamlanmadı. Yeni sürümün kârlılığı kanıtlanmış değil.

## Kontroller ve devam

Makro yaşı, tarihsel saat, dolum/stop sırası, maliyetli tepki çıkışı, yeniden oynatma izolasyonu, rapor-defter eşleşmesi, broker saati, araştırma anahtarı izolasyonu ve gözlemci kontrollerinde **54 ayrı test geçti**. Sentetik testler finansal performans kanıtı değildir.

**Çalışan paper süreci yeniden başlatılmadı; kod düzeltmeleri o sürece henüz yüklenmedi.** Gerçek para işlemi başlatılmadı. Eski defter yeni sürümün getirisine dönüştürülmedi.

Raporu API kullanmadan yenilemek: `python scripts/forex_gold_report.py`.

Kota uygun olduğunda, yalnız kullanıcının devam talebiyle mevcut ücretsiz araştırma profili üzerinden yeniden başlatma:

```powershell
python scripts/resume_full_2025_study.py --research-env config/research.env --months 2025-01 --candidate-index data/full_2025_study/candidate_index_current_three
```

Kaynak/girdi değişirse indeks yeniden üretilmeli. Ücretli plana geçilmez; zamanlanmış devam oluşturulmadı. Tam aylık yeniden oynatma ve görülmemiş dönem doğrulaması tamamlanmadan canlıya hazır sonucu çıkarılamaz.
