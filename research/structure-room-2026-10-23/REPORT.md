# Begonya00 geliştirme: yapısal giriş, maliyet gözlemi ve hedef alanı

## Tamamlanan geliştirmeler

1. **Araştırma akışına bağlı maliyet/alan gözlemi:** `features.py`, her referans kararında ve hazır M1 girişinde maliyet bütçesini ve o anda bilinen H1 karşı seviyesini hesaplıyor. `cost_room_observations.jsonl` içinde 180 kayıt oluştu. Bu testte ask sentetik; her kayıtta bu açıkça işaretlidir. Gerçek tarihsel bid/ask kaydı üretildiği iddia edilmez.
2. **Yeni giriş ve yapısal stop prototipi:** orijinal limit bölgesine temas ve M1 tepki kapanışı; daha sonraki M1 mumunun tepki tepe/dibini yönünde aşan kapanışı; ancak sonraki mumun açılışında piyasa girişi. Long ask+0.2pip, short bid−0.2pip. Yeni stop tepki mumunun dışında bir tick; short için ask eşdeğeri kullanılır. Teyit öncesinde yapı kırılırsa henüz emir bulunmadığından kurulum iptal olur. Giriş mumunun sonraki tepe/dibi sinyali seçemez.
3. **Hedef alanı ölçümü:** son 100 tamamlanmış H1 içinde iki sol/iki sağ mumla teyit edilen en yakın karşı tepe/dip. Beş mum penceresi saat bakımından kesintisiz olmalı. TP1, seviyeden en az bir tick önce olmalı. Seviye yoksa alan sınırsız sayılmaz: UNKNOWN. Bu mekanik ölçüm mevcut botun swing yorumunun aynısı veya seviyenin kesin çalışacağı iddiası değildir.
4. **Gerçek teklif ihracına uygun salt gözlem adaptörü:** `quote_journal.py`, dışarıdan verilen bid/ask, saat ve kaynak etiketini kaydeder; SQLite kayıtları tekrar işlendiğinde çoğalmaz. Eksik teklif UNPRICED, eksik H1 UNKNOWN, eski/gelecek teklif UNPRICED. Komisyon/kayma yapılandırılmış varsayım olarak kalır. Emir, canlı veto ve ağ erişimi içermez. Çalışan botun teklif akışına bağlanmadı.

## Deney ve sınırlar

Önceki çalışmanın değişmeden alınan 33 ilk günlük kurulumu: Ocak 2025'te 23, Kasım'da 10; altı majör parite evreni. Haziran adayı bu ihracatta yok. Yeni aylık dedektör taraması, altın, makro/haber, ortak risk veya tam bot backtesti değildir. Ocak/Kasım daha önce görülmüş dönemler; gerçek OOS yok.

Birinci aşama, sonuçlar alınmadan `protocol.json` ile kilitlendi: beş sabit varyant, 0.2/0.5/0.9/1.5 pip spread, komisyon 100 bin birime toplam 4USD, piyasa giriş/çıkışında ayrı 0.2pip kayma. Referans limit girişinde giriş kayması yok. Sentetik ask, tarihsel broker maliyetinin doğrulaması değildir. Ücretler R için kotasyon para birimine çevrilir; hesap getirisi hesaplanmaz.

Maliyet kontrolünün önceden sabitlenen üst sınırı **0.20R tahmini bütçe**. Bütçe spread+komisyon+piyasa kaymasıdır; icra fiyatlarına işlenen maliyet PNL'den tekrar çıkarılmaz. Gözlem eşiği optimize edilmedi ve canlıya uygulanmadı. Günlük ilk kurulum seçimi korunur; elenen kurulumun yerine o gün yeni kazançlı aday aranmaz.

Ortak çıkış: TP1'de yarı kapatma, BE/trailing, dolum mumunda TP yasağı, stop önceliği, olumsuz dolum tepkisinde ücretli piyasa çıkışı, London16:30 kapanış. Yeni girişlerde hedefler gerçek yeni riskten en az1.2R/2R ve tick dışına yuvarlanır. Stop üzerinden olumsuz gap daha kötü fiyatla muhasebeleştirilir. Eksik dakika net sonuç olarak doldurulmaz.

## Sonuçlar

| Varyant | 0.5pip dolum | 0.5pip netR | 1.5pip dolum | 1.5pip netR |
|---|---:|---:|---:|---:|
| Önceki referans, değişmeden | 31 | +5.190 | 30 | −1.352 |
| Referans + H1 hedef alanı | 9 | +0.377 | 9 | −1.775 |
| Yeni M1 giriş + M1 yapısal stop | 14 | −3.786 | 9 | −3.235 |
| Yeni M1 + maliyet bütçesi | 3 | −0.738 | 0 | 0.000 |
| Yeni M1 + maliyet + hedef alanı | 1 | −0.217 | 0 | 0.000 |

Sıfır dolum başarı değildir. Referans ana sonucu önceki +5.190387221887223R ile sayısal olarak eşleşti; fark yalnız yeni filtre/giriş kollarındadır. Referansın Kasım sonucu −2.487R. Alan filtresinin Kasım sonucu iki dolumla −0.463R. Yeni M1 kolunun Kasım sonucu beş dolumla −4.746R. Dolayısıyla yeni kolların hiçbiri hem dönem hem maliyet dayanıklılığı koşulunu karşılamadı.

Yeni M1 ana senaryosunda, aynı 14 hazır girişin orijinal stop mesafesi medyanı 10pip iken yeni stop mesafesi 4.15pip. Yeni/eski risk mesafesi oranının medyanı %42. Maliyet bütçesinin medyanı **0.310R**. Stopu küçültmek, aynı komisyon ve spreadi risk birimi cinsinden büyütüyor. 0.20R kontrolü 14 hazır girişten 11'ini eliyor; geriye kalan üç dolum da pozitif değil.

## Ek kontrol: stopu korumak çözüm mü?

İlk aşama görüldükten sonra ayrı `stop_control_protocol.json` oluşturuldu. Bu ek kontrol önceki aşamadan bağımsız doğrulama değildir. Aynı M1 teyit uygunluğu ve giriş fiyat/zamanları korunup sadece stop eski ORB stopuna alınır; hedefler yeni entry-stop riskinden yeniden hesaplanır. Önceki M1 yapı bozulması nedeniyle emir oluşmayan kurulumlar bu kontrolde de geri getirilmez.

| Ek kontrol | 0.5pip dolum | 0.5pip netR | 1.5pip dolum | 1.5pip netR |
|---|---:|---:|---:|---:|
| M1 giriş, orijinal stop | 14 | −2.800 | 9 | −5.164 |
| Aynısı + maliyet bütçesi | 14 | −2.800 | 6 | −3.288 |

Eski stopu korumak ana senaryoda daha az negatif bir R toplamı verdi; pozitif beklenti sağlamadı. Stop değişince risk ölçeği ve türetilmiş hedefler de değişir; aradaki R farkı aynı lotla parasal kâr artışı değildir. Bu örneklemde geç teyitle girişin problemini yalnız stop genişliğiyle çözemedik.

## Kullanılabilir sonuç ve sonraki geliştirme yönü

**Bu tur kârlılığı artıran yeni kural bulmadı; maliyet ve uygulanabilirlik ölçümünü geliştirdi.** Dar stoplu M1 kolunu ve katı H1 alan filtresini varsayılan canlı kural yapmıyoruz. H1 filtresi burada kazançlı fırsatları da eledi; piyasa seviyesinin varlığı tek başına kullanışlı veto olmadı. Bu sonuçlara bakıp eşiği biraz değiştirerek aynı aylarda yeşil tablo aramıyoruz.

Bir sonraki anlamlı iş, gözlem adaptörüne gerçek teklif/kapanış kayıtları sağlamak ve aynı kuralları yeni dönemde ölçmek. İhtiyaç duyulan alanlar artık açık ve araç hazır: karar zamanı, teklif kaynağı/yaşı, bid/ask, stop mesafesi, komisyon varsayımı, TP alanı ve kurulum kimliği. Gerçekleşmiş kayma/komisyon için ayrıca dolum/çıkış kayıtları gerekir; bu adaptör onları üretmez. Bunlar olmadan gerçek broker maliyeti çözüldü denemez.

Stratejik araştırma önceliği, daha fazla teyit katmak yerine **hangi açılış bağlamında mevcut erken limit girişinin işe yaradığını yeni veride ölçmek** olmalı. Ocak/Kasım farkı gözlemidir; sebebi henüz kanıtlanmış rejim filtresi değildir. Yeni veri üzerinde önceden sabitlenmiş bağlamlar değerlendirilmeli; bu aylardaki kazanan parite/günlerden sonradan filtre türetilmemeli.

## Kullanım ve doğrulama

Araştırma tekrar ölçümü:

```
python research/structure-room-2026-10-23/study.py verify
python research/structure-room-2026-10-23/study.py run
python research/structure-room-2026-10-23/stop_control.py run
```

Teklif adaptörü; girdi JSONL satırında `signal`, saat dilimli `as_of`, isteğe bağlı `quote:{bid,ask,quote_at,source}` ve H1 kayıtları bulunur. Veri kaynağını etiketlemek çağıranın sorumluluğundadır; broker kaynağı bağımsız sertifikalanmaz. Örnek kullanım (dosya yolları kullanıcı veri ihracına göre seçilir):

```
python research/structure-room-2026-10-23/quote_journal.py --input paper_quotes.jsonl --db data/research_quote_context.sqlite --commission-usd 4 --exit-slip-pips 0.2
```

**19 yeni test geçti:** teyit kapanışı/sonraki açılış, gelecekteki entry mumunun seçimi değiştirememesi, yapı bozulması, eksik dakika, stop önceliği, piyasa giriş fiyatı, H1 pivot teyidi/gelecek veri ayrımı, hedef alanı, iki taraf piyasa kayması, short ask stopu, eksik/eski/gelecek teklifler, zaman dilimi, idempotent kayıt, geçersiz maliyet/kontrat.

Birinci aşamada 660, ek kontrolde 264 kurulum/senaryo/varyant kaydı var: toplam924; bu sayı bağımsız işlem sayısı değildir. Hiçbir replay UNRESOLVED kalmadı. Referans eşitliği ve dondurulmuş dosya hashleri doğrulandı. Çalışan bot, canlı emir ayarları, üretim modülleri değiştirilmedi. Ücretli API veya otomatik devam görevi yok.
