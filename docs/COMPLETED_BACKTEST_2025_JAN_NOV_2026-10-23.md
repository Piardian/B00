# Yeni araştırma anahtarıyla tamamlanan ay testleri — 23 Ekim 2026

Yeni proje anahtarı gerçek makro çıktısı üretti. Ocak 2025 ve ek kontrol olarak Kasım 2025, asıl giriş ve işlem takip motoruyla ay sonuna kadar yeniden oynatıldı. Yeni entry mekanizması eklenmedi.

**Sonuç: bu iki dönem pozitif ve kalıcı edge kanıtlamıyor.**

| Dönem | Paper maliyet çarpanı | Dolmuş/kapanmış işlem | Net R | Makro risk çarpanlı net R |
|---|---:|---:|---:|---:|
| 2025-01 | 1.0x | 3 | -0.043333 | +0.168897 |
| 2025-01 | 1.5x | 3 | -2.293333 | -1.715213 |
| 2025-01 | 2.0x | 3 | -2.975833 | -2.315335 |
| 2025-11 | 1.0x | 1 | -0.417763 | -0.360112 |
| 2025-11 | 1.5x | 1 | -0.590653 | -0.509143 |
| 2025-11 | 2.0x | 1 | -1.160000 | -0.999920 |

Ocakta üç gerçekleşmiş işlem EURUSD ORB; Kasımda tek gerçekleşmiş işlem EURUSD SFP/iFVG/Breaker. GBPUSD ve XAUUSD bu iki ayda dolmuş işlem üretmedi. Dört temel senaryo işlemi istatistiksel üstünlük göstermek için yeterli değildir. 1.5x ve 2x aynı işlemlerin bağımsız tekrarları sayılmaz.

Normal net R, eşit birim riskle işlem toplamıdır. Diğer sütun her işlemin makro risk çarpanını uygular; gerçek hesap yüzdesi veya gerçekleşmiş para getirisi değildir. Bu nedenle Ocak normal toplamı hafif negatifken risk çarpanlı toplam hafif pozitiftir.

## Kapsam ve sınırlar

- Aynı BegonyaEngine, SFP/ORB dedektörleri, makro/haber kapıları, risk frenleri ve passive-limit-v3 takipçisi kullanıldı. Tüm senaryolarda kaynak kod SHA256 değerleri aynı ve mevcut kaynaklarla eşleşiyor.
- Makro çıktılar orijinal 2025 LLM arşivi değildir; gerçek tarihsel girdilerle güncel üretim grafiğinden yeniden üretildi. Yalnız olası girişlerin tükettiği görüntüler hesaplandı. Kullanılmayan ara analizlerin ardışık rejim durumu taşıması birebir modellenmedi. Dolayısıyla 2025 canlı davranışının birebir kanıtı veya makro motorunun bütün tarihsel akışının eksiksiz testi denemez.
- Paper gideri sabit 0.08R, spread eşiği fiyat oranıdır; stres çarpanı ikisini de değiştirir. Böylece dolum zamanı ve kapanış da değişebilir. Gerçek bid/ask, hesaba ait tarihsel komisyon, swap ve kayma doğrulanmadı.
- Her senaryoda ay sonunda açık işlem, çözülmemiş takip boşluğu ve fiyatlanmamış aktif kuyruk yok. Bu, veri dosyalarında piyasanın açık olduğu her dakikanın kesin mevcut olduğuna dair genel bir sertifika değildir.
- Kasım 2025 eski varlık seçimi taramasına dahildi; görülmemiş örneklem dışı veri değildir. 36 dosyalık protokolde kaydedilen gerçek ileri dönem Kasım 2026 henüz yaşanmadı.
- Canlı paper süreç yeniden başlatılmadı; gerçek para emri verilmedi ve otomatik devam kurulmadı.

Önceki kota engeli yeni projeyle aşıldı. API yanıtları ve gerçek karar dosyaları çalışma klasöründe korunuyor. Anahtar metni rapora eklenmedi.

## Kaynak sonuç dosyaları

- `data\full_2025_study\replay_attempts\20261023T064213\2025-01\result.json`; SHA256 `f782e5a3bcee9cdc9b591107202a2b00e0c98a152f500cc47cb164a392340ce7`
- `data\full_2025_study\january_completed_new_project_cost_1_5\result.json`; SHA256 `669f7415c3b78f503252162affac1e40013f08b0fa3c598021a4e8ca551c8a34`
- `data\full_2025_study\january_completed_new_project_cost_2\result.json`; SHA256 `d248e6d190173ed78a385929ca2d4fc94c46dce3bf4ee767f9c997a315b335b1`
- `data\full_2025_study\replay_attempts\20261023T064501\2025-11\result.json`; SHA256 `352fb5bbf80067a1421af1ef514492d3a19fb124a1a98d5cbcb79cf42e0e21a8`
- `data\full_2025_study\november_completed_new_project_cost_1_5\result.json`; SHA256 `3a178df1d2994d8c82bbcfb4d2ce238fdedd1a0ba6606140ce66468eb6b269a4`
- `data\full_2025_study\november_completed_new_project_cost_2\result.json`; SHA256 `9c5b1f35572bb8d8084426aefeb50797272d92461251bd9a9fb9c5ce6b1def0c`
