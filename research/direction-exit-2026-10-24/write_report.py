"""Post-run report; no candidate selection or rule fitting."""
import json
from study import HERE,write,sha


def load(name):return json.loads((HERE/name).read_text(encoding='utf-8'))


def main():
    summaries=load('summary.json');paired=load('paired.json');directions=load('direction_summary.json');status=load('status.json')
    lookup={(r['source'],r['spread_pips'],r['mode']):r for r in summaries}
    conditions=load('reaction_context_groups.json');after=load('after_fill_direction_summary.json')
    gates={}
    for mode in ['never','half_r_adverse']:
        rules={}
        for cost in [.5,1.5]:
            r=lookup['RECHECK',cost,mode];base=lookup['RECHECK',cost,'always']
            rules[f'improves_recheck_{cost}pip']=r['net_r']>base['net_r']
            rules[f'positive_both_months_{cost}pip']=all(v['fills']>0 and v['net_r']>0 for v in r['monthly'].values())
        gates[mode]=dict(survives_screen=all(rules.values()),checks=rules)
    write(HERE/'decision.json',dict(status='NO_EXIT_CANDIDATE_CONFIRMED',rules=gates,live_promotion=False,
      direction='No demonstrated directional advantage on fixed60minute diagnostic; not a statement about every horizon or executable reverse strategy.'))
    lines=[]
    for source,label in [('DISCOVERY','Ocak/Kasım'),('RECHECK','Şubat/Mart'),('ALL','Dört ay')]:
        for mode,title in [('always','Mevcut tepki çıkışı'),('never','Tepki çıkışı yok'),('half_r_adverse','Tepki çıkışı yalnız≤−0.5R kapanışta')]:
            a=lookup[source,.5,mode];b=lookup[source,1.5,mode]
            lines.append(f"|{label}|{title}|{a['fills']}|{a['net_r']:+.3f}|{b['net_r']:+.3f}|")
    direction_lines=[]
    for d in directions:
        ci=d['original_mean_day95'];label={'ALL':'Dört ay','DISCOVERY':'Ocak/Kasım','RECHECK':'Şubat/Mart'}[d['source']]
        direction_lines.append(f"|{label}|{d['measured']}|{d['positive']}|{d['negative']}|{d['original_mean_score_r']:+.3f}|[{ci[0]:+.3f},{ci[1]:+.3f}]|")
    context_lines=[]
    for r in conditions:
        if r['source']=='RECHECK' and r['feature']=='wait':
            context_lines.append(f"|{r['spread_pips']:.1f}pip|{r['group']}|{r['n']}|{r['total_early_exit_benefit_r']:+.3f}|{r['helped']}|{r['hurt']}|")
    text=f'''# Giriş yönü ve erken tepki çıkışı: kontrollü araştırma

**Sonuç: yeni bir çıkış kuralı veya güvenilir yön avantajı doğrulanmadı.** Erken çıkışı kaldırmak bazı koşullarda kaybı azaltıyor, başka koşullarda artırıyor. Yeni kuralı üretime almak için gerekçe yok.

## Kapsam

Ocak/Kasım2025'ten33 ve Şubat/Mart2025'ten25 olmak üzere **58sabit ilk günlük kurulum** kullanıldı. Şubat/Mart25kurulum bu turun ana kontrol örneklemidir; önceki sıkışma testindeki yalnız21TIGHTdolumla karıştırılmamalıdır. Bu turda %35filtresi uygulanmadı; aynı dedektörün bütün25kurulumu korundu. Makro/haber/SFPönceliği/portföyriski yok; tam bot veya gerçek hesap performansı değildir. Bütün dönemler daha önce görüldü; bu çalışma yeni OOS kanıtı değildir.

Protokol grup/çıkış sonuçlarından önce donduruldu. Üretim kaynakları değiştirilmedi; önceki araştırma motorunun yerel kopyasında yalnız erken çıkış koşulu değiştirildi. İlk stop,limitdolumu,hedefler,kısmiçıkış,BE/trailing veLondon16:30sonu aynı. Dolum mumunda hedef kredisi yok, stop öncelikli, zararlı dolum silinmiyor. Bütün **232önceki referans kaydının** durum,dolum,kapanış,sebep ve netRsi yeniden eşleşti; çıkış varyantlarında giriş dolumları aynı kaldı.

## 1. Çıkış kuralını tek başına değiştirmek

Üç sabit kural:

-always: mevcut olumsuz dolum-mumu tepki çıkışı.
-never: yalnız bu tepki çıkışı kaldırılır; yapısal stop ve diğer çıkışlar korunur.
-half_r_adverse: aynı olumsuz tepki bulunursa, ancak executable mum kapanışı girişe göre−0.5Rveya daha kötü olduğunda çıkar. Bu mark-to-entry ölçümü çıkış kayması/komisyondan öncedir; kapanışta bilinir. Eşik taranmadı.

NetR, önceki varsayımsal maliyet sözleşmesiyle: sabitspread,100binbirime4USDround-trip komisyon,0.2pip olumsuz piyasa çıkış kayması. Gerçek bid/ask/hesap ücretiyle doğrulanmış netgetiri değildir. Spread senaryosu dolum ve izlenen yolu da değiştirebilir; aynı ücret düşülmüş sabit kazançlar gibi yorumlanmaz.

|Dönem|Çıkış|0.5pip dolum|0.5pip netR|1.5pip netR|
|---|---|---:|---:|---:|
{chr(10).join(lines)}

Şubat/Mart ana modelinde tepki çıkışını kaldırmak toplamı+1.105Riyileştiriyor; ama Şubat−0.046R,Mart−3.722R ve toplam−3.768R kalıyor. Stres spreadinde−2.690Rdaha kötü. Ana maliyette6kurulum iyileşti,7kötüleşti; streste3iyileşti,8kötüleşti. Geri kalanlar değişmedi. Eşleştirilmiş ortalama farkın gün-küme95%aralıkları sıfırı içeriyor; istikrarlı iyileştirme kanıtı yok.

−0.5Rkoşullu kural, bu örneklemde never ile aynı sonuçları verdi. Tepki başarısızlığıyla çıkan mumların kapanış kayıpları eşiğe ulaşmadığından bu kural çıkışı tetiklemedi. Bunlar iki bağımsız olumlu/olumsuz kanıt değil, örneklemde aynı yolu üreten iki tanımdır. Eşiği sonradan değiştirmedik.

## 2. Yönün kendisi avantajlı mı?

Her kurulumun orijinal bilgi-kullanılabilirlik anından sonraki sabit60dakikalık bid-open hareketi, giriş-stop mesafesine bölündü. Orijinal sinyal yönü ve ters işaret aynı fiyat/riskte karşılaştırıldı. **Bu yön skoru, stoplu işlem getirisi veya maliyet sonrası kâr değildir.** Limitin dolmasına bağlı örnek seçilmedi. Ters işaret matematiksel kontrol; uygulanabilir ters strateji backtesti değildir.

|Dönem|Ölçüm|Yönünde hareket|Ters hareket|Ortalama yön skoruR|Gün-küme95%aralık|
|---|---:|---:|---:|---:|---|
{chr(10).join(direction_lines)}

Şubat'ta ortalama yön skoru+0.380R,Mart'ta−0.293R. Şubat/Mart toplamında ters-yön skor ortalaması−0.030R; bunun pozitif bir ters-strateji önerisine dönüşmesi mümkün değil. Seçilen60dakika ufkunda tutarlı yön avantajı gösterilemedi; başka her zaman ufku için matematiksel imkânsızlık iddiası yok.

Ek ölçüm, gerçek dolumun M1içindeki sırası bilinmediğinden dolum mumundan **sonraki M1açılışından**60dakika ilerisine yapıldı. Şubat/Mart23dolumun13ünde hareket orijinal yönde; ortalama+0.098R ve gün-küme95%aralık[−0.638,+0.745]. Bu da belirgin üstünlük kanıtı değil. Erken çıkmış işlemler bu fiyat-yolu ölçümünde tutulur; yeni emir veya gerçekleşmiş getiri sayılmaz.

## 3. Erken çıkış hangi koşulda faydalı?

Toplam sonuçlar görüldükten sonra **ayrı context_protocol.json** ile betimleyici ikinci aşama sabitlendi: kapanışın girişe göre işareti,bekleme≤15dakika ve Asya≤0.35. Hiçbiri yeni canlı filtreye dönüştürülmedi. Faydası mevcut tepki çıkışı netRsi eksi aynı dolumda çıkışı kaldıran varyantın netRsidir: pozitif fark, erken çıkışın zararı azalttığını gösterir.

Şubat/Mart'ta sadece orijinaltepkiçıkışları:

|Spread|Doluma kadar bekleme|Örnek|Erken çıkışın toplam faydasıR|Faydalı|Zararlı|
|---|---|---:|---:|---:|---:|
{chr(10).join(context_lines)}

15dakikadan geç dolan üçtepkiçıkışında erken kapatma iki maliyette de toplamı korumuş. Fakat **üçörnekten kural doğrulanmaz**. Hızlı dolumlardaki fayda işareti maliyet senaryosuyla değişiyor. Kapanış işareti de bu kontrol grubunu ayırmadı: bütüntepkiçıkışları girişe göre negatif kapanışlı;−0.283Rile−0.018Rarasında. Asya ayrımı önceki başarısız filtreyi kurtarmadı. Koşul grupları ve bütünhücreler reaction_context_groups.json içinde; iyi görünen hücreler tek başına seçilmedi.

Bu kayıtların somut değeri: **dolum gecikmesi, dolum mumu kapanışRsi ve eşleştirilmiş çıkış faydası** artık ayrı alanlarda ölçülüyor. Gelecek kayıtlar aynı alanlarla izlenebilir; gelecekteki gerçekleşmiş fayda geçmişte bilinen bir giriş özelliği gibi kullanılamaz.

## Karar ve geliştirme yönü

Mevcut deneylerde yalnız çıkışı gevşetmek veya sinyal yönünü ters çevirmek çözüm olmadı. Sonraki ayrı hipotez için ölçülebilir aday **kurulumun zamanla eskimesi**: limitin doluma kadar bekleme süresi ve dolum anında kırılım yapısının hâlâ geçerli olması. Bu turda15dakikalık emir iptal kuralı uygulanmadı; böyle bir kuralın kârlı olduğu iddia edilmiyor. Önce yeni dönemde aynı gözlem alanlarıyla kontrol grubu korunmalı. Düşük örnekli geçdolum grubuna bakarak eski aylarda yeni süre/stop eşikleri taranmamalı.

Çıkış değişikliği için önceden istenen ikiayda pozitiflik ve1.5pip dayanıklılığı sağlanmadı. **Canlı terfi yok; edge kanıtlanmadı.** Bu, projenin her olası varyantının başarısız olacağı iddiası değildir; test edilen belirli giriş/çıkış tanımlarına ilişkin ölçümdür.

## Doğrulama ve dosyalar

-58kurulum×4maliyet×3çıkış=696replaykaydı; bağımsız696işlem değildir.
-Çözümlenmemiş replay:{status['unresolved']}; çözümlenmemiş karar-yönü ölçümü:{status['direction_unresolved']}.
-8yeni davranıştesti: stopun korunması, dolumun silinmemesi, hafif/ağırtepki ayrımı, dolum-mumuTPyasağı, yönölçümünün limitdolumundan bağımsızlığı,60dakika sonrasıfuturedataayrımı,eksikmum ve dolumsuzkurulum.
-232referans lifecycle/netR eşitliği ve varyantların aynıdolumları koruması çalışma içi zorunlu kontrol.
-protocol.json ana plan; context_protocol.json ikinci betimleyici aşama. outcomes.json/summary.json/paired.json netkarşılaştırmalar; direction_records.json/summary,after_fill_direction_records.json/summary fiyat-yolu ölçümleri; reaction_context_records.json/groups koşul kayıtları.

Üretim kaynağı/çalışan bot değişmedi; ağ isteği, ücretliAPI, emir veya otomasyon kullanılmadı. Yeni girdi indirilmedi. Tekrar kontrol: `python research/direction-exit-2026-10-24/study.py verify`. Tekrar ölçüm `study.py run`; ikinci aşama `reaction_context.py run`. Bütün kurallar ve girdiler hash kilitlidir.
'''
    (HERE/'REPORT.md').write_text(text,encoding='utf-8')
    write(HERE/'artifact_manifest.json',{p.name:sha(p) for p in HERE.glob('*.py')})
    print('REPORT complete; no exit candidate confirmed')


if __name__=='__main__':main()
