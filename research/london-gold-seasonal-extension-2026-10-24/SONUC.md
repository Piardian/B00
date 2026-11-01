# London XAUUSD ORB: yaz filtresi ve ayri maliyet filtresi

Bu arastirma kullanicinin cozum odakli, gercekci arastirma talebiyle yapildi. Tum giris/stop/2R hedef/16:00EOD kurallari klasik motorla ayni. Yalniz belirtilen tek filtre karsilastirilir. Canli/paper emir yok.

2025tam yil;2026yalnizOcakEylul. Ilk2025OcakAgustos sonuclari gorulerek mevsimsellik hipotezi onerildi. Sonraki donemler bu klasik altin kuraliyla burada yeni olculdu, fakat daha eski genis arastirmada gorulmus olabilir; tamamen dokunulmamis OOS veya ileri test degildir.

## 1. Haziran-Agustos kapali

| Donem | Maliyet | Her gun ORB | Yaz kapali | Kapatma farki | Yaz kapali islem | Yaz kapali PF |
|---|---|---:|---:|---:|---:|---:|
| 2025_full | 1x | -2.08R | +8.60R | +10.68R | 175 | 1.07 |
| 2025_full | 1.5x | -4.34R | +6.93R | +11.27R | 175 | 1.06 |
| 2025_full | 2x | -14.60R | -2.78R | +11.82R | 175 | 0.98 |
| 2025_new_SepDec | 1x | -5.30R | -5.30R | +0.00R | 78 | 0.90 |
| 2025_new_SepDec | 1.5x | -5.87R | -5.87R | +0.00R | 78 | 0.89 |
| 2025_new_SepDec | 2x | -6.43R | -6.43R | +0.00R | 78 | 0.88 |
| 2026_JanSep_partial | 1x | EKSİK | EKSİK | — | — | — |
| 2026_JanSep_partial | 1.5x | EKSİK | EKSİK | — | — | — |
| 2026_JanSep_partial | 2x | EKSİK | EKSİK | — | — | — |
| all_21months | 1x | EKSİK | EKSİK | — | — | — |
| all_21months | 1.5x | EKSİK | EKSİK | — | — | — |
| all_21months | 2x | EKSİK | EKSİK | — | — | — |

### Belirsizlik ve donem tutarliligi

- 2025_full: yazkapali %95 netR araligi [-34.42205704830151, 49.85588590897855]; kapatma farkinin araligi [-9.477535425650448, 32.88232334657298];2025Mayis haric yazkapali net -6.79R.
- 2025_new_SepDec: yazkapali %95 netR araligi [-36.03330488349206, 25.249544631568995]; kapatma farkinin araligi [0.0, 0.0];2025Mayis haric yazkapali net -5.87R.
- 2026_JanSep_partial: bilinmeyen gunler ['2026-03-16', '2026-04-03']. Tam donem net/PF/CI verilmez. Cozumlenmis kapali islemler alt toplami hergun -37.15R, yazkapali -24.46R; bunlar tam donem sonucu degildir.
- all_21months: bilinmeyen gunler ['2026-03-16', '2026-04-03']. Tam donem net/PF/CI verilmez. Cozumlenmis kapali islemler alt toplami hergun -41.49R, yazkapali -17.53R; bunlar tam donem sonucu degildir.

Mevsimsellik karar kapisi: GECMEDI; takvim filtresi dogrulanmis cozum degil.

{
  "complete": false,
  "native": false,
  "clock": true
}

## 2. Maliyet/risk <=0.05R: yaz filtresinden AYRI

Giris anindaki spread + varsayilan iki tarafli slippage + ayni komisyon modelinin ilk risk mesafesine orani. Gelecekteki cikis spreadi bilinmediginden giris spreadi tur maliyeti icin bir vekildir. Oran0.05Rden buyukse ilk aday iptal, ikinci aday yok. Yaz kapatma eklenmez. Esik yeni donem sonuclari hesaplanmadan once donduruldu; esik taranmaz.

| Donem | Maliyet | Klasik | Maliyet filtresi | Fark | Islem | PF |
|---|---|---:|---:|---:|---:|---:|
| known2025JanAug | 1x | +3.22R | +11.87R | +8.65R | 15 | 3.33 |
| known2025JanAug | 1.5x | +1.53R | +2.00R | +0.47R | 4 | 2.98 |
| known2025JanAug | 2x | -8.17R | +2.98R | +11.15R | 3 | NA |
| new2025SepDec | 1x | -5.30R | +1.40R | +6.70R | 28 | 1.08 |
| new2025SepDec | 1.5x | -5.87R | +6.95R | +12.83R | 8 | 3.32 |
| new2025SepDec | 2x | -6.43R | +5.93R | +12.36R | 6 | 3.94 |
| 2025_full | 1x | -2.08R | +13.27R | +15.35R | 43 | 1.56 |
| 2025_full | 1.5x | -4.34R | +8.95R | +13.29R | 12 | 3.23 |
| 2025_full | 2x | -14.60R | +8.91R | +23.51R | 9 | 5.41 |
| 2026JanSep_partial | 1x | EKSİK | EKSİK | — | — | — |
| 2026JanSep_partial | 1.5x | EKSİK | EKSİK | — | — | — |
| 2026JanSep_partial | 2x | EKSİK | EKSİK | — | — | — |
| all21months | 1x | EKSİK | EKSİK | — | — | — |
| all21months | 1.5x | EKSİK | EKSİK | — | — | — |
| all21months | 2x | EKSİK | EKSİK | — | — | — |

### Uc adayli aile icin yaklasik %98.33 araliklar

- new2025SepDec: filtreli netR araligi [-3.0083183308425436, 19.881759556772963], eslesik fark araligi [-19.19420093787096, 43.43700001532937].
- 2026JanSep_partial: bilinmeyen gunler ['2026-03-16', '2026-04-03']; net/CI iddiasi yok.
- all21months: bilinmeyen gunler ['2026-03-16', '2026-04-03']; net/CI iddiasi yok.

### Eksik kis gunlerinden ayri, TAM kapsanan iki yaz

| Yaz | 1.5x islem | Haziran | Temmuz | Agustos | Yaz neti |
|---|---:|---:|---:|---:|---:|
| 2025 | 54 | +1.54R | +4.10R | -16.91R | -11.27R |
| 2026 | 61 | -5.73R | -2.49R | -4.47R | -12.70R |

Iki yazda da kayip var; yazkapatma arastirmaya deger. Ancak2025Aralik da -17.23R: sorun yalniz yaz degil.2025yazkapali2xmaliyet sonucu -2.78R. Mevsimsellik tek basina yeterli cozum degil.

### Maliyet filtresi: yalniz ortak COZUMLENMIS2026gunleri

Ayni193gun, eksik2026-03-16ve2026-04-03heriki politikadan da dislandi: maliyetfiltresi 13islem,+4.47R,PF1.63,%95aralik[-4.558129397169323, 17.01672694439513]. Bu eksik iki gunu0yapmak degildir; bu sadece193gunluk cozumlenmis altorneklemdir,2026toplami degildir. Baseline ayni altorneklem -37.15R.

Maliyetfiltresi2025te12islem,+8.95R; yeniSepAralikta8islem,+6.95R. Olumlu bir arastirma adayi, fakat sayi cok az: en az100islem kapisi ve belirsizlik kontrolleri gecmedi. Esik gevsetilmedi. Bu kapi genis acilis/risk araligi olan gunleri de secer; iyilesmeyi salt komisyon mekanizmasina baglayan nedensellik kaniti yok.

## 3. Dogrulama ve sinirlar

- Native acilis fiyat/yon QA: 450/451; nativeBIDhacim: 450/451. Ilk173gun sonucunun eski motorla birebir paritesi assert edildi.
- Yeni donem bagimsiz EURUSD saat kontrolu: 65 guclu gun, 0 celiski, yil bazinda {'2025': 65, '2026': 0}.2026icin dogrudan bagimsiz referans yok; ayni brokerin onceden dogrulanmis saat rejimi kullanildi. Bagimsiz altin feed kaniti degil.
- 9 eski replay testi ve4yeni odakli test gecti. Yeni testler maliyet kapisinin gelecektekiP&L/cikis alanlarini kullanmadigini, takvim sinirlarini, stres maliyetini ve yalniz veri API erisimini kontrol eder.
- 2025komisyon sayisal tarifesi dogrulanmadi; ayni muhafazakar envelope, gozlenen BIDASK ve varsayilan slip kullanildi.2026ayni tarife varsayilir, donemsel ucret degisimi kaniti yok. Shortstop BIDtetikASKcikis sanaldir; gercek brokerASKstop ile ayni degil.
- R birim baslangicriski; hesap yuzde getirisi degil. Herpolitika icin ayni gunler kullanildi; yazkapali gunler0 ama veri/gerceklesme bilinmeyenleri0yapilmadi.
- Mevcut The5ers oturumunda otomatik islem izni acikti; bu gorev ayar degistirmedi, terminali kapatmadi ve emir gondermedi. Disksiniri disaridan izlendi.2024sogukcache indirmesi yapilmadi.
- Tamamlanma, kaynakhash ve tapehash kontrolleri ayri JSON dosyalarindadir.456isgunu talep edildi;451tape,4tamkapali tatil,1Londraseansi eksik tatil.2026-03-16tapeicerisinde4566.247saniye bosluk var.2026-04-03gece nativebarlar oldugundan dondurulmus tamkapali-tatil kosulunu saglamaz ve bilinmeyen kalir.2026ve21aylik tam toplamlar tanimli degildir. Gelecekte olumlu aday ancak yeni tarihsel veri veya emir-gondermeyen ileri gozlemle tekrar sinanir.

## 4. Siradaki cozumler

M1 kapanis/retest/oncekimumbreak ve Asya araligindan cikis baglami COZUM_PLANI.mdde mekanik olarak tanimlandi; bu iki aday bu raporda olculmedi. Maliyet filtresi ve yazfiltresi sonucu bunlarin sonucunu onceden belirlemez. Ayni anda filtre eklemek yerine tek mekanizma degistirilir.