# Pasif işlem kalitesi ölçümü

Giriş, limit dolumu, stop, hedef, trailing, risk sınırı ve seans kuralları değiştirilmedi. Amaç yeni bir strateji denemek değil, iyileştirme önerileri için veri toplamaktır.

## İlk durum ölçümü

19–22 Ekim 2026 TRT kapanışlarına ait 19 gerçekleşmiş işlem incelendi. Tamamı `legacy` kayıt; yeni korumalı sürümün performansı olarak yorumlanamaz.

- Model spread tamponunun başlangıç stop mesafesine oranı medyan **0,273R**, en yüksek **0,510R**.
- Bunlar gerçek broker spreadi/slipajı değildir. Tampon yalnızca kodun fiyat eşiği varsayımıdır; kaydedilmiş net R'ye ek bir gerçekleşmiş gider gibi tekrar eklenmez.
- <=0,15R grubunda 2 işlem / 0 stop / +2,85R; 0,15–0,30R grubunda 10 işlem / 9 stop / −8,61R; >0,30R grubunda 7 işlem / 5 stop / −3,39R var. Az sayıda örnek ve farklı enstrümanlar nedeniyle buradan yeni eleme eşiği çıkarılmadı.
- Eski kayıtların tamamında güvenilir eksiksiz 1m fiyat yolu olmadığı için MAE/MFE veya stop/trailing sonrası hedefe dönüş oranı hesaplanmadı. Bilinmeyen sonuçlar `null` bırakıldı.

Detaylar `data/execution_quality_baseline_20261022.json` ve aynı adlı `.md` dosyasında.

## İleriye dönük kayıt

`ExecutionObserver`, `data/execution_observations.sqlite3` dosyasına şunları yazar:

- Motorun gerçekten okuduğu kapanmış 1m, 15m ve 1h OHLCV mumları; ilk görülme zamanı ve sonradan gelen farklı sürümler korunur. Üst sağlayıcı kimliği doğrulanmadığından kaynak açıkça `actual_live_provider_return; upstream feed unspecified` diye işaretlenir.
- Makro kapı dosyasının gözlenen değişimleri, özgün JSON gövdesi ve gözlenme zamanı. Dosyanın içindeki eski zaman damgası kullanılabilirlik tarihi sayılmaz. Aynı kararın A → B → A dönüşü de ayrı olay olarak tutulur. Bu, 60 saniyelik gözlem arşividir; iki okuma arasında değişip kaybolan içeriklerin tamamını yakaladığı iddia edilmez.
- Pozisyon durumları, dolum/kapanış ve özgün fiyat seviyeleri. Mevcut ledger yeniden yazılmaz.

Stop ve trailing ile kapanan semboller, çıkıştan sonraki **4 saat** boyunca seans dışında da yalnızca fiyat kaydı için izlenir. Bu ek gözlem yeni işlem açmaz. Normal tarama sırasında zaten çekilmiş mumlar kullanılır; seans dışında gözlem gereken sembollerde ek veri sorgusu olabilir. Arşivleme hatası işlem onayını veya çıkış kararını değiştirmez; uyarı kaydı bırakır.

## Raporun yorumlanması

`scripts/analyze_execution_quality.py` yalnızca mevcut ledger ve gözlem arşivini okur. Giriş üretmez, alternatif kazanç hesaplamaz, parametre değiştirmez.

Eksiksiz dakika kapsamı ve dakikaya oturan yeni sürüm zamanları varsa pozisyonun MAE/MFE mum sınırları hesaplanır. Çıkış mumunun fitili gerçek çıkıştan sonraki hareketi de içerebileceği için bunlar kesin tick bazlı hareket değildir. Eski, dakika ortasına düşen zamanlar kesin kapsam olarak sayılmaz.

Çıkış sonrası özgün TP1/TP2'ye, mevcut spread tamponuyla, 4 saat içinde ulaşılıp ulaşılmadığı ölçülür. Trailing sonrasında özgün SL ile TP2'nin sırası ayrıca kaydedilir. Aynı 1m mumda ikisi de görülürse sıra belirsiz işaretlenir ve muhafazakâr olarak SL önce sayılır. Dört saat dolmamışsa beklenir; eksik/revize veri varsa sonuç bilinmiyor kalır. Bu takip, eski stopu kaldırıp yeni bir pozisyon varmış gibi PnL yazmaz.

Yeni rapor üretmek için mevcut bir çıktı adını yeniden kullanmadan:

```powershell
python scripts/analyze_execution_quality.py --start 2026-10-19 --end 2026-10-23 --output data/execution_quality_next
```

Tarihler TRT; `--start` dahil, `--end` hariçtir. Birkaç işlemden filtre seçilmeyecek; yeterli farklı gün ve enstrüman örneği oluşunca net beklenti, stop oranı, TP2'ye ulaşma ve kayıp serileri birlikte karşılaştırılacak. Gerçek bid/ask ve slipaj ölçümü hâlâ yoktur. 2025 özgün makro arşivi de geriye dönük yaratılmış değildir.

## Doğrulama

34 test geçti. Yeni testler; arşivde tekrarların tekilleştirilmesini, farklı mum sürümlerinin korunmasını, makro kullanılabilirlik zamanını, makronun önceki durumuna dönüşünü, kayıt hatasında işlem akışının devamını, eksik geçmişin bilinmiyor bırakılmasını, dört saatlik hedef takibinde belirsiz sırayı, model tamponunun gerçek gider gibi sunulmamasını, yanlış enstrüman/proxy karşılaştırmasının reddini ve NAS100 yedeğinin QQQ ile eşleşmesini kapsıyor.

## Erişilebilir geçmişle ek inceleme

13 sembolün yakın dönem 1m geçmişi Yahoo üzerinden indirildi; özgün canlı arşivden ayrı tutuldu. Raw CSV'ler ve indirme manifestleri `data/execution_backfill_20261022/` ve düzeltilmiş QQQ için `data/execution_backfill_qqq_20261022/` altında. Birleşik analiz kopyası `data/execution_backfill_verified_20261022.sqlite3`; geçerli sonuç `data/execution_quality_retrospective_final_20261022.md` ve `.json` dosyalarında. İlk kontrolün hatalı proxy karşılaştırmaları geçersiz/superseded olarak işaretlendi; orijinal işlem defteri değiştirilmedi.

| Döviz çıkışı | Tam 4h takip edilen | Sonrasında TP1 | Sonrasında TP2 |
|---|---:|---:|---:|
| Stop loss | 12 | 3 | 1 |
| Trailing stop | 3 | 1 | 0 |

Bu sayılar, çıkıştan sonraki fiyat gözlemleridir; stopu kaldırınca kazanılacak ek kâr değildir. İncelenen kayıtların tamamı eski sürüme ait. Bir stopun dört saatlik penceresi rapor anında henüz dolmamıştı; iki altın işlemi vadeli kontrat/spot eşdeğerliği doğrulanmadığı için dışarıda tutuldu. Bu küçük örneklem stopları topluca genişletmek veya trailing'i kaldırmak için güçlü destek vermiyor. Dört saat sonrasına dair çıkarım yapılmıyor.

12 işlemin kayıtlı dolum/kapanış arasındaki tam dakika penceresi kapsanabildi. Eski zaman damgaları dakika ortasına denk geldiği için gerçek dolumdan itibaren kesin MAE/MFE hâlâ bilinmiyor; raporda yaklaşık kayıt penceresi ölçümü ayrı alanlarda yer alıyor. Fiyat kaynağı özgün canlı sağlayıcıyla birebir eşit olarak doğrulanmadı.

## Bulunan ve düzeltilen NAS100 kaynak karışması

İşlem defterindeki NAS100 giriş seviyesi 718,75 iken ilk indirilen NQ=F vadeli serisi yaklaşık 30.000 seviyesindeydi. Kaynak incelendi:

- `swing-bos-core/server/twelveDataClient.ts:360` ve `Begonya/smc_engine/server/twelveDataClient.ts:339`, mantıksal NAS100 sembolünü **QQQ** olarak eşliyor.
- Begonya00 Yahoo yedeği NAS100'ü **NQ=F** olarak eşliyordu. Böylece veri kaynağı ve zaman dilimi değişince farklı enstrümanların fiyatları karışabiliyordu.
- Yerel yedek NAS100 için QQQ'ya düzeltildi. US100/NDX eşlemeleri değiştirilmedi. Bu, NAS100 nakit endeksinin fiyatı olduğu iddiası değildir: mevcut sistemin NAS100 etiketi QQQ vekilidir.
- Eski yerel NAS100 cache dosyaları `data/nas100_feed_alignment_20261022/` altında yedeklendi; 1m, 15m ve 1h cache QQQ serileriyle hizalandı. Eski NQ verileri işlem defterine uygulanmadı.
- QQQ 1h penceresi bu kontrolde 200 tamamlanmış 4H mum sağlamadığı için 4H sonucu `UNKNOWN` idi. Mevcut trend kuralı bu durumda NAS100'de yeni girişe izin vermez. Veri yetersizliği trend varmış gibi doldurulmadı.

Giriş, TP/SL ve risk parametreleri bu ölçümde değiştirilmedi. Öncelik, kaynak tutarlılığı ve gerçek maliyet verisini doğrulamaktır; sonraki filtre deneyleri bunun üzerine ayrı ve açıkça tanımlı yapılmalıdır. 2025 tam sistem testi için eksik tarihsel makro arşivi ve M1 veri gereksinimi devam ediyor.
