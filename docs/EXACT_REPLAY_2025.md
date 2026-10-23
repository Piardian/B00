# 2025: üç ayda canlı sistemin tekrar oynatılması

İstenen temel testte yeni bir giriş/çıkış algoritması veya makro stratejisi tanımlanmadı. Aylar sonuçlara bakılmadan **Ocak, Haziran, Kasım 2025** olarak seçildi. Ay sınırları UTC, günlük zarar freni canlıdaki gibi TRT günüdür.

## Mevcut sonuç: performans testi çalıştırılamadı

22 Ekim 2026 tarihinde `scripts/replay_live_system.py --run` ile mevcut 64 sembollük evrene üç ay için veri ön kontrolü uygulandı. Canlı ayarda hariç tutulan AUD/USD ve GBP/JPY çıkarılınca veri gereken 62 sembol kalıyor.

| Ay | Geçerli 1m verisi olan sembol | Geçerli 15m / 1h verisi olan sembol | Tarihsel özgün makro karar arşivi | Sonuç |
|---|---:|---:|---|---|
| Ocak 2025 | 0 / 62 | 26 / 62 | Bulunamadı | Eksik veri nedeniyle çalıştırılamadı |
| Haziran 2025 | 0 / 62 | 26 / 62 | Bulunamadı | Eksik veri nedeniyle çalıştırılamadı |
| Kasım 2025 | 0 / 62 | 26 / 62 | Bulunamadı | Eksik veri nedeniyle çalıştırılamadı |

Bu tablo işlem sonucu değildir. Üç ay için net R, başarı oranı, TP, SL veya hesap getirisi **hesaplanmadı**. JSON'da `metrics: null` ve `BLOCKED_MISSING_INPUTS` var; sıfır işlem/başarılı test anlamına gelmiyor. 15m/1h sayıları 65 günlük ısınma dahil istenen aralıkta veri bulunan sembolleri gösterir; tam veri kalitesi onayı değildir.

Tam kayıt: `data/exact_replay_2025_final_20261022/input_audit.json`. Aynı klasörde 12 üretim modülünün hash ile doğrulanmış kaynak kopyaları, tekrar oynatma betiği ve etkin ayarlar bulunur. Üç ay da 136 girdi engeli nedeniyle çalıştırılmadı; bir performans çıktısı üretilmedi.

Önemli veri hatası: EUR/USD için her üç ayın MT5 M1 sorgusu 2026-07-16 16:16 UTC tarihli tek bir mum döndürdü. İstenen ayın dışında olduğu için reddedildi. Aynı üç ayın M15 verileri gerçekten 2025 tarihliydi; M15 verisini M1'e bölerek doldurmadık. MT5'in yalnızca terminalde mevcut geçmişi sağladığı [resmî belgede](https://www.mql5.com/tr/docs/python_metatrader5/mt5copyratesrange_py) açıklanıyor. Bu gözlem tek başına hatanın broker, terminal veya API katmanlarından hangisinde olduğunu kanıtlamaz.

Proje, bağlı fiyat klasörleri ve komşu Begonya projesindeki makro kapı dosyaları kontrol edildi. Bulunan kapılar Ekim 2026 tarihli; bunları 2025'e uygulamak gelecekteki bilgiyi kullanmak olur. Ekonomik olay CSV'si, özgün makro kapı kararlarının ve risk çarpanlarının arşivi değildir.

Eski `DailyMacroGateTable` bu talebe uygun değil: eksik göstergeleri sabit/sentetik değerlerle dolduruyor, reel faizi sentetik hesaplıyor ve canlı makro motorunun özgün geçmiş çıktısını kullanmıyor. Eski 2025 testleri de farklı TP/SL, saat, giriş ve çıkış kuralları içeriyor. Sonuçları bu sisteme aitmiş gibi aktarılmadı.

## Tekrar oynatma nasıl çalışıyor?

`scripts/replay_live_system.py`, doğrudan mevcut `BegonyaEngine.scan_symbol`, `_process_candidate`, SFP/ORB detektörleri, `MacroGateClient`, `NewsGuard`, `OutcomeTracker.register_trade` ve `check_trade_progress` yöntemlerini çağırır. İşlem kuralı kopyalamaz. Sadece saat, geçmiş fiyat sağlayıcısı, kayıt yolları, grafik üretimi ve bildirim bağlantıları izole edilir. Canlı dosyalara yazmaz, Telegram'a bağlanmaz.

- Canlıdaki 60 saniyelik tarama ve sembol sırası kullanılır. 300 adet 15m, 1000 adet 1h ve 1000 adet 1m pencereleri korunur. Gerçek 4H hesabı aynı üretim fonksiyonudur.
- Tarihsel saat hem Python hem pandas saat çağrılarına uygulanır. Gelecekteki kapanış mumu filtrelerden geçemez.
- Makroda yalnızca o anda yayımlanmış özgün snapshot geçerlidir. Makro kararları bugünkü fiyatlardan yeniden uydurulmaz.
- Günlük zarar, stop serisi, açık risk ve ortak para birimi sınırları aynı portföy nesnesi üzerinde çalışır.
- Haber filtresi mevcut `news_events.json` ile aynen çalışır. Bu dosyada 2025 olayları bulunmaması mevcut sistemin bir eksiğidir; sessizce tarihsel bir haber filtresi eklenmez.
- Ay sonunda açık pozisyonlar yapay olarak kapatılmaz. Kapalı sonuç, açık pozisyon ve eksik veri ayrı raporlanır. Her ay boş portföyle başlar; üç ayrık ay tek devamlı yıl simülasyonu değildir.
- Kod dosyaları SHA256 ile tanımlanır; etkin ayarlar rapora yazılır. Sonraki çalıştırmalarda kaynak kopyaları çıktı klasöründe saklanır.

Bu, canlı **paper modelinin** tekrarıdır. Broker dolumu, gerçek bid/ask, bağlantı gecikmesi veya yeniden üretilemeyen 2025 LLM kararları için birebirlik iddiası yoktur. Sabit dakika başında tarama, canlı taramanın ölçülmüş gecikmelerini içermez. 23 Ekim düzeltmesiyle limit teması dolum sayılır; aynı bardaki stop zarar yazar, başarısız tepki dolmuş işlemi kapanış fiyatından maliyetle kapatır. Bu hâlâ gerçek broker dolumu doğrulaması değildir. Güncel durum: [doğrulama düzeltmeleri](FOREX_GOLD_VALIDATION_FIXES_2026-10-23.md).

## Eksik girdilerin sözleşmesi

`--data-root` klasöründe her sembol için `EURUSD_1m.csv`, `EURUSD_15m.csv`, `EURUSD_1h.csv` düzeni gerekir. Kolonlar: `datetime,open,high,low,close,volume`. Zamanlar UTC; 15m ve 1h dosyalarında ay başından önce en az 65 günlük veri olmalıdır. `provenance.json` kaynak ve hacmin gerçek/tick/sentetik anlamını açıklamalıdır. MT5, Yahoo ve Binance fiyatları sessizce birbirinin yerine geçirilmez.

`--macro-archive` JSONL satırlarında `available_at`, özgün `gate` gövdesi ve kaynağı açıklayan `provenance` gerekir. Arşivin tarama dönemini kapsadığı ve kesintisiz kaydedildiği ayrıca doğrulanmalıdır; tek bir eski snapshot tüm ayın karar akışını kanıtlamaz.

Örnek komut, girdiler tamamlandıktan sonra:

```powershell
python scripts/replay_live_system.py --run --months 2025-01 2025-06 2025-11 --data-root D:/verified_history --macro-archive D:/verified_history/macro_gates.jsonl --output data/replay_2025_verified
```

Makro arşivi veya fiyat bulunamazsa bu komut sonuç uydurmak yerine başarısız durum döndürür.

## TP / stop açısından pragmatik değerlendirme

Henüz yeni sistemin daha kârlı olduğu kanıtlanmadı. Koruma eklemek ile pozitif beklenti göstermek farklı işlerdir. Ama ölçülebilecek somut iyileştirme alanları var:

1. **Maliyetin stop mesafesine oranı.** Canlı modelde döviz için spread tamponu girişin %0,02'si. Örneğin 1,4036 giriş ve 0,0007 stop mesafesinde tampon yaklaşık 0,40R eder; ayrıca 0,08R sabit maliyet var. Bu bir broker maliyet ölçümü değil, mevcut kodun varsayımıdır. Önce gerçek bid/ask ve slipajla doğrulanmalı; sonra yüksek maliyet/risk oranlı kurulumların elenmesi ayrı bir deney olarak denenebilir.
2. **Stopların tipi.** Gerçekten tezi bozulan işlemlerle stop sonrası özgün hedefe dönen işlemleri ayırmak için MAE/MFE ve hedefe/stopa ilk ulaşma sırası ölçülmeli. Bu ölçüm olmadan stopu daraltmak daha sık stop yaratabilir; genişletmek ise hedefe ulaşmayı zorlaştırabilir. Yeni stop veya giriş kuralı bu temel teste eklenmedi.
3. **Kârın nerede kesildiği.** TP1=1R'de yarısı, TP2=3R'de kalan yarısı kapanınca tam başarı brüt 2R, mevcut sabit ücretle net 1,92R'dir. +0,75R trailing stopla kalan yarı kapanırsa net yaklaşık 0,795R; kalan yarı başabaş kapanırsa net 0,42R. Sırf TP2 etiketini büyütmek beklentiyi artırmaz. Önce kaç işlemin trailing sonrası özgün TP2'ye vardığı ölçülmeli.
4. **Sembol, strateji ve seans ayrımı.** Kayıpların belirli gruplarda tekrarlanıp tekrarlanmadığına bakılmalı. Daha az işlem tek başına daha iyi sistem demek değildir; net beklenti ve düşüş de iyileşmeli.

Sadece tam TP2 ve tam stop iki sonucu olsaydı 1,92R kazanç / 1,08R kayıpla başabaş başarı oranı %36 olurdu. Kazançların çoğu 0,795R trailing ile bitseydi gereken oran yaklaşık %57,6 olurdu. Gerçek karışım ancak doğru işlem örnekleminden çıkar. Başarı oranını tek başına yükseltmek hedeflenmemeli.

Bu üç ay ilk durum ölçümü olarak tutulmalı. Aynı aylarda çok sayıda filtre deneyip en iyi kombinasyonu seçmek, sonra aynı sonucu kanıt saymak uygun değil; bu risk [backtest aşırı uyumu araştırmasında](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) ele alınıyor. Öneriler şimdilik hipotez; canlı ayarlara uygulanmadı.

## Testler

`tests/` altında 22 test geçti. Yeni dört test; tarih dışı mumların reddini, eksik makroda sıfır getiri gösterilmemesini, gelecek mumların dışlanmasını ve gerçek canlı tracker ile izole kayıt yolunda işlem yaşam döngüsünü doğrular. Bu son testteki sentetik veri sadece yazılım testi içindir; 2025 performansı olarak raporlanmaz.
