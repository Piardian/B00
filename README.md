# 🌺 Begonya 00 (Çift Sıfır): Kurumsal Makro Rejim, SFP & Hacim Anomalisi ve ORB Seans Hibrit Sistemi

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Architecture](https://img.shields.io/badge/Architecture-Macro%20%2B%20SFP%2FVolume%20%2B%20ORB-purple.svg)]()
[![Execution](https://img.shields.io/badge/Execution-Fully%20Autonomous-brightgreen.svg)]()

**Begonya 00**, kurumsal düzeyde çalışan iki temel ayağı tek bir orkestrasyon çatısı altında birleştiren yeni nesil hibrit bir otonom işlem çerçevesidir:
1. **Makroekonomik Rejim Motoru (`macro_engine`):** Çoklu Google Gemini yapay zeka ajanları, FRED veri entegrasyonu, ABD Hazine getiri eğrisi dinamiği (2Y/10Y spread), TIPS reel faizleri ve Fed net likidite metrikleriyle piyasanın birincil rejimini ve yön kısıtını belirler (`shared/macro_bias_gate.json`).
2. **SFP & Hacim Anomalisi ve ORB Seans Motoru (`sfp_orb_engine`):** Klasik SMC yerine likidite süpürmeleri (Swing Failure Pattern), kurumsal hacim patlamaları (Z-Score & Spike Climax) ve Londra/New York seans açılış aralıkları (Opening Range Breakout) ile milisaniyelik seviyede A+/A kalite işlem sinyalleri üretir.

---

## 🏛️ Mimari Şema

```text
                                 [ KÜRESEL PİYASA VERİLERİ ]
                        (TwelveData API, FRED API, Takvim & Makro)
                                             │
                                             ▼
                     ┌───────────────────────────────────────────────┐
                     │  1. MAKROEKONOMİK REJİM MOTORU (Python)       │
                     │  • Getiri Eğrisi & 20-Günlük Eğim (Spread_20D)│
                     │  • TIPS Reel Faizler (DFII10) & Histeresis    │
                     │  • Likidite Dinamikleri (WALCL - RRP - TGA)   │
                     │  • Çoklu Ajan Konsensüsü (Ajan 1, 2, 3)      │
                     │  • T-0 Anlık Stres Devre Kesicisi (VIX/OAS)   │
                     └───────────────────────┬───────────────────────┘
                                             │ Atomik JSON Kapısı
                                             ▼
                               [ shared/macro_bias_gate.json ]
                            (Yön Kısıtı: LONG_ONLY / SHORT_ONLY,
                             Risk Çarpanı: 0.25x - 1.0x, VETO)
                                             │
                                             ▼
                     ┌───────────────────────────────────────────────┐
                     │  2. MİKRO TETİKLEYİCİ MOTORU (Python)         │
                     │  • [SFP Motoru]: Swing High/Low Likidite Avı  │
                     │  • [Hacim Anomalisi]: Z-Score, Spike & Emilim │
                     │  • [ORB Seans Motoru]: Londra & NY Açılışları │
                     │  • [Makro Geçit Kalkanı]: Ters Yönlü VETO    │
                     └───────────────────────┬───────────────────────┘
                                             │
                                             ▼
                     [ KUSURSUZ İŞLEM BİLDİRİMİ & GÖRSEL KANIT ]
                     • Telegram Detaylı Checklist Kartı
                     • Matplotlib Canlı Grafik Kanıtı (Giriş, SL, TP)
                     • Makro Rejim Gerekçesi & Dinamik Risk Çarpanı
```

---

## 🚀 Başlatma

Sistemi masaüstünden veya proje kök dizininden tek tıkla çalıştırabilirsiniz:

```bash
# Masaüstündeki kısayol:
BEGONYA00_BASLAT.bat

# Veya terminalden:
python orchestrator/start_begonya.py
```

### Tekil Tarama / Test Seçenekleri
```bash
# Telegram kartı ve grafik üretim testi:
python -m sfp_orb_engine.run_engine --test-card

# Tüm sembol evrenini anlık olarak tek seferlik tarama:
python -m sfp_orb_engine.run_engine --scan-once
```
