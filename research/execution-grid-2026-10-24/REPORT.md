# Araştırma fiyat-adımı adaptörü

Mevcut broker fiyat adımlarına göre57 SFP adayının tamamı için sayısal olarak uyumlu giriş/stop/hedef önerisi üretildi. Bu bir kâr backtesti veya kabul edilmiş broker emri değildir.

- Alış girişi yukarı, satış girişi aşağı yuvarlanır; giriş fiyatında olumlu iyileşme yazılmaz.
- Stop yapısal seviyeden dışarı yuvarlanır. Yeni risk mesafesi yeniden hesaplanır.
- Hedefler yeni riske göre en az1.2R/2R olacak şekilde dışarı yuvarlanır.
- Eski dolumlar, yön puanları ve kârlar bu önerilere taşınmadı. Değişen fiyatlar dolumu ve çıkışı değiştirebilir; yeni kronolojik replay gerekir.
- Fiyat adımları2026 broker metadata'sıdır. Tarihsel emir kabulü, minimum stop mesafesi ve diğer broker kısıtları doğrulanmış değildir.

10 birim testi geçti;57 önerinin tüm seviyeleri ve minimum RR'si ayrıca doğrulandı. Üretim kodu ve eski araştırma sonuçları değiştirilmedi. Sonraki iş yeni bir protokolle kotasyon kapsamını tamamlayıp bu seviyeleri baştan oynatmaktır. Bu düzeltme tek başına edge üretildiği anlamına gelmez.
