# Asya sıkışması: ayrı dönem doğrulaması

**Karar: NOT_CONFIRMED. Canlıya geçiş yok.**

Önceki Ocak/Kasım2025 bulgusundaki %35 eşiği değiştirilmeden, Şubat ve Mart2025'te yeniden sınandı. Bu iki ayın fiyatları başka bir klasikORB araştırmasında kullanılmıştı. Bu çalışma bu erken-limit/sıkışma hipotezi için ayrı dönem kontrolüdür; tamamen dokunulmamış proje-geneli OOS veya prospektif forward değildir. Şubat/Mart sonucu eski aylara eklenerek bağımsız kanıt diye sunulmaz.

## Kuralların eşitliği

Dondurulmuş config,ORB,entry,volume ve London-context modülleri önceki çalışmayla byte düzeyinde aynı. Önceki33kurulumun entry/stop/TP1/TP2 değerleri yeni dondurulmuş dedektörle birebir yeniden üretildi. Giriş MIDPOINT limit; önceki ortak araştırma çıkış motoru aynen kullanıldı. Stop küçültülmedi, M1teyit eklenmedi, hedef uzaklaştırılmadı.

Her parite/London gününde ilk normalize edilmiş uygun kurulum seçilir; dolmasa da gün tüketilir. Daha sonra Asya aralığı/dailyATR≤0.35 TIGHT, (0.35,0.70] LOOSE olarak etiketlenir. Sıkışık gruba geçmek için o gün daha sonraki aday aranmaz. Temel dedektörün0.70 sınırı korunur; kontrol grubu bütün piyasa günleri değil, aynı dedektörden çıkan daha geniş Asya kurulumlarıdır.

## Kapsam ve veri

- Altı parite:EURUSD,GBPUSD,USDJPY,USDCAD,USDCHF,NZDUSD. Altın yok.
-41hafta içi gün×6parite=246parite-günü; Asya24M15barı, London aralığı ve giriş saatleri ile ATR geçmişi kontrol edildi.
-Seçilen kurulum:25; ana model bütün referans dolumu:23.
-TIGHT:22kurulum/21dolum; LOOSE:3kurulum/2dolum.
-H1/M15yerel broker geçmişinden; günlük ATR yalnız önceki tamamlanmış yeterli UTC günlerinden. Son300tamamlanmışM15 kullanılır.
-NativeM1 geçmişi istenen dönemi vermedi. Sonuçlar hesaplanmadan ikinci protokolle, mevcut The5ers London08–16tick arşivinden ve önbellekteki16–16:31kuyruğundan bidM1 üretildi. Eksik fiyat interpolasyonu yok. Her parite için41×511=20951LondonM1 satırı var.
-Broker saat dönüşümü öncekiUS-DST UTC+2/3 eşlemesidir; mevcut bağımsız H1clock denetimi41güçlü günde sıfır saat kayması raporlamıştır. Bu çalışma clock araştırmasını yeniden yapmadı.

Bu setup araştırmasıdır: makro/haber,SFPönceliği,ortak portföy riski,marj ve gerçek hesap yürütmesi yok. R bağımsız kurulumun ilk fiyat riskine göre normalize edilmiş model sonucudur.

## Sonuçlar

**Aşağıdaki netR modeldir:** gerçek bidM1 + varsayımsal sabit ask spreadi,4USD/100binbirim round-trip komisyon ve0.2pip olumsuz piyasa çıkış kayması. Tarihsel gerçek ask,hesap komisyonu ve kayma yaşam döngüsü doğrulaması değildir. Ortak çıkışlar:TP1yarım,BE/trailing,dolum mumundaTPyok,stopöncelikli,olumsuzdolumtepkisindeücretliçıkış,London16:30kapatma. Bu son kapanış önceki araştırma sözleşmesidir; üretim botunun birebir sonlandırma kuralı diye sunulmaz.

|Spread varsayımı|TIGHT dolum|TIGHT toplamR|ŞubatR|MartR|LOOSE dolum|LOOSE toplamR|
|---|---:|---:|---:|---:|---:|---:|
|0.2pip|21|-2.521|+0.520|-3.041|2|+0.814|
|0.5pip|21|-5.665|-3.302|-2.362|2|+0.791|
|0.9pip|21|-5.980|-3.487|-2.494|2|+0.760|
|1.5pip|21|-5.768|-2.185|-3.583|2|+0.714|

Ana0.5pip modelinde TIGHT beklenti -0.257R/kabul edilen kurulum;95%gün-küme bootstrap aralığı **[-0.473, -0.037]**. Aynı günün işlemleri birlikte örneklenir. Aralık geçmiş çoklu araştırmaları düzeltmez; günler arası tam seri bağımlılık düzeltmesi de değildir. Sıfır dolumlar kabul edilen kurulum paydasında korunur. Kazançlı ay veya parite seçilmedi.

## Önceden belirlenen karar kapıları

- tight_positive_total_0.5pip: GEÇMEDİ
- tight_both_months_positive_0.5pip: GEÇMEDİ
- tight_outperforms_loose_mean_0.5pip: GEÇMEDİ
- tight_positive_total_1.5pip: GEÇMEDİ
- tight_both_months_positive_1.5pip: GEÇMEDİ
- tight_outperforms_loose_mean_1.5pip: GEÇMEDİ
- at_least30_primary_tight_fills: GEÇMEDİ
- all246pair_days_covered: GEÇTİ
- no_unresolved_replay: GEÇTİ

30dolum alt sınırı pratik bir örneklem kapısıdır;30veya daha çok işlem edge kanıtı değildir. Toplam artı yeterli değildir: iki ayın ve1.5pip stresinin de pozitif olması, çözümlenmemiş veri/işlem olmaması, TIGHT'ın LOOSE'a göre kurulum başına daha iyi sonuç vermesi aranmıştır. Başarısız kapılar çıktıda korunur. Olumsuz sonucu düzeltmek için0.30/0.40gibi yeni eşikler, parite/saat alt kümeleri veya yeni çıkışlar denenmedi.

## Çıktılar ve doğrulama

protocol.json ilk planı; protocol_v2.json nativeM1 engelinden sonra, yeni aday/getiri hesaplanmadan yapılan kaynak düzeltmesini korur. price_manifest_frozen.json veri kilididir. candidates.json bütün seçilen kurulumları, coverage.json246günü, outcomes.json her maliyet/kurulum yolunu, summary.json tüm grupları, decision.json kapıları içerir.

11test geçti: %35sınırı,geçersizoranlar,US/UKDSTayrımı,çözümlenmemişişlemdennetkâryazmama ve eski33kurulumun giriş/hedef eşitliği. Dondurulmuş kaynak ve veri hashleri tekrar denetlenir. Canlı kod/çalışan süreç değiştirilmedi, emir gönderilmedi, ücretliAPI/otomatik devam görevi yok.

Tekrar kontrol:

```
python research/asia-validation-2026-10-24/study.py verify
python research/asia-validation-2026-10-24/study.py run
```

## Başarısız doğrulamadan sonra fiyat yolu teşhisi

Ana senaryonun21TIGHTdolumunda, ilk yapısal stop/TP1 seviyeleriyle ve sabit16:30sonuna kadar bakıldığında: **12işlemde stop önce**, **9işlemde TP1önce**. Bu fiyat yoludur; varsayımsal yeni strateji kârı değildir.

12olumsuz tepki çıkışı toplam -1.993R üretmiş. Bu çıkışlardan sonra ilk TP1/ilk stop yarışı **6TP1önce /6stopönce**. Dolayısıyla erken çıkışların bazısı toparlanmadan önce kapanıyor, bazıları daha büyük yapısal zarardan önce kapanıyor. Bu örneklem “tepki çıkışını kaldırmak çözüm” demiyor. Tüm21fiyat-yolu sınıflandırmasında belirsiz/eksik dakika veya aynı-mum stop/TP1çakışması çıkmadı.

Bu teşhis sonuçlar görüldükten sonra ayrı diagnostic_protocol.json ile kilitlendi. Fiyatın sonraki davranışı girişte bilinen bir özellik olarak kullanılamaz. Yeni filtre, hedef veya hipotetik netkâr çıkarılmadı. Dört ek fiyat-yolu testiyle **toplam15test geçti**.

**Uygulanabilir karar:** %35Asya filtresini canlıya almamak ve bu sabit filtreyi edge adayı olarak terfi ettirmemek. Kontrol grubu yalnız2dolumdur; tersine çevirip genişAsya grubunu başarılı strateji ilan etmek de yanlış olur. Sonraki ayrı araştırma için sorun başlıkları artık ölçülüdür: kurulumların başlangıç yön avantajı ve erken çıkışın kurtardığı/kaçırdığı hareketleri girişte bilinen verilerle ayırabilmek. Bu ayrım yeni bir dönem veya prospektif gözlemde sınanmalı; başarısız doğrulama aylarında eşik/çıkış taramasıyla yeşil tablo aranmamalıdır.
