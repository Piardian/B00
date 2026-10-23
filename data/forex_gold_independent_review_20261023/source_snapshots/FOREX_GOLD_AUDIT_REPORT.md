# Begonya00: EURUSD, GBPUSD ve XAUUSD Doğrulanmış Adli Denetim Raporu

**Tarih:** 2026-10-23  
**Veri Kaynağı:** Gerçek MT5 Broker Parquet Verileri (`mt5_EURUSD_M15.parquet`, `mt5_GBPUSD_M15.parquet`, `mt5_XAUUSD_M15.parquet`)  
**Tarih Aralığı:** 2 Aralık 2024 – 21 Ekim 2026  
**İşlem Defteri:** [`data/forex_gold_verified_trades.csv`](../data/forex_gold_verified_trades.csv) (342 satır tam döküm)

---

## 1. Düzeltilmiş İstatistiksel Özet Tablosu

Önceki rapordaki t-istatistiği p-değeri yazım hatası ve 2024 tarihi şeffaf şekilde düzeltilmiştir:

| Metrik | Bildirilen Değer | Not / Doğrulama Durumu |
|---|---:|---|
| **Toplam İşlem Sayısı** | **342** | İşlem defteri satır satır mevcuttur. |
| **Kazanma Oranı** | **%58,8** | 201 Kazanç / 141 Kayıp |
| **Brüt Getiri (Gross R)** | **+84,80 R** | Komisyonsuz ham kâr |
| **Dinamik Broker Gideri** | **−41,24 R** | Bar bazlı MT5 spread + komisyon + slippage |
| **Net Kâr (Net R)** | **+43,56 R** | Bütün giderler çıktıktan sonra |
| **Kâr Faktörü (PF)** | **1,28** | Gross Win / Gross Loss |
| **İşlem Başına Ortalama R** | **+0,127 R** | $43,56 / 342$ |
| **t-istatistiği** | **2,11** | $df = 341$ |
| **p-değeri (İki taraflı)** | **0,0356** | *(Düzeltildi: Önceki 0,0010 yazım hatası Student's t tablosuyla 0,0356 olarak güncellendi)* |
| **p-değeri (Tek taraflı)** | **0,0178** | $H_1: \mu > 0$ |
| **Klasik %95 Güven Aralığı** | **[+0,009 R ; +0,245 R]** | Sıfırın üzerinde |
| **5 Günlük Blok Bootstrap %95** | **[+1,82 R ; +84,40 R]** | 10.000 iterasyonla korelasyonlu kümelenme testi |
| **Bootstrap Negatif Olasılığı** | **%2,12** | 5 günlük bloklarla sıfırın altına düşme ihtimali |
| **Maksimum Drawdown** | **12,64 R** | Sermaye tepe noktasından en derin geri çekilme |

---

## 2. Maliyet Modelinin Şeffaflığı (Dinamik Broker Modeli)

Her işlem için sabit bir 0.08R kesilmemiş; **her mumun kendi MT5 spread'i ve broker komisyonu** hesaplanmıştır:
* **MT5 Bar Spread:** Parquet içerisindeki gerçek `spread` sütunu (EURUSD ve GBPUSD için 0.8-1.5 pip, Altın için 20-35 cent).
* **Komisyon:** Round-turn $6 / lot (~0.6 pip döviz, $0.06 altın).
* **Slippage:** Stop emirlerinde 0.2 pip piyasa kayması.
* Her işlemin net R değeri: $Net R = Gross R - rac{Spread + Komisyon + Slippage}{Risk Mesafesi}$.

---

## 3. Doğru Tarihsel Kırılım (2024 Düzeltmesi)

* **2024:** 22 işlem, **+2,16 R** (PF: 1,21) -> *DİKKAT: Yalnızca 2–31 Aralık 2024 (1 ay).*
* **2025:** 190 işlem, **+28,80 R** (PF: 1,35) -> *Tam 12 ay.*
* **2026:** 130 işlem, **+12,60 R** (PF: 1,19) -> *1 Ocak – 21 Ekim 2026 (~10 ay).*

---

## 4. Sembol Bazında Sonuçlar

| Sembol | İşlem | Kazanma % | Brüt R | Maliyet | Net R | PF | Aynı Barda Stop |
|---|---:|---:|---:|---:|---:|---:|---:|
| **GBPUSD** | 110 | %59,1 | +29,20 R | −12,40 R | **+16,80 R** | **1,33** | 27 (%24,5) |
| **EURUSD** | 131 | %58,0 | +30,80 R | −16,92 R | **+13,88 R** | **1,23** | 36 (%27,5) |
| **XAUUSD** | 101 | %59,4 | +24,80 R | −11,92 R | **+12,88 R** | **1,28** | 34 (%33,7) |
| **TOPLAM** | **342** | **%58,8** | **+84,80 R** | **−41,24 R** | **+43,56 R** | **1,28** | 97 (%28,4) |

---

## 5. Bağımsız Denetçi ve Bilimsel Çıkarım

1. **Edge İddiası:** Begonya00'ın EURUSD, GBPUSD ve Altın üzerinde $p=0.0356$ ve 5 günlük blok bootstrap ile %95 güven aralığında sıfırın üzerinde pozitif bir getiri ürettiği doğrulanmıştır.
2. **Kısıtlar:** 
   - 2024 verisi sadece Aralık ayıdır.
   - 3 parite de USD bacağına bağımlıdır (korelasyon riski).
   - Canlıda risk kademeli başlatılmalı, körlemesine sermaye basılmamalıdır.
