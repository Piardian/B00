# London ORB: girişten sonraki fiyat yolu denetimi

**Karar: çoğu stop işleminde korunacak büyük bir kâr oluşmamış. Basit bant teması da kazananı kaybedenden ayırmıyor. Yeni bir çıkış kuralının edge sağladığı gösterilmedi.**

Önceden görülmüş Şubat, Mart, Nisan, Mayıs, Eylül ve Ekim 2025; altı majör parite. Sabit ana grup RVOL ≥ 1, ana maliyet 1,5x. Hiçbir işlem sonucu, stop/hedef, gün veya parite değiştirilmedi. Bu, strateji testi değil geriye dönük betimleyici teşhistir.

## Ana grubun 254 işlemi (1,5x)

| Sonuç | İşlem |
|---|---:|
| 2R fiyat hedefine ulaşan | 78 |
| Gün sonunda net pozitif kapanan | 15 |
| Stop: öncesinde +0,5R nete ulaşmayan | 99 |
| Stop: öncesinde +0,5R nete ulaşan | 57 |
| Gün sonunda net pozitif olmayan | 5 |

156 stopun **99’u (%63.5)** +0,5R net kâr görmedi. Stop işlemlerinde medyan en yüksek geçici net kâr yalnız **0.319R**. Sadece **28/156** stop öncesinde +1R nete ulaştı. Bu bulgu, sorunu yalnız TP1/BE ekleyerek çözebileceğimizi desteklemez; böyle bir kuralın kazananları ne kadar keseceği ayrıca nedensel replay gerektirir.

| Grup | İşlem | Net R | Stop sayısı | Stop öncesi +0,5R net | Stop öncesi +1R net |
|---|---:|---:|---:|---:|---:|
| RVOL ≥ 1, 1,5x | 254 | -5.37 | 156 | 57 | 28 |
| Hacim filtresiz, 1,5x | 701 | -96.60 | 451 | 164 | 75 |
| RVOL ≥ 1, Gözlenen 1x | 254 | +8.78 | 153 | 58 | 29 |
| Hacim filtresiz, Gözlenen 1x | 701 | -66.86 | 447 | 179 | 81 |

## Stopa gidiş süresi

| Girişten sonra | Kümülatif stop |
|---|---:|
| ≤ 5 dakika | 6 / 156 |
| ≤ 15 dakika | 32 / 156 |
| ≤ 30 dakika | 54 / 156 |
| ≤ 60 dakika | 81 / 156 |

Stop medyan süresi **56.0 dakika**; stopların yalnız 6’sı ilk 5 dakika içinde. Hepsini anlık sahte kırılım diye adlandırmak doğru olmaz.

## Retest teması seçici mi?

254 işlemin tamamında çıkıştan önce fiyat kırılan BID bandının içine en az bir kez döndü. Kazanan 93/93 ve kaybeden 161/161 işlemde bu dönüş var. Bu olay, tamamlanmış mumla teyitli retest değildir; tek ticklik içeri dönüşü de sayar. Sonuç sonrası açıklayıcı süre kırılımı:

| Grup | İşlem | İlk içeri dönüş medyanı (saniye) | İlk 5 saniyede içeri dönüş |
|---|---:|---:|---:|
| Tümü | 254 | 0.317 | 197 |
| Kazananlar | 93 | 0.279 | 74 |
| Kaybedenler | 161 | 0.370 | 123 |

Sadece temas beklemek için burada ayırt edici kanıt çıkmadı. Bu raporun protokolündeki basit retest gerekçesi kapısı karşılanmadı. Ayrı `london-confirmed-retest-2026-10-24` denemesi, bu bulguyla desteklendiği iddia edilen bir doğrulama değildir: kullanıcının izin verdiği sınırlı araştırma kapsamında, mum kapanışıyla anlamlı kırılımı tek tick temasından ayıran tek bir **keşif hipotezi** olarak ayrıca sabitlenmiştir. Eski negatif M1 sonuçları geçerliliğini korur.

## Stop sonrasını kâr saymadık

Stop olan 156 işlemin 32 tanesinde fiyat aynı gün daha sonra orijinal hedef koşuluna ulaştı. Bu, stopu yok sayarak elde edilebilecek kâr değildir: aradaki risk ve kayıp yolu korunur. Bu sayıdan stop genişletme veya stop kaldırma kararı çıkarılamaz.

## Hesaplama ve doğrulama

- MFE/MAE: girişten **gerçek çıkışa kadar**, o anda pozisyon kapatılsa oluşacak BID/ASK, varsayılan kayma ve tam tur komisyon sonrası net R uçları. Giriş tickindeki anlık geri kapama maliyeti dahil. Hedef çıkış tickinde olumlu gap kârı verilmez; kaydedilmiş hedef dolumu kullanılır.
- MFE geçmiş yolun en iyi noktasıdır; önceden bilinen sinyal veya o fiyattan otomatik çıkış garantisi değildir. +0,5R eşiği optimizasyonla seçilmedi. Net eşikler, nominal 2R fiyat hedefiyle aynı şey değildir.
- 701 ayrı quote dosyası üzerinde 1x ve 1,5x toplam 1.402 kapalı replay’in giriş/çıkış zamanı, fiyatı, risk, hedef, komisyon ve net sonucu eski motorla birebir eşleşti. Aynı milisaniyedeki kayıt sırası korundu. Kaynak ve kullanılan quote hashleri başta/sonda doğrulandı.
- Altı odaklı test geçti: kısa ASK hedefi, hedef gap sınırı, aynı zaman damgası sırası, stop sonrasının ayrılması, komisyon ve referans değişiminin yakalanması.
- MT5/veri indirme veya emir API çağrısı yok. Üretim kodu ve çalışan süreçler değiştirilmedi. R toplamları hesap getirisi değildir.

Dosyalar: `protocol_frozen.json`, `paths.json`, `paths.csv`, `results.json`, `integrity_check.json`; kaynaklar `frozen_sources/` altında. Sonuç sonrası retest zaman kırılımı, temel protokoldeki kategorilere ek betimlemedir ve filtre olarak kullanılmadı.
