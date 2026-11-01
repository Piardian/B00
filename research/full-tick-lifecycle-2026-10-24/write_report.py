"""Decision and report after all fixed tick scenarios. No optimization."""
import json
from study import HERE,SCENARIOS,TTLS,write,sha


def load(n):return json.loads((HERE/n).read_text(encoding='utf-8'))


def main():
    rows=load('summary.json');status=load('status.json');integrity=load('integrity.json')
    if integrity['status']!='PASSED' or integrity['outcome_sha256']!=sha(HERE/'outcomes.json'):raise RuntimeError('Ledger integrity required')
    lookup={(r['cohort'],r['scenario'],r['ttl']):r for r in rows};screen={}
    for ttl in TTLS:
        obs=lookup['ALL','OBSERVED_QUOTES',ttl]
        gates=dict(no_unresolved=status['unresolved']==0,at_least50closedfills=obs['fills']>=50,
                   observed_mean_day95_lower_positive=obs['mean_setup_day95'] is not None and obs['mean_setup_day95'][0]>0)
        for scenario in SCENARIOS:
            allrows=lookup['ALL',scenario,ttl]
            gates['positive_total_'+scenario]=allrows['net_r'] is not None and allrows['net_r']>0
            gates['positive_without_marketable_'+scenario]=allrows['net_excluding_marketable_cases']>0
            gates['both_periods_positive_'+scenario]=all(lookup[g,scenario,ttl]['net_r'] is not None and lookup[g,scenario,ttl]['net_r']>0 for g in ['RECHECK','FOLLOWUP'])
        for scenario in ['OBSERVED_QUOTES','COST_STRESS_1_5X']:
            gates['at_least4of6positive_months_'+scenario]=sum(m['closed_only_r']>0 and not m['unresolved'] for m in lookup['ALL',scenario,ttl]['monthly'].values())>=4
        screen[ttl]=dict(passed=all(gates.values()),gates=gates)
    passed=[ttl for ttl in TTLS if screen[ttl]['passed']]
    decision=dict(status='DEMO_CANDIDATE_ONLY' if passed else ('INCONCLUSIVE_DATA' if status['unresolved'] else 'STOP_THIS_ORB_PARAMETER_SWEEP'),
      demo_candidates=passed,demo_started=False,live_approved=False,
      research_scope='Only frozen early-limit London ORB setup/lifecycle; not entire Begonya00/SFP/macro portfolio',
      action='Keep frozen rules for manual paper forward study' if passed else 'Stop TTL/TP/SL sweeps on this frozen branch; preserve artifacts, no production change or project deletion',
      screen=screen,caveat='Historic quote-based simulation, configured commission/slip, no actual fill receipts, macro/news/shared portfolio omitted, previously seen data.')
    write(HERE/'decision.json',decision)
    table=[]
    labels={'OBSERVED_QUOTES':'Gözlenen spread + temel varsayımlar','COST_STRESS_1_5X':'Spread/komisyon/kayma1.5x','SPREAD_FLOOR_1PIP':'1pipspreadtabanı+stres'}
    for scenario in SCENARIOS:
        a=lookup['ALL',scenario,'REFERENCE_240'];b=lookup['ALL',scenario,'TTL_15']
        table.append(f"|{labels[scenario]}|{a['fills']}|{a['net_r']:+.3f}|{b['fills']}|{b['net_r']:+.3f}|")
    months=[]
    for m in sorted(lookup['ALL','OBSERVED_QUOTES','REFERENCE_240']['monthly']):
        a=lookup['ALL','OBSERVED_QUOTES','REFERENCE_240']['monthly'][m];b=lookup['ALL','OBSERVED_QUOTES','TTL_15']['monthly'][m]
        months.append(f"|{m}|{a['closed_only_r']:+.3f}|{b['closed_only_r']:+.3f}|")
    base=lookup['ALL','OBSERVED_QUOTES','REFERENCE_240'];short=lookup['ALL','OBSERVED_QUOTES','TTL_15']
    zero_assumed=base['gross_price_r']+base['assumed_market_slippage_r']
    text=f'''# Tam tick yaşam döngüsü: London erken-limit ORB karar raporu

**Karar: {decision['status']}. Bu dondurulmuş ORB giriş/çıkış kolunda süre/TP/SL taramasını durduruyoruz; demo başlatılmadı.** Gözlenen bid/ask kullanıldığında da iki limit-süresi seçeneği negatif. Bu karar Begonya00'ın bütün SFP/makro/varlık stratejilerinin matematiksel olarak imkânsızlığı iddiası değildir.

## İstenen sıra tamamlandı

1.90kurulum için dolum,ilkstop,TP1/TP2,kısmi kapatma,BE/trailing,olumsuztepki çıkışı veLondon16:30sonu kronolojikquote düzeyinde yeniden oynatıldı.
2.Aynı giriş/stop/hedef ve kurulum setinde240dakika(noonkapı) ile15dakika(noonkapı) karşılaştırıldı. Saat sınırı münhasır; dolmuş pozisyon süre doldu diye kapatılmadı.
3.Önceden sabitlenen kâr/dayanıklılık kapılarıyla demo/araştırma kararı verildi. Pozitif sonuç elde etmek için ilave eşik taranmadı.

## Sonuçlar

**NetR, gerçekleşmiş hesap getirisi değildir:** arşivdeki gözlenenbid/ask fiyatları + açık komisyon/kayma varsayımlarıyla araştırma simülasyonudur. R ilk kotasyon-fiyat riskine normalize edilir; sermaye,marj ve eşzamanlı risk portföyü uygulanmaz.

|Senaryo|Mevcut süre dolum|Mevcut süre netR|15dk dolum|15dk netR|
|---|---:|---:|---:|---:|
{chr(10).join(table)}

Temel senaryoda PFler mevcut sürede{base['pf']:.3f},15dakikada{short['pf']:.3f}.15dakika toplam kaybı{short['net_r']-base['net_r']:+.3f}Razaltıyor; fakat işlem başına sonuç mevcutta{base['net_r']/base['fills']:+.3f}R,15dakikada{short['net_r']/short['fills']:+.3f}R. Yalnız daha az işlem ve daha küçük toplam zarar, daha kaliteli/pozitif bir giriş seçildiğini göstermiyor.

|Ay,gözlenen spread|Mevcut süre netR|15dk netR|
|---|---:|---:|
{chr(10).join(months)}

Altı ayın ikisi temel senaryoda artı,dördü eksi. Daha önce işaretlenen marketableaçılış vakası çıkarıldığında da temel sonuçlar mevcutta{base['net_excluding_marketable_cases']:+.3f}R,15dakikada{short['net_excluding_marketable_cases']:+.3f}R; kararı o tek vaka belirlemiyor.

Komisyon ve varsayımsal kaymayı aynı işlem yolu üzerinde sıfırlayan muhasebe duyarlılığında bile mevcut sürenin fiyat sonucu **{zero_assumed:+.3f}R**. Gözlenen spread hâlâ fiyatın içindedir. Bu yeni bir giriş/çıkış stratejisi denemesi değil; aynı olay defterinden varsayımsal iki maliyeti geri eklemektir. Sonucu yalnız komisyon tarifesinin belirsizliği açıklamıyor.

## Veri ve değişmeyen strateji seviyeleri

Şubat/Mart25,Nisan/Mayıs/Eylül/Ekim65 olmak üzere90önceden kilitlenmiş ilk-günlük kurulum; altımajörFXparitesi. Ocak/Kasım bu90kurulumda yok. Altın,makro/haber,SFPönceliği ve ortakportföyriski yok; tam Begonya00motor backtesti değildir. Veriler daha önce incelendi; yeni OOS veya prospektifforward iddiası yok.

Giriş/ilkstop/TP1/TP2,önceki cases_frozen.json ile byte düzeyinde aynı veriden alındı. Emir, gerçekaskın buyentryden bir tick aşağısına veya gerçekbidin sellentryden bir tick yukarısına geçtiği ilk kayıtta nominal limit fiyatından dolmuş varsayılır; lehte fiyat iyileşmesi yazılmaz. Likidite/kuyruk/gerçekbroker dolum fişi bilinmez. Marketableaçılış ayrıca işaretlenir; o vakanın çıkarılmasıyla duyarlılık da gösterilir.

Mevcut tamseans tape'leri16:00da bitiyordu.90kurulumun tamamı için seans sonu16:00–16:31gerçekbid/askkuyruğu mevcut aynıbrokerönbelleğinden, getiri hesaplanmadan önce alındı. Veriler birleştirilirken örtüşen16:00kısmı tekrarlanmadı; aynı milisaniyedeki kayıt sırası korundu. İnterpolasyon yok. İlkquote en fazla5saniye sonra; terminalolaya kadar60saniyeden büyük boşluk netR üretmez.

## Tick icrası ve mum proxy'si arasındaki açık farklar

-İlk stop dolum anı dahil herquoteda aktiftir; longbid,shortask tetikler. Gap varsa o anda gözlenen daha kötü fiyat ve varsayımsal olumsuzkayma kullanılır.
-**Dolumun bütün M1mumunda TP kredisi yoktur.** Dolum mumu tepki şekli yalnız tamamlandığında bilinir; olumsuz tepki çıkışı önceki kapanış fiyatından değil sonraki ilk gerçekquotedan olur. Bu örneklemde bu karar ile icra arasındaki en büyük bekleme1.617saniye.
-TP1'deyarı,TP2'dekalan nominalhedef fiyatından kapanır; aynıquote ikihedefi aşarsa iki parçanın nominalseviyeleri kullanılır. Lehte gap kazancı eklenmez.
-M1belirsizliğinin aksine, tickte TP1'in daha sonraki stoptan önce geldiği biliniyorsa kısmi kâr korunur. Stop,target aynıquoteda çakışırsa stopönceliği sürer. Bu, sinyal/hedef değişikliği değil kronolojik icra doğrulamasıdır.
-BE,TP1mumundan sonraki ilkM1quote'da etkin olur.1.5Rde0.75Rtrailing,TP1mumundan sonraki mumlarda aranır ve takipedenM1de etkinleşir; yeni stop geçmişquotelara uygulanmaz.
-London16:30da ilkquote'dan piyasa kapanışı yapılır. Dolumsuz emrin iptali kazanç veya ücret üretmez.

Bu yürütme sözleşmesi önceki araştırma yaşam döngüsünü gerçekquotelara açıkça uyarlar; eski canlıbotla byte düzeyinde aynı icra motoru diye adlandırılmaz. Önceki M1proxy netRleriyle farkı yalnız spread farkına bağlamak da yanlış olur: kronoloji ve tepki çıkış fiyatı da netleşmiştir.

## Maliyet ayrımı

Temel senaryo: gözlenen ask-bid,kontrat100binbirim başına4USDroundtripkomisyon(2açılış+2kapanış,kısmi çıkışlarda ağırlıklı) ve yalnız piyasa çıkışında0.2pip olumsuzkayma. USD-bazlı paritelerde komisyon ilgili fiyatla kotasyon para birimine çevrilir. Tarihsel hesaba ait komisyon/kayma fişleri doğrulanmadı.

1.5xstres ask-bidfarkını,komisyonu ve kaymayı1.5ile çarpar; **1.5pip spread** demek değildir. Ek muhafazakâr senaryoda aynıstresle spreadenaz1pip alınır; hamarşivdeki sıfırspreadlere karşı duyarlılık sağlar. Bu son senaryonun askı sentetiktir; gözlenenask diye etiketlenmez.

Spread,icra fiyatlarının içindedir ve ayrıca tekrar düşülmez. Komisyon,kayma ve olaylar ayrı alanlarda tutulur. Gözlenen spreadin sıfır olması ücretsiz/garantili işlem anlamına gelmez. Hiçbir senaryo gerçek hesap kazancı sertifikası değildir.

## Karar kapıları

Önceden demo adayı sayılabilmek için≥50kapalıdolum,gözlenen senaryoda pozitif gün-küme95%alt sınırı,üçmaliyet altında pozitif toplam ve ikiayrı dönem grubunda pozitiflik,gözlenen/stres altında≥4/6pozitifay,çözümlenmemişkayıt olmaması ve marketablevakalarçıkarılınca artı toplam arandı. Hem mevcut süre hem15dakika başarısız oldu. Bütün kapılar decision.jsonda saklıdır; negatifsonuçta örneklem veya eşik değiştirilmedi.

**Somut karar:** bu dondurulmuş Londonerken-limitORB tanımında yeni süre/TP/SL taraması yapılmayacak; demo başlatılmayacak. Üretim kodunu silmek, çalışanbotu durdurmak veya Begonya00'ın diğerstratejilerini iptal etmek bu kararın parçası değil. Farklı giriş hipotezi araştırılacaksa ayrı protokol ve yeni kanıt gerektirir; mevcutkolu kârlıymış gibi sunmayacağız.

## Kontroller ve tekrar üretim

-14test geçti:long/shortquote tarafı,gapstopu/komisyon,tepkiçıkışınınsonrakiquote'danicrası,dolum-mumuTPyasağı,kısmiücret,BE/trailingzamanı,tickkronolojisikısmiTPsonrastop,TTL15sınırı,dolmuşişleminsüreötesitakibi,quote boşluğu,spreadtabanı,eksikkuyrukta netRvermeme,16:30kapanışveUSDbasekısmiücret.
-90kurulum×3maliyet×2süre=540replaykaydı; bağımsız540işlem değildir. Çözümlenmemiş kayıt:{status['unresolved']}.
-Gözlenen senaryonun90kurulumundaki ilk-dolum/dolumsuzluk kayıtları önceki bid/asktickdenetimiyle birebir eşleşti. Aynı dolumu koruyan kısa/uzunTTL yollarının bütün olay defterleri de aynı.
-Açılış/kapanış miktarı1,defter ücretleri,net=gross−komisyon,dolumsuzemirde0ücret kontrolleri geçti. integrity.json bu kontrolleri outcomes.jsonhashine bağlar.
-Kaynak,90tamseanstape,90kuyruk ve girdiler hashlerle kilitli.14test, veri/broker dolum sertifikası değil, model davranış kontrolüdür.

Dosyalar:protocol.json,cases_frozen.json,tail_manifest_frozen.json,outcomes.json(olaydefterleri),summary.json,integrity.json,decision.json. Tekrar kontrol:

```
python research/full-tick-lifecycle-2026-10-24/study.py verify
python research/full-tick-lifecycle-2026-10-24/validate_results.py
```

Emir,ücretliAPI,otomatikdevam veya üretimkodudeğişikliği yok. Brokererişimi yalnız önbellekteki teklifleri okumaktı; kullanıcı dosyası silinmedi. Demo ileri test yalnız kapılar geçse hazırlanacaktı; bu çalışmada geçilmedi.
'''
    (HERE/'REPORT.md').write_text(text,encoding='utf-8')
    write(HERE/'artifact_manifest.json',{p.name:sha(p) for p in HERE.glob('*.py')})
    print(json.dumps({k:v for k,v in decision.items() if k!='screen'},indent=2))


if __name__=='__main__':main()
