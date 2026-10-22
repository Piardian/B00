# 2025 tam sistem oynatması: yöntem ve sınırlar

22 Ekim 2026. Bu çalışma henüz tamamlanmış bir performans backtesti değildir.
Sabit aylar: Ocak, Haziran, Kasım 2025. Aylık sonuçlar görülerek ay seçilmedi.
Güncel durum: `data/full_2025_study/FULL_SYSTEM_2025_STATUS.md`.

Son kullanıcı talebi kapsamı **yalnız Ocak 2025** olarak daralttı.
`requested_scope.json` bu tercihi saklar; devam aracı açık `--months`
verilmediğinde bu kapsamı kullanır. Kullanıcı otomatik devam istemedi.
Önceki üç ayın girdileri korunur, Haziran/Kasım oynatması yürütülmez.

## Gerçekte çalıştırılan sistem

`scripts/replay_live_system.py`, orijinal `BegonyaEngine.scan_symbol` /
`_process_candidate`, SFP/ORB dedektörleri, HTF filtresi, MacroGateClient,
NewsGuard ve OutcomeTracker kodunu çağırır. Yeni bir entry üretilmez.
Dakikalık saat, tamamlanmış mum sınırı ve sembol sırası korunur. Her ay boş
pozisyonla bağımsız başlar. Ay sonundaki açık pozisyon zorla kapatılmaz.

SFP/ORB aday indeksi, aynı dedektörlerin aynı M15/H1 pencerelerindeki
sonuçlarıdır; sonuç metrikleri değildir. Kod ve veri SHA256 kontrolleri
değişen indeksin sessizce kullanılmasını engeller. Pozisyon takibi her dakika
sürer. Bellek optimizasyonu yalnız M1'i ilgili ay ve önceki bir güne kırpar;
M15/H1 dedektör ve HTF geçmişini kırpmaz. İki bellek modunun işlem sonucu
eşitliği regresyon testinde doğrulanır.

Emir dolumu, kısmi TP, stop, BE/trailing, işlem maliyeti tamponu ve risk
frenleri mevcut koddan gelir. OHLC içindeki sıra bilinmiyorsa mevcut stop
önceliği uygulanır. Gerçek broker dolumu, spread ve kayma kaydı mevcut
olmadığından sonuçlar gerçekleşmiş hesap getirisi olarak sunulamaz.

## Fiyat ve takvim

- 62 sembol için 186 adet M1/M15/H1 sıkıştırılmış fiyat dosyası üretildi;
  canlı konfigürasyonda dışlanan iki sembol dışarıda kaldı.
- Kripto: Binance resmi arşivleri ve dosya doğrulamaları. 2025 mikro-saniye
  zaman damgası normalize edildi. Listeleme öncesi dönem doldurulmadı.
- Forex/altın: brokerın gerçek bid tick'lerinden M1 ve doğal M15/H1.
  Bunlar arşivlenmiş canlı TwelveData Forex akışının birebir aynısı değildir.
- ETF: TwelveData QQQ/SPY; mevcut sistemdeki NAS100 eşlemesi QQQ'dur.
- Broker duvar saati, bağımsız fiyat karşılaştırmasıyla doğrulanan New York
  yaz/kış saatine göre UTC+2/UTC+3 düzeltilir. ABD/Avrupa farklı DST haftaları
  ayrıca kontrol edildi. Forex/altın günlük kapalı saatleri boş mumla doldurulmaz.
- Resmi ForexFactory aylık sayfaları, istenen haftaların önceki/sonraki ay
  taşmalarını da kapsar. Eksik ay 'haber yok' sayılmaz. Tarihsel ekonomik
  gerçekleşmeler ham arşivde dursa da canlı akıştaki altı alanlı sözleşmede
  bulunmadığı için modele eklenmez. Haber veto pencereleri mevcut beş olay
  tanımından tarihsel gerçek tarihlere taşınır.

Bazı broker enstrümanlarında ayın UTC sonundaki son iki/üç saat henüz eksiktir.
EURUSD ve beş başka paritenin elde edilebilen sınır verileri eklendi; kalan
boşluklar uydurulmadı. İzlemede gerçek boşluk veya ay sonu fiyatlanmamış açık
işlem kalırsa `complete_return_coverage=false` olur. Üç ay yürütülmüş olsa da
bu durumda devam aracı tam sonuç sertifikası vermez.

## Makro: geçmişe bakış hatası ve gerçek model çıktısı

Resmi ALFRED veri vintajları, yayın tarihleri ve resmi tahvil kaynakları
kullanılır. Gün içi kesin yayın saati bulunmayan FRED vintajlarında önceki
UTC gününün veri erişimi kullanılır; bu muhafazakâr günlük varsayım özgün
canlı veri erişiminin birebir kaydı değildir. Makro piyasa görünümü son
tamamlanmış M15/H1 ve tamamlanmış günlük veriden kurulur; özgün tick görünümü
değildir. Takvim tahminlerinin o gün kaydedilmiş özgün sürümü doğrulanamamıştır.

Model grafiği, tarihi saat dondurulup **canlı `as_of=None` yolu** üzerinden
orijinal üç uzmanla çalıştırılır. Yalnız aynı rol, prompt, sistem talimatı,
şema, router kodu ve model listesi için kaydedilmiş gerçek cevap tekrar
kullanılabilir. Cevap eksikse gerçek servis çağrısı gerekir; risk çarpanı veya
rejim varsayılarak işlem açılmaz. Çıktılar araştırma klasörüne yazılır;
canlı makro kapıları veya işlem defteri üzerine yazılmaz, bildirim gönderilmez.

İşlemde tüketilmeyen makro döngüleri atlanır; grafikte döngüler arasında rejim
taşıması bulunmadığı doğrulandı. Bu, kullanılmayan döngülerde servis arızası
olmadığı varsayımını içerir. Mevcut kuralların modelden bağımsız kesin veto
verdiği yön/risk durumlarında çağrı atlanabilir. Bu kanıtlar onay üretemez;
olası her onay gerçek model çıktısını gerektirir.

Mevcut ihracatçı 37 kripto sembolüne yön kapısı vermez. Bunlar makro nötr
kalır. ETF'ler mevcut 1000 H1 penceresinde 200 tamamlanmış UTC dört saatlik
gruba ulaşamadığından HTF_NOT_READY kalır. Bunları düzeltip baseline
performansı değiştirmedik. SOL rotasyonu için geçmiş gerçekleşmiş funding,
canlı premiumIndex.lastFundingRate alanına eşdeğer değildir ve onay girdisi
olarak kullanılmaz. Mevcut tek ilgili SOL short adayı, gerçek BTC ana yönü
tarafından modelden bağımsız veto edilir; başka durumda eksik rotasyon
girdisi testi durdurur.

2025'in özgün LLM cevapları yoktur. Tamamlansa bile çalışma, **bugünkü sistemin
2025 verisiyle ve bugünkü model servisiyle yeniden kurulmuş backtesti** olur.
2025'te alınmış özgün kararların birebir tekrarı veya broker işlem kaydı değildir.

Araştırma anahtarı kullanılırken sağlayıcı hata kaydı ayrıca tutulur.
Google'ın 503 yoğunluk ve 504 deadline yanıtları gözlendikten sonra yalnız
araştırma HTTP zaman aşımı 25 saniyeden 90 saniyeye çıkarıldı. Prompt, şema,
üretim parametreleri ve model sırası değiştirilmedi; canlı yönlendirici aynı
kalır. Çalışma özgün servis kesintilerini veya timeout kaynaklı model
seçimlerini birebir yeniden üretme iddiasında değildir.

## Tekrar çalıştırma

Önce `data/full_2025_study/model_quota_all_keys.json` ve paylaşılan canlı servis
kotası kontrol edilmelidir. Yeni ücretli kapasite bu çalışma tarafından açılmadı.

```powershell
# Ağ çağrısı yapmadan eldeki gerçek cevapların izin verdiği yere kadar doğrula:
python scripts/resume_full_2025_study.py --offline-models

# Uygun model kapasitesi mevcutsa üç ayı sırayla yeniden yürüt:
python scripts/resume_full_2025_study.py
```

Araç kota sıfırlanma zamanından önce normal çalıştırmada yeni çağrı yapmaz.
Gerçek model cevapları diskte kaldığından yeniden başlatma onları korur;
işlem defteri her denemede baştan yürütülür. Sonuç klasörleri farklıdır.
`resume_status.json` tamamlanmayan ayda metrikleri null tutar. Geçmiş kotanın
sıfırlanması, bütün çalışma için yeterli kapasite oluşacağı garantisi değildir.

`source_snapshot_manifest.json` kaynak kodu anlık kopyasının SHA256 listesidir.
`prices_utc/provenance.json`, takvim manifesti ve model cevap teypleri girdi
izlenebilirliğini sağlar. Bunlar eksik performans sonucunun yerine geçmez.

Bu turdaki makro veri tazeliği ve canlı saat düzeltmeleri kaynakta uygulanıp
test edildi; çalışan makro servisi bu değişiklikler için yeniden başlatılmadı.
