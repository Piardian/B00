# Begonya00: giriş yeniliği ve maliyet araştırması

## Karar

**Proje için umut veren bir araştırma kolu var; doğrulanmış edge ve canlıya geçiş yok.** Yeni, açıkça ayrılmış London ORB deneyinde temel limit giriş, orta spread varsayımında pozitif kaldı. Fakat Kasım zararlı, yüksek spread senaryosu zararlı ve kâr az sayıda işleme yoğunlaşıyor. Ek teyit genel örneklemde çözüm olmadı.

Bu çalışma yalnız sonuç tablosu üretmedi: üç giriş politikası için nedensel, bid/ask farkını hesaba katan araştırma motoru ve gerçek teklifleri değerlendirebilen salt gözlem maliyet modülü yazıldı. Canlı motor, emirler ve çalışan süreçler değiştirilmedi. API kullanımı yok; yeni ücret yok.

## Deneyin sınırı

- Kaynak: mevcut opening-only aday ihracındaki 36 kayıt; hedefler araştırma kuralıyla düzeltildikten sonra her parite/London gününde ilk kurulum seçildi: 33 kurulum. Ocak 23, Kasım 10. Altı majör parite tarama evreni; altın yok.
- Haziran fiyat verisi var, fakat alınan aday ihracında Haziran adayı yok. **Haziran sonucu, üçüncü ay doğrulaması veya başarılı sıfır işlem filtresi iddiası yok.** Bu yeni çalışma tam aylık dedektör taraması yapmadı; mevcut adayların giriş/çıkış alternatiflerini sınadı.
- Giriş ve ilk yapısal stop korundu. Hedefler gerçek entry-stop mesafesine göre dışarı yuvarlandı: en az TP1=1.2R, TP2=2R. Bu, geçmişte RR nedeniyle reddedilen bazı adayları deneyin içine alır. Üretime uygulanmadı.
- Bütün politikalarda dolum sonrası olumsuz M1 tepki çıkışı, stop önceliği, dolum mumunda TP yasağı, TP1'de yarım kapatma/BE ve sonraki mumlarda trailing ortak.
- **Yeni ortak deney kuralı:** pozisyon London 16:30 M1 açılışında kapanır; böylece gecelik swap varsayımı yapılmaz. Bu mevcut botun çıkışıyla birebir aynı değildir. Bekleyen emir London 12:00 veya dört saatlik sürenin erken olanında biter.
- Makro/haber, SFP önceliği, ortak risk ve eşzamanlı portföy icrası yok. R, ilk fiyat riskine göre normalize edilmiş bağımsız kurulum sonucudur; hesap getirisi değildir. Önceki −2.837R paper tabloyla değişimin yalnız girişten/yuvarlamadan kaynaklandığı söylenemez: aday seti, maliyet ve gün sonu kuralı da farklıdır.
- Ocak ve Kasım daha önce görülmüş dönemlerdir. Kasım burada geriye dönük dönem ayrımıdır; gerçek OOS değildir.

`protocol.json` sonuçlardan önce oluşturuldu; motor, kurallar, adaylar ve altı M1 dosyası SHA256 ile kilitlendi. Sonuçlar çalışma sırasında üretim modüllerini içe aktarmaz.

## Maliyet ve icra

M1 bid verisine sabit varsayımsal ask spreadi eklendi. Long limit için ask, short limit için bid girişin bir tick ötesine geçmeli. Long çıkış bid, short çıkış ask üzerinden; stop ve piyasa çıkışına 0.2 pip olumsuz kayma uygulanır. Limit fiyat iyileşmesi sayılmaz. Dolum mumunda hem stop hem hedef varsa stop kazanır. Eksik dakika varsa sonuç UNRESOLVED olur ve net kâr atanmaz. Bu koşullarda 396 kurulum/senaryo replay'inin hiçbirinde belirsiz son kalmadı.

Spread senaryoları 0.2 / 0.5 / 0.9 / 1.5 pip; önceden belirlenen ana senaryo 0.5 pip. Komisyon 100 bin birim kontrat için toplam 4 USD; açılış/kapanış ve kısmi çıkışlar ayrı kaydedilir. USD bazlı paritelerde komisyon o andaki fiyattan kotasyon para birimine çevrilir. Spread icra fiyatlarına dahildir, ayrıca tekrar çıkarılmaz. R kotasyon fiyat riski bazındadır; hesap para birimine çevrilmiş equity değildir.

[The5ers'in güncel resmi tarifesi](https://the5ers.com/faqs/what-are-the-spreads-and-commissions/) normal majör spreadi 0.2–0.9 pip ve Forex komisyonunu round trip 4 USD/lot olarak veriyor. **Bu, 2025'teki gerçek hesap spread/komisyonunun doğrulaması değildir.** Sabit spread tarihsel haber genişlemesi veya broker tick icrasını temsil etmez. Artan spread farklı dakikada dolum/stop üretebildiği için sonuçlar monoton olmak zorunda değildir; en iyi spread senaryosu seçilmedi.

## Sonuçlar

Tüm ilk günlük kurulumlar; net R, komisyon ve fiyat içindeki spread/kayma sonrası:

| Giriş politikası | 0.2 pip | **0.5 pip ana** | 0.9 pip | 1.5 pip stres |
|---|---:|---:|---:|---:|
| Temel pasif limit | +1.934 | **+5.190** | +2.188 | −1.352 |
| M1 tepki kapanışı, sonraki yeniden temas | +1.497 | **−2.234** | +0.042 | −0.388 |
| Tepki, sonraki M1 kırılım kapanışı, sonraki yeniden temas | −1.341 | **−3.007** | −2.980 | −1.986 |

Teyit mumunda geriye dönük dolum yapılmaz. Her üç politikada aynı günlük kurulum seçilir; teyit beklerken emir oluşmasa da o gün başka adayla değiştirilmez.

Ana senaryo ayrımı:

| Politika | Dolum | Ocak net R | Kasım net R | PF |
|---|---:|---:|---:|---:|
| Temel | 31 | +7.677 | −2.487 | 1.60 |
| Tepki + yeniden temas | 24 | +0.941 | −3.175 | 0.75 |
| Kırılım + yeniden temas | 24 | +0.307 | −3.314 | 0.66 |

Temelde 14 olumsuz tepki çıkışı toplam −2.210R. Teyit alternatiflerinde bu çıkışların toplamı −2.603R ve −3.490R: ilave teyit otomatik olarak kötü dolumu çözmüyor. En büyük dört kazanç çıkarıldığında temel toplam +5.190R'den −1.217R'ye iner. Bu bir istatistiksel test değildir; kâr yoğunlaşması teşhisidir.

Önceden tanımlanan HTF yön uyumu + motor seans saatine uyan ikincil grupta 9 kurulum var. Kırılım/yeniden temas kolu 7 dolumla bütün spreadlerde +2.607 / +1.229 / +1.141 / +1.080R üretti. **Tamamı Ocak; Kasım/Haziran ölçümü yok, yalnız iki kazanan dolum var.** Bu küçük gruptan doğrulanmış filtre veya edge çıkarılamaz. Aynı günlük kurulum kümesinin alt grubudur; ilk uygun HTF adayını yeniden arayan farklı bir stratejiyle karıştırılmamalıdır.

## Çözüm ve geliştirme sırası

Çalışma sonunda aynı checkout'ta paralel hazırlanmış `../london-edge-development-2026-10-23/SONUC.md` de okundu; hesapları bu çalışmada tekrar çalıştırılmadı. Orada mevcut paper modelindeki düzeltilmiş referans −12.16R, tepki çıkışını kaldırma −8.11R ve başka bir M1 teyit/giriş tanımı −8.29R; ayrı klasik ORB kontrolü de negatif raporlanıyor. Buradaki +5.190R ile birleştirilemez: maliyet, giriş/çıkış sözleşmeleri farklıdır. Bu uyuşmazlık maliyet/yaşam döngüsü varsayımına hassasiyeti gösterir; olumlu modeli seçerek proje edge'i ilan etmeyi desteklemez.

1. **Maliyeti ölçerek giriş kalitesini değerlendirmek.** `cost_observer.py` gerçek bid/ask ve zaman damgasını alır; spread/stop oranı, komisyon bütçesi, ağırlıklı hedef ve basit başabaş kazanma oranını verir. Eski/gelecek teklif UNPRICED olur. Emir göndermez, eşik seçmez, otomatik veto uygulamaz. Bir sonraki çalışma bu kayıtları gerçek veya ayrı paper aday akışına bağlamalıdır. Maliyet eşiğini eski kazançları ayıklayarak seçmekten kaçınılmalıdır.
2. **Hedef geometrisini düzeltmek, sonra hedefin piyasa içinde ulaşılabilirliğini sınamak.** Dışarı yuvarlama prototipi burada kullanıldı. Ancak TP1'in yarısı ve TP2'nin yarısı 1.2/2R hedeflerde toplam 1.6R brüt verir; iki hedef de gerçekleşse 2R kazanılmaz. Daha uzak TP yerine giriş anında bilinen karşı seviye/günlük kalan hareket alanı kaydedilmeli. Bu yeni bir test hipotezidir; henüz faydası ölçülmedi. Üretim hedeflerini şimdi değiştirmek için kanıt yok.
3. **Genel bir teyit eklemek yerine koşullu giriş dalını izlemek.** Tüm örneklemde iki teyit başarısız; bunları varsayılan giriş yapmıyoruz. HTF uyumlu kırılım/yeniden temas yalnız küçük bir aday araştırma kolu olarak saklanmalı. Aynı sabit tanımla yeni dönemde değerlendirilmeden filtre genişletilmemeli.
4. **Stopu fiyat yapısından koparmadan daha iyi giriş aramak.** Önceki stop buffer küçültme deneyi kötüleşmişti. Bu çalışmanın iki yeniden temas mekanizması da genelde çözüm olmadı. Sonraki ayrı deney için teyit edilen M1 yapısına göre yeni giriş/stop çifti düşünülebilir; bu orijinal sistem backtesti diye adlandırılamaz. Spread ve minimum stop sınırı dahil edilmeden yüksek RR başarı sayılmamalı.

Yeni geliştirmede ölçülecek kayıtlar: kurulum zamanı, emir zamanı, bid/ask yaşı, yapısal stop, ağırlıklı hedef, girişte bilinen karşı seviye, dolum, kısmi çıkışlar ve toplam gerçek maliyet. Böylece işlem fırsatının mı zayıf olduğu, maliyetin mi tükettiği veya çıkışın mı iyi hareketi erken kestiği ayrılabilir.

Sonraki doğrulama aynı kurallarla zaman bakımından ayrılmış yeni veride yapılmalı; negatif/işlemsiz dönemler dahil tutulmalı. Şu an hiçbir dal canlıya geçiş koşullarını karşılamıyor. Bunun anlamı “proje hiçbir şekilde çalışamaz” değil: orta maliyette pozitif bir araştırma temeli var, fakat aylar arası dayanıklılık ve maliyet toleransı çözülmüş değil.

## Dosyalar ve doğrulama

- `quote_engine.py`: bağımsız giriş/icra prototipi.
- `cost_observer.py`: salt gözlem maliyet hesabı; canlı veri bağlantısı henüz yok.
- `study.py`, `protocol.json`, `candidates_frozen.json`: kilitli karşılaştırma.
- `outcomes.json`, `summary.json`, `selected_setups.json`, `diagnostics.json`: işlem/senaryo ve teşhis çıktıları.
- `diagnose.py`: sonuç sonrası yoğunlaşma/kapsam kontrolü; aday seçiminde kullanılmadı.
- **15 test geçti:** bid/ask dolumu, teyit sonrası nedensellik, stop önceliği, zarar dolum maliyeti, kısmi komisyon, eksik dakika, son giriş saati, gün sonu çıkışı, short ask stopu, eski/gelecek teklifler ve geçersiz maliyet/quote.

Tekrar ölçüm: `python research/entry-innovation-2026-10-23/study.py run`. Girdi hash değişirse durur; kuralı değiştirip aynı dondurulmuş sonuç gibi çalıştıramaz. Test komutu: `python -m pytest research/entry-innovation-2026-10-23/test_quote_engine.py research/entry-innovation-2026-10-23/test_cost_observer.py -q --basetemp=data/test_tmp_entry_innovation_b` (yeni çalıştırmada yeni bir basetemp adı kullanın).
