# London altin ORB: sorun -> mekanizma -> deney

Amac raporu guzellestirmek degil, maliyet sonrasi tekrarlanabilir beklenti ureten bir giris mekanizmasi bulmak. Zararli bir test, bir sonraki testi neden yaptigimizi netlestirmeli. Bu belge sonuc garantisi degildir.

## Simdi olculen hipotez: yaz aylarini kapatmak

Haziran-Temmuz-Agustos kapali; diger her sey sabit. 2025 tam yil tamamlanir; 2026 Ocak-Eylul ayri raporlanir. Ikincisi tam yil degildir. Iki yilda da kapatma farki ayni yonde degilse takvim filtresi aktif adaya eklenmez. Dogrulanmamis bir filtre baska filtrelerle birlestirilmez.

## Siradaki uc bagimsiz cozum adayi

1. **Maliyet/risk orani:** Giris aninda gorulen spread + iki taraf icin varsayilan slippage + tur komisyonunun toplam fiyat karsiligini ilk risk mesafesine bol. Oran 0.05R'den buyukse ilk adayi reddet; o gun ikinci aday arama. Hipotez, dar bantlarda odemelerin beklenen getiriyi yemesidir. 0.05 tek esiktir; grid veya en iyi esik secimi yok. Daha az islem veya daha az zarar, edge sayilmaz. EOD, stop, hedef ayni kalir. Bu filtre bilgi avantajindan cok gider azaltabilir; etkiyi olcmek gerekir.

2. **M1 kapanis + retest + tepe/dip kirilimi:** Ilk tamamlanmis M1 mumunun OR disinda islem yonunde kapanmasi; sonraki quote'larda kirilan banda retest; retest mumundan sonraki tamamlanmis M1 mumunun onceki tamamlanmis mumun tepe/dibini yonunde kapanisla asmasi ve OR disinda kalmasi. Giris sonraki dakikanin ilk quote'unda <=5sn, kesin12:00oncesi. Arada karsi OR stop bandi bozulursa gun iptal. Tek deneme. Hipotez, ilk temastaki sahte kirilimlari azaltmaktir; daha gec/daha pahali giris maliyeti de olculur. Bu mekanik onceki mum kirilimi, gozle swing seciminin birebir taklidi degildir. Benzer FX deneyi negatif/eksik kapsamliydi; altinda basarili oldugu varsayilmaz.

3. **Asya araligindan cikis baglami:** London00:00-08:00 tamamlanmis BID M15 barlarinin tepe/dibi. 08:00-08:15 OR kapanisi long icin Asya tepesinin ustunde, short icin Asya dibinin altindaysa klasik kirilim adayi uygundur. Esitlik gecmez; Asya barlari eksikse bilinmeyen. Hipotez, gunun onceki dengesini gercekten terk eden acilislarin devam sansinin daha yuksek olmasidir. Ayni veri uzerinde avantajli seans saati/Asya tanimi aranmamalidir.

Bu uc aday AYRI AYRI, filtresiz ayni klasik London ORB ile karsilastirilir. Birbirleriyle veya yaz filtresiyle birlestirilmez; en iyi kombinasyon taranmaz. Saat08:00-08:15London, giris12:00oncesi, enstruman basina tek deneme, karsi BID bant sanal stop,2R ve16:00EOD korunur.

## Degerlendirme duzeni

- Onceden gorulmus Ocak-Agustos2025 gelistirme/tani; SepAralik2025 ve OcakEylul2026 bu yeni giris varyantlariyla henuz olculmemistir ama genis arastirmada bu tarihler gorulmustur. Ayni tarihin yeni varyantla testi tamamen dokunulmamis OOS veya ileri test diye sunulmaz.
- Her aday icin ana senaryo1.5x;1x ve2x zorunlu stres kontrolleri. Ortak gunlerde netR farki, tum gunler korunarak no-entry0; bilinmeyen dolum/kapanis asla0 degil. Giris geometri farklari nedeniyle R farki dolar getirisiyle ayni degildir.
- Yalniz pozitif PF ile aday terfi etmez. Tam kapsam, en az100kapali islem,1.5xve2xpozitiflik,1.5x net beklenti ve eslesik fark icin blok guven araligi, donemler arasi tutarlilik gerekir. Uc hipotez icin karsilastirma sayisi gizlenmez; aday-basina%98.33 iki tarafli araliklar Bonferroni yaklasimiyla aile bazinda%95 hedefler (bootstrap yaklasiktir).
- Stop/TP/holding parametreleri bu turda degismez. Pozitif aday icin yeni kullanilmamis tarihsel donem veya tarihten sonra toplanmis emir-gondermeyen forward veri gerekir. Numerik2025komisyon ve gerceklesme belirsizligi ayrica kalir.
- Uc aday da elenirse daha fazla ORB parametresi taramak yerine London strateji ailesini degistirmek icin yeni protokol yazilir. Ornek: acilis sonrasi geri donusun fiyat onayi uzerinden sinanmasi; eski hatali ADR sonucu tum mean-reversion ailesini curutmez. Bu alternatif henuz tanimlanmis veya olculmus bir edge degildir.

Uretim koduna filtre eklenmez; canli/paper emir gonderilmez. Her deneyde uygulama, test, kaynak/tape hashleri ve sonuc dosyasi tutulur. Su an bu belgede siradaki adaylar arastirma plani; bunlarin sonuclari hesaplanmis degildir.
