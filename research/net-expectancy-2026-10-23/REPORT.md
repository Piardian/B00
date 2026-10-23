# Net beklenti araştırması — ilk kontrollü deneyler

23 Ekim 2026. TP/SL ve maliyet sorusu için önceki tam ay testinin dondurulmuş kaynakları kullanıldı. Çalışma sırasında ana klasörde London ORB/seans kodları değiştiği için farklı sürümlü ilk koşular karşılaştırmadan çıkarıldı. Bu rapor yeni London kodunun performans raporu değildir.

**Maliyet sonrası pozitif ve doğrulanmış bir aday henüz yok.**

| Deney | Ay | İşlem | Net R, 1.5x paper maliyet |
|---|---|---:|---:|
| Referans | 2025-01 | 3 | -2.293333 |
| Referans | 2025-11 | 1 | -0.590653 |
| TP2 → 3R | 2025-01 | 3 | -2.293333 |
| TP2 → 3R | 2025-11 | 1 | -0.590653 |
| Yapısal tampon yarım | 2025-01 | 3 | -2.478096 |
| Yapısal tampon yarım | 2025-11 | 1 | -0.631943 |
| Spread/stop ≤ %25 | 2025-01 | 0 | +0.000000 |
| Spread/stop ≤ %25 | 2025-11 | 0 | +0.000000 |
| Hedef/fiyat adımı tutarlılığı | 2025-01 | 3 | -2.293333 |
| Hedef/fiyat adımı tutarlılığı | 2025-11 | 1 | -0.590653 |

Sıfır işlem, kâr veya başarılı filtre kanıtı sayılmadı. Eksik ayın getirisi sıfır yazılmadı. Her deney önceden ilan edildi; sonuç gördükten sonra parametre araması yapılmadı.

## Teşhis ve somut çıktı

- TP2 uzatma tek başına bu ayları iyileştirmedi; işlemler hedefe varmadan çıkıyor. Stop tamponunu azaltmak, Ocak sonucunu kötüleştirdi. Mevcut yapı içinde stopu daraltmak daha az stop garantisi vermiyor.
- Dar stop deneyi entry ve fiyat hedeflerini korur; yalnız mevcut yapının dışındaki tamponu yarıya indirir. Gider R, daralan stopa ters orantılı artırılarak aynı parasal masrafın yapay biçimde ucuzlaması önlenir.
- 55 ham adayın 24ünde TP minimumu ile yuvarlanmış fiyatlar uyuşmuyor: 23 TP1, 1 TP2 kontrolünden geçemiyor. Örneğin EURUSD SHORT entry=1.0307, stop=1.0323, TP1=1.0288: hedef 1.2R yerine 1.1875R.
- Araştırma tarafındaki price_rules.py giriş ve stopu koruyarak hedefleri son risk mesafesine göre hesaplar ve fiyat adımında dışa yuvarlar. Bu sayede seviye/trend kontrolünden geçen aday 15ten 25e çıkar. Bunlar ek işlem veya ek kâr değildir; makro, haber, dolum ve risk kapıları ayrıca çalışmalıdır.
- Altının referans indeksinde 1040 uygun tarama penceresine rağmen aday yok; burada TP/SL ayarı denenebilecek işlem örneklemi oluşmamış.

## Sınırlar ve sonraki çalışma

Birinci teknik öncelik hedef/stop fiyat hesaplarının broker hassasiyeti ve minimum R/R ile tutarlılığıdır. Hesaplama düzeltmesi ayrı dosyada hazır ve altı test geçti; üretime bağlanmadı. Hedef tutarlılığı hipotezi tabloda ayrıca asıl motorla denendi; aday sayısı artışı doğrudan kazanç sayılmadı. Sonraki doğrulama daha geniş ve görülmemiş örneklemde, gerçek hesap maliyetleriyle yapılmalıdır. Yeni entry mekanizması oluşturulmadı, makro veto kaldırılmadı.

İki ay daha önce görülmüş araştırma verisidir; örneklem dışı doğrulama değildir. Paper maliyetinin sabit R gideri ve fiyat oranlı spreadi gerçek hesap komisyonu, swap ve kayma doğrulaması değildir. [Güncel resmi maliyet açıklaması](https://the5ers.com/faqs/what-are-the-spreads-and-commissions/) Forex ve metal giderlerini ayrı tanımlar; güncel tarife 2025 hesabının tarifesi yerine geçirilmedi.

Önemli kalibrasyon farkı: paper Forex spread eşiği entry×0.0002dir. EURUSD 1.03 örneğinde 2.06 pip, 1.5x stresle 3.09 pip eder. Resmi sayfa normal koşullarda majörlerde 0.2–0.9 pip aralığını belirtir. Bu aralık her saat veya 2025 için gerçek spread kaydı değildir. Stres modelinde zarar görülmesi, gerçek hesap koşullarında avantajın kesin yokluğunu kanıtlamaz; sonraki öncelik bid/ask ve hesap giderlerini kalibre etmektir.

Ücretli kullanım açılmadı. Bu deneyler canlı sürece uygulanmadı. protokol.json, summary.json ve candidate_quality_diagnostics.json tüm sonuçları ve hesaplama izini içerir.
