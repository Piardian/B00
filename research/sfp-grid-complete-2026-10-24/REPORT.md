# SFP: tamamlanan kotasyonlar ve fiyat-adımı karşılaştırması

**Bu çalışma tam sistem kâr backtesti değildir.** Sabit57aday, aynı240dk limit süresi ve dolumdan60dk sonraki fiyat hareketi; ilk stop/TP yönetimi uygulanmaz. Stop aşan markout işlem kârı sayılamaz.

| Dönem | Model | Senaryo | Dolum | Dolmayan | Belirsiz | Ortalama maliyetli markout R | Stop aşımı |
|---|---|---|---:|---:|---:|---:|---:|
| DEVELOPMENT | NOMINAL | OBSERVED | 24 | 9 | 3 | 0.034811 | 8 |
| DEVELOPMENT | NOMINAL | STRESS_1_5X | 25 | 9 | 2 | -0.069154 | 9 |
| DEVELOPMENT | NOMINAL | STRESS_FLOOR | 25 | 9 | 2 | -0.084939 | 10 |
| DEVELOPMENT | ALIGNED | OBSERVED | 24 | 9 | 3 | 0.034312 | 8 |
| DEVELOPMENT | ALIGNED | STRESS_1_5X | 25 | 9 | 2 | -0.068763 | 9 |
| DEVELOPMENT | ALIGNED | STRESS_FLOOR | 25 | 9 | 2 | -0.087833 | 10 |
| VALIDATION | NOMINAL | OBSERVED | 11 | 8 | 2 | -0.282088 | 8 |
| VALIDATION | NOMINAL | STRESS_1_5X | 11 | 8 | 2 | -0.310246 | 8 |
| VALIDATION | NOMINAL | STRESS_FLOOR | 11 | 8 | 2 | -0.313251 | 9 |
| VALIDATION | ALIGNED | OBSERVED | 10 | 8 | 3 | -0.593833 | 8 |
| VALIDATION | ALIGNED | STRESS_1_5X | 10 | 8 | 3 | -0.620437 | 8 |
| VALIDATION | ALIGNED | STRESS_FLOOR | 10 | 8 | 3 | -0.613034 | 9 |

Komisyon ve kayma önceki deneydeki sabit varsayımlar. Spread arşivden gözlenir;1.5x ve ek spread tabanı senaryoları aynıdır. Fiyat adımı2026 metadata kaydıdır;2025 emir kabulü doğrulanmış değildir. Yeni fiyatlar için dolum ve maliyetler yeniden hesaplandı; eski getiriler taşınmadı.

Önceki çözülmüş84 senaryo kaydının84 tanesi yeni nominal replay ile birebir eşleşti. Tüm yeni dosyalar hash ve saat hizası kontrolünden geçirildi. Eksik/bozuk veri sıfır getiri sayılmadı.

Karar: Edge kanıtlanmadı; ayrıntılı örnek/kapsam/istikrar koşulları decision.json içinde. Daha fazla işlem tek başına başarı değil.

Az sinyalin nedenleri funnel.json ve FUNNEL.md içinde ayrı incelenir. Üretim kodu/süreç/emirler değiştirilmedi. Ücretli API kullanılmadı.
