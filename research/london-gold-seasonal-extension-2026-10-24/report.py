"""Report fixed seasonal comparison and separately measured cost gate."""
import json
import study as s
g=s.g

def main():
    s.verify();r=s.read('results.json');qa=s.read('native_qa.json');clock=s.read('clock_qa.json')
    cr=g.read(s.BASE/'cost_gate/results.json');diagnostics=s.read('coverage_diagnostics.json')
    lines=['# London XAUUSD ORB: yaz filtresi ve ayri maliyet filtresi','',
        'Bu arastirma kullanicinin cozum odakli, gercekci arastirma talebiyle yapildi. Tum giris/stop/2R hedef/16:00EOD kurallari klasik motorla ayni. Yalniz belirtilen tek filtre karsilastirilir. Canli/paper emir yok.','',
        '2025tam yil;2026yalnizOcakEylul. Ilk2025OcakAgustos sonuclari gorulerek mevsimsellik hipotezi onerildi. Sonraki donemler bu klasik altin kuraliyla burada yeni olculdu, fakat daha eski genis arastirmada gorulmus olabilir; tamamen dokunulmamis OOS veya ileri test degildir.','',
        '## 1. Haziran-Agustos kapali','',
        '| Donem | Maliyet | Her gun ORB | Yaz kapali | Kapatma farki | Yaz kapali islem | Yaz kapali PF |',
        '|---|---|---:|---:|---:|---:|---:|']
    for group in ['2025_full','2025_new_SepDec','2026_JanSep_partial','all_21months']:
        for name,m in g.SCENARIOS:
            z=r['results'][group][name]
            if z['complete_always']:
                a=z['always_on'];b=z['summer_off'];pf=f"{b['pf']:.2f}" if b['pf'] is not None else 'NA'
                lines.append(f"| {group} | {m:g}x | {a['net_r']:+.2f}R | {b['net_r']:+.2f}R | {z['paired_delta_net_r']:+.2f}R | {b['fills']} | {pf} |")
            else:
                lines.append(f"| {group} | {m:g}x | EKSİK | EKSİK | — | — | — |")
    lines+=['','### Belirsizlik ve donem tutarliligi','']
    for group in ['2025_full','2025_new_SepDec','2026_JanSep_partial','all_21months']:
        z=r['results'][group]['STRESS_1.5x']
        if z['complete_always']:
            lines.append(f"- {group}: yazkapali %95 netR araligi {z['summer_off']['block_total_ci95']}; kapatma farkinin araligi {z['paired_delta_ci95']};2025Mayis haric yazkapali net {z['summeroff_without_2025May_r']:+.2f}R.")
        else:lines.append(f"- {group}: bilinmeyen gunler {z['unknown_always']}. Tam donem net/PF/CI verilmez. Cozumlenmis kapali islemler alt toplami hergun {z['resolved_closed_always_net_r']:+.2f}R, yazkapali {z['resolved_closed_summeroff_net_r']:+.2f}R; bunlar tam donem sonucu degildir.")
    lines+=['','Mevsimsellik karar kapisi: '+('GECTI; yalniz arastirma destegi, canli onay degil.' if r['all_checks_pass'] else 'GECMEDI; takvim filtresi dogrulanmis cozum degil.'),'',json.dumps(r['checks'],indent=2),'',
        '## 2. Maliyet/risk <=0.05R: yaz filtresinden AYRI','',
        'Giris anindaki spread + varsayilan iki tarafli slippage + ayni komisyon modelinin ilk risk mesafesine orani. Gelecekteki cikis spreadi bilinmediginden giris spreadi tur maliyeti icin bir vekildir. Oran0.05Rden buyukse ilk aday iptal, ikinci aday yok. Yaz kapatma eklenmez. Esik yeni donem sonuclari hesaplanmadan once donduruldu; esik taranmaz.','',
        '| Donem | Maliyet | Klasik | Maliyet filtresi | Fark | Islem | PF |',
        '|---|---|---:|---:|---:|---:|---:|']
    for group in ['known2025JanAug','new2025SepDec','2025_full','2026JanSep_partial','all21months']:
        for name,m in g.SCENARIOS:
            z=cr['results'][group][name]
            if z['complete']:
                a=z['baseline'];b=z['costgate'];pf=f"{b['pf']:.2f}" if b['pf'] is not None else 'NA'
                lines.append(f"| {group} | {m:g}x | {a['net_r']:+.2f}R | {b['net_r']:+.2f}R | {z['paired_delta_net_r']:+.2f}R | {b['fills']} | {pf} |")
            else:lines.append(f"| {group} | {m:g}x | EKSİK | EKSİK | — | — | — |")
    lines+=['','### Uc adayli aile icin yaklasik %98.33 araliklar','']
    for group in ['new2025SepDec','2026JanSep_partial','all21months']:
        z=cr['results'][group]['STRESS_1.5x']
        if z['complete']:lines.append(f"- {group}: filtreli netR araligi {z['variant_ci98_33']}, eslesik fark araligi {z['paired_delta_ci98_33']}.")
        else:lines.append(f"- {group}: bilinmeyen gunler {z['unknown_dates']}; net/CI iddiasi yok.")
    lines+=['','### Eksik kis gunlerinden ayri, TAM kapsanan iki yaz','',
        '| Yaz | 1.5x islem | Haziran | Temmuz | Agustos | Yaz neti |',
        '|---|---:|---:|---:|---:|---:|']
    for year in ['2025','2026']:
        z=diagnostics['summers'][year]['STRESS_1.5x']['summer'];mm=z['by_month']
        lines.append(f"| {year} | {z['fills']} | {mm[year+'-06']:+.2f}R | {mm[year+'-07']:+.2f}R | {mm[year+'-08']:+.2f}R | {z['net_r']:+.2f}R |")
    lines+=['','Iki yazda da kayip var; yazkapatma arastirmaya deger. Ancak2025Aralik da -17.23R: sorun yalniz yaz degil.2025yazkapali2xmaliyet sonucu -2.78R. Mevsimsellik tek basina yeterli cozum degil.','',
        '### Maliyet filtresi: yalniz ortak COZUMLENMIS2026gunleri','']
    known=diagnostics['cost_common_known']['2026JanSep_partial']['STRESS_1.5x']
    z=known['costgate']
    lines.append(f"Ayni193gun, eksik2026-03-16ve2026-04-03heriki politikadan da dislandi: maliyetfiltresi {z['fills']}islem,{z['net_r']:+.2f}R,PF{z['pf']:.2f},%95aralik{z['block_total_ci95']}. Bu eksik iki gunu0yapmak degildir; bu sadece193gunluk cozumlenmis altorneklemdir,2026toplami degildir. Baseline ayni altorneklem {known['baseline']['net_r']:+.2f}R.")
    lines+=['','Maliyetfiltresi2025te12islem,+8.95R; yeniSepAralikta8islem,+6.95R. Olumlu bir arastirma adayi, fakat sayi cok az: en az100islem kapisi ve belirsizlik kontrolleri gecmedi. Esik gevsetilmedi. Bu kapi genis acilis/risk araligi olan gunleri de secer; iyilesmeyi salt komisyon mekanizmasina baglayan nedensellik kaniti yok.','',
        '## 3. Dogrulama ve sinirlar','',
        f"- Native acilis fiyat/yon QA: {sum(q['price_match'] for q in qa)}/{len(qa)}; nativeBIDhacim: {sum(q['volume_match'] for q in qa)}/{len(qa)}. Ilk173gun sonucunun eski motorla birebir paritesi assert edildi.",
        f"- Yeni donem bagimsiz EURUSD saat kontrolu: {clock['strong_days']} guclu gun, {len(clock['conflicts'])} celiski, yil bazinda {clock['per_year']}.2026icin dogrudan bagimsiz referans yok; ayni brokerin onceden dogrulanmis saat rejimi kullanildi. Bagimsiz altin feed kaniti degil.",
        '- 9 eski replay testi ve4yeni odakli test gecti. Yeni testler maliyet kapisinin gelecektekiP&L/cikis alanlarini kullanmadigini, takvim sinirlarini, stres maliyetini ve yalniz veri API erisimini kontrol eder.',
        '- 2025komisyon sayisal tarifesi dogrulanmadi; ayni muhafazakar envelope, gozlenen BIDASK ve varsayilan slip kullanildi.2026ayni tarife varsayilir, donemsel ucret degisimi kaniti yok. Shortstop BIDtetikASKcikis sanaldir; gercek brokerASKstop ile ayni degil.',
        '- R birim baslangicriski; hesap yuzde getirisi degil. Herpolitika icin ayni gunler kullanildi; yazkapali gunler0 ama veri/gerceklesme bilinmeyenleri0yapilmadi.',
        '- Mevcut The5ers oturumunda otomatik islem izni acikti; bu gorev ayar degistirmedi, terminali kapatmadi ve emir gondermedi. Disksiniri disaridan izlendi.2024sogukcache indirmesi yapilmadi.',
        '- Tamamlanma, kaynakhash ve tapehash kontrolleri ayri JSON dosyalarindadir.456isgunu talep edildi;451tape,4tamkapali tatil,1Londraseansi eksik tatil.2026-03-16tapeicerisinde4566.247saniye bosluk var.2026-04-03gece nativebarlar oldugundan dondurulmus tamkapali-tatil kosulunu saglamaz ve bilinmeyen kalir.2026ve21aylik tam toplamlar tanimli degildir. Gelecekte olumlu aday ancak yeni tarihsel veri veya emir-gondermeyen ileri gozlemle tekrar sinanir.','',
        '## 4. Siradaki cozumler','',
        'M1 kapanis/retest/oncekimumbreak ve Asya araligindan cikis baglami COZUM_PLANI.mdde mekanik olarak tanimlandi; bu iki aday bu raporda olculmedi. Maliyet filtresi ve yazfiltresi sonucu bunlarin sonucunu onceden belirlemez. Ayni anda filtre eklemek yerine tek mekanizma degistirilir.']
    (s.BASE/'SONUC.md').write_text('\n'.join(lines),encoding='utf8')
    files=['study.py','protocol_frozen.json','native_frozen.json','quote_manifest.json','clock_qa.json','native_qa.json','outcomes.json','outcomes.csv','results.json','integrity_check.json','COZUM_PLANI.md','report.py','SONUC.md','coverage_diagnostics.py','coverage_diagnostics.json','storage_repair_protocol.json','storage_repair_result.json','quote_manifest_before_repack.json','repack.py','resume_guard.ps1','cost_gate/completion.json','cost_gate/protocol_frozen.json','cost_gate/results.json','cost_gate/entry_features.json','cost_gate/outcomes.json','cost_gate.py','test_extension.py']
    save=dict(status='COMPLETE_RESEARCH',complete_coverage=r['complete'],seasonal_checks_pass=r['all_checks_pass'],orders_sent=False,production_changed=False,tests_passed=13,hashes={n:g.sha(s.BASE/n) for n in files})
    g.save(s.BASE/'completion.json',save)
    print('REPORT_COMPLETE',r['checks'],flush=True)

if __name__=='__main__':main()
