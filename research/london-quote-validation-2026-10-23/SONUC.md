# Sabit London ORB — The5ers bid/ask doğrulaması

**İşlem verisinin tamamı FivePercentOnline-Real sunucusundan, doğru The5ers terminali üzerinden salt okunur geçmiş tick çağrılarıyla alındı. Canlı/paper emir gönderilmedi.**

Durum: COMPLETE_QUOTE_REPLAY. Önceden sabitlenen araştırma kapısı: GEÇİLEMEDİ; doğrulanmış pozitif edge yok. Sonuç hazırlandığı UTC: 2026-10-23T21:11:06.025392+00:00.

## Dönem ve değişmeyen kurallar

Yeni dönemler Şubat ve Mart2025; önceki araştırmadaki Ocak/Haziran/Kasım2025ten ayrıdır. Bu gerçek ileri dönem değildir, farklı tarihsel dönem doğrulamasıdır. EURUSD,GBPUSD,USDJPY,USDCAD,USDCHF,NZDUSD.41işlem günü,246parite-günü; önceki14işgünü açılış hacmi hazırlığıyla330dosya.

Ana hipotez CLASSIC_RVOL_GE1, karşılaştırma CLASSIC_ALL. London08:00–08:15bidaralığı, açılış mumunun yönündeki ilk bidkırılımı,12:00öncesi yeni giriş, parite başına tek günlük işlem. Karşıbidbant yapısalstop, tam2Rhedef ve16:00London’da ilk gelen kotasyonda günsonu çıkış. TP1,BE,trailing,retest,HTF veya yeni eşik taraması yok. RVOL ilk15dakika MT5BIDbayrağı2güncelleme sayısının aynı kaynaktaki önceki14mevcut08:00açılışın ortalamasına oranıdır; eşik≥1. Bu, önceki stratejinin nativeM15tick_volume alanıdır, merkeziForexişlem hacmi değildir.

Alış gözlenenask, satış gözlenenbid üzerinden modellenir; longkapanışıbid, shortkapanışıasktır. Shortyapısalstop önceki sabit modeldeki karşıbidbandına göre sanal tetiklenir; başlangıç riskine giriş spreadi dahil edilir. Bu,MT5sellpozisyonuna sabitaskSLemri gönderiminin birebir taklidi değildir. Tick sırası kullanılır; gapte gözlenen daha kötü kotasyon esas alınır. Gözlenen kotasyonlar gerçek emir kuyruğu veya garantili dolum belgesi değildir.

## Net sonuçlar

| Model | Gider senaryosu | Dolum | NetR | PF | ŞubatR | MartR |
|---|---|---:|---:|---:|---:|---:|
| CLASSIC_ALL | COST_STRESS_1.5x | 218 | -25.53 | 0.84 | -24.31 | -1.22 |
| CLASSIC_ALL | COST_STRESS_2x | 218 | -31.73 | 0.81 | -27.95 | -3.78 |
| CLASSIC_ALL | MIN_SPREAD_1PIP | 218 | -26.04 | 0.84 | -24.33 | -1.71 |
| CLASSIC_ALL | OBSERVED_QUOTES_1x | 218 | -16.13 | 0.90 | -20.55 | +4.42 |
| CLASSIC_RVOL_GE1 | COST_STRESS_1.5x | 78 | +14.22 | 1.29 | +3.81 | +10.41 |
| CLASSIC_RVOL_GE1 | COST_STRESS_2x | 78 | +12.54 | 1.25 | +3.20 | +9.34 |
| CLASSIC_RVOL_GE1 | MIN_SPREAD_1PIP | 78 | +12.00 | 1.25 | +3.33 | +8.67 |
| CLASSIC_RVOL_GE1 | OBSERVED_QUOTES_1x | 78 | +18.94 | 1.41 | +4.44 | +14.50 |

OBSERVED_QUOTES_1x gerçek tarihselbid/askalanlarını kullanır.0.1pip/yönkayma ve4USD/100000birimroundtripkomisyon varsayımdır; geçmiş kişisel hesap masrafları uzlaştırılmadı. USD-bazlı paritelerde giriş kuru yaklaşımıyla quotepara birimine çeviri yapılır. Dolayısıyla bu gerçek fiyatlarla modellenmiş netRdir; gerçekleşmiş hesap kârı değildir.

1.5x/2x senaryolar gözlenenask-bidfarkını, varsayılan kayma ve komisyonu artırır. Stres fiyat ve hedefleri değiştirip başka kapanışlara yol açabilir; bunlar sabit dolum maliyetleri diye sunulmaz. MIN_SPREAD_1PIP senaryosunda spread gözlenen değer ile1pipten büyük olanıdır; diğer giderler temeldedir. Bu, gerçek spreadlerin üzerine ayrıca1pipekleme değildir.

## Kotasyon kalitesi ve saat

Toplam hazırlık+doğrulama kaydı: 22,067,572 tick. Günler içi kaynakta negatif/crossedaskbid, açılış/EODeksikliği veya60saniyeüstüboşluklar kapıdan geçirilmez. Tam dönem durumunun tamamlanması bütün gerekli dosyaların varlığını gerektirir. EksiklerinPnLsi sıfır yapılmaz.

| Parite | Doğrulama tick sayısı | Ortalama günlük sıfırspread oranı | En uzun boşluk(sn) |
|---|---:|---:|---:|
| EURUSD | 3,602,704 | %67.74 | 48.059 |
| GBPUSD | 3,936,873 | %74.44 | 38.392 |
| NZDUSD | 2,217,816 | %0.00 | 40.869 |
| USDCAD | 3,018,925 | %0.00 | 50.750 |
| USDCHF | 2,060,615 | %0.00 | 50.893 |
| USDJPY | 6,954,219 | %56.36 | 29.062 |

Özellikle EURUSD,GBPUSD,USDJPYde çok sayıda sıfırspread vardır. Bunlar brokerın ham tarihsel kotasyon alanlarıdır; gerçek işlemde her tickte aynı spreadle dolum alındığını doğrulamaz. Bunları sessizce genişletmedik veya silmedik. Ayrı1pipfloorstresi, olumlu bir sonucun bu özelliğe bağımlılığını değerlendirir.

Saat: geçmiş brokerUTC+2/+3US-DSTpolitikası kullanıldı. YeniEURUSDkotasyonlarını bağımsızYahooH1fiyatlarıyla kıyaslayan önceden kaydedilmişQAda41günde güçlü eşleşme,0çelişki; toplam saatlik getiri korelasyonu0.9793. Yahoo verisi yalnız saat kontrolünde kullanıldı; strateji fiyatları/hacmi değildir. İlkM15referans arşivinin yalnız2günü örtüştüğü için20gün kapsamkapısı geçilememişti; bu eksik rapor saklandı. Daha kapsamlıH1referansı kullanma gerekçesi ve kriterleriPnLöncesinde kaydedildi.

## Belirsizlik ve araştırma kapısı

- Ana model COST_STRESS_1.5x:5gözlemgünüblokbootstrap%95toplamRaralığı[-15.45,+48.91]R.
- Ana model COST_STRESS_2x:5gözlemgünüblokbootstrap%95toplamRaralığı[-17.07,+46.89]R.
- Ana model MIN_SPREAD_1PIP:5gözlemgünüblokbootstrap%95toplamRaralığı[-17.57,+45.75]R.
- Ana model OBSERVED_QUOTES_1x:5gözlemgünüblokbootstrap%95toplamRaralığı[-9.40,+52.39]R.

## Hacim uygulaması tutarlılık denetimi

İlk tick uygulaması bidveaskgüncellemelerinin tamamını hacim sayıyordu. Önceki klasik model nativeM15tick_volume kullanıyordu. Bu fark PnLsonrası uygulama kontrolünde bulundu; eski sonuçlar silinmedi. NativeM15hacmi MT5BIDbayrağı2sayımıdır. Doğrudan sunucudan tekrar okunan330M15mumunun hacmi, tepe/dibi ve yönü tickten üretilenlerle330/330eşleşti. Parametre, dönem ve eşik değiştirilmedi; fiyat geometrisi246doğrulamagününün hiçbirinde değişmedi.

Bu rapordaki ana tablo orijinalnativeM15hacimtanımını koruyan native_results.json sonucudur. Tümkotasyonolaylarınısayansürümresults.jsonda korunur:84dolum,+17.41Rtemel,+12.57R1.5x. Nativehacim78dolum,+18.94Rtemel,+14.22R1.5x. Bu karşılaştırma uygulama revizyonudur, ikinci bağımsız kanıt değildir. İlk sonuçlar görülmüş olduğu için çalışma kusursuz dokunulmamış tekbirOOSdeneyi olarak sunulmaz. native_volume_protocol.json gerekçeyi ve kaynak hashlerini yeni hesap öncesi kaydeder.

## Önceki olumsuz dönemler ve karar

Daha önceki Ocak/Haziran/Kasım2025sentetikspread/M1modeli olumsuzdu. Bu yeni iki olumlu ay o sonuçları ortadan kaldırmaz. Tick sırası,gözlenenbidaskveörneklemdönemleri öncekiM1varsayımlarından farklı olduğundan Rtoplamlarını tek bir performans serisi gibi toplamayın. Olumlu ayların kalıcı bir rejimi mi, örneklemşansını mı veya maliyetmodeli farkını mı yansıttığı daha geniş dönemlerle ayrılmalıdır. Henüz canlı kullanım gerekçesi yoktur.

Bu aralıklar bütün geçmiş strateji/evren seçimlerini düzeltmez. GünlükRler farklı paritelerde eşzamanlı birim riskli fırsat toplamlarıdır; portföyde marj, toplam açık risk, günlük kayıp freni ve para cinsinden bileşik getiri uygulanmış değildir. Gerçekhesapdrawdownı raporlanmaz. Bütün kapıların geçilmesi bile yalnız daha güçlü bir araştırma adayı üretir, canlı onay değildir.

Önceden sabitlenen kapılar: tam veri+saatdoğrulaması,ana modeldeenaz100dolum,ikiayın dapozitifolması,1xgüvenaralığıaltsınırınınpozitifolması,1.5x/2xgiderve1pipfloorstresindepozitifkalması. AyrıntılıTrue/False sonuçlar gate_results.json içindedir.

## Veri erişimi ve güvenlik

VarsayılanMT5bağlantısı yanlış terminale gittiği için ilk denemeAuthorizationfailedverdi. Açıkça C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe seçilince doğru sunucudan geçmişveri okundu. Giriş bilgisi değiştirilmedi, şifre raporlanmadı. Kullanıcı yalnızThe5ersistediği için alternatifDukascopykaynağı kullanılmadı. DNS/429başarısız yoklamalarıperformansverisine dönüşmedi.

10test geçti:bidaskyönü,askalış,bid/askdoğrukapanış,gapstop,kotasyonboşluğu,EOD,saat sınırı,gelecekteki fiyatın aralığa sızmaması,sıfırspreadfloorstresi,nativeBIDhacimve collector’ın yalnız okumaMT5çağrılarını kullanması. Kaynak ve330veridosyasınınhashleri sonuç sonunda yeniden doğrulandı. Üretimstratejisi, çalışanbot ve canlı emir ayarları değiştirilmedi;otomasyon kurulmadı.

Dosyalar: protocol_frozen.json, quote_manifest_frozen.json, tapes/, clock_h1_qa.json, native_volume_protocol.json, native_bar_qa.json, gate_results.json, native_results.json, native_outcomes.json ve outcomes.csv. İlkquote-volumehesabıresults.json/outcomes.jsonda korunur. Hamquotealanları,orijinalnumpybaythashleri,sembolözellikleri ve saat dönüşüm politikası kayıtlıdır.
