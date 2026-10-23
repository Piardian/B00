# Doğrulama çalışması — 23 Ekim 2026

**Sonraki güncelleme:** Yeni araştırma projesinin anahtarıyla makro engeli aşıldı. Ocak ve Kasım 2025 için üçer paper maliyet senaryosu ay sonuna kadar tamamlandı. [Tamamlanan sonuçlar ve sınırlamalar](COMPLETED_BACKTEST_2025_JAN_NOV_2026-10-23.md). Aşağıdaki kota/eksik karar kayıtları önceki denemeyi anlatır.

Kullanıcının devam talebiyle eksik gerçek makro işi yeniden çalıştırıldı; yalnız ayrı ücretsiz araştırma anahtarı kullanıldı. İlk stratejist modeli HTTP 503, sonraki model **günlük ücretsiz kota için HTTP 429** verdi. İlk günlük kota hatasında duruldu; aynı kota için model döngüsü ve tekrarlar sürdürülmedi. Ücretli plan açılmadı.

Gerçek sağlayıcı yanıtı `data/full_2025_study/research_provider_attempts.jsonl` içinde: `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, limit 20, `retryDelay=25529s`. Yeni isteğe göre tahmini tekrar zamanı **23 Ekim 2026 10:00 Türkiye saati**. Bu saat başarı garantisi değildir. Son deneme özeti: `latest_genuine_macro_retry.json`.

## Tamamlanan yerel işler

- İcra sürümü `passive-limit-v3` olarak ayrıldı. Eski tepki teyitli defterle düzeltilmiş limit/zarar muhasebesi aynı sürüm diye raporlanmayacak. Giriş dedektörleri ve entry/TP/SL parametreleri değiştirilmedi.
- Ocak ve Kasım 2025 için asıl dedektörler yeniden çalıştırıldı. EURUSD: Ocak 11, Kasım 12 aday; GBPUSD: Ocak 15, Kasım 17 aday; altın: her iki ayda 0 aday. Bunlar işlem veya getiri sayıları değildir.
- Kasım 2025 asıl motor yeniden oynatması **6 Kasım 08:45 UTC** adayında, **07:30 UTC** makro görüntüsüne ait gerçek analist yanıtı eksik olduğundan durdu. `november_validation_20261023/failure.json` içinde `metrics=null`. Ocak engeli 17 Ocak 17:30 UTC'deki gerçek stratejist yanıtıdır. Hiçbir eksik karar yerine yön/risk değeri üretilmedi.
- Üç paritenin dokuz M1/M15/H1 dosyası denetlendi: yinelenen zaman damgası ve boş OHLC hücresi yok. Bu kontrol piyasanın açık olduğu bütün dakikaların mevcut olduğuna dair belge değildir; bar devamlılığı ayrıca değerlendirilmeli.
- Paylaşılan paper takipçisinde 1.0x, 1.5x ve 2.0x maliyet stresi araştırma yoluna eklendi. Çarpan hem spread eşiğine hem sabit R giderine uygulanır; dolum ve çıkışlar aynı asıl motorla yeniden hesaplanır. Yalnız eski net kârdan gider çıkarmakla yetinilmez. Bu stres modelinin gerçek broker maliyeti olduğu iddia edilmez.
- Kota durdurma/redaksiyon, geçmiş saat, dolum/stop sırası, maliyetli tepki çıkışı, üç maliyet çarpanında motor izolasyonu ve mevcut veri/kimlik kontrollerinde **66 test geçti**. Bunlar kârlılık kanıtı değildir.

Üç maliyet senaryosu Ocak gerçek fiyatları üzerinde de ayrı ayrı çalıştırıldı: `cost_validation_20261023_1`, `_1_5`, `_2`. Üçü de 17 Ocak'taki eksik stratejist yanıtında durdu; üçünün de tam aylık metriği `null`.

Yalnız tamamlanan ara işlemlerin mekanik kontrolü:

| Paper maliyet çarpanı | İlk işlem net R / kapanış | İkinci işlem net R / kapanış |
|---|---|---|
| 1.0x | -0,613333 / tepki sonrası çıkış | -0,35 / tepki sonrası çıkış |
| 1.5x | -0,653333 / tepki sonrası çıkış | -1,12 / stop |
| 2.0x | -1,093333 / tepki sonrası çıkış | -1,16 / stop |

Spread eşiği dolum zamanını değiştirdiği için kapanış davranışı da değişti. Bu tablo stres yolunun gerçek motorla yeniden çalıştığını gösterir; iki işlemden stratejinin beklenen getirisi veya tam aylık zarar/kâr sonucu çıkarılamaz.

## Gerçek maliyet konusunda bulunan eksik

Paper takipçisi hâlâ sabit **0,08R gider** ve fiyat oranı üzerinden spread eşiği kullanıyor. Kanonik M1 dosyalarında bid/ask veya gerçek spread sütunu yok. Hesaba ve tarihe ait komisyon, swap ve gerçekleşmiş kayma doğrulanmış değil.

[The5ers'ın güncel resmi açıklaması](https://the5ers.com/faqs/what-are-the-spreads-and-commissions/) 22 Temmuz 2026 güncellemesiyle Forex için 4 dolar/lot gidiş-dönüş, metaller için yüzde esaslı komisyon belirtiyor. Eski adayın 6 dolar/lot ve altın için 0,06 fiyat mesafesi varsayımı bununla aynı değildir. Güncel web tarifesi 2025 hesabının tarihsel tarifesi yerine geçirilmedi. Dolayısıyla “gerçek broker maliyetleriyle doğrulandı” sonucu çıkarılamaz.

## Görülmemiş dönem

Eski aday Aralık 2024–Ekim 2026 aralığında varlık seçimine dayanak oldu; **Kasım 2025 dokunulmamış örneklem dışı veri değildir**. Onu ek geriye dönük kontrol olarak kullanıyoruz.

36 kaynak dosyası, araştırma kuralları ve veri özetleri `data/full_2025_study/validation_protocol_20261023_final/protocol.json` içinde kaydedildi; kaynak kopyaları alındı ve 36 SHA256 eşleşmesi doğrulandı. Önceki hazırlık kaydı korundu; geçerli son kayıt `_final` klasöründedir.

Gerçekten ileriye dönük ilk tam ay **Kasım 2026** olarak sonuç görülmeden belirlendi. Kaynak/politika değişirse karşılaştırma geçersiz olur ve yeni dönem kaydı gerekir. Bir ay veya az sayıda işlem tek başına kalıcı edge kanıtlamaz. Gelecek fiyatlar bugün mevcut olmadığı için bu test bugün tamamlanamaz.

## Çalıştırma ve mevcut sınır

Güncel indeks: `data/full_2025_study/candidate_index_validation_20261023`. Kota uygun olduğunda, kullanıcının manuel devam talebiyle:

```powershell
python scripts/resume_full_2025_study.py --research-env config/research.env --months 2025-01 --candidate-index data/full_2025_study/candidate_index_validation_20261023
```

Araştırma stres senaryoları için aynı komuta `--cost-multiplier 1.5` veya `--cost-multiplier 2` eklenebilir. Sonuçlar farklı klasörlere kaydedilir; tam ay bitmeden aylık getiri yayımlanmaz.

Çalışan paper süreç yeniden başlatılmadı. Gerçek para emri ve otomatik/zamanlanmış devam başlatılmadı. **Tam aylık backtest, gerçek maliyet doğrulaması ve kalıcı edge kanıtı henüz tamamlanmış değil.**
