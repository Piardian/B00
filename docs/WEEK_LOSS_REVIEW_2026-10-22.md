# 19–22 Ekim 2026 kayıp incelemesi

İnceleme 22 Ekim 2026 tarihinde yerel `trade_ledger.json`, `engine_telemetry.jsonl` ve canlı kod üzerinden yapıldı. Hafta, kapanış tarihi 19–22 Ekim olan işlemler olarak tanımlandı. Bunlar OutcomeTracker / paper ledger sonuçlarıdır; broker ekstresi veya parasal hesap bakiyesi değildir. R, işlem başına başlangıç risk birimidir. Canlı ayar veya işlem kayıtları değiştirilmedi.

## Hesap

| Dönem / grup | Net sonuç |
| --- | ---: |
| 19 Ekim öncesi geçerli kapalı kayıtlar | +21,97R |
| 19 Ekim | −3,24R |
| 20 Ekim | −1,34R |
| 21 Ekim | −2,41R |
| 22 Ekim, inceleme anına kadar | −2,16R |
| Bu hafta | −9,15R |
| Geçerli kayıtların toplamı | +12,82R |

Önceki birikimin %41,65'i geri verilmiş. `INVALID_GHOST_SIGNAL` kayıtları hariç tutuldu. Bu hafta 38 kapanış kaydının 19'u dolmayan emir, 19'u gerçekleşmiş işlem. Gerçekleşenlerde 14 stop ve 5 pozitif kapanış var: başarı oranı %26,32. Stoplar −15,12R, pozitif kapanışlar +5,97R. Brüt sonuç −7,63R; kayıtlı maliyet 1,52R; net −9,15R.

Döviz: 16 işlem, 13 stop, −10,92R. Altın ve NAS100: 3 işlem, +1,77R. Bu hafta kapanan gerçekleşmiş kripto işlemi yok. Gerçekleşen işlemlerin tamamı SFP_VOLUME_ANOMALY.

## Kanıtlanan uygulama sorunları

1. **Canlı strateji ile sıkı backtest kuralları aynı değil.** `config.py` içindeki `REQUIRE_PRO_TREND_AAA=True` canlı motor/detektörde zorunlu koşul olarak kullanılmıyor. Canlı motor A+ derecesini de kabul ediyor. `REQUIRE_STRUCTURAL_BREAKER` detektöre import ediliyor ama denetlenmiyor. `USE_IFVG_ENTRY` iFVG bulunmadığında standart FVG veya fitil girişine izin veriyor. `custom_1m_backtest.py` ise trend, breaker ve giriş tepkisi için ayrı kurallar uyguluyor. Bu nedenle sıkı backtest sonuçları canlı stratejinin performansı olarak alınamaz.

2. **Nötr ortamda işlem açılıyor.** Sinyal telemetrisiyle sembol ve en yakın açılış zamanı üzerinden eşleştirilen 19 gerçekleşmiş işlemin 14'ünde teknik trend NEUTRAL; bunların toplamı −8,00R. Makro kapısı NEUTRAL_RANGE olan ayrı bir 14 işlem grubu −10,87R; yönlü makro onaylı 5 işlem +1,72R. Bu iki grup tanımı farklıdır ve sonuçlar birbirine eklenmez. Canlı makro istemcisi nötr kapıya düşük riskle izin verirken, makro filtresi etkin custom backtest nötr kapıyı reddediyor. Bu ayrım kayıp yoğunlaşmasını açıklar; tek haftalık veri gelecek performansını kanıtlamaz.

3. **Giriş tepkisi filtresi canlı takipte bağlı değil.** `REQUIRE_ENTRY_REACTION=True` olmasına rağmen `OutcomeTracker` limitin fiyat aralığına değmesini dolum kabul ediyor; slice-through/tepki kontrolü çağırmıyor. 20 Ekim AUD/JPY LONG ve 22 Ekim USD/CAD LONG doldukları dakika stop yazılmış. 15 dakikalık OHLC'den mum içi fiyat sırası bilinmediği için bunlara kesin hatalı stop denemez; mikro veriyle yeniden yürütme gerekir.

4. **Hedef kuralında sapma var.** Ayarlarda TP2 minimumu 3R; detektörün mevcut yerel değişikliği manyetik hedef eşiğini 2R'ye indiriyor. Haftanın 19 gerçekleşmiş işleminden 6'sında telemetride TP2 oranı 3R altında; altısı da stop. Bu, minimum kuralla uyumsuzluğu kanıtlar; stopların doğrudan hedef düşürülmesinden kaynaklandığını kanıtlamaz.

5. **Zarar serisini kesecek portföy freni görünmüyor.** Canlı giriş yolunda günlük zarar limiti, art arda stop limiti veya bağlantılı pariteler için toplam risk sınırı yok. Tek sembolde aktif işlem koruması ve 45 dakikalık sinyal beklemesi bunların yerini tutmuyor.

## Sonuçların güvenilirliğiyle ilgili ek sınırlar

- Motor pozisyon takibine yalnızca son 15 dakikalık barı gönderiyor; atlanan barları sırayla işlemiyor. Aynı bar tekrar değerlendirilebiliyor. TP/SL aynı mumda olduğunda kodun kontrol sırası sonucu etkileyebilir.
- Canlı trend hesabı aynı 15 dakikalık seride EMA20/50/200 kullanıyor; ayar açıklamasındaki ayrı 4H teyidi canlı tarama yolunda yok.
- Makro risk çarpanı bildirim/telemetride bulunuyor; `register_trade` bunu pozisyona kaydetmiyor ve ledger R toplamını çarpanla ağırlıklandırmıyor. Dolayısıyla +12,82R gerçek hesap getiri yüzdesine çevrilemez.
- Döviz verisinde gerçek hacim bulunmayınca sağlayıcı fiyat aralığından yapay hacim üretebiliyor. Haftanın 19 gerçekleşmiş sinyalinden 15'inde hacim anomalisi false; bu grup −7,96R. Strateji adı zorunlu hacim teyidi anlamına gelmiyor.

## Teknik düzeltme sırası

Önce canlı ile backtest kurallarını ortak ve zorunlu bir doğrulama yolunda birleştirmek; sonra giriş/dolum/TP/SL takibini zaman sıralı mikro veriyle doğrulamak; ardından portföy risk sınırlarını uygulamak gerekir. Tarihsel bu hafta üzerinde filtre seçip aynı haftayı başarı kanıtı olarak kullanmamak gerekir. Mevcut inceleme bir neden analizi; düzeltmeler henüz uygulanmadı.
