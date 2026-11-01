"""Reports both locked15minuteTTL stages; never tunes rules."""
import json
from study import HERE,sha,write,day_ci


def load(name):return json.loads((HERE/name).read_text(encoding='utf-8'))


def main():
    summaries=load('summary.json');comparisons=load('comparisons.json');initial_status=load('status.json')
    status=load('followup_status.json')
    if status['status']!='COMPLETE':raise RuntimeError('Cannot issue complete followup report on missing/unresolved data')
    follow=load('followup_summary.json');pairs=load('followup_pairs.json')
    old={(r['source'],r['spread_pips'],r['variant']):r for r in summaries}
    new={(r['spread_pips'],r['variant']):r for r in follow}
    gates={}
    for sp in [.5,1.5]:
        base=new[sp,'REFERENCE_240'];short=new[sp,'TTL_15']
        gates[f'improves_followup_total_{sp}pip']=short['net_r'] is not None and base['net_r'] is not None and short['net_r']>base['net_r']
        gates[f'every_followup_month_positive_{sp}pip']=all(m['fills']>0 and m['closed_only_r']>0 for m in short['monthly'].values())
    gates['followup_no_unresolved']=all(r['unresolved']==0 for r in follow)
    decision=dict(status='SCREEN_SURVIVED_NOT_EDGE_PROVEN' if all(gates.values()) else 'TTL15_NOT_CONFIRMED',gates=gates,live_promotion=False,
      caveat='Both stages retrospective; same setup-only assumed-cost model. Do not equate smaller loss with positive edge.')
    write(HERE/'decision.json',decision)
    lines=[]
    for sp in [.2,.5,.9,1.5]:
        a=old['ALL',sp,'REFERENCE_240'];b=old['ALL',sp,'TTL_15']
        lines.append(f"|{sp:.1f}pip|{a['fills']}|{a['net_r']:+.3f}|{b['fills']}|{b['net_r']:+.3f}|{b['net_r']-a['net_r']:+.3f}|")
    followlines=[];monthly=[];follow_changes=[]
    for sp in [.2,.5,.9,1.5]:
        a=new[sp,'REFERENCE_240'];b=new[sp,'TTL_15']
        followlines.append(f"|{sp:.1f}pip|{a['fills']}|{a['net_r']:+.3f}|{b['fills']}|{b['net_r']:+.3f}|{b['net_r']-a['net_r']:+.3f}|")
        rows=[r for r in pairs if r['spread_pips']==sp]
        follow_changes.append(dict(spread_pips=sp,mean_delta_day95=day_ci(rows,lambda r:r['delta_r']),removed_fills=sum(r['removed'] for r in rows)))
    for month in ['2025-04','2025-05','2025-09','2025-10']:
        a=new[.5,'REFERENCE_240']['monthly'][month];b=new[.5,'TTL_15']['monthly'][month]
        stress=new[1.5,'TTL_15']['monthly'][month]
        monthly.append(f"|{month}|{a['closed_only_r']:+.3f}|{b['closed_only_r']:+.3f}|{stress['closed_only_r']:+.3f}|")
    write(HERE/'followup_comparisons.json',follow_changes)
    gate_lines='\n'.join(f"- {name}: {'GEÇTİ' if value else 'GEÇMEDİ'}" for name,value in gates.items())
    follow_outcomes=load('followup_outcomes.json')
    find={(r['case_id'],r['spread_pips'],r['variant']):r for r in follow_outcomes}
    removal=[]
    for sp in [.5,1.5]:
        removed=[r for r in follow_outcomes if r['spread_pips']==sp and r['variant']=='REFERENCE_240' and r['filled_at'] and not find[r['case_id'],sp,'TTL_15']['filled_at']]
        removal.append(dict(spread_pips=sp,removed=len(removed),missed_winners=sum(r['net_r']>0 for r in removed),avoided_losers=sum(r['net_r']<0 for r in removed),missed_profit_r=sum(r['net_r'] for r in removed if r['net_r']>0),avoided_loss_r=-sum(r['net_r'] for r in removed if r['net_r']<0)))
    write(HERE/'followup_removed_breakdown.json',removal)
    primary=old['RECHECK',.5,'TTL_15'];combined=old['ALL',.5,'TTL_15']
    c=next(r for r in comparisons if r['source']=='ALL' and r['spread_pips']==.5)
    text=f'''# Dolum gecikmesi: sabit15dakikalık limit ömrü araştırması

**Karar: {decision['status']}. Canlıya terfi yok.** Bütün aşamalarda aynı15dakika sınırı ve kontrol grubu korundu. Sınır eşiği veya parite/ay seçimi sonuçlara göre taranmadı.

## Deney

Sadece bekleyen limit emrin geçerlilik süresi değişti:

-Referans: en fazla240dakika; London12:00 daha erkense orada biter.
-Aday: en fazla15dakika; London12:00 daha erkense orada biter.

Emir `[sinyalin kullanılabilir olduğu an, son geçerlilik anı)` aralığında aktiftir. **Tam15.dakikadaki temas kabul edilmez.** Önceki betimleyici≤15dakika grubu ile bu sınır aynı tanım değildir; eşitlik davranışı sonuçlardan önce sabitlendi. İlk15dakikada dolmuş pozisyon sonrasında normal çıkış kurallarıyla takip edilir;15.dakikada zorla kapanmaz. İptal edilen emir o günün denemesini tüketir; başka adayla değiştirilmez.

Giriş,ilkstop,TP1/TP2,olumsuztepkiçıkışı,kısmi kapatma,BE/trailing veLondon16:30araştırma kapanışı aynı. Stopönceliği ve dolum-mumuTPyasağı korunur. Bu motor üretim botunun tüm makro/haber/SFP/ortakrisk kararları değildir; setup araştırmasıdır. Altın yok.

Maliyetler aynı varsayımlı sözleşme:0.2/0.5/0.9/1.5pip sabitspread,100binbirime4USDround-trip komisyon,0.2pip olumsuz piyasa çıkış kayması. BidM1 gerçektir; tarihsel ask,hesap komisyonu ve kayma gerçekleşmeleri doğrulanmadı. NetR birim ilk fiyat riskine normalize edilmiş fırsat toplamıdır; hesap/portföy getirisi değildir.

## Aşama1: önceki58kurulumda ölçüm

Ocak/Kasım33 ve Şubat/Mart25kurulum değişmeden alındı. Hepsi daha önce görüldü; burada yeni OOS iddiası yok. İki süre için de bütün kurulumlar korunur; iptal/no-fill sıfır getiridir, kazanan işlem değildir.

|Spread|Referans dolum|Referans netR|15dk dolum|15dk netR|FarkR|
|---|---:|---:|---:|---:|---:|
{chr(10).join(lines)}

Ana0.5pip senaryosunda 15dk sınırı12geçdolumu eliyor:11zararlı,1kârlı. Toplam{c['avoided_loss_r']:.3f}Rkayıp engellenirken{c['missed_profit_r']:.3f}Rkâr kaçırılıyor; fark{c['net_delta_r']:+.3f}R. Bu, düşürülen işlemlerin hesapta başka işlemle değiştirildiği anlamına gelmez.

Şubat/Mart özelinde23dolum19a indi; dörtelenen dolum da ana ve stres senaryolarında zararlı. Ana sonuç−4.874Rden−3.419Rye iyileşti; **iki ay da hâlâ eksi**.0.2pip senaryosunda Şubat/Mart biraz kötüleşti (−1.707→−1.930R); iyileşme her örneklem/maliyette geçerli değil.

Dört ayın ana15dk sonucu+3.661R; fakat Ocak+10.181R,Şubat−2.064R,Mart−1.355R,Kasım−3.101R. Sadece toplam artıya bakmak rejim bağımlılığını gizler.232önceki referans kaydı birebir yeniden üretildi; kalan erken dolumların bütün yaşam döngüsü ve netRsi değişmedi. Toplam464replaykaydı bağımsız464işlem değildir. Çözümlenmemiş replay:{initial_status['unresolved']}.

## Aşama2: ayrı dört ayda kontrol

İlk sonuç görüldükten sonra aynı15dk süresi **Nisan,Mayıs,Eylül,Ekim2025** için ayrı followup_protocol.json ile sabitlendi. Aylar mevcut tam tick arşivi olduğu için birlikte seçildi; yeni bu kurulumların sonuçları önceden okunmadı. Fiyatlar başka bir klasikORB araştırmasında kullanılmıştır; dolayısıyla tamamen dokunulmamış proje-geneli OOS veya prospektifforward değildir. Bu süre kuralının ek dönem kontrolüdür.

Altıparite×89haftaiçigün=534parite-günü. AsyaM15,Londonaralığı/giriş gridleri ve geçmişATR girdileri kontrol edildi; yeni{status['candidates']}ilk günlük kurulum seçildi. Tüm pariteler ve aylar korunur. NativeH1/M15bağlamı; mevcut tick arşivi ve önbellekteki16–16:31kuyruğundan M1. İnterpolasyon yok. Her paritede89×511=45479LondonM1satırı. Veri eksikleri veya işlem kuyruğu bilinmezliği netkârla doldurulmadı.

|Spread|Referans dolum|Referans netR|15dk dolum|15dk netR|FarkR|
|---|---:|---:|---:|---:|---:|
{chr(10).join(followlines)}

|Yeni ay|Referans0.5pip netR|15dk0.5pip netR|15dk1.5pip netR|
|---|---:|---:|---:|
{chr(10).join(monthly)}

## Önceden sabitlenen karar kapıları

{gate_lines}

Başarılı aday saymak için ek dönemde hem0.5hem1.5pip altında toplamı iyileştirmesi ve dört ayın her birinde dolumla pozitif kalması istendi. Daha az zarar veya sıfır işlem başarı sayılmaz. İlk dört ayın toplamı, başarısız ek dönemleri kurtarmak için kullanılmaz. Gatesonucu olumlu olsa bile gerçek maliyet/ileri dönem kanıtı olmadan canlı onayı verilmez.

Gün-küme bootstrap aralıkları comparisons.json ve followup_comparisons.json içindedir:10000örnek,95%yüzdelik,kurulum başına eşleştirilmiş fark. Aynıgün pozisyonları birlikte çekilir. Önceki çoklu hipotezleri ve tam seri bağımlılığı düzeltmez; yeni dört ay da geriye dönüktür. Az sayıdaki silinen işleme dayalı dar aralık edge kanıtı değildir.

## Uygulanabilir çıktı

**Nihai yorum:**15dakika sınırı bağımsız bir kâr kaynağı olarak doğrulanmadı. Ek dönemde ana maliyette zarar−12.548Rden−10.849Rye düşüyor; streste−12.785Rden−13.837Rye büyüyor. Ana senaryoda elenen10geçdolumun2si kârlı,8i zararlı; streste elenen11dolumun5i kârlı,6sı zararlı. Süre sınırı kazanan fırsatları da iptal ediyor. Ek dönem eşleştirilmiş farkının gün-küme aralığı her maliyette sıfırı içeriyor.

Hızlı dolan38işlem de ana modelde−10.849R bırakıyor; komisyon düşülmeden önceki fiyat sonucu dahi−8.862R (spread/kayma hâlâ fiyat içindedir). Bu, sorunun yalnız komisyon veya geçdolum olmadığını gösterir. Bekleme süresini daha da kısaltmanın edge sağlayacağına dair sonuç yok; yeni süre taraması yapılmadı. Bu sabit15dakika kuralı üretime alınmamalı; yararlı bir gözlem alanı olarak dolum gecikmesi kaydı korunabilir. Sonraki yeni strateji araştırması bu giriş setinin yapısal yön/kurulum avantajını değiştiren açık bir hipotez gerektirir; süre/TP/SL ayarıyla kâr varmış gibi sunulamaz.

Bekleyen emre süre koyan araştırma parametresi hazır. Kural yalnız emir dolmadan önce çalışır; dolmuş zararları silmez. Geçdolum sepeti, kaçırılan kazançlar ve önlenen kayıplar ayrı kaydedilir. Bu, sürenin risk etkisini izlenebilir hale getirir. Modelde daha iyi görünen toplamlar tek başına kârlı strateji anlamına gelmez. 10/20/30dakika taraması veya sonuçlara göre yeni giriş/stop/çıkış değişikliği yapılmadı.

## Test ve bütünlük

10test geçti:15dakika sınırında dolum yasağı,14.dakika dolumu, dolmuş pozisyonun süre sonrası takibi, referansta gerçek geçdolum ve ücret,Londonnoon sınırı,eksikM1,stopönceliği ve geçersizsüreler.232referans eşitliği ve korunan dolumların netR/lifecycle eşitliği çalışma içi zorunlu kontrol. Ek dönemde de retainedfill eşitliği ve iptal edilen emrin sıfırdolum/ücreti kontrol edildi.

protocol.json ilk58kurulumu; followup_protocol.json ayrı4ay planını ve kaynaklarını kilitler. summary.json/outcomes.json/paired_records.json/age_groups.json ilk aşama; followup_summary.json/outcomes/pairs/coverage ek aşamadır. Bütün kaynak/veri hashleri tekrar denetlenir.

Üretim kaynağı ve çalışan bot değiştirilmedi; emir, ücretliAPI veya otomatik devam görevi yok. Ek aşamadaki MT5erişimi saltokuma ve mevcutönbellekle sınırlıydı. Küçükbarçıktıları için1GiBboşluk/64MiBnetbüyüme sınırı kullanıldı; hiçbir kullanıcı kaynağı silinmedi.

Tekrar kontrol:

```
python research/fill-delay-2026-10-24/study.py verify
python research/fill-delay-2026-10-24/followup.py check
```
'''
    (HERE/'REPORT.md').write_text(text,encoding='utf-8')
    write(HERE/'artifact_manifest.json',{str(p.relative_to(HERE)):sha(p) for p in list(HERE.glob('*.py'))+list((HERE/'frozen_engine').glob('*.py'))})
    print(json.dumps(decision,indent=2))


if __name__=='__main__':main()
