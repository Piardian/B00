from pathlib import Path
from datetime import datetime,timezone
import json,hashlib
import pandas as pd
BASE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    protocol=json.loads((BASE/'protocol_frozen.json').read_text())['declaration']
    for path,digest in protocol['files'].items():assert sha(Path(path))==digest,path
    manifest=json.loads((BASE/'quote_manifest_frozen.json').read_text())
    for meta in manifest['files'].values():assert sha(Path(meta['path']))==meta['sha256']
    payload=json.loads((BASE/'results.json').read_text())
    native_payload=json.loads((BASE/'native_results.json').read_text());result=native_payload['results']
    native_protocol=json.loads((BASE/'native_volume_protocol.json').read_text())['declaration']
    for path,digest in native_protocol['files'].items():assert sha(Path(path))==digest,path
    native_qa=json.loads((BASE/'native_bar_qa.json').read_text());assert native_qa['passed']
    qa=json.loads((BASE/'clock_h1_qa.json').read_text());rows=json.loads((BASE/'native_outcomes.json').read_text())
    pd.DataFrame([{k:v for k,v in x.items() if k!='outcome'}|x['outcome'] for x in rows]).to_csv(BASE/'outcomes.csv',index=False)
    complete=payload['status']=='COMPLETE_QUOTE_REPLAY'
    primary=result['CLASSIC_RVOL_GE1'];observed=primary['OBSERVED_QUOTES_1x']
    gates=dict(complete_tape=complete,independent_clock=qa['passed'],at_least100fills=observed['fills']>=100,
        positive_both_months=all(v>0 for v in observed['by_month'].values()),
        observed_ci_lower_positive=observed['block_total_ci95'][0]>0,
        positive_stress_1_5x=primary['COST_STRESS_1.5x']['net_r']>0,
        positive_stress_2x=primary['COST_STRESS_2x']['net_r']>0,
        positive_spread_floor_1pip=primary['MIN_SPREAD_1PIP']['net_r']>0)
    gates['research_candidate_gate_passed']=all(gates.values())
    (BASE/'gate_results.json').write_text(json.dumps(gates,indent=2))
    info=pd.DataFrame(manifest['files'].values());evaluation=info[~info.warmup]
    text=['# Sabit London ORB — The5ers bid/ask doğrulaması','',
        '**İşlem verisinin tamamı FivePercentOnline-Real sunucusundan, doğru The5ers terminali üzerinden salt okunur geçmiş tick çağrılarıyla alındı. Canlı/paper emir gönderilmedi.**','',
        f"Durum: {payload['status']}. Önceden sabitlenen araştırma kapısı: {'GEÇTİ (yalnız araştırma adayı)' if gates['research_candidate_gate_passed'] else 'GEÇİLEMEDİ; doğrulanmış pozitif edge yok'}. Sonuç hazırlandığı UTC: {datetime.now(timezone.utc).isoformat()}.", '',
        '## Dönem ve değişmeyen kurallar','',
        'Yeni dönemler Şubat ve Mart2025; önceki araştırmadaki Ocak/Haziran/Kasım2025ten ayrıdır. Bu gerçek ileri dönem değildir, farklı tarihsel dönem doğrulamasıdır. EURUSD,GBPUSD,USDJPY,USDCAD,USDCHF,NZDUSD.41işlem günü,246parite-günü; önceki14işgünü açılış hacmi hazırlığıyla330dosya.', '',
        'Ana hipotez CLASSIC_RVOL_GE1, karşılaştırma CLASSIC_ALL. London08:00–08:15bidaralığı, açılış mumunun yönündeki ilk bidkırılımı,12:00öncesi yeni giriş, parite başına tek günlük işlem. Karşıbidbant yapısalstop, tam2Rhedef ve16:00London’da ilk gelen kotasyonda günsonu çıkış. TP1,BE,trailing,retest,HTF veya yeni eşik taraması yok. RVOL ilk15dakika MT5BIDbayrağı2güncelleme sayısının aynı kaynaktaki önceki14mevcut08:00açılışın ortalamasına oranıdır; eşik≥1. Bu, önceki stratejinin nativeM15tick_volume alanıdır, merkeziForexişlem hacmi değildir.', '',
        'Alış gözlenenask, satış gözlenenbid üzerinden modellenir; longkapanışıbid, shortkapanışıasktır. Shortyapısalstop önceki sabit modeldeki karşıbidbandına göre sanal tetiklenir; başlangıç riskine giriş spreadi dahil edilir. Bu,MT5sellpozisyonuna sabitaskSLemri gönderiminin birebir taklidi değildir. Tick sırası kullanılır; gapte gözlenen daha kötü kotasyon esas alınır. Gözlenen kotasyonlar gerçek emir kuyruğu veya garantili dolum belgesi değildir.', '',
        '## Net sonuçlar','',
        '| Model | Gider senaryosu | Dolum | NetR | PF | ŞubatR | MartR |',
        '|---|---|---:|---:|---:|---:|---:|']
    for cohort,scenarios in result.items():
        for name,z in scenarios.items():
            text.append(f"| {cohort} | {name} | {z['fills']} | {z['net_r']:+.2f} | {z['pf']:.2f} | {z['by_month']['2025-02']:+.2f} | {z['by_month']['2025-03']:+.2f} |")
    text+=['','OBSERVED_QUOTES_1x gerçek tarihselbid/askalanlarını kullanır.0.1pip/yönkayma ve4USD/100000birimroundtripkomisyon varsayımdır; geçmiş kişisel hesap masrafları uzlaştırılmadı. USD-bazlı paritelerde giriş kuru yaklaşımıyla quotepara birimine çeviri yapılır. Dolayısıyla bu gerçek fiyatlarla modellenmiş netRdir; gerçekleşmiş hesap kârı değildir.', '',
        '1.5x/2x senaryolar gözlenenask-bidfarkını, varsayılan kayma ve komisyonu artırır. Stres fiyat ve hedefleri değiştirip başka kapanışlara yol açabilir; bunlar sabit dolum maliyetleri diye sunulmaz. MIN_SPREAD_1PIP senaryosunda spread gözlenen değer ile1pipten büyük olanıdır; diğer giderler temeldedir. Bu, gerçek spreadlerin üzerine ayrıca1pipekleme değildir.', '',
        '## Kotasyon kalitesi ve saat','',
        f"Toplam hazırlık+doğrulama kaydı: {int(info.rows.sum()):,} tick. Günler içi kaynakta negatif/crossedaskbid, açılış/EODeksikliği veya60saniyeüstüboşluklar kapıdan geçirilmez. Tam dönem durumunun tamamlanması bütün gerekli dosyaların varlığını gerektirir. EksiklerinPnLsi sıfır yapılmaz.", '',
        '| Parite | Doğrulama tick sayısı | Ortalama günlük sıfırspread oranı | En uzun boşluk(sn) |','|---|---:|---:|---:|']
    for s,g in evaluation.groupby('symbol'):
        text.append(f"| {s} | {int(g.rows.sum()):,} | %{g.zero_spread_fraction.mean()*100:.2f} | {g.max_gap_seconds.max():.3f} |")
    text += ['',
        'Özellikle EURUSD,GBPUSD,USDJPYde çok sayıda sıfırspread vardır. Bunlar brokerın ham tarihsel kotasyon alanlarıdır; gerçek işlemde her tickte aynı spreadle dolum alındığını doğrulamaz. Bunları sessizce genişletmedik veya silmedik. Ayrı1pipfloorstresi, olumlu bir sonucun bu özelliğe bağımlılığını değerlendirir.', '',
        f"Saat: geçmiş brokerUTC+2/+3US-DSTpolitikası kullanıldı. YeniEURUSDkotasyonlarını bağımsızYahooH1fiyatlarıyla kıyaslayan önceden kaydedilmişQAda{qa['strong_days']}günde güçlü eşleşme,{len(qa['conflicts'])}çelişki; toplam saatlik getiri korelasyonu{qa['pooled_corr']:.4f}. Yahoo verisi yalnız saat kontrolünde kullanıldı; strateji fiyatları/hacmi değildir. İlkM15referans arşivinin yalnız2günü örtüştüğü için20gün kapsamkapısı geçilememişti; bu eksik rapor saklandı. Daha kapsamlıH1referansı kullanma gerekçesi ve kriterleriPnLöncesinde kaydedildi.", '',
        '## Belirsizlik ve araştırma kapısı','']
    for name,z in result['CLASSIC_RVOL_GE1'].items():
        lo,hi=z['block_total_ci95'];text.append(f"- Ana model {name}:5gözlemgünüblokbootstrap%95toplamRaralığı[{lo:+.2f},{hi:+.2f}]R.")
    text += ['',
        '## Hacim uygulaması tutarlılık denetimi','',
        'İlk tick uygulaması bidveaskgüncellemelerinin tamamını hacim sayıyordu. Önceki klasik model nativeM15tick_volume kullanıyordu. Bu fark PnLsonrası uygulama kontrolünde bulundu; eski sonuçlar silinmedi. NativeM15hacmi MT5BIDbayrağı2sayımıdır. Doğrudan sunucudan tekrar okunan330M15mumunun hacmi, tepe/dibi ve yönü tickten üretilenlerle330/330eşleşti. Parametre, dönem ve eşik değiştirilmedi; fiyat geometrisi246doğrulamagününün hiçbirinde değişmedi.', '',
        'Bu rapordaki ana tablo orijinalnativeM15hacimtanımını koruyan native_results.json sonucudur. Tümkotasyonolaylarınısayansürümresults.jsonda korunur:84dolum,+17.41Rtemel,+12.57R1.5x. Nativehacim78dolum,+18.94Rtemel,+14.22R1.5x. Bu karşılaştırma uygulama revizyonudur, ikinci bağımsız kanıt değildir. İlk sonuçlar görülmüş olduğu için çalışma kusursuz dokunulmamış tekbirOOSdeneyi olarak sunulmaz. native_volume_protocol.json gerekçeyi ve kaynak hashlerini yeni hesap öncesi kaydeder.', '',
        '## Önceki olumsuz dönemler ve karar','',
        'Daha önceki Ocak/Haziran/Kasım2025sentetikspread/M1modeli olumsuzdu. Bu yeni iki olumlu ay o sonuçları ortadan kaldırmaz. Tick sırası,gözlenenbidaskveörneklemdönemleri öncekiM1varsayımlarından farklı olduğundan Rtoplamlarını tek bir performans serisi gibi toplamayın. Olumlu ayların kalıcı bir rejimi mi, örneklemşansını mı veya maliyetmodeli farkını mı yansıttığı daha geniş dönemlerle ayrılmalıdır. Henüz canlı kullanım gerekçesi yoktur.', '',
        'Bu aralıklar bütün geçmiş strateji/evren seçimlerini düzeltmez. GünlükRler farklı paritelerde eşzamanlı birim riskli fırsat toplamlarıdır; portföyde marj, toplam açık risk, günlük kayıp freni ve para cinsinden bileşik getiri uygulanmış değildir. Gerçekhesapdrawdownı raporlanmaz. Bütün kapıların geçilmesi bile yalnız daha güçlü bir araştırma adayı üretir, canlı onay değildir.', '',
        'Önceden sabitlenen kapılar: tam veri+saatdoğrulaması,ana modeldeenaz100dolum,ikiayın dapozitifolması,1xgüvenaralığıaltsınırınınpozitifolması,1.5x/2xgiderve1pipfloorstresindepozitifkalması. AyrıntılıTrue/False sonuçlar gate_results.json içindedir.', '',
        '## Veri erişimi ve güvenlik','',
        'VarsayılanMT5bağlantısı yanlış terminale gittiği için ilk denemeAuthorizationfailedverdi. Açıkça C:/Program Files/Five Percent Online MetaTrader 5/terminal64.exe seçilince doğru sunucudan geçmişveri okundu. Giriş bilgisi değiştirilmedi, şifre raporlanmadı. Kullanıcı yalnızThe5ersistediği için alternatifDukascopykaynağı kullanılmadı. DNS/429başarısız yoklamalarıperformansverisine dönüşmedi.', '',
        '10test geçti:bidaskyönü,askalış,bid/askdoğrukapanış,gapstop,kotasyonboşluğu,EOD,saat sınırı,gelecekteki fiyatın aralığa sızmaması,sıfırspreadfloorstresi,nativeBIDhacimve collector’ın yalnız okumaMT5çağrılarını kullanması. Kaynak ve330veridosyasınınhashleri sonuç sonunda yeniden doğrulandı. Üretimstratejisi, çalışanbot ve canlı emir ayarları değiştirilmedi;otomasyon kurulmadı.', '',
        'Dosyalar: protocol_frozen.json, quote_manifest_frozen.json, tapes/, clock_h1_qa.json, native_volume_protocol.json, native_bar_qa.json, gate_results.json, native_results.json, native_outcomes.json ve outcomes.csv. İlkquote-volumehesabıresults.json/outcomes.jsonda korunur. Hamquotealanları,orijinalnumpybaythashleri,sembolözellikleri ve saat dönüşüm politikası kayıtlıdır.']
    (BASE/'SONUC.md').write_text('\n'.join(text)+'\n',encoding='utf8')
    print('Verified source/tape hashes; research gates:',gates)
if __name__=='__main__':main()
