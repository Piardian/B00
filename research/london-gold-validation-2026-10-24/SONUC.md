# London XAUUSD ORB: zaman ayrimli dogrulama

**Karar: Bu surumde edge dogrulanmadi. Ayri donem testi basarisiz. Canliya gecis yok.**

Ilk Ocak-Haziran testi istatistiksel esigi gecmemisti. Kullanici talebiyle Temmuz-Agustos icin ayri protokol, sonuclar hesaplanmadan once donduruldu. Eski protokol ve sonuc degistirilmedi. Bu aylar daha eski genis arastirmalarda goruldugu icin tamamen dokunulmamis OOS veya ileri test sayilamaz.

08:00-08:15 London BID araligi, acilis mumunun yonunde ilk kirilim, 12:00 oncesi tek giris, karsi bant sanal stop, 2R hedef ve 16:00 cikis aynen korundu. Gercek broker bid/ask gecmisi kullanildi; emir gerceklesmeleri ve slippage modellenmistir. Short stop BID ile tetiklenen sanal stop, ASK cikisidir; broker ASK stop emriyle esit degildir.

| Maliyet | Temmuz-Agustos (38 islem) | PF | Ocak-Agustos (151 islem) | PF |
|---|---:|---:|---:|---:|
| 1x | -12.35R | 0.59 | +3.22R | 1.03 |
| 1.5x | -12.81R | 0.58 | +1.53R | 1.02 |
| 2x | -13.24R | 0.57 | -8.17R | 0.92 |

1.5x maliyetle Temmuz +4.10R; Agustos -16.91R. Birlesik %95 bes-isgunu blok bootstrap araligi [-33.62R, +38.17R]. En iyi bes islem cikinca birlesik sonuc -8.39R. Mayis haric toplam -12.18R. Bunlar ek tani testleridir; yeni filtre secmek icin kullanilmadi.

44/44 isgunu kapsandi: 38 islem, 6 giris yok. Yerel M15 acilis fiyati, yonu ve BID hacmi 44/44 eslesti. Aritmetik, kaynak ve tape hash kontrolleri gecti; mevcut replay motorunun 9 testi gecti. Yeni dogrudan EURUSD referansi ortusmesi yalniz iki gun; daha genis broker saat kaniti ilk arastirmanin bagimsiz kontrolunden gelir. Bagimsiz altin fiyat akisi dogrulamasi yok.

2025 komisyon tarifesi hala dogrulanmadi; onceki dondurulmus muhafazakar komisyon modeli ve taraf basina $0.05/ons slippage aynen kullanildi. R, birim baslangic riski; hesap yuzde getirisi degildir. Mevcut terminalin otomatik islem izni acikti; bu arastirma ayar degistirmedi veya emir gondermedi.

Bu yalın ORB surumu aktif edge adayi olarak elenir. Bu sonuc tum ORB fikirlerinin imkansizligini kanitlamaz; mevcut kuralin donemler arasi tasinmadigini gosterir. Sonuclari gordukten sonra filtre eklemek yeni bir hipotezdir ve yeni, kullanilmamis donem gerektirir.
