# Forex ve Altın: eski aday simülatörünün işlem defteri özeti

**Bu rapor canlı sistemin tam backtesti değildir; doğrulanmış edge veya canlıya geçiş onayı vermez.**

Ayrı M15 simülatörü canlı iFVG/Breaker dedektörünü, makro/haber kapılarını ve ortak risk takibini çalıştırmıyor. Dolumdan önceki hedefin kâr yazılması bağımsız M1 kontrolünde gösterildi. Aşağıdaki rakamlar bu kusurlu modelin kaydedilmiş defterini özetler; gerçekleşebilir getiri sayılmaz.

İşlem defteri: `forex_gold_verified_trades.csv`; SHA256: `44af99976a236d444f77d64f0fd91149a7fcccc1a1aa37d9ca6f9f9b6741a2ae`.

Maliyet etiketi: adayın varsayılan 1.0x modeli; 1.5x maliyet sonucu değildir. Spread sütunu ve varsayılan komisyon/kayma, gerçek broker dolumlarının kanıtı değildir.

| Ölçüm | Defterden hesaplanan |
|---|---:|
| İşlem | 343 |
| Kazanç / kayıp | 201 / 142 |
| Kazanma oranı | %58.60 |
| Brüt / maliyet / net | +82.6000 / 49.8886 / +32.7114 R |
| PF | 1.1964221592662734 |
| Ortalama | +0.095369 R |
| t / iki taraflı p (IID varsayımı) | 1.554312 / 0.121035 |
| Ortalama için %95 Student t aralığı | [-0.025317, +0.216054] R |
| Kapanış sırasıyla maksimum düşüş | 14.6748 R |
| Beş işlem günü blok bootstrap toplam %95 aralığı | [-11.8698, +77.1224] R |
| Bootstrap örneklerinde sıfır veya negatif toplam oranı | %7.66 |

IID testi korelasyonu ve seçim yanlılığını çözmez. Bootstrap oranı edge yokluğu olasılığı veya p-değeri değildir. Düşüş hesabı açık pozisyon zararını içermez. Bloklar beş aktif işlem günüdür; takvim haftası değildir.

| Sembol | İşlem | Net R |
|---|---:|---:|
| EURUSD | 132 | +3.6613 |
| GBPUSD | 110 | +13.6543 |
| XAUUSD | 101 | +15.3958 |

| Açılış yılı | İşlem | Net R |
|---|---:|---:|
| 2024 | 22 | +0.9546 |
| 2025 | 190 | +25.5642 |
| 2026 | 131 | +6.1926 |

2024 yalnızca Aralık verisi; 2026 veri sonuna kadardır. Hiçbiri bağımsız ve dokunulmamış örneklem dışı doğrulama değildir.

[Bağımsız inceleme ve dolum sırası kanıtları](FOREX_GOLD_INDEPENDENT_REVIEW_2026-10-23.md)
